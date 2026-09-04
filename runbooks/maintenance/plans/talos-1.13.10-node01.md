---
plan_id: talos-1.13.10-node01
component: Talos Linux              # same component string as part 1 — coverage.py
                                    # keys a plan on this field, so node 01 stays
                                    # covered after part 1 is marked executed.
pr: 208                             # ghcr.io/siderolabs/installer v1.13.8 -> v1.13.10
kind: os
current: "talosVersion v1.13.8 on k8s-nuc14-01 (nodes 02 and 03 already on v1.13.10 from part 1)"
target: "talosVersion v1.13.10"
update_type: patch
risk: medium                        # single node, but it is the LAST control-plane
                                    # node of a 3-node cluster and the roll is one-way
est_duration_min: 45                # 5 pre-checks + 25-35 node + 5 final verification
needs_reboot: true                  # 1 node reboot
capability_change: false
rollback_class: one-way             # node-image roll-forward, same as part 1
touches:
  - all namespaces (node drain)
  - k8s-nuc14-01
  - kubernetes/bootstrap/talos/talconfig.yaml
depends_on:
  - talos-1.13.10                   # HARD dependency. Do NOT run this before part 1
                                    # has completed and been verified. If part 1 was
                                    # aborted mid-sequence, re-scope this plan first.
conflicts_with: []                  # deliberately empty and VERIFIED empty, not
                                    # inherited. Part 1's conflicts are re-checked at
                                    # execution; nothing is scheduled into 09-13 today.
security_ref: null
finding_refs: [F-912f4778]
status: scheduled                   # OPERATOR GO 2026-09-05 (same GO as part 1 —
                                    # the operator approved the upgrade, the split is
                                    # only how it is sequenced).
window: "sun-attended:2026-09-13"   # PART 2 of 2. sun-attended is the only
                                    # allow_reboot:true slot.
sops_refs: []
generated: "2026-09-05"
---

# Talos v1.13.10 — part 2 of 2: node k8s-nuc14-01

**Part 1 is `talos-1.13.10.md` and carries the full procedure.** This file is
deliberately thin: it exists so node 01 has its own dated window occurrence and
cannot be forgotten once part 1 is marked executed. That is not hypothetical —
`talos-1.13.9` was stranded for 17 days as an approved-but-undated plan.

## 1 · Scope

One node: **k8s-nuc14-01**. Nodes 02 and 03 are already on v1.13.10 from part 1.

Between the two windows the cluster deliberately runs a **mixed patch level**
(v1.13.10 / v1.13.10 / v1.13.8) for one week. Talos supports this; etcd runs 3/3
throughout. It is a documented, accepted state — not drift to be alarmed by, and
specifically not something for the sweep to flag as a version inconsistency.

## 2 · Pre-checks

Run **§2 of part 1 in full**, plus:

- [ ] Part 1 completed and verified — nodes 02 and 03 both report `v1.13.10`,
      `Ready`, and carry no `NotReady`/`SchedulingDisabled` residue:
      `talosctl -n <02>,<03> version` and `kubectl get nodes -o wide`
- [ ] etcd healthy and **3/3 members**, not 2/3 — a degraded member from part 1
      must be fully recovered before the last control-plane node is touched
- [ ] Longhorn: 0 degraded, 0 rebuilding volumes. Rebuilds triggered by part 1
      have a week to finish; if any are still running, **stop** and investigate
      rather than draining
- [ ] §2.10 factory-tag pre-check re-run — the installer tag must resolve. It
      could not be proven from the planning host (a TLS-intercepting middlebox
      returned 302 even for a bogus `v9.9.9`, so the probe could not
      distinguish a real tag from a fake one)

## 3 · Execution

Follow **§3 of part 1** for node 01 only.

This is the **last control-plane node**. When it drains and reboots, etcd runs
on 2 of 3 members with no spare — there is no second failure budget. If etcd is
not cleanly 3/3 beforehand, do not start.

## 4 · Verification

Run **§4 of part 1** for node 01, then §4.5 cluster-wide, and additionally:

- [ ] All three nodes report `v1.13.10` — the mixed-version state is now closed
- [ ] `kubectl get nodes` — 3/3 `Ready`, none `SchedulingDisabled`
- [ ] etcd 3/3, no leader-election churn in the last 10 minutes
- [ ] Longhorn: 94 volumes attached/healthy, 0 degraded, 0 rebuilding
- [ ] `snapshot-controller` in `storage` is `Running` and its leader election
      settled — it was added 2026-09-04 (5787cf3d) and, as of part 1, had never
      survived a node roll
- [ ] Flux: all Kustomizations and HelmReleases `Ready`

## 5 · Rollback

**One-way**, same as part 1 — a Talos node upgrade is not a git revert. Recovery
is roll-forward or restore from backup. Node 01 being the last control-plane
node is what makes this the riskiest of the three; §5 of part 1 applies verbatim.

## 6 · Interference

Nothing is scheduled into `sun-attended:2026-09-13` at time of writing —
re-check at execution rather than trusting this line. Longhorn replica rebuild
remains the per-node gate. **No VolumeSnapshot work in this window.**
