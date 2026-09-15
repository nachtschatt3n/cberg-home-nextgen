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

    # ---- on-demand NOW slot (2026-09-15) ---------------------------------
    od = {"id": "now", "duration_min": 480, "allow_reboot": False}
    od_cfg = dict(CFG, on_demand=od)
    exp_od = mp.expected_slots(od_cfg, today, lookback_days=14)
    check("on-demand slot is NEVER an expected occurrence",
          all(s != "now" for s, _ in exp_od) and exp_od == mp.expected_slots(CFG, today, 14),
          str(exp_od))
    real_exp = mp.expected_slots(mp.load_windows(), today, lookback_days=14)
    check("real YAML: no 'now' occurrence is ever expected",
          real_exp and all(s != "now" for s, _ in real_exp), str(real_exp[:3]))
    # a completed now row is an extra row — it satisfies nothing and breaks nothing
    missing = mp.missing_window_runs(exp, [("tue-early", "2026-09-08"),
                                           ("sat-early", "2026-09-05"),
                                           ("now", "2026-09-07")])
    check("a completed 'now' row neither satisfies nor adds a missing slot",
          missing == [], str(missing))

    from datetime import datetime, timedelta, timezone
    t_now = datetime(2026, 9, 9, 18, 0, tzinfo=timezone.utc)

    def open_row(slot, hours_ago):
        return (slot, "2026-09-09", t_now - timedelta(hours=hours_ago), None, "running")

    rows3 = [open_row("now", 3)]
    check("stuck: a 3h-old open 'now' row is NOT stuck under the 480m ceiling",
          mp.stuck_window_runs(CFG["windows"], rows3, t_now, on_demand=od) == [])
    # the control that shows the ceiling is load-bearing: without it grace
    # alone (60m) would already call an attended multi-plan run dead
    check("stuck: ...but WITHOUT the on_demand block it would read as stuck (why it is wired)",
          mp.stuck_window_runs(CFG["windows"], rows3, t_now) == ["now:2026-09-09"])
    check("stuck: a 9.5h-old open 'now' row IS stuck (480 + 60 grace = 9h)",
          mp.stuck_window_runs(CFG["windows"], [open_row("now", 9.5)], t_now,
                               on_demand=od) == ["now:2026-09-09"])
    check("stuck: on_demand does not change a scheduled window's threshold",
          mp.stuck_window_runs([{"id": "nightly", "duration_min": 90}],
                               [open_row("nightly", 3)], t_now,
                               on_demand=od) == ["nightly:2026-09-09"])

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
