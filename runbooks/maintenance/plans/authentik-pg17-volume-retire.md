---
plan_id: authentik-pg17-volume-retire
component: authentik
pr: null
kind: infra
current: "PV data-authentik-postgresql-0 Released/Retain/longhorn-static + Longhorn volume storage/data-authentik-postgresql-0 detached (frozen 2026-08-19 pre-cutover postgres 17.11 data, 2 snapshots), 9 Completed backups"
target: "PV + Longhorn volume data-authentik-postgresql-0 (and its 2 snapshots) deleted; all 9 Longhorn backups KEPT"
update_type: decommission
risk: medium                      # small blast radius, but it deletes the last ON-CLUSTER copy
                                  # of the pre-cutover data, and the live auth DB volume
                                  # (authentik-pg-data) is the obvious fat-finger neighbour
est_duration_min: 50              # ~20 restore proof + 5 deletes + 15 verification waits + 10 docs
needs_reboot: false
touches:
  namespaces: [storage, kube-system, databases]
  resources:
    - pv/data-authentik-postgresql-0                                   # deleted (cluster-scoped; bound to ns kube-system, PVC already gone)
    - volumes.longhorn.io/data-authentik-postgresql-0                  # deleted (ns storage) + its engine/2 replicas by cascade
    - snapshots.longhorn.io/authentik-pg17-decommission-preflight-20260926   # deleted by ownerRef cascade (explicit by-name fallback)
    - snapshots.longhorn.io/daily-ba-d5638786-bd2a-4d57-979d-26e28fd6e608    # deleted by ownerRef cascade
    - "restore-proof scratch volume/pv/pvc/pod (label restore-proof=true, ns storage + databases) — created and torn down by runbooks/backup-restore-proof.py in §3.1"
    - "docs/applications.md, docs/sops/authentik.md, docs/sops/disaster-recovery.md (the 'kept' wording, §3.5)"
    - "NOT touched, by design: backupvolumes.longhorn.io/data-authentik-postgresql-0-6dd5bdc0 and its 9 backups.longhorn.io; volumes.longhorn.io/authentik-pg-data (the LIVE auth DB); deploy/authentik-pg"
  shared: [storage/longhorn]      # restore proof reads the CIFS backup target and builds a scratch volume
depends_on: []                    # 2026-09-26: was [authentik-pg17-decommission] (its premises
                                  # read this PV/volume). That plan EXECUTED and was retired in
                                  # 2b82a7f4 (07:35 CEST) while this draft was written, so the
                                  # ordering is satisfied and the ref would be a DEAD-REF.
conflicts_with:
  - talos-1.14.1                  # node roll: its Longhorn gates enumerate the not-healthy /
                                  # detached volume set and total count (94); this plan changes
                                  # both, and a restore proof mid-roll competes for replicas.
                                  # talos-1.14.1 already lists authentik-pg17-decommission for
                                  # the same reason; the reciprocal entry for THIS plan is owed
                                  # there (not edited here — see §6).
