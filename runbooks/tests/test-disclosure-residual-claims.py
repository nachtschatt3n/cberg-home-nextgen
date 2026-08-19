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

    def test_tooling_talk_acquitted_only_by_a_script_path(self):
        # A commit editing the scanner must be able to name what it matches on
        # — but the acquittal is now keyed on a FILE PATH, which an author
        # cannot emit by accident.
        self.assertAllowed(
            "fix(security-check): stop counting kernel-header packages as "
            "fixable criticals in security-check.py"
        )

    def test_bare_scope_no_longer_acquits(self):
        # Regression for the forgeable-acquittal finding: the conventional
        # commit SCOPE used to clear the residual tier, which handed a free
        # pass to exactly the commits most likely to carry a residual claim.
        hits = dp.scan(norm(
            "fix(security): fixable CRITICAL driver still present on the edge image"
        ))
        self.assertTrue(hits, "a bare fix(security) scope must NOT acquit")

    def test_explicit_trailer_waives_residual_tier_only(self):
        body = ("fix(security-check): rework the fix-availability vocabulary\n\n"
                "Counts fixable criticals differently now.\n\n"
                "disclosure-review: tooling-edit")
        # Trailer is multiline-anchored, so scan the RAW text, not normalized.
        self.assertFalse(dp.scan(body), "trailer should waive the residual tier")
        # ...and the commit-msg hook scans a whitespace-JOINED message, where
        # the line anchor can never match. That made the sanctioned opt-out
        # inert in the only place it is used while this test stayed green, so
        # assert the hook's actual call shape too.
        joined = re.sub(r"\s+", " ", " ".join(body.splitlines())).strip()
        self.assertTrue(dp.scan(joined),
                        "a joined message must not self-detect the trailer")
        self.assertFalse(dp.scan(joined, waived=True),
                         "an explicitly-waived joined message still blocked")
        self.assertTrue(dp.scan(re.sub(r"\s+", " ", " ".join(
            body.replace("Counts fixable criticals differently now.",
                         "Fixes handling of CVE-2026-99999.").splitlines())),
            waived=True), "waived=True must NOT waive a CVE identifier")
        # ...but never the hard tier.
        hard = body.replace("Counts fixable criticals differently now.",
                            "Fixes handling of CVE-2026-99999.")
        self.assertTrue(dp.scan(hard),
                        "trailer must NOT waive a CVE identifier")


class AdversarialBypassesStayClosed(unittest.TestCase):
    """Every case here defeated an earlier version of the residual tier.

    Found by an adversarial review of the first patch (2026-08-19), not by the
    author. Each one is a reminder that this tier is a phrase list: it catches
    careless disclosure, not fluent paraphrase.
    """

    def assertBlocked(self, text):
        self.assertTrue(dp.scan(norm(text)), f"BYPASS regressed: {text!r}")

    def test_conventional_commit_scope_does_not_acquit(self):
        self.assertBlocked(
            "fix(security): fixable CRITICAL driver still present on the edge image")

    def test_false_positive_phrase_does_not_acquit(self):
        # "Not a false positive: ..." is what an honest author writes, and the
        # first acquittal list treated it as proof of tooling context.
        self.assertBlocked(
            "Not a false positive: the fixable CRITICAL driver is still present.")

    def test_neighbouring_reopen_sentence_does_not_acquit(self):
        self.assertBlocked(
            "Does not close F-31327aa9. Nothing was reopened; the driver is unchanged.")

    def test_unrelated_closure_sentence_does_not_acquit(self):
        self.assertBlocked(
            "Clears the last lint warning. F-31327aa9 does not close yet.")

    def test_full_paraphrase_of_the_original_breach(self):
        # Blocked via the negated-closure + upstream rules ("is not fixed by
        # this release", "has yet to ship").
        self.assertBlocked(
            "The bundled npm dependency is not fixed by this release; the "
            "driver persists and upstream has yet to ship a corrected "
            "library. F-31327aa9 is carried forward to the next cycle.")

    def test_bare_persistence_synonyms_WARN_but_do_not_block(self):
        """Deliberate, measured limitation — see SOP §2.4.

        A residual claim carrying NO negation and NO scanner vocabulary is
        only warned about. `persist`/`pending`/`issue`/`gap` are too common in
        ordinary engineering prose to gate on: they produced 15 of 25 flips
        over 4841 commit messages, mostly `persist` in its database sense.
        This test exists so the limitation is explicit rather than discovered.
        """
        for t in [
            "F-1234abcd remains as recorded.",
            "The issue is still unresolved.",
            "The gap awaits an upstream release.",
            "F-1234abcd is carried forward.",
        ]:
            with self.subTest(t=t):
                n = norm(t)
                self.assertFalse(dp.scan(n), f"should not BLOCK: {t!r}")
                self.assertTrue(dp.scan_warn(n), f"should WARN: {t!r}")

    def test_does_not_address_the_issue(self):
        # `issue`/`gap` were accepted by the left-open rule but not by the
        # negated-closure rules — an inconsistency a paraphrase walked through.
        self.assertBlocked("This does not address the issue.")


