"""Regression tests for the RETRY cron half of window-crons.py.

Pins the 2026-09-14 finding from the other side: the OpenClaw cron that
drives the nightly window reports `ok` on DELIVERY of the prompt to the
console, not on completion, so five nightly dates had no window_runs row
and nothing noticed. The fix is a second cron at start+retry_after_min whose
payload (`maintenance-window retry`) no-ops when any row exists for
(slot, today). These fixtures pin the derived expression, the parity rules
--check applies to that cron, and — load-bearing — that a retry cron is
NEVER mistaken for a driver.

Run:  python3 runbooks/tests/test-window-crons-retry.py
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
NIGHTLY = {"id": "nightly", "day": "daily", "start": "03:30", "retry_after_min": 135}
SAT = {"id": "sat-attended", "day": "saturday", "start": "09:00"}
WINDOWS = [NIGHTLY, SAT]


def cron(window_id, expr, verb="run", enabled=True, tz=TZ):
    return {"name": f"win {window_id} {verb}", "enabled": enabled,
            "schedule": {"kind": "cron", "expr": expr, "tz": tz},
            "payload": {"argv": ["sh", "-lc",
                                 f"/home/node/.openclaw/bin/maintenance-window {verb} --window {window_id}"]}}


DRIVERS = [cron("nightly", "30 3 * * *"), cron("sat-attended", "0 9 * * 6")]
RETRY = cron("nightly", "45 5 * * *", verb="retry")
GOOD = DRIVERS + [RETRY]
FAILURES: list[str] = []


def check(name, errs, want):
    """want=None: expect clean. want=str: expect some error containing it.
    want=(str, n): expect exactly n errors, one containing str."""
    if want is None:
        ok = not errs
    elif isinstance(want, tuple):
        ok = len(errs) == want[1] and any(want[0] in e for e in errs)
    else:
        ok = any(want in e for e in errs)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {errs}"))
    if not ok:
        FAILURES.append(name)


def main() -> int:
    print("test-window-crons-retry")

    # --- expression derivation -------------------------------------------
    cases = {
        "03:30 + 135 daily -> 05:45": (NIGHTLY, "45 5 * * *"),
        "no retry_after_min -> None": (SAT, None),
        "retry_after_min: 0 -> None": ({"day": "daily", "start": "03:30", "retry_after_min": 0}, None),
        "weekday, same day": ({"day": "sunday", "start": "09:00", "retry_after_min": 200}, "20 12 * * 0"),
        "weekday crossing midnight shifts dow": ({"day": "saturday", "start": "23:00", "retry_after_min": 120}, "0 1 * * 0"),
        "sunday crossing midnight wraps to monday": ({"day": "sunday", "start": "23:30", "retry_after_min": 60}, "30 0 * * 1"),
        "daily crossing midnight stays daily": ({"day": "daily", "start": "23:30", "retry_after_min": 60}, "30 0 * * *"),
    }
    for name, (win, want) in cases.items():
        got = wc.expected_retry_cron_expr(win)
        check(f"expr: {name}", [] if got == want else [f"got {got!r} want {want!r}"], None)

    # --- payload recognition ---------------------------------------------
    check("retry payload is recognised as a retry",
          [] if wc.retry_window_of_cron(RETRY) == "nightly" else ["not recognised"], None)
    # load-bearing: `maintenance-window retry` must not read as a driver, or a
    # window with only a retry cron would pass as driven (and the driver
    # check would flag the pair as double-firing)
    check("retry payload is NOT a driver",
          [] if wc.window_of_cron(RETRY) is None else ["retry counted as driver"], None)
    check("driver payload is NOT a retry",
          [] if wc.retry_window_of_cron(DRIVERS[0]) is None else ["driver counted as retry"], None)

    # --- parity ----------------------------------------------------------
    check("control: drivers + retry is clean", wc.check(WINDOWS, TZ, GOOD), None)

    # the pre-fix shape (live 2026-09-14 before the cron was added)
    check("declared retry with no retry cron",
          wc.check(WINDOWS, TZ, DRIVERS), ("NO retry cron", 1))

    # a window with ONLY a retry cron is still undriven
    check("retry cron alone does not drive the window",
          wc.check(WINDOWS, TZ, [DRIVERS[1], RETRY]), "NO cron drives it")
    check("... and does not double-fire it",
          [e for e in wc.check(WINDOWS, TZ, GOOD) if "crons" in e and "driven" in e], None)

    check("disabled retry cron",
          wc.check(WINDOWS, TZ, DRIVERS + [cron("nightly", "45 5 * * *", "retry", enabled=False)]),
          "retry cron exists but is DISABLED")
    check("retry expr drift",
          wc.check(WINDOWS, TZ, DRIVERS + [cron("nightly", "45 6 * * *", "retry")]),
          "start + retry_after_min")
    check("retry tz drift",
          wc.check(WINDOWS, TZ, DRIVERS + [cron("nightly", "45 5 * * *", "retry", tz="UTC")]),
          "retry cron tz")
    check("duplicate retry crons",
          wc.check(WINDOWS, TZ, GOOD + [RETRY]), "2 retry crons")

    # orphans: a retry for a window that declares none, and for a deleted window
    check("orphan retry: window declares no retry_after_min",
          wc.check(WINDOWS, TZ, GOOD + [cron("sat-attended", "15 11 * * 6", "retry")]),
          ("declares no retry_after_min", 1))
    check("orphan retry: window no longer declared",
          wc.check(WINDOWS, TZ, GOOD + [cron("tue-early", "0 7 * * 2", "retry")]),
          ("ORPHAN retry cron for window 'tue-early'", 1))

    # a YAML without any retry_after_min is exactly the old contract
    check("no retry declared anywhere: old contract holds",
          wc.check([{**NIGHTLY, "retry_after_min": None}, SAT], TZ, DRIVERS), None)

    # --- render ----------------------------------------------------------
    out = wc.render(WINDOWS, TZ)
    want = [
        'maintenance-window retry --window nightly',
        '--name "Maintenance Window — nightly retry"',
        '--cron "45 5 * * *" --tz Europe/Berlin',
        'MAINTENANCE_WINDOW_TRIGGER=cron',
    ]
    check("render prints the retry cron add",
          [f"missing {w!r}" for w in want if w not in out], None)
    check("render prints no retry for a window without retry_after_min",
          ["sat-attended retry rendered"] if "retry --window sat-attended" in out else [], None)
    check("render still prints the driver before the retry",
          [] if out.index("run --window nightly") < out.index("retry --window nightly") else ["order"], None)

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} -> {', '.join(FAILURES)}")
        return 1
    print("all tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
