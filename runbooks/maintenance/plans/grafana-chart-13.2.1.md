---
plan_id: grafana-chart-13.2.1
component: grafana
pr: null                              # community chart; no Renovate PR raised
kind: chart
current: "chart 13.0.1 (appVersion 13.2.0, image grafana/grafana:13.2.0-distroless)"
target: "chart 13.2.1 (appVersion 13.2.1, image grafana/grafana:13.2.1-distroless)"
update_type: minor
risk: medium
est_duration_min: 25
needs_reboot: false
touches:
  namespaces: [monitoring]
  resources:
    - helmrelease/grafana
    - deployment/grafana
    - pvc/grafana-config
  shared: []
depends_on: []
conflicts_with: []
capability_change: false
rollback_class: git-revert
status: vetted
window: "sun-attended:2026-09-13"   # AUTO-ASSIGNED 2026-09-06 by window-scheduler (AUTO-NIGHT; earning supervised runs — category not yet graduated)
premises:
  - id: chart-still-13.0.1
    why: >-
      The whole plan is the 13.0.1 -> 13.2.1 delta. If the chart already moved,
      the CVE arithmetic below was done against a version we no longer run.
    run: kubectl get helmrelease -n monitoring grafana -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: "13.0.1"
  - id: still-on-the-distroless-image
    why: >-
      The scan evidence below is for the -distroless variant specifically. The
      plain grafana/grafana image is a different artifact with a different CVE
      set, and a finding was already raised against it by mistake (F-de4d92cd,
      closed as not-deployed).
    # NOTE containers[0] is grafana-sc-dashboard, NOT grafana — the two
    # k8s-sidecar containers sort ahead of it. The first version of this
    # premise used [0] and asserted against the sidecar image; plan-premises.py
    # caught it immediately. Select by NAME.
    run: kubectl get deploy -n monitoring grafana -o jsonpath='{.spec.template.spec.containers[?(@.name=="grafana")].image}'
    expect_contains: "-distroless"
---

# grafana chart 13.0.1 -> 13.2.1

## Why, with the number measured rather than assumed

`security_ref: F-e8894b9a`.

Chart 13.0.1 ships appVersion 13.2.0. Charts 13.1.0, 13.2.0 and 13.2.1 all ship
appVersion **13.2.1** — verified against the community chart index, which is the
repo this HelmRelease actually points at
(`https://grafana-community.github.io/helm-charts`, NOT the official
`grafana.github.io` one; they carry different version lines and searching the
wrong one returns nothing for 13.x).

Scanned both image tags directly, `--ignore-unfixed --severity CRITICAL`:

| image | fixable CRITICAL |
|---|---|
| `grafana/grafana:13.2.0-distroless` (current) | 5 |
| `grafana/grafana:13.2.1-distroless` (target)  | 3 |

So this clears 2 and **leaves 3**. That is the honest reason to do it, and the
honest reason not to expect the finding to disappear: the residue is Go stdlib
and `golang.org/x/crypto` in an image we do not build, so it needs an upstream
rebuild, not another tag.

## What makes this a plan and not a hot bump

Grafana chart moves have bitten twice in one day (2026-09-06):

1. `12.11.2 -> 13.0.1` was a genuine breaking change — the chart default image
   became `-distroless` (no shell, no `wget`, no `ls`), which silently
   invalidated every `kubectl exec` snippet in
   `docs/sops/grafana-image-changes.md`.
2. Adding `serviceMonitor.labels: {release: kube-prometheus-stack}` FAILED the
   HelmRelease upgrade outright: the chart already hardcodes
   `release: {{ .Release.Name }}`, so the render produced
   `mapping key "release" already defined`. It was reverted within minutes.
   **Do not reintroduce that key.** Grafana is scraped because the Prometheus CR
   uses `serviceMonitorSelector: {}` (35b08902), not because of a chart label.

## Pre-checks

1. Run the premises above (`plan-premises.py grafana-chart-13.2.1`).
2. Confirm the target chart still resolves to appVersion 13.2.1:
   ```bash
   curl -s https://grafana-community.github.io/helm-charts/index.yaml \
     | python3 -c "import sys,yaml;d=yaml.safe_load(sys.stdin);print([(e['version'],e.get('appVersion')) for e in d['entries']['grafana'] if e['version']=='13.2.1'])"
   ```
3. Note the current dashboard count and datasource health, so the post-check
   compares against something:
   ```bash
   curl -s -u "$U:$P" localhost:3000/api/search | python3 -c "import sys,json;print(len(json.load(sys.stdin)))"
   ```

## Steps (GitOps)

Bump `spec.chart.spec.version` 13.0.1 -> 13.2.1 in
`kubernetes/apps/monitoring/grafana/app/helmrelease.yaml`, commit, push, let
Flux reconcile. Change nothing else — in particular do not touch
`serviceMonitor`.

## Verification

```bash
# 1. the release actually upgraded (not "Ready" against the OLD revision)
flux get helmrelease -n monitoring grafana

# 2. the image really moved
kubectl get deploy -n monitoring grafana -o jsonpath='{.spec.template.spec.containers[?(@.name=="grafana")].image}'
# EXPECT: grafana/grafana:13.2.1-distroless
# NOT containers[0] — that is grafana-sc-dashboard (k8s-sidecar).

# 3. grafana is still SCRAPED (the thing that was broken all day before 35b08902)
curl -s localhost:9090/api/v1/query --get --data-urlencode 'query=count(grafana_build_info)'

# 4. dashboards and datasources survived the roll — compare to the pre-check counts
```

Check 3 matters more than it looks: grafana had never been scraped in 244 days
until today, and a chart move is exactly when a ServiceMonitor gets rewritten.

## Rollback

`git-revert` the version bump. The PVC and its sqlite are untouched by a chart
minor, so rollback is a revert plus a reconcile.
