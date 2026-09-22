#!/usr/bin/env python3
"""Regression test: an ORCHESTRATED run with no database must die loudly
(F-28e8c394, 2026-09-22).

`FindingsWriter` degrades to markdown-only when `dsn` is falsy: emit() derives
the finding id and throws the row away, close() writes nothing. That is correct
for an operator running one check script by hand.

It was also what happened INSIDE A SWEEP. `runbooks/sweep-run.py` sets
SWEEP_CYCLE_ID and SWEEP_PG_DSN together, so a cycle id with no DSN means the
DSN setup (port-forward, secret decode) failed. The seven check scripts then
ran their full audits against the live cluster, printed a confident coloured
board, and persisted NOTHING — no findings, no cycle row — while the reconcile
step, the auto-close pass and the open-findings queue all read that silence as
"the sections were clean". A whole sweep evaporating with a green exit code is
the exact silent-loss class this module exists to prevent, and it is invisible
afterwards: there is no row to notice the absence of.

Measured before the fix, with SWEEP_CYCLE_ID set and SWEEP_PG_DSN unset:
    orchestrated = True, enabled = False, conn = None
    emit("critical", ...) -> "F-88f71372"     # minted, then dropped
    close(verdict="red")  -> None             # nothing written, no complaint

THE DIRECTION OF FAILURE MATTERS. Raising in __init__ changes behaviour for
every caller, so the cases below pin BOTH directions: the orchestrated-no-DB
shape must raise, and the two legitimate DB-less shapes (an ad-hoc markdown-only
run, and an offline test that attaches its own connection) must keep working.
A fix that made every dsn=None construction fatal would break the markdown-only
workflow the module explicitly supports.

Run:  python3 runbooks/tests/test-findings-writer-orchestrated-needs-db.py
"""

from __future__ import annotations

import importlib.util
import os
import sys
import types
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
os.environ.setdefault("_MISE_ACTIVATED", "1")
_SRC = _REPO / "runbooks" / "lib" / "findings_writer.py"

_spec = importlib.util.spec_from_file_location("fw_under_test", _SRC)
fw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fw)

CYCLE = "11111111-2222-3333-4444-555555555555"
FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


class no_env:
    """SWEEP_CYCLE_ID removed for the duration, then restored.

    The test process may well be a shell that exported it (an agent that
    sourced the sweep DSN helper, or a commit made mid-sweep — the pre-commit
    hook runs this suite). Every case below states its own orchestration
    explicitly rather than inheriting one.
    """

    def __init__(self, value: str | None = None):
        self._value = value

    def __enter__(self):
        self._prev = os.environ.get("SWEEP_CYCLE_ID")
        os.environ.pop("SWEEP_CYCLE_ID", None)
        if self._value:
            os.environ["SWEEP_CYCLE_ID"] = self._value
        return self

    def __exit__(self, *a):
        os.environ.pop("SWEEP_CYCLE_ID", None)
        if self._prev is not None:
            os.environ["SWEEP_CYCLE_ID"] = self._prev


def raises(exc, fn):
    try:
        fn()
    except exc as e:
        return e
    except Exception as e:  # noqa: BLE001 — wrong type is a failure, not an error
        return ("WRONG-TYPE", type(e).__name__, str(e))
    return None


def prefix_module():
    """The PRE-FIX module: the same source with the fail-closed guard removed.

    Text surgery on one line, so the straw cannot drift away from the real
    implementation the way a hand-written stand-in does.
    """
    src = _SRC.read_text()
    needle = "        if self._orchestrated and not self.dsn and not allow_no_db:"
    if needle not in src:
        raise AssertionError(
            "commissioning straw is broken: the guard line it reverts is not in "
            "findings_writer.py any more — re-derive it before trusting this suite")
    mod = types.ModuleType("fw_prefix")
    mod.__file__ = str(_SRC)
    exec(compile(src.replace(needle, "        if False:"), str(_SRC), "exec"),
         mod.__dict__)
    return mod