exclusive: false
security_ref: null
capability_change: false
rollback_class: backup-restore
backup_gate: >-
  BEFORE the PV or volume is deleted, all four must pass, in order:
  (a) backups.longhorn.io/authentik-pg17-decommission-preflight-20260926 (ns storage)
  is Completed with status.volumeName == data-authentik-postgresql-0 (premise
  preflight-backup-completed), and the volume has >= 9 Completed backups (premise
  nine-completed-backups);
  (b) that backup's status.size is non-zero (2761949184 measured 2026-09-26);
  (c) RESTORE PROOF, executed live: `runbooks/backup-restore-proof.py --volume
  data-authentik-postgresql-0 --image postgres:17.11-bookworm --pgdata
  /var/lib/postgresql/data/data --superuser authentik --smoke-table
  authentik.authentik_core_user` exits 0, its `proving:` line names
  authentik-pg17-decommission-preflight-20260926, and its RESTORE PROVEN line
  reports authentik_core_user > 0 rows;
  (d) the probe's scratch objects are gone (`kubectl get volumes.longhorn.io -n
  storage -l restore-proof=true` → No resources found).
  Any failure → STOP, delete nothing. The backups are NEVER deleted by this plan;
  retention is indefinite (see §1 "Retention").
finding_refs: []                  # checked 2026-09-26: `finding list --grep` authentik /
                                  # data-authentik / postgresql-0 / detached / 17.11 — no finding
                                  # for this volume. F-8ab2ee07 (the 17.11 pin phantom) is owned
                                  # by authentik-pg17-decommission and is NOT claimed here.
status: draft
window: null
premises:
  # All read-only, pipe-free jq stages (plan-premises refuses ; && > etc.).
  # Each was dry-run 2026-09-26 against the negative control named in its `why`.
  - id: pv-released-retain-longhorn-static
    why: >-
      The PV is Released (no PVC bound), Retain (deleting it cannot trigger a CSI
      DeleteVolume) and longhorn-static. Control: the same read on
      pv/authentik-pg-data prints "Bound Retain longhorn-static" and fails.
    run: kubectl get pv data-authentik-postgresql-0 -o jsonpath='{.status.phase} {.spec.persistentVolumeReclaimPolicy} {.spec.storageClassName}'
    expect_exact: Released Retain longhorn-static
  - id: pv-is-longhorn-no-subdir
    why: >-
      Storage-safety pre-flight, structural half: the driver is Longhorn and there
      is no subdir attribute (the CIFS root-subdir STOP branch cannot apply). A
      CIFS PV would print "smb.csi.k8s.io [<subdir>]" and fail.
    run: kubectl get pv data-authentik-postgresql-0 -o jsonpath='{.spec.csi.driver} [{.spec.csi.volumeAttributes.subdir}]'
    expect_exact: driver.longhorn.io []
  - id: no-pvc-names-or-binds-it
    why: >-
      No PVC anywhere is named data-authentik-postgresql-0 or has it as
      spec.volumeName. Prints the match count. Control: the same pipeline with
      -x authentik-pg-data prints 2 (name + volumeName) and fails.
    run: kubectl get pvc -A -o json | jq -r '.items[].metadata.name, .items[].spec.volumeName' | grep -c -x data-authentik-postgresql-0
    expect_exact: "0"
  - id: no-pod-references-authentik-postgresql
    why: >-
      No pod (any namespace) references authentik-postgresql in any field.
      Control: grep -c authentik-pg on the same JSON prints 23 and fails.
    run: kubectl get pods -A -o json | grep -c authentik-postgresql
    expect_exact: "0"
  - id: no-workload-named-authentik-postgresql
    why: "The bundled StatefulSet is gone (decommission step 1). Prints the match count."
    run: kubectl get sts,deploy -A -o name | grep -c authentik-postgresql
    expect_exact: "0"
  - id: old-volume-detached
    why: >-
      The Longhorn volume exists, is detached and sees its PV Released. Control:
      volume authentik-pg-data prints "attached Bound" and fails.
    run: kubectl get volumes.longhorn.io -n storage data-authentik-postgresql-0 -o jsonpath='{.status.state} {.status.kubernetesStatus.pvStatus}'
    expect_exact: detached Released
  - id: preflight-backup-completed
    why: >-
      The named recovery floor exists, is Completed and belongs to this volume.
      A missing CR fails on NotFound.
    run: kubectl get backups.longhorn.io -n storage authentik-pg17-decommission-preflight-20260926 -o jsonpath='{.status.state} {.status.volumeName}'
    expect_exact: Completed data-authentik-postgresql-0
  - id: nine-completed-backups
    why: >-
      The full kept set (9 Completed on 2026-09-26: 7 dailies 09-18..09-24, the
      preflight, the 2026-01-04 original). Control: selector
      backup-volume=does-not-exist prints 0 and fails.
    run: kubectl get backups.longhorn.io -n storage -l backup-volume=data-authentik-postgresql-0 -o jsonpath='{range .items[*]}{.status.state}{"\n"}{end}' | grep -c -x Completed
    expect_matches: '^(9|[1-9][0-9])$'
  - id: backupvolume-present
    why: >-
      The BackupVolume that OWNS the 9 backups exists (deleting it would cascade
      them; this plan never does). NotFound fails.
    run: kubectl get backupvolumes.longhorn.io -n storage data-authentik-postgresql-0-6dd5bdc0 -o jsonpath='{.spec.volumeName}'
    expect_exact: data-authentik-postgresql-0
  - id: live-auth-volume-healthy
    why: >-
      The fat-finger neighbour — the LIVE authentik DB volume — is attached and
      healthy before we start; §4 re-reads it after. Control: the old volume
      prints "detached unknown" and fails.
    run: kubectl get volumes.longhorn.io -n storage authentik-pg-data -o jsonpath='{.status.state} {.status.robustness}'
    expect_exact: attached healthy
  - id: leftover-snapshot-present
    why: >-
      The leftover on-demand snapshot is still on the old volume (false by design
      after this plan runs). NotFound fails.
    run: kubectl get snapshots.longhorn.io -n storage authentik-pg17-decommission-preflight-20260926 -o jsonpath='{.spec.volume}'
    expect_exact: data-authentik-postgresql-0
sops_refs:
  - docs/sops/storage-safety.md
  - docs/sops/longhorn.md
  - docs/sops/backup.md
  - docs/sops/authentik.md
generated: "2026-09-26"
---

# Retire the frozen authentik postgres 17.11 volume

## 1. Summary & why held

**Operator decision 2026-09-26:** take option (b) of
`authentik-pg17-decommission` §"Known consequence" — retire the PV and Longhorn
volume `data-authentik-postgresql-0` instead of keeping them detached forever.
This is not a held version bump. No Renovate PR exists (`pr: null`). The plan
has no GO of its own and is written as a reviewable draft.

**What the data is.** This is the bundled chart postgres (official
`postgres:17.11-bookworm` image in a bitnami-style layout, `PGDATA=/bitnami/postgresql/data`,
so the data dir sits at `data/` on the volume root). It was frozen at the
2026-08-19/20 cutover. authentik has run on `deploy/authentik-pg` (postgres
18.6, volume `authentik-pg-data`) since 2026-08-20. The StatefulSet was retired on
2026-09-24 (`5f162456`), and the PVC was deleted by the operator on the same day
(PV `Released` at 2026-09-24T17:41:36Z, recorded in `e6e31d44`). No current
authentik data lives here. The history is in plan `authentik-pg17-decommission`,
which was executed and retired in `2b82a7f4` (read it with
`git show 2b82a7f4^:runbooks/maintenance/plans/authentik-pg17-decommission.md`).
Its residual R2 **purged the Mac-mini dump** `~/db-dumps/authentik-pg17-2026-08-20.dump`
on 2026-09-26. The 9 Longhorn backups plus this volume are therefore the only
copies of the pre-cutover data (Time Machine aside), and once this plan runs
the **backups alone** remain. That is why §3.1 is a live restore proof and not
a status check.

**Live state, measured read-only 2026-09-26:**

| Object | Reading |
|---|---|
| `pv/data-authentik-postgresql-0` | `Released`, `Retain`, `longhorn-static`, driver `driver.longhorn.io`, volumeAttributes `{diskSelector:"", nodeSelector:"", numberOfReplicas:"2", staleReplicaTimeout:"20"}`: **no `subdir`**. Finalizers `kubernetes.io/pv-protection`, `external-attacher/driver-longhorn-io`. No `storage.k8s.io` VolumeAttachment references it. |
| `volumes.longhorn.io/data-authentik-postgresql-0` (ns storage) | `detached`, robustness `unknown`, 20 GiB, actualSize ~1.4 GB, 2 replicas (`-r-4e43d658` on nuc14-01, `-r-83b6f41f` on nuc14-02, both `stopped`), engine `-e-0` `stopped`, Longhorn VolumeAttachment tickets `{}`. Label `recurring-job-group.longhorn.io/default: enabled`. |
| Snapshots on it | `authentik-pg17-decommission-preflight-20260926` (user-created 05:02:21Z) and `daily-ba-d5638786-…` (2026-09-24 03:00Z), both with ownerReference → the Volume (uid `8c9d69c2-…`). |
| Backups (BackupVolume `data-authentik-postgresql-0-6dd5bdc0`) | **9 Completed**: `authentik-pg17-decommission-preflight-20260926` (created 2026-09-26T05:02:36Z, size 2761949184, url `cifs://192.168.55.240/backups?backup=authentik-pg17-decommission-preflight-20260926&volume=data-authentik-postgresql-0`), 7 dailies 2026-09-18 → 09-24, and `backup-b6619f46ad37492d` (2026-01-04, the backup this volume was itself restored from). |
| Consumers | 0 PVCs name or bind it, 0 pods reference `authentik-postgresql`, 0 StatefulSets/Deployments of that name. |
| GitOps | **No manifest for this PV or volume exists in git** (`git grep data-authentik-postgresql-0 -- kubernetes/` matches only a comment in `longhorn-alerts.yaml`). The PV came from a 2026-01 migration and the Volume CR was hand-created. So the delete in §3 is manual. There is no GitOps path for it, which is the same shape as `superset-pg-decommission` §4.5. |

