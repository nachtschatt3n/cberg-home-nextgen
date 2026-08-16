---
plan_id: talos-v1.13.8
component: talos
pr: 194                             # Renovate: ghcr.io/siderolabs/installer v1.13.7 → v1.13.8
kind: node-os                       # rolling node upgrade, one node at a time
current: "v1.13.7"
target: "v1.13.8"
update_type: patch
risk: medium                        # patch content is low-drama; risk is the
                                    # ROLLING REBOOTS (Longhorn RWO reattach churn,
                                    # etcd quorum, single-replica apps blip per node)
est_duration_min: 75                # ~20-25 min/node incl. health-wait + reconverge
needs_reboot: true                  # → sun-window ONLY (allow_reboot: true)
touches:
  namespaces: [all]                 # every pod on each node reboots in turn
  resources:
    - "node/k8s-nuc14-01 (192.168.55.11)"
    - "node/k8s-nuc14-02 (192.168.55.12)"
    - "node/k8s-nuc14-03 (192.168.55.13)"
    - kubernetes/bootstrap/talos/talconfig.yaml   # talosVersion bump (PR #194)
  shared: [nodes, etcd, longhorn]   # whole-cluster churn; nothing else may run
depends_on: []
conflicts_with: []                  # SOLO window — never alongside app plans;
                                    # multiple reboots must serialize with full
                                    # node-Ready + Longhorn reconvergence between
status: partial            # 1/3 nodes on v1.13.8 (sun-window:2026-08-16)
window: "sun-window:2026-08-23"     # RESUME nodes 02+03 (next reboot-capable slot)
auto_execute: false                 # node reboots → always operator-present go/no-go
sops_refs:
  - docs/sops/talos-upgrade.md      # THE procedure — this plan defers to it
  - docs/sops/storage-safety.md
generated: "2026-08-07"
---

# Talos v1.13.7 → v1.13.8 — rolling node patch (PR #194)

## 1. Summary & why held

Patch bump of the Talos node OS across all 3 nodes. Held by the auto-updater
(correctly): a Talos installer-image bump is applied via `talosctl upgrade`
with a **rolling reboot per node**, not a git merge alone. Procedure,
performance-tuning context, and per-node verification live in
`docs/sops/talos-upgrade.md` (v2026.08.02) — this plan is the window wrapper.

Reboot-cause note: kmsg shipping (Tier 2) survives reboots via UDP; after each
node reboot, spot-check per-node kmsg counts in ES and toggle any silent
sender per `docs/troubleshooting/node-reboot-observability.md` (collector-
restart stall gotcha).

## 2. Pre-checks (from the SOP; all must pass)

```bash
# cluster green: all nodes Ready, etcd healthy, 0 firing alerts, Flux clean
mise exec -- kubectl get nodes
mise exec -- talosctl -n 192.168.55.11,192.168.55.12,192.168.55.13 health --wait-timeout 2m
# Longhorn: all volumes healthy, last backup < 24h (reboots reattach RWO volumes)
mise exec -- kubectl get volumes -n storage -o custom-columns=NAME:.metadata.name,ROBUST:.status.robustness --no-headers | grep -v healthy || echo "all healthy"
# target installer image exists (PR #194 CI green)
mise exec -- gh pr checks 194
# no other plan running this window (SOLO)
```

## 3. Steps

1. Merge PR #194 (talconfig.yaml `talosVersion: v1.13.8`), push.
2. `talhelper genconfig` — regenerate clusterconfig.
3. Per node, **serially** (…-01 → …-02 → …-03), per the SOP:
   `talosctl -n <ip> upgrade --image factory.talos.dev/installer/<schematic>:v1.13.8`
   → wait `talosctl health` + node Ready + **Longhorn volumes all healthy** +
   orphaned `Error/ContainerStatusUnknown` pods cleaned before the next node.
4. After node 3: full health gate (flux ks/hr all Ready, 0 firing alerts,
   kmsg per-node counts in ES).

## 4. Verification

- `kubectl get nodes -o wide` → all 3 Ready on v1.13.8 kernel/OS.
- `talosctl version -n <each>` → v1.13.8.
- Longhorn 0 degraded volumes; no stuck ghost pods (crash-ghost-reaper clears).
- 0 firing alerts; spot-check HA, ES, authentik, ingress serve.
- kmsg flowing from all 3 nodes in ES (node-reboot-observability gotcha).

## 5. Rollback

Talos supports A/B boot: `talosctl rollback -n <ip>` reverts a node to the
previous install (v1.13.7) — per node, serially, same health-waits. Git side:
revert the PR merge commit. If only later nodes misbehave, stop the roll and
leave the cluster mixed (supported) until diagnosed.

## 6. Interference notes

