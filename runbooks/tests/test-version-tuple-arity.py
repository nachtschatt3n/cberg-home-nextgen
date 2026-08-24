#!/usr/bin/env python3
"""Regression tests for variable-arity version tuples.

`parse_version` returns ALL numeric components (the 2026-08-22 fix for
4-component Plex builds), so callers meet tuples of differing length. Two
defects followed, both found on 2026-08-24:

1. `assess_update_complexity` unpacked exactly three values. Any two-part tag
   (`python:3.11-slim`, `busybox:1.38`) raised ValueError and killed the WHOLE
   version check four apps in. Because a Python traceback exits 1 — the same
   code as the ordinary "found findings" — sweep-run scored the aborted run as
   completed and auto-closed 25 findings the scan never even reached.
2. Raw tuple comparison made `1.38` strictly less than `1.38.0`, so the same
   release was reported as an available update every single run.

Both are fixed by zero-padding to a common length, which equates ONLY the
formatting difference: every real ordering, including 4+ component builds,
must survive. That is what these tests pin.

Run: python3 runbooks/tests/test-version-tuple-arity.py
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
    return _mod.VersionChecker(os.path.join(_HERE, "..", ".."))


class ShortTupleArityTest(unittest.TestCase):
    """Defect 1: a 2-component tag must not crash the run."""

    def test_two_component_tag_does_not_raise(self):
        """mcpo's `python:3.11-slim` — the exact tag that aborted the sweep."""
        c = _checker()
        result = c.assess_update_complexity("3.11-slim", "3.14.7-slim")
        self.assertEqual(result["type"], "minor")

    def test_two_component_on_both_sides(self):
        c = _checker()
        self.assertEqual(
            c.assess_update_complexity("1.38", "1.39")["type"], "minor")

    def test_single_component_tag(self):
        c = _checker()
        self.assertEqual(c.assess_update_complexity("17", "18")["type"], "major")

    def test_short_current_against_long_latest_is_still_ordered(self):
        """Padding must not blind the detector: 1.38 → 1.38.1 IS an update."""
        c = _checker()
        self.assertEqual(
            c.assess_update_complexity("1.38", "1.38.1")["type"], "patch")
        self.assertTrue(c.is_reportable_update("1.38", "1.38.1"))


class FormattingOnlyDifferenceTest(unittest.TestCase):
    """Defect 2: `1.38` and `1.38.0` are the same release."""

    def test_trailing_zero_is_not_an_update(self):
        c = _checker()
        self.assertFalse(c.is_reportable_update("1.38", "1.38.0"))
        self.assertEqual(
            c.assess_update_complexity("1.38", "1.38.0")["type"], "unknown")

    def test_trailing_zero_on_a_two_to_three_pad(self):
        c = _checker()
        self.assertFalse(c.is_reportable_update("1.16", "1.16.0"))


class FourComponentBuildTest(unittest.TestCase):
    """The 4-component case the padding must NOT re-truncate."""

    def test_plex_build_bump_is_reportable(self):
        c = _checker()
        self.assertTrue(c.is_reportable_update("1.43.3.10861", "1.43.3.10896"))

    def test_plex_build_bump_is_classified_not_dismissed(self):
        """It used to render as 'Versions appear equal' — a real update
        described as a non-event."""
        c = _checker()
        result = c.assess_update_complexity("1.43.3.10861", "1.43.3.10896")
        self.assertEqual(result["type"], "patch")
        self.assertNotIn("appear equal", result["description"])

    def test_plex_build_downgrade_is_not_reportable(self):
        c = _checker()
        self.assertFalse(c.is_reportable_update("1.43.3.10896", "1.43.3.10861"))

    def test_identical_four_component_tags(self):
        c = _checker()
        self.assertFalse(c.is_reportable_update("1.43.3.10896", "1.43.3.10896"))


class PadHelperTest(unittest.TestCase):

    def test_pads_to_longer_side(self):
        self.assertEqual(
            _mod._pad_to_same_length((1, 38), (1, 38, 3, 4)),
            ((1, 38, 0, 0), (1, 38, 3, 4)))

    def test_minimum_floor_guarantees_unpackable_arity(self):
        a, b = _mod._pad_to_same_length((3, 11), (3,), minimum=3)
        self.assertEqual(len(a), 3)
        self.assertEqual(len(b), 3)

    def test_never_truncates(self):
        a, b = _mod._pad_to_same_length((1, 43, 3, 10896), (1, 43), minimum=3)
        self.assertEqual(a, (1, 43, 3, 10896))
        self.assertEqual(b, (1, 43, 0, 0))


class CrashVetoTest(unittest.TestCase):
    """A crash must not be scored as a completed run.

    sweep-run.py treats rc in (0, 1, 2) as "ran to completion", and an
    uncaught traceback exits 1. main() must therefore return a code OUTSIDE
    that set, and __main__ must actually propagate it.
    """

    def test_main_exit_code_is_propagated(self):
        src = open(_SCRIPT).read()
        self.assertIn("sys.exit(main() or 0)", src,
                      "bare main() discards the crash veto's exit code")

    def test_crash_path_returns_a_code_sweep_run_calls_a_crash(self):
        src = open(_SCRIPT).read()
        self.assertIn("return 3", src)
        self.assertNotIn("\n        return 1\n", src.split("def main(")[-1],
                         "rc 1 is indistinguishable from 'found findings'")


if __name__ == "__main__":
    unittest.main(verbosity=2)
