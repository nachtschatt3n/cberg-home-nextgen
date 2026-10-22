---
plan_id: grafana-13.7.0
component: grafana
pr: 312                             # Renovate "update grafana ( 13.2.7 -> 13.7.0 )" (newest stable on the 13.x line).
                                    # PR #250 (13.2.8) is obsolete once this lands. PR #374 (14.0.1 MAJOR) -> plan grafana-14.0.1.
kind: chart
current: "13.2.7"
target: "13.7.0"
update_type: minor
risk: medium                        # chart minor that MOVES appVersion 13.2.3 -> 13.2.4 (grafana binary patch); a
                                    # patch can still run a forward sqlite/unified-storage migration (gate 4.3).
est_duration_min: 25
needs_reboot: false
touches:
  namespaces: [monitoring]
  resources:
    - helmrelease/monitoring/grafana
    - deployment/monitoring/grafana            # one Recreate roll: grafana 13.2.3 -> 13.2.4-distroless, both k8s-sidecar 2.11.2 -> 2.14.1, init curl 8.22.0 -> 8.23.0
    - kustomization/monitoring/grafana
    - pvc/monitoring/grafana-config            # sqlite + unified storage; new binary opens it
    - configmap/monitoring/grafana
    - servicemonitor/monitoring/grafana        # label churn only
    - httproute/monitoring/grafana             # unchanged; UI down ~1-2 min during Recreate
    - kubernetes/apps/monitoring/grafana/app/helmrelease.yaml
  shared: [monitoring]                # Grafana is the monitoring UI; also reads datasources prometheus, elasticsearch, influxdb x2, postgres x2, alertmanager
depends_on: []
conflicts_with:
  - flux-oci-chart-sources            # swaps grafana's chart source AND rolls deployment/grafana
  - helm-drift-detection              # writes a field on every HelmRelease incl. grafana
  - flux-reconciler-impersonation     # changes how helm-controller reconciles every HR (exclusive)
  - flux-fleet-0.60.0                 # helm-controller swap mid-upgrade would confound 4.1
  - flux-distribution-2.9.6           # exclusive
  - talos-linux-1.14.2                # exclusive node roll; evicts grafana
  - talos-linux-1.14.4                # exclusive node roll; evicts grafana
  - kube-prometheus-stack-92.2.0      # exclusive; this plan's 4.5 reads Prometheus (shared instrument)
  - kube-prometheus-stack-92.10.1     # exclusive; same reason; its bundled-grafana-inert premise also reads grafana chart versions
  - kube-prometheus-stack-92.11.0     # exclusive; its gates read Prometheus/monitoring (shared instrument): never the same window (reviewer 2026-10-22)
  - spegel-0.8.0                      # registry mirror: a mid-roll change could stall the 3 image pulls
exclusive: false
security_ref: F-fcb94b29              # open row on the grafana 13.2.3 image; target image 13.2.4 is the fix.
                                      # Detail stays on the DB record (docs/sops/vulnerability-disclosure.md).
