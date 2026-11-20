# SOP: AI Integration

> Standard Operating Procedures for AI/ML service integration and management.
> Reference: `docs/integration.md` for endpoint reference table.
> Description: Operating and integrating Ollama-based AI endpoints for cluster applications.
> Version: `2026.11.08`
> Last Updated: `2026-11-08`
> Owner: `Platform`

---

## Description

This SOP defines how AI integrations use the Mac Mini Ollama endpoints, how to configure consuming
applications, and how to verify end-to-end connectivity and model behavior.

---

## Overview

AI inference runs on Mac Mini M4 Pro (`192.168.30.111`) with a single Ollama instance on
port 11434, using Metal Performance Shaders (MPS) for GPU acceleration.

Ports 11435 and 11436 are no longer in use — all traffic goes to 11434.

In-cluster AI services (Open WebUI, AnythingLLM, OpenClaw, etc.) connect to this external endpoint.

hermes-agent and LibreChat (both `ai`) were decommissioned on 2026-10-04 and are no longer Ollama consumers.

---

## Blueprints

N/A for dedicated Authentik-style blueprints.

Declarative source-of-truth for AI integrations is maintained in application manifests under:
- `kubernetes/apps/ai/`
- `kubernetes/apps/office/` (Paperless-ngx native AI / AFFiNE / Nextcloud)
- `kubernetes/apps/home-automation/` (Frigate AI settings, Home Assistant, n8n)

---

## Operational Instructions

1. All apps use the single endpoint: `http://192.168.30.111:11434`
2. Use `gemma4:26b-mlx` for all LLM tasks (chat, reasoning, vision, voice).
3. Use `nomic-embed-text:latest` for embeddings.
4. Update the target app manifest/secret in Git with endpoint + model configuration.
5. Commit and push changes to trigger Flux reconciliation.
6. Validate app logs and endpoint connectivity.

---

## Examples

### Example 1: Native Ollama API Configuration

```yaml
env:
  - name: OLLAMA_HOST
    value: "http://192.168.30.111:11434"
  - name: OLLAMA_MODEL
    value: "gemma4:26b-mlx"
```

### Example 2: OpenAI-Compatible Configuration

```yaml
env:
  - name: OPENAI_BASE_URL
    value: "http://192.168.30.111:11434/v1"
  - name: OPENAI_MODEL
    value: "gemma4:26b-mlx"
```

---

## Ollama Endpoint

| Endpoint | Port | Purpose |
|---------|------|---------|
| `http://192.168.30.111:11434` | 11434 | All AI inference |

### Models

| Model | Purpose |
|-------|---------|
| `gemma4:26b-mlx` | All LLM tasks — chat, reasoning, vision, voice. Multimodal (text + image). |
| `nomic-embed-text:latest` | Text embeddings |

**Important:** The model name in API calls must be exactly `gemma4:26b-mlx` (not `gemma4` or `gemma4:26b-mlx-instruct`).

---

## Native API Format (Preferred)

- Base URL: `http://192.168.30.111:11434/api` (no trailing slash, no `/v1`)
- Endpoints: `/api/chat`, `/api/generate`
- API key: not required for native Ollama API
- Model name: `gemma4:26b-mlx` (exact)
- Embedding model: `nomic-embed-text:latest`

Use OpenAI-compatible `/v1` endpoints only for apps that require OpenAI API format.

---

## Testing Endpoints

```bash
# Test LLM (text)
curl -X POST http://192.168.30.111:11434/api/chat \
  -H "Content-Type: application/json" \
  -d '{"model": "gemma4:26b-mlx", "messages": [{"role": "user", "content": "Hello"}], "stream": false}'

# Test embeddings
curl -X POST http://192.168.30.111:11434/api/embed \
  -H "Content-Type: application/json" \
  -d '{"model": "nomic-embed-text:latest", "input": "Hello world"}'

# List available models
curl http://192.168.30.111:11434/api/tags
```

**Expected response:** JSON with `model`, `message.content`, and timing fields.

---

## Model Management

### Pulling a New Model

SSH into Mac Mini and use Ollama CLI, or use the Ollama API:

```bash
# Pull model via API
curl http://192.168.30.111:11434/api/pull \
  -H "Content-Type: application/json" \
  -d '{"name": "gemma4:26b-mlx", "stream": false}'

# Check pull status
curl http://192.168.30.111:11434/api/tags
```

### Checking Model Status

```bash
# List models on the instance
curl -s http://192.168.30.111:11434/api/tags | python3 -c \
  "import sys, json; models = json.load(sys.stdin)['models']; [print(m['name'], m['size']) for m in models]"
```

### Deleting a Model

```bash
curl -X DELETE http://192.168.30.111:11434/api/delete \
  -H "Content-Type: application/json" \
  -d '{"name": "old-model:tag"}'
```

---

## In-Cluster AI Services

### Open WebUI (`ai/open-webui`)

Chat interface for AI models.

```bash
# Check Open WebUI is running
kubectl get pods -n ai -l app.kubernetes.io/name=open-webui

# View logs
kubectl logs -n ai -l app.kubernetes.io/name=open-webui --tail=50

# Access
# https://openwebui.${SECRET_DOMAIN}
```

**Configuration:** `kubernetes/apps/ai/open-webui/app/helmrelease.yaml`
**Endpoint:** `http://192.168.30.111:11434`

