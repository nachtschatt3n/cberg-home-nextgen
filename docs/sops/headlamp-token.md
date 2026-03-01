# SOP: Headlamp Short-Lived Token Generation

> Description: How to generate a short-lived cluster-admin token for Headlamp when manual kubectl or UI access is needed. Long-lived tokens are intentionally not stored in the repo.
> Version: `2026.03.01`
> Last Updated: `2026-03-01`
> Owner: `ops`

---

## 1) Description

Headlamp runs in in-cluster mode and authenticates all Kubernetes API calls via its own ServiceAccount (cluster-admin). Authentik forward auth protects the web UI. No long-lived token is stored in the repository.

This SOP covers generating a short-lived token on demand for:
- Pasting into the Headlamp UI on a new browser session
- Direct `kubectl` API calls using the headlamp SA identity
- Debugging cluster permissions as cluster-admin

- Scope: `monitoring/headlamp`
- Prerequisites: `kubectl` access to the cluster
- Out of scope: Changing RBAC or rotating the ServiceAccount itself

---

## 2) Overview

| Setting | Value |
|---------|-------|
| Namespace | `monitoring` |
| ServiceAccount | `headlamp` |
| ClusterRoleBinding | `headlamp-cluster-admin` → `cluster-admin` |
| RBAC source of truth | `kubernetes/apps/monitoring/headlamp/app/rbac.yaml` |
| Token type | Short-lived (via `kubectl create token`) — no static secret in repo |
| Web auth | Authentik forward auth (ingress annotations in `helmrelease.yaml`) |

---

## 3) Blueprints

N/A — tokens are ephemeral and not stored anywhere. The only declarative artifact is the RBAC:

```yaml
# kubernetes/apps/monitoring/headlamp/app/rbac.yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: headlamp
  namespace: monitoring
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: headlamp-cluster-admin
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: cluster-admin
subjects:
  - kind: ServiceAccount
    name: headlamp
    namespace: monitoring
```

---

## 4) Operational Instructions

### Generate a token

```bash
# Default: 1 hour (recommended for normal use)
kubectl create token headlamp -n monitoring --duration=1h

# Extended: up to 8 hours for long sessions
kubectl create token headlamp -n monitoring --duration=8h

# Short: 15 minutes for quick one-off access
kubectl create token headlamp -n monitoring --duration=15m
```

The token is printed to stdout. Copy and paste it into the Headlamp UI token prompt or use it directly with `kubectl`.

### Use the token with kubectl

```bash
TOKEN=$(kubectl create token headlamp -n monitoring --duration=1h)

# Query the cluster as the headlamp SA
kubectl --token="$TOKEN" get nodes
kubectl --token="$TOKEN" get pods -A
```

### Token expiry

Tokens expire automatically at the requested duration. No cleanup needed. Do not store tokens in files, environment files, or scripts.

---

## 5) Examples

### Example A: Browser session — paste token into Headlamp UI

```bash
# Generate and copy to clipboard (Linux)
kubectl create token headlamp -n monitoring --duration=1h | xclip -selection clipboard

# macOS
kubectl create token headlamp -n monitoring --duration=1h | pbcopy
```

Open `https://headlamp.<domain>`, sign in via Authentik, then paste the token when prompted.

### Example B: Debug cluster state with kubectl using headlamp SA

```bash
TOKEN=$(kubectl create token headlamp -n monitoring --duration=15m)
kubectl --token="$TOKEN" get helmreleases -A
kubectl --token="$TOKEN" get kustomizations -A
kubectl --token="$TOKEN" describe pod <pod-name> -n <namespace>
```

### Example C: Verify token claims before use

```bash
TOKEN=$(kubectl create token headlamp -n monitoring --duration=1h)

# Decode payload (no verification needed for inspection)
echo "$TOKEN" | cut -d. -f2 | base64 -d 2>/dev/null | python3 -m json.tool
```

Expected output includes `"sub": "system:serviceaccount:monitoring:headlamp"` and an `"exp"` timestamp.

---

## 6) Verification Tests

### Test 1: Token is accepted by the API server

```bash
TOKEN=$(kubectl create token headlamp -n monitoring --duration=5m)
kubectl --token="$TOKEN" auth whoami
```

Expected:
- Output shows `Username: system:serviceaccount:monitoring:headlamp`

If failed:
- Check that the `headlamp` ServiceAccount exists: `kubectl get sa headlamp -n monitoring`

### Test 2: Token has cluster-admin permissions

```bash
TOKEN=$(kubectl create token headlamp -n monitoring --duration=5m)
kubectl --token="$TOKEN" auth can-i list pods --all-namespaces
```

Expected:
- `yes`

If failed:
- Check ClusterRoleBinding: `kubectl get clusterrolebinding headlamp-cluster-admin -o yaml`

### Test 3: No long-lived token secret exists in cluster

```bash
kubectl get secret -n monitoring | grep headlamp
```

Expected:
- No secret of type `kubernetes.io/service-account-token` for headlamp appears

If failed:
- A long-lived secret was re-created. Delete it: `kubectl delete secret headlamp-token -n monitoring`
- Check if `token-secret.yaml` was re-added to the kustomization and revert via GitOps

---

## 7) Troubleshooting

