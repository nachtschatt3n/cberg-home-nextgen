# Ops-Continuity Plan — autonomous operations that actually run

> Status: **in progress** (mechanisms complete; G1/G2 + weekend renames outstanding). Delete this file when P3.2 closes.
> Started: 2026-08-26 · Operator-approved plan, validated against SRE/ITIL/
> k8s-at-home practice + current AIOps research (G1–G4 amendments).

## Goal (operator's words, paraphrased)

A continuously stable cluster with no critical issues. Checked daily; criticals
tackled immediately. Human-in-the-loop ONLY for capability-changing or
interrupting work; routine reversible updates run fully automated at night.
The operator stops being the system's execution engine.

## Why (measured, 2026-08-26)

30 days of sweeps: 33 red / 2 yellow / 0 green — "red" had stopped meaning
anything. Criticals resolved fine (327 in 60d, median 2.0d) but the EXECUTION
plane was structurally broken: 4 of 7 declared maintenance windows had no
driving cron (plans scheduled into them silently never ran, one with a live
operator GO); GOs leaked past their windows and stayed readable as live
authorization; the plan↔held matcher couldn't see its own plans (perpetual
"NEEDS A PLAN" + redundant planner dispatch); "routed to PLAN" produced no
plan; and roughly half of all failures were silent-inert-check failures —
controls that could not fire and looked healthy.

## Architecture spine

Desired state in git (windows YAML, plan frontmatter, policy YAMLs) · observed
state live (OpenClaw crons, DB rows, cluster) · reconcilers that assert parity
every sweep and page on divergence. Every control ships with (a) a one-time
commissioning proof it CAN fire and (b) a standing staleness assertion.

## Done (all commissioned by watching them fail first)

| Item | What | Commit(s) |
|---|---|---|
| P0.1 | `sat-early` OpenClaw cron created (was declared, undriven) | live: `fe1f69f9` |
| P0.2 | Stale talos GO voided + fresh go/no-go for sun-window:2026-08-30 | `75692284` |
| P0.3 | Plan↔held matcher: `lib/plan_matching.py`, PR/name/version-pair tiers | `46008239` |
| P0.4 | `maintenance-plan.py --validate` frontmatter invariants; 6 plans fixed; new `status: reference` | `509b0d81` |
| P0.5 | In-cluster sweep heartbeat CronJob + `SweepPipelineDead` (Mac-independent alert path) | `c5d77423` |
| P1.4 | `home-operation tick` auto-expires GOs whose window passed; reopens as fresh go/no-go | `b9f17908` |
| P1.3 | `window_runs` table + `window-run-record.py` + per-occurrence liveness assertion | `3a9dda9d` |
| P2.2 | plan-or-page: `finding_refs` frontmatter, 4d SLA, pages on overdue; planner accepts finding-shaped input | `7ac09300` |
| — | DECIDE glob fix: "unexpected external ingress" routes to operator judgement | `3332d094` |
| P1.1/2 | Windows 7→3 (`nightly` 03:30 unattended daily + sat/sun attended); `window-crons.py --render/--check` parity asserted every sweep | `7589b734` |
| P2.1a | `autonomy-policy.yaml` + derived execution classes (REPORT-ONLY soak); facts backfilled into 5 executable plans; G4 doctrine codified | `3a6ca388` |
| P2.1b | Class-based autonomy ENFORCED in the window agent; auto_execute retired everywhere (validator-blocked); kill switch = empty the policy classes | `a39d8766` |
| P3.1 | Ownership-aware verdict flipped (red = unowned/SLA-breach/ownership-unknown; yellow = owned in flight; green = zero). First live run: 2026-08-28 sweep | `0f786bc4` |
| P3.2 | `controls.yaml` ledger (needle contract) + `docs/sops/control-liveness.md` + doc-check s10 enforcement; 4d planner dispatch collapsed into 4d0 | `fb35142f` |
| P3.1 prep | 30-day back-test of ownership-aware verdict: 21/33 reds → yellow; the 12 that stay red are the genuine 08-15..18 stuck period; one old yellow was an under-report. 4d SLA needs no tuning | (read-only) |

Seven new regression suites (42 total in `runbooks/tests/run-all.sh`). Three
falsy-zero/def-time-default/carried-field bugs caught during commissioning and
pinned.

## Remaining

- **G1:** `minimum_release_age` in `auto-update-policy.yaml` (waived for
  CVE-driven bumps) + enforcement in the safe-update lane, with tests.
  auto-update.py is the most safety-critical script — deserves its own
  focused session.
- **G2:** the automated scratch-restore probe (`backup_gate`) for
  AUTO-BACKUP-GATED plans; upgrades the manual quarterly Restore Drill
  (log in control-liveness.md, next due 2026-11-26). The two postgres 17→18
  plans (expected from the 2026-08-28 sweep's planner dispatch) adopt it.
- **Weekend-gated:** `sat-early`→`sat-attended` / `sun-window`→`sun-attended`
  renames after the 08-29/08-30 GOs execute; `first_runs_supervised` tracking
  begins with the first AUTO-classed plan.
- **Close-out:** delete this file once the above land and one full week of
  nightly windows + two sweeps have run clean under the new semantics.

## Live soak events (first unattended exercises)

- nightly window: first fire 2026-08-27 03:30 (Step 0 only; no plans slotted)
- sweep 2026-08-28 02:03: first plan-or-page + parity + liveness run in anger;
  rule 4e dispatches planners for the unplanned PLAN-lane findings
- tick: GO expiry active since 2026-08-26 (30-min cadence)
- in-cluster heartbeat: every 6h; `SweepPipelineDead` commissioning pair
  (fire→resolve) expected around first scheduled success
- sat-early:2026-08-29 09:00 — longhorn engine drain, operator-present, GO loaded
- sun-window:2026-08-30 09:00 — talos v1.13.9, awaiting fresh GO (in reminders)

## Decisions of record

- Zero-open-criticals is NOT the steady-state target (Little's Law: ~10 in
  flight at CVE arrival rate); "everything owned and within SLA" is. Green
  stays defined as literally zero — aspirational top state.
- Windows: 2 time shapes (unattended night / attended weekend), not 7 slots.
- Autonomy is decided by reversibility + capability-change + blast radius —
  NOT by `risk:` (that blunt ceiling is what wrongly human-gated the frigate
  restart mitigation).
- Batched nightly updates trade revert attribution for cadence — accepted at
  homelab scale (health-gate reverts the whole batch).
- Talos node reboots stay HUMAN-GATED initially; revisit as a one-line policy
  PR after track record.
