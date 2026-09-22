#!/usr/bin/env python3
"""Pin the Flux source hygiene detector in security-check.py s10 (F-e805174a).

Three questions per source — scheme, consumers, namespace ownership — each
behind a control so a zero means "checked and clean" and never "the query
broke". The classifier `flux_source_hygiene` is pure; it is run here over
the REAL repository manifests through the module's own reader
(`flux_objects_from_repo`), and over synthetic fixtures that carry each
defect, with the defect removed again to prove the fixture is a witness.

Population guards abort the run when the reader returns nothing or reports
parse failures: a detector validated only on synthetic input is not
validated (docs/sops/audit-script-correctness.md), and a reader that
silently skipped every file would pass every "no http source" assertion.

COMMISSIONING STRAW: before this detector existed, s10_flux_posture asked
none of the three questions, so a fixture holding all three defects produced
no finding. The straw is that fixture: each defect must be detected, and
each must vanish when the defect is edited out — otherwise the assertion
would pass on a detector that flags everything, or nothing.

Run: python3 runbooks/tests/test-flux-source-hygiene.py
"""
from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import os
import sys
from pathlib import Path

os.environ.setdefault("_MISE_ACTIVATED", "1")
os.environ.pop("SWEEP_PG_DSN", None)
ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
sys.argv = ["security-check.py"]
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


def abort(msg: str) -> None:
    print(f"\n  ABORT  {msg}")
    sys.exit(1)


# A deterministic owner oracle. Controls answer correctly; a small table of
# personal accounts; everything else is an organization. Never the network.
PERSONAL = {"someuser", "another-person"}


def oracle(owner: str) -> str | None:
    if owner in sc._GITHUB_OWNER_CONTROLS:
        return sc._GITHUB_OWNER_CONTROLS[owner]
    return "User" if owner in PERSONAL else "Organization"


def broken_oracle(owner: str) -> str | None:
    return None                      # rate-limited / offline: answers nothing


def src(kind: str, name: str, url: str, ns: str = "flux-system", **spec) -> dict:
    return {"apiVersion": "source.toolkit.fluxcd.io/v1", "kind": kind,
            "metadata": {"name": name, "namespace": ns}, "spec": {"url": url, **spec}}


def hr(name: str, source_kind: str, source_name: str, ns: str = "apps",
       source_ns: str | None = "flux-system") -> dict:
    ref = {"kind": source_kind, "name": source_name}
    if source_ns:
        ref["namespace"] = source_ns
    return {"apiVersion": "helm.toolkit.fluxcd.io/v2", "kind": "HelmRelease",
            "metadata": {"name": name, "namespace": ns},
            "spec": {"chart": {"spec": {"chart": name, "sourceRef": ref}}}}


def ks(name: str, source_name: str = "flux-system") -> dict:
    return {"apiVersion": "kustomize.toolkit.fluxcd.io/v1", "kind": "Kustomization",
            "metadata": {"name": name, "namespace": "flux-system"},
            "spec": {"path": "./x", "sourceRef": {"kind": "GitRepository",
                                                   "name": source_name,
                                                   "namespace": "flux-system"}}}


ROOT_SRC = src("GitRepository", "flux-system",
               "https://github.com/example-self/cluster.git", ref={"name": "refs/heads/main"})

print("flux source hygiene\n")

# ── 1. the real repository, through the real reader ─────────────────────────
print("-- real repository manifests --")
sources, consumers, stats = sc.flux_objects_from_repo(ROOT)
if stats["files"] < 100:
    abort(f"reader walked only {stats['files']} files — population too small to trust")
if stats["parse_failures"]:
    abort(f"reader reported parse failures: {stats['parse_failures'][:5]}")
kinds = {}
for s in sources:
    kinds[s["kind"]] = kinds.get(s["kind"], 0) + 1
ckinds = {}
for c in consumers:
    ckinds[c["kind"]] = ckinds.get(c["kind"], 0) + 1
check(f"population: {len(sources)} sources parsed ({kinds})",
      kinds.get("HelmRepository", 0) >= 20 and kinds.get("GitRepository", 0) >= 2
      and kinds.get("OCIRepository", 0) >= 1)
check(f"population: {len(consumers)} consumers parsed ({ckinds})",
      ckinds.get("HelmRelease", 0) >= 50 and ckinds.get("Kustomization", 0) >= 50)
root = [s for s in sources if sc.flux_source_key(s) == sc._FLUX_ROOT_SOURCE]
check("the root sync GitRepository is synthesised from the FluxInstance values (not a manifest)",
      len(root) == 1 and root[0].get("_synthesized_from", "").endswith("helm-values.yaml"))

real = sc.flux_source_hygiene(sources, consumers, owner_type=oracle)
check("resolver control passes on the real repo (root referenced by ≥50 consumers)",
      real["resolver_ok"] and real["root_consumers"] >= 50, str(real["root_consumers"]))
