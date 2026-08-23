#!/usr/bin/env python3
"""Regression tests for coverage.py's live-repo cross-check.

coverage.py enumerates the actionable universe from version-check-current.md, a
SNAPSHOT the sweep writes every 48h. Maintenance windows apply bumps BETWEEN
sweeps, so the snapshot kept proposing updates that had already landed: after
the 2026-08-23 sun-window applied 10 of 12 AUTO items, re-running the reconciler
returned byte-identical output. The AUTO lane could never self-clear, every
window re-proposed the same batch, and the operator could not tell a pending
bump from a done one.

`already_applied()` closes that, and its ASYMMETRY is the whole point: a false
"already applied" silently drops a real update — the CRACK class this file
exists to prevent — while a false "still pending" costs one redundant no-op. So
the test demands BOTH that the target is present AND that the current version is
gone, and every unresolvable case must fall back to "still pending".

Run: python3 runbooks/tests/test-coverage-already-applied.py
"""
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "coverage_mod", os.path.join(_HERE, "..", "coverage.py"))
cov = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cov)


def item(**kw):
    base = {"component": "app", "namespace": "testns", "kind": "image",
            "current": "1.0.0", "target": "1.0.1"}
    base.update(kw)
    return base


class AlreadyApplied(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "kubernetes" / "apps" / "testns").mkdir(parents=True)
        self._orig_root = cov.REPO_ROOT
        cov.REPO_ROOT = self.root
        cov._NS_TEXT_CACHE.clear()

    def tearDown(self):
        cov.REPO_ROOT = self._orig_root
        cov._NS_TEXT_CACHE.clear()
        self._tmp.cleanup()

    def write(self, name, text):
        (self.root / "kubernetes" / "apps" / "testns" / name).write_text(text)
        cov._NS_TEXT_CACHE.clear()

    # ── the bug this closes ────────────────────────────────────────────────
    def test_applied_bump_is_dropped(self):
        self.write("hr.yaml", "spec:\n  values:\n    image:\n      tag: 1.0.1\n")
        self.assertTrue(cov.already_applied(item()))

    def test_pending_bump_is_kept(self):
        self.write("hr.yaml", "spec:\n  values:\n    image:\n      tag: 1.0.0\n")
        self.assertFalse(cov.already_applied(item()))

    # ── the asymmetry: anything unprovable stays PENDING ───────────────────
    def test_old_version_still_present_elsewhere_keeps_item(self):
        # sibling workload in the same namespace is still on the old version:
        # we must NOT claim the bump landed. This is the real 8.10.0-alpine
        # case — superset/nextcloud/paperless run redis as plain Deployments.
        self.write("a.yaml", "image: redis:1.0.1\n")
        self.write("b.yaml", "image: redis:1.0.0\n")
        self.assertFalse(cov.already_applied(item()))

    def test_unknown_namespace_keeps_item(self):
        self.assertFalse(cov.already_applied(item(namespace="does-not-exist")))

    def test_missing_namespace_keeps_item(self):
        self.write("hr.yaml", "tag: 1.0.1\n")
        self.assertFalse(cov.already_applied(item(namespace="")))

    def test_truncated_tag_keeps_item(self):
        # the overview table clips long cells; a clipped tag cannot be matched
        # literally, so it must never be judged applied.
        self.write("hr.yaml", "tag: v0.144.1-noble-full\n")
        self.assertFalse(cov.already_applied(
            item(current="v0.143.0-noble-full", target="v0.144.1-noble-ful...")))

    def test_target_absent_keeps_item(self):
        self.write("hr.yaml", "tag: 9.9.9\n")
        self.assertFalse(cov.already_applied(item()))

    # ── comments are not deployed versions ─────────────────────────────────
    def test_old_version_only_in_a_comment_is_dropped(self):
        # a bump's changelog comment names the version it REPLACED, so the old
        # string lingers forever and the check never fired. grafana
        # 12.11.0->12.11.1 stayed in AUTO for exactly this reason.
        self.write("hr.yaml",
                   "    # 2026-08-18: chart 1.0.0 (App 13.2.0) — routine minor.\n"
                   "    version: 1.0.1\n")
        self.assertTrue(cov.already_applied(item(kind="chart")))

    def test_full_line_comment_stripped_too(self):
        self.write("hr.yaml", "# was 1.0.0\nversion: 1.0.1\n")
        self.assertTrue(cov.already_applied(item(kind="chart")))

    def test_comment_stripping_keeps_real_values(self):
        # a '#' that is not a comment marker must not eat the version
        self.write("hr.yaml", "digest: sha256:abc#notacomment\nversion: 1.0.0\n")
        self.assertFalse(cov.already_applied(item(kind="chart")))


class SnapshotAge(unittest.TestCase):
    def test_age_is_reported_or_none(self):
        age = cov.snapshot_age_hours()
        self.assertTrue(age is None or age >= 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
