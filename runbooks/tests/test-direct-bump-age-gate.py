"""Regression tests for coverage.py's G5 cooldown on the DIRECT-BUMP lane.

F-0bd870a4 (2026-09-04): `minimum_release_age_hours` lived only in
auto-update.py, which gates Renovate PRs — coverage.py's direct-bump exit had
NO age check, so the lane with no reviewable PR got LESS scrutiny than the
lane with one. Proven exploited: homepage v2.2.0 was direct-bumped at ~40h in
28c68f59 while curl PR #211 was correctly held at 21h by the same policy in
the same window.

Directions pinned here: young holds, old passes, UNKNOWN AGE HOLDS (fail-safe
— a check that cannot see must not report a pass), an unresolved image repo
holds, `age_waive` globs waive, knob=0 disables, and the threshold is SOURCED
from auto-update-policy.yaml (single source of truth), never a constant local
to coverage.py.

CHARTS (2026-09-07): this file used to assert "chart kind -> out of scope
(pass)". That assertion encoded the bug rather than guarding against it. The
exemption's stated rationale was "auto-update.py still gates their PRs", which
is false for exactly the items the gate governs — a DIRECT bump is the no-PR
path, so nothing gated them. plex chart 1.9.0 would have been applied by the
03:30 nightly at ~5.5h old. Charts are now measured from the per-version
`created` in the Helm repo's index.yaml, so the directions pinned below are the
same three as for images: young holds, old passes, unknowable HOLDS fail-safe.
A blanket hold would also satisfy "young holds", so the old-passes case is the
one that proves this is a real cooldown.

Run:  python3 runbooks/tests/test-direct-bump-age-gate.py
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("cov", REPO / "runbooks/coverage.py")
cov = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cov)

FAILURES: list[str] = []
POLICY = {"minimum_release_age_hours": 48, "age_waive": []}


def check(name, got, want_hold):
    held = got is not None
    ok = held == want_hold
    print(f"  {'PASS' if ok else 'FAIL'}  {name}: {'hold' if held else 'pass'}"
          + ("" if ok else f"  ({got})"))
    if not ok:
        FAILURES.append(name)


def with_ages(mapping):
    """Patch the registry lookup: {'repo:tag': age_hours_or_None}."""
    cov.image_publish_age_hours = lambda repo, tag: mapping.get(f"{repo}:{tag}")


def item(repo="ghcr.io/x/y", tag="1.2.3", kind="image", comp="x"):
    return {"component": comp, "kind": kind, "current": "1.2.2",
            "target": tag, "image_repo": repo}


def main() -> int:
    print("test-direct-bump-age-gate")

    # too-young release HOLDS (the F-0bd870a4 case: homepage at ~40h < 48h)
    with_ages({"ghcr.io/x/y:1.2.3": 40})
    check("40h-old image -> hold", cov.direct_bump_age_gate(item(), POLICY), True)

    # old-enough release passes
    with_ages({"ghcr.io/x/y:1.2.3": 72})
    check("72h-old image -> pass", cov.direct_bump_age_gate(item(), POLICY), False)

    # unknown age HOLDS (fail-safe: a cooldown that cannot be proven has not elapsed)
    with_ages({})
    check("unknown age -> hold (fail-safe)",
          cov.direct_bump_age_gate(item(), POLICY), True)

    # an IMAGE with no resolvable repository is unmeasurable, not safe
    check("unresolved image repo -> hold (fail-safe)",
          cov.direct_bump_age_gate(item(repo=None), POLICY), True)

    # multi-repo row: a wrong repo self-eliminates (no such tag), the right one decides
    with_ages({"docker.io/library/busybox:1.2.3": None, "ghcr.io/x/y:1.2.3": 100})
    multi = {**item(repo=None), "image_repos": ["docker.io/library/busybox", "ghcr.io/x/y"]}
    check("multi-repo: wrong repo self-eliminates, right one passes",
          cov.direct_bump_age_gate(multi, POLICY), False)

    # operator age_waive glob waives (same semantics as auto-update.py)
    with_ages({"ghcr.io/x/y:1.2.3": 1})
    check("age_waive glob waives",
          cov.direct_bump_age_gate(
              item(), {"minimum_release_age_hours": 48, "age_waive": ["*x/y*"]}),
          False)

    # knob=0 / absent disables cleanly
    check("knob=0 disables gate",
          cov.direct_bump_age_gate(item(), {"minimum_release_age_hours": 0}), False)
    check("knob absent disables gate", cov.direct_bump_age_gate(item(), {}), False)

    # ── charts: same three directions as images ────────────────────────────
    # A chart whose source cannot be resolved is UNMEASURABLE, not safe.
    # (item() has component "x" in no namespace, so nothing resolves.)
    cov._CHART_AGE_CACHE.clear()
    check("chart, unresolvable source -> hold (fail-safe)",
          cov.direct_bump_age_gate(item(kind="chart"), POLICY), True)

    def with_chart_age(hours):
        """Pin chart_publish_age_hours without touching the network."""
        cov._CHART_AGE_CACHE.clear()
        cov.chart_publish_age_hours = lambda it, _h=hours: _h

    _real_chart_age = cov.chart_publish_age_hours
    try:
        with_chart_age(3)      # the measured plex 1.9.0 case
        check("3h-old chart -> hold",
              cov.direct_bump_age_gate(item(kind="chart"), POLICY), True)

        # THE LOAD-BEARING ONE: an old chart must PASS. Without this, a blanket
        # hold would satisfy every other chart assertion here.
        with_chart_age(250)
        check("250h-old chart -> pass",
              cov.direct_bump_age_gate(item(kind="chart"), POLICY), False)

        with_chart_age(None)   # OCI repo / no `created` / index unreachable
        check("chart age unknown -> hold (fail-safe)",
              cov.direct_bump_age_gate(item(kind="chart"), POLICY), True)

        # an operator waive still wins for charts, as it does for images
        with_chart_age(1)
        check("chart age_waive glob waives",
              cov.direct_bump_age_gate(
                  item(kind="chart"),
                  {"minimum_release_age_hours": 48, "age_waive": ["x"]}), False)
    finally:
        cov.chart_publish_age_hours = _real_chart_age
        cov._CHART_AGE_CACHE.clear()

    # SINGLE SOURCE OF TRUTH: the threshold comes from auto-update-policy.yaml
    # via load_policy(), never a constant duplicated in coverage.py.
    real = cov.load_policy()
    got = real.get("minimum_release_age_hours")
    ok = isinstance(got, (int, float)) and got > 0
    print(f"  {'PASS' if ok else 'FAIL'}  policy file carries minimum_release_age_hours ({got})")
    if not ok:
        FAILURES.append("policy-sourced threshold")
    src = (REPO / "runbooks/coverage.py").read_text()
    body = src.split("def direct_bump_age_gate", 1)[1].split("\ndef ", 1)[0]
    ok = not re.search(r"min_age\s*=\s*\d", body) and "minimum_release_age_hours" in body
    print(f"  {'PASS' if ok else 'FAIL'}  gate reads the policy key, no hardcoded threshold")
    if not ok:
        FAILURES.append("no hardcoded threshold")

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} -> {', '.join(FAILURES)}")
        return 1
    print("all tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
