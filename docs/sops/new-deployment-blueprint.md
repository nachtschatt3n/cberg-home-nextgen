# SOP: New Deployment Blueprint

> Standard Operating Procedure for onboarding and rolling out new applications in this repository.
> Reference: `docs/applications.md`, `docs/infrastructure.md`, `docs/sops/homepage-integration.md`, `docs/sops/longhorn.md`, `docs/sops/monitoring.md`, `docs/sops/sops-encryption.md`.
> Description: Default deployment blueprint that combines namespace rules, Homepage integration, storage rules, monitoring requirements, Flux webhook GitOps workflow, and code standards.
> Version: `2026.04.19`
> Last Updated: `2026-04-19`
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

Three-file pattern when using `longhorn-static` (see `kubernetes/apps/databases/pgadmin/app/` or `kubernetes/apps/databases/superset/app/` for working references).

**Important — Longhorn Volume CR is NOT managed by Flux**: Flux app Kustomizations use `targetNamespace: {app-namespace}` which silently overrides the `namespace: storage` field in the `longhorn.io/v1beta2/Volume` manifest. This produces a duplicate/broken Volume in the app namespace that Longhorn does not manage. Therefore:

- Keep `longhorn-volume.yaml` in the app folder as version-controlled source.
- **Do NOT list it in `app/kustomization.yaml`.**
- Apply it ONCE manually against the `storage` namespace before the first reconcile:
  ```bash
  mise exec -- kubectl apply -f kubernetes/apps/{namespace}/{app}/app/longhorn-volume.yaml
  ```
- Flux then manages only `pv.yaml` and `data-pvc.yaml` (both correctly reside in the app namespace).

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
   - `longhorn-static` for stable speaking names — write all three files (`longhorn-volume.yaml`, `pv.yaml`, `data-pvc.yaml`) with the **same speaking identifier** (Longhorn Volume name = PV name = PV `volumeHandle` = PVC `volumeName` = PVC name). Never use UUIDs. List only `pv.yaml` + `data-pvc.yaml` in `app/kustomization.yaml`; apply the `Volume` CR manually with `kubectl apply -f .../longhorn-volume.yaml` (see the Storage blueprint section above for the full rationale and `kubernetes/apps/databases/pgadmin/app/` for a reference).
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

## Known Gotchas (learned the hard way)

Common pitfalls when onboarding a new Helm-based app into this cluster. Check these before debugging pod-level errors.

### 1. Bitnami images — always use `bitnamilegacy/*`

Bitnami deleted all pre-2026 image tags from `docker.io/bitnami/*` in late 2025; the tags live in `docker.io/bitnamilegacy/*` with identical content. Helm charts using Bitnami subcharts (postgresql, redis, mongodb, etc.) still reference the old tags and will fail with `image not found` unless overridden.

Fix pattern for any chart with Bitnami dependencies:
```yaml
postgresql:
  image:
    registry: docker.io
    repository: bitnamilegacy/postgresql
redis:
  image:
    registry: docker.io
    repository: bitnamilegacy/redis
```

### 2. Flux `targetNamespace` overrides per-manifest namespaces

Flux Kustomizations with `targetNamespace: {app-ns}` apply that namespace to **every resource** in the kustomize build, silently including resources whose manifest declares a different namespace (e.g. `longhorn.io/v1beta2/Volume` targeted at `storage`). Result: a broken duplicate in the app namespace that's never attached.

Workaround: keep cross-namespace resources (like Longhorn Volume CRs) OUT of `app/kustomization.yaml` and apply them once manually. Document the rule in the kustomization file itself with a comment explaining why it's absent.

### 3. Helm chart `configFromSecret` / `envFromSecret` replace defaults

Many charts (Apache Superset included) support these values to point the chart at an existing Secret for config/env. But using them **replaces** (not merges) the chart's default secret which often contains additional keys (e.g. the chart's bootstrap script, default env vars like `DB_HOST`). Result: init containers break with missing env vars or missing bootstrap files.

Two fix patterns:
- Use **`envFromSecrets`** (plural) to ADD your Secret alongside the chart's default. Chart's default secret stays intact.
- Or put everything the chart's default provided INTO your Secret (e.g. copy `DB_HOST`, `DB_PORT`, `REDIS_HOST`, etc. into your SOPS-encrypted Secret).

### 4. Python apps: install drivers into the actual runtime venv

Images packaged with a venv (e.g. `apache/superset:5.0.0` uses `/app/.venv`) need pip installs to target that venv, not the system Python. Modern Apache images use `uv` — not pip — and the venv may have NO pip binary inside.

Correct bootstrap pattern for Superset-like images:
```bash
uv pip install --python /app/.venv/bin/python <packages>
```

`pip install` alone → installs to system Python, invisible to the app.
`/app/.venv/bin/pip install` → fails if venv has no pip.

### 5. Celery/async workers: cap concurrency on fat nodes

Celery defaults worker concurrency to CPU count. On nuc14 nodes (18 threads), that's 18 processes × ~100-200MB each = 2-4GB just idle. Either:

- Set explicit `--concurrency=N` in the container's `command` (tune to actual workload)
- Bump memory `limits` to match worst case

Symptom: `Exit Code: 137 (OOMKilled)` on worker pods after the image loads.

### 6. Authentik blueprints — `copy-blueprints` init must wildcard

The Authentik HelmRelease in this cluster has a custom `copy-blueprints` init container that copies files from the ConfigMap volume (read-only) into an emptyDir (writable) that the worker mounts. If that init uses a hardcoded list of `cp` commands (as it did originally), adding a new blueprint YAML to the ConfigMap is silently ignored.

Correct init command:
```bash
cp /blueprints-source/*.yaml /blueprints/ || true
```

