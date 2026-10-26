---
plan_id: grafana-14.1.0
component: grafana
pr: null                          # NO Renovate PR exists for 14.1.0 (chart published 2026-10-26T09:49Z, hours
                                  # before this plan; `gh pr list --search grafana` = none open, 2026-10-26).
                                  # If Renovate opens one before the window, close it and take the hand-edit
                                  # below (the *grafana* deny rule holds a minor in the PLAN lane anyway).
kind: chart
current: "14.0.1"                 # MEASURED 2026-10-26: HR spec 14.0.1, history[0] 14.0.1 / app 13.2.4, Ready
target: "14.1.0"
update_type: minor
risk: low
est_duration_min: 20
needs_reboot: false
touches:
  namespaces: [monitoring]
  resources:                      # every object below verified to EXIST live 2026-10-26
    - helmrelease/grafana         # git edit: spec.chart.spec.version 14.0.1 -> 14.1.0
    - deployment/grafana          # ROLLS ONCE (Recreate): pod-template label helm.sh/chart changes; image unchanged
    - pvc/grafana-config          # sqlite; RWO longhorn-static; mounted, NOT migrated (appVersion unchanged)
    - configmap/grafana           # re-rendered; content-identical except helm.sh/chart label
    - servicemonitor/grafana      # label only; Prometheus must re-find the new pod
    - clusterrole/grafana-clusterrole   # label only (rules gated on a sidecar we do not enable)
    - clusterrolebinding/grafana-clusterrolebinding   # label only
  shared: []                      # tenant of ns monitoring, not infrastructure: no gateway/cni/dns/db is restarted.
                                  # It READS shared infra in verification (Prometheus, Elasticsearch, InfluxDB,
                                  # the TeslaMate and pellets Postgres) but perturbs none of it.
depends_on: []
conflicts_with:                   # ONLY this field is honoured by the scheduler. Reasons, strongest first:
  - talos-linux-1.14.4            # node roll evicts grafana mid-gate; also exclusive:true on sun-attended:2026-11-01
  - teslamate-4.4.0               # HARD: every grafana start re-fetches the 11 TeslaMate dashboards from UNPINNED
                                  # teslamate master (init container download-dashboards), and that plan's section
                                  # 4.5 reads Grafana as its instrument while the TeslaMate DB schema is mid-migration
  - longhorn-1.13.0               # grafana-config is a Longhorn volume; replica/instance-manager churn during the roll
  - helm-drift-detection          # edits spec of EVERY HelmRelease incl. helmrelease/grafana: same object, attribution
  - flux-oci-chart-sources        # rewrites the chart source of HelmReleases incl. grafana (it also rolls deployment/grafana)
  - otel-operator-0.25.1          # SOFT (attribution hygiene, no technical coupling found): both gate on ns monitoring
  - edot-collector-0.163.2        # signals; keep a failed gate attributable to ONE change. Neither plan reads Grafana.
exclusive: false
security_ref: null                # not security-driven (open image findings on 13.2.4 are AR-029 accepted rows and
                                  # this bump does not change the image, so it cannot move them)
capability_change: false          # same Grafana binary (13.2.4), same config; the only functional addition is an
                                  # OPT-IN Git Sync sidecar that is OFF by default and which we do not enable
rollback_class: git-revert        # appVersion identical both sides -> no sqlite migration crossed (section 5 proves it)
finding_refs: [F-c01c08c6]        # VERIFIED 2026-10-26 via `policy-cli.py finding list --grep grafana`:
                                  # "grafana: chart 14.0.1 -> 14.1.0 (minor)", section version, PLAN lane
review: ready-for-go@2026-10-26   # plan-reviewer 2026-10-26: needs-fix on 2 small items (pod name in 2.6, unproven V3 absence gate), both fixed + re-run live by the planner; reviewer: "ready-for-go once fixed"
status: vetted
window: null                      # suggested: nightly:2026-10-29 (see section 6); the window agent assigns it
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/grafana-image-changes.md
  - docs/sops/monitoring.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-10-26"
premises:
  - id: live-chart-is-14.0.1
    why: "`current:` claims 14.0.1. If the HR already moved (manual bump, Step 0 direct-bump, another plan), the diff and rollback baseline below are stale."
    run: kubectl get helmrelease grafana -n monitoring -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: "14.0.1"
  - id: live-image-is-13.2.4-distroless
    why: "The whole git-revert argument rests on the RUNNING app being 13.2.4 with no image.tag override. A different live tag voids the appVersion analysis."
    run: kubectl get deploy grafana -n monitoring -o jsonpath='{.spec.template.spec.containers[?(@.name=="grafana")].image}'
    expect_exact: "docker.io/grafana/grafana:13.2.4-distroless"
  - id: helmrelease-ready
    why: "Never stack a bump on an already-failing release (remediation retries 3 would mask the cause)."
    run: kubectl get helmrelease grafana -n monitoring -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: no-image-tag-pin-in-values
    why: "The image follows .Chart.AppVersion only while values carry no `image:` key; a pin added since would decouple the binary from the chart and void the claim."
    run: grep -c '^    image:' kubernetes/apps/monitoring/grafana/app/helmrelease.yaml
    expect_exact: "0"
  - id: preinstall-guard-live
    why: "GF_PLUGINS_PREINSTALL_DISABLED=true is load-bearing (2026-09-12: its absence cost 2.5 days of dead TeslaMate/Pellets panels after one restart). This roll restarts the pod, so the guard must be live BEFORE we restart."
    run: kubectl get deploy grafana -n monitoring -o jsonpath='{.spec.template.spec.containers[?(@.name=="grafana")].env[?(@.name=="GF_PLUGINS_PREINSTALL_DISABLED")].value}'
    expect_exact: "true"
  - id: repo-cache-sees-target
    why: "`helm show chart ... --version 14.1.0` fails on a stale local index and is indistinguishable from the chart not existing. The local cache lacked 14.1.0 until `helm repo update grafana-community` (2026-10-26). Refresh first if this fails."
    run: helm show chart grafana-community/grafana --version 14.1.0 | grep '^version:'
    expect_exact: "version: 14.1.0"
  - id: target-chart-appversion-unchanged
    why: "THE central claim. If 14.1.0 is ever repackaged with a different appVersion, this plan is void and must be re-triaged as appVersion-moving (backup-restore rollback class)."
    run: helm show chart grafana-community/grafana --version 14.1.0 | grep '^appVersion:'
    expect_exact: "appVersion: 13.2.4"
  - id: container-set-baseline
    why: "Verification asserts the pod keeps exactly these three containers (i.e. the new sc-repositories sidecar stays off). Baseline must hold before the change."
    run: kubectl get pod -n monitoring -l app.kubernetes.io/name=grafana -o jsonpath='{.items[*].spec.containers[*].name}'
    expect_exact: "grafana-sc-dashboard grafana-sc-datasources grafana"