### OpenClaw (`ai/openclaw`)

AI agent platform.

```bash
kubectl get pods -n ai -l app.kubernetes.io/name=openclaw
# Access: https://openclaw.${SECRET_DOMAIN}
```

#### Model failover chain (added 2026-08-18)

Until 2026-11-08 the primary model ran through the **Codex harness on ChatGPT OAuth**, which has
two independent ways to fail (that path is now the FIRST fallback rung, and Anthropic API errors, rate limits or exhausted credit fail over to it) — both of which took *every* turn down (chat,
skills, cron dispatch) while `agents.defaults.model` carried a bare `primary`
and no fallbacks. It now degrades to the local Ollama models instead:

```jsonc
// ~/.openclaw/openclaw.json  (set declaratively by the init script in helmrelease.yaml)
"agents": { "defaults": { "model": {
  "primary":   "anthropic/claude-sonnet-5-5",       // Anthropic API key (ANTHROPIC_API_KEY env), embedded runtime; since 2026-11-08 (operator decision), openai/gpt-6.1-terra before
  "fallbacks": ["openai/gpt-6.1-terra",              // Codex harness / ChatGPT OAuth, no per-token cost
                "ollama/gemma4:26b-mlx"]                // quality tier (e2b-mlx retired 2026-10-19)
}}}
```

Schema facts (verified against the installed 2026.6.11 bundle, not guessed):

- The validator is `AgentModelSchema = union([string(), object({primary, fallbacks:
  array(string())}).strict()])` in `dist/zod-schema.agent-runtime-*.js`. The key is
  **`fallbacks` — plural, an ordered array**. Because the object is `.strict()`, a
  singular `fallback` key is **rejected** and the gateway fails config validation.
- Consumed by `resolveAgentModelFallbackValues()` (`dist/model-input-*.js`), read
  from `agents.defaults.model` in `dist/model-fallback-*.js`.
- **The harness is resolved per candidate**, so the chain legitimately switches
  from the codex plugin harness to the embedded OpenClaw runtime for the Ollama
  rungs. This is the whole point — a codex-side outage does not strand the agent.
- **Crons inherit the chain even though they pin a model.** A cron payload model
  sets `modelOverrideSource="auto"`, which is explicitly *not* the `return []`
  branch in `resolveEffectiveModelFallbacks` (`dist/agent-scope-*.js`); it falls
  through to `defaultFallbacks`. So the morning briefing and the sweep cron are
  covered.
- Changing `fallbacks` is **hot-reloaded** — no pod roll needed. Watch for
  `[reload] config hot reload applied (agents.defaults.model.fallbacks)`.
- Only models that are BOTH in `models.providers.ollama.models[]` AND pulled on
  the Mac mini are valid rungs. `gemma4:e2b` / `gemma4:e2b-mlx` are retired
  (operator removed all e2b use 2026-10-19); a dead rung only burns a retry.

The init script sets `model.primary` unconditionally from `OPENCLAW_DEFAULT_MODEL`
on every boot but never touched `fallbacks`, so the chain is now written there too
— a PVC rebuild cannot silently lose it.

##### Which codex failure mode am I in?

Both present as "the agent answers nothing", so check auth **before** blaming the
quota — the ChatGPT *app* quota is separate from the Codex CLI quota:

```bash
OC=$(kubectl -n ai get pod -l app.kubernetes.io/instance=openclaw -o jsonpath='{.items[0].metadata.name}')
kubectl -n ai exec "$OC" -c app -- codex login status
```

| Signal | Mode 1 — OAuth refresh drift | Mode 2 — subscription quota |
|---|---|---|
| `codex login status` | NOT logged in / errors | `Logged in using ChatGPT` |
| Dispatch error | `No API key for provider openai` | `You've reached your Codex subscription usage limit. Next reset in N days` |
| Classified reason | `auth` / `auth_permanent` | `rate_limit` |
| Fix | operator must re-login in a browser: `kubectl exec -it -n ai deploy/openclaw -c app -- codex login --device-auth` | none — wait for the reset |
| Self-heals? | No | **Yes** |

`rate_limit` is a cooldown-probeable reason (`shouldAllowCooldownProbeForReason`
in `dist/model-fallback-*.js`), so the primary is periodically re-probed and
traffic returns to codex automatically once quota resets. **No manual revert is
required after a quota window** — the chain is permanent config, not a temporary
model switch.

Confirm a failover actually happened (rather than a silent total failure):

```bash
kubectl -n ai logs "$OC" -c app --tail=400 | grep "model-fallback/decision"
# healthy degrade looks like:
#   decision=candidate_failed  requested=openai/gpt-6.1-terra reason=rate_limit next=ollama/gemma4:26b-mlx
#   decision=candidate_succeeded requested=openai/gpt-6.1-terra candidate=ollama/gemma4:26b-mlx
# "next=none" means NO fallbacks are configured — the chain is missing.
```

**Voice / TTS:** `say.py` uses the local **Qwen3-TTS** (mlx-audio,
OpenAI-compatible) on the mini (`192.168.30.111`, port 8000) as the **only**
provider. ElevenLabs was removed on 2026-08-18 (operator decision): it was
metered, effectively unused (318 of 59k chars), and its budget guard silently
refused a 4366-char morning briefing so no voice note was sent at all. The base
URL comes from the `OPENCLAW_TTS_FALLBACK_URL` key (name is legacy, from when
Qwen3 was the fallback) in the `openclaw-secret` SOPS secret. Qwen3 returns WAV,
converted to OGG/Opus via ffmpeg — the `sendVoice` flow is unchanged.

