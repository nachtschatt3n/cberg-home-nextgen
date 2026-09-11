#!/usr/bin/env python3
"""Regression tests: a HelmRelease's chart source must resolve in BOTH shapes,
and a shape this tooling cannot read must SAY SO instead of returning ''.

A HelmRelease names its chart in exactly one of two mutually exclusive ways:

    spec.chart.spec.{chart,version,sourceRef}    inline; version is in git
    spec.chartRef.{kind,name,namespace}          points at a source CR

Under `chartRef` the version is NOT in the HelmRelease — it lives on the
referenced object (`OCIRepository.spec.ref.tag`, `HelmChart.spec.version`).
`parse_helmrelease()` read only the first shape, so when k8s-gateway migrated
to an OCIRepository + chartRef on 2026-09-11 (43a3b3e4, digest pinned in
0c77bbb0) it parsed to chart_name='' / chart_version=''. check_all() reads an
empty chart name as "this row has no chart", so INTERNAL DNS left the
frozen/stale-upstream freshness detector entirely — a detector that exists
BECAUSE this very chart's HTTP index froze and was then deleted. Renovate still
covered the component, so this was loss of OUR measurement, not of all
coverage; but Renovate reports "up to date" against a frozen registry, which is
exactly the state only the freshness detector can see. `coverage.py` carried the
same blindness in `_chart_source_for()`.

Four things are pinned here, because each failed independently:

  1. the classic shape still resolves (the CONTROL — a fix that only
     teaches the new shape while breaking the 123 existing ones is not a fix);
  2. the chartRef shape resolves chart name AND version by following the ref;
  3. a ref carrying BOTH `tag` and `digest` resolves to the TAG. The digest is
     an immutability pin, not a version — reporting it as the version makes
     every downstream comparison meaningless, and treating its presence as
     "no version found" re-creates the blind spot;
  4. an unreadable shape is SIGNALLED (self.unresolved_chart_sources +
     degraded.record) rather than returned as empty strings. The only reason
     the regression survived a day is that a silent '' is indistinguishable
     from "no chart here". A silent zero is never a pass.

ADVERSARIAL CHECK (required by docs/sops/audit-script-correctness.md). This
suite was re-run against the PRE-FIX copies of both scripts, via the CAV_PATH /
COV_PATH overrides below: 17 of 26 assertions fail there (15 with only the
pre-fix check-all-versions.py) — k8s-gateway resolves to '', the unresolved
bucket does not exist, coverage.py returns (None, None). So it pins behaviour
rather than describing whatever the tree happens to do.

ONE TRAP when re-running it that way: coverage.py derives REPO_ROOT from its own
file location, so a copy outside the repo finds no kubernetes/ tree and fails
BOTH coverage assertions — including the control — for the wrong reason. A
pre-fix coverage.py must have `REPO_ROOT` reassigned to the real repo before
`_chart_source_for()` is called; with that done the control passes and only the
chartRef case fails, which is the result that actually proves anything.

Run: python3 runbooks/tests/test-helmrelease-chartref-shape.py
"""
import importlib.util
import os
import pathlib
import sys
import tempfile

os.environ["_MISE_ACTIVATED"] = "1"
ROOT = pathlib.Path(__file__).resolve().parents[2]
os.chdir(ROOT)
sys.argv = ["check-all-versions.py"]


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# The module under test is overridable so the adversarial run can point this
# same suite at a pre-fix copy of the script (see the docstring).
CAV_PATH = os.environ.get("CAV_PATH", str(ROOT / "runbooks" / "check-all-versions.py"))
cav = _load(CAV_PATH, "cav")

PASS = FAIL = 0


def check(name, got, want):
    global PASS, FAIL
    if got == want:
        print(f"  PASS  {name}")
        PASS += 1
    else:
        print(f"  FAIL  {name}\n        got {got!r}\n        want {want!r}")
        FAIL += 1


print("HelmRelease chartRef shape tests\n")

# ── Synthetic repo: both shapes side by side, plus two unreadable ones ──────
HR_CLASSIC = """---
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: classic-app
spec:
  chart:
    spec:
      chart: adguard-home
      version: 0.24.1
      sourceRef:
        kind: HelmRepository
        name: rm3l
        namespace: flux-system
  values:
    image:
      repository: adguard/adguardhome
      tag: v0.107.79
"""

