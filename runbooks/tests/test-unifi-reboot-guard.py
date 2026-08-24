#!/usr/bin/env python3
"""
Regression test for the UniFi "device rebooted" guard in health-check.sh
(found 2026-08-24).

A dip in derivative(uptime) is produced by a real reboot AND by a scrape gap,
so on 2026-08-14 a cross-check was added: a candidate whose CURRENT uptime
already exceeds the 24h window cannot have rebooted inside it. That guard was
inert from the day it shipped.

InfluxDB's Flux orders `keep()` output by its own rules, not by the order the
columns are requested in:

    keep(columns: ["name"])           ->  ,result,table,name          name at 3
    keep(columns: ["name","_time"])   ->  ,result,table,_time,name    name at 4

The guard read index 3 for the device name in BOTH queries. On the two-column
one that is the TIMESTAMP, so it compared timestamps against a set of device
names, matched nothing, and dropped nothing. The tell was printed on every run
and never read: the line came out as

    2026-08-24T00:10:07.603891672Z rebooted around Basement-AP-U6+

i.e. "<timestamp> rebooted around <name>" — backwards.

Live blast radius when found: three APs with 37d / 37d / 17d uptime were
reported as having rebooted, all at the same nanosecond, during a UniFi
controller flap.

The parser is extracted from health-check.sh rather than restated here, so the
test fails if the script regresses to positional indexing.

Run: python3 runbooks/tests/test-unifi-reboot-guard.py
"""
import pathlib
import re
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


# ---------------------------------------------------------------- structure
block = re.search(
    r"# Device reboots in last 24h.*?# AP/SW device count sanity check",
    src, re.S)
check("reboot block still present in health-check.sh", block is not None, True)
block_src = block.group(0) if block else ""

check("reboot rows are not read positionally",
      re.search(r"c\[3\]|c\[4\]", block_src) is None, True)
check("guard keys on the 'name' column by header",
      "r['name']" in block_src, True)
check("a baseline-unavailable branch exists (cannot-measure is not a pass)",
      "BASELINE-UNAVAILABLE" in block_src, True)
check("baseline query does not push the >24h filter into Flux "
      "(empty result must stay distinguishable from 'all freshly booted')",
      re.search(r"UPTIME_CSV=.*_value > 86400", block_src) is None, True)
check("reboot counter matches the full phrase, not the bare word",
      'grep -c "rebooted around"' in block_src, True)

# ------------------------------------------------------------------ parser
# Pull the real parser out of the script so behaviour, not a copy, is tested.
m = re.search(r'INFLUX_BY_HEADER="(.*?)\n"\n', src, re.S)
check("INFLUX_BY_HEADER parser is extractable", m is not None, True)
if not m:
    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1)

ns = {}
exec(m.group(1), ns)          # noqa: S102 - the point is to run the shipped code
table = ns["table"]

# Real header shapes, captured live from InfluxDB 2026-08-24.
UPTIME_CSV = (
    ",result,table,_value,name\n"
    ",_result,0,3196800,Basement-AP-U6+\n"          # 37d
    ",_result,1,3196800,Hallway-AP-U6 Pro\n"        # 37d
    ",_result,2,1468800,Living Room-AP-U7 Pro\n"    # 17d
    ",_result,3,600,Guest Room USW SW-8\n"          # 10m - genuinely rebooted
)
DIPS_CSV = (
    ",result,table,_time,name\n"
    ",_result,0,2026-08-24T00:10:07.603891672Z,Basement-AP-U6+\n"
    ",_result,1,2026-08-24T00:10:07.603891672Z,Hallway-AP-U6 Pro\n"
    ",_result,2,2026-08-24T00:10:07.603891672Z,Living Room-AP-U7 Pro\n"
    ",_result,3,2026-08-24T03:55:00.000000000Z,Guest Room USW SW-8\n"
)


def run(uptime_csv, dips_csv):
    base = [r for r in table(uptime_csv) if r.get("name")]
    stable = set()
    for r in base:
        try:
            if float(r.get("_value") or 0) > 86400:
                stable.add(r["name"])
        except ValueError:
            pass
    raw = [r for r in table(dips_csv) if r.get("name")]
    data = [r for r in raw if r["name"] not in stable]
    return base, raw, data


# The column ORDER differs between the two queries; parsing by header must not
# care. This is the exact condition the positional version got wrong.
check("header parser reads 'name' from a _time-first table",
      [r["name"] for r in table(DIPS_CSV)],
      ["Basement-AP-U6+", "Hallway-AP-U6 Pro", "Living Room-AP-U7 Pro",
       "Guest Room USW SW-8"])
check("header parser reads 'name' from a _value-first table",
      [r["name"] for r in table(UPTIME_CSV)][:2],
      ["Basement-AP-U6+", "Hallway-AP-U6 Pro"])

base, raw, data = run(UPTIME_CSV, DIPS_CSV)
check("all four dips are seen", len(raw), 4)
check("the three long-uptime dips are dropped as scrape artifacts",
      sorted(r["name"] for r in data), ["Guest Room USW SW-8"])

# Adversarial: the guard must not become a blanket suppressor. A device that
# really did reboot has a short current uptime and must survive.
check("a genuine reboot is still reported", len(data), 1)

# Adversarial: losing the baseline must not read as 'no reboots'.
base2, raw2, data2 = run("", DIPS_CSV)
check("empty baseline is detectable as a measurement failure", base2, [])
check("empty baseline does not silently drop candidates", len(data2), len(raw2))

# Adversarial: a garbage/HTML error body must not parse into phantom rows.
check("non-CSV error body yields no rows",
      list(table("<html>502 Bad Gateway</html>")), [])

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
