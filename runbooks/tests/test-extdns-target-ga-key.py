#!/usr/bin/env python3
"""Regression test: the external-dns DNS-traceability check must read the GA
annotation key, not only the alpha one (F-c43f447f, 2026-09-22).

s8_external_exposure asserts that the `envoy-external` Gateway declares an
external-dns target — the single point of failure for every externally-routed
hostname, since external-dns's gateway-httproute source takes the target from
the PARENT Gateway and ignores the same annotation on a route. That assertion
read exactly one key:

    external-dns.alpha.kubernetes.io/target

external-dns has since promoted its annotations to a GA prefix. v0.22.0 reads
`external-dns.kubernetes.io/*` ONLY, with no fallback to alpha; v0.21 reads
only alpha. `kubernetes/apps/network/envoy-gateway/app/gateways.yaml` therefore
carries BOTH keys through the transition — which is the only reason this check
was green. It was passing by coincidence, and both ends of the migration break
it in opposite directions:

  drop the alpha key (the planned cleanup once v0.22 is in) -> a correctly
    annotated Gateway is reported as MISSING its target. A false warning on the
    line whose entire job is to be believed.

  drop the GA key -> the check stays GREEN while the running external-dns reads
    nothing, publishes nothing, and every external hostname goes dark. That is
    not hypothetical: it happened on 2026-09-07 when the target was set in a
    place external-dns did not read, and the hostnames went dark publicly until
    the commit was reverted.

The FIXTURES below are synthetic. A test anchored to the live Gateway would
assert nothing today (it carries both keys, so every variant passes) and would
start failing the day the alpha key is legitimately retired — exactly backwards.

Run:  python3 runbooks/tests/test-extdns-target-ga-key.py
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
os.environ.setdefault("_MISE_ACTIVATED", "1")
os.chdir(_REPO)
sys.argv = ["security-check.py"]

_spec = importlib.util.spec_from_file_location(
    "sc", _REPO / "runbooks" / "security-check.py")
sc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sc)

GA = "external-dns.kubernetes.io/target"
ALPHA = "external-dns.alpha.kubernetes.io/target"
TARGET = "external.example.invalid"

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


def gateway(annotations):
    return {"metadata": {"name": "envoy-external", "namespace": "network",
                         "annotations": annotations}}


ROUTES = {"items": [{
    "metadata": {"namespace": "default", "name": "app"},
    "spec": {"parentRefs": [{"name": "envoy-external"}],
             "hostnames": ["app.example.invalid"]},
}]}


def missing_extdns_count(gw) -> int:
    """Run the REAL s8 against a fixture cluster and count the DNS findings.

    Calls the section rather than the helper so a call site that stopped using
    the helper cannot pass this suite.
    """
    orig_json, orig_kubectl, orig_sensitive = sc.kubectl_json, sc.kubectl, sc._sensitive

    def fake_json(args, timeout=30):
        if args.startswith("get gateway"):
            return gw
        if args.startswith("get httproute"):
            return ROUTES
        if args.startswith("get ingress"):
            return {"items": []}
        return None

    try:
        sc.kubectl_json = fake_json
        sc.kubectl = lambda a, timeout=30: ""
        sc._sensitive = dict(orig_sensitive)
        sc._sensitive["DOMAIN"] = "example.invalid"
        with contextlib.redirect_stdout(io.StringIO()):
            _worst, f, _md = sc.s8_external_exposure()
        return sum(1 for _s, m, _meta in f._items
                   if "missing external-dns target" in m)
    finally:
        sc.kubectl_json, sc.kubectl, sc._sensitive = orig_json, orig_kubectl, orig_sensitive


def main() -> int:
    print(__doc__.strip().splitlines()[0])
    print()

    # --- THE HELPER ---------------------------------------------------------
    check("the GA key alone resolves", sc.extdns_target({GA: TARGET}) == TARGET)
    check("the alpha key alone still resolves (rollback path intact)",
          sc.extdns_target({ALPHA: TARGET}) == TARGET)
    check("GA wins when both are present",
          sc.extdns_target({GA: "ga", ALPHA: "alpha"}) == "ga")
    check("neither key -> None", sc.extdns_target({"other": "x"}) is None)
    check("no annotations at all -> None", sc.extdns_target(None) is None)
    check("an EMPTY value is not a target",
          sc.extdns_target({GA: ""}) is None)
    check("an empty GA value falls through to alpha rather than masking it",
          sc.extdns_target({GA: "", ALPHA: TARGET}) == TARGET)
    check("the constants match the keys external-dns actually reads",
          (sc.EXTDNS_TARGET_GA, sc.EXTDNS_TARGET_ALPHA) == (GA, ALPHA))

    # --- THE SECTION, against fixture Gateways ------------------------------
    check("a Gateway carrying ONLY the GA key is DNS-tracked (the fix)",
          missing_extdns_count(gateway({GA: TARGET})) == 0)
    check("a Gateway carrying ONLY the alpha key is still DNS-tracked",
          missing_extdns_count(gateway({ALPHA: TARGET})) == 0)
    check("a Gateway carrying BOTH is DNS-tracked (today's live shape)",
          missing_extdns_count(gateway({GA: TARGET, ALPHA: TARGET})) == 0)

    # DO NOT BLIND THE DETECTOR. Broadening which keys count must not make the
    # check unable to fail — that is how an FP fix has repeatedly become an FN
    # here. A Gateway with no target at all is the incident shape.
    check("a Gateway with NEITHER key is still reported missing",
          missing_extdns_count(gateway({"unrelated": "x"})) == 1)
    check("a Gateway with no annotations block is still reported missing",
          missing_extdns_count({"metadata": {"name": "envoy-external"}}) == 1)
    check("an unreadable Gateway (kubectl returned None) is reported missing",
          missing_extdns_count(None) == 1)

    # --- COMMISSIONING STRAW ------------------------------------------------
    # Revert the helper to the pre-fix alpha-only read. The GA-only case must
    # then FAIL — which also proves the call site goes through the helper: if
    # it did not, this monkeypatch would change nothing.
    orig = sc.extdns_target
    try:
        sc.extdns_target = lambda ann: (ann or {}).get(ALPHA) or None
        check("commissioning: with the alpha-only read restored, a GA-only "
              "Gateway is falsely reported MISSING its target",
              missing_extdns_count(gateway({GA: TARGET})) == 1)
        check("commissioning: ...and the both-keys Gateway still passes, which "
              "is why the defect was invisible",
              missing_extdns_count(gateway({GA: TARGET, ALPHA: TARGET})) == 0)
    finally:
        sc.extdns_target = orig

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
