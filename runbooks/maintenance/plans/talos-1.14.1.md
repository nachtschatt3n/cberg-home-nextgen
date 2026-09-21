---
plan_id: talos-1.14.1
component: talos
pr: null                              # THE NODE IMAGE HAS NO RENOVATE PR — see §1
                                      # "Attribution". PR #212 is the talosctl CLI
                                      # pin in .mise.toml (retargeted upstream to
                                      # 1.14.1 on 2026-09-19) and is a SEPARATE
                                      # artifact, merged as the LAST step (§3.7).
kind: infra
current: "v1.13.10"                   # live on all 3 nodes, re-verified 2026-09-20
target: "v1.14.1"                     # released 2026-09-15; supersedes v1.14.0 (2026-09-03)
update_type: minor                    # one minor hop, but it SKIPS OVER v1.14.0 — §1 reviews
                                      # both release notes because we never run 1.14.0
risk: high                            # rolling reboot of every control-plane node in a
                                      # 3-node hyper-converged cluster: etcd quorum,
                                      # 94 Longhorn volumes at replica=2, and the ONLY
                                      # HTTP data plane (Envoy Gateway) all ride on it
est_duration_min: 145                 # RE-MEASURED 2026-09-20 — was 140 for v1.14.0.
                                      # IN-WINDOW only; Phase A prep (~30 min) is
                                      # Flux-inert and MUST run before the window.
                                      # +5 because node 03 now holds BOTH the VIP and
                                      # etcd leadership, so the final node carries a VIP
                                      # failover AND a leader re-election that the
                                      # v1.14.0 plan split across two nodes. See §7.
needs_reboot: true                    # three sequential node reboots
touches:
  namespaces:
    - kube-system                     # etcd, kube-apiserver, controller-manager,
                                      # scheduler, coredns, cilium, authentik
    - storage                         # longhorn-manager, instance-manager, CSI, 94 volumes
    - network                         # envoy-gateway, envoy-internal, envoy-external,
                                      # k8s-gateway, external-dns, adguard-home, cloudflared
    - monitoring                      # prometheus, alertmanager, grafana, edot-collector
    - "ALL (cluster-wide)"            # every pod on the cluster is evicted and
                                      # rescheduled once; this is not a scoped change
  resources:
    - kubernetes/bootstrap/talos/talconfig.yaml   # talosVersion — THE node image bump
    - kubernetes/bootstrap/talos/clusterconfig/   # talhelper-generated, SOPS-encrypted
    - .mise.toml                                  # talhelper pin (§3.5) + talosctl CLI pin (§3.7)
    - runbooks/auto-update-policy.yaml            # stale reason text (§3.3)
    - node/k8s-nuc14-01                           # 192.168.55.11 — CANARY (lightest)
    - node/k8s-nuc14-02                           # 192.168.55.12 — heaviest Longhorn load
    - node/k8s-nuc14-03                           # 192.168.55.13 — holds VIP .10 AND etcd leader
    - "etcd (3 members, 3.6.14 -> 3.7.1)"
    - "192 longhorn replicas / 94 volumes (numberOfReplicas: 2)"
  shared:
    - etcd                            # quorum 3; exactly ONE member may be down
    - cni/cilium                      # DaemonSet restarts per node
    - coredns                         # Talos-bundled version moves with the release
    - storage/longhorn                # instance-manager restart + replica rebuild per node
    - gateway/envoy                   # Envoy Gateway IS the only HTTP(S) data plane.
                                      # NOT "ingress": ingress-nginx was deleted 2026-09-07
                                      # (ad1ea7c2) and the plans README names this exact
                                      # miswording. The v1.14.0 plan said `ingress`.
    - cert-manager                    # webhook pods reschedule
    - monitoring                      # scrape gaps + node-level alerts during each reboot
depends_on: []
conflicts_with:                       # THIS PLAN NEEDS THE WHOLE sun-attended SLOT.
  - cilium-1.20.2                     # names talos-1.14.0 back; CNI under a node roll
  - flux-oci-chart-sources            # names talos-1.14.0 back
  - helm-drift-detection              # names talos-1.14.0 back
  - n8n-2.39.8                        # names talos-1.14.0 back
  - edot-collector-0.161.0            # names talos-1.14.0 back; its pod is evicted 3x
  - otel-operator-0.23.0              # names talos-1.14.0 back
  - kube-prometheus-stack-91.4.1      # ADDED — the v1.14.0 plan OMITTED it. §4 reads
                                      # Prometheus for its alert/target/rule gates, so a
                                      # same-night bump of the instrument invalidates the
                                      # measurement (plans README, conflicts_with rule).
  - multus-macvlan-foundation         # also mutates Talos machine config
  - authentik-pg17-decommission       # must not destroy the auth DB rollback in a window
                                      # that also reboots every node
  - nextcloud-34.0.4                  # sun-attended:2026-10-04 — declared in case THIS
  - jellyfin-12.1                     # sun-attended:2026-10-11 — plan slips to their date.
                                      # Today the minutes check already excludes them
                                      # (145+75 and 145+60 both exceed the 180 budget);
                                      # these entries survive a downward duration revision.
  # DROPPED vs the v1.14.0 plan: absenty-drop-npm-runtime (now `blocked`, window null, and
  # 145+90 > 180 so the scheduler refuses it on minutes) and authentik-pg18-lockstep (now
  # `executed`). Both entries existed only for the spent 2026-09-13 slot.
  # General rule, not a list: NO other plan may share this window (§6).
capability_change: true               # v1.14 changes node-level behaviour on upgrade:
                                      # containerd NRI now ENABLED by default,
                                      # net.ipv4.conf.*.send_redirects=0 by default,
                                      # etcd + kube-apiserver minimum TLS 1.3,
                                      # etcd HTTP endpoints move 2379 -> 2383,
                                      # containerd 2.2.7 -> 2.3.5.
                                      # => never unattended. Operator present.
rollback_class: one-way               # HONEST RATING — see §5. Per-node `talosctl rollback`
                                      # is real and is the CANARY's abort path, but it is one
                                      # boot-partition deep and does not unwind etcd 3.6->3.7.
                                      # Past the canary this is roll-forward / stop-in-place.
security_ref: null                    # no security driver
finding_refs:
  - F-912f4778                        # "Talos Linux (cluster nodes): v1.13.10 → v1.14.1"
                                      # — the finding's own title now names v1.14.1
  - F-0a32b505                        # "Plan talos-1.14.0 ... has drifted ... re-seek the
                                      # operator GO for the new target" — THIS FILE answers it
  - F-9a58f400                        # the PR #212 mis-attribution this plan carries forward
  # DROPPED F-fc435c71: resolved 2026-09-10 (window-capacity question, discharged).
  # An ownership claim on a closed finding is noise.
status: draft                         # re-drafted 2026-09-20 for the v1.14.1 re-target.
                                      # The 2026-09-12 operator GO covered v1.14.0 ONLY and
                                      # does NOT carry over — an approval is scoped to what
                                      # was reviewed. Needs re-vet, then a fresh GO.
window: "sun-attended:2026-09-27"     # inherited from the superseded talos-1.14.0, which
                                      # held this slot. sun-attended is the ONLY
                                      # allow_reboot window; a node roll may not be stamped
                                      # `now:` (on_demand has allow_reboot: false).
sops_refs:
  - docs/sops/talos-upgrade.md
  - docs/sops/application-update.md
  - docs/sops/longhorn.md
  - docs/sops/storage-safety.md
  - docs/sops/backup.md
  - docs/sops/disaster-recovery.md
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/monitoring.md
generated: "2026-09-20"
---

# Talos Linux node roll — v1.13.10 → v1.14.1

> **Supersedes `talos-1.14.0.md`.** Same work, new target. Every premise below was
> re-measured on 2026-09-20; nothing is carried forward from the 2026-09-09 draft.
> Where a number moved, the old value is shown so the drift is visible.

## 1) Summary & why held

Roll all three control-plane/worker nodes (`k8s-nuc14-01/02/03`, 192.168.55.11-.13,
VLAN 55) from Talos **v1.13.10** to **v1.14.1**, one node at a time, with a Longhorn
replica-rebuild gate between nodes. Kubernetes stays pinned at **v1.36.0** — this
window does **not** bump `kubernetesVersion`.

Held because it is the definition of a held update: it reboots every node in the
cluster.

### Why this file exists: the recorded GO is stale

The operator approved **v1.14.0** on 2026-09-12. Upstream published **v1.14.1** on
2026-09-15 16:41Z. An approval is scoped to what was reviewed, so the recorded GO does
not authorise v1.14.1, and executing v1.14.0 now would deliberately install a
superseded release on every control-plane node. Finding **F-0a32b505** called for
exactly this re-resolution; **F-58f0bbab** is the general form (upstream drift must be
caught *before* the GO, not mid-window).

**Measured 2026-09-20** — `gh api repos/siderolabs/talos/releases`:

| Tag | Published | Prerelease |
|---|---|---|
| **v1.14.1** | 2026-09-15 16:41Z | false ← **target** |
| v1.15.0-alpha.0 | 2026-09-08 | **true** — not a candidate |
| v1.14.0 | 2026-09-03 | false ← superseded |
| v1.13.10 | 2026-09-03 | false ← **live** |

v1.14.1 is the newest stable release on any line. `runbooks/check-all-versions.py`
agrees (*Latest stable Talos: v1.14.1*), as does finding **F-912f4778**, whose title
now reads `v1.13.10 → v1.14.1`.

### ATTRIBUTION — the correction this plan carries (F-9a58f400)

Two different artifacts have been conflated. They are not the same thing and they do
not move at the same time.

