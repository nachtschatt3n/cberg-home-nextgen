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

    def test_severity_word_does_not_match_inside_a_longer_word(self):
        """SEV had the same missing \\b that PERSISTS did (found 2026-09-21).

        SEV bounded only its right edge with (?![-\\w]), so `low` matched inside
        "below", "allowlist" and "shallow" when a residual verb followed within
        four tokens. Found when the hook flagged a plan commit reading "Nothing
        below is deleted. It remains the reasoning this decision overrode" --
        prose about preserving a recommendation block, on a plan whose
        security_ref is null.

        NOTE ON THE ASSERTION SHAPE: scan() returns (match, MATCHED TEXT), not a
        rule label -- e.g. ('...', 'low is deleted. It remains'). An earlier
        version of this test filtered on "residual" in the second element and so
        could never be true for any input, passing and failing for the wrong
        reason. Assert on scan() directly, as the suspend-vocabulary test below
        already does.
        """
        for t in ("Nothing below is deleted. It remains the reasoning this decision overrode",
                  "the allowlist below remains unchanged",
                  "a shallow copy remains in place",
                  "the row below is deleted; the note remains for context"):
            self.assertFalse(dp.scan(norm(t)),
                             "%r must not block a commit" % t)

    def test_severity_words_still_match_as_their_own_word(self):
        """The other direction: the boundary must not blunt the rule it guards."""
        for t in ("3 CRITICAL are deleted. It remains exposed until upstream ships",
                  "one critical remains on that image",
                  "two high findings are still open"):
            self.assertTrue(dp.scan(norm(t)),
                            "%r must still block a commit" % t)

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


# ── 2026-09-22: three verified gaps (F-c2e3d6de, F-c1537a4e, F-a1b6c39b) ──
# Every fixture below is ASSEMBLED from these placeholders at runtime. None is
# a real CVE id, a real domain, a real finding id, or a real per-image count.
SVC = "exampleapp"
IMG = "example-org/widget:" + "1.2.3"
COUNT = str(1 + 2)


def scan_without(text, label):
    """COMMISSIONING STRAW: scan with every rule carrying `label` removed.

    A widening is load-bearing only if its positive fixture scans CLEAN
    without it -- otherwise the assertion passes on the strength of some other
    rule and proves nothing about the new one.
    """
    return dp._scan(norm(text), [r for r in dp._COMPILED3 if r[1] != label])


def scan_warn_without(text, label):
    return dp._scan(norm(text), [r for r in dp._COMPILED3_WARN if r[1] != label])


class MissingControlBlocked(unittest.TestCase):
    """F-c2e3d6de: a security control asserted ABSENT on a surface we run.

    "no rate limit protects X", "nothing throttles Y", "no lockout on Z" carry
    no vulnerability word, no count and no image, so every earlier tier
    returned [] and the commit-msg hook exited 0 -- reproduced 2026-09-22 with
    dp.scan() against the frozen library before the rule existed.
    """
    LABEL = "residual claim — missing control"
    POSITIVE = [
        "no rate limit protects the %s login endpoint" % SVC,
        "nothing throttles the %s token endpoint" % SVC,
        "no lockout on the %s admin accounts" % SVC,
        "there is no throttling in place for the %s api" % SVC,
        "nothing protects the %s admin dashboard" % SVC,
    ]
    NEGATIVE = [
        # Past tense: the commit that ADDS the control describes the past.
        "no rate limit protected the %s endpoint; this commit adds one" % SVC,
        # Design statements, not gaps.
        "the healthz probe needs no auth for the %s endpoint" % SVC,
        "no auth at the %s gateway level is needed" % SVC,
        # A locked account is hardening -- measured on a real plan file.
        "no usable password on the %s service user" % SVC,
        # Tooling talk: a build gate is not a security control.
        "nothing gates the apply on the check; the gate now blocks",
        # Closed in the same message.
        "no lockout on the %s admin accounts until now; this change enforces one" % SVC,
    ]

    def test_positive_fixtures_block(self):
        for t in self.POSITIVE:
            with self.subTest(t=t):
                self.assertIn(self.LABEL, [h[2] for h in dp.scan(norm(t))], t)

    def test_negative_fixtures_stay_clean(self):
        for t in self.NEGATIVE:
            with self.subTest(t=t):
                self.assertFalse(dp.scan(norm(t)), "must not block: %r" % t)

    def test_straw_pattern_is_load_bearing(self):
        for t in self.POSITIVE:
            with self.subTest(t=t):
                self.assertFalse(scan_without(t, self.LABEL),
                                 "another rule already carries %r" % t)

    def test_residual_tier_waiver_covers_it(self):
        self.assertFalse(dp.scan(norm(self.POSITIVE[0]), waived=True))


