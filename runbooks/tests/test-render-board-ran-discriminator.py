#!/usr/bin/env python3
"""Pin how render-board.py decides a section REPORTED (F-bfb9ec80).

On 2026-09-17 the board rendered two false gaps out of six: `slo` had
written five snapshots and `doc` had run clean (its findings filed under
`plan`, as the rules require), and both rendered as DID NOT REPORT because
the renderer answered "did it report?" from finding rows plus the
orchestrator's declared `ran` set — and the orchestrator had declared
neither. "No findings" and "no report" are different answers; only the
second is a gap.

The renderer now reads every durable per-section artifact, in evidence
order: rows, the section's own completion record (written by its
FindingsWriter at close), SLO snapshots inside the cycle window, then the
reconcile's declaration. The snapshot window is bounded by the NEXT cycle's
start, like the action-list query — never by finished_at.

COMMISSIONING STRAW: the pre-fix rule (rows or declared `ran`) is transcribed
and run over the 2026-09-17 shape; it renders both sections as gaps. The
fixed rule renders both as clean runs with their evidence named.

Run: python3 runbooks/tests/test-render-board-ran-discriminator.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

os.environ.pop("SWEEP_PG_DSN", None)
ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("render_board", ROOT / "runbooks" / "render-board.py")
rb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rb)

PASS = FAIL = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}" + (f"\n        {detail}" if detail else ""))


def old_rule(d: dict, s: str) -> str:
    """The pre-fix section line, transcribed from render() as of 9d0e77b7."""
    info = d["sections"].get(s)
    if info is None:
        if s in d.get("ran", set()):
            return "ran clean — 0 new (run declared at reconcile)"
        return "**DID NOT REPORT** — gap, not a pass"
    return f"{info['new']} new, {info['open']} open"


# The 2026-09-17 shape: health/security/version wrote rows; doc closed clean;
# slo wrote snapshots; media declared at reconcile; the orchestrator's `ran`
# left doc and slo out.
NIGHT = {
    "sections": {"health": {"new": 1, "open": 4}, "security": {"new": 0, "open": 210},
                 "version": {"new": 2, "open": 9}},
    "completed": {"doc": {"verdict": "green", "at": "2026-09-17T02:03:11+00:00", "emitted": 0},
                  "health": {"verdict": "yellow", "at": "2026-09-17T02:20:00+00:00", "emitted": 7}},
    "slo_snapshots_in_cycle": 5,
    "ran": {"health", "security", "version", "media"},
    "incomplete": {},
}

print("render-board ran discriminator\n")
print("-- COMMISSIONING STRAW: the rows-or-declared rule --")
check("STRAW renders doc as a gap although its writer closed with a verdict",
      "DID NOT REPORT" in old_rule(NIGHT, "doc"))
check("STRAW renders slo as a gap although it wrote five snapshots",
      "DID NOT REPORT" in old_rule(NIGHT, "slo"))

print("\n-- evidence order --")
check("rows win: health has rows AND a completion record -> the row line",
      rb.section_evidence(NIGHT, "health") == "rows" and rb.section_line(NIGHT, "health") == "1 new, 4 open")
check("doc: completion record -> ran clean, verdict and time named",
      rb.section_evidence(NIGHT, "doc") == "completed"
      and rb.section_line(NIGHT, "doc") == "ran clean — 0 findings (section closed with verdict green at 2026-09-17T02:03)")
check("slo: snapshots inside the cycle window -> ran clean, count named",
      rb.section_evidence(NIGHT, "slo") == "snapshots"
      and rb.section_line(NIGHT, "slo") == "ran clean — 0 findings (5 SLO snapshot(s) written this cycle)")
check("media: only the reconcile's declaration -> the declared line (still honoured)",
      rb.section_evidence(NIGHT, "media") == "declared"
      and "declared at reconcile" in rb.section_line(NIGHT, "media"))
check("every 2026-09-17 section now reports; no gap",
      all(rb.section_reported(NIGHT, s) for s in rb.EXPECTED_SECTIONS))

nothing = {"sections": {}, "completed": {}, "slo_snapshots_in_cycle": 0, "ran": set(), "incomplete": {}}
check("with no artifact at all a section is still a GAP (the fix does not manufacture reports)",
      all(not rb.section_reported(nothing, s) for s in rb.EXPECTED_SECTIONS)
      and "DID NOT REPORT" in rb.section_line(nothing, "doc"))
check("snapshots count only for slo, never for another section",
      not rb.section_reported({**nothing, "slo_snapshots_in_cycle": 3}, "doc")
      and rb.section_reported({**nothing, "slo_snapshots_in_cycle": 3}, "slo"))
check("a completion record for a section with rows never hides the rows",
      rb.section_line({**nothing, "sections": {"doc": {"new": 3, "open": 3}},
                       "completed": {"doc": {"verdict": "yellow"}}}, "doc") == "3 new, 3 open")

inc = {**NIGHT, "incomplete": {"doc": "trivy cache unreachable"}}
check("an INCOMPLETE veto renders as a suffix on the clean line, never as a gap",
      rb.section_reported(inc, "doc")
      and rb.section_line(inc, "doc").endswith("— coverage INCOMPLETE (trivy cache unreachable)"))
check("a completion record without a timestamp still renders",
      rb.section_line({**nothing, "completed": {"doc": {"verdict": "green"}}}, "doc")
      == "ran clean — 0 findings (section closed with verdict green)")

print("\n-- collect(): the notes are parsed and the snapshot window is bounded correctly --")


class FakeCursor:
    """Answers collect()'s statements by shape; records every SQL."""

    def __init__(self, notes: str | None, snapshot_count: int, section_rows):
        self.notes = notes
        self.snapshot_count = snapshot_count
        self.section_rows = section_rows
        self.sql: list[str] = []
        self._last = ""

    def execute(self, sql, params=None):
        self._last = " ".join(sql.split())
        self.sql.append(self._last)

    def fetchone(self):
        s = self._last
        if s.startswith("SELECT started_at, finished_at, verdict"):
            return ("2026-09-17 02:00:00+00", None, None)
        if s.startswith("SELECT notes"):
            return (self.notes,)
        if s.startswith("SELECT count(*) FROM slo_snapshots"):
            return (self.snapshot_count,)
        return None

    def fetchall(self):
        s = self._last
        if "GROUP BY section" in s:
            return self.section_rows
        return []