| | Artifact | What it is | Renovate | Reboot? |
|---|---|---|---|---|
| **A** | `kubernetes/bootstrap/talos/talconfig.yaml` → `talosVersion: v1.13.10` | **THE NODE IMAGE.** Feeds `talhelper gencommand upgrade`, which installs `factory.talos.dev/installer/<schematic>:<version>` on each node. | **No PR. Renovate-untracked.** | **YES — 3 reboots** |
| **B** | `.mise.toml` → `"aqua:siderolabs/talos" = "1.13.10"` | The **talosctl CLI** binary installed locally by mise/aqua on this Mac. Touches no node, no manifest, no cluster object. | **PR #212**, now titled `1.13.10 → 1.14.1` (retargeted 2026-09-19) | **No** |

The policy file already encodes this correctly: `runbooks/auto-update-policy.yaml`
carries a specific `aqua:siderolabs/talos` rule ABOVE the `siderolabs/*` glob (split
2026-09-13, F-1128fcdf), so #212 is now held for the right reason — *"it FOLLOWS a node
upgrade; it does not authorise one."*

**One convenient consequence of the re-target:** #212 now proposes **1.14.1**, exactly
the version this plan installs. Merging it at §3.7 lands the CLI pin on the cluster
version with no drift — under the v1.14.0 plan it would have left the pin a patch ahead.

**Why the node image still produces no PR.** `talconfig.yaml` line 3 carries
`# renovate: datasource=docker depName=ghcr.io/siderolabs/installer`, which the
`customManagers` regex in `.github/renovate.json5` does match. But v1.14.0's notes
state: *"The default installer image has been updated to use the Image Factory. The
`ghcr.io/siderolabs/installer` image is no longer published with releases."*
Re-measured 2026-09-20, with negative controls so the check can fail:

```
ghcr.io/siderolabs/installer:v1.13.10  -> HTTP 200
ghcr.io/siderolabs/installer:v1.14.0   -> HTTP 404
ghcr.io/siderolabs/installer:v1.14.1   -> HTTP 404
ghcr.io/siderolabs/installer:v9.9.9    -> HTTP 404   (control — proves 404 is real)

factory.talos.dev/installer/43b3cbfc…99a3:v1.13.10 -> HTTP 200
factory.talos.dev/installer/43b3cbfc…99a3:v1.14.0  -> HTTP 200
factory.talos.dev/installer/43b3cbfc…99a3:v1.14.1  -> HTTP 200   <- our schematic IS published
factory.talos.dev/installer/43b3cbfc…99a3:v9.9.9   -> HTTP 404   (control)
```

Renovate's docker datasource sees no 1.14.x for that repository and correctly emits
nothing. **This is permanent.** §3.2 repoints the annotation.

### THE SCHEMATIC — confirmed live, and a stale comment to correct

`talconfig.yaml` installs schematic `43b3cbfc…99a3`. **Verified against the running
nodes** (not just the repo) — `talosctl get machineconfig` on all three:

```
192.168.55.11/.12/.13  image: factory.talos.dev/installer/43b3cbfc…99a3:v1.13.10
```

That schematic carries the kernel args and extensions we depend on (`i915.enable_guc=3`,
`intel_iommu=on`, `mitigations=off`, `hugepages=1024`, plus `siderolabs/i915`,
`intel-npu`, `intel-ucode`, `iscsi-tools`, `mei`, `thunderbolt`, `util-linux-tools`,
`v4l-uvc-drivers`, `intel-ice-firmware`), and the live `/proc/cmdline` on all three
nodes matches it (`hugepages=1024`, `HugePages_Total: 1024`).

> **REPO CORRECTION (report, do not silently work around).**
> `kubernetes/bootstrap/talos/patches/global/machine-intelgpu.yaml` says the kernel args
> are baked into schematic **`b85cceac…68da`**. That schematic is NOT installed on any
> node, and it differs materially: it has **no `siderolabs/intel-npu` extension**.
> Following that comment during a recovery would silently drop the NPU extension.
> The comment should name `43b3cbfc…99a3`. Both schematics publish v1.14.1 (200/200,
> `v9.9.9` → 404 control), so this is a documentation defect, not a blocker.

### What we are actually traversing: v1.14.0 AND v1.14.1

The cluster never runs v1.14.0, so **both** sets of notes apply in one hop. Read against
the upstream release bodies for a cluster **upgraded** (not newly created) — the
distinction matters, because several of the loudest changes are opt-in and do **not**
apply to us.

#### From v1.14.0 — genuinely changes behaviour on upgrade

1. **etcd 3.6.14 → 3.7.1.** *"Talos is now compatible with etcd v3.6.x only … The
   default version is 3.7.0+ now."* Live measurement: `PROTOCOL 3.6.14`, `STORAGE 3.6.0`
   on all three members, so the prerequisite holds. This is the single biggest reason
   `rollback_class` is `one-way`: once a majority of members have advanced, unwinding is
   a snapshot restore, not a revert.
2. **etcd HTTP endpoints move `2379` → `2383`.** *"etcd metrics and the HTTP health
   endpoint are no longer reachable on 2379; scrape them on 2383 instead."*
   **This does not hit us, and §4 proves it rather than assuming it.** Talos runs etcd
   with a dedicated `--listen-metrics-urls` on **2381**, and the note says *"If
   `--listen-metrics-urls` was customized, the metrics should not move."* Verified live:
   `kube-prometheus-stack-kube-etcd` targets are `192.168.55.11:2381`, `.12:2381`,
   `.13:2381`, all three `up`.
3. **containerd NRI is no longer disabled by default.** Nothing here registers an NRI
   plugin, so the expected effect is nil — but it is a default flip on the container
   runtime and is part of why `capability_change: true`.
4. **`net.ipv4.conf.{all,default}.send_redirects=0` by default.** These nodes are not L3
   gateways (the UDM-Pro at 192.168.55.1 is), so no impact expected.
5. **etcd and kube-apiserver require TLS ≥ 1.3**, and custom cipher-suite settings are
   ignored. `talconfig.yaml` sets no cipher suites, so nothing to unwind.
6. **`--mode=reboot` removed from `talosctl apply-config`.** Our
   `.taskfiles/Talos/Taskfile.yaml` `apply-node` task uses `--mode={{.MODE}}` defaulting
   to `auto`. Unaffected — but do not hand-type `--mode=reboot` with a 1.14 client.
7. **CoreDNS moves with the release** (1.14.7). The cluster additionally runs its own
   CoreDNS HelmRelease; unchanged here.
8. **Flannel gets `EnableNFTables`** — inert for us, `cniConfig.name: none` (Cilium).

#### From v1.14.1 — what the extra patch buys us

v1.14.1 is **36 commits ahead of v1.14.0, 0 behind** (`gh api compare`). Component
deltas: **Linux 6.18.48 → 6.18.51**, **containerd 2.3.4 → 2.3.5**, Go 1.26.7 → 1.26.8.
etcd stays 3.7.1, Kubernetes default stays 1.37.0, CoreDNS stays 1.14.7.

Four of those 36 commits matter *specifically for this operation*:

- **`fix: prevent sandboxd signal dispositions leaking into services`** — `sandboxd` is
  new in 1.14 and runs on upgraded clusters too (see the correction below). A signal
  disposition leaking into services is exactly the class of fault that would show up as
  an unreliable `kubelet`/`cri` restart after a reboot. Taking 1.14.1 rather than
  1.14.0 avoids shipping that bug onto all three nodes.
- **`fix: improve resilience of the action tracker against dropped conns`** and
  **`fix: set TCP keepalive and user timeout on apid proxied connections`** — the action
  tracker is what `talosctl upgrade` uses to follow an upgrade to completion. This roll
  is driven from the Mac over the LAN, so a dropped connection mid-upgrade is a real
  failure mode; these harden precisely that path.
- **`fix: tighten the validation of v1alpha1 configs vs. migration`** — **directly
  relevant.** This plan deliberately does NOT migrate to the new multi-document config
  (§"Opt-in" below), so our config is exactly the v1alpha1-with-deprecations shape whose
  validation this commit changes. §3.6 reviews the generated diff by hand for that
  reason.

Also present and benign for us: `fix: harden the code around kubelet's client
certificate handling`, `fix(security): define the permissions the 6.18 kernel expects in
the classes`, `fix: guard against nil config document slices`. Changes that touch
hardware/boot paths we do not use (`overlay assets in ESP`, `GRUB ISOs only for BIOS`,
`USB settle`, `LVM`, `BGP/VRF`, `WireGuard over gRPC`, NixOS OVMF) are not applicable —
we boot NVMe by serial with no overlay, no LVM, no BGP.

> **Networking commits worth a second look, and why they are inert here.**
> `fix: empty searchdomains dropped on merge` and `fix: drop logical links if they no
> longer declare as logical`. Our `patches/global/machine-network.yaml` sets
> `disableSearchDomain: true` with three static nameservers and no logical links
> (no bonds, bridges or VLAN interfaces — one physical NIC per node selected by MAC).
> Neither fix changes our rendered network config. §3.6's diff review is the gate that
> would catch it if that reasoning is wrong.

#### Opt-in, and this plan deliberately does NOT opt in

9. **Workload isolation (`sandboxd`).** The notes are explicit: *"Clusters upgraded from
   older versions do not have this document and therefore keep the previous
   (non-isolated) behavior until it is added — upgrades change nothing on their own."*
   **DO NOT add a `SecurityProfileConfig` document in this window.** The same notes warn:
   *"With workload isolation enabled, the deprecated in-tree Kubernetes iSCSI volume
   plugin does not work."* Our storage is 94 Longhorn volumes over iSCSI. Longhorn uses
   its own CSI driver (the supported path), but flipping a node-isolation boundary
   underneath the iSCSI stack in the same window as a version roll would make any storage
   failure undiagnosable. Separate plan, separate window, or never.

   > **CORRECTION to the v1.14.0 plan.** That plan's §4.4 told the executor to run
   > `talosctl logs sandboxd` and expect it **absent/empty** as proof isolation stayed
   > off. That gate is wrong in both directions. `sandboxd` is the *service that anchors
   > the namespace* and is part of 1.14 regardless; v1.14.1 even ships a bug fix for it.
   > Expecting it to be absent would raise a false alarm on a perfectly correct upgrade.
   > §4.5 replaces it with an assertion on the **config document**, which is what
   > actually controls isolation. Baseline measured today: `securityprofileconfig` count
   > **0** on all three nodes, with a positive control proving the grep works.