class StillCarriedBlocked(unittest.TestCase):
    """F-c1537a4e: "image X still carries criticals" and its family.

    PERSISTS has matched `still carries` since 2026-08-19, but only in the WARN
    tier and only next to FINDING_ANCHOR_WIDE. A bare scanner plural is not an
    anchor there, so "the image still carries criticals" neither warned nor
    blocked (reproduced 2026-09-22).
    """
    LABEL = "residual claim — still carried"
    POSITIVE = [
        "the %s image still carries criticals" % SVC,
        "the %s image still ships the CVE from its base layer" % SVC,
        "the %s runtime still has vulns after the rebuild" % SVC,
        "the CVE is still present on the base image",
        "criticals are still there after the rebuild",
    ]
    NEGATIVE = [
        "the %s image still carries no criticals" % SVC,        # closed gap
        "the %s image still has high latency" % SVC,           # bare adjective
        "the %s chart still contains the old values" % SVC,    # no vuln noun
        "the retained rollback datadir still carries the old value",
    ]

    def test_positive_fixtures_block(self):
        for t in self.POSITIVE:
            with self.subTest(t=t):
                self.assertIn(self.LABEL, [h[2] for h in dp.scan(norm(t))], t)

    def test_negative_fixtures_stay_clean(self):
        for t in self.NEGATIVE:
            with self.subTest(t=t):
                self.assertFalse(dp.scan(norm(t)), "must not block: %r" % t)

    def test_straw_pattern_is_load_bearing(self):
        for t in self.POSITIVE:
            with self.subTest(t=t):
                self.assertFalse(scan_without(t, self.LABEL),
                                 "another rule already carries %r" % t)


class ImageAdjacencyNeedsARealToken(unittest.TestCase):
    """The image rules paired IMAGE_REF with full VULN, so a bare severity word
    within 80 chars of a SYNTHETIC tag -- a counted-severity test fixture, the
    exact shape the policy asks authors to write -- blocked (2026-09-22). The
    counted rule compounded it: the tag's trailing digit read as a count
    ("1.2.3 for high").
    """
    IMAGE_LABEL = "vulnerability state tied to a named image"
    COUNTED_LABEL = "counted vulnerability phrasing"
    NEGATIVE = [
        '("%s", "high", %s)' % (IMG, COUNT),
        "%s produced a high error count in the fixture" % IMG,
        "%s runs at low priority in the test fixture" % IMG,
        "chore(app): bump to 1.2.3 for high availability",
        "| `%s` (cache only) | medium | 45 m |" % IMG,
    ]

    def test_bare_severity_near_an_image_is_not_evidence(self):
        for t in self.NEGATIVE:
            with self.subTest(t=t):
                self.assertFalse(dp.scan(norm(t)), "must not block: %r" % t)

    def test_real_token_near_an_image_still_blocks(self):
        t = "%s carries a known advisory in its base layer" % IMG
        self.assertIn(self.IMAGE_LABEL, [h[2] for h in dp.scan(norm(t))])
        self.assertFalse(scan_without(t, self.IMAGE_LABEL), "straw: rule not load-bearing")

    def test_counted_severity_near_an_image_blocks_via_the_count(self):
        t = "%s carries %s criticals" % (IMG, COUNT)
        labels = [h[2] for h in dp.scan(norm(t))]
        self.assertIn(self.COUNTED_LABEL, labels)
        self.assertNotIn(self.IMAGE_LABEL, labels, "the count carries it, not the adjacency")
        self.assertFalse(scan_without(t, self.COUNTED_LABEL), "straw: rule not load-bearing")

    def test_count_reaches_across_a_version_token(self):
        # Measured: "3 unfixable v1.15.1 criticals" was only ever caught by the
        # tag digit; the real count could not cross the dotted token.
        t = "%s unfixable v1.15.1 criticals accepted on %s" % (COUNT, SVC)
        hits = [h for h in dp.scan(norm(t)) if h[2] == self.COUNTED_LABEL]
        self.assertTrue(hits, "count must still block")
        self.assertTrue(hits[0][1].startswith(COUNT + " "),
                        "the COUNT must carry the match, not the tag digit: %r" % hits[0][1])
        self.assertFalse(scan_without(t, self.COUNTED_LABEL), "straw: rule not load-bearing")

    def test_version_slack_does_not_cross_a_sentence(self):
        t = "review again after 30 days. With criticals the plan is kept"
        self.assertFalse([h for h in dp.scan(norm(t)) if h[2] == self.COUNTED_LABEL],
                         '"days." is not a version token')


