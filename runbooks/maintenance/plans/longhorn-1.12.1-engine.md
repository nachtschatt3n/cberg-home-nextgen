---
plan_id: longhorn-1.12.1-engine
component: longhorn
pr: null                              # chart bump has no Renovate PR yet; the engine
                                      # upgrade is a CR operation, not a version bump.
kind: chart
current: "chart 1.12.0 / 74 of 80 volumes still on engine v1.11.2"
target: "chart 1.12.1 + ALL volumes on engine v1.12.1"
update_type: patch                    # chart 1.12.0 -> 1.12.1; the engine move is the real work
risk: medium                          # live engine upgrade touches every attached volume
est_duration_min: 60
needs_reboot: false
touches:
  namespaces: [storage]
  resources:
    - helmrelease/longhorn             # chart 1.12.0 -> 1.12.1
    - "engineimage/ei-c9fa6d45"        # v1.11.2, refCount 302 — should GC once unreferenced
    - "volume/* (80)"                  # live engine upgrade, 74 still on v1.11.2
    - daemonset/engine-image-ei-*      # the stale v1.11.2 DS retires with the last reference
  shared: [storage]                    # EVERY stateful app rides Longhorn — see Interference
depends_on: []
conflicts_with: []                    # but do NOT co-schedule with any data-store plan
status: draft
window: "sat-early:2026-09-05"       # MOVED 2026-08-14: sat-early:2026-08-22 collided with
                                      # kube-prometheus-stack-88 on `storage` (kps moves its
                                      # Prometheus PVCs). Longhorn carries EVERY stateful app,
                                      # so it gets a solo window rather than a "should be fine".
                                      # namespace, no shared resource); 90m slot, cap 6
auto_execute: false                   # storage engine upgrade — never unattended
sops_refs:
  - docs/sops/longhorn.md
  - docs/sops/backup.md
  - docs/sops/storage-safety.md
generated: "2026-08-14"
---

# Longhorn: chart 1.12.0 → 1.12.1 **and** finish the engine upgrade

## 1) Summary & why held

Two fixable CRITICAL CVEs sit on `longhornio/longhorn-engine:v1.11.2`, plus
~240 fixable HIGH across `longhorn-engine/instance-manager/manager/share-manager/ui`
and the three `longhornio/csi-*` sidecars.

**The important part: bumping the chart alone will NOT clear them.** The chart is
already at 1.12.0, but **74 of 80 volumes still run engine `v1.11.2`** — only 6
moved. `EngineImage ei-c9fa6d45` (v1.11.2) has refCount 302 and its DaemonSet is
still deployed, which is what Trivy keeps scanning. Cause:
`concurrent-automatic-engine-upgrade-per-node-limit = 0` (automatic engine
upgrade disabled, and not set in git), so the engine never followed the manager.

So the CVE is cleared by **completing the live engine upgrade**, after which the
stale image GCs and the DaemonSet retires. The 1.12.0 → 1.12.1 chart bump is
worth doing in the same window but is not, by itself, the fix.

**Do NOT "fix" this by pinning engine v1.11.3.** That is an older minor line than
the 1.12.x the manager is already on — it would move backwards.

## 2) Pre-checks

```bash
# a) how many volumes are still on the old engine, and is the old image referenced?
kubectl get volumes -n storage -o custom-columns=NAME:.metadata.name,ENGINE:.status.currentImage --no-headers | awk '{print $2}' | sort | uniq -c
kubectl get engineimages -n storage
kubectl get ds -n storage | grep engine-image

# b) EVERY volume healthy and attached before touching the engine — a live
#    upgrade on a degraded volume is how you lose data.
kubectl get volumes -n storage -o custom-columns=NAME:.metadata.name,STATE:.status.state,ROBUSTNESS:.status.robustness --no-headers | awk '$3!="healthy"'
#    expect NO rows.

# c) backups fresh for every volume (mandatory before a storage-layer change)
kubectl get volumes -n storage -o custom-columns=NAME:.metadata.name,LASTBACKUP:.status.lastBackupAt --no-headers | awk '$2==""||$2=="<none>"'
#    expect NO rows.

# d) current auto-upgrade setting (this is what stalled the rollout)
kubectl get setting -n storage concurrent-automatic-engine-upgrade-per-node-limit -o jsonpath='{.value}{"\n"}'

# e) chart target exists
helm search repo longhorn/longhorn --versions | head -3
```

