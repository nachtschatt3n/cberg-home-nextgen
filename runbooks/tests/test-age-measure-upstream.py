"""Regression tests for auto-update.py G5's AGE MEASURE (upstream vs PR commit).

The n8n starvation (2026-09-04): G5 judged the cooldown against the PR's
newest Renovate commit, and fast-shipping upstreams (n8n releases every
~1-2 days) force-push the PR on every retarget — resetting the clock, so
PR #210 sat 9 days without ever being "48h old". The cooldown defends against
a poisoned RELEASE, so the honest clock is the target version's UPSTREAM
publish timestamp.

Directions pinned here: the upstream release date is PREFERRED over the PR
commit date (old release + freshly force-pushed PR passes; young release +
old PR commit holds); when the upstream date is unknowable the gate FALLS
BACK to the PR-commit measure (fail-closed to the stricter clock); unknown on
both measures holds; the registry publish date is the second upstream source;
the hold reason NAMES the measure used; security waivers still bypass.

Run:  python3 runbooks/tests/test-age-measure-upstream.py
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
POLICY = {"minimum_release_age_hours": 48, "age_waive": []}
PR = {"number": 210, "title": "feat(container): update ghcr.io/x/n8n ( 1.0.0 → 1.0.1 )",
      "labels": []}
PARSED = {"dep": "ghcr.io/x/n8n", "new": "1.0.1"}


def iso(hours_ago):
    return (NOW - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def check(name, got, want_hold, reason_contains=None):
    held = got is not None
    ok = held == want_hold
    if ok and reason_contains and held:
        ok = reason_contains in got[1]
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


class Checker:
    """Stub VersionChecker: `published` is the GitHub-release age in hours,
    or None to make the upstream lookup fail."""

    def __init__(self, published=None):
        self.published = published

    def get_repo_info_from_image(self, dep):
        return ("x", "n8n") if self.published is not None else None

    def get_chart_repo_info(self, *a):
        return None

    def fetch_release_notes(self, owner, repo, tag):
        return {"body": "notes", "published_at": iso(self.published)}


def with_registry(age):
    """Patch the coverage.py registry fallback to return `age` (or None)."""
    au._load_coverage = lambda: types.SimpleNamespace(
        image_publish_age_hours=lambda repo, tag: age)


def main() -> int:
    print("test-age-measure-upstream")
    with_registry(None)

    # THE n8n CASE: release is 60h old upstream, but Renovate force-pushed the
    # PR 5h ago. The old PR-commit measure held this forever; the upstream
    # measure must PASS it.
    with_commits([iso(5)])
    check("old upstream release + fresh force-push -> pass (no starvation)",
          au.age_gate(PR, PARSED, POLICY, Checker(published=60)), False)

    # the inverse: a genuinely young release holds even if the PR commit is old
    with_commits([iso(200)])
    check("young upstream release + old PR commit -> hold",
          au.age_gate(PR, PARSED, POLICY, Checker(published=10)), True,
          reason_contains="upstream GitHub release")

    # upstream unknowable -> falls back to the PR-commit measure (stricter)
    with_commits([iso(5)])
    check("no upstream date + young PR commit -> hold (fallback)",
          au.age_gate(PR, PARSED, POLICY, Checker(published=None)), True,
          reason_contains="stricter fallback")
    with_commits([iso(72)])
    check("no upstream date + old PR commit -> pass (fallback)",
          au.age_gate(PR, PARSED, POLICY, Checker(published=None)), False)

    # registry publish date is the second upstream source (image-shaped deps)
    with_registry(100)
    with_commits([iso(5)])  # would hold on the commit measure
    check("registry date resolves when GitHub release does not",
          au.age_gate(PR, PARSED, POLICY, Checker(published=None)), False)
    with_registry(None)

    # unknown on BOTH measures holds (fail-safe)
    au.run = lambda *a, **k: (1, "", "boom")
    check("unknown on both measures -> hold",
          au.age_gate(PR, PARSED, POLICY, Checker(published=None)), True,
          reason_contains="both measures")

    # security waiver still bypasses everything, age 0 included
    sec = dict(PR, labels=[{"name": "security"}])
    check("security label waives regardless of measure",
          au.age_gate(sec, PARSED, POLICY, Checker(published=1)), False)

    # no checker (legacy callers) -> pure PR-commit behaviour, unchanged
    with_commits([iso(72)])
    check("checker=None -> PR-commit measure only",
          au.age_gate(PR, PARSED, POLICY), False)

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} -> {', '.join(FAILURES)}")
        return 1
    print("all tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
