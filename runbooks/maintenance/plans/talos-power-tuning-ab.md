---
plan_id: talos-power-tuning-ab
component: talos
pr: null                              # no Renovate PR: operator-requested follow-up to talos-sysfs-power-caps (chat 2026-10-05)
kind: infra
current: "SysfsConfig c2c155b8 on all 3 nodes: RAPL PL1 35 W / PL2 55 W (PL1 tau BIOS 27983872 us), EPP balance_power (179) on cpu0-17, iGPU gt0 1500 MHz"
target: "the A/B winner of {A0 current, B = EPP 64, C = EPP 96, D = EPP 96 + PL2 45 W + PL1 tau 10 s}, committed to the global SysfsConfig patch and applied to all 3 nodes (PL1 35 W and iGPU 1500 MHz unchanged in every variant)"
update_type: refactor
risk: medium                          # Not high: no reboot (every variant dry-run-proven 2026-10-05: "Applied configuration
                                      # without a reboot"), no etcd/apiserver change, every step is a live sysfs write the
                                      # pre-rendered A0 config undoes in seconds. Not low: up to 9 machine-config applies on
                                      # control-plane nodes in one evening, and the winner changes CPU behaviour for every workload.
est_duration_min: 310                 # PER EVENING (max of the two; review-2: evening 1 ~308) - the plan runs as TWO attended NOW runs (§6, reviewer 2026-10-05: one evening
                                      # was ~450 min with realistic run times, too close to the 480 ceiling). Run time ~32 min
                                      # (A0/C/D; B faster) incl. 300 s settle + 2-node packing; cooldowns <= 5 min each.
                                      # Evening 1 (A0 + B + C + back to A0): Step 0 15, pre 10, A0 32, 2 switches x 17,
                                      # 6 runs x 32 + cooldowns 15, return to A0 10, gate/settle margins -> ~308.
                                      # Evening 2 (A0 + D + decision + roll): Step 0 15, pre 10, A0 32, switch 17, 3 runs 96 +
                                      # cooldowns 10, decision 10, final roll + 02 watch 45, slack 10 -> ~245.
needs_reboot: false
exclusive: true                       # review-2 B1: nothing may share either evening's slot. ci-runner-exclude-node02 must be
                                      # EXECUTED beforehand (run-now checks ALL premises at preflight, so it can never run
                                      # "first in the same run": node02-excluded-from-ci would refuse the whole run).
touches:
  namespaces: [ci-runner, monitoring]  # ci-runner: 10 measurement CI runs (sims 4 + e2e 3 each). monitoring: read-only
                                       # (capstats, NodeCPUPackagePowerAtCap check); no monitoring object is changed.
  resources:
    - talos-machineconfig/k8s-nuc14-01             # variant applies (B, C, D) + final, --mode=no-reboot
    - talos-machineconfig/k8s-nuc14-03             # variant applies (B, C, D) + final
    - talos-machineconfig/k8s-nuc14-02             # final roll only
    - "sysfs: /sys/devices/system/cpu/cpu{0..17}/cpufreq/energy_performance_preference (01,03 in the A/B; all 3 at the end)"
    - "sysfs: /sys/class/powercap/intel-rapl:0/constraint_1_power_limit_uw (variant D / winner D)"
    - "sysfs: /sys/class/powercap/intel-rapl:0/constraint_0_time_window_us (variant D / winner D; NEW key)"
    - file/kubernetes/bootstrap/talos/patches/global/machine-sysfs-power.yaml   # final commit, only if the winner is B/C/D
    - "pod/tnb-sims-d3ae92f-*, pod/tnb-e2e-gpu-d3ae92f-* (ci-runner, transient, Job TTL 600 s)"
  shared: [talos-machineconfig, node-power-thermal, igpu-i915, monitoring, ci-runner-thermal-gate]
                                      # node-power-thermal: every pod on 01/03 runs under each variant for ~100 min.
                                      # igpu-i915: e2e shards use the iGPU on 01/03 (gt0 cap unchanged at 1500).
                                      # monitoring: every gate reads Prometheus (capstats) - the instrument.
                                      # ci-runner-thermal-gate: the A/B runs set GATE_SECOND_POD_NODES= and GATE_MAX_CPU_PER_NODE=1
                                      # for its own triggers (one shard per node), so NO other CI may run meanwhile.
depends_on:                           # talos-sysfs-power-caps is NOT here on purpose (2026-10-05): run-now.py preflight refuses
                                      # an unmet depends_on while that plan sits in awaiting-soak, i.e. even AFTER its soak was
                                      # captured, and a retired (deleted) plan becomes a DEAD-REF. The real gate is the premise
                                      # soak-24h-recorded (the soak JSON exists only after CAPSTATS_OK); the ordering is in
                                      # conflicts_with below.
  - ci-runner-exclude-node02          # the A/B runs on 01/03 only; the exclusion keeps the gate from placing a shard on 02
conflicts_with:
  - talos-sysfs-power-caps            # never the same run: its soak (3.10 evidence) measures the config this plan changes
  - talos-linux-1.14.2                # rolling reboot; a reboot mid-A/B voids the variant and re-reads the card index
  - multus-macvlan-foundation         # also talosctl apply-config on the same nodes
  - kube-prometheus-stack-91.9.0      # every gate reads Prometheus; a kps restart punches a hole in a run's capstats
  - immich-machine-learning-3.2.4     # iGPU + CPU consumer on nuc14-03: its roll during a run changes that run's load
  - jellyfin-12.1                     # iGPU consumer on nuc14-01 (same reason)
  - jellyfin-config-rwo-migration     # iGPU consumer on nuc14-01 (same reason)
  # - mariadb-28.1.1  # RESOLVED 2026-10-06: executed green now:2026-10-05, plan retired in 5af1e51f
  - nextcloud-fleet-35.0.1            # reciprocity (review-3): it names this plan (backup-restore stacking)
  - k8s-1.36.5                        # reciprocity (review-3): it names this plan
  - helm-drift-detection              # its P2 rolls intel-gpu-plugin (re-registers gpu.intel.com/i915 on every node)
security_ref: null
capability_change: true               # TRUE: the winner changes the CPU energy/performance bias (and for D the burst budget) of
                                      # every workload on every node: user-visible throughput and heat. Never unattended.
rollback_class: backup-restore        # rollback = re-apply the PRE-RENDERED A0 config (= HEAD at plan start), proven byte-equal
                                      # to the live config by an EMPTY dry-run diff before the first forward apply. Flux does not
                                      # reconcile kubernetes/bootstrap/talos/, so a git revert alone changes nothing on the nodes.
restore_proof: "§3.2: the A0 config ($W/r-A0, rendered from HEAD) dry-run against every node prints 'Applied configuration without a reboot' and ab-diffgate.py <dry> A0 A0 prints GATE_PASS (empty diff = the live config IS A0); §5 then re-reads every key (ab-readback.py <ip> A0 --status -> GATE_PASS, incl. the PL1 tau back at 27983872 after D)."
backup_gate: "per node, before its FIRST forward apply: (1) $W/r-A0/kubernetes-k8s-nuc14-0N.yaml exists and validates for metal mode, (2) its dry-run against the node gives an empty diff (ab-diffgate.py ... A0 A0 -> GATE_PASS), (3) ab-readback.py <ip> A0 --status -> GATE_PASS (the live values are the values the rollback restores), (4) $W/live-<ip>.yaml break-glass copy written and non-empty"
finding_refs:
  - F-6c7843e4                        # "decide PL2 40-45 W and/or shorter PL1 tau via a reviewed plan amendment ... CI +35 % from
                                      # EPP balance_power": this plan is that amendment, measured
review: ready-for-go@2026-10-05     # 4th pass @5a27a9b8 (0 blocking)
status: vetted
window: null                          # PROPOSED: two on-demand NOW runs, 2026-10-06 and 2026-10-07, each 18:30 Europe/Berlin
                                      # (16:30Z); evening 1 ends ~23:20, evening 2 ~22:30 Berlin; hard stop 01:45, everything done
                                      # by 02:45 (nightly 03:30). Stamped only by run-now.py stamp inside each run.
premises:
  - id: nodes-on-talos-1.14
    why: "Every render and dry-run below was measured on v1.14.1 (kernel 6.18). Another minor invalidates the renders and the no-reboot verdict."
    run: kubectl get nodes -o jsonpath='{.items[*].status.nodeInfo.osImage}'
    expect_matches: '^Talos \(v1\.14\.[0-9]+\) Talos \(v1\.14\.[0-9]+\) Talos \(v1\.14\.[0-9]+\)$'
  - id: soak-24h-recorded
    why: "Ordering gate vs talos-sysfs-power-caps (conflicts_with, deliberately not depends_on; see depends_on comment): its 24 h soak JSON exists only after a CAPSTATS_OK. Read from THIS plan's $W: the predecessor's close-out (Copy-out step, 3c8833b8) copies 7 secret-free files here BEFORE it wipes its own scratch dir tonight. Missing = soak not taken, or not copied: STOP. A premise cannot read 'copy OR source' (grep exits 2 on any missing file), so the copy is the contract."
    run: "grep -c '\"label\": \"soak-24h\"' /private/tmp/powerab-talos-power-tuning-ab/stats-soak-24h.json"
    expect_exact: "1"
  - id: baseline-files-present
    why: "The paired BEFORE/AFTER comparison needs the 2026-10-04 shard records, logs and stats, copied from the predecessor's scratch dir into $W by its close-out (same 7-file Copy-out). Owned steps: talos-sysfs-power-caps §5 Copy-out + reminders talos-sysfs-power-caps-soak-3.10 / -scratch-wipe + F-6c7843e4 item (5), all updated 2026-10-05."
    run: "grep -c '' /private/tmp/powerab-talos-power-tuning-ab/shards-before.json /private/tmp/powerab-talos-power-tuning-ab/shards-after.json /private/tmp/powerab-talos-power-tuning-ab/ci-before.log /private/tmp/powerab-talos-power-tuning-ab/ci-after.log /private/tmp/powerab-talos-power-tuning-ab/stats-before-ci.json /private/tmp/powerab-talos-power-tuning-ab/stats-after-ci.json | wc -l | tr -d ' '"
    expect_exact: "6"
  - id: node02-excluded-from-ci
    why: "depends_on ci-runner-exclude-node02 (must be EXECUTED before the run; preflight checks this premise): without the knob the gate can pin an A/B shard on nuc14-02, and that run is INVALID (ab-summary.py drops runs with a shard on 02)."
    run: "grep '^EXCLUDE_NODES = ' scripts/ninth-banner-admit.py | wc -l | tr -d ' '"
    expect_exact: "1"
  - id: sysfs-patch-committed-shape
    why: "ab-patches.py asserts the c2c155b8 shape (18 balance_power EPP lines, PL2 55 W, no time-window key) and the talos dir must be clean, or the final git commit --only would carry foreign hunks."
    run: "git status --porcelain kubernetes/bootstrap/talos | wc -l | tr -d ' '"
    expect_exact: "0"
  - id: epp-lines-balance-power
    why: "Same shape check, on content: 18 EPP keys at balance_power in the committed global patch."
    run: "grep -c 'energy_performance_preference: \"balance_power\"$' kubernetes/bootstrap/talos/patches/global/machine-sysfs-power.yaml"
    expect_exact: "18"
  - id: meteor-lake-epp-table
    why: "The variant meanings rest on intel_pstate's Meteor Lake table (intel_epp_default, v6.18: INTEL_METEORLAKE_L -> balance_power 179, balance_performance 64, performance 16): family 6 model 170 on all 18 CPUs of all 3 nodes (02 gets the winner too). Another model = another table: B would no longer equal the pre-2026-10-04 EPP and the read-back mapping in ab-readback.py is wrong."
    run: "talosctl --nodes=192.168.55.11 read /proc/cpuinfo | grep -c '^model[[:space:]]*: 170$'"
    expect_exact: "18"
  - id: meteor-lake-epp-table-02
    why: "same as meteor-lake-epp-table, node 02 (talosctl read takes exactly one node; 02 receives the winner in 3.7)"
    run: "talosctl --nodes=192.168.55.12 read /proc/cpuinfo | grep -c '^model[[:space:]]*: 170$'"
    expect_exact: "18"
  - id: meteor-lake-epp-table-03
    why: "same as meteor-lake-epp-table, node 03"
    run: "talosctl --nodes=192.168.55.13 read /proc/cpuinfo | grep -c '^model[[:space:]]*: 170$'"
    expect_exact: "18"
  - id: hwp-epp-numeric-write-allowed
    why: "store_energy_performance_preference accepts a raw 0-255 EPP only with X86_FEATURE_HWP_EPP (else returns the match_string error): the hwp_epp flag on every CPU of all 3 nodes."
    run: "talosctl --nodes=192.168.55.11 read /proc/cpuinfo | grep -c 'hwp_epp'"
    expect_exact: "18"
  - id: hwp-epp-numeric-write-allowed-02
    why: "same as hwp-epp-numeric-write-allowed, node 02"
    run: "talosctl --nodes=192.168.55.12 read /proc/cpuinfo | grep -c 'hwp_epp'"
    expect_exact: "18"
  - id: hwp-epp-numeric-write-allowed-03
    why: "same as hwp-epp-numeric-write-allowed, node 03"
    run: "talosctl --nodes=192.168.55.13 read /proc/cpuinfo | grep -c 'hwp_epp'"
    expect_exact: "18"
  - id: rapl-not-locked-01
    why: "PL2 and the PL1 time window share MSR_PKG_POWER_LIMIT's lock bit; enabled=1 = not BIOS-locked (rapl_write_pl_data would return EACCES)."
    run: talosctl --nodes=192.168.55.11 read /sys/class/powercap/intel-rapl:0/enabled
    expect_exact: "1"
  - id: rapl-not-locked-03
    why: same as -01, node 03
    run: talosctl --nodes=192.168.55.13 read /sys/class/powercap/intel-rapl:0/enabled
    expect_exact: "1"
  - id: pl1-tau-bios-value-01
    why: "ab-readback.py expects the untouched PL1 window at 27983872 us for A0/B/C (2^14 x 1.75 x 976 us). Another value = BIOS changed: re-plan the D window."
    run: talosctl --nodes=192.168.55.11 read /sys/class/powercap/intel-rapl:0/constraint_0_time_window_us
    expect_exact: "27983872"
  - id: pl1-tau-bios-value-03
    why: same as -01, node 03
    run: talosctl --nodes=192.168.55.13 read /sys/class/powercap/intel-rapl:0/constraint_0_time_window_us
    expect_exact: "27983872"
  - id: igpu-card-index-node03-card1
    why: "ab-readback.py/ab-works.py hard-code card1 on 03, card0 on 01/02 (simpledrm on 03). Re-measured 2026-10-05."
    run: talosctl --nodes=192.168.55.13 read /sys/class/drm/card1/gt/gt0/rps_max_freq_mhz
    expect_exact: "1500"
  - id: runner-image-lockstep
    why: "ninth-banner-test.sh refuses to run a ref whose tests/e2e/runner.json names a different Playwright image than the template (IMAGE MISMATCH, exit 2). The fixed ref d3ae92f ran with this digest on 2026-10-04; a template bump since then breaks every A/B run."
    run: "grep -c 'playwright:v1.63.0-noble@sha256:eff16c30e6f3f4af0a03fa4b706120d5e9b0891c344a27d64559aff5900a4a27' kubernetes/apps/ci-runner/the-ninth-banner-tests/job-template.yaml.tpl"
    expect_exact: "1"
  - id: power-at-cap-alert-31w
    why: "PL1 stays 35 W in every variant, so NodeCPUPackagePowerAtCap keeps its 31 W threshold (90 % of PL1). A different value means someone retuned it: re-check before claiming no retune is needed."
    run: grep -c 'joules_total{job="node-exporter"}.5m.) . 31$' kubernetes/apps/monitoring/kube-prometheus-stack/app/node-thermal-alerts.yaml
    expect_exact: "1"
