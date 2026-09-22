#!/usr/bin/env python3
"""Regression test: the Envoy DATA-PLANE image is in the version universe —
measured when git names it, loudly NOT MEASURED when it does not.

F-41f0d855, measured 2026-09-22:

    rg -c envoy runbooks/check-all-versions.py            -> 0        # BEFORE
    Envoy Gateway v1.9.1 default data-plane image (api/v1alpha1/shared_types.go)
        -> docker.io/envoyproxy/envoy:distroless-v1.39.1@sha256:...
    kubernetes/apps/network/envoy-gateway/app/gatewayclass.yaml EnvoyProxy
        -> spec.provider.kubernetes.envoyDeployment.container.image UNSET

Envoy Gateway renders the data-plane Deployment from the EnvoyProxy CR, so no
manifest in git carries a pod template and the raw-manifest walker (which
keys on Deployment/StatefulSet/DaemonSet/CronJob/Job) never saw it. The
controller's compiled-in default runs: invisible to git, to Renovate and to
this check — for the internet-facing gateway.

THE CHOICE, and why: this file is git-only for every in-cluster component
(the sole live probe is talosctl, for node firmware). Its answer to "the image
comes from a default, not from git" has always been to NAME it in git — every
sidecar image here is pinned for that reason — so the walker now reads
`EnvoyProxy.spec.provider.kubernetes.envoyDeployment.container.image` exactly
as it reads a Deployment's containers. Until the field is pinned, the honest
answer is NOT MEASURED, delivered by the same three signals an unresolved
chart source gets (stderr, a report section, a per-component auto-close veto)
— never a silent skip. Reading the live Deployment instead would tie the
universe to cluster reachability and still leave the image unpinned.

And the pin alone would not have been enough: measured with the real picker,
`distroless-v1.39.1` was NOT version-shaped (key (0,0,0,0,0)) and the picker
proposed the bare `v1.40.0` — a silent distroless -> full-image base swap
dressed as a minor. Envoy publishes its build flavour as a PREFIX; that is now
canonicalised through the one tag chokepoint so the flavour is kept.

Run: python3 runbooks/tests/test-envoy-rendered-image.py
"""

from __future__ import annotations

import contextlib
import importlib.util
import inspect
import io
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


cav = _load("cav", "runbooks/check-all-versions.py")
VC = cav.VersionChecker

FAILURES: list[str] = []
ENVOY = "docker.io/envoyproxy/envoy"
PIN = "distroless-v1.39.1"
DIGEST = "@sha256:" + "e" * 64
ENVOY_TAGS = ["v1.39.1", PIN, "v1.40.0", "distroless-v1.40.0", "debug-v1.40.0",
              "tools-v1.40.0", "dev", "distroless-dev", "v1.41.0-rc1", "distroless-v1.41.0-rc1"]
BAD_MARKERS = ("Traceback", "usage:", "error")


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


class FakeLog:
    def __init__(self):
        self.records = []

    def record(self, scope, dependency, detail="", *, component=None):
        self.records.append((scope, dependency, detail, component))


def envoyproxy_yaml(image: str | None) -> str:
    container = f"        container:\n          image: {image}\n" if image else ""
    return f"""---
apiVersion: gateway.networking.k8s.io/v1
kind: GatewayClass
metadata:
  name: envoy
spec:
  controllerName: gateway.envoyproxy.io/gatewayclass-controller
---
apiVersion: gateway.envoyproxy.io/v1alpha1
kind: EnvoyProxy
metadata:
  name: envoy-proxy-config
spec:
  provider:
    type: Kubernetes
    kubernetes:
      envoyDeployment:
        replicas: 3
{container}      envoyPDB:
        minAvailable: 2
"""


