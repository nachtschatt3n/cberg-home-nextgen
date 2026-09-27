# Weekly Ops Retro — procedure for the ops console

**Trigger:** OpenClaw cron "Weekly Ops Retro" (`e9ce4ac3`, Monday 07:30
Europe/Berlin) runs `operation retro --trigger cron`, which types a prompt into
the `ai-server-ops` console telling it to follow THIS file. Ad-hoc: send
`operation retro` once, or type "run the ops retro" into the console. Never put
it on a `/loop` or `CronCreate` schedule, and never in a cloud sandbox (CLAUDE.md
"Scheduled Sweeps"). The declaration lives in `runbooks/ops-crons.yaml`, and
every sweep checks it via `window-crons.py --check`.

**Why:** operator, 2026-09-27: *"every week we do a retro about the efficiency of
the operation."* The first retro was done by hand. Of about 23 operator stops,
about 12 were procedural questions with a predictable answer. Those answers are
now SD-1..SD-9 in `.claude/agents/maintenance-window-agent.md` §"Standing
operator decisions". The memory `feedback_fewer_human_stops` has the rest of
the background. This retro repeats that analysis every week, with numbers.

**Budget:** about 30 minutes and ONE report. An unattended run (the prompt
starts with `[AUTOMATED SCHEDULED RUN`) asks the operator nothing. Anything that
needs the operator goes into the report and the proposal.

---

## 1. Measure

```bash
cd /Users/mu/code/cberg-home-nextgen
source runbooks/lib/sweep-pg-dsn.sh && sweep_pg_dsn_up      # main shell, never in a pipe
D=~/.local/state/ops-retro/$(date +%Y-%m-%d); mkdir -p "$D"
.venv/bin/python3 runbooks/ops-retro.py --json-out "$D/retro.json" --md-out "$D/retro.md"
echo "rc=$?"
sweep_pg_dsn_down
```

- **rc 2 means a data source failed.** The JSON `sources` block names it.
  - Every metric from that source is `UNMEASURED`. Report it that way, and
    never as 0.
  - Try once to fix the source (DSN, pod, port-forward). If you can't, carry on
    with the rest and put "source X down" first in the report.
- **Read `coverage`.** `partial` and `lower-bound` values cannot be compared
  directly with last week's. Examples: Prometheus retention of 7d, Alertmanager
  garbage-collecting silences after 120h, the SD convention starting
  2026-09-27.
- The artifacts stay on this Mac under `~/.local/state/ops-retro/`, outside the
  public repo. Do not commit them: this is a point-in-time report
  (CLAUDE.md §Documentation Conventions).

## 2. Analyse — four questions, evidence first

For each question, drill from the metric into the evidence. Use `window_runs`
notes, `plan_executions` notes, `home-operation list --all --json`,
`openclaw cron runs --id <job>`, `git log` and the week's findings. A claim with
no row, commit or run behind it does not go in the report.

0. **HEADLINE: are we keeping pace with updates and security patches?**
   Operator, 2026-09-27: *"the update and security patches are not efficient
   and we are not catching up with the fast pace."* Read the `velocity`
   section first:
   - **Backlog by lane.** If `BACKLOG GREW` is printed, that is the report's
     first line.
   - **Lead time.** Compare the publish-to-landed median and p90.
   - **Share landed automatically vs by plan vs by operator.** A low
     auto share means the safe lane is starving.
   - **Open fixable HIGH/CRIT and detect-to-fixed days.** Quote the
     contextual tier, not the raw Trivy count.
   - **Renovate intake vs merged.**
   - **Earned-autonomy lane usage**, once that lane exists.

   For each lane, name the bottleneck that holds updates back. Examples:
   - PLAN items waiting on a GO;
   - `max_rule_holds` with no channel oracle;
   - `needs_plan` with no planner dispatched;
   - G3 "release notes unverified".

   Propose the specific policy or automation change that would move them.
1. **Which human stops were unnecessary?**
   - Evidence: go/no-go decisions and time-to-decision, voided GOs, supervised
     vs unsupervised executions, operator questions, and the plans awaiting GO
     for more than 7 days.
   - An unnecessary stop is a question where the operator picked the
     recommended or predictable answer. Also count a stop that stalled an agent
     that was waiting passively.
   - For each pattern that repeats: **propose a new SD rule**, with its exact
     conditions and what still stops.
   - For each SD rule that was cited but led to a bad outcome, such as a revert
     or a regression after an SD-n use: **propose retiring or narrowing it**.
   - SD-n citations only count if agents log them. If a run clearly applied an
     SD and did not cite it, note that too.
2. **Which gates misfired?**
   - A false positive (FP) blocked safe work, for example:
     - a premise or preflight refusal that was later overridden by inspection;
     - a gate that the operator accepted as an FP;
     - a cron refusal (exit 4/8/12/13) that did not match what the console
       actually looked like.
   - A false negative (FN) let a problem through, for example:
     - a revert or regression the gate did not predict;
     - a missed window or sweep that no alert caught.
   - Fix the root cause in the audit logic (`feedback_false_positive_root_cause`).
     Never AR-suppress the symptom.
