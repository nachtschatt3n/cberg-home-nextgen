---
plan_id: talos-sysfs-power-caps
component: talos
pr: null                              # no Renovate PR: an operator-requested node-config change (2026-10-04)
kind: infra
current: "BIOS/driver defaults on all 3 nodes: RAPL PL1=PL2=64 W, EPP balance_performance, iGPU gt0 max 2200 MHz; no SysfsConfig document"
target: "Talos SysfsConfig: RAPL PL1 35 W / PL2 55 W, EPP balance_power on cpu0..cpu17, iGPU render GT (gt0) max 1500 MHz"
update_type: refactor
risk: medium                          # Not high: no reboot (MEASURED dry-run, section 1), no apiserver/etcd restart,
                                      # each key is a live sysfs write that the plan's own rollback undoes in
                                      # seconds. Not low: it is a machine-config apply on all three
                                      # control-plane nodes, and it deliberately lowers sustained CPU/iGPU
                                      # throughput for every workload (capability_change below).
est_duration_min: 125                 # EVERYTHING in-window (review 2026-10-04: a pre-window phase has no owner):
                                      # Phase A baseline 35 (CI run ~20, 3 benches + calib ~12, stats 3);
                                      # premises+pre-checks 8, render+gates+rollback pre-render 12, commit 3,
                                      # per node (apply 1, gates 3, bench 3, settle 3) 10 x 3 = 30, final 5;
                                      # Phase C after-CI run + stats 22; slack 10. Fits only sun-attended (180).
needs_reboot: false                   # MEASURED 2026-10-04: `talosctl apply-config --dry-run --mode=no-reboot` with a
                                      # migrated+SysfsConfig render on k8s-nuc14-01 -> "Applied configuration without a
                                      # reboot". Talos source v1.14.1: KernelParamConfigController watches the ACTIVE
                                      # MachineConfig and KernelParamSpecController writes /sys live (section 1).
exclusive: false
touches:
  namespaces: [default, monitoring, ci-runner]     # default: transient capbench pods only (section 4.B);
                                                   # ci-runner: the Phase A/C measurement CI runs;
                                                   # monitoring: one PrometheusRule threshold (section 3.9)
  resources:
    - talos-machineconfig/k8s-nuc14-01               # apply-config --mode=no-reboot
    - talos-machineconfig/k8s-nuc14-02
    - talos-machineconfig/k8s-nuc14-03
    - "sysfs: /sys/class/powercap/intel-rapl:0/constraint_{0,1}_power_limit_uw (all nodes)"
    - "sysfs: /sys/devices/system/cpu/cpu{0..17}/cpufreq/energy_performance_preference (all nodes)"
    - "sysfs: /sys/class/drm/card{0,0,1}/gt/gt0/rps_max_freq_mhz (nodes 01,02,03)"
    - file/kubernetes/bootstrap/talos/talconfig.yaml
    - file/kubernetes/bootstrap/talos/patches/global/machine-sysfs-power.yaml     # NEW
    - file/kubernetes/bootstrap/talos/patches/node/k8s-nuc14-0{1,2,3}-sysfs-igpu.yaml   # NEW
    - prometheusrule/node-thermal-alerts (monitoring)  # NodeCPUPackagePowerAtCap 58 -> 31 W, section 3.9
    - file/runbooks/tests/test-node-thermal-alerts.py  # fixtures follow the threshold, section 3.9
    - "pod/capbench-* (default, transient, deleted by the script)"
    - "file/scripts/ninth-banner-admit.py + docs/sops/ci-runner.md (SOAK step 3.10 only, conditional)"
  shared: [talos-machineconfig, node-power-thermal, igpu-i915, monitoring, ci-runner-thermal-gate]
                                      # node-power-thermal: every pod on every node runs under the new cap.
                                      # igpu-i915: render GT capped at 1500 MHz (media GT gt1 untouched) -
                                      # frigate/immich-ml OpenVINO, jellyfin/plex tone-mapping, CI Chromium.
                                      # monitoring: section 4 reads Prometheus (its instrument).
depends_on:
  - talconfig-multidoc-migration      # MUST RUN FIRST. SysfsConfig is a v1.14 document; until the migration lands
                                      # `task talos:generate-config` fails on main and NO machine-config change can
                                      # be rendered (talos-upgrade.md §14.2). It is `exclusive: true`, so it cannot
                                      # share this plan's slot: earliest is the NEXT attended window after it executes.
conflicts_with:
  - talos-linux-1.14.2                # rolling reboot of all 3 nodes; never the same night. If it runs FIRST, the
                                      # card-index premise (section 2.4) must be re-measured; if it runs AFTER, its
                                      # reboots are this plan's first real "re-applied at boot" test (section 6).
  - talconfig-multidoc-migration      # reciprocity for depends_on (exclusive anyway)
  - multus-macvlan-foundation         # reference/unwindowed; also talosctl apply-config on the same nodes
  # No OPEN kube-prometheus-stack plan exists (91.4.1 executed 2026-09-26); section 4 reads Prometheus, so any
  # future same-night kube-prometheus-stack plan must be added here and must name this plan back.
security_ref: null
capability_change: true               # TRUE, deliberately: lowers sustained CPU package power (64 -> 35 W PL1),
                                      # biases P-state selection toward efficiency on every CPU and caps the iGPU
                                      # render GT at 68 % of RP0 -> slower CI shards, transcodes and inference.
                                      # User-visible behaviour change, so never unattended.
rollback_class: backup-restore        # The node rollback is a re-apply of a PRE-RENDERED rollback config carrying
                                      # the explicit 2026-10-04 values (section 5), proven acceptable by a dry-run
                                      # BEFORE the first apply. Flux does not reconcile kubernetes/bootstrap/talos/,
                                      # so a git revert alone changes nothing on the nodes.
restore_proof: "section 3.3: the PRE-RENDERED rollback config ($W/rb) is dry-run against every node BEFORE the first forward apply and must print GATE_PASS keys=21/21 from sysfs-diffgate.py (Talos accepts it, no reboot, it changes exactly the 21 keys to the 2026-10-04 values); section 5 then re-reads all 21 keys (sysfs-readback.py <ip> orig --status -> GATE_PASS)."
backup_gate: "per node, BEFORE its apply: (1) $W/rb/kubernetes-k8s-nuc14-0N.yaml rendered from the same tree with sysfs-patches.py orig, (2) sysfs-diffgate.py on its --dry-run --mode=no-reboot output prints GATE_PASS keys=21/21 (adds only the 21 SysfsConfig keys with the ORIGINAL values), (3) sysfs-readback.py <ip> orig prints GATE_PASS (the values the rollback restores are the values the node has right now)"
finding_refs: []                      # Queried 2026-10-04 with the DB reachable: `finding list --grep` thermal,
                                      # throttl, temperature, RAPL, power, package, sysfs, nuc14, hot, ci-runner
                                      # (--all) -> no finding owns node thermals/power. Nothing to claim.
review: null
status: draft
window: null                          # suggestion only (the window agent assigns): 125 min needs a sun-attended
                                      # slot after talconfig-multidoc-migration executed. Reviewer 2026-10-04:
                                      # sun-attended:2026-11-01 (45/180 booked); 10-11 exclusive, 10-18/10-25 too full.
