"""Regression tests for the ownership-aware verdict (P3.1, sweep-run.py).

The old semantics — red = any open critical — produced 33 red / 2 yellow / 0
green over 30 days: red was the permanent state and stopped meaning "act
today". The 30-day back-test of these semantics showed 21 of those reds
becoming yellow (owned work in flight), the 12 that stay red forming one
genuine stuck period, and one old YELLOW becoming red because 49 findings sat
>4d unplanned while the verdict said calm.

These tests pin the direction of every failure mode: a verdict that cannot
establish ownership must be RED, never the calm color.

Run:  python3 runbooks/tests/test-ownership-verdict.py
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("sr", REPO / "runbooks/sweep-run.py")
sr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sr)

FAILURES: list[str] = []


def check(name, got, want):
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {name}: {got}" + ("" if ok else f" (wanted {want})"))
    if not ok:
        FAILURES.append(name)


def fake_triage(payload=None, *, raises=False, garbage=False):
    """Patch subprocess.run inside _ownership_verdict."""
    class R:
        stdout = "not json {" if garbage else json.dumps(payload or {})
    def run(*a, **kw):
        if raises:
            raise OSError("triage unavailable")
        return R()
    return types.SimpleNamespace(run=run)


def verdict_with(payload=None, **kw):
    import subprocess
    orig = subprocess.run
    subprocess.run = fake_triage(payload, **kw).run
    try:
        return sr._ownership_verdict(warn=1)
    finally:
        subprocess.run = orig


def main() -> int:
    print("test-ownership-verdict")

    # all criticals owned, none overdue -> yellow (the healthy steady state)
    check("owned criticals -> yellow",
          verdict_with({"counts": {"COVERED": 7, "PLAN": 3, "CRACK": 0},
                        "overdue_unplanned": []}), "yellow")

    # a CRACK is red — the no-cracks guarantee, surfaced in the verdict
    check("CRACK -> red",
          verdict_with({"counts": {"CRACK": 1}, "overdue_unplanned": []}), "red")

    # the back-test's yellow->red case: unplanned past SLA
    check("overdue unplanned -> red",
          verdict_with({"counts": {"PLAN": 2, "CRACK": 0},
                        "overdue_unplanned": ["F-aaaaaaaa"]}), "red")

    # every ownership-unknown mode is red, never calm
    check("triage crashes -> red", verdict_with(raises=True), "red")
    check("triage emits garbage -> red", verdict_with(garbage=True), "red")
    check("triage JSON without counts -> red", verdict_with({}), "red")

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} -> {', '.join(FAILURES)}")
        return 1
    print("all tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
