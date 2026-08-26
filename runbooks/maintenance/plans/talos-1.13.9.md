---
plan_id: talos-1.13.9
component: Talos Linux              # MUST equal the version-check's component
                                    # string exactly: coverage.py keys a plan
                                    # solely on this field (keys = {component})
                                    # and the held item reports "Talos Linux".
                                    # Written as "talos" first, which matched
                                    # nothing, so the plan was invisible and
                                    # coverage kept the bump in NEEDS A PLAN.
pr: null
kind: os
current: "talosVersion v1.13.8 on all 3 nodes (k8s-nuc14-01/02/03)"
target: "talosVersion v1.13.9"
update_type: patch
risk: medium                          # patch content, but it reboots every node in the cluster
est_duration_min: 60
needs_reboot: true                    # 3 sequential node reboots
touches:
  namespaces: [all]                   # every workload is rescheduled as nodes cycle
  resources:
    - node/k8s-nuc14-01
    - node/k8s-nuc14-02
    - node/k8s-nuc14-03
    - kubernetes/bootstrap/talos/talconfig.yaml
  shared: [longhorn, cilium]          # storage detach/reattach + CNI restart on every node
depends_on: []
conflicts_with:
  - longhorn-1.12.1-engine            # both cycle Longhorn volumes; never the same window
status: awaiting-go                   # the 2026-08-24 GO was scoped to sun-window:2026-08-23,
                                      # which passed with 0 plans executed; voided 2026-08-26
                                      # (resolve --by superseded) and a FRESH go/no-go issued for
                                      # sun-window:2026-08-30. A GO does not survive its window.
window: "sun-window:2026-08-30"       # only allow_reboot:true slot; conflicts_with longhorn-1.12.1-engine (scheduled tue-early:2026-08-25, different day)
auto_execute: false                   # never unattended: node reboots
security_ref: F-912f4778
sops_refs:
  - docs/sops/talos-upgrade.md
  - docs/sops/longhorn.md
  - docs/sops/backup.md
generated: "2026-08-19"
---

# Talos v1.13.8 → v1.13.9

## 1) Scope — and what this plan deliberately does NOT do

A **patch** release (2026-08-19): Linux 6.18.44, containerd 2.2.7, built with
Go 1.26.6. No Talos API or machine-config breaking changes.

**Only `talosVersion` moves.** `kubernetesVersion` stays at **v1.36.0**.

> Talos v1.13.9 *bundles* Kubernetes 1.36.3, and `docs/sops/talos-upgrade.md`
> Step 1 shows both versions being bumped together, because that SOP documents a
> combined OS + Kubernetes + performance-tuning sweep. They are independent
> knobs in `talconfig.yaml`: `talosVersion` picks the installer image,
> `kubernetesVersion` picks the kubelet. Bumping the kubelet is a **separate
> decision with its own blast radius** and is out of scope here. Do not let
> the SOP's example line pull it in.

Likewise **skip SOP Steps 2–6** (sysctls, kubelet patch, RPS mask, intelgpu,
udev). Those are the tuning sweep; none of them change for a patch bump. This
plan is Steps 1, 7, 8, 9 only.

## 2) Pre-flight

Verified 2026-08-19 while writing this plan — **re-verify at execution**:

- The factory schematic already publishes the target. Our three nodes all run
  schematic `43b3cbfc2957259b4588d362709d47387607901d4d3506c1ea46d7ea74cb99a3`
  (identical, and matching the live `extensions.talos.dev/schematic`
  annotation). A schematic is version-independent — it encodes extensions and
  kernel args, not the release — so **no regeneration at factory.talos.de is
  needed** unless extensions change:
  ```
  installer v1.13.8  -> 200
  installer v1.13.9  -> 200      # target exists for OUR schematic
  installer v1.13.10 -> 404      # v1.13.9 is newest
  ```
- All 3 nodes Ready, on v1.13.8, kubelet v1.36.0.
- Longhorn: **0 volumes degraded or faulted**, and every volume that must
  survive a reboot has >1 replica. Check before starting, not after:
  ```
  kubectl get volumes -n storage -o json | jq -r '.items[]
    | select(.status.robustness=="degraded" or .status.robustness=="faulted")
    | "\(.metadata.name) \(.status.robustness)"'
  ```
- Longhorn backups fresh (`docs/sops/backup.md`); a node that fails to come back
  is a restore, not a retry.
- Flux fully reconciled beforehand, so a failure during the window is
  attributable to the upgrade and not to in-flight drift.

## 3) Steps

1. `kubernetes/bootstrap/talos/talconfig.yaml`: `talosVersion: v1.13.8` →
   `v1.13.9`. **Leave `kubernetesVersion` alone** (§1).
2. Regenerate configs — SOP Step 7:
   `mise exec -- bash -c 'cd kubernetes/bootstrap/talos && talhelper genconfig'`
   (`SOPS_AGE_KEY_FILE` must be exported; the configs are SOPS-encrypted.)
3. Commit + push (SOP Step 8). Config generation is deterministic — review the
   diff and confirm the ONLY semantic change is the installer version.
4. Rolling upgrade, **one node at a time, verifying between each** (SOP Step 9):
   ```
   mise exec -- task talos:upgrade-node IP=192.168.55.11
   # verify §4, then:
   mise exec -- task talos:upgrade-node IP=192.168.55.12
   # verify §4, then:
   mise exec -- task talos:upgrade-node IP=192.168.55.13
   ```
   Do **not** run `task talos:upgrade-k8s` — that is the kubelet, out of scope.

> **The drain will sit for minutes on Longhorn, and that is normal.**
> `talosctl upgrade` installs the image first, then cordons and drains. The wait
> is Longhorn detaching volumes, **not** a stuck `instance-manager` PDB. Do not
> delete the PDBs and do not reach for `EXTRA_FLAGS='--drain=false'` —
> `docs/sops/talos-upgrade.md` §"The Longhorn instance-manager PDB drain block"
> explains why that reads as a hang when it is progress.

## 4) Verification after EACH node — contents, not shape

`Ready` returns before the node is genuinely carrying load, so Ready alone is
not the gate:

1. `kubectl get nodes` — the node reports **Talos (v1.13.9)** and `Ready`.
   Kubelet must still read **v1.36.0**; if it moved, the kubelet was bumped
   unintentionally (§1) — stop.
2. The node is **uncordoned** and actually has pods scheduled on it again
   (`kubectl get pods -A -o wide | grep <node>`), not merely Ready-and-empty.
3. **Longhorn replicas rebuilt**: no volume left `degraded`. This is the one
   that must gate the NEXT node — starting node N+1 while N's replicas are
   still rebuilding is how a multi-replica volume loses quorum.
4. No pods in CrashLoopBackOff or Pending that were not there before.

Cluster-wide at the end: all 3 nodes on v1.13.9, Longhorn all healthy, Flux
green, no firing alerts beyond Watchdog.

## 5) Rollback

Talos keeps the previous install; `talosctl rollback --nodes <ip>` returns a
node to the prior image, and the git revert restores `talosVersion`. Roll back
the **affected node only** — the cluster tolerates a mixed patch level for the
duration, so a single bad node never forces reverting the ones that succeeded.

If a node does not return at all, it is a rebuild from `talconfig.yaml` plus a
Longhorn restore, which is why §2 requires fresh backups before the first
reboot.
