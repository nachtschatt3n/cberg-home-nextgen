---
plan_id: talos-linux-1.14.2
component: talos
pr: null                              # THE NODE IMAGE HAS NO RENOVATE PR. talconfig.yaml's
                                      # `talosVersion` carries `# renovate: datasource=github-releases
                                      # depName=siderolabs/talos` (repointed in cad2bd3f), but no PR is
                                      # open for it (gh pr list, 2026-10-01: none matching talos/sidero).
                                      # PR #212-style PRs are the talosctl CLI pin in .mise.toml, a
                                      # SEPARATE artifact that FOLLOWS the roll (§3.12).
kind: infra
current: "v1.14.1"                    # live on all 3 nodes, measured 2026-10-01 ~03:40Z (premise
                                      # nodes-on-v1.14.1): kernel 6.18.51-talos, containerd 2.3.5,
                                      # kubelet v1.36.0, etcd 3.7.1 / storage 3.7.0
target: "v1.14.2 + Kubernetes 1.36.5" # Talos v1.14.2: released 2026-09-29T20:44:07Z, prerelease=false;
                                      # newest stable on any line (v1.15.0-alpha.0 is a prerelease).
                                      # Kubernetes v1.36.0 -> v1.36.5 FOLDED IN 2026-10-05 (operator decision,
                                      # chat 2026-10-05): `talosctl upgrade-k8s` as Phase K, AFTER the three
                                      # node rolls converge, no reboot, behind its own go/no-go (§3.K0).
                                      # Was the standalone plan k8s-1.36.5 (now superseded, kept as the
                                      # deferral fallback, §3.K0 DEFER).
update_type: patch
risk: high                            # NOT because v1.14.2 looks dangerous (20 commits, no etcd/K8s
                                      # move, §1) but because it is a rolling reboot of all three
                                      # control-plane nodes of a 3-node hyper-converged cluster: etcd
                                      # quorum (exactly one member may be down), 94 Longhorn volumes at
                                      # replica 2, the only HTTP data plane, and a MEASURED history of
                                      # drain-driven survivor fsync stalls + elections on the last roll
                                      # (docs/sops/talos-upgrade.md §14.3, F-2cb2dbc9).
est_duration_min: 180                 # = the sun-attended SCHEDULABLE CAP (200 - 20 Step-0), NOT the full
                                      # scope. FULL SCOPE IS 210 > 180: OS roll 165 (2026-09-27 MEASURED
                                      # timings, talos-upgrade.md §14.7, F-3625b9f6) + Phase K 45 (with the
                                      # Phase A pre-pull; 49 without). Phase K is the DESIGNED OVERFLOW:
                                      # it starts only if §3.K0 is reached by T+129 (or the present
                                      # operator extends), else it is DEFERRED and the OS roll alone is
                                      # the complete, green outcome. Declared 180 (not 210) because 210
                                      # could never be placed and would strand the OS roll too; the
                                      # plan is exclusive, so the figure only decides fit. Arithmetic §7.
                                      # Phase A prep (~30 min incl. the §3.7b pre-pull) runs BEFORE the
                                      # window opens and is not counted.
needs_reboot: true                    # three sequential node reboots (Phase B). Phase K reboots
                                      # nothing: every upgrade-k8s machine-config patch is
                                      # ApplyConfigurationRequest_NO_REBOOT (talos pkg/cluster/kubernetes/patch.go)
exclusive: true                       # the node roll must have its sun-attended slot TO ITSELF,
                                      # including plans not written yet (§6)
touches:
  namespaces:
    - flux-system                     # freeze sha recorded + gated before every node (§2.0b); source NOT suspended
    - my-software-production          # 2 ImageUpdateAutomations suspended/resumed (gas-price-monitor, splitfairy);
                                      # absenty-image-updates is suspend:true IN GIT -> read, never touched (§2.0b)
    - my-software-development         # read-only today: its only IUA (absenty) is suspend:true in git; touched
                                      # only if that git hold is lifted before the window (§2.0b re-derives)
    - my-software-showcase            # 1 ImageUpdateAutomation suspended/resumed
    - kube-system                     # etcd, kube-apiserver/-controller-manager/-scheduler static
                                      # pods (rescheduled by the roll; IMAGE-BUMPED by Phase K), coredns,
                                      # cilium, authentik + 13 outposts; Phase K: 7 Talos bootstrap
                                      # objects (SSA annotation adoption) + configmap
                                      # talos-bootstrap-manifests-inventory
    - storage                         # longhorn-manager, instance-manager, CSI, 94 volumes
    - network                         # envoy-gateway, envoy-internal, envoy-external, k8s-gateway,
                                      # external-dns, adguard-home, cloudflared
    - monitoring                      # prometheus (on k8s-nuc14-02 2026-10-01), alertmanager,
                                      # grafana, node-exporter, otel collectors
    - security                        # falco (modern_ebpf meets kernel 6.18.54), wazuh-agent
    - "ALL (cluster-wide)"            # every pod is evicted and rescheduled once per node
  resources:
    - kubernetes/bootstrap/talos/talconfig.yaml   # Phase A: talosVersion v1.14.1 -> v1.14.2 (THE node image
                                                  # bump); Phase K: kubernetesVersion v1.36.0 -> v1.36.5 (§3.K2)
    - runbooks/auto-update-policy.yaml            # stale "currently v1.14.1" reason text (§3.3)
    - .mise.toml                                  # talosctl CLI pin ONLY, LAST, after §5.4 (§3.12)
    - kubernetes/bootstrap/talos/clusterconfig/   # gitignored local render: NOT touched by Phases A/B
                                                  # (talosctl upgrade does not write machine config, §1.3);
                                                  # RE-RENDERED in Phase K (§3.K3, 12 lines/node measured)
                                                  # so a later apply-config cannot downgrade K8s. Never applied.
    - "node images: kube-apiserver/-controller-manager/-scheduler:v1.36.5 (cri ns) + siderolabs/kubelet:v1.36.5 (system ns) pre-pulled on all 3 nodes in Phase A (§3.7b, ~140 MB/node)"
    - "machine config (all 3 nodes, Phase K, NO_REBOOT): apiserver/controller-manager/scheduler/kubelet/kube-proxy image fields only"
    - "clusterrolebinding/system-bootstrap-approve-node-client-csr, system-bootstrap-node-bootstrapper, system-bootstrap-node-renewal, system:talos-nodes; clusterrole/system:talos-nodes; secret/kube-system/bootstrap-token-*; configmap/kube-system/kubeconfig-in-cluster (Phase K annotation-only SSA adoption, §1.5)"
    - node/k8s-nuc14-01                           # 192.168.55.11
    - node/k8s-nuc14-02                           # 192.168.55.12 — runs prometheus-kube-prometheus-stack-0 (2026-10-01)
    - node/k8s-nuc14-03                           # 192.168.55.13 — held VIP AND etcd leadership 2026-10-01 03:40Z
    - "etcd (3 members, 3.7.1 -> 3.7.1: NO protocol move in this hop; defrag §3.8.0 + snapshot §3.8a)"
    - "all Longhorn replicas (188 = 94 volumes x numberOfReplicas 2, 2026-10-01)"
    - "imageupdateautomation (every main-pushing one NOT already suspended — 3 of 5 on 2026-10-01; the 2 absenty ones are suspend:true in git and left alone; enumerated live at §2.0b)"
  shared:
    - apiserver                       # Phase B: one apiserver down per node reboot; Phase K: all 3
                                      # kube-apiservers restart on v1.36.5, one node at a time
                                      # (VIP holder's restart blips the executor's kubectl)
    - flux                            # Phase K: Flux controllers' watches drop with each apiserver
                                      # restart; §3.K6 reads Flux health (SSA path fixed in 1.36.3)
    - etcd                            # quorum 3; exactly ONE member may be down
    - cni/cilium                      # DaemonSet restarts per node
    - coredns                         # cluster CoreDNS pods reschedule per node
    - storage/longhorn                # instance-manager restart + replica rebuild per node
    - gateway/envoy                   # the ONLY HTTP(S) data plane, public edge included
                                      # (ingress-nginx deleted 2026-09-07, ad1ea7c2)
    - authentik                       # server/worker/13 single-replica outposts reschedule
    - cert-manager                    # webhook pods reschedule
    - monitoring                      # scrape gaps per reboot; §4 reads Prometheus (its instrument)
    - igpu-i915                       # intel device plugins re-register i915 + NPU on every node
    - cifs-share                      # every smb.csi mount is torn down/remounted with its pods
    - flux-source                     # PUSH FREEZE: origin/main must equal the freeze sha before every node
    - git-main                        # no session/bot pushes to main in-window
    - talos-machineconfig             # node OS + kernel 6.18.51 -> 6.18.54 (block WBT newly ON, §1.2);
                                      # Phase K patches the live machine config (image fields, NO_REBOOT)
depends_on: []                        # RESOLVED 2026-10-05 (F-c688c50f): satisfied depends_on removed --
                                      # talconfig-multidoc-migration was executed green on 2026-10-04
                                      # (now:2026-10-04) in a7965251, retired 10bee773. Premise
                                      # multidoc-migration-applied-on-all-nodes is the live gate.
conflicts_with:                       # exclusive: true already keeps everything out of the slot;
                                      # these are the plans that ALSO mutate Talos machine config or
                                      # the same nodes and must never share a night with this roll.
  # - talconfig-multidoc-migration (RESOLVED 2026-10-05: executed green now:2026-10-04 in a7965251 + retired 10bee773; dead ref removed per the dead-ref convention, sweep 481b9c1f / F-c688c50f)
  - multus-macvlan-foundation         # reference/unwindowed; talosctl apply-config on the nodes
  - talos-sysfs-power-caps            # reciprocity (added 2026-10-05 by that plan's planner): it writes a
                                      # SysfsConfig (RAPL PL1/PL2, EPP, iGPU gt0 max) via apply-config; never
                                      # the same night. If it executed BEFORE this roll, §4.1 re-checks its
                                      # 21 keys after each reboot (the iGPU card index is boot-dependent).
  - talos-power-tuning-ab            # reciprocity (2026-10-05): live SysfsConfig A/B applies on 01/03 + final roll on all
                                      # 3 nodes; never the same night (a reboot voids a variant and re-reads the card index).
  - kube-prometheus-stack-91.9.0       # reciprocity (2026-10-05): that plan (chart 91.5.2 -> 91.9.0,
                                      # Prometheus restart) names this plan in its conflicts_with. §4
                                      # reads Prometheus (canary choice, etcd latency, alerts); a
                                      # Prometheus restart the same night blanks that evidence. Any
                                      # further kube-prometheus-stack plan must be added here too.
  # - k8s-1.36.5 (REMOVED 2026-10-05: folded into this plan as Phase K and marked superseded_by
  #   talos-linux-1.14.2; a conflict with one's own folded scope is meaningless. If Phase K is
  #   DEFERRED and k8s-1.36.5 is re-activated, re-add it here — §3.K0 DEFER.)
  # Carried forward from k8s-1.36.5's conflicts_with for the folded Phase K scope (exclusive: true
  # already keeps them out of the slot; listed so the relation survives if exclusivity is dropped):
  - longhorn-1.13.0                   # Phase K: CSI plugin re-registration under every kubelet restart
                                      # must not overlap a Longhorn manager/engine/CSI move (and §6.3:
                                      # never roll nodes with a Longhorn upgrade in flight)
  - flux-fleet-0.60.0                 # Phase K: Flux controllers restarting while apiservers roll would
                                      # confound the §3.K6 Flux gate
  - flux-reconciler-impersonation     # same Flux surface (exclusive plan; blocked 2026-10-04)
  - nextcloud-fleet-35.0.1            # reciprocity: it names k8s-1.36.5 (apiserver restarts break its
                                      # §3.4 log/exec reads + helm-controller's upgrade watch); the folded
                                      # scope inherits the relation. Its owner should retarget its line to
                                      # talos-linux-1.14.2.
capability_change: true               # v1.14.2 changes node behaviour, not just versions (§1.2):
                                      # kernel CONFIG_BLK_WBT=y + CONFIG_BLK_WBT_MQ=y turns block
                                      # writeback throttling ON by default for the NVMe that etcd,
                                      # Longhorn and images share (measured absent today: no
                                      # /sys/block/nvme0n1/queue/wbt_lat_usec on any node); Talos now
                                      # deletes kubelet CPU/memory-manager state files it judges
                                      # invalid before kubelet starts; sandboxd now starts early and
                                      # unconditionally and CRI start conditions changed. => never
                                      # unattended. Operator present. (Phase K alone would be false:
                                      # 1.36.0 -> 1.36.5 is bug-fix only, no API/feature-gate move.)
rollback_class: git-revert            # HONEST, and different from talos-1.14.1 (one-way): NOTHING
                                      # forward-only crosses this hop — etcd stays 3.7.1/storage 3.7.0,
                                      # no storage-version migration (K8s patch releases ship none).
                                      # Phase B writes no machine config. Phase K's rollback is a second
                                      # `upgrade-k8s --to 1.36.0` (path table "1.36->1.36", §5.5). The
                                      # git commit is inert (Flux does not reconcile bootstrap/talos/);
                                      # the NODE revert is a DRAINED `talosctl upgrade --image
                                      # <factory>:v1.14.1` on a Ready node (bare `talosctl rollback`
                                      # does NOT drain — hard reboot, NotReady nodes only), per
                                      # affected node, at ANY point of the roll — §5.1. Each node
                                      # revert is another reboot cycle (~25-30 min).
                                      # The §3.8a etcd snapshot is defence in depth, not the rollback.
security_ref: F-f3f2af15              # Phase K's driver: control-plane image security finding (detail
                                      # in the DB only). The Talos OS hop itself has no security driver.
finding_refs:
  - F-f3f2af15                        # kube-apiserver:v1.36.0 image finding — Phase K is the remedy
  - F-c0de81ca                        # kube-controller-manager:v1.36.0 image finding — Phase K
  - F-b2d00c28                        # kube-scheduler:v1.36.0 image finding — Phase K
                                      # (moved here from k8s-1.36.5 on the fold, 2026-10-05; if Phase K is
                                      # DEFERRED these three move BACK to the re-activated k8s-1.36.5,
                                      # §3.K0 DEFER, or they read as planned-by-a-plan-that-skipped-them)
  - F-2cb2dbc9                        # "Talos roll: node drain triggers etcd fsync stalls on survivors"
                                      # — this plan codifies pattern (ii) as gates (§3.10) and makes the
                                      # Longhorn-throttle decision explicit (§3.11; default: keep 8)
  - F-e8bb3113                        # "Node rolls blind their own instrument" — Prometheus-independent
                                      # survivor etcd probe + log capture on every node (§3.9a), and the
                                      # Prometheus node is rolled first (§2.4)
  - F-3625b9f6                        # "Talos plan pricing" — priced from the measured 2026-09-27 data (§7)
  # Queried 2026-10-01 with SWEEP_PG_DSN up: `finding list --grep talos|etcd|1.14.2|cluster nodes`.
  # NO version finding exists for v1.14.1 -> v1.14.2 (the v1.13.10 -> v1.14.1 one, F-912f4778,
  # closed with that roll). NOT claimed: F-7b842e62 (rebuild-limit monitor; decided-not-changed
  # here, §3.11, left open as the standing knob), F-3602cfa9 (unexplained 09-24 stall, owned by
  # health-check-agent, named as residual risk in §7), F-59b12b2b (owned by
  # talconfig-multidoc-migration).
review: null
status: draft
window: null                          # sun-attended is the ONLY allow_reboot window. 2026-10-05: the
                                      # flux-reconciler-impersonation placeholder on 10-11 was released;
                                      # n8n-2.39.8 now holds sun-attended:2026-10-11. The coordinator will
                                      # PROPOSE sun-attended:2026-11-01 for this plan — not assigned here;
                                      # the window agent assigns.
premises:
  # All read-only, single pipelines. Upstream reads use `kubectl get --raw` against a public
  # host with --kubeconfig=/dev/null and a dummy bearer (--token=none): kubectl is the only HTTP
  # client plan-premises.py allows, the dummy token stops kubectl's basic-auth prompt, and no
  # cluster credential is sent.
  - id: nodes-on-v1.14.1
    why: >-
      `current:` claims all three nodes run v1.14.1. A node already on v1.14.2, a node still on
      something older, or a fourth node prints a different string and fails.
    run: kubectl get nodes -o jsonpath='{.items[*].status.nodeInfo.osImage}'
    expect_exact: Talos (v1.14.1) Talos (v1.14.1) Talos (v1.14.1)
  - id: etcd-protocol-3.7
    why: >-
      v1.14.2 ships etcd 3.7.1, the same as live, so this hop must NOT move etcd. Exactly one
      server_version group, 3.7.x, count 3. A mixed cluster prints a second group and fails.
      Reads Prometheus through the apiserver service proxy.
    run: kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=count%20by%20(server_version)%20(etcd_server_version)'
    expect_matches: '^\{"status":"success","data":\{"resultType":"vector","result":\[\{"metric":\{"server_version":"3\.7\.[0-9]+"\},"value":\[[0-9.]+,"3"\]\}\]\}\}$'
  - id: factory-publishes-schematic-v1.14.2
    why: >-
      The Image Factory serves the OCI index for our schematic at v1.14.2 and its linux/amd64
      entry is the digest measured 2026-10-01. Content-pinned: an intercepting middlebox answering
      every path cannot satisfy it, and a silently re-published tag fails it. Checked negative:
      the same regex against the v1.14.1 manifest does NOT match. The v9.9.9 -> 404 control
      cannot be a premise (rc=1 with no stdout scores as a failure by design); it is the hard
      gate at §3.1.
    run: kubectl --kubeconfig=/dev/null --server=https://factory.talos.dev --token=none get --raw /v2/installer/43b3cbfc2957259b4588d362709d47387607901d4d3506c1ea46d7ea74cb99a3/manifests/v1.14.2
    expect_matches: '"mediaType":"application/vnd\.oci\.image\.index\.v1\+json".*"digest":"sha256:59537ad60b61d3b7595864a0edd8b62070a134a354ed3207ad9049d7f40e23b2","platform":\{"architecture":"amd64","os":"linux"\}'
  - id: newest-stable-talos-is-v1.14.2
    why: >-
      The factory's installable version list contains v1.14.2 and no later STABLE tag (v1.14.3+,
      or v1.15.0+ without a pre-release suffix). A newer stable release means retarget and re-seek
      the GO (§3.4). Dry-tested 2026-10-01 against the live list with injected "v1.14.3" and
      "v1.15.0" (both FAIL) and "v1.15.0-alpha.1" (correctly ignored).
    run: kubectl --kubeconfig=/dev/null --server=https://factory.talos.dev --token=none get --raw /versions
    expect_matches: '^(?!.*"v1\.14\.([3-9]|[1-9][0-9])")(?!.*"v1\.(1[5-9]|[2-9][0-9])\.[0-9]+")(?=.*"v1\.14\.2")'
  - id: multidoc-migration-applied-on-all-nodes
    why: >-
      Formerly the gate behind depends_on talconfig-multidoc-migration (§6.1). Its apply puts a
      KubeAPIServerConfig document into every node's live machine config. Printed 0 on 2026-10-01
      (before the migration); the migration EXECUTED green on 2026-10-04 (a7965251, plan retired
      10bee773) and the depends_on was removed 2026-10-05 (F-c688c50f), so this premise is now the
      live proof that the migration is still applied: expect 3. Anything else means a node lost
      the multi-document config — STOP.
    run: "talosctl --nodes=192.168.55.11,192.168.55.12,192.168.55.13 get machineconfig v1alpha1 -o yaml | grep -c 'kind: KubeAPIServerConfig'"
    expect_exact: "3"
  - id: no-pending-machineconfig-per-node
    why: >-
      Intent: NO config change is pending that would land on the reboot. On v1.14.1 every node
      carries exactly two MachineConfig resources: `v1alpha1` (config.ActiveID, the running
      config) and `persistent` (config.PersistentID, the copy saved to disk). Talos v1.14.1
      pkg/machinery/resources/config/machine_config.go documents that PersistentID is AHEAD of
      the active config after a --mode=staged apply and BEHIND it after --mode=try; the two
      specs are equal only when nothing is staged. (The 2026-10-01 measurement of a single
      v1alpha1 id predates the 2026-10-04 multidoc migration + sysfs-caps apply-configs, after
      which `persistent` reappeared; measured 2026-10-05: persistent v2 / v1alpha1 v3 on all three
      nodes, specs equal, 16459 chars.) The specs carry machine secrets, so they are compared
      INSIDE jq and never printed or stored; the output is only node, sorted id list, and
      spec-equality. plan-premises.py allows no hashing tool, and in-memory equality is
      stricter than a hash compare anyway. FAILS on: specs differing (true -> false), any extra id
      (e.g. a third resource), a missing `persistent`, or an unreachable node (pipefail).
      Negative control 2026-10-05: appending a byte to node .12's persistent spec in-stream
      printed false for .12; injecting a third id on .13 printed its 3-id list and false.
      STOP on failure and find out what staged it.
    run: talosctl --nodes=192.168.55.11,192.168.55.12,192.168.55.13 get machineconfig -o json | jq -sc 'group_by(.node)[]' | jq -c 'sort_by(.metadata.id)' | jq -c '[.[0].node, map(.metadata.id), unique_by(.spec)[1] == null]'
    expect_matches: '^\["192\.168\.55\.11",\["persistent","v1alpha1"\],true\]\s+\["192\.168\.55\.12",\["persistent","v1alpha1"\],true\]\s+\["192\.168\.55\.13",\["persistent","v1alpha1"\],true\]$'
  - id: longhorn-all-volumes-replica-2
    why: >-
      A RULE, not a count: every Longhorn volume has numberOfReplicas 2 (94 volumes on
      2026-10-01). §2.5 measures the live set and §3.11 gates against that recording. Any volume
      at 1 or 3 changes the one-node-down arithmetic; an empty list fails.
    run: kubectl get volumes.longhorn.io -n storage -o jsonpath='{.items[*].spec.numberOfReplicas}'
    expect_matches: '^2( 2)*$'
  - id: no-volume-with-stale-replica-timeout-0
    why: >-
      F-b91ef6e5 (resolved 4af5b6bc) set staleReplicaTimeout 20/30 on every volume so failed
      replicas after a drain are garbage-collected; on 2026-09-27 two volumes at 0 blocked the
      replica-total gate. Measured 2026-10-01: 32 volumes at 20, 62 at 30, none at 0. A 0 creeping
      back means §3.11 will need the manual cleanup of talos-upgrade.md §14.4 — re-price.
    run: kubectl get volumes.longhorn.io -n storage -o jsonpath='{.items[*].spec.staleReplicaTimeout}'
    expect_matches: '^(20|30)( (20|30))*$'
  - id: backup-cronjob-exists
    why: >-
      §2.6 names storage/daily-backup-all-volumes (NOT the stale backup-of-all-volumes). Schedule
      is UTC (no timeZone set). Missing object fails.
    run: kubectl get cronjob -n storage daily-backup-all-volumes -o jsonpath='{.metadata.name} {.spec.schedule} tz=[{.spec.timeZone}]'
    expect_exact: daily-backup-all-volumes 0 3 * * * tz=[]
  - id: pgadmin-selector
    why: >-
      §4.3 CONTENTS ASSERTION 1 writes through deploy/pgadmin (PVC pgadmin-data at
      /var/lib/pgadmin, measured 2026-10-01) and selects its pod with app=pgadmin.
    run: kubectl get deploy -n databases pgadmin -o jsonpath='{.spec.selector.matchLabels}'
    expect_exact: '{"app":"pgadmin"}'
  - id: etcd-latency-histograms-scraped
    why: >-
      §2.3b and §3.10b gate on the worst 5m-p99 of etcd WAL fsync and backend commit. An
      unscraped histogram reads EMPTY and a "< 50 ms" check would pass on no data. Expects 3 fsync
      + 3 commit series (6); a lost etcd target prints 4 or 5.
    run: kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=count(etcd_disk_wal_fsync_duration_seconds_count)%20%2B%20count(etcd_disk_backend_commit_duration_seconds_count)'
    expect_matches: '"value":\[[0-9.]+,"6"\]'
  - id: kustomize-controller-write-metric-scraped
    why: >-
      The < 5 MB/s kustomize-controller gate reads cAdvisor container_fs_writes_bytes_total for
      container=manager. The filter must select exactly one series; 0 (not scraped) or 2
      (double count) fails here.
    run: kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=count(container_fs_writes_bytes_total%7Bnamespace%3D%22flux-system%22%2Ccontainer%3D%22manager%22%2Cpod%3D~%22kustomize-controller-.*%22%7D)'
    expect_matches: '"value":\[[0-9.]+,"1"\]'
  # Phase K (Kubernetes 1.36.5) premises, carried from k8s-1.36.5 (all read-only; passed
  #     2026-10-05 under `plan-premises.py k8s-1.36.5`). They describe the PRE-WINDOW state; Phase
  #     K re-measures after the roll at §3.K1/§3.K4. talos-uniform-1.14 is subsumed by
  #     nodes-on-v1.14.1 above.
  - id: kubelets-on-1.36.0
    why: "Phase K's `current` is kubelet v1.36.0 x3. Anything else means a partial earlier upgrade-k8s run (re-run resumes; read §5.5 first) or someone already upgraded."
    run: kubectl get nodes -o jsonpath='{.items[*].status.nodeInfo.kubeletVersion}'
    expect_exact: "v1.36.0 v1.36.0 v1.36.0"
  - id: talconfig-pins-1.36.0
    why: "§3.K2's anchored sed rewrites exactly this line (dry-tested 2026-10-05 on a scratch copy already carrying talosVersion v1.14.2). A different value means the sed is a no-op and upgrade-k8s would read the wrong --to."
    run: "grep -c '^kubernetesVersion: v1.36.0$' kubernetes/bootstrap/talos/talconfig.yaml"
    expect_exact: "1"
  - id: apiserver-configs-on-1.36.0
    why: "Talos' own APIServerConfig resources (what upgrade-k8s patches) carry v1.36.0 on all nodes: 6 image lines across 3 nodes, measured 2026-10-05. §3.K6 expects 6 at v1.36.5."
    run: "talosctl --nodes=192.168.55.11,192.168.55.12,192.168.55.13 get apiserverconfigs -o yaml | grep -c 'image: registry.k8s.io/kube-apiserver:v1.36.0'"
    expect_exact: "6"
  - id: build-info-scraped-12
    why: "§3.K6's CONTENTS ASSERTION reads kubernetes_build_info: 12 series (apiserver, kubelet, kube-scheduler, kube-controller-manager x3). Fewer means a scrape job went blind and the post-check could pass on an empty set."
    run: kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=count(kubernetes_build_info%7Bgit_version%3D%22v1.36.0%22%7D)'
    expect_matches: '"value":\[[0-9.]+,"12"\]'
  - id: bootstrap-inventory-7
    why: "upgrade-k8s prunes against this SSA inventory. The 2026-10-05 dry-run diff showed 7 objects, all `configured` (annotation adoption), zero deletes, against an inventory of 7 entries. A different entry count means the prune set changed: §3.K4's dry-run must be read action by action."
    run: kubectl get configmap -n kube-system talos-bootstrap-manifests-inventory -o jsonpath='{.data}'
    expect_matches: '^\{(?:"[^"]+":"[^"]*",?){7}\}$'
  - id: longhorn-rebuild-limit-8
    why: >-
      §3.11 and §7 price the roll at concurrent-replica-rebuild-per-node-limit 8 (measured ~20 min
      rebuild per node on 2026-09-27). If someone lowers it before the window, the per-node time
      roughly multiplies — re-price rather than run.
    run: kubectl get settings.longhorn.io -n storage concurrent-replica-rebuild-per-node-limit -o jsonpath='{.value}'
    expect_exact: "8"
