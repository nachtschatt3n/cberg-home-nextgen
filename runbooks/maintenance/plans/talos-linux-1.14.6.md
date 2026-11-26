---
plan_id: talos-linux-1.14.6
component: talos
supersedes: talos-linux-1.14.5
pr: 248
kind: infra
current: v1.14.1
target: v1.14.6 + Kubernetes 1.36.6
update_type: patch
risk: high
est_duration_min: 180
needs_reboot: true
exclusive: true
touches:
  namespaces:
  - flux-system
  - my-software-production
  - my-software-development
  - my-software-showcase
  - kube-system
  - storage
  - network
  - monitoring
  - security
  - home-automation
  - office
  - backup
  - ALL (cluster-wide)
  resources:
  - kubernetes/bootstrap/talos/talconfig.yaml
  - runbooks/auto-update-policy.yaml
  - .mise.toml
  - kubernetes/bootstrap/talos/clusterconfig/
  - 'node images: kube-apiserver/-controller-manager/-scheduler:v1.36.6 (cri ns) + siderolabs/kubelet:v1.36.6 (system ns) pre-pulled on all 3 nodes in Phase A (§3.7b, ~140 MB/node)'
  - 'machine config (all 3 nodes, Phase K, NO_REBOOT): apiserver/controller-manager/scheduler/kubelet/kube-proxy image fields only'
  - clusterrolebinding/system-bootstrap-approve-node-client-csr, system-bootstrap-node-bootstrapper, system-bootstrap-node-renewal, system:talos-nodes; clusterrole/system:talos-nodes; secret/kube-system/bootstrap-token-*; configmap/kube-system/kubeconfig-in-cluster (Phase K annotation-only SSA adoption, §1.5)
  - node/k8s-nuc14-01
  - node/k8s-nuc14-02
  - node/k8s-nuc14-03
  - 'etcd (3 members, 3.7.1 -> 3.7.3: Talos-default image, NOT pinned in machine config — re-measured 2026-10-31; storage stays 3.7.0; defrag §3.8.0 + snapshot §3.8a)'
  - all Longhorn replicas (158 = 79 volumes x numberOfReplicas 2, 2026-10-31)
  - imageupdateautomation (every main-pushing one NOT already suspended — 4 of 6 on 2026-10-31; enumerated live at §2.0b)
  - 'kernel sysctl kernel.modprobe: '''' -> /sbin/modprobe on every node (v1.14.5 Talos default, §1.2; measured empty 2026-10-31)'
  - 'backup/offsite restic Jobs (offsite-seed-*, nightly offsite-backup-apps/-core): must be finished (none Running) before ANY drain, section 2.3; never suspended (a suspended Job counts its deleted pod as failed and backoffLimit is 0); premise offsite-restic-seed-not-running'
  - kernel 6.18.58 -> 6.18.63 on every node (the only node-visible delta of v1.14.5 -> v1.14.6 besides Go 1.26.11 and Flannel 0.28.10, which we do not run)
  shared:
  - apiserver
  - flux
  - etcd
  - cni/cilium
  - coredns
  - storage/longhorn
  - gateway/envoy
  - public-edge
  - authentik
  - cert-manager
  - monitoring
  - igpu-i915
  - home-automation-pinned
  - node-power-thermal
  - cifs-share
  - flux-source
  - git-main
  - talos-machineconfig
  - offsite-backup
depends_on:
- longhorn-1.13.0
conflicts_with:
- talos-linux-1.14.5                # superseded sibling; edits the same talosVersion line.
- coredns-1.50.5
- envoy-gateway-1.10.0
- envoy-proxy-config-distroless-v1.40.0
- envoy-proxy-config-distroless-v1.40.2
- etcd-timeouts-5000-500
- flux-oci-chart-sources
- flux-reconciler-impersonation
- frigate-reolink-go2rtc-flv
- helm-drift-detection
- icloud-drive-fleet-2.3.0
- kube-prometheus-stack-93.3.0
- longhorn-1.13.0
- mac-tooling-pins-2026-11
- multus-macvlan-foundation
- n8n-2.47.7
- nextcloud-mcp-0.206.0
- nextcloud-mcp-0.211.1
- nocodb-2026.10.1
- otbr-0.4.0
- otbr-thread-rcp-recovery
- otel-operator-0.27.2
- postgres-digest-refresh-2026-11
- postgres-fleet-18.7-alpine
- postgres-fleet-18.7-bookworm
- redis-fleet-8.10.3
- talos-power-tuning-ab
- nextcloud-12.0.2   # plan-refine 2026-11-26: successor of a dead ref
- nextcloud-9.4.5   # plan-refine 2026-11-26: successor of a dead ref
# plan-refine 2026-11-26: dead ref(s) immich-machine-learning-3.4.1, immich-server-3.4.1, iobroker-v12.0.0-digest-005ba9c, music-assistant-skill-b1ef33a, nextcloud-9.4.3, tube-archivist-elasticsearch-9.5.5, unpoller-5.9.5 pruned
capability_change: true
rollback_class: git-revert
security_ref: F-f3f2af15
finding_refs:
- F-27a3f024   # etcd churn (open; the real blocker)
- F-33873912   # etcd churn
- F-94f3d2b3   # churn linked to CI-runner CPU saturation on nuc14-01/02 (cause is not ours)
- F-8bfd22b9   # CI maxRunners saturating nodes
- F-912f4778
- F-f3f2af15
- F-c0de81ca
- F-b2d00c28
- F-2cb2dbc9
- F-e8bb3113
- F-3625b9f6
review: null
status: draft
window: null
premises:
- id: nodes-on-v1.14.1
  why: '`current:` claims all three nodes run v1.14.1. A node already on v1.14.4/v1.14.5, a node still on something older, or a fourth node prints a different string and fails.'
  run: kubectl get nodes -o jsonpath='{.items[*].status.nodeInfo.osImage}'
  expect_exact: Talos (v1.14.1) Talos (v1.14.1) Talos (v1.14.1)
- id: etcd-protocol-3.7
  why: Pre-window etcd is one server_version group, 3.7.x, count 3 (3.7.1 x3 re-read 2026-10-31 via talosctl etcd status). A mixed cluster (a half-done earlier roll) prints a second group and fails. After this roll the same query must read 3.7.3 x3 (§4.3 CONTENTS ASSERTION 6). Reads Prometheus through the apiserver service proxy.
  run: kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=count%20by%20(server_version)%20(etcd_server_version)'
  expect_matches: ^\{"status":"success","data":\{"resultType":"vector","result":\[\{"metric":\{"server_version":"3\.7\.[0-9]+"\},"value":\[[0-9.]+,"3"\]\}\]\}\}$
- id: etcd-elections-24h-below-6
  why: 'Section 2.3 NO-GO line as a premise: < 6 leader changes in 24h with no reboot (>= 6 = etcd already unstable). LIVE 2026-11-16: 41.01 in 24h (152-154 in 7d; F-27a3f024, F-33873912); re-read 07:05Z 54.02 - this premise FAILS TODAY, which is the proof it can fail. WINDOW-START ONLY: after the canary reboots this premise can never pass again, so it is never a per-node gate (section 2.2 node mode is). Regex dry-tested: "5.0017" and "0" pass; "6", "12.3", "41.014" fail. Must PASS at the operator GO AND again at window start. Never weaken, widen or skip.'
  run: kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=max(increase(etcd_server_leader_changes_seen_total%5B24h%5D))'
  expect_matches: '"value":\[[0-9.]+,"[0-5](\.[0-9]+)?"\]'
- id: etcd-elections-last-2h-zero
  why: 'HARD etcd-quiet gate (new 2026-11-16): ZERO leader changes in the last 2 h. The 24h rule alone can pass on a day whose churn aged out at 22:00 and restarts at 06:00; a node drain on an etcd that elected within the last two hours is exactly the F-2cb2dbc9 pattern. LIVE 2026-11-16: earlier in the day the 1 h increase read 5.04 and the 2 h increase 11-15 on every member (fails); re-read 07:00Z: 0 on all three (the burst aged out, passes). Churn is bursty, which is why section 2.2 requires two reads 15 min apart. WINDOW-START ONLY, like the 24 h premise. A quiet counter prints exactly "0" (no increase); any election prints a non-zero float. Fails closed on empty (no data).'
  run: kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=max(increase(etcd_server_leader_changes_seen_total%5B2h%5D))'
  expect_matches: '"value":\[[0-9.]+,"0"\]'
- id: etcd-wal-fsync-p99-below-50ms-10m
  why: 'HARD etcd-quiet gate (new 2026-11-16): the WORST member''s 10-minute WAL fsync p99 is below 50 ms. Shared consumer NVMe (etcd + Longhorn + images) spikes 23-110 ms on busy days (2026-11-16: 88 ms on .11 over 5 m earlier; re-read 07:00Z over 10 m: 25.5 / 24.9 / 14.8 ms, passes). histogram_quantile over an unscraped/empty histogram prints NaN or nothing: neither matches, so it fails closed. Regex dry-tested: "0.0318", "0.0499" pass; "0.0880", "0.05", "0.1", "NaN" fail.'
  run: kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=max(histogram_quantile(0.99,sum%20by%20(le,instance)(rate(etcd_disk_wal_fsync_duration_seconds_bucket%5B10m%5D))))'
  expect_matches: '"value":\[[0-9.]+,"0\.0[0-4][0-9]*"\]'
- id: offsite-restic-seed-not-running
  why: 'No off-site restic job pod (the ~16 h seed offsite-seed-*, or the nightly offsite-backup-apps/core at 00:30/00:40 UTC) is Running: a node drain kills the pod, the Job has backoffLimit 0, so a part-written restic repository is left with a stale lock and the seed restarts from its last snapshot. LIVE 2026-11-16 07:05Z: TWO pods Running, both on k8s-nuc14-01: offsite-backup-core-29913160-hrxcr (the 00:40 UTC nightly, 6 h 25 m old) and offsite-seed-core-64pxh (Job offsite-seed-core re-created 06:44Z; the 22:07Z seed pod is gone) -> prints 2, fails. WINDOW-START ONLY: section 2.3 re-checks before every drain. grep -c prints the count (0 when none match), so an empty cluster does not fail-closed by accident.'
  run: kubectl get pods -n backup --field-selector=status.phase=Running -o name | grep -c offsite
  expect_exact: '0'
- id: factory-publishes-schematic-v1.14.6
  why: 'The Image Factory serves the OCI index for our schematic at v1.14.6 and its linux/amd64 entry is the digest measured 2026-11-16 (sha256:d488effd...5c10; the first request after a release builds the image on demand and can take minutes, so a premise timeout (60 s) on a COLD factory is a retry-once, not a NO-GO; section 3.1 is the hard gate with the v9.9.9 -> 404 control). Content-pinned: an intercepting middlebox answering every path, or a silently re-published tag, fails it.'
  run: kubectl --kubeconfig=/dev/null --server=https://factory.talos.dev --token=none get --raw /v2/installer/43b3cbfc2957259b4588d362709d47387607901d4d3506c1ea46d7ea74cb99a3/manifests/v1.14.6
  expect_matches: '"mediaType":"application/vnd\.oci\.image\.index\.v1\+json".*"digest":"sha256:d488effdca3f6f0d667d5ea61e31a6831e51290ccf49b0980d93ba301f575c10","platform":\{"architecture":"amd64","os":"linux"\}'
- id: talos-v1.14.6-installable
  why: The factory still lists v1.14.6 as installable (the 1.14 MINOR LINE at the reviewed patch; a NEWER 1.14.x patch does not fail this premise - it is the in-window 2.2b decision, default stay on v1.14.6, F-56452df7). Fails when v1.14.6 disappears from the list (pulled release) or the factory answers with something that is not the version array; the closing quote anchors against "v1.14.60".
  run: kubectl --kubeconfig=/dev/null --server=https://factory.talos.dev --token=none get --raw /versions
  expect_matches: ^\[.*"v1\.14\.6".*\]$
- id: multidoc-migration-applied-on-all-nodes
  why: The 2026-10-04 multidoc migration (a7965251) put a KubeAPIServerConfig document into every node's live machine config. Expect 3; anything else means a node lost the multi-document config — STOP.
  run: 'talosctl --nodes=192.168.55.11,192.168.55.12,192.168.55.13 get machineconfig v1alpha1 -o yaml | grep -c ''kind: KubeAPIServerConfig'''
  expect_exact: '3'
