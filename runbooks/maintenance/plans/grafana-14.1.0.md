---
plan_id: grafana-14.1.0           # KEPT on purpose although target moved to 14.2.0: the id is an identifier, not an assertion
                                  # (README "When the held target MOVES"); other plans' conflicts_with, the finding join and
                                  # any go/no-go issue resolve by it. `target:` below is authoritative.
component: grafana
pr: 374                           # Renovate PR #374 (branch renovate/grafana-14.x) now proposes 14.0.1 -> 14.2.0; its diff is
                                  # exactly the one `version:` line. The plan hand-edits that SAME line and Renovate autocloses it.
kind: chart
current: "14.0.1"                 # MEASURED 2026-10-30: HR spec 14.0.1, history[0] 14.0.1 / app 13.2.4, Ready, pod age 7d20h, 0 restarts
target: "14.2.0"                  # RETARGETED 2026-10-30 from 14.1.0 (see section 1: 14.2.0 moves the APP 13.2.4 -> 13.3.0)
update_type: minor                # chart minor AND Grafana application minor
risk: medium
est_duration_min: 40
needs_reboot: false
touches:
  namespaces: [monitoring, storage]
  resources:                      # every object below verified to EXIST live 2026-10-30
    - helmrelease/grafana         # git edit: spec.chart.spec.version 14.0.1 -> 14.2.0
    - deployment/grafana          # ROLLS ONCE (Recreate): image 13.2.4-distroless -> 13.3.0-distroless
    - pvc/grafana-config          # sqlite; RWO longhorn-static. MIGRATED FORWARD by 13.3.0 on first boot (rollback class)
    - volume.longhorn.io/grafana-config   # ns storage: snapshot + backup taken BEFORE the roll; restore path in section 5
    - configmap/grafana           # re-rendered; content-identical except labels (values.yaml identical 14.1.0 -> 14.2.0)
    - servicemonitor/grafana      # label only; Prometheus must re-find the new pod
    - clusterrole/grafana-clusterrole   # label only
    - clusterrolebinding/grafana-clusterrolebinding   # label only
  shared: []                      # tenant of ns monitoring, not infrastructure. It READS shared infra in verification
                                  # (Prometheus, Elasticsearch, InfluxDB, the TeslaMate and pellets Postgres) and
                                  # snapshots one Longhorn volume, but restarts none of it.
depends_on: []
conflicts_with:                   # ONLY this field is honoured by the scheduler. Reasons, strongest first:
  - talos-linux-1.14.4            # node roll evicts grafana mid-gate; also exclusive:true on sun-attended:2026-11-01
  - teslamate-4.4.0               # HARD: every grafana start re-fetches the 11 TeslaMate dashboards from UNPINNED
                                  # teslamate master, and that plan's section 4.5 reads Grafana as its instrument while
                                  # the TeslaMate DB schema is mid-migration
  - longhorn-1.13.0               # grafana-config is a Longhorn volume; this plan snapshots/backs it up and may restore it
  - helm-drift-detection          # edits spec of EVERY HelmRelease incl. helmrelease/grafana: same object, attribution
  - flux-oci-chart-sources        # rewrites the chart source of HelmReleases incl. grafana (it also rolls deployment/grafana)
  - otel-operator-0.25.1          # SOFT (attribution hygiene, no technical coupling found): both gate on ns monitoring
  - edot-collector-0.163.2        # signals; keep a failed gate attributable to ONE change. Neither plan reads Grafana.
  - edot-collector-0.164.0        # (draft, added 2026-10-30; it already lists this plan)
exclusive: false
security_ref: F-482f421e          # open warning "grafana/grafana:13.2.4-distroless ... newer upstream tag available". Detail stays
                                  # in the DB. 13.3.0 is the newest upstream tag, so this bump is the available remediation.
capability_change: true           # Grafana 13.2.4 -> 13.3.0 is an application MINOR: user-visible default changes (release notes:
                                  # "Make the auto grid to be default", "Unified storage: Enable automatic cleanup of deleted
                                  # resources by default") => never unattended without an operator GO. Previously false at 14.1.0.
rollback_class: backup-restore    # the sqlite schema is migrated forward on first boot; a pin revert may not boot on it
backup_gate: "2.5: a Longhorn Backup CR for volume grafana-config in state Completed, created less than 6 hours before the roll, PLUS a named pre-change Longhorn snapshot (grafana-pre-14-2-0) listed on the volume. Both must PASS before the pin is edited. Freshness proof only - NOT a restore proof; acceptable because the plan is human-gated and section 5 states what a total DB loss costs (2 users, 1 service account, 0 annotations, 0 alert rules measured 2026-10-30)."
finding_refs: [F-482f421e]        # F-482f421e security warning, newer tag exists (open; VERIFIED via policy-cli finding list 2026-10-30).
                                  # HISTORICAL, deliberately not listed: F-c01c08c6 "grafana: chart 14.0.1 -> 14.2.0 (minor)" (version,
                                  # PLAN lane) is status resolved in the DB since 2026-10-30; this plan answered it, it needs no ownership claim.
review: null                      # material change (target, risk class, rollback class, gates): needs a fresh plan-review
status: draft
window: null                      # suggested: nightly:2026-11-03 with operator GO (section 6); the window agent assigns it
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/grafana-image-changes.md
  - docs/sops/backup.md
  - docs/sops/monitoring.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-10-30"
premises:
  - id: live-chart-is-14.0.1
    why: "`current:` claims 14.0.1. If the HR already moved (manual bump, another plan), the diff and rollback baseline below are stale."
    run: kubectl get helmrelease grafana -n monitoring -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: "14.0.1"
  - id: live-image-is-13.2.4-distroless
    why: "The migration analysis assumes the RUNNING app is 13.2.4 with no image.tag override. A different live tag voids the app-delta analysis (e.g. someone already took 13.3.0)."
    run: kubectl get deploy grafana -n monitoring -o jsonpath='{.spec.template.spec.containers[?(@.name=="grafana")].image}'
    expect_exact: "docker.io/grafana/grafana:13.2.4-distroless"
  - id: helmrelease-ready
    why: "Never stack a bump on an already-failing release (remediation retries 3 would mask the cause)."
    run: kubectl get helmrelease grafana -n monitoring -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: no-image-tag-pin-in-values
    why: "The image follows .Chart.AppVersion only while values carry no `image:` key; a pin added since would decouple the binary from the chart."
    run: grep -c '^    image:' kubernetes/apps/monitoring/grafana/app/helmrelease.yaml
    expect_exact: "0"
  - id: preinstall-guard-live
    why: "GF_PLUGINS_PREINSTALL_DISABLED=true is load-bearing (2026-09-12: its absence cost 2.5 days of dead TeslaMate/Pellets panels after one restart). This roll restarts the pod, so the guard must be live BEFORE we restart."
    run: kubectl get deploy grafana -n monitoring -o jsonpath='{.spec.template.spec.containers[?(@.name=="grafana")].env[?(@.name=="GF_PLUGINS_PREINSTALL_DISABLED")].value}'
    expect_exact: "true"
  - id: repo-cache-sees-target
    why: "`helm show chart ... --version 14.2.0` fails on a stale local index and is indistinguishable from the chart not existing. Refresh with `helm repo update grafana-community` if this fails."
    run: helm show chart grafana-community/grafana --version 14.2.0 | grep '^version:'
    expect_exact: "version: 14.2.0"
  - id: target-chart-appversion-is-13.3.0
    why: "THE central fact of the retarget. If 14.2.0 is ever repackaged with a different appVersion, the app-delta analysis (13.2.4 -> 13.3.0, forward-only migration, backup-restore class) is void and the plan must be re-triaged."
    run: helm show chart grafana-community/grafana --version 14.2.0 | grep '^appVersion:'
    expect_exact: "appVersion: 13.3.0"
  - id: container-set-baseline
    why: "Verification asserts the pod keeps exactly these three containers (the new sc-repositories sidecar stays off). Baseline must hold before the change."
    run: kubectl get pod -n monitoring -l app.kubernetes.io/name=grafana -o jsonpath='{.items[*].spec.containers[*].name}'
    expect_exact: "grafana-sc-dashboard grafana-sc-datasources grafana"
  - id: grafana-volume-healthy
    why: "The backup gate and the section 5 restore both assume the Longhorn volume is attached and healthy (2 replicas)."
    run: kubectl get volume grafana-config -n storage -o jsonpath='{.status.state} {.status.robustness}'
    expect_exact: "attached healthy"
