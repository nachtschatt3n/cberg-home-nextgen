"""Regression tests for the premises gate in window-scheduler.py's assign().

WHY THIS GATE EXISTS
Twice on 2026-09-06 a plan was caught MID-EXECUTION as a data-loss trap, both
times by a human reading the body at the last moment. The scheduler is the
last automated step before a plan lands in a window, and until this gate it
placed plans on class + status + depends_on alone — none of which say whether
the plan's assumptions are still true days after it was written.

The gate refuses to assign a plan unless `plan-premises.py <id>
--require-premises --json` reports a clean pass. These tests pin every
refusal branch SEPARATELY, because the gate's value is in failing CLOSED and
each "silence read as consent" hole is a distinct bug:

  * any failing premise                       -> refused
  * NO premises declared                      -> refused (unverified != pass)
  * non-zero exit without a passing report    -> refused
  * unparseable / empty output                -> refused
  * no report for THIS plan id (plan-premises.py exits 0 with `plans: []`
    for an unknown id — the most dangerous shape)  -> refused
  * checker raises / times out                -> refused
  * a clean pass                              -> assigned (the gate is not inert)

The check is injectable (`assign(..., premises_check=...)`), so nothing here
shells out or touches the cluster. `premises_verdict()` is pure and is tested
directly on fake plan-premises.py output; the subprocess wrapper's only job is
to feed it (returncode, stdout).

Run:  python3 runbooks/tests/test-scheduler-premises-gate.py
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("ws", REPO / "runbooks/window-scheduler.py")
ws = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ws)

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


CFG = {"windows": [
    {"id": "nightly", "day": "daily", "duration_min": 90,
     "capacity_risk": 6, "allow_reboot": False, "mode": "unattended"},
    {"id": "sat-attended", "day": "saturday", "duration_min": 90,
     "capacity_risk": 6, "allow_reboot": False, "mode": "attended"},
]}
MONDAY = dt.date(2026, 9, 7)


def plan(pid, **kw):
    base = {"plan_id": pid, "kind": "image", "status": "vetted", "window": None,
            "risk": "medium", "est_duration_min": 25, "depends_on": [],
            "conflicts_with": [], "needs_reboot": False}
    base.update(kw)
    return base


def run(plans, premises_check, classes=None):
    classes = classes or {p["plan_id"]: "AUTO-NIGHT" for p in plans}
    return ws.assign(plans, CFG, classes, {}, MONDAY, premises_check=premises_check)


def reason_for(skipped, pid):
    return next((s["reason"] for s in skipped if s["plan_id"] == pid), "")


# Fake plan-premises.py --json output, shaped exactly like check_plan()/main().
def report(pid, results, declared=None):
    declared = len(results) if declared is None else declared
    passed = bool(declared) and all(r["passed"] for r in results)
    return {"plan_id": pid, "status": "vetted", "window": None,
            "declared": declared, "results": results, "passed": passed}


def stdout_for(reports, ok):
    return json.dumps({"plans": reports, "ok": ok})


PASSING = [{"id": "image-is-current", "passed": True, "ran": True,
            "detail": "got 'x:1.2.3', want exactly 'x:1.2.3'"}]
FAILING = [{"id": "image-is-current", "passed": False, "ran": True,
            "detail": "got 'x:1.2.4', want exactly 'x:1.2.3'"}]


def main() -> int:
    print("scheduler premises gate — premises_verdict (pure):")
    v = ws.premises_verdict

    ok, why = v(0, stdout_for([report("p", PASSING)], True), "p")
    check("clean pass is accepted", ok, why)

    ok, why = v(1, stdout_for([report("p", FAILING)], False), "p")
    check("a failing premise refuses and names it",
          not ok and "FAILED" in why and "image-is-current" in why, why)

    # Mixed: one passing, one failing — must still refuse, and name only the failure.
    mixed = PASSING + [{"id": "pvc-bound", "passed": False, "ran": True,
                        "detail": "command produced NO output"}]
    ok, why = v(1, stdout_for([report("p", mixed)], False), "p")
    check("one failing premise among passing ones refuses",
          not ok and "pvc-bound" in why and "image-is-current" not in why, why)

    ok, why = v(1, stdout_for([report("p", [], declared=0)], False), "p")
    check("no premises declared refuses (unverified is not passing)",
          not ok and "undeclared" in why, why)

    # plan-premises.py filters to the given ids; an unknown id yields no report
    # and exit 0 with ok:true. That must NOT pass.
    ok, why = v(0, stdout_for([], True), "ghost")
    check("exit 0 with no report for this plan id refuses",
          not ok and "no report" in why, why)

    ok, why = v(0, stdout_for([report("other", PASSING)], True), "p")
    check("a passing report for a DIFFERENT plan does not pass this one",
          not ok and "no report" in why, why)

    ok, why = v(1, "", "p")
    check("empty output refuses", not ok and "parseable" in why, why)

    ok, why = v(0, "Traceback (most recent call last): ...", "p")
    check("non-JSON output refuses even on exit 0", not ok and "parseable" in why, why)

    # Inconsistent: report claims pass but the process exited non-zero.
    ok, why = v(1, stdout_for([report("p", PASSING)], True), "p")
    check("non-zero exit refuses even if the report looks clean",
          not ok and "exited 1" in why, why)

    # Inconsistent the other way: exit 0 but the report's own verdict is false.
    r = report("p", PASSING)
    r["passed"] = False
    ok, why = v(0, stdout_for([r], True), "p")
    check("report passed=false refuses even on exit 0", not ok, why)

    print("\nscheduler premises gate — assign() integration:")

    a, s = run([plan("good")], lambda pid: (True, "1 premise(s) hold"))
    check("a plan whose premises hold is assigned (gate is not inert)",
          len(a) == 1 and not s, f"{a} / {s}")

    a, s = run([plan("stale")], lambda pid: (False, "premises FAILED: image-is-current (drifted)"))
    check("a plan with a failing premise is refused with a loud reason",
          not a and reason_for(s, "stale").startswith("premises not verified")
          and "image-is-current" in reason_for(s, "stale"), reason_for(s, "stale"))

    a, s = run([plan("bare")], lambda pid: (False, "premises undeclared — an unverified plan is not a passing one"))
    check("a plan declaring no premises is refused",
          not a and "undeclared" in reason_for(s, "bare"), reason_for(s, "bare"))

    def boom(pid):
        raise RuntimeError("kubectl unreachable")
    a, s = run([plan("crash")], boom)
    check("a checker that raises fails CLOSED (refused, not skipped-as-ok)",
          not a and "RuntimeError" in reason_for(s, "crash")
          and "fail closed" in reason_for(s, "crash"), reason_for(s, "crash"))

    import subprocess

    def slow(pid):
        raise subprocess.TimeoutExpired(cmd="plan-premises.py", timeout=300)
    a, s = run([plan("slow")], slow)
    check("a checker that times out fails CLOSED",
          not a and "TimeoutExpired" in reason_for(s, "slow"), reason_for(s, "slow"))

    # The checker is asked by plan_id and only for plans that survived the
    # cheap refusals — a draft must be refused on status, not by shelling out.
    asked = []

    def spy(pid):
        asked.append(pid)
        return True, "ok"
    a, s = run([plan("drafty", status="draft"), plan("live")], spy)
    check("the check is keyed by plan_id and skipped for plans already refused",
          asked == ["live"] and len(a) == 1 and "draft" in reason_for(s, "drafty"),
          f"asked={asked} a={a} s={s}")

    # Discrimination: same plan set, only the verdict differs.
    a_ok, _ = run([plan("x1"), plan("x2")], lambda pid: (True, "ok"))
    a_no, s_no = run([plan("x1"), plan("x2")], lambda pid: (False, "premises FAILED: z"))
    check("gate discriminates — identical plans, verdict alone decides",
          len(a_ok) == 2 and not a_no and len(s_no) == 2, f"{a_ok} / {a_no}")

    # The default checker must be the subprocess implementation, not a stub —
    # a scheduler whose default silently passes would be fail-open in prod.
    import inspect
    default = inspect.signature(ws.assign).parameters["premises_check"].default
    check("assign() defaults to the subprocess checker (no fail-open default)",
          default is ws.check_premises_subprocess, repr(default))

    print()
    if FAILURES:
        print(f"FAILED ({len(FAILURES)}): {', '.join(FAILURES)}")
        return 1
    print("all scheduler-premises-gate tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
