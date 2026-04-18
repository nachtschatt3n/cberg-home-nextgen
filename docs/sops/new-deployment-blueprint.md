# SOP: New Deployment Blueprint

> Standard Operating Procedure for onboarding and rolling out new applications in this repository.
> Reference: `docs/applications.md`, `docs/infrastructure.md`, `docs/sops/homepage-integration.md`, `docs/sops/longhorn.md`, `docs/sops/monitoring.md`, `docs/sops/sops-encryption.md`.
> Description: Default deployment blueprint that combines namespace rules, Homepage integration, storage rules, monitoring requirements, Flux webhook GitOps workflow, and code standards.
> Version: `2026.04.18`
> Last Updated: `2026-04-18`
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
| AlertManager | Every new app must have a PrometheusRule in `kubernetes/apps/monitoring/kube-prometheus-stack/app/` covering pod readiness, crash looping, and restarts |
| Elasticsearch | Every new app's logs must be verified present in Elasticsearch after first deployment (`resource.attributes.k8s.namespace.name` + `resource.attributes.k8s.container.name` query on `logs-generic-default`) |
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
- Mandatory: `kubernetes/apps/monitoring/kube-prometheus-stack/app/{app}-alerts.yaml` — PrometheusRule for AlertManager

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

kubernetes/apps/monitoring/kube-prometheus-stack/app/
  {app}-alerts.yaml         # PrometheusRule — mandatory for every new app
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

**Longhorn volume naming rule** (mandatory for `longhorn-static`):

- **Default: use `longhorn` (dynamic).** PVCs get auto-generated UUID PV names — this is fine for app data that can be recreated from backup.
- **Use `longhorn-static` when you want a stable, speaking volume name** (reviewed/grep-able/backup-auditable). The PV **must not** be a UUID — it must match the PVC's `volumeName` exactly.
- **The Longhorn Volume, the PV, the PVC's `volumeName`, the PV's `volumeHandle`, and the PVC name must all be the SAME speaking identifier.** Convention: `{app}-{purpose}-data` (e.g. `pgadmin-data`, `superset-postgresql-data`).

Three-file pattern when using `longhorn-static` (see `kubernetes/apps/databases/pgadmin/app/` or `kubernetes/apps/databases/superset/app/` for working references):

```yaml
# longhorn-volume.yaml — the physical Longhorn volume (create first)
apiVersion: longhorn.io/v1beta2
kind: Volume
metadata:
  name: {app}-data       # speaking name, NOT a UUID
  namespace: storage
spec:
  size: "21474836480"    # bytes
  numberOfReplicas: 2
  dataEngine: v1
  accessMode: rwo
  frontend: blockdev
---
# pv.yaml — Kubernetes PersistentVolume bound to the Longhorn volume
apiVersion: v1
kind: PersistentVolume
metadata:
  name: {app}-data       # MUST match Longhorn volume name
spec:
  capacity: { storage: 20Gi }
  storageClassName: longhorn-static
  accessModes: [ReadWriteOnce]
  persistentVolumeReclaimPolicy: Retain
  csi:
    driver: driver.longhorn.io
    fsType: ext4
    volumeHandle: {app}-data   # MUST match Longhorn volume name (anchor 3)
    volumeAttributes: { numberOfReplicas: "2", staleReplicaTimeout: "30" }
---
# data-pvc.yaml — PVC bound by name to the PV
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: {app}-data
  namespace: {namespace}
spec:
  storageClassName: longhorn-static
  volumeName: {app}-data   # MUST match PV name
  accessModes: [ReadWriteOnce]
  resources: { requests: { storage: 20Gi } }
```

Never skip the speaking name and fall back to a UUID PV — that defeats the purpose of `longhorn-static` (manual control, visibility, backup naming).

---

Authentik SSO blueprint (mandatory for apps with user login):

All Authentik providers **must** be declared in the SOPS-encrypted blueprint ConfigMap at `kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml`. **UI-only configuration is forbidden** — it is not reviewable, not restorable, and drifts silently.

- **Forward-auth (proxy) providers** for apps without their own auth (e.g. Longhorn UI, Prometheus): use `authentik_providers_proxy.proxyprovider`. See existing `esphome-blueprint.yaml`, `longhorn-forward-auth-blueprint.yaml` as templates.
- **OAuth2/OIDC providers** for apps with their own user model (e.g. Grafana, Superset, pgAdmin): use `authentik_providers_oauth2.oauth2provider`. See existing `grafana-oauth2-blueprint.yaml`, `superset-oauth2-blueprint.yaml` as templates.

OAuth2 blueprint entry shape:

```yaml
- id: {app}-oauth2-provider
  model: authentik_providers_oauth2.oauth2provider
  state: present
  identifiers:
    name: {app}                    # upsert target — matches existing UI provider if present
  attrs:
    name: {app}
    client_id: <same as in app secret>
    client_secret: <same as in app secret — SOPS protects this ConfigMap>
    client_type: confidential
    authorization_flow: "0cdf1b8c-88f9-4b90-a063-a14e18192f74"   # default-provider-authorization-implicit-consent
    invalidation_flow:  "b8a97e00-f02f-48d9-b854-b26bf837779c"   # default-provider-invalidation-flow
    redirect_uris:
      - matching_mode: strict
        url: "https://{app}.${SECRET_DOMAIN}/<callback-path>"
    signing_key: !Find [authentik_crypto.certificatekeypair, [name, "authentik Self-signed Certificate"]]
    property_mappings:
      - !Find [authentik_providers_oauth2.scopemapping, [managed, "goauthentik.io/providers/oauth2/scope-openid"]]
      - !Find [authentik_providers_oauth2.scopemapping, [managed, "goauthentik.io/providers/oauth2/scope-email"]]
      - !Find [authentik_providers_oauth2.scopemapping, [managed, "goauthentik.io/providers/oauth2/scope-profile"]]
- id: {app}-application
  model: authentik_core.application
  state: present
  identifiers:
    slug: {app}
  attrs:
    name: {App display name}
    slug: {app}
    provider: !KeyOf {app}-oauth2-provider
    meta_launch_url: "https://{app}.${SECRET_DOMAIN}"
    meta_icon: "https://raw.githubusercontent.com/walkxcode/dashboard-icons/main/png/{app}.png"
```

**Keep `client_secret` synchronized** between the blueprint (source of truth) and the app's own SOPS Secret (runtime config). When rotating, update BOTH in the same commit.

**Per-app redirect URI paths** (common patterns — match what the chart/app expects):
- Grafana: `/login/generic_oauth`
- pgAdmin: `/oauth2/callback`
- Superset: `/oauth-authorized/authentik`

Using `state: present` with `identifiers.name` makes the blueprint idempotent — it upserts an existing UI-created provider in place rather than duplicating. No data loss.

---

## Operational Instructions

1. Choose target namespace and app path based on `docs/applications.md`.
2. Create `kubernetes/apps/{namespace}/{app}/` with `ks.yaml` and `app/` manifests.
3. Define app deployment (`helmrelease.yaml`) and wire it into `kustomization.yaml`.
4. Create secrets as `*.sops.yaml` and encrypt in repository path before commit.
5. Configure storage class:
   - `longhorn` for normal app/stateful workloads (UUID PV names acceptable).
   - `longhorn-static` for stable speaking names — write all three files (`longhorn-volume.yaml`, `pv.yaml`, `{app}-data-pvc.yaml`) with the **same speaking identifier** (Longhorn Volume name = PV name = PV `volumeHandle` = PVC `volumeName` = PVC name). Never use UUIDs. See the Storage blueprint section above and `kubernetes/apps/databases/pgadmin/app/` for a reference.
6. Configure ingress and Homepage metadata for user-facing web apps (annotations + label).
7. If the app has user login, declare the Authentik provider in the blueprint ConfigMap (`kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml`):
   - Forward-auth proxy providers for apps without their own auth.
   - OAuth2/OIDC providers for apps with their own user model.
   - Add a new `*-blueprint.yaml` key per the Authentik SSO blueprint section above. `client_secret` lives in the SOPS ConfigMap AND in the app's own SOPS Secret — keep both in sync.
   - Never configure providers via the Authentik UI only — blueprints are authoritative.
8. Add monitoring coverage:
   - Ensure app health endpoints/probes are set.
   - Add `ServiceMonitor` when required.
   - Confirm logs/events are observable.
9. Create AlertManager PrometheusRule (mandatory):
   - Add `kubernetes/apps/monitoring/kube-prometheus-stack/app/{app}-alerts.yaml`.
   - Include rules for: pod not ready (critical, 5m), crash looping (critical, 5m), pod restarted (warning, 1m).
   - Required labels: `release: kube-prometheus-stack`, `app.kubernetes.io/name: kube-prometheus-stack`, `app.kubernetes.io/part-of: kube-prometheus-stack`.
   - Register in `kubernetes/apps/monitoring/kube-prometheus-stack/app/kustomization.yaml`.
   - See `kubernetes/apps/monitoring/kube-prometheus-stack/app/anythingllm-alerts.yaml` as reference.
10. Verify Elasticsearch log ingestion (mandatory):
   - edot-collector ships all pod logs automatically — no config change needed.
   - After first deployment, confirm logs are present via Kibana (`logs-generic-default` data stream, filter by `resource.attributes.k8s.namespace.name` and `resource.attributes.k8s.container.name`).
   - Or query directly: `curl -sk -u "elastic:$ES_PASS" "https://localhost:9200/logs-generic-default/_count" -d '{"query":{"bool":{"must":[{"match":{"resource.attributes.k8s.namespace.name":"{namespace}"}},{"match":{"resource.attributes.k8s.container.name":"{app}"}}]}}}'`