---

# grafana: chart 14.0.1 -> 14.2.0 (Grafana 13.2.4 -> 13.3.0, application minor)

## 1) Summary & why held

**RETARGET 2026-10-30 (was: chart 14.1.0).** The nightly:2026-10-29 run stopped at pre-check 2.3 because Renovate PR
#374 (`renovate/grafana-14.x`, same number that carried 13.7.0 -> 14.0.1) now proposes **14.0.1 -> 14.2.0**. The original
plan assumed no grafana PR existed and was written when 14.1.0 was newest. Re-assessed from scratch below; the
conclusion flipped: **the old low-risk / git-revert verdict does NOT carry over**, because 14.2.0 moves the app.

**(1) What is live now (measured 2026-10-30).** Unchanged since the original plan: HelmRelease `grafana` spec and
history[0] chart **14.0.1**, appVersion 13.2.4, Ready, last deployed 2026-10-23T01:38Z; one pod
`grafana-5fb7f595c9-6x2bm` 3/3, 0 restarts, age 7d20h; image `docker.io/grafana/grafana:13.2.4-distroless`.
`git log` of the grafana app folder: newest commit is still 2259f141 (the 14.0.1 bump). Nothing else changed.

**(2) 14.2.0 vs 14.1.0.** Chart repo index (`https://grafana-community.github.io/helm-charts`):
```
14.2.0   appVersion 13.3.0   created 2026-10-27T15:49Z   <- Renovate PR #374 / this plan
14.1.0   appVersion 13.2.4   created 2026-10-26T09:49Z   <- previous target (opt-in Git Sync sidecar only)
14.0.1   appVersion 13.2.4   created 2026-10-16          <- live
```
- Chart source diff 14.1.0 -> 14.2.0: **`Chart.yaml` only** (`appVersion: 13.3.0`). `values.yaml`, templates, RBAC: byte-identical.
  Upstream release note for grafana-14.2.0: *"[grafana] Update docker.io/grafana/grafana Docker tag to v13.3.0 (#939)"*.
- Render diff against OUR live `spec.values` (`helm template`, chart 14.1.0 vs 14.2.0): `helm.sh/chart` label,
  `app.kubernetes.io/version` label (13.2.4 -> 13.3.0) and **one image line**
  `grafana:13.2.4-distroless` -> `grafana:13.3.0-distroless` (`13.3.0-distroless` exists on Docker Hub, pushed 2026-10-27).
  Env, volumes, containers, sidecar versions, selectors, ConfigMap data: unchanged. The new `sc-repositories` sidecar stays
  off (default `false`, we do not set it) - container set stays 3.
- So 14.2.0 = the whole of 14.1.0 **plus a Grafana application minor**. That is exactly the hazard the `*grafana*` deny rule
  (`max: patch`) exists for: the SOP (`grafana-image-changes.md` fact 3) and the HelmRelease header state that Grafana 13
  migrates the sqlite schema on boot and the migration is forward-only.
- **Grafana 13.3.0 release notes** (`grafana/grafana` v13.3.0, read 2026-10-30): a large feature release with a Security
  section (detail intentionally not copied here; see `security_ref` F-482f421e), Alerting import/auto-sync rework
  (we run `handleGrafanaManagedAlerts: false`, 0 alert rules), Git Sync/provisioning work (unused), `Dashboards: Make the
  auto grid to be default`, `Unified storage: Enable automatic cleanup of deleted resources by default`, `Canvas: load the
  standalone plugin by default`, a **Breaking changes** entry limited to renaming the plugins-marketplace config section
  (`marketplace` -> `plugins_marketplace`; we set no such section), and plugin-dev API changes (irrelevant).
  **The release notes do not say whether 13.3.0 migrates the schema; the SOURCE does, and it does.** Checked 2026-10-30 by
  fetching `pkg/services/sqlstore/migrations/migrations.go` at both tags (`gh api repos/grafana/grafana/contents/...?ref=v13.2.4|v13.3.0`):
  the three registration names `AddManagedFolderVariableActionsMigration`, `CollateBinAlertRuleFolderFullpath` and
  `ExpandAlertRuleMissingSeriesEvalsToResolve` appear **0 times at v13.2.4 and 3 times at v13.3.0**. Per the plan review's reading
  of the same diff: `CollateBinAlertRuleFolderFullpath` is mysql/postgres only (a no-op on our sqlite), the other two run on sqlite,
  and the unified-storage side adds a `resource_blob_upload_chunk` table (resource-migrator expected to perform >= 2). So the first
  13.3.0 boot WILL perform sqlite migrations (`migrator performed>0`): the rollback class (backup-restore) is not a precaution but a
  consequence, and the verification expects a non-zero count rather than `performed=0`.
