"""Regression test: an on-demand run covers an ATTENDED slot only when its notes
EXPLICITLY declare `absorbs <slot>:<date>`.

Operator decision 2026-09-28. The 09-26 NOW run (window_runs 48, outcome
partial, notes "... absorbs sat-attended:2026-09-26 ...") ran Saturday's
attended batch, yet liveness paged sat-attended:2026-09-26 as missed. The
nightly rule (0dcd7654) covers only `nightly`, implicitly; attended slots get
NO implicit coverage — only the explicit token.

Pins:
  * the real row-48 shape (partial, `now`, ad-hoc, token in notes) covers
    sat-attended:2026-09-26 -> only nightly:2026-09-22-style gaps remain
  * NEGATIVE CONTROL: the same row WITHOUT the token does NOT cover the slot
  * NEGATIVE: token for another date (not the row's Berlin day) is ignored
  * NEGATIVE: open (running) and aborted rows with the token do not cover
  * NEGATIVE: a `cron` row in a non-`now` slot with the token does not cover
  * NEGATIVE: "absorbs" inside a longer word / "does not absorb" does not match
  * multiple tokens in one note are all honoured
  * a row without a notes column absorbs nothing (6-tuple callers unaffected)
  * window_liveness_report (behind --liveness-metrics / the Pushgateway push)
    selects notes and applies the coverage end-to-end
  * ops-retro window_metrics (notes at column 7) applies it too

Run:  python3 runbooks/tests/test-window-liveness-now-absorbs-attended.py
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
TOKEN = "on-demand batch; absorbs sat-attended:2026-09-26; consent: operator"


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + ("" if cond else f"  {detail}"))
    if not cond:
        FAILURES.append(name)


def ts(s):
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def row(slot, run_date, started, outcome, trigger, notes=None, finished=True):
    st = ts(started)
    return (slot, run_date, st, st if finished else None, outcome, trigger, notes)


def main() -> int:
    print("test-window-liveness-now-absorbs-attended")
    today = date(2026, 9, 28)
    exp = mp.expected_slots(CFG, today, lookback_days=3)
    # nightlies 25/26/27 present, sun present, sat has NO row of its own
    base = [row("nightly", "2026-09-25", "2026-09-25 01:30:00", "green", "cron"),
            row("nightly", "2026-09-26", "2026-09-26 01:30:00", "green", "cron"),
            row("nightly", "2026-09-27", "2026-09-27 01:30:00", "green", "cron"),
            row("sun-attended", "2026-09-27", "2026-09-27 07:00:00", "green", "cron")]

    def missing(rows):
        cov = mp.nightly_covered_by_on_demand(rows) + mp.attended_absorbed_by_on_demand(rows)
        return mp.missing_window_runs(exp, mp.completed_run_rows(rows), cov)

    check("baseline: sat-attended:2026-09-26 missing",
          missing(base) == ["sat-attended:2026-09-26"], str(missing(base)))

    row48 = row("now", "2026-09-26", "2026-09-26 05:11:00", "partial", "ad-hoc", TOKEN)
    check("row-48 shape (partial now/ad-hoc + token) covers sat-attended:2026-09-26",
          missing(base + [row48]) == [], str(missing(base + [row48])))

    # NEGATIVE CONTROL: identical row, no token
    r = base + [row("now", "2026-09-26", "2026-09-26 05:11:00", "partial", "ad-hoc",
                    "on-demand batch; consent: operator")]
    check("NEGATIVE CONTROL: same row without the token does NOT cover",
          missing(r) == ["sat-attended:2026-09-26"], str(missing(r)))
    r = base + [row("now", "2026-09-26", "2026-09-26 05:11:00", "partial", "ad-hoc", None)]
    check("NEGATIVE: notes NULL does not cover", missing(r) == ["sat-attended:2026-09-26"],
          str(missing(r)))

    r = base + [row("now", "2026-09-25", "2026-09-25 10:00:00", "green", "ad-hoc", TOKEN)]
    check("NEGATIVE: token dated another day than the row's Berlin date is ignored",
          missing(r) == ["sat-attended:2026-09-26"], str(missing(r)))

    r = base + [row("now", "2026-09-26", "2026-09-26 05:11:00", "running", "ad-hoc", TOKEN,
                    finished=False)]
    check("NEGATIVE: an OPEN (running) row with the token does not cover",
          missing(r) == ["sat-attended:2026-09-26"], str(missing(r)))
    r = base + [row("now", "2026-09-26", "2026-09-26 05:11:00", "aborted", "ad-hoc", TOKEN)]
    check("NEGATIVE: an ABORTED row with the token does not cover",
          missing(r) == ["sat-attended:2026-09-26"], str(missing(r)))

    r = base + [row("sun-attended", "2026-09-26", "2026-09-26 05:11:00", "green", "cron", TOKEN)]
    check("NEGATIVE: a cron row in a non-`now` slot does not cover via the token",
          missing(r) == ["sat-attended:2026-09-26"], str(missing(r)))

    for bad in ("reabsorbs sat-attended:2026-09-26", "does not absorb sat-attended:2026-09-26",
                "pre-absorbs sat-attended:2026-09-26", "absorbs sat-attended 2026-09-26"):
        r = base + [row("now", "2026-09-26", "2026-09-26 05:11:00", "green", "ad-hoc", bad)]
        check(f"NEGATIVE: non-token text {bad!r} does not match",
              missing(r) == ["sat-attended:2026-09-26"], str(missing(r)))

    # multiple tokens (Sunday row missing too)
    base2 = base[:3]
    r = base2 + [row("now", "2026-09-27", "2026-09-27 08:00:00", "green", "ad-hoc",
                     "absorbs sun-attended:2026-09-27; absorbs sat-attended:2026-09-27")]
    check("token for the row's own day covers; sat token on a sunday date is harmless",
          missing(r) == ["sat-attended:2026-09-26"], str(missing(r)))
    r = base2 + [row48, row("now", "2026-09-27", "2026-09-27 08:00:00", "green", "ad-hoc",
                            "absorbs sun-attended:2026-09-27")]
    check("two rows each absorbing their day clear both attended slots",
          missing(r) == [], str(missing(r)))

    # Berlin date wins: opened 22:30Z on 09-25 = 00:30 Berlin 09-26
    r = base + [row("now", "2026-09-25", "2026-09-25 22:30:00", "green", "ad-hoc", TOKEN)]
    check("Berlin date of started_at (not UTC run_date) is the row's day",
          missing(r) == [], str(missing(r)))

    six = [r_[:6] for r_ in base + [row48]]
    check("6-column rows (no notes) absorb nothing",
          mp.attended_absorbed_by_on_demand(six) == [], "")

    # end-to-end: window_liveness_report selects notes and applies it
    seen = {}
    rows = base + [row48]

    class Cur:
        def execute(self, sql, params=None):
            seen["sql"] = sql

        def fetchall(self):
            return rows

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class Conn:
        def cursor(self):
            return Cur()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    fake = types.SimpleNamespace(connect=lambda *a, **k: Conn())
    saved_mod, saved_dsn = sys.modules.get("psycopg"), os.environ.get("SWEEP_PG_DSN")
    sys.modules["psycopg"] = fake
    os.environ["SWEEP_PG_DSN"] = "postgresql://fake"
    try:
        rep = mp.window_liveness_report(CFG, today, now=ts("2026-09-28 08:00:00"))
    finally:
        if saved_mod is None:
            sys.modules.pop("psycopg", None)
        else:
            sys.modules["psycopg"] = saved_mod
        if saved_dsn is None:
            os.environ.pop("SWEEP_PG_DSN", None)
        else:
            os.environ["SWEEP_PG_DSN"] = saved_dsn
    check("window_liveness_report SELECTs notes", "notes" in seen.get("sql", ""), seen.get("sql"))
    got = [m for m in rep["missing"] if m.startswith("sat-attended")]
    check("window_liveness_report: sat-attended:2026-09-26 not missing", got == [],
          str(rep["missing"]))

    # ops-retro: notes at column 7 (after safe_updates)
    rspec = importlib.util.spec_from_file_location("retro", REPO / "runbooks/ops-retro.py")
    retro = importlib.util.module_from_spec(rspec)
    rspec.loader.exec_module(retro)
    wide = [r_[:6] + (0, r_[6]) for r_ in rows]
    span = (ts("2026-09-21 22:00:00"), ts("2026-09-28 22:00:00"))
    m = retro.window_metrics(mp, CFG, wide, date(2026, 9, 29), span)
    txt = repr(m.get("missed_slots"))
    check("ops-retro window_metrics honours the token (notes at column 7)",
          "sat-attended:2026-09-26" not in txt, txt)
    wide_nt = [r_[:6] + (0, None) for r_ in rows]
    m = retro.window_metrics(mp, CFG, wide_nt, date(2026, 9, 29), span)
    txt = repr(m.get("missed_slots"))
    check("ops-retro NEGATIVE CONTROL: without notes the slot is missed",
          "sat-attended:2026-09-26" in txt, txt)

    print(f"{'FAIL' if FAILURES else 'OK'}: {len(FAILURES)} failure(s)")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
