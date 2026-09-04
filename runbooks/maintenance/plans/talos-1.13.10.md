---
plan_id: talos-1.13.10
component: Talos Linux              # MUST equal the version-check's component
                                    # string exactly — coverage.py keys a plan
                                    # solely on this field and the held item
                                    # reports "Talos Linux". Do not shorten.
pr: 208                             # ghcr.io/siderolabs/installer v1.13.8 -> v1.13.10.
                                    # Deliberately NOT merged as a git bump: the
                                    # installer tag is consumed by talconfig.yaml's
                                    # renovate comment, and the actual roll is a
                                    # talosctl upgrade operation. Recorded so the
                                    # plan<->held matcher's PR tier binds them.
                                    # NB: PR #212 (aqua:siderolabs/talos 1.13.4 ->
                                    # 1.14.0) is the LOCAL CLI, a different thing —
                                    # see §7.
kind: os
current: "talosVersion v1.13.8 on all 3 nodes (k8s-nuc14-01/02/03), kubelet v1.36.0, kernel 6.18.42-talos"
target: "talosVersion v1.13.10"
update_type: patch
risk: medium                        # patch content, but it reboots every node of a
                                    # 3-node hyper-converged cluster carrying 94
                                    # attached Longhorn volumes
est_duration_min: 70                # PART 1 = 2 nodes only: 10 pre-checks + 2 x (25-35) +
                                    # 10 final verification = ~70-90, inside the 90-min slot.
                                    # The full 3-node figure was 110 and did NOT fit; it was
                                    # never shaved — the SCOPE shrank. Node 01 carries its own
                                    # ~45 min in part 2. Original note follows:
                                    # 25-35 min per node incl. replica rebuild,
                                    # + 10 pre-checks + 10 final verification.
                                    # EXCEEDS the 90-min sun-attended slot — see §6.
needs_reboot: true                  # 3 sequential node reboots
capability_change: false            # patch line; no new user-visible behaviour
rollback_class: one-way             # node-image roll-forward. `talosctl rollback`
                                    # is ANOTHER reboot into the previous image,
                                    # not a git revert and not a restore. See §5.
touches:
  namespaces: [all]                 # every workload is rescheduled as nodes cycle
  resources:
    - node/k8s-nuc14-01
    - node/k8s-nuc14-02
    - node/k8s-nuc14-03
    - kubernetes/bootstrap/talos/talconfig.yaml
    - kubernetes/bootstrap/talos/clusterconfig/
  shared: [longhorn, cilium, coredns, ingress, etcd]
                                    # Longhorn detach/rebuild on every reboot;
                                    # cilium agent restarts per node; coredns and
                                    # every ingressed app briefly reschedule;
                                    # etcd loses one of three members per node.
depends_on: []
conflicts_with:                     # real plan_ids only (verified against
                                    # `grep -h '^plan_id:' runbooks/maintenance/plans/*.md`)
  - bitnamilegacy-exit-nextcloud-db
  - bitnamilegacy-exit-paperless-db
  - paperless-db-12.3.3
  - superset-pg-cutover
  - superset-6.1.0
                                    # All five move or rewrite data on Longhorn
                                    # PVCs. A node reboot mid-dump/restore is an
                                    # incident, and their rebuild traffic competes
                                    # with ours. The general rule (§6): NOTHING
                                    # with `shared: [longhorn]` or a storage-
                                    # namespace resource shares this window.
                                    # (The previous plan named
                                    # `longhorn-1.12.1-engine`, which is not a
                                    # plan_id in this directory and never was —
                                    # a dead reference the interference guard
                                    # silently ignored. Dropped.)
security_ref: null                  # F-912f4778 is a VERSION finding, not a
                                    # security one — cited below as finding_refs.
finding_refs: [F-912f4778]          # "Talos Linux (cluster nodes): v1.13.8 -> v1.14.0",
                                    # section=version, first_seen 2026-08-24.
                                    # READ §1.3: executing this plan does NOT close
                                    # that finding.
status: scheduled                   # OPERATOR GO 2026-09-05, option (B) — SPLIT and SCHEDULED.
                                    # Supersedes the brief option-(C) cut earlier the same night:
                                    # (C) is what left this plan with no date at all, which is the
                                    # exact shape that stranded talos-1.13.9 for 17 days. A dated
                                    # window occurrence is what makes it actually happen.
