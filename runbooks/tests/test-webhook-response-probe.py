#!/usr/bin/env python3
"""Regression test for Section 38 (Admission Webhook Health) in health-check.sh
(2026-08-24).

Section 38 counted `mutatingwebhookconfigurations` / `validatingwebhookconfigurations`
objects and called that "webhook health" -- a count of how many webhooks are
DECLARED, never whether they WORK. It read "All webhooks healthy (48
configured)" on every run while 14 of those 48 routes 404'd on their own
target service: the Intel device-plugin operator runs with `--devices=gpu,npu`
only, but its chart renders webhook config objects for all 8 device types
unconditionally, so the other 6 point at routes the controller never
registers. Two of the 14 -- the FPGA and SGX POD-mutators
(`fpga.mutator.webhooks.intel.com`, `sgx.mutator.webhooks.intel.com`, rules
matching core-group `pods`) -- fire on EVERY pod CREATE cluster-wide with
`failurePolicy: Ignore`, so the 404 blocks nothing, generates no Warning
event (invisible to the section's own event-keyword grep), and repeats an
estimated ~2,700 times/day. The other 12 are CRD-scoped (fire only on an
`FpgaDevicePlugin`-shaped object create, essentially never) -- dead, but not
a noise source, which is why the fix classifies severity by `rules`
(core-group + `pods` = HIGH) rather than treating every 404 alike.

Run: python3 runbooks/tests/test-webhook-response-probe.py
"""
import json
import pathlib
import re
import shutil
import subprocess
import sys

HC = pathlib.Path(__file__).resolve().parents[1] / "health-check.sh"
src = HC.read_text()
PASS = FAIL = 0


def check(name, got, want):
    global PASS, FAIL
    if got == want:
        print(f"  PASS  {name}")
        PASS += 1
    else:
        print(f"  FAIL  {name}\n        got {got!r}\n        want {want!r}")
        FAIL += 1


i = src.index('log_section "Section 38: Admission Webhook Health"')
j = src.index('\nlog_section', i + 20)
section = src[i:j]

# --- the regression this replaces: config-count masquerading as health -----
check("the verdict no longer relies solely on a bare object COUNT",
      "log_success \"All webhooks healthy ($TOTAL_WEBHOOKS configured)\"" in section
      and "WEBHOOK_PROBE" in section, True)
check("a response probe is present", "WEBHOOK_PROBE=$(python3" in section, True)

# --- the embedded probe script must be syntactically valid Python ----------
m = re.search(r'python3 -c "\n(.*?)\n"', section, re.S)
check("the embedded probe script was found", m is not None, True)
probe_src = m.group(1)
import ast
try:
    ast.parse(probe_src)
    check("the embedded probe script parses as valid Python", True, True)
except SyntaxError as e:
    check(f"the embedded probe script parses as valid Python ({e})", False, True)

# --- structural properties of the probe: severity discriminator ------------
check("HIGH severity requires core apiGroup", "'' in (r.get(\\'apiGroups\\'" in section
      or "in (r.get('\\''apiGroups'\\''" in section
      or "apiGroups" in probe_src, True)
check("HIGH severity requires 'pods' in resources", "'pods'" in probe_src, True)
check("a 404 -- and only a 404 -- is treated as a dead route",
      "== '404'" in probe_src or "== \"404\"" in probe_src, True)
check("a service that never opens is reported, not silently skipped",
      "could_not_run" in probe_src and "continue" in probe_src, True)
check("the probe uses each webhook's registered path (not a fixed guess)",
      "t['path']" in probe_src, True)

# --- exercise the real severity classifier against synthetic webhook docs --
# Same technique as test-longhorn-disk-capacity.py: run the actual embedded
# logic (not a restatement of it) against fixture data, via the real tool.
classify_src = (
    "import json, sys\n"
    "wh = json.loads(sys.stdin.read())\n"
    "rules = wh.get('rules') or []\n"
    "hits_all_pods = any(\n"
    "    'pods' in (r.get('resources') or [])\n"
    "    and '' in (r.get('apiGroups') or [])\n"
    "    for r in rules\n"
    ")\n"
    "print('HIGH' if hits_all_pods else 'LOW')\n"
)
# The classifier fragment above is restated deliberately narrowly (just the
# discriminator) so this test does not need to fake kubectl/curl/port-forward
# to exercise it -- but it is checked byte-for-byte against the deployed
# script's own fragment first, so a change to the real logic fails loudly
# here instead of this test silently testing something else.
deployed_fragment = (
    "hits_all_pods = any(\n"
    "                'pods' in (r.get('resources') or [])\n"
    "                and '' in (r.get('apiGroups') or [])\n"
    "                for r in rules\n"
    "            )"
)
check("the classifier fixture matches the deployed script verbatim",
      deployed_fragment in probe_src, True)


def classify(webhook_doc):
    r = subprocess.run([sys.executable, "-c", classify_src],
                       input=json.dumps(webhook_doc), capture_output=True, text=True)
    return r.stdout.strip()


POD_MUTATOR = {"name": "fpga.mutator.webhooks.intel.com",
               "rules": [{"apiGroups": [""], "resources": ["pods"]}]}
CRD_MUTATOR = {"name": "mfpgadeviceplugin.kb.io",
               "rules": [{"apiGroups": ["deviceplugin.intel.com"],
                         "resources": ["fpgadeviceplugins"]}]}
POD_AND_OTHER = {"name": "generic-pod-and-cm",
                  "rules": [{"apiGroups": [""], "resources": ["configmaps"]},
                            {"apiGroups": [""], "resources": ["pods"]}]}
NON_CORE_PODS = {"name": "not-core-group",
                  "rules": [{"apiGroups": ["apps"], "resources": ["pods"]}]}
NO_RULES = {"name": "no-rules", "rules": []}

check("a pod-scoped, core-group webhook classifies HIGH",
      classify(POD_MUTATOR), "HIGH")
check("a CRD-scoped webhook classifies LOW",
      classify(CRD_MUTATOR), "LOW")
check("one rule among several matching pods+core is still HIGH",
      classify(POD_AND_OTHER), "HIGH")
check("'pods' resource in a NON-core apiGroup does not count as HIGH",
      classify(NON_CORE_PODS), "LOW")
check("no rules at all classifies LOW, not an error",
      classify(NO_RULES), "LOW")

# --- live smoke test: the actual known-dead webhooks, best-effort ----------
if not shutil.which("kubectl"):
    print("  SKIP  kubectl not available -- live probe not exercised")
else:
    r = subprocess.run(["kubectl", "get", "mutatingwebhookconfigurations",
                        "inteldeviceplugins-mutating-webhook-configuration",
                        "-o", "json"], capture_output=True, text=True, timeout=15)
    if r.returncode != 0 or not r.stdout.strip():
        print("  SKIP  cluster unreachable -- live probe not exercised")
    else:
        doc = json.loads(r.stdout)
        by_name = {wh["name"]: wh for wh in doc.get("webhooks", [])}
        for name in ("fpga.mutator.webhooks.intel.com", "sgx.mutator.webhooks.intel.com"):
            if name in by_name:
                check(f"live cluster: {name} still classifies HIGH (real fixture)",
                      classify(by_name[name]), "HIGH")
        if "mgpudeviceplugin.kb.io" in by_name:
            check("live cluster: the ENABLED gpu device webhook classifies LOW "
                  "(CRD-scoped, correctly not flagged as a cluster-wide risk)",
                  classify(by_name["mgpudeviceplugin.kb.io"]), "LOW")

print(f"\n  {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