- **Plugin trap.** The pod restarts once either way. `GF_PLUGINS_PREINSTALL_DISABLED: "true"` is in the 14.2.0 render and live
  today, and `[plugins] preinstall_auto_update = false` is in the live ConfigMap. What is NEW with an app minor: the bundled plugin
  set can change (the 13.2.0 jump took the count from 2 to 13 bundled entries, PR #129593). Per the plan review, 13.3.0 adds
  bundled EXTERNAL plugins `cloudwatch` and `canvas` and removes the core CloudWatch implementation, so the datasource count is
  expected to STAY 18 (cloudwatch moves from core to bundled-external); I did not verify that against the image, hence the
  pre-flight and the "== pre-flight" gate rather than a hard-coded expectation. Section 2.8 therefore measures the candidate
  image OFF the live PVC against a 13.2.4 control and section 4 compares to that measurement.
- Restart side effects to expect (unchanged from the original plan): `download-dashboards` re-fetches the TeslaMate (+ flux, k8s,
  nginx) dashboards from unpinned `master`; the pod re-reads `secret/elasticsearch-es-elastic-user` (F-03d0843d).

**(3) Retarget decision: 14.2.0 is the right target; 14.1.0 is dropped, not held.**
- 14.1.0 delivers nothing we use (an opt-in sidecar) and would cost an extra restart, an extra gate run and an extra
  window; it also does not touch the open security finding.
- Holding PR #374 to land 14.1.0 first would need a Renovate `allowedVersions` cap (a config change in `.github/renovate.json5`)
  and then a second plan for 14.2.0 anyway.
- 13.2.4 is already the newest 13.2.x and the open finding F-482f421e says a newer upstream tag exists: 13.3.0 is it.
  Taking the app forward is the point, and it is why the class changed.

**Verdict.** `risk: medium` (was low), `capability_change: true` (was false), `rollback_class: backup-restore` (was
git-revert), no reboot, ~40 min. Execution class derives to HUMAN-GATED: needs an attended-or-nightly slot WITH an explicit
operator GO. It cannot be AUTO-NIGHT or SD-10 pre-approved.

**Data at stake if the sqlite DB is lost (measured via API 2026-10-30):** 2 users, 1 service account, 0 annotations, 0 public
dashboards, 0 library elements, 0 alert rules. All 72 dashboards, all 7 datasources and the Authentik SSO config come from git
or the sidecar. So the worst-case rollback (fresh DB) costs the service account and its token(s), the two user records
(re-created on next SSO login) and per-user preferences/stars. Record the service account's NAME in 2.9 so its consumer can be
re-issued if that case is ever hit.

## 2) Pre-checks

Run every premise first: `.venv/bin/python3 runbooks/plan-premises.py grafana-14.1.0 --require-premises`.
Then, in order (do not start Step 3 unless each prints the stated result):

```bash
# 2.1 Refresh the local helm index (premise repo-cache-sees-target depends on it) and confirm the target.
helm repo update grafana-community
helm show chart grafana-community/grafana --version 14.2.0 | grep -E '^(version|appVersion):'
# expect exactly: appVersion: 13.3.0 / version: 14.2.0   (anything else: STOP, plan is void)

# 2.2 Newer target? If upstream shipped a chart NEWER than 14.2.0, this plan is DRIFTED: STOP and refresh, do not roll a stale target.
python3 - <<'PY'
import subprocess,json
out=subprocess.check_output(["helm","search","repo","grafana-community/grafana","--versions","-o","json"],text=True)
v=[x["version"] for x in json.loads(out)][:3]; print("newest charts:",v)
print("TARGET_IS_NEWEST" if v[0]=="14.2.0" else "NEWER_CHART_EXISTS - STOP, refresh the plan (or consciously stay on 14.2.0 and say why)")
PY

# 2.3 Renovate PR handling (this is the check that STOPped nightly:2026-10-29, now corrected). PR #374 exists ON PURPOSE.
gh pr list --state open --json number,title --jq '.[]|select(.title|test("grafana";"i"))|[.number,.title]|@tsv'
# PASS = no output, OR exactly one line: 374<TAB>feat(helm): update grafana ( 14.0.1 → 14.2.0 )
# STOP = any other grafana PR, or #374 proposing a target other than 14.2.0 (retargeted again: refresh the plan first).
# #374's diff is exactly the one `version:` line (checked 2026-10-30). Step 3 hand-edits that same line plus a history
# comment; Renovate autocloses #374 once main carries 14.2.0 (what it did for 14.0.1, commit 2259f141). Do NOT merge #374
# AND hand-edit. Do NOT close #374 first (Renovate would reopen it against the next push).

# 2.4 Release is Ready, no in-flight reconcile, pod healthy with zero restarts.
flux get helmrelease grafana -n monitoring
kubectl get pods -n monitoring -l app.kubernetes.io/name=grafana
kubectl get pod -n monitoring -l app.kubernetes.io/name=grafana -o jsonpath='{.items[0].status.containerStatuses[*].restartCount}{"\n"}'   # 0 0 0

# 2.5 BACKUP GATE (rollback class backup-restore). The nightly Longhorn job runs 23:00 (cluster time) so a 03:30 window sees
#     a backup ~4.5 h old; on any other slot take a fresh one first (docs/sops/backup.md "Manual Backup": single-volume backup
#     from the Longhorn UI, or `kubectl create job --from=cronjob/daily-backup-all-volumes ...` which backs up ALL volumes - heavy).
kubectl get backups.longhorn.io -n storage -l backup-volume=grafana-config --sort-by=.metadata.creationTimestamp \
  -o custom-columns=NAME:.metadata.name,STATE:.status.state,CREATED:.metadata.creationTimestamp | tail -3
python3 - <<'PY'
import subprocess,json,datetime as d
o=json.loads(subprocess.check_output(["kubectl","get","backups.longhorn.io","-n","storage","-l","backup-volume=grafana-config","-o","json"],text=True))
ok=[b for b in o["items"] if b.get("status",{}).get("state")=="Completed"]
ok.sort(key=lambda b:b["metadata"]["creationTimestamp"])
if not ok: print("BACKUP_NONE"); raise SystemExit
t=d.datetime.fromisoformat(ok[-1]["metadata"]["creationTimestamp"].replace("Z","+00:00"))
age=(d.datetime.now(d.timezone.utc)-t).total_seconds()/3600
print("newest Completed backup:",ok[-1]["metadata"]["name"],"age %.1f h"%age); print("BACKUP_OK" if age<6 else "BACKUP_TOO_OLD - take a fresh backup, re-run")
PY
# Snapshot half of the gate: create a NAMED pre-change snapshot and see it listed (Longhorn Snapshot CR; one apply, executor-owned).
cat <<'YAML' | kubectl apply -f -
apiVersion: longhorn.io/v1beta2
kind: Snapshot
metadata:
  name: grafana-pre-14-2-0
  namespace: storage
spec:
  volume: grafana-config
  createSnapshot: true
YAML
for i in $(seq 1 30); do   # readyToUse flips asynchronously; poll up to 150 s, never read it once
  r=$(kubectl get snapshots.longhorn.io -n storage grafana-pre-14-2-0 -o jsonpath='{.status.readyToUse}'); [ "$r" = true ] && break; sleep 5
done
kubectl get snapshots.longhorn.io -n storage grafana-pre-14-2-0 -o jsonpath='{.status.readyToUse} {.status.creationTime}{"\n"}'
# PASS = "true <timestamp>". Anything else after the loop = SNAPSHOT_NOT_READY: STOP, do not edit the pin.
# (Caveat: the Snapshot manifest's fields (spec.volume, spec.createSnapshot) were checked against the live CRD schema
#  (snapshots.longhorn.io v1beta2) but NOT applied during planning - read-only session.
#  If the apply is rejected, take the snapshot from the Longhorn UI (Volume grafana-config -> Take Snapshot, name it
#  grafana-pre-14-2-0) and treat the UI listing as the gate.)

# 2.6 Same-night interference: Prometheus is this window's instrument. kube-prometheus-stack (PR #428-class bumps) is AUTO-lane,
#     so Step 0 of THIS window may apply one BEFORE this plan runs. HONEST SCOPE: this settle check is mostly a TIMING mitigation;
#     the REAL control is that the 2.7 baselines are taken AFTER Step 0 (a kps-driven change to the dashboard count or the
#     Prometheus pod cannot then be mistaken for a Grafana regression).
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
# PASS = KPS_SETTLED (history[0].status deployed AND lastDeployed > 30 min ago AND every container of
# pod prometheus-kube-prometheus-stack-0 ready; an untouched kps passes by age alone). A wrong pod name makes kubectl exit
# non-zero and the script raise: fails closed. Live 2026-10-30 not re-measured here beyond the 2026-10-26 rehearsal of this block.

# 2.7 BASELINES - taken AFTER Step 0 of this window, never carried over from an earlier day (record all three).
U=$(kubectl get secret grafana-admin-secret -n monitoring -o jsonpath='{.data.admin-user}' | base64 -d)
PW=$(kubectl get secret grafana-admin-secret -n monitoring -o jsonpath='{.data.admin-password}' | base64 -d)
kubectl port-forward -n monitoring svc/grafana 33001:80 >/dev/null 2>&1 &
PF=$!; sleep 5
echo "BASE_PLUGINS=$(curl -s -u "$U:$PW" 'http://127.0.0.1:33001/api/plugins?embedded=0&type=datasource' | python3 -c 'import sys,json; print(len(json.load(sys.stdin)))')"   # 2026-10-26: 18
echo "BASE_DASH=$(curl -s -u "$U:$PW" 'http://127.0.0.1:33001/api/search?type=dash-db&limit=1000' | python3 -c 'import sys,json; print(len(json.load(sys.stdin)))')"       # 2026-10-26: 72
curl -s -u "$U:$PW" 'http://127.0.0.1:33001/api/serviceaccounts/search?perpage=100' | python3 -c 'import sys,json; print("SERVICE_ACCOUNTS:",[s["name"] for s in json.load(sys.stdin)["serviceAccounts"]])'   # 2.9 record
kill $PF; wait $PF 2>/dev/null
P=/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query
echo "BASE_PROMDS=$(kubectl get --raw "$P?query=count%28grafana_plugin_build_info%7Bplugin_type%3D%22datasource%22%7D%29" | python3 -c 'import sys,json; print(json.load(sys.stdin)["data"]["result"][0]["value"][1])')"   # 2026-10-26: 13
# GATE: BASE_PLUGINS must be 18. If it is already lower, Grafana is ALREADY degraded (the 09-12 signature is 13):
# STOP and fix that first - do not roll on top of it, the verification would "pass" against a broken baseline.

# 2.8 PRE-FLIGHT the candidate image OFF the live PVC (docs/sops/grafana-image-changes.md section 8 B, distroless form).
#     A throwaway pod mounts NO grafana-config, so what it reports is exactly what the IMAGE ships. A 13.2.4 CONTROL runs first:
#     it must report the live baseline number (proves the method counts what the live pod counts).
#     NOT REHEARSED IN PLANNING: it needs a cluster mutation (kubectl run) and the planning session is read-only. What WAS
#     checked: `bash -n` on the script below, the overrides JSON parsed with json.loads, and `kubectl run --dry-run=client`.
#     The pods copy the live container's hardening (uid/gid 472, readOnlyRootFilesystem, drop ALL, RuntimeDefault seccomp,
#     writable emptyDirs only at /tmp, /var/lib/grafana, /var/lib/grafana-search) so a read-only-fs plugin-installer failure
#     would reproduce; the guard env var is set exactly as in the live HelmRelease.
S=${TMPDIR:-/tmp}
cat > "$S/grafana-preflight.sh" <<'EOF2'
#!/usr/bin/env bash
set -u
S=${S:-${TMPDIR:-/tmp}}
ADMINPW=$(python3 -c 'import secrets; print(secrets.token_urlsafe(18))')
PF=
cleanup() {  # runs on ANY exit, incl. failure: no preflight pod or port-forward may outlive this script
  [ -n "$PF" ] && kill "$PF" 2>/dev/null
  kubectl delete pod -n monitoring -l app.kubernetes.io/component=grafana-preflight --ignore-not-found --wait=false >/dev/null 2>&1
}
trap cleanup EXIT
for TAG in 13.2.4 13.3.0; do
  N=grafana-preflight-${TAG//./-}
  python3 - "$N" "$TAG" "$ADMINPW" > "$S/$N.json" <<'PY'
import json,sys
n,tag,pw=sys.argv[1:4]
print(json.dumps({"spec":{
 "securityContext":{"runAsUser":472,"runAsGroup":472,"runAsNonRoot":True,"fsGroup":472},
 "containers":[{"name":n,"image":"docker.io/grafana/grafana:%s-distroless"%tag,
  "env":[{"name":"GF_PLUGINS_PREINSTALL_DISABLED","value":"true"},{"name":"GF_SECURITY_ADMIN_PASSWORD","value":pw},
         {"name":"GF_PATHS_DATA","value":"/var/lib/grafana"},{"name":"GF_UNIFIED_STORAGE_INDEX_PATH","value":"/var/lib/grafana-search"}],
  "ports":[{"containerPort":3000}],
  "readinessProbe":{"httpGet":{"path":"/api/health","port":3000},"periodSeconds":5,"failureThreshold":30},
  "securityContext":{"readOnlyRootFilesystem":True,"allowPrivilegeEscalation":False,"privileged":False,
                     "capabilities":{"drop":["ALL"]},"seccompProfile":{"type":"RuntimeDefault"}},
  "volumeMounts":[{"name":"tmp","mountPath":"/tmp"},{"name":"data","mountPath":"/var/lib/grafana"},{"name":"search","mountPath":"/var/lib/grafana-search"}]}],
 "volumes":[{"name":"tmp","emptyDir":{}},{"name":"data","emptyDir":{}},{"name":"search","emptyDir":{}}]}}))
PY
  kubectl run "$N" -n monitoring --image="docker.io/grafana/grafana:${TAG}-distroless" --restart=Never \
    --labels=app.kubernetes.io/component=grafana-preflight --overrides="$(cat "$S/$N.json")" || exit 1
  # A fresh DB runs ~730 sqlite + unified-storage migrations BEFORE it listens: the container is "started" long before it
  # answers. Wait for the readiness probe, then POLL /api/health (up to 120 s) - never count plugins before it returns 200.
  kubectl wait pod/"$N" -n monitoring --for=condition=Ready --timeout=180s || { kubectl logs "$N" -n monitoring --tail=30; echo "PREFLIGHT_NOT_READY $TAG (pod never Ready) - infrastructure failure, NOT a plugin verdict"; exit 1; }
  kubectl port-forward -n monitoring pod/"$N" 33002:3000 >/dev/null 2>&1 &
  PF=$!
  code=000
  for i in $(seq 1 60); do
    code=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:33002/api/health); [ "$code" = 200 ] && break; sleep 2
  done
  [ "$code" = 200 ] || { kubectl logs "$N" -n monitoring --tail=30; echo "PREFLIGHT_NOT_READY $TAG (/api/health=$code after 120 s) - NOT a plugin verdict, do not read this as 0 plugins"; exit 1; }
  n=$(curl -s -u admin:"$ADMINPW" 'http://127.0.0.1:33002/api/plugins?embedded=0&type=datasource' | python3 -c 'import sys,json; print(len(json.load(sys.stdin)))')
  ro=$(kubectl logs "$N" -n monitoring | grep -i -c -e 'read-only file system' -e 'unlinkat')
  echo "PREFLIGHT $TAG datasource plugins: $n   read-only-fs/unlinkat log lines: $ro"
  kill "$PF" 2>/dev/null; PF=
  kubectl delete pod "$N" -n monitoring --wait=true
done
EOF2
bash -n "$S/grafana-preflight.sh" && S="$S" bash "$S/grafana-preflight.sh"
# PASS = the 13.2.4 control line equals BASE_PLUGINS (18) AND the 13.3.0 line is >= 18 AND both "read-only-fs/unlinkat" counts are 0.
# Record the 13.3.0 number as PREFLIGHT_PLUGINS (section 4 requires it, and the live pod to match it exactly). A 13.3.0 number BELOW 18 =
# it ships fewer datasource backends: STOP. A line PREFLIGHT_NOT_READY is an infrastructure failure, not a verdict: re-run once, then STOP.
# The pods carry label app.kubernetes.io/component=grafana-preflight (not app.kubernetes.io/name=grafana), so no grafana selector, probe or
# ServiceMonitor can pick them up; they use a throwaway admin password that is never stored; the trap deletes them on any exit.

# 2.9 Rehearse the gate script on the CURRENT state. FIRST save it: run the `cat > "$S/grafana-verify.sh"` heredoc from
#     section 4 now (it is only a file write). Then, with the 2.7 baselines:
#       EXPECT_CHART=14.0.1 EXPECT_APP=13.2.4 MIGRATIONS=none BASE_PLUGINS=.. BASE_DASH=.. BASE_PROMDS=.. bash "$S/grafana-verify.sh"
#     It must print ALL GATES PASS. If not, the pre-state is already degraded - STOP, do not edit anything.
```

## 3) Steps (GitOps)

An alert silence is not needed: no Grafana-specific alert rule exists in the repo (`grep -rn "alert:.*[Gg]rafana" kubernetes` = none)
and the outage is ~1-3 min. Expect a longer first boot than a patch (schema migration + 4 migrators + init-container dashboard fetch).

1. Edit the chart pin in `kubernetes/apps/monitoring/grafana/app/helmrelease.yaml`. Dry-tested on a scratch copy on macOS (BSD sed)
   with the new target; the resulting diff is exactly:
   ```
   11c11
   <       version: 14.0.1
   ---
   >       version: 14.2.0
   ```
   ```bash
   sed -i '' 's/^\(      version: \)14\.0\.1$/\114.2.0/' kubernetes/apps/monitoring/grafana/app/helmrelease.yaml
   git diff --stat kubernetes/apps/monitoring/grafana/app/helmrelease.yaml    # expect: 1 file, 1 insertion, 1 deletion
   ```
2. With the Edit tool, add this to the dated history block, directly above `    deploymentStrategy:` (keep all prior history):
   ```
       # 2026-11-xx: chart 14.2.0 - Grafana 13.2.4 -> 13.3.0 (APPLICATION minor: sqlite schema migrates forward on first
       # boot; rollback class backup-restore, NOT git-revert). Values/templates identical to 14.1.0; render diff under OUR
       # values = chart label + app version label + image tag. Pre-change Longhorn snapshot grafana-pre-14-2-0 + backup.
       # Plan: grafana-14.1.0 (id kept, target moved). PR #374. Finding: F-482f421e (F-c01c08c6 historical).
   ```
   (Replace `xx`.) Run `git diff`; confirm only the version line and these comment lines changed.
3. Commit, VERIFY THE SUBJECT, push (shared worktree: `--only` with explicit path; never `git add -A`):
   ```bash
   git commit --only kubernetes/apps/monitoring/grafana/app/helmrelease.yaml \
     -m "chore(grafana): chart 14.0.1 -> 14.2.0 (Grafana 13.2.4 -> 13.3.0, forward-only sqlite migration) [plan grafana-14.1.0, PR #374, finding F-482f421e]"
   git log -1 --format=%s     # must be exactly the line above; if another session's message landed, amend BEFORE pushing
   git show --stat HEAD       # exactly one file: the helmrelease.yaml
   git push
   ```
   (Run the commit in a shell where `SWEEP_PG_DSN` is NOT sourced - it breaks the pre-commit gate.)
4. Let the push webhook reconcile Flux, then confirm the pin landed before concluding anything:
   ```bash
   kubectl get helmrelease grafana -n monitoring -o jsonpath='{.spec.chart.spec.version}{"\n"}'   # expect 14.2.0
   ```
   If it still shows 14.0.1 after 10 min (webhook slow, HelmRepository index interval), and only then:
   `flux reconcile helmrelease grafana -n monitoring --with-source`.
5. Watch the single `Recreate` roll (single replica, RWO PVC) and the first-boot log:
   ```bash
   kubectl rollout status deployment/grafana -n monitoring --timeout=420s
   kubectl get pods -n monitoring -l app.kubernetes.io/name=grafana     # NEW pod name, 3/3, restarts 0
   ```
   `rollout status` can green-light the old generation: section 4 independently asserts the new pod via image tag,
   `/api/health` version and the pod's `helm.sh/chart` label.
6. **Wait 90 s after the pod is Ready** (Prometheus scrape interval) before running section 4.
7. After a green section 4, confirm Renovate closed #374 (it should, within its next run): `gh pr view 374 --json state --jq .state`
   -> `CLOSED`. If it is still OPEN with title 14.2.0 after the next Renovate run, close it with a comment pointing at the bump commit.
   Delete snapshot `grafana-pre-14-2-0` only after the soak below (it is the fastest rollback).

## 4) Verification

Floor (shape): HR Ready at 14.2.0, pod 3/3 on the new generation. The CONTENTS gates are what matter and are all in one
script so none can be skipped. Save and run it (needs `kubectl`, `curl`, `python3`; it port-forwards `svc/grafana` to 33001
itself and exits non-zero on any FAIL):

```bash
S=${TMPDIR:-/tmp}; cat > "$S/grafana-verify.sh" <<'EOF'
#!/usr/bin/env bash
# usage (post-change):
#   EXPECT_CHART=14.2.0 EXPECT_APP=13.3.0 MIGRATIONS=expect BASE_PLUGINS=18 BASE_DASH=72 BASE_PROMDS=13 PREFLIGHT_PLUGINS=<2.8> bash grafana-verify.sh
# usage (rehearsal on the CURRENT state):
#   EXPECT_CHART=14.0.1 EXPECT_APP=13.2.4 MIGRATIONS=none BASE_PLUGINS=18 BASE_DASH=72 BASE_PROMDS=13 bash grafana-verify.sh
fail=0
ok()  { echo "PASS  $1"; }
bad() { echo "FAIL  $1"; fail=1; }
: "${EXPECT_CHART:?}" "${EXPECT_APP:?}" "${MIGRATIONS:?none|expect}" "${BASE_PLUGINS:?}" "${BASE_DASH:?}" "${BASE_PROMDS:?}"
[ "$MIGRATIONS" = expect ] && : "${PREFLIGHT_PLUGINS:?run 2.8 first and pass its 13.3.0 number}"

# V1 release, image and pod identity (grafana_build_info alone cannot tell old pod from new when the app is unchanged;
# on THIS bump the app does change, so /api/health + image tag discriminate, and the chart label covers the rest)
c=$(kubectl get helmrelease grafana -n monitoring -o jsonpath='{.status.history[0].chartVersion} {.status.conditions[?(@.type=="Ready")].status}')
[ "$c" = "$EXPECT_CHART True" ] && ok "HR chart/Ready: $c" || bad "HR chart/Ready: got '$c' want '$EXPECT_CHART True'"
img=$(kubectl get deploy grafana -n monitoring -o jsonpath='{.spec.template.spec.containers[?(@.name=="grafana")].image}')
[ "$img" = "docker.io/grafana/grafana:$EXPECT_APP-distroless" ] && ok "image $img" || bad "image is '$img' want docker.io/grafana/grafana:$EXPECT_APP-distroless"
lbl=$(kubectl get pod -n monitoring -l app.kubernetes.io/name=grafana -o jsonpath='{.items[*].metadata.labels.helm\.sh/chart}')
[ "$lbl" = "grafana-$EXPECT_CHART" ] && ok "pod chart label $lbl (the measured pod is the new generation)" || bad "pod chart label '$lbl' want grafana-$EXPECT_CHART (old pod still serving, or two pods)"
names=$(kubectl get pod -n monitoring -l app.kubernetes.io/name=grafana -o jsonpath='{.items[*].spec.containers[*].name}')
[ "$names" = "grafana-sc-dashboard grafana-sc-datasources grafana" ] && ok "containers: $names (no sc-repositories sidecar)" || bad "container set changed: '$names'"
rdy=$(kubectl get pod -n monitoring -l app.kubernetes.io/name=grafana -o jsonpath='{.items[*].status.containerStatuses[*].ready}')
[ "$rdy" = "true true true" ] && ok "3/3 ready" || bad "readiness: '$rdy'"
rc=$(kubectl get pod -n monitoring -l app.kubernetes.io/name=grafana -o jsonpath='{.items[*].status.containerStatuses[*].restartCount}')
case "$rc" in "0 0 0") ok "restartCount 0 0 0";; *) bad "restartCount '$rc' (crash-looping or restarted after roll)";; esac

# V2 the load-bearing preinstall guard survived chart+render+app change
pv=$(kubectl get deploy grafana -n monitoring -o jsonpath='{.spec.template.spec.containers[?(@.name=="grafana")].env[?(@.name=="GF_PLUGINS_PREINSTALL_DISABLED")].value}')
[ "$pv" = "true" ] && ok "GF_PLUGINS_PREINSTALL_DISABLED=true" || bad "GF_PLUGINS_PREINSTALL_DISABLED='$pv'"
kubectl get cm grafana -n monitoring -o jsonpath='{.data.grafana\.ini}' | grep -q '^preinstall_auto_update = false' && ok "ini preinstall_auto_update=false" || bad "ini preinstall_auto_update missing"

# V3 migrations + plugin-installer errors (log must be NON-empty: every migrator prints one 'migrations completed' line)
L=$(kubectl logs -n monitoring deploy/grafana -c grafana)
nz=$(printf '%s\n' "$L" | grep -c 'migrations completed.*performed=[1-9]')
z=$(printf '%s\n' "$L" | grep -c 'migrations completed.*performed=0')
tot=$(printf '%s\n' "$L" | grep -c 'migrations completed.*performed=')   # the 4 migrator lines; the "Unified storage migrations completed successfully" line has no performed= and is checked separately
errm=$(printf '%s\n' "$L" | grep -i -c -e 'level=error.*migrat' -e 'migrat.*level=error' -e 'migration failed')
if [ "$MIGRATIONS" = none ]; then
  { [ "$nz" = 0 ] && [ "$z" -ge 4 ]; } && ok "migrations: performed=0 x$z, nonzero x$nz" || bad "migrations: performed=0 x$z, nonzero x$nz (need 0 and >=4)"
else
  rm=$(printf '%s\n' "$L" | grep 'logger=resource-migrator' | grep -c 'migrations completed.*performed=\([2-9]\|[1-9][0-9]\)')
  echo "INFO  migrations on this boot: migrator lines=$tot performed=0 x$z performed>0 x$nz resource-migrator>=2 x$rm  (RECORD these numbers in the window report)"
  # v13.3.0 registers new sqlite migrations (source-verified, section 1): a boot with NO nonzero migrator line is the OLD pod or a
  # different binary, so this gate FAILS on it (rehearsed against the old pod: see section 4).
  { [ "$tot" -ge 4 ] && [ "$nz" -ge 1 ] && [ "$errm" = 0 ]; } && ok "migrations: all $tot migrators completed, $nz performed work, no migration errors" || bad "migrations: lines=$tot nonzero=$nz errors=$errm (need lines>=4, nonzero>=1, errors=0)"
fi
printf '%s\n' "$L" | grep -q 'Unified storage migrations completed successfully' && ok "unified storage migrations completed" || bad "no 'Unified storage migrations completed successfully' line"
ro=$(printf '%s\n' "$L" | grep -i -c -e 'read-only file system' -e 'unlinkat')
[ "$ro" = 0 ] && ok "no read-only-fs plugin-installer errors" || bad "plugin-installer read-only-fs errors x$ro"

# V4 CONTENTS via API
U=$(kubectl get secret grafana-admin-secret -n monitoring -o jsonpath='{.data.admin-user}' | base64 -d)
PW=$(kubectl get secret grafana-admin-secret -n monitoring -o jsonpath='{.data.admin-password}' | base64 -d)
kubectl port-forward -n monitoring svc/grafana 33001:80 >/dev/null 2>&1 &
PF=$!; sleep 5
A="http://127.0.0.1:33001"
hv=$(curl -s -u "$U:$PW" "$A/api/health" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("version"))' 2>/dev/null)
[ "$hv" = "$EXPECT_APP" ] && ok "/api/health version $hv" || bad "/api/health version '$hv' want $EXPECT_APP"
np=$(curl -s -u "$U:$PW" "$A/api/plugins?embedded=0&type=datasource" | python3 -c 'import sys,json; print(len(json.load(sys.stdin)))' 2>/dev/null)
if [ "$MIGRATIONS" = none ]; then want_ok=$([ "$np" = "$BASE_PLUGINS" ] && echo y); else want_ok=$([ -n "$np" ] && [ "$np" -ge "$BASE_PLUGINS" ] 2>/dev/null && { [ -z "$PREFLIGHT_PLUGINS" ] || [ "$np" = "$PREFLIGHT_PLUGINS" ]; } && echo y); fi
[ "$want_ok" = y ] && ok "datasource plugins = $np (baseline $BASE_PLUGINS, preflight ${PREFLIGHT_PLUGINS:-n/a})" || bad "datasource plugins = '$np' (baseline $BASE_PLUGINS, preflight ${PREFLIGHT_PLUGINS:-n/a}; 13 = the 2026-09-12 preinstall-killer signature)"
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

# V5 Prometheus sees the new pod (scrape interval lag: caller waits >=90 s after pod Ready)
P=/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query
pq() { kubectl get --raw "$P?query=$(python3 -c 'import sys,urllib.parse;print(urllib.parse.quote(sys.argv[1]))' "$1")" | python3 -c 'import sys,json; r=json.load(sys.stdin)["data"]["result"]; print(r[0]["value"][1] if r else "EMPTY")'; }
u=$(pq 'up{job="grafana"}'); [ "$u" = "1" ] && ok "up{job=grafana}=1" || bad "up{job=grafana}='$u'"
bv=$(kubectl get --raw "$P?query=grafana_build_info" | python3 -c 'import sys,json; r=json.load(sys.stdin)["data"]["result"]; print(",".join(sorted(x["metric"]["version"] for x in r)))')
[ "$bv" = "$EXPECT_APP" ] && ok "grafana_build_info version=$bv (single series = old pod's series gone)" || bad "grafana_build_info versions='$bv' want exactly $EXPECT_APP"
pm=$(pq 'count(grafana_plugin_build_info{plugin_type="datasource"})')
if [ "$MIGRATIONS" = none ]; then [ "$pm" = "$BASE_PROMDS" ] && ok "datasource plugins in metrics=$pm" || bad "datasource plugins in metrics='$pm' want $BASE_PROMDS"
else case "$pm" in ''|EMPTY|*[!0-9]*) bad "datasource plugins in metrics='$pm'";; *) [ "$pm" -ge "$BASE_PROMDS" ] && ok "datasource plugins in metrics=$pm (>= $BASE_PROMDS)" || bad "datasource plugins in metrics=$pm below baseline $BASE_PROMDS";; esac; fi
sd=$(pq 'grafana_stat_totals_dashboard'); [ "$sd" = "$BASE_DASH" ] && ok "grafana_stat_totals_dashboard=$sd" || bad "grafana_stat_totals_dashboard='$sd' want $BASE_DASH"
echo; [ $fail = 0 ] && echo "ALL GATES PASS" || echo "GATE FAILURE - see FAIL lines (rollback per section 5)"
exit $fail
EOF
EXPECT_CHART=14.2.0 EXPECT_APP=13.3.0 MIGRATIONS=expect BASE_PLUGINS=<2.7> BASE_DASH=<2.7> BASE_PROMDS=<2.7> PREFLIGHT_PLUGINS=<2.8> bash "$S/grafana-verify.sh"
```

Rehearsal 2026-10-30 against the LIVE pre-change state (read-only): `EXPECT_CHART=14.0.1 EXPECT_APP=13.2.4 MIGRATIONS=none` printed
`ALL GATES PASS`. With the post-change expectations (`EXPECT_CHART=14.2.0 EXPECT_APP=13.3.0 MIGRATIONS=expect`) against the
still-old pod it printed exactly the identity FAILs (`HR chart/Ready`, `image`, `pod chart label`, `/api/health version`,
`grafana_build_info`), so the gates that prove "this is the new pod running the new app" can fail. The migration gate in
`expect` mode now FAILS against the old pod (its log shows `performed=0 x4`, no nonzero line: `FAIL migrations: lines=4 nonzero=0`),
which is what makes it a gate; it can only pass on a boot that actually migrated.
Bugs found earlier and kept fixed: `grep -v 'performed=0'` reads 1 on a healthy pod (Grafana also prints `Unified storage
migrations completed successfully`), so the `none` gate counts `performed=[1-9]` (must be 0) AND `performed=0` (must be >= 4).

Negative control for the absence gate (the log must be able to print non-zero through the IDENTICAL command; replayed
2026-10-26 on a synthetic line modelled on the quoted 2026-09-12 failure, same pipeline over a clean line prints 0):
```bash
printf 'logger=plugin.backgroundinstaller level=error msg="unlinkat /usr/share/grafana/data/plugins-bundled/postgres: read-only file system"\n' | grep -i -c -e 'read-only file system' -e 'unlinkat'   # prints 1
printf 'logger=settings level=info msg="ok"\n' | grep -i -c -e 'read-only file system' -e 'unlinkat'                                                  # prints 0
```

What each gate guards against, and what its failure prints:

| Gate | Failure it guards against | Failure output |
|---|---|---|
| HR `chartVersion Ready` = `14.2.0 True` | Flux still on 14.0.1 / remediation rolled back | `FAIL HR chart/Ready: got '14.0.1 True'` |
| image `13.3.0-distroless` | tag drift / wrong generation | `FAIL image is '...13.2.4-distroless' want ...13.3.0-distroless` |
| pod label `helm.sh/chart` == `grafana-14.2.0` (all matching pods) | measuring the OLD pod, or two pods | `FAIL pod chart label 'grafana-14.0.1' want grafana-14.2.0` |
| `/api/health` version == `13.3.0` and `grafana_build_info` == exactly `13.3.0` | old binary still serving; stale old-pod series | `FAIL /api/health version '13.2.4' want 13.3.0` |
| containers == 3 named, 3/3 ready, restartCount `0 0 0` | the new `sc-repositories` sidecar appearing; crash-looping on the migrated DB | `FAIL container set changed` / `FAIL restartCount '0 1 0'` |
| `GF_PLUGINS_PREINSTALL_DISABLED=true` env + ini `preinstall_auto_update = false` | the guard lost - recreates the 2026-09-12 outage on the NEXT restart | `FAIL GF_PLUGINS_PREINSTALL_DISABLED=''` |
| log (`expect` mode): >= 4 migrator lines, at least ONE with `performed>0`, no migration errors, plus the separate `Unified storage migrations completed successfully` line; `INFO` prints the counts | schema migration failing half-way / not finishing / the old binary | `FAIL migrations: lines=4 nonzero=0 errors=0 (need lines>=4, nonzero>=1, errors=0)` |
| log: no `read-only file system` / `unlinkat` (case-insensitive) | the background installer killing bundled backends | `FAIL plugin-installer read-only-fs errors x3` |
| API `/api/plugins?type=datasource` count >= baseline AND == PREFLIGHT_PLUGINS (the 13.3.0 image measured off-PVC) | stripped/killed bundled backends; **13 is the measured 2026-09-12 signature** | `FAIL datasource plugins = '13' (baseline 18, preflight 18 ...)` |
| 6 datasource `/health` == `OK` + alertmanager proxy `cluster` key + `/api/ds/query` numeric (`from`/`to` mandatory, else a healthy Grafana returns empty) | dead plugin, bad ES secret (401 after restart), unreachable DB | `FAIL datasource TeslaMate health='ERROR'` |
| dashboards == baseline (72 on 2026-10-26) | `download-dashboards` init writing 0-byte files on a GitHub fetch failure; sidecar provisioning broken | `FAIL dashboards = '55' want 72` |
| 7 datasource UIDs exact set | provisioning regression | `FAIL datasource set: ...` |
| `/api/frontend/settings` oauth name `Authentik` | SSO wiring (F-5a894d0e) lost; 13.3.0 changed OAuth handling | `FAIL Authentik SSO oauth block: 'None'` |
| Prometheus `up{job="grafana"}` == 1, datasource-plugin series >= baseline, `grafana_stat_totals_dashboard` == baseline | ServiceMonitor lost the target; provisioning count drift | `FAIL up{job=grafana}='EMPTY'` |

CONTENTS ASSERTION: the bundled datasource backends and the provisioned datasources survived the app upgrade and restart -
measured by `/api/plugins?embedded=0&type=datasource` count (compared with the off-PVC pre-flight of the 13.3.0 image, 2.8), six
`/api/datasources/uid/<uid>/health` calls and a real `/api/ds/query`, against the 2.7 baselines (18 plugins, 7 datasources, 72 dashboards
on 2026-10-26).

CONTROL: metric up - `up{job="grafana"}` must be 1 on the new pod (live: 1)
CONTROL: metric grafana_build_info - `version` label must be exactly `13.3.0` after the roll (live now: `13.2.4`; the gate can fail today)
CONTROL: metric grafana_plugin_build_info - `count(...{plugin_type="datasource"})` must be >= the 2.7 baseline (live 2026-10-26: 13)
CONTROL: metric grafana_stat_totals_dashboard - must equal the 2.7 dashboard baseline (live: 72)

No alertname control: the repo carries no Grafana-specific PrometheusRule, and asserting a generic alert would be a gate that
cannot fail on the property under change.

**PASS** = script prints `ALL GATES PASS` (exit 0) AND the `INFO migrations on this boot:` line is recorded in the window
report (expected from section 1: migrator `performed>0`, resource-migrator `performed>=2`; any deviation from that expectation is
worth a line in the report even when the gates pass).

**Soak:** re-run the script once more >= 2 h after the roll (a quiet pod can pass at t+5 min and fail when the first scheduled
plugin/unified-storage cleanup runs; 13.3.0 enables automatic deleted-resource cleanup by default). Only then delete snapshot
`grafana-pre-14-2-0`.

**Owner of the soak re-run and the snapshot deletion** (this is not optional, an unowned soak is a skipped soak): the window agent,
at the end of its Step 4 for this plan, files a home-operation reminder due `T+2h` (same pattern as the soak reminder in
`frigate-reolink-go2rtc-flv.md`: `home-operation ingest --json` with source `maintenance`, resolved by
`home-operation resolve` after the re-run passes), naming the exact command line and the snapshot to delete. If no agent session is
available the operator owns it, prompted by that reminder. The plan is not retired until the reminder is resolved;
the snapshot must not outlive the reminder by more than 7 days (it pins Longhorn space).

## 5) Rollback

**Rollback class is backup-restore, not git-revert.** The chart pin is trivially revertible; the DATABASE may not be. Grafana does
not support downgrading across a schema migration, and whether 13.2.4 will boot on a 13.3.0-migrated `grafana.db` is unknown
(not measurable from here). So the rollback is a ladder; stop at the first rung that passes section 4 with
`EXPECT_CHART=14.0.1 EXPECT_APP=13.2.4 MIGRATIONS=none`:

**Rung 1 - revert the pin (always first, cheap; it restores the chart, not necessarily the data).**
```bash
git revert --no-edit <bump-commit-sha>
git log -1 --format=%s        # confirm the revert subject is yours before pushing
git push
# webhook slow after 10 min: flux reconcile helmrelease grafana -n monitoring --with-source
kubectl rollout status deployment/grafana -n monitoring --timeout=300s
```
Then run the section 4 script with `EXPECT_CHART=14.0.1 EXPECT_APP=13.2.4 MIGRATIONS=none` (the revert is a SECOND restart: the
preinstall guard and datasource gates apply to it exactly as to the forward roll). A migration DID run on the forward roll (the
forward gate required it), so the database is "newer than the app". If the old pod boots and every gate passes, 13.2.4 tolerated
the migrated schema: record it, but do not call the rollback done silently - re-plan the upgrade rather than leaving it half-way.
If it does not boot (crash-loop, schema error in `kubectl logs --previous`), continue to Rung 2.
**Unattended nightly:** Rungs 2 and 3 need the Longhorn UI and operator judgement. In an unattended run the agent stops after
Rung 1, leaves the pod as it is, and escalates through the window's `blocked` / `reverted` notification (`urgent` events in
`runbooks/maintenance-windows.yaml`) - it must not improvise Rung 2/3.

