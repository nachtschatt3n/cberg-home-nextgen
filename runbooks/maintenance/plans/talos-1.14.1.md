---
plan_id: talos-1.14.1
component: talos
pr: null                              # THE NODE IMAGE HAS NO RENOVATE PR — see §1
                                      # "Attribution". PR #212 is the talosctl CLI
                                      # pin in .mise.toml (retargeted upstream to
                                      # 1.14.1 on 2026-09-19) and is a SEPARATE
                                      # artifact, merged as the LAST step (§3.12).
kind: infra
current: "v1.13.10"                   # live on all 3 nodes, re-verified 2026-09-26 (premise)
target: "v1.14.1"                     # released 2026-09-15; supersedes v1.14.0 (2026-09-03)
update_type: minor                    # one minor hop, but it SKIPS OVER v1.14.0 — §1 reviews
                                      # both release notes because we never run 1.14.0
risk: high                            # rolling reboot of every control-plane node in a
                                      # 3-node hyper-converged cluster: etcd quorum,
                                      # 93 Longhorn volumes at replica=2, and the ONLY
                                      # HTTP data plane (Envoy Gateway) all ride on it
est_duration_min: 160                 # RE-PRICED 2026-09-26 (was 145): the canary may now be
                                      # the HEAVIEST node (39 engines on 02, re-measured 2026-09-26),
                                      # plus the pre-roll etcd snapshot, the UniFi and per-node
                                      # DaemonSet/device-plugin gates. IN-WINDOW only; Phase A
                                      # prep (~35 min) is Flux-inert and runs BEFORE the window.
                                      # Breakdown in §7.
needs_reboot: true                    # three sequential node reboots
exclusive: true                       # the node roll must have sun-attended:2026-09-27 TO
                                      # ITSELF — including plans not yet written (§6).
touches:
  namespaces:
    - kube-system                     # etcd, kube-apiserver, controller-manager,
                                      # scheduler, coredns, cilium, authentik
    - storage                         # longhorn-manager, instance-manager, CSI, 93 volumes
    - network                         # envoy-gateway, envoy-internal, envoy-external,
                                      # k8s-gateway, external-dns, adguard-home, cloudflared
    - monitoring                      # prometheus, alertmanager, grafana, edot/otel collectors
    - security                        # falco (modern_ebpf vs the new 6.18.51 kernel), wazuh-agent
    - "ALL (cluster-wide)"            # every pod on the cluster is evicted and
                                      # rescheduled once; this is not a scoped change
  resources:
    - kubernetes/bootstrap/talos/talconfig.yaml   # talosVersion — THE node image bump
    - .mise.toml                                  # talhelper pin (§3.5) + talosctl CLI pin (§3.12, via PR #212)
    - runbooks/auto-update-policy.yaml            # stale reason text (§3.3)
    # NOT kubernetes/bootstrap/talos/clusterconfig/: those files are gitignored
    # plaintext (clusterconfig/.gitignore), regenerated locally by §3.6 and never committed.
    - node/k8s-nuc14-01                           # 192.168.55.11 — held the VIP on 2026-09-26
    - node/k8s-nuc14-02                           # 192.168.55.12 — heaviest (39 engines); etcd leader on 2026-09-26
    - node/k8s-nuc14-03                           # 192.168.55.13
    - "etcd (3 members, 3.6.14 -> 3.7.1; pre-roll snapshot taken at §3.8a)"
    - "all Longhorn replicas (186 on 2026-09-26, after the pg17 volume retire) / 93 volumes (numberOfReplicas: 2)"
  shared:
    - etcd                            # quorum 3; exactly ONE member may be down
    - cni/cilium                      # DaemonSet restarts per node
    - coredns                         # Talos-bundled version moves with the release
    - storage/longhorn                # instance-manager restart + replica rebuild per node
    - gateway/envoy                   # Envoy Gateway IS the only HTTP(S) data plane (public edge
                                      # envoy-external included). NOT "ingress": ingress-nginx
                                      # was deleted 2026-09-07 (ad1ea7c2).
    - authentik                       # server/worker/outposts reschedule 3x — every SSO login path
    - cert-manager                    # webhook pods reschedule
    - monitoring                      # scrape gaps + node-level alerts during each reboot;
                                      # §4 reads Prometheus, so it is also this plan's instrument
    - igpu-i915                       # intel device plugins re-register gpu.intel.com/i915 +
                                      # npu.intel.com/accel on every rolled node
    - cifs-share                      # every CIFS mount (smb.csi) is torn down and remounted
                                      # with its pods on each node
depends_on: []
conflicts_with:                       # THIS PLAN NEEDS THE WHOLE sun-attended SLOT (also exclusive: true).
  - flux-oci-chart-sources            # names talos-1.14.1 back
  - helm-drift-detection              # names talos-1.14.1 back
  - n8n-2.39.8                        # names talos-1.14.1 back
  # - edot-collector-0.161.0 (RESOLVED 2026-09-26: executed + retired in now:2026-09-26; ref removed) # names talos-1.14.1 back; its pod is evicted 3x
  - otel-operator-0.23.0              # names talos-1.14.1 back
  - multus-macvlan-foundation         # also mutates Talos machine config
  # - nextcloud-34.0.4 (RESOLVED 2026-09-26: executed + retired in now:2026-09-26; ref removed) # declared in case either plan slips onto the other's date
  - jellyfin-12.1                     # sat-attended:2026-10-10; same reason
  # ADDED 2026-09-26 for reciprocity — each of these already names talos-1.14.1:
  # - authentik-2026.8.3 (RESOLVED 2026-09-26: executed + retired in now:2026-09-26; ref removed)
  # - elasticsearch-obs-recovery-3.14.7 (RESOLVED 2026-09-26: executed + retired in now:2026-09-26; ref removed)
  # - falco-9.2.0 (RESOLVED 2026-09-26: executed + retired in now:2026-09-26; ref removed) # falco's eBPF probe meets the new kernel in this plan
  - flux-reconciler-impersonation
  # - icloud-backup-freshness-3.24.2 (RESOLVED 2026-09-26: executed + retired in now:2026-09-26; ref removed)
  - n8n-chart-2.1.1
  # - prometheus-pushgateway-3.9.0 (RESOLVED 2026-09-26: executed + retired in now:2026-09-26; ref removed)
  # - wazuh-2xx-edge-coverage (RESOLVED 2026-09-26: executed + retired in now:2026-09-26; ref removed)
  # DROPPED 2026-09-26: kube-prometheus-stack-91.4.1 (status executed). The rule still
  # stands: any FUTURE same-night kube-prometheus-stack plan must be added here, because
  # §4 reads Prometheus. cilium-1.20.2 / authentik-pg17-decommission / authentik-pg17-volume-retire
  # (0591e95b, plan file deleted): retired.
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
                                      # Past the canary: stop-in-place, or DR from the §3.8a
                                      # etcd snapshot + Longhorn backups (§5.2).
security_ref: null                    # no security driver
finding_refs:
  - F-912f4778                        # "Talos Linux (cluster nodes): v1.13.10 → v1.14.1"
  # DROPPED 2026-09-26: F-0a32b505 (resolved 2026-09-21) and F-9a58f400 (resolved
  # 2026-09-22). An ownership claim on a resolved finding is noise.
premises:
  # All read-only, single commands, no pipes. The three upstream reads use
  # `kubectl get --raw` against a public host with --kubeconfig=/dev/null and a dummy
  # bearer (--token=none): kubectl is the only HTTP client plan-premises.py allows, the
  # dummy token stops kubectl's basic-auth prompt, and no cluster credential is sent.
  - id: nodes-on-v1.13.10
    why: >-
      `current:` claims all three nodes run v1.13.10. A node already on v1.14.x (or a
      fourth node) prints a different string and fails.
    run: kubectl get nodes -o jsonpath='{.items[*].status.nodeInfo.osImage}'
    expect_exact: Talos (v1.13.10) Talos (v1.13.10) Talos (v1.13.10)
  - id: etcd-protocol-3.6
    why: >-
      Talos 1.14 is compatible with etcd 3.6.x only. Reads Prometheus through the
      apiserver service proxy: exactly one server_version group, 3.6.x, with count 3.
      A mixed or 3.5/3.7 cluster prints a second group or another version and fails.
    run: kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=count%20by%20(server_version)%20(etcd_server_version)'
    expect_matches: '^\{"status":"success","data":\{"resultType":"vector","result":\[\{"metric":\{"server_version":"3\.6\.[0-9]+"\},"value":\[[0-9.]+,"3"\]\}\]\}\}$'
  - id: factory-publishes-schematic-v1.14.1
    why: >-
      The Image Factory serves the OCI index for our schematic at v1.14.1, and its
      linux/amd64 entry is the digest measured 2026-09-26. Content-pinned, so a
      TLS-intercepting middlebox answering every path (the 2026-09-06 failure) cannot
      satisfy it, and a silently re-published tag fails it too. The v9.9.9 -> 404
      NEGATIVE CONTROL cannot be a premise: kubectl prints NotFound on stderr with
      rc=1, which plan-premises.py scores as a failure by design and redirects are
      refused. It is therefore a hard gate at §3.1 instead.
    run: kubectl --kubeconfig=/dev/null --server=https://factory.talos.dev --token=none get --raw /v2/installer/43b3cbfc2957259b4588d362709d47387607901d4d3506c1ea46d7ea74cb99a3/manifests/v1.14.1
    expect_matches: '"mediaType":"application/vnd\.oci\.image\.index\.v1\+json".*"digest":"sha256:2c44ce6a02726daa6742eb1ba8efc6dad5dea692db5b8496f52f0523da1d6253","platform":\{"architecture":"amd64","os":"linux"\}'
  - id: newest-stable-talos-is-v1.14.1
    why: >-
      The factory's version list (the set of installable releases) contains v1.14.1 and
      no later STABLE tag (v1.14.2+, v1.15.0+ without a pre-release suffix). A new
      stable release means re-seek the GO (§3.4). v1.15.0-alpha.0 is correctly ignored.
    run: kubectl --kubeconfig=/dev/null --server=https://factory.talos.dev --token=none get --raw /versions
    expect_matches: '^(?!.*"v1\.14\.([2-9]|[1-9][0-9])")(?!.*"v1\.(1[5-9]|[2-9][0-9])\.[0-9]+")(?=.*"v1\.14\.1")'
  - id: longhorn-all-volumes-replica-2
    why: >-
      A RULE, not a count: every Longhorn volume has numberOfReplicas 2 (93 volumes on
      2026-09-26). The volume count is deliberately not pinned — §2.5 measures the live set
      and the replica total and §3.11 gates against that recording, so a volume added or
      retired before the window must not stale this premise. Any volume at 1 or 3 replicas
      (changes the one-node-down arithmetic in §2.5) or an empty list fails.
    run: kubectl get volumes.longhorn.io -n storage -o jsonpath='{.items[*].spec.numberOfReplicas}'
    expect_matches: '^2( 2)*$'
  - id: backup-cronjob-exists
    why: >-
      §2.6 and §6 name storage/daily-backup-all-volumes (NOT the stale
      backup-of-all-volumes). Schedule is UTC (no timeZone set). Missing object fails.
    run: kubectl get cronjob -n storage daily-backup-all-volumes -o jsonpath='{.metadata.name} {.spec.schedule} tz=[{.spec.timeZone}]'
    expect_exact: daily-backup-all-volumes 0 3 * * * tz=[]
  - id: pgadmin-selector
    why: >-
      §4.3 CONTENTS ASSERTION 1 writes through deploy/pgadmin and selects its pod with
      app=pgadmin. A renamed deploy or a changed selector fails here, not mid-window.
    run: kubectl get deploy -n databases pgadmin -o jsonpath='{.spec.selector.matchLabels}'
    expect_exact: '{"app":"pgadmin"}'
  - id: talhelper-3.1.17-published
    why: >-
      §3.5 bumps talhelper to 3.1.17. plan-premises.py cannot run `mise` (not an allowed
      read command), so this reads the same upstream tag from the Go module proxy; a
      non-existent tag returns NotFound (control v3.1.99 measured NotFound 2026-09-26).
      Local installability is still gated by `mise ls-remote talhelper` at §3.5.
    run: kubectl --kubeconfig=/dev/null --server=https://proxy.golang.org --token=none get --raw /github.com/budimanjojo/talhelper/v3/@v/v3.1.17.info
    expect_contains: '"Version":"v3.1.17"'