### 7. PrometheusRule for apps with init-db Jobs

`kube_pod_status_ready{condition="true"} == 0` matches **Completed** (Succeeded-phase) Job pods — they have `ready=false` by design. Without exclusion, alerts fire immediately after the init job finishes.

Correct expression:
```promql
sum by (namespace, pod) (
  kube_pod_status_ready{..., condition="true"}
  unless on(namespace, pod) kube_pod_status_phase{phase="Succeeded"} == 1
) == 0
```

### 8. Homepage icon verification

The repo convention uses `gethomepage.dev/icon: "foo.png"` which Homepage resolves against dashboard-icons repos — but not every app has a PNG there. Before committing, verify:

```bash
curl -sI "https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons@main/png/<name>.png" | head -1
```

If 404, fall back to:
- **Simple Icons**: `si-<simpleicons-slug>` (e.g. `si-apachesuperset`) — check at https://simpleicons.org
- **Material Design Icons**: `mdi-<name>` (e.g. `mdi-database-eye`) — check at https://pictogrammers.com/library/mdi

Keep the value bare (no `si-` quotes or URL) — Homepage's resolver handles the prefix.

### 9. Python WSGI apps behind TLS-terminating ingress

Flask, Django, and other WSGI apps see the request as `http://` internally because nginx-ingress terminates TLS at the edge. Any URL the app generates from the request (OAuth `redirect_uri`, absolute asset URLs, `url_for(_external=True)`, cookie `secure` flags) will come out wrong unless the app trusts the ingress's `X-Forwarded-*` headers.

Symptoms:
- OAuth provider returns "Redirect URI mismatch / invalid redirect_uri"
- Mixed-content warnings when app loads static assets
- Cookies not set or not sent (`secure` flag misdecided)
- Links in emails have wrong scheme/host

Fix per framework:

```python
# Flask / Flask-AppBuilder (Superset, Airflow)
ENABLE_PROXY_FIX = True
PROXY_FIX_CONFIG = {"x_for": 1, "x_proto": 1, "x_host": 1, "x_port": 1, "x_prefix": 1}
```

```python
# Django
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True
```

```python
# FastAPI / Uvicorn
# launch with --proxy-headers --forwarded-allow-ips='*'
```

```ruby
# Rails
config.force_ssl = true   # also trusts X-Forwarded-Proto by default
```

```yaml
# n8n / Node apps reading process.env
N8N_PROTOCOL: https
WEBHOOK_URL: https://n8n.${SECRET_DOMAIN}/
```

Our `internal` / `external` nginx ingress controllers already set `X-Forwarded-Proto`, `X-Forwarded-Host`, `X-Forwarded-For`, `X-Real-IP` — no ingress-side config needed.

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
| PodNotReady alert fires for Completed Job pods | `kube_pod_status_ready{condition="true"}` is 0 for Succeeded pods | Add `unless on(namespace, pod) kube_pod_status_phase{phase="Succeeded"} == 1` to the expr |
| `bitnami/*` image 404 pulling | Bitnami deleted pre-2026 tags from Docker Hub | Override `image.repository` to `bitnamilegacy/*` (same tag lives there) |
| Longhorn Volume CR created in wrong namespace | Flux `targetNamespace` overrode `namespace: storage` | Keep `longhorn-volume.yaml` out of `app/kustomization.yaml`; apply once manually with `kubectl apply` (see Storage blueprint section) |
| Authentik blueprint not picked up after ConfigMap change | `copy-blueprints` init hardcoded file list in authentik HelmRelease | Ensure init uses `cp /blueprints-source/*.yaml /blueprints/` wildcard — any new key in the ConfigMap is auto-copied |
| Homepage icon broken (404) | Dashboard-icons repo doesn't ship that app | Use `si-<name>` (Simple Icons) or `mdi-<name>` (Material Design) prefix — verify URL before committing with `curl -sI https://cdn.simpleicons.org/<name>` |
| Helm chart with bundled Postgres needs custom PG driver | Image lacks `psycopg2` / other connector | Use chart's `bootstrapScript` value — install into the runtime venv path (e.g. Superset: `uv pip install --python /app/.venv/bin/python psycopg2-binary==X`) |
| Chart `envFromSecret`/`configFromSecret` breaks chart's default config | Chart default secret is replaced (not merged) when these values are set | Use `envFromSecrets` (plural array) to add your secret on top of the chart's default |
| Celery-based app OOM-kills on fat nodes | Default concurrency = CPU count (18 on nuc14) → huge memory | Set explicit `--concurrency=N` in container `command` and bump memory limit |
| OAuth provider rejects `redirect_uri` with scheme mismatch (`http://` vs `https://`) | WSGI app sees request as `http://` internally; doesn't trust ingress's `X-Forwarded-Proto` | Enable framework's ProxyFix (Flask: `ENABLE_PROXY_FIX=True` + `PROXY_FIX_CONFIG`, Django: `SECURE_PROXY_SSL_HEADER`) — see Known Gotcha #9 |

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
| `2026.04.18b` | `2026-04-18` | Add "Known Gotchas" section (Bitnami legacy images, Flux targetNamespace override, Helm configFromSecret pitfall, venv pip for modern Python images, Celery concurrency, Authentik copy-blueprints wildcard, PromRule Succeeded-phase exclusion, Homepage icon verification) |
| `2026.04.18c` | `2026-04-18` | Add Known Gotcha #9: Python WSGI apps behind TLS-terminating ingress — enable framework ProxyFix (Flask/Django/FastAPI/Rails/n8n variants) so OAuth redirect_uri and self-referencing URLs use `https://` |
| `2026.04.19` | `2026-04-19` | Consolidate prior 04.18/04.18b/04.18c versions into a single YYYY.MM.DD format (doc-check compliance) |