- id: no-pending-machineconfig-per-node
  why: 'Intent: NO config change is pending that would land on the reboot. On v1.14.1 every node carries exactly two MachineConfig resources: `v1alpha1` (config.ActiveID, the running config) and `persistent` (config.PersistentID, the copy saved to disk). Talos v1.14.1 pkg/machinery/resources/config/machine_config.go documents that PersistentID is AHEAD of the active config after a --mode=staged apply and BEHIND it after --mode=try; the two specs are equal only when nothing is staged. (The 2026-10-01 measurement of a single v1alpha1 id predates the 2026-10-04 multidoc migration + sysfs-caps apply-configs, after which `persistent` reappeared; measured 2026-10-05: persistent v2 / v1alpha1 v3 on all three nodes, specs equal, 16459 chars.) The specs carry machine secrets, so they are compared INSIDE jq and never printed or stored; the output is only node, sorted id list, and spec-equality. plan-premises.py allows no hashing tool, and in-memory equality is stricter than a hash compare anyway.
    AMENDED 2026-11-16 (the carried 1.14.5 regex FAILED live): node .11 now carries ONLY `v1alpha1` (no `persistent` resource) while .12/.13 carry both — most likely the aborted 2026-11-03 etcd-timeouts NOW run apply + rollback on .11; the specs are equal, so nothing is staged. A single `v1alpha1` id is the clean 2026-10-01 form, so the regex now accepts either id list per node. FAILS on: specs differing (true -> false), any extra id (e.g. a third resource), a missing `persistent`, or an unreachable node (pipefail). Negative control 2026-10-05: appending a byte to node .12''s persistent spec in-stream printed false for .12; injecting a third id on .13 printed its 3-id list and false. STOP on failure and find out what staged it.'
  run: talosctl --nodes=192.168.55.11,192.168.55.12,192.168.55.13 get machineconfig -o json | jq -sc 'group_by(.node)[]' | jq -c 'sort_by(.metadata.id)' | jq -c '[.[0].node, map(.metadata.id), unique_by(.spec)[1] == null]'
  expect_matches: ^\["192\.168\.55\.11",\[("persistent",)?"v1alpha1"\],true\]\s+\["192\.168\.55\.12",\[("persistent",)?"v1alpha1"\],true\]\s+\["192\.168\.55\.13",\[("persistent",)?"v1alpha1"\],true\]$
- id: longhorn-all-volumes-replica-2
  why: 'A RULE, not a count: every Longhorn volume has numberOfReplicas 2 (79 volumes on 2026-10-31; 80 on 2026-10-17; 94 on 2026-10-01). §2.5 measures the live set and §3.11 gates against that recording. Any volume at 1 or 3 changes the one-node-down arithmetic; an empty list fails.'
  run: kubectl get volumes.longhorn.io -n storage -o jsonpath='{.items[*].spec.numberOfReplicas}'
  expect_matches: ^2( 2)*$
- id: no-volume-with-stale-replica-timeout-0
  why: 'F-b91ef6e5 (resolved 4af5b6bc) set staleReplicaTimeout 20/30 on every volume so failed replicas after a drain are garbage-collected; on 2026-09-27 two volumes at 0 blocked the replica-total gate. Measured 2026-10-17: 31 volumes at 20, 49 at 30, none at 0. A 0 creeping back means §3.11 will need the manual cleanup of talos-upgrade.md §14.4 — re-price.'
  run: kubectl get volumes.longhorn.io -n storage -o jsonpath='{.items[*].spec.staleReplicaTimeout}'
  expect_matches: ^(20|30)( (20|30))*$
- id: backup-cronjob-exists
  why: §2.6 names storage/daily-backup-all-volumes (NOT the stale backup-of-all-volumes). Schedule is UTC (no timeZone set). Missing object fails.
  run: kubectl get cronjob -n storage daily-backup-all-volumes -o jsonpath='{.metadata.name} {.spec.schedule} tz=[{.spec.timeZone}]'
  expect_exact: daily-backup-all-volumes 0 23 * * * tz=[]
- id: pgadmin-selector
  why: §4.3 CONTENTS ASSERTION 1 writes through deploy/pgadmin (PVC pgadmin-data at /var/lib/pgadmin, measured 2026-10-01; selector re-read 2026-10-17) and selects its pod with app=pgadmin.
  run: kubectl get deploy -n databases pgadmin -o jsonpath='{.spec.selector.matchLabels}'
  expect_exact: '{"app":"pgadmin"}'
- id: etcd-latency-histograms-scraped
  why: §2.3b and §3.10b gate on the worst 5m-p99 of etcd WAL fsync and backend commit. An unscraped histogram reads EMPTY and a "< 50 ms" check would pass on no data. Expects 3 fsync + 3 commit series (6); a lost etcd target prints 4 or 5.
  run: kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=count(etcd_disk_wal_fsync_duration_seconds_count)%20%2B%20count(etcd_disk_backend_commit_duration_seconds_count)'
  expect_matches: '"value":\[[0-9.]+,"6"\]'
- id: kustomize-controller-write-metric-scraped
  why: The < 5 MB/s kustomize-controller gate reads cAdvisor container_fs_writes_bytes_total for container=manager. The filter must select exactly one series; 0 (not scraped) or 2 (double count) fails here.
  run: kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=count(container_fs_writes_bytes_total%7Bnamespace%3D%22flux-system%22%2Ccontainer%3D%22manager%22%2Cpod%3D~%22kustomize-controller-.*%22%7D)'
  expect_matches: '"value":\[[0-9.]+,"1"\]'
- id: kubelets-on-1.36.0
  why: Phase K's `current` is kubelet v1.36.0 x3. Anything else means a partial earlier upgrade-k8s run (re-run resumes; read §5.5 first) or someone already upgraded.
  run: kubectl get nodes -o jsonpath='{.items[*].status.nodeInfo.kubeletVersion}'
  expect_exact: v1.36.0 v1.36.0 v1.36.0
- id: talconfig-pins-1.36.0
  why: '§3.K2''s anchored sed rewrites exactly this line (dry-tested 2026-10-31 on a scratch copy already carrying talosVersion v1.14.5; same line as Renovate PR #233). A different value means the sed is a no-op and upgrade-k8s would read the wrong --to.'
  run: 'grep -c ''^kubernetesVersion: v1.36.0$'' kubernetes/bootstrap/talos/talconfig.yaml'
  expect_exact: '1'
- id: apiserver-configs-on-1.36.0
  why: 'Talos'' own APIServerConfig resources (what upgrade-k8s patches) carry v1.36.0 on all nodes: 6 image lines across 3 nodes, measured 2026-10-05. §3.K6 expects 6 at v1.36.6.'
  run: 'talosctl --nodes=192.168.55.11,192.168.55.12,192.168.55.13 get apiserverconfigs -o yaml | grep -c ''image: registry.k8s.io/kube-apiserver:v1.36.0'''
  expect_exact: '6'
- id: build-info-scraped-12
  why: '§3.K6''s CONTENTS ASSERTION reads kubernetes_build_info: 12 series (apiserver, kubelet, kube-scheduler, kube-controller-manager x3). Fewer means a scrape job went blind and the post-check could pass on an empty set.'
  run: kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=count(kubernetes_build_info%7Bgit_version%3D%22v1.36.0%22%7D)'
  expect_matches: '"value":\[[0-9.]+,"12"\]'
- id: bootstrap-inventory-7
  why: 'upgrade-k8s prunes against this SSA inventory. The 2026-10-05 dry-run diff showed 7 objects, all `configured` (annotation adoption), zero deletes, against an inventory of 7 entries. A different entry count means the prune set changed: §3.K4''s dry-run must be read action by action.'
  run: kubectl get configmap -n kube-system talos-bootstrap-manifests-inventory -o jsonpath='{.data}'
  expect_matches: ^\{(?:"[^"]+":"[^"]*",?){7}\}$