**Rung 2 - 13.2.4 crash-loops on the migrated DB (look for a schema/migration error in `kubectl logs ... --previous`).**
Restore the PRE-CHANGE data under the pinned old app. Grafana's state is tiny (2 users, 1 service account, 0 annotations, 0 alert
rules) and everything else is provisioned from git, so this rung is a controlled DB reset, not a data-recovery emergency:
1. Keep the pin reverted (rung 1 commit pushed and reconciled). Scale to zero: `kubectl scale deployment/grafana -n monitoring --replicas=0`;
   wait for the pod to terminate and the Longhorn volume to detach. Do NOT `flux suspend`: HelmRelease `driftDetection` is unset on
   `grafana` (live `spec.driftDetection` empty; 0 of the 115 HelmReleases set it, 2026-10-30), so Flux does not revert a manual
   replica count. (If `helm-drift-detection` has landed since, re-check this: with drift detection on, suspend the HelmRelease first.)
2. Revert the volume to the pre-change snapshot in place: Longhorn UI (port-forward `svc/longhorn-frontend` in ns `storage`) ->
   Volume `grafana-config` -> attach in Maintenance mode -> Snapshots -> `grafana-pre-14-2-0` -> Revert -> detach.
   (Longhorn requires the maintenance-mode attach for a snapshot revert; this UI procedure was NOT rehearsed in planning.)