11. Run local validation commands:

```bash
task template:configure -- --strict
kubeconform -summary -fail-on error kubernetes/apps/{namespace}/{app}
```

12. Commit and push changes to trigger Flux webhook flow:

```bash
git add kubernetes/apps/{namespace}/{app}/ docs/applications.md
git commit -m "feat({app}): deploy to {namespace}"
git push
```

13. Validate webhook-driven GitOps execution (no manual reconcile):

```bash
kubectl get receiver github-receiver -n flux-system
kubectl get events -n flux-system --sort-by='.lastTimestamp' | tail -30
flux get kustomizations -A
flux get helmreleases -A
```

14. Run compliance and health check runbooks to ensure proper integration:

```bash
python3 runbooks/doc-check.py
python3 runbooks/check-all-versions.py
./runbooks/health-check.sh
```

15. Execute Verification Tests, Health Check, and Security Check sections below.

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

### Test 7: AlertManager PrometheusRule Is Active

```bash
kubectl get prometheusrule -n monitoring {app}-alerts
kubectl get prometheusrule {app}-alerts -n monitoring -o jsonpath='{.spec.groups[*].rules[*].alert}' | tr ' ' '\n'
```

Expected:
- PrometheusRule exists in the `monitoring` namespace.
- At minimum: `*PodNotReady`, `*PodCrashLooping`, `*PodRestarted` alerts are defined.
- Label `release: kube-prometheus-stack` is present (required for Prometheus discovery).

Failure hint:
- Create `kubernetes/apps/monitoring/kube-prometheus-stack/app/{app}-alerts.yaml` and register in its `kustomization.yaml`.

### Test 8: Elasticsearch Log Ingestion Verified

```bash
ES_PASS=$(kubectl get secret -n monitoring elasticsearch-es-elastic-user -o jsonpath='{.data.elastic}' | base64 -d)
kubectl port-forward -n monitoring svc/elasticsearch-es-http 9200:9200 &
sleep 5
curl -sk -u "elastic:$ES_PASS" "https://localhost:9200/logs-generic-default/_count" \
  -H "Content-Type: application/json" \
  -d '{"query":{"bool":{"must":[{"match":{"resource.attributes.k8s.namespace.name":"{namespace}"}},{"match":{"resource.attributes.k8s.container.name":"{app}"}}]}}}'
kill %1
```

Expected:
- `count` field is greater than 0 (logs are present in Elasticsearch).
- No config changes needed — edot-collector ships all pod logs automatically.

Failure hint:
- Check edot-collector Deployment health in `monitoring` namespace.
- Verify no log exclusion annotation on the pod.

### Test 9: Application Inventory Registration

```bash
python3 runbooks/doc-check.py | rg -A 5 "Section 3: Application Documentation"
```

Expected:
- The new app is correctly listed in `docs/applications.md` and passed the documentation check.

Failure hint:
- Add the app entry to `docs/applications.md` following the existing format.

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
| No AlertManager alerts for app | Missing PrometheusRule or wrong label | Create `{app}-alerts.yaml` with `release: kube-prometheus-stack` label |
| Logs missing in Kibana | edot-collector issue or pod excluded | Check edot-collector Deployment in `monitoring` namespace and pod annotations |

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

```bash
# AlertManager: PrometheusRule exists and is loaded
kubectl get prometheusrule -n monitoring {app}-alerts
# Elasticsearch: logs are present
ES_PASS=$(kubectl get secret -n monitoring elasticsearch-es-elastic-user -o jsonpath='{.data.elastic}' | base64 -d)
kubectl port-forward -n monitoring svc/elasticsearch-es-http 9200:9200 &>/dev/null &
sleep 5 && curl -sk -u "elastic:$ES_PASS" "https://localhost:9200/logs-generic-default/_count" -H "Content-Type: application/json" -d '{"query":{"bool":{"must":[{"match":{"resource.attributes.k8s.namespace.name":"{namespace}"}},{"match":{"resource.attributes.k8s.container.name":"{app}"}}]}}}' && kill %1 2>/dev/null
```

Quality criteria:
- Flux resources for the app are ready.
- Workload pods are healthy and stable.
- No unresolved warning-event trend.
- Stateful storage is bound and healthy.
- PrometheusRule `{app}-alerts` exists in `monitoring` namespace.
- Elasticsearch log count is greater than 0.

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
| `2026.03.11` | `2026-03-11` | Add mandatory AlertManager PrometheusRule and Elasticsearch log verification steps |
| `2026.04.16` | `2026-04-16` | Update logging references from fluent-bit to edot-collector / OTel field mappings |
| `2026.04.18` | `2026-04-18` | Add speaking-name rule for `longhorn-static` volumes; mandate Authentik provider declarations via SOPS-encrypted blueprint ConfigMap (forward-auth + OAuth2/OIDC) |
