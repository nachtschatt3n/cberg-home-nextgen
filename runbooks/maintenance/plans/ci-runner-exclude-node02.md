---
plan_id: ci-runner-exclude-node02
component: ci-runner
pr: null                              # no Renovate PR: operator-requested CI policy change (chat 2026-10-05)
kind: infra
current: "CI thermal gate (scripts/ninth-banner-admit.py @4534a467) admits CI shards onto all 3 nodes; nuc14-02 limited only by temperature + 1 cpu-lane pod"
target: "GATE_EXCLUDE_NODES (default k8s-nuc14-02): nuc14-02 takes no CI pod in either lane until its cooling is fixed"
update_type: refactor
risk: low                             # Mac-side admission script, no Flux object, no node/config change. The edit only
                                      # REMOVES a placement option; running pods are never touched by the gate. Instant
                                      # per-run override (GATE_EXCLUDE_NODES=) and a one-commit revert.
est_duration_min: 28                  # = the NIGHTLY VARIANT (§4.2): window-scheduler.py reads ONLY est_duration_min against
                                      # duration_min - STEP0_RESERVE_MIN (90 - 20 = 70 schedulable). Co-scheduled after
                                      # flux-fleet-0.60.0 (35): 35 + 28 = 63 <= 70. Breakdown: premises+pre-checks 6,
                                      # edit+parse+§4.1 gate 6, commit/push 4, §2.x/§4.1 re-reads 4, slack 8.
                                      # FULL variant (attended slot, §4.2 e2e run included): ~45-58 (the e2e run is 17-30).
needs_reboot: false
exclusive: false
touches:
  namespaces: [ci-runner]             # the verification e2e run (3 transient shard pods)
  resources:
    - file/scripts/ninth-banner-admit.py     # +EXCLUDE_NODES (5 lines) + 2-line check in closed_reason()
    - file/docs/sops/ci-runner.md            # version, one §2b row, one troubleshooting row, one history line
    - "pod/tnb-e2e-gpu-d3ae92f-* (ci-runner, transient, Job TTL 600 s)"
  shared: [ci-runner-thermal-gate, igpu-i915, monitoring]
                                      # ci-runner-thermal-gate: every CI run on the Mac uses the edited file from the
                                      # moment it is written (each tick is a fresh python process).
                                      # igpu-i915: the verification run puts 3 GPU shards on nuc14-01/03.
                                      # monitoring: the gate's input is Prometheus (node_thermal_zone_temp).
depends_on: []
conflicts_with:
  - talos-sysfs-power-caps            # its SOAK step 3.10 edits the SAME file (GATE_OPEN_BELOW_C 85 -> 88). Different
                                      # lines (both edits are anchored and dry-tested independently), but serialize them so
                                      # each one's premise reads the file the other left. It is awaiting-soak (now:2026-10-05).
  - kube-prometheus-stack-91.9.0      # the gate and §4 read Prometheus: a kps restart mid-verification closes every node
                                      # (fail-closed) and the run reads as "stuck", not as "excluded".
  - flux-distribution-2.9.6           # Flux control-plane change (window null today): never the same night as this plan's
                                      # Prometheus-read gate. ORDERING (not a conflict, because a conflicts_with entry would
                                      # forbid the chosen co-scheduling): in nightly:2026-10-06 flux-fleet-0.60.0 runs FIRST,
                                      # and this plan starts only after flux-fleet's health gate (§6).
security_ref: null
capability_change: false              # FALSE: no new feature, route, permission, API or exposure. It narrows WHERE the
                                      # existing best-effort CI may place a shard (one node fewer); production workloads
                                      # and the CI software are unchanged. CI loses ~1/3 of its slots (see §6).
rollback_class: git-revert            # one commit; the file is read fresh on every tick, so a revert is live on the next tick
finding_refs:
  - F-6c7843e4                        # "BIOS/fan/paste check on nuc14-02's cooler first": this keeps CI heat off that node
                                      # until the physical fix; shared with talos-sysfs-power-caps / talos-power-tuning-ab
