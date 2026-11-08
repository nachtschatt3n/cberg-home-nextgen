---
plan_id: grafana-chart-14.4.0
component: grafana
pr: 374                           # Renovate PR #374 (branch renovate/grafana-14.x) "update grafana ( 14.0.1 -> 14.4.0 )"; its diff is
                                  # exactly the one `version:` line (checked 2026-11-09). The plan hand-edits that SAME line and Renovate autocloses it.
kind: chart
current: "14.0.1"                 # MEASURED 2026-11-09: HR spec + history[0] 14.0.1 / app 13.2.4, Ready, pod grafana-c5f66c545-9swpr 3/3, 0 restarts
target: "14.4.0"                  # newest chart in grafana-community.github.io/helm-charts on 2026-11-09 (14.4.0 appVersion 13.3.0, released 2026-11-05)
update_type: minor                # chart minor AND Grafana application minor (13.2.4 -> 13.3.0)
risk: medium
est_duration_min: 45
needs_reboot: false
touches:
  namespaces: [monitoring, storage]
  resources:                      # every object below verified to EXIST live 2026-11-09
    - helmrelease/grafana         # git edit: spec.chart.spec.version 14.0.1 -> 14.4.0
    - deployment/grafana          # ROLLS ONCE (Recreate): grafana 13.2.4-distroless -> 13.3.0-distroless, both sidecars 2.14.1 -> 2.14.3
    - pvc/grafana-config          # sqlite (no [database] section; log "dbtype=sqlite3"); RWO longhorn-static. MIGRATED FORWARD by 13.3.0 on first boot
    - volume.longhorn.io/grafana-config   # ns storage: snapshot + backup BEFORE the roll; restore path in section 5
    - configmap/grafana           # re-rendered; content-identical except labels (render diff below)
    - servicemonitor/grafana      # label only; Prometheus must re-find the new pod
    - clusterrole/grafana-clusterrole   # label only
    - clusterrolebinding/grafana-clusterrolebinding   # label only
    - httproute/grafana           # NOT modified; reads envoy-internal. Listed because the SSO redirect and UI are reached through it
  shared: [monitoring]            # tenant of ns monitoring, restarts no shared infra. It READS Prometheus, Alertmanager, Elasticsearch, InfluxDB,
                                  # the TeslaMate and pellets Postgres and Authentik (SSO) in verification, and snapshots one Longhorn volume.
                                  # Declared per authoring rule 4 so a same-night monitoring change is attributable.
depends_on: []
conflicts_with:                   # ONLY this field is honoured by the scheduler. Built 2026-11-09 from every open plan's frontmatter. Strongest first:
  - longhorn-1.13.0               # grafana-config is a Longhorn volume; this plan snapshots/backs it up and may restore it. EXCLUSIVE-class engine roll
  - talos-linux-1.14.5            # node roll evicts grafana mid-gate (EXCLUSIVE slot anyway)
  - postgres-digest-refresh-2026-11   # restarts the pellets Postgres Grafana queries; a restart during the gate reads as a datasource failure
  - redis-fleet-8.10.3            # reciprocal (their controls read Prometheus; Grafana is the operator's second instrument)
  - helm-drift-detection          # edits spec of EVERY HelmRelease incl. helmrelease/grafana: same object, attribution
  - flux-oci-chart-sources        # rewrites the chart source of HelmReleases incl. grafana (it also rolls deployment/grafana)
  - edot-collector-0.165.0        # monitoring-namespace attribution: keep a failed gate attributable to ONE change
  - open-webui-0.13.0             # reciprocal (monitoring is its second instrument)
  - python-fleet-3.15.2-alpine    # reciprocal (reads Prometheus, same instrument as this plan's section 4)
  - coredns-1.50.2                # the download-dashboards init container fetches 41 URLs from GitHub at every start; a DNS roll mid-fetch writes
                                  # 0-byte dashboards (the cert-manager comment in helmrelease.yaml documents the failure shape)
  - kube-prometheus-stack-92.22.0 # draft plan (2026-11-09): restarts Prometheus/Alertmanager (this plan's instrument) and ships the sidecar dashboard ConfigMaps this plan gates on
  - envoy-gateway-1.10.0          # DRAFT, untracked at planning time so its own file could NOT be given the reciprocal ref (whoever commits it must add
                                  # grafana-chart-14.4.0). Restarts the gateways that serve grafana's HTTPRoute and the DNS gate; blurs the SSO check
exclusive: false
security_ref: F-482f421e          # open warning "grafana/grafana:13.2.4-distroless ... newer upstream tag available". Detail stays in the DB;
                                  # 13.3.0 is the newest tag on the 13.3 line, so this bump is the available remediation (we bump, never rebuild).
capability_change: true           # Grafana 13.2.4 -> 13.3.0 is an application MINOR with user-visible default changes (release notes: "Make the auto grid
                                  # to be default", "Unified storage: Enable automatic cleanup of deleted resources by default") => never unattended
                                  # without an operator GO.
rollback_class: backup-restore    # the sqlite schema is migrated forward on first boot; a pin revert may not boot on it
backup_gate: "2.5: runbooks/longhorn-backup-age.py grafana-config --max-hours 6 prints FRESH, PLUS a named pre-change Longhorn snapshot grafana-pre-14-4-0 listed readyToUse on the volume. Both must PASS before the pin is edited. Freshness proof only - NOT a restore proof; acceptable because the plan is human-gated and section 5 states what a total DB loss costs (2 users, 1 service account, 0 alert rules, 0 annotations measured 2026-11-09)."
finding_refs: [F-c01c08c6, F-482f421e]   # F-c01c08c6 "grafana: chart 14.0.1 -> 14.4.0 (minor)" (version, PLAN lane, open - VERIFIED via policy-cli finding list
                                  # --grep grafana 2026-11-09); F-482f421e security warning, newer tag exists (open). F-03d0843d (ES password rotation
                                  # pending, deferred) is related, not owned: a restart makes the pod re-read the secret, see section 6.
review: ready-for-go@2026-11-09   # plan-reviewer 2026-11-09: needs-fix (kps plan conflicts_with link missing/stale), fixed; HUMAN-GATED: needs an operator GO via home-operation before the window runs
status: vetted
window: nightly:2026-11-11        # reviewer: acceptable only with a recorded operator GO (65 of 70 min); attended fallback sat-attended:2026-12-12
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/grafana-image-changes.md
  - docs/sops/backup.md
  - docs/sops/monitoring.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-11-09"
supersedes: grafana-14.1.0        # RETARGET 14.2.0 -> 14.4.0 done as a NEW plan id at operator request; grafana-14.1.0 carries superseded_by: grafana-chart-14.4.0
premises:
  - id: live-chart-is-14.0.1
    why: "`current:` claims 14.0.1. If the HR already moved (manual bump, another plan), the diff and rollback baseline below are stale."
    run: kubectl get helmrelease grafana -n monitoring -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: "14.0.1"
  - id: live-image-is-13.2.4-distroless
    why: "The migration analysis assumes the RUNNING app is 13.2.4 with no image.tag override. A different live tag voids the app-delta analysis (someone already took 13.3.0)."
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
    why: "GF_PLUGINS_PREINSTALL_DISABLED=true is load-bearing (2026-09-12: its absence cost 2.5 days of dead TeslaMate/Pellets panels after ONE restart). This roll restarts the pod, so the guard must be live BEFORE we restart."
    run: kubectl get deploy grafana -n monitoring -o jsonpath='{.spec.template.spec.containers[?(@.name=="grafana")].env[?(@.name=="GF_PLUGINS_PREINSTALL_DISABLED")].value}'
    expect_exact: "true"
  - id: repo-cache-sees-target
    why: "`helm show chart ... --version 14.4.0` fails on a stale local index and is indistinguishable from the chart not existing. Refresh with `helm repo update grafana-community` if this fails."
    run: helm show chart grafana-community/grafana --version 14.4.0
    expect_contains: "version: 14.4.0"
  - id: target-chart-appversion-is-13.3.0
    why: "THE central fact of the plan. If 14.4.0 is ever repackaged with another appVersion, the app-delta analysis (13.2.4 -> 13.3.0, forward-only sqlite migration, backup-restore class) is void and the plan must be re-triaged."
    run: helm show chart grafana-community/grafana --version 14.4.0
    expect_contains: "appVersion: 13.3.0"
  - id: container-set-baseline
    why: "Verification asserts the pod keeps exactly these three containers (the opt-in sc-repositories / init-sc-plugins sidecars stay off). Baseline must hold before the change."
    run: kubectl get pod -n monitoring -l app.kubernetes.io/name=grafana -o jsonpath='{.items[*].spec.containers[*].name}'
    expect_exact: "grafana-sc-dashboard grafana-sc-datasources grafana"
  - id: sidecar-image-baseline
    why: "The chart default sidecar moves 2.14.1 -> 2.14.3 under this bump. If a sidecar pin appeared in values the render diff in section 1 no longer holds."
    run: kubectl get pod -n monitoring -l app.kubernetes.io/name=grafana -o jsonpath='{.items[0].spec.containers[0].image}'
    expect_exact: "quay.io/kiwigrid/k8s-sidecar:2.14.1"
  - id: grafana-volume-healthy
    why: "The backup gate and the section 5 restore both assume the Longhorn volume is attached and healthy (2 replicas)."
    run: kubectl get volume grafana-config -n storage -o jsonpath='{.status.state} {.status.robustness}'
    expect_exact: "attached healthy"
  - id: provisioned-teslamate-dashboards-in-git
    why: "The 23 TeslaMate dashboards are git-provisioned (467747761 added the 12 that were missing): the gate asserts TeslaMate=23. If someone removed entries from values the baseline in 2.7 will say so, but this premise catches it earlier."
    run: grep -c 'teslamate/master/grafana/dashboards/.*\.json$' kubernetes/apps/monitoring/grafana/app/helmrelease.yaml
    expect_exact: "23"
