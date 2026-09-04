# SOP: New Deployment Blueprint

> Standard Operating Procedure for onboarding and rolling out new applications in this repository.
> Reference: `docs/applications.md`, `docs/infrastructure.md`, `docs/sops/homepage-integration.md`, `docs/sops/longhorn.md`, `docs/sops/log-volume-runaway.md`, `docs/sops/monitoring.md`, `docs/sops/sops-encryption.md`.
> Description: Default deployment blueprint that combines namespace rules, Homepage integration, storage rules, monitoring requirements, Flux webhook GitOps workflow, and code standards.
> Version: `2026.09.04`
> Last Updated: `2026-09-04`
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
| Storage | Use `longhorn-static` with a speaking PV name by default; `longhorn` (dynamic, UUID PV) only where a name is impossible — StatefulSet volumeClaimTemplates |
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
  storageClassName: longhorn-static
  volumeName: {app}-{purpose}          # speaking name, never a UUID
```

**Longhorn volume naming rule:**

- **Default: use `longhorn-static` with a speaking name.** Longhorn's UI, backup list and every restore procedure key on the **PV** name, so a `pvc-<uuid>` PV cannot be identified without a `claimRef` lookup — exactly the indirection you do not want mid-incident.
- **The Longhorn Volume, the PV, the PVC's `volumeName`, the PV's `volumeHandle`, and the PVC name must all be the SAME speaking identifier.** Convention: `{app}-{purpose}` (e.g. `pgadmin-data`, `superset-postgresql-data`).
- **Use `longhorn` (dynamic, UUID PV) only when a name is impossible** — StatefulSet `volumeClaimTemplates` generate one PVC per replica at scale time, so PVs cannot be pre-created. Also acceptable for genuinely ephemeral scratch/cache data.
- **The manual Volume-CR apply is not a reason to fall back to dynamic.** A `Pending` PVC means you have not applied `longhorn-volume.yaml` yet (see the Flux `targetNamespace` note below) — apply it, do not switch class.

Three-file pattern for `longhorn-static` (see `kubernetes/apps/databases/pgadmin/app/` or `kubernetes/apps/databases/superset/app/` for working references).

**High-churn data (logs / metrics / time-series) — enforce app-side retention.** Longhorn's nightly `global-filesystem-trim` (02:00, covers every volume in the `default` group automatically) only reclaims blocks the *application* has freed. If the app never deletes its own old data, the volume fills with live data and trips `LonghornVolumeUsage*` alerts — trim can't help. So for any app that continuously writes (Elasticsearch/OTel datastreams, Prometheus, Loki, time-series DBs): verify its retention/ILM/DSL actually deletes old data. Watch for the Elasticsearch gotcha where `index.lifecycle.prefer_ilm: true` makes a no-delete ILM policy win over DSL `data_retention` (see the `filesystem-trim` note in `docs/sops/longhorn.md`).

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
   - **CIFS / SMB / NFS classes**: read `docs/sops/storage-safety.md` first. Never author a new shared-fs StorageClass with `subdir: /` and `reclaimPolicy: Delete` — that pattern recursively wipes the entire share on PVC delete (see 2026-04-26 incident). Subdir must be a per-app path exclusively owned by PVCs of that class. Prefer `reclaimPolicy: Retain` for any class that points at user data. Add the new class to the table in `docs/sops/storage-safety.md` in the same commit.

5a. **Storage teardown / decommissioning** — when removing or rotating a stateful workload:
   - Run the 3-step pre-flight from `docs/sops/storage-safety.md` (inspect `volumeAttributes.subdir`, `persistentVolumeReclaimPolicy`, StorageClass defaults) **before** any `kubectl delete pvc`.
   - For CIFS/SMB/NFS PVCs on a `Delete` reclaim class with `subdir: /` or any path containing user data beyond the PVC's scope: patch the PV to `Retain` first, then delete the PVC. Do not rely on the PVC's stated quota — it does not bound deletes.
   - Sub-agent dispatch (`health-check-agent`, `version-check-agent`, `security-agent`, `doc-agent`) must include the storage-safety rules in the brief if the task touches storage.
6. Configure ingress and Homepage metadata for user-facing web apps (annotations + label).
   - Use `className: internal` for LAN-only access; `className: external` for internet-facing apps.
   - **External ingresses MUST include the `external-dns.alpha.kubernetes.io/target: "external.${SECRET_DOMAIN}"` annotation.** Without it, external-dns falls back to the internal LoadBalancer IP, which Cloudflare rejects (error 9003) for proxied records — the DNS record will never be created and the hostname will return NXDOMAIN.
7. If the app has user login, declare the Authentik provider in the blueprint ConfigMap (`kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml`):
   - Forward-auth proxy providers for apps without their own auth.
   - OAuth2/OIDC providers for apps with their own user model.
   - Add a new `*-blueprint.yaml` key per the Authentik SSO blueprint section above. `client_secret` lives in the SOPS ConfigMap AND in the app's own SOPS Secret — keep both in sync.
   - Never configure providers via the Authentik UI only — blueprints are authoritative.
8. Add monitoring coverage:
   - Ensure app health endpoints/probes are set, and that the probe target is a
     **static, cheap, silent** endpoint — never a framework route. The kubelet hits
     it ~480x/hour; a route that boots the application on every request turns that
     into a log-volume incident. See Known Gotcha #13 and
     `docs/sops/log-volume-runaway.md`.
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
# Repo-wide manifest validation (the `task template:configure` target referenced
# by older docs no longer exists in this Taskfile).
task kubeconform
kubeconform -summary -exit-on-error -ignore-missing-schemas kubernetes/apps/{namespace}/{app}
```