3. Bring it back explicitly - nothing else will: the revert already reconciled, so there is no spec change, no Helm upgrade, and
   replicas would stay 0. `kubectl scale deployment/grafana -n monitoring --replicas=1`, then
   `kubectl rollout status deployment/grafana -n monitoring --timeout=420s` and confirm 1/1 available with 3/3 containers ready
   (`kubectl get pods -n monitoring -l app.kubernetes.io/name=grafana`) BEFORE re-running section 4 with the 14.0.1 / 13.2.4 values.

**Rung 3 - the snapshot is unusable (it lives on the same volume's replicas).** Restore the newest Completed Backup CR of
`grafana-config` (the 2.5 gate proved one < 6 h old exists) by the repo-correct path in `docs/sops/backup.md` "Restore from Backup /
Bind Restored Volume to Application" (restore to a NEW volume name, then repoint the git-tracked PV/PVC; the same-name alternative
deletes the on-cluster replicas first and is the last resort). Total-loss fallback: delete the PVC contents and let Grafana
re-initialise; consequences measured above (service account + its token(s) re-issued; 2 users re-created on next SSO login).
The SERVICE_ACCOUNTS list printed in 2.7 names what to re-issue.

Trigger rollback on any `FAIL` that persists after one further 3-minute settle (scrape lag, init-container fetch, first-boot
migration). Per `docs/sops/grafana-image-changes.md` section 4 step 7 do not debug in place: monitoring is what you debug with.

