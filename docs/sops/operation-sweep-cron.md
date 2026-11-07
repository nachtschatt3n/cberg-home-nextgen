# SOP: Recovering a failed OpenClaw-triggered operation sweep

> Description: How the in-cluster OpenClaw cron hands the sweep (and the
> snapshot, retro and maintenance-window jobs) to the Mac, what each exit code
> and marker means, how to read the cron's run history, and the single safe way
> to re-trigger. Written after the 2026-11-04..07 run of cron failures.
> Version: `2026.11.07`
> Last Updated: `2026-11-07`
> Owner: `operator + openclaw-agent`

---

## 1) Description

The sweep runs on the Mac mini, never in the cluster or a cloud sandbox (local
SOPS key, `kubectl`, mise tooling; see `CLAUDE.md` "Scheduled Sweeps"). The
OpenClaw cron `8163c139` ("Daily Operation Sweep Every 2 Days", every 48h,
04:00 Europe/Berlin) is only the trigger: it runs
`operation sweep --wait --trigger cron` in the `ai/openclaw` pod, which hands the
job to the Mac.

Two delivery paths exist:

1. **Headless dispatcher (preferred, tried first).** The `ai-server-cron` iTerm
   pane runs `runbooks/headless-dispatcher.py`; the skill types one `HRUN` line
   into it and a fresh `claude -p` starts in the repo, logging to
   `~/Library/Logs/cberg-headless/<UTC-stamp>-<kind>-<run-id>.log`. The ops
   console being busy, in a menu or context-exhausted is irrelevant here.
2. **Ops console (fallback, only when the dispatcher is absent).** Types into the
   `ai-server-ops` Claude pane, which refuses when the pane is not at its prompt.

- Scope: sweep (`op-sweep`), snapshot (`op-snapshot`), retro (`op-retro`) and the
  maintenance-window crons (`mw-*`), which share the delivery code.
- Prerequisites: `kubectl`, the repo, and read access to
  `~/Library/Logs/cberg-headless/` on the Mac.
- Out of scope: maintenance-window internals (`docs/sops/maintenance-windows.md`).

## 2) Overview

| Item | Value |
|---|---|
| Trigger cron | OpenClaw `8163c139`, every 48h, 04:00 Europe/Berlin (mirror: `runbooks/ops-crons.yaml`) |
| Skill that hands off | `operation` (git: `kubernetes/apps/ai/openclaw/app/skills-configmap.sops.yaml`, key `operation.py`) |
| Headless logs | `~/Library/Logs/cberg-headless/` on the Mac |
| Completion proof | a `sweep_cycles` row with `trigger='cron'` (sweep_history Postgres) |
| Liveness detector | `runbooks/maintenance-plan.py` asserts sweep-cron liveness from `sweep_cycles` |

Exit codes of `operation` (cron or manual):

| Exit | Meaning | Action |
|---|---|---|
| 0 | delivered; with `--wait` and a non-manual trigger, the `sweep_cycles` row appeared | none |
| 2 / 3 | `openclaude` binary missing / call timed out | check the pod's `~/.openclaw/bin/openclaude` and the harness |
| 4 | pane refused or unreachable: wrong cwd, dead, exhausted and not auto-clearable, `/clear` did not take. Also what you see when the dispatcher AND the harness are both unreachable (the fallback to the console cannot resolve the pane either) | `operation classify`; if the harness is down, restore it (section 7) |
| 5 / 6 | send / ask failed | re-check the harness, then retry once |
| 11 / 12 | `--wait` completion gate: `sweep_cycles` unreadable / no new row | the job may still be running or died; section 4 step 3 |
| 13 | console not at the prompt (busy / background agents / menu); nothing typed | only on the console path; wait for idle |
| 14 | headless path: the dispatcher REFUSED (a job of the same kind is still running) or no `HEADLESS_STARTED` marker within 45 s after typing; never falls back to the console | section 4 |

Markers printed by the cron's stdout (`openclaw cron show <id>` diagnostic):
`HEADLESS_STARTED run=<id> pid=<n>` (job started), `HEADLESS_UNAVAILABLE: ...`
(dispatcher absent, console fallback follows), `HEADLESS_REFUSED`, and
`headless run <id> is still running after 1800s (not killed); checking the
ledger instead` (the cron stopped waiting, the job keeps going; success is then
judged from the ledger).

## 3) Blueprints

- Cron declarations: `runbooks/ops-crons.yaml`, `runbooks/maintenance-windows.yaml`
  (checked by `runbooks/window-crons.py --check` on every sweep).
- Skill code: `kubernetes/apps/ai/openclaw/app/skills-configmap.sops.yaml`
  (`operation.py`, `maintenance-window.py`); SOPS-encrypted, edit with the
  `EDITOR=<script> sops` method so only changed values re-encrypt.
- Dispatcher: `runbooks/headless-dispatcher.py` and the launchd/iTerm setup in
  `docs/sops/maintenance-windows.md` section "Headless cron path".

## 4) Operational Instructions

When the sweep cron shows `error`, or the board says the sweep cron is overdue:

1. **Read the cron's own record** (never trust a label):

   ```bash
   OC=$(kubectl -n ai get pod -l app.kubernetes.io/instance=openclaw -o jsonpath='{.items[0].metadata.name}')
   kubectl -n ai exec "$OC" -c app -- openclaw cron show 8163c139-0f93-42bd-a9d7-dda188c072ba
   kubectl -n ai exec "$OC" -c app -- openclaw cron runs --id 8163c139-0f93-42bd-a9d7-dda188c072ba --limit 5
   ```

   Look at `lastErrorReason`/`diagnostic`, the exit code, and which marker
   appeared.
