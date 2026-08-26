---
plan_id: longhorn-1.12.1-engine
component: longhorn
pr: null                              # the engine upgrade is a CR operation, not a version bump
kind: chart
current: "96 volumes (2026-08-25 recount): 71 v1.11.2 + 21 v1.12.0 + 4 v1.12.1"
target: "every ATTACHED volume on v1.12.1; 2 detached rollback floors explicitly EXCLUDED — see 1c"
update_type: patch
risk: medium                          # live engine upgrade touches every attached volume
est_duration_min: 45                  # ATTENDED portion. The drain itself is ASYNC and
                                      # unbounded — see §6. Do not read this as a finish time.
needs_reboot: false
capability_change: false             # same storage features before and after
rollback_class: one-way              # the drain has no clean rollback (its own §5)
touches:
  namespaces: [storage]
  resources:
    - "engineimage/ei-c9fa6d45"        # v1.11.2, refCount 292 — GCs once unreferenced
    - "engineimage/ei-a4d05f02"        # v1.12.0, refCount 84  — GCs once unreferenced
    - "volume/* (95, of which 92 attached)"   # 72 v1.11.2 + 21 v1.12.0 + 2 v1.12.1
    - daemonset/engine-image-ei-*      # both stale DaemonSets retire with the last reference
    - setting/concurrent-automatic-engine-upgrade-per-node-limit
  shared: [storage]                   # EVERY stateful app rides Longhorn — see §6
depends_on: []                        # was [longhorn-1.12.1-chart] -- DEAD REF, no such plan file ever
                                      # existed, so the dependency guard could never enforce it (found
                                      # 2026-08-23). The underlying precondition (v1.12.1 must be the
                                      # default engine before draining onto it) is satisfied IN FACT --
                                      # verified live 2026-08-24: longhorn-manager:v1.12.1 and
                                      # setting/default-engine-image both v1.12.1. Cleared rather than
                                      # left pointing at nothing.
conflicts_with: []                    # (declared FROM the five sibling plans, see §6)
security_ref: F-49f172b9              # see also F-6bedee0b (engine v1.12.0)
status: scheduled                     # FRESH operator GO 2026-08-25 for sat-early:2026-08-29,
                                      # recorded in OpenClaw (decision=approve, exec_state=pending).
                                      # The 2026-08-24 GO was superseded when the preconditions moved;
                                      # this one was given AFTER the 1d blocker was resolved (see 1e).
                                      # Deferred out of tue-early:2026-08-25 by the window agent.
window: "sat-attended:2026-08-29"        # 90min OPERATOR-PRESENT no-reboot slot. NOT sun-window:2026-08-30 --
                                      # talos-1.13.9 is scheduled there and 6 forbids pairing an engine
                                      # drain with a node roll. Moved off tue-early:2026-08-25 because that
                                      # was an unattended 60min cron slot and this plan is auto_execute:false.
# auto_execute RETIRED 2026-08-26 (P2.1b) — execution class is now DERIVED
# from capability_change/rollback_class per runbooks/autonomy-policy.yaml.
# (original rationale: storage engine upgrade — never unattended)
sops_refs:
  - docs/sops/longhorn.md
  - docs/sops/backup.md
  - docs/sops/storage-safety.md
generated: "2026-08-14"
revised: "2026-08-25"                 # 2026-08-19 SPLIT from chart bump + SCOPE CORRECTED;
                                      # 2026-08-25 census drift + gate defect recorded (see 1d)
---

# Longhorn: finish the engine upgrade — every attached volume → v1.12.1

## 1) Summary & why held

Security driver on `longhornio/longhorn-engine`.

> **Security driver — detail withheld from this public repo.**
> Tracked as **F-49f172b9** (engine v1.11.2) and **F-6bedee0b** (v1.12.0).
> Counts, advisory references and exposure live on the finding records.
>
> - Dashboard: `https://sweep.<DOMAIN>/findings/F-49f172b9`
> - CLI: `runbooks/policy-cli.py finding show F-49f172b9`
>
> Convention: `docs/sops/vulnerability-disclosure.md`.

**SCOPE CORRECTED 2026-08-19.** The previous revision of this plan claimed
"74 of 80 volumes still on v1.11.2". Measured against the live cluster:

