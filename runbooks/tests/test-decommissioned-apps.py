#!/usr/bin/env python3
"""
Regression tests for runbooks/lib/decommissioned_apps.py (2026-10-05).

ac7bf0e0 decommissioned 16 apps by COMMENTING OUT their `./<app>/ks.yaml`
entry in the parent namespace kustomization, leaving the directories in git.
check-all-versions.py rglob'd kubernetes/apps/ and kept emitting version
findings for them (actual-budget became a planner-dispatch group).

The fix must stay NARROW: "disabled" requires a commented reference AND no live
reference. Absence alone must never disable a directory — narrowing a detector
to kill a false positive has repeatedly created false negatives here — so most
of these cases pin the ENABLED direction.

Run: python3 runbooks/tests/test-decommissioned-apps.py
"""
import importlib.util
import os
import sys
import tempfile
import textwrap
from pathlib import Path

os.environ.setdefault("_MISE_ACTIVATED", "1")
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "runbooks"))

from lib.decommissioned_apps import (  # noqa: E402
    find_disabled_app_dirs, is_disabled, skip_line,
)

FAILS: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        FAILS.append(msg)


def write(root: Path, rel: str, body: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(body))


def app(root: Path, ns: str, name: str, ks_name: str = "ks.yaml") -> None:
    write(root, f"kubernetes/apps/{ns}/{name}/{ks_name}", f"""\
        apiVersion: kustomize.toolkit.fluxcd.io/v1
        kind: Kustomization
        metadata:
          name: {name}
        spec:
          path: ./kubernetes/apps/{ns}/{name}/app
        """)
    write(root, f"kubernetes/apps/{ns}/{name}/app/helmrelease.yaml", "kind: HelmRelease\n")


def disabled_names(root: Path) -> set[str]:
    return {d.rel.removeprefix("kubernetes/apps/") for d in find_disabled_app_dirs(root)}


def fixture() -> Path:
    return Path(tempfile.mkdtemp(prefix="decomm-"))


def test_commented_only_is_disabled():
    r = fixture()
    for a in ("live", "gone"):
        app(r, "office", a)
    write(r, "kubernetes/apps/office/kustomization.yaml", """\
        resources:
         - ./live/ks.yaml
         # - ./gone/ks.yaml  # DISABLED 2026-10-04 (operator: decommissioned)
        """)
    d = disabled_names(r)
    check(d == {"office/gone"}, f"commented-only => disabled (got {sorted(d)})")
    dis = find_disabled_app_dirs(r)
    check(is_disabled(r / "kubernetes/apps/office/gone/app/helmrelease.yaml", dis),
          "files inside a disabled dir are disabled")
    check(not is_disabled(r / "kubernetes/apps/office/live/app/helmrelease.yaml", dis),
          "files inside a live dir are not disabled")
    check(not is_disabled(r / "kubernetes/apps/office/gone-two/x.yaml", dis),
          "prefix-sibling `gone-two` is not inside `gone`")
    line = skip_line(dis)
    check("skipped 1 decommissioned" in line and "office/gone" in line,
          f"skip line names the dir: {line!r}")


def test_commented_plus_uncommented_is_enabled():
    r = fixture()
    app(r, "office", "both")
    write(r, "kubernetes/apps/office/kustomization.yaml", """\
        resources:
          # - ./both/ks.yaml  # old entry
          - ./both/ks.yaml
        """)
    check(disabled_names(r) == set(), "commented + uncommented => enabled")


def test_absent_is_enabled():
    r = fixture()
    app(r, "office", "orphan")
    app(r, "office", "live")
    write(r, "kubernetes/apps/office/kustomization.yaml", """\
        resources:
          - ./live/ks.yaml
        """)
    check(disabled_names(r) == set(),
          "absent reference => NOT disabled (absence is never evidence)")
    check(skip_line([]).startswith("skipped 0"), "empty skip line still printed")


def test_path_variants():
    r = fixture()
    for a in ("a1", "a2", "a3", "a4", "a6", "keep"):
        app(r, "ns", a)
    app(r, "ns", "a5", ks_name="ks.yml")
    write(r, "kubernetes/apps/ns/kustomization.yaml", """\
        resources:
          - ./keep/ks.yaml
          #- ./a1/ks.yaml
          # - a2/ks.yaml
          # - "./a3/ks.yaml"
          ## - './a4/ks.yaml'   # trailing comment
          # - ./a5/ks.yml
          # - ./a6
        """)
    d = disabled_names(r)
    want = {f"ns/a{i}" for i in range(1, 7)}
    check(d == want, f"ks.yaml path variants all recognised (got {sorted(d)})")


def test_live_variant_keeps_enabled():
    r = fixture()
    for a in ("v1", "v2", "v3"):
        app(r, "ns", a)
    write(r, "kubernetes/apps/ns/kustomization.yaml", """\
        resources:
          # - ./v1/ks.yaml
          - v1/ks.yaml
          # - ./v2/ks.yaml
          - "./v2"
          # - ./v3/ks.yaml
          - ./v3/ks.yml
        """)
    check(disabled_names(r) == set(),
          "a live reference in ANY path spelling keeps the dir enabled")


def test_commented_plain_manifest_is_not_a_dir_disable():
    r = fixture()
    app(r, "home", "z2m")
    write(r, "kubernetes/apps/home/kustomization.yaml", "resources:\n  - ./z2m/ks.yaml\n")
    write(r, "kubernetes/apps/home/z2m/app/kustomization.yaml", """\
        resources:
          - ./helmrelease.yaml
          #- ./service.yaml
          #- ./deployment.yaml
        """)
    check(disabled_names(r) == set(),
          "commented plain manifest (#- ./deployment.yaml) does not disable its dir")