3. **Where did agents stall?**
   - Look for:
     - window runs with a long gap between `started_at` and `finished_at`;
     - `stuck` rows;
     - missed or lost occurrences;
     - `refusals` per cron job;
     - agents waiting on the operator or on each other.
   - Name each stall's mechanism: busy console, context exhaustion, passive
     wait, or unrecorded GO.
4. **What was the top toil?**
   - Look for:
     - the same fix applied by hand more than once;
     - finding churn (opened and closed both large, with net about 0, which
       means an auto-close/re-open loop);
     - commit bursts (`peak_per_hour`; the etcd-stall lesson F-baf94b64 says to
       batch pushes);
     - revert count;
     - silences created by hand.

Rank all candidates across the four questions by **operator-minutes saved per
week × confidence**. Keep the top 5. Everything else is one line or is dropped.

## 3. Write — three outputs, nothing else

### (a) The report — ONE home-operation issue

The report is at most 15 lines, ranked, and every line carries a number. It
has, in order:

- the patch-velocity headline: backlog trend, lead time and security fix time;
- the top 5 improvements, each with evidence;
- any source failures or UNMEASURED metrics that matter;
- the proposal path.

```bash
KEY="ops-retro-$(date +%G-W%V)"
kubectl -n ai exec deploy/openclaw -c app -- /home/node/.openclaw/bin/home-operation ingest --json "$(python3 - <<'EOF'
import json, os, datetime
d = os.path.expanduser(f"~/.local/state/ops-retro/{datetime.date.today()}")
print(json.dumps({
  "key": os.environ.get("KEY") or f"ops-retro-{datetime.date.today():%G-W%V}",
  "kind": "window_warning", "source": "maintenance", "severity": "info",
  "title": "Weekly ops retro <week>: <one-line headline>",
  "detail": open(f"{d}/report.txt").read()[:3500],
  "component": "operations", "action": "ack"}))
EOF
)"
```

- Before ingesting, write the report text to `$D/report.txt`.
- `kind: window_warning` is the closest valid kind (valid kinds are listed in
  skill `home-operation`).
  - Never use `go_no_go`. The window agent reads `decisions --pending-exec` as
    plan authorisations.
  - Severity `info` means the report appears in the morning briefing and is not
    pushed.
- **Fallback, only when the ingest exits non-zero** (pod down):
  `.venv/bin/python3 -c "import sys; sys.path.insert(0,'runbooks'); from lib.notify import notify; notify(open('$D/report.txt').read())"`.
  Say in the console reply that the fallback was used.
- Public-repo rules still apply to the text: no CVE IDs, no media titles, no
  secret hostnames.

### (b) Findings — one per concrete improvement (P4.1.6 contract)

An improvement that exists only in report prose does not exist. Emit one
finding per improvement, with an `action` that names the exact change and its
owner:

```bash
source runbooks/lib/sweep-pg-dsn.sh && sweep_pg_dsn_up
.venv/bin/python3 runbooks/policy-cli.py finding add --section plan --subsection ops-retro \
  --severity deferred --component <component> \
  --title "ops-retro <week>: <publish-safe one-liner>" \
  --action "<exact change> — owner: <agent/operator>"
```

- Dedupe first: `policy-cli.py finding list --section plan` (it has a default
  row limit, so pass `--limit`). A still-open finding from an earlier retro gets
  a new occurrence in the report, not a second row.
- These rows never auto-close. Whoever lands the fix runs
  `finding close <id> --commit <sha>` in the same turn.

### (c) Proposals — a diff for the operator, never applied

- Write every proposed SD or agent-instruction change as a unified diff to
  `$D/proposal.diff` against the current files. The usual targets are
  `.claude/agents/*.md`, `runbooks/autonomy-policy.yaml` and
  `runbooks/auto-update-policy.yaml`.
- Each hunk carries a comment line with its evidence, and says whether it
  **adds**, **narrows** or **retires** an SD.
- **Do not apply behaviour changes to agents.** The operator approves them
  (in the console or in reply to the report). After approval, apply the diff in
  its own commit that cites the retro week.
- **Small doc fixes ARE OK to apply directly.** These are a wrong path, a stale
  count, or a dead reference. Commit them with `git commit --only <paths>` and
  a unique message file, then verify with `git show --stat HEAD` and
  `git log -1 --format=%s`.

## 4. Close

- Reply in the console with the report text, the finding ids and the proposal
  path.
- If last week's proposal is still unanswered, list it once at the bottom of
  the report. Do not re-propose it as new.
- Check that last week's findings moved. A finding that is untouched for 2
  retros is itself a toil signal.

## Recording conventions the retro depends on

- **SD-n citations** (since 2026-09-27): window and plan evidence says
  "standing decision SD-n" (maintenance-window-agent §Standing operator
  decisions). `ops-retro.py` counts `SD-\d+` in `window_runs` notes,
  `plan_executions` notes and commit messages.
- **Operator questions**: there is no structured record, so the metric is a
  lower bound. It counts `AskUserQuestion` and "operator question" mentions in
  `window_runs` notes. Recording each question in the notes as
  `operator-question: <topic>` would make it exact. That is an agent-behaviour
  change, so it is proposed through (c) and not applied here.