```
total volumes: 95          # RECOUNTED 2026-08-19 after the day's migrations
  72  docker.io/longhornio/longhorn-engine:v1.11.2
  21  docker.io/longhornio/longhorn-engine:v1.12.0
   2  docker.io/longhornio/longhorn-engine:v1.12.1   # born on the new default
```

Both numerator and denominator were wrong, and — the substantive error — the
21 volumes on **v1.12.0 are not "already done"**. v1.12.0 carries its own
finding (**F-6bedee0b**), so it is not a clean destination. **Every ATTACHED
volume must reach v1.12.1**, not just the v1.11.2 ones. A run that stopped when
v1.11.2 hit zero would leave 21 volumes on a flagged engine and the sweep still
red. For the detached exclusions, and why the census moved, see §1c.

`EngineImage ei-c9fa6d45` (v1.11.2) has refCount 292 and `ei-a4d05f02`
(v1.12.0) refCount 84; **both** DaemonSets are still deployed, and both stale
images must become unreferenced before the finding clears.

**Root cause of the stall:** `concurrent-automatic-engine-upgrade-per-node-limit`
is `0` (automatic engine upgrade disabled, and not set in git), so engines never
followed the manager. This plan's real work is turning that on in a controlled
way and draining.

**Do NOT "fix" this by pinning engine v1.11.3** — an older minor line than the
1.12.x the manager is on; it moves backwards.

**Split note:** the chart bump 1.12.0 → 1.12.1 is now a separate plan
(`longhorn-1.12.1-chart`) and is a hard `depends_on` — v1.12.1 must be the
cluster's default engine image before anything drains onto it.

## 1b) TRAP FOUND 2026-08-19 during the chart half — read before any longhorn bump

The chart bump to 1.12.1 shipped a **silent network-posture change inside a
patch release**, and it broke monitoring within seconds.

Chart 1.12.1 adds `networkPolicies.restrictInternalTraffic`, **defaulting to
`true`**. It renders NetworkPolicies even though `networkPolicies.enabled` is
still `false` — the two are independent, which is not obvious from the values
file. Measured:

```
helm template … --version 1.12.0                                      -> 0 NetworkPolicy
helm template … --version 1.12.1                                      -> 6 NetworkPolicy
helm template … --version 1.12.1 --set networkPolicies.restrictInternalTraffic=false -> 0
```

`netpol/storage/longhorn-manager` admits only longhorn-internal pods. Prometheus
is not in the allow-list, so all three `longhorn-backend` scrape targets went
DOWN (`context deadline exceeded` on `:9500/metrics`) and `LonghornManagerDown`
×3 + `TargetDown` fired **permanently**. Longhorn itself stayed healthy (all
volumes attached + healthy) — so this was a monitoring blind spot, which is the
dangerous kind: a standing false alarm masks a real future manager failure.

Pinned to `false` in the HelmRelease to keep 1.12.1 a true patch bump.

**The hardening is worth adopting — but as its own vetted plan, not as a side
effect.** That plan must (a) allow-list `monitoring` to `longhorn-manager:9500`,
and (b) verify the ~10 nightly `storage` CronJobs under the policies — backups
`0 3 * * *`, filesystem-trim `0 2 * * *`, snapshot-cleanup `30 2 * * *`. None of
them had run under the new policies when this was found, so their blast radius
is still untested. Do not adopt it blind.

**Lesson for this plan:** verification for a storage-layer change must include
"Prometheus can still scrape it", not only "the volumes are healthy". §4 below
inherits that.

## 1c) RECOUNT + EXCLUSIONS — added 2026-08-19, read before the gate

**Do not trust any volume count written in this file. Re-derive it live.** The
fleet changed under this plan during the 2026-08-19 window:

```
2026-08-19 recount:  95 volumes  (was 93 when this plan was written)
  72  v1.11.2      21  v1.12.0      2  v1.12.1
  92 attached      3 detached
```

Two volumes were created by the day's migrations (`paperless-db-data`,
`nextcloud-db-data`), both born on v1.12.1 because the chart bump moved the
default engine. Neither is pinned — pinning a volume makes it actively resist
this drain.

### The three detached volumes, and why two are permanent exclusions

