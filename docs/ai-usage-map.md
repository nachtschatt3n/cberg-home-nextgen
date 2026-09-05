# AI Usage Map

> Comprehensive mapping of all AI/LLM integrations across the cluster and Home Assistant.
> Last Updated: 2026-09-04

---

## Mac Mini Ollama Endpoint (192.168.30.111:11434)

Single Ollama instance on Mac Mini M4 Pro with Metal (MPS) acceleration.
Ports 11435 and 11436 are no longer in use.

### Models

| Model | Purpose |
|-------|---------|
| `gemma4:26b-mlx` | All LLM tasks (chat, reasoning, vision, voice). Multimodal (text + image). |
| `nomic-embed-text:latest` | Text embeddings |

### All Consumers

> **Completeness warning (2026-09-04).** This table was found to be MISSING
> three live consumers — `sure`, `hermes-agent` and `ha-ai-harness` — during
> the GGUF→MLX migration. Sure alone was ~85% of the day's load. Do NOT treat
> this list as authoritative: verify with an exhaustive repo grep
> (`gemma4`, `26b`, `192.168.30.111`, `11434`, `OPENAI_MODEL`, `LLM_MODEL`,
> `OLLAMA_MODEL`, `AI_MODEL`, `genai`, `llm_backend`) **plus** the DB/UI-side
> consumers below, which no grep can see.

**Migrated column:** `git` = model name lives in this repo, changed by the
2026-09-04 migration commit. `DB/UI` = configured outside GitOps; **still on
the GGUF `gemma4:26b` unless its own owner has changed it.**

