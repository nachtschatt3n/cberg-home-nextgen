#!/usr/bin/env python3
"""Regression test: the Authentik outpost audit must enumerate the LIVE
outpost list and must actually fire (security-check.py s12, F-0e2c62ad).

Every Authentik outpost on a Kubernetes service connection must carry
`kubernetes_disabled_components: [ingress]`. Without it the outpost controller
publishes its own Ingress holding the app's hostname -- an object in no git
repo, with no ownerReferences, invisible to a repo grep, and recreated if
deleted. It has mis-routed a hostname three times.

The bug this test guards is NOT "the rule is unwritten" -- the rule was
documented and every declared outpost complied. The bug is that the audit was
a repo grep. `rg kubernetes_disabled_components` enumerates the outposts we
DECLARED in configmap.sops.yaml; it does not enumerate the outposts that
EXIST. The `authentik Embedded Outpost` is created by authentik in code
(AuthentikOutpostConfig.embedded_outpost in authentik/outposts/apps.py), no
blueprint declares it, and it therefore sat on `[]` -- on a live Kubernetes
service connection -- invisible to every audit that had ever run.

So this test asserts three things, and the first is the load-bearing one:

  1. The check reads the live outpost list, not the repo. A repo-grep
     implementation would reproduce the bug the check exists to catch.
  2. It FIRES on a non-compliant outpost -- including a managed/system one
     with no blueprint, which is the case that actually bit us.
  3. It is SILENT on compliant outposts, and on outposts that are not on a
     Kubernetes service connection (no ingress reconciler -- flagging those
     would be crying wolf).

All 13 live outposts are compliant today, so a green run proves nothing about
direction 2. That direction is exercised against fixtures here.

Run: python3 runbooks/tests/test-outpost-ingress-suppression.py
"""
import pathlib
import re
import sys

SC = pathlib.Path(__file__).resolve().parents[1] / "security-check.py"
src = SC.read_text()
PASS = FAIL = 0


def check(name, got, want):
    global PASS, FAIL
    if got == want:
        print(f"  PASS  {name}")
        PASS += 1
    else:
        print(f"  FAIL  {name}\n        got {got!r}\n        want {want!r}")
        FAIL += 1


# --- 1. the enumeration source ------------------------------------------
# The probe must go to the Authentik DB via the worker pod. If this ever
# becomes a repo grep, the embedded outpost goes invisible again.
check("the section exists", "def s12_authentik_outposts()" in src, True)
check("it is registered in _SECTION_SLUGS, so its findings are scored/persisted",
      '"s12_authentik_outposts",' in src, True)
check("main() actually calls it (a section nobody calls is a check nobody runs)",
      "results.append(s12_authentik_outposts())" in src, True)

probe_m = re.search(r"_AK_OUTPOST_PROBE = f'''(.*?)'''", src, re.S)
check("the live probe was found", probe_m is not None, True)
probe = probe_m.group(1)
check("the probe enumerates ALL outposts from the Authentik ORM",
      "Outpost.objects.all()" in probe, True)
check("the probe reports each outpost's service-connection type",
      "service_connection" in probe, True)
check("the probe reports kubernetes_disabled_components",
      "kubernetes_disabled_components" in probe, True)
check("the probe does NOT filter out managed/system outposts "
      "(that filter IS the embedded-outpost bug)",
      "managed=False" in probe or "exclude(managed" in probe, False)

live_m = re.search(r"def _live_authentik_outposts\(\).*?\n(?=\ndef |\n# ---)", src, re.S)
check("_live_authentik_outposts() was found", live_m is not None, True)
live_src = live_m.group(0)
check("it reads the cluster, not the repo",
      "kubectl(" in live_src, True)
check("it does NOT grep the repo for the answer",
      bool(re.search(r"configmap\.sops\.yaml|rg |ripgrep|Path\(.*kubernetes/", live_src)), False)