| volume | engine | why detached |
|---|---|---|
| `paperless-mariadb` | **v1.11.2** | retained rollback floor for the paperless replatform |
| `redis-data-nextcloud-redis-master-0` | **v1.11.2** | retained rollback floor for the nextcloud redis cutover |
| `nextcloud-db-data` | v1.12.1 | parked from the rolled-back nextcloud-db attempt; already on target |

**A detached volume cannot be live-upgraded.** Longhorn upgrades the engine of a
running volume; there is no engine process to swap on a detached one. Attaching
these two purely to upgrade them would mean attaching a rollback floor — exactly
what `docs/sops/storage-safety.md` and the retention decisions of this window
say not to touch. **Do not attach them. Do not delete them.**

### Consequence the success gate must account for

The original gate said "both stale EngineImages unreferenced, then gone; their
DaemonSets retired". **That is no longer achievable in this run**, and it is
important not to discover that at the end:

- `ei-c9fa6d45` (v1.11.2) will retain references from the two detached floors,
  so it will **not** GC and its DaemonSet will **not** retire.
- `ei-a4d05f02` (v1.12.0) has no such blocker and should GC normally once the
  attached v1.12.0 volumes drain.

So the honest gate for this run is:

1. every **attached** volume on v1.12.1 (re-derive the count; 92 on 2026-08-19);
2. `ei-a4d05f02` unreferenced and gone;
3. `ei-c9fa6d45` still present, referenced **only** by the two excluded floors —
   assert that its remaining references are exactly those two, not some volume
   the drain silently skipped. That distinction is the whole point of the check.

**Scope note:** the outcome for the older engine line is bounded by those two
exclusions, and retiring a rollback floor is a separate decision with its own
risk. Do not smuggle it into a drain. Record the outcome on the finding records
(`F-49f172b9`, `F-6bedee0b`) rather than reporting the drain as failed — a drain
that correctly refuses to touch a rollback floor has succeeded, not fallen
short. Status detail belongs on the record, not in this file.

## 1d) CENSUS DRIFT + GATE DEFECT — found 2026-08-25 at tue-early, READ BEFORE RE-APPROVING

The window agent ran this plan's read-only pre-checks on 2026-08-25 and did NOT
drain. Pre-checks (a), (b), (d) PASSED: chart 1.12.1, engineimage v1.12.1
`deployed`, `default-engine-image` v1.12.1, every ATTACHED volume healthy,
concurrency limit still `0` as described. What changed is the census, again:

```
plan 1c (2026-08-19):  95 volumes   92 attached   3 detached
LIVE   (2026-08-25):   97 volumes   94 attached   3 detached
                       72 v1.11.2   21 v1.12.0    4 v1.12.1
```

**`nextcloud-db-data` no longer exists.** 1c lists it as one of the three
detached volumes ("parked from the rolled-back nextcloud-db attempt"). It has
since been removed. Do not look for it.

**A THIRD detached v1.11.2 volume has appeared: `paperless-ai-data`.** Its PV is
`Released` / reclaim `Retain`, orphaned by `66adefd7` (retiring paperless-ai for
native paperless-ngx AI, 2026-08-24). It has a backup (2026-08-24). It is NOT a
sanctioned exclusion in 1c.

The live detached set on v1.11.2 is therefore:

| volume | sanctioned by 1c? |
|---|---|
| `paperless-mariadb` | yes — rollback floor |
| `redis-data-nextcloud-redis-master-0` | yes — rollback floor |
| `paperless-ai-data` | **NO — undocumented, needs a ruling** |

### Why this blocks, rather than being a footnote

Success gate 3 in 1c/4 asserts that `ei-c9fa6d45`'s residual references are
**exactly** the two rollback floors — and 1c is explicit that this is "the check
that distinguishes 'correctly refused to touch a rollback floor' from 'missed
one'". With an undocumented third detached volume that assertion cannot be made
as written. Widening it to "three" unattended would delete the only discriminator
the gate has, which is the opposite of what 1c intends.

**Operator ruling needed before re-approval:** is `paperless-ai-data` a sanctioned
third permanent exclusion (leave it detached on v1.11.2 and state the gate as
three), or is the orphaned Released PV cleaned up separately FIRST so the gate
stays at two? Either is defensible; the drain must not start until one is chosen.

### One false alarm, already resolved — do not re-raise it

