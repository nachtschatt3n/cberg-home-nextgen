#!/usr/bin/env python3
"""
Regression test for F-ee2f51a2 (2026-09-26): health-check.sh could count a
flood but not say what caused it.

2026-09-24 ~20:25Z a switch reboot dropped the NIC carrier on all three nodes
in one 10-minute window; etcd lost its leader and one kube-apiserver wrote
~351k `watch chan error: etcdserver: no leader` lines in that window. The
report said only "kube-system 360k errors (93%)".

Pinned here, against the REAL functions extracted from health-check.sh:

  netstab_assess (Section 11a)
    * the 09-24 shape (3 nodes x4 carrier changes in one bucket, 1 etcd
      leader change in the same bucket) -> MAJOR link-drop + MINOR etcd
      attributed to it                                   (must FIRE)
    * the 09-23 clean window -> OK / OK, no issue           (must stay QUIET)
    * one node flapping alone -> MINOR, not MAJOR
    * two nodes in DIFFERENT buckets -> MINOR each, not MAJOR
    * a carrier change in the node's own boot bucket -> INFO (reboot), no issue
    * etcd 3/24h -> MINOR, 6/24h -> MAJOR, 1-2/24h uncorrelated -> INFO
    * no series / failed query -> UNMEASURED, never OK (silent-zero class)
    * titles carry backticked anchors so findings keep one row across cycles
  ns_attr_render (Section 34 attribution)
    * klog-prefixed etcd lines normalise to ONE message; busiest bucket named
    * empty / failed ES responses -> "attribution unavailable", never blank
    * backticks in a log line cannot leak into (and fork) the finding anchor
  wiring
    * the four namespace findings append ${NS_ATTR} and anchor the namespace
    * the Section 34 wildcard count query is UNCHANGED (the control is never
      narrowed): *error* / *fatal* should, *noerror* must_not, 24h, no ns filter

Fixture numbers are the ones measured live on 2026-09-26 by replaying
2026-09-24T21:00Z and 2026-09-23T21:00Z against Prometheus/ES.

Optional live replay (needs port-forwards):
  HC_LIVE_PROM_PORT=19090 python3 runbooks/tests/test-health-check-netstab-attribution.py

Run: python3 runbooks/tests/test-health-check-netstab-attribution.py
"""
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

HC = pathlib.Path(__file__).resolve().parents[1] / "health-check.sh"
SRC = HC.read_text()
PASS = FAIL = 0


def check(name, ok, detail=""):
    global PASS, FAIL
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"\n        {detail}"))
    if ok:
        PASS += 1
    else:
        FAIL += 1


def grab(name):
    i = SRC.index(f"{name}() {{")
    j = SRC.index("\n}\n", i) + 3
    return SRC[i:j]


FUNCS = "NETSTAB_NIC_RE='(en|eth|bond).*'\n" + "\n\n".join(
    grab(n) for n in ("prom_query_at", "prom_query_range", "netstab_collect",
                      "netstab_assess", "ns_attr_render"))


def ts(y, mo, d, h, mi=0):
    return int(datetime(y, mo, d, h, mi, tzinfo=timezone.utc).timestamp())


NODES = {"192.168.55.11:9100": "k8s-nuc14-01", "192.168.55.12:9100": "k8s-nuc14-02",
         "192.168.55.13:9100": "k8s-nuc14-03"}


def prom(result, status="success"):
    return json.dumps({"status": status, "data": {"resultType": "matrix", "result": result}})


def grid(end):
    return [end - 86400 + 600 + 600 * k for k in range(144)]


def carrier(end, events):
    """events: {instance: {bucket_ts: count}}"""
    return prom([{"metric": {"instance": inst},
                  "values": [[t, str(events.get(inst, {}).get(t, 0))] for t in grid(end)]}
                 for inst in NODES])


def scalar(v):
    return prom([] if v is None else [{"metric": {}, "value": [0, str(v)]}])


def assess(end, events, etcd24, etcd7, etcd_changes=(), boots=None,
           carrier_json=None):
    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d)
        (p / "carrier.json").write_text(carrier_json if carrier_json is not None
                                        else carrier(end, events))
        (p / "boot.json").write_text(prom([{"metric": {"instance": i},
                                            "value": [0, str((boots or {}).get(i, end - 30 * 86400))]}
                                           for i in NODES]))
        (p / "uname.json").write_text(prom([{"metric": {"instance": i, "nodename": n},
                                             "value": [0, "1"]} for i, n in NODES.items()]))
        (p / "etcd24h.json").write_text(scalar(etcd24))
        (p / "etcd7d.json").write_text(scalar(etcd7))
        (p / "etcdrange.json").write_text(prom([{"metric": {}, "values": [
            [t, "1.0526" if t in etcd_changes else "0"] for t in grid(end)]}]))
        r = subprocess.run(["bash", "-c", FUNCS + f'\nnetstab_assess "{d}"'],
                           capture_output=True, text=True)
    rows = [ln.split("\t", 2) for ln in r.stdout.splitlines() if ln.strip()]
    return rows, r.stderr