10. **`FilesystemTrimConfig`** — absent on upgraded clusters, so periodic fstrim stays
    off. We already run explicit `*-filesystem-trim` CronJobs in `storage`. Leave it.
11. **Multi-document config migration** (`SysctlConfig`, `UdevRulesConfig`,
    `KubeNodeConfig`, `UnattendedInstall`, `KubeProxyConfig`, `ResolverConfig`,
    `DiscoveryServiceConfig`, …). Every v1alpha1 field this repo uses is **deprecated but
    still supported**. **Do not migrate any of it in this window.** A config-shape
    migration and a node roll must not fail together.
12. **Dedicated system volumes / LVM / RAID / BGP / DoT-DoH / NTS** — all new opt-in
    features. Not configured, not enabled, out of scope.

### Kubernetes compatibility — OPEN ITEM #1 FROM THE v1.14.0 PLAN IS NOW CLOSED

The v1.14.0 plan could not machine-read the support matrix (the docs site renders it in
JavaScript) and left it as a Phase-A to-do. **Resolved from upstream code**, which is
authoritative and diffable —
`pkg/machinery/compatibility/talos114/talos114.go` @ tag `v1.14.1`:

```go
// MinimumHostUpgradeVersion is the minimum version of Talos that can be upgraded to 1.14.
var MinimumHostUpgradeVersion = semver.MustParse("1.12.0")
// MaximumHostDowngradeVersion is the maximum (not inclusive) version of Talos that can be downgraded to 1.14.
var MaximumHostDowngradeVersion = semver.MustParse("1.16.0")
// MinimumKubernetesVersion is the minimum version of Kubernetes is supported with 1.14.
var MinimumKubernetesVersion = semver.MustParse("1.32.0")
// MaximumKubernetesVersion is the maximum version of Kubernetes is supported with 1.14.
var MaximumKubernetesVersion = semver.MustParse("1.37.99")
```

Two conclusions, both load-bearing:

- **Our v1.13.10 → v1.14.1 hop is explicitly supported** (1.13.10 ≥ 1.12.0). Talos does
  not require passing through 1.14.0.
- **Our pinned Kubernetes v1.36.0 sits inside 1.32.0 – 1.37.99**, so leaving
  `kubernetesVersion` untouched is supported, not merely tolerated. `upgrade-k8s` is
  **not** part of this window.

### The tooling constraint that gates the whole plan

**`talhelper` is end-of-life.** Release **v3.1.17 (2026-08-26)** is the last one; the
repo pins **3.1.11**. Re-measured today against a scratch copy carrying
`talosVersion: v1.14.1`:

```
$ talhelper validate talconfig <scratch>/talconfig.yaml
There are issues with your talhelper config file:
field: "talosVersion"
  * WARNING: "v1.14.1" might not be compatible with this Talhelper version you're using
exit=0
```

Cause, confirmed from talhelper's own `go.mod` (with a `v9.9.9` → HTTP 404 control):
3.1.11 embeds `siderolabs/talos/pkg/machinery v1.14.0-alpha.1`; the final release 3.1.17
embeds `v1.14.0-alpha.2`. Neither embeds GA machinery, so the warning fires on the
version string and **no talhelper release will ever clear it** — it fired identically for
v1.14.0. The warning is not a blocker (exit 0), but it means **talhelper is not the
validator here — the generated diff and the canary node are.** §3.6 reviews the diff by
hand; §4.1 gates on node 01 actually booting.

## 2) Pre-checks

Run all of these **inside the window, before touching a node**. Every one has a stated
pass condition; a fail is a no-go, not a note. Baselines are from **2026-09-20**.

```bash
cd /Users/mu/code/cberg-home-nextgen
export KUBECONFIG="$PWD/kubeconfig"
export TALOSCONFIG="$PWD/kubernetes/bootstrap/talos/clusterconfig/talosconfig"
```

**2.1 — No other plan is mid-flight.** This window is exclusive.

```bash
.venv/bin/python3 runbooks/maintenance-plan.py --open
```
**PASS:** no other plan carries `sun-attended:2026-09-27`. **Also confirm
`talos-1.14.0` is NOT listed as executable** — it must be `superseded`, or the slot is
double-booked at 145+140 min (§6).

**2.2 — Nodes healthy and all on v1.13.10.**

```bash
mise exec -- kubectl get nodes -o wide
```
**PASS:** 3× `Ready`, `Talos (v1.13.10)`, kubelet `v1.36.0`.
*(Baseline: kernel `6.18.48-talos`, containerd `2.2.7`. Note both move: kernel →
6.18.51, containerd → 2.3.5.)*

**2.3 — etcd quorum, and confirm we are on 3.6.x (the v1.14 prerequisite).**

```bash
mise exec -- talosctl -n 192.168.55.11 etcd members
mise exec -- talosctl -n 192.168.55.11,192.168.55.12,192.168.55.13 etcd status
```
**PASS:** exactly 3 members, no `LEARNER`, empty `ERRORS`, converged `RAFT INDEX`, and
`PROTOCOL` reporting **3.6.x**.
*(Baseline: PROTOCOL 3.6.14 / STORAGE 3.6.0, leader `73a201c6b4bf6faf` =
**k8s-nuc14-03**, raft term 65, index 402848902 identical on all three, DB 821–859 MB
with 140 MB in use.)* **If `PROTOCOL` is not 3.6.x, STOP** — v1.14 states compatibility
with 3.6.x only.

**2.4 — Re-derive the roll order. THE ORDER CHANGED since the v1.14.0 plan.**

```bash
# VIP owner (192.168.55.10) — must be the LAST node rolled
for ip in 192.168.55.11 192.168.55.12 192.168.55.13; do
  echo -n "$ip vip=" ; mise exec -- talosctl -n $ip get addresses 2>/dev/null | grep -c '192.168.55.10/32'
done
# Longhorn attach load per node
mise exec -- kubectl get volumes -n storage \
  -o custom-columns='NODE:.status.currentNodeID' --no-headers | sort | uniq -c
```
**PASS:** exactly one node reports `vip=1`.
*(Baseline 2026-09-20: **VIP on `k8s-nuc14-03`** — it was on 02 in the v1.14.0 plan.
Attached volumes 01=17, 02=45, 03=30, plus 2 detached. So **node 03 now holds the VIP
AND etcd leadership simultaneously**; §3.5 re-derives the order from that, and §7 prices
the extra 5 minutes it costs.)*

**2.5 — Longhorn: every volume healthy, with the two expected exceptions named.**

```bash
mise exec -- kubectl get volumes -n storage -o json | python3 -c "
import sys,json,collections
d=json.load(sys.stdin)['items']
bad=[(v['metadata']['name'],v['status'].get('robustness'),v['status'].get('state')) for v in d
     if v['status'].get('robustness')!='healthy']
print('total',len(d),'not-healthy',len(bad))
for b in bad: print('  ',b)
print('replica counts:',collections.Counter(v['spec'].get('numberOfReplicas') for v in d))
print('state:',collections.Counter(v['status'].get('state') for v in d))"
```

**PASS:** `total 94`, and the not-healthy set is **exactly these two, and no others**:

```
('icloud-docker-mu-session', 'unknown', 'detached')
('pvc-f6ec0213-4b00-49d9-93b4-954d5fee1d31', 'unknown', 'detached')   # PVC icloud-docker-andrea-session
```

> **This gate was WRONG in the v1.14.0 plan and would have false-failed the window.**
> That plan asserted *"the live reading is 93/93 healthy with zero detached… Any
> non-healthy or detached volume is now a no-go."* Today there are **94** volumes and
> **two** are legitimately detached: both `icloud-docker` session volumes in namespace
> `backup`, whose Deployments (`icloud-docker-mu`, `icloud-docker-andrea`) are scaled
> **0/0** and have been for 33 days. Longhorn only computes `robustness` while a volume
> is attached, so `unknown` on a deliberately-detached volume is the expected reading,
> not a fault. Both still back up nightly (`lastBackupAt` 2026-09-20 03:07/03:08Z).
> A gate that cries wolf gets waved through on the one occasion it is real.

**Any THIRD non-healthy volume is a no-go.** **PASS also:** `replica counts:
Counter({2: 94})`. **This is the number that sizes the gate.** At `numberOfReplicas: 2`
across 3 nodes, taking one node down leaves a large share of volumes on a single replica
— degraded but serving. There is no spare-replica cushion.

**2.6 — Backups fresh.** `docs/sops/backup.md` warns `lastBackupAt` can lag one cycle.

```bash
mise exec -- kubectl get jobs -n storage --sort-by=.status.startTime \
  | grep daily-backup-all-volumes | tail -1
mise exec -- kubectl get volumes -n storage -o json | python3 -c "
import sys,json,datetime
now=datetime.datetime.now(datetime.timezone.utc); stale=[]
for v in json.load(sys.stdin)['items']:
    lb=v['status'].get('lastBackupAt') or ''
    if not lb: stale.append((v['metadata']['name'],'NEVER')); continue
    h=(now-datetime.datetime.fromisoformat(lb.replace('Z','+00:00'))).total_seconds()/3600
    if h>48: stale.append((v['metadata']['name'],f'{h:.0f}h'))
print('stale(>48h) or never:',len(stale))
for s in stale: print(' ',s)"
```
**PASS:** the most recent `daily-backup-all-volumes-*` Job is `Complete` within 24h, and
the stale list is **empty**.
*(Baseline: Job `daily-backup-all-volumes-29831220` Complete, 18h old; `stale: 0`.
The CronJob `storage/daily-backup-all-volumes` runs `0 3 * * *` — verified to exist
under that exact name, so a 09:00 window sees a ~6h-old backup.)*