status: awaiting-go                   # plan-reviewer re-review 2026-09-26: ready-for-go.
                                      # NO GO RECORDED. The 2026-09-12 GO covered v1.14.0 ONLY
                                      # and does NOT carry over — the operator must give a
                                      # FRESH GO for v1.14.1 before the window.
window: "sun-attended:2026-09-27"     # sun-attended is the ONLY allow_reboot window; a node
                                      # roll may not be stamped `now:` (on_demand has
                                      # allow_reboot: false).
sops_refs:
  - docs/sops/talos-upgrade.md
  - docs/sops/application-update.md
  - docs/sops/longhorn.md
  - docs/sops/storage-safety.md
  - docs/sops/backup.md
  - docs/sops/disaster-recovery.md
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/monitoring.md
  - docs/sops/unifi-device-firmware.md
generated: "2026-09-26"
---

# Talos Linux node roll — v1.13.10 → v1.14.1

> **Supersedes `talos-1.14.0.md`.** Same work, new target. Re-measured on 2026-09-20, then
> again on **2026-09-26** in a reviewer fix pass (plan-reviewer verdict `needs-fix`): the
> machine-checkable facts now live in the frontmatter `premises:` block
> (`plan-premises.py talos-1.14.1 --require-premises`), and every drifting baseline —
> VIP owner, etcd leader, Longhorn engine counts, the not-healthy volume set, alert/target/
> rule counts, HTTPRoute count — is **re-measured at §2 by rule, never compared to a number
> written here.** Numbers quoted below are dated examples of what the rule printed.

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
superseded release on every control-plane node. Finding F-0a32b505 called for exactly
this re-resolution (resolved 2026-09-21 by this file); **F-58f0bbab** is the general form
(upstream drift must be caught *before* the GO, not mid-window).

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

### ATTRIBUTION — the correction this plan carries (F-9a58f400, resolved 2026-09-22)

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
   plugin does not work."* Our storage is 93 Longhorn volumes over iSCSI. Longhorn uses
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
hand; §4.1 gates on the canary actually booting.

## 2) Pre-checks

Run all of these **inside the window, before touching a node**. Every one has a stated
pass condition; a fail is a no-go, not a note. **Every baseline is RE-MEASURED here and
recorded to a file in `$SCR`; later gates compare against those files, never against a
number printed in this plan.** Dated example readings (2026-09-26 ~06:00Z) are in italics.

```bash
cd /Users/mu/code/cberg-home-nextgen
export KUBECONFIG="$PWD/kubeconfig"
export TALOSCONFIG="$PWD/kubernetes/bootstrap/talos/clusterconfig/talosconfig"
# Local-only scratch for baselines, the old node configs (§3.6) and the etcd snapshot (§3.8a).
# NOT the repo, NOT /tmp of another session, NOT an iCloud/Nextcloud-synced path.
SCR="$HOME/.cache/talos-1141"; mkdir -p "$SCR"; chmod 700 "$SCR"
stat -f '%Lp %N' "$SCR"                     # MUST print 700
P='/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1'
```

**2.0 — Write the four gate helpers into `$SCR`.** Each was dry-run against the live
cluster on 2026-09-26 **with a negative control** (a crafted baseline that must fail did
fail). They read Prometheus through the apiserver service proxy (`kubectl get --raw`), so
no port-forward can silently die mid-window.