window: "sun-attended:2026-09-06"   # PART 1 of 2 — nodes k8s-nuc14-02 and -03 only.
                                    # Node 01 runs in PART 2, sun-attended:2026-09-13, tracked in
                                    # talos-1.13.10-node01.md. sun-attended is the ONLY
                                    # allow_reboot:true slot (nightly and sat-attended are both
                                    # allow_reboot:false, so a node roll cannot go there).
                                    #
                                    # WHY SPLIT rather than extend the window: two nodes fit the
                                    # existing 90 min with margin, so no change to
                                    # maintenance-windows.yaml is needed and no other Sunday is
                                    # affected. Talos explicitly tolerates a mixed patch level
                                    # across nodes, and etcd stays 3/3 the whole time — the
                                    # cluster simply sits v1.13.10/v1.13.10/v1.13.8 for one week.
                                    #
                                    # COST, stated plainly: it is two sittings, not one, and the
                                    # cluster is mixed-version in between. If a single sitting
                                    # matters more, the alternative is to raise sun-attended's
                                    # duration_min 90 -> 120 in maintenance-windows.yaml and run
                                    # all three nodes on 09-06 — that is a global window change,
                                    # so it is the operator's call, not this plan's.
# auto_execute RETIRED 2026-08-26 (P2.1b) — execution class is DERIVED from
# capability_change/rollback_class per runbooks/autonomy-policy.yaml.
# rollback_class: one-way => HUMAN-GATED. Never unattended, never in `nightly`.
sops_refs:
  - docs/sops/talos-upgrade.md
  - docs/sops/longhorn.md
  - docs/sops/backup.md
  - docs/sops/storage-safety.md
generated: "2026-09-05"
---

# Talos v1.13.8 → v1.13.10 (3-node rolling upgrade)

## 1) Summary & why held

### 1.1 What this is

The auto-updater holds every node-image bump by construction: it reboots all
three nodes, and `nightly` / `sat-attended` are `allow_reboot: false`. This is
not a "breaking change in the release notes" hold — it is a blast-radius hold.

**Only `talosVersion` moves.** `kubernetesVersion` stays at **v1.36.0**.
They are independent knobs in `talconfig.yaml`: `talosVersion` selects the
installer image, `kubernetesVersion` selects the kubelet. `docs/sops/talos-upgrade.md`
Step 1 shows both moving together because that SOP documents a combined
OS + Kubernetes + performance-tuning sweep; do not let its example line pull the
kubelet in. **Skip SOP Steps 2–6** (sysctls, kubelet patch, RPS mask, intelgpu,
udev) — none of them change for a patch bump. This plan is SOP Steps 1, 7, 8, 9.

`v1.13.9` is skipped; Talos patches are cumulative, so 1.13.8 → 1.13.10 is one
hop. Verified against the upstream release list (v1.13.10 published
2026-09-03, v1.13.9 2026-08-19).

Content of v1.13.10 (upstream release notes, 2026-09-03): Linux 6.18.48,
CoreDNS 1.14.7, etcd 3.6.14, built with Go 1.26.7. No Talos API, machine-config
schema, or `talconfig` breaking change. Fixes that actually matter here:

- `fix: allow CSI volumes to be mounted with an SELinux context` and
  `fix: skip selinux label for read-only/detached/external mounts` — CSI mount
  path, i.e. Longhorn and the 19 CIFS classes.
- `fix: reduce stalls in the etcd member promotion cycle` — all three nodes are
  control-plane; this is the failure mode a rolling reboot exercises.
- `fix: route creation churning every 100ms`, `fix: watch IPv6 route changes in
  RouteSpecController`.
- `fix: harden the code around kubelet's client certificate handling`,
  `fix: validate received kubeconfig`, `fix: treat desired roles empty as error
  in Talos API access`, plus a set of tar/extract path hardening fixes
  (`os.Root` in extract/untar paths, parent-dir creation, special-mode
  preservation).
- `fix: write the uploaded etcd snapshot atomically`,
  `fix: persist in-memory meta on fresh install`.

So the patch is security- and storage-relevant, not cosmetic.

### 1.2 Why v1.13.10 and NOT v1.14.0 — the recommendation, stated plainly

**Recommended target: v1.13.10.** v1.14.0 exists (published 2026-09-03, real,
not a prerelease) and is offered by PR #212's *CLI* bump, but it must not be the
node target in this window. Reasons, in order of weight:

1. **`talhelper` cannot be trusted to generate a v1.14 machine config today.**
   We are pinned at `talhelper = "3.1.11"` (released 2026-06-10) in `.mise.toml`
   — three months older than Talos 1.14.0. talhelper embeds the machine-config
   schema. Worse: **talhelper is EOL** — upstream v3.1.17 (2026-08-26) is
   explicitly announced as "the last release of Talhelper". A minor-line move
   therefore needs a talhelper bump to 3.1.17 *and* a plan for what replaces
   talhelper afterwards. That is config-generation work; it does not belong in
   a reboot window.
2. **v1.14.0 moves the etcd metrics/health endpoint.** Upstream upgrade note:
   *"etcd metrics and the HTTP health endpoint are no longer reachable on 2379;
   scrape them on port 2383 instead."* Our `kubeEtcd` scrape is enabled against
   the three node IPs and the live Service `kube-system/kube-prometheus-stack-kube-etcd`
   binds **2381** (chart default). Whatever the current binding resolves to, the
   failure mode of getting this wrong is silent: etcd monitoring goes dark while
   every pod stays green. That has to be measured and re-pointed *before* a 1.14
   roll, not discovered during one.