**Why it needs a plan (not a one-liner).** It deletes the last *on-cluster*
copy of the pre-cutover dataset. The backup that replaces it has never been
restored. And `authentik-pg-data` (the live SSO database) sits in the same
namespace under a similar name. The gate is therefore a live restore proof,
not a CR status.

**Retention (the backups are KEPT — this plan never deletes a backup).** Once
the volume is gone, no RecurringJob acts on it again. `daily-backup-all-volumes`
(`retain: 7`) prunes only when it runs *for* a volume, so all 9 backups stay
frozen **indefinitely**. They are removed only by an explicit operator
decision, which is not part of this plan. Longhorn `auto-cleanup-when-delete-backup`
is `false`. **Never delete `backupvolumes.longhorn.io/data-authentik-postgresql-0-6dd5bdc0`**:
deleting it cascades to all 9 backups (same rule as
`superset-pg-data-26df02ea`, `docs/sops/postgres-major-upgrade.md`). The
off-site cloud copy of the NAS `backups` share follows its own owner-managed
retention (`docs/sops/backup.md`). The backups hold password hashes, MFA secrets
and session tokens as of 2026-08-19. That is the reason nobody should casually
restore them, and it is not a reason to delete them under this plan.

## Known consequence — LonghornVolumeSnapshotChainNotPruned until this runs

The on-demand backup left a **second** snapshot on this detached volume.
`allow-recurring-job-while-volume-detached` is `false`, so the 02:30
`global-snapshot-cleanup` skips the volume and never prunes it. Measured
2026-09-26: `count(longhorn_snapshot_actual_size_bytes{volume="data-authentik-postgresql-0"})` = 2,
30h `count_over_time` = 180. The rule (`kubernetes/apps/monitoring/kube-prometheus-stack/app/longhorn-alerts.yaml`,
30h `min_over_time` ≥ 2, `for: 30m`) therefore **starts firing around
2026-09-27 11:30Z** (30h after the 05:02Z snapshot, plus 30m). **It keeps
firing until this plan runs.** It is expected: do not chase it, and do not
"fix" it by attaching the volume or flipping the detached-recurring-job
setting. If a silence is wanted meanwhile, scope it to
`alertname=LonghornVolumeSnapshotChainNotPruned, volume=data-authentik-postgresql-0`
only. It resolves within minutes of §3.4. The rule's RHS joins on
`longhorn_volume_capacity_bytes`, which stops being exported when the volume
is deleted.

