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
* A tick admits gated pods OLDEST FIRST, at most one per node per tick. It pins
  the pod to a node (nodeSelector kubernetes.io/hostname) and removes the gate.
  A node is open only if all of these hold:
  - its package temperature, averaged over 2 min, is < OPEN_BELOW_C (first
    CI pod) or < SECOND_OPEN_BELOW_C (second pod: the node already has one);
  - its peak over the last 3 min is < HOT_C (first pod) or < SECOND_HOT_C
    (second pod);
  - it holds < MAX_PER_NODE CI pods (bound or pinned, not finished);
  - no CI pod was admitted or started there in the last SETTLE_SECONDS, so the
    previous pod's heat shows before another pod is added.
* BRAKE: if ANY node's package temperature reached >= BRAKE_C in the last
  BRAKE_MINUTES (+1 min, i.e. a 1-min max >= BRAKE_C), nothing is admitted
  ANYWHERE until BRAKE_MINUTES after that reading. Running pods are untouched.
* Fail-closed: no or stale Prometheus data means no node is open, and pods queue.
  Production pods are never touched: the tick only reads and patches pods in
  ci-runner. Running pods are never changed: the gate only decides where and
  when a NEW pod starts.
* Concurrency: every trigger instance runs ticks; a host-wide lock lets one
  run at a time (others skip), so two runs never fill the same free slot.
"""
import fcntl
import json
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
BRAKE_C = float(os.environ.get("GATE_BRAKE_C", "100"))
BRAKE_MINUTES = int(os.environ.get("GATE_BRAKE_MINUTES", "10"))
MAX_PER_NODE = int(os.environ.get("GATE_MAX_PER_NODE", "2"))
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
    return {n: (avg2[n], max3.get(n, 999.0)) for n in avg2 if age.get(n, 999.0) < 90}


def brake_until():
    """{node: epoch until which admission is braked} for nodes that read >= BRAKE_C recently."""
    last = prom(f"max_over_time(timestamp({TEMP} >= {BRAKE_C})[{BRAKE_MINUTES + 1}m:15s]) {JOIN}")
    return {n: t + 60 * BRAKE_MINUTES for n, t in last.items()}


def ts(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()


def gated(p):
    return any(g.get("name") == GATE for g in p["spec"].get("schedulingGates") or [])


def snapshot():
    pods = json.loads(kubectl("get", "pods", "-n", NS, "-l", SELECTOR, "-o", "json"))["items"]
    live = [p for p in pods if p["status"].get("phase") in ("Pending", "Running")
            and not p["metadata"].get("deletionTimestamp")]
    count, last, queue = {}, {}, []
    for p in live:
        if gated(p):
            queue.append(p)
            continue
        node = p["spec"].get("nodeName") or (p["spec"].get("nodeSelector") or {}).get("kubernetes.io/hostname")
        if not node:
            continue   # an ungated pod the scheduler has not placed yet
        count[node] = count.get(node, 0) + 1
        t = (p["metadata"].get("annotations") or {}).get(RELEASED_AT) or p["status"].get("startTime")
        if t:
            last[node] = max(last.get(node, 0.0), ts(t))
    queue.sort(key=lambda p: (p["metadata"]["creationTimestamp"], p["metadata"]["name"]))
    return count, last, queue


def closed_reason(node, temps, count, last, now):
    avg2, max3 = temps[node]
    n = count.get(node, 0)
    open_below, hot = (OPEN_BELOW_C, HOT_C) if n == 0 else (SECOND_OPEN_BELOW_C, SECOND_HOT_C)
    tier = "" if n == 0 else ", 2nd-pod limit"
    if avg2 >= open_below:
        return f"warm (2m avg {avg2:.0f}C >= {open_below:.0f}{tier})"
    if max3 >= hot:
        return f"hot (3m peak {max3:.0f}C >= {hot:.0f}{tier})"
    if n >= MAX_PER_NODE:
        return f"full ({count[node]}/{MAX_PER_NODE} CI pods)"
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
            _, _, queue = snapshot()
            for p in queue:
                release(p, None)
                log(f"ROLLBACK released {p['metadata']['name']} (unpinned)")
            return 0
        now = time.time()
        brake = {}
        try:
            temps = node_temps()
            brake = {n: t for n, t in brake_until().items() if t > now}
        except Exception as e:
            log(f"no temperature data, nothing admitted (fail-closed): {e}")
            temps = {}
        count, last, queue = snapshot()
        if mode == "--status":
            for n in sorted(temps):
                r = closed_reason(n, temps, count, last, now)
                print(f"{n}  2m-avg {temps[n][0]:5.1f}C  3m-peak {temps[n][1]:5.1f}C  "
                      f"ci {count.get(n, 0)}/{MAX_PER_NODE}  {'CLOSED ' + r if r else 'open'}")
            for n, t in sorted(brake.items()):
                print(f"BRAKE: {n} read >= {BRAKE_C:.0f}C; no admissions anywhere for {t - now:.0f}s more")
            print(f"gated (queued) pods: {len(queue)}")
            for p in queue:
                print(f"  {p['metadata']['name']}  since {p['metadata']['creationTimestamp']}")
            return 0
        if brake:
            if queue:
                n, t = max(brake.items(), key=lambda kv: kv[1])
                log(f"BRAKE: {n} read >= {BRAKE_C:.0f}C; {len(queue)} pod(s) held, "
                    f"no admissions for {t - now:.0f}s more")
            return 0
        used = set()
        for p in queue:
            open_nodes = [n for n in temps if n not in used and not closed_reason(n, temps, count, last, now)]
            if not open_nodes:
                break
            # fewest CI pods first, then the coolest
            n = min(open_nodes, key=lambda n: (count.get(n, 0), temps[n][0]))
            try:
                release(p, n)
            except Exception as e:
                log(f"admit {p['metadata']['name']} -> {n} failed: {e}")
                continue
            log(f"admitted {p['metadata']['name']} -> {n} (2m avg {temps[n][0]:.0f}C, "
                f"3m peak {temps[n][1]:.0f}C, CI pods {count.get(n, 0)}->{count.get(n, 0) + 1})")
            count[n] = count.get(n, 0) + 1
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