capability_change: false              # same product line, no new route/permission/exposure; chart additions are unset-by-default knobs
rollback_class: git-revert            # holds IF gate 4.3 shows no migration; the in-window decision rule is in section 5
finding_refs: [F-c01c08c6, F-fcb94b29]
review: ready-for-go@2026-10-22   # plan-reviewer 2026-10-22: needs-fix (missing kube-prometheus-stack-92.11.0 conflict) -> fixed; render/migrator/backup/gates verified; premises 10/10
status: vetted
window: "now:2026-10-22"   # ON-DEMAND NOW run 2026-10-22 (run-now.py stamp; was None)
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/grafana-image-changes.md
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/backup.md
premises:
  - id: live-chart-pre-change
    why: "Diff/rollback baseline. 13.2.8 accepted (Step 0 may land PR #250 first; render-identical). Anything else = stale plan."
    run: kubectl get helmrelease grafana -n monitoring -o jsonpath='{.spec.chart.spec.version}'
    expect_matches: "^13\\.2\\.[78]$"
  - id: helmrelease-ready
    why: "Do not stack a bump on an already-failing release."
    run: kubectl get helmrelease grafana -n monitoring -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: live-grafana-image-13.2.3-distroless
    why: "Pre-change binary baseline; if something else runs, the rollback analysis is unproven."
    run: kubectl get deploy grafana -n monitoring -o jsonpath='{.spec.template.spec.containers[?(@.name=="grafana")].image}'
    expect_exact: "docker.io/grafana/grafana:13.2.3-distroless"
  - id: no-image-override
    why: "An image.tag/repository override would decouple the container from the chart appVersion and void this analysis."
    run: kubectl get helmrelease grafana -n monitoring -o jsonpath='{.spec.values.image}' | wc -c | tr -d ' '
    expect_exact: "0"
  - id: no-sidecar-image-override
    why: "The sidecar move comes from the chart default."
    run: kubectl get helmrelease grafana -n monitoring -o jsonpath='{.spec.values.sidecar.image}' | wc -c | tr -d ' '
    expect_exact: "0"
  - id: preinstall-disabled
    why: "Load-bearing on distroless: any restart without it lets the plugin installer kill bundled datasource backends (2026-09-12 incident)."
    run: kubectl get deploy grafana -n monitoring -o jsonpath='{.spec.template.spec.containers[?(@.name=="grafana")].env[?(@.name=="GF_PLUGINS_PREINSTALL_DISABLED")].value}'
    expect_exact: "true"
  - id: repo-cache-has-target
    why: "Local helm index must know the target (run `helm repo update grafana-community` first). Alias grafana-community = the URL behind flux-system/grafana; the alias `grafana` is a DIFFERENT frozen repo."
    run: helm show chart grafana-community/grafana --version 13.7.0 | grep '^version:'
    expect_exact: "version: 13.7.0"
  - id: target-appversion-13.2.4
    why: "CENTRAL CLAIM. Target ships appVersion 13.2.4 (patch of the running 13.2.3). A different value (e.g. 13.3.x) means a bigger binary jump -> re-plan."
    run: helm show chart grafana-community/grafana --version 13.7.0 | grep '^appVersion:'
    expect_exact: "appVersion: 13.2.4"
  - id: target-sidecar-default-2.14.1
    why: "Sidecar assessed in section 1 is the chart default of the target."
    run: helm show values grafana-community/grafana --version 13.7.0 | grep -A1 'kiwigrid/k8s-sidecar$' | grep 'tag:'
    expect_contains: "tag: 2.14.1"
  - id: grafana-config-backup-exists
    why: "Proves a backup EXISTS (plan-premises.py refuses python3 as a run command). FRESHNESS (<26h) is the section 2 STOP gate."
    run: kubectl get volume grafana-config -n storage -o jsonpath='{.status.lastBackupAt}'
    expect_matches: "^20[0-9]{2}-[0-9]{2}-[0-9]{2}T"
generated: "2026-10-22"
---

# grafana: chart 13.2.7 -> 13.7.0 (Grafana 13.2.3 -> 13.2.4; k8s-sidecar 2.11.2 -> 2.14.1)

## 1) Summary & why held

**Why held.** `runbooks/auto-update-policy.yaml` rule `*grafana*` is `max: patch`; a chart minor
may move appVersion across forward-only sqlite migrations. This section states what it moves.

**Newest stable per line (measured 2026-10-22, `helm search repo grafana-community/grafana -l`):**
13.x head = **13.7.0** (appVersion 13.2.4); 14.0.1 (appVersion 13.2.4) is the only newer chart and
is a chart MAJOR with the SAME binary (see plan `grafana-14.0.1`). 13.5.0 (old draft target,
appVersion 13.2.3) is superseded: 13.5.1+ is the first line that ships 13.2.4.

**What moves (render diff of `helm template` 13.2.7 vs 13.7.0 fed the live `spec.values`; all lines
other than `helm.sh/chart` / `app.kubernetes.io/version` labels):**
- grafana `13.2.3-distroless` -> `13.2.4-distroless` (tag published 2026-10-13, Docker Hub). The one real
  risk. Upstream 13.2.4 notes: security fixes, alerting/provisioning/dashboard-store fixes; no breaking
  change listed.
