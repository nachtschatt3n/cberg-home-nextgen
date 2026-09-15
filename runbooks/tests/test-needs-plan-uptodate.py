"""Regression test for coverage.py's needs_plan exemption when the stable
channel head is already deployed (F-52e5637f, 2026-09-15).

n8n publishes its beta on the next MINOR line with a bare semver tag, so the
snapshot shows `2.38.7 -> 2.39.5 (minor)`. The `*n8n*` `max: patch` rule holds
it (correctly) and assign_lane() routes it to PLAN. Meanwhile the SAME run's
max_rule_fallbacks() record says `up-to-date`: npm dist-tag stable == the
deployed tag, nothing to do. Yet the item still landed in needs_plan, so every
sweep and every nightly Step 0.5 was asked to dispatch a planner for a beta
bump that policy will never admit — a draft somebody has to retire, forever.

The two outputs contradicted each other and the dispatch believed the wrong
one. up_to_date_components() + needs_plan_exempt() make the fallback record
authoritative for the planner question only: the item STAYS in PLAN (lane
counts remain honest), it just never becomes a planner target.

Run:  python3 runbooks/tests/test-needs-plan-uptodate.py
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("cov", REPO / "runbooks/coverage.py")
cov = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cov)

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


def main() -> int:
    print("test-needs-plan-uptodate")
    fallbacks = [
        {"component": "n8n", "status": "up-to-date", "current": "2.38.7",
         "blocked_target": "2.39.5", "candidate": None},
        {"component": "nocodb", "status": "hold", "current": "2026.08.2",
         "blocked_target": "2026.09.0", "candidate": "2026.09.0"},
        {"component": "nextcloud-mcp", "status": "hold", "candidate": None},
    ]
    cur = cov.up_to_date_components(fallbacks)
    check("only the up-to-date record's component is exempt", cur == {"n8n"}, f"got {cur}")

    n8n = {"component": "n8n", "kind": "image", "current": "2.38.7", "target": "2.39.5", "type": "minor"}
    nocodb = {"component": "nocodb", "kind": "image", "current": "2026.08.2", "target": "2026.09.0", "type": "minor"}
    check("n8n (stable head deployed) is exempt from needs_plan", cov.needs_plan_exempt(n8n, cur))
    check("nocodb (channel HOLD, real bump pending) still needs a plan", not cov.needs_plan_exempt(nocodb, cur))
    check("case-insensitive on the component key",
          cov.needs_plan_exempt({"component": "N8N"}, cur))
    check("no fallback records -> nothing exempt (the pre-existing behaviour)",
          not cov.needs_plan_exempt(n8n, cov.up_to_date_components([])))
    check("a `candidate` record is never exempt — it IS the thing to plan or apply",
          cov.up_to_date_components([{"component": "x", "status": "candidate"}]) == set())

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} -> {', '.join(FAILURES)}")
        return 1
    print("all tests passed")
    return 0


def test_pytest_entry() -> None:
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
