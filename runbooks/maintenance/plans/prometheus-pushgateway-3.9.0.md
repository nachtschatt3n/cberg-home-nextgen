---
plan_id: prometheus-pushgateway-3.9.0
component: prometheus-pushgateway
pr: null                              # no Renovate PR; reached the PLAN lane via coverage.py
                                      # needs_plan ("G3 could not verify the release notes")
kind: chart
current: "3.8.0"
target: "3.9.0"
update_type: minor
risk: low                             # MEASURED 2026-09-25: the rendered-manifest diff with
                                      # our live values is ONLY the helm.sh/chart label (5
                                      # lines, §1.2). appVersion unchanged (v1.11.3 -> v1.11.3),
                                      # image unchanged. The one real cost is a pod restart
                                      # that wipes in-memory pushed state (§1.3) — handled by
                                      # timing + one re-push, not by risk tier.
est_duration_min: 35                  # pre-checks 5, commit+reconcile+Recreate ~5, then wait
                                      # for the hourly :17/:23 probes to re-push (<=20 min when
                                      # started at hh:00-hh:08, §3.0), gate 2.
needs_reboot: false
touches:
  namespaces: [monitoring]
  resources:
    - helmrelease/prometheus-pushgateway
    - deployment/prometheus-pushgateway
    - servicemonitor/prometheus-pushgateway
  shared: [monitoring]                # pushgateway is the shared push target for four
                                      # pushers in three other namespaces (kube-system
                                      # authentik-db-probe, backup icloud-backup-freshness,
                                      # home-automation pellet-price-monitor, and the Mac-side
                                      # sweep's maintenance-window-liveness). A restart blanks
                                      # every alert that reads those series (§1.3).
depends_on: []
conflicts_with:
  - kube-prometheus-stack-91.4.1      # §4 gate reads Prometheus; that bump restarts it. Its §4 also diffs the firing set vs its baseline, which this restart perturbs: run strictly AFTER its §4 is recorded.
  - icloud-backup-freshness-3.24.2    # its §2/§4 baseline reads the icloud group FROM THIS
                                      # pushgateway; a same-night restart wipes that baseline
                                      # and its gate would fail for a reason not its own.
                                      # (It does not list us back — reciprocal ref owed.)
  - talos-1.14.1                      # node reboots restart pushgateway too; two wipes in one
                                      # night make §4 unable to attribute a missing group.
  - authentik-pg17-decommission       # its verification reads
                                      # authentik_audit_newest_event_timestamp_seconds, a
                                      # PUSHED series this plan blanks for up to ~20 min.
exclusive: false
security_ref: null                    # image is unchanged by this bump; the image's own
                                      # finding lives in the DB and is not driven by this plan
capability_change: false
rollback_class: git-revert
finding_refs: [F-684a70f6]            # version finding "prometheus-pushgateway: chart 3.8.0 -> 3.9.0"
status: vetted   # 2026-09-26 plan-reviewer ready-for-go (0 blocking); timing exception, file-carried T0/POD_IP/OLD_IP, alert counts corrected
window: null
premises:
  - id: hr-still-on-3.8.0
    why: "Baseline and rollback target. If the HR already moved, this plan is stale."
    run: kubectl get helmrelease -n monitoring prometheus-pushgateway -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: "3.8.0"
  - id: image-v1.11.3
    why: "The risk call rests on 3.9.0 keeping appVersion v1.11.3. A different live image means a different delta."
    run: kubectl get deploy -n monitoring prometheus-pushgateway -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: quay.io/prometheus/pushgateway:v1.11.3
  - id: route-values-unset
    why: "The ONLY template change in 3.9.0 is templates/httproute.yaml. With no route values it renders nothing; if someone enabled a route, the rule name and HTTPRoute name semantics changed and this plan must be re-derived."
    run: kubectl get helmrelease -n monitoring prometheus-pushgateway -o json | jq -r '.spec.values.route'
    expect_exact: "null"
  - id: no-persistence-args
    why: "The restart-loss analysis (§1.3) assumes in-memory only. A --persistence.file arg would change what a restart loses."
    run: kubectl get deploy -n monitoring prometheus-pushgateway -o json | jq -r '.spec.template.spec.containers[0].args'
    expect_exact: "null"
  - id: pod-template-carries-chart-label
    why: "Proves the bump DOES roll the pod (the chart label is in the pod template), i.e. the state loss in §1.3 is real and §3.4 is required."
    run: kubectl get deploy -n monitoring prometheus-pushgateway -o jsonpath='{.spec.template.metadata.labels.helm\.sh/chart}'
    expect_exact: prometheus-pushgateway-3.8.0
  - id: strategy-recreate
    why: "Single replica; Recreate means a short scrape gap and one pod IP change, which §4 keys on."
    run: kubectl get deploy -n monitoring prometheus-pushgateway -o jsonpath='{.spec.strategy.type}'
    expect_exact: Recreate
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/monitoring.md           # "Push-based Metrics (Pushgateway)"
generated: "2026-09-25"
---