---

# grafana: chart 14.0.1 -> 14.4.0 (Grafana 13.2.4 -> 13.3.0, application minor)

## 1) Summary & why held

**What this is.** Renovate PR #374 (`renovate/grafana-14.x`) now proposes chart **14.0.1 -> 14.4.0** (title updated 2026-11-05). This plan
replaces `grafana-14.1.0` (id kept through two retargets, last targeting 14.2.0, status vetted/ready-for-go 2026-10-30, never executed); that
file is now `status: superseded` with `superseded_by: grafana-chart-14.4.0`. The README prefers refreshing in place; the new id was requested
by the operator. Its four resolve-by-id consumers were handled: other plans' `conflicts_with` were re-pointed here, `finding_refs` moved
(F-c01c08c6 is OPEN again with the 14.4.0 title; F-482f421e still open), no `window:` stamp existed (both null), and no go/no-go issue was
keyed on the old id at planning time. If one exists, re-key it to `grafana-chart-14.4.0`.

**Chart repo (measured 2026-11-09, `helm search repo grafana-community/grafana --versions`; the old `grafana.github.io` repo is frozen at 10.5.15,
see the repo note in `helmrelease.yaml`).**
```
14.4.0  appVersion 13.3.0  released 2026-11-05   <- PR #374 / this plan (newest)
14.3.1  appVersion 13.3.0  released 2026-11-02   (chart-releaser CI + k8s-sidecar 2.14.3)
14.3.0  appVersion 13.3.0  released 2026-10-31   (init-sc-plugins render fix, opt-in)
14.2.0  appVersion 13.3.0  released 2026-10-27   (the previous plan's target: app 13.2.4 -> 13.3.0)
14.1.0  appVersion 13.2.4                        (opt-in Git Sync sidecar only)
14.0.1  appVersion 13.2.4                        <- LIVE
```

**Chart source diff 14.2.0 -> 14.4.0 (helm pull of each version, `diff -ru`, 2026-11-09), the complete list:**
1. `values.yaml`: `sidecar.image.tag` 2.14.1 -> **2.14.3** (the only non-comment values change). k8s-sidecar 2.14.2 was tagged but never released (its release
   build failed); 2.14.3 "notes cover all changes since 2.14.1": a Python base-image move for riscv64 support plus a CI-dependency bump. No runtime
   behaviour change in the notes; `quay.io/kiwigrid/k8s-sidecar:2.14.3` exists (quay API, created 2026-11-02).
2. 14.3.0: `_pod.tpl` renders an `init-sc-plugins` initContainer when `sidecar.plugins.initPlugins` is true. Default false, we do not set it: no render effect.
3. **14.4.0 (README "To 14.4.0", chart PR #945): pod templates no longer carry `helm.sh/chart`** (new `grafana.podLabels` helper; Deployment and StatefulSet
   templates use it). The label stays on every object. Consequences for THIS plan: (a) the old plan's gate "pod label helm.sh/chart == grafana-<chart>" would
   FAIL on a healthy 14.4.0 pod; section 4 asserts identity differently (Deployment label, pod `app.kubernetes.io/version`, pod-template-hash, images).
   (b) kube-state-metrics `label_helm_sh_chart` series stop populating for grafana pods: `grep -rn "label_helm_sh_chart" kubernetes runbooks` = no consumer
   (the only `helm.sh/chart` hits are plans/docs). (c) Good news: future chart bumps with no other change no longer restart the pod.

**Render diff under OUR live `spec.values`** (`helm template`, chart 14.0.1 vs 14.4.0, 2026-11-09): `helm.sh/chart` label (13 objects),
`app.kubernetes.io/version` 13.2.4 -> 13.3.0 (13 objects + pod), the pod-template `helm.sh/chart` label removed, **three image lines**
(`grafana:13.2.4-distroless` -> `13.3.0-distroless`, two `k8s-sidecar` 2.14.1 -> 2.14.3). Env (including `GF_PLUGINS_PREINSTALL_DISABLED`), volumes,
containers, ConfigMap data, selectors: unchanged. Container set stays 3.

**Why held: the application moves, not the chart.** The `*grafana*` rule in `runbooks/auto-update-policy.yaml` (`max: patch`) exists because chart minors can
move appVersion, crossing forward-only sqlite migrations and downgrading rollback from git-revert to restore-from-backup. Here the appVersion
moves **13.2.4 -> 13.3.0**. Grafana 13.3.0 (`grafana/grafana` v13.3.0, released 2026-10-27): a large feature release; its one Breaking-changes entry is the
rename of the plugins-marketplace config section (`marketplace` -> `plugins_marketplace`; we set no such section); `Dashboards: Make the auto grid to be default`
and `Unified storage: Enable automatic cleanup of deleted resources by default` change defaults; alerting import/auto-sync rework does not apply
(`handleGrafanaManagedAlerts: false`, 0 alert rules); Git Sync is unused. Security-section detail is intentionally not copied (see `security_ref`).

**The schema migrates.** Release notes do not say; the source does. Checked 2026-11-09 with `gh api repos/grafana/grafana/contents/pkg/services/sqlstore/migrations/migrations.go?ref=<tag>`:
the names `AddManagedFolderVariableActionsMigration`, `CollateBinAlertRuleFolderFullpath`, `ExpandAlertRuleMissingSeriesEvalsToResolve` occur **0 times at v13.2.4
and 3 times at v13.3.0**. (`CollateBinAlertRuleFolderFullpath` is mysql/postgres-only; the other two run on sqlite; unified storage adds a table.) Grafana's own
DB is **sqlite** on the `grafana-config` PVC (live log: `Connecting to DB dbtype=sqlite3`; no `[database]` section in the ini), not Postgres. The Pellets and
TeslaMate Postgres instances are DATA SOURCES that Grafana only reads; they are not migrated. Therefore the first 13.3.0 boot WILL migrate (`performed>0`):
backup-restore is a consequence, not a precaution, and section 4 expects non-zero migrator lines. Whether 13.2.4 would boot on the migrated file is unknown.

**Everything stateful that must survive (measured live 2026-11-09 by API; the migration is the only thing that touches it):**
- 18 datasource plugins (ids listed in 2.7), 7 provisioned datasources (Alertmanager, Prometheus, InfluxDB, Unpoller InfluxDB, Elasticsearch, TeslaMate, Pellets;
  the two Postgres ones use plugin `grafana-postgresql-datasource` 13.0.4; prometheus 13.2.3, elasticsearch 12.8.2, influxdb 13.1.7), all 6 with a backend `/health` == OK
  (Alertmanager has no backend health: proxy `/api/v2/status` is the check).
- **84 dashboards**: General 44, TeslaMate **23**, Kubernetes 6, UniFi 5, Flux 2, Nginx 2, Media 1, Pellets 1. The 23 TeslaMate dashboards are git-provisioned in
  `helmrelease.yaml` (commit 467747761 added the 12 that were missing) but their JSON is fetched by the `download-dashboards` init container from the
  **unpinned TeslaMate `master`** at every pod start; the rest come from `gnetId`/GitHub URLs and from **37 sidecar ConfigMaps** (`grafana_dashboard=1`, kube-prometheus-stack
  and apps). A fetch failure writes 0-byte files, so the gate counts dashboards per folder and checks that every TeslaMate dashboard has >= 1 panel.
- Authentik SSO (`auth.generic_oauth` enabled, F-5a894d0e): `/api/frontend/settings` oauth name `Authentik`, plus `/login/generic_oauth` must 302 to the authorize endpoint.
- DB contents: 2 users, 1 service account (`n8n`), 0 alert rules, 0 annotations. Total loss costs the service account's token(s) and per-user prefs; users re-create on SSO login.
- Plugin trap: `GF_PLUGINS_PREINSTALL_DISABLED=true` (env, load-bearing since 2026-09-12, comment block in `helmrelease.yaml`) plus ini `preinstall_auto_update = false`.
  13.3.0 may change the bundled plugin set (13.2.0 grew it 2 -> 13); the post-restart gate is the 18 plugin IDS (not just the count) plus per-datasource `/health`,
  compared with the 13.3.0 image measured OFF the live PVC in 2.8.

