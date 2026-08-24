#!/usr/bin/env python3
"""Regression: non-security CRITICAL findings must rank as CRITICAL.

Before this, `collect()` never selected `severity` for non-security sections
and `render()` hardcoded MEDIUM for every one of them. The contextual
`risk_tier` model is security-only, so a health finding stored as
`severity='critical'` -- a component actively degrading -- rendered as a
MEDIUM beneath a grouped doc line. Cycle 6c46d183 (2026-08-24) shipped that
way: Frigate at 98.6% of its memory cgroup limit sat at position 5.
"""
import importlib.util, sys
spec = importlib.util.spec_from_file_location(
    "render_board", "/Users/mu/code/cberg-home-nextgen/runbooks/render-board.py")
rb = importlib.util.module_from_spec(spec); spec.loader.exec_module(rb)

W = {"warnings": []}
BASE = {"cycle_id": "test1234-0000-0000", "started_at": "2026-08-24 02:02",
        "tiers": {}, "criticals": [], "high": [], "high_accepted": 0,
        "sections": {}, "slos": [], "planned": {}, "medium_groups": [],
        "new_other": [], "ran": ["health", "version"], "warnings": []}

def mk(**kw):
    d = dict(BASE); d.update(kw); return d

def find(lines, frag):
    return [l for l in lines if frag in l]

fails = []
def check(cond, msg):
    if not cond: fails.append(msg)

# 1. a health critical is rated CRITICAL, not MEDIUM
out = rb.render(mk(new_other=[{"id":"F-1","section":"health","severity":"critical",
                               "title":"frigate walking into its memory limit"}]), W).splitlines()
check(find(out, "**[CRITICAL]** `health/critical`"), "health critical not rendered CRITICAL")
check(not find(out, "**[MEDIUM]** `health/new`"), "health critical leaked into MEDIUM bucket")
check(not find(out, "no CRITICAL items"), "'no CRITICAL items' printed despite a critical")

# 2. criticals are NEVER collapsed, even past the >5 grouping threshold
many = [{"id":f"F-{i}","section":"health","severity":"critical","title":f"crit {i}"}
        for i in range(8)]
out = rb.render(mk(new_other=many), W).splitlines()
check(len(find(out, "**[CRITICAL]**")) == 8, "criticals were grouped/collapsed")

# 3. ADVERSARIAL: non-critical severities must NOT be promoted
for sev in ("warning", "monitor", "deferred", "info"):
    out = rb.render(mk(new_other=[{"id":"F-9","section":"health","severity":sev,
                                   "title":"routine"}]), W).splitlines()
    check(not find(out, "**[CRITICAL]**"), f"severity={sev} wrongly promoted to CRITICAL")
    check(find(out, "**[MEDIUM]** `health/new`"), f"severity={sev} lost from the board")

# 4. ADVERSARIAL: mixed section -- grouping count must EXCLUDE the criticals
mixed = ([{"id":"F-c","section":"version","severity":"critical","title":"crit"}]
         + [{"id":f"F-{i}","section":"version","severity":"monitor","title":f"m{i}"}
            for i in range(7)])
out = rb.render(mk(new_other=mixed), W).splitlines()
check(len(find(out, "**[CRITICAL]**")) == 1, "mixed: critical not surfaced once")
grp = find(out, "`version/new`")
check(grp and "7 new finding(s)" in grp[0],
      f"mixed: group count should exclude the critical, got {grp}")

# 5. ADVERSARIAL: security criticals still render, and both kinds coexist
out = rb.render(mk(criticals=[{"id":"F-s","title":"sec crit"}],
                   new_other=[{"id":"F-h","section":"health","severity":"critical",
                               "title":"health crit"}]), W).splitlines()
check(len(find(out, "**[CRITICAL]**")) == 2, "security+ops criticals do not coexist")

# 6. the clean case still says so
out = rb.render(mk(), W).splitlines()
check(find(out, "no CRITICAL items"), "clean board lost its 'no CRITICAL items' line")

if fails:
    print("FAIL:"); [print("  -", f) for f in fails]; sys.exit(1)
print(f"PASS — 6 scenarios, {len(BASE)} base keys, no over-promotion")