- id: longhorn-rebuild-limit-2
  why: '§3.11 and §7 price the roll at concurrent-replica-rebuild-per-node-limit 2 — the operator''s 2026-10-13 etcd-protection decision (1696a127), owned by Flux through the Setting CR in kubernetes/apps/storage/longhorn/app/concurrency-settings.yaml. It was 8 when talos-linux-1.14.2 was priced (that plan''s premise longhorn-rebuild-limit-8 FAILS today: got ''2''). A different value means someone moved the knob again: re-price (§7) rather than run. This plan never changes the limit; a value of 8 (or anything but 2) fails the premise so a stale price cannot be executed.'
  run: kubectl get settings.longhorn.io -n storage concurrent-replica-rebuild-per-node-limit -o jsonpath='{.value}'
  expect_exact: '2'
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
- docs/sops/maintenance-windows.md
generated: '2026-11-16'
needs_replan: "premise-fail: etcd-elections-24h-below-6: got '{\"status\":\"success\",\"data\":{\"resultType\":\"vector\",\"result\":[{\"metric\":{},\"value\":[179; offsite-restic-seed-not-running: got '1', want exactly '0'"
needs_replan_since: "2026-11-26"
---

# Talos Linux node roll — v1.14.1 → v1.14.6, then Kubernetes v1.36.0 → v1.36.6

> **SUPERSEDES `talos-linux-1.14.5`** (written 2026-11-16, upgrade-planner). v1.14.6 shipped 2026-11-11 and
> Renovate PR #248 and finding F-912f4778 now both read `v1.14.1 → v1.14.6`. `talos-linux-1.14.5` is vetted
> (`ready-for-go@2026-11-02`, slot `sun-attended:2026-11-22`) and **was not edited**. **This file is a DELTA PLAN:**
> the roll mechanics (helpers, per-node drain/gate loop, freeze, Phase K, rollback) are NOT re-typed; they are
> carried **by reference** from `talos-linux-1.14.5.md` pinned at commit `1641b605e` (read it with
> `git show 1641b605e:runbooks/maintenance/plans/talos-linux-1.14.5.md`; the file must stay in the tree, or in git
> history, until this plan is executed — never delete it before). What this file adds, in order of consequence:
> (1) the **etcd-quiet hard gate**, which FAILS TODAY (§2.2); (2) the **off-site restic fence** (§2.3); (3) the
> **v1.14.6 substitution table** (§3.0) — every version-bearing value re-derived and dry-run 2026-11-16; (4) the
> **v1.14.5 → v1.14.6 per-commit reading** (§1.2); (5) the verdict on **stacking `etcd-timeouts-5000-500`** (§1.4: do not).

## 1) Summary & why held

### 1.1 What changes, why held, why a NEW plan and not a retarget of 1.14.5

Roll `k8s-nuc14-01/02/03` (192.168.55.11–.13) from Talos **v1.14.1** to **v1.14.6** one node at a time with the
Longhorn and etcd gates between nodes; Kubernetes stays v1.36.0 during the roll. etcd moves 3.7.1 → **3.7.3**
member by member (v1.14.6's `DefaultEtcdVersion` is `v3.7.3`, identical to v1.14.5 — read from
`pkg/machinery/constants/constants.go` at both tags 2026-11-16). Then Phase K: Kubernetes v1.36.0 → v1.36.6, no
reboot (v1.36.6 still the newest 1.36 patch, 2026-10-28; v1.36.5 is the previous one). **Why held:** it reboots
every node of a 3-node hyper-converged control plane; not a false positive. Risk is `high`, exclusive Sunday.

**Retarget 1.14.5 in place, or supersede?** The README's default is *refresh in place, keep the plan_id* (four
things resolve by id). That is the right call when the work and its approvals survive the retarget. Here they do not:
1. The plan's `review: ready-for-go` and its pasted evidence (factory digest, talosctl checksum, kernel string,
   expected seds/diffs) are all derived for v1.14.5 — a retarget is a material amendment that re-reviews anyway.
2. **No operator GO exists to lapse**: the 1.14.5 plan itself states a *fresh GO* is still owed (its §6.2) and the
   roll has not started, so superseding destroys no approval. (When v1.14.4 → v1.14.5 happened the same way, the
   precedent was supersede.)
3. The operator's instruction for this task forbade editing the 1.14.5 file; PR #248, F-912f4778 and the
   reconciler's STALE check all already track v1.14.6, so leaving 1.14.5 as the "plan of record" lands the cluster
   one patch behind with the PR and finding still open.
4. Counter-argument, stated honestly: the 1.14.5 plan's own §2.2b says *default stay on the reviewed patch* and
   v1.14.6 carries nothing urgent for us (§1.2). If the operator prefers the least-new-evidence path, **executing
   1.14.5 as vetted is also defensible** — but then PR #248 and F-912f4778 must be re-dispositioned by hand, and a
   second roll for 1.14.6 follows later. We recommend one roll, to 1.14.6.

**Cost of superseding (the coordinator owns these edits; this file does none of them):** set `talos-linux-1.14.5`
to `status: superseded`, `superseded_by: talos-linux-1.14.6`, `window: null`; move the operator-chosen slot
`sun-attended:2026-11-22` to THIS plan only after plan-reviewer `ready-for-go` AND a fresh GO AND §2.2 passing; every
non-terminal plan that names `talos-linux-1.14.5` in its `conflicts_with` (list in the frontmatter here, 33 entries)
must add `talos-linux-1.14.6` (reciprocity owed; `maintenance-plan.py --validate` checks refs resolve, not
reciprocity). `grafana-chart-14.4.0`, named in the 1.14.5 conflicts, matches no plan file (DEAD-REF in 1.14.5; dropped
here).

### 1.2 v1.14.5 → v1.14.6, read per commit (20 talos + 11 pkgs + 1 tools; release 2026-11-11)

Component updates upstream: **Linux 6.18.58 → 6.18.63**, Flannel 0.28.10 (we run Cilium: inert), Go 1.26.11. etcd
3.7.3 and containerd 2.3.7 do NOT move. What reaches OUR nodes:
- **Kernel 6.18.63** (pkgs `e6ad19d`): five stable bumps on the NVMe/igc/i915 stack that carries etcd, Longhorn and
  the iGPU. Read-only risk: a hwmon/thermal rename like 6.18.51 → gate §4.4 #10 (`hwmon.py compare`) stays.
- **`8f6c141db` "don't zero the discovered volume partition offset"** (`block/discovery.go`): touches how Talos
  tracks partitions after a re-probe. New gate **CA8** (§4.1): per node, every `nvme0n1pN` DiscoveredVolume keeps a
  non-zero `offset` (live read: p1@1048576 … p6@1261436928 on all three nodes today).
- **`a16555ed5` "log lifecycle service actions to console"**: informational — a node's service stop/start lines now
  reach the console, which narrows the open "reboot cause is blind" gap. Record, do not gate.
- **`cc384acab` aescbc provider in the etcd-encryption GENERATOR** (`generate/kubernetes.go`): fires only when a
  secrets bundle carries an AES-CBC secret and only in `generate`/`genconfig`. Ours is a pinned patch
  (`patches/controller/kube-etcd-encryption.yaml`: secretbox `key2` + identity), Phase B writes no config. **Check
  anyway** at Phase K's re-render (§3.K3): the rendered `KubeEtcdEncryptionConfig` must still show `secretbox` /
  `key2` / `identity` (gate in §4.1 CA9) — unreadable Secrets would be the cost of being wrong.
- **`a02b84749` drop `kubernetes.io/arch` from affinity rules** (`k8stemplates/affinity.go`, flannel, coredns/
  kube-proxy test data): changes the Talos-rendered bootstrap manifests that `upgrade-k8s` diffs. **Phase K's
  dry-run (1.14.5 §3.K4, "7 objects, all configured, zero deletes") must be re-read action by action** — an
  affinity hunk on a bootstrap object is expected here and was not in the 1.14.5 evidence.
- Inert for us (no config uses them): GoBGP 4.10.0 / BGP peer updates, OpenStack MAC matching, SELinux mdadm/udev
  types, SideroLink token masking, log-sender reconnect, applesmc/ionic/Pensando/amdxdna/Grace modules, K8s CA
  rotation wait. `service etcd restart` is **still refused** (see §1.4): `ServiceRestart`/etcd service sources are
  untouched between the tags (compare of v1.14.5...v1.14.6 listed only `machined.go` and `udev.cil` under
  `*service*`/`*etcd*` names).
- Everything in 1.14.5 §1.1–§1.2 (WBT on NVMe, kubelet state-file deletion, KubePrism LB recovery, on-demand module
  loading, ACPI power button, kernel.modprobe sysctl) still applies: the hop is cumulative from v1.14.1.

`capability_change: true` (carried: node behaviour changes — WBT, on-demand module loading, power button). Never
unattended. `rollback_class: git-revert` carried with the same honesty as 1.14.5: nothing forward-only crosses the
hop (etcd 3.7.1 → 3.7.3 stays inside storage version 3.7.0; the real per-node revert is a DRAINED
`talosctl upgrade --image <factory>:v1.14.1`, 1.14.5 §5.1).

### 1.3 State measured 2026-11-16 (why this plan cannot run today)

- Nodes: 3 × Talos v1.14.1, kernel 6.18.51, kubelet v1.36.0, no reboot since 2026-09-27.
- **etcd is NOT quiet over 24 h, and its quiet is bursty.** `increase(etcd_server_leader_changes_seen_total[24h])` = **41.01** earlier on 2026-11-16 and **51-54**
  at 07:05Z (7 d: 154; F-27a3f024, F-33873912); the 2 h count read 11-15 per member earlier and **0** at 07:00Z, WAL fsync p99 over 5 m reached **88 ms** on `.11`
  earlier (10 m: 23-28 / 25 / 14-15 ms at 07:05Z), backend commit p99 up to 54 ms earlier (16 / 16 / 14 ms now). Leader is `.11`; `etcd status` shows 3.7.1 x3,
  storage 3.7.0, no learner, RAFT INDEX converged. The 1.14.5 plan's own NO-GO line is >= 6 per 24 h: **today is a NO-GO by 8-9x** on that line.
- Off-site restic: **two Jobs Running on `k8s-nuc14-01`** at 07:05Z - the 00:40 UTC nightly `offsite-backup-core-29913160` (6 h 25 m old) and `job/offsite-seed-core`
  (re-created 2026-11-16T06:44Z, image `restic 0.19.1`, `backoffLimit: 0`, `activeDeadlineSeconds: 172800`, 3 `backup-src-N` PVCs); `offsite-backup-apps-29913150` Completed.
  The earlier-read seed pod (running since 2026-11-15T22:07Z) is gone, so the seed was restarted. Nightly `offsite-backup-apps` 00:30 UTC, `-core` 00:40 UTC, prune Sun 04:30
  UTC, check Wed 04:30 UTC. `sun-attended` starts 09:00 Europe/Berlin = 08:00 UTC (CET), so only a still-running Job can overlap (§2.3).
