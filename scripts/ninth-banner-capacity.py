#!/usr/bin/env python3
"""Admission helper for scripts/ninth-banner-test.sh (docs/sops/ci-runner.md).

Subcommands (all fail LOUD: non-zero exit and a message on stderr when the
kubectl data is unreadable -- an empty or failed read is never "plenty of CPU"):

  free                      free allocatable CPU millicores over schedulable nodes
  table                     per-node allocatable / requested / free (CPU + memory)
  podreq JOB_YAML           effective request of one Job pod as "<cpu_m>,<mem_bytes>"
                            (opaque to the trigger: it is passed back as --req)
  decide --req REQ --par "4 2" --headroom CPU [--mem-headroom MEM]
                            REQ is podreq's "<cpu_m>,<mem_bytes>" (a bare <cpu_m>
                            from an older trigger means memory 0). Exit 0 +
                            "admit <par> <need> <free>" for the first parallelism
                            that FITS, exit 10 + "queue <need> <free> (<reason>)"
                            (need of the smallest option) otherwise
  submitter SHA             resolved submitter label + source ("<value> <env|branch|sha>"):
                            env SUBMITTER, else the first remote branch of the Ninth
                            Banner checkout (TNB_GAME_REPO, default
                            /Users/mu/code/the-ninth-banner) containing SHA, else sha[:8]
  inflight SUBMITTER        name of a non-terminal sims Job labelled with this
                            submitter (empty output = none)

Per node free = allocatable - sum of requests of non-terminal pods bound to the
node, for CPU and memory, counted like the scheduler: per pod
max(sum(containers + restartable init), max(plain init)) + pod overhead.
Schedulable = Ready, not cordoned, no NoSchedule/NoExecute taint (the Job
template carries no tolerations).

FITS means all of:
  1. the `par` pods first-fit, one at a time, into the schedulable nodes' free
     CPU AND free memory, each node keeping `--headroom` CPU and `--mem-headroom`
     memory (default TNB_HEADROOM_MEM, else 2Gi) free AFTER placement. A pod
     cannot span nodes, so 3 nodes x 1.5 CPU free never admits one 2-CPU pod,
     even though the cluster-wide sum (4.5) would cover it;
  2. every ResourceQuota in the Job namespace (TNB_NAMESPACE, default ci-runner)
     still has room for `par` more pods and their CPU / memory requests
     (`pods`, `requests.cpu`/`cpu`, `requests.memory`/`memory`). No quota in
     the namespace = no quota limit; an unreadable quota list fails loud.
Not modelled: limits.* quotas, extended resources (iGPU), ephemeral storage,
and Pending pods not yet bound to a node.
"""
import json
import math
import os
import shlex
import subprocess
import sys

EXIT_QUEUE = 10
SUBMITTER_LABEL = "ci.cberg.home/submitter"
DEFAULT_MEM_HEADROOM = "2Gi"
DEFAULT_NAMESPACE = "ci-runner"


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


_MEM_SUFFIXES = (
    ("Ki", 1024), ("Mi", 1024 ** 2), ("Gi", 1024 ** 3), ("Ti", 1024 ** 4),
    ("Pi", 1024 ** 5), ("Ei", 1024 ** 6),
    ("k", 1000), ("M", 1000 ** 2), ("G", 1000 ** 3), ("T", 1000 ** 4),
    ("P", 1000 ** 5), ("E", 1000 ** 6), ("m", 0.001),
)


def parse_mem(q):
    """Kubernetes memory quantity -> bytes (int, rounded up). '6Gi', '512Mi', '1G', '129e6'."""
    if isinstance(q, (int, float)) and not isinstance(q, bool):
        return int(math.ceil(q))
    if not isinstance(q, str) or not q.strip():
        raise DataError(f"unreadable memory quantity {q!r}")
    s = q.strip()
    try:
        for suf, mul in _MEM_SUFFIXES:
            if s.endswith(suf):
                return int(math.ceil(float(s[:-len(suf)]) * mul))
        return int(math.ceil(float(s)))
    except ValueError:
        raise DataError(f"unreadable memory quantity {q!r}")


