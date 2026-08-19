---
plan_id: longhorn-1.12.1-engine
component: longhorn
pr: null                              # the engine upgrade is a CR operation, not a version bump
kind: chart
current: "93 volumes: 72 on engine v1.11.2 + 21 on engine v1.12.0"
target: "ALL 93 volumes on engine v1.12.1"
update_type: patch
risk: medium                          # live engine upgrade touches every attached volume
est_duration_min: 45                  # ATTENDED portion. The drain itself is ASYNC and
                                      # unbounded — see §6. Do not read this as a finish time.
needs_reboot: false
touches:
  namespaces: [storage]
  resources:
    - "engineimage/ei-c9fa6d45"        # v1.11.2, refCount 292 — GCs once unreferenced
    - "engineimage/ei-a4d05f02"        # v1.12.0, refCount 84  — GCs once unreferenced
    - "volume/* (93)"                  # live engine upgrade: 72 on v1.11.2, 21 on v1.12.0
    - daemonset/engine-image-ei-*      # both stale DaemonSets retire with the last reference
    - setting/concurrent-automatic-engine-upgrade-per-node-limit
  shared: [storage]                   # EVERY stateful app rides Longhorn — see §6
depends_on: [longhorn-1.12.1-chart]   # v1.12.1 must be the default engine before draining onto it
conflicts_with: []                    # (declared FROM the five sibling plans, see §6)
security_ref: F-49f172b9              # see also F-6bedee0b (engine v1.12.0)
status: vetted
window: "ad-hoc:2026-08-19"           # LAST slot of the session; may run past it (async tail)
auto_execute: false                   # storage engine upgrade — never unattended
sops_refs:
  - docs/sops/longhorn.md
  - docs/sops/backup.md
  - docs/sops/storage-safety.md
generated: "2026-08-14"
revised: "2026-08-19"                 # SPLIT from the chart bump + SCOPE CORRECTED
---

# Longhorn: finish the engine upgrade — all 93 volumes → v1.12.1

## 1) Summary & why held

Security driver on `longhornio/longhorn-engine`.

> **Security driver — detail withheld from this public repo.**
> Tracked as **F-49f172b9** (engine v1.11.2) and **F-6bedee0b** (v1.12.0).
> Counts, advisory references and exposure live on the finding records.
>
> - Dashboard: `https://sweep.<DOMAIN>/findings/F-49f172b9`
> - CLI: `runbooks/policy-cli.py finding show F-49f172b9`
>
> Convention: `docs/sops/vulnerability-disclosure.md`.

**SCOPE CORRECTED 2026-08-19.** The previous revision of this plan claimed
"74 of 80 volumes still on v1.11.2". Measured against the live cluster:

```
total volumes: 93
  72  docker.io/longhornio/longhorn-engine:v1.11.2
  21  docker.io/longhornio/longhorn-engine:v1.12.0
```

Both numerator and denominator were wrong, and — the substantive error — the
21 volumes on **v1.12.0 are not "already done"**. v1.12.0 carries its own
finding (**F-6bedee0b**), so it is not a clean destination. **All 93 volumes
must reach v1.12.1**, not 72 of them. A run that stopped when v1.11.2 hit zero
would leave 21 volumes on a flagged engine and the sweep still red.

`EngineImage ei-c9fa6d45` (v1.11.2) has refCount 292 and `ei-a4d05f02`
(v1.12.0) refCount 84; **both** DaemonSets are still deployed, and both stale
images must become unreferenced before the finding clears.

**Root cause of the stall:** `concurrent-automatic-engine-upgrade-per-node-limit`
is `0` (automatic engine upgrade disabled, and not set in git), so engines never
followed the manager. This plan's real work is turning that on in a controlled
way and draining.

**Do NOT "fix" this by pinning engine v1.11.3** — an older minor line than the
1.12.x the manager is on; it moves backwards.

**Split note:** the chart bump 1.12.0 → 1.12.1 is now a separate plan
(`longhorn-1.12.1-chart`) and is a hard `depends_on` — v1.12.1 must be the
cluster's default engine image before anything drains onto it.

## 2) Pre-checks

```bash
# a) the chart half is done and v1.12.1 is the default engine image
kubectl get hr -n storage longhorn -o jsonpath='{.status.history[0].chartVersion}{"\n"}'   # 1.12.1
kubectl get engineimages -n storage    # a v1.12.1 image must exist and be `deployed`

# b) EVERY volume healthy and attached — a live upgrade on a degraded volume is
#    how you lose data.
kubectl get volumes -n storage -o custom-columns=N:.metadata.name,S:.status.state,R:.status.robustness --no-headers | awk '$3!="healthy"'
#    expect NO rows

# c) backups fresh for EVERY volume (mandatory — this is the step with no clean rollback)
kubectl get volumes -n storage -o custom-columns=N:.metadata.name,LASTBACKUP:.status.lastBackupAt --no-headers | awk '$2==""||$2=="<none>"'
#    expect NO rows  (verified 0 rows on 2026-08-19)

# d) baseline distribution
kubectl get volumes -n storage -o custom-columns=E:.status.currentImage --no-headers | sort | uniq -c

# e) NOTHING from the conflicts set still running — see §6. In particular every
#    volume-creating / DB-cutover plan of the session must be COMPLETE, not merely
#    "its window ended".
```

