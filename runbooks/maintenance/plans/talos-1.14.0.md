---
plan_id: talos-1.14.0
component: talos
pr: null                              # THE NODE IMAGE HAS NO RENOVATE PR — see §1
                                      # "Attribution". PR #212 is the talosctl CLI
                                      # pin in .mise.toml and is a SEPARATE artifact,
                                      # merged as the LAST step of this plan (§3.6).
kind: infra
current: "v1.13.10"                   # live on all 3 nodes, verified 2026-09-09
target: "v1.14.0"                     # released 2026-09-03
update_type: minor                    # single-minor traversal (Talos allows no skip)
risk: high                            # rolling reboot of every control-plane node in a
                                      # 3-node hyper-converged cluster: etcd quorum,
                                      # 93 Longhorn volumes at replica=2, and the ONLY
                                      # HTTP data plane (Envoy Gateway) all ride on it
est_duration_min: 140                 # IN-WINDOW only. Phase A prep (~30 min) is
                                      # Flux-inert and MUST run before the window —
                                      # see §7 "Duration against the 150-min slot".
needs_reboot: true                    # three sequential node reboots
touches:
  namespaces:
    - kube-system                     # etcd, kube-apiserver, controller-manager,
                                      # scheduler, kube-proxy, coredns, cilium, authentik
    - storage                         # longhorn-manager, instance-manager, CSI, 93 volumes
    - network                         # envoy-gateway, envoy-internal, envoy-external,
                                      # k8s-gateway, external-dns, adguard-home, cloudflared
    - monitoring                      # prometheus, alertmanager, grafana, edot-collector
    - "ALL (cluster-wide)"            # every pod on the cluster is evicted and
                                      # rescheduled once; this is not a scoped change
  resources:
    - kubernetes/bootstrap/talos/talconfig.yaml   # talosVersion — THE node image bump
    - kubernetes/bootstrap/talos/clusterconfig/   # talhelper-generated, SOPS-encrypted
    - .mise.toml                                  # aqua:siderolabs/talos CLI pin (§3.6)
    - .github/renovate.json5                      # not edited; see §3.1 note on the
                                                  # dead ghcr.io installer annotation
    - node/k8s-nuc14-01                           # 192.168.55.11
    - node/k8s-nuc14-02                           # 192.168.55.12 — holds the VIP .10
    - node/k8s-nuc14-03                           # 192.168.55.13 — current etcd leader
    - "etcd (3 members, 3.6.14 -> 3.7.x)"
    - "190 longhorn replicas / 93 volumes (numberOfReplicas: 2)"
  shared:
    - etcd                            # quorum 3; exactly ONE member may be down
    - cni/cilium                      # v1.20.1 DaemonSet restarts per node
    - coredns                         # bundled version moves with the Talos release
    - storage/longhorn                # instance-manager restart + replica rebuild per node
    - ingress                         # Envoy Gateway IS the only HTTP(S) data plane
    - cert-manager                    # webhook pods reschedule
    - monitoring                      # scrape gaps + node-level alerts during each reboot
depends_on: []
conflicts_with:                       # THIS PLAN NEEDS THE WHOLE sun-attended SLOT.
  - absenty-drop-npm-runtime          # currently sun-attended:2026-09-13, 60 min
  - authentik-pg18-lockstep           # currently sun-attended:2026-09-13, 35 min
  - authentik-pg17-decommission       # must not destroy the auth DB rollback in a
                                      # window that also reboots every node
  # RESOLVED 2026-09-09: superset-pg-cutover dropped. Its §5 rollback repointed
  # DB_HOST at superset-postgresql (retired 2026-09-05, 90539942), and the
  # alternate leg superset-pg was retired 2026-09-09 (9d10199c). Neither leg
  # exists, so the guard protected nothing — same dead-ref shape as the
  # longhorn-1.12.1-engine entries cleaned out on 2026-09-05.
  - multus-macvlan-foundation         # also mutates Talos machine config
  # General rule, not a list: NO other plan may share this window. A node roll
  # evicts every pod in the cluster, so any concurrent plan's verification is
  # measuring a cluster in motion. See §6.
capability_change: true               # v1.14 changes node-level behaviour on upgrade:
                                      # containerd NRI now ENABLED by default,
                                      # net.ipv4.conf.*.send_redirects=0 by default,
                                      # etcd + kube-apiserver minimum TLS 1.3,
                                      # etcd HTTP endpoints move 2379 -> 2383.
                                      # => never unattended. Operator present.
rollback_class: one-way               # HONEST RATING — see §5. Per-node
                                      # `talosctl rollback` is real and is the CANARY's
                                      # abort path, but it is one boot-partition deep
                                      # and does not unwind etcd 3.6 -> 3.7. Past the
                                      # canary this is roll-forward / restore.
security_ref: null                    # no security driver
finding_refs:
  - F-912f4778                        # "Talos Linux (cluster nodes): v1.13.10 -> v1.14.0"
  - F-fc435c71                        # "node roll has no plan file and no reboot-capable
                                      #  window with capacity" — THIS FILE answers it
  - F-9a58f400                        # the PR #212 mis-attribution this plan corrects
status: awaiting-go                    # needs an operator go/no-go before it runs
window: "sun-attended:2026-09-27"     # NOT self-assigned: this is the first-feasible
                                      # slot F-fc435c71 already computed, and
                                      # maintenance-plan.py --validate rejects
                                      # status:awaiting-go with a null window (a
                                      # slotless awaiting-go plan silently never runs).
                                      # sun-attended is the ONLY allow_reboot window.
                                      # 2026-09-13 is already committed (95 min booked,
                                      # see conflicts_with) and 2026-09-20 is contested
                                      # (see §"open items" #2). THE SCHEDULER/OPERATOR
                                      # MAY MOVE THIS — pull it earlier by clearing a
                                      # sun-attended slot of every other plan (§6);
                                      # this plan needs the slot exclusively.
sops_refs:
  - docs/sops/talos-upgrade.md
  - docs/sops/application-update.md
  - docs/sops/longhorn.md
  - docs/sops/storage-safety.md
  - docs/sops/backup.md
  - docs/sops/disaster-recovery.md
  - docs/sops/envoy-gateway-upgrade.md
  - docs/sops/monitoring.md
generated: "2026-09-09"
---

# Talos Linux node roll — v1.13.10 → v1.14.0

## 1) Summary & why held

Roll all three control-plane/worker nodes (`k8s-nuc14-01/02/03`, 192.168.55.11-.13,
VLAN 55) from Talos **v1.13.10** to **v1.14.0**, one node at a time, with a Longhorn
replica-rebuild gate between nodes. Kubernetes stays pinned at **v1.36.0** — this
window does **not** bump `kubernetesVersion`.

Held because it is the definition of a held update: it reboots every node in the
cluster. It is also the last untracked major-ish item in the queue, and it stayed
invisible for a specific, fixable reason recorded below.

### ATTRIBUTION — the correction this plan carries (F-9a58f400)

Two different artifacts have been conflated. They are not the same thing and they
do not move at the same time.