sops_refs:
  - docs/sops/talos-upgrade.md
  - docs/sops/etcd.md
  - docs/sops/application-update.md
  - docs/sops/longhorn.md
  - docs/sops/storage-safety.md
  - docs/sops/backup.md
  - docs/sops/disaster-recovery.md
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/monitoring.md
  - docs/sops/unifi-device-firmware.md
generated: "2026-10-01"
---

# Talos Linux node roll — v1.14.1 → v1.14.2, then Kubernetes v1.36.0 → v1.36.5

> **2026-10-05 — Kubernetes 1.36.5 FOLDED IN (operator decision, relayed by the coordinator).**
> The standalone plan `k8s-1.36.5` is `superseded_by: talos-linux-1.14.2`; its live-verified
> `upgrade-k8s` procedure is **Phase K** here (§1.5, §3.K0–§3.K7, §5.5), run in the same Sunday
> window **after** all three node rolls have converged and §4.4 is green, with no reboot, behind
> its own go/no-go (§3.K0). The OS roll alone remains a complete, green outcome: Phase K is the
> designed overflow and is DEFERRED rather than squeezed (§7 — full scope 210 min vs 180
> schedulable). Phase A gains one Flux-inert prep step: pre-pulling the four 1.36.5 images
> (§3.7b). **Expected outcome on price: Phase K DEFERRED unless the operator pre-approves the
> ~30-min extension at the GO** (§7) — the GO should state that answer.

> **Built on the executed `talos-1.14.1` plan** (retired in `40ca20d6`; full text:
> `git show 40ca20d6^:runbooks/maintenance/plans/talos-1.14.1.md`) and on the lessons it
> wrote into `docs/sops/talos-upgrade.md` §14–§15 (option B roll without `genconfig`, etcd disk
> gates, push freeze, pattern (ii), failed-replica cleanup, the Prometheus blind spot, hwmon
> renumbering, measured timings). The gate helpers are re-used with three changes, each
> dry-run on 2026-10-01: `nodegate.py` also checks node-exporter; a new `probe.py` gives a
> Prometheus-independent survivor etcd record (F-e8bb3113); `hwmon.py` diffs the hwmon chip set
> across the kernel bump (§14.6). Every drifting baseline is **re-measured at §2 by rule** and
> recorded to a file; numbers in this plan are dated examples, never thresholds.

## 1) Summary & why held

Roll all three control-plane/worker nodes (`k8s-nuc14-01/02/03`, 192.168.55.11–.13, VLAN 55)
from Talos **v1.14.1** to **v1.14.2**, one node at a time, with the Longhorn and etcd gates
between nodes. During the roll Kubernetes stays **v1.36.0** (Talos 1.14.2's *default* moves to
1.37.1; ours is pinned in `talconfig.yaml`, and Phase B does not touch it). etcd stays **3.7.1**
throughout. **Then, Phase K:** once the roll has converged and §4.4 is green, upgrade the control
plane (kube-apiserver / -controller-manager / -scheduler static pods) and the kubelet on all three
nodes from **v1.36.0 to v1.36.5** with `task talos:upgrade-k8s` (§1.5). No reboot.

**Why held:** it reboots every node in the cluster. That is a sun-attended,
operator-present, reboot-capable job by definition; nothing about the content makes it "safe".
Attribution (talos-1.14.1 §1, F-9a58f400): the node image (`talosVersion`) has no PR; the
talosctl CLI pin in `.mise.toml` is a separate artifact that moves **last** (§3.12).

### 1.1 Upstream evidence — what v1.14.2 is

`gh api repos/siderolabs/talos/releases` (2026-10-01): **v1.14.2 published 2026-09-29T20:44Z,
prerelease=false**, newest stable on any line. 20 talos commits + 12 pkgs commits over v1.14.1.

Release body, verbatim where load-bearing:

> **Kubelet Resource Manager State.** *"Talos now validates the kubelet CPU manager and memory
> manager state files (`/var/lib/kubelet/cpu_manager_state`, `/var/lib/kubelet/memory_manager_state`)
> the same way kubelet does on startup, and removes a state file kubelet would refuse to load
> before starting kubelet."*
>
> **Component Updates.** *"Linux: 6.18.54, containerd: 2.3.6, runc: 1.5.2, Kubernetes: 1.37.1."*
> Images list: `registry.k8s.io/etcd:3.7.1`, `coredns:v1.14.7` — both unchanged from v1.14.1.

Compatibility, from upstream code (`pkg/machinery/compatibility/talos114/talos114.go` @ `v1.14.2`):
`MinimumHostUpgradeVersion 1.12.0`, `MaximumHostDowngradeVersion 1.16.0`,
`MinimumKubernetesVersion 1.32.0`, `MaximumKubernetesVersion 1.37.99` — identical to v1.14.1.
So v1.14.1 → v1.14.2 is supported, **v1.14.2 → v1.14.1 (rollback) is inside the downgrade
window**, and K8s v1.36.0 stays supported.

### 1.2 What actually changes on OUR nodes (read per commit, not per headline)

| Upstream change | Applies here? | Evidence / why |
|---|---|---|
| **pkgs `cc717ed` `feat: enable CONFIG_BLK_WBT`** — the patch sets `CONFIG_BLK_WBT=y` **and `CONFIG_BLK_WBT_MQ=y`** (default-on for blk-mq devices). Motivated by talos#14461, *"periodic trim disrupts cluster workloads … bad enough to cause etcd leader elections … CONFIG_BLK_WBT is not configured in the Talos kernel, and that's supposed to help prevent discards from impacting other workloads."* | **YES — the one real behaviour change.** | Measured 2026-10-01 on all three nodes: `/sys/block/nvme0n1/queue/wbt_lat_usec` → **NotFound** (WBT not built), scheduler `[none]`, `write_cache` = `write back`. After the roll the kernel throttles buffered writeback on the NVMe that etcd, Longhorn replicas and container images share (consumer 980/990 PRO, no PLP — talos-1.14.1 Appendix A). Expected effect neutral-to-positive for etcd fsync tail latency (that is upstream's intent), but it is a change on **exactly** the disk path behind F-84a27c15 / F-2cb2dbc9, so it is MEASURED, not assumed: §4.3 CONTENTS ASSERTION 4 proves WBT is live, §4.4 #9 + the §3.10b gates hold the etcd p99 floor, §4.6 records a before/after p99 comparison. |
| `a015f81` kubelet CPU/memory-manager state validation (the headline feature) | Inert in practice | Live state files on 2026-10-01: `{"policyName":"none",…}` and `{"policyName":"None","machineState":{}…}` — default policies; `machine-kubelet.yaml` sets only reservations/GC/maxPods, no `cpuManagerPolicy`/`reservedSystemCPUs`/`reservedMemory`. A valid default-policy state file is kept. |
| `c792fa4` stricter validation of hostnames / search domains | Inert; **gated** | Code (`pkg/machinery/nethelpers/dnsname.go` @ v1.14.2): rejects only whitespace/control bytes; for machine config it is a **WARNING, not an error** (*"to keep accepting machine configuration which was valid before"*). Our hostnames `k8s-nuc14-0N`; `disableSearchDomain: true`. Measured: `talosctl 1.14.2 validate` on all three LIVE configs prints the same single warning as 1.14.1 (§3.6). /etc/hosts rendering moved to `etcrender.Hosts`, which drops the hostname line for an invalid name — §4.3 CONTENTS ASSERTION 5 checks the line is still written. |
| `c7e2524` CRI ↔ sandboxd start conditions (`sandboxd` now starts early and unconditionally; CRI starts once the legacy v1alpha1 config is available) | Boot-path change | Fixes talos#14374. Workload isolation stays OFF (no `SecurityProfileConfig`, §4.5). A boot-order regression shows as kubelet/CRI not coming up → caught by §3.10 (node Ready) on the canary; a node whose kubelet never came up has nothing to drain, so §5.1b's bare `talosctl rollback` (hard reboot) applies. |
| `3137edf` routes without `outLinkName` no longer loop | Inert/benign | Our only route is the per-interface default route in `talconfig.yaml` `networkInterfaces[].routes`, which v1alpha1 binds to its link. |
| `f53a000` block: drop devices gone from the last generation | Inert | Matters for re-created `/dev/dm-*`; no LVM/dm here. |
| containerd 2.3.5 → 2.3.6, runc → 1.5.2, kernel 6.18.51 → 6.18.54 | Yes (versions) | Kernel bump ⇒ hwmon renumbering risk (talos-upgrade.md §14.6) → §2.8/§4.4 diff the chip set; falco `modern_ebpf` meets the new kernel → §3.10 DaemonSet gate. |
| macsec module, swtpm, Apple-hardware boot patch, Akamai/Linode, Docker-hostname, LVM retry, WireGuard PSK redaction, arm64 crypto config | Not applicable | No macsec/TPM emulation/LVM/WireGuard/cloud platform; NUC14 x86_64 bare metal. |

**Opt-in features remain opt-in and this plan does NOT opt in** (unchanged from talos-1.14.1
§1 items 9–12): workload isolation, `FilesystemTrimConfig`, dedicated etcd volume. Note the
interaction: WBT is what upstream added *for* trim-induced etcd latency; it makes C3 (periodic
fstrim) a less risky future decision, but that decision is not this plan's.

### 1.3 Tooling — the roll does not need `genconfig`, before or after the migration

`task talos:upgrade-node` runs `talhelper gencommand upgrade`, which only prints
`talosctl upgrade --image …`, and Talos's `Upgrade()` handler takes the image from the request
and **does not write the machine config** (talos-upgrade.md §14.2). **Dry-run 2026-10-01** with
talhelper **3.1.11** against a scratch `talconfig.yaml` at `v1.14.2`:

```
talosctl upgrade --talosconfig=<path> --nodes=192.168.55.12 --image=factory.talos.dev/installer/43b3cbfc2957259b4588d362709d47387607901d4d3506c1ea46d7ea74cb99a3:v1.14.2 --image='factory.talos.dev/installer/43b3cbfc2957259b4588d362709d47387607901d4d3506c1ea46d7ea74cb99a3:v1.14.2' --timeout=10m;
```

`talconfig-multidoc-migration` (executed 2026-10-04, a7965251; formerly this plan's depends_on,
§6.1) bumped talhelper to 3.1.17 and
made `task talos:generate-config` work again; neither matters to the roll. **Phases A and B do
not regenerate `clusterconfig/` and nothing in this plan ever `apply-config`s.** (Phase K
re-renders the gitignored `clusterconfig/` locally at §3.K3, after all three nodes run v1.14.2,
so the render's installer tag and K8s images are both truthful; it applies nothing — upgrade-k8s
patches the image fields itself.) After it, each node's
`machine.install.image` still names the tag its last applied config carried (`:v1.13.10` today,
`:v1.14.1` after the migration) — the running version is asserted by `kubectl get nodes`
OS-IMAGE, never by that field.

### 1.4 Schematic — unchanged, verified live

All three nodes run `factory.talos.dev/installer/43b3cbfc…99a3` (live machineconfig, 2026-10-01).
Factory, 2026-10-01: `v1.14.2 → 200`, `v1.14.1 → 200`, `v9.9.9 → 404` (control). The stale
`b85cceac…` comment in `patches/global/machine-intelgpu.yaml` reported by talos-1.14.1 §1 is
still owed (repo correction, not this plan's file).

### 1.5 Phase K — Kubernetes v1.36.0 → v1.36.5 (folded from `k8s-1.36.5`, 2026-10-05)

**What `upgrade-k8s` does here** (upstream code, `siderolabs/talos` `pkg/cluster/kubernetes/
talos_managed.go`, `kubelet.go`, `patch.go`, read at v1.14.1 and — `prePullImages` — re-read at
v1.14.2 for this fold):
1. **Compatibility check** against the Talos version, then `upgrade.NewChecks`. The path table
   (`siderolabs/go-kubernetes` v0.2.41 `kubernetes/upgrade/path.go`) keys on major.minor and
   lists `"1.36->1.36"`: v1.36.0→v1.36.5 and the rollback v1.36.5→v1.36.0 are both accepted.
   `talos114.go` (§1.1): K8s 1.32.0–1.37.99 is supported on v1.14.1 **and** v1.14.2, so a later
   per-node Talos rollback (§5.1) under K8s 1.36.5 is also supported (the 2026-10-05 dry-run
   printed `Talos version 1.14.1 is compatible with Kubernetes version 1.36.5` ×3).
2. **Image pre-pull** (`--pre-pull-images`, default true): `ImagePull` of apiserver,
   controller-manager and scheduler `:v1.36.5` into the **`cri`** namespace of each control-plane
   node, then `ghcr.io/siderolabs/kubelet:v1.36.5` (our kubelet image has no suffix) into the
   **`system`** namespace of every node. **Not gated on `--dry-run`** (no DryRun check in
   `prePullImages`), hence `--pre-pull-images=false` on every dry-run here. `talosctl image pull
   --namespace cri|system` calls the same `ImagePull` API, which is what makes the §3.7b Phase A
   pre-pull an exact, earlier copy of this step and nothing more.
3. **Static pods**, apiserver → controller-manager → scheduler, one node at a time: patch the
   image in the node's machine config with `ApplyConfigurationRequest_NO_REBOOT` (multi-doc
   aware — patches our v1.14 `KubeAPIServerConfig` documents), wait for the new static pod Ready.
4. **kube-proxy**: only the `KubeProxyConfig` image field changes (ours is `enabled: false`,
   `daemonset/kube-proxy` NotFound — measured).
5. **Kubelet**, one node at a time (NO_REBOOT): wait for kubelet down → healthy → Node reports
   the new version and Ready.
6. **Bootstrap-manifest sync** (SSA with an inventory, then prune). The 2026-10-05 dry-run (on
   v1.14.1 nodes) showed **7 actions, all `configured`, 0 `created`, 0 `deleted`** — each only adds
   `config.k8s.io/owning-inventory: talos-bootstrap-manifests-inventory` to an existing object
   (4 ClusterRoleBindings, 1 ClusterRole, `secret/kube-system/bootstrap-token-*`,
   `configmap/kube-system/kubeconfig-in-cluster`); the inventory lists exactly those 7. **The
   manifests are rendered by the nodes' Talos machinery**, so this must be re-dry-run after the
   roll, on v1.14.2 nodes (§3.K4) — the v1.14.1 reading is not transferable.

**Upstream evidence** (`kubernetes/kubernetes` `CHANGELOG/CHANGELOG-1.36.md`, "since v1.36.0"
through "since v1.36.4"): none of the five patch releases has an *Urgent Upgrade Notes*, *API
Change* or *Deprecation* section; no API added or removed. Load-bearing here: 1.36.3 *"Fixed a
kubelet memory leak regression in 1.36 caused by leaked contexts on every Pod sync"* (every node
has run a 1.36.0 kubelet since 2026-04-30) and *"Fixes a 1.36 regression in server side apply
where patching a container type (list or map) could result in `422 required` errors"* (Flux
applies everything with SSA); 1.36.4 *"Update golang.org/x/text and golang.org/x/net
dependencies to include security updates"* plus the Go toolchain bumps — the content behind
`security_ref` (detail in the DB only). Upstream docs: *"Kubelet upgrades may cause workloads to
restart"* — §3.K6 CA-K3 measures whether any did.