# Digest-pinned, exactly as k8s-gateway is on disk: tag AND digest together.
OCI_DIGEST_PINNED = """---
apiVersion: source.toolkit.fluxcd.io/v1
kind: OCIRepository
metadata:
  name: ref-app
spec:
  interval: 1h
  ref:
    tag: 3.7.2
    digest: sha256:3783b0b4bc414e040d6b72e81cf78071542b27a4779d3e462f547bbfd23651fc
  url: oci://ghcr.io/k8s-gateway/charts/k8s-gateway
"""

HR_CHARTREF = """---
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: ref-app
spec:
  chartRef:
    kind: OCIRepository
    name: ref-app
  values:
    fullnameOverride: ref-app
"""

HR_CHARTREF_HELMCHART = """---
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: chart-app
spec:
  chartRef:
    kind: HelmChart
    name: chart-app
"""

HELMCHART = """---
apiVersion: source.toolkit.fluxcd.io/v1
kind: HelmChart
metadata:
  name: chart-app
spec:
  chart: some-chart
  version: 9.8.7
  sourceRef:
    kind: HelmRepository
    name: somewhere
"""

# Unreadable #1: chartRef points at a source CR that does not exist.
HR_DANGLING = """---
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: dangling-app
spec:
  chartRef:
    kind: OCIRepository
    name: nowhere
"""

# Unreadable #2: a shape this parser has never seen. Stands in for the NEXT
# migration — it must announce itself rather than vanish from the denominator.
HR_FUTURE_SHAPE = """---
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: future-app
spec:
  chartRef:
    kind: SomeFutureKind
    name: whatever
"""

# Digest-ONLY ref: genuinely no version, and must be counted as unresolved.
OCI_DIGEST_ONLY = """---
apiVersion: source.toolkit.fluxcd.io/v1
kind: OCIRepository
metadata:
  name: digestonly-app
spec:
  ref:
    digest: sha256:aaaa0b4bc414e040d6b72e81cf78071542b27a4779d3e462f547bbfd23651fc
  url: oci://ghcr.io/example/charts/digestonly
"""

HR_DIGEST_ONLY = """---
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: digestonly-app
spec:
  chartRef:
    kind: OCIRepository
    name: digestonly-app
"""

# A semver RANGE, not a pinned tag. source-controller resolves this against the
# registry at reconcile time, so the string in git is NOT what is deployed.
OCI_SEMVER_RANGE = """---
apiVersion: source.toolkit.fluxcd.io/v1
kind: OCIRepository
metadata:
  name: semverrange-app
spec:
  ref:
    semver: ">=3.7.0 <4.0.0"
  url: oci://ghcr.io/example/charts/semverrange
"""

HR_SEMVER_RANGE = """---
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: semverrange-app
spec:
  chartRef:
    kind: OCIRepository
    name: semverrange-app
"""

# Two DIFFERENT HelmChart objects sharing one (kind, name) key — the shape that
# used to last-win silently, because every HelmChart resolves to url='' and the
# old guard compared url alone.
HELMCHART_DUP_A = """---
apiVersion: source.toolkit.fluxcd.io/v1
kind: HelmChart
metadata:
  name: dup-chart
  namespace: alpha
spec:
  chart: chart-one
  version: 1.0.0
  sourceRef:
    kind: HelmRepository
    name: repo-a
"""

HELMCHART_DUP_B = """---
apiVersion: source.toolkit.fluxcd.io/v1
kind: HelmChart
metadata:
  name: dup-chart
  namespace: beta
spec:
  chart: chart-two
  version: 2.0.0
  sourceRef:
    kind: HelmRepository
    name: repo-b
"""

