---
plan_id: prometheus-volume-rightsize
component: kube-prometheus-stack
pr: null                              # not a version bump and not a Renovate item.
                                      # Capacity remediation on a live datastore,
                                      # raised by the operator from the 2026-09-06
                                      # Longhorn scheduling measurement.
kind: infra
current: "Longhorn volume `prometheus-kube-prometheus-stack` — 100Gi declared,
  8.22 GiB filesystem-used, 2 replicas (k8s-nuc14-02 + k8s-nuc14-03).
  PV `prometheus-kube-prometheus-stack` (longhorn-static, Retain) bound to PVC
  `prometheus-kube-prometheus-stack-db-prometheus-kube-prometheus-stack-0`."
target: "NEW Longhorn volume `prometheus-tsdb` — 30Gi declared, 2 replicas,
  seeded with a file-level copy of the live TSDB, cut over by repointing the
  StatefulSet's volumeClaimTemplate. The 100Gi volume is KEPT, detached and
  intact, as the rollback for a 7-day soak."
update_type: refactor                 # no software version changes; storage geometry only
risk: high                            # see §1 "Why high". Live monitoring datastore,
                                      # PVC delete + recreate, and the whole alerting
                                      # + collection path is DOWN for the cutover.
est_duration_min: 45                  # 45 total; of which Prometheus is DOWN for 15-25
                                      # (budget 30, hard abort at 40 — see §1)
needs_reboot: false
touches:
  namespaces: [monitoring, storage]
  resources:
    - prometheus/kube-prometheus-stack                 # CR paused, then storage spec changed
    - statefulset/prometheus-kube-prometheus-stack     # DELETED and recreated by the operator
    - pod/prometheus-kube-prometheus-stack-0           # down for the cutover
    - pvc/prometheus-kube-prometheus-stack-db-prometheus-kube-prometheus-stack-0  # DELETED + recreated
    - pv/prometheus-kube-prometheus-stack              # -> Released, Retain, KEPT (the rollback)
    - "longhorn:volume/prometheus-kube-prometheus-stack"   # detached, KEPT for the soak
    - "longhorn:volume/prometheus-tsdb"                # NEW, hand-applied per docs/sops/longhorn.md
    - pv/prometheus-tsdb                               # NEW, Flux-managed
    - pvc/prometheus-tsdb-seed                         # NEW, transient, deleted in-window
    - job/prometheus-tsdb-copy                         # NEW, transient, deleted in-window
    - configmap/kube-prometheus-stack-values           # helmvalues.yaml edit
    - helmrelease/kube-prometheus-stack                # suspended + resumed
    - kustomization/kube-prometheus-stack              # suspended + resumed (ns monitoring)
  shared: [monitoring, longhorn]
    # monitoring: Prometheus is the SOURCE for every alert rule (110 groups / 446
    #   rules) and every Grafana prometheus-datasource panel. While it is down,
    #   NOTHING alerts and NOTHING is collected, cluster-wide. This is not a
    #   "monitoring namespace" co-location note — it is a cluster-wide blind spot.
    # longhorn: creates + deletes Longhorn volumes and moves ~140 GiB of
    #   scheduling reservation across nuc14-02/03. Per runbooks/autonomy-policy.yaml
    #   `forbid_shared: [storage, longhorn]`, this can NEVER derive AUTO-* —
    #   correct, and declared deliberately.
depends_on: []
conflicts_with: [grafana-13.0.0, unpoller-v5.1.0]
  # NOT merely same-namespace. Both of those plans verify themselves through
  # Grafana datasources and through "are the metrics still arriving" gates.
  # If Prometheus history is being moved in the same slot, a dead panel is
  # ambiguous between three causes and none of the three gates means anything.
  # Those two already carry a live INTERFERENCE warning with EACH OTHER in
  # sat-attended:2026-09-19 — do not add a third monitoring plan to that slot.
security_ref: null
capability_change: false              # same Prometheus v3.14.0-distroless, same
                                      # retention: 7d / retentionSize: 20GiB, same
                                      # scrape config, same rules. Only the disk the
                                      # TSDB sits on changes size. No user-visible
                                      # behaviour change is intended.
rollback_class: backup-restore        # NOT git-revert. `git revert` restores the
                                      # helmvalues but does NOT re-bind the PVC: the
                                      # PVC is deleted and recreated in §3, so
                                      # recovery means re-pointing at the retained
                                      # 100Gi PV and letting the operator rebuild the
                                      # StatefulSet. Concrete steps in §5.
