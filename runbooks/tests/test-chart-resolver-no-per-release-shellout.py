#!/usr/bin/env python3
"""Chart-version resolvers must not shell out once per HelmRelease (F-539b186e).

Measured 2026-09-28: a full check-all-versions.py run took 979 s, over the
maintenance window's 15-min Step 0 refresh cap. The two biggest costs were
per-HelmRelease subprocesses whose answer cannot change within a run:

  * `helm repo add` + `helm search repo` + `helm repo remove` for every
    classic-repo chart (30 calls, 343 s + 31 s) -- `helm search repo` loads
    every index in the local helm cache, ~11 s a call;
  * `helm show chart oci://...` for every OCI chart (94 calls, 212 s) --
    ~40 HelmReleases pin the same app-template chart.

These tests pin the fix: a classic repo is answered from the per-run
index.yaml cache (no helm subprocess at all), an OCI ref is resolved once
per run, and both keep their failure semantics (index unreachable -> the
old helm path; a failed `helm show chart` is recorded once, not per
consumer, and is not retried as a success).
"""
import importlib.util
import os
import pathlib
import sys
import types
import unittest

os.environ.setdefault("_MISE_ACTIVATED", "1")
ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("cav_resolver", ROOT / "runbooks" / "check-all-versions.py")
cav = importlib.util.module_from_spec(spec)
sys.modules["cav_resolver"] = cav
spec.loader.exec_module(cav)
_CLS = cav.VersionChecker


class _Degraded:
    def __init__(self):
        self.records = []

    def record(self, *a, **kw):
        self.records.append(a)


def _inst(index=None):
    c = _CLS.__new__(_CLS)
    c.degraded = _Degraded()
    c._index_cache = dict(index or {})
    return c


class _Run:
    """Stand-in for subprocess.run that counts calls per argv[0:3]."""

    def __init__(self, stdout="", rc=0):
        self.calls = []
        self.stdout, self.rc = stdout, rc

    def __call__(self, cmd, *a, **kw):
        self.calls.append(list(cmd))
        return types.SimpleNamespace(returncode=self.rc, stdout=self.stdout, stderr="")


class TestClassicRepoFromIndex(unittest.TestCase):
    def setUp(self):
        self._orig = cav.subprocess.run

    def tearDown(self):
        cav.subprocess.run = self._orig

    def test_index_answers_without_any_helm_subprocess(self):
        url = "https://charts.example.test"
        c = _inst({url: {"foo": [{"version": "1.9.0"}, {"version": "1.10.0"},
                                 {"version": "2.0.0-rc.1"}, {"version": "1.2.3"}]}})
        run = _Run()
        cav.subprocess.run = run
        self.assertEqual(c.get_helm_repo_chart_version(url, "foo"), "1.10.0",
                         "newest STABLE version, as `helm search repo` without --devel")
        self.assertEqual(run.calls, [], "no helm repo add/search/remove per release")

    def test_index_unreachable_falls_back_to_helm(self):
        url = "https://charts.example.test"
        c = _inst({url: None})               # negative-cached: index fetch failed
        run = _Run(stdout='[{"version": "3.1.0"}]')
        cav.subprocess.run = run
        self.assertEqual(c.get_helm_repo_chart_version(url, "foo"), "3.1.0")
        self.assertTrue(any(cmd[:3] == ["helm", "search", "repo"] for cmd in run.calls),
                        "an index outage must degrade to the old path, never to a silent None")

    def test_chart_absent_from_index_falls_back_to_helm(self):
        url = "https://charts.example.test"
        c = _inst({url: {"other": [{"version": "1.0.0"}]}})
        run = _Run(stdout="[]")
        cav.subprocess.run = run
        self.assertIsNone(c.get_helm_repo_chart_version(url, "foo"))
        self.assertTrue(run.calls, "a chart the index does not carry still gets the helm lookup")


class TestOciChartResolvedOncePerRun(unittest.TestCase):
    def setUp(self):
        self._orig = cav.subprocess.run

    def tearDown(self):
        cav.subprocess.run = self._orig

    def test_same_ref_one_helm_show_chart(self):
        c = _inst()
        run = _Run(stdout="apiVersion: v2\nname: app-template\nversion: 5.2.1\n")
        cav.subprocess.run = run
        got = [c.get_oci_chart_version("oci://ghcr.io/bjw-s-labs/helm", "app-template")
               for _ in range(40)]
        self.assertEqual(set(got), {"5.2.1"})
        self.assertEqual(len(run.calls), 1, "40 consumers of one chart -> ONE pull")

    def test_distinct_refs_are_not_conflated(self):
        c = _inst()
        run = _Run(stdout="version: 1.0.0\n")
        cav.subprocess.run = run
        c.get_oci_chart_version("ghcr.io/a", "x")
        c.get_oci_chart_version("ghcr.io/b", "x")
        c.get_oci_chart_version("ghcr.io/a", "y")
        self.assertEqual(len(run.calls), 3)

    def test_failure_is_cached_and_recorded_once(self):
        c = _inst()
        run = _Run(stdout="", rc=1)
        cav.subprocess.run = run
        self.assertIsNone(c.get_oci_chart_version("oci://ghcr.io/x", "broken"))
        self.assertIsNone(c.get_oci_chart_version("oci://ghcr.io/x", "broken"))
        self.assertEqual(len(run.calls), 1)
        self.assertEqual(len(c.degraded.records), 1,
                         "the degradation is per ref, not per consumer")


if __name__ == "__main__":
    unittest.main(verbosity=2)