| | Artifact | What it is | Renovate | Reboot? |
|---|---|---|---|---|
| **A** | `kubernetes/bootstrap/talos/talconfig.yaml` → `talosVersion: v1.13.10` | **THE NODE IMAGE.** Feeds `talhelper gencommand upgrade`, which installs `factory.talos.dev/installer/<schematic>:<version>` on each node. | **No PR. Renovate-untracked.** | **YES — 3 reboots** |
| **B** | `.mise.toml` → `"aqua:siderolabs/talos" = "1.13.10"` | The **talosctl CLI** binary installed locally by mise/aqua on this Mac. Touches no node, no manifest, no cluster object. | **PR #212** (`feat(github-release): update aqua:siderolabs/talos ( 1.13.10 → 1.14.0 )`) | **No** |

`runbooks/auto-update-policy.yaml` lines 206-209 deny `siderolabs/*` with the reason
*"Talos node image — needs a rolling node-reboot maintenance window, not a git merge."*
That glob matches the dependency **name**, not the Renovate manager, so it also
catches **B** and labels a local developer binary as node work. The hold on #212 is
the right outcome for the wrong reason; the node image, which genuinely needs this
window, was never held at all because it never produced a PR.

**Verified why the node image produces no PR — and why it never will again.**
`talconfig.yaml` line 3 carries `# renovate: datasource=docker depName=ghcr.io/siderolabs/installer`,
which the `customManagers` regex in `.github/renovate.json5` does match. But the
v1.14.0 release notes state: *"The default installer image has been updated to use the
Image Factory. The `ghcr.io/siderolabs/installer` image is no longer published with
releases."* Measured 2026-09-09, with a negative control so the check can fail:

```
ghcr.io/siderolabs/installer:v1.13.10  -> HTTP 200
ghcr.io/siderolabs/installer:v1.14.0   -> HTTP 404
ghcr.io/siderolabs/installer:v9.9.9    -> HTTP 404   (control — proves 404 is real)

factory.talos.dev/installer/43b3cbfc…99a3:v1.13.10 -> HTTP 200
factory.talos.dev/installer/43b3cbfc…99a3:v1.14.0  -> HTTP 200   <- our schematic IS published
factory.talos.dev/installer/43b3cbfc…99a3:v9.9.9   -> HTTP 404   (control)
```

So Renovate's docker datasource sees no v1.14.0 for that repository and correctly
emits nothing. **This is permanent** — the annotation points at a registry that has
stopped receiving Talos releases. §3.1 repoints it, which is the durable fix for the
invisibility F-fc435c71 is about. `git ls-remote --heads origin | grep renovate`
returns only `renovate/aqua-siderolabs-talos-1.x` and `renovate/n8nio-n8n-2.x`: there
is no node-image branch, confirming this is not a rate-limit or a stale scan.

**#212's disposition is decided, and it is not "close it".** The finding record's own
detail says the file's stated policy — *"CLI pin — track the CLUSTER, not Renovate"* —
is satisfied by **merging #212 as a step of this plan, after the nodes are on
v1.14.0**. That is §3.6. Do not merge it in Phase A: a v1.13.10 client is exactly the
right client for driving a v1.13.10 → v1.14.0 upgrade (Talos supports n±1, and the
older client is the normal direction), and bumping it early would put the pin ahead of
the cluster, which is the drift the comment exists to prevent.

### What in v1.14.0 makes this non-trivial

Read against the actual v1.14.0 release notes, for a cluster **upgraded** (not newly
created). The distinction matters — several of the loudest changes are opt-in and do
**not** apply to us.

**Genuinely changes behaviour on upgrade:**

1. **etcd 3.6.14 → 3.7.x.** *"Talos is now compatible with etcd v3.6.x only … The
   default version is 3.7.0+ now."* We are on **3.6.14** (measured), so the
   prerequisite holds. This is also the single biggest reason `rollback_class` is
   `one-way`: once a majority of members have advanced, unwinding is a snapshot
   restore, not a revert.
2. **etcd HTTP endpoints move `2379` → `2383`.** *"etcd metrics and the HTTP health
   endpoint are no longer reachable on 2379; scrape them on 2383 instead."*
   **This does not hit us, and §4 proves it rather than assuming it.** Talos runs etcd
   with a dedicated `--listen-metrics-urls` on **2381**, and the release note says
   *"If `--listen-metrics-urls` was customized, the metrics should not move."*
   Verified live: `kube-prometheus-stack-kube-etcd` endpoints are
   `192.168.55.11:2381,.12:2381,.13:2381`, all three targets `up`.
3. **containerd NRI is no longer disabled by default.** A plugin interface that was
   off is now on. Nothing in this cluster registers an NRI plugin today, so the
   expected effect is nil — but it is a default flip on the container runtime and is
   why `capability_change: true`.
4. **`net.ipv4.conf.{all,default}.send_redirects=0` by default.** These nodes are not
   L3 gateways (the UDM-Pro at 192.168.55.1 is), so no impact expected.
5. **etcd and kube-apiserver now require TLS ≥ 1.3**, and custom cipher-suite settings
   are ignored. `talconfig.yaml` sets no cipher suites, so nothing to unwind.
6. **`--mode=reboot` removed from `talosctl apply-config`.** Our
   `.taskfiles/Talos/Taskfile.yaml` `apply-node` task uses `--mode={{.MODE}}` defaulting
   to `auto`. Unaffected — but do not hand-type `--mode=reboot` with a 1.14 client.
7. **CoreDNS moves with the release** (1.14.7 in v1.14.0) for the Talos-bundled
   manifest. The cluster additionally runs its own CoreDNS HelmRelease; unchanged here.

**Opt-in, and this plan deliberately does NOT opt in:**

8. **Workload isolation (`sandboxd`).** The container runtime plane moves into a
   dedicated PID/mount namespace. The notes are explicit: *"Clusters upgraded from
   older versions do not have this document and therefore keep the previous
   (non-isolated) behavior until it is added — upgrades change nothing on their own."*
   **DO NOT add a `SecurityProfileConfig` document in this window.** The same notes
   warn: *"With workload isolation enabled, the deprecated in-tree Kubernetes iSCSI
   volume plugin does not work (the kubelet cannot reach the host `iscsid` across the
   sandbox)."* This cluster's storage is 93 Longhorn volumes over iSCSI. Longhorn uses
   its own CSI driver (which the note says is the supported path), but flipping a
   node-isolation boundary underneath the iSCSI stack in the same window as a version
   roll would make any storage failure undiagnosable. Separate plan, separate window,
   or never.
9. **`FilesystemTrimConfig`** — absent on upgraded clusters, so periodic fstrim stays
   off. We already run explicit `*-filesystem-trim` CronJobs in `storage`. Leave it.
10. **Multi-document config migration** (`SysctlConfig`, `UdevRulesConfig`,
    `KubeNodeConfig`, `UnattendedInstall`, …). Every v1alpha1 field this repo uses is
    **deprecated but still supported**. **Do not migrate any of it in this window.**
    A config-shape migration and a node roll must not fail together.

### The tooling constraint that gates the whole plan

**`talhelper` is end-of-life.** Release **v3.1.17 (2026-08-26)** says: *"This will be
the last release of Talhelper."* The repo pins **3.1.11**. Measured against a scratch
copy of `talconfig.yaml` with `talosVersion: v1.14.0`:

```
$ talhelper validate talconfig talconfig.yaml
There are issues with your talhelper config file:
field: "talosVersion"
  * WARNING: "v1.14.0" might not be compatible with this Talhelper version you're using
(exit 0)
```

