"""Regression test: HelmRepository CRs under repositories/oci/ are loaded
(2026-09-24).

`load_helmrepositories()` globbed only `kubernetes/flux/meta/repositories/helm/`.
The `type: oci` HelmRepositories live in the sibling `oci/` directory, so every
chart sourced from one (bitnami, controlplaneio, coredns, librechat, n8n,
spegel, stakater) hit get_latest_chart_version()'s silent
`repo_name not in self.helm_repositories` branch: "could not check latest",
no degradation, no finding. Measured misses on the day: a bitnami mariadb chart
MAJOR, flux-operator/flux-instance minors, and several patches.

Asserted against the REAL repo tree (the directory layout is the thing that
broke), plus a straw proving an oci-only fixture is picked up.

Run:  python3 runbooks/tests/test-version-check-oci-helmrepos.py
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

import yaml

_REPO = Path(__file__).resolve().parents[2]
os.environ.setdefault("_MISE_ACTIVATED", "1")
sys.path.insert(0, str(_REPO / "runbooks"))
_spec = importlib.util.spec_from_file_location(
    "cav", _REPO / "runbooks" / "check-all-versions.py")
cav = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cav)

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


def _declared(sub: str) -> set[str]:
    names = set()
    for f in (_REPO / "kubernetes/flux/meta/repositories" / sub).glob("*.yaml"):
        for doc in yaml.safe_load_all(f.read_text()):
            if doc and doc.get("kind") == "HelmRepository":
                names.add(doc["metadata"]["name"])
    return names


print("real repo tree:")
vc = cav.VersionChecker(str(_REPO))
vc.load_helmrepositories()
loaded = set(vc.helm_repositories)
oci = _declared("oci")
helm = _declared("helm")
check("repositories/oci/ declares at least one HelmRepository", bool(oci))
check("every oci/ HelmRepository is loaded", oci <= loaded,
      f"missing={sorted(oci - loaded)}")
check("every helm/ HelmRepository is still loaded", helm <= loaded,
      f"missing={sorted(helm - loaded)}")
check("oci/ repos keep type=oci",
      all(vc.helm_repositories[n]["type"] == "oci" for n in oci & loaded))

print("fixture (oci-only):")
with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    (root / "kubernetes/flux/meta/repositories/helm").mkdir(parents=True)
    (root / "kubernetes/flux/meta/repositories/oci").mkdir(parents=True)
    (root / "kubernetes/flux/meta/repositories/oci/x.yaml").write_text(
        "apiVersion: source.toolkit.fluxcd.io/v1\nkind: HelmRepository\n"
        "metadata:\n  name: straw\nspec:\n  type: oci\n  url: oci://example.invalid/charts\n")
    fx = cav.VersionChecker(str(root))
    fx.load_helmrepositories()
    check("oci-only fixture repo is loaded", "straw" in fx.helm_repositories,
          f"loaded={sorted(fx.helm_repositories)}")

if FAILURES:
    print(f"\nFAILED: {len(FAILURES)}")
    sys.exit(1)
print("\nOK")
