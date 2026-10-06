---
plan_id: node-thermal-calibration
component: talos
pr: null                              # no Renovate PR: operator-approved measurement (chat 2026-10-06), follow-up to F-6c7843e4
kind: infra
current: "all 3 nodes: RAPL PL1 35 W / PL2 55 W, EPP balance_power. nuc14-02 runs hotter than 01/03 under CI; unknown whether that is its WORKLOAD (CI placement) or its HARDWARE (cooler, paste, airflow)"
target: "no cluster change. A measured package-power-vs-temperature curve per node under a fixed synthetic load, and a rule-based verdict on whether nuc14-02's heat is explained by its workload"
update_type: n/a
risk: low                             # No config change, no reboot, no persistent object. One short-lived busybox pod per node
                                      # (default namespace, 100m CPU request, deleted by the tool in a finally block), a hot-abort at
                                      # 95 C inside the pod AND on the Mac, and the plan is exclusive so no CI or A/B load overlaps.
est_duration_min: 75                  # pre-checks 10 + per node (cool-down <= 20, baseline 120 s, 5 steps x 150 s, pod start/stop ~1 min)
                                      # ~16 min active = 3 nodes ~48 + cool-down slack. A repeat of one INCONCLUSIVE node (3.5) adds ~16 min.
needs_reboot: false
exclusive: true                       # any other live plan changes the heat the curve measures (CI shards, EPP/PL applies, reboots)
autonomy_override: human-gated        # SD-10/SD-11 would otherwise pre-approve a risk:low, capability_change:false plan for the
                                      # nightly. This one is an attended, operator-started measurement and must never be picked up.
touches:
  namespaces: [default, ci-runner]    # default: pod thermalcal-0N (transient). ci-runner: READ ONLY (the tool refuses to start/continues
                                      # only while no CI pod exists).
  resources:
    - "pod/thermalcal-01, pod/thermalcal-03, pod/thermalcal-02 (default, transient, one at a time, deleted by the tool)"
    - "sysfs READ ONLY via talosctl: /sys/class/powercap/intel-rapl:0*/energy_uj, /sys/class/thermal/thermal_zone0/temp, thermal_throttle/package_throttle_count"
  shared: [node-power-thermal, ci-runner-thermal-gate]
                                      # node-power-thermal: the pod puts up to 18 busy workers on ONE node for ~15 min.
                                      # ci-runner-thermal-gate: no CI may run meanwhile (pre-check 2.4 + the tool's own guard).
conflicts_with:
  - talos-power-tuning-ab             # changes EPP/PL on 01/03 and runs CI on them: the curve would be a mix of configs
  - talos-sysfs-power-caps            # its soak measures the current caps; synthetic load would pollute it
  - talos-linux-1.14.2                # rolling reboot
  - multus-macvlan-foundation         # talosctl apply-config on the same nodes
  - kube-prometheus-stack-91.9.0      # §4.3 reads Prometheus; a kps restart punches a hole in the control series (nightly:2026-10-08)
  - immich-machine-learning-3.2.4     # CPU/iGPU consumer on nuc14-03: its roll changes the heat mid-run
  - jellyfin-12.1                     # iGPU consumer on nuc14-01
  - jellyfin-config-rwo-migration     # iGPU consumer on nuc14-01
  - nextcloud-fleet-35.0.1            # backup/restore load and pod moves
security_ref: null
capability_change: false              # reads only; nothing the household notices changes
rollback_class: git-revert            # nothing persists on the cluster. The repo side (this plan file) reverts with git.
finding_refs:
  - F-6c7843e4                        # "BIOS/fan/paste check on nuc14-02's cooler first": this measures whether the cooler is the cause
