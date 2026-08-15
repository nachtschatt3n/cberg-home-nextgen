---
plan_id: grafana-chart-11
component: grafana
pr: null
kind: chart
current: "chart 10.5.15 (grafana-community, source swapped in 0f8baf00) / Grafana app 12.4.8 (image-pinned)"
target: "chart 11.6.1 (grafana-community) / Grafana app 12.4.8 (image pin RETAINED)"
update_type: major                    # chart major 10 → 11; the application does NOT move
risk: medium
est_duration_min: 45
needs_reboot: false
touches:
  namespaces: [monitoring]
  resources:
    - helmrelease/grafana
    - deployment/grafana               # rolls: chart template changes + Recreate strategy
    - configmap/grafana-dashboards-*   # 38 sidecar/provisioned dashboards re-rendered
    - "datasource provisioning: Prometheus, Unpoller InfluxDB, InfluxDB, TeslaMate, Pellets, Elasticsearch"
    - pvc/grafana-config               # grafana.db (SQLite) — NOT migrated by this stage
  shared: [monitoring]
depends_on: []                        # stage 1 (grafana-repo-swap) LANDED 2026-08-15 as 0f8baf00;
                                      # plan file deleted per the plans README convention.
                                      # Pre-check (a) below re-asserts the live source URL anyway.
conflicts_with: [kube-prometheus-stack-88]
status: draft
window: "thu-early:2026-08-27"
auto_execute: false
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/monitoring.md
  - docs/sops/backup.md
generated: "2026-08-15"
---

# Grafana stage 2/4 — chart 10.5.15 → 11.6.1 (application stays on Grafana 12.4.8)

## 1) Summary & why held

Stage 2 of 4 from the former `grafana-chart-migration`. The point of this stage
is the cut itself: **move the chart major, hold the application still.** Chart
`11.6.1` is the newest chart whose `appVersion` is still Grafana 12
(`12.4.3`); chart `12.0.0` is where `appVersion` becomes Grafana 13. Verified
from the community index on 2026-08-15:

| chart | appVersion |
|---|---|
| 10.5.15 | 12.3.1 |
| **11.6.1** | **12.4.3** ← last Grafana-12 chart |
| 12.0.0 | 13.0.0 |
| 12.10.4 | 13.1.3 |

Our values pin `image.tag: "12.4.8"`, so the app runs 12.4.8 regardless of
appVersion and **does not move in this stage**. If something breaks here, it is
the chart's templating — not Grafana.

**Upstream's own upgrade note for this major is small.** The chart README's
`### To 11.0.0` says in full: *"The minimum required Kubernetes version is now
1.25. All references to deprecated APIs have been removed."* A top-level values
diff 10.5.15 → 11.6.1 removes **no** keys (`verticalPodAutoscaler` is added).
That is why this is medium and not high.

**Keep the CVE pins in this stage — they are still load-bearing here.** Chart
11.6.1 defaults are `k8s-sidecar 2.6.0` and `curlimages/curl 8.19.0`, both
*older* than the 2026-08-14 pins (`2.10.1` / `8.21.0`). Dropping the pins on this
chart would re-open the criticals. They only become no-ops at chart 12.10.4
(stage 3).

**The trap this stage must not repeat.** The first attempt at the CVE pin
no-op'd because a second top-level `sidecar:` key was added and YAML
duplicate-key resolution silently kept the last one, while the HelmRelease
happily reported Ready. Verification below therefore reads the **rendered
Deployment**, not the HelmRelease status.

## 2) Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) stage 1 really landed — this stage cannot resolve its chart otherwise
mise exec -- kubectl get helmrepository -n flux-system grafana \
  -o jsonpath='{.spec.url}{"\n"}'          # MUST be https://grafana-community.github.io/helm-charts
mise exec -- kubectl get hr -n monitoring grafana \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.lastAppliedRevision}{"\n"}'   # True 10.5.15

# b) chart 11.6.1 exists and still carries a Grafana 12 appVersion
curl -sSL https://grafana-community.github.io/helm-charts/index.yaml -o /tmp/gc.yaml
python3 - <<'PY'
import yaml
d = yaml.safe_load(open("/tmp/gc.yaml"))
for x in d["entries"]["grafana"]:
    if x["version"] in ("11.6.1", "12.0.0"):
        print(x["version"], "appVersion", x.get("appVersion"))
PY
# expect: 11.6.1 appVersion 12.4.x  and  12.0.0 appVersion 13.x

# c) RENDER the new chart with our values BEFORE pushing (see §3 step 2) — the diff is
#    the actual review artifact for this stage.