sops_refs:
  - docs/sops/talos-upgrade.md
  - docs/sops/application-update.md
  - docs/sops/ci-runner.md
  - docs/sops/monitoring.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-10-05"
---

# Talos power tuning A/B: EPP and PL2/tau on nuc14-01/03, winner to all three nodes

## 1. Summary & why held

**What this is.** An amendment to `talos-sysfs-power-caps` (live since 2026-10-04 23:17Z). Its BEFORE/AFTER showed:
package temperature -18..-26 %, nuc14-02 CI throttles 380 -> 0, and package power -34..-50 %. The cost was CI
**~+35 % slower** (sims median 350 -> 478 s, e2e 197 -> 264 s; paired per shard index +36.6 %, recomputed 2026-10-05
by `ab-summary.py` on the 10-04 files). During that AFTER run the package never exceeded ~20 W (1-min max), far below
the 35 W PL1, and gt0 never exceeded 800 MHz, below the 1500 cap. So the RAPL and iGPU caps did not bind. The suspect
is the EPP change `balance_performance -> balance_power`. This plan measures that live on two nodes, picks a winner by
a fixed rule, and rolls it out.

**Variants** (PL1 35 W and gt0 1500 MHz in ALL of them; written as SysfsConfig values):

| variant | PL2 (`constraint_1_power_limit_uw`) | PL1 tau (`constraint_0_time_window_us`) | EPP (cpu0-17) | data |
|---|---|---|---|---|
| E (not run) | 64 W (PL1 = PL2 = 64 W) | BIOS 27 983 872 | balance_performance (64) | REUSED: 2026-10-04 BEFORE (stability priority) |
| **A0** = committed now | 55 W | BIOS 27 983 872 (key absent) | balance_power (179) | 1 control run tonight + the 2026-10-04 AFTER |
| **B** | 55 W | BIOS (key absent) | `"64"` | 3 runs |
| **C** | 55 W | BIOS (key absent) | `"96"` | 3 runs |
| **D** | **45 W** | **`"10000000"`** (reads back 9 994 240) | `"96"` | 3 runs |

**Primary-source facts the plan rests on (each verified 2026-10-05):**
1. *EPP numbers on this CPU.* `drivers/cpufreq/intel_pstate.c` (v6.18) `intel_epp_default[]`:
   `X86_MATCH_VFM(INTEL_METEORLAKE_L, HWP_SET_EPP_VALUES(HWP_EPP_POWERSAVE, 179, 64, 16))` (arguments: powersave,
   balance_power, balance_perf, performance). The nodes report family 6 **model 170** (= 0xAA, METEORLAKE_L) and the
   `hwp_epp` flag on all 18 CPUs (premises). So **B (EPP 64) is exactly the pre-2026-10-04 `balance_performance`**, and
   B isolates the EPP effect under the new caps. C (96) sits between 64 and 179. Caveat
   (`intel_pstate_update_epp_defaults`): when HWP is BIOS-forced and the firmware EPP is <= 0x80, the kernel takes the
   firmware value as `balance_performance` instead. dmesg reads "HWP enabled" (not "by BIOS") on 02/03; 01's boot lines
   have rotated. If 01 were forced, B's read-back on 01 FAILS loudly (gate 4.1), so nothing silent can happen.
2. *Numeric EPP writes are accepted.* `store_energy_performance_preference`: when the string matches no name and
   `boot_cpu_has(X86_FEATURE_HWP_EPP)`, it parses `kstrtouint(buf, 10, &epp)`, rejects `> 255`, and writes the raw
   value (`raw = true`). Active mode (`intel_pstate_driver == &intel_pstate`) applies it directly.
3. *Read-back shows NAMES for table values.* `show_energy_performance_preference` -> `intel_pstate_get_energy_pref_index`
   returns the name when the raw EPP equals a table entry. So after B, `/sys/.../energy_performance_preference` reads
   **`balance_performance`, not `64`**, and after C/D it reads `96`. `ab-readback.py` maps this. A gate comparing the
   sysfs text with the written string would false-FAIL every B apply.
4. *Talos status holds the WRITTEN string.* Talos v1.14.1 `kernel_param_spec.go` `updateKernelParam`:
   `res.TypedSpec().Current = value` (the spec value, no re-read). So `KernelParamStatus` reads `64` while sysfs
   reads `balance_performance`. Every reconcile re-writes every key (no compare), and a key that leaves the config
   is `resetKernelParam`-ed: the captured pre-first-write default is written back live and its status is DESTROYED.
   So D -> any other variant writes the PL1 window back to 27 983 872 without a reboot, and the A0/B/C read-back
   expects NO time-window status.
5. *PL1 window is writable and quantized.* `intel_rapl_common.c` (v6.18): the powercap op `set_time_window_us` ->
   `rapl_write_pl_data(rd, id, PL_TIME_WINDOW, ...)` (lock bit as for PL1/PL2: `enabled=1` on 01/03).
   `rapl_compute_time_window_core` stores `2^Y * (1 + F/4)` time units. The time unit is 976 us here: the live
   27 983 872 = 2^14 x 1.75 x 976 exactly. 10 000 000 us therefore becomes Y=13, F=1 -> **9 994 240 us**.
   `constraint_0` is `long_term` (PL1), `constraint_1` is `short_term` (PL2, window 2 440 us, untouched).
6. *Every variant applies live.* Talhelper renders (scratch, 2026-10-05) give one SysfsConfig document per node with
   21 keys (A0/B/C) or 22 keys (D), and all 12 pass `talosctl validate --mode metal`. A dry-run of each against
   k8s-nuc14-03 answered "Applied configuration without a reboot (skipped in dry-run)". `ab-diffgate.py` passed
   A0->A0 (empty diff: **the repo IS the live config**), A0->B and A0->C (18-/18+), and A0->D (19-/20+). It FAILED on
   every negative control: wrong target variant, wrong value, injected `+machine:` line, A0->A0 on a real diff.
7. *A per-node patch cannot override a global SysfsConfig key* (talhelper 3.1.17, scratch render 2026-10-05: EPP keys
   added to `k8s-nuc14-02-sysfs-igpu.yaml` were overridden by the global patch; 02 still rendered `64`). So the winner
   goes to all three nodes. A per-node exception for 02 would need the EPP keys moved out of the global patch (§6).

**Why it is a plan.** Up to 9 machine-config applies on control-plane nodes, and a behaviour change for every
workload (`capability_change: true`). The operator's apply split from the predecessor holds: **the coordinator runs
every `talosctl apply-config` on the operator's OK; the agent does everything else.**

**Decision rule (fixed before any data; implemented in `ab-summary.py`, tested on the 10-04 data):**
1. A variant is ELIGIBLE only if it has >= 2 VALID runs (A0: >= 1, the control) and on BOTH 01 and 03, over all its runs: package `temp_p95` <= 75 °C, `temp_max` < 95 °C,
   0 minutes >= 100 °C, and package throttles <= 5 in total. A0 is filtered like the others. If nothing is eligible the verdict is
   `AB_NO_WINNER` and A0 stays anyway (it is the committed config).
2. Among eligible variants, the lowest paired CI slowdown vs BEFORE (geometric mean of per-shard-index time ratios,
   sims + e2e, all runs) wins. **Stability tie-break:** every variant within 3 percentage points of the best is a tie,
   and the tie goes to the lower max p95, then the lower J/shard. So A0 keeps its place unless a variant is clearly
   faster.
3. If **B is still > 15 % slower than BEFORE**, then EPP is not the whole story and the 35 W PL1 / 1500 MHz cap binds.
   Record `PL1_BINDING_NOTE` and propose **PL1 40 W as the next test, NOT in this plan**. Caveat: the BEFORE baseline
   ran sims shard 0 on the throttling nuc14-02, and one e2e shard has no finish time. Every "vs BEFORE" ratio carries that
   skew. The ranking BETWEEN variants is unaffected (same baseline), but treat the 15 % line as approximate.
4. No eligible variant -> `AB_NO_WINNER`: A0 stays (the decision is still recorded, 3.7).
5. **Ranking is per evening (B4).** Each variant is compared with ITS OWN evening's A0 control, paired by shard index:
   B and C against A0-1, D against A0-2. The summary prints the paired A0-2 vs A0-1 drift. If that drift is more than 3
   points, or A0-2 is missing, the cross-evening (B/C vs D) ranking is unreliable: it prints `CROSS_EVENING_UNRELIABLE` and
   `AB_NEEDS_OPERATOR provisional ...` (exit 4), and **the operator decides** from the table. Tested 2026-10-05 on
   synthetic two-evening data: 0 % drift -> `AB_WINNER=D`; +6 % drift -> `AB_NEEDS_OPERATOR`.
6. **The rule ignores nuc14-02** (no A/B data there by design). 02 is covered by the 3.7.5 20-min watch, its per-node
   rollback, and the open F-6c7843e4 (24 h check before closing).
