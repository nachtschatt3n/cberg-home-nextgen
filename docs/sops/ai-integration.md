# SOP: AI Integration

> Standard Operating Procedures for AI/ML service integration and management.
> Reference: `docs/integration.md` for endpoint reference table.
> Description: Operating and integrating Ollama-based AI endpoints for cluster applications.
> Version: `2026.03.01`
> Last Updated: `2026-03-01`
> Owner: `Platform`

---

## Description

This SOP defines how AI integrations use the Mac Mini Ollama endpoints, how to configure consuming
applications, and how to verify end-to-end connectivity and model behavior.

---

## Overview

AI inference runs on Mac Mini M4 Pro (`192.168.30.111`) with three dedicated Ollama instances
using Metal Performance Shaders (MPS) for GPU acceleration.

In-cluster AI services (Open WebUI, Langfuse, etc.) connect to these external endpoints.

---

## Blueprints

N/A for dedicated Authentik-style blueprints.

Declarative source-of-truth for AI integrations is maintained in application manifests under:
- `kubernetes/apps/ai/`
- `kubernetes/apps/office/` (Paperless-AI / Paperless-GPT)
- `kubernetes/apps/home-automation/` (Frigate AI settings)

---

## Operational Instructions

1. Choose the correct Ollama instance and model.
2. Update the target app manifest/secret in Git with endpoint + model configuration.
3. Commit and push changes to trigger Flux reconciliation.
4. Validate app logs and endpoint connectivity.

---

## Examples

### Example 1: Native Ollama API Configuration

```yaml
env:
  - name: OLLAMA_HOST
    value: "http://192.168.30.111:11435"
  - name: OLLAMA_MODEL
    value: "gpt-oss:20b"
```

### Example 2: OpenAI-Compatible Configuration

```yaml
env:
  - name: OPENAI_BASE_URL
    value: "http://192.168.30.111:11435/v1"
  - name: OPENAI_MODEL
    value: "gpt-oss:20b"
```

---

## Ollama Instances

| Instance | Port | Model | Purpose |
|---------|------|-------|---------|
| Voice | 11434 | `qwen3:4b-instruct` | Voice/audio processing |
| Reason | 11435 | `gpt-oss:20b` | General reasoning and text |
| Vision | 11436 | `qwen3-vl:8b-instruct` | Vision/image analysis |

**Base URL pattern:** `http://192.168.30.111:{PORT}/api`

---

## Native API Format (Preferred)

- Base URL: `http://192.168.30.111:{PORT}/api` (no trailing slash, no `/v1`)
- Endpoints: `/api/chat`, `/api/generate`
- API key: not required for native Ollama API
- Model names must use Ollama format: `gpt-oss:20b`, `qwen3:4b-instruct`, `qwen3-vl:8b-instruct`
- Avoid OpenAI-style model IDs such as `openai/gpt-oss-20b`

Use OpenAI-compatible `/v1` endpoints only for apps that require OpenAI API format.

---

## Testing Endpoints

```bash
# Test Voice instance
curl -X POST http://192.168.30.111:11434/api/chat \
  -H "Content-Type: application/json" \
  -d '{"model": "qwen3:4b-instruct", "messages": [{"role": "user", "content": "Hello"}], "stream": false}'

# Test Reason instance
curl -X POST http://192.168.30.111:11435/api/chat \
  -H "Content-Type: application/json" \
  -d '{"model": "gpt-oss:20b", "messages": [{"role": "user", "content": "Hello"}], "stream": false}'

# Test Vision instance
curl -X POST http://192.168.30.111:11436/api/chat \
  -H "Content-Type: application/json" \
  -d '{"model": "qwen3-vl:8b-instruct", "messages": [{"role": "user", "content": "Hello"}], "stream": false}'

# List available models on an instance
curl http://192.168.30.111:11435/api/tags
```

**Expected response:** JSON with `model`, `message.content`, and timing fields.

---

## Model Management

### Pulling a New Model