def levels(rows, check_name):
    return [lv for lv, c, _ in rows if c == check_name]


def msgs(rows, check_name):
    return " | ".join(m for _, c, m in rows if c == check_name)


print("test-health-check-netstab-attribution")

# ---------------------------------------------------------------- the incident
END = ts(2026, 9, 24, 21)
B = ts(2026, 9, 24, 20, 30)          # bucket (20:20, 20:30]
inc = {i: {B: 4.2105} for i in NODES}
rows, err = assess(END, inc, 1.0003, 2.0, etcd_changes={B})
check("09-24 replay: link-drop MAJOR (3 nodes, same 10-min window)",
      levels(rows, "link-drop") == ["MAJOR"] and "3 nodes" in msgs(rows, "link-drop")
      and "20:20Z-20:30Z" in msgs(rows, "link-drop"), f"{rows} {err}")
check("09-24 replay: names all three nodes",
      all(n in msgs(rows, "link-drop") for n in NODES.values()), msgs(rows, "link-drop"))
check("09-24 replay: etcd leader change fires, attributed to the link drop",
      levels(rows, "etcd-leader") == ["MINOR"] and "coincides with the multi-node link drop"
      in msgs(rows, "etcd-leader"), f"{rows}")
check("titles carry backticked anchors (stable finding identity)",
      "`node-nic-carrier`" in msgs(rows, "link-drop")
      and "`etcd-leader-changes`" in msgs(rows, "etcd-leader"), f"{rows}")

# ---------------------------------------------------------------- clean window
rows, err = assess(ts(2026, 9, 23, 21), {}, 0.0, 1.0)
check("09-23 clean replay: link-drop OK, etcd OK, nothing raised",
      levels(rows, "link-drop") == ["OK"] and levels(rows, "etcd-leader") == ["OK"], f"{rows} {err}")

# ---------------------------------------------------------------- shapes
rows, _ = assess(END, {"192.168.55.12:9100": {B: 2}}, 0.0, 1.0)
check("one node flapping alone -> MINOR naming that node, not MAJOR",
      levels(rows, "link-drop") == ["MINOR"] and "`k8s-nuc14-02`" in msgs(rows, "link-drop"), f"{rows}")
rows, _ = assess(END, {"192.168.55.11:9100": {B: 2}, "192.168.55.13:9100": {B - 7200: 2}}, 0.0, 1.0)
check("two nodes in DIFFERENT windows -> two MINORs, no MAJOR",
      levels(rows, "link-drop") == ["MINOR", "MINOR"], f"{rows}")
rows, _ = assess(END, {"192.168.55.11:9100": {B: 2}}, 0.0, 1.0,
                 boots={"192.168.55.11:9100": B - 120})
check("carrier change in the node's own boot bucket -> INFO (reboot), OK, no issue",
      "MINOR" not in levels(rows, "link-drop") and "MAJOR" not in levels(rows, "link-drop")
      and "INFO" in levels(rows, "link-drop"), f"{rows}")
rows, _ = assess(END, {"192.168.55.11:9100": {B: 2}, "192.168.55.12:9100": {B: 2}}, 0.0, 1.0,
                 boots={"192.168.55.11:9100": B - 120, "192.168.55.12:9100": B - 60})
check("rolling reboot of two nodes in one bucket is NOT a multi-node link drop",
      "MAJOR" not in levels(rows, "link-drop"), f"{rows}")

rows, _ = assess(END, {}, 3.0, 5.0, etcd_changes={B, B - 3600, B - 7200})
check("etcd 3 leader changes / 24h, no link drop -> MINOR", levels(rows, "etcd-leader") == ["MINOR"], f"{rows}")
rows, _ = assess(END, {}, 6.2, 8.0)
check("etcd 6 leader changes / 24h -> MAJOR", levels(rows, "etcd-leader") == ["MAJOR"], f"{rows}")
rows, _ = assess(END, {}, 1.0, 6.0, etcd_changes={B})
check("etcd 1 change / 24h, no link drop -> INFO (background ~6/7d), no issue",
      levels(rows, "etcd-leader") == ["INFO"], f"{rows}")

# ---------------------------------------------------------------- blind != green
rows, _ = assess(END, {}, None, None, carrier_json=prom([]))
check("no carrier series -> UNMEASURED, never OK",
      levels(rows, "link-drop") == ["UNMEASURED"], f"{rows}")
check("no etcd series -> UNMEASURED, never OK",
      levels(rows, "etcd-leader") == ["UNMEASURED"], f"{rows}")
rows, _ = assess(END, {}, 0.0, 0.0, carrier_json="")
check("failed Prometheus query (empty body) -> UNMEASURED",
      levels(rows, "link-drop") == ["UNMEASURED"], f"{rows}")


