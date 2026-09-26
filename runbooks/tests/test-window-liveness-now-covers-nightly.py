"""Regression test: a same-day on-demand run covers that day's NIGHTLY.

Operator decision 2026-09-26. The nightly window's job is Step 0 (safe updates
land every night); a `now` / ad-hoc run runs Step 0 first by contract, so a day
the console spent in an attended NOW run must not page as a missed nightly.

Pins:
  * completed, non-aborted `now` row on the same Europe/Berlin date -> covered
  * trigger `ad-hoc` in a non-nightly slot also covers (the "ad-hoc row" arm)
  * NEGATIVE: an OPEN (`running`, no finished_at) `now` row does NOT cover
  * NEGATIVE: an `aborted` `now` row does NOT cover
  * NEGATIVE: a `now` row on a DIFFERENT Berlin date does not cover
  * the Berlin date wins over run_date (UTC): a NOW run opened 00:30 Berlin
    (22:30 UTC, run_date = previous day) covers TODAY's nightly, and one opened
    23:30 UTC the evening before covers the next Berlin day, not its run_date
  * sat-attended / sun-attended are NOT covered (nightly only)
  * a cron row in sat-attended does not cover the Saturday nightly
  * window_liveness_report (the path behind --liveness-metrics, which
    sweep-run.py's Pushgateway push runs) applies the coverage end-to-end

Run:  python3 runbooks/tests/test-window-liveness-now-covers-nightly.py
"""

from __future__ import annotations

import importlib.util
import os
import sys
import types
from datetime import date, datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("mp", REPO / "runbooks/maintenance-plan.py")
mp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mp)

CFG = {"windows": [
    {"id": "nightly", "day": "daily", "duration_min": 90},
    {"id": "sat-attended", "day": "saturday", "duration_min": 90},
    {"id": "sun-attended", "day": "sunday", "duration_min": 200},
], "on_demand": {"id": "now", "duration_min": 480}}

FAILURES: list[str] = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + ("" if cond else f"  {detail}"))
    if not cond:
        FAILURES.append(name)


def ts(s):
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def row(slot, run_date, started, outcome, trigger, finished=True):
    st = ts(started)
    return (slot, run_date, st, st if finished else None, outcome, trigger)