- both sidecars `k8s-sidecar` `2.11.2` -> `2.14.1` (no `src/` change upstream; Python `kubernetes`
  client 32 -> 36; analysis in retired plan `grafana-13.5.0` section 1).
- init `curl` `8.22.0` -> `8.23.0` (download-dashboards init container).
- Nothing else: new `serviceMonitor.scrape*`, `imageRenderer.readinessProbe`, `podManagementPolicy`
  are unset/unrendered for our values (Deployment, no image-renderer). Selector unchanged.

**Why a patch binary still gets a plan.** Grafana 13 migrates the sqlite schema on boot. A patch seldom
adds a migration but may, and a downgrade after one is not guaranteed. Gate 4.3 reads the migrator
output; section 5 gives the decision rule. A fresh Longhorn backup is the STOP gate.

**Security relevance:** `security_ref: F-fcb94b29` (the image row; this bump is its fix).

**Verdict.** risk medium, no reboot, one Recreate roll (~1-2 min UI gap, alerting unaffected),
`capability_change: false`, `rollback_class: git-revert` conditional on 4.3.

## 2) Pre-checks (all STOP gates; an unattended run that fails any of them stops with the repo untouched)

```bash
cd /Users/mu/code/cberg-home-nextgen
helm repo update grafana-community >/dev/null
.venv/bin/python3 runbooks/plan-premises.py grafana-13.7.0       # all premises PASS
```
**STOP gate 2.1: target images are published** (a missing tag leaves ImagePullBackOff with the old pod gone):
```bash
curl -s https://hub.docker.com/v2/repositories/grafana/grafana/tags/13.2.4-distroless | python3 -c 'import sys,json;print(json.load(sys.stdin).get("name"))'
# PASS: 13.2.4-distroless. FAIL: prints None (control: tag 13.99.9-distroless returns {"message":"..."} -> None).
curl -s 'https://quay.io/api/v1/repository/kiwigrid/k8s-sidecar/tag/?specificTag=2.14.1' | python3 -c 'import sys,json;print([t["name"] for t in json.load(sys.stdin)["tags"]])'
# PASS: ['2.14.1']. FAIL: [].
curl -s https://hub.docker.com/v2/repositories/curlimages/curl/tags/8.23.0 | python3 -c 'import sys,json;print(json.load(sys.stdin).get("name"))'
# PASS: 8.23.0.
```
**STOP gate 2.2: backup freshness of the grafana volume** (restore point for the migration branch):
```bash
.venv/bin/python3 runbooks/longhorn-backup-age.py grafana-config --max-hours 26
# PASS: prints "FRESH <h> via backup-cr backup=backup-..." (2026-10-22: FRESH 19.4h, backup-f1e83cd96a3149d3). Record the backup name.
# FAIL: prints STALE/error -> STOP; do not edit git.
```
**Baseline** (record BASE_* ; live values 2026-10-22 in comments). Scratch dir `$W` holds scripts:
```bash
W=$(mktemp -d); export W
U=$(kubectl -n monitoring get secret grafana-admin-secret -o jsonpath='{.data.admin-user}' | base64 -d)
P=$(kubectl -n monitoring get secret grafana-admin-secret -o jsonpath='{.data.admin-password}' | base64 -d); export U P
kubectl -n monitoring port-forward svc/grafana 33011:80 >/dev/null 2>&1 & PF=$!; sleep 4
curl -s http://127.0.0.1:33011/api/health            # {"database":"ok","version":"13.2.3",...}
curl -s -u "$U:$P" 'http://127.0.0.1:33011/api/plugins?embedded=0&type=datasource' | python3 -c 'import sys,json;print("ds_plugins="+str(len(json.load(sys.stdin))))'   # BASE_DS=18
cat > $W/prov.py <<'PY'
import os, json, base64, urllib.request
a = "Basic " + base64.b64encode(f"{os.environ['U']}:{os.environ['P']}".encode()).decode()
def g(p):
    return json.load(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:33011" + p, headers={"Authorization": a})))
ds = g("/api/search?type=dash-db&limit=5000"); prov = err = 0
for d in ds:
    try: prov += bool(g("/api/dashboards/uid/" + d["uid"])["meta"].get("provisioned"))
    except Exception: err += 1
print(f"dashboards={len(ds)} provisioned={prov} fetch_errors={err}")
PY
python3 $W/prov.py                                    # BASE: dashboards=72 provisioned=65 fetch_errors=0
kill $PF
kubectl get cm,secret -A -l grafana_dashboard -o name | wc -l      # BASE_SC=37
```
(The prov.py above was run live 2026-10-22 and printed the BASE line.) The old pod's sidecar log has
rotated (10 days of output, no `Writing` lines), so the sidecar baseline is the object count BASE_SC,
not a log count.

