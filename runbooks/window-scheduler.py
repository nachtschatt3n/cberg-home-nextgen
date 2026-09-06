#!/usr/bin/env python3
"""window-scheduler — assign auto-capable plans to a window, so nights stop idling.

WHY THIS EXISTS
`maintenance-plan.py` DERIVES each plan's execution class and then does nothing
with it. Window assignment is the `window:` field, written by hand. Measured
2026-09-06: eight plans derived AUTO-*, all eight sat at `window: null`, and the
nightly window had executed 0 plans across its first 7 runs while every one of
the 10 plan executions in 11 days happened in an attended weekend slot.

THE GRADUATION LOOP, AND HOW THIS CLOSES IT
`autonomy-policy.yaml` only lets a plan CATEGORY run unattended after N clean
SUPERVISED runs. Supervised runs happen in attended windows. But nothing ever
scheduled an auto-capable plan into any window, so no category could accumulate
runs, so none could graduate — a loop with no entry point.

So this scheduler routes by track record rather than refusing:

    category NOT graduated  ->  next ATTENDED window   (earn the supervised runs)
    category graduated      ->  next UNATTENDED window (nights, unsupervised)

That is the ITIL standard-change ramp the policy already describes, made
executable. A category walks itself from supervised to autonomous instead of
waiting for someone to notice it never started.

WHAT IT REFUSES TO SCHEDULE, AND WHY EACH REFUSAL IS LOAD-BEARING

  status not vetted     `draft` means nobody has confirmed the plan is correct.
                        Not theoretical: `paperclip-base-images` derives
                        AUTO-NIGHT while its own target field reads
                        "RECOMMENDED: DO NOT EXECUTE", and draft status is the
                        only thing standing between it and a window.
  dead status           blocked / executed / superseded. `paperless-db` was
                        blocked for a premise that would have dropped an
                        integrity check, and still derived an auto class.
  AUTO-BACKUP-GATED     deliberately EXCLUDED for now. Both plans in that class
                        today are the two that were caught mid-execution as
                        data-loss traps. Backup-gating protects against a bad
                        outcome; it does not protect against a plan whose
                        premises stopped being true. Admit this class only after
                        premise validation exists.
  unmet depends_on      `superset-pg-18.6` hard-depends on `superset-6.1.0`,
                        which has not executed.
  conflicts_with        never two conflicting plans in one slot.
  over capacity         risk-load against `capacity_risk`, and minutes against
                        `duration_min` LESS a reserve for Step 0, which applies
                        safe updates in every window before any plan runs.

DEFAULT IS DRY-RUN. `--apply` writes the `window:` field back into the plan
frontmatter and nothing else; it never touches the cluster.

    window-scheduler.py                 # show what would be assigned, and why not
    window-scheduler.py --json
    window-scheduler.py --apply
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

# A plan is schedulable only once someone has confirmed it. `draft` is the
# pipeline's "not reviewed yet" and must stay meaningful — the whole point of
# automating scheduling is to remove clerical work, not review.
SCHEDULABLE_STATUSES = ("vetted", "scheduled")

# Classes this scheduler is willing to place. AUTO-BACKUP-GATED is absent on
# purpose; see the module docstring.
SCHEDULABLE_CLASSES = ("AUTO-NIGHT",)

# Step 0 (safe-update apply) runs in EVERY window before any plan. Scheduling a
# plan into the full nominal duration would routinely overrun.
STEP0_RESERVE_MIN = 20

RISK_WEIGHT = {"low": 1, "medium": 2, "high": 4}


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, SCRIPT_DIR / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def risk_of(plan) -> str:
    # `risk:` frequently carries a trailing comment in these files.
    return str(plan.get("risk") or "medium").split()[0].strip().lower()


def upcoming_slots(cfg, today, horizon_days=21):
    """Every dated window occurrence in the horizon, earliest first."""
    days = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
            "friday": 4, "saturday": 5, "sunday": 6}
    out = []
    for back in range(0, horizon_days + 1):
        d = today + dt.timedelta(days=back)
        for w in cfg.get("windows", []):
            day = str(w.get("day", "")).lower()
            wd = days.get(day)
            if day != "daily" and wd != d.weekday():
                continue
            # today's occurrence has probably already fired
            if back == 0:
                continue
            out.append({**w, "date": d.isoformat(), "slot": f"{w['id']}:{d.isoformat()}"})
    return out


def slot_load(slot, plans):
    """(risk_load, minutes) already committed to a dated slot."""
    here = [p for p in plans if p.get("window") == slot]
    return (sum(RISK_WEIGHT.get(risk_of(p), 2) for p in here),
            sum(int(p.get("est_duration_min") or 0) for p in here))


def assign(plans, cfg, classes, graduated, today, horizon_days=21):
    """Pure planner. Returns (assignments, skipped).

    `graduated` maps category -> bool. `classes` maps plan_id -> execution class.
    No DB, no filesystem, no clock — so every refusal below is directly testable.
    """
    executed = {p.get("plan_id") for p in plans
                if str(p.get("status")) == "executed"}
    slots = upcoming_slots(cfg, today, horizon_days)
    # working copy so successive assignments see each other's capacity use
    live = [dict(p) for p in plans]
    by_id = {p.get("plan_id"): p for p in live}

    assignments, skipped = [], []

    def skip(plan, reason):
        skipped.append({"plan_id": plan.get("plan_id"), "reason": reason})

    # smallest first: a 20-minute plan should not be blocked by a 90-minute one
    todo = sorted([p for p in live if not p.get("window")],
                  key=lambda p: int(p.get("est_duration_min") or 0))

    for plan in todo:
        pid = plan.get("plan_id")
        klass = classes.get(pid, "HUMAN-GATED")
        status = str(plan.get("status") or "").strip()

        if klass not in SCHEDULABLE_CLASSES:
            skip(plan, f"class {klass} is not auto-schedulable")
            continue
        if status not in SCHEDULABLE_STATUSES:
            skip(plan, f"status {status!r} — only {'/'.join(SCHEDULABLE_STATUSES)} are scheduled")
            continue

        unmet = [d for d in (plan.get("depends_on") or []) if d not in executed]
        if unmet:
            skip(plan, f"unmet depends_on: {', '.join(unmet)}")
            continue

        want_attended = not graduated.get(
            f"{plan.get('kind')}/{klass}", False)
        dur = int(plan.get("est_duration_min") or 0)
        conflicts = set(plan.get("conflicts_with") or [])

        placed = None
        for s in slots:
            attended = str(s.get("mode")) == "attended"
            if want_attended != attended:
                continue
            if dur and not s.get("allow_reboot") and plan.get("needs_reboot"):
                continue
            # never share a slot with a declared conflict
            here = {p.get("plan_id") for p in live if p.get("window") == s["slot"]}
            if conflicts & here:
                continue
            rload, rmins = slot_load(s["slot"], live)
            if rload + RISK_WEIGHT.get(risk_of(plan), 2) > int(s.get("capacity_risk", 4)):
                continue
            budget = int(s.get("duration_min") or 0) - STEP0_RESERVE_MIN
            if rmins + dur > budget:
                continue
            placed = s
            break

        if not placed:
            skip(plan, f"no {'attended' if want_attended else 'unattended'} slot in horizon "
                       f"with room for {dur}m at risk {risk_of(plan)}")
            continue

        by_id[pid]["window"] = placed["slot"]
        assignments.append({
            "plan_id": pid, "slot": placed["slot"], "class": klass,
            "category": f"{plan.get('kind')}/{klass}",
            "reason": ("earning supervised runs — category not yet graduated"
                       if want_attended else
                       "category graduated — eligible for unattended execution"),
            "minutes": dur, "risk": risk_of(plan),
        })

    return assignments, skipped


def write_window(path: Path, slot: str, note: str) -> None:
    """Set `window:` in a plan's frontmatter, preserving everything else."""
    text = path.read_text()
    m = re.search(r"^window:.*$", text, re.M)
    line = f'window: "{slot}"   # {note}'
    if m:
        text = text[:m.start()] + line + text[m.end():]
    else:  # insert before the closing frontmatter fence
        parts = text.split("---", 2)
        parts[1] = parts[1].rstrip("\n") + "\n" + line + "\n"
        text = "---".join(parts)
    path.write_text(text)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true",
                    help="write the assignments into the plan files (default: dry run)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--horizon-days", type=int, default=21)
    args = ap.parse_args()

    mp = _load("mp", "maintenance-plan.py")
    ar = _load("ar", "autonomy-record.py")

    cfg = mp.load_windows()
    plans = mp.load_plans(cfg)
    policy = mp.load_autonomy_policy()
    classes = {p.get("plan_id"): mp.execution_class(p, policy)[0] for p in plans}

    # graduation: unreadable track record => nothing is graduated => everything
    # routes to an attended window. Denying autonomy on an unreadable ledger is
    # the safe direction, and it is the same rule autonomy-record.py applies.
    threshold = ar.load_policy()
    graduated, verified = {}, False
    conn = ar._connect()
    if conn is not None and threshold is not None:
        with conn, conn.cursor() as cur:
            for row in ar._track_record(cur):
                graduated[row["category"]] = row["clean_supervised"] >= threshold
        verified = True

    today = dt.date.fromisoformat(os.environ.get("SCHEDULER_TODAY",
                                                 dt.date.today().isoformat()))
    assignments, skipped = assign(plans, cfg, classes, graduated, today,
                                  args.horizon_days)

    out = {"today": today.isoformat(), "track_record_verified": verified,
           "threshold": threshold, "graduated": graduated,
           "assignments": assignments, "skipped": skipped,
           "applied": bool(args.apply)}

    if args.apply:
        by_id = {p.get("plan_id"): p for p in plans}
        for a in assignments:
            p = by_id[a["plan_id"]]
            write_window(Path(p["_path"]), a["slot"],
                         f"AUTO-ASSIGNED {today.isoformat()} by window-scheduler "
                         f"({a['class']}; {a['reason']})")

    if args.json:
        print(json.dumps(out, indent=2))
        return 0

    if not verified:
        print("track record NOT VERIFIED — every category treated as unproven, "
              "so nothing routes to an unattended window")
    print(f"assignments ({len(assignments)}):" if assignments else "assignments: none")
    for a in assignments:
        print(f"  {a['plan_id']:30} -> {a['slot']:24} {a['minutes']:>3}m  {a['reason']}")
    print(f"\nnot scheduled ({len(skipped)}):")
    for s in skipped:
        print(f"  {s['plan_id']:30} {s['reason']}")
    if not args.apply and assignments:
        print("\n(dry run — re-run with --apply to write these into the plan files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