**Expectation to state in the GO text:** B will very likely be DISQUALIFIED. The 10-04 BEFORE run (same EPP, 64 W)
already read 03 p95 77.35 °C (> 75), and B differs only by the 35/55 W caps, which CI never reached. The synthetic test
of the rule disqualifies it on exactly that number. B is still run: it is the only clean measure of the EPP share.
Per-core-type EPP (P-cores cpu0-7 = 4 x 2 HT at 4.5 GHz max, E-cores cpu8-15 at 3.6 GHz, LP-E cpu16-17 at 2.5 GHz,
measured via `cpuinfo_max_freq`) was evaluated and NOT included. Each extra variant costs ~100 min tonight, and sims
(single-threaded) runs on a P-core under ITMT anyway. If the winner is B or C, "EPP 64 on cpu0-7 only, 179 on cpu8-17"
is the obvious next test.

## 2. Pre-checks (in the NOW run, before any apply; mutation-free)

From the repo root on the Mac mini, as `mu`, mise activated, talosctl v1.14.x client. **`W` is a FIXED mode-700 dir
outside the repo.** It holds rendered machine configs (secrets): never `cat` a render or print a dry-run diff. Shell
variables do not survive between agent Bash calls: every block starts with the guard line.
```bash
cd /Users/mu/code/cberg-home-nextgen
umask 077; export W=/private/tmp/powerab-talos-power-tuning-ab; mkdir -p "$W"; chmod 700 "$W"
export SOPS_AGE_KEY_FILE=$PWD/age.key
for b in ab-patches ab-diffgate ab-readback ab-works ab-shards ab-summary capstats; do
  awk -v b="$b" '$0=="```python " b {f=1;next} /^```$/{f=0} f' runbooks/maintenance/plans/talos-power-tuning-ab.md > "$W/$b.py"
  python3 -c "import ast,sys; ast.parse(open(sys.argv[1]).read())" "$W/$b.py" && test -s "$W/$b.py" || echo "EXTRACT FAILED $b"
done
awk '$0=="```bash ab-run" {f=1;next} /^```$/{f=0} f' runbooks/maintenance/plans/talos-power-tuning-ab.md > "$W/ab-run.sh"
bash -n "$W/ab-run.sh" && test -s "$W/ab-run.sh" && chmod 700 "$W/ab-run.sh" || echo "EXTRACT FAILED ab-run"
echo d3ae92f > "$W/ci-ref"
```
2.1 **Premises**: `.venv/bin/python3 runbooks/plan-premises.py talos-power-tuning-ab --require-premises` -> all PASS
(`soak-24h-recorded` fails until the predecessor's soak ran: STOP, too early).

2.2 **Cluster health**: 3 nodes `Ready`; `mise exec -- talosctl -n 192.168.55.11,192.168.55.12,192.168.55.13 etcd status`
-> 3 members, no learner, no ERRORS. **Record the leader and the RAFT TERM** (2026-10-05: `187ea782` = nuc14-01, term 83):
`mise exec -- talosctl -n 192.168.55.11 etcd status | awk 'NR==2{print $8, $10}' > "$W/etcd-before.txt"` (LEADER = token 8, RAFT TERM = token 10:
DB SIZE `462 MB` and IN USE `141 MB (30.54%)` split into 2 and 3 tokens; measured live 2026-10-05 -> `187ea782cbe2f8d1 83`.
Review-3 caught the earlier `$5, $9`, which read IN USE and RAFT INDEX). Per variant, apply the
non-leader first. `flux get kustomizations -A | awk 'NR==1 || $5 != "True"'` -> header only.
`mise exec -- talosctl -n <ip> get machineconfig` on 01/03 lists only `v1alpha1` (+ the v1.14 `persistent` copy with
the SAME hash, which is not a staged config; predecessor execution record).

2.3 **Baselines (no secrets; already in `$W`, premises).** The predecessor's close-out copies the 7 files here as soon as
its soak printed `CAPSTATS_OK` (`talos-sysfs-power-caps` §5 Copy-out, 3c8833b8). This step only renames them to the run
labels `ab-summary.py` reads:
```bash
export W=/private/tmp/powerab-talos-power-tuning-ab; test -d "$W" || { echo NO_W; exit 1; }
cp -p "$W/shards-before.json" "$W/shards-E.json"; cp -p "$W/ci-before.log" "$W/run-E.log"; cp -p "$W/stats-before-ci.json" "$W/stats-E.json"
cp -p "$W/shards-after.json" "$W/shards-A1004.json"; cp -p "$W/ci-after.log" "$W/run-A1004.log"; cp -p "$W/stats-after-ci.json" "$W/stats-A1004.json"
ls "$W" | grep -cE '^(shards|run|stats)-(E|A1004)\.(json|log)$'    # 6
git hash-object scripts/ninth-banner-admit.py > "$W/gate-hash"; cat "$W/gate-hash"     # ab-run.sh refuses a run if the gate changed
```
The gate hash is re-taken on evening 2 only if `git log -1 -- scripts/ninth-banner-admit.py` shows no new commit since
evening 1. If there is one, read it first: a changed gate between evenings changes the experiment.

2.4 **No CI in flight and none planned 18:30-02:45 Berlin**: `scripts/ninth-banner-admit.py --status` -> `gated (queued)
pods: 0` and `ci-cpu 0/6` on every node; `kubectl get jobs -n ci-runner` shows no active Job. Tell the ci-runner owner
(game sessions) that CI is reserved for the A/B tonight. Their runs would share the gate and the nodes. The A/B runs
override `GATE_SECOND_POD_NODES`/`GATE_MAX_CPU_PER_NODE` for their own ticks.

**Step 0 first.** Every NOW run starts with the safe-update batch (Step 0, `docs/sops/auto-update.md`). It can roll
Prometheus or iGPU pods. Take 2.5 only after Step 0 has settled, and record which pods it rolled.

2.5 **Snapshots** (`backup_gate` part 4 + works baseline; `ab-works.py --snap` is RE-TAKEN right before every apply, 3.4c):
```bash
export W=/private/tmp/powerab-talos-power-tuning-ab; test -d "$W" || { echo NO_W; exit 1; }
for ip in 192.168.55.11 192.168.55.12 192.168.55.13; do
  mise exec -- talosctl -n $ip get machineconfig v1alpha1 -o yaml | python3 -c 'import sys,yaml; print(list(yaml.safe_load_all(sys.stdin))[0]["spec"], end="")' > "$W/live-$ip.yaml"
  test -s "$W/live-$ip.yaml" && echo "backup $ip ok"
  mise exec -- python3 "$W/ab-works.py" $ip --snap          # WORKS_SNAP_OK ... gpu_pods>=1
  mise exec -- python3 "$W/ab-readback.py" $ip A0 --status | tail -1   # GATE_PASS ... variant=A0 keys=21 mismatches=0
done
kubectl get pods -A -o jsonpath='{range .items[*]}{.metadata.namespace}/{.metadata.name} {range .status.containerStatuses[*]}{.restartCount} {end}{"\n"}{end}' > "$W/restarts-before.txt"; wc -l < "$W/restarts-before.txt"   # > 100
```
`ab-readback.py` on 02 also PASSES (02 has the same A0 config). The gate was measured to fail both ways on 2026-10-05:
A0 -> `GATE_PASS ... mismatches=0` on 01 and 03, B -> `GATE_FAIL ... mismatches=36` (18 sysfs + 18 status).
`ab-works.py` was measured 2026-10-05: `CONFIGWORKS_PASS` on 01 (3 iGPU pods) and 03 (1). It FAILED on an injected
bootID change and an injected restart-count change.

## 3. Steps

**Apply convention for every `talosctl apply-config` below:** the agent prepares the exact command and gate, and asks
the operator. The **coordinator** runs it on the operator's OK (one OK may cover both nodes of a variant switch;
the operator decides). Then the agent runs the gates. Any gate failure -> §5 for THAT node, then stop that variant.

### 3.1 Render A0, B, C, D (from HEAD, into `$W`, never into `clusterconfig/`) - parallel to 3.3
```bash
export W=/private/tmp/powerab-talos-power-tuning-ab; test -d "$W" || { echo NO_W; exit 1; }
cd /Users/mu/code/cberg-home-nextgen; export SOPS_AGE_KEY_FILE=$PWD/age.key
for v in A0 B C D; do
  rsync -a --exclude clusterconfig kubernetes/bootstrap/talos/ "$W/src-$v/"
  mise exec -- python3 "$W/ab-patches.py" "$W/src-$v" $v                          # AB_PATCHES_OK variant=$v
  (cd "$W/src-$v" && mise exec -- talhelper genconfig -o "$W/r-$v") 2>&1 | grep -v -E '^generated|talosVersion|might not be compatible|issues with your Talhelper'
done
for v in A0 B C D; do for n in 01 02 03; do
  mise exec -- talosctl validate --config "$W/r-$v/kubernetes-k8s-nuc14-$n.yaml" --mode metal 2>&1 | tail -1
  python3 - "$W/r-$v/kubernetes-k8s-nuc14-$n.yaml" $v <<'PY'
import sys, yaml
s = [d for d in yaml.safe_load_all(open(sys.argv[1])) if d and d.get("kind") == "SysfsConfig"]
p = s[0]["params"] if s else {}
print(sys.argv[2], sys.argv[1][-8:-5], "docs", len(s), "keys", len(p), sorted(set(p.values())))
PY
done; done
```
PASS (measured on the scratch render 2026-10-05) = 12x `is valid for metal mode` and per variant (each node):
`A0 docs 1 keys 21 ['1500','35000000','55000000','balance_power']`, `B ... keys 21 [...,'64']`, `C ... keys 21 [...,'96']`,
`D docs 1 keys 22 ['10000000','1500','35000000','45000000','96']`. The talhelper `talosVersion v1.14.1 might not be
compatible` warning is expected (talhelper 3.1.17). Anything else -> STOP.

### 3.2 A0 dry-run = the rollback proof (restore_proof / backup_gate 1-3)
```bash
export W=/private/tmp/powerab-talos-power-tuning-ab; test -d "$W" || { echo NO_W; exit 1; }
for n in 1 2 3; do ip=192.168.55.1$n
  mise exec -- talosctl -n $ip apply-config --dry-run --mode=no-reboot -f "$W/r-A0/kubernetes-k8s-nuc14-0$n.yaml" > "$W/dry-A0-$n.txt" 2>&1
  echo "node0$n rc=$? $(sed -n 2p "$W/dry-A0-$n.txt")"; mise exec -- python3 "$W/ab-diffgate.py" "$W/dry-A0-$n.txt" A0 A0
done
```
PASS = 3x `rc=0 Applied configuration without a reboot (skipped in dry-run).` + `GATE_PASS from=A0 to=A0 (expect no
diff)`. Measured on 03 2026-10-05: PASS. A diff here means the live config is not the repo -> STOP (drift; the rollback
target would be wrong).

### 3.3 A0 control run (current config; no apply) - start first, it overlaps 3.1/3.2
Idle reference, then the run (`run_in_background: true`; wait with a Monitor until-loop on
`grep -q '^SHARDS_DONE' "$W/shards-A0-1.out"`, never a foreground sleep):
```bash
export W=/private/tmp/powerab-talos-power-tuning-ab; test -d "$W" || { echo NO_W; exit 1; }
"$W/ab-run.sh" A0-1
```
After it: stats for the run window and for the 5 min before it (marginal energy):
```bash
export W=/private/tmp/powerab-talos-power-tuning-ab; test -d "$W" || { echo NO_W; exit 1; }
L=A0-1; S0=$(cat "$W/run-$L.start"); S1=$(cat "$W/run-$L.end"); M=$(( (S1 - S0) / 60 + 1 ))
mise exec -- python3 "$W/capstats.py" $L $M "$W" $S1; echo "rc=$?"
mise exec -- python3 "$W/capstats.py" idle-$L 5 "$W" $S0; echo "rc=$?"
```
PASS = `rc=0` + `CAPSTATS_OK` twice. A `CAPSTATS_ABORT` is a failed instrument: fix it and re-run capstats (the data
is in Prometheus), never skip it. The run itself is valid when `ab-summary.py` lists it without `INVALID RUN`: >= 7
finished shards and none on nuc14-02. Shard PASS/FAIL does not matter (sims shard 4 fails at this ref in every
variant; e2e shard 2's animation assertion is timing-sensitive). Only the run times matter.

### 3.4 Per variant V = B, then C, then D (fixed order: the variant closest to BEFORE first)
`P` = the variant the nodes hold now (A0 before B, B before C, C before D).

**a) Dry-run gates P -> V on 03 and 01** (mutation-free):
```bash
export W=/private/tmp/powerab-talos-power-tuning-ab; test -d "$W" || { echo NO_W; exit 1; }
P=A0; V=B                                   # set per switch
for n in 3 1; do ip=192.168.55.1$n
  mise exec -- talosctl -n $ip apply-config --dry-run --mode=no-reboot -f "$W/r-$V/kubernetes-k8s-nuc14-0$n.yaml" > "$W/dry-$V-$n.txt" 2>&1
  echo "node0$n rc=$? $(sed -n 2p "$W/dry-$V-$n.txt")"; mise exec -- python3 "$W/ab-diffgate.py" "$W/dry-$V-$n.txt" $P $V