review: ready-for-go@2026-10-05     # review fix applied per the reviewer's exact correction (nightly variant, §4.2/§6)
status: vetted
window: "nightly:2026-10-06"          # was PROPOSED nightly:2026-10-06 (03:30 Europe/Berlin = 01:30Z), i.e. after the
                                      # talos-sysfs-power-caps 24 h soak closes (>= 2026-10-05T23:17Z) and before the A/B.
                                      # Fallback (review-2 B1): nightly:2026-10-07. It can NOT join the A/B's NOW run (that plan is
                                      # exclusive and run-now checks all premises at preflight); the A/B evenings then shift a day.
premises:
  - id: soak-24h-recorded
    why: "talos-sysfs-power-caps' 24 h soak (capstats soak-24h, owed >= 2026-10-05T23:17Z) must be captured BEFORE this lands: capstats ends its window at 'now', so a later soak read would include the post-exclusion period (02 cooler, 01/03 + this plan's CI run hotter). The JSON exists only after a CAPSTATS_OK; read from the copy the predecessor's close-out puts into the A/B's dir (talos-sysfs-power-caps §5 Copy-out), because its own scratch dir is wiped afterwards. EXPECTED TO FAIL until the soak is taken and copied."
    run: "grep -c '\"label\": \"soak-24h\"' /private/tmp/powerab-talos-power-tuning-ab/stats-soak-24h.json"
    expect_exact: "1"
  - id: gate-has-no-exclusion-yet
    why: "The edit (exclude-edit.py) asserts the anchor shape and refuses a second run; a non-zero count means someone already added an exclusion knob - re-plan instead of stacking a second one."
    run: "grep 'EXCLUDE_NODES' scripts/ninth-banner-admit.py | wc -l | tr -d ' '"
    expect_exact: "0"
  - id: gate-closed-reason-anchor
    why: "exclude-edit.py inserts the check right after the first line of closed_reason(); the gate was edited 5x on 2026-10-04 by the ci-runner work. Exactly one anchor line = the shape the edit was dry-tested against."
    run: "grep '^def closed_reason(node, lane, req, temps, count, last, now, free, ci_req, brake):$' scripts/ninth-banner-admit.py | wc -l | tr -d ' '"
    expect_exact: "1"
  - id: gate-and-sop-clean
    why: "git commit --only commits the whole working-tree file: another session's uncommitted hunk in either file would ride along under this plan's subject."
    run: "git status --porcelain scripts/ninth-banner-admit.py docs/sops/ci-runner.md | wc -l | tr -d ' '"
    expect_exact: "0"
  - id: node02-is-a-gate-node
    why: "The default value names the node by hostname; the gate keys every decision on the Prometheus nodename. If the hostname changed the exclusion would silently exclude nothing (the §4.1 gate would also catch it)."
    run: "kubectl get node k8s-nuc14-02 -o jsonpath='{.metadata.name}'"
    expect_exact: "k8s-nuc14-02"
sops_refs:
  - docs/sops/ci-runner.md
  - docs/sops/application-update.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-10-05"
---

# CI runner: keep CI shards off k8s-nuc14-02 until its cooling is fixed

## 1. Summary & why held

**What changes.** The CI thermal gate (`scripts/ninth-banner-admit.py`, a Mac-side script ticked by every
`scripts/ninth-banner-test.sh` run; no Flux object) gets one new knob, `GATE_EXCLUDE_NODES`, which defaults to
`k8s-nuc14-02`. `closed_reason()` returns `excluded (GATE_EXCLUDE_NODES)` for such a node before any other check,
so neither the browser lane nor the cpu lane ever pins a shard there. Diff (dry-tested on a scratch copy
2026-10-05, `python3 -c 'import ast...'` parses):

```
+# Nodes that get NO CI pod in either lane (plan ci-runner-exclude-node02, 2026-10):
+# ... (3 comment lines)
+EXCLUDE_NODES = {n for n in os.environ.get("GATE_EXCLUDE_NODES", "k8s-nuc14-02").split(",") if n}
 ...
 def closed_reason(node, lane, req, temps, count, last, now, free, ci_req, brake):
     avg2, max3 = temps[node]
+    if node in EXCLUDE_NODES:
+        return "excluded (GATE_EXCLUDE_NODES)"
```
`docs/sops/ci-runner.md` gets the matching §2b row, the troubleshooting row "nuc14-02 never gets a CI pod" now
names the exclusion, a Version History line, a new `Version:`/`Last Updated:`, and the browser-slot totals in §1 and
the §2b "browser lane open when" row now read 3 (1 on 03, up to 2 on 01) instead of 4 (anchored, dry-tested).

