"""Regression test: the version report's source link for app-template points
at the real release (2026-09-26).

bjw-s publishes app-template from `oci://ghcr.io/bjw-s-labs/helm`, which
get_chart_repo_info() derives to `bjw-s-labs/app-template` -- a repository
that does not exist. The releases live in the charts monorepo
bjw-s-labs/helm-charts under the tag `app-template-X.Y.Z` (verified live:
releases/tag/app-template-5.2.1 resolves). check-all-versions.py
CHART_RELEASE_SOURCES now carries that, and the report prints the tag.

Run:  python3 runbooks/tests/test-chart-release-source-link.py
"""
from __future__ import annotations

import importlib.util
import inspect
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
os.environ.setdefault("_MISE_ACTIVATED", "1")
spec = importlib.util.spec_from_file_location("cav_link_under_test",
                                              REPO / "runbooks/check-all-versions.py")
cav = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cav)  # type: ignore
FAILURES: list[str] = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {str(detail)[:300]}"))
    if not ok:
        FAILURES.append(name)


src = cav.CHART_RELEASE_SOURCES.get("app-template")
check("app-template maps to bjw-s-labs/helm-charts", src and src[:2] == ("bjw-s-labs", "helm-charts"), src)
check("... with the `<chart>-<version>` tag shape",
      src and src[2].format(chart="app-template", version="5.2.1") == "app-template-5.2.1", src)
full = Path(cav.__file__).read_text()
check("the chart loop consults CHART_RELEASE_SOURCES before get_chart_repo_info",
      "CHART_RELEASE_SOURCES.get(hr['chart_name'])" in full)
check("the notes fetch uses the release TAG, not the bare version",
      "self.fetch_release_notes(owner, repo, release_tag)" in full)
check("the report's Source link prints the release tag",
      "releases/tag/{chart.get('release_tag') or chart['latest_version']}" in full)
check("G3's chart resolver is untouched (no app-template entry in get_chart_repo_info)",
      "'app-template'" not in inspect.getsource(cav.VersionChecker.get_chart_repo_info))

print()
if FAILURES:
    print(f"FAILED {len(FAILURES)}: {FAILURES}")
    sys.exit(1)
print("ALL PASS")
