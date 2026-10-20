#!/usr/bin/env python3
"""Admission helper for scripts/ninth-banner-test.sh (docs/sops/ci-runner.md).

Subcommands (all fail LOUD: non-zero exit and a message on stderr when the
kubectl data is unreadable -- an empty or failed read is never "plenty of CPU"):

  free                      free allocatable millicores over schedulable nodes
  table                     per-node allocatable / requested / free (CPU)
  podreq JOB_YAML           effective CPU request (millicores) of one Job pod
  decide --req M --par "4 2" --headroom CPU
                            exit 0 + "admit <par> <need> <free>" for the first
                            parallelism whose need fits, exit 10 + "queue <need>
                            <free>" (need of the smallest option) otherwise
  inflight SUBMITTER        name of a non-terminal sims Job labelled with this
                            submitter (empty output = none)

Free CPU = sum over schedulable nodes of (allocatable.cpu - sum of CPU requests
of non-terminal pods bound to the node), counted like the scheduler: per pod
max(sum(containers + restartable init), max(plain init)) + pod overhead.
Schedulable = Ready, not cordoned, no NoSchedule/NoExecute taint (the Job
template carries no tolerations).
"""
import json
import os
import shlex
import subprocess
import sys

EXIT_QUEUE = 10
SUBMITTER_LABEL = "ci.cberg.home/submitter"


class DataError(Exception):
    pass


def parse_cpu(q):
    """Kubernetes CPU quantity -> millicores (int). '500m', '2', '1.5', '250u'."""
    if isinstance(q, (int, float)):
        return int(round(q * 1000))
    if not isinstance(q, str) or not q.strip():
        raise DataError(f"unreadable CPU quantity {q!r}")
    s = q.strip()
    try:
        if s.endswith("n"):
            return int(round(float(s[:-1]) / 1_000_000))
        if s.endswith("u"):
            return int(round(float(s[:-1]) / 1000))
        if s.endswith("m"):
            return int(round(float(s[:-1])))
        return int(round(float(s) * 1000))
    except ValueError:
        raise DataError(f"unreadable CPU quantity {q!r}")


def _req(c):
    return parse_cpu(((c.get("resources") or {}).get("requests") or {}).get("cpu", "0"))


def pod_request(spec):
    """Effective CPU request (millicores) the scheduler uses for a pod spec."""
    run = sum(_req(c) for c in spec.get("containers") or [])
    side = 0      # restartable init containers (sidecars) run alongside
    peak = 0      # plain init containers run one at a time, before the sidecars
    for c in spec.get("initContainers") or []:
        if c.get("restartPolicy") == "Always":
            side += _req(c)
            peak = max(peak, side)
        else:
            peak = max(peak, side + _req(c))
    total = max(run + side, peak)
    total += parse_cpu(((spec.get("overhead") or {}).get("cpu", "0")))
    return total


def schedulable(node):
    spec = node.get("spec") or {}
    if spec.get("unschedulable"):
        return False
    for t in spec.get("taints") or []:
        if t.get("effect") in ("NoSchedule", "NoExecute"):
            return False
    for c in (node.get("status") or {}).get("conditions") or []:
        if c.get("type") == "Ready":
            return c.get("status") == "True"
    return False   # no Ready condition: do not count the node


def node_table(nodes_json, pods_json):
    """[(name, allocatable_m, requested_m, free_m)] for schedulable nodes."""
    nodes = (nodes_json or {}).get("items")
    pods = (pods_json or {}).get("items")
    if not nodes:
        raise DataError("node list is empty or unreadable")
    if not pods:
        raise DataError("pod list is empty or unreadable")
    requested = {}
    for p in pods:
        node = (p.get("spec") or {}).get("nodeName")
        phase = (p.get("status") or {}).get("phase")
        if not node or phase in ("Succeeded", "Failed"):
            continue
        requested[node] = requested.get(node, 0) + pod_request(p.get("spec") or {})
    rows = []
    for n in nodes:
        name = (n.get("metadata") or {}).get("name")
        if not name:
            raise DataError("node without a name")
        if not schedulable(n):
            continue
        alloc = ((n.get("status") or {}).get("allocatable") or {}).get("cpu")
        if alloc is None:
            raise DataError(f"node {name} has no allocatable.cpu")
        a = parse_cpu(alloc)
        r = requested.get(name, 0)
        rows.append((name, a, r, a - r))
    if not rows:
        raise DataError("no schedulable node found (all cordoned/tainted/NotReady?)")
    return rows