done
```
PASS = `rc=0`, `Applied configuration without a reboot`, and `GATE_PASS from=P to=V` with the expected counts.
A0->B / B->C: `plus=18/18 minus=18/18`. C->D: `plus=2/2 minus=1/1` (PL2 changed, tau added; EPP 96 unchanged).
`non_sysfs_changed_lines=0` in every case. A STOP here is never overridden in-window (predecessor rule): skip the
variant and record the counts.

**b) Quiet node:** the previous run has `SHARDS_DONE`, `scripts/ninth-banner-admit.py --status` shows 0 CI pods on 01/03.

**c) Apply (coordinator, operator OK) - 03 first, then 01 (leader last); gates after EACH node:**
```bash
export W=/private/tmp/powerab-talos-power-tuning-ab; test -d "$W" || { echo NO_W; exit 1; }
V=B; ip=192.168.55.13; n=3                  # then ip=192.168.55.11; n=1
mise exec -- python3 "$W/ab-works.py" $ip --snap    # fresh baseline: a Flux roll since 18:30 must not read as "pod gone"
mise exec -- talosctl -n $ip apply-config --mode=no-reboot -f "$W/r-$V/kubernetes-k8s-nuc14-0$n.yaml"     # coordinator
python3 -c "import time; time.sleep(10)"
mise exec -- python3 "$W/ab-readback.py" $ip $V --status | tail -3     # GATE_PASS node=... variant=V keys=21|22 mismatches=0
mise exec -- python3 "$W/ab-works.py" $ip --check | tail -3            # CONFIGWORKS_PASS
```
Both PASS -> next node. Either FAIL -> §5 for that node (A0), stop this variant, and record why.

**d) Settle:** Monitor until-loop until 5 min after the second apply AND `scripts/ninth-banner-admit.py --status` shows
2-min avg < 65 °C on 01 and 03. Then the idle window before run 1 reflects V.

**e) Three runs V-1, V-2, V-3** (`ab-run.sh` refuses with `GATE_CHANGED` if `scripts/ninth-banner-admit.py` no longer
matches `$W/gate-hash` from 2.3. Dry-tested: a mismatched hash exits 2 before creating any run file; (`ab-shards.py` keeps polling up to 180 s after `SUITES_DONE` until every pod of the
run's Jobs has `finishedAt`, else it prints `SHARDS_UNFINISHED`. That fixes the 10-04 race, where the BEFORE run lost
its last pod's finish time),, each exactly as 3.3 (`"$W/ab-run.sh" $V-1` in the background, Monitor on
`^SHARDS_DONE`, then the two `capstats.py` calls with `L=$V-1`). Before each next run: Monitor until both nodes'
2-min avg < 65 °C (max 5 min). Then start it anyway and note "warm start".
**In-run abort (disqualifies V, ends its runs, go to the next variant):** after any run, its `stats-$V-k.json` shows on
01 or 03 `temp_max >= 95` or `min_ge100 > 0`, or `CAPSTATS ... throttles` > 5 in one run. Note it, and go to 3.4 for the
next variant (its dry-run starts from P = V; that path is gated like any other). If the abort is on D (last), go
to 3.5.

### 3.5 Decision
```bash
export W=/private/tmp/powerab-talos-power-tuning-ab; test -d "$W" || { echo NO_W; exit 1; }
mise exec -- python3 "$W/ab-summary.py" "$W" | tee "$W/summary.txt"
```
It prints the evening drift (A0-2 vs A0-1, paired), each A0 vs the 10-04 AFTER, any `INVALID RUN` (< 7 finished
shards, a shard on 02, or a FOREIGN CI pod on 01/03 overlapping the run window, B3), the per-variant table, any `DISQUALIFIED`, the
`PL1_BINDING_NOTE`, and the verdict `AB_WINNER=<v> ...` or `AB_NO_WINNER` (rc 3). Fill §4.B from it. **The operator
confirms the winner** before 3.6. That is the third touchpoint, and it can share the OK with the final applies.

### 3.6 Time box (decide BEFORE starting a variant)
- Each evening: start a variant's runs only if all 3 fit before 01:00 Berlin, else run 2 (`ab-summary.py` counts VALID
  runs and DISQUALIFIES a B/C/D variant with < 2; tested 2026-10-05: C with 1 valid run -> `DISQUALIFIED C: 1 valid run(s) < 2`).
  A variant whose runs come out INVALID (< 7 finished shards, a shard on 02) gets a replacement run if time allows.
- **01:45 Berlin = hard stop for the final roll.** If 3.7 has not started, apply A0 to 03 and 01 (§5, dry-run first:
  P -> A0 must PASS) and defer the roll to a later on-demand run. The decision stays valid for 7 days. Everything
  must be done by 02:45 (nightly at 03:30).

**End of evening 1:** after C's runs, apply A0 to 03 and 01 per §5 (`ab-works.py <ip> --snap` immediately before each
apply; dry-run `C A0` must PASS; gates `ab-readback.py <ip> A0 --status` + `ab-works.py --check`). Evening 2 starts from A0
with a fresh control run `A0-2`. **Suggested: the operator pre-grants this return-to-A0 apply together with OK #2 (C)**,
so evening 1 can close without a late extra touchpoint.

**Plan status between the evenings (B6):** evening 1 leaves the plan status UNCHANGED (still the vetted/awaiting-go state
it ran under; never `executed`). The window agent records the evening in `window_runs` as `partial`, with notes: "A0-1,
B x3, C x3 measured; 01/03 back on A0; evening 2 owed". Evening 2 needs a FRESH operator GO, scoped `now:2026-10-07`
(`run-now.py stamp` writes it; the 10-06 stamp is not reused). **When evening 1 closes, the window agent resolves or
consumes the 10-06 `approve` decision row** (`home-operation resolve --issue talos-power-tuning-ab ...` / decision
consumed). `run-now.py approval_verdict` accepts an approve for `now:<yesterday>` (age 0..1), so a pending evening-1
approval would otherwise pass evening 2's preflight without the fresh GO.
**Invalid A0 control:** ab-run.sh refuses a reused label, so a replacement control run is `A0-1b` (or `A0-2b`).
`ab-summary.py` uses the first VALID A0 label per evening as that evening's reference (tested: `A0-1b` stands in for
`A0-1`). A variant normalised against the OTHER evening's A0 (its own is missing) always prints
`CROSS_EVENING_UNRELIABLE` -> `AB_NEEDS_OPERATOR` (exit 4; tested with A0-1 + D removed).

### 3.7 Final roll
**Winner A0 or AB_NO_WINNER:** dry-run P -> A0 on 03 and 01 (`ab-diffgate.py ... P A0`), `ab-works.py <ip> --snap`
immediately before each apply, apply A0 (coordinator) to 03
then 01, gates `ab-readback.py <ip> A0 --status` + `ab-works.py <ip> --check`. Then RECORD the decision in git, so
dependants (`ci-gate-primary-control-rework` premise `power-tuning-decided`) have something to key on:
`mise exec -- python3 "$W/ab-patches.py" kubernetes/bootstrap/talos A0 --record` (one comment line, render-neutral:
dry-tested 2026-10-05, a render with it dry-runs against 03 with an EMPTY diff, `ab-diffgate.py ... A0 A0` -> GATE_PASS).
Commit exactly as step 1 below with subject `docs(talos): power tuning A/B kept variant A0 (talos-power-tuning-ab)`.
Go to 3.9.

**Winner B, C or D:**
1. Repo edit + commit (the talos dir is clean; premise):
   ```bash
   cd /Users/mu/code/cberg-home-nextgen; export W=/private/tmp/powerab-talos-power-tuning-ab; WIN=D     # the winner
   mise exec -- python3 "$W/ab-patches.py" kubernetes/bootstrap/talos $WIN          # AB_PATCHES_OK variant=$WIN
   git diff --stat kubernetes/bootstrap/talos      # 1 file: B/C 19 ins 18 del; D 25 ins 21 del (measured 2026-10-05: header + RAPL comment + tau lines)
   M=$(mktemp /private/tmp/claude-powerab-msg.XXXXXX)
   printf '%s\n\n%s\n' "feat(talos): SysfsConfig power tuning -> variant $WIN (talos-power-tuning-ab A/B winner)" \
     "A/B on nuc14-01/03, 3 runs per variant at ninth-banner d3ae92f; table in the plan's 4.B. F-6c7843e4. Config only; applied per node in window." > "$M"
   # append the session's attribution trailer lines (Co-Authored-By / Claude-Session) to "$M" before committing
   git commit --only kubernetes/bootstrap/talos/patches/global/machine-sysfs-power.yaml -F "$M"
   git log -1 --format=%s; git show --stat HEAD     # subject is ours; exactly that 1 file
   git pull --rebase --autostash && git push
   ```
2. Render the committed tree and prove it equals the measured winner render:
   ```bash
   export W=/private/tmp/powerab-talos-power-tuning-ab; test -d "$W" || { echo NO_W; exit 1; }
   cd /Users/mu/code/cberg-home-nextgen; export SOPS_AGE_KEY_FILE=$PWD/age.key
   (cd kubernetes/bootstrap/talos && mise exec -- talhelper genconfig -o "$W/r-final") 2>&1 | grep -v -E '^generated|talosVersion|might not be compatible|issues with your Talhelper'
   for n in 01 02 03; do python3 - "$W/r-final/kubernetes-k8s-nuc14-$n.yaml" "$W/r-$WIN/kubernetes-k8s-nuc14-$n.yaml" <<'PY'
   import sys, yaml
   g = lambda f: [d for d in yaml.safe_load_all(open(f)) if d and d.get("kind") == "SysfsConfig"][0]["params"]
   print(sys.argv[1][-8:-5], "SAME_SYSFS" if g(sys.argv[1]) == g(sys.argv[2]) else "DIFFERENT_SYSFS")
   PY
   done
   ```
   PASS = `SAME_SYSFS` x3. (The full render may differ only where talhelper is non-deterministic. The dry-run gate below
   decides the rest: `non_sysfs_changed_lines=0`.)
3. Dry-run r-final: on 03 and 01 from P (= last variant; if P == winner the gate expects an empty diff: `... $WIN $WIN`),
   on 02 from A0 (`ab-diffgate.py <dry> A0 $WIN`). All must PASS.
4. Apply r-final (coordinator): 03, 01 (skip a node whose dry-run was empty). `ab-works.py <ip> --snap` immediately
   before each apply, then the 3.4c gates against `$WIN`.
5. **nuc14-02 last, with a 20-min watch** (it is the suspected-defect node and runs production only):
   ```bash
   export W=/private/tmp/powerab-talos-power-tuning-ab; test -d "$W" || { echo NO_W; exit 1; }
   T0=$(date +%s); echo $T0 > "$W/n02-apply"; mise exec -- python3 "$W/capstats.py" pre02 20 "$W" $T0     # the 20 min BEFORE
   mise exec -- python3 "$W/ab-works.py" 192.168.55.12 --snap        # immediately before the apply
   # coordinator: talosctl -n 192.168.55.12 apply-config --mode=no-reboot -f "$W/r-final/kubernetes-k8s-nuc14-02.yaml"
   ```
   Gates: `ab-readback.py 192.168.55.12 $WIN --status` + `ab-works.py 192.168.55.12 --check`. Then wait 20 min (Monitor)
   and run `capstats.py post02 20 "$W"`. PASS on 02 = `min_ge100` 0, `temp_max` <= pre02 `temp_max` + 3 °C, and
   `throttles` <= max(2 x pre02, pre02 + 20). FAIL -> §5 for 02 only (apply `$W/r-A0/kubernetes-k8s-nuc14-02.yaml`,
   whose empty dry-run was proven in 3.2). Record the **known drift**: git = winner, nuc14-02 = A0. It is cured by the
   BIOS/cooler fix or by moving the EPP keys to per-node patches (§6). Set the plan `blocked` with that note, not
   `executed`.

### 3.8 Alert threshold: no change (asserted, not assumed)
PL1 is 35 W in every variant, and `NodeCPUPackagePowerAtCap` fires at 90 % of PL1 (31 W). Premise
`power-at-cap-alert-31w` holds the repo side. Check the loaded rule once at the end:
`kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/rules' | python3 -c 'import sys,json; print([r["query"] for g in json.load(sys.stdin)["data"]["groups"] for r in g["rules"] if r["name"]=="NodeCPUPackagePowerAtCap"])'`
-> contains `> 31`. D lowers only PL2 (45 W): the alert reads the 5-min rate against PL1, so it is unaffected.