SSH into Mac Mini and use Ollama CLI, or use the Ollama API:

```bash
# Pull model via API (runs on Mac Mini)
curl http://192.168.30.111:11435/api/pull \
  -H "Content-Type: application/json" \
  -d '{"name": "llama3.2:3b", "stream": false}'

# Check pull status
curl http://192.168.30.111:11435/api/tags
```

### Checking Model Status

```bash
# List models on each instance
for port in 11434 11435 11436; do
  echo "=== Port $port ==="
  curl -s http://192.168.30.111:${port}/api/tags | python3 -c \
    "import sys, json; models = json.load(sys.stdin)['models']; [print(m['name'], m['size']) for m in models]"
done
```

### Deleting a Model

```bash
curl -X DELETE http://192.168.30.111:11435/api/delete \
  -H "Content-Type: application/json" \
  -d '{"name": "old-model:tag"}'
```

---

## In-Cluster AI Services

### Open WebUI (`ai/open-webui`)

Chat interface for AI models. Connects to in-cluster IPEX Ollama instance.

```bash
# Check Open WebUI is running
kubectl get pods -n ai -l app.kubernetes.io/name=open-webui

# View logs
kubectl logs -n ai -l app.kubernetes.io/name=open-webui --tail=50

# Access
# https://openwebui.${SECRET_DOMAIN}
```

**Configuration:** Open WebUI uses the in-cluster IPEX Ollama instance
(`http://ollama-ipex.ai.svc.cluster.local:11434`), not the Mac Mini directly.

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

AI-powered SRE tooling. Uses Reason instance on port 11435.

```bash
kubectl get pods -n ai -l app.kubernetes.io/name=ai-sre
```

---

## App-Specific AI Configurations

### Paperless-AI (`office/paperless-ai`)

Document classification using Ollama.

| Setting | Value |
|---------|-------|
| Instance | Reason (11435) |
| Model | `qwen3:4b-instruct` |
| Config | `AI_PROVIDER: "custom"`, `CUSTOM_BASE_URL: "http://192.168.30.111:11435/api"` |

```bash
kubectl get pods -n office -l app.kubernetes.io/name=paperless-ai
kubectl logs -n office -l app.kubernetes.io/name=paperless-ai --tail=50
```

### Paperless-GPT (`office/paperless-gpt`)

AI tagging and summarization for Paperless-ngx.

| Setting | Value |
|---------|-------|
| Instance | Reason (11435) |
| LLM Model | `gpt-oss:20b` |
| Vision Model | `qwen3-vl:8b-instruct` |
| Vision Endpoint | `http://192.168.30.111:11435/api` (same Reason instance) |
| Config | `LLM_PROVIDER: "openai"`, `OPENAI_BASE_URL: "http://192.168.30.111:11435/api"` |

```bash
kubectl logs -n office -l app.kubernetes.io/name=paperless-gpt --tail=50
```

### Frigate NVR AI (`home-automation/frigate-nvr`)

AI object detection using Vision instance.

| Setting | Value |
|---------|-------|
| Instance | Vision (11436) |
| Model | `qwen3-vl:8b-instruct` |
| Endpoint | `http://192.168.30.111:11436/api` |
| Config | `OPENAI_BASE_URL` env var (`/v1` may be required by some OpenAI-only clients) |

```bash
kubectl logs -n home-automation -l app.kubernetes.io/name=frigate-nvr --tail=50 | grep -i ai
```

---

## Integrating a New App with Ollama

### Step 1: Choose the Right Instance

| Use Case | Instance | Port | Model |
|---------|---------|------|-------|
| Text processing, reasoning | Reason | 11435 | `gpt-oss:20b` |
| Image/vision analysis | Vision | 11436 | `qwen3-vl:8b-instruct` |
| Voice/audio | Voice | 11434 | `qwen3:4b-instruct` |

### Step 2: Configure the App

Most apps support either native Ollama API or OpenAI-compatible API.
Prefer native `/api` unless the app explicitly requires OpenAI-compatible `/v1`.