```bash
cat > "$SCR/lh_gate.py" <<'PY'
import json, subprocess, sys, collections
mode, path = sys.argv[1], sys.argv[2]          # mode: baseline | gate
def kget(*a):
    return json.loads(subprocess.check_output(["kubectl", "get", *a, "-o", "json"]))["items"]
vols = kget("volumes.longhorn.io", "-n", "storage")
reps = kget("replicas.longhorn.io", "-n", "storage")
pvs = {p["metadata"]["name"]: p["status"].get("phase") for p in kget("pv")}
wl = kget("deploy,statefulset", "-A")
def consumers(ns, pvc):
    return [(w["kind"] + "/" + w["metadata"]["name"], w["spec"].get("replicas")) for w in wl
            if w["metadata"]["namespace"] == ns and any(
                (x.get("persistentVolumeClaim") or {}).get("claimName") == pvc
                for x in (w["spec"]["template"]["spec"].get("volumes") or []))]
nogo, nh = [], []
for v in vols:
    s, n = v["status"], v["metadata"]["name"]
    if s.get("robustness") == "healthy": continue
    nh.append(n)
    if s.get("state") != "detached":
        nogo.append(f"{n}: {s.get('robustness')} while {s.get('state')}"); continue
    ks = s.get("kubernetesStatus") or {}
    pv = pvs.get(ks.get("pvName") or n, "?"); cons = consumers(ks.get("namespace"), ks.get("pvcName"))
    ok = pv == "Released" or (bool(cons) and all(r == 0 for _, r in cons))
    print(f"  {'EXEMPT' if ok else 'NO-GO '} {n} detached pv={pv} consumers={cons}")
    if not ok: nogo.append(f"{n}: detached but pv={pv}, consumers not all scaled to 0")
total = len(reps)
print("volumes", len(vols), "numberOfReplicas", dict(collections.Counter(v["spec"].get("numberOfReplicas") for v in vols)))
print("replicas total", total, sorted(collections.Counter((r["spec"].get("nodeID"), r["status"].get("currentState")) for r in reps).items()))
print("NOT-HEALTHY", sorted(nh))
if mode == "baseline":
    json.dump({"not_healthy": sorted(nh), "replica_total": total}, open(path, "w"))
    print("recorded ->", path)
else:
    b = json.load(open(path))
    if sorted(nh) != b["not_healthy"]: nogo.append(f"not-healthy set {sorted(nh)} != baseline {b['not_healthy']}")
    if total != b["replica_total"]: nogo.append(f"replica total {total} != baseline {b['replica_total']}")
for x in nogo: print("  FAIL:", x)
print("VERDICT", "NO-GO" if nogo else "PASS")
PY
cat > "$SCR/bk.py" <<'PY'
import json, subprocess, sys, datetime
def kget(*a):
    return json.loads(subprocess.check_output(["kubectl", "get", *a, "-o", "json"]))["items"]
def ts(x):
    return datetime.datetime.fromisoformat(x.replace("Z", "+00:00")) if x else None
now = datetime.datetime.now(datetime.timezone.utc)
exempt = set(json.load(open(sys.argv[1]))["not_healthy"])
bv = {}
for b in kget("backupvolumes.longhorn.io", "-n", "storage"):
    vn = b["spec"].get("volumeName") or (b["metadata"].get("labels") or {}).get("backup-volume")
    t = ts(b["status"].get("lastBackupAt"))
    if vn and t and (vn not in bv or t > bv[vn]): bv[vn] = t
stale, exempted, mismatch = [], [], []
for v in kget("volumes.longhorn.io", "-n", "storage"):
    n = v["metadata"]["name"]
    tv = ts(v["status"].get("lastBackupAt")); tb = bv.get(n)
    if tv and tb and abs((tv - tb).total_seconds()) > 3600:
        mismatch.append((n, str(tv), str(tb)))
    best = max([t for t in (tv, tb) if t], default=None)
    age = "NEVER" if best is None else f"{(now - best).total_seconds() / 3600:.0f}h"
    bad = best is None or (now - best).total_seconds() > 48 * 3600
    if not bad: continue
    if n in exempt and v["status"].get("state") == "detached":
        exempted.append((n, age))
    else:
        stale.append((n, age, v["status"].get("state")))
print("EXEMPT (detached, recorded at 2.5):", len(exempted))
for e in exempted: print("   ", e)
print("Volume-vs-BackupVolume lastBackupAt mismatch >1h:", len(mismatch))
for m in mismatch: print("   ", m)
print("STALE(>48h) or NEVER, not exempt:", len(stale))
for s in stale: print("   ", s)
print("VERDICT", "NO-GO" if stale else "GO")
PY
cat > "$SCR/alerts.py" <<'PY'
import json, subprocess, sys
mode, path = sys.argv[1], sys.argv[2]          # baseline | compare
P = "/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/alerts"
al = json.loads(subprocess.check_output(["kubectl", "get", "--raw", P]))["data"]["alerts"]
firing = [a for a in al if a["state"] == "firing"]
wd = sum(1 for a in firing if a["labels"].get("alertname") == "Watchdog")
def k(a):
    l = a["labels"]
    return "|".join([l.get("alertname", "")] + [f"{x}={l[x]}" for x in ("namespace", "volume", "instance", "account") if x in l])
s = sorted({k(a) for a in firing if a["labels"].get("alertname") not in ("Watchdog", "InfoInhibitor")})
print("Watchdog firing:", wd)
print("firing (excl. Watchdog/InfoInhibitor):", len(s))
for x in s: print("   ", x)
fail = []
if wd != 1: fail.append("Watchdog not firing exactly once -> the alert pipeline itself is broken")
if mode == "baseline":
    json.dump(s, open(path, "w")); print("recorded ->", path)
else:
    new = [x for x in s if x not in set(json.load(open(path)))]
    if new: fail.append(f"NEW alerts vs baseline: {new}")
for f in fail: print("  FAIL:", f)
print("VERDICT", "FAIL" if fail else "PASS")
PY
cat > "$SCR/notready.py" <<'PY'
import json, subprocess, sys
mode, path = sys.argv[1], sys.argv[2]           # baseline | compare
pods = json.loads(subprocess.check_output(["kubectl", "get", "pods", "-A", "-o", "json"]))["items"]
def key(p):
    o = (p["metadata"].get("ownerReferences") or [{}])[0]
    n = o.get("name") or p["metadata"]["name"]
    if o.get("kind") == "ReplicaSet": n = n.rsplit("-", 1)[0]
    if o.get("kind") == "Job": n = "job:" + n.rsplit("-", 1)[0]
    return f"{p['metadata']['namespace']}/{n}"
bad = set()
for p in pods:
    ph = p["status"].get("phase")
    if ph == "Succeeded": continue
    cs = p["status"].get("containerStatuses") or []
    if ph != "Running" or not cs or not all(c.get("ready") for c in cs):
        bad.add(key(p))
print("NOT-READY workloads:", len(bad))
for b in sorted(bad): print("   ", b)
if mode == "baseline":
    json.dump(sorted(bad), open(path, "w")); print("recorded ->", path)
else:
    new = sorted(bad - set(json.load(open(path))))
    print("NEW vs baseline:", new)
    print("VERDICT", "FAIL" if new else "PASS")
PY
cat > "$SCR/nodegate.py" <<'PY'
import json, subprocess, sys
# snap <file>  |  check <file> <rolled-node-name> <rolled-node-was-etcd-leader: yes|no>
mode, path = sys.argv[1], sys.argv[2]
IP = {"k8s-nuc14-01": "192.168.55.11", "k8s-nuc14-02": "192.168.55.12", "k8s-nuc14-03": "192.168.55.13"}
Q = "/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query="
def q(expr):
    r = json.loads(subprocess.check_output(["kubectl", "get", "--raw", Q + expr]))["data"]["result"]
    return {x["metric"]["instance"].split(":")[0]: float(x["value"][1]) for x in r}
carrier = q("node_network_carrier_changes_total%7Bdevice%3D~%22en.*%22%7D")
leader = q("etcd_server_leader_changes_seen_total")
if len(carrier) != 3 or len(leader) != 3:
    sys.exit(f"FAIL: expected 3 series each, got carrier={carrier} leader={leader} (scrape gap? wait and retry)")
print("carrier_changes", carrier); print("leader_changes", leader)
if mode == "snap":
    json.dump({"carrier": carrier, "leader": leader}, open(path, "w")); print("recorded ->", path); sys.exit(0)
rolled, was_leader = sys.argv[3], sys.argv[4] == "yes"
b = json.load(open(path)); fail = []
for ip in IP.values():
    if ip == IP[rolled]: continue            # its counters reset with the reboot
    dc = carrier[ip] - b["carrier"][ip]; dl = leader[ip] - b["leader"][ip]
    print(f"  survivor {ip}: carrier +{dc:.0f}  leader_changes +{dl:.0f}")
    if dc > 0: fail.append(f"{ip} NIC carrier changed during another node's reboot -> STOP (switch/cabling, not Talos)")
    if dl > (1 if was_leader else 0): fail.append(f"{ip} saw {dl:.0f} leader change(s); allowed {1 if was_leader else 0} -> etcd leader loss outside this node's own reboot, STOP")
n = json.loads(subprocess.check_output(["kubectl", "get", "node", rolled, "-o", "json"]))["status"]["allocatable"]
for res, want in (("gpu.intel.com/i915", "5"), ("npu.intel.com/accel", "1")):
    print(f"  {rolled} {res}={n.get(res)}")
    if n.get(res) != want: fail.append(f"{rolled} allocatable {res}={n.get(res)} (want {want}) -> device plugin not re-registered")
for ns, ds in (("security", "falco"), ("security", "falco-log-rotate"), ("security", "wazuh-agent"), ("monitoring", "otel-operator-daemon-collector")):
    s = json.loads(subprocess.check_output(["kubectl", "get", "ds", "-n", ns, ds, "-o", "json"]))["status"]
    print(f"  ds {ns}/{ds} ready {s.get('numberReady')}/{s.get('desiredNumberScheduled')}")
    if not (s.get("numberReady") == s.get("desiredNumberScheduled") == 3): fail.append(f"ds {ns}/{ds} not 3/3")
for f in fail: print("  FAIL:", f)
print("VERDICT", "FAIL" if fail else "PASS")
PY
ls -l "$SCR"/*.py | wc -l                   # MUST print 5
```

*Controls run 2026-09-26:* `lh_gate.py gate` against a baseline naming one volume and 190
replicas → `NO-GO` on both lines; `bk.py` with an empty exempt set → `NO-GO` naming the
detached `icloud-docker-andrea` session volume (147h); `nodegate.py check` against a
baseline with one leader change fewer → `FAIL … leader loss`.

**2.1 — Today's NOW run is finished and no other plan is mid-flight.** This window is
exclusive (`exclusive: true`).

```bash
.venv/bin/python3 runbooks/maintenance-plan.py --open
grep -l 'window: "now:2026-09-26"' runbooks/maintenance/plans/*.md
cat runbooks/state/active-updates.json
git log --oneline -15
```
**PASS, all of:** (a) `--open` lists **no** plan under `now:2026-09-26`, and the `grep`
prints nothing — every plan of the 2026-09-26 NOW run is executed-and-retired or
re-windowed (on 2026-09-26 06:00Z fifteen were still stamped, mid-run); (b)
`active-updates.json` has an empty `"active": []`; (c) no plan other than `talos-1.14.1`
carries `sun-attended:2026-09-27`; (d) `talos-1.14.0` is `superseded` with `window: null`.
**Any leftover `now:2026-09-26` plan = NO-GO**: a half-verified change from yesterday is a
second candidate cause for anything this roll breaks.

**2.2 — Nodes healthy and all on v1.13.10.** (also premise `nodes-on-v1.13.10`)

```bash
mise exec -- kubectl get nodes -o wide
```
**PASS:** 3× `Ready`, `Talos (v1.13.10)`, kubelet `v1.36.0`.
*(Kernel `6.18.48-talos`, containerd `2.2.7`; both move: kernel → 6.18.51, containerd → 2.3.5.)*

**2.3 — etcd quorum, 3.6.x, and the spontaneous-election rate.**

```bash
mise exec -- talosctl -n 192.168.55.11 etcd members
mise exec -- talosctl -n 192.168.55.11,192.168.55.12,192.168.55.13 etcd status
mise exec -- kubectl get --raw "$P/query?query=max(increase(etcd_server_leader_changes_seen_total%5B24h%5D))"
```
**PASS:** exactly 3 members, no `LEARNER`, empty `ERRORS`, converged `RAFT INDEX`,
`PROTOCOL` **3.6.x** on all three (else STOP — v1.14 is 3.6-only), and the 24h leader-change
increase **< 6**. *(2026-09-26: PROTOCOL 3.6.14 / STORAGE 3.6.0, DB 845–886 MB with 244 MB
in use. The leader was `a1ca2fde…` = k8s-nuc14-02 at 05:54Z and `73a201c6…` = k8s-nuc14-03
at 06:03Z — **no reboot in between**. Spontaneous elections measured: 6 in 7d, 4 in 24h, 2
in the busy hour of the NOW run. That base rate is why §3.10's leader-loss rule has a
triage branch.)* ≥ 6 in 24h with no reboots = etcd is already unstable: NO-GO, investigate
first.

**2.4 — Roll order: derive it by RULE, now and again before every node.**

```bash
for ip in 192.168.55.11 192.168.55.12 192.168.55.13; do
  echo -n "$ip vip=" ; mise exec -- talosctl -n $ip get addresses 2>/dev/null | grep -c '192.168.55.10/32'
done
mise exec -- talosctl -n 192.168.55.11,192.168.55.12,192.168.55.13 etcd status   # LEADER column
mise exec -- kubectl -n storage get engines.longhorn.io \
  -o custom-columns='NODE:.spec.nodeID' --no-headers | sort | uniq -c
```
**PASS:** exactly one node reports `vip=1`, and all three MEMBER rows show the same LEADER.

**The rule (applied in §3.8):** walk the fixed tie-break order **02 → 01 → 03**. The
**canary** is the first node in that order holding **neither** the VIP **nor** etcd
leadership. The other two follow in the same 02 → 01 → 03 order. Never roll a node that
holds BOTH the VIP and leadership while an un-rolled node holding neither exists — swap them.
*(Examples: the reviewer's reading, VIP 01 / leader 03 → **02 → 01 → 03**. The 05:54Z
reading, VIP 01 / leader 02 → 03 → 02 → 01. The 06:03Z reading, VIP 01 / leader 03 → 02 →
01 → 03 again. Leadership moved twice in ten minutes; that is why the order is a rule.)*
*Engines per node 2026-09-26 (re-measured after the pg17 volume retire): 01=19, 02=39, 03=34
(+1 detached with no node). So the canary
may well be the HEAVIEST node — §7 prices it that way.*

