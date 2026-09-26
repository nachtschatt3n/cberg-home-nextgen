# SOP: maintenance-windows — planning + executing NON-safe updates

> Version: `2026.09.26`
> Last Updated: `2026-09-26`

## 1) Description

The auto-updater (`docs/sops/auto-update.md`) merges SAFE patch/minor updates at
**Step 0 of EVERY maintenance window** — not on the sweep. The sweep is
READ-ONLY: it dry-runs `auto-update.py` (rule 4c) to report what will land next
window, and applies nothing. Everything the auto-updater HOLDS — majors, breaking-despite-patch,
deny-listed components, node-reboot items — is a **non-safe** update that must be
executed deliberately. This SOP is the pipeline that gets those done without
tangling several risky changes together:

```
auto-update HOLDS an update
      │
      ▼
sweep (rule 4d) → upgrade-planner-agent  ── writes one executable plan per update
      │                                     (runbooks/maintenance/plans/<comp>-<tgt>.md)
      ▼
maintenance-window-agent  ── vets plans for INTERFERENCE + SIDE EFFECTS,
      │                       sequences them, operator go/no-go, executes
      ▼
3 scheduled windows — nightly unattended + sat/sun attended (runbooks/maintenance-windows.yaml)
  + the on-demand `now` slot — an attended NOW run of named, approved plans (§4)
```

Three roles, deliberately separated: the **sweep** plans + schedules + reports
(never executes); the **planner** investigates one update and writes a plan
(read-only + one file); the **window agent** vets the whole set for conflicts and
runs the approved sequence (delegating cluster changes to `cberg-agent`).

Related: `docs/sops/auto-update.md`, `docs/sops/application-update.md`,
`docs/sops/talos-upgrade.md`, `docs/sops/storage-safety.md`.

## 2) Overview

- **Schedule:** `runbooks/maintenance-windows.yaml` — **3 windows (reshaped
  2026-08-26, P1.1)**: `nightly` 03:30 daily 90m unattended no-reboot (Step 0
  safe updates now land EVERY night); `sat-attended` 09:00 90m attended
  no-reboot; `sun-attended` 09:00 90m attended reboot-capable (renamed from
  `sat-early`/`sun-window` in 746eff14, migrated atomically). The 7/week
  schedule this replaces was fictional capacity — four weekday slots never had
  a driving cron, and plans scheduled into them silently never ran. Every
  window now REQUIRES a driving cron (`window-crons.py --check`, asserted
  every sweep) and a `window_runs` row per dated occurrence (asserted every
  sweep). Weekend ids renamed to `sat-attended`/`sun-attended` 2026-08-26, migrated
  atomically with the plans' window refs, both crons, and the live GO records. Daily replaced the 4/week
  aggressive-drain cadence (Tue/Thu/Sat/Sun), which stretched the then-23-plan
  queue to late October; an IDLE window costs nothing — nothing runs unless a
  plan is slotted — so the extra weekday slots are pure optionality. **Daily
  compresses INDEPENDENT work only: it must never be used to collapse a
  deliberate soak** (e.g. `superset-pg-decommission` sits 10 days after the
  cutover on purpose — the old database IS the rollback). **Slot by
  reboot-need, not risk:** Sun is still the only reboot-capable window, so
  reserve it for Talos + app-template churn and push every
  `needs_reboot: false` plan to a weekday or Sat. Each window has a
  `capacity_risk` (risk-weight budget, low1/med2/high3) and an `allow_reboot`
  flag. Times/capacities are editable (git-tracked; bump `version`).
- **On-demand NOW slot (2026-09-15):** a top-level `on_demand:` block in the same
  YAML (id `now`, attended, `allow_reboot: false`, serial, `duration_min: 480`)
  lets the operator run vetted, approved plans immediately instead of waiting
  for their window ("run the X upgrade now"). It is deliberately **not** an entry
  in `windows:`: everything that reads `windows:` asserts a SCHEDULE — cron
  parity (`window-crons.py --check` would demand a cron), per-occurrence
  liveness (`expected_slots` would report it missed every day) and the
  scheduler (`window-scheduler.py` would place work into it). An on-demand slot
  has no schedule, so it can be used but never missed. What does read it:
  `validate_plans` accepts `now:<YYYY-MM-DD>` window refs (no weekday check;
  `est_duration_min` must fit the 480m ceiling; a `needs_reboot` plan may NOT
  carry one), `stuck_window_runs` uses the ceiling for an open `now` row, the
  reconciler's per-slot OVER-TIME / REBOOT / INTERFERENCE / STACKING checks
  (no risk-load budget — the run is operator-chosen and serial), and
  `runbooks/run-now.py`. Full flow in §4 "Run approved plans NOW".
- **A same-day on-demand run covers that day's `nightly` (operator decision
  2026-09-26).** The nightly's job is Step 0, and a NOW / ad-hoc run runs Step 0
  first by contract, so liveness does not report `nightly:<date>` missed when a
  `window_runs` row with slot `now` (or trigger `ad-hoc` in another slot) exists
  whose `started_at` falls on the same **Europe/Berlin** date and which is
  **terminal and not `aborted`** (`green`/`partial`/`revert`/`idle`). An OPEN
  (`running`) or `aborted` row does NOT cover — "started" is not "ran Step 0",
  and the ledger has no Step 0 flag, so completion is the proof. The Berlin date
  of `started_at` is used, not `run_date` (UTC-stamped): a NOW run opened at
  00:30 Berlin covers that Berlin day. **Only `nightly` is covered** —
  `sat-attended` / `sun-attended` carry attended plan capacity and the Sunday
  reboot allowance that a NOW run does not substitute for, and a cron row in
  those slots does not cover the nightly either. Code:
  `maintenance-plan.py:nightly_covered_by_on_demand()`, applied in
  `window_liveness_report()` — the one path behind the sweep's liveness
  section, `reconcile()` and `--liveness-metrics` (which `sweep-run.py` pushes
  to the Pushgateway as `window_runs_missing_count`). Test:
  `runbooks/tests/test-window-liveness-now-covers-nightly.py`.
- **Plans:** `runbooks/maintenance/plans/<component>-<target>.md` — frontmatter
  (component, PR, current→target, risk, duration, `needs_reboot`, precise
  `touches`, `depends_on`, `conflicts_with`, status, window) + six body sections
  (Summary & why held, Pre-checks, Steps, Verification, Rollback, Interference
  notes). Schema in `runbooks/maintenance/plans/README.md`. Plans are transient —
  deleted in the commit that lands the upgrade. **Verification must assert
  CONTENTS, not shape** — every plan carries at least one assertion that would
  fail if the thing it changed were empty/wrong while structurally healthy
  (per-class exemplars in the plans README; failure class and worked examples in
  `docs/sops/verification-contents-not-shape.md`). A plan whose §4 is only
  "Ready/200/healthy" is **not vettable** — the window agent sends it back.
