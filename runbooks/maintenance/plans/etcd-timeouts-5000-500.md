---
plan_id: etcd-timeouts-5000-500
component: talos-etcd
pr: null                              # no Renovate PR: operator-requested control-plane tuning (chat 2026-10-13)
kind: infra
current: "etcd defaults on all 3 members: --election-timeout=1000 --heartbeat-interval=100 (neither flag is set; running cmdline checked live 2026-10-13)"
target: "--election-timeout=5000 --heartbeat-interval=500 on all 3 members via cluster.etcd.extraArgs in kubernetes/bootstrap/talos/patches/controller/cluster.yaml"
update_type: refactor
risk: medium                          # Not low: it restarts the etcd service on every control-plane node (3 of 3, one at a
                                      # time, quorum 2/3 held at every step), the SOP base-rate rule (>= 6 leader changes/24h =
                                      # NO-GO) was tripped on 2026-10-12, and a wrong value costs the API server. Not high: no
                                      # node reboot, no data migration, the flag is not stored in the WAL or DB (rollback is a
                                      # config re-apply + service restart), and it is mechanically reversible per node.
est_duration_min: 110                 # setup+premises+gates 15 · freeze 3 · snapshot 3 · render+dry-run 5 · 2 followers x (apply 1
                                      # + restart/verify 4 + 10 min settle + gate 2) = 34 · leader (forfeit + apply + restart +
                                      # settle) 20 · commit/push + IUA resume + final soak 12 · slack 18. DOES NOT fit sat-attended
                                      # (70 schedulable) or nightly (70): Sunday (180) or an on-demand NOW run only.
needs_reboot: false                   # a service restart, NOT a node reboot - see section 1.2 (the dry-run says "without a reboot"
                                      # and that is true, but it does NOT mean etcd picks the flags up)
touches:
  namespaces:
    - kube-system                     # apiserver/controller-manager/scheduler lose or stall their local etcd for seconds per node
    - flux-system                     # push freeze: ImageUpdateAutomations suspended for the window (resumed at the end)
    - monitoring                      # READ-ONLY: every gate reads Prometheus
  resources:
    - talos-machineconfig/k8s-nuc14-01
    - talos-machineconfig/k8s-nuc14-02
    - talos-machineconfig/k8s-nuc14-03
    - "talos-service/etcd on 192.168.55.11, .12, .13 (restarted one at a time; followers first, leader last after forfeit-leadership)"
    - file/kubernetes/bootstrap/talos/patches/controller/cluster.yaml
    - "imageupdateautomation (only the rows with spec.suspend false/unset; suspended then resumed)"
  shared:
    - etcd                            # the single cluster datastore: quorum 2 of 3 is the only margin during each restart
    - kube-apiserver                  # each apiserver talks to its LOCAL etcd (127.0.0.1:2379) only
    - control-plane-vip               # 192.168.55.10 is elected through etcd; held by .13 on 2026-10-13; kubectl uses it
    - talos-machineconfig
    - monitoring                      # the gates' instrument (Prometheus is reached through the same apiserver VIP)
depends_on: []
conflicts_with:
  - envoy-proxy-config-distroless-v1.39.4   # reciprocal, added 2026-10-26 (sweep a1721200 plan review)
  # 2026-10-25: pruned dead refs kube-prometheus-stack-92.2.0, nocodb-2026.09.1, nextcloud-fleet-35.0.1, jellyfin-12.2.20261005 (executed/retired)
  - talos-linux-1.14.2                # exclusive node roll (11-01): reboots every node and restarts etcd three times; also
                                      # rewrites the same machine configs. Never the same night, and 11-08 is 7 days later on
                                      # purpose so the roll's own pre-gates (no unexplained leader change in 2 h) are not
                                      # confounded. NEEDS the reciprocal entry in that plan.
  - talos-power-tuning-ab             # talosctl apply-config on the same 3 nodes (live SysfsConfig A/B); a config apply from
                                      # two plans in one slot makes "the config on the node" ambiguous
  - multus-macvlan-foundation         # reference plan, also talosctl apply-config on the same nodes
  - longhorn-1.13.0                   # exclusive storage-engine upgrade (11-15): its gates also read etcd health; one risky
                                      # change per window
  - n8n-2.39.8                        # backup-restore stacking rule
  - paperless-db-13.0.2               # backup-restore stacking rule
exclusive: false                      # not exclusive: nothing structural forbids a no-risk co-tenant, but see nocodb above
security_ref: null
capability_change: true               # TRUE: node-loss failover goes from ~1-2 s to ~5-10 s (randomised election timeout 5-10 s),
                                      # i.e. a behaviour change for every workload that rides etcd, accepted by the operator
                                      # in exchange for far fewer spurious elections. Never unattended.
rollback_class: backup-restore        # the flag is not persisted in etcd data, so the rollback is a config re-apply + service
                                      # restart (mechanically a revert). It is declared backup-restore, not git-revert, because
                                      # Flux does NOT reconcile kubernetes/bootstrap/talos/: a git revert alone changes nothing
                                      # on the nodes. The last-resort restore path is the etcd snapshot taken in 2.4.
restore_proof: "2.5: the pre-rendered rollback config ($W/r-head, rendered from HEAD before the edit) dry-runs against every node to 'No changes.' - proof it is byte-equivalent to the live pre-change config - and etcdargs.py absent passes on all three nodes before any forward apply."
backup_gate: "2.4: talosctl etcd snapshot from the leader to $W, mode 600, size within 50 percent of the largest DB SIZE shown by etcd status (a 0-byte or few-KB file is a FAIL), plus the 2.5 empty-diff proof of the rollback config. Both must PASS before the first apply-config."
finding_refs:
  - F-f5879ed8                        # "etcd leader churn 2026-10-12 19:39-23:45Z (23 elections) tracks ARC CI build load" - NOTE:
                                      # that finding's own action is a CI CPU cap; THIS plan is the operator-requested etcd-side
                                      # remedy and does not remove the CI cause. Close only after the post-window soak (4.6).
  - F-27a3f024                        # "etcd leader changes: 23 in 24h" (the sweep's measurement of the same event)
review: ready-for-go@2026-10-13   # plan-reviewer 2026-10-13 (2nd pass): ready-for-go, 0 blocking; vetted at operator request (AskUserQuestion 2026-10-13)
status: vetted
window: "sun-attended:2026-11-08"   # OPERATOR-CHOSEN 2026-10-13 (AskUserQuestion). nocodb-2026.09.1 moved off this slot (risk-class stacking). 110 of 180 min; 7 days after the talos roll (11-01) on purpose, 7 days before longhorn-1.13.0 (11-15). HUMAN-GATED: needs a fresh operator GO recorded for this dated slot.
premises:
  - id: nodes-on-talos-1.14
    why: "All dry-runs and the apply-config no-reboot verdict were measured on v1.14.1 (etcd 3.7.1 service, args computed in the Talos etcd service PreFunc). A different minor invalidates the verdict in section 1.2."
    run: kubectl get nodes -o jsonpath='{.items[*].status.nodeInfo.osImage}'
    expect_matches: '^Talos \(v1\.14\.[0-9]+\) Talos \(v1\.14\.[0-9]+\) Talos \(v1\.14\.[0-9]+\)$'
  - id: timeout-flags-not-yet-in-etcdspec
    why: "Idempotence guard on the resource side (the premise allowlist is get-only; the RUNNING-process check is etcdargs.py absent in 2.5). Non-zero means the change (or a partial run) already happened - re-plan, do not re-apply blind."
    run: "talosctl --nodes=192.168.55.11,192.168.55.12,192.168.55.13 get etcdspec -o yaml | grep -c -i -e election-timeout"
    expect_exact: "0"
  - id: patch-not-yet-edited
    why: "The repo patch must not already carry the flags, or section 3.1's anchored edit is a no-op/duplicate."
    run: "grep -c 'election-timeout' kubernetes/bootstrap/talos/patches/controller/cluster.yaml"
    expect_exact: "0"
  - id: patch-anchor-present
    why: "Section 3.1 inserts the two keys directly after this exact line; exactly one occurrence is required."
    run: "grep -c 'listen-metrics-urls: http://0.0.0.0:2381' kubernetes/bootstrap/talos/patches/controller/cluster.yaml"
    expect_exact: "1"
  - id: talos-dir-clean
    why: "git commit --only in section 3.8 must commit exactly one file; any other uncommitted change under kubernetes/bootstrap/talos (a concurrent talos plan, e.g. a SysfsConfig edit) would be rendered into the node configs by talhelper genconfig and applied with this change."
    run: "git status --porcelain kubernetes/bootstrap/talos | wc -l | tr -d ' '"
    expect_exact: "0"
  - id: prometheus-sees-three-etcd-members
    why: "Every gate reads etcd_server_has_leader from Prometheus; count(...) must return 3 (fewer = scrape gap, and an empty result would look like a pass)."
    run: "kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=count(etcd_server_has_leader)' | grep -c -E '\"value\":\\[[0-9.]+,\"3\"\\]'"
    expect_exact: "1"