review: ready-for-go@2026-10-06     # plan-reviewer-agent 2026-10-06 @0d673050: 0 blocking, 4 non-blocking fixes applied
status: executed                      # NOW run now:2026-10-06: THERMALCAL_VERDICT node02=HARDWARE-SUSPECT node03=WORKLOAD-EXPLAINED; controls PASS; numbers in F-6c7843e4 detail (DB)
window: "now:2026-10-06"   # ON-DEMAND NOW run 2026-10-06 (run-now.py stamp; was None)
premises:
  - id: nodes-on-talos-1.14
    why: "The sysfs paths and the talosctl read semantics were measured on v1.14.1 (kernel 6.18). Another minor invalidates them."
    run: kubectl get nodes -o jsonpath='{.items[*].status.nodeInfo.osImage}'
    expect_matches: '^Talos \(v1\.14\.[0-9]+\) Talos \(v1\.14\.[0-9]+\) Talos \(v1\.14\.[0-9]+\)$'
  - id: no-ci-in-flight
    why: "Any CI pod puts load on a node the curve measures. Zero pods in ci-runner at the start (the query counts the EMPTY `items` list: 1 = no pods; a populated namespace such as kube-system reads 0 and so does a failing kubectl, so an API error fails closed instead of reading as no CI); the tool re-checks every 10 s and marks the run INVALID if one appears."
    run: "kubectl get pods -n ci-runner -o json | grep -c '\"items\": \\[\\]'"
    expect_exact: "1"
  - id: no-capbench-or-thermalcal-pod
    why: "A leftover capbench or thermalcal pod (aborted earlier run) keeps burning CPU on one node. Zero before the first run."
    run: "kubectl get pods -n default -l 'app in (capbench,thermalcal)' --no-headers | wc -l | tr -d ' '"
    expect_exact: "0"
  - id: etcd-healthy
    why: "The apiserver serves the pod create/delete and the log stream; a sick etcd makes the abort path (force delete) unreliable."
    run: kubectl get --raw=/readyz/etcd
    expect_exact: "ok"
  - id: pkg-zone-01
    why: "thermal_zone0 must be x86_pkg_temp (the package sensor). The pod finds the zone by type and the tool reads zone0 over talosctl; another type means the temperature column is not the package."
    run: talosctl --nodes=192.168.55.11 read /sys/class/thermal/thermal_zone0/type
    expect_exact: "x86_pkg_temp"
  - id: pkg-zone-02
    why: same as pkg-zone-01, node 02
    run: talosctl --nodes=192.168.55.12 read /sys/class/thermal/thermal_zone0/type
    expect_exact: "x86_pkg_temp"
  - id: pkg-zone-03
    why: same as pkg-zone-01, node 03
    run: talosctl --nodes=192.168.55.13 read /sys/class/thermal/thermal_zone0/type
    expect_exact: "x86_pkg_temp"
  - id: node-temp-le-60c-01
    why: "Start condition: the package is at most 60 C (millidegrees: 0-60000) so the tool's wait to <= 55 C is short. A hotter node at plan start means something else is loading it: STOP."
    run: talosctl --nodes=192.168.55.11 read /sys/class/thermal/thermal_zone0/temp
    expect_matches: '^([0-9]{1,4}|[1-5][0-9]{4}|60000)$'
  - id: node-temp-le-60c-02
    why: same as node-temp-le-60c-01, node 02
    run: talosctl --nodes=192.168.55.12 read /sys/class/thermal/thermal_zone0/temp
    expect_matches: '^([0-9]{1,4}|[1-5][0-9]{4}|60000)$'
  - id: node-temp-le-60c-03
    why: same as node-temp-le-60c-01, node 03
    run: talosctl --nodes=192.168.55.13 read /sys/class/thermal/thermal_zone0/temp
    expect_matches: '^([0-9]{1,4}|[1-5][0-9]{4}|60000)$'
  - id: energy-readable-01
    why: "The whole measurement is energy_uj deltas. The package counter must be readable through talosctl on every node (one non-negative integer line)."
    run: "talosctl --nodes=192.168.55.11 read /sys/class/powercap/intel-rapl:0/energy_uj | grep -c '^[0-9][0-9]*$'"
    expect_exact: "1"
  - id: energy-readable-02
    why: same as energy-readable-01, node 02
    run: "talosctl --nodes=192.168.55.12 read /sys/class/powercap/intel-rapl:0/energy_uj | grep -c '^[0-9][0-9]*$'"
    expect_exact: "1"
  - id: energy-readable-03
    why: same as energy-readable-01, node 03
    run: "talosctl --nodes=192.168.55.13 read /sys/class/powercap/intel-rapl:0/energy_uj | grep -c '^[0-9][0-9]*$'"
    expect_exact: "1"
  - id: pl1-35w-01
    why: "All three nodes must run the SAME power cap, or the curves are not comparable. PL1 35 W read back."
    run: talosctl --nodes=192.168.55.11 read /sys/class/powercap/intel-rapl:0/constraint_0_power_limit_uw
    expect_exact: "35000000"
  - id: pl1-35w-02
    why: same as pl1-35w-01, node 02
    run: talosctl --nodes=192.168.55.12 read /sys/class/powercap/intel-rapl:0/constraint_0_power_limit_uw
    expect_exact: "35000000"
  - id: pl1-35w-03
    why: same as pl1-35w-01, node 03
    run: talosctl --nodes=192.168.55.13 read /sys/class/powercap/intel-rapl:0/constraint_0_power_limit_uw
    expect_exact: "35000000"
  - id: pl2-55w-01
    why: "Same comparability reason as pl1-35w-*: PL2 55 W on every node."
    run: talosctl --nodes=192.168.55.11 read /sys/class/powercap/intel-rapl:0/constraint_1_power_limit_uw
    expect_exact: "55000000"
  - id: pl2-55w-02
    why: same as pl2-55w-01, node 02
    run: talosctl --nodes=192.168.55.12 read /sys/class/powercap/intel-rapl:0/constraint_1_power_limit_uw
    expect_exact: "55000000"
  - id: pl2-55w-03
    why: same as pl2-55w-01, node 03
    run: talosctl --nodes=192.168.55.13 read /sys/class/powercap/intel-rapl:0/constraint_1_power_limit_uw
    expect_exact: "55000000"
  - id: ab-not-mid-variant
    why: "The A/B plan changes EPP on 01/03 per variant (balance_performance/96 during B/C/D). balance_power on cpu0 of node 01 and 03 = the A/B is not mid-variant (evening 2 not running); a different value means the config is not the committed one."
    run: talosctl --nodes=192.168.55.11 read /sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference
    expect_exact: "balance_power"
  - id: ab-not-mid-variant-03
    why: same as ab-not-mid-variant, node 03
    run: talosctl --nodes=192.168.55.13 read /sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference
    expect_exact: "balance_power"
  - id: ab-not-mid-variant-02
    why: same as ab-not-mid-variant, node 02 (never an A/B node, but its EPP is part of the comparison)
    run: talosctl --nodes=192.168.55.12 read /sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference
    expect_exact: "balance_power"
sops_refs:
  - docs/sops/ci-runner.md
  - docs/sops/monitoring.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-10-06"
---

# Node thermal calibration: is nuc14-02's heat its workload or its hardware?

## 1. Summary & why held

**Why.** `F-6c7843e4` records that nuc14-02 runs hotter than 01/03 and threw ~29k package throttles a day before the
power caps. CI shards used to land on it, so two explanations compete: (a) **workload**: it simply ran more or heavier
pods, or (b) **hardware**: its cooler, thermal paste or airflow is worse, so the SAME load gives a hotter package. The
finding's remedy ("BIOS/fan/paste check on nuc14-02's cooler first") is a physical step that costs an opened NUC. This
plan decides whether that step is warranted, by measuring all three nodes under an IDENTICAL, controlled load.

**Held** because it is an attended, exclusive, ~75 min measurement that must not share a run with anything that adds
heat. It changes nothing on the cluster. Operator GO recorded 2026-10-06 (chat). `autonomy_override: human-gated` keeps
the nightly from picking it up.

**What it does.** One busybox pod per node, one node at a time in the fixed order **01, 03, 02**. Per node:

1. wait until the package is <= 55 C (max 20 min, else the run is INVALID: a node that cannot cool is itself a result,
   recorded in `why_invalid`);
2. 120 s idle baseline;
3. stepped load of N = 2, 4, 8, 12, 18 workers, 150 s each (a worker is a `dd | sha256sum` loop: CPU-bound, no I/O);
4. the stats of each step are taken over its LAST 60 s (guard 5 s before the step ends), so the thermal transient of the
   step before it has settled.

Per step the tool records package W (RAPL `energy_uj` delta, wrap-safe), core W (`intel-rapl:0:0`), uncore W (package
minus core), mean and max package C, and the package throttle-count delta. Power is the independent variable: the three
nodes are compared at the SAME watts, not the same worker count.

**Hot-abort.** At >= 95 C (read inside the pod every second and on the Mac every second) the pod stops all workers and
the run ends. An abort is a RECORDED RESULT, not an error: the step is kept with its partial window, and the verdict
treats "aborts where a reference node completed" as hardware evidence.

### 1.3 Verdict rules (fixed BEFORE any data; `thermalcal-verdict.py` header repeats them)

