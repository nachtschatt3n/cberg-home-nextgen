#!/usr/bin/env python3
"""Regression tests for VersionChecker._pick_latest_semver_tag.

Guards the 2026-08-18 fix for the same-major masking bug (found during
redisinsight-3.8.0 planning, plan §1.1): the picker preferred the current
tag's major unconditionally, so a component sitting at the HEAD of a stale
major line got its own tag back and reported as up-to-date — masking the
entire newer major (redisinsight 2.70.1 vs the 3.x line, ~7 months).

Run: python3 runbooks/tests/test-pick-latest-semver-tag.py
"""

import importlib.util
import os
import sys
import unittest

os.environ.setdefault("_MISE_ACTIVATED", "1")  # skip the mise re-exec on import

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPT = os.path.join(_HERE, "..", "check-all-versions.py")
_spec = importlib.util.spec_from_file_location("check_all_versions", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


def _checker():
    # repo root; no network is touched by _pick_latest_semver_tag
    return _mod.VersionChecker(os.path.join(_HERE, "..", ".."))


class PickLatestSemverTagTest(unittest.TestCase):
    def setUp(self):
        self.c = _checker()

    def pick(self, tags, current=""):
        return self.c._pick_latest_semver_tag(tags, current)

    # ── The redisinsight §1.1 regression ────────────────────────────────
    def test_head_of_stale_major_surfaces_newer_major(self):
        """Current is the newest tag of an old major → must return the newer
        major's head, NOT the current tag (the masking bug)."""
        tags = ["2.58.0", "2.70.0", "2.70.1", "3.0.1", "3.7.0", "3.8.0"]
        self.assertEqual(self.pick(tags, "2.70.1"), "3.8.0")

    # ── Legitimate same-major preference must survive ──────────────────
    def test_in_line_update_preferred_over_newer_major(self):
        """A newer tag WITHIN the current major exists → prefer it (postgres
        17.10 should propose 17.11, not jump to 18.x)."""
        tags = ["17.10", "17.11", "18.5", "18.6"]
        self.assertEqual(self.pick(tags, "17.10"), "17.11")

    def test_up_to_date_overall_returns_current(self):
        tags = ["3.7.0", "3.8.0"]
        self.assertEqual(self.pick(tags, "3.8.0"), "3.8.0")

    def test_no_current_tag_returns_overall_newest(self):
        tags = ["1.2.3", "2.0.0", "0.9.9"]
        self.assertEqual(self.pick(tags), "2.0.0")

    # ── Existing behaviours that must not regress ──────────────────────
    def test_variant_pinning_still_applies(self):
        """On an -alpine pin, never propose a cross-variant tag."""
        tags = ["1.25-alpine", "1.26-alpine", "1.27"]
        self.assertEqual(self.pick(tags, "1.25-alpine"), "1.26-alpine")

    def test_no_semver_tags_returns_none(self):
        self.assertIsNone(self.pick(["latest", "edge", "sha-abc1234"], "latest"))

    def test_clean_tag_outranks_build_sha_suffix(self):
        """n8n 2026-08-03 case: same version, plain tag wins over sha-build."""
        tags = ["2.33.3-12d3f08", "2.33.3", "2.33.2"]
        self.assertEqual(self.pick(tags, "2.33.2"), "2.33.3")

    # ── Pre-releases are never a recommendation (2026-08-18) ───────────
    def test_prerelease_never_recommended(self):
        """frigate case: 0.18.0-beta* must not beat stable 0.17.2."""
        tags = ["0.17.1", "0.17.2", "0.18.0-beta1", "0.18.0-beta2",
                "0.18.0-beta3"]
        self.assertEqual(self.pick(tags, "0.17.2"), "0.17.2")

    def test_prerelease_with_variant_suffix_still_excluded(self):
        """A hex-lookalike pre-release IS version-shaped once a known variant
        follows it (`0.18.0-b1-noble`), so only the explicit pre-release rule
        keeps it out."""
        tags = ["0.17.2-noble", "0.18.0-b1-noble"]
        self.assertEqual(self.pick(tags, "0.17.2-noble"), "0.17.2-noble")

    def test_short_hex_lookalike_prerelease_excluded(self):
        """`-b2` parses as a hex build suffix; it is still a pre-release."""
        tags = ["1.4.0", "1.5.0-b2", "1.5.0-rc.1"]
        self.assertEqual(self.pick(tags, "1.4.0"), "1.4.0")

    def test_dotted_rc_excluded(self):
        """whiteboard case: v2.0.0-beta.1 must not mask the v1.5.x line."""
        tags = ["v1.5.3", "v1.5.9", "v2.0.0-beta.1"]
        self.assertEqual(self.pick(tags, "v1.5.3"), "v1.5.9")

    def test_prerelease_only_repo_still_answers(self):
        """No stable candidate exists → do not collapse to None, answer with
        the pre-release line. (Word-shaped markers like `beta1` never reach
        this rule — `_SEMVER_TAG_RE` already rejects them as unparseable.)"""
        picked = self.pick(["0.9.0-b1", "1.0.0-b1"], "0.9.0-b1")
        self.assertEqual(picked, "1.0.0-b1")

    # ── Compound distro variants (2026-08-18, koush/scrypted) ──────────
    def test_compound_distro_variant_is_version_shaped(self):
        """`-noble-full` is a build flavour, not a version — and the whole
        repo was invisible to the picker without it."""
        tags = ["v0.142.9-noble-full", "v0.143.0-noble-full",
                "v0.144.1-noble-full", "v0.144.1-noble-lite"]
        self.assertEqual(self.pick(tags, "v0.143.0-noble-full"),
                         "v0.144.1-noble-full")

    def test_compound_variant_pinning_does_not_cross_flavours(self):
        tags = ["v0.143.0-noble-full", "v0.144.1-noble-nvidia"]
        self.assertEqual(self.pick(tags, "v0.143.0-noble-full"),
                         "v0.143.0-noble-full")

    def test_compound_variant_does_not_swallow_prerelease(self):
        self.assertTrue(_mod.VersionChecker._is_prerelease_tag("0.18.0-beta1-tensorrt"))
        self.assertFalse(_mod.VersionChecker._is_prerelease_tag("v0.144.1-noble-full"))
        self.assertFalse(_mod.VersionChecker._is_prerelease_tag("8.10.0-alpine"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
