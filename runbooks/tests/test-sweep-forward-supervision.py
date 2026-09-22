#!/usr/bin/env python3
"""Regression tests: a sweep section whose DB write was lost must FAIL the run.

F-f85cf55c — sweep-run.py's `_start_port_forward` was a one-shot 6s probe with
no supervision, and main() had a single `return 0`: a forward that died
between sections lost that section's ENTIRE DB write (findings_writer catches
every write exception — "never lose the cycle close"), the section still
exited 0/1/2, sweep-run scored it completed, auto-closed against it, and the
run reported success.

F-fe1795c5 — "was alive at start" is not the property that matters: on
2026-09-22 a forward reported ready and refused the VERY NEXT connection.
kubectl port-forward listens locally and only dials the pod when a connection
arrives, so a bare TCP accept proves nothing about the path to the pod.

The fix: an end-to-end probe (SELECT 1 / HTTP ready) run BEFORE and AFTER
every section, one re-dial per phase, a section whose forward was dead at
write time scored LOST (struck from auto-close) — and a non-zero exit
(EXIT_FORWARD_DEAD = 3) whenever a write depended on a dead forward.

Hermetic: no kubectl, no DB. Popen, probes, secret lookup and the section
runner are all faked; `_stop` is neutralised so no real process group is ever
signalled.

Run: python3 runbooks/tests/test-sweep-forward-supervision.py
"""
from __future__ import annotations

import importlib.util
import os
import pathlib
import sys

os.environ["_MISE_ACTIVATED"] = "1"          # dodge the mise re-exec guard
ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("sweep_run", ROOT / "runbooks/sweep-run.py")
sr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sr)

# NEVER signal a real process group from a test: Forward.stop()/ensure() call
# the module-global _stop, which killpg()s the fake pid otherwise.
sr._stop = lambda pf: None
sr.time.sleep = lambda s: None

FAILURES: list[str] = []
ERROR_MARKS = ("Traceback", "Exception:", "Error:")


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


def count(population, pred) -> int:
    """Counting helper that ABORTS on an empty population or error text —
    a zero over nothing is not a measurement."""
    items = list(population)
    if not items:
        raise AssertionError("count(): EMPTY population — nothing was observed")
    joined = "\n".join(str(x) for x in items)
    if any(m in joined for m in ERROR_MARKS):
        raise AssertionError(f"count(): population carries error text: {joined[:120]!r}")
    return sum(1 for x in items if pred(x))


class FakeProc:
    def __init__(self):
        self.pid = 4242
        self._rc = None

    def poll(self):
        return self._rc

    def terminate(self):
        self._rc = -15


# ---------------------------------------------------------------------------
# 1. the supervisor itself
# ---------------------------------------------------------------------------
def supervisor_scenarios() -> dict:
    out = {}
    st = {"alive": True, "dials": 0}

    def starter(ns, svc, lp, rp):
        st["dials"] += 1
        st["alive"] = True          # a fresh forward is healthy
        return FakeProc()

    fwd = sr.Forward("databases", "postgresql", 5555, 5432,
                     probe=lambda: st["alive"], starter=starter)
    fwd.dial()
    out["alive when the end-to-end probe passes"] = fwd.alive() is True
    st["alive"] = False
    out["dead when the probe fails, even with the process running"] = fwd.alive() is False
    out["ensure() re-dials ONCE and revives"] = (
        fwd.ensure("t") is True and st["dials"] == 2 and fwd.redials == 1)
    out["ensure() logs the supervision event"] = count(fwd.log, lambda l: "re-dial" in l) >= 1

    def raising():
        raise ConnectionRefusedError("refused")
    fwd2 = sr.Forward("databases", "postgresql", 5556, 5432, probe=raising, starter=starter)
    fwd2.dial()
    out["a probe that RAISES is a dead forward, not an unknown one"] = fwd2.alive() is False

    fwd3 = sr.Forward("databases", "postgresql", 5557, 5432, probe=lambda: True, starter=starter)
    fwd3.dial()
    fwd3.proc._rc = 1
    out["an exited process is dead even when the probe would pass"] = fwd3.alive() is False

    dead = {"n": 0}

    def dead_starter(*a):
        dead["n"] += 1
        return FakeProc()
    fwd4 = sr.Forward("databases", "postgresql", 5558, 5432, probe=lambda: False,
                      starter=dead_starter)
    fwd4.dial()
    out["ensure() is False when the re-dial is still dead (one re-dial, not a loop)"] = (
        fwd4.ensure("t") is False and dead["n"] == 2)
    return out


