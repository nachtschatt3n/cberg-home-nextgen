---
plan_id: grafana-14.0.1
component: grafana
pr: 374                             # Renovate "feat(helm)!: Update grafana ( 13.2.7 -> 14.0.1 )" (chart MAJOR)
kind: chart
current: "13.7.0"                   # runs AFTER grafana-13.7.0 (PR #374 itself diffs from 13.2.7; this plan assumes 13.7.0 landed)
target: "14.0.1"
update_type: major
risk: low
est_duration_min: 15
needs_reboot: false
touches:
  namespaces: [monitoring]
  resources:
    - helmrelease/monitoring/grafana
    - deployment/monitoring/grafana            # label churn only; with our values the render is IDENTICAL to 13.7.0 except helm.sh/chart labels
    - kustomization/monitoring/grafana
    - kubernetes/apps/monitoring/grafana/app/helmrelease.yaml
  shared: [monitoring]
depends_on: [grafana-13.7.0]
conflicts_with:
  - grafana-13.7.0                    # must be sequenced after, never same step
  - flux-oci-chart-sources
  - helm-drift-detection
  - flux-reconciler-impersonation
  - flux-fleet-0.60.0
  - flux-distribution-2.9.6
  - talos-linux-1.14.2
  - talos-linux-1.14.4
  - kube-prometheus-stack-92.2.0
  - kube-prometheus-stack-92.10.1
  - kube-prometheus-stack-92.11.0     # exclusive; shared Prometheus instrument: never the same window (reviewer 2026-10-22)
exclusive: false
security_ref: null                    # F-c01c08c6 is a version finding, not a security finding (reviewer 2026-10-22); the grafana image row F-fcb94b29 is on the 13.7.0 plan
capability_change: false              # 14.0.0 adds values.schema.json validation + extraContainers list form; no runtime change
rollback_class: git-revert
finding_refs: [F-c01c08c6]
review: ready-for-go@2026-10-22   # plan-reviewer 2026-10-22: needs-fix (conflict, security_ref, grep exit-status trap) -> fixed; render identical to 13.7.0; helm lint passes; runs only after grafana-13.7.0 landed
status: vetted
window: null
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/grafana-image-changes.md
premises:
  - id: grafana-13.7.0-landed
    why: "This plan is the second hop. Requires chart 13.7.0 live."
    run: kubectl get helmrelease grafana -n monitoring -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: "13.7.0"
  - id: helmrelease-ready
    why: "Do not stack on a failing release."
    run: kubectl get helmrelease grafana -n monitoring -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: target-appversion-13.2.4
    why: "CENTRAL CLAIM: 14.0.1 ships the same appVersion as 13.7.0, so no binary moves."
    run: helm show chart grafana-community/grafana --version 14.0.1 | grep '^appVersion:'
    expect_exact: "appVersion: 13.2.4"
generated: "2026-10-22"
---

# grafana: chart 13.7.0 -> 14.0.1 (MAJOR chart, same Grafana 13.2.4 binary)

## 1) Summary & why held
Held only because the chart major bumps trip the `*grafana*` `max: patch` rule. Measured 2026-10-22:
`diff -r` of the 13.7.0 and 14.0.1 chart tarballs shows (a) a new `values.schema.json` (14.0.0, validates value
TYPES on install/upgrade/template; undeclared keys still accepted), (b) `extraContainers` accepts a list as well as
a string (`_pod.tpl`), (c) README notes (admin password applied only on first DB start; we use `envFromSecret` and do not rotate here).
`helm template` of both charts fed the LIVE `spec.values` renders **identical output apart from `helm.sh/chart` labels** and exits 0
under the schema. The Grafana image stays 13.2.4-distroless, sidecars 2.14.1. Residual risk: only the schema check against
values changed between now and the window (gate 2.1 re-runs it). Not a needs-operator item unless 2.1 fails.