## 2. Pre-checks (in the window, before anything is touched)

```bash
cd /Users/mu/code/cberg-home-nextgen

# 2.1 Premises — every one must PASS. Any FAIL -> STOP, touch nothing.
.venv/bin/python3 runbooks/plan-premises.py authentik-pg17-volume-retire --require-premises

# 2.2 The predecessor is done: authentik-pg17-decommission was executed and its
#     file retired in 2b82a7f4. Confirm nobody resurrected it (a live copy would
#     carry premises that read the objects deleted below).
git log -1 --format='%h %s' -- runbooks/maintenance/plans/authentik-pg17-decommission.md
test ! -e runbooks/maintenance/plans/authentik-pg17-decommission.md && echo "predecessor retired"
# EXPECT: 2b82a7f4 ... retire plan  AND  "predecessor retired". Otherwise -> STOP.

# 2.3 Not inside Longhorn's nightly jobs: do NOT start between 02:00 and 03:30 UTC
#     (trim 02:00, snapshot-cleanup 02:30, backups 03:00 all hit the backup
#     target the restore proof reads from).
date -u +%H:%M

# 2.4 Cluster quiet: no degraded/faulted volume, Flux clean
kubectl get volumes.longhorn.io -n storage -o json | python3 -c "
import sys,json
d=json.load(sys.stdin)['items']
bad=[(v['metadata']['name'],v['status'].get('robustness'),v['status'].get('state')) for v in d if v['status'].get('robustness')!='healthy']
print('total',len(d),'not-healthy',len(bad))
for b in bad: print('  ',b)"
# 2026-09-26: total 94, not-healthy 2 = data-authentik-postgresql-0 (unknown, detached)
# and pvc-f6ec0213-… (icloud-docker-andrea-session). Any degraded/faulted -> STOP.
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
```

### 2.5 STORAGE-SAFETY PRE-FLIGHT — run and RECORD it, even though this is Longhorn

The CLAUDE.md one-liner starts from the **PVC**
(`kubectl -n $NS get pvc $PVC -o jsonpath='{.spec.volumeName}'`). That PVC was
deleted on 2026-09-24, so as written the one-liner yields `PV=""`. With an
empty name, `kubectl get pv "" -o jsonpath='{.spec.csi.volumeAttributes}'`
prints nothing and `reclaim=` comes out empty: a **silently empty pre-flight**.
Run the PV-rooted form with the PV named explicitly:

```bash
PV=data-authentik-postgresql-0
kubectl get pv "$PV" -o jsonpath='{.spec.csi.driver}{"\n"}'                       # (0) driver
kubectl get pv "$PV" -o jsonpath='{.spec.csi.volumeAttributes}' | jq              # (1) subdir?
echo "reclaim=$(kubectl get pv "$PV" -o jsonpath='{.spec.persistentVolumeReclaimPolicy}')"   # (2)
SC=$(kubectl get pv "$PV" -o jsonpath='{.spec.storageClassName}')
kubectl get sc "$SC" -o jsonpath='{.metadata.name} {.provisioner} {.reclaimPolicy}{"\n"}'  # (3)
```

**Expected (measured 2026-09-26), paste the actual output into the window log:**

| Step | Reading | Meaning |
|---|---|---|
| (0) | `driver.longhorn.io` | Block device, not a share. |
| (1) | `{"diskSelector":"","nodeSelector":"","numberOfReplicas":"2","staleReplicaTimeout":"20"}` | **No `subdir` key.** The `subdir: /` STOP branch is structurally inapplicable: a Longhorn volume is its own ext4 block device, not a directory inside a shared export, so no sibling app's data sits under a common parent. That conclusion comes from the reading above, not from an assumption. |
| (2) | `reclaim=Retain` | Deleting the PV does **not** call CSI DeleteVolume, so the Longhorn volume survives step 3.3 and is removed only by the explicit step 3.4. |
| (3) | `longhorn-static driver.longhorn.io Delete` | The class default is `Delete`. Only the PV overrides it. It does not matter here (no new PV is provisioned), but it is why (2) must be read live every time. |

**STOP if:** (0) is anything but `driver.longhorn.io`, (1) contains a `subdir`
key, or (2) is not `Retain`.

**Blast radius, stated:** exactly one 20 GiB Longhorn volume, its 2 replicas,
its engine and its 2 snapshots. Every command names the object explicitly.
**Never** use a glob, a label selector for a delete, or `grep authentik`:
`authentik-pg-data` (the live SSO DB) is one `grep` away.

### 2.6 Baselines (§4 compares against these)

