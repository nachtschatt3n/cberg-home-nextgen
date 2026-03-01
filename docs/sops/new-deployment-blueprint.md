# SOP: New Deployment Blueprint

> Standard Operating Procedure for onboarding and rolling out new applications in this repository.
> Reference: `docs/applications.md`, `docs/infrastructure.md`, `docs/sops/homepage-integration.md`, `docs/sops/longhorn.md`, `docs/sops/monitoring.md`, `docs/sops/sops-encryption.md`.
> Description: Default deployment blueprint that combines namespace rules, Homepage integration, storage rules, monitoring requirements, Flux webhook GitOps workflow, and code standards.
> Version: `2026.03.01`
> Last Updated: `2026-03-01`
> Owner: `Platform`

---

## Description

This SOP is the default process for deploying a new app into the cluster.
It defines where the app should live, how it should be configured, and how to verify that the rollout worked.

- Scope: `kubernetes/apps/**` new app onboarding and rollout updates.
- Prerequisites: Git access, cluster read access (`kubectl`, `flux`), SOPS/age configured.
- Out of scope: One-off emergency hotfixes applied directly to the cluster.

---

## Overview

| Setting | Standard |
|---------|----------|
| GitOps trigger | Push to GitHub, then Flux webhook receiver triggers reconciliation |
| Manual reconcile | Not part of default flow for this SOP |
| Namespace placement | Follow existing namespace model in `docs/applications.md` and `docs/infrastructure.md` |
| App structure | `kubernetes/apps/{namespace}/{app}/` with `ks.yaml` + `app/` manifests |
| Secrets | Must be SOPS-encrypted (`*.sops.yaml`) before commit |
| Storage | Use `longhorn` by default; use `longhorn-static` only for explicitly managed volumes |
| Homepage | All user-facing web apps must include Homepage annotations + label |
| Monitoring | Every new app must have rollout health checks and logs/events verification |
| Code standards | 2-space indentation (except Python/Shell at 4), kebab-case files/dirs, snake_case vars/functions |

Namespace rules:
- Prefer existing namespaces by domain (`office`, `monitoring`, `home-automation`, `media`, etc.).
- Do not create a new namespace unless existing boundaries are clearly insufficient.
- Keep app folder and namespace aligned: `kubernetes/apps/{namespace}/{app}/`.

Common namespace mapping:
- `home-automation`: Smart-home services and integrations.
- `office`: Productivity/document services.
- `monitoring`: Observability stack and monitoring tools.
- `databases`: Shared database engines and DB UIs.
- `media`, `download`, `ai`, `network`: Domain-specific app workloads.
- `kube-system`, `flux-system`, `storage`, `cert-manager`: Platform/system components.

Flux rules:
- Do not run direct `kubectl apply` for app changes.
- Do not use `flux reconcile` in this default rollout SOP.
- Use git commit + push and validate webhook-driven reconciliation.
- Monitor reconciliation events in `flux-system`.

Code standards:
- Use relative imports for local files and absolute imports for standard libraries.
- Use LF line endings.
- Use 2-space indentation except Python/Shell files (4 spaces).
- Prefer YAML schemas for configuration.
- Use JSON schema only where YAML schema is not practical.
- Use kebab-case for files/directories and snake_case for variables/functions.
- Use Kubernetes logs/events for debugging instead of ad-hoc console output in manifests/scripts.
- Never commit plaintext secrets; use `*.sops.yaml` with age encryption.

---

## Blueprints

Declarative source of truth:
- `kubernetes/apps/{namespace}/{app}/ks.yaml`
- `kubernetes/apps/{namespace}/{app}/app/kustomization.yaml`
- `kubernetes/apps/{namespace}/{app}/app/helmrelease.yaml`
- Optional: `secret.sops.yaml`, `pvc.yaml`, `servicemonitor.yaml`, ingress resources

Minimal new app blueprint:

```text
kubernetes/apps/{namespace}/{app}/
  ks.yaml
  app/
    kustomization.yaml
    helmrelease.yaml
    secret.sops.yaml        # if credentials are needed
    pvc.yaml                # if persistent storage is needed
    servicemonitor.yaml     # if custom monitoring target is needed
```

Ingress/Homepage metadata blueprint:

```yaml
annotations:
  gethomepage.dev/enabled: "true"
  gethomepage.dev/name: "My App"
  gethomepage.dev/group: "Office"
  gethomepage.dev/icon: "my-app.png"
  gethomepage.dev/description: "Short app description"
labels:
  gethomepage.dev/enabled: "true"
```