**Why.** Measured during `talos-sysfs-power-caps` (2026-10-04/05): an 18-thread benchmark hot-aborted at 96 °C
on nuc14-02 within ~4 s at the new 35/55 W cap, versus ~25-30 s on nuc14-03. Over 7 days nuc14-02 logged
64,970 package throttles against 741 (01) and 56 (03), and 56 minutes at >= 100 °C. That points at a cooler defect
on 02 (contact, paste or fan), which the operator will check physically and possibly send for RMA. Until then CI heat
should not land on it. A second reason is measurement hygiene: `talos-power-tuning-ab` runs its CI A/B on 01 and 03
only, and a shard on 02 would change the shard placement it compares.

**Why the gate and not a taint or affinity.** The gate pins each admitted pod with
`nodeSelector kubernetes.io/hostname=<node>` (`release()`). A taint on 02 or a `nodeAffinity` in
`job-template.yaml.tpl` would not stop the gate from picking 02. The pinned pod would then sit `Pending`
(unschedulable) on that node while holding a CI slot, which is worse than now. A taint would also be a node mutation
outside GitOps. The gate is the only place that chooses the node, so the exclusion goes there.

**Why a plan, not a direct edit.** The ci-runner owner edited the gate 5x on 2026-10-04. This change must land
on a known file shape (premises), after the power-caps soak and before the A/B baseline. It is low risk.

## 2. Pre-checks

From the repo root on the Mac, as `mu` (never root; SOP §2b), mise activated.
```bash
cd /Users/mu/code/cberg-home-nextgen
umask 077; export W=/private/tmp/ci-exclude-node02; mkdir -p "$W"
awk '$0=="```python exclude-edit" {f=1;next} /^```$/{f=0} f' runbooks/maintenance/plans/ci-runner-exclude-node02.md > "$W/exclude-edit.py"
python3 -c "import ast,sys; ast.parse(open(sys.argv[1]).read())" "$W/exclude-edit.py" && test -s "$W/exclude-edit.py" && echo EXTRACT_OK
git log -1 --format='%h %ad %s' --date=iso -- scripts/ninth-banner-admit.py
```
2.1 Premises: `.venv/bin/python3 runbooks/plan-premises.py ci-runner-exclude-node02 --require-premises` -> all PASS.
2.2 The `git log` line above prints `4534a467 ...`. If a NEWER commit touched the gate, read its diff first. The
edit script still asserts the anchor shape, but a new knob may overlap this one (e.g. the power-caps 3.10
`GATE_OPEN_BELOW_C` raise is compatible: different line).
2.3 No CI run is half-admitted: `scripts/ninth-banner-admit.py --status | tail -n +1 | grep -c '^  tnb-'` prints the number
of gated pods. Any number is safe (gated pods simply never go to 02 afterwards). Record it.
2.4 Baseline for the negative control: `scripts/ninth-banner-admit.py --status | grep -c excluded` -> `0`.

## 3. Steps

3.1 Edit (anchored; refuses a second run, measured on the scratch copy: second run -> `AssertionError: gate not in the expected shape`):
```bash
cd /Users/mu/code/cberg-home-nextgen; export W=/private/tmp/ci-exclude-node02
python3 "$W/exclude-edit.py" . "$(date +%Y.%m.%d)"          # -> EXCLUDE_EDIT_OK
python3 -c "import ast; ast.parse(open('scripts/ninth-banner-admit.py').read())" && echo PARSE_OK
git diff --stat scripts/ninth-banner-admit.py docs/sops/ci-runner.md      # 2 files, ~+11/-2
```
From this moment every running trigger's next tick uses the new file.

3.2 Gate 4.1 (below) MUST pass BEFORE the commit. If it fails: `git checkout -- scripts/ninth-banner-admit.py docs/sops/ci-runner.md`, stop.

3.3 Commit + push (message file unique, written BEFORE the commit; `--only` so nothing foreign rides along):
```bash
cd /Users/mu/code/cberg-home-nextgen
M=$(mktemp /private/tmp/claude-ci-exclude-msg.XXXXXX)
printf '%s\n\n%s\n' 'fix(ci-runner): thermal gate excludes k8s-nuc14-02 (GATE_EXCLUDE_NODES) until its cooler is fixed' \
  'Plan ci-runner-exclude-node02; F-6c7843e4. 96 C within ~4 s of an 18-thread load at 35/55 W; 64,970 package throttles/7d vs 741/56 on 01/03.' > "$M"
