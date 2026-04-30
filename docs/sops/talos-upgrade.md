# SOP: Talos Linux Upgrade with Performance Tuning

> Description: Upgrade Talos Linux from v1.11.0 → v1.12.6 and apply missing performance patches (intelgpu, udev, enhanced sysctls, kubelet reservations, RPS fix). Unblocks OTBR (Thread border router) via `CONFIG_IPV6_MROUTE=y` now present in v1.12.x kernels. Keeps `powersave` CPU governor for home-lab power profile.
> Version: `2026.04.30`
> Last Updated: `2026-04-30`
> Owner: `homelab-ops`

> **Reader's note (2026-04-30):** Sections 1–12 are the canonical reference for a single-minor Talos upgrade. The cluster has since been taken to Talos `v1.13.0` + Kubernetes `v1.36.0` via two stages — see **§13 Stage A → Stage B path (v1.11.0 → v1.13.0)** for the multi-minor traversal procedure and the lessons learned during that run.

---

## 1) Description

Full-cluster Talos upgrade combined with a performance tuning sweep. Performs a rolling node upgrade using `talhelper`-generated configs, then re-enables OTBR which is currently blocked by a missing kernel option.

- **Scope**: All 3 control-plane nodes (`k8s-nuc14-01/02/03`), Kubernetes version, Longhorn v1 volumes migrate automatically through rolling upgrade.
- **Prerequisites**:
  - `talosctl`, `talhelper`, `kubectl`, `flux`, `mise`, `sops` available via `mise`
  - Healthy cluster: 0 firing Prometheus alerts, all Longhorn volumes `healthy`, all Flux kustomizations `Ready`
  - Backups verified: last `daily-backup-all-volumes` Longhorn job `Complete` within 24h
  - Maintenance window: ~60-90 minutes (one node at a time, replicas rebuild ~10-15 min per node)
- **Out of scope**: Longhorn v2 data engine enablement (still Technical Preview, see section 12 for notes)

---

## 2) Overview

| Setting | Current | Target |
|---------|---------|--------|
| Talos version | v1.11.0 | **v1.12.6** |
| Kubernetes version | v1.34.0 | **v1.35.x** (latest in v1.35 line) |
| Kernel | 6.12.43 | **6.18.18** |
| `CONFIG_IPV6_MROUTE` | not set | **=y** ← unblocks OTBR |
| CPU governor | `powersave` | `powersave` (unchanged — home-lab power profile) |
| `machine-intelgpu.yaml` | ❌ not wired | ✅ applied |
| `machine-udev.yaml` | ❌ not wired | ✅ applied |
| Kubelet reservations | none | `systemReserved` + `kubeReserved` |
| RPS mask | `ffff` (16 CPUs) | `3ffff` (18 CPUs) |
| Conntrack tuning | default | `nf_conntrack_max=1048576` |
| BBR congestion control | off | on (`tcp_congestion_control=bbr`) |
| Source of truth | `kubernetes/bootstrap/talos/talconfig.yaml` | same |

---

## 3) Blueprints

Declarative source of truth is `talhelper`-managed. Regenerate cluster configs after editing `talconfig.yaml` or any patch.

- **Source of truth**: `kubernetes/bootstrap/talos/talconfig.yaml`
- **Generated configs**: `kubernetes/bootstrap/talos/clusterconfig/kubernetes-k8s-nuc14-0{1,2,3}.yaml` (SOPS-encrypted)
- **Patches**: `kubernetes/bootstrap/talos/patches/global/*.yaml` and `patches/controller/*.yaml`

### Files to create/modify

| File | Action |
|------|--------|
| `talconfig.yaml` | Bump versions, add 2 missing patches |
| `patches/global/machine-sysctls.yaml` | Add BBR, conntrack, fd, vm.max_map_count |
| `patches/global/machine-kubelet.yaml` | Add systemReserved, kubeReserved |
| `patches/global/machine-network-rps.yaml` | Change mask `ffff` → `3ffff` |
| `patches/global/machine-intelgpu.yaml` | (already exists, just wire it in) |
| `patches/global/machine-udev.yaml` | (already exists, just wire it in) |
| `kubernetes/apps/home-automation/kustomization.yaml` | Uncomment `./otbr/ks.yaml` (after upgrade) |

---

## 4) Operational Instructions

### Step 0 — Pre-flight checks

```bash
# All run from repo root
cd /Users/mu/code/cberg-home-nextgen

# 0.1 Verify cluster healthy
mise exec -- kubectl get nodes
mise exec -- flux get kustomizations -A | grep -vE "True|^NAMESPACE"  # should be empty
mise exec -- kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &
sleep 2
curl -s http://localhost:9090/api/v1/alerts | python3 -c "
import sys,json
a=[x for x in json.load(sys.stdin)['data']['alerts'] if x['state']=='firing' and x['labels']['alertname'] not in ('Watchdog','InfoInhibitor')]
print(f'Firing alerts: {len(a)}')"
kill %1 2>/dev/null

# 0.2 Verify recent Longhorn backup
mise exec -- kubectl get jobs -n storage | grep daily-backup-all-volumes | tail -1

# 0.3 Record current Talos versions
mise exec -- talosctl version --nodes 192.168.55.11,192.168.55.12,192.168.55.13 --short
```

**Expected**: `Firing alerts: 0`, daily backup `Complete` within last 24h, all nodes on v1.11.0.

### Step 1 — Edit `talconfig.yaml`

Bump versions and wire in the two missing patches:

```yaml
# kubernetes/bootstrap/talos/talconfig.yaml
talosVersion: v1.12.6          # was v1.11.6
kubernetesVersion: v1.35.6     # was v1.34.6 (use latest 1.35.x — check siderolabs/kubelet tags)

# ...

patches:
  - "@./patches/global/machine-files.yaml"
  - "@./patches/global/machine-intelgpu.yaml"     # NEW
  - "@./patches/global/machine-kubelet.yaml"
  - "@./patches/global/machine-network.yaml"
  - "@./patches/global/machine-network-rps.yaml"
  - "@./patches/global/machine-sysctls.yaml"
  - "@./patches/global/machine-time.yaml"
  - "@./patches/global/machine-udev.yaml"         # NEW
```

Also update the `talosImageURL` installer hash if you regenerate schematic via factory.talos.dev (keep current hash if intelgpu extras are already baked in).

### Step 2 — Enhance `machine-sysctls.yaml`

