#!/usr/bin/env python3
"""
Regression test for the orphaned cert-manager TLS Secret detector in
security-check.py section 10 (F-d4039dd2).

The gap: a Secret still carrying `cert-manager.io/certificate-name` after its
Certificate is deleted keeps serving until notAfter and then lapses with
nothing to renew it. Seven such leftovers (F-3201fe14) were found BY HAND in a
maintenance window because no check paired Secrets with Certificates. Today the
cluster is 4 annotated Secrets <-> 4 Certificates, 0 orphans — so the test
constructs an orphan fixture: a detector that cannot fail proves nothing.

Contract, asserted through the module's own functions:
  1. _orphaned_cert_secrets pairs by (namespace, spec.secretName): a missing
     Certificate is an orphan; a same-named Certificate in ANOTHER namespace
     does not rescue it; un-annotated TLS Secrets are ignored.
  2. An EMPTY population (no annotated Secrets, or no Certificates) returns
     None — never a clean zero: the wildcard alone should give 1/1.
  3. s9_certificates surfaces the orphan as a WARNING naming ns/name, reports
     NOT MEASURED when a listing fails or a population is empty, and reports
     0 with both control counts when clean.
  4. COMMISSIONING STRAW: with the pairing disabled (the pre-fix state — no
     detector), the same orphan fixture produces no finding.

Fixtures are synthetic (no real domain, no real secret names).

Run: python3 runbooks/tests/test-cert-manager-orphan-secrets.py
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import sys
from pathlib import Path

os.environ.setdefault("_MISE_ACTIVATED", "1")
ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
_spec = importlib.util.spec_from_file_location("sc", ROOT / "runbooks" / "security-check.py")
sc = importlib.util.module_from_spec(_spec)
with contextlib.redirect_stdout(io.StringIO()):
    _spec.loader.exec_module(sc)

PASS = FAIL = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}" + (f"\n        {detail}" if detail else ""))


def secret(ns, name, cert=None):
    md = {"namespace": ns, "name": name}
    if cert:
        md["annotations"] = {sc.CERT_MANAGER_NAME_ANNOTATION: cert}
    return {"metadata": md, "type": "kubernetes.io/tls", "data": {"tls.crt": "AAAA"}}


def certificate(ns, name, secret_name):
    return {"metadata": {"namespace": ns, "name": name}, "spec": {"secretName": secret_name}}


PAIRED = [secret("apps-a", "web-tls", "web"), secret("apps-a", "api-tls", "api")]
CERTS = [certificate("apps-a", "web", "web-tls"), certificate("apps-a", "api", "api-tls")]
ORPHAN = secret("apps-b", "old-tls", "old")
SELF_SIGNED = secret("infra", "webhook-ca")            # no annotation: operator-owned

# 1 — pairing
check("1:1 pairing -> no orphans, both counts",
      sc._orphaned_cert_secrets(PAIRED, CERTS) == ([], 2, 2))
res = sc._orphaned_cert_secrets(PAIRED + [ORPHAN], CERTS)
check("annotated Secret without a Certificate -> orphan named with its cert annotation",
      res is not None and [(o["namespace"], o["name"], o["certificate_name"]) for o in res[0]]
      == [("apps-b", "old-tls", "old")] and res[1:] == (3, 2), f"{res}")
res = sc._orphaned_cert_secrets(PAIRED + [ORPHAN], CERTS + [certificate("apps-a", "old", "old-tls")])
check("a same-named Certificate in ANOTHER namespace does not rescue the orphan",
      res is not None and len(res[0]) == 1 and res[0][0]["namespace"] == "apps-b", f"{res}")
res = sc._orphaned_cert_secrets(PAIRED + [ORPHAN], CERTS + [certificate("apps-b", "old", "old-tls")])
check("the Certificate in the SAME namespace does", res == ([], 3, 3), f"{res}")
res = sc._orphaned_cert_secrets(PAIRED + [SELF_SIGNED], CERTS)
check("an un-annotated TLS Secret is ignored (not counted, never an orphan)", res == ([], 2, 2), f"{res}")

# 2 — empty populations abort
check("no Certificates at all -> None (listing broken, not 0 orphans)",
      sc._orphaned_cert_secrets(PAIRED, []) is None)
check("no annotated Secrets at all -> None", sc._orphaned_cert_secrets([SELF_SIGNED], CERTS) is None)
check("both empty -> None", sc._orphaned_cert_secrets([], []) is None)


# 3 — the section end-to-end, kubectl stubbed
def run_s9(secrets, certs, *, certs_none=False):
    def fake_kubectl_json(args, timeout=30):
        if args.startswith("get secret"):
            return {"items": secrets}
        if args.startswith("get certificate"):
            return None if certs_none else {"items": certs}
        return None

    saved = sc.kubectl_json, sc.kubectl, sc._cert_not_after
    sc.kubectl_json = fake_kubectl_json
    sc.kubectl = lambda args, timeout=30: ""              # wildcard secret path: absent
    sc._cert_not_after = lambda b64: "Jan 1 00:00:00 2027 GMT"
    before = list(sc.DEGRADED.reasons)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            status, f, body = sc.s9_certificates()
    finally:
        sc.kubectl_json, sc.kubectl, sc._cert_not_after = saved
    return status, f, body, [r for r in sc.DEGRADED.reasons if r not in before]


status, f, body, new = run_s9(PAIRED + [ORPHAN, SELF_SIGNED], CERTS)
orphan_msgs = [m for s, m, _ in f._items if s == sc.WARNING and "Orphaned cert-manager TLS Secret" in m]
check("s9 surfaces the orphan as a WARNING naming ns/name and the missing Certificate",
      len(orphan_msgs) == 1 and "`apps-b/old-tls`" in orphan_msgs[0] and "`old`" in orphan_msgs[0]
      and "2027" in orphan_msgs[0], f"{orphan_msgs}")
check("report carries the orphan count over both populations",
      "Orphaned cert-manager TLS Secrets: **1** (of 3 annotated; 2 Certificates)" in body, body)
check("TLS secret count comes from the same listing", "TLS secrets in cluster: 4" in body, body)

status, f, body, new = run_s9(PAIRED, CERTS)
check("clean fixture -> 0 orphans with both control counts, no DEGRADED",
      "Orphaned cert-manager TLS Secrets: **0** (2 annotated Secrets <-> 2 Certificates)" in body
      and not any("Orphaned" in m for _, m, _ in f._items) and new == [], body)

status, f, body, new = run_s9(PAIRED, CERTS, certs_none=True)
check("Certificate listing failed -> NOT MEASURED, never a zero",
      "Orphaned cert-manager TLS Secrets: NOT MEASURED" in body and "**0**" not in body.split("Orphaned")[1], body)

status, f, body, new = run_s9([SELF_SIGNED], CERTS)
check("empty annotated population -> NOT MEASURED + DEGRADED, never a zero",
      "NOT MEASURED — empty population (0 annotated Secrets, 2 Certificates)" in body
      and any("empty population" in r for r in new), f"{body} {new}")

# 4 — COMMISSIONING STRAW: disable the pairing (pre-fix: no detector existed)
saved_pair = sc._orphaned_cert_secrets
sc._orphaned_cert_secrets = lambda secrets, certs: ([], 1, 1)
try:
    status, f, body, new = run_s9(PAIRED + [ORPHAN], CERTS)
    check("STRAW: without the pairing the orphan is invisible (defect reproduces)",
          not any("Orphaned cert-manager TLS Secret `" in m for _, m, _ in f._items))
finally:
    sc._orphaned_cert_secrets = saved_pair
status, f, body, new = run_s9(PAIRED + [ORPHAN], CERTS)
check("pairing restored -> the orphan is found again",
      any("`apps-b/old-tls`" in m for _, m, _ in f._items))

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
