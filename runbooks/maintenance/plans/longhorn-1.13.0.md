---
plan_id: longhorn-1.13.0
component: longhorn
pr: null                              # no Renovate PR exists (gh pr list --search longhorn: none open);
                                      # the bump reaches us via coverage.py's direct-bump lane and is
                                      # HELD by the `*longhorn*` max: patch deny rule (8201c9dc).
kind: chart
current: "1.12.1"
target: "1.13.0"
update_type: minor
risk: high                            # storage engine under all 94 volumes; the upgrade is ONE-WAY
                                      # (upstream downgrade prevention, §5); 35 Kustomizations
                                      # dependsOn storage/longhorn -> cluster-wide Flux amber for
                                      # 5-15 min (docs/sops/longhorn.md "Chart Upgrade Storm").
est_duration_min: 70                  # pre-checks 15 + Phase A (chart, storm settle, verify) 30 +
                                      # Phase B (engine drain, async) 25. Phase B is SEPARABLE: if it
                                      # has not started by T+45 min, stop after Phase A (manager
                                      # 1.13.0 + engines 1.12.1 is a supported state) and re-window B.
needs_reboot: false
touches:
  namespaces: [storage]
  resources:
    - helmrelease/longhorn
    - daemonset/longhorn-manager       # rolls; serves the admission webhook on :9502
    - deployment/longhorn-ui
    - deployment/longhorn-driver-deployer
    - deployment/longhorn-global-manager   # NEW in 1.13.0, 3 replicas
    - "deployment/csi-attacher, csi-provisioner, csi-resizer, csi-snapshotter"   # re-created by the driver deployer under the NEW longhorn-csi-service-account
    - daemonset/longhorn-csi-plugin
    - "daemonset/engine-image-ei-* (new v1.13.0 engine image DaemonSet)"
    - "instancemanager/* (new v1.13.0 instance-manager pod per node)"
    - "crd/instancemanagerupgradecontrols.longhorn.io, instancemanagerupgrades.longhorn.io, snapshotgroups.longhorn.io"   # NEW CRDs
    - "clusterrole+clusterrolebinding/longhorn-csi-role, longhorn-csi-secret-role; role+rolebinding/longhorn-csi-role; serviceaccount/longhorn-csi-service-account"   # NEW RBAC
    - setting/concurrent-automatic-engine-upgrade-per-node-limit   # Phase B: 0 -> 1 -> 0 (CR op, not in git)
    - "volume/* (94, all attached, all v1) — Phase B live engine upgrade"
    - "systembackup/pre-1-13-0-<date>  (created in pre-check §2.6)"
    - "deployment/mealie (ns office) — restarted once in §4.4 as the attach/IO probe"
  shared:
    - storage/longhorn                # every stateful app in the cluster rides it
    - flux                            # 35 Kustomizations dependsOn storage/longhorn -> storm
    - monitoring                      # §4 reads Prometheus; longhorn-backend is a scrape target
                                      # whose reachability a chart default already broke once (3c73a7b0)
    - cifs/backups                    # the BackupTarget (NAS //…/backups) is written by the §2.6
                                      # SystemBackup; no CIFS StorageClass/PVC is touched
depends_on: []
conflicts_with:
  - talos-linux-1.14.2                # node roll restarts instance-managers + rebuilds replicas; never
                                      # pair with a storage-engine upgrade (same rule as 34abe2bb)
  - talconfig-multidoc-migration      # control-plane/etcd config change; exclusive, keep the
                                      # storage engine out of its slot and vice versa
  - jellyfin-config-rwo-migration     # allocates a NEW Longhorn volume + restore-proof on the engine
                                      # this plan is replacing; run before or after, never with
  # - mariadb-chart-27.3.0 (RESOLVED 2026-10-04: executed + retired 418faa1e (now:2026-10-03); dead ref removed per the dead-ref convention)
  - mariadb-28.1.1  # ADDED 2026-10-04: successor plan (same databases/mariadb HR + mariadb-0 roll); reciprocal -- it already lists this plan
    # its gates read Longhorn backup freshness; Phase B moves every
                                      # engine under it
  - flux-fleet-0.60.0                 # Flux controllers are the instrument that judges the storm;
                                      # changing them in the same slot makes §4.1 unreadable
  - flux-oci-chart-sources            # moves the longhorn HelmRepository source (shared storage/longhorn, flux)
  - flux-reconciler-impersonation     # Flux control-plane change; same reasoning as flux-fleet
  - bitnamilegacy-exit-nextcloud-db   # allocates a new Longhorn volume
