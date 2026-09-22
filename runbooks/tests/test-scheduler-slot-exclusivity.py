#!/usr/bin/env python3
"""Regression tests: `exclusive: true` is a slot guard, in BOTH directions.

F-48a45acf — a plan's hardest scheduling constraint ("nothing else may run in
my window") was enforced by NOTHING: `grep -c exclusiv window-scheduler.py`
read 0 on 2026-09-22. `conflicts_with` cannot express it (it names specific
plans; the plan written next week is not on the list) and capacity cannot
either (a 10-minute low-risk plan fits beside anything).

Pinned here:
  * an exclusive candidate is refused an occupied slot, and takes the next
    empty one;
  * ANY candidate is refused a slot an exclusive plan already holds (the
    occupant's declaration binds every later arrival);
  * two plain plans still share a slot (the guard is not over-broad);
  * only a BARE boolean counts — the string "true" is not exclusive for the
    scheduler and IS a --validate error, so a typo can neither reserve a
    window silently nor drop the constraint silently;
  * the skip reason names exclusivity when that is what blocked every slot;
  * validate_plans() reports an exclusive plan sharing a hand-written window
    (the scheduler's guard never sees a window written by hand).

Run: python3 runbooks/tests/test-scheduler-slot-exclusivity.py
"""
from __future__ import annotations

import datetime as dt
import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ws = _load("ws", "runbooks/window-scheduler.py")
mp = _load("mp", "runbooks/maintenance-plan.py")

FAILURES: list[str] = []
ERROR_MARKS = ("Traceback", "Exception:", "Error:")


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


def count(population, pred) -> int:
    items = list(population)
    if not items:
        raise AssertionError("count(): EMPTY population — nothing was observed")
    joined = "\n".join(str(x) for x in items)
    if any(m in joined for m in ERROR_MARKS):
        raise AssertionError(f"count(): population carries error text: {joined[:120]!r}")
    return sum(1 for x in items if pred(x))


# nightly only: every night is a candidate slot, so "next empty slot" is the
# following night and the test reads without a calendar.
CFG = {"windows": [
    {"id": "nightly", "day": "daily", "duration_min": 90,
     "capacity_risk": 6, "allow_reboot": False, "mode": "unattended"},
]}
MONDAY = dt.date(2026, 9, 7)
TUE, WED = "nightly:2026-09-08", "nightly:2026-09-09"


def plan(pid, **kw):
    base = {"plan_id": pid, "kind": "image", "status": "vetted", "window": None,
            "risk": "low", "est_duration_min": 10, "depends_on": [],
            "conflicts_with": [], "needs_reboot": False}
    base.update(kw)
    return base


def run(plans, horizon_days=21):
    classes = {p["plan_id"]: "AUTO-NIGHT" for p in plans}
    graduated = {"image/AUTO-NIGHT": True}    # route to the unattended nightly
    return ws.assign(plans, CFG, classes, graduated, MONDAY, horizon_days,
                     premises_check=lambda pid: (True, "fixture"))


def slot_of(assignments, pid):
    return next((a["slot"] for a in assignments if a["plan_id"] == pid), None)


def reason_for(skipped, pid):
    return next((s["reason"] for s in skipped if s["plan_id"] == pid), "")


def scheduler_scenarios() -> dict:
    out = {}
    # direction 1: the CANDIDATE is exclusive, the slot is occupied
    a, s = run([plan("occupant", status="scheduled", window=TUE),
                plan("excl", exclusive=True)])
    out["exclusive candidate is refused the occupied night"] = slot_of(a, "excl") != TUE
    out["exclusive candidate takes the next EMPTY night"] = slot_of(a, "excl") == WED

    # direction 2: the OCCUPANT is exclusive, the candidate is plain
    a, s = run([plan("occupant-excl", status="scheduled", window=TUE, exclusive=True),
                plan("plain")])
    out["plain candidate is refused a night an exclusive plan holds"] = slot_of(a, "plain") != TUE
    out["plain candidate takes the next empty night instead"] = slot_of(a, "plain") == WED

    # control: two plain plans still share (the guard is not over-broad)
    a, s = run([plan("occupant", status="scheduled", window=TUE), plan("plain")])
    out["two plain plans still share a night (guard not over-broad)"] = slot_of(a, "plain") == TUE

    # strict type: the STRING "true" is not exclusive for the scheduler
    a, s = run([plan("occupant", status="scheduled", window=TUE),
                plan("typo", exclusive="true")])
    out["exclusive: 'true' (a string) does not reserve the slot"] = slot_of(a, "typo") == TUE

    # two exclusive candidates never land together
    a, s = run([plan("x1", exclusive=True), plan("x2", exclusive=True)])
    out["two exclusive candidates land on different nights"] = (
        slot_of(a, "x1") and slot_of(a, "x2") and slot_of(a, "x1") != slot_of(a, "x2"))

    # reason: with a 1-day horizon only TUE exists, so the exclusive plan is
    # skipped, and the reason must say why
    a, s = run([plan("occupant", status="scheduled", window=TUE), plan("excl", exclusive=True)],
               horizon_days=1)
    out["skip reason names exclusivity when it blocked every slot"] = (
        slot_of(a, "excl") is None and "exclusiv" in reason_for(s, "excl").lower())

    # the helper is symmetric on its own
    out["helper: exclusive candidate vs any occupant -> reason"] = bool(
        ws.slot_exclusivity_blocks(plan("c", exclusive=True), [plan("o")]))
    out["helper: plain candidate vs exclusive occupant -> reason"] = bool(
        ws.slot_exclusivity_blocks(plan("c"), [plan("o", exclusive=True)]))
    out["helper: plain vs plain -> None"] = ws.slot_exclusivity_blocks(plan("c"), [plan("o")]) is None
    out["helper: empty slot -> None even for an exclusive candidate"] = (
        ws.slot_exclusivity_blocks(plan("c", exclusive=True), []) is None)
    return out