check("no cleartext http source in the repo today", real["http"] == [], str(real["http"]))
check("no unexpected scheme in the repo", real["odd_scheme"] == [], str(real["odd_scheme"]))

# Consistency, not a fixed expectation: every "unreferenced" verdict must be
# corroborated by an INDEPENDENT walk of the raw consumer dicts, and every
# referenced source contradicted by one. (A fixed list would break the moment
# the operator deletes a stranded source, which is the very action the
# finding asks for.)
def raw_ref_names(c: dict) -> set[str]:
    spec = c.get("spec") or {}
    out = set()
    for ref in (((spec.get("chart") or {}).get("spec") or {}).get("sourceRef"),
                spec.get("chartRef"), spec.get("sourceRef")):
        if isinstance(ref, dict) and ref.get("name"):
            out.add((ref.get("kind"), ref["name"]))
    return out


named = set()
for c in consumers:
    named |= raw_ref_names(c)
unref = real["unreferenced"]
check(f"every unreferenced verdict is corroborated by the raw consumer walk ({len(unref)} today: "
      f"{', '.join(sc._fmt_key(k) for k in unref) or '-'})",
      all((k[0], k[2]) not in named for k in unref))
referenced = [k for k, n in real["consumer_counts"].items() if n > 0]
check(f"every referenced source ({len(referenced)}) is named by at least one raw consumer ref",
      all((k[0], k[2]) in named for k in referenced))
check("the self owner is derived from the root URL, not hardcoded",
      real["owner"]["self_owners"] == [sc.github_owner_of(root[0]["spec"]["url"])],
      str(real["owner"]["self_owners"]))
check("sources under the self owner are never flagged personal",
      all(o not in real["owner"]["self_owners"] for _, o in real["owner"]["personal"]))
check("owner classes partition the source set",
      sum(len(real["owner"][k]) for k in ("personal", "org", "self", "not_github", "unknown"))
      == len(sources))

# ── 2. url parsing ───────────────────────────────────────────────────────────
print("\n-- url parsing --")
for url, want_scheme, want_owner in [
    ("https://someuser.github.io/helm-charts", "https", "someuser"),
    ("https://raw.githubusercontent.com/SomeOrg/repo/gh-pages", "https", "someorg"),
    ("https://github.com/example-self/cluster.git", "https", "example-self"),
    ("oci://ghcr.io/someorg/charts", "oci", "someorg"),
    ("oci://registry-1.docker.io/somecharts", "oci", None),
    ("https://charts.example-project.io", "https", None),
    ("http://charts.example-project.io", "http", None),
    ("ssh://git@github.com/someorg/repo.git", "ssh", "someorg"),
    ("git@github.com:someorg/repo.git", "ssh", "someorg"),
    ("", "", None),
]:
    check(f"scheme/owner of {url or '(empty)'!r} -> {want_scheme!r}/{want_owner!r}",
          sc.url_scheme(url) == want_scheme and sc.github_owner_of(url) == want_owner,
          f"got {sc.url_scheme(url)!r}/{sc.github_owner_of(url)!r}")

# ── 3. COMMISSIONING STRAW: one fixture, every defect, each removable ────────
print("\n-- commissioning straw: three defects in one fixture, each proven removable --")
FIX_SOURCES = [
    ROOT_SRC,
    src("HelmRepository", "plain", "http://charts.example-project.io"),           # scheme
    src("HelmRepository", "stranded", "https://charts.example-org.io"),          # no consumer
    src("HelmRepository", "personal", "https://someuser.github.io/helm-charts"),  # User account
    src("HelmRepository", "fine", "https://charts.example-org.io/fine"),
    src("OCIRepository", "app-oci", "oci://ghcr.io/someorg/charts/app", ns="apps"),
    src("GitRepository", "floating", "https://github.com/someorg/repo", ref={"branch": "main"}),
    src("GitRepository", "pinned", "https://github.com/someorg/repo",
        ref={"branch": "release-1", "commit": "0123456789abcdef"}),
]
FIX_CONSUMERS = [
    ks("cluster-apps"), ks("cluster-meta"),
    hr("plain-app", "HelmRepository", "plain"),
    hr("personal-app", "HelmRepository", "personal"),
    hr("fine-app", "HelmRepository", "fine"),
    hr("floating-app", "GitRepository", "floating"),
    hr("pinned-app", "GitRepository", "pinned"),
    {"apiVersion": "helm.toolkit.fluxcd.io/v2", "kind": "HelmRelease",
     "metadata": {"name": "app", "namespace": "apps"},
     "spec": {"chartRef": {"kind": "OCIRepository", "name": "app-oci"}}},
]
res = sc.flux_source_hygiene(FIX_SOURCES, FIX_CONSUMERS, owner_type=oracle)
K = lambda kind, name, ns="flux-system": (kind, ns, name)  # noqa: E731

