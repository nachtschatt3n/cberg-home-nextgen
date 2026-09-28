---
name: operation-sweep
description: Run the full agentic operation sweep — six specialists in parallel writing to ONE shared cycle, reconcile findings/AR suppression, refresh the SLO/SLI snapshots, ingest open issues to OpenClaw, then render the operator's board DETERMINISTICALLY via runbooks/render-board.py. Use for "run a sweep", "operation sweep", the 48h cron, or any post-change verification pass.
---

# Operation Sweep

You orchestrate the sweep. You do **not** audit the cluster yourself, and —
critically — you do **not** write the final board yourself. The board is the
output contract and it is rendered by a script, because on 2026-08-16 the
prose-synthesis step sat blocked on a planner child while every finding was
already in Postgres, and the operator had to ask where his board was. A
deterministic renderer answers immediately and shows explicit GAPs for
sections that did not report.

## Ground rules (non-negotiable)

- **READ-ONLY against the cluster.** Dry-run `auto-update.py` only. Safe
  updates apply at Step 0 of maintenance windows, never in the sweep.
- **One shared cycle id.** Mint it FIRST and put it in every specialist's
  environment; six sections land in ONE `sweep_cycles` row:
  `SWEEP_CYCLE_ID=$(uuidgen | tr 'A-Z' 'a-z')`
- **Propagate the run trigger alongside it.** If the invoking prompt carries a
  `[AUTOMATED SCHEDULED RUN — SWEEP_TRIGGER=<t>]` preamble (the every-48h cron
  runs `operation sweep --wait --trigger cron`, which prepends exactly that),
  export `SWEEP_TRIGGER=<t>` in EVERY specialist's environment too. Omitting it
  silently records an autonomous run as `trigger='manual'`
  (`runbooks/sweep-run.py` defaults it), which makes the `sweep-heartbeat`
  CronJob — it queries `WHERE trigger = 'cron'` — alarm forever and never
  clear. That false "sweep cron dead" finding has now shipped twice
  (2026-07-17, 2026-09-05). No preamble = operator run = correctly `'manual'`.
- **Probe behaviour, not Flux status.** Flux has been fully green during two
  total internal-DNS outages. `Ready=True` is not proof.
- **ES field traps** (all verified): `log.level` is unmapped;
  `severity_text`/`severity_number` are dead (28 of 3.49M docs); the only
  signal is a case-insensitive `wildcard` on `body.text` **minus**
  `*noerror*` (CoreDNS logs successful answers as NOERROR). A zero without a
  live-ingestion control query is a broken query, not a clean cluster.
- **A silent zero is never a pass.** Every "0 errors / 0 alarms / clean"
  claim needs a control proving the measurement can see. This class of bug
  has been found eleven times in this repo; see
  `docs/sops/audit-script-correctness.md`.
- **Verify sub-agent findings before promoting them.** Specialists have
  fabricated results, misread node AGE as uptime, and reported stale
  mid-roll snapshots. Cross-check anything surprising against the live
  cluster before it reaches the operator.
- **Do not block the board on planners.** If coverage reports `needs_plan`,
  dispatch upgrade-planner-agents in the BACKGROUND and note it on the
  board; never make the operator wait on them. The dispatch is MECHANICAL
  (step 2b below): one planner per `needs_plan_groups` entry, never per row.

## Flow

1. **Mint the cycle id** (above). Export `SWEEP_PG_DSN` via
   `runbooks/sweep-run.py`'s port-forward setup or run specialists through it.

2. **Dispatch the six specialists in parallel**, each with
   `SWEEP_CYCLE_ID` **and `SWEEP_TRIGGER`** (when the prompt declares one —
   see ground rules) exported: health-check-agent, security-agent,
   version-check-agent, doc-agent, media-manager, slo-agent. Brief each
   with the P4.1.6 contract: a recommendation that implies a state change
   (restart X, delete Y, resize Z) MUST be emitted as a finding — a
   recommendation that exists only in report prose does not exist. The security
   section scores contextual tiers automatically (`risk_model.py`);
   paging is dry unless `SWEEP_NOTIFY_BY_TIER` is set.

2b. **Dispatch planners from the grouped list — mechanically (2026-09-27).**
   Run coverage once and keep the file (rule 4d0 and the reconciler both read it):

       python3 runbooks/coverage.py --json > /tmp/coverage-<cycle>.json
       python3 runbooks/maintenance-plan.py --json --coverage-json /tmp/coverage-<cycle>.json

   `needs_plan_groups` is the dispatch list. Same-image fleets are ALREADY
   collapsed into one target (every `redis:*-alpine` consumer at one patch =
   `redis-fleet-<ver>`; every app-template wrapper = `app-template-<ver>`;
   `flux-instance` + `flux-operator` = `flux-fleet-<ver>`), security-driven
   groups sort first, and a group whose live plan exists has `dispatch: false`.
   Take the entries with `dispatch: true` **in list order, at most
   `planner_dispatch_cap` (5) per sweep**, and dispatch ONE
   `upgrade-planner-agent` per group with `run_in_background: true`. Brief it
   with the group's `group_id` (use it as the plan_id / filename), every
   member (component, namespace, current→target, image repos), the
   `security_evidence` refs (F-ids only, never CVE ids), and the `reason`.
   Before dispatching, skip a group a planner from an EARLIER sweep is still
   working on (a `runbooks/maintenance/plans/<group_id>.md` draft appears the
   moment it writes). Groups beyond the cap wait for the next sweep — list
   them on the board as "queued for planning", never drop them silently.
   Do not dispatch from the raw `needs_plan` rows: that is per-component
   evidence and re-creates the one-planner-per-consumer waste.