Cause, confirmed from talhelper's `go.mod`: 3.1.11 embeds
`siderolabs/talos/pkg/machinery v1.14.0-alpha.1`; the last release, 3.1.17, embeds
`v1.14.0-alpha.2`. Neither embeds the v1.14.0 **GA** machinery, so the warning fires on
the version string and **no talhelper release will ever clear it**. The warning is not
a blocker (exit 0, and the alpha machinery already understands the 1.14 contract for
the v1alpha1 fields we use), but it means **talhelper is not the validator here — the
canary node is.** §3.4 reviews the generated diff by hand and §4.1 gates on node 01
actually booting. Bump the pin to 3.1.17 in Phase A so we are on the final release, and
expect the warning to persist.

## 2) Pre-checks

Run all of these **inside the window, before touching a node**. Every one has a stated
pass condition; a fail is a no-go, not a note.

```bash
cd /Users/mu/code/cberg-home-nextgen
export KUBECONFIG="$PWD/kubeconfig"
export TALOSCONFIG="$PWD/kubernetes/bootstrap/talos/clusterconfig/talosconfig"
```

**2.1 — No other plan is mid-flight.** This window is exclusive.

```bash
python3 runbooks/maintenance-plan.py --open
```
**PASS:** no other plan carries this window's id. If `absenty-drop-npm-runtime` or
`authentik-pg18-lockstep` is still assigned to this slot, **stop** — the slot must be
cleared first (§6).

**2.2 — Nodes healthy and all on v1.13.10.**

```bash
kubectl get nodes -o wide
```
**PASS:** 3× `Ready`, `Talos (v1.13.10)`, kubelet `v1.36.0`.
*(Baseline 2026-09-09: kernel `6.18.48-talos`, containerd `2.2.7`.)*

**2.3 — etcd quorum, and confirm we are on 3.6.x (the v1.14 prerequisite).**

```bash
mise exec -- talosctl -n 192.168.55.11 etcd members
mise exec -- talosctl -n 192.168.55.11,192.168.55.12,192.168.55.13 etcd status
```
**PASS:** exactly 3 members, no `LEARNER`, empty `ERRORS`, identical `RAFT INDEX`
across all three (they may differ by a few — they must not diverge by thousands), and
`PROTOCOL` reporting **3.6.x**.
*(Baseline: 3.6.14, leader `73a201c6b4bf6faf` = `k8s-nuc14-03`, DB ~800 MB / 187 MB in
use, raft term 60.)* **If `PROTOCOL` is not 3.6.x, STOP** — v1.14 states compatibility
with 3.6.x only.

**2.4 — Record the roll order inputs.** The order is a rule, not a hardcode (§3.5).

```bash
# VIP owner (192.168.55.10) — must be the LAST node rolled
for ip in 192.168.55.11 192.168.55.12 192.168.55.13; do
  echo -n "$ip vip=" ; mise exec -- talosctl -n $ip get addresses 2>/dev/null | grep -c '192.168.55.10/32'
done
# Longhorn load per node
kubectl get volumes -n storage -o custom-columns=NODE:.status.currentNodeID --no-headers | sort | uniq -c
```
**PASS:** exactly one node reports `vip=1`. *(Baseline 2026-09-09: VIP on
`k8s-nuc14-02`; attached volumes 01=13, 02=47, 03=34.)*

**2.5 — Longhorn: every volume healthy, replica counts as expected.**

```bash
kubectl get volumes -n storage -o json | python3 -c "
import sys,json,collections
d=json.load(sys.stdin)['items']
bad=[(v['metadata']['name'],v['status'].get('robustness'),v['status'].get('state')) for v in d
     if v['status'].get('robustness')!='healthy']
print('total',len(d),'not-healthy',len(bad))
for b in bad: print(' ',b)
print('replica counts:',collections.Counter(v['spec'].get('numberOfReplicas') for v in d))"
```
**PASS:** every volume `healthy`. **There are no known exceptions as of
2026-09-11** — the two retained Superset rollback volumes that used to sit here
(`superset-postgresql-data`, `superset-pg-data`) were reclaimed by plan
`superset-pg-decommission` (`06c954d2`), so the live reading is 93/93 `healthy`
with zero detached. **Any** non-healthy or detached volume is now a no-go; do not
carry an exception forward without re-deriving it from live state.

Longhorn only computes `robustness` while a volume is attached, so `unknown` on a
deliberately-detached volume is the expected reading, not a fault. Confirm each has
its full replica count with no `failedAt` if you want positive evidence.

Any *other* non-healthy volume is a no-go.

> **Keep this list current when a rollback datastore is retired.** Every such
> retirement adds a permanently-detached volume; if the list is not updated the gate
> false-fails, and a gate that cries wolf gets waved through on the one occasion it
> is real.

**PASS also:** `replica counts: Counter({2: 93})`. **This is the number that sizes the
gate.** At `numberOfReplicas: 2` across 3 nodes, taking one node down leaves a large
share of volumes running on a single replica — degraded but serving. There is no
spare-replica cushion. Do not proceed on a cluster that is already degraded.

**2.6 — Backups fresh.** `docs/sops/backup.md` warns `lastBackupAt` can lag one cycle.

```bash
kubectl get jobs -n storage --sort-by=.status.startTime | grep daily-backup-all-volumes | tail -1
kubectl get volumes -n storage -o json | python3 -c "
import sys,json,datetime
now=datetime.datetime.now(datetime.timezone.utc); stale=[]
for v in json.load(sys.stdin)['items']:
    lb=v['status'].get('lastBackupAt') or ''
    if not lb: stale.append((v['metadata']['name'],'NEVER')); continue
    h=(now-datetime.datetime.fromisoformat(lb.replace('Z','+00:00'))).total_seconds()/3600
    if h>48: stale.append((v['metadata']['name'],f'{h:.0f}h'))
print('stale(>48h) or never:',len(stale))
for s in stale: print(' ',s)"
```
**PASS:** the most recent `daily-backup-all-volumes-*` Job is `Complete` within 24h
(the CronJob runs `0 3 * * *`, so a 09:00 window sees a ~6h-old backup), and the stale
list is **empty** — since the 2026-09-11 Superset volume reclaim (`06c954d2`)
every volume is attached and snapshotted. Any stale volume is a no-go.

**2.7 — Flux fully green.** A reconcile landing mid-roll is a confounder.

```bash
mise exec -- flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
mise exec -- flux get helmreleases   -A | awk 'NR==1 || $5 != "True"'
```
**PASS:** both print only the header row.

**2.8 — Observability baseline. Write these three numbers down** — §4.4 diffs against
them.

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9099:9090 >/dev/null 2>&1 &
sleep 4
curl -s localhost:9099/api/v1/alerts | python3 -c "
import sys,json
a=[x for x in json.load(sys.stdin)['data']['alerts'] if x['state']=='firing'
   and x['labels'].get('alertname') not in ('Watchdog','InfoInhibitor')]