- `longhorn-1.13.0` (the plan this one `depends_on`) is `vetted`, slot `sun-attended:2026-11-15` has passed and
  `helmrelease/longhorn` in `storage` still reads chart 1.12.1: **it did not execute**. `etcd-timeouts-5000-500` is
  `blocked` (its 2026-11-03 NOW run aborted, §1.4).
- Longhorn `concurrent-replica-rebuild-per-node-limit` = 2 (premise), Renovate #248 (this), #247 (talosctl pin, last),
  #233 (kubelet = Phase K's line).

### 1.4 Should the v1.14.6 roll carry the `etcd-timeouts-5000-500` change? **No — do not stack.**

Facts: Talos v1.14.1 *and* v1.14.6 refuse `talosctl service etcd restart` (the 2026-11-03 NOW run proved it on 1.14.1;
the service sources are untouched in v1.14.6), and etcd's args are computed from `EtcdSpec` when the service
(re)starts, so **a node reboot is the only mechanism** that makes `cluster.etcd.extraArgs`
`election-timeout: "5000"` / `heartbeat-interval: "500"` take effect. The roll reboots each node anyway, so it
*could* carry the flags: `apply-config` (no reboot) to a node immediately before that node's `talosctl upgrade`.
It **should not**, for four reasons:
1. **Mixed timeouts for hours.** etcd's tuning documentation: *"The heartbeat interval and election timeout value
   should be the same for all members in one cluster. Setting different values for etcd members may disrupt cluster
   stability"* (etcd-io/website `tuning.md`, read 2026-11-16). `etcd-timeouts-5000-500` exposes that state for ~35 min
   with no drain; a roll holds it for the whole of three rebuild-and-settle cycles (this plan prices 165–290 min) — on
   a cluster already electing 41×/24 h.
2. **Blind gates.** This plan's churn gates (elections, leaderless probe `probe.py`, RAFT TERM) measure whether the
   *OS roll* disturbed etcd. A simultaneous 1–2 s → 5–10 s failover-time change makes every election-count and
   leaderless-window reading ambiguous, and a half-applied timeout set is itself an election source.
3. **Rollback is no longer one-dimensional.** Phase B today writes no machine config (§1.2 rollback honesty). With
   flags stacked, a per-node revert to v1.14.1 reboots into a config that still carries the flags, and
   `no-pending-machineconfig-per-node` stops being a clean precondition for the *next* window. The operator's own
   rule in the etcd-timeouts plan: one risky change per window.
4. **It does not fix today's blocker.** Churn is the reason the roll cannot start (§1.3); stacking the remedy into the
   thing the churn gate guards is circular.

**What to do instead (for the operator, and the owner of `etcd-timeouts-5000-500`):** the ordering decision of
2026-11-02 (*etcd-timeouts first*) was made when that plan was executable; it is now `blocked`, so `depends_on`
here is `[longhorn-1.13.0]` only (the etcd-timeouts dependency is DROPPED; operator to confirm — Open item 1). When
etcd is quiet enough to pass §2.2, run this roll, soak ≥ 24 h with zero elections, then re-plan etcd-timeouts as a
**reboot-based** plan on the already-new OS: apply-config to all three nodes first (EtcdSpec only), then a rolling
`talosctl reboot` per node with exactly this plan's per-node drain/gate loop (the canary here MEASURES R and the
leader-rollover behaviour on 3.7.3). If the operator overrides and wants them in one slot anyway, the only shape that
is not worse: apply-config on all three nodes **before** Phase B (one commit, its own gates), accept the mixed state
until the third reboot, and re-price at ≥ 290 min (it will not fit 180 — it would need a NOW-class exclusive day).

## 2) Pre-checks

Run **inside the window, after Step 0, before touching a node.** Also run §2.1–§2.3 at the operator GO. Any failure
= NO-GO for the day — not a waiver, not a re-run-until-green.

### 2.0 Setup (scratch is local-only, mode 700)

```bash
cd /Users/mu/code/cberg-home-nextgen
export KUBECONFIG="$PWD/kubeconfig"
export TALOSCONFIG="$PWD/kubernetes/bootstrap/talos/clusterconfig/talosconfig"
SCR="$HOME/.cache/talos-1146"; mkdir -p "$SCR"; chmod 700 "$SCR"; stat -f '%Lp %N' "$SCR"     # MUST print 700
git show 1641b605e:runbooks/maintenance/plans/talos-linux-1.14.5.md > "$SCR/PROC-1.14.5.md"   # the carried procedure, pinned
wc -l "$SCR/PROC-1.14.5.md"                                                                    # MUST print 3096 (git show of 1641b605e, measured 2026-11-16; wc counts newlines)
awk 'NR>=600 && /1\.14\.5|1145|6\.18\.58|c865077b/ {printf "%d ", NR}' "$SCR/PROC-1.14.5.md"; echo   # MUST equal the 117 numbers listed under section 3.0 (a different list = PROC changed under you: STOP)
```
`PROC` below = `$SCR/PROC-1.14.5.md`; "PROC §x" = that section. Everything not listed in §3.0/§2.2/§2.3/§3.1/§4.1 CA8–CA9 is
executed exactly as PROC says, with the §3.0 table applied row by row (the table is complete: section 3.0 proves it with the awk line above).

### 2.1 Premises

```bash
.venv/bin/python3 runbooks/plan-premises.py talos-linux-1.14.6 --require-premises
```
**PASS:** every premise passes. **Run it at the operator GO and once at window start, NEVER mid-roll:** the premises describe the
PRE-roll world (`nodes-on-v1.14.1`, etcd `3.7.1` x3, the 2 h/24 h election premises, `kubelets-on-1.36.0`) and several of them
legitimately FAIL after the canary reboots. **At 2026-11-16 07:05Z it prints FAIL for exactly two premises:**
`etcd-elections-24h-below-6` (54.02) and `offsite-restic-seed-not-running` (2) - each a gate that can and does fail on live data.
(Earlier the same day `etcd-elections-last-2h-zero` and `etcd-wal-fsync-p99-below-50ms-10m` also failed; by 07:00Z both read clean, which is
why section 2.2 demands two reads 15 minutes apart.) The factory premise can take > 60 s on a cold tag: retry ONCE; a second failure is NO-GO.

### 2.2 The etcd-quiet HARD gate (new; reads Prometheus through the apiserver service proxy, no port-forward to die)

**Two modes, because one absolute gate cannot serve both moments.** A first draft of this plan required "zero leader changes in
2 h and < 6 in 24 h" before EVERY drain. That cannot pass after the first node: each reboot of a 3-member etcd produces at least
one election/leader observation, so the 2 h count is non-zero for ~2 h after node 1 returns and the 24 h count stays above 5.5 for
a day - the roll would be blocked by its own canary, or the operator would be tempted to waive the gate. The correct reading is
relative to the event that is allowed to disturb etcd:

| Moment | Mode | What must hold |
|---|---|---|
| operator GO and window start (twice, >= 15 min apart) | `start` | 2 h elections = 0 and 24 h < 6 on every member; fsync p99 < 50 ms, commit p99 < 100 ms; 3/3 series; `etcd_server_has_leader` = 1 x3 |
| before the CANARY drain | `node --since-epoch <QUIET>` | zero elections on every member since the last thing this plan did to etcd (QUIET = the stamp written after PROC 3.8.0 defrag / 3.8a snapshot) |
| before node 2 and node 3 drains | `node --since-epoch <RETURNED-prev>` | zero elections on all three members since the previous node returned `Ready` (this covers its Longhorn rebuild and settle, not only the settle) |

The rebooted member's own counter restarts at its boot, so the election it logs while rejoining happens BEFORE `Ready` and is
outside the window; a second election after `Ready`, on any member, is a real signal and fails the gate. The 24 h and 2 h absolute
lines are **window-start only** (they are also the premises of section 2.1; never re-run those mid-roll).

