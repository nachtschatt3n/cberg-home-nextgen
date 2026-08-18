#!/usr/bin/env python3
"""Regression tests for s4_cve_check's OSV.dev component scan.

Guards the 2026-08-18 fix for a check that had never worked. The query sent
`ecosystem: "Helm"`, which OSV does not have; the API answered HTTP 400
"invalid ecosystem" to all 25 requests, every request was swallowed, and the
section printed "No CVEs found for checked components" on every run since it
was written — a manufactured green in a security audit.

The CONTROL INVARIANT below is the point of this file: the scan must never be
able to report a clean OSV result unless at least one query actually
succeeded. A silent zero is not a pass.

Run: python3 runbooks/tests/test-osv-coverage.py
"""

import importlib.util
import io
import contextlib
import json
import os
import sys
import unittest
import urllib.error
import urllib.request

os.environ.setdefault("_MISE_ACTIVATED", "1")  # skip the mise re-exec on import

_HERE = os.path.dirname(os.path.abspath(__file__))
_RUNBOOKS = os.path.dirname(_HERE)
sys.path.insert(0, _RUNBOOKS)

_spec = importlib.util.spec_from_file_location(
    "security_check", os.path.join(_RUNBOOKS, "security-check.py"))
sc = importlib.util.module_from_spec(_spec)
sys.modules["security_check"] = sc
_spec.loader.exec_module(sc)


def _run_s4(urlopen_impl):
    """Run s4_cve_check with OSV mocked and trivy forced absent.

    Forcing `shutil.which("trivy") -> None` makes the section return right
    after the OSV block, so the test exercises OSV coverage accounting without
    a 60s image scan.
    """
    import shutil
    orig_urlopen, orig_which, orig_runlines = (
        urllib.request.urlopen, shutil.which, sc.run_lines)
    urllib.request.urlopen = urlopen_impl
    shutil.which = lambda _n: None
    sc.run_lines = lambda *a, **k: []
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            status, findings, _body = sc.s4_cve_check()
    finally:
        urllib.request.urlopen = orig_urlopen
        shutil.which = orig_which
        sc.run_lines = orig_runlines
    return status, findings, buf.getvalue()


def _titles(findings):
    return [t for _sev, t, _meta in findings._items]


class TestOsvControlInvariant(unittest.TestCase):
    """A silent zero is never a pass."""

    def test_zero_successful_queries_cannot_report_clean(self):
        def always_400(*_a, **_k):
            raise urllib.error.HTTPError("u", 400, "invalid ecosystem", None, None)

        _status, findings, out = _run_s4(always_400)
        titles = " | ".join(_titles(findings))

        self.assertNotIn("No CVEs found", out,
                         "printed a clean OSV verdict with zero successful queries")
        self.assertIn("inoperative", titles.lower(),
                      "did not emit an 'inoperative' finding when every query failed")

    def test_zero_successful_queries_also_covers_transient_failure(self):
        def always_503(*_a, **_k):
            raise urllib.error.HTTPError("u", 503, "unavailable", None, None)

        _status, findings, out = _run_s4(always_503)
        self.assertNotIn("No CVEs found", out)
        self.assertIn("inoperative", " | ".join(_titles(findings)).lower())
        # A 5xx is transient, so it must ALSO arm the auto-close veto.
        self.assertTrue(
            any("OSV" in r for r in sc.DEGRADED.reasons),
            "a transient OSV failure did not arm the veto")

    def test_unmapped_components_are_reported_not_folded_into_green(self):
        """Components with no verified OSV identity must surface as a gap."""
        class _Resp:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return json.dumps({"vulns": []}).encode()

        def ok_empty(*_a, **_k):
            return _Resp()

        _status, findings, _out = _run_s4(ok_empty)
        titles = " | ".join(_titles(findings))
        self.assertIn("coverage gap", titles.lower(),
                      "unmapped components were silently folded into the result")
        self.assertIn("ecosystem undetermined", titles.lower())


class TestOsvMappingTable(unittest.TestCase):

    def test_no_helm_ecosystem_ever_again(self):
        ecos = {eco for eco, _pkg in sc._OSV_PACKAGES.values()}
        self.assertNotIn("Helm", ecos, "OSV has no Helm ecosystem")

    def test_no_distro_ecosystems(self):
        """Distro versions (1:10.11.6-1) cannot be compared to an image tag."""
        ecos = {eco for eco, _pkg in sc._OSV_PACKAGES.values()}
        for bad in ("Debian", "Alpine", "Ubuntu", "Red Hat", "Rocky Linux"):
            self.assertNotIn(bad, ecos,
                             f"{bad} version semantics do not match our image tags")

    def test_table_is_non_empty(self):
        self.assertTrue(sc._OSV_PACKAGES, "mapping table is empty — nothing is checked")