Per node a least-squares line `C = a + s*W` over the steps that did not abort and have mean W >= 12 (>= 3 points).
`M` = matched power = min(30 W, lowest top-step W over all runs). node02 is compared against the median of
node01/node03; node03 against node01. `ratio = s_test / median(s_ref)`, `dT = (a+s*M)_test - median((a+s*M)_ref)`.

| verdict | rule | meaning |
|---|---|---|
| **HARDWARE-SUSPECT** | ratio >= 1.25, OR dT >= +8 C, OR it hot-aborts at a step a reference run completed | same watts, hotter package: the cooler/paste/airflow is the cause. Do the physical check. |
| **WORKLOAD-EXPLAINED** | ratio <= 1.15 AND dT <= +4 C AND no abort difference | at equal watts the node behaves like its siblings: its heat was what ran on it. Close the hardware branch of the finding. |
| **INCONCLUSIVE** | anything between | repeat once (3.5), then decide with the operator. |
| **INVALID** | fewer than 3 usable points | the run is not a result (never counted as either verdict). |

The thresholds come from the finding's history and the sensor resolution (1 C); the +4 C bound is the author's
addition (a node 4-8 C hotter at matched watts is worth a second run, not a conclusion).

**Limits.** One ambient temperature, one evening; fans are firmware-controlled (their speed is part of "hardware"). The
tool measures the package sensor, not the case. A single run per node can be wrong by a few C (room, rack position of
the neighbour): that is why the INCONCLUSIVE band exists. Package power is limited by PL1 35 W: the top steps may sit at
the cap on all nodes (then the compared W is the cap, and a hotter node at the cap IS the signal).

## 2. Pre-checks (in the NOW run; mutation-free)

From the repo root on the Mac mini, as `mu`, mise activated, talosctl v1.14.x client. Shell variables do not survive
between agent Bash calls: every block starts with the guard line. `W` holds only the tools and the result JSON (no secrets).
```bash
cd /Users/mu/code/cberg-home-nextgen
umask 077; export W=/private/tmp/thermalcal-node-thermal-calibration; mkdir -p "$W"; chmod 700 "$W"
for b in thermalcal thermalcal-verdict; do
  awk -v b="$b" '$0=="```python " b {f=1;next} /^```$/{f=0} f' runbooks/maintenance/plans/node-thermal-calibration.md > "$W/$b.py"
  python3 -c "import ast,sys; ast.parse(open(sys.argv[1]).read())" "$W/$b.py" && test -s "$W/$b.py" || echo "EXTRACT FAILED $b"