---

# grafana: chart 14.0.1 -> 14.1.0 (minor, appVersion 13.2.4 unchanged)

## 1) Summary & why held

**What changes.** Helm chart `grafana` (grafana-community repo, the one the in-cluster
HelmRepository `flux-system/grafana` points at) 14.0.1 -> 14.1.0. **The Grafana application
version does NOT change: appVersion is 13.2.4 on both sides**, the rendered image is
`docker.io/grafana/grafana:13.2.4-distroless` on both sides, and `app.kubernetes.io/version`
stays `13.2.4`.

**Why it was held.** `runbooks/auto-update-policy.yaml` rule `*grafana*` (`max: patch`) routes every
chart MINOR to the PLAN lane because a chart minor *can* carry the app across forward-only sqlite
migrations (grafana-config PVC), turning the rollback from `git revert` into restore-from-backup.
That is a hazard about appVersion. Measured here, it does not apply to this hop.

**Evidence (all measured 2026-10-26, nothing assumed):**

1. Chart repo `index.yaml` (`https://grafana-community.github.io/helm-charts`):
   ```
   14.1.0   appVersion 13.2.4   created 2026-10-26T09:49Z   <- target (hours old)
   14.0.1   appVersion 13.2.4   created 2026-10-16           <- live
   14.0.0   appVersion 13.2.4   created 2026-10-15
   13.7.0   appVersion 13.2.4   created 2026-10-15
   ```
   and `helm show chart grafana-community/grafana --version {14.0.1,14.1.0}` both print `appVersion: 13.2.4`.
2. Upstream release notes for `grafana-14.1.0` (grafana-community/helm-charts, the ONLY entry):
   *"[grafana] Add sidecar to provision Git Sync repositories (PR #932)"*. The v14.0.x major
   (values-schema change) is already live (commit 2259f141) and healthy; 14.1.0 is a minor on top of it.
3. Full source diff of the unpacked charts 14.0.1 vs 14.1.0: new `templates/configmap-repository-sync.yaml`,
   new `files/repository-sync.py`, new `sc-repositories` container + volumes in `_pod.tpl`, extra
   RBAC `or` terms, a `checksum/repository-sync` annotation, README, `values.yaml` +
   `values.schema.json`. **Every new template is gated on `sidecar.repositories.enabled`, whose chart
   default is `false`** (`values.yaml` line 1625) and which our HelmRelease does not set.
4. **Render diff against OUR real `spec.values`** (`helm template` of both charts fed the live values
   block): the two renders differ in exactly **one kind of line** - `helm.sh/chart: grafana-14.0.1` ->
   `grafana-14.1.0` on 14 labelled objects. No annotation, env, image, volume, container, RBAC rule,
   ConfigMap data or selector changes. `Deployment.spec.selector.matchLabels` is unchanged, so no
   immutable-selector delete/recreate. The `GF_PLUGINS_PREINSTALL_DISABLED: "true"` env and
   `[plugins] preinstall_auto_update = false` are present in the 14.1.0 render.
5. Live sqlite state: the running pod (age 3d8h, same appVersion 13.2.4) logged
   `migrations completed performed=0` on all four migrators (730/35/55/4 skipped) at its last start.
   A start on an unchanged appVersion performs no migration; this hop starts the same binary against
   the same PVC.

**The one thing that is NOT a no-op: the pod WILL restart.** The `helm.sh/chart` label sits in the
pod template (render line 646), so the Deployment rolls once (strategy `Recreate`: old pod gone and
PVC released before the new one starts; ~1-2 min Grafana unavailable, grafana.<domain> returns 5xx
meanwhile). This is the previously-hit trap: on 2026-09-12 a single restart killed the bundled
postgres/influxdb/loki/jaeger/mssql datasource backends and left every TeslaMate and Pellets panel
returning "Plugin not registered" for 2.5 days (the plugin background-installer unlinking
bundled backends on a read-only root filesystem). The guard `GF_PLUGINS_PREINSTALL_DISABLED=true`
(helmrelease.yaml, env block) now closes it; **this plan therefore treats the restart as the real
change under test and makes section 4 prove the guard held**, rather than trusting it.

