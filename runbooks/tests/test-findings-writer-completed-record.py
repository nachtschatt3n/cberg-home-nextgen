#!/usr/bin/env python3
"""Pin FindingsWriter's per-section completion record (F-bfb9ec80).

A section that ran clean writes no finding rows, so from the DB alone it was
indistinguishable from a section that never ran; the board rendered it as
DID NOT REPORT. The writer is the one process that knows for certain that
its section finished, so `close(verdict=…)` now records
`notes.completed[section] = {verdict, at, emitted}` on the shared cycle row
— under the same row lock the veto notes use, merged into whatever the row
already carries, never replacing another section's record.

The connection is a fake that records SQL, in the same shape
runbooks/lib/test_findings_writer_autoclose.py uses, so each assertion is
about the DECISION and the statement it produced, not a DB side effect.

COMMISSIONING STRAW: the pre-fix decision rule for "did this section
report?" (any finding row for the section in this cycle) is applied to the
statement log of a clean close — it answers "no". The completion record on
the same log answers "yes, verdict green".

Run: python3 runbooks/tests/test-findings-writer-completed-record.py
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

os.environ.pop("SWEEP_PG_DSN", None)
for k in ("SWEEP_AUTOCLOSE", "SWEEP_AUTOCLOSE_DRYRUN"):
    os.environ.pop(k, None)
ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "findings_writer", ROOT / "runbooks" / "lib" / "findings_writer.py")
fw = importlib.util.module_from_spec(_spec)
sys.modules["findings_writer"] = fw
_spec.loader.exec_module(fw)

PASS = FAIL = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}" + (f"\n        {detail}" if detail else ""))


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self._last = ""

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self._last = " ".join(sql.split())
        self.conn.log.append((self._last, params))
        # Keep the notes "row" live across statements, like a real row would.
        if self._last.startswith("UPDATE sweep_cycles SET notes"):
            self.conn.notes = params[0]

    def fetchall(self):
        return []      # no stale candidates: nothing to auto-close

    def fetchone(self):
        if self._last.startswith("SELECT notes") and self.conn.notes is not None:
            return (self.conn.notes,)
        return None


class FakeConn:
    def __init__(self, notes=None):
        self.log: list = []
        self.notes = notes

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


def writer(section="doc", orchestrated=True, notes=None):
    cid = "11111111-2222-3333-4444-555555555555" if orchestrated else None
    w = fw.FindingsWriter(dsn=None, section=section, cycle_id=cid,
                          producer="script", allow_no_db=True)
    conn = FakeConn(notes=notes)
    w._conn = conn
    w._enabled = True
    w._run_started = datetime(2026, 9, 17, 2, 0, tzinfo=timezone.utc)
    w._emitted_fps = set()
    return w, conn


def completed_record(conn):
    """The notes JSON the LAST `UPDATE sweep_cycles SET notes` wrote, or None."""
    upd = [p for s, p in conn.log if s.startswith("UPDATE sweep_cycles SET notes")]
    if not upd:
        return None
    return json.loads(upd[-1][0]).get("completed")


def old_reported(conn, section) -> bool:
    """Pre-fix rule: a section reported iff it wrote a finding row this cycle."""
    return any(s.startswith("INSERT INTO sweep_findings") for s, _ in conn.log)


print("findings-writer completion record\n")

print("-- COMMISSIONING STRAW --")
w, conn = writer()
with contextlib.redirect_stdout(io.StringIO()):
    w.close(verdict="green")
check("STRAW: by the rows-only rule a clean close never reported",
      old_reported(conn, "doc") is False)
rec = completed_record(conn)
check("the completion record on the SAME log says the section closed green",
      rec is not None and rec.get("doc", {}).get("verdict") == "green", str(rec))
check("the record carries a UTC timestamp and the emitted count (0 for a clean run)",
      rec is not None and rec["doc"]["at"].endswith("+00:00") and rec["doc"]["emitted"] == 0, str(rec))

print("\n-- when it is and is not written --")
w, conn = writer()
with contextlib.redirect_stdout(io.StringIO()):
    w.close()
check("bare close() (the crash path, no verdict) records NO completion",
      completed_record(conn) is None)
w, conn = writer()
with contextlib.redirect_stdout(io.StringIO()):
    w.close(verdict="green", section_complete=False)
check("an explicit section_complete=False records NO completion", completed_record(conn) is None)
w, conn = writer(orchestrated=False)
with contextlib.redirect_stdout(io.StringIO()):
    w.close(verdict="yellow")
check("an ad-hoc (non-orchestrated) run still records its completion on its own cycle row",
      (completed_record(conn) or {}).get("doc", {}).get("verdict") == "yellow")
w, conn = writer()
w.mark_incomplete("trivy cache unreachable")
with contextlib.redirect_stdout(io.StringIO()):
    w.close(verdict="red")
notes = json.loads(conn.notes)
check("a vetoed (INCOMPLETE) run records BOTH completion and the veto — different facts",
      notes.get("completed", {}).get("doc", {}).get("verdict") == "red"
      and notes.get("incomplete", {}).get("doc") == "trivy cache unreachable", str(notes))

print("\n-- merge semantics on the shared row --")
existing = json.dumps({"ran": ["health"], "completed": {"slo": {"verdict": "green", "at": "x"}},
                       "uncovered": {"version": {"a": "b"}}})
w, conn = writer(section="doc", notes=existing)
with contextlib.redirect_stdout(io.StringIO()):
    w.close(verdict="green")
merged = json.loads(conn.notes)
check("another section's completion record survives", merged["completed"]["slo"]["verdict"] == "green")
check("this section's record is added beside it", merged["completed"]["doc"]["verdict"] == "green")
check("unrelated keys (ran, uncovered) are untouched",
      merged["ran"] == ["health"] and merged["uncovered"] == {"version": {"a": "b"}})
w, conn = writer(section="doc", notes="legacy free text")
with contextlib.redirect_stdout(io.StringIO()):
    w.close(verdict="green")
legacy = json.loads(conn.notes)
check("legacy free-text notes are preserved under legacy_notes, not overwritten",
      legacy.get("legacy_notes") == "legacy free text" and legacy["completed"]["doc"]["verdict"] == "green")

print("\n-- the write is locked and the row is guaranteed --")
w, conn = writer()
with contextlib.redirect_stdout(io.StringIO()):
    w.close(verdict="green")
stmts = [s for s, _ in conn.log]
# The record's own three statements: the LAST INSERT-if-missing, then a
# SELECT … FOR UPDATE and an UPDATE after it (earlier SELECT FOR UPDATEs belong
# to the veto-note retraction that runs first).
i_ins = max((i for i, s in enumerate(stmts) if s.startswith("INSERT INTO sweep_cycles")), default=-1)
i_sel = next((i for i, s in enumerate(stmts) if i > i_ins
              and s.startswith("SELECT notes FROM sweep_cycles") and "FOR UPDATE" in s), -1)
i_upd = next((i for i, s in enumerate(stmts) if i > i_sel
              and s.startswith("UPDATE sweep_cycles SET notes")), -1)
check("INSERT-if-missing, then SELECT … FOR UPDATE, then UPDATE — in that order",
      0 <= i_ins < i_sel < i_upd, str(stmts))
check("the completion record is the LAST notes write (it merges onto the veto notes)",
      i_upd == max(i for i, s in enumerate(stmts) if s.startswith("UPDATE sweep_cycles SET notes")))

print("\n-- withheld when the writer itself distrusts the run --")


class RefusingCursor(FakeCursor):
    """One open stale row to close, so a zero-emit run trips the breaker."""

    def fetchall(self):
        if self._last.startswith("SELECT id, finding_id, severity"):
            return [(101, "F-aaaa1111", "critical", "someapp: image ghcr.io/example/app 1.0.0 → 2.0.0",
                     datetime(2026, 8, 17, 4, 0, tzinfo=timezone.utc), {})]
        return []


class RefusingConn(FakeConn):
    def cursor(self):
        return RefusingCursor(self)


w = fw.FindingsWriter(dsn=None, section="version", cycle_id="11111111-2222-3333-4444-555555555555",
                      producer="script", allow_no_db=True)
conn = RefusingConn()
w._conn, w._enabled = conn, True
w._run_started = datetime(2026, 9, 17, 2, 0, tzinfo=timezone.utc)
w._emitted_fps = set()
with contextlib.redirect_stdout(io.StringIO()):
    w.close(verdict="green")
check("zero-emit run REFUSED by the circuit breaker -> no completion record (the board must not read it as clean)",
      completed_record(conn) is None
      and not any("resolved_at = now()" in s for s, _ in conn.log), str([s for s, _ in conn.log]))

os.environ["SWEEP_AUTOCLOSE_DRYRUN"] = "1"
try:
    w, conn = writer()
    with contextlib.redirect_stdout(io.StringIO()):
        w.close(verdict="green")
    check("SWEEP_AUTOCLOSE_DRYRUN=1 writes nothing — including this record",
          completed_record(conn) is None)
finally:
    os.environ.pop("SWEEP_AUTOCLOSE_DRYRUN", None)
check("the completion record never touches sweep_findings",
      not any("sweep_findings" in s and "UPDATE" in s for s in stmts))

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