FILES = {
    "apps/network/classic-app/app/helmrelease.yaml": HR_CLASSIC,
    "apps/network/ref-app/ocirepository.yaml": OCI_DIGEST_PINNED,
    "apps/network/ref-app/helmrelease.yaml": HR_CHARTREF,
    "apps/network/chart-app/helmchart.yaml": HELMCHART,
    "apps/network/chart-app/helmrelease.yaml": HR_CHARTREF_HELMCHART,
    "apps/network/dangling-app/helmrelease.yaml": HR_DANGLING,
    "apps/network/future-app/helmrelease.yaml": HR_FUTURE_SHAPE,
    "apps/network/digestonly-app/ocirepository.yaml": OCI_DIGEST_ONLY,
    "apps/network/digestonly-app/helmrelease.yaml": HR_DIGEST_ONLY,
    "apps/network/semverrange-app/ocirepository.yaml": OCI_SEMVER_RANGE,
    "apps/network/semverrange-app/helmrelease.yaml": HR_SEMVER_RANGE,
    "apps/alpha/dup/helmchart.yaml": HELMCHART_DUP_A,
    "apps/beta/dup/helmchart.yaml": HELMCHART_DUP_B,
}

with tempfile.TemporaryDirectory() as td:
    root = pathlib.Path(td)
    for rel, body in FILES.items():
        p = root / "kubernetes" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)

    checker = cav.VersionChecker(str(root))
    # A pre-fix copy has no chart-source index at all; tolerate its absence so
    # the adversarial run reaches the assertions instead of erroring out.
    if hasattr(checker, "load_chart_sources"):
        checker.load_chart_sources()

    parsed = {}
    for f in checker.find_helmreleases():
        hr = checker.parse_helmrelease(f)
        if hr:
            parsed[hr["name"]] = hr

    # 1. CONTROL — the classic inline shape is untouched.
    check("classic: chart name",
          parsed.get("classic-app", {}).get("chart_name"), "adguard-home")
    check("classic: chart version",
          parsed.get("classic-app", {}).get("chart_version"), "0.24.1")
    check("classic: repository name",
          parsed.get("classic-app", {}).get("repository_name"), "rm3l")

    # 2/3. chartRef -> OCIRepository, digest-pinned: chart from the URL's last
    # segment, version from the TAG, never the digest.
    ref = parsed.get("ref-app", {})
    check("chartRef/OCI: chart name", ref.get("chart_name"), "k8s-gateway")
    check("chartRef/OCI: version is the TAG", ref.get("chart_version"), "3.7.2")
    check("chartRef/OCI: version is not the digest",
          str(ref.get("chart_version", "")).startswith("sha256:"), False)
    # The URL is kept as the PARENT path because get_oci_chart_version()
    # appends /<chart> to it.
    check("chartRef/OCI: repo url is the parent path",
          ref.get("chart_repo_url"), "oci://ghcr.io/k8s-gateway/charts")
    check("chartRef/OCI: repo type", ref.get("chart_repo_type"), "oci")

    # 2b. chartRef -> HelmChart carries its own version.
    hc = parsed.get("chart-app", {})
    check("chartRef/HelmChart: chart name", hc.get("chart_name"), "some-chart")
    check("chartRef/HelmChart: version", hc.get("chart_version"), "9.8.7")

    # 4. LOUD FAILURE — three unreadable rows, each named, none silent.
    unresolved = {u["name"]: u for u in
                  getattr(checker, "unresolved_chart_sources", [])}
    check("dangling chartRef is counted unresolved",
          "dangling-app" in unresolved, True)
    check("unknown chartRef kind is counted unresolved",
          "future-app" in unresolved, True)
    check("digest-ONLY ref is counted unresolved",
          "digestonly-app" in unresolved, True)
    check("unresolved rows carry a reason",
          all(bool(u.get("reason")) for u in unresolved.values()) and bool(unresolved),
          True)
    # A resolved row must NEVER be listed — over-reporting would train the
    # operator to ignore the signal, which is the same failure by another road.
    check("resolved rows are not listed as unresolved",
          {"classic-app", "ref-app", "chart-app"} & set(unresolved), set())
    # The denominator: everything except the deliberately-broken rows.
    check("resolved count",
          sum(1 for h in parsed.values()
              if h["chart_name"] and h["chart_version"]), 3)

    # Carried out of the temp-dir scope for the hardening assertions below.
    unresolved_rows = list(getattr(checker, "unresolved_chart_sources", []))
    unresolved_names = set(unresolved)
    semver_row = parsed.get("semverrange-app", {})
    # The collision must be RECORDED, not silently resolved by last-wins. It is
    # recorded without a `component=`, i.e. a section-wide veto, because when
    # two objects share a key we cannot know which rows the wrong one touched.
    collision_recorded = any(
        "COLLISION" in r for r in getattr(checker.degraded, "reasons", []))