# prometheus-pushgateway chart 3.8.0 -> 3.9.0

## 1. Summary & why held

### 1.1 Why held
`coverage.py` routed it here with "G3 could not verify the release notes — an
unverified bump needs an assessed window". No Renovate PR exists. The
prometheus-community chart repo has no per-chart CHANGELOG, so G3 had nothing
to read. The assessment below replaces the release notes with a direct diff of
both published chart tarballs.

### 1.2 What 3.9.0 actually changes (measured 2026-09-25)
Source: `https://github.com/prometheus-community/helm-charts/releases/download/prometheus-pushgateway-3.9.0/prometheus-pushgateway-3.9.0.tgz`
(index `created: 2026-09-22T19:14:20Z`, `appVersion: v1.11.3`, same as 3.8.0).
`diff -ru` of the two unpacked charts shows three changes:

- `templates/httproute.yaml`: HTTPRoute name becomes `<fullname>-<routeName>` for
  routes other than `main`. Each rule gets a `name:`, and there is a new optional
  `sessionPersistence`.
- `values.yaml`: new `route.main.name: ""` and `route.main.sessionPersistence: {}`
  (route stays `enabled: false` by default).
- new `unittests/` directory, which is not rendered.

`helm template` of BOTH versions with our exact `spec.values` differs in the
`helm.sh/chart` label and nothing else (5 lines: Service, ServiceAccount,
Deployment metadata, **Deployment pod template**, ServiceMonitor). We set no
`route:` values, so the only functional change renders nothing here. The hold
is a false positive on content.

### 1.3 The real cost: one restart wipes pushed state
The pod-template label change rolls the pod (Recreate). Pushgateway runs
in-memory with no `--persistence.file` (premise `no-persistence-args`). A
restart drops every pushed group. Live groups on 2026-09-25, with who re-pushes
each one and what happens meanwhile:

| Group (job) | Pusher / cadence | Rules that go blank while it is missing | Effect of the gap |
|---|---|---|---|
| `authentik-db-probe` | CronJob kube-system, hourly `:17` | AuthentikAuditLogStale / AuthentikAuditFreshnessProbeStale / AuthentikPostgresConnectionsHigh go inert; `AuthentikAuditFreshnessProbeMissing` (absent, `for: 3h`) | Re-pushed within ≤60 min, normally ≤17 min with §3.0 timing. No false page. |
| `icloud-backup-freshness` | CronJob backup, hourly `:23` | `ICloudBackupPhotosStale{,Critical}` (**FIRING**: 3 series on 2026-09-26) RESOLVE. `ICloudBackupFreshnessMetricMissing*` (absent, `for: 3h`) | Alertmanager sends a **false "resolved"** for each firing series. They re-fire ≥30 min (`for: 30m`) after the next push. Expected noise, so tell the operator. |
| `maintenance-window-liveness` | **Mac sweep only, ~48h** | `MaintenanceWindowMissed` + `MaintenanceWindowsRepeatedlyMissed` (**currently FIRING**) RESOLVE. `MaintenanceWindowLivenessMetricsAbsent` (absent, `for: 6h`) **pages** if nothing re-pushes | **Would stay blank until the next sweep.** §3.4 re-pushes it by hand. That is the one non-optional step. |
| `pellet-price-monitor` | CronJob home-automation, 08:00 + 20:00 local | `PalletPriceMonitorRunStale` goes inert. `PalletCriticalSourceStale` uses `absent_over_time(...[30h])`, and TSDB history still covers the gap | Masked (not falsely paged) until the next run, ≤12h. Grafana panels show a gap. Accept it, because the run cannot be reproduced without triggering the Job. |