Storage blueprint:

```yaml
spec:
  storageClassName: longhorn
```

Use `longhorn-static` only when a pre-created, manually managed volume is required.

---

## Operational Instructions

1. Choose target namespace and app path based on `docs/applications.md`.
2. Create `kubernetes/apps/{namespace}/{app}/` with `ks.yaml` and `app/` manifests.
3. Define app deployment (`helmrelease.yaml`) and wire it into `kustomization.yaml`.
4. Create secrets as `*.sops.yaml` and encrypt in repository path before commit.
5. Configure storage class:
   - `longhorn` for normal app/stateful workloads.
   - `longhorn-static` only for explicit pre-provisioned volume workflows.
6. Configure ingress and Homepage metadata for user-facing web apps (annotations + label).
7. Add monitoring coverage:
   - Ensure app health endpoints/probes are set.
   - Add `ServiceMonitor` when required.
   - Confirm logs/events are observable.
8. Run local validation commands:

```bash
task template:configure -- --strict
kubeconform -summary -fail-on error kubernetes/apps/{namespace}/{app}
```

9. Commit and push changes to trigger Flux webhook flow:

```bash
git add kubernetes/apps/{namespace}/{app}/ docs/applications.md
git commit -m "feat({app}): deploy to {namespace}"
git push
```

10. Validate webhook-driven GitOps execution (no manual reconcile):

```bash
kubectl get receiver github-receiver -n flux-system
kubectl get events -n flux-system --sort-by='.lastTimestamp' | tail -30
flux get kustomizations -A
flux get helmreleases -A
```

11. Execute Verification Tests, Health Check, and Security Check sections below.

---

## Examples

### Example 1: New Internal Web App in `office`

```bash
mkdir -p kubernetes/apps/office/my-app/app
# Add ks.yaml, app/kustomization.yaml, app/helmrelease.yaml
# Add ingress with Homepage metadata and className: internal
# Add secret.sops.yaml if needed
```

### Example 2: Stateful App with Manual Volume Control

```yaml
# pvc.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: my-app-config
  namespace: office
spec:
  accessModes: [ReadWriteOnce]
  resources:
    requests:
      storage: 10Gi
  storageClassName: longhorn-static
  volumeName: my-app-config
```

Use this only after creating the matching Longhorn volume and PV.

---

## Verification Tests

### Test 1: Flux Webhook Path Is Healthy

```bash
kubectl get receiver github-receiver -n flux-system -o yaml | rg "name:|Ready|secretRef"
kubectl get events -n flux-system --sort-by='.lastTimestamp' | tail -30
```

Expected:
- Receiver exists and is ready.
- Recent events show source/kustomization activity after push.

Failure hint:
- Check webhook token secret and source-controller logs in `flux-system`.

### Test 2: Kustomization and HelmRelease Ready

```bash
flux get kustomizations -A | rg "{app}|True|Ready"
flux get helmreleases -A | rg "{app}|True|Ready"
```

Expected:
- Target app resources report ready.

Failure hint:
- Inspect `kubectl describe` and controller logs for failed dependencies or values errors.

### Test 3: Workload Rollout Succeeded

```bash
kubectl get deploy,sts -n {namespace}
kubectl get pods -n {namespace}
```

Expected:
- Desired replicas are available.
- Pods are `Running` (or `Completed` for jobs).

Failure hint:
- Check pod events and container logs.

### Test 4: Homepage Registration Is Correct

```bash
kubectl get ingress {ingress-name} -n {namespace} -o yaml | rg "gethomepage.dev/"
kubectl logs -n default -l app.kubernetes.io/name=homepage --tail=200
```

Expected:
- Ingress contains required Homepage annotations and label.
- No relevant discovery errors in Homepage logs.

Failure hint:
- Verify `gethomepage.dev/enabled: "true"` exists in both annotations and labels.

### Test 5: Storage Binding Is Healthy (If Stateful)

```bash
kubectl get pvc -n {namespace}
kubectl get pv | rg "{pvc-name}|Bound"
kubectl get volume -n storage
```

Expected:
- PVC is `Bound` and Longhorn volume is healthy.

Failure hint:
- Validate storage class, access mode, and volume handle alignment.

### Test 6: Monitoring Signals Are Present

