#!/usr/bin/env python3
"""Thermal gate for the ci-runner test pods: one admission tick.

    scripts/ninth-banner-admit.py            one tick (called every ~10 s by
                                             every running ninth-banner-test.sh)
    scripts/ninth-banner-admit.py --status   print node state + queue, change nothing
    scripts/ninth-banner-admit.py --release-all
                                             ROLLBACK ONLY: ungate every gated pod
                                             without pinning (docs/sops/ci-runner.md)

Contract (docs/sops/ci-runner.md, "Thermal gate"):
* Jobs rendered from job-template.yaml.tpl create their pods with the scheduling
  gate GATE: Pending (SchedulingGated), invisible to the scheduler, no node
  resources used, so nothing runs until a tick admits it.
* Two LANES, each with its own per-node slots: "browser" (Playwright suites,
  usually on the iGPU, 2 CPU request / 4 limit) and "cpu" (sims/unit: Node
  without a browser, 1 CPU request / 1.5 limit, no GPU). Lane = pod label
  ci.cberg.home/lane; pods created before the label existed: suite sims/unit
  without a GPU request = cpu, everything else = browser.
* A tick admits gated pods OLDEST FIRST per lane (a pod whose lane is closed
  does not block the other lane), at most one per node per tick. It pins
  the pod to a node (nodeSelector kubernetes.io/hostname) and removes the gate.
  A node is open for a pod only if all of these hold:
  - its package temperature, averaged over 2 min, is below the lane's limit:
    browser OPEN_BELOW_C (node has no CI pod) or SECOND_OPEN_BELOW_C (node
    already has a CI pod); cpu CPU_OPEN_BELOW_C;
  - its peak over the last 3 min is below HOT_C / SECOND_HOT_C / CPU_HOT_C;
  - lane slots: < MAX_PER_NODE browser pods (a second one only on
    SECOND_POD_NODES), < MAX_CPU_PER_NODE cpu pods (bound or pinned, not finished);
  - CI CPU requests on the node stay <= NODE_CPU_BUDGET, and the pod's CPU,
    memory and i915 requests fit the node's allocatable minus every running/
    pending pod's requests (kube-state-metrics + the CI pods themselves);
  - no CI pod was admitted or started there in the last SETTLE_SECONDS, so the
    previous pod's heat shows before another pod is added.
* BRAKE, PER NODE (since 2026-10-04 late evening): a node whose package
  temperature reached >= BRAKE_C (a 1-min max >= BRAKE_C) gets no NEW CI pod
  until BRAKE_MINUTES after that reading; the other nodes keep admitting under
  their normal limits (a CI pod on one node does not heat another, and
  nuc14-02 alone reaches >= 100 C from production load). GLOBAL hold: if
  >= GLOBAL_BRAKE_NODES nodes are braked at once (each read >= BRAKE_C within
  the last BRAKE_MINUTES), nothing is admitted anywhere (a shared cause such as
  room heat). Running pods are untouched.
* Fail-closed: no or stale Prometheus data (temperature or node capacity)
  means no node is open, and pods queue.
  Production pods are never touched: the tick only reads and patches pods in
  ci-runner. Running pods are never changed: the gate only decides where and
  when a NEW pod starts.
* Concurrency: every trigger instance runs ticks; a host-wide lock lets one
  run at a time (others skip), so two runs never fill the same free slot.
"""
import fcntl
import json
import math
import os
import subprocess
import sys
import time
import urllib.parse
from datetime import datetime, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NS = "ci-runner"
SELECTOR = "app.kubernetes.io/name=the-ninth-banner-tests"
GATE = "ci.cberg.home/thermal"
RELEASED_AT = "ci.cberg.home/released-at"
OPEN_BELOW_C = float(os.environ.get("GATE_OPEN_BELOW_C", "85"))
HOT_C = float(os.environ.get("GATE_HOT_C", "93"))
# Second pod on a node (2026-10-04 tightening after a 103 C single sample on
# nuc14-03 with 2 shards; 102 C rebooted a node on 2026-08-08):
SECOND_OPEN_BELOW_C = float(os.environ.get("GATE_SECOND_OPEN_BELOW_C", "78"))
SECOND_HOT_C = float(os.environ.get("GATE_SECOND_HOT_C", "90"))
# Only these nodes may take a SECOND CI pod at all. Data 2026-10-04: nuc14-03
# hit 103 C twice within ~2 min of its 2nd shard starting (15:32, 16:28) even
# though it passed the 78/90 C pre-check (the new shard's npm ci/startup burst
# is what spikes it); nuc14-01 with 2 shards peaked at 92-95 C; nuc14-02 reaches
# 96-100 C with ONE shard or none. Comma-separated; empty = 1 CI pod per node.
SECOND_POD_NODES = {n for n in os.environ.get("GATE_SECOND_POD_NODES", "k8s-nuc14-01").split(",") if n}
BRAKE_C = float(os.environ.get("GATE_BRAKE_C", "100"))
BRAKE_MINUTES = int(os.environ.get("GATE_BRAKE_MINUTES", "10"))
# Braked nodes at once that freeze ALL admission; 0 = never global
GLOBAL_BRAKE_NODES = int(os.environ.get("GATE_GLOBAL_BRAKE_NODES", "2"))
MAX_PER_NODE = int(os.environ.get("GATE_MAX_PER_NODE", "2"))   # browser lane
# CPU lane (sims/unit). Heat data 2026-10-04 (12 h, 1-min samples): one sims
# shard is a single core at full turbo and costs about as much as a GPU browser
# shard: node 2-min average +12 C on n01/n02, +22 C on n03 (browser +11/+13/+14);
# its first 10 min peak a median +17-19 C above the pre-start 2-min average.
CPU_OPEN_BELOW_C = float(os.environ.get("GATE_CPU_OPEN_BELOW_C", "88"))
CPU_HOT_C = float(os.environ.get("GATE_CPU_HOT_C", "96"))
MAX_CPU_PER_NODE = int(os.environ.get("GATE_MAX_CPU_PER_NODE", "2"))
# CI CPU requests per node (owner 2026-10-04: CI gets >= 6 CPU per node while
# the node is below the thermal limits; production leaves 6.4-7.2 of 17 free)
NODE_CPU_BUDGET = float(os.environ.get("GATE_NODE_CPU_BUDGET", "6"))
LANE = "ci.cberg.home/lane"
CPU_SUITES = {"sims", "unit"}
GPU_RES = "gpu.intel.com/i915"
# 300 s (trial 2026-10-04: 120 s let nuc14-02 take a 2nd shard before the 1st
# one's test load had started - clone + npm ci take 1-2 min - and the node then
# held a 94 C 2-min floor with 100 C peaks)
SETTLE_SECONDS = int(os.environ.get("GATE_SETTLE_SECONDS", "300"))
# Fixed path shared by every trigger on the Mac (they all run as mu). The file
# is mu-owned, 0644: flock needs no write access, so it is opened read-only and
# never followed through a symlink.
LOCK = "/tmp/ninth-banner-admit.lock"
PROM = "/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?"
TEMP = 'node_thermal_zone_temp{type="x86_pkg_temp"}'
JOIN = "* on(instance) group_left(nodename) node_uname_info"