## 3) Steps (GitOps)

1. Edit the pin (BSD sed, dry-tested 2026-10-22 on a scratch copy; diff is exactly
   `11c11 <       version: 13.2.7 --- >       version: 13.7.0`):
   ```bash
   sed -i '' -E 's/^      version: 13\.2\.[78]$/      version: 13.7.0/' kubernetes/apps/monitoring/grafana/app/helmrelease.yaml
   git diff --stat kubernetes/apps/monitoring/grafana/app/helmrelease.yaml   # expect 1 insertion, 1 deletion; "0" = premise should have stopped you
   ```
2. Commit only that path and verify before pushing:
   ```bash
   git commit --only kubernetes/apps/monitoring/grafana/app/helmrelease.yaml -m "chore(grafana): chart 13.2.x -> 13.7.0 (Grafana 13.2.3 -> 13.2.4, sidecar 2.14.1) [plan grafana-13.7.0, PR #312]"
   git log -1 --format=%s      # must be the subject above; amend if not
   git show --stat HEAD        # only helmrelease.yaml
   git push
   ```
3. If the webhook has not reconciled within ~2 min: `flux reconcile kustomization grafana -n monitoring --with-source`,
   then `kubectl get hr grafana -n monitoring -o jsonpath='{.spec.chart.spec.version}'` must print 13.7.0.
4. `kubectl rollout status deployment/grafana -n monitoring --timeout=300s` (can green-light the old generation; 4.1 checks the pod).

## 4) Verification (each gate states its failure)

Re-create `$W`/`U`/`P` if the shell changed (section 2 block).

**4.1 New pod, new binary, health.**
```bash
kubectl get hr grafana -n monitoring -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion}{"\n"}'
# PASS "True 13.7.0". FAIL False / 13.2.x.
POD=$(kubectl -n monitoring get pods -l app.kubernetes.io/name=grafana -o jsonpath='{.items[0].metadata.name}')
kubectl -n monitoring get pod $POD -o jsonpath='{.metadata.labels.helm\.sh/chart} {.status.startTime}{"\n"}{range .status.containerStatuses[*]}{.name} {.image} {.imageID} restarts={.restartCount}{"\n"}{end}'
# PASS: grafana-13.7.0; startTime after the push; grafana -> grafana/grafana:13.2.4-distroless, both sidecars -> k8s-sidecar:2.14.1,
#       imageID digest DIFFERENT from sha256:202e5d5b3f85... (the 13.2.3 pod's digest); restarts=0 everywhere.
# FAIL: old chart label/digest = stale pod; restarts>0 = crashing image.
kubectl -n monitoring port-forward svc/grafana 33011:80 >/dev/null 2>&1 & PF=$!; sleep 4
curl -s http://127.0.0.1:33011/api/health | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["version"], d["database"])'
# PASS "13.2.4 ok". FAIL: "13.2.3 ..." (old binary), database != ok, or JSON parse error (not up).
```
**4.2 Sidecar contents.**
```bash
kubectl -n monitoring get pod $POD -o jsonpath='{range .status.initContainerStatuses[*]}{.name} {.state.terminated.reason} {.state.terminated.exitCode}{"\n"}{end}'
# PASS: init-chown-data and download-dashboards both "Completed 0". FAIL: a curl (22) = upstream grafana.com/GitHub 404, not this bump.
kubectl -n monitoring logs $POD -c grafana-sc-dashboard | grep -c '"msg": "Writing '      # PASS: >= BASE_SC (37). FAIL: fewer = the watch missed objects.
kubectl -n monitoring logs $POD -c grafana-sc-dashboard | grep -c 'Response: 200 OK.*Dashboards config reloaded'   # PASS >=1. FAIL 0 = reload never accepted.
kubectl -n monitoring logs $POD -c grafana-sc-dashboard | grep -ciE 'segmentation|sigsegv|"level": "ERROR"'      # PASS 0.
```
Known pre-existing noise: one sidecar logs `Address in use` on health port 8080; up to 5 `Retrying localhost:3000` while Grafana boots.
If the "Writing" count reads 0 but dashboards (below) are intact, the 2.14.1 log wording may differ: treat the dashboards gate as authoritative, record it, do not fail on wording alone.