| App | Namespace | Model | API Style | Migrated | Config Location |
|-----|-----------|-------|-----------|----------|-----------------|
| AnythingLLM | ai | `gemma4:26b-mlx` (LLM) | Native Ollama | git ✅ | `kubernetes/apps/ai/anythingllm/app/helmrelease.yaml:83` |
| AnythingLLM | ai | `nomic-embed-text:latest` (embeddings) | Native Ollama | n/a | `kubernetes/apps/ai/anythingllm/app/helmrelease.yaml:87-88` |
| OpenClaw | ai | `gemma4:26b-mlx` | OpenAI `/v1` via `ollama-toolfix` | git ✅ | `kubernetes/apps/ai/openclaw/app/helmrelease.yaml` (env `OLLAMA_MODEL`, fallback rung, model catalog, memory-dreaming) **and** `skills-configmap.sops.yaml` (the model-switch skill) |
| Next AI Draw.io | ai | `gemma4:26b-mlx` | Native Ollama `/api` | git ✅ | `kubernetes/apps/ai/next-ai-draw-io/app/helmrelease.yaml:37-40` |
| LibreChat | ai | `gemma4:26b-mlx` (default, **`fetch: true`**) | OpenAI `/v1` | git ⚠️ | `kubernetes/apps/ai/librechat/app/helmrelease.yaml:162` — default only; `fetch: true` still lists every host model, so a user can pick the GGUF |
| **Sure** | **office** | `gemma4:26b-mlx` | OpenAI `/v1` | git ✅ | **TWO places:** `kubernetes/apps/office/sure/app/helmrelease.yaml` (`OPENAI_MODEL`, plain env — this one wins) **and** `secret.sops.yaml` (`OPENAI_MODEL`). Was absent from this table until 2026-09-04 despite being the largest single consumer. |
| **hermes-agent** | **ai** | `gemma4:26b-mlx` | OpenAI `/v1` | git ⚠️ | `kubernetes/apps/ai/hermes-agent/app/configmap.yaml:11` is a **SEED ONLY** — the live config is `/opt/data/config.yaml` on the `hermes-agent-data` PVC and the init container copies the seed only when that file is absent. Editing the ConfigMap changes NOTHING on a running install. See Known Gotcha #14 in `docs/sops/new-deployment-blueprint.md`. Was absent from this table until 2026-09-04. |
| **ha-ai-harness** | **home-automation** | `gemma4:26b-mlx` (`DENSE_MODEL`) + `gemma4:e2b-mlx` (`EDGE_MODEL`, already MLX) | Native Ollama | git ✅ | `kubernetes/apps/home-automation/ha-ai-harness/app/helmrelease.yaml:38-41`. Was absent from this table until 2026-09-04. |
| AFFiNE | office | `gemma4:26b-mlx` (6 scenarios) | OpenAI `/v1` | git ✅ | `kubernetes/apps/office/affine/app/configmap.yaml:58-65,71` |
| Frigate NVR | home-automation | `gemma4:26b-mlx` — **vision**, 3 of 5 cameras have `genai.enabled: true` | OpenAI `/v1` | git ✅ | `configmap.sops.yaml` (`genai.model`, encrypted); host URL in `helmrelease.yaml:34` |
| Open WebUI | ai | (human picks per chat) | Native Ollama | **DB ❌** | Not settable from the manifest. `ui.default_models`, the `model` table's `is_active`, and `ollama.api_configs[].model_ids` (per-connection allow-list) all live in `webui.db` and are PersistentConfig — env only seeds a fresh DB. The GGUF stays pickable until an admin hides it. |
| Paperless-ngx (native AI) | office | `gemma4:26b-mlx` (suggestions, 45s timeout) + `nomic-embed-text:latest` (RAG) | Native Ollama | **DB ✅** | DB-stored `ApplicationConfiguration`; migrated 2026-09-04 by paperless-agent — see `docs/sops/paperless.md` §4a |
| Nextcloud | office | `gemma4:26b-mlx` | OpenAI `/v1` | **DB ✅** | Migrated 2026-09-04 via `occ config:app:set` — **all FOUR** keys (`default_completion_model_id`, `default_image_model_id`, `default_speech_model_id`, `default_stt_model_id`), not just the completion one. Verified by reading each back. |
| Nextcloud | office | `nomic-embed-text:latest` (context_chat RAG) | OpenAI `/v1` | n/a | NC UI: `context_chat` app |
| n8n | home-automation | `gemma4:26b-mlx` | Ollama (UI) | **DB ✅** | Migrated 2026-09-05. ONE node in the inactive `ai-sysadmin-agent` workflow; the `ollamaApi` credential holds only the base URL. Verified via `workflow_entity` **through the SQLite driver**: 14 workflows, 0 on the GGUF. A raw grep of the DB file says otherwise and is wrong — see the WAL/free-page note in `docs/integration.md`. |
| Home Assistant | home-automation | `gemma4:26b-mlx` + `gemma4:e2b-mlx` (voice) | Native Ollama | **UI ✅** | Migrated 2026-09-05 by ha-agent, confirmed with five `/api/ps` snapshots. Covers 2 Ollama subentries **and** three direct-HTTP scripts in the `/config` PVC that no integration list shows: `ai_person_check.py`, `ai_person_check_file.py` (**both vision**, `images:[b64]`), `ai_water_check.py`. **HA sends an explicit `num_ctx` and cannot omit it** — an unset value sends 8192, not the host default — so HA must move in lockstep with any `OLLAMA_CONTEXT_LENGTH` change or every call evicts and reloads the pinned model. All subentries set `keep_alive: -1`. |
| Headlamp | **monitoring** (not kube-system) | `gemma4:26b` | OpenAI `/v1` | **browser ❌** | AI Assistant plugin config lives in per-browser localStorage — no server-side config exists in the pod; cannot be fixed from cluster or repo |

---

## External Cloud AI APIs

