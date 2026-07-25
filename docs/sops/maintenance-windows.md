# SOP: maintenance-windows — planning + executing NON-safe updates

> Version: `2026.07.25`
> Last Updated: `2026-07-25`

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
3 scheduled windows/week (runbooks/maintenance-windows.yaml)
```

Three roles, deliberately separated: the **sweep** plans + schedules + reports
(never executes); the **planner** investigates one update and writes a plan
(read-only + one file); the **window agent** vets the whole set for conflicts and
runs the approved sequence (delegating cluster changes to `cberg-agent`).

Related: `docs/sops/auto-update.md`, `docs/sops/application-update.md`,
`docs/sops/talos-upgrade.md`, `docs/sops/storage-safety.md`.

## 2) Overview

- **Schedule:** `runbooks/maintenance-windows.yaml` — 3 windows/week
  (Tue 05:00, Thu 05:00 weekday 1h slots; Sun 09:00 90m reboot-capable
  operator-present slot). Each window has a `capacity_risk` (risk-weight budget,
  low1/med2/high3) and an `allow_reboot` flag. Times/capacities are editable
  (git-tracked; bump `version`).
- **Plans:** `runbooks/maintenance/plans/<component>-<target>.md` — frontmatter
  (component, PR, current→target, risk, duration, `needs_reboot`, precise
  `touches`, `depends_on`, `conflicts_with`, status, window) + six body sections
  (Summary & why held, Pre-checks, Steps, Verification, Rollback, Interference
  notes). Schema in `runbooks/maintenance/plans/README.md`. Plans are transient —
  deleted in the commit that lands the upgrade.
- **Reconciler:** `runbooks/maintenance-plan.py` — read-only glue the sweep runs.
  Reports held-updates-without-a-plan, stale/orphan plans, the next window + its
  queue, and capacity/reboot/interference warnings.
- **Agents:** `.claude/agents/upgrade-planner-agent.md` (one per held update),
  `.claude/agents/maintenance-window-agent.md` (runs a window).
- **Execution posture (limited autonomy, enabled 2026-07-25):** a plan runs
  unattended only if `auto_execute: true` AND `risk: low` AND
  `execution.unattended_allowed: true` AND it has no unresolved interference —
  the trivial runs itself. Everything else (any medium/high plan, any
  interference/side-effect conflict, any rollback) is **operator go/no-go** and
  is never silently skipped or auto-decided.
- **Operator notifications (`runbooks/lib/notify.py` → Telegram, the same
  channel Alertmanager pages):** an **urgent** push fires on `decision-needed`,
  `interference-conflict`, `blocked`, and `reverted`; a non-urgent one on
  `window-complete`. A go/no-go left unanswered during a window **defers** (never
  hangs, never auto-runs above `max_unattended_risk`); the plan sits
  `status: awaiting-go` and the **sweep re-reminds you every cycle** until you
  answer or it's superseded. So you always get a proper reminder when a decision
  is yours to make.

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