VCFG = {"windows": [{"id": "nightly", "day": "daily", "duration_min": 90,
                     "capacity_risk": 6, "allow_reboot": False, "mode": "unattended"}]}


def vplan(pid, **kw):
    base = {"plan_id": pid, "status": "scheduled", "window": TUE, "est_duration_min": 10}
    base.update(kw)
    return base


def measured(fn) -> bool:
    """A check whose counting helper ABORTS (empty population) is a FAILED
    check, not a crashed suite — under the straw the error list is legitimately
    empty, and that emptiness is exactly the failure being demonstrated."""
    try:
        return bool(fn())
    except AssertionError:
        return False


def validate_scenarios() -> dict:
    out = {}
    errs = mp.validate_plans(VCFG, [vplan("a", exclusive=True), vplan("b")])
    out["--validate: exclusive plan sharing a hand-written window is an ERROR"] = measured(
        lambda: count(errs, lambda e: "exclusive: true but shares window" in e and e.startswith("a:")) == 1)
    errs = mp.validate_plans(VCFG, [vplan("a", exclusive=True), vplan("b", status="executed")])
    out["--validate: a TERMINAL plan still carrying the window does not count as sharing"] = (
        not any("shares window" in e for e in errs))
    errs = mp.validate_plans(VCFG, [vplan("a", exclusive=True)])
    out["--validate: an exclusive plan alone in its window is clean"] = (
        not any("exclusive" in e for e in errs))
    errs = mp.validate_plans(VCFG, [vplan("a", exclusive="yes")])
    out["--validate: a non-boolean exclusive is a type ERROR"] = (
        count(errs, lambda e: "exclusive must be a bare boolean" in e) == 1)
    errs = mp.validate_plans(VCFG, [vplan("a", exclusive=False), vplan("b")])
    out["--validate: exclusive: false shares freely"] = not any("exclusive" in e for e in errs)
    out["helper: exclusive_slot_violations names the other occupant"] = (
        "with b" in " ".join(mp.exclusive_slot_violations([vplan("a", exclusive=True), vplan("b")])))
    return out


# ---------------------------------------------------------------------------
# commissioning straws
# ---------------------------------------------------------------------------
MUST_FAIL_SCHED = [
    "exclusive candidate is refused the occupied night",
    "exclusive candidate takes the next EMPTY night",
    "plain candidate is refused a night an exclusive plan holds",
    "plain candidate takes the next empty night instead",
    "skip reason names exclusivity when it blocked every slot",
]
MUST_FAIL_VALIDATE = [
    "--validate: exclusive plan sharing a hand-written window is an ERROR",
]


def main() -> int:
    print("test-scheduler-slot-exclusivity")
    for name, ok in scheduler_scenarios().items():
        check(name, ok)
    for name, ok in validate_scenarios().items():
        check(name, ok)

    print("  -- commissioning straw: no exclusivity guard (pre-fix scheduler)")
    saved = ws.slot_exclusivity_blocks
    ws.slot_exclusivity_blocks = lambda plan, here: None
    try:
        under = scheduler_scenarios()
    finally:
        ws.slot_exclusivity_blocks = saved
    failed = [n for n in MUST_FAIL_SCHED if under.get(n) is False]
    check("straw: every both-direction check FAILS with the guard reverted",
          len(failed) == len(MUST_FAIL_SCHED),
          f"still passing: {sorted(set(MUST_FAIL_SCHED) - set(failed))}")
    check("straw: the not-over-broad control still passes under the straw",
          under.get("two plain plans still share a night (guard not over-broad)") is True)

    print("  -- commissioning straw: no cross-plan validation (pre-fix validate_plans)")
    saved_v = mp.exclusive_slot_violations
    mp.exclusive_slot_violations = lambda plans: []
    try:
        under_v = validate_scenarios()
    finally:
        mp.exclusive_slot_violations = saved_v
    check("straw: the shared-window validation check FAILS with the validator reverted",
          all(under_v.get(n) is False for n in MUST_FAIL_VALIDATE))

    print()
    if FAILURES:
        print(f"FAILED ({len(FAILURES)}): {', '.join(FAILURES)}")
        return 1
    print("all scheduler-slot-exclusivity tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