- **Reconciler:** `runbooks/maintenance-plan.py` — read-only glue the sweep runs.
  Reports held-updates-without-a-plan, stale/orphan plans, the next window + its
  queue, and capacity/reboot/interference warnings.
- **Coverage guarantee (no cracks):** `runbooks/coverage.py` (added 2026-08-02)
  closes the hole that the auto-updater only ever sees OPEN Renovate PRs. It
  enumerates the FULL actionable universe from `version-check-current.md` and
  assigns every update a **lane** so nothing falls between the cracks:
  - **AUTO** — safe (patch/minor, not deny-listed): applied in the window
    (window-agent Step 0, **hybrid** — merge the Renovate PR if one exists, else
    **direct-bump** the manifest tag, so a safe update never stalls waiting on
    Renovate's schedule).
    **AUTO disqualifiers (2026-08-18)** — a safe-looking semver label is not
    sufficient; `assign_lane()` also routes to PLAN when:
    1. the target is a **pre-release**: an explicit tag marker (`-beta`, `-rc`,
       `-nightly`, …), MEMBERSHIP in `CHANNEL_RULES` for an upstream that
       pushes dev builds to the SAME repo as stable — so no version string can
       decide the channel, and membership itself is the hold (for scrypted,
       stable-ness depends on whether a non-prerelease GitHub Release exists
       for that exact tag; the old "stable = ODD minors only" rule was
       DISPROVED 2026-09-11 — ~17 even-minor releases carry prerelease=false,
       and it also scored Release-less ODD-minor dev tags as stable) — or an
       active AR declaring the component's pre-release channel unacceptable. The gate sits ABOVE the Renovate-PR shortcut — an
       open PR does not launder a beta. Layers 1-2 are git-tracked on purpose:
       the window agent runs `coverage.py` without `SWEEP_PG_DSN`, so a DB-only
       gate would fail OPEN exactly where it matters.
    2. it is a **0.x release-line move** (`0.175 → 0.178`): at major 0 the minor
       is the breaking axis (same doctrine as `_release_line`).
    3. it is **lockstep-coupled**: a sibling of the same component is PLAN/HELD,
       so a chart must not move ahead of its held image (or vice versa). These
       appear under the `lockstep` key in `coverage.py --json`.
  - **PLAN** — major/deny-listed: needs an assessed window plan. The sweep (rule
    4d0) dispatches an `upgrade-planner-agent` for **every** `needs_plan` item —
    the whole non-safe universe, not just deny-listed open PRs — so the PLAN lane
    covers everything.
  - **REBUILD** — self-built `ghcr.io/nachtschatt3n/*`: can't be tag-bumped,
    surfaced as a human action-row (rebuild in its source repo).
  - **HELD** — explicitly accepted (e.g. openclaw node 22). **CRACK** —
    actionable but in none of the above; **must be zero** → a CRITICAL finding +
    OpenClaw page. The sweep reports lane counts and fails loud on any CRACK.
- **Agents:** `.claude/agents/upgrade-planner-agent.md` (one per held update),
  `.claude/agents/maintenance-window-agent.md` (runs a window).
- **Execution posture (class-based autonomy, P2.1b 2026-08-26; replaces the
  2026-07-25 `auto_execute`+`risk: low` pair):** a plan's execution class is
  DERIVED from declared facts (`capability_change`, `rollback_class`,
  `needs_reboot`, shared-storage touch) against `runbooks/autonomy-policy.yaml`
  — plans cannot claim a class. **AUTO-NIGHT** may execute WITHOUT asking in
  **ANY** window regardless of its `mode:` (widened 2026-09-12, `d147b1ce` —
  the old "`mode: unattended` only" wording contradicted the attended-window
  no-ack rule below, and being stricter it won, so a cron-fired ATTENDED window
  could execute nothing on its own). Still required: no unresolved
  interference, and the plan's category needs `first_runs_supervised` clean
  supervised runs first. `mode:` records whether a human is expected around; it
  does not decide whether pre-approved work may run. **AUTO-BACKUP-GATED**
  additionally requires its named restore-proof `backup_gate` to PASS in the
  window. **HUMAN-GATED** — and every ambiguity, missing fact, or unreadable
  policy — is operator go/no-go, never silently skipped or auto-decided.
  Autonomy is decided by reversibility + capability-change + blast radius,
  deliberately NOT by `risk:` (which stays the capacity weight).
- **Notifications + open-issue tracking are owned by OpenClaw** (skill
  `home-operation`, since 2026-07-25). Emitters route each issue to it via
  `kubectl exec` (contract below); OpenClaw pushes to the operator's Clawd DM,
  holds the open-issue store (keyed by `plan_id`/`finding_id`), reminds on an
  **escalating `tick` cadence** (critical immediately, go/no-go 6h→12h→24h),
  lets the operator **approve/deny/defer conversationally**, surfaces open issues
  in the **morning briefing**, and can **run a plan on say-so** ("run the redis
  upgrade now"). `runbooks/lib/notify.py` (raw Telegram) is only the **fallback**
  when the openclaw pod is unreachable — an alert is never lost. A go/no-go left
  unanswered **defers** (never hangs, never widens autonomy — unattended
  execution stays limited to plans deriving AUTO-* under
  `runbooks/autonomy-policy.yaml`);
  the plan sits `status: awaiting-go` and OpenClaw keeps reminding until you
  answer or it's superseded.

  **Contract (emitters → OpenClaw):**
  ```bash
  # ingest/UPSERT an issue (or JSON array), idempotent by `key`
  kubectl -n ai exec deploy/openclaw -c app -- \
    /home/node/.openclaw/bin/home-operation ingest --json '<issue>'
  # auto-close issues no longer open (pass the current open-key set)
  ... home-operation reconcile --source maintenance --open '<[plan_id,...]>'
  # window agent: pull cleared-to-run decisions, then ack execution
  ... home-operation --json decisions --pending-exec
  ... home-operation resolve --issue <key> --by executed|denied|superseded [--note <commit>]
  ```
  **Two different `--json` flags — placement is not interchangeable.** The
  machine-readable-output switch is a **global** boolean and must come
  **BEFORE** the subcommand (`home-operation --json decisions ...`); putting it
  after fails with `error: unrecognized arguments: --json`, because only
  `ingest` defines a `--json` of its own — and that one is the required
  issue **payload** argument, so it must come **AFTER** `ingest`. Every other
  subcommand (`decisions`, `list`, `brief`, `reconcile`, `resolve`, `decide`,
  `ack`, `tick`, `run`) takes the global form only.
  Issue fields: `key` (plan_id|finding_id, required), `kind`
  (`go_no_go`|`blocked_plan`|`auto_update_revert`|`auto_update_blocked`|
  `window_warning`|`finding`|`reverted` — the last two are emitted by the sweep
  and the auto-updater respectively and were simply never written down until
  2026-08-24. An unknown `kind` matches no `KIND_DEFAULTS`, so `severity` and
  `action` fall back to the generic defaults; when the emitter also omits
  `action` that means `ack`, and a go/no-go silently becomes a passive notice
  nobody is asked to decide. Emitters that pass `action` explicitly dodge it —
  which is why the five `kind=plan` rows in the store still got
  `needs_decision=1`; the trap was latent, not universal. Since 2026-08-23
  ingest coerces a genuinely unknown kind to the nearest valid one and warns on
  stderr rather than accepting it silently),
  `source`, `severity` (`info`|`warning`|`critical`), `title`, `action` (csv;
  containing `approve`/`deny` marks it a decision), + optional `component`,
  `target`, `window`, `plan_path`, `detail`, `url`. **Decision → execution:**
  OpenClaw only records the decision (`exec_state=pending`); the
  maintenance-window-agent pulls it and does the GitOps via `cberg-agent` —
  OpenClaw never mutates the cluster.
- **An approval is scoped to the window it was given for.** If the run failed,
  was rolled back, or the plan slipped, the operator must REVOKE it with
  `home-operation resolve --issue <key> --by cleared --note "<why>"`.
  `--by cleared|denied|superseded|manual` voids the decision so
  `decisions --pending-exec` can never serve it as live authorization again;
  only `--by executed` keeps it, as executed history. Re-approving later is a
  fresh `decide`. Until 2026-08-23 neither voiding happened nor did
  `--pending-exec` filter resolved issues, so a revoked GO — and any issue
  auto-closed by `reconcile` — stayed readable as a current approval. A window
  agent MUST still treat a decision whose `window` has passed as expired, not
  as a standing GO.
- **Durability caveats (both PVC-only, not git):** (1) the `home-operation`
  issue store + the `tick` reminder cron live in OpenClaw's PVC — the skill
  itself is in git (`skills-configmap.sops.yaml`) and re-seeds on boot, but the
  cron must be recreated on PVC loss. (2) The morning-briefing hook is a patch to
  the in-pod `~/clawd/scripts/morning_briefing.py`, which is intentionally NOT in
  git (PII rule). It survives pod rolls but **not a PVC rebuild or a
  briefing-script restore** — the open-issues block would silently vanish. The
  patch is marker-guarded and idempotent (safe to re-run); on a PVC rebuild,
  re-apply it (backup: `morning_briefing.py.bak-*`). If the block disappears from
  the briefing, that's the first thing to check.

## 3) Blueprints

N/A. Git-tracked YAML schedule + Markdown plans + two agent definitions; no
Authentik/Homepage/Longhorn objects.

## 4) Operational Instructions

- **Change the schedule:** edit `runbooks/maintenance-windows.yaml` (days,
  times, capacity, reboot flag), bump `version`, commit, push.
- **Plans get created automatically** on the scheduled sweep (rule 4d dispatches
  an `upgrade-planner-agent` per held update). To force one:
  `Task/Agent → upgrade-planner-agent` with the held update's details.
- **Assign a plan to a window:** set its frontmatter `window: "<id>:<YYYY-MM-DD>"`
  (e.g. `sun-attended:2026-08-30`) and `status: scheduled`.
- **Run a window:** invoke `maintenance-window-agent` ("run the maintenance
  window"). It vets interference/side effects, sequences, and asks go/no-go.
- **Trigger at the window time:** the sweep reports upcoming windows so nothing
  is silently missed. Each slot also *auto-fires* the window agent via a cluster
  OpenClaw cron that drives the Mac `daily-operation`/`server-operation` session
  (mirrors the every-48h sweep cron `8163c139`; same `command`-payload shape).
  The crons run the `maintenance-window` skill (`maintenance-window run --window
  <id>`), which resolves the operation pane with the same fail-loud handoff as
  the `operation` skill and pages the operator on Telegram if the handoff fails
  — so an unattended 03:30/09:00 window is never silently skipped. Firing while
  the operator sleeps is by design: the agent notifies + defers on anything above
  low-risk (it does not auto-run risky/reboot changes unattended). Cron runs are
  tagged `MAINTENANCE_WINDOW_TRIGGER=cron`.

  | Window | Cron (Europe/Berlin) | OpenClaw cron id |
  | --- | --- | --- |
  | `nightly` | `30 3 * * *` | `cd659ac2-180c-4de5-af39-7a339b52eedf` |
  | `sat-attended` | `0 9 * * 6` | `fe1f69f9-bf65-4aec-b49e-0b44f985d43f` |
  | `sun-attended` | `0 9 * * 0` | `d8b8f2a0-61c5-45e7-92ca-aecc8e971917` |

  (tue-early `335e4a3e` and thu-early `a9325ac9` removed 2026-08-26 with the
  reshape. Re-render any command with `runbooks/window-crons.py --render`;
  verify parity any time with `--check`.)
  A window declaring `retry_after_min` also gets a retry cron from `--render`,
  asserted by `--check` (2026-09-14).
  Every driver and retry cron carries a Telegram `failureAlert` whose cooldown
  is **strictly shorter than its period** (daily 20h, weekly 24h; the 48h sweep
  cron `8163c139` uses 44h). A cooldown equal to the period swallowed the
  2026-09-24 nightly failure (F-e6dda67f). `--render` emits the flags (chat id
  from `$FAILURE_ALERT_TO`, never committed); `--check` asserts them.

- **Run approved plans NOW (on demand, attended — 2026-09-15).** The operator
  says "run the grafana upgrade now" to OpenClaw, or types it into the Mac ops
  console. End to end:

  ```
  operator: "run X (and Y) now"
      │  OpenClaw chat                       │  or directly in the ops console
      ▼                                      │
  home-operation run --issue X[,Y]           │
      │  each --issue must be the EXACT key of ONE open go_no_go issue, else
      │  exit 3 (suggestions only) / 5 and NOTHING is recorded; records approve
      │  by "operator (say-so run-now)" (or re-scopes an existing GO) with
      │  window now:<today Europe/Berlin> → exec_state=pending (tick voids it
      │  2 days later if the run never happens). --no-push writes nothing.
      │  Dispatch rc != 0 / exception → the say-so is UNDONE (see §5 exit 8/10)
      ▼                                      │
  maintenance-window run-now --plan X --plan Y
      │  REFUSES (non-zero, nothing sent): exit 10 ANY open `now` window_runs row
      │  (any run_date), exit 7 that ledger unreadable, exit 8 console not at prompt (busy/agents/menu); never
      │  /clears; sends [OPERATOR NOW-RUN — MAINTENANCE_WINDOW_TRIGGER=now, plans=X,Y]
      ▼                                      ▼
  ops console → maintenance-window-agent, "On-demand NOW runs" section
      │  1. window-run-record.py --slot now --outcome running --trigger ad-hoc
      │  2. Step 0 safe updates (every run, this one too)
      │  3. run-now.py preflight X Y --json   (replaces window-occupancy checks)
      │  4. run-now.py stamp <runnable>        (window: now:<date>, via GitOps)
      │  5. execute the sequence SERIALLY, full per-plan contract
      │  6. autonomy-record --slot now --supervised; resolve --by executed
      ▼
  window-run-record.py --finalize --slot now --trigger ad-hoc
  ```

  `runbooks/run-now.py preflight` refuses, per plan and fail-closed: an
  unreadable or missing plan file; any status but `vetted`/`scheduled`/
  `awaiting-go` (draft, blocked, awaiting-soak, executed, superseded, reference
  — with the reason); `needs_reboot` (node rolls stay in `sun-attended`);
  over the ceiling; `depends_on` neither executed nor in the run; no operator
  approval — a pending `approve` scoped to `now:<today|yesterday>` in
  `home-operation --json decisions --pending-exec`, or `--operator-go
  "<who/how>"` given by the operator at the console (recorded as the consent
  source); failing premises. A home-operation exec that fails is NO approval. A
  GO recorded for a scheduled window does not authorize a NOW run (approvals are
  scoped to their window — `run --issue` re-scopes it on the operator's say-so).
  It orders the rest deterministically: shared infra first, then risk
  high→low, stable by plan id, `depends_on` honoured; a declared
  `conflicts_with` pair (either direction) may share a NOW run ONLY because it
  is serial, and the later step is marked `settle_before` so the executor
  settles and re-verifies cluster health between them. Every sequence entry
  carries `depends_on_in_run`, and the executor does not start a step whose
  in-run dependency did not execute green (it revokes that approval with
  `resolve --by cleared`). A plan already stamped `now:<today>` and not executed
  is refused as "already in an on-demand run today" unless `--operator-go`
  AND `--resume` continue the same run. With `--operator-go` the output's
  `running_row_notes` is written into the running row's notes (durable
  consent). Exit 0 all runnable, 1 partial (ask the operator), 2 nothing
  runnable.

  From the console without OpenClaw: `runbooks/run-now.py preflight <ids>`
  first; if the only refusal is the approval, the operator's explicit yes in
  the console becomes `--operator-go`.

  **Durability caveat:** these crons live only in OpenClaw's PVC sqlite (the
  gateway cron store), **not** in git — same as the sweep cron. They survive pod
  rolls but not PVC loss; recreate them with `openclaw cron add` (see the
  `maintenance-window` skill) if the PVC is rebuilt. The `maintenance-window`
  skill itself *is* in git (`skills-configmap.sops.yaml`) and re-seeds on boot.

## 5) Examples

### Reconciler output (sweep's schedule check)

```
== maintenance schedule · 2026-08-27 · 1 held update(s) ==
next window: sun-attended:2026-08-30 09:00 Europe/Berlin (90m, cap 6, reboot=yes)

NEEDS A PLAN (1) — dispatch an upgrade-planner-agent for each:
  • ghcr.io/siderolabs/installer v1.13.6→v1.13.7 (PR #194, held:policy) — Talos node image …
```

### A window with an interference warning

```
scheduled:
  thu-early:2026-07-30: ['ingress-nginx-4.16.0', 'affine-0.27.3']
⚠️  WARNINGS:
  ! INTERFERENCE thu-early:2026-07-30: ingress-nginx-4.16.0 ⋂ affine-0.27.3 share ['ingress']
```

→ the window agent serializes them (ingress first, verify all ingressed apps,
then affine) or defers affine to the next slot.

### A window with two irreversible plans (RISK-CLASS STACKING)

```
⚠️  WARNINGS:
  ! RISK-CLASS STACKING sun-attended:2026-09-14: 2 irreversible plans in one
    slot (paperless-db-12.3.3, mariadb-11.4) — if the second fails there is no
    rollback path for the window. Serialize across slots.
```

Interference by shared namespace/resource was never the whole story: **blast
radius is set by reversibility, not by namespace.** Two plans that touch
nothing in common still cannot share a slot if neither can be rolled back —
once the first has migrated its data directory, a failure in the second leaves
the window with no way back except a restore from backup, and an operator who
already spent the slot's budget.

`maintenance-plan.py` therefore warns when **more than one** plan in a slot
declares `rollback_class` in `("one-way", "backup-restore")`
(`IRREVERSIBLE_ROLLBACK`). Deliberately quiet in two cases: a **single**
irreversible plan (that is normal, and the plan carries its own restore path),
and a plan whose rollback is a **git revert** (reversible by construction).
Added `656ffef8`; the convention was prose-only before that, and
`paperless-db-12.3.3.md` documented it for itself while nothing enforced it.

Resolution is the same as for interference: serialize across slots, so each
irreversible change gets a window where it is the only thing that cannot be
undone.

## 6) Verification Tests

### Test 1: reconciler is read-only and correct

```bash
git status --porcelain            # note current state
.venv/bin/python3 runbooks/maintenance-plan.py --json | python3 -c "import sys,json;d=json.load(sys.stdin);print('held',d['held_count'],'needs_plan',len(d['needs_plan']),'warnings',len(d['warnings']))"
git status --porcelain            # MUST be unchanged (read-only)
```

### Test 2: every held update ends up planned

After a scheduled sweep, `needs_plan` should be empty (a plan exists for each
held update) or every gap explained. A held update with no plan for >1 sweep
cycle is a process failure — dispatch the planner manually.

### Test 3: no window exceeds its budget

`warnings` must contain no `OVER-CAPACITY` / `REBOOT-IN-NONREBOOT` /
unresolved `INTERFERENCE` for any window with a date in the future.

### Test 4b: the NOW trigger is wired end to end (read-only)

```bash
# the preflight reads approvals + premises, never mutates
.venv/bin/python3 runbooks/run-now.py preflight <plan_id> --json | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['window_ref'], d['ok'], [(p['plan_id'], p['reasons']) for p in d['plans']])"
# the exact prompt a NOW run would send (no session touched)
kubectl -n ai exec deploy/openclaw -c app -- /home/node/.openclaw/bin/maintenance-window run-now --plan <plan_id> --dry-run | head -1
# expect: [OPERATOR NOW-RUN — MAINTENANCE_WINDOW_TRIGGER=now, plans=<plan_id>]
python3 runbooks/tests/test-run-now.py && python3 runbooks/tests/test-openclaw-run-now-skill.py
```

### Test 4: every scheduled plan asserts contents, not shape

A plan is only vettable if its Verification section can fail on an *empty but
healthy* outcome. Scan the queue before a window:

```bash
grep -L 'CONTENTS ASSERTION' runbooks/maintenance/plans/*.md
```

Absence of the marker is a prompt to read §4 by hand, not an automatic reject
(several plans assert contents in prose and carry no marker) —
but a §4 that contains only `Ready` / `200` / `healthy` / `Running` and no
count, diff, round-trip or served-bytes check **is** a reject. See
`docs/sops/verification-contents-not-shape.md`.

## 7) Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| `needs_plan` never clears | planner not dispatched, or PR title unparsable | dispatch `upgrade-planner-agent` manually with the details |
| Plan marked STALE, entry carries `age_days` + `reason: unused > stale_after_days` | nothing moved — the plan simply sat unused past `planning.stale_after_days` (14d) without reaching `executed`/`superseded` | re-investigate whether the work is still wanted: refresh and re-date `generated:` if it is, supersede the file if it is not |
| **Plan DRIFTED** — STALE entry carries `plan_target` + `now_target` | the held update RETARGETED after the plan was written (upstream published a newer version, or Renovate moved the PR). `target_covers()` compares version TOKENS between the plan's `target:` and the held `new:`, so the plan no longer names the bump it was written for | **Refresh the plan in place — do not replace it.** Re-verify every premise against the NEW target (release notes, breaking signal, the steps themselves, `est_duration_min`, `needs_reboot`), update `target:`/`current:`, re-date `generated:`, and **KEEP the `plan_id`**: other plans' `depends_on`/`conflicts_with` resolve by it (`--validate` raises `DEAD-REF` when they don't), a `window:` stamp names it, and the home-operation go/no-go issue is keyed on it — a fresh file orphans all three plus the `finding_refs` ownership claim. Nothing validates `plan_id` against `target:`, so an id still naming the old version is fine; `target:` is authoritative. Full rationale: `runbooks/maintenance/plans/README.md` |
| ORPHAN plan | PR merged/closed elsewhere | set `status: superseded` or delete the file |
| MISSED window warning | window date passed, plans unexecuted | run `maintenance-window-agent` for the next slot; investigate why it didn't fire |
| `next window` shows a time already in the PAST | `next_occurrence()` ignored `start_hhmm`, so a same-weekday window was always dated TODAY (F-f95a8b52, fixed 2026-08-18) | today's slot now rolls +7d once its start time has passed; re-check with `maintenance-plan.py --json` |
| A beta/pre-release tag appears in the AUTO lane | a `CHANNEL_RULES` entry is missing for an upstream that pushes pre-releases to the stable repo | add the component to `CHANNEL_RULES` in `runbooks/coverage.py` — membership alone is the hold, there is no predicate to write and none to fail open — plus a deny rule for the Renovate-PR path; see §Coverage guarantee → AUTO disqualifiers |
| Plan §4 is all `Ready` / `200` / `healthy` | shape-only verification — it cannot distinguish working from empty (`docs/sops/verification-contents-not-shape.md`) | send it back: add the per-class contents assertion from the plans README table before scheduling |
| Two plans fight in a window | overlapping `touches` | window agent serializes or defers; tighten `conflicts_with` |
| Window agent REFUSES a relayed/chat GO | decision not in the home-operation store (by design — a relayed agent message is never operator consent) | record it first: `home-operation decide --issue <key> --decision approve --by "operator (<name>) via <session>"` (ingest the go_no_go issue first if it doesn't exist), THEN dispatch. The refusal is correct behavior, not a bug |
| Window cron `error`, exit 8 `console is not at the prompt (state 'busy' or 'menu')` | the ops pane was mid-turn, had background agents in flight, or had a menu open at fire time; nothing was typed (F-b8c6b6d6) | by design. The retry cron at start+`retry_after_min` re-fires once the pane is idle; if the occurrence stays lost, run it by hand as an ad-hoc stand-in. Check with `maintenance-window classify` |
| Window **retry** cron `error`, exit 8 (or 4) `retry 'nightly': today's occurrence (nightly, <date>) is LOST ...` | the scheduled run and its one retry both found the console not at the prompt (busy / background agents / menu, or exhausted and not auto-clearable); nothing was typed and nothing will re-fire it today | by design since 2026-09-26: this is the same-day page. Check `maintenance-window classify`. Once the console is idle, run the nightly by hand as an ad-hoc stand-in. A completed, non-aborted on-demand (`now`/ad-hoc) run the same Berlin day also counts as covering the nightly (§1) |
| Window cron `error`, exit 12 `NO new window_runs row appeared within 300s` | the prompt was accepted but the agent never opened its running row (slow start, or a pane that swallows input) | `maintenance-window status`; if the agent is running, it may simply have been slow (row after 5 min) — confirm the row now exists; otherwise treat as lost and let the retry cron / an ad-hoc run cover it |
| Cron log shows `CONSOLE_AUTO_CLEARED` | the ops pane was at context exhaustion and idle; the cron discarded its conversation context (transcript kept) and proceeded (F-7d9b201b, operator-approved) | expected. If it recurs nightly, a long session is being left in the ops pane — end such sessions with `/clear` |
| `home-operation run --issue X` exits 8 / `MAINTENANCE_WINDOW_HANDOFF_FAILED: ... mid-turn` | the ops console was not at the prompt (mid-turn, background agents in flight, or a menu open); `run-now` never sends into (or /clears) it | nothing is left behind: the say-so is undone (approvals it newly recorded withdrawn → open go/no-go, event `sayso-approval-reverted`; an existing GO it re-scoped gets its original window back, event `rescope-reverted`; the JSON `reverted` list names each). Re-run `home-operation run --issue X` when the console is idle |
| `home-operation run --issue X` exits 10 / `... on-demand NOW run(s) already OPEN (... run_date <d> started_at <ts>)` | a `window_runs` row slot `now`, outcome `running`, not finished, exists — WHATEVER its run_date. A NOW run is still in progress, often waiting at an operator question (it looks idle on screen); an evening run waiting overnight is dated yesterday (UTC), so the guard deliberately has no date filter | by design: answer or finish that run in the console. The say-so was undone as for exit 8. Exit 7 = the ledger could not be read (fail closed, same undo). A row stuck open from a crashed/abandoned run blocks every NOW run until it is finalized — use the run_date the refusal names: `window-run-record.py --finalize --slot now --run-date <d> --outcome aborted --trigger ad-hoc` |
| `home-operation run --issue X` exits 3 with `suggestions` | `run --issue` needs the EXACT issue key — a name/substring that `decide` would accept is refused, so a word in another plan's title can never approve that plan | pick the key from `suggestions` / `home-operation list` with the operator and retry |
| `run-now.py preflight`: "already in an on-demand run today" | the plan is stamped `now:<today>` and not executed — today's NOW run already claimed it | if it is the SAME run continuing (the operator answered a question), re-run with `--operator-go "<who/how>" --resume`; otherwise let that run finish |
| `run-now.py preflight`: "approved for sun-attended:…, not for an on-demand now run" | the GO was scoped to a scheduled window | by design — re-approve for the NOW run with `home-operation run --issue X`, or the operator confirms in the console (`--operator-go`) |
| `run-now.py preflight`: "could not read home-operation approvals (exec failed)" | openclaw pod down / mid-roll | fail-closed by design; wait for the pod, or the operator confirms at the console (`--operator-go`) |
| `STALE ON-DEMAND stamp now:<date>` warning | plans were stamped for a NOW run that did not execute them. Timing: the reconciler warns from day+1 (date < today); `home-operation tick` voids the GO only at ≥ 2 days; `run-now.py` still accepts a `now:` GO dated today or yesterday — so on day+1 the warning shows while the GO may still be live | on day+1: re-run it (`home-operation run --issue <key>`, which re-scopes the GO to today) or revoke it (`resolve --by cleared`) and clear `window:`. From day+2 `tick` has voided the GO: re-approve before re-running, or clear `window:` |
| Background window agent stalls "waiting to settle" | agent ended its turn on a passive wait — background agents get NO timer wakeups | agent must poll in-turn (bounded retries) or explicitly hand the wait back to its coordinator with what-to-check; coordinator: verify the settle yourself and resume it with the result |

### Ops-console delivery path: pane states and exit codes (2026-09-25)

The window crons (`maintenance-window run|retry`) and the 48h sweep cron
(`operation sweep`) deliver by TYPING into the Mac mini ops pane
(`ai-server-ops`). Before typing anything they classify the pane with one pure
function (`classify_pane`, byte-identical in both skills, pinned by
`runbooks/tests/test-openclaw-console-delivery.py`). Read the live state
without typing anything:

```bash
kubectl -n ai exec deploy/openclaw -c app -- sh -lc \
  'OPERATION_SESSION=ai-server-ops /home/node/.openclaw/bin/maintenance-window classify'
```

| Pane state | Looks like | `run` (cron) | `retry` | `run-now` | `operation sweep --trigger cron` |
|---|---|---|---|---|---|
| `idle` | empty or drafted `❯` input, nothing running | deliver (cron: `/clear` + ctrl+u first), then poll | deliver + poll | deliver | deliver |
| `busy` | spinner with `esc to interrupt`, **or** `Waiting for N background agents` / the `← for agents` tray (`openclaude status` calls this "idle" — do not trust it) | **exit 8**, nothing typed | occurrence LOST: **exit 8**, nothing typed (failureAlert pages); row exists: no-op, exit 0 | exit 8 | delivers (not gated — see below) |
| `menu` | question menu, permission prompt, `/resume` list, or no input prompt visible | **exit 8**, nothing typed | occurrence LOST: **exit 8**, nothing typed; row exists: no-op, exit 0 | exit 8 | delivers (not gated) |
| `exhausted-idle` | `/clear to save …` / `100% context used` in the footer, idle, EMPTY input | `/clear`, wait ≤30s for a fresh prompt, log `CONSOLE_AUTO_CLEARED`, deliver | same | **exit 4** (attended, never cleared) | same auto-clear |
| `exhausted-draft` | as above but text in the input | exit 4 | exit 4 | exit 4 | exit 4 |
| `exhausted-busy` | exhausted + spinner / agents / menu | exit 4 | exit 4 | exit 4 | exit 4 |
| `exhausted-unclear` | exhaustion text only in the transcript, not the footer | exit 4 | exit 4 | exit 4 | exit 4 |

**Retry refusals page (operator decision 2026-09-26).** `retry` reads the
ledger first. If a row exists for (slot, today) it is a no-op, exit 0, whatever
the pane shows. If the occurrence is LOST and the pane refuses delivery, retry
exits non-zero: 8 for busy / background agents / menu, 4 for an exhausted pane
that cannot be auto-cleared. Both messages start `retry '<slot>': today's
occurrence (<slot>, <date>) is LOST`. The retry cron's failureAlert (20h
cooldown) then pages the same morning. Before this change the busy/menu case
was a silent exit 0, and the only same-day signal was the 01:30 alert. Exit 8
is reused because it already means "pane not at the prompt, nothing typed".
Exit 4 stays the code for "pane refused, exhausted". Nothing is typed in
either case.

Why a draft blocks auto-clear: at exhaustion the TUI can ignore ctrl+u while
Enter still submits, so typing `/clear` would append to and SUBMIT a stale draft
(the 2026-08-04 wedge had a declined destructive command sitting there). Manual
(`--trigger manual`) calls never auto-clear. Exhausted + busy/draft is the case
for `operation restart` (see the `operation` skill).

**Completion poll.** A `--trigger cron` `run`/`retry` does not report success
on delivery: it polls `window_runs` for (slot, today) for up to 300s
(`--confirm-timeout`, clamped at 540 under the cron's 600s timeout) for the
agent's first-action `running` row. A row that existed before the send does not
count. Say-so runs (`home-operation run --window`, 180s subprocess timeout) do
not poll. Measured 2026-09-15..25: the row lands 0:24–4:10 after the fire.

| Exit | Meaning (maintenance-window) |
|---|---|
| 0 | delivered (and, for cron, the running row appeared), or a retry no-op (a `window_runs` row already exists — nothing lost) |
| 2 | usage |
| 3 / 4 | openclaude unreachable, or the pane was refused (wrong cwd, dead, or exhausted in a non-clearable state, or `/clear` did not take) |
| 5 / 6 | send / ask failed |
| 7 | window_runs ledger unreadable before dispatch (retry, run-now) — nothing sent |
| 8 | pane not at the prompt (busy / background agents / menu) — nothing typed (run, run-now, and retry when the occurrence is LOST) |
| 10 | an on-demand NOW run is still open (run-now) |
| 11 | prompt delivered but window_runs could not be read during the poll |
| 12 | prompt delivered but no new window_runs row appeared in the poll budget |

`operation` keeps its own codes (4 refused/unreachable, 7–9 restart, 11/12
the `--wait` sweep_cycles completion gate). Known gap: `operation sweep` still
does not gate on `busy`/`menu` (its exit 8 already means "Claude survived TERM
and KILL" in `restart`); only its exhaustion handling changed.

### Plan-authoring lessons (2026-08-18, bitnamilegacy-exit-phase1 incident)

- **Verify RBAC per kubectl SUBCOMMAND in plan Jobs.** `kubectl wait
  --for=delete pod/<name>` (and any by-name `get pod/<name>`) needs the `get`
  verb — `list`+`watch` is NOT enough. A selector-form
  `kubectl wait --for=delete pod -l <sel>` rides `list`. Dry-run the exact
  commands under the Job's ServiceAccount (`kubectl auth can-i get pods
  --as=system:serviceaccount:<ns>:<sa>`) as a plan pre-check.
- **Scale-down/up Jobs must not strand the workload.** If a Job's init chain
  is scale-down → wait → work → scale-up, EVERY retry re-runs scale-down and a
  mid-chain failure leaves the app at 0 replicas until intervention. Either
  make scale-up unconditional (separate container/Job that always runs) or
  cap `backoffLimit` low and pair the plan with an explicit "restore replicas"
  rollback step.
- **A plan's "resource X unchanged, re-verified" claim is an assertion to
  RE-TEST at execution time**, not a fact — the paperclip Role claim was wrong
  and cost a 15-min outage.

## 8) Diagnose Examples

```bash
# Full machine-readable schedule state
.venv/bin/python3 runbooks/maintenance-plan.py --json | python3 -m json.tool

# What is queued for the next window?
.venv/bin/python3 runbooks/maintenance-plan.py --json | python3 -c "import sys,json;d=json.load(sys.stdin);w=d['next_windows'][0]['slot'];print(w, d['scheduled'].get(w, []))"
```

## 9) Health Check

```bash
python3 -c "import yaml;yaml.safe_load(open('runbooks/maintenance-windows.yaml'));print('schedule OK')"
.venv/bin/python3 runbooks/maintenance-plan.py >/dev/null && echo "reconciler OK"
ls runbooks/maintenance/plans/*.md 2>/dev/null | grep -v README | wc -l  # active plans
```

## 10) Security Check

- The reconciler + planners are **read-only** against the cluster; the only
  writes are plan files under `runbooks/maintenance/plans/`.
- Execution runs only the operator-approved sequence, one plan at a time, via
  GitOps through `cberg-agent`; nothing here decrypts secrets outside the normal
  SOPS flow.
- Non-safe updates are operator go/no-go by default; only derived AUTO-*
  classes run without asking (see Execution posture above). To disable ALL
  self-running: empty the `classes:` map in `runbooks/autonomy-policy.yaml`
  (or delete the file — fail-safe routes everything to HUMAN-GATED).
- Node-reboot plans run only in an `allow_reboot: true` window and follow
  `docs/sops/talos-upgrade.md`.

## 11) Rollback Plan

```bash
# Pause the whole pipeline: nothing auto-executes anyway (operator go/no-go).
# To stop new plans being created, remove the rule-4d planner dispatch from
# .claude/agents/daily-operation.md (the reconciler stays, still reporting).

# Undo an executed plan: each plan carries its own Rollback section —
# git revert the upgrade commit + confirm restore (Flux reconciles).

# Reschedule everything: clear `window:`/`status:` back to draft in the plan
# frontmatter; the reconciler re-queues them.
```

## 12) References

- Schedule: `runbooks/maintenance-windows.yaml`
- Plans + schema: `runbooks/maintenance/plans/` (README.md)
- Reconciler: `runbooks/maintenance-plan.py`
- On-demand NOW runs: `runbooks/run-now.py` (preflight + stamp), OpenClaw skills
  `home-operation run --issue` / `maintenance-window run-now`
- Agents: `.claude/agents/{upgrade-planner-agent,maintenance-window-agent}.md`
- Sweep hook: `.claude/agents/daily-operation.md` rule 4d
- Upstream of the pipeline: `docs/sops/auto-update.md`
- Per-upgrade procedure the plans follow: `docs/sops/application-update.md`,
  `docs/sops/talos-upgrade.md`

## Version History

| Version | Date | Change |
|---|---|---|
| 2026.09.26 | 2026-09-26 | **Retry refusals page (operator decision).** `maintenance-window retry` used to no-op with exit 0 when the occurrence was LOST but the console was busy or in a menu, which left the 01:30 alert as the only same-day signal. It now exits 8, nothing typed, with a message naming the lost (slot, date), so the retry cron's failureAlert fires. An exhausted pane that cannot be auto-cleared still exits 4, now with the same LOST wording. When a row exists, retry stays a no-op with exit 0. Test `runbooks/tests/test-openclaw-console-delivery.py`. |
| 2026.09.26 | 2026-09-26 | **A same-day on-demand run covers the nightly (operator decision).** `expected_slots`/`missing_window_runs` counted `(nightly, date)` missed unless a nightly row existed, so a day spent in an attended NOW run paged a missed nightly although Step 0 ran. A completed, non-aborted `now`/ad-hoc row on the same Europe/Berlin date (of `started_at`) now covers it; open or aborted rows do not; sat/sun are not covered. Same function feeds the Pushgateway liveness push. Test `runbooks/tests/test-window-liveness-now-covers-nightly.py`. |
| 2026.09.25 | 2026-09-25 | **Ops-console delivery states (F-b8c6b6d6, F-7d9b201b).** `maintenance-window run` typed the nightly prompt into a mid-turn console (skipping only `/clear`, still sending ctrl+u) and exited ok — 09-21/09-22 lost; the busy marker `" esc to "` matched menus and missed `Waiting for N background agents`. Now one pure `classify_pane` in both skills: run refuses exit 8 on busy/menu, nothing typed; cron runs poll ≤300s for the Step 0 running row (exit 12/11); an exhausted-but-idle pane with an empty input is auto-`/clear`ed for unattended runs (operator decision) instead of exit 4; `classify` verb; new §7 subsection + test `runbooks/tests/test-openclaw-console-delivery.py`. |
| 2026.09.25 | 2026-09-25 | **Failure-alert cooldown < period (F-e6dda67f).** The nightly driver cron's `failureAlert.cooldownMs` equalled its 24h period, so the 09-24 failure landed 0.3s inside the cooldown and was swallowed; the nightly retry cron had no failureAlert. Live: nightly 24h→20h, retry gained a Telegram alert (20h), sweep cron `8163c139` 24h→44h; sat/sun (weekly, 24h) already compliant. `window-crons.py --render` now emits the alert flags and `--check` asserts presence + cooldown < period (`runbooks/tests/test-window-cron-failure-alert.py`). |
| 2026.09.22 | 2026-09-22 | **§7 had no row for a DRIFTED plan — the case where the held update retargets after the plan was written (F-e1002c61).** The word "drift" appeared nowhere in this SOP. `maintenance-plan.py` files a drifted plan under the same **STALE plans** headline as the age-based case, but the two need opposite responses, and the single row present ("PR target moved / >stale_after_days old → re-run the planner; supersede the old file") taught the wrong one for the more common case: superseding a drifted plan raises `DEAD-REF` on every `depends_on`/`conflicts_with` naming it, drops its `window:` stamp and its home-operation go/no-go issue key, and abandons its `finding_refs` ownership claim. Split into two rows keyed on which fields the reconciler entry actually carries (`plan_target`+`now_target` = refresh in place; `reason: unused > stale_after_days` = nothing moved), and mirrored as a new section in `runbooks/maintenance/plans/README.md`. |
| 2026.09.13 | 2026-09-13 | **Two stale assertions corrected, both of a kind that has already cost a window.** (a) §1 said the auto-updater "merges SAFE patch/minor updates on the scheduled sweep" — the retired "sweep-applies" model; the sweep is READ-ONLY and safe updates land at Step 0 of every window, as §2 of this same SOP already said. (b) §Execution posture still said AUTO-NIGHT "runs unattended in `mode: unattended` windows" — the exact wording `d147b1ce` removed from `maintenance-window-agent.md`, `autonomy-policy.yaml` and `maintenance-windows.yaml` on 2026-09-12 because, being the stricter of two contradictory rules, it meant a cron-fired ATTENDED window could execute NOTHING. This SOP was the fourth site and was missed. |
| 2026.09.14 | 2026-09-14 | **Lost-occurrence retry + in-flight rows.** A window may declare `retry_after_min` (nightly: 135 → 05:45); `window-crons.py --render` then also emits a `Maintenance Window — <id> retry` cron and `--check` asserts it. The retry verb (`maintenance-window retry --window <id>`, in the OpenClaw skill) no-ops when ANY `window_runs` row exists for (slot, today) — including the new `--outcome running` row the window agent now writes at Step 0 start and closes with `--finalize` — and fails closed on an unreadable ledger. `maintenance-plan.py` reports a never-finalized running row under `window_liveness.stuck`. Also: scheduler refuses plans with absent/failing premises; nightly window dispatches planners for `needs_plan` items; two aborts on one plan in a window → blocked; every executed plan is recorded via `autonomy-record.py` before the finalize (ledger backfilled with 24 audited executions; chart/image AUTO-NIGHT graduated). Operator-approved mechanics; no gate/threshold/deny rule changed. |
| 2026.09.15 | 2026-09-15 | **Active NOW trigger (operator request).** The say-so path existed but was dead: `home-operation run --issue` resolved the issue to its SCHEDULED window id and fired a normal window run (which found nothing due today and went idle), and both skills still named the retired `tue-early`/`thu-early`/`sun-window` ids. Now: top-level `on_demand:` slot `now` in `maintenance-windows.yaml` (attended, no reboot, serial, 480m ceiling; outside `windows:` so cron parity, liveness and the scheduler are untouched); `validate_plans` accepts `now:<date>` refs; stuck detection uses the ceiling for `now` rows; new `runbooks/run-now.py` (fail-closed preflight + deterministic serial order with conflict-pair settle flags + frontmatter-only stamp); `home-operation run --issue` records/re-scopes the approval to `now:<today>` and calls the new `maintenance-window run-now` verb, which refuses a mid-turn console and never /clears; hardened after adversarial review: `run --issue` needs an EXACT key (a substring once approved the wrong plan), `run-now` refuses while ANY open `now` window_runs row exists, whatever its run_date — an evening run waiting overnight is dated yesterday; a stale row must be finalized first (exit 10, the refusal names the row's run_date + started_at; unreadable ledger exit 7), a failed dispatch undoes the say-so (new approvals withdrawn, re-scoped GOs get their window back), `--no-push` writes nothing, preflight refuses plans already stamped `now:<today>` without `--operator-go --resume`, `sequence` carries `depends_on_in_run` and a step whose dependency was not green is not started, `--operator-go` consent is written into the running row, `run/retry --window now` are refused; window agent gained an "On-demand NOW runs" section (row first, Step 0 still first, only the named plans, `--supervised`, finalize `--slot now`). Retired window ids are refused with their replacement. |
| 2026.09.11 | 2026-09-11 | `CHANNEL_RULES` is now **membership, not a predicate**. The `"stable": "odd-minor"` rule for scrypted was DISPROVED (~17 even-minor releases carry `prerelease=false`) and, worse, failed OPEN: a Release-less ODD-minor dev tag scored stable and would have been applied UNATTENDED at Step 0 onto a privileged NVR, with the `auto-update-policy.yaml` deny rule as the only thing holding the door. Stable-ness depends on whether upstream published a non-prerelease Release for that EXACT tag — which no version string can answer — so membership alone is the hold. Membership stays offline-decidable, which the window agent requires. |
| 2026.09.05 | 2026-09-05 | Documented the **RISK-CLASS STACKING** detector (`656ffef8`): >1 irreversible plan (`rollback_class` one-way/backup-restore) in one slot has no rollback path for the window; quiet on a single irreversible plan and on git-revert rollbacks. Blast radius is set by reversibility, not namespace. |
| 2026.07.25 | 2026-07-25 | Initial SOP. 3 windows/week; per-held-update planner agent; window agent vets interference + side effects, sequences, operator go/no-go; sweep reconciles + reports the schedule. |
| 2026.08.02 | 2026-08-02 | Added `coverage.py` no-cracks guarantee (AUTO/PLAN/REBUILD/HELD/CRACK lanes; window-agent Step 0 hybrid PR-merge-or-direct-bump; sweep rule 4d0 dispatches a planner for the full non-safe universe + pages on any CRACK). Aggressive-drain schedule: added Sat window (4/week), raised weekday `capacity_risk` 4→6; slot by reboot-need not risk. |
| 2026.08.19 | 2026-08-19 | Documented the **AUTO-lane disqualifiers** (pre-release channel gate incl. `CHANNEL_RULES`, 0.x release-line moves, chart↔image lockstep) and the two troubleshooting rows for them + the past-dated `next window` bug (F-f95a8b52). |
| 2026.08.26 | 2026-08-26 | **Reshape 7 -> 3** (P1.1): `nightly` 03:30 daily unattended replaces the five weekday slots (four of which never had a driving cron — the schedule was partly fictional); sat/sun stay attended. New enforcement: `window-crons.py --check` cron↔YAML parity + `window_runs` per-occurrence liveness, both asserted every sweep. GO auto-expiry in `home-operation tick`. |
| 2026.08.16 | 2026-08-16 | Cadence 4 windows/week -> **7 (daily)**: added Mon/Wed/Fri 05:00 60m no-reboot slots, all windows at `capacity_risk: 6`. Drains the plan queue to 2026-09-13 instead of late October. Soaks are NOT compressible by the extra slots. |
| 2026.08.23 | 2026-08-23 | **Approval revocation**: `resolve --by cleared|denied|superseded|manual` now VOIDS the decision, and `decisions --pending-exec` excludes resolved issues. Previously a revoked GO (and any issue auto-closed by `reconcile`) stayed readable as live authorization — found on `bitnamilegacy-exit-nextcloud-db`, a high-risk DB migration whose 2026-08-19 GO survived its own rollback. |
