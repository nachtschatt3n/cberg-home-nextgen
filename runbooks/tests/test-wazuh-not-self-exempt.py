#!/usr/bin/env python3
"""Regression test: the security-monitoring stack must not exempt itself
from its own CVE scan (security-check.py, 2026-08-24).

`wazuh/wazuh-*` was in `_should_skip()`'s Trivy exclusion list from the very
first commit that introduced image scanning (85790e0a, 2026-05-09), grouped
with Bitnami under "internal images" with no accepted-risk rationale ever
recorded for it. Unlike Bitnami -- frozen/unmaintained, separately tracked by
the bundled-datastore-exit programme -- Wazuh has no such justification: the
images are public (no registry-auth blocker the way `ghcr.io/nachtschatt3n/*`
is), actively maintained upstream, and demonstrably not low-signal. Verified
live 2026-08-24: `wazuh/wazuh-manager:4.14.5` alone carries real, currently-open
CRITICAL/HIGH CVEs, all invisible to every security-check.py run since May.

Run: python3 runbooks/tests/test-wazuh-not-self-exempt.py
"""
import json
import pathlib
import re
import shutil
import subprocess
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


m = re.search(r"def _should_skip\(img: str\) -> bool:\s*\n\s*return any\(skip in img\.lower\(\) for skip in \(\s*\n(.*?)\n\s*\)\)",
              src, re.S)
check("_should_skip() was found", m is not None, True)
skip_tuple_body = m.group(1)

check("wazuh/wazuh- is NOT in the skip list (this is the fix)",
      "wazuh" in skip_tuple_body.lower(), False)
check("bitnami/ IS still in the skip list (that exclusion is separately "
      "justified -- frozen/unmaintained, tracked by bundled-datastore-exit)",
      "bitnami/" in skip_tuple_body, True)

# --- exercise the real predicate, extracted verbatim, against fixtures -----
# _should_skip is a nested function, not importable -- exec the extracted
# source (same technique as test-longhorn-disk-capacity.py uses for jq) so
# the test runs the ACTUAL deployed logic, not a restatement of it.
ns = {}
exec(compile(m.group(0), "<extracted _should_skip>", "exec"), ns)
should_skip = ns["_should_skip"]

check("a wazuh image is no longer skipped",
      should_skip("wazuh/wazuh-manager:4.14.5"), False)
check("a wazuh dashboard image is no longer skipped",
      should_skip("wazuh/wazuh-dashboard:4.14.5"), False)
check("a bitnami image is still skipped",
      should_skip("docker.io/bitnami/postgresql:16"), True)
check("an unrelated image is not skipped (control)",
      should_skip("ghcr.io/nextcloud-releases/whiteboard:v1.5.9"), False)

# --- live proof: the image is scannable AND materially vulnerable ----------
if not shutil.which("trivy"):
    print("  SKIP  trivy not installed -- live scan not exercised")
elif not shutil.which("kubectl"):
    print("  SKIP  kubectl not available -- cannot confirm the image is live")
else:
    r = subprocess.run(
        ["kubectl", "get", "pods", "-n", "security", "-o",
         "jsonpath={.items[*].spec.containers[*].image}"],
        capture_output=True, text=True, timeout=15,
    )
    if r.returncode != 0 or "wazuh" not in r.stdout:
        print("  SKIP  wazuh not found running in-cluster -- live scan not exercised")
    else:
        images = [i for i in r.stdout.split() if "wazuh/wazuh-" in i]
        target = sorted(set(images))[0] if images else None
        check("a running wazuh image was found to scan", target is not None, True)
        if target:
            scan = subprocess.run(
                ["trivy", "image", "--scanners", "vuln",
                 "--severity", "CRITICAL,HIGH", "--format", "json", target],
                capture_output=True, text=True, timeout=180,
            )
            check(f"trivy can scan {target} (public image, no auth needed)",
                  scan.returncode, 0)
            if scan.returncode == 0:
                d = json.loads(scan.stdout)
                total = sum(len(r.get("Vulnerabilities") or [])
                           for r in d.get("Results") or [])
                # Deliberately asserting only presence of scan DATA, never a
                # count or severity claim in committed text -- see
                # docs/sops/vulnerability-disclosure.md.
                check(f"live cluster: trivy returned real vulnerability data for "
                      f"{target} (proving this was never noise-free, only unmeasured)",
                      total > 0, True)

print(f"\n  {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