exclusive: true                       # the storm fans out to 35 dependents (+ transitive); any other
                                      # plan's Flux-Ready gate in the same slot reads false-red, and
                                      # a one-way storage change must not share attribution.
security_ref: F-723fbe83              # see finding_refs for the full set; detail stays in the DB
capability_change: true               # NOT "to be safe": 1.13.0 adds 3 new CRD kinds (new API surface),
                                      # a new cluster-scoped workload (longhorn-global-manager running
                                      # the pod/PV controllers) and a new ServiceAccount with
                                      # cluster-wide Secret `get` (longhorn-csi-service-account). No
                                      # new feature is switched ON by our values, but the permission
                                      # and API surface change is real.
rollback_class: one-way               # upstream: "Once you successfully upgrade to v1.13.0, you will
                                      # not be allowed to revert to the previously installed version."
finding_refs:
  - F-f79c74ac                        # plan: 1.13.0 had no deny rule (now held)
  - F-4125346e                        # version: longhorn chart 1.12.1 -> 1.13.0
  - F-723fbe83                        # longhorn-manager image (clears in Phase A)
  - F-205433dd                        # longhorn-ui image (clears in Phase A)
  - F-3bc71aff                        # longhorn-engine image (clears in Phase B)
  - F-21e6a381                        # longhorn-instance-manager image (clears in Phase B)
  - F-23a73fba                        # longhorn-share-manager image (see §4.8 — may need a remount)
review: null
status: draft
window: null
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/longhorn.md
  - docs/sops/storage-safety.md
  - docs/sops/backup.md
  - docs/sops/flux-dependency-revision-gate.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-10-01"
---

# Longhorn 1.12.1 -> 1.13.0 (chart + manager, then live engine drain)

## 1) Summary & why held

**What changes.** `kubernetes/apps/storage/longhorn/app/helmrelease.yaml`
`spec.chart.spec.version` `"1.12.1"` -> `"1.13.0"` (appVersion v1.13.0). Then,
in the same window, a live engine upgrade of every volume from
`longhorn-engine:v1.12.1` to `v1.13.0` by temporarily raising
`concurrent-automatic-engine-upgrade-per-node-limit` 0 -> 1 -> 0 — the exact
CR operation used for the 1.12.1 engine drain (34abe2bb).

**Why held.** The `*longhorn*` `max: patch` rule in
`runbooks/auto-update-policy.yaml` (8201c9dc, F-f79c74ac). Before that rule,
1.13.0 was held only by the 48h cooldown and would have landed unattended.
Three facts make it a planned change and not a false positive:

1. **It is one-way.** Upstream upgrade doc (longhorn.io/docs/1.13.0/deploy/upgrade):
   > "Starting with v1.5.0, Longhorn only supports upgrades from one minor
   > version to the next … Warning: Once you successfully upgrade to v1.13.0,
   > you will not be allowed to revert to the previously installed version."
   A `git revert` after a successful upgrade does NOT roll back — the
   pre-upgrade hook rejects the downgrade. See §5.
2. **Breaking change, checked:** release notes, "Breaking Changes":
   > "Because the CSI external-provisioner is upgraded to v6.3.0, all clusters
   > must be running Kubernetes v1.34 or later before installing or upgrading
   > to Longhorn v1.13.0."
   Live: server `v1.36.0` on all three nodes; chart `kubeVersion: '>=1.34.0-0'`.
   **Met.** The other breaking item (legacy V2 linked-clone volumes) does not
   apply: `v2-data-engine=false`, 94/94 volumes `dataEngine=v1`.
