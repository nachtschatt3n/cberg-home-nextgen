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

  --slot takes the BARE window id from maintenance-windows.yaml
  ("sat-attended"), NOT the dated occurrence form ("sat-attended:2026-09-05").
  The date goes in --run-date. A dated value is normalized with a warning --
  see normalize_slot() for why it silently inverted the liveness check.

Two-phase recording (2026-09-14). Five nightly dates had NO row at all: the
OpenClaw cron reports `ok` on DELIVERY of the trigger to the Mac console
session, not on completion, so a window that started and died mid-run left
the same nothing as a window that never fired. The fix is to write the row
at OPEN, not only at close-out:

  window-run-record.py --slot nightly --outcome running --trigger cron
      -> inserts a row with finished_at NULL ("the window has started")
  window-run-record.py --slot nightly --outcome green --trigger cron \
      --plans-executed 1 --safe-updates 3 --finalize
      -> UPDATEs the latest still-running row for (slot, run_date): outcome,
         finished_at (now, or --finished), counters, notes appended; the
         trigger is kept from the open. With no running row it falls back to
         the plain insert and WARNS -- a close-out must never be lost because
         the open was skipped.

A running row that never gets finalized is reported by maintenance-plan.py
under window_liveness.stuck once it is older than the window's duration_min
plus a grace period, and it does NOT satisfy the per-occurrence liveness
assertion -- "started" is not "ran".

Exit codes: 0 recorded; 2 no DSN (prints the exact row it WOULD have written,
so a degraded environment is loud, never silent).
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime, timezone

_DATED_SLOT = re.compile(r"^(?P<id>.+):(?P<date>\d{4}-\d{2}-\d{2})$")

# The close-out vocabulary. `running` is the OPEN marker (finished_at NULL);
# everything else is terminal and is what --finalize writes over it.
TERMINAL_OUTCOMES = ("green", "revert", "partial", "idle", "aborted")
RUNNING = "running"
OUTCOMES = TERMINAL_OUTCOMES + (RUNNING,)

_FINALIZE_SELECT = ("SELECT id, started_at, outcome, finished_at, notes, trigger"
                    " FROM window_runs WHERE slot = %s AND run_date = %s")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", required=True)
    ap.add_argument("--outcome", required=True, choices=list(OUTCOMES))
    ap.add_argument("--trigger", required=True, choices=["cron", "ad-hoc"])
    ap.add_argument("--plans-executed", type=int, default=0)
    ap.add_argument("--safe-updates", type=int, default=0)
    ap.add_argument("--run-date", default=None, help="YYYY-MM-DD, default today")
    ap.add_argument("--started", default=None, help="ISO ts, default now")
    ap.add_argument("--finished", default=None,
                    help="ISO ts for --finalize, default now")
    ap.add_argument("--notes", default=None)
    ap.add_argument("--finalize", action="store_true",
                    help="close the latest still-running row for (slot, run_date) "
                         "instead of inserting; falls back to insert with a warning")
    return ap


def validate_args(a: argparse.Namespace) -> str | None:
    """Pure: the argument combinations argparse cannot express. None = ok."""
    if a.finalize and a.outcome == RUNNING:
        return "--finalize needs a terminal outcome; 'running' is the OPEN marker"
    if a.finished and not a.finalize:
        return "--finished only applies with --finalize"
    return None


def finalize_target(rows):
    """Pure: which existing row --finalize updates.

    rows: (id, started_at, outcome, finished_at, ...) for ONE (slot, run_date).
    Returns the id of the latest-started row that is still open — outcome
    'running' AND finished_at NULL — or None. Both conditions matter: a row
    already closed by an earlier finalize must not be re-closed by a second
    close-out (it would silently overwrite the real result), and a terminal
    row that happens to have a NULL finished_at is not an open window.
    Latest-by-started_at because an aborted-and-retried window legitimately
    opens twice on one date; the close-out belongs to the newest open.
    """
    open_rows = [r for r in rows if r[2] == RUNNING and r[3] is None]
    if not open_rows:
        return None
    return max(open_rows, key=lambda r: r[1])[0]


def append_notes(existing: str | None, new: str | None) -> str | None:
    """Pure: close-out notes are appended to the open's notes, never replace
    them — the open often records WHY the window was triggered."""
    if not new:
        return existing
    if not existing:
        return new
    return f"{existing}\n{new}"