## 3) Steps

1. Marker: `runbooks/update-marker.sh add longhorn storage 2 "chart 1.12.1 + engine upgrade (CVE)"`
2. **Chart bump first** — `kubernetes/apps/storage/longhorn/app/helmrelease.yaml`
   1.12.0 → 1.12.1. Commit, push, let Flux reconcile. Wait for manager/CSI pods
   to settle and re-run pre-check (b): all volumes healthy.
3. **Then the engine upgrade — the actual fix.** Prefer the controlled route:
   raise `concurrent-automatic-engine-upgrade-per-node-limit` from 0 to **1**
   (one volume per node at a time), so Longhorn live-upgrades attached volumes
   incrementally and you can stop at any point.
   ```bash
   kubectl -n storage patch setting concurrent-automatic-engine-upgrade-per-node-limit \
     --type=merge -p '{"value":"1"}'
   ```
   Watch it drain:
   ```bash
   watch 'kubectl get volumes -n storage -o custom-columns=E:.status.currentImage --no-headers | sort | uniq -c'
   ```
   > This setting is NOT currently in git. Decide deliberately whether it stays
   > at 1 permanently (engines then follow future chart bumps automatically, and
   > this whole class of drift stops recurring) or is returned to 0 after the
   > run. If it stays, add it to the HelmRelease values so it is not a
   > cluster-only mutation.
4. Any volume that will not live-upgrade (detached, or a workload that dislikes
   it) can be moved by scaling its workload to 0, letting the engine swap, and
   scaling back — one app at a time, never in bulk.

## 4) Verification

```bash
# all 80 volumes on the new engine, none left on v1.11.2
kubectl get volumes -n storage -o custom-columns=E:.status.currentImage --no-headers | sort | uniq -c
# stale EngineImage unreferenced, then gone; its DaemonSet retired
kubectl get engineimages -n storage
kubectl get ds -n storage | grep engine-image
# every volume still healthy + attached, no replica rebuild storm
kubectl get volumes -n storage -o custom-columns=N:.metadata.name,S:.status.state,R:.status.robustness --no-headers | awk '$3!="healthy"'
# CVE gone
trivy image longhornio/longhorn-engine:v1.12.1 --severity CRITICAL --ignore-unfixed
# app-level smoke: one stateful app per class still reads/writes (e.g. a database
# pod and a CIFS-backed media pod), plus `flux get kustomizations -A`.
```

## 5) Rollback

The chart bump reverts by `git revert` + reconcile. **The engine upgrade does
not revert cleanly** — Longhorn does not downgrade engines live. If a volume
misbehaves mid-upgrade: set the concurrency setting back to `0` to STOP further
upgrades immediately, leave already-upgraded volumes alone (they are on a newer,
supported engine), and treat any single broken volume as a restore-from-backup
per `docs/sops/backup.md`. This is why pre-check (c) is mandatory.

## 6) Interference notes

- **`shared: [storage]` is load-bearing.** Every stateful app in the cluster
  rides Longhorn. Do not co-schedule with ANY plan that touches a data store
  (mariadb-27, kube-prometheus-stack's Prometheus PVCs during a chart move, or
  a Talos reboot window). The sat-early:2026-08-22 slot pairs it with
  kube-prometheus-stack-88, which is a different namespace — acceptable only if
  the kps plan does not move its PVCs; the window agent must confirm that before
  running both.
- Never run this in the same window as `talos-v1.13.8` (sun-window 2026-08-16):
  a node reboot during a live engine upgrade is the worst case.
- Incremental by design: with concurrency 1 the blast radius at any instant is a
  single volume on a single node.