```bash
cat > "$SCR/etcdquiet.py" <<'PY'
import json, subprocess, sys, argparse, time
ap = argparse.ArgumentParser()
ap.add_argument("--mode", choices=["start", "node"], default="start")
ap.add_argument("--since-epoch", type=int, default=0)             # node mode: the PREVIOUS node's settle-start (or the start-gate time)
ap.add_argument("--max-elections", type=float, default=0.0)       # node mode: elections since --since-epoch (quiet = exactly zero)
ap.add_argument("--max-elections-2h", type=float, default=0.0)    # start mode
ap.add_argument("--max-elections-24h", type=float, default=5.5)   # start mode, < 6
ap.add_argument("--max-fsync-ms", type=float, default=50.0)
ap.add_argument("--max-commit-ms", type=float, default=100.0)
a = ap.parse_args()
P = "/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query="
def q(expr):
    raw = subprocess.check_output(["kubectl", "get", "--raw", P + expr.replace(" ", "%20").replace("[", "%5B").replace("]", "%5D")])
    return json.loads(raw)["data"]["result"]
bad = []
def one(label, expr, limit, scale=1.0, want=3, floor=None):
    r = q(expr)
    vals = {(x["metric"].get("instance") or "all"): float(x["value"][1]) * scale for x in r}
    print(f"  {label:34s} series={len(vals)}/{want} " + " ".join(f"{k.split(':')[0]}={v:.3f}" for k, v in sorted(vals.items())))
    if len(vals) != want: bad.append(f"{label}: expected {want} series, got {len(vals)} (blind instrument)")
    for k, v in vals.items():
        if v != v or (limit is not None and v > limit) or (floor is not None and v < floor):
            bad.append(f"{label}: {k} = {v:.3f} outside limit")
if a.mode == "start":
    one("leader changes, last 2h", "max by (instance)(increase(etcd_server_leader_changes_seen_total[2h]))", a.max_elections_2h)
    one("leader changes, last 24h", "max by (instance)(increase(etcd_server_leader_changes_seen_total[24h]))", a.max_elections_24h)
else:
    n = int(time.time()) - a.since_epoch
    print(f"  node mode: window since --since-epoch = {n} s")
    if a.since_epoch <= 0:
        bad.append("--since-epoch missing")
    elif n < 600:
        bad.append(f"window {n} s < 600 s: too short to read, refusing to pass")
    else:
        one(f"leader changes, last {n}s", "max by (instance)(increase(etcd_server_leader_changes_seen_total[%ds]))" % n, a.max_elections)
one("etcd_server_has_leader", "etcd_server_has_leader", None, floor=1.0)
one("WAL fsync p99 10m (ms)", "histogram_quantile(0.99,sum by (le,instance)(rate(etcd_disk_wal_fsync_duration_seconds_bucket[10m])))", a.max_fsync_ms, 1000.0)
one("backend commit p99 10m (ms)", "histogram_quantile(0.99,sum by (le,instance)(rate(etcd_disk_backend_commit_duration_seconds_bucket[10m])))", a.max_commit_ms, 1000.0)
print("VERDICT FAIL" if bad else "VERDICT PASS")
for b in bad: print("  -", b)
sys.exit(1 if bad else 0)
PY
.venv/bin/python3 "$SCR/etcdquiet.py"                                                          # GATE (start mode), at GO and at window start
.venv/bin/python3 "$SCR/etcdquiet.py" --max-elections-2h 999 --max-elections-24h 999 --max-fsync-ms 99999 --max-commit-ms 99999 | tail -1   # CONTROL A: VERDICT PASS (the read works, the pass path is reachable)
.venv/bin/python3 "$SCR/etcdquiet.py" --max-elections-2h 999 --max-elections-24h 999 --max-fsync-ms 0.001 --max-commit-ms 99999 | tail -5   # CONTROL B: VERDICT FAIL naming the three fsync rows
# --- per-node mode (before each drain; see the table). Example for node 2 after node 1 returned Ready at §3.10 ---
.venv/bin/python3 "$SCR/etcdquiet.py" --mode node --since-epoch "$(cat "$SCR/returned-<prev-node>.epoch")"             # GATE
.venv/bin/python3 "$SCR/etcdquiet.py" --mode node --since-epoch "$(( $(date +%s) - 900 ))" --max-elections -1 --max-fsync-ms 99999 --max-commit-ms 99999 | tail -4   # CONTROL C: must print VERDICT FAIL naming the three election rows (limit -1 can never hold, so the election check can fail on a quiet day too)
.venv/bin/python3 "$SCR/etcdquiet.py" --mode node --since-epoch "$(( $(date +%s) - 60 ))" --max-fsync-ms 99999 --max-commit-ms 99999 | tail -2   # CONTROL D: must print VERDICT FAIL "window 6x s < 600 s" (an unreadable window never passes)
```
**Stamps this plan writes (all `date +%s` into `$SCR`, so they survive separate Bash calls):** `quiet.epoch` immediately after PROC 3.8.0/3.8a
finish and BEFORE the canary gate; `returned-<node>.epoch` at the moment PROC 3.10 sees the node `Ready` (the first line of 3.10). The gate
refuses a window shorter than 600 s, so it cannot be run "early".

**PASS (start mode):** `VERDICT PASS`, twice, >= 15 min apart. **PASS (node mode):** `VERDICT PASS` - zero elections on 3/3 members since the
stamp, `etcd_server_has_leader` 1 x3, 10-min WAL fsync p99 < 50 ms, commit p99 < 100 ms. In every mode a series count other than 3/3 fails as a
*blind instrument*, so an unscraped etcd never reads as quiet. PROC 3.10b's `etcdgate.py` and `etcdstat.py converged` stay on top of this gate.
**Dry-run 2026-11-16 07:05Z (live, this exact script):** start mode printed `VERDICT FAIL` on the three 24 h rows only (51.0 / 51.0 / 54.0; the 2 h rows read 0.000
x3, fsync 24.9 / 25.5 / 14.8 ms, commit 15.8 / 15.7 / 14.0 ms, has_leader 1 x3); CONTROL A `VERDICT PASS`; node mode with `--since-epoch now-900` printed `VERDICT PASS`
(0.000 x3 over 901 s) and with `--max-elections -1` printed `VERDICT FAIL` on the three election rows (control C); a 61-s window printed `VERDICT FAIL`
`window 61 s < 600 s` (control D); a missing `--since-epoch` printed `VERDICT FAIL` `--since-epoch missing`. **Rule:** a failing start read is NO ROLL TODAY. The
churn's cause is not this plan's to fix (F-33873912, F-27a3f024); do not substitute a longer wait for a green gate on the day. A failing node-mode read before a
later node = STOP part-rolled (PROC 3.11 split rule, PROC 5.2); never roll a second node into an etcd that has elected since the last node returned.

### 2.3 Off-site restic fence (new): NO off-site Job may be running at ANY drain

**Why.** The off-site Jobs run on `k8s-nuc14-01` today. `backoffLimit` is 0 on every off-site CronJob and on the hand-created seed Job, so a drain that evicts the
pod leaves the Job `Failed` with a part-written restic repository and a lock; the seed (~16 h) restarts from the repository's dedup state and the nightly tier
misses a night (`OffsiteBackupStale` fires after 36 h). **Why the fence is "none Running", not "suspended".** `kubectl patch job ... suspend=true` is NOT a
pause for these Jobs: Kubernetes v1.36.0 `pkg/controller/job/job_controller.go` deletes the active pods of a suspended Job (`manageJob`, ~line 1785), counts a
deleted pod as FAILED (`isPodFailed`, ~line 2169-2178: "Count deleted Pods as failures") and fails the Job when `failed > backoffLimit` (line 1067, 1086), i.e.
immediately at `backoffLimit: 0`. A suspend therefore ends the Job as `BackoffLimitExceeded`, the same outcome as the eviction it was meant to avoid (read from
source 2026-11-16; NOT executed against the cluster, which is read-only here). The previous draft's "pause it" and the earlier "Flux reverts a kubectl pause" were both
wrong: Flux never touches a hand-created Job, and suspend is not a pause. The fence is therefore (1) wait for completion, or (2) an operator-approved knowing stop.

