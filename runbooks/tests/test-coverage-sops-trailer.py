#!/usr/bin/env python3
"""Regression test: the SOPS metadata trailer is not a deployed version.

F-a52c69d7, measured 2026-09-17. `already_applied()` proves a bump landed with
a NAMESPACE-WIDE substring test — target present AND current absent — over
every `*.yaml` under `kubernetes/apps/<ns>/`. Every SOPS-encrypted file ends in
a `sops:` trailer carrying `version: <the sops BINARY version>`, which is a
version-shaped string with nothing to do with any workload.

The collision was live: memgraph had been bumped 3.13.0 -> 3.13.1 in git, but
`3.13.0` still appeared in two unrelated `secret.sops.yaml` trailers in the
same namespace (the local sops binary was 3.13.0), so `cur not in txt` was
False, the bump never self-cleared, and `counts.AUTO` reported 2 where the true
actionable AUTO was 1 — a number the maintenance-window agent reads at Step 0
and re-proposes from. Three files under `kubernetes/apps/databases/` carry
`version: 3.13.0` today, so this is not a one-off.

The trailer is also STABLE — it moves only when the sops binary moves — so any
component whose CURRENT version happens to equal the sops version is stuck in
AUTO indefinitely, not transiently.

THE OTHER DIRECTION MATTERS AS MUCH. `already_applied()` is deliberately
asymmetric: a false "already applied" silently DROPS a real update, which is
the CRACK class this whole file exists to prevent. So the fix must delete the
trailer and nothing else — a stripper that drops a whole file because it
contains `sops:` would take real, deployed tags with it. That straw is
commissioned at the bottom.

Run: python3 runbooks/tests/test-coverage-sops-trailer.py
"""

from __future__ import annotations

import importlib.util
import re
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("cov", REPO / "runbooks/coverage.py")
cov = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cov)

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


# The exact shape sops writes: a top-level `sops:` key, indented children, at
# the end of the file. `version:` here is the sops BINARY, not the workload.
SOPS_SECRET = """apiVersion: v1
kind: Secret
metadata:
    name: app-secret
stringData:
    password: ENC[AES256_GCM,data:abc,type:str]
sops:
    age:
        - recipient: age1nw624gk
          enc: |
            -----BEGIN AGE ENCRYPTED FILE-----
            c29tZSBlbmNyeXB0ZWQgYnl0ZXM=
            -----END AGE ENCRYPTED FILE-----
    lastmodified: "2026-09-17T02:00:00Z"
    mac: ENC[AES256_GCM,data:zzz,type:str]
    version: 3.13.0
"""


class Fixture:
    """A throwaway kubernetes/apps/<ns>/ tree, like the already-applied suite."""

    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.ns = self.root / "kubernetes" / "apps" / "testns"
        self.ns.mkdir(parents=True)
        self._orig = cov.REPO_ROOT
        cov.REPO_ROOT = self.root
        cov._NS_TEXT_CACHE.clear()
        return self

    def __exit__(self, *a):
        cov.REPO_ROOT = self._orig
        cov._NS_TEXT_CACHE.clear()
        self._tmp.cleanup()

    def write(self, name, text):
        (self.ns / name).write_text(text)
        cov._NS_TEXT_CACHE.clear()


def item(**kw):
    base = {"component": "memgraph", "namespace": "testns", "kind": "image",
            "current": "3.13.0", "target": "3.13.1"}
    base.update(kw)
    return base


def main() -> int:
    print("test-coverage-sops-trailer")

    # ── THE DEFECT, in its measured shape ──────────────────────────────
    with Fixture() as f:
        f.write("helmrelease.yaml", 'spec:\n  values:\n    image:\n      tag: "3.13.1"\n')
        f.write("secret.sops.yaml", SOPS_SECRET)
        check("bump IS recognised as applied although the sops trailer carries "
              "the old version string (THE defect: memgraph stuck in AUTO)",
              cov.already_applied(item()))

    # ── the asymmetry must survive: a REAL leftover still holds the item ──
    with Fixture() as f:
        f.write("helmrelease.yaml", 'spec:\n  values:\n    image:\n      tag: "3.13.1"\n')
        f.write("sidecar.yaml", "image: memgraph/memgraph:3.13.0\n")
        f.write("secret.sops.yaml", SOPS_SECRET)
        check("a genuine leftover of the OLD version still keeps the item pending "
              "(the deliberate false-negative-never direction is intact)",
              not cov.already_applied(item()))

    # ── the trailer is deleted, the FILE is not ────────────────────────
    real_above = SOPS_SECRET.replace("stringData:", 'tag: "9.9.9"\nstringData:')
    stripped = cov._strip_sops_trailer(real_above)
    check("the sops: block is gone", "lastmodified" not in stripped
          and "3.13.0" not in stripped, stripped[-120:])
    check("...and REAL keys above it survive (a whole-file drop would silently "
          "delete a deployed tag and manufacture a false 'already applied')",
          '9.9.9' in stripped and "kind: Secret" in stripped)
    check("a file with no trailer is returned unchanged",
          cov._strip_sops_trailer("a: 1\nb: 2\n") == "a: 1\nb: 2\n")
    check("a NESTED key called sops: is not a trailer and is left alone",
          "3.13.0" in cov._strip_sops_trailer("top:\n  sops:\n    version: 3.13.0\n"))

    # ── the live tree: the trailer version must not leak into ns text ──
    cov.REPO_ROOT = REPO
    cov._NS_TEXT_CACHE.clear()
    txt = cov._namespace_text("databases") or ""
    sops_versions = set(re.findall(r"^\s*version: (3\.\d+\.\d+)\s*$",
                                   (REPO / "kubernetes/apps/databases/sweep-history/app"
                                    / "secret.sops.yaml").read_text(), re.M))
    check("live databases namespace: the sops binary version no longer appears "
          "in the text already_applied() searches",
          bool(sops_versions) and not any(v in txt for v in sops_versions),
          f"sops versions {sops_versions} still present")
    cov._NS_TEXT_CACHE.clear()

    # ── COMMISSIONING: straws that must FAIL the assertions above ──────
    def straw_noop(text):
        """The pre-fix behaviour: no trailer handling at all."""
        return text

    def straw_drop_file(text):
        """The over-broad 'fix': drop any file mentioning sops:."""
        return "" if "sops:" in text else text

    orig = cov._strip_sops_trailer
    try:
        cov._strip_sops_trailer = straw_noop
        with Fixture() as f:
            f.write("helmrelease.yaml", 'tag: "3.13.1"\n')
            f.write("secret.sops.yaml", SOPS_SECRET)
            check("commissioning: the PRE-FIX stripper is caught (bump reads as "
                  "still pending)", not cov.already_applied(item()))

        cov._strip_sops_trailer = straw_drop_file
        with Fixture() as f:
            # the deployed tag lives in the SAME file as the trailer
            f.write("secret.sops.yaml",
                    SOPS_SECRET.replace("stringData:", 'tag: "3.13.1"\nstringData:'))
            check("commissioning: the whole-file straw is caught (it deletes the "
                  "deployed tag, so the target vanishes and the bump cannot be "
                  "proven applied)", not cov.already_applied(item()))
    finally:
        cov._strip_sops_trailer = orig
        cov._NS_TEXT_CACHE.clear()

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