**2.7 — Flux fully green.** A reconcile landing mid-roll is a confounder.

```bash
mise exec -- flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
mise exec -- flux get helmreleases   -A | awk 'NR==1 || $5 != "True"'
```
**PASS:** both print only the header row. *(Baseline: both clean.)*

**2.8 — Observability baseline. THE ALERT BASELINE IS NOT ZERO. Write these down** —
§4.4 diffs against them.

```bash
mise exec -- kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus \
  9099:9090 >/dev/null 2>&1 & PF=$!
sleep 6
curl -s localhost:9099/api/v1/alerts | python3 -c "
import sys,json
a=[x for x in json.load(sys.stdin)['data']['alerts'] if x['state']=='firing'
   and x['labels'].get('alertname') not in ('Watchdog','InfoInhibitor')]
print('firing:',len(a))
for x in a: print('  ',x['labels'].get('alertname'),x['labels'].get('account','-'))"
curl -s localhost:9099/api/v1/targets | python3 -c "
import sys,json
t=json.load(sys.stdin)['data']['activeTargets']
print('targets',len(t),'up',sum(1 for x in t if x['health']=='up'))
print('etcd:',[(x['labels'].get('instance'),x['health']) for x in t if 'etcd' in x['labels'].get('job','')])"
curl -s localhost:9099/api/v1/rules | python3 -c "
import sys,json; g=json.load(sys.stdin)['data']['groups']
print('groups',len(g),'rules',sum(len(x['rules']) for x in g))"
kill $PF 2>/dev/null
```

**PASS / baseline measured 2026-09-20:**

| Signal | Baseline | v1.14.0 plan said |
|---|---|---|
| firing | **4** (see below) | 0 |
| targets | **98 up 98** | 99 up 99 |
| etcd targets | `.11:2381`, `.12:2381`, `.13:2381` all `up` | same |
| rule groups / rules | **119 / 487** | 115 / 463 |

The four firing alerts are **pre-existing and unrelated to this plan**:

```
ICloudBackupPhotosStale          account=andrea   severity=warning    active since 2026-09-20T14:24Z
ICloudBackupPhotosStale          account=mu       severity=warning    active since 2026-09-20T14:24Z
ICloudBackupPhotosStaleCritical  account=andrea   severity=critical   active since 2026-09-20T14:24Z
ICloudBackupPhotosStaleCritical  account=mu       severity=critical   active since 2026-09-20T14:24Z
```