### 3.9 Close-out
- Regenerate the local clusterconfig (gitignored): `cp -Rp kubernetes/bootstrap/talos/clusterconfig "$W/clusterconfig-pre"; mise exec -- task talos:generate-config`.
- `.venv/bin/python3 runbooks/policy-cli.py finding detail F-6c7843e4 --plan talos-power-tuning-ab --detail-file "$W/summary.txt"`
  (with `SWEEP_PG_DSN` up, in a separate Bash call from any `git commit`). Close the finding with the 3.7 commit
  (`finding close F-6c7843e4 --commit <sha>`) only if the winner's 01/03 `temp_max` stayed < 90 °C in every run AND 02
  passed its watch AND a 24 h `capstats.py` on 02 at the next sweep shows no minute >= 100 °C (the 20-min night watch is
  short). Otherwise leave it open with the numbers.
- Write the §4.B table into this plan's execution record. Status `executed` (or `blocked` per 3.7.5).
- Cleanup: `rm -rf /private/tmp/powerab-talos-power-tuning-ab /private/tmp/powerab-planning-dryrun` (machine secrets)
  within 7 days and no later than 2026-10-13. Keep `summary.txt` and the `stats-*`/`shards-*` files (no secrets) by
  copying them out first if wanted.

## 4. Verification

**4.1 CONTENTS ASSERTION: each node holds exactly the variant's values, and Talos owns them.** Measured by
`ab-readback.py <ip> <V> --status` after every apply. It reads every written key back from `/sys`, applying the
Meteor Lake name mapping (`64` -> `balance_performance`) and the RAPL quantization (`10000000` -> `9994240`). It checks
the untouched neighbours: PL4 120000000, PL2 window 2440, gt1 1300, and the PL1 window 27983872 when V has no tau
key. It requires one `KernelParamStatus` per key whose `current` is the WRITTEN string, and no other `sys.*` status.
PASS = `GATE_PASS node=<ip> variant=<V> keys=21|22 mismatches=0`.
What failure prints: an EPP write the kernel refused reads back the old name (`want balance_performance got
balance_power`). A tau that did not apply reads `27983872`. A tau not reset after leaving D shows
`unexpected sys.* statuses`. A locked RAPL leaves `got 55000000`.
Measured 2026-10-05: A0 PASS on 01/03, B on the A0 node FAIL (36 mismatches). The gate fails both ways.
CONTROL: metric node_rapl_package_joules_total - capstats `rapl_avg_w`/`rapl_max1m_w` per run. D must show
`rapl_max1m_w` <= ~46 W on 01/03 if any run ever reached PL2 (informational: CI reached only ~20 W on 10-04).

**4.2 CONTENTS ASSERTION: every apply changed exactly the planned keys and nothing else.** `ab-diffgate.py` on the
node's own dry-run before each apply: `GATE_PASS ... values_ok=True non_sysfs_changed_lines=0`. Measured: A0->A0
(empty), A0->B, A0->C and A0->D PASS on 03. Five negative controls FAIL (wrong target, wrong value, foreign line,
A0->A0 on a real diff).

**4.3 "Config works" per node** (`ab-works.py --check`): bootID unchanged (no reboot, deciding); node Ready; etcd 3
members, no learner, no ERRORS; gt0 max 1500 and gt1 max 1300 (iGPU caps intact); intel-gpu-plugin 1/1 Running on
the node; `gpu.intel.com/i915` allocatable > 0; every iGPU pod on the node Running+Ready with unchanged restarts
(2026-10-05: 01 = immich-server, jellyfin, makemkv; 02 = frigate, plex; 03 = immich-machine-learning); i915 dmesg error
lines not increased (INFORMATIONAL only: 01's ring buffer rotates within a day, so the count can fall). Negative controls measured 2026-10-05: a changed bootID and a changed restart count each FAIL.

**4.4 Measurement validity (per run):** `ab-summary.py` drops a run with < 7 finished shards, any shard on nuc14-02, or
any pod of a Job NOT named in the run's own log, on 01/03, whose run overlaps the run window (`foreign_ci_pods`; another
session's CI shared the nodes) -> `INVALID RUN`. Measured on the 10-04 files: the AFTER file contains 3 pods of the BEFORE
e2e Job (23:05-23:09Z). Replayed with its TRUE window (from 23:17:44Z) it is correctly NOT flagged, because those pods
had finished. With the window widened to overlap them it prints `INVALID RUN ... foreign_ci_pods=2` (the third BEFORE pod ran on 02,
outside the 01/03 filter). `ab-shards.py` now skips only pods that FINISHED before the run started. A foreign Job
created gated before `t0` and admitted onto 01/03 during the run is therefore recorded and invalidates the run.
Dry-tested with a fake pod list: a foreign pod created at t0-60 and started at t0+60 is recorded; a pod finished at
t0-500 is not. A missing
`stats-idle-L.json` ABORTS the summary (`AB_SUMMARY_ABORT ...`, fail closed: J/shard would read NaN). Re-run that
capstats; the data is in Prometheus. `capstats.py` writes its JSON only after its node-count and coverage checks: `CAPSTATS_ABORT` = no
data = re-run capstats, never a zero.
CONTROL: metric node_thermal_zone_temp - `temp_p95`/`temp_max`/`min_ge100` per run, `max by (instance)` aggregated
(decision rule 1).
CONTROL: metric node_cpu_package_throttles_total - `throttles` per run (decision rule 1; in-run abort > 5).
CONTROL: metric node_hwmon_temp_celsius - NVMe max per run (informational; a rise points at airflow, not the CPU).
CONTROL: alertname NodeCPUPackagePowerAtCap - rule loaded with `> 31` at the end (3.8). It may fire (info) under load;
that is the cap working, not a failure.
CONTROL: alertname NodeCPUPackageHot - INFORMATIONAL (capstats decides).
CONTROL: alertname CIRunnerThermalGateStalled - must not fire during a run. If it does, a shard never got a slot and
that run is invalid.

**4.5 End state (after 3.7):** all three nodes `ab-readback.py <ip> <winner> --status` -> GATE_PASS (02: A0 if its watch
failed, recorded). `ab-works.py --check` PASS on all three. `kubectl get pods -A ...` into `$W/restarts-after.txt`:
`diff` against `restarts-before.txt` shows no new restarts in kube-system/storage/network. etcd leader changes during
the run <= 1: `mise exec -- talosctl -n 192.168.55.11 etcd status | awk 'NR==2{print $8, $10}'` against
`$W/etcd-before.txt`. Each election increments RAFT TERM by >= 1, so the term delta must be <= 1. The same leader with
the same term = 0 elections.

### 4.B Result table (fill from `summary.txt`; attach to the run report)

| | E BEFORE 10-04 | A0 (control + 10-04 AFTER) | B | C | D |
|---|---|---|---|---|---|
| runs (valid) | 1 | 1 (+1) | | | |
| sims / e2e median shard s | 350 / 197 | 478 / 264 (10-04) | | | |
| paired slowdown vs BEFORE | 0 | +36.6 % (10-04) | | | |
| 01: temp p95 / max °C | 74.4 / 77 | 61.0 / 62 (10-04) | | | |
| 03: temp p95 / max °C | 77.4 / 87 | 57.0 / 71 (10-04) | | | |
| 01 / 03 throttles (sum) | 1 / 0 | 1 / 0 (10-04) | | | |
| 01 / 03 avg W, J/shard | 23.9 / 19.4 W | 15.6 / 12.7 W (10-04) | | | |
| eligible / verdict | n/a | | | | |

## 5. Rollback

**Per node (primary; no reboot): apply the A0 render (= HEAD at plan start, proven equal to the live config in 3.2).**
```bash
export W=/private/tmp/powerab-talos-power-tuning-ab; test -d "$W" || { echo NO_W; exit 1; }
P=B; ip=192.168.55.13; n=3                  # P = what the node holds now
mise exec -- python3 "$W/ab-works.py" $ip --snap    # immediately before the apply (the check after it compares to this)
mise exec -- talosctl -n $ip apply-config --dry-run --mode=no-reboot -f "$W/r-A0/kubernetes-k8s-nuc14-0$n.yaml" > "$W/dry-rb-$n.txt" 2>&1; mise exec -- python3 "$W/ab-diffgate.py" "$W/dry-rb-$n.txt" $P A0
mise exec -- talosctl -n $ip apply-config --mode=no-reboot -f "$W/r-A0/kubernetes-k8s-nuc14-0$n.yaml"      # coordinator
python3 -c "import time; time.sleep(10)"; mise exec -- python3 "$W/ab-readback.py" $ip A0 --status | tail -1      # GATE_PASS ... variant=A0
mise exec -- python3 "$W/ab-works.py" $ip --check | tail -1        # CONFIGWORKS_PASS
```
Back when it prints `GATE_PASS ... variant=A0 keys=21 mismatches=0`: EPP balance_power on 18 CPUs, PL2 55 W, the PL1
window back at 27983872 with no time-window status (Talos `resetKernelParam` after D), and KernelParamStatus for
exactly the 21 committed keys. In a rollback the diff gate is advisory. If it FAILs (unexpected live state), apply A0
anyway: it is the known-good repo state. Break-glass if the A0 apply itself errors:
`talosctl -n $ip apply-config --mode=no-reboot -f "$W/live-$ip.yaml"` (the 2.5 copy), then
`ab-readback.py $ip A0 --status`.

**Repo (only if 3.7 committed):** `git revert <3.7 sha>`, verify subject and stat, push; then apply A0 per node as above.
Flux reconciles nothing for the talos part. Restore the local dir: `rm -rf kubernetes/bootstrap/talos/clusterconfig && cp -Rp
"$W/clusterconfig-pre" kubernetes/bootstrap/talos/clusterconfig`.

**Forward-only parts:** none. No data, no reboot. Every EPP/PL/tau value is rewritten by the next apply.

## 6. Interference notes

**Proposed timetable: TWO attended on-demand NOW runs** (Europe/Berlin = UTC+2 until 2026-10-25). Reviewer 2026-10-05:
realistic run times (~32 min) put a single evening at ~450 min, too close to the 480 ceiling. Two evenings also give two
A0 controls, one per evening, which counterbalances the fixed B -> C -> D order against evening load drift.

| Berlin (UTC) | step | operator |
|---|---|---|
| **Evening 1, Tue 2026-10-06** | | |
| 18:30 (16:30Z) | run-now preflight (needs `ci-runner-exclude-node02` EXECUTED, nightly 10-06), Step 0 (safe updates), 2.x pre-checks | GO |
| 18:55 (16:55Z) | 3.3 A0 control `A0-1` (renders 3.1 + A0 dry-runs 3.2 in parallel) | - |
| 19:30 (17:30Z) | **B: dry-run, apply 03 + 01** | **OK #1** |
| 19:50-21:30 | B-1..B-3 | - |
| 21:30 (19:30Z) | **C apply** | **OK #2** (suggest: also pre-grant the 23:10 return to A0) |
| 21:50-23:10 | C-1..C-3 | - |
| 23:10 (21:10Z) | **back to A0 on 03 + 01** (§5 procedure, dry-run gated) -> no node stays overnight on a measured-only variant | **OK #3** |
| ~23:40 | evening 1 done (~308 min); `ab-summary.py` interim table (no decision) | - |
| **Evening 2, Wed 2026-10-07** | | |
| 18:30 (16:30Z) | preflight, Step 0, 2.2/2.4/2.5 again (the 2.3 baselines and renders in `$W` are reused; re-run 3.2 A0 dry-runs) | GO |
| 18:55 | A0 control `A0-2` | - |
| 19:30 (17:30Z) | **D: dry-run A0 -> D, apply 03 + 01** | **OK #4** |
| 19:50-21:30 | D-1..D-3 | - |
| 21:30 (19:30Z) | 3.5 decision over A0-1, A0-2, B, C, D | **confirm winner + OK #5 (final applies)** |
| 21:40-22:30 | 3.7 final roll (03, 01, 02 + 20-min watch), 3.8, 3.9 | - |
| 01:45 / 02:45 | hard stop for 3.7 / everything done (nightly 03:30) | - |

On evening 2 the D dry-run starts from P = A0, because evening 1 ended on A0. The gate expects
`plus=20/20 minus=19/19` (measured A0->D on 03). Capacity: evening 1 ~308 min, evening 2 ~245 min, both under the 480
on-demand ceiling. `needs_reboot: false`, so NOW runs may carry it. A single long evening is still possible
(B -> C -> D without the return to A0, ~450 min, start no later than 17:30). It is not recommended.

- **Nothing else in either NOW run** (`exclusive: true`). `ci-runner-exclude-node02` must have EXECUTED before evening 1
  (nightly 2026-10-06). If that nightly does not run it (e.g. the soak was not captured in time), it runs in the nightly
  of 10-07 and **both A/B evenings shift by one day** (10-07/10-08). It cannot join the A/B's run, because run-now
  checks every premise at preflight.
- **No other CI** 18:30-02:45: the A/B's triggers export `GATE_SECOND_POD_NODES=` and `GATE_MAX_CPU_PER_NODE=1` (one
  shard per node, as in BEFORE/AFTER where each shard ran alone on its node). Another session's trigger would admit
  with the defaults and break that. Coordinate with the ci-runner owner (2.4).