git commit --only scripts/ninth-banner-admit.py docs/sops/ci-runner.md -F "$M"
git log -1 --format=%s        # must be the subject above; else amend before push
git show --stat HEAD          # exactly these 2 files
git pull --rebase --autostash && git push   # --autostash REQUIRED: another session's unstaged file in the shared worktree
                                             # (e.g. runbooks/state/active-updates.json) makes a plain pull --rebase exit 128
```

## 4. Verification

**4.1 CONTENTS ASSERTION: nuc14-02 is closed for both lanes, 01/03 are not excluded.** Measured by the gate's own
read-only status, compared against the empty-override negative control. **Positive guard first** (the gate prints no
node lines at all when it has no Prometheus data, and every absence check below would then read 0):
```bash
cd /Users/mu/code/cberg-home-nextgen
scripts/ninth-banner-admit.py --status | grep -c -E '^k8s-nuc14-0[123] '                                                                           # 3 (guard)
scripts/ninth-banner-admit.py --status | grep -A1 '^k8s-nuc14-02 ' | grep -c 'browser: CLOSED excluded (GATE_EXCLUDE_NODES)  cpu: CLOSED excluded (GATE_EXCLUDE_NODES)'   # 1
scripts/ninth-banner-admit.py --status | grep -A1 -E '^k8s-nuc14-0[13] ' | grep -c excluded                                                       # 0
GATE_EXCLUDE_NODES= scripts/ninth-banner-admit.py --status | grep -c -E '^k8s-nuc14-0[123] '                                                      # 3 (guard)
GATE_EXCLUDE_NODES= scripts/ninth-banner-admit.py --status | grep -c excluded                                                                     # 0 (negative control)
```
PASS = `3`, `1`, `0`, `3`, `0`. A guard reading < 3 means no data: retry once after `--status | head -3`, then STOP
(not a FAIL of the change). Each check can fail:
- The old code path or a hostname mismatch prints `0` on line 2. Measured: the unmodified gate prints `0`.
- A code path that excluded 01/03 prints `>0` on line 3. Reviewer measurement:
  `GATE_EXCLUDE_NODES=k8s-nuc14-01,k8s-nuc14-03 ... | grep -A1 -E '^k8s-nuc14-0[13] ' | grep -c excluded` reads `2`.
- A default that ignores the env prints `>0` on line 5. The default-env form of that command reads `1`.

Measured 2026-10-05 on the dry-tested scratch copy against the live cluster: `1` / `0` / `0`, with the guard at 3.
CONTROL: metric node_thermal_zone_temp - the gate's input (`x86_pkg_temp` 2-min avg/3-min peak); the guard proves it
is read for all three nodes.

**NIGHTLY VARIANT (the default in `nightly:2026-10-06`, co-scheduled after flux-fleet-0.60.0): §4.2 is DEFERRED.** The
nightly runs §2, §3 and §4.1 only (~28 min, `est_duration_min`). §4.1 proves the gate change by its own reading (guards
3, `1`/`0`/`3`/`0`). The §4.2 evidence is then the A/B's evening-1 control run **`A0-1`** (`talos-power-tuning-ab` §3.3,
2026-10-06 ~18:55 Berlin). It is the same ref and suite set, and its `ab-summary.py` marks a run `INVALID RUN ...
on_nuc14-02=N` if any shard lands on 02. Record the link in this plan's execution record: "§4.2 deferred, evidence =
talos-power-tuning-ab A0-1 (`shards-A0-1.json`: 0 pods on k8s-nuc14-02)". If the A/B does not run within 48 h, run
§4.2 as below in the next attended slot. In an attended slot (or a nightly with spare capacity) run §4.2 directly.

**4.2 CONTENTS ASSERTION: a real run places every shard on 01/03 and none on 02.** One e2e run (3 GPU shards, the same
ref the A/B uses), started with `run_in_background: true` (it outlives the 600 s Bash limit). Wait for `^SUITES_DONE`
with a Monitor until-loop, never a foreground sleep:
```bash
cd /Users/mu/code/cberg-home-nextgen; export W=/private/tmp/ci-exclude-node02
{ scripts/ninth-banner-test.sh d3ae92f e2e 3; echo "e2e rc=$?"; echo SUITES_DONE; } > "$W/verify.log" 2>&1
```
While it runs (pods hold until collected, TTL 600 s after the Job finishes), and once more after `SUITES_DONE`:
```bash
J=$(sed -n 's|^job ci-runner/\([^ ]*\) .*|\1|p' /private/tmp/ci-exclude-node02/verify.log)
kubectl get pods -n ci-runner -l "batch.kubernetes.io/job-name=$J" -o jsonpath='{range .items[*]}{.spec.nodeName}{"\n"}{end}' | sort | uniq -c
```
PASS = exactly 3 pods, every `nodeName` in {`k8s-nuc14-01`, `k8s-nuc14-03`} (any split, e.g. 2+1 or 1+2:
the 3rd shard waits for nuc14-01's second slot or for a finished shard and may land on 03), zero on `k8s-nuc14-02`,
and the log reaches `SUITES_DONE`. A mid-run reading prints blank lines for pods still gated (no node yet). That is
expected, not a failure. Shard pass/fail is not the gate: e2e shard 2 failed on a timing assertion on 10-05, and the
runner is best-effort. Can it fail? Yes: on 2026-10-05 01:05Z the unmodified gate put an e2e shard on 02 (02 was the
coolest node with the fewest CI pods), and right now 02 reads 50 °C, the same as 01/03. Without the exclusion the
"fewest pods, then coolest" rule picks 02 for one of the three shards.
CONTROL: alertname CIRunnerThermalGateStalled - must NOT fire during the run. Its firing would mean the 3rd shard
never got a slot. INFORMATIONAL only: 30 min `for`, longer than this run. The pod count above decides.
CONTROL: alertname CIRunnerPodStuckPending - informational. It ignores gated pods, and a pinned pod that cannot
schedule would trip it.

**4.3 Capacity with 2 nodes (informational, recorded):** browser lane 3 slots (01 x2, 03 x1), cpu lane 4 slots
(01 x2, 03 x2), CI CPU budget 6 per node -> 12 CPU. Quota 24 pods / 48 CPU is unchanged and never binding at
that size. The cost is ~1/3 fewer CI slots: a 4-shard sims run still runs 2 at a time (Job parallelism 2), and
an e2e/release 3-shard run waits up to 300 s for nuc14-01's second slot (settle).

## 5. Rollback

- Caveat for every `git pull --rebase --autostash` in this plan: it temporarily stashes OTHER sessions' uncommitted
  changes in the shared worktree and restores them UNSTAGED. Check that the pull ends with `Applied autostash.` A
  conflict on restore leaves them in `git stash list`: restore them, never drop them.
- Per run, no commit: `GATE_EXCLUDE_NODES= scripts/ninth-banner-test.sh ...` (empty = nothing excluded). It applies
  only to the ticks THAT trigger runs: the host lock is shared, and a concurrent trigger ticks with its own env (default =
  02 excluded), so with two triggers running, 02 is open only on this trigger's ticks.
- Permanent: `git revert <3.3 sha>`, verify `git log -1 --format=%s` and `git show --stat HEAD` (= the 2 files),
  `git pull --rebase --autostash && git push`. The next tick of any running trigger reads the reverted file. Confirm with the
  positive guard `scripts/ninth-banner-admit.py --status | grep -c -E '^k8s-nuc14-0[123] '` -> `3`, AND
  `scripts/ninth-banner-admit.py --status | grep -c excluded` -> `0` (before the revert the same command reads `1`).
  If `git revert` refuses because other sessions have staged files in the shared index, use the per-run override
  above until the index is clear. Never `git stash` another session's work.
- When nuc14-02's cooler is fixed, do the same revert, or change the default to `""`. Then watch one run per §4.2 with
  02 now allowed.
No forward-only parts.

## 6. Interference notes

- **talos-power-tuning-ab depends on this plan**: its A/B runs on 01/03 only and compares per-shard times. The
  unmodified gate has no exclusion knob at all, so the A/B cannot be run correctly without this plan. It must be
  EXECUTED before the A/B's first evening: nightly 10-06, else nightly 10-07 (the A/B then shifts a day). It cannot run
  inside the A/B's NOW run (exclusive; preflight checks the A/B premise `node02-excluded-from-ci`).
- **talos-sysfs-power-caps 3.10** (soak step, operator/attended) edits `OPEN_BELOW_C` in the same file. Independent
  anchors: either order works, but not in parallel sessions (shared worktree, `git commit --only` takes whole files).
  Listed in `conflicts_with`.
- **kube-prometheus-stack-91.9.0**: the gate fails closed without Prometheus. A kps roll during §4.2 queues the shards
  and the run reads as stuck. Listed both ways (repo correction for that plan's author: add
  `ci-runner-exclude-node02` to its `conflicts_with`; the planner writes only its own files).
- **CI owner coordination**: the ci-runner work edits this file often. The premises pin the shape, and §2.2 tells the
  executor to read any newer commit first. The SOP edit keeps the §2b table the single place that lists gate knobs.
- **Nightly 2026-10-06 needs the soak captured first.** Premise `soak-24h-recorded` passes only if someone runs
  `capstats.py soak-24h 1440 "$W"` (talos-sysfs-power-caps 3.10 evidence, `W=/private/tmp/sysfscaps-talos-sysfs-power-caps`)
  between 2026-10-05T23:17Z and 01:30Z, and the predecessor's Copy-out puts `stats-soak-24h.json` into
  `/private/tmp/powerab-talos-power-tuning-ab`. The coordinator will try, if its session is active. Otherwise this plan
  STOPs safely on its premises in the nightly and goes to nightly 10-07. A Mac reboot wipes `/private/tmp`, i.e. the
  soak evidence with it.
- **Nightly capacity (corrected, review 2026-10-05):** the schedulable nightly is 90 - 20 Step-0 reserve = **70 min**
  (`window-scheduler.py` `STEP0_RESERVE_MIN`, `maintenance-windows.yaml` nightly). flux-fleet-0.60.0 (35) + the FULL
  variant (45) = **80 > 70 schedulable**, so the nightly runs the NIGHTLY VARIANT (28 min, §4.2 deferred to the A/B's
  `A0-1`, see §4): 35 + 28 = 63 <= 70. **Order: flux-fleet-0.60.0 first**, this plan after its health gate.
- **ci-gate-primary-control-rework** (backlog draft) depends on this plan and edits the same two files later.
- **Nightly 2026-10-06 ordering:** `flux-fleet-0.60.0` is scheduled into the same night (shared `monitoring`). Run
  this plan after its health gate, so a Flux/monitoring disturbance cannot read as a "stuck" §4.2 run.
- **Other CI triggers**: every trigger on the Mac uses the same file, so release-status runs (`release` suite) also stay
  off 02. GitHub Actions CI is unaffected.

## Appendix - exclude-edit.py (extracted by §2; dry-tested 2026-10-05 on a scratch copy: first run EXCLUDE_EDIT_OK, second run AssertionError, result parses, `--status` 1/0/0)

```python exclude-edit
# exclude-edit.py <repo-root> <YYYY.MM.DD>  -- plan ci-runner-exclude-node02, section 3.1
# Adds GATE_EXCLUDE_NODES (default k8s-nuc14-02) to the CI thermal gate + SOP rows.
# Anchored replacements; refuses to run twice or on an unexpected file shape.
import sys
root, ver = sys.argv[1], sys.argv[2]
g = f"{root}/scripts/ninth-banner-admit.py"; t = open(g).read()
A = "# CI CPU requests per node (owner 2026-10-04: CI gets >= 6 CPU per node while\n"
B = "    avg2, max3 = temps[node]\n    if node in brake:\n"
assert t.count(A) == 1 and t.count(B) == 1 and "EXCLUDE_NODES" not in t, "gate not in the expected shape"
t = t.replace(A, (
    "# Nodes that get NO CI pod in either lane (plan ci-runner-exclude-node02, 2026-10):\n"
    "# nuc14-02 hit 96 C ~4 s into an 18-thread load at 35/55 W and logged 64,970\n"
    "# package throttles in 7 days vs 741 / 56 on 01 / 03 (suspected cooler defect).\n"
    "# Comma-separated hostnames; GATE_EXCLUDE_NODES= (empty) excludes none.\n"
    'EXCLUDE_NODES = {n for n in os.environ.get("GATE_EXCLUDE_NODES", "k8s-nuc14-02").split(",") if n}\n') + A)