2c. **Review drafts AND drain the review backlog (rule 4d0b; ops-retro
   2026-W40, F-2c849d1e).** Dispatch ONE `plan-reviewer-agent` (background,
   read-only, ~20 min) per draft written or retargeted since the previous
   sweep, PLUS up to 5 more plans, oldest first, whose status is
   `draft|vetted|awaiting-go` and that carry no `review: ready-for-go@…`
   line (or one older than 30 days) — skip `blocked` plans and files another
   session has dirty in `git status`. The since-last-sweep filter alone
   stranded every draft a missed sweep skipped: on 2026-09-28, 24 of 27 plans
   had no recorded review and the oldest draft dated from 2026-08-15. Apply
   the corrections, re-review substantive fixes, and write `review:` +
   `status: vetted` only on `ready-for-go` (full rule in
   `.claude/agents/daily-operation.md` 4d0b). List the reviewed ids and
   verdicts on the board.

3. **Update the lists** (this is the "updates" half of the skill):
   - `python3 runbooks/sweep-run.py --reconcile-only` with the cycle id and
     `--ran <sections-that-actually-ran>` — AR suppression + auto-close.
     NOTE (P4.0.6): `media` is the one section with NO sweep-run step —
     the media-manager agent writes its findings out-of-band. Include
     `media` in `--ran` ONLY if that agent reported completion; a
     caller-declared `--ran` is the sole thing standing between "ran
     clean" and "never ran" until the media step lands (P4.4.5).
     Auto-close only touches sections that demonstrably ran, and
     `--cycle-id` is now REQUIRED: without it the reconcile mints a fresh
     cycle id that no row can carry, so every open finding in the `--ran`
     scope would close.
     This reconcile is now a BACKSTOP, not the primary closer. Each check
     script's `FindingsWriter.close(verdict=...)` already resolves the
     findings ITS OWN section stopped emitting, keyed on fingerprint, at
     the moment that section finishes. That is what fixes the failure mode
     where a section completes at 13:52 but the only reconcile passes ran
     at 13:33/13:37 and its stale rows survive (2026-08-18: 82 obsolete
     app-template chart-major rows hand-resolved). Set
     `SWEEP_AUTOCLOSE_DRYRUN=1` to see what would close without writing;
     `SWEEP_AUTOCLOSE=0` disables it.
     A section whose dependencies DEGRADED declares itself incomplete; both
     the writer and this backstop then leave its findings alone (the veto is
     persisted on `sweep_cycles.notes.incomplete` so it survives the process
     boundary). Expect `auto-close SKIPPED … declared INCOMPLETE` in the log
     — that is the veto working, not an error.
     Since 2026-08-19 a degradation attributable to ONE component instead
     records a scope on `sweep_cycles.notes.uncovered`: the section still
     auto-closes, and you will see `⏸ kept open <section>/<F-id> —
     uncovered <component>` per held row. That is ALSO the veto working.
     Past 10 components, or 10% of the attempted universe, it reverts to
     the section-wide form. Full contract:
     `docs/sops/sweep-findings-lifecycle.md`.
   - SLO/SLI snapshots land via slo-agent (`slo-check.py`); confirm rows
     exist in the cycle's time window — a clean SLO run writes snapshots
     but no findings, which is NOT a gap.
   - Ingest open issues / go-no-gos to OpenClaw `home-operation` so
     decisions reach the operator's phone (fallback: `runbooks/lib/notify.py`).

4. **Render the board — never hand-write it:**
   `python3 runbooks/render-board.py` (add `--cycle <id>` for this run).
   The board IS the deliverable, in the operator's defined order:
   tier board → **numbered action list** (every item numbered, categorized
   `section/kind`, one-line description, rated CRITICAL/HIGH/MEDIUM/LOW by
   the contextual model; individual entries for HIGH+, grouped entries for
   the medium queue and low batch so bulk tiers don't drown the list;
   AR-accepted HIGHs and findings already covered by an active maintenance
   plan — exact `security_ref` match only — each collapse to a single count
   line [planned items show the earliest window date]; CRITICALs are never
   collapsed) →
   sections+gaps → SLO/SLI table → maintenance windows.

5. **Append below the rendered board, briefly:** anything you verified that
   contradicts a specialist, anything you could NOT verify (stated as
   such), and auto-fixes committed during the sweep (root-cause fixes to
   audit tooling are in-scope; cluster changes are not).

## Severity semantics (the operator's definition)

- **critical** — external-unauth + exploited-in-the-wild (CISA KEV) + real
  vuln. The ONLY tier that pages. Normally zero.
- **high** — external + real vuln not exploited, or internal + exploited.
  Briefing material.
- **medium** — internal open issue. Maintenance-window queue.
- **low** — policy/hygiene (floating tags, drift, stale charts). Weekly.

Known-open items live in the plans queue and the ops DB — do not
re-litigate them each sweep; report only state CHANGES.
