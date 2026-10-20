#!/usr/bin/env python3
"""Tests for scripts/ninth-banner-capacity.py (CI runner admission by free CPU).

Fabricated kubectl JSON; pins: millicore parsing, scheduler-style pod requests
(init max rule), terminal pods ignored, cordoned/tainted/NotReady nodes
excluded, parallelism choice (4 -> 2 -> queue), one sims Job per submitter, and
FAIL LOUD on unreadable data (an empty read is never 'plenty of CPU').
"""
import importlib.util
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCRIPT = os.path.join(ROOT, "scripts", "ninth-banner-capacity.py")
spec = importlib.util.spec_from_file_location("admit", SCRIPT)
A = importlib.util.module_from_spec(spec)
spec.loader.exec_module(A)

fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


def raises(fn, *a):
    try:
        fn(*a)
    except A.DataError:
        return True
    return False


def node(name, cpu="17", unsched=False, taints=None, ready="True"):
    return {"metadata": {"name": name},
            "spec": {"unschedulable": unsched, "taints": taints or []},
            "status": {"allocatable": {"cpu": cpu},
                       "conditions": [{"type": "Ready", "status": ready}]}}


def pod(node_name, cpu, phase="Running", init=None):
    spec = {"nodeName": node_name, "containers": [{"resources": {"requests": {"cpu": cpu}}}]}
    if init:
        spec["initContainers"] = [{"resources": {"requests": {"cpu": c}}} for c in init]
    return {"spec": spec, "status": {"phase": phase}}


# millicore parsing
check("parse 500m", A.parse_cpu("500m") == 500)
check("parse 2", A.parse_cpu("2") == 2000)
check("parse 1.5", A.parse_cpu("1.5") == 1500)
check("parse 250u/n", A.parse_cpu("250000u") == 250 and A.parse_cpu("250000000n") == 250)
check("parse garbage fails loud", raises(A.parse_cpu, "lots") and raises(A.parse_cpu, ""))

# scheduler-style pod request: max(sum(containers), max(init))
check("init max rule", A.pod_request({"containers": [{"resources": {"requests": {"cpu": "1"}}}],
                                      "initContainers": [{"resources": {"requests": {"cpu": "2500m"}}}]}) == 2500)
check("sum of containers", A.pod_request({"containers": [{"resources": {"requests": {"cpu": "500m"}}},
                                                         {"resources": {"requests": {"cpu": "250m"}}}]}) == 750)
check("no request = 0", A.pod_request({"containers": [{}]}) == 0)

nodes = {"items": [node("n1"), node("n2"), node("n3")]}
pods = {"items": [pod("n1", "500m"), pod("n1", "1"), pod("n2", "2", init=["3"]),
                  pod("n3", "4", phase="Succeeded"), pod("n3", "4", phase="Failed"),
                  {"spec": {"containers": [{"resources": {"requests": {"cpu": "9"}}}]}, "status": {"phase": "Pending"}}]}
rows = {r[0]: r for r in A.node_table(nodes, pods)}
check("n1 requested 1500m", rows["n1"][2] == 1500 and rows["n1"][3] == 15500)
check("n2 init max counted (3000m)", rows["n2"][2] == 3000)
check("terminal + unscheduled pods ignored", rows["n3"][2] == 0)
check("free total", A.free_milli(nodes, pods) == 15500 + 14000 + 17000)

# excluded nodes
n2 = {"items": [node("n1"), node("n2", unsched=True),
                node("n3", taints=[{"key": "x", "effect": "NoSchedule"}]), node("n4", ready="False"),
                node("n5", taints=[{"key": "y", "effect": "PreferNoSchedule"}])]}
names = sorted(r[0] for r in A.node_table(n2, pods))
check("cordoned/tainted/NotReady excluded, PreferNoSchedule kept", names == ["n1", "n5"])

# fail loud
check("empty nodes fails loud", raises(A.node_table, {"items": []}, pods))
check("empty pods fails loud", raises(A.node_table, nodes, {"items": []}))
check("None data fails loud", raises(A.node_table, None, None))
check("all nodes cordoned fails loud", raises(A.node_table, {"items": [node("a", unsched=True)]}, pods))
bad = node("a"); del bad["status"]["allocatable"]
check("missing allocatable fails loud", raises(A.node_table, {"items": [bad]}, pods))
check("jobs unreadable fails loud", raises(A.job_in_flight, None, "x"))

# decide: 4 parallel -> 2 -> queue (req 1000m, headroom 2000m)
check("4-parallel needs 6 CPU", A.decide(6000, 1000, [4, 2], 2000) == ("admit", 4, 6000))
check("falls back to 2 (needs 4)", A.decide(5999, 1000, [4, 2], 2000) == ("admit", 2, 4000))
check("queue reports the 2-parallel need", A.decide(3999, 1000, [4, 2], 2000) == ("queue", None, 4000))
check("huge headroom queues", A.decide(11822, 1000, [4, 2], 999000)[0] == "queue")
check("fmt", A.fmt_cpu(11822) == "11.822" and A.fmt_cpu(6000) == "6" and A.fmt_cpu(0) == "0")


# one sims job in flight per submitter
def job(name, suite, sub, cond=None):
    return {"metadata": {"name": name, "labels": {"ci.cberg.home/suite": suite, A.SUBMITTER_LABEL: sub}},
            "status": {"conditions": [{"type": cond, "status": "True"}] if cond else []}}


jobs = {"items": [job("a", "sims", "x", "Complete"), job("b", "sims", "y"), job("c", "unit", "x"),
                  job("d", "sims", "x", "Failed")]}
check("terminal/other-submitter/other-suite ignored", A.job_in_flight(jobs, "x") == "")
jobs["items"].append(job("e", "sims", "x"))
check("non-terminal sims job of same submitter blocks", A.job_in_flight(jobs, "x") == "e")
check("other submitter unaffected", A.job_in_flight(jobs, "z") == "")

# CLI fails loud (exit 3, message) when kubectl is broken or returns junk
for label, kc in (("kubectl failing", "false"), ("kubectl junk output", "echo not-json")):
    env = dict(os.environ, TNB_KUBECTL=kc)
    r = subprocess.run([sys.executable, SCRIPT, "free"], capture_output=True, text=True, env=env)
    check(f"CLI {label}: exit 3, no number on stdout", r.returncode == 3 and r.stdout.strip() == "" and "FAIL" in r.stderr)

print("%d failure(s)" % len(fails))
sys.exit(1 if fails else 0)