> **kubeconform SKIPS every CRD kind — it can validate nothing and still exit 0.**
> `HelmRelease`, `Probe`, `PrometheusRule`, `Gateway`, `Kustomization` etc. have
> no schema locally, so an app built entirely from CRDs reports
> `Valid: 0 … Skipped: 8` and passes. Observed 2026-08-15 on
> `prometheus-blackbox-exporter`, where the skip hid a wrong `serviceMonitor`
> values shape that rendered **no ServiceMonitor at all**.
>
> For any HelmRelease whose `values` shape is non-trivial, validate by rendering
> against the pulled chart — this is the only step that actually checks your
> values keys exist:
>
> ```bash
> # extract spec.values, then render the real chart with them
> helm template {app} <chart-ref> --version <ver> -n {namespace} -f /tmp/values.yaml
> ```
>
> Check the rendered kinds are the ones you expect, and remember Helm coalesces
> nested maps: chart-default entries survive your block unless explicitly
> nulled (`somekey: null`).

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

### 1. Bitnami images — `bitnamilegacy/*` unblocks a chart, it is not the destination

Bitnami deleted all pre-2026 image tags from `docker.io/bitnami/*` in late 2025; the tags live in `docker.io/bitnamilegacy/*` with identical content. Helm charts using Bitnami subcharts (postgresql, redis, mongodb, etc.) still reference the old tags and will fail with `image not found` unless overridden.

> **For a NEW deployment, do not bundle the datastore at all.** Those
> `bitnamilegacy/*` images are frozen and unmaintained: the datastore cannot be
> patched independently of the chart, so every CVE in it waits on a chart
> release. Since 2026-08 this cluster has been actively exiting them — set
> `postgresql.enabled: false` / `redis.enabled: false` / `mariadb.enabled: false`
> and stand the datastore up as our own Deployment + Service + PV/PVC on the
> Docker Official image. Done four times so far (`superset-pg`, `paperless-db`,
> `authentik-pg`, `nextcloud-db`); the procedure and its failure modes are in
> [`docs/sops/bundled-datastore-exit.md`](bundled-datastore-exit.md).
>
> Use the override below only to get an existing chart pulling again, or when a
> subchart genuinely cannot be separated. It is a unblock, not a target state,
> and it books future migration work.

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

### 1b. Never deploy on a floating tag — pin a version or a digest

`latest`, `main`, `stable`, and variant-only tags (`node:22-bookworm`,
`lts-alpine`, `trixie-slim`) are rebuilt in place upstream. The consequence is
not just unpredictability, it is **invisibility**: Renovate's helm-values manager
diffs a version-shaped tag, so a floating tag never changes, never emits a PR,
and the image ages silently — no update lane, no CVE signal, no drift report.
That was 19 images across six namespaces when it was measured, and clearing it
took four batches (`43ec3d84`, `58faf4bd`, `b8d583f0`, `f5b03e8a`) plus a tail of
residuals.

**Rule for any new deployment:** every image reference — app, init containers,
sidecars, and subchart images alike — must carry either a concrete version tag
or a digest.

```yaml
image:
  repository: docker.io/library/postgres
  tag: 18.6-bookworm@sha256:<digest>   # version for readability, digest for immutability
```

Digest-pin whenever upstream rebuilds the tag in place (Docker Official base
images, `node:*`, `busybox`, `debian`, `ubuntu`). A version tag alone is enough
for images whose publisher treats tags as immutable. Pin to the digest that is
**already running** so the change is pure observability and moves no bytes.

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

