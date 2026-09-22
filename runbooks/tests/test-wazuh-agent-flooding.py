#!/usr/bin/env python3
"""Pin the per-agent event-queue overflow slice in security-check.py s13 (F-9952c59e).

Measured 2026-09-18: 10 "queue is full" + 12 `agent_flooding` alerts, ALL on
one node. Two things hid them. A phrase query on `rule.description` — a
KEYWORD field — returns 0 by construction, so the first re-check read "does
not reproduce". And the group-level triage keeps `agent_flooding` behind a
`> 5` volume floor because it is noisy cluster-wide, so a quiet day's 3
events on one node never surfaced. A dropping agent turns every other SIEM
count from that node into a floor, so the node has to be named.

COMMISSIONING STRAW: the pre-fix triage (`flag_wazuh_groups` with the
section's own sets) is run over a day with 3 agent_flooding events and
returns nothing; the per-agent detector over the same day names the agent.

Run: python3 runbooks/tests/test-wazuh-agent-flooding.py
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import sys
from pathlib import Path

os.environ.setdefault("_MISE_ACTIVATED", "1")
os.environ.pop("SWEEP_PG_DSN", None)
ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
sys.argv = ["security-check.py"]
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


def buckets(**kw):
    return [{"key": k, "doc_count": n} for k, n in kw.items()]


print("wazuh agent flooding\n")

# ── the pure detector ────────────────────────────────────────────────────────
print("-- detector --")
check("a SINGLE event on one agent is reported (no volume floor)",
      sc.flag_wazuh_flooding_agents(buckets(**{"node-b": 1})) == [("node-b", 1)])
check("agents with zero events are not reported",
      sc.flag_wazuh_flooding_agents(buckets(**{"node-a": 0, "node-b": 3})) == [("node-b", 3)])
check("an empty aggregation yields nothing and does not raise",
      sc.flag_wazuh_flooding_agents([]) == [])
check("a bucket missing doc_count is treated as zero, not as an error",
      sc.flag_wazuh_flooding_agents([{"key": "node-c"}]) == [])

# ── COMMISSIONING STRAW ──────────────────────────────────────────────────────
print("\n-- commissioning straw --")
CONCERNING = {"authentication_failed", "authentication_failures", "web_attack", "attack",
              "attacks", "rootcheck", "syscheck", "ids", "ipsec", "agent_flooding",
              "configuration_failure"}
RARE = {"intrusion_detection", "privilege_escalation", "recon", "web_scan"}
quiet_day_groups = buckets(homelab=4000, agent_flooding=3)
check("STRAW: group-level triage on a quiet day (3 agent_flooding events) reports nothing",
      sc.flag_wazuh_groups(quiet_day_groups, CONCERNING, RARE) == [])
check("the per-agent detector on the same day names the node",
      sc.flag_wazuh_flooding_agents(buckets(**{"node-b": 3})) == [("node-b", 3)])


# ── the section slice, end to end, with a fake indexer ───────────────────────
print("\n-- section slice --")


class FakeWazuh:
    """Answers the s13 queries by shape. Only the agent_flooding term query
    carries the fixture; every other slice gets an empty, well-formed answer."""

    def __init__(self, flooding_buckets, *, fail_flooding=False):
        self.flooding = flooding_buckets
        self.fail_flooding = fail_flooding
        self.bodies = []

    def query(self, body, timeout=15):
        self.bodies.append(body)
        must = (body.get("query", {}).get("bool", {}) or {}).get("must", [])
        if any(m.get("term", {}).get("rule.groups") == "agent_flooding" for m in must):
            if self.fail_flooding:
                return None
            return {"hits": {"total": {"value": sum(b["doc_count"] for b in self.flooding)}},
                    "aggregations": {"by_agent": {"buckets": self.flooding}}}
        return {"hits": {"total": {"value": 0}},
                "aggregations": {"by_rule": {"buckets": []}, "by_agent": {"buckets": []},
                                 "by_groups": {"buckets": []}}}


def run_slice(wz):
    saved_run = sc.run
    # agent_control -l via kubectl exec: give the heartbeat slice a registered list
    sc.run = lambda cmd, timeout=30: "   ID: 001, Name: node-a, IP: any, Active\n" if "agent_control" in cmd else ""
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            status, f, body = sc.s13_wazuh_siem(wz)
    finally:
        sc.run = saved_run
    return f, body


wz = FakeWazuh(buckets(**{"node-b": 3}))
f, body = run_slice(wz)
flood_findings = [m for s, m, _ in f._items if "overflowed its event queue" in m]
check("a flooding agent -> one WARNING naming the agent and the count",
      len(flood_findings) == 1 and "`node-b`" in flood_findings[0] and "3 agent_flooding" in flood_findings[0],
      str([m for _, m, _ in f._items]))
check("the report line lists the agent",
      "Agent event-queue overflow" in body and "node-b (3)" in body, body)
flood_q = [b for b in wz.bodies
           if any(m.get("term", {}).get("rule.groups") == "agent_flooding"
                  for m in (b.get("query", {}).get("bool", {}) or {}).get("must", []))]
check("the query is an ENUMERATING one: term on rule.groups + terms agg on agent.name, 24h",
      len(flood_q) == 1
      and flood_q[0]["aggs"]["by_agent"]["terms"]["field"] == "agent.name"
      and any(m.get("range", {}).get("@timestamp", {}).get("gte") == "now-24h"
              for m in flood_q[0]["query"]["bool"]["must"]))
check("no phrase / match query on rule.description anywhere in the slice",
      not any("match_phrase" in str(b) or '"match": {"rule.description"' in str(b) for b in wz.bodies))

f, body = run_slice(FakeWazuh([]))
check("no flooding -> no finding, and the report says enumerated by group, not a bare zero",
      not any("overflowed" in m for _, m, _ in f._items) and "**0** across 0 agent(s)" in body, body)

f, body = run_slice(FakeWazuh([], fail_flooding=True))
check("query failure -> NOT MEASURED in the report, no finding, never a clean zero",
      "NOT MEASURED" in body and "**0** across" not in body
      and not any("overflowed" in m for _, m, _ in f._items), body)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
