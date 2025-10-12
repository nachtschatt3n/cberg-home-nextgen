# k8s-self-ai-ops v1.0.1 Deployment Summary

## ✅ Deployment Complete

k8s-self-ai-ops v1.0.1 has been successfully configured for deployment to your cluster via Flux GitOps.

### What Was Deployed

**Source**: https://github.com/nachtschatt3n/k8s-self-ai-ops (v1.0.1)
**Target Namespace**: `ai`
**Method**: Flux GitOps with SOPS-encrypted secrets

### Files Created

```
kubernetes/apps/ai/k8s-mcp-server/
├── README.md                    # Integration documentation
├── DEPLOYMENT_SUMMARY.md        # This file
├── ks.yaml                      # Flux Kustomization
└── app/
    ├── kustomization.yaml       # App resources
    └── secret.sops.yaml         # SOPS-encrypted auth token

kubernetes/flux/meta/repositories/
└── k8s-self-ai-ops.yaml        # GitRepository definition

kubernetes/apps/ai/
└── kustomization.yaml          # Updated to include k8s-mcp-server
```

### Configuration Highlights

**GitRepository**:
- URL: `https://github.com/nachtschatt3n/k8s-self-ai-ops`
- Reference: `v1.0.1` (tag)
- Path: `./kubernetes` (only kubernetes directory is deployed)

**Namespace Handling**:
- External repo uses `ai-system` namespace
- Flux patches convert everything to `ai` namespace
- Skips creating namespace (already exists)

**Security**:
- Auth token SOPS-encrypted with age key
- Decrypted by Flux using `sops-age` secret
- Token: `GI6EWiGrGnOYg0kwLt75ixq18u2MXcbqhAr0ssiJTQM=` (encrypted in secret)

## 🚀 Next Steps

### 1. Push to Git

```bash
cd /Users/U709434/code/home/cberg-home-nextgen
git push origin main
```

### 2. Monitor Flux Deployment

```bash
# Watch Flux reconciliation
watch flux get kustomizations -A

# Specifically watch k8s-mcp-server
flux get kustomization k8s-mcp-server --watch

# Check GitRepository
flux get sources git k8s-self-ai-ops
```

### 3. Verify Deployment

```bash
# Check pods
kubectl get pods -n ai -l app=k8s-mcp-server

# Expected output:
# NAME                              READY   STATUS    RESTARTS   AGE
# k8s-mcp-server-xxxxxxxxxx-xxxxx   1/1     Running   0          2m

# Check logs
kubectl logs -n ai -l app=k8s-mcp-server -f

# Check service
kubectl get svc -n ai k8s-mcp-server
```

### 4. Test the MCP Server

```bash
# Port-forward to access locally
kubectl port-forward -n ai svc/k8s-mcp-server 8000:8000 &

# Test health endpoint
curl http://localhost:8000/health

# Expected: {"status":"healthy","kubernetes":true,"tools":25}

# List available tools
curl -H "Authorization: Bearer GI6EWiGrGnOYg0kwLt75ixq18u2MXcbqhAr0ssiJTQM=" \
  http://localhost:8000/tools | jq '.count'

# Expected: 25

# Test a simple tool
curl -X POST \
  -H "Authorization: Bearer GI6EWiGrGnOYg0kwLt75ixq18u2MXcbqhAr0ssiJTQM=" \
  -H "Content-Type: application/json" \
  -d '{"include_details": false}' \
  http://localhost:8000/tools/get_cluster_health | jq
```

## 📊 Monitoring

### Flux Status

```bash
# Overall Flux health
flux check

# k8s-mcp-server status
flux get kustomization k8s-mcp-server

# Secret deployment status
flux get kustomization k8s-mcp-server-secrets

# View reconciliation logs
flux logs --kind=Kustomization --name=k8s-mcp-server
```

### Kubernetes Resources

```bash
# All resources in ai namespace
kubectl get all -n ai -l app=k8s-mcp-server

# Detailed deployment status
kubectl describe deployment -n ai k8s-mcp-server

# Check events
kubectl get events -n ai --sort-by='.lastTimestamp' | grep k8s-mcp

# Check PVC for audit logs
kubectl get pvc -n ai k8s-mcp-server-audit
```

### Application Logs

```bash
# Real-time logs
kubectl logs -n ai -l app=k8s-mcp-server -f

# Logs with timestamps
kubectl logs -n ai -l app=k8s-mcp-server --timestamps=true

# Previous container logs (if crashed)
kubectl logs -n ai -l app=k8s-mcp-server --previous
```

## 🔧 Troubleshooting

### Deployment Not Starting