def test_flux_spec_path_keeps_enabled():
    r = fixture()
    app(r, "ns", "wired")
    app(r, "ns", "other")
    write(r, "kubernetes/apps/ns/kustomization.yaml", """\
        resources:
          - ./other/ks.yaml
          # - ./wired/ks.yaml
        """)
    # another, LIVE Flux Kustomization points into the commented dir
    write(r, "kubernetes/apps/ns/other/ks.yaml", """\
        apiVersion: kustomize.toolkit.fluxcd.io/v1
        kind: Kustomization
        metadata:
          name: other
        spec:
          path: ./kubernetes/apps/ns/wired/app
        """)
    check(disabled_names(r) == set(),
          "a live Flux spec.path into the dir keeps it enabled (wired another way)")


def test_own_ks_spec_path_does_not_self_enable():
    r = fixture()
    app(r, "ns", "self")      # its own ks.yaml spec.path points at ./self/app
    write(r, "kubernetes/apps/ns/kustomization.yaml", "resources:\n  # - ./self/ks.yaml\n")
    check(disabled_names(r) == {"ns/self"},
          "the dir's own ks.yaml spec.path does not count as a live reference")


def test_namespace_level():
    r = fixture()
    app(r, "office", "x")
    app(r, "media", "y")
    write(r, "kubernetes/apps/office/kustomization.yaml", "resources:\n  - ./x/ks.yaml\n")
    write(r, "kubernetes/apps/media/kustomization.yaml", "resources:\n  - ./y/ks.yaml\n")
    write(r, "kubernetes/apps/kustomization.yaml", """\
        resources:
          - ./media
          # - ./office   # DISABLED
        """)
    dis = find_disabled_app_dirs(r)
    check({d.rel for d in dis} == {"kubernetes/apps/office"},
          f"commented namespace entry disables the namespace dir (got {[d.rel for d in dis]})")
    check(is_disabled(r / "kubernetes/apps/office/x/app/helmrelease.yaml", dis),
          "apps inside a disabled namespace are disabled")
    check(not is_disabled(r / "kubernetes/apps/media/y/app/helmrelease.yaml", dis),
          "apps in a live namespace are not")


def test_unparseable_kustomization_fails_toward_enabled():
    r = fixture()
    app(r, "ns", "p")
    write(r, "kubernetes/apps/ns/kustomization.yaml", """\
        resources: [
          # - ./p/ks.yaml
          - ./p/ks.yaml
        """)
    check(disabled_names(r) == set(),
          "unparseable kustomization: regex fallback still sees the live ref")


def test_live_repo():
    """The real tree as of 2026-10-05: exactly the 16 ac7bf0e0 decommissions."""
    d = disabled_names(REPO)
    expected = {
        "ai/hermes-agent", "ai/librechat", "home-automation/scrypted-nvr",
        "office/actual-budget", "office/omni-tools",
    } | {f"my-software-showcase/{a}" for a in (
        "globalmobility", "holm-backend", "ibgastro", "inbewegung",
        "kfa-medienarchiv", "mangold-smarthomeadvisor", "max-jung", "ordiga",
        "see-edv-ibspm", "stepbystepguide", "zuhause-betreut")}
    # Superset, not equality: a LATER decommission is legitimate. What must
    # never happen is an ACTIVE app being swept in.
    check(expected <= d, f"all 16 decommissioned dirs detected (missing {sorted(expected - d)})")
    for active in ("haarfabrik", "metaldyne", "u-zeit", "uzeit-de"):
        check(f"my-software-showcase/{active}" not in d, f"active showcase app {active} stays in scope")
    for active in ("office/affine", "office/nextcloud", "home-automation/zigbee2mqtt",
                   "home-automation/home-assistant", "ai/openclaw"):
        check(active not in d, f"{active} stays in scope")


def test_check_all_versions_enumeration():
    spec = importlib.util.spec_from_file_location(
        "cav", REPO / "runbooks" / "check-all-versions.py")
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except ImportError as e:   # requests/packaging absent in a bare python3
        print(f"  skip check-all-versions enumeration ({e}) — run with .venv/bin/python3")
        return
    vc = mod.VersionChecker(str(REPO))
    hrs = [str(p.relative_to(REPO)) for p in vc.find_helmreleases()]
    check(not any("/office/actual-budget/" in p for p in hrs),
          "check-all-versions: actual-budget HelmRelease not enumerated")
    check(not any("/ai/hermes-agent/" in p for p in hrs),
          "check-all-versions: hermes-agent HelmRelease not enumerated")
    raw = [w['file_path'] for w in vc.find_raw_manifest_workloads()]
    check(not any(is_disabled(REPO / p if not os.path.isabs(p) else p, vc.decommissioned)
                  for p in raw),
          "check-all-versions: no raw workload from a decommissioned dir")
    every = hrs + [str(p) for p in raw]
    for active in ("haarfabrik", "metaldyne", "u-zeit", "uzeit-de"):
        check(any(f"/my-software-showcase/{active}/" in p for p in every),
              f"check-all-versions: active showcase app {active} still enumerated")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(name)
            fn()
    if FAILS:
        print(f"\n{len(FAILS)} FAILED")
        sys.exit(1)
    print("\nall passed")