sops_refs:
  - docs/sops/etcd.md
  - docs/sops/talos-upgrade.md
  - docs/sops/maintenance-windows.md
  - docs/sops/application-update.md
generated: "2026-10-13"
---

# etcd election-timeout 1000 -> 5000 ms, heartbeat-interval 100 -> 500 ms (3 control-plane nodes)

## 1. Summary & why held

### 1.1 What changes and why

Two etcd flags are added to `cluster.etcd.extraArgs` in the controller patch
(`kubernetes/bootstrap/talos/patches/controller/cluster.yaml`, rendered into all three
`kubernetes-k8s-nuc14-0N.yaml`), then applied node by node:

```yaml
  etcd:
    extraArgs:
      listen-metrics-urls: http://0.0.0.0:2381
      election-timeout: "5000"        # NEW
      heartbeat-interval: "500"       # NEW
```

**Why (operator request, re-verified live 2026-10-13):** on 2026-10-12 19:39-23:45Z etcd had
23 leader changes (the 7 days before: background of a handful, 0/day on 10-06..10-11). The
cluster's three members share one consumer NVMe each with Longhorn and container images, so
CI bursts (ARC runners on all three nodes after `faa3ec55` re-added nuc14-02) produce disk and
CPU stalls that outlast a 1 s election timeout. Measured: WAL fsync p99 baseline 21-30 ms (live
1 h window 2026-10-13: 30.2 / 22.7 / 21.5 ms), backend commit p99 15-52 ms, peer RTT p99 about
6 ms (peak 12.6 ms) - the network is not the problem; the election timeout is simply 1-2
orders of magnitude tighter than the stall the disks and CPUs produce under CI load.
(F-f5879ed8 measured the fsync p99 as flat at 20-30 ms in 30-minute buckets and attributes the
churn to CPU load from CI; a finer-grained query shows short WAL-fsync spikes up to about 1 s on
nuc14-02. Either way the remedy here - a more tolerant election timeout - applies. It is NOT a
root-cause fix: the CI placement/CPU question in F-f5879ed8 stays open.)

**Why it is held (not auto-applied):** no Renovate PR exists and this is a Talos machine-config
change on the only control plane (`capability_change: true`, the failover trade-off below). It
is therefore HUMAN-GATED, attended, and per `docs/sops/etcd.md` the base-rate rule (>= 6 leader
changes in 24 h with no reboots = "already unstable", planned disruptions NO-GO) applies: the
2026-10-12 count tripped it. The change IS the remedy for that instability, so the rule is
reconciled explicitly in 2.2 (it only applies if the window day itself shows >= 6, and then the
operator must acknowledge it by name).

### 1.2 Primary-source findings (what the window agent must not re-derive)

1. **Validity.** etcd 3.7 `embed/config.go` (`Validate`): `--election-timeout` must be at least
   5x `--heartbeat-interval` (`5*TickMs > ElectionMs` is an error) and at most `maxElectionMs =
   50000`. 5000/500 is 10x and 10 percent of the maximum: valid. Defaults are `TickMs: 100,
   ElectionMs: 1000`. Neither flag is on Talos's etcd deny-list (`argsForControlPlane` in
   `internal/app/machined/pkg/system/services/etcd.go`: name, data-dir, listen-*, TLS, feature
   gates, watch-progress only), so extraArgs are passed through - the live
   `--listen-metrics-urls=http://0.0.0.0:2381` is the same mechanism and is visible on the
   running cmdline today.
2. **`apply-config` does NOT make etcd pick the flags up.** Measured on v1.14.1:
   `talosctl apply-config --dry-run --mode=no-reboot` against the real nodes with the new
   config prints exactly the two added lines and `Applied configuration without a reboot`. That
   phrase means *no node reboot*. The etcd service computes its argument list once, in
   `Etcd.PreFunc`, from the `EtcdSpec` resource (`talosctl get etcdspec -o yaml` today shows
   `extraArgs: listen-metrics-urls` only); the container restart wrapper restarts the container
   with the SAME args, and the running cmdline today carries neither flag
   (`talosctl -n <ip> processes`). So the sequence per node is: apply-config (updates the
   resource, no reboot) -> **`talosctl -n <ip> service etcd restart`** (re-runs `PreFunc`, new
   args) -> verify the *running* cmdline. `needs_reboot: false` is correct; "applied" is not
   "effective". Gate `etcdargs.py` exists to catch exactly that gap.
3. **Quorum math.** A 3-member cluster tolerates one member down. Restarting one etcd at a time
   keeps 2/3 voting at every moment; restarting two at once, or one while another is unhealthy,
   loses quorum. Each member's election timeout is local (it is not negotiated between members
   and is not stored in the WAL/DB), so a mixed 1000/5000 cluster is legal during the roll.
4. **Mixed-config hazard and why the order is followers first, leader last.** A follower
   re-arms a randomised election timer of 1x-2x its election timeout on every heartbeat. While
   the leader still runs 100 ms heartbeats, a restarted new-config follower (5-10 s timer) is
   strictly more patient: safe. Once a *new-config* member leads (500 ms heartbeats), an
   *old-config* follower (1-2 s timer) has only about 1 s of margin between heartbeats: workable
   on a quiet node, thin under a stall. Leader-last with `forfeit-leadership` keeps that
   exposure to one member for about a minute (3.6). The alternative (plain restart of the old
   leader) removes the thin margin but opens a leaderless gap of 5-10 s on the two new-config
   members; 3.6 documents the fallback and its allowance.
5. **Trade-off the operator accepted.** Real node/leader loss now takes up to ~10 s (randomised
   5-10 s timer) to elect a successor instead of ~1-2 s. During that gap the datastore is
   write-unavailable. kube-controller-manager / kube-scheduler use the upstream 15 s lease
   (live `leaseDurationSeconds: 15` on the kube-controller-manager Lease; the 10 s renew-deadline
   is the upstream default and is UNVERIFIED here - the static pod command only sets
   `--leader-elect=true`), so the worst case sits at their renew deadline and *can* cost a
   controller leader transition. Correction (verified live 2026-10-13): Flux controllers run
   `--enable-leader-election` with a 35 s lease (`kustomize-controller-leader-election`
   `leaseDurationSeconds: 35`), i.e. they ride out a 10 s gap; the earlier "15 s Flux lease" claim
   was wrong. Impact is therefore on the kube-system controllers only (`kube-system` leases show `leaseTransitions` 45 / 37
   today); the plan records those counters (3.0) so any change attributable to the window is
   reported, not hidden.