def free_milli(nodes_json, pods_json):
    return sum(max(f, 0) for _, _, _, f in node_table(nodes_json, pods_json))


def decide(free, req_m, pars, headroom_m):
    """First (largest-first) parallelism that fits -> ('admit', par, need);
    else ('queue', None, need_of_smallest)."""
    needs = [(p, p * req_m + headroom_m) for p in pars]
    for p, need in needs:
        if free >= need:
            return "admit", p, need
    return "queue", None, needs[-1][1]


def fmt_cpu(m):
    return f"{m / 1000:.3f}".rstrip("0").rstrip(".") or "0"


def job_in_flight(jobs_json, submitter):
    items = (jobs_json or {}).get("items")
    if items is None:
        raise DataError("job list unreadable")
    for j in items:
        labels = (j.get("metadata") or {}).get("labels") or {}
        if labels.get("ci.cberg.home/suite") != "sims" or labels.get(SUBMITTER_LABEL) != submitter:
            continue
        done = any(c.get("type") in ("Complete", "Failed", "SuccessCriteriaMet", "FailureTarget")
                   and c.get("status") == "True"
                   for c in (j.get("status") or {}).get("conditions") or [])
        if not done:
            return j["metadata"]["name"]
    return ""


def kubectl_json(*args):
    cmd = shlex.split(os.environ.get("TNB_KUBECTL", "mise exec -- kubectl")) + list(args) + ["-o", "json"]
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    try:
        out = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise DataError(f"kubectl failed: {e}")
    if out.returncode != 0:
        raise DataError(f"kubectl {' '.join(args)} exited {out.returncode}: {out.stderr.strip()[:200]}")
    try:
        return json.loads(out.stdout)
    except ValueError:
        raise DataError(f"kubectl {' '.join(args)} returned unparseable output")


def main(argv):
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2
    cmd, rest = argv[0], argv[1:]
    try:
        if cmd in ("free", "table", "decide"):
            nodes = kubectl_json("get", "nodes")
            pods = kubectl_json("get", "pods", "-A")
            rows = node_table(nodes, pods)
            if cmd == "table":
                print(f"{'node':<16}{'allocatable':>12}{'requested':>11}{'free':>8}   (CPU)")
                for n, a, r, f in rows:
                    print(f"{n:<16}{fmt_cpu(a):>12}{fmt_cpu(r):>11}{fmt_cpu(f):>8}")
                print(f"{'TOTAL':<16}{fmt_cpu(sum(x[1] for x in rows)):>12}"
                      f"{fmt_cpu(sum(x[2] for x in rows)):>11}{fmt_cpu(free_milli(nodes, pods)):>8}")
                return 0
            free = free_milli(nodes, pods)
            if cmd == "free":
                print(free)
                return 0
            req_m = int(rest[rest.index("--req") + 1])
            pars = [int(x) for x in rest[rest.index("--par") + 1].split()]
            headroom_m = parse_cpu(rest[rest.index("--headroom") + 1])
            verdict, par, need = decide(free, req_m, pars, headroom_m)
            if verdict == "admit":
                print(f"admit {par} {fmt_cpu(need)} {fmt_cpu(free)}")
                return 0
            print(f"queue {fmt_cpu(need)} {fmt_cpu(free)}")
            return EXIT_QUEUE
        if cmd == "podreq":
            import yaml
            doc = yaml.safe_load(open(rest[0]))
            m = pod_request(doc["spec"]["template"]["spec"])
            if m <= 0:
                raise DataError("rendered pod spec has no CPU request")
            print(m)
            return 0
        if cmd == "inflight":
            print(job_in_flight(kubectl_json("get", "jobs", "-n", "ci-runner"), rest[0]))
            return 0
    except (DataError, ValueError, IndexError, KeyError, OSError) as e:
        print(f"ninth-banner-capacity: FAIL ({type(e).__name__}): {e}", file=sys.stderr)
        return 3
    print(f"unknown subcommand {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