**Verdict.** `risk: medium`, `capability_change: true`, `rollback_class: backup-restore`, no reboot, ~45 min, ~1-3 min of Grafana downtime. Execution class derives to
HUMAN-GATED (explicit operator GO). It cannot be AUTO-NIGHT or SD-10 pre-approved. Rationale for 14.4.0 rather than 14.2.0: identical application delta (both ship 13.3.0), strictly
fewer future restarts, the sidecar base-image refresh, and it is what PR #374 proposes; the extra chart delta is small (list above) and is covered by the gates.
**Alternative considered and rejected:** staying on 13.2.x would mean Grafana 13.2.5 (published 2026-10-27), but no chart ships it (every 14.x since 14.2.0 pins 13.3.0), so
it would need an `image.tag` override, which the HelmRelease header forbids ("roll the variant, never the version").

## 2) Pre-checks

Run every premise first: `.venv/bin/python3 runbooks/plan-premises.py grafana-chart-14.4.0 --require-premises` (no `REFUSED` line may remain).
Then, in order (do not start Step 3 unless each prints the stated result):

```bash
# 2.1 Refresh the local helm index (premise repo-cache-sees-target depends on it) and confirm the target.
helm repo update grafana-community
helm show chart grafana-community/grafana --version 14.4.0 | grep -E '^(version|appVersion):'
# expect exactly: appVersion: 13.3.0 / version: 14.4.0   (anything else: STOP, plan is void)

# 2.2 Newer target? If upstream shipped a chart NEWER than 14.4.0, this plan is DRIFTED: STOP and refresh (README), do not roll a stale target.
helm search repo grafana-community/grafana --versions -o json | python3 -c "
import sys,json; v=[x['version'] for x in json.load(sys.stdin)][:3]; print('newest charts:',v)
print('TARGET_IS_NEWEST' if v[0]=='14.4.0' else 'NEWER_CHART_EXISTS - STOP, refresh the plan (or consciously stay on 14.4.0 and say why)')"

# 2.3 Renovate PR handling. PR #374 exists ON PURPOSE.
gh pr list --state open --json number,title --jq '.[]|select(.title|test("grafana";"i"))|[.number,.title]|@tsv'
# PASS = no output, OR exactly one line: 374<TAB>feat(helm): update grafana ( 14.0.1 -> 14.4.0 )   (the real title uses the unicode arrow)
# STOP = any other grafana PR, or #374 proposing a target other than 14.4.0 (retargeted again: refresh the plan first).
# #374's diff is exactly the one `version:` line. Step 3 hand-edits that same line plus a history comment; Renovate autocloses #374 once main
# carries 14.4.0. Do NOT merge #374 AND hand-edit. Do NOT close #374 first (Renovate would reopen it against the next push).

# 2.4 Release is Ready, no in-flight reconcile, pod healthy with zero restarts.
flux get helmrelease grafana -n monitoring
kubectl get pods -n monitoring -l app.kubernetes.io/name=grafana
kubectl get pod -n monitoring -l app.kubernetes.io/name=grafana -o jsonpath='{.items[0].status.containerStatuses[*].restartCount}{"\n"}'   # 0 0 0

# 2.5 BACKUP GATE (rollback class backup-restore). The nightly Longhorn job (CronJob storage/daily-backup-all-volumes, 23:00 UTC) leaves a backup
#     ~4.5 h old at 03:30 local; on any other slot take a fresh one first (docs/sops/backup.md "Manual Backup"). The helper, never an inline
#     status.volumeName filter (F-a915dd47: unsynced nightly CRs read stale):
.venv/bin/python3 runbooks/longhorn-backup-age.py grafana-config --max-hours 6
# PASS = "grafana-config <age>h FRESH via ..." exit 0 (measured 2026-11-09: 0.5h FRESH via backup-cr). STALE/NONE (exit 1) or lookup error (exit 2): STOP.
# Negative control (measured 2026-11-09): `... nonexistent-vol --max-hours 26` prints "ERROR: no Longhorn volume named" and exits 2, so a typo cannot pass.
# Snapshot half of the gate: a NAMED pre-change snapshot (Longhorn Snapshot CR, executor-owned single apply; CRD snapshots.longhorn.io present).
cat <<'YAML' | kubectl apply -f -
apiVersion: longhorn.io/v1beta2
kind: Snapshot
metadata:
  name: grafana-pre-14-4-0
  namespace: storage
spec:
  volume: grafana-config
  createSnapshot: true
YAML
for i in $(seq 1 30); do   # readyToUse flips asynchronously; poll up to 150 s, never read it once
  r=$(kubectl get snapshots.longhorn.io -n storage grafana-pre-14-4-0 -o jsonpath='{.status.readyToUse}'); [ "$r" = true ] && break; sleep 5
done
kubectl get snapshots.longhorn.io -n storage grafana-pre-14-4-0 -o jsonpath='{.status.readyToUse} {.status.creationTime}{"\n"}'
# PASS = "true <timestamp>". Anything else = SNAPSHOT_NOT_READY: STOP, do not edit the pin.
# (Caveat: the manifest fields were checked against the live CRD schema but NOT applied in planning - read-only session. If the apply is rejected, take
#  the snapshot from the Longhorn UI (Volume grafana-config -> Take Snapshot, name grafana-pre-14-4-0) and treat the UI listing as the gate.)

# 2.6 Same-night interference: Prometheus is this window's instrument. kube-prometheus-stack bumps are held by the time-boxed deny rule (revisit by
#     2026-11-30) but a deliberate bump may land in the same window. HONEST SCOPE: this settle check is mostly timing; the REAL control is that the 2.7
#     baselines are taken AFTER Step 0 of the window, so a kps-driven change cannot be mistaken for a Grafana regression.
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
# PASS = KPS_SETTLED. A wrong pod name makes kubectl exit non-zero and the script raise: it fails closed.

# 2.7 BASELINES - taken AFTER Step 0 of this window, never carried over from an earlier day. Run the script, then paste its `export` lines into the shell
#     that will run section 4 (it also prints SERVICE_ACCOUNTS for the Rung-3 re-issue note). Measured 2026-11-09 output is shown in the comments.
#!/usr/bin/env bash
NS=monitoring
U=$(kubectl get secret grafana-admin-secret -n $NS -o jsonpath='{.data.admin-user}' | base64 -d)
PW=$(kubectl get secret grafana-admin-secret -n $NS -o jsonpath='{.data.admin-password}' | base64 -d)
kubectl port-forward -n $NS svc/grafana 33001:80 >/dev/null 2>&1 &
PF=$!; sleep 5; A=http://127.0.0.1:33001
echo "export BASE_IDS=$(curl -s -u "$U:$PW" "$A/api/plugins?embedded=0&type=datasource" | python3 -c 'import sys,json; print(",".join(sorted(x["id"] for x in json.load(sys.stdin))))')"
S=$(curl -s -u "$U:$PW" "$A/api/search?type=dash-db&limit=1000")
echo "export BASE_DASH=$(printf '%s' "$S" | python3 -c 'import sys,json; print(len(json.load(sys.stdin)))')"
echo "export BASE_FOLDERS='$(printf '%s' "$S" | python3 -c '
import sys,json,collections
c=collections.Counter(x.get("folderTitle","General") for x in json.load(sys.stdin)); print(",".join(f"{k}={c[k]}" for k in sorted(c)))')'"
echo "SERVICE_ACCOUNTS: $(curl -s -u "$U:$PW" "$A/api/serviceaccounts/search?perpage=100" | python3 -c 'import sys,json; print(",".join(s["name"] for s in json.load(sys.stdin)["serviceAccounts"]))')"
kill $PF 2>/dev/null; wait $PF 2>/dev/null
echo "export BASE_CMS=$(kubectl get cm -A -l grafana_dashboard=1 --no-headers | wc -l | tr -d ' ')"
echo "export PREV_POD_HASH=$(kubectl get pod -n $NS -l app.kubernetes.io/name=grafana -o jsonpath='{.items[0].metadata.labels.pod-template-hash}')"
P=/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query
echo "export BASE_PROMDS=$(kubectl get --raw "$P?query=count%28grafana_plugin_build_info%7Bplugin_type%3D%22datasource%22%7D%29" | python3 -c 'import sys,json; print(json.load(sys.stdin)["data"]["result"][0]["value"][1])')"
# 2026-11-09: BASE_DASH=84 BASE_FOLDERS='Flux=2,General=44,Kubernetes=6,Media=1,Nginx=2,Pellets=1,TeslaMate=23,UniFi=5' BASE_CMS=37 BASE_PROMDS=13 PREV_POD_HASH=c5f66c545 SERVICE_ACCOUNTS: n8n
#             BASE_IDS=alertmanager,cloudwatch,elasticsearch,grafana-azure-monitor-datasource,grafana-postgresql-datasource,grafana-pyroscope-datasource,
#                      grafana-testdata-datasource,graphite,influxdb,jaeger,loki,mssql,mysql,opentsdb,prometheus,stackdriver,tempo,zipkin   (18)
# GATE: BASE_IDS must list 18 ids. If it is already fewer, Grafana is ALREADY degraded (the 2026-09-12 signature is 13): STOP and fix that first -
# the verification would "pass" against a broken baseline. BASE_FOLDERS must show TeslaMate=23.

# 2.8 PRE-FLIGHT the candidate image OFF the live PVC (docs/sops/grafana-image-changes.md section 8 B, distroless form).
#     A throwaway pod mounts NO grafana-config, so what it reports is exactly what the IMAGE ships. A 13.2.4 CONTROL runs first: it must report the live
#     baseline id set (proves the method counts what the live pod counts).
#     NOT REHEARSED IN PLANNING (needs `kubectl run`; the session is read-only). What WAS checked: `bash -n`, the overrides JSON parsed with json.loads.
#     The pods copy the live container's hardening (uid/gid 472, readOnlyRootFilesystem, drop ALL, RuntimeDefault seccomp, emptyDirs only at /tmp,
#     /var/lib/grafana, /var/lib/grafana-search); the guard env var is set exactly as in the live HelmRelease. GF_LOG_MODE=console is REQUIRED (the default
#     "console file" writes to the read-only root and would fail the zero-count rule). Carried over unchanged from the vetted grafana-14.1.0 plan, plus the
#     id list: PREFLIGHT_IDS is what section 4 compares the live pod to.
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
  rm -f "$S"/grafana-preflight-*.json   # these hold the throwaway admin password
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
  "env":[{"name":"GF_PLUGINS_PREINSTALL_DISABLED","value":"true"},{"name":"GF_LOG_MODE","value":"console"},{"name":"GF_SECURITY_ADMIN_PASSWORD","value":pw},
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
  ids=$(curl -s -u admin:"$ADMINPW" 'http://127.0.0.1:33002/api/plugins?embedded=0&type=datasource' | python3 -c 'import sys,json; print(",".join(sorted(x["id"] for x in json.load(sys.stdin))))')
  n=$(printf '%s' "$ids" | awk -F, '{print NF}')
  ro=$(kubectl logs "$N" -n monitoring | grep -i -c -e 'read-only file system' -e 'unlinkat')
  echo "PREFLIGHT $TAG datasource plugins: $n   read-only-fs/unlinkat log lines: $ro"
  echo "PREFLIGHT_IDS $TAG $ids"
  kill "$PF" 2>/dev/null; PF=
  kubectl delete pod "$N" -n monitoring --wait=true
done
EOF2
bash -n "$S/grafana-preflight.sh" && S="$S" bash "$S/grafana-preflight.sh"
# PASS = the 13.2.4 control PREFLIGHT_IDS equals BASE_IDS AND the 13.3.0 PREFLIGHT_IDS is a superset of BASE_IDS AND both "read-only-fs/unlinkat" counts are 0.
# Record the 13.3.0 id list as PREFLIGHT_IDS (export it, section 4 requires it). A 13.3.0 list MISSING any baseline id: STOP. PREFLIGHT_NOT_READY is an
# infrastructure failure, not a verdict: re-run once, then STOP.

# 2.8b Sidecar image is pullable BEFORE the Recreate roll (Recreate kills the old pod first: an ImagePullBackOff on 2.14.3 would be an outage, not a delay).
kubectl run grafana-preflight-sc -n monitoring --image=quay.io/kiwigrid/k8s-sidecar:2.14.3 --restart=Never --labels=app.kubernetes.io/component=grafana-preflight --command -- python -c 'print("sidecar-ok")'
kubectl wait pod/grafana-preflight-sc -n monitoring --for=jsonpath='{.status.phase}'=Succeeded --timeout=180s
kubectl logs grafana-preflight-sc -n monitoring ; kubectl delete pod grafana-preflight-sc -n monitoring --wait=false
# PASS = "sidecar-ok". (NOT rehearsed: needs a pod create; the image's python entrypoint is assumed from the k8s-sidecar Dockerfile base. If `python` is
#  absent but the pod reaches Running/ErrImage-free, the pull itself succeeded - that is the property being tested.) This pulls on one node only; the roll may
#  land on another, so an ImagePullBackOff there is handled by Rung 1.

# 2.9 Rehearse the gate script on the CURRENT state. FIRST save it: run the `cat > "$S/grafana-verify.sh"` heredoc from section 4 (a file write only). Then:
#       EXPECT_CHART=14.0.1 EXPECT_APP=13.2.4 EXPECT_SIDECAR=2.14.1 POD_CHART_LABEL=grafana-14.0.1 MIGRATIONS=none bash "$S/grafana-verify.sh"
#     (with the 2.7 BASE_* exports in the environment). It must print ALL GATES PASS. If not, the pre-state is already degraded - STOP, edit nothing.
```