class TestVersionSnapshotParser(unittest.TestCase):
    """The version sent to OSV must be the App version, not the Namespace.

    The original regex took the first two BACKTICKED cells of
    `| Deployment | Namespace | Chart | Image | App | Complexity |`, which are
    Deployment and Namespace — so it queried `version: "ai"`. OSV does not
    reject an unparseable version, it returns EVERY vulnerability for the
    package: one component came back with 233 CVEs independent of the version
    actually deployed. Column position identifies the version, not backticks.
    """

    TABLE = """
| Deployment | Namespace | Chart | Image | App | Complexity |
|------------|-----------|-------|-------|-----|------------|
| `open-webui` | `ai` | 16.0.0 | 0.11.0 | 0.11.0 | - |
| `superset` | `databases` | 1.2.3 | 5.0.0 | 5.0.0 | - |
| `librechat` | `ai` | 2.0.7 | latest | - | - |
| `mcpo` | `ai` | 5.1.0 | git-44ce6d0 | git-44ce6d0 | - |
| `openclaw` | `ai` | 5.1.0 | x | 22.23.2-bookworm@sha256:0557ac14 | - |
"""

    def test_extracts_app_version_not_namespace(self):
        rows = dict(sc._parse_version_snapshot(self.TABLE)[0])
        self.assertEqual(rows.get("open-webui"), "0.11.0")
        self.assertEqual(rows.get("superset"), "5.0.0")
        for name, ver in rows.items():
            self.assertNotIn(ver, ("ai", "databases"),
                             f"{name}: namespace leaked through as the version")

    def test_drops_uncomparable_versions(self):
        rows = dict(sc._parse_version_snapshot(self.TABLE)[0])
        self.assertNotIn("librechat", rows, "'-' is not a comparable version")
        self.assertNotIn("mcpo", rows, "'git-<sha>' is not a comparable version")

    def test_strips_variant_suffix_and_digest(self):
        rows = dict(sc._parse_version_snapshot(self.TABLE)[0])
        self.assertEqual(rows.get("openclaw"), "22.23.2")

    def test_header_row_is_not_a_component(self):
        rows = dict(sc._parse_version_snapshot(self.TABLE)[0])
        self.assertNotIn("Deployment", rows)

    def test_dropped_rows_are_reported_not_swallowed(self):
        """A mapped component with no comparable version must not vanish.

        cert-manager's App cell is `-` (its version is in the Chart column), so
        it is dropped by the version filter. It was then in NEITHER `candidates`
        NOR `unmapped`, so it was never queried and never reported as
        unchecked — the same silently-folded-into-a-green shape one layer down.
        """
        table = self.TABLE + "| `cert-manager` | `cert-manager` | 1.21.1 | x | - | - |\n"
        rows, dropped = sc._parse_version_snapshot(table)
        self.assertIn("cert-manager", dropped)
        self.assertNotIn("cert-manager", dict(rows))
        self.assertIn("cert-manager", sc._OSV_PACKAGES,
                      "fixture assumes cert-manager IS mapped")


class TestTransientClassifier(unittest.TestCase):

    def _http(self, code):
        return urllib.error.HTTPError("u", code, "m", None, None)

    def test_cloudflare_and_5xx_range_are_transient(self):
        for code in (500, 502, 503, 504, 507, 508, 509, 520, 521, 522, 524, 527):
            self.assertTrue(sc._is_transient(self._http(code)),
                            f"HTTP {code} must veto — misfiling it loses findings")

    def test_throttle_codes_are_transient(self):
        for code in (403, 408, 425, 429):
            self.assertTrue(sc._is_transient(self._http(code)))

    def test_client_errors_are_permanent(self):
        for code in (400, 401, 404, 410, 422):
            self.assertFalse(sc._is_transient(self._http(code)))

    def test_non_numeric_code_does_not_raise(self):
        class Weird(Exception):
            code = "not-a-number"
        self.assertTrue(sc._is_transient(Weird()),
                        "unknown shape must fail SAFE (veto), not raise")


class TestOsvLive(unittest.TestCase):
    """Acceptance: the mapping actually works against the real API."""

    def test_at_least_one_mapping_returns_200_with_a_real_result_set(self):
        hits = []
        for name, (eco, pkg) in sorted(sc._OSV_PACKAGES.items()):
            payload = json.dumps({"version": "1.0.0",
                                  "package": {"name": pkg, "ecosystem": eco}}).encode()
            req = urllib.request.Request(
                "https://api.osv.dev/v1/query", data=payload,
                headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=15) as r:
                    self.assertEqual(r.status, 200, f"{name}: expected HTTP 200")
                    n = len(json.load(r).get("vulns", []))
                    if n:
                        hits.append((name, eco, pkg, n))
            except urllib.error.HTTPError as e:
                self.fail(f"{name} ({eco}/{pkg}) rejected: HTTP {e.code}")
            except Exception as e:  # offline / DNS — not a code defect
                self.skipTest(f"OSV unreachable: {type(e).__name__}")
        self.assertTrue(
            hits, "no mapped component returned a non-empty vuln set — "
                  "cannot prove the ecosystem coordinates resolve to real packages")
        for name, eco, pkg, n in hits:
            print(f"    verified {name}: {eco}/{pkg} -> HTTP 200, {n} vuln(s)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
