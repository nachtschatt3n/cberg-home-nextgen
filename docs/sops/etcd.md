# SOP: etcd Performance, Stability and Maintenance

> Description: How to read etcd health on this 3-node Talos cluster: disk-latency thresholds, leader-change triage (including the pattern (ii) continue-rule for node rolls), `talosctl etcd defrag`, snapshot and restore, and the shared-NVMe contention behind most leader flaps.
> Version: `2026.09.28`
> Last Updated: `2026-09-28`
> Owner: `homelab-ops` (cluster-ops-agent / health-check-agent)

---

## 1) Description

etcd runs as a Talos-managed service (not a pod) on all three control-plane nodes
(`k8s-nuc14-01/02/03`, `192.168.55.11-13`). Quorum is 2 of 3: exactly one member may be
down. Every node is also a worker, and etcd shares its NVMe with container images and
Longhorn replicas, so disk contention from ordinary cluster work is the main threat to
etcd stability here.

This SOP exists because the knowledge was spread across a retired maintenance plan
(`git show 40ca20d6^:runbooks/maintenance/plans/talos-1.14.1.md`), the 2026-09-26 etcd
investigation and several findings (F-65b9b738, F-84a27c15, F-58141d46, F-2cb2dbc9,
F-e8bb3113, F-3602cfa9).

- Scope: etcd members on the three Talos nodes; the Prometheus metrics that describe them;
  the cluster workloads that contend for the same disk (Flux, Longhorn, node drains).
- Prerequisites: `talosctl` + `kubectl` via `mise`, `TALOSCONFIG` from `.mise.toml`;
  Prometheus reachable through the apiserver service proxy (no port-forward needed).
- Out of scope: the Talos node roll itself (`docs/sops/talos-upgrade.md`), Longhorn
  internals (`docs/sops/longhorn.md`), full-cluster DR (`docs/sops/disaster-recovery.md`).

---

## 2) Overview

| Setting | Value |
|---------|-------|
| Version | etcd `3.7.1`, storage `3.7.0` (Talos v1.14.1, since 2026-09-27; was 3.6.14) |
| Members | 3 (`192.168.55.11/.12/.13`), quorum 2 |
| Data dir | `/var/lib/etcd` — a **directory on EPHEMERAL** (`nvme0n1p6`), same partition as `/var/lib/longhorn` and container images |
| Disks | Consumer NVMe, no power-loss protection: 980 PRO 1 TB on 01/02, 990 PRO 1 TB on 03 |
| Metrics | `listen-metrics-urls: http://0.0.0.0:2381` (`kubernetes/bootstrap/talos/patches/controller/cluster.yaml`); Prometheus job `kube-etcd`, instances `192.168.55.1x:2381`. Talos 1.14 moved the *default* to 2383; the explicit setting keeps 2381. |
| Latency thresholds | worst 5m-p99 **WAL fsync < 50 ms** and **backend commit < 50 ms** |
| Leader-change base rate | ~6 spontaneous elections / 7 d before the 2026-09-26 mitigation |
| Defrag trigger | IN USE < 50 % of DB SIZE on any member |
| Source of truth | `kubernetes/bootstrap/talos/talconfig.yaml` + `patches/controller/cluster.yaml` (applied manually; Flux does not reconcile `kubernetes/bootstrap/talos/`) |

---

## 3) Blueprints

N/A for etcd itself — it is Talos machine config, and machine-config changes are blocked
until the multi-document config migration lands (`docs/sops/talos-upgrade.md` §14.2,
F-59b12b2b).

The one GitOps artifact that exists to protect etcd is the Flux source `spec.ignore`
(`b4ed1d63`), which cuts the per-commit artifact extraction volume on the shared disk:
`kubernetes/apps/flux-system/flux-operator/instance/helm-values.yaml`
(`instance.kustomize.patches`, see `docs/sops/flux-image-automation-push-auth.md` §3 "Source filter").

---

## 4) Operational Instructions

All Prometheus reads below go through the apiserver service proxy:

```bash
P='/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query='
pq() { mise exec -- kubectl get --raw "$P$(python3 -c 'import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))' "$1")" \
  | python3 -c "import sys,json; [print(' ',x['metric'].get('instance'),x['value'][1]) for x in json.load(sys.stdin)['data']['result']]"; }
```

