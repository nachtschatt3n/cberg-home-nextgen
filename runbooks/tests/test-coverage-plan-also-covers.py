#!/usr/bin/env python3
"""Regression test: a plan's lockstep coverage is machine-readable.

F-d71bc523, measured in the nightly window 2026-09-16 during the Step 0.5
planner-dispatch dedup. `coverage.py --json` listed nextcloud-notify-push
34.0.4 under needs_plan, while plan nextcloud-34.0.4 (vetted, operator GO
recorded) bumps that deployment's tag in the SAME commit and says so in its
`touches` block: "deployment/nextcloud-notify-push — tag moves in the SAME
commit (lockstep rule)".

The evidence existed in frontmatter; nothing read it. Dispatching a planner
there would have produced a SECOND plan for a bump an approved plan already
performs, and the two would then have to be kept in lockstep by hand. Dispatch
was withheld manually — which is exactly the step the signal is meant to
remove.

`also_covers:` is an explicit list rather than an inference from the prose,
because inferring coverage from prose is how a plan comes to claim work it does
not actually do — the failure `_plan_delivers()` already exists to prevent.

Run: python3 runbooks/tests/test-coverage-plan-also-covers.py
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("cov", REPO / "runbooks/coverage.py")
cov = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cov)

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


def item(component, target, current, kind="image"):
    return {"component": component, "namespace": "office", "kind": kind,
            "current": current, "target": target, "type": "patch"}


NOTIFY = item("nextcloud-notify-push", "34.0.4", "34.0.3")
WHITEBOARD = item("nextcloud-whiteboard", "v2.0.0", "v1.5.9")


def _plans_with_retired(plan_id: str) -> list:
    """Live plans plus `plan_id` as it stood in the commit before it was
    deleted. GIT_* is scrubbed: under the pre-commit hook it would point git
    at the hook's temporary index."""
    import os
    import shutil
    import subprocess
    import tempfile
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    rel = f"runbooks/maintenance/plans/{plan_id}.md"
    rev = subprocess.run(["git", "-C", str(REPO), "log", "-1", "--format=%H",
                          "--diff-filter=D", "--", rel],
                         capture_output=True, text=True, env=env).stdout.strip()
    if not rev:
        return cov.load_plans()
    body = subprocess.run(["git", "-C", str(REPO), "show", f"{rev}^:{rel}"],
                          capture_output=True, text=True, env=env).stdout
    if not body.strip():
        return cov.load_plans()
    tmp = Path(tempfile.mkdtemp(prefix="plans-also-covers-"))
    for f in cov.PLANS_DIR.glob("*.md"):
        shutil.copy(f, tmp / f.name)
    (tmp / f"{plan_id}.md").write_text(body)
    saved = cov.PLANS_DIR
    try:
        cov.PLANS_DIR = tmp
        return cov.load_plans()
    finally:
        cov.PLANS_DIR = saved
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    print("test-coverage-plan-also-covers")

    # ── the REAL plan file, not a fixture ──────────────────────────────
    # The plan was EXECUTED and retired (e43a1381, 2026-09-26), which deleted
    # the file this test reads and failed the whole pre-commit suite. The file
    # is still the real evidence, so read it from the last revision that had
    # it, alongside the live plan set — never a hand-written fixture.
    plans = cov.load_plans()
    if not any(p["plan_id"] == "nextcloud-34.0.4" for p in plans):
        plans = _plans_with_retired("nextcloud-34.0.4")
    nc = [p for p in plans if p["plan_id"] == "nextcloud-34.0.4"]
    check("the live nextcloud-34.0.4 plan loads", len(nc) == 1)
    if not nc:
        print("FAILED: plan missing")
        return 1
    nc = nc[0]
    check("it declares its lockstep coverage machine-readably",
          "nextcloud-notify-push" in nc["also_keys"], sorted(nc["also_keys"]))
    check("the plan is still keyed on its OWN component too",
          "nextcloud" in nc["keys"], sorted(nc["keys"]))

    got, _drift = cov.match_plan(NOTIFY, cov._name_keys(NOTIFY["component"]), plans)
    check("notify-push now matches the plan that actually moves its tag",
          got is not None and got["plan_id"] == "nextcloud-34.0.4",
          f"got {got and got['plan_id']}")
    got, _ = cov.match_plan(WHITEBOARD, cov._name_keys(WHITEBOARD["component"]), plans)
    check("so does the whiteboard backend, the other tag in that commit",
          got is not None and got["plan_id"] == "nextcloud-34.0.4",
          f"got {got and got['plan_id']}")

    server = item("nextcloud", "34.0.4", "34.0.3")
    got, _ = cov.match_plan(server, cov._name_keys("nextcloud"), plans)
    check("the plan's OWN component is claimed across kinds too — declaring "
          "also_covers marks this a chart+image lockstep plan, so the server "
          "image is covered by its own plan rather than indirectly, by happening "
          "to share a repository string with a sibling",
          got is not None and got["plan_id"] == "nextcloud-34.0.4",
          f"got {got and got['plan_id']}")

    # ── the KIND guard is waived only for a declared lockstep ──────────
    check("the plan is kind: chart while the item is an image — the declared "
          "lockstep is what waives the kind guard", nc["kind"] == "chart")
    unrelated_chart = {"plan_id": "x-chart", "file": "x.md", "keys": {"someapp"},
                       "also_keys": set(), "status": "draft", "kind": "chart",
                       "current": "1.0.0", "target": "2.0.0"}
    got, _ = cov.match_plan(item("someapp", "2.0.0", "1.0.0"), {"someapp"},
                            [unrelated_chart])
    check("a chart plan still does NOT deliver an ordinary image bump — the "
          "guard is waived for declared coverage only, not in general",
          got is None)

    # ── coverage still has to DELIVER the version ──────────────────────
    future = item("nextcloud-notify-push", "35.0.0", "34.0.3")
    got, _ = cov.match_plan(future, cov._name_keys(future["component"]), plans)
    check("a FUTURE bump of the same component is not covered by this plan "
          "(also_covers grants a key, never a blank cheque)",
          got is None or got["plan_id"] != "nextcloud-34.0.4",
          f"got {got and got['plan_id']}")

    # ── nothing else changed ───────────────────────────────────────────
    plain = [p for p in plans if not p.get("also_keys")]
    check("plans with no also_covers still load with an empty set (no crash, no "
          "accidental coverage)", all(p["also_keys"] == set() for p in plain)
          and len(plain) > 10, f"{len(plain)} plain plans")

    # ── COMMISSIONING ──────────────────────────────────────────────────
    def straw_ignore_also(item_, keys, plans_, heads=None):
        """The pre-fix matcher: name keys only, kind guard always on."""
        for p in plans_:
            if not (p["keys"] & keys) or p["status"] in cov.DEAD_PLAN_STATUSES:
                continue
            covers, drift = cov._plan_delivers(p, item_, heads)
            if covers:
                return p, drift
        return None, None

    got, _ = straw_ignore_also(NOTIFY, cov._name_keys(NOTIFY["component"]), plans)
    check("commissioning: the PRE-FIX matcher is caught — notify-push is "
          "unmatched and would be dispatched a redundant planner", got is None,
          f"straw matched {got and got['plan_id']}")

    orig = cov._plan_delivers

    def straw_ignore_kind_everywhere(plan, it, heads=None, ignore_kind=False):
        """Over-correction: waive the kind guard for ALL matches.

        Calls the CAPTURED original, not the module attribute — the attribute
        is what this straw replaces, so reading it back would recurse.
        """
        return orig(plan, it, heads, ignore_kind=True)

    try:
        cov._plan_delivers = straw_ignore_kind_everywhere
        got, _ = cov.match_plan(item("someapp", "2.0.0", "1.0.0"), {"someapp"},
                                [unrelated_chart])
        check("commissioning: waiving the kind guard everywhere is caught — a "
              "chart plan would claim an unrelated image bump", got is not None,
              "the kind assertion cannot discriminate")
    finally:
        cov._plan_delivers = orig

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} -> {', '.join(FAILURES)}")
        return 1
    print("all tests passed")
    return 0


def test_pytest_entry() -> None:
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())