- **talos-sysfs-power-caps**: conflicts_with plus the premise `soak-24h-recorded`, because its soak must finish first. Not
  depends_on: run-now refuses a dependency until it is `executed`, and the soak alone does not make it executed. Its 3.10 (CI gate 85 -> 88 °C) may land
  before tonight; that only changes admission temperatures, which the A/B's 1-shard-per-node runs rarely touch.
  Its close-out copies the **seven** baseline files into this plan's `$W` before wiping its own dir (§5 Copy-out, 3c8833b8).
- **talos-linux-1.14.2** (reboot roll): never the same night. If it runs later, its post-reboot gates must read back
  the WINNER's values (`ab-readback.py <ip> <winner>`), not the 2026-10-04 caps. That is a repo correction for that plan,
  whose `sysfs-readback.py ... caps` check will FAIL against any winner other than A0.
- **kube-prometheus-stack-91.9.0 / immich-ml / jellyfin / helm-drift-detection**: conflicts_with (instrument or iGPU/CPU
  load on 01/03). kube-prometheus-stack-91.9.0 and immich-machine-learning-3.2.4 have `window: null` today (immich-ml
  is vetted and the scheduler proposes nightly:2026-10-06, i.e. 03:30, BEFORE evening 1, which is fine). jellyfin-12.1
  sat 10-10, jellyfin-config-rwo-migration sun 10-25, helm-drift-detection sat 11-07. The refs keep the scheduler from
  putting any of them into an A/B run. Reciprocity owed by those authors.
- **ci-gate-primary-control-rework** (backlog) depends on this plan's committed winner.
- **Per-node exception for nuc14-02:** not possible with the current patch layout (fact 7). If 02 fails its watch,
  the clean fix is moving the 18 EPP keys from the global patch into the three per-node patches (a follow-up plan),
  or the BIOS/cooler fix. Until then git and 02 differ, recorded in the plan and the finding.
- **BIOS follow-up (operator, physical):** when the BIOS PL1/PL2/tau are set to match the chosen OS values, the
  SysfsConfig RAPL keys still overwrite the MSR at boot. Measure after the BIOS change (predecessor §6 procedure); an
  ASUS BIOS update can also move the DRM card index (premise `igpu-card-index-node03-card1`).
- **Repo correction, not planned around:** `talos-sysfs-power-caps` §1 says "EPP balance_power on cpu0..cpu17" as if
  it were driver-independent. On this CPU it is the raw value 179, and `64` == `balance_performance`. The read-back
  of a raw-EPP config differs from the written string (fact 3); anyone writing a numeric-EPP gate must map it.

## Appendix - scripts (extracted by §2; all dry-tested 2026-10-05 as stated in §2/§3/§4)

### ab-patches.py

```python ab-patches
# ab-patches.py <talos-dir> <A0|B|C|D>  -- rewrites patches/global/machine-sysfs-power.yaml for one variant
# (plan talos-power-tuning-ab). Input MUST be the committed c2c155b8 shape (asserted). PL1 35 W and the
# iGPU key never change. Only D carries the PL1 time-window key; for A0/B/C it stays at the BIOS value
# 27983872 us, and removing it after D makes Talos write the captured default back (resetKernelParam).
import sys
T, v = sys.argv[1], sys.argv[2]
V = {"A0": ("55000000", None, "balance_power"), "B": ("55000000", None, "64"),
     "C": ("55000000", None, "96"), "D": ("45000000", "10000000", "96")}
pl2, tau, epp = V[v]
p = f"{T}/patches/global/machine-sysfs-power.yaml"; t = open(p).read()
L2 = '  class/powercap/intel-rapl:0/constraint_1_power_limit_uw: "55000000"\n'
E = 'energy_performance_preference: "balance_power"\n'
assert t.count(L2) == 1 and t.count(E) == 18 and "constraint_0_time_window_us" not in t \
    and t.count('constraint_0_power_limit_uw: "35000000"\n') == 1, "patch not in the committed c2c155b8 shape"
if v == "A0":
    if "--record" in sys.argv:   # final roll, A0 kept: record the decision in git (comment only, render-neutral)
        t = t.replace("apiVersion: v1alpha1\n", "# Power tuning A/B (plan talos-power-tuning-ab): variant A0 kept, no value change "
                      "(EPP 179 = balance_power, PL2 55 W).\napiVersion: v1alpha1\n", 1)
        open(p, "w").write(t); print("AB_PATCHES_OK variant=A0 recorded"); sys.exit(0)
    print("AB_PATCHES_OK variant=A0 (unchanged)"); sys.exit(0)
t = t.replace(E, f'energy_performance_preference: "{epp}"\n')
new = f'  class/powercap/intel-rapl:0/constraint_1_power_limit_uw: "{pl2}"\n'
if tau:
    C1 = "  # RAPL package-0: PL1 (long_term), PL2 (short_term). Time windows (PL1 tau\n  # ~28 s, PL2 2.44 ms) and PL4 (peak_power 120 W) stay at BIOS values.\n"
    assert t.count(C1) == 1, "RAPL comment not in the c2c155b8 shape"
    t = t.replace(C1, "  # RAPL package-0: PL1 (long_term), PL2 (short_term). PL1 tau is set below (variant D);\n"
                      "  # the PL2 window (2.44 ms) and PL4 (peak_power 120 W) stay at BIOS values.\n")
    new += ("  # PL1 time window (tau) 28 s -> 10 s: the package falls back to PL1 sooner after a burst\n"
            "  # (RAPL quantizes 10000000 us to 9994240 us; plan talos-power-tuning-ab)\n"
            f'  class/powercap/intel-rapl:0/constraint_0_time_window_us: "{tau}"\n')
t = t.replace(L2, new)
t = t.replace("apiVersion: v1alpha1\n", f"# Variant {v} of plan talos-power-tuning-ab: PL2 {int(pl2)//1000000} W, EPP {epp} "
              f"(Meteor Lake: 64 = balance_performance, 179 = balance_power){', PL1 tau 10 s' if tau else ''}.\napiVersion: v1alpha1\n", 1)
open(p, "w").write(t); print(f"AB_PATCHES_OK variant={v}")
```

### ab-diffgate.py

```python ab-diffgate
# ab-diffgate.py <dry-run-output> <from-variant> <to-variant>
# Every changed line of the Talos dry-run diff must be one of the plan's SysfsConfig keys, '-' with the FROM
# value and '+' with the TO value, and exactly the keys whose value differs must appear. Content never printed.
import re, sys
txt = open(sys.argv[1]).read(); fr, to = sys.argv[2], sys.argv[3]
V = {"A0": ("55000000", None, "balance_power"), "B": ("55000000", None, "64"),
     "C": ("55000000", None, "96"), "D": ("45000000", "10000000", "96")}
def keys(v):
    pl2, tau, epp = V[v]
    d = {"class/powercap/intel-rapl:0/constraint_1_power_limit_uw": pl2}
    d.update({f"devices/system/cpu/cpu{i}/cpufreq/energy_performance_preference": epp for i in range(18)})
    if tau: d["class/powercap/intel-rapl:0/constraint_0_time_window_us"] = tau
    return d
F, Tt = keys(fr), keys(to)
want_minus = {k: v for k, v in F.items() if Tt.get(k) != v}
want_plus = {k: v for k, v in Tt.items() if F.get(k) != v}
if fr == to:
    ok = "No changes" in txt or ("Config diff:" in txt and not [l for l in txt.split("Config diff:", 1)[1].splitlines() if l[:1] in "+-" and l not in ("--- a", "+++ b")])
    print(f"{'GATE_PASS' if ok else 'GATE_FAIL'} from={fr} to={to} (expect no diff)"); sys.exit(0 if ok else 1)
if "Config diff:" not in txt: print('GATE_FAIL no "Config diff:" in dry-run output'); sys.exit(2)
KEY = re.compile(r'^([+-]) {4}([a-z0-9/:_-]+): "?([a-z_0-9]+)"?$')
plus, minus, bad = {}, {}, 0
for l in txt.split("Config diff:", 1)[1].splitlines():
    if l in ("--- a", "+++ b") or not l or l[0] not in "+-": continue
    m = KEY.match(l)
    if m and m.group(2) in set(F) | set(Tt):
        (plus if m.group(1) == "+" else minus)[m.group(2)] = m.group(3)
    else: bad += 1
ok = bad == 0 and plus == want_plus and minus == want_minus
print(f"{'GATE_PASS' if ok else 'GATE_FAIL'} from={fr} to={to} plus={len(plus)}/{len(want_plus)} minus={len(minus)}/{len(want_minus)} "
      f"values_ok={plus == want_plus and minus == want_minus} non_sysfs_changed_lines={bad}")
sys.exit(0 if ok else 1)
```

### ab-readback.py

```python ab-readback
#!/usr/bin/env python3
# ab-readback.py <node-ip> <A0|B|C|D> [--status]  -- reads every SysfsConfig key back from /sys (talosctl read)
# and, with --status, requires one Talos KernelParamStatus per key whose `current` is the WRITTEN string and no
# other sys.* status. Sysfs shows Meteor Lake's named EPPs for 64/179 (intel_pstate show_energy_performance_
# preference prints the name when the raw EPP equals a table value) and the quantized tau (9994240 for 10000000).
import json, subprocess, sys
ip, v = sys.argv[1], sys.argv[2]; want_status = "--status" in sys.argv
CARD = {"192.168.55.11": "card0", "192.168.55.12": "card0", "192.168.55.13": "card1"}[ip]
V = {"A0": ("55000000", None, "balance_power"), "B": ("55000000", None, "64"),
     "C": ("55000000", None, "96"), "D": ("45000000", "10000000", "96")}
pl2, tau, epp = V[v]
written = {"class/powercap/intel-rapl:0/constraint_0_power_limit_uw": "35000000",
           "class/powercap/intel-rapl:0/constraint_1_power_limit_uw": pl2,
           f"class/drm/{CARD}/gt/gt0/rps_max_freq_mhz": "1500"}
written.update({f"devices/system/cpu/cpu{i}/cpufreq/energy_performance_preference": epp for i in range(18)})
if tau: written["class/powercap/intel-rapl:0/constraint_0_time_window_us"] = tau
SHOW = {"64": "balance_performance", "179": "balance_power", "16": "performance", "10000000": "9994240"}
neigh = {"class/powercap/intel-rapl:0/constraint_2_power_limit_uw": "120000000",
         "class/powercap/intel-rapl:0/constraint_1_time_window_us": "2440",
         f"class/drm/{CARD}/gt/gt1/rps_max_freq_mhz": "1300"}
if not tau: neigh["class/powercap/intel-rapl:0/constraint_0_time_window_us"] = "27983872"
bad = []
def rd(k):
    r = subprocess.run(["talosctl", "-n", ip, "read", "/sys/" + k], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else f"ERR({r.stderr.strip()[-60:]})"
for k, w in written.items():
    got = rd(k); exp = SHOW.get(w, w)
    if got != exp: bad.append(f"{k}: want {exp} got {got}")
for k, w in neigh.items():
    got = rd(k)
    if got != w: bad.append(f"{k} (untouched): want {w} got {got}")
if want_status:
    out = subprocess.run(["talosctl", "-n", ip, "get", "kernelparamstatuses", "-o", "json"], capture_output=True, text=True).stdout
    dec, i, st, n = json.JSONDecoder(), 0, {}, 0
    while i < len(out):
        while i < len(out) and out[i].isspace(): i += 1
        if i >= len(out): break
        o, i = dec.raw_decode(out, i); n += 1
        if o["metadata"]["id"].startswith("sys."): st[o["metadata"]["id"]] = str(o["spec"]["current"])
    if n == 0: bad.append("KernelParamStatus list EMPTY (talosctl error?) - cannot assert")
    for k, w in written.items():
        if st.get("sys." + k) != w: bad.append(f"KernelParamStatus sys.{k}: want {w} got {st.get('sys.' + k)}")
    extra = set(st) - {"sys." + k for k in written}
    if extra: bad.append(f"unexpected sys.* statuses: {sorted(extra)}")
for b in bad[:30]: print("  MISMATCH", b)
print(f"{'GATE_PASS' if not bad else 'GATE_FAIL'} node={ip} variant={v} keys={len(written)} mismatches={len(bad)}")
sys.exit(0 if not bad else 1)
```