def _terminal_sql(row):
    """The plain insert every pre-2026-09-14 caller has always used."""
    return (
        "INSERT INTO window_runs (slot, run_date, started_at, finished_at,"
        " trigger, outcome, plans_executed, safe_updates, notes)"
        " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)"
        " ON CONFLICT (slot, run_date, started_at) DO UPDATE SET"
        " finished_at=EXCLUDED.finished_at, outcome=EXCLUDED.outcome,"
        " plans_executed=EXCLUDED.plans_executed,"
        " safe_updates=EXCLUDED.safe_updates, notes=EXCLUDED.notes",
        row)


def normalize_slot(slot: str, run_date: str) -> tuple[str, str | None]:
    """Return (bare_slot, warning). `slot` is the BARE window id.

    Callers naturally say "sat-attended:2026-09-05" because that is how a
    window OCCURRENCE is named in prose and in plan frontmatter — but the
    table already carries the date in its own `run_date` column, so writing
    the dated form makes `slot` disagree with what
    `maintenance-plan.py:expected_slots()` emits (a bare id). Every dated row
    is then invisible to `missing_window_runs()`, and a window that ran
    correctly is reported as a missing occurrence. That inverted the liveness
    check for the whole ledger (2026-09-05): 3 of 8 reported-missing slots had
    rows, and the ONLY slot that "passed" was one recorded in the wrong form.

    Normalizing here rather than on read is deliberate — one choke point, so a
    future caller cannot poison the ledger again, and a read-side fallback
    cannot hide that it happened.
    """
    m = _DATED_SLOT.match(slot)
    if not m:
        return slot, None
    bare, embedded = m.group("id"), m.group("date")
    warn = (f"window-run-record: --slot '{slot}' carries an embedded date; "
            f"recording slot='{bare}' (the date belongs in --run-date). ")
    if embedded != run_date:
        warn += (f"NOTE: embedded date {embedded} != run_date {run_date}; "
                 f"run_date wins.")
    return bare, warn


def main(argv=None) -> int:
    ap = build_parser()
    a = ap.parse_args(argv)
    err = validate_args(a)
    if err:
        ap.error(err)

    now = datetime.now(timezone.utc)
    run_date = a.run_date or now.date().isoformat()
    started = a.started or now.isoformat()
    slot, warn = normalize_slot(a.slot, run_date)
    if warn:
        print(warn, file=sys.stderr)
    # An OPEN row has no finish; a terminal insert finishes now (as always).
    finished = None if a.outcome == RUNNING else (a.finished or now.isoformat())
    row = (slot, run_date, started, finished, a.trigger,
           a.outcome, a.plans_executed, a.safe_updates, a.notes)
    verb = "finalized" if a.finalize else "written"

    dsn = os.environ.get("SWEEP_PG_DSN")
    if not dsn:
        print("window-run-record: NO SWEEP_PG_DSN — run NOT recorded. "
              f"Would have {verb}: slot={slot} date={run_date} "
              f"outcome={a.outcome} trigger={a.trigger}", file=sys.stderr)
        return 2

    import psycopg
    with psycopg.connect(dsn, connect_timeout=10) as c, c.cursor() as cur:
        target = None
        if a.finalize:
            cur.execute(_FINALIZE_SELECT, (slot, run_date))
            existing = cur.fetchall()
            target = finalize_target(existing)
            if target is None:
                print(f"window-run-record: WARNING no running row for "
                      f"{slot} {run_date} — nothing to finalize; inserting a "
                      f"fresh {a.outcome} row instead (was the open skipped?)",
                      file=sys.stderr)
        if target is not None:
            old = next(r for r in existing if r[0] == target)
            cur.execute(
                "UPDATE window_runs SET outcome=%s, finished_at=%s,"
                " plans_executed=%s, safe_updates=%s, notes=%s WHERE id=%s",
                (a.outcome, finished, a.plans_executed, a.safe_updates,
                 append_notes(old[4], a.notes), target))
            kept_trigger = old[5]
            if kept_trigger != a.trigger:
                print(f"window-run-record: trigger kept as '{kept_trigger}' "
                      f"from the open (--trigger {a.trigger} ignored)",
                      file=sys.stderr)
            print(f"recorded: {slot} {run_date} {a.outcome} "
                  f"(plans={a.plans_executed}, safe={a.safe_updates}, "
                  f"{kept_trigger}) [finalized running row id={target}]")
            return 0
        cur.execute(*_terminal_sql(row))
    if a.outcome == RUNNING:
        print(f"recorded: {slot} {run_date} running "
              f"(started {started}, {a.trigger}) — finalize at close-out")
        return 0
    print(f"recorded: {slot} {run_date} {a.outcome} "
          f"(plans={a.plans_executed}, safe={a.safe_updates}, {a.trigger})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