## 3) Steps (GitOps)

No alert silence is needed: no Grafana-specific alert rule exists in the repo and the outage is ~1-3 min. Expect a longer first boot than a patch (schema migration,
4 migrators, init-container dashboard fetch of 41 URLs).

1. Edit the chart pin in `kubernetes/apps/monitoring/grafana/app/helmrelease.yaml`. Dry-tested on a scratch copy on macOS (BSD sed); the resulting diff is exactly:
   ```
   11c11
   <       version: 14.0.1
   ---
   >       version: 14.4.0
   ```
   ```bash
   sed -i '' 's/^\(      version: \)14\.0\.1$/\114.4.0/' kubernetes/apps/monitoring/grafana/app/helmrelease.yaml
   git diff --stat kubernetes/apps/monitoring/grafana/app/helmrelease.yaml    # expect: 1 file, 1 insertion, 1 deletion
   ```
2. With the Edit tool, add this to the dated history block, directly above `    deploymentStrategy:` (keep all prior history):
   ```
       # 2026-11-xx: chart 14.4.0 - Grafana 13.2.4 -> 13.3.0 (APPLICATION minor: sqlite schema migrates forward on first
       # boot; rollback class backup-restore, NOT git-revert). Sidecars 2.14.1 -> 2.14.3. Chart 14.4.0 drops helm.sh/chart from the
       # POD template (verify identity via the Deployment label / pod-template-hash, not a pod label). Pre-change Longhorn
       # snapshot grafana-pre-14-4-0 + backup. Plan: grafana-chart-14.4.0. PR #374. Findings: F-c01c08c6, F-482f421e.
   ```
   (Replace `xx`.) Run `git diff`; confirm only the version line and these comment lines changed.
3. Commit, VERIFY THE SUBJECT, push (shared worktree: `--only` with explicit path; never `git add -A`):
   ```bash
   git commit --only kubernetes/apps/monitoring/grafana/app/helmrelease.yaml \
     -m "chore(grafana): chart 14.0.1 -> 14.4.0 (Grafana 13.2.4 -> 13.3.0, forward-only sqlite migration) [plan grafana-chart-14.4.0, PR #374, findings F-c01c08c6 F-482f421e]"
   git log -1 --format=%s     # must be exactly the line above; if another session's message landed, amend BEFORE pushing
   git show --stat HEAD       # exactly one file: the helmrelease.yaml
   git push
   ```
   (Run the commit in a shell where `SWEEP_PG_DSN` is NOT sourced - it breaks the pre-commit gate.)
4. Let the push webhook reconcile Flux, then confirm the pin landed before concluding anything:
   ```bash
   kubectl get helmrelease grafana -n monitoring -o jsonpath='{.spec.chart.spec.version}{"\n"}'   # expect 14.4.0
   ```
   If it still shows 14.0.1 after 10 min, and only then: `flux reconcile helmrelease grafana -n monitoring --with-source`.
5. Watch the single `Recreate` roll (single replica, RWO PVC) and the first-boot log:
   ```bash
   kubectl rollout status deployment/grafana -n monitoring --timeout=420s
   kubectl get pods -n monitoring -l app.kubernetes.io/name=grafana     # NEW pod name, 3/3, restarts 0
   ```
   `rollout status` can green-light the old generation: section 4 independently asserts the new pod (images, `app.kubernetes.io/version`, pod-template-hash).
6. **Wait 90 s after the pod is Ready** (Prometheus scrape interval) before running section 4.
7. After a green section 4, confirm Renovate closed #374: `gh pr view 374 --json state --jq .state` -> `CLOSED`. If still OPEN with the 14.4.0 title after the next
   Renovate run, close it with a comment pointing at the bump commit. Delete snapshot `grafana-pre-14-4-0` only after the soak below.

## 4) Verification

Floor (shape): HR Ready at 14.4.0, pod 3/3 on the new generation. The CONTENTS gates are what matter and are all in one script so none can be skipped. Save and run
it (needs `kubectl`, `curl`, `python3`; it port-forwards `svc/grafana` to 33001 itself and exits non-zero on any FAIL):

