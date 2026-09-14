#!/usr/bin/env python3
"""Regression tests for two-phase window_runs recording (2026-09-14).

GROUND TRUTH THIS EXISTS FOR. Five nightly dates had no window_runs row at
all. The driving OpenClaw cron reports `ok` on DELIVERY of the trigger to the
Mac console session, not on completion — so a window that started and died
mid-run left exactly the same nothing as a window whose cron never fired, and
the liveness check could only say "missing" for both. The row was written
once, at close-out, by the very process that had just died.

The fix writes the row at OPEN (`--outcome running`, finished_at NULL) and
closes it at close-out (`--finalize`). Three properties must hold, and each
fails in its own direction:

  1. --finalize must update the RIGHT row — the latest still-open one — and
     never re-close a row an earlier close-out already finished (that would
     silently overwrite a real result with a later, wrong one).
  2. An open row must NOT satisfy the liveness assertion. "Started" is not
     "ran"; counting it would turn the crash-after-open into a verified run,
     the exact blind spot this is meant to close. An open row older than the
     window's duration + grace is `stuck`, reported separately.
  3. Every pre-existing caller — the window agent's close-out, the SOP
     recipes — keeps working unchanged: same flags, same outcomes, same
     one-row insert.

Run:  python3 runbooks/tests/test-window-run-running-row.py
"""

from __future__ import annotations

import importlib.util
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, REPO / "runbooks" / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rec = _load("window_run_record", "window-run-record.py")
mp = _load("maintenance_plan", "maintenance-plan.py")

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


T0 = datetime(2026, 9, 14, 1, 30, tzinfo=timezone.utc)   # 03:30 Berlin
WINDOWS = [{"id": "nightly", "day": "daily", "duration_min": 90},
           {"id": "sat-attended", "day": "saturday", "duration_min": 90},
           {"id": "sun-attended", "day": "sunday", "duration_min": 200}]


def row(rid, started, outcome, finished=None, notes=None, trigger="cron"):
    """(id, started_at, outcome, finished_at, notes, trigger) — the recorder's
    _FINALIZE_SELECT column order."""
    return (rid, started, outcome, finished, notes, trigger)


def lrow(slot, run_date, started, finished, outcome):
    """(slot, run_date, started_at, finished_at, outcome) — the liveness read."""
    return (slot, run_date, started, finished, outcome)


def parse(argv):
    return rec.build_parser().parse_args(argv)