### 9. bjw-s app-template — `resources` must be nested inside the container, not at chart top level

In bjw-s `app-template`, placing `resources:` at the top level of `values:` (or under `controllers.<name>:`) is silently ignored — the pod runs with no resource limits. The correct location is inside `controllers.<name>.containers.<name>`:

```yaml
# ❌ WRONG — no-op, ignored by app-template
values:
  resources:
    requests:
      memory: 128Mi

# ✅ CORRECT
values:
  controllers:
    main:
      containers:
        main:
          resources:
            requests:
              cpu: 50m
              memory: 128Mi
            limits:
              cpu: 200m
              memory: 512Mi
```

Symptom: pod runs without OOM limit → `Exit Code: 137 (OOMKilled)` if it grows unbounded. The HelmRelease shows `Ready: True` — there is no chart-level error for a misplaced `resources` block.

### 10. Python WSGI apps behind TLS-terminating ingress

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

### 11. External ingress — missing `external-dns.alpha.kubernetes.io/target` annotation causes NXDOMAIN

When switching an ingress from `className: internal` to `className: external`, external-dns must know to create a CNAME pointing to the Cloudflare tunnel rather than an A record pointing at the internal LoadBalancer IP. Without the target annotation, external-dns tries to register the LB IP (`192.168.55.x`) as a proxied Cloudflare A record, which Cloudflare rejects with error 9003 — "Target is not allowed for a proxied record." The DNS record is never created and the hostname returns NXDOMAIN.

**Fix:** always add this annotation to every `className: external` ingress:

```yaml
annotations:
  external-dns.alpha.kubernetes.io/target: "external.${SECRET_DOMAIN}"
```

This makes external-dns create a proxied CNAME pointing to `external.${SECRET_DOMAIN}` (the cloudflared tunnel entry point), consistent with all other internet-facing services in the cluster.

### 12. Single-replica Deployment on an RWO volume — set the rollout strategy

A `Deployment` with `replicas: 1` that mounts a **ReadWriteOnce** Longhorn PVC will
stall on `FailedAttachVolume` / `Multi-Attach error` when it is next rolled, unless
you set the rollout strategy. The default `RollingUpdate` at `replicas: 1` computes
to `maxSurge: 1` (25% rounds **up**) and `maxUnavailable: 0` (25% rounds **down**),
so it must bring a second pod to Ready before releasing the first — but the second
pod cannot attach a volume the first still holds.

It clears only when a retry happens to co-schedule the replacement onto the node
already holding the attachment, so it presents as an intermittent, confusing stall
rather than a clean failure.

**Fix — ship one of these from day one on any new single-replica app with an RWO PVC:**

```yaml
# preferred for a NEW Deployment
spec:
  strategy:
    type: Recreate
```

```yaml
# equivalent; required when converting an EXISTING Deployment, because
# server-side apply cannot drop the API-defaulted rollingUpdate block
spec:
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 0
      maxUnavailable: 1
```

For chart-based apps this is a **values** change and the key differs per chart
(`strategy` vs `updateStrategy` vs `<subchart>.updateStrategy`) — a wrong path
silently no-ops, so verify with `helm template`, not by reading the values file.

StatefulSets need nothing: they terminate before recreating. CIFS/SMB PVCs need
nothing either (`smb.csi.k8s.io` has `attachRequired: false`).

Full SOP: [`docs/sops/longhorn-rwo-multi-attach.md`](longhorn-rwo-multi-attach.md).

### 13. Probe endpoints must be STATIC — a framework route probed at kubelet frequency is a log-volume incident

The kubelet is the highest-frequency client any app has. With the house probe
defaults (readiness 10s, liveness 30s, startup 5s) it makes **~480 requests per
hour, forever**, on a service with zero users. Whatever a probe costs, it costs
480 times an hour.

That is fine for a static endpoint and ruinous for a framework route. On a
per-request-boot runtime (php-fpm, CGI, some Python WSGI setups) a route boots
the entire framework on every hit. One real case: a CakePHP 1.x `/health` route
emitted ~370 PHP deprecation notices per boot, each double-logged by php-fpm and
nginx:

```
480 boots/hour x ~370 notices = ~179,000 log lines/hour = 4.35M/24h
```

which was **58% of the entire cluster's log ingest** and **98.8% of the error
metric** — from health probes alone, on an app that was working perfectly. It
also scored as errors only because the substring `Error` sits inside the method
name `handleError`. Nothing was broken; the health check was the incident.

**The pattern — split the probes:**