def walk(root: Path):
    """The real walker over `root`, with its output captured and screened:
    an instrument that crashed or printed an error must not read as a count."""
    ck = VC(str(root))
    ck.degraded = FakeLog()
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        entries = ck.find_raw_manifest_workloads()
    text = out.getvalue() + err.getvalue()
    for marker in BAD_MARKERS:
        if marker.lower() in text.lower():
            raise SystemExit(f"ABORT: walker output carries {marker!r} — broken instrument, not a count:\n{text[:800]}")
    return ck, entries


def fixture(image: str | None) -> Path:
    root = Path(tempfile.mkdtemp(prefix="envoy-fixture-"))
    app = root / "kubernetes" / "apps" / "network" / "envoy-gateway" / "app"
    app.mkdir(parents=True)
    (app / "gatewayclass.yaml").write_text(envoyproxy_yaml(image))
    return root


def main() -> int:
    print("test-envoy-rendered-image")

    # ── the tag machinery: a PREFIX flavour is a flavour ───────────────
    ck = VC(str(REPO))
    check("distroless-v1.39.1 canonicalises to the suffix form",
          VC._canonical_tag(PIN) == "v1.39.1-distroless", VC._canonical_tag(PIN))
    check("...digest-pinned too", VC._canonical_tag(PIN + DIGEST) == "v1.39.1-distroless")
    check("its variant is 'distroless'", VC._tag_variant(PIN) == "distroless", VC._tag_variant(PIN))
    check("a compound prefix keeps both parts", VC._tag_variant("contrib-debug-v1.39.1") == "contrib-debug")
    check("it is version-shaped to the key and the parser",
          VC._semver_tag_key(PIN)[:3] == (1, 39, 1) and ck.parse_version(PIN) == (1, 39, 1),
          f"{VC._semver_tag_key(PIN)} {ck.parse_version(PIN)}")
    check("it is not rolling", not ck.is_rolling_tag(PIN))
    check("suffix variants are untouched (8.10.0-alpine)",
          VC._canonical_tag("8.10.0-alpine") == "8.10.0-alpine" and VC._tag_variant("8.10.0-alpine") == "alpine")
    check("a bare version and a floating tag are untouched",
          VC._canonical_tag("v1.39.1") == "v1.39.1" and VC._canonical_tag("dev") == "dev"
          and ck.is_rolling_tag("dev"))
    pick = ck._pick_latest_semver_tag(ENVOY_TAGS, PIN, ENVOY)
    check("the picker proposes the SAME-flavour successor distroless-v1.40.0",
          pick == "distroless-v1.40.0", str(pick))
    check("...never the bare v1.40.0 (a base-image swap), never a pre-release",
          pick not in ("v1.40.0", "distroless-v1.41.0-rc1"))
    check("from the bare pin the bare successor is still chosen",
          ck._pick_latest_semver_tag(ENVOY_TAGS, "v1.39.1", ENVOY) == "v1.40.0")
    check("the hop is reportable and a MINOR",
          ck.is_reportable_update(PIN, "distroless-v1.40.0")
          and ck.assess_update_complexity(PIN, "distroless-v1.40.0")["type"] == "minor")
    check("digest-pinned and bare forms of the same tag are EQUAL",
          ck.tags_are_equal(PIN, PIN + DIGEST) and not ck.is_reportable_update(PIN, PIN + DIGEST))
    check("the pinned ref splits to repo + flavoured tag",
          cav._split_image_ref(f"{ENVOY}:{PIN}{DIGEST}") == (ENVOY, PIN))

    # ── the walker: git names the image -> it is a tracked workload ────
    ck, entries = walk(fixture(f"{ENVOY}:{PIN}{DIGEST}"))
    check("a pinned EnvoyProxy yields exactly one workload entry", len(entries) == 1, str(entries))
    e = entries[0] if entries else {}
    img = (e.get("images") or [{}])[0]
    check("...named after the CR, in the app's namespace",
          e.get("name") == "envoy-proxy-config" and e.get("namespace") == "network", str(e))
    check("...with the envoy repository and the flavoured tag",
          img.get("repository") == ENVOY and img.get("tag") == PIN, str(img))
    check("...at the EnvoyProxy image path",
          img.get("path") == "spec.provider.kubernetes.envoyDeployment.container.image", str(img))
    check("...HelmRelease-shaped so check_all()'s image loop takes it unchanged",
          e.get("chart_name") == "" and e.get("repository_name") == "")
    check("...and nothing is recorded as unmeasured",
          ck.unresolved_rendered_images == [] and ck.degraded.records == [])

    # ── the walker: git does NOT name it -> NOT MEASURED, three signals ─
    ck, entries = walk(fixture(None))
    check("an unpinned EnvoyProxy yields NO workload entry (nothing to compare)", entries == [])
    rows = ck.unresolved_rendered_images
    check("signal 1: a report row names the CR and the unset field",
          len(rows) == 1 and rows[0]["kind"] == "EnvoyProxy" and rows[0]["name"] == "envoy-proxy-config"
          and "container.image" in rows[0]["reason"], str(rows))
    check("...and the image the default resolves to", rows and rows[0]["image_hint"] == ENVOY)
    recs = ck.degraded.records
    check("signal 2: a coverage-gap record, scoped to that one component",
          len(recs) == 1 and recs[0][3] == cav.component_key("image", ENVOY), str(recs))
    md = ck.generate_markdown_report()
    check("signal 3: the report carries the NOT version-checked section with the row",
          "Controller-rendered images not named in git" in md and "`EnvoyProxy/envoy-proxy-config`" in md)
    check("...and the emitted finding is wired to the same list",
          "unresolved_rendered_images" in inspect.getsource(cav._emit_findings))

    # ── the REAL repo: pinned or recorded, never neither ───────────────
    ck, entries = walk(REPO)
    if not entries:
        raise SystemExit("ABORT: the real walker returned no raw workloads at all — broken instrument")
    pinned = [e for e in entries
              if any("envoyDeployment" in (i.get("path") or "") for i in e.get("images") or [])]
    recorded = [r for r in ck.unresolved_rendered_images if r["kind"] == "EnvoyProxy"]
    check(f"real repo: the EnvoyProxy is either measured ({len(pinned)}) or recorded "
          f"as NOT MEASURED ({len(recorded)}) — never absent",
          (len(pinned) + len(recorded)) >= 1)
    check("real repo: a measured EnvoyProxy image parses (no silent 'could not check')",
          all(not ck.is_rolling_tag(i["tag"]) and ck.parse_version(i["tag"])
              for e in pinned for i in e["images"]))

    # ── COMMISSIONING STRAWS ───────────────────────────────────────────
    real_kinds = VC._RENDERED_IMAGE_KINDS
    real_canon = VC.__dict__["_canonical_tag"]
    try:
        VC._RENDERED_IMAGE_KINDS = {}                       # the pre-fix walker
        ck, entries = walk(fixture(f"{ENVOY}:{PIN}"))
        check("commissioning: with EnvoyProxy unknown to the walker the pinned fixture "
              "yields nothing AND records nothing — the silent skip the assertions "
              "above would FAIL on",
              entries == [] and ck.unresolved_rendered_images == [])
        VC._RENDERED_IMAGE_KINDS = real_kinds
        VC._canonical_tag = classmethod(lambda cls, t: cls._strip_digest(t))   # the pre-fix chokepoint
        straw_pick = VC(str(REPO))._pick_latest_semver_tag(ENVOY_TAGS, PIN, ENVOY)
        check("commissioning: with the prefix flavour not canonicalised the picker "
              "proposes the bare v1.40.0 again — i.e. the flavour assertion would FAIL",
              straw_pick == "v1.40.0", str(straw_pick))
    finally:
        VC._RENDERED_IMAGE_KINDS = real_kinds
        VC._canonical_tag = real_canon

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