# d) baseline to compare against
mise exec -- kubectl get deploy -n monitoring grafana \
  -o jsonpath='{range .spec.template.spec.containers[*]}{.name}={.image}{"\n"}{end}'
mise exec -- kubectl exec -n monitoring deploy/grafana -c grafana -- \
  sh -c 'find /var/lib/grafana/dashboards -name "*.json" | wc -l'     # record (expect 38)
mise exec -- kubectl exec -n monitoring deploy/grafana -c grafana -- \
  sh -c 'ls -la /var/lib/grafana/grafana.db'                          # size + mtime

# e) FRESH Longhorn backup of the grafana PVC (grafana.db lives there). Not because this
#    stage migrates the DB — it does not — but because a chart change can restart grafana
#    and a corrupt-on-restart SQLite is the one thing git cannot revert.
mise exec -- kubectl get volume -n storage grafana-config \
  -o custom-columns=NAME:.metadata.name,STATE:.status.state,ROBUST:.status.robustness,LASTBACKUP:.status.lastBackupAt

# f) no in-flight reconcile
mise exec -- flux get kustomizations -A | awk 'NR==1 || $5!="True"'
```

## 3) Steps

1. **Active-update marker**:
   ```bash
   runbooks/update-marker.sh add grafana monitoring 1 "grafana chart 10.5.15 -> 11.6.1 (app pinned 12.4.8)"
   ```
2. **Render both charts with OUR values and diff them.** Do this before editing
   anything; it is the review evidence for the window:
   ```bash
   cd /tmp && rm -rf gdiff && mkdir gdiff && cd gdiff
   for V in 10.5.15 11.6.1; do
     curl -sSL -o g-$V.tgz "https://github.com/grafana-community/helm-charts/releases/download/grafana-$V/grafana-$V.tgz"
     mkdir -p c$V && tar xzf g-$V.tgz -C c$V
   done
   cd /Users/mu/code/cberg-home-nextgen
   mise exec -- yq '.spec.values' kubernetes/apps/monitoring/grafana/app/helmrelease.yaml \
     | sed -e 's/\${SECRET_DOMAIN}/example.invalid/g' \
           -e 's/\${INFLUXDB_ORG}/org/g' -e 's/\${INFLUXDB_BUCKET}/bucket/g' > /tmp/gdiff/values.yaml
   for V in 10.5.15 11.6.1; do
     mise exec -- helm template grafana /tmp/gdiff/c$V/grafana -n monitoring -f /tmp/gdiff/values.yaml > /tmp/gdiff/render-$V.yaml
   done
   diff -u /tmp/gdiff/render-10.5.15.yaml /tmp/gdiff/render-11.6.1.yaml | head -300
   ```
   Read the diff for: container images, the datasources Secret/ConfigMap, the
   dashboard provider ConfigMap, `persistence`/`existingClaim`, and the ingress.
   **If a datasource or a dashboard provider disappears from the render, stop.**
3. **Bump the chart version** in
   `kubernetes/apps/monitoring/grafana/app/helmrelease.yaml`:
   ```yaml
     chart:
       spec:
         chart: grafana
         version: 11.6.1
   ```
   **Change nothing else.** In particular leave `image.tag: "12.4.8"`,
   `sidecar.image.tag: "2.10.1"` and `downloadDashboardsImage.tag: "8.21.0"` exactly
   as they are, and do not add a second top-level `sidecar:` key.
   ```bash
   grep -c '^    sidecar:' kubernetes/apps/monitoring/grafana/app/helmrelease.yaml   # must be 1
   git diff --stat     # ONE file, ONE changed line
   ```
4. **Prove the render carries the pins** (the anti-no-op check):
   ```bash
   mise exec -- helm template grafana /tmp/gdiff/c11.6.1/grafana -n monitoring -f /tmp/gdiff/values.yaml \
     | mise exec -- yq 'select(.kind=="Deployment" and .metadata.name=="grafana")
                        | [.spec.template.spec.containers[].image,
                           .spec.template.spec.initContainers[].image]'
   # expect grafana/grafana:12.4.8 and quay.io/kiwigrid/k8s-sidecar:2.10.1 — NOT the
   # chart defaults (12.4.3 / 2.6.0). If you see the defaults, the pin did not apply.
   ```
5. **Validate, commit, push** (on `main`, stage only this file):
   ```bash
   mise exec -- kubeconform -summary -exit-on-error -ignore-missing-schemas kubernetes/apps/monitoring/grafana
   git add kubernetes/apps/monitoring/grafana/app/helmrelease.yaml
   git commit -m "feat(grafana): chart 10.5.15 -> 11.6.1 (app stays pinned at 12.4.8)"
   git push
   ```
   Flux reconciles; `deploymentStrategy: Recreate` means grafana is down for the
   pod replacement (~30–60 s).
6. On success clear the marker: `runbooks/update-marker.sh clear grafana`.

## 4) Verification

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) HR reconciled to the new chart
mise exec -- kubectl get hr -n monitoring grafana \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.lastAppliedRevision}{"\n"}'   # True 11.6.1
mise exec -- kubectl rollout status deploy/grafana -n monitoring --timeout=300s

# b) THE load-bearing check — read the LIVE objects, not the HR status
mise exec -- kubectl get deploy -n monitoring grafana \
  -o jsonpath='{range .spec.template.spec.containers[*]}{.name}={.image}{"\n"}{end}'
# grafana MUST still be 12.4.8 (this stage does not move the app) and the sidecar MUST
# still be 2.10.1 (not the chart-11 default 2.6.0 — that would silently re-open 2 CVEs).
mise exec -- kubectl get pods -n monitoring -l app.kubernetes.io/name=grafana -o json | python3 -c "
import sys, json
for p in json.load(sys.stdin)['items']:
    for cs in p['status'].get('containerStatuses', []):
        print(cs['name'], cs['image'], 'ready', cs['ready'], 'restarts', cs['restartCount'])"

# c) dashboards + datasources survived provisioning
mise exec -- kubectl exec -n monitoring deploy/grafana -c grafana -- \
  sh -c 'find /var/lib/grafana/dashboards -name "*.json" | wc -l'     # same as pre-check (38)
mise exec -- kubectl logs -n monitoring deploy/grafana -c grafana --since=15m \
  | grep -iE 'error|failed to load dashboard|provisioning' | head -20 || echo clean

# d) app-level proof
DOM=$(mise exec -- kubectl get secret -n flux-system cluster-secrets -o jsonpath='{.data.SECRET_DOMAIN}' | base64 -d)
curl -s --max-time 20 "https://grafana.$DOM/api/health"     # {"database":"ok", "version":"12.4.8"}
# Operator smoke test (the real gate): log in via OAuth and open ONE dashboard per
# datasource — Prometheus, Elasticsearch, InfluxDB, TeslaMate, Pellets. A provisioning
# schema regression renders as EMPTY PANELS on a perfectly healthy pod.
```