print('firing:',len(a),[x['labels'].get('alertname') for x in a])"
curl -s localhost:9099/api/v1/targets | python3 -c "
import sys,json
t=json.load(sys.stdin)['data']['activeTargets']
print('targets',len(t),'up',sum(1 for x in t if x['health']=='up'))
print('etcd:',[(x['labels'].get('instance'),x['health']) for x in t if 'etcd' in x['labels'].get('job','')])"
curl -s localhost:9099/api/v1/rules | python3 -c "
import sys,json; g=json.load(sys.stdin)['data']['groups']
print('groups',len(g),'rules',sum(len(x['rules']) for x in g))"
kill %1 2>/dev/null
```
**PASS / baseline measured 2026-09-09:** `firing: 0` · `targets 99 up 99` ·
`etcd: all three on :2381 up` · `groups 115 rules 463`.

**2.9 — Envoy Gateway is the only HTTP data plane. Record its pre-state.**

```bash
kubectl get gateway -A
kubectl get httproute -A --no-headers | wc -l
kubectl get pods -n network -o wide | grep -E 'envoy-(internal|external|gateway)'
```
**PASS:** `envoy-internal` (192.168.55.103) and `envoy-external` (192.168.55.104) both
`PROGRAMMED=True`; **103** HTTPRoutes; and — the load-bearing one — **each of
`envoy-internal`, `envoy-external` and `envoy-gateway` has 3 replicas, one per node.**
That is what makes a one-node-at-a-time roll survivable: two of three stay up
throughout. If any of those Deployments is down to fewer than 3 healthy pods spread
across ≥2 nodes, **stop** — there is no fallback controller. ingress-nginx was deleted
2026-09-07 (`ad1ea7c2`); do not look for one.

**2.10 — Longhorn instance-manager PDBs.**

```bash
kubectl -n storage get pdb | grep instance-manager
kubectl -n storage get pods -l longhorn.io/component=instance-manager -o wide
```
**PASS:** exactly 3 PDBs, each with a live pod, one per node.
**`ALLOWED DISRUPTIONS = 0` on all three is the correct steady state, not a fault** —
each PDB selects exactly one pod with `minAvailable: 1`, so the arithmetic is always 0
(`docs/sops/talos-upgrade.md` §9). Do not delete them. Do not reach for `--drain=false`
on the strength of seeing a zero here.

## 3) Steps

### Phase A — PREP, run BEFORE the window (~30 min, zero cluster effect)

**Why this is safe to do early:** `kubernetes/bootstrap/talos/` is **not reconciled by
Flux.** Verified — every Flux Kustomization `spec.path` points under
`./kubernetes/apps` or the flux config dirs; none references `bootstrap`. The
talhelper-generated configs are applied by `talosctl`, by hand. So committing and
pushing a `talosVersion` bump changes **nothing** on the cluster until §3.5 runs
`talosctl upgrade`. Doing prep in-window costs 30 of 150 minutes for no benefit.

**3.1 — Bump the node image and repair the dead Renovate annotation.**

Edit `kubernetes/bootstrap/talos/talconfig.yaml`:

```yaml
# BEFORE
# renovate: datasource=docker depName=ghcr.io/siderolabs/installer
talosVersion: v1.13.10