def parse_count(q):
    try:
        return int(str(q).strip())
    except ValueError:
        raise DataError(f"unreadable count {q!r}")


def _req(c, key="cpu", parse=parse_cpu):
    return parse(((c.get("resources") or {}).get("requests") or {}).get(key, "0"))


def pod_request(spec, key="cpu", parse=parse_cpu):
    """Effective request the scheduler uses for a pod spec (CPU millicores by
    default; key="memory", parse=parse_mem for bytes)."""
    run = sum(_req(c, key, parse) for c in spec.get("containers") or [])
    side = 0      # restartable init containers (sidecars) run alongside
    peak = 0      # plain init containers run one at a time, before the sidecars
    for c in spec.get("initContainers") or []:
        if c.get("restartPolicy") == "Always":
            side += _req(c, key, parse)
            peak = max(peak, side)
        else:
            peak = max(peak, side + _req(c, key, parse))
    total = max(run + side, peak)
    total += parse(((spec.get("overhead") or {}).get(key, "0")))
    return total


def pod_mem_request(spec):
    return pod_request(spec, "memory", parse_mem)


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


def node_capacity(nodes_json, pods_json):
    """[{name, cpu_alloc, cpu_req, cpu_free, mem_alloc, mem_req, mem_free}] for
    schedulable nodes (CPU in millicores, memory in bytes)."""
    nodes = (nodes_json or {}).get("items")
    pods = (pods_json or {}).get("items")
    if not nodes:
        raise DataError("node list is empty or unreadable")
    if not pods:
        raise DataError("pod list is empty or unreadable")
    cpu_used, mem_used = {}, {}
    for p in pods:
        spec = p.get("spec") or {}
        node = spec.get("nodeName")
        phase = (p.get("status") or {}).get("phase")
        if not node or phase in ("Succeeded", "Failed"):
            continue
        cpu_used[node] = cpu_used.get(node, 0) + pod_request(spec)
        mem_used[node] = mem_used.get(node, 0) + pod_mem_request(spec)
    rows = []
    for n in nodes:
        name = (n.get("metadata") or {}).get("name")
        if not name:
            raise DataError("node without a name")
        if not schedulable(n):
            continue
        alloc = (n.get("status") or {}).get("allocatable") or {}
        if alloc.get("cpu") is None:
            raise DataError(f"node {name} has no allocatable.cpu")
        if alloc.get("memory") is None:
            raise DataError(f"node {name} has no allocatable.memory")
        ca, ma = parse_cpu(alloc["cpu"]), parse_mem(alloc["memory"])
        cr, mr = cpu_used.get(name, 0), mem_used.get(name, 0)
        rows.append({"name": name, "cpu_alloc": ca, "cpu_req": cr, "cpu_free": ca - cr,
                     "mem_alloc": ma, "mem_req": mr, "mem_free": ma - mr})
    if not rows:
        raise DataError("no schedulable node found (all cordoned/tainted/NotReady?)")
    return rows


def node_table(nodes_json, pods_json):
    """[(name, allocatable_m, requested_m, free_m)] (CPU) for schedulable nodes."""
    return [(r["name"], r["cpu_alloc"], r["cpu_req"], r["cpu_free"])
            for r in node_capacity(nodes_json, pods_json)]


def free_milli(nodes_json, pods_json):
    return sum(max(f, 0) for _, _, _, f in node_table(nodes_json, pods_json))


def first_fit(rows, par, cpu_m, mem_b, cpu_head_m=0, mem_head_b=0):
    """Place `par` identical pods first-fit into the nodes' free CPU and memory,
    each node keeping the headroom free. -> list of node names, or None."""
    room = [[r["name"], r["cpu_free"] - cpu_head_m, r["mem_free"] - mem_head_b] for r in rows]
    placed = []
    for _ in range(par):
        for slot in room:
            if slot[1] >= cpu_m and slot[2] >= mem_b:
                slot[1] -= cpu_m
                slot[2] -= mem_b
                placed.append(slot[0])
                break
        else:
            return None
    return placed


