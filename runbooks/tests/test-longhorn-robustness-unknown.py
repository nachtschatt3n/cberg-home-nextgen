#!/usr/bin/env python3
"""Regression test for the Longhorn volume-health display line in
health-check.sh, Section 10 (2026-08-24).

`robustness == "unknown"` is correctly EXCLUDED from the alarm-triggering
UNHEALTHY_VOLUMES count -- it is Longhorn's expected value for every
detached (intentionally idle) volume, not a failure, and the existing
comment defending that design is correct and untouched by this fix.

The bug was one line further down: the display line computed
`TOTAL - UNHEALTHY` and printed that as "healthy". Since "unknown" is neither
counted in UNHEALTHY nor its own bucket, it fell out of the subtraction and
was silently folded INTO "healthy" -- a volume whose robustness is literally
unknown got reported as robust. Live on 2026-08-24: 95 volumes, 93
attached+healthy, 2 detached+unknown (`paperless-mariadb`,
`redis-data-nextcloud-redis-master-0`, both migration-rollback soak
volumes) -- displayed as "95/95 healthy", a claim the data does not support.

Fixed by giving "unknown" its own bucket (UNKNOWN_ROBUSTNESS), named by
volume, and subtracting it explicitly so HEALTHY_VOLUMES cannot silently
absorb it. The alarm logic (UNHEALTHY_VOLUMES, what actually pages) is
UNCHANGED -- this is a reporting-honesty fix, not a new alert.

Run: python3 runbooks/tests/test-longhorn-robustness-unknown.py
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


i = src.index('log_section "Section 10: Longhorn Storage"')
j = src.index("\nlog_section", i + 20)
section = src[i:j]

# --- the fix must exist, and must NOT touch the alarm logic ----------------
check("UNKNOWN_ROBUSTNESS is computed as its own bucket",
      "UNKNOWN_ROBUSTNESS=" in section, True)
check("the display line no longer computes healthy as TOTAL - UNHEALTHY alone",
      "$((TOTAL_VOLUMES - UNHEALTHY_VOLUMES))/$TOTAL_VOLUMES healthy" in section,
      False)
check("HEALTHY_VOLUMES subtracts BOTH unhealthy and unknown",
      "HEALTHY_VOLUMES=$((TOTAL_VOLUMES - UNHEALTHY_VOLUMES - UNKNOWN_ROBUSTNESS))"
      in section, True)
check("the original alarm predicate (degraded/faulted, or attached+non-healthy) "
      "is untouched -- this fix must not change what pages "
      "(appears 3x: UNHEALTHY_VOLUMES, UNHEALTHY_DETAIL, the >0 display branch)",
      section.count('select((.status.robustness == "degraded" or '
                    '.status.robustness == "faulted") or '
                    '(.status.state == "attached" and '
                    '.status.robustness != "healthy"))'), 3)
check("unknown-robustness volumes are named individually in the output "
      "(not just counted)",
      "select(.status.robustness == \\\"unknown\\\")" in section
      or 'select(.status.robustness == "unknown")' in section, True)

# --- the jq expression itself, run for real ---------------------------------
if not shutil.which("jq"):
    print("  SKIP  jq not installed - query behaviour not exercised")
else:
    UNKNOWN_Q = '[.items[] | select(.status.robustness == "unknown")] | length'
    UNHEALTHY_Q = ('[.items[] | select((.status.robustness == "degraded" or '
                   '.status.robustness == "faulted") or '
                   '(.status.state == "attached" and '
                   '.status.robustness != "healthy"))] | length')

    def jq(expr, payload):
        r = subprocess.run(["jq", expr], input=json.dumps(payload),
                           capture_output=True, text=True)
        return r.stdout.strip()

    def vol(name, state, robustness):
        return {"metadata": {"name": name},
                "status": {"state": state, "robustness": robustness}}

    # the real fixture shape from this cluster: 93 attached+healthy,
    # 2 detached+unknown
    fixture = {"items": (
        [vol(f"v{n}", "attached", "healthy") for n in range(93)]
        + [vol("paperless-mariadb", "detached", "unknown"),
           vol("redis-data-nextcloud-redis-master-0", "detached", "unknown")]
    )}
    total = len(fixture["items"])
    unhealthy = int(jq(UNHEALTHY_Q, fixture))
    unknown = int(jq(UNKNOWN_Q, fixture))
    healthy = total - unhealthy - unknown

    check("real fixture: total is 95", total, 95)
    check("real fixture: UNHEALTHY_VOLUMES is 0 (detached+unknown does not alarm)",
          unhealthy, 0)
    check("real fixture: UNKNOWN_ROBUSTNESS is 2 (the two orphans)",
          unknown, 2)
    check("real fixture: HEALTHY_VOLUMES is 93, not 95 -- this is the fix",
          healthy, 93)

    # a GENUINE failure (attached + degraded) must still alarm, unaffected
    fixture2 = {"items": fixture["items"] + [vol("broken-vol", "attached", "degraded")]}
    check("a genuine attached+degraded volume still counts as unhealthy",
          int(jq(UNHEALTHY_Q, fixture2)), 1)
    check("...and is NOT double-counted as unknown too",
          int(jq(UNKNOWN_Q, fixture2)), 2)

# --- live cluster proof, best-effort -----------------------------------------
if not shutil.which("kubectl"):
    print("  SKIP  kubectl not available -- live check not exercised")
else:
    r = subprocess.run(["kubectl", "get", "volumes", "-n", "storage", "-o", "json"],
                       capture_output=True, text=True, timeout=15)
    if r.returncode != 0 or not r.stdout.strip():
        print("  SKIP  cluster unreachable -- live check not exercised")
    else:
        d = json.loads(r.stdout)
        unknown_live = [v["metadata"]["name"] for v in d["items"]
                        if v["status"].get("robustness") == "unknown"]
        # Not asserting a specific count (the live inventory can change) --
        # only that IF any unknown-robustness volumes exist, they are real
        # detached volumes, matching the design's own invariant.
        for name in unknown_live:
            v = next(x for x in d["items"] if x["metadata"]["name"] == name)
            check(f"live cluster: {name} (unknown robustness) is detached, "
                  "not silently misreported",
                  v["status"].get("state"), "detached")

print(f"\n  {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
