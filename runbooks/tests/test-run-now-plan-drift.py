#!/usr/bin/env python3
"""Regression tests: upstream drift since review blocks a NOW run as NEEDS-DECISION.

F-58f0bbab — coverage.py has computed `plan_drift` for months (a live plan
whose target fell behind the version snapshot), but nothing on the EXECUTION
path read it, so the drift was caught only mid-run by a human reading the plan
body. Live proof on 2026-09-22: nextcloud-mcp-0.187.1 carried a recorded GO
for 0.187.1 while the snapshot's newest tag was 0.195.0 — eight 0.x release
lines past the reviewed target.

Pinned here:
  * drift_by_plan() attributes coverage's plan_drift rows to plan ids (by the
    `plan exists: <id> (…)` reason, falling back to the drift's file stem) and
    returns None — never {} — when coverage produced no report;
  * a drifted plan is refused with a reason that starts NEEDS-DECISION, is
    flagged `needs_decision`, loses its consent, and --operator-go does NOT
    override it;
  * an unmeasurable drift (oracle returns None / raises) refuses too;
  * the oracle is consulted lazily, once per preflight, and never for a plan
    already refused on cheap grounds;
  * a caller that supplies no oracle gets NO gate and the report says so
    (`drift_verified: false`) instead of pretending one ran.

Run: python3 runbooks/tests/test-run-now-plan-drift.py
"""
from __future__ import annotations

import datetime as dt
import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("run_now", REPO / "runbooks/run-now.py")
rn = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rn)

FAILURES: list[str] = []
ERROR_MARKS = ("Traceback", "Exception:", "Error:")
TODAY = dt.date(2026, 9, 22)
OD = {"id": "now", "mode": "attended", "allow_reboot": False, "serial": True,
      "duration_min": 480}
PASS_PREMISES = lambda pid: (True, "fixture")  # noqa: E731


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


def count(population, pred) -> int:
    items = list(population)
    if not items:
        raise AssertionError("count(): EMPTY population — nothing was observed")
    joined = "\n".join(str(x) for x in items)
    if any(m in joined for m in ERROR_MARKS):
        raise AssertionError(f"count(): population carries error text: {joined[:120]!r}")
    return sum(1 for x in items if pred(x))


def plan(pid, **kw):
    base = {"plan_id": pid, "component": pid.rsplit("-", 1)[0], "kind": "image",
            "status": "vetted", "window": None, "risk": "medium", "est_duration_min": 30,
            "needs_reboot": False, "depends_on": [], "conflicts_with": [],
            "touches": {"shared": []}, "target": "0.187.1", "current": "0.184.5",
            "_path": f"runbooks/maintenance/plans/{pid}.md"}
    base.update(kw)
    return base


# the record shape coverage.reconcile()["plan_drift"] carries (see coverage.py
# assign_lane + _drift_note); values are the live 2026-09-22 nextcloud-mcp row
DRIFT_ROW = {
    "component": "nextcloud-mcp", "kind": "image", "current": "0.184.5",
    "target": "0.195.0", "lane": "PLAN",
    "reason": "plan exists: nextcloud-mcp-0.187.1 (awaiting-go)",
    "drift": ("nextcloud-mcp-0.187.1.md: plan targets 0.187.1, but 0.195.0 is now "
              "published — CHANNEL UNRESOLVED: confirm 0.195.0 is on the stable channel "
              "before re-targeting"),
}
COVERAGE = {"plan_drift": [DRIFT_ROW], "counts": {}, "lanes": {}, "needs_plan": [],
            "cracks": [], "covered": True}


def pf(ids, plans, drift_check, operator_go="mu at the console"):
    return rn.preflight(ids, plans, [], OD, None, operator_go, TODAY, PASS_PREMISES,
                        drift_check=drift_check)


def row(report, pid):
    return next((r for r in report["plans"] if r["plan_id"] == pid), {})


