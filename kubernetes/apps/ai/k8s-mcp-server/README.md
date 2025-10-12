# k8s-mcp-server - Self-Healing AI Operations

This integrates the [k8s-self-ai-ops](https://github.com/nachtschatt3n/k8s-self-ai-ops) project (v1.0.1) into the homelab cluster via Flux.

## Deployment

The deployment uses Flux to pull manifests from the external GitHub repository and applies them to the `ai` namespace.

### Components

**GitRepository**: `kubernetes/flux/meta/repositories/k8s-self-ai-ops.yaml`
- Points to: `https://github.com/nachtschatt3n/k8s-self-ai-ops`
- Version: `v1.0.1`
- Public repository (no credentials needed)

**Secrets**: `app/secret.sops.yaml`
- SOPS-encrypted authentication token
- Decrypted by Flux using the `sops-age` secret

**Kustomization**: `ks.yaml`
- Deploys manifests from external repo to `ai` namespace
- Depends on secrets being deployed first
- Health checks for deployment readiness

## Access

Once deployed, the MCP server will be available at:

- **Internal Service**: `http://k8s-mcp-server.ai.svc:8000`
- **WebSocket**: `ws://k8s-mcp-server.ai.svc:8001/ws`
- **Ingress** (if configured): Based on ingress settings in external repo

## Authentication

The auth token is stored in the SOPS-encrypted secret:
```bash
# View (requires SOPS_AGE_KEY_FILE to be set)
sops -d app/secret.sops.yaml

# Update token
sops app/secret.sops.yaml
# Edit MCP_AUTH_TOKEN value, save and exit
```

## Integration

### n8n

```javascript
const result = await $http.request({
  url: 'http://k8s-mcp-server.ai.svc:8000/tools/get_cluster_health',
  method: 'POST',
  headers: {
    'Authorization': 'Bearer YOUR_TOKEN_FROM_SECRET',
    'Content-Type': 'application/json'
  },
  body: { include_details: true }
});
```

### Claude Desktop

Add to your MCP config:
```json
{
  "mcpServers": {
    "homelab": {
      "url": "http://k8s-mcp-server.ai.svc:8000",
      "headers": {
        "Authorization": "Bearer YOUR_TOKEN_FROM_SECRET"
      }
    }
  }
}
```

## Monitoring

```bash
# Check deployment status
flux get kustomizations -A | grep k8s-mcp

# Check pods
kubectl get pods -n ai -l app=k8s-mcp-server

# View logs
kubectl logs -n ai -l app=k8s-mcp-server -f

# Port-forward for local access
kubectl port-forward -n ai svc/k8s-mcp-server 8000:8000
```

## Troubleshooting

### Secret not decrypted
```bash
# Check SOPS secret exists
kubectl get secret -n flux-system sops-age

# Check Flux logs
flux logs --kind=Kustomization --name=k8s-mcp-server-secrets
```

### Deployment issues
```bash
# Force reconciliation
flux reconcile source git k8s-self-ai-ops
flux reconcile kustomization k8s-mcp-server

# Check events
kubectl get events -n ai --sort-by='.lastTimestamp' | grep k8s-mcp
```

## Upgrading

To upgrade to a new version:

1. Update the tag in `kubernetes/flux/meta/repositories/k8s-self-ai-ops.yaml`
2. Commit and push
3. Flux will automatically reconcile

```bash
# Edit the file to update tag (e.g., v1.0.2)
vim kubernetes/flux/meta/repositories/k8s-self-ai-ops.yaml

# Commit
git add kubernetes/flux/meta/repositories/k8s-self-ai-ops.yaml
git commit -m "feat(ai): Update k8s-self-ai-ops to v1.0.2"
git push

# Force reconciliation if needed
flux reconcile source git k8s-self-ai-ops --with-source
```

## Links

- **Source Repository**: https://github.com/nachtschatt3n/k8s-self-ai-ops
- **Documentation**: https://github.com/nachtschatt3n/k8s-self-ai-ops/blob/main/README.md
- **Container Images**: ghcr.io/nachtschatt3n/k8s-self-ai-ops