## 6) Interference notes

- **Window (answer to the reschedule):** suggested **`nightly:2026-11-03`** with an operator GO recorded before the night
  (execution class is HUMAN-GATED now; the nightly default mode is operator-go-no-go). Why that night: it is after the
  Sunday 2026-11-01 Talos roll (`talos-linux-1.14.4`, exclusive) with one full day for the cluster to settle (nightly:2026-11-02
  is the first night after a 3-node reboot, so it is skipped), it shares the night only with `wazuh-100404-ci-build-tuning`
  (low, 25 min, ns security; capacity 6: 2 + 1), and it is three nights before `nightly:2026-11-06` `teslamate-4.4.0` which must
  not share a night or sit right behind a Grafana minor. Fallbacks, in order: `nightly:2026-11-05` (n8n-fleet, low;
  teslamate is next night: tighter), `sat-attended:2026-11-14` (python-fleet only; the day before `longhorn-1.13.0`
  `sun-attended:2026-11-15`, a day of soak). Avoid: 11-01 (exclusive Talos), 11-04 (memgraph, harmless but
  stacks restarts in the data tier), 11-06 (teslamate, hard conflict), 11-07 (otel-operator + helm-drift-detection), 11-08
  (etcd-timeouts, 110 min).
- **Why the nightly STOPped on 2026-10-29, and why it will not again.** The stop was the plan's OWN pre-check 2.3
  ("no grafana PR open"), not the auto-updater: Renovate had by then opened #374 for 14.2.0. 2.3 now accepts exactly the
  PR that proposes this plan's target and stops only for a DIFFERENT target.