| App | Namespace | Provider | Services | Config Location |
|-----|-----------|----------|----------|-----------------|
| Home Assistant | home-automation | OpenAI (ChatGPT) | Conversation, AI Task, TTS (`gpt-4o-mini-tts`), STT | HA UI: `.storage/core.config_entries` (openai_conversation domain) |
| Home Assistant | home-automation | Google Generative AI | Conversation, TTS, AI Task, STT | HA UI: `.storage/core.config_entries` (google_generative_ai_conversation domain) |
| Home Assistant | home-automation | Google Translate | TTS | HA UI: `.storage/core.config_entries` (google_translate domain) |
| Paperclip | ai | OpenAI | Agent orchestration | `kubernetes/apps/ai/paperclip/app/secret.sops.yaml` (OPENAI_API_KEY) |
| n8n | home-automation | OpenAI | AI Agent workflows (Google Calendar, etc.) | n8n SQLite DB: `openAiApi` credential |
| n8n | home-automation | Anthropic | Available in workflows | n8n SQLite DB: `anthropicApi` credential |
| opencode (dev template) | my-software-development | Anthropic, OpenAI, Gemini | Coding assistant | `kubernetes/apps/my-software-development/_template/app/secrets.example.yaml` (scaffold; rename + sops-encrypt before deploying a real app) |

---

## AI Infrastructure (No Direct Model Inference)

| App | Namespace | Role | Config Location |
|-----|-----------|------|-----------------|
| MCPO | ai | MCP protocol server orchestrator (GitHub, etc.) | `kubernetes/apps/ai/mcpo/app/helmrelease.yaml` |
| AI-SRE | ai | MCP-based SRE tooling (cluster ops, not LLM inference) | `kubernetes/apps/ai/ai-sre/app/helmrelease.yaml` |

---

## UI/DB-Configured Apps — status after the 2026-09-04/05 MLX migration

These apps store their Ollama config in their own databases/UI, not in git
manifests, so the migration commit could not touch them — each needed its own
owner and its own verification. **Any one of them still requesting `gemma4:26b`
would keep the 27.1 GiB GGUF resident on the host.** All but Headlamp are done.

| App | Status | Owner | Notes |
|-----|--------|-------|-------|
| **Paperless-ngx** | Migrated 2026-09-04 | paperless-agent | `ApplicationConfiguration` DB row |
| **Nextcloud** | Migrated 2026-09-04 | cberg-agent | All four model keys via `occ config:app:set` |
| **n8n** | Migrated 2026-09-05 | cberg-agent | One node in an inactive workflow; verified through the SQLite driver, not a file grep |
| **Home Assistant** | Migrated 2026-09-05 | ha-agent | 2 subentries + 3 direct-HTTP scripts. Sends explicit `num_ctx` — must move with the host ceiling. All `keep_alive: -1` |
| **Headlamp** | **OUTSTANDING — unfixable server-side** | user | AI Assistant plugin stores model + endpoint in **per-browser localStorage**. No server-side config exists in the pod, so neither GitOps nor a DB edit can reach it. The user must change it in the plugin's settings **in every browser and profile** he uses. Until then, that browser still requests the GGUF. |
| **Open WebUI** | Migrated 2026-09-05 | cberg-agent | GGUF locked out server-side: removed from the `ollama.api_configs` connection allow-list (`model_ids`) **and** `is_active=0` on its `model` row. Verified persisted across a restart. Note the user's earlier UI pinning had *included* the GGUF in that allow-list. |
| **LibreChat** | Migrated 2026-09-05 | cberg-agent | All 37 Mongo collections audited: 0 presets, 0 agents, 0 assistants, 0 user defaults. One dormant conversation (last touched 19 Aug) repointed. `messages`/`transactions` left as historical records. `fetch: true` still lists whatever is pulled on disk, so a human can pick the GGUF by hand until the tag is removed. |
| **Frigate NVR** | Migrated 2026-09-04 | git | `configmap.sops.yaml` — now in GitOps, not UI |

---

## Nextcloud AI Task Routing

Nextcloud routes AI tasks through the `integration_openai` app.

| Task Type | Provider | Model |
|-----------|----------|-------|
| text2text (all: chat, summary, translate, proofread, etc.) | integration_openai | `gemma4:26b-mlx` (after manual update) |
| context_chat (RAG) | context_chat + files | `nomic-embed-text:latest` (embeddings) |

Nextcloud apps: `assistant` (3.3.0), `context_chat` (5.3.1), `integration_openai` (4.3.0)

---

## n8n AI Workflows

