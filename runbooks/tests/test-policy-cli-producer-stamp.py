#!/usr/bin/env python3
"""Regression test: a hand-authored finding must survive the next script sweep
of its section (F-d93b2328, 2026-09-22).

Auto-close resolves open rows in a section that the current run did not
re-emit, and `foreign_candidates()` is the gate that stops a run closing rows
it does not own. The gate reads ONE key: `metadata.producer`.

`policy-cli.py finding add` does not go through `FindingsWriter.emit()` — it
INSERTs into sweep_findings directly — and it stamped only the older spelling:

    {"authored_by": "policy-cli", "subsection": "plan_driver"}

so the gate saw no producer at all. An untagged row is deliberately closeable
(the back-catalogue carve-out), so every hand-authored driver written into a
script-owned section was auto-closed by the next orchestrated run of that
section's script — silently, because a closed finding leaves the queue.

Measured before the fix:
    foreign_candidates([row_with_authored_by_only], "script") -> []
i.e. NOT held back.

THE FIX HAS TWO HALVES and both are pinned below, because either alone leaves a
real gap:

  write side  — `finding add` now stamps `producer` as well. Fixes new rows.
  read  side  — `row_producer()` accepts `authored_by` as the legacy spelling
                of the same fact. Fixes the rows ALREADY in the table, which
                the write-side change can never reach.

THE CARVE-OUT MUST NOT MOVE. Rows carrying NEITHER key stay closeable. Holding
them was tried on 2026-09-06 and reverted within the hour: it broke 9 of 31
cases in test_findings_writer_autoclose.py because rows predate the stamp
entirely. Narrowing a gate to kill a false positive is how this codebase has
repeatedly created a false negative, so the "still closes" cases below are as
load-bearing as the "held back" ones.

Run:  python3 runbooks/tests/test-policy-cli-producer-stamp.py
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import sys
import types
from pathlib import Path
from types import SimpleNamespace

_REPO = Path(__file__).resolve().parents[2]
os.environ.setdefault("_MISE_ACTIVATED", "1")
os.chdir(_REPO)

_FW_SRC = _REPO / "runbooks" / "lib" / "findings_writer.py"
_PC_SRC = _REPO / "runbooks" / "policy-cli.py"

_spec = importlib.util.spec_from_file_location("fw_under_test", _FW_SRC)
fw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fw)

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


def candidate(fid, meta):
    """A _autoclose_stale candidate: (db_id, (fid, sev, title, last_seen, meta))."""
    return (hash(fid) & 0xffff, (fid, "warning", "t", "2026-09-01", meta))


# ---------------------------------------------------------------------------
# The write side: call cmd_finding_add for real and capture what it INSERTs.
# ---------------------------------------------------------------------------

class FakeCursor:
    def __init__(self, log):
        self.log = log
        self._last = ""

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self._last = " ".join(sql.split())
        self.log.append((self._last, params))

    def fetchone(self):
        if self._last.startswith("SELECT finding_id FROM sweep_findings"):
            return None                      # not already open
        if self._last.startswith("SELECT cycle_id FROM sweep_cycles"):
            return {"cycle_id": "c0000000-0000-0000-0000-000000000000"}
        return None


class FakeConn:
    def __init__(self, log):
        self.log = log

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def cursor(self):
        return FakeCursor(self.log)

    def commit(self):
        pass


def load_policy_cli(source_transform=None):
    """Import policy-cli.py as a module, optionally with the fix reverted."""
    src = _PC_SRC.read_text()
    if source_transform:
        src = source_transform(src)
    sys.path.insert(0, str(_REPO / "runbooks"))
    mod = types.ModuleType("policy_cli_under_test")
    mod.__file__ = str(_PC_SRC)
    exec(compile(src, str(_PC_SRC), "exec"), mod.__dict__)
    return mod


def added_metadata(mod) -> dict:
    """Run `finding add` against a fake DB and return the metadata it wrote."""
    log: list[tuple[str, tuple]] = []
    mod._connect = lambda dsn: FakeConn(log)
    mod._finding_row = lambda cur, fid: {
        "finding_id": fid, "section": "security", "severity": "warning",
        "metadata": {},
    }
    args = SimpleNamespace(
        section="security", subsection=None, title="a hand-authored driver",
        severity="warning", action="do the thing", detail=None, detail_file=None,
        plan=None, component=None,
    )
    # cmd_finding_add prints the reference block; keep the suite's output clean.
    with contextlib.redirect_stdout(io.StringIO()):
        mod.cmd_finding_add(args, "dsn://ignored")
    inserts = [(s, p) for s, p in log if s.startswith("INSERT INTO sweep_findings")]
    assert len(inserts) == 1, f"expected exactly one INSERT, got {len(inserts)}"
    return json.loads(inserts[0][1][-1])


def main() -> int:
    print(__doc__.strip().splitlines()[0])
    print()

    # --- READ SIDE: the gate must hold a legacy authored_by-only row --------
    legacy = {"authored_by": "policy-cli", "subsection": "plan_driver"}
    held = fw.foreign_candidates([candidate("F-d93b2328", legacy)], "script")
    check("a row carrying ONLY authored_by is held back from a script run",
          len(held) == 1, f"got {held!r}")

    check("row_producer() resolves authored_by as the legacy spelling",
          fw.row_producer(legacy) == "policy-cli",
          f"got {fw.row_producer(legacy)!r}")
    check("row_producer() prefers producer when both are present",
          fw.row_producer({"producer": "doc-agent",
                           "authored_by": "policy-cli"}) == "doc-agent")

    # --- THE CARVE-OUT: do not blind the detector --------------------------
    for label, meta in (("an empty metadata mapping", {}),
                        ("a NULL metadata column", None),
                        ("an explicit producer: None", {"producer": None}),
                        ("unrelated metadata only", {"component": "postgres"})):
        check(f"untagged legacy row stays closeable — {label}",
              fw.foreign_candidates([candidate("F-legacy", meta)], "script") == [],
              f"got {fw.row_producer(meta)!r}")

    check("a script's OWN row still closes on a script run",
          fw.foreign_candidates(
              [candidate("F-own", {"producer": "script"})], "script") == [])
    check("policy-cli's own row is NOT held from a policy-cli run (symmetry)",
          fw.foreign_candidates([candidate("F-pc", legacy)], "policy-cli") == [])

    # --- WRITE SIDE: `finding add` stamps producer -------------------------
    pc = load_policy_cli()
    meta = added_metadata(pc)
    check("`finding add` stamps metadata.producer", meta.get("producer") == "policy-cli",
          f"got {meta!r}")
    check("...and keeps authored_by, which render-board.py reads",
          meta.get("authored_by") == "policy-cli")
    check("...and the row it writes is held back by the gate end-to-end",
          len(fw.foreign_candidates([candidate("F-new", meta)], "script")) == 1)

    # --- THE BACKSTOP MUST USE THE SAME PREDICATE --------------------------
    # sweep-run.py runs a second auto-close pass after every step, with its own
    # copy of the producer gate. On 2026-09-05 a writer-side gate was shipped,
    # the suite went green, and the backstop closed the rows anyway in the next
    # cycle — the third divergence between the two implementations. So the
    # backstop must call the SHARED predicate, not re-spell it.
    sweep_src = (_REPO / "runbooks" / "sweep-run.py").read_text()
    check("the sweep-run backstop imports the shared predicate",
          "from lib.findings_writer import finding_matches_component, row_producer"
          in sweep_src)
    check("...and uses it instead of reading metadata['producer'] itself",
          "_producer = row_producer(meta)" in sweep_src
          and '_producer = (meta or {}).get("producer")' not in sweep_src)

    # --- COMMISSIONING STRAW (read side) -----------------------------------
    # Revert row_producer to the pre-fix predicate — producer only — and the
    # central assertion must FAIL.
    def prefix_foreign(cands, run_producer):
        return [c for c in cands
                if (c[1][4] or {}).get("producer") not in (None, run_producer)]

    check("commissioning: the PRE-FIX gate does NOT hold an authored_by-only row",
          prefix_foreign([candidate("F-d93b2328", legacy)], "script") == [])

    # --- COMMISSIONING STRAW (write side) ----------------------------------
    # Revert the stamp in policy-cli's source and re-run the same capture.
    needle = '"producer": "policy-cli",\n'
    src_now = _PC_SRC.read_text()
    if needle not in src_now:
        check("commissioning: the write-side straw can find the line it reverts",
              False, "the `producer` stamp is not spelled as this straw expects")
    else:
        pc_old = load_policy_cli(lambda s: s.replace(needle, "", 1))
        meta_old = added_metadata(pc_old)
        check("commissioning: with the stamp reverted, `finding add` writes no producer",
              "producer" not in meta_old, f"got {meta_old!r}")
        check("commissioning: ...and that row is silently closeable by a script run "
              "under the pre-fix gate (the defect, reproduced)",
              prefix_foreign([candidate("F-old", meta_old)], "script") == [])

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} -> {', '.join(FAILURES)}")
        return 1
    print("all tests passed")
    return 0


def test_pytest_entry() -> None:
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())