class DetectionCoverageBlocked(unittest.TestCase):
    """F-a1b6c39b: what our monitoring does NOT see, next to a security event.

    Modelled on the 2026-09-09 commit body (left in history as it is):
    "authentication that succeeds is invisible", "none of the notification
    rules matches action: login", "cannot correlate ... burst-from-one-IP".
    dp.scan() returned [] on all of it (reproduced 2026-09-22).
    """
    LABEL = "residual claim — detection coverage"
    WARN_LABEL = "possible detection-coverage statement"
    POSITIVE = [
        "we cannot detect a successful login to %s from a new address" % SVC,
        "no alert fires when a brute-force burst hits %s" % SVC,
        "authentication that succeeds on %s is invisible to the SIEM" % SVC,
        "none of the notification rules matches a login on %s" % SVC,
        "the indexer never correlates by client ip, so an attacker on %s goes unnoticed" % SVC,
    ]
    NEGATIVE = [
        # Tooling talk about the scanner itself.
        "the hook cannot detect a paraphrase of the residual claim",
        # An ops gap: WARN-only (asserted below), never a block.
        "no alert fires when the %s rollover stalls" % SVC,
        # `login` the page, `log in` the verb.
        "we cannot see the login page of %s on mobile" % SVC,
        "we cannot log in to %s after the upgrade" % SVC,
        # Past tense: the commit that adds the rule describes the past.
        "we could not detect a failed login on %s before this rule" % SVC,
        # Measured noise: adversarial review, the Authorization HEADER, a
        # registry status.
        "a blind spot in the code; re-attacking adversarially found it",
        "only Host and Authorization are forwarded, so the outpost cannot see the session",
        "trivy reports UNAUTHORIZED -> UNKNOWN, a coverage blind spot",
        # Closed in the same message.
        "a brute-force burst on %s is no longer invisible: this rule adds the decoder" % SVC,
    ]

    def test_positive_fixtures_block(self):
        for t in self.POSITIVE:
            with self.subTest(t=t):
                self.assertIn(self.LABEL, [h[2] for h in dp.scan(norm(t))], t)

    def test_negative_fixtures_stay_clean(self):
        for t in self.NEGATIVE:
            with self.subTest(t=t):
                self.assertFalse(dp.scan(norm(t)), "must not block: %r" % t)

    def test_straw_pattern_is_load_bearing(self):
        for t in self.POSITIVE:
            with self.subTest(t=t):
                self.assertFalse(scan_without(t, self.LABEL),
                                 "another rule already carries %r" % t)

    def test_generic_shape_warns_only_next_to_a_monitor(self):
        ops = norm("no alert fires when the %s rollover stalls" % SVC)
        self.assertFalse(dp.scan(ops))
        self.assertIn(self.WARN_LABEL, [h[2] for h in dp.scan_warn(ops)])
        self.assertFalse(scan_warn_without(ops, self.WARN_LABEL), "straw: warn rule not load-bearing")
        scanner = norm("trivy cannot see private images, a scan blind spot")
        self.assertFalse(dp.scan(scanner))
        self.assertIn(self.WARN_LABEL, [h[2] for h in dp.scan_warn(scanner)])
        # No monitor word anywhere: neither tier. This repo says "cannot
        # detect" about its own tooling constantly.
        tooling = norm("the hook cannot detect a paraphrase of the residual claim")
        self.assertFalse(dp.scan(tooling))
        self.assertFalse(dp.scan_warn(tooling))

    def test_existing_blind_spot_fixture_still_does_not_block(self):
        # WarnTierNeverGates already asserts this one; it is repeated here
        # because `blind spot` is now a coverage anchor and this is the fixture
        # a careless widening would break.
        self.assertFalse(dp.scan(norm(
            "fix(elasticsearch): bump 8.19.15 -> 8.19.20 (CVE blind-spot plan)")))


class CommitMsgHookEndToEnd(unittest.TestCase):
    """F-c2e3d6de was an EXIT CODE (commit-msg exited 0), so assert the hook,
    not only the library. Runs `.githooks/commit-msg` on a temp file the way
    git does; the hook resolves GITHOOKS_DIR from its own path.
    """
    HOOK = os.path.join(_HERE, "..", "..", ".githooks", "commit-msg")

    def _run(self, message):
        import subprocess
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".msg", delete=False) as fh:
            fh.write(message)
            path = fh.name
        try:
            return subprocess.run(["bash", self.HOOK, path],
                                  capture_output=True, text=True)
        finally:
            os.unlink(path)

    def test_missing_control_message_is_rejected(self):
        r = self._run("fix(%s): tighten the login flow\n\n"
                      "no rate limit protects the %s login endpoint\n" % (SVC, SVC))
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("missing control", r.stderr)

    def test_detection_coverage_message_is_rejected(self):
        r = self._run("docs(plan): note the edge gap\n\n"
                      "authentication that succeeds on %s is invisible\n"
                      "to the SIEM today.\n" % SVC)
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("detection coverage", r.stderr)

    def test_still_carried_message_is_rejected(self):
        r = self._run("chore(%s): rebuild\n\nthe %s image still carries\n"
                      "criticals after the rebuild.\n" % (SVC, SVC))
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("still carried", r.stderr)

    def test_version_tail_near_a_severity_word_is_accepted(self):
        r = self._run("chore(app): bump to 1.2.3 for high availability\n\n"
                      "Patch release, no breaking changes upstream.\n")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_ops_coverage_gap_is_advisory_only(self):
        r = self._run("fix(alerts): note the gap\n\n"
                      "no alert fires when the %s rollover stalls\n" % SVC)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("advisory", r.stderr)


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