Every rule above keys on `job=` from the pushed group. That works because the
ServiceMonitor scrapes with `honor_labels` (live: `count by (job)
(push_time_seconds)` returns the four pusher jobs, not `prometheus-pushgateway`).

## 2. Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen
.venv/bin/python3 runbooks/plan-premises.py prometheus-pushgateway-3.9.0      # all 6 PASS, else STOP

flux get helmreleases -n monitoring prometheus-pushgateway                    # Ready True, 3.8.0
kubectl get pod -n monitoring -l app.kubernetes.io/name=prometheus-pushgateway -o wide   # 1/1 Running
kubectl get pod -n monitoring -l app.kubernetes.io/name=prometheus-pushgateway -o jsonpath='{.items[0].status.podIP}' > /tmp/pgw-OLD_IP; cat /tmp/pgw-OLD_IP

# 2.1 Baseline the pushgateway groups (what a restart will wipe):
kubectl port-forward -n monitoring svc/prometheus-pushgateway 19091:9091 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s http://127.0.0.1:19091/api/v1/metrics | python3 -c "
import sys,json
print(sorted(g['labels']['job'] for g in json.load(sys.stdin)['data']))"
# expect: ['authentik-db-probe', 'icloud-backup-freshness', 'maintenance-window-liveness', 'pellet-price-monitor']
# A 5th job means a pusher this plan did not assess: STOP and add it to §1.3.
kill $PF 2>/dev/null

# 2.2 GATE for §3.4: the liveness payload must be buildable WITH the ledger.
#     A verified=0 payload re-pushed in §3.4 would fire MaintenanceWindowLivenessUnverified.
source runbooks/lib/sweep-pg-dsn.sh && sweep_pg_dsn_up
.venv/bin/python3 runbooks/maintenance-plan.py --liveness-metrics > /tmp/mwl.prom
grep -c '^window_runs_liveness_verified 1$' /tmp/mwl.prom     # must print 1, else STOP (do not bump)
sweep_pg_dsn_down
```

## 3. Steps

**3.0 Timing.** Do the commit (3.2) between **hh:00 and hh:08**. The two hourly
probes (`:17`, `:23`) then re-populate the gateway within ~20 min instead of
~75, which shortens both the false-resolved window and §4's wait.
**Exception around 08:00/20:00 local:** the pellet CronJob pushes then, so a
restart at hh:00-hh:08 of those hours blanks it for 12h. Commit at
07:40-07:52 (or 19:40-19:52) instead, so the new pod is serving before the
pellet push. §4 must PASS before any other same-day window whose plans read
pushed series starts (e.g. sat-attended 09:00). Record T0:

```bash
T0=$(date +%s); echo "$T0" > /tmp/pgw-T0; echo "T0=$T0"   # fresh shell per call: re-read with $(cat /tmp/pgw-T0)
```

**3.1 Edit.** Dry-tested with BSD sed on a scratch copy 2026-09-25. It matched exactly one line:

```bash
cd /Users/mu/code/cberg-home-nextgen
sed -i '' 's/^\([[:space:]]*version:[[:space:]]*\)3\.8\.0$/\13.9.0/' \
  kubernetes/apps/monitoring/prometheus-pushgateway/app/helmrelease.yaml