6. **What this does NOT change.** The fsync/commit latency itself (disk contention, the
   `docs/sops/etcd.md` section 4.5 root cause) is unchanged; only the tolerance to it grows.
   Expect `etcd_disk_wal_fsync_duration_seconds` to look the same afterwards and
   `etcd_server_leader_changes_seen_total` to stop climbing under CI load.
   `etcd_server_heartbeat_send_failures_total` will drop *by definition* (a send is counted as
   failed when it takes longer than 2 x the heartbeat interval: 200 ms -> 1 s) and must not be
   used on its own as evidence of improvement (4.5).
7. **Defrag is deliberately NOT in this plan.** IN USE is about 32 percent of DB SIZE
   (`etcd status` 2026-10-13: 135-150 MB in use of 449-464 MB), under the 50 percent trigger of
   `docs/sops/etcd.md` 4.3. Defrag is the heaviest self-inflicted write burst; with the OLD
   1 s timeout a leader defrag can itself cause an election. Run it in a LATER window, after the
   new timeouts have soaked: one risky change per window.

## 2. Pre-checks

Shell: zsh on the Mac mini. Every Bash call re-exports the two environment lines in 2.1 (shell
state does not persist). Do not source the sweep DSN in the same call as a `git commit`
(a sourced DSN breaks the pre-commit gate).

### 2.0 Working directory and scripts

```bash
W=/private/tmp/etcd-timeouts-5000-500; mkdir -p "$W" && chmod 700 "$W"; cd /Users/mu/code/cberg-home-nextgen
cat > "$W/etcdstat.py" <<'PY'
import json, subprocess, sys
# converged                    -> 3 members, ONE leader, no learner, empty ERRORS, one common RAFT TERM, raft index spread/apply lag <= 50
# snap <file>                  -> converged + record {term, leader_ip} to <file>
# terms <file> <allowed>       -> converged + (RAFT TERM now - recorded term) <= <allowed>   (an election is a term bump; the term is
#                                 PERSISTED in the WAL, so unlike Prometheus counters it survives the etcd restarts of this plan)
# leader                       -> print only the leader's node IP (for ordering)
U = {"B": 1e-6, "kB": 1e-3, "KB": 1e-3, "MB": 1, "GB": 1e3}
IPS = "192.168.55.11,192.168.55.12,192.168.55.13"
out = subprocess.check_output(["talosctl", "-n", IPS, "etcd", "status"], text=True)
rows = [l.split() for l in out.splitlines()[1:] if l.strip()]
m, fail = {}, []
for t in rows:
    ip = t[0]
    m[ip] = dict(member=t[1], db=float(t[2]) * U[t[3]], use=float(t[4]) * U[t[5]], leader=t[7],
                 raft=int(t[8]), term=int(t[9]), applied=int(t[10]), learner=t[11], proto=t[12], err=" ".join(t[14:]))
mode = sys.argv[1] if len(sys.argv) > 1 else "converged"
if mode == "leader":
    lid = {v["leader"] for v in m.values()}
    if len(m) != 3 or len(lid) != 1: sys.exit("FAIL: cannot determine ONE leader from 3 members")
    print([ip for ip, v in m.items() if v["member"] in lid][0]); sys.exit(0)
for ip, v in sorted(m.items()):
    print(f"{ip} db={v['db']:.0f}MB in_use={v['use']:.0f}MB raft={v['raft']} term={v['term']} applied={v['applied']} learner={v['learner']} err=[{v['err']}]")
if len(m) != 3: fail.append(f"expected 3 members, got {len(m)}")
if len({v['leader'] for v in m.values()}) != 1: fail.append("members disagree on the leader")
if any(v["learner"] != "false" for v in m.values()): fail.append("a LEARNER is present")
if any(v["err"] for v in m.values()): fail.append("ERRORS column not empty")
if len({v["term"] for v in m.values()}) != 1: fail.append("members disagree on RAFT TERM")
spread = max(v["raft"] for v in m.values()) - min(v["raft"] for v in m.values()) if m else -1
lag = max(v["raft"] - v["applied"] for v in m.values()) if m else -1
print(f"raft index spread {spread}, max raft-applied lag {lag}")
if spread > 50 or lag > 50: fail.append(f"not converged: spread {spread} / apply lag {lag} (> 50)")
term = max(v["term"] for v in m.values()) if m else -1
lead_ip = [ip for ip, v in m.items() if v["member"] == next(iter(v2["leader"] for v2 in m.values()))]
if mode == "snap":
    json.dump({"term": term, "leader_ip": lead_ip[0] if lead_ip else None}, open(sys.argv[2], "w"))
    print("recorded term", term, "leader", lead_ip, "->", sys.argv[2])
if mode == "terms":
    base = json.load(open(sys.argv[2]))["term"]; allowed = int(sys.argv[3])
    print(f"RAFT TERM {base} -> {term}: {term - base} election(s), allowed {allowed}")
    if term - base > allowed: fail.append(f"{term - base} election(s) since the snapshot, allowed {allowed}")
for f in fail: print("  FAIL:", f)
print("VERDICT", "FAIL" if fail else "PASS")
sys.exit(1 if fail else 0)
PY
cat > "$W/promgate.py" <<'PY'
import json, subprocess, sys, argparse, urllib.parse
# Prometheus-side etcd gate. Every threshold is a flag so a negative control can force a FAIL.
ap = argparse.ArgumentParser()
ap.add_argument("--lookback", default="10m")      # fsync/commit worst-5m-p99 window
ap.add_argument("--fsync-ms", type=float, default=50)
ap.add_argument("--commit-ms", type=float, default=50)
ap.add_argument("--hl-window", default="10m")     # etcd_server_has_leader min_over_time window
ap.add_argument("--hl-ignore", default="")        # member IP that just restarted (its own has_leader=0 while booting is not a quorum loss)
ap.add_argument("--kc-mbps", type=float, default=5)
ap.add_argument("--kc-window", default="10m")
ap.add_argument("--members", type=int, default=3)
a = ap.parse_args()
Q = "/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query="
def q(expr):
    d = json.loads(subprocess.check_output(["kubectl", "get", "--raw", Q + urllib.parse.quote(expr)]))
    if d.get("status") != "success": sys.exit(f"FAIL: query error {d}")
    return {x["metric"].get("instance", "*").split(":")[0]: float(x["value"][1]) for x in d["data"]["result"]}
fail = []
for name, metric, lim in (("wal_fsync", "etcd_disk_wal_fsync_duration_seconds_bucket", a.fsync_ms),
                          ("backend_commit", "etcd_disk_backend_commit_duration_seconds_bucket", a.commit_ms)):
    r = q(f"max_over_time(histogram_quantile(0.99, sum by (instance,le) (rate({metric}[5m])))[{a.lookback}:1m])")
    print(f"{name} worst 5m-p99 over {a.lookback}: " + " ".join(f"{k}={v*1000:.1f}ms" for k, v in sorted(r.items())))
    if len(r) != a.members: fail.append(f"{name}: expected {a.members} members, got {sorted(r)} (scrape gap -> wait, retry)")
    elif max(r.values()) * 1000 >= lim: fail.append(f"{name} worst p99 {max(r.values())*1000:.1f}ms >= {lim}ms")
hl = q(f"min_over_time(etcd_server_has_leader[{a.hl_window}])")
print(f"has_leader min over {a.hl_window}: {hl}")
if len(hl) != a.members: fail.append(f"has_leader: expected {a.members} series, got {sorted(hl)}")
for ip, v in hl.items():
    if v < 1 and ip != a.hl_ignore: fail.append(f"{ip} reported etcd_server_has_leader=0 inside {a.hl_window} (leaderless period)")
isl = q("etcd_server_is_leader")
print(f"is_leader: {isl}")
if len(isl) != a.members or sum(isl.values()) != 1: fail.append(f"expected exactly ONE etcd_server_is_leader=1 among {a.members}, got {isl}")
kc = q(f'sum(rate(container_fs_writes_bytes_total{{namespace="flux-system",container="manager",pod=~"kustomize-controller-.*"}}[{a.kc_window}]))')
if not kc: fail.append("kustomize-controller write metric returned NO series -> not scraped, FAIL closed")
else:
    mb = list(kc.values())[0] / 1e6
    print(f"kustomize-controller writes over {a.kc_window}: {mb:.2f} MB/s")
    if mb >= a.kc_mbps: fail.append(f"kustomize-controller {mb:.2f} MB/s >= {a.kc_mbps} MB/s (commit burst in progress)")
for f in fail: print("  FAIL:", f)
print("VERDICT", "FAIL" if fail else "PASS")
sys.exit(1 if fail else 0)
PY
cat > "$W/etcdargs.py" <<'PY'
import subprocess, sys
# want <ip>...   -> each node's RUNNING etcd cmdline carries --election-timeout=5000 AND --heartbeat-interval=500
# absent <ip>... -> neither flag is present (pre-change baseline, and the rollback end-state)
mode, ips = sys.argv[1], sys.argv[2:]
fail = []
for ip in ips:
    out = subprocess.check_output(["talosctl", "-n", ip, "processes"], text=True)
    lines = [l for l in out.splitlines() if "/usr/local/bin/etcd " in l]
    if len(lines) != 1: fail.append(f"{ip}: expected exactly 1 etcd process, found {len(lines)}"); continue
    toks = lines[0].split()
    et = [t for t in toks if t.startswith("--election-timeout")]
    hb = [t for t in toks if t.startswith("--heartbeat-interval")]
    print(f"{ip} pid={toks[1]} {et} {hb}")
    if mode == "want" and (et != ["--election-timeout=5000"] or hb != ["--heartbeat-interval=500"]):
        fail.append(f"{ip}: running etcd does NOT carry 5000/500 (apply-config updates the EtcdSpec only; the process needs `service etcd restart`)")
    if mode == "absent" and (et or hb):
        fail.append(f"{ip}: running etcd still carries a timeout flag {et}{hb}")
for f in fail: print("  FAIL:", f)
print("VERDICT", "FAIL" if fail else "PASS")
sys.exit(1 if fail else 0)
PY
ls "$W"/*.py | wc -l        # MUST print 3
```

