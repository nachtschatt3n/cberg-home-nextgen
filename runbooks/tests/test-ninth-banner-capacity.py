#!/usr/bin/env python3
"""Tests for scripts/ninth-banner-capacity.py (CI runner admission by free CPU).

Fabricated kubectl JSON; pins: millicore + memory parsing, scheduler-style pod
requests (init max rule), terminal pods ignored, cordoned/tainted/NotReady nodes
excluded, per-node first-fit of CPU AND memory with per-node headroom (a pod
never spans nodes: 3 x 1.5 CPU free does not admit one 2-CPU shard), the
namespace ResourceQuota, parallelism choice (4 -> 2 -> queue), one sims Job per
submitter, and FAIL LOUD on unreadable data (an empty read is never 'plenty of
CPU').
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


def node(name, cpu="17", unsched=False, taints=None, ready="True", mem="64Gi"):
    return {"metadata": {"name": name},
            "spec": {"unschedulable": unsched, "taints": taints or []},
            "status": {"allocatable": {"cpu": cpu, "memory": mem},
                       "conditions": [{"type": "Ready", "status": ready}]}}


def pod(node_name, cpu, phase="Running", init=None, mem=None):
    req = {"cpu": cpu}
    if mem:
        req["memory"] = mem
    spec = {"nodeName": node_name, "containers": [{"resources": {"requests": req}}]}
    if init:
        spec["initContainers"] = [{"resources": {"requests": {"cpu": c}}} for c in init]
    return {"spec": spec, "status": {"phase": phase}}


# millicore parsing
check("parse 500m", A.parse_cpu("500m") == 500)
check("parse 2", A.parse_cpu("2") == 2000)
check("parse 1.5", A.parse_cpu("1.5") == 1500)
check("parse 250u/n", A.parse_cpu("250000u") == 250 and A.parse_cpu("250000000n") == 250)
check("parse garbage fails loud", raises(A.parse_cpu, "lots") and raises(A.parse_cpu, ""))
GI = 1024 ** 3
check("mem 6Gi", A.parse_mem("6Gi") == 6 * GI)
check("mem 512Mi / 64921904Ki", A.parse_mem("512Mi") == 512 * 1024 ** 2 and A.parse_mem("64921904Ki") == 64921904 * 1024)
check("mem decimal 1G / plain / exponent", A.parse_mem("1G") == 10 ** 9 and A.parse_mem("1048576") == 1048576
      and A.parse_mem("129e6") == 129 * 10 ** 6)
check("mem garbage fails loud", raises(A.parse_mem, "lots") and raises(A.parse_mem, "") and raises(A.parse_mem, None))
check("pod memory request (init max rule)",
      A.pod_mem_request({"containers": [{"resources": {"requests": {"memory": "1Gi"}}}],
                         "initContainers": [{"resources": {"requests": {"memory": "3Gi"}}}]}) == 3 * GI)

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
bad = node("a"); del bad["status"]["allocatable"]["memory"]
check("missing allocatable.memory fails loud", raises(A.node_capacity, {"items": [bad]}, pods))
check("jobs unreadable fails loud", raises(A.job_in_flight, None, "x"))

# decide: per-node first-fit of CPU + memory, per-node headroom, quota
def cap(*spec):
    """rows from (name, cpu_free, mem_free) with nothing else running."""
    ns = {"items": [node(n, cpu=c, mem=m) for n, c, m in spec]}
    ps = {"items": [pod("elsewhere", "1")]}       # pod list must be non-empty
    return A.node_capacity(ns, ps)


def quota(name="ci-runner-quota", hard=None, used=None):
    return {"metadata": {"name": name}, "status": {"hard": hard or {}, "used": used or {}}}


big = cap(("n1", "17", "64Gi"), ("n2", "17", "64Gi"), ("n3", "17", "64Gi"))
NOQ = {"items": []}
cpu_req = (1000, 1 * GI)       # cpu lane: 1 CPU / 1Gi
brw_req = (2000, 6 * GI)       # browser lane: 2 CPU / 6Gi
check("4-parallel admitted on roomy nodes", A.decide(big, cpu_req, [4, 2], 2000, 2 * GI, NOQ)[:3] == ("admit", 4, 4000))
# THE single-node rule: 3 nodes x 1.5 CPU free = 4.5 summed, but no node fits a 2-CPU shard
tight = cap(("n1", "1500m", "64Gi"), ("n2", "1500m", "64Gi"), ("n3", "1500m", "64Gi"))
v = A.decide(tight, brw_req, [1], 0, 0, NOQ)
check("3 nodes x 1.5 CPU free do NOT admit one 2-CPU shard", v[0] == "queue" and v[2] == 2000 and "do not fit" in v[3])
check("...though the old cluster-wide sum would have (4.5 >= 2)", A.free_milli(
    {"items": [node("n1", cpu="1500m"), node("n2", cpu="1500m"), node("n3", cpu="1500m")]},
    {"items": [pod("x", "1")]}) == 4500)
check("first_fit places nothing that does not fit", A.first_fit(tight, 1, 2000, GI) is None)
# headroom is per node and is kept AFTER placement
h = cap(("n1", "4", "64Gi"), ("n2", "4", "64Gi"))
check("2 CPU headroom per node: 4 CPU node fits ONE 2-CPU pod", A.first_fit(h, 2, 2000, GI, 2000, 0) == ["n1", "n2"])
check("...and not three", A.first_fit(h, 3, 2000, GI, 2000, 0) is None)
check("falls back to 2 when 4 do not fit", A.decide(h, brw_req, [4, 2], 2000, 0, NOQ)[:2] == ("admit", 2))
check("queue reports the smallest option's need", A.decide(h, brw_req, [4, 3], 2000, 0, NOQ)[:3] == ("queue", None, 6000))
# memory: CPU is plentiful, memory is not
m = cap(("n1", "16", "10Gi"), ("n2", "16", "10Gi"), ("n3", "16", "10Gi"))
check("memory: 6Gi shard fits a 10Gi node without mem headroom", A.decide(m, brw_req, [1], 0, 0, NOQ)[0] == "admit")
v = A.decide(m, brw_req, [1], 0, 5 * GI, NOQ)
check("memory: 10Gi free - 5Gi headroom < 6Gi -> queue despite 16 CPU free", v[0] == "queue" and "Gi" in v[3])
check("memory: 3 x 10Gi = 30Gi summed still fits only 3 x 6Gi shards (one per node)",
      A.first_fit(m, 3, 2000, 6 * GI) == ["n1", "n2", "n3"] and A.first_fit(m, 4, 2000, 6 * GI) is None)
# ResourceQuota
q_ok = {"items": [quota(hard={"pods": "31", "requests.cpu": "62", "requests.memory": "165Gi", "limits.cpu": "141"},
                        used={"pods": "10", "requests.cpu": "20", "requests.memory": "60Gi", "limits.cpu": "40"})]}
check("quota with room admits 4", A.decide(big, brw_req, [4, 2], 2000, 2 * GI, q_ok)[:2] == ("admit", 4))
q_pods = {"items": [quota(hard={"pods": "31"}, used={"pods": "28"})]}
check("quota pods: 28/31 -> 4 refused, 2 admitted", A.decide(big, brw_req, [4, 2], 2000, 0, q_pods)[:2] == ("admit", 2))
q_cpu = {"items": [quota(hard={"requests.cpu": "62"}, used={"requests.cpu": "60500m"})]}
v = A.decide(big, brw_req, [4, 2], 2000, 0, q_cpu)
check("quota requests.cpu: 1.5 left -> queue with a quota reason", v[0] == "queue" and "requests.cpu" in v[3])
q_mem = {"items": [quota(hard={"requests.memory": "165Gi"}, used={"requests.memory": "155Gi"})]}
v = A.decide(big, brw_req, [2, 1], 0, 0, q_mem)
check("quota requests.memory: 10Gi left -> one 6Gi shard, not two", v[:2] == ("admit", 1))
check("no quota object = no quota limit", A.decide(big, brw_req, [4], 0, 0, NOQ)[0] == "admit")
check("quota list unreadable fails loud", raises(A.decide, big, brw_req, [4], 0, 0, None) is False
      and raises(A.quota_shortfall, None, 1, 1, 1))
check("quota without status fails loud", raises(A.quota_shortfall, {"items": [{"metadata": {"name": "q"}}]}, 1, 1, 1))
check("quota missing usage for a hard key fails loud",
      raises(A.quota_shortfall, {"items": [quota(hard={"pods": "3"}, used={})]}, 1, 1, 1))
# --req token from podreq; a bare CPU value (older trigger) still works
check("req token cpu,mem", A.parse_req_token("2000,6442450944") == (2000, 6 * GI))
check("req token bare cpu = mem 0", A.parse_req_token("1000") == (1000, 0))
check("req token junk fails loud", raises(A.parse_req_token, "x") and raises(A.parse_req_token, "1,2,3")
      and raises(A.parse_req_token, "0,5"))
check("fmt_mem", A.fmt_mem(6 * GI) == "6Gi" and A.fmt_mem(1536 * 1024 ** 2) == "1.5Gi")
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

# submitter resolution
import types
def fake_run(stdout, rc=0):
    return lambda *a, **k: types.SimpleNamespace(returncode=rc, stdout=stdout, stderr="")
sha = "0123456789abcdef"
check("env SUBMITTER wins", A.resolve_submitter(sha, {"SUBMITTER": "Int-0412"}, run=fake_run("  origin/other\n")) == ("int-0412", "env"))
check("branch from the game repo, HEAD pointer skipped, origin/ stripped",
      A.resolve_submitter(sha, {}, run=fake_run("  origin/HEAD -> origin/main\n  origin/int-0412\n  origin/main\n")) == ("int-0412", "branch"))
check("branch sanitized for a label", A.resolve_submitter(sha, {}, run=fake_run("  origin/Feat/My Lane!\n")) == ("feat-my-lane", "branch"))
check("sanitize caps at 63 and trims ends", len(A.sanitize_label("a" * 80)) == 63 and A.sanitize_label("--x_-") == "x")
check("no containing branch -> sha8", A.resolve_submitter(sha, {}, run=fake_run("")) == ("01234567", "sha"))
check("git failure -> sha8 (no error, not empty)", A.resolve_submitter(sha, {}, run=fake_run("", rc=128)) == ("01234567", "sha"))
def boom(*a, **k): raise OSError("no git")
check("missing repo/git -> sha8", A.resolve_submitter(sha, {}, run=boom) == ("01234567", "sha"))
check("empty env SUBMITTER is not 'set'", A.resolve_submitter(sha, {"SUBMITTER": " "}, run=fake_run("")) [1] == "sha")
# real git: fabricated game repo; the cberg repo's own branch is never consulted
import tempfile
# scrub GIT_* (the pre-commit hook exports GIT_INDEX_FILE etc.; they would redirect the fixture repo)
for _k in [k for k in os.environ if k.startswith("GIT_")]:
    del os.environ[_k]
with tempfile.TemporaryDirectory() as d:
    g = lambda *c: subprocess.run(["git", "-C", d] + list(c), capture_output=True, text=True, check=True).stdout.strip()
    subprocess.run(["git", "init", "-q", d], check=True)
    g("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "x")
    head = g("rev-parse", "HEAD")
    g("update-ref", "refs/remotes/origin/lane-7", head)
    check("real git: remote branch containing sha", A.resolve_submitter(head, {}, game_repo=d) == ("lane-7", "branch"))
    check("real git: unknown sha -> sha8", A.resolve_submitter("f" * 40, {}, game_repo=d) == ("ffffffff", "sha"))
src = open(SCRIPT.replace("capacity.py", "capacity.py")).read()
check("cberg branch never used (no rev-parse --abbrev-ref in trigger)",
      "--abbrev-ref" not in open(os.path.join(ROOT, "scripts", "ninth-banner-test.sh")).read())

# CLI fails loud (exit 3, message) when kubectl is broken or returns junk
for label, kc in (("kubectl failing", "false"), ("kubectl junk output", "echo not-json")):
    env = dict(os.environ, TNB_KUBECTL=kc)
    r = subprocess.run([sys.executable, SCRIPT, "free"], capture_output=True, text=True, env=env)
    check(f"CLI {label}: exit 3, no number on stdout", r.returncode == 3 and r.stdout.strip() == "" and "FAIL" in r.stderr)

# CLI end to end with a fake kubectl (nodes / pods / resourcequota by argv)
import json as _json
with tempfile.TemporaryDirectory() as d:
    fixtures = {
        "nodes": {"items": [node("n1", cpu="1500m"), node("n2", cpu="1500m"), node("n3", cpu="1500m")]},
        "pods": {"items": [pod("n1", "0")]},
        "resourcequota": {"items": []},
    }
    for k, v in fixtures.items():
        open(os.path.join(d, k + ".json"), "w").write(_json.dumps(v))
    fake = os.path.join(d, "kubectl")
    open(fake, "w").write("#!/bin/sh\nshift; cat \"$(dirname \"$0\")/$1.json\"\n")
    os.chmod(fake, 0o755)
    env = dict(os.environ, TNB_KUBECTL=fake)
    r = subprocess.run([sys.executable, SCRIPT, "decide", "--req", "2000,6442450944", "--par", "1",
                        "--headroom", "0"], capture_output=True, text=True, env=env)
    check("CLI decide: 3 x 1.5 CPU -> queue (exit 10) with a reason",
          r.returncode == 10 and r.stdout.startswith("queue 2 4.5 (") and "do not fit" in r.stdout)
    r = subprocess.run([sys.executable, SCRIPT, "decide", "--req", "1000,1073741824", "--par", "4 2",
                        "--headroom", "0"], capture_output=True, text=True, env=env)
    check("CLI decide: 1-CPU pods first-fit one per node -> admit 2 of 4/2",
          r.returncode == 0 and r.stdout.split()[:2] == ["admit", "2"])
    tpl = os.path.join(d, "job.yaml")
    open(tpl, "w").write("spec:\n  template:\n    spec:\n      containers:\n"
                         "        - resources: {requests: {cpu: '2', memory: 6Gi}}\n")
    r = subprocess.run([sys.executable, SCRIPT, "podreq", tpl], capture_output=True, text=True)
    check("CLI podreq prints cpu_m,mem_bytes", r.returncode == 0 and r.stdout.strip() == "2000,6442450944")

print("%d failure(s)" % len(fails))
sys.exit(1 if fails else 0)