| Credential | Provider | Notes |
|------------|----------|-------|
| `ollamaApi` | Ollama (Mac Mini) | Needs manual update to `:11434` endpoint and `gemma4:26b-mlx` model |
| `openAiApi` | OpenAI Cloud | No change needed |
| `anthropicApi` | Anthropic Cloud | No change needed |

---

## Context and TTL settings

The host-side values (engine version, `OLLAMA_CONTEXT_LENGTH`, `OLLAMA_KEEP_ALIVE`,
`OLLAMA_NUM_PARALLEL`, `OLLAMA_MAX_LOADED_MODELS`, warm set) are documented in
**`local-ollama-monitor/docs/ollama-model-setup.md`** and deliberately not copied
here — duplicated numbers drift.

What lives on the consumer side:

| Consumer | Setting | Purpose | Moves with the host ceiling? |
|---|---|---|---|
| `openclaw` | `contextWindow` on all four `ollama`/`ollama-native` refs | Compaction threshold for agent turns | **Yes — mirrors the host.** `/v1`, so no wire `num_ctx` |
| `hermes-agent` | `context_length` in `configmap.yaml` **and** `/opt/data/config.yaml` (PVC) | Client-side prompt budgeting | **Yes.** Seed does not propagate — patch the PVC too |
| `home-assistant` | `num_ctx` per Ollama subentry | Sent on the wire | **YES, mandatory.** Cannot be omitted — unset sends 8192, not the host default. A mismatch makes every HA call evict and reload the pinned 18 GB model |
| `sure` | `LLM_CONTEXT_WINDOW` | Caps `BatchSlicer` input | No — a client-side cap well under the ceiling. Re-check the margin before raising it |
| `sure` | `OPENAI_REQUEST_TIMEOUT` | Tolerates slow local inference | No |
| `paperless-ngx` | `llm_request_timeout` (DB row) | Bounds suggestion calls | No |
| `frigate` | hard-coded 120 s genai timeout | Not configurable | No — but it is the ceiling a slow vision path must fit inside |
| `anythingllm` | `OLLAMA_RESPONSE_TIMEOUT` | Tolerates slow inference | No |

**`keep_alive` is the other half of the memory story.** The host runs
`OLLAMA_KEEP_ALIVE=-1`, so anything loaded once is pinned permanently. Home
Assistant *additionally* sets `keep_alive: -1` on its own subentries, which means a
finite host default would not save you — one HA call re-pins whatever it loads.

---

## Models Required on Mac Mini

| Model | Consumers |
|-------|-----------|
| `gemma4:26b-mlx` | **Migrated:** AnythingLLM, OpenClaw, Next AI Draw.io, LibreChat, Sure, hermes-agent, ha-ai-harness, AFFiNE, Frigate NVR, Paperless-ngx |
| `gemma4:26b` (GGUF — **retired 2026-09-05**) | **Nothing autonomous requests it any more.** Remaining human-initiated paths only: Headlamp (per-browser localStorage) and LibreChat's picker (`fetch: true` lists whatever is pulled on disk). **Never re-point a consumer at this tag:** it needs 27.1 GiB (256k ctx alloc, `-np 2`, q8_0 KV) against the MLX build's 18.7 GiB — 45.8 of 48 GiB, so any state where both are requested is guaranteed to OOM. |
| `nomic-embed-text:latest` | AnythingLLM (embeddings), Nextcloud (context_chat RAG), AFFiNE (embeddings), Paperless-ngx (native AI RAG embeddings) |

---

## Consumer Count

| Endpoint | Git-Managed Apps | UI/DB-Configured Apps | Total |
|----------|------------------|-----------------------|-------|
| Mac Mini :11434 | 9 (AnythingLLM, OpenClaw, Next AI Draw.io, LibreChat, **Sure**, **hermes-agent**, **ha-ai-harness**, AFFiNE, Frigate NVR) | 6 (Paperless, Nextcloud, n8n, Home Assistant, Open WebUI, Headlamp) | 15 |
| Cloud APIs | 1 (Paperclip) | 5 (HA x3, n8n x2) | 6 |