Because Qwen3-TTS is a VoiceDesign model, `say` pins `voice` + `seed` on every
request: without them each chunk of a multi-chunk briefing generated a
different random voice, and unlucky generations padded dead air (97s of audio
for 874 chars). A dead-air guard re-synthesises any chunk whose speech rate
falls below 70% of the batch median. With no cloud fallback left, the
`openclaw-probe` CronJob treats an unreachable local server as **critical**.

**HA Assist fallback (conversation agent):** The gateway's OpenAI-compatible
`/v1/chat/completions` endpoint is enabled (config-guard block in
`kubernetes/apps/ai/openclaw/app/helmrelease.yaml`). Home Assistant Assist
(`custom_conversation`) POSTs to it as its fallback conversation agent; the
OpenAI `model` field selects an OpenClaw AGENT (`openclaw` = default,
`openclaw/<agentId>`), not a provider model.

- **Security:** this endpoint grants full operator access to the gateway.
  Bearer auth = the gateway token; it is reachable in-cluster/LAN only and
  must **never** be exposed publicly. Concretely, post-`ad1ea7c2`: give it no
  HTTPRoute parented to `envoy-external`. "No Ingress" is no longer a
  meaningful guard — zero Ingress objects and no controller exist, so the
  Gateway parent is the only thing that decides internal vs. internet.