## 3) Steps

1. Marker: `runbooks/update-marker.sh add longhorn storage 2 "engine drain -> v1.12.1 (CVE)"`
2. **Raise the concurrency limit from 0 to 1** — one volume per node at a time,
   so the blast radius at any instant is a single volume on a single node and
   you can stop at any point:
   ```bash
   kubectl -n storage patch setting concurrent-automatic-engine-upgrade-per-node-limit \
     --type=merge -p '{"value":"1"}'
   ```
3. Watch it drain — **both** source images must fall to zero:
   ```bash
   watch 'kubectl get volumes -n storage -o custom-columns=E:.status.currentImage --no-headers | sort | uniq -c'
   ```
4. Any volume that will not live-upgrade (detached, or a workload that dislikes
   it) is moved by scaling its workload to 0, letting the engine swap, and
   scaling back — **one app at a time, never in bulk.**
5. **Decide the end state deliberately** (this setting is NOT in git today):
   leaving it at `1` means engines follow future chart bumps automatically and
   this entire class of drift stops recurring; returning it to `0` restores the
   drift. If it stays at `1`, add
   `concurrentAutomaticEngineUpgradePerNodeLimit: 1` to `defaultSettings` in
   the HelmRelease in the same session so it is not a cluster-only mutation.

## 4) Verification

```bash
# ALL 93 volumes on v1.12.1 — nothing left on v1.11.2 OR v1.12.0
kubectl get volumes -n storage -o custom-columns=E:.status.currentImage --no-headers | sort | uniq -c
#   expect a single line: 93 ... longhorn-engine:v1.12.1

# BOTH stale EngineImages unreferenced, then gone; their DaemonSets retired
kubectl get engineimages -n storage
kubectl get ds -n storage | grep engine-image

# every volume still healthy + attached, no replica rebuild storm
kubectl get volumes -n storage -o custom-columns=N:.metadata.name,S:.status.state,R:.status.robustness --no-headers | awk '$3!="healthy"'

# finding cleared
trivy image longhornio/longhorn-engine:v1.12.1 --severity CRITICAL --ignore-unfixed
# Record the result on F-49f172b9 and F-6bedee0b — not in this file.

# app-level smoke: one stateful app per class still reads/writes (a database pod
# and a CIFS-backed media pod), plus `flux get kustomizations -A`.
```

## 5) Rollback

**There is no clean rollback — Longhorn does not downgrade engines live.** This
is why pre-check (c) is mandatory.

If a volume misbehaves mid-drain:
1. Set the concurrency setting back to `0` **immediately** — this stops all
   further upgrades within seconds.
2. Leave already-upgraded volumes alone; they are on a newer, supported engine.
3. Treat any single broken volume as a restore-from-backup per
   `docs/sops/backup.md`.

**No PVC/PV deletes** under any circumstance — see `docs/sops/storage-safety.md`.

## 6) Interference notes

- **This is the half that carries the conflicts.** Five sibling plans declare
  `conflicts_with: longhorn-1.12.1-engine`: `cilium-1.20.1`,
  `superset-pg-cutover`, `superset-6.1.0`, `bitnamilegacy-exit-paperless-db`,
  `bitnamilegacy-exit-nextcloud-db`. Their stated reasons are all about the
  engine work specifically ("must not run under storage-engine work", "never
  pair storage-engine work with new-volume creation", "live engine upgrade
  rides the network the agents blip"). Those declarations remain correct and
  unedited after the split, because this file kept the `longhorn-1.12.1-engine`
  plan_id.
- **`shared: [storage]` is load-bearing.** Every stateful app rides Longhorn.
- **The drain is ASYNCHRONOUS and unbounded.** `est_duration_min: 45` covers the
  attended portion (pre-checks, flipping the setting, confirming the drain has
  started cleanly and is progressing). With concurrency 1 across 93 volumes the
  tail can run well past the window. **The conflicting plans need the drain
  COMPLETE, not the window ended** — that asymmetry is precisely why this was
  split out of the chart bump, and it is why this plan is scheduled LAST in the
  2026-08-19 ad-hoc session with an explicitly accepted async tail.
- Never run in the same window as a Talos node roll: a node reboot during a live
  engine upgrade is the worst case.
- Incremental by design: with concurrency 1 the blast radius at any instant is a
  single volume on a single node.
