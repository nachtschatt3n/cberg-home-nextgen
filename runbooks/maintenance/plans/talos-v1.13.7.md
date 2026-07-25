---
plan_id: talos-v1.13.7
component: talos
pr: 194
kind: infra
current: "v1.13.6"
target: "v1.13.7"
update_type: patch
risk: medium                       # patch content is low-drama, but a full
                                   # rolling reboot of all 3 control-plane nodes
                                   # bounces every workload + stresses etcd quorum
est_duration_min: 90
needs_reboot: true                 # → only a window with allow_reboot:true (sun-window)
touches:
  namespaces: ["*"]                # every node reboots in turn → every namespace
                                   # bounces; kube-system (etcd/apiserver/cilium/
                                   # coredns) is the most sensitive
  resources: [talos/nodes, talos/etcd, daemonset/cilium, longhorn/replicas]
  shared: [cni, storage]           # cilium restarts on each rebooted node;
                                   # Longhorn volumes detach → reattach → rebuild
depends_on: []
conflicts_with: []                 # nothing else planned; but see Interference —
                                   # do NOT co-schedule any other reboot/infra plan
status: draft
window: "sun-window:2026-07-26"
auto_execute: false                # medium + reboot → always operator go/no-go
sops_refs:
  - docs/sops/talos-upgrade.md
  - docs/sops/application-update.md
  - docs/sops/crash-ghost-reaper.md
generated: "2026-07-25"
---

# Talos Linux v1.13.6 → v1.13.7 — rolling node OS upgrade

## 1. Summary & why held

**What changes:** Renovate PR #194 bumps `talosVersion: v1.13.6 → v1.13.7` in
`kubernetes/bootstrap/talos/talconfig.yaml` (the diff is one line — `additions:1
deletions:1`, only `talconfig.yaml`). `kubernetesVersion` stays `v1.36.0`, so
**there is no Kubernetes upgrade in this plan** (no `task talos:upgrade-k8s`).
The factory schematic (`talosImageURL` hash
`43b3cbfc…74cb99a3`) is unchanged — same extension set, same kernel args — so
no schematic regeneration at factory.talos.dev is needed.

**Why it was held (gate: policy):** the auto-updater's `deny` rule
`siderolabs/*` (`runbooks/auto-update-policy.yaml`) blocks any node-OS image
from auto-merge: *"Talos node image — needs a rolling node-reboot maintenance
window, not a git merge."* Merging the PR only rewrites a version string —
Talos machine configs are **not** Flux-reconciled (they live under
`kubernetes/bootstrap/`, applied out-of-band via `talosctl`). The actual
upgrade is a manual, one-node-at-a-time `talosctl upgrade` that **reboots each
control-plane node**. That is exactly what a reboot-capable window exists for.

