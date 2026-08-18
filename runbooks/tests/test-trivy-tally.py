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


def _vuln(vid, pkg, sev, fixed=None):
    v = {"VulnerabilityID": vid, "PkgName": pkg, "Severity": sev}
    if fixed:
        v["FixedVersion"] = fixed
    return v


def _report(*results):
    return {"Results": [{"Class": cls, "Vulnerabilities": vulns}
                        for cls, vulns in results]}


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