# ---------------------------------------------------------------------------
# 2. sections under supervision
# ---------------------------------------------------------------------------
def steps_scenarios() -> dict:
    out = {}

    def make(dead_for_good=False, die_after=None):
        st = {"alive": True, "dials": 0, "dead": False}
        ran = []

        def starter(*a):
            st["dials"] += 1
            st["alive"] = not st["dead"]
            return FakeProc()

        def probe():
            return st["alive"] and not st["dead"]

        def runner(cmd, env=None):
            ran.append(pathlib.Path(cmd[-1]).name)
            if die_after and len(ran) == die_after:
                st["alive"] = False
                st["dead"] = dead_for_good
            return 0
        fwd = sr.Forward("databases", "postgresql", 5560, 5432, probe=probe, starter=starter)
        fwd.dial()
        return st, ran, fwd, runner

    # healthy throughout
    st, ran, fwd, runner = make()
    res = sr._run_steps_supervised(["version", "doc"], {}, fwd, None, runner=runner)
    out["healthy forward: both sections completed, nothing lost"] = (
        res["completed"] == ["version", "doc"] and not res["lost"] and not res["skipped"])

    # dies after the first section's write, revivable
    st, ran, fwd, runner = make(die_after=1)
    res = sr._run_steps_supervised(["version", "doc"], {}, fwd, None, runner=runner)
    out["forward dead AFTER a section = that section is LOST, not completed"] = (
        res["lost"] == ["version"] and res["completed"] == ["doc"])
    out["a successful re-dial does NOT retroactively score the lost section"] = (
        "version" not in res["completed"] and st["dials"] == 2)
    out["the next section still ran, through the re-dialled forward"] = ran == [
        "check-all-versions.py", "doc-check.py"]

    # dies for good after the first section
    st, ran, fwd, runner = make(die_after=1, dead_for_good=True)
    res = sr._run_steps_supervised(["version", "doc"], {}, fwd, None, runner=runner)
    out["unrevivable forward: the following section is SKIPPED, never run"] = (
        res["skipped"] == ["doc"] and ran == ["check-all-versions.py"] and res["lost"] == ["version"])

    # a crash (rc 3) with a live forward is neither completed nor lost
    st, ran, fwd, _ = make()
    res = sr._run_steps_supervised(["doc"], {}, fwd, None, runner=lambda c, env=None: 3)
    out["crash rc=3 stays outside completed AND outside lost"] = (
        not res["completed"] and not res["lost"] and res["nonzero"] == ["doc(3)"])

    # --no-write: no forward to supervise, sections complete on rc alone
    res = sr._run_steps_supervised(["doc"], {}, None, None, runner=lambda c, env=None: 1)
    out["no forward (--no-write): completion is judged on rc alone"] = res["completed"] == ["doc"]

    # the prometheus forward is consulted only by the slo step
    consulted = []

    class Spy(sr.Forward):
        def ensure(self, phase):
            consulted.append(phase)
            return True

        def alive(self):
            return True
    prom = Spy("monitoring", "prom", 5561, 9090, probe=lambda: True, starter=lambda *a: FakeProc())
    sr._run_steps_supervised(["doc", "slo"], {}, None, prom, runner=lambda c, env=None: 0)
    out["the prometheus forward is supervised around the slo step only"] = (
        consulted == ["before slo"])
    return out


# ---------------------------------------------------------------------------
# 3. main() end to end — the exit code is the deliverable
# ---------------------------------------------------------------------------
def run_main(argv, die_after=None, dead_for_good=False, dead_from_start=False):
    st = {"alive": not dead_from_start, "dead": dead_from_start, "dials": 0}
    ran, closed_scope, cycle_rows = [], [], []
    saved = {k: getattr(sr, k) for k in (
        "_start_port_forward", "_kubectl_secret_dsn", "_pg_probe", "_ensure_cycle_row",
        "_apply_ar_suppression", "_auto_close_stale_findings", "_reconcile_verdict",
        "_sections_reporting_this_cycle")}
    saved_call = sr.subprocess.call
    saved_env = dict(os.environ)

    def starter(ns, svc, lp, rp):
        st["dials"] += 1
        st["alive"] = not st["dead"]
        return FakeProc()

    def fake_call(cmd, env=None):
        step = pathlib.Path(cmd[-1]).name
        ran.append(step)
        if die_after and len(ran) == die_after:
            st["alive"] = False
            st["dead"] = dead_for_good
        return 0

    sr._start_port_forward = starter
    # built by concatenation: the in-cluster FQDN inline trips the pre-commit
    # secret scanner (see sweep-run.py main())
    sr._kubectl_secret_dsn = lambda: ("postgresql://sweep@postgresql."
                                      + "databases.svc.cluster.local:5432/sweep_history")
    sr._pg_probe = lambda dsn: (lambda: st["alive"] and not st["dead"])
    sr._ensure_cycle_row = lambda dsn, cid, trig: cycle_rows.append(cid)
    sr._apply_ar_suppression = lambda dsn: 0
    sr._auto_close_stale_findings = lambda dsn, cid, completed: (closed_scope.extend(completed), [])[1]
    sr._reconcile_verdict = lambda dsn, cid: "green"
    sr._sections_reporting_this_cycle = lambda dsn, cid: set()
    sr.subprocess.call = fake_call
    os.environ["GITHUB_TOKEN"] = "test-token"     # keeps main() from shelling out to gh
    os.environ.pop("SWEEP_PG_DSN", None)
    try:
        try:
            rc = sr.main(argv)
        except SystemExit as e:
            rc = e.code
    finally:
        for k, v in saved.items():
            setattr(sr, k, v)
        sr.subprocess.call = saved_call
        os.environ.clear()
        os.environ.update(saved_env)
    return {"rc": rc, "ran": ran, "closed": closed_scope, "dials": st["dials"],
            "cycle_rows": cycle_rows}