- **How PR #374 and the `*grafana*` deny rule (`max: patch`) interact with this plan.**
  (a) Step 0 (`auto-update.py --apply`) only merges the SAFE subset; a chart minor is held by the rule, so #374 is never
  auto-merged and cannot race the hand-edit. Correct for 14.2.0: it moves the app.
  (b) `coverage.py` matches a plan file BEFORE it consults deny rules: the plan with `target: 14.2.0` covers the held 14.0.1 -> 14.2.0
  item (it stops re-dispatching planners). If Renovate retargets again (a 14.3.0 minor) the plan reads DRIFTED and must be
  refreshed (README), which pre-check 2.2 also catches at run time.
  (c) Once 14.2.0 is live, a later chart PATCH (14.2.x) is inside `max: patch` and WILL auto-apply at Step 0 under the normal gates
  - acceptable only because app patches on 13.3.x keep the schema; the rule's reasoning is unchanged. I recommend NOT narrowing
  the rule: this retarget is a live example of the hazard it names (a "minor chart" PR that is really an app minor).
  (d) Because the class is HUMAN-GATED, no AUTO-NIGHT/SD-10 path exists for this plan, so no gate here can silently skip it and
  the rule cannot cause a repeat STOP; the only run-time stop conditions are the explicit ones in section 2.
  (e) After the bump lands, Renovate autocloses #374 (step 7); the hand-edit and the PR carry the identical `version:` line so
  there is no merge conflict to resolve.
