#!/usr/bin/env python3
"""Regression test: a release candidate wearing a GA-looking tag is not AUTO.

F-aff597aa — and this one CAME TRUE. The record said in as many words "Do NOT
direct-bump penpot-cache to 9.2". The fix was not implemented, so the AUTO lane
admitted it again and the bump SHIPPED, unattended, in the Step 0 batch of the
on-demand cilium window (commit 335ff526).

Measured live, and re-verified the day this test was written:
  valkey/valkey:9.2        sha256:b0eef48ff6c2d8c4c…  pushed 2026-09-17T00:43:36Z
  valkey/valkey:9.2.0-rc1  sha256:b0eef48ff6c2d8c4c…  pushed 2026-09-17T00:43:34Z
  IDENTICAL digest, 1.7s apart.  9.2.0 -> HTTP 404.  9.2.1 -> HTTP 404.
There is no GA 9.2.x at all, so a RELEASE CANDIDATE runs in production — and a
pinned 3-component tag was replaced by a FLOATING 2-component one, which a
future reconcile can move again with no commit and no review.

TWO detectors, because each covers the other's blind spot:
  1. ARITY — offline, decidable by the window agent with no DSN and no network:
     the target names fewer version components than the pin, on the same major.
  2. DIGEST TWIN — Docker Hub, best-effort, ADDITIVE: the target is
     byte-identical to a sibling -rc/-beta/-alpha tag. Catches the case arity
     cannot, a 3-component GA-looking tag that is really the RC.

Scope matters in both directions: `13.6-bookworm` is an ordinary suffixed tag,
not a pre-release, and holding it would be the over-capture this repo keeps
finding. That contract is pinned here too.

Run: python3 runbooks/tests/test-coverage-prerelease-target.py
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("cov", REPO / "runbooks/coverage.py")
cov = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cov)
cov._release_tags_between = lambda *a, **k: ([], "stubbed")
cov._direct_bump_structural_gate = lambda item: (False, "clean (diff checked: stubbed — the G3 structural companion reaches the compare API; pinned by test-structural-signal.py)")

FAILURES: list[str] = []
POLICY = {"deny": []}


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


def penpot(target="9.2"):
    """The live item that shipped, verbatim from the snapshot."""
    return {"component": "penpot-cache", "namespace": "office", "kind": "image",
            "current": "9.1.2", "target": target, "type": "minor",
            "image_repos": ["valkey/valkey"]}


def no_twin(*a, **k):
    return None, ""


def main() -> int:
    # G3 is stubbed as CHECKED so this suite exercises the pre-release gate alone;
    # since 2026-09-22 an unavailable-notes verdict routes to PLAN on its own,
    # which would otherwise mask what the straw below needs to demonstrate.
    cov.breaking_change_signal = lambda repo, tag: (False, "clean (release notes checked, stubbed)")
    print("test-coverage-prerelease-target")
    cov._prerelease_digest_twin = no_twin

    # ── layer 1: ARITY, offline ────────────────────────────────────────
    hold = cov.prerelease_target_hold(penpot())
    check("9.1.2 -> 9.2 is held: a floating 2-component pointer replacing a "
          "pinned 3-component version (THE live bump)", bool(hold))
    check("...and the reason explains BOTH halves — not GA-provable, and a "
          "floating pin a reconcile can move again",
          bool(hold) and "GA" in hold and "floating" in hold, str(hold))
    check("the gate needs no network for this: it is decidable in the window "
          "agent with no DSN", cov.prerelease_target_hold(
              dict(penpot(), image_repos=[])) is not None)

    # ── SCOPE: it must not become a general suffix freeze ──────────────
    check("an ordinary suffixed tag on a DIFFERENT major is untouched "
          "(`13.6-bookworm` is not a pre-release)",
          cov.prerelease_target_hold(
              {"component": "x", "kind": "image", "current": "1.0.0",
               "target": "13.6-bookworm", "image_repos": []}) is None)
    check("a full 3-component GA target is untouched",
          cov.prerelease_target_hold(penpot("9.2.0")) is None)
    check("a longer target (more components, not fewer) is untouched",
          cov.prerelease_target_hold(
              {"component": "x", "kind": "image", "current": "1.43.3",
               "target": "1.43.3.10896", "image_repos": []}) is None)

    # ── layer 2: DIGEST TWIN, additive ─────────────────────────────────
    cov._prerelease_digest_twin = lambda repo, tag: (
        ("9.2.0-rc1", f"{repo}:{tag} and {repo}:9.2.0-rc1 are the same image")
        if tag == "9.2.0" else (None, ""))
    hold = cov.prerelease_target_hold(penpot("9.2.0"))
    check("a 3-component target that is BYTE-IDENTICAL to an -rc sibling is "
          "held — the case arity cannot see", bool(hold))
    check("...and the reason names the twin tag as the evidence",
          bool(hold) and "9.2.0-rc1" in hold, str(hold))
    cov._prerelease_digest_twin = no_twin
    check("with no twin found the layer adds nothing (it can only ADD holds)",
          cov.prerelease_target_hold(penpot("9.2.0")) is None)

    # ── the lane, and the position of the gate ─────────────────────────
    lane, reason, _ = cov.assign_lane(penpot(), POLICY, {}, [])
    check("the lane is PLAN, not the lane an unattended window applies",
          lane == "PLAN", f"{lane}: {reason}")
    lane, reason, _ = cov.assign_lane(penpot(), POLICY, {"penpot-cache": "999"}, [])
    check("an open Renovate PR does NOT launder it — the gate sits ABOVE both "
          "AUTO exits", lane == "PLAN", f"{lane}: {reason}")

    # A plan that already covers the bump still wins: the gate sits BELOW
    # match_plan, so a planned item keeps its truer reason.
    plan = {"plan_id": "valkey-9.2", "file": "v.md", "keys": {"penpot-cache"},
            "also_keys": set(), "status": "draft", "kind": "image",
            "current": "9.1.2", "target": "9.2"}
    lane, reason, _ = cov.assign_lane(penpot(), POLICY, {}, [plan])
    check("an existing plan still owns the item (the gate does not overwrite a "
          "truer reason)", lane == "PLAN" and reason.startswith("plan exists"),
          f"{lane}: {reason}")

    # ── COMMISSIONING ──────────────────────────────────────────────────
    def straw_marker_only(item):
        """The pre-fix behaviour: trust an explicit -rc/-beta marker in the tag."""
        return ("target is an explicit pre-release tag"
                if cov._PRERELEASE_TAG.search(str(item.get("target") or ""))
                else None)

    orig = cov.prerelease_target_hold
    try:
        cov.prerelease_target_hold = straw_marker_only
        lane, _r, _ = cov.assign_lane(penpot(), POLICY, {}, [])
        check("commissioning: the PRE-FIX marker-only check is caught — 9.2 "
              "carries no marker, so the RC reaches AUTO again", lane == "AUTO",
              f"straw gave {lane}")
        # ...and it must still catch what it always caught.
        check("commissioning: the straw does still hold an explicitly marked tag, "
              "so this file is testing the NEW capability, not the old one",
              straw_marker_only({"target": "9.2.0-rc1"}) is not None)
    finally:
        cov.prerelease_target_hold = orig

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
