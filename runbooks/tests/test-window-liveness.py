"""Regression tests for the window-liveness assertion in maintenance-plan.py.

Pins the D1 lesson: four of seven declared maintenance windows had no driving
cron for weeks, and nothing could notice — a window's only artifact was its
commits, so "ran and found nothing" and "never ran" were indistinguishable.
window_runs rows (written by the window agent at close-out, idle runs
included) make them distinguishable; this asserts the assertion.

Run:  python3 runbooks/tests/test-window-liveness.py
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("mp", REPO / "runbooks/maintenance-plan.py")
mp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mp)

CFG = {"windows": [
    {"id": "tue-early", "day": "tuesday"},
    {"id": "sat-early", "day": "saturday"},
]}

FAILURES: list[str] = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + ("" if cond else f"  {detail}"))
    if not cond:
        FAILURES.append(name)


def main() -> int:
    print("test-window-liveness")
    today = date(2026, 9, 9)  # a Wednesday, well past the epoch

    exp = mp.expected_slots(CFG, today, lookback_days=7)
    check("expected slots enumerated",
          exp == [("sat-early", "2026-09-05"), ("tue-early", "2026-09-08")], str(exp))

    # the D1 shape: tue ran, sat silently did not
    missing = mp.missing_window_runs(exp, [("tue-early", "2026-09-08")])
    check("dead slot detected", missing == ["sat-early:2026-09-05"], str(missing))

    # both ran (one idle) -> clean
    missing = mp.missing_window_runs(
        exp, [("tue-early", "2026-09-08"), ("sat-early", "2026-09-05")])
    check("recorded runs (incl. idle) are clean", missing == [])

    # ad-hoc runs count: the recorder writes the same row shape
    # (trigger differs, slot+date match) — same as above by construction.

    # today's own window is never asserted (it may not have fired yet)
    exp_today = mp.expected_slots(CFG, date(2026, 9, 8), lookback_days=7)
    check("today's occurrence excluded",
          ("tue-early", "2026-09-08") not in exp_today, str(exp_today))

    # pre-epoch occurrences are not asserted (no day-one false flood)
    exp_epoch = mp.expected_slots(CFG, date(2026, 8, 28), lookback_days=7)
    check("pre-epoch history excluded",
          all(d >= "2026-08-27" for _, d in exp_epoch), str(exp_epoch))

    # no-DSN => verified=False, missing empty — degraded, never all-clear
    import os
    os.environ.pop("SWEEP_PG_DSN", None)
    missing, verified = mp.window_liveness(CFG, today)
    check("no DSN -> NOT verified (and not clean-looking)",
          verified is False and missing == [])

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} -> {', '.join(FAILURES)}")
        return 1
    print("all tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