```bash
S=${TMPDIR:-/tmp}; cat > "$S/grafana-verify.sh" <<'EOF'
#!/usr/bin/env bash
# usage (post-change, forward roll):
#   EXPECT_CHART=14.4.0 EXPECT_APP=13.3.0 EXPECT_SIDECAR=2.14.3 POD_CHART_LABEL=absent MIGRATIONS=expect \
#   BASE_IDS=<2.7> BASE_DASH=<2.7> BASE_FOLDERS=<2.7> BASE_CMS=<2.7> BASE_PROMDS=<2.7> PREV_POD_HASH=<2.7> PREFLIGHT_IDS=<2.8> bash grafana-verify.sh
# usage (rehearsal on the pre-change state, and the rollback check):
#   EXPECT_CHART=14.0.1 EXPECT_APP=13.2.4 EXPECT_SIDECAR=2.14.1 POD_CHART_LABEL=grafana-14.0.1 MIGRATIONS=none \
#   BASE_IDS=.. BASE_DASH=.. BASE_FOLDERS=.. BASE_CMS=.. BASE_PROMDS=.. bash grafana-verify.sh
fail=0
ok()  { echo "PASS  $1"; }
bad() { echo "FAIL  $1"; fail=1; }
: "${EXPECT_CHART:?}" "${EXPECT_APP:?}" "${EXPECT_SIDECAR:?}" "${POD_CHART_LABEL:?absent|grafana-X.Y.Z}" "${MIGRATIONS:?none|expect}" "${BASE_IDS:?}" "${BASE_DASH:?}" "${BASE_FOLDERS:?}" "${BASE_CMS:?}" "${BASE_PROMDS:?}"
if [ "$MIGRATIONS" = expect ]; then : "${PREFLIGHT_IDS:?run 2.8 first and pass the 13.3.0 id list}" "${PREV_POD_HASH:?pod-template-hash recorded in 2.7}"; fi
NS=monitoring; SEL=app.kubernetes.io/name=grafana

# V1 release, image and pod identity. On 14.4.0 the pod template NO LONGER carries helm.sh/chart (chart PR #945), so the old
# "pod chart label == grafana-<chart>" gate is wrong for the target: identity is asserted via the Deployment's own label, the
# pod's app.kubernetes.io/version label, the pod-template-hash (changed on the forward roll) and the containers' images.
c=$(kubectl get helmrelease grafana -n $NS -o jsonpath='{.status.history[0].chartVersion} {.status.conditions[?(@.type=="Ready")].status}')
[ "$c" = "$EXPECT_CHART True" ] && ok "HR chart/Ready: $c" || bad "HR chart/Ready: got '$c' want '$EXPECT_CHART True'"
dl=$(kubectl get deploy grafana -n $NS -o jsonpath='{.metadata.labels.helm\.sh/chart}')
[ "$dl" = "grafana-$EXPECT_CHART" ] && ok "deployment label helm.sh/chart=$dl" || bad "deployment label '$dl' want grafana-$EXPECT_CHART"
img=$(kubectl get deploy grafana -n $NS -o jsonpath='{.spec.template.spec.containers[?(@.name=="grafana")].image}')
[ "$img" = "docker.io/grafana/grafana:$EXPECT_APP-distroless" ] && ok "image $img" || bad "image is '$img' want docker.io/grafana/grafana:$EXPECT_APP-distroless"
si=$(kubectl get pod -n $NS -l $SEL -o jsonpath='{.items[*].spec.containers[?(@.name!="grafana")].image}')
[ "$si" = "quay.io/kiwigrid/k8s-sidecar:$EXPECT_SIDECAR quay.io/kiwigrid/k8s-sidecar:$EXPECT_SIDECAR" ] && ok "both sidecars on $EXPECT_SIDECAR" || bad "sidecar images '$si' want 2 x quay.io/kiwigrid/k8s-sidecar:$EXPECT_SIDECAR"
np=$(kubectl get pod -n $NS -l $SEL --no-headers | wc -l | tr -d ' ')
[ "$np" = 1 ] && ok "exactly one grafana pod" || bad "grafana pod count $np (old generation still around?)"
pl=$(kubectl get pod -n $NS -l $SEL -o jsonpath='{.items[0].metadata.labels.helm\.sh/chart}')
if [ "$POD_CHART_LABEL" = absent ]; then [ -z "$pl" ] && ok "pod template carries no helm.sh/chart (14.4.0 behaviour)" || bad "pod still carries helm.sh/chart='$pl' (rendered by a pre-14.4.0 chart?)"
else [ "$pl" = "$POD_CHART_LABEL" ] && ok "pod chart label $pl" || bad "pod chart label '$pl' want $POD_CHART_LABEL"; fi
pv=$(kubectl get pod -n $NS -l $SEL -o jsonpath='{.items[0].metadata.labels.app\.kubernetes\.io/version}')
[ "$pv" = "$EXPECT_APP" ] && ok "pod app.kubernetes.io/version=$pv" || bad "pod version label '$pv' want $EXPECT_APP"
ph=$(kubectl get pod -n $NS -l $SEL -o jsonpath='{.items[0].metadata.labels.pod-template-hash}')
if [ "$MIGRATIONS" = expect ]; then [ "$ph" != "$PREV_POD_HASH" ] && ok "pod-template-hash $ph != pre-change $PREV_POD_HASH (a new generation is serving)" || bad "pod-template-hash unchanged ($ph): still the OLD generation"; fi
names=$(kubectl get pod -n $NS -l $SEL -o jsonpath='{.items[*].spec.containers[*].name}')
[ "$names" = "grafana-sc-dashboard grafana-sc-datasources grafana" ] && ok "containers: $names" || bad "container set changed: '$names'"
ini=$(kubectl get pod -n $NS -l $SEL -o jsonpath='{.items[*].spec.initContainers[*].name}')
[ "$ini" = "init-chown-data download-dashboards" ] && ok "initContainers: $ini (no init-sc-plugins)" || bad "initContainer set '$ini'"
rdy=$(kubectl get pod -n $NS -l $SEL -o jsonpath='{.items[*].status.containerStatuses[*].ready}')
[ "$rdy" = "true true true" ] && ok "3/3 ready" || bad "readiness: '$rdy'"
rc=$(kubectl get pod -n $NS -l $SEL -o jsonpath='{.items[*].status.containerStatuses[*].restartCount}')
case "$rc" in "0 0 0") ok "restartCount 0 0 0";; *) bad "restartCount '$rc'";; esac

# V2 the load-bearing preinstall guard
g=$(kubectl get deploy grafana -n $NS -o jsonpath='{.spec.template.spec.containers[?(@.name=="grafana")].env[?(@.name=="GF_PLUGINS_PREINSTALL_DISABLED")].value}')
[ "$g" = "true" ] && ok "GF_PLUGINS_PREINSTALL_DISABLED=true" || bad "GF_PLUGINS_PREINSTALL_DISABLED='$g'"
kubectl get cm grafana -n $NS -o jsonpath='{.data.grafana\.ini}' | grep -q '^preinstall_auto_update = false' && ok "ini preinstall_auto_update=false" || bad "ini preinstall_auto_update missing"

# V3 migrations + plugin-installer errors (the log is non-empty on any boot)
L=$(kubectl logs -n $NS deploy/grafana -c grafana)
nz=$(printf '%s\n' "$L" | grep -c 'migrations completed.*performed=[1-9]')
z=$(printf '%s\n' "$L" | grep -c 'migrations completed.*performed=0')
tot=$(printf '%s\n' "$L" | grep -c 'migrations completed.*performed=')
errm=$(printf '%s\n' "$L" | grep -i -c -e 'level=error.*migrat' -e 'migrat.*level=error' -e 'migration failed')
if [ "$MIGRATIONS" = none ]; then
  { [ "$nz" = 0 ] && [ "$z" -ge 4 ]; } && ok "migrations: performed=0 x$z, nonzero x$nz" || bad "migrations: performed=0 x$z, nonzero x$nz (need 0 and >=4)"
else
  rm=$(printf '%s\n' "$L" | grep 'logger=resource-migrator' | grep -c 'migrations completed.*performed=\([2-9]\|[1-9][0-9]\)')
  echo "INFO  migrations on this boot: migrator lines=$tot performed=0 x$z performed>0 x$nz resource-migrator>=2 x$rm  (RECORD in the window report)"
  { [ "$tot" -ge 4 ] && [ "$nz" -ge 1 ] && [ "$errm" = 0 ]; } && ok "migrations: all $tot migrators completed, $nz performed work, no migration errors" || bad "migrations: lines=$tot nonzero=$nz errors=$errm (need lines>=4, nonzero>=1, errors=0)"
fi
printf '%s\n' "$L" | grep -q 'Unified storage migrations completed successfully' && ok "unified storage migrations completed" || bad "no 'Unified storage migrations completed successfully' line"
ro=$(printf '%s\n' "$L" | grep -i -c -e 'read-only file system' -e 'unlinkat')
[ "$ro" = 0 ] && ok "no read-only-fs plugin-installer errors" || bad "plugin-installer read-only-fs errors x$ro"
sce=$(kubectl logs -n $NS deploy/grafana -c grafana-sc-dashboard | grep -i -c -e '"level": "ERROR"' -e traceback)
[ "$sce" = 0 ] && ok "dashboard sidecar log: 0 errors" || bad "dashboard sidecar log errors x$sce"

# V4 CONTENTS via API
U=$(kubectl get secret grafana-admin-secret -n $NS -o jsonpath='{.data.admin-user}' | base64 -d)
PW=$(kubectl get secret grafana-admin-secret -n $NS -o jsonpath='{.data.admin-password}' | base64 -d)
kubectl port-forward -n $NS svc/grafana 33001:80 >/dev/null 2>&1 &
PF=$!; sleep 5
A="http://127.0.0.1:33001"
hv=$(curl -s -u "$U:$PW" "$A/api/health" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("version"))' 2>/dev/null)
[ "$hv" = "$EXPECT_APP" ] && ok "/api/health version $hv" || bad "/api/health version '$hv' want $EXPECT_APP"
ids=$(curl -s -u "$U:$PW" "$A/api/plugins?embedded=0&type=datasource" | python3 -c 'import sys,json; print(",".join(sorted(x["id"] for x in json.load(sys.stdin))))' 2>/dev/null)
n=$(printf '%s' "$ids" | awk -F, '{print NF}')
miss=$(python3 -c 'import sys; a=set(sys.argv[1].split(",")); b=set(sys.argv[2].split(",")); print(",".join(sorted(a-b)))' "$BASE_IDS" "$ids")
if [ "$MIGRATIONS" = none ]; then okp=$([ "$ids" = "$BASE_IDS" ] && echo y); else okp=$([ -z "$miss" ] && [ "$ids" = "$PREFLIGHT_IDS" ] && echo y); fi
[ "$okp" = y ] && ok "datasource plugin ids ($n) = expected set (none of the baseline missing)" || bad "datasource plugin ids ($n) missing-vs-baseline='$miss' got='$ids' (the 2026-09-12 signature is 13 plugins)"
for uid in prometheus elasticsearch influxdb unpoller-influxdb pellets TeslaMate; do
  s=$(curl -s -u "$U:$PW" -X POST "$A/api/datasources/uid/$uid/health" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("status"))' 2>/dev/null)
  [ "$s" = "OK" ] && ok "datasource $uid health OK" || bad "datasource $uid health='$s'"
done
am=$(curl -s -u "$U:$PW" "$A/api/datasources/proxy/uid/alertmanager/api/v2/status" | python3 -c 'import sys,json; print("cluster" in json.load(sys.stdin))' 2>/dev/null)
[ "$am" = "True" ] && ok "alertmanager proxy returns status (no backend health exists)" || bad "alertmanager proxy: '$am'"
q=$(curl -s -u "$U:$PW" -H 'Content-Type: application/json' -X POST "$A/api/ds/query" -d '{"from":"now-5m","to":"now","queries":[{"refId":"A","datasource":{"uid":"prometheus","type":"prometheus"},"expr":"count(kube_pod_info)","instant":true,"range":false}]}' | python3 -c '
import sys,json
d=json.load(sys.stdin); f=d["results"]["A"]["frames"][0]["data"]["values"]; print(int(f[1][-1]))' 2>/dev/null)
case "$q" in ''|*[!0-9]*) bad "ds/query count(kube_pod_info)='$q'";; *) [ "$q" -gt 50 ] && ok "ds/query count(kube_pod_info)=$q" || bad "ds/query suspiciously low: $q";; esac
for pair in "TeslaMate:select count(*) as n from drives" "pellets:select 1 as n"; do
  uid=${pair%%:*}; sql=${pair#*:}
  r=$(curl -s -u "$U:$PW" -H 'Content-Type: application/json' -X POST "$A/api/ds/query" -d "{\"from\":\"now-5m\",\"to\":\"now\",\"queries\":[{\"refId\":\"A\",\"datasource\":{\"uid\":\"$uid\"},\"rawSql\":\"$sql\",\"format\":\"table\"}]}" | python3 -c '
import sys,json
d=json.load(sys.stdin); print(int(d["results"]["A"]["frames"][0]["data"]["values"][0][0]))' 2>/dev/null)
  case "$r" in ''|*[!0-9]*) bad "postgres ds/query $uid ('$sql')='$r' (Plugin not registered / auth / reachability)";; *) [ "$r" -ge 1 ] && ok "postgres ds/query $uid returned $r" || bad "postgres ds/query $uid returned $r";; esac
done
S=$(curl -s -u "$U:$PW" "$A/api/search?type=dash-db&limit=1000")
nd=$(printf '%s' "$S" | python3 -c 'import sys,json; print(len(json.load(sys.stdin)))' 2>/dev/null)
[ "$nd" = "$BASE_DASH" ] && ok "dashboards = $nd" || bad "dashboards = '$nd' want $BASE_DASH"
fo=$(printf '%s' "$S" | python3 -c '
import sys,json,collections
c=collections.Counter(x.get("folderTitle","General") for x in json.load(sys.stdin)); print(",".join(f"{k}={c[k]}" for k in sorted(c)))' 2>/dev/null)
[ "$fo" = "$BASE_FOLDERS" ] && ok "dashboards per folder = $fo" || bad "folder counts '$fo' want '$BASE_FOLDERS' (TeslaMate=23 are fetched from unpinned upstream master at every start)"
tmuids=$(printf '%s' "$S" | python3 -c 'import sys,json; print(" ".join(x["uid"] for x in json.load(sys.stdin) if x.get("folderTitle")=="TeslaMate"))' 2>/dev/null)
empty=0; for u in $tmuids; do pc=$(curl -s -u "$U:$PW" "$A/api/dashboards/uid/$u" | python3 -c 'import sys,json; print(len(json.load(sys.stdin)["dashboard"].get("panels",[])))' 2>/dev/null); [ "${pc:-0}" -ge 1 ] 2>/dev/null || empty=$((empty+1)); done
[ -n "$tmuids" ] && [ "$empty" = 0 ] && ok "all $(echo $tmuids | wc -w | tr -d ' ') TeslaMate dashboards have >=1 panel" || bad "TeslaMate dashboards with 0 panels (or none listed): $empty"
cms=$(kubectl get cm -A -l grafana_dashboard=1 --no-headers | wc -l | tr -d ' ')
[ "$cms" = "$BASE_CMS" ] && ok "sidecar dashboard ConfigMaps = $cms" || bad "sidecar dashboard ConfigMaps = $cms want $BASE_CMS"
ds=$(curl -s -u "$U:$PW" "$A/api/datasources" | python3 -c 'import sys,json; print(",".join(sorted(x["uid"] for x in json.load(sys.stdin))))' 2>/dev/null)
[ "$ds" = "TeslaMate,alertmanager,elasticsearch,influxdb,pellets,prometheus,unpoller-influxdb" ] && ok "7 provisioned datasources: $ds" || bad "datasource set: '$ds'"
ob=$(curl -s -u "$U:$PW" "$A/api/frontend/settings" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("oauth",{}).get("generic_oauth",{}).get("name"))' 2>/dev/null)
[ "$ob" = "Authentik" ] && ok "Authentik SSO button present" || bad "Authentik SSO oauth block: '$ob'"
rl=$(curl -s -o /dev/null -w '%{http_code} %{redirect_url}' "$A/login/generic_oauth" | sed -E 's#^([0-9]+) https?://[^/]+(/application/o/authorize/).*#\1 HOST\2#')
[ "$rl" = "302 HOST/application/o/authorize/" ] && ok "SSO start redirects to the Authentik authorize endpoint" || bad "SSO start redirect: '$rl' (a missing provider also 302s, to /login - only the authorize path counts)"
sa=$(curl -s -u "$U:$PW" "$A/api/serviceaccounts/search?perpage=100" | python3 -c 'import sys,json; print(",".join(s["name"] for s in json.load(sys.stdin)["serviceAccounts"]))' 2>/dev/null)
[ "$sa" = "n8n" ] && ok "service accounts: $sa (the migrated sqlite kept its rows)" || bad "service accounts '$sa' want n8n (DB reset or data loss)"
kill $PF 2>/dev/null; wait $PF 2>/dev/null

# V5 Prometheus sees the new pod (caller waits >=90 s after pod Ready)
P=/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query
pq() { kubectl get --raw "$P?query=$(python3 -c 'import sys,urllib.parse;print(urllib.parse.quote(sys.argv[1]))' "$1")" | python3 -c 'import sys,json; r=json.load(sys.stdin)["data"]["result"]; print(r[0]["value"][1] if r else "EMPTY")'; }
u=$(pq 'up{job="grafana"}'); [ "$u" = "1" ] && ok "up{job=grafana}=1" || bad "up{job=grafana}='$u'"
bv=$(kubectl get --raw "$P?query=grafana_build_info" | python3 -c 'import sys,json; r=json.load(sys.stdin)["data"]["result"]; print(",".join(sorted(x["metric"]["version"] for x in r)))')
[ "$bv" = "$EXPECT_APP" ] && ok "grafana_build_info version=$bv (single series)" || bad "grafana_build_info versions='$bv' want exactly $EXPECT_APP"
pm=$(pq 'count(grafana_plugin_build_info{plugin_type="datasource"})')
case "$pm" in ''|EMPTY|*[!0-9]*) bad "datasource plugins in metrics='$pm'";; *) if [ "$MIGRATIONS" = none ]; then [ "$pm" = "$BASE_PROMDS" ] && ok "datasource plugins in metrics=$pm" || bad "datasource plugins in metrics=$pm want $BASE_PROMDS"; else [ "$pm" -ge "$BASE_PROMDS" ] && ok "datasource plugins in metrics=$pm (>= $BASE_PROMDS)" || bad "datasource plugins in metrics=$pm below baseline $BASE_PROMDS"; fi;; esac
sd=$(pq 'grafana_stat_totals_dashboard'); [ "$sd" = "$BASE_DASH" ] && ok "grafana_stat_totals_dashboard=$sd" || bad "grafana_stat_totals_dashboard='$sd' want $BASE_DASH"
echo; [ $fail = 0 ] && echo "ALL GATES PASS" || echo "GATE FAILURE - see FAIL lines (rollback per section 5)"
exit $fail
EOF
EXPECT_CHART=14.4.0 EXPECT_APP=13.3.0 EXPECT_SIDECAR=2.14.3 POD_CHART_LABEL=absent MIGRATIONS=expect bash "$S/grafana-verify.sh"
# (needs the 2.7 exports BASE_IDS BASE_DASH BASE_FOLDERS BASE_CMS BASE_PROMDS PREV_POD_HASH and the 2.8 export PREFLIGHT_IDS in the environment)
```

