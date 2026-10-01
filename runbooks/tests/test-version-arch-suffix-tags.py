#!/usr/bin/env python3
"""Regression test: a single-architecture tag is never the bump target.

`_SEMVER_TAG_RE`'s build-suffix group `(-[0-9a-f]+)?` accepts `-386` (386 is
valid hex). On 2026-10-01 otel collector-contrib had published `0.162.0-386`
(and the other per-arch tags) while the multi-arch `0.162.0` was still 404, so
the picker offered a 32-bit image as the target of a safe-lane bump
(F-dab96929, found by the edot-collector-0.162.0 plan review).

Run: python3 runbooks/tests/test-version-arch-suffix-tags.py
"""

import importlib.util
import os
import unittest

os.environ.setdefault("_MISE_ACTIVATED", "1")  # skip the mise re-exec on import

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPT = os.path.join(_HERE, "..", "check-all-versions.py")
_spec = importlib.util.spec_from_file_location("check_all_versions", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


def _checker():
    return _mod.VersionChecker(os.path.join(_HERE, "..", ".."))


class ArchSuffixTags(unittest.TestCase):
    def setUp(self):
        self.c = _checker()

    def test_386_only_release_is_not_picked(self):
        # The measured 2026-10-01 shape: per-arch tags exist, manifest list does not.
        tags = ["0.161.0", "0.162.0-386", "0.162.0-amd64", "0.162.0-arm64"]
        self.assertEqual(self.c._pick_latest_semver_tag(tags, "0.161.0"), "0.161.0")

    def test_plain_tag_wins_once_published(self):
        tags = ["0.161.0", "0.162.0", "0.162.0-386", "0.162.0-amd64"]
        self.assertEqual(self.c._pick_latest_semver_tag(tags, "0.161.0"), "0.162.0")

    def test_hex_build_suffix_still_accepted(self):
        # The build-suffix group exists for real hex builds; only arch names go.
        tags = ["1.2.3", "1.2.4-ab12cd3"]
        self.assertEqual(self.c._pick_latest_semver_tag(tags, "1.2.3"), "1.2.4-ab12cd3")

    def test_arch_pinned_current_keeps_old_behaviour(self):
        tags = ["1.0.0-amd64", "1.1.0-amd64", "1.1.0"]
        self.assertIsNotNone(self.c._pick_latest_semver_tag(tags, "1.0.0-amd64"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
