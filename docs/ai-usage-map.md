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
| Nextcloud | office | `gemma4:26b` | OpenAI `/v1` | **DB ❌** | `occ config:app:get integration_openai default_completion_model_id` — verified still on the GGUF 2026-09-04 |
| Nextcloud | office | `nomic-embed-text:latest` (context_chat RAG) | OpenAI `/v1` | n/a | NC UI: `context_chat` app |
| n8n | home-automation | `gemma4:26b` | Ollama (UI) | **DB ❌** | n8n SQLite DB — 470 `lmChatOllama` nodes + `ollamaApi` credential, verified still on the GGUF 2026-09-04 |
| Home Assistant | home-automation | `gemma4:26b` (2 subentries) + `gemma4:e2b-mlx` (voice) | Native Ollama | **UI ❌** | HA UI + **three direct-HTTP scripts in the `/config` PVC** that no integration list shows: `ai_person_check.py`, `ai_person_check_file.py` (**both vision**, `images:[b64]`), `ai_water_check.py` (probes `/api/ps` for the literal string `gemma4:26b` — needs 2 coordinated edits). All subentries set `keep_alive: -1`. Owner: `ha-agent` |
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

## UI/DB-Configured Apps — OUTSTANDING after the 2026-09-04 MLX migration

These apps store their Ollama config in their own databases/UI, not in git
manifests, so the migration commit could NOT touch them. **Each one still
requesting `gemma4:26b` keeps the 27.1 GiB GGUF resident on the host.**

| App | Status | Owner | Notes |
|-----|--------|-------|-------|
| **Paperless-ngx** | Migrated 2026-09-04 | paperless-agent | `ApplicationConfiguration` DB row |
| **Nextcloud** | **OUTSTANDING** | — | `occ config:app:set integration_openai default_completion_model_id gemma4:26b-mlx` |
| **n8n** | **OUTSTANDING** | — | `ollamaApi` credential + every `lmChatOllama` node in the SQLite DB |
| **Home Assistant** | **OUTSTANDING** | ha-agent | 2 Ollama subentries + 3 direct-HTTP scripts in `/config` (2 of them vision). All `keep_alive: -1` |
| **Headlamp** | **OUTSTANDING** | — | Per-browser localStorage; no server-side config exists |
| **Open WebUI** | **OUTSTANDING** | — | Human picks per chat; hide the GGUF via `is_active` or `model_ids` allow-list |
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

## Models Required on Mac Mini

| Model | Consumers |
|-------|-----------|
| `gemma4:26b-mlx` | **Migrated:** AnythingLLM, OpenClaw, Next AI Draw.io, LibreChat, Sure, hermes-agent, ha-ai-harness, AFFiNE, Frigate NVR, Paperless-ngx |
| `gemma4:26b` (GGUF — **to be retired**) | **Still requesting it:** Nextcloud, n8n, Home Assistant, Headlamp, Open WebUI (user-selectable). **The GGUF needs 27.1 GiB (256k ctx alloc, `-np 2`, q8_0 KV) and the MLX build 18.7 GiB — 45.8 of 48 GiB. Any state where both are requested is guaranteed to OOM.** The GGUF cannot be unloaded until this row is empty. |
| `nomic-embed-text:latest` | AnythingLLM (embeddings), Nextcloud (context_chat RAG), AFFiNE (embeddings), Paperless-ngx (native AI RAG embeddings) |

---

## Consumer Count

| Endpoint | Git-Managed Apps | UI/DB-Configured Apps | Total |
|----------|------------------|-----------------------|-------|
| Mac Mini :11434 | 10 (AnythingLLM, OpenClaw, Next AI Draw.io, LibreChat, **Sure**, **hermes-agent**, **ha-ai-harness**, AFFiNE, Frigate NVR + embeddings) | 6 (Paperless, Nextcloud, n8n, HA, Headlamp, Open WebUI) | 16 |
| Cloud APIs | 1 (Paperclip) | 5 (HA x3, n8n x2) | 6 |