Two restart side effects to expect and not misread as regressions:
- the `download-dashboards` init container re-fetches the 11 TeslaMate dashboards (+ flux/k8s/nginx) from
  `raw.githubusercontent.com` **unpinned master** on every start, so dashboard JSON can differ from what
  ran before; compare COUNTS and datasource wiring, not bytes;
- the pod re-reads `secret/elasticsearch-es-elastic-user` (finding F-03d0843d: Grafana only picks up a
  rotated ES password on restart) - if that secret rotated since the last start, the Elasticsearch
  datasource gate below is where it would show.

**Verdict.** `risk: low`, `rollback_class: git-revert`, `capability_change: false`, no reboot. The hold was
appropriate (the policy forced this measurement) and the check comes back negative: a "false-positive
hold" in the sense that the hazard named in the deny rule is absent. Whether it may run AUTO-NIGHT is in
section 6.

Not verified from here: the 14.1.0 `files/repository-sync.py` was read only to confirm it is mounted solely
under the disabled sidecar; it is not exercised by this plan.

## 2) Pre-checks

Run every premise first: `.venv/bin/python3 runbooks/plan-premises.py grafana-14.1.0 --require-premises`.
Then, in order (do not start Step 3 unless each prints the stated result):

```bash
# 2.1 Refresh the local helm index (premise repo-cache-sees-target depends on it) and confirm the target.
helm repo update grafana-community
helm show chart grafana-community/grafana --version 14.1.0 | grep -E '^(version|appVersion):'
# expect exactly: appVersion: 13.2.4 / version: 14.1.0   (anything else: STOP, plan is void)

# 2.2 Chart age gate (repo convention: no <48h-old chart unattended). 14.1.0 was created 2026-10-26T09:49Z.
python3 - <<'PY'
import datetime as d
t=d.datetime(2026,10,26,9,49,tzinfo=d.timezone.utc); age=(d.datetime.now(d.timezone.utc)-t).total_seconds()/3600
print("chart age h:",round(age,1)); print("AGE_OK" if age>=48 else "AGE_TOO_YOUNG - defer to a later night")
PY

# 2.3 No Renovate PR for grafana is open that would race the hand-edit.
gh pr list --state open --json number,title --jq '.[]|select(.title|test("grafana";"i"))|[.number,.title]|@tsv'
# expect: no output. If a PR for 14.1.0 exists, close it (comment: superseded by plan grafana-14.1.0) before Step 3.

# 2.4 Release is Ready, no in-flight reconcile, pod healthy with zero restarts.
flux get helmrelease grafana -n monitoring
kubectl get pods -n monitoring -l app.kubernetes.io/name=grafana
kubectl get pod -n monitoring -l app.kubernetes.io/name=grafana -o jsonpath='{.items[0].status.containerStatuses[*].restartCount}{"\n"}'

# 2.5 Safety net: grafana-config has a backup < 26 h old (rollback needs none, the PVC is untouched; this is the
#     belt for the unexpected). Live 2026-10-26: lastBackupAt 2026-10-25T23:04:53Z.
kubectl get volume grafana-config -n storage -o jsonpath='{.status.lastBackupAt}{"\n"}'
python3 - <<'PY'
import subprocess,datetime as d
s=subprocess.check_output(["kubectl","get","volume","grafana-config","-n","storage","-o","jsonpath={.status.lastBackupAt}"],text=True).strip()
age=(d.datetime.now(d.timezone.utc)-d.datetime.fromisoformat(s.replace("Z","+00:00"))).total_seconds()/3600
print("BACKUP_OK" if age<26 else "BACKUP_STALE %.1fh"%age)
PY

# 2.6 Same-night interference: Prometheus is this window's instrument. kube-prometheus-stack (PR #428,
#     92.11.1 -> 92.13.1) is AUTO-lane, so Step 0 of THIS window may apply it BEFORE this plan runs.
#     HONEST SCOPE: this settle check is mostly a TIMING mitigation - it cannot prevent kps from landing earlier in the
#     same window. The REAL control is that the 2.7 baselines are taken AFTER Step 0 (so a kps-driven change to the
#     dashboard count or the Prometheus pod cannot be mistaken for a Grafana regression).
kubectl get helmrelease kube-prometheus-stack -n monitoring -o jsonpath='{.status.history[0].chartVersion} {.status.history[0].status} {.status.history[0].lastDeployed}{"\n"}{.status.history[1].chartVersion}{"\n"}'
kubectl get pod prometheus-kube-prometheus-stack-0 -n monitoring -o jsonpath='{.status.containerStatuses[*].ready} startTime={.status.startTime}{"\n"}'
python3 - <<'PY'
import subprocess,json,datetime as d
def k(*a): return subprocess.check_output(["kubectl",*a],text=True)
hr=json.loads(k("get","helmrelease","kube-prometheus-stack","-n","monitoring","-o","json"))
h=hr["status"]["history"][0]
age=(d.datetime.now(d.timezone.utc)-d.datetime.fromisoformat(h["lastDeployed"].replace("Z","+00:00"))).total_seconds()/60
pod=json.loads(k("get","pod","prometheus-kube-prometheus-stack-0","-n","monitoring","-o","json"))
cs=pod["status"]["containerStatuses"]; allready=bool(cs) and all(c["ready"] for c in cs)
ok=(h["status"]=="deployed") and age>30 and allready
print("kps",h["chartVersion"],h["status"],"deployed %.0f min ago"%age,"| prometheus containers ready:",allready)
print("KPS_SETTLED" if ok else "KPS_NOT_SETTLED - wait 30 min after lastDeployed or defer one night")
PY
# PASS rule (computable): prints KPS_SETTLED = history[0].status deployed AND lastDeployed older than 30 min (a kps that was
# not touched tonight passes by age alone) AND every container of pod prometheus-kube-prometheus-stack-0 ready. A real
# StatefulSet/Prometheus CR name here is `prometheus-kube-prometheus-stack` / `kube-prometheus-stack` (verified live 2026-10-26;
# a wrong pod name makes `kubectl get pod` exit non-zero and the script raise, i.e. the check fails closed, not open).
# Live example 2026-10-26: 92.11.1 deployed 02:33Z, previous 92.11.0, pod containers true true -> KPS_SETTLED once > 30 min old.
# kps ALSO moves the dashboard count (it ships grafana_dashboard ConfigMaps via the sidecar): baselines below are mandatory.

# 2.7 BASELINES - taken AFTER Step 0 of this window, never carried over from an earlier day (record all three; section 4 compares against them, hard-coded numbers below are 2026-10-26 values).
U=$(kubectl get secret grafana-admin-secret -n monitoring -o jsonpath='{.data.admin-user}' | base64 -d)
PW=$(kubectl get secret grafana-admin-secret -n monitoring -o jsonpath='{.data.admin-password}' | base64 -d)
kubectl port-forward -n monitoring svc/grafana 33001:80 >/dev/null 2>&1 &
PF=$!; sleep 5
echo "BASE_PLUGINS=$(curl -s -u "$U:$PW" 'http://127.0.0.1:33001/api/plugins?embedded=0&type=datasource' | python3 -c 'import sys,json; print(len(json.load(sys.stdin)))')"   # 2026-10-26: 18
echo "BASE_DASH=$(curl -s -u "$U:$PW" 'http://127.0.0.1:33001/api/search?type=dash-db&limit=1000' | python3 -c 'import sys,json; print(len(json.load(sys.stdin)))')"       # 2026-10-26: 72
kill $PF; wait $PF 2>/dev/null
P=/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query
echo "BASE_PROMDS=$(kubectl get --raw "$P?query=count%28grafana_plugin_build_info%7Bplugin_type%3D%22datasource%22%7D%29" | python3 -c 'import sys,json; print(json.load(sys.stdin)["data"]["result"][0]["value"][1])')"   # 2026-10-26: 13
# GATE: BASE_PLUGINS must be 18. If it is already lower, Grafana is ALREADY degraded (the 09-12 signature is 13):
# STOP and fix that first - do not roll on top of it, the verification would "pass" against a broken baseline.
# Also confirm the Authentik SSO button is the baseline: the verification script asserts it.

# 2.8 Rehearse the gate script on the CURRENT state. FIRST save it: run the `cat > "$S/grafana-verify.sh"` heredoc from
#     section 4 now (it is only a file write). Then, with the 2.7 baselines:
#       EXPECT_CHART=14.0.1 BASE_PLUGINS=.. BASE_DASH=.. BASE_PROMDS=.. bash "$S/grafana-verify.sh"
#     It must print ALL GATES PASS. If not, the pre-state is already degraded - STOP, do not edit anything.
```