**4.3 Migrations and dashboards (the gate that decides the rollback class).**
```bash
kubectl -n monitoring logs $POD -c grafana | grep 'msg="migrations completed"' | awk '{n++; if ($0 !~ /performed=0 /) bad++} END{print "lines="n+0, "nonzero="bad+0}'
# Live old pod 2026-10-22: 4 lines, all performed=0. PASS: lines=4 nonzero=0 (rollback stays git-revert).
# nonzero>0 = a forward migration ran -> section 5 "migration ran" rule. lines=0 = log not read -> investigate, do not pass.
python3 $W/prov.py
# PASS: dashboards == 72, provisioned >= 65, fetch_errors=0. FAIL: any count falls (provisioning dropped dashboards, e.g. TeslaMate set).
```
**4.4 Datasources and plugins (mandatory after any Grafana restart; GF_PLUGINS_PREINSTALL_DISABLED hazard).**
```bash
curl -s -u "$U:$P" 'http://127.0.0.1:33011/api/plugins?embedded=0&type=datasource' | python3 -c 'import sys,json; print("ds_plugins="+str(len(json.load(sys.stdin))))'
# PASS: >= 18 (BASE_DS). FAIL: a drop (13 on 2026-09-12) = bundled backends killed.
for uid in prometheus elasticsearch influxdb unpoller-influxdb pellets TeslaMate; do
  printf '%s -> ' $uid
  curl -s -u "$U:$P" "http://127.0.0.1:33011/api/datasources/uid/$uid/health" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("status"), str(d.get("message",""))[:60])'
done
# PASS: OK for all six. FAIL: ERROR, or None + plugin.notRegistered. (uids verified live 2026-10-22 via /api/datasources; no secrets printed.)
curl -s -u "$U:$P" -o /dev/null -w 'alertmanager_proxy=%{http_code}\n' 'http://127.0.0.1:33011/api/datasources/proxy/uid/alertmanager/api/v2/status'   # PASS 200
curl -s -u "$U:$P" -H 'Content-Type: application/json' -X POST 'http://127.0.0.1:33011/api/ds/query' \
  -d '{"from":"now-5m","to":"now","queries":[{"refId":"A","datasource":{"uid":"prometheus","type":"prometheus"},"expr":"count(kube_pod_info)","instant":true,"range":false}]}' \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); print("pods="+str(d["results"]["A"]["frames"][0]["data"]["values"][1][0]))'
# PASS: positive integer. FAIL: KeyError/IndexError traceback (no data through the query path).
kill $PF
kubectl -n monitoring logs $POD -c grafana | grep -ciE 'plugin.*not (found|registered)|read-only file system'    # PASS 0
```
**4.5 Scrape and build info** (skip with a note if a kube-prometheus-stack plan ran the same night):
```bash
kubectl -n monitoring port-forward svc/kube-prometheus-stack-prometheus 9091:9090 >/dev/null 2>&1 & PF2=$!; sleep 65
curl -s http://127.0.0.1:9091/api/v1/query --data-urlencode 'query=up{namespace="monitoring",service="grafana"}' | python3 -c 'import sys,json; print([(x["metric"].get("pod"), x["value"][1]) for x in json.load(sys.stdin)["data"]["result"]])'
# PASS: exactly [($POD, "1")]. FAIL: [] or old pod.
curl -s http://127.0.0.1:9091/api/v1/query --data-urlencode 'query=grafana_build_info' | python3 -c 'import sys,json; print(sorted({x["metric"].get("version") for x in json.load(sys.stdin)["data"]["result"]}))'
# PASS: ['13.2.4']. FAIL: [] (series missing) or 13.2.3.
kill $PF2
```
CONTENTS ASSERTION: dashboards == 72 / provisioned >= 65 and six datasource health checks OK plus a non-empty `count(kube_pod_info)` through Grafana, versus the section 2 baseline.
CONTROL: metric up - `up{namespace="monitoring",service="grafana"}` must be 1 for the NEW pod.
CONTROL: metric grafana_build_info - `version` label must read 13.2.4.
CONTROL: metric kube_pod_info - `count(kube_pod_info)` through Grafana must be positive.