- **HA voice agents (2026-11-18):** Assist uses `openclaw/voice-mathias`,
  `openclaw/voice-andrea` and `openclaw/household`. The two `voice-*` agents
  are HTTP-only twins of `main` / `juno-andrea`: **same workspace** (AGENTS.md
  VOICE MODE, MEMORY.md, memory/, skills shared), own agentDir/sessions,
  **no bindings**. All three run `anthropic/claude-haiku-5-5` with per-agent
  `thinkingDefault: "off"` (fallbacks Sonnet 5.5, then local gemma), set by the
  config-guard `famManaged` block. Telegram/Discord stay on `main` /
  `juno-andrea` (Sonnet 5.5, global thinking `low`); the shared
  `agents.defaults.models['anthropic/claude-haiku-5-5']` entry is deliberately
  untouched so Telegram's Haiku fallback rung keeps thinking on.
  Why not a per-request override: the gateway only takes a backend model via
  the `x-openclaw-model` header (the `model` body field selects an agent), and
  HA `custom_conversation` 1.7.0 cannot send custom headers;
  `channels.modelByChannel` never matches the HTTP path (`webchat` is not a
  deliverable channel).
  **Live token streaming (2026-11-18):** the voice agents' primary is
  `anthropic-voice/claude-haiku-5-5`, a provider alias on the same
  `api.anthropic.com` + `ANTHROPIC_API_KEY` env. Upstream `@openclaw/ai`
  buffers every Claude 5-family reply until `message_stop` (refusal
  contract). The init script's idempotent `VOICE-STREAM PATCH` (v4 since 2026-11-20, marker
  `oc-voice-stream-v4`) replaces that buffer ONLY for provider
  `anthropic-voice` + `claude-haiku-5-5` with a per-message "narration gate":
  text in a model message is held until the message either starts a tool
  call (held text is dropped and blanked in the stored message, so Haiku's
  pre-tool narration is never spoken or kept) or ends (released in one
  burst). Both transport files; boot log (init container
  `install-openclaw`): `voice-stream patch: N file(s) patched`, or a WARN and
  an unpatched boot if upstream changed. Every `anthropic/*` ref, incl.
  Telegram's Sonnet primary and Haiku fallback rung, keeps the upstream
  buffer. Accepted tradeoffs for voice: no spoken filler, each answer
  message arrives in one burst at its end, the alias gets no implicit
  Anthropic beta headers and no server-side tool clearing. VOICE MODE v5.2
  lives in the PVC AGENTS.md files (PVC-owned; the `workspace-agents*.md`
  configmap keys are first-boot copies of the same block).
  **Narration scrub (gate v3, marker `oc-voice-stream-v3`, 2026-11-18):** the
  gate only drops PRE-TOOL text; a final message can still open with meta
  narration (household: "The NPR stream is playing ..., and the user asked
  for "another one", which I read as another joke. I'll give a joke instead
  ...\n\nHere's another one: ..."). On flush (no tool call) v3 drops LEADING
  sentences that talk about "the user"/"der Nutzer", "voice mode", "I read
  that as", "I'll answer in ..." plus an "I'll ..." plan sentence right after
  one; at least one sentence is always kept and mid-answer text is never
  touched. `output.content` and the held `text_delta`/`text_end` are
  rewritten together. Same model scope as v2 (all three HA voice agents,
  never Telegram). VOICE MODE v5.5 adds the matching prompt rules (no
  third-person narration; device/media state only if read this turn, and a
  media player is "playing" only when its state is `playing`; no sensor
  timestamps unless asked). Household also gets "chat follow-ups need no
  tools".
  **Narration scrub v4 (marker `oc-voice-stream-v4`, 2026-11-20):** v3
  stopped at the first unrecognised sentence, so voice-andrea's "English,
  since the question is in English. This is a voice-mode turn (Home
  Assistant), so I answer directly in plain spoken sentences. ..." was
  spoken in full. v4 (same gate, same streaming, only the scrub function
  changed): (a) STRONG self-talk about language choice, voice mode, tools or
  instructions ("question is in English", "Deutsch, weil ...", "voice-mode",
  "plain spoken", "I answer directly", "per my instructions", "tool call",
  "I don't have a timer tool", ...) is dropped WHEREVER it appears; (b)
  third-person narration ("the user ...", "I read that as") in the first 3
  sentences cuts everything before it; (c) the v3 leading meta/plan run is
  dropped after that; (d) if nothing else is left, "Sorry, I didn't catch
  that." / "Das habe ich nicht verstanden." is spoken instead (never empty:
  empty output triggers failover). Answers without meta pass byte-identical.
  Offline suite (27 cases: 13 leak/meta incl. the kitchen leak, 14 legit
  incl. "user manual", "English muffins", "In English it is called ...",
  recipe "instructions on the box", the TIMERS reply) passes 27/27; v3 passed
  15/27 (all legit + the v3 household case). The init revert regex now
  rewinds a surviving v2 OR v3 line (multi-line) before applying v4.
  **Grill (2026-11-18):** `ha grill` (ha.py) returns one interpreted summary:
  Otto Wilde G32 -> BLE -> ESPHome ESP32 display bridge (`g32_display_bt_*`)
  -> Wi-Fi -> HA; `yard_otto_wilde_bbq_*` is only the Shelly plug; gas left =
  NET (`sensor.gas_bottle_gas_remaining` / `_fill`), the GasBuddy value on the
  grill is GROSS (minus `input_number.gas_bottle_tare`); probe 1500 =
  unplugged. `ha find grill|bbq|esp32|gas...` matches the G32/gas entities and
  hints at `ha grill`. Juno's AGENTS.md routing bullet carries the same map.
  **Startup-retry patch (2026-11-18):** at gateway start the first agent to
  publish its model runtime while a plugin/config publication lands can fail
  with "prepared model runtime publication was superseded" / "owner is stale
  after config publication"; upstream retries only its own
  `AgentDatabaseStartupSupersededError`, so that agent stayed "agent database
  remains degraded" (household -> every HA household request HTTP 500). The
  init script's `STARTUP-RETRY PATCH` (marker `oc-startup-retry`) retries
  those two messages too (1/2/3 s back-off). Boot log (init container
  `install-openclaw`): `startup-retry patch: 1 file(s) patched`.
  Rollback: delete the block (one pod roll).
  **voice-handoff v2 (2026-11-18):** VOICE MODE v5.4.2 (first bullet) tells
  `voice-mathias` / `voice-andrea` to hand long requests (mail, bookings,
  travel, calendar changes, more than about two lookups) off instead of
  doing them: `voice-handoff start` records a one-time id (3 h) and prints
  the person's Telegram DM session key (`agent:main|juno-andrea:telegram:
  direct:<id>`) plus a ready-made message; the twin sends it with its
  `sessions_send` tool (`timeoutSeconds: 0`) and answers at once "...and get
  back to you on Telegram". The full agent does the task in that Telegram
  conversation, delivers the result with its `message` tool, then runs
  `voice-handoff report --id <id>`, which POSTs `{"person","message"}` to
  `$HASS_URL/api/webhook/$HA_VOICE_WEBHOOK_ID` (key in `openclaw-secret`,
  SOPS) only for a valid unused id, so normal Telegram chats can never
  trigger a spoken report. Home Assistant decides whether to speak (person
  home and alone in the room, 07:00-22:30). The twins may `sessions_send`
  only to their person's agent (`tools.agentToAgent.send`). Household never
  hands off. Why not `openclaw agent` from the script: OpenClaw refuses
  gateway `agent`/send RPCs from an agent's exec (`OPENCLAW_SHELL=exec`,
  "would lose inter-session attribution"); never strip that marker.
  State: `~/clawd/state/voice-handoff/<id>.json`; `voice-handoff status`. HA's custom_conversation `max_tokens` must be well above 300: it is a
  per-model-call cap, and 300 truncates tool calls ("Provider completed
  stream with an incomplete tool call").
  **familyha (2026-11-18):** household controls the house through a fourth
  family-mcp server, `familyha` (tools `familyha__list_entities`, `get_state`,
  `control`, `list_items`, `camera_snapshot`, `calendar_events`, `weather`). It REUSES
  OpenClaw's existing HA token (`HASS_TOKEN`, an owner/admin user; captured
  inside family-mcp before its env scrub, never returned), so all protection
  is enforced in code (`FamilyHA` in family-mcp.py): an HTTP method+path
  allow-list, a (domain, service) allow-list with per-field validators, and
  entity lists. Allowed: lights, blinds (device_class blind/shade/shutter/
  curtain; open/close/stop only, so HA's window-safety automations apply),
  media players + Music Assistant play_media, the two shared shopping lists,
  timers, 7 room thermostats (5-28 C), scenes, household calendars (read),
  cameras (read + snapshot to the agent only + show on a display via the
  three `esphome.*_home_show_camera` actions), and automation trigger/turn_on/
  turn_off except a pattern deny list (safety, water/valve/leak/irrigation,
  vacation/away/alarm/alert, heater/pellet/dust fan, watchdogs/guards, voice,
  ...; trigger always keeps the automation's conditions). Denied: locks,
  alarm, garage/gate/door covers, camera control, valves, sirens, switches,
  scripts, homeassistant/config/restart and everything not listed; the kids'
  room cameras are hidden. Household has no messaging tool, so snapshots
  cannot leave the conversation.
  **Post-restart check (always):** `openclaw/household` answers HTTP 200, the
  gateway log `/tmp/openclaw/openclaw-<date>.log` has no "agent database
  remains degraded" and no `AgentDatabaseAdmissionError`, and both
  `oc-voice-stream-v4` and `oc-startup-retry` markers are present.
  Rollback: remove the patch block and set `famVoiceModel.primary` back to
  `anthropic/claude-haiku-5-5` (one pod roll; npm reinstall restores the
  pristine files).
  **Voice latency v5.6 (2026-11-20):** VOICE MODE gains (1) HOUSE COMMANDS:
  Juno twins act with ONE `ha call` (exact forms in the bullet and in the
  home-assistant skill's "Voice" section, no `--json`) and NEVER verify with
  `ha state` / `sleep`; household acts with one `familyha__control` and never
  re-reads; (2) FRAGMENTS: a 1-2 word input with no request gets only "Hm?" /
  "Ja?" (an empty reply was not used: OpenClaw treats empty assistant output
  as a failover case); (3) household LOOKUPS name the exact `dispatch_action`
  ids + args (`familycal__list_events`, `meals__get_meal_plan`,
  `familyha__weather`, `familyha__list_entities`, `familyha__control`) so it
  skips tool_search/tool_describe. Tool Search itself can only be switched
  globally (`tools.toolSearch`, no per-agent key in 2026.11.1), so it stays on.
  `familyha__weather` is new: read-only `weather.forecast_home` state + the
  `weather.get_forecasts` (daily) response. The AGENTS.md files are PVC-owned,
  so the same edits were also applied in-pod (`.bak-pre-v56-latency-*`), and
  main's AGENTS.md lost a stale duplicate of the doctor's TOOLS.md migration
  (it was 42.3K > `bootstrapMaxChars` 40K, i.e. truncated). Cause of the
  duplicate: init re-seeds TOOLS.md every boot and `doctor --fix` inserts a
  new copy whenever workspace-tools.md changed; recheck after edits to it.
  **TIMERS v5.7 (2026-11-20):** kitchen "Set timer 15 minutes." / "Set second
  timer for 2 minutes." missed HA's strict local timer grammar (no "for"),
  fell through to voice-andrea, which had no timer tool, created one-shot
  `automations` (cron) jobs instead and said "Your 15-minute timer is set".
  The jobs fired, but a scheduled `announce` to an HTTP voice session has no
  channel (`delivery.channel=last` unresolved, `cron runs` still says
  "delivered"), so nothing was ever heard. Fixes: HA custom sentences now
  match those phrasings locally (ha-agent lane), and VOICE MODE v5.7 (all
  three voice AGENTS.md, PVC + `workspace-agents*.md` first-boot keys,
  `.bak-pre-v57-20261120` in-pod) adds a TIMERS bullet + reminder line: no
  device-timer tool, never say a timer is set, never schedule a job/cron/
  reminder as a substitute, answer only with the phrase to say ("Say: set a
  timer for fifteen minutes." / "Sag: Timer fünfzehn Minuten."). Household
  may still start/read existing HA `timer.*` helpers by name via familyha.
  main/voice-mathias AGENTS.md is now ~37.1K of the 40K `bootstrapMaxChars`.
  A real device timer from OpenClaw would need the satellite's device_id
  (custom_conversation `llm_hass_api` client tools; HA lane, not done).
  **LATENCY-DEBUG (TIME-BOXED, enabled 2026-11-20, REVERT on/after
  2026-11-21):** to explain the ~2.9 s prep gap (tool-catalog -> first model
  request), the ~3.4 s pre-session gap and plugin-reload stalls, the app
  container sets `OPENCLAW_DIAGNOSTICS=reply.profiler,ingress.timing,
  plugin.load-profile,timeline`, `OPENCLAW_DIAGNOSTICS_TIMELINE_PATH=
  /home/node/.openclaw/diag/latency-timeline.jsonl` and
  `OPENCLAW_DIAGNOSTICS_EVENT_LOOP=1`, and the init container lowers the
  embedded-run prep-stage WARN thresholds (10 s/5 s -> 1 s/0.5 s), so slow
  runs log `[trace:embedded-run] prep stages: ... stages=...` as WARN. All
  timing-only (stage names, ms, session UUIDs, plugin ids; no prompts or
  secrets). Revert: delete every block tagged `LATENCY-DEBUG` in
  helmrelease.yaml (3 env vars, the init sed block, the diag mkdir), push,
  then `rm -rf /home/node/.openclaw/diag` in-pod.
  **Heartbeats are explicitly enrolled per agent** because of these twins:
  every agent gets `heartbeat: {}` (= defaults, 1h) and the twins get
  `every: "0m"`. Otherwise a twin would run main's stateful `HEARTBEAT.md`
  (hb-record watermark) a second time every hour. Since any per-agent block
  switches OpenClaw to explicit-only enrollment, an agent added at runtime
  only gets a heartbeat after the next boot.
- **Voice agent (legacy):** a dedicated `voice` agent runs on
  `ollama-native/gemma4:26b-mlx` (moved off e2b-mlx 2026-10-19). It is runtime-managed
  (`openclaw agents add voice …`) and persists in the PVC — the config-guard
  intentionally does not manage it.
- **HA MCP:** the `homeassistant` MCP server entry
  (`kubernetes/apps/ai/openclaw/app/mcporter-config.yaml`) connects the voice
  agent to HA's core "MCP Server" integration over SSE, so Assist follow-up
  turns can read/control entities. URL/auth are substituted at container
  startup from `HASS_URL`/`HASS_TOKEN` (mapped from `openclaw-secret`).

**HA voice STT/TTS (Mac Mini):** In addition to Ollama, the Mac Mini
(`192.168.30.111`) runs two host-managed (launchd) Wyoming services for the
HA voice pipeline:

| Service | Port | Purpose |
|---------|------|---------|
| `wyoming-faster-whisper` | `10300` | Speech-to-text for HA Assist |
| `wyoming-piper` | `10200` | Text-to-speech for HA Assist |

These are host-managed on the mini (not in-cluster); HA connects to them via
the Wyoming integration.

### MCPO (`ai/mcpo`)

Model Control Plane Orchestrator.

```bash
kubectl get pods -n ai -l app.kubernetes.io/name=mcpo
```

### AI-SRE (`ai/ai-sre`)

MCP-based SRE tooling for cluster operations. Does not perform LLM inference directly.

```bash
kubectl get pods -n ai -l app.kubernetes.io/name=ai-sre
```

### Paperclip (`ai/paperclip`)

AI agent orchestration platform. Uses OpenAI cloud API (key in SOPS secret).

```bash
kubectl get pods -n ai -l app.kubernetes.io/name=paperclip
```

**Configuration:** `kubernetes/apps/ai/paperclip/app/secret.sops.yaml` (OPENAI_API_KEY)

---

## App-Specific AI Configurations

### Home Assistant (`home-automation/home-assistant`)

Home Assistant uses Ollama plus cloud AI APIs.
Configuration is managed through the HA UI (stored in `.storage/core.config_entries`),
not in git-managed manifests. **Requires manual update.**

| Integration | Endpoint | Model | Use Case |
|------------|----------|-------|----------|
| Ollama (all tasks) | `http://192.168.30.111:11434` | `gemma4:26b-mlx` | Voice, AI tasks, vision |
| OpenAI (ChatGPT) | Cloud | `gpt-4o-mini-tts` (TTS) | Conversation, AI Task, TTS, STT |
| Google Generative AI | Cloud | (default) | Conversation, TTS, AI Task, STT |
| Google Translate | Cloud | - | TTS |