**Why it was held:** the `siderolabs/*` deny rule in `auto-update-policy.yaml`. Its reason
("needs a rolling node-reboot maintenance window") is wrong for the kubelet dep — upgrade-k8s
reboots nothing — reported as a repo correction (Open items #7), not planned around. The hold
itself is right: every apiserver and kubelet restarts, and the action is an imperative `talosctl`
call Flux cannot revert.

**Why after the roll, not before:** operator decision 2026-10-05. Either order is supported by
upstream (§1.1 compatibility); after-the-roll means Phase B's gates and PASS lines (§2.2, §4.4
#1: kubelet `v1.36.0`) stay exactly as reviewed, and Phase K's dry-run sees the final Talos
machinery.

## 2) Pre-checks

Run **inside the window, after this window's Step 0 has landed, before touching a node**.
Every baseline is RE-MEASURED and recorded to `$SCR`; later gates compare against those files.

```bash
cd /Users/mu/code/cberg-home-nextgen
export KUBECONFIG="$PWD/kubeconfig"
export TALOSCONFIG="$PWD/kubernetes/bootstrap/talos/clusterconfig/talosconfig"
# Local-only scratch: baselines, live configs (§3.6), the etcd snapshot (§3.8a), probe logs.
# NOT the repo, NOT another session's /tmp, NOT an iCloud/Nextcloud-synced path.
SCR="$HOME/.cache/talos-1142"; mkdir -p "$SCR"; chmod 700 "$SCR"
stat -f '%Lp %N' "$SCR"                     # MUST print 700
P='/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1'
.venv/bin/python3 runbooks/plan-premises.py talos-linux-1.14.2 --require-premises
```
**PASS:** every premise passes (incl. `multidoc-migration-applied-on-all-nodes` = 3). Any
failure = NO-GO for today; do not "fix" a premise in-window.

**2.0 — Write the gate helpers into `$SCR`.** Six are the talos-1.14.1 helpers (dry-run with
negative controls 2026-09-26, used in the 2026-09-27 roll); `nodegate.py` gained the
node-exporter DaemonSet; `probe.py` and `hwmon.py` are new (dry-run 2026-10-01, controls in
§2.0 notes). All read Prometheus through the apiserver service proxy (`kubectl get --raw`), so
no port-forward can die mid-window. Phase A may write them the evening before.

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
    if dl > (1 if was_leader else 0): fail.append(f"{ip} saw {dl:.0f} leader change(s); allowed {1 if was_leader else 0} -> pattern (ii) triage (§3.10)")
n = json.loads(subprocess.check_output(["kubectl", "get", "node", rolled, "-o", "json"]))["status"]["allocatable"]
for res, want in (("gpu.intel.com/i915", "5"), ("npu.intel.com/accel", "1")):
    print(f"  {rolled} {res}={n.get(res)}")
    if n.get(res) != want: fail.append(f"{rolled} allocatable {res}={n.get(res)} (want {want}) -> device plugin not re-registered")
for ns, ds in (("security", "falco"), ("security", "falco-log-rotate"), ("security", "wazuh-agent"),
               ("monitoring", "otel-operator-daemon-collector"), ("monitoring", "kube-prometheus-stack-prometheus-node-exporter")):
    s = json.loads(subprocess.check_output(["kubectl", "get", "ds", "-n", ns, ds, "-o", "json"]))["status"]
    print(f"  ds {ns}/{ds} ready {s.get('numberReady')}/{s.get('desiredNumberScheduled')}")
    if not (s.get("numberReady") == s.get("desiredNumberScheduled") == 3): fail.append(f"ds {ns}/{ds} not 3/3")
for f in fail: print("  FAIL:", f)
print("VERDICT", "FAIL" if fail else "PASS")
PY
cat > "$SCR/etcdgate.py" <<'PY'
import json, subprocess, sys, time, argparse, urllib.parse
# Prometheus-side etcd/disk gate. Every threshold is a flag so a negative control can run it.
ap = argparse.ArgumentParser()
ap.add_argument("--lookback", default="1h")        # fsync/commit worst-5m-p99 window
ap.add_argument("--leader-window", default="2h")   # leader-change window
ap.add_argument("--allow-file", default="")        # explained leader changes: "<epoch> <reason>" per line
ap.add_argument("--fsync-ms", type=float, default=50)
ap.add_argument("--commit-ms", type=float, default=50)
ap.add_argument("--kc-mbps", type=float, default=5)
ap.add_argument("--kc-window", default="10m")
ap.add_argument("--members", type=int, default=3)   # 0 = skip the count checks (ONLY the §3.11 node-down tripwire)
a = ap.parse_args()
Q = "/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query="
def q(expr):
    d = json.loads(subprocess.check_output(["kubectl", "get", "--raw", Q + urllib.parse.quote(expr)]))
    if d.get("status") != "success": sys.exit(f"FAIL: query error {d}")
    return {x["metric"].get("instance", "*").split(":")[0]: float(x["value"][1]) for x in d["data"]["result"]}
def secs(w):
    return int(w[:-1]) * {"m": 60, "h": 3600, "d": 86400}[w[-1]]
fail = []
for name, metric, lim in (("wal_fsync", "etcd_disk_wal_fsync_duration_seconds_bucket", a.fsync_ms),
                          ("backend_commit", "etcd_disk_backend_commit_duration_seconds_bucket", a.commit_ms)):
    r = q(f"max_over_time(histogram_quantile(0.99, sum by (instance,le) (rate({metric}[5m])))[{a.lookback}:1m])")
    print(f"{name} worst 5m-p99 over {a.lookback}: " + " ".join(f"{k}={v*1000:.1f}ms" for k, v in sorted(r.items())))
    if a.members and len(r) != a.members: fail.append(f"{name}: expected {a.members} members, got {sorted(r)} (scrape gap -> wait, retry)")
    if not r: continue
    worst = max(r.values()) * 1000
    if worst >= lim: fail.append(f"{name} worst p99 {worst:.1f}ms >= {lim}ms")
now = time.time(); lw = secs(a.leader_window)
start = q('process_start_time_seconds{job="kube-etcd"}')
chg = q(f"etcd_server_leader_changes_seen_total - etcd_server_leader_changes_seen_total offset {a.leader_window}")
counted = {ip: v for ip, v in chg.items() if start.get(ip, now) < now - lw}
print(f"leader changes over {a.leader_window} (members up the whole window): {counted}; skipped (restarted inside it): {sorted(set(start) - set(counted))}")
allowed = 0
if a.allow_file:
    try:
        allowed = sum(1 for l in open(a.allow_file) if l.strip() and float(l.split()[0]) >= now - lw)
    except FileNotFoundError:
        pass
if a.members and len(start) != a.members: fail.append(f"expected {a.members} etcd process_start series, got {sorted(start)}")
if not counted: fail.append("no member was up for the whole leader window -> cannot measure, FAIL closed")
elif max(counted.values()) > allowed:
    fail.append(f"{max(counted.values()):.0f} leader change(s) in {a.leader_window}, explained/allowed {allowed}")
kc = q(f'sum(rate(container_fs_writes_bytes_total{{namespace="flux-system",container="manager",pod=~"kustomize-controller-.*"}}[{a.kc_window}]))')
if not kc: fail.append("kustomize-controller write metric returned NO series -> not scraped, FAIL closed")
else:
    mb = list(kc.values())[0] / 1e6
    print(f"kustomize-controller writes over {a.kc_window}: {mb:.2f} MB/s")
    if mb >= a.kc_mbps: fail.append(f"kustomize-controller {mb:.2f} MB/s >= {a.kc_mbps} MB/s (commit burst / cold start in progress)")
for f in fail: print("  FAIL:", f)
print("VERDICT", "FAIL" if fail else "PASS")
sys.exit(1 if fail else 0)
PY
cat > "$SCR/etcdstat.py" <<'PY'
import subprocess, sys
# converged                -> 3 members, 1 leader, no learner, no errors, RAFT INDEX spread <= 50
# defragged <ip> [<ip>..]  -> additionally: IN USE >= 80% of DB SIZE on each named member
U = {"B": 1e-6, "kB": 1e-3, "KB": 1e-3, "MB": 1, "GB": 1e3}
out = subprocess.check_output(["talosctl", "-n", "192.168.55.11,192.168.55.12,192.168.55.13", "etcd", "status"], text=True)
rows = [l.split() for l in out.splitlines()[1:] if l.strip()]
m, fail = {}, []
for t in rows:
    ip = t[0]
    m[ip] = dict(member=t[1], db=float(t[2]) * U[t[3]], use=float(t[4]) * U[t[5]], leader=t[7],
                 raft=int(t[8]), applied=int(t[10]), learner=t[11], proto=t[12], err=" ".join(t[14:]))
    print(f"{ip} db={m[ip]['db']:.0f}MB in_use={m[ip]['use']:.0f}MB ({100*m[ip]['use']/m[ip]['db']:.0f}%) raft={m[ip]['raft']} applied={m[ip]['applied']} learner={m[ip]['learner']} proto={m[ip]['proto']} err=[{m[ip]['err']}]")
if len(m) != 3: fail.append(f"expected 3 members, got {len(m)}")
if len({v['leader'] for v in m.values()}) != 1: fail.append("members disagree on the leader")
if any(v["learner"] != "false" for v in m.values()): fail.append("a LEARNER is present")
if any(v["err"] for v in m.values()): fail.append("ERRORS column not empty")
spread = max(v["raft"] for v in m.values()) - min(v["raft"] for v in m.values()) if m else -1
lag = max(v["raft"] - v["applied"] for v in m.values()) if m else -1
print(f"raft index spread {spread}, max raft-applied lag {lag}")
if spread > 50 or lag > 50: fail.append(f"not converged: spread {spread} / apply lag {lag} (> 50)")
if len(sys.argv) > 1 and sys.argv[1] == "defragged":
    for ip in sys.argv[2:]:
        r = m.get(ip)
        if not r or r["use"] / r["db"] < 0.8: fail.append(f"{ip} not defragged: in-use {r and round(100*r['use']/r['db'])}% of DB SIZE (< 80%)")
for f in fail: print("  FAIL:", f)
print("VERDICT", "FAIL" if fail else "PASS")
sys.exit(1 if fail else 0)
PY
cat > "$SCR/probe.py" <<'PY'
import sys
# probe.py <probe-log> <survivor-ip> <survivor-ip> [--allow-elections N]
# Each log line: "<epoch> <talosctl etcd status output with newlines replaced by '|'>".
# Prometheus-independent pattern-(ii) evidence (F-e8bb3113): elections = RAFT TERM increases
# seen by the survivors; leaderless = a sample in which a survivor row is missing, carries
# ERRORS, or the survivors disagree on the leader. Two consecutive bad samples (>= ~10 s) = FAIL.
args = sys.argv[1:]
allow = 0
if "--allow-elections" in args:
    i = args.index("--allow-elections"); allow = int(args[i + 1]); del args[i:i + 2]
path, surv = args[0], set(args[1:3])
samples, bad_run, worst_run, terms, nbad = 0, 0, 0, [], 0
for line in open(path):
    line = line.strip()
    if not line: continue
    ts, _, rest = line.partition(" ")
    rows = {}
    for r in rest.split("|"):
        t = r.split()
        if len(t) >= 14 and t[0] in surv:
            rows[t[0]] = dict(leader=t[7], term=int(t[9]), err=" ".join(t[14:]))
    samples += 1
    ok = (set(rows) == surv and len({v["leader"] for v in rows.values()}) == 1
          and not any(v["err"] for v in rows.values()))
    if ok:
        terms.append(max(v["term"] for v in rows.values())); bad_run = 0
    else:
        nbad += 1; bad_run += 1; worst_run = max(worst_run, bad_run)
elections = sum(1 for a, b in zip(terms, terms[1:]) if b > a)
print(f"samples {samples}  bad {nbad}  worst consecutive bad {worst_run}  term {terms[:1]}->{terms[-1:]}  elections {elections} (allowed {allow})")
fail = []
if samples < 6: fail.append("fewer than 6 samples -> the probe did not run long enough to cover the drain, FAIL closed")
if worst_run >= 2: fail.append(f"{worst_run} consecutive samples without a common healthy leader on the survivors -> possible leaderless period")
if elections > allow: fail.append(f"{elections} election(s) seen by the survivors, allowed {allow}")
for f in fail: print("  FAIL:", f)
print("VERDICT", "FAIL" if fail else "PASS")
sys.exit(1 if fail else 0)
PY
cat > "$SCR/hwmon.py" <<'PY'
import json, subprocess, sys
# baseline <file> | compare <file> — the hwmon chip set (talos-upgrade.md §14.6: 6.18.51 renamed
# thermal_thermal_zone0 -> thermal_thermal_zone1 and broke a pinned Uptime Kuma monitor)
mode, path = sys.argv[1], sys.argv[2]
Q = "/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=count%20by%20(chip)%20(node_hwmon_temp_celsius)"
r = json.loads(subprocess.check_output(["kubectl", "get", "--raw", Q]))["data"]["result"]
s = {x["metric"]["chip"]: x["value"][1] for x in r}
print("chips", sorted(s.items()))
if not s: sys.exit("FAIL: no node_hwmon_temp_celsius series -> node-exporter not scraped, FAIL closed")
if mode == "baseline":
    json.dump(s, open(path, "w")); print("recorded ->", path); sys.exit(0)
b = json.load(open(path))
gone = sorted(set(b) - set(s)); new = sorted(set(s) - set(b))
moved = sorted(c for c in set(b) & set(s) if b[c] != s[c])
print("gone", gone, "new", new, "count-changed", moved)
print("VERDICT", "FAIL" if (gone or new or moved) else "PASS")
sys.exit(1 if (gone or new or moved) else 0)
PY
ls "$SCR"/*.py | wc -l                      # MUST print 9
```

**Controls for the new/changed helpers (run once; dry-run 2026-10-01):**
- `probe.py` — a 7-sample live log of `talosctl -e .11 -n .11,.12 etcd status` →
  `VERDICT PASS` (term 81→81, 0 elections). The same log with the last term bumped 81→82 →
  `FAIL: 1 election(s) … allowed 0`, and with `--allow-elections 1` → PASS. Two lines replaced
  by an `rpc error` → `FAIL: 2 consecutive samples without a common healthy leader`. In-window:
  build the bumped-term copy of the canary's first probe log with the same 3-line python edit
  and confirm FAIL before trusting the canary's PASS.
- `hwmon.py` — `compare` against a baseline file with one chip renamed must print `VERDICT FAIL`
  (`gone [...] new [...]`). *2026-10-01 baseline: `i2c_0_0_0050:3, i2c_0_0_0052:3,
  nvme_nvme0:9, platform_coretemp_0:45, thermal_thermal_zone1:9`.*
- `nodegate.py` — as talos-1.14.1: `check` against a snap with one leader change fewer →
  `FAIL … pattern (ii) triage`.
- `etcdgate.py` / `etcdstat.py` — §2.3b's two controls; `etcdstat.py defragged 192.168.55.12`
  printed `FAIL … in-use 30% of DB SIZE` on 2026-10-01 (today's un-defragged state).

**2.0b — PUSH FREEZE begins (F-84a27c15, talos-upgrade.md §14.3). AFTER this window's Step 0
has landed and Phase A's §3.7 commit is pushed; BEFORE 2.1.**

*Operator, before running anything below — stop the other writers yourself; an agent cannot:*
tell every other Claude Code session **"push freeze on cberg-home-nextgen main until the
talos-linux-1.14.2 window ends"**; no ad-hoc `operation sweep`; hold any OpenClaw cron that
commits to this repo; **merge no PRs** (incl. any talosctl CLI-pin PR — that is §3.12, after
§5.4); no manual Renovate run.

```bash
# (0) T0 for the §3.K0 clock = now (Step 0 is done). The window-open time is read in its OWN
#     Bash call (0a) below, because a sourced SWEEP_PG_DSN must not share a shell with git commits.
date -u +%s | tee "$SCR/t-plan-start.txt"
# (1) record the source state (spec.ignore from F-baf94b64 should be set)
mise exec -- kubectl -n flux-system get gitrepository flux-system \
  -o jsonpath='ignore=[{.spec.ignore}] size={.status.artifact.size} rev={.status.artifact.revision}{"\n"}' \
  | tee "$SCR/source-pre.txt"
# (2) the FREEZE SHA; the source must have fetched it
git fetch -q origin && git rev-parse origin/main | tee "$SCR/freeze-sha.txt"
# (3) suspend EVERY ImageUpdateAutomation that pushes to main — enumerated LIVE, not from a list
#     (2026-10-01: 5 — absenty x2, gas-price-monitor, splitfairy, showcase; the 09-27 plan knew 2)
mise exec -- kubectl get imageupdateautomation -A -o json | python3 -c "
import sys, json
for i in json.load(sys.stdin)['items']:
    if (i['spec'].get('git', {}).get('push') or {}).get('branch') == 'main':
        print(i['metadata']['namespace'], i['metadata']['name'], 'true' if i['spec'].get('suspend') else 'false')" > "$SCR/iua-pre.txt"
cat "$SCR/iua-pre.txt"; wc -l < "$SCR/iua-pre.txt"
# split: ONLY the rows not already suspended are ours to suspend (and later resume)
awk '$3=="false"{print $1, $2}' "$SCR/iua-pre.txt" > "$SCR/iua-main.txt"     # we suspend + resume these
awk '$3=="true"{print $1, $2}'  "$SCR/iua-pre.txt" > "$SCR/iua-presusp.txt"  # suspended IN GIT; never touch
wc -l < "$SCR/iua-main.txt"; wc -l < "$SCR/iua-presusp.txt"
while read -r ns name; do mise exec -- flux suspend image update "$name" -n "$ns"; done < "$SCR/iua-main.txt"
mise exec -- kubectl get imageupdateautomation -A -o custom-columns='NS:.metadata.namespace,NAME:.metadata.name,SUSPEND:.spec.suspend' --no-headers
```
*2026-10-01 live (the expected split):* `iua-pre.txt` has 5 rows; **`absenty-image-updates` in
`my-software-production` AND `my-software-development` are already `suspend: true` — set IN GIT**
(`kubernetes/apps/my-software-{production,development}/absenty/app/image-automation.yaml`,
line 54, a deliberate operator hold) → `iua-presusp.txt` = those 2; `iua-main.txt` = the 3 at
`<none>`: `gas-price-monitor-image-updates`, `splitfairy-image-updates` (production),
`showcase-image-updates` (showcase). Re-derive live; if the git hold was lifted by then, the
split moves and that is fine — the rule is the column, not this list.

**(0a) — Window-open time, ALWAYS rewritten (separate Bash call, READ-ONLY on sweep_history).**
Authoritative source: `window_runs.started_at` for today's `sun-attended` row(s), which the window
agent writes (`runbooks/window-run-record.py --outcome running`) when it opens the window, before
Step 0. The EARLIEST row of the day is used (a retried Sunday then prices the retry against the
first open, the conservative side). When no row exists (or the read fails) it automatically writes the
scheduled 09:00 Europe/Berlin with source `fallback-0900`, and §3.K0 then asks the present
operator for the actual open time (`operator-stated`) or DEFERs. Both files are deleted first and
rewritten every run, so a stale value in the fixed `$SCR` cannot survive into a retried window.
```bash
cd /Users/mu/code/cberg-home-nextgen
SCR="$HOME/.cache/talos-1142"                 # own Bash call: re-set, never inherit
rm -f "$SCR/t-window-open.txt" "$SCR/t-window-open.src"   # a retried Sunday never reuses a stale open
cat > "$SCR/winopen.py" <<'PY'
import os, sys, datetime as d, zoneinfo as z
# winopen.py <out-epoch-file> <out-source-file> [YYYY-MM-DD]   (READ-ONLY; needs SWEEP_PG_DSN)
import psycopg
tz = z.ZoneInfo("Europe/Berlin")
day = d.date.fromisoformat(sys.argv[3]) if len(sys.argv) > 3 else d.datetime.now(tz).date()
with psycopg.connect(os.environ["SWEEP_PG_DSN"]) as c, c.cursor() as cur:
    cur.execute("SELECT min(started_at), count(*) FROM window_runs WHERE slot = 'sun-attended' AND run_date = %s", (day,))
    t, n = cur.fetchone()
if t is not None:
    ep, src = int(t.timestamp()), f"window_runs (earliest of {n} row(s) for sun-attended {day})"
else:
    ep, src = int(d.datetime.combine(day, d.time(9, 0), tz).timestamp()), "fallback-0900"
open(sys.argv[1], "w").write(f"{ep}\n"); open(sys.argv[2], "w").write(f"{src}\n")
print(f"window-open {d.datetime.fromtimestamp(ep, tz).isoformat()} source={src}")
PY
if source runbooks/lib/sweep-pg-dsn.sh && sweep_pg_dsn_up >/dev/null; then
  .venv/bin/python3 "$SCR/winopen.py" "$SCR/t-window-open.txt" "$SCR/t-window-open.src" || echo "winopen.py FAILED"
else
  echo "DSN-FAIL: window_runs unreadable"
fi
sweep_pg_dsn_down >/dev/null 2>&1; true
# AUTOMATIC fallback pair on DSN-FAIL / query error / missing output (§3.K0 then asks the operator or DEFERs)
if [ ! -s "$SCR/t-window-open.txt" ] || [ ! -s "$SCR/t-window-open.src" ]; then
  python3 -c "import datetime as d, zoneinfo as z; tz = z.ZoneInfo('Europe/Berlin'); print(int(d.datetime.combine(d.datetime.now(tz).date(), d.time(9, 0), tz).timestamp()))" > "$SCR/t-window-open.txt"
  echo fallback-0900 > "$SCR/t-window-open.src"; echo "window-open FALLBACK written (09:00 Europe/Berlin)"
fi
echo "S0 (informational; §3.K0 decides) = $(( ($(cat "$SCR/t-plan-start.txt") - $(cat "$SCR/t-window-open.txt")) / 60 )) min, source $(cat "$SCR/t-window-open.src")"
```
**Expected:** one `window-open … source=window_runs (earliest of N row(s) …)` line. *Read-only
dry-run 2026-10-05:* `2026-09-27` → `08:47:38+02:00` from `window_runs` (that ad-hoc Sunday
opened 13 min BEFORE 09:00 — exactly the case the 09:00 fallback gets wrong), `2026-10-04` →
`09:00:14+02:00` from `window_runs`, `2026-10-05` (no row) → `09:00:00+02:00 source=fallback-0900`.
`fallback-0900` (no row, `DSN-FAIL`, or a `winopen.py` error — the fallback pair is written
automatically, dry-tested 2026-10-05 in the Bash tool's shell with a simulated DSN failure over
stale files) means the window agent's open is unknown: say so in the report; §3.K0 then asks the
present operator for the actual open time or DEFERs.

**PASS:** (1) `ignore=[…]` non-empty and `rev=` reads `refs/heads/main@sha1:<freeze-sha>` (else
wait for the 1-min interval); (2) one 40-hex sha; (3) `iua-pre.txt` lists ≥ 1 automation
(an empty file is a FAIL — the enumeration is blind), `iua-main.txt` + `iua-presusp.txt` line
counts sum to it, and every row of the final read prints `true`. **Negative control:** the
`iua-main.txt` rows read `<none>` in the pre-suspend `cat "$SCR/iua-pre.txt"` (column 3 =
`false`) and flip to `true` only after the loop — a read that printed `true` for them BEFORE
the loop would mean the column is not `.spec.suspend`. The `iua-presusp.txt` rows are `true`
both before and after and cannot serve as a control; their job is §5.4's
"still `true`" assertion (resuming them would override an operator hold made in git; the
owning Kustomization's next apply should restore it, but until then the automation is live and
can push absenty bumps to `main` — not measured how long that gap is, so never create it).

**The flux-system GitRepository is NOT suspended** (talos-upgrade.md §14.3: source-controller
storage is emptyDir; a suspended source never rebuilds its artifact after a drain moves the
pod — all Kustomizations would go `Ready=False`). The freeze is enforced by the **freeze-sha
gate**, before §3.8.0 and before EVERY node's §3.9:

```bash
git fetch -q origin && [ "$(git rev-parse origin/main)" = "$(cat "$SCR/freeze-sha.txt")" ] \
  && echo FREEZE-HELD || { echo "FREEZE BROKEN:"; git log --oneline "$(cat "$SCR/freeze-sha.txt")"..origin/main; }
```
**PASS:** `FREEZE-HELD`. Negative control: comparing against `origin/main~1` prints `FREEZE
BROKEN`. **On FREEZE BROKEN: do not start the next node**; name the commits/session to the
operator; continue only after the operator judges them harmless AND §2.3b's kustomize-controller
gate passes again. The window agent's own bookkeeping commits wait until after §5.4.

**2.1 — Nothing else in flight.** `exclusive: true`.

```bash
.venv/bin/python3 runbooks/maintenance-plan.py --open
cat runbooks/state/active-updates.json
grep -n '^status:' runbooks/maintenance/plans/talconfig-multidoc-migration.md 2>/dev/null || echo "migration plan retired (expected after it executed)"
git log --oneline -15
```
**PASS, all of:** no other plan carries today's `sun-attended:` ref; `"active": []`;
`talconfig-multidoc-migration` is executed/retired (premise
`multidoc-migration-applied-on-all-nodes` already proved the cluster side); no `now:<today>`
stamp outstanding.

**2.1b — What did THIS window's Step 0 apply?** Step 0 ran before the freeze (§2.0b) and may
have moved shared infra this plan's gates read or depend on.

```bash
git log --oneline "$(git log -1 --before='6 hours ago' --format=%H)"..HEAD -- kubernetes/ \
  | tee "$SCR/step0-commits.txt"
grep -iE 'kube-prometheus-stack|prometheus|longhorn|flux|cert-manager|cilium|coredns|envoy' "$SCR/step0-commits.txt" || echo "no shared-infra bump in Step 0"
git diff --stat "$(git log -1 --before='6 hours ago' --format=%H)"..HEAD -- kubernetes/ \
  | grep -iE 'kube-prometheus-stack|longhorn|flux|cert-manager|cilium|coredns|envoy' || true
```
**PASS:** `no shared-infra bump in Step 0`. **If kube-prometheus-stack, Longhorn, Flux,
cert-manager, cilium, coredns or envoy moved** (by commit subject OR by a touched path —
both greps are case-insensitive; a Renovate subject names the chart, the path names the
component): wait **≥ 10 min after its HelmRelease is `Ready` on the new version**, then
re-take every baseline recorded so far (§2.3b gates, §2.5 Longhorn baseline, §2.8 alert set
and hwmon, `notready-baseline.json`) — the 2026-09-27 baselines would otherwise attribute
Step 0's restarts to the canary. Do not proceed on a Longhorn manager/engine move without the
operator (§6.3: never with a Longhorn upgrade in flight). Negative control: on a Step-0-empty
morning the first grep prints the `echo` line; widening `--before` to `14 days ago` must list
at least one Renovate commit, proving the range expression is not empty by construction.

**2.2 — Nodes healthy, all on v1.14.1.** (premise `nodes-on-v1.14.1`)

```bash
mise exec -- kubectl get nodes -o wide
mise exec -- kubectl get nodes -o 'custom-columns=N:.metadata.name,OS:.status.nodeInfo.osImage,K:.status.nodeInfo.kernelVersion,CR:.status.nodeInfo.containerRuntimeVersion,KL:.status.nodeInfo.kubeletVersion'
```
**PASS:** 3× `Ready`, `Talos (v1.14.1)`, `6.18.51-talos`, `containerd://2.3.5`, `v1.36.0`.

**2.3 — etcd quorum and election base rate.**

```bash
mise exec -- talosctl -n 192.168.55.11,192.168.55.12,192.168.55.13 etcd status | tee "$SCR/etcd-status-pre.txt"
mise exec -- talosctl -n 192.168.55.11,192.168.55.12,192.168.55.13 etcd alarm list
mise exec -- kubectl get --raw "$P/query?query=max(increase(etcd_server_leader_changes_seen_total%5B24h%5D))"
```
**PASS:** 3 members, no `LEARNER`, empty `ERRORS`, converged `RAFT INDEX`, `PROTOCOL 3.7.1`
on all three; alarm list empty; 24h leader-change increase **< 6** (≥ 6 with no reboots = etcd
already unstable: NO-GO). *(2026-10-01 03:40Z: 3.7.1/3.7.0, DB 445–462 MB, IN USE 148 MB =
32–33 %, leader `73a201c6…` = k8s-nuc14-03, term 81; 24h increase 0, 7d 16 — the 7d figure
contains the 2026-09-27 roll.)* Read IN USE % here: it decides §3.8.0.

**2.3b — etcd disk gates (F-84a27c15), each able to fail.** After 2.0b; needs 10 quiet minutes
after the last push.

```bash
mise exec -- python3 "$SCR/etcdgate.py" --lookback 1h --leader-window 2h --allow-file "$SCR/leader-allow.log" | tee "$SCR/etcdgate-2.3.txt"
mise exec -- python3 "$SCR/etcdstat.py" converged
# control 1 — MUST print VERDICT FAIL on both latency lines (the latency queries are read)
mise exec -- python3 "$SCR/etcdgate.py" --fsync-ms 1 --commit-ms 1 --kc-mbps 1000
# control 2 — the leader counter is live: MUST print "value":[...,"3"]
mise exec -- kubectl get --raw "$P/query?query=count(etcd_server_leader_changes_seen_total%20%3E%200)"
```
**PASS:** the two real gates print `VERDICT PASS` — worst 5m-p99 WAL fsync AND backend commit
over 1h < 50 ms on every member (3 series each), 0 leader changes in 2h, kustomize-controller
< 5 MB/s over 10 min; etcd converged. Control 1 prints `VERDICT FAIL` naming both latency
lines; control 2 prints `"3"` (every member's counter exists and is > 0 — a member always counts
the election that seated the leader it joined; *2026-10-01: 1/3/6*; a misspelled metric returns
`"result":[]`, measured). Either control misbehaving = the gate is blind: NO-GO.
**Why not the talos-1.14.1 `--leader-window 7d` control:** dry-run 2026-10-01 it still prints
`VERDICT FAIL`, but for the WRONG reason — `no member was up for the whole leader window`,
because every etcd member restarted inside the last 7 d (the 09-27 roll). A control that fails
closed on an unrelated condition proves nothing about the counter; after any roll it decays
this way for a week. **Budget rule:** not PASS by window-start + 60 min
→ no roll today (§5.4, reschedule). A leader-change FAIL is not waited out — investigate.

**2.4 — Roll order, by RULE, now and before every node.**

```bash
for ip in 192.168.55.11 192.168.55.12 192.168.55.13; do
  echo -n "$ip vip="; mise exec -- talosctl -n $ip get addresses 2>/dev/null | grep -c '192.168.55.10/32'
done
mise exec -- talosctl -n 192.168.55.11,192.168.55.12,192.168.55.13 etcd status        # LEADER column
mise exec -- kubectl -n monitoring get pod prometheus-kube-prometheus-stack-0 -o jsonpath='{.spec.nodeName}{"\n"}'
mise exec -- kubectl -n storage get engines.longhorn.io -o custom-columns='NODE:.spec.nodeID' --no-headers | sort | uniq -c
```
**PASS:** exactly one node `vip=1`; all three rows agree on LEADER; the Prometheus pod has a node.

**The rule (applied at §3.8 before EVERY node):**
1. **Canary = the node running `prometheus-kube-prometheus-stack-0`, if it holds neither the
   VIP nor etcd leadership** (talos-upgrade.md §14.5 / F-e8bb3113: the canary's Prometheus
   blind spot is then covered by §3.9a's survivor probe and by the canary's clean rollback).
   Otherwise the canary is the first node in tie-break order **02 → 01 → 03** holding neither.
2. Then the remaining nodes in tie-break order, **except**: never roll a node holding BOTH
   the VIP and leadership while an un-rolled node holding neither exists; and if Prometheus
   re-landed on one of the two remaining nodes after the canary, roll that one **last** (one
   more blind spot instead of two).
*(2026-10-01 03:40Z: VIP 03, leader 03, Prometheus on 02, engines 01=21 / 02=27 / 03=46 →
**02 (canary) → 01 → 03**, unless Prometheus re-lands on 01, then 02 → 03 is blocked by
"both on 03", so 02 → 01 → 03 stands and 01 carries the second blind spot.)*

**2.5 — Longhorn: every not-healthy volume explained, set RECORDED.**

```bash
mise exec -- python3 "$SCR/lh_gate.py" baseline "$SCR/lh-baseline.json"
cat "$SCR/lh-baseline.json"
```
**PASS:** `VERDICT PASS`, `numberOfReplicas {2: N}`, the file records the not-healthy names
and replica total. *(2026-10-01: 94 volumes, 188 replicas, not-healthy `[]`.)* Any attached
not-healthy volume = NO-GO. At replica 2 on 3 nodes there is no spare-replica cushion.

**2.6 — Backups fresh.**

```bash
mise exec -- kubectl get jobs -n storage --sort-by=.status.startTime | grep daily-backup-all-volumes | tail -1
mise exec -- python3 "$SCR/bk.py" "$SCR/lh-baseline.json"
```
**PASS:** newest `daily-backup-all-volumes-*` Job `Complete` within 24h, and `VERDICT GO` (no
attached volume NEVER-backed-up or > 48h). The CronJob is `0 3 * * *` with no `timeZone` =
**03:00 UTC** (05:00 CEST until 2026-10-25, 04:00 CET after).

**2.7 — Flux green.**

```bash
mise exec -- flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
mise exec -- flux get helmreleases   -A | awk 'NR==1 || $5 != "True"'
```
**PASS:** header rows only.

**2.8 — Observability baselines, recorded.**

```bash
mise exec -- python3 "$SCR/alerts.py"   baseline "$SCR/alerts-baseline.json"
mise exec -- python3 "$SCR/notready.py" baseline "$SCR/notready-baseline.json"
mise exec -- python3 "$SCR/hwmon.py"    baseline "$SCR/hwmon-baseline.json"
mise exec -- kubectl get --raw "$P/targets" | python3 -c "
import sys,json
t=json.load(sys.stdin)['data']['activeTargets']
print('targets',len(t),'up',sum(1 for x in t if x['health']=='up'))
print('etcd:',[(x['labels'].get('instance'),x['health']) for x in t if 'etcd' in x['labels'].get('job','')])" \
  | tee "$SCR/targets-baseline.txt"
mise exec -- kubectl get --raw "$P/rules" | python3 -c "
import sys,json; g=json.load(sys.stdin)['data']['groups']
print('groups',len(g),'rules',sum(len(x['rules']) for x in g))" | tee "$SCR/rules-baseline.txt"
# WBT baseline (§1.2): today the attribute must NOT exist
for ip in 11 12 13; do echo -n "$ip wbt="; mise exec -- talosctl -n 192.168.55.$ip read /sys/block/nvme0n1/queue/wbt_lat_usec 2>&1 | head -1; done | tee "$SCR/wbt-pre.txt"
for ip in 11 12 13; do echo -n "$ip wc="; mise exec -- talosctl -n 192.168.55.$ip read /sys/block/nvme0n1/queue/write_cache; done
# per-node cmdline + /etc/hosts baseline (§4.1, CONTENTS ASSERTION 5)
for ip in 11 12 13; do mise exec -- talosctl -n 192.168.55.$ip read /proc/cmdline | tr ' ' '\n' | grep -E 'hugepages|i915|intel_iommu|mitigations|init_on_alloc' | sort | tr '\n' ' ' > "$SCR/cmdline-$ip.txt"; echo "$ip: $(cat "$SCR/cmdline-$ip.txt")"; done
```
**PASS:** `Watchdog firing: 1` and `VERDICT PASS` (the Watchdog is the positive control);
every target `up`, three etcd targets `.11/.12/.13:2381` up; `hwmon.py` records a non-empty
chip set; `wbt-pre.txt` shows `NotFound … no such file or directory` on all three **and**
`write_cache` reads `write back` (positive control: the same `talosctl read` path works, so the
NotFound is about the attribute, not the call); each `cmdline-*.txt` non-empty.
*(2026-10-01: cmdline `hugepages=1024 i915.enable_guc=3 init_on_alloc=0 intel_iommu=on
mitigations=off` on 13 — note: no doubled `init_on_alloc` on v1.14.1, unlike the v1.13.10
reading the 09-27 plan carried. The recorded files are the contract, not this example.)*

**2.9 — Envoy Gateway pre-state.**

```bash
mise exec -- kubectl get gateway -A
mise exec -- kubectl get httproute -A --no-headers | wc -l | tee "$SCR/httproutes-baseline.txt"
mise exec -- kubectl get pods -n network -o wide | grep -E 'envoy-(internal|external|gateway)'
# ONE real host per gateway that answers 2xx WITH A BODY. Hostnames stay out of this public repo.
INT_HOST=<host routed on envoy-internal>; EXT_HOST=<host routed on envoy-external>
printf '%s\n%s\n' "$INT_HOST" "$EXT_HOST" > "$SCR/probe-hosts.txt"
{ curl -sS -o /dev/null -w 'internal %{http_code} %{size_download}\n' -H "Host: $INT_HOST" https://192.168.55.103/ -k
  curl -sS -o /dev/null -w 'external %{http_code} %{size_download}\n' -H "Host: $EXT_HOST" https://192.168.55.104/ -k
} | tee "$SCR/curl-baseline.txt"
```
**PASS:** both Gateways `PROGRAMMED=True` (`envoy-internal` 192.168.55.103, `envoy-external`
192.168.55.104); route count recorded (*110 on 2026-10-01*); `envoy-internal`/`-external`/
`-gateway` 3 pods each, one per node; both curls 2xx with size > 0 (pick another host on a
3xx/0B).

**2.10 — Longhorn instance-manager PDBs.**

```bash
mise exec -- kubectl -n storage get pdb | grep instance-manager
```
**PASS:** exactly 3, one per node. `ALLOWED DISRUPTIONS = 0` is the correct steady state
(talos-upgrade.md §9) — do not delete them, do not reach for `--drain=false`.

**2.11 — UniFi: no switch firmware this window** (`docs/sops/unifi-device-firmware.md`).

```bash
mise exec -- unifictl local health get >/dev/null && echo session-ok
mise exec -- unifictl local device list -o json | python3 -c "
import sys,json
d=json.load(sys.stdin); d=d.get('data',d) if isinstance(d,dict) else d
print('devices',len(d),'upgradable=True:',[x.get('name') for x in d if x.get('upgradable')])"
```
**PASS:** `session-ok`, `devices N` (N > 0) and `upgradable=True: []`; plus the operator's read
in the Network UI that device auto-update is OFF (no CLI reader exists — human read, stated as
such). Never retry a unifictl login into a 429.

**2.12 — Per-node baseline for §3.10.**

```bash
mise exec -- python3 "$SCR/nodegate.py" snap "$SCR/node-pre.json"
mise exec -- kubectl get nodes -o custom-columns='N:.metadata.name,GPU:.status.allocatable.gpu\.intel\.com/i915,NPU:.status.allocatable.npu\.intel\.com/accel'
```
**PASS:** 3 carrier + 3 leader-change series recorded; every node `5` / `1`.

## 3) Steps

### Phase A — PREP, BEFORE the window opens (~30 min, zero workload/config effect)

`kubernetes/bootstrap/talos/` is **not reconciled by Flux** (no Kustomization `spec.path`
points there; configs are applied by `talosctl` by hand). Committing the bump changes nothing
until §3.9 runs `talosctl upgrade`. Run Phase A the evening before or before 09:00 on the day;
§7's price excludes it. The one node-side write is §3.7b's image pre-pull (~140 MB into each
node's image store; nothing references the images until Phase K patches the machine config).

**3.1 — The factory publishes our schematic at the target, WITH a negative control.**
(talos-upgrade.md §4 Step 1; the 2026-09-06 intercepting-middlebox lesson.)

```bash
SCHEM=43b3cbfc2957259b4588d362709d47387607901d4d3506c1ea46d7ea74cb99a3
for TAG in v1.14.2 v9.9.9; do
  printf "%-10s HTTP %s\n" "$TAG" "$(curl -s -o /dev/null -w '%{http_code}' "https://factory.talos.dev/v2/installer/$SCHEM/manifests/$TAG")"
done
```
**PASS — EXACTLY:** `v1.14.2 HTTP 200` and `v9.9.9 HTTP 404` *(measured 2026-10-01)*. Control
also 200 or both 3xx = intercepting proxy, result invalid. **Never add `-k`.**

**3.2 — Bump the node image.** One line in `kubernetes/bootstrap/talos/talconfig.yaml`. `sed`,
not `yq` (`yq -i` strips every blank line, talos-1.14.1 §3.2). BSD sed: `-i ''`, literal
anchors only.

```bash
cd /Users/mu/code/cberg-home-nextgen
sed -i '' -e 's|^talosVersion: v1\.14\.1$|talosVersion: v1.14.2|' kubernetes/bootstrap/talos/talconfig.yaml
git --no-pager diff kubernetes/bootstrap/talos/talconfig.yaml
```

**Expected diff — EXACTLY this** (dry-tested 2026-10-01 on a scratch copy of the current file,
111 lines before and after; a second run is a no-op):

```diff
@@ -1,7 +1,7 @@
 # yaml-language-server: $schema=https://raw.githubusercontent.com/budimanjojo/talhelper/master/pkg/config/schemas/talconfig.json
 ---
 # renovate: datasource=github-releases depName=siderolabs/talos
-talosVersion: v1.14.1
+talosVersion: v1.14.2
 # renovate: datasource=docker depName=ghcr.io/siderolabs/kubelet
 kubernetesVersion: v1.36.0
```

The migration plan edits `talconfig.yaml` too (patch list); if its edit moved the head of the
file, the context lines differ but the `-`/`+` pair must be exactly this one. **Any other
`-`/`+` line is a STOP.** Leave `kubernetesVersion` and every `talosImageURL` unchanged.

**3.3 — Refresh the deny-rule reason text** (documentation-only; no behaviour change).

```bash
sed -i '' -e 's|kubernetes/bootstrap/talos/talconfig.yaml, currently v1\.14\.1), so it must|kubernetes/bootstrap/talos/talconfig.yaml, currently v1.14.2), so it must|' runbooks/auto-update-policy.yaml
git --no-pager diff runbooks/auto-update-policy.yaml
```
**Expected diff (dry-tested 2026-10-01):**
```diff
@@ -453,7 +453,7 @@
   - match: "aqua:siderolabs/talos"
     reason: "talosctl CLI pin — tracks the CLUSTER version (talosVersion in
-      kubernetes/bootstrap/talos/talconfig.yaml, currently v1.14.1), so it must
+      kubernetes/bootstrap/talos/talconfig.yaml, currently v1.14.2), so it must
       never move AHEAD of the nodes. It FOLLOWS a node upgrade; it does not
```

**3.4 — Target still the head.**

```bash
gh api repos/siderolabs/talos/releases --jq '[.[] | select(.prerelease==false)] | .[0] | "\(.tag_name)  \(.published_at)"'
```
**PASS:** `v1.14.2`. A newer stable tag = STOP and re-seek the GO; never retarget in-window
(the README's DRIFTED procedure applies: refresh this file, keep the plan_id).

**3.5 — Download the target talosctl into scratch (checksum-verified; NOT the mise pin).**

```bash
curl -sfL -o "$SCR/talosctl-1.14.2" https://github.com/siderolabs/talos/releases/download/v1.14.2/talosctl-darwin-arm64
curl -sfL https://github.com/siderolabs/talos/releases/download/v1.14.2/sha256sum.txt | grep ' talosctl-darwin-arm64$'
shasum -a 256 "$SCR/talosctl-1.14.2"; chmod 700 "$SCR/talosctl-1.14.2"
"$SCR/talosctl-1.14.2" version --client --short
```
**PASS:** the published line and `shasum` print the **same** hash (*2026-10-01:
`4b509e96912278f2af58dc0005be5252124bcba4b87a7f877674160bbf000b6f`*) and the client says
`Talos v1.14.2`.

**3.6 — Validate the LIVE machine configs with talosctl 1.14.2 vs 1.14.1. No genconfig, no
write to `clusterconfig/`.** The roll keeps each node's current config, so the question is
"does v1.14.2 machinery accept what the node already has, with nothing new to say about it?".
`c792fa4` added validation WARNINGS on exactly the hostname/search-domain surface, so the gate
is a **warning-set diff between the running version's client and the target's**, which is
form-independent (it works on the v1alpha1 config of today and on the multi-doc config the
migration will have applied).

```bash
cd /Users/mu/code/cberg-home-nextgen
T2="$SCR/talosctl-1.14.2"
mise exec -- talosctl version --client --short                     # MUST be v1.14.1 (the pin; it moves at §3.12)
# (1) live configs -> scratch (machine secrets: never print, never commit). Read the ACTIVE id
#     `v1alpha1`; its `persistent` twin is byte-equal (premise no-pending-machineconfig-per-node).
( umask 077; for ip in 11 12 13; do
    mise exec -- talosctl -n 192.168.55.$ip get machineconfig v1alpha1 -o yaml \
      | .venv/bin/python3 -c "import sys,yaml; d=list(yaml.safe_load_all(sys.stdin)); assert len(d)==1, len(d); sys.stdout.write(d[0]['spec'])" \
      > "$SCR/live-$ip.yaml"
  done )
ls -l "$SCR"/live-*.yaml                                          # 3 files, -rw-------, non-zero
# (2) validate each with BOTH clients; compare verdicts and warning sets
for ip in 11 12 13; do
  mise exec -- talosctl validate --config "$SCR/live-$ip.yaml" --mode metal > "$SCR/v141-$ip.out" 2>&1; r1=$?
  "$T2" validate --config "$SCR/live-$ip.yaml" --mode metal > "$SCR/v142-$ip.out" 2>&1; r2=$?
  grep -i '^warning' "$SCR/v141-$ip.out" | sort > "$SCR/w141-$ip.txt"
  grep -i '^warning' "$SCR/v142-$ip.out" | sort > "$SCR/w142-$ip.txt"
  if [ $r1 -eq 0 ] && [ $r2 -eq 0 ] && cmp -s "$SCR/w141-$ip.txt" "$SCR/w142-$ip.txt" && grep -q 'is valid for metal mode' "$SCR/v142-$ip.out"; then
    echo "live-$ip SAME-VERDICT (warnings $(wc -l < "$SCR/w142-$ip.txt" | tr -d ' '))"
  else echo "live-$ip DIFFERENT -- STOP"; cat "$SCR/v142-$ip.out"; diff "$SCR/w141-$ip.txt" "$SCR/w142-$ip.txt"; fi
done
# (3) NEGATIVE CONTROL A — the parser/validator can fail: a duplicate HostnameConfig document
cp "$SCR/live-11.yaml" "$SCR/neg.yaml"
printf -- '---\napiVersion: v1alpha1\nkind: HostnameConfig\nhostname: k8s-nuc14-01\n' >> "$SCR/neg.yaml"
"$T2" validate --config "$SCR/neg.yaml" --mode metal > "$SCR/negA.out" 2>&1; echo "negA exit=$?"; grep -ci 'duplicate document' "$SCR/negA.out"
# (4) NEGATIVE CONTROL B — the warning DIFF can fail, and the two binaries really differ:
#     a whitespace hostname warns under 1.14.2 (c792fa4) and is silent under 1.14.1
sed 's|^hostname: k8s-nuc14-01$|hostname: "k8s nuc14"|' "$SCR/live-11.yaml" > "$SCR/neg.yaml"
mise exec -- talosctl validate --config "$SCR/neg.yaml" --mode metal 2>&1 | grep -i '^warning' | sort > "$SCR/wn141.txt"
"$T2" validate --config "$SCR/neg.yaml" --mode metal 2>&1 | grep -i '^warning' | sort > "$SCR/wn142.txt"
cmp -s "$SCR/wn141.txt" "$SCR/wn142.txt" && echo "negB SAME -- control FAILED to fail, STOP" || { echo "negB DIFFERENT (control works)"; diff "$SCR/wn141.txt" "$SCR/wn142.txt"; }
rm -P "$SCR/neg.yaml"
# (5) the image the roll will install
( cd kubernetes/bootstrap/talos && mise exec -- talhelper gencommand upgrade --node 192.168.55.12 \
    --extra-flags "--image='factory.talos.dev/installer/43b3cbfc2957259b4588d362709d47387607901d4d3506c1ea46d7ea74cb99a3:v1.14.2' --timeout=10m" ) \
  | sed -E 's/--talosconfig[= ][^ ]+/--talosconfig=<path>/'
```
**PASS — all of** *(every line below was measured on 2026-10-01 against today's v1alpha1 live
configs; re-run on the post-migration configs is the point of running it in Phase A)*:
- (1) three non-empty mode-600 files (*14155 B each today; the multi-doc form will differ*).
- (2) `live-11/12/13 SAME-VERDICT` — both clients exit 0, identical warning sets, 1.14.2 says
  `is valid for metal mode`. *(Today: 1 warning each, `.machine.files is deprecated`.)*
  `DIFFERENT` = v1.14.2 has something new to say about a running node's config: STOP, read it.
  Client-side validation only — boot adds runtime checks, so the canary remains the sufficient
  gate (§4.1).
- (3) `negA exit=1` and the grep prints `1` (*measured: `duplicate document
  v1alpha1/HostnameConfig/ is not allowed`*).
- (4) `negB DIFFERENT` and the diff shows the 1.14.2-only line `hostname: name "k8s nuc14"
  contains invalid character ' ' …` (*measured*). `SAME` = the comparison is blind or both
  invocations ran the same binary: STOP.
- (5) the printed command carries
  `--image=factory.talos.dev/installer/43b3cbfc…99a3:v1.14.2` (both `--image` flags, same value;
  requires §3.2 in the working tree) *(measured with talhelper 3.1.11 on a scratch copy; 3.1.17
  after the migration prints the same shape)*.

`rm -P "$SCR"/live-*.yaml` after §4.4 passes. Do NOT run `task talos:generate-config` in
Phases A/B (only Phase K's §3.K3 renders, locally) and never `apply-config` (§1.3).

**3.7 — Commit and push (still zero cluster effect).** `--only` with explicit paths; the
worktree is shared. Write the message file BEFORE the commit; do not source `SWEEP_PG_DSN` in
this shell (it breaks the pre-commit gate).

```bash
MSG="$SCR/talos-1142-commit-msg.txt"
cat > "$MSG" <<'MSGEOF'
feat(talos): node image v1.14.1 -> v1.14.2 (config only; roll is manual)

Bumps talosVersion in talconfig.yaml. Flux does not reconcile
kubernetes/bootstrap/talos/, so this commit changes nothing until
`task talos:upgrade-node` runs in the window. Machine configs are NOT
regenerated or applied: talosctl upgrade keeps each node's live config,
which validates identically under talosctl 1.14.1 and 1.14.2.

v1.14.2: kernel 6.18.54 (block writeback throttling now built in and on
by default), containerd 2.3.6, runc 1.5.2, kubelet resource-manager
state validation, sandboxd/CRI start-order fix. etcd stays 3.7.1,
Kubernetes stays v1.36.0.

Also refreshes the cluster version in the aqua:siderolabs/talos
deny-rule reason.

Plan: runbooks/maintenance/plans/talos-linux-1.14.2.md
MSGEOF
git commit --only kubernetes/bootstrap/talos/talconfig.yaml runbooks/auto-update-policy.yaml -F "$MSG"
git log -1 --format=%s          # MUST be the feat(talos) subject above; amend before push if not
git show --stat HEAD            # exactly these TWO files
git push
```

**3.7b — Pre-pull the Kubernetes 1.36.5 images for Phase K (Flux-inert; cuts ~4 min from
Phase K). Runs ONLY after the operator's GO for this plan is recorded** (it writes to every
node; a plan without a GO does not touch nodes, however inertly). This is upgrade-k8s's own step 2 (§1.5), done early through the same `ImagePull`
API: apiserver/controller-manager/scheduler into the `cri` namespace, the kubelet into `system`,
on all three nodes. It writes only to each node's image store; no pod, static pod, kubelet or
machine config references a v1.36.5 image until §3.K5. **Survives Phase B's reboots — measured
2026-10-05 on .12:** `ghcr.io/siderolabs/kubelet:v1.36.0` (system ns) and
`registry.k8s.io/kube-apiserver:v1.36.0` (cri ns) carry CREATED `2026-04-30T13:49–13:50Z` (the
2026-04-30 upgrade-k8s pull) on a node that booted `2026-09-27T08:26Z` in the v1.14.1 roll, and an
unused `kube-apiserver:v1.34.0` pulled 2026-01-05 is still present — Talos upgrades preserve
EPHEMERAL and kubelet image GC has not pruned unused images here. If the images are nevertheless
gone at §3.K5, upgrade-k8s simply pulls them (+~4 min), so this step is an optimisation, never a
gate on Phase K.

```bash
cd /Users/mu/code/cberg-home-nextgen
N=192.168.55.11,192.168.55.12,192.168.55.13
CRI_RE='registry\.k8s\.io/kube-(apiserver|controller-manager|scheduler):v1\.36\.5[[:space:]]'
SYS_RE='ghcr\.io/siderolabs/kubelet:v1\.36\.5[[:space:]]'
# control BEFORE: target images absent; the same grep on v1.36.0 proves the reader works
mise exec -- talosctl -n $N image list --namespace cri    | grep -cE "$CRI_RE"                                  # 0 (2026-10-05)
mise exec -- talosctl -n $N image list --namespace cri    | grep -cE 'registry\.k8s\.io/kube-(apiserver|controller-manager|scheduler):v1\.36\.0[[:space:]]'   # 9
mise exec -- talosctl -n $N image list --namespace system | grep -cE "$SYS_RE"                                  # 0
for ip in 192.168.55.11 192.168.55.12 192.168.55.13; do
  for img in registry.k8s.io/kube-apiserver:v1.36.5 registry.k8s.io/kube-controller-manager:v1.36.5 registry.k8s.io/kube-scheduler:v1.36.5; do
    mise exec -- talosctl -n "$ip" image pull --namespace cri "$img" || echo "PULL-FAIL $ip $img"
  done
  mise exec -- talosctl -n "$ip" image pull --namespace system ghcr.io/siderolabs/kubelet:v1.36.5 || echo "PULL-FAIL $ip kubelet"
done
# AFTER
mise exec -- talosctl -n $N image list --namespace cri    | grep -cE "$CRI_RE" | tee "$SCR/prepull-cri.txt"     # 9
mise exec -- talosctl -n $N image list --namespace system | grep -cE "$SYS_RE" | tee "$SCR/prepull-sys.txt"     # 3
```
**PASS:** before `0` / `9` / `0`; no `PULL-FAIL` line; after `9` and `3`. A `PULL-FAIL` (registry
outage, tag missing) is not a Phase B blocker — record it; §3.K5 will pull (and fail loudly if the
tag really is missing, before touching anything: pre-pull runs first and aborts the run). The
v1.36.0 grep printing `0` means the reader is blind: STOP the step. Re-read both counts at §3.K1
(after the reboots).

### Phase B — THE ROLL (in-window)

**Concurrency rule, absolute: exactly ONE node down at a time.** Two down = quorum lost = the
roll cannot be driven.

**3.8 — Apply the §2.4 rule before EVERY node** and write down, per node, who held the VIP and
who led etcd immediately before it rolled (§3.9/§3.10 need the leader flag). If the node about
to roll holds the VIP, the kubeconfig endpoint (192.168.55.10) drops for up to ~1 min; talosctl
drives nodes by IP. Per node, run **3.9 → 3.9a → 3.10 → 3.10a → 3.11 → 3.10b** to completion
before the next.

**3.8.0 — etcd defrag (docs/sops/etcd.md §4.3), ONCE, after §2.3b PASS, before §3.8a — only if
§2.3 read IN USE < 50 % of DB SIZE on any member** (*2026-10-01: 32–33 % → expected to run*).

```bash
git fetch -q origin && [ "$(git rev-parse origin/main)" = "$(cat "$SCR/freeze-sha.txt")" ] && echo FREEZE-HELD
mise exec -- talosctl -n 192.168.55.11,192.168.55.12,192.168.55.13 etcd status   # LEADER column
LEADER_IP=<ip whose MEMBER equals the LEADER column>
FOLLOWERS=(<ip> <ip>)            # an ARRAY (zsh does not word-split a scalar), 02 -> 01 -> 03 order
DONE=()
for ip in "${FOLLOWERS[@]}" "$LEADER_IP"; do
  echo "=== $ip"
  mise exec -- python3 "$SCR/etcdgate.py" --lookback 10m --leader-window 2h --allow-file "$SCR/leader-allow.log" \
    && mise exec -- python3 "$SCR/etcdstat.py" defragged "${DONE[@]}" \
    || { echo "GATE FAIL before defragging $ip -- STOP, do not defrag it"; break; }
  /usr/bin/time -p mise exec -- talosctl -n "$ip" etcd defrag || { echo "DEFRAG FAILED on $ip -- STOP"; break; }
  DONE+=("$ip"); sleep 60
done
echo "defragged: ${DONE[*]}  (MUST list all three)"
mise exec -- python3 "$SCR/etcdstat.py" defragged "${DONE[@]}"
mise exec -- python3 "$SCR/etcdgate.py" --lookback 10m --leader-window 2h --allow-file "$SCR/leader-allow.log"
mise exec -- talosctl -n 192.168.55.11,192.168.55.12,192.168.55.13 etcd alarm list
```
**PASS:** each in-loop gate PASS before the next member; final `defragged <all three>` PASS
(IN USE ≥ 80 %), final gate PASS, alarms empty; `real` in seconds. A gate FAIL right after a
follower's defrag is its own spike: re-check every 3 min, ≤ 6 tries, continue with only the
members not in `DONE`; still failing = stop defragging (a partly-defragged cluster is fine) and
proceed only if §2.3b's gates pass on a re-run. **One** leader change right after the
**leader's** defrag is explained — `echo "$(date -u +%s) defrag-of-leader $LEADER_IP" >>
"$SCR/leader-allow.log"`; a change during a follower's defrag, or more than one = STOP, no
snapshot, no roll (§5.4). A member not healthy after 5 min: `talosctl -n <ip> service etcd
restart` on that member only; still bad = NO-GO. Skip this section (and its 7 min) if every
member is ≥ 50 % at §2.3 — note the reading.

**3.8a — Pre-roll etcd snapshot** (talos-upgrade.md Step 0.4, mandatory; defence in depth —
this hop does not move etcd, §5).

```bash
LEADER_IP=<current leader ip>
mise exec -- talosctl -n "$LEADER_IP" etcd snapshot "$SCR/etcd-pre-v1.14.2.db"
chmod 600 "$SCR/etcd-pre-v1.14.2.db"; stat -f '%Lp %z %N' "$SCR/etcd-pre-v1.14.2.db"; stat -f '%Lp %N' "$SCR"
```
**PASS:** mode 600, dir 700, size in the order of the post-defrag DB SIZE (*~150–300 MB*; a
0-byte/few-KB file is a FAIL — no roll). Local only, holds every Secret; `rm -P` after 24h soak.

**3.9 — Upgrade one node.**

```bash
git fetch -q origin && [ "$(git rev-parse origin/main)" = "$(cat "$SCR/freeze-sha.txt")" ] && echo FREEZE-HELD   # MUST print it
mise exec -- python3 "$SCR/nodegate.py" snap "$SCR/node-pre-<node-name>.json"
date -u +%s > "$SCR/node<N>-start.txt"                 # N = 1, 2, 3 in roll order; §4.4 #9 reads node3
# ONLY if this node is the etcd leader right now: pre-record its expected election
# echo "$(date -u +%s) rolled-leader <node-name>" >> "$SCR/leader-allow.log"
```

**3.9a — Start the survivor record (F-e8bb3113), THEN upgrade.** Prometheus may be on the node
being drained (it was on the canary-to-be on 2026-10-01) and then has no samples for exactly
the reboot window (talos-upgrade.md §14.5). This record does not depend on it: a 5-s poll of
`etcd status` from the two survivors, using a survivor as the talosctl ENDPOINT so the poll
never routes through the node going down, plus their etcd logs.

```bash
S1=<survivor ip>; S2=<other survivor ip>; NODE=<node-name>
( while :; do printf '%s ' "$(date -u +%s)"; mise exec -- talosctl -e "$S1" -n "$S1,$S2" etcd status 2>&1 | tr '\n' '|'; echo; sleep 5; done ) \
  > "$SCR/probe-$NODE.log" 2>&1 & PROBE=$!
mise exec -- talosctl -e "$S1" -n "$S1" logs etcd -f > "$SCR/etcd-$S1-$NODE.log" 2>&1 & L1=$!
mise exec -- talosctl -e "$S2" -n "$S2" logs etcd -f > "$SCR/etcd-$S2-$NODE.log" 2>&1 & L2=$!
sleep 15; tail -2 "$SCR/probe-$NODE.log" | cut -c1-200     # MUST show rows for both survivors
mise exec -- task talos:upgrade-node IP=<node-ip>
```
Installs the image, cordons, drains, reboots. It will sit on `evicting pod
storage/instance-manager-<hash>` until the node's Longhorn engines drain to 0 — normal
(talos-upgrade.md §9). Watch:

```bash
mise exec -- kubectl -n storage get engines.longhorn.io -o json | python3 -c "
import sys,json
print(len([e for e in json.load(sys.stdin)['items'] if e['spec'].get('nodeID')=='<node-name>']))"
```

**POSITIVE CONTROL for §4.4 #4 — canary only, mid-drain**, while its engine count is > 0:
`mise exec -- python3 "$SCR/notready.py" compare "$SCR/notready-baseline.json"` MUST print
`VERDICT FAIL` naming ≥ 1 workload (evicted envoy replicas sit Pending under
`topologySpreadConstraints` + PDB `minAvailable: 2`). A `PASS` mid-drain = the helper is blind:
STOP before §3.10.

**Do NOT** delete the PDBs or pre-emptively use `EXTRA_FLAGS='--drain=false'`. Only on a drain
**timeout** (`context deadline exceeded` waiting for `instance-manager-…`): uncordon first, then
delete the `Pending` pods so the scheduler spreads the attach load.

**Node-down tripwire:** not back `Ready` within 10 min of the reboot starting = Longhorn will
start FULL rebuilds on the two quorum disks. Every 2 min until it returns:
`mise exec -- python3 "$SCR/etcdgate.py" --members 0 --lookback 5m --allow-file "$SCR/leader-allow.log"`,
reading the two SURVIVORS' lines. Any survivor election or survivor p99 ≥ 50 ms = no next node today.
**When Prometheus is on the node that is down** (it was on canary 02 on 2026-10-01 — check
`kubectl -n monitoring get pod -o wide | grep prometheus-kube-prometheus-stack` before §3.9a),
`etcdgate.py` has no instrument for exactly this interval: it prints a query/connection error
or a no-series FAIL, which is NOT a survivor verdict. The tripwire for that interval is the
§3.9a survivor probe log instead:
`python3 "$SCR/probe.py" "$SCR/probe-$NODE.log" "$S1" "$S2" --allow-elections <1 if this node was leader, else 0>` every 2 min (PASS/FAIL on
survivor elections and leaderless samples, Prometheus-independent), plus
`tail -3 "$SCR/probe-$NODE.log" | cut -c1-200` by eye. Resume `etcdgate.py` once Prometheus is
Running again.

**3.10 — Node health gate + pattern (ii).** When the node is `Ready`:

```bash
kill $PROBE $L1 $L2 2>/dev/null
mise exec -- kubectl get nodes -o wide
mise exec -- talosctl -n <node-ip> version --short
mise exec -- talosctl -n 192.168.55.11,192.168.55.12,192.168.55.13 etcd status
mise exec -- python3 "$SCR/nodegate.py" check "$SCR/node-pre-<node-name>.json" <node-name> <yes|no: was it leader at 3.8?> | tee "$SCR/g310-<node-name>.txt"
python3 "$SCR/probe.py" "$SCR/probe-<node-name>.log" "$S1" "$S2" --allow-elections <1 if it was leader, else 0> | tee -a "$SCR/g310-<node-name>.txt"
grep -ciE 'elected leader|lost leader|leader changed' "$SCR/etcd-$S1-<node-name>.log" "$SCR/etcd-$S2-<node-name>.log"
```
**PASS, all of:** node `Ready`, not `SchedulingDisabled`, `Tag: v1.14.2`; etcd **3 members**, no
LEARNER, empty ERRORS, raft converged (a `Ready` node with a missing member = quorum of two: do
not proceed); `nodegate.py` `VERDICT PASS` (i915=5 / NPU=1 re-registered; falco, falco-log-rotate,
wazuh-agent, otel daemon collector, node-exporter **3/3** — falco's `modern_ebpf` meets kernel
6.18.54 here; survivors' NIC carrier +0; survivors' leader changes within the allowance);
`probe.py` `VERDICT PASS` (≥ 6 samples, never 2 consecutive samples without a common healthy
leader, elections within the allowance). The log grep is evidence for triage, not a gate
(case-insensitive on purpose; etcd's wording varies by version). `$SCR/g310-<node-name>.txt` is
the per-node record §3.K0 reads (first `tee` overwrites, so a re-run of §3.10 for that node
replaces a failed record rather than appending to it).

**Pattern (ii) — talos-upgrade.md §14.3, now a written rule (F-2cb2dbc9).** If `nodegate.py` or
`probe.py` reports an election that this node's own reboot does not explain: **STOP and triage.**
Continue to the next step ONLY if ALL hold, each read from its instrument:
1. NIC carrier **+0** on both survivors (`nodegate.py` survivor lines) — a carrier change =
   the network moved (switch/firmware/cabling): STOP the roll, check §2.11 + `unifictl local
   event list`;
2. **never leaderless** — `probe.py` worst consecutive bad < 2 (Prometheus-independent), AND,
   if Prometheus was NOT on the drained node,
   `min_over_time(etcd_server_has_leader[15m]) = 1` on both survivors;
3. slow fdatasync only inside the drain window — §3.10b's 10-min latency gate PASSES after it;
4. `etcdstat.py converged` PASS.
Otherwise stop part-rolled (§5.2 — a supported mixed state). Record the decision and the four
readings in `$SCR/pattern-ii-<node>.txt`. Never add a line to `leader-allow.log` to make a gate pass.

**3.10a — Forward-auth gate (F-89376ab7).** The 13 authentik outposts are single-replica by
design (filesystem session store; Envoy would ping-pong a 2-replica outpost). Expect a short
5xx and one silent re-login on apps whose outpost lived on the drained node. Do not scale them.

```bash
mise exec -- kubectl get deploy -n kube-system -l app.kubernetes.io/managed-by=goauthentik.io
mise exec -- kubectl get pods -n kube-system -l app.kubernetes.io/managed-by=goauthentik.io -o wide
mise exec -- kubectl get securitypolicy -A -o json | python3 -c "
import sys, json, subprocess
for p in json.load(sys.stdin)['items']:
    if not p['spec'].get('extAuth'): continue
    ns = p['metadata']['namespace']
    for t in p['spec'].get('targetRefs', []):
        h = subprocess.run(['mise','exec','--','kubectl','get','httproute','-n',ns,t['name'],
            '-o','jsonpath={.spec.hostnames[0]}'], capture_output=True, text=True).stdout
        print(t['name'], h)" > "$SCR/fwd-auth-hosts.txt"
wc -l < "$SCR/fwd-auth-hosts.txt"
while read -r name host; do echo "$name $(curl -s -o /dev/null -m 10 -w '%{http_code}' "https://$host/")"; done < "$SCR/fwd-auth-hosts.txt"
```
**PASS:** all outpost deployments `1/1` (*13 on 2026-10-01*), none on a `SchedulingDisabled`
node; the host list is non-empty (*12 SecurityPolicies on 2026-10-01* — an empty list makes the
loop pass on nothing: FAIL) and every host returns **302** or **200**, none 5xx/000. The
uptime-kuma outpost (`mode: proxy`, no SecurityPolicy) — curl its host once by hand, expect 302.

**3.11 — THE LONGHORN GATE.** Do not start the next node until it passes.

```bash
mise exec -- python3 "$SCR/lh_gate.py" gate "$SCR/lh-baseline.json"
```
**PASS — `VERDICT PASS`:** not-healthy set equals the §2.5 recording; replica total equals the
recording (*188 on 2026-10-01*); read the per-node table — the rebooted node has a `running`
count in the order of its §2.5 line. **Failed replicas** on the rolled node keep the total
off: since F-b91ef6e5 every volume has `staleReplicaTimeout` 20/30, so they are GC'd within
~30 min; if the 25-min budget below would trip on them, use talos-upgrade.md §14.4's procedure
(delete only `DELETE-OK` failed replicas on the rolled node of volumes with ≥ 2 healthy
replicas, one by one; never Volume/PV/PVC).

**Rebuild concurrency stays at 8 — the decision, with reasons (F-2cb2dbc9 / F-7b842e62).**
(a) Measured 09-27: rebuild ~20 min/node at 8; at 2 it would be several times longer and the
roll would not fit the slot (§7). (b) The 09-27 survivor stalls were in the DRAIN window
(eviction burst, engine moves, cold kustomize-controller — talos-upgrade.md §14.3), before the
returning node's incremental rebuild starts, so the limit is not the lever for them. (c) The
correct path, if the operator wants it, is a TOP-LEVEL `values.defaultSettings.
concurrentReplicaRebuildPerNodeLimit` in the Longhorn HelmRelease with an explicit restore
to 8 (the `values.longhorn:` block is inert; `git revert` does not restore the Setting CR) —
its own small plan landed before the window, not an edit under the freeze. **Operator: if you
want the throttle anyway, say so at the GO; this plan is then re-priced, not run as-is.**

**Budget rule:** not PASS 25 min after the node returned `Ready` → stop rolling, leave the
cluster part-rolled (§5.2), finish §4.4 on the mix, reschedule.

**3.10b — Inter-node settle + etcd gate (between nodes 1→2 and 2→3).** Starts at §3.11 PASS.
**Wait ≥ 10 min**, then:

```bash
date -u +%s > "$SCR/settle-start-<node-name>.txt"          # at §3.11 PASS
# ... >= 10 min; use it for §4.1, the canary go/no-go and §3.8's re-check
mise exec -- python3 "$SCR/etcdgate.py" --lookback 10m --leader-window 2h --allow-file "$SCR/leader-allow.log"
mise exec -- python3 "$SCR/etcdstat.py" converged
echo "settled $(( ($(date -u +%s) - $(cat "$SCR/settle-start-<node-name>.txt")) / 60 )) min"   # MUST be >= 10
```
**PASS:** ≥ 10 min; `etcdgate.py` PASS (worst p99 fsync AND commit < 50 ms over the 10-min
settle window, no unexplained leader change in 2h, kc < 5 MB/s); `etcdstat.py` PASS (raft
converged — caught up, not merely rejoined). On the FIRST pass confirm the rolled member is
listed under `skipped (restarted inside it)` — if not, `process_start_time_seconds` is not
tracking reboots and the leader count is unreliable: STOP. Not PASS within 20 min of the settle
start → stop part-rolled (§5.2). Why 10 min not 1h: the last hour contains this plan's own
drain by construction (talos-1.14.1 §3.10b).

**3.12 — talosctl CLI pin → 1.14.2 — LAST, after §4.4 PASS, Phase K (§3.K7 pushed, or K
DEFERRED at §3.K0) and §5.4 ended the freeze, and only if all three nodes report v1.14.2.** No Renovate PR existed on 2026-10-01. If one has appeared
by then whose diff changes ONLY the `"aqua:siderolabs/talos"` line to `"1.14.2"` with green
checks (incl. `Flate Render Gate`), merge it (`gh pr merge <n> --squash`). Otherwise edit by hand:

```bash
mise exec -- kubectl get nodes -o wide | grep -c 'Talos (v1.14.2)'     # MUST be 3
sed -i '' -e 's|^"aqua:siderolabs/talos" = "1\.14\.1"  # CLI pin|"aqua:siderolabs/talos" = "1.14.2"  # CLI pin|' .mise.toml
git --no-pager diff .mise.toml          # exactly ONE -/+ pair, on the "aqua:siderolabs/talos" line (dry-tested 2026-10-01)
MSG="$SCR/talos-1142-cli-msg.txt"
printf 'chore(mise): talosctl CLI pin 1.14.1 -> 1.14.2 (cluster rolled)\n\nAll three nodes report Talos v1.14.2. The CLI pin follows the cluster.\n\nPlan: runbooks/maintenance/plans/talos-linux-1.14.2.md\n' > "$MSG"
git commit --only .mise.toml -F "$MSG"
git log -1 --format=%s; git show --stat HEAD     # subject yours; exactly .mise.toml
git push
mise install && mise exec -- talosctl version --short            # Client v1.14.2, servers v1.14.2
```
Fewer than 3 nodes on v1.14.2 → do NOT bump; a v1.14.1 client drives a mixed cluster fine.
The `talhelper` line is not touched here (the migration owns it).

**Explicitly NOT in Phases A/B:** `task talos:upgrade-k8s` (that is Phase K, after §4.4),
`generate-config` (Phase K §3.K3 only), `apply-config` (never), any machine-config patch other
than the ones upgrade-k8s itself writes in Phase K.

### Phase K — Kubernetes v1.36.0 → v1.36.5 (in-window, AFTER §4.4 + §4.5 PASS, no reboot)

**Execution order of the window tail:** Phase B → §4.1–§4.6 → **§3.K0 checkpoint** → (K1–K6 +
§4.7, or DEFER) → §5.4 freeze lift → §3.K7 commit/push (if K ran) → §3.12 CLI pin. The push
freeze stays up through Phase K: `talconfig.yaml` is edited in the working tree from §3.K2 to
§3.K7, and a concurrent edit of it (Renovate, another session) would ride into §3.K7's commit or
make §3.K3's render diff unreadable. Phase K reads Prometheus through the same apiserver proxy
as Phase B; while one of the three apiservers restarts, a `kubectl get --raw` through the VIP
can be refused for a few seconds (Talos does not move the VIP on an apiserver restart) — retry
the read, never "fix" it. In-cluster clients use the `kubernetes` Service, Cilium uses KubePrism
(`127.0.0.1:7445`); both fail over to the other two apiservers.

**3.K0 — GO / NO-GO / DEFER checkpoint (the designed overflow valve).** Mechanical, not an extra
human stop: the operator's window GO covers Phase K; this checkpoint only asks the operator when
the clock needs an extension.

```bash
cd /Users/mu/code/cberg-home-nextgen
SCR="$HOME/.cache/talos-1142"                                               # re-set, never inherit
N=192.168.55.11,192.168.55.12,192.168.55.13
rm -f "$SCR/k-klim.txt"                                                     # never inherit a GO
FH=0; git fetch -q origin && [ "$(git rev-parse origin/main)" = "$(cat "$SCR/freeze-sha.txt")" ] && { echo FREEZE-HELD; FH=1; } || echo "FREEZE BROKEN"
mise exec -- kubectl get nodes -o 'custom-columns=N:.metadata.name,R:.status.conditions[?(@.type=="Ready")].status,OS:.status.nodeInfo.osImage,KL:.status.nodeInfo.kubeletVersion'
KV=$(grep -c '^kubernetesVersion: v1.36.0$' kubernetes/bootstrap/talos/talconfig.yaml); echo "talconfig v1.36.0 lines: $KV"   # 1
# roll record: PRESENCE gate PER NODE on the §3.10 files (each: exactly 2 PASS = nodegate + probe,
# 0 FAIL), plus the absence of pattern-(ii) triage records. `find`, NOT a glob: the executor's zsh
# runs with nobareglobqual + nomatch, where `g310-*.txt(N)` aborts with "no matches found".
n=0; bad=0
for f in $(find "$SCR" -maxdepth 1 -name 'g310-*.txt'); do n=$((n+1)); p=$(grep -c '^VERDICT PASS$' "$f"); x=$(grep -c '^VERDICT FAIL$' "$f"); echo "  $(basename "$f") pass=$p fail=$x"; [ "$p" -eq 2 ] && [ "$x" -eq 0 ] || bad=$((bad+1)); done
pii=$(find "$SCR" -maxdepth 1 -name 'pattern-ii-*.txt' | wc -l | tr -d ' ')
RR=0; [ "$n" -eq 3 ] && [ "$bad" -eq 0 ] && [ "$pii" -eq 0 ] && { echo "K0-ROLLRECORD PASS (files=$n pattern-ii=$pii)"; RR=1; } || echo "K0-ROLLRECORD FAIL (files=$n bad=$bad pattern-ii=$pii)"
# §3.7b pre-pull counts (after the reboots) feed the clock: missing images = Phase K costs 49, not 45
CRI=$(mise exec -- talosctl -n $N image list --namespace cri    | grep -cE 'registry\.k8s\.io/kube-(apiserver|controller-manager|scheduler):v1\.36\.5[[:space:]]')
SYS=$(mise exec -- talosctl -n $N image list --namespace system | grep -cE 'ghcr\.io/siderolabs/kubelet:v1\.36\.5[[:space:]]')
cat > "$SCR/k0clock.py" <<'PY'
import sys
# k0clock.py <window-open-epoch> <window-open-source> <plan-start-epoch> <now-epoch> <prepull-cri> <prepull-sys> <klim-out-file>
tw = int(sys.argv[1]); src = sys.argv[2]; t0, now, cri, sysc = map(int, sys.argv[3:7]); out = sys.argv[7]
if not (src.startswith("window_runs") or src.startswith("operator-stated")):
    print(f"open-source={src}")
    print("K0-CLOCK DEFER (no recorded window open: ask the present operator for the actual open time,"
          " record it as operator-stated (§3.K0) and re-run; no answer = DEFER)")
    sys.exit(0)
s0 = (t0 - tw) // 60; el = (now - t0) // 60
kcost = 45 if (cri == 9 and sysc == 3) else 49        # §7: +4 when upgrade-k8s must pull
close = 6                                              # §5.4 + §3.12
raw = 200 - s0 - kcost - close                         # latest start that still ends inside the raw 200
klim = min(180 - kcost - close, raw)                   # 129 with the pre-pull and S0 = 20
print(f"open-source={src} S0={s0}min EL=T+{el} prepull cri={cri}/9 sys={sysc}/3 -> Phase K {kcost}min; KLIM=T+{klim}; raw-limit=T+{raw}")
if s0 < 0:
    print("K0-CLOCK DEFER (clock inconsistent: window open is after plan start)")
elif el < 0:
    print("K0-CLOCK DEFER (clock inconsistent: plan start in the future)")
elif el <= klim:
    open(out, "w").write(f"{klim}\n"); print("K0-CLOCK GO")
elif el <= raw:
    print(f"K0-CLOCK ASK-EXTENSION (limit {raw})")
else:
    print("K0-CLOCK DEFER")
PY
# the clock runs ONLY when the roll record, the freeze and the untouched pin all hold
if [ "$RR" -eq 1 ] && [ "$FH" -eq 1 ] && [ "$KV" -eq 1 ]; then
  python3 "$SCR/k0clock.py" "$(cat "$SCR/t-window-open.txt")" "$(cat "$SCR/t-window-open.src")" "$(cat "$SCR/t-plan-start.txt")" "$(date -u +%s)" "$CRI" "$SYS" "$SCR/k-klim.txt"
else
  echo "K0 DEFER (rollrecord=$RR freeze-held=$FH talconfig-v1.36.0=$KV): clock not run, no k-klim.txt"
fi
```
The block prints `K0 DEFER (rollrecord=… freeze-held=… talconfig-v1.36.0=…)` without running the
clock unless all three preconditions hold. The clock then prints **exactly one** of `K0-CLOCK GO`
/ `K0-CLOCK DEFER` / `K0-CLOCK ASK-EXTENSION (limit L)`, and only `GO` writes `$SCR/k-klim.txt` —
the file §3.K5's guard requires. Dry-tested 2026-10-05 on synthetic epochs (source `window_runs`
unless stated): S0 20/EL 120 → GO (KLIM 129, file written); S0 20/EL 130 → DEFER; S0 5/EL 130 →
ASK-EXTENSION (limit 144); **S0 40 (early ad-hoc open, 40-min Step 0)/EL 120 → DEFER (KLIM
109)**; `operator-stated` S0 40/EL 100 → GO (KLIM 109); `fallback-0900` → DEFER with the
ask-the-operator instruction; S0 20/EL 126 with pre-pull 0/0 → DEFER (KLIM 125); open after plan
start → DEFER (inconsistent). No `k-klim.txt` in every non-GO case.

**On `fallback-0900` (N4):** ask the present operator once for the actual window-open time (the
moment Step 0 started). If stated: `python3 -c "import datetime as d, zoneinfo as z;
print(int(d.datetime.combine(d.date.today(), d.time(H, M), z.ZoneInfo('Europe/Berlin')).timestamp()))"
> "$SCR/t-window-open.txt"; echo "operator-stated HH:MM" > "$SCR/t-window-open.src"` and re-run this
block (the clock accepts sources `window_runs …` and `operator-stated …` only). No answer → DEFER.

**Roll-record known-bad demo — dry-tested 2026-10-05 IN THE BASH TOOL'S OWN SHELL (zsh 5.9,
`nobareglobqual`), not `zsh -f`:** 2/2/2 PASS → `K0-ROLLRECORD PASS (files=3 pattern-ii=0)`;
2/1/3 (total still 6) → `FAIL (files=3 bad=2 …)`; 2/2/2 + a `pattern-ii-*.txt` → `FAIL (…
pattern-ii=1)`; empty dir → `FAIL (files=0 …)`; 2 files → `FAIL (files=2 …)`; 4 files → `FAIL
(files=4 …)`; 2/2/2 with one extra `VERDICT FAIL` line → `FAIL (… bad=1 …)`. (An earlier draft
used `g310-*.txt(N)`, which passed under a fresh `zsh` but aborts with "no matches found" in the
executor's shell — Phase K could never have GONE.) Executor's own control: run the
`n=0 … RR=` lines only, with `SCR=$(mktemp -d)` holding one `g310-x.txt` of a single `VERDICT
PASS` line → must print `K0-ROLLRECORD FAIL (files=1 bad=1 …)`.

**GO to §3.K1 only if ALL hold:**
1. **The OS roll is complete and green:** §4.4 #1–#11 and §4.5 all PASS (3× `Talos (v1.14.2)`,
   kubelet still `v1.36.0`, Longhorn gate PASS, etcd converged, alerts sustained ≥ 15 min);
   `FREEZE-HELD`; no node was rolled back (§5.1) and the roll was not stopped part-rolled
   (§5.2). **Roll record present:** `K0-ROLLRECORD PASS` — exactly 3 g310 files, each with exactly
   2 `VERDICT PASS` (nodegate + probe) and 0 `VERDICT FAIL`, and `0` `pattern-ii-*.txt` — a triaged-and-continued election is a
   reason to leave the control plane alone today. Any other file count or per-file tally = the record is
   missing or broken, not clean: DEFER.
2. **Clock:** `K0-CLOCK GO`. KLIM = min(180 − Kcost − 6, 200 − S0 − Kcost − 6) with Kcost 45
   (49 if the pre-pull counts are not `9`/`3`) and S0 = T0 − the §2.0b(0a) window open (source
   `window_runs` or `operator-stated`; `fallback-0900` → ask or DEFER, above); 129 when S0 = 20
   and the pre-pull held.
3. **Extension — only on `K0-CLOCK ASK-EXTENSION (limit L)`**, which the clock prints only when
   a recorded or operator-stated S0 < 20 left room inside the raw 200: ask the present operator once — *"Phase K needs ~Kcost
   min, ending inside the raw window end; extend past the 180 budget?"* (no live question if the
   operator pre-stated the answer at the GO, §7). On yes: `echo L > "$SCR/k-klim.txt"` and record
   the answer in the window report. No answer, "no", or `K0-CLOCK DEFER` → **DEFER**. Never trim
   a K gate or the 10-min soak to fit.
4. `talconfig.yaml` still pins `v1.36.0` (`1`) — Phase K has not been half-started.

**DEFER (any condition fails):** touch nothing of Phase K. The §3.7b images stay on the nodes,
unreferenced and harmless (they are reused when Phase K runs). Continue with §5.4 and §3.12; the
OS roll is the complete outcome of this window. Window report: `Phase K DEFERRED: <which
condition, EL>`. **Follow-up for the coordinator (not the executor):** re-activate
`k8s-1.36.5` (its file is kept intact for exactly this) — `status: draft`, drop
`superseded_by`, move `security_ref` + the three Phase K `finding_refs` back to it, and re-add the
mutual `conflicts_with` here. Its premise `talos-uniform-1.14` accepts a uniform v1.14.2 and its
§3.1 diff tolerates the moved `talosVersion` context line; **one amendment is owed:** its §3.2
render PASS expects `10` lines/node, but the local `clusterconfig/` will still be the v1.14.1
render, so it reads **`12`** (the two installer-image lines `:v1.14.1 → :v1.14.2`, measured
2026-10-05) unless something re-rendered it after the roll. It fits sat-attended (55 ≤ 70).

**3.K1 — Phase K baselines** (re-measured now, after the roll; Phase B's files are not reused
for these instruments because every pod moved since §2).

```bash
cd /Users/mu/code/cberg-home-nextgen
N=192.168.55.11,192.168.55.12,192.168.55.13
pq(){ mise exec -- kubectl get --raw "$P/query?query=$1" | python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];print(len(r),sorted((tuple(sorted(x['metric'].items())),x['value'][1]) for x in r))"; }
date -u +%Y-%m-%dT%H:%M:%SZ | tee "$SCR/k-t0.txt"; date -u +%s > "$SCR/k-t0.epoch"
mise exec -- talosctl -n $N get apiserverconfigs -o yaml | grep -c 'image: registry.k8s.io/kube-apiserver:v1.36.0'   # 6
mise exec -- talosctl -n $N get kubeletspecs -o yaml   | grep -c 'image: ghcr.io/siderolabs/kubelet:v1.36.0'        # 3
mise exec -- kubectl get configmap -n kube-system talos-bootstrap-manifests-inventory -o jsonpath='{.data}' | python3 -c "import sys,json;print(len(json.load(sys.stdin)))"   # 7
pq 'count%20by%20(job)(kubernetes_build_info%7Bgit_version%3D%22v1.36.0%22%7D)' | tee "$SCR/k-build-pre.txt"
pq 'sum%20by%20(job)(up%7Bjob%3D~%22apiserver%7Ckubelet%7Ckube-scheduler%7Ckube-controller-manager%7Ckube-etcd%22%7D)' | tee "$SCR/k-up-pre.txt"
mise exec -- python3 "$SCR/alerts.py" baseline "$SCR/k-alerts-baseline.json"
mise exec -- flux get kustomizations -A --no-header | awk '$5!="True"' | wc -l | tee "$SCR/k-ks-notready.txt"
mise exec -- flux get helmreleases   -A --no-header | awk '$5!="True"' | wc -l | tee "$SCR/k-hr-notready.txt"
mise exec -- talosctl -n $N get kernelparamstatuses | grep -c ' sys\.' | tee "$SCR/k-sysfs-pre.txt"
mise exec -- talosctl -n $N image list --namespace cri    | grep -cE 'registry\.k8s\.io/kube-(apiserver|controller-manager|scheduler):v1\.36\.5[[:space:]]'   # 9 if §3.7b held
mise exec -- talosctl -n $N image list --namespace system | grep -cE 'ghcr\.io/siderolabs/kubelet:v1\.36\.5[[:space:]]'                                      # 3 if §3.7b held
mise exec -- talosctl version --short                                                        # client v1.14.1, servers v1.14.2
```
**PASS:** `6`, `3`, `7` (a different inventory count = the prune set moved: §3.K4 must be read
action by action); `k-build-pre` 4 jobs × `'3'` (fewer = a scrape job is blind, STOP — §4.7
could then pass on an empty set); `k-up-pre` apiserver 3, kubelet 9, kube-scheduler 3,
kube-controller-manager 3, kube-etcd 3 (*2026-10-05*); `alerts.py` `Watchdog firing: 1`;
`k-sysfs-pre` recorded (*63 on 2026-10-05 with talos-sysfs-power-caps applied; re-read, since a
reboot may have re-read the iGPU card index, §4.1*); the client is within n±1 of the servers
(SOP §13 lesson 6: two minors behind fails `upgrade-k8s`). Pre-pull counts below `9`/`3` are
**not** a STOP — note them and add ~4 min to the clock (§3.K5 pulls).

**3.K2 — Bump the pin.** Anchored BSD sed, not `yq` (`yq -i` strips blank lines).
```bash
sed -i '' -e 's|^kubernetesVersion: v1\.36\.0$|kubernetesVersion: v1.36.5|' kubernetes/bootstrap/talos/talconfig.yaml
git --no-pager diff kubernetes/bootstrap/talos/talconfig.yaml
```
**Expected diff — EXACTLY this** (dry-tested 2026-10-05 on a scratch copy of the current file
with §3.2's `talosVersion: v1.14.2` already applied, 126 lines; a second run is a no-op):
```diff
@@ -3,7 +3,7 @@
 # renovate: datasource=github-releases depName=siderolabs/talos
 talosVersion: v1.14.2
 # renovate: datasource=docker depName=ghcr.io/siderolabs/kubelet
-kubernetesVersion: v1.36.0
+kubernetesVersion: v1.36.5
 
 clusterName: kubernetes
 endpoint: https://192.168.55.10:6443
```
The context line must read `talosVersion: v1.14.2` (§3.7 is committed). Any other `-`/`+` line,
or a `talosVersion` hunk (= §3.7 not on HEAD), is a **STOP** → `git checkout --
kubernetes/bootstrap/talos/talconfig.yaml`, DEFER.

**3.K3 — Re-render the local machine configs** (gitignored, holds machine secrets — copy into
`$SCR` only; never print a non-image line).
```bash
( umask 077; cp -R kubernetes/bootstrap/talos/clusterconfig "$SCR/clusterconfig.pre" )
mise exec -- task talos:generate-config
for n in 01 02 03; do echo "$n $(diff "$SCR/clusterconfig.pre/kubernetes-k8s-nuc14-$n.yaml" kubernetes/bootstrap/talos/clusterconfig/kubernetes-k8s-nuc14-$n.yaml | grep -c '^[<>]')"; done
for n in 01 02 03; do diff "$SCR/clusterconfig.pre/kubernetes-k8s-nuc14-$n.yaml" kubernetes/bootstrap/talos/clusterconfig/kubernetes-k8s-nuc14-$n.yaml | grep '^[<>]' | grep -vc 'image: '; done
diff "$SCR/clusterconfig.pre/kubernetes-k8s-nuc14-01.yaml" kubernetes/bootstrap/talos/clusterconfig/kubernetes-k8s-nuc14-01.yaml | grep '^[<>]' | grep 'image: ' | sed 's/^\([<>]\).*image: /\1 /' | sort
```
**PASS — measured 2026-10-05** by rendering a scratch copy with both bumps (talhelper genconfig,
scratch dir, deleted after) against today's local `clusterconfig/` (which was byte-identical to a
HEAD render): **`12` per node**, **`0` non-image lines** per node, and exactly these 6 old / 6 new
image values: the installer `factory.talos.dev/installer/43b3cbfc…99a3` `:v1.14.1 → :v1.14.2`
(Phase A's bump, never rendered before because Phases A/B do not render) and `kubelet`,
`kube-apiserver`, `kube-controller-manager`, `kube-proxy`, `kube-scheduler` `:v1.36.0 →
:v1.36.5`. Anything else = the render picked up unrelated patch drift: **STOP**, restore with
`cp "$SCR"/clusterconfig.pre/* kubernetes/bootstrap/talos/clusterconfig/`, revert §3.K2, DEFER.
(If someone re-rendered `clusterconfig/` after §3.7, the installer pair is absent and the count
is `10` — acceptable only with `0` non-image lines and the five K8s pairs above.)

**3.K4 — Read-only dry-run against the v1.14.2 nodes.** `--pre-pull-images=false` explicitly:
the pre-pull is NOT gated on `--dry-run` (§1.5 step 2). This is the reading that matters — the
bootstrap manifests are rendered by the nodes' (now v1.14.2) Talos machinery.
```bash
( cd kubernetes/bootstrap/talos && mise exec -- talosctl upgrade-k8s --talosconfig=./clusterconfig/talosconfig --to=v1.36.5 --dry-run --pre-pull-images=false --nodes=192.168.55.11 > "$SCR/k-dryrun.txt" 2>&1; echo "rc=$?" )
grep -c 'Talos version 1.14.2 is compatible with Kubernetes version 1.36.5' "$SCR/k-dryrun.txt"
grep -c 'skipped in dry-run' "$SCR/k-dryrun.txt"
grep '^ < ' "$SCR/k-dryrun.txt" | awk '{print $2}' | sort | uniq -c
grep -E '^ < ' "$SCR/k-dryrun.txt" | grep -ciE 'deleted|created'
```
**PASS:** `rc=0`; compatible count `3` (the string names **1.14.2** — `1.14.1` here would mean a
node is not on the roll's target: STOP); `skipped in dry-run` > 0 (the update lines were
reached); the manifest actions read exactly **`7 configured`**, and the created/deleted grep
prints **`0`** (*2026-10-05 on v1.14.1 nodes: 7 configured / 0*). **Any `deleted` or `created`
action, or a configured object outside the 7 named in §1.5, is a STOP:** the prune set changed
with the Talos version — read every diff in `$SCR/k-dryrun.txt`, revert §3.K2/§3.K3, DEFER; do
not decide a prune in-window.

**3.K5 — Run the upgrade** (repo task, `docs/sops/talos-upgrade.md` §9.4). The task reads
`kubernetesVersion` from the working-tree `talconfig.yaml`, so §3.K2 must be in place.
```bash
(cd kubernetes/bootstrap/talos && mise exec -- talhelper gencommand upgrade-k8s --extra-flags "--to 'v1.36.5'")
# expect: talosctl upgrade-k8s --talosconfig=./clusterconfig/talosconfig --to=v1.36.5 --to 'v1.36.5' --nodes=192.168.55.11;
# CLOCK GUARD at the acting step (a skipped or stale §3.K0 still stops here): needs the GO/extension
# file §3.K0 wrote, and T+EL <= KLIM + 10 (10 = §3.K1..§3.K4's budget).
KL=$(cat "$SCR/k-klim.txt" 2>/dev/null); EL=$(( ($(date -u +%s) - $(cat "$SCR/t-plan-start.txt")) / 60 ))
if [ -n "$KL" ] && [ "$EL" -le $(( KL + 10 )) ]; then
  echo "K5-CLOCK OK (T+$EL <= T+$((KL + 10)))"
  mise exec -- task talos:upgrade-k8s 2>&1 | tee "$SCR/k-upgrade.log"
else
  echo "K5-CLOCK STOP (T+$EL, limit ${KL:-none}+10): do NOT run upgrade-k8s -> §5.5 STOP path, DEFER"
fi
grep -c 'pre-pulling' "$SCR/k-upgrade.log"; grep -c 'successfully updated' "$SCR/k-upgrade.log"
```
**Guard PASS:** `K5-CLOCK OK`. `K5-CLOCK STOP` = nothing ran (dry-tested 2026-10-05 under zsh:
limit 129/T+100 → OK; 129/T+140 → STOP; no `k-klim.txt` → STOP): take §5.5's pre-run STOP path
(restore `talconfig.yaml` + `clusterconfig.pre`) and DEFER. Do not interrupt a running task.
Expected log: 12 `pre-pulling` lines (fast — near no-op after §3.7b), then
`updating "kube-apiserver"`, `"kube-controller-manager"`, `"kube-scheduler"` with `successfully
updated` ×3 each, then `updating kubelet` with `successfully updated` ×3, then `updating
manifests` with 7 `configured`. **Resumable:** on a partial failure (pull timeout, apiserver slow
to Ready) re-run the same task; components already on v1.36.5 are skipped (`staticPodImage`
returns `errUpdateSkipped`). **Never** reboot or `apply-config` a node to unstick it; read
`talosctl -n <ip> logs kubelet` / `talosctl -n <ip> containers -k` first (§5.5). etcd is not
touched by this phase, so talos-upgrade §11.4 etcd recovery is never the answer here.

**3.K6 — Verify: run §4.7 in full** (CONTENTS ASSERTIONS, then the 10-min soak). FAIL → §5.5.

**3.K7 — Commit the pin — after §4.7 PASS and AFTER §5.4's freeze check** (§5.4 asserts
`freeze-sha..origin/main` is empty, so this push must come after it).
```bash
MSG="$SCR/k-commit-msg.txt"
printf '%s\n' "feat(talos): kubernetesVersion v1.36.0 -> v1.36.5 (plan talos-linux-1.14.2, Phase K)" "" \
  "Applied with task talos:upgrade-k8s after the v1.14.2 node roll; verified per plan section 4.7." "" \
  "<executing session's attribution lines>" > "$MSG"
git commit --only kubernetes/bootstrap/talos/talconfig.yaml -F "$MSG"
git log -1 --format=%s; git show --stat HEAD     # subject is yours; exactly talconfig.yaml, one -/+ pair
git push
```
Flux does not reconcile `kubernetes/bootstrap/talos/`; this push is the record that keeps git in
step with the cluster. Then §3.12.

## 4) Verification

### 4.1 — Per node, right after it returns (with §3.10/§3.11)

```bash
mise exec -- talosctl read /proc/cmdline -n <node-ip> | tr ' ' '\n' | grep -E 'hugepages|i915|intel_iommu|mitigations|init_on_alloc' | sort | tr '\n' ' ' > "$SCR/cmdline-post-<NN>.txt"
cmp -s "$SCR/cmdline-<NN>.txt" "$SCR/cmdline-post-<NN>.txt" && echo CMDLINE-SAME || { echo CMDLINE-CHANGED; diff "$SCR/cmdline-<NN>.txt" "$SCR/cmdline-post-<NN>.txt"; }
mise exec -- talosctl read /proc/meminfo -n <node-ip> | grep HugePages_Total
```
**PASS:** `CMDLINE-SAME` against the §2.8 file (`<NN>` = 11/12/13) and `HugePages_Total: 1024`.
Args silently vanishing across an upgrade is talos-upgrade.md lessons #2/#3/#13; a changed
set = re-run `task talos:upgrade-node` for that IP before moving on.

**Only if `talos-sysfs-power-caps` has executed** (its SysfsConfig is live: `mise exec -- talosctl -n <node-ip> get
kernelparamstatuses` lists `sys.class/powercap/...` rows) - after each node returns, take `sysfs-readback.py` from
that plan's Appendix A (its §2 awk loop extracts it; from git history if the plan file was retired) into `$SCR/`
and run `mise exec -- python3 "$SCR/sysfs-readback.py" <node-ip> caps --status` -> **PASS:** `GATE_PASS ... keys=21
mismatches=0`. **If `talos-power-tuning-ab` has executed** (2026-10-05 correction, its §6): the 2026-10-04 `caps`
values are no longer the committed ones, so use THAT plan's read-back instead:
`mise exec -- python3 "$SCR/ab-readback.py" <node-ip> <winner> --status` (extract `ab-readback.py` from its Appendix,
`<winner>` = the variant its execution record names; PASS `GATE_PASS ... keys=21|22 mismatches=0`). EPP 64 reads back
as `balance_performance` there by design. This is the first boot after the caps: Talos must re-apply all 21 keys. A `MISMATCH` on the
`class/drm/cardN/gt/gt0/rps_max_freq_mhz` key with `ERR(...no such file...)` means the iGPU card index moved across
the reboot (nuc14-03 had i915 on card1 because simpledrm took card0): re-measure with
`mise exec -- talosctl -n <node-ip> list /sys/class/drm`, fix that node's `patches/node/k8s-nuc14-NN-sysfs-igpu.yaml`
in a follow-up apply (no reboot) - not a reason to roll back the node. Any other mismatch (RAPL/EPP not re-applied)
-> STOP before the next node and report.

**CANARY GO/NO-GO (after the first node).** §3.10 (incl. `nodegate.py` and `probe.py`
PASS — plus the in-window bumped-term control of §2.0 on this probe log printing FAIL),
§3.10a, §3.11, the cmdline check, §4.3 CONTENTS ASSERTIONS 4 and 5 on the canary, and pods
running on it again (`kubectl get pods -A --field-selector spec.nodeName=<canary>`). **Time the
canary** (upgrade start → §3.11 PASS) and re-plan the other two from it. Any failure: **roll
the canary back (§5.1)** and stop.

### 4.2 — Storage: the iSCSI record trap (after the LAST node)

```bash
mise exec -- kubectl get volumes -n storage -o custom-columns='NODE:.status.currentNodeID' --no-headers | sort | uniq -c
```
**PASS:** all three node names with a non-trivial count. A node at 0 while the others hold
dozens = stale iSCSI records (talos-upgrade.md §9): remove only unparseable records under
`/var/lib/iscsi/nodes` on that node, check ALL of them; do not reboot/drain/reset; delete no
PV/PVC/Volume/Replica.

### 4.3 — CONTENTS ASSERTIONS

> **CONTENTS ASSERTION 1 (storage — a real write/read round-trip through a mounted Longhorn
> PVC on a ROLLED node).** Longhorn `healthy` says nothing about whether a volume can be used
> (§4.2 is the proof). Measured by writing and reading back a file; compared to the string
> written. Target verified 2026-10-01: `deploy/pgadmin` (ns `databases`), PVC `pgadmin-data`
> (`longhorn-static`, Bound) at `/var/lib/pgadmin`.
> ```bash
> mise exec -- kubectl -n databases get pod -l app=pgadmin -o jsonpath='{.items[0].spec.nodeName}{"\n"}'
> mise exec -- kubectl -n databases exec deploy/pgadmin -- sh -c \
>   'echo talos-1142-probe-$$ > /var/lib/pgadmin/.probe && cat /var/lib/pgadmin/.probe && rm /var/lib/pgadmin/.probe'
> ```
> **PASS:** the string returns identical from a pod on a rolled node. Empty read, I/O error,
> read-only FS = FAIL even with every volume healthy. If pgadmin sits on an un-rolled node, use
> any other RWO-PVC pod on a rolled node from §4.2's table.

> **CONTENTS ASSERTION 2 (monitoring — series still arrive, with a floor).**
> ```bash
> mise exec -- kubectl get --raw "$P/targets" | python3 -c "
> import sys,json
> t=json.load(sys.stdin)['data']['activeTargets']
> print('targets',len(t),'up',sum(1 for x in t if x['health']=='up'))
> for x in t:
>     if x['health']!='up': print('  DOWN',x['labels'].get('job'),x['labels'].get('instance'))"
> cat "$SCR/targets-baseline.txt"
> mise exec -- kubectl get --raw "$P/query?query=count(etcd_server_has_leader)"
> mise exec -- kubectl get --raw "$P/rules" | python3 -c "
> import sys,json; g=json.load(sys.stdin)['data']['groups']
> print('groups',len(g),'rules',sum(len(x['rules']) for x in g))"
> cat "$SCR/rules-baseline.txt"
> ```
> **PASS:** target total **≥** the §2.8 total and up == total (a smaller total is a FAIL — a
> vanished target reads as 100 % up); the etcd query returns `"value":[…,"3"]` (the floor);
> groups/rules equal the §2.8 line.

> **CONTENTS ASSERTION 3 (routing — real HTTP through Envoy, not Gateway status).**
> ```bash
> mise exec -- kubectl get gateway -A
> mise exec -- kubectl get httproute -A --no-headers | wc -l; cat "$SCR/httproutes-baseline.txt"
> mise exec -- kubectl get httproute -A -o json | python3 -c "
> import sys,json
> bad=[(r['metadata']['namespace'],r['metadata']['name'],c['type']) for r in json.load(sys.stdin)['items']
>      for p in r.get('status',{}).get('parents',[]) for c in p.get('conditions',[])
>      if c['type'] in ('Accepted','ResolvedRefs') and c['status']!='True']
> print('routes NOT Accepted/ResolvedRefs:',len(bad)); [print('  ',b) for b in bad]"
> INT_HOST=$(sed -n 1p "$SCR/probe-hosts.txt"); EXT_HOST=$(sed -n 2p "$SCR/probe-hosts.txt")
> curl -sS -o /dev/null -w 'internal %{http_code} %{size_download}\n' -H "Host: $INT_HOST" https://192.168.55.103/ -k
> curl -sS -o /dev/null -w 'external %{http_code} %{size_download}\n' -H "Host: $EXT_HOST" https://192.168.55.104/ -k
> cat "$SCR/curl-baseline.txt"
> ```
> **PASS:** both Gateways `PROGRAMMED=True`; route count equals the §2.9 file; `routes NOT
> Accepted/ResolvedRefs: 0`; both curls 2xx with a non-zero body of the same order as the baseline.

> **CONTENTS ASSERTION 4 (the new kernel's block layer is actually live — WBT, §1.2).** The tag
> `v1.14.2` says which image booted; this says the behaviour change the plan priced is really
> on the etcd disk. Measured on every rolled node; compared to `$SCR/wbt-pre.txt` (NotFound on
> all three on 2026-10-01).
> ```bash
> for ip in 11 12 13; do echo -n "$ip wbt="; mise exec -- talosctl -n 192.168.55.$ip read /sys/block/nvme0n1/queue/wbt_lat_usec 2>&1 | head -1; done | tee "$SCR/wbt-post.txt"
> cat "$SCR/wbt-pre.txt"
> ```
> **PASS:** on every rolled node the read returns a **number** (the attribute exists = kernel
> built with `CONFIG_BLK_WBT`), where `wbt-pre.txt` showed `NotFound`. Record the value; the
> kernel's non-rotational default is expected to be `2000` µs — a `0` means WBT is built but
> disabled (note it, not a FAIL; the etcd gates are what judge the effect). Still `NotFound` on
> a node reporting `Talos (v1.14.2)` = the node is not running the kernel this plan priced:
> FAIL, stop, investigate before the next node. **Negative control:** `wbt-pre.txt` itself —
> the same read printed NotFound on v1.14.1, so this assertion cannot pass on the old kernel.
> **Third outcome — `invalid argument` (EINVAL):** linux v6.18 `block/blk-sysfs.c`
> `queue_wb_lat_show()` returns `-EINVAL` when the attribute EXISTS but no WBT rq_qos is
> attached to this queue (`!wbt_rq_qos(q)`), and `0` only when attached-but-disabled. So
> `EINVAL` = kernel built with WBT (the image is right) but WBT not active on `nvme0n1` — the
> behaviour change §1.2 priced is absent on that node. Not a node defect and not a rollback
> trigger: record it, it is a PASS for "the priced kernel booted" and a note that §4.6's
> before/after comparison measures nothing for that node. It is distinguishable from
> `NotFound` (old kernel) by the error text — read the line, do not reduce it to "not a number".

> **CONTENTS ASSERTION 5 (`/etc/hosts` still carries the node's own name — the `c792fa4`
> render path).** v1.14.2 moved /etc/hosts rendering into `etcrender.Hosts`, which silently
> DROPS the hostname line when the name fails `ValidateDNSNameChars`. Measured 2026-10-01 on
> v1.14.1: line 2 of each node's `/etc/hosts` is `<node-ip> k8s-nuc14-0N`.
> ```bash
> for n in 1 2 3; do echo -n "1${n}: "; mise exec -- talosctl -n 192.168.55.1${n} read /etc/hosts | grep -cE "^192\.168\.55\.1${n}[[:space:]]+k8s-nuc14-0${n}\$"; done
> # negative control (crossed digits) — MUST print 0:
> mise exec -- talosctl -n 192.168.55.11 read /etc/hosts | grep -cE '^192\.168\.55\.11[[:space:]]+k8s-nuc14-02$'
> ```
> **PASS:** `1` for every rolled node, and the crossed-digit control prints `0` (dry-run
> 2026-10-01 under zsh: `1 1 1` / `0`). Braced `${n}`: in zsh `$n[...]` is an array subscript
> and aborts with `bad output format specification` (hit while dry-running this line).
> (`grep -E` with `[[:space:]]`, not `\s` — BSD tools.)

### 4.4 — Whole-cluster verification (end of window; talos-upgrade.md §15.1)

```bash
# 1. every node on the target
mise exec -- kubectl get nodes -o 'custom-columns=N:.metadata.name,OS:.status.nodeInfo.osImage,K:.status.nodeInfo.kernelVersion,CR:.status.nodeInfo.containerRuntimeVersion,KL:.status.nodeInfo.kubeletVersion'
#    PASS: 3x Talos (v1.14.2), 6.18.54-talos, containerd://2.3.6, v1.36.0  (kubelet moves only in Phase K, AFTER this; §4.7 then asserts v1.36.5)
# 2. etcd: 3 members, no LEARNER, empty ERRORS, converged, PROTOCOL 3.7.1 on ALL (unchanged)
mise exec -- talosctl -n 192.168.55.11,192.168.55.12,192.168.55.13 etcd status
# 3. VIP on exactly one node
for ip in 192.168.55.11 192.168.55.12 192.168.55.13; do echo -n "$ip vip="; mise exec -- talosctl -n $ip get addresses 2>/dev/null | grep -c '192.168.55.10/32'; done
# 4. no pod left behind — phase AND readiness
mise exec -- kubectl get pods -A --field-selector status.phase!=Running,status.phase!=Succeeded
mise exec -- python3 "$SCR/notready.py" compare "$SCR/notready-baseline.json"
# 5. Flux
mise exec -- flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
mise exec -- flux get helmreleases   -A | awk 'NR==1 || $5 != "True"'
# 6. Longhorn gate + §4.2
mise exec -- python3 "$SCR/lh_gate.py" gate "$SCR/lh-baseline.json"
# 7. all five CONTENTS ASSERTIONS (§4.3) on all three nodes
# 8. DaemonSets desired == ready everywhere; device plugins on every node
mise exec -- kubectl get ds -A | awk 'NR==1 || $4 != $6'
mise exec -- kubectl get nodes -o custom-columns='N:.metadata.name,GPU:.status.allocatable.gpu\.intel\.com/i915,NPU:.status.allocatable.npu\.intel\.com/accel'
# 9. etcd after the roll — leader window from the THIRD node's start
LW="$(( ($(date -u +%s) - $(cat "$SCR/node3-start.txt")) / 60 ))m"; echo "leader window $LW"
mise exec -- python3 "$SCR/etcdgate.py" --lookback 10m --leader-window "$LW" --allow-file "$SCR/leader-allow.log"
mise exec -- python3 "$SCR/etcdstat.py" converged
# 10. hwmon chip set vs §2.8 (kernel bump; talos-upgrade.md §14.6)
mise exec -- python3 "$SCR/hwmon.py" compare "$SCR/hwmon-baseline.json"
# 11. alerts vs the §2.8 SET — after >= 15 min settle
mise exec -- python3 "$SCR/alerts.py" compare "$SCR/alerts-baseline.json"
```
**PASS:** 1–3 as annotated; **4** the field-selector query prints nothing AND `notready.py`
`VERDICT PASS` (a CrashLoopBackOff pod still reports `Running` — the phase query alone is a
shape check; its mid-drain positive control ran at §3.9); **5** header rows only; **6** `VERDICT
PASS`; **7** all five; **8** the DaemonSet awk prints only the header, every node `5`/`1`;
**9** both `VERDICT PASS`; **10** `VERDICT PASS` — a changed chip set is a FAIL **to be acted
on, not absorbed**: find every consumer pinning a chip name (Uptime Kuma "Cluster GPU Temp",
Grafana panels, PrometheusRules), record a finding, fix it (F-b7f34c39 is the precedent);
**11** `Watchdog firing: 1` and `VERDICT PASS`, sustained ≥ 15 min after the last node returned
(talos-upgrade.md §15.2 lists the transients that may appear earlier and their "transient if"
conditions; anything outside it is a regression).

**CONTROL lines — the instruments the gates read (`plan-premises.py --controls`):**

CONTROL: metric ALERTS — `alerts.py` reads the firing set via `/api/v1/alerts`; asserts the Watchdog (chart-default rule, so not a repo PrometheusRule and not a separate `alertname` CONTROL line — `--controls` checks alertnames against repo manifests only) firing exactly once, and no alertname outside the §2.8 set.
CONTROL: metric etcd_server_has_leader — §4.3 CA2 asserts `count(...) == 3`; §3.10 pattern (ii) condition 2 asserts `min_over_time(...[15m]) = 1` on survivors when Prometheus was not on the drained node.
CONTROL: metric etcd_server_leader_changes_seen_total — `nodegate.py` (survivors +0, or +1 when the rolled node was leader) and `etcdgate.py` (no unexplained change in the window).
CONTROL: metric etcd_disk_wal_fsync_duration_seconds_bucket — `etcdgate.py` worst 5m-p99 < 50 ms over 1h (§2.3b) / 10m (§3.10b, §4.4 #9); exactly 3 series.
CONTROL: metric etcd_disk_backend_commit_duration_seconds_bucket — same gate as above for backend commit.
CONTROL: metric container_fs_writes_bytes_total — `etcdgate.py` kustomize-controller (`container="manager"`) < 5 MB/s over 10 min; no series = FAIL.
CONTROL: metric node_network_carrier_changes_total — `nodegate.py`: survivors' `device=~"en.*"` unchanged across each reboot.
CONTROL: metric node_hwmon_temp_celsius — `hwmon.py`: `count by (chip)` identical before/after the kernel bump; empty = FAIL.
CONTROL: metric etcd_server_version — premise `etcd-protocol-3.7` (one `server_version` group, 3.7.x, count 3).
CONTROL: metric up — §4.3 CA2: target total ≥ the §2.8 total, all up.

### 4.5 — Workload isolation NOT silently enabled

```bash
for ip in 192.168.55.11 192.168.55.12 192.168.55.13; do
  echo -n "$ip securityprofileconfig="; mise exec -- talosctl -n $ip get machineconfig -o yaml | grep -ci 'securityprofileconfig'
  echo -n "   positive-control(machine:)="; mise exec -- talosctl -n $ip get machineconfig -o yaml | grep -ci 'machine:'
done
```
**PASS:** `0` and `≥ 1` on all three. `sandboxd` running proves nothing on v1.14 (it starts
unconditionally since `c7e2524`); the config document is the property.

### 4.6 — Record (not gate) the WBT before/after on etcd tail latency

```bash
mise exec -- kubectl get --raw "$P/query?query=max_over_time(histogram_quantile(0.99,%20sum%20by%20(instance,le)%20(rate(etcd_disk_wal_fsync_duration_seconds_bucket%5B5m%5D)))%5B1h:1m%5D)"
```
Run once ≥ 1 h after the last node (or at the next sweep) and write the per-member worst p99 next
to `$SCR/etcdgate-2.3.txt`'s pre-roll line in the window report. It is a recorded comparison for
the WBT change (§1.2), not a gate: §3.10b/§4.4 #9 already hold the 50 ms floor.

### 4.7 — Phase K verification (after §3.K5; `pq`, `$P`, `$N` from §3.K1)

> **CA-K1 — every control-plane component and kubelet REPORTS v1.36.5** (the binaries' own
> `kubernetes_build_info`, independent of what Talos configured). Allow 2 scrape intervals.
> ```bash
> pq 'count%20by%20(job)(kubernetes_build_info%7Bgit_version%3D%22v1.36.5%22%7D)'
> pq 'count(kubernetes_build_info)'
> pq 'count%20by%20(kubelet_version)(kube_node_info)'
> mise exec -- kubectl get nodes -o 'custom-columns=N:.metadata.name,OS:.status.nodeInfo.osImage,KL:.status.nodeInfo.kubeletVersion'
> ```
> **PASS:** 4 jobs (apiserver, kubelet, kube-scheduler, kube-controller-manager) each `'3'`;
> total `'12'`; `kube_node_info` one group `v1.36.5` = `'3'`; nodes `Talos (v1.14.2)` +
> `v1.36.5` ×3. **Fails on:** a component left on v1.36.0 (`<4` jobs or a job `<3`), a blind
> scrape (total `<12`, or result count `0` — empty is FAIL; premise `build-info-scraped-12` and
> §3.K1's `k-build-pre` prove the series exist).

> **CA-K2 — Talos holds the new images and nothing else in the machine config moved.**
> ```bash
> mise exec -- talosctl -n $N get apiserverconfigs -o yaml | grep -c 'image: registry.k8s.io/kube-apiserver:v1.36.5'
> mise exec -- talosctl -n $N get kubeletspecs -o yaml   | grep -c 'image: ghcr.io/siderolabs/kubelet:v1.36.5'
> mise exec -- kubectl -n kube-system get pods -l tier=control-plane -o 'custom-columns=N:.metadata.name,I:.spec.containers[0].image,R:.status.containerStatuses[0].ready'
> mise exec -- talosctl -n $N get kernelparamstatuses | grep -c ' sys\.'; cat "$SCR/k-sysfs-pre.txt"
> ```
> **PASS:** `6` and `3` (the same readers printed `6`/`3` for v1.36.0 on 2026-10-05, so they can
> count); all 9 control-plane pods `:v1.36.5` and `true`; the `sys.*` count equals
> `k-sysfs-pre.txt`. **Fails on:** a node left on v1.36.0 (`<6`/`<3`), or a patch that clobbered
> the SysfsConfig documents (a lower `sys.*` count would silently undo talos-sysfs-power-caps /
> talos-power-tuning-ab).

> **CA-K3 — the kubelet restarts did not restart workload containers.** Lists every container
> whose last termination falls inside Phase K. Dry-tested 2026-10-05 (k8s-1.36.5 §4.3) over the
> previous 24 h: 315 pods read, 3 real hits (the 2026-10-04 multidoc apply's control-plane
> restarts), so it can fail.
> ```bash
> cat > "$SCR/restarts.py" <<'EOF'
> import sys, json, subprocess, datetime as dt
> t0 = dt.datetime.fromisoformat(sys.argv[1].replace("Z", "+00:00"))
> t1 = dt.datetime.fromisoformat(sys.argv[2].replace("Z", "+00:00"))
> pods = json.loads(subprocess.run(["kubectl", "get", "pods", "-A", "-o", "json"], check=True, capture_output=True, text=True).stdout)["items"]
> if not pods:
>     sys.exit("ABORT: 0 pods read - instrument empty")
> hits = []
> for p in pods:
>     for cs in (p.get("status", {}).get("containerStatuses") or []):
>         term = (cs.get("lastState") or {}).get("terminated")
>         if not term or not term.get("finishedAt"):
>             continue
>         f = dt.datetime.fromisoformat(term["finishedAt"].replace("Z", "+00:00"))
>         if t0 <= f <= t1:
>             hits.append(f'{p["metadata"]["namespace"]}/{p["metadata"]["name"]}/{cs["name"]} reason={term.get("reason")} exit={term.get("exitCode")} at={term["finishedAt"]}')
> print(f"pods_read={len(pods)} container_restarts_in_window={len(hits)}")
> for h in hits:
>     print("  " + h)
> EOF
> mise exec -- python3 "$SCR/restarts.py" "$(cat "$SCR/k-t0.txt")" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" | grep -v -E 'kube-system/kube-(apiserver|controller-manager|scheduler)-k8s-nuc14-'
> ```
> **PASS:** `pods_read` in the 300s and no hit left after excluding the control-plane static
> pods. Per hit: caused by this phase, or a known crash-looper (did the same container restart in
> the hour before `k-t0`)? A cluster-wide wave of hits is a FAIL → §5.5. (`t0` is Phase K's own
> start, so Phase B's drain/reboot restarts are outside the window by construction.)

**Health floor after a 10-minute soak** from the end of §3.K5 (`sleep` is not allowed in the
agent shell; wait with Monitor or the window agent's clock):
```bash
KW="$(( ($(date -u +%s) - $(cat "$SCR/k-t0.epoch")) / 60 ))m"; echo "phase K window $KW"
pq 'sum%20by%20(job)(up%7Bjob%3D~%22apiserver%7Ckubelet%7Ckube-scheduler%7Ckube-controller-manager%7Ckube-etcd%22%7D)'; cat "$SCR/k-up-pre.txt"
mise exec -- python3 "$SCR/etcdgate.py" --lookback 10m --leader-window "$KW" --allow-file "$SCR/leader-allow.log"
mise exec -- python3 "$SCR/etcdstat.py" converged
mise exec -- flux get kustomizations -A --no-header | awk '$5!="True"' | wc -l; cat "$SCR/k-ks-notready.txt"
mise exec -- flux get helmreleases   -A --no-header | awk '$5!="True"' | wc -l; cat "$SCR/k-hr-notready.txt"
mise exec -- python3 "$SCR/lh_gate.py" gate "$SCR/lh-baseline.json"
mise exec -- python3 "$SCR/alerts.py" compare "$SCR/k-alerts-baseline.json"
mise exec -- kubectl get csinodes -o 'custom-columns=N:.metadata.name,D:.spec.drivers[*].name'
```
**PASS:**
- `up` per-job sums equal `k-up-pre.txt` (a 0 = a scrape job lost a target).
- `etcdgate.py` `VERDICT PASS` over Phase K's window: no leader change (nothing in Phase K
  explains one — do not add a `leader-allow.log` line for it), fsync/commit p99 < 50 ms, kc < 5
  MB/s. The third node's restart is > 45 min before `k-t0`, so every member counts for the whole
  window. `etcdstat.py` PASS.
- Flux not-Ready counts ≤ the `k-*-notready.txt` baselines. This is the SSA path 1.36.3 fixed, so
  a new `422`-style apply error is a regression signal, not noise.
- `lh_gate.py` `VERDICT PASS` against the §2.5 recording (the kubelet restarts re-registered the
  CSI plugins without disturbing a replica).
- `alerts.py` `Watchdog firing: 1` and `VERDICT PASS` vs `k-alerts-baseline.json`. A new
  `KubeVersionMismatch`, `KubeAPIDown`, `KubeletDown`, `etcd*` or `TargetDown` is a FAIL.
- Every CSINode lists both `driver.longhorn.io` and `smb.csi.k8s.io` (a missing driver = a CSI
  node plugin did not re-register with its restarted kubelet).

CONTROL: metric kubernetes_build_info — §4.7 CA-K1: `count by (job)` at git_version v1.36.5 = 4×3, total 12; empty = FAIL (premise build-info-scraped-12 + §3.K1 prove 12 series exist).
CONTROL: metric kube_node_info — §4.7 CA-K1: single kubelet_version group v1.36.5 = 3.

## 5) Rollback

**Rollback is per phase.** Phase B (OS) → §5.1–§5.3; Phase K (Kubernetes) → §5.5. They are
independent: a Phase K rollback never touches the OS, and a later per-node OS rollback under K8s
1.36.5 is supported (§1.5: v1.14.1 accepts 1.32–1.37.99; measured `1.14.1 is compatible with
1.36.5`). Never roll back both at once — Phase K first if both are wanted.

**This hop crosses nothing forward-only** — etcd stays 3.7.1 (storage 3.7.0), Phase B writes no
machine config, Phase K is a patch hop with no storage-version migration, and v1.14.2 → v1.14.1
is inside upstream's downgrade window (`MaximumHostDowngradeVersion 1.16.0`). Rolling a node back is therefore real at ANY
point of the roll — unlike talos-1.14.1, whose etcd 3.6 → 3.7 move made it one-way past the
canary. It is still **another reboot cycle per node (~25 min incl. its Longhorn gate)**, never a
`git revert` alone: the commit is inert.

### 5.1 — Per-node rollback — DRAINED by default; bare `talosctl rollback` only for a NotReady node

**`talosctl rollback` does NOT cordon or drain.** Measured in v1.14.2 source: `Server.Rollback`
(`internal/app/machined/internal/server/v1alpha1/v1alpha1_server.go`) runs
`runtime.SequenceReboot`, and `Sequencer.Reboot` (`…/runtime/v1alpha1/v1alpha1_sequencer.go`
L257–271) is `StopAllPods → preShutdown → stopAll → reboot` — no `CordonAndDrainNode` phase
(that phase is in `Upgrade`, L453–455, and `Shutdown`, L370–372, only). On a `Ready` node a bare
rollback is therefore a **hard reboot under load**: Longhorn engines on it die un-migrated
(every attached volume with a replica-less engine there goes degraded/faulted for the reboot),
envoy/authentik/coredns pods vanish without PDB protection. So:

**(5.1a) Node is `Ready` (the normal case — CA/DaemonSet/WBT defect found after it returned):**
roll it back with a **drained downgrade-upgrade** to the exact v1.14.1 image. Do NOT use
`task talos:upgrade-node` — it reads `talosVersion` from `talconfig.yaml`, which says v1.14.2
until §5.3. Run talosctl directly, with the same §3.9 FREEZE-HELD check, nodegate snap and §3.9a
survivor probe before it:
```bash
mise exec -- talosctl -n <node-ip> version --short          # Tag: v1.14.2
mise exec -- talosctl -n <node-ip> upgrade --timeout=10m \
  --image factory.talos.dev/installer/43b3cbfc2957259b4588d362709d47387607901d4d3506c1ea46d7ea74cb99a3:v1.14.1
mise exec -- talosctl -n <node-ip> version --short          # Tag: v1.14.1 after it returns
```
`Upgrade` cordons + drains, so it waits on `storage/instance-manager-<hash>` exactly like §3.9
(normal; same engine-count watch, same rule: never delete PDBs, never `--drain=false` up front;
on a drain **timeout** only, uncordon then delete the `Pending` pods). v1.14.1 is inside the
downgrade window (`MaximumHostDowngradeVersion 1.16.0`) and the factory serves it (§1.4: `200`).
Price: same as a roll node, ~25–30 min incl. §3.11.

**(5.1b) Node is NotReady / API unreachable (kubelet/CRI never came up — nothing to drain):**
bare rollback, **labelled a hard reboot**:
```bash
mise exec -- talosctl -n <node-ip> version --short          # Tag: v1.14.2 (apid answers even if kubelet does not)
mise exec -- talosctl rollback --nodes <node-ip>            # HARD REBOOT: no cordon, no drain
mise exec -- talosctl -n <node-ip> version --short          # Tag: v1.14.1 after it returns
```
Price it as a full §3.11 Longhorn recovery, not an incremental rebuild: the node has been out
for the whole failed boot plus this one, so expect replicas past the 10-min tripwire to be
FULL rebuilds (~20+ min at concurrency 8, possibly the 25-min budget, §14.4 failed-replica
procedure). A bare rollback on a `Ready` node is never the shortcut.

Either way, then re-run §3.10 (with a fresh §3.9 snap + §3.9a probe around the reboot), §3.11
and §4.1 for that node. **(b) is one partition deep:** it returns to the image booted before the
last upgrade (v1.14.1) — nothing further; (a) writes v1.14.1 as a fresh install. **Canary**: roll it back, stop, leave the other two on
v1.14.1 — the cluster is exactly where it started; then §5.3. **Later nodes**: roll back the
broken node only, or all rolled nodes one at a time with the full gate set between them; a mixed
v1.14.1/v1.14.2 cluster is a supported transient (same etcd, same K8s).

**When rollback is the WRONG answer:** an election / fsync spike during a drain that passes
pattern (ii) is the 09-27 behaviour, not a v1.14.2 regression — rolling back is another drain
and makes it worse. Roll back for a node-level defect (kubelet/CRI not starting, a DaemonSet
failing on the new kernel, a CONTENTS ASSERTION failing, WBT demonstrably hurting etcd per
§3.10b on a rolled node while un-rolled ones are fine).

### 5.2 — Stop, don't unwind (time, or "something looks off")

A part-rolled cluster is a supported transient. Stop where you are, finish §4.4 on the mix, §5.4,
reschedule the rest. **Quorum lost and not coming back** is disaster recovery, operator
decision, never improvised: restore from the §3.8a snapshot via talos-upgrade.md §11.4 /
`docs/sops/etcd.md` §4.4 (`reset --system-labels-to-wipe=EPHEMERAL` destroys every Longhorn
replica on that node; restore volumes from the §2.6-verified backups per `docs/sops/backup.md`
and `docs/sops/disaster-recovery.md`; no `--recover-skip-hash-check`).

### 5.2a — Window aborted BEFORE the canary (Phase A pushed, no node touched)

Phase A's §3.7 commit (`talosVersion: v1.14.2` + deny-rule text) is pushed before the window
and is Flux-inert, but it is NOT harmless to leave: `task talos:upgrade-node` and every later
reader of `talconfig.yaml` (the migration plan's re-review, the version check, the next
planner) would take v1.14.2 as the cluster state. If the window ends — for any reason —
before §3.9a's `talos:upgrade-node` was issued on the canary:
`kubectl get nodes -o wide` shows `Talos (v1.14.1)` on all three (prove it, do not assume),
then run **§5.3** to revert Phase A, then **§5.4** (the freeze may already be up). Record
the abort reason in the window report. The §3.7b pre-pulled v1.36.5 images need no revert: they
are referenced by nothing and are reused by whichever plan later runs Phase K (`talosctl image
remove` exists if the operator wants them gone; not required). **Alternative that avoids this path:** run Phase A
the same morning, immediately before §2.0b, at the cost of +25 min in-window (§7 already
prices that case: stop after the canary + 2nd node unless the operator extends).

### 5.3 — Reverting the git commit (only after no node runs v1.14.2)

If Phase K ran, it stays (K8s 1.36.5 on v1.14.1 is supported); only the `talosVersion` line is
reverted. If §3.K7 is on top of §3.7, `git revert` of §3.7 still applies cleanly (different
lines) — check the `git status` line below.

```bash
git revert --no-commit <sha-of-3.7>          # talosVersion back to v1.14.1 + the reason text
git status --short                           # exactly talconfig.yaml, auto-update-policy.yaml
MSG="$SCR/talos-1142-revert-msg.txt"; printf 'Revert Talos v1.14.2 node config\n\nPlan: talos-linux-1.14.2 (section 5.3)\n' > "$MSG"
git commit --only kubernetes/bootstrap/talos/talconfig.yaml runbooks/auto-update-policy.yaml -F "$MSG"
git log -1 --format=%s; git show --stat HEAD
git push
```
**Confirm the cluster is back by the NODES, never the repo:** `kubectl get nodes -o wide` shows
`Talos (v1.14.1)` / `6.18.51-talos` on every node, plus §3.11 and §4.3 CA1–CA3. If §3.12 already
ran, revert `.mise.toml` too (a client one patch ahead of the servers is tolerated, but the pin
must track the cluster).

### 5.4 — END OF WINDOW: lift the push freeze. EVERY exit path.

```bash
git fetch -q origin && git log --oneline "$(cat "$SCR/freeze-sha.txt")"..origin/main     # MUST be empty
while read -r ns name; do mise exec -- flux resume image update "$name" -n "$ns"; done < "$SCR/iua-main.txt"   # ONLY ours
mise exec -- kubectl get imageupdateautomation -A -o json | python3 -c "
import sys, json
live = {(i['metadata']['namespace'], i['metadata']['name']): bool(i['spec'].get('suspend')) for i in json.load(sys.stdin)['items']}
def rows(p): return [tuple(l.split()[:2]) for l in open(p) if l.strip()]
bad = 0
for k in rows('$SCR/iua-main.txt'):
    ok = k in live and live[k] is False; bad += not ok; print('resumed   ', *k, 'suspend=%s' % live.get(k), 'OK' if ok else 'FAIL')
for k in rows('$SCR/iua-presusp.txt'):
    ok = k in live and live[k] is True;  bad += not ok; print('git-held  ', *k, 'suspend=%s' % live.get(k), 'OK' if ok else 'FAIL')
print('VERDICT', 'PASS' if bad == 0 else 'FAIL')"
mise exec -- kubectl get imageupdateautomation -A -o custom-columns='NS:.metadata.namespace,NAME:.metadata.name,SUSPEND:.spec.suspend,READY:.status.conditions[0].status' --no-headers
mise exec -- flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
kill $PROBE $L1 $L2 2>/dev/null; true
```
**PASS:** the `git log` is empty (else name the commits/session to the operator); `VERDICT PASS`
= **every** row of `iua-main.txt` reads `suspend=False` (a forgotten suspension silently stops
that app's image bumps while reading `Ready=True`) **AND every row of `iua-presusp.txt` still
reads `suspend=True`** (the absenty git holds survived — resuming them would undo an operator
decision made in git); the resumed rows Ready `True`; Kustomizations header only. **This gate
can fail both ways:** before the resume loop it prints `FAIL` on every `iua-main.txt` row (they
are `True` then) — run it once before the loop on the first use as the control; a stray
`flux resume` on an absenty row prints `git-held … suspend=False FAIL`. Tell the other sessions
the freeze is over. Only then §3.K7 (if Phase K ran), §3.12 and the window agent's bookkeeping
commits.

### 5.5 — Phase K rollback: Kubernetes v1.36.5 → v1.36.0 (~25 min, no reboot)

**When:** a §3.K2–§3.K4 STOP (nothing changed in the cluster yet: `git checkout --
kubernetes/bootstrap/talos/talconfig.yaml`, `cp "$SCR"/clusterconfig.pre/*
kubernetes/bootstrap/talos/clusterconfig/`, then DEFER as in §3.K0), or a §4.7 FAIL attributable
to the new version. **Supported:** the go-kubernetes path table keys on major.minor and lists
`"1.36->1.36"`; `--from` is auto-detected as the lowest running version, so `--to 1.36.0` is
accepted. Upstream does not certify patch downgrades in so many words, but nothing forward-only
happens in this hop (no API added/removed, no storage-version migration, no etcd change). The
SSA inventory annotation on the 7 bootstrap objects stays — harmless, and what a 1.36.0 run also
writes.

```bash
cd /Users/mu/code/cberg-home-nextgen
# 1) restore the pin — uncommitted case (§3.K7 not yet run):
git checkout -- kubernetes/bootstrap/talos/talconfig.yaml
#    ... or, if §3.K7 was already pushed:
#    git revert --no-edit <sha of the §3.K7 commit> && git log -1 --format=%s && git show --stat HEAD && git push
grep -c '^kubernetesVersion: v1.36.0$' kubernetes/bootstrap/talos/talconfig.yaml      # 1
grep -c '^talosVersion: v1.14.2$'      kubernetes/bootstrap/talos/talconfig.yaml      # 1 (the OS bump stays)
cp "$SCR"/clusterconfig.pre/* kubernetes/bootstrap/talos/clusterconfig/               # back to the pre-K render
# 2) roll the cluster back with the same tool (read-only preview first)
(cd kubernetes/bootstrap/talos && mise exec -- talosctl upgrade-k8s --talosconfig=./clusterconfig/talosconfig --to=v1.36.0 --dry-run --pre-pull-images=false --nodes=192.168.55.11 | grep -E 'update |compatible|^ < ')
mise exec -- task talos:upgrade-k8s 2>&1 | tee "$SCR/k-rollback.log"
```
(The restored `clusterconfig.pre` carries the installer `:v1.14.1` line — that matches the
render before Phase K, and nothing in this plan applies it. Re-render after the window if the
operator wants it truthful for v1.14.2.)

**Confirm the cluster is back:** §4.7 CA-K1 with `v1.36.0` in place of `v1.36.5` (4 jobs × 3,
total 12, `kube_node_info` v1.36.0 = 3), CA-K2 expecting `v1.36.0` counts `6`/`3` and the
`k-sysfs-pre.txt` `sys.*` count, then the §4.7 health floor against the same `k-*` baselines.

**Wedged run** (one apiserver not Ready): the other two keep API traffic. Do NOT reboot or
`apply-config` a node to unstick it — re-run the task (it resumes; already-matching components
are skipped), and read `talosctl -n <ip> logs kubelet` / `talosctl -n <ip> containers -k` for the
static pod first. A part-upgraded control plane (some components 1.36.5, some 1.36.0) is inside
the Kubernetes version-skew policy, so a rollback that would overrun the window may be finished
in a later reboot-free slot with the operator's say-so; it is never a reason to touch etcd or a
node.

## 6) Interference notes

### 6.1 — Ordering against `talconfig-multidoc-migration` — RESOLVED (executed 2026-10-04)

**Historical.** The migration executed green on 2026-10-04 (a7965251, retired 10bee773); the
`depends_on` was removed 2026-10-05 (F-c688c50f) and premise
`multidoc-migration-applied-on-all-nodes` is now the live proof it is still applied. The
reasoning that fixed the order is kept below for the record:

- **Roll first → the migration's ready-for-go review is void.** Its premise
  `nodes-on-talos-1.14.1` (`expect_exact: Talos (v1.14.1) ×3`) fails, and its render, semantic
  diff and dry-runs were all measured against v1.14.1 machinery. A high-risk control-plane
  plan whose review is the only thing standing between it and "every Secret unreadable" would
  have to be re-rendered and re-reviewed.
- **Migration first → this plan is unaffected.** The roll does not read or write machine config
  (§1.3); §3.6 validates whatever is live, in either form (the warning-diff and both negative
  controls are form-independent by construction — control A uses a document kind present in
  both forms). After it, `task talos:generate-config` works on main again, so if WBT (§1.2) ever
  needed a sysfs/udev counter-measure, the GitOps path for it exists.
- **The migration must also not run after a PART-rolled cluster** (its premise again). If this
  plan ever stops part-rolled (§5.2), finish or roll back the roll before the migration runs.

**Reciprocity (house rule; `--validate` does not check it):** `kube-prometheus-stack-91.9.0`
names this plan in `conflicts_with` (named back here 2026-10-05); the migration plan is retired. `multus-macvlan-foundation` does not yet;
it is unwindowed so the scheduler is safe today, but its owner should add `talos-linux-1.14.2`
in its next edit.

### 6.2 — Slot

This plan needs a whole `sun-attended` window alone (`exclusive: true`): every pod is evicted and
rescheduled three times; any other change verified in the same window has two candidate causes.
State 2026-10-05: the 10-04 migration has executed (a7965251); the flux-reconciler-impersonation
placeholder on 10-11 was released and **n8n-2.39.8 now holds sun-attended:2026-10-11**. The
coordinator will propose **sun-attended:2026-11-01** for this plan (the window agent assigns; the
2026-10-01 listing of later Sundays is stale — read `maintenance-plan.py --open` at assignment). After 2026-10-25, 09:00 Berlin = **08:00Z**
(CET); all UTC timestamps in the gates are absolute and unaffected.

### 6.3 — Things that must not run concurrently

- **This window's Step 0** runs FIRST (scheduler reserves 20 min), then Phase A's commit must
  already be pushed, then the freeze. Never skip Step 0 to buy time.
- **The nightly 03:30 window** of the same day — its reconciles must have landed (§2.7).
- **`storage/daily-backup-all-volumes` (03:00 UTC)** and the `*-filesystem-trim` /
  `*-snapshot-cleanup` CronJobs (02:00/02:30 UTC) — a 09:00 window clears them; do not let this
  plan slip into their path.
- **The 04:00-anchored operation sweep** — finished before §2.0b; no ad-hoc sweep in-window.
- **Any Longhorn engine/manager upgrade, StorageClass change, PVC delete**
  (`docs/sops/storage-safety.md` applies in full; nothing here deletes a PVC).
- **UniFi firmware** — none in this slot (§2.11); a survivor carrier change stops the roll.
- **Zigbee/Home Assistant work** — every reboot drops SLZB coordinator sockets; expected noise.
  Run `docs/sops/home-assistant-updates.md`'s post-restart checklist afterwards.
- **Any kube-prometheus-stack change** — §4 reads Prometheus (see `conflicts_with` note).

### 6.3a — Phase K (folded `k8s-1.36.5`) — what changed in the plan set

- `k8s-1.36.5` is `status: superseded`, `superseded_by: talos-linux-1.14.2`, `window: null`. Its
  file is kept intact: it is the **deferral fallback** (§3.K0 DEFER) and its §1–§5 are the source
  of Phase K's procedure.
- Other plans that still name `k8s-1.36.5` in `conflicts_with` (`nextcloud-fleet-35.0.1`,
  `talos-power-tuning-ab`) keep a now-terminal reference; their owners should retarget the line to
  `talos-linux-1.14.2` (both already conflict with this plan by exclusivity; `talos-power-tuning-ab`
  names it explicitly). Not edited from here.
- `kube-prometheus-stack-91.9.0` was asked (k8s-1.36.5 §6) to list `k8s-1.36.5` back; it already
  lists this plan, which now covers the folded scope.
- Phase K's own slot need (no reboot) no longer matters: it rides this plan's exclusive Sunday.

### 6.4 — Shared infra this perturbs

| Shared thing | Effect | Who notices |
|---|---|---|
| `gateway/envoy` | one of three pods of each Envoy deployment down per node | every routed app (110 HTTPRoutes on 2026-10-01) incl. the public edge — brief resets; no fallback controller |
| `etcd` | one member down per node (no version move); defrag + snapshot first | control plane; API blips |
| `apiserver` (Phase K) | each kube-apiserver restarts on v1.36.5, one node at a time; every watch re-lists against etcd | executor's kubectl via the VIP (seconds); Flux controllers; operators/webhooks with watches |
| kubelet (Phase K) | each kubelet restarts once (NO_REBOOT); CSI + intel device plugins re-register | §4.7 CA-K3 (workload restarts) + CSINode check |
| VIP 192.168.55.10 | fails over when its owner rolls (03 held it 2026-10-01) | kubeconfig clients incl. the executor |
| etcd leadership | re-elects when the leader rolls; drain-driven survivor elections possible (§14.3) | §3.10 pattern (ii) |
| `talos-machineconfig` / kernel | 6.18.54 + WBT on the shared NVMe | etcd, Longhorn, image pulls — measured by §3.10b/§4.4 #9/§4.6 |
| `igpu-i915` / NPU | device plugins re-register per node | Frigate, Jellyfin, Plex, Immich, NPU workloads |
| `security` DaemonSets | falco (`modern_ebpf` vs 6.18.54), wazuh-agent, otel daemon restart per node | per-node telemetry gap |
| `authentik` | server/worker/13 outposts reschedule | SSO, one silent re-login per app |
| `storage/longhorn` | instance-manager restart + replica rebuild ×3 | every stateful app |
| `cni/cilium`, `coredns`, `cert-manager` | pods restart/reschedule per node | pod networking/DNS/webhooks, briefly |
| `monitoring` | Prometheus loses samples while its node drains (§3.9a covers etcd) | §4 waits 15 min before judging |
| `flux-source` / `git-main` | push freeze, freeze-sha gate before every node, every main-pushing ImageUpdateAutomation not already git-suspended is suspended (and only those resumed) | every session/bot that commits |
| `cifs-share` | smb.csi mounts torn down/remounted with their pods | media apps, paperless, backups |

## 7) Risk and duration against the slot

**Risk: `high`** — blast radius is the whole cluster and the last roll measured drain-driven
survivor fsync stalls (worst 1.8 s → 3.6 s → 7.3 s) and elections (talos-upgrade.md §14.3). The
CONTENT of v1.14.2 is low-risk (a patch, no etcd/K8s move) and, unlike v1.14.1, **rollback is real
at every node** (§5). Phase K alone would be `medium` (bug-fix patch, rolling and readiness-gated
by upstream tooling, no reboot; but it restarts every apiserver and kubelet and adopts 7 bootstrap
objects into an SSA inventory); it does not raise the plan's risk, and its rollback (§5.5) is real. `needs_reboot: true`, `capability_change: true` → operator-present,
sun-attended only.

**Residual risks the operator should weigh at the GO:**
- **F-3602cfa9** — the unexplained cluster-wide etcd stall of 2026-09-24 ~20:28Z (no disk/IO
  signal) is still open. None of the disk gates would predict a recurrence; §3.10's carrier rule
  and pattern (ii) would stop the roll between nodes; if it recurs while a node is down, quorum
  can be lost for its duration — the §3.8a snapshot is the backstop.
- **WBT is new on the etcd disk.** Upstream's intent is lower tail latency under background
  writeback/discard; it is unmeasured on this hardware. The canary measures it first (§3.10b on
  the canary, CA4), and its rollback is clean.

**Price — from the 2026-09-27 MEASUREMENTS (talos-upgrade.md §14.7, F-3625b9f6):**

| Phase | Min | Basis |
|---|---:|---|
| Phase A (§3.1–§3.7) | (25) | **before the window**, Flux-inert — not counted |
| §2.0b freeze + suspend 3 automations (2 git-held left alone) + read-back | 3 | |
| §2 pre-checks incl. premises, §2.3b gates + controls, baselines | 20 | 09-27 took ~23 incl. helper writing; helpers now written in Phase A |
| §3.8.0 defrag (IN USE 32–33 % on 2026-10-01) | 7 | measured 4–7 |
| §3.8a snapshot | 3 | measured |
| Canary: drain ~2 + reboot ~1 + Longhorn ~20 + §3.10/§3.10a/§4.1 + go/no-go | 30 | measured ~23/node + 7 for the canary-only checks |
| §3.10b settle | 10 | fixed gate |
| 2nd node | 27 | ~23 measured + probe/gates |
| §3.10b settle | 10 | fixed gate |
| 3rd node | 27 | |
| §4 incl. ≥ 15-min alert settle (#9/#10 inside it) | 20 | |
| §5.4 resume + read-back | 3 | |
| §3.12 CLI pin commit | 3 | after §5.4 |
| **OS roll in-window total** | **163 → priced 165** | |
| Phase A §3.7b pre-pull | (5) | before the window — not counted |
| §3.K0 checkpoint | 2 | |
| §3.K1 baselines (re-measured after the roll) | 3 | |
| §3.K2 sed + §3.K3 render diff + §3.K4 dry-run | 5 | dry-run measured rc 0 in seconds; render measured |
| §3.K5 `upgrade-k8s` | 15 | k8s-1.36.5 priced ~20 incl. 12 pulls; the pulls are near no-ops after §3.7b (−4..5); 9 static-pod restarts + 3 kubelet restarts each waited to Ready — **NOT measured here; the 2026-04-30 run left no timing**. Without §3.7b: 19–20 |
| §4.7 CA-K1..K3 | 5 | |
| §4.7 10-min soak + health floor | 13 | fixed soak + reads |
| §3.K7 commit + push | 2 | after §5.4 |
| **Phase K in-window total** | **45** (49 without §3.7b) | |
| **FULL SCOPE** | **210** | |

```
slot wall clock                      200   (sun-attended, runbooks/maintenance-windows.yaml)
  − Step 0 reserve (mandatory)        20
  = schedulable                      180
  − OS roll (Phases B + §4 + close)  165
  ────────────────────────────────────────
  = residual                          15   <  Phase K 45   ->  FULL SCOPE 210 = 180 + 30 OVER
```

**Phase K does NOT fit the priced slot: 210 > 180 by 30 min** (and > the raw 200 even if Step 0
took 0 min). Declared `est_duration_min: 180` = the cap, because a declared 210 could never be
placed and would strand the OS roll with it; the plan is `exclusive: true`, so the figure only
decides fit. The design that makes this honest:

1. **The deferral checkpoint is the overflow valve (§3.K0).** Phase K starts only if the OS roll
   reached §3.K0 by **T+129** (180 − 45 − 6 close). The priced OS timeline reaches §3.K0 at
   **~T+159**, so on the price Phase K **defers**; it runs inside 180 only if the roll beats its
   price by ≥ 30 min. Plausible but not expected: 09-27 measured ~23 min/node against the 27/30
   priced here (−11 over three nodes), §3.8.0's defrag is skipped if IN USE ≥ 50 % (−7), and
   §4.4's 15-min alert settle mostly overlaps node 3's ~20-min Longhorn gate (§4.4 #11 counts
   from the node's return, not from §3.11 PASS) — together roughly −25.
2. **Operator extension (§3.K0 #3)** is the other path: Phase K is reboot-free, the operator is
   present, and the window's raw end is T+(200 − Step 0 actual). If Step 0 is quick (≤ 10 min),
   the full scope ends at ~T+190–200 ≤ the raw end — a ~30-min extension past the 180 budget,
   asked once at §3.K0. **Recommended at the GO:** the operator pre-states whether such an
   extension is acceptable, so §3.K0 needs no live question.
3. **On DEFER** the folded work falls back to `k8s-1.36.5` (re-activated by the coordinator,
   §3.K0) in a sat-attended slot (55 ≤ 70) — no work lost, the OS roll stands complete.
4. **Not proposed:** trimming the 10-min soak, the §3.K4 dry-run (the only gate on the prune set
   under v1.14.2 machinery), or any Phase B gate/settle to make room.

**Phase K's own overrun risk:** a §5.5 rollback adds ~25 min and cannot fit any K start time
inside 180. Because K8s patch skew is supported and Phase K reboots nothing, a rollback that would
cross the raw window end is finished in a later reboot-free slot with the operator's say-so
(§5.5 "Wedged run"), never squeezed.
The residual is not the rollback budget; the **timeline** is: the canary ends at about
**T+63** (3 + 20 + 7 + 3 + 30), leaving ~117 min of slot, and a canary rollback costs ~35 min drained (§5.1a; a §5.1b hard-reboot rollback of a NotReady canary prices as a full Longhorn recovery, ~45+ min)
(reboot + Longhorn gate + re-verify). Past the canary the answer is stop-part-rolled (§5.2) or a
per-node rollback, both supported. **Executor rule:** if the 2nd node's §3.10b has not PASSED by
**T+140**, stop part-rolled after two nodes (§5.2) unless the operator, present, extends. If
Phase A was NOT done before the window, it runs first (+25 → 190 > 180 schedulable): then stop
after the canary + 2nd node unless the operator extends. Never trim a gate or a settle to fit
the third node. If the canary alone takes > 45 min, re-plan from that measurement.

## Open items / repo corrections (reported, not worked around)

1. **The talos-1.14.1 live-config procedure no longer works on v1.14.** It read two MachineConfig
   ids (`v1alpha1`, `persistent`) and treated `DIFFER` as a STOP. On v1.14.1 `persistent`
   returns NotFound (measured 2026-10-01 on all three) and the loop prints `DIFFER` on a healthy
   node. `docs/sops/talos-upgrade.md` §14.2 step 1 still prescribes it ("Both must be identical —
   `DIFFER` means something is staged: STOP") — that SOP text would halt the next roll falsely.
   This plan first used a one-id premise (`single-machineconfig-per-node`, RETIRED); after the
   2026-10-04 multidoc + sysfs apply-configs `persistent` reappeared, and the live premise is now
   `no-pending-machineconfig-per-node` (ids `persistent` + `v1alpha1`, specs equal). **SOP corrected
   2026-10-01** (§14.2 step 1 now: single `v1alpha1` id, any extra id = staged → STOP; §11.1
   now carries the rollback-is-undrained warning) — that 2026-10-01 SOP text ("single `v1alpha1`
id") is itself stale since 2026-10-04 and should follow the premise above (reported, not edited).
2. **The 2026-09-27 plan's "expected doubled `init_on_alloc`" cmdline is stale** — v1.14.1 emits
   a single `init_on_alloc=0`. §4.1 now compares against a recorded per-node file instead of a
   written set.
3. **ImageUpdateAutomations that push to `main` grew from 2 to 5** (gas-price-monitor,
   splitfairy, showcase). talos-upgrade.md §14.3 says "suspend any ImageUpdateAutomation that
   pushes to main" (correct, rule-based); any runbook that names only the two absenty ones is stale.
   §2.0b enumerates live. **The SOP rule is incomplete in the other direction:** both absenty
   automations are `suspend: true` IN GIT (operator hold), and a blanket suspend-then-resume-all
   would resume them. talos-upgrade.md §14.3 should say "suspend those not already suspended;
   record the pre-state; resume only what you suspended" (reported, not edited here).
4. **No version finding exists for Talos v1.14.1 → v1.14.2.** The version sweep did not file one
   (the previous one, F-912f4778, closed with the roll); the plan-or-page pass therefore has no
   finding to join this plan to for the version itself. Worth checking why the version check is
   silent on a newer stable Talos release.
5. Still owed from talos-1.14.1: the stale schematic `b85cceac…` comment in
   `patches/global/machine-intelgpu.yaml`.
6. `plan-premises.py` cannot express the factory `v9.9.9 → 404` control (rc≠0 with no stdout
   always fails) — kept as the §3.1 hard gate, as before.
7. **(carried from k8s-1.36.5 on the fold)** The `siderolabs/*` deny-rule reason in
   `runbooks/auto-update-policy.yaml` ("needs a rolling node-reboot maintenance window") is wrong
   for the `ghcr.io/siderolabs/kubelet` dep — that dep is a no-reboot `upgrade-k8s`. The hold is
   right; the reason misroutes it to reboot-capable Sundays. Fix: a dedicated rule above the
   glob, `match: "ghcr.io/siderolabs/kubelet"`, whose reason names `upgrade-k8s`. Not edited here.
8. **Pre-pull persistence is measured once, not per release:** §3.7b relies on images surviving
   a Talos upgrade (measured on .12 against the 09-27 roll). If a future Talos release changes
   EPHEMERAL handling, upgrade-k8s silently re-pulls (cost: minutes, not correctness).