premises:
  - id: nodes-on-talos-1.14
    why: "SysfsConfig is a Talos v1.14 document and every path below was measured on v1.14.1 (kernel 6.18.51). A node on another minor invalidates the render and the no-reboot verdict."
    run: kubectl get nodes -o jsonpath='{.items[*].status.nodeInfo.osImage}'
    expect_matches: '^Talos \(v1\.14\.[0-9]+\) Talos \(v1\.14\.[0-9]+\) Talos \(v1\.14\.[0-9]+\)$'
  - id: multidoc-migration-applied-on-all-nodes
    why: "depends_on talconfig-multidoc-migration. Its apply puts a KubeAPIServerConfig document into every node's live config: prints 3 after it ran, 0 today (measured 2026-10-04, rc=1). This premise is EXPECTED TO FAIL until the migration executes; that failure is the gate."
    run: "talosctl --nodes=192.168.55.11,192.168.55.12,192.168.55.13 get machineconfig v1alpha1 -o yaml | grep -c 'kind: KubeAPIServerConfig'"
    expect_exact: "3"
  - id: no-sysfs-kernelparams-yet
    why: "Today no node carries any sys.* KernelParamStatus (no SysfsConfig, no machine.sysfs). One appearing means someone else already writes /sys through Talos: re-plan instead of merging blind."
    run: talosctl --nodes=192.168.55.11,192.168.55.12,192.168.55.13 get kernelparamstatuses -o yaml
    expect_matches: '^(?![\s\S]*\bid: sys\.)[\s\S]*id: proc\.sys\.'
  - id: rapl-pl1-not-bios-locked-01
    why: "intel_rapl_common reports `enabled` 0 when the PL1 lock bit (shared by PL1/PL2 in MSR_PKG_POWER_LIMIT) is set (get_domain_enable, drivers/powercap/intel_rapl_common.c v6.18), and a write then fails EACCES. 1 = writable. Read-only lock test; no write in planning."
    run: talosctl --nodes=192.168.55.11 read /sys/class/powercap/intel-rapl:0/enabled
    expect_exact: "1"
  - id: rapl-pl1-not-bios-locked-02
    why: same as -01, node 02
    run: talosctl --nodes=192.168.55.12 read /sys/class/powercap/intel-rapl:0/enabled
    expect_exact: "1"
  - id: rapl-pl1-not-bios-locked-03
    why: same as -01, node 03
    run: talosctl --nodes=192.168.55.13 read /sys/class/powercap/intel-rapl:0/enabled
    expect_exact: "1"
  - id: no-intel-rapl-mmio-zone
    why: "Only intel-rapl (MSR) zones exist; no intel-rapl-mmio (MCHBAR) zone is exposed on any node (measured 2026-10-04). If one appears (kernel/driver change), its limit would also bind (lower wins) and must be read and planned too."
    run: talosctl --nodes=192.168.55.11,192.168.55.12,192.168.55.13 list /sys/class/powercap
    expect_matches: '^(?![\s\S]*mmio)[\s\S]*intel-rapl:0'
  - id: igpu-card-index-node03-card1
    why: "nuc14-03 boots with simpledrm on card0, so i915 is card1 there; 01/02 have i915 on card0. The per-node patches hard-code this. A different index means edit the per-node patch before rendering (section 2.4)."
    run: talosctl --nodes=192.168.55.13 read /sys/class/drm/card1/gt/gt0/rps_RP0_freq_mhz
    expect_exact: "2200"
  - id: igpu-card-index-node01-card0
    why: same as above, node 01 on card0
    run: talosctl --nodes=192.168.55.11 read /sys/class/drm/card0/gt/gt0/rps_RP0_freq_mhz
    expect_exact: "2200"
  - id: igpu-card-index-node02-card0
    why: same as above, node 02 on card0
    run: talosctl --nodes=192.168.55.12 read /sys/class/drm/card0/gt/gt0/rps_RP0_freq_mhz
    expect_exact: "2200"
  - id: media-gt-rp0-1300
    why: "The reason the plan writes gt/gt0/rps_max_freq_mhz and NOT the card-level gt_max_freq_mhz: the card-level store loops over every GT (sysfs_gt_attribute_w_func) and gt1 (media) has RP0 1300, so 1500 returns EINVAL there (intel_guc_slpc_set_max_freq). If gt1 RP0 ever reads >= 1500 the reasoning changes, not the plan's safety."
    run: talosctl --nodes=192.168.55.11 read /sys/class/drm/card0/gt/gt1/rps_RP0_freq_mhz
    expect_exact: "1300"
  - id: epp-balance-power-available
    why: "intel_pstate active mode advertises balance_power; a driver change (passive mode, acpi-cpufreq) would drop the EPP files and every EPP key would fail with ENOENT."
    run: talosctl --nodes=192.168.55.11 read /sys/devices/system/cpu/cpu17/cpufreq/energy_performance_available_preferences
    expect_contains: balance_power
  - id: eighteen-logical-cpus
    why: "The SysfsConfig names cpu0..cpu17. 18 per node x 3 = 54 cpuN directories. More CPUs would leave some on balance_performance; fewer would make keys fail with ENOENT."
    run: talosctl --nodes=192.168.55.11,192.168.55.12,192.168.55.13 list /sys/devices/system/cpu | grep -cE ' cpu[0-9]+$'
    expect_exact: "54"
  - id: rapl-energy-metric-scraped
    why: "Section 4.B reads node_rapl_package_joules_total (enabled by 957789c1 on 2026-10-04). Exactly 3 series = one per node; 0 means the exporter went blind again (capbench.py's talosctl energy_uj reading is the Prometheus-independent fallback)."
    run: kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=count(node_rapl_package_joules_total)'
    expect_matches: '"value":\[[0-9.]+,"3"\]'
  - id: power-at-cap-alert-still-58w
    why: "Section 3.9 rewrites the NodeCPUPackagePowerAtCap threshold 58 -> 31 W with an anchored sed; a different live value means the sed matches nothing (dry-tested)."
    run: grep -c 'joules_total{job="node-exporter"}.5m.) . 58$' kubernetes/apps/monitoring/kube-prometheus-stack/app/node-thermal-alerts.yaml
    expect_exact: "1"
  - id: ci-gate-open-below-85
    why: "Section 3.10 (soak) raises GATE_OPEN_BELOW_C 85 -> 88 with an anchored sed; the gate is edited often (3 commits on 2026-10-04)."
    run: grep -c '^OPEN_BELOW_C = float(os.environ.get("GATE_OPEN_BELOW_C", "85"))$' scripts/ninth-banner-admit.py
    expect_exact: "1"
sops_refs:
  - docs/sops/talos-upgrade.md
  - docs/sops/application-update.md
  - docs/sops/ci-runner.md
  - docs/sops/monitoring.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-10-04"
---

# Talos SysfsConfig power/thermal caps (all three NUC14 nodes)

## 1. Summary & why held

**What changes.** A Talos v1.14 `SysfsConfig` document, rendered by talhelper from one new global
patch and three new per-node patches, writes 21 sysfs keys on each node, live and without a reboot:

| key (Talos prefixes `/sys/`) | today (all 3 nodes, measured 2026-10-04) | target |
|---|---|---|
| `class/powercap/intel-rapl:0/constraint_0_power_limit_uw` (PL1, long_term, tau 27 983 872 us) | 64000000 | **35000000** |
| `class/powercap/intel-rapl:0/constraint_1_power_limit_uw` (PL2, short_term, tau 2 440 us) | 64000000 | **55000000** |
| `devices/system/cpu/cpu{0..17}/cpufreq/energy_performance_preference` (18 keys) | balance_performance | **balance_power** |
| `class/drm/<card>/gt/gt0/rps_max_freq_mhz` (render GT; card0 on 01/02, **card1 on 03**) | 2200 (= RP0) | **1500** |

Untouched on purpose (and asserted untouched in section 4): PL1/PL2 time windows, PL4 `constraint_2` (120 W),
the media GT `gt1` (max 1300), governor `powersave`, `no_turbo 0`, the `psys` zone (disabled, `enabled=0`).
Operator decision 2026-10-04 (chat): PL1 35 W / PL2 55 W directly, no 45/64 step ("a stable system is key for 24/7").

**Why.** All three nodes are NUC14RVK (Core Ultra 5 125H, 18 threads, BIOS RVMTL357.0041 on 01/02, .0038 on 03)
running the ASUS default PL1 = PL2 = 64 W. Measured: 7-day package peaks 95 / 102 / 103 °C, nuc14-02 ~29 000
package-throttle events and ~420 000 core-throttle events in 24 h, a 102 °C thermal reboot on 2026-08-08, and the
CI thermal gate (`scripts/ninth-banner-admit.py`) currently capping CI to ~1 pod per node because nodes run hot
from production load alone. `constraint_0_max_power_uw` reads 28 000 000: the CPU's own TDP is 28 W, so 35 W is
still above Intel's base power, and 55 W PL2 keeps short bursts.

**Why it is a plan, not an auto-update.** It is a machine-config apply to all three control-plane nodes and it
deliberately lowers sustained throughput for every workload (`capability_change: true`). Nothing upstream is
"broken" here; the risk is our own change.

**Primary-source evidence (each claim the steps rely on).**

1. *Applied live, no reboot.* Talos v1.14.1 `internal/app/machined/pkg/controllers/runtime/kernel_param_config.go`:
   `KernelParamConfigController` takes the ACTIVE MachineConfig as input and turns `cfg.Config().SysfsConfig()`
   into `KernelParamSpec`s with prefix `sys.`; `kernel_param_spec.go` writes each with `os.WriteFile`. Measured:
   a migrated+SysfsConfig render dry-run against k8s-nuc14-01 answered *"Applied configuration without a reboot
   (skipped in dry-run)"* and its diff shows the `SysfsConfig` document as the only sysfs change.
2. *Key format.* `pkg/machinery/kernel/kernel.go` `Param.Path()`: after stripping `sys.`, if the FIRST separator is
   `.` it swaps every `.` and `/`; if it is `/` it keeps the key as-is. Dotted keys would turn `intel-rapl:0` intact
   but any key containing a `.` in a path component would break, so every key is slash-separated.
3. *Removing the document restores the old value without a reboot.* `KernelParamSpecController.updateKernelParam`
   reads and remembers the pre-write value (`ctrl.defaults[key]`) before its first write; `resetKernelParam` writes
   that default back when a key leaves the config. So "values persist until reboot" is **false** for Talos: removal
   reverts live. The rollback in section 5 nevertheless writes the old values EXPLICITLY (operator request), so it
   does not depend on in-memory state (which a machined restart, i.e. a reboot, would lose anyway).
4. *Failure mode of a bad key.* A write error (ENOENT for a wrong card index, EACCES for a BIOS-locked RAPL, EINVAL
   for an out-of-range frequency) is collected and the controller continues with the remaining keys, then returns the
   error and is retried with backoff (`kernel_param_spec.go`, `continue` + `return errs`). So one bad key does not
   block the other 20, but it leaves no `KernelParamStatus` for itself and loops in the controller log. Section 4
   asserts all 21 statuses.
5. *BIOS lock, read-only.* `drivers/powercap/intel_rapl_common.c` (v6.18): `rapl_detect_powerlimit` sets `locked` from
   the PL lock bit and `pr_info`s "locked by BIOS"; `get_domain_enable` returns `enabled=0` when PL1 is locked;
   `rapl_write_pl_data` returns `-EACCES` for a locked limit. Measured: `enabled=1` on all three nodes, and the
   boot dmesg of 02 and 03 contains no "locked by BIOS" line (01's ring buffer has rotated past boot; `enabled=1`
   covers it). PL1 and PL2 share the MSR's single lock bit. No write test was done in planning; section 4.1 is
   the after-apply read-back that STOPs if a value did not stick.