## 3) Steps (GitOps)

No alert silence needed: no Grafana-specific alert rule exists in the repo (`grep -rn "alert:.*[Gg]rafana" kubernetes`
= none) and the outage is ~1-2 min; `KubeDeploymentReplicasMismatch`-class alerts fire after 15 min.

1. Edit the chart pin in `kubernetes/apps/monitoring/grafana/app/helmrelease.yaml`. Dry-tested on a scratch
   copy on macOS (BSD sed); the resulting diff is exactly:
   ```
   11c11
   <       version: 14.0.1
   ---
   >       version: 14.1.0
   ```
   ```bash
   sed -i '' 's/^\(      version: \)14\.0\.1$/\114.1.0/' kubernetes/apps/monitoring/grafana/app/helmrelease.yaml
   git diff --stat kubernetes/apps/monitoring/grafana/app/helmrelease.yaml    # expect: 1 file, 1 insertion, 1 deletion
   ```
2. With the Edit tool, add this line to the dated history block, directly above `    deploymentStrategy:` (do not delete any prior history, it is evidence for the next planner):
   ```
       # 2026-10-xx: chart 14.1.0 - appVersion UNCHANGED at 13.2.4 (index + `helm show chart` + rendered
       # app.kubernetes.io/version), render diff vs 14.0.1 under OUR values = helm.sh/chart label only.
       # Adds an opt-in Git Sync sidecar (sidecar.repositories.enabled, default false) that we do NOT enable.
       # The pod still restarts once (label is in the pod template): re-run the datasource gate after.
       # Plan: grafana-14.1.0. Finding: F-c01c08c6.
   ```
   (Replace `xx` with the real day.) Then run `git diff` and confirm only the version line and these comment lines changed.
3. Commit, VERIFY THE SUBJECT, push (shared worktree: `--only` with explicit path; never `git add -A`):
   ```bash
   git commit --only kubernetes/apps/monitoring/grafana/app/helmrelease.yaml \
     -m "chore(grafana): chart 14.0.1 -> 14.1.0 (appVersion 13.2.4 unchanged; opt-in Git Sync sidecar left off) [plan grafana-14.1.0, finding F-c01c08c6]"
   git log -1 --format=%s     # the subject must be exactly the line above; if another session's message landed, amend BEFORE pushing
   git show --stat HEAD       # exactly one file: the helmrelease.yaml
   git push
   ```
   (Run the commit in a shell where `SWEEP_PG_DSN` is NOT sourced - it breaks the pre-commit gate.)