### 4.1 Disk-latency thresholds

```bash
pq 'max_over_time(histogram_quantile(0.99, sum by (instance,le) (rate(etcd_disk_wal_fsync_duration_seconds_bucket[5m])))[1h:1m])'
pq 'max_over_time(histogram_quantile(0.99, sum by (instance,le) (rate(etcd_disk_backend_commit_duration_seconds_bucket[5m])))[1h:1m])'
```

- **PASS: every member < 0.050 (50 ms).** Measured healthy 2026-09-28: fsync 15–29 ms,
  commit 13–29 ms. Upstream guidance is p99 fsync < 10 ms on server disks; consumer NVMe
  sharing with Longhorn sits higher, so 50 ms is this cluster's gate, not a target.
- Expect exactly 3 series per query. Fewer = a scrape gap: an empty result reads as "under
  50 ms" and must fail closed, never pass.
- Seconds-scale values (1.8 s → 7.3 s were seen during the 2026-09-27 drains) mean the
  member cannot heartbeat in time and an election follows.

### 4.2 Leader-change triage

```bash
mise exec -- talosctl -n 192.168.55.11,192.168.55.12,192.168.55.13 etcd status   # LEADER column, RAFT TERM, ERRORS
pq 'increase(etcd_server_leader_changes_seen_total[24h])'                          # reset-aware, approximate
pq 'min_over_time(etcd_server_has_leader[15m])'                                    # 1 = never leaderless
pq 'increase(node_network_carrier_changes_total{device=~"en.*"}[1h])'               # NIC flaps per node
pq 'histogram_quantile(0.99, sum by (instance,le) (rate(etcd_network_peer_round_trip_time_seconds_bucket[5m])))'
pq 'process_start_time_seconds{job="kube-etcd"}'                                   # did a member restart?
```

**Counter trap:** `x - x offset <window>` is exact but goes **negative** for a member that
restarted inside the window (measured 2026-09-28 after the roll: -12 / -13 / -16 over 24 h).
Either use `increase()` (reset-aware, extrapolated) or skip members whose
`process_start_time_seconds` lies inside the window, as the roll gates did.

Classify each election:

| Pattern | Signature | Verdict |
|---|---|---|
| (i) Rolled-leader | The node that rebooted WAS the leader; exactly +1 on the survivors | Expected. Pre-record it before the reboot. |
| **(ii) Drain-driven** | Survivors elect while another node drains/reboots; **carrier +0** everywhere; `min_over_time(etcd_server_has_leader[15m]) = 1` on the survivors; slow fdatasync (p99 ≥ 50 ms) **only inside the drain window** and clean after; `etcd status` clean on all 3 | Disk contention from the drain. A node roll may continue (operator decision) — `docs/sops/talos-upgrade.md` §14.3. |
| (iii) Disk-driven, idle cluster | Elections with no drain, fsync/commit p99 spikes, `kustomize-controller` write burst or Longhorn rebuild at the same minute | Shared-NVMe contention (§4.5). Find the writer. |
| (iv) Network / cluster-wide stall | All members fail health together, peer RTT in the seconds buckets, **no** disk-latency or IO signal (F-3602cfa9, 2026-09-24 ~20:28Z, still unexplained) | Not a disk problem. Check the switch (Basement-SW-24-PoE carries all three nodes), `unifictl local event list`, CPU pressure. Never during a node roll or switch firmware update (`docs/sops/unifi-device-firmware.md`). |
| Leaderless | `min_over_time(etcd_server_has_leader[15m]) < 1` | Quorum was lost. Incident — §7. |

**Base-rate rule:** ≥ 6 leader changes in 24 h with no reboots = etcd is already unstable;
no planned disruption (node roll, switch firmware, big Longhorn operation) until explained.

### 4.3 Defrag (`talosctl etcd defrag`)

Defrag rewrites the bbolt file with only live pages. It changes no keys (nothing to roll
back), but it is the heaviest write burst etcd does to itself and blocks that member's
backend for its duration. Run it when IN USE < 50 % of DB SIZE on any member (2026-09-26:
25–29 % in use, 867–912 MB files → 167–175 MB after).

Rules: **one member at a time, followers first, leader last, a gate between members.**

