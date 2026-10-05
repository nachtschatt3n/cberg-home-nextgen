---
plan_id: ci-gate-primary-control-rework
component: ci-runner
pr: null                              # no Renovate PR: operator-requested backlog item (chat 2026-10-05)
kind: infra
current: "CI thermal gate admits by package temperature (browser first pod < 85 C 2-min avg / < 93 C 3-min peak, 2nd pod < 78/90 C on nuc14-01 only, cpu lane < 88/96 C, 2 cpu pods per node, brake >= 100 C)"
target: "Primary control = 1 CI pod per node (both lanes together) under the RAPL power cap; temperature only as a ~90 C backstop (brake), no per-lane temperature admission thresholds"
update_type: refactor
risk: medium                          # BACKLOG DRAFT - not ready for review-to-go. Medium because it rewrites the admission
                                      # policy the whole CI farm depends on, and the old thresholds were tuned by 6 commits
                                      # of live measurement on 2026-10-04.
est_duration_min: 60                  # edit + unit-test the gate 20, SOP 10, commit 5, one sims 4 + e2e 3 run on 01/03 25
needs_reboot: false                   # the gate rework itself is a Mac-side script. The OPTIONAL simpledrm kernel arg (§6)
                                      # DOES need a reboot and is NOT part of this plan's steps.
exclusive: false
touches:
  namespaces: [ci-runner]
  resources:
    - file/scripts/ninth-banner-admit.py
    - file/docs/sops/ci-runner.md
    - "pod/tnb-* (ci-runner, transient verification run)"
  shared: [ci-runner-thermal-gate, node-power-thermal, igpu-i915, monitoring]
depends_on:
  - talos-power-tuning-ab             # the power cap is the new PRIMARY control: its final PL1/PL2/tau/EPP must be live and
                                      # committed before the temperature thresholds are retired.
  - ci-runner-exclude-node02          # the rework keeps GATE_EXCLUDE_NODES; written against the post-exclusion file.
conflicts_with:
  - talos-sysfs-power-caps            # its 3.10 soak step edits GATE_OPEN_BELOW_C in the same file
  - kube-prometheus-stack-91.9.0      # the gate and the verification read Prometheus
security_ref: null
capability_change: false              # no new feature/route/permission/API/exposure: same CI, different admission control.
rollback_class: git-revert            # Mac-side script read fresh every tick: a revert is live on the next tick
finding_refs:
  - F-6c7843e4                        # FOLLOWS FROM it (talos-power-tuning-ab may close it with its commit; then this ref
                                      # points at a resolved row - re-file a ci-runner finding when this leaves backlog)
review: null
status: draft                         # BACKLOG: no window until talos-power-tuning-ab has executed and its numbers exist
window: null
premises:
  - id: power-tuning-decided
    why: "The rework assumes the RAPL cap bounds per-node CI heat, so the A/B decision must be TAKEN and RECORDED. talos-power-tuning-ab §3.7 commits a comment line naming that plan into the global sysfs patch for EVERY outcome (B/C/D: the variant header; A0/no winner: a 'variant A0 kept' line, render-neutral). Reviewer 2026-10-05: keying on a B/C/D header only would deadlock this plan when A0 wins. EXPECTED TO FAIL until the A/B has run."
    run: "grep -c '^# .*talos-power-tuning-ab' kubernetes/bootstrap/talos/patches/global/machine-sysfs-power.yaml"
    expect_matches: '^[1-9][0-9]*$'
  - id: exclusion-knob-present
    why: "Depends on ci-runner-exclude-node02; the rework keeps that knob unchanged."
    run: "grep '^EXCLUDE_NODES = ' scripts/ninth-banner-admit.py | wc -l | tr -d ' '"
    expect_exact: "1"
sops_refs:
  - docs/sops/ci-runner.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-10-05"
---

# CI gate: power cap + 1 pod per node as the primary control, temperature as backstop (BACKLOG DRAFT)

## 1. Summary & why held

**Status: backlog draft.** This plan records the design and the evidence; it is not ready for a window. It becomes
executable after `talos-power-tuning-ab` has committed its winner (premise `power-tuning-committed`).