def log(msg):
    print(f"  gate {time.strftime('%H:%M:%S')} {msg}", flush=True)


def kubectl(*args, stdin=None):
    r = subprocess.run(["mise", "exec", "--", "kubectl", *args], cwd=REPO_ROOT, input=stdin,
                       capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(f"kubectl {' '.join(args[:3])}: {r.stderr.strip()[:300]}")
    return r.stdout


def prom(query):
    out = kubectl("get", "--raw", PROM + urllib.parse.urlencode({"query": query}))
    res = json.loads(out)["data"]["result"]
    return {s["metric"]["nodename"]: float(s["value"][1]) for s in res if "nodename" in s["metric"]}


def node_temps():
    avg2 = prom(f"avg_over_time({TEMP}[2m]) {JOIN}")
    max3 = prom(f"max_over_time({TEMP}[3m]) {JOIN}")
    age = prom(f"(time() - timestamp({TEMP})) {JOIN}")
    # a node whose exporter stopped reporting is never open
    # non-finite readings (NaN compares False with every threshold) close the node too
    return {n: (avg2[n], max3.get(n, 999.0)) for n in avg2
            if age.get(n, 999.0) < 90 and math.isfinite(avg2[n]) and math.isfinite(max3.get(n, 999.0))}


def brake_until():
    """{node: epoch until which admission is braked} for nodes that read >= BRAKE_C recently."""
    last = prom(f"max_over_time(timestamp({TEMP} >= {BRAKE_C})[{BRAKE_MINUTES + 1}m:15s]) {JOIN}")
    return {n: t + 60 * BRAKE_MINUTES for n, t in last.items()}


def qty(v):
    """Kubernetes quantity -> float (cores for cpu, bytes for memory)."""
    v = str(v)
    for suf, mul in (("Ki", 2**10), ("Mi", 2**20), ("Gi", 2**30), ("Ti", 2**40),
                     ("m", 1e-3), ("k", 1e3), ("M", 1e6), ("G", 1e9)):
        if v.endswith(suf):
            return float(v[:-len(suf)]) * mul
    return float(v)


def pod_requests(p):
    """Effective pod requests {cpu, memory, gpu}: max(sum of containers, largest init)."""
    def of(cs):
        return [{k: qty(((c.get("resources") or {}).get("requests") or {}).get(r, 0))
                 for k, r in (("cpu", "cpu"), ("memory", "memory"), ("gpu", GPU_RES))} for c in cs]
    main_ = of(p["spec"].get("containers") or [])
    init = of(p["spec"].get("initContainers") or [])
    return {k: max(sum(c[k] for c in main_), max([c[k] for c in init] or [0])) for k in ("cpu", "memory", "gpu")}


def lane_of(p):
    lab = p["metadata"].get("labels") or {}
    if lab.get(LANE) in ("browser", "cpu"):
        return lab[LANE]
    return "cpu" if lab.get("ci.cberg.home/suite") in CPU_SUITES and not pod_requests(p)["gpu"] else "browser"


def node_free():
    """{node: {cpu, memory, gpu}} allocatable minus requests of every NON-CI pod
    that is Pending/Running on it (kube-state-metrics). CI pods are subtracted
    from the live pod list in snapshot(), which also sees pinned-not-yet-bound pods."""
    res = {"cpu": "cpu", "memory": "memory", "gpu": "gpu_intel_com_i915"}
    def by(q):
        out = json.loads(kubectl("get", "--raw", PROM + urllib.parse.urlencode({"query": q})))["data"]["result"]
        return {(s["metric"]["node"], s["metric"]["resource"]): float(s["value"][1]) for s in out}
    alloc = by('kube_node_status_allocatable{resource=~"cpu|memory|gpu_intel_com_i915"}')
    used = by('sum by (node, resource) (kube_pod_container_resource_requests{namespace!="%s",'
              'resource=~"cpu|memory|gpu_intel_com_i915"} * on(namespace, pod) group_left() '
              'max by (namespace, pod) (kube_pod_status_phase{phase=~"Pending|Running"} == 1))' % NS)
    nodes = {n for n, _ in alloc}
    return {n: {k: alloc[(n, r)] - used.get((n, r), 0.0) for k, r in res.items()}
            for n in nodes if (n, "cpu") in alloc and (n, "memory") in alloc and (n, "cpu") in used}


def ts(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()


def gated(p):
    return any(g.get("name") == GATE for g in p["spec"].get("schedulingGates") or [])


def snapshot():
    pods = json.loads(kubectl("get", "pods", "-n", NS, "-l", SELECTOR, "-o", "json"))["items"]
    live = [p for p in pods if p["status"].get("phase") in ("Pending", "Running")
            and not p["metadata"].get("deletionTimestamp")]
    count, last, queue, ci_req = {}, {}, [], {}
    for p in live:
        if gated(p):
            queue.append(p)
            continue
        node = p["spec"].get("nodeName") or (p["spec"].get("nodeSelector") or {}).get("kubernetes.io/hostname")
        if not node:
            continue   # an ungated pod the scheduler has not placed yet
        c = count.setdefault(node, {"browser": 0, "cpu": 0})
        c[lane_of(p)] += 1
        r, acc = pod_requests(p), ci_req.setdefault(node, {"cpu": 0.0, "memory": 0.0, "gpu": 0.0})
        for k in acc:
            acc[k] += r[k]
        t = (p["metadata"].get("annotations") or {}).get(RELEASED_AT) or p["status"].get("startTime")
        if t:
            last[node] = max(last.get(node, 0.0), ts(t))
    queue.sort(key=lambda p: (p["metadata"]["creationTimestamp"], p["metadata"]["name"]))
    return count, last, queue, ci_req


def global_hold(brake):
    return GLOBAL_BRAKE_NODES > 0 and len(brake) >= GLOBAL_BRAKE_NODES


def closed_reason(node, lane, req, temps, count, last, now, free, ci_req, brake):
    avg2, max3 = temps[node]
    if node in brake:
        return f"brake (read >= {BRAKE_C:.0f}C; {brake[node] - now:.0f}s more)"
    c = count.get(node, {"browser": 0, "cpu": 0})
    nb, nc = c["browser"], c["cpu"]
    if lane == "cpu":
        open_below, hot, tier = CPU_OPEN_BELOW_C, CPU_HOT_C, ", cpu lane"
    elif nb + nc == 0:
        open_below, hot, tier = OPEN_BELOW_C, HOT_C, ""
    else:
        open_below, hot, tier = SECOND_OPEN_BELOW_C, SECOND_HOT_C, ", 2nd-pod limit"
    if avg2 >= open_below:
        return f"warm (2m avg {avg2:.0f}C >= {open_below:.0f}{tier})"
    if max3 >= hot:
        return f"hot (3m peak {max3:.0f}C >= {hot:.0f}{tier})"
    if lane == "browser":
        if nb >= 1 and node not in SECOND_POD_NODES:
            return f"full ({nb}/1 browser pods; no 2nd browser pod on this node)"
        if nb >= MAX_PER_NODE:
            return f"full ({nb}/{MAX_PER_NODE} browser pods)"
    elif nc >= MAX_CPU_PER_NODE:
        return f"full ({nc}/{MAX_CPU_PER_NODE} cpu-lane pods)"
    used = ci_req.get(node, {"cpu": 0.0, "memory": 0.0, "gpu": 0.0})
    if used["cpu"] + req["cpu"] > NODE_CPU_BUDGET + 1e-6:
        return f"budget (CI CPU requests {used['cpu']:g}+{req['cpu']:g} > {NODE_CPU_BUDGET:g})"
    if node not in free:
        return "no capacity data (fail-closed)"
    short = [k for k in ("cpu", "memory", "gpu") if free[node][k] - used[k] < req[k] - 1e-6]
    if short:
        return f"no room ({', '.join(short)} requests do not fit next to production)"
    if now - last.get(node, 0.0) < SETTLE_SECONDS:
        return f"settling ({now - last[node]:.0f}s/{SETTLE_SECONDS}s since last CI start)"
    return ""


def release(p, node):
    sel = dict(p["spec"].get("nodeSelector") or {})
    rest = [g for g in p["spec"].get("schedulingGates") or [] if g.get("name") != GATE]
    patch = [
        # optimistic concurrency: refuse to act on a stale view of the pod
        {"op": "test", "path": "/metadata/resourceVersion", "value": p["metadata"]["resourceVersion"]},
        {"op": "replace", "path": "/spec/schedulingGates", "value": rest},
        {"op": "add", "path": "/metadata/annotations/" + RELEASED_AT.replace("/", "~1"),
         "value": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")},
    ]
    if node:
        sel["kubernetes.io/hostname"] = node
        patch.insert(1, {"op": "add", "path": "/spec/nodeSelector", "value": sel})
    if not (p["metadata"].get("annotations")):
        patch.insert(1, {"op": "add", "path": "/metadata/annotations", "value": {}})
    kubectl("patch", "pod", "-n", NS, p["metadata"]["name"], "--type=json", "-p", json.dumps(patch))


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "tick"
    fd = os.open(LOCK, os.O_RDONLY | os.O_CREAT | os.O_NOFOLLOW, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | (fcntl.LOCK_NB if mode == "tick" else 0))
    except BlockingIOError:
        return 0   # another trigger instance is admitting right now
    try:
        if mode == "--release-all":
            _, _, queue, _ = snapshot()
            for p in queue:
                release(p, None)
                log(f"ROLLBACK released {p['metadata']['name']} (unpinned)")
            return 0
        now = time.time()
        brake, free = {}, {}
        try:
            temps = node_temps()
            brake = {n: t for n, t in brake_until().items() if t > now}
            free = node_free()
        except Exception as e:
            log(f"no temperature/capacity data, nothing admitted (fail-closed): {e}")
            temps = {}
        count, last, queue, ci_req = snapshot()
        if mode == "--status":
            probe = {"browser": {"cpu": 2.0, "memory": 6.0 * 2**30, "gpu": 1.0},
                     "cpu": {"cpu": 1.0, "memory": 1.0 * 2**30, "gpu": 0.0}}
            for n in sorted(temps):
                c = count.get(n, {"browser": 0, "cpu": 0})
                u = ci_req.get(n, {"cpu": 0.0})
                state = "  ".join(f"{ln}: " + ("CLOSED " + r if r else "open") for ln in ("browser", "cpu")
                                  for r in [closed_reason(n, ln, probe[ln], temps, count, last, now, free, ci_req, brake)])
                print(f"{n}  2m-avg {temps[n][0]:5.1f}C  3m-peak {temps[n][1]:5.1f}C  "
                      f"browser {c['browser']}/{MAX_PER_NODE} cpu {c['cpu']}/{MAX_CPU_PER_NODE} "
                      f"ci-cpu {u['cpu']:g}/{NODE_CPU_BUDGET:g}\n    {state}")
            for n, t in sorted(brake.items()):
                print(f"BRAKE: {n} read >= {BRAKE_C:.0f}C; no admissions on {n} for {t - now:.0f}s more")
            if global_hold(brake):
                print(f"GLOBAL HOLD: {len(brake)} nodes braked (>= {GLOBAL_BRAKE_NODES}); "
                      f"no admissions anywhere for {min(brake.values()) - now:.0f}s more")
            print(f"gated (queued) pods: {len(queue)}")
            for p in queue:
                print(f"  {p['metadata']['name']}  {lane_of(p)}  since {p['metadata']['creationTimestamp']}")
            return 0
        if global_hold(brake):
            if queue:
                log(f"GLOBAL HOLD: {', '.join(sorted(brake))} read >= {BRAKE_C:.0f}C; "
                    f"{len(queue)} pod(s) held, no admissions anywhere for "
                    f"{min(brake.values()) - now:.0f}s more")
            return 0
        if brake and queue:
            log("BRAKE: " + ", ".join(f"{n} ({t - now:.0f}s more)" for n, t in sorted(brake.items()))
                + f" read >= {BRAKE_C:.0f}C; no admissions there, other nodes admit")
        used = set()
        for p in queue:
            if len(used) >= len(temps):
                break
            lane, req = lane_of(p), pod_requests(p)
            open_nodes = [n for n in temps if n not in used
                          and not closed_reason(n, lane, req, temps, count, last, now, free, ci_req, brake)]
            if not open_nodes:
                continue   # this lane is closed; a younger pod of the other lane may still fit
            # fewest CI pods first, then the coolest
            n = min(open_nodes, key=lambda n: (sum(count.get(n, {}).values()), temps[n][0]))
            try:
                release(p, n)
            except Exception as e:
                log(f"admit {p['metadata']['name']} -> {n} failed: {e}")
                continue
            c = count.setdefault(n, {"browser": 0, "cpu": 0})
            log(f"admitted {p['metadata']['name']} ({lane}) -> {n} (2m avg {temps[n][0]:.0f}C, "
                f"3m peak {temps[n][1]:.0f}C, {lane} pods {c[lane]}->{c[lane] + 1})")
            c[lane] += 1
            acc = ci_req.setdefault(n, {"cpu": 0.0, "memory": 0.0, "gpu": 0.0})
            for k in acc:
                acc[k] += req[k]
            last[n] = now
            used.add(n)
        return 0
    finally:
        os.close(fd)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:   # never break the trigger's poll loop
        log(f"tick error: {e}")
        sys.exit(0)