```bash
# Backup inventory — the thing that must survive
kubectl get backups.longhorn.io -n storage -l backup-volume=data-authentik-postgresql-0 -o json \
 | python3 -c "
import sys,json
for b in json.load(sys.stdin)['items']:
    s=b.get('status',{})
    print(b['metadata']['name'], s.get('state'), s.get('volumeName'), s.get('backupCreatedAt'), s.get('size'))" \
 | sort > /tmp/authentik-pg17-backups-before.txt
wc -l < /tmp/authentik-pg17-backups-before.txt            # EXPECT 9
grep -c ' Completed ' /tmp/authentik-pg17-backups-before.txt   # EXPECT 9

# Live auth DB contents — proves afterwards the LIVE DB was not the thing touched
kubectl exec -n kube-system deploy/authentik-pg -- psql -U authentik -d authentik -Atc \
  'select count(*) from authentik_core_user' | tee /tmp/authentik-live-users-before.txt

# PV object, for the partial-rollback case in §5.1 only
kubectl get pv data-authentik-postgresql-0 -o yaml > /tmp/authentik-pg17-pv.yaml
```

## 3. Steps

### 3.1 backup_gate — restore proof of the named backup (do this FIRST, in full)

(a) and the 9-count are premises (§2.1). Then:

```bash
# (b) non-zero size
kubectl get backups.longhorn.io -n storage authentik-pg17-decommission-preflight-20260926 -o jsonpath='{.status.size}{"\n"}'
# EXPECT 2761949184 (any non-zero value within 20% of it; 0 or empty -> STOP)

# (c) restore proof: restores the NEWEST Completed backup into a scratch
#     1-replica volume, boots postgres 17.11 on it, counts rows, tears down.
#     The source volume is never touched.
.venv/bin/python3 runbooks/backup-restore-proof.py \
  --volume data-authentik-postgresql-0 \
  --image postgres:17.11-bookworm \
  --pgdata /var/lib/postgresql/data/data \
  --superuser authentik \
  --smoke-table authentik.authentik_core_user
echo "rc=$?"
```

**PASS requires all three:** `rc=0`, a `proving:` line naming
`authentik-pg17-decommission-preflight-20260926`, and a `RESTORE PROVEN` line
showing `authentik.authentik_core_user=<N> rows` with **N > 0**.

- The probe mounts the volume root at `/var/lib/postgresql/data`, and the old
  chart kept PGDATA at `<root>/data`, hence `--pgdata /var/lib/postgresql/data/data`.
  If `postgres` never becomes ready and the pod log says it cannot find
  `PG_VERSION`/`postgresql.conf`, the path is wrong. That is a plan defect, not
  a bad backup: STOP and do not delete. Re-run with `--keep` and
  `kubectl exec` into the scratch pod to `ls` the mount.
- `rc=2` with `INCONCLUSIVE` means postgres booted, which proves the restore,
  but the role guess missed. Re-run once with `--superuser postgres`. The gate
  needs the row count, so INCONCLUSIVE alone is **not** a pass.
- `rc=2` with `PRECONDITION: leftover restore-proof volume(s)` means another
  proof run's leftovers exist. Do not delete them blind; find their owner first.
- **Not yet executed against this volume.** The flags above are derived from
  the recorded layout (`authentik-postgres-18` §"re-measured at 2026.8.0":
  image `postgres:17.11-bookworm`, `PGDATA=/bitnami/postgresql/data`, mount
  `/bitnami/postgresql`). Planning was read-only, so this gate's first real
  run is in the window.

```bash
# (d) scratch objects gone
kubectl get volumes.longhorn.io -n storage -l restore-proof=true    # EXPECT: No resources found
kubectl get pv -l restore-proof=true                                # EXPECT: No resources found
```

Any failure in (a)–(d) → **STOP. Leave every object in place.** The alert in
"Known consequence" keeps firing, and nothing is lost.

### 3.2 Recurring-job group — NOT needed (checked, recorded)

The volume carries `recurring-job-group.longhorn.io/default: enabled`. That
label lives on the Volume CR, so it disappears when the volume is deleted in 3.4,
and nothing else references the volume by name (all 11 RecurringJobs select
by group, not by volume). Until then every job skips the volume because it is
detached (`allow-recurring-job-while-volume-detached=false`). Removing the label
first would be an extra mutation with no effect, so it is deliberately not done.
The only requirement is timing, covered by §2.3.

### 3.3 Delete the PV (by name)

```bash
kubectl delete pv data-authentik-postgresql-0 --wait=true --timeout=120s
kubectl get pv data-authentik-postgresql-0          # EXPECT: NotFound
```

With `Retain` this removes only the Kubernetes object. Longhorn keeps the
volume, and Longhorn's `kubernetesStatus` for it clears. If the PV sits in
`Terminating` past the timeout, **do not strip finalizers**. Check
`kubectl get volumeattachments.storage.k8s.io | grep data-authentik-postgresql-0`
(none existed at planning), then STOP and escalate. §5.1 recreates the PV.

### 3.4 Delete the Longhorn Volume CR (by name, fully-qualified kind)

```bash
kubectl -n storage delete volumes.longhorn.io data-authentik-postgresql-0 --wait=true --timeout=300s
# NOT a glob, NOT a selector, NOT `grep authentik`. authentik-pg-data MUST survive.
kubectl -n storage get volumes.longhorn.io data-authentik-postgresql-0      # EXPECT: NotFound
kubectl -n storage get volumes.longhorn.io authentik-pg-data -o jsonpath='{.status.state} {.status.robustness}{"\n"}'   # EXPECT: attached healthy
```

