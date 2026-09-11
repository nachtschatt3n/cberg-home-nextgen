---
plan_id: superset-pg-decommission
component: superset
pr: null
kind: infra
current: "Two retired Superset metadata DBs still hold cluster storage: the 20Gi longhorn-static volume `superset-pg-data` (postgres 17.11, workload retired 2026-09-09 in 9d10199c, PVC Bound with no consumer) and `superset-postgresql-data` (bundled bitnamilegacy postgres 14.17, workload retired 2026-09-05 in 90539942, same disposition). Both PVs are Retain; both volumes are detached; neither receives new daily backups."
target: "Both PVCs, PVs and Longhorn Volume CRs deleted and their manifests removed from git; ~80 GiB of scheduled Longhorn capacity released. The two FROZEN Longhorn backup sets are DELIBERATELY RETAINED and remain the restore path — retiring them is a separate, later decision (see §7)."
update_type: decommission
risk: medium                          # small blast radius, but it deletes the
                                      # last in-cluster copy of two metadata DBs
est_duration_min: 70
needs_reboot: false
touches:
  namespaces: [databases, storage]
  resources:
    - "pvc/superset-pg-data (databases)"
    - "pv/superset-pg-data"
    - "volume/superset-pg-data (storage, Longhorn CR — hand-applied, hand-deleted)"
    - "pvc/superset-postgresql-data (databases)"
    - "pv/superset-postgresql-data"
    - "volume/superset-postgresql-data (storage, Longhorn CR)"
    - kustomization/superset
  shared: [storage/longhorn]          # replica rebuild/space accounting is
                                      # cluster-wide; a delete perturbs it
depends_on: []
conflicts_with: []                    # deliberately EMPTY. The only plan that
                                      # could collide is another storage-deleting
                                      # one, and none exists today. Per the
                                      # brief's rule I do not write a forward
                                      # reference to a plan_id I cannot confirm
                                      # exists — a dangling ref silently disables
                                      # the guard (cleaned up on
                                      # paperclip-postgresql-18.6 this week).
capability_change: false              # nothing user-visible changes; Superset
                                      # has served off superset-pg18 since
                                      # 2026-09-08 08:36
rollback_class: backup-restore        # NOT one-way, and the distinction is the
                                      # whole design of this plan: the frozen
                                      # backup sets are retained, so the undo
                                      # path is "restore the backup into a new
                                      # volume", not "it is gone". It becomes
                                      # one-way only when §7 (backup retirement)
                                      # is separately decided and executed.
backup_gate: >-
  BEFORE any PVC/PV/Volume is deleted, all four must pass, in this order:
  (a) `kubectl -n storage get backups.longhorn.io` lists a backup for volume
  superset-pg-data with `.status.state == Completed` and
  `.status.backupCreatedAt >= 2026-09-09T00:00:00Z` — the newest one is the ONLY
  member of the set carrying the Superset 6.1.0 alembic schema (see §1.3), so an
  absent or non-Completed newest backup means STOP;
  (b) that backup's `.status.size` is non-zero and within 20% of the size of the
  09-08 daily for the same volume — a Completed backup of a detached volume that
  shrank by an order of magnitude is not a backup;
  (c) RESTORE PROOF, executed live, not asserted: restore that backup into a
  scratch volume `superset-pg-restoreproof`, attach it to a throwaway
  `postgres:17.11-alpine` pod, start postgres and run BOTH
  `select count(*) from ab_user;` (must be >0) and
  `select version_num from alembic_version;` (must be non-empty and must equal
  the value recorded in §1.3). A restore that mounts but whose ab_user is empty
  is exactly the failure this gate exists to catch;
  (d) the scratch volume is deleted again and Longhorn reports no degraded or
  rebuilding volume cluster-wide before the real deletes begin.
  If (a)-(c) cannot ALL be demonstrated in the window, abort the plan and leave
  every object in place — there is no partial-credit version of this step.
status: executed                      # EXECUTED 2026-09-11 in commits 06c954d2
                                      # (manifests) + the docs commit that follows
                                      # it. The §2 soak gate was NOT satisfied —
                                      # it was OVERRIDDEN BY THE OPERATOR, who was
                                      # shown the gate and its reasoning in full
                                      # and directed the plan to proceed anyway.
                                      # See "§2a Soak override" below. Recorded as
                                      # a decision, not a missed precondition.
window: null                          # executed out-of-window on operator
                                      # direction 2026-09-11; holds no slot. Do
                                      # NOT retire this file yet despite the
                                      # executed-plan convention — §1.6 lists
                                      # cross-references that still resolve here,
                                      # and this file is the only record
                                      # distinguishing this work from the
                                      # 2026-09-05 stage 4 of the same plan_id.
                                      # Correct those refs first, then retire.
security_ref: null                    # the credential exposure this plan touches
                                      # is already public in docs/applications.md
                                      # and carries no undisclosed detail
finding_refs:
  - F-0631781c                        # orphaned 20Gi Longhorn volume superset-postgresql-data
  - F-8dcc495d                        # retained postgres artefacts have no decommission date
sops_refs:
  - docs/sops/storage-safety.md
  - docs/sops/longhorn.md
  - docs/sops/backup.md
  - docs/sops/postgres-major-upgrade.md
generated: "2026-09-09"
---

# Reclaim the two retired Superset metadata-DB volumes

## 1. Summary & why this is held

Superset's metadata DB has moved twice in three weeks:

| Generation | Volume | Retired | Disposition today |
|---|---|---|---|
| bundled bitnamilegacy postgres 14.17 | `superset-postgresql-data` | 2026-09-05 (`90539942`) | detached, PVC Bound, no consumer |
| standalone postgres 17.11-alpine | `superset-pg-data` | 2026-09-09 (`9d10199c`) | detached, PVC Bound, no consumer |
| standalone postgres 18.6-alpine | `superset-pg18-data` | — | **LIVE**, attached, healthy |