**2.5 — Longhorn: every not-healthy volume is explained, and the set is RECORDED.**

```bash
python3 "$SCR/lh_gate.py" baseline "$SCR/lh-baseline.json"
cat "$SCR/lh-baseline.json"
```
**The rule (in `lh_gate.py`):** every volume whose `robustness` is not `healthy` must be
**detached** AND (its PV is `Released` OR every Deployment/StatefulSet mounting its PVC is
scaled to **0**). **Any attached not-healthy volume is a NO-GO**, as is a detached one whose
consumer still wants replicas. **PASS:** `VERDICT PASS`, `numberOfReplicas` all `2` (premise
`longhorn-all-volumes-replica-2`; `{2: 93}` on 2026-09-26), and the recorded file carries the not-healthy **names**
and the **replica total**. §2.6 and §3.11 read that file.
*(2026-09-26, re-measured after `authentik-pg17-volume-retire` deleted `data-authentik-postgresql-0`:
the only not-healthy volume is `pvc-f6ec0213-…` = PVC `backup/icloud-docker-andrea-session`,
detached, consumer `Deployment/icloud-docker-andrea` at 0 replicas. Replica total **186**:
01=59 running/1 stopped, 02=66/0, 03=59/1; the 2 `stopped` belong to that one detached volume.
`icloud-docker-mu-session` — exempt in the 2026-09-20 draft — is attached and healthy now.)*

> The set and total are measured here, not written down: whatever §2.5 records is the
> contract for §3.11. Never "correct" the file by hand to match this plan.

At `numberOfReplicas: 2` across 3 nodes, one node down leaves every volume with a replica
there on a single replica — degraded but serving. There is no spare-replica cushion.

**2.6 — Backups fresh.** `docs/sops/backup.md` warns `lastBackupAt` can lag one cycle, and
**Backup CRs can be unsynced (`status.volumeName` empty — hit two plans on 2026-09-26)**, so
this gate does NOT enumerate Backup CRs: it reads `Volume.status.lastBackupAt` and
cross-checks the matching `BackupVolume.status.lastBackupAt`, taking the newer of the two.

```bash
mise exec -- kubectl get jobs -n storage --sort-by=.status.startTime | grep daily-backup-all-volumes | tail -1
python3 "$SCR/bk.py" "$SCR/lh-baseline.json"
```
**PASS:** the newest `daily-backup-all-volumes-*` Job is `Complete` within 24h, and
`VERDICT GO` — i.e. **no volume is NEVER-backed-up or older than 48h unless it is one of the
DETACHED names recorded at §2.5**. The exempt names are printed with their age; read them.
An **attached** volume older than 48h, or any `NEVER`, still fails. A `Volume-vs-BackupVolume
mismatch` line is not a fail by itself but must be explained before GO.
*(2026-09-26: Job `daily-backup-all-volumes-29839860` Complete 03:09:37Z; exempt:
`pvc-f6ec0213-…` 147h — its consumer is scaled to 0, so nothing writes to it; stale 0.)*
**Timing, corrected:** the CronJob `storage/daily-backup-all-volumes` is `0 3 * * *` with no
`timeZone`, i.e. **03:00 UTC = 05:00 Europe/Berlin (CEST)**. The window opens 09:00 Berlin =
07:00Z, so it sees a **~4h-old** backup (the 2026-09-20 draft said ~6h, reading the schedule
as Berlin time).

**2.7 — Flux fully green.** A reconcile landing mid-roll is a confounder.

```bash
mise exec -- flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
mise exec -- flux get helmreleases   -A | awk 'NR==1 || $5 != "True"'
```
**PASS:** both print only the header row.

**2.8 — Observability baseline, recorded to files.** §4.3/§4.4 compare against these.

```bash
python3 "$SCR/alerts.py"   baseline "$SCR/alerts-baseline.json"
python3 "$SCR/notready.py" baseline "$SCR/notready-baseline.json"
mise exec -- kubectl get --raw "$P/targets" | python3 -c "
import sys,json
t=json.load(sys.stdin)['data']['activeTargets']
print('targets',len(t),'up',sum(1 for x in t if x['health']=='up'))
print('etcd:',[(x['labels'].get('instance'),x['health']) for x in t if 'etcd' in x['labels'].get('job','')])" \
  | tee "$SCR/targets-baseline.txt"
mise exec -- kubectl get --raw "$P/rules" | python3 -c "
import sys,json; g=json.load(sys.stdin)['data']['groups']
print('groups',len(g),'rules',sum(len(x['rules']) for x in g))" | tee "$SCR/rules-baseline.txt"
```
**PASS:** `alerts.py` prints `Watchdog firing: 1` and `VERDICT PASS` — **the Watchdog is the
positive control that the alert pipeline is alive; an empty firing list proves nothing on
its own.** Every target `up`; the three etcd targets `.11/.12/.13:2381` up.
*(2026-09-26: Watchdog 1, other firing **0** at 05:54Z — the four `ICloudBackupPhotosStale*`
alerts of the 2026-09-20 draft are gone; one transient `AuthentikTaskWorkersZero` fired at
06:02Z during the concurrent authentik upgrade. Targets **101 up 101**; groups/rules
**126 / 532**; not-ready workloads **0**.)* Whatever set is recorded is the baseline — do not
edit it to match these examples.

**2.9 — Envoy Gateway is the only HTTP data plane. Record its pre-state.**

```bash
mise exec -- kubectl get gateway -A
mise exec -- kubectl get httproute -A --no-headers | wc -l | tee "$SCR/httproutes-baseline.txt"
mise exec -- kubectl get pods -n network -o wide | grep -E 'envoy-(internal|external|gateway)'
# Pick ONE real host per gateway that answers 2xx WITH A BODY (not an auth 302 with 0B —
# measured 2026-09-26: the first envoy-external route returned 302 0B). Hostnames stay out
# of this public repo; they live only in $SCR.
INT_HOST=<host routed on envoy-internal>; EXT_HOST=<host routed on envoy-external>
printf '%s\n%s\n' "$INT_HOST" "$EXT_HOST" > "$SCR/probe-hosts.txt"
{ curl -sS -o /dev/null -w 'internal %{http_code} %{size_download}\n' -H "Host: $INT_HOST" https://192.168.55.103/ -k
  curl -sS -o /dev/null -w 'external %{http_code} %{size_download}\n' -H "Host: $EXT_HOST" https://192.168.55.104/ -k
} | tee "$SCR/curl-baseline.txt"
```
**PASS (probe baseline):** both lines `2xx` with a size **> 0**; if a host gives 3xx/0B, pick
another before continuing.

**PASS:** `envoy-internal` (192.168.55.103) and `envoy-external` (192.168.55.104) both
`PROGRAMMED=True`; the route count recorded (*109 on 2026-09-26*); and each of
`envoy-internal`, `envoy-external`, `envoy-gateway` has **3 pods, one per node**. Below 3
healthy pods across ≥2 nodes: **stop** — there is no fallback controller (ingress-nginx was
deleted 2026-09-07, `ad1ea7c2`).

**2.10 — Longhorn instance-manager PDBs.**

```bash
mise exec -- kubectl -n storage get pdb | grep instance-manager
mise exec -- kubectl -n storage get pods -l longhorn.io/component=instance-manager -o wide
```
**PASS:** exactly 3 PDBs, each with a live pod, one per node.
**`ALLOWED DISRUPTIONS = 0` on all three is the correct steady state, not a fault** (each
selects one pod with `minAvailable: 1`; `docs/sops/talos-upgrade.md` §9). Do not delete them.
Do not reach for `--drain=false` on the strength of seeing a zero here.

**2.11 — UniFi: no switch firmware can land in this window.** (`docs/sops/unifi-device-firmware.md`
— a switch reboot and a node reboot in the same slot is the 2026-09-24 partition, compounded.)

```bash
mise exec -- unifictl local health get >/dev/null && echo session-ok     # cached session only
mise exec -- unifictl local device list -o json | python3 -c "
import sys,json
d=json.load(sys.stdin); d=d.get('data',d) if isinstance(d,dict) else d
bad=[x.get('name') for x in d if x.get('upgradable')]
print('devices',len(d),'upgradable=True:',bad)"
```
**PASS:** `session-ok`, `devices 10` (*2026-09-26*) and `upgradable=True: []` — every switch,
AP and the gateway reports `upgradable=False`. **Plus, read by the operator in the Network UI**
(UniFi OS Settings › Control Plane › Updates › UniFi Devices): device **auto-update OFF**
(`mgmt.auto_upgrade: false`) and no scheduled `upgrade` task. `unifictl` has no reader for
`get/setting/mgmt` (checked 2026-09-26: no `setting` subcommand), so this half is a
human read, stated as such. **No switch firmware in this window, even if one becomes
upgradable mid-roll.**

**2.12 — Per-node baseline for §3.10.**

```bash
python3 "$SCR/nodegate.py" snap "$SCR/node-pre.json"
mise exec -- kubectl get nodes -o json | python3 -c "
import sys,json
for n in json.load(sys.stdin)['items']:
    a=n['status']['allocatable']; print(n['metadata']['name'],a.get('gpu.intel.com/i915'),a.get('npu.intel.com/accel'))"
mise exec -- kubectl get ds -n security falco falco-log-rotate wazuh-agent
mise exec -- kubectl get ds -n monitoring otel-operator-daemon-collector
```
**PASS:** 3 carrier series and 3 leader-change series recorded; every node allocates
`gpu.intel.com/i915=5` and `npu.intel.com/accel=1`; the four DaemonSets are `3/3` ready.
*(All true 2026-09-26.)*

## 3) Steps

### Phase A — PREP, run BEFORE the window (~35 min, zero cluster effect)