Success = HR Ready on 11.6.1, grafana container still `12.4.8`, sidecar still
`2.10.1`, dashboard count unchanged, `/api/health` reports database ok and
version 12.4.8, and all five datasources render panels.

## 5) Rollback

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <chart-11-commit-sha>     # back to chart 10.5.15
git push
mise exec -- kubectl rollout status deploy/grafana -n monitoring --timeout=300s
mise exec -- kubectl get hr -n monitoring grafana \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.lastAppliedRevision}{"\n"}'   # True 10.5.15
mise exec -- kubectl get deploy -n monitoring grafana \
  -o jsonpath='{range .spec.template.spec.containers[*]}{.name}={.image}{"\n"}{end}'   # 12.4.8 / 2.10.1
```

If Helm wedges in `pending-upgrade`, clear it per
`docs/sops/application-update.md` §11 before re-reconciling.

**Data:** this stage does not migrate `grafana.db` — the application binary is
unchanged, so a chart revert reopens the same SQLite file. The PVC restore path
(`docs/sops/backup.md`, volume `grafana-config`) is only needed if the pod
restart itself corrupted the DB; the pre-check backup exists for exactly that.

## 6) Interference notes

- **Out of order:** without `grafana-repo-swap` (stage 1) the chart `11.6.1` does
  not exist in the configured HelmRepository — the HR fails to resolve its chart,
  goes not-Ready, and the running pod keeps serving stale. Nothing is lost, but
  the window is wasted. Do not "fix" that by swapping the repo mid-window: that is
  stage 1's job and it has its own verification.
- **Do not run stage 3 (`grafana-chart-12`) in the same window.** The entire value
  of this split is that a failure here is attributable to chart-major 10→11 alone.
- **`conflicts_with: kube-prometheus-stack-88`** — same `monitoring` namespace and
  the same observability surface. This stage is scheduled 5 days *after* kps-88's
  window so kps has settled first.
- Grafana restarts (Recreate). Anything whose verification depends on dashboards
  must not be in this window.
- The chart bump also re-renders the 38 dashboard ConfigMaps and the datasource
  provisioning Secret. `sidecar.dashboards.searchNamespace: ALL` means the sidecar
  reads dashboards from every namespace; a sidecar image regression would
  therefore quietly affect dashboards owned by other apps too — that is why the
  sidecar tag is verified on the live Deployment, not assumed.