def quota_shortfall(quotas_json, par, cpu_m, mem_b):
    """None if every ResourceQuota has room for `par` more pods, else a reason."""
    items = (quotas_json or {}).get("items") if isinstance(quotas_json, dict) else None
    if items is None:
        raise DataError("resourcequota list unreadable")
    for q in items:
        name = (q.get("metadata") or {}).get("name", "?")
        st = q.get("status") or {}
        hard, used = st.get("hard"), st.get("used")
        if hard is None or used is None:
            raise DataError(f"quota {name} has no status.hard/status.used (not computed yet?)")
        for key, hv in hard.items():
            if key == "pods":
                parse, ask, fmt = parse_count, par, str
            elif key in ("requests.cpu", "cpu"):
                parse, ask, fmt = parse_cpu, par * cpu_m, fmt_cpu
            elif key in ("requests.memory", "memory"):
                parse, ask, fmt = parse_mem, par * mem_b, fmt_mem
            else:
                continue
            if key not in used:
                raise DataError(f"quota {name} reports no usage for {key}")
            h, u = parse(hv), parse(used[key])
            if u + ask > h:
                return f"quota {name} {key}: used {fmt(u)} + {fmt(ask)} > hard {fmt(h)}"
    return None


def decide(rows, req, pars, headroom_m, mem_headroom_b=0, quotas=None):
    """First (largest-first) parallelism that fits on the nodes AND in the
    quota -> ('admit', par, need_cpu_m, ''); else ('queue', None,
    need_cpu_of_smallest, reason). `req` is (cpu_m, mem_b); `quotas` is the
    kubectl resourcequota list (None = not checked)."""
    cpu_m, mem_b = req
    reason = ""
    for p in pars:
        need = p * cpu_m
        if first_fit(rows, p, cpu_m, mem_b, headroom_m, mem_headroom_b) is None:
            room = ", ".join(f"{r['name']} {fmt_cpu(r['cpu_free'] - headroom_m)}/"
                             f"{fmt_mem(r['mem_free'] - mem_headroom_b)}" for r in rows)
            reason = (f"{p} x {fmt_cpu(cpu_m)} CPU/{fmt_mem(mem_b)} do not fit the nodes keeping "
                      f"{fmt_cpu(headroom_m)} CPU/{fmt_mem(mem_headroom_b)} headroom each; "
                      f"room after headroom: {room}")
            continue
        if quotas is not None:
            short = quota_shortfall(quotas, p, cpu_m, mem_b)
            if short:
                reason = f"{p} pod(s) exceed the namespace quota: {short}"
                continue
        return "admit", p, need, ""
    return "queue", None, pars[-1] * cpu_m, reason


def parse_req_token(tok):
    """podreq output "<cpu_m>,<mem_bytes>" -> (cpu_m, mem_b); bare "<cpu_m>" -> mem 0."""
    parts = str(tok).strip().split(",")
    if len(parts) > 2 or not parts[0]:
        raise DataError(f"unreadable --req {tok!r}")
    try:
        cpu = int(parts[0])
        mem = int(parts[1]) if len(parts) == 2 else 0
    except ValueError:
        raise DataError(f"unreadable --req {tok!r}")
    if cpu <= 0 or mem < 0:
        raise DataError(f"unreadable --req {tok!r}")
    return cpu, mem


def fmt_cpu(m):
    return f"{m / 1000:.3f}".rstrip("0").rstrip(".") or "0"


def fmt_mem(b):
    return f"{b / 1024 ** 3:.2f}".rstrip("0").rstrip(".") + "Gi"


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


def sanitize_label(v):
    """Label value: [a-z0-9._-], alnum at both ends, <= 63 chars; '' if nothing is left."""
    out = "".join(ch if (ch.isalnum() and ch.isascii()) or ch in "._-" else "-" for ch in (v or "").lower())
    out = out[:63]
    return out.strip("-_.")