4. Let the push webhook reconcile Flux. Confirm the HelmRelease values/chart landed before concluding anything:
   ```bash
   kubectl get helmrelease grafana -n monitoring -o jsonpath='{.spec.chart.spec.version}{"\n"}'   # expect 14.1.0
   ```
   If it still shows 14.0.1 after 10 min (webhook slow, HelmRepository index interval), and only then:
   `flux reconcile helmrelease grafana -n monitoring --with-source`.
5. Watch the single `Recreate` roll (single replica, RWO PVC):
   ```bash
   kubectl rollout status deployment/grafana -n monitoring --timeout=300s
   kubectl get pods -n monitoring -l app.kubernetes.io/name=grafana     # NEW pod name, 3/3, restarts 0
   ```
   `rollout status` can green-light the old generation (docs: feedback rollout-status-old-generation): section 4
   independently asserts the new pod via chart version in HR history, `grafana_build_info` and pod age.
6. **Wait 90 s after the pod is Ready** (Prometheus scrape interval) before running section 4.

## 4) Verification

Floor (shape): HR Ready at 14.1.0, pod 3/3 on the new generation. The CONTENTS gates are what matter and
are all in one script so none can be skipped. Save and run it (it needs `kubectl`, `curl`, `python3`; it
port-forwards `svc/grafana` to 33001 itself and exits non-zero on any FAIL):

