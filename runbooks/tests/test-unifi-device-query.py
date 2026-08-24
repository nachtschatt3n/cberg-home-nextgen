#!/usr/bin/env python3
"""
Regression test for the live UniFi device/client queries in health-check.sh
(found 2026-08-24).

The block called:

    unifictl local devices  -o json
    unifictl local clients  --wired -o json

The subcommands are `device list` and `client list`. unifictl rejects the
plural forms with "unrecognized subcommand", stderr went to /dev/null, and the
JSON parse fell into a bare `except: print(0)`. Net effect:

  - OFFLINE_DEVICES was 0 on every run the check ever made — a green verdict
    that no device state could change,
  - the client counts printed "?" forever.

Same shape as the `.spec.disks` Longhorn row in
docs/sops/audit-script-correctness.md: a query aimed at something that does not
exist, collapsing into a clean zero.

Secondary defect: `client list --limit` defaults to 30, so the printed wireless
count was a cap, not a measurement (30 reported vs 101 actual on this site).

The script text is asserted on directly, and the tally parser is exercised
against real payload shapes captured live on 2026-08-24.

Run: python3 runbooks/tests/test-unifi-device-query.py
"""
import json
import pathlib
import re
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
        print(f"  FAIL  {name}\n        got {got!r} want {want!r}")
        FAIL += 1


# ------------------------------------------------------- subcommand spelling
# `local devices` / `local clients` do not exist. Match the word boundary so
# `device list` / `client list` do not register as hits.
check("no call to the non-existent `unifictl local devices`",
      re.search(r"unifictl local devices\b", src) is None, True)
check("no call to the non-existent `unifictl local clients`",
      re.search(r"unifictl local clients\b", src) is None, True)
check("device enumeration uses `device list`",
      "unifictl local device list" in src, True)
check("client enumeration uses `client list`",
      "unifictl local client list" in src, True)

# ------------------------------------------------------------ measurability
check("device tally carries a QUERY-FAILED sentinel (not-measured != 0 offline)",
      "QUERY-FAILED" in src, True)
check("a not-measured branch raises a finding rather than scoring green",
      "offline-device check could not run" in src, True)
check("the tally reports a denominator, so an empty list is detectable",
      "device list empty" in src, True)
unifi_block = re.search(r"# --- Live controller check via unifictl.*?"
                        r"# --- Historical data from InfluxDB", src, re.S)
check("UniFi live block still present", unifi_block is not None, True)
# Strip shell comments first: the block's own comment quotes the old snippet.
unifi_code = "\n".join(
    l for l in (unifi_block.group(0) if unifi_block else "").splitlines()
    if not l.lstrip().startswith("#"))
check("no bare `except: print(0)` left swallowing the parse in the UniFi block",
      re.search(r"except:\s*print\(0\)", unifi_code) is None, True)

# ------------------------------------------------------------- limit default
check("client list raises --limit above the 30 default",
      len(re.findall(r"client list [^\n|]*--limit \d+", src)) == 2, True)

# -------------------------------------------------------- parser behaviour
# The tally snippet is extracted from the script so behaviour, not a copy, runs.
m = re.search(r"UNIFI_DEV_TALLY=\$\(unifictl local device list -o json "
              r"2>/dev/null \| python3 -c \"\n(.*?)\n\" 2>/dev/null", src, re.S)
check("tally parser is extractable from health-check.sh", m is not None, True)
if not m:
    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1)
parser = m.group(1)


def run(stdin_text):
    r = subprocess.run([sys.executable, "-c", parser], input=stdin_text,
                       capture_output=True, text=True)
    return (r.stdout.splitlines() or [""])[0].strip()


# Real payload shape: {"data": [...], "meta": {...}}, state 1 == online.
ONLINE = {"data": [{"name": f"dev{i}", "state": 1} for i in range(10)],
          "meta": {}}
check("all-online site tallies as 0 offline of 10", run(json.dumps(ONLINE)), "0 10")

MIXED = {"data": [{"name": "dev0", "state": 1},
                  {"name": "dev1", "state": 0},
                  {"name": "dev2", "state": 1}], "meta": {}}
check("an offline device is counted", run(json.dumps(MIXED)), "1 3")

# Adversarial: every not-measured shape must be distinguishable from 0 offline.
check("empty stdin (the old broken-subcommand case) is QUERY-FAILED",
      run(""), "QUERY-FAILED")
check("a CLI usage/error string is QUERY-FAILED",
      run("error: unrecognized subcommand 'devices'"), "QUERY-FAILED")
check("an HTML error body is QUERY-FAILED",
      run("<html>502 Bad Gateway</html>"), "QUERY-FAILED")
check("a non-list JSON payload is QUERY-FAILED",
      run('{"data": {"oops": true}}'), "QUERY-FAILED")

# Adversarial: an empty-but-valid device list must NOT read as a healthy 0.
# It tallies "0 0"; the denominator is what lets the caller reject it.
check("an empty controller inventory reports a zero denominator",
      run('{"data": [], "meta": {}}'), "0 0")

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