### ab-works.py

```python ab-works
#!/usr/bin/env python3
# ab-works.py <node-ip> --snap | --check   (read-only; plan talos-power-tuning-ab "config works")
#   --snap : record bootID, i915 dmesg error-line count and the restart counts of every iGPU-consumer pod on the node
#   --check: bootID unchanged, node Ready, etcd 3 members/no errors, gt0 max 1500 + gt1 max 1300 (untouched), intel-gpu-plugin
#            1/1 Running on the node, i915 allocatable > 0, every pod requesting gpu.intel.com/i915 on the node Running+Ready
#            with restarts unchanged, i915 error lines not increased.  -> CONFIGWORKS_PASS / CONFIGWORKS_FAIL
import json, re, subprocess, sys
ip, mode = sys.argv[1], sys.argv[2]
W = "/private/tmp/powerab-talos-power-tuning-ab"
node = {"192.168.55.11": "k8s-nuc14-01", "192.168.55.12": "k8s-nuc14-02", "192.168.55.13": "k8s-nuc14-03"}[ip]
card = {"192.168.55.11": "card0", "192.168.55.12": "card0", "192.168.55.13": "card1"}[ip]
def sh(*a): return subprocess.run(list(a), capture_output=True, text=True)
def gpu_pods():
    out = {}
    for p in json.loads(sh("kubectl", "get", "pods", "-A", "-o", "json").stdout)["items"]:
        if p["spec"].get("nodeName") != node or p["metadata"]["namespace"] == "ci-runner": continue
        if any("gpu.intel.com/i915" in ((c.get("resources") or {}).get("requests") or {}) for c in p["spec"]["containers"]):
            cs = p["status"].get("containerStatuses") or []
            out[f'{p["metadata"]["namespace"]}/{p["metadata"]["name"]}'] = {
                "restarts": sum(c.get("restartCount", 0) for c in cs), "phase": p["status"].get("phase"),
                "ready": bool(cs) and all(c.get("ready") for c in cs)}
    return out
def i915_err(): return len([l for l in sh("talosctl", "-n", ip, "dmesg").stdout.splitlines() if re.search(r"i915.*(error|fail|hang|reset)", l, re.I)])
boot = sh("kubectl", "get", "node", node, "-o", "jsonpath={.status.nodeInfo.bootID}").stdout.strip()
snapf = f"{W}/works-snap-{ip}.json"
if mode == "--snap":
    s = {"boot": boot, "i915_err": i915_err(), "pods": gpu_pods()}
    if not boot or not s["pods"]: print("WORKS_SNAP_FAIL empty bootID or no iGPU pods on node"); sys.exit(1)
    json.dump(s, open(snapf, "w")); print(f"WORKS_SNAP_OK node={node} gpu_pods={len(s['pods'])} i915_err={s['i915_err']}"); sys.exit(0)
s = json.load(open(snapf)); bad = []
if boot != s["boot"]: bad.append(f"bootID changed ({s['boot'][:8]} -> {boot[:8]}): REBOOT")
ready = sh("kubectl", "get", "node", node, "-o", 'jsonpath={.status.conditions[?(@.type=="Ready")].status}').stdout.strip()
if ready != "True": bad.append(f"node Ready={ready}")
et = sh("talosctl", "-n", "192.168.55.11,192.168.55.12,192.168.55.13", "etcd", "status").stdout.splitlines()[1:]
# healthy row = 14 tokens ("462 MB", "123 MB (26.61%)" split); an ERRORS value adds tokens; LEARNER is token 11
if len(et) != 3 or any(len(l.split()) != 14 or l.split()[11] != "false" for l in et): bad.append(f"etcd: {len(et)} members, a learner, or ERRORS set")
for g, w in (("gt0", "1500"), ("gt1", "1300")):
    got = sh("talosctl", "-n", ip, "read", f"/sys/class/drm/{card}/gt/{g}/rps_max_freq_mhz").stdout.strip()
    if got != w: bad.append(f"{g} max {got} != {w}")
pl = [l.split() for l in sh("kubectl", "-n", "kube-system", "get", "pods", "-o", "wide", "--no-headers").stdout.splitlines() if "intel-gpu-plugin" in l and node in l]
if not pl or pl[0][1] != "1/1" or pl[0][2] != "Running": bad.append(f"intel-gpu-plugin on {node}: {pl[0][1:4] if pl else 'MISSING'}")
alloc = sh("kubectl", "get", "node", node, "-o", "jsonpath={.status.allocatable.gpu\\.intel\\.com/i915}").stdout.strip()
if alloc in ("", "0"): bad.append(f"i915 allocatable '{alloc}'")
now = gpu_pods()
for k, v in s["pods"].items():
    n = now.get(k)
    if n is None: bad.append(f"iGPU pod {k} gone (replaced? check its owner)"); continue
    if n["phase"] != "Running" or not n["ready"] or n["restarts"] != v["restarts"]: bad.append(f"iGPU pod {k}: {n} (was restarts={v['restarts']})")
e = i915_err()
if e > s["i915_err"]: bad.append(f"i915 dmesg error lines {s['i915_err']} -> {e}")
for b in bad: print("  WORKS_FAIL", b)
print(f"{'CONFIGWORKS_PASS' if not bad else 'CONFIGWORKS_FAIL'} node={node} gpu_pods={len(s['pods'])} checks_failed={len(bad)}")
sys.exit(0 if not bad else 1)
```

### ab-shards.py

```python ab-shards
# ab-shards.py <label>  -- records every CI shard pod of run <label> (node, container start, finish) until the run's
# log says SUITES_DONE; writes $W/shards-<label>.json (same shape as the 2026-10-04 shards-before/after.json).
import calendar, json, os, re, subprocess, sys, time
W = "/private/tmp/powerab-talos-power-tuning-ab"; L = sys.argv[1]
t0 = int(open(f"{W}/run-{L}.start").read()); out = f"{W}/shards-{L}.json"; rec = {}; done_at = None
def ts(s): return calendar.timegm(time.strptime(s, "%Y-%m-%dT%H:%M:%SZ")) if s else 0   # UTC (mktime would apply local DST)
while True:
    r = subprocess.run(["kubectl", "get", "pods", "-n", "ci-runner", "-l", "app.kubernetes.io/name=the-ninth-banner-tests", "-o", "json"], capture_output=True, text=True)
    if r.returncode == 0:
        for p in json.loads(r.stdout)["items"]:
            # skip only pods that FINISHED before this run started: a foreign Job created (gated) BEFORE t0 but admitted
            # onto 01/03 DURING the run must be recorded, so ab-summary.py foreign() can invalidate the run
            fin0 = ((p.get("status", {}).get("containerStatuses") or [{}])[0].get("state", {}).get("terminated") or {}).get("finishedAt")
            if fin0 and ts(fin0) < t0: continue
            n = p["metadata"]["name"]; st = p.get("status", {}); cs = (st.get("containerStatuses") or [{}])[0]
            term = cs.get("state", {}).get("terminated") or {}; run = cs.get("state", {}).get("running") or {}
            d = rec.setdefault(n, {})
            d.update({"job": p["metadata"]["labels"].get("batch.kubernetes.io/job-name"), "node": p["spec"].get("nodeName") or d.get("node"),
                      "runStarted": run.get("startedAt") or term.get("startedAt") or d.get("runStarted"),
                      "finishedAt": term.get("finishedAt") or d.get("finishedAt"), "exitCode": term.get("exitCode", d.get("exitCode")),
                      "phase": st.get("phase")})
        json.dump(rec, open(out, "w"), indent=1)
    log = open(f"{W}/run-{L}.log").read() if os.path.exists(f"{W}/run-{L}.log") else ""
    if "SUITES_DONE" in log:
        # the trigger finishes a shard when it has COPIED its results; the container ends seconds later (10-04 BEFORE:
        # +4 s, finishedAt missed). Keep polling until every pod of this run's Jobs has finishedAt, bounded to 180 s.
        done_at = done_at or time.time()
        jobs = set(re.findall(r"^job ci-runner/(\S+) ", log, re.M))
        open_pods = [n for n, d in rec.items() if d.get("job") in jobs and not d.get("finishedAt")]
        if not open_pods or time.time() - done_at > 180:
            if open_pods: print("SHARDS_UNFINISHED", L, open_pods)
            break
        time.sleep(5); continue
    time.sleep(15)
print("SHARDS_DONE", L, len(rec))
```

### ab-summary.py