Controls run 2026-10-13 against the live cluster (read-only), to re-run once in-window before
trusting a PASS:
- `etcdargs.py absent` on .11/.12/.13 -> `VERDICT PASS`; `etcdargs.py want 192.168.55.11` ->
  `FAIL: ... does NOT carry 5000/500` (proves the gate fails on the pre-change state).
- `etcdstat.py terms <snap> -1` -> `FAIL: 0 election(s) since the snapshot, allowed -1`.
- `promgate.py --fsync-ms 1 --commit-ms 1 --kc-mbps 0.0001` -> three `FAIL:` lines;
  `promgate.py --members 4` -> `FAIL: ... expected 4 ...`.
- The default 1 h `promgate.py` on 2026-10-13 already printed `FAIL: backend_commit worst p99 51.8ms
  >= 50ms` (nuc14-01): the gate bites on real data. If it does that on the window day, see 2.2.

### 2.1 Environment and premises

```bash
cd /Users/mu/code/cberg-home-nextgen
export TALOSCONFIG=$PWD/kubernetes/bootstrap/talos/clusterconfig/talosconfig     # absolute: the .envrc value is relative
export PATH="$(dirname "$(mise which talosctl)"):$(dirname "$(mise which kubectl)"):$(dirname "$(mise which talhelper)"):$PATH"
mise which talhelper ; talhelper --version     # MUST be the 3.1.17 install (/Users/mu/.local/share/mise/installs/talhelper/3.1.17/talhelper);
                                               # the default PATH may resolve 3.1.11, and the configs here were render-verified with 3.1.17
talosctl version --nodes 192.168.55.11 --short 2>&1 | head -3 ; kubectl get nodes
python3 runbooks/plan-premises.py etcd-timeouts-5000-500      # every premise PASS
```

**PASS:** all premises `PASS`, 3 nodes `Ready`, `talhelper --version` reports 3.1.17 (anything else
renders different configs than the ones dry-run verified: STOP). Any FAIL = STOP (do not "fix" a premise).

**Step 0 first.** Every window starts with the safe-update apply (`AUTO_UPDATE_APPLY=1 auto-update.py
--apply` + `coverage.py`), which Flux-reconciles and health-gates a batch of image/chart bumps. Let
it finish AND settle (its health gate green, `flux get kustomizations -A | awk 'NR==1 || $5 != "True"'`
empty, then at least 10 min with no new rollouts) BEFORE starting 2.2: a reconcile storm is exactly the
disk/CPU burst this plan exists to tolerate, and it must not be running underneath the pre-gates.
For an ad-hoc run outside a window, confirm no auto-update batch is in flight.

### 2.2 Starting state and the base-rate rule

```bash
python3 "$W/etcdstat.py" snap "$W/term-before.json"          # converged, records RAFT TERM + leader
python3 "$W/promgate.py" --lookback 1h --hl-window 2h        # the SOP pre-start gate
kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=max(increase(etcd_server_leader_changes_seen_total%5B24h%5D))' | python3 -c "import sys,json;print('max leader changes seen in 24h:', json.load(sys.stdin)['data']['result'][0]['value'][1])"
# CI-idle gate: count ALL non-terminal pods in both CI namespaces (runner pods AND shard/job pods such as
# tnb-responsive-gpu-* in ci-runner; the earlier name regex -runner-[a-z0-9]{5} undercounted: it matched 2 of 5 Running)
CI_ACTIVE=$(for ns in ci-runner arc-build; do kubectl get pods -n $ns --field-selector=status.phase!=Succeeded,status.phase!=Failed --no-headers; done | wc -l | tr -d ' ')
echo "CI pods Running/Pending: $CI_ACTIVE"; test "$CI_ACTIVE" = 0 && echo "CI-IDLE: PASS" || echo "CI-BUSY: FAIL ($CI_ACTIVE)"
```

Negative control (measured live 2026-10-13, the gate FAILS on real data): the same command printed
`CI pods Running/Pending: 3` and `CI-BUSY: FAIL (3)` (ci-runner: one runner pod Running, one in
`Init:0/1`; arc-build: one runner Running; Completed shard pods are correctly not counted). The
phase filter drops Succeeded/Failed pods, so a finished burst reads 0. A kubectl error (missing
namespace, API down) prints to stderr and the count falls to 0, so also run
`kubectl get ns ci-runner arc-build` once and require both to exist (a missing namespace is a FAIL).
Idle is a period of quiet, not an instant: require three consecutive `CI-IDLE: PASS` readings 5 min
apart, because CI jobs start in bursts.

**PASS (all):** `etcdstat` PASS; `promgate` PASS (worst 5m-p99 fsync and commit under 50 ms
over 1 h, one leader, kustomize-controller under 5 MB/s); the 24 h leader-change maximum is
below 6 (see the acknowledgement step below: expected to be FALSE right after a CI day); **`CI-IDLE: PASS`**
(0 non-terminal pods in `ci-runner` and `arc-build`; CI is the churn driver - a build burst during the
window confounds every gate and is itself a load on the disks being restarted).