6. *Why not the card-level iGPU file.* `drivers/gpu/drm/i915/gt/intel_gt_sysfs_pm.c` `sysfs_gt_attribute_w_func`:
   a write to `card*/gt_max_freq_mhz` iterates **every GT**; Meteor Lake has `gt0` (render, RP0 2200) and `gt1`
   (media, RP0 1300), and `intel_guc_slpc_set_max_freq` rejects `val > rp0_freq` with `-EINVAL`. The card-level
   write of 1500 would set gt0 and then fail on gt1 -> a permanent Talos controller error. The plan writes
   `gt/gt0/rps_max_freq_mhz` instead.
7. *The DRM card index is not stable.* nuc14-03's boot dmesg: `[drm] Initialized simpledrm ... on minor 0`, so i915
   registered as card1; 01/02 have no simpledrm and i915 is card0. There is no index-free path to the GT files (even
   `/sys/devices/pci0000:00/0000:00:02.0/drm/cardN` carries N), so the iGPU key is per node, premise-checked, and
   re-checked after any reboot or BIOS change (section 6).
8. *talhelper renders it.* talhelper 3.1.17 on a scratch copy of the post-migration tree (the
   `talconfig-multidoc-migration` Appendix A diff applied) plus these patches: one `SysfsConfig` document per node
   with 21 keys (global 20 + per-node 1 merged), correct card per node, no `machine.sysfs`; `talosctl validate
   --mode metal` passes on all three. The rollback variant (`sysfs-patches.py orig`) renders the same 21 keys with
   the old values.

**Lower limit wins? Only partly - read before the BIOS follow-up.** The MSR limit Talos writes REPLACES the BIOS
value in `MSR_PKG_POWER_LIMIT` (unless the BIOS locks it). It is not a min() with the BIOS setting. Hardware does
enforce the lower of the MSR limit and the MCHBAR (MMIO) limit, and BIOS PL settings usually program both; there is
no `intel-rapl-mmio` zone on these nodes to read the MMIO side. So after a BIOS change (section 6) the effective
limit must be MEASURED (capbench), not assumed.

## 2. Pre-checks

Run from the repo root on the Mac mini, mise activated, talosctl v1.14.x client (`mise exec -- talosctl version
--client --short`; the v1.13.10 client in some shells is too old for v1.14 documents). **`W` is a FIXED mode-700 scratch dir outside the repo** (`/private/tmp/sysfscaps-talos-sysfs-power-caps`); shell
variables do not survive between agent Bash calls, so every later code block starts with the guard line
`W=/private/tmp/sysfscaps-talos-sysfs-power-caps; test -d "$W" || { echo NO_W; exit 1; }`. If `$W` is lost
mid-plan, re-create it with this block and re-run 3.2 (the rollback configs `rb/` are re-renderable from ANY tree
with `sysfs-patches.py <tree> orig`, they do not depend on the forward commit) - but `live-*.yaml` (3.5) and the
Phase A numbers are then gone: re-take them before continuing. Rendered configs contain machine secrets: never `cat` them, never print a dry-run diff.

```bash
cd /Users/mu/code/cberg-home-nextgen
umask 077; W=/private/tmp/sysfscaps-talos-sysfs-power-caps; mkdir -p "$W"; chmod 700 "$W"   # FIXED path: it holds
# the rollback configs, backups, bench-mb, ci-ref across Phase A, the window, Phase C and the +24 h soak.
export SOPS_AGE_KEY_FILE=$PWD/age.key
for b in sysfs-patches talconfig-edit sysfs-diffgate sysfs-readback capbench capstats; do
  awk -v b="$b" '$0=="```python " b {f=1;next} /^```$/{f=0} f' runbooks/maintenance/plans/talos-sysfs-power-caps.md > "$W/$b.py"
  python3 -c "import ast,sys; ast.parse(open(sys.argv[1]).read())" "$W/$b.py" && test -s "$W/$b.py" || echo "EXTRACT FAILED $b"
