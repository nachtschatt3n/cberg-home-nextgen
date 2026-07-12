# Voice Pipeline — HA Voice PE → local intents → local LLM fallback

Version: 2026.07.12 · Status: **live** · Owner: Mathias + Claude session log

> **OUTCOME NOTE:** the design goal (per Mathias) is voice fallback into the
> **full OpenClaw MAIN agent — skills + ChatGPT (openai/gpt-5.5 via Codex
> harness)** — not a bare local LLM. Finding during build: OpenClaw 2026.6.11's
> `/v1` endpoint drops the agent harness for **ollama-runtime agents** when a
> request carries a `system` message or `user`/session field (raw model then
> echoes; verified with fresh sessions) — but the **codex-runtime main agent
> handles those shapes correctly**, so the intended design works by targeting
> model `openclaw` (main agent) instead of a dedicated small ollama agent.
>
> Two pipelines exist; the Voice PE satellite uses **"Local + OpenClaw"**:
> - **Local + OpenClaw** (satellite default): fallback →
>   `conversation.openclaw` (custom_conversation → gateway `/v1`, model
>   `openclaw`). Local 0.3 s; fallback 20–40 s but with FULL skills (verified:
>   pellet-storage skill answered with live probe data) + memory + ChatGPT.
> - **Local + Voice LLM** (fast alternative, one satellite-select away):
>   fallback → `conversation.voice_gemma_e2b` (native Ollama gemma4:e2b-mlx,
>   think:false, Assist tools). Local 0.26 s / fallback 2.3 s, no skills.
>
> The runtime-managed OpenClaw `voice` (gemma) agent and ha-mcp wiring stay:
> ha-mcp gives every OpenClaw agent house control; the gemma agent is unused
> by voice but available.
>
> **Bilingual (2026-07-12 late):** the Voice PE runs TWO wake words:
> **"Okay Nabu" → "Local + OpenClaw" (German)** and **"Hey Jarvis" →
> "Local + OpenClaw EN" (English)**. Same OpenClaw agent + Qwen3-TTS
> (multilingual) behind both; whisper receives the language per-request from
> the pipeline (service runs WITHOUT --language; --beam-size 1 for speed).
> English local intents match natively (entity/area names are English);
> German matching uses the added aliases.

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

## Final state (2026-07-12 evening)
- Pipeline **"Local + Voice LLM"** (preferred): STT `stt.faster_whisper`,
  conversation `conversation.voice_gemma_e2b` (native Ollama, think:false,
  Assist API), TTS `tts.openai_tts_qwen3_voice`, `prefer_local_intents: true`,
  language de. Voice PE satellite pointed at it, wake word **Okay Nabu**.
- German **aliases** added: 13 areas (Küche, Wohnzimmer, Bad, …) + 8 key
  entities (großes Licht, Rollladen im Wohnzimmer, Gartenbewässerung, …) —
  required for local intent matching, since entity names are English.
- `custom_conversation` entry (→ OpenClaw /v1) exists but is NOT in the
  pipeline (kept for experiments; component-level HA-agent toggle disabled).
- Watchdog automation `voice_stt_watchdog`: notifies if whisper unavailable
  10+ min.
- Automation `voice_openclaw_thinking_ack`: if the satellite stays in
  `processing` >3 s (only the OpenClaw fallback does; local intents finish
  <0.5 s), it speaks a cached "Moment." (0.6 s) on the PE media channel so
  long waits aren't silent. ⚠ Qwen3-TTS quirk: an ellipsis ("Moment...")
  renders as a ~13 s clip — keep ack phrases plain.
- Benchmarks: local 0.26 s / built-in Q&A 0.04 s / LLM fallback 2.27 s
  (targets were <2 s / <10 s).

## Live-test results (2026-07-12) & operational quirks
- Both wake words verified live: "Okay Nabu" (DE) incl. an OpenClaw
  skills answer that consulted the Nextcloud calendar + memory (68 s worst
  case); "Hey Jarvis" (EN) local command in 0.2 s.
- STT model upgraded twice during testing: small-int8 → **large-v3-turbo
  (int8, beam 1, no --language)** after code-switched German (English room
  names) was mangled. Post-upgrade transcriptions clean.
- **Quirk: changing wake_word_2 on the Voice PE needs a device reboot** to
  load the second micro-wake-word model (select-cycling is not enough). The
  hidden `button.home_assistant_voice_09c778_restart` was enabled for this.
- **Quirk: restarting the whisper service while the satellite holds an open
  stream wedges the PE** (LED spins forever). Fix: reload the ESPHome config
  entry (or reboot the PE). Avoid whisper restarts while voice is in use.

## Local patch in custom_conversation (would be lost on HACS update!)
`/config/custom_components/custom_conversation/conversation.py` line ~193:
`json.dumps(content.tool_result)` → `json.dumps(content.tool_result, default=str)`.
Upstream bug (v1.6.1, michelle-avery/custom-conversation): an LLM follow-up
turn in a conversation whose history contains a locally-handled tool result
with non-JSON-serializable objects (e.g. `time` from "What time is it?")
crashes with `TypeError: Object of type time is not JSON serializable` →
pipeline `intent-failed` → "conversation starts but never answers".
Reproduced, patched, and fix-verified 2026-07-12. Re-apply after any
component update until fixed upstream.

## Open items
1. File the serialization bug upstream (michelle-avery/custom-conversation).
2. Optional: restrict OpenClaw `voice` agent tool profile (hardening; only
   relevant if OpenClaw /v1 path is revisited).
3. Optional: upstream issue to OpenClaw about /v1 dropping the agent harness
   on system/user-carrying requests (ollama-runtime agents only).

## Rollback
- HA voice: satellite `select.home_assistant_voice_09c778_assistant` → "Home Assistant Cloud" (one select).
- GitOps: `git revert e0c375e9 181d6a73 && git push`.
- Mac mini: `launchctl bootout gui/$UID ~/Library/LaunchAgents/com.mathiasuhl.wyoming-{whisper,piper}.plist`; remove plists + `~/wyoming/`.
- OpenClaw: `openclaw agents delete voice`; HA: remove openai_tts/wyoming/mcp_server entries, re-hide exposed entities.
