"""Regression tests for auto-update.py's G5 release-age cooldown.

The nightly window merges safe updates unattended every night, which widens
the supply-chain surface: a poisoned upstream release published hours ago
could ride the next 03:30 lane. Industry guidance (Renovate's own automerge
docs) is a minimum release age with the deliberate inversion that CVE fixes
merge at age 0 — a known-bad current version outranks an unknown-new one.

Directions pinned here: young holds, old passes, UNKNOWN HOLDS (a cooldown
that cannot be proven has not elapsed — the silent-wrong-answer family),
security markers waive, operator globs waive, retargeted PRs measure from the
NEWEST commit, and knob=0 disables cleanly.

Run:  python3 runbooks/tests/test-release-age-gate.py
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("au", REPO / "runbooks/auto-update.py")
au = importlib.util.module_from_spec(spec)
spec.loader.exec_module(au)

NOW = datetime.now(timezone.utc)
FAILURES: list[str] = []


def check(name, got, want_hold):
    held = got is not None
    ok = held == want_hold
    print(f"  {'PASS' if ok else 'FAIL'}  {name}: {'hold' if held else 'pass'}"
          + ("" if ok else f"  ({got})"))
    if not ok:
        FAILURES.append(name)


def with_commits(iso_list):
    """Patch run() so `gh pr view --json commits` returns these commits."""
    def fake_run(cmd, timeout=60, check=False):
        if "commits" in " ".join(map(str, cmd)):
            return 0, json.dumps({"commits": [{"committedDate": t} for t in iso_list]}), ""
        raise AssertionError(f"unexpected cmd {cmd}")
    au.run = fake_run


REAL_RUN = au.run
POLICY = {"minimum_release_age_hours": 48, "age_waive": []}
PR = {"number": 1, "title": "fix(container): update ghcr.io/x/y ( 1.0.0 → 1.0.1 )", "labels": []}
PARSED = {"dep": "ghcr.io/x/y"}


def iso(hours_ago):
    return (NOW - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    print("test-release-age-gate")

    with_commits([iso(10)])
    check("10h-old release -> hold", au.age_gate(PR, PARSED, POLICY), True)

    with_commits([iso(72)])
    check("72h-old release -> pass", au.age_gate(PR, PARSED, POLICY), False)

    # retargeted PR: old first commit, YOUNG newest — must hold
    with_commits([iso(200), iso(5)])
    check("retargeted PR measures newest commit", au.age_gate(PR, PARSED, POLICY), True)

    # unknown age holds (gh failure)
    au.run = lambda *a, **k: (1, "", "boom")
    check("unknown age -> hold (fail-safe)", au.age_gate(PR, PARSED, POLICY), True)

    # security title waives even at age 0
    with_commits([iso(1)])
    sec = dict(PR, title="fix(container): update x to 1.0.1 [SECURITY] CVE-2026-1234")
    check("CVE-marked PR waives cooldown", au.age_gate(sec, PARSED, POLICY), False)

    # security label waives
    lab = dict(PR, labels=[{"name": "security"}])
    with_commits([iso(1)])
    check("security label waives cooldown", au.age_gate(lab, PARSED, POLICY), False)

    # operator glob waives
    with_commits([iso(1)])
    check("age_waive glob waives",
          au.age_gate(PR, PARSED, {"minimum_release_age_hours": 48,
                                   "age_waive": ["*x/y*"]}), False)

    # knob absent/0 disables (no gh call is even attempted)
    au.run = lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not call gh"))
    check("knob=0 disables gate", au.age_gate(PR, PARSED, {"minimum_release_age_hours": 0}), False)
    check("knob absent disables gate", au.age_gate(PR, PARSED, {}), False)

    au.run = REAL_RUN
    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} -> {', '.join(FAILURES)}")
        return 1
    print("all tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
