# AI Usage Map

> Comprehensive mapping of all AI/LLM integrations across the cluster and Home Assistant.
> Last Updated: 2026-04-04

---

## Mac Mini Ollama Endpoint (192.168.30.111:11434)

Single Ollama instance on Mac Mini M4 Pro with Metal (MPS) acceleration.
Ports 11435 and 11436 are no longer in use.

### Models

| Model | Purpose |
|-------|---------|
| `gemma4:26b` | All LLM tasks (chat, reasoning, vision, voice). Multimodal (text + image). |
| `nomic-embed-text:latest` | Text embeddings |

### All Consumers

| App | Namespace | Model | API Style | Config Location |
|-----|-----------|-------|-----------|-----------------|
| AnythingLLM | ai | `gemma4:26b` (LLM) | Native Ollama | `kubernetes/apps/ai/anythingllm/app/helmrelease.yaml:82-83` |
| AnythingLLM | ai | `nomic-embed-text:latest` (embeddings) | Native Ollama | `kubernetes/apps/ai/anythingllm/app/helmrelease.yaml:87-88` |
| OpenClaw | ai | `gemma4:26b` | OpenAI `/v1` | `kubernetes/apps/ai/openclaw/app/helmrelease.yaml:424-426` |
| Next AI Draw.io | ai | `gemma4:26b` | Native Ollama `/api` | `kubernetes/apps/ai/next-ai-draw-io/app/helmrelease.yaml:37-40` |
| LibreChat | ai | `gemma4:26b` (default, fetch=true) | OpenAI `/v1` | `kubernetes/apps/ai/librechat/app/helmrelease.yaml:64-70` |
| Open WebUI | ai | (all available models) | Native Ollama | `kubernetes/apps/ai/open-webui/app/helmrelease.yaml:84` |
| Paperless-GPT | office | `gemma4:26b` (LLM + vision) | OpenAI `/v1` | `kubernetes/apps/office/paperless-gpt/app/helmrelease.yaml:48,55-56` |
| Paperless-AI | office | `gemma4:26b` | OpenAI `/v1` | `kubernetes/apps/office/paperless-ai/app/helmrelease.yaml:52-53` |
| AFFiNE | office | `gemma4:26b` (coding, text, summarize) | OpenAI `/v1` | `kubernetes/apps/office/affine/app/configmap.yaml:58-65,71` |
| Frigate NVR | home-automation | `gemma4:26b` (in encrypted configmap) | OpenAI `/v1` | `kubernetes/apps/home-automation/frigate-nvr/app/helmrelease.yaml:34` |
| Nextcloud | office | `gemma4:26b` | OpenAI `/v1` | NC UI: `integration_openai` app (updated 2026-04-04) |
| Nextcloud | office | `nomic-embed-text:latest` (context_chat RAG) | OpenAI `/v1` | NC UI: `context_chat` app |
| n8n | home-automation | `gemma4:26b` | Ollama (UI) | n8n SQLite DB (updated 2026-04-04) |
| Home Assistant | home-automation | `gemma4:26b` (all integrations) | Native Ollama | HA UI (updated 2026-04-04) |
| Headlamp | kube-system | `gemma4:26b` | OpenAI `/v1` | Headlamp UI: AI Assistant plugin (updated 2026-04-05) |

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
| Langfuse | ai | LLM observability/tracing platform | `kubernetes/apps/ai/langfuse/app/langfuse.yaml` |
| MCPO | ai | MCP protocol server orchestrator (GitHub, etc.) | `kubernetes/apps/ai/mcpo/app/helmrelease.yaml` |
| AI-SRE | ai | MCP-based SRE tooling (cluster ops, not LLM inference) | `kubernetes/apps/ai/ai-sre/app/helmrelease.yaml` |

---

## UI-Configured Apps (Manual Updates Completed 2026-04-04)

These apps store their Ollama config in their own databases/UI, not in git manifests.
All have been updated to `gemma4:26b` on `:11434`.

| App | Status | Notes |
|-----|--------|-------|
| **Home Assistant** | Done | All 3 Ollama integrations updated via HA UI |
| **Nextcloud** | Done | `integration_openai` settings updated via `occ config:app:set` |
| **n8n** | Done | Ollama credential and workflow nodes updated via n8n UI |
| **Frigate NVR** | Done | `configmap.sops.yaml` decrypted, updated, re-encrypted in git |
| **Headlamp** | Done | AI Assistant plugin model updated via Headlamp UI |

---

## Nextcloud AI Task Routing

Nextcloud routes AI tasks through the `integration_openai` app.

| Task Type | Provider | Model |
|-----------|----------|-------|
| text2text (all: chat, summary, translate, proofread, etc.) | integration_openai | `gemma4:26b` (after manual update) |
| context_chat (RAG) | context_chat + files | `nomic-embed-text:latest` (embeddings) |

Nextcloud apps: `assistant` (3.3.0), `context_chat` (5.3.1), `integration_openai` (4.3.0)

---

## n8n AI Workflows

| Credential | Provider | Notes |
|------------|----------|-------|
| `ollamaApi` | Ollama (Mac Mini) | Needs manual update to `:11434` endpoint and `gemma4:26b` model |
| `openAiApi` | OpenAI Cloud | No change needed |
| `anthropicApi` | Anthropic Cloud | No change needed |

---

## Models Required on Mac Mini

| Model | Consumers |
|-------|-----------|
| `gemma4:26b` | AnythingLLM, OpenClaw, Next AI Draw.io, LibreChat, Open WebUI, Paperless-GPT, Paperless-AI, AFFiNE, Frigate NVR, Home Assistant, Nextcloud, n8n, Headlamp |
| `nomic-embed-text:latest` | AnythingLLM (embeddings), Nextcloud (context_chat RAG), AFFiNE (embeddings) |

---

## Consumer Count

| Endpoint | Git-Managed Apps | UI-Configured Apps | Total |
|----------|------------------|--------------------|-------|
| Mac Mini :11434 | 9 | 4 (HA, Nextcloud, n8n, Headlamp) | 13 |
| Cloud APIs | 1 (Paperclip) | 5 (HA x3, n8n x2) | 6 |
