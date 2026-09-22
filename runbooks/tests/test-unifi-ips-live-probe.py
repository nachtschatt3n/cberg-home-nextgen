#!/usr/bin/env python3
"""
Regression test for the LIVE UniFi IPS/IDS probe in security-check.py
(F-64d54ab1; supersedes the hardcoded-constant contract).

The defect: `UNIFI_IPS_ENABLED = False` was a source-code constant consumed
before any probe, so the section printed a green "IPS/IDS disabled by operator
decision" line from a stale value with no link to controller state. Had the
operator re-enabled threat management, real alarms would have accumulated
unread indefinitely.

Contract, asserted through the module's own functions:
  1. _classify_unifi_alarm_probe: HTTP 404 in the ERROR TEXT -> "n/a" (the
     disabled feature, not a gap); a live answer -> "measured" with the list;
     everything else -> "unmeasured". rc alone can never yield "n/a".
  2. _s11_ips_alarms: "unmeasured" records DEGRADED and never prints a clean
     zero; "n/a" reports N/A and records nothing; "measured" raises a
     CRITICAL per alarm, or reports 0 with the feed marked live. A live feed
     while the declaration says disabled is a WARNING (declaration drift).
  3. _probe_unifi_ips_alarms retries only the transient class, never a 404.
  4. COMMISSIONING STRAW: a constant gate — a probe that answers "n/a"
     without looking, which is exactly what `if not UNIFI_IPS_ENABLED:` did —
     turns a controller output carrying an alarm into no finding at all;
     the live classifier on the same output raises the alarm.

Run: python3 runbooks/tests/test-unifi-ips-live-probe.py
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import sys
from pathlib import Path

os.environ.setdefault("_MISE_ACTIVATED", "1")
ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
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


NOT_FOUND = "Error: Resource not found (404) at https://controller.example.internal/api/s/default/list/alarm"
ALARM_OUT = (0, '{"data":[{"msg":"alarm A"}]}', "")

# 1 — classifier table
for (rc, out, err), want in [
    ((1, "", NOT_FOUND), "n/a"),
    ((1, "", "Command timed out after 15 seconds"), "unmeasured"),
    ((1, "", "Error: login failed (401)"), "unmeasured"),
    ((1, "", "Error: 500 Internal Server Error"), "unmeasured"),
    ((1, "", ""), "unmeasured"),
    ((0, "", ""), "unmeasured"),
    ((0, "not json", ""), "unmeasured"),
    ((0, '{"data": 5}', ""), "unmeasured"),
    ((0, "[]", ""), "measured"),
    (ALARM_OUT, "measured"),
]:
    got = sc._classify_unifi_alarm_probe(rc, out, err)[0]
    check(f"classify rc={rc} out={out[:12]!r} err={err[:28]!r} -> {want}", got == want, f"got {got}")
check("measured answer carries the alarm list",
      sc._classify_unifi_alarm_probe(*ALARM_OUT)[1] == [{"msg": "alarm A"}])
check("rc!=0 with no 404 text is never n/a (a failed probe must not read as disabled)",
      all(sc._classify_unifi_alarm_probe(1, "", e)[0] != "n/a"
          for e in ("", "timeout", "Error: 502 Bad Gateway", "unauthorized")))


# 2 — the section block under each probe outcome
def run_block(probe):
    f, lines = sc.Findings(), []
    before = list(sc.DEGRADED.reasons)
    with contextlib.redirect_stdout(io.StringIO()):
        sc._s11_ips_alarms(f, lines, probe=probe)
    return f, "".join(lines), [r for r in sc.DEGRADED.reasons if r not in before]


f, text, new = run_block(lambda: ("unmeasured", None, "Command timed out after 15 seconds"))
check("unmeasured -> DEGRADED recorded, naming the alarm feed",
      len(new) == 1 and "alarm feed" in new[0], f"{new}")
check("unmeasured -> NOT MEASURED in the report, no clean zero, no CRITICAL",
      "NOT MEASURED" in text and "**0**" not in text and f.count(sc.CRITICAL) == 0, text)

f, text, new = run_block(lambda: ("n/a", None, "HTTP 404"))
check("n/a -> N/A reported as the disabled feature, nothing DEGRADED",
      "IPS/IDS alarms: N/A" in text and "disabled by operator" in text and new == [], text)
check("n/a with declaration False -> no drift finding", f.count(sc.WARNING) == 0)

f, text, new = run_block(lambda: ("measured", [{"msg": "alarm A"}, {"key": "alarm B"}], ""))
check("measured with alarms -> one CRITICAL per alarm", f.count(sc.CRITICAL) == 2,
      f"{[m for _, m, _ in f._items]}")
check("measured with declaration False -> declaration-drift WARNING",
      any("declares" in m and "disabled" in m for s, m, _ in f._items if s == sc.WARNING))

f, text, new = run_block(lambda: ("measured", [], ""))
check("measured empty -> 0 alarms, feed marked live, nothing DEGRADED",
      "**0**" in text and "feed live" in text and new == [] and f.count(sc.CRITICAL) == 0, text)

# declaration drift in the other direction
saved_decl = sc.UNIFI_IPS_ENABLED
sc.UNIFI_IPS_ENABLED = True
try:
    f, text, new = run_block(lambda: ("n/a", None, "HTTP 404"))
    check("n/a with declaration True -> drift WARNING (declared enabled, controller has no feed)",
          f.count(sc.WARNING) == 1 and "declared ENABLED" in f._items[0][1])
    f, text, new = run_block(lambda: ("measured", [], ""))
    check("measured with declaration True -> no drift finding", f.count(sc.WARNING) == 0)
finally:
    sc.UNIFI_IPS_ENABLED = saved_decl


# 3 — retry policy of the real probe (run_cmd and sleep stubbed)
def probe_with(seq):
    calls: list[str] = []

    def fake_run_cmd(cmd, timeout=30):
        calls.append(cmd)
        return seq[min(len(calls) - 1, len(seq) - 1)]

    saved = sc.run_cmd, sc.time.sleep
    sc.run_cmd, sc.time.sleep = fake_run_cmd, (lambda s: None)
    try:
        return sc._probe_unifi_ips_alarms(), calls
    finally:
        sc.run_cmd, sc.time.sleep = saved


(state, alarms, _), calls = probe_with([(1, "", NOT_FOUND)])
check("a 404 is an answer: n/a after exactly one call", state == "n/a" and len(calls) == 1, f"{calls}")
(state, alarms, _), calls = probe_with([(1, "", "Error: login failed"), (1, "", NOT_FOUND)])
check("a transient blip is retried, then the 404 answer stands", state == "n/a" and len(calls) == 2)
(state, alarms, _), calls = probe_with([(1, "", "Command timed out")])
check("three failures -> unmeasured after 3 calls (2 retries)", state == "unmeasured" and len(calls) == 3)
(state, alarms, _), calls = probe_with([ALARM_OUT])
check("a live feed is measured on the first call", state == "measured" and alarms == [{"msg": "alarm A"}] and len(calls) == 1)
check("the probe runs the alarm-feed command", all(c == sc._UNIFI_ALARM_CMD for c in calls))

# 4 — COMMISSIONING STRAW: the pre-fix constant gate
f_straw, _, _ = run_block(lambda: ("n/a", None, ""))            # never looks at the controller
check("STRAW: a constant gate turns a live alarm into no finding (the F-64d54ab1 blind spot)",
      f_straw.count(sc.CRITICAL) == 0)
f_live, _, _ = run_block(lambda: sc._classify_unifi_alarm_probe(*ALARM_OUT))
check("the live classifier on the same controller output raises the alarm",
      f_live.count(sc.CRITICAL) == 1)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