```python ab-summary
#!/usr/bin/env python3
# ab-summary.py [W]  -- plan talos-power-tuning-ab §4.B table + decision rule.
# Runs: A0-1, B-1..3, C-1..3 (evening 1) and A0-2, D-1..3 (evening 2). Per run L: shards-L.json (ab-shards.py),
# run-L.{start,end,log}, stats-L.json + stats-idle-L.json (capstats.py). Baselines (copied in §2): E = 2026-10-04 BEFORE,
# A1004 = 2026-10-04 AFTER, both at ref d3ae92f (they carry no .start/.end; never validity-checked, never ranked).
# PRIMARY metric: each variant against ITS OWN EVENING's A0 control, PAIRED by shard index (same tests on the same
# evening) -> geometric-mean ratio - 1. "vs BEFORE" (paired vs E) is reported and feeds only the PL1 note.
import calendar, glob, json, math, re, statistics as st, sys, time
W = sys.argv[1] if len(sys.argv) > 1 else "/private/tmp/powerab-talos-power-tuning-ab"
N = {"192.168.55.11": "k8s-nuc14-01", "192.168.55.13": "k8s-nuc14-03"}
EVE = {"A0-1": 1, "B": 1, "C": 1, "A0-2": 2, "D": 2}
def ts(s): return calendar.timegm(time.strptime(s, "%Y-%m-%dT%H:%M:%SZ"))   # UTC
def jobs_of(L):
    j = set(re.findall(r"^job ci-runner/(\S+) ", open(f"{W}/run-{L}.log").read(), re.M))
    if not j: raise SystemExit(f"AB_SUMMARY_ABORT run-{L}.log names no Job")
    return j
def raw(L): return json.load(open(f"{W}/shards-{L}.json"))
def shards(L):
    # only the Jobs this run's own log created: the 2026-10-04 AFTER collector also caught the BEFORE run's e2e pods
    jobs, out = jobs_of(L), []
    for name, d in raw(L).items():
        m = re.match(r"tnb-(sims|e2e)(?:-gpu)?-[0-9a-f]{7}-\d+-(\d+)-", name)
        if m and d.get("job") in jobs and d.get("runStarted") and d.get("finishedAt"):
            out.append((m.group(1), int(m.group(2)), d["node"], ts(d["finishedAt"]) - ts(d["runStarted"])))
    return out
def foreign(L):
    # a CI pod of ANOTHER Job on 01/03 whose run overlaps this run's window = someone else's CI shared the nodes
    jobs, s0, s1 = jobs_of(L), int(open(f"{W}/run-{L}.start").read()), int(open(f"{W}/run-{L}.end").read())
    return [n for n, d in raw(L).items() if d.get("job") not in jobs and d.get("node") in N.values() and d.get("runStarted")
            and ts(d["runStarted"]) < s1 and (ts(d["finishedAt"]) if d.get("finishedAt") else s1) > s0]
def ld(f):
    try: return json.load(open(f))["nodes"]
    except Exception: return None
def gm(rs): return math.exp(sum(math.log(r) for r in rs) / len(rs)) - 1 if rs else float("nan")
def paired(a, b):   # ratios a/b for shard keys present in both (a, b: {(suite, idx): seconds})
    return [a[k] / b[k] for k in a if k in b]
base = {(s, i): t for s, i, n, t in shards("E")}
labels = sorted(f.split("shards-", 1)[1][:-5] for f in glob.glob(f"{W}/shards-*.json"))
labels = [L for L in labels if L not in ("E", "A1004")]
valid, bad = {}, []
for L in labels:
    s = shards(L); fo = foreign(L); stt = ld(f"{W}/stats-{L}.json"); idle = ld(f"{W}/stats-idle-{L}.json")
    on02 = [x for x in s if x[2] == "k8s-nuc14-02"]
    if len(s) < 7 or on02 or fo or stt is None:
        bad.append(f"{L}: shards={len(s)} on_nuc14-02={len(on02)} foreign_ci_pods={len(fo)} stats={'ok' if stt else 'MISSING'}"); continue
    if idle is None:   # fail closed: J/shard would silently read NaN; the data is in Prometheus, re-run capstats
        raise SystemExit(f"AB_SUMMARY_ABORT stats-idle-{L}.json missing: run capstats.py idle-{L} 5 \"$W\" $(cat \"$W/run-{L}.start\")")
    valid[L] = (s, stt, idle, json.load(open(f"{W}/stats-{L}.json"))["minutes"])
for b in bad: print("INVALID RUN (excluded):", b)
# A0 control per evening: label A0-<evening>[suffix]; a replacement for an INVALID control is A0-1b / A0-2b (ab-run.sh
# refuses a reused label). The first VALID label per evening, in sorted order, is that evening's reference.
a0 = {}
for L in sorted(valid):
    if L.startswith("A0-") and L[3:4] in ("1", "2") and f"A0-{L[3]}" not in a0:
        a0[f"A0-{L[3]}"] = {(su, i): t for su, i, n, t in valid[L][0]}
drift = None
if len(a0) == 2:
    drift = gm(paired(a0["A0-2"], a0["A0-1"]))
    print(f"EVENING DRIFT A0-2 vs A0-1 (paired, {len(paired(a0['A0-2'], a0['A0-1']))} shards): {drift:+.1%}")
aft = {(s, i): t for s, i, n, t in shards("A1004") if n != "k8s-nuc14-02"}
for L in a0: print(f"{L} vs 2026-10-04 AFTER (paired): {gm(paired(a0[L], aft)):+.1%} (informational)")
res = {}
for v in ("A0", "B", "C", "D"):
    Ls = [L for L in valid if L.split("-")[0] == v]
    if not Ls: continue
    ref = None if v == "A0" else (f"A0-{EVE[v]}" if f"A0-{EVE[v]}" in a0 else next(iter(a0), None))
    sh, rE, rA, th = [], [], [], {ip: {k: [] for k in ("p95", "max", "thr", "w", "ge100", "j")} for ip in N}
    for L in Ls:
        s, stt, idle, mins = valid[L]; sh += s
        d = {(su, i): t for su, i, n, t in s}
        rE += paired(d, base)
        if ref: rA += paired(d, a0[ref])
        for ip, node in N.items():
            x = stt[ip]; th[ip]["p95"].append(x["temp_p95"]); th[ip]["max"].append(x["temp_max"]); th[ip]["thr"].append(x["throttles"])
            th[ip]["w"].append(x["rapl_avg_w"]); th[ip]["ge100"].append(x["min_ge100"])
            k = len([y for y in s if y[2] == node])
            if k: th[ip]["j"].append((x["rapl_avg_w"] - idle[ip]["rapl_avg_w"]) * mins * 60 / k)
    res[v] = {"runs": len(Ls), "ref": ref or "-", "slow_own": 0.0 if v == "A0" else gm(rA), "slow_E": gm(rE),
              "cross": ref is not None and v != "A0" and ref != f"A0-{EVE[v]}",   # normalised against ANOTHER evening's A0
              "med": {su: st.median([t for s_, i, n, t in sh if s_ == su]) for su in ("sims", "e2e")},
              "th": {ip: {"p95": max(x["p95"]), "max": max(x["max"]), "thr": sum(x["thr"]), "w": st.mean(x["w"]),
                          "ge100": sum(x["ge100"]), "j": st.mean(x["j"]) if x["j"] else float("nan")} for ip, x in th.items()}}
print(f"{'var':4} {'runs':>4} {'ref':>5} {'vs own A0':>9} {'vs BEFORE':>9} {'sims/e2e med s':>14} | per node 01 / 03: p95/max C, throttles, avg W, J/shard, min>=100")
for v, r in res.items():
    t = "  ".join(f"{d['p95']:.0f}/{d['max']:.0f}C thr={d['thr']:.0f} {d['w']:.1f}W {d['j']:.0f}J ge100={d['ge100']:.0f}" for ip, d in sorted(r["th"].items()))
    print(f"{v:4} {r['runs']:>4} {r['ref']:>5} {r['slow_own']:>+9.1%} {r['slow_E']:>+9.1%} {r['med']['sims']:>6.0f}/{r['med']['e2e']:<6.0f} | {t}")
MINRUNS = {"A0": 1}   # plan 3.6: >= 2 VALID runs for B/C/D, >= 1 for the A0 control
for v, r in res.items():
    if r["runs"] < MINRUNS.get(v, 2): print(f"DISQUALIFIED {v}: {r['runs']} valid run(s) < {MINRUNS.get(v, 2)}")
ok = {v: r for v, r in res.items() if r["runs"] >= MINRUNS.get(v, 2) and all(
      d["p95"] <= 75 and d["thr"] <= 5 and d["max"] < 95 and d["ge100"] == 0 for d in r["th"].values())}
for v in res:
    if v not in ok and res[v]["runs"] >= MINRUNS.get(v, 2): print(f"DISQUALIFIED {v}: package p95 > 75 C, throttles > 5, max >= 95 C or a minute >= 100 C on 01/03")
if "B" in res and res["B"]["slow_E"] > 0.15:
    print(f"PL1_BINDING_NOTE: B (EPP 64 = the BEFORE EPP) is still {res['B']['slow_E']:+.1%} vs BEFORE -> the 35 W PL1 / 1500 MHz cap binds; next test PL1 40 W (NOT in this plan)")
if not ok: print("AB_NO_WINNER keep A0 (the committed config)"); sys.exit(3)
best = min(r["slow_own"] for r in ok.values())
near = [v for v, r in ok.items() if r["slow_own"] - best <= 0.03]          # within 3 points: stability first
win = min(near, key=lambda v: (max(d["p95"] for d in ok[v]["th"].values()), sum(d["j"] for d in ok[v]["th"].values())))
line = f"AB_WINNER={win} vs_own_evening_A0={ok[win]['slow_own']:+.1%} vs_BEFORE={ok[win]['slow_E']:+.1%} (eligible: {sorted(ok)}; tie band: {sorted(near)})"
multi = len({EVE[v] for v in ok if v != "A0"} | ({1} if "A0" in ok else set())) > 1   # candidates span both evenings
cross = [v for v, r in ok.items() if r["cross"]]                                        # normalised against the OTHER evening
if cross or (multi and (drift is None or abs(drift) > 0.03)):
    print(f"CROSS_EVENING_UNRELIABLE: evening drift {'unknown' if drift is None else f'{drift:+.1%}'}; normalised against the other "
          f"evening's A0: {cross or 'none'} (> 3 points, a missing A0 control, or a cross-evening reference): "
          "the B/C vs D ranking spans two evenings -> OPERATOR DECIDES from the table (both rankings above)")
    print("AB_NEEDS_OPERATOR provisional " + line); sys.exit(4)
print(line)
```

### capstats.py (verbatim copy of talos-sysfs-power-caps Appendix A; that plan will be retired)

```python capstats
#!/usr/bin/env python3
# capstats.py <label> <minutes> <out-dir> [end_unix] [--no-rapl]
#   -> one CAPSTATS line per node; ONLY if every check passes: <out-dir>/stats-<label>.json + "CAPSTATS_OK".
#   --no-rapl: skip the RAPL families (for windows older than the RAPL series, enabled 2026-10-04).
# Window = [end - minutes, end]. Reads Prometheus through the apiserver proxy (kubectl get --raw).
# ABORTS (exit 2) if any metric family returns fewer than 3 nodes: an unscraped series must
# not read as "0 throttles" or "no heat" (docs/sops/verification-contents-not-shape.md).
import json, os, subprocess, sys, time, urllib.parse
args = [a for a in sys.argv[1:] if not a.startswith("--")]; norapl = "--no-rapl" in sys.argv
label, mins, outdir = args[0], int(args[1]), args[2]; end = int(args[3]) if len(args) > 3 else int(time.time())
if not os.path.isdir(outdir): print(f"CAPSTATS_ABORT out-dir {outdir!r} missing"); sys.exit(2)
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
if norapl: Q = {k: v for k, v in Q.items() if "rapl" not in k}
out, short = {}, []
for k, q in Q.items():
    raw = subprocess.run(["kubectl", "get", "--raw", P + urllib.parse.urlencode({"query": q, "time": end})],
                         capture_output=True, text=True)
    res = json.loads(raw.stdout)["data"]["result"] if raw.returncode == 0 else []
    if len(res) != 3: short.append(f"{k}:{len(res)}")
    for r in res: out.setdefault(r["metric"]["instance"].split(":")[0], {})[k] = round(float(r["value"][1]), 2)
for n in sorted(out): print(f"CAPSTATS {label} {n} " + " ".join(f"{k}={v}" for k, v in sorted(out[n].items())))
lowcov = [f"{n}:{k}={v}" for n, d in out.items() for k, v in d.items() if k.startswith("cov_") and v < 0.9]
if lowcov: print(f"CAPSTATS_ABORT sample coverage < 0.9 (window older than the series or a scrape gap): {lowcov}"); sys.exit(3)
if short: print(f"CAPSTATS_ABORT families without exactly 3 nodes: {short}"); sys.exit(2)
json.dump({"label": label, "end": end, "minutes": mins, "nodes": out}, open(f"{outdir}/stats-{label}.json", "w"), indent=1)
print(f"CAPSTATS_OK {label} -> {outdir}/stats-{label}.json")
```

### ab-run.sh

```bash ab-run
#!/bin/bash
# ab-run.sh <label>  -- ONE A/B CI run (run_in_background: true): sims 4 then e2e 3 at the fixed ref, exactly the
# 2026-10-04 BEFORE/AFTER protocol. Writes run-<label>.{start,end,log}, shards-<label>.json; last log line SUITES_DONE.
set -u; W=/private/tmp/powerab-talos-power-tuning-ab; L=$1
cd /Users/mu/code/cberg-home-nextgen || exit 2
test -s "$W/ci-ref" || { echo NO_CI_REF; exit 2; }
test -e "$W/run-$L.start" && { echo "LABEL_USED $L"; exit 2; }
# the CI gate must be the file recorded in plan 2.4 (edited often by other sessions): a changed gate = a changed
# experiment, refuse instead of measuring it
test "$(git hash-object scripts/ninth-banner-admit.py)" = "$(cat "$W/gate-hash" 2>/dev/null)" || { echo "GATE_CHANGED: scripts/ninth-banner-admit.py differs from $W/gate-hash"; exit 2; }
# one shard per node at a time, as in the 2026-10-04 BEFORE/AFTER runs (each shard alone on its node): the gate
# reads these for every tick THIS trigger runs (no other CI may run meanwhile, plan section 2.4)
export GATE_SECOND_POD_NODES= GATE_MAX_CPU_PER_NODE=1
date +%s > "$W/run-$L.start"
mise exec -- python3 "$W/ab-shards.py" "$L" > "$W/shards-$L.out" 2>&1 & C=$!
{ scripts/ninth-banner-test.sh "$(cat "$W/ci-ref")" sims 4; echo "sims rc=$?"
  scripts/ninth-banner-test.sh "$(cat "$W/ci-ref")" e2e 3; echo "e2e rc=$?"; } > "$W/run-$L.log" 2>&1
date +%s > "$W/run-$L.end"; echo SUITES_DONE >> "$W/run-$L.log"
wait $C; cat "$W/shards-$L.out"
```
