# SOP: Weekly Ops Retro

> Description: Weekly, measured review of how efficiently the homelab operation runs (human stops, gate misfires, agent stalls, toil), producing one ranked report, improvement findings, and operator-approved standing-decision changes.
> Version: `2026.09.27`
> Last Updated: `2026-09-27`
> Owner: `operator + ai-server-ops console`

---

## 1) Description

On 2026-09-27 the operator asked for a retro "every week ... about the
efficiency of the operation". The first retro was done by hand and produced the
standing decisions SD-1..SD-9. This SOP makes the retro a scheduled procedure
with a measured basis.

- Scope:
  - maintenance windows and plans;
  - operator decisions (home-operation);
  - OpenClaw crons that drive the ops console;
  - sweep cycles;
  - findings flow;
  - git churn;
  - alerting.
- Prerequisites:
  - the Mac mini ops console (`ai-server-ops`);
  - `kubectl` access;
  - the repo `.venv` with psycopg;
  - `runbooks/lib/sweep-pg-dsn.sh`.
- Out of scope:
  - applying agent-behaviour changes. The retro only proposes them. The
    operator approves.

---

## 2) Overview

| Setting | Value |
|---------|-------|
| Schedule | Monday 07:30 Europe/Berlin (after the 03:30 nightly and its 05:45 retry) |
| Trigger | OpenClaw cron "Weekly Ops Retro" `e9ce4ac3` → `operation retro --trigger cron` |
| Executes on | the Mac mini ops console (never `/loop`, `CronCreate` or a cloud sandbox) |
| Procedure | `runbooks/ops-retro.md` |
| Measurement | `runbooks/ops-retro.py` (JSON + markdown; exit 2 on a data-source failure) |
| Cron mirror | `runbooks/ops-crons.yaml`, asserted by `runbooks/window-crons.py --check` every sweep |
| Report channel | `home-operation ingest`, kind `window_warning`, source `maintenance`, severity `info` |
| Artifacts | `~/.local/state/ops-retro/<date>/` on the Mac (not committed) |
| Failure alert | Telegram, after 1 failure, cooldown 6d (< the 7d period, F-e6dda67f) |

---

## 3) Blueprints

N/A. There are no Kubernetes manifests. The skill change lives in
`kubernetes/apps/ai/openclaw/app/skills-configmap.sops.yaml` (`operation.py`,
`skill-operation.md`).

---

## 4) Operational Instructions

1. The cron fires. The `operation` skill resolves the console, then applies the
   same gate as sweep/fix/versions:
   - a busy or menu pane: exit 13, nothing typed;
   - exhausted and idle: `/clear`, then deliver;
   - any other exhausted state: exit 4.

   A non-zero exit pages Telegram through the cron failureAlert.
2. The console follows `runbooks/ops-retro.md`: measure, analyse the four
   questions, then write the three outputs (report, findings, proposal diff).
3. The operator reads the report in the morning briefing. To approve or decline
   proposals, the operator answers in the console. Approved proposals land as
   their own commits.
4. Ad-hoc run: `operation retro` from chat, or "run the ops retro" typed into
   the console. Run it once, never on a loop.

---

## 5) Examples

### Example A: normal weekly run

The cron fires at 07:30 and the console is idle. The prompt is delivered with
exit 0. About 30 minutes later these exist:
- an `ops-retro-2026-W40` issue in `home-operation list`;
- 0-5 `plan/ops-retro` findings;
- `~/.local/state/ops-retro/2026-09-28/proposal.diff`.

### Example B: console busy at 07:30

The cron exits 13 and Telegram pages "Weekly Ops Retro failed". The run is lost
for that week. There is no retry cron, because a week-late retro is still
useful done by hand. Run `operation retro` once the console is idle.

---

## 6) Verification Tests

### Test 1: metrics script against live data

```bash
source runbooks/lib/sweep-pg-dsn.sh && sweep_pg_dsn_up
.venv/bin/python3 runbooks/ops-retro.py; echo rc=$?
sweep_pg_dsn_down
```

Expected: `rc=0` and `**Sources:** all read`. With the DSN unset, it gives
`rc=2`, and every Postgres-backed metric reads `UNMEASURED (...)`, never 0.