**Rehearsed 2026-11-09 against the LIVE pre-change state (read-only).** `EXPECT_CHART=14.0.1 EXPECT_APP=13.2.4 EXPECT_SIDECAR=2.14.1 POD_CHART_LABEL=grafana-14.0.1 MIGRATIONS=none`
printed 40 PASS lines and `ALL GATES PASS`. With the post-change expectations against the still-old pod it printed exactly the identity FAILs
(`HR chart/Ready: got '14.0.1 True' want '14.4.0 True'`, deployment label, image, sidecar images, `pod still carries helm.sh/chart`, pod version label,
`pod-template-hash unchanged`, `/api/health version`, `grafana_build_info`) and `FAIL migrations: lines=4 nonzero=0 errors=0`, so the gates that prove
"this is the new pod running the new app and the schema migrated" can fail. A second run with a corrupted baseline (a fake plugin id, 72 dashboards, TeslaMate=11,
36 ConfigMaps) printed FAIL for the plugin-id set, dashboards, folder map, ConfigMap count and `grafana_stat_totals_dashboard`. SSO control: `/login/nosuchprovider`
also answers 302 but to `/login`, which the redirect gate rejects (only `HOST/application/o/authorize/` passes).

Negative control for the absence gate (the identical command can print non-zero; same pipeline over a clean line prints 0):
```bash
printf 'logger=plugin.backgroundinstaller level=error msg="unlinkat /usr/share/grafana/data/plugins-bundled/postgres: read-only file system"\n' | grep -i -c -e 'read-only file system' -e 'unlinkat'   # prints 1
printf 'logger=settings level=info msg="ok"\n' | grep -i -c -e 'read-only file system' -e 'unlinkat'                                                  # prints 0
```