**Why this is safe to do early:** `kubernetes/bootstrap/talos/` is **not reconciled by
Flux** — every Flux Kustomization `spec.path` points under `./kubernetes/apps` or the
flux config dirs; none references `bootstrap`. The talhelper-generated configs are
gitignored local files, applied by `talosctl` by hand. So committing and pushing a `talosVersion` bump changes
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
mise ls-remote talhelper | grep -c -x '3.1.17'            # MUST print 1 (installable here)
sed -i '' 's|^talhelper = "3\.1\.11"$|talhelper = "3.1.17"|' .mise.toml
git --no-pager diff -U0 .mise.toml
mise install
mise exec -- talhelper --version                           # expect 3.1.17
```
**Expected diff — EXACTLY this one line (dry-tested on a scratch copy 2026-09-26, BSD sed):**

```diff
@@ -47 +47 @@
-talhelper = "3.1.11"
+talhelper = "3.1.17"
```
Do NOT touch `"aqua:siderolabs/talos"` (line 28) here — that is PR #212, §3.12.

**3.6 — Regenerate and READ THE DIFF. This is the real gate, because talhelper cannot
be it.**

**What these files are (corrected 2026-09-26):** `kubernetes/bootstrap/talos/clusterconfig/
kubernetes-k8s-nuc14-0{1,2,3}.yaml` and `talosconfig` are **gitignored plaintext**
(`clusterconfig/.gitignore`), written by `talhelper genconfig`, **not SOPS-encrypted and not
in git** — `git show HEAD:` of them fails and `sops -d` has nothing to decrypt. The only copy
of the "old" config is the one on this disk, and `genconfig` overwrites it. So snapshot it
FIRST, and prove the snapshot matches what the nodes actually run:

```bash
# (1) Snapshot the CURRENT generated configs into the mode-700 scratch dir — BEFORE genconfig
SCR="$HOME/.cache/talos-1141"; mkdir -p "$SCR"; chmod 700 "$SCR"
for n in 01 02 03; do
  cp -p kubernetes/bootstrap/talos/clusterconfig/kubernetes-k8s-nuc14-$n.yaml "$SCR/old-$n.yaml"
done
chmod 600 "$SCR"/old-*.yaml; ls -l "$SCR"/old-*.yaml

# (2) The OLD install image must equal what the LIVE nodes run — else "old" is not the baseline
for n in 01 02 03; do grep -h 'image: factory' "$SCR/old-$n.yaml"; done
for ip in 11 12 13; do
  mise exec -- talosctl -n 192.168.55.$ip get machineconfig -o yaml | grep 'image: factory' | sort -u
done
```
**PASS (2):** all six lines are exactly
`image: factory.talos.dev/installer/43b3cbfc2957259b4588d362709d47387607901d4d3506c1ea46d7ea74cb99a3:v1.13.10`
(*measured 2026-09-26: 6/6*). A mismatch means the local files are stale relative to the
cluster — STOP; regenerating on top of them diffs against the wrong baseline.

```bash
# (3) Validate + regenerate
( cd kubernetes/bootstrap/talos && mise exec -- talhelper validate talconfig talconfig.yaml )
mise exec -- task talos:generate-config
# (4) Diff NEW vs the scratch OLD
for n in 01 02 03; do
  echo "=== nuc14-$n ==="
  diff -u "$SCR/old-$n.yaml" kubernetes/bootstrap/talos/clusterconfig/kubernetes-k8s-nuc14-$n.yaml
done
git status --short kubernetes/bootstrap/talos/clusterconfig/   # MUST print nothing (still ignored)
```

**Expected `validate` output — this warning is EXPECTED and is not a failure** (measured
verbatim against a v1.14.1 scratch copy, exit code 0):

```
There are issues with your talhelper config file:
field: "talosVersion"
  * WARNING: "v1.14.1" might not be compatible with this Talhelper version you're using
```

**PASS (4):** per node, the only differences are the `machine.install.image` tag
`v1.13.10 → v1.14.1` and the config version-contract stamp (if any).
**STOP AND INVESTIGATE** if the diff shows any of: a new `SecurityProfileConfig` document
(workload isolation — §1 item 9, must NOT appear), a new `UnattendedInstall` document
replacing `machine.install`, `machine.sysctls` / `machine.udev.rules` / `machine.kubelet`
rewritten into `SysctlConfig` / `UdevRulesConfig` / `KubeNodeConfig` documents, a changed
`nameservers`/`searchDomain` block, any **removed** field, or **any change to a secret/cert
field** (a regenerated secret here would mean `talsecret` was not used). Alpha machinery
emitting a GA-era document shape is exactly the failure this step exists to catch — and
v1.14.1's `fix: tighten the validation of v1alpha1 configs vs. migration` lands on precisely
this surface. If it appears, do not "fix it up": restore the old files
(`cp -p "$SCR/old-0N.yaml" kubernetes/bootstrap/talos/clusterconfig/kubernetes-k8s-nuc14-0N.yaml`),
abort Phase A and reschedule.

Keep `$SCR/old-*.yaml` until §4.4 passes (they are the §5.3 restore source), then `rm -P`
them — they hold the cluster's machine secrets in plaintext.

**3.7 — Commit and push (still zero cluster effect).**

Per `CLAUDE.md`, use `--only` with explicit paths — the worktree is shared. The regenerated
`clusterconfig/` files are **not** in this list: they are gitignored and never committed.

```bash
MSG="$SCR/talos-1141-commit-msg.txt"         # unique filename, not /tmp/talos-msg.txt
cat > "$MSG" <<'MSGEOF'
feat(talos)!: node image v1.13.10 -> v1.14.1 (config only; roll is manual)

Bumps talosVersion in talconfig.yaml and talhelper 3.1.11 -> 3.1.17 (its final
release). Flux does not reconcile kubernetes/bootstrap/talos/, and the node
configs under clusterconfig/ are gitignored and regenerated locally, so this
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
Finding: F-912f4778
MSGEOF

git commit --only \
  kubernetes/bootstrap/talos/talconfig.yaml \
  runbooks/auto-update-policy.yaml \
  .mise.toml \
  -F "$MSG"

git log -1 --format=%s          # MUST be the feat(talos)! subject above — concurrent
                                # sessions can swap messages; amend before push