def main() -> int:
    print("two-phase window_runs recording:")

    # ---- 1. finalize picks the right row ------------------------------------
    check("no rows -> nothing to finalize (fallback insert path)",
          rec.finalize_target([]) is None)

    check("a single open row is the target",
          rec.finalize_target([row(7, T0, "running")]) == 7)

    check("an already-finalized row is NOT re-closed by a second close-out",
          rec.finalize_target([row(7, T0, "green", finished=T0 + timedelta(hours=1))]) is None)

    # aborted-and-retried: two opens on one date, the newest one is live
    rows = [row(1, T0, "running"),
            row(2, T0 + timedelta(hours=2), "running")]
    check("latest-started open row wins over an older open row",
          rec.finalize_target(rows) == 2)
    check("order of the SELECT result does not change the answer",
          rec.finalize_target(list(reversed(rows))) == 2)

    # a terminal row with a NULL finished_at is not an open window
    check("terminal outcome with NULL finished_at is not a finalize target",
          rec.finalize_target([row(3, T0, "aborted", finished=None)]) is None)

    # the closed earlier attempt must not shadow the later open one
    rows = [row(1, T0, "aborted", finished=T0 + timedelta(minutes=5)),
            row(2, T0 + timedelta(hours=2), "running")]
    check("closed first attempt + open retry -> the retry",
          rec.finalize_target(rows) == 2)

    # ---- notes append, never replace ---------------------------------------
    check("close-out notes append to the open's notes",
          rec.append_notes("opened by cron", "3 safe updates") == "opened by cron\n3 safe updates")
    check("no close-out notes keeps the open's notes",
          rec.append_notes("opened by cron", None) == "opened by cron")
    check("no open notes -> close-out notes verbatim",
          rec.append_notes(None, "x") == "x")

    # ---- the SQL still carries what the re-implementation assumes ----------
    sql = rec._FINALIZE_SELECT
    check("finalize SELECT is scoped to (slot, run_date)",
          "slot = %s" in sql and "run_date = %s" in sql, sql)
    check("finalize SELECT returns the columns finalize_target indexes",
          sql.startswith("SELECT id, started_at, outcome, finished_at, notes, trigger"), sql)
    ins_sql, _ = rec._terminal_sql(("s", "d", "t", None, "cron", "green", 0, 0, None))
    check("plain insert still upserts on (slot, run_date, started_at)",
          "ON CONFLICT (slot, run_date, started_at)" in ins_sql, ins_sql)

    # ---- 2. liveness: open rows do not count, old open rows are stuck ------
    expected = [("nightly", "2026-09-13")]
    open_row = lrow("nightly", "2026-09-13", T0 - timedelta(days=1), None, "running")
    check("an OPEN row does not satisfy the liveness assertion",
          mp.missing_window_runs(expected, mp.completed_run_rows([open_row]))
          == ["nightly:2026-09-13"])
    done_row = lrow("nightly", "2026-09-13", T0 - timedelta(days=1),
                    T0 - timedelta(days=1, minutes=-30), "green")
    check("a finalized row satisfies it",
          mp.missing_window_runs(expected, mp.completed_run_rows([done_row])) == [])
    check("a pre-2026-09-14 terminal row (finished_at set) still counts",
          mp.completed_run_rows([lrow("nightly", "2026-09-13", T0, T0, "idle")])
          == [("nightly", "2026-09-13")])
    check("missing_window_runs itself is unchanged (2-tuples in, slot:date out)",
          mp.missing_window_runs([("a", "2026-09-01"), ("b", "2026-09-01")],
                                 [("a", "2026-09-01")]) == ["b:2026-09-01"])

    # stuck: nightly is 90 min + 60 grace = 150 min
    fresh = lrow("nightly", "2026-09-14", T0, None, "running")
    check("open row inside duration+grace is NOT stuck",
          mp.stuck_window_runs(WINDOWS, [fresh], T0 + timedelta(minutes=149)) == [])
    check("open row past duration+grace IS stuck",
          mp.stuck_window_runs(WINDOWS, [fresh], T0 + timedelta(minutes=151))
          == ["nightly:2026-09-14"])
    check("grace is per-window: sun-attended (200m) still open at +200m is not stuck",
          mp.stuck_window_runs(WINDOWS, [lrow("sun-attended", "2026-09-13", T0, None, "running")],
                               T0 + timedelta(minutes=250)) == [])
    check("... but is at +261m",
          mp.stuck_window_runs(WINDOWS, [lrow("sun-attended", "2026-09-13", T0, None, "running")],
                               T0 + timedelta(minutes=261)) == ["sun-attended:2026-09-13"])
    check("a finalized row is never stuck, however old",
          mp.stuck_window_runs(WINDOWS, [lrow("nightly", "2026-09-01", T0 - timedelta(days=13),
                                              T0 - timedelta(days=13), "green")], T0) == [])
    check("a terminal row with NULL finished_at is not stuck (it is not open)",
          mp.stuck_window_runs(WINDOWS, [lrow("nightly", "2026-09-01", T0 - timedelta(days=13),
                                              None, "aborted")], T0) == [])
    check("a retired window id gets grace only (still reported, never silently dropped)",
          mp.stuck_window_runs(WINDOWS, [lrow("tue-early", "2026-09-08", T0, None, "running")],
                               T0 + timedelta(minutes=61)) == ["tue-early:2026-09-08"])
    check("naive started_at is read as UTC, not rejected",
          mp.stuck_window_runs(WINDOWS, [lrow("nightly", "2026-09-14", T0.replace(tzinfo=None),
                                              None, "running")],
                               T0 + timedelta(hours=5)) == ["nightly:2026-09-14"])
    check("stuck output is sorted and one entry per row",
          mp.stuck_window_runs(WINDOWS, [
              lrow("sun-attended", "2026-09-13", T0 - timedelta(days=1), None, "running"),
              lrow("nightly", "2026-09-13", T0 - timedelta(days=1), None, "running")],
              T0) == ["nightly:2026-09-13", "sun-attended:2026-09-13"])

    # the two views agree: a stuck slot is ALSO missing (started != ran)
    stale_open = lrow("nightly", "2026-09-13", T0 - timedelta(days=1), None, "running")
    check("a stuck occurrence is also reported missing — never counted as ran",
          mp.missing_window_runs(expected, mp.completed_run_rows([stale_open]))
          == ["nightly:2026-09-13"]
          and mp.stuck_window_runs(WINDOWS, [stale_open], T0) == ["nightly:2026-09-13"])

    # no DSN -> the report is NOT verified, and both lists are empty, not absent
    os.environ.pop("SWEEP_PG_DSN", None)
    rep = mp.window_liveness_report({"windows": WINDOWS}, date(2026, 9, 14), now=T0)
    check("no DSN -> unverified report with both keys present",
          rep == {"missing": [], "stuck": [], "verified": False}, str(rep))
    check("window_liveness() keeps its (missing, verified) contract",
          mp.window_liveness({"windows": WINDOWS}, date(2026, 9, 14)) == ([], False))

    # ---- 3. CLI backward compatibility --------------------------------------
    legacy = ["--slot", "sat-attended", "--outcome", "green", "--trigger", "cron",
              "--plans-executed", "1", "--safe-updates", "7", "--notes", "n"]
    a = parse(legacy)
    check("legacy invocation parses unchanged",
          (a.slot, a.outcome, a.trigger, a.plans_executed, a.safe_updates, a.notes)
          == ("sat-attended", "green", "cron", 1, 7, "n"))
    check("legacy invocation is NOT a finalize and has no --finished",
          a.finalize is False and a.finished is None)
    check("legacy invocation passes validation", rec.validate_args(a) is None)
    for oc in ("green", "revert", "partial", "idle", "aborted"):
        a = parse(["--slot", "nightly", "--outcome", oc, "--trigger", "cron"])
        check(f"legacy outcome '{oc}' still accepted", a.outcome == oc)

    a = parse(["--slot", "nightly", "--outcome", "running", "--trigger", "cron"])
    check("--outcome running is accepted",
          a.outcome == "running" and rec.validate_args(a) is None)
    check("running is not a terminal outcome", "running" not in rec.TERMINAL_OUTCOMES)

    a = parse(["--slot", "nightly", "--outcome", "green", "--trigger", "cron", "--finalize"])
    check("--finalize parses", a.finalize is True and rec.validate_args(a) is None)
    a = parse(["--slot", "nightly", "--outcome", "green", "--trigger", "cron",
               "--finalize", "--finished", "2026-09-14T03:00:00+00:00"])
    check("--finished rides with --finalize", rec.validate_args(a) is None)

    a = parse(["--slot", "nightly", "--outcome", "running", "--trigger", "cron", "--finalize"])
    check("--finalize with --outcome running is refused",
          rec.validate_args(a) is not None)
    a = parse(["--slot", "nightly", "--outcome", "green", "--trigger", "cron",
               "--finished", "2026-09-14T03:00:00+00:00"])
    check("--finished without --finalize is refused",
          rec.validate_args(a) is not None)

    try:
        parse(["--slot", "nightly", "--outcome", "bogus", "--trigger", "cron"])
        check("unknown outcome is still rejected by argparse", False)
    except SystemExit:
        check("unknown outcome is still rejected by argparse", True)

    # no DSN -> loud exit 2, no write, for the new paths too (never silent)
    for argv in (["--slot", "nightly", "--outcome", "running", "--trigger", "cron"],
                 ["--slot", "nightly", "--outcome", "green", "--trigger", "cron", "--finalize"],
                 legacy):
        rc = rec.main(argv)
        check(f"no DSN -> exit 2 for {argv[3]}{' --finalize' if '--finalize' in argv else ''}",
              rc == 2, f"rc={rc}")

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} -> {', '.join(FAILURES)}")
        return 1
    print("all tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
