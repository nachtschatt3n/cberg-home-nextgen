"""Regression tests for validate_plans() in maintenance-plan.py.

Every fixture reproduces a contradiction that was LIVE in the repo on
2026-08-26 and had been filed without anything noticing:

  * five plans carried `status: scheduled` with `window: null` — a plan that
    believes it is scheduled but names no slot silently never runs;
  * media-naming-p3's depends_on named a plan file that never existed, so the
    dependency guard enforced nothing (every sweep warned; nothing failed);
  * nothing checked that a plan's window id names a window that exists, or
    that the date falls on that window's weekday, or that the plan can
    physically fit the slot.

The validator is commissioned the same way it was proven live: it must FAIL
on these shapes. A validator that only passes is indistinguishable from no
validator.

Run:  python3 runbooks/tests/test-plan-frontmatter-invariants.py
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("mp", REPO / "runbooks/maintenance-plan.py")
mp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mp)

CFG = {"windows": [
    {"id": "sat-early", "day": "saturday", "start": "09:00", "duration_min": 90},
    {"id": "sun-window", "day": "sunday", "start": "09:00", "duration_min": 90},
]}

GOOD = {"plan_id": "good", "status": "scheduled", "window": "sat-early:2026-08-29",
        "est_duration_min": 45, "depends_on": [], "conflicts_with": []}

FAILURES: list[str] = []


def check(name, errs, want_substr):
    """want_substr None => expect NO errors; else expect one containing it."""
    if want_substr is None:
        ok = not errs
        detail = "; ".join(errs)
    else:
        ok = any(want_substr in e for e in errs)
        detail = f"wanted {want_substr!r} in {errs}"
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


def v(*plans):
    return mp.validate_plans(CFG, list(plans))


def main() -> int:
    print("test-plan-frontmatter-invariants")

    # control: a correct plan produces zero errors, or every case below is noise
    check("control: valid plan is clean", v(GOOD), None)

    # the live envoy/multus shape
    check("scheduled + window:null -> error",
          v(dict(GOOD, window=None)), "window is null")

    # the live media-naming-p3 shape
    check("dead depends_on ref -> error",
          v(dict(GOOD, depends_on=["never-existed"])), "names no existing plan")

    # window id that no window declares (the sat-early class, one level down)
    check("unknown window id -> error",
          v(dict(GOOD, window="wed-early:2026-08-27")), "not declared")

    # date on the wrong weekday (2026-08-29 IS a Saturday; the 30th is Sunday)
    check("weekday mismatch -> error",
          v(dict(GOOD, window="sat-early:2026-08-30")), "runs on")

    # plan physically cannot fit its slot
    check("duration exceeds window -> error",
          v(dict(GOOD, est_duration_min=240)), "can never fit")

    # reference plans must not carry a window (the other half of the contract)
    check("reference + window -> error",
          v(dict(GOOD, status="reference")), "must not carry a window")
    check("reference without window is clean",
          v({"plan_id": "r", "status": "reference", "window": None}), None)

    # unknown status strings don't pass silently
    check("unknown status -> error",
          v(dict(GOOD, status="scheduled ")), None)  # trailing space is stripped
    check("truly unknown status -> error",
          v(dict(GOOD, status="pending")), "unknown status")

    # malformed window ref
    check("malformed window ref -> error",
          v(dict(GOOD, window="saturday morning")), "not <window-id>")

    # `approved` was dropped in P4.0.4 — a status no loader reads must not
    # silently return
    check("retired 'approved' status -> error",
          v(dict(GOOD, status="approved")), "unknown status")

    # status-vocabulary parity (P4.0.4): the plans README must document exactly
    # VALID_STATUSES, and the window agent's Step 1 load-set must be a subset.
    # Same needle contract as controls.yaml: prose that drifts silently
    # documents a different system.
    readme = (REPO / "runbooks/maintenance/plans/README.md").read_text()
    missing = [st for st in sorted(mp.VALID_STATUSES) if st not in readme]
    check("README documents every VALID_STATUSES value",
          [f"missing from README: {missing}"] if missing else [], None)
    check("README does not document retired 'approved'",
          ["README still documents 'approved'"]
          if "| approved" in readme or "approved |" in readme else [], None)
    agent = (REPO / ".claude/agents/maintenance-window-agent.md").read_text()
    import re as _re
    m2 = _re.search(r"status: ([a-z|-]+)", agent)
    loadset = set((m2.group(1) if m2 else "").split("|")) - {""}
    bad = sorted(loadset - mp.VALID_STATUSES) if loadset else ["<no load-set found>"]
    check("window-agent Step 1 load-set is a VALID_STATUSES subset",
          [f"outside VALID_STATUSES: {bad}"] if (not loadset or loadset - mp.VALID_STATUSES) else [], None)

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} -> {', '.join(FAILURES)}")
        return 1
    print("all tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