### AnythingLLM (`ai/anythingllm`)

RAG chat and document embedding.

| Setting | Value |
|---------|-------|
| Endpoint | `http://192.168.30.111:11434` |
| LLM Model | `gemma4:26b-mlx` |
| Embedding Model | `nomic-embed-text:latest` |
| Config | `OLLAMA_BASE_PATH`, `EMBEDDING_BASE_PATH` |

**Configuration:** `kubernetes/apps/ai/anythingllm/app/helmrelease.yaml` (env vars at ~line 81)

### Next AI Draw.io (`ai/next-ai-draw-io`)

AI-powered diagram generation.

| Setting | Value |
|---------|-------|
| Endpoint | `http://192.168.30.111:11434/api` |
| Model | `gemma4:26b-mlx` |
| Config | `AI_PROVIDER: "ollama"`, `OLLAMA_BASE_URL` (native `/api`) |

**Configuration:** `kubernetes/apps/ai/next-ai-draw-io/app/helmrelease.yaml` (env vars at ~line 36)

### AFFiNE (`office/affine`)

Collaborative workspace with AI copilot features.

| Setting | Value |
|---------|-------|
| Endpoint | `http://192.168.30.111:11434/v1` |
| LLM Model | `gemma4:26b-mlx` (coding, text gen, summarize, decisions) |
| Embedding Model | `nomic-embed-text:latest` |
| Config | OpenAI-compatible provider in copilot configmap |