Pre-check (c) appears to fail: `mealie-data` has an EMPTY `.status.lastBackupAt`.
It is **not** unbacked — a `Completed` Backup CR exists from `2026-08-25T03:02:09Z`.
This is the documented `lastBackupAt` lag in `docs/sops/backup.md`. When running
pre-check (c), cross-check the Backup CRs before treating a blank field as a
missing backup, or this plan will keep tripping over its own mandatory gate.

## 1e) 1d RESOLVED — operator ruling 2026-08-25, gate stays at TWO

The 1d blocker is closed. The operator ruled on the third detached volume:
**`paperless-ai-data` was cleaned up, not sanctioned as a permanent exclusion.**

Executed 2026-08-25 (this was the cleanup 1d called for, done separately and
BEFORE the drain, exactly as that section required):

```
kubectl delete pv paperless-ai-data                    # Released / Retain, no claim, no workload
kubectl -n storage delete volume paperless-ai-data     # the CR holding the v1.11.2 engine ref
```

Pre-flight before the delete: storageClass `longhorn-static` (a Longhorn volume,
NOT a CIFS/SMB class — `docs/sops/storage-safety.md` blast-radius rules do not
apply), phase `Released`, reclaim `Retain`, PVC `office/paperless-ai-data` gone,
no pod in any namespace referencing it, and **7 Completed backups retained**
(newest `backup-218a3d7a72b14ea7`, 2026-08-24) so the delete is recoverable.

Live census re-verified immediately after:

```
96 volumes   94 attached   2 detached
71 v1.11.2   21 v1.12.0    4 v1.12.1

DETACHED SET:
  paperless-mariadb                      v1.11.2   (sanctioned rollback floor)
  redis-data-nextcloud-redis-master-0    v1.11.2   (sanctioned rollback floor)
```

**Success gate 3 is therefore assertable exactly as 1c wrote it: `ei-c9fa6d45`'s
residual references must be EXACTLY those two volumes. Do NOT widen it to three.**
The discriminator between "correctly refused to touch a rollback floor" and
"silently missed a volume" is intact — which was the whole reason the window agent
refused to widen it unattended.

Also note the 1c census fix carried forward: `nextcloud-db-data` no longer exists.
Do not look for it.

## 2) Pre-checks

```bash
# a) the chart half is done and v1.12.1 is the default engine image
kubectl get hr -n storage longhorn -o jsonpath='{.status.history[0].chartVersion}{"\n"}'   # 1.12.1
kubectl get engineimages -n storage    # a v1.12.1 image must exist and be `deployed`

# b) EVERY volume healthy and attached — a live upgrade on a degraded volume is
#    how you lose data.
kubectl get volumes -n storage -o custom-columns=N:.metadata.name,S:.status.state,R:.status.robustness --no-headers | awk '$3!="healthy"'
#    expect NO rows

# c) backups fresh for EVERY volume (mandatory — this is the step with no clean rollback)
kubectl get volumes -n storage -o custom-columns=N:.metadata.name,LASTBACKUP:.status.lastBackupAt --no-headers | awk '$2==""||$2=="<none>"'
#    expect NO rows  (verified 0 rows on 2026-08-19)

# d) baseline distribution
kubectl get volumes -n storage -o custom-columns=E:.status.currentImage --no-headers | sort | uniq -c

# e) NOTHING from the conflicts set still running — see §6. In particular every
#    volume-creating / DB-cutover plan of the session must be COMPLETE, not merely
#    "its window ended".
```

## 3) Steps

1. Marker: `runbooks/update-marker.sh add longhorn storage 2 "engine drain -> v1.12.1 (CVE)"`
2. **Raise the concurrency limit from 0 to 1** — one volume per node at a time,
   so the blast radius at any instant is a single volume on a single node and
   you can stop at any point:
   ```bash
   kubectl -n storage patch setting concurrent-automatic-engine-upgrade-per-node-limit \
     --type=merge -p '{"value":"1"}'
   ```
3. Watch it drain — **both** source images must fall to zero:
   ```bash
   watch 'kubectl get volumes -n storage -o custom-columns=E:.status.currentImage --no-headers | sort | uniq -c'
   ```