# ---------------------------------------------------------------- attribution
def render(hist, sample, total):
    with tempfile.TemporaryDirectory() as d:
        h, s = pathlib.Path(d) / "h.json", pathlib.Path(d) / "s.json"
        h.write_text(hist if isinstance(hist, str) else json.dumps(hist))
        s.write_text(sample if isinstance(sample, str) else json.dumps(sample))
        r = subprocess.run(["bash", "-c", FUNCS + f'\nns_attr_render "{h}" "{s}" {total}'],
                           capture_output=True, text=True)
    return r.stdout.strip()


def hits(texts):
    return {"hits": {"hits": [{"_source": {"body": {"text": t}}} for t in texts]}}


def hist(buckets):
    return {"aggregations": {"per10m": {"buckets": [
        {"key": k * 1000, "doc_count": c} for k, c in buckets]}}}


etcd = [f"E0924 20:26:{s:02d}.{s * 7919:06d}       1 watcher.go:336] watch chan error: etcdserver: no leader"
        for s in range(48)]
other = ['{"level":"warn","logger":"etcd-client","msg":"retrying of unary invoker failed"}'] * 2
out = render(hist([(ts(2026, 9, 24, 20, 20), 351632), (ts(2026, 9, 24, 20, 30), 227)]),
             hits(etcd + other), 360833)
check("klog-prefixed etcd lines collapse to one normalised message (~96%)",
      '"watcher.go:#] watch chan error: etcdserver: no leader" ~96%' in out, out)
check("busiest 10m window named with its share of the namespace",
      "busiest 10m: 2026-09-24 20:20-20:30Z 351632 (97% of the namespace)" in out, out)
check("empty ES responses -> 'attribution unavailable', never blank",
      render("", "", 0).startswith("attribution unavailable"), render("", "", 0))
check("ES error body -> 'attribution unavailable'",
      render({"error": "x"}, {"error": "x"}, 5).startswith("attribution unavailable"))
out = render(hist([(END, 5)]), hits(["error: `rm -rf` failed"] * 3), 5)
check("backticks in a log line cannot reach the finding anchor", "`" not in out, out)

# ---------------------------------------------------------------- wiring
lines = [ln for ln in SRC.splitlines() if re.search(r'add_(critical|major|minor)_issue ".*in namespace', ln)]
check("four namespace error-volume findings exist", len(lines) == 4, f"{len(lines)}")
check("every namespace finding appends ${NS_ATTR}", all(ln.rstrip().endswith('${NS_ATTR}"') for ln in lines),
      "\n".join(lines))
check("every namespace finding anchors `ns` + `error-log-volume`",
      all("\\`$NS_NAME\\` (\\`error-log-volume\\`)" in ln for ln in lines), "\n".join(lines))
m = re.search(r'ERROR_DATA=\$\(curl .*?\}\' 2>/dev/null', SRC, re.S)
q = m.group(0) if m else ""
check("Section 34 wildcard control query still present", bool(q))
check("control query NOT narrowed: *error*/*fatal* should, *noerror* must_not, now-24h, no ns filter",
      '"*error*"' in q and '"*fatal*"' in q and '"*noerror*"' in q and '"now-24h"' in q
      and "k8s.namespace.name\": " not in q.split('"aggs"')[0], q[:400])
check("Section 11a is wired and reads netstab_assess",
      'log_section "Section 11a: Node Link Stability & etcd Leadership"' in SRC
      and 'netstab_assess "$NETSTAB_TMP"' in SRC)
check("kubectl-log counters document the rotated-file blind spot",
      "ROTATED FILES ARE INVISIBLE HERE" in SRC)

# ---------------------------------------------------------------- live replay
port = os.environ.get("HC_LIVE_PROM_PORT")
if port:
    def live(end):
        with tempfile.TemporaryDirectory() as d:
            r = subprocess.run(["bash", "-c", FUNCS + f'\nPROM_AVAILABLE=true; PROM_PORT={port}\n'
                                f'netstab_collect {end} "{d}"; netstab_assess "{d}"'],
                               capture_output=True, text=True)
        return [ln.split("\t", 2) for ln in r.stdout.splitlines() if ln.strip()]
    rows = live(ts(2026, 9, 24, 21))
    check("LIVE 2026-09-24T21:00Z: link-drop MAJOR + etcd fires",
          levels(rows, "link-drop") == ["MAJOR"] and levels(rows, "etcd-leader") in (["MINOR"], ["MAJOR"]),
          f"{rows}")
    rows = live(ts(2026, 9, 23, 21))
    check("LIVE 2026-09-23T21:00Z: quiet", levels(rows, "link-drop") == ["OK"]
          and levels(rows, "etcd-leader") in (["OK"], ["INFO"]), f"{rows}")
else:
    print("  NOTE  live replay skipped (set HC_LIVE_PROM_PORT to a Prometheus port-forward)")

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