**Configuration:** `kubernetes/apps/office/affine/app/configmap.yaml` (copilot section at ~line 52)

### Nextcloud (`office/nextcloud`)

Nextcloud uses the `integration_openai` app plus `context_chat` for RAG with embeddings.
All configured through the Nextcloud admin UI. **Requires manual update.**

| Integration | Model | Use Case |
|------------|-------|----------|
| integration_openai | `gemma4:26b-mlx` | Text gen, chat, summary, translate, proofread, headlines, topics |
| context_chat | `nomic-embed-text:latest` | RAG embeddings for file-based context chat |

**Configuration:** NC admin UI > `integration_openai` app settings
- Endpoint: `http://192.168.30.111:11434/v1`
- Default model: `gemma4:26b-mlx`
- NC apps: `assistant` (3.3.0), `context_chat` (5.3.1), `integration_openai` (4.3.0)

```bash
# Check Nextcloud AI config
kubectl exec -n office deploy/nextcloud -- php occ config:list --private 2>/dev/null | python3 -c "
import sys, json; data = json.load(sys.stdin)
for k, v in data.get('apps', {}).get('integration_openai', {}).items():
    print(f'{k} = {v}')
"
```

### n8n (`home-automation/n8n`)

n8n has AI provider credentials configured via its workflow UI (stored in SQLite DB on PVC).
**Requires manual update.**