Known pre-existing noise the gates deliberately do NOT count (measured on the live pod 2026-11-09): `level=error msg="Unexpected element in Dashboard JSON"`
(x2, a TeslaMate dashboard) and `Request Completed ... /api/datasources/uid/alertmanager/health status=500` (Alertmanager has no backend health), and 2 pre-existing
error lines in the `grafana-sc-datasources` sidecar log. Only the migration/plugin-installer patterns and the dashboard sidecar (0 errors baseline) are gated.

What each gate guards against, and what its failure prints:

| Gate | Failure it guards against | Failure output |
|---|---|---|
| HR `chartVersion Ready` = `14.4.0 True`; Deployment label `helm.sh/chart` = `grafana-14.4.0` | Flux still on 14.0.1 / remediation rolled back | `FAIL HR chart/Ready: got '14.0.1 True' ...` |
| image `13.3.0-distroless`; both sidecars `2.14.3`; exactly 1 pod | tag drift / wrong generation / two pods | `FAIL image is '...13.2.4-distroless'`, `FAIL sidecar images ...` |
| pod label `helm.sh/chart` ABSENT; pod `app.kubernetes.io/version` = 13.3.0; pod-template-hash != pre-change | measuring the OLD pod, or a chart older than 14.4.0 rendering the pod | `FAIL pod still carries helm.sh/chart='grafana-14.0.1'`, `FAIL pod-template-hash unchanged` |
| `/api/health` version == `13.3.0` and `grafana_build_info` == exactly `13.3.0` | old binary still serving; stale old-pod series | `FAIL /api/health version '13.2.4' want 13.3.0` |
| containers == 3 named, initContainers == `init-chown-data download-dashboards`, 3/3 ready, restartCount `0 0 0` | an opt-in sidecar appearing; crash-looping on the migrated DB | `FAIL container set changed` / `FAIL restartCount '0 1 0'` |
| `GF_PLUGINS_PREINSTALL_DISABLED=true` env + ini `preinstall_auto_update = false` | the guard lost - recreates the 2026-09-12 outage on the NEXT restart | `FAIL GF_PLUGINS_PREINSTALL_DISABLED=''` |
| log (`expect` mode): >= 4 migrator lines, at least ONE `performed>0`, no migration errors, plus `Unified storage migrations completed successfully` | schema migration failing half-way / not running / the old binary | `FAIL migrations: lines=4 nonzero=0 errors=0 ...` |
| log: no `read-only file system` / `unlinkat` (case-insensitive); dashboard sidecar log 0 errors | the background installer killing bundled backends; sidecar failing to load ConfigMaps | `FAIL plugin-installer read-only-fs errors x3` |
| API `/api/plugins?type=datasource` IDS superset of baseline AND == PREFLIGHT_IDS (13.3.0 image measured off-PVC) | stripped/killed bundled backends; **13 plugins is the measured 2026-09-12 signature** | `FAIL datasource plugin ids (13) missing-vs-baseline='...'` |
| 6 datasource `/health` == `OK`; Alertmanager proxy `cluster` key; `/api/ds/query` numeric for Prometheus (`from`/`to` mandatory, else a healthy Grafana returns empty), TeslaMate (`select count(*) from drives` >= 1) and pellets (`select 1`) | dead plugin ("Plugin not registered"), bad ES secret (401 after restart), unreachable DB, wrong postgres plugin version | `FAIL datasource TeslaMate health='ERROR'` / `FAIL postgres ds/query pellets ...` |
| dashboards == baseline (84); per-folder map exact (TeslaMate=23); every TeslaMate dashboard >= 1 panel; sidecar ConfigMaps == 37 | `download-dashboards` writing 0-byte files on a GitHub fetch failure (or TeslaMate master restructuring); sidecar provisioning broken | `FAIL dashboards = '55' want 84`, `FAIL folder counts ...` |
| 7 datasource UIDs exact set | provisioning regression | `FAIL datasource set: ...` |
| `/api/frontend/settings` oauth name `Authentik`; `/login/generic_oauth` -> 302 to `.../application/o/authorize/` | SSO wiring (F-5a894d0e) lost; 13.3.0 changed OAuth handling | `FAIL Authentik SSO oauth block: 'None'` / `FAIL SSO start redirect: '302 http://127.0.0.1:33001/login'` |
| service accounts == `n8n` | DB reset / migration lost rows | `FAIL service accounts '' want n8n` |
| Prometheus `up{job="grafana"}` == 1, datasource-plugin series >= baseline, `grafana_stat_totals_dashboard` == baseline | ServiceMonitor lost the target; provisioning count drift | `FAIL up{job=grafana}='EMPTY'` |

CONTENTS ASSERTION: the bundled datasource backends, the 7 provisioned datasources (including real SQL against the TeslaMate and pellets Postgres), the 84 dashboards
(23 TeslaMate, each non-empty), the sidecar ConfigMap dashboards, the Authentik SSO start and the sqlite-held service account survived the application upgrade and restart,
measured against the 2.7 baselines and the off-PVC 13.3.0 pre-flight.

CONTROL: metric up - `up{job="grafana"}` must be 1 on the new pod (live 2026-11-09: 1)
CONTROL: metric grafana_build_info - `version` label must be exactly `13.3.0` after the roll (live now: `13.2.4`; the gate can fail today)
CONTROL: metric grafana_plugin_build_info - `count(...{plugin_type="datasource"})` must be >= the 2.7 baseline (live 2026-11-09: 13)
CONTROL: metric grafana_stat_totals_dashboard - must equal the 2.7 dashboard baseline (live: 84)

No alertname control: the repo carries no Grafana-specific PrometheusRule, and asserting a generic alert would be a gate that cannot fail on the property under change.

**PASS** = script prints `ALL GATES PASS` (exit 0) AND the `INFO migrations on this boot:` line is recorded in the window report (expected: migrator `performed>0`,
resource-migrator `performed>=2`; any deviation is worth a line even when the gates pass).

**Soak:** re-run the script once more >= 2 h after the roll (a quiet pod can pass at t+5 min and fail when the first scheduled plugin / unified-storage cleanup
runs; 13.3.0 enables automatic deleted-resource cleanup by default). Only then delete snapshot `grafana-pre-14-4-0`.

**Owner of the soak re-run and the snapshot deletion** (an unowned soak is a skipped soak): the window agent, at the end of its Step 4 for this plan, files a
home-operation reminder due `T+2h`. The `source` is `plan-soak`, deliberately NOT `maintenance` (the window close-out runs `home-operation reconcile --source maintenance
--open '<plan ids>'` and would close a `maintenance` reminder whose key is not in that list):
```
kubectl -n ai exec deploy/openclaw -c app -- /home/node/.openclaw/bin/home-operation ingest --json '{"key":"grafana-14-4-0-soak","kind":"window_warning","source":"plan-soak","severity":"warning","action":"ack","component":"grafana","plan_path":"runbooks/maintenance/plans/grafana-chart-14.4.0.md","title":"grafana 14.4.0: re-run the section-4 soak at T+2h, then delete snapshot grafana-pre-14-4-0","detail":"Re-run the section-4 script in expect mode (2h after the roll), then delete the Longhorn snapshot within 7 days."}'
# after the soak re-run passes and the snapshot is deleted:
kubectl -n ai exec deploy/openclaw -c app -- /home/node/.openclaw/bin/home-operation resolve --issue grafana-14-4-0-soak --by executed --note "<sha>"
```
If no agent session is available the operator owns it, prompted by that reminder. The snapshot must not outlive the reminder by more than 7 days (it pins Longhorn space).