| Probe | Target | Why |
|---|---|---|
| liveness | the deep framework route | must detect a dead app tier; 120 boots/hour is affordable |
| readiness | a **static** endpoint | 360 boots/hour — this is the whole saving |
| startup | the deep framework route | fires **0x/hour** in steady state, so it costs nothing, and it is what gates the Flux rollout |

The startup row is the counter-intuitive one, and it was got wrong once already
in this repo before being caught in review. State the division of labour
plainly:

> **Startup is the DEPLOY gate. Readiness is the TRAFFIC gate.**

They fail differently and they must be probed differently:

- **Readiness** answers *"should this pod receive requests right now?"* — asked
  360 times an hour, forever. This is where every probe saving is, and a shallow
  check is acceptable because liveness still catches a dead tier within one
  window.
- **Startup** answers *"did this release actually come up?"* — asked a handful of
  times, once, and then **never again**. Its steady-state rate is **0/hour**, so
  moving it to a cheap endpoint saves *nothing whatsoever*.

What a shallow startup probe costs is the release verdict. While startup fails
the container is not Ready, the Deployment never becomes Available, and the
HelmRelease's `upgrade.remediation.strategy: rollback` fires. Point startup at
a static endpoint and that safety net is gone: a pod that boots with a bad DB
credential, an unreachable database or an unwritable temp dir answers the shallow
check instantly, so **the release reports SUCCESSFUL** and the app only starts
CrashLooping afterwards — after Flux has already recorded a good deploy and moved
on. With `strategy: Recreate` at `replicas: 1`, the previous working pod was
deleted before the new one started, so there is nothing still serving.

Trading a real deploy gate for a 0/hour saving is always a bad trade. If you are
tempted to shallow a probe, first ask how often it actually fires.

If the image has no static health endpoint, add one **additively** rather than
overriding the image's config — a ConfigMap `subPath`-mounted into
`/etc/nginx/conf.d/` adds a file without shadowing `default.conf`:

```nginx
server {
    listen 8080;
    server_name _;
    access_log off;              # probes must not log either
    default_type text/plain;
    location = /healthz { return 200 "ok\n"; }
    location /         { return 404; }
}
```

Keep that port off the Service and the ingress. Reference implementation:
`kubernetes/apps/my-software-showcase/ibgastro/app/configmap-nginx-healthz.yaml`.

**Do not "fix" a probe storm by relaxing the intervals** (palliative, costs
detection latency) **or by dropping the lines at the collector** (masks the
problem, and the app then has no way to report a real error). Full remediation
order and the attribution queries:
[`docs/sops/log-volume-runaway.md`](log-volume-runaway.md).

---

### 14. A ConfigMap can be a SEED, not the live config — the live process is the truth, not the manifest

**The rule: after changing a value, verify it by reading the running process,
not by reading the manifest and not by reading `flux get`.** Green reconcile
proves the API server has your YAML. It proves nothing about what the process
is doing.

There are three distinct ways a correct manifest silently fails to reach the
workload, and the 2026-09-04 `gemma4` GGUF→MLX migration hit all three in one
commit. In every case Flux was green.

**(a) Seed-only ConfigMap — the worst, because grep cannot find it.**
`ai/hermes-agent` mounts its ConfigMap at `/seed` and runs an init container:

```sh
if [ ! -f /opt/data/config.yaml ]; then
  cp /seed/config.yaml /opt/data/config.yaml
fi
```

`/opt/data` is a PVC. Once seeded, **the PVC copy is authoritative forever.**
Editing `configmap.yaml` changes nothing — not on reconcile, not on restart,
not with Reloader. The manifest said `gemma4:26b-mlx`, the ConfigMap in the
API said `gemma4:26b-mlx`, the pod had just been restarted, and the process
was reading a **17-day-old PVC file** naming the old model. An exhaustive repo
grep for the old value returned *zero* hits while a live consumer was still
requesting it. Fix by patching the file in-container, then restarting, then
re-reading the file in-container.

**(b) ConfigMap-backed env with no checksum annotation.** `ai/anythingllm`'s
chart generates a ConfigMap consumed as env, and adds no pod-template checksum.
Changing the ConfigMap does not change the pod template, so no rollout happens
and the pod keeps its original env indefinitely — the pod was 6 days old.

**(c) Config file read once at process start.** `home-automation/frigate`
reads `/config/config.yml` at boot. The ConfigMap updates and the mounted file
eventually updates, but the *running process* keeps its parsed copy. Only a
restart applies it; here that would have been the 02:30 CronJob, hours later.