def main() -> int:
    print(__doc__.strip().splitlines()[0])
    print()

    # --- THE DEFECT: orchestrated + no DSN must raise -----------------------
    with no_env():
        err = raises(RuntimeError, lambda: fw.FindingsWriter(
            dsn=None, section="security", cycle_id=CYCLE, producer="script"))
        check("an explicit cycle_id with no DSN raises", isinstance(err, RuntimeError),
              f"got {err!r}")
        check("...and the message names the env var the operator must fix",
              isinstance(err, RuntimeError) and "SWEEP_PG_DSN" in str(err),
              f"got {str(err)[:120]!r}")
        check("...and it names the section, so a fan-out says which one died",
              isinstance(err, RuntimeError) and "security" in str(err))

    # sweep-run.py hands the cycle id down through the ENVIRONMENT, not the
    # argument (check scripts call cycle_id_from_env()). That path must raise too.
    with no_env(CYCLE):
        err = raises(RuntimeError, lambda: fw.FindingsWriter(
            dsn=None, section="doc", producer="script",
            cycle_id=fw.cycle_id_from_env()))
        check("the env-orchestrated path raises as well (the real sweep shape)",
              isinstance(err, RuntimeError), f"got {err!r}")

        err = raises(RuntimeError, lambda: fw.FindingsWriter(
            dsn="", section="doc", producer="script", cycle_id=CYCLE))
        check("an EMPTY-STRING dsn is refused too, not just None",
              isinstance(err, RuntimeError), f"got {err!r}")

    # --- THE OTHER DIRECTION: legitimate DB-less runs must still work -------
    with no_env():
        w = fw.FindingsWriter(dsn=None, section="doc", producer="script")
        check("an AD-HOC run with no DSN still degrades to markdown-only",
              w._enabled is False and w._orchestrated is False)
        fid = w.emit("warning", "a hand-run finding")
        check("...and still derives a finding id for the markdown report",
              isinstance(fid, str) and fid.startswith("F-"), f"got {fid!r}")

    with no_env(CYCLE):
        w = fw.FindingsWriter(dsn=None, section="doc", producer="script",
                              allow_no_db=True)
        check("allow_no_db=True is an explicit opt-out for offline tests",
              w._orchestrated is True and w._enabled is False)

    # --- ORDERING: a call-signature bug must not be masked by the env -------
    # These two assertions are why the guard sits AFTER the producer check.
    # test-autoclose-producer-scope.py pins them, and they must hold in a shell
    # that happens to export SWEEP_CYCLE_ID.
    with no_env(CYCLE):
        check("omitting producer= still raises TypeError, not the env error",
              isinstance(raises(TypeError, lambda: fw.FindingsWriter(
                  dsn=None, section="doc")), TypeError))
        check("a blank producer= still raises ValueError, not the env error",
              isinstance(raises(ValueError, lambda: fw.FindingsWriter(
                  dsn=None, section="doc", producer="  ")), ValueError))

    # --- COMMISSIONING STRAW ------------------------------------------------
    # Revert the guard and re-run the central case. It must FAIL: the pre-fix
    # module constructs happily and silently drops the finding.
    old = prefix_module()
    with no_env():
        # Literally the suite's central predicate, re-run against the reverted
        # module: it must come back None (nothing raised), i.e. the assertion
        # at the top of this file FAILS without the fix.
        still_raises = raises(RuntimeError, lambda: old.FindingsWriter(
            dsn=None, section="security", cycle_id=CYCLE, producer="script"))
        check("commissioning: with the guard reverted, the central assertion "
              "'an explicit cycle_id with no DSN raises' FAILS",
              still_raises is None, f"got {still_raises!r}")

        w = old.FindingsWriter(dsn=None, section="security", cycle_id=CYCLE,
                               producer="script")
        dropped_id = w.emit("critical", "a finding the sweep would have lost")
        closed = w.close(verdict="red")
        check("commissioning: ...it mints a finding id and DROPS it "
              "(this is the defect, reproduced)",
              isinstance(dropped_id, str) and dropped_id.startswith("F-")
              and w._conn is None and not closed,
              f"id={dropped_id!r} closed={closed!r}")

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