check("STRAW resolver control passes (root referenced by the two Kustomizations)",
      res["resolver_ok"] and res["root_consumers"] == 2)
check("STRAW detects the http source", [k for k, _ in res["http"]] == [K("HelmRepository", "plain")])
check("STRAW detects the unreferenced source", res["unreferenced"] == [K("HelmRepository", "stranded")])
check("STRAW detects the personal-account source",
      [k for k, _ in res["owner"]["personal"]] == [K("HelmRepository", "personal")])
check("STRAW detects the branch-tracking GitRepository, not the commit-pinned one, not the root",
      [k for k, _ in res["branch_tracking"]] == [K("GitRepository", "floating")])
check("chartRef -> OCIRepository in the consumer's own namespace resolves",
      res["consumer_counts"][K("OCIRepository", "app-oci", "apps")] == 1)
check("no consumer ref was left unresolved in the fixture", res["unresolved_refs"] == 0)

# Each defect removed -> each finding gone (proves the fixture is a witness).
fixed = copy.deepcopy(FIX_SOURCES)
fixed[1]["spec"]["url"] = "https://charts.example-project.io"
fixed[3]["spec"]["url"] = "https://someorg.github.io/helm-charts"
fixed[6]["spec"]["ref"]["tag"] = "v1.0.0"
res2 = sc.flux_source_hygiene(fixed, FIX_CONSUMERS + [hr("stranded-app", "HelmRepository", "stranded")],
                              owner_type=oracle)
check("with the defects edited out, every list is empty",
      res2["http"] == [] and res2["unreferenced"] == [] and res2["owner"]["personal"] == []
      and res2["branch_tracking"] == [],
      f"{res2['http']} {res2['unreferenced']} {res2['owner']['personal']} {res2['branch_tracking']}")

# ── 4. the controls refuse to answer when they cannot ────────────────────────
print("\n-- controls --")
no_root = [s for s in FIX_SOURCES if sc.flux_source_key(s) != sc._FLUX_ROOT_SOURCE]
res3 = sc.flux_source_hygiene(no_root, FIX_CONSUMERS, owner_type=oracle)
check("root absent -> resolver not ok and NO unreferenced verdict (stranded is still stranded)",
      not res3["resolver_ok"] and res3["unreferenced"] == [] and not res3["root_present"])
res4 = sc.flux_source_hygiene(FIX_SOURCES, [c for c in FIX_CONSUMERS if c["kind"] != "Kustomization"],
                              owner_type=oracle)
check("root present but unreferenced -> resolver not ok and NO unreferenced verdict",
      not res4["resolver_ok"] and res4["unreferenced"] == [] and res4["root_present"])
res5 = sc.flux_source_hygiene(FIX_SOURCES, FIX_CONSUMERS, owner_type=broken_oracle)
check("oracle controls fail -> ownership NOT MEASURED: nothing personal, the source is 'unknown'",
      not res5["owner"]["oracle_ok"] and res5["owner"]["personal"] == []
      and K("HelmRepository", "personal") in [k for k, _ in res5["owner"]["unknown"]])
check("oracle controls fail -> scheme and consumer verdicts are unaffected",
      res5["http"] == res["http"] and res5["unreferenced"] == res["unreferenced"])


def half_oracle(owner):          # one control right, one wrong -> still not ok
    return "User" if owner == "octocat" else "User"


res6 = sc.flux_source_hygiene(FIX_SOURCES, FIX_CONSUMERS, owner_type=half_oracle)
check("an oracle that calls everything a User fails the Organization control",
      not res6["owner"]["oracle_ok"] and res6["owner"]["personal"] == [])

# ── 5. section wiring: findings, DEGRADED, live-vs-git drift ─────────────────
print("\n-- section wiring --")


def run_section(live_sources, live_consumers, repo_sources, oracle_fn=oracle):
    saved = (sc._flux_objects_live, sc._github_owner_type, sc.flux_objects_from_repo)
    calls = []

    def fake_live(resources):
        calls.append(resources)
        if resources == sc._FLUX_SOURCE_RESOURCES:
            return live_sources
        if resources == sc._FLUX_CONSUMER_RESOURCES:
            return live_consumers
        return None

    sc._flux_objects_live = fake_live
    sc._github_owner_type = oracle_fn
    sc.flux_objects_from_repo = lambda root: (repo_sources, [], {"files": 1, "parse_failures": [], "docs": 1})
    f, checks = sc.Findings(), []
    before = list(sc.DEGRADED.reasons)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            sc._s10_flux_source_hygiene(f, checks)
    finally:
        sc._flux_objects_live, sc._github_owner_type, sc.flux_objects_from_repo = saved
    new = [r for r in sc.DEGRADED.reasons if r not in before]
    return f, checks, new