git show --stat HEAD            # exactly these three files, nothing else
git push
```

### Phase B — THE ROLL (in-window)

**Concurrency rule, absolute: exactly ONE node down at a time.** All three nodes are etcd
members; a 3-member cluster tolerates the loss of exactly one. Two down = quorum lost = the
API server is gone and the roll cannot be driven. There is no step in this plan where two
nodes are unavailable.

**3.8 — Roll order: apply the §2.4 rule, and RE-CHECK before EVERY node.**

Before each node (including the first), re-run the §2.4 VIP/leader loop and apply the rule:
tie-break order **02 → 01 → 03**; canary = first node in that order holding neither the VIP
nor etcd leadership; then the remaining un-rolled nodes in the same order; never roll a node
holding BOTH while an un-rolled node holding neither exists. Write down, per node, **who held
the VIP and who led etcd immediately before it rolled** — §3.10 needs the leader flag.

| Node | Engines 2026-09-26 | Note |
|---|---:|---|
| `k8s-nuc14-01` / .11 | 19 | held the VIP 192.168.55.10 on 2026-09-26 |
| `k8s-nuc14-02` / .12 | **39** | heaviest; etcd leader at 05:54Z |
| `k8s-nuc14-03` / .13 | 34 | etcd leader at 06:03Z |

**If the node about to roll holds the VIP**, expect the kubeconfig endpoint
(192.168.55.10) to drop for up to ~1 min while the VIP moves; talosctl drives nodes by their
own IPs and is unaffected. Do not interpret that blip as a failure; re-run `kubectl get nodes`
until it answers, then continue watching the drain.

For each node, in the order the rule gives, run **3.9 → 3.10 → 3.11** to completion before
starting the next.

**3.8a — Pre-roll etcd snapshot (ONCE, immediately before the first node).**
Per `docs/sops/talos-upgrade.md` Step 0.4 (added 2026-09-26 — the SOP had no etcd snapshot
procedure). Longhorn backups do not cover control-plane state.

```bash
LEADER_IP=<ip whose MEMBER id equals the LEADER column in §2.4's etcd status>
mise exec -- talosctl -n "$LEADER_IP" etcd snapshot "$SCR/etcd-pre-v1.14.1.db"
chmod 600 "$SCR/etcd-pre-v1.14.1.db"
stat -f '%Lp %z %N' "$SCR/etcd-pre-v1.14.1.db"
stat -f '%Lp %N' "$SCR"
```
**PASS:** file mode `600`, dir mode `700`, and a size in the same order as §2.3's `DB SIZE`
(*845–886 MB on 2026-09-26*; a 0-byte or few-KB file is a FAIL — do not start the roll). It is
**local only**: never copy it into the repo or a synced folder; it holds every Secret. Delete
it (`rm -P`) after §4.4 has passed and the cluster has soaked 24h. Restore path: §5.2.

**3.9 — Upgrade one node.**

```bash
python3 "$SCR/nodegate.py" snap "$SCR/node-pre-<node-name>.json"     # counters just before
mise exec -- task talos:upgrade-node IP=<node-ip>
```

This installs the new image, then cordons, drains, and reboots. Expect it to sit on
`evicting pod storage/instance-manager-<hash>` for a while. **That is normal.** Per
`docs/sops/talos-upgrade.md` §9 the drain waits for Longhorn volumes to **detach**, not for a
stuck PDB. Watch the engine count fall:

```bash
mise exec -- kubectl -n storage get engines.longhorn.io -o json | python3 -c "
import sys,json
print(len([e for e in json.load(sys.stdin)['items'] if e['spec'].get('nodeID')=='<node-name>']))"
```
*(Engines that must drain to 0, 2026-09-26: 01=19, 02=39, 03=34 — re-read §2.4's count for
the node you are rolling.)*

**POSITIVE CONTROL for §4.4 check 4 — canary only, mid-drain.** `notready.py` and the phase
query pass on an ABSENCE, and on 2026-09-26 both read 0, so neither has been seen to fail.
While the canary's engine count is still **above 0**, run once:

```bash
python3 "$SCR/notready.py" compare "$SCR/notready-baseline.json"
mise exec -- kubectl get pods -A --field-selector status.phase!=Running,status.phase!=Succeeded
```
**PASS (of the control):** `notready.py` prints `VERDICT FAIL` naming **≥1** workload **and**
the phase query prints **≥1** pod. Expected, because evicted pods sit Pending/not-Ready
mid-drain — e.g. `envoy-internal`/`envoy-external`/`envoy-gateway` use
`topologySpreadConstraints` (`DoNotSchedule` on hostname) with a PDB `minAvailable: 2`, so the
evicted replica stays Pending until the node returns. **A `VERDICT PASS` mid-drain means the
helper is blind: STOP before §3.10** and fix it; do not trust §4.4 check 4 without it. Engines going N → 0 is the drain progressing. When it hits 0,
Longhorn deletes the PDB itself and the drain completes in seconds.

**Do NOT** delete the PDBs. **Do NOT** use `EXTRA_FLAGS='--drain=false'` pre-emptively. Only if
the drain **times out** with `error when waiting for pod "instance-manager-…" to terminate:
context deadline exceeded` (the load-dependent recreate race in the SOP): **uncordon the node
first**, then delete the `Pending` pods so the scheduler spreads the attach load. Do not wait it
out. `--drain=false` is a last resort and never unattended.

**3.10 — Node health gate.**

```bash
mise exec -- kubectl get nodes -o wide
mise exec -- talosctl -n <node-ip> version --short
mise exec -- talosctl -n 192.168.55.11,192.168.55.12,192.168.55.13 etcd status
python3 "$SCR/nodegate.py" check "$SCR/node-pre-<node-name>.json" <node-name> <yes|no: was it etcd leader at 3.8?>
```
**PASS, all of:** the node is `Ready` and **not** `SchedulingDisabled`; `Tag: v1.14.1`; etcd
reports **3 members**, no `LEARNER`, empty `ERRORS`, raft indexes converged (do not proceed
until the rebooted member has rejoined — `Ready` with a missing member is a quorum of two);
**and `nodegate.py` prints `VERDICT PASS`**, which asserts:

- `gpu.intel.com/i915=5` and `npu.intel.com/accel=1` allocatable again on the rolled node
  (the Intel device plugins re-registered — Frigate/Jellyfin/Plex/Immich and the NPU
  workloads depend on them);
- DaemonSets `security/falco`, `security/falco-log-rotate`, `security/wazuh-agent`,
  `monitoring/otel-operator-daemon-collector` all **3/3** ready. **falco meets the new kernel
  here** (6.18.48 → 6.18.51): it runs `driver.kind: modern_ebpf` (CO-RE, no kmod build), so a
  load failure shows as the falco pod on this node not Ready — that is a FAIL, not noise;
- **no NIC carrier change on the two nodes that did NOT reboot**
  (`node_network_carrier_changes_total{device=~"en.*"}`, per survivor, unchanged);
- **no etcd leader change on the survivors beyond what this node's own reboot explains**
  (`etcd_server_leader_changes_seen_total`: +1 allowed only if this node was leader).

*Expect `PROTOCOL` 3.7.x on upgraded members and 3.6.14 on the rest; a mixed reading
mid-roll is correct. Expect the otel daemon collector on this node to log `memory_limiter`
refusals / dropped data while it sheds the backlog buffered during the reboot — that is
backpressure working, not a failure, as long as the DaemonSet is 3/3 and §4.3 CONTENTS
ASSERTION 2 holds at the end.*

**STOP rules (UniFi / network, from `docs/sops/unifi-device-firmware.md`):**
- A **carrier change on a survivor** = the network moved under us (switch, cabling, a
  firmware push): **STOP the roll**, do not start the next node, check §2.11 and
  `unifictl local event list`. It is not a Talos problem and must not be diagnosed as one.
- An **etcd leader change on the survivors that this node's reboot does not explain** =
  STOP and triage. Base rate is non-zero (§2.3: 6 spontaneous elections in 7d, 2 in one busy
  hour on 2026-09-26), so the operator may continue ONLY after confirming, together: no
  carrier change anywhere, `etcd status` clean on all 3, and `min_over_time(etcd_server_has_leader[15m])`
  = 1 on both survivors (a re-election, not a leaderless period). Otherwise stop part-rolled
  (§5.2).

**3.10a — Forward-auth gate (F-89376ab7). Forward-auth must stay available across every node
reboot; check it after EACH node, before 3.11.**

The 13 authentik forward-auth outposts (`kube-system/ak-outpost-*`) are **single-replica**,
and that is deliberate for now. A non-embedded proxy outpost on 2026.8.3 keeps its sessions
in the pod's own `/tmp` (the filesystem store; only the embedded outpost uses PostgreSQL).
On a session miss it clears the cookie and restarts login. Envoy load-balances every
ext_authz check per request across the outpost's endpoints, so `kubernetes_replicas: 2`
would ping-pong users between two session stores and break XHR and assets on every protected app.
**Do not "fix" a failure here by scaling outposts.** What the drain gives us instead: 3.9
cordons and drains first, so each outpost on the rolled node is evicted and restarts on a
survivor within seconds. **Expect** a short 5xx on the apps whose outpost lived on that node
and one silent re-login per user per app (their session file died with the pod). A page
reload fixes it. Homepage widgets may error until then.

```bash
# (a) all 13 outposts back at 1/1 and none on the node that just rolled
mise exec -- kubectl get deploy -n kube-system -l app.kubernetes.io/managed-by=goauthentik.io
mise exec -- kubectl get pods -n kube-system -l app.kubernetes.io/managed-by=goauthentik.io -o wide
# (b) every forward-auth host answers through the gateway (hosts come from the live
#     SecurityPolicies -> HTTPRoutes; the list stays in $SCR, never in this repo)
mise exec -- kubectl get securitypolicy -A -o json | python3 -c "
import sys, json, subprocess
for p in json.load(sys.stdin)['items']:
    if not p['spec'].get('extAuth'): continue
    ns = p['metadata']['namespace']
    for t in p['spec'].get('targetRefs', []):
        h = subprocess.run(['mise','exec','--','kubectl','get','httproute','-n',ns,t['name'],
            '-o','jsonpath={.spec.hostnames[0]}'], capture_output=True, text=True).stdout
        print(t['name'], h)" > "$SCR/fwd-auth-hosts.txt"
while read -r name host; do
  code=$(curl -s -o /dev/null -m 10 -w '%{http_code}' "https://$host/")
  echo "$name $code"