```bash
S=${TMPDIR:-/tmp}; cat > "$S/grafana-verify.sh" <<'EOF'
#!/usr/bin/env bash
# usage: EXPECT_CHART=14.1.0 BASE_PLUGINS=18 BASE_DASH=72 BASE_PROMDS=13 bash verify.sh
fail=0
ok()  { echo "PASS  $1"; }
bad() { echo "FAIL  $1"; fail=1; }
: "${EXPECT_CHART:?}" "${BASE_PLUGINS:?}" "${BASE_DASH:?}" "${BASE_PROMDS:?}"

# V1 release + image identity
c=$(kubectl get helmrelease grafana -n monitoring -o jsonpath='{.status.history[0].chartVersion} {.status.conditions[?(@.type=="Ready")].status}')
[ "$c" = "$EXPECT_CHART True" ] && ok "HR chart/Ready: $c" || bad "HR chart/Ready: got '$c' want '$EXPECT_CHART True'"
img=$(kubectl get deploy grafana -n monitoring -o jsonpath='{.spec.template.spec.containers[?(@.name=="grafana")].image}')
[ "$img" = "docker.io/grafana/grafana:13.2.4-distroless" ] && ok "image $img" || bad "image drifted: $img"
names=$(kubectl get pod -n monitoring -l app.kubernetes.io/name=grafana -o jsonpath='{.items[*].spec.containers[*].name}')
[ "$names" = "grafana-sc-dashboard grafana-sc-datasources grafana" ] && ok "containers: $names (no sc-repositories sidecar)" || bad "container set changed: '$names'"
lbl=$(kubectl get pod -n monitoring -l app.kubernetes.io/name=grafana -o jsonpath='{.items[*].metadata.labels.helm\.sh/chart}')
[ "$lbl" = "grafana-$EXPECT_CHART" ] && ok "pod chart label $lbl (the measured pod is the new generation)" || bad "pod chart label '$lbl' want grafana-$EXPECT_CHART (old pod still serving, or two pods)"
rdy=$(kubectl get pod -n monitoring -l app.kubernetes.io/name=grafana -o jsonpath='{.items[*].status.containerStatuses[*].ready}')
[ "$rdy" = "true true true" ] && ok "3/3 ready" || bad "readiness: '$rdy'"

# V2 the load-bearing preinstall guard survived chart+render
pv=$(kubectl get deploy grafana -n monitoring -o jsonpath='{.spec.template.spec.containers[?(@.name=="grafana")].env[?(@.name=="GF_PLUGINS_PREINSTALL_DISABLED")].value}')
[ "$pv" = "true" ] && ok "GF_PLUGINS_PREINSTALL_DISABLED=true" || bad "GF_PLUGINS_PREINSTALL_DISABLED='$pv'"
kubectl get cm grafana -n monitoring -o jsonpath='{.data.grafana\.ini}' | grep -q '^preinstall_auto_update = false' && ok "ini preinstall_auto_update=false" || bad "ini preinstall_auto_update missing"

# V3 no schema migration performed, no plugin-killer messages (log must be NON-empty: 4 migrators print performed=0)
L=$(kubectl logs -n monitoring deploy/grafana -c grafana)
nz=$(printf '%s\n' "$L" | grep -c 'migrations completed.*performed=[1-9]')
z=$(printf '%s\n' "$L" | grep -c 'migrations completed.*performed=0')
{ [ "$nz" = 0 ] && [ "$z" -ge 4 ]; } && ok "migrations: performed=0 x$z, nonzero x$nz" || bad "migrations: performed=0 x$z, nonzero x$nz (need 0 and >=4)"
ro=$(printf '%s\n' "$L" | grep -i -c -e 'read-only file system' -e 'unlinkat')
[ "$ro" = 0 ] && ok "no read-only-fs plugin-installer errors" || bad "plugin-installer read-only-fs errors x$ro"

# V4 CONTENTS via API
U=$(kubectl get secret grafana-admin-secret -n monitoring -o jsonpath='{.data.admin-user}' | base64 -d)
PW=$(kubectl get secret grafana-admin-secret -n monitoring -o jsonpath='{.data.admin-password}' | base64 -d)
kubectl port-forward -n monitoring svc/grafana 33001:80 >/dev/null 2>&1 &
PF=$!; sleep 5
A="http://127.0.0.1:33001"
np=$(curl -s -u "$U:$PW" "$A/api/plugins?embedded=0&type=datasource" | python3 -c 'import sys,json; print(len(json.load(sys.stdin)))' 2>/dev/null)
[ "$np" = "$BASE_PLUGINS" ] && ok "datasource plugins = $np" || bad "datasource plugins = '$np' want $BASE_PLUGINS (13 = the 2026-09-12 preinstall-killer signature)"
for uid in prometheus elasticsearch influxdb unpoller-influxdb pellets TeslaMate; do
  s=$(curl -s -u "$U:$PW" -X POST "$A/api/datasources/uid/$uid/health" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("status"))' 2>/dev/null)
  [ "$s" = "OK" ] && ok "datasource $uid health OK" || bad "datasource $uid health='$s'"
done
am=$(curl -s -u "$U:$PW" "$A/api/datasources/proxy/uid/alertmanager/api/v2/status" | python3 -c 'import sys,json; print("cluster" in json.load(sys.stdin))' 2>/dev/null)
[ "$am" = "True" ] && ok "alertmanager proxy returns status" || bad "alertmanager proxy: '$am'"
q=$(curl -s -u "$U:$PW" -H 'Content-Type: application/json' -X POST "$A/api/ds/query" -d '{"from":"now-5m","to":"now","queries":[{"refId":"A","datasource":{"uid":"prometheus","type":"prometheus"},"expr":"count(kube_pod_info)","instant":true,"range":false}]}' | python3 -c '
import sys,json
d=json.load(sys.stdin); f=d["results"]["A"]["frames"][0]["data"]["values"]; print(int(f[1][-1]))' 2>/dev/null)
case "$q" in ''|*[!0-9]*) bad "ds/query count(kube_pod_info)='$q'";; *) [ "$q" -gt 50 ] && ok "ds/query count(kube_pod_info)=$q" || bad "ds/query suspiciously low: $q";; esac
nd=$(curl -s -u "$U:$PW" "$A/api/search?type=dash-db&limit=1000" | python3 -c 'import sys,json; print(len(json.load(sys.stdin)))' 2>/dev/null)
[ "$nd" = "$BASE_DASH" ] && ok "dashboards = $nd" || bad "dashboards = '$nd' want $BASE_DASH"
ds=$(curl -s -u "$U:$PW" "$A/api/datasources" | python3 -c 'import sys,json; print(",".join(sorted(x["uid"] for x in json.load(sys.stdin))))' 2>/dev/null)
[ "$ds" = "TeslaMate,alertmanager,elasticsearch,influxdb,pellets,prometheus,unpoller-influxdb" ] && ok "7 provisioned datasources: $ds" || bad "datasource set: '$ds'"
ob=$(curl -s -u "$U:$PW" "$A/api/frontend/settings" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("oauth",{}).get("generic_oauth",{}).get("name"))' 2>/dev/null)
[ "$ob" = "Authentik" ] && ok "Authentik SSO button present" || bad "Authentik SSO oauth block: '$ob'"
kill $PF 2>/dev/null; wait $PF 2>/dev/null

# V5 Prometheus sees the new pod (scrape interval lag: caller waits >=75 s after pod Ready)
P=/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query
pq() { kubectl get --raw "$P?query=$(python3 -c 'import sys,urllib.parse;print(urllib.parse.quote(sys.argv[1]))' "$1")" | python3 -c 'import sys,json; r=json.load(sys.stdin)["data"]["result"]; print(r[0]["value"][1] if r else "EMPTY")'; }
u=$(pq 'up{job="grafana"}'); [ "$u" = "1" ] && ok "up{job=grafana}=1" || bad "up{job=grafana}='$u'"
bv=$(kubectl get --raw "$P?query=grafana_build_info" | python3 -c 'import sys,json; r=json.load(sys.stdin)["data"]["result"]; print(",".join(sorted(x["metric"]["version"] for x in r)))')
[ "$bv" = "13.2.4" ] && ok "grafana_build_info version=$bv" || bad "grafana_build_info versions='$bv'"
pm=$(pq 'count(grafana_plugin_build_info{plugin_type="datasource"})'); [ "$pm" = "$BASE_PROMDS" ] && ok "datasource plugins in metrics=$pm" || bad "datasource plugins in metrics='$pm' want $BASE_PROMDS"
sd=$(pq 'grafana_stat_totals_dashboard'); [ "$sd" = "$BASE_DASH" ] && ok "grafana_stat_totals_dashboard=$sd" || bad "grafana_stat_totals_dashboard='$sd' want $BASE_DASH"
echo; [ $fail = 0 ] && echo "ALL GATES PASS" || echo "GATE FAILURE - see FAIL lines (rollback per section 5)"
exit $fail
EOF
EXPECT_CHART=14.1.0 BASE_PLUGINS=<from 2.7> BASE_DASH=<from 2.7> BASE_PROMDS=<from 2.7> bash "$S/grafana-verify.sh"
```

The script was rehearsed 2026-10-26 against the LIVE pre-change state with `EXPECT_CHART=14.0.1`
(`ALL GATES PASS`) and with deliberately wrong expectations
(`EXPECT_CHART=14.1.0 BASE_PLUGINS=19`) where it printed exactly the two expected `FAIL` lines
and exited 1 - so the gates are known to be able to fail. One bug found and fixed in rehearsal:
`grep -v 'performed=0'` over the migration log reads 1, not 0, on a healthy pod, because Grafana
prints `Unified storage migrations completed successfully` (no `performed=`); the gate therefore counts
`performed=[1-9]` (must be 0) AND `performed=0` (must be >= 4, so an empty log cannot pass).