| Credential | Provider | Model |
|------------|----------|-------|
| ollamaApi | Ollama (`http://192.168.30.111:11434`) | `gemma4:26b-mlx` |
| openAiApi | OpenAI Cloud | (default cloud models) |
| anthropicApi | Anthropic Cloud | (available, usage varies by workflow) |

**Configuration:** n8n UI > Credentials (stored in `/home/node/.n8n/database.sqlite`)

```bash
# Check n8n AI credentials (via string extraction)
kubectl exec -n home-automation deploy/n8n -- cat /home/node/.n8n/database.sqlite 2>/dev/null \
  | strings | grep -iE 'ollamaApi|openAiApi|anthropicApi' | head -10
```

### Paperless-ngx native AI (`office/paperless-ngx`)

Document classification (LLM suggestions) + RAG chat, built into paperless-ngx
3.0.5. Retired the standalone `paperless-gpt` (vision-OCR/metadata) and
`paperless-ai` (auto-tag/RAG) sidecars on 2026-08-24 — both were fully
redundant with this native module. **Config is a DB row, not a manifest**
(`paperless.models.ApplicationConfiguration`) — see `docs/sops/paperless.md`
§4a for the read/write recipe (always `gosu paperless`, never a bare exec).

| Setting | Value |
|---------|-------|
| Endpoint (LLM + embeddings) | `http://192.168.30.111:11434` |
| LLM model | `gemma4:26b-mlx` (`llm_backend=ollama`) |
| Embedding model | `nomic-embed-text:latest` (`llm_embedding_backend=ollama`) |
| Config | DB-stored `ApplicationConfiguration` singleton row |

```bash
PPOD=$(kubectl get pod -n office -l app.kubernetes.io/name=paperless-ngx \
  --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n office "$PPOD" -c paperless-ngx -- gosu paperless python3 \
  /usr/src/paperless/src/manage.py shell -c "
from paperless.models import ApplicationConfiguration
ac = ApplicationConfiguration.objects.first()
print(ac.ai_enabled, ac.llm_backend, ac.llm_model, ac.llm_embedding_backend, ac.llm_embedding_model)"
```

paperless-gpt's vision-OCR (automated hard-scan fallback) has no native
replacement — hard-to-OCR scans now go through manual review (operator +
Claude Code reading the page image on demand) instead of an automated
pipeline stage.

### Frigate NVR AI (`home-automation/frigate-nvr`)

AI-powered camera event descriptions.

| Setting | Value |
|---------|-------|
| Endpoint | `http://192.168.30.111:11434/v1` |
| Model | `gemma4:26b-mlx` (in encrypted configmap, **requires manual update**) |
| Config | `OPENAI_BASE_URL` env var |

```bash
kubectl logs -n home-automation -l app.kubernetes.io/name=frigate-nvr --tail=50 | grep -i ai
```

---

## Integrating a New App with Ollama

### Step 1: Choose the Model

| Use Case | Model | Notes |
|---------|-------|-------|
| Text processing, reasoning, chat | `gemma4:26b-mlx` | Multimodal — handles text and images |
| Image/vision analysis | `gemma4:26b-mlx` | No separate vision model needed |
| Voice/audio | `gemma4:26b-mlx` | Same model for all tasks |
| Text embeddings | `nomic-embed-text:latest` | For RAG, search, similarity |

### Step 2: Configure the App

All apps use `http://192.168.30.111:11434`. Prefer native `/api` unless the app
explicitly requires OpenAI-compatible `/v1`.

**Native Ollama API:**
```yaml
env:
  - name: OLLAMA_HOST
    value: "http://192.168.30.111:11434"
  - name: OLLAMA_MODEL
    value: "gemma4:26b-mlx"
```

**OpenAI-compatible API:**
```yaml
env:
  - name: OPENAI_BASE_URL
    value: "http://192.168.30.111:11434/v1"
  - name: OPENAI_API_KEY
    value: "not-required"
  - name: OPENAI_MODEL
    value: "gemma4:26b-mlx"
```

### Step 3: Update Integration Documentation

Update `docs/integration.md` → "Application Configuration" table and `docs/ai-usage-map.md`.

### Step 4: Test

```bash
# Test that the app can reach the Ollama endpoint
kubectl exec -n {namespace} {pod} -- \
  wget -qO- http://192.168.30.111:11434/api/tags 2>&1 | head -20
```

---

## Troubleshooting

### App Cannot Connect to Ollama

```bash
# Test connectivity from a test pod (if app pod lacks wget/curl)
kubectl run test-ai --rm -it --image=alpine -n {namespace} -- \
  wget -qO- http://192.168.30.111:11434/api/tags

# Check Mac Mini is reachable
ping 192.168.30.111

# Verify Ollama is running on Mac Mini (via SSH or local)
# On Mac Mini: launchctl list | grep ollama
```

### Model Not Found Error

```bash
# List available models
curl http://192.168.30.111:11434/api/tags | python3 -c \
  "import sys, json; [print(m['name']) for m in json.load(sys.stdin)['models']]"

# Pull the model if missing
curl -X POST http://192.168.30.111:11434/api/pull \
  -H "Content-Type: application/json" \
  -d '{"name": "gemma4:26b-mlx"}'
```

### Slow Response Times

