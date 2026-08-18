#!/usr/bin/env python3
"""Regression tests for the residual-claim tier in .githooks/lib/disclosure_patterns.py.

Guards the 2026-08-18 miss: every rule in the library required a NUMBER, a
QUANTIFIER or an IMAGE_REF to fire, so a purely QUALITATIVE residual claim
("does not close F-xxxxxxxx", "the finding stays open", "ships it unchanged")
matched nothing and reached a public commit body. The residual rules key on
the CLAIM SHAPE instead.

The other half of these tests is just as important: the SOP (§2.1) explicitly
PUBLISHES closed-gap statements and supply-chain facts. A hook that blocks
honest commits gets bypassed with --no-verify, and a bypassed hook protects
nothing — so the acquittal cases below are load-bearing, not decoration.

Fixtures are SYNTHETIC. Real counts/CVE IDs for unfixed issues are DB-only
(docs/sops/vulnerability-disclosure.md).

Run: python3 runbooks/tests/test-disclosure-residual-claims.py
"""

import importlib.util
import os
import re
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_LIB = os.path.join(_HERE, "..", "..", ".githooks", "lib", "disclosure_patterns.py")
_spec = importlib.util.spec_from_file_location("disclosure_patterns", _LIB)
dp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dp)


def norm(t):
    """Callers normalize whitespace before scanning; mirror that here."""
    return re.sub(r"\s+", " ", t).strip()


class ResidualClaimsBlocked(unittest.TestCase):
    """Qualitative residual claims — no count, no image ref — must BLOCK."""

    def assertBlocked(self, text):
        hits = dp.scan(norm(text))
        self.assertTrue(hits, f"expected a block, got none for: {text!r}")

    def test_the_actual_2026_08_18_breach(self):
        # Verbatim shape of the commit body that reached origin/main.
        self.assertBlocked(
            "Does NOT close F-31327aa9: the finding's fixable-CRITICAL driver "
            "is a bundled npm dependency that 0.27.4 ships unchanged. The "
            "finding stays open with that reason recorded."
        )

    def test_negated_closure_variants(self):
        for t in [
            "This does not close F-1234abcd.",
            "The bump won't clear the advisory.",
            "Cannot fix the CVE without an upstream release.",
            "This fails to resolve the finding.",
            "F-1234abcd is not closed by this change.",
        ]:
            with self.subTest(t=t):
                self.assertBlocked(t)

    def test_finding_left_open(self):
        for t in [
            "The finding stays open.",
            "F-1234abcd remains open for now.",
            "The advisory is still open upstream.",
        ]:
            with self.subTest(t=t):
                self.assertBlocked(t)

    def test_fixable_vocabulary_without_a_count(self):
        # "fixable CRITICAL" with no number in front is scanner vocabulary
        # asserting live unfixed state.
        for t in [
            "Reduces the fixable-CRITICAL surface on this image.",
            "There are fixable criticals left on the runtime image.",
        ]:
            with self.subTest(t=t):
                self.assertBlocked(t)

    def test_upstream_has_not_shipped_a_fix(self):
        for t in [
            "The CVE is in a bundled dependency that upstream ships unchanged.",
            "The vulnerability persists because the dependency has not been refreshed.",
        ]:
            with self.subTest(t=t):
                self.assertBlocked(t)


class PublishableStaysPublishable(unittest.TestCase):
    """SOP §2.1 allows these. Blocking them would drive --no-verify."""

    def assertAllowed(self, text):
        hits = dp.scan(norm(text))
        self.assertFalse(hits, f"expected NO block, got {hits!r} for: {text!r}")

    def test_zero_is_a_closed_gap(self):
        # Named verbatim in the SOP as publishable.
        self.assertAllowed("post-rebuild: 0 fixable CRITICAL")

    def test_closed_gap_phrasings(self):
        for t in [
            "Clears the last fixable CRITICAL on the production image.",
            "Rolls onto the build with no fixable criticals left.",
        ]:
            with self.subTest(t=t):
                self.assertAllowed(t)

    def test_plain_supply_chain_facts(self):
        for t in [
            "fix(affine): bump 0.27.3 -> 0.27.4",
            "chore(postgres): re-pin 17.11-alpine to the current upstream build",
            "Upstream stable release; bumps both containers to the same tag.",
        ]:
            with self.subTest(t=t):
                self.assertAllowed(t)

    def test_sanctioned_reference_form(self):
        self.assertAllowed("Security driver, tracked as F-31327aa9.")
        self.assertTrue(dp.SECURITY_REF_LINE.match("security_ref: F-31327aa9"))

    def test_scanner_tooling_talk_is_acquitted(self):
        # A commit editing the scanner must be able to name what it matches on.
        self.assertAllowed(
            "fix(security-check): stop counting kernel-header packages as "
            "fixable criticals"
        )


class WarnTierNeverGates(unittest.TestCase):
    """The bare-semver rule caught 30 of 39 new hits on ordinary bump prose."""

    def test_bare_semver_prose_warns_but_does_not_block(self):
        t = norm("fix(elasticsearch): bump 8.19.15 -> 8.19.20 (CVE blind-spot plan)")
        self.assertFalse(dp.scan(t), "bare-semver prose must not BLOCK")
        self.assertTrue(dp.scan_warn(t), "bare-semver prose should still WARN")

    def test_warn_tier_is_separate_from_block_tier(self):
        self.assertTrue(hasattr(dp, "scan_warn"))
        self.assertNotEqual(id(dp._COMPILED3), id(dp._COMPILED3_WARN))


class LibraryContract(unittest.TestCase):
    """Both hooks import this module; keep the exported shape stable."""

    def test_back_compat_two_tuple_export(self):
        for entry in dp.COMPILED:
            self.assertEqual(len(entry), 2)

    def test_every_rule_compiles_and_is_labelled(self):
        for rx, label, _acq in dp._COMPILED3 + dp._COMPILED3_WARN:
            self.assertTrue(label and isinstance(label, str))
            self.assertTrue(hasattr(rx, "search"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