git diff kubernetes/apps/monitoring/prometheus-pushgateway/app/helmrelease.yaml
# expect exactly:  -      version: 3.8.0   /   +      version: 3.9.0
```

**3.2 Commit + push** (shared worktree, so use `--only`, then check the subject):

```bash
git commit --only kubernetes/apps/monitoring/prometheus-pushgateway/app/helmrelease.yaml \
  -m "chore(prometheus-pushgateway): chart 3.8.0 -> 3.9.0 (plan prometheus-pushgateway-3.9.0)"
git log -1 --format=%s        # must be the subject above; amend before push if not
git show --stat HEAD          # exactly one file
git push
```

**3.3 Wait for the rollout.** Flux uses the webhook, so there is no manual reconcile:

```bash
kubectl get helmrelease -n monitoring prometheus-pushgateway -o jsonpath='{.status.history[0].chartVersion}{"\n"}'   # 3.9.0
kubectl get deploy -n monitoring prometheus-pushgateway -o jsonpath='{.spec.template.metadata.labels.helm\.sh/chart}{"\n"}'  # prometheus-pushgateway-3.9.0
kubectl rollout status -n monitoring deploy/prometheus-pushgateway --timeout=180s
POD_IP=$(kubectl get pod -n monitoring -l app.kubernetes.io/name=prometheus-pushgateway -o jsonpath='{.items[0].status.podIP}'); echo "$POD_IP" > /tmp/pgw-POD_IP; echo "POD_IP=$POD_IP"
[ "$(cat /tmp/pgw-POD_IP)" != "$(cat /tmp/pgw-OLD_IP)" ] && echo NEW-POD || echo "SAME IP: STOP"   # proves the new pod, not the old generation
```

**3.4 Re-push maintenance-window liveness (required).** This is the same
payload, job and method that `sweep-run.py push_liveness_metrics` uses. It
restores the only group whose pusher is days away. Regenerate the payload
here rather than reusing the pre-check file, so the numbers are current:

```bash
source runbooks/lib/sweep-pg-dsn.sh && sweep_pg_dsn_up
.venv/bin/python3 runbooks/maintenance-plan.py --liveness-metrics > /tmp/mwl.prom
grep -c '^window_runs_liveness_verified 1$' /tmp/mwl.prom     # 1, else do NOT push; see §5 note
kubectl port-forward -n monitoring svc/prometheus-pushgateway 19091:9091 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s http://127.0.0.1:19091/api/v1/metrics | python3 -c "import sys,json;print(len(json.load(sys.stdin)['data']),'groups')"
#   ^ CONTENTS ASSERTION (restart really wiped state): expect 0 groups (or only a
#     probe that already ran since T0). 4 groups here = old pod still serving, so STOP.
curl -sS -o /dev/null -w '%{http_code}\n' -X POST --data-binary @/tmp/mwl.prom \
  -H 'Content-Type: text/plain; version=0.0.4; charset=utf-8' \
  http://127.0.0.1:19091/metrics/job/maintenance-window-liveness                # 200
