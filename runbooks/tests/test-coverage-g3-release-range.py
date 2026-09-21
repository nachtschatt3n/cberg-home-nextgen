#!/usr/bin/env python3
"""Regression test: G3 reads the release RANGE, not the target tag alone.

F-51728488, measured 2026-09-21 by reading the source and by observing a live
instance twice, hours apart:

  snapshot age 22.6h : scan-inbox-validator 3.1.3 -> 3.2.0, lane PLAN,
                       reason "G3 breaking-change signal — update ng-select to
                       v24, handle breaking changes"
  snapshot age 0.34h : scan-inbox-validator 3.1.3 -> 3.2.1, lane AUTO,
                       reason "safe patch/minor — window applies"

The breaking change did not go away. The TARGET moved past it: `breaking_signal`
fetched notes for the single new tag, so once 3.2.1 shipped, 3.2.0's notes were
never read by anything. The gate read as a breaking-change check while being a
breaking-change check for exactly one version — and AUTO is the lane an
UNATTENDED nightly window applies with no plan.

Ground truth re-verified live before this fix was written (the Action was
executed, not assumed):
  gh api repos/paperless-ngx/paperless-ngx/releases -> v3.2.1, v3.2.0, v3.1.3 …
  detect_breaking_changes(v3.2.0 body) -> ["Chore: update ng-select to v24,
                                            handle breaking changes"]
  detect_breaking_changes(v3.2.1 body) -> []
(The direct `releases/tags/3.2.0` probe returns empty — upstream tags carry a
`v` prefix and fetch_release_notes tries both; a test that skipped that detail
would have "proved" the notes were clean.)

THE ASYMMETRY IS DELIBERATE AND IS PINNED HERE. An unreadable range HOLDS only
when the hop crosses a MINOR boundary and the item has a resolved artifact.
Within a patch line the pre-existing G3-unknown baseline still applies — an
unauthenticated GitHub rate limit must not close the AUTO lane — and an item
with no artifact at all is already held one gate earlier by G5.

Run: python3 runbooks/tests/test-coverage-g3-release-range.py
"""

from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("cov", REPO / "runbooks/coverage.py")
cov = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cov)
cov._prerelease_digest_twin = lambda *a, **k: (None, "")

_au_spec = importlib.util.spec_from_file_location("au", REPO / "runbooks/auto-update.py")
au = importlib.util.module_from_spec(_au_spec)
_au_spec.loader.exec_module(au)

FAILURES: list[str] = []
POLICY = {"deny": []}
REPO_NAME = "ghcr.io/paperless-ngx/paperless-ngx"


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


def validator(target="3.2.1"):
    """The live item, verbatim from the snapshot."""
    return {"component": "scan-inbox-validator", "namespace": "office",
            "kind": "image", "current": "3.1.3", "target": target,
            "type": "minor", "image_repos": [REPO_NAME]}


def stub_range(between, note="stubbed"):
    cov._release_tags_between = lambda dep, cur, tgt: (between, note)


def stub_notes(breaking_tags):
    cov.breaking_change_signal = lambda repo, tag: (
        (True, "breaking-change signal in release notes: update ng-select to v24, "
               "handle breaking changes") if tag in breaking_tags
        else (False, "clean (release notes checked)"))


