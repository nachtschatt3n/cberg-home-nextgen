#!/usr/bin/env python3
"""Regression tests for coverage.py's version comparators.

`_is_strictly_newer` and `_semver_type` both parsed a tag with
`re.findall(r"\d+", v)[:3]` — the first three numeric components and no more.
Two Plex builds differing only in the 4th field (`1.43.3.10861` vs
`1.43.3.10896`) therefore compared EQUAL, so `_is_strictly_newer` returned
False and `parse_actionable()` dropped the item before it reached any lane.

That is worse than a mislabel. `_is_strictly_newer` is not only a suppressor,
it is the DENOMINATOR: an update that never enters the enumeration can never
be reported as a crack, so coverage printed `covered: YES (no cracks)` over a
real, actionable, unplanned update. Found 2026-08-24, the same afternoon the
identical `[:3]` truncation was fixed in check-all-versions.py — one defect,
two independent implementations.

The suppressor half must keep working: `_is_strictly_newer` exists to stop a
DOWNGRADE arrow (the immich `v3.1.0 → v1.116.0` phantom) manufacturing a
PLAN-lane item. Widening the comparison must not blind it.

Run: python3 runbooks/tests/test-coverage-version-arity.py
"""

import importlib.util
import os
import sys
import unittest

os.environ.setdefault("_MISE_ACTIVATED", "1")

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPT = os.path.join(_HERE, "..", "coverage.py")
_spec = importlib.util.spec_from_file_location("coverage_mod", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
sys.argv = ["coverage.py"]
_spec.loader.exec_module(_mod)


class FourComponentTagTest(unittest.TestCase):
    """The defect: a build-only bump vanished from the enumeration."""

    def test_plex_build_bump_is_strictly_newer(self):
        self.assertTrue(_mod._is_strictly_newer(
            "1.43.3.10861-07dfddaeb", "1.43.3.10896-cb3ebc72d"))

    def test_plex_build_bump_survives_a_truncated_target(self):
        """The overview table clips long tags; the arrow must still count."""
        self.assertTrue(_mod._is_strictly_newer(
            "1.43.3.10861-07dfddaeb", "1.43.3.10896-cb..."))

    def test_plex_build_bump_is_typed_patch_not_unknown(self):
        """`unknown` handed classification to the row's complexity column,
        which describes the CHART, not this image."""
        self.assertEqual(_mod._semver_type(
            "1.43.3.10861-07dfddaeb", "1.43.3.10896-cb3ebc72d"), "patch")

    def test_plex_build_downgrade_is_not_newer(self):
        self.assertFalse(_mod._is_strictly_newer(
            "1.43.3.10896-cb3ebc72d", "1.43.3.10861-07dfddaeb"))

    def test_identical_four_component_tags_are_not_newer(self):
        self.assertFalse(_mod._is_strictly_newer(
            "1.43.3.10896-cb3ebc72d", "1.43.3.10896-cb3ebc72d"))

    def test_jellyfin_style_date_build_tag(self):
        self.assertTrue(_mod._is_strictly_newer(
            "10.11.10.20260524-220644", "10.11.11.20260606-153911"))
        self.assertFalse(_mod._is_strictly_newer(
            "10.11.11.20260606-153911", "10.11.10.20260524-220644"))


class DowngradeSuppressorStillWorksTest(unittest.TestCase):
    """The half that must NOT be blinded by widening the comparison."""

    def test_immich_phantom_downgrade_stays_suppressed(self):
        self.assertFalse(_mod._is_strictly_newer("v3.1.0", "v1.116.0"))
        self.assertFalse(_mod._is_strictly_newer(
            "v3.1.0-openvino", "v1.94.1-openvino"))

    def test_trailing_zero_is_not_an_update(self):
        """busybox `1.38 → 1.38.0` is the same release."""
        self.assertFalse(_mod._is_strictly_newer("1.38", "1.38.0"))

    def test_unparseable_side_is_never_suppressed(self):
        self.assertTrue(_mod._is_strictly_newer("git-44ce6d0", "git-9ab1f22"))


class OrdinaryBumpsUnchangedTest(unittest.TestCase):

    def test_patch_minor_major_still_classify(self):
        self.assertEqual(_mod._semver_type("8.10.0-alpine", "8.10.1-alpine"), "patch")
        self.assertEqual(_mod._semver_type("6.14.5", "6.15.2"), "minor")
        self.assertEqual(_mod._semver_type("17.11-bookworm", "18.6-bookworm"), "major")
        self.assertEqual(_mod._semver_type("2026.8.0", "2026.8.1"), "patch")

    def test_short_tags_still_order(self):
        self.assertTrue(_mod._is_strictly_newer("4.1.1", "4.2"))
        self.assertTrue(_mod._is_strictly_newer("1.38", "1.38.1"))


class EnumerationTest(unittest.TestCase):
    """End-to-end: the item must actually reach parse_actionable()."""

    def test_a_four_component_row_enters_the_denominator(self):
        import tempfile
        import pathlib
        md = (
            "## Quick Overview Table\n\n"
            "| Deployment | Namespace | Chart | Image | App | Complexity |\n"
            "|---|---|---|---|---|---|\n"
            "| `plex` | `media` | 1.6.0 ✅ | "
            "1.43.3.10861-07dfddaeb → 1.43.3.10896-cb... | "
            "1.43.3.10861-07dfddaeb | \U0001f7e2 PATCH |\n"
        )
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "version-check-current.md"
            p.write_text(md)
            orig = _mod.VERSION_MD
            try:
                _mod.VERSION_MD = p
                items = _mod.parse_actionable()
            finally:
                _mod.VERSION_MD = orig
        comps = [i["component"] for i in items]
        self.assertIn("plex", comps,
                      "a 4-component build bump must enter the enumeration; "
                      "an item that is never enumerated can never be a crack")


if __name__ == "__main__":
    unittest.main(verbosity=2)