kill $PF 2>/dev/null
sweep_pg_dsn_down
```

**3.5 Wait** until at least hh:25 (both hourly probes have pushed), then run §4.

## 4. Verification

Floor: HR Ready on 3.9.0, pod 1/1 Running, pod template label
`prometheus-pushgateway-3.9.0`, image still `quay.io/prometheus/pushgateway:v1.11.3`.

CONTENTS ASSERTION: every group with a sub-hour or manual re-push is back in
Prometheus with a push_time AFTER T0, the scrape runs against the NEW pod, and
the payload values are real. Measured by the gate below, which reads Prometheus
(the reader every rule uses). Compared against T0 and the pre-check group list.

CONTROL: metric up — `up{job="prometheus-pushgateway"}`: exactly one series, value 1, instance on the new `$POD_IP`
CONTROL: metric push_time_seconds — `{job=...}` for authentik-db-probe, icloud-backup-freshness, maintenance-window-liveness each > T0
CONTROL: metric window_runs_liveness_verified — == 1 (payload re-pushed with the ledger, not the verified=0 fallback)
CONTROL: metric icloud_backup_newest_file_timestamp_seconds — count == 2 (both accounts)
CONTROL: metric authentik_audit_newest_event_timestamp_seconds — count == 1
CONTROL: alertname MaintenanceWindowLivenessMetricsAbsent — must NOT be pending/firing at gate time
CONTROL: alertname ICloudBackupFreshnessMetricMissing — must NOT be pending/firing at gate time

Write the gate to a scratch file, then run it with `bash` (it is bash, not zsh):

```bash
cat > /tmp/pgw-gate.sh <<'SH'
T0="$1"; POD_IP="$2"
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
python3 - "$T0" "$POD_IP" <<'EOF'
import sys, json, urllib.request, urllib.parse
T0, POD_IP = float(sys.argv[1]), sys.argv[2]
def q(expr):
    u = "http://127.0.0.1:19090/api/v1/query?" + urllib.parse.urlencode({"query": expr})
    r = json.load(urllib.request.urlopen(u, timeout=15))
    if r.get("status") != "success":
        sys.exit(f"FAIL query error for {expr!r}: {r}")
    return r["data"]["result"]
fails = []
up = q('up{job="prometheus-pushgateway"}')
if len(up) != 1 or up[0]["value"][1] != "1" or not up[0]["metric"].get("instance", "").startswith(POD_IP + ":"):
    fails.append(f"scrape: expected exactly one up==1 on {POD_IP}, got {[(r['metric'].get('instance'), r['value'][1]) for r in up]}")
for job in ("authentik-db-probe", "icloud-backup-freshness", "maintenance-window-liveness"):
    r = q(f'push_time_seconds{{job="{job}"}}')
    if not r:
        fails.append(f"{job}: no push_time_seconds series (group not re-pushed since restart)")
    elif float(r[0]["value"][1]) <= T0:
        fails.append(f"{job}: push_time {r[0]['value'][1]} <= T0 {T0:.0f} (pre-upgrade sample)")
checks = {
    'window_runs_liveness_verified == 1': 1,
    'count(icloud_backup_newest_file_timestamp_seconds)': 2,
    'count(authentik_audit_newest_event_timestamp_seconds)': 1,
}
for expr, want in checks.items():
    r = q(expr)
    got = float(r[0]["value"][1]) if r else None
    if got != want:
        fails.append(f"{expr}: got {got}, want {want}")
a = q('ALERTS{alertname=~"MaintenanceWindowLivenessMetricsAbsent|ICloudBackupFreshnessMetricMissing.*"}')
if a:
    fails.append(f"absence guard active: {[(x['metric']['alertname'], x['metric']['alertstate']) for x in a]}")