4. Any volume that will not live-upgrade (detached, or a workload that dislikes
   it) is moved by scaling its workload to 0, letting the engine swap, and
   scaling back — **one app at a time, never in bulk.**
5. **Decide the end state deliberately** (this setting is NOT in git today):
   leaving it at `1` means engines follow future chart bumps automatically and
   this entire class of drift stops recurring; returning it to `0` restores the
   drift. If it stays at `1`, add
   `concurrentAutomaticEngineUpgradePerNodeLimit: 1` to `defaultSettings` in
   the HelmRelease in the same session so it is not a cluster-only mutation.

## 4) Verification

```bash
# Every ATTACHED volume on v1.12.1. Do NOT expect a single-line result —
# the excluded detached floors (1c) stay on their old engines by design.
kubectl get volumes -n storage -o custom-columns=E:.status.currentImage --no-headers | sort | uniq -c
#   expect: all ATTACHED volumes on v1.12.1, plus exactly the 1c exclusions
#   still on v1.11.2. Re-derive the counts live; do not trust a number in this file.

# EngineImages — see 1c, the expectation is ASYMMETRIC now:
#   ei-a4d05f02 (v1.12.0): must go unreferenced and GC; its DaemonSet retires.
#   ei-c9fa6d45 (v1.11.2): must REMAIN, referenced ONLY by the two excluded
#                          detached floors. It will not GC and that is correct.
kubectl get engineimages -n storage
kubectl get ds -n storage | grep engine-image
# Prove c9fa6d45's leftover references are EXACTLY the exclusions and not a
# volume the drain silently skipped — this is the check that distinguishes
# "correctly refused to touch a rollback floor" from "missed one":
kubectl get volumes -n storage -o json | python3 -c "
import sys, json
stuck=[(v['metadata']['name'], v['status'].get('state'))
       for v in json.load(sys.stdin)['items']
       if 'v1.11.2' in (v['status'].get('currentImage') or '')]
print('still on v1.11.2:', stuck)
assert all(st != 'attached' for _, st in stuck), 'an ATTACHED volume was left behind'
"

# every volume still healthy + attached, no replica rebuild storm
kubectl get volumes -n storage -o custom-columns=N:.metadata.name,S:.status.state,R:.status.robustness --no-headers | awk '$3!="healthy"'

# engine image scan for the record
trivy image longhornio/longhorn-engine:v1.12.1 --ignore-unfixed
# Record the outcome on F-49f172b9 and F-6bedee0b — not in this file.
# Per 1c: F-6bedee0b (v1.12.0) can close in this run; F-49f172b9 (v1.11.2)
# CANNOT, because the two excluded floors keep that image referenced. Record the
# partial outcome rather than reporting the drain as failed.
```

### CONTENTS ASSERTIONS — do NOT sign this plan off on the block above

Volume `state=attached` + `robustness=healthy` is the SHAPE of the storage
layer. It is exactly what stayed green through the §1b incident, and it says
nothing about whether anything can still *observe* or *use* the volumes. Both
assertions below are mandatory; see
`docs/sops/verification-contents-not-shape.md`.

**CONTENTS ASSERTION 1 — Prometheus still scrapes Longhorn.** This is §1b's
lesson, executed rather than narrated. The chart half already pinned
`restrictInternalTraffic: false`, but the engine drain restarts
instance-managers on every node, so re-assert it *after* the drain:

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &
sleep 5

# a) all three longhorn-backend targets UP (not "0 down" — count them: 3)
curl -s http://localhost:9090/api/v1/targets | python3 -c "
import sys, json
t=[x for x in json.load(sys.stdin)['data']['activeTargets']
   if 'longhorn' in x['labels'].get('job','')]
print('targets:', len(t))
for x in t: print(' ', x['labels']['job'], x['labels'].get('instance'), x['health'], x.get('lastError',''))
assert t and all(x['health']=='up' for x in t), 'LONGHORN SCRAPE DOWN — STOP'"

# b) the series ACTUALLY ARRIVE — a target can be up and export nothing.
#    Query a 5m window that starts AFTER the drain, and require one row per volume.
curl -s --get http://localhost:9090/api/v1/query \
  --data-urlencode 'query=count(count by (volume) (longhorn_volume_actual_size_bytes))' \
  | python3 -c "