Patterns merged from:
- [tyriis/home-ops talconfig.yaml](https://github.com/tyriis/home-ops/blob/main/talos/utility/talconfig.yaml) — `tcp_fastopen`, `vm.nr_hugepages` (deferred)
- [marcolongol/homelab-cluster machine-sysctls.yaml](https://github.com/marcolongol/homelab-cluster/blob/main/talos/patches/global/machine-sysctls.yaml) — BBR, conntrack, fd limits, keepalives
- [OneUptime: Tune Network Performance](https://oneuptime.com/blog/post/2026-03-03-tune-network-performance-on-talos-linux/view) — conntrack sizing rationale
- [Talos discussion #12313](https://github.com/siderolabs/talos/discussions/12313) — conntrack table full prevention
- [Kubernetes sysctl docs](https://kubernetes.io/docs/tasks/administer-cluster/sysctl-cluster/) — allowed safe sysctls

Replace the file with:

```yaml
# kubernetes/bootstrap/talos/patches/global/machine-sysctls.yaml
machine:
  sysctls:
    # --- File watching (existing) ---
    fs.inotify.max_user_watches: "1048576"    # Watchdog
    fs.inotify.max_user_instances: "8192"     # Watchdog

    # --- File descriptors (new) — Elasticsearch, Nextcloud, Postgres ---
    # Source: marcolongol/homelab-cluster, common Elasticsearch requirements
    fs.file-max: "2097152"
    fs.nr_open: "1048576"

    # --- Network core (existing + new) ---
    net.core.rmem_max: "16777216"
    net.core.wmem_max: "16777216"
    net.core.rmem_default: "262144"
    net.core.wmem_default: "262144"
    net.core.netdev_max_backlog: "5000"
    net.core.netdev_budget: "600"
    net.core.netdev_budget_usecs: "8000"
    net.core.somaxconn: "65535"               # NEW — listen() backlog (marcolongol)
    net.core.default_qdisc: "fq"              # NEW — pairs with BBR (oneuptime)

    # --- TCP tuning (existing + new) ---
    net.ipv4.tcp_rmem: "4096 87380 16777216"
    net.ipv4.tcp_wmem: "4096 65536 16777216"
    net.ipv4.tcp_congestion_control: "bbr"    # NEW — Google BBR (oneuptime, marcolongol)
    net.ipv4.tcp_fastopen: "3"                # NEW — client + server TFO (tyriis)
    net.ipv4.ip_local_port_range: "1024 65535" # NEW (marcolongol)
    net.ipv4.tcp_max_syn_backlog: "8192"       # NEW (marcolongol)
    net.ipv4.tcp_fin_timeout: "30"             # NEW (marcolongol)
    net.ipv4.tcp_keepalive_time: "600"         # NEW (marcolongol)
    net.ipv4.tcp_keepalive_intvl: "60"         # NEW (marcolongol)
    net.ipv4.tcp_keepalive_probes: "3"         # NEW (marcolongol)

    # --- Conntrack (new) — prevents silent drops under load ---
    # Source: siderolabs/talos discussion #12313, oneuptime blog
    net.netfilter.nf_conntrack_max: "1048576"
    net.netfilter.nf_conntrack_buckets: "262144"
    net.netfilter.nf_conntrack_tcp_timeout_established: "86400"

    # --- Memory (existing + new) ---
    vm.dirty_ratio: "10"
    vm.dirty_background_ratio: "5"
    vm.max_map_count: "262144"                # NEW — required by Elasticsearch (elastic.co docs)
    vm.swappiness: "10"                        # NEW — no swap, but explicit (marcolongol)
    vm.vfs_cache_pressure: "50"                # NEW — balance VFS cache (marcolongol)

    # --- Process limits (new) ---
    kernel.pid_max: "4194304"                  # marcolongol
```

### Step 3 — Update `machine-kubelet.yaml`

Pattern reference:
- [tyriis/home-ops](https://github.com/tyriis/home-ops/blob/main/talos/utility/talconfig.yaml) — `serializeImagePulls: false`, `defaultRuntimeSeccompProfileEnabled`
- [Kubernetes kubelet config reference](https://kubernetes.io/docs/reference/config-api/kubelet-config.v1beta1/) — `systemReserved`, `kubeReserved`, `maxParallelImagePulls`
- [Kubernetes Reserve Compute Resources](https://kubernetes.io/docs/tasks/administer-cluster/reserve-compute-resources/) — rationale for system/kube reservations

```yaml
# kubernetes/bootstrap/talos/patches/global/machine-kubelet.yaml
machine:
  kubelet:
    nodeIP:
      validSubnets:
        - 192.168.55.0/24
    extraConfig:
      # Reserve resources so kubelet/containerd don't starve under burst load.
      # NUC14 has 18 CPUs / 62 GiB — 1 CPU + 2 GiB is ~5% overhead.
      # Ref: https://kubernetes.io/docs/tasks/administer-cluster/reserve-compute-resources/
      systemReserved:
        cpu: 500m
        memory: 1Gi
        ephemeral-storage: 2Gi
      kubeReserved:
        cpu: 500m
        memory: 1Gi
        ephemeral-storage: 2Gi
      # Parallel image pulls (speed up cold-start after upgrade). Ref: tyriis/home-ops
      serializeImagePulls: false
      maxParallelImagePulls: 5
```

### Step 4 — Fix RPS mask

```yaml
# kubernetes/bootstrap/talos/patches/global/machine-network-rps.yaml
machine:
  files:
    - path: /var/etc/udev/rules.d/50-rps.rules
      permissions: 0644
      op: create
      content: |
        # Enable RPS on all network interfaces (18 CPUs for NUC14 Meteor Lake)
        # 3ffff = 18 bits = all 18 CPUs; was ffff (16) which missed 2 cores
        SUBSYSTEM=="net", ACTION=="add", RUN+="/bin/sh -c 'for i in /sys/class/net/%k/queues/rx-*/rps_cpus; do echo 3ffff > $$i; done'"
        SUBSYSTEM=="net", ACTION=="add", RUN+="/bin/sh -c 'for i in /sys/class/net/%k/queues/rx-*/rps_flow_cnt; do echo 4096 > $$i; done'"
```

**Note**: Also remove the duplicate RPS udev rule from `machine-files.yaml` if present — `machine-files.yaml` historically contained the same rule and may conflict.

### Step 5 — Verify `machine-intelgpu.yaml` content

Pattern reference:
- [tyriis/home-ops talconfig.yaml](https://github.com/tyriis/home-ops/blob/main/talos/utility/talconfig.yaml) — exact same `apparmor=0`, `init_on_alloc=0`, `intel_iommu=on`, `iommu=pt`, `mitigations=off`, `security=none`, `talos.auditd.disabled=1` set
- [Intel GuC/HuC firmware guide](https://gist.github.com/Brainiarc7/aa43570f512906e882ad6cdd835efe57) — `i915.enable_guc=3` enables both GuC submission and HuC authentication
- [Talos performance tuning docs](https://docs.siderolabs.com/talos/v1.12/configure-your-talos-cluster/system-configuration/performance-tuning) — official Talos recommendations
- [Arch Wiki: Intel graphics](https://wiki.archlinux.org/title/Intel_graphics) — GuC/HuC caveats

The existing file at `kubernetes/bootstrap/talos/patches/global/machine-intelgpu.yaml` should contain:

```yaml
machine:
  install:
    extraKernelArgs:
      - i915.enable_guc=3                     # Meteor Lake GPU (GuC + HuC firmware loading)
      - apparmor=0                             # Perf: disable LSM AppArmor
      - init_on_alloc=0                        # Perf: disable memory init on alloc
      - init_on_free=0                         # Perf: disable memory init on free
      - intel_iommu=on                         # PCI passthrough prerequisite
      - iommu=pt                               # IOMMU passthrough mode (faster)
      - mitigations=off                        # Perf: disable Spectre/Meltdown mitigations
      - security=none                          # Perf: disable LSM
      - sysctl.kernel.kexec_load_disabled=1    # Security
      - talos.auditd.disabled=1                # Perf: no audit
      # NOT adding: cpufreq.default_governor=performance (keep powersave for idle power)
      # NOT adding: intel_idle.max_cstate=1 (only if a latency problem is measured)
```

No changes needed unless you want to tune — we're just wiring it into talconfig.

### Step 6 — Verify `machine-udev.yaml`

Existing content is correct:

```yaml
machine:
  udev:
    rules:
      # Intel GPU device node permissions for pods
      - SUBSYSTEM=="drm", KERNEL=="renderD*", GROUP="44", MODE="0660"
```

### Step 7 — Regenerate Talos cluster configs

```bash
# From repo root
mise exec -- bash -c 'cd kubernetes/bootstrap/talos && talhelper genconfig'
# Or if there's a task for it:
mise exec -- task talos:generate-config

# Verify generated configs have the new kernel args
grep -A15 "extraKernelArgs" kubernetes/bootstrap/talos/clusterconfig/kubernetes-k8s-nuc14-01.yaml | head -20
```

**Expected**: `extraKernelArgs` section contains `i915.enable_guc=3`, `intel_iommu=on`, `mitigations=off`, `init_on_alloc=0`.

**SOPS note**: `talhelper genconfig` produces SOPS-encrypted cluster configs. Ensure `SOPS_AGE_KEY_FILE` is exported (should be handled by `.mise.toml`).

### Step 8 — Commit and push

```bash
git add kubernetes/bootstrap/talos/
git commit -m "Talos v1.11.0 → v1.12.6 upgrade + performance tuning

- Bump Talos v1.11.6 → v1.12.6, Kubernetes v1.34.6 → v1.35.6
- Wire machine-intelgpu.yaml and machine-udev.yaml into talconfig
  (were on disk but not applied — Intel GPU GuC, mitigations=off,
  intel_iommu, init_on_alloc=0 now active)
- Add BBR, conntrack, fd limits, vm.max_map_count to sysctls
- Add kubelet systemReserved/kubeReserved (1 CPU + 2 GiB)
- Fix RPS mask ffff → 3ffff (was only using 16 of 18 CPUs)
- Keep CPU governor as powersave for idle power profile

Unblocks OTBR (CONFIG_IPV6_MROUTE=y in Talos v1.12.x kernel)."
git push
```

### Step 9 — Rolling node upgrade

**One node at a time. Wait for Longhorn replicas to rebuild between nodes.**

```bash
# 9.1 First node: k8s-nuc14-01
mise exec -- task talos:upgrade-node IP=192.168.55.11

# Wait until node Ready + all Longhorn replicas on that node show healthy:
mise exec -- kubectl get nodes
mise exec -- kubectl get replica -n storage -o json | python3 -c "
import sys,json
rs = json.load(sys.stdin)['items']
degraded = [r for r in rs if r['spec'].get('nodeID','?')=='k8s-nuc14-01' and r['status'].get('currentState')!='running']
print(f'nuc14-01 replicas degraded: {len(degraded)}')"

# 9.2 Second node
mise exec -- task talos:upgrade-node IP=192.168.55.12
# wait for Ready + replicas healthy (same check with k8s-nuc14-02)

# 9.3 Third node
mise exec -- task talos:upgrade-node IP=192.168.55.13
# wait for Ready + replicas healthy

# 9.4 Upgrade Kubernetes (after all nodes on new Talos)
mise exec -- task talos:upgrade-k8s
```

### Step 10 — Re-enable OTBR

```bash
# Edit kubernetes/apps/home-automation/kustomization.yaml
# Uncomment the ./otbr/ks.yaml line
```

Change:
```yaml
 - ./node-red/ks.yaml
 # otbr disabled: ...
 # - ./otbr/ks.yaml
 - ./scrypted-nvr/ks.yaml
```

To:
```yaml
 - ./node-red/ks.yaml
 - ./otbr/ks.yaml
 - ./scrypted-nvr/ks.yaml
```

```bash
git add kubernetes/apps/home-automation/kustomization.yaml
git commit -m "Re-enable OTBR after Talos v1.12.6 upgrade (CONFIG_IPV6_MROUTE=y)"
git push
```

---

## 5) Examples

### Example A: Full upgrade path (happy path)

```bash
cd /Users/mu/code/cberg-home-nextgen
# Edit files per sections 1-6 above
mise exec -- task talos:generate-config
git add kubernetes/bootstrap/talos/ && git commit -m "Talos upgrade + perf tuning" && git push
mise exec -- task talos:upgrade-node IP=192.168.55.11  # wait for Ready + healthy replicas
mise exec -- task talos:upgrade-node IP=192.168.55.12  # wait
mise exec -- task talos:upgrade-node IP=192.168.55.13  # wait
mise exec -- task talos:upgrade-k8s
# Re-enable OTBR in home-automation/kustomization.yaml
```

### Example B: Upgrade single node (recovery / one at a time)

```bash
# Override the installer image if needed
mise exec -- task talos:upgrade-node IP=192.168.55.11 IMAGE=factory.talos.dev/installer/<hash>:v1.12.6
```

---

## 6) Verification Tests

### Test 1: Node running Talos v1.12.6

```bash
mise exec -- talosctl version --nodes 192.168.55.11,192.168.55.12,192.168.55.13 --short
```

**Expected**: Three `Tag: v1.12.6` lines.

**If failed**: Check `task talos:upgrade-node` output for errors. Node may need reboot with `talosctl reboot --mode force -n <ip>`.

### Test 2: Kernel command-line contains new args

```bash
mise exec -- talosctl read /proc/cmdline -n 192.168.55.11
```

**Expected**: Contains `intel_iommu=on`, `iommu=pt`, `mitigations=off`, `i915.enable_guc=3`, `init_on_alloc=0`, `apparmor=0`.

**If failed**: `machine-intelgpu.yaml` not in `talconfig.yaml` patches list, or node not yet upgraded (kernel args only apply after install/upgrade, not runtime apply).

### Test 3: `CONFIG_IPV6_MROUTE` is set

```bash
mise exec -- talosctl read /proc/config.gz -n 192.168.55.11 | gunzip | grep IPV6_MROUTE
```

**Expected**:
```
CONFIG_IPV6_MROUTE=y
CONFIG_IPV6_MROUTE_MULTIPLE_TABLES=y
CONFIG_IPV6_PIMSM_V2=y
```

**If failed**: Node still on old Talos kernel (6.12). Re-run upgrade.

### Test 4: New sysctls active

```bash
for key in net.ipv4.tcp_congestion_control net.core.default_qdisc net.netfilter.nf_conntrack_max vm.max_map_count fs.file-max; do
  val=$(mise exec -- talosctl read /proc/sys/$(echo $key | tr . /) -n 192.168.55.11 2>/dev/null)
  echo "$key = $val"
done
```

**Expected**:
```
net.ipv4.tcp_congestion_control = bbr
net.core.default_qdisc = fq
net.netfilter.nf_conntrack_max = 1048576
vm.max_map_count = 262144
fs.file-max = 2097152
```

**If failed**: Sysctl rejected (typo or wrong format), or node hasn't re-applied config. Check `talosctl dmesg -n <ip> | grep sysctl`.

### Test 5: Kubelet reservations applied

```bash
mise exec -- kubectl describe node k8s-nuc14-01 | grep -A2 "Allocatable:"
```

**Expected**: Allocatable CPU ~17000m (18000m − 1000m reservation), Memory ~60 GiB (62 − 2 GiB).

**If failed**: Kubelet extraConfig not parsed. Check `talosctl service kubelet status -n <ip>`.

### Test 6: RPS mask applied

```bash
mise exec -- talosctl read /sys/class/net/enp86s0/queues/rx-0/rps_cpus -n 192.168.55.11
```

**Expected**: `3ffff` (not `ffff`).

**If failed**: Udev rule didn't run. Run manually: `echo 3ffff | tee /sys/class/net/*/queues/rx-*/rps_cpus` via toolbox pod.

### Test 7: OTBR running after re-enable

```bash
mise exec -- kubectl get pods -n home-automation -l app.kubernetes.io/name=otbr
mise exec -- kubectl logs -n home-automation -l app.kubernetes.io/name=otbr --tail=20 | grep -E "InitMulticast|backbone|otbr-agent"
```

**Expected**: Pod `Running 1/1`, no `InitMulticastRouterSock() Protocol not available` errors, `otbr-agent` active.

**If failed**: Confirm `CONFIG_IPV6_MROUTE=y` (Test 3). If kernel option missing, OTBR can't be re-enabled — Talos didn't actually upgrade.

### Test 8: Longhorn volumes healthy after rolling upgrade

```bash
mise exec -- kubectl get volume -n storage -o json | python3 -c "
import sys,json
vs = json.load(sys.stdin)['items']
degraded = [v['metadata']['name'] for v in vs if v['status'].get('robustness') != 'healthy']
print(f'Degraded volumes: {len(degraded)}')
for v in degraded[:10]: print(f'  - {v}')"
```

**Expected**: `Degraded volumes: 0`. Rebuild time: 10-15 min per node.

**If failed**: Wait longer (replicas are rebuilding). If stuck > 30 min, check Longhorn UI and replica CR status.

### Test 9: Zero Prometheus alerts

```bash
mise exec -- kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &
sleep 2
curl -s http://localhost:9090/api/v1/alerts | python3 -c "
import sys,json
a=[x for x in json.load(sys.stdin)['data']['alerts'] if x['state']=='firing' and x['labels']['alertname'] not in ('Watchdog','InfoInhibitor')]
print(f'Firing alerts: {len(a)}')
for x in a: print(f'  - {x[\"labels\"][\"alertname\"]}: {x[\"labels\"].get(\"pod\",\"-\")}')"
kill %1 2>/dev/null
```

**Expected**: `Firing alerts: 0`.

**If failed**: See section 7 Troubleshooting.

---

## 7) Troubleshooting

| Symptom | Likely Cause | First Fix |
|---------|--------------|-----------|
| `task talos:upgrade-node` fails with "no config" | `talhelper genconfig` not run after talconfig edit | Run `talhelper genconfig`, commit, re-run upgrade |
| Kernel cmdline missing new args after upgrade | `install.extraKernelArgs` only applies at install time; node kept old boot | Run `talosctl upgrade` with `--preserve=false` to force reinstall |
| Node stuck in `NotReady` after upgrade | Kubelet can't start (misconfigured `extraConfig`) | `talosctl service kubelet status -n <ip>`, check validation errors |
| Longhorn volumes degraded > 30 min | Replica rebuild queue saturated or engine image mismatch | Check `kubectl get engineimage -n storage`, ensure all healthy. Increase `concurrent-replica-rebuild-per-node-limit` if needed |
| OTBR still crashing with `InitMulticastRouterSock` | Node didn't actually upgrade (kernel still 6.12) | Verify with Test 3. Re-run upgrade-node with force reboot |
| sysctl rejected at boot | Unknown parameter in new kernel version | `talosctl dmesg -n <ip> \| grep sysctl`. Remove unknown keys |
| `intel_iommu=on` causes boot failure | Rare firmware/BIOS incompatibility | Remove `intel_iommu=on` and `iommu=pt` from intelgpu patch, regenerate config |
| Elasticsearch crashes with `max virtual memory` error | `vm.max_map_count` not applied | Confirm sysctl is active (Test 4). ES needs at least 262144 |
| BBR not active (`tcp_congestion_control` still cubic) | `CONFIG_TCP_CONG_BBR` not built in | Check `/proc/sys/net/ipv4/tcp_available_congestion_control`. Talos v1.12 kernel has BBR; v1.11 may be module-only |

```bash
# Quick debug commands
mise exec -- talosctl dmesg -n 192.168.55.11 | tail -50
mise exec -- talosctl service kubelet status -n 192.168.55.11
mise exec -- talosctl get machineconfig -n 192.168.55.11 -o yaml | grep -A20 extraKernelArgs
```

---

## 8) Diagnose Examples

### Diagnose Example 1: Upgrade didn't change kernel cmdline

```bash
# Check what the config says vs. what the kernel uses
diff <(mise exec -- talosctl get machineconfig -n 192.168.55.11 -o yaml | grep -A15 extraKernelArgs) \
     <(mise exec -- talosctl read /proc/cmdline -n 192.168.55.11 | tr ' ' '\n' | sort)
```

**Expected**: Cmdline contains every arg in `extraKernelArgs`.

**If unclear**: The node boots from its installed image; `install.extraKernelArgs` only affects new installs/upgrades. Force reinstall:
```bash
mise exec -- talosctl upgrade --nodes 192.168.55.11 --image factory.talos.dev/installer/<hash>:v1.12.6 --preserve=false
```

### Diagnose Example 2: Longhorn replicas stuck rebuilding

```bash
# Find replicas on the upgraded node
mise exec -- kubectl get replica -n storage -o custom-columns=NAME:.metadata.name,NODE:.spec.nodeID,STATE:.status.currentState | grep k8s-nuc14-01

# Check instance manager status
mise exec -- kubectl get instancemanager -n storage | grep nuc14-01
```

**Expected**: All replicas on node → `running`, instance managers → `running`.

**If unclear**: Check Longhorn manager logs:
```bash
mise exec -- kubectl logs -n storage -l app=longhorn-manager --since=30m | grep -iE "error|rebuild|fail"
```

### Diagnose Example 3: OTBR still failing after upgrade

```bash
# 1. Confirm kernel has mroute
mise exec -- talosctl read /proc/config.gz -n 192.168.55.13 | gunzip | grep IPV6_MROUTE
# Expected: CONFIG_IPV6_MROUTE=y

# 2. Check OTBR agent logs
mise exec -- kubectl logs -n home-automation -l app.kubernetes.io/name=otbr --tail=30 | grep -iE "init|mroute|backbone|error"
# Expected: No "InitMulticastRouterSock" or "Protocol not available"

# 3. Check pod events
mise exec -- kubectl describe pod -n home-automation -l app.kubernetes.io/name=otbr | tail -30
```

**Expected**: OTBR pod `Running 1/1`, mDNS service active, Thread backbone initialized.

**If unclear**: OTBR image may have other issues unrelated to mroute. Try without `BACKBONE_IF` env var to isolate.

---

## 9) Health Check

Run weekly or after any cluster change:

```bash
# Version consistency across nodes
mise exec -- talosctl version --nodes 192.168.55.11,192.168.55.12,192.168.55.13 --short | grep Tag | sort -u

# All kustomizations applied
mise exec -- flux get kustomizations -A | grep -cv "True"  # should print 1 (just the header)

# All Longhorn volumes healthy
mise exec -- kubectl get volume -n storage -o json | python3 -c "
import sys,json
n=sum(1 for v in json.load(sys.stdin)['items'] if v['status'].get('robustness')!='healthy')
print(f'Unhealthy: {n}')"

# No Prometheus alerts
mise exec -- bash -c 'kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &>/dev/null &
sleep 2
curl -s http://localhost:9090/api/v1/alerts | python3 -c "
import sys,json
a=[x for x in json.load(sys.stdin)[\"data\"][\"alerts\"] if x[\"state\"]==\"firing\" and x[\"labels\"][\"alertname\"] not in (\"Watchdog\",\"InfoInhibitor\")]
print(f\"Firing: {len(a)}\")"
kill %1 2>/dev/null'
```

**Expected**:
- 1 unique Tag line (all on v1.12.6)
- 1 line from flux kustomizations grep (just header)
- `Unhealthy: 0`
- `Firing: 0`

---

## 10) Security Check

After the upgrade, verify that performance-vs-security trade-offs are as intended:

```bash
# 1. Confirm mitigations are intentionally off
mise exec -- talosctl read /proc/cmdline -n 192.168.55.11 | grep mitigations
# Expected: mitigations=off (intentional for home-lab perf)

# 2. Confirm SOPS-encrypted configs haven't leaked
head -20 kubernetes/bootstrap/talos/clusterconfig/kubernetes-k8s-nuc14-01.yaml | grep -E "sops:|ENC\["
# Expected: Sops metadata present (file is encrypted)

# 3. Confirm no new privileged pods created
mise exec -- kubectl get pods -A -o json | python3 -c "
import sys,json
pods=[p for p in json.load(sys.stdin)['items'] for c in p['spec'].get('containers',[]) if c.get('securityContext',{}).get('privileged')]
print(f'Privileged pods: {len(pods)}')"
# Expected: same count as before upgrade (baseline 6)

# 4. Verify sops-age key still valid for Flux
mise exec -- kubectl get secret -n flux-system sops-age -o jsonpath='{.data}' | wc -c
# Expected: non-zero (secret exists)

# 5. Run security-check runbook
mise exec -- python3 runbooks/security-check.py
```

**Expected**:
- `mitigations=off` present (intentional)
- clusterconfig files show SOPS encryption headers
- Privileged pod count unchanged from baseline
- Security check runbook completes with no new criticals

---

## 11) Rollback Plan

Talos supports rolling back the installed image. **Longhorn replicas remain on the old version during rollback** so data is safe.

### 11.1 Single-node rollback (during upgrade)

```bash
# Check previous image
mise exec -- talosctl get machinestatus -n 192.168.55.11 -o yaml | grep image

# Rollback to previous
mise exec -- talosctl rollback --nodes 192.168.55.11
```

### 11.2 Full cluster rollback

```bash
# Revert the Talos upgrade commit
cd /Users/mu/code/cberg-home-nextgen
git log --oneline -10 kubernetes/bootstrap/talos/
git revert <upgrade-commit-sha>
mise exec -- task talos:generate-config
git add kubernetes/bootstrap/talos/
git commit -m "Rollback Talos upgrade"
git push

# Re-upgrade each node to old version
mise exec -- task talos:upgrade-node IP=192.168.55.11  # uses old talconfig
mise exec -- task talos:upgrade-node IP=192.168.55.12
mise exec -- task talos:upgrade-node IP=192.168.55.13
mise exec -- task talos:upgrade-k8s  # roll back K8s too
```

### 11.3 Disable OTBR again if mroute broken

If v1.12.6 somehow still doesn't fix OTBR, comment it back out:

```bash
# Edit kubernetes/apps/home-automation/kustomization.yaml
# - ./otbr/ks.yaml  →  # - ./otbr/ks.yaml
git add kubernetes/apps/home-automation/kustomization.yaml
git commit -m "Re-disable OTBR (mroute issue persists)"
git push
```

---

## 12) References

### Official Talos documentation
- [Talos v1.12.0 release notes](https://github.com/siderolabs/talos/releases/tag/v1.12.0) — What's new, kernel 6.18, K8s 1.35
- [Talos v1.12.6 release notes](https://github.com/siderolabs/talos/releases/tag/v1.12.6) — Latest patch
- [Talos performance tuning (v1.12)](https://docs.siderolabs.com/talos/v1.12/configure-your-talos-cluster/system-configuration/performance-tuning) — Official perf guide
- [Talos performance tuning (v1.11)](https://docs.siderolabs.com/talos/v1.11/configure-your-talos-cluster/system-configuration/performance-tuning) — Current version
- [Talos upgrade guide](https://www.talos.dev/v1.12/talos-guides/upgrading-talos/)
- [Talos discussion #12313: conntrack table full](https://github.com/siderolabs/talos/discussions/12313) — Why we tune conntrack
- [Talos issue #8332: kube-proxy IPVS + externalIP](https://github.com/siderolabs/talos/issues/8332) — Why kube-proxy is disabled
- [siderolabs/pkgs kernel config (main)](https://raw.githubusercontent.com/siderolabs/pkgs/main/kernel/build/config-amd64) — Kernel options (v1.12+)
- [siderolabs/pkgs kernel config (v1.11.0)](https://raw.githubusercontent.com/siderolabs/pkgs/v1.11.0/kernel/build/config-amd64) — Kernel options (v1.11)

### Community Talos homelab repos (pattern sources)
- [tyriis/home-ops](https://github.com/tyriis/home-ops/blob/main/talos/utility/talconfig.yaml) — Source for most kernel args (`mitigations=off`, `init_on_alloc=0`, `intel_iommu=on`, `iommu=pt`, `apparmor=0`, `security=none`, `talos.auditd.disabled=1`), `tcp_fastopen`, `serializeImagePulls: false`
- [marcolongol/homelab-cluster](https://github.com/marcolongol/homelab-cluster/blob/main/talos/patches/global/machine-sysctls.yaml) — Source for BBR, conntrack sizing, TCP keepalives, file descriptors, pid_max, `ip_local_port_range`, vm/swappiness/vfs_cache_pressure
- [onedr0p/cluster-template](https://github.com/onedr0p/cluster-template) — General structure and `cluster.sample.yaml` patterns

### Tuning guides (external)
- [OneUptime: Tune Kernel Parameters on Talos](https://oneuptime.com/blog/post/2026-03-03-tune-kernel-parameters-on-talos-linux/view)
- [OneUptime: Tune Network Performance on Talos](https://oneuptime.com/blog/post/2026-03-03-tune-network-performance-on-talos-linux/view)
- [OneUptime: Configure Extra Kernel Arguments](https://oneuptime.com/blog/post/2026-03-03-configure-extra-kernel-arguments-in-talos-linux/view)
- [OneUptime: Set Machine Sysctls](https://oneuptime.com/blog/post/2026-03-03-set-machine-sysctls-in-talos-linux/view)
- [OneUptime: Kernel Module Parameters](https://oneuptime.com/blog/post/2026-03-03-set-machine-kernel-module-parameters-in-talos-linux/view)
- [OneUptime: Talos on Intel NUC](https://oneuptime.com/blog/post/2026-03-03-set-up-talos-linux-on-intel-nuc/view)

### Kernel and GPU references
- [Intel GuC/HuC firmware guide](https://gist.github.com/Brainiarc7/aa43570f512906e882ad6cdd835efe57) — `i915.enable_guc=3` rationale
- [Intel GuC/HuC PDF](https://cdrdv2-public.intel.com/609249/609249-final-enabling-intel-guc-huc-advanced-gpu-features-v1-1-1.pdf) — Official Intel doc
- [Arch Wiki: Intel graphics](https://wiki.archlinux.org/title/Intel_graphics) — i915 driver tuning
- [drm/i915 kernel docs](https://docs.kernel.org/gpu/i915.html) — Upstream driver reference
- [Phoronix: GuC firmware for ADL-P](https://www.phoronix.com/news/GuC-Firmware-ADL-P-Linux-5.19) — Context for `enable_guc=3`

### Kubernetes references
- [Using sysctls in a Kubernetes Cluster](https://kubernetes.io/docs/tasks/administer-cluster/sysctl-cluster/) — Allowed safe sysctls
- [Kubelet config (v1beta1)](https://kubernetes.io/docs/reference/config-api/kubelet-config.v1beta1/) — `systemReserved`, `kubeReserved`, `maxParallelImagePulls`
- [Reserve Compute Resources](https://kubernetes.io/docs/tasks/administer-cluster/reserve-compute-resources/) — Rationale for node reservations

### Longhorn v2 (deferred, see section 12 Longhorn note)
- [Longhorn v2 data engine](https://longhorn.io/docs/1.11.1/v2-data-engine/) — Overview
- [Longhorn v2 prerequisites](https://longhorn.io/docs/1.11.1/v2-data-engine/prerequisites/) — Kernel modules, hugepages, CPU
- [Longhorn v2 features](https://longhorn.io/docs/1.11.1/v2-data-engine/features/) — Feature support matrix (still Tech Preview)

### Local repo files
- `runbooks/health-check.sh` — Post-upgrade verification
- `runbooks/security-check.py` — Security validation
- `runbooks/check-all-versions.py` — Talos version check (added in session 2026-04-11)
- `docs/sops/longhorn.md` — Longhorn storage SOP (replica concepts)
- `docs/sops/backup.md` — Backup verification procedure
- `kubernetes/bootstrap/talos/talconfig.yaml` — Source of truth
- `kubernetes/bootstrap/talos/patches/global/` — All performance patches

### Longhorn v2 note (deferred)

Longhorn v2 data engine is **not** part of this upgrade. Kernel support is already present in v1.11 (NVMe TCP, VFIO PCI, UIO), but v2 is still Technical Preview in Longhorn v1.11.1 and is missing:
- Online replica rebuilding
- Replica count adjustment
- RWX access mode

Re-evaluate when Longhorn v2 reaches GA. Prerequisites to add at that time:
- `hugepages=1024` kernel arg (2 GiB of 2 MiB pages per node)
- Preload kernel modules: `vfio_pci`, `uio_pci_generic`
- Enable `v2-data-engine: true` in Longhorn Helm values
- Reserve 1 CPU per node for `spdk_tgt` polling (already set via `data-engine-cpu-mask: 0x1`)

### CPU governor decision

`cpufreq.default_governor=performance` was considered and **rejected**. Reason: NUC14 `intel_pstate` with `powersave` governor + `balance_performance` EPP already ramps up quickly on demand, and the `performance` governor would add ~3-4 W/node at idle (~10 W/cluster, ~€30-100/year). Current cluster load is 5-9% CPU; no throughput problem exists.

If a latency-sensitive workload later demands it, prefer `intel_idle.max_cstate=1` as a targeted change (lower idle power cost, fixes wake-up latency).

---

## 13) Stage A → Stage B path (v1.11.0 → v1.13.0)

> **Status:** Executed 2026-04-30. Cluster is now on Talos `v1.13.0` + Kubernetes `v1.36.0`. The single-step path in sections 1–12 above remains the canonical reference for one-minor upgrades; this section documents the actual two-stage traversal that crosses **two** minor versions and the lessons learned.

### 13.1 Strategy & rationale

Talos enforces single-minor traversal — there is no supported direct path from `v1.11.x → v1.13.x`. The same constraint applies to Kubernetes (`v1.34 → v1.36` must go through `v1.35`). The cluster therefore upgraded in two stages, back-to-back inside one maintenance window:

| Stage | Talos | Kubernetes | Notes |
|-------|-------|------------|-------|
| A | `v1.11.0` → `v1.12.7` | `v1.34.x` → `v1.35.4` | Performance sweep from sections 2–6 was applied here. |
| B | `v1.12.7` → `v1.13.0` | `v1.35.4` → `v1.36.0` | Pure version bump. No new patches. |

**Mandatory settle gate between A and B**: ≥10 minutes with all Flux kustomizations `Ready`, all pods running, all Longhorn volumes `healthy`. If Stage B has to be deferred (suspect alerts, replica rebuild lag, or operator on-call constraints), `v1.12.7` is a safe long-term resting point — leave the cluster there and run Stage B in a follow-up window.

**Do not skip the gate.** Back-to-back `apply-config` cycles across all three nodes within a few minutes was observed to cause etcd churn → brief cluster `NotReady` (lesson #12 below).

### 13.2 Operational instructions (delta vs. sections 4–9)

The single-step procedure already covers regenerating configs, the rolling node upgrade, and `upgrade-k8s`. For the two-stage path, run that procedure **twice** with the following deltas:

#### Stage A — execute sections 1–9 as written, with three additions

1. The performance patches from sections 2–6 (sysctls, kubelet reservations, RPS mask, `machine-intelgpu.yaml`, `machine-udev.yaml`) are wired in during Stage A. Stage B does not touch them.
2. `machine-intelgpu.yaml` also wires the Longhorn v2 OS prerequisites (`hugepages=1024` kernel arg, plus `vfio_pci` and `uio_pci_generic` kernel modules). These are inert until Longhorn v2 is enabled but must be in the schematic from Stage A onward — re-doing the schematic mid-cycle is error-prone.
3. After Stage A passes Test 1–9 (section 6) and the settle gate has elapsed, proceed to Stage B in the same window.

#### Stage B — minimal config change, same rolling pattern

```yaml
# kubernetes/bootstrap/talos/talconfig.yaml
talosVersion: v1.13.0          # was v1.12.7
kubernetesVersion: v1.36.0     # was v1.35.4
```

Regenerate, commit, push, then run the same rolling upgrade (one node at a time, wait for Ready + Longhorn healthy between each) followed by `task talos:upgrade-k8s`. Re-run section 6 verification tests at the end.

#### Bumping the `talosctl` client

`talosctl` is roughly `n±1` compatible with the cluster. After Stage B the repo-pinned `talosctl 1.12.4` will succeed for `apply-config` against a `v1.13` cluster but **fails** on `upgrade-k8s` (lesson #6 below). Before Stage B's `upgrade-k8s` step, merge the Renovate PR that bumps `talosctl` to a `v1.13.x` client and run `mise install`. Re-run `mise exec -- talosctl version --short` to confirm the client is now `v1.13.x`.

### 13.3 Pitfalls and lessons learned (Stage A + Stage B)

The numbered items below are observed regressions or footguns from the actual run. They extend section 7 (Troubleshooting) — items there still apply, these are additional.

#### 1. `talosctl reboot --mode powercycle` stuck on node 03

`talosctl reboot --mode powercycle --nodes 192.168.55.13` returned successfully but `talosctl get machinestatus` reported `stage: rebooting` indefinitely; cri/etcd/kubelet/trustd never restarted. Observed twice during this upgrade, both times on `k8s-nuc14-03` only.

**Recovery:** re-issue `talosctl reboot --mode default --nodes 192.168.55.13 --wait`. The graceful default reboot completes and the node returns to `Ready`.

Full reproduction notes, dmesg, and analysis are in `docs/troubleshooting/talos-powercycle-stuck.md` — do not duplicate here.

#### 2. KSPP filters `install.extraKernelArgs` in v1.12+

In Talos `v1.12+`, kernel args set in `machine.install.extraKernelArgs` are silently dropped by the KSPP (Kernel Self-Protection Project) filter for any arg KSPP considers redundant or conflicting. Examples seen: `i915.enable_guc=3`, `intel_iommu=on`. Verify with:

```bash
mise exec -- talosctl read /proc/cmdline -n 192.168.55.11
```

If args are missing, **move them into the schematic itself** at https://factory.talos.dev (extension config / kernel args field in the schematic) rather than the install patch. The schematic-injected cmdline survives KSPP filtering.

#### 3. `grubUseUKICmdline` default flips on v1.12+

When kernel args are set via the schematic, the v1.12+ default for `install.grubUseUKICmdline` causes grub to override the schematic-injected cmdline. Fix:

```yaml
machine:
  install:
    grubUseUKICmdline: false
```

Set this explicitly any time you rely on schematic-side kernel args.

#### 4. JSON6902 patches in multi-doc machineconfig fail in v1.12+

The previously-working `admission-controller-patch.yaml` (a JSON6902 `op: add` injecting Pod Security Admission config into the kube-apiserver static pod manifest) breaks in `v1.12+`. The patch silently fails to apply, leaving PSA defaults in place.

**Resolution applied this cluster:** removed the JSON6902 patch entirely and switched to per-namespace PSA labels via kustomize patches. See:
- `kubernetes/flux/components/common/namespace.yaml` — base namespace template
- `patches:` blocks in each `kubernetes/apps/<ns>/kustomization.yaml` — per-namespace PSA enforcement

#### 5. `talhelper` Go-template ate `$patch` and `$i`

`talhelper` runs the patch YAML through Go templating before handing it to Talos. Tokens like `$patch` (kustomize directive) and `$i` (shell variable in udev RUN) get interpreted as missing template vars and emit empty strings, breaking the patch. Quote them:

```yaml
# inside the udev RPS rule patch
RUN+="/bin/sh -c 'for i in /sys/...; do echo 3ffff > '$i'; done'"
# becomes (escaped for talhelper)
RUN+="/bin/sh -c 'for i in /sys/...; do echo 3ffff > '$$i'; done'"
```

Use `'$patch'` and `'$$i'` (or equivalent escaping) wherever a literal dollar-prefixed token appears in patch YAML.

#### 6. talosctl client compatibility window

`talosctl 1.12.4` against a `v1.13` cluster: `apply-config` works, `upgrade-k8s` fails. Cluster-side gRPC API contract changed.

**Rule of thumb:** keep the client within `n±1` of the cluster. Bump the Renovate `talosctl` PR before running `upgrade-k8s` against a freshly-bumped cluster.

#### 7. Drain rate-limiter errors during node 01 (Stage B)

During Stage B's first node (`k8s-nuc14-01`), the drain phase hit a rate-limiter error from the eviction API. Workaround applied:

```bash
mise exec -- task talos:upgrade-node IP=192.168.55.11 EXTRA_FLAGS="--drain=false"
```

Pods that would have been evicted by drain are subsequently evicted by `descheduler` and standard kubelet eviction once the node returns Ready. Longhorn replicas re-attach normally. Reserve `--drain=false` for the case where drain is itself the failure point — do not use it as a default.

#### 8. PV cascade-deleted despite `Retain` on backup-restore

When restoring a Longhorn volume from backup using the operator's `fromBackup` flow, an intermediate failure can cause the operator to delete the failed `Volume` CR **and** the bound `PersistentVolume` together — even when `reclaimPolicy: Retain` is set on the PV. This nullifies the documented expectation that `Retain` protects the PV.

**Resolution applied this cluster:** pre-create the `PersistentVolume` and `PersistentVolumeClaim` manifests pointing to the desired restored volume name, then create the Longhorn `Volume` CR from backup with that exact name. The PVC binds to the pre-existing PV instead of the operator generating a new one. This isolates the restore from the operator's PV lifecycle.

#### 9. Intel device-plugin operator `--devices` argument format

`--devices=gpu,npu` (single flag, comma-separated) crashes the `intel-device-plugin-operator` immediately on startup. Use one flag per device:

```yaml
controllerExtraArgs:
  - --devices=gpu
  - --devices=npu
```

#### 10. NPU plugin DaemonSet unscheduled — missing NFD label

`node-feature-discovery` does not auto-emit `intel.feature.node.kubernetes.io/npu=true` for Meteor Lake NPUs out of the box, which leaves the NPU plugin DaemonSet unscheduled. Add an explicit `NodeFeatureRule` matching PCI class `0x1200` + vendor `0x8086`:

- `kubernetes/apps/kube-system/node-feature-discovery/rules/intel-npu-device.yaml`

After NFD reconciles, `kubectl get nodes -L intel.feature.node.kubernetes.io/npu` shows the label and the plugin DaemonSet schedules normally.

#### 11. OTBR helmrelease hardcoded `replicas: 0`

Discovered during the post-Stage-A re-enable of OTBR: the helmrelease values had `replicas: 0` hardcoded from a previous incident. Setting the field back to `1` is required — uncommenting the kustomization entry is not sufficient.

#### 12. `apply-config` back-to-back caused etcd churn

Issuing `talosctl apply-config` against all three nodes within a few seconds (no per-node health gate) caused etcd leader election storms and a brief cluster `NotReady`. Always serial across nodes with a health gate (node `Ready` + etcd member healthy) between each `apply-config`.

```bash
mise exec -- kubectl get nodes
mise exec -- talosctl etcd members --nodes 192.168.55.11
# wait for full membership before touching the next node
```

#### 13. Hugepages cmdline lost after apply-config churn (node 02)

After the etcd-churn incident in #12, `k8s-nuc14-02` came back without `hugepages=1024` on `/proc/cmdline`. Re-upgrading the node with the same schematic restored it. Always verify per-node post-window:

```bash
for ip in 192.168.55.11 192.168.55.12 192.168.55.13; do
  echo "=== $ip ==="
  mise exec -- talosctl read /proc/cmdline -n $ip | tr ' ' '\n' | grep -E 'hugepages|i915|intel_iommu|mitigations'
  mise exec -- talosctl read /proc/meminfo -n $ip | grep HugePages_Total
done
```

**Expected per node:** `hugepages=1024` on cmdline, `HugePages_Total: 1024` in meminfo. Anything else means the node booted from an older install — re-run `task talos:upgrade-node` for that IP with the current schematic.

### 13.4 Verification (post Stage B)

Re-run section 6 tests with the updated expected values:

| Test | Expected after Stage B |
|------|-----------------------|
| Test 1 — Talos version | All three nodes report `Tag: v1.13.0` |
| Test 2 — `/proc/cmdline` | Contains all schematic-side args (#2 above) including `hugepages=1024` |
| Test 3 — `CONFIG_IPV6_MROUTE` | Still `=y` (kernel 6.18+) |
| Test 4 — sysctls | Unchanged from Stage A |
| Test 5 — kubelet reservations | Unchanged from Stage A |
| Test 6 — RPS mask | `3ffff` |
| Test 8 — Longhorn | `Degraded volumes: 0` |
| Test 9 — alerts | `Firing alerts: 0` |

Add the hugepages-per-node check from #13 above, plus:

```bash
mise exec -- kubectl version --short
# Server Version expected: v1.36.0
```

### 13.5 Rollback in two-stage mode

The single-step rollback in section 11 still applies, but with one nuance: rolling back **across two minor versions** (e.g. `v1.13.0 → v1.11.x`) is not supported in one operation. To unwind from a failed Stage B:

1. **Stop at v1.12.7.** Revert the Stage B commit only. `talosctl rollback --nodes <ip>` per node returns each to the v1.12.7 image (Talos keeps the previous installed image).
2. **Only continue rolling back to v1.11.x if Stage A also needs to be reverted.** This is a fresh full-window operation, not a hot rollback — replica rebuild on every node, K8s downgrade, full verification.

In practice, if Stage B fails: stop at `v1.12.7`, file the issue, plan Stage B retry for a later window. Do **not** chain a v1.13→v1.11 rollback inside the same window.

---

## Version History

- `2026.04.30`: Documented the actual Stage A → Stage B path (`v1.11.0 → v1.12.7 → v1.13.0`, K8s `v1.34 → v1.35.4 → v1.36.0`) executed in this cluster. Added 13 lessons learned: powercycle-stuck on node 03 (cross-link to `docs/troubleshooting/talos-powercycle-stuck.md`), KSPP filtering of `install.extraKernelArgs` in v1.12+, `grubUseUKICmdline` default flip, JSON6902 PSA patch breaking, `talhelper` `$patch`/`$i` escaping, `talosctl` client `n±1` compatibility window, drain rate-limiter workaround, Longhorn `Retain` PV cascade-delete on backup-restore, intel-device-plugin operator `--devices` flag format, NPU NFD rule requirement, OTBR `replicas: 0` hardcode, etcd churn from concurrent `apply-config`, hugepages cmdline loss recovery. Section 2–6 perf sweep reframed as "applied during Stage A 2026-04-30". Longhorn v2 OS prereqs (hugepages=1024, `vfio_pci`, `uio_pci_generic`) recorded as wired in during Stage A via `machine-intelgpu.yaml`.
- `2026.04.12`: Initial SOP — Talos v1.11.0 → v1.12.6 upgrade path combined with performance tuning sweep. Unblocks OTBR via `CONFIG_IPV6_MROUTE=y`. Keeps `powersave` governor.
