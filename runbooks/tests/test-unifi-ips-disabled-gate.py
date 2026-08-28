#!/usr/bin/env python3
"""
Regression test for the UNIFI_IPS_ENABLED gate in security-check.py
(operator decision 2026-08-28).

The operator disabled UniFi threat management (IDS/IPS) on the controller for
gateway performance. With the feature off, `stat alarm` 404s/returns empty, so
the unconditional probe recorded a DEGRADED coverage gap every sweep — which
kept the whole security section INCOMPLETE and permanently vetoed
stale-finding auto-close, for a signal that is deliberately absent
(F-e545073a: the 404 was the disabled feature, not a moved endpoint).

Contract asserted here:
  1. The gate constant exists and defaults to disabled.
  2. The `stat alarm` probe is called exactly once, and only behind the gate
     (the walrus elif after `if not UNIFI_IPS_ENABLED:`).
  3. The disabled branch REPORTS the N/A state — an invisible skip would read
     as coverage that never happened.
  4. The rogue-AP and admin-activity probes stay unconditional — disabling
     IPS must not silently drop the compensating signals.

Run: python3 runbooks/tests/test-unifi-ips-disabled-gate.py
"""
import pathlib
import re
import sys

SC = pathlib.Path(__file__).resolve().parents[1] / "security-check.py"
src = SC.read_text()
PASS = FAIL = 0


def check(name, got, want=True):
    global PASS, FAIL
    if got == want:
        print(f"  PASS  {name}")
        PASS += 1
    else:
        print(f"  FAIL  {name}\n        got {got!r} want {want!r}")
        FAIL += 1


check("gate constant exists and is disabled",
      re.search(r"^UNIFI_IPS_ENABLED = False$", src, re.M) is not None)

check("stat-alarm probe appears exactly once",
      src.count('_unifi_json("stat alarm")'), 1)

m = re.search(
    r"if not UNIFI_IPS_ENABLED:.*?elif \(alarms := _unifi_json\(\"stat alarm\"\)\) is None:",
    src, re.S)
check("probe is reachable only behind the gate (walrus elif)", m is not None)

check("disabled branch reports N/A in the section report",
      "IPS/IDS alarms: N/A" in src and "disabled by operator" in src)

check("rogue-AP probe stays unconditional",
      re.search(r"^    rogues = _unifi_json\(\"stat rogueap\"\)$", src, re.M)
      is not None)
check("admin-activity probe stays unconditional",
      re.search(r"^    admin = _unifi_json\(\"log admin-activity", src, re.M)
      is not None)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
