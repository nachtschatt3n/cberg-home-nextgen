#!/usr/bin/env python3
"""
Regression test for doc-check.py's exposure-column derivation (F-ce5a9fd5).

The defect: docs/applications.md states each app's exposure by hand. It was
wrong for 13 apps at the Envoy-migration review (11 documented Internal while
actually internet-reachable), corrected by hand, then wrong for 7 more
(4afadaac) — the predicted recurrence. Exposure is a property of which Gateway
a route attaches to, so it is now DERIVED from live HTTPRoute parentRefs and
diffed against the column. The finding's implementation warning is load-
bearing: a first attempt with fuzzy app-name matching produced confident wrong
corrections (redis <- redisinsight, wazuh-agent <- the dashboard host), so the
route->app mapping here is EXACT and repo-grounded (the Flux object named in
the route's labels is declared inside exactly one app directory).

Contract, asserted through the module's own functions:
  1. _derive_route_exposure: parentRefs on the https listener of a known
     Gateway count; the :80 (http) listener and hostname-less routes do not;
     an owner that does not resolve EXACTLY is reported unmapped, never
     guessed; `redis` never inherits `redisinsight`'s route.
  2. _doc_exposure_claims / _parse_exposure_claim: every vocabulary form the
     real doc uses; an unparseable cell is None, not a guess.
  3. _exposure_mismatches: the dangerous direction (documented Internal /
     None while a route is on envoy-external) is reported, non-repo rows are
     skipped, unparseable rows are listed.
  4. Real repo: the owner index resolves the four declared-name cases without
     an alias table (frigate, scrypted, flux-instance, adguard-home under a
     grouping dir), and the real doc parses.
  5. COMMISSIONING STRAW: with an empty owner index — the pre-fix state, no
     repo-grounded mapping — every route is unmapped and nothing can be
     attributed, so the drift is invisible.

Run: python3 runbooks/tests/test-doc-check-exposure-derivation.py
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

os.environ["_MISE_ACTIVATED"] = "1"
ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
_spec = importlib.util.spec_from_file_location("dc", ROOT / "runbooks" / "doc-check.py")
dc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dc)

PASS = FAIL = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}" + (f"\n        {detail}" if detail else ""))


def route(ns, name, hosts, parents, labels=None, annotations=None):
    return {"metadata": {"namespace": ns, "name": name, "labels": labels or {},
                         "annotations": annotations or {}},
            "spec": {"hostnames": hosts,
                     "parentRefs": [{"name": n, "namespace": "network", "sectionName": s}
                                    for n, s in parents]}}


KS, HR, INST = ("kustomize.toolkit.fluxcd.io/name", "helm.toolkit.fluxcd.io/name",
                "app.kubernetes.io/instance")
OWNER = {("apps", "web"): "web", ("apps", "web-helm"): "web", ("apps", "vault"): "vault",
         ("db", "redisinsight"): "redisinsight", ("db", "redis"): "redis", ("net", "gw"): "gw"}
ROUTES = [
    route("apps", "web", ["web.example.internal"], [("envoy-external", "https")], {KS: "web"}),
    route("apps", "web-outpost", ["web.example.internal"], [("envoy-internal", "https")], {HR: "web-helm"}),
    route("apps", "vault", ["v.example.internal"], [("envoy-external", "https")], {}, {"meta.helm.sh/release-name": "vault"}),
    route("net", "https-redirect", [], [("envoy-internal", "http"), ("envoy-external", "http")], {KS: "gw"}),
    route("net", "gw-http-only", ["x.example.internal"], [("envoy-external", "http")], {KS: "gw"}),
    route("db", "redisinsight", ["ri.example.internal"], [("envoy-internal", "https")], {INST: "redisinsight"}),
    route("db", "mystery", ["m.example.internal"], [("envoy-internal", "https")], {KS: "nobody"}),
]

# 1 — derivation
derived, unmapped = dc._derive_route_exposure(ROUTES, OWNER)
check("both gateways aggregate per app across its routes (label + helm-name resolution)",
      derived.get(("apps", "web")) == {"external", "internal"}, f"{derived}")
check("annotation release-name resolves too", derived.get(("apps", "vault")) == {"external"})
check("a hostname-less route (https-redirect) exposes nothing", ("net", "gw") not in derived)
check("the :80 http listener does not count", ("net", "gw") not in derived)
check("an unresolvable owner is reported unmapped, never guessed", unmapped == ["db/mystery"], f"{unmapped}")
check("redis does NOT inherit redisinsight's route (exact mapping, no name similarity)",
      ("db", "redis") not in derived and derived.get(("db", "redisinsight")) == {"internal"})

# 2 — the doc side
DOC = """\
## Apps (`apps`)