t = t.replace(B, "    avg2, max3 = temps[node]\n    if node in EXCLUDE_NODES:\n"
                 '        return "excluded (GATE_EXCLUDE_NODES)"\n    if node in brake:\n')
open(g, "w").write(t)
s = f"{root}/docs/sops/ci-runner.md"; d = open(s).read()
R = "| Brake (per node, since 2026-10-04 late evening) |"
H = "- `2026.10.04` (gate-stall alert):"
V = "> Version: `2026.10.04`\n"
U = "> Last Updated: `2026-10-04`\n"
B4 = "So nuc14-02/03 take 1 CI pod, nuc14-01 up to 2 (total 4)."
S4 = "browser shards at most 4 running (1 each on nuc14-02/03, up to 2 on nuc14-01)"
T = "| nuc14-02 never gets a CI pod | Expected: it peaks at 96-98 °C even without CI, so its 3-min peak is usually >= 93 °C (§2b) |"
assert d.count(R) == 1 and d.count(H) == 1 and d.count(V) == 1 and d.count(T) == 1 and d.count(U) == 1 and d.count(B4) == 1 and d.count(S4) == 1 and "GATE_EXCLUDE_NODES" not in d, "SOP not in the expected shape"
row = ("| Excluded nodes (plan ci-runner-exclude-node02) | `GATE_EXCLUDE_NODES` (default `k8s-nuc14-02`): an excluded node takes **no** CI pod in either lane "
       "(reason `excluded` in `--status`), checked before every other limit. nuc14-02 hit 96 °C ~4 s into an 18-thread load at 35/55 W and logged ~65k package "
       "throttles in 7 days (01: 741, 03: 56): suspected cooler defect. Remove it from the default once the cooler is repaired/replaced. "
       "One-run override: `GATE_EXCLUDE_NODES= scripts/ninth-banner-test.sh ...` (empty = none excluded); it applies only to the ticks THAT trigger runs "
       "(the host lock is shared, concurrent triggers tick with their own env) |\n")