done
chmod 700 "$W"/thermalcal.py "$W"/thermalcal-verdict.py
python3 "$W/thermalcal.py" --selftest            # THERMALCAL_SELFTEST_OK
python3 "$W/thermalcal-verdict.py" --selftest    # THERMALCAL_VERDICT_SELFTEST_OK
for ip in 11 12 13; do python3 "$W/thermalcal.py" 192.168.55.$ip dry --out "$W" --dry | head -2; done
```
2.1 **Premises**: `.venv/bin/python3 runbooks/plan-premises.py node-thermal-calibration --require-premises` -> all PASS.
`no-ci-in-flight` failing = CI is running: wait (3.1 tells how to hold CI), do not override.

2.2 **Selftests and dry-runs** (the block above): both selftests print their OK token; each `--dry` prints
`THERMALCAL_DRY rc=0 pod/thermalcal-0N-dry created (server dry run)` and a `reads ok: zone_c=... ranges=(262143328850, 262143328850)` line.
`THERMALCAL_DRY_NOTE throttle counter unreadable` is informational (the throttle column becomes null).

2.3 **Cluster health**: 3 nodes `Ready`; `mise exec -- talosctl -n 192.168.55.11,192.168.55.12,192.168.55.13 etcd status`
-> 3 members, no learner, no ERRORS. Record the throttle counters before the first run (they are cumulative since boot):
```bash
for ip in 11 12 13; do echo "$ip $(talosctl --nodes=192.168.55.$ip read /sys/devices/system/cpu/cpu0/thermal_throttle/package_throttle_count)"; done | tee "$W/throttle-before.txt"
```

2.4 **CI hold.** The window's Step 0 (safe updates) may start CI shards or roll pods that heat a node. Run the premises
and this check AFTER Step 0 has settled. `kubectl get pods -n ci-runner -o json | grep -c '"items": \[\]'` must read `1` (empty namespace), and the
operator must not push to `the-ninth-banner` meanwhile (the push triggers CI). If CI is mandatory meanwhile, STOP and
re-plan: this measurement is never run with CI in flight.

## 3. Steps

### 3.1 Run the nodes sequentially: 01, 03, 02

Order: 01 and 03 first (references), 02 last (the test node: it has the most to lose from an early hot-abort that
fails the other two runs). Each run is ~16 min; the tool is long-running, so start it in the background (the agent
Bash call limit is 10 min) and wait for its completion notification. Before each node re-check CI (the tool does too):
```bash
cd /Users/mu/code/cberg-home-nextgen
export W=/private/tmp/thermalcal-node-thermal-calibration; test -d "$W" || { echo NO_W; exit 1; }
test "$(kubectl get pods -n ci-runner -o json | grep -c '"items": \[\]')" = 1 || { echo CI_PRESENT; exit 1; }
python3 "$W/thermalcal.py" 192.168.55.11 run1 --out "$W" > "$W/log-01-run1.txt" 2>&1    # run_in_background
```
Then the same for `192.168.55.13` (03) and `192.168.55.12` (02), label `run1`. Do not start the next node before the
previous run's `THERMALCAL ...` line (or `THERMALCAL_INVALID`) is printed and its pod is gone
(`kubectl get pods -n default -l app=thermalcal --no-headers | wc -l` -> 0).

3.2 **Reading the result line.** `THERMALCAL node=... status=OK` = a valid run. `status=HOT_ABORT` = a recorded result
(the run ends at the abort step, valid if >= 3 usable points exist for the verdict). `THERMALCAL_INVALID ... why=`: the
reason is in the line (`package never cooled`, `CI pod appeared`, `pod never started`, a missing marker). An INVALID run
is repeated ONCE (new label `run2`) after fixing the cause; a second INVALID on the same node is reported as a finding
of its own (a node that cannot cool to 55 C or keeps getting CI is itself the result).

3.3 **Verdict.**
```bash
python3 "$W/thermalcal-verdict.py" "$W"
```
Prints per-node idle and step tables, `VERDICT node02 ...`, `VERDICT node03 ...` and the final
`THERMALCAL_VERDICT node02=<verdict> node03=<verdict> matched_w=<W>`. Exit code 3 = INVALID.

3.4 **If node03 vs node01 is HARDWARE-SUSPECT** the reference pair is not homogeneous: node02's verdict is then
compared against a mixed reference. Report both and do not conclude on node02 alone; repeat 01 and 03 once (3.5).

3.5 **INCONCLUSIVE: repeat once.** Re-run the affected node(s) with label `run2` (the verdict script averages the runs
of a node). A second INCONCLUSIVE is reported as such with the table; the operator decides (physical check yes/no).
The extra time is ~16 min per node: stay inside the on-demand ceiling and finish by 02:45 Europe/Berlin (the nightly starts 03:30).

### 3.6 Close-out (DB only for the numbers)

Per-run numbers (watts, temperatures, throttle deltas) are NOT committed anywhere: the repo is public and they describe
exposure on a specific node. They go to the finding's detail in sweep_history Postgres (source the DSN in a SEPARATE
Bash call from any `git commit`):
```bash
cd /Users/mu/code/cberg-home-nextgen
export W=/private/tmp/thermalcal-node-thermal-calibration
source runbooks/lib/sweep-pg-dsn.sh && sweep_pg_dsn_up && .venv/bin/python3 runbooks/policy-cli.py finding show F-6c7843e4 > "$W/finding-before.txt"; sweep_pg_dsn_down
```
`finding detail --detail-file` REPLACES `security_detail`: extract the existing text from `finding-before.txt` (the lines
after `--- security_detail ...`, 2-space indent stripped), write `existing + "\n\n" + new section` (date, the verdict line,
the per-node tables from 3.3, the throttle deltas vs `throttle-before.txt`) to `$W/detail-new.txt`, check it contains
the old text, then:
```bash
source runbooks/lib/sweep-pg-dsn.sh && sweep_pg_dsn_up && .venv/bin/python3 runbooks/policy-cli.py finding detail F-6c7843e4 --plan node-thermal-calibration --detail-file "$W/detail-new.txt"; sweep_pg_dsn_down
```
Give the operator a summary table (node, idle W/C, slope C/W, C at matched W, throttle delta, verdict). The plan's
execution notes carry ONLY the aggregate verdict token, nothing numeric. Then `rm -rf "$W"` (mode-700 scratch, no secrets,
but it is measurement data that now lives in the DB).

## 4. Verification

**4.1 CONTENTS ASSERTION: every node's result file holds real measurements, not an empty shell.** For each node
`cal-0N-run1.json` has `valid: true` (or `abort` set with >= 3 usable steps), a `baseline` with a non-null `mean_w`, and
per step `samples >= 40` spanning >= 50 s (aborted steps: >= 3 samples). The verdict script prints per-step W/C: a step
whose W does not rise with N, or a package W of 0, means the load never ran (a gutted window is INVALID by construction:
the selftest proves it). `THERMALCAL_VERDICT` is only trusted if the per-node tables show W increasing across steps.
What failure prints: `THERMALCAL_INVALID ... why=` (tool) or `SKIPPED_INVALID_RUN` (verdict script).

**4.2 CONTENTS ASSERTION: nothing was left running and nothing was changed.** After the last run
`kubectl get pods -n default -l app=thermalcal --no-headers | wc -l` -> `0`; the PL1/PL2/EPP premises (`pl1-35w-*`, `pl2-55w-*`,
`ab-not-mid-variant*`) still PASS when re-run (`plan-premises.py node-thermal-calibration`), i.e. the run read sysfs only.

**4.3 Measurement controls** (the instrument and what else heated the nodes):
CONTROL: metric node_thermal_zone_temp - the Prometheus package temperature of each node over the run window matches the
tool's own `mean_c` per step within ~2 C (the tool reads the same zone over talosctl); a disagreement means the tool read a
different sensor.
CONTROL: metric node_rapl_package_joules_total - rate() over a step window equals the tool's `mean_w` for that step within
~10 % (two independent readers of the same counter).
CONTROL: metric node_rapl_core_joules_total - core W <= package W at every step (uncore = package - core is never negative).
CONTROL: metric node_cpu_package_throttles_total - the delta over the run equals the sum of the tool's per-step
`throttle_delta` plus idle drift; a throttle burst that the tool did not see means a step window hid it.
CONTROL: alertname CIRunnerThermalGateStalled - must not fire during the run (a stalled gate means CI tried to run).
CONTROL: alertname NodeCPUPackageHot - INFORMATIONAL: it may fire on the top steps; that is the load, not a failure.

## 5. Rollback

Nothing persists on the cluster. If a run must stop NOW (operator abort, unexpected alert, node unhealthy):
```bash
pkill -f thermalcal.py; kubectl delete pod -n default -l app=thermalcal --grace-period=0 --force
kubectl get pods -n default -l app=thermalcal --no-headers | wc -l       # 0
```
The tool also force-deletes its pod in a `finally` block and on the 95 C hot-abort, and the pod itself carries
`activeDeadlineSeconds` (baseline + steps x hold + 180 s), so a dead Mac session cannot leave the load running past
~17 min. No sysfs value is written, no object is created beyond the pod, no reboot. Forward-only parts: none. The repo
side (this plan file) is `git revert`-able.

## 6. Interference notes

- **Exclusive**: no other live plan may share the run. `talos-power-tuning-ab` currently carries a stale
  `window: "now:2026-10-06"` stamp for its evening 1; stamp THIS plan only after that window is cleared or released
  (`run-now.py` refuses two exclusive plans on one date), and never while the A/B runs on 01/03 (its variants change EPP/PL).
- **Timing**: run it AFTER both A/B evenings (the A/B plan changes EPP/PL on 01/03 and runs CI on them), on an evening with no
  `kube-prometheus-stack` nightly (conflicts_with), and finish by 02:45 Europe/Berlin. `ci-runner-exclude-node02` is already EXECUTED
  (its gate knob stays: it keeps CI off node 02 for the whole measurement).
- **CI** is the main interferer (3.1/2.4): the push of any commit to `the-ninth-banner` triggers shards that the thermal
  gate places on the nodes. The tool refuses to start with CI present and invalidates a run in which a CI pod appears.
- **Step 0 (safe updates) runs first in every NOW run**: its image pulls and pod restarts heat the nodes. Take the premises
  and the first run after it settles; a node that cannot reach 55 C within 20 min is INVALID, not hot-aborted.
- **Other tenants**: jellyfin/immich-ml roll or transcode on 01/03 would add heat (the plan conflicts with their plans;
  an unplanned transcode shows as a W step that does not follow N, visible in the tables).
- **Neighbours**: the three NUCs share a rack; a hot neighbour raises ambient. Sequential runs 01, 03, 02 put the test
  node last, i.e. in the warmest rack state: a conservative bias (against 02). Say so when reporting a SUSPECT verdict.
- **Load on the apiserver/etcd**: one pod create/delete and one log stream per node. Negligible.
- **Throttle counters** are cumulative; compare against `throttle-before.txt`, never absolute.

## Appendix - scripts (extracted by §2; selftests and server dry-runs 2026-10-06)

### thermalcal.py

```python thermalcal
#!/usr/bin/env python3
# thermalcal.py <node-ip> <label> --out DIR [--dry] [--selftest]
# Stepped-load thermal calibration of ONE node: package W (RAPL) vs package C (x86_pkg_temp) at N busy
# workers = 2,4,8,12,18 (150 s each, after a 120 s idle baseline). A hot-abort is a recorded result.
# Safety (as capbench.py): in-pod 1 s watchdog at 95 C (works if the Mac dies; no zone -> exit 3 before any
# load); Mac-side abort at 95 C; force-delete in finally; refuses to start a node >= 80 C; one-node nodeSelector;
# transient pod in default; busybox:1.38 as nobody. Before the pod: waits for the package <= 55 C (max 20 min).
# Run it with Bash run_in_background: one node takes ~16 min + the wait (the Bash timeout is 10 min).
import argparse, json, re, signal, subprocess, sys, threading, time
from datetime import datetime, timezone

