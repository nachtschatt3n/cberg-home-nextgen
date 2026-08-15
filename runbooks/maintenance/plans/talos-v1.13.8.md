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
status: scheduled
window: "sun-window:2026-08-16"     # operator-scheduled 2026-08-07 (reboot-capable slot)
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