**Native Ollama API:**
```yaml
env:
  - name: OLLAMA_HOST
    value: "http://192.168.30.111:11435"
  - name: OLLAMA_MODEL
    value: "gpt-oss:20b"
```

**OpenAI-compatible API:**
```yaml
env:
  - name: OPENAI_BASE_URL
    value: "http://192.168.30.111:11435/v1"
  - name: OPENAI_API_KEY
    value: "not-required"
  - name: OPENAI_MODEL
    value: "gpt-oss:20b"
```

### Step 3: Update Integration Documentation

Update `docs/integration.md` → "Application Configuration" table with the new app.

### Step 4: Test

```bash
# Test that the app can reach the Ollama endpoint
kubectl exec -n {namespace} {pod} -- \
  wget -qO- http://192.168.30.111:11435/api/tags 2>&1 | head -20
```

---

## Troubleshooting

### App Cannot Connect to Ollama

```bash
# Test connectivity from a test pod (if app pod lacks wget/curl)
kubectl run test-ai --rm -it --image=alpine -n {namespace} -- \
  wget -qO- http://192.168.30.111:11435/api/tags

# Check Mac Mini is reachable
ping 192.168.30.111

# Verify Ollama is running on Mac Mini (via SSH or local)
# On Mac Mini: launchctl list | grep ollama
```

### Model Not Found Error

```bash
# List available models on the instance
curl http://192.168.30.111:11435/api/tags | python3 -c \
  "import sys, json; [print(m['name']) for m in json.load(sys.stdin)['models']]"

# Pull the model if missing
curl -X POST http://192.168.30.111:11435/api/pull \
  -H "Content-Type: application/json" \
  -d '{"name": "gpt-oss:20b"}'
```

### Slow Response Times

- Check Mac Mini load: high memory usage from other models may slow inference
- Consider using a smaller model (e.g., `qwen3:4b-instruct` instead of `gpt-oss:20b`)
- Ensure only needed models are loaded (Ollama loads models on demand)

### Wrong Endpoint Format

Apps expecting OpenAI format need `/v1/` path, not `/api/`:
```
OpenAI format: http://192.168.30.111:11435/v1/chat/completions
Ollama native: http://192.168.30.111:11435/api/chat
```

Model naming also differs. Use Ollama model IDs with colon separators:
```
Correct: gpt-oss:20b, qwen3:4b-instruct, qwen3-vl:8b-instruct
Incorrect: openai/gpt-oss-20b, qwen/qwen3-4b-2507
```

---

## Verification Tests

### Test 1: Endpoint Reachability

```bash
for port in 11434 11435 11436; do
  echo -n "Port $port: "
  curl -sf http://192.168.30.111:${port}/api/tags > /dev/null && echo "OK" || echo "FAIL"
done
```

Expected:
- All required ports print `OK`.

If failed:
- Check network reachability to `192.168.30.111` and service status on Mac Mini.

### Test 2: Model Invocation

```bash
curl -sS -X POST http://192.168.30.111:11435/api/chat \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-oss:20b","messages":[{"role":"user","content":"ping"}],"stream":false}'
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
  wget -qO- http://192.168.30.111:11435/api/tags
```

Expected:
- Returns model JSON from the endpoint.

If unclear:
- Run `ping 192.168.30.111` from a reachable node or diagnostic pod.

### Diagnose Example 2: Model Not Found in App

```bash
curl -s http://192.168.30.111:11435/api/tags | python3 -c \
  "import sys, json; [print(m['name']) for m in json.load(sys.stdin).get('models',[])]"
```

Expected:
- Requested model appears exactly with Ollama naming format.

If unclear:
- Pull the model on the target Ollama instance and retest.

---

## Health Check

```bash
# Check all Ollama instances are reachable
for port in 11434 11435 11436; do
  echo -n "Port $port: "
  curl -sf http://192.168.30.111:${port}/api/tags > /dev/null \
    && echo "OK" || echo "UNREACHABLE"
done

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