Negative control for the absence gate (log must be able to print non-zero through the IDENTICAL command). Replayed
2026-10-26 on a synthetic line modelled on the quoted 2026-09-12 failure; the same pipeline over a clean line prints 0:
```bash
printf 'logger=plugin.backgroundinstaller level=error msg="unlinkat /usr/share/grafana/data/plugins-bundled/postgres: read-only file system"\n' | grep -i -c -e 'read-only file system' -e 'unlinkat'   # prints 1
printf 'logger=settings level=info msg="ok"\n' | grep -i -c -e 'read-only file system' -e 'unlinkat'                                                  # prints 0
```
(Also note the `grep -c` over a captured `$L` variable in the script is the same grep; an empty `$L` would be caught by the
`performed=0 >= 4` gate, so an unreadable log cannot make this gate pass vacuously.)

What each gate guards against, and what its failure prints:

| Gate | Failure it guards against | Failure output |
|---|---|---|
| HR `chartVersion Ready` = `14.1.0 True` | Flux still on 14.0.1 / remediation rolled back | `FAIL HR chart/Ready: got '14.0.1 True'` |
| image `13.2.4-distroless` | tag drift - the premise of the git-revert class | `FAIL image drifted: ...` |
| pod label `helm.sh/chart` == `grafana-$EXPECT_CHART` | measuring the OLD pod (`grafana_build_info` reads 13.2.4 on both generations, so only this and HR history discriminate) | `FAIL pod chart label 'grafana-14.0.1' want grafana-14.1.0` |
| containers == 3 named | the new `sc-repositories` sidecar appearing (feature switched on by accident) | `FAIL container set changed` |
| `GF_PLUGINS_PREINSTALL_DISABLED=true` env + ini `preinstall_auto_update = false` | chart render dropping/renaming the guard - recreates the 2026-09-12 outage on the NEXT restart | `FAIL GF_PLUGINS_PREINSTALL_DISABLED=''` |
| log: `performed=[1-9]` count 0, `performed=0` count >= 4 | any sqlite migration (rollback class would silently become backup-restore) | `FAIL migrations: ... nonzero x1` |
| log: no `read-only file system` / `unlinkat` (case-insensitive) | the background installer killing bundled backends | `FAIL plugin-installer read-only-fs errors x3` |
| API `/api/plugins?type=datasource` count == baseline (18) | stripped/killed bundled backends; **13 is the measured 2026-09-12 signature** | `FAIL datasource plugins = '13' want 18` |
| 6 datasource `/health` == `OK` + alertmanager proxy `cluster` key + `/api/ds/query` numeric (`from`/`to` mandatory, else a healthy Grafana returns empty) | dead plugin, bad ES secret (401 after restart), unreachable DB | `FAIL datasource TeslaMate health='ERROR'` |
| dashboards == baseline (72 on 2026-10-26) | `download-dashboards` init writing 0-byte files on a GitHub fetch failure; sidecar provisioning broken | `FAIL dashboards = '55' want 72` |
| 7 datasource UIDs exact set | provisioning (`deleteDatasources` + `datasources.yaml`) regression | `FAIL datasource set: ...` |
| `/api/frontend/settings` oauth name `Authentik` | SSO wiring (F-5a894d0e) lost in the re-render | `FAIL Authentik SSO oauth block: 'None'` |
| Prometheus `up{job="grafana"}` == 1, `grafana_build_info` version `13.2.4`, datasource-plugin series == baseline (13), `grafana_stat_totals_dashboard` == baseline | ServiceMonitor label/selector lost the target; stale old-pod series | `FAIL up{job=grafana}='EMPTY'` |

CONTENTS ASSERTION: the bundled datasource backends and the provisioned datasources survived the restart -
measured by `/api/plugins?embedded=0&type=datasource` count and six `/api/datasources/uid/<uid>/health` calls plus a real
`/api/ds/query` (not a connection test), compared to the section 2.7 baseline (18 plugins, 7 datasources, 72 dashboards on 2026-10-26).

CONTROL: metric up - `up{job="grafana"}` must be 1 on the new pod (verified live 2026-10-26: 1)
CONTROL: metric grafana_build_info - `version` label must be exactly `13.2.4` (verified live: `release-13.2.4#patched`, version 13.2.4)
CONTROL: metric grafana_plugin_build_info - `count(...{plugin_type="datasource"})` must equal the section 2.7 baseline (live 2026-10-26: 13)
CONTROL: metric grafana_stat_totals_dashboard - must equal the section 2.7 dashboard baseline (live: 72)

No alertname control: the repo carries no Grafana-specific PrometheusRule, and asserting a generic alert here would be a
gate that cannot fail on the property under change.

**PASS** = script prints `ALL GATES PASS` (exit 0). Additionally open the UI once as a human-equivalent check
only if attended: `/login` shows the Authentik button (asserted by the script already) - no manual step is required.

## 5) Rollback

Everything this plan changes is the chart pin (+ a comment). No sqlite migration is crossed in either direction
(appVersion 13.2.4 -> 13.2.4; the `performed=0` gate proves it from the running pod), no PVC content is rewritten, no
CRD is installed (the chart has none), so a plain revert is a complete rollback.

```bash
git revert --no-edit <bump-commit-sha>
git log -1 --format=%s        # confirm the revert subject is yours before pushing
git push
# if webhook slow after 10 min: flux reconcile helmrelease grafana -n monitoring --with-source
kubectl rollout status deployment/grafana -n monitoring --timeout=300s
```
Confirm back: `kubectl get helmrelease grafana -n monitoring -o jsonpath='{.status.history[0].chartVersion}'` = `14.0.1`,
then re-run the section 4 script with `EXPECT_CHART=14.0.1` and the same baselines. **The revert is a SECOND pod restart**:
the preinstall guard and datasource gates apply to it exactly as to the forward roll, so do not skip the re-run.

