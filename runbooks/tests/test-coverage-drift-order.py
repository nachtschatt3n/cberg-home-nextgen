#!/usr/bin/env python3
"""Regression test: plan drift is a NEWER version than the plan target, compared
numerically — an OLDER tag is never drift (2026-09-26).

THE DEFECT. `_plan_delivers()` flagged drift for ANY same-release-line version
that differed from the plan target, with no ordering check. Live: the
nextcloud-mcp-0.187.1 plan targets 0.195.4 (reviewed; digest == `latest`;
GitHub "Latest") while the version snapshot, generated before 0.195.4 shipped,
names 0.195.3. run-now.py's preflight then refused the plan:

  NEEDS-DECISION: upstream drift since review: plan targets 0.195.4, but
  0.195.3 is now published — CHANNEL UNRESOLVED

THE DETECTOR MUST NOT GO BLIND (feedback_fp_fix_can_blind_detector):
  * a NEWER stable tag on the same line is still drift;
  * a newer tag with NO resolvable channel is still drift, labelled
    CHANNEL UNRESOLVED, and still a NEEDS-DECISION in run-now;
  * a positively-resolved channel head newer than the plan is still drift even
    when the raw snapshot tag is older;
  * the order is numeric, not lexical (0.195.10 > 0.195.9).

Run:  python3 runbooks/tests/test-coverage-drift-order.py
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cov = _load("cov", "runbooks/coverage.py")
rn = _load("run_now", "runbooks/run-now.py")

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


def item(comp, target, kind="image", current="0.184.5"):
    return {"component": comp, "kind": kind, "current": current,
            "target": target, "type": "minor"}


def plan(comp, target, kind="image", plan_id=None):
    return {"plan_id": plan_id or f"{comp}-plan", "file": f"{comp}.md",
            "keys": {comp}, "also_keys": set(), "status": "awaiting-go",
            "kind": kind, "current": "", "target": target}


def refusal_for(it, pl, heads=None):
    """End to end through the run-now gate: coverage's match_plan -> a
    synthesized reconcile() report -> drift_by_plan -> drift_refusal."""
    matched, drift = cov.match_plan(it, {it["component"]}, [pl], heads)
    report = {"plan_drift": []}
    if matched is not None and drift:
        report["plan_drift"].append({
            **it, "drift": drift,
            "reason": f"plan exists: {pl['plan_id']} ({pl['status']})"})
    return matched, drift, rn.drift_refusal(pl, rn.drift_by_plan(report))


MCP = "nextcloud-mcp"
MCP_PLAN = plan(MCP, "0.195.4", plan_id="nextcloud-mcp-0.187.1")

print("older-than-target tag published later -> NOT drift")
m, d, r = refusal_for(item(MCP, "0.195.3"), MCP_PLAN)
check("live case: plan 0.195.4 vs snapshot 0.195.3 is covered", m is MCP_PLAN, repr(m))
check("live case: no drift note", d is None, repr(d))
check("live case: run-now does not refuse", r is None, repr(r))

m, d, r = refusal_for(item(MCP, "0.195.9"), plan(MCP, "0.195.10"))
check("numeric not lexical: 0.195.9 is older than 0.195.10", d is None and r is None,
      repr(d))

print("newer stable -> drift")
heads = {(MCP, "image"): ("0.195.5", "`latest` tag label, digest-confirmed")}
m, d, r = refusal_for(item(MCP, "0.195.5"), MCP_PLAN, heads)
check("newer resolved-stable tag is drift", bool(d) and "0.195.5" in d, repr(d))
check("newer resolved-stable tag -> NEEDS-DECISION",
      bool(r) and r.startswith("NEEDS-DECISION"), repr(r))

m, d, r = refusal_for(item(MCP, "0.195.10"), plan(MCP, "0.195.9"), {})
check("numeric not lexical: 0.195.10 is newer than 0.195.9 -> drift",
      bool(d) and bool(r), repr(d))

print("channel head newer than plan, raw snapshot tag older -> still drift")
heads = {(MCP, "image"): ("0.195.6", "`latest` tag label, digest-confirmed")}
m, d, r = refusal_for(item(MCP, "0.195.3"), MCP_PLAN, heads)
check("resolved head 0.195.6 > plan 0.195.4 is still drift",
      bool(d) and "0.195.6" in d and bool(r), repr(d))

print("unresolved channel -> still NEEDS-DECISION")
m, d, r = refusal_for(item(MCP, "0.195.5"), MCP_PLAN, {})
check("newer tag, no channel oracle -> CHANNEL UNRESOLVED",
      bool(d) and "CHANNEL UNRESOLVED" in d, repr(d))
check("newer tag, no channel oracle -> run-now NEEDS-DECISION",
      bool(r) and r.startswith("NEEDS-DECISION") and "CHANNEL UNRESOLVED" in r, repr(r))
m, d, r = refusal_for(item("kube-prometheus-stack", "91.4.1", kind="chart",
                           current="90.0.0"),
                      plan("kube-prometheus-stack", "91.4.0", kind="chart"), {})
check("chart (never has an oracle) newer tag -> NEEDS-DECISION",
      bool(r) and "CHANNEL UNRESOLVED" in r, repr(r))
check("unmeasurable drift (no coverage report) still fails closed",
      str(rn.drift_refusal(MCP_PLAN, rn.drift_by_plan({"error": "x"}))
          ).startswith("NEEDS-DECISION"))

print("exact target -> no drift (unchanged)")
m, d, r = refusal_for(item(MCP, "0.195.4"), MCP_PLAN)
check("exact match covered, no drift", m is MCP_PLAN and d is None and r is None)

if FAILURES:
    print(f"\nFAIL: {len(FAILURES)} check(s) failed")
    sys.exit(1)
print("\nOK: all checks passed")