2. **Check the Mac side** (needs two signals, not one): the newest
   `~/Library/Logs/cberg-headless/*-op-sweep-*.log` AND the ledger.

   ```sql
   select started_at, finished_at, trigger, verdict from sweep_cycles
    where trigger='cron' order by started_at desc limit 3;
   ```

   A log without a `sweep_cycles` row means the run died early (see section 7:
   usage limit, auth). A row without a log means the console path ran.
3. **Is it still running?** A sweep legitimately runs 15 to 90 minutes. The cron
   stops waiting at 1800s and verifies from the ledger afterwards. Do nothing
   while the dispatcher pane shows the run active.
4. **Re-trigger at most once**, only after steps 1 to 3 show the run is dead:
   send `operation sweep` (or type "run a sweep" into the `daily-operation`
   session) **once**. Never create a `/loop` or `CronCreate` schedule: it
   double-runs against the cluster cron.
5. Confirm with the ledger query above (a fresh `trigger` row, `finished_at`
   set) and that the next cron run is scheduled (`openclaw cron list`).

## 5) Examples

### Example A: harness unreachable (2026-11-04 and 11-05)

Cron stdout began `HEADLESS_UNAVAILABLE: no dispatcher pane ... openclaude:
harness unreachable at http://<mac>:6770: Connection refused`, then
`OPERATION_SWEEP_HANDOFF_FAILED: could not reach a live ...`, exit 4. The Mac
side of the iTerm harness was down, so neither path could resolve a pane. The
sweep and the nightly window for those days were lost; both recovered on their
own once the harness was back (11-06 sweep and nightly completed).

### Example B: typed but no marker (2026-11-06 01:45, snapshot)

`typed run=... but no STARTED/REFUSED marker within 45s -- NOT falling back`,
exit 14. No log file was created, so the job never started. The next day's run
was fine. A single occurrence needs no action; three in a row means the
dispatcher pane is wedged (ctrl-c and restart it, running jobs keep going).

## 6) Verification Tests

### Test 1: the trigger is healthy

```bash
kubectl -n ai exec "$OC" -c app -- openclaw cron list | grep -i "sweep"
# status ok, next run in the future
```

### Test 2: a cron-triggered cycle completed

The ledger query in section 4 returns a row with `finished_at` not null and a
verdict, dated after the last 04:00 firing.

### Test 3: the pane path is ready

`maintenance-window classify` (or `operation classify`) reports
`cron_path: headless dispatcher READY`.

## 7) Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| exit 4, `harness unreachable ... Connection refused` | the iTerm harness on the Mac is not running (Mac reboot, iTerm restart, harness process died) | restart the harness / iTerm session on the Mac; the next cron fires normally, re-trigger a missed sweep once |
| `HEADLESS_UNAVAILABLE: no dispatcher pane` then exit 13 or 4 | dispatcher pane absent or not READY, console busy or exhausted | start the dispatcher (`docs/sops/maintenance-windows.md` "Headless cron path"); `operation restart` for a wedged console |
| exit 14 REFUSED | the same kind is still running | none; do not re-send |
| exit 14, no STARTED marker | dispatcher pane wedged or busy typing | ctrl-c and restart the dispatcher |
| log present, tiny, no `sweep_cycles` row | the headless `claude -p` died at startup: weekly usage limit rejected, or auth | read the end of the log; the limit resets on a schedule, do not loop |
| `--wait` exit 11 / 12 | ledger unreadable / no row yet | run the ledger query by hand before concluding failure |
| cron `error` but the job later completed | the cron's wait elapsed first | trust the ledger, not the cron status; the next successful run clears the status |

## 8) Diagnose Examples

### Diagnose Example 1: "the sweep cron is red but the board is fresh"

Read step 1 and the ledger query. A fresh `trigger='cron'` row with
`finished_at` set means the run succeeded and only the cron's wait lost the
race; no re-trigger.

### Diagnose Example 2: "no cycle for 4 days"

`openclaw cron runs` shows errors on the due days; `ls -lt
~/Library/Logs/cberg-headless/*op-sweep*` shows no log for them: the handoff
never started (harness down, example A). Recover the harness, then re-trigger
once.

## 9) Health Check

`runbooks/health-check.sh` reports sweep cron `lastRunStatus=error`;
`runbooks/maintenance-plan.py` reports a missing `trigger='cron'` cycle. Both are
symptoms: use section 4 to find the cause.

## 10) Security Check

Headless logs contain full sweep transcripts. Do not paste them into commits,
issues or chat. Never print the contents of the SOPS age key or decoded secrets
while triaging.

## 11) Rollback Plan

Nothing to roll back for a failed run. If a skill change broke the handoff,
revert the `skills-configmap.sops.yaml` commit; the reloader re-seeds the skills
on the next pod roll (check no cron is due within ~15 minutes first).

## 12) References

- `docs/sops/maintenance-windows.md` (window crons, exit-code table, headless path)
- `docs/sops/openclaw-config.md`, `docs/sops/ai-integration.md`
- `runbooks/ops-crons.yaml`, `runbooks/headless-dispatcher.py`, `CLAUDE.md`

## Version History

- `2026.11.07`: created (closes the missing-SOP finding for recovery of a failed
  OpenClaw-triggered sweep).
