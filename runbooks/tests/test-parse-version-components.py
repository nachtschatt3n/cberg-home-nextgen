#!/usr/bin/env python3
"""parse_version() must keep EVERY numeric component, not just three.

Truncating at (major, minor, micro) made Plex builds that differ only in a
4th component compare EQUAL, so a real update was invisible AND the
downgrade-suppressor could never fire. Both are covered here.
"""
import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("cav", ROOT / "runbooks" / "check-all-versions.py")
cav = importlib.util.module_from_spec(spec)
sys.modules["cav"] = cav
spec.loader.exec_module(cav)
_CLS = next(getattr(cav, n) for n in dir(cav)
            if isinstance(getattr(cav, n), type) and hasattr(getattr(cav, n), "parse_version"))


def _inst():
    return _CLS.__new__(_CLS)


class TestParseVersionKeepsAllComponents(unittest.TestCase):
    def test_four_component_build_is_not_truncated(self):
        self.assertEqual(_inst().parse_version("1.43.3.10861-07dfddaeb"), (1, 43, 3, 10861))

    def test_two_builds_differing_only_in_4th_are_not_equal(self):
        """The regression: both used to parse to (1, 43, 3)."""
        i = _inst()
        a = i.parse_version("1.43.3.10861-07dfddaeb")
        b = i.parse_version("1.43.3.10896-cb3ebc72d")
        self.assertNotEqual(a, b, "4-component builds must be distinguishable")
        self.assertLess(a, b, "the higher build must sort newer")

    def test_plain_semver_unchanged(self):
        self.assertEqual(_inst().parse_version("1.2.3"), (1, 2, 3))

    def test_calver_unchanged(self):
        self.assertEqual(_inst().parse_version("2026.8.3"), (2026, 8, 3))

    def test_v_prefix_and_build_metadata_still_stripped(self):
        self.assertEqual(_inst().parse_version("v1.2.3+build"), (1, 2, 3))

    def test_unparseable_returns_none(self):
        self.assertIsNone(_inst().parse_version(""))
        self.assertIsNone(_inst().parse_version("latest"))


class TestDowngradeSuppressorSeesFourthComponent(unittest.TestCase):
    """The padding in _is_real_downgrade was dead code while parse_version
    truncated; these assert it is now actually exercised."""

    def test_older_resolver_result_is_a_downgrade(self):
        self.assertTrue(_inst()._is_real_downgrade("1.43.3.10861-07dfddaeb", "1.43.3.10896-cb3ebc72d"))

    def test_newer_resolver_result_is_not_a_downgrade(self):
        self.assertFalse(_inst()._is_real_downgrade("1.43.3.10896-cb3ebc72d", "1.43.3.10861-07dfddaeb"))

    def test_shorter_prefix_sorts_older(self):
        self.assertTrue(_inst()._is_real_downgrade("1.43.3", "1.43.3.10861"))

    def test_plain_semver_both_directions(self):
        i = _inst()
        self.assertTrue(i._is_real_downgrade("1.2.3", "1.2.4"))
        self.assertFalse(i._is_real_downgrade("1.2.5", "1.2.4"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