3. **v1.14.0 stops publishing `ghcr.io/siderolabs/installer`.** Upstream:
   *"The default installer image has been updated to use the Image Factory. The
   `ghcr.io/siderolabs/installer` image is no longer published with releases."*
   Our nodes already install from `factory.talos.dev/installer/<schematic>`
   (so the roll itself would work), but `talconfig.yaml` line 3 is
   `# renovate: datasource=docker depName=ghcr.io/siderolabs/installer` — the
   version tracker that produced PR #208 goes stale at the 1.14 boundary. Moving
   to 1.14 without re-pointing that datasource ends node version tracking.
4. **Other 1.14.0 surface that needs its own assessment**: TLS 1.3 enforced as
   the minimum for etcd and kube-apiserver (custom cipher suites removed);
   `--mode=reboot` removed from `talosctl apply-config`; ICMP `send_redirects`
   disabled by default; FlexVolume host path removed; in-tree volume plugins
   deprecated; dedicated system volumes; NRI no longer disabled by default;
   Kubernetes 1.37.0 bundled (we run 1.36.0).
5. **Two days of soak.** v1.14.0 is 2 days old at time of writing. This cluster
   has no staging.

**v1.14.0 is not rejected — it is sequenced.** It needs its own plan
(`talos-1.14.0`) whose *prerequisites* are: bump talhelper 3.1.11 → 3.1.17,
bump the `talosctl` CLI (PR #212), re-point the renovate datasource to the
Image Factory, and prove the etcd scrape target survives the 2379/2381 → 2383
move. None of those need a reboot; all of them can land in `nightly` or
`sat-attended` first.

### 1.3 This plan does NOT close F-912f4778

The version finding is titled `v1.13.8 → v1.14.0`. Landing v1.13.10 will make it
re-fire as `v1.13.10 → v1.14.0`. That is correct and expected — do not resolve
the finding on execution of this plan; it is answered only by the follow-up
`talos-1.14.0` plan described above. The ref is carried here so the finding
reads as *planned*, not unplanned.

### 1.4 This plan SUPERSEDES `talos-1.13.9`

`runbooks/maintenance/plans/talos-1.13.9.md` must be marked `superseded` (and
retired) in the same commit that schedules this one. It is 17 days old (past
`planning.stale_after_days: 14`), its target drifted (PR #208 now points at
v1.13.10), its window `sun-attended:2026-08-30` passed unexecuted, and its
`conflicts_with: [longhorn-1.12.1-engine]` names no plan that exists.

**Its operator GO does not carry over.** A GO is scoped to a window; that window
passed. This plan needs a fresh go/no-go. Do not re-arm the old decision record.

## 2) Pre-checks

Run ALL of these in the window, immediately before touching anything. The
values in brackets are what was observed 2026-09-05 while writing this plan —
they are a baseline to diff against, not a substitute for re-running.

```bash
# 2.1 All three nodes Ready, on v1.13.8, kubelet v1.36.0, same schematic
mise exec -- kubectl get nodes -o json | python3 -c "
import sys,json
for n in json.load(sys.stdin)['items']:
    i=n['status']['nodeInfo']
    ready=[c['status'] for c in n['status']['conditions'] if c['type']=='Ready'][0]
    print(n['metadata']['name'], 'Ready='+ready, i['osImage'], i['kubeletVersion'], i['kernelVersion'],
          n['metadata']['annotations'].get('extensions.talos.dev/schematic','?')[:16])"
# [expect: 3x Ready=True  Talos (v1.13.8)  v1.36.0  6.18.42-talos  43b3cbfc2957259b]
```

```bash
# 2.2 etcd health + member count — 3 members, all healthy. NEVER start a node
#     roll with a degraded etcd: you would be taking the second member down.
mise exec -- talosctl -n 192.168.55.11,192.168.55.12,192.168.55.13 service etcd
mise exec -- talosctl -n 192.168.55.11 etcd members
mise exec -- talosctl -n 192.168.55.11 etcd status
# [expect: 3 members, no alarms, all Running/Healthy]
```

```bash
# 2.3 Longhorn: ZERO degraded/faulted volumes, and nothing rebuilding.
mise exec -- kubectl get volumes -n storage -o json | python3 -c "
import sys,json
from collections import Counter
v=json.load(sys.stdin)['items']
print('volumes', len(v), Counter((x['status'].get('robustness'), x['status'].get('state')) for x in v))
bad=[(x['metadata']['name'], x['status'].get('robustness')) for x in v if x['status'].get('robustness')!='healthy']
print('NOT healthy:', bad)
single=[x['metadata']['name'] for x in v if x['spec'].get('numberOfReplicas',3)<2 and x['status'].get('state')=='attached']
print('attached single-replica (will go OFFLINE on their node reboot):', single)"
# [baseline 2026-09-05: 94 volumes, ALL ('healthy','attached'), 0 single-replica]
```

```bash
# 2.4 No replica currently rebuilding
mise exec -- kubectl get replicas.longhorn.io -n storage -o json | python3 -c "
import sys,json
r=json.load(sys.stdin)['items']
notrunning=[(x['metadata']['name'], x['status'].get('currentState')) for x in r if x['status'].get('currentState')!='running']
print('replicas', len(r), '| not running:', notrunning)"
```

```bash
# 2.5 Backup freshness — a node that does not come back is a RESTORE, not a retry
mise exec -- kubectl get volumes -n storage -o json | python3 -c "
import sys,json
v=json.load(sys.stdin)['items']
ts=[x['status'].get('lastBackupAt') for x in v if x['status'].get('lastBackupAt')]
print('with lastBackupAt:', len(ts), 'of', len(v), '| newest', max(ts), '| oldest', min(ts))"
# [baseline 2026-09-05: 94/94, newest 2026-09-04T03:09Z, oldest 2026-09-03T03:03Z]
# GATE: oldest must be < 48h old. lastBackupAt can lag one cycle — for a
# stale-looking volume cross-check its newest Completed Backup CR
# (docs/sops/backup.md -> "lastBackupAt Can Lag") before aborting.
```

```bash
# 2.6 Flux fully reconciled BEFORE we start, so any failure during the window is
#     attributable to the upgrade and not to in-flight drift.
mise exec -- flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
mise exec -- flux get helmreleases -A   | awk 'NR==1 || $5 != "True"'
```

```bash
# 2.7 Alert baseline — record it, so "new alert" is a meaningful statement later
mise exec -- kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &
curl -s http://localhost:9090/api/v1/alerts | grep -o '"alertname":"[^"]*"' | grep -vE 'Watchdog|InfoInhibitor' | sort | uniq -c
# 2.8 CONTENTS BASELINE for §4.5 — record the etcd scrape target's health NOW
curl -s 'http://localhost:9090/api/v1/targets?state=active' | python3 -c "
import sys,json
t=json.load(sys.stdin)['data']['activeTargets']
e=[x for x in t if 'etcd' in x['labels'].get('job','')]
print([(x['labels'].get('instance'), x['health'], x['lastError']) for x in e])"
# 2.9 CONTENTS BASELINE — a real etcd series, to compare against after the roll
curl -s --data-urlencode 'query=count(etcd_server_has_leader)' http://localhost:9090/api/v1/query
```

```bash
# 2.10 Confirm the factory publishes the target for OUR schematic.
#      COULD NOT BE VERIFIED FROM THE PLANNING HOST (a TLS-intercepting middlebox
#      made factory.talos.dev return a self-signed-cert error, and -k turned every
#      tag into a 302 — including a nonsense v9.9.9 control, so the check proves
#      nothing). RUN THIS FOR REAL BEFORE STEP 3.4:
mise exec -- crane manifest \
  factory.talos.dev/installer/43b3cbfc2957259b4588d362709d47387607901d4d3506c1ea46d7ea74cb99a3:v1.13.10 >/dev/null && echo OK
# no crane? then, from a node:
mise exec -- talosctl -n 192.168.55.11 image pull --namespace system \
  factory.talos.dev/installer/43b3cbfc2957259b4588d362709d47387607901d4d3506c1ea46d7ea74cb99a3:v1.13.10
# A schematic is version-independent (it encodes extensions + kernel args, not the
# release), so NO regeneration at factory.talos.dev is needed — but the tag must
# resolve for this schematic before the first node is cordoned.
```

**Abort conditions** — any one of these stops the window before Step 3.4:
etcd not 3/3 healthy · any Longhorn volume not `healthy` · any replica not
`running` · oldest backup > 48h · a Flux kustomization/HR not Ready · the
factory tag does not resolve.

## 3) Steps — GitOps

```bash
cd /Users/mu/code/cberg-home-nextgen   # work on main, no feature branch
```

**3.1** Edit `kubernetes/bootstrap/talos/talconfig.yaml` line 4:

```diff
 # renovate: datasource=docker depName=ghcr.io/siderolabs/installer
-talosVersion: v1.13.8
+talosVersion: v1.13.10
 # renovate: datasource=docker depName=ghcr.io/siderolabs/kubelet
 kubernetesVersion: v1.36.0
```

**Leave `kubernetesVersion: v1.36.0` untouched** (§1.1). Do not touch
`talosImageURL` — it is already the factory URL and is version-independent.

**3.2** Regenerate the SOPS-encrypted node configs (SOP Step 7):

```bash
mise exec -- bash -c 'cd kubernetes/bootstrap/talos && talhelper genconfig'
# SOPS_AGE_KEY_FILE must be exported (.mise.toml handles it).
```

**3.3** Review the diff and commit. The generation is deterministic — the ONLY
semantic change must be the installer version:

```bash
git diff -- kubernetes/bootstrap/talos/ | grep -E '^[+-]' | grep -v '^[+-][+-]' | head -40
# shared worktree: commit ONLY these paths, whatever else is staged (CLAUDE.md)
git commit --only kubernetes/bootstrap/talos/ \
  -m "chore(talos): talosVersion v1.13.8 -> v1.13.10 (sun-attended:2026-09-06)

Patch line: Linux 6.18.48, CoreDNS 1.14.7, etcd 3.6.14. kubernetesVersion
stays v1.36.0. Plan: runbooks/maintenance/plans/talos-1.13.10.md (PR #208)."
git show --stat HEAD    # is every file here actually ours?
git push
```

> The commit is bookkeeping + the source of truth for the next `genconfig`;
> **Flux does not apply Talos machine configs.** The nodes are changed only by
> the `talosctl upgrade` in 3.4. Do not wait for a reconcile here.

**3.4** Rolling upgrade — **one node at a time, health-gated between nodes**
(SOP Step 9). Node order: **02 → 03 → 01**. Start with a non-`talosctl`-endpoint
node and leave `k8s-nuc14-01` (192.168.55.11, the node the pre-check commands
address) for last, so the diagnostic path stays stable for as long as possible.

```bash
# --- NODE 1 of 3: k8s-nuc14-02 -----------------------------------------
mise exec -- task talos:upgrade-node IP=192.168.55.12
#   >>> run the FULL §4 per-node gate. Do not continue until every item passes.

# --- NODE 2 of 3: k8s-nuc14-03 -----------------------------------------
mise exec -- task talos:upgrade-node IP=192.168.55.13
#   >>> run the FULL §4 per-node gate again.

# --- STOP. PART 1 ENDS HERE. -------------------------------------------
#
#   Nodes 02 and 03 are the ENTIRE scope of this window (split decision,
#   §6.1). After node 03's §4 gate passes, run §4.5 cluster-wide and CLOSE
#   the window. The cluster is now intentionally mixed-version:
#       k8s-nuc14-02  v1.13.10
#       k8s-nuc14-03  v1.13.10
#       k8s-nuc14-01  v1.13.8   <- stays here for one week, on purpose
#   Talos supports this and etcd remains 3/3. Do not "just finish" node 01
#   to tidy it up: the 90-minute slot does not hold a third node, and node
#   01 is the LAST control-plane node — draining it leaves etcd at 2 of 3
#   with no failure budget, which is not something to start against a clock.
#
# --- NODE 01 IS PART 2 --------------------------------------------------
#   runbooks/maintenance/plans/talos-1.13.10-node01.md
#   window: sun-attended:2026-09-13
#   The command below is kept for reference ONLY — it belongs to part 2:
#
#   mise exec -- task talos:upgrade-node IP=192.168.55.11
#   >>> then §4 per-node gate, then §4.5 cluster-wide.
```

Do **not** run `task talos:upgrade-k8s` — that is the kubelet, out of scope.

> **The drain WILL sit for minutes on Longhorn, and that is normal.**
> `talosctl upgrade` installs the image first, then cordons and drains. The wait
> is Longhorn detaching volumes — **not** a stuck `instance-manager` PDB. All
> three instance-manager PDBs report `ALLOWED DISRUPTIONS = 0` permanently and
> arithmetically (selector pins one pod, `minAvailable: 1`); that is the steady
> state, not a fault. **Do not delete the PDBs. Do not reach for
> `EXTRA_FLAGS='--drain=false'`.** Watch progress instead — engines on the node
> under upgrade must fall to zero, then the PDB self-deletes and the drain
> completes within seconds (observed 8 → 0 in ~75s on 2026-08-16):
>
> ```bash
> mise exec -- kubectl -n storage get engines.longhorn.io -o json | python3 -c "
> import sys,json
> print(len([e for e in json.load(sys.stdin)['items'] if e['spec'].get('nodeID')=='k8s-nuc14-02']))"
> ```
>
> Full mechanism, and the real (race-shaped) failure mode:
> `docs/sops/talos-upgrade.md` § "The Longhorn instance-manager PDB drain block".

## 4) Verification

### 4.1 → 4.4 After EACH node, before touching the next

`Ready` returns before a node genuinely carries load, so Ready alone is not the
gate.

1. **Version and kubelet**:
   ```bash
   mise exec -- kubectl get nodes -o wide
   ```
   The node reports **Talos (v1.13.10)** and `Ready`. Kubelet must still read
   **v1.36.0** — if it moved, the kubelet was bumped unintentionally (§1.1): stop.
2. **Uncordoned and actually carrying pods** — not Ready-and-empty:
   ```bash
   mise exec -- kubectl get node <name> -o jsonpath='{.spec.unschedulable}'; echo
   mise exec -- kubectl get pods -A -o wide --field-selector spec.nodeName=<name> | wc -l
   ```
3. **etcd back to 3/3 healthy before the next node is touched** — this is the
   quorum gate; two down on a 3-member cluster loses the API server:
   ```bash
   mise exec -- talosctl -n 192.168.55.11 etcd members
   mise exec -- talosctl -n 192.168.55.11 etcd status   # no alarms, 3 members
   ```
4. **Longhorn fully rebuilt** — re-run pre-check 2.3 and 2.4 and require the
   *same* result: 94-ish volumes, **all `healthy`**, zero replicas not `running`.
   Starting node N+1 while N's replicas are still rebuilding is how a
   multi-replica volume loses quorum. This typically takes **10–15 minutes** and
   is the single biggest time cost of the window. Do not shortcut it.
5. No pod in `CrashLoopBackOff`/`Pending` that was not in the 2.7 baseline.

### 4.5 Cluster-wide, at the end

```bash
mise exec -- kubectl get nodes -o wide            # 3x Talos (v1.13.10), kubelet v1.36.0, kernel 6.18.48-talos
mise exec -- talosctl -n 192.168.55.11,192.168.55.12,192.168.55.13 version
mise exec -- flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
mise exec -- flux get helmreleases -A   | awk 'NR==1 || $5 != "True"'
```

**CONTENTS ASSERTION 1 (storage): a real read/write round-trip through a
mounted Longhorn PVC**, because "all volumes healthy" says nothing about whether
anything can still *use* them:

```bash
# pick any running pod with a Longhorn RWO mount, e.g. in the storage-consuming app set
POD=$(mise exec -- kubectl -n <ns> get pod -l <app-label> -o name | head -1)
mise exec -- kubectl -n <ns> exec $POD -- sh -c \
  'echo talos-1.13.10-$(date +%s) > /<mountpath>/.upgrade-probe && cat /<mountpath>/.upgrade-probe && rm /<mountpath>/.upgrade-probe'
```
Must echo back the exact string written. A read-only or detached volume fails
here while Longhorn still reports `healthy`.

**CONTENTS ASSERTION 2 (monitoring did not go dark): the etcd metric series
still arrive after the roll**, compared to the 2.8/2.9 baseline — a node OS bump
can move or re-TLS a scrape endpoint while every pod stays perfect:

```bash
mise exec -- kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &
# target health must still be up for all three node IPs:
curl -s 'http://localhost:9090/api/v1/targets?state=active' | python3 -c "
import sys,json
t=json.load(sys.stdin)['data']['activeTargets']
print([(x['labels'].get('instance'), x['health'], x['lastError']) for x in t if 'etcd' in x['labels'].get('job','')])"
# and a real series over a window that STARTS AFTER the last node rebooted:
curl -s --data-urlencode 'query=count_over_time(etcd_server_has_leader[10m])' \
  http://localhost:9090/api/v1/query
```
Required: three etcd targets `health=up`, and a **non-zero** count for the
post-upgrade window. A floor, not just a ceiling — total disappearance of the
series must not read as success.

**CONTENTS ASSERTION 3 (workloads, not just pods): one ingressed app answers
end-to-end** — pick any Homepage-registered app and fetch its health path
through the ingress, asserting a 200 and a non-empty body, not merely that the
pod is `Running`.

Finally: alert set back to the 2.7 baseline (nothing new beyond Watchdog).

## 5) Rollback — and it is NOT clean

**State this plainly: a Talos upgrade is not a git revert.** `rollback_class:
one-way`.

- **Reverting the commit changes nothing on the nodes.** Flux does not apply
  machine configs; the git change only feeds the next `genconfig`. Reverting it
  is bookkeeping so the repo matches reality — it does not undo an install.
- **The node-level undo is another reboot**, into the image Talos kept in the
  other boot slot:
  ```bash
  mise exec -- talosctl rollback --nodes 192.168.55.12
  ```
  This is only available for the *immediately* previous install and is itself a
  disruptive reboot — with another full Longhorn detach/rebuild cycle. Budget
  15–25 min per node rolled back.
- **Roll back the AFFECTED NODE ONLY.** The cluster tolerates a mixed patch
  level (1.13.8 alongside 1.13.10) indefinitely, so one bad node never forces
  reverting the ones that succeeded. Stop the sequence, roll back that node,
  leave the rest.
- Then, to make the repo honest:
  ```bash
  git revert --no-edit <sha-from-3.3>
  mise exec -- bash -c 'cd kubernetes/bootstrap/talos && talhelper genconfig'
  git commit --only kubernetes/bootstrap/talos/ -m "revert(talos): back to v1.13.8"
  ```
- **Confirm the cluster is back**: re-run §2.1 (node reports the expected
  version, Ready), §2.2 (etcd 3/3, no alarms), §2.3/2.4 (all volumes `healthy`,
  no replica rebuilding), §2.6 (Flux green) and CONTENTS ASSERTION 1.
- **If a node does not come back at all**, this is not a rollback — it is a
  rebuild from `talconfig.yaml` plus a Longhorn restore from backup. That is
  exactly why pre-check 2.5 is an abort gate and not a formality.

## 6) Interference notes

### 6.1 Capacity — RESOLVED 2026-09-05: option (B), split across two Sundays

> **FINAL OPERATOR DECISION 2026-09-05 — option (B).**
> Part 1: nodes 02 + 03 on `sun-attended:2026-09-06`, ~70 min.
> Part 2: node 01 on `sun-attended:2026-09-13`, ~45 min (`talos-1.13.10-node01.md`).
>
> **This supersedes the option-(C) cut made earlier the same night.** (C) — run
> attended, outside the window system — was chosen first and then reversed for
> one concrete reason: it left the plan with **no date at all**. Nothing pulls a
> `window: null` plan, so it happens only if someone remembers. That is the exact
> shape that stranded `talos-1.13.9` for 17 days behind a live operator GO. A
> dated window occurrence is what converts an approval into an execution.
>
> **What (B) restores that (C) gave up:**
> - **Step 0 runs first** again, so the safe-update batch lands with its
>   health-gate — budget it before the ~70 min.
> - **The window agent's health-gate and auto-revert harness** wraps the run.
>
> **What (B) costs, plainly:** two sittings instead of one, and the cluster runs
> a **mixed patch level** (v1.13.10 / v1.13.10 / v1.13.8) for one week. Talos
> supports this and etcd stays 3/3 throughout — it is an accepted state, not
> drift.
>
> **If a single sitting matters more than the split**, the alternative is to
> raise `sun-attended.duration_min` 90 -> 120 in `runbooks/maintenance-windows.yaml`
> and run all three nodes on 09-06. That changes every Sunday window, so it is an
> operator policy call rather than something this plan should assume.
>
> The estimate was never shaved to fit: the **scope** shrank from 3 nodes to 2.
> The original three-option analysis is kept below for provenance.

#### Original analysis (pre-decision)

### 6.1-orig Capacity — honest verdict: this does NOT fit sun-attended:2026-09-06

`sun-attended` is 90 minutes (`duration_min: 90`, `capacity_risk: 6`), and it is
the **only** window with `allow_reboot: true`. Realistic cost here:

| Phase | Estimate |
|---|---|
| Pre-checks §2 (incl. factory-tag proof) | 10 min |
| Per node: install + drain/detach + reboot + Ready | 10–15 min |
| Per node: Longhorn replica rebuild (94 attached volumes) | 10–15 min |
| Per node: §4 gate | ~5 min |
| **Per node total** | **25–35 min** |
| 3 nodes | 75–105 min |
| Final §4.5 cluster verification | 10 min |
| **Total** | **95–125 min (plan of record: 110)** |

**And Step 0 comes first.** Every window — including this one — begins with the
`maintenance-window-agent` applying the safe-update batch
(`AUTO_UPDATE_APPLY=1 auto-update.py --apply` + `coverage.py`), reconciling and
health-gating it. That is not free time, and its rollouts perturb the same
workloads we are about to reschedule. Budget it *before* the 110 min above.

Three options for the operator at go/no-go — **do not let the window agent pick
silently**:

- **(A) Extend the window / accept an attended overrun.** Operator is present by
  definition in `sun-attended`; the risk is fatigue on the last node's gate,
  which is the gate that matters most.
- **(B) Split across two Sundays** — nodes 02 + 03 on 2026-09-06, node 01 on
  2026-09-13. **This is safe**: Talos explicitly tolerates a mixed patch level,
  etcd runs 3/3 throughout, and each node is fully verified before the window
  closes. Cost: the cluster sits mixed-version for a week, and the second window
  is consumed. *This is the recommended option if nothing else is scheduled into
  09-13.*
- **(C) Run attended outside the window system**, like the `envoy-gateway-phase*`
  work. Appropriate if the operator wants the whole roll in one sitting without
  a clock.

**`maintenance-plan.py --validate` deliberately flags this plan**
(`est_duration_min 110 can never fit sun-attended (90m)`). That error is the
machine-readable form of this section, not an oversight — it clears when the
operator picks (A), (B) or (C) and the plan is re-cut accordingly (under (B),
each half is ~60 min and fits). Do not silence it by shaving the estimate.

Whichever is chosen, the **per-node gates in §4 are not negotiable**. If time
runs out mid-sequence, the correct action is to **stop on a fully-verified node
boundary**, not to skip a gate to "finish".

### 6.2 What must NOT run in the same window

- **Anything with `shared: [longhorn]` or a `storage` namespace resource.**
  Longhorn replica rebuilds after each of the three reboots are the dominant
  contention in this window — they saturate the storage path and they *are* the
  per-node gate. A concurrent plan that moves PVC data both slows the rebuild
  and risks being interrupted by the next reboot. `conflicts_with` names the
  five real plans that fit that description today; the *rule* is broader than
  the list.
- **New since 2026-09-04 (commit 5787cf3d): the `storage` namespace now also
  runs a `snapshot-controller` Deployment (2 replicas, 9h old at planning
  time), alongside Longhorn's `csi-snapshotter` sidecar, plus the restored
  `snapshot.storage.k8s.io` CRDs.** It is brand new and has never been through a
  node roll. Two consequences: (a) treat a `snapshot-controller` crashloop or
  watch error after a reboot as *expected-to-be-checked*, not as a mystery —
  include it in the §4 per-node pod check; (b) **do not schedule any
  VolumeSnapshot/CSI-snapshot work in this window** — a snapshot in flight
  during a detach/reattach cycle is exactly the wrong overlap, and this
  component has no reboot history to lean on.
- **Anything touching cilium, coredns, cert-manager or the ingress
  controller.** Every one of them restarts on every node cycle anyway; a
  concurrent change to them makes any failure unattributable.
- **The Longhorn backup CronJob at 03:00** does not overlap a 09:00 window —
  but do not manually trigger a backup during the roll.
- **Only ONE reboot-bearing plan per window.** Nothing else with
  `needs_reboot: true` may share this slot.

### 6.3 Ordering / dependencies

- No `depends_on`. Nothing must run before this.
- Node order 02 → 03 → 01 (§3.4). All three are control-plane; **never** allow
  two nodes to be down or cordoned simultaneously — etcd quorum on a 3-member
  cluster is 2.
- `superset-pg-decommission` sits in `sat-attended:2026-09-05` and
  `bitnamilegacy-exit-nextcloud-db` in `sat-attended:2026-09-12` — different
  windows, no overlap today. If either slips *into* a Sunday slot, it conflicts
  (both are in `conflicts_with`).

## 7) The `talosctl` CLI bump (PR #212) — a DIFFERENT change, not this window

**Do not conflate these. This exact collision has bitten this repo before.**

| | PR #208 | PR #212 |
|---|---|---|
| What | `ghcr.io/siderolabs/installer` v1.13.8 → **v1.13.10** | `aqua:siderolabs/talos` 1.13.4 → **1.14.0** |
| Where | `kubernetes/bootstrap/talos/talconfig.yaml` (`talosVersion`) | `.mise.toml` (local CLI pin) |
| Effect | rolls and **reboots all 3 nodes** | changes a binary on the operator's Mac |
| Reboot | **yes** | **no** |
| This plan | **yes** | **no** |

PR #212 is local tooling only — no cluster effect, no reboot — so it must **not**
consume the scarce reboot-capable slot. Route it to **`nightly`** (or
`sat-attended`) as an ordinary safe update: it is a `.mise.toml` pin bump,
reversible by `git revert`, verified with `mise exec -- talosctl version --client`.

Two caveats for whoever lands it:

1. Taking the CLI to **1.14.0** while the nodes stay on **1.13.x** inverts the
   usual skew (client newer than server). One minor of skew is supported, but
   `talosctl` 1.14 also **removes `--mode=reboot` from `apply-config`** — check
   `.taskfiles/talos/Taskfile.yaml` before merging: `apply-node` passes
   `--extra-flags '--mode={{.MODE}}'` with `MODE` defaulting to `auto`, which is
   fine, but an operator habit of `MODE=reboot` would start failing.
2. Do not merge #212 *during* this upgrade window. Changing the CLI mid-roll
   makes any `talosctl` failure unattributable.

Neither PR should be merged as a plain git bump for the *node* side: the
installer version reaches the nodes only through §3, not through Flux.

## 8) What could not be verified while writing this plan

- **The factory tag for our schematic.** `factory.talos.dev` could not be
  reached from the planning host (TLS-intercepting middlebox → self-signed-cert
  error; with `-k` every tag including a bogus `v9.9.9` control returned 302, so
  the result is worthless). Pre-check **2.10** is therefore a hard gate, not a
  formality. The upstream *release* v1.13.10 is confirmed real (published
  2026-09-03 on siderolabs/talos), and the schematic
  `43b3cbfc2957259b…` is confirmed identical on all three live nodes.
- **Whether the current etcd scrape is actually healthy.** The Service
  `kube-system/kube-prometheus-stack-kube-etcd` binds 2381 with all three node
  IPs as endpoints, but target health was not measured — hence pre-checks 2.8/2.9
  record the baseline and CONTENTS ASSERTION 2 compares against it.
- **Longhorn rebuild duration on 94 attached volumes.** The 10–15 min/node
  figure comes from `docs/sops/talos-upgrade.md` and the 2026-08-16 roll, not
  from a measurement on today's volume count.
