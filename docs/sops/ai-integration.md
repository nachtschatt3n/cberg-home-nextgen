# SOP: AI Integration

> Standard Operating Procedures for AI/ML service integration and management.
> Reference: `docs/integration.md` for endpoint reference table.
> Description: Operating and integrating Ollama-based AI endpoints for cluster applications.
> Version: `2026.04.04`
> Last Updated: `2026-04-04`
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

In-cluster AI services (Open WebUI, Langfuse, etc.) connect to this external endpoint.

---

## Blueprints

N/A for dedicated Authentik-style blueprints.

Declarative source-of-truth for AI integrations is maintained in application manifests under:
- `kubernetes/apps/ai/`
- `kubernetes/apps/office/` (Paperless-AI / Paperless-GPT / AFFiNE / Nextcloud)
- `kubernetes/apps/home-automation/` (Frigate AI settings, Home Assistant, n8n)

---

## Operational Instructions

1. All apps use the single endpoint: `http://192.168.30.111:11434`
2. Use `gemma4:26b` for all LLM tasks (chat, reasoning, vision, voice).
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
    value: "gemma4:26b"
```

### Example 2: OpenAI-Compatible Configuration

```yaml
env:
  - name: OPENAI_BASE_URL
    value: "http://192.168.30.111:11434/v1"
  - name: OPENAI_MODEL
    value: "gemma4:26b"
```

---

## Ollama Endpoint

| Endpoint | Port | Purpose |
|---------|------|---------|
| `http://192.168.30.111:11434` | 11434 | All AI inference |

### Models

| Model | Purpose |
|-------|---------|
| `gemma4:26b` | All LLM tasks — chat, reasoning, vision, voice. Multimodal (text + image). |
| `nomic-embed-text:latest` | Text embeddings |

**Important:** The model name in API calls must be exactly `gemma4:26b` (not `gemma4` or `gemma4:26b-instruct`).

---

## Native API Format (Preferred)

- Base URL: `http://192.168.30.111:11434/api` (no trailing slash, no `/v1`)
- Endpoints: `/api/chat`, `/api/generate`
- API key: not required for native Ollama API
- Model name: `gemma4:26b` (exact)
- Embedding model: `nomic-embed-text:latest`

Use OpenAI-compatible `/v1` endpoints only for apps that require OpenAI API format.

---

## Testing Endpoints

```bash
# Test LLM (text)
curl -X POST http://192.168.30.111:11434/api/chat \
  -H "Content-Type: application/json" \
  -d '{"model": "gemma4:26b", "messages": [{"role": "user", "content": "Hello"}], "stream": false}'

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
  -d '{"name": "gemma4:26b", "stream": false}'

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

### Langfuse (`ai/langfuse`)

LLM observability, tracing, and analytics.

```bash
kubectl get pods -n ai -l app.kubernetes.io/name=langfuse
kubectl logs -n ai -l app.kubernetes.io/name=langfuse --tail=50
# Access: https://langfuse.${SECRET_DOMAIN}
```

### OpenClaw (`ai/openclaw`)

AI agent platform.

```bash
kubectl get pods -n ai -l app.kubernetes.io/name=openclaw
# Access: https://openclaw.${SECRET_DOMAIN}
```

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
| Ollama (all tasks) | `http://192.168.30.111:11434` | `gemma4:26b` | Voice, AI tasks, vision |
| OpenAI (ChatGPT) | Cloud | `gpt-4o-mini-tts` (TTS) | Conversation, AI Task, TTS, STT |
| Google Generative AI | Cloud | (default) | Conversation, TTS, AI Task, STT |
| Google Translate | Cloud | - | TTS |

### AnythingLLM (`ai/anythingllm`)

RAG chat and document embedding.

| Setting | Value |
|---------|-------|
| Endpoint | `http://192.168.30.111:11434` |
| LLM Model | `gemma4:26b` |
| Embedding Model | `nomic-embed-text:latest` |
| Config | `OLLAMA_BASE_PATH`, `EMBEDDING_BASE_PATH` |

**Configuration:** `kubernetes/apps/ai/anythingllm/app/helmrelease.yaml:80-89`

### LibreChat (`ai/librechat`)

Chat interface with multi-provider support.

| Setting | Value |
|---------|-------|
| Endpoint | `http://192.168.30.111:11434/v1` |
| Default Model | `gemma4:26b` (fetch=true for dynamic model list) |
| Config | Custom endpoint "Ollama" with OpenAI-compatible API |

**Configuration:** `kubernetes/apps/ai/librechat/app/helmrelease.yaml:63-72`

### Next AI Draw.io (`ai/next-ai-draw-io`)

AI-powered diagram generation.

| Setting | Value |
|---------|-------|
| Endpoint | `http://192.168.30.111:11434/api` |
| Model | `gemma4:26b` |
| Config | `AI_PROVIDER: "ollama"`, `OLLAMA_BASE_URL` (native `/api`) |

**Configuration:** `kubernetes/apps/ai/next-ai-draw-io/app/helmrelease.yaml:35-40`

### AFFiNE (`office/affine`)

Collaborative workspace with AI copilot features.