**Problem with the current primary control.** The gate (`scripts/ninth-banner-admit.py`) decides by package
temperature: 85/93 °C for the first browser pod, 78/90 °C for a second one, 88/96 °C for the cpu lane. These
thresholds were tuned on 2026-10-04 at **64 W PL1/PL2**, when one shard's startup burst could take a node from
75 °C to 103 °C within two minutes. Temperature is a lagging signal, so the gate admitted on a cool reading and
the burst arrived afterwards. That is why it grew a second-pod tier, a per-node node list, a per-node cpu override,
a 300 s settle and a brake (5 commits in one day). Since the SysfsConfig caps (2026-10-04 23:17Z) the package cannot
sustain more than PL1 = 35 W. Measured in the AFTER CI run: max 1-min RAPL 18.6-20.1 W, package max 62-71 °C,
0 throttles on 01/03. The heat a node can produce is now bounded by the cap, not by how many shards the gate
lets in. The temperature thresholds now mostly add queueing. **Counter-evidence, stated:** F-6c7843e4 records nodes
reaching 96 °C INSIDE the PL2 window (~45-55 W for up to ~28 s) under an 18-thread synthetic load. That is
production-plus-burst heat, which a 90 °C backstop sits below. This design holds only if (a) the A/B winner shortens or
lowers that burst (variant D) or CI never reaches it (one shard per node drew <= ~20 W on 2026-10-04), and (b) nuc14-02,
the node that hits 96 °C in ~4 s, stays excluded. Otherwise the backstop fires on production bursts and looks like an
unexpected stall: re-check against the A/B numbers before leaving backlog.

**Proposed control (design to be finalised with the A/B numbers):**
1. **1 CI pod per node, both lanes combined** (`MAX_PER_NODE=1`, cpu lane folded in, `SECOND_POD_NODES` empty), with
   nuc14-02 still excluded (`GATE_EXCLUDE_NODES`). That gives 2 concurrent shards on 01/03. Bounded heat per node =
   production + one shard under the cap.
2. **The RAPL cap is the primary heat control** (values from `talos-power-tuning-ab`).
3. **Temperature only as backstop**: one per-node brake at **~90 °C** (1-min max), replacing the 85/78/88 °C
   admission thresholds and the 93/90/96 °C peak checks. Keep the 2+-nodes global hold.
4. Keep everything that is not about heat: fail-closed on missing data, the CPU/memory/i915 fit check, the CI CPU
   budget, oldest-first per lane, the host lock, `--status`, `--release-all`.

**Evidence still owed before this is executable** (from `talos-power-tuning-ab` §4.B): per-node package p95/max
under 1 shard at the chosen cap must stay <= ~80 °C with headroom to the 90 °C backstop. If 01 or 03 exceeds that
with ONE shard, this design is wrong (keep the thresholds).

## 2. Pre-checks
- Premises PASS (`plan-premises.py ci-gate-primary-control-rework --require-premises`).
- `git log -3 -- scripts/ninth-banner-admit.py`: read every change since `ci-runner-exclude-node02`; the file is edited often.
- `git status --porcelain scripts/ninth-banner-admit.py docs/sops/ci-runner.md` prints nothing.
- No CI run in flight (`scripts/ninth-banner-admit.py --status`: 0 gated pods, 0 CI pods on any node).

## 3. Steps (outline; to be made copy-pasteable when the plan leaves backlog)
3.1 Gate: replace the per-lane slot checks with ONE combined per-node count (browser + cpu pods <= 1) - do NOT express
it as `GATE_MAX_CPU_PER_NODE=0` next to the old check (`nc >= 0` is always true and would close the cpu lane for good);
clear `GATE_SECOND_POD_NODES` and the `GATE_CPU_MAX_OVERRIDE` default (`k8s-nuc14-02=1`); `GATE_BRAKE_C=90`. Remove the `OPEN_BELOW_C`/`SECOND_*`/`CPU_OPEN_BELOW_C`/`*_HOT_C`
admission checks from `closed_reason()` (or default them to 200 so they never bind, which is the smaller diff). An
anchored python edit, dry-tested on a scratch copy, as in `ci-runner-exclude-node02`.
3.2 SOP `docs/sops/ci-runner.md` §2b table rewritten (control = cap + 1 pod/node + 90 °C brake), Version History.
3.3 `git commit --only` the two files, verify the subject, push.