## 5) Rollback

**Trigger.** Any 4.x gate fails (except the documented sidecar-wording case). Stop, do not iterate in the window.

**Decide by 4.3 first.**
- `nonzero=0` (no migration): **git-revert** is safe (old binary opens an unchanged DB):
  ```bash
  SHA=$(git log -1 --format=%H -- kubernetes/apps/monitoring/grafana/app/helmrelease.yaml)
  git show --stat $SHA          # subject names plan grafana-13.7.0
  git revert --no-edit $SHA && git log -1 --format=%s && git push
  flux reconcile kustomization grafana -n monitoring --with-source
  kubectl rollout status deployment/grafana -n monitoring --timeout=300s
  ```
  Confirm: hr chartVersion = the pre-change premise value; grafana image `13.2.3-distroless`, sidecars `2.11.2`; re-run 4.2-4.4 (a rollback is a restart).
- `nonzero>0` (a migration ran): if 4.1-4.4 otherwise pass, **stay forward** and report. If unhealthy: restore
  procedure, not revert. Scale to zero via git (`replicas: 0` in HelmRelease values, `git commit --only`), restore
  volume `grafana-config` from the backup recorded in 2.2 (`docs/sops/backup.md`, RecurringJob `daily-backup-all-volumes`),
  revert the chart commit and restore replicas in the same push, re-run 4.1-4.5. At risk: UI-made state since that backup
  (about 7 non-provisioned dashboards, preferences, annotations); provisioned dashboards/datasources regenerate from git.
- Datasource gate fails on BOTH sides: preinstall hazard, not this chart. Check `GF_PLUGINS_PREINSTALL_DISABLED` is still
  `"true"` in the rendered Deployment; escalate.

## 6) Interference notes

- Hard conflicts are in `conflicts_with`: Flux/helm-controller changes (oci sources, drift detection, impersonation,
  fleet, distribution), node rolls (Talos 1.14.2/1.14.4 evict grafana), and kube-prometheus-stack plans (shared
  monitoring instrument; 92.10.1 also checks the grafana chart version in its bundled-subchart premise).
  Repo correction: `kube-prometheus-stack-92.10.1` lists `grafana-13.5.0` (now superseded); it should name `grafana-13.7.0`.
- Plan `grafana-13.5.0` is superseded by this plan (kept as a file only because other plans reference its id).
  PR #250 (13.2.8) and PR #312 become obsolete when this lands; Renovate closes them.
- PR #374 (14.0.1, MAJOR, same binary 13.2.4) is plan `grafana-14.0.1`, which depends_on this plan.
- Namespace neighbours in `monitoring` with no resource overlap may share a window; run this first or last.
- TeslaMate: Grafana reads its Postgres via datasource `TeslaMate`; a same-night TeslaMate/DB roll can make that one
  health check ERROR transiently. Re-run it after the other roll settles before declaring failure.
- User impact: Grafana UI and SSO unavailable ~1-2 min (Recreate, RWO PVC). `download-dashboards` pulls from grafana.com
  and GitHub raw on every start; an upstream outage fails the init regardless of this bump.
- Unattended-safe: every pre-check STOP happens before the git edit; after the push, the only automatic action on failure
  is the section 5 rule (git-revert when 4.3 is clean; otherwise stop and leave Grafana forward for the operator).