```bash
cat > "$SCR/offsite_fence.py" <<'PY'
import json, subprocess, sys
src = sys.argv[1] if len(sys.argv) > 1 else None   # test hook only: a saved `kubectl get jobs -n backup -o json`
def get(args):
    return subprocess.check_output(["kubectl", "get"] + args + ["-o", "json"], text=True)
jobs = json.loads(open(src).read() if src else get(["jobs", "-n", "backup"]))["items"]
cjs = json.loads(get(["cronjobs", "-n", "backup"]))["items"]
want = {"offsite-backup-apps": "30 0 * * *", "offsite-backup-core": "40 0 * * *",
        "offsite-backup-prune": "30 4 * * 0", "offsite-backup-check": "30 4 * * 3"}
got = {c["metadata"]["name"]: (c["spec"]["schedule"], c["spec"].get("timeZone"), bool(c["spec"].get("suspend")))
       for c in cjs if c["metadata"]["name"].startswith("offsite-")}
bad = []
for n, s in want.items():
    if n not in got: bad.append(f"cronjob {n} missing (blind instrument)")
    elif got[n] != (s, "Etc/UTC", False): bad.append(f"cronjob {n} reads {got[n]}, expected {(s, 'Etc/UTC', False)}: re-derive the overlap with the window")
for j in jobs:
    n = j["metadata"]["name"]
    if not n.startswith("offsite-"): continue
    st = j.get("status", {}); act = st.get("active") or 0
    print(f"  job {n:36s} active={act} succeeded={st.get('succeeded', 0)} failed={st.get('failed', 0)}")
    if act > 0: bad.append(f"job {n} is ACTIVE: a drain kills its pod and (backoffLimit 0) fails the Job")
print("VERDICT FAIL" if bad else "VERDICT CLEAR")
for b in bad: print("  -", b)
sys.exit(1 if bad else 0)
PY
.venv/bin/python3 "$SCR/offsite_fence.py"                      # GATE: VERDICT CLEAR
kubectl get pods -n backup --field-selector=status.phase=Running -o name | grep -c offsite     # second reader: must print 0 (this is premise offsite-restic-seed-not-running)
```
**Handles "no such Job".** The script lists Jobs (`kubectl get jobs -n backup`) instead of reading `job/offsite-seed-core` by name, so a seed Job that already
finished and was garbage-collected (`ttlSecondsAfterFinished: 604800`) or was never re-created reads as "no active job" = no fence, not as a `NotFound` error
that would turn into a false NO-GO. (The earlier draft's `kubectl get job offsite-seed-core -o jsonpath=...` errored with `NotFound` in exactly that case.)
Its blind-instrument guard is different: the four off-site CronJobs must exist with schedules `30 0 * * *`, `40 0 * * *`, `30 4 * * 0`, `30 4 * * 3`, timeZone
`Etc/UTC`, not suspended - a missing or changed one prints `VERDICT FAIL` because the "nothing fires inside the window" argument below depended on them.
**Dry-run 2026-11-16 07:05Z:** live printed `VERDICT FAIL` naming the two ACTIVE jobs (`offsite-backup-core-29913160`, `offsite-seed-core`; `offsite-backup-apps-29913150`
Complete); a saved copy of that Job list with `status.active` set to 0 printed `VERDICT CLEAR`; an EMPTY Job list printed `VERDICT CLEAR` (the NotFound-equivalent case).
**Scheduled Jobs cannot start inside the window by construction:** daily 00:30 / 00:40 UTC, prune Sun 04:30 UTC, check Wed 04:30 UTC, against `sun-attended` 09:00
Europe/Berlin = 08:00 UTC (CET) to at most 11:20 UTC; only a Job that is still running from before 08:00 can overlap, and that is what the gate reads.

**If the gate is not CLEAR at the GO (days ahead):** nothing to do - the seed finishes on its own (the Job allows 48 h; a long nightly core run is the same Job class).
**If it is not CLEAR at window start:** the default is NO-GO until it is. The only alternative is an OPERATOR-APPROVED KNOWING STOP, recorded in the run log with the
operator's go: `kubectl delete job -n backup <name> --wait=true` (a direct mutation of a hand-created or CronJob-spawned Job, not Flux-managed; the pod gets SIGTERM and a
30 s grace, and restic's SIGTERM handler removes its repository lock - `cmd/restic/cleanup.go` in v0.19.1 registers SIGINT and SIGTERM). Then re-run the gate (CLEAR), record
the stop in the window report, and AFTER the window re-create the Job per `docs/sops/backup.md` ("Seed or run now": `kubectl create job -n backup <new-name> --from=cronjob/offsite-backup-core`)
and run its lock check; restic dedups, so the cost is time, not data. The nightly 00:40 core Job re-creates itself; the seed does not.
**Before EVERY drain (canary, node 2, node 3) re-run both lines above**: a Job created since window start would die with the node. Also record the nightly Longhorn backup state: PROC 2.6
(`storage/daily-backup-all-volumes`, 23:00 UTC).

### 2.4 Newer 1.14.x patch? (PROC §2.2b, retargeted)

```bash
gh api repos/siderolabs/talos/releases --jq '[.[] | select(.prerelease==false) | select(.tag_name|test("^v1[.]14[.]"))] | .[0] | "\(.tag_name)  \(.published_at)"'
gh api repos/siderolabs/talos/releases --jq '[.[] | select(.prerelease==false) | select(.tag_name|test("^v1[.]13[.]"))] | .[0] | "\(.tag_name)  \(.published_at)"'   # control: a DIFFERENT line
```
*Dry-run 2026-11-16:* first line `v1.14.6  2026-11-11T19:51:33Z`. Decision table exactly as PROC §2.2b: `v1.14.6` → proceed;
newer `v1.14.N` → **default stay on v1.14.6**, retarget only under SD-6 with the operator present and every §3.0 row
re-derived. A stable v1.15.x is out of scope.

### 2.5 Everything else (executed as PROC §2, in order)

PROC §2.0 helper files (ten helpers: `lh_gate.py`, `etcdstat.py`, `nodegate.py`, `probe.py`, `hwmon.py`, `cifsproof.py`,
…) written with their negative controls; §2.0b freeze + ImageUpdateAutomation enumeration; §2.1 baselines (Longhorn
census 79 volumes / 158 replicas expected, re-read after `longhorn-1.13.0`); §2.3b/§3.10b latency gates; §2.4 roll
order read from LIVE etcd leader (the leader is `.11` today, not the 1.14.5 comment's `.13`); §2.5 Longhorn arithmetic;
§2.6 backup freshness; §2.8 hwmon/alerts baselines; §2.12b node-pinned workloads (frigate@02, matter-server+otbr@03).
`kube-prometheus-stack` must not change on the day: the deny rule `*kube-prometheus-stack*` in
`runbooks/auto-update-policy.yaml` holds Renovate's PR out of Step 0 and has no expiry field (comment: revisit by 2026-12-31) — re-check it covers the
slot; `kube-prometheus-stack-93.3.0` (draft) is in `conflicts_with`.

## 3) Steps

### 3.0 Substitution table - v1.14.5 -> v1.14.6 (COMPLETE: every PROC line that carries a v1.14.5-bearing value, 117 of them, is a row below)

PROC lines 1-433 are its frontmatter and banner and 434-618 its section 1 narrative: **replaced by this file's own frontmatter and section 1**, never executed.
Lines 619-3096 (sections 2-7 and the open items) are executed or read; the awk line in section 2.0 lists every line there that matches
`1.14.5|1145|6.18.58|c865077b`, and the expected output is EXACTLY these 117 numbers:

```
630 633 642 648 650 651 652 653 992 1065 1112 1436 1440 1449 1462 1474 1485 1501 1502 1509 1510 1511 1512 1515 1516 1518 1520 1528 1553 1561 1567 1569 1573 1574 1575 1578 1589 1591 1597 1599 1611 1618 1621 1714 1715 1795 1797 1803 1912 1940 1941 1942 1947 1948 1950 1951 1955 1957 1982 2058 2083 2086 2108 2129 2133 2141 2157 2165 2167 2170 2175 2217 2218 2237 2244 2302 2346 2357 2370 2430 2521 2612 2620 2631 2635 2649 2663 2666 2682 2685 2695 2704 2763 2771 2809 2868 2870 2871 2877 2878 2890 2891 2894 2896 2901 2906 2923 2925 2937 2949 3017 3056 3072 3076 3085 3095 3096
```
Every number is covered by one row below or by the "read as the new target" group. Rows S1-S12 keep the numbering of the first draft; S13-S26 were added by review
(the first draft's table listed 13 rows and skipped, among others, the freeze announcement, the etcd snapshot name, the commit and revert messages, the K2/K3/K4
expected strings and the 5.5 grep). **Value rows** mean the executing session applies the new reading when it reaches that PROC line; where a row says "sed below" the
substitution is a literal edit whose diff is pasted below. Everything not on the list is the CURRENT state (v1.14.1, etcd 3.7.1, kubelet v1.36.0) or does not move (etcd 3.7.3,
containerd 2.3.7, K8s 1.36.6, rollback target v1.14.1).

| Row | PROC lines | v1.14.5 text in PROC | v1.14.6 reading | Evidence |
|---|---|---|---|---|
| S13 | 630, 1112, 1982 | `SCR="$HOME/.cache/talos-1145"` (setup and the two per-call re-sets) | `talos-1146` | scratch dir only; this file's section 2.0 already uses it |
| S14 | 633 | `plan-premises.py talos-linux-1.14.5 --require-premises` | `talos-linux-1.14.6` | this plan's section 2.1 runs it |
| S15 | 642, 648, 650, 651, 652, 653 | PROC 2.2b newer-patch check (`v1.14.5` is the head) | replaced by THIS file's section 2.4 (head must read `v1.14.6`) | `gh api` 2026-11-16 printed `v1.14.6  2026-11-11T19:51:33Z` |
| S16 | 992, 2302 | `talos-1145-` nonce / probe string (`etcdstat.py` canary nonce; the pgadmin write-read probe in CA1) | `talos-1146-` | a label written to a file and read back; any unique string works, the compare is against itself |
| S17 | 1065 | freeze announcement `... until the talos-linux-1.14.5 window ends` | `... until the talos-linux-1.14.6 window ends` | text read by the other sessions; they must see the new plan id |
| S1 / S4 | 1436, 1440, 1501, 1502 | `for TAG in v1.14.5 v9.9.9`; PASS `v1.14.5 HTTP 200`; 3.4 head `v1.14.5` | `v1.14.6`; PASS `v1.14.6 HTTP 200` and `v9.9.9 HTTP 404`; 3.4 head `v1.14.6` (a newer patch follows 2.4) | measured 2026-11-16 (control 404, real tag 200); amd64 index digest `sha256:d488effdca3f6f0d667d5ea61e31a6831e51290ccf49b0980d93ba301f575c10`, pinned by premise `factory-publishes-schematic-v1.14.6` |
| S2 / S3 | 1449, 1462, 1474, 1485 | `talosVersion: v1.14.5` and the deny-rule `currently v1.14.5)` text (seds and the pasted diff) | `v1.14.6` (seds and diff below) | BSD-sed dry-run 2026-11-16, diff pasted below |
| S5 | 1509, 1510, 1511, 1512, 1515, 1516 | `talosctl-1.14.5`, `.../v1.14.5/talosctl-darwin-arm64`, `sha256sum.txt` URL, `shasum`, `version --client` ; hash `c865077b...3096`; client says `Talos v1.14.5` | `talosctl-1.14.6`, `.../v1.14.6/...`; hash **`dd290798702d60ce8c1f59f4c223d5bdbc9c0638db45a9827d7f6cb4bd4a3f39`**; client says `Talos v1.14.6` | `sha256sum.txt` re-read 2026-11-16 07:05Z (same hash); PASS only if published line AND `shasum -a 256` agree |
| S6 | 1518, 1520, 1528, 1553, 1561, 1567, 1569, 1573, 1574, 1575, 1578 | `T2="$SCR/talosctl-1.14.5"`; both `--image=...:v1.14.5` flags in the talhelper line; the PASS text naming 1.14.5 (`is valid for metal mode`, `DIFFERENT = v1.14.5 has something new`, `1.14.5-only line`, `negA NOT yet run with v1.14.5`) | `talosctl-1.14.6`; `--image=...:v1.14.6` (both flags, same value); every `1.14.5` in that PASS text reads `1.14.6` | controls A and B are re-run in-window, never assumed; `wn145.txt` / `wn141.txt` are only file names, keep them |
| S7 | 1589, 1591, 1597, 1599, 1611 | commit message: file `talos-1145-commit-msg.txt`; subject `node image v1.14.1 -> v1.14.5`; `validates identically under talosctl 1.14.1 and 1.14.5`; `v1.14.2..v1.14.5: kernel 6.18.58`; `Plan: ...talos-linux-1.14.5.md` | `talos-1146-commit-msg.txt`; `-> v1.14.6`; `1.14.1 and 1.14.6`; `v1.14.2..v1.14.6: kernel 6.18.63` (etcd 3.7.1 -> 3.7.3 and containerd 2.3.7 stay as written); `Plan: ...talos-linux-1.14.6.md` | `Supersedes Renovate PR #248` stays true: #248 now carries `talosVersion: v1.14.6` |
| S18 | 1618, 1621 | PR #248 `rebased to v1.14.5`; `gh pr close 248 --comment "landed via <sha> (plan talos-linux-1.14.5 §3.7)"` | `rebased to v1.14.6`; `... (plan talos-linux-1.14.6 §3.7)` | `gh pr list` 2026-11-16: #248 `v1.14.1 -> v1.14.6` |
| S19 | 1714, 1715 | `etcd-pre-v1.14.5.db` (snapshot, chmod, stat: three uses) | `etcd-pre-v1.14.6.db` | file name |
| S8 / S9 | 1795, 1797, 1803, 2430, 2521, 2058, 2346, 2357 | `Tag: v1.14.5`; `Talos (v1.14.5)`; kernel `6.18.58-talos`; "a canary that came back on v1.14.5" | `Tag: v1.14.6`; `Talos (v1.14.6)`; kernel **`6.18.63-talos`**; containerd `containerd://2.3.7` unchanged | `constants.go` at both tags and release.toml `Linux: 6.18.63`; PASS compares against the live `kernelVersion` column |
| S12 | 1940, 1941, 1942, 1947, 1948, 1950, 1951, 1955, 1957 | 3.12 CLI pin: heading `-> 1.14.5`; `grep -c 'Talos (v1.14.5)'`; the `.mise.toml` sed; `talos-1145-cli-msg.txt`; commit text `1.14.1 -> 1.14.5`, `report Talos v1.14.5`; `Client v1.14.5, servers v1.14.5`; `Fewer than 3 nodes on v1.14.5` | `1.14.6` everywhere (sed and diff below); PR #247 now reads `1.14.1 -> 1.14.6`; still LAST, after 5.4 | BSD-sed dry-run 2026-11-16 on a scratch copy of `.mise.toml`, diff pasted below |
| S20 | 2083, 2086, 2108 | k8s-1.36.5 follow-up text `accepts a uniform v1.14.5`; K3 line count `12` = installer pair `:v1.14.1 -> :v1.14.5`; `client v1.14.1, servers v1.14.5` | `v1.14.6` in all three; the count stays `12` | shape only (two installer-image lines plus the five K8s pairs); re-measured in-window at 3.K3 |
| S21 | 2129, 2133, 2141 | 3.K2 expected diff: context line `talosVersion: v1.14.5` (three places in the block) | `talosVersion: v1.14.6` | the only context line that moves |
| S22 | 2157 | 3.K3 PASS: installer pair `:v1.14.1 -> :v1.14.5` | `:v1.14.1 -> :v1.14.6` | same shape: 12 lines per node, 0 non-image lines |
| S23 | 2165, 2167, 2170, 2175 | 3.K4 `(now v1.14.5)` and the grep `'Talos version 1.14.5 is compatible with Kubernetes version 1.36.6'`; PASS text `names 1.14.5` | `Talos version 1.14.6 is compatible with Kubernetes version 1.36.6` (count 3); `names 1.14.6`; `1.14.1` still means a node is not on the target | string measured on the same code path as 1.14.5; confirmed in-window by the count of 3 |
| S24 | 2217, 2218 | 3.K7 commit text `plan talos-linux-1.14.5, Phase K` and `after the v1.14.5 node roll` | `talos-linux-1.14.6` / `v1.14.6` | text |
| S25 | 2244 | `did not boot v1.14.5's machined` | `v1.14.6's machined`; expectation `/sbin/modprobe` unchanged | the sysctl default is the same in v1.14.6 |
| S26 | 2635, 2649, 2704, 2763 | 5.1 `Tag: v1.14.5` (two reads); 5.3 revert message `talos-1145-revert-msg.txt`, `Revert Talos v1.14.5 node config`, `Plan: talos-linux-1.14.5`; 5.5 `grep -c '^talosVersion: v1.14.5$'` expecting 1 | `v1.14.6` / `talos-1146-` / `talos-linux-1.14.6`; the grep expects `^talosVersion: v1.14.6$` | rollback target stays **v1.14.1** (`Tag: v1.14.1` after the downgrade-upgrade) |
| S10 / S11 | (none) | etcd 3.7.3 on rolled members; rollback image `:v1.14.1` | **unchanged** | `DefaultEtcdVersion = "v3.7.3"` at v1.14.5 AND v1.14.6; no upgrade/sequencer file in the compare |

**Read as the new target, no edit needed (prose, history or reciprocity text that merely names the plan or version):** PROC lines 1912, 2612, 2631, 2663, 2666, 2682,
2685, 2695, 2771 (rollback/abort prose: "v1.14.5" means the roll's target, read it as v1.14.6), 2809, 2868, 2870, 2871, 2877, 2878, 2890, 2891, 2894, 2896, 2901, 2906 (reciprocity and
sibling-plan prose; this plan's section 6 supersedes it), 2923, 2925 (kernel `6.18.58` in the risk table: read `6.18.63`), 2937, 2949, 3017, 3056, 3072, 3076, 3085, 3095, 3096
(open-item history). **Kept as written because still true for v1.14.6:** 2237 (on-demand module loading arrived in v1.14.5 and persists), 2370 (the `/etc/hosts` rendering change arrived in
v1.14.5), 2620 (the `Rollback` source files are unchanged between v1.14.4, v1.14.5 and v1.14.6; the v1.14.5...v1.14.6 compare listed no upgrade/sequencer file).

**S2/S3 dry-tests (BSD sed, scratch copies of the live files, 2026-11-16):**
```bash
sed -i '' -e 's|^talosVersion: v1\.14\.1$|talosVersion: v1.14.6|' kubernetes/bootstrap/talos/talconfig.yaml
git --no-pager diff kubernetes/bootstrap/talos/talconfig.yaml
sed -i '' -e 's|kubernetes/bootstrap/talos/talconfig.yaml, currently v1\.14\.1), so it must|kubernetes/bootstrap/talos/talconfig.yaml, currently v1.14.6), so it must|' runbooks/auto-update-policy.yaml
git --no-pager diff runbooks/auto-update-policy.yaml
```
Resulting `-`/`+` pairs (the only lines that may differ; assert `1 insertion(+), 1 deletion(-)` per file, then bump the
policy file's `version:` to the day's date, currently `"2026.11.07"`; `@@` numbers drift, never assert them):
```diff
-talosVersion: v1.14.1
+talosVersion: v1.14.6
-      kubernetes/bootstrap/talos/talconfig.yaml, currently v1.14.1), so it must
+      kubernetes/bootstrap/talos/talconfig.yaml, currently v1.14.6), so it must
```
**S12 dry-test (BSD sed on a scratch copy of the live `.mise.toml`, 2026-11-16; the CLI-pin line carries a trailing comment that the sed leaves alone):**
```bash
sed -i '' -e 's|^"aqua:siderolabs/talos" = "1\.14\.1"  # CLI pin|"aqua:siderolabs/talos" = "1.14.6"  # CLI pin|' .mise.toml
git --no-pager diff .mise.toml          # exactly ONE -/+ pair
```
```diff
-"aqua:siderolabs/talos" = "1.14.1"  # CLI pin — track the CLUSTER (talosVersion in
+"aqua:siderolabs/talos" = "1.14.6"  # CLI pin — track the CLUSTER (talosVersion in
```
Preconditions measured clean 2026-11-16: `git status --porcelain kubernetes/bootstrap/talos runbooks/auto-update-policy.yaml`
printed nothing. If either file has foreign uncommitted edits in-window: STOP, let that session land first, commit with
`git commit --only <path>`, and confirm `git log -1 --format=%s` is yours before pushing.

### 3.1 Phase A - PREP (PROC §3 Phase A, 3.1 -> 3.12 with §3.0 applied) and Phase B - THE ROLL (PROC §3 Phase B)

Execute PROC Phase A and Phase B **step by step as written**, with §3.0 substituted, plus these insertions (each is a gate that can fail; none replaces a PROC gate):
1. **Fence and quiet, in this order, before the canary drain.** (a) §2.3 `offsite_fence.py` must print `VERDICT CLEAR` and the `grep -c offsite` line `0`.
   (b) After PROC 3.8.0 (defrag) and 3.8a (snapshot) finish: `date +%s > "$SCR/quiet.epoch"`; wait >= 10 min (use it for PROC 3.8's re-check and the canary
   go/no-go reads); then `etcdquiet.py --mode node --since-epoch "$(cat "$SCR/quiet.epoch")"` must print `VERDICT PASS`. The start-mode gate (§2.2) was already
   passed twice at window start; it is NOT re-run here.
2. **Before node 2 and node 3 (each drain):** `etcdquiet.py --mode node --since-epoch "$(cat "$SCR/returned-<previous node>.epoch")"` must print `VERDICT PASS`, AND
   §2.3 re-run (CLEAR, `0`). The previous node's `returned-<node>.epoch` is written at the first line of PROC 3.10 (`date +%s`, node seen `Ready`). A FAIL with a node
   already on v1.14.6 = STOP part-rolled (PROC §3.11 split rule; PROC §5.2). Never roll a second node into an etcd that has elected since the last node returned.
3. **After each node returns:** run CA8 (§4.1) on that node, in addition to PROC §4.1.
4. **Never re-run `plan-premises.py` mid-roll** (§2.1): `nodes-on-v1.14.1`, the etcd `3.7.1` group and both election premises are pre-roll facts.

### 3.2 Phase K — Kubernetes v1.36.0 → v1.36.6 (PROC §3 Phase K, unchanged; expected to DEFER)

Run only if PROC §3.K0's clock admits it. **Two deltas for v1.14.6:** (a) PROC §3.K4's read-only dry-run is now expected
to show *affinity* hunks on Talos bootstrap objects (commit `a02b84749`, §1.2) — read it object by object, and STOP on any
`delete` or any object outside the 7-entry inventory (premise `bootstrap-inventory-7`); (b) after §3.K3's re-render run
CA9. The `siderolabs/kubelet` deny-rule reason defect (PROC Open item 7) stands.

## 4) Verification

PROC §4.1–§4.7 apply, with §3.0 S9–S10 expectations (kernel `6.18.63-talos`, etcd 3.7.3 on rolled members). New and
changed gates:

### 4.1 CONTENTS ASSERTIONS added by this plan

**CA8 — partition table intact after the kernel/discovery change** (per node, after it returns; baseline = the same read
before the roll):
```bash
cat > "$SCR/voloffset.py" <<'PY'
import sys, subprocess, yaml
ip, zero_inject = sys.argv[1], (len(sys.argv) > 2 and sys.argv[2] == "--inject-zero")
out = subprocess.check_output(["talosctl", "-n", ip, "get", "discoveredvolumes", "-o", "yaml"], text=True)
rows = [d for d in yaml.safe_load_all(out) if d]
parts = [(d["metadata"]["id"], d["spec"].get("offset"), d["spec"].get("size"), d["spec"].get("partition_label")) for d in rows
         if str(d["metadata"]["id"]).startswith("nvme") and "p" in str(d["metadata"]["id"])[4:]]
if zero_inject and parts: parts[-1] = (parts[-1][0], 0) + parts[-1][2:]
bad = [p for p in parts if not p[1]]
print(ip, "partitions=%d" % len(parts), " ".join(f"{p[0]}@{p[1]}" for p in parts))
print("VERDICT", "FAIL (zero/absent offset: %s)" % [p[0] for p in bad] if bad or len(parts) < 4 else "PASS")
PY
.venv/bin/python3 "$SCR/voloffset.py" 192.168.55.12              # per node; repeat for .11 / .13
.venv/bin/python3 "$SCR/voloffset.py" 192.168.55.12 --inject-zero | tail -1   # CONTROL: must print VERDICT FAIL naming nvme0n1p6
```
CONTENTS ASSERTION: every `nvme0n1pN` DiscoveredVolume on the returned node has a non-zero `offset` and ≥ 4 partitions —
measured by `voloffset.py`, compared to the 2026-11-16 baseline on all three nodes (`p1@1048576 p2@105906176
p3@106954752 p4@1155530752 p5@1156579328 p6@1261436928`, six partitions, `VERDICT PASS`). Guards the one v1.14.6 change
that touches disk bookkeeping (`8f6c141db`). It fails on a zeroed offset (control proves it) and on a missing partition
table (`partitions=0` < 4). It is a floor on the *discovery view*, not a data-integrity proof: Longhorn and CIFS proofs in
PROC §4.1–§4.2 remain the data-path gates.

**CA9 — encryption layout untouched** (only if Phase K re-renders; PROC §3.K3):
```bash
grep -c -E '^ +- secretbox:|^ +- name: key2|^ +- identity:' kubernetes/bootstrap/talos/patches/controller/kube-etcd-encryption.yaml     # expect 3
talosctl --nodes=192.168.55.11 get machineconfig v1alpha1 -o yaml | grep -c -E '^ +- secretbox:|^ +- name: key2|^ +- identity:'   # expect 3
talosctl --nodes=192.168.55.11 get machineconfig v1alpha1 -o yaml | grep -c -i aescbc                                           # expect 0
echo '- aescbc:' | grep -c -i aescbc                                                                                          # CONTROL: must print 1 (the detector can fire)
```
CONTENTS ASSERTION: the live encryption providers are still `secretbox key2` + `identity` and **no** `aescbc` provider
exists — the first two lines each print `3`, the third `0`, the control `1` (measured 2026-11-16: `3`, `3`, `0`, `1`). A
render that silently switched providers would print a different count on line 2 or non-zero on line 3 and would make every
stored Secret unreadable. Measured on the live machine config and the repo patch, not a status flag. `grep -c` exits 1 when
it prints `0`: read the printed number, not `$?` (pipefail aside).

### 4.2 CONTROLs (named instruments; `plan-premises.py --controls talos-linux-1.14.6` checks them)

CONTROL: metric etcd_server_leader_changes_seen_total — §2.2 reads `increase()` per member: start mode over 2 h and 24 h (ceiling 0 / 5.5), node mode since the last QUIET/RETURNED stamp (ceiling 0, window >= 600 s); floor: exactly 3 series.
CONTROL: metric etcd_disk_wal_fsync_duration_seconds_bucket — §2.2 p99 over 10 m per member, ceiling 50 ms, 3/3 series (an unscraped histogram prints no series and fails).
CONTROL: metric etcd_disk_backend_commit_duration_seconds_bucket — §2.2 p99 over 10 m, ceiling 100 ms, 3/3 series.
CONTROL: metric etcd_server_version — PROC §4.4 #2: server_version count by group 3.7.1 ×3 before, 3.7.3 ×3 after (premise `etcd-protocol-3.7`).
CONTROL: metric kubernetes_build_info — Phase K floor: 12 series (premise `build-info-scraped-12`), then 12 at v1.36.6.
CONTROL: alertname etcdDatabaseHighFragmentationRatio — not firing at the end of the window (PROC §3.8.0 defrags before the roll; a firing alert afterwards means the db grew back or the defrag was skipped); PROC §4.4 #11 compares the whole alert SET against §2.8.

### 4.3 Whole-cluster verification

PROC §4.4 #1–#11 as written (S9: kernel `6.18.63-talos`), then PROC §4.5–§4.7 for Phase K, then **a 24 h soak read** the
next morning: `etcdquiet.py` with `--max-elections-2h 999` is NOT the soak gate; the soak gate is the 24 h election line
< 6 **and** no pattern-(ii) triage record (PROC §3.10). The roll itself MAY raise elections on each reboot (the
expected, pre-recorded ones per PROC §3.10a); only an *unrecorded* election is a FAIL.

## 5) Rollback

PROC §5 applies unchanged: **§5.1 per-node, DRAINED** (`talosctl upgrade --image <factory installer>:v1.14.1` on a Ready
node; bare `talosctl rollback` is only for a NotReady node and does not drain), **§5.2 stop, don't unwind** (a part-rolled
cluster, nodes on mixed v1.14.1/v1.14.6, is a supported steady state while etcd is healthy), §5.2a window aborted before the
canary, §5.3 git revert only after no node runs v1.14.6 (the commit is inert; Flux does not reconcile
`kubernetes/bootstrap/talos/`), **§5.4 lift the push freeze on EVERY exit path**, §5.5 Phase K → 1.36.0 (`upgrade-k8s --to
v1.36.0`). Additions for this plan:
- **etcd gate trips mid-roll (§2.2 node-mode FAIL before node N+1):** STOP, do not roll further, lift the freeze per PROC §5.4,
  record the node list and the stamp used; the cluster is safe part-rolled. The etcd snapshot of PROC §3.8a is the defence in depth
  (`talosctl etcd snapshot`, mode 600, in `$SCR`; restore path `docs/sops/etcd.md` / `docs/sops/disaster-recovery.md`).
- **Off-site Job killed (by a drain, or by the operator-approved stop of §2.3):** `kubectl get jobs -n backup | grep offsite` reads `Failed`/absent for the seed or the
  nightly core Job; follow `docs/sops/backup.md` "Seed or run now" (`kubectl create job -n backup <new-name> --from=cronjob/offsite-backup-core`; apps likewise), then run its
  restic lock check before the next nightly. No data is lost (append-only restic repo, dedup); the cost is time. Do NOT use `suspend` on these Jobs (§2.3: it fails them).
- Confirm back on target: `kubectl get nodes -o jsonpath='{.items[*].status.nodeInfo.osImage}'` prints the intended
  per-node versions and `etcdstat.py converged` passes (PROC helpers).

## 6) Interference notes

- **Exclusive Sunday.** `exclusive: true`; the slot is the operator's call. Slot facts: `sun-attended:2026-11-22` is
  currently held by `talos-linux-1.14.5`; `longhorn-1.13.0` (its `depends_on`) missed `11-15`, so 11-22 may be consumed by
  that plan instead — re-read `maintenance-plan.py --open` before assigning. `redis-fleet-8.10.3` is on 11-29 (the
  continuation Sunday PROC §6.2 reserves); `helm-drift-detection` sat-attended 11-28. A hard-churn day is NO ROLL: the plan
  returns to the queue, it is not rescheduled into a Saturday (needs `allow_reboot`, Sunday only).
- **Reciprocity owed** (conflicts here, not named back): every plan in this file's `conflicts_with` still names
  `talos-linux-1.14.5` only. `etcd-timeouts-5000-500` (blocked) must name `talos-linux-1.14.6` and its owner must pick up
  §1.4. `talos-power-tuning-ab` baselines (kernel 6.18.51) will be re-baselined on 6.18.63.
- **Shared surfaces** (`touches.shared`): apiserver, etcd, cilium, coredns, longhorn, envoy gateway + public edge,
  authentik, cert-manager, `monitoring` (the window's instrument — no Prometheus change same day), `igpu-i915`,
  `cifs-share`, `flux-source`/`git-main` (push freeze), `offsite-backup` (§2.3), node-pinned home-automation
  (frigate@02, matter-server+otbr@03).
- **`depends_on: [longhorn-1.13.0]`** — never roll nodes with a Longhorn engine/manager move in flight, and the rebuild
  gates are priced at the limit 2 that plan leaves alone.
- **Duration:** 180 = the sun-attended schedulable cap (200 − 20 Step 0), priced as PROC §7 (OS roll 165–290 depending on
  rebuild time R at limit 2, UNMEASURED; the canary measures it; Phase K 45 defers). v1.14.6 changes no mechanics. §2.2's two
  15-minute-apart reads add ≤ 20 min at window start and are inside Step 0's slack only if Step 0 finishes early: if
  the window cannot afford them, that is a reason not to start.

## Open items / repo corrections (reported, not worked around)

1. **Operator decision owed:** `etcd-timeouts-5000-500` was ordered BEFORE the roll on 2026-11-02; it is now `blocked`
   (Talos refuses `service etcd restart`). This plan drops it from `depends_on` and recommends the reboot-based follow-up of
   §1.4. The operator must confirm or reverse; if it should instead gate this roll, the roll cannot be scheduled until
   that plan is re-planned and executed (3 reboots of its own).
2. **The churn is the real blocker** (41 elections / 24 h, 154 / 7 d, 88 ms fsync spikes on shared consumer NVMe). No plan in
   the queue removes the cause; F-33873912 / F-27a3f024 own it. Rolling three drained nodes into it is the F-2cb2dbc9 failure
   pattern; §2.2 is the guard, not the fix.
3. **`talos-linux-1.14.5` `conflicts_with` carries `grafana-chart-14.4.0`, which matches no plan file** (DEAD-REF there).
4. **`docs/sops/talos-upgrade.md` §14.x etcd-restart guidance and the `etcd-timeouts-5000-500` §3.4 `service etcd restart`
   step are wrong on Talos ≥ 1.14.1** (F-be3f5bf0): the mechanism is a reboot. Reported, not edited.
5. **PROC Open items 1–14 still stand** (stale `talos-upgrade.md` §14.2 live-config text, ImageUpdateAutomation suspend rule,
   `siderolabs/kubelet` deny-rule reason, `talos-power-tuning-ab` premise, …); this file re-derives none of them.
6. Premise `factory-publishes-schematic-v1.14.6` can exceed the runner's 60 s on a cold factory tag (measured: > 2 min for the
   first v1.14.6 request, then instant). Warm it once at Phase A (§3.1 does).
7. **Repo correction (found while fencing the off-site Jobs): `suspend` is not a pause for a `backoffLimit: 0` Job.** Kubernetes v1.36.0
   `job_controller.go` deletes a suspended Job's active pods, counts a deleted pod as failed (`isPodFailed`, "Count deleted Pods as failures") and fails the Job when
   `failed > backoffLimit` (lines 1067 and 1086). Any SOP, plan or agent advice that says "suspend the seed Job before maintenance" would fail it exactly as an eviction does. Read from
   source, not executed (cluster read-only); verify on a scratch Job before ever relying on the opposite. `docs/sops/backup.md` has no such advice today; the first draft of this
   plan did, and the same draft's "Flux reverts a kubectl pause" was wrong too (Flux never touches a hand-created Job). Not edited in the SOP; reported.
8. **Per-node absolute etcd election gates cannot pass after the first reboot** (first-draft defect of this plan, fixed in §2.2). The same shape is worth checking in
   `talos-linux-1.14.5` (PROC 2.3's "< 6 in 24 h" is a start-of-window rule; its per-node gate is PROC 3.10b) - reported, that file was not edited.
