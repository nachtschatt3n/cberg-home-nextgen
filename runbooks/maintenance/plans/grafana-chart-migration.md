---
plan_id: grafana-chart-migration
component: grafana
pr: null                              # the checker reports grafana as "latest ✅" — see Summary
kind: chart
current: "chart 10.5.15 (grafana.github.io) / Grafana app 12.4.8 (image-pinned)"
target: "chart 12.10.4 (grafana-community.github.io) / Grafana app 13.x"
update_type: major                    # repo swap + chart 10 -> 12 + app 12 -> 13
risk: high
est_duration_min: 90
needs_reboot: false
touches:
  namespaces: [monitoring, flux-system]
  resources:
    - helmrepository/grafana           # URL swap to grafana-community
    - helmrelease/grafana              # chart 10.5.15 -> 12.10.4
    - deployment/grafana               # app 12 -> 13 (major)
    - "38 sidecar-provisioned dashboards"
    - "datasources: Prometheus, Elasticsearch, InfluxDB, TeslaMate, Pellets"
  shared: [monitoring]
depends_on: []
conflicts_with: []                    # but never with kube-prometheus-stack in one window
status: draft
window: null                          # NOT scheduled — needs operator go-ahead first
auto_execute: false
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/monitoring.md
generated: "2026-08-14"
---

# Grafana: chart-repo migration + app 12 → 13

## 1) Summary & why held

**The chart repo we point at is frozen.** `kubernetes/flux/meta/repositories/helm/grafana.yaml`
targets `https://grafana.github.io/helm-charts`, whose newest grafana chart is
**10.5.15 / appVersion 12.3.1**. The live chart moved to
`https://grafana-community.github.io/helm-charts`, currently **12.10.4 /
appVersion 13.1.3** — kube-prometheus-stack 88.3.0's own `Chart.yaml` already
resolves its grafana dependency there.

**Consequence worth understanding:** `check-all-versions.py` queries the pinned
repo, finds 10.5.15 is its newest, and reports grafana as "latest ✅". It is not
lying about the repo — the repo is dead. This is why the drift went unnoticed,
and it is the same shape as the other audit findings this month: a green result
derived from a source that stopped answering.

**Not urgent for CVEs.** The 13 fixable criticals that lived here (grafana 12.3.1,
k8s-sidecar 2.5.0, curl 8.9.1) were cleared on 2026-08-14 by pinning image tags
on the existing chart — see the values block in the HelmRelease. This plan is
about getting off a dead repo, not about CVEs, so it can wait for a good window.

**Why high risk:** it is three majors at once — repo, chart (10 → 12) and the
Grafana application (12 → 13). Grafana 13 has breaking changes around
provisioning and plugin APIs, and this instance carries 38 sidecar-provisioned
dashboards plus five datasources including two custom ones.

## 2) Pre-checks

```bash
# what actually changes between the two charts
helm repo add grafana-community https://grafana-community.github.io/helm-charts
helm show values grafana-community/grafana --version 12.10.4 > /tmp/new-values.yaml
helm show values grafana/grafana --version 10.5.15 > /tmp/old-values.yaml
diff -u /tmp/old-values.yaml /tmp/new-values.yaml | head -200
#   pay attention to: image.*, sidecar.*, downloadDashboardsImage.*, persistence,
#   admin/existingSecret, grafana.ini handling, and the datasource provisioning schema.

# READ the Grafana 13 breaking-changes / upgrade notes before the window.

# capture current state to compare against afterwards
kubectl exec -n monitoring deploy/grafana -c grafana -- \
  sh -c 'find /var/lib/grafana/dashboards -name "*.json" | wc -l'     # expect 38
kubectl get secret -n monitoring grafana-admin-secret -o json | python3 -c \
  "import sys,json;print(sorted(json.load(sys.stdin)['data'].keys()))"
# Longhorn backup of the grafana PVC must be fresh.
```

## 3) Steps

1. Swap the HelmRepository URL to `https://grafana-community.github.io/helm-charts`
   in its own commit, and confirm Flux pulls the index (`flux get sources helm -A`).
2. Bump the chart to 12.10.4 and reconcile. **Remove the three CVE image pins**
   added on 2026-08-14 (`image.tag`, `sidecar.image.tag`,
   `downloadDashboardsImage.tag`) — the new chart's defaults should already be at
   or ahead of them; verify with `helm template` that the rendered tags are >= the
   pinned ones before dropping the pins, and keep any that would regress.
3. Reconcile Kustomization BEFORE HelmRelease, then check the **Deployment**
   images, not just HR Ready (the open-webui lesson).

## 4) Verification

```bash
kubectl get deploy -n monitoring grafana -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
kubectl exec -n monitoring deploy/grafana -c grafana -- sh -c 'find /var/lib/grafana/dashboards -name "*.json" | wc -l'   # still 38
curl -s localhost:3000/api/health   # via port-forward: database ok, version 13.x
# Operator smoke test: log in via OAuth, open one dashboard per datasource
# (Prometheus, Elasticsearch, InfluxDB, TeslaMate, Pellets) and confirm panels
# render — a datasource provisioning schema change shows up as empty panels, not
# as a failed pod.
```

## 5) Rollback

Revert both commits (chart, then repo URL) and reconcile. Grafana's own DB may
have been migrated by v13 on first start; if dashboards or datasources do not
come back cleanly on 12.4.8, restore the grafana PVC from the pre-change Longhorn
backup per `docs/sops/backup.md`. Take that backup in pre-checks — this is the
step that makes the plan reversible.

## 6) Interference notes

- Never in the same window as `kube-prometheus-stack-88`: both touch monitoring,
  and kps 88.3.0 resolves its own grafana dependency from the new repo — doing
  both at once makes attribution impossible if something breaks.
- Grafana is how you SEE the cluster. Do not schedule alongside any plan whose
  verification depends on dashboards.
- `window: null` deliberately: this needs an explicit operator decision about
  taking Grafana 13, not just a free slot.
