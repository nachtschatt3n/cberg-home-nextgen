"""Regression tests for finding-triage.py's plan-or-page pass.

Pins the P2.2 gap: triage routed unmatched criticals to the PLAN lane and the
guarantee quietly ended there — rule 4e's prose said "dispatch a planner", and
whether a plan file ever appeared was checked by nobody. Four criticals sat
with lane=PLAN, no plan file, no window, invisible.

Also pins two bugs found during commissioning, both silent-wrong-answer class:
first_seen was not carried into triage results (unknown age => everything
overdue), and `policy.get("plan_sla_days") or 4` rewrote a legitimate SLA of 0
to 4 (falsy-zero).

Run:  python3 runbooks/tests/test-plan-or-page.py
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("ft", REPO / "runbooks/finding-triage.py")
ft = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ft)

NOW = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
FAILURES: list[str] = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + ("" if cond else f"  {detail}"))
    if not cond:
        FAILURES.append(name)


def res(fid, lane="PLAN", age_days=5.0):
    return {"finding_id": fid, "lane": lane, "title": f"{fid} title",
            "first_seen": None if age_days is None else NOW - timedelta(days=age_days)}


def with_plans(*plans):
    """Point PLANS_DIR at a tmpdir containing the given (name, frontmatter) plans."""
    d = Path(tempfile.mkdtemp())
    for name, fm in plans:
        (d / name).write_text(f"---\n{fm}\n---\nbody\n")
    ft.PLANS_DIR = d
    return d


def main() -> int:
    print("test-plan-or-page")
    pol = {"plan_sla_days": 4}

    # the live gap: PLAN-lane finding, no plan anywhere, past SLA -> overdue
    with_plans()
    needs, over = ft.plan_or_page([res("F-aaaaaaaa")], pol, now=NOW)
    check("unplanned past SLA -> overdue",
          [r["finding_id"] for r in over] == ["F-aaaaaaaa"])

    # a live plan carrying the ref claims the finding
    with_plans(("x.md", 'plan_id: x\nstatus: draft\nfinding_refs: ["F-aaaaaaaa"]'))
    needs, over = ft.plan_or_page([res("F-aaaaaaaa")], pol, now=NOW)
    check("plan with finding_refs claims it", needs == [] and over == [])

    # an EXECUTED plan does not count — its work is history
    with_plans(("x.md", 'plan_id: x\nstatus: executed\nfinding_refs: ["F-aaaaaaaa"]'))
    needs, over = ft.plan_or_page([res("F-aaaaaaaa")], pol, now=NOW)
    check("executed plan does not claim", len(over) == 1)

    # young finding: needs a plan, but not yet overdue
    with_plans()
    needs, over = ft.plan_or_page([res("F-bbbbbbbb", age_days=1.0)], pol, now=NOW)
    check("young finding: needs_plan but not overdue",
          len(needs) == 1 and over == [])

    # unknown age must NOT earn an implicit SLA extension
    needs, over = ft.plan_or_page([res("F-cccccccc", age_days=None)], pol, now=NOW)
    check("unknown age counts as overdue", len(over) == 1)

    # falsy-zero: SLA of 0 means everything unplanned is overdue NOW
    needs, over = ft.plan_or_page([res("F-dddddddd", age_days=0.1)],
                                  {"plan_sla_days": 0}, now=NOW)
    check("SLA=0 is honored (falsy-zero regression)", len(over) == 1)

    # non-PLAN lanes are never flagged
    needs, over = ft.plan_or_page([res("F-eeeeeeee", lane="COVERED")], pol, now=NOW)
    check("non-PLAN lanes ignored", needs == [] and over == [])

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} -> {', '.join(FAILURES)}")
        return 1
    print("all tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