```bash
mise exec -- talosctl -n 192.168.55.11,192.168.55.12,192.168.55.13 etcd status
LEADER_IP=<ip whose MEMBER equals the LEADER column>
FOLLOWERS=(<ip> <ip>)     # an ARRAY: zsh does not word-split a "a b" scalar
for ip in "${FOLLOWERS[@]}" "$LEADER_IP"; do
  echo "=== gate before $ip"
  # GATE (all must hold, else STOP and do not defrag $ip):
  #   §4.1 queries with [10m:1m] instead of [1h:1m] -> every member < 50 ms
  #   etcd status: 3 members, one leader, no learner, empty ERRORS, RAFT INDEX spread <= 50
  #   no leader change since the previous member's defrag
  /usr/bin/time -p mise exec -- talosctl -n "$ip" etcd defrag || { echo "DEFRAG FAILED on $ip -- STOP"; break; }
  sleep 60
done
mise exec -- talosctl -n 192.168.55.11,192.168.55.12,192.168.55.13 etcd status   # IN USE ~ DB SIZE on all three
mise exec -- talosctl -n 192.168.55.11,192.168.55.12,192.168.55.13 etcd alarm list
```

- **PASS:** after each defrag that member's IN USE ≥ 80 % of DB SIZE; `real` is seconds
  (0.74–0.86 s each on 2026-09-26); cluster converged; `etcd alarm list` empty.
- A gate failure right after a follower's defrag is usually that defrag's own p99 spike,
  which stays in a 10-min lookback for ~15 min. Re-check every 3 min, at most 6 tries, then
  continue with ONLY the members not yet done. Still failing = stop; a partly-defragged
  cluster is correct, just larger.
- The leader's defrag may cause ONE election (backend blocked longer than the election
  timeout). One change right after the leader's defrag is explained; a change during a
  follower's defrag, or more than one, is not — stop and triage (§4.2).
- A member that does not come back healthy within 5 min:
  `talosctl -n <that-ip> service etcd restart` on that member only.

### 4.4 Snapshot and restore

**Snapshot** (before any node roll, and before any risky control-plane change):

```bash
SCR=$(mktemp -d /tmp/etcd-snap.XXXXXX); chmod 700 "$SCR"   # local only, never the repo or a synced folder
mise exec -- talosctl -n "$LEADER_IP" etcd snapshot "$SCR/etcd-$(date -u +%Y%m%dT%H%MZ).db"
chmod 600 "$SCR"/etcd-*.db; stat -f '%Lp %z %N' "$SCR"/etcd-*.db
```

PASS: mode 600 and a size in the order of the current DB SIZE (~150–450 MB). A 0-byte or
few-KB file is a FAIL. The snapshot contains **every Secret in the cluster**: delete it
(`rm -P`) once the change has soaked 24 h.

**Restore** is disaster recovery only (permanent quorum loss), operator-present, and follows
`docs/sops/talos-upgrade.md` §11.4: `reset --system-labels-to-wipe=EPHEMERAL` on each node
(**this destroys every Longhorn replica on that node**, because Longhorn lives on EPHEMERAL
too), wait for etcd `Preparing` everywhere, then
`talosctl -n <one-ip> bootstrap --recover-from=<snapshot>`. A single broken member is NOT a
restore case — restart it, or remove and re-add that member.

### 4.5 Shared-NVMe contention — causes and mitigations

etcd needs low-latency `fdatasync`. Everything below writes to the same partition:

| Cause | Mechanism | Mitigation |
|---|---|---|
| **Flux source extraction** (the dominant trigger until 2026-09-26) | The `flux-system` GitRepository had no `spec.ignore`; for every new revision, and on every interval, kustomize-controller downloaded and unpacked the whole repo (docs/ and runbooks/ are the bulk) once per Kustomization — ~141× per commit. Commit bursts → fsync stalls → elections (8 in the 7 d to 2026-09-26). | **`b4ed1d63`**: `spec.ignore` ships only `kubernetes/` (artifact 7.1 MB → 1.9 MB). Gate: `kustomize-controller` writes < 5 MB/s over 10 min (`sum(rate(container_fs_writes_bytes_total{namespace="flux-system",container="manager",pod=~"kustomize-controller-.*"}[10m]))`). A push freeze during node rolls. |
| **Longhorn rebuilds** | Replica rebuilds after a node returns (incremental) or after > 600 s away (FULL rebuilds onto the two survivors — exactly the quorum disks). `concurrent-replica-rebuild-per-node-limit` is 8. | Keep nodes back within `replica-replenishment-wait-interval` (600 s). For a roll, optionally drop the limit to 2 via a **top-level** `values.defaultSettings` override and restore 8 explicitly (F-2cb2dbc9; `docs/sops/talos-upgrade.md` §14.3). |
| **Node drains** | Mass eviction, engine moves, image pulls, and a cold kustomize-controller on a survivor reconciling everything at once. Survivor fsync 1.8 s → 3.6 s → 7.3 s across the 2026-09-27 drains. | Pattern (ii) rule (§4.2); gates between nodes; roll the node running Prometheus first so the instrument is not blinded (F-e8bb3113). |
| etcd's own defrag | Full file rewrite. | One member at a time, gated (§4.3). |