def resolve_submitter(sha, env=None, game_repo=None, run=subprocess.run):
    """-> (value, source). Never the cberg repo's own branch (the trigger always
    runs on main there, which would serialize every agent's sims)."""
    env = os.environ if env is None else env
    v = sanitize_label(env.get("SUBMITTER", ""))
    if v:
        return v, "env"
    repo = game_repo or env.get("TNB_GAME_REPO", "/Users/mu/code/the-ninth-banner")
    try:
        out = run(["git", "-C", repo, "branch", "-r", "--contains", sha],
                  capture_output=True, text=True, timeout=30)
        if out.returncode == 0:
            for line in out.stdout.splitlines():
                b = line.strip()
                if not b or "->" in b:      # HEAD pointer
                    continue
                if b.startswith("origin/"):
                    b = b[len("origin/"):]
                v = sanitize_label(b)
                if v:
                    return v, "branch"
    except (OSError, subprocess.TimeoutExpired):
        pass
    return sanitize_label(sha[:8]) or "unknown", "sha"


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


def _opt(rest, flag, default=None):
    if flag in rest:
        return rest[rest.index(flag) + 1]
    if default is None:
        raise DataError(f"missing {flag}")
    return default


def main(argv):
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2
    cmd, rest = argv[0], argv[1:]
    try:
        if cmd in ("free", "table", "decide"):
            nodes = kubectl_json("get", "nodes")
            pods = kubectl_json("get", "pods", "-A")
            rows = node_capacity(nodes, pods)
            free = free_milli(nodes, pods)
            if cmd == "table":
                print(f"{'node':<16}{'allocatable':>12}{'requested':>11}{'free':>8}   (CPU)"
                      f"{'allocatable':>14}{'requested':>11}{'free':>9}   (memory)")
                for r in rows:
                    print(f"{r['name']:<16}{fmt_cpu(r['cpu_alloc']):>12}{fmt_cpu(r['cpu_req']):>11}"
                          f"{fmt_cpu(r['cpu_free']):>8}        {fmt_mem(r['mem_alloc']):>14}"
                          f"{fmt_mem(r['mem_req']):>11}{fmt_mem(r['mem_free']):>9}")
                print(f"{'TOTAL':<16}{fmt_cpu(sum(r['cpu_alloc'] for r in rows)):>12}"
                      f"{fmt_cpu(sum(r['cpu_req'] for r in rows)):>11}{fmt_cpu(free):>8}        "
                      f"{fmt_mem(sum(r['mem_alloc'] for r in rows)):>14}"
                      f"{fmt_mem(sum(r['mem_req'] for r in rows)):>11}"
                      f"{fmt_mem(sum(max(r['mem_free'], 0) for r in rows)):>9}")
                return 0
            if cmd == "free":
                print(free)
                return 0
            req = parse_req_token(_opt(rest, "--req"))
            pars = [int(x) for x in _opt(rest, "--par").split()]
            if not pars:
                raise DataError("empty --par")
            headroom_m = parse_cpu(_opt(rest, "--headroom"))
            mem_head_b = parse_mem(_opt(rest, "--mem-headroom",
                                        os.environ.get("TNB_HEADROOM_MEM") or DEFAULT_MEM_HEADROOM))
            ns = os.environ.get("TNB_NAMESPACE") or DEFAULT_NAMESPACE
            quotas = kubectl_json("get", "resourcequota", "-n", ns)
            verdict, par, need, reason = decide(rows, req, pars, headroom_m, mem_head_b, quotas)
            if verdict == "admit":
                print(f"admit {par} {fmt_cpu(need)} {fmt_cpu(free)}")
                return 0
            print(f"queue {fmt_cpu(need)} {fmt_cpu(free)} ({reason})")
            return EXIT_QUEUE
        if cmd == "podreq":
            import yaml
            doc = yaml.safe_load(open(rest[0]))
            spec = doc["spec"]["template"]["spec"]
            m = pod_request(spec)
            if m <= 0:
                raise DataError("rendered pod spec has no CPU request")
            b = pod_mem_request(spec)
            if b <= 0:
                raise DataError("rendered pod spec has no memory request")
            print(f"{m},{b}")
            return 0
        if cmd == "submitter":
            v, src = resolve_submitter(rest[0])
            print(v, src)
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