f, checks, new = run_section(FIX_SOURCES, FIX_CONSUMERS, FIX_SOURCES)
titles = [m for _, m, _ in f._items]
check("section: http source -> CRITICAL naming kind/ns/name",
      any(s == sc.CRITICAL and "HelmRepository/flux-system/plain" in m and "cleartext http" in m
          for s, m, _ in f._items), str(titles))
check("section: unreferenced source -> WARNING with the accepted-risk hint",
      any("HelmRepository/flux-system/stranded" in m and "no consumer" in m and "accepted-risk" in m
          for m in titles), str(titles))
check("section: personal account -> WARNING naming the owner",
      any("HelmRepository/flux-system/personal" in m and "`someuser`" in m for m in titles), str(titles))
check("section: branch-tracking GitRepository -> WARNING",
      any("flux-system/floating" in m and "mutable branch" in m for m in titles), str(titles))
check("section: nothing DEGRADED when every control passes", new == [], str(new))
check("section: report lines carry the ownership tally",
      any("Flux source ownership" in c for c in checks), str(checks))

f, checks, new = run_section(FIX_SOURCES, FIX_CONSUMERS, FIX_SOURCES[:-1])
titles = [m for _, m, _ in f._items]
check("section: a live source declared in no manifest -> WARNING (out-of-band object)",
      any("exists in the cluster but is declared in no manifest" in m and "flux-system/pinned" in m
          for m in titles), str(titles))

# The k8s-gateway shape: an app-local manifest with NO metadata.namespace (the
# Flux Kustomization's targetNamespace injects it). The first live run flagged
# it as "live-only" — a false positive this case pins shut.
repo_shaped = copy.deepcopy(FIX_SOURCES)
for s in repo_shaped:
    if s["kind"] == "OCIRepository":
        del s["metadata"]["namespace"]
f, checks, new = run_section(FIX_SOURCES, FIX_CONSUMERS, repo_shaped)
titles = [m for _, m, _ in f._items]
check("section: a namespace-less repo manifest matches its live object (no false live-only)",
      not any("declared in no manifest" in m for m in titles)
      and any("Flux sources live vs git" in c and "0 live-only" in c and "declared-but-not-live" not in c
              for c in checks), f"{titles} {checks}")
check("declared-matcher: empty repo namespace matches any live namespace; a set one must match",
      sc.flux_source_declared(("OCIRepository", "network", "x"), {("OCIRepository", "", "x")})
      and sc.flux_source_declared(("OCIRepository", "network", "x"), {("OCIRepository", "network", "x")})
      and not sc.flux_source_declared(("OCIRepository", "network", "x"), {("OCIRepository", "other", "x")})
      and not sc.flux_source_declared(("OCIRepository", "network", "x"), {("HelmRepository", "", "x")}))
# And on the REAL repo: the app-local OCIRepository has no namespace in git,
# so the real reader must produce a key the matcher accepts for its live form.
real_oci = [sc.flux_source_key(s) for s in sources if s["kind"] == "OCIRepository"]
check("real repo: the app-local OCIRepository key carries no namespace and still matches its live shape",
      real_oci and all(k[1] == "" for k in real_oci)
      and all(sc.flux_source_declared((k[0], "network", k[2]), set(real_oci)) for k in real_oci),
      str(real_oci))

f, checks, new = run_section([], [], FIX_SOURCES)
check("section: empty inventory -> DEGRADED and NOT MEASURED, zero findings",
      f._items == [] and len(new) == 1 and any("NOT MEASURED" in c for c in checks), f"{new} {checks}")

f, checks, new = run_section(None, FIX_CONSUMERS, FIX_SOURCES)
check("section: kubectl failure -> NOT MEASURED line, zero findings",
      f._items == [] and any("NOT MEASURED" in c for c in checks), str(checks))

f, checks, new = run_section(FIX_SOURCES, FIX_CONSUMERS, FIX_SOURCES, oracle_fn=broken_oracle)
check("section: broken oracle -> ownership DEGRADED + NOT MEASURED, scheme/consumer findings still emitted",
      any("owner-type oracle" in r for r in new)
      and any("cleartext http" in m for _, m, _ in f._items)
      and not any("personal GitHub account" in m for _, m, _ in f._items), f"{new}")

# ── 6. the section really calls the detector ─────────────────────────────────
src_text = (ROOT / "runbooks" / "security-check.py").read_text()
check("s10_flux_posture wires the hygiene block before AR suppression",
      src_text.find("_s10_flux_source_hygiene(f, checks)") < src_text.find(
          "f.suppress_accepted(_ACCEPTED_RISKS)", src_text.find("def s10_flux_posture")))

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