**Operator acknowledgement step (mandatory, asked explicitly in the go/no-go, not assumed).** Measured
2026-10-13: 27 leader changes in the last 24 h, and the default-threshold `promgate.py` already FAILS
today (backend commit p99 51.8 ms on nuc14-01). So on any day within roughly 24 h of a CI burst the
base-rate rule and `promgate` WILL trip, and "wait and retry" is only meaningful once CI is idle.
Procedure: (1) check CI idle first with the gate above (3 readings 5 min apart); (2) only then run
`promgate.py --lookback 1h` - the 1 h lookback must not contain the CI burst; (3) read the 24 h
leader-change maximum, and if it is >= 6, record the operator's named acknowledgement
(`home-operation decide`, text: "proceed against the base-rate rule; churn attributed to CI load,
CI idle for the last hour") BEFORE the freeze in 2.3. No acknowledgement = NO-GO for the day,
even if every other gate passes. Do not wait for the 24 h count to fall below 6 when CI is idle
and the 1 h gates pass - that is exactly the state the acknowledgement covers.

**If the 24 h count is >= 6** the SOP base-rate rule says planned disruptions are NO-GO until
explained. Here it is explained (this plan's purpose) but a *currently unstable* cluster is the
wrong moment for a service restart: STOP unless the operator acknowledges by name, in the go/no-go,
that the window proceeds against the base-rate rule and the churn is attributed to CI load
(check the churn timestamps against `kubectl get pods -A | grep runner`). Without that
acknowledgement the plan is NO-GO for the day.

**If `promgate` fails on commit/fsync (as it did 2026-10-13 for nuc14-01 at 51.8 ms):** wait
10 min and retry, at most 3 times, with CI runners idle. Still failing = NO-GO (not urgent; the
change adds tolerance, it must not be started during a stall). Do not raise the thresholds.

### 2.3 Push freeze and ImageUpdateAutomation (docs/sops/talos-upgrade.md 14.3 wording)

Commit bursts drive etcd disk writes; freeze `main` for the window.

```bash
git fetch origin main && git rev-parse origin/main | tee "$W/freeze-sha.txt"
# pre-state of every ImageUpdateAutomation: (namespace, name, suspend)
kubectl get imageupdateautomation -A -o jsonpath='{range .items[*]}{.metadata.namespace}{" "}{.metadata.name}{" "}{.spec.suspend}{"\n"}{end}' | tee "$W/iua-before.txt"
```

Suspend ONLY rows whose third column is `false` or empty (an automation that is `true` in git is
an operator hold - never resume it). Example for one row, repeat per row:
`kubectl patch imageupdateautomation <name> -n <ns> --type merge -p '{"spec":{"suspend":true}}'`
(this is an in-window freeze, reverted in 3.8; do NOT suspend the `flux-system` GitRepository).
Before every node step in section 3, `git fetch origin main && test "$(git rev-parse origin/main)" = "$(cat "$W/freeze-sha.txt")"`
must succeed; a moved `origin/main` = pause, find out who pushed, and let `promgate` settle.

### 2.4 Snapshot (backup_gate, part 1)

```bash
LEADER_IP=$(python3 "$W/etcdstat.py" leader); echo "leader=$LEADER_IP"
talosctl -n "$LEADER_IP" etcd snapshot "$W/etcd-pre-$(date -u +%Y%m%dT%H%MZ).db"
chmod 600 "$W"/etcd-pre-*.db; stat -f '%Lp %z %N' "$W"/etcd-pre-*.db
```

**PASS:** mode `600` and size of the same order as `DB SIZE` (about 450 MB; a 0-byte or few-KB
file is a FAIL). The file holds every Secret in the cluster: local only, `rm -P` it 24 h after
the change has soaked (3.9). Restore is disaster-recovery only (`docs/sops/etcd.md` 4.4 /
`docs/sops/talos-upgrade.md` 11.4) - a single unhealthy member is NOT a restore case.

### 2.5 Pre-render the rollback config and prove it equals live (backup_gate, part 2)

```bash
cd kubernetes/bootstrap/talos && talhelper genconfig >/dev/null && cd ../../..
rm -rf "$W/r-head" && cp -R kubernetes/bootstrap/talos/clusterconfig "$W/r-head" && chmod -R go-rwx "$W/r-head"
for n in 1 2 3; do talosctl -n 192.168.55.1$n apply-config --dry-run --mode=no-reboot -f "$W/r-head/kubernetes-k8s-nuc14-0$n.yaml" 2>&1 | grep -E '^(\+|-|No changes|Applied)' ; done
python3 "$W/etcdargs.py" absent 192.168.55.11 192.168.55.12 192.168.55.13
```

(`genconfig` renders from the clean HEAD tree - premise `talos-dir-clean`.)

**PASS:** each of the three dry-runs prints `No changes.` and no `+`/`-` line (HEAD == live; this
is the byte-equivalence proof for the rollback config) and `etcdargs.py absent` prints `VERDICT
PASS`. A `+`/`-` line = live config drifted from HEAD: STOP, someone changed a node by hand.
The grep deliberately drops context lines: the unfiltered dry-run diff prints the etcd CA key
material. Never pipe an unfiltered dry-run into a log, a chat or the repo.

### 2.6 Control-plane baseline

```bash
{ kubectl get lease -n kube-system kube-controller-manager kube-scheduler -o jsonpath='{range .items[*]}{.metadata.name}={.spec.leaseTransitions}{"\n"}{end}'
  kubectl get pods -n kube-system -l tier=control-plane -o jsonpath='{range .items[*]}{.metadata.name}={.status.containerStatuses[0].restartCount}{"\n"}{end}'; } | tee "$W/cp-before.txt"
```

Expected on 2026-10-13: `kube-controller-manager=45`, `kube-scheduler=37`, nine static pods
(apiserver 0/0/0). Values at the window are the baseline.

## 3. Steps

All steps are run by cberg-agent under the window agent; the operator is present (attended
slot). No step in this plan reboots a node. Stop rules: any `FAIL` or any unexpected term bump
ends the forward path at the current node; go to section 5 for the nodes already changed.

### 3.0 Edit the patch (working tree only; not committed until 3.8)

```bash
cd /Users/mu/code/cberg-home-nextgen
F=kubernetes/bootstrap/talos/patches/controller/cluster.yaml python3 - <<'PY'
import os
p = os.environ["F"]
s = open(p).read()
old = "      listen-metrics-urls: http://0.0.0.0:2381\n"
new = old + '      election-timeout: "5000"\n      heartbeat-interval: "500"\n'
assert s.count(old) == 1 and "election-timeout" not in s, "anchor missing/duplicated or already patched"
open(p, "w").write(s.replace(old, new))
PY
git diff --stat -- "$F" kubernetes/bootstrap/talos/patches/controller/cluster.yaml | tail -1
git diff -U0 -- kubernetes/bootstrap/talos/patches/controller/cluster.yaml | grep -E '^[+-][^+-]'
```

Dry-tested 2026-10-13 on a scratch copy; the diff against HEAD is exactly:

```
+      election-timeout: "5000"
+      heartbeat-interval: "500"
```

**PASS:** exactly those two `+` lines and nothing else (the python asserts abort on a changed
anchor, so a silent no-op is impossible). Re-read the result with
`python3 -c "import yaml;print(yaml.safe_load(open('kubernetes/bootstrap/talos/patches/controller/cluster.yaml'))['cluster']['etcd'])"`
(must show `election-timeout: '5000'` and `heartbeat-interval: '500'` as STRINGS - Talos
extraArgs are string-valued).

### 3.1 Render and prove the node-config diff

```bash
cd kubernetes/bootstrap/talos && talhelper genconfig >/dev/null && cd ../../..
for n in 1 2 3; do diff <(grep -v '^#' "$W/r-head/kubernetes-k8s-nuc14-0$n.yaml") <(grep -v '^#' kubernetes/bootstrap/talos/clusterconfig/kubernetes-k8s-nuc14-0$n.yaml); done
cp -R kubernetes/bootstrap/talos/clusterconfig "$W/r-new" && chmod -R go-rwx "$W/r-new"
```

(The files are `-01..-03`, two digits - NOT the node IP's last octet; an IP-derived name fails
with "no such file".) Each of the three diffs must be exactly
`> election-timeout: "5000"` / `> heartbeat-interval: "500"` (two `>` lines at the same indent)
and nothing else. Anything else = another patch changed: STOP.

### 3.2 Dry-run against every node

```bash
for n in 1 2 3; do echo "== 0$n"; talosctl -n 192.168.55.1$n apply-config --dry-run --mode=no-reboot -f kubernetes/bootstrap/talos/clusterconfig/kubernetes-k8s-nuc14-0$n.yaml 2>&1 | grep -E '^(\+|-|No changes|Applied|Dry)'; done
```

**PASS:** each node prints `Applied configuration without a reboot (skipped in dry-run).` and
exactly `+            election-timeout: "5000"` and `+            heartbeat-interval: "500"`
(measured identically on all three nodes 2026-10-13). `--mode=no-reboot` is used for the real
applies so that, if a future Talos made this change reboot-requiring, the apply fails instead of
rebooting a control-plane node.

### 3.3 Order

```bash
LEADER_IP=$(python3 "$W/etcdstat.py" leader); echo "leader=$LEADER_IP"
```

Followers = the two nodes that are NOT `$LEADER_IP`; leader last. On 2026-10-13 the leader is
.12 (a1ca2fde...), the VIP holder is .13, so the expected order is .11, then .13, then .12 -
but re-read the leader at the window; the order follows the live leader, not this sentence.
Node numbers: .11 = `01`, .12 = `02`, .13 = `03`; members .11 = 187ea782..., .12 = a1ca2fde...,
.13 = 73a201c6... (2026-10-13).

### 3.4 Follower 1 (repeat 3.4 for follower 2; set `N`/`IP` first)

```bash
N=01; IP=192.168.55.11          # first FOLLOWER (not the leader)
git fetch origin main && test "$(git rev-parse origin/main)" = "$(cat "$W/freeze-sha.txt")" && echo FREEZE-OK
talosctl -n $IP apply-config --mode=no-reboot -f kubernetes/bootstrap/talos/clusterconfig/kubernetes-k8s-nuc14-$N.yaml
talosctl -n $IP get etcdspec -o yaml | grep -A2 -E 'election-timeout|heartbeat-interval'      # resource updated
python3 "$W/etcdargs.py" absent $IP                       # EXPECTED PASS: still the old flags - this is the apply/effective gap
talosctl -n $IP service etcd restart
for i in $(seq 1 60); do python3 "$W/etcdargs.py" want $IP >/dev/null 2>&1 && break; sleep 5; done
python3 "$W/etcdargs.py" want $IP
```

**PASS:** the etcdspec shows both values; the pre-restart `absent` check PASSES (documents that
apply-config alone did nothing to the process); after the restart `want` prints
`VERDICT PASS` for this node (the flags exist ONLY on the new process, so this also proves the
process was replaced). A FAIL after 5 min: `talosctl -n $IP service etcd` and `talosctl -n $IP
logs etcd | tail -30`; the node's etcd is down on 1 of 3 - quorum holds, but STOP and go to 5.

Then verify convergence and settle:

```bash
for i in $(seq 1 24); do python3 "$W/etcdstat.py" terms "$W/term-before.json" 0 >/dev/null 2>&1 && break; sleep 5; done
python3 "$W/etcdstat.py" terms "$W/term-before.json" 0
sleep 600          # >= 10 min settle between nodes (docs/sops/talos-upgrade.md 14.3)
python3 "$W/promgate.py" --lookback 10m --hl-window 10m --hl-ignore $IP
python3 "$W/etcdstat.py" terms "$W/term-before.json" 0
```

**PASS:** `etcdstat` converged with **0 elections** (a follower restart must not bump the term;
`terms ... 0`), `promgate` PASS over the 10-minute settle window (fsync and commit under 50 ms,
one leader, no `has_leader=0` on the members that did not restart, kustomize-controller under
5 MB/s). After the restart, kubectl through the VIP may hiccup for seconds if the node held the
VIP (.13): `promgate` errors during that interval are retried, not ignored - three retries
30 s apart, then it is a FAIL. A term bump here is a stop (election with no leader change
expected = pattern (ii) of `docs/sops/talos-upgrade.md` 14.3: triage before continuing).

### 3.5 Follower 2

Repeat 3.4 with the other follower (`N=03; IP=192.168.55.13` when the order is .11, .13, .12).
Same PASS criteria; `terms ... 0` still allows 0 elections. If the node holds the VIP expect
the VIP to move and return (watch with `talosctl -n 192.168.55.11,192.168.55.12,192.168.55.13
get address | grep 192.168.55.10`); kubectl, if it fails, is retried against the next VIP
holder - do not treat the transient as a cluster fault unless it lasts over 60 s.

### 3.6 Leader (last)

At this point both followers run 5000/500 and the leader still runs 1000/100.

```bash
N=02; IP=192.168.55.12          # the LEADER (re-read: python3 "$W/etcdstat.py" leader)
git fetch origin main && test "$(git rev-parse origin/main)" = "$(cat "$W/freeze-sha.txt")" && echo FREEZE-OK
talosctl -n $IP apply-config --mode=no-reboot -f kubernetes/bootstrap/talos/clusterconfig/kubernetes-k8s-nuc14-$N.yaml
talosctl -n $IP get etcdspec -o yaml | grep -A2 -E 'election-timeout|heartbeat-interval'
talosctl -n $IP etcd forfeit-leadership                   # moves leadership to a NEW-config member (+1 election, by design)
python3 "$W/etcdstat.py" leader                           # MUST now print a node other than $IP
talosctl -n $IP service etcd restart                      # now a follower: no leaderless gap
for i in $(seq 1 60); do python3 "$W/etcdargs.py" want $IP >/dev/null 2>&1 && break; sleep 5; done
python3 "$W/etcdargs.py" want $IP
```

Run `forfeit-leadership` and `service etcd restart` back to back (seconds apart): between them the
old-config member is a follower of a 500 ms-heartbeat leader with about 1 s of margin (1.4).
`talosctl etcd forfeit-leadership` is the stock Talos command (it hands leadership to another
member before the node goes away); its exact transfer behaviour was not re-read in source for
v1.14.1 - the gate below, not the command's name, is the evidence.

**PASS:** the leader changed before the restart; `want` PASS; and

```bash
for i in $(seq 1 24); do python3 "$W/etcdstat.py" terms "$W/term-before.json" 1 >/dev/null 2>&1 && break; sleep 5; done
python3 "$W/etcdstat.py" terms "$W/term-before.json" 1       # at most ONE election in the whole window
```

is converged with a total term bump of **exactly 1** (the forfeit). If `forfeit-leadership`
errors or the leader did not move: do NOT retry in a loop. Fallback (documented, higher
exposure): plain `service etcd restart` on the leader - expect a leaderless gap of 5-10 s while
the two new-config members time out (writes stall, apiserver 5xx for that long), term +1 or +2;
the allowance becomes `terms ... 2` for this path, and the control-plane lease counters in 4.4
are expected to move. Use the fallback only with the operator's say-so in the window.

Settle and gate exactly like 3.4:

```bash
sleep 600
python3 "$W/promgate.py" --lookback 10m --hl-window 10m --hl-ignore $IP
python3 "$W/etcdstat.py" terms "$W/term-before.json" 1
```

### 3.7 Final proof that all three run the new flags

```bash
python3 "$W/etcdargs.py" want 192.168.55.11 192.168.55.12 192.168.55.13
```

### 3.8 Commit and push the patch, thaw

The patch is committed only now, after the nodes run it (Flux does not reconcile this
directory, so the commit is the record, not the deployment).

```bash
cd /Users/mu/code/cberg-home-nextgen
printf '%s\n' 'feat(talos): etcd election-timeout 5000 / heartbeat-interval 500 (F-f5879ed8)' '' 'Applied node by node (followers first, leader last after forfeit-leadership) with a' 'service etcd restart per member: apply-config alone does not change the running args.' > "$W/msg-commit.txt"
git commit --only kubernetes/bootstrap/talos/patches/controller/cluster.yaml -F "$W/msg-commit.txt"
git log -1 --format=%s ; git show --stat HEAD | tail -3
```

**PASS:** the subject printed by `git log -1 --format=%s` is YOURS (concurrent sessions swap
messages - amend before pushing if not) and `git show --stat` lists exactly one file. Then
`git push origin main`.

Thaw only what 2.3 suspended: for each row of `$W/iua-before.txt` whose third column was
`false` or empty, `kubectl patch imageupdateautomation <name> -n <ns> --type merge -p '{"spec":{"suspend":false}}'`.

```bash
kubectl get imageupdateautomation -A -o jsonpath='{range .items[*]}{.metadata.namespace}{" "}{.metadata.name}{" "}{.spec.suspend}{"\n"}{end}' | diff - "$W/iua-before.txt" && echo IUA-RESTORED
```

**PASS:** `diff` is empty (resumed rows are back to their pre-state, the pre-suspended rows
are still `true`). A non-empty diff is read row by row, never blanket-resumed.

### 3.9 Cleanup

Keep `$W/etcd-pre-*.db` and `$W/r-head` for 24 h; then `rm -P "$W"/etcd-pre-*.db` and
`rm -rf "$W/r-head" "$W/r-new"` (the config copies contain cluster secrets).

## 4. Verification

Run after 3.7 and again 24 h later (4.6). Each gate states what its failure looks like.

### 4.1 The change is live on the running processes (not just in config)

```bash
python3 "$W/etcdargs.py" want 192.168.55.11 192.168.55.12 192.168.55.13
for ip in 192.168.55.11 192.168.55.12 192.168.55.13; do talosctl -n $ip get etcdspec -o yaml | grep -A2 -E 'election-timeout|heartbeat-interval' | tr -d '\n '; echo; done
```

CONTENTS ASSERTION: the RUNNING etcd process on each of the three nodes carries
`--election-timeout=5000` and `--heartbeat-interval=500` - measured by `etcdargs.py want` on
`talosctl processes`, compared to the pre-change baseline where the same script's `absent` mode
passed and `want` failed (2026-10-13, 2.0). A config that was applied but not restarted prints
`FAIL ... does NOT carry 5000/500`; an etcdspec without a restart (the apply-config-only
state) prints PASS for the grep above and FAIL for `etcdargs.py` - that is why the script, not the
resource, is the gate.

### 4.2 The cluster is healthy and converged

```bash
python3 "$W/etcdstat.py" terms "$W/term-before.json" 1
talosctl -n 192.168.55.11,192.168.55.12,192.168.55.13 etcd members
talosctl -n 192.168.55.11,192.168.55.12,192.168.55.13 etcd alarm list
```

CONTENTS ASSERTION: three voting members, one leader, no learner, empty ERRORS, one common
RAFT TERM, raft index spread under 50, and the total RAFT TERM bump since 2.2 is at most 1 (the
forfeit) - measured by `etcdstat.py` against `$W/term-before.json`. Failure prints `FAIL: N
election(s) since the snapshot, allowed 1`, `members disagree on RAFT TERM`, or a non-empty
ERRORS column. `etcd alarm list` must print nothing (a NOSPACE alarm would be a separate
incident).

### 4.3 Prometheus agrees (and the instrument itself is alive)

```bash
python3 "$W/promgate.py" --lookback 10m --hl-window 30m
kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=ALERTS%7Balertname%3D~%22etcd.%2A%22%2Calertstate%3D%22firing%22%7D' | python3 -c "import sys,json;print('etcd alerts firing:', len(json.load(sys.stdin)['data']['result']))"
kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=ALERTS%7Balertname%3D%22Watchdog%22%2Calertstate%3D%22firing%22%7D' | python3 -c "import sys,json;print('Watchdog (ALERTS ingestion control):', len(json.load(sys.stdin)['data']['result']))"
```

CONTENTS ASSERTION: all three members scrape (3 series per gate metric), worst 5m-p99 WAL fsync
and backend commit stay under 50 ms over the final settle window, exactly one member reports
`etcd_server_is_leader=1`, no member reported `etcd_server_has_leader=0` in the last 30 min, and
**0 etcd alerts firing**. The alert count is only meaningful if the `ALERTS` series is ingested:
the Watchdog control line MUST print `1`; `0` there means "empty read", not "no alerts" (FAIL
closed).

CONTROL: metric etcd_disk_wal_fsync_duration_seconds_bucket - worst 5m-p99 under 50 ms per member over the settle window; exactly 3 series, fewer = scrape gap = FAIL.
CONTROL: metric etcd_disk_backend_commit_duration_seconds_bucket - same bound, same 3-series requirement.
CONTROL: metric etcd_server_has_leader - min_over_time over the window is 1 on every member that did not just restart; fewer than 3 series = FAIL.
CONTROL: metric etcd_server_is_leader - exactly one series equals 1.
CONTROL: metric etcd_server_leader_changes_seen_total - post-window soak only (4.6): a per-member counter that RESETS on each restart, so it is not used as the in-window gate (RAFT TERM from `talosctl etcd status` is).
CONTROL: metric container_fs_writes_bytes_total - kustomize-controller (`container="manager"`) write rate under 5 MB/s over 10 min; no series = FAIL (push-freeze effectiveness).
CONTROL: alertname etcdNoLeader - not firing.
CONTROL: alertname etcdMembersDown - not firing.
CONTROL: alertname etcdInsufficientMembers - not firing.
CONTROL: alertname etcdHighNumberOfLeaderChanges - not firing.
CONTROL: alertname etcdHighFsyncDurations - not firing.
CONTROL: alertname Watchdog - FIRING (value 1): the proof that the ALERTS series is ingested, so a zero for the etcd alerts is a real zero.

### 4.4 The control plane did not pay for it

```bash
{ kubectl get lease -n kube-system kube-controller-manager kube-scheduler -o jsonpath='{range .items[*]}{.metadata.name}={.spec.leaseTransitions}{"\n"}{end}'
  kubectl get pods -n kube-system -l tier=control-plane -o jsonpath='{range .items[*]}{.metadata.name}={.status.containerStatuses[0].restartCount}{"\n"}{end}'; } > "$W/cp-after.txt"
diff "$W/cp-before.txt" "$W/cp-after.txt"; echo "---"; diff <(grep apiserver "$W/cp-before.txt") <(grep apiserver "$W/cp-after.txt") && echo APISERVER-RESTARTS-UNCHANGED
kubectl get pods -A --no-headers | grep -v -E 'Running|Completed' | head
```

CONTENTS ASSERTION: no kube-apiserver static pod restarted (`APISERVER-RESTARTS-UNCHANGED`;
a restart means its liveness probe saw its local etcd down long enough to be killed). The full
`diff` is REPORTED, not gated: a `kube-controller-manager`/`kube-scheduler` `leaseTransitions`
+1 is the documented cost of one etcd restart on the node they sit on (they re-acquire the lease)
and is recorded in the window report. Failure of the apiserver assertion prints the changed
`kube-apiserver-...=N` line. The last command lists non-Running pods; compare to the 2.1
baseline - anything new that is not a Job/Completed is investigated before closing.
Negative control: `sed 's/kube-apiserver-k8s-nuc14-01=0/kube-apiserver-k8s-nuc14-01=1/' "$W/cp-after.txt" > "$W/cp-neg.txt"`
then the same apiserver `diff` against it must exit non-zero (BSD sed, plain BRE, no `\s`).

### 4.5 What NOT to read as success

`etcd_server_heartbeat_send_failures_total` will flatten or drop after this change **by
definition**: etcd counts a failure when a heartbeat send takes longer than 2 x the heartbeat
interval (200 ms -> 1 s) and sends are now 5x rarer. The before/after comparison of that counter
is not evidence the cluster got better and no gate here reads it. Likewise
`etcd_network_peer_round_trip_time_seconds` (RTT p99 about 6 ms, peak 12.6 ms on 2026-10-13)
should be UNCHANGED - it is the network, which this plan does not touch; a changed RTT would
point at something else that happened in the window.

### 4.6 Soak (operator follow-up, not a window gate)

Record in the window report: the RAFT TERM after the window (expected `term-before + 1`).
After the next CI-heavy day and again at 7 days: `talosctl -n 192.168.55.11 etcd status` RAFT
TERM must have grown by at most the real node events in between (not by 20 per evening). Then
`runbooks/policy-cli.py finding close F-f5879ed8 --commit <sha>` and F-27a3f024 ONLY if the term
did not climb under a CI burst; if it did climb, the CI-side fix in F-f5879ed8 (cap CI CPU on the
control-plane nodes) is the next action and this plan did not fix the cause.

## 5. Rollback

**Nature of the rollback.** The timeouts are process arguments, not stored in the WAL or DB:
nothing is forward-only, and reverting is: restore the old config on the node, then restart
that node's etcd (again, apply-config alone does nothing to the running process). Flux does not
reconcile `kubernetes/bootstrap/talos/`, so `git revert` of the commit changes NOTHING on the
nodes. Rollback therefore always has an on-node part.

**Triggers.** Any gate FAIL that persists after its retries; an unexpected election (term bump
beyond the allowance); `etcdNoLeader` / `etcdMembersDown` firing; an apiserver restart; the
operator calling it. A part-rolled cluster (some members 5000/500, some 1000/100) is a supported
transient (Section 1.2 point 3-4) - the safe response to a doubt is to STOP where you are,
not to push on and not to hurry back.

```bash
cd /Users/mu/code/cberg-home-nextgen
# 1. working tree back to HEAD for the patch (before 3.8 there is nothing committed):
git diff --quiet HEAD -- kubernetes/bootstrap/talos/patches/controller/cluster.yaml || git checkout HEAD -- kubernetes/bootstrap/talos/patches/controller/cluster.yaml
# AFTER 3.8 instead:  git revert --no-edit <sha-of-the-etcd-commit>   (a normal revert commit; verify git log -1 --format=%s before pushing)
# 2. the rollback configs were pre-rendered and proven equal to live in 2.5:
ls "$W/r-head"/kubernetes-k8s-nuc14-0*.yaml | wc -l      # MUST print 3
```

Then, for EACH node that already runs the new flags (check with `etcdargs.py want <ip>`), in the
same order as forward (followers first, leader last, `forfeit-leadership` before the leader):

```bash
N=01; IP=192.168.55.11
talosctl -n $IP apply-config --mode=no-reboot -f "$W/r-head/kubernetes-k8s-nuc14-$N.yaml"
talosctl -n $IP get etcdspec -o yaml | grep -c -E 'election-timeout|heartbeat-interval'     # must print 0
talosctl -n $IP service etcd restart
for i in $(seq 1 60); do python3 "$W/etcdargs.py" absent $IP >/dev/null 2>&1 && break; sleep 5; done
python3 "$W/etcdargs.py" absent $IP
python3 "$W/etcdstat.py" converged ; sleep 600; python3 "$W/promgate.py" --lookback 10m --hl-ignore $IP
```

**Confirm the cluster is back:** `etcdargs.py absent` PASS on all three nodes, the dry-run of
`kubernetes/bootstrap/talos/clusterconfig` regenerated from the reverted tree reports `No changes.` on
all three nodes, `etcdstat.py converged` PASS, `promgate.py` PASS, the patch file has no
`election-timeout` line (`grep -c election-timeout kubernetes/bootstrap/talos/patches/controller/cluster.yaml` prints 0), and the IUAs are
restored as in 3.8. Rolling back does not restore any state: the term simply keeps counting.

**If a member does not come back** (etcd `service` not `Running`/`OK` after 5 min, or ERRORS in
`etcd status`): quorum is still 2/3 - do not touch a second member. `talosctl -n <ip> logs etcd`
first; a bad flag value would show as a flag-parse error on start (the values here were
validated against `embed/config.go`). `docs/sops/etcd.md` 4.3: restart the service on that
member only. **Quorum loss or data corruption** (two members down, or the cluster not
recovering): operator-present disaster recovery from the 2.4 snapshot per `docs/sops/etcd.md`
4.4 / `docs/sops/talos-upgrade.md` 11.4 - that wipes EPHEMERAL on the nodes (every Longhorn
replica on them), so it is a last resort and needs the operator's explicit go.

## 6. Interference notes

- **Window choice (PENDING OPERATOR DECISION; `window: null`).** Options:
  1. **Attended ad-hoc run on a CI-idle period (RECOMMENDED by the plan reviewer and the planner).** An
     on-demand run has 480 min of capacity (est 110), brings the tolerance in BEFORE the 11-01
     `talos-linux-1.14.2` roll (which restarts etcd three times and is where the thin 1 s margin
     hurts most), avoids the nocodb collision entirely, and needs no other plan to move. Requires an
     attended operator and the idle-CI gate in 2.2.
  2. `sun-attended:2026-11-08` - only if `nocodb-2026.09.1` (45 min, backup-restore, 12 knex
     migrations, currently holding that slot) moves. `conflicts_with` declares the pairing and the
     scheduler refuses it (operator rule: ONE risky change per window; two backup-restore plans in
     one slot leave no rollback capacity for either). 11-08 is 7 days after the node roll and 7 days
     before `longhorn-1.13.0`, which keeps their "no unexplained leader change in 2 h" pre-gates
     clean, but it lands AFTER the roll, so etcd would go through the roll on the old 1 s timeout.
  Capacity rules out Saturday and nightly (est 110 min vs 70 schedulable on both). Every earlier
  Sunday/Saturday is taken (10-17 coredns; 10-18 nextcloud-fleet; 10-24 paperless-db; 10-25
  redis-fleet + jellyfin-config-rwo-migration; 10-31 penpot-chart; 11-01 talos-linux-1.14.2
  exclusive; 11-07 helm-drift-detection), 11-15 is the exclusive longhorn-1.13.0 and 11-22
  flux-oci-chart-sources. Do not stamp a window until the operator chooses.
- **Reciprocity is not mine to write.** `conflicts_with` is honoured per side. The plans that
  must name `etcd-timeouts-5000-500` back: `talos-linux-1.14.2`, `longhorn-1.13.0`,
  `kube-prometheus-stack-92.2.0`, `nocodb-2026.09.1`, `talos-power-tuning-ab`, and the
  backup-restore pairs. This plan edited none of them.
- **Prometheus is the instrument and goes through the VIP.** Every gate reads Prometheus via
  `kubectl get --raw`, i.e. through the apiserver; while the node that holds the VIP (.13 on
  2026-10-13) restarts etcd, the VIP can move and kubectl can fail for seconds. A gate error in
  that interval is retried, not counted as a pass. The same-night `kube-prometheus-stack` bump is
  forbidden (conflicts_with).
- **CI is both the cause and the confounder.** ARC runner pods (`arc-build`, `ci-runner`) are the
  load that produced the churn. 2.2 requires `CI-IDLE: PASS` (0 non-terminal pods in both CI namespaces, three readings) at the start; a CI burst
  mid-window makes every gate unreadable and is a reason to pause, not to proceed.
- **Flux / commit load.** The ImageUpdateAutomation suspend and the origin/main freeze exist
  because commit bursts drive etcd disk writes. Only the rows that were not already suspended are
  suspended and resumed (the absenty automations are an operator hold).
- **Talos config is applied by hand.** Another plan that runs `talosctl apply-config` on these
  nodes in the same slot would make "the config on the node" ambiguous - hence the
  `talos-*`/`multus-*` conflicts. The `talos-dir-clean` premise stops a stray uncommitted edit
  from being rendered into the node configs alongside this change.
- **Public repo.** No hostnames, CA material or secrets appear here. The dry-run diff of
  `apply-config` prints the etcd CA key in its context lines; the plan filters them out and
  must keep doing so.
- **Repo corrections found while planning (for the window agent's report).**
  `docs/sops/etcd.md` section 3 said machine-config changes are blocked until the multi-doc
  migration - stale; the migration landed 2026-10-04 (commit `a7965251`, applied to all three nodes;
  `docs/sops/talos-upgrade.md` 14.2 records it). Corrected in the SOP by the planner on 2026-10-13.
  Its "expect 6 series" counts fsync + commit combined (3 members x 2), not 6 members (not yet
  corrected).
