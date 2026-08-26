"""Regression tests for window-crons.py's parity logic.

Pins the D1 lesson from the other side: runbooks/maintenance-windows.yaml
declared seven windows while only three had driving OpenClaw crons, and
nothing compared the two. The live commissioning run of --check reported
exactly the three undriven windows (and, after the reshape, the two orphan
crons of deleted windows) before anything was fixed — these fixtures pin
those shapes.

Run:  python3 runbooks/tests/test-window-cron-parity.py
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("wc", REPO / "runbooks/window-crons.py")
wc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wc)

TZ = "Europe/Berlin"
WINDOWS = [
    {"id": "nightly", "day": "daily", "start": "03:30"},
    {"id": "sat-early", "day": "saturday", "start": "09:00"},
]


def cron(window_id, expr, enabled=True, tz=TZ):
    return {"name": f"win {window_id}", "enabled": enabled,
            "schedule": {"kind": "cron", "expr": expr, "tz": tz},
            "payload": {"argv": ["sh", "-lc",
                                 f"/home/node/.openclaw/bin/maintenance-window run --window {window_id}"]}}


GOOD = [cron("nightly", "30 3 * * *"), cron("sat-early", "0 9 * * 6")]
FAILURES: list[str] = []


def check(name, errs, want):
    ok = (not errs) if want is None else any(want in e for e in errs)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {errs}"))
    if not ok:
        FAILURES.append(name)


def main() -> int:
    print("test-window-cron-parity")

    check("control: full parity is clean", wc.check(WINDOWS, TZ, GOOD), None)

    # the live D1 shape: declared window, no cron
    check("undriven window detected",
          wc.check(WINDOWS, TZ, GOOD[:1]), "NO cron drives it")

    # the post-reshape shape: cron for a window the YAML deleted
    check("orphan cron detected",
          wc.check(WINDOWS, TZ, GOOD + [cron("tue-early", "0 5 * * 2")]),
          "ORPHAN cron")

    # a disabled cron is not a driving cron
    check("disabled cron detected",
          wc.check(WINDOWS, TZ, [cron("nightly", "30 3 * * *", enabled=False), GOOD[1]]),
          "DISABLED")

    # schedule drift: cron exists but fires at the wrong time
    check("wrong expr detected",
          wc.check(WINDOWS, TZ, [cron("nightly", "30 4 * * *"), GOOD[1]]),
          "!=")

    # double-driven window double-fires
    check("duplicate crons detected",
          wc.check(WINDOWS, TZ, GOOD + [cron("nightly", "30 3 * * *")]),
          "2 crons")

    # daily + weekday expr derivation
    ok = (wc.expected_cron_expr({"day": "daily", "start": "03:30"}) == "30 3 * * *"
          and wc.expected_cron_expr({"day": "sunday", "start": "09:00"}) == "0 9 * * 0")
    check("expr derivation (daily + weekday)", [] if ok else ["derivation wrong"], None)

    # unrelated crons (briefings, snapshots) are ignored entirely
    noise = {"name": "Daily Morning Briefing", "enabled": True,
             "schedule": {"expr": "45 8 * * *", "tz": TZ},
             "payload": {"argv": ["sh", "-lc", "briefing"]}}
    check("non-window crons ignored", wc.check(WINDOWS, TZ, GOOD + [noise]), None)

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} -> {', '.join(FAILURES)}")
        return 1
    print("all tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