- **SOLO window, hard rule.** Whole-cluster churn: every single-replica app
  blips as its node reboots; Longhorn RWO volumes detach/reattach per node.
  Nothing else runs in this window (the sun-08-16 slot has no other plans).
- Serialize strictly; never two nodes in flight (etcd quorum = 3).
- Expect the known post-reboot noise (update-marker + alert-triage handle);
  set `runbooks/update-marker.sh add talos '*' 3 "v1.13.8 rolling reboot"`.
- ~~If sat-08-15's envoy-gateway-phase1 deferred into this window~~ OBSOLETE
  (2026-08-15): the envoy chain is BLOCKED — phase 0 was rolled back after the
  Gateway API CRDs took internal DNS down (see envoy-gateway-phase0.md §0).
  Do NOT pick up any envoy-gateway-phase* plan in this window.


## 7. Execution record — sun-window:2026-08-16 (PARTIAL, 1/3 nodes)

**Result: node 01 upgraded to v1.13.8. Nodes 02 + 03 remain on v1.13.7.**
Mixed patch versions across nodes is a supported Talos state; cluster left
fully healthy (80/80 Longhorn volumes healthy, Flux 0 not-ready, DNS + both
ingress VIPs verified serving).

### What happened
- **node 01 (192.168.55.11) — SUCCESS.** `task talos:upgrade-node IP=192.168.55.11`,
  6m28s. Ephemeral partition is wiped by this upgrade path, so 49/65 replicas
  rebuilt; full Longhorn reconvergence to 0 degraded took a further ~6 min.
- **node 02 (192.168.55.12) — ABORTED, not upgraded.** The drain hit the
  documented Longhorn `instance-manager` PDB block and timed out after ~5 min:
  `error when waiting for pod "instance-manager-…" in namespace "storage" to
  terminate: context deadline exceeded`. The task exited before the upgrade ran;
  the node was left **cordoned but still v1.13.7**.
- **Knock-on incident.** With node 02 cordoned, its evicted workloads all landed
  on node 01, and 34 RWO volumes wedged in `attaching` with 37 pods `Pending`
  (`AttachVolume.Attach failed … DeadlineExceeded`). Node 01 was NOT resource
  constrained (67% cpu / 66% mem) — this was Longhorn attach-concurrency, not
  scheduling pressure.
- **Recovery.** Uncordon node 02 (restores its instance-manager, which the cordon
  was itself blocking), then delete the 37 `Pending` pods so the scheduler
  redistributes them across all three nodes. Full recovery in ~8 min:
  0 pending, 80/80 volumes healthy.

### Why the roll was stopped at one node
Not a time-only decision. The drain path is currently broken on this cluster, and
the plumbed workaround (`EXTRA_FLAGS='--drain=false'`) is **untested here** and
plausibly worse — it skips graceful eviction, so it could reproduce the same
mass-reschedule pile-up less gracefully. Retrying into a known-bad path with
~35 min left, after an incident that took ~18 min to recover, risked ending the
window mid-roll on a degraded cluster.

### Before resuming nodes 02 + 03 — do this first
1. **Investigate the `instance-manager` PDB drain block.** It is described in
   `.taskfiles/talos/Taskfile.yaml` as "the node-03 footgun"; it fired on
   **node 02** this time, so it is not node-specific. Establish whether
   `--drain=false` is actually safe here, or whether Longhorn needs its
   `instance-manager` PDB / `node-drain-policy` setting adjusted before a drain.
2. **Expect the ephemeral wipe.** Each node loses its replicas and rebuilds
   (~6 min at 80 volumes). Budget ~13-15 min per node end-to-end, and never
   start the next node before `degraded == 0`.
3. **Watch for the attach pile-up.** If a drain aborts again, uncordon the node
   first (the cordon blocks instance-manager recovery), then delete `Pending`
   pods to spread attach load. Do not wait it out — it did not self-resolve.

### Verified good after the window (evidence, not Ready=True)
- k8s-gateway restarted twice unplanned (node 01 → 02 → 01) with the new
  Gateway API CRDs and logged `Synced all required resources`, **0** `could not
  sync` / `failed to list`. The latent CRD failure did **not** fire.
- DNS via 192.168.55.101 returns the correct VIPs by hand-check: internal hosts
  → 192.168.55.100, external hosts → 192.168.55.102 (not merely "some 192.168.x.x").
  Live HTTPS through both VIPs returns 302 (auth redirect).
- MariaDB digest-pinned image **pulled successfully on a cold node** (7.6s from
  registry) — the `IfNotPresent`/`latest`-digest ImagePullBackOff risk did not
  materialise.
- LibreChat logged `Connected to MongoDB` after its pod moved; NetworkPolicy OK.
- ingress-nginx serving all 102 ingresses; Envoy untouched (still 1 HTTPRoute).