class SopPublishableExploitability(unittest.TestCase):
    """SOP §2.1 publishes the DEFERRAL phrasing; the rule used to reject it."""

    def test_deferral_phrasing_allowed(self):
        self.assertFalse(dp.scan(norm(
            "Exploitability assessed on the finding record.")))

    def test_actual_assessment_still_blocked(self):
        self.assertTrue(dp.scan(norm(
            "Real-world exploitability is low because the binary is not "
            "network-reachable.")))


class WarnTierNeverGates(unittest.TestCase):
    """The bare-semver rule caught 30 of 39 new hits on ordinary bump prose."""

    def test_bare_semver_prose_warns_but_does_not_block(self):
        t = norm("fix(elasticsearch): bump 8.19.15 -> 8.19.20 (CVE blind-spot plan)")
        self.assertFalse(dp.scan(t), "bare-semver prose must not BLOCK")
        self.assertTrue(dp.scan_warn(t), "bare-semver prose should still WARN")

    def test_warn_tier_is_separate_from_block_tier(self):
        self.assertTrue(hasattr(dp, "scan_warn"))
        self.assertNotEqual(id(dp._COMPILED3), id(dp._COMPILED3_WARN))


class PersistsWordBoundaries(unittest.TestCase):
    """PERSISTS had no \\b, so `pending` matched inside ordinary English.

    Reproduced 2026-08-19: "suspending", "depending" and "appending" all fired
    the residual rule. `suspend` is core maintenance-plan vocabulary — and this
    tier BLOCKS a commit — so it was rejecting exactly the commits that get
    written most during a maintenance window.
    """

    def test_pending_does_not_match_inside_a_longer_word(self):
        for word in ("suspending", "depending", "appending", "impending"):
            t = norm("fix(maintenance): %s the HelmRelease so the finding stays put" % word)
            hits = [h for h in dp.scan(t) if "residual" in h[1].lower()]
            self.assertFalse(hits, "%r must not trip the residual rule" % word)

    def test_pending_still_matches_as_its_own_word(self):
        self.assertTrue(re.search(dp.PERSISTS, "pending operator approval", re.I))

    def test_suspend_vocabulary_survives_next_to_a_finding_anchor(self):
        t = norm("fix(plan): suspend both the HelmRelease and the Kustomization "
                 "so the finding's quiesce actually holds")
        self.assertFalse(dp.scan(t), "suspend-vocabulary must not BLOCK a commit")


class PersistsStillCarries(unittest.TestCase):
    """`still (carries|contains|holds|retains)` was not covered.

    Only `still (there|present|open|unfixed)` was, so a commit saying a retained
    artefact "still carries the old value" scanned clean (2026-08-19).
    """

    def test_still_carries_family_is_matched(self):
        for phrase in ("still carries the old value",
                       "still contains the hash",
                       "still holds the placeholder",
                       "still retains the old credential"):
            self.assertTrue(re.search(dp.PERSISTS, phrase, re.I), phrase)

    def test_overly_generic_forms_deliberately_excluded(self):
        # `still has` / `still uses` are too generic for a blocking rule.
        for phrase in ("still has three steps", "still uses the same chart"):
            self.assertFalse(re.search(dp.PERSISTS, phrase, re.I), phrase)


class LibraryContract(unittest.TestCase):
    """Both hooks import this module; keep the exported shape stable."""

    def test_back_compat_two_tuple_export(self):
        for entry in dp.COMPILED:
            self.assertEqual(len(entry), 2)

    def test_every_rule_compiles_and_is_labelled(self):
        for rx, label, _acq, _win in dp._COMPILED3 + dp._COMPILED3_WARN:
            self.assertTrue(label and isinstance(label, str))
            self.assertTrue(hasattr(rx, "search"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