3. **Architecture moves inside a minor** (measured by `helm template` of both
   charts with OUR `spec.values`, `--kube-version 1.36.0`): 47 -> 58 objects.
   New: `Deployment longhorn-global-manager` (3 replicas, runs the cluster-wide
   pod and PV controllers that previously lived in the manager DaemonSet —
   upstream: "Before upgrading, make sure at least one of its pods can be
   scheduled"); CSI sidecars move to a dedicated `longhorn-csi-service-account`
   with new ClusterRole/Role bindings; 3 new CRDs
   (`instancemanagerupgradecontrols`, `instancemanagerupgrades`,
   `snapshotgroups`, all `v1beta2`). **No existing CRD changes its
   served/storage versions** (diffed). Rendered ConfigMaps, Services and
   StorageClasses are identical apart from the version label.

**The 1.12.1 trap, re-checked for 1.13.0.** 1.13.0 keeps
`networkPolicies.restrictInternalTraffic: true` as the chart DEFAULT and
renders **6 NetworkPolicies** without our pin. Our top-level
`networkPolicies.restrictInternalTraffic: false` (3c73a7b0) is still honoured —
rendered with our values: **0 NetworkPolicies** on both 1.12.1 and 1.13.0. 1.13.0
also adds `networkPolicies.metricsScrapeSources` (the allow-list hook the
3c73a7b0 note said adoption would need); adopting the hardening stays a
separate plan — do NOT flip it here.

**Upgrade path.** 1.12.1 -> 1.13.0 is `x.y.* -> x.(y+1).*`: supported. The
release notes' "live upgrade only from v1.12.2" caveat is about **V2** volumes
only (none here). Note: v1.12.2 is referenced by the notes but is **not
published** (latest releases: 1.13.0, 1.12.1) — do not wait for it.

**Engine/instance-manager behaviour (why Phase B exists).** Upstream:
> "first upgrade Longhorn manager to the latest version, then manually upgrade
> the Longhorn engine … Since Longhorn v1.1.1, we provide an option to help you
> automatically upgrade engines."
Live `concurrent-automatic-engine-upgrade-per-node-limit` = `0`, so after
Phase A every volume stays on the v1.12.1 engine and the three v1.12.1
instance-manager pods keep running beside new v1.13.0 ones. That is a
supported, compatible state (the gate in §4.2 asserts `INCOMPATIBLE=false`),
but it leaves the engine and instance-manager findings open. Phase B drains.

**Security driver — detail withheld from this public repo.** Tracked as
F-723fbe83 (manager), F-205433dd (ui), F-3bc71aff (engine), F-21e6a381
(instance-manager), F-23a73fba (share-manager): each a "newer upstream tag
available" finding on the v1.12.1 images. `runbooks/policy-cli.py finding show <id>`.
Convention: `docs/sops/vulnerability-disclosure.md`.

**Freshness caveat.** 1.13.0 was published 2026-09-29. At window time, check
`gh release list -R longhorn/longhorn -L 5` and the
[Release-Known-Issues wiki](https://github.com/longhorn/longhorn/wiki/Release-Known-Issues);
if 1.13.1 exists, retarget THIS plan in place (keep the plan_id; README
"When the held target MOVES").

## 2) Pre-checks (all read-only except 2.6; every one must PASS)

Run from the repo root on the Mac mini (zsh).

2.1 **Chart and cluster at the expected pre-state.**
```bash
kubectl -n storage get hr longhorn -o jsonpath='{.spec.chart.spec.version} {.status.conditions[?(@.type=="Ready")].status}{"\n"}'
# PASS: 1.12.1 True
kubectl version -o json | python3 -c "import sys,json;v=json.load(sys.stdin)['serverVersion'];print(v['major'],v['minor'])"
# PASS: minor >= 34 (live 2026-10-01: 1 36)
kubectl -n storage get settings.longhorn.io current-longhorn-version default-engine-image v2-data-engine concurrent-automatic-engine-upgrade-per-node-limit -o custom-columns=N:.metadata.name,V:.value --no-headers
# PASS: v1.12.1 / longhorn-engine:v1.12.1 / false / 0
```

2.2 **Every volume healthy, none faulted, none V2** (upstream: "Avoid upgrading
when volumes are in the Faulted status").
```bash
kubectl -n storage get volumes.longhorn.io -o jsonpath='{range .items[*]}{.spec.dataEngine} {.status.state} {.status.robustness} {.status.currentImage}{"\n"}{end}' | sort | uniq -c
# PASS: exactly one line, "<N> v1 attached healthy docker.io/longhornio/longhorn-engine:v1.12.1"
# (2026-10-01: N=94). Any degraded/faulted/unknown/detached line -> STOP and triage.
# Record N as $CENSUS for §4.
```
If a volume is `detached`: read the 34abe2bb commit message first — Phase B
re-points a DETACHED volume's engine directly; "detached" is not an exclusion.
Get an operator ruling before Phase B if that volume is a rollback floor.

2.3 **No failed BackingImage** (upstream manual check).
```bash
kubectl -n storage get backingimages.longhorn.io --no-headers 2>/dev/null | wc -l   # expect 0 (none in use)
```

2.4 **Backups fresh for EVERY volume** (upstream prerequisite: "Always back up
volumes before upgrading"). The 03:00 `daily-backup-all-volumes` run is ~6h
old at a 09:00 window.
```bash
.venv/bin/python3 runbooks/longhorn-backup-age.py $(kubectl -n storage get volumes.longhorn.io -o jsonpath='{.items[*].metadata.name}') --max-hours 10 > /tmp/lh-pre-backup.txt; echo rc=$?
grep -vc " FRESH " /tmp/lh-pre-backup.txt
# PASS: rc=0 and 0. Measured 2026-10-01 (with --max-hours 26): 94 FRESH, rc=0.
# The helper exits 1 on any STALE/NONE and 2 on a lookup error (fails closed).
kubectl -n storage get backuptarget default -o jsonpath='{.status.available}{"\n"}'   # PASS: true
```

2.5 **Scrape baseline** (the instrument §4 reads).
```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
for q in 'count(up{job="longhorn-backend"}==1)' 'count(longhorn_volume_robustness==1)' 'count(longhorn_instance_manager_cpu_usage_millicpu)'; do
  echo "$q => $(curl -s --data-urlencode "query=$q" http://localhost:19090/api/v1/query | python3 -c 'import sys,json;r=json.load(sys.stdin)["data"]["result"];print(r[0]["value"][1] if r else "EMPTY")')"; done
kill $PF 2>/dev/null
# PASS: 3 / $CENSUS / 3   (2026-10-01: 3 / 94 / 3). "EMPTY" on any line = STOP.
kubectl -n storage get networkpolicy -o name | wc -l    # PASS: 0
```

2.6 **Longhorn SystemBackup** (upstream: "It is recommended to create a
Longhorn system backup before performing the upgrade"). The only existing
SystemBackups (`unas-v1`, `unas-v2`) are v1.6.2 from 2025 — useless. Volume
data is already covered by 2.4, so skip re-backing volumes:
```bash
D=$(date +%Y%m%d)
cat <<EOF | kubectl apply -f -
apiVersion: longhorn.io/v1beta2
kind: SystemBackup
metadata:
  name: pre-1-13-0-$D
  namespace: storage
spec:
  volumeBackupPolicy: disabled
EOF
# Wait until Ready (typically < 2 min):
kubectl -n storage get systembackups.longhorn.io pre-1-13-0-$D -o jsonpath='{.status.state} {.status.version}{"\n"}'
# PASS: "Ready v1.12.1". "Error" or stuck > 10 min -> STOP (backup target path is broken,
# which would also break every post-upgrade backup).
```

2.7 **No in-flight storage work.** No `jellyfin-config-rwo-migration`,
`talos-*`, or engine drain in progress (`exclusive: true` keeps them out of the
slot, but confirm): `kubectl -n storage get volumes.longhorn.io -o jsonpath='{range .items[*]}{.status.currentImage}{" "}{.spec.image}{"\n"}{end}' | awk '$1!=$2' | wc -l` -> `0`.
Not running 02:00-03:30 (trim/snapshot-cleanup/backup CronJobs).

## 3) Steps

### Phase A — chart 1.12.1 -> 1.13.0 (GitOps)

A1. Edit the version (dry-tested on a scratch copy, BSD sed):
```bash
sed -i '' 's/^\([[:space:]]*version:[[:space:]]*\)"1\.12\.1"$/\1"1.13.0"/' kubernetes/apps/storage/longhorn/app/helmrelease.yaml
git diff kubernetes/apps/storage/longhorn/app/helmrelease.yaml
# Expected, exactly one hunk:
# -      version: "1.12.1"
# +      version: "1.13.0"
```
Do NOT touch `networkPolicies.restrictInternalTraffic: false` or the inert
`longhorn:` block. Do NOT add `spec.upgrade.remediation` / rollback — a Flux
rollback after a successful upgrade is a downgrade Longhorn refuses.

A2. Commit + push (shared worktree rules):
```bash
git commit --only kubernetes/apps/storage/longhorn/app/helmrelease.yaml -m "feat(longhorn): chart 1.12.1 -> 1.13.0 (plan longhorn-1.13.0)"
git show --stat HEAD && git log -1 --format=%s    # only the helmrelease; subject is yours
git push
```

A3. **Push nothing else until §4.1 converges** — every commit re-arms the
`dependsOn` revision gate for 35 Kustomizations (docs/sops/longhorn.md "Chart
Upgrade Storm"). Expect 5-15 min of cluster-wide Flux amber; do NOT roll back
on dependents' messages. Judge only `storage/longhorn` and revision
convergence (§4.1).

If the HelmRelease reports a failed upgrade with `pre-upgrade hooks failed`:
the upgrade did NOT happen (pre-upgrade checker refused it) -> read
`kubectl -n storage logs job/longhorn-pre-upgrade` and go to §5 case 1. If it
failed on `timeout` while §4.2 shows all new pods Ready, the upgrade applied
and only Helm's wait expired: operator-present, run
`flux reconcile hr longhorn -n storage --force` once to re-record it.

### Phase B — live engine drain v1.12.1 -> v1.13.0 (CR operation)

Start only if §4.1-§4.6 all PASS and the clock is <= T+45 min; otherwise end
the window after Phase A and re-window Phase B as its own slot.

B1. Confirm the new engine image is the default and deployed:
```bash
kubectl -n storage get engineimages.longhorn.io -o custom-columns=N:.metadata.name,IMG:.spec.image,STATE:.status.state,INCOMPAT:.status.incompatible,REF:.status.refCount
kubectl -n storage get settings.longhorn.io default-engine-image -o jsonpath='{.value}{"\n"}'
# PASS: a v1.13.0 row state=deployed incompatible=false; default = ...longhorn-engine:v1.13.0
```
B2. Enable the drain (one volume per node at a time — 34abe2bb precedent):
```bash
kubectl -n storage patch settings.longhorn.io concurrent-automatic-engine-upgrade-per-node-limit --type merge -p '{"value":"1"}'
```
B3. Watch progress (async; each live upgrade is a brief per-volume IO pause):
```bash
kubectl -n storage get volumes.longhorn.io -o jsonpath='{range .items[*]}{.status.currentImage} {.status.robustness}{"\n"}{end}' | sort | uniq -c
```
Abort criteria (go to §5 Phase B): any volume `faulted`; > 2 volumes
`degraded` for > 10 min; any app pod with IO errors on its PVC.
B4. When every volume reports `v1.13.0` (or at the window's end, whichever
first), **always** return the limit to 0:
```bash
kubectl -n storage patch settings.longhorn.io concurrent-automatic-engine-upgrade-per-node-limit --type merge -p '{"value":"0"}'
kubectl -n storage get settings.longhorn.io concurrent-automatic-engine-upgrade-per-node-limit -o jsonpath='{.value}{"\n"}'   # PASS: 0
```
A partially drained fleet is a supported state; finish it in the next slot.

## 4) Verification

4.1 **Storm converged (the clearing test from docs/sops/longhorn.md).**
```bash
kubectl get endpoints -n storage longhorn-admission-webhook -o jsonpath='{range .subsets[*].addresses[*]}{.ip}{" "}{end}{"\n"}' | wc -w   # PASS: 3
kubectl -n storage get ds longhorn-manager -o jsonpath='{.status.desiredNumberScheduled} {.status.numberReady} {.status.updatedNumberScheduled}{"\n"}'   # PASS: 3 3 3
HEAD=$(git rev-parse --short HEAD); flux get kustomizations -A | tail -n +2 | grep -cv "$HEAD"   # PASS: 0 within 20 min
```
Fails if: the webhook Service has no endpoints (prints < 3) or the DS is
stuck below desired (> 10 min => "wedged" per SOP; diagnose
`kubectl -n storage logs ds/longhorn-manager --previous`).

4.2 **CONTENTS ASSERTION: the manager is actually 1.13.0 and still accepts the old engine** — measured through the manager API and the EngineImage CR, compared to 2.1.
```bash
kubectl -n storage get settings.longhorn.io current-longhorn-version -o jsonpath='{.value}{"\n"}'   # PASS: v1.13.0
kubectl -n storage get ds longhorn-manager -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'   # PASS: ...longhorn-manager:v1.13.0
kubectl -n storage get engineimages.longhorn.io -o custom-columns=IMG:.spec.image,STATE:.status.state,INCOMPAT:.status.incompatible --no-headers
# PASS: the v1.12.1 row is "deployed false" (still compatible) and a v1.13.0 row is "deployed false".
# A "true" in INCOMPAT for v1.12.1 means volumes cannot be operated until upgraded -> start Phase B at once.
kubectl -n storage get deploy longhorn-global-manager -o jsonpath='{.status.readyReplicas}/{.spec.replicas}{"\n"}'   # PASS: 3/3 (>=1 is upstream's minimum)
kubectl -n storage get deploy csi-attacher csi-provisioner -o jsonpath='{range .items[*]}{.metadata.name}={.spec.template.spec.serviceAccountName} {.status.readyReplicas}{"\n"}{end}'
# PASS: both "=longhorn-csi-service-account 3". Still longhorn-service-account => the driver
# deployer has not rolled the CSI layer yet (wait); Ready < 3 => new SA lacks a permission.
```

4.3 **Prometheus still scrapes longhorn-manager (the 3c73a7b0 regression class).**
```bash
kubectl -n storage get networkpolicy -o name | wc -l   # PASS: 0 (a non-zero count is the 1.12.1 trap again)
# then re-run the 2.5 Prometheus block >= 5 min after 4.1 passes
# PASS: 3 / $CENSUS / >=3  (IM count is 6 while old+new IMs coexist before Phase B — also PASS)
```
CONTROL: metric up — `up{job="longhorn-backend"}` must be 1 on all 3 manager
pods' NEW IPs; 3c73a7b0 is the measured negative (all three went 0 with the
NetworkPolicies present).
CONTROL: metric longhorn_volume_robustness — `count(==1)` equals $CENSUS; an
empty result prints `EMPTY` and fails (the series is emitted by the manager,
so a silently dead exporter cannot pass).
CONTROL: metric longhorn_instance_manager_cpu_usage_millicpu — count >= 3.
CONTROL: alertname LonghornManagerDown — must NOT be firing 10 min after 4.1
(`expr: up{job="longhorn-backend"} == 0`, for 2m, in
`kubernetes/apps/monitoring/kube-prometheus-stack/app/longhorn-alerts.yaml`).
CONTROL: alertname LonghornVolumeDegraded — not firing after Phase B settles.

4.4 **CONTENTS ASSERTION: a real detach -> attach -> mount -> write/read round-trip through the NEW CSI layer** — measured on `office/mealie` (`mealie-data`, longhorn-static RWO, Deployment strategy `Recreate`, verified live), compared to a nonce written in the same step.
```bash
kubectl -n office rollout restart deploy/mealie && kubectl -n office rollout status deploy/mealie --timeout=300s
N=lh113-$(date +%s)
kubectl -n office exec deploy/mealie -c main -- sh -c "echo $N > /app/data/.lh-upgrade-probe && sync && cat /app/data/.lh-upgrade-probe && rm /app/data/.lh-upgrade-probe"
# PASS: prints exactly the nonce. FAILS on: pod stuck ContainerCreating (attach/mount via new
# csi-attacher/longhorn-csi-plugin broken — rollout status times out), "Read-only file system"
# or "Input/output error" (non-zero exit), or a different string.
kubectl -n office get pod -l app.kubernetes.io/name=mealie -o jsonpath='{.items[0].status.startTime}{"\n"}'   # must be AFTER the push time
```
Run 4.4 again after Phase B (the volume's engine has then been live-swapped).
Residual: the PROVISION path (csi-provisioner v6.3.0) is not exercised — no
scratch PVC is created, by rule. It is exercised by the next new PVC; check
`kubectl -n storage logs deploy/csi-provisioner --since=30m | grep -ic error` -> 0.

4.5 **UI serves and talks to the 1.13.0 manager** (CONTENTS, not 200).
```bash
kubectl -n storage port-forward svc/longhorn-frontend 18080:80 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s http://localhost:18080/v1/settings/current-longhorn-version | python3 -c "import sys,json;print(json.load(sys.stdin).get('value'))"
kill $PF 2>/dev/null
# PASS: v1.13.0 (measured pre-change through the same path: v1.12.1). An HTML body or
# a JSON error raises in python and prints a traceback = FAIL.
```

4.6 **Backups still work.**
- Immediately: `kubectl -n storage get backuptarget default -o jsonpath='{.status.available} {.status.lastSyncedAt}{"\n"}'` -> `true` and a timestamp AFTER the push.
- Next morning (deferred gate, the window agent records it in its report;
  the 03:00 `daily-backup-all-volumes` RecurringJob/CronJob runs under 1.13.0):
  ```bash
  .venv/bin/python3 runbooks/longhorn-backup-age.py $(kubectl -n storage get volumes.longhorn.io -o jsonpath='{.items[*].metadata.name}') --max-hours 8; echo rc=$?
  # PASS: rc=0 — every volume FRESH from the post-upgrade 03:00 run (>= the $CENSUS lines)
  ```
  CONTROL: alertname LonghornBackupFailed — not firing
  (`(longhorn_backup_state == 4) unless on(volume) (longhorn_backup_state == 3)`).
  CONTROL: metric longhorn_backup_state — non-empty (2026-10-01: 882 series).
  Note upstream fixed "Recurring-job pods report success after startup or volume
  execution errors" (#13587) in 1.13.0: a CronJob that was silently green may
  now honestly fail. A new failure here is signal, not upgrade breakage — triage it.

4.7 **Phase B result.**
```bash
kubectl -n storage get volumes.longhorn.io -o jsonpath='{range .items[*]}{.status.state} {.status.robustness} {.status.currentImage}{"\n"}{end}' | sort | uniq -c
# PASS: one line "<CENSUS> attached healthy docker.io/longhornio/longhorn-engine:v1.13.0"
kubectl -n storage get instancemanagers.longhorn.io -o custom-columns=IMG:.spec.image,ST:.status.currentState --no-headers | sort | uniq -c
# PASS (may take minutes after the last volume): 3 x instance-manager:v1.13.0 running, 0 x v1.12.1
kubectl -n storage get engineimages.longhorn.io -o custom-columns=IMG:.spec.image,REF:.status.refCount --no-headers
# PASS: v1.12.1 refCount 0 (then GC'd). A non-zero residual must be NAMED volume-by-volume.
```

4.8 **Share-manager (F-23a73fba) — observe, do not force.**
`kubectl -n storage get pod share-manager-jellyfin-config -o jsonpath='{.spec.containers[0].image}{"\n"}'`.
If still `:v1.12.1`, the share-manager pod is only re-created on the next
remount of the RWX volume; do NOT restart Jellyfin for it here (igpu-i915,
media users). It clears with `jellyfin-config-rwo-migration`, which retires
the RWX share entirely, or at Jellyfin's next restart. Record the state on the
finding.

## 5) Rollback

**There is no chart rollback after a successful upgrade** (downgrade
prevention, §1). The procedure depends on where it failed:

**Case 1 — pre-upgrade hook refused (upgrade never happened).** §4.2 still
shows `current-longhorn-version=v1.12.1`. Safe to revert:
```bash
git revert --no-edit <sha-of-A2>    # restores version: "1.12.1"
git show --stat HEAD && git log -1 --format=%s
git push
kubectl -n storage get hr longhorn -o jsonpath='{.status.history[0].chartVersion} {.status.conditions[?(@.type=="Ready")].status}{"\n"}'   # PASS: 1.12.1 True
```
Then confirm 2.2 and 2.5 match their baselines.

**Case 2 — upgraded, but a regression (scrape lost, CSI attach failing, UI broken).**
Forward-fix, do NOT revert the version:
- Scrape lost / NetworkPolicies appeared: confirm `networkPolicies.restrictInternalTraffic: false`
  is still at the TOP LEVEL of `spec.values`; if 1.13.x changed its semantics,
  set `networkPolicies.metricsScrapeSources` to the monitoring namespace +
  Prometheus pod selector (from the chart's values.yaml comment) — a separate
  commit, after reading the rendered policy.
- CSI attach failing under the new SA: collect `kubectl -n storage logs deploy/csi-attacher`
  and `kubectl -n storage describe deploy/csi-attacher`; this is an upstream
  bug -> open/track the upstream issue and take the next 1.13.x patch (the
  `max: patch` rule lets it auto-apply).
- Volumes faulted/data loss (last resort): restore the affected volumes from
  the 03:00 backups verified in 2.4 (`docs/sops/backup.md` restore section);
  Longhorn resources from SystemBackup `pre-1-13-0-<date>` via a
  `SystemRestore` CR (docs/sops/longhorn.md / upstream "Restore Longhorn System").
  Note: a SystemRestore into a 1.13.0 install from a 1.12.1 backup is itself
  version-gated — it is a disaster-recovery path, not a downgrade.

**Phase B — partial or misbehaving drain.**
1. Stop it: patch the limit back to `0` (B4). In-flight upgrades finish; no new ones start.
2. A volume that misbehaves on the new engine can be live-upgraded BACK to the
   v1.12.1 engine image while that EngineImage is still deployed (refCount > 0
   keeps it from GC) — Longhorn UI -> volume -> Upgrade Engine -> select v1.12.1,
   one volume at a time, attended. Once the v1.12.1 EngineImage has GC'd this
   path is gone; that is why B4 runs before the window closes and 4.7 is
   checked before declaring Phase B done.
3. Confirm: rerun 4.4 and the 4.3 Prometheus block.

## 6) Interference notes

- **Exclusive slot.** A Longhorn manager roll takes down the admission webhook
  (served by longhorn-manager :9502) for the DaemonSet roll and fans out to 35
  Kustomizations that `dependsOn: storage/longhorn` (measured live 2026-10-01;
  the SOP says 36). Any other plan's "Flux Ready" gate in the same slot reads
  false-red, and every extra commit re-arms the storm. Hence `exclusive: true`
  on top of `conflicts_with`.
- **Window choice.** HUMAN-GATED (one-way + capability_change + storage floor).
  `sat-attended` (09:00, 70 min budget) fits; `nightly` (03:30) does NOT —
  it overlaps the 03:00 `daily-backup-all-volumes` run whose concurrency-2
  backups would be in flight during the manager roll and Phase B. Never
  02:00-03:30 (trim 02:00, snapshot-cleanup 02:30, backup 03:00 —
  `kubectl -n storage get cronjob` verified).
- **Reciprocity owed** (this plan can only write its own file): the plans in
  `conflicts_with` should list `longhorn-1.13.0` back. `talos-linux-1.14.2`
  and `talconfig-multidoc-migration` are `exclusive: true` already, so slot
  separation holds in both directions today; `jellyfin-config-rwo-migration`,
  `mariadb-chart-27.3.0`, `flux-fleet-0.60.0`, `flux-oci-chart-sources`,
  `flux-reconciler-impersonation`, `bitnamilegacy-exit-nextcloud-db` should add it.
- **Ordering preference (not a hard dep):** run BEFORE
  `jellyfin-config-rwo-migration` so its new volume is born on the 1.13.0
  engine and the RWX share-manager (F-23a73fba) retires on the new line; and
  NOT the day before `talos-linux-1.14.2` — the node roll restarts every
  instance-manager, and a fresh engine line should soak >= 2 nightly backup
  cycles first.
- **Prometheus is shared instrument.** §4.3 reads it; no
  `kube-prometheus-stack` bump is open (91.4.1 executed 2026-09-26). If one is
  written, it must conflict with this plan.
- **Storage safety.** No PVC/PV is deleted or created by this plan. No CIFS
  StorageClass is touched; the BackupTarget (CIFS) is only written to by the
  SystemBackup (2.6). The `mealie` restart in 4.4 is the only app pod this
  plan restarts deliberately.
- **Not in this plan (deliberate):** adopting `restrictInternalTraffic` /
  `metricsScrapeSources`; turning off `csi.allowControllerSecretAccess` (safe
  later — no StorageClass carries `csi.storage.k8s.io/provisioner-secret-*`,
  verified); age-based retention; un-nesting the inert `longhorn:` values block.

**Repo corrections found while planning** (not fixed here — planner writes only the plan):
1. `docs/sops/longhorn.md` §"Longhorn Version Upgrade via Flux" step 3 says
   `kubectl rollout status -n storage deployment/longhorn-manager` — longhorn-manager
   is a **DaemonSet**; the command fails. Should be `ds/longhorn-manager`, and the
   section should mention the one-way downgrade prevention and the separate
   engine-drain step (`concurrent-automatic-engine-upgrade-per-node-limit` is 0
   by design here).
2. Same SOP says 36 `dependsOn` Kustomizations; live count is 35.