## 2) Pre-checks
```bash
cd /Users/mu/code/cberg-home-nextgen; helm repo update grafana-community >/dev/null
.venv/bin/python3 runbooks/plan-premises.py grafana-14.0.1
```
**2.1 STOP gate: our live values pass the 14.x schema and render equal to 13.7.0.**
```bash
V=$(mktemp -d)
kubectl get hr grafana -n monitoring -o jsonpath='{.spec.values}' | .venv/bin/python3 -c 'import sys,json,yaml;print(yaml.safe_dump(json.load(sys.stdin)))' > $V/vals.yaml
for c in 13.7.0 14.0.1; do helm template grafana grafana-community/grafana --version $c -n monitoring -f $V/vals.yaml > $V/r$c.yaml; echo "$c rc=$?"; done
DIFFN=$(diff $V/r13.7.0.yaml $V/r14.0.1.yaml | grep '^[<>]' | grep -vc 'helm.sh/chart' || true); echo "non-label diff lines: $DIFFN"; test "$DIFFN" = 0 && echo PASS || echo FAIL   # grep -c exits 1 when the count is 0 (the PASS case): read the printed count, not the exit status (reviewer 2026-10-22)
# PASS: both rc=0 and the count is 0. FAIL: a schema error ("got string, want ...") or count>0 -> STOP, leave PR #374 held (needs-operator: quote/retype the named value).
```
**2.2 STOP gate: backup fresh** (nothing here touches data, but a roll happens): `.venv/bin/python3 runbooks/longhorn-backup-age.py grafana-config --max-hours 26` must print FRESH.
Baseline for gates 4.x: same `$W`/prov.py/datasource baseline block as plan `grafana-13.7.0` section 2 (dashboards=72 provisioned=65, ds_plugins=18).

## 3) Steps (GitOps)
```bash
sed -i '' -E 's/^      version: 13\.7\.0$/      version: 14.0.1/' kubernetes/apps/monitoring/grafana/app/helmrelease.yaml
git diff --stat kubernetes/apps/monitoring/grafana/app/helmrelease.yaml   # 1 insertion, 1 deletion (dry-tested pattern, same shape as 13.7.0 plan)
git commit --only kubernetes/apps/monitoring/grafana/app/helmrelease.yaml -m "chore(grafana): chart 13.7.0 -> 14.0.1 (major chart; values schema only, Grafana 13.2.4 unchanged) [plan grafana-14.0.1, PR #374]"
git log -1 --format=%s; git show --stat HEAD; git push
kubectl rollout status deployment/grafana -n monitoring --timeout=300s
```

## 4) Verification
Run gates 4.1-4.4 of plan `grafana-13.7.0` with these differences: chart label `grafana-14.0.1`, hr chartVersion `14.0.1`,
`/api/health` version stays `13.2.4`, images unchanged from 13.7.0 (grafana `13.2.4-distroless`, sidecars `2.14.1`).
Specific failure guards: `kubectl get hr grafana -n monitoring -o jsonpath='{.status.conditions[?(@.type=="Ready")].message}'`
containing `values don't meet the specifications` or `got string` = the schema rejected a value (helm-controller then keeps 13.7.0 running: confirm `.status.history[0].chartVersion` still 13.7.0 and revert the git commit);
dashboards == 72/provisioned >= 65; six datasource `/health` OK; ds_plugins >= 18 (GF_PLUGINS_PREINSTALL_DISABLED still `true`).
CONTENTS ASSERTION: dashboards == 72, provisioned >= 65, six datasources OK, versus the section 2 baseline.

## 5) Rollback
`SHA=$(git log -1 --format=%H -- kubernetes/apps/monitoring/grafana/app/helmrelease.yaml); git revert --no-edit $SHA; git log -1 --format=%s; git push`,
reconcile, confirm hr chartVersion 13.7.0 and re-run the datasource gate. No data change is possible (same binary, identical render), so no volume restore applies.

## 6) Interference notes
Sequence strictly after `grafana-13.7.0` (own roll, own verification). Same shared-monitoring conflicts as that plan. Repo note:
`kube-prometheus-stack-92.10.1` bumps its bundled (disabled) grafana subchart to 14.0.1; inert and independent.