Trigger rollback on any `FAIL` that persists after one further 2-minute settle (scrape lag, init-container fetch). Per
`docs/sops/grafana-image-changes.md` section 4 step 7 do not debug in place: monitoring is the instrument you would debug with.

If, against the evidence, the PVC itself is damaged (Grafana fails to open `grafana.db`, or dashboards/users vanish):
restore Longhorn volume `grafana-config` (namespace `storage`) from its latest backup per `docs/sops/backup.md`
(backup job `storage/daily-backup-all-volumes`; `lastBackupAt` recorded in 2.5). Not expected: no write path to the DB
differs from a plain restart on the same binary.

## 6) Interference notes

- **No shared infra is restarted.** Grafana is a tenant of `monitoring`. kube-prometheus-stack runs `grafana.enabled: false`,
  so this HelmRelease is the only owner; nothing else reconciles Grafana.
- **kube-prometheus-stack PR #428 (92.11.1 -> 92.13.1)** - parked by the 48h gate (opened 2026-10-24T22:02Z; the 48h gate counts
  UPSTREAM release age, which I did not measure, so "eligible from the 2026-10-27 nightly" is approximate). It is auto-lane, so it cannot be named in `conflicts_with` (there is
  no plan file; a ref to a non-plan is a DEAD-REF). It matters twice: Prometheus rolling makes the section 4 Prometheus
  gates unreadable/unattributable, and kps ships `grafana_dashboard` ConfigMaps that the Grafana sidecar loads, so it can
  move the dashboard count. Handled by pre-check 2.6 (timing mitigation only: Step 0 of the same window can still apply kps before this plan
  runs) and, as the real control, by taking BASELINES at execution time AFTER Step 0 (2.7). Suggested placement tends
  to keep a night between them (kps approx. nightly:2026-10-27, this plan nightly:2026-10-29) but that is not guaranteed.
- **`teslamate-4.4.0` (nightly:2026-11-06, schema migration, its section 4.5 reads Grafana)** - hard conflict, see frontmatter:
  a Grafana restart re-pulls unpinned TeslaMate master dashboards, which may already target 4.4.0 while the DB is on 4.3.0.
  Never the same night; this plan runs first (it is earlier).
- **`otel-operator-0.25.1` (sat-attended:2026-11-07) / `edot-collector-0.163.2` (nightly:2026-11-10)** - checked, NO technical
  coupling: neither reads Grafana (grep of both plans = 0 hits), Grafana's Elasticsearch datasource reads ES not the collector,
  and a Grafana roll does not touch the OTLP path. Listed in `conflicts_with` as attribution hygiene only; at the suggested date they
  are 9 and 12 days apart, so it costs nothing. If a reviewer prefers fewer declared conflicts, these two are the removable ones.
- **`talos-linux-1.14.4` (sun-attended:2026-11-01, exclusive)** - the slot is exclusive anyway; the earlier nightly:2026-10-29 also
  leaves two clear days, so a failed Grafana gate cannot spill into the node roll.
- **`longhorn-1.13.0` (sun-attended:2026-11-15), `helm-drift-detection` (sat 11-07), `flux-oci-chart-sources` (sun 11-22)** - each touches
  the Longhorn volume or the HelmRelease object itself; declared as conflicts so a rollout cause stays singular.
- **Old plan `grafana-chart-13.2.3` is SUPERSEDED**: its frontmatter says `status: superseded` (2026-09-14: the deny rule was
  narrowed to `max: patch` and the patch lane took over). Its `target: 13.2.4` / `current: 13.2.1` are two majors behind live
  14.0.1, it carries `finding_refs: [F-cce839da]`, and nothing in this plan depends on it. The file itself is retire-on-sight
  (git has it) - left untouched here because this planner may only write its own file. Its useful methodology (datasource gate,
  appVersion premise, cache-staleness gotcha) is reused above.
- **Window placement.** Suggested `nightly:2026-10-29` (earliest night where the chart is >= 48 h old: 14.1.0 was published
  2026-10-26 09:49Z, so nightly:2026-10-28 03:30 is only ~42 h). 20 min, risk weight 1, fits the 90-min nightly
  (capacity_risk 6) with the existing 10-29 load (nextcloud-whiteboard, low, 15 min). Fallback: sat-attended:2026-10-31.
- **Could this be AUTO-class?** Yes, by the derivation in `runbooks/autonomy-policy.yaml`: `capability_change: false` +
  `rollback_class: git-revert` + `needs_reboot: false` + empty `shared` + `risk: low` = AUTO-NIGHT, and with a
  `review: ready-for-go@<date>` from the plan-reviewer it meets the SD-10 pre-approval (nightly, no operator GO, premises
  re-checked at runtime). Two honest caveats: (a) the `*grafana*` deny rule (`max: patch`) will keep every future minor in the
  PLAN lane even though the hazard it names (appVersion) is mechanically checkable - narrowing it to "held only if the target
  chart's appVersion differs from the live one" is an operator decision, not mine, and would need a premise-style gate in the
  auto-updater; (b) the section 4 script needs `kubectl port-forward` and the admin secret, so an unattended run depends on the
  window agent executing it, not merely reading Flux status.
- **No node reboot.** Single replica, `Recreate`, RWO PVC already handled; no change to that config.
