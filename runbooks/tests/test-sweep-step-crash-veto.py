#!/usr/bin/env python3
"""Regression tests: a crashed sweep step must never read as a completed run.

sweep-run.py scores a step "completed" on `rc in (0, 1, 2)` — 1/2 normally
meaning "found findings", not "crashed". A Python traceback from an uncaught
exception ALSO exits 1 by default, so without an explicit crash veto a mid-run
abort is indistinguishable from a clean pass, and sweep-run.py's own auto-close
then resolves every open finding in that section as "didn't re-fire this
cycle" — including ones the crashed run never got anywhere near.

This happened for real on 2026-08-24: the version scan crashed four apps in
(a two-part image tag broke `parse_version`), exited 1, was scored complete,
and 25 open findings auto-closed — 9 of them wrongly, including a live Talos
Renovate PR. check-all-versions.py was fixed first (14ecaeed); this suite
covers the four sibling step scripts (doc, security, health, slo), which had
the identical exposure.

The fix: each script's `main()` is now a thin wrapper — `_parse_args`, then
`_main_impl(args)` inside a try/except that catches ANY exception, prints the
traceback (so nothing is silently swallowed), records a `mark_incomplete` +
`verdict=red` on the shared cycle row when a DSN is available, and returns 3.
3 is deliberately outside sweep-run.py's `(0, 1, 2)` completed set.

Run: python3 runbooks/tests/test-sweep-step-crash-veto.py
"""
import importlib.util
import os
import pathlib
import sys

os.environ["_MISE_ACTIVATED"] = "1"          # dodge each script's mise re-exec guard
ROOT = pathlib.Path(__file__).resolve().parents[2]
os.chdir(ROOT)

PASS = FAIL = 0


def check(name, got, want):
    global PASS, FAIL
    if got == want:
        print(f"  PASS  {name}")
        PASS += 1
    else:
        print(f"  FAIL  {name}\n        got {got!r}\n        want {want!r}")
        FAIL += 1


def load(relpath):
    spec = importlib.util.spec_from_file_location(relpath, ROOT / relpath)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


SCRIPTS = [
    "runbooks/doc-check.py",
    "runbooks/security-check.py",
    "runbooks/health-check.py",
    "runbooks/slo-check.py",
]

print("sweep-step crash-veto tests\n")

for rel in SCRIPTS:
    name = pathlib.Path(rel).name
    sys.argv = [name]
    m = load(rel)

    # --- direction 1: an uncaught exception must NOT collide with rc=1 ------
    def boom(args):
        raise RuntimeError("injected crash for crash-veto test")
    m._main_impl = boom
    rc = m.main([])
    check(f"{name}: crash returns rc=3, not 1", rc, 3)
    check(f"{name}: rc=3 is outside sweep-run's completed set (0,1,2)",
          rc in (0, 1, 2), False)

    # --- direction 2: the split must not change behaviour on a clean run ----
    def clean_zero(args):
        return 0
    m._main_impl = clean_zero
    check(f"{name}: clean rc=0 passes through unchanged", m.main([]), 0)

    def clean_one(args):
        return 1
    m._main_impl = clean_one
    check(f"{name}: findings-found rc=1 passes through unchanged (not eaten by the wrapper)",
          m.main([]), 1)

    # --- direction 3: the wrapper does not swallow the traceback ------------
    # A crash must still be visible in the process's own output, not just
    # scored -- an operator staring at a red run needs to see WHY.
    import io
    import contextlib
    def boom_named(args):
        raise ValueError("distinctive marker for stderr capture")
    m._main_impl = boom_named
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        m.main([])
    check(f"{name}: traceback is still printed, not swallowed",
          "distinctive marker for stderr capture" in buf.getvalue(), True)

print(f"\n  {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