| Setting | Value |
|---------|-------|
| Endpoint | `http://192.168.30.111:11434/v1` |
| LLM Model | `gemma4:26b` (coding, text gen, summarize, decisions) |
| Embedding Model | `nomic-embed-text:latest` |
| Config | OpenAI-compatible provider in copilot configmap |

**Configuration:** `kubernetes/apps/office/affine/app/configmap.yaml:58-72`

### Nextcloud (`office/nextcloud`)

Nextcloud uses the `integration_openai` app plus `context_chat` for RAG with embeddings.
All configured through the Nextcloud admin UI. **Requires manual update.**

| Integration | Model | Use Case |
|------------|-------|----------|
| integration_openai | `gemma4:26b` | Text gen, chat, summary, translate, proofread, headlines, topics |
| context_chat | `nomic-embed-text:latest` | RAG embeddings for file-based context chat |

**Configuration:** NC admin UI > `integration_openai` app settings
- Endpoint: `http://192.168.30.111:11434/v1`
- Default model: `gemma4:26b`
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
| ollamaApi | Ollama (`http://192.168.30.111:11434`) | `gemma4:26b` |
| openAiApi | OpenAI Cloud | (default cloud models) |
| anthropicApi | Anthropic Cloud | (available, usage varies by workflow) |

**Configuration:** n8n UI > Credentials (stored in `/home/node/.n8n/database.sqlite`)

```bash
# Check n8n AI credentials (via string extraction)
kubectl exec -n home-automation deploy/n8n -- cat /home/node/.n8n/database.sqlite 2>/dev/null \
  | strings | grep -iE 'ollamaApi|openAiApi|anthropicApi' | head -10
```

### Paperless-AI (`office/paperless-ai`)

Document classification using Ollama.

| Setting | Value |
|---------|-------|
| Endpoint | `http://192.168.30.111:11434/v1` |
| Model | `gemma4:26b` |
| Config | `AI_PROVIDER: "custom"`, `CUSTOM_BASE_URL` |

```bash
kubectl get pods -n office -l app.kubernetes.io/name=paperless-ai
kubectl logs -n office -l app.kubernetes.io/name=paperless-ai --tail=50
```

### Paperless-GPT (`office/paperless-gpt`)

AI tagging and summarization for Paperless-ngx.

| Setting | Value |
|---------|-------|
| Endpoint | `http://192.168.30.111:11434/v1` |
| LLM Model | `gemma4:26b` |
| Vision Model | `gemma4:26b` (multimodal) |
| Config | `LLM_PROVIDER: "openai"`, `OPENAI_BASE_URL` |

```bash
kubectl logs -n office -l app.kubernetes.io/name=paperless-gpt --tail=50
```

### Frigate NVR AI (`home-automation/frigate-nvr`)

AI-powered camera event descriptions.

| Setting | Value |
|---------|-------|
| Endpoint | `http://192.168.30.111:11434/v1` |
| Model | `gemma4:26b` (in encrypted configmap, **requires manual update**) |
| Config | `OPENAI_BASE_URL` env var |

```bash
kubectl logs -n home-automation -l app.kubernetes.io/name=frigate-nvr --tail=50 | grep -i ai
```

---

## Integrating a New App with Ollama

### Step 1: Choose the Model

| Use Case | Model | Notes |
|---------|-------|-------|
| Text processing, reasoning, chat | `gemma4:26b` | Multimodal — handles text and images |
| Image/vision analysis | `gemma4:26b` | No separate vision model needed |
| Voice/audio | `gemma4:26b` | Same model for all tasks |
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
    value: "gemma4:26b"
```

**OpenAI-compatible API:**
```yaml
env:
  - name: OPENAI_BASE_URL
    value: "http://192.168.30.111:11434/v1"
  - name: OPENAI_API_KEY
    value: "not-required"
  - name: OPENAI_MODEL
    value: "gemma4:26b"
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
  -d '{"name": "gemma4:26b"}'
```

### Slow Response Times

- Check Mac Mini load: `gemma4:26b` is 26B params, ensure adequate memory
- Ollama loads models on demand and keeps them warm with `keep_alive`
- Only `gemma4:26b` and `nomic-embed-text:latest` should be loaded

### Wrong Endpoint Format

Apps expecting OpenAI format need `/v1/` path, not `/api/`:
```
OpenAI format: http://192.168.30.111:11434/v1/chat/completions
Ollama native: http://192.168.30.111:11434/api/chat
```

Model name must be exactly `gemma4:26b` (not `gemma4` or `gemma4:26b-instruct`).

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
  -d '{"model":"gemma4:26b","messages":[{"role":"user","content":"ping"}],"stream":false}'
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
- `gemma4:26b` and `nomic-embed-text:latest` appear in the list.

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
for required in ['gemma4:26b', 'nomic-embed-text:latest']:
    status = 'OK' if required in models else 'MISSING'
    print(f'{required}: {status}')
"

# Check all AI namespace pods are running
kubectl get pods -n ai

# Check Langfuse is receiving traces (via UI)
# https://langfuse.${SECRET_DOMAIN}
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
