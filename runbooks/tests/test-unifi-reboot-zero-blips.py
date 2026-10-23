#!/usr/bin/env python3
"""
Regression test for F-36517bdb: health-check.sh Section 18 counted unpoller
uptime==0 scrape blips as reboots. The 2026-10-08 shape was 18 drops to 0 that
each recovered to ~2.73M s, plus ONE real reset (to 949 s). Must yield 1.

The resets() function is extracted from health-check.sh, not restated.
Run: python3 runbooks/tests/test-unifi-reboot-zero-blips.py
"""
import pathlib
import re
import sys

src = (pathlib.Path(__file__).resolve().parents[1] / "health-check.sh").read_text()
m = re.search(r'INFLUX_BY_HEADER="(.*?)\n"\n', src, re.S)
assert m, "INFLUX_BY_HEADER not extractable"
ns = {}
exec(m.group(1), ns)  # noqa: S102
resets = ns["resets"]

T0 = 1791417600  # 2026-10-08T00:00:00Z
BASE = 2730000


def iso(t):
    import time
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def row(t, v, name="DMP-CBERG"):
    return {"name": name, "_measurement": "usw", "_time": iso(t), "_value": str(v)}


rows = []
t = T0
up = BASE
for i in range(2880):                       # 24h at 30 s
    t = T0 + i * 30
    up = BASE + i * 30
    if i % 150 == 10 and i < 2700:          # 18 blips to 0
        rows.append(row(t, 0))
    elif i == 2000:                         # one real reset
        rows.append(row(t, 949))
        BASE = 949 - i * 30                 # later samples continue from 949
    else:
        rows.append(row(t, BASE + i * 30))

blips = sum(1 for r in rows if r["_value"] == "0")
fails = 0


def check(name, got, want):
    global fails
    ok = got == want
    print(("  PASS  " if ok else "  FAIL  ") + name + ("" if ok else f" got {got!r} want {want!r}"))
    fails += not ok


check("fixture really contains 18 zero blips", blips, 18)
check("2026-10-08 shape yields exactly 1 reboot", len(resets(rows)), 1)
check("only zero blips yield 0", len(resets([r for r in rows if r["_value"] != "949"][:1000])), 0)
check("zero is never used as the previous sample",
      len(resets([row(T0, 5000), row(T0 + 30, 0), row(T0 + 60, 5060)])), 0)
check("a reset right after a zero blip is still caught",
      len(resets([row(T0, 5000), row(T0 + 30, 0), row(T0 + 60, 20)])), 1)
check("series for different devices do not interleave",
      len(resets([row(T0, 9000, "a"), row(T0 + 1, 100, "b"), row(T0 + 30, 9030, "a"), row(T0 + 31, 130, "b")])), 0)
sys.exit(1 if fails else 0)