## 5) Rollback

**Rollback class is backup-restore, not git-revert.** The chart pin is trivially revertible; the DATABASE may not be. Grafana does not support downgrading across a schema
migration, and whether 13.2.4 boots on a 13.3.0-migrated `grafana.db` is unknown (not measurable from here). Ladder; stop at the first rung that passes section 4 with
`EXPECT_CHART=14.0.1 EXPECT_APP=13.2.4 EXPECT_SIDECAR=2.14.1 POD_CHART_LABEL=grafana-14.0.1 MIGRATIONS=none` (a 14.0.1 pod DOES carry the pod `helm.sh/chart` label again):

**Rung 1 - revert the pin (always first, cheap; restores the chart, not necessarily the data).**
```bash
git revert --no-edit <bump-commit-sha>
git log -1 --format=%s        # confirm the revert subject is yours before pushing
git push
# webhook slow after 10 min: flux reconcile helmrelease grafana -n monitoring --with-source
kubectl rollout status deployment/grafana -n monitoring --timeout=300s
```
Then run the section 4 script with the 14.0.1 values above (the revert is a SECOND restart: the preinstall guard and datasource gates apply to it exactly as to the forward roll;
the Deployment template equals the pre-change one, so the old ReplicaSet `grafana-c5f66c545` is reused - do NOT pass `PREV_POD_HASH`/`MIGRATIONS=expect`). A migration DID run
forward, so the database is "newer than the app". If the old pod boots and every gate passes, 13.2.4 tolerated the migrated schema: record it, but do not call the rollback done
silently - re-plan the upgrade rather than leaving it half-way. If it does not boot (crash-loop, schema error in `kubectl logs --previous`), continue to Rung 2.
**Unattended nightly:** Rungs 2 and 3 need the Longhorn UI and operator judgement. In an unattended run the agent stops after Rung 1, leaves the pod as it is, and escalates through
the window's `blocked` / `reverted` notification - it must not improvise Rung 2/3.

**Rung 2 - 13.2.4 crash-loops on the migrated DB.** Restore the PRE-CHANGE data under the pinned old app. State is tiny (2 users, 1 service account, 0 alert rules) and everything
else is provisioned from git, so this is a controlled DB reset, not a data-recovery emergency:
1. Keep the pin reverted (Rung 1 pushed and reconciled). `kubectl scale deployment/grafana -n monitoring --replicas=0`; wait for the pod to terminate and the Longhorn volume
   to detach. Do NOT `flux suspend`: HelmRelease `driftDetection` is unset on `grafana` (0 of the HelmReleases set it, measured 2026-11-09), so Flux does not revert a manual
   replica count. (If `helm-drift-detection` has landed since, re-check: with drift detection on, suspend the HelmRelease first.)
2. Revert the volume to the pre-change snapshot in place: Longhorn UI (port-forward `svc/longhorn-frontend` in ns `storage`) -> Volume `grafana-config` -> attach in Maintenance mode
   -> Snapshots -> `grafana-pre-14-4-0` -> Revert -> detach. (Maintenance-mode attach is required for a snapshot revert; NOT rehearsed in planning.)
3. Bring it back explicitly - nothing else will (no spec change, no Helm upgrade, replicas stay 0): `kubectl scale deployment/grafana -n monitoring --replicas=1`, then
   `kubectl rollout status deployment/grafana -n monitoring --timeout=420s` and confirm 3/3 ready BEFORE re-running section 4 with the 14.0.1 values.

**Rung 3 - the snapshot is unusable (it lives on the same volume's replicas).** Restore the newest Completed Backup of `grafana-config` (2.5 proved one < 6 h old) by the
repo-correct path in `docs/sops/backup.md` "Restore from Backup" / "Bind Restored Volume to Application" (restore to a NEW volume name, then repoint the git-tracked PV/PVC; the
same-name alternative deletes the on-cluster replicas first and is the last resort; the PV `grafana-config` is reclaim `Retain`). Total-loss fallback: empty the PVC contents and let Grafana
re-initialise; consequences measured above (service account `n8n` and its token(s) must be re-issued and the n8n credential updated; 2 users re-created on next SSO login).

Trigger rollback on any `FAIL` that persists after one further 3-minute settle (scrape lag, init-container fetch, first-boot migration). Per `docs/sops/grafana-image-changes.md`
section 4 step 7 do not debug in place: monitoring is what you debug with.

## 6) Interference notes

- **Window.** Suggested **`nightly:2026-11-11`** with an operator GO recorded before the night (HUMAN-GATED; nightly default is operator-go-no-go). It is a free night on 2026-11-09:
  no open plan holds a nightly slot (`maintenance-plan.py --open` shows only sat/sun slots), and it is 3 days before `sat-attended:2026-11-14` (`open-webui-0.13.0`,
  `python-fleet-3.15.2-alpine`) and 4 before `sun-attended:2026-11-15` (`longhorn-1.13.0`), leaving a clean soak. Fallbacks: `nightly:2026-11-12`, then `nightly:2026-11-17`. Avoid the nights
  directly before `sun-attended:2026-11-22` (`talos-linux-1.14.5`, EXCLUSIVE node roll), and `sat-attended:2026-11-21` (`coredns-1.50.2`). The previous suggestion `nightly:2026-11-03` has passed.
- **PR #374 and the `*grafana*` deny rule (`max: patch`).** (a) Step 0 (`auto-update.py --apply`) merges only the SAFE subset; a chart minor is held by the rule, so #374 is never auto-merged
  and cannot race the hand-edit. (b) `coverage.py` matches a plan file BEFORE it consults deny rules: this plan (`target: 14.4.0`) covers the held 14.0.1 -> 14.4.0 item; if Renovate retargets again
  (a 14.5.0) the plan reads DRIFTED and must be refreshed, which pre-check 2.2 also catches at run time. (c) Once 14.4.0 is live, a later chart PATCH is inside `max: patch` and WILL auto-apply at Step 0;
  acceptable only while app patches on 13.3.x keep the schema, so I recommend NOT narrowing or removing the rule: this retarget is the second live example of the hazard it names. (d) With 14.4.0 a
  values-identical chart patch no longer restarts the pod at all.
- **kube-prometheus-stack (plan `kube-prometheus-stack-92.22.0` now exists as a draft and IS a `conflicts_with` entry; the older #428-class note follows).** Held by a time-boxed deny rule (revisit by 2026-11-30) but may be applied deliberately. It matters
  twice: Prometheus rolling makes the Prometheus gates unattributable, and kps ships `grafana_dashboard` ConfigMaps (the 37 gated) the sidecar loads, so it can move the dashboard count. Mitigation: 2.6 (timing)
  and, as the real control, baselines taken AFTER Step 0 (2.7). Do not schedule this plan in a window that also carries a kube-prometheus-stack bump.
- **Shared surfaces read, not restarted:** Prometheus/Alertmanager (monitoring), Elasticsearch (the pod re-reads `secret/elasticsearch-es-elastic-user` on restart - related deferred finding
  F-03d0843d; if the ES datasource health fails with 401 after the roll, that rotation is the cause, not Grafana), InfluxDB, the pellets Postgres (`postgres-digest-refresh-2026-11` declared), the TeslaMate
  Postgres, Authentik (SSO is only probed to the authorize redirect; a full login needs a browser and a person - not gated), GitHub raw (dashboard fetch; an outage shows as fewer dashboards).
- **No teslamate plan is open** (`teslamate-4.4.0` executed and retired 2026-11-06), so the old "hard conflict" no longer applies; the residual coupling is that every Grafana start re-fetches the TeslaMate
  dashboards from unpinned `master`, so a dashboard JSON that targets a newer TeslaMate schema than the deployed one can appear at ANY restart, not just this one.
- **`talos-power-tuning-ab`** (`exclusive: true`, touches monitoring, `window: null`) is not scheduled, so it does not constrain the suggested night; if scheduled, exclusivity keeps this plan out of that slot.
- **n8n** holds the service account `n8n` (it calls Grafana's API); `n8n-fleet-2.46.6` mentions grafana only in prose and is a different night, so it is not a declared conflict, but a Grafana
  restart briefly fails n8n's calls: expected, not a regression.
- **Old plans.** `grafana-14.1.0` (superseded by this plan) and `grafana-chart-13.2.3` (superseded 2026-09-14) are untouched except for the supersede marker.
- **Could this be AUTO-class? No.** `capability_change: true` and `rollback_class: backup-restore` derive HUMAN-GATED; a future 13.3.x PATCH chart (app patch, git-revert class, `capability_change: false`) would be eligible again.
- **No node reboot.** Single replica, `Recreate`, RWO PVC already handled; no change to that config.