def _emitted_severity_for_unresolved():
    """Severity `_emit_findings()` actually gives an unresolved-chart-source row.

    Asserted on the EMITTED value rather than by reading the source, because the
    severity is the whole question: at `monitor` the row never reaches the
    section verdict, and for a component whose only remaining version signal is
    this bucket (csi-driver-smb, F-2e76c058) that is indistinguishable from the
    silence this file exists to prevent.
    """
    class _W:
        enabled = True

        def __init__(self):
            self.items = []

        def emit(self, **kw):
            self.items.append(kw)

    w = _W()
    stub = cav.VersionChecker.__new__(cav.VersionChecker)
    stub.unresolved_chart_sources = [
        {"name": "probe-app", "file_path": "x/y.yaml", "reason": "because"}]
    stub.results = []
    stub.external_infra_results = []
    cav._emit_findings(w, stub, "evidence.md")
    rows = [i for i in w.items if "UNRESOLVED" in i.get("title", "")]
    return rows[0]["severity"] if len(rows) == 1 else f"{len(rows)} rows emitted"


# ── The real repo: k8s-gateway is the live instance of the bug ──────────────
live = cav.VersionChecker(str(ROOT))
if hasattr(live, "load_chart_sources"):
    live.load_chart_sources()
live_rows = {}
for f in live.find_helmreleases():
    hr = live.parse_helmrelease(f)
    if hr:
        live_rows[hr["name"]] = hr

kg = live_rows.get("k8s-gateway", {})
check("live k8s-gateway: chart name", kg.get("chart_name"), "k8s-gateway")
check("live k8s-gateway: version resolved (non-empty)",
      bool(kg.get("chart_version")), True)
# Controls from the live tree, classic shape, must still resolve.
for name, want_chart in (("adguard-home", "adguard-home"),
                         ("longhorn", "longhorn"),
                         ("authentik", "authentik")):
    check(f"live control {name}: chart name",
          live_rows.get(name, {}).get("chart_name"), want_chart)
# k8s-gateway specifically must NOT be in the unresolved bucket — that is the
# regression this suite pins. The bucket is deliberately NOT asserted empty:
# the live tree legitimately acquires new chart-source shapes (csi-driver-smb
# moved to a GitRepository source on the same day, which has no version in git
# at all), and asserting emptiness would turn a parser test into a repo-state
# lint that blocks other agents' commits on the shared pre-commit hook. The
# bucket's contents are PRINTED instead, so a new shape is still visible here.
live_unresolved = [u["name"] for u in
                   getattr(live, "unresolved_chart_sources", [])]
check("live k8s-gateway is NOT in the unresolved bucket",
      "k8s-gateway" in live_unresolved, False)
if live_unresolved:
    print(f"  note  live unresolved chart sources (informational): "
          f"{', '.join(sorted(live_unresolved))}")

# The loud-failure MECHANISM must exist at all. Asserted structurally because
# every behavioural assertion about it is vacuous on a parser that simply has
# no bucket — which is exactly the pre-fix state.
check("the unresolved bucket exists",
      isinstance(getattr(live, "unresolved_chart_sources", None), list), True)
check("chart-source index is loaded before parsing",
      callable(getattr(live, "load_chart_sources", None)), True)

# ── coverage.py carried the same blindness ─────────────────────────────────
# The `current` versions are READ FROM THE MANIFESTS, never hardcoded.
# `_chart_source_for()` pins the HelmRelease by matching item['current'] against
# the deployed version, so a literal here would silently stop matching at the
# next routine chart bump — and because run-all.sh is a fail-closed pre-commit
# gate for any staged runbooks/ script, that would block an unrelated commit in
# someone else's session. Same brittleness the live-bucket assertion avoids.
import yaml as _yaml

KG_OCI = ROOT / "kubernetes/apps/network/internal/k8s-gateway/ocirepository.yaml"
AD_HR = ROOT / "kubernetes/apps/network/internal/adguard-home/app/helmrelease.yaml"
kg_tag = ((_yaml.safe_load(KG_OCI.read_text()) or {})
          .get("spec", {}).get("ref", {}).get("tag"))