done < "$SCR/fwd-auth-hosts.txt"
```
**PASS:** (a) 13/13 deployments `1/1`, no outpost pod on a `SchedulingDisabled` node;
(b) every host returns **302** (to the authentik authorize endpoint) or **200**, and none
returns 5xx/000. Baseline 2026-09-26 (dry-run of exactly this block): 12 SecurityPolicy hosts,
all 302. The 13th outpost, uptime-kuma, is `mode: proxy` with no SecurityPolicy (its HTTPRoute
points at the outpost itself), so the loop does not cover it. Curl its host once by hand and
expect 302. **FAIL** means an outpost is
Pending or CrashLooping: `kubectl describe` it and read its logs before starting the next node.
Losing forward-auth on two nodes' worth of apps at once is what this gate exists to prevent.

**3.11 — THE LONGHORN GATE. This is the step that blows the time budget.**

Do **not** start the next node until this passes. With `numberOfReplicas: 2` there is no
cushion: starting the next node while volumes are still degraded means volumes on **zero**
replicas.

```bash
python3 "$SCR/lh_gate.py" gate "$SCR/lh-baseline.json"
```

**PASS — `VERDICT PASS`, which asserts together:**

1. The not-healthy set is **exactly the names recorded at §2.5** — same names, no more, no
   fewer — and each is still detached with its PV Released / consumer at 0. Any **attached**
   not-healthy volume (`degraded`, `rebuilding`) fails: `degraded` means one replica, exactly
   the state we must not enter the next reboot in.
2. The replica total equals **the total recorded at §2.5** (*186 on 2026-09-26*).
3. Read the printed per-node table yourself: the just-rebooted node is back with a
   `running` count in the same order as its §2.5 line.

**Why this can run long.** `replica-replenishment-wait-interval` is **600s**, so Longhorn
waits 10 minutes before replenishing a missing replica elsewhere. If the node returns inside
that window (typical), replicas restart in place and rebuild incrementally — fast. If the
reboot overruns 10 minutes, Longhorn builds **full** replicas on the survivors and the gate
can take far longer over 92 attached volumes (93 minus the one detached). `concurrent-replica-rebuild-per-node-limit` is
**8** and `replica-rebuild-concurrent-sync-limit` is `{"v1":"1"}`, deliberately paced.

**Budget rule: if the gate has not passed 25 minutes after the node returned `Ready`, stop
rolling.** Do not skip the gate, do not shorten it, do not start the next node. Leave the
cluster part-rolled (a supported transient), finish §4.4 on the current mix, and reschedule.

**3.12 — Merge PR #212 (the talosctl CLI pin) — LAST, and only after all three nodes
report v1.14.1.**

PR #212 edits `.mise.toml` **line 28** (`"aqua:siderolabs/talos"`); §3.5 already changed
**line 47** (`talhelper`). The hunks do not overlap, but the PR's base is older than §3.7's
commit, so GitHub may report it `BEHIND`/`CONFLICTING` or its checks may be stale.

```bash
mise exec -- kubectl get nodes -o wide | grep -c 'Talos (v1.14.1)'   # MUST be 3
gh pr view 212 --json mergeable,mergeStateStatus,files --jq '{mergeable,mergeStateStatus,files:[.files[].path]}'
# if mergeStateStatus is BEHIND or DIRTY, or mergeable is CONFLICTING:
#   gh pr comment 212 --body '@renovatebot rebase'     # then wait for the new head + checks
gh pr checks 212
gh pr diff 212
```
**Merge PASS condition — all of:** exactly 3 nodes on `Talos (v1.14.1)`; `files` is exactly
`[".mise.toml"]`; `mergeable` = `MERGEABLE`; `gh pr checks 212` all pass on the CURRENT head
(including `Flate Render Gate`); and `gh pr diff 212` changes **only line 28** —
`"aqua:siderolabs/talos" = "1.13.10"` → `"1.14.1"` — and **does not revert
`talhelper = "3.1.17"`** (a stale base shows up here as a `-talhelper = "3.1.17"` line; that is
a FAIL, rebase first). Then:

```bash
gh pr merge 212 --squash
git pull
mise install
mise exec -- talosctl version --short         # Client: v1.14.1, and it still reaches the nodes
grep -n -E '^(talhelper|"aqua:siderolabs/talos")' .mise.toml   # talhelper 3.1.17 AND talos 1.14.1
```

**If fewer than 3 nodes reached v1.14.1, do NOT merge #212.** Leave it open; a v1.13.10
client drives a mixed cluster correctly (n±1, older client is the normal direction).

**Explicitly NOT in this window:** `task talos:upgrade-k8s`. Kubernetes stays on v1.36.0,
which §1 proves is inside Talos 1.14's supported range (1.32.0 – 1.37.99). A Kubernetes minor
bump is its own plan, its own window (SOP lesson #6).

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

**CANARY GO/NO-GO (after the first node only — whichever node §3.8's rule picked).** All of
§3.10 (incl. `nodegate.py` PASS), §3.11 and the cmdline check pass, **and**
`kubectl get pods -A --field-selector spec.nodeName=<canary>` shows pods scheduling and running
there again. **Time the canary** (upgrade start → §3.11 PASS) and re-plan the remaining two
from that measurement, not from §7's table. If any check fails: **stop, roll the canary back
(§5.1), and do not touch the other two.** This is the one point in the plan with a clean exit.

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
> # the pod must be on a ROLLED node — resolve it, don't assume it.
> # Selector is app=pgadmin (deploy/pgadmin spec.selector, premise `pgadmin-selector`).
> # The 2026-09-20 draft used app.kubernetes.io/name=pgadmin, which matches NOTHING, so
> # jsonpath '{.items[0]...}' errored and the "rolled node" check could never run.
> mise exec -- kubectl -n databases get pod -l app=pgadmin \
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
> P='/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1'
> mise exec -- kubectl get --raw "$P/targets" | python3 -c "
> import sys,json
> t=json.load(sys.stdin)['data']['activeTargets']
> print('targets',len(t),'up',sum(1 for x in t if x['health']=='up'))
> print('etcd:',[(x['labels'].get('instance'),x['health']) for x in t if 'etcd' in x['labels'].get('job','')])
> for x in t:
>     if x['health']!='up': print('  DOWN',x['labels'].get('job'),x['labels'].get('instance'))"
> cat "$SCR/targets-baseline.txt"
> # the floor — etcd must still be PRODUCING, not merely 'up'
> mise exec -- kubectl get --raw "$P/query?query=count(etcd_server_has_leader)"
> mise exec -- kubectl get --raw "$P/rules" | python3 -c "
> import sys,json; g=json.load(sys.stdin)['data']['groups']
> print('groups',len(g),'rules',sum(len(x['rules']) for x in g))"
> cat "$SCR/rules-baseline.txt"
> ```
> **PASS — compared to the §2.8 FILES, not to numbers in this plan:** `targets N up N` where N
> is **≥ the recorded target total** (a *smaller total* is a FAIL — a disappeared target reads
> as 100% up) and up == total; the etcd query returns `"value":[…,"3"]`; and `groups`/`rules`
> **equal the recorded line** (no rule group should vanish across a node roll). *(2026-09-26
> reading, for orientation only: 101 up 101, 126 groups / 532 rules.)*
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
> cat "$SCR/httproutes-baseline.txt"
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
> INT_HOST=$(sed -n 1p "$SCR/probe-hosts.txt"); EXT_HOST=$(sed -n 2p "$SCR/probe-hosts.txt")
> curl -sS -o /dev/null -w 'internal %{http_code} %{size_download}\n' -H "Host: $INT_HOST" https://192.168.55.103/ -k
> curl -sS -o /dev/null -w 'external %{http_code} %{size_download}\n' -H "Host: $EXT_HOST" https://192.168.55.104/ -k
> cat "$SCR/curl-baseline.txt"
> ```
> **PASS:** both Gateways `PROGRAMMED=True`; the HTTPRoute count equals the §2.9 baseline
> recorded in `$SCR/httproutes-baseline.txt` (*109 on 2026-09-26; it was 107 on 09-20 and 103
> before that — this number drifts, which is why it is a file*); `routes NOT
> Accepted/ResolvedRefs: 0`; and both curls return the **same status class as
> `$SCR/curl-baseline.txt` (2xx) with a non-zero body size** in the same order of magnitude. A
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

# 4. no pod left behind — phase AND readiness, vs the §2.8 baseline
mise exec -- kubectl get pods -A --field-selector status.phase!=Running,status.phase!=Succeeded
python3 "$SCR/notready.py" compare "$SCR/notready-baseline.json"

# 5. Flux still green (it has been reconciling against a moving cluster all window)
mise exec -- flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
mise exec -- flux get helmreleases   -A | awk 'NR==1 || $5 != "True"'

# 6. Longhorn: the §3.11 gate one final time + the §4.2 per-node attach check
python3 "$SCR/lh_gate.py" gate "$SCR/lh-baseline.json"
# 7. all three CONTENTS ASSERTIONS from §4.3
# 8. alerts vs the §2.8 baseline SET — after a settle period, NOT immediately
python3 "$SCR/alerts.py" compare "$SCR/alerts-baseline.json"
```

**PASS on 4:** the field-selector query prints no pods **and** `notready.py` prints
`VERDICT PASS` (no workload not-ready that was ready at §2.8). The phase query alone is a
shape check: a **CrashLoopBackOff pod still reports `phase: Running`**, so it is invisible to
`status.phase!=Running`; `notready.py` reads every container's `ready` flag instead. A
transient CronJob pod may appear as `job:<name>` — re-run after it completes before calling it.

**PASS on 8 — a SET comparison, with a live-pipeline control:** `alerts.py compare` prints
`Watchdog firing: 1` **and** `VERDICT PASS`, **sustained for ≥15 minutes** after the last node
returned. The Watchdog is the positive control: the §2.8 baseline firing set was **empty**
on 2026-09-26, so "no alerts" cannot distinguish a healthy cluster from a dead
Prometheus → Alertmanager path — a missing Watchdog does. Any alertname not in the baseline
is a real regression, not reboot noise; node-level alerts fire during every reboot and clear
on their own, which is what the 15 minutes are for (budgeted in §7).

CONTROL: metric ALERTS — `alerts.py` reads the firing set from Prometheus `/api/v1/alerts`; the gate asserts the Watchdog firing exactly once and no alertname outside the §2.8 set (no allowances).
CONTROL: metric etcd_server_has_leader — §4.3 CA2 asserts `count(...) == 3` (the floor), and §3.10's triage branch asserts `min_over_time` = 1 on survivors.
CONTROL: metric etcd_server_leader_changes_seen_total — §3.10 `nodegate.py`: survivors may rise by at most 1, and only when the rolled node was leader.
CONTROL: metric node_network_carrier_changes_total — §3.10 `nodegate.py`: survivors' `device=~"en.*"` counters unchanged across each node's reboot.
CONTROL: metric etcd_server_version — premise `etcd-protocol-3.6` (exactly one `server_version` group, 3.6.x, count 3).
CONTROL: metric up — §4.3 CA2 target total ≥ the §2.8 recorded total, all up.

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
(~45–50 min for the canary, including its Longhorn re-gate), never a `git revert`.** The git
commit is inert; reverting it moves no node.

### 5.1 — Per-node rollback (REAL, and it is the canary's abort path)

Talos keeps the previous installed image on the alternate boot partition:

```bash
mise exec -- talosctl -n <node-ip> version --short     # Tag: v1.14.1 before the rollback
mise exec -- talosctl rollback --nodes <node-ip>
mise exec -- talosctl -n <node-ip> version --short     # Tag: v1.13.10 after it returns
```
Then re-run §3.10 + §3.11 to confirm the node came back on v1.13.10 with its Longhorn
replicas running, and §4.1 for its kernel cmdline.

**This is genuinely reversible, with two hard limits:**
- It is **one boot partition deep.** It returns the node to the image it ran before the last
  upgrade — nothing further back.
- It does **not** unwind cluster-level state.

**Use it at exactly one point: the canary (§4.1). That is the clean exit.** With the canary
rolled back and the other two never touched, the cluster is where it started (etcd never left
3.6 — a single 3.7 member rolled back rejoins a 3.6 majority) and the §3.7 commit can simply be
reverted (§5.3).

**Cost, which is the number the window is sized around:** one node reboot cycle
(~10 min) plus its Longhorn replica-rebuild gate (up to the 25-min budget rule) plus
re-verification ≈ **45 min**. This is why §7 insists the residual slot time is a rollback
budget and not slack.

### 5.2 — Past the canary: there is no clean revert. Stop, don't unwind.

etcd's **cluster** version is the minimum across members, so it only moves to 3.7 once
**all three** members run 3.7.1 — the hard one-way point is the THIRD node, not the second.
Before that, each upgraded member's own binary is 3.7.1 on a 3.6 cluster. The plan still treats
everything past the canary as stop-don't-unwind, deliberately: downgrading a Talos node image
does not downgrade an etcd data directory, and "revert the commit and re-roll" is an untested
downgrade on a cluster holding a ~850–890 MB database (~230–245 MB in use, 2026-09-26).

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
- **If the cluster itself is broken (etcd quorum lost and not coming back):** this is
  **disaster recovery**, not rollback — operator decision, never improvised in-window. The
  restore source is the **§3.8a snapshot** `$SCR/etcd-pre-v1.14.1.db`, via
  `docs/sops/talos-upgrade.md` §11.4 (added 2026-09-26):

  ```bash
  mise exec -- talosctl -n <ip> service etcd                      # confirm etcd down on all 3
  # wipe EPHEMERAL on each control-plane node -- on THIS cluster that also destroys every
  # Longhorn replica on the node (/var/lib/longhorn lives on EPHEMERAL, nvme0n1p6)
  mise exec -- talosctl -n <ip> reset --graceful=false --reboot --system-labels-to-wipe=EPHEMERAL
  # when `service etcd` shows Preparing on all three, bootstrap ONE node from the snapshot
  mise exec -- talosctl -n <one-ip> bootstrap --recover-from="$SCR/etcd-pre-v1.14.1.db"
  mise exec -- talosctl -n 192.168.55.11,192.168.55.12,192.168.55.13 etcd status
  ```
  Then restore Longhorn volumes from the §2.6-verified backups
  (`docs/sops/backup.md`, `docs/sops/disaster-recovery.md`). Everything created in-window is
  lost from etcd; Flux re-applies git on top. **No `--recover-skip-hash-check`** — that flag is
  for a copied data directory, not a real snapshot.

### 5.3 — Reverting the git commit