This deletes the engine, both replicas (with their on-disk data on nuc14-01 and
nuc14-02) and every snapshot in the chain. The BackupVolume and its 9 backups
live in the backup target and are **not** affected.

### 3.5 The leftover snapshot(s)

Both Snapshot CRs carry an ownerReference to the Volume, so they are
garbage-collected with it. The snapshot data itself lived in the replicas
deleted in 3.4. Deleting the snapshot *before* the volume buys nothing: its
data goes with the replicas anyway, and on a detached volume Longhorn can need
to bring the engine up to purge a snapshot. So 3.4 comes first, and here we confirm:

```bash
kubectl -n storage get snapshots.longhorn.io -l longhornvolume=data-authentik-postgresql-0
# EXPECT: No resources found (allow up to 5 min for GC).
# Only if one lingers after 5 min, delete it BY NAME with the FULLY-QUALIFIED kind:
kubectl -n storage delete snapshots.longhorn.io authentik-pg17-decommission-preflight-20260926
```

**Name-collision trap:** the Backup CR has the **same name** as this snapshot.
`kubectl delete backups.longhorn.io authentik-pg17-decommission-preflight-20260926`
would delete the recovery floor this plan's gate just proved. Always type
`snapshots.longhorn.io` in full, and never the short `snapshot` (VolumeSnapshot
CRDs are also installed). If a snapshot is stuck on its `longhorn.io` finalizer,
STOP; do not patch the finalizer away.

### 3.6 Documentation: "kept" becomes "deleted, backups kept"

Three docs say the PV and volume are *kept*. After 3.4 that sends a reader
looking for objects that no longer exist. In one commit:

1. `docs/applications.md` (authentik row, currently line 181). Replace
   "its PV/Longhorn volume `data-authentik-postgresql-0` and backups are kept as a frozen pre-cutover (2026-08-19) snapshot — never restore it to recover current authentik data."
   with
   "its PV and Longhorn volume `data-authentik-postgresql-0` were deleted <YYYY-MM-DD> by plan `authentik-pg17-volume-retire`; its 9 Longhorn backups (BackupVolume `data-authentik-postgresql-0-6dd5bdc0`, newest `authentik-pg17-decommission-preflight-20260926`, restore-proven <YYYY-MM-DD>) are kept as a frozen pre-cutover (2026-08-19) copy — never restore them to recover current authentik data."
2. `docs/sops/authentik.md` (currently lines 43–47). Replace "The PV and Longhorn volume `data-authentik-postgresql-0` are `Retain` and its Longhorn backups are kept as the pre-cutover recovery floor." with "The PV and Longhorn volume `data-authentik-postgresql-0` were deleted <YYYY-MM-DD> (plan `authentik-pg17-volume-retire`); its Longhorn backups are kept as the pre-cutover recovery floor — restore via `runbooks/backup-restore-proof.py --keep` (flags in that plan's §3.1)." Keep the "Never restore that volume to recover authentik" sentence, reworded to "those backups".
3. `docs/sops/disaster-recovery.md` (currently line 368). Replace "Its PV/Longhorn volume `data-authentik-postgresql-0` and backups are KEPT but hold a frozen 2026-08-19 snapshot." with "Its PV/Longhorn volume `data-authentik-postgresql-0` was deleted <YYYY-MM-DD>; its Longhorn backups are KEPT but hold a frozen 2026-08-19 snapshot."
4. The predecessor plan file is already retired (`2b82a7f4`), so there is no
   "Known consequence" section left to annotate. The commit message of this
   step records "option (b) chosen 2026-09-26, executed by `authentik-pg17-volume-retire`".

```bash
rg -n "data-authentik-postgresql-0" docs/     # every remaining hit must say deleted / backups kept
git commit --only docs/applications.md docs/sops/authentik.md docs/sops/disaster-recovery.md \
  -F "msg-authentik-pg17-volume-retire-$(date +%s).txt"
git show --stat HEAD && git log -1 --format=%s   # every file yours, subject yours
git push
```

## 4. Verification

Every gate below states what its failure prints, and each was measured on
2026-09-26 in the state where it would fail.

**V1 — the three objects are gone (and only they).**
```bash
kubectl get pv data-authentik-postgresql-0                                   # EXPECT NotFound
kubectl -n storage get volumes.longhorn.io data-authentik-postgresql-0       # EXPECT NotFound
kubectl -n storage get replicas.longhorn.io,engines.longhorn.io,snapshots.longhorn.io -l longhornvolume=data-authentik-postgresql-0   # EXPECT No resources found
kubectl -n storage get replicas.longhorn.io,engines.longhorn.io -l longhornvolume=authentik-pg-data --no-headers | wc -l   # CONTROL: > 0 (the selector reads)
```
Failure prints the object (today: the PV `Released`, the volume `detached`, 2
replicas + 1 engine + 2 snapshots). Re-run the §2.4 count as well: EXPECT
`total 93` and `data-authentik-postgresql-0` absent from the not-healthy list.