For (b) and (c) the fix is `reloader.stakater.com/auto: "true"` (Reloader runs
in this cluster; see `mosquitto`, `trmnl-ha`, `scrypted-nvr`, `mqttx-web`). For
(a) **do not add a Reloader annotation** — it cannot work, and it creates false
confidence in a mechanism that will never fire.

**Verification pattern — cheap, and it is the only thing that actually proves
the change landed:**

```bash
# env-based
kubectl exec -n <ns> deploy/<app> -- sh -c 'echo $MY_SETTING'
# file-based (mounted ConfigMap, or a PVC copy)
kubectl exec -n <ns> deploy/<app> -- cat /path/to/config.yaml
```

**Before declaring a fleet-wide value change complete, diff the set of
workloads you changed against the set whose live process you actually read.**
Anything in the first set but not the second is unverified, and "Flux is green"
is not evidence. The same lesson applies to DB/UI-configured apps
(`docs/ai-usage-map.md` lists which ones those are) — for those the manifest
never had the value in the first place.

---

## Troubleshooting

| Symptom | Likely Cause | Action |
|---------|--------------|--------|
| Push completed but app did not update | Webhook or source sync issue | Check `Receiver`, Flux events, and source-controller logs |
| HelmRelease not ready | Invalid values/chart mismatch | `kubectl describe helmrelease {app} -n {namespace}` and fix values |
| App running but missing from Homepage | Missing/misplaced metadata | Add Homepage annotations and label to ingress |
| External hostname returns NXDOMAIN | Missing `external-dns.alpha.kubernetes.io/target` annotation | Add `external-dns.alpha.kubernetes.io/target: "external.${SECRET_DOMAIN}"` to ingress annotations — see Known Gotcha #11 |
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
| OAuth provider rejects `redirect_uri` with scheme mismatch (`http://` vs `https://`) | WSGI app sees request as `http://` internally; doesn't trust ingress's `X-Forwarded-Proto` | Enable framework's ProxyFix (Flask: `ENABLE_PROXY_FIX=True` + `PROXY_FIX_CONFIG`, Django: `SECURE_PROXY_SSL_HEADER`) — see Known Gotcha #10 |
| HelmRelease times out on FIRST install, pods look fine | A from-scratch schema/app install exceeds Helm's 5m default timeout — the work is still running when Flux gives up, and the retry restarts it from the beginning | Set `spec.timeout: 15m` (and `spec.install.timeout`) on the HelmRelease. Seen on uzeit-de's from-scratch TYPO3 install (`152cb651`, 2026-08-18) and on a Superset `Recreate` transition (`8b0075ed`). Check pod logs for forward progress before assuming a real failure |
| Pod OOMKilled despite `resources:` in HelmRelease | `resources:` placed at wrong nesting level in app-template (no-op) | Move `resources:` inside `controllers.<name>.containers.<name>` — see Known Gotcha #9 |

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
| `2026.05.04` | `2026-05-04` | Add Known Gotcha #9: bjw-s app-template `resources` placement (top-level is a no-op → OOMKilled); update troubleshooting table; renumber WSGI gotcha to #10 |
| `2026.05.06` | `2026-05-06` | Add Known Gotcha #11: external ingress requires `external-dns.alpha.kubernetes.io/target` annotation — without it Cloudflare rejects the A record (error 9003) and hostname returns NXDOMAIN |
| `2026.08.18` | `2026-08-18` | Add Known Gotcha #13: probe endpoints must be static — a framework route probed at kubelet frequency (~480 req/h) produced 58% of all cluster log ingest; split-probe pattern, and why `startup` must stay on the deep route |
| `2026.09.04` | `2026-09-04` | Add Known Gotcha #14: a ConfigMap can be a SEED, not the live config — the live process is the truth, not the manifest. Three failure modes (seed-only ConfigMap copied to a PVC, ConfigMap-backed env with no checksum annotation, config file read once at start), why Reloader fixes two of them and must NOT be used for the third, and the exec-based verification pattern. Learned during the gemma4 GGUF→MLX migration, where a repo grep returned zero hits while a live consumer still requested the old model |
| `2026.08.23` | `2026-08-23` | F-750d8a3c — realign with 2026-08 practice: Gotcha #1 reframed (`bitnamilegacy/*` is an unblock, not a target; new deployments stand the datastore up standalone per `bundled-datastore-exit.md`); new Gotcha #1b requiring version- or digest-pinned tags for every image (a floating tag never emits a Renovate PR, so the image ages invisibly — 19 of them, cleared in batches A–D); troubleshooting row for a from-scratch install exceeding Helm's 5m default timeout (uzeit-de `152cb651`) |