print("\n".join("FAIL " + f for f in fails) if fails else "PASS pushgateway contents restored after T0")
sys.exit(1 if fails else 0)
EOF
RC=$?; kill $PF 2>/dev/null; exit $RC
SH
bash /tmp/pgw-gate.sh "$(cat /tmp/pgw-T0)" "$(cat /tmp/pgw-POD_IP)"; echo "gate rc=$?"      # PASS + rc=0
```

**How each gate can fail.** Measured 2026-09-25 against the live pre-state with
the same script, before the ALERTS clause was added:
- `T0=now`: printed `FAIL authentik-db-probe: push_time … <= T0` for all three
  jobs, rc=1. This is what a stale pre-upgrade sample, or a gate run before the
  probes fired, looks like.
- wrong `POD_IP` (`10.0.0.1`): printed `FAIL scrape: expected exactly one up==1 on
  10.0.0.1, got [('10.69.2.241:9091', '1')]`, rc=1. This is what "Prometheus still
  scraping the old pod" looks like.
- `T0=now-48h` with the right IP: `PASS`, rc=0 (re-run with the ALERTS clause
  in place: still PASS).
- ALERTS clause, tested by pointing its regex at the currently-firing
  `MaintenanceWindowMissed`: printed `FAIL absence guard active:
  [('MaintenanceWindowMissed', 'firing')]`, rc=1.
- `plan-premises.py --controls`: 7 CONTROL lines and 7 instruments, all resolved
  against the repo rules and live Prometheus.
- A missing group prints `no push_time_seconds series`. After a restart,
  Prometheus marks the old series stale, so the query really does return empty
  rather than a leftover value.
- A `verified=0` re-push prints `window_runs_liveness_verified == 1: got None`.

If the gate prints FAIL only for `authentik-db-probe` / `icloud-backup-freshness`
and it is before hh:25, wait for the next `:17`/`:23` and re-run. Those are
push-cadence failures, not chart regressions. Anything else goes to §5.

**Deferred check (sweep, not the window):** after the next 08:00 or 20:00 local run,
`push_time_seconds{job="pellet-price-monitor"}` > T0. If it is not there, the
problem is the pellet CronJob, not this chart (the gate above already proves
the gateway accepts pushes).

**Tell the operator:** the firing `ICloudBackupPhotosStale*` series and
`MaintenanceWindowMissed`/`MaintenanceWindowsRepeatedlyMissed` sent a false
"resolved" at the restart. They were firing before, nothing is fixed, and they
re-fire after their `for:` (30m / 1h).

## 5. Rollback

`rollback_class: git-revert`. Nothing about pushgateway state is forward-only,
because the state is ephemeral whichever way you go.

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <sha-of-3.2>
git log -1 --format=%s && git show --stat HEAD     # the revert, one file
git push
kubectl get deploy -n monitoring prometheus-pushgateway -o jsonpath='{.spec.template.metadata.labels.helm\.sh/chart}{"\n"}'   # prometheus-pushgateway-3.8.0
kubectl rollout status -n monitoring deploy/prometheus-pushgateway --timeout=180s
```

The rollback restarts the pod AGAIN, so the state is wiped a second time.
Repeat §3.4 (liveness re-push) with a fresh `T0` and `POD_IP`, then re-run the §4
gate. Rollback is confirmed when the gate passes on 3.8.0.

If the §3.4 ledger check prints 0 (DSN or DB unavailable), **do not push the
fallback payload**. Pushing nothing leaves `MaintenanceWindowLivenessMetricsAbsent`
to page after 6h, which is an honest page. Pushing `verified=0` would instead fire
`MaintenanceWindowLivenessUnverified` and blank the Missed rules. Report it and
let the next sweep re-push.

## 6. Interference notes

- **Shared push target.** Any plan whose verification reads a pushed series
  (`authentik_db_*`, `authentik_audit_*`, `icloud_backup_*`, `pellet_*`,
  `window_runs_*`, `push_time_seconds`) must not share this window. That is why
  `icloud-backup-freshness-3.24.2` and `authentik-pg17-decommission` are in
  `conflicts_with`. `talos-1.14.1` is listed because a node drain restarts this
  pod as well.
- **The §4 gate reads Prometheus**, so `kube-prometheus-stack-91.4.1` is excluded.
- **Reciprocity.** `window-scheduler.py` honours `conflicts_with` symmetrically.
  Even so, `icloud-backup-freshness-3.24.2` should name this plan back, because
  its §2 baseline is exactly what this plan wipes.
- **Nightly-window caveat.** The 03:30 nightly start is fine: hh:00–hh:08 means
  starting at 04:00 (or 03:30 and waiting ≤30 min). The pellet group then stays
  missing until 08:00. That is inside `PalletCriticalSourceStale`'s 30h
  `absent_over_time` window, so there is no false page.
- **No routing, storage, CNI or auth surface is touched.** The pushgateway has
  no HTTPRoute (ClusterIP only) and no PVC.
