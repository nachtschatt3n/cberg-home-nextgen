---
plan_id: longhorn-1.12.1-chart
component: longhorn
pr: null
kind: chart
current: "chart 1.12.0"
target: "chart 1.12.1"
update_type: patch
risk: low                             # control-plane only: manager/CSI/UI roll.
                                      # Volume ENGINES are NOT touched (see §1).
est_duration_min: 15
needs_reboot: false
touches:
  namespaces: [storage]
  resources:
    - helmrelease/longhorn
    - deployment/longhorn-driver-deployer
    - daemonset/longhorn-manager
    - daemonset/longhorn-csi-plugin
  shared: []                          # deliberately NOT [storage] — see §6. This plan does not
                                      # move a single volume's engine and allocates no volume.
depends_on: []
conflicts_with: []                    # the storage-layer conflicts belong to the DRAIN half
                                      # (plan_id longhorn-1.12.1-engine), which is what the
                                      # five sibling plans actually declare against.
security_ref: null                    # the CVE driver is the ENGINE image; see the drain plan
status: vetted
window: "ad-hoc:2026-08-19"
auto_execute: false
sops_refs:
  - docs/sops/longhorn.md
  - docs/sops/storage-safety.md
generated: "2026-08-14"
revised: "2026-08-19"                 # SPLIT out of longhorn-1.12.1-engine by the
                                      # maintenance-window-agent on operator authorization
---

# Longhorn chart 1.12.0 → 1.12.1 (control plane only)

## 1) Summary & why this is its own plan

This is the **first half** of the former `longhorn-1.12.1-engine` plan, split on
operator authorization 2026-08-19.

The original plan bundled two operations with very different risk and — crucially —
very different *duration semantics*:

1. a bounded ~15 min chart bump (manager, CSI sidecars, UI), and
2. an **asynchronous, unbounded live engine upgrade** across every volume.

Five sibling plans declare `conflicts_with: longhorn-1.12.1-engine`
(`cilium-1.20.1`, `superset-pg-cutover`, `superset-6.1.0`,
`bitnamilegacy-exit-paperless-db`, `bitnamilegacy-exit-nextcloud-db`). Reading
their stated rationales, **every one of them is about the engine work**, not the
chart:

> "DB standup/restore must not run under **storage-engine work**"
> "Never pair **storage-engine work** with new-volume creation"
> "**live engine upgrade** rides the network the agents blip"
> "shared storage layer; a DB cutover must not run under **storage-engine work**"

Those plans need the drain **complete**, not merely "the window ended" — and
because the drain is asynchronous it can outlive its window. Bundling therefore
blocked far more work than the risk justified. Splitting lets the cheap, bounded
half land immediately and confines the real conflict to the drain.

**Why the chart bump does not start an engine upgrade.** Verified on the live
cluster 2026-08-19:

- `kubectl get setting -n storage concurrent-automatic-engine-upgrade-per-node-limit` → **`0`**
- `concurrentAutomaticEngineUpgradePerNodeLimit` is **absent** from
  `defaultSettings` in `kubernetes/apps/storage/longhorn/app/helmrelease.yaml`,
  and upstream's default for it is likewise `0`.

So Helm cannot flip it as a side effect of the version bump. The chart bump
creates the *v1.12.1 EngineImage* and makes it the default for **new** volumes;
existing volumes keep the engine they are on until the drain plan runs. That
stalled-engine behaviour is exactly the bug the drain plan fixes — here it is
the property that makes the split safe.

**This plan clears no security finding.** The CVE driver lives on the engine
image; only the drain clears it.

## 2) Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) the setting that makes this safe MUST be 0 — abort if not
kubectl get setting -n storage concurrent-automatic-engine-upgrade-per-node-limit -o jsonpath='{.value}{"\n"}'   # 0

# b) every volume healthy before touching the storage control plane
kubectl get volumes -n storage -o custom-columns=N:.metadata.name,S:.status.state,R:.status.robustness --no-headers | awk '$3!="healthy"'
#    expect NO rows

# c) record the engine distribution so §4 can prove it did NOT move
kubectl get volumes -n storage -o custom-columns=E:.status.currentImage --no-headers | sort | uniq -c > /tmp/lh-engines-before.txt
cat /tmp/lh-engines-before.txt    # 2026-08-19 baseline: 72 v1.11.2 + 21 v1.12.0 = 93

# d) chart target exists
helm search repo longhorn/longhorn --versions | head -3

# e) nothing else in flight
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
```

## 3) Steps

1. Marker: `runbooks/update-marker.sh add longhorn storage 1 "chart 1.12.0 -> 1.12.1 (control plane only)"`
2. Bump `kubernetes/apps/storage/longhorn/app/helmrelease.yaml` `version: "1.12.0"` → `"1.12.1"`.
3. Commit (hunk-scoped — shared worktree), push, `flux reconcile source git flux-system`
   then `flux reconcile hr -n storage longhorn`.
4. Watch the control plane roll:
   ```bash
   kubectl -n storage rollout status ds/longhorn-manager --timeout=10m
   kubectl -n storage rollout status ds/longhorn-csi-plugin --timeout=10m
   ```
5. Clear the marker.

## 4) Verification

```bash
# chart actually at 1.12.1 and Ready
kubectl get hr -n storage longhorn -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion}{"\n"}'   # True 1.12.1

# all storage pods Ready
kubectl get pods -n storage | awk '$3!="Running" && $3!="Completed" && NR>1'

# THE SPLIT'S SAFETY ASSERTION: engines did NOT move
kubectl get volumes -n storage -o custom-columns=E:.status.currentImage --no-headers | sort | uniq -c > /tmp/lh-engines-after.txt
diff /tmp/lh-engines-before.txt /tmp/lh-engines-after.txt && echo "ENGINES UNCHANGED — split held"
# a v1.12.1 EngineImage may now EXIST (expected, it is the new default for new
# volumes); what must not happen is volumes migrating onto it in this plan.
kubectl get setting -n storage concurrent-automatic-engine-upgrade-per-node-limit -o jsonpath='{.value}{"\n"}'   # still 0

# every volume still healthy + attached
kubectl get volumes -n storage -o custom-columns=N:.metadata.name,S:.status.state,R:.status.robustness --no-headers | awk '$3!="healthy"'

# CSI still provisions/attaches: a stateful app can still restart
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
```

## 5) Rollback

Clean `git revert` + reconcile — no data-path change was made, so this is a
genuine rollback rather than a roll-forward:

```bash
git revert <sha> && git push
flux reconcile source git flux-system && flux reconcile hr -n storage longhorn
kubectl -n storage rollout status ds/longhorn-manager --timeout=10m
```

If volumes somehow began migrating engines (they must not — see §4), STOP by
setting the concurrency limit to `0` immediately; already-migrated volumes are
on a newer supported engine and are left alone (engines do not downgrade live).

## 6) Interference notes

- **`shared:` is intentionally empty**, unlike the drain plan's `[storage]`.
  This plan rolls the storage *control plane*, not the data path: attached
  volumes keep serving through a manager/CSI restart because engine processes
  are separate from the manager. What it does briefly perturb is **new
  attach/detach and provisioning**, so do not run it concurrently with a plan
  that creates a volume or restarts a stateful workload. In the 2026-08-19
  ad-hoc session it runs at step 2, hours before the volume-creating
  `bitnamilegacy-exit-*` plans — fully settled by then.
- It does **not** inherit the five sibling `conflicts_with` declarations; those
  correctly name `longhorn-1.12.1-engine`, which remains the drain.
- Not to be co-scheduled with a Talos node roll (manager DaemonSet + drain).