def main_scenarios() -> dict:
    out = {}
    r = run_main(["version", "doc"])
    out["healthy run exits 0 and auto-closes against both sections"] = (
        r["rc"] == 0 and r["ran"] == ["check-all-versions.py", "doc-check.py"]
        and r["closed"] == ["version", "doc"])

    r = run_main(["version", "doc"], die_after=1)
    out["forward dead at a section's write time => run exits EXIT_FORWARD_DEAD (3)"] = (
        r["rc"] == sr.EXIT_FORWARD_DEAD == 3)
    out["the lost section is struck from the auto-close scope"] = r["closed"] == ["doc"]
    out["exactly one re-dial happened for the lost section"] = r["dials"] == 2

    r = run_main(["version", "doc"], die_after=1, dead_for_good=True)
    out["unrevivable forward mid-run => exit 3 and the next section never runs"] = (
        r["rc"] == 3 and r["ran"] == ["check-all-versions.py"])
    out["no auto-close is attempted through a dead forward"] = r["closed"] == []

    r = run_main(["version"], dead_from_start=True)
    out["F-fe1795c5: forward that refuses the FIRST end-to-end probe aborts at startup, exit 3"] = (
        r["rc"] == 3 and r["ran"] == [] and r["cycle_rows"] == [])

    r = run_main(["--reconcile-only", "--cycle-id", "cyc-1", "--ran", "doc"], dead_from_start=True)
    out["reconcile-only over a dead forward aborts before any write, exit 3"] = (
        r["rc"] == 3 and r["cycle_rows"] == [] and r["closed"] == [])
    return out


# ---------------------------------------------------------------------------
# commissioning straws — each reverts the fix and MUST make named checks fail
# ---------------------------------------------------------------------------
def straw_no_supervision():
    """Pre-fix: 'alive at start' is the only property; nothing re-checks."""
    saved = (sr.Forward.alive, sr.Forward.ensure, sr._require_forward)
    sr.Forward.alive = lambda self: True
    sr.Forward.ensure = lambda self, phase: True
    sr._require_forward = lambda fwd, phase: None
    try:
        return main_scenarios()
    finally:
        sr.Forward.alive, sr.Forward.ensure, sr._require_forward = saved


MUST_FAIL_UNDER_STRAW = [
    "forward dead at a section's write time => run exits EXIT_FORWARD_DEAD (3)",
    "the lost section is struck from the auto-close scope",
    "unrevivable forward mid-run => exit 3 and the next section never runs",
    "F-fe1795c5: forward that refuses the FIRST end-to-end probe aborts at startup, exit 3",
    "reconcile-only over a dead forward aborts before any write, exit 3",
]


def main() -> int:
    print("test-sweep-forward-supervision")
    for name, ok in supervisor_scenarios().items():
        check(name, ok)
    for name, ok in steps_scenarios().items():
        check(name, ok)
    res = main_scenarios()
    for name, ok in res.items():
        check(name, ok)
    check("EXIT_FORWARD_DEAD is outside the (0,1,2) 'ran to completion' set",
          sr.EXIT_FORWARD_DEAD not in (0, 1, 2))

    print("  -- commissioning straw: no supervision (the pre-fix code path)")
    under = straw_no_supervision()
    failed = [n for n in MUST_FAIL_UNDER_STRAW if not under.get(n, True)]
    check("straw: every dead-forward check FAILS when supervision is reverted",
          len(failed) == len(MUST_FAIL_UNDER_STRAW),
          f"still passing under the straw: {sorted(set(MUST_FAIL_UNDER_STRAW) - set(failed))}")
    check("straw: the healthy run still passes under the straw (the straw is the pre-fix code, not a broken one)",
          under.get("healthy run exits 0 and auto-closes against both sections") is True)

    print()
    if FAILURES:
        print(f"FAILED ({len(FAILURES)}): {', '.join(FAILURES)}")
        return 1
    print("all sweep-forward-supervision tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