import sys, json
r=json.load(sys.stdin)['data']['result']
assert r, 'EMPTY RESULT — metrics are not arriving. STOP.'
print('volumes reporting metrics:', r[0]['value'][1])"
#    must equal the LIVE attached count (re-derive it; it was 92 on 2026-08-19).
#    An empty result array is a FAILURE, not 'no news'.

# c) and no permanently-firing false alarm left behind
curl -s http://localhost:9090/api/v1/alerts | grep -o '"alertname":"[^"]*"' \
  | grep -vE 'Watchdog|InfoInhibitor' | sort | uniq -c
#    LonghornManagerDown / TargetDown must be ABSENT (they fired ×3 in §1b)

# no NetworkPolicy crept back in with the engine work
kubectl get netpol -n storage
```

**CONTENTS ASSERTION 2 — a real read/write round-trip through a mounted PVC.**
"App-level smoke" was too vague to execute; make it a byte-level round-trip on
one Longhorn-backed database pod and one CIFS-backed media pod (the CIFS pod is
the control — it must be unaffected by engine work):

```bash
# Longhorn-backed: write, sync, read back, delete. Pick any attached-volume pod.
POD=<a pod mounting a Longhorn PVC>; NS=<its namespace>
kubectl exec -n $NS $POD -- sh -c \
  'D=$(mktemp -d 2>/dev/null || echo /tmp); echo verify-$$ > /<mountpath>/.verify && sync && cat /<mountpath>/.verify && rm -f /<mountpath>/.verify'
#   must echo back the exact string it wrote

# Database-level, the assertion that matters for a storage change: the data is
# still READABLE, not merely that the pod is Ready.
kubectl exec -n databases <pg-pod> -- psql -U <u> -d <db> -At -c 'select count(*) from <a real table>;'
#   non-zero and matching the pre-check value

kubectl get pods -A --field-selector=status.phase!=Running | grep -v Completed
mise exec -- flux get kustomizations -A | awk 'NR==1 || $5!="True"'
```

Success = every ATTACHED volume on v1.12.1 (re-derive the count live), every
volume healthy,
**all three Longhorn scrape targets up with the full live volume count reporting
metrics and no
LonghornManagerDown firing**, and a byte-level read/write round-trip proven on a
Longhorn-backed PVC.

## 5) Rollback

**There is no clean rollback — Longhorn does not downgrade engines live.** This
is why pre-check (c) is mandatory.

If a volume misbehaves mid-drain:
1. Set the concurrency setting back to `0` **immediately** — this stops all
   further upgrades within seconds.
2. Leave already-upgraded volumes alone; they are on a newer, supported engine.
3. Treat any single broken volume as a restore-from-backup per
   `docs/sops/backup.md`.

**No PVC/PV deletes** under any circumstance — see `docs/sops/storage-safety.md`.

## 6) Interference notes

- **This is the half that carries the conflicts.** Five sibling plans declare
  `conflicts_with: longhorn-1.12.1-engine`: `cilium-1.20.1`,
  `superset-pg-cutover`, `superset-6.1.0`, `bitnamilegacy-exit-paperless-db`,
  `bitnamilegacy-exit-nextcloud-db`. Their stated reasons are all about the
  engine work specifically ("must not run under storage-engine work", "never
  pair storage-engine work with new-volume creation", "live engine upgrade
  rides the network the agents blip"). Those declarations remain correct and
  unedited after the split, because this file kept the `longhorn-1.12.1-engine`
  plan_id.
- **`shared: [storage]` is load-bearing.** Every stateful app rides Longhorn.
- **The drain is ASYNCHRONOUS and unbounded.** `est_duration_min: 45` covers the
  attended portion (pre-checks, flipping the setting, confirming the drain has
  started cleanly and is progressing). With concurrency 1 across ~90 volumes the
  tail can run well past the window. **The conflicting plans need the drain
  COMPLETE, not the window ended** — that asymmetry is precisely why this was
  split out of the chart bump, and it is why this plan is scheduled LAST in the
  2026-08-19 ad-hoc session with an explicitly accepted async tail.
- Never run in the same window as a Talos node roll: a node reboot during a live
  engine upgrade is the worst case.
- Incremental by design: with concurrency 1 the blast radius at any instant is a
  single volume on a single node.
