#!/usr/bin/env python3
"""Regression tests for the Trivy cache: top-up coverage, tally-version
invalidation, and the steady-state-vs-transient degradation split.

Guards F-8cdf8719: a Trivy cache HIT used to skip the running-image scan
entirely. Images that started running after the cache was written were never
scanned, the section reported the cache's stale numbers as current, and — had
the incomplete-run veto not tripped for unrelated reasons — writer-side
auto-close would have resolved findings for images nobody re-checked.

Three properties are pinned here:

1. `collect_trivy_results` tops up a warm cache with every currently-running
   image the cache does not cover, and reaches full coverage of the scannable
   set.
2. `load_trivy_cache` discards a cache built by a different
   `_TRIVY_TALLY_VERSION`, so a tally-logic fix takes effect on the next run
   instead of waiting out the 24h TTL.
3. Degradation follows the transitions rule of
   docs/sops/sweep-findings-lifecycle.md §4.3 — a permanently-unscannable
   image (our own private registry, no pull credentials by policy) does NOT
   arm the veto; a transient scan failure on a normally-pullable image DOES.

Fixtures are SYNTHETIC on purpose — real per-image counts and CVE IDs for
unfixed issues are DB-only (docs/sops/vulnerability-disclosure.md).

Run: python3 runbooks/tests/test-trivy-cache-coverage.py
"""

import importlib.util
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