- **No shared infra is restarted.** Grafana is a tenant of `monitoring`; kube-prometheus-stack runs `grafana.enabled: false`.
  It snapshots one Longhorn volume (`grafana-config`), which is why `longhorn-1.13.0` is a declared conflict.
- **kube-prometheus-stack (PR #428-class bumps).** Auto-lane, so it cannot be named in `conflicts_with` (no plan file). It matters
  twice: Prometheus rolling makes the Prometheus gates unattributable, and kps ships `grafana_dashboard` ConfigMaps the Grafana
  sidecar loads, so it can move the dashboard count. Mitigation: 2.6 (timing only - Step 0 of the same window can still apply it
  first) and, as the real control, baselines taken AFTER Step 0 (2.7). The 48h gate counts upstream release age, so any statement
  about when a given kps PR becomes eligible is approximate.
- **`teslamate-4.4.0` (nightly:2026-11-06, schema migration, its section 4.5 reads Grafana)** - hard conflict: a Grafana restart
  re-pulls unpinned TeslaMate master dashboards, which may already target 4.4.0 while the DB is on 4.3.0. This plan runs first.
- **`otel-operator-0.25.1` / `edot-collector-0.163.2` / `edot-collector-0.164.0`** - checked, NO technical coupling: none reads
  Grafana (grep = 0 hits for the first two; 0.164.0 is a draft that already names this plan), Grafana's Elasticsearch datasource
  reads ES, not the collector. Declared as attribution hygiene only; at the suggested date they are 4-7 days away. They are the
  removable entries if a reviewer prefers fewer declared conflicts.
- **`talos-linux-1.14.4` (sun-attended:2026-11-01, exclusive)** - the slot is exclusive anyway; nightly:2026-11-03 also leaves two
  clear days so a failed Grafana gate cannot spill into the node roll's soak.
- **`longhorn-1.13.0` (sun-attended:2026-11-15), `helm-drift-detection` (sat 11-07), `flux-oci-chart-sources` (sun 11-22)** - each touches
  the Longhorn volume or the HelmRelease object itself; declared so a rollout cause stays singular.
- **`talos-power-tuning-ab`** (vetted, `exclusive: true`, touches monitoring, 310 min attended x2) has `window: null` and its own
  premises failing; it is NOT scheduled, so it does not constrain nightly:2026-11-03. If it is ever scheduled, its exclusivity already
  keeps this plan out of that slot (the scheduler refuses an occupied exclusive slot in both directions); no extra `conflicts_with` needed.
- **Old plan `grafana-chart-13.2.3`** is `status: superseded` (since 2026-09-14), two majors behind; untouched, nothing depends on it.
- **Could this be AUTO-class? No (changed from the 14.1.0 answer).** `capability_change: true` and `rollback_class: backup-restore`
  derive HUMAN-GATED; even with a `backup_gate` the capability flag alone blocks unattended execution. A future 13.3.x PATCH
  chart (appVersion patch, git-revert class, `capability_change: false`) would be eligible again.
- **No node reboot.** Single replica, `Recreate`, RWO PVC already handled; no change to that config.