**V2 — the backups survived (the assertion that makes this `backup-restore`, not `one-way`).**
Wait ≥ 6 min after 3.4. The backup target `pollInterval` is 5m, so Backup CRs
are re-synced from the store at least once. Then:
```bash
kubectl get backups.longhorn.io -n storage -l backup-volume=data-authentik-postgresql-0 -o json \
 | python3 -c "
import sys,json
for b in json.load(sys.stdin)['items']:
    s=b.get('status',{})
    print(b['metadata']['name'], s.get('state'), s.get('volumeName'), s.get('backupCreatedAt'), s.get('size'))" \
 | sort > /tmp/authentik-pg17-backups-after.txt
diff /tmp/authentik-pg17-backups-before.txt /tmp/authentik-pg17-backups-after.txt && echo BACKUPS-IDENTICAL
kubectl get backupvolumes.longhorn.io -n storage data-authentik-postgresql-0-6dd5bdc0 -o jsonpath='{.status.lastBackupName}{"\n"}'
# EXPECT authentik-pg17-decommission-preflight-20260926
```

CONTENTS ASSERTION: the 9 backups of `data-authentik-postgresql-0` still exist
and are Completed with unchanged size and timestamps after the volume delete.
Measured by the before/after `diff` above, compared to the §2.6 baseline. A
silent diff prints `BACKUPS-IDENTICAL`. Any missing or changed row prints a
`<` line and fails. Combined with §3.1(c), this proves a recoverable copy of
the data exists, not just a list entry.

CONTENTS ASSERTION: the live auth DB was not the object touched. Re-run the
§2.6 `select count(*) from authentik_core_user` on `deploy/authentik-pg` and
diff it against `/tmp/authentik-live-users-before.txt`. It must be identical
and non-zero. `authentik-pg-data` must read `attached healthy` (3.4).

**V3 — the snapshot series and the alert are gone for this volume, with a scrape control.**
```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
q(){ curl -s --data-urlencode "query=$1" http://localhost:19090/api/v1/query | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['result'])"; }
q 'count(longhorn_snapshot_actual_size_bytes{volume="data-authentik-postgresql-0"})'   # EXPECT []   (baseline 2026-09-26: value 2)
q 'count(longhorn_snapshot_actual_size_bytes)'                                         # CONTROL: EXPECT > 0 (baseline 97)
q 'count(longhorn_volume_capacity_bytes{volume="data-authentik-postgresql-0"})'        # EXPECT []   (baseline 1)
q 'ALERTS{alertname="LonghornVolumeSnapshotChainNotPruned",volume="data-authentik-postgresql-0"}'  # EXPECT [] (re-check 15 min after 3.4)
q 'ALERTS{alertname="LonghornSnapshotMetricsAbsent"}'                                   # EXPECT []
kill $PF 2>/dev/null
```
An empty result is only evidence when the fleet-wide count is non-zero. If
`count(longhorn_snapshot_actual_size_bytes)` is also empty, the scrape is down
and the volume-scoped `[]` proves nothing: STOP and treat V3 as UNMEASURED. If
the alert had not started firing yet when the plan ran (before ~2026-09-27
11:30Z), the ALERTS line is vacuous. The series-count line is then the gate.

CONTROL: metric longhorn_snapshot_actual_size_bytes — volume-scoped count must be empty after 3.4 (baseline 2) while the fleet-wide count stays > 0 (baseline 97).
CONTROL: metric longhorn_volume_capacity_bytes — the series for data-authentik-postgresql-0 must be gone (baseline 1); it is the RHS join that keeps the alert alive.
CONTROL: alertname LonghornVolumeSnapshotChainNotPruned — not firing for volume=data-authentik-postgresql-0 15 min after 3.4.
CONTROL: alertname LonghornSnapshotMetricsAbsent — not firing (otherwise V3 is blind).

## 5. Rollback

There is no service to roll back: nothing reads this data. "Rollback" means
**getting the pre-cutover dataset back on the cluster**, which the operator may
want for forensics.

**5.1 PV deleted, volume NOT yet deleted (3.3 done, 3.4 not).** Recreate the PV
from the saved object, minus server-set fields. It comes back `Available`, and
Longhorn re-links it by `volumeHandle`:
```bash
.venv/bin/python3 - <<'EOF'   # needs PyYAML (the repo venv has it)
import yaml
d=yaml.safe_load(open('/tmp/authentik-pg17-pv.yaml'))
for k in ('uid','resourceVersion','creationTimestamp','finalizers','managedFields'): d['metadata'].pop(k,None)
d['spec'].pop('claimRef',None); d.pop('status',None)
yaml.safe_dump(d,open('/tmp/authentik-pg17-pv-clean.yaml','w'))
EOF
kubectl apply -f /tmp/authentik-pg17-pv-clean.yaml
kubectl get pv data-authentik-postgresql-0 -o jsonpath='{.status.phase} {.spec.csi.volumeHandle}{"\n"}'   # EXPECT Available data-authentik-postgresql-0
```