os.environ.setdefault("_MISE_ACTIVATED", "1")  # skip the mise re-exec on import

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPT = os.path.join(_HERE, "..", "security-check.py")
_spec = importlib.util.spec_from_file_location("security_check", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


def _cve_result(crit_fix=1, high_fix=0):
    return {"crit_fix": crit_fix, "crit_nofix": 0,
            "high_fix": high_fix, "high_nofix": 0,
            "fix_sample": ["pkg"], "nofix_sample": [],
            "fix_ids": ["CVE-0000-0001"], "nofix_ids": []}


class TopUpCoverageTest(unittest.TestCase):
    """Part 1 — a cache hit must not define coverage; the running set does."""

    def test_topup_scans_only_the_uncovered_images(self):
        cache = {"results": {"old:1": _cve_result()},
                 "failed": [],
                 "scanned": ["old:1", "clean:1"]}
        running = ["old:1", "clean:1", "new-a:2", "new-b:2"]
        seen = []

        def scan_fn(targets):
            seen.extend(targets)
            return {"new-a:2": _cve_result(crit_fix=3)}, []

        results, failed, scanned_ok, topped = _mod.collect_trivy_results(
            running, cache, scan_fn)

        # Only the two images absent from the cache were scanned...
        self.assertEqual(sorted(seen), ["new-a:2", "new-b:2"])
        self.assertEqual(sorted(topped), ["new-a:2", "new-b:2"])
        # ...and coverage now spans the FULL running set.
        self.assertEqual(scanned_ok | set(failed), set(running))
        self.assertEqual(sorted(results), ["new-a:2", "old:1"])

    def test_regression_cache_hit_alone_leaves_running_images_uncovered(self):
        """The defect, expressed as a property: cache coverage != running set."""
        cache = {"results": {}, "failed": [], "scanned": ["old:1"]}
        running = ["old:1", "new:1", "newer:1"]
        # Old behaviour = serve the cache, scan nothing.
        old_coverage = set(cache["scanned"]) & set(running)
        self.assertLess(len(old_coverage), len(running))
        _r, failed, scanned_ok, _t = _mod.collect_trivy_results(
            running, cache, lambda t: ({}, []))
        self.assertEqual(scanned_ok | set(failed), set(running))

    def test_cold_cache_scans_everything(self):
        running = ["a:1", "b:1"]
        results, failed, scanned_ok, topped = _mod.collect_trivy_results(
            running, None, lambda t: ({}, []))
        self.assertEqual(sorted(topped), running)
        self.assertEqual(scanned_ok, set(running))
        self.assertEqual(failed, [])

    def test_rescan_supersedes_a_stale_cached_verdict(self):
        """An image that is clean now must lose its cached CVE entry."""
        cache = {"results": {"app:1": _cve_result(crit_fix=9)},
                 "failed": [], "scanned": []}  # no `scanned` -> re-scan it
        results, _f, scanned_ok, topped = _mod.collect_trivy_results(
            ["app:1"], cache, lambda t: ({}, []))
        self.assertEqual(topped, ["app:1"])
        self.assertNotIn("app:1", results)
        self.assertIn("app:1", scanned_ok)

    def test_transient_cached_failure_is_retried_private_one_is_not(self):
        priv = _mod._PRIVATE_REGISTRY_PREFIX + "own-app:1"
        cache = {"results": {}, "failed": ["public:1", priv], "scanned": []}
        seen = []

        def scan_fn(targets):
            seen.extend(targets)
            return {}, []

        _r, failed, scanned_ok, _t = _mod.collect_trivy_results(
            ["public:1", priv], cache, scan_fn,
            retry_failed=lambda i: not i.startswith(_mod._PRIVATE_REGISTRY_PREFIX))
        self.assertEqual(seen, ["public:1"])      # retried
        self.assertEqual(failed, [priv])          # not retried, still failed
        self.assertIn("public:1", scanned_ok)     # recovered


class ScannabilityClassificationTest(unittest.TestCase):
    """The steady-state predicate depends on the ENVIRONMENT, not the registry."""

    def setUp(self):
        self._old = {k: os.environ.pop(k, None)
                     for k in ("TRIVY_USERNAME", "TRIVY_PASSWORD",
                               "TRIVY_REGISTRY_TOKEN")}

    def tearDown(self):
        for k, v in self._old.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v

    def test_private_without_creds_is_permanent(self):
        self.assertTrue(_mod._is_permanently_unscannable(
            _mod._PRIVATE_REGISTRY_PREFIX + "app:1"))

    def test_private_with_creds_is_not_permanent(self):
        os.environ["TRIVY_PASSWORD"] = "x"
        self.assertFalse(_mod._is_permanently_unscannable(
            _mod._PRIVATE_REGISTRY_PREFIX + "app:1"))

    def test_username_without_a_secret_is_still_permanent(self):
        """A username alone cannot authenticate, so the scan can never succeed
        on such a run — classifying it transient would arm the veto on a
        permanent condition."""
        os.environ["TRIVY_USERNAME"] = "someone"
        self.assertTrue(_mod._is_permanently_unscannable(
            _mod._PRIVATE_REGISTRY_PREFIX + "app:1"))

    def test_bearer_registry_token_counts_as_credentials(self):
        os.environ["TRIVY_REGISTRY_TOKEN"] = "x"
        try:
            self.assertFalse(_mod._is_permanently_unscannable(
                _mod._PRIVATE_REGISTRY_PREFIX + "app:1"))
        finally:
            os.environ.pop("TRIVY_REGISTRY_TOKEN", None)

    def test_public_is_never_permanent(self):
        self.assertFalse(_mod._is_permanently_unscannable("docker.io/x:1"))
        os.environ["TRIVY_USERNAME"] = "x"
        self.assertFalse(_mod._is_permanently_unscannable("docker.io/x:1"))

    def test_credentialled_private_failure_is_retried(self):
        os.environ["TRIVY_PASSWORD"] = "x"
        priv = _mod._PRIVATE_REGISTRY_PREFIX + "app:1"
        cache = {"results": {}, "failed": [priv], "scanned": []}
        seen = []
        _mod.collect_trivy_results(
            [priv], cache, lambda t: (seen.extend(t), ({}, []))[1],
            retry_failed=lambda i: not _mod._is_permanently_unscannable(i))
        self.assertEqual(seen, [priv])


class TallyVersionInvalidationTest(unittest.TestCase):
    """Part 3 — a tally-logic change must invalidate the cache immediately."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "cache.json"

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, version, created=None):
        self.path.write_text(json.dumps({
            "parser_version": version,
            "created_at": created if created is not None else time.time(),
            "results": {"a:1": _cve_result()}, "failed": [], "scanned": ["a:1"],
        }))

    def test_matching_version_is_served(self):
        self._write(_mod._TRIVY_TALLY_VERSION)
        cached, created = _mod.load_trivy_cache(self.path, 86400)
        self.assertIsNotNone(cached)
        self.assertIsNotNone(created)

    def test_different_version_is_discarded(self):
        self._write(_mod._TRIVY_TALLY_VERSION - 1)
        cached, _ = _mod.load_trivy_cache(self.path, 86400)
        self.assertIsNone(cached)

    def test_pre_mechanism_cache_without_the_key_is_discarded(self):
        self.path.write_text(json.dumps({"results": {}, "failed": []}))
        cached, _ = _mod.load_trivy_cache(self.path, 86400)
        self.assertIsNone(cached)

    def test_ttl_uses_created_at_not_mtime(self):
        """A top-up rewrites the file; the TTL must not restart with it."""
        self._write(_mod._TRIVY_TALLY_VERSION, created=time.time() - 90000)
        self.assertGreater(self.path.stat().st_mtime, time.time() - 60)  # fresh mtime
        cached, _ = _mod.load_trivy_cache(self.path, 86400)
        self.assertIsNone(cached)

    def test_unparsable_cache_is_discarded(self):
        self.path.write_text("{not json")
        self.assertEqual(_mod.load_trivy_cache(self.path, 86400), (None, None))


class DegradationClassificationTest(unittest.TestCase):
    """Part 2 — veto on transitions, never on steady states (§4.3).

    Drives the real `s4_cve_check()` with a synthetic cluster inventory and a
    fake trivy, and asserts on what lands in the DegradationLog.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        tmpdir = self.tmp.name
        # Scratch TMPDIR: never touch the live sweep's cache file.
        self._old_tmpdir = os.environ.get("TMPDIR")
        os.environ["TMPDIR"] = tmpdir
        self.cache_path = Path(tmpdir) / "cberg-trivy-cve-cache-v4.json"

        # SCRIPT_DIR must hold a version-check snapshot or s4 early-returns.
        # An empty one parses to zero components, so no OSV query is made.
        self._old_script_dir = _mod.SCRIPT_DIR
        _mod.SCRIPT_DIR = Path(tmpdir)
        (Path(tmpdir) / "version-check-current.md").write_text("# empty\n")

        # No registry credentials by default -> private images are permanently
        # unscannable on this run. Individual tests set them to flip the class.
        self._old_creds = {k: os.environ.pop(k, None)
                           for k in ("TRIVY_USERNAME", "TRIVY_PASSWORD",
                                     "TRIVY_REGISTRY_TOKEN")}
        self._saved = {n: getattr(_mod, n) for n in
                       ("run_lines", "kubectl", "run_cmd", "_newer_upstream_tag_exists")}
        _mod.run_lines = lambda *a, **k: []          # no gh PR lookup
        _mod._newer_upstream_tag_exists = lambda img: True   # no registry lookup
        _mod.DEGRADED._reasons = []

    def tearDown(self):
        for k, v in self._old_creds.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v
        for n, v in self._saved.items():
            setattr(_mod, n, v)
        _mod.SCRIPT_DIR = self._old_script_dir
        if self._old_tmpdir is None:
            os.environ.pop("TMPDIR", None)
        else:
            os.environ["TMPDIR"] = self._old_tmpdir
        _mod.DEGRADED._reasons = []
        self.tmp.cleanup()

    def _run_section(self, images, failing=()):
        _mod.kubectl = lambda args, timeout=30: "\n".join(images)

        def fake_run_cmd(cmd, timeout=30):
            img = cmd.split()[-1]
            if img in failing:
                return 1, "", "simulated scan failure"
            return 0, json.dumps({"Results": []}), ""

        _mod.run_cmd = fake_run_cmd
        return _mod.s4_cve_check()

    def _reasons(self):
        return [r for r in _mod.DEGRADED._reasons if "trivy" in r.lower()]

    def test_private_registry_image_does_not_arm_the_veto(self):
        priv = _mod._PRIVATE_REGISTRY_PREFIX + "own-app:1.2.3"
        _sev, findings, _md = self._run_section(["public:1", priv], failing=[priv])
        self.assertEqual(self._reasons(), [], "steady state must not veto")
        titles = " ".join(m for _s, m, _meta in findings._items)
        self.assertIn("no registry credentials", titles)  # reported as a FINDING

    def test_private_image_WITH_credentials_arms_the_veto(self):
        """The orchestrated sweep injects a gh token as TRIVY_USERNAME/PASSWORD
        (runbooks/sweep-run.py), so private images ARE scannable and DO carry
        real findings. A failure then is a transition, not a steady state —
        otherwise an expired token silently auto-closes all of them at once."""
        os.environ["TRIVY_PASSWORD"] = "x"  # not a real credential
        priv = _mod._PRIVATE_REGISTRY_PREFIX + "own-app:1.2.3"
        _sev, findings, _md = self._run_section(["public:1", priv], failing=[priv])
        self.assertTrue(self._reasons(), "credentialled private failure must veto")
        titles = " ".join(m for _s, m, _meta in findings._items)
        self.assertNotIn("no registry credentials", titles)
        self.assertIn("unscannable after retry", titles)

    def test_transient_public_failure_arms_the_veto(self):
        _sev, findings, _md = self._run_section(
            ["public:1", "flaky:2"], failing=["flaky:2"])
        self.assertTrue(self._reasons(), "transient failure must veto")
        self.assertIn("still unscannable after retry", " ".join(self._reasons()))

    def test_full_coverage_arms_nothing(self):
        self._run_section(["public:1", "other:2"])
        self.assertEqual(self._reasons(), [])

    def test_warm_cache_tops_up_a_newly_running_image(self):
        self._run_section(["a:1"])
        self.assertTrue(self.cache_path.exists())
        self.assertEqual(json.loads(self.cache_path.read_text())["scanned"], ["a:1"])
        # Second run: a new image appears. It must be scanned, not skipped.
        _mod.DEGRADED._reasons = []
        self._run_section(["a:1", "b:2"])
        cache = json.loads(self.cache_path.read_text())
        self.assertEqual(cache["scanned"], ["a:1", "b:2"])
        self.assertEqual(self._reasons(), [])

    def test_stale_tally_version_forces_a_full_rescan(self):
        self._run_section(["a:1", "b:2"])
        cache = json.loads(self.cache_path.read_text())
        cache["parser_version"] = _mod._TRIVY_TALLY_VERSION - 1
        self.cache_path.write_text(json.dumps(cache))
        scanned = []
        _mod.kubectl = lambda args, timeout=30: "a:1\nb:2"

        def fake_run_cmd(cmd, timeout=30):
            scanned.append(cmd.split()[-1])
            return 0, json.dumps({"Results": []}), ""

        _mod.run_cmd = fake_run_cmd
        _mod.s4_cve_check()
        self.assertEqual(sorted(scanned), ["a:1", "b:2"])  # both, not zero
        self.assertEqual(
            json.loads(self.cache_path.read_text())["parser_version"],
            _mod._TRIVY_TALLY_VERSION)


if __name__ == "__main__":
    unittest.main(verbosity=2)
