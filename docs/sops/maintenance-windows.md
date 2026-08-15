# SOP: maintenance-windows — planning + executing NON-safe updates

> Version: `2026.08.16`
> Last Updated: `2026-08-16`

## 1) Description

The auto-updater (`docs/sops/auto-update.md`) merges SAFE patch/minor updates on
the scheduled sweep. Everything it HOLDS — majors, breaking-despite-patch,
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
7 scheduled windows/week — DAILY (runbooks/maintenance-windows.yaml)
```

Three roles, deliberately separated: the **sweep** plans + schedules + reports
(never executes); the **planner** investigates one update and writes a plan
(read-only + one file); the **window agent** vets the whole set for conflicts and
runs the approved sequence (delegating cluster changes to `cberg-agent`).

Related: `docs/sops/auto-update.md`, `docs/sops/application-update.md`,
`docs/sops/talos-upgrade.md`, `docs/sops/storage-safety.md`.

## 2) Overview

- **Schedule:** `runbooks/maintenance-windows.yaml` — **7 windows/week
  (DAILY since 2026-08-16)**: Mon/Tue/Wed/Thu/Fri 05:00 60m no-reboot slots;
  Sat 09:00 90m no-reboot slot; Sun 09:00 90m reboot-capable operator-present
  slot. Every window carries `capacity_risk: 6`. Daily replaced the 4/week
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
- **Plans:** `runbooks/maintenance/plans/<component>-<target>.md` — frontmatter
  (component, PR, current→target, risk, duration, `needs_reboot`, precise
  `touches`, `depends_on`, `conflicts_with`, status, window) + six body sections
  (Summary & why held, Pre-checks, Steps, Verification, Rollback, Interference
  notes). Schema in `runbooks/maintenance/plans/README.md`. Plans are transient —
  deleted in the commit that lands the upgrade.
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
- **Execution posture (limited autonomy, enabled 2026-07-25):** a plan runs
  unattended only if `auto_execute: true` AND `risk: low` AND
  `execution.unattended_allowed: true` AND it has no unresolved interference —
  the trivial runs itself. Everything else (any medium/high plan, any
  interference/side-effect conflict, any rollback) is **operator go/no-go** and
  is never silently skipped or auto-decided.
- **Notifications + open-issue tracking are owned by OpenClaw** (skill
  `home-operation`, since 2026-07-25). Emitters route each issue to it via
  `kubectl exec` (contract below); OpenClaw pushes to the operator's Clawd DM,
  holds the open-issue store (keyed by `plan_id`/`finding_id`), reminds on an
  **escalating `tick` cadence** (critical immediately, go/no-go 6h→12h→24h),
  lets the operator **approve/deny/defer conversationally**, surfaces open issues
  in the **morning briefing**, and can **run a plan on say-so** ("run the redis
  upgrade now"). `runbooks/lib/notify.py` (raw Telegram) is only the **fallback**
  when the openclaw pod is unreachable — an alert is never lost. A go/no-go left
  unanswered **defers** (never hangs, never auto-runs above `max_unattended_risk`);
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
  ... home-operation decisions --json --pending-exec
  ... home-operation resolve --issue <key> --by executed|denied|superseded [--note <commit>]
  ```
  Issue fields: `key` (plan_id|finding_id, required), `kind`
  (`go_no_go`|`blocked_plan`|`auto_update_revert`|`auto_update_blocked`|`window_warning`),
  `source`, `severity` (`info`|`warning`|`critical`), `title`, `action` (csv;
  containing `approve`/`deny` marks it a decision), + optional `component`,
  `target`, `window`, `plan_path`, `detail`, `url`. **Decision → execution:**
  OpenClaw only records the decision (`exec_state=pending`); the
  maintenance-window-agent pulls it and does the GitOps via `cberg-agent` —
  OpenClaw never mutates the cluster.
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
  (e.g. `sun-window:2026-07-27`) and `status: scheduled`.