| Symptom | Likely Cause | First Fix |
|---------|--------------|-----------|
| `error: unknown flag: --duration` | Old kubectl version | Upgrade kubectl to ≥ v1.24 |
| `Error from server (NotFound): serviceaccounts "headlamp" not found` | SA deleted or namespace wrong | Check `kubectl get sa -n monitoring` and verify rbac.yaml is applied |
| Token rejected by Headlamp UI | Token expired | Generate a new token |
| Headlamp UI not accessible | Authentik outpost down | Check `kubectl get pods -n kube-system \| grep outpost` |
| `Forbidden` when using token | ClusterRoleBinding missing | Check `kubectl get clusterrolebinding headlamp-cluster-admin` |

```bash
# Quick status check
kubectl get sa headlamp -n monitoring
kubectl get clusterrolebinding headlamp-cluster-admin
kubectl get pods -n monitoring -l app.kubernetes.io/name=headlamp
```

---

## 8) Diagnose Examples

### Diagnose Example 1: Token not working after generation

```bash
TOKEN=$(kubectl create token headlamp -n monitoring --duration=1h)

# Check token is well-formed
echo "$TOKEN" | tr '.' '\n' | wc -l
# Expected: 3 (header.payload.signature)

# Decode expiry
echo "$TOKEN" | cut -d. -f2 | base64 -d 2>/dev/null | python3 -c "
import sys, json, datetime
p = json.load(sys.stdin)
exp = datetime.datetime.fromtimestamp(p['exp'])
print(f'Expires: {exp}')
print(f'Subject: {p[\"sub\"]}')
"

# Test API access
kubectl --token="$TOKEN" auth whoami
```

Expected:
- 3 parts, valid expiry in the future, subject matches headlamp SA

If unclear:
- Check API server logs: `kubectl logs -n kube-system -l component=kube-apiserver --tail=50`

### Diagnose Example 2: Headlamp pod can't reach API server

```bash
# Check pod status
kubectl get pods -n monitoring -l app.kubernetes.io/name=headlamp

# Check pod logs
kubectl logs -n monitoring -l app.kubernetes.io/name=headlamp --tail=50

# Verify in-cluster SA token is mounted
kubectl exec -n monitoring deployment/headlamp -- ls /var/run/secrets/kubernetes.io/serviceaccount/
```

Expected:
- Files: `ca.crt`, `namespace`, `token`
- The mounted `token` is automatically rotated by Kubernetes (short-lived)

If unclear:
- Check if the ServiceAccount exists and is healthy: `kubectl describe sa headlamp -n monitoring`

---

## 9) Health Check

```bash
# SA and RBAC present
kubectl get sa headlamp -n monitoring
kubectl get clusterrolebinding headlamp-cluster-admin

# No long-lived static token secret exists
kubectl get secret -n monitoring | grep headlamp

# Headlamp pod running
kubectl get pods -n monitoring -l app.kubernetes.io/name=headlamp

# In-cluster SA token correctly mounted in pod
kubectl exec -n monitoring deployment/headlamp -- cat /var/run/secrets/kubernetes.io/serviceaccount/namespace
```

Expected:
- SA and CRB present
- No `kubernetes.io/service-account-token` secret for headlamp
- Pod is `Running`
- Namespace file contains `monitoring`

---

## 10) Security Check

```bash
# Confirm no long-lived token secret in repo
grep -r "kubernetes.io/service-account-token" kubernetes/apps/monitoring/headlamp/

# Confirm no long-lived token secret in cluster
kubectl get secret -n monitoring -o json | python3 -c "
import sys, json
secrets = json.load(sys.stdin)['items']
sa_tokens = [s['metadata']['name'] for s in secrets if s['type'] == 'kubernetes.io/service-account-token']
print('Long-lived SA tokens:', sa_tokens or 'none')
"

# Confirm Authentik forward auth still present on ingress
kubectl get ingress -n monitoring headlamp -o jsonpath='{.metadata.annotations.nginx\.ingress\.kubernetes\.io/auth-url}'
```

Expected:
- No matches in repo for `service-account-token` under headlamp
- `Long-lived SA tokens: none`
- Auth URL points to the Authentik outpost

---

## 11) Rollback Plan

There is no rollback needed — token generation is read-only and ephemeral. If access is lost entirely:

```bash
# Emergency: generate token as cluster-admin via a privileged SA
kubectl create token headlamp -n monitoring --duration=1h

# If the headlamp SA or CRB was accidentally deleted, re-apply from repo
kubectl apply -f kubernetes/apps/monitoring/headlamp/app/rbac.yaml
```

If Authentik is down and you cannot reach the Headlamp UI:

```bash
# Port-forward directly, bypassing ingress auth
kubectl port-forward -n monitoring svc/headlamp 4466:80 &
# Then access http://localhost:4466 and paste the generated token
```

---

## 12) References

- RBAC manifest: `kubernetes/apps/monitoring/headlamp/app/rbac.yaml`
- HelmRelease: `kubernetes/apps/monitoring/headlamp/app/helmrelease.yaml`
- Authentik SOP: `docs/sops/authentik.md`
- Kubernetes token docs: https://kubernetes.io/docs/reference/access-authn-authz/service-accounts-admin/#bound-service-account-tokens

---

## Version History

- `2026.03.01`: Initial SOP. Long-lived token secret removed from repo; short-lived token workflow documented.