## 4. Verification (outline)
- CONTENTS ASSERTION: `--status` with one CI pod on a node shows that node `full (1/1 ...)` for BOTH lanes. Negative
  control: the pre-change gate shows the cpu lane `open` next to a browser pod.
- CONTENTS ASSERTION: a sims 4 + e2e 3 run at the A/B ref never has more than 1 CI pod per node at any sample
  (`kubectl get pods -n ci-runner -o wide` sampled every 15 s), and finishes.
- CONTROL: metric node_thermal_zone_temp - per-node p95/max during the run (`capstats.py`), must stay below the 90 °C
  backstop with >= 5 °C headroom on 01/03.
- CONTROL: metric node_cpu_package_throttles_total - ~0 during the run.
- Before leaving backlog: `capstats.py` must come from a durable copy (talos-power-tuning-ab's appendix carries it verbatim;
  the predecessor's scratch dir is deleted after its soak), and each absence gate (throttles ~0, alert not firing, "never
  >1 pod per node") needs a recorded reading that shows it CAN read non-zero (pre-change: 2 pods on nuc14-01 is possible).
- CONTROL: alertname CIRunnerThermalGateStalled - not firing.

## 5. Rollback
`git revert <sha>` of 3.3, push; the next tick reads the old thresholds. Per run: the old behaviour can be had with the
`GATE_*` env overrides documented in SOP §2b.

## 6. Interference notes

- **Depends on** `talos-power-tuning-ab` (the cap values) and `ci-runner-exclude-node02` (the knob it keeps).
- **talos-sysfs-power-caps 3.10** raises `GATE_OPEN_BELOW_C` 85 -> 88. That step becomes moot under this design. If 3.10
  has run first, this plan's edit must start from the 88 line.
- **Stable DRM card index - `initcall_blacklist` does NOT work here (reviewer finding 2026-10-05, re-measured).** This
  bullet first proposed `initcall_blacklist=simpledrm_platform_driver_init` as an Image Factory kernel arg. That would
  silently do nothing:
  - simpledrm is **built in** on Talos v1.14.1 / kernel 6.18 (`modules.builtin` lists
    `kernel/drivers/gpu/drm/sysfb/simpledrm.ko` on all nodes), so a module blacklist cannot stop it. The source macro
    `module_platform_driver(simpledrm_platform_driver)` (v6.18 `drivers/gpu/drm/sysfb/simpledrm.c`) suggests the
    initcall `simpledrm_platform_driver_init`.
  - BUT the Talos kernel is built with Clang LTO. `init/main.c` `initcall_blacklisted()` compares the blacklist
    entry against the initcall's SYMBOL name, and under `CONFIG_LTO_CLANG` that symbol is a generated stub. Live
    `/proc/kallsyms` on nuc14-03 has only `__initstub__kmod_simpledrm__722_922_simpledrm_platform_driver_init6`, with
    no plain `simpledrm_platform_driver_init`. The stub name embeds `__COUNTER__`/`__LINE__`, so it changes between
    kernel builds: a schematic pinned to it would break on the next Talos patch.
  - Facts that still stand: on nuc14-03, simpledrm takes DRM minor 0 and i915 gets card1. On 01/02, card0 is i915
    (sysfs `card0` -> i915; 02's full-boot dmesg has no simpledrm line; 01's ring buffer has rotated). Kernel args reach
    these nodes through the Image Factory schematic in `talosImageURL` (the live cmdline carries `i915.enable_guc=3`).
    01's dmesg is full of EDID messages, so something may be attached to its display output: "headless" is not certain.
  - `/dev/dri/by-path/pci-0000:00:02.0-card` is stable (present on 03), but SysfsConfig writes `/sys` paths, and every
    sysfs route to the GT files carries the `cardN` index. **Conclusion: keep the per-node iGPU patches** (premise-checked
    after every reboot/BIOS change), and re-check after the BIOS 0054 update whether 03 still loads simpledrm at all.
