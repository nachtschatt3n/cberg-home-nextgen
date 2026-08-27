"""Regression tests for runbooks/openclaw-sync.py (P4.1.1).

The script exists because three OpenClaw ingests lived only as prompt text and
could be silently skipped. These tests pin the two properties that make it
safe to run every sweep:

1. PAYLOAD SHAPE — issues carry the home-operation contract fields (key /
   kind / source / action / title), go/no-go issues really carry a decision
   action (the documented `kind` defaulting trap turns an action-less
   go_no_go into a passive ack nobody is asked to decide), and each subject
   uses its OWN source. Source isolation is load-bearing: the old prompt
   contract put DECIDE findings under source "maintenance", where rule 4d's
   plan-key reconcile would auto-close them one sweep later.

2. ABSENT INPUT ≠ EMPTY SET — a subject whose input file is missing is
   SKIPPED, including its reconcile. Reconciling a source against an empty
   set that only reflects a missing input would close every open issue of
   that source. A coverage gap is not a fix.

Run:  python3 runbooks/tests/test-openclaw-sync-payload.py
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "runbooks/openclaw-sync.py"

spec = importlib.util.spec_from_file_location("ocs", SCRIPT)
ocs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ocs)

FAILURES: list[str] = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


PLAN_JSON = {
    "awaiting_go": [{"plan_id": "talos-1.99.0", "plan": "runbooks/maintenance/plans/talos-1.99.0.md",
                     "component": "Talos Linux", "target": "v1.99.0",
                     "window": "sun-attended:2027-01-03"}],
    "open_issue_keys": ["talos-1.99.0", "longhorn-9.9.9-engine"],
}
TRIAGE_JSON = {
    "results": [
        {"finding_id": "F-aaaa1111", "lane": "DECIDE", "rule": "eol-component",
         "title": "synthetic-svc is end of life", "reason": "EOL glob matched"},
        {"finding_id": "F-bbbb2222", "lane": "PLAN", "rule": "default",
         "title": "synthetic other", "reason": "default"},
    ],
}
COVERAGE_JSON = {
    "lanes": {"REBUILD": [{"component": "synthetic-tool", "namespace": "media",
                           "current": "1.0.0", "target": "1.2.0"}],
              "AUTO": [], "PLAN": [], "HELD": [], "CRACK": []},
}


def run_dry(*flags) -> tuple[int, dict]:
    p = subprocess.run([sys.executable, str(SCRIPT), "--dry-run", *flags],
                       capture_output=True, text=True, timeout=60)
    try:
        return p.returncode, json.loads(p.stdout)
    except json.JSONDecodeError:
        return p.returncode, {"_stdout": p.stdout, "_stderr": p.stderr}


def main() -> int:
    print("test-openclaw-sync-payload")

    # ---- unit level: builders --------------------------------------------
    issues, open_keys = ocs.plan_issues(PLAN_JSON)
    check("plan issue keyed on plan_id",
          len(issues) == 1 and issues[0]["key"] == "talos-1.99.0", issues)
    check("plan issue is a decision (kind go_no_go WITH approve action)",
          issues[0]["kind"] == "go_no_go" and "approve" in issues[0]["action"],
          issues[0])
    check("plan issue source is 'maintenance'",
          issues[0]["source"] == "maintenance", issues[0])
    check("plan reconcile set = EVERY non-terminal plan, not just awaiting-go",
          open_keys == ["talos-1.99.0", "longhorn-9.9.9-engine"], open_keys)

    issues, open_keys = ocs.decide_issues(TRIAGE_JSON)
    check("only DECIDE-lane findings become issues",
          len(issues) == 1 and issues[0]["key"] == "F-aaaa1111", issues)
    check("DECIDE issue is a decision with its own source 'triage' "
          "(NOT 'maintenance' — 4d's plan-key reconcile would close it)",
          issues[0]["source"] == "triage" and "approve" in issues[0]["action"],
          issues[0])

    issues, open_keys = ocs.rebuild_issues(COVERAGE_JSON)
    check("REBUILD issue keyed rebuild:<component>, source 'rebuild'",
          issues and issues[0]["key"] == "rebuild:synthetic-tool"
          and issues[0]["source"] == "rebuild", issues)
    check("REBUILD issue names the SLA and the rebuild SOP",
          str(ocs.REBUILD_SLA_DAYS) in issues[0]["title"]
          and "self-built-image-rebuild" in issues[0]["url"], issues[0])

    # ---- process level: --dry-run execs nothing, reports honestly ---------
    with tempfile.TemporaryDirectory() as td:
        pj = Path(td, "plan.json"); pj.write_text(json.dumps(PLAN_JSON))
        tj = Path(td, "triage.json"); tj.write_text(json.dumps(TRIAGE_JSON))
        cj = Path(td, "cov.json"); cj.write_text(json.dumps(COVERAGE_JSON))

        rc, out = run_dry("--plan-json", str(pj), "--triage-json", str(tj),
                          "--coverage-json", str(cj))
        check("full dry-run exits 0", rc == 0, out)
        ops = [(e.get("op"), e.get("source") or e.get("subject"))
               for e in out.get("synced", [])]
        check("dry-run reconciles maintenance + legacy maintenance-window + "
              "triage + rebuild",
              {("reconcile", s) for s in
               ("maintenance", "maintenance-window", "triage", "rebuild")}
              <= set(ops), ops)

        # THE IMPORTANT ONE: absent input skips the subject INCLUDING reconcile
        rc, out = run_dry("--plan-json", str(pj))
        sources = {e.get("source") for e in out.get("synced", [])
                   if e.get("op") == "reconcile"}
        check("absent triage/coverage input -> their reconciles DO NOT run",
              "triage" not in sources and "rebuild" not in sources
              and out.get("skipped") == ["decide", "rebuild"], out)

        # no inputs at all must be loud, never a silent no-op success
        rc, out = run_dry()
        check("no inputs -> exit 2 (loud), nothing synced",
              rc == 2 and out.get("skipped") == ["plans", "decide", "rebuild"],
              out)

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} -> {', '.join(FAILURES)}")
        return 1
    print("all tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