- **Run a window:** invoke `maintenance-window-agent` ("run the maintenance
  window"). It vets interference/side effects, sequences, and asks go/no-go.
- **Trigger at the window time:** the sweep reports upcoming windows so nothing
  is silently missed. Each slot also *auto-fires* the window agent via a cluster
  OpenClaw cron that drives the Mac `daily-operation`/`server-operation` session
  (mirrors the every-48h sweep cron `8163c139`; same `command`-payload shape).
  The crons run the `maintenance-window` skill (`maintenance-window run --window
  <id>`), which resolves the operation pane with the same fail-loud handoff as
  the `operation` skill and pages the operator on Telegram if the handoff fails
  — so an unattended 05:00/09:00 window is never silently skipped. Firing while
  the operator sleeps is by design: the agent notifies + defers on anything above
  low-risk (it does not auto-run risky/reboot changes unattended). Cron runs are
  tagged `MAINTENANCE_WINDOW_TRIGGER=cron`.

  | Window | Cron (Europe/Berlin) | OpenClaw cron id |
  | --- | --- | --- |
  | `tue-early` | `0 5 * * 2` | `335e4a3e-36e1-481a-81a7-6c59caa1be65` |
  | `thu-early` | `0 5 * * 4` | `a9325ac9-443a-41d3-a386-d8f6402e0ea3` |
  | `sun-window` | `0 9 * * 0` | `d8b8f2a0-61c5-45e7-92ca-aecc8e971917` |

  **Durability caveat:** these crons live only in OpenClaw's PVC sqlite (the
  gateway cron store), **not** in git — same as the sweep cron. They survive pod
  rolls but not PVC loss; recreate them with `openclaw cron add` (see the
  `maintenance-window` skill) if the PVC is rebuilt. The `maintenance-window`
  skill itself *is* in git (`skills-configmap.sops.yaml`) and re-seeds on boot.

## 5) Examples

### Reconciler output (sweep's schedule check)

```
== maintenance schedule · 2026-07-25 · 1 held update(s) ==
next window: sun-window:2026-07-26 09:00 Europe/Berlin (90m, cap 6, reboot=yes)

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

## 7) Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| `needs_plan` never clears | planner not dispatched, or PR title unparsable | dispatch `upgrade-planner-agent` manually with the details |
| Plan marked STALE | PR target moved / >stale_after_days old | re-run the planner; supersede the old file |
| ORPHAN plan | PR merged/closed elsewhere | set `status: superseded` or delete the file |
| MISSED window warning | window date passed, plans unexecuted | run `maintenance-window-agent` for the next slot; investigate why it didn't fire |
| Two plans fight in a window | overlapping `touches` | window agent serializes or defers; tighten `conflicts_with` |

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
- Non-safe updates are operator go/no-go by default. `unattended_allowed: true`
  (enabled 2026-07-25) permits ONLY `auto_execute: true` + `risk: low` plans to
  run without asking; `max_unattended_risk: low` is the hard ceiling and set
  `unattended_allowed: false` to disable all self-running.
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
- Agents: `.claude/agents/{upgrade-planner-agent,maintenance-window-agent}.md`
- Sweep hook: `.claude/agents/daily-operation.md` rule 4d
- Upstream of the pipeline: `docs/sops/auto-update.md`
- Per-upgrade procedure the plans follow: `docs/sops/application-update.md`,
  `docs/sops/talos-upgrade.md`

## Version History

| Version | Date | Change |
|---|---|---|
| 2026.07.25 | 2026-07-25 | Initial SOP. 3 windows/week; per-held-update planner agent; window agent vets interference + side effects, sequences, operator go/no-go; sweep reconciles + reports the schedule. |
| 2026.08.02 | 2026-08-02 | Added `coverage.py` no-cracks guarantee (AUTO/PLAN/REBUILD/HELD/CRACK lanes; window-agent Step 0 hybrid PR-merge-or-direct-bump; sweep rule 4d0 dispatches a planner for the full non-safe universe + pages on any CRACK). Aggressive-drain schedule: added Sat window (4/week), raised weekday `capacity_risk` 4→6; slot by reboot-need not risk. |
| 2026.08.16 | 2026-08-16 | Cadence 4 windows/week -> **7 (daily)**: added Mon/Wed/Fri 05:00 60m no-reboot slots, all windows at `capacity_risk: 6`. Drains the plan queue to 2026-09-13 instead of late October. Soaks are NOT compressible by the extra slots. |