NODES = {"192.168.55.11": "k8s-nuc14-01", "192.168.55.12": "k8s-nuc14-02", "192.168.55.13": "k8s-nuc14-03"}
HOT_ABORT_C, WIN_S, GUARD_S = 95, 60, 5
PKG, CORE = "/sys/class/powercap/intel-rapl:0", "/sys/class/powercap/intel-rapl:0:0"
THR = "/sys/devices/system/cpu/cpu0/thermal_throttle/package_throttle_count"

POD_SH = r'''Z=""
for z in /sys/class/thermal/thermal_zone*; do [ "$(cat $z/type 2>/dev/null)" = x86_pkg_temp ] && Z=$z/temp; done
[ -n "$Z" ] && [ "$(cat $Z)" -gt 0 ] 2>/dev/null || { echo NO_PKG_ZONE; exit 3; }
trap 'trap - TERM; kill 0; exit 143' TERM
worker() { while :; do dd if=/dev/zero bs=1M count=64 2>/dev/null | sha256sum >/dev/null; done; }
hold() {
  s=$(date +%s); e=$((s + $2))
  while [ $(date +%s) -lt $e ]; do
    t=$(cat $Z)
    if [ "$t" -ge __HOT__ ]; then echo "POD_HOT_ABORT step=$1 temp_mc=$t after_s=$(( $(date +%s) - s ))"; trap - TERM; kill 0; exit 4; fi
    sleep 1
  done
}
echo STEP_START 0; hold 0 __BASE__
for n in __STEPS__; do
  pids=""
  for i in $(seq $n); do worker & pids="$pids $!"; done
  echo STEP_START $n
  hold $n __HOLD__
  kill $pids 2>/dev/null; wait
  echo STEP_END $n
done
echo CAL_DONE
'''


def window_stats(samples, t0, hold, rngs, partial_until=None):
    """Mean W / C over the last WIN_S s of a step (less GUARD_S). samples = (t, c, e_pkg, e_core|None, thr|None)."""
    lo, hi = t0 + hold - WIN_S - GUARD_S, t0 + hold - GUARD_S
    if partial_until is not None:
        lo, hi = max(t0, partial_until - WIN_S), partial_until
    ws = [s for s in samples if lo <= s[0] <= hi]
    need_n, need_span = (3, 2) if partial_until is not None else (40, 50)
    if len(ws) < need_n or ws[-1][0] - ws[0][0] < need_span:
        return None
    def watts(i, rng):
        e0, e1 = ws[0][i], ws[-1][i]
        return (e1 - e0 + (rng if e1 < e0 else 0)) / 1e6 / (ws[-1][0] - ws[0][0])
    w = watts(2, rngs[0])
    cw = watts(3, rngs[1]) if rngs[1] and all(s[3] is not None for s in ws) else None
    ts = [s for s in samples if s[4] is not None and t0 <= s[0] <= t0 + hold]
    return {"mean_w": round(w, 2), "core_w": None if cw is None else round(cw, 2),
            "uncore_w": None if cw is None else round(w - cw, 2),
            "mean_c": round(sum(s[1] for s in ws) / len(ws), 2), "max_c": round(max(s[1] for s in ws), 2),
            "throttle_delta": (ts[-1][4] - ts[0][4]) if len(ts) >= 2 else None, "samples": len(ws)}


def build_result(samples, starts, steps, base, hold, rngs, abort, done):
    out, problems = [], []
    for n in [0] + steps:
        if n not in starts:
            if not abort:
                problems.append(f"step {n} never started")
            continue
        h = base if n == 0 else hold
        ab = bool(abort and abort["step"] == n)
        st = window_stats(samples, starts[n], h, rngs, abort["t"] if ab else None)
        if st is None and ab:
            continue
        if st is None:
            problems.append(f"step {n}: too few samples in its measurement window")
            continue
        st.update({"n": n, "aborted": ab})
        out.append(st)
    if not abort and not done:
        problems.append("no CAL_DONE marker and no abort")
    return out, problems