| App | Purpose | Ingress | Homepage Group |
|-----|---------|---------|----------------|
| web | a web thing | **External** — `envoy-external`; no internal route | Apps |
| worker | a worker | None — cluster-only Service; no HTTPRoute exists | — |
| both | ui | Internal UI; External `api`/`stream` | Apps |
| hook | hook | **External (webhook)** — must be reachable | — |
| vault | pw | Internal + Authentik SAML SSO | Apps |
| odd | odd | LAN via LoadBalancer | — |

## Databases (`db`)

| App | Purpose | Ingress | Homepage Group |
|-----|---------|---------|----------------|
| redisinsight | ui | Internal | Databases |
| redis | cache | None | — |

## Network (`net`)

| App | Sub-path | Purpose | Ingress |
|-----|----------|---------|---------|
| gw | `net/gw/` | the gateway | None |

### `custom`

| App | Purpose | Ingress |
|-----|---------|---------|
| site | site | Internal |
| **Total** | | **3** |
"""
claims = dc._doc_exposure_claims(DOC)
check("claims: every vocabulary form parses to the intended set", {
    ("apps", "web"): {"external"}, ("apps", "worker"): set(), ("apps", "both"): {"internal", "external"},
    ("apps", "hook"): {"external"}, ("apps", "vault"): {"internal"}, ("apps", "odd"): None,
    ("db", "redisinsight"): {"internal"}, ("db", "redis"): set(), ("net", "gw"): set(),
    ("custom", "site"): {"internal"}} == claims, f"{claims}")
check("Ingress column is located by header, whatever its position", claims.get(("net", "gw")) == set())
check("the Total row is not an app", not any(a.startswith("Total") for _, a in claims))
check("prose after the dash cannot flip a claim ('no internal route' stays External)",
      dc._parse_exposure_claim("**External** — `envoy-external`; no internal route") == {"external"})

# 3 — the diff
REPO = {("apps", "web"), ("apps", "worker"), ("apps", "both"), ("apps", "hook"), ("apps", "vault"),
        ("apps", "odd"), ("db", "redisinsight"), ("db", "redis"), ("net", "gw")}
DERIVED = {("apps", "web"): {"external"}, ("apps", "worker"): {"external"},
           ("apps", "both"): {"internal", "external"}, ("apps", "hook"): {"external"},
           ("apps", "vault"): {"external"}, ("db", "redisinsight"): {"internal"}}
mis, compared, skipped, unp = dc._exposure_mismatches(claims, DERIVED, REPO)
check("dangerous direction is reported: documented None / Internal while a route is on envoy-external",
      mis == ["apps/vault: doc says internal, routes say external",
              "apps/worker: doc says none, routes say external"], f"{mis}")
check("compared / skipped / unparseable are all accounted for",
      compared == 8 and skipped == ["custom/site"] and unp == ["apps/odd"],
      f"{compared} {skipped} {unp}")

# 4 — real repo
idx = dc._route_owner_index()
check("real owner index: declared HelmRelease/Kustomization names resolve to their app dir",
      idx.get(("home-automation", "frigate")) == "frigate-nvr"
      and idx.get(("home-automation", "scrypted")) == "scrypted-nvr"
      and idx.get(("flux-system", "flux-instance")) == "flux-operator",
      f"{ {k: idx.get(k) for k in (('home-automation', 'frigate'), ('home-automation', 'scrypted'), ('flux-system', 'flux-instance'))} }")
check("real owner index: a grouping dir's ks.yaml maps its children to the CHILD, not the grouping dir",
      idx.get(("network", "adguard-home")) == "adguard-home", f"{idx.get(('network', 'adguard-home'))}")
real_claims = dc._doc_exposure_claims((ROOT / "docs" / "applications.md").read_text())
check("real docs/applications.md parses (>= 100 rows under an Ingress column)",
      len(real_claims) >= 100, f"{len(real_claims)}")
print(f"        (real doc: {len(real_claims)} rows, "
      f"{sum(1 for v in real_claims.values() if v is None)} unparseable)")

# 5 — COMMISSIONING STRAW: no repo-grounded mapping (pre-fix state)
d0, u0 = dc._derive_route_exposure(ROUTES, {})
check("STRAW: with an empty owner index every hostname-bearing https route is unmapped and nothing is attributed",
      d0 == {} and sorted(u0) == ["apps/vault", "apps/web", "apps/web-outpost", "db/mystery", "db/redisinsight"],
      f"{d0} {u0}")
mis0, *_ = dc._exposure_mismatches(claims, d0, REPO)
check("STRAW: ...so the vault drift is not reported as the external route it is",
      "apps/vault: doc says internal, routes say external" not in mis0, f"{mis0}")

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