They are the same `icloud-docker` outage as the two detached volumes in §2.5 (both
Deployments scaled 0/0), tracked as **F-21d7e2ec** *("The iCloud photo backup stopped on
2026-09-06 and nothing noticed for 14 days")*. They are **not** suppressed by any
noise rule or accepted risk, so they will still be firing during the window.

> **The gate is therefore a SET comparison, not a count of zero.** `firing: 0` — the
> v1.14.0 plan's pre-check *and* its final gate — is unreachable today and would have
> either blocked the window at §2.8 or been waved through at §4.4. Record the exact
> alertname set at pre-check time and compare names, not totals. **If F-21d7e2ec is
> fixed before the window, the baseline legitimately drops to 0** — re-measure, never
> assume the four.

**2.9 — Envoy Gateway is the only HTTP data plane. Record its pre-state.**

```bash
mise exec -- kubectl get gateway -A
mise exec -- kubectl get httproute -A --no-headers | wc -l
mise exec -- kubectl get pods -n network -o wide | grep -E 'envoy-(internal|external|gateway)'
```
**PASS:** `envoy-internal` (192.168.55.103) and `envoy-external` (192.168.55.104) both
`PROGRAMMED=True`; **107** HTTPRoutes *(was 103 in the v1.14.0 plan — use the number you
measure, this one drifts)*; and — the load-bearing one — **each of `envoy-internal`,
`envoy-external` and `envoy-gateway` has 3 pods, one per node** (verified: all nine pods
`Running`, spread 01/02/03). That is what makes a one-node-at-a-time roll survivable: two
of three stay up throughout. If any of those Deployments is below 3 healthy pods across
≥2 nodes, **stop** — there is no fallback controller. ingress-nginx was deleted
2026-09-07 (`ad1ea7c2`); do not look for one.

**2.10 — Longhorn instance-manager PDBs.**

```bash
mise exec -- kubectl -n storage get pdb | grep instance-manager
mise exec -- kubectl -n storage get pods -l longhorn.io/component=instance-manager -o wide
```
**PASS:** exactly 3 PDBs, each with a live pod, one per node.
**`ALLOWED DISRUPTIONS = 0` on all three is the correct steady state, not a fault** —
each PDB selects exactly one pod with `minAvailable: 1`, so the arithmetic is always 0
(`docs/sops/talos-upgrade.md` §9). *(Baseline: 3 PDBs, 3 `Running` instance-managers, one
per node, all 14d old.)* Do not delete them. Do not reach for `--drain=false` on the
strength of seeing a zero here.

## 3) Steps

### Phase A — PREP, run BEFORE the window (~30 min, zero cluster effect)

**Why this is safe to do early:** `kubernetes/bootstrap/talos/` is **not reconciled by
Flux** — every Flux Kustomization `spec.path` points under `./kubernetes/apps` or the
flux config dirs; none references `bootstrap`. The talhelper-generated configs are
applied by `talosctl`, by hand. So committing and pushing a `talosVersion` bump changes
**nothing** on the cluster until §3.5 runs `talosctl upgrade`.

**3.1 — Prove the factory publishes our schematic for the target, WITH a negative
control.** Mandatory per `docs/sops/talos-upgrade.md` §4 Step 1 — that guard exists
because on 2026-09-06 a TLS-intercepting middlebox made this check "pass" for a
nonsense tag.

```bash
SCHEM=43b3cbfc2957259b4588d362709d47387607901d4d3506c1ea46d7ea74cb99a3
for TAG in v1.14.1 v9.9.9; do
  printf "%-10s HTTP %s\n" "$TAG" "$(curl -s -o /dev/null -w '%{http_code}' \
    "https://factory.talos.dev/v2/installer/$SCHEM/manifests/$TAG")"
done
```
**PASS — EXACTLY:** `v1.14.1 -> 200` **and** `v9.9.9 -> 404`.
Control also 200, or both 3xx? You are behind an intercepting proxy; the result is
**invalid**. **Never add `-k`** — that removes the check's ability to fail.
*(Measured 2026-09-20: 200 / 404. Correct.)*

**3.2 — Bump the node image and repair the dead Renovate annotation.**

Two single-line edits in `kubernetes/bootstrap/talos/talconfig.yaml`.

> **Use `sed`, NOT `yq`.** Dry-tested on a scratch copy on this Mac (macOS/BSD):
> `yq -i '.talosVersion = "v1.14.1"'` produces the correct value **but strips every
> blank line in the file — 111 lines → 103**, turning a 2-line change into an 8-hunk
> diff over `talconfig.yaml`. Note BSD `sed` requires the empty `-i ''` argument, and
> `\s` is not a BRE class here (`docs/sops/`-adjacent lesson: BSD flags misfire
> silently), so the expressions below use literal anchors only.

```bash
cd /Users/mu/code/cberg-home-nextgen
sed -i '' \
  -e 's|^# renovate: datasource=docker depName=ghcr.io/siderolabs/installer$|# renovate: datasource=github-releases depName=siderolabs/talos|' \
  -e 's|^talosVersion: v1\.13\.10$|talosVersion: v1.14.1|' \
  kubernetes/bootstrap/talos/talconfig.yaml
git --no-pager diff kubernetes/bootstrap/talos/talconfig.yaml
```

**Expected diff — EXACTLY this, dry-tested 2026-09-20 (111 lines before and after):**

```diff
--- a/kubernetes/bootstrap/talos/talconfig.yaml
+++ b/kubernetes/bootstrap/talos/talconfig.yaml
@@ -1,7 +1,7 @@
 # yaml-language-server: $schema=https://raw.githubusercontent.com/budimanjojo/talhelper/master/pkg/config/schemas/talconfig.json
 ---
-# renovate: datasource=docker depName=ghcr.io/siderolabs/installer
-talosVersion: v1.13.10
+# renovate: datasource=github-releases depName=siderolabs/talos
+talosVersion: v1.14.1
 # renovate: datasource=docker depName=ghcr.io/siderolabs/kubelet
 kubernetesVersion: v1.36.0
```

**A different diff is a STOP.** Re-running the same `sed` is a no-op (verified
idempotent — the anchors no longer match), so a second run cannot double-apply.

Leave `kubernetesVersion: v1.36.0` **unchanged** (supported, §1). Leave every
`talosImageURL` **unchanged** — `43b3cbfc…99a3` is live on all three nodes and publishes
v1.14.1.

**3.3 — Correct the stale deny-rule reason text (documentation-only).**

`runbooks/auto-update-policy.yaml`'s `aqua:siderolabs/talos` rule says the CLI pin tracks
*"talosVersion … currently v1.13.10"*. After this roll that is stale. Update the
parenthetical to `v1.14.1` in the same commit. **No behaviour change** — per the plans
README, a deny rule's text is the only thing that changes for a `PLAN`-classified item.

**3.4 — Re-confirm the target is still the head.** Cheap, and it is exactly the drift
that produced this re-plan (F-0a32b505, F-58f0bbab).

```bash
gh api repos/siderolabs/talos/releases --jq \
  '[.[] | select(.prerelease==false)] | .[0] | "\(.tag_name)  \(.published_at)"'
```
**PASS:** `v1.14.1`. **If a v1.14.2 (or later stable) has appeared, STOP and re-seek the
GO** — do not silently retarget in-window. That is the whole lesson of this file.

**3.5 — Bump talhelper to its final release.**

```bash
# .mise.toml — talhelper 3.1.11 -> 3.1.17 (the LAST talhelper release, 2026-08-26;
# confirmed installable: `mise ls-remote talhelper | tail -1` => 3.1.17)
# Do NOT touch "aqua:siderolabs/talos" here — that is §3.7, after the roll.
mise install
mise exec -- talhelper --version          # expect 3.1.17
```

**3.6 — Regenerate and READ THE DIFF. This is the real gate, because talhelper cannot
be it.**

```bash
cd kubernetes/bootstrap/talos
mise exec -- talhelper validate talconfig talconfig.yaml
cd -
mise exec -- task talos:generate-config
git --no-pager diff --stat kubernetes/bootstrap/talos/
```

**Expected `validate` output — this warning is EXPECTED and is not a failure** (measured
verbatim today against a v1.14.1 scratch copy, exit code 0):

```
There are issues with your talhelper config file:
field: "talosVersion"
  * WARNING: "v1.14.1" might not be compatible with this Talhelper version you're using
```

Now diff the generated node configs by hand. The three files under `clusterconfig/` are
SOPS-encrypted; diff the decrypted form:

```bash
for n in 01 02 03; do
  echo "=== nuc14-$n ==="
  mise exec -- sops -d kubernetes/bootstrap/talos/clusterconfig/kubernetes-k8s-nuc14-$n.yaml \
    > /tmp/new-$n.yaml
  git show HEAD:kubernetes/bootstrap/talos/clusterconfig/kubernetes-k8s-nuc14-$n.yaml \
    | mise exec -- sops -d /dev/stdin > /tmp/old-$n.yaml
  diff -u /tmp/old-$n.yaml /tmp/new-$n.yaml
done
```

**PASS:** the only differences are the `machine.install.image` tag `v1.13.10 → v1.14.1`
and the config version-contract stamp.
**STOP AND INVESTIGATE** if the diff shows any of: a new `SecurityProfileConfig` document
(workload isolation — §1 item 9, must NOT appear), a new `UnattendedInstall` document
replacing `machine.install`, `machine.sysctls` / `machine.udev.rules` / `machine.kubelet`
rewritten into `SysctlConfig` / `UdevRulesConfig` / `KubeNodeConfig` documents, a changed
`nameservers`/`searchDomain` block, or any **removed** field. Alpha machinery emitting a
GA-era document shape is exactly the failure this step exists to catch — and v1.14.1's
`fix: tighten the validation of v1alpha1 configs vs. migration` lands on precisely this
surface. If it appears, do not "fix it up" in-window — abort Phase A and reschedule.

Then `rm -f /tmp/old-*.yaml /tmp/new-*.yaml` (they hold decrypted cluster secrets).

**3.7 — Commit and push (still zero cluster effect).**

Per `CLAUDE.md`, use `--only` with explicit paths — the worktree is shared.

```bash
cat > /tmp/talos-msg.txt <<'EOF'
feat(talos)!: node image v1.13.10 -> v1.14.1 (config only; roll is manual)

Bumps talosVersion in talconfig.yaml and regenerates the three SOPS-encrypted
node configs. Flux does not reconcile kubernetes/bootstrap/talos/, so this
commit changes nothing until `task talos:upgrade-node` runs in the window.

Re-targeted from v1.14.0 (approved 2026-09-12) to v1.14.1 (published
2026-09-15): the recorded GO was scoped to v1.14.0 and does not carry over.
v1.14.1 also fixes sandboxd signal dispositions leaking into services and
hardens the talosctl action tracker against dropped connections -- both on
the path this roll drives.

Also repoints the Renovate annotation from ghcr.io/siderolabs/installer (which
stopped publishing at v1.14.0 -- the Image Factory is now the only source) to
github-releases/siderolabs/talos, and refreshes the stale cluster version in
the aqua:siderolabs/talos deny-rule reason.

Plan: runbooks/maintenance/plans/talos-1.14.1.md
Findings: F-912f4778, F-0a32b505, F-9a58f400
EOF

git commit --only \
  kubernetes/bootstrap/talos/talconfig.yaml \
  kubernetes/bootstrap/talos/clusterconfig/ \
  runbooks/auto-update-policy.yaml \
  .mise.toml \
  -F /tmp/talos-msg.txt

git log -1 --format=%s          # MUST be the feat(talos)! subject above — concurrent
                                # sessions can swap COMMIT_EDITMSG; amend before push
git show --stat HEAD            # every file here MUST be one of the four above
git push
```

### Phase B — THE ROLL (in-window)

**Concurrency rule, absolute: exactly ONE node down at a time.** All three nodes are etcd
members; a 3-member cluster tolerates the loss of exactly one. Two down = quorum lost =
the API server is gone and the roll cannot be driven. There is no step in this plan where
two nodes are unavailable, and no circumstance in which "just do the last two together to
save time" is acceptable.

**3.8 — Roll order. THIS CHANGED since the v1.14.0 plan** — re-derive from §2.4 at window
time, because it moved once already.

| Rule | Node (measured 2026-09-20) | Why |
|---|---|---|
| **1st — CANARY**: lightest Longhorn load, holds neither the VIP nor etcd leadership | **`k8s-nuc14-01` / 192.168.55.11** (17 attached, 58 running replicas) | Smallest state to move, so the fastest, cleanest first reboot. If v1.14.1 is bad we learn it while the API endpoint and etcd leadership — **both now on 03** — are untouched. **This is the go/no-go for the other two nodes.** |
| **2nd**: heaviest load, but no VIP and not leader | **`k8s-nuc14-02` / 192.168.55.12** (45 attached, 67 running replicas) | Do the big drain while a proven-good v1.14.1 peer exists and the control-plane endpoint is still stationary. |
| **3rd — LAST**: the VIP owner **and** the etcd leader | **`k8s-nuc14-03` / 192.168.55.13** (30 attached, 59 running replicas, **holds VIP 192.168.55.10**, **is etcd leader** `73a201c6b4bf6faf`) | Both disruptive control-plane events happen once, at the end, after two nodes have proven v1.14.1. |

> **Why the order is not the v1.14.0 plan's.** That plan ordered 01 → 03 → 02 because the
> VIP was on 02 and leadership on 03, deliberately separating the two events. They are now
> **on the same node**, so separating them is impossible; the correct response is to put
> that node last and accept one combined disruption. This is also where the +5 min in
> §7 comes from.

For each node, in that order, run **3.9 → 3.10 → 3.11** to completion before starting the
next.

**3.9 — Upgrade one node.**

```bash
mise exec -- task talos:upgrade-node IP=<node-ip>
```

This installs the new image, then cordons, drains, and reboots. Expect it to sit on
`evicting pod storage/instance-manager-<hash>` for a while. **That is normal.** Per
`docs/sops/talos-upgrade.md` §9 the drain waits for Longhorn volumes to **detach**, not
for a stuck PDB. Watch the engine count fall:

```bash
mise exec -- kubectl -n storage get engines.longhorn.io -o json | python3 -c "
import sys,json
print(len([e for e in json.load(sys.stdin)['items'] if e['spec'].get('nodeID')=='<node-name>']))"
```
*(Baseline engine counts, which are what must drain to 0: 01=17, 02=45, 03=30.)*
Engines going N → 0 (~75s observed on the 2026-08-16 roll) is the drain progressing. When
it hits 0, Longhorn deletes the PDB itself and the drain completes in seconds.

**Do NOT** delete the PDBs. **Do NOT** use `EXTRA_FLAGS='--drain=false'` pre-emptively.
Only if the drain **times out** with
`error when waiting for pod "instance-manager-…" to terminate: context deadline exceeded`
(the load-dependent recreate race in the SOP): **uncordon the node first**, then delete
the `Pending` pods so the scheduler spreads the attach load. Do not wait it out — it does
not self-resolve. `--drain=false` is a last resort and never unattended.

**3.10 — Node health gate.**

```bash
mise exec -- kubectl get nodes -o wide
mise exec -- talosctl -n <node-ip> version --short
mise exec -- talosctl -n 192.168.55.11,192.168.55.12,192.168.55.13 etcd status
```
**PASS, all of:** the node is `Ready` and **not** `SchedulingDisabled`; `Tag: v1.14.1`;
etcd reports **3 members**, no `LEARNER`, empty `ERRORS`, and raft indexes converged. Do
not proceed until etcd shows three healthy members — a node that is `Ready` but whose etcd
member has not rejoined is a quorum of two, and the next node would take it to one.

*Expect `PROTOCOL` to read 3.7.x on upgraded members and 3.6.14 on not-yet-rolled ones; a
mixed reading mid-roll is correct, not a fault.*

**3.11 — THE LONGHORN GATE. This is the step that blows the time budget.**

Do **not** start the next node until this passes. With `numberOfReplicas: 2` there is no
cushion: starting the next node while volumes are still degraded means volumes running on
**zero** replicas.

```bash
mise exec -- kubectl get volumes -n storage -o json | python3 -c "
import sys,json,collections
d=json.load(sys.stdin)['items']
bad=[(v['metadata']['name'],v['status'].get('robustness'),v['status'].get('state'))
     for v in d if v['status'].get('robustness')!='healthy']
print('NOT-HEALTHY:',len(bad))
for b in bad: print('  ',b)
print('robustness:',collections.Counter(v['status'].get('robustness') for v in d))"

mise exec -- kubectl get replicas.longhorn.io -n storage -o json | python3 -c "
import sys,json,collections
rs=json.load(sys.stdin)['items']
c=collections.Counter((r['spec'].get('nodeID','?'), r['status'].get('currentState','?')) for r in rs)
for k,v in sorted(c.items()): print(k,v)
print('total replicas',len(rs))"
```

**PASS — all three conditions, together:**

1. `NOT-HEALTHY: 2`, and **both are the known `icloud-docker` session volumes from
   §2.5**. Not 3, not a different pair. Not `degraded`, not `rebuilding` — `degraded`
   means one replica, which is exactly the state we must not enter the next reboot in.
2. The just-rebooted node appears again in the replica table with a **`running`** count in
   the same order as before the reboot (baseline 2026-09-20: 01=58 running/6 stopped,
   02=67/1, 03=59/1 — the `stopped` ones are replicas of the detached volumes).
3. `total replicas` is back at **192**.

**Why this can run long, and what to do about it.** `replica-replenishment-wait-interval`
is **600s** (verified live), so Longhorn waits 10 minutes before replenishing a missing
replica elsewhere. If the node returns inside that window (typical), replicas restart in
place and rebuild incrementally — fast. If the reboot overruns 10 minutes, Longhorn starts
building **full** replicas on the surviving nodes and the gate can take far longer over 92
attached volumes. `concurrent-replica-rebuild-per-node-limit` is **8** and
`replica-rebuild-concurrent-sync-limit` is `{"v1":"1"}` (both verified live), so it is
deliberately paced.

**Budget rule: if the gate has not passed 25 minutes after the node returned `Ready`, stop
rolling.** Do not skip the gate, do not shorten it, do not start the next node. Leave the
cluster part-rolled (a supported transient), finish §4.4 on the current mix, and reschedule
the remainder. A part-rolled cluster is fine; a cluster with volumes on zero replicas is
not.

**3.12 — Merge PR #212 (the talosctl CLI pin) — LAST, and only after all three nodes
report v1.14.1.**

```bash
mise exec -- kubectl get nodes -o wide | grep -c 'Talos (v1.14.1)'   # MUST be 3
gh pr checks 212
gh pr merge 212 --squash
git pull
mise install
mise exec -- talosctl version --short                                # Client: Talos v1.14.1
```
**PASS:** client reports `v1.14.1` — **exactly the cluster version**, because #212 was
retargeted to 1.14.1 upstream on 2026-09-19 — and `talosctl -n <any> version --short`
still talks to the nodes.

**If fewer than 3 nodes reached v1.14.1, do NOT merge #212.** Leave it open; a v1.13.10
client drives a mixed cluster correctly (Talos supports n±1, older client is the normal
direction).

**Explicitly NOT in this window:** `task talos:upgrade-k8s`. Kubernetes stays on v1.36.0,
which §1 proves is inside Talos 1.14's supported range (1.32.0 – 1.37.99). A Kubernetes
minor bump is its own plan, its own window, and it needs a client matching the cluster
(SOP lesson #6).

## 4) Verification

### 4.1 — Per-node, immediately after each node returns (§3.10 + §3.11 above)

Plus, on **every** node as it comes back — the kernel-cmdline check, because
`docs/sops/talos-upgrade.md` lessons #2, #3 and #13 all describe args silently
disappearing across an upgrade:

```bash
mise exec -- talosctl read /proc/cmdline -n <node-ip> \
  | tr ' ' '\n' | grep -E 'hugepages|i915|intel_iommu|mitigations|init_on_alloc'
mise exec -- talosctl read /proc/meminfo -n <node-ip> | grep HugePages_Total
```
**PASS — the exact arg set measured on all three nodes today:**
`init_on_alloc=1 init_on_alloc=0 i915.enable_guc=3 intel_iommu=on mitigations=off
hugepages=1024`, and `HugePages_Total: 1024`. A node missing them booted from an older
install — re-run `task talos:upgrade-node` for that IP before moving on.
*(The doubled `init_on_alloc` is expected: the kernel default is emitted before the
schematic's override. It is present today on all three nodes.)*

**CANARY GO/NO-GO (after node 01 only).** All of §3.10, §3.11 and the cmdline check pass,
**and** `kubectl get pods -A --field-selector spec.nodeName=k8s-nuc14-01` shows pods
scheduling and running there again. If any fails: **stop, roll node 01 back (§5.1), and do
not touch nodes 02/03.** This is the one point in the plan with a clean exit.

### 4.2 — Storage: the iSCSI record trap (run after the LAST node)

Mandatory. On the 2026-08-16 roll this bit node 03 and was nearly missed: the node was
`Ready`, Longhorn reported every volume healthy, and the node could not attach a single
volume — the scheduler just placed everything elsewhere and the cluster **looked** green.

```bash
mise exec -- kubectl get volumes -n storage \
  -o custom-columns='NODE:.status.currentNodeID' --no-headers | sort | uniq -c
```
**PASS:** all three node names appear with a non-trivial count. **A node showing 0 while
the others show dozens is the smoking gun.** If it happens:

```bash
mise exec -- talosctl -n <node-ip> list /var/lib/iscsi/nodes
mise exec -- talosctl -n <node-ip> read /var/lib/iscsi/nodes/<target>/<portal>/default | grep conn_reopen
```
The failing record names a **different** volume than the one in the pod's error — chase the
one in the `config file … invalid` line, and check **all** records, not just the first (5 of
6 were poisoned last time). Fix is to remove only the unparseable records; Longhorn
recreates them on next attach. **Do not** reboot, drain, or reset the node, and **do not**
delete any PV/PVC/Volume/Replica — it is a host-state file problem.

### 4.3 — CONTENTS ASSERTIONS

Per the plans README: a health signal that cannot distinguish "working" from "empty" is not
a health signal. Three, because this change has three distinct ways to fail while looking
perfect.

> **CONTENTS ASSERTION 1 (storage — a real read/write round-trip through a mounted
> Longhorn PVC).** Longhorn's own `robustness: healthy` says nothing about whether anything
> can still *use* a volume — §4.2 is proof that it lies in exactly this situation.
> **Measured by:** writing and reading back a file inside a live pod on a **rolled** node.
> **Compared to:** the byte-identical string written.
>
> Verified target (exists today, `kubectl get` + a no-write shell probe):
> `deploy/pgadmin` in ns `databases`, PVC **`pgadmin-data`** (`longhorn-static`, RWO,
> Bound, 5Gi), mounted at **`/var/lib/pgadmin`**; the container has `sh`.
>
> ```bash
> # the pod must be on a ROLLED node — resolve it, don't assume it
> mise exec -- kubectl -n databases get pod -l app.kubernetes.io/name=pgadmin \
>   -o jsonpath='{.items[0].spec.nodeName}{"\n"}'
> mise exec -- kubectl -n databases exec deploy/pgadmin -- sh -c \
>   'echo talos-1141-probe-$$ > /var/lib/pgadmin/.probe && cat /var/lib/pgadmin/.probe && rm /var/lib/pgadmin/.probe'
> ```
> **PASS:** the echoed string comes back identical, from a pod on a rolled node. An empty
> read, an I/O error, or a read-only filesystem is a FAIL **even with every volume
> `healthy`**. If pgadmin happens to sit on an un-rolled node, pick any other pod from the
> §4.2 attach table that does — the assertion is "a write lands on a rolled node", not
> "pgadmin specifically".

> **CONTENTS ASSERTION 2 (monitoring — the series still arrive, with a floor).** Node
> reboots are the classic way to lose a scrape target silently, and v1.14 moves etcd's HTTP
> endpoints (2379 → 2383) — our scrape is on 2381 and should be unaffected, but "should be"
> is not an assertion. **Measured by:** target health **and** a representative etcd series
> returning a non-empty result. **Compared to:** the §2.8 baseline.
>
> ```bash
> mise exec -- kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus \
>   9099:9090 >/dev/null 2>&1 & PF=$!
> sleep 6
> curl -s localhost:9099/api/v1/targets | python3 -c "
> import sys,json
> t=json.load(sys.stdin)['data']['activeTargets']
> print('targets',len(t),'up',sum(1 for x in t if x['health']=='up'))
> for x in t:
>     if x['health']!='up': print('  DOWN',x['labels'].get('job'),x['labels'].get('instance'))"
> # the floor — etcd must still be PRODUCING, not merely 'up'
> curl -s --get localhost:9099/api/v1/query \
>   --data-urlencode 'query=count(etcd_server_has_leader)' \
>   | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['status'], d['data']['result'])"
> curl -s localhost:9099/api/v1/rules | python3 -c "
> import sys,json; g=json.load(sys.stdin)['data']['groups']
> print('groups',len(g),'rules',sum(len(x['rules']) for x in g))"
> kill $PF 2>/dev/null
> ```
> **PASS:** `targets 98 up 98` (≥ the baseline; a *smaller total* is a FAIL — a disappeared
> target reads as 100% up), the etcd query returns **`success [... value 3]`**, and
> `groups 119 rules 487` (±0 — no rule group should vanish across a node roll).
>
> > **The v1.14.0 plan's version of this query was BROKEN and could never pass.** It used
> > `count(count by (instance) (etcd_server_has_leader[10m]))`, which Prometheus rejects:
> > `parse error: expected type instant vector in aggregation expression, got range vector`.
> > Measured today — it returns an error object with no `data` key, so the executor's
> > one-liner raises `KeyError: 'data'` rather than printing a number. The form above is
> > measured working and returns `3`. **A ceiling without a floor is a shape check:** "no
> > targets down" would still be green if the etcd job stopped existing; this `count()` is
> > the floor.

> **CONTENTS ASSERTION 3 (routing — real HTTP through Envoy, not Gateway status).** Envoy
> Gateway has **no fallback controller**; a roll that breaks it is a total loss of HTTP
> routing. `PROGRAMMED=True` is a shape check — a Gateway can be Programmed with an empty
> or stale route table. **Measured by:** every HTTPRoute `Accepted` **and** `ResolvedRefs`,
> the route **count** matched against the §2.9 baseline, and a real request returning real
> bytes through **both** gateways.
>
> ```bash
> mise exec -- kubectl get gateway -A
> mise exec -- kubectl get httproute -A --no-headers | wc -l      # MUST equal the §2.9 count
> mise exec -- kubectl get httproute -A -o json | python3 -c "
> import sys,json
> bad=[]
> for r in json.load(sys.stdin)['items']:
>     for p in r.get('status',{}).get('parents',[]):
>         for c in p.get('conditions',[]):
>             if c['type'] in ('Accepted','ResolvedRefs') and c['status']!='True':
>                 bad.append((r['metadata']['namespace'],r['metadata']['name'],c['type'],c.get('reason')))
> print('routes NOT Accepted/ResolvedRefs:',len(bad))
> for b in bad: print('  ',b)"
> # real traffic, both data planes, from the LAN
> curl -sS -o /dev/null -w 'internal %{http_code} %{size_download}B\n' \
>   -H "Host: <a real ingressed host>" https://192.168.55.103/ -k
> curl -sS -o /dev/null -w 'external %{http_code} %{size_download}B\n' \
>   -H "Host: <a real ingressed host>" https://192.168.55.104/ -k
> ```
> **PASS:** both Gateways `PROGRAMMED=True`; the HTTPRoute count equals the §2.9 baseline
> (**107** today — re-measure, it drifted from 103 since the v1.14.0 plan); `routes NOT
> Accepted/ResolvedRefs: 0`; and both curls return 2xx/3xx with a **non-zero body size**. A
> 200 with `0B`, or a route count that quietly dropped to 40, is a FAIL. *(Substitute a real
> host at run time; this repo is public, so no hostname is written here. The point is a
> body, not a status line.)*

### 4.4 — Whole-cluster verification (end of window)

```bash
# 1. every node on the target
mise exec -- kubectl get nodes -o wide     # 3x Ready, Talos (v1.14.1), kubelet v1.36.0
#    ALSO expect: kernel 6.18.51-talos (was 6.18.48), containerd 2.3.5 (was 2.2.7)

# 2. etcd healthy AND advanced
mise exec -- talosctl -n 192.168.55.11,192.168.55.12,192.168.55.13 etcd status
#    PASS: 3 members, no LEARNER, empty ERRORS, converged raft index, PROTOCOL 3.7.x on ALL

# 3. the VIP is owned by exactly one node again
for ip in 192.168.55.11 192.168.55.12 192.168.55.13; do
  echo -n "$ip vip=" ; mise exec -- talosctl -n $ip get addresses 2>/dev/null | grep -c '192.168.55.10/32'
done                                       # PASS: exactly one node reports 1

# 4. no pod left behind
mise exec -- kubectl get pods -A --field-selector status.phase!=Running,status.phase!=Succeeded

# 5. Flux still green (it has been reconciling against a moving cluster all window)
mise exec -- flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
mise exec -- flux get helmreleases   -A | awk 'NR==1 || $5 != "True"'

# 6. Longhorn: the §3.11 gate one final time + the §4.2 per-node attach check
# 7. all three CONTENTS ASSERTIONS from §4.3
# 8. alerts back to the baseline SET — after a settle period, NOT immediately
```

**PASS on 8 — this is a SET comparison, not `firing: 0`:** the firing alertname set equals
the §2.8 baseline set (today: `ICloudBackupPhotosStale` ×2, `ICloudBackupPhotosStaleCritical`
×2, all `component=icloud-docker`), **sustained for ≥15 minutes** after the last node
returned, with **no new alertname** present. Any alertname not in the baseline is a real
regression, not reboot noise. Node-level alerts fire during every reboot and clear on their
own — that is why the 15 minutes exist, and why they are budgeted in §7 rather than skipped.

> **Positive control, so this gate can be trusted:** the four baseline alerts are themselves
> proof the alert pipeline is live and reaching Prometheus. If the firing set comes back
> **empty**, do not read that as success — `ICloudBackupPhotosStale` cannot self-resolve
> while both `icloud-docker` Deployments are scaled 0/0 (F-21d7e2ec). An empty set means the
> alerting path broke during the roll, which is a FAIL.

### 4.5 — Confirm workload isolation was NOT silently enabled

```bash
for ip in 192.168.55.11 192.168.55.12 192.168.55.13; do
  echo -n "$ip securityprofileconfig="
  mise exec -- talosctl -n $ip get machineconfig -o yaml | grep -ci 'securityprofileconfig'
  echo -n "   positive-control(machine:)="
  mise exec -- talosctl -n $ip get machineconfig -o yaml | grep -ci 'machine:'
done
```
**PASS:** `securityprofileconfig=0` on all three **and** `positive-control≥1` on all three.
*(Baseline measured 2026-09-20 on v1.13.10: 0 and 2 respectively.)* The positive control is
what makes the zero meaningful — a `grep` against an empty or failed `talosctl` call also
returns 0, and would otherwise read as a pass.

**Do NOT assert that `sandboxd` is absent.** On v1.13.10 the service list is
`apid containerd cri dashboard etcd ext-iscsid kubelet machined syslogd trustd udevd`
(measured — no `sandboxd`), but on v1.14 `sandboxd` is expected to exist regardless of
whether workload isolation is enabled; v1.14.1 ships a fix for it. Its presence proves
nothing about isolation. The config document above is the property that actually controls it.

## 5) Rollback

**Be honest about this: a Talos node-image upgrade is not a clean revert, and
`rollback_class` is `one-way` for that reason. Rolling back a node is ANOTHER REBOOT CYCLE
(~45 min for node 01, including its Longhorn re-gate), never a `git revert`.** The git
commit is inert; reverting it moves no node.

### 5.1 — Per-node rollback (REAL, and it is the canary's abort path)

Talos keeps the previous installed image on the alternate boot partition:

```bash
mise exec -- talosctl get machinestatus -n <node-ip> -o yaml | grep -i image
mise exec -- talosctl rollback --nodes <node-ip>
```
Then re-run §3.10 + §3.11 to confirm the node came back on v1.13.10 with its Longhorn
replicas running, and §4.1 for its kernel cmdline.

**This is genuinely reversible, with two hard limits:**
- It is **one boot partition deep.** It returns the node to the image it ran before the last
  upgrade — nothing further back.
- It does **not** unwind cluster-level state.

**Use it at exactly one point: the canary (§4.1). That is the clean exit.** With node 01
rolled back and 02/03 never touched, the cluster is where it started and the §3.7 commit can
simply be reverted.

**Cost, which is the number the window is sized around:** one node reboot cycle
(~10 min) plus its Longhorn replica-rebuild gate (up to the 25-min budget rule) plus
re-verification ≈ **45 min**. This is why §7 insists the residual slot time is a rollback
budget and not slack.

### 5.2 — Past the canary: there is no clean revert. Stop, don't unwind.

Once **two or more** nodes are on v1.14.1, the etcd cluster has advanced from 3.6.14 toward
3.7.1 on a majority of its members. Downgrading a Talos node image does not downgrade an
etcd data directory, so "revert the commit and re-roll" is **not** a rollback — it is an
untested downgrade across an etcd storage-version boundary on a cluster holding an ~820 MB
database (140 MB in use).

*(For completeness: upstream's `MaximumHostDowngradeVersion = 1.16.0` means Talos permits
downgrading **to** 1.14 from below 1.16 — it says nothing about downgrading 1.14 → 1.13
underneath an advanced etcd. Do not read the compatibility constant as a rollback warranty.)*

**Therefore, past the canary:**
- **Preferred: stop, don't unwind.** A part-rolled cluster (some nodes v1.13.10, some
  v1.14.1) is a **supported transient** — it is what every rolling upgrade passes through.
  Stop where you are, finish §4.4 against the mix, and reschedule the remainder. This is the
  right answer to "we ran out of time" and to most "something looks off".
- **If a specific node is broken:** `talosctl rollback` that **one** node (§5.1) and leave
  the rest. Same supported mixed state.
- **If the cluster itself is broken:** this is **disaster recovery**, not rollback.
  `docs/sops/disaster-recovery.md` + the Longhorn backups verified in §2.6 + an etcd
  snapshot. Do not improvise it inside the window; escalate to the operator.

### 5.3 — Reverting the git commit

The §3.7 commit is inert on its own, so reverting it is safe and does **not** move any node:

```bash
git revert <sha>                 # restores talosVersion: v1.13.10 + the annotation
mise exec -- task talos:generate-config
git commit --only kubernetes/bootstrap/talos/ -m "Revert Talos v1.14.1 node config"
git log -1 --format=%s           # confirm the subject is yours before pushing
git push
```
**Confirm the cluster is back** by the state of the *nodes*, never the state of the repo:
`kubectl get nodes -o wide` showing the expected Talos tag on each node, plus §3.11
(Longhorn) and §4.3 (all three contents assertions). The commit and the cluster are
independent here — a green `git log` proves nothing.

**Do not** revert `.mise.toml`'s `aqua:siderolabs/talos` below the cluster version if any
node is on v1.14.1: an n-1 client is fine, an n-2 client is not.

## 6) Interference notes

**This plan requires the ENTIRE `sun-attended` window, with no other plan in it.** That is
not a preference. A node roll evicts and reschedules **every pod in the cluster**, three
times. Any other plan running in the same window is verifying its change against a cluster
in motion — and if something breaks, there are two candidate causes and no way to separate
them.

**FIRST, A HOUSEKEEPING BLOCKER — the superseded plan must not keep claiming this slot.**
`talos-1.14.0.md` held `sun-attended:2026-09-27` at `awaiting-go`, 140 min. If both files
are live the scheduler sees **145 + 140 = 285 min** against a **180-min** budget. This plan
is only schedulable once `talos-1.14.0` is `superseded` with `window: null`. Verify at §2.1.

**Six other plans name `talos-1.14.0` in their `conflicts_with`** — `cilium-1.20.2`,
`flux-oci-chart-sources`, `helm-drift-detection`, `n8n-2.39.8`, `edot-collector-0.161.0`,
`otel-operator-0.23.0`. Those refs still *resolve* (the superseded file stays on disk, so
`--validate`'s dead-cross-reference check passes), but they now point at a plan that will
never run, so they no longer protect against **this** one.

> **REPO CORRECTION for the vetter:** those six should be updated to name `talos-1.14.1`.
> This plan declares all six on its own side, and the scheduler honours the field from
> either side, so the window is safe today — but reciprocity is the documented house rule
> and `--validate` does not check it.

**Sequencing within the window:** this plan runs **alone**. If the operator insists on
pairing it with something, the only defensible shape is a short, fully-reversible,
storage-untouching plan running **after** §4.4 has completely passed — never before, never
interleaved between nodes.

**Things that must not run concurrently, beyond other plans:**
- **The nightly window's Step 0 safe-update apply.** `sun-attended` is a different window,
  but it fires at 03:30 the same day; verify via §2.7 that its reconciles have fully landed.
- **This window's OWN Step 0.** It runs first, every window, unattended-or-not, and the
  scheduler reserves 20 min for it. It is not optional and must not be skipped to buy time.
- **The Longhorn backup CronJob `daily-backup-all-volumes` (`0 3 * * *`)** and the
  `*-filesystem-trim` / `*-snapshot-cleanup` CronJobs (`0 2` / `30 2`). A 09:00 window clears
  all of them, but do not let this plan slip earlier into their path — a backup running
  against volumes whose replicas are rebuilding competes for exactly the bandwidth the gate
  is waiting on.
- **The 04:00-anchored operation sweep.** Same reasoning; it must be finished.
- **Any Longhorn engine/manager upgrade, any StorageClass change, any PVC delete.**
  `docs/sops/storage-safety.md` applies in full; nothing in this plan deletes a PVC and
  nothing in this plan may be extended to.
- **Zigbee/Home Assistant work.** Every node reboot disconnects the SLZB coordinator
  sockets; that noise is expected and must not be diagnosed as a Zigbee fault. Also run
  `docs/sops/home-assistant-updates.md`'s post-restart checklist afterwards — HA reinstalls
  HACS requirements on each boot.

**Shared infra this perturbs, and who feels it:**

| Shared thing | Effect | Who notices |
|---|---|---|
| `gateway/envoy` | one of three pods of each of `envoy-internal`/`envoy-external`/`envoy-gateway` down per node | **every ingressed app** (107 HTTPRoutes) — brief connection resets; **no fallback controller exists** |
| `etcd` | one member down per node; leadership re-elects on the **final** node; 3.6.14 → 3.7.1 | whole control plane; API blips |
| VIP 192.168.55.10 | fails over once, on the final node (**same node as the leader now**) | anything using the kubeconfig endpoint, incl. this session |
| `storage/longhorn` | instance-manager restart + replica rebuild ×3 | every stateful app; the databases in particular |
| `cni/cilium` | DaemonSet pod restart per node | all pod networking, briefly |
| `coredns` | Talos-bundled version moves | cluster DNS, briefly |
| `cert-manager` | webhook pods reschedule | any Certificate reconcile landing mid-roll |
| `monitoring` | scrape gaps + node alerts during each reboot | expected; §4.4 waits 15 min before judging |

## 7) Risk and duration against the slot

**Risk: `high`.** Not because v1.14.1 looks dangerous — the breaking changes that matter are
opt-in and this plan declines them, and v1.14.1 specifically fixes two faults on the path
this roll drives — but because the blast radius is the whole cluster and there is no clean
rollback past the first node. `needs_reboot: true` and `capability_change: true` both hold,
so this is operator-present, reboot-capable, `sun-attended` only.

### The slot arithmetic, corrected

`runbooks/maintenance-windows.yaml` was updated on 2026-09-20 to state what the scheduler
has always done, and it changes this plan's fit:

> **SCHEDULABLE BUDGET = duration_min − 20.** `window-scheduler.py` reserves
> `STEP0_RESERVE_MIN = 20` for the Step 0 safe-update batch that runs FIRST in every window,
> then places plans against `duration_min − 20` (verified in code at
> `window-scheduler.py:92` and `:270`). *"FOUR separate artifacts have now done slot
> arithmetic against the raw `duration_min` and concluded a plan fits when the scheduler
> would refuse it."*

So `sun-attended` is **200 wall-clock / 180 schedulable**, not 200 for plans.

### Re-measured duration: 145 min in-window

| Phase | Min | Basis (re-measured 2026-09-20) |
|---|---:|---|
| **A — prep (BEFORE the window)** | **~30** | *Not counted in `est_duration_min`.* Flux does not reconcile `kubernetes/bootstrap/talos/`, so §3.1–§3.7 are inert until `talosctl upgrade` runs. |
| §2 pre-checks | 15 | 10 checks, several with per-node loops |
| Node 01 — canary: upgrade + drain + reboot + §3.10 + §3.11 + §4.1 + canary go/no-go | 35 | lightest node (17 attached, 58 replicas); includes the extra canary verification the other two skip |
| Node 02 — upgrade + gate | 40 | heaviest (45 attached, 67 replicas) |
| Node 03 — upgrade + gate; **VIP failover AND etcd leader re-election** | 35 | mid load (30 attached, 59 replicas) but carries both control-plane events |
| §4.2 + §4.4 + §4.5 whole-cluster verification (incl. the 15-min alert settle) | 20 | overlaps the settle wait |
| **In-window total** | **145** | |

**This is 5 minutes more than the v1.14.0 plan's 140, and the task framing asked me to say
so explicitly. Here is where it went:** node 03 now holds **both** the VIP and etcd
leadership. The v1.14.0 plan could sequence those two disruptions onto different nodes
(leader on 03 in mid-position, VIP on 02 last) and priced them separately. They are now
inseparable, so the final node carries a failover *and* a re-election plus its own rebuild
gate. That is a genuine +5, not padding.

### Does it still fit, with a real rollback budget? Honestly: yes, but tighter than 45.

```
slot wall clock                      200
  − Step 0 reserve (mandatory)        20
  − this plan                        145
  ────────────────────────────────────────
  = residual                          35    ← the rollback budget
```

- **Against the scheduler's rule it fits comfortably:** 145 ≤ 180 schedulable, with 35 min
  of schedulable room to spare.
- **Against the intended rollback budget it is 10 minutes short.** The slot was sized as
  140 + 45 + 15. The 15-min alert settle is already *inside* my 145 (it lives in the §4.4
  block), so the honest decomposition is 20 + 145 + **35**, against a realistic worst-case
  single-node rollback of **45**.

**Why that 10-minute shortfall is acceptable, and the one case where it is not:**

1. **The rollback budget is only genuinely needed at the canary**, which completes around
   **T+50** (15 pre-checks + 35 for node 01). At that moment ~110 minutes of slot remain —
   more than double the 45-min rollback cost. The clean exit is cheap precisely because it
   is early.
2. **Past the canary the correct response is not rollback at all — it is to stop
   part-rolled** (§5.2), which costs *nothing* and is a supported transient. So the
   end-of-window scenario that would consume a 45-min rollback does not call for one.
3. **The squeeze only bites in one case:** node 03 fails at the very end AND the operator
   decides to roll that single node back rather than stop. That is a deliberate, attended
   decision with the operator present, and it would overrun the slot by ~10 minutes. **Flag
   it at the go/no-go rather than discovering it at 12:20.**

**Stopping part-way is a designed outcome, not a failure.** A mixed v1.13.10 / v1.14.1
cluster is supported. If the budget goes, stop after whichever node just passed its gate, run
§4.4 against the mix, and take the rest next window. Do **not** trim the estimate to make
three nodes fit — that is how a gate gets skipped.

## Open items — could not be determined read-only

1. **RESOLVED (was open item #1 on the v1.14.0 plan).** Talos v1.14 ↔ Kubernetes support
   matrix: answered from upstream code (1.32.0 – 1.37.99; host upgrade floor 1.12.0), not
   from the JS-rendered docs site. No Phase-A follow-up needed.
2. **`talhelper genconfig` output diff for v1.14.1** was reasoned about, not executed:
   running it writes SOPS-encrypted node configs into the repo, which is outside this agent's
   write boundary. §3.6 makes reviewing that diff an explicit, gated step with a named list
   of things that must **not** appear — and v1.14.1's tightened v1alpha1-vs-migration
   validation makes that review more load-bearing than it was for v1.14.0.
3. **Node-reboot duration on v1.14.1 specifically.** The 35/40/35 per-node figures are
   extrapolated from the 2026-08-16 v1.13.8 roll and today's measured per-node Longhorn load.
   v1.14 adds `sandboxd` to the boot path even with workload isolation off; whether that
   changes boot time is unmeasured. **The canary is where this becomes a fact — time it, and
   re-plan nodes 02/03 from the measurement rather than from this table.**
4. **Repo corrections owed** (reported, not silently worked around): the stale schematic
   `b85cceac…` in `machine-intelgpu.yaml` (§1), the six plans still naming `talos-1.14.0` in
   `conflicts_with` (§6), and the stale `v1.13.10` in the `aqua:siderolabs/talos` deny-rule
   reason (§3.3, fixed by this plan's own commit).