i = d.index(R); j = d.index("\n", i) + 1; d = d[:j] + row + d[j:]
i = d.index(H); j = d.index("\n", i) + 1
d = d[:j] + f"- `{ver}` (node exclusion): `GATE_EXCLUDE_NODES` (default `k8s-nuc14-02`) keeps CI off nuc14-02 in both lanes until its cooling is fixed (plan ci-runner-exclude-node02).\n" + d[j:]
d = d.replace(V, f"> Version: `{ver}`\n")
d = d.replace(U, f"> Last Updated: `{ver.replace('.', '-')}`\n")
d = d.replace(T, "| nuc14-02 never gets a CI pod | Expected: it is in `GATE_EXCLUDE_NODES` (§2b, suspected cooler defect); `--status` shows `CLOSED excluded` for both lanes |")
d = d.replace(B4, "So nuc14-03 takes 1 CI pod, nuc14-01 up to 2 (total 3 while nuc14-02 is in `GATE_EXCLUDE_NODES`; 4 without the exclusion).")
d = d.replace(S4, "browser shards at most 3 running (1 on nuc14-03, up to 2 on nuc14-01; nuc14-02 excluded via `GATE_EXCLUDE_NODES`)")
open(s, "w").write(d)
print("EXCLUDE_EDIT_OK")
```