- Check Mac Mini load: `gemma4:26b-mlx` is 26B params, ensure adequate memory
- Ollama loads models on demand and keeps them warm with `keep_alive`
- Only `gemma4:26b-mlx` and `nomic-embed-text:latest` should be loaded

### Wrong Endpoint Format

Apps expecting OpenAI format need `/v1/` path, not `/api/`:
```
OpenAI format: http://192.168.30.111:11434/v1/chat/completions
Ollama native: http://192.168.30.111:11434/api/chat
```

Model name must be exactly `gemma4:26b-mlx` (not `gemma4` or `gemma4:26b-mlx-instruct`).

---

## Verification Tests

### Test 1: Endpoint Reachability

```bash
curl -sf http://192.168.30.111:11434/api/tags > /dev/null && echo "OK" || echo "FAIL"
```

Expected:
- Prints `OK`.

If failed:
- Check network reachability to `192.168.30.111` and service status on Mac Mini.

### Test 2: Model Invocation

```bash
curl -sS -X POST http://192.168.30.111:11434/api/chat \
  -H "Content-Type: application/json" \
  -d '{"model":"gemma4:26b-mlx","messages":[{"role":"user","content":"ping"}],"stream":false}'
```

Expected:
- JSON response with a non-empty `message.content`.

If failed:
- Verify model exists via `/api/tags` and pull if missing.

---

## Diagnose Examples

### Diagnose Example 1: App Cannot Reach Ollama

```bash
kubectl run test-ai --rm -it --image=alpine -n {namespace} -- \
  wget -qO- http://192.168.30.111:11434/api/tags
```

Expected:
- Returns model JSON from the endpoint.

If unclear:
- Run `ping 192.168.30.111` from a reachable node or diagnostic pod.

### Diagnose Example 2: Model Not Found in App

```bash
curl -s http://192.168.30.111:11434/api/tags | python3 -c \
  "import sys, json; [print(m['name']) for m in json.load(sys.stdin).get('models',[])]"
```

Expected:
- `gemma4:26b-mlx` and `nomic-embed-text:latest` appear in the list.

If unclear:
- Pull the model and retest.

---

## Health Check

```bash
# Check Ollama endpoint is reachable
curl -sf http://192.168.30.111:11434/api/tags > /dev/null \
  && echo "Ollama: OK" || echo "Ollama: UNREACHABLE"

# Verify required models are available
curl -s http://192.168.30.111:11434/api/tags | python3 -c "
import sys, json
models = [m['name'] for m in json.load(sys.stdin)['models']]
for required in ['gemma4:26b-mlx', 'nomic-embed-text:latest']:
    status = 'OK' if required in models else 'MISSING'
    print(f'{required}: {status}')
"

# Check all AI namespace pods are running
kubectl get pods -n ai

```

---

## Security Check

```bash
# Ensure AI-related secret manifests remain encrypted
find kubernetes/apps -path '*/ai/*' -name '*.sops.yaml' -print | head -20

# Check no plaintext secret-like keys were accidentally introduced
rg -n --glob '*.yaml' 'api[_-]?key|token|password|secret' kubernetes/apps/ai kubernetes/apps/office | head -40
```

Expected:
- Sensitive values are in SOPS-managed files and no plaintext credentials are committed.

---

## Rollback Plan

```bash
# Revert AI integration changes to the last known good revision
git log -- docs/sops/ai-integration.md kubernetes/apps/ai kubernetes/apps/office kubernetes/apps/home-automation
# then revert the relevant commit(s)
git revert <commit-sha>
git push
```

Rollback validation:
- Re-run the `Verification Tests` section.

---

## Version History

- `2026.11.08`: OpenClaw primary is `anthropic/claude-sonnet-5-5` (shared `anthropic-api-key`, plugin `anthropic` enabled, key detected from env, no auth profile), fallbacks `openai/gpt-6.1-terra` then `ollama/gemma4:26b-mlx`; terra, luna and gpt-5.5 stay overlaid + allowlisted for manual `--model` use. Agents on the primary: main, juno-andrea, vita-*, jerry-* (8); `voice` stays on `ollama-native`. Heartbeats and dreaming pin the local model. Details and the 2026.11 runtime rows: `docs/sops/openclaw-config.md`.
- `2026.11.07`: OpenClaw primary model now `openai/gpt-6.1-terra` (`1cbf86998`).
  Seeded-config guards (web search, memory embeddings, codex plugin strip) are
  documented in `docs/sops/openclaw-config.md`; recovery of a failed
  OpenClaw-triggered sweep in `docs/sops/operation-sweep-cron.md`.
- `2026.10.26`: OpenClaw failover-chain example: `primary` corrected from
  `openai/gpt-5.6-terra` to the live `openai/gpt-6-luna` (switched 2026-09-26 in
  `4d90cfb1`; re-verified in the pod's `openclaw.json` 2026-10-26), also in the
  `model-fallback/decision` log example. `gpt-5.6-terra` stays overlaid and
  allowlisted as a one-command `--model` fallback. Also records the 2026-10-19
  change that shipped without a version bump (`ee06496d`): `gemma4:e2b-mlx`
  removed from the fallback chain (now `ollama/gemma4:26b-mlx` only) and the
  `voice` agent moved to `ollama-native/gemma4:26b-mlx`.
- `2026.10.04`: earlier versions predate this history section; see `git log`.