ad_ver = None
for _d in _yaml.safe_load_all(AD_HR.read_text()):
    if isinstance(_d, dict) and _d.get("kind") == "HelmRelease":
        ad_ver = (((_d.get("spec") or {}).get("chart") or {})
                  .get("spec") or {}).get("version")
check("fixture: k8s-gateway tag read from the manifest", bool(kg_tag), True)
check("fixture: adguard-home version read from the manifest", bool(ad_ver), True)

cov = _load(os.environ.get("COV_PATH", str(ROOT / "runbooks" / "coverage.py")),
            "cov_chartref")
check("coverage: chartRef chart source resolves",
      cov._chart_source_for({"namespace": "network", "current": str(kg_tag),
                             "component": "k8s-gateway", "target": "9.9.9"}),
      ("k8s-gateway", "oci://ghcr.io/k8s-gateway/charts"))
check("coverage: classic chart source still resolves (control)",
      cov._chart_source_for({"namespace": "network", "current": str(ad_ver),
                             "component": "adguard-home", "target": "9.9.9"}),
      ("adguard-home", "https://helm-charts.rm3l.org"))
# A semver RANGE is not a version: it must not satisfy the `current` match.
# Exercised against a TEMP tree with REPO_ROOT repointed — asserting it against
# the real repo would pass vacuously, because no OCIRepository here uses semver
# and a missing key looks identical to a correctly-rejected range.
with tempfile.TemporaryDirectory() as td2:
    root2 = pathlib.Path(td2)
    d2 = root2 / "kubernetes" / "apps" / "network" / "semverrange-app"
    d2.mkdir(parents=True)
    (d2 / "ocirepository.yaml").write_text(OCI_SEMVER_RANGE)
    (d2 / "helmrelease.yaml").write_text(HR_SEMVER_RANGE)
    cov2 = _load(os.environ.get("COV_PATH", str(ROOT / "runbooks" / "coverage.py")),
                 "cov_semver")
    cov2.REPO_ROOT = root2
    entry = cov2._chart_ref_sources().get(("OCIRepository", "semverrange-app"))
    check("coverage: a semver range resolves to NO version",
          (entry or ("?", "?", "?"))[1], "")
    # …and therefore can never be matched as the deployed version, whatever
    # `current` says — including the range string itself.
    check("coverage: a semver range never matches as `current`",
          [cov2._chart_source_for({"namespace": "network", "current": c,
                                   "component": "semverrange-app",
                                   "target": "9.9.9"})
           for c in (">=3.7.0 <4.0.0", "3.7.2", "")],
          [(None, None), (None, None), (None, None)])

# ── Hardening pinned after the 97c3e913 review ─────────────────────────────
# 1. `ref.semver` is a RANGE, not a pinned version.
check("semver-range ref is counted unresolved",
      "semverrange-app" in unresolved_names, True)
check("semver-range reason names the range, not a version",
      any("RANGE" in u["reason"] for u in unresolved_rows
          if u["name"] == "semverrange-app"), True)
check("semver-range resolves to NO version",
      semver_row.get("chart_version"), "")
# 2. Two different CRs sharing a (kind, name) key must not silently last-win.
check("chart-source collision is recorded as a degradation",
      collision_recorded, True)
# 3. An OCI path's generic container segment is not a GitHub repo.
live_checker = live
check("chart repo info: generic `charts` segment is not used as the repo",
      live_checker.get_chart_repo_info(
          "some-chart", "x", "oci://ghcr.io/some-owner/charts"),
      ("some-owner", "some-chart"))
check("chart repo info: a real middle segment is still used",
      live_checker.get_chart_repo_info(
          "zzz-unmapped", "x", "oci://ghcr.io/some-owner/real-repo"),
      ("some-owner", "real-repo"))
# The one live chartRef chart must resolve to a repo that EXISTS (verified
# against the GitHub API 2026-09-11: the underscore form is the real one).
check("chart repo info: k8s-gateway maps to its real (underscore) repo",
      live_checker.get_chart_repo_info(
          "k8s-gateway", "k8s-gateway", "oci://ghcr.io/k8s-gateway/charts"),
      ("k8s-gateway", "k8s_gateway"))
# 4. The unresolved finding must reach the section verdict. `monitor` would
#    keep the SOLE remaining signal for a component off the board.
check("unresolved rows are emitted at warning, not monitor",
      _emitted_severity_for_unresolved(), "warning")

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