**5.2 Volume deleted (3.4 done). Restore from the kept backup.** Longhorn can
only restore under a *free* name, and the original name is free again. Still,
use a NEW speaking name so nobody mistakes it for a live object:

*Fast path (read-only look, auto-cleaned):* the §3.1 probe with `--keep` leaves
a restored scratch volume, PV, PVC and a running `postgres:17.11-bookworm` pod
in ns `databases`:
```bash
.venv/bin/python3 runbooks/backup-restore-proof.py --volume data-authentik-postgresql-0 \
  --image postgres:17.11-bookworm --pgdata /var/lib/postgresql/data/data \
  --superuser authentik --smoke-table authentik.authentik_core_user --keep
# it prints the scratch name; `kubectl -n databases exec <scratch> -- psql -U authentik -d authentik`
```

*Durable path (a named volume):*
```bash
URL=$(kubectl -n storage get backups.longhorn.io authentik-pg17-decommission-preflight-20260926 -o jsonpath='{.status.url}')
# 2026-09-26: cifs://192.168.55.240/backups?backup=authentik-pg17-decommission-preflight-20260926&volume=data-authentik-postgresql-0
cat <<EOF | kubectl apply -f -
apiVersion: longhorn.io/v1beta2
kind: Volume
metadata: {name: authentik-pg17-frozen, namespace: storage}
spec:
  fromBackup: "$URL"
  numberOfReplicas: 2
  size: "21474836480"
  frontend: blockdev
  accessMode: rwo
  dataEngine: v1
EOF
# wait until restore finishes:
kubectl -n storage get volumes.longhorn.io authentik-pg17-frozen -o jsonpath='{.status.restoreRequired} {.status.state}{"\n"}'   # EXPECT false detached
```
Then create a PV and PVC per `docs/sops/backup.md` §"Bind Restored Volume",
Case A. PV `authentik-pg17-frozen`: `longhorn-static`, `Retain`, 20Gi,
`volumeHandle: authentik-pg17-frozen`, `numberOfReplicas: "2"`. PVC
`authentik-pg17-frozen` in `kube-system` with `volumeName: authentik-pg17-frozen`.
Read it with a throwaway pod: image `postgres:17.11-bookworm`, mount the PVC at
`/var/lib/postgresql/data`, env `PGDATA=/var/lib/postgresql/data/data`.
Confirm with
`psql -U authentik -d authentik -Atc 'select count(*) from authentik_core_user'`
(non-zero). **Never point authentik at it.** It is frozen at 2026-08-19 and
holds stale credentials/MFA state. If the restored copy should stay, it becomes
a hand-applied `longhorn-static` volume and must be recorded like any other.
Otherwise delete PVC → PV → Volume again in that order.

Failure of 5.2 falls back to the other 8 Completed backups in the set, newest
first (dailies 09-24 → 09-18, then `backup-b6619f46ad37492d`).

## 6. Interference notes

- **Predecessor ordering is satisfied.** `authentik-pg17-decommission`'s
  residual premises read this PV, this volume and this backup, so this plan had
  to run after it. That plan executed (R1 + R2) and was retired in `2b82a7f4`
  on 2026-09-26, so `depends_on` is empty (§2.2 re-checks it). R2 already
  purged `~/db-dumps/authentik-pg17-2026-08-20.dump`. After this plan, the 9
  Longhorn backups are the only copies. That is the intended end state, and it
  is why the restore proof is a gate here.
- **conflicts_with `talos-1.14.1`** (`sun-attended:2026-09-27`). Its Longhorn
  gates hard-code the fleet: `total 94`, a not-healthy set of exactly two
  icloud-docker session volumes, `total replicas 192`. **That gate is ALREADY
  stale** (measured 2026-09-26): the not-healthy set is now
  `data-authentik-postgresql-0` + `pvc-f6ec0213-…` (icloud-docker-andrea);
  `icloud-docker-mu-session` is healthy, and the replica total reads 188. This
  plan would change it again (total 93, one fewer detached, 2 fewer stopped
  replicas). The reciprocal `conflicts_with: authentik-pg17-volume-retire` is
  owed in `talos-1.14.1` and was not edited here, because a planner writes only
  its own file.
- **Prometheus is the V3 instrument.** No `kube-prometheus-stack` bump is open:
  `kube-prometheus-stack-91.4.1` was executed on 2026-09-26, so nothing is
  listed. A future kps plan landing the same night must be added to
  `conflicts_with` on both sides.
- `flux-reconciler-impersonation` is `exclusive: true` and already keeps its
  slot to itself. `authentik-2026.8.3` does not interfere: it rolls
  authentik-server/worker/outposts on `authentik-pg`, while this plan touches
  only the dead volume.
- **Backup-target load.** The §3.1 restore proof pulls about 2.8 GB from the NAS
  `backups` share. Keep it away from 02:00–03:30 UTC (§2.3) and from any other
  plan's restore proof in the same window. The probe also refuses to start on
  leftovers.
- **Name traps:** `authentik-pg-data` (LIVE) vs `data-authentik-postgresql-0`
  (this plan), and Backup CR vs Snapshot CR both named
  `authentik-pg17-decommission-preflight-20260926`. Every delete in §3 names the
  object and the fully-qualified kind.
