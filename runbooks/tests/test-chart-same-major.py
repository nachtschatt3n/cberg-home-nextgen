#!/usr/bin/env python3
"""Regression test: a chart reports its SAME-MAJOR successor alongside the head.

F-a8bfa9de, measured 2026-09-22 with the file's own readers:

    _oci_v2_tags('ghcr.io', 'prometheus-community/charts/kube-prometheus-stack')
        -> 1138 tags, 90.x = ['90.0.0', '90.1.0', '90.1.1', '90.1.2', '90.2.0']
    _pick_latest_semver_tag(tags, '90.0.0')            -> '90.2.0'
    get_latest_chart_version(... kube-prometheus-stack) -> '91.4.1'   # BEFORE
    resolve_chart_versions(... '90.0.0')                -> {'latest': '90.2.0',
                                                             'head': '91.4.1'}  # AFTER

`helm show chart` answers with the newest tag's Chart.yaml and nothing else, so
a chart had exactly ONE answer — the absolute head. Pinned at 90.0.0 with
90.1.0..90.2.0 published, the report said `90.0.0 -> 91.4.1`: a MAJOR, PLAN
lane, planner dispatch — while the in-line minors that Renovate's
separate-major PR offers and the nightly window could apply were masked behind
it. The image side fixed the mirror image of this on 2026-08-15 (redisinsight:
same-major preference, fall through to the head when the line is exhausted);
this ports that rule to charts and ALWAYS carries the head so the report shows
both.

Pinned directions: same-major successor becomes `latest` when one exists;
when the current line is exhausted the head surfaces (a MAJOR is not hidden);
at the head nothing is reported; an UNKNOWABLE listing falls back to the old
single-answer resolver (never silently worse than before); pre-releases never
win; the overview cell carries the head AFTER the arrow pair so coverage.py's
row parser lanes the same-major step and still sees the head.

Hermetic: the registry listers and helm are replaced by stubs.
Run: python3 runbooks/tests/test-chart-same-major.py
"""

from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


cav = _load("cav", "runbooks/check-all-versions.py")
cov = _load("cov", "runbooks/coverage.py")

FAILURES: list[str] = []
TAGS = ["0.1.0", "89.0.0", "90.0.0", "90.1.0", "90.1.1", "90.1.2", "90.2.0",
        "91.0.0", "91.4.1", "92.0.0-rc.1"]
OCI_URL = "oci://ghcr.io/prometheus-community/charts"
CHART = "kube-prometheus-stack"


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


def counted(population, what: str) -> int:
    n = len(population)
    if n == 0:
        raise SystemExit(f"ABORT: empty population for {what} — instrument broken, not 'zero'")
    return n


def checker(tags=TAGS, helm_head="91.4.1"):
    ck = cav.VersionChecker(str(REPO))
    ck.calls = []
    ck.get_latest_chart_version = lambda *a, **k: helm_head           # the OLD single answer

    def oci(host, path, **k):
        ck.calls.append(("oci", host, path))
        return tags

    def hub(name, current_tag="", **k):
        ck.calls.append(("hub", name))
        return tags or []

    def index(url):
        ck.calls.append(("index", url))
        return None if tags is None else {CHART: [{"version": v} for v in tags]}

    ck._oci_v2_tags = oci
    ck._dockerhub_tags = hub
    ck._chart_index_entries = index
    return ck


def resolve(ck, current, url=OCI_URL, rtype="oci", repo="prometheus-community"):
    return ck.resolve_chart_versions(repo, CHART, current, url, rtype)


