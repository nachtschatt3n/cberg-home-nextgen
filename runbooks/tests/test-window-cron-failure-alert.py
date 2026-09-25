"""Regression tests for the failureAlert half of window-crons.py --check.

Pins F-e6dda67f (2026-09-25): the nightly window cron had failureAlert
cooldownMs = 86,400,000 (exactly 24h) on a 24h schedule, so the 09-24 failure
landed 0.3s inside the previous alert's cooldown and paged nobody; the retry
cron had no failureAlert at all. Rule: every driver/retry cron carries a
failureAlert with cooldown STRICTLY below its period.

Run:  python3 runbooks/tests/test-window-cron-failure-alert.py
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("wc", REPO / "runbooks/window-crons.py")
wc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wc)

H = 3600 * 1000
NIGHTLY = {"id": "nightly", "day": "daily", "start": "03:30", "retry_after_min": 135}
SAT = {"id": "sat-attended", "day": "saturday", "start": "09:00"}
WINDOWS = [NIGHTLY, SAT]
FAILURES: list[str] = []


def fa(cooldown_h, to="<chat>", after=1):
    return {"after": after, "channel": "telegram", "to": to,
            "cooldownMs": int(cooldown_h * H), "mode": "announce"}


def cron(wid, verb="run", alert=None):
    c = {"enabled": True, "payload": {"argv": ["sh", "-lc",
         f"/home/node/.openclaw/bin/maintenance-window {verb} --window {wid}"]}}
    if alert is not None:
        c["failureAlert"] = alert
    return c


def check(name, errs, want):
    ok = (not errs) if want is None else (len(errs) == want[1] and any(want[0] in e for e in errs))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {errs}"))
    if not ok:
        FAILURES.append(name)


def main() -> int:
    print("test-window-cron-failure-alert")
    good = [cron("nightly", alert=fa(20)), cron("nightly", "retry", fa(20)),
            cron("sat-attended", alert=fa(24))]
    check("control: post-fix live shape is clean", wc.check_failure_alerts(WINDOWS, good), None)

    # the exact pre-fix live shape (2026-09-24)
    pre = [cron("nightly", alert=fa(24)), cron("nightly", "retry"),
           cron("sat-attended", alert=fa(24))]
    errs = wc.check_failure_alerts(WINDOWS, pre)
    check("pre-fix: cooldown == period flagged", errs, (">= period", 2))
    check("pre-fix: retry without failureAlert flagged", errs, ("retry cron has NO failureAlert", 2))

    check("cooldown one ms under period passes",
          wc.check_failure_alerts(WINDOWS, [cron("nightly", alert={**fa(0), "cooldownMs": 24 * H - 1})]), None)
    check("weekly: 7d cooldown flagged",
          wc.check_failure_alerts(WINDOWS, [cron("sat-attended", alert=fa(168))]), (">= period", 1))
    check("weekly: 24h cooldown passes",
          wc.check_failure_alerts(WINDOWS, [cron("sat-attended", alert=fa(24))]), None)
    check("missing cooldownMs flagged",
          wc.check_failure_alerts(WINDOWS, [cron("nightly", alert={"after": 1, "to": "x"})]), (">= period", 1))
    check("no destination flagged",
          wc.check_failure_alerts(WINDOWS, [cron("nightly", alert=fa(20, to=""))]), ("no destination", 1))
    check("after=0 flagged",
          wc.check_failure_alerts(WINDOWS, [cron("nightly", alert=fa(20, after=0))]), ("after=0", 1))
    check("unrelated cron ignored",
          wc.check_failure_alerts(WINDOWS, [{"payload": {"argv": ["sh", "-lc", "echo hi"]}}]), None)

    out = wc.render(WINDOWS, "Europe/Berlin")
    check("render: every cron add carries --failure-alert",
          [] if out.count("cron add") == out.count("--failure-alert ") == 3 else [out], None)
    check("render: daily 20h, weekly 24h",
          [] if out.count("--failure-alert-cooldown 20h") == 2 and out.count("--failure-alert-cooldown 24h") == 1 else ["cooldowns"], None)
    for w in WINDOWS:
        ms = int(wc.expected_alert_cooldown(w)[:-1]) * H
        check(f"render cooldown < period for {w['id']}",
              [] if ms < wc.window_period_ms(w) else ["cooldown >= period"], None)
    check("render: no chat id committed",
          [] if "FAILURE_ALERT_TO" in out and not any(ch.isdigit() and len(ch) > 6 for ch in out.split()) else ["literal id?"], None)

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} -> {', '.join(FAILURES)}")
        return 1
    print("all tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
