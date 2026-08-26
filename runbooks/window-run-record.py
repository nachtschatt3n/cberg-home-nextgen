#!/usr/bin/env python3
"""Record one maintenance-window run in sweep_history.window_runs.

Called by the maintenance-window-agent at close-out — for EVERY run, including
idle ones ("checked, nothing to do") and ad-hoc operator-triggered ones. The
row is the liveness substrate: `maintenance-plan.py` asserts that every dated
slot declared in maintenance-windows.yaml has a run row, which is how a window
whose cron silently disappeared becomes a finding instead of a quiet absence
(four of seven declared windows had no driving cron for weeks; the only
artifact of a window was its commits, so an idle-and-ran window and a
never-ran window were indistinguishable).

Usage:
  SWEEP_PG_DSN=... window-run-record.py --slot sat-attended --outcome green \
      --trigger cron --plans-executed 1 --safe-updates 7 [--notes "..."]
  (--run-date defaults to today; --started defaults to now)

Exit codes: 0 recorded; 2 no DSN (prints the exact row it WOULD have written,
so a degraded environment is loud, never silent).
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", required=True)
    ap.add_argument("--outcome", required=True,
                    choices=["green", "revert", "partial", "idle", "aborted"])
    ap.add_argument("--trigger", required=True, choices=["cron", "ad-hoc"])
    ap.add_argument("--plans-executed", type=int, default=0)
    ap.add_argument("--safe-updates", type=int, default=0)
    ap.add_argument("--run-date", default=None, help="YYYY-MM-DD, default today")
    ap.add_argument("--started", default=None, help="ISO ts, default now")
    ap.add_argument("--notes", default=None)
    a = ap.parse_args()

    now = datetime.now(timezone.utc)
    run_date = a.run_date or now.date().isoformat()
    started = a.started or now.isoformat()
    row = (a.slot, run_date, started, now.isoformat(), a.trigger,
           a.outcome, a.plans_executed, a.safe_updates, a.notes)

    dsn = os.environ.get("SWEEP_PG_DSN")
    if not dsn:
        print("window-run-record: NO SWEEP_PG_DSN — run NOT recorded. "
              f"Would have written: slot={a.slot} date={run_date} "
              f"outcome={a.outcome} trigger={a.trigger}", file=sys.stderr)
        return 2

    import psycopg
    with psycopg.connect(dsn, connect_timeout=10) as c, c.cursor() as cur:
        cur.execute(
            "INSERT INTO window_runs (slot, run_date, started_at, finished_at,"
            " trigger, outcome, plans_executed, safe_updates, notes)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)"
            " ON CONFLICT (slot, run_date, started_at) DO UPDATE SET"
            " finished_at=EXCLUDED.finished_at, outcome=EXCLUDED.outcome,"
            " plans_executed=EXCLUDED.plans_executed,"
            " safe_updates=EXCLUDED.safe_updates, notes=EXCLUDED.notes",
            row)
    print(f"recorded: {a.slot} {run_date} {a.outcome} "
          f"(plans={a.plans_executed}, safe={a.safe_updates}, {a.trigger})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