def main() -> int:
    print("test-chart-same-major")

    # ── THE defect ─────────────────────────────────────────────────────
    ck = checker()
    r = resolve(ck, "90.0.0")
    check("pinned 90.0.0: latest is the same-major successor 90.2.0",
          r["latest"] == "90.2.0", str(r))
    check("...and the head 91.4.1 is carried alongside", r["head"] == "91.4.1", str(r))
    check("...from a real listing", r["listed"] is True and r["candidates"] == counted(TAGS, "TAGS"))
    check("the OCI chart is listed at <path>/<chart> on the registry host",
          ("oci", "ghcr.io", f"prometheus-community/charts/{CHART}") in ck.calls, str(ck.calls))

    # ── the directions the image side already pins, now for charts ─────
    r = resolve(checker(), "90.2.0")
    check("at the head of its major: the next MAJOR surfaces as latest (not hidden)",
          r["latest"] == "91.4.1" and r["head"] == "91.4.1", str(r))
    r = resolve(checker(), "91.4.1")
    check("at the head: latest == head == current (nothing to report)",
          r["latest"] == "91.4.1" and r["head"] == "91.4.1", str(r))
    r = resolve(checker(), "90.1.1")
    check("mid-line: the newest same-major, not merely the next patch",
          r["latest"] == "90.2.0", str(r))
    r = resolve(checker(tags=TAGS + ["91.5.0"]), "90.0.0")
    check("a complete listing that is NEWER than helm's single answer wins the head",
          r["head"] == "91.5.0" and r["latest"] == "90.2.0", str(r))
    r = resolve(checker(tags=TAGS[:-2]), "90.0.0")   # listing stops at 91.0.0, helm says 91.4.1
    check("a listing OLDER than helm's answer does not drag the head backwards",
          r["head"] == "91.4.1", str(r))
    r = resolve(checker(), "90.0.0")
    check("a pre-release never wins the head (92.0.0-rc.1 is in the list)",
          r["head"] == "91.4.1")

    # ── unknowable listing: the pre-fix behaviour, never silently worse ─
    r = resolve(checker(tags=None), "90.0.0")
    check("listing unknowable -> latest == head from the old resolver, listed=False",
          r == {"latest": "91.4.1", "head": "91.4.1", "listed": False, "candidates": 0}, str(r))
    r = resolve(checker(tags=[]), "90.0.0")
    check("an EMPTY listing is treated as unknowable, not as 'no other versions'",
          r["latest"] == "91.4.1" and r["listed"] is False, str(r))

    # ── every chart source shape goes through the right lister ─────────
    ck = checker()
    r = resolve(ck, "90.0.0", url="https://example.invalid/charts", rtype="default")
    check("classic Helm repo: index.yaml entries are the candidates",
          r["latest"] == "90.2.0" and ("index", "https://example.invalid/charts") in ck.calls, str(ck.calls))
    ck = checker()
    r = resolve(ck, "90.0.0", url="oci://docker.io/example", rtype="oci")
    check("Docker Hub-hosted OCI chart: the Hub lister is used, not a bare v2 call to docker.io",
          ("hub", f"example/{CHART}") in ck.calls and r["latest"] == "90.2.0", str(ck.calls))
    ck = checker()
    r = ck.resolve_chart_versions("nowhere", CHART, "90.0.0", "", "")
    check("unknown repo + no URL: nothing is listed and nothing invented",
          r["listed"] is False and r["candidates"] == 0 and not ck.calls, str(r))

    # ── the report: both versions rendered; coverage.py lanes the hop ──
    ck = checker()
    ck.results = [{
        "name": CHART, "namespace": "monitoring",
        "file_path": "kubernetes/apps/monitoring/kube-prometheus-stack/app/helmrelease.yaml",
        "chart": {"name": CHART, "repository": "prometheus-community",
                  "current_version": "90.0.0", "latest_version": "90.2.0",
                  "head_version": "91.4.1",
                  "update_assessment": ck.assess_update_complexity("90.0.0", "90.2.0")},
        "images": [],
    }]
    md = ck.generate_markdown_report()
    rows = [ln for ln in md.splitlines() if ln.startswith("|") and f"`{CHART}`" in ln]
    counted(rows, "overview rows")
    row = rows[0]
    check("overview cell shows the same-major hop AND the head",
          "90.0.0 → 90.2.0" in row and "(head 91.4.1)" in row, row)
    m = cov._ROW.match(row)
    am = cov._ARROW.search(m.group(3)) if m else None
    check("coverage.py's REAL row parser lanes 90.0.0 -> 90.2.0 from that cell (minor)",
          bool(am) and am.group(1) == "90.0.0" and am.group(2) == "90.2.0"
          and cov._semver_type("90.0.0", "90.2.0") == "minor", str(am and am.groups()))
    check("detail section names the newest overall as a separate, larger hop",
          "**Newest Overall:** `91.4.1`" in md)
    ck.results[0]["chart"]["head_version"] = "90.2.0"
    md = ck.generate_markdown_report()
    check("no head note when the actionable hop IS the head", "(head " not in md)

    # ── wiring ─────────────────────────────────────────────────────────
    src = inspect.getsource(cav.VersionChecker.check_all)
    check("check_all() resolves charts through resolve_chart_versions and stores head_version",
          "resolve_chart_versions(" in src and "head_version" in src)

    # ── COMMISSIONING STRAW: the pre-fix world had no listing ──────────
    ck = checker()
    real = ck.get_chart_version_candidates
    try:
        ck.get_chart_version_candidates = lambda *a, **k: None
        straw = resolve(ck, "90.0.0")
        check("commissioning: without the listing the resolver collapses to the head "
              "(90.0.0 -> 91.4.1) — i.e. the same-major assertion above would FAIL",
              straw["latest"] == "91.4.1" and straw["head"] == "91.4.1", str(straw))
    finally:
        ck.get_chart_version_candidates = real

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} -> {', '.join(FAILURES)}")
        return 1
    print("all tests passed")
    return 0


def test_pytest_entry() -> None:
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())