The §3.7 commit is inert on its own, so reverting it is safe and does **not** move any node:

```bash
git revert --no-commit <sha>     # restores talosVersion v1.13.10, the annotation, talhelper
                                 # 3.1.11 and the deny-rule text (3 files)
git status --short               # exactly talconfig.yaml, .mise.toml, auto-update-policy.yaml
MSG="$SCR/talos-1141-revert-msg.txt"; printf 'Revert Talos v1.14.1 node config\n\nPlan: talos-1.14.1 (section 5.3)\n' > "$MSG"
git commit --only kubernetes/bootstrap/talos/talconfig.yaml .mise.toml runbooks/auto-update-policy.yaml -F "$MSG"
git log -1 --format=%s           # confirm the subject is yours before pushing
git show --stat HEAD
git push
mise install                     # back to talhelper 3.1.11
# The local node configs are gitignored: restore them from the §3.6 scratch copies
for n in 01 02 03; do
  cp -p "$SCR/old-$n.yaml" kubernetes/bootstrap/talos/clusterconfig/kubernetes-k8s-nuc14-$n.yaml
done
grep -h 'image: factory' kubernetes/bootstrap/talos/clusterconfig/kubernetes-k8s-nuc14-0*.yaml   # 3x :v1.13.10
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

**Enforced two ways (refreshed 2026-09-26):** `exclusive: true` makes `window-scheduler.py`
refuse any other plan for `sun-attended:2026-09-27` (and refuse this plan an occupied slot),
including plans not written yet; `conflicts_with` names every existing plan that names this
one back. `talos-1.14.0` is `superseded` with `window: null`, so it no longer claims the slot.

**Reciprocity (house rule; `--validate` does not check it):** as of 2026-09-26 every plan
that names `talos-1.14.1` is named back here — `flux-oci-chart-sources`,
`helm-drift-detection`, `n8n-2.39.8`, `edot-collector-0.161.0`, `otel-operator-0.23.0`,
`authentik-2026.8.3`, `elasticsearch-obs-recovery-3.14.7`,
`falco-9.2.0`, `flux-reconciler-impersonation`, `icloud-backup-freshness-3.24.2`,
`n8n-chart-2.1.1`, `prometheus-pushgateway-3.9.0`, `wazuh-2xx-edge-coverage`. Several of those
are in the 2026-09-26 NOW run and will be retired when they execute; their refs must then be
dropped here in the same commit that retires them (a dead ref is a `--validate` ERROR).
`kube-prometheus-stack-91.4.1` was dropped (executed) — any **future** same-night
kube-prometheus-stack plan must be added, because §4 reads Prometheus.

**The day before matters as much as the day itself.** The 2026-09-26 NOW run is changing
authentik, falco, the edot/otel collectors, elasticsearch, the pushgateway and more the day
before this roll. §2.1 refuses to start while any of it is still stamped, and §2.8 records
its after-effects (e.g. a transient `AuthentikTaskWorkersZero`) as baseline rather than
blaming them on Talos. `authentik-pg17-volume-retire` executed 2026-09-26 (0591e95b):
`data-authentik-postgresql-0` is gone, so §2.5's exempt set is one name and §4.4 carries no
allowed-late alert.

**UniFi:** no switch/AP firmware in this slot — `docs/sops/unifi-device-firmware.md` now
says so explicitly (2026-09-26). §2.11 checks `upgradable=False` everywhere; §3.10 stops on
any carrier change on a survivor.

**Sequencing within the window:** this plan runs **alone**. If the operator insists on
pairing it with something, the only defensible shape is a short, fully-reversible,
storage-untouching plan running **after** §4.4 has completely passed — never before, never
interleaved between nodes.

**Things that must not run concurrently, beyond other plans:**
- **The nightly window's Step 0 safe-update apply.** `sun-attended` is a different window,
  but it fires at 03:30 the same day; verify via §2.7 that its reconciles have fully landed.
- **This window's OWN Step 0.** It runs first, every window, unattended-or-not, and the
  scheduler reserves 20 min for it. It is not optional and must not be skipped to buy time.
- **The Longhorn backup CronJob `daily-backup-all-volumes` (`0 3 * * *`, no `timeZone` =
  03:00 **UTC** = 05:00 Berlin)** and the `*-filesystem-trim` / `*-snapshot-cleanup` CronJobs
  (`0 2` / `30 2`, UTC). A 09:00-Berlin (07:00Z) window clears all of them, but do not let this plan slip earlier into their path — a backup running
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
| `gateway/envoy` | one of three pods of each of `envoy-internal`/`envoy-external`/`envoy-gateway` down per node | **every routed app** (109 HTTPRoutes on 2026-09-26) incl. the public edge — brief connection resets; **no fallback controller exists** |
| `etcd` | one member down per node; 3.6.14 → 3.7.1; snapshot taken first (§3.8a) | whole control plane; API blips |
| VIP 192.168.55.10 | fails over when its owner rolls (owner re-checked before every node, §3.8) | anything using the kubeconfig endpoint, incl. this session |
| `etcd` leadership | re-elects when the leader rolls — and spontaneously (6× in 7d, §2.3) | control plane; §3.10's triage branch |
| `igpu-i915` / NPU | device plugins re-register per node | Frigate, Jellyfin, Plex, Immich, NPU workloads |
| `security` DaemonSets | falco (modern_ebpf vs kernel 6.18.51), wazuh-agent, otel daemon restart per node | security telemetry gap per node; otel sheds its backlog via memory_limiter |
| `authentik` | server/worker/outposts reschedule | SSO logins, briefly |
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

### Re-priced duration: 160 min in-window (was 145)

| Phase | Min | Basis (re-measured 2026-09-26) |
|---|---:|---|
| **A — prep (BEFORE the window)** | **~35** | *Not counted.* Flux does not reconcile `kubernetes/bootstrap/talos/`; §3.1–§3.7 are inert until `talosctl upgrade`. +5 vs 09-20 for the §3.6 scratch snapshot + live-image check. |
| §2 pre-checks | 20 | 12 checks + writing the 5 helpers + UniFi (§2.11) + per-node baseline (§2.12); +5 vs 09-20 |
| §3.8a etcd snapshot | 3 | ~0.9 GB streamed over the LAN |
| **Canary** — upgrade + drain + reboot + §3.10 + §3.11 + §4.1 + canary go/no-go | **45** | **priced for the HEAVIEST node**: the §2.4 rule can pick node 02 (39 engines, 66 replicas on 2026-09-26). The 09-20 plan priced a 17-engine canary at 35; drain and rebuild scale with engines, +10 |
| 2nd node — upgrade + gates | 37 | 19–39 engines; possibly a VIP failover |
| 3rd node — upgrade + gates | 35 | possibly a VIP failover and/or leader re-election |
| §4.2 + §4.3 + §4.4 + §4.5 (incl. the 15-min alert settle) | 20 | overlaps the settle wait |
| **In-window total** | **160** | |

Where the +15 went: +10 because the canary can no longer be assumed light (the rule picks by
VIP/leadership, and leadership moves — it moved twice in ten minutes on 2026-09-26), +5 for
the snapshot / UniFi / per-node gates the reviewer required. The old "+5 because node 03
holds both VIP and leader" is gone: that pairing no longer holds and the order is a rule now.

### Does it still fit, with a real rollback budget? Yes on the scheduler's rule; the rollback budget is 20, and that is acceptable only because of WHEN it is needed.

```
slot wall clock                      200
  − Step 0 reserve (mandatory)        20
  − this plan                        160
  ────────────────────────────────────────
  = residual                          20    ← the late-rollback budget
```

- **Scheduler:** 160 ≤ 180 schedulable. Fits, with `exclusive: true` so nothing else can.
- **The canary rollback (~45–50 min) is fully covered:** the canary finishes around
  **T+68** (20 pre-checks + 3 snapshot + 45); ~110 minutes of slot remain at that point.
- **Past the canary the answer is stop-part-rolled (§5.2), which costs nothing.** The only
  case the 20-min residual does not cover: the LAST node fails at the very end AND the
  operator chooses to roll that one node back rather than stop. That overruns by ~25–30 min,
  attended, operator present. **Flag it at the go/no-go rather than discovering it at 12:20.**
- If the canary alone takes > 60 min, re-plan: stop after the canary, run §4.4 on the mix,
  take the other two next Sunday. Do **not** trim the estimate to make three nodes fit.

## Open items — could not be determined read-only

1. **RESOLVED.** Talos v1.14 ↔ Kubernetes support matrix: answered from upstream code
   (1.32.0 – 1.37.99; host upgrade floor 1.12.0).
2. **`talhelper genconfig` output diff for v1.14.1** was reasoned about, not executed: running
   it overwrites the gitignored local node configs, outside this agent's write boundary.
   §3.6 makes the diff an explicit gate against a scratch snapshot of the old files, verified
   against the live machineconfig first.
3. **Node-reboot duration on v1.14.1.** Extrapolated from the 2026-08-16 roll and today's
   engine counts; `sandboxd` joins the boot path. **Time the canary and re-plan from it.**
4. **Tooling gaps found in this fix pass (repo corrections, reported not worked around):**
   - `runbooks/plan-premises.py` allows no HTTP client other than `kubectl`, and scores any
     command with rc≠0 as failed — so a **404 negative control can never be a premise**, and
     `mise ls-remote` / `gh` checks cannot be either. This plan uses `kubectl get --raw` with
     `--kubeconfig=/dev/null --token=none` against public hosts (content-pinned) and keeps the
     404 control and `mise ls-remote` as in-window hard gates (§3.1, §3.5).
   - `unifictl` has no reader for the controller's `get/setting/mgmt` (`auto_upgrade`), so
     §2.11's auto-update half is a human read.
   - `runbooks/maintenance-windows.yaml` says the nightly 03:30 window starts "after the
     03:00 Longhorn backup kicks off" — the CronJob is 03:00 **UTC** (05:00 Berlin), i.e.
     *after* a 03:30-Berlin nightly window, not before it.
   - The stale schematic `b85cceac…` in `patches/global/machine-intelgpu.yaml` (§1) and the
     stale `v1.13.10` in the `aqua:siderolabs/talos` deny-rule reason (§3.3, fixed by this
     plan's own commit) are still owed.
