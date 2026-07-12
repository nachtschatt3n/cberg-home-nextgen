# Voice Pipeline — HA Voice PE → local intents → OpenClaw fallback

Version: 2026.07.12 · Status: **in build** · Owner: Mathias + Claude session log

Goal: wake-word voice on the HA Voice PE satellite; common commands handled by
HA's local intent engine (<2 s), free-form queries falling back to the OpenClaw
`voice` agent on local Ollama (`gemma4:e2b-mlx`, Mac Mini). STT/TTS local.

## Architecture

```
Voice PE (09c778) ── wake "Okay Nabu"
  └─ HA Assist pipeline "Local + OpenClaw"   [pending creation]
       STT  : wyoming faster-whisper  @ 192.168.30.111:10300
       Intents: HA local-first (prefer_local_intents: true)
       Conv : custom_conversation → OpenClaw /v1  [pending]
       TTS  : tts.openai_tts_qwen3_voice → mlx-audio @ 192.168.30.111:8000
  └─ OpenClaw gateway (ai ns, :18789, token auth)
       agent "voice" → ollama-native/gemma4:e2b-mlx (Mac Mini :11434)
       tools: homeassistant MCP (HA core MCP Server, SSE)
```

## Change log — exactly what was done, where

### 1. Mac Mini host (Mathiass-Mini, 192.168.30.111) — manual, NOT GitOps
| What | Where |
|---|---|
| Installed `uv` 0.11.28 | homebrew |
| Installed wyoming-faster-whisper 3.5.0 (model `small-int8`, `--language auto`) | `uv tool` → `~/.local/bin/wyoming-faster-whisper`, data `~/wyoming/whisper-data` |
| Installed wyoming-piper 2.2.2 (voice `de_DE-thorsten-medium`) — **fallback TTS only** | `~/.local/bin/wyoming-piper`, data `~/wyoming/piper-data` |
| launchd services (RunAtLoad+KeepAlive), logs in `~/Library/Logs/wyoming-*.log` | `~/Library/LaunchAgents/com.mathiasuhl.wyoming-whisper.plist`, `…wyoming-piper.plist` |
| Ports listening | :10300 (whisper), :10200 (piper) |
| OLLAMA_KEEP_ALIVE | **no change** — Guardian already pins `-1` (infinite; stronger than planned 24h) |

### 2. GitOps (this repo)
| Commit | Change |
|---|---|
| `181d6a73` | `kubernetes/apps/ai/openclaw/app/helmrelease.yaml`: config-guard now enables `gateway.http.endpoints.chatCompletions` (security comment: operator-level endpoint, token-auth, never via ingress). Sed block substitutes `__HA_MCP_URL__` → `$HASS_URL/mcp_server/sse` and `__HA_MCP_AUTH_HEADER__` → `Bearer $HASS_TOKEN` (existing secret keys HA_URL/HA_TOKEN — no secret changes). `mcporter-config.yaml`: new `homeassistant` SSE MCP server. `docs/sops/ai-integration.md`: sections for the above. |
| `e0c375e9` | `helmrelease.yaml`: added provider `ollama-native` (api `ollama`, base without `/v1`) as twin of the existing `ollama` provider. Reason: Ollama's OpenAI-compat `/v1` rejects OpenClaw's tool-call replay (`function.arguments` object vs required string) → first gate test failed with 400. Native API accepts structured args + honours think=false. Voice agent to use `ollama-native/gemma4:e2b-mlx`. |

### 3. OpenClaw runtime (ai namespace pod, persisted in PVC — not in git by design)
| What | Where |
|---|---|
| Agent `voice` created (`openclaw agents add voice --model ollama/gemma4:e2b-mlx --workspace /home/node/clawd-voice`) — model repoint to `ollama-native/...` pending | agent dir `/home/node/.openclaw/agents/voice/agent` |
| Persona seeded (ONE-sentence answers, DE/EN mirror, use HA tools, no reasoning narration) | `/home/node/clawd-voice/SOUL.md` |

### 4. Home Assistant runtime (UI-managed config, not in git)
| What | Detail |
|---|---|
| Wyoming config entry "faster-whisper" | host 192.168.30.111 port 10300 → STT engine |
| MCP Server integration (core) | LLM API "Assist"; `/mcp_server/sse` verified 401-unauth / 200-token |
| `openai_tts` HACS component **v3.8** manually installed (sfortis/openai_tts) | `/config/custom_components/openai_tts/` (survives pod restart via config PVC; HA was restarted to load it) |
| openai_tts parent entry "Qwen3 TTS (Mac Mini)" | url `http://192.168.30.111:8000/v1/audio/speech`, dummy key |
| openai_tts subentry "Qwen3 Voice" | model `mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-8bit`, voice `default`, wav → entity `tts.openai_tts_qwen3_voice`; synthesis verified (German sentence, valid WAV) |
| Assist exposure curated (was 1 entity) | 27 entities: main lights (kitchen/big/sink/tub/living/dining), 12 covers incl. `cover.tub_room_blinds_calibrated` (NOT the raw one), `climate.tub_room`, kids temp/CO2, Grünbeck daily usage + capacity, yard valve + daily volume, 2 soil moistures |

### 5. Validation so far
- `gemma4:e2b-mlx`: tools-capable **verified** (clean structured call), ~144 tok/s warm, TTFT 0.19 s. ⚠ defaults to *thinking* — must be disabled on the voice path (native API supports think=false).
- Gate test #1 via `/v1` (`model=openclaw/voice`, German blinds question): agent attempted the HA tool call correctly but Ollama `/v1` rejected the replay → fix = commit `e0c375e9` (pod roll in progress at time of writing).
- Qwen3-TTS through HA: ~1 s fetch, valid 24 kHz WAV.

## Open items (at time of writing)
1. Repoint agent `voice` → `ollama-native/gemma4:e2b-mlx`; re-run gate test (blinds query must answer via MCP tools; verify no thinking-token stall).
2. Restrict voice agent tool profile (deny fs/exec/browser groups) — hardening after E2E works.
3. Create HA pipeline "Local + OpenClaw" (whisper STT, custom_conversation→OpenClaw conv, Qwen TTS, prefer_local_intents=true, lang de) + set Voice PE satellite assistant + wake word `okay_nabu`.
4. custom_conversation entry: base_url `http://openclaw.ai.svc.cluster.local:18789/v1`, bearer = `OPENCLAW_GATEWAY_TOKEN` (in openclaw-secret), model `openclaw/voice`.
5. Latency benchmarks (local <2 s, fallback <10 s), prefer_local_intents regression check, STT-unavailable watchdog automation.

## Rollback
- HA voice: satellite `select.home_assistant_voice_09c778_assistant` → "Home Assistant Cloud" (one select).
- GitOps: `git revert e0c375e9 181d6a73 && git push`.
- Mac mini: `launchctl bootout gui/$UID ~/Library/LaunchAgents/com.mathiasuhl.wyoming-{whisper,piper}.plist`; remove plists + `~/wyoming/`.
- OpenClaw: `openclaw agents delete voice`; HA: remove openai_tts/wyoming/mcp_server entries, re-hide exposed entities.