done
```

2.1 **Premises**: `.venv/bin/python3 runbooks/plan-premises.py talos-sysfs-power-caps --require-premises` -> all PASS
(`multidoc-migration-applied-on-all-nodes` fails until the migration has executed: STOP, wrong window).

2.2 **Cluster health**: 3 nodes `Ready`; `talosctl -n 192.168.55.11,192.168.55.12,192.168.55.13 etcd status` -> 3
members, no learner, no ERRORS; `flux get kustomizations -A | awk 'NR==1 || $5 != "True"'` -> header only.
Record the etcd leader (apply it LAST in 3.6).

2.3 **Single machineconfig, nothing staged**: `talosctl -n <ip> get machineconfig` lists only `v1alpha1` on each node.

2.4 **Card index and current values, per node** (also the rollback baseline):
```bash
W=/private/tmp/sysfscaps-talos-sysfs-power-caps; test -d "$W" || { echo NO_W; exit 1; }
for ip in 192.168.55.11 192.168.55.12 192.168.55.13; do mise exec -- python3 "$W/sysfs-readback.py" $ip orig | tail -1; done
talosctl -n 192.168.55.13 list /sys/class/drm | grep -E ' card[0-9]$'     # i915 card on 03: expect card1
```
PASS = `GATE_PASS ... mode=orig keys=21 mismatches=0` x3 (it reads every key at the card index the patches use, plus
PL4, the PL1 time window and gt1 as untouched neighbours). A `MISMATCH ... ERR(... no such file ...)` on the `drm`
key means the card index moved (e.g. after the talos-linux-1.14.2 roll or a monitor attached): change `CARD` in
`$W/sysfs-patches.py` AND in `$W/sysfs-readback.py` for that node to the measured card, note it in the commit
message, and continue. Any other mismatch (a value is no longer the 2026-10-04 default) -> STOP: the rollback
values would be wrong; re-plan.

2.5 **No CI shard running during a benchmark**: `kubectl get pods -n ci-runner --field-selector=status.phase=Running
-o wide` - a benchmark on a node with a CI shard is still valid for the power gate but not for the BEFORE/AFTER
performance figure; run that node's capbench when it is CI-free, or note "CI present" in the table.

### 2.6 Phase A - BEFORE baseline (IN-WINDOW, the first ~35 min; owner: the window agent; nothing here changes config)

**Pre-check first: the talos dir must be clean** - `git status --porcelain kubernetes/bootstrap/talos` prints nothing.
`git commit --only talconfig.yaml` in 3.4 commits the WHOLE working-tree file, so another session's uncommitted
hunks there (seen 2026-10-04 while the migration was in flight) would ride along. Not clean -> STOP.

A1. **CI performance run** (fixed commit, fixed suites, recorded so Phase C repeats it exactly):
```bash
W=/private/tmp/sysfscaps-talos-sysfs-power-caps; test -d "$W" || { echo NO_W; exit 1; }
REF=$(git ls-remote https://github.com/nachtschatt3n/the-ninth-banner.git HEAD | cut -c1-7); echo "$REF" > "$W/ci-ref"
A1_START=$(date +%s); scripts/ninth-banner-test.sh "$REF" sims 4; echo "sims rc=$?"
scripts/ninth-banner-test.sh "$REF" e2e 3; echo "e2e rc=$?"; A1_END=$(date +%s); echo "$A1_START $A1_END" > "$W/ci-before-window"
```
Record per shard the RUNNING time (not the queue time: the thermal gate's admission wait differs before/after):
for each finished shard pod, `kubectl get pod -n ci-runner <pod> -o jsonpath='{.status.startTime} {.status.containerStatuses[0].state.terminated.finishedAt}'`
(the Job TTL is 600 s: read them right after each run; the run's `job.yaml` in `~/ci-results/<run>/` names the Job).
Value = median shard run time per suite. Also note which nodes the shards ran on.

A2. **Heat/power under that CI load** (Prometheus, CI window from A1):
`mise exec -- python3 "$W/capstats.py" before-ci <minutes of A1> $A1_END` -> one `CAPSTATS before-ci <ip> ...` line per node.
`CAPSTATS_ABORT` (a metric family without exactly 3 nodes) -> fix the instrument first; never record a blind zero.
Also a quiet-hour reference: `mise exec -- python3 "$W/capstats.py" before-24h 1440`.

A3. **Fixed-work CPU benchmark per node, at 64 W** (busybox `sha256sum` x18 workers, steady package power read
from `energy_uj` at t+40 s..t+70 s, watchdog force-deletes the pod at >= 95 °C, grace 0, workers trapped):
```bash
W=/private/tmp/sysfscaps-talos-sysfs-power-caps; test -d "$W" || { echo NO_W; exit 1; }
mise exec -- python3 "$W/capbench.py" 192.168.55.11 calib 2048     # calibrate ONCE: wall_s must be 90-150 s; else scale MB
                                                      # (MB_new = 2048 * 120 / wall_s, rounded to 256) and repeat
echo <MB> > "$W/bench-mb"
for ip in 192.168.55.11 192.168.55.13 192.168.55.12; do mise exec -- python3 "$W/capbench.py" $ip before $(cat "$W/bench-mb"); sleep 180; done
```
Keep every `CAPBENCH ...` line. **Negative control for gate 4.3, PER NODE:** each node's `before` `steady_w` must
read **>= 42 W** (64 W cap, 18 busy threads; a hot-aborted run still prints `steady_w` when it ran past t+40 s).
A node whose before-run read < 42 W (or aborted before t+40 s) has no proof that 4.3 can fail on it: for that node
4.3 is downgraded to informational and the deciding gate is 4.1 alone - say so in the report.
A `CAPBENCH_INVALID ... hot_abort=True` is itself a baseline result (record "aborted at 95 °C after N s"); the
after-run then reports wall time without a before value.

## 3. Steps

### 3.1 Repo change (Flux does NOT reconcile `kubernetes/bootstrap/talos/`)

Gate: Phase A is complete - `test -s "$W/bench-mb" && test -s "$W/ci-ref" && test -s "$W/stats-before-ci.json"`
and three `CAPBENCH ... phase=before` lines are in the window log. Missing -> run Phase A first (the BEFORE numbers
cannot be taken once the caps are live).

```bash
W=/private/tmp/sysfscaps-talos-sysfs-power-caps; test -d "$W" || { echo NO_W; exit 1; }
mise exec -- python3 "$W/sysfs-patches.py" kubernetes/bootstrap/talos caps      # -> SYSFS_PATCHES_OK mode=caps (4 files)
mise exec -- python3 "$W/talconfig-edit.py"                                     # -> TALCONFIG_EDIT_OK
git diff --stat kubernetes/bootstrap/talos/talconfig.yaml          # 1 file, 7 insertions
```
`talconfig-edit.py` asserts the post-migration shape (exactly one `machine-sysctls.yaml` line, one entry per
hostname, no prior `machine-sysfs-power.yaml`) and refuses to run twice (dry-tested: second run -> AssertionError).
Resulting talconfig diff (dry-tested on the migrated scratch tree, identical to the render input of section 1.8):
```
>   - "@./patches/global/machine-sysfs-power.yaml"          (after machine-sysctls.yaml)
>     patches:
>       - "@./patches/node/k8s-nuc14-01-sysfs-igpu.yaml"     (same for -02, -03 under each hostname)
```

### 3.2 Render the forward AND the rollback configs into `$W` (never into `clusterconfig/`)

```bash
W=/private/tmp/sysfscaps-talos-sysfs-power-caps; test -d "$W" || { echo NO_W; exit 1; }
(cd kubernetes/bootstrap/talos && mise exec -- talhelper genconfig -o "$W/fw") 2>&1 | grep -v '^generated'
rsync -a --exclude clusterconfig kubernetes/bootstrap/talos/ "$W/rbsrc/"
mise exec -- python3 "$W/sysfs-patches.py" "$W/rbsrc" orig                       # -> SYSFS_PATCHES_OK mode=orig
(cd "$W/rbsrc" && mise exec -- talhelper genconfig -o "$W/rb") 2>&1 | grep -v '^generated'
for d in fw rb; do for n in 01 02 03; do
  mise exec -- talosctl validate --config "$W/$d/kubernetes-k8s-nuc14-$n.yaml" --mode metal 2>&1 | tail -1
  python3 - "$W/$d/kubernetes-k8s-nuc14-$n.yaml" <<'PY'
import sys, yaml
s = [d for d in yaml.safe_load_all(open(sys.argv[1])) if d and d.get("kind") == "SysfsConfig"]
print(sys.argv[1].rsplit("/", 2)[-2:], "SysfsConfig docs", len(s), "keys", len(s[0]["params"]) if s else 0,
      sorted(set(s[0]["params"].values())) if s else None, [k for k in s[0]["params"] if "drm" in k] if s else None)
PY
done; done
```
PASS = 6x `is valid for metal mode`; each line `SysfsConfig docs 1 keys 21`; `fw` values
`['1500', '35000000', '55000000', 'balance_power']`, `rb` values `['2200', '64000000', 'balance_performance']`;
the `drm` key names card0 for 01/02 and card1 for 03 (or the card measured in 2.4). Anything else -> STOP.

### 3.3 Dry-run gates per node: forward AND rollback (the node decides, the gate reads the diff)

```bash
W=/private/tmp/sysfscaps-talos-sysfs-power-caps; test -d "$W" || { echo NO_W; exit 1; }
for n in 1 2 3; do ip=192.168.55.1$n
  for d in fw rb; do
    mise exec -- talosctl -n $ip apply-config --dry-run --mode=no-reboot -f "$W/$d/kubernetes-k8s-nuc14-0$n.yaml" > "$W/dry-$d-$n.txt" 2>&1
    echo "node0$n $d rc=$? $(sed -n 2p "$W/dry-$d-$n.txt")"
    mise exec -- python3 "$W/sysfs-diffgate.py" "$W/dry-$d-$n.txt" 21 add
  done
done
```
PASS = for all six: `rc=0`, `Applied configuration without a reboot (skipped in dry-run).`, and
`GATE_PASS keys=21/21 plus=21 minus=0 non_sysfs_changed_lines=0`. **Never print `dry-*.txt`.** The gate
counts changed diff lines that are not one of the 21 SysfsConfig keys (or the new document's 4 header lines)
without echoing them. A non-zero `non_sysfs_changed_lines` means the live config differs from the repo
somewhere else (drift, or the migration not fully applied) and this apply would change that too -> STOP.
**Measured 2026-10-04 (gate negative control):** against today's PRE-migration nodes the same gate prints
`GATE_FAIL ... non_sysfs_changed_lines=155`; injected controls (a foreign `+machine:` line -> FAIL, expected count 20
-> FAIL) fail; a rollback-shaped diff (`-`/`+` per key) passes only in `change` mode; a duplicated key line (plus=22) fails.
A real PASS on a post-migration node has NOT been observed (impossible before the migration); the gate's failure
mode is a false STOP (e.g. an unexpected diff alignment of the new document's header lines), never a false GO:
if it STOPs, inspect the diff's line COUNTS by hand (`grep -c '^[+-]' "$W/dry-fw-$n.txt"`), never print it.

### 3.4 Commit before applying (config only)

`git commit --only kubernetes/bootstrap/talos/talconfig.yaml kubernetes/bootstrap/talos/patches/global/machine-sysfs-power.yaml kubernetes/bootstrap/talos/patches/node/k8s-nuc14-01-sysfs-igpu.yaml kubernetes/bootstrap/talos/patches/node/k8s-nuc14-02-sysfs-igpu.yaml kubernetes/bootstrap/talos/patches/node/k8s-nuc14-03-sysfs-igpu.yaml -F <unique msg file>`
(the new files need `git add` of exactly those paths first - `--only` with untracked paths fails otherwise);
message `feat(talos): SysfsConfig power caps PL1 35/PL2 55 W, EPP balance_power, iGPU gt0 1500 MHz (config only; applied per node in window)`.
Then `git log -1 --format=%s` is yours, `git show --stat HEAD` lists exactly these 5 files, `git pull --rebase --autostash && git push`.

### 3.5 Pre-apply backup per node (backup_gate)

```bash
W=/private/tmp/sysfscaps-talos-sysfs-power-caps; test -d "$W" || { echo NO_W; exit 1; }
for n in 1 2 3; do ip=192.168.55.1$n
  talosctl -n $ip get machineconfig v1alpha1 -o yaml | python3 -c 'import sys,yaml; print(list(yaml.safe_load_all(sys.stdin))[0]["spec"], end="")' > "$W/live-$ip.yaml"
  test -s "$W/live-$ip.yaml" && echo "backup $ip ok"
done
```
(`$W/live-<ip>.yaml` is the break-glass copy; the planned rollback is `$W/rb/`, already dry-run-proven in 3.3.)

### 3.6 Apply per node - nuc14-01 first (coolest), then the other follower, etcd leader last

```bash
W=/private/tmp/sysfscaps-talos-sysfs-power-caps; test -d "$W" || { echo NO_W; exit 1; }
ip=192.168.55.11; n=01; node=k8s-nuc14-01          # adjust per node
kubectl get node $node -o jsonpath='{.status.nodeInfo.bootID}' > "$W/bootid-$ip"
mise exec -- talosctl -n $ip apply-config --mode=no-reboot -f "$W/fw/kubernetes-k8s-nuc14-$n.yaml"
# expected: "Applied configuration without a reboot"
sleep 10
mise exec -- python3 "$W/sysfs-readback.py" $ip caps --status        # gate 4.1 - must print GATE_PASS
```
Then gates 4.2-4.4 for this node, `mise exec -- python3 "$W/capbench.py" $ip after $(cat "$W/bench-mb")` (gate 4.3), wait
3 min, re-check etcd (`talosctl -n <all three> etcd status`, 3 members, same leader or one clean election, no
ERRORS) and node `Ready`. Only then the next node (SOP talos-upgrade.md §13 lesson 12: serial, health-gated).
**Any gate failure -> section 5 for THAT node and stop the roll.**

### 3.7 After the third node: regenerate the local clusterconfig

```bash
W=/private/tmp/sysfscaps-talos-sysfs-power-caps; test -d "$W" || { echo NO_W; exit 1; }
cp -Rp kubernetes/bootstrap/talos/clusterconfig "$W/clusterconfig-pre"
mise exec -- task talos:generate-config
git status --short kubernetes/bootstrap/talos/clusterconfig/      # nothing: gitignored
```

### 3.8 Phase C - AFTER measurements (IN-WINDOW, last ~22 min; owner: the window agent)

Repeat A1 with the SAME `$(cat "$W/ci-ref")` and suites, then A2 (`capstats.py after-ci ...`). The A3 `after`
benchmarks were taken per node in 3.6. Fill the table in section 4.B and attach it to the window report.
Then set the plan to `awaiting-soak` (24 h soak, 3.10).

### 3.9 Alert threshold follows the cap (Flux-reconciled; after all three nodes passed section 4)

`node-thermal-alerts.yaml` says: *"When the talos-sysfs-power-caps plan lowers PL1, lower this threshold to ~90 % of
the new cap"*. 90 % of 35 W = 31.5 -> 31. Committed separately from 3.4 on purpose: a mid-roll abort must not
leave the alert tuned for a cap that is not live. Dry-tested on scratch copies 2026-10-04 (promtool suite: 12/12
PASS incl. the moved mutant; unmodified suite also PASS):
```bash
W=/private/tmp/sysfscaps-talos-sysfs-power-caps; test -d "$W" || { echo NO_W; exit 1; }
sed -i '' 's/expr: rate(node_rapl_package_joules_total{job="node-exporter"}\[5m\]) > 58$/expr: rate(node_rapl_package_joules_total{job="node-exporter"}[5m]) > 31/' kubernetes/apps/monitoring/kube-prometheus-stack/app/node-thermal-alerts.yaml
sed -i '' 's/(expected cap 64 W)/(expected cap 35 W)/' kubernetes/apps/monitoring/kube-prometheus-stack/app/node-thermal-alerts.yaml
sed -i '' -e 's/s(rapl, "0+1800x80")\],  # 60 W/s(rapl, "0+1020x80")],  # 34 W/' \
          -e 's/s(rapl, "0+1200x80")\],  # 40 W/s(rapl, "0+840x80")],  # 28 W/' \
          -e 's/mut("power threshold 30"/mut("power threshold 25"/' \
          -e 's/replace("> 58", "> 30")/replace("> 31", "> 25")/' runbooks/tests/test-node-thermal-alerts.py
python3 runbooks/tests/test-node-thermal-alerts.py > "$W/promtool.txt" 2>&1; echo "rc=$?"; grep -vc '^PASS' "$W/promtool.txt"
```
PASS = `rc=0` and `0` non-PASS lines. Resulting diff: `> 58` -> `> 31`, `(expected cap 64 W)` -> `(expected cap 35 W)`;
test fixtures 60 W/40 W -> 34 W/28 W (fires above 31, silent below), mutant `> 31` -> `> 25` (must be caught).
and the rule comment (lines 170-171, `Expected cap = the CURRENT PL1/PL2 of 64 W` / `Fires at >=90 % of it (58 W)`):
```bash
W=/private/tmp/sysfscaps-talos-sysfs-power-caps; test -d "$W" || { echo NO_W; exit 1; }
F=kubernetes/apps/monitoring/kube-prometheus-stack/app/node-thermal-alerts.yaml
sed -i '' -e 's/# Expected cap = the CURRENT PL1\/PL2 of 64 W (constraint_0\/1_power_limit_uw$/# Expected cap = PL1 35 W (SysfsConfig, plan talos-sysfs-power-caps; constraint_0_power_limit_uw/' \
          -e 's/# on all three nodes, 2026-10-04). Fires at >=90 % of it (58 W) held$/# on all three nodes). Fires at >=90 % of it (31 W) held/' "$F"
grep -c 'Expected cap = PL1 35 W' "$F"; grep -c 'of it (31 W) held' "$F"     # 1 and 1
```
`git commit --only` those two files, message `fix(monitoring): NodeCPUPackagePowerAtCap follows the 35 W PL1 (talos-sysfs-power-caps)`;
verify subject, push. Verify the rule is LOADED with the new threshold (memory: an unloaded PrometheusRule fails silently):
`kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/rules' | python3 -c 'import sys,json; print([r["query"] for g in json.load(sys.stdin)["data"]["groups"] for r in g["rules"] if r["name"]=="NodeCPUPackagePowerAtCap"])'`
-> contains `> 31` (may take one Flux interval + rule reload).

### 3.10 SOAK step (+24 h, next sweep or operator): raise the CI thermal gate - conditional

Owner: the gate lives in THIS repo (`scripts/ninth-banner-admit.py`, runs on the Mac, ticked by every
`ninth-banner-test.sh`; no Flux step) and was edited three times on 2026-10-04 by the ci-runner work -
coordinate with whoever holds that work (check `git log -3 -- scripts/ninth-banner-admit.py` right before the edit;
if it changed after this plan's premise run, re-read the thresholds before changing one).

**Proposal: `GATE_OPEN_BELOW_C` (browser lane, first CI pod) 85 -> 88 °C.** Only this one. `HOT_C 93`,
`SECOND_*`, `CPU_*` and the per-node `BRAKE_C 100` stay: they are the safety rails, and the browser first-pod
threshold is the one that today keeps nuc14-02/03 mostly closed (SOP §2b: "nuc14-02 never gets a CI pod ...
peaks at 96-98 °C even without CI"). 88 equals the cpu lane's existing `CPU_OPEN_BELOW_C`.

**Evidence required (all four, from the 24 h soak `capstats.py soak-24h 1440` + the Phase C table):**
(a) every node's `temp_p95` <= 85 °C over 24 h; (b) `min_ge100` = 0 on every node (no brake-level minute);
(c) `throttles` (24 h package-throttle increase) < 100 on every node (today: 77 / 29 018 / 10);
(d) Phase C CI window: `temp_max` < 93 on every node that ran a shard (`CAPSTATS after-ci <ip> ... temp_max=`,
from 3.8; it is the max over the 30 s-step node maximum, i.e. the gate's 1-min view or stricter). If any fails: do NOT raise; record the numbers on the
plan and leave 85. If all pass:
```bash
W=/private/tmp/sysfscaps-talos-sysfs-power-caps; test -d "$W" || { echo NO_W; exit 1; }
sed -i '' 's/^OPEN_BELOW_C = float(os.environ.get("GATE_OPEN_BELOW_C", "85"))$/OPEN_BELOW_C = float(os.environ.get("GATE_OPEN_BELOW_C", "88"))/' scripts/ninth-banner-admit.py
python3 -c "import ast; ast.parse(open('scripts/ninth-banner-admit.py').read())" && grep -c 'GATE_OPEN_BELOW_C", "88"' scripts/ninth-banner-admit.py   # 1
scripts/ninth-banner-admit.py --status | head -5      # read-only: prints node state with the new limit
```
(dry-tested on a scratch copy: one-line diff, parses.) Update `docs/sops/ci-runner.md` in the same commit: line 14
("first pod only below 85 °C") and the §2b table row "browser lane open when" (`< 85 °C` -> `< 88 °C`, with
"raised 2026-10-xx after the talos-sysfs-power-caps soak: p95/max/throttle numbers"), plus a Version History line.
Rollback of this step: `git revert` it; takes effect on the next tick.

## 4. Verification (per node right after its apply, then cluster-wide)

**4.1 CONTENTS ASSERTION: the node holds exactly the 21 target values, and Talos owns them.** Measured by
`sysfs-readback.py <ip> caps --status`: reads all 21 files back from `/sys` (`talosctl read`), checks PL4,
the PL1 time window and the media GT `gt1` are UNCHANGED (120000000 / 27983872 / 1300), and requires a
`KernelParamStatus` `sys.<key>` with `current` = target for every key and no foreign `sys.*` status.
PASS = `GATE_PASS node=<ip> mode=caps keys=21 mismatches=0`. What failure prints: a BIOS-locked or ignored write
reads back `64000000` (`MISMATCH ... want 35000000 got 64000000`); a wrong card index reads `ERR(...no such file...)`;
a key Talos failed to write has `KernelParamStatus ... got None`. Measured 2026-10-04: today the same command prints
`GATE_FAIL ... mismatches=21` (`caps`), and `orig` without `--status` prints `GATE_PASS` on all three nodes, so the
gate can fail both ways. **FAIL -> section 5 for this node, stop the roll.**

4.2 **No reboot.** `kubectl get node $node -o jsonpath='{.status.nodeInfo.bootID}'` equals `$W/bootid-$ip` (a reboot
changes it) - deciding. *Informational only:* `talosctl -n $ip logs controller-runtime | grep -c 'KernelParamSpecController'`
- the reviewer found ZERO lines of this controller in ~14 h of buffer on all nodes, so "0 errors" was never shown
to be able to read non-zero; a missing write is caught by 4.1's per-key `KernelParamStatus` instead.

**Deciding gates** (the only ones that may PASS a node): 4.1 (`--status`, measured to fail both ways), 4.2 bootID,
4.3 capbench (where its per-node negative control held), and `capstats.py` numbers (with its coverage abort).

4.3 **CONTENTS ASSERTION: the cap actually binds under load.** Measured by `capbench.py <ip> after <MB>`:
`steady_w` = RAPL package energy over t+40..t+70 s of an 18-thread fixed-work run, read with `talosctl read
energy_uj` (Prometheus-independent). PASS = `CAPBENCH` (not `_INVALID`) and `steady_w <= 37.5` (35 W PL1 + 7 %
measurement slack: two talosctl reads ~0.2 s each in a 30 s window). It can fail: Phase A's `before` run must
have read >= 42 W on at least one node (negative control, 2.6 A3); a cap that did not take, or was clamped back by
firmware, reads ~45-64 W. Idle reference 2026-10-04: 14-17 W on all nodes, so an idle node can NOT pass for the
wrong reason - `_INVALID` (wall < 75 s or no samples) is not a pass.
CONTROL: metric node_rapl_package_joules_total - cross-check: `rate(...[1m])` for the node during the capbench run
must peak <= 56 W (PL2) and settle <= 37.5 W; also feeds `rapl_avg_w`/`rapl_max1m_w` in 4.B.

4.4 **EPP took effect on behaviour, not just on the file.** In the same capbench run, the after `peak_c` must be
lower than the node's before `peak_c` (or the before run hot-aborted). Not a hard gate (room temperature varies);
a HIGHER peak at 35 W is a STOP-and-look: it means something other than package power drives the heat.

4.5 **Cluster-wide, after the third node (and again at the 24 h soak):**
- CONTROL: metric node_thermal_zone_temp - `capstats.py` `temp_avg/temp_p95/temp_max/min_ge100` per node
  (aggregated `max by (instance)` so a node-exporter pod roll cannot hide a node's series; measured 2026-10-04: the
  un-aggregated query read 59 °C for a node whose real 1-h max was 102 °C).
- CONTROL: metric node_cpu_package_throttles_total - 24 h increase per node; expected to FALL (it counts thermal/
  PROCHOT events, not power-limit clamping). A RISE on any node -> STOP-and-look.
- CONTROL: metric node_hwmon_temp_celsius - NVMe composite max (should not change; a rise says airflow, not CPU).
- CONTROL: alertname NodeCPUPackageHot - INFORMATIONAL (recorded in 4.B; zero firing history in the last 24 h even
  with 102 °C peaks, so "not firing" cannot fail here - the capstats temp numbers decide).
- CONTROL: alertname NodeCPUThermalThrottling - INFORMATIONAL for the same reason; capstats `throttles` decides.
- CONTROL: alertname NodeRAPLMetricsMissing - INFORMATIONAL; capstats' coverage/node-count abort decides.
- CONTROL: alertname NodeCPUPackagePowerAtCap - after 3.9: may fire (info) under sustained batch load; that is the
  cap working, recorded in 4.B, not a failure.
- Stability: `kubectl get nodes` all Ready the whole window; etcd leader changes during the window <= 1
  (`talosctl etcd status` before/after; `etcd_server_leader_changes_seen_total` increase via Prometheus);
  no new pod restarts in kube-system/storage/network vs the 2.2 snapshot (`kubectl get pods -A` restart columns).
- `capstats.py` aborting (`CAPSTATS_ABORT`) is a FAILED gate, not a skipped one.

### 4.B BEFORE / AFTER comparison (operator request 2026-10-04) - fill and attach to the window report

| metric (per node 01 / 02 / 03) | BEFORE (Phase A, 64 W) | AFTER (Phase C, 35/55 W) | delta % | success criterion |
|---|---|---|---|---|
| CI-window package temp avg / p95 / max (°C) | | | | p95 <= ~85 °C |
| minutes >= 100 °C in CI window | | | | 0 |
| package-throttle increase, CI window | | | | ~0 under CI |
| package-throttle increase, 24 h (soak) | 77 / 29 018 / 10 (2026-10-04) | | | < 100 each |
| RAPL avg W / max 1-min W, CI window | | | | max 1-min <= ~55 W |
| NVMe max (°C) | | | | unchanged |
| capbench steady W | | | | <= 37.5 W |
| capbench wall s (fixed work) | | | | report; regression expected |
| capbench peak °C | | | | lower |
| CI median shard run time, sims (s) | | | | regression <= ~10-15 % (flag worse) |
| CI median shard run time, e2e (s) | | | | regression <= ~10-15 % (flag worse) |
| stability: NotReady / etcd leader changes / kube-system restarts | | | | 0 / <= 1 / 0 |

delta % = (after - before) / before. CI times are noisy (shard placement depends on the gate) - report the median and
the nodes each shard ran on. **Soak point (+24 h, `capstats.py soak-24h 1440`)** fills the 24 h rows; it is the
input to 3.10.

## 5. Rollback

**Per node (primary; no reboot): apply the pre-rendered, dry-run-proven rollback config with the explicit old values.**
```bash
W=/private/tmp/sysfscaps-talos-sysfs-power-caps; test -d "$W" || { echo NO_W; exit 1; }
mise exec -- talosctl -n $ip apply-config --mode=no-reboot -f "$W/rb/kubernetes-k8s-nuc14-0$n.yaml"
sleep 10; mise exec -- python3 "$W/sysfs-readback.py" $ip orig --status       # must print GATE_PASS ... mode=orig ... mismatches=0
```
Confirmed back when it prints `GATE_PASS`: PL1/PL2 64000000, EPP balance_performance on 18 CPUs, gt0 2200, and Talos
holds them as `KernelParamStatus`. If the forward apply failed on a key (e.g. ENOENT), the rollback config carries
the same key and fails the same way: in that case break-glass `talosctl -n $ip apply-config --mode=no-reboot -f
"$W/live-$ip.yaml"` (no SysfsConfig at all) - Talos then writes back the captured pre-change value for every key
it had written (evidence 3, section 1) - and verify with `sysfs-readback.py $ip orig` (no `--status`).
If the roll stopped on node N, roll back nodes already done in reverse order only if the failure was a behaviour
problem; a node that passed section 4 may keep the caps.

**Repo:** `git revert <3.4 sha>` (and `<3.9 sha>` / `<3.10 sha>` if they landed), push. Flux reconciles nothing for
the talos part. The nodes then still carry the explicit-old-values SysfsConfig from the rollback apply; the NEXT
machine-config apply from the reverted repo removes the document, and Talos writes the same captured values back
(a no-op in effect). Restore the local dir: `rm -rf kubernetes/bootstrap/talos/clusterconfig && cp -Rp
"$W/clusterconfig-pre" kubernetes/bootstrap/talos/clusterconfig`.

**Note on the explicit-value rollback:** it pins 64 W in software. If the BIOS is later set LOWER (section 6), a node
still carrying the rollback document would raise the MSR back to 64 W at every boot - remove the document then.

**Forward-only parts:** none. No data, no reboot, no etcd or apiserver change.
**Cleanup:** `rm -rf /private/tmp/sysfscaps-talos-sysfs-power-caps` (machine secrets) only AFTER the 3.10 soak step
has run (or after a completed rollback) - it holds the rollback configs until then.

## 6. Interference notes

- **Order:** after `talconfig-multidoc-migration` (depends_on; it is `exclusive`, so a later window). Never the same
  night as `talos-linux-1.14.2` (conflicts_with). If the 1.14.2 roll runs AFTER this plan, its reboots are the first
  real test that Talos re-applies all 21 keys at boot (the controller retries until i915/intel_pstate/RAPL exist):
  that plan's post-node gates should run `sysfs-readback.py <ip> caps --status` per node - repo correction for
  that plan's author. If it runs BEFORE, re-measure the card index (2.4).
- **Card index after ANY reboot / BIOS update / monitor plugged in:** a moved index turns the iGPU key into a
  permanent ENOENT retry loop (the other 20 keys still apply). The sweep can detect it read-only:
  `talosctl -n <ip> get kernelparamstatuses` lacks the `sys.class/drm/...` row.
- **BIOS follow-up (operator-physical, AFTER this plan): PL1/PL2, fan curve, BIOS 0054, After Power Failure.**
  The RAPL keys here OVERWRITE the BIOS's MSR value at boot (no min()); hardware takes the lower of MSR and MMIO,
  and BIOS settings usually program both - but this is to be measured, not assumed. After a BIOS change: run
  2.4 (`sysfs-readback.py <ip> caps`) and `capbench.py <ip> bios <MB>`. If the BIOS was set lower than 35/55 W
  and the MSR now reads 35/55 again, lower the SysfsConfig values to the BIOS values (or drop the two RAPL keys).
  If the BIOS sets the lock bit, Talos's write fails with EACCES every retry: drop the two RAPL keys in the same
  change. BIOS 0054 may also change the card index (simpledrm) - premise `igpu-card-index-*`.
- **Workload impact (expected, capability_change):** sustained all-core throughput falls (package 64 -> 35 W);
  short bursts keep 55 W for PL2's ~2.4 ms window and PL1's 28 s moving average. iGPU render GT max 2200 -> 1500
  MHz: frigate/immich-ml OpenVINO and Chromium-on-iGPU CI get slower; video DECODE/ENCODE run on the media GT and
  its engines (gt1, untouched). No open plan's verification is an iGPU or CPU throughput benchmark (checked the
  igpu-i915 plans 2026-10-04), so `shared: igpu-i915` is a warning, not a conflict.
- **CI runner:** the capbench pods are BestEffort with a 100m request and land on one node at a time; the CI gate
  sees their heat as production heat. Run Phase A/C CI runs with no other CI in flight.
- **Monitoring is the instrument** (section 4.5): no open kube-prometheus-stack plan; any future same-night one must
  conflict both ways.
- **Reciprocity (repo correction for other plans' authors):** `talos-linux-1.14.2` should add `talos-sysfs-power-caps`
  to its `conflicts_with` and a per-node post-reboot `sysfs-readback.py <ip> caps --status` + card-index re-measure;
  `talconfig-multidoc-migration` may list this plan as a dependent. Not edited here (planner writes only this file).
- **Repo corrections found while planning (not silently planned around):**
  1. The research recommendation's card-level `class/drm/card0/gt_max_freq_mhz` would fail on Meteor Lake (writes
     every GT; gt1 rejects 1500) and `card0` is wrong on nuc14-03. This plan uses `gt/gt0/rps_max_freq_mhz` per node.
  2. "Lower limit wins if the BIOS later sets lower limits" does not hold for the MSR this plan writes (it replaces
     the BIOS MSR value); only MSR-vs-MMIO is a min(). Section 6 BIOS bullet is the procedure.
  3. "SysfsConfig removed -> values persist until reboot" is not Talos behaviour: removal writes back the captured
     pre-change value live (`resetKernelParam`).
  4. No sweep finding tracks node thermals/power (queried 2026-10-04); a PLAN-lane finding for "NUC14 package
     temperature / throttle" would let the sweep track this plan's soak. Not filed by the planner.

## Appendix A - scripts (extracted by section 2's awk loop; all dry-tested 2026-10-04)

### sysfs-patches.py

```python sysfs-patches
# Writes the 4 SysfsConfig patch files. argv[1] = talos dir; argv[2] = caps|orig
# (orig renders the ROLLBACK variant: same keys, the 2026-10-04 BIOS/driver values).
import os, sys
T, mode = sys.argv[1], sys.argv[2]
PL1, PL2, EPP, GT = {"caps": ("35000000", "55000000", "balance_power", "1500"),
                     "orig": ("64000000", "64000000", "balance_performance", "2200")}[mode]
CARD = {"01": "card0", "02": "card0", "03": "card1"}   # live 2026-10-04; re-checked in section 2.4
os.makedirs(f"{T}/patches/node", exist_ok=True)
hdr = f'''# Software power/thermal caps (plan talos-sysfs-power-caps, 2026-10-04).
# NUC14RVK / Core Ultra 5 125H ship PL1=PL2=64 W (ASUS default) with EPP
# balance_performance; 7-day package peaks 95-103 C, nuc14-02 ~29k
# package-throttle events/24h. SLASH-separated keys on purpose: a dotted key
# has '.'<->'/' swapped by Talos (pkg/machinery/kernel Param.Path), which
# mangles 'intel-rapl:0'. Talos prefixes /sys itself.
# The RAPL MSR is a plain write: a value here OVERRIDES what the BIOS put in
# MSR_PKG_POWER_LIMIT at boot. If the BIOS is later set LOWER, lower these
# too or drop the keys (plan section 6).
apiVersion: v1alpha1
kind: SysfsConfig
params:
  # RAPL package-0: PL1 (long_term), PL2 (short_term). Time windows (PL1 tau
  # ~28 s, PL2 2.44 ms) and PL4 (peak_power 120 W) stay at BIOS values.
  class/powercap/intel-rapl:0/constraint_0_power_limit_uw: "{PL1}"
  class/powercap/intel-rapl:0/constraint_1_power_limit_uw: "{PL2}"
  # EPP on every logical CPU (cpu0..cpu17; intel_pstate active, governor powersave)
'''
body = "".join(f'  devices/system/cpu/cpu{i}/cpufreq/energy_performance_preference: "{EPP}"\n' for i in range(18))
open(f"{T}/patches/global/machine-sysfs-power.yaml", "w").write(hdr + body)
for n, c in CARD.items():
    open(f"{T}/patches/node/k8s-nuc14-{n}-sysfs-igpu.yaml", "w").write(f'''# iGPU render GT (gt0) max frequency (RP0 2200 MHz). PER NODE because the DRM
# card index is not stable: nuc14-03 boots with simpledrm on card0, so i915 is
# card1 there (measured 2026-10-04). Do NOT use card-level gt_max_freq_mhz: on
# Meteor Lake it writes EVERY GT and the media GT (gt1, RP0 1300) rejects a
# value above 1300 with EINVAL (intel_guc_slpc_set_max_freq). Plan talos-sysfs-power-caps.
apiVersion: v1alpha1
kind: SysfsConfig
params:
  class/drm/{c}/gt/gt0/rps_max_freq_mhz: "{GT}"
''')
print(f"SYSFS_PATCHES_OK mode={mode}")
```

### talconfig-edit.py

```python talconfig-edit
import sys
p = "kubernetes/bootstrap/talos/talconfig.yaml"; t = open(p).read()
a = '  - "@./patches/global/machine-sysctls.yaml"\n'
assert t.count(a) == 1 and "machine-sysfs-power.yaml" not in t, "talconfig not in the expected post-migration shape"
t = t.replace(a, a + '  - "@./patches/global/machine-sysfs-power.yaml"\n')
for n in ("01", "02", "03"):
    h = f'  - hostname: "k8s-nuc14-{n}"\n'
    assert t.count(h) == 1, h
    t = t.replace(h, h + f'    patches:\n      - "@./patches/node/k8s-nuc14-{n}-sysfs-igpu.yaml"\n')
open(p, "w").write(t); print("TALCONFIG_EDIT_OK")
```

### sysfs-diffgate.py

```python sysfs-diffgate
import re,sys
# usage: sysfs-diffgate.py <dry-run-output> <expected_key_count> <mode: add|change>
txt=open(sys.argv[1]).read(); want=int(sys.argv[2]); mode=sys.argv[3]
if 'Config diff:' not in txt: print('GATE_FAIL no "Config diff:" in dry-run output'); sys.exit(2)
body=txt.split('Config diff:',1)[1].splitlines()
KEY=re.compile(r'^[+-] {4}(class/powercap/intel-rapl:0/constraint_[01]_power_limit_uw|devices/system/cpu/cpu([0-9]|1[0-7])/cpufreq/energy_performance_preference|class/drm/card[0-9]/gt/gt0/rps_max_freq_mhz): ("?)[a-z_0-9]+\3$')
HDR={'+---','+apiVersion: v1alpha1','+kind: SysfsConfig','+params:'}
plus=minus=bad=0; keys=set()
for l in body:
    if l in ('--- a','+++ b') or not l or l[0] not in '+-': continue
    m=KEY.match(l)
    if m: keys.add(m.group(1)); plus+=l[0]=='+'; minus+=l[0]=='-'
    elif mode=='add' and l in HDR: pass
    else: bad+=1          # content never printed: the diff can carry key material
ok = bad==0 and len(keys)==want and plus==want and (minus==0 if mode=='add' else minus==want)
print(f"{'GATE_PASS' if ok else 'GATE_FAIL'} keys={len(keys)}/{want} plus={plus} minus={minus} non_sysfs_changed_lines={bad}")
sys.exit(0 if ok else 1)
```

### sysfs-readback.py

```python sysfs-readback
#!/usr/bin/env python3
# sysfs-readback.py <node-ip> <caps|orig> [--status]
# Reads every key of the plan's SysfsConfig back from the node's /sys and
# compares with the expected set. --status additionally requires a Talos
# KernelParamStatus per key whose `current` equals the expected value (proves
# it is TALOS that holds the value, not a coincidence). Prints GATE_PASS/FAIL.
import subprocess, sys
ip, mode = sys.argv[1], sys.argv[2]; want_status = "--status" in sys.argv
CARD = {"192.168.55.11": "card0", "192.168.55.12": "card0", "192.168.55.13": "card1"}[ip]
V = {"caps": ("35000000", "55000000", "balance_power", "1500"),
     "orig": ("64000000", "64000000", "balance_performance", "2200")}[mode]
exp = {"class/powercap/intel-rapl:0/constraint_0_power_limit_uw": V[0],
       "class/powercap/intel-rapl:0/constraint_1_power_limit_uw": V[1],
       f"class/drm/{CARD}/gt/gt0/rps_max_freq_mhz": V[3]}
exp.update({f"devices/system/cpu/cpu{i}/cpufreq/energy_performance_preference": V[2] for i in range(18)})
bad = []
for k, v in exp.items():
    r = subprocess.run(["talosctl", "-n", ip, "read", "/sys/" + k], capture_output=True, text=True)
    got = r.stdout.strip() if r.returncode == 0 else f"ERR({r.stderr.strip()[-60:]})"
    if got != v: bad.append(f"{k}: want {v} got {got}")
# untouched neighbours must stay untouched (PL4, time windows, media GT)
for k, v in {"class/powercap/intel-rapl:0/constraint_2_power_limit_uw": "120000000",
             "class/powercap/intel-rapl:0/constraint_0_time_window_us": "27983872",
             f"class/drm/{CARD}/gt/gt1/rps_max_freq_mhz": "1300"}.items():
    got = subprocess.run(["talosctl", "-n", ip, "read", "/sys/" + k], capture_output=True, text=True).stdout.strip()
    if got != v: bad.append(f"{k} (must be untouched): want {v} got {got}")
if want_status:
    import json
    out = subprocess.run(["talosctl", "-n", ip, "get", "kernelparamstatuses", "-o", "json"],
                         capture_output=True, text=True).stdout
    dec, i, st, n = json.JSONDecoder(), 0, {}, 0
    while i < len(out):
        while i < len(out) and out[i].isspace(): i += 1
        if i >= len(out): break
        o, i = dec.raw_decode(out, i); n += 1
        if o["metadata"]["id"].startswith("sys."): st[o["metadata"]["id"]] = str(o["spec"]["current"])
    if n == 0: bad.append("KernelParamStatus list came back EMPTY (talosctl error?) - cannot assert")
    for k, v in exp.items():
        if st.get("sys." + k) != v: bad.append(f"KernelParamStatus sys.{k}: want {v} got {st.get('sys.' + k)}")
    extra = set(st) - {"sys." + k for k in exp}
    if extra: bad.append(f"unexpected sys.* statuses: {sorted(extra)}")
for b in bad[:30]: print("  MISMATCH", b)
print(f"{'GATE_PASS' if not bad else 'GATE_FAIL'} node={ip} mode={mode} keys={len(exp)} mismatches={len(bad)}")
sys.exit(0 if not bad else 1)
```

### capbench.py

```python capbench
#!/usr/bin/env python3
# capbench.py <node-ip> <phase-label> <mb-per-worker> [--dry]
# Fixed-work CPU benchmark on ONE node + Prometheus-independent package power.
# 18 workers (one per logical CPU) each hash <mb> MiB of zeros with busybox
# sha256sum. Prints one line: CAPBENCH node=.. phase=.. wall_s=.. steady_w=..
# steady_w = RAPL package energy delta between t+40 s and t+70 s after the pod
# is Running (past the PL1 tau of ~28 s, so it reads the SUSTAINED limit).
# Watchdog: package >= HOT_ABORT_C (95 C) -> pod deleted, result _INVALID hot_abort=True.
# A result line WITHOUT the _INVALID suffix needs: Succeeded, wall >= 75 s, both energy samples.
import json, subprocess, sys, time
ip, phase, mb = sys.argv[1], sys.argv[2], int(sys.argv[3]); dry = "--dry" in sys.argv
node = {"192.168.55.11": "k8s-nuc14-01", "192.168.55.12": "k8s-nuc14-02", "192.168.55.13": "k8s-nuc14-03"}[ip]
name = f"capbench-{node[-2:]}-{phase}"
RANGE = "/sys/class/powercap/intel-rapl:0/max_energy_range_uj"
HOT_ABORT_C = 95
def rd(p): return int(subprocess.check_output(["talosctl", "-n", ip, "read", p], text=True).strip())
def energy(): return rd("/sys/class/powercap/intel-rapl:0/energy_uj"), time.time()
script = (f"trap 'kill 0; exit 143' TERM; s=$(date +%s); for i in $(seq 18); do (dd if=/dev/zero bs=1M count={mb} 2>/dev/null | sha256sum >/dev/null) & done; "
          "wait; echo BENCH_WALL_S=$(( $(date +%s) - s ))")
pod = {"apiVersion": "v1", "kind": "Pod",
       "metadata": {"name": name, "namespace": "default", "labels": {"app": "capbench"}},
       "spec": {"nodeSelector": {"kubernetes.io/hostname": node}, "restartPolicy": "Never",
                "activeDeadlineSeconds": 420, "terminationGracePeriodSeconds": 0,
                "securityContext": {"runAsNonRoot": True, "runAsUser": 65534, "seccompProfile": {"type": "RuntimeDefault"}},
                "containers": [{"name": "bench", "image": "docker.io/library/busybox:1.38", "command": ["sh", "-c", script],
                                "resources": {"requests": {"cpu": "100m", "memory": "32Mi"}, "limits": {"memory": "64Mi"}},
                                "securityContext": {"allowPrivilegeEscalation": False, "readOnlyRootFilesystem": True,
                                                    "capabilities": {"drop": ["ALL"]}}}]}}
k = lambda *a, **kw: subprocess.run(["kubectl", *a], text=True, capture_output=True, **kw)
r = k("apply", *(["--dry-run=server"] if dry else []), "-f", "-", input=json.dumps(pod))
if r.returncode: print(f"CAPBENCH_ERROR apply: {r.stderr.strip()}"); sys.exit(2)
if dry: print(f"CAPBENCH_DRY ok: {r.stdout.strip()}"); e1, t1 = energy(); print(f"energy read ok e={e1}"); sys.exit(0)
def pkg_zone():
    for z in range(16):
        r = subprocess.run(["talosctl", "-n", ip, "read", f"/sys/class/thermal/thermal_zone{z}/type"], capture_output=True, text=True)
        if r.returncode: break
        if r.stdout.strip() == "x86_pkg_temp": return f"/sys/class/thermal/thermal_zone{z}/temp"
    raise SystemExit("CAPBENCH_ERROR no x86_pkg_temp thermal zone")
ZONE = pkg_zone()
try:
    for _ in range(180):
        if k("get", "pod", "-n", "default", name, "-o", "jsonpath={.status.phase}").stdout in ("Running", "Succeeded", "Failed"): break
        time.sleep(1)
    else: raise SystemExit("CAPBENCH_ERROR pod never started")
    t0, e1, e2, peak, hot, ph = time.time(), None, None, 0, False, ""
    while time.time() - t0 < 400:
        el = time.time() - t0
        c = rd(ZONE) // 1000; peak = max(peak, c)
        if c >= HOT_ABORT_C:      # watchdog: never cook a node for a benchmark
            hot = True; k("delete", "pod", "-n", "default", name, "--grace-period=0", "--force", "--wait=false"); break
        if e1 is None and el >= 40: e1 = energy()
        if e2 is None and el >= 70: e2 = energy()
        ph = k("get", "pod", "-n", "default", name, "-o", "jsonpath={.status.phase}").stdout
        if ph in ("Succeeded", "Failed"): break
        time.sleep(2)
    log = k("logs", "-n", "default", name).stdout if not hot else ""
    wall = next((l.split("=", 1)[1] for l in log.splitlines() if l.startswith("BENCH_WALL_S=")), "NA")
    sw = "NA"
    if e1 is not None and e2 is None and hot: e2 = energy()   # abort after t+40: still report steady W
    if e1 and e2:
        (a, ta), (b, tb) = e1, e2
        if b < a: b += rd(RANGE)
        sw = f"{(b - a) / 1e6 / (tb - ta):.1f}"
    valid = (not hot) and (tb - ta >= 20 if (e1 and e2) else True) and ph == "Succeeded" and wall != "NA" and int(wall) >= 75 and sw != "NA"
    print(f"CAPBENCH{'' if valid else '_INVALID'} node={node} phase={phase} mb={mb} wall_s={wall} "
          f"steady_w={sw} peak_c={peak} hot_abort={hot} pod_phase={ph}")
finally:
    k("delete", "pod", "-n", "default", name, "--ignore-not-found", "--grace-period=0", "--force", "--wait=false")
```

### capstats.py

```python capstats
#!/usr/bin/env python3
# capstats.py <label> <minutes> [end_unix]  -> one CAPSTATS line per node + JSON in $W/stats-<label>.json
# Window = [end - minutes, end]. Reads Prometheus through the apiserver proxy (kubectl get --raw).
# ABORTS (exit 2) if any metric family returns fewer than 3 nodes: an unscraped series must
# not read as "0 throttles" or "no heat" (docs/sops/verification-contents-not-shape.md).
import json, os, subprocess, sys, time, urllib.parse
label, mins = sys.argv[1], int(sys.argv[2]); end = int(sys.argv[3]) if len(sys.argv) > 3 else int(time.time())
P = "/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?"
w = f"{mins}m"
T = 'max by (instance) (node_thermal_zone_temp{type="x86_pkg_temp"})'   # one series per node even
# across node-exporter pod rolls (a roll splits the raw series by `pod`; un-aggregated, the last
# pod's series silently wins -- measured 2026-10-04: raw max 59 C vs real 102 C on nuc14-02)
Q = {"temp_avg": f"avg_over_time(({T})[{w}:30s])",
     "temp_p95": f"quantile_over_time(0.95, ({T})[{w}:30s])",
     "temp_max": f"max_over_time(({T})[{w}:30s])",
     "min_ge100": f"sum_over_time(({T} >= bool 100)[{w}:1m])",
     "throttles": f'sum by (instance) (increase(node_cpu_package_throttles_total[{w}]))',
     "rapl_avg_w": f'sum by (instance) (rate(node_rapl_package_joules_total[{w}]))',
     "rapl_max1m_w": f'max_over_time((sum by (instance) (rate(node_rapl_package_joules_total[1m])))[{w}:30s])',
     "nvme_max": f'max by (instance) (max_over_time(node_hwmon_temp_celsius{{chip=~"nvme_.+",sensor="temp1"}}[{w}]))'}
# Sample coverage: an under-covered window (series younger than the window, scrape gap) under-reads
# averages/increases WITHOUT any error (measured 2026-10-04: rapl_avg_w over 60m read 5 W against
# 16-19 W real while the RAPL series was 20 min old). Require >= 90 % of the 30 s steps per node.
Q["cov_temp"] = f"count_over_time(({T})[{w}:30s]) / {mins * 2}"
Q["cov_rapl"] = f"count_over_time((sum by (instance) (node_rapl_package_joules_total))[{w}:30s]) / {mins * 2}"
out, short = {}, []
for k, q in Q.items():
    raw = subprocess.run(["kubectl", "get", "--raw", P + urllib.parse.urlencode({"query": q, "time": end})],
                         capture_output=True, text=True)
    res = json.loads(raw.stdout)["data"]["result"] if raw.returncode == 0 else []
    if len(res) != 3: short.append(f"{k}:{len(res)}")
    for r in res: out.setdefault(r["metric"]["instance"].split(":")[0], {})[k] = round(float(r["value"][1]), 2)
for n in sorted(out): print(f"CAPSTATS {label} {n} " + " ".join(f"{k}={v}" for k, v in sorted(out[n].items())))
wd = os.environ.get("W", ".")
json.dump({"label": label, "end": end, "minutes": mins, "nodes": out}, open(f"{wd}/stats-{label}.json", "w"), indent=1)
lowcov = [f"{n}:{k}={v}" for n, d in out.items() for k, v in d.items() if k.startswith("cov_") and v < 0.9]
if lowcov: print(f"CAPSTATS_ABORT sample coverage < 0.9 (window older than the series or a scrape gap): {lowcov}"); sys.exit(3)
if short: print(f"CAPSTATS_ABORT families without exactly 3 nodes: {short}"); sys.exit(2)
```