**C2 — the structural fix (follow-up, not scheduled):** Talos 1.14 can put etcd on a
**dedicated system volume** (`VolumeConfig`, "Dedicated System Volumes" in the v1.14.0
changelog). Directory-vs-partition is fixed at provisioning, so it needs a
`talosctl reset` + etcd member replace per node — its own project, and it depends on the
multi-document config migration (C1, F-59b12b2b) landing first. Until then the mitigations
above are the controls.

---

## 5) Examples

### Example A: routine health read

```bash
mise exec -- talosctl -n 192.168.55.11,192.168.55.12,192.168.55.13 etcd status
pq 'max_over_time(histogram_quantile(0.99, sum by (instance,le) (rate(etcd_disk_wal_fsync_duration_seconds_bucket[5m])))[1h:1m])'
pq 'increase(etcd_server_leader_changes_seen_total[7d])'
```

### Example B: sweep reports "etcd leader changes: 9 in 24h"

1. Was there a node roll / drain in the window? (`pq 'process_start_time_seconds{job="kube-etcd"}'`,
   `kubectl get nodes` ages.) Yes → match each change to a drain/reboot; pattern (i)/(ii).
2. No → pull fsync/commit p99 and kustomize-controller write rate at the minute of each
   change (pattern (iii)); check carrier changes and peer RTT (pattern (iv)).
3. Changes continuing after the roll ended are not explained by it.

---

## 6) Verification Tests

### Test 1: metrics are scraped (the gates can fail)

```bash
pq 'count(etcd_disk_wal_fsync_duration_seconds_count) + count(etcd_disk_backend_commit_duration_seconds_count)'
```

Expected: `6`. If failed: the `kube-etcd` target is down or the metrics URL changed —
check `patches/controller/cluster.yaml` still sets port 2381.

### Test 2: cluster converged

```bash
mise exec -- talosctl -n 192.168.55.11,192.168.55.12,192.168.55.13 etcd status
```

Expected: 3 rows, one LEADER value, LEARNER `false`, empty ERRORS, identical RAFT INDEX
(± 50), same PROTOCOL on all. If failed: §7.

### Test 3: negative control for the latency gate

Re-run §4.1 mentally against a 1 ms limit: live values (15–29 ms) must FAIL it. A gate that
passes at 1 ms is reading nothing.

---

## 7) Troubleshooting

| Symptom | Likely Cause | First Fix |
|---------|--------------|-----------|
| Leader changes while idle, fsync p99 spikes | Shared-disk writer (Flux burst, Longhorn rebuild) | §4.5; find the writer at that minute |
| Leader changes during a drain | Pattern (ii) | §4.2; roll decision per `talos-upgrade.md` §14.3 |
| All members unhealthy together, peer RTT seconds, no disk signal | Network / switch / CPU (pattern iv) | Carrier changes, `unifictl local event list`, node CPU |
| `etcdserver: no leader` flood in kube-system logs | Leaderless period during an election | Correlate with §4.2; transient if `has_leader` recovered |
| `etcd alarm list` shows `NOSPACE` | DB hit quota | Compact is automatic; defrag (§4.3), then `talosctl etcd alarm disarm` |
| Member ERRORS non-empty after reboot/defrag | Member not caught up | Wait 5 min; `talosctl -n <ip> service etcd restart` on that member only |
| Leader-change diff negative | Counter reset on restart | Use `increase()` or skip restarted members (§4.2) |