### Test 2: unit and delivery tests

```bash
python3 runbooks/tests/test-ops-retro.py
python3 runbooks/tests/test-ops-cron-parity.py
python3 runbooks/tests/test-openclaw-console-delivery.py
```

Expected: all three print `all ... passed`.

### Test 3: cron parity

`python3 runbooks/window-crons.py --check` gives `parity holds: ... 1 ops
cron(s) from ops-crons.yaml present`.

---

## 7) Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `ops-retro.py` rc=2, `postgres` failed | DSN not sourced, or port-forward died | `source runbooks/lib/sweep-pg-dsn.sh && sweep_pg_dsn_up` in the main shell |
| `home_operation` / `openclaw_cron` failed | openclaw pod restarting | wait for Ready and re-run; the metrics are UNMEASURED meanwhile |
| Paging series UNMEASURED for last week | Prometheus retention is 7d | expected; compare only this week's |
| Cron failed with exit 13 | console busy at 07:30 | run `operation retro` when idle |
| Cron failed with exit 4 | console exhausted, not auto-clearable | `operation classify`; `operation restart` if wedged |
| Parity check: "NO cron runs ... operation retro" | cron deleted or edited | `window-crons.py --render`, then paste the add + edit |

---

## 8) Diagnose Examples

### Diagnose Example 1: the retro never ran this week

```bash
kubectl -n ai exec deploy/openclaw -c app -- /home/node/.openclaw/bin/openclaw cron runs --id e9ce4ac3-a38a-491d-950c-234040a1f360 --limit 3
```

Read `status`, `error` ("command exited with code N") and the diagnostics
summary. The refusal codes are 4, 12 and 13, and they are described in
`runbooks/ops-retro.py` `REFUSAL_MEANING`.

### Diagnose Example 2: a metric looks wrong

```bash
.venv/bin/python3 runbooks/ops-retro.py --json | python3 -c "import sys,json; r=json.load(sys.stdin); print(json.dumps(r['current']['hitl'], indent=1))"
```

Every metric names its `source`. Re-run that query by hand before you trust or
dispute the number.

---

## 9) Health Check

- `window-crons.py --check` passes. It runs every sweep through
  `maintenance-plan.py reconcile`.
- The newest `ops-retro-*` issue in `home-operation list --all` is 7 days old
  or less.
- `openclaw cron runs --id e9ce4ac3...` shows the last run `ok`.

---

## 10) Security Check

- Report text and findings are publish-safe. They contain no CVE IDs or
  unfixed-vulnerability detail (`docs/sops/vulnerability-disclosure.md`), no
  media titles, and no secret hostnames.
- Artifacts stay in `~/.local/state/ops-retro/` on the Mac and are never
  committed.
- The failure-alert Telegram destination is not committed: `--render` reads it
  from `$FAILURE_ALERT_TO`.
- The retro only proposes agent changes. It never self-applies behaviour
  changes.

---

## 11) Rollback Plan

- Stop the schedule with
  `openclaw cron disable e9ce4ac3-a38a-491d-950c-234040a1f360`, and remove the
  entry from `runbooks/ops-crons.yaml` in the same commit. Otherwise the parity
  check flags the disabled cron.
- Remove the intent by reverting the `skills-configmap.sops.yaml` commit. Flux
  reconciles the skill back.
- The retro writes nothing to the cluster apart from home-operation issues and
  `plan` findings. Resolve those with `home-operation resolve --issue <key>
  --by cleared` and `policy-cli.py finding close <id>`.

---

## 12) References

- `runbooks/ops-retro.md` — the procedure
- `runbooks/ops-retro.py` — the metrics
- `runbooks/ops-crons.yaml`, `runbooks/window-crons.py` — schedule mirror and parity
- `.claude/agents/maintenance-window-agent.md` §"Standing operator decisions" — SD-1..SD-9
- `docs/sops/maintenance-windows.md` — window pipeline

---

## Version History

| Version | Date | Change |
|---------|------|--------|
| 2026.09.27 | 2026-09-27 | Initial: weekly retro, script, `operation retro` intent, Monday 07:30 cron |