def selftest():
    import random
    random.seed(7)
    rng = 262143328850
    steps, base, hold = [2, 4, 8], 100, 100
    def synth(drop_after=None, wrap=True):
        S, starts, t, e = [], {}, 1000.0, rng - 30_000_000 if wrap else 5_000_000
        plan = [(0, base, 8.0)] + [(n, hold, 8.0 + 2.5 * n) for n in steps]
        for n, h, p in plan:
            starts[n] = t
            for i in range(h):
                if drop_after and n == drop_after[0] and i >= drop_after[1]:
                    return S, starts
                e += p * 1e6 * 1.0
                if e >= rng: e -= rng
                S.append((t, 50 + 0.8 * p + random.random() * 0.2, int(e), None, 100 + n))
                t += 1.0
        return S, starts
    S, starts = synth()
    res, prob = build_result(S, starts, steps, base, hold, (rng, None), None, True)
    assert not prob, prob
    want = {0: 8.0, 2: 13.0, 4: 18.0, 8: 28.0}
    for r in res:
        assert abs(r["mean_w"] - want[r["n"]]) < 0.15, (r, want[r["n"]])
        assert abs(r["mean_c"] - (50 + 0.8 * want[r["n"]])) < 0.5, r
    S2 = [s for s in S if not (starts[4] + 20 < s[0] < starts[4] + 99)]
    _, prob = build_result(S2, starts, steps, base, hold, (rng, None), None, True)
    assert any("step 4" in p for p in prob), "a step with a gutted window must be reported"
    _, prob = build_result(S, starts, steps, base, hold, (rng, None), None, False)
    assert any("CAL_DONE" in p for p in prob), "a run without CAL_DONE and abort must be invalid"
    S3, st3 = synth(drop_after=(4, 70))
    ab = {"step": 4, "t": S3[-1][0]}
    res, prob = build_result(S3, {k: v for k, v in st3.items()}, steps, base, hold, (rng, None), ab, False)
    assert not prob, prob
    assert res[-1]["n"] == 4 and res[-1]["aborted"], res[-1]
    S4, st4 = synth(drop_after=(4, 12))
    res, prob = build_result(S4, st4, steps, base, hold, (rng, None), {"step": 4, "t": S4[-1][0]}, False)
    assert not prob and res[-1]["n"] == 4 and res[-1]["aborted"], (res, prob)
    S5, st5 = synth(drop_after=(4, 1))
    res, prob = build_result(S5, st5, steps, base, hold, (rng, None), {"step": 4, "t": S5[-1][0]}, False)
    assert not prob and res[-1]["n"] == 2, "an abort within the first second of a step is recorded without a window"
    print("THERMALCAL_SELFTEST_OK")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ip"); ap.add_argument("label")
    ap.add_argument("--out", default="."); ap.add_argument("--dry", action="store_true")
    ap.add_argument("--steps", default="2,4,8,12,18"); ap.add_argument("--hold", type=int, default=150)
    ap.add_argument("--base", type=int, default=120); ap.add_argument("--wait-max", type=int, default=1200)
    ap.add_argument("--start-max-c", type=int, default=55)
    a = ap.parse_args()
    for s in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        signal.signal(s, lambda *_: sys.exit(1))
    ip, node = a.ip, NODES[a.ip]
    steps = [int(x) for x in a.steps.split(",")]
    if not re.fullmatch(r"[a-z0-9]{1,8}", a.label) or not all(1 <= n <= 18 for n in steps):
        raise SystemExit("THERMALCAL_ERROR bad label or steps")
    if not a.dry and (a.hold < 80 or a.base < 80):
        raise SystemExit("THERMALCAL_ERROR hold/base < 80 s leaves no 60 s measurement window")
    name = f"thermalcal-{node[-2:]}-{a.label}"
    rd = lambda p: int(subprocess.check_output(["talosctl", "-n", ip, "read", p], text=True).strip())
    def rd_opt(p):
        try: return rd(p)
        except Exception: return None
    def zone():
        for z in range(16):
            r = subprocess.run(["talosctl", "-n", ip, "read", f"/sys/class/thermal/thermal_zone{z}/type"], capture_output=True, text=True)
            if r.returncode: break
            if r.stdout.strip() == "x86_pkg_temp": return f"/sys/class/thermal/thermal_zone{z}/temp"
        raise SystemExit("THERMALCAL_ERROR no x86_pkg_temp thermal zone")
    ZONE = zone()
    total = a.base + len(steps) * a.hold
    script = (POD_SH.replace("__HOT__", str(HOT_ABORT_C * 1000)).replace("__BASE__", str(a.base))
              .replace("__HOLD__", str(a.hold)).replace("__STEPS__", " ".join(map(str, steps))))
    pod = {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": name, "namespace": "default", "labels": {"app": "thermalcal"}},
           "spec": {"nodeSelector": {"kubernetes.io/hostname": node}, "restartPolicy": "Never",
                    "activeDeadlineSeconds": total + 180, "terminationGracePeriodSeconds": 0,
                    "securityContext": {"runAsNonRoot": True, "runAsUser": 65534, "seccompProfile": {"type": "RuntimeDefault"}},
                    "containers": [{"name": "cal", "image": "docker.io/library/busybox:1.38", "command": ["sh", "-c", script],
                                    "resources": {"requests": {"cpu": "100m", "memory": "32Mi"}, "limits": {"memory": "96Mi"}},
                                    "securityContext": {"allowPrivilegeEscalation": False, "readOnlyRootFilesystem": True,
                                                        "capabilities": {"drop": ["ALL"]}}}]}}
    k = lambda *x, **kw: subprocess.run(["kubectl", *x], text=True, capture_output=True, **kw)
    DEL = ["delete", "pod", "-n", "default", name, "--ignore-not-found", "--grace-period=0", "--force", "--wait=false"]
    ci_pods = lambda: (lambda r: len(r.stdout.split()) if r.returncode == 0 else 99)(k("get", "pods", "-n", "ci-runner", "-o", "name"))  # kubectl failure reads as CI present (fail closed)
    phase = lambda: k("get", "pod", "-n", "default", name, "-o", "jsonpath={.status.phase}").stdout
    rngs = (rd(PKG + "/max_energy_range_uj"), rd_opt(CORE + "/max_energy_range_uj"))
    if a.dry:
        r = k("apply", "--dry-run=server", "-f", "-", input=json.dumps(pod))
        print(f"THERMALCAL_DRY rc={r.returncode} {r.stdout.strip() or r.stderr.strip()}")
        print(f"reads ok: zone_c={rd(ZONE) / 1000:.0f} e_pkg={rd(PKG + '/energy_uj')} e_core={rd_opt(CORE + '/energy_uj')} thr={rd_opt(THR)} ranges={rngs}")
        if rd_opt(THR) is None: print("THERMALCAL_DRY_NOTE throttle counter unreadable (informational column will be null)")
        sys.exit(r.returncode)
    result = {"node": node, "label": a.label, "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "cfg": {"steps": steps, "hold_s": a.hold, "base_s": a.base}, "start_c": None, "wait_s": 0,
              "baseline": None, "steps": [], "abort": None, "valid": False, "why_invalid": ""}
    def finish(code):
        path = f"{a.out}/cal-{node[-2:]}-{a.label}.json"
        open(path, "w").write(json.dumps(result, indent=1) + "\n")
        b = result["baseline"] or {}
        status = "INVALID" if not result["valid"] else ("HOT_ABORT" if result["abort"] else "OK")
        print(f"THERMALCAL{'' if result['valid'] else '_INVALID'} node={node} label={a.label} status={status} start_c={result['start_c']} "
              f"base_w={b.get('mean_w')} base_c={b.get('mean_c')} steps=" +
              ",".join(f"{s['n']}:{s['mean_w']}W/{s['mean_c']}C" for s in result["steps"] if s["n"]) +
              f" abort={result['abort']} why={result['why_invalid'] or '-'} file={path}")
        sys.exit(code)
    c0 = rd(ZONE) / 1000
    result["start_c"] = c0
    if c0 >= 80:
        result["why_invalid"] = f"node already {c0:.0f} C at start (>= 80): something else is loading it"; finish(2)
    if ci_pods():
        result["why_invalid"] = "CI pods exist in ci-runner at start (the calibration needs the cluster free of CI)"; finish(2)
    w0 = time.time()
    while rd(ZONE) / 1000 > a.start_max_c:
        if time.time() - w0 > a.wait_max:
            result["why_invalid"] = f"package never cooled to <= {a.start_max_c} C in {a.wait_max} s"; result["wait_s"] = int(time.time() - w0); finish(2)
        time.sleep(10)
    result["wait_s"] = int(time.time() - w0)
    ev = {"starts": {}, "done": None, "pod_hot": None, "no_zone": None}
    proc = None; samples = []; mac_hot = None; ci_seen = False
    try:
        r = k("apply", "-f", "-", input=json.dumps(pod))
        if r.returncode:
            result["why_invalid"] = f"kubectl apply: {r.stderr.strip()}"; finish(2)
        for _ in range(240):
            if phase() in ("Running", "Succeeded", "Failed"): break
            time.sleep(1)
        else:
            result["why_invalid"] = "pod never started (image pull?)"; finish(2)
        proc = subprocess.Popen(["kubectl", "logs", "-f", "-n", "default", name], stdout=subprocess.PIPE, text=True)
        def reader():
            for line in proc.stdout:
                now, line = time.time(), line.strip()
                m = re.fullmatch(r"STEP_START (\d+)", line)
                if m: ev["starts"][int(m.group(1))] = now
                elif line == "CAL_DONE": ev["done"] = now
                elif line.startswith("POD_HOT_ABORT"): ev["pod_hot"] = (now, line)
                elif line.startswith("NO_PKG_ZONE"): ev["no_zone"] = now
        threading.Thread(target=reader, daemon=True).start()
        t0 = time.time(); n_tick = 0; ph = ""
        while time.time() - t0 < total + 150:
            now = time.time()
            c = rd(ZONE) / 1000
            samples.append((now, c, rd(PKG + "/energy_uj"), rd_opt(CORE + "/energy_uj") if rngs[1] else None,
                            rd_opt(THR) if n_tick % 5 == 0 else None))
            n_tick += 1
            if c >= HOT_ABORT_C:
                mac_hot = (now, c); k(*DEL); break
            if ev["done"] or ev["pod_hot"] or ev["no_zone"]: break
            if n_tick % 10 == 0:
                ci_seen = ci_seen or bool(ci_pods())
                ph = phase()
                if ph in ("Succeeded", "Failed"): time.sleep(3); break
            time.sleep(max(0.0, 1.0 - (time.time() - now)))
    finally:
        k(*DEL)
        if proc: proc.kill()
    abort = None
    if ev["pod_hot"]:
        m = re.search(r"step=(\d+) temp_mc=(\d+) after_s=(\d+)", ev["pod_hot"][1])
        abort = {"by": "pod", "step": int(m.group(1)), "after_s": int(m.group(3)), "temp_c": int(m.group(2)) / 1000, "t": ev["pod_hot"][0]}
    elif mac_hot:
        cur = max(ev["starts"], key=lambda n: ev["starts"][n]) if ev["starts"] else 0
        abort = {"by": "mac", "step": cur, "after_s": int(mac_hot[0] - ev["starts"].get(cur, mac_hot[0])), "temp_c": mac_hot[1], "t": mac_hot[0]}
    if ev["no_zone"]:
        result["why_invalid"] = "pod found no x86_pkg_temp zone"; finish(2)
    res, problems = build_result(samples, ev["starts"], steps, a.base, a.hold, rngs, abort, bool(ev["done"]))
    if abort: result["abort"] = {k2: v for k2, v in abort.items() if k2 != "t"}
    result["baseline"] = next((s for s in res if s["n"] == 0), None)
    result["steps"] = res
    if not result["baseline"] and not abort: problems.append("no baseline window")
    if ci_seen: problems.append("a CI pod appeared in ci-runner during the run (load not ours)")
    result["valid"] = not problems
    result["why_invalid"] = "; ".join(problems)
    finish(0 if result["valid"] else 2)