```bash
kubectl get events -n {namespace} --field-selector type=Warning --sort-by='.lastTimestamp' | tail -20
kubectl logs -n {namespace} {pod-name} --tail=100 | rg -i "error|fail|panic"
kubectl get servicemonitor -n {namespace}
```

Expected:
- No unresolved warning events.
- No recurring startup/runtime errors.
- `ServiceMonitor` exists when app requires custom scraping.

Failure hint:
- Fix probe endpoints, service labels/selectors, or container config and redeploy.

---

## Troubleshooting

| Symptom | Likely Cause | Action |
|---------|--------------|--------|
| Push completed but app did not update | Webhook or source sync issue | Check `Receiver`, Flux events, and source-controller logs |
| HelmRelease not ready | Invalid values/chart mismatch | `kubectl describe helmrelease {app} -n {namespace}` and fix values |
| App running but missing from Homepage | Missing/misplaced metadata | Add Homepage annotations and label to ingress |
| PVC pending | Wrong storage class or missing static volume | Validate `longhorn`/`longhorn-static` workflow and PV binding |
| Pods crash looping | Secret/config/runtime mismatch | Check pod events/logs and verify SOPS secrets |
| Metrics missing | No ServiceMonitor or label mismatch | Validate ServiceMonitor selector and service labels |

---

## Diagnose Examples

### Diagnose Example 1: Webhook Trigger Did Not Apply Changes

```bash
kubectl get receiver github-receiver -n flux-system -o yaml | rg "Ready|secretRef"
kubectl get events -n flux-system --sort-by='.lastTimestamp' | tail -30
kubectl logs -n flux-system deployment/source-controller --tail=100
```

Interpretation:
- If receiver is not ready or events are stale, webhook processing is broken.
- Fix receiver secret/token or GitHub webhook configuration, then push a new commit.

### Diagnose Example 2: App Deployed but Missing in Homepage

```bash
kubectl get ingress {ingress-name} -n {namespace} -o yaml | rg "gethomepage.dev/"
kubectl logs -n default -l app.kubernetes.io/name=homepage --tail=200 | rg -i "{app}|error"
```

Interpretation:
- Missing label or group mismatch blocks discovery.
- Add required metadata, commit, and push for webhook-triggered update.

---

## Health Check

Run after rollout completes:

```bash
flux get kustomizations -A
flux get helmreleases -A
kubectl get pods -n {namespace}
kubectl get events -n {namespace} --field-selector type=Warning --sort-by='.lastTimestamp' | tail -20
kubectl get pvc -n {namespace}
```

Quality criteria:
- Flux resources for the app are ready.
- Workload pods are healthy and stable.
- No unresolved warning-event trend.
- Stateful storage is bound and healthy.

---

## Security Check

Run for every new deployment:

```bash
# Verify secrets are encrypted
rg -n "kind: Secret|stringData:" kubernetes/apps/{namespace}/{app}/app
rg --files kubernetes/apps/{namespace}/{app}/app | rg "secret.*\.sops\.yaml$"

# Ensure no obvious plaintext secrets were introduced
rg -n "password:|token:|api[_-]?key:|secret:" kubernetes/apps/{namespace}/{app}/app --glob '!*.sops.yaml'

# Verify Flux webhook receiver remains authenticated
kubectl get receiver github-receiver -n flux-system -o yaml | rg "secretRef"
```

Security criteria:
- Secret manifests are SOPS-encrypted.
- No plaintext credentials in non-SOPS files.
- Flux webhook receiver uses a `secretRef`.

---

## Rollback Plan

1. Revert the deployment commit in git:

```bash
git revert <commit-sha>
git push
```

2. Wait for normal webhook-driven Flux rollout (do not run manual reconcile in this SOP).
3. Validate previous version recovery:

```bash
flux get helmreleases -A
kubectl get pods -n {namespace}
```

4. If rollback involves stateful data, restore from Longhorn backup per `docs/sops/backup.md` and `docs/sops/longhorn.md`.

Rollback success criteria:
- Previous known-good app revision is active.
- Pods are healthy.
- Errors introduced by rollout are gone.

---

## References

- `docs/applications.md`
- `docs/infrastructure.md`
- `docs/sops/homepage-integration.md`
- `docs/sops/longhorn.md`
- `docs/sops/monitoring.md`
- `docs/sops/sops-encryption.md`

---

## Version History

| Version | Date | Change |
|---------|------|--------|
| `2026.03.01` | `2026-03-01` | Initial version |