backup_gate: "The OLD volume itself is the gate, and it is verified live, not from a
  timestamp: BEFORE the PVC is deleted (Step 8), the copy job's output must match the
  source on (a) identical sorted TSDB block-directory listing, (b) byte-exact `du -sb`,
  (c) identical file count. The 100Gi PV is then left Released+Retain and its Longhorn
  volume left detached and intact for a 7-day soak. Longhorn's own nightly backup of
  this volume (backup-96e0ceca7fef4199, 2026-09-06T03:06:14Z, target
  cifs://192.168.55.240/backups) is a SECOND floor but is NOT the gate — a restore
  from it lands a 100Gi volume, not a 30Gi one (see §1)."
finding_refs: []                      # no sweep finding drives this; the operator
                                      # raised it from a direct Longhorn measurement.
                                      # Related-but-not-owned: F-1b602271 (doc-agent,
                                      # "SOP gap: Longhorn per-disk provisioning
                                      # ceiling (StorageMaximum minus StorageReserved)
                                      # is undocumented") — this plan is the concrete
                                      # instance of exactly that gap biting.
status: draft
window: null
  # MUST NOT be scheduled into sat-attended:2026-09-19 — that slot already carries
  # grafana-13.0.0 + unpoller-v5.1.0 with a live monitoring INTERFERENCE warning
  # between them (see conflicts_with).
  # The operator has asked to execute this SAME-DAY (2026-09-06), attended, outside
  # the window system. §1 "Is same-day safe?" answers that question directly: YES.
  # `window:` stays null either way — the window agent assigns slots; an
  # operator-attended out-of-band run does not consume one.
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/longhorn.md
  - docs/sops/storage-safety.md
  - docs/sops/backup.md
  - docs/sops/monitoring.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-09-06"
---

# Right-size the Prometheus Longhorn volume: 100Gi → 30Gi

## 1. Summary & why this needs a plan

### The problem, measured 2026-09-06

Longhorn schedules replicas against **declared** volume size, not actual usage, and
`storage-over-provisioning-percentage: 100` caps total commitment at physical usable
capacity. Measured from `kubectl get nodes.longhorn.io -n storage` (values below in
**GiB**; the Longhorn API reports decimal bytes, so `840.0 GiB = 901.9 GB` — same
number, different unit):

| node | replicas | declared | actual | headroom | usable |
|---|---|---|---|---|---|
| k8s-nuc14-01 | 50 | 567.0 GiB | 137.6 GiB | 312.9 GiB | 879.9 GiB |
| k8s-nuc14-02 | 74 | **840.0 GiB** | 150.3 GiB | **39.9 GiB** | 879.9 GiB |
| k8s-nuc14-03 | 68 | 744.0 GiB | 107.0 GiB | 135.9 GiB | 879.9 GiB |

Cluster-wide: **1063.0 GiB declared vs 197.2 GiB actual across 94 volumes = 18.6%**.
Node 02 sits at **95.5% committed with 415 GB physically free**. The first real
symptom already landed: volume `clawd-bot-data` logged
`Scheduled: False / LocalReplicaSchedulingFailure: insufficient storage` because
`defaultDataLocality: best-effort` could not place a local replica on node 02.
(Honest note: as of 2026-09-06T07:33:02Z that volume's `Scheduled` condition is back
to `True` — the symptom cleared on its own. The *cause* did not.)

**The single biggest contributor, by a wide margin:**

```
volume                                 declared    actual   replicas   used%
prometheus-kube-prometheus-stack        100.0 GiB  12.7 GiB     2       12.7%
```

That is ~140 GiB of cluster scheduling reserved for ~17 GiB of block allocation,
and one of its two replicas sits on the saturated node.

### Why this is a create-new + migrate + cutover, not a resize

**Longhorn can only EXPAND a volume, never shrink it.** Upstream is explicit
(longhorn/longhorn#1132, "[FEATURE] Shrinking Volumes" — still open): expansion
requires the new size be strictly larger, and there is no shrink path at all.

This also kills the obvious "just restore the nightly backup into a smaller volume"
idea, and it is worth stating because it looks like it should work: **a Longhorn
restore creates the volume at the backup's recorded `volumeSize`.** Restoring
`backup-96e0ceca7fef4199` gives you another 100Gi volume. Block-level copy — backup/
restore, clone, `DataSource` — cannot change the geometry. The only mechanism that
can is a **file-level copy into a separately-created smaller volume**, which is what
§3 does.

### Two structural facts about the current wiring that this plan also fixes

Both were found by reading the live objects against git, and both are landmines:

1. **git and the cluster disagree about the storage class.** `helmvalues.yaml` line
   182 declares `storageClassName: longhorn`, but the live PVC is on
   **`longhorn-static`**, bound to a hand-made PV named
   `prometheus-kube-prometheus-stack` with `persistentVolumeReclaimPolicy: Retain`
   and `volumeHandle: prometheus-kube-prometheus-stack`. A StatefulSet
   `volumeClaimTemplate` is immutable, so the values edit never reached the live
   PVC — it has been inert since. **Consequence if left alone:** the day that PVC is
   ever deleted (which this plan does, deliberately and once), the StatefulSet would
   regenerate it as a *dynamic* `longhorn` PVC — a fresh, empty, 100Gi, `Delete`-
   reclaim volume, silently undoing everything here. The VCT must be corrected in the
   same operation.
2. **The single-replica intent in git was never applied either.** The same block
   carries `annotations: {longhorn.io/number-of-replicas: "1"}` with the comment
   *"Prometheus data is ephemeral - use single replica to save space"*. The live
   Longhorn volume has `numberOfReplicas: 2`. Longhorn's CSI reads replica count
   from **StorageClass parameters**, not PVC annotations, and this is a static PV
   anyway — so the annotation has never done anything. **This plan deliberately does
   NOT act on it.** Dropping to 1 replica would free another 30 GiB and is a
   one-line, instantly-reversible change, but it lowers Prometheus's durability to
   "one node loss = TSDB gone", which is precisely the moment you most want metrics.
   That is an operator DECISION about durability posture, not a capacity task —
   raised in §6 as a follow-up, not folded in here.

### The target size, argued from the actual retention config

The brief asked whether retention is time-based with no size cap, and whether setting
`retentionSize` is the real fix. **It is already set, and that is what makes
right-sizing safe at all.** Verified against the running process, not the values file
(`/api/v1/status/flags`, 2026-09-06):

```
storage.tsdb.retention.time = 1w
storage.tsdb.retention.size = 20GiB
walCompression               = true (snappy)
storage.tsdb.max-block-duration = 16h48m
```

Measured working set (`/api/v1/query`, same session):

| quantity | value |
|---|---|
| filesystem used on `/prometheus` (`kubelet_volume_stats_used_bytes`) | 8,822,775,808 B = **8.22 GiB** |
| filesystem capacity (`kubelet_volume_stats_capacity_bytes`) | 105,358,004,224 B = 98.12 GiB |
| persisted blocks (`prometheus_tsdb_storage_blocks_bytes`) | 8,257,146,775 B = 7.69 GiB |
| WAL (`prometheus_tsdb_wal_storage_size_bytes`) | 495,333,427 B = 472 MiB |
| head chunks (`prometheus_tsdb_head_chunks_storage_size_bytes`) | 79,989,172 B = 76 MiB |
| head series | 228,649 |
| ingest rate | 7,105 samples/s → **1.92 bytes/sample** |
| oldest sample (`prometheus_tsdb_lowest_timestamp_seconds`) | 2026-08-30T06:00:00Z |

`count(up)` evaluated at now−6.8d returns `74`; at now−8d returns empty. So **time
retention binds first**: 7 days costs 8.22 GiB, and the 20 GiB size cap has never
fired. There is **no remote_write, no Thanos, no long-term store** — grep of
`helmvalues.yaml` for `remoteWrite|thanos` returns nothing. 7 days is all the history
that exists anywhere.

Upstream's sizing rule (prometheus.io/docs/prometheus/latest/storage/) is the number
to design against, not today's usage:

> "Only the persistent blocks are deleted to honor this retention although WAL and
> m-mapped chunks are counted in the total size."
>
> "At present, we recommend setting the retention size to, at most, 80-85% of your
> allocated Prometheus disk space. The remaining 15-20% buffer covers the temporary
> extra space required by in-progress compactions." … "both the source blocks and the
> new compacted block must coexist on disk, so on-disk size can briefly exceed the
> retention size limit."
>
> "If both time and size retention policies are specified, whichever triggers first
> will be used."

Working it through:

- Required filesystem ≥ `retentionSize / 0.80` = 20 GiB / 0.80 = **25.0 GiB**.
- Longhorn + ext4 usable overhead measured here: 98.12 GiB usable on a 100Gi volume
  = **98.1%**. So required declared size ≥ 25.0 / 0.981 = **25.5 Gi** minimum.
- **Choose 30Gi.** Usable ≈ 29.4 GiB → `retentionSize` is **68% of allocated disk**,
  comfortably inside the 80–85% ceiling, leaving ~9.4 GiB of slack for the largest
  compaction (max block 16h48m ≈ 0.83 GiB of source, roughly doubled transiently) and
  for series growth.
- **Growth headroom:** at 1.92 B/sample, series could roughly **double to ~460k**
  (7d ≈ 15.4 GiB) and still sit under both the 20 GiB cap and 80% of 29.4 GiB. Past
  that point size retention starts trimming the oldest blocks: effective retention
  shortens below 7d, but **the disk never fills**. That is the correct failure mode,
  and it is the reason `retentionSize: 20GB` must stay where it is rather than being
  lowered to squeeze the volume further.
- **Do not size to observed usage.** A 12Gi or 16Gi volume would put the 20 GiB cap
  *above* the disk, making the disk the binding constraint — Prometheus would hit
  ENOSPC before its own size retention ever evicted a block. And because Longhorn
  expands but never shrinks, being generous once is cheap and being tight is a repeat
  of this whole exercise.

**Target: 30Gi (32,212,254,720 bytes), 2 replicas, `retention`/`retentionSize`
unchanged.**

### Expected end state (this is the point of the exercise — verify it in §4)

70 GiB freed per replica, two replicas, one on each of the loaded nodes:

| node | scheduled before | scheduled after | headroom before | **headroom after** | committed |
|---|---|---|---|---|---|
| k8s-nuc14-01 | 567.0 GiB | 567.0 GiB (unchanged) | 312.9 GiB | 312.9 GiB | 64.4% |
| k8s-nuc14-02 | 840.0 GiB | **770.0 GiB** | 39.9 GiB | **109.9 GiB** | 95.5% → **87.5%** |
| k8s-nuc14-03 | 744.0 GiB | **674.0 GiB** | 135.9 GiB | **205.9 GiB** | 84.6% → 76.6% |

Cluster declared 1063.0 → **993.0 GiB**; utilisation 18.6% → 19.8%.

This does **not** make node 02 comfortable in absolute terms (87.5% committed is
still high) — it makes it *safe*, moving it from 39.9 GiB of headroom (less than one
median volume) to 109.9 GiB. The remaining fix is the follow-up list in §6.

### Migrate the history, or start fresh? — RECOMMENDATION: MIGRATE

Both are legitimate. Stated honestly, then decided:

**Option B — start fresh, accept the gap.** Cheaper: no copy job, ~10 min of
downtime instead of ~20, one fewer failure mode. What is actually lost:

- **At most 7 days of metrics** (2026-08-30T06:00Z → now). Not "years of history" —
  7d retention is the ceiling and nothing else stores these series. That is a much
  smaller loss than it sounds.
- **All 5 SLOs degrade for a full 7 days.** Every enabled row in `slo_definitions`
  (`internal-dns-resolution`, `internal-ingress-availability`,
  `longhorn-volume-health`, `mosquitto-broker-up`, `unifi-device-availability`) uses a
  **7d window**. `slo-check.py` would compute each over a partial window and report
  compliance numbers that are arithmetically fine and epistemically worthless — and
  `longhorn-volume-health` is precisely the SLO you would want intact on the day you
  perturb Longhorn.
- **24 hours of alert blindness on the long-window rules**, which is the part that
  actually bites. `ContainerMemoryPredictedOOM` and its sibling both use
  `predict_linear(container_memory_rss[24h], …)` (container-memory-alerts.yaml:147,
  167) and `LonghornHighVolumeLatencyDaily` uses `max_over_time(...[24h])`
  (longhorn-alerts.yaml:254). These do not fail loudly on an empty window — they go
  **inert**, which is the exact failure shape `project_inert_alert_rules_trap` is
  about. A rule matching no series sits at `state=inactive` and looks healthy.
- Grafana panels wider than ~1h show a wall for a week.

**Option A — migrate the TSDB (RECOMMENDED).** The working set is **8.22 GiB** of
mostly-large sequential block files, copied between two Longhorn volumes attached to
the same node. That is on the order of **1–3 minutes of actual copying**, and it buys
back every one of the costs above. It adds roughly 10 minutes to the outage and one
verifiable failure mode (an incomplete copy), and that failure mode is checked
*before* anything is deleted, while the old volume is still authoritative and the
abort is free.

**Recommendation: Option A.** The deciding factor is not the dashboards — it is that
Option B trades a 10-minute saving for a 24-hour degradation of OOM-prediction
alerting and a 7-day hole in SLO measurement, incurred on the same day we are moving
storage around. Paying 10 minutes to avoid that is obviously correct.

**Option B remains the in-window fallback**: if the copy job fails or its verification
gate does not go green (Step 7), do **not** debug it during the outage — abort to
Option B by starting Prometheus on the empty 30Gi volume (§5, path R2). Same end
state for capacity, only the history is lost. The old volume is retained either way,
so Option B is reversible too.

### Why `risk: high`

- The PVC is **deleted and recreated**. Delete/recreate on a bound PVC is the highest-
  consequence step in this repo's storage vocabulary. It is safe *here* only because
  the PV is `persistentVolumeReclaimPolicy: Retain` (verified on the live object) —
  under `Delete` this same sequence would destroy the rollback.
- The **StatefulSet is deleted** and rebuilt by prometheus-operator.
- **Alerting and collection are down cluster-wide** for the duration (quantified
  below).
- `touches.shared` includes `longhorn` — per `runbooks/autonomy-policy.yaml`
  (`forbid_shared: [storage, longhorn]`) this can never derive AUTO-*, and
  `rollback_class: backup-restore` puts it at HUMAN-GATED regardless. Correct.

Note for the reader who wants to argue this down: no *software version* changes
anywhere in this plan. The risk is entirely in the storage choreography.

### Blast radius: what is blind, and for how long

While `prometheus-kube-prometheus-stack-0` is down:

- **No metric collection.** All 75 scrape targets go unscraped. A gap appears in
  every series; it is permanent and will be visible in dashboards forever.
- **No rule evaluation.** All 110 rule groups / 446 rules stop. Nothing fires,
  nothing resolves.
- **Alertmanager silences are pointless.** Alertmanager stays up and healthy but
  receives nothing — the *source* is down, not noisy. Silencing a source that emits
  nothing accomplishes nothing; do not create any.
- **Nothing external will page about it.** The `Watchdog` alert routes to the `null`
  receiver (alertmanager-telegram-config.yaml:24-28) and no external dead-man's-switch
  consumes it. So the outage is silent — which is convenient and also exactly why it
  must be time-boxed by a human rather than by an alarm.
- **Uptime Kuma is unaffected and keeps watching.** `uptime-kuma` in `monitoring` is
  an independent prober with its own notification path; external service availability
  continues to be monitored throughout. It is the safety net during the gap.
- **On return**, every rule's `for:` timer restarts from zero, and `absent()` guards
  may fire briefly during WAL replay. Expect a small burst of alert noise within ~10
  min of recovery; do not treat the first two minutes of post-start alerts as signal.

**Duration:** target **15–25 minutes** of Prometheus downtime (Steps 5→11).
**Budget 30 minutes. Hard abort at 40** — at 40 minutes, stop debugging and take
rollback path R1 or R2 in §5; both restore service in under 10 minutes.

**Pause nothing else, but do not START anything else.** Specifically, for the
duration and for ~15 minutes after: do **not** run an operation sweep, do **not**
run a maintenance window (Step 0 safe-update apply health-gates on Prometheus and
would read the outage as a regression and auto-revert a healthy batch), and do not
merge anything that a health gate will check. Nothing needs to be scaled down or
suspended.

### Is same-day execution safe? — YES

The brief asked me to say plainly if it is not. It is. The reasoning:

- The mechanism needs **no fresh backup to be taken** — the rollback is the existing
  100Gi volume, left physically intact and detached. Nothing has to be dumped,
  uploaded, or waited on. (The nightly Longhorn backup at 2026-09-06T03:06:14Z exists
  as a second floor and is 6 hours old, but the plan does not depend on it.)
- The copy is **8.22 GiB**, not hours.
- There is **no soak requirement before the cutover**. The soak in this plan is
  *after* the cutover, and it is a soak on *when the old volume may be deleted* — an
  action that appears nowhere in today's steps.
- The operator is **present and attended**, which is what a deliberate 20-minute
  monitoring blackout requires.

The one thing that must not be compressed: **the 7-day soak before reclaiming the old
volume.** Deleting the 100Gi volume today would turn a fully reversible operation into
a one-way one, for zero additional capacity benefit (its scheduling reservation is
already released the moment the volume detaches and the replicas are removed — see
§4's node check, which is what actually proves the exercise landed).

---

## 2. Pre-checks

All read-only. Every one must pass before Step 1.

```bash
cd /Users/mu/code/cberg-home-nextgen

# P1 — cluster is quiet: no failing Flux objects, nothing mid-reconcile
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
flux get helmreleases -A   | awk 'NR==1 || $5 != "True"'

# P2 — no OTHER maintenance in flight and the worktree is clean enough to commit from
git -C /Users/mu/code/cberg-home-nextgen status --short
git -C /Users/mu/code/cberg-home-nextgen log --oneline -3

# P3 — the live storage objects are what this plan assumes.
#      MUST print: reclaim=Retain  class=longhorn-static  handle=prometheus-kube-prometheus-stack
kubectl get pv prometheus-kube-prometheus-stack \
  -o jsonpath='reclaim={.spec.persistentVolumeReclaimPolicy} class={.spec.storageClassName} handle={.spec.csi.volumeHandle}{"\n"}'
# ^ STOP THE PLAN if reclaim is not Retain. Under Delete, Step 8 destroys the rollback.

# P4 — the Longhorn volume is healthy and its replica placement is as assumed
kubectl get volume -n storage prometheus-kube-prometheus-stack \
  -o jsonpath='size={.spec.size} actual={.status.actualSize} replicas={.spec.numberOfReplicas} state={.status.state} robustness={.status.robustness} node={.spec.nodeID}{"\n"}'
kubectl get replicas.longhorn.io -n storage \
  -o custom-columns=NAME:.metadata.name,VOLUME:.spec.volumeName,NODE:.spec.nodeID \
  | grep prometheus-kube-prometheus-stack
# Expect: 2 replicas, one on k8s-nuc14-02 and one on k8s-nuc14-03.
# If BOTH are on the same node, the freed headroom lands differently than §1 predicts
# — recompute the end-state table before proceeding, do not abandon the plan.

# P5 — the name `prometheus-tsdb` is free at all three layers
kubectl get volume -n storage prometheus-tsdb 2>&1 | tail -1   # expect NotFound
kubectl get pv prometheus-tsdb 2>&1 | tail -1                   # expect NotFound
kubectl get pvc -n monitoring prometheus-tsdb-seed 2>&1 | tail -1  # expect NotFound

# P6 — node capacity baseline. RECORD THIS OUTPUT; §4 diffs against it.
kubectl get nodes.longhorn.io -n storage -o json | python3 -c "
import sys, json
G = 1024**3
for n in json.load(sys.stdin)['items']:
    for dn, dk in n['status'].get('diskStatus', {}).items():
        mx = dk.get('storageMaximum',0); sch = dk.get('storageScheduled',0)
        res = n['spec']['disks'].get(dn,{}).get('storageReserved',0)
        usable = mx - res
        print(f\"{n['metadata']['name']:14} scheduled={sch/G:7.1f}GiB usable={usable/G:7.1f}GiB headroom={(usable-sch)/G:7.1f}GiB committed={100*sch/usable:5.1f}%\")
"
# Expect (2026-09-06): 01 scheduled=567.0 headroom=312.9 | 02 scheduled=840.0 headroom=39.9 | 03 scheduled=744.0 headroom=135.9

# P7 — free physical space on nodes 02/03 must exceed 30 GiB each (the new replicas
#      are created BEFORE the old ones go away, so both coexist briefly)
kubectl get nodes.longhorn.io -n storage -o json | python3 -c "
import sys, json
G = 1024**3
for n in json.load(sys.stdin)['items']:
    for dn, dk in n['status'].get('diskStatus', {}).items():
        print(n['metadata']['name'], f\"physically_available={dk.get('storageAvailable',0)/G:.1f}GiB\")
"
# Expect ~350-415 GiB available on each. Anything under 40 GiB on node 02 -> STOP.
# NOTE: node 02 has 39.9 GiB of SCHEDULING headroom, which is less than the 30 GiB
# the new replica wants plus margin. Step 3 therefore creates the new volume with
# BOTH replicas allowed to land anywhere; if Longhorn cannot schedule it, the volume
# sits `Scheduled: False` and Step 3's gate catches it BEFORE any outage begins.

# P8 — Prometheus baseline. RECORD ALL OF IT; §4 compares against these numbers.
kubectl -n monitoring port-forward svc/kube-prometheus-stack-prometheus 19090:9090 >/tmp/pf-prom.log 2>&1 &
PF=$!; sleep 3
curl -s http://127.0.0.1:19090/api/v1/targets?state=active | python3 -c "
import sys,json; t=json.load(sys.stdin)['data']['activeTargets']
print('TARGETS total', len(t), 'up', sum(1 for x in t if x['health']=='up'))"
curl -s http://127.0.0.1:19090/api/v1/rules | python3 -c "
import sys,json; g=json.load(sys.stdin)['data']['groups']
print('RULES groups', len(g), 'rules', sum(len(x['rules']) for x in g))"
curl -s 'http://127.0.0.1:19090/api/v1/query?query=prometheus_tsdb_head_series' | python3 -c "
import sys,json; print('HEAD SERIES', json.load(sys.stdin)['data']['result'][0]['value'][1])"
curl -s 'http://127.0.0.1:19090/api/v1/query?query=prometheus_tsdb_lowest_timestamp_seconds' | python3 -c "
import sys,json,datetime
v=float(json.load(sys.stdin)['data']['result'][0]['value'][1])
print('OLDEST SAMPLE', datetime.datetime.fromtimestamp(v, datetime.UTC).isoformat())"
curl -s 'http://127.0.0.1:19090/api/v1/query?query=kubelet_volume_stats_used_bytes{persistentvolumeclaim=~".*prometheus-kube.*"}' | python3 -c "
import sys,json
for r in json.load(sys.stdin)['data']['result']: print('FS USED BYTES', r['value'][1])"
kill $PF
# Expect (2026-09-06 baseline): TARGETS 75/75 | RULES 110 groups / 446 rules |
# HEAD SERIES ~228,600 | OLDEST 2026-08-30T06:00:00Z | FS USED ~8,822,775,808
```

---

## 3. Steps

Timings are wall-clock estimates. **The outage starts at Step 5 and ends at Step 11.**
Steps 1–4 are entirely non-disruptive and fully reversible by deleting three objects —
the risk is front-loaded in the sense that everything that *can* go wrong structurally
(name collisions, scheduling failure on the new volume, a bad copy) is discovered
before Prometheus is touched.

### Step 1 — Suspend Flux for this app so ordering is ours (1 min, no impact)

```bash
flux suspend kustomization kube-prometheus-stack -n monitoring
flux suspend helmrelease   kube-prometheus-stack -n monitoring
flux get kustomizations -n monitoring kube-prometheus-stack
flux get helmreleases    -n monitoring kube-prometheus-stack
# both must show SUSPENDED=True
```

Why: the helmvalues ConfigMap edit and the PVC recreation must happen in a specific
order. An unsuspended Flux would re-apply the old values or race the operator.

### Step 2 — Land the git change (3 min, no impact — Flux is suspended)

Two file edits. Edit **only** these hunks.

**2a.** `kubernetes/apps/monitoring/kube-prometheus-stack/app/helmvalues.yaml` —
replace the `storageSpec` block (currently lines 175–185):

```yaml
        storageSpec:
          volumeClaimTemplate:
            spec:
              # RIGHT-SIZED 2026-09-06: 100Gi -> 30Gi. Longhorn schedules on DECLARED
              # size; 100Gi for an 8.2 GiB working set reserved ~140 GiB of cluster
              # scheduling across two replicas and pushed k8s-nuc14-02 to 95.5%
              # committed. 30Gi keeps retentionSize (20GiB) at 68% of allocated disk,
              # inside upstream's 80-85% compaction-headroom guidance.
              # Plan: runbooks/maintenance/plans/prometheus-volume-rightsize.md
              #
              # storageClassName CORRECTED longhorn -> longhorn-static: the live PVC
              # has ALWAYS been longhorn-static (StatefulSet volumeClaimTemplates are
              # immutable, so the earlier `longhorn` edit never took effect). Leaving
              # it as `longhorn` meant any future PVC delete would silently
              # regenerate a dynamic, EMPTY, Delete-reclaim 100Gi volume.
              #
              # volumeName pins the claim to the named static PV so the StatefulSet
              # can only ever re-bind to the intended volume.
              #
              # The old `longhorn.io/number-of-replicas: "1"` annotation is REMOVED,
              # not kept: Longhorn reads replica count from StorageClass parameters,
              # never from PVC annotations, so it was inert and read as an applied
              # setting that was not applied. Replica count now lives, visibly, on
              # the hand-applied Volume CR (longhorn-volume-prometheus-tsdb.yaml).
              storageClassName: longhorn-static
              volumeName: prometheus-tsdb
              resources:
                requests:
                  storage: 30Gi
```

`retention: 7d` and `retentionSize: 20GB` (lines 173–174) are **unchanged** — see §1.

**2b.** New file
`kubernetes/apps/monitoring/kube-prometheus-stack/app/prometheus-tsdb-pv.yaml`:

```yaml
---
apiVersion: v1
kind: PersistentVolume
metadata:
  name: prometheus-tsdb
spec:
  capacity:
    storage: 30Gi
  volumeMode: Filesystem
  accessModes:
    - ReadWriteOnce
  persistentVolumeReclaimPolicy: Retain
  storageClassName: longhorn-static
  csi:
    driver: driver.longhorn.io
    fsType: ext4
    volumeAttributes:
      numberOfReplicas: "2"
      staleReplicaTimeout: "30"
    volumeHandle: prometheus-tsdb
```

**2c.** New file
`kubernetes/apps/monitoring/kube-prometheus-stack/app/longhorn-volume-prometheus-tsdb.yaml`
— version-controlled source for the Longhorn Volume CR, **deliberately NOT added to
`kustomization.yaml`** and applied by hand (docs/sops/longhorn.md: the app
Kustomization's `targetNamespace` overrides `namespace: storage` and creates a broken
duplicate Longhorn ignores):

```yaml
---
# NOT in kustomization.yaml on purpose — hand-applied. See docs/sops/longhorn.md
# "The one cost of a static volume".
apiVersion: longhorn.io/v1beta2
kind: Volume
metadata:
  name: prometheus-tsdb
  namespace: storage
spec:
  size: "32212254720"      # 30Gi
  numberOfReplicas: 2
  dataEngine: v1
  dataLocality: best-effort
  accessMode: rwo
  frontend: blockdev
  migratable: false
  encrypted: false
  staleReplicaTimeout: 30
```

**2d.** Add the PV (only the PV) to
`kubernetes/apps/monitoring/kube-prometheus-stack/app/kustomization.yaml`, next to
`./grafana-pvc.yaml`:

```yaml
  - ./prometheus-tsdb-pv.yaml
```

**2e.** Commit with `--only` (shared worktree — CLAUDE.md rule; a bare `git add` can
pick up another session's staged hunk):

```bash
cd /Users/mu/code/cberg-home-nextgen
cat > /tmp/prom-rightsize-msg.txt <<'EOF'
refactor(monitoring): right-size prometheus TSDB volume 100Gi -> 30Gi

Longhorn schedules on DECLARED size and storageOverProvisioningPercentage is
100, so a 100Gi volume holding 8.2 GiB reserved ~140 GiB of cluster scheduling
across 2 replicas and pushed k8s-nuc14-02 to 95.5% committed (39.9 GiB
headroom) while 415 GB sat physically free. Longhorn cannot shrink a volume,
so this creates prometheus-tsdb (30Gi) and cuts the StatefulSet over to it.

30Gi is derived, not guessed: retentionSize is 20GiB and upstream recommends
retention size <= 80-85% of allocated disk for compaction headroom. 20 GiB /
0.80 = 25.0 GiB usable; ext4-on-Longhorn usable is 98.1% of declared; 30Gi
gives 29.4 GiB usable = 68% committed, with room for a doubling of the
current 228k head series. retention 7d / retentionSize 20GB are unchanged.

Also corrects two long-standing drifts in the same block: storageClassName
said `longhorn` while the live PVC has always been `longhorn-static` (an
immutable volumeClaimTemplate meant the edit never applied), and a
longhorn.io/number-of-replicas annotation that Longhorn never reads.

The old 100Gi PV/volume is retained, detached and intact, as the rollback.

Plan: runbooks/maintenance/plans/prometheus-volume-rightsize.md

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_012bXdxrZGGHNy5e4RnF6seD
EOF

git commit --only \
  kubernetes/apps/monitoring/kube-prometheus-stack/app/helmvalues.yaml \
  kubernetes/apps/monitoring/kube-prometheus-stack/app/prometheus-tsdb-pv.yaml \
  kubernetes/apps/monitoring/kube-prometheus-stack/app/longhorn-volume-prometheus-tsdb.yaml \
  kubernetes/apps/monitoring/kube-prometheus-stack/app/kustomization.yaml \
  -F /tmp/prom-rightsize-msg.txt

git show --stat HEAD    # every file here must be one of the four above
git push
```

### Step 3 — Create the new Longhorn volume and PV (3 min, no impact)

```bash
cd /Users/mu/code/cberg-home-nextgen
kubectl apply -f kubernetes/apps/monitoring/kube-prometheus-stack/app/longhorn-volume-prometheus-tsdb.yaml
kubectl apply -f kubernetes/apps/monitoring/kube-prometheus-stack/app/prometheus-tsdb-pv.yaml
```

**GATE — this is the last cheap abort point. Do not proceed until it is green:**

```bash
kubectl get volume -n storage prometheus-tsdb \
  -o jsonpath='state={.status.state} robustness={.status.robustness}{"\n"}'
kubectl get volume -n storage prometheus-tsdb \
  -o json | python3 -c "
import sys,json
for c in json.load(sys.stdin)['status']['conditions']:
    if c['type'] == 'Scheduled':
        print('Scheduled =', c['status'], c.get('reason',''), c.get('message',''))
"
kubectl get pv prometheus-tsdb -o jsonpath='{.status.phase}{"\n"}'   # Available
kubectl get replicas.longhorn.io -n storage \
  -o custom-columns=NAME:.metadata.name,VOLUME:.spec.volumeName,NODE:.spec.nodeID \
  | grep prometheus-tsdb
```

Required: `state=detached`, **`Scheduled = True`**, PV phase `Available`, and two
replicas with real `nodeID`s. If `Scheduled = False` /
`ReplicaSchedulingFailure`, node 02 could not take the new replica alongside the old
one — **abort here** (`kubectl delete volume -n storage prometheus-tsdb; kubectl
delete pv prometheus-tsdb`), nothing has been disturbed, and see §6 for the
sequencing alternative.

### Step 4 — Create the seed PVC (1 min, no impact)

```bash
kubectl apply -f - <<'EOF'
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: prometheus-tsdb-seed
  namespace: monitoring
  labels:
    app.kubernetes.io/part-of: prometheus-volume-rightsize
spec:
  accessModes: [ReadWriteOnce]
  resources:
    requests:
      storage: 30Gi
  storageClassName: longhorn-static
  volumeName: prometheus-tsdb
EOF

kubectl -n monitoring get pvc prometheus-tsdb-seed   # must reach Bound
```

### Step 5 — STOP Prometheus (2 min) — **OUTAGE STARTS HERE. Note the time.**

```bash
date -u +%Y-%m-%dT%H:%M:%SZ   # record: outage start

# Pause the operator so it cannot recreate the StatefulSet under us.
kubectl -n monitoring patch prometheus kube-prometheus-stack \
  --type merge -p '{"spec":{"paused":true}}'
kubectl -n monitoring get prometheus kube-prometheus-stack -o jsonpath='paused={.spec.paused}{"\n"}'

# Delete the StatefulSet. Default cascade: the pod goes, the PVC stays
# (StatefulSets never delete their PVCs here).
kubectl -n monitoring delete statefulset prometheus-kube-prometheus-stack

# Wait for the pod to be gone and the old volume to detach.
kubectl -n monitoring get pod prometheus-kube-prometheus-stack-0 2>&1 | tail -1   # NotFound
kubectl get volume -n storage prometheus-kube-prometheus-stack \
  -o jsonpath='{.status.state}{"\n"}'    # must reach: detached
kubectl -n monitoring get pvc prometheus-kube-prometheus-stack-db-prometheus-kube-prometheus-stack-0
# ^ still Bound. Good.
```

`spec.paused` is the documented prometheus-operator mechanism for exactly this
(prometheus-operator.dev/docs/platform/storage/: *"update the `spec.paused` field to
`true` (to prevent the operator from recreating the StatefulSet)"*). Without it the
operator recreates the StatefulSet mid-copy and re-attaches the old PVC.

### Step 6 — Copy the TSDB (3–6 min)

```bash
kubectl apply -f - <<'EOF'
---
apiVersion: batch/v1
kind: Job
metadata:
  name: prometheus-tsdb-copy
  namespace: monitoring
  labels:
    app.kubernetes.io/part-of: prometheus-volume-rightsize
spec:
  backoffLimit: 0
  ttlSecondsAfterFinished: 7200
  template:
    spec:
      restartPolicy: Never
      securityContext:
        runAsUser: 0
      containers:
        - name: copy
          image: docker.io/library/alpine:3.22
          command: ["/bin/sh", "-c"]
          args:
            - |
              set -eux
              echo "--- SOURCE ---"
              ls -la /src
              du -sb /src
              find /src -type f | wc -l
              echo "--- COPY ---"
              cp -a /src/. /dst/
              sync
              echo "--- OWNERSHIP (prometheus runs 1000:2000) ---"
              chown -R 1000:2000 /dst
              sync
              echo "--- DEST ---"
              ls -la /dst
              du -sb /dst
              find /dst -type f | wc -l
              echo "--- DONE ---"
          volumeMounts:
            - { name: src, mountPath: /src }
            - { name: dst, mountPath: /dst }
      volumes:
        - name: src
          persistentVolumeClaim:
            claimName: prometheus-kube-prometheus-stack-db-prometheus-kube-prometheus-stack-0
        - name: dst
          persistentVolumeClaim:
            claimName: prometheus-tsdb-seed
EOF

kubectl -n monitoring wait --for=condition=complete job/prometheus-tsdb-copy --timeout=900s
kubectl -n monitoring logs job/prometheus-tsdb-copy
```

If the Job does not complete within 15 minutes, or `wait` returns failed: **abort to
rollback path R2 in §5** (start on the empty volume, accept the 7-day gap). Do not
debug during the outage.

### Step 7 — GATE: prove the copy is complete (2 min) — **the backup_gate**

This runs while the source is still authoritative and the abort is still free. It is
the CONTENTS assertion required by
`runbooks/maintenance/plans/README.md` §"Verification must assert CONTENTS, not SHAPE"
— a shape check ("the Job succeeded", "the PVC is Bound") would go green on an empty
destination.

```bash
kubectl apply -f - <<'EOF'
---
apiVersion: batch/v1
kind: Job
metadata:
  name: prometheus-tsdb-verify
  namespace: monitoring
  labels:
    app.kubernetes.io/part-of: prometheus-volume-rightsize
spec:
  backoffLimit: 0
  ttlSecondsAfterFinished: 7200
  template:
    spec:
      restartPolicy: Never
      securityContext:
        runAsUser: 0
      containers:
        - name: verify
          image: docker.io/library/alpine:3.22
          command: ["/bin/sh", "-c"]
          args:
            - |
              set -eu
              fail=0
              # 1. identical sorted TSDB block-directory listing (the actual history)
              ls -1 /src | sort > /tmp/src.list
              ls -1 /dst | sort > /tmp/dst.list
              echo "=== TOP-LEVEL DIFF (must be empty) ==="
              diff /tmp/src.list /tmp/dst.list || fail=1
              echo "=== BLOCK DIRS: src=$(ls -1d /src/01* 2>/dev/null | wc -l) dst=$(ls -1d /dst/01* 2>/dev/null | wc -l) ==="
              [ "$(ls -1d /src/01* 2>/dev/null | wc -l)" = "$(ls -1d /dst/01* 2>/dev/null | wc -l)" ] || fail=1
              [ "$(ls -1d /dst/01* 2>/dev/null | wc -l)" -gt 0 ] || { echo "FLOOR FAILED: zero blocks on dst"; fail=1; }
              # 2. byte-exact size
              s=$(du -sb /src | cut -f1); d=$(du -sb /dst | cut -f1)
              echo "=== BYTES src=$s dst=$d ==="
              [ "$s" = "$d" ] || fail=1
              # 3. identical file count
              sf=$(find /src -type f | wc -l); df=$(find /dst -type f | wc -l)
              echo "=== FILES src=$sf dst=$df ==="
              [ "$sf" = "$df" ] || fail=1
              # 4. the WAL made it
              [ -d /dst/wal ] || { echo "no /dst/wal"; fail=1; }
              [ "$fail" = "0" ] && echo "GATE: PASS" || { echo "GATE: FAIL"; exit 1; }
          volumeMounts:
            - { name: src, mountPath: /src }
            - { name: dst, mountPath: /dst }
      volumes:
        - name: src
          persistentVolumeClaim:
            claimName: prometheus-kube-prometheus-stack-db-prometheus-kube-prometheus-stack-0
        - name: dst
          persistentVolumeClaim:
            claimName: prometheus-tsdb-seed
EOF

kubectl -n monitoring wait --for=condition=complete job/prometheus-tsdb-verify --timeout=300s
kubectl -n monitoring logs job/prometheus-tsdb-verify | tail -20
```

**Required: `GATE: PASS`.** Anything else → rollback path R1 (§5): nothing has been
deleted yet, so simply unpause and restart on the old volume.

```bash
# Gate passed — release both PVCs from the copy jobs
kubectl -n monitoring delete job prometheus-tsdb-copy prometheus-tsdb-verify
```

### Step 8 — Release the new PV and delete the old PVC (3 min)

`persistentVolumeReclaimPolicy: Retain` on **both** PVs is what makes this safe; it was
asserted in pre-check P3.

```bash
# 8a. Free the new PV from the seed claim
kubectl -n monitoring delete pvc prometheus-tsdb-seed
kubectl get pv prometheus-tsdb -o jsonpath='{.status.phase}{"\n"}'      # -> Released
kubectl patch pv prometheus-tsdb --type json -p '[{"op":"remove","path":"/spec/claimRef"}]'
kubectl get pv prometheus-tsdb -o jsonpath='{.status.phase}{"\n"}'      # -> Available

# 8b. Delete the OLD PVC. The PV is Retain, so this does NOT delete data.
kubectl -n monitoring delete pvc prometheus-kube-prometheus-stack-db-prometheus-kube-prometheus-stack-0

# 8c. CONFIRM the rollback survived. Both lines must be non-empty and correct.
kubectl get pv prometheus-kube-prometheus-stack \
  -o jsonpath='phase={.status.phase} reclaim={.spec.persistentVolumeReclaimPolicy}{"\n"}'
#   expect: phase=Released reclaim=Retain
kubectl get volume -n storage prometheus-kube-prometheus-stack \
  -o jsonpath='state={.status.state} actual={.status.actualSize} robustness={.status.robustness}{"\n"}'
#   expect: state=detached, actual ~13,580,000,000, robustness=healthy
```

> **Do NOT delete `pv/prometheus-kube-prometheus-stack` or
> `volume/prometheus-kube-prometheus-stack`. Not today. Not in this window.**
> They are the rollback. Reclaiming them is a separate action after the soak — §5.

### Step 9 — Resume Flux and let the operator rebuild (3 min)

```bash
flux resume kustomization kube-prometheus-stack -n monitoring
flux resume helmrelease   kube-prometheus-stack -n monitoring

# The Helm upgrade re-renders the Prometheus CR from the NEW helmvalues and, because
# `paused` is a manual patch not present in the values, drops it — so the operator
# un-pauses and rebuilds the StatefulSet from the new volumeClaimTemplate in one move.
flux get helmreleases -n monitoring kube-prometheus-stack

# Belt and braces — assert the CR actually picked up the new storage spec:
kubectl -n monitoring get prometheus kube-prometheus-stack -o jsonpath='paused={.spec.paused} sc={.spec.storage.volumeClaimTemplate.spec.storageClassName} vol={.spec.storage.volumeClaimTemplate.spec.volumeName} size={.spec.storage.volumeClaimTemplate.spec.resources.requests.storage}{"\n"}'
# expect: paused=  sc=longhorn-static  vol=prometheus-tsdb  size=30Gi
# If `paused=true` still shows, clear it explicitly:
#   kubectl -n monitoring patch prometheus kube-prometheus-stack --type json \
#     -p '[{"op":"remove","path":"/spec/paused"}]'
```

### Step 10 — Watch it come back (3–5 min)

```bash
kubectl -n monitoring get sts prometheus-kube-prometheus-stack -w    # ^C when 1/1
kubectl -n monitoring get pvc prometheus-kube-prometheus-stack-db-prometheus-kube-prometheus-stack-0
# MUST show: Bound / VOLUME prometheus-tsdb / CAPACITY 30Gi / longhorn-static
kubectl -n monitoring get pod prometheus-kube-prometheus-stack-0 -o wide
kubectl -n monitoring logs prometheus-kube-prometheus-stack-0 -c prometheus | grep -iE 'WAL|replay|Server is ready|error' | tail -20
```

WAL replay for ~228k series takes well under a minute. Watch for
`msg="Server is ready to receive web requests."`.

### Step 11 — **OUTAGE ENDS.** Record the duration.

```bash
date -u +%Y-%m-%dT%H:%M:%SZ    # record: outage end; subtract Step 5's timestamp
```

Then go straight to §4. If total elapsed from Step 5 exceeds **40 minutes** at any
point without a Ready pod, stop and take §5.

---

## 4. Verification

### 4.1 Shape floor (necessary, nowhere near sufficient)

```bash
flux get kustomizations -n monitoring kube-prometheus-stack   # Ready=True
flux get helmreleases   -n monitoring kube-prometheus-stack   # Ready=True
kubectl -n monitoring get pod prometheus-kube-prometheus-stack-0   # 2/2 Running, 0 restarts
kubectl get volume -n storage prometheus-tsdb \
  -o jsonpath='size={.spec.size} state={.status.state} robustness={.status.robustness}{"\n"}'
# expect: size=32212254720 state=attached robustness=healthy
```

### 4.2 CONTENTS ASSERTION — the history survived the move

> **CONTENTS ASSERTION: the pre-cutover metric history is queryable on the NEW
> volume** — measured by a range query at `now − 6.8d` returning a non-empty result
> whose value matches the pre-cutover baseline from P8, and by
> `prometheus_tsdb_lowest_timestamp_seconds` still reporting 2026-08-30T06:00:00Z.
> A pod-Ready / targets-up check would go green on a completely empty TSDB; this
> would not.

```bash
kubectl -n monitoring port-forward svc/kube-prometheus-stack-prometheus 19090:9090 >/tmp/pf-prom.log 2>&1 &
PF=$!; sleep 3

echo "=== A. oldest sample still ~2026-08-30T06:00Z (NOT today) ==="
curl -s 'http://127.0.0.1:19090/api/v1/query?query=prometheus_tsdb_lowest_timestamp_seconds' | python3 -c "
import sys,json,datetime
v=float(json.load(sys.stdin)['data']['result'][0]['value'][1])
print(datetime.datetime.fromtimestamp(v, datetime.UTC).isoformat())"

echo "=== B. history is QUERYABLE 6.8 days back (must return ~74, not empty) ==="
curl -s -G --data-urlencode 'query=count(up)' \
  --data-urlencode "time=$(python3 -c 'import time;print(int(time.time()-6.8*86400))')" \
  http://127.0.0.1:19090/api/v1/query; echo

echo "=== C. continuity across the cutover: samples per hour over the last 12h ==="
echo "    (expect a single short dip at the outage, NOT a wall)"
curl -s -G --data-urlencode 'query=count(up)' \
  --data-urlencode "start=$(python3 -c 'import time;print(int(time.time()-12*3600))')" \
  --data-urlencode "end=$(python3 -c 'import time;print(int(time.time()))')" \
  --data-urlencode 'step=300' \
  http://127.0.0.1:19090/api/v1/query_range | python3 -c "
import sys,json,datetime
r=json.load(sys.stdin)['data']['result']
if not r: print('EMPTY — CONTINUITY FAILED'); raise SystemExit(1)
vals=r[0]['values']
print('points:',len(vals),'expected ~144 minus the outage')
prev=None
for ts,_ in vals:
    if prev is not None and ts-prev > 600:
        print('GAP', datetime.datetime.fromtimestamp(prev, datetime.UTC).isoformat(),
              '->', datetime.datetime.fromtimestamp(ts, datetime.UTC).isoformat(),
              f'({(ts-prev)/60:.0f} min)')
    prev=ts
print('^ exactly ONE gap, matching the recorded outage window, is the expected result')"
```

If (A) shows today's date or (B) is empty, the copy did not land and Prometheus
started on an empty volume. That is Option B's outcome arrived at by accident —
recoverable via §5 path R1 (the old volume still has everything). Decide explicitly
rather than accepting it silently.

### 4.3 Collection and rule evaluation are fully back

```bash
echo "=== targets: must be 75 / 75 ==="
curl -s http://127.0.0.1:19090/api/v1/targets?state=active | python3 -c "
import sys,json; t=json.load(sys.stdin)['data']['activeTargets']
up=sum(1 for x in t if x['health']=='up')
print('total',len(t),'up',up)
for x in t:
    if x['health']!='up': print('  DOWN:', x['labels'].get('job'), x['labels'].get('instance'), x.get('lastError'))"

echo "=== rule groups: must be 110 groups / 446 rules ==="
curl -s http://127.0.0.1:19090/api/v1/rules | python3 -c "
import sys,json; g=json.load(sys.stdin)['data']['groups']
print('groups',len(g),'rules',sum(len(x['rules']) for x in g))
bad=[x['name'] for x in g if x.get('lastError')]
print('groups with lastError:', bad or 'none')"
```

Both counts must match the P8 baseline exactly. **Read via `/api/v1/rules`, not by
counting PrometheusRule objects** — a rule missing the `release:
kube-prometheus-stack` label is never loaded and produces no error anywhere
(`project_prometheusrule_silent_ignore`). This plan does not touch rule labels, so a
drop here means the HelmRelease re-rendered with different selectors, not a labelling
bug.

```bash
echo "=== retention config unchanged ==="
curl -s http://127.0.0.1:19090/api/v1/status/runtimeinfo | python3 -c "
import sys,json; print('storageRetention =', json.load(sys.stdin)['data']['storageRetention'])"
# expect: 1w or 20GiB   (unchanged — this plan changes the DISK, not the policy)

echo "=== headroom on the new disk ==="
curl -s 'http://127.0.0.1:19090/api/v1/query?query=kubelet_volume_stats_used_bytes{persistentvolumeclaim=~".*prometheus-kube.*"}' | python3 -c "
import sys,json
for r in json.load(sys.stdin)['data']['result']:
    print('used', int(r['value'][1])/2**30, 'GiB')"
curl -s 'http://127.0.0.1:19090/api/v1/query?query=kubelet_volume_stats_capacity_bytes{persistentvolumeclaim=~".*prometheus-kube.*"}' | python3 -c "
import sys,json
for r in json.load(sys.stdin)['data']['result']:
    print('capacity', int(r['value'][1])/2**30, 'GiB')"
# expect: used ~8.2 GiB, capacity ~29.4 GiB -> ~28% full. If used/capacity > 0.70,
# the sizing argument in §1 was wrong somewhere; expand (Longhorn CAN expand) rather
# than repeating this whole migration.
kill $PF
```

### 4.4 Storage round-trip through the mounted PVC

Per README's storage row: Longhorn's own `state=attached / robustness=healthy` says
nothing about whether anything can still *use* the volume. Prometheus writing new
samples is itself the round-trip, and 4.2(C) proves it — but assert it directly:

```bash
kubectl -n monitoring logs prometheus-kube-prometheus-stack-0 -c prometheus --since=5m \
  | grep -iE 'error|failed|no space|read-only' | grep -v 'level=info' | tail -20
# expect: nothing
```

### 4.5 Grafana datasources still alive

```bash
kubectl -n monitoring get pod -l app.kubernetes.io/name=grafana
kubectl -n monitoring logs deploy/grafana -c grafana --since=10m 2>/dev/null \
  | grep -iE 'datasource|prometheus' | tail -20
```

Then open Grafana and load one Prometheus-backed dashboard with a **7-day** range.
Panels must render pre-cutover data with a single narrow gap at the outage. A dashboard
that renders only post-cutover data means the copy did not land.

### 4.6 **THE POINT OF THE EXERCISE** — node scheduling actually moved

This is the assertion that distinguishes "Prometheus came back up" from "we solved the
capacity problem". Re-run pre-check P6 verbatim:

```bash
kubectl get nodes.longhorn.io -n storage -o json | python3 -c "
import sys, json
G = 1024**3
for n in json.load(sys.stdin)['items']:
    for dn, dk in n['status'].get('diskStatus', {}).items():
        mx = dk.get('storageMaximum',0); sch = dk.get('storageScheduled',0)
        res = n['spec']['disks'].get(dn,{}).get('storageReserved',0)
        usable = mx - res
        print(f\"{n['metadata']['name']:14} scheduled={sch/G:7.1f}GiB usable={usable/G:7.1f}GiB headroom={(usable-sch)/G:7.1f}GiB committed={100*sch/usable:5.1f}%\")
"
```

**Required end state:**

| node | scheduled | headroom | committed |
|---|---|---|---|
| k8s-nuc14-01 | 567.0 GiB (unchanged) | 312.9 GiB | 64.4% |
| **k8s-nuc14-02** | **770.0 GiB** (was 840.0) | **109.9 GiB** (was 39.9) | **87.5%** (was 95.5%) |
| **k8s-nuc14-03** | **674.0 GiB** (was 744.0) | **205.9 GiB** (was 135.9) | **76.6%** (was 84.6%) |

Tolerance: ±3 GiB per node for concurrent unrelated volume churn. **If node 02's
headroom has not risen by ~70 GiB, the old replicas have not been released** —
check that the old volume is `detached` and that its replicas are gone:

```bash
kubectl get replicas.longhorn.io -n storage \
  -o custom-columns=NAME:.metadata.name,VOLUME:.spec.volumeName,NODE:.spec.nodeID \
  | grep -E 'prometheus-kube-prometheus-stack|prometheus-tsdb'
```

A **detached** volume still holds its replicas on disk and — importantly — Longhorn
still counts them against `storageScheduled`. **So the ~70 GiB per node is expected
to appear only after the old volume's replicas are removed, which happens when the
old volume is deleted at the END of the soak, not today.**

**Therefore the honest same-day expectation is:**

| | today, post-cutover | after the soak ends and the old volume is deleted |
|---|---|---|
| nuc14-02 scheduled | 870.0 GiB (840.0 + 30 new) | **770.0 GiB** |
| nuc14-02 headroom | **9.9 GiB** | **109.9 GiB** |
| nuc14-03 scheduled | 774.0 GiB | 674.0 GiB |

**Read that carefully — it is the single most important operational fact in this
plan.** Keeping the old volume as the rollback means the new volume's reservation is
*added* to the old one until the soak ends. Node 02 goes **temporarily to 9.9 GiB of
headroom, worse than the 39.9 GiB it has now**, and stays there for the soak period.
That is a real, if bounded, regression in the exact number the exercise exists to fix.

Two ways to handle it, operator's call — **decide this BEFORE Step 1, not after:**

- **(i) Accept the soak (default, and what this plan is written for).** Node 02 sits
  at ~9.9 GiB headroom for the soak. During that time **no new Longhorn volume can be
  scheduled onto node 02**, and `defaultDataLocality: best-effort` will again fail to
  place local replicas there. Acceptable only if no new PVCs are being created — check
  first, and shorten the soak to **48 hours** rather than 7 days on that basis. Two
  full days covers a compaction cycle, a nightly backup, and a full 7d-window SLO
  evaluation pass, which is what the soak is actually for.
- **(ii) Shorten the exposure by deleting the OLD LONGHORN REPLICAS but keeping the
  BACKUP.** After 48 h, delete `volume/prometheus-kube-prometheus-stack` and
  `pv/prometheus-kube-prometheus-stack`; the rollback then rests on
  `backup-96e0ceca7fef4199` on `cifs://192.168.55.240/backups` (restorable, but as a
  100Gi volume, and it takes ~15 min). Weaker rollback, full capacity benefit sooner.

**Recommendation: (i) with a 48-hour soak.** Node 02 at 9.9 GiB headroom is
uncomfortable but bounded, observed, and — crucially — no worse than the failure that
already occurred once and self-cleared. Trading two days of that for a
zero-effort, zero-risk rollback on a live monitoring datastore is the right trade.
Verify before starting that nothing is about to provision a new PVC.

---

## 5. Rollback

**The old 100Gi Longhorn volume `prometheus-kube-prometheus-stack` and its PV are the
rollback.** They are never written to, never detached-and-reattached, never deleted by
any step in §3. Their data is exactly as of Step 5's shutdown.

### R1 — Full rollback to the old volume (any failure at Steps 5–10)

Recovers the complete pre-cutover TSDB. ~8 minutes.

```bash
cd /Users/mu/code/cberg-home-nextgen

# 1. Stop the operator touching anything
flux suspend kustomization kube-prometheus-stack -n monitoring
flux suspend helmrelease   kube-prometheus-stack -n monitoring
kubectl -n monitoring patch prometheus kube-prometheus-stack --type merge -p '{"spec":{"paused":true}}'
kubectl -n monitoring delete statefulset prometheus-kube-prometheus-stack --ignore-not-found

# 2. Drop whatever bound the new volume
kubectl -n monitoring delete pvc prometheus-kube-prometheus-stack-db-prometheus-kube-prometheus-stack-0 --ignore-not-found
kubectl -n monitoring delete pvc prometheus-tsdb-seed --ignore-not-found
kubectl -n monitoring delete job prometheus-tsdb-copy prometheus-tsdb-verify --ignore-not-found

# 3. Make the OLD PV claimable again (it is Released + Retain; data intact)
kubectl patch pv prometheus-kube-prometheus-stack --type json -p '[{"op":"remove","path":"/spec/claimRef"}]' || true
kubectl get pv prometheus-kube-prometheus-stack -o jsonpath='{.status.phase}{"\n"}'   # Available

# 4. Revert the git change and let Flux restore the original values
git revert --no-edit <sha-of-the-Step-2e-commit>
git push
flux resume kustomization kube-prometheus-stack -n monitoring
flux resume helmrelease   kube-prometheus-stack -n monitoring
flux reconcile kustomization kube-prometheus-stack -n monitoring --with-source
```

**The revert alone is NOT sufficient** — the reverted helmvalues declare
`storageClassName: longhorn` with no `volumeName`, which is the pre-existing drift
described in §1 and would provision a *fresh empty dynamic 100Gi* volume. So
**recreate the PVC by hand, pinned to the old PV, before the operator builds the
StatefulSet:**

```bash
kubectl apply -f - <<'EOF'
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: prometheus-kube-prometheus-stack-db-prometheus-kube-prometheus-stack-0
  namespace: monitoring
spec:
  accessModes: [ReadWriteOnce]
  resources:
    requests:
      storage: 100Gi
  storageClassName: longhorn-static
  volumeName: prometheus-kube-prometheus-stack
EOF
kubectl -n monitoring get pvc prometheus-kube-prometheus-stack-db-prometheus-kube-prometheus-stack-0   # Bound, 100Gi

kubectl -n monitoring patch prometheus kube-prometheus-stack --type json -p '[{"op":"remove","path":"/spec/paused"}]' || true
```

**Confirm the cluster is genuinely back** (not just Running):

```bash
kubectl -n monitoring get pod prometheus-kube-prometheus-stack-0        # 2/2 Running
kubectl -n monitoring get pvc prometheus-kube-prometheus-stack-db-prometheus-kube-prometheus-stack-0 \
  -o jsonpath='vol={.spec.volumeName} cap={.status.capacity.storage}{"\n"}'   # prometheus-kube-prometheus-stack / 100Gi
kubectl -n monitoring port-forward svc/kube-prometheus-stack-prometheus 19090:9090 >/tmp/pf.log 2>&1 &
sleep 3
curl -s http://127.0.0.1:19090/api/v1/targets?state=active | python3 -c "
import sys,json; t=json.load(sys.stdin)['data']['activeTargets']
print('targets', len(t), 'up', sum(1 for x in t if x['health']=='up'))"   # 75 / 75
curl -s -G --data-urlencode 'query=count(up)' \
  --data-urlencode "time=$(python3 -c 'import time;print(int(time.time()-6.8*86400))')" \
  http://127.0.0.1:19090/api/v1/query    # non-empty -> history is back
```

Then clean up the new objects at leisure:
`kubectl delete pv prometheus-tsdb; kubectl delete volume -n storage prometheus-tsdb`.

### R2 — Abort to "fresh start" (copy job failed, Step 6/7)

Keeps the capacity win, loses ≤7 days of history — Option B from §1, arrived at
deliberately. Faster than R1 and leaves the old volume intact as a *further*
fallback, so R1 stays available afterwards.

```bash
kubectl -n monitoring delete job prometheus-tsdb-copy prometheus-tsdb-verify --ignore-not-found
kubectl -n monitoring delete pvc prometheus-tsdb-seed
kubectl patch pv prometheus-tsdb --type json -p '[{"op":"remove","path":"/spec/claimRef"}]'
# then continue with §3 Step 8b onward, unchanged — Prometheus starts on an empty 30Gi volume
```

**Say out loud in the run report that history was lost, and when the gap starts/ends.**
Expect the 24 h / 7 d degradations catalogued in §1 (predict_linear OOM rules inert
for 24 h; all five 7d-window SLOs partial for 7 days).

### Soak and reclamation of the old volume — NOT part of today

```
SOAK: 48 hours minimum from the successful cutover (see §4.6 for why not 7 days).
DO NOT delete `pv/prometheus-kube-prometheus-stack`,
             `volume/prometheus-kube-prometheus-stack`,
             or its backup, before the soak ends.
```

Conditions to end the soak, all of which must hold:

1. Prometheus has been Ready with 75/75 targets for 48 h with no restarts.
2. At least one full compaction cycle has run on the new volume
   (`prometheus_tsdb_compactions_total` has increased).
3. The nightly Longhorn backup of `prometheus-tsdb` has completed once
   (`kubectl get backupvolumes.longhorn.io -n storage | grep prometheus-tsdb`).
4. Disk usage on the new volume is stable and under 70% of capacity.
5. All five `slo_definitions` rows evaluate over a full 7d window without a data gap
   that changes their verdict.

Reclamation, when those hold — a **separate, deliberate action**, and the step that
actually delivers the numbers in §4.6's right-hand column:

```bash
kubectl delete pv prometheus-kube-prometheus-stack
kubectl delete volume -n storage prometheus-kube-prometheus-stack
kubectl delete recurringjob -n storage prometheus-filesystem-trim prometheus-snapshot-cleanup  # if their labels still point at the old volume name
# then re-run §4.6 and confirm nuc14-02 headroom = ~109.9 GiB
```

This mirrors how `superset-postgresql-data` (20 GiB, detached, 2 stopped replicas) is
being handled after the 2026-09-05 Superset decommission: retained deliberately as the
rollback, reclaimable **only** when the operator ends that soak. **This plan does not
propose deleting it either** — it is named here only as the precedent for the pattern
and as one of the reclaimable-later items in §6.

---

## 6. Interference notes

### Scheduling

- **MUST NOT go into `sat-attended:2026-09-19`.** That slot already carries
  `grafana-13.0.0` + `unpoller-v5.1.0`, which have a live INTERFERENCE warning with
  each other and a mandated serial order. Both verify through Grafana datasources and
  "are metrics arriving" gates; adding a plan that moves the Prometheus TSDB in the
  same slot makes any failure in any of the three unattributable.
- `conflicts_with: [grafana-13.0.0, unpoller-v5.1.0]` is set for that reason, not for
  namespace co-location.
- **Never unattended.** `touches.shared` includes `longhorn`, which
  `runbooks/autonomy-policy.yaml` lists under `forbid_shared` for every AUTO-* class;
  `rollback_class: backup-restore` and `risk: high` reinforce it. HUMAN-GATED, always.
- **No reboot.** Nothing here touches Talos, the kernel, or node state.
- **Do not run concurrently with any other maintenance work, a sweep, or a
  maintenance window.** A window's Step 0 safe-update apply health-gates on
  Prometheus and would read this deliberate outage as a regression and auto-revert an
  otherwise-healthy batch of safe updates.

### Ordering constraints inside the plan

- The **contents gate (Step 7) must run before the PVC delete (Step 8)** — that is the
  README's "order matters for migrations" corollary. Verifying after the app already
  serves turns a free abort into an incident.
- **Flux must be suspended (Step 1) before the git push (Step 2).** An unsuspended
  Flux applies the new helmvalues immediately, the operator sees a changed
  `volumeClaimTemplate` on a live StatefulSet, the update is `Forbidden`, and
  prometheus-operator enters a recreate loop (prometheus-operator#5067) — at a moment
  of our choosing, replaced by one of its choosing.
- **`spec.paused` must be set before deleting the StatefulSet**, or the operator
  recreates it and re-attaches the old PVC mid-copy.

### Things the executor must not do

- **Do not create Alertmanager silences for this outage.** The source is down, not
  noisy; a silence accomplishes nothing and will outlive its usefulness.
- **Do not delete the old PV or Longhorn volume in this session** (§5).
- **Do not "fix" node 02's headroom mid-soak** by deleting the old volume early
  without re-reading §4.6.
- **Do not run `kubectl delete pvc` against anything on a CIFS/SMB class** while in
  this headspace. Nothing here is CIFS — both volumes are Longhorn — but
  `docs/sops/storage-safety.md` Hard Rule 1's three-step pre-flight applies to any
  PVC delete on a shared-fs class, and this plan deletes PVCs.

### The general lesson, and follow-ups (explicitly OUT of scope here)

Over-declaration is **systemic, not a Prometheus bug**: 1063.0 GiB declared against
197.2 GiB actual across 94 volumes is **18.6% utilisation**. Two structural causes:

1. **No convention bounds a new PVC's declared size.** "20Gi" is the reflex default,
   and Longhorn charges the full 20 GiB against scheduling forever.
2. **`replicaAutoBalance: best-effort` balances replica COUNT, not BYTES.** That is
   why node 02 carries 74 replicas to node 01's 50 and is the *most* committed while
   node 01 sits at 64.4%. Rebalancing will not fix a byte imbalance; only
   right-sizing or manual replica placement will.

Also worth fixing, because it is why this had to be found by hand:
**Longhorn scheduling saturation is not alerted on.** `LonghornDiskUsageHigh` /
`Critical` (longhorn-alerts.yaml:175, 188) use
`longhorn_disk_usage_bytes / longhorn_disk_capacity_bytes` — *actual* usage, which
sits at ~55–62% on every node and is nowhere near their 85/95% thresholds. Nothing
alerts on **scheduled/committed**, the number that actually failed. The metric to
build it on exists (`longhorn_disk_reservation_bytes` is exported, currently the
53.7 GB reserve, so the rule needs
`longhorn_disk_usage_bytes` replaced by a scheduled-bytes series — check whether the
Longhorn manager exports one before writing the rule, and pair it with an `absent()`
guard per `project_inert_alert_rules_trap`).

**Follow-up candidates — mentioned, deliberately NOT executed here:**

| volume | declared | actual | used% | note |
|---|---|---|---|---|
| `tube-archivist-cache-2g` | 24.0 GiB | 0.7 GiB | 2.8% | the name literally says "2g"; 24Gi is almost certainly a typo |
| `paperless-data` | 20.0 GiB | 0.8 GiB | 4.0% | |
| `pvc-bd4b4e52-0a71-4690-aade-ad99b1cddfe6` | 20.0 GiB | 0.8 GiB | 3.8% | dynamic/UUID PV — identify its claim before touching |
| `superset-pg-data`, `pvc-b32f29a6…`, `pvc-4b686821…`, `pvc-27866fc8…` | 20.0 GiB each | 0.4–0.6 GiB | 2.2–2.8% | |
| `superset-postgresql-data` | 20.0 GiB | 0.6 GiB | 3.2% | **detached, 2 stopped replicas — the deliberately retained rollback from the 2026-09-05 Superset decommission. Reclaimable ONLY when the operator ends that soak. Do not plan its deletion.** |

Each needs the same create-new + migrate + cutover treatment (Longhorn still cannot
shrink), so each is its own plan. Doing them one at a time is also the only way to keep
node 02 from being squeezed by overlapping soaks — see §4.6.

**Recommended follow-up, separate from all of the above:** a review of PVC sizing
conventions for new deployments in `docs/sops/new-deployment-blueprint.md` and
`docs/sops/longhorn.md` — declare close to the real working set plus a bounded growth
allowance, and rely on Longhorn's *expansion* path (which works, online, no downtime)
rather than defensive over-declaration (which does not have a reverse gear). That
convention gap is the root cause of every row in the table above, and
`F-1b602271` ("SOP gap: Longhorn per-disk provisioning ceiling … is undocumented") is
the existing doc-agent finding closest to it.