if __name__ == "__main__":
    selftest() if "--selftest" in sys.argv else main()
```

### thermalcal-verdict.py

```python thermalcal-verdict
#!/usr/bin/env python3
# thermalcal-verdict.py <DIR> | --selftest      DIR holds cal-01-*.json, cal-02-*.json, cal-03-*.json (thermalcal.py output).
# Fixed BEFORE any data (plan §1.3). Per node: least-squares line C = a + s*W over the steps with mean W >= 12
# that did not hot-abort (>= 3 points per run); several runs of a node are averaged (a, s). matched W =
# min(30, lowest top-step W of any run of any node). node02 is compared with the median of node01/node03,
# node03 with node01:   ratio = s_test / median(s_ref);   dT = (a+s*M)_test - median((a+s*M)_ref).
#   HARDWARE-SUSPECT   ratio >= 1.25  OR  dT >= +8 C  OR  it hot-aborts at a step some reference run completed
#   WORKLOAD-EXPLAINED ratio <= 1.15  AND dT <= +4 C  AND no such abort difference
#   INCONCLUSIVE       anything between (repeat once, plan 3.5)      INVALID: fewer than 3 usable points
import glob, json, statistics, sys

MIN_W, MAX_M, R_SUSPECT, R_OK, DT_SUSPECT, DT_OK = 12.0, 30.0, 1.25, 1.15, 8.0, 4.0


def fit(points):
    n = len(points); mx = sum(p[0] for p in points) / n; my = sum(p[1] for p in points) / n
    sxx = sum((p[0] - mx) ** 2 for p in points)
    if sxx <= 0: return None
    s = sum((p[0] - mx) * (p[1] - my) for p in points) / sxx
    return my - s * mx, s


def node_metrics(runs):
    fits, tops, aborts, cleared = [], [], [], []
    for r in runs:
        pts = [(x["mean_w"], x["mean_c"]) for x in r["steps"] if x["n"] > 0 and not x["aborted"] and x["mean_w"] >= MIN_W]
        if r.get("abort"): aborts.append(r["abort"]["step"])
        done = [x["n"] for x in r["steps"] if x["n"] > 0 and not x["aborted"]]
        cleared.append(max(done) if done else 0)
        f = fit(pts) if len(pts) >= 3 else None
        if f and f[1] > 0:
            fits.append(f); tops.append(max(p[0] for p in pts))
    return {"fits": fits, "tops": tops, "aborts": aborts, "cleared": cleared, "runs": len(runs)}