def main() -> int:
    print("test-coverage-g3-release-range")
    _real_bcs = cov.breaking_change_signal

    # ── adjacency arithmetic: what counts as leapfrogging ──────────────
    check("3.1.3 -> 3.2.1 skips releases (the live case)",
          cov._hop_skips_releases("3.1.3", "3.2.1"))
    check("3.13.1 -> 3.13.2 is ADJACENT — the memgraph patch must not be "
          "dragged out of AUTO by this gate",
          not cov._hop_skips_releases("3.13.1", "3.13.2"))
    check("1.0.0 -> 1.0.3 skips 1.0.1 and 1.0.2",
          cov._hop_skips_releases("1.0.0", "1.0.3"))
    check("a downgrade or equality is not a skip",
          not cov._hop_skips_releases("2.0.0", "1.0.0")
          and not cov._hop_skips_releases("2.0.0", "2.0.0"))
    check("an unparseable pair is NOT assumed to skip (a skip must be proven)",
          not cov._hop_skips_releases("latest", "main"))
    check("crossing a minor is detected; a patch gap is not",
          cov._crosses_minor("3.1.3", "3.2.1")
          and not cov._crosses_minor("1.2.3", "1.2.7"))

    # ── THE defect ─────────────────────────────────────────────────────
    stub_range(["3.2.0"], "1 intermediate release(s) read")
    stub_notes({"3.2.0"})
    status, note = cov._g3_range_gate(validator())
    check("the SKIPPED 3.2.0 is read and reported breaking", status == "breaking",
          f"{status}: {note}")
    check("...and the note names the skipped release, not the target",
          "3.2.0" in note and "SKIPPED" in note, note)
    lane, reason, _ = cov.assign_lane(validator(), POLICY, {}, [])
    check("the live 3.1.3 -> 3.2.1 hop lands in PLAN, not the unattended lane",
          lane == "PLAN", f"{lane}: {reason}")
    check("the lane reason says WHY (a skipped release), so the operator is not "
          "told a clean target's notes were the reason", "SKIPPED" in reason, reason)

    # ── and the hop that made it invisible: target-only reads clean ────
    check("the target tag 3.2.1 itself is clean — which is exactly why the "
          "target-only gate reported AUTO",
          cov.breaking_change_signal(REPO_NAME, "3.2.1")[0] is False)

    # ── clean intermediates still flow to AUTO ─────────────────────────
    stub_notes(set())
    lane, reason, _ = cov.assign_lane(validator(), POLICY, {}, [])
    check("when every skipped release reads clean the item still reaches AUTO",
          lane == "AUTO", f"{lane}: {reason}")
    check("...and the AUTO reason states the range was actually read",
          "G3 range" in reason, reason)

    # ── the FAIL-SAFE half, and its deliberate limit ───────────────────
    stub_range(None, "release list for X unreadable")
    lane, reason, _ = cov.assign_lane(validator(), POLICY, {}, [])
    check("an UNREADABLE range across a minor boundary HOLDS to PLAN",
          lane == "PLAN" and "UNEVALUATED" in reason, f"{lane}: {reason}")
    patch_gap = dict(validator(), current="3.2.1", target="3.2.4", type="patch")
    lane, reason, _ = cov.assign_lane(patch_gap, POLICY, {}, [])
    check("an unreadable range WITHIN a patch line does NOT hold — a rate-limited "
          "GitHub must not close the AUTO lane (the documented asymmetry)",
          lane == "AUTO", f"{lane}: {reason}")
    norepo = dict(validator(), image_repos=[])
    lane, reason, _ = cov.assign_lane(norepo, POLICY, {}, [])
    check("an item with NO resolved artifact is not held here — G5 already holds "
          "that case one gate earlier, with a truer reason",
          lane == "AUTO", f"{lane}: {reason}")
    chart = {"component": "somechart", "namespace": "x", "kind": "chart",
             "current": "1.2.0", "target": "1.4.0", "type": "minor"}
    lane, _r, _ = cov.assign_lane(chart, POLICY, {}, [])
    check("a CHART whose release list cannot be read is not held either — this "
          "gate must not silently become a blanket chart freeze", lane == "AUTO")

    # ── the range filter itself (auto-update.py), off the network ──────
    releases = [("v3.2.1", False), ("v3.2.0", False), ("v3.1.3", False),
                ("v3.1.2", False), ("v3.3.0-beta1", True)]
    au.github_releases = lambda checker, dep, timeout=15: releases
    between, why = au.release_tags_between(None, REPO_NAME, "3.1.3", "3.2.1")
    check("the range filter returns exactly the leapfrogged release",
          between == ["v3.2.0"], f"got {between} ({why})")
    check("...excluding both endpoints and any pre-release",
          "v3.1.3" not in (between or []) and "v3.2.1" not in (between or [])
          and "v3.3.0-beta1" not in (between or []))
    adj, _ = au.release_tags_between(None, REPO_NAME, "3.2.0", "3.2.1")
    check("an adjacent hop leapfrogs nothing", adj == [], f"got {adj}")
    au.github_releases = lambda checker, dep, timeout=15: None
    none_between, _why = au.release_tags_between(None, REPO_NAME, "3.1.3", "3.2.1")
    check("an unreadable release list returns None (never an empty list, which "
          "would read as 'nothing was skipped')", none_between is None)

    # ── THE WIRING: the gate must be called, or all of the above is inert
    src = inspect.getsource(cov.assign_lane)
    check("assign_lane() actually calls the range gate", "_g3_range_gate(" in src)
    check("...and routes its `breaking` verdict to PLAN",
          '"breaking"' in src and "PLAN" in src)
    au_src = inspect.getsource(au.classify)
    check("the PR lane passes the CURRENT version into G3 too, so a merged PR "
          "cannot leapfrog a breaking release either",
          "cur_tag=" in au_src, au_src[au_src.find("breaking_signal"):][:120])

    # ── COMMISSIONING ──────────────────────────────────────────────────
    stub_range(["3.2.0"], "1 intermediate")
    stub_notes({"3.2.0"})

    def straw_target_only(item):
        """The pre-fix gate: read the target tag, nothing else."""
        return "n/a", ""

    def straw_hold_on_any_unknown(item):
        """Over-correction: hold whenever a range cannot be read, patch or not."""
        if not cov._hop_skips_releases(item.get("current"), item.get("target")):
            return "n/a", ""
        return "unreadable", "over-eager straw"

    orig = cov._g3_range_gate
    try:
        cov._g3_range_gate = straw_target_only
        lane, _r, _ = cov.assign_lane(validator(), POLICY, {}, [])
        check("commissioning: the PRE-FIX target-only gate is caught — the live "
              "case reaches AUTO again", lane == "AUTO", f"straw gave {lane}")

        cov._g3_range_gate = straw_hold_on_any_unknown
        lane, _r, _ = cov.assign_lane(patch_gap, POLICY, {}, [])
        check("commissioning: an over-eager gate that holds every unreadable "
              "range is caught by the patch-line assertion", lane == "PLAN",
              f"straw gave {lane}")
    finally:
        cov._g3_range_gate = orig
        cov.breaking_change_signal = _real_bcs

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