notes = json.dumps({"ran": ["health", "security", "version", "media"],
                    "completed": {"doc": {"verdict": "green", "at": "2026-09-17T02:03:11+00:00"}},
                    "incomplete": {"security": "NVD throttled"}})
cur = FakeCursor(notes, 5, [("health", 1, 4), ("security", 0, 210), ("version", 2, 9)])
saved = rb.planned_findings
rb.planned_findings = lambda c: {}
try:
    out = rb.collect(cur, "00000000-0000-0000-0000-000000000001")
finally:
    rb.planned_findings = saved
check("collect parses completed / incomplete / ran from the notes JSON",
      out["completed"] == {"doc": {"verdict": "green", "at": "2026-09-17T02:03:11+00:00"}}
      and out["incomplete"] == {"security": "NVD throttled"}
      and out["ran"] == {"health", "security", "version", "media"})
check("collect counts SLO snapshots in the cycle window", out["slo_snapshots_in_cycle"] == 5)
check("gaps are derived from section_reported -> none on the 2026-09-17 shape", out["gaps"] == [])
snap_sql = next((s for s in cur.sql if s.startswith("SELECT count(*) FROM slo_snapshots")), "")
check("the snapshot window is bounded by the NEXT cycle's start, not finished_at",
      "MIN(started_at)" in snap_sql and "started_at >" in snap_sql and "finished_at" not in snap_sql,
      snap_sql)
check("the snapshot window anchors on this cycle's started_at",
      "taken_at >= (SELECT started_at FROM sweep_cycles WHERE cycle_id" in snap_sql, snap_sql)

cur = FakeCursor("not json at all", 0, [])
rb.planned_findings = lambda c: {}
try:
    out2 = rb.collect(cur, "00000000-0000-0000-0000-000000000002")
finally:
    rb.planned_findings = saved
check("unparsable notes -> empty records, every section a gap (fails closed)",
      out2["completed"] == {} and out2["ran"] == set() and out2["gaps"] == rb.EXPECTED_SECTIONS)

print("\n-- render() uses the discriminator --")
src = (ROOT / "runbooks" / "render-board.py").read_text()
check("render() builds each section line through section_line()",
      'L.append(f"- `{s}`: {section_line(d, s)}")' in src)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