```bash
# Check Flux reconciliation
flux get kustomizations -A | grep k8s-mcp

# Force reconciliation
flux reconcile source git k8s-self-ai-ops --with-source
flux reconcile kustomization k8s-mcp-server

# Check for errors
flux logs --kind=Kustomization --name=k8s-mcp-server --level=error
```

### Secret Not Decrypted

```bash
# Verify SOPS secret exists
kubectl get secret -n flux-system sops-age

# If missing, check your age.key file
# The secret should contain your age private key

# Test decryption locally
cd /Users/U709434/code/home/cberg-home-nextgen
sops -d kubernetes/apps/ai/k8s-mcp-server/app/secret.sops.yaml
```

### Namespace Issues

The external repo uses `ai-system` but we deploy to `ai`. If you see namespace errors:

```bash
# Check if patches are applied
kubectl get kustomization -n flux-system k8s-mcp-server -o yaml | grep -A 20 patches

# Verify targetNamespace
kubectl get kustomization -n flux-system k8s-mcp-server -o yaml | grep targetNamespace
```

### Pod CrashLoopBackOff

```bash
# Check pod status
kubectl describe pod -n ai -l app=k8s-mcp-server

# Check logs for errors
kubectl logs -n ai -l app=k8s-mcp-server --previous

# Common issues:
# 1. RBAC permissions - check ServiceAccount
# 2. Can't reach Prometheus - verify MCP_PROMETHEUS_URL in ConfigMap
# 3. Missing dependencies - check dependsOn in Kustomization
```

## 🔄 Upgrading

To upgrade to a newer version:

```bash
# Edit the GitRepository
vim kubernetes/flux/meta/repositories/k8s-self-ai-ops.yaml

# Change ref.tag to new version
# Before: tag: v1.0.1
# After:  tag: v1.0.2

# Commit and push
git add kubernetes/flux/meta/repositories/k8s-self-ai-ops.yaml
git commit -m "feat(ai): Upgrade k8s-self-ai-ops to v1.0.2"
git push

# Force reconciliation
flux reconcile source git k8s-self-ai-ops --with-source
flux reconcile kustomization k8s-mcp-server
```

## 🔗 Integration Examples

### n8n HTTP Request Node

```javascript
// Configuration
URL: http://k8s-mcp-server.ai.svc:8000/tools/get_cluster_health
Method: POST
Authentication: None
Headers:
  Authorization: Bearer GI6EWiGrGnOYg0kwLt75ixq18u2MXcbqhAr0ssiJTQM=
  Content-Type: application/json
Body (JSON):
  {
    "include_details": true
  }
```

### Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "homelab": {
      "url": "http://k8s-mcp-server.ai.svc:8000",
      "headers": {
        "Authorization": "Bearer GI6EWiGrGnOYg0kwLt75ixq18u2MXcbqhAr0ssiJTQM="
      }
    }
  }
}
```

Then restart Claude Desktop and ask:
- "Check my homelab cluster health"
- "Show me any crashing pods"
- "Query prometheus for memory usage"

### Python Script

```python
import httpx

MCP_URL = "http://k8s-mcp-server.ai.svc:8000"
AUTH_TOKEN = "GI6EWiGrGnOYg0kwLt75ixq18u2MXcbqhAr0ssiJTQM="

headers = {
    "Authorization": f"Bearer {AUTH_TOKEN}",
    "Content-Type": "application/json"
}

# Get cluster health
response = httpx.post(
    f"{MCP_URL}/tools/get_cluster_health",
    headers=headers,
    json={"include_details": True}
)

print(response.json())
```

## 📝 Important Notes

1. **Auth Token Security**: The token is encrypted with SOPS in the repository. Never commit unencrypted tokens.

2. **Namespace Override**: The external repo deploys to `ai-system` but Flux patches convert it to `ai`. This is handled automatically.

3. **Public Repository**: The source repo is public, so no credentials are needed for GitRepository.

4. **Audit Logs**: The server creates audit logs in `/data/audit/operations.json` inside the pod, backed by a PVC.

5. **Rate Limiting**: Default is 30 operations per minute with 15-second cooldown between changes.

## 📚 Resources

- **Source Code**: https://github.com/nachtschatt3n/k8s-self-ai-ops
- **Main README**: kubernetes/apps/ai/k8s-mcp-server/README.md
- **External Docs**: https://github.com/nachtschatt3n/k8s-self-ai-ops/blob/main/README.md
- **Container Images**: ghcr.io/nachtschatt3n/k8s-self-ai-ops

---

**Deployment Status**: ✅ Ready to Push
**Next Action**: `git push origin main` and monitor Flux reconciliation

