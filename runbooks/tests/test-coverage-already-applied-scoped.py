"""Regression test: `already_applied()` must judge the ITEM'S OWN image
(F-a52c69d7, the second disjunct, 2026-09-21).

`already_applied()` proves a bump landed by asking whether the target version
appears under `kubernetes/apps/<ns>/` and the current one does not. That
question is namespace-wide, and a SECOND IMAGE legitimately still pinning the
old version answers it wrongly:

    memgraph/lab            3.13.1 -> 3.13.2   <- bumped
    memgraph/memgraph-mage  3.13.1             <- deliberately NOT bumped

so `cur not in txt` was False, the landed bump never self-cleared, and the AUTO
lane kept re-proposing it — an unattended bump that risked dragging mage along,
a change the operator had explicitly excluded ("lab controller only, mage
unchanged"). 12 of 18 namespaces carry that shape (>1 repo, >1 distinct tag).

DIRECTION OF FAILURE IS THE WHOLE RISK HERE. Repo-scoping is strictly MORE
permissive than the namespace-wide test: it can return True where the old test
returned False, and a false "already applied" SILENTLY DROPS A REAL UPDATE —
the crack class this file exists to prevent. So it may engage only when exactly
one repository resolves AND that repository is actually found in git. Every
ambiguous shape below must fall back rather than assume.

THE FIXTURES ARE SYNTHETIC ON PURPOSE. The live memgraph instance self-resolved
on 2026-09-21 (the snapshot caught up to the git bump), and measured across all
22 live rows this change is a no-op today. A test anchored to live repo state
would therefore assert nothing now and break the day a row legitimately flips.

Run:  python3 runbooks/tests/test-coverage-already-applied-scoped.py
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
os.environ.setdefault("_MISE_ACTIVATED", "1")
sys.path.insert(0, str(_REPO / "runbooks"))
_spec = importlib.util.spec_from_file_location("cov", _REPO / "runbooks" / "coverage.py")
cov = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cov)

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


class Fixture:
    """A throwaway kubernetes/apps/testns/ tree."""

    def __init__(self, files):
        self._files = files

    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        ns = root / "kubernetes" / "apps" / "testns"
        ns.mkdir(parents=True)
        for n, t in self._files.items():
            (ns / n).write_text(t)
        self._orig = cov.REPO_ROOT
        cov.REPO_ROOT = root
        cov._NS_TEXT_CACHE.clear()
        return self

    def __exit__(self, *a):
        cov.REPO_ROOT = self._orig
        cov._NS_TEXT_CACHE.clear()
        self._tmp.cleanup()


# The live shape that motivated the finding: two images, one bumped, one not.
MEMGRAPH_HR = """apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
spec:
  values:
    controllers:
      memgraph:
        containers:
          app:
            image:
              repository: memgraph/memgraph-mage
              tag: "3.13.1"
          init:
            image:
              repository: busybox
              tag: 1.38.0@sha256:dc2d74b28e4cf8984fa52af1f39bc7c3d9c73760b41a74d629f5d11b1ab28616
      lab:
        containers:
          app:
            image:
              repository: memgraph/lab
              tag: "3.13.2"
"""


def lab(**kw):
    base = {"component": "memgraph", "namespace": "testns", "kind": "image",
            "current": "3.13.1", "target": "3.13.2", "image_repo": "memgraph/lab"}
    base.update(kw)
    return base


def main() -> int:
    print(__doc__.strip().splitlines()[0])
    print()

    # --- THE DEFECT ---------------------------------------------------------
    with Fixture({"hr.yaml": MEMGRAPH_HR}):
        check("a bump proven on THIS item's image is applied, although a sibling "
              "image legitimately still pins the old version",
              cov.already_applied(lab()))

        # Commissioning: the case must be non-trivial. With the scoped branch
        # neutralised the item falls back to the namespace-wide test, which is
        # exactly the pre-fix behaviour and must NOT see it.
        orig = cov._namespace_repo_tags
        try:
            cov._namespace_repo_tags = lambda ns: {}
            check("commissioning: the PRE-FIX namespace-wide test is caught "
                  "(reads the landed bump as still pending)",
                  not cov.already_applied(lab()))
        finally:
            cov._namespace_repo_tags = orig
            cov._NS_TEXT_CACHE.clear()

    # --- THE DANGEROUS DIRECTION: every ambiguity must stay PENDING ----------
    with Fixture({"a.yaml": "image: redis:1.0.1\n", "b.yaml": "image: redis:1.0.0\n"}):
        check("the SAME repo with one instance still lagging stays pending",
              not cov.already_applied(
                  {"component": "app", "namespace": "testns", "kind": "image",
                   "current": "1.0.0", "target": "1.0.1", "image_repo": "redis"}))

    with Fixture({"hr.yaml": MEMGRAPH_HR}):
        check("an item whose repo is NOT in git falls back, never assumes",
              not cov.already_applied(lab(image_repo="ghcr.io/nothing/here")))
        check("a MULTI-image row falls back to the namespace-wide test",
              not cov.already_applied(
                  lab(image_repo=None,
                      image_repos=["memgraph/lab", "memgraph/memgraph-mage"])))
        check("an item with NO repo at all falls back",
              not cov.already_applied(lab(image_repo=None, image_repos=[])))
        check("a chart row never takes the image branch",
              not cov.already_applied(lab(kind="chart")))
        check("target absent from this repo stays pending",
              not cov.already_applied(lab(target="9.9.9")))
        check("a truncated tag is still never judged applied",
              not cov.already_applied(lab(target="3.13.2...")))

    # --- NORMALISATION: the fix is inert if these do not reconcile -----------
    check("registry prefix is stripped", cov._norm_repo("docker.io/jellyfin/jellyfin")
          == "jellyfin/jellyfin")
    check("the implicit library/ namespace is stripped",
          cov._norm_repo("library/postgres") == "postgres")
    check("an unqualified repo is unchanged",
          cov._norm_repo("memgraph/lab") == "memgraph/lab")

    with Fixture({"hr.yaml": MEMGRAPH_HR}):
        tags = cov._namespace_repo_tags("testns")
        check("a digest-pinned tag is indexed by its bare version",
              tags.get("busybox") == {"1.38.0"}, f"got {tags.get('busybox')!r}")
        check("both sibling images are indexed separately",
              tags.get("memgraph/lab") == {"3.13.2"}
              and tags.get("memgraph/memgraph-mage") == {"3.13.1"}, f"got {tags!r}")

    # --- THE CACHE TRAP -----------------------------------------------------
    # The repo->tags map lives inside _NS_TEXT_CACHE under a tuple key so that
    # the 11 existing `_NS_TEXT_CACHE.clear()` calls in the other two suites
    # invalidate it too. A cache of its own would serve a previous fixture's
    # tree while every clear() still looked correct.
    with Fixture({"hr.yaml": MEMGRAPH_HR}):
        cov._namespace_repo_tags("testns")
        check("the repo cache is keyed inside _NS_TEXT_CACHE",
              any(isinstance(k, tuple) and k[0] == "repos" for k in cov._NS_TEXT_CACHE))
        cov._NS_TEXT_CACHE.clear()
        check("...so the shared clear() invalidates it",
              not any(isinstance(k, tuple) for k in cov._NS_TEXT_CACHE))

    with Fixture({"hr.yaml": 'spec:\n  values:\n    x: 1\n'}):
        check("a namespace with no images yields an empty map, not a crash",
              cov._namespace_repo_tags("testns") == {})
    check("an unknown namespace yields an empty map",
          cov._namespace_repo_tags("does-not-exist") == {})

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