Each retirement deliberately kept the data as the rollback. That was correct at
the time and it is why this plan exists rather than a `kubectl delete`.

### 1.1 This plan is the decision that supersedes the docs

`docs/applications.md` currently says of both volumes, in as many words:

> a **deliberately-orphaned rollback artifact** … Do NOT treat it as an orphan
> to reclaim; that is a separate, explicitly-decided cleanup.

**This plan IS that separate, explicit decision.** Once it executes, that framing
is wrong and must not be left standing — a future reader finding "do not reclaim"
next to a deleted volume cannot tell which one is stale. Updating
`docs/applications.md` is therefore a numbered STEP of this plan (§4.6), not
follow-up work.

### 1.2 The backups are frozen, and that is the actual reason to act

Because both volumes are detached, `daily-backup-all-volumes` produces no new
backups for them. Measured 2026-09-09:

```
superset-pg-data          7 Completed dailies, 2026-09-03 .. 2026-09-09, then nothing
superset-postgresql-data  7 Completed dailies, 2026-08-29 .. 2026-09-04, then nothing
```

A frozen set does not age out on its own. So "leave it alone" is not a
zero-cost null action — it is a decision to keep two 20Gi volumes (2 replicas
each: ~80 GiB of *scheduled* Longhorn capacity across three nodes, currently
708/730/613 GiB scheduled of 930 GiB max) plus fourteen backups indefinitely,
with nobody's name on the expiry. `superset-postgresql-data` is the precedent
and the warning: it has sat in exactly this state since 2026-09-04 and only
surfaced because a sweep flagged it (`F-0631781c`).

This is hygiene, not capacity pressure. There is no urgency argument here and
the plan should not pretend otherwise.

### 1.3 The alembic boundary — the fact that makes six of seven backups useless

Commit ordering on 2026-09-08 (verified with `git log --date=format`):

```
08:09  6cd371f8  superset image 5.0.0 -> 6.1.0   (alembic migrations ran against superset-pg 17.11)
08:36  d9863640  metadata DB cut over to superset-pg18
10:24  dad8922c  admin FAB password rotated      (writes land in pg18, NOT in superset-pg)
14:49  0af4b8e5  mu_adm FAB password rotated     (same)
```

Consequences, and they are load-bearing for anyone attempting a restore:

- The **volume** `superset-pg-data` was frozen at 08:36 and therefore carries the
  **6.1.0 alembic schema**.
