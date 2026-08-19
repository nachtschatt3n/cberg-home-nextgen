#!/usr/bin/env python3
"""Regression tests for security-check.tally_trivy_report.

Guards the 2026-08-18 kernel-header fix: `linux-libc-dev` (and the other
header-only OS packages) ship /usr/include/linux and nothing executable, so
the kernel CVEs Trivy attaches to them describe the RUNNING kernel — which on
this cluster is the Talos node kernel, never the image's distro kernel. They
were dominating the fixable-CRITICAL tally on every Ubuntu/Debian-based image
and were not even remediable by the bump that tally implies (the same header
version is pinned in newer upstream builds of the same image).

Fixtures here are SYNTHETIC on purpose — real per-image counts and CVE IDs for
unfixed issues are DB-only (docs/sops/vulnerability-disclosure.md).

Run: python3 runbooks/tests/test-trivy-tally.py
"""

import importlib.util
import os
import unittest

os.environ.setdefault("_MISE_ACTIVATED", "1")  # skip the mise re-exec on import

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPT = os.path.join(_HERE, "..", "security-check.py")
_spec = importlib.util.spec_from_file_location("security_check", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

tally = _mod.tally_trivy_report


def _vuln(vid, pkg, sev, fixed=None, installed=None, published=None):
    v = {"VulnerabilityID": vid, "PkgName": pkg, "Severity": sev}
    if fixed:
        v["FixedVersion"] = fixed
    if installed:
        v["InstalledVersion"] = installed
    if published:
        v["PublishedDate"] = published
    return v


def _report(*results, artifact=None):
    r = {"Results": [{"Class": cls, "Vulnerabilities": vulns}
                     for cls, vulns in results]}
    if artifact:
        r["ArtifactName"] = artifact
    return r


def _pseudo(ts, rev="0123456789ab"):
    """A Go pseudo-version stamped at commit time `ts` (YYYYMMDDHHMMSS)."""
    return f"v0.0.0-{ts}-{rev}"


class KernelHeaderExclusionTest(unittest.TestCase):
    def test_kernel_headers_dropped_from_fixable_tally(self):
        """The scrypted shape: many header criticals, a few real lang-pkg ones."""
        r = tally(_report(
            ("os-pkgs", [_vuln(f"TEST-K-{i}", "linux-libc-dev", "CRITICAL", "6.8.0-88.89")
                         for i in range(22)]
                        + [_vuln(f"TEST-KH-{i}", "linux-libc-dev", "HIGH", "6.8.0-88.89")
                           for i in range(264)]),
            ("lang-pkgs", [_vuln(f"TEST-T-{i}", "tar", "CRITICAL", "7.5.3")
                           for i in range(4)]),
        ))
        self.assertEqual(r["crit_fix"], 4)
        self.assertEqual(r["high_fix"], 0)
        self.assertEqual(len(r["fix_ids"]), 4)
        self.assertTrue(all(i.startswith("TEST-T-") for i in r["fix_ids"]))

    def test_genuine_os_criticals_still_counted(self):
        """The control shape: openssl/gnutls-class findings must be untouched."""
        r = tally(_report(("os-pkgs", [
            _vuln("TEST-A", "libssl3", "CRITICAL", "3.0.18"),
            _vuln("TEST-B", "libgnutls30", "CRITICAL", "3.7.10"),
            _vuln("TEST-C", "openssl", "HIGH", "3.0.18"),
            _vuln("TEST-D", "linux-libc-dev", "CRITICAL", "6.1.149-1"),
        ])))
        self.assertEqual(r["crit_fix"], 2)
        self.assertEqual(r["high_fix"], 1)

    def test_header_variants_and_prefixes_excluded(self):
        r = tally(_report(("os-pkgs", [
            _vuln("TEST-E", "kernel-headers", "CRITICAL", "6.12.1"),
            _vuln("TEST-F", "linux-headers-6.8.0-87", "CRITICAL", "6.8.0-88"),
            _vuln("TEST-G", "linux-libc-dev", "CRITICAL", "6.8.0-88"),
            _vuln("TEST-H", "curl", "CRITICAL", "8.15.0"),
        ])))
        self.assertEqual(r["crit_fix"], 1)

    def test_exclusion_is_os_pkgs_only(self):
        """A lang-pkg that happens to share the name is a different artifact."""
        r = tally(_report(("lang-pkgs", [
            _vuln("TEST-I", "linux-libc-dev", "CRITICAL", "1.0.0"),
        ])))
        self.assertEqual(r["crit_fix"], 1)

    def test_nofix_side_untouched(self):
        """Deliberately narrow: no-fix headers still count (AR-029 context only)."""
        r = tally(_report(("os-pkgs", [
            _vuln("TEST-J", "linux-libc-dev", "CRITICAL"),
            _vuln("TEST-K", "linux-libc-dev", "HIGH"),
        ])))
        self.assertEqual(r["crit_fix"], 0)
        self.assertEqual(r["crit_nofix"], 1)
        self.assertEqual(r["high_nofix"], 1)

    def test_header_only_image_is_not_silently_clean(self):
        """All-fixable-headers image returns None (nothing to report), not a
        zeroed dict that would look like a scanned-and-clean result."""
        self.assertIsNone(tally(_report(("os-pkgs", [
            _vuln("TEST-L", "linux-libc-dev", "CRITICAL", "6.8.0-88"),
        ]))))

    def test_clean_report_returns_none(self):
        self.assertIsNone(tally({"Results": []}))

    def test_medium_and_low_ignored(self):
        r = tally(_report(("os-pkgs", [
            _vuln("TEST-M", "zlib1g", "MEDIUM", "1.3"),
            _vuln("TEST-N", "zlib1g", "CRITICAL", "1.3"),
        ])))
        self.assertEqual(r["crit_fix"], 1)
        self.assertEqual(r["fix_ids"], ["TEST-N"])

    def test_cve_ids_deduped(self):
        r = tally(_report(("os-pkgs", [
            _vuln("TEST-O", "libssl3", "CRITICAL", "3.0.18"),
            _vuln("TEST-O", "libssl3", "CRITICAL", "3.0.18"),
        ])))
        self.assertEqual(r["crit_fix"], 2)      # two findings
        self.assertEqual(r["fix_ids"], ["TEST-O"])  # one id


class GoPseudoVersionTest(unittest.TestCase):
    """Guards the 2026-08-19 fix: a Go pseudo-version carries no comparable
    version, so comparing its `v0.0.0` placeholder base against a real release
    is arithmetic without meaning and must not be counted as a fixable CVE.

    Two SHAPES matter and pull in opposite directions, which is why a blanket
    "ignore pseudo-versions" rule would be wrong: a binary stamped with a
    pseudo-version for its OWN main module is usually current, while a
    DEPENDENCY pinned at an old commit is usually genuinely behind its fix and
    must keep counting. The routes below decide which, or decline.

    Fleet measurements, affected image names and per-image counts are DB-only
    (docs/sops/vulnerability-disclosure.md) — see security_ref F-9e1e421c.
    Fixtures here are SYNTHETIC.
    """

    # -- Route A: the module IS the image's own program -----------------------

    def test_main_module_tag_at_or_past_fix_is_not_fixable(self):
        """Image tag 1.14.7 >= fix 1.14.3 -> the fix is already present."""
        r = tally(_report(
            ("lang-pkgs", [_vuln("TEST-P-1", "example.org/acme/dnsd", "HIGH",
                                 "1.14.3", _pseudo("20260819003913"))]),
            artifact="acme/dnsd:1.14.7"))
        self.assertIsNone(r)

    def test_main_module_tag_behind_fix_stays_fixable(self):
        """The route must be able to CONFIRM a finding, not only clear one."""
        r = tally(_report(
            ("lang-pkgs", [_vuln("TEST-P-2", "example.org/acme/dnsd", "HIGH",
                                 "1.15.0", _pseudo("20260819003913"))]),
            artifact="acme/dnsd:1.14.7"))
        self.assertEqual(r["high_fix"], 1)
        self.assertEqual(r["high_undet"], 0)

    def test_main_module_major_suffix_stripped(self):
        """`github.com/org/app/v3` is still the program in `org/app:3.1.0`."""
        r = tally(_report(
            ("lang-pkgs", [_vuln("TEST-P-3", "github.com/org/app/v3", "CRITICAL",
                                 "3.0.9", _pseudo("20260101000000"))]),
            artifact="org/app:3.1.0"))
        self.assertIsNone(r)

    def test_dependency_module_does_not_borrow_the_image_tag(self):
        """A dependency is not the program, so the image tag says nothing about
        it. Route A must decline (here it falls through to route C)."""
        r = tally(_report(
            ("lang-pkgs", [_vuln("TEST-P-4", "example.org/dep/netlib", "HIGH",
                                 "0.55.0", _pseudo("20200625001655"),
                                 "2026-05-22T16:16:19Z")]),
            artifact="example.org/vendor/exporter:0.8.0"))
        self.assertEqual(r["high_fix"], 1)   # old build, much later advisory
        self.assertEqual(r["high_undet"], 0)

    def test_unparsable_image_tag_does_not_clear(self):
        """A non-numeric tag is not a version. Route A declines rather than
        guessing; with no other evidence the finding is UNDETERMINED."""
        r = tally(_report(
            ("lang-pkgs", [_vuln("TEST-P-5", "github.com/org/app", "CRITICAL",
                                 "3.0.9", _pseudo("20260101000000"))]),
            artifact="org/app:latest"))
        self.assertEqual(r["crit_fix"], 0)
        self.assertEqual(r["crit_undet"], 1)

    def test_bare_integer_tag_does_not_clear(self):
        """A single-component tag is ambiguous in a way that fails dangerously.
        `:18` is a head-of-line tag, and a date tag `:20260819` would parse as
        major 20,260,819 and compare greater than every FixedVersion there is —
        silently clearing every finding on the image."""
        for tag in ("18", "20260819"):
            with self.subTest(tag=tag):
                r = tally(_report(
                    ("lang-pkgs", [_vuln("TEST-P-20", "github.com/org/app", "CRITICAL",
                                         "3.0.9", _pseudo("20260101000000"))]),
                    artifact=f"org/app:{tag}"))
                self.assertEqual(r["crit_fix"], 0)
                self.assertEqual(r["crit_undet"], 1)

    def test_prerelease_tag_is_not_treated_as_its_release(self):
        """`1.14.0-rc1` is not `1.14.0` — truncating it would assert a version
        that was never measured."""
        r = tally(_report(
            ("lang-pkgs", [_vuln("TEST-P-6", "github.com/org/app", "HIGH",
                                 "1.14.0", _pseudo("20260101000000"))]),
            artifact="org/app:1.14.0-rc1"))
        self.assertEqual(r["high_fix"], 0)
        self.assertEqual(r["high_undet"], 1)

    def test_branch_specific_fix_list_uses_the_installed_branch(self):
        """An advisory naming one fix per maintained branch ("1.2.3, 2.0.1")
        must be judged on the INSTALLED branch. Taking the lowest cleared a
        2.0.0 build for beating the 1.x fix while 2.0.1 was still ahead of it."""
        r = tally(_report(
            ("lang-pkgs", [_vuln("TEST-P-21", "example.org/acme/dnsd", "CRITICAL",
                                 "1.2.3, 2.0.1", _pseudo("20260101000000"))]),
            artifact="acme/dnsd:2.0.0"))
        self.assertEqual(r["crit_fix"], 1)

    def test_branch_specific_fix_list_clears_on_its_own_branch(self):
        r = tally(_report(
            ("lang-pkgs", [_vuln("TEST-P-22", "example.org/acme/dnsd", "CRITICAL",
                                 "1.2.3, 2.0.1", _pseudo("20260101000000"))]),
            artifact="acme/dnsd:2.0.1"))
        self.assertIsNone(r)

    def test_build_above_every_branch_clears(self):
        """No fix is named on the 3.x line, and 3.0.0 is past them all."""
        r = tally(_report(
            ("lang-pkgs", [_vuln("TEST-P-23", "example.org/acme/dnsd", "CRITICAL",
                                 "1.2.3, 2.0.1", _pseudo("20260101000000"))]),
            artifact="acme/dnsd:3.0.0"))
        self.assertIsNone(r)

    def test_calver_tag_against_semver_fixes_does_not_clear(self):
        """A dotted date tag survives require_dotted but is not on the same
        numbering scale: 2026.08.19 parses as major 2026 and would compare
        greater than every semver FixedVersion, clearing the whole image."""
        r = tally(_report(
            ("lang-pkgs", [_vuln("TEST-P-24", "example.org/acme/dnsd", "CRITICAL",
                                 "3.0.0", _pseudo("20260101000000"))]),
            artifact="acme/dnsd:2026.08.19"))
        self.assertEqual(r["crit_fix"], 0)
        self.assertEqual(r["crit_undet"], 1)

    def test_calver_on_both_sides_is_a_real_comparison(self):
        """Projects that genuinely version in CalVer get their advisories in
        CalVer too — same scale, so the comparison is meaningful."""
        r = tally(_report(
            ("lang-pkgs", [_vuln("TEST-P-25", "example.org/acme/dnsd", "CRITICAL",
                                 "2026.5.6", _pseudo("20260101000000"))]),
            artifact="acme/dnsd:2026.8.0"))
        self.assertIsNone(r)

    def test_dependency_sharing_the_image_name_does_not_borrow_its_tag(self):
        """Leaf-only matching let a dependency impersonate the main module.
        `cli`, `agent`, `operator`, `exporter` are common module leaves AND
        common image names; the owner segment has to agree too."""
        r = tally(_report(
            ("lang-pkgs", [_vuln("TEST-P-26", "example.org/urfave/cli", "CRITICAL",
                                 "3.9.0", _pseudo("20200101000000"),
                                 "2026-01-01T00:00:00Z")]),
            artifact="ghcr.io/acme/cli:3.5.0"))
        self.assertEqual(r["crit_fix"], 1)   # kept, via route C

    def test_relationship_field_overrides_the_name_match(self):
        """Where Trivy marks the package as a non-root dependency, believe it
        even if the names happen to line up."""
        v = _vuln("TEST-P-27", "example.org/acme/dnsd", "CRITICAL",
                  "9.9.9", _pseudo("20260101000000"), "2026-01-01T00:00:00Z")
        v["Relationship"] = "indirect"
        r = tally(_report(("lang-pkgs", [v]), artifact="acme/dnsd:1.0.0"))
        # Route A declined, so this is decided by C (inside the margin) -> undet
        self.assertEqual(r["crit_undet"], 1)

    def test_route_b_multi_value_takes_the_highest_fix_commit(self):
        """One fix commit per branch; a timestamp cannot say which branch this
        build is on, so the bar is the highest and the finding survives."""
        r = tally(_report(
            ("lang-pkgs", [_vuln("TEST-P-28", "example.org/dep/netlib", "HIGH",
                                 f"{_pseudo('20210101000000')}, {_pseudo('20230101000000')}",
                                 _pseudo("20220101000000"))]),
            artifact="acme/dnsd:1.0.0"))
        self.assertEqual(r["high_fix"], 1)

    # -- Route B: FixedVersion is itself a pseudo-version ---------------------

    def test_pseudo_vs_pseudo_newer_build_clears(self):
        r = tally(_report(
            ("lang-pkgs", [_vuln("TEST-P-7", "golang.org/x/crypto", "HIGH",
                                 _pseudo("20211202192323"), _pseudo("20220101000000"))]),
            artifact="some/image:1.0.0"))
        self.assertIsNone(r)

    def test_pseudo_vs_pseudo_older_build_stays_fixable(self):
        """A dependency pinned at an old commit, against a fix commit from a
        year later, is genuinely behind and must keep counting."""
        r = tally(_report(
            ("lang-pkgs", [_vuln("TEST-P-8", "golang.org/x/crypto", "HIGH",
                                 _pseudo("20211202192323"), _pseudo("20201221181555"))]),
            artifact="example.org/vendor/app:0.17.2"))
        self.assertEqual(r["high_fix"], 1)

    # -- Route C: build time vs advisory publication, outside the margin ------

    def test_build_well_after_publication_clears(self):
        r = tally(_report(
            ("lang-pkgs", [_vuln("TEST-P-9", "golang.org/x/net", "CRITICAL",
                                 "0.55.0", _pseudo("20260901000000"),
                                 "2026-01-01T00:00:00Z")]),
            artifact="some/image:1.0.0"))
        self.assertIsNone(r)

    def test_build_well_before_publication_stays_fixable(self):
        r = tally(_report(
            ("lang-pkgs", [_vuln("TEST-P-10", "golang.org/x/net", "CRITICAL",
                                 "0.55.0", _pseudo("20200101000000"),
                                 "2026-01-01T00:00:00Z")]),
            artifact="some/image:1.0.0"))
        self.assertEqual(r["crit_fix"], 1)

    def test_inside_the_margin_is_undetermined_not_fixable(self):
        """Publication drifts from the fix commit in both directions, so a
        build a few days either side of it decides nothing. The finding is
        neither asserted nor suppressed."""
        r = tally(_report(
            ("lang-pkgs", [_vuln("TEST-P-11", "golang.org/x/net", "CRITICAL",
                                 "0.55.0", _pseudo("20260110000000"),
                                 "2026-01-01T00:00:00Z")]),
            artifact="some/image:1.0.0"))
        self.assertEqual(r["crit_fix"], 0)
        self.assertEqual(r["crit_undet"], 1)
        self.assertEqual(r["undet_ids"], ["TEST-P-11"])

    def test_no_publication_date_is_undetermined(self):
        r = tally(_report(
            ("lang-pkgs", [_vuln("TEST-P-12", "golang.org/x/net", "HIGH",
                                 "0.55.0", _pseudo("20260110000000"))]),
            artifact="some/image:1.0.0"))
        self.assertEqual(r["high_undet"], 1)

    # -- Scope: everything else must be untouched ----------------------------

    def test_real_semver_installed_version_is_untouched(self):
        """The control. A normal version string still compares normally — the
        path the overwhelming majority of gobinary images take, and one the
        fix must leave completely alone."""
        r = tally(_report(
            ("lang-pkgs", [_vuln("TEST-P-13", "example.org/dep/modlib", "HIGH",
                                 "0.40.0", "v0.37.0")]),
            artifact="acme/dnsd:1.14.7"))
        self.assertEqual(r["high_fix"], 1)
        self.assertEqual(r["high_undet"], 0)

    def test_os_pkgs_never_take_the_pseudo_path(self):
        """The classifier is lang-pkgs-only; an OS package version that happens
        to look like one is a different artifact."""
        r = tally(_report(
            ("os-pkgs", [_vuln("TEST-P-14", "somepkg", "CRITICAL",
                               "1.0", _pseudo("20260901000000"),
                               "2020-01-01T00:00:00Z")]),
            artifact="some/image:1.0.0"))
        self.assertEqual(r["crit_fix"], 1)

    def test_nofix_findings_are_never_reclassified(self):
        """No FixedVersion means the comparison never happened, so there is
        nothing for this fix to correct — it stays in the AR-029 class."""
        r = tally(_report(
            ("lang-pkgs", [_vuln("TEST-P-15", "example.org/acme/dnsd", "HIGH",
                                 None, _pseudo("20260819003913"))]),
            artifact="acme/dnsd:1.14.7"))
        self.assertEqual(r["high_nofix"], 1)
        self.assertEqual(r["high_undet"], 0)

    def test_undetermined_alone_is_not_a_clean_report(self):
        """An image whose ONLY findings are undetermined must not return None —
        that would render as 'scanned, no CVEs' and hide the unknown."""
        r = tally(_report(
            ("lang-pkgs", [_vuln("TEST-P-16", "golang.org/x/net", "CRITICAL",
                                 "0.55.0", _pseudo("20260110000000"),
                                 "2026-01-01T00:00:00Z")]),
            artifact="some/image:1.0.0"))
        self.assertIsNotNone(r)
        self.assertEqual((r["crit_fix"], r["crit_nofix"]), (0, 0))
        self.assertEqual(r["crit_undet"], 1)

    def test_undetermined_ids_stay_out_of_both_other_id_lists(self):
        r = tally(_report(
            ("lang-pkgs", [
                _vuln("TEST-P-17", "golang.org/x/net", "CRITICAL",
                      "0.55.0", _pseudo("20260110000000"), "2026-01-01T00:00:00Z"),
                _vuln("TEST-P-18", "golang.org/x/mod", "CRITICAL", "0.40.0", "v0.37.0"),
                _vuln("TEST-P-19", "golang.org/x/sys", "CRITICAL", None, "v0.1.0"),
            ]),
            artifact="some/image:1.0.0"))
        self.assertEqual(r["fix_ids"], ["TEST-P-18"])
        self.assertEqual(r["nofix_ids"], ["TEST-P-19"])
        self.assertEqual(r["undet_ids"], ["TEST-P-17"])

    def test_mixed_main_module_and_dependency_end_to_end(self):
        """The shape that motivated the fix, in synthetic form: several
        advisories against the pseudo-versioned MAIN MODULE, all of them fixed
        in releases the image tag has passed, alongside advisories against a
        DEPENDENCY carrying a real version that is genuinely behind. Only the
        dependency's should survive."""
        main = [_vuln(f"TEST-P-M-{i}", "example.org/acme/dnsd", "HIGH",
                      fx, _pseudo("20260819003913"))
                for i, fx in enumerate(["1.11.0", "1.12.2", "1.14.2", "1.14.2",
                                        "1.14.3", "1.14.3", "1.14.3", "1.14.3",
                                        "1.14.3"])]
        dep = [_vuln(f"TEST-P-D-{i}", "example.org/dep/modlib", "HIGH",
                     "0.40.0", "v0.37.0") for i in range(2)]
        r = tally(_report(("lang-pkgs", main + dep), artifact="acme/dnsd:1.14.7"))
        self.assertEqual(r["high_fix"], 2)
        self.assertEqual(r["high_undet"], 0)
        self.assertTrue(all(i.startswith("TEST-P-D-") for i in r["fix_ids"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