**Upstream evidence — v1.13.7 is a genuine patch, no breaking change / no
migration** ([release notes](https://github.com/siderolabs/talos/releases/tag/v1.13.7)):
- `Linux: 6.18.38 → 6.18.39`, `containerd: 2.2.6`, `Go 1.26.5` — point bumps.
- Fixes, several of them favourable to *this* cluster's known failure modes:
  - `"oom podruntime protection"` — hardens pod-runtime against OOM.
  - `"do not block volume lifecycle teardown on failed user volumes"` —
    directly relevant to Longhorn detach/reattach during the rolling reboot.
  - `"make audit restartable"`, `"do proper backoff for NTP Kiss-of-Death
    responses"`, `"provide correct handler for Ctrl-Alt-Delete sequence"`.
  - New feature `"add --no-reboot flag to upgrade cmd"` (not used here — we
    *want* the reboot to land the new kernel).
- Release notes carry **no breaking changes, no migration steps, no etcd/kubelet
  config changes**.

So the *content* risk is low; the risk that sets `risk: medium` +
`needs_reboot: true` is purely the **blast radius of rebooting all three
hyper-converged control-plane nodes** (etcd quorum, Cilium, Longhorn replica
rebuild, every workload restarts once). This is not a false-positive hold — the
policy correctly routed a node-reboot item here.

## 2. Pre-checks

Run all from repo root (`cd /Users/mu/code/cberg-home-nextgen`). **All must
pass before touching any node.** Follow `docs/sops/talos-upgrade.md` §Step 0.

```bash
# 2.1 All three nodes Ready, current version is the expected v1.13.6
mise exec -- kubectl get nodes -o wide
mise exec -- talosctl version --nodes 192.168.55.11,192.168.55.12,192.168.55.13 --short | grep Tag
# Expected: three "Tag: v1.13.6" lines.

# 2.2 etcd quorum healthy on all members (this is the gate that must hold
#     between every node — capture the baseline now)
mise exec -- talosctl etcd members --nodes 192.168.55.11
mise exec -- talosctl etcd status  --nodes 192.168.55.11,192.168.55.12,192.168.55.13
# Expected: 3 members, all with a leader, no ERRORS/alarms.

# 2.3 No in-flight Flux reconcile (everything Ready)
mise exec -- flux get kustomizations -A | grep -vE "True|^NAMESPACE"   # empty
mise exec -- flux get helmreleases   -A | grep -vE "True|^NAMESPACE"   # empty

# 2.4 All Longhorn volumes healthy (no pre-existing degradation)
mise exec -- kubectl get volume -n storage -o json | python3 -c "
import sys,json
n=sum(1 for v in json.load(sys.stdin)['items'] if v['status'].get('robustness')!='healthy')
print(f'Unhealthy volumes: {n}')"
# Expected: Unhealthy volumes: 0

# 2.5 Fresh Longhorn backup (< 24h) — recovery floor if a node loses data
mise exec -- kubectl get jobs -n storage | grep daily-backup-all-volumes | tail -1
# Expected: last job Complete within 24h. If not, do NOT proceed — trigger a
# backup first (docs/sops/backup.md).

# 2.6 Zero firing Prometheus alerts (Watchdog/InfoInhibitor excluded)
mise exec -- bash -c 'kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &>/dev/null &
sleep 2
curl -s http://localhost:9090/api/v1/alerts | python3 -c "
import sys,json
a=[x for x in json.load(sys.stdin)[\"data\"][\"alerts\"] if x[\"state\"]==\"firing\" and x[\"labels\"][\"alertname\"] not in (\"Watchdog\",\"InfoInhibitor\")]
print(f\"Firing: {len(a)}\")"
kill %1 2>/dev/null'
# Expected: Firing: 0

# 2.7 crash-ghost-reaper is ACTIVE (post-reboot ghost safety net, DRY_RUN=false
#     since 2026-07-22). Graceful reboots shouldn't leave ghosts, but confirm
#     the reaper is armed in case a node returns ungracefully.
mise exec -- kubectl get cronjob -n kube-system crash-ghost-reaper \
  -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].env}{"\n"}'
# Expected: DRY_RUN "false".

# 2.8 talosctl client is within n±1 of the cluster (v1.13.x). We only run
#     upgrade-node (not upgrade-k8s), so this is low-risk, but confirm.
mise exec -- talosctl version --client --short
```

**Go criteria:** three nodes on v1.13.6 + Ready, 3 healthy etcd members, all
Flux Ready, 0 unhealthy Longhorn volumes, backup < 24h, 0 firing alerts,
reaper armed. Any failure → **stop and surface** (do not start the roll).

## 3. Steps

**GitOps first, then the rolling reboot. One node at a time, with an etcd +
Longhorn health gate between each (talos-upgrade.md lesson #12: back-to-back
node ops cause etcd leader-election storms → brief cluster NotReady).** The
maintenance-window-agent delegates the git changes to `cberg-agent`; the
`talosctl` operations are the operator-present part of the window.

### 3a. Land the version bump in git

```bash
cd /Users/mu/code/cberg-home-nextgen

# Merge Renovate PR #194 (one-line talosVersion v1.13.6 → v1.13.7). Do NOT rely
# on the merge to change the cluster — it only updates the source-of-truth
# string. Equivalent manual edit if not merging the PR:
#   kubernetes/bootstrap/talos/talconfig.yaml : talosVersion: v1.13.6 -> v1.13.7
git pull

# Regenerate the SOPS-encrypted per-node clusterconfigs from the new talconfig.
# (Renovate's PR does NOT regenerate these — it only touches talconfig.yaml.)
mise exec -- task talos:generate-config

# Sanity: version string propagated into generated configs
grep -H "v1.13.7" kubernetes/bootstrap/talos/clusterconfig/kubernetes-k8s-nuc14-01.yaml \
  2>/dev/null || echo "NOTE: clusterconfigs are SOPS-encrypted; verify via talhelper output above"

# Commit the regenerated clusterconfigs
git add kubernetes/bootstrap/talos/clusterconfig/ kubernetes/bootstrap/talos/talconfig.yaml
git commit -m "feat(talos): upgrade nodes v1.13.6 -> v1.13.7 (PR #194)"
git push
```

### 3b. Rolling node upgrade — node 01 (192.168.55.11)

```bash
mise exec -- task talos:upgrade-node IP=192.168.55.11
# (task reads TALOS_VERSION=v1.13.7 from talconfig.yaml via yq, uses the
#  unchanged factory schematic image, graceful default-mode reboot, --timeout=10m)
```

**Health gate — do NOT proceed to node 02 until ALL pass:**

```bash
# node back Ready on v1.13.7
mise exec -- kubectl get nodes
mise exec -- talosctl version --nodes 192.168.55.11 --short | grep Tag   # v1.13.7

# etcd: 3 members, healthy, node 01 rejoined
mise exec -- talosctl etcd members --nodes 192.168.55.11
mise exec -- talosctl etcd status  --nodes 192.168.55.11,192.168.55.12,192.168.55.13

# Longhorn replicas on nuc14-01 back to running (rebuild ~10-15 min)
mise exec -- kubectl get replica -n storage -o json | python3 -c "
import sys,json
rs=json.load(sys.stdin)['items']
deg=[r['metadata']['name'] for r in rs if r['spec'].get('nodeID')=='k8s-nuc14-01' and r['status'].get('currentState')!='running']
print(f'nuc14-01 replicas not running: {len(deg)}')"
# Expected: 0

# No lingering ghost pods from the reboot (reaper should auto-clear within 15m
# if any appeared; a graceful reboot normally leaves none)
mise exec -- kubectl get pods -A -o json | python3 -c "
import sys,json
p=json.load(sys.stdin)['items']
def ghost(x):
    s=x.get('status',{}); css=s.get('containerStatuses') or []
    return not x['metadata'].get('deletionTimestamp') and s.get('reason')=='NodeLost' or (bool(css) and all((c.get('state',{}).get('terminated',{}) or {}).get('reason') in ('Unknown','ContainerStatusUnknown') for c in css))
g=[(x['metadata']['namespace'],x['metadata']['name']) for x in p if ghost(x)]
print(f'ghosts: {len(g)} {g[:5]}')"
# Expected: ghosts: 0. If >0 and owner-managed, wait one reaper cycle (15m) or
# see docs/sops/crash-ghost-reaper.md.
```

### 3c. Node 02 (192.168.55.12) — same command + same health gate

```bash
mise exec -- task talos:upgrade-node IP=192.168.55.12
# then repeat the full 3b health gate with nodeID=k8s-nuc14-02
```

### 3d. Node 03 (192.168.55.13) — same command + same health gate

```bash
mise exec -- task talos:upgrade-node IP=192.168.55.13
# then repeat the full 3b health gate with nodeID=k8s-nuc14-03
```

> **Known footgun (talos-upgrade.md lesson #1):** node 03 has twice hung in
> `stage: rebooting` after a `powercycle`. The `upgrade-node` task uses a
> graceful default reboot so this is unlikely, but if node 03 does not return:
> `mise exec -- talosctl reboot --mode default --nodes 192.168.55.13 --wait`
> (see `docs/troubleshooting/talos-powercycle-stuck.md`).
>
> **Known footgun (lesson #7):** if a node's drain phase hits an eviction
> rate-limiter, re-run that one node with
> `mise exec -- task talos:upgrade-node IP=<ip> EXTRA_FLAGS="--drain=false"`.
> Reserve `--drain=false` for that specific failure only — descheduler + kubelet
> eviction clean up afterward and Longhorn replicas re-attach normally.

**No `task talos:upgrade-k8s`** — `kubernetesVersion` is unchanged (`v1.36.0`).

## 4. Verification

```bash
# 4.1 All three nodes on v1.13.7 (one unique Tag)
mise exec -- talosctl version --nodes 192.168.55.11,192.168.55.12,192.168.55.13 --short | grep Tag | sort -u
# Expected: single line "Tag: v1.13.7"

# 4.2 New kernel is live on every node
for ip in 192.168.55.11 192.168.55.12 192.168.55.13; do
  echo "=== $ip ==="; mise exec -- talosctl version --nodes $ip --short | grep Tag
done
mise exec -- talosctl read /proc/version -n 192.168.55.11   # Expected: 6.18.39

# 4.3 Schematic kernel args survived the upgrade (lesson #13 — hugepages/i915
#     can drop if a node booted an older install). Same schematic hash → same args.
for ip in 192.168.55.11 192.168.55.12 192.168.55.13; do
  echo "=== $ip ==="
  mise exec -- talosctl read /proc/cmdline -n $ip | tr ' ' '\n' | grep -E 'hugepages|i915|intel_iommu|mitigations'
done
# Expected per node: hugepages=1024, i915.enable_guc=3, intel_iommu=on, mitigations=off

# 4.4 etcd healthy, 3 members
mise exec -- talosctl etcd status --nodes 192.168.55.11,192.168.55.12,192.168.55.13

# 4.5 All Flux Kustomizations + HelmReleases Ready
mise exec -- flux get kustomizations -A | grep -vE "True|^NAMESPACE"   # empty
mise exec -- flux get helmreleases   -A | grep -vE "True|^NAMESPACE"   # empty

# 4.6 All Longhorn volumes healthy (rebuild complete)
mise exec -- kubectl get volume -n storage -o json | python3 -c "
import sys,json
n=sum(1 for v in json.load(sys.stdin)['items'] if v['status'].get('robustness')!='healthy')
print(f'Unhealthy volumes: {n}')"
# Expected: 0

# 4.7 No ghost pods, no crashlooping workloads
mise exec -- kubectl get pods -A | grep -vE "Running|Completed|^NAMESPACE" || echo "all pods Running/Completed"

# 4.8 Zero firing alerts
mise exec -- bash -c 'kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &>/dev/null &
sleep 2
curl -s http://localhost:9090/api/v1/alerts | python3 -c "
import sys,json
a=[x for x in json.load(sys.stdin)[\"data\"][\"alerts\"] if x[\"state\"]==\"firing\" and x[\"labels\"][\"alertname\"] not in (\"Watchdog\",\"InfoInhibitor\")]
print(f\"Firing: {len(a)}\")"
kill %1 2>/dev/null'
# Expected: Firing: 0
```

**Success = all three nodes report `Tag: v1.13.7`, kernel 6.18.39, 3 healthy
etcd members, all Flux Ready, 0 unhealthy Longhorn volumes, 0 ghosts, 0 firing
alerts.**

## 5. Rollback

Talos keeps the previous installed image, so a within-minor rollback
(`v1.13.7 → v1.13.6`) is a clean per-node operation — no K8s downgrade, no
schematic change. Longhorn replicas stay on their data during rollback.

### 5.1 A single node fails to return / verification fails on one node

```bash
# Roll that node back to the previous (v1.13.6) image
mise exec -- talosctl rollback --nodes <ip>
# Confirm it returns Ready + rejoins etcd:
mise exec -- kubectl get nodes
mise exec -- talosctl etcd members --nodes <ip>
mise exec -- talosctl version --nodes <ip> --short | grep Tag   # back to v1.13.6
```

Then **stop the roll** — do not advance to the next node. Leave the remaining
nodes on whatever version they're on (mixed v1.13.6/v1.13.7 within the same
minor is fine as a resting state), file the issue, and re-plan.

### 5.2 Full revert (abort the upgrade entirely)

```bash
cd /Users/mu/code/cberg-home-nextgen
git log --oneline -5 -- kubernetes/bootstrap/talos/
git revert <upgrade-commit-sha>            # restores talconfig + clusterconfigs to v1.13.6
mise exec -- task talos:generate-config
git add kubernetes/bootstrap/talos/ && git commit -m "Rollback Talos v1.13.7 -> v1.13.6" && git push

# Roll any already-upgraded node back to v1.13.6:
for ip in 192.168.55.11 192.168.55.12 192.168.55.13; do
  mise exec -- talosctl rollback --nodes $ip     # only where it went to v1.13.7
done
```

**Confirm cluster is back:** all nodes `Tag: v1.13.6` + Ready (4.1), 3 healthy
etcd members (4.4), all Flux Ready (4.5), 0 unhealthy Longhorn volumes (4.6).

## 6. Interference notes

- **Reboot-capable window only.** `needs_reboot: true` — this can run **only**
  in `sun-window` (`allow_reboot: true`, operator-present). Assigned to
  `sun-window:2026-07-26`. The Tue/Thu 1h slots (`allow_reboot: false`) must
  never host it. Risk weight 2 against the sun-window `capacity_risk: 6`.
- **Serialize with any other reboot/infra plan — do NOT co-schedule.** Even
  though `conflicts_with` is empty (no other plan exists yet), a second Talos or
  node-level plan in the same window would compound reboots and risk etcd
  quorum. If the window agent finds another `needs_reboot` or `shared: [cni]` /
  `shared: [storage]` plan for the same slot, run this one **alone** and defer
  the other. This plan owns the whole window.
- **Every workload bounces once.** All three control-plane nodes drain + reboot
  sequentially, so `touches.namespaces: ["*"]`. Expect brief per-node
  disruption to every ingressed app, databases, and Home Assistant as pods
  reschedule. Nothing needs pre-stopping — the graceful drain + Longhorn
  reattach handle it.
- **etcd quorum is the hard constraint.** Only ever one node down at a time; the
  3b/3c/3d health gate (3 healthy etcd members before advancing) is
  non-negotiable (lesson #12). If etcd shows fewer than 3 healthy members after
  a node returns, **wait** — do not touch the next node.
- **Longhorn rebuild is the long pole (~10-15 min/node).** Total window budget
  90 min is realistic for 3 sequential reboots + reconvergence + verification
  (no K8s upgrade shortens it vs. a full minor bump). If replica rebuild on a
  node exceeds ~30 min, pause and check Longhorn before advancing.
- **crash-ghost-reaper is the post-reboot safety net.** Active (`DRY_RUN=false`)
  since 2026-07-22; it auto-clears any node-loss ghost pods within 15 min if a
  node returns ungracefully and leaves a pod holding a Longhorn RWO volume in
  `FailedMount`. Graceful `upgrade-node` reboots normally produce **no** ghosts;
  treat any ghost as a signal the reboot wasn't clean (verify that node).
- **cberg-agent does the GitOps; talosctl steps are operator-present.** The
  version bump/regenerate/commit is delegated; the per-node `talosctl upgrade`
  + health-gating is the operator-in-the-loop core of the window.