- Of its seven daily backups, six (09-03 … 09-08, all taken ~03:00) predate
  08:09 and therefore carry the **5.0.0** schema. They are restorable only
  alongside an image downgrade to `apache/superset:5.0.0`, which plan
  `superset-6.1.0` already recorded as not available ("two majors of one-way
  alembic migrations … there is no image-tag rollback, only a DB restore").
- Only the **2026-09-09 03:04** backup is a usable restore source for today's
  running app. The effective restore set is **one backup**, not seven.
- The alembic-ran-against-17.11 inference comes from commit ordering, not from
  reading the volume. The backup_gate's `select version_num from
  alembic_version` on the restore proof is what turns it into a measurement —
  record the value there and compare it to the LIVE pg18 value
  (`kubectl -n databases exec deploy/superset-pg18 -- psql -U superset -d superset
  -c 'select version_num from alembic_version;'`) before trusting any of this.

### 1.4 MANDATORY on any restore: reset both local Admin accounts FIRST

**All fourteen frozen backups, and both retained volumes, predate the 2026-09-08
credential rotation.** They carry the pre-rotation Flask-AppBuilder password
hashes for **every** local db-provider Admin account — currently two, `admin`
and `mu_adm`. Superset's `db` auth provider is advertised unconditionally at
`/api/v1/security/login` regardless of `AUTH_TYPE = AUTH_OAUTH`, so a valid
db-provider password is full Superset Admin with **no Authentik, no MFA, no
Authentik audit trail** (`docs/sops/sso-local-auth-bypass.md`). One of those
plaintexts was public for ~4.7 months and can never be un-published.

> **Restoring any of these artifacts re-arms both bypasses.**
> Resetting or disabling every local db-provider Admin account is a
> **MANDATORY STEP OF THE RESTORE ITSELF, executed before Superset is allowed to
> serve traffic** — never a follow-up ticket, never "we'll rotate after".
> Enumerate the accounts with `superset fab list-users` in-pod rather than
> assuming there are two; provider enumeration cannot reveal how many accounts
> hold a usable local password.

This clause is reproduced verbatim in §6 (Rollback), which is where someone in a
hurry will actually read it.

### 1.5 A note for whoever maintains the phantom table

`runbooks/maintenance/plans/README.md` lists `superset-pg` image
`17.11-alpine → 18.6-alpine` as a phantom that survives "until a
`superset-pg-decommission` plan lands". That row is **already stale**:
`9d10199c` deleted `pg-deployment.yaml`, so the 17.11 image pin no longer exists
anywhere in the repo and `coverage.py` has nothing left to read it from. The
phantom dissolved with the workload, not with this plan. I have not edited the
README here — another session is writing in this directory — but the row should
go when someone next touches it. The related sweep finding is `F-da30e00e`; this
plan deliberately does **not** claim it in `finding_refs`, because claiming
ownership of something already resolved elsewhere is how a finding stops being
re-checked.

### 1.6 plan_id reuse — read this before you assume this plan already ran

The id `superset-pg-decommission` was **used once before**: it was stage 4 of
`superset-bitnamilegacy-migration`, it EXECUTED on 2026-09-05 (`90539942`), and
its file was retired per the executed-plan convention. Its stage-4 row in
`superset-bitnamilegacy-migration.md` still links to `superset-pg-decommission.md`
and now resolves to *this* file, which is different work. The operator named this
plan, so the id stands; this paragraph is the disambiguation. There is no
validator collision (only one file carries the id), and
`runbooks/tests/test-retired-plan-occupancy.py` uses the name only as an inline
fixture, not by reading this directory.

**Eight other references now resolve to this file while meaning the old work.** A
doc-agent pass on 2026-09-09 enumerated them; they are listed here rather than
edited, because several sit in files a concurrent session was writing. Whoever
next touches each should correct it:

| Reference | What it actually means |
|---|---|
| `superset-bitnamilegacy-migration.md:47` | Stage-4 row still **links** to `superset-pg-decommission.md`, describing `postgresql.enabled:false`, 30 m, `tue-early:2026-09-22`. Rows 1–2 are marked *(executed, plan retired)*; row 4 is not, though it executed 2026-09-05. **Highest-value fix: mark it executed and REMOVE the link** — the target is now different work. |
| `superset-bitnamilegacy-migration.md:32` | `superseded_by: superset-pg-decommission` — same misresolution, in machine-readable frontmatter. |
| `README.md:55` | Phantom-table owner column says the plan is "**not yet written**". It is. See §1.5 — that whole row should be retired. |
| `bitnamilegacy-exit-nextcloud-db.md:80`, `:860` | "the last bitnamilegacy image … once superset-pg-decommission has also run" — already true since 2026-09-05. Now reads as blocked on a plan that removes no bitnamilegacy image. |
| `authentik-pg17-decommission.md:27` | "Same shape as superset-pg-decommission, which used `one-way`." This plan declares `backup-restore` and argues that distinction is deliberate, so the citation now contradicts its referent. |
| `media-naming-p3.md:45`, `:51` | A co-scheduling guard against `sat-early:2026-09-05`, a slot now in the past, for an id that today has no window. Dead constraint. |
| `docs/sops/maintenance-windows.md:52` | "sits 10 days after the cutover on purpose" — describes the old stage-4 soak, not this plan's 21-day §2 gate. |
| `runbooks/maintenance-plan.py:241` | Historical comment, now ambiguous against a live plan of the same id. |

`docs/applications.md:99` also references the id but carries the commit hash
`90539942`, so it stays unambiguous. **Separately noted by the same pass:**
`superset-pg-cutover.md` is itself a retired plan whose stated retention
condition ("until stage 4 retires it") expired on 2026-09-05 — the
`flux-stack-v0.57` shape the README warns about. It should be deleted per the
executed-plan convention; that is not this plan's call to make unilaterally.

## 2. Soak gate — do not schedule this before 2026-09-30

The floor named in the README is "≥7 clean days on `superset-pg18`". **Seven days
is not enough here**, for a reason specific to this cutover:

1. **Two majors landed 27 minutes apart.** Superset 5.0.0→6.1.0 (08:09) and
   postgres 17→18 (08:36) on the same morning. A fault in either surfaces as
   "Superset is broken", and the two rollbacks are different operations. A soak
   short enough to overlap the tail of a double-major is not a soak.
2. **The soak clock does not start at the cutover — it starts 2026-09-09.** SQL
   Lab had been returning 500 "Authentication required." on *every* query since
   2026-08-17 and was only fixed yesterday (`e351c722`). An entire subsystem of
   the app had **zero** days of exercised-and-working operation as of the
   cutover, so the cutover date measures nothing about it.
3. Superset's periodic surfaces (scheduled reports/alerts, the pellet-price
   dashboards fed by a twice-daily ETL) need several weekly cycles to have
   plausibly exercised the migrated schema.

**Soak: 21 clean days from 2026-09-09 → earliest eligible date 2026-09-30.**
Proposed slot: **`sat-attended:2026-10-10`** — 70 min against that window's 90 min.
Not the first eligible Saturday (2026-10-03): that slot is already proposed for
`external-dns-unowned-cnames` (40 min), and 40 + 70 = 110 does not fit 90. The
soak expiry is a floor, not a target, so the extra week costs nothing and avoids
handing the window agent an impossible slot to unpick.

Do not schedule it earlier to "use up" spare nightly capacity — `nightly` is
`mode: unattended` and this plan is HUMAN-GATED by derivation anyway, and the
windows YAML is explicit that nightly windows "must never be used to collapse a
deliberate soak".

**Soak exit conditions — all must hold on the scheduling date:**

- `superset-pg18` Deployment: no restarts, `volume/superset-pg18-data` attached +
  healthy, daily backups Completed for 21 consecutive days.
- Superset, worker and celerybeat pods: restart count 0 (or explained).
- At least one SQL Lab query and one dashboard render succeed on the day of the
  window (this is what item 2 above buys).
- No open Superset finding in `sweep_findings` rated warning or above.

## 2a. SOAK OVERRIDE — executed 2026-09-11, gate NOT satisfied

**The §2 soak gate above was not met. It was overridden by the operator.**

- §2 set the earliest eligible date at **2026-09-30** (21 clean days from
  2026-09-09). The plan executed on **2026-09-11**, 19 days early.
- The operator was shown the gate **in detail before deciding** — including the
  two reasons that motivated it: two majors 27 minutes apart on 2026-09-08
  (Superset 5.0.0→6.1.0 at 08:09, postgres 17→18 at 08:36), and SQL Lab having
  worked only since 2026-09-09 — and directed that it proceed regardless.
- This is therefore a **deliberate override, not an oversight**. It is recorded
  here, and in the commit messages, so the audit trail shows which of the two it
  was. Nothing else in the plan was waived: §3 pre-checks, the full `backup_gate`
  including the live restore proof, the ordering, the verification and the
  rollback path were all executed as written.

**What made the override survivable, and it is not an argument that the soak did
not matter:** the frozen backup sets were retained, and the `backup_gate` was
executed in full rather than asserted. The newest `superset-pg-data` backup
(2026-09-09 03:04) was restored into a scratch Longhorn volume, booted under
`postgres:17.11-alpine`, and measured: `ab_user` = 2 and
`alembic_version` = `4b2a8c9d3e1f`, **identical to the live `superset-pg18`
value**. That turns §1.3's commit-ordering *inference* about the 6.1.0 schema
boundary into a *measurement*, which is the single most load-bearing fact behind
running this early.

**The soak's own exit condition was also checked on the day and passed**: SQL Lab
executed real queries successfully (HTTP 200, `status=success`, rows returned)
both before and after the deletes — the subsystem §2 item 2 existed to protect.
What the override genuinely gives up is the *duration* argument: the periodic
surfaces in §2 item 3 (scheduled reports/alerts, the twice-daily pellet ETL) have
had days rather than weeks to exercise the migrated schema. If a latent
6.1.0/pg18 schema fault surfaces later, the recovery is §6, and it is a
restore-from-backup — slower and more involved than the repoint that a completed
soak would have preserved.

## 3. Pre-checks (run in the window, before anything is touched)

```bash
cd /Users/mu/code/cberg-home-nextgen

# 3.1 The live DB is healthy and is genuinely the one serving traffic
mise exec -- kubectl -n databases get deploy superset-pg18 superset superset-worker superset-celerybeat
mise exec -- kubectl -n databases get secret superset-secrets -o jsonpath='{.data.DB_HOST}' | base64 -d; echo
mise exec -- kubectl -n databases exec deploy/superset-pg18 -- \
  psql -U superset -d superset -c 'select count(*) from ab_user; select version_num from alembic_version;'

# 3.2 Nothing mounts what we are about to delete (the actual safety question)
for v in superset-pg-data superset-postgresql-data; do
  echo "== $v =="
  mise exec -- kubectl -n storage get volume "$v" \
    -o custom-columns=NAME:.metadata.name,STATE:.status.state,NODE:.status.currentNodeID --no-headers
  mise exec -- kubectl -n databases describe pvc "$v" | grep -i 'Used By'
done
# EXPECT: state=detached, currentNodeID empty, "Used By: <none>" for BOTH.
# ANY other answer -> STOP.

# 3.3 Cluster is quiet
mise exec -- flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
mise exec -- kubectl -n storage get volumes -o json | .venv/bin/python3 -c "
import sys,json
d=json.load(sys.stdin)
bad=[v['metadata']['name'] for v in d['items']
     if v.get('status',{}).get('robustness') in ('degraded','faulted')]
print('degraded/faulted:', bad or 'none')"
```

### 3.4 STORAGE-SAFETY PRE-FLIGHT — mandatory, even though this is Longhorn

`docs/sops/storage-safety.md` writes its 3-step inspection for CIFS/SMB/NFS.
This plan runs it anyway, because the rule that matters ("know the blast radius
from the StorageClass, not from the brief") is class-independent, and because
skipping a pre-flight on the grounds that *this* driver is the safe one is
precisely the reasoning that cost 4.7 TB on 2026-04-26.

```bash
for PVC in superset-pg-data superset-postgresql-data; do
  PV=$(mise exec -- kubectl -n databases get pvc "$PVC" -o jsonpath='{.spec.volumeName}')
  echo "== $PVC -> $PV =="
  # (1) volumeAttributes — is there a subdir, and does it point at a shared root?
  mise exec -- kubectl get pv "$PV" -o jsonpath='{.spec.csi}' | .venv/bin/python3 -m json.tool
  # (2) reclaim policy
  echo "reclaim=$(mise exec -- kubectl get pv "$PV" -o jsonpath='{.spec.persistentVolumeReclaimPolicy}')"
  # (3) StorageClass default
  SC=$(mise exec -- kubectl get pv "$PV" -o jsonpath='{.spec.storageClassName}')
  mise exec -- kubectl get sc "$SC" -o yaml | grep -E 'reclaimPolicy|provisioner|parameters' -A3
done
```

**Measured 2026-09-09, and this is the expected answer:**

| Step | `superset-pg-data` | Reading |
|---|---|---|
| (1) volumeAttributes | `{numberOfReplicas: "2", staleReplicaTimeout: "30"}`, `volumeHandle: superset-pg-data`, driver `driver.longhorn.io` | **No `subdir` key exists.** Longhorn has no shared-root semantics — a volume is a block device, not a directory inside somebody else's export. The `subdir: /` STOP branch is structurally inapplicable, and that is a *finding*, not an assumption. |
| (2) PV reclaimPolicy | `Retain` | A PVC delete alone releases the PV and destroys nothing. |
| (3) StorageClass `longhorn-static` | **`reclaimPolicy: Delete`** | ⚠️ The class default is `Delete`; only the hand-authored PV overrides it to `Retain`. Anyone recreating these PVs from a template that omits `persistentVolumeReclaimPolicy` gets `Delete`. Verify (2) on the live object every time — never infer it from the class. |

**BLAST RADIUS, stated explicitly:** exactly the two named 20 GiB Longhorn
volumes and their replicas. Longhorn deletes only the volume named in the CR;
there is no shared filesystem, no sibling app's data under a common parent, and
no third volume reachable from this operation. `superset-pg18-data` — the LIVE
metadata DB, in the same namespace, in the same app folder, one character
different in the name — is **not** in scope and is the single most likely target
of a fat-fingered delete. Every command in §4 names volumes explicitly; do not
substitute a glob, a label selector, or `grep superset`.

## 4. Steps

### 4.1 Satisfy the backup_gate (do this FIRST, in full)

Execute (a)–(d) of the `backup_gate` in the frontmatter, on
`superset-pg-data`'s newest backup. Record the `alembic_version` value you
observe; §5 compares against it. **If any part fails, stop here and leave every
object in place.**

### 4.2 Capture the pre-delete inventory (this is the §5 baseline)

```bash
mise exec -- kubectl -n storage get backups.longhorn.io -o json \
  | .venv/bin/python3 -c "
import sys,json
d=json.load(sys.stdin)
for b in d['items']:
    s=b.get('status',{})
    if s.get('volumeName') in ('superset-pg-data','superset-postgresql-data'):
        print(s['volumeName'], b['metadata']['name'], s.get('state'), s.get('backupCreatedAt'), s.get('size'))
" | sort | tee /tmp/superset-frozen-backups-before.txt
# EXPECT 14 rows (7 + 7), all Completed.
```

### 4.3 GitOps change — remove the manifests

Edit `kubernetes/apps/databases/superset/app/kustomization.yaml`: drop
`pg-pv.yaml`, `pg-pvc.yaml`, `pv.yaml`, `data-pvc.yaml` from `resources`, and
delete the now-unreferenced files plus the two hand-applied Longhorn CRs that
live in the folder as source:

```
git rm kubernetes/apps/databases/superset/app/pg-pv.yaml \
       kubernetes/apps/databases/superset/app/pg-pvc.yaml \
       kubernetes/apps/databases/superset/app/pg-longhorn-volume.yaml \
       kubernetes/apps/databases/superset/app/pv.yaml \
       kubernetes/apps/databases/superset/app/data-pvc.yaml \
       kubernetes/apps/databases/superset/app/longhorn-volume.yaml
```

Leave `pg18-*.yaml` and `redis-deployment.yaml` untouched. Keep the
kustomization comment block explaining why `pg18-longhorn-volume.yaml` is not
listed — that rule still applies to the live volume.

Validate, then commit with `--only` on exactly these paths (the worktree is
shared) and push:

```bash
mise exec -- task kubeconform
git commit --only kubernetes/apps/databases/superset/app/ -F /tmp/msg.txt
git show --stat HEAD     # every file must be yours
git push
```

### 4.4 Let Flux prune, then confirm it actually pruned

Flux's pruner removes the PVCs and PVs it owns. Do **not** hand-delete them
first — a hand delete races the reconcile and leaves Flux reporting drift.

```bash
mise exec -- flux get kustomizations -A | grep -i superset
mise exec -- kubectl -n databases get pvc | grep superset   # expect only superset-pg18-data
mise exec -- kubectl get pv | grep superset                 # expect only superset-pg18-data
```

### 4.5 Delete the two Longhorn Volume CRs BY NAME

Flux does not own these (they live in namespace `storage`, deliberately outside
`kustomization.yaml`), so they are the one manual delete in this plan.

```bash
mise exec -- kubectl -n storage delete volume superset-pg-data
mise exec -- kubectl -n storage delete volume superset-postgresql-data
# NOT a glob. NOT `grep superset`. superset-pg18-data must survive.
mise exec -- kubectl -n storage get volume | grep superset   # expect exactly one row
```

### 4.6 Update the documentation in the same change set

**TWO files carry framing that this plan's execution makes wrong. Both must move
in the same change set** — a doc-agent pass on 2026-09-09 found the second one,
which an earlier draft of this plan had missed:

1. **`docs/applications.md:99`** describes both volumes as deliberately-orphaned
   rollback artifacts that must not be reclaimed (the phrase appears **twice** on
   that line, once per volume). Replace the framing for **both** with: reclaimed
   on <date> by plan `superset-pg-decommission`; the frozen Longhorn backup sets
   are retained and are the remaining restore path; any restore must first reset
   every local db-provider Admin account (§1.4). Keep the credential caveat
   itself — it survives the volume and applies to the backups.
2. **`docs/sops/postgres-major-upgrade.md:159`** states the recovery path as
   *restore-from-volume*: "re-create the Deployment from git history against the
   retained PVC". Once §4.4 prunes that PVC, this instruction is simply wrong and
   will send someone looking for an object that no longer exists. Change it to
   restore-from-frozen-Longhorn-backup and point at §6 of this plan.

Cosmetic, fix if convenient: `runbooks/backup-restore-proof.py:27` uses
`--volume superset-postgresql-data` as its usage-docstring example, which stops
being a real volume.

Commit the docs separately from the manifests, again with `git commit --only`.

## 5. Verification

Flux Ready and "the PVC is gone" are the floor, not the section.

```
CONTENTS ASSERTION 1 — the live DB still holds real data, not just a schema:
  `select count(*) from ab_user` and a per-table row count on superset-pg18
  after the deletes, diffed against the same query run in §3.1 BEFORE them.
  Must be identical. (A shape check here would be "pod Ready" — which stays
  green if the deletes had somehow detached the wrong volume and postgres came
  back on an empty datadir.)

CONTENTS ASSERTION 2 — the app renders real content, not an empty shell:
  load a dashboard with a known chart count and assert every chart resolves with
  data, plus one SQL Lab query returning rows. `/health` returning 200 is
  explicitly NOT sufficient; SQL Lab returned 200-with-500-bodies for three
  weeks (`e351c722`).

CONTENTS ASSERTION 3 — the restore path we chose to keep still exists:
  re-run the §4.2 inventory query and diff against
  /tmp/superset-frozen-backups-before.txt. All 14 backup rows must STILL be
  present and Completed AFTER the volumes are deleted. This is the assertion
  that distinguishes this plan from a one-way delete, and it is the one most
  likely to fail silently — a Longhorn volume delete that also reaped its
  backups turns rollback_class: backup-restore into a lie.
```

Plus:

```bash
mise exec -- kubectl -n storage get volume superset-pg18-data \
  -o custom-columns=NAME:.metadata.name,STATE:.status.state,ROB:.status.robustness --no-headers
# attached / healthy

mise exec -- kubectl -n storage get nodes.longhorn.io -o json | .venv/bin/python3 -c "
import sys,json
d=json.load(sys.stdin)
for n in d['items']:
    for did,st in (n.get('status',{}).get('diskStatus') or {}).items():
        print(n['metadata']['name'], 'scheduled=%.0fGi'%(st.get('storageScheduled',0)/2**30))"
# scheduled should have fallen ~40 GiB per volume vs the §3 reading
```

Run `runbooks/health-check.sh` and the `health-check-agent` afterwards.

## 6. Rollback

**Before the deletes (§4.5):** `git revert` the §4.3 commit. Flux re-creates the
PV and PVC; they re-bind to the still-existing Longhorn volumes. Free.

**After the deletes:** the in-cluster objects are gone and recovery is a
**restore from the retained frozen backup set**:

1. Restore `superset-pg-data`'s **2026-09-09** backup (the only member carrying
   the 6.1.0 alembic schema — §1.3) into a new Longhorn volume.
2. Re-create the 17.11 Deployment and Service from git history:
   `git show 9d10199c^:kubernetes/apps/databases/superset/app/pg-deployment.yaml`,
   plus the PV/PVC from this plan's own revert.
3. **BEFORE Superset is repointed at it and BEFORE it serves any traffic:**
   enumerate local db-provider accounts with `superset fab list-users` in-pod
   and **reset or disable the password of every account holding Admin** —
   currently `admin` (SOPS key `ADMIN_PASSWORD`) and `mu_adm` (SOPS key
   `MU_ADM_PASSWORD`). This restore crosses the 2026-09-08 rotation boundary and
   re-arms an SSO bypass whose plaintext was public for ~4.7 months. **This is a
   step of the restore, not a follow-up.** Skipping it produces a working
   Superset that anyone holding a 4.7-month-old public string can log into as
   Admin, with no Authentik audit trail to show it happened.
4. Only then repoint `DB_HOST` and let Superset start.

`superset-postgresql-data` (postgres 14.17, Superset ≤5.0.0 schema) has **no**
viable restore into today's 6.1.0 app and should be treated as unrecoverable
once deleted. That is accepted: it is obsolete twice over.

## 7. The frozen backup sets — EXECUTED 2026-09-11, retention trimmed to one

### 7.1 Original scope note (kept for the record)

This plan, as written, did **not** delete the fourteen frozen Longhorn backups.
Doing so is the step that makes this genuinely one-way, and it deserved its own
decision with its own date rather than riding along in a storage-hygiene window.
Recommended shape when someone takes it up: keep the single 2026-09-09
`superset-pg-data` backup until Superset has run a full quarter on 6.1.0/pg18,
delete the other thirteen, and record the expiry date in `docs/applications.md`
so the set does not silently become permanent a second time.

### 7.2 That decision was taken and executed — 2026-09-11

**Operator-approved, destructive, irreversible.** The retention trim above was
executed on 2026-09-11 (NOT deferred a quarter — the operator took the decision
on the day). Thirteen of the fourteen frozen backups were deleted; one was kept.

**Why it was taken now rather than held.** The trigger was not capacity. Both
source volumes were deleted earlier the same day (`06c954d2`), so
`daily-backup-all-volumes` can never rotate their backups — the set was frozen
with nobody's name on its expiry, which is the exact failure mode §1.2 named.
And per §1.4 every one of the fourteen predates the 2026-09-08 credential
rotation (`dad8922c`), so each carried pre-rotation local db-provider Admin
material on a share with no at-rest encryption. Keeping thirteen redundant
copies of that was cost with no matching rollback benefit: §1.3 had already
established that only the 2026-09-09 backup is restorable into the running
6.1.0 app, so deleting the other six on `superset-pg-data` and all seven on
`superset-postgresql-data` **cost zero rollback capability**.

**KEPT — exactly one:**

| Backup | Volume | Created | Size | Why |
|---|---|---|---|---|
| `backup-5876963a2bce454c` | `superset-pg-data` | 2026-09-09T03:04:08Z | 922,746,880 B | The only member of either frozen set carrying the **6.1.0 alembic schema** (§1.3), and the only one **proven bootable**: restored to a scratch volume under `postgres:17.11-alpine`, `ab_user`=2 and `alembic_version`=`4b2a8c9d3e1f`, equal to live pg18 (§9 limb (c)). It is the entire rollback path. |

**DELETED — thirteen**, each by exact name with a pre-check asserting
`.status.volumeName` matched the expected dead volume, one at a time:

- `superset-pg-data` (6, all pre-6.1.0-alembic per §1.3, restorable only
  alongside an image downgrade that does not exist):
  `backup-2229284ade6b4d28` (09-03) · `backup-b547f116304a481b` (09-04) ·
  `backup-3cea5d70ecf746b8` (09-05) · `backup-280e922e529c48ee` (09-06) ·
  `backup-b1d9ce382358454d` (09-07) · `backup-92946861d1654e0a` (09-08)
- `superset-postgresql-data` (7, the bundled bitnamilegacy postgres 14.17 set —
  obsolete twice over per §6, unrecoverable into Superset 6.1.0):
  `backup-b96b8dc8e4754059` (08-29) · `backup-1697404b20d443c6` (08-30) ·
  `backup-02f86468c50d4883` (08-31) · `backup-34bd89679c6444eb` (09-01) ·
  `backup-08cf61b70b1e4941` (09-02) · `backup-515156dbcd7f4cdf` (09-03) ·
  `backup-1b88356cb3ec4330` (09-04)

**The near-miss this step is designed around, and how it was handled.** §8's
"dangerous neighbour" warning applies with more force here than to the volume
deletes: `superset-pg-data` and `superset-pg18-data` differ by two characters,
and `superset-pg18-data`'s four backups are the **live** service's real rollback.
Controls used: no wildcard, no label selector, no loop over "superset"; a
delete helper that **refused** any name on a hardcoded survivor list and any
name whose live `.status.volumeName` did not equal the expected dead volume; and
after **every single delete**, a re-assertion that all five survivors
(the keeper plus the four `superset-pg18-data` backups) were still present and
`Completed`. That check passed 13 times out of 13.

Incremental-chain note, since it is the non-obvious risk: `backup-92946861d1654e0a`
(09-08) is the keeper's immediate predecessor in an `incremental` backup chain.
Longhorn block-refcounts the backup store, so deleting it does not strand the
keeper's blocks — but that was verified rather than assumed (deep re-read of the
keeper's `state`/`progress`/`size`/`snapshotName`/`messages` immediately after,
all unchanged), and the `superset-pg-data-26df02ea` BackupVolume correctly
re-pointed `lastBackupName` at the keeper.

**Both `BackupVolume` records were deliberately left in place.** The keeper's
`ownerReferences` point at `BackupVolume/superset-pg-data-26df02ea`, so deleting
that record would **cascade-delete the keeper** — the one object this step exists
to protect. `superset-postgresql-data-b3f40529` now shows
`lastBackupName: ""` and `dataStored: 0` and was also left alone; an empty
BackupVolume record is harmless, and removing it was outside the approved scope.

**Verification:**

- Inventory re-enumerated from the live cluster BEFORE acting and matched the
  approved list exactly: 7 on `superset-pg-data`, 7 on
  `superset-postgresql-data`, 4 on `superset-pg18-data` = 18.
- Keeper verified `Completed`, `progress: 100`, `messages: null` **before** any
  delete, and re-verified after each of the 13.
- All 4 `superset-pg18-data` backups present and `Completed` throughout and after.
- Superset total backup count **18 → 5** (1 keeper + 4 live). Cluster-wide
  backup count 862.
- CONTENTS ASSERTION 1 — live `superset-pg18` table counts diffed before/after
  the trim: byte-identical (`ab_user`=2, `dashboards`=1, `slices`=10,
  `dashboard_slices`=9, `tables`=10, `table_columns`=92,
  `alembic_version`=`4b2a8c9d3e1f`).
- CONTENTS ASSERTION 2 — SQL Lab exercised against the live data DB: HTTP 200
  `status=success` with real rows, including a real-table probe returning five
  base tables and an aggregate over the pellet-price table (4,791 rows, newest
  observation 2026-09-11 18:00 UTC — i.e. current, not a stale shell). Dashboard
  1 published, charts endpoint HTTP 200 with its 9 charts. Per §4.7 `/health`
  alone was explicitly not accepted.
- All Superset pods `Running` with 0 restarts; `superset-pg18-data` untouched.

**Space reclaimed: NOT measured, and this is a real gap.** Longhorn exposes no
retrospective per-backup stored-bytes figure, and the pre-delete `dataStored` on
the two `BackupVolume` records was not captured as a baseline. Post-trim,
`superset-pg-data-26df02ea` holds 50,331,648 B and
`superset-postgresql-data-b3f40529` holds 0. The deleted backups' *logical*
sizes totalled ~12.3 GiB, but the backup store is compressed (`lz4`) and
block-deduplicated, so actual freed bytes are materially lower and are
**unverified**. Anyone repeating a trim should record
`backupvolumes.longhorn.io -o jsonpath={.status.dataStored}` first.

### 7.3 Consequence: the rollback is now SINGLE-COPY

`rollback_class: backup-restore` still holds, but it now rests on **one backup
with no second copy anywhere**. `backup-5876963a2bce454c` is the sole surviving
artifact of the pre-pg18 metadata DB; if it is lost or fails to restore, there is
**no Superset metadata rollback at all** — the live `superset-pg18-data` backups
roll back to pg18 states only, not across the 2026-09-08 cutover. Treat it
accordingly:

- Do **not** delete it, and do **not** delete
  `BackupVolume/superset-pg-data-26df02ea` (cascade, see above).
- Its §1.4 obligation is undiminished: **restoring it re-arms both local
  db-provider Admin bypasses.** Resetting or disabling every local Admin account
  is a mandatory step *of the restore itself*, before Superset serves traffic.
  See §6, which reproduces this verbatim.
- Set and record an expiry. The shape §7.1 recommended — retire the keeper once
  Superset has run a full quarter on 6.1.0/pg18, i.e. **on or after
  2026-12-08** — is still the right one, and is now the only thing standing
  between this set and the "silently permanent" outcome §1.2 warned about. That
  date belongs in `docs/applications.md`; recording it there is **not yet done**.

## 8. Interference notes for the window agent

- **Shared infra touched:** `storage/longhorn`. Two volume deletes trigger
  replica cleanup. Do not co-schedule with any other plan that moves Longhorn
  volumes, changes the engine image, or drains a node — sequence this one last
  if such a plan shares the slot.
- **Not reboot-related.** `needs_reboot: false`; it must not consume a Sunday
  reboot-capable slot. In particular do **not** put it near
  `sun-attended:2026-09-27`, which is already at 140 of 150 minutes.
- **Attended only.** Derived class is HUMAN-GATED; `nightly` is unattended, so
  the plan cannot run there regardless of capacity.
- **The dangerous neighbour is inside this plan, not outside it.**
  `superset-pg18-data` sits in the same namespace and folder, one character away
  from a volume being deleted. Any operator or agent executing §4.5 must type
  both names in full and confirm the survivor with the follow-up `get`.

## 9. Execution record — 2026-09-11

Executed by cberg-agent on operator direction (see §2a for the soak override).

**backup_gate, all four limbs, executed not asserted:**

| Limb | Result |
|---|---|
| (a) newest Completed backup ≥ 2026-09-09 | PASS — `backup-5876963a2bce454c`, Completed, `2026-09-09T03:04:08Z` |
| (b) size non-zero and within 20% of the 09-08 daily | PASS — 922,746,880 B vs 905,969,664 B (+1.9%) |
| (c) live restore proof | PASS — restored to scratch volume, booted `postgres:17.11-alpine`, `ab_user`=2, `alembic_version`=`4b2a8c9d3e1f` **equal to live pg18** |
| (d) scratch removed, Longhorn clean | PASS — volume count back to 95, no degraded/faulted/rebuilding |

Limb (c) was run via `runbooks/backup-restore-proof.py --keep`. Its built-in
smoke connects as the `postgres` role and so reported a false FAILED on a cluster
initdb'd under `superset`; the restore itself had succeeded and the gate queries
were then run directly with `-U superset`. The script's docstring now warns about
this (same change set).

**Pre-flight (§3.4), per PV — both identical:** no `subdir` key (Longhorn block
device, so the shared-root STOP branch is structurally inapplicable), PV
`persistentVolumeReclaimPolicy: Retain` on the live object, StorageClass
`longhorn-static` (class default `reclaimPolicy: Delete` — the PV overrides it,
which is why (2) must be read off the live object every time), volume `detached`
with empty `currentNodeID`, PVC `Used By: <none>`, workload pods in `Succeeded`.

**Order executed:** backup gate → pre-checks → behaviour baseline → commit
`06c954d2` + push → Flux pruned both PVCs and both PVs (within ~15 s, no
hand-delete, no orphaned `Released` PV) → manual `kubectl delete volume` of
`superset-pg-data` then `superset-postgresql-data`, by full name, one at a time,
with a survivor check after each.

**Capacity released: 80.0 GiB of scheduled Longhorn capacity** (nuc14-01 718→698,
nuc14-02 730→690, nuc14-03 603→583 GiB) — 4 replicas × 20 GiB, matching the
plan's ~80 GiB estimate exactly. Volume count 95 → 93. No orphaned replicas.

**Verification:**

- CONTENTS ASSERTION 1 — live `superset-pg18` table counts diffed before/after:
  21 of 23 tables byte-identical, including `ab_user`=2, `dashboards`=1,
  `slices`=10, `dashboard_slices`=9, `tables`=10, `table_columns`=92,
  `alembic_version`=`4b2a8c9d3e1f`. The only two that moved were `logs`
  (2407→2498) and `query` (17→20), both append-only activity tables that grew
  because the verification itself exercised the app.
- CONTENTS ASSERTION 2 — SQL Lab returned HTTP 200 `status=success` with real
  rows both before and after (`prices` = 4773 rows, newest observation
  2026-09-11 06:00 UTC, plus a GROUP BY aggregate). Dashboard 1 loads with its 9
  charts; 4 of 10 charts resolve data via the saved-query-context API path with
  rowcounts 58/1/134/134, **identical before and after**. The other 6 return
  "Chart has no query context saved" on that API path — identical before and
  after, therefore pre-existing and not caused by this change. The UI loads and
  redirects to Authentik SSO as expected.
- CONTENTS ASSERTION 3 — **all 14 backup rows still present and Completed after
  the deletes**, byte-identical to the pre-delete inventory. `rollback_class:
  backup-restore` is intact rather than a lie.
- `superset-pg18-data` attached + healthy throughout; all Superset pods Running
  with 0 restarts.

**Not verified / carried forward:** the 6 charts without a saved query_context
were not rendered with data by any path (the API needs a fully-built query
context per viz type; a real browser render would need an interactive Authentik
login). Their state is unchanged by this plan but is not a positive assertion.
The stale comment at `kubernetes/apps/storage/longhorn/app/helmrelease.yaml:128`
names `superset-postgresql-data`'s stopped replicas in a dated verification note;
left alone deliberately — it is a timestamped historical record, not an
instruction, and rewriting someone's past measurement would be wrong.

### 9.1 Do NOT retire this file yet (convention tension, recorded deliberately)

`runbooks/maintenance/plans/README.md` says to delete a plan file once
`status: executed`. **That is the wrong move here, for now.** §1.6 lists
cross-references that resolve to THIS file while meaning the 2026-09-05 stage-4
work of the same `plan_id`, and this file is the only record that disambiguates
the two. Deleting it dangles those references and destroys the disambiguation.

Correct sequence: (1) `window: null` — done, which clears the
`RETIRED PLAN STILL WINDOWED` warning from `runbooks/maintenance-plan.py`;
(2) correct the cross-references in §1.6; (3) then retire the file.

### 9.2 Follow-on doc drift this execution created, fixed in the same change set

The deletes invalidated go/no-go gates in an **unexecuted** plan, which is the
highest-consequence drift found and was not in §4.6's list:

- `runbooks/maintenance/plans/talos-1.14.0.md` (scheduled 2026-09-27) keyed its
  Longhorn pre-flight on the two deleted volumes as *known exceptions*, including
  a live gate expression excluding `superset-postgresql-data` by name. Left
  alone, the node roll would have carried a hardcoded exception for objects that
  no longer exist — masking a genuinely unhealthy volume. The exception table,
  the stale-volume gate, the gate code and the volume/replica counts
  (95→93 volumes, 194→190 replicas, `Counter({2: 95})`→`Counter({2: 93})`) were
  all corrected against live state. The "95 min" duration figures in that file
  are minutes, not volume counts, and were deliberately left alone.
- `kubernetes/apps/storage/longhorn/app/helmrelease.yaml` cited
  `superset-postgresql-data`'s stopped replicas as live evidence for
  `orphanResourceAutoDeletion`. Kept as a dated record with an appended
  correction rather than rewritten — it is evidence for a past decision.
- `docs/sops/new-deployment-blueprint.md` used `superset-postgresql-data` as a
  volume-naming exemplar; now `superset-pg18-data`.
- `AGENTS.md` / `docs/sops/longhorn.md` static-vs-dynamic PV counts were stale by
  ~10 before this change and moved by 2 because of it; re-measured live.