check("a failed probe returns None (distinguishable from 'no outposts'), so "
      "a broken query cannot read as a clean result",
      live_src.count("return None") >= 3, True)

# The section must treat both None and [] as blind. A silent empty list is the
# exact shape of failure this whole section exists to prevent.
sec_m = re.search(r"def s12_authentik_outposts\(\).*?\n(?=\n# ---|\ndef )", src, re.S)
sec_src = sec_m.group(0)
check("None (probe failed) raises a finding rather than passing",
      "outposts is None" in sec_src and "did NOT run" in sec_src, True)
check("an empty outpost list is treated as blind, not as clean",
      "if not outposts:" in sec_src and "ZERO outposts" in sec_src, True)
check("it also catches an already-published outpost Ingress (disabling the "
      "component stops management but does not delete the object)",
      "ak-outpost-" in sec_src, True)
# The stale-Ingress sub-probe gets the same blindness rule as the outpost
# probe. `if ing:` would have read a FAILED Ingress read as "no stale Ingress"
# -- kubectl_json returns a List with empty items when there genuinely are
# none, so None is always a coverage gap, never a clean result.
check("a failed Ingress read is a finding, not a silent pass",
      "if ing is None:" in sec_src
      and "would not have been detected" in sec_src, True)

# --- 2 & 3. exercise the REAL predicate, extracted verbatim --------------
# _outpost_ingress_offenders is module-level and pure precisely so both
# directions can be exercised without a live cluster.
pred_m = re.search(r"def _outpost_ingress_offenders\(outposts: list\[dict\]\) -> list\[dict\]:.*?\n    return offenders\n",
                   src, re.S)
check("_outpost_ingress_offenders() was found", pred_m is not None, True)
ns: dict = {}
exec(compile(pred_m.group(0), "<extracted _outpost_ingress_offenders>", "exec"), ns)
offenders = ns["_outpost_ingress_offenders"]


def o(name, *, k8s=True, disabled=("ingress",), managed=False, providers=1):
    return {"name": name, "managed": managed, "providers": providers,
            "kubernetes_service_connection": k8s,
            "service_connection": "KubernetesServiceConnection" if k8s else "DockerServiceConnection",
            "disabled_components": list(disabled)}


def names(rows):
    return sorted(r["name"] for r in offenders(rows))


# FIRES -- the load-bearing direction.
check("fires on a blueprint outpost with an empty disabled list",
      names([o("app-forward-auth", disabled=[])]), ["app-forward-auth"])
check("fires on the MANAGED/system outpost with no blueprint -- the real "
      "2026-09-09 finding, invisible to any repo grep",
      names([o("authentik Embedded Outpost", disabled=[], managed=True, providers=0)]),
      ["authentik Embedded Outpost"])
check("fires when the key holds some OTHER component but not ingress",
      names([o("half-done", disabled=["deployment"])]), ["half-done"])
check("fires on a latent outpost (0 providers) -- that is the state the "
      "embedded outpost sat in, and when the fix is free",
      names([o("latent", disabled=[], providers=0)]), ["latent"])
check("picks the offender out of a mostly-compliant fleet",
      names([o("ok-1"), o("ok-2"), o("bad", disabled=[]), o("ok-3")]), ["bad"])

# SILENT -- the anti-cry-wolf direction.
check("silent on a compliant outpost", names([o("compliant")]), [])
check("silent on a compliant outpost with extra components disabled",
      names([o("extra", disabled=["ingress", "deployment"])]), [])
check("silent on a NON-Kubernetes service connection: no Kubernetes "
      "controller means no Ingress to publish, so flagging it is crying wolf",
      names([o("docker-outpost", k8s=False, disabled=[])]), [])
check("silent on the whole compliant fleet (today's live state)",
      names([o(f"app{i}-forward-auth") for i in range(13)]), [])
check("case/whitespace in the component value does not create a false positive",
      names([o("cased", disabled=["  Ingress "])]), [])

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
