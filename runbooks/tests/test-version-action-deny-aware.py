#!/usr/bin/env python3
"""Regression test: the version check's Action text is deny-aware (2026-09-15).

runbooks/check-all-versions.py emitted `action="batch with other minor bumps"`
for EVERY minor bump. Four live findings carried that instruction for hops the
lane engine (runbooks/coverage.py::assign_lane) routes to PLAN, which the
maintenance window will therefore never apply:

  F-7ef7af04  external-dns   chart 1.21.1 -> 1.22.0   full-block deny rule
  F-9af9baf7  nextcloud-mcp  image 0.184.5 -> 0.187.1  `max: patch` rule, minor hop
  F-24463e2b  frigate        image 0.17.2 -> 0.18.0    `max: patch` rule, minor hop
  F-60ebcdb5  otel-operator  chart 0.20.9 -> 0.21.0    0.x release-line rule, no deny rule

The operator reads the Action field, and it told them to batch a bump that
policy forbids. `bump_action()` now decides the text with coverage.py's OWN
matching (load_policy / deny_rule_for / _ver_tuple) so action and lane cannot
disagree, keys on the component name the way assign_lane() does (lowercased,
5.x chart -> `app-template`), and degrades to the old text when coverage.py is
unavailable (policy=None) — a version check must never crash on its policy
file. It is pure: a synthetic policy dict in, a string out, no network.

Run:  python3 runbooks/tests/test-version-action-deny-aware.py
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

os.environ.setdefault("_MISE_ACTIVATED", "1")  # skip the mise re-exec on import

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "check_all_versions", REPO / "runbooks/check-all-versions.py")
cav = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cav)

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


# Synthetic policy in the house YAML shape. Rule ORDER matters: coverage.py's
# deny_rule_for() lets the first matching glob decide (2026-09-12), which is
# why `*nextcloud-mcp*` sits above the `*nextcloud*` catch-all here as it does
# in the real file.
POLICY = {"deny": [
    {"match": "*external-dns*", "reason": "full block"},
    {"match": "*nextcloud-mcp*", "reason": "minor hops break", "max": "patch"},
    {"match": "*nextcloud*", "reason": "server catch-all (full block)"},
    {"match": "*app-template*", "reason": "chart migration", "max": "patch"},
]}
EMPTY = {"deny": []}
BATCH_MINOR = "batch with other minor bumps"
BATCH_PATCH = "batch with other patch bumps"


def main() -> int:
    print("test-version-action-deny-aware")
    ba = cav.bump_action

    # --- the four live findings, by shape ---------------------------------
    a = ba("external-dns", "chart", "1.21.1", "1.22.0", "minor", POLICY)
    check("external-dns minor + full-block rule -> held, names the glob",
          a.startswith("held by auto-update-policy (*external-dns*)") and "PLAN lane" in a, a)

    a = ba("nextcloud-mcp", "image", "0.184.5", "0.187.1", "minor", POLICY)
    check("nextcloud-mcp minor + `max: patch` -> held (deny outranks the 0.x rule)",
          a.startswith("held by auto-update-policy (*nextcloud-mcp*)"), a)

    a = ba("nextcloud-mcp", "image", "0.187.0", "0.187.1", "patch", POLICY)
    check("nextcloud-mcp PATCH + `max: patch` -> NOT held, batch text", a == BATCH_PATCH, a)

    a = ba("frigate", "image", "0.17.2", "0.18.0", "minor", EMPTY)
    check("frigate 0.17.2->0.18.0, no rule -> 0.x release-line text",
          a == "0.x release-line move (0.17 -> 0.18) — PLAN lane", a)

    a = ba("otel-operator", "chart", "0.20.9", "0.21.0", "minor", EMPTY)
    check("otel-operator 0.20.9->0.21.0 chart, no rule -> 0.x release-line text",
          a == "0.x release-line move (0.20 -> 0.21) — PLAN lane", a)

    # --- the unchanged cases -----------------------------------------------
    a = ba("homepage", "image", "1.4.0", "1.5.0", "minor", EMPTY)
    check("plain 1.x minor, no rule -> batch text (pre-existing behaviour)", a == BATCH_MINOR, a)

    a = ba("homepage", "image", "1.4.0", "1.4.1", "patch", EMPTY)
    check("plain 1.x patch, no rule -> batch patch text", a == BATCH_PATCH, a)

    a = ba("frigate", "image", "0.18.0", "0.18.1", "patch", EMPTY)
    check("0.x PATCH stays on its line -> 0.x rule does not fire", a == BATCH_PATCH, a)

    # --- fallback: coverage.py unavailable must never crash or invent a hold --
    a = ba("frigate", "image", "0.17.2", "0.18.0", "minor", None)
    check("policy=None (load failure) -> old batch text, even on a 0.x hop", a == BATCH_MINOR, a)
    a = ba("external-dns", "chart", "1.21.1", "1.22.0", "minor", None)
    check("policy=None (load failure) -> old batch text, even for a denied name", a == BATCH_MINOR, a)

    # --- parity with assign_lane()'s matching -------------------------------
    a = ba("nextcloud-mcp", "image", "0.187.0", "0.187.1", "patch", POLICY)
    check("first-match-wins: the narrow `max: patch` rule is not shadowed by the "
          "`*nextcloud*` catch-all below it", a == BATCH_PATCH, a)
    a = ba("nextcloud", "chart", "8.1.0", "8.2.0", "minor", POLICY)
    check("the catch-all still holds the server itself",
          a.startswith("held by auto-update-policy (*nextcloud*)"), a)
    a = ba("pgadmin", "chart", "5.1.0", "5.2.0", "minor", POLICY)
    check("5.x CHART target collapses to `app-template` like assign_lane()",
          a.startswith("held by auto-update-policy (*app-template*)"), a)
    a = ba("pgadmin", "chart", "5.1.0", "5.1.1", "patch", POLICY)
    check("app-template PATCH is admitted by its `max: patch`", a == BATCH_PATCH, a)
    a = ba("pgadmin", "image", "5.1.0", "5.2.0", "minor", POLICY)
    check("the collapse is chart-only: a 5.x IMAGE tag is not app-template", a == BATCH_MINOR, a)
    a = ba("External-DNS", "chart", "1.21.1", "1.22.0", "minor", POLICY)
    check("component match is case-insensitive (assign_lane lowercases)",
          a.startswith("held by auto-update-policy (*external-dns*)"), a)
    a = ba("external-dns-image", "image", "ghcr.io/x/external-dns:v0.14.0", "v0.15.0", "minor", POLICY)
    check("image repository is NOT the match key — only the component name is",
          a.startswith("held by auto-update-policy (*external-dns*)"), a)

    # --- the real loader path (importlib on SCRIPT_DIR/coverage.py) --------
    pol = cav.load_update_policy()
    check("load_update_policy() loads the real policy through coverage.py",
          isinstance(pol, dict) and isinstance(pol.get("deny"), list), repr(pol)[:80])
    check("bump_action never raises on garbage input",
          isinstance(ba(None, None, None, None, "minor", POLICY), str))

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