```bash
mise exec -- talosctl -n <ip> logs etcd | tail -100          # ring buffer: 'apply request took too long' spam rotates quickly
mise exec -- talosctl -n <ip> service etcd
mise exec -- talosctl -n 192.168.55.11 etcd members
```

---

## 8) Diagnose Examples

### Diagnose Example 1: 2026-09-26 — 8 elections in 7 days on an idle cluster

Pattern (iii). Elections lined up with commit bursts: every push made kustomize-controller
unpack the whole repo ~141×. Controls measured before the fix: kustomize-controller
11.19 MB/s during a burst vs < 5 MB/s gate. Fix: `b4ed1d63` (`spec.ignore`), plus defrag
(DB 867–912 MB → ~170 MB).

### Diagnose Example 2: 2026-09-27 — elections on survivors during the Talos roll

Pattern (ii). Survivor fdatasync stalls 1.8 s → 3.6 s → 7.3 s inside each drain, carrier +0,
clean after. Node 01's changes could not be classified because Prometheus ran on node 01 and
had no samples for its reboot window, and the survivors' etcd logs had rotated
(F-e8bb3113). Lesson: stream survivor etcd logs to local scratch during every drain.

---

## 9) Health Check

```bash
mise exec -- talosctl -n 192.168.55.11,192.168.55.12,192.168.55.13 etcd status
mise exec -- talosctl -n 192.168.55.11,192.168.55.12,192.168.55.13 etcd alarm list
pq 'max_over_time(histogram_quantile(0.99, sum by (instance,le) (rate(etcd_disk_wal_fsync_duration_seconds_bucket[5m])))[1h:1m])'
pq 'increase(etcd_server_leader_changes_seen_total[24h])'
```

Healthy: converged status, no alarms, p99 < 50 ms, < 6 changes/24 h without reboots. The
daily sweep's `etcd-leader-changes` check reports the same counter.

---

## 10) Security Check

- Snapshots hold every Secret: local mode-700 scratch only, mode 600, `rm -P` after 24 h;
  never in the repo, iCloud, Nextcloud or a sweep artifact.
- etcd and kube-apiserver require TLS 1.3 minimum since Talos 1.14.
- The metrics listener (`0.0.0.0:2381`, plain HTTP) exposes metrics only, on the node
  network; no key access.
- `talosconfig` is gitignored; never paste `talosctl` output that contains keys.

---

## 11) Rollback Plan

- Defrag: nothing to roll back (no key changes). A failed member → restart it.
- Flux `spec.ignore`: `git revert b4ed1d63` restores full-repo artifacts (and the IO load).
- Longhorn rebuild-limit override: set `8` explicitly — removing the key leaves the Setting
  CR at the lowered value.
- Quorum loss: restore from the latest snapshot (§4.4 / `talos-upgrade.md` §11.4). Objects
  created after the snapshot are lost; Flux re-applies git.

---

## 12) References

- `docs/sops/talos-upgrade.md` — §0.4 snapshot, §11.4 restore, §14 v1.14.1 roll lessons, §15 expected transients
- `docs/sops/flux-image-automation-push-auth.md` §3 "Source filter" — the `spec.ignore` source filter
- `docs/sops/longhorn.md`, `docs/sops/storage-safety.md`
- `docs/sops/unifi-device-firmware.md` — never a switch reboot in the same slot as a node roll
- `docs/sops/monitoring.md`
- Retired plan with the gate helpers: `git show 40ca20d6^:runbooks/maintenance/plans/talos-1.14.1.md`
- Findings: F-65b9b738, F-84a27c15, F-58141d46, F-2cb2dbc9, F-e8bb3113, F-3602cfa9, F-59b12b2b
- Upstream: etcd "Hardware recommendations" and "Maintenance — defragmentation"; Talos "Disaster Recovery" and v1.14.0 changelog

---

## Version History

- `2026.09.28`: Initial version (F-65b9b738). Thresholds, leader-change pattern table incl.
  pattern (ii), gated defrag, snapshot/restore, shared-NVMe contention causes (Flux source
  extraction before `b4ed1d63`, Longhorn rebuilds, node drains) and the C2 dedicated-partition
  follow-up. Records the negative-counter trap after member restarts (measured 2026-09-28).