def main() -> int:
    print("test-window-liveness-now-covers-nightly")
    # Monday 2026-09-28: lookback covers Sat 09-26 + Sun 09-27 and nightlies 09-21..27
    today = date(2026, 9, 28)
    exp = mp.expected_slots(CFG, today, lookback_days=3)
    check("expected: nightly x3 + sat + sun",
          exp == [("nightly", "2026-09-25"), ("nightly", "2026-09-26"), ("nightly", "2026-09-27"),
                  ("sat-attended", "2026-09-26"), ("sun-attended", "2026-09-27")], str(exp))

    base = [row("nightly", "2026-09-25", "2026-09-25 01:30:00", "green", "cron"),
            row("sat-attended", "2026-09-26", "2026-09-26 07:00:00", "idle", "cron"),
            row("sun-attended", "2026-09-27", "2026-09-27 07:00:00", "idle", "cron")]

    def missing(rows):
        cov = mp.nightly_covered_by_on_demand(rows)
        return mp.missing_window_runs(exp, mp.completed_run_rows(rows), cov)

    check("baseline: nightlies 26/27 missing",
          missing(base) == ["nightly:2026-09-26", "nightly:2026-09-27"], str(missing(base)))

    # positive: green NOW row same Berlin date covers the nightly
    r = base + [row("now", "2026-09-26", "2026-09-26 04:51:00", "green", "ad-hoc")]
    check("completed green `now` row covers that day's nightly",
          missing(r) == ["nightly:2026-09-27"], str(missing(r)))

    for outcome in ("idle", "partial", "revert"):
        r = base + [row("now", "2026-09-26", "2026-09-26 04:51:00", outcome, "ad-hoc")]
        check(f"completed `now` row outcome={outcome} covers",
              missing(r) == ["nightly:2026-09-27"], str(missing(r)))

    # NEGATIVE: still running
    r = base + [row("now", "2026-09-26", "2026-09-26 04:51:00", "running", "ad-hoc",
                    finished=False)]
    check("NEGATIVE: an OPEN (running) `now` row does NOT cover",
          missing(r) == ["nightly:2026-09-26", "nightly:2026-09-27"], str(missing(r)))

    # NEGATIVE: aborted
    r = base + [row("now", "2026-09-26", "2026-09-26 04:51:00", "aborted", "ad-hoc")]
    check("NEGATIVE: an ABORTED `now` row does NOT cover",
          missing(r) == ["nightly:2026-09-26", "nightly:2026-09-27"], str(missing(r)))

    # NEGATIVE: different date
    r = base + [row("now", "2026-09-24", "2026-09-24 10:00:00", "green", "ad-hoc")]
    check("NEGATIVE: a `now` row on another Berlin date does not cover",
          missing(r) == ["nightly:2026-09-26", "nightly:2026-09-27"], str(missing(r)))

    # Berlin date wins over UTC run_date (CEST = UTC+2)
    r = base + [row("now", "2026-09-26", "2026-09-26 22:30:00", "green", "ad-hoc")]
    check("NOW opened 00:30 Berlin (run_date = previous UTC day) covers the Berlin day",
          missing(r) == ["nightly:2026-09-26"], str(missing(r)))

    # ad-hoc arm in a non-nightly slot
    r = base + [row("sat-attended", "2026-09-27", "2026-09-27 12:00:00", "green", "ad-hoc")]
    check("an ad-hoc row in another slot covers that day's nightly",
          missing(r) == ["nightly:2026-09-26"], str(missing(r)))

    # cron row in sat-attended does NOT cover the Saturday nightly
    check("a CRON sat-attended row does not cover the Saturday nightly",
          "nightly:2026-09-26" in missing(base), str(missing(base)))

    # only nightly is covered: sat/sun stay missing without their own rows
    r = [row("nightly", "2026-09-25", "2026-09-25 01:30:00", "green", "cron"),
         row("now", "2026-09-26", "2026-09-26 08:00:00", "green", "ad-hoc"),
         row("now", "2026-09-27", "2026-09-27 08:00:00", "green", "ad-hoc")]
    check("sat-attended / sun-attended are NOT covered by a NOW run",
          missing(r) == ["sat-attended:2026-09-26", "sun-attended:2026-09-27"], str(missing(r)))

    # a row without a trigger column is judged by its slot alone
    cov = mp.nightly_covered_by_on_demand(
        [("now", "2026-09-26", ts("2026-09-26 05:00:00"), ts("2026-09-26 06:00:00"), "green")])
    check("5-column row (no trigger) still covered by slot `now`",
          cov == [("nightly", "2026-09-26")], str(cov))

    # end-to-end through window_liveness_report (behind --liveness-metrics)
    rows = base + [row("now", "2026-09-26", "2026-09-26 04:51:00", "green", "ad-hoc"),
                   row("now", "2026-09-27", "2026-09-27 04:51:00", "running", "ad-hoc",
                       finished=False)]
    seen = {}

    class Cur:
        def execute(self, sql, params):
            seen["sql"], seen["params"] = sql, params

        def fetchall(self):
            return rows

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def cursor(self):
            return self

        execute, fetchall = Cur.execute, Cur.fetchall

    fake = types.SimpleNamespace(connect=lambda *a, **k: Conn())
    saved_mod, saved_dsn = sys.modules.get("psycopg"), os.environ.get("SWEEP_PG_DSN")
    sys.modules["psycopg"] = fake
    os.environ["SWEEP_PG_DSN"] = "postgres://fake"
    old = mp.WINDOW_LIVENESS_LOOKBACK_DAYS
    try:
        rep = mp.window_liveness_report(CFG, today,
                                        now=ts("2026-09-27 06:00:00"))
    finally:
        if saved_mod is None:
            sys.modules.pop("psycopg", None)
        else:
            sys.modules["psycopg"] = saved_mod
        if saved_dsn is None:
            os.environ.pop("SWEEP_PG_DSN", None)
        else:
            os.environ["SWEEP_PG_DSN"] = saved_dsn
        mp.WINDOW_LIVENESS_LOOKBACK_DAYS = old
    check("report reads the trigger column", "trigger" in seen.get("sql", ""), seen.get("sql", ""))
    m = rep["missing"]
    check("report: nightly 09-26 covered by the green NOW run",
          "nightly:2026-09-26" not in m, str(m))
    check("report: nightly 09-27 NOT covered by the still-running NOW run",
          "nightly:2026-09-27" in m, str(m))
    fig = mp.liveness_figures(rep["missing"], rep["stuck"], rep["verified"], today)
    check("metrics text carries the covered count",
          f"window_runs_missing_count{{lookback_days=\"7\"}} {len(m)}"
          in mp.liveness_metrics_text(fig), mp.liveness_metrics_text(fig))

    print(f"\n{'OK' if not FAILURES else 'FAILED'}: {len(FAILURES)} failure(s)")
    return 1 if FAILURES else 0


def test_pytest_entry() -> None:
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