# AFTER
# renovate: datasource=github-releases depName=siderolabs/talos
# (was datasource=docker depName=ghcr.io/siderolabs/installer — that image stopped
#  being published at v1.14.0; the Image Factory is now the only source, and the old
#  annotation silently produced NO PR for this bump. See plan talos-1.14.0 §1.)
talosVersion: v1.14.0
```

Leave `kubernetesVersion: v1.36.0` **unchanged**. Leave every `talosImageURL`
**unchanged** — the schematic
`factory.talos.dev/installer/43b3cbfc2957259b4588d362709d47387607901d4d3506c1ea46d7ea74cb99a3`
is already published for v1.14.0 (proved in §3.3 with a negative control).

**3.2 — Correct the deny-rule reason text (documentation-only).**

In `runbooks/auto-update-policy.yaml`, the `siderolabs/*` rule's `reason:` currently
claims every match is the node image. Per this directory's `README.md`, a deny rule's
text is the only thing that changes for a `PLAN`-classified item, so this is a text fix
with **no behaviour change** — but it stops the next agent repeating F-9a58f400:

```yaml
  - match: "siderolabs/*"
    reason: >-
      Matches BOTH the Talos node image AND the local talosctl CLI pin
      (.mise.toml aqua:siderolabs/talos) — the glob keys on the dep NAME, not the
      manager. The NODE image lives in kubernetes/bootstrap/talos/talconfig.yaml
      (talosVersion) and needs a rolling node-reboot window. A Renovate PR titled
      'aqua:siderolabs/talos' is the CLI and needs neither. See F-9a58f400.
```

**3.3 — Prove the factory publishes our schematic for the target, WITH a negative
control.** Mandatory per `docs/sops/talos-upgrade.md` §4 Step 1 — that guard exists
because on 2026-09-06 a TLS-intercepting middlebox made this check "pass" for a
nonsense tag.

```bash
SCHEM=43b3cbfc2957259b4588d362709d47387607901d4d3506c1ea46d7ea74cb99a3
for TAG in v1.14.0 v9.9.9; do
  printf "%-10s HTTP %s\n" "$TAG" "$(curl -s -o /dev/null -w '%{http_code}' \
    "https://factory.talos.dev/v2/installer/$SCHEM/manifests/$TAG")"
done
```
**PASS — EXACTLY:** `v1.14.0 -> 200` **and** `v9.9.9 -> 404`.
Control also 200, or both 3xx? You are behind an intercepting proxy; the result is
**invalid**. **Never add `-k`** — that removes the check's ability to fail.
*(Measured 2026-09-09: 200 / 404. Correct.)*

**3.4 — Bump talhelper to its final release, regenerate, and READ THE DIFF.**

```bash
# .mise.toml — talhelper 3.1.11 -> 3.1.17 (the LAST talhelper release, 2026-08-26)
# Do NOT touch "aqua:siderolabs/talos" here — that is §3.6, after the roll.
mise install
mise exec -- talhelper --version          # expect 3.1.17

cd kubernetes/bootstrap/talos
mise exec -- talhelper validate talconfig talconfig.yaml
cd -
mise exec -- task talos:generate-config
git --no-pager diff --stat kubernetes/bootstrap/talos/
```

**Expected `validate` output — this warning is EXPECTED and is not a failure:**
```
field: "talosVersion"
  * WARNING: "v1.14.0" might not be compatible with this Talhelper version you're using
```
It fires because talhelper 3.1.17 embeds machinery `v1.14.0-alpha.2`, not GA. No
talhelper release will ever clear it (the project is EOL). Exit code is 0.

**Now read the generated diff by hand. This is the real gate, because talhelper cannot
be it.** The three files under `clusterconfig/` are SOPS-encrypted; diff the decrypted
form:

```bash
for n in 01 02 03; do
  echo "=== nuc14-$n ==="
  mise exec -- sops -d kubernetes/bootstrap/talos/clusterconfig/kubernetes-k8s-nuc14-$n.yaml \
    > /tmp/new-$n.yaml
  git show HEAD:kubernetes/bootstrap/talos/clusterconfig/kubernetes-k8s-nuc14-$n.yaml \
    | mise exec -- sops -d /dev/stdin > /tmp/old-$n.yaml
  diff -u /tmp/old-$n.yaml /tmp/new-$n.yaml
done
```

**PASS:** the only differences are the `machine.install.image` tag `v1.13.10 → v1.14.0`
and the config version-contract stamp.
**STOP AND INVESTIGATE** if the diff shows any of: a new `SecurityProfileConfig`
document (that is workload isolation — §1 item 8, must NOT appear), a new
`UnattendedInstall` document replacing `machine.install`, `machine.sysctls` /
`machine.udev.rules` / `machine.kubelet` rewritten into `SysctlConfig` /
`UdevRulesConfig` / `KubeNodeConfig` documents, or any **removed** field. Alpha
machinery emitting a GA-era document shape is exactly the failure this step exists to
catch. If it appears, do not "fix it up" in-window — abort Phase A and reschedule.

Then `rm -f /tmp/old-*.yaml /tmp/new-*.yaml` (they hold decrypted cluster secrets).

**3.5 — Commit and push (still zero cluster effect).**

Per `CLAUDE.md`, use `--only` with explicit paths — the worktree is shared.

```bash
cat > /tmp/talos-msg.txt <<'EOF'
feat(talos)!: node image v1.13.10 -> v1.14.0 (config only; roll is manual)

Bumps talosVersion in talconfig.yaml and regenerates the three SOPS-encrypted
node configs. Flux does not reconcile kubernetes/bootstrap/talos/, so this
commit changes nothing until `task talos:upgrade-node` runs in the window.

Also repoints the Renovate annotation from ghcr.io/siderolabs/installer (which
stopped publishing at v1.14.0 — the Image Factory is now the only source) to
github-releases/siderolabs/talos. The dead annotation is why this bump produced
no PR and stayed invisible: F-fc435c71.

Corrects the siderolabs/* deny-rule reason text, which attributed the local
talosctl CLI pin to the node image: F-9a58f400. No behaviour change.

Plan: runbooks/maintenance/plans/talos-1.14.0.md
Findings: F-912f4778, F-fc435c71, F-9a58f400
EOF

git commit --only \
  kubernetes/bootstrap/talos/talconfig.yaml \
  kubernetes/bootstrap/talos/clusterconfig/ \
  runbooks/auto-update-policy.yaml \
  .mise.toml \
  -F /tmp/talos-msg.txt

git show --stat HEAD        # every file here MUST be one of the four above
git push
```

### Phase B — THE ROLL (in-window)

**Concurrency rule, absolute: exactly ONE node down at a time.** All three nodes are
etcd members; a 3-member cluster tolerates the loss of exactly one. Two down = quorum
lost = the API server is gone and the roll cannot be driven. There is no step in this
plan where two nodes are unavailable, and no circumstance in which "just do the last
two together to save time" is acceptable.

**3.5 — Roll order.** Stated as a **rule** with today's measured assignment; re-derive
from §2.4 at window time in case the VIP or load has moved.

| Rule | Node (measured 2026-09-09) | Why |
|---|---|---|
| **1st — CANARY**: lightest Longhorn load, and holds neither the VIP nor etcd leadership | **`k8s-nuc14-01` / 192.168.55.11** (13 attached, 60 replicas, no VIP, not leader) | Smallest state to move, so the fastest, cleanest first reboot. If v1.14 is bad we learn it while the API endpoint (VIP on 02) and etcd leadership (03) are both untouched. **This is the go/no-go for the other two nodes.** |
| **2nd**: mid load | **`k8s-nuc14-03` / 192.168.55.13** (34 attached, 62 replicas, current etcd **leader**) | Leadership re-election is expected and normal here; it happens once, on a node that has a healthy v1.14 peer already proven. |
| **3rd — LAST**: the VIP owner, heaviest load | **`k8s-nuc14-02` / 192.168.55.12** (47 attached, 72 replicas, **holds VIP 192.168.55.10**) | Heaviest drain goes last so the API endpoint moves exactly once, at the end, after two nodes have proven v1.14. If the budget runs out here, stopping with 2/3 on v1.14 is a supported transient. |

For each node, in that order, run **3.5a → 3.5b → 3.5c** to completion before starting
the next.

**3.5a — Upgrade one node.**

```bash
mise exec -- task talos:upgrade-node IP=<node-ip>
```

This installs the new image, then cordons, drains, and reboots. Expect it to sit on
`evicting pod storage/instance-manager-<hash>` for a while. **That is normal.** Per
`docs/sops/talos-upgrade.md` §9: the drain waits for Longhorn volumes to **detach**, not
for a stuck PDB. Watch the engine count fall:

```bash
kubectl -n storage get engines.longhorn.io -o json | python3 -c "
import sys,json
print(len([e for e in json.load(sys.stdin)['items'] if e['spec'].get('nodeID')=='<node-name>']))"
```
Engines going N → 0 (~75s observed on the 2026-08-16 roll) is the drain progressing.
When it hits 0, Longhorn deletes the PDB itself and the drain completes in seconds.

**Do NOT** delete the PDBs. **Do NOT** use `EXTRA_FLAGS='--drain=false'` pre-emptively.
Only if the drain **times out** with
`error when waiting for pod "instance-manager-…" to terminate: context deadline exceeded`
(the load-dependent recreate race documented in the SOP): **uncordon the node first**,
then delete the `Pending` pods so the scheduler spreads the attach load. Do not wait it
out — it does not self-resolve. `--drain=false` is a last resort and never unattended.

**3.5b — Node health gate.**

```bash
kubectl get nodes -o wide
mise exec -- talosctl -n <node-ip> version --short
mise exec -- talosctl -n 192.168.55.11,192.168.55.12,192.168.55.13 etcd status
```
**PASS, all of:** the node is `Ready` and **not** `SchedulingDisabled`; `Tag: v1.14.0`;
etcd reports **3 members**, no `LEARNER`, empty `ERRORS`, and raft indexes converged.
Do not proceed to 3.5c until etcd shows three healthy members — a node that is `Ready`
but whose etcd member has not rejoined is a quorum of two, and the next node would take
it to one.

**3.5c — THE LONGHORN GATE. This is the step that blows the time budget.**

Do **not** start the next node until this passes. With `numberOfReplicas: 2` there is no
cushion: starting the next node while volumes are still degraded means volumes running
on **zero** replicas.

```bash
kubectl get volumes -n storage -o json | python3 -c "
import sys,json,collections
d=json.load(sys.stdin)['items']
bad=[(v['metadata']['name'],v['status'].get('robustness'),v['status'].get('state'))
     for v in d if v['status'].get('robustness') not in ('healthy',)]
print('NOT-HEALTHY:',len(bad))
for b in bad: print('  ',b)
print('robustness:',collections.Counter(v['status'].get('robustness') for v in d))"

kubectl get replicas.longhorn.io -n storage -o json | python3 -c "
import sys,json,collections
rs=json.load(sys.stdin)['items']
c=collections.Counter((r['spec'].get('nodeID','?'), r['status'].get('currentState','?')) for r in rs)
for k,v in sorted(c.items()): print(k,v)
print('total replicas',len(rs))"
```

**PASS — all three conditions, together:**
1. `NOT-HEALTHY … : 0` — every volume is `healthy`.
   Not `degraded`, not `rebuilding`. `degraded` means one replica; that is exactly the
   state we must not enter the next reboot in.
2. The just-rebooted node appears again in the replica table with a **`running`** count
   in the same order as before the reboot (baseline 2026-09-09: 01≈55-60, 02≈71-72,
   03≈62 running; a handful of `stopped` is normal — 01 had 5, 02 had 1 — those are
   replicas of detached volumes).
3. `total replicas` is back at ≈**194**.

**Why this can run long, and what to do about it.** `replica-replenishment-wait-interval`
is **600s**, so Longhorn waits 10 minutes before replenishing a missing replica
elsewhere. If the node returns inside that window (typical), replicas restart in place
and rebuild incrementally — fast. If the reboot overruns 10 minutes, Longhorn starts
building **full** replicas on the surviving nodes and the gate can take far longer, on
94 attached volumes. `concurrent-replica-rebuild-per-node-limit` is 8 and
`replica-rebuild-concurrent-sync-limit` is `{"v1":"1"}`, so it is deliberately paced.

**Budget rule: if the gate has not passed 25 minutes after the node returned `Ready`,
stop rolling.** Do not skip the gate, do not shorten it, do not start the next node.
Leave the cluster part-rolled (a supported transient), finish §4.4 whole-cluster
verification on the current mix, and reschedule the remainder for the next
reboot-capable window. A part-rolled cluster is fine; a cluster with volumes on zero
replicas is not.

**3.6 — Merge PR #212 (the talosctl CLI pin) — LAST, and only after all three nodes
report v1.14.0.**

This is the **other** artifact from §1, and the finding record's recorded disposition:
*"hold #212 until the node roll executes, then merge it inside that plan."* The
`.mise.toml` comment states the policy this satisfies — *"CLI pin — track the CLUSTER
… not Renovate."* Merging earlier would put the pin ahead of the cluster.

```bash
kubectl get nodes -o wide | grep -c 'Talos (v1.14.0)'   # MUST be 3 before proceeding
gh pr checks 212
gh pr merge 212 --squash
git pull
mise install
mise exec -- talosctl version --short                   # Client: Talos v1.14.0
```
**PASS:** client reports `v1.14.0`, and `talosctl -n <any> version --short` still talks
to the nodes.

**If fewer than 3 nodes reached v1.14.0, do NOT merge #212.** Leave it open; it is the
correct state for a part-rolled cluster, and re-opening it later is worse than leaving
it.

**Explicitly NOT in this window:** `task talos:upgrade-k8s`. Kubernetes stays on
v1.36.0. Talos v1.14.0 ships Kubernetes 1.37.0 as its default, and v1.36.0 is inside
Talos's supported range — **confirm this against the v1.14 support matrix during
Phase A** (it could not be machine-read from the docs site while writing this plan;
see §"open items"). A Kubernetes minor bump is its own plan, its own window, its own
`upgrade-k8s` run, and it needs a talosctl client matching the cluster (SOP lesson #6:
`upgrade-k8s` fails across a client/cluster minor boundary).

## 4) Verification

### 4.1 — Per-node, immediately after each node returns (§3.5b + §3.5c above)

Plus, on **every** node as it comes back — the kernel-cmdline check, because
`docs/sops/talos-upgrade.md` lessons #2, #3 and #13 all describe args silently
disappearing across an upgrade (KSPP filtering, `grubUseUKICmdline`, and one node
booting an older install):

```bash
mise exec -- talosctl read /proc/cmdline -n <node-ip> \
  | tr ' ' '\n' | grep -E 'hugepages|i915|intel_iommu|mitigations|init_on_alloc'
mise exec -- talosctl read /proc/meminfo -n <node-ip> | grep HugePages_Total
```
**PASS:** the same arg set as before the roll, and `HugePages_Total: 1024`. A node
missing them booted from an older install — re-run `task talos:upgrade-node` for that
IP before moving on.

**CANARY GO/NO-GO (after node 01 only).** All of §3.5b, §3.5c and the cmdline check
pass, **and** `kubectl get pods -A --field-selector spec.nodeName=k8s-nuc14-01` shows
pods scheduling and running there again. If any fails: **stop, roll node 01 back
(§5.1), and do not touch nodes 02/03.** This is the one point in the plan with a clean
exit.

### 4.2 — Storage: the iSCSI record trap (run after the LAST node)

Mandatory. On the 2026-08-16 roll this bit node 03 and was nearly missed: the node was
`Ready`, Longhorn reported every volume healthy, and the node could not attach a single
volume — the scheduler just placed everything elsewhere and the cluster **looked**
green.

```bash
kubectl get volumes -n storage -o custom-columns=NODE:.status.currentNodeID \
  --no-headers | sort | uniq -c
```
**PASS:** all three node names appear with a non-trivial count. **A node showing 0 while
the others show dozens is the smoking gun.** If it happens:

```bash
mise exec -- talosctl -n <node-ip> list /var/lib/iscsi/nodes
mise exec -- talosctl -n <node-ip> read /var/lib/iscsi/nodes/<target>/<portal>/default | grep conn_reopen
```
The failing record names a **different** volume than the one in the pod's error — chase
the one in the `config file … invalid` line, and check **all** records, not just the
first (5 of 6 were poisoned last time). Fix is to remove only the unparseable records;
Longhorn recreates them on next attach. **Do not** reboot, drain, or reset the node, and
**do not** delete any PV/PVC/Volume/Replica — it is a host-state file problem.

### 4.3 — CONTENTS ASSERTIONS

Per this directory's README: a health signal that cannot distinguish "working" from
"empty" is not a health signal. Three, because this change has three distinct ways to
fail while looking perfect.

> **CONTENTS ASSERTION 1 (storage — a real read/write round-trip through a mounted
> Longhorn PVC).** Longhorn's own `robustness: healthy` says nothing about whether
> anything can still *use* a volume — §4.2 is the proof that it lies in exactly this
> situation. Measured by: pick a live app with a Longhorn RWO PVC, exec into its pod,
> write a throwaway file, read it back byte-identical, delete it. Then confirm the pod's
> node is one that was rolled. Compared to baseline: the write must succeed on a
> **rolled** node, not merely somewhere in the cluster.
>
> ```bash
> # example shape — substitute a live pod that mounts a longhorn PVC
> POD=<pod>; NS=<ns>
> kubectl -n $NS get pod $POD -o jsonpath='{.spec.nodeName}{"\n"}'   # must be a rolled node
> kubectl -n $NS exec $POD -- sh -c \
>   'echo talos-1.14.0-probe-$$ > /<mountpath>/.probe && cat /<mountpath>/.probe && rm /<mountpath>/.probe'
> ```
> **PASS:** the echoed string comes back identical. An empty read, an I/O error, or a
> read-only filesystem is a FAIL even with every volume `healthy`.

> **CONTENTS ASSERTION 2 (monitoring — the series still arrive, with a floor).**
> Node-level reboots are the classic way to lose a scrape target silently, and v1.14
> moves etcd's HTTP endpoints (2379 → 2383) — our scrape is on 2381 and should be
> unaffected, but "should be" is not an assertion. Measured by: target health **and** a
> representative etcd series returning a non-empty result **over a window that starts
> after the last reboot**. Compared to the §2.8 baseline.
>
> ```bash
> kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9099:9090 >/dev/null 2>&1 &
> sleep 4
> curl -s localhost:9099/api/v1/targets | python3 -c "
> import sys,json
> t=json.load(sys.stdin)['data']['activeTargets']
> print('targets',len(t),'up',sum(1 for x in t if x['health']=='up'))
> for x in t:
>     if x['health']!='up': print('  DOWN',x['labels'].get('job'),x['labels'].get('instance'))"
> # the floor — etcd must still be PRODUCING, not merely 'up'
> curl -s --get localhost:9099/api/v1/query \
>   --data-urlencode 'query=count(count by (instance) (etcd_server_has_leader[10m]))' \
>   | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['result'])"
> curl -s localhost:9099/api/v1/rules | python3 -c "
> import sys,json; g=json.load(sys.stdin)['data']['groups']
> print('groups',len(g),'rules',sum(len(x['rules']) for x in g))"
> kill %1 2>/dev/null
> ```
> **PASS:** `targets 99 up 99` (≥ the baseline; a *smaller* total is a FAIL — a
> disappeared target reads as 100% up), the etcd query returns **3**, and
> `groups 115 rules 463` (±0 — no rule group should vanish across a node roll).
> **A ceiling without a floor is a shape check:** "no targets down" would still be
> green if the etcd job stopped existing. The `count(...[10m])` **is** the floor.

> **CONTENTS ASSERTION 3 (routing — real HTTP through Envoy, not Gateway status).**
> Envoy Gateway has **no fallback controller**; a roll that breaks it is a total loss of
> HTTP routing. `PROGRAMMED=True` is a shape check — a Gateway can be Programmed with an
> empty or stale route table. Measured by: every HTTPRoute `Accepted` **and**
> `ResolvedRefs`, the route **count** matched against the §2.9 baseline of 103, and a
> real request returning real bytes through **both** gateways.
>
> ```bash
> kubectl get gateway -A
> kubectl get httproute -A --no-headers | wc -l      # MUST be 103, not "≥1"
> kubectl get httproute -A -o json | python3 -c "
> import sys,json
> bad=[]
> for r in json.load(sys.stdin)['items']:
>     for p in r.get('status',{}).get('parents',[]):
>         for c in p.get('conditions',[]):
>             if c['type'] in ('Accepted','ResolvedRefs') and c['status']!='True':
>                 bad.append((r['metadata']['namespace'],r['metadata']['name'],c['type'],c.get('reason')))
> print('routes NOT Accepted/ResolvedRefs:',len(bad))
> for b in bad: print('  ',b)"
> # real traffic, both data planes, from the LAN
> curl -sS -o /dev/null -w 'internal %{http_code} %{size_download}B\n' \
>   -H 'Host: echo.${SECRET_DOMAIN}' https://192.168.55.103/ -k
> curl -sS -o /dev/null -w 'external %{http_code} %{size_download}B\n' \
>   -H 'Host: echo.${SECRET_DOMAIN}' https://192.168.55.104/ -k
> ```
> **PASS:** both Gateways `PROGRAMMED=True`; **103** HTTPRoutes; `routes NOT
> Accepted/ResolvedRefs: 0`; and both curls return a 2xx/3xx with a **non-zero body
> size**. A 200 with `0B`, or a route count that quietly dropped to 40, is a FAIL.
> *(Substitute any real ingressed host for `echo.${SECRET_DOMAIN}`; the point is a body,
> not a status line.)*

### 4.4 — Whole-cluster verification (end of window)

```bash
# 1. every node on the target
kubectl get nodes -o wide                      # 3x Ready, Talos (v1.14.0), kubelet v1.36.0

# 2. etcd healthy AND advanced
mise exec -- talosctl -n 192.168.55.11,192.168.55.12,192.168.55.13 etcd status
#    PASS: 3 members, no LEARNER, empty ERRORS, converged raft index, PROTOCOL 3.7.x

# 3. the VIP is owned by exactly one node again
for ip in 192.168.55.11 192.168.55.12 192.168.55.13; do
  echo -n "$ip vip=" ; mise exec -- talosctl -n $ip get addresses 2>/dev/null | grep -c '192.168.55.10/32'
done                                           # PASS: exactly one node reports 1

# 4. no pod left behind
kubectl get pods -A --field-selector status.phase!=Running,status.phase!=Succeeded

# 5. Flux still green (it has been reconciling against a moving cluster all window)
mise exec -- flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
mise exec -- flux get helmreleases   -A | awk 'NR==1 || $5 != "True"'

# 6. Longhorn: §3.5c gate one final time + the §4.2 per-node attach check

# 7. all three CONTENTS ASSERTIONS from §4.3

# 8. alerts back to the baseline — after a settle period, NOT immediately
#    (node-level alerts fire during every reboot and clear on their own)
```
**PASS on 8:** `firing: 0`, matching the §2.8 baseline, sustained for **≥15 minutes**
after the last node returned. Anything still firing at that point is a real regression,
not reboot noise.

**Also run** `mise exec -- talosctl -n <ip> logs sandboxd` on one node — it should be
**absent/empty**, confirming workload isolation was **not** silently enabled (§1 item 8).
If `sandboxd` is running, a `SecurityProfileConfig` document got in; that is out of
scope for this window and must be investigated before the next backup cycle.

## 5) Rollback

**Be honest about this: a Talos node-image upgrade is not a clean revert, and
`rollback_class` is `one-way` for that reason.**

### 5.1 — Per-node rollback (REAL, and it is the canary's abort path)

Talos keeps the previous installed image on the alternate boot partition:

```bash
mise exec -- talosctl get machinestatus -n <node-ip> -o yaml | grep -i image
mise exec -- talosctl rollback --nodes <node-ip>
```
Then re-run §3.5b + §3.5c to confirm the node came back on v1.13.10 with its Longhorn
replicas running.

**This is genuinely reversible, with two hard limits:**
- It is **one boot partition deep.** It returns the node to the image it ran before the
  last upgrade — nothing further back.
- It does **not** unwind cluster-level state.

**Use it at exactly one point: the canary (§4.1). That is the clean exit.** With node 01
rolled back and 02/03 never touched, the cluster is byte-for-byte where it started and
the git commit from §3.5 can simply be reverted (it changed nothing on its own).

### 5.2 — Past the canary: there is no clean revert. Roll forward.

Once **two or more** nodes are on v1.14.0, the etcd cluster has advanced from 3.6.14
toward 3.7.x on a majority of its members. Downgrading a Talos node image does not
downgrade an etcd data directory, so "revert the commit and re-roll" is **not** a
rollback — it is an untested downgrade across an etcd storage-version boundary on a
cluster holding an ~800 MB / 187 MB-in-use database.

**Therefore, past the canary:**
- **Preferred: stop, don't unwind.** A part-rolled cluster (some nodes v1.13.10, some
  v1.14.0) is a **supported transient** — it is what every rolling upgrade passes
  through. Stop where you are, finish §4.4 against the mix, and reschedule the
  remainder. This is the right answer to "we ran out of time" and to most
  "something looks off".
- **If a specific node is broken:** `talosctl rollback` that **one** node (§5.1) and
  leave the rest. Same supported-mixed state.
- **If the cluster itself is broken:** this is **disaster recovery**, not rollback.
  `docs/sops/disaster-recovery.md` + the Longhorn backups verified in §2.6 + an etcd
  snapshot. Do not improvise it inside the window; escalate to the operator.

### 5.3 — Reverting the git commit

The §3.5 commit is inert on its own, so reverting it is safe and does **not** move any
node:

```bash
git revert <sha>                 # restores talosVersion: v1.13.10 + the annotation
mise exec -- task talos:generate-config
git commit --only kubernetes/bootstrap/talos/ -m "Revert Talos v1.14.0 node config"
git push
```
**Confirm the cluster is back** by the state of the *nodes*, never the state of the
repo: `kubectl get nodes -o wide` showing the expected Talos tag on each node, plus
§3.5c (Longhorn) and §4.3 (all three contents assertions). The commit and the cluster
are independent here — a green `git log` proves nothing.

**Do not** revert `.mise.toml`'s `aqua:siderolabs/talos` back below the cluster version
if any node is on v1.14.0: an n-1 client is fine, an n-2 client is not.

## 6) Interference notes

**This plan requires the ENTIRE `sun-attended` window, with no other plan in it.**
That is not a preference. A node roll evicts and reschedules **every pod in the
cluster**, three times. Any other plan running in the same window is verifying its
change against a cluster in motion — and if something breaks, there are two candidate
causes and no way to separate them.

**Live conflict as of 2026-09-09.** `maintenance-plan.py --open` shows
`sun-attended:2026-09-13` already carrying `absenty-drop-npm-runtime` (60 min, vetted)
and `authentik-pg18-lockstep` (35 min, vetted) = **95 min of the 150 already booked**.
That leaves 55 min; this plan needs 140. **They cannot share the slot.** The operator
or window-scheduler must either move both plans off a `sun-attended` date and give this
plan that whole slot, or place this plan in the next fully-empty `sun-attended` slot.
Finding F-fc435c71 reached the same conclusion and named `sun-attended:2026-09-27` as
the first feasible date on that basis. *(Note: F-fc435c71 also cites a `superset-6.1.0`
plan holding 2026-09-20 at 75 min. No such plan file exists in this directory — see
"open items".)*

**Sequencing within the window:** this plan runs **alone**. If the operator insists on
pairing it with something, the only defensible shape is a short, fully-reversible,
storage-untouching plan running **after** §4.4 has completely passed — never before,
never interleaved between nodes.

**Things that must not run concurrently, beyond other plans:**
- **The nightly window's Step 0 safe-update apply.** `sun-attended` is a different
  window, but be aware it fires at 03:30 the same day; verify via §2.7 that its
  reconciles have fully landed before starting.
- **The Longhorn backup CronJob `daily-backup-all-volumes` (`0 3 * * *`)** and the
  `*-filesystem-trim` / `*-snapshot-cleanup` CronJobs (`0 2` / `30 2`). A 09:00 window
  clears all of them, but do not let this plan slip earlier into their path — a backup
  running against volumes whose replicas are rebuilding competes for exactly the
  bandwidth the gate is waiting on.
- **The 04:00-anchored operation sweep.** Same reasoning; it must be finished.
- **Any Longhorn engine/manager upgrade, any StorageClass change, any PVC delete.**
  `docs/sops/storage-safety.md` applies in full; nothing in this plan deletes a PVC and
  nothing in this plan may be extended to.
- **Zigbee/Home Assistant work.** Every node reboot disconnects the SLZB coordinator
  sockets; that noise is expected and must not be diagnosed as a Zigbee fault during
  this window.

**Shared infra this perturbs, and who feels it:**

| Shared thing | Effect | Who notices |
|---|---|---|
| `ingress` (Envoy Gateway) | one of three replicas of each of `envoy-internal`/`envoy-external`/`envoy-gateway` down per node | **every ingressed app** (103 HTTPRoutes) — brief connection resets; **no fallback controller exists** |
| `etcd` | one member down per node; leadership re-elects on the 03 step; 3.6→3.7 | whole control plane; API blips |
| VIP 192.168.55.10 | fails over once, on the final node | anything using the kubeconfig endpoint, incl. this session |
| `storage/longhorn` | instance-manager restart + replica rebuild ×3 | every stateful app; the databases in particular |
| `cni/cilium` | DaemonSet pod restart per node | all pod networking, briefly |
| `coredns` | Talos-bundled version moves | cluster DNS, briefly |
| `cert-manager` | webhook pods reschedule | any Certificate reconcile that lands mid-roll |
| `monitoring` | scrape gaps + node alerts during each reboot | expected; §4.4 waits 15 min before judging |

## 7) Risk and duration against the 150-minute slot

**Risk: `high`.** Not because v1.14.0 looks dangerous — the breaking changes that matter
are opt-in and this plan declines them — but because the blast radius is the whole
cluster and there is no clean rollback past the first node. `needs_reboot: true` and
`capability_change: true` both hold, so this is operator-present, reboot-capable,
`sun-attended` only.

**Duration: 140 min in-window, against a 150-min slot. It fits — but only with Phase A
done beforehand, and the margin is 10 minutes.**

| Phase | Min | Basis |
|---|---:|---|
| **A — prep (BEFORE the window)** | **~30** | *Not counted in `est_duration_min`.* Flux does not reconcile `kubernetes/bootstrap/talos/` (verified), so §3.1-§3.5 are inert until `talosctl upgrade` runs. |
| §2 pre-checks | 15 | 10 checks, several with per-node loops |
| Node 01 — canary: upgrade + drain + reboot + §3.5b + §3.5c gate + §4.1 + canary go/no-go | 35 | lightest node (13 attached, 60 replicas); includes the extra canary verification the other two skip |
| Node 03 — upgrade + gate | 30 | 34 attached / 62 replicas |
| Node 02 — upgrade + gate; heaviest, plus the VIP failover | 40 | 47 attached / 72 replicas |
| §4.2 + §4.4 whole-cluster verification (incl. the 15-min alert settle) | 20 | overlaps the settle wait |
| **In-window total** | **140** | **10 min margin in a 150-min slot** |

**Honesty about the fit, three ways:**

1. **This does not fit if Phase A runs in-window.** 140 + 30 = **170 > 150**. If prep
   has not been done and pushed before the window opens, the correct call is to
   **abort and reschedule**, not to compress the pre-checks or the Longhorn gate.
2. **The 10-minute margin is thin and the gate is the thing that eats it.** The window's
   own YAML comment sizes a 3-node roll at 115 min and calls the Longhorn rebuild gate
   "the step most likely to run long on 94 volumes" — and that was written before the
   `numberOfReplicas: 2` measurement, which removes any spare-replica cushion. The
   25-minute per-gate budget rule in §3.5c exists precisely so an over-run becomes a
   deliberate *stop*, not an over-run window.
3. **Stopping part-way is a designed outcome, not a failure.** A mixed
   v1.13.10 / v1.14.0 cluster is a supported transient. If the budget goes, stop after
   whichever node just passed its gate, run §4.4 against the mix, and take the rest next
   window. Do **not** trim the estimate to make three nodes fit — that is how a gate
   gets skipped.

## Open items — could not be determined read-only

1. **Talos v1.14 ↔ Kubernetes support matrix.** v1.14.0 ships k8s 1.37.0 and Talos's
   documented window is the shipped minor plus the prior few, which puts our pinned
   **v1.36.0** comfortably inside — but the docs site renders the matrix in JavaScript
   and it could not be machine-read while writing this. **Confirm it in Phase A** before
   committing the bump.
2. **`superset-6.1.0`.** F-fc435c71 cites it as holding `sun-attended:2026-09-20` for
   75 min, but no plan file with that `plan_id` exists in this directory and
   `maintenance-plan.py --open` does not list it. Either the finding is stale or the
   plan was never written. The window-scheduler should resolve this before choosing a
   date — it changes which slots are actually free.
3. **`talhelper genconfig` output diff for v1.14.0** was reasoned about, not executed:
   running it writes SOPS-encrypted node configs into the repo, which is outside this
   agent's write boundary. §3.4 makes reviewing that diff an explicit, gated step with
   a named list of things that must **not** appear.
4. **Node-reboot duration on v1.14 specifically.** The 30-40 min per-node figures are
   extrapolated from the 2026-08-16 v1.13.8 roll and today's measured per-node Longhorn
   load. v1.14 adds `sandboxd` to the boot path even when workload isolation is off;
   whether that changes boot time is unmeasured. The canary node is where this becomes
   a fact — time it, and re-plan nodes 03/02 from the measurement rather than from this
   table.