def verdict(test, refs, M):
    abort_diff = any(k > 0 and any(c >= k for r in refs for c in r["cleared"]) for k in test["aborts"])
    if abort_diff:
        return "HARDWARE-SUSPECT", {"why": f"hot-abort at step {min(test['aborts'])} where a reference run completed it"}
    if not test["fits"] or not all(r["fits"] for r in refs):
        return "INVALID", {"why": "fewer than 3 usable points (W >= 12, not aborted) in a run of the node or of its reference"}
    avg = lambda m: (sum(f[0] for f in m["fits"]) / len(m["fits"]), sum(f[1] for f in m["fits"]) / len(m["fits"]))
    a, s = avg(test); ra = [avg(r) for r in refs]
    ref_s = statistics.median(x[1] for x in ra); ref_t = statistics.median(x[0] + x[1] * M for x in ra)
    ratio, dT = s / ref_s, (a + s * M) - ref_t
    d = {"slope": round(s, 3), "ref_slope": round(ref_s, 3), "ratio": round(ratio, 3), "dT_matched": round(dT, 2), "matched_w": M}
    if ratio >= R_SUSPECT or dT >= DT_SUSPECT: return "HARDWARE-SUSPECT", d
    if ratio <= R_OK and dT <= DT_OK: return "WORKLOAD-EXPLAINED", d
    return "INCONCLUSIVE", d


def evaluate(by_node):
    m = {n: node_metrics(r) for n, r in by_node.items()}
    tops = [t for n in m.values() for t in n["tops"]]
    M = round(min([MAX_M] + tops), 1) if tops else None
    if M is None or M < MIN_W: return {"matched_w": M, "02": ("INVALID", {"why": "no usable points"}), "03": ("INVALID", {"why": "no usable points"})}
    return {"matched_w": M, "02": verdict(m["02"], [m["01"], m["03"]], M), "03": verdict(m["03"], [m["01"]], M)}


def load(d):
    by = {"01": [], "02": [], "03": []}
    for p in sorted(glob.glob(f"{d}/cal-0[123]-*.json")):
        r = json.load(open(p))
        if r.get("valid"): by[r["node"][-2:]].append(r)
        else: print(f"SKIPPED_INVALID_RUN {p}: {r.get('why_invalid')}")
    for n, v in by.items():
        if not v: raise SystemExit(f"THERMALCAL_VERDICT_ERROR no valid run for node {n}")
    return by


def report(by, res):
    for n in ("01", "03", "02"):
        for r in by[n]:
            b = r["baseline"] or {}
            print(f"node{n} {r['label']}: start {r['start_c']} C, idle {b.get('mean_w')} W (core {b.get('core_w')}, uncore {b.get('uncore_w')}) {b.get('mean_c')} C"
                  + (f", ABORT {r['abort']}" if r.get("abort") else ""))
            for x in r["steps"]:
                if x["n"]: print(f"   N={x['n']:>2}  {x['mean_w']:>6} W  mean {x['mean_c']:>5} C  max {x['max_c']:>5} C  throttle+{x['throttle_delta']}{'  ABORTED' if x['aborted'] else ''}")
    for n in ("02", "03"):
        v, d = res[n]
        print(f"VERDICT node{n} {v} {json.dumps(d)}")
    print(f"THERMALCAL_VERDICT node02={res['02'][0]} node03={res['03'][0]} matched_w={res['matched_w']}")


def selftest():
    def run(n, slope, off, ws=(8, 13, 20, 28, 35), abort=None, label="r1"):
        steps = [{"n": 0, "mean_w": 8.0, "mean_c": 45 + 0.8 * 8 + off, "max_c": 0, "aborted": False}]
        for i, w in zip((2, 4, 8, 12, 18), ws):
            if abort and i >= abort: break
            steps.append({"n": i, "mean_w": float(w), "mean_c": 40 + off + slope * w, "max_c": 0, "aborted": False, "throttle_delta": 0})
        return {"node": f"k8s-nuc14-{n}", "label": label, "valid": True, "start_c": 50, "baseline": steps[0], "steps": steps,
                "abort": {"step": abort, "by": "pod"} if abort else None}
    base = {"01": [run("01", 0.8, 0)], "03": [run("03", 0.85, 3)]}
    def go(n2):
        res = evaluate({**base, "02": n2}); return res["02"][0], res
    assert go([run("02", 0.8, 1)])[0] == "WORKLOAD-EXPLAINED"
    assert go([run("02", 1.1, 0)])[0] == "HARDWARE-SUSPECT", "slope x1.33"
    assert go([run("02", 0.85, 9)])[0] == "HARDWARE-SUSPECT", "+9 C offset at matched W"
    assert go([run("02", 0.95, 2)])[0] == "INCONCLUSIVE", "slope x1.15-1.25, small offset"
    assert go([run("02", 0.85, 6)])[0] == "INCONCLUSIVE", "+6 C offset only"
    assert go([run("02", 0.8, 1, abort=12)])[0] == "HARDWARE-SUSPECT", "aborts where the others complete"
    assert go([run("02", 0.8, 1, ws=(8, 13, 20, 28, 35), abort=18), run("02", 0.8, 1, label="r2")])[0] == "HARDWARE-SUSPECT", "one aborted run is enough"
    assert go([run("02", 0.8, 1, ws=(8, 9, 10, 11, 11))])[0] == "INVALID", "no step >= 12 W: cannot be scored"
    two = {**base, "01": [run("01", 0.8, 0, abort=12)], "03": [run("03", 0.85, 3, abort=12)]}
    assert evaluate({**two, "02": [run("02", 0.8, 1, abort=12)]})["02"][0] != "HARDWARE-SUSPECT", "same abort step everywhere is not a difference"
    assert evaluate({**base, "02": [run("02", 0.8, 1, ws=(8, 13, 20, 24, 27))]})["matched_w"] == 27.0, "matched W follows the weakest top step"
    print("THERMALCAL_VERDICT_SELFTEST_OK")


if __name__ == "__main__":
    if "--selftest" in sys.argv: selftest()
    else:
        by = load(sys.argv[1]); res = evaluate(by); report(by, res)
        sys.exit(3 if "INVALID" in (res["02"][0], res["03"][0]) else 0)
```