def scenarios() -> dict:
    out = {}
    # --- attribution ---------------------------------------------------------
    m = rn.drift_by_plan(COVERAGE)
    out["drift_by_plan keys the row by the plan id in `plan exists: …`"] = (
        list(m) == ["nextcloud-mcp-0.187.1"] and m["nextcloud-mcp-0.187.1"][0] is DRIFT_ROW)
    nolead = dict(DRIFT_ROW, reason="something else")
    m2 = rn.drift_by_plan({"plan_drift": [nolead]})
    out["drift_by_plan falls back to the drift text's file stem"] = list(m2) == ["nextcloud-mcp-0.187.1"]
    out["drift_by_plan: coverage error => None, never {}"] = (
        rn.drift_by_plan({"error": "version-check-current.md missing", "cracks": []}) is None)
    out["drift_by_plan: not a report => None"] = rn.drift_by_plan(None) is None
    out["drift_by_plan: no drift rows => {} (measured clean)"] = rn.drift_by_plan({"plan_drift": []}) == {}

    # --- refusal text --------------------------------------------------------
    why = rn.drift_refusal(plan("nextcloud-mcp-0.187.1"), m)
    out["drifted plan => NEEDS-DECISION naming reviewed, live and newest"] = (
        why is not None and why.startswith("NEEDS-DECISION")
        and "0.187.1" in why and "0.184.5" in why and "0.195.0" in why)
    out["the refusal says --operator-go does not override it"] = (
        why is not None and "operator-go does not override" in why)
    out["undrifted plan => no refusal"] = rn.drift_refusal(plan("other-1.0.0"), m) is None
    unm = rn.drift_refusal(plan("other-1.0.0"), None)
    out["unmeasurable drift (None) => NEEDS-DECISION for every plan"] = (
        unm is not None and unm.startswith("NEEDS-DECISION") and "could NOT be measured" in unm)

    # --- preflight wiring ----------------------------------------------------
    r = pf(["nextcloud-mcp-0.187.1"], [plan("nextcloud-mcp-0.187.1")], lambda: m)
    rw = row(r, "nextcloud-mcp-0.187.1")
    out["preflight: drifted plan is refused even with --operator-go"] = rw.get("ok") is False
    out["preflight: the refusal is flagged needs_decision and consent is dropped"] = (
        rw.get("needs_decision") is True and rw.get("consent_source") is None)
    out["preflight: the first reason starts NEEDS-DECISION"] = (
        bool(rw.get("reasons")) and rw["reasons"][0].startswith("NEEDS-DECISION"))
    out["preflight: report lists the plan under needs_decision and drift_verified is true"] = (
        r["needs_decision"] == ["nextcloud-mcp-0.187.1"] and r["drift_verified"] is True)
    out["preflight: nothing runnable => exit 2"] = rn.exit_code(r) == 2

    r = pf(["other-1.0.0"], [plan("other-1.0.0")], lambda: m)
    out["preflight: an undrifted plan passes with the gate active"] = (
        row(r, "other-1.0.0").get("ok") is True and r["drift_verified"] is True
        and r["needs_decision"] == [])

    r = pf(["other-1.0.0"], [plan("other-1.0.0")], lambda: None)
    out["preflight: oracle returning None refuses NEEDS-DECISION, drift_verified false"] = (
        row(r, "other-1.0.0").get("ok") is False and row(r, "other-1.0.0").get("needs_decision")
        and r["drift_verified"] is False)

    def boom():
        raise RuntimeError("coverage exploded")
    r = pf(["other-1.0.0"], [plan("other-1.0.0")], boom)
    out["preflight: a raising oracle fails closed, not open"] = (
        row(r, "other-1.0.0").get("ok") is False and r["drift_verified"] is False)

    r = rn.preflight(["other-1.0.0"], [plan("other-1.0.0")], [], OD, None, "mu", TODAY,
                     PASS_PREMISES)
    out["preflight: no oracle supplied => no gate, and the report SAYS so"] = (
        row(r, "other-1.0.0").get("ok") is True and r["drift_verified"] is False)

    calls = []

    def counting():
        calls.append(1)
        return m
    pf(["other-1.0.0", "other-2.0.0"], [plan("other-1.0.0"), plan("other-2.0.0")], counting)
    out["preflight: the oracle is consulted ONCE for a multi-plan run"] = len(calls) == 1
    calls.clear()
    pf(["d"], [plan("d", status="draft")], counting)
    out["preflight: the oracle is NOT consulted for a plan refused on cheap grounds"] = calls == []

    # --- human rendering -----------------------------------------------------
    r = pf(["nextcloud-mcp-0.187.1"], [plan("nextcloud-mcp-0.187.1")], lambda: m)
    lines = rn._human(r).splitlines()
    out["_human renders the row as NEEDS-DECISION, not REFUSED"] = (
        count(lines, lambda l: l.strip().startswith("NEEDS-DECISION")) == 1
        and count(lines, lambda l: "REFUSED" in l) == 0)
    r = pf(["other-1.0.0"], [plan("other-1.0.0")], lambda: None)
    lines = rn._human(r).splitlines()
    out["_human warns when drift could not be verified"] = (
        count(lines, lambda l: "NOT VERIFIED" in l) == 1)
    return out


MUST_FAIL = [
    "preflight: drifted plan is refused even with --operator-go",
    "preflight: the refusal is flagged needs_decision and consent is dropped",
    "preflight: the first reason starts NEEDS-DECISION",
    "preflight: report lists the plan under needs_decision and drift_verified is true",
    "preflight: oracle returning None refuses NEEDS-DECISION, drift_verified false",
    "_human renders the row as NEEDS-DECISION, not REFUSED",
]


def main() -> int:
    print("test-run-now-plan-drift")
    for name, ok in scenarios().items():
        check(name, ok)

    print("  -- commissioning straw: drift never refuses (the pre-fix preflight)")
    saved = rn.drift_refusal
    rn.drift_refusal = lambda plan, drift_map: None
    try:
        under = scenarios()
    finally:
        rn.drift_refusal = saved
    failed = [n for n in MUST_FAIL if under.get(n) is False]
    check("straw: every drift-gate check FAILS with the refusal reverted",
          len(failed) == len(MUST_FAIL), f"still passing: {sorted(set(MUST_FAIL) - set(failed))}")
    check("straw: the undrifted-plan control still passes under the straw",
          under.get("preflight: an undrifted plan passes with the gate active") is True)

    print()
    if FAILURES:
        print(f"FAILED ({len(FAILURES)}): {', '.join(FAILURES)}")
        return 1
    print("all run-now-plan-drift tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
