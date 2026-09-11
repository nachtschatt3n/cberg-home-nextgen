# SOP: PostgreSQL Major Upgrades — the PGDATA relocation trap

> Description: How to move a PostgreSQL instance across a major version without silently writing the new data directory into the container's ephemeral layer, and why "SELECT version() says 18.6 and the row counts match" is not evidence the upgrade worked.
> Version: `2026.09.08`
> Last Updated: `2026-09-08`
> Owner: `homelab-sre`

---

## 1) Description

Sibling to [`mariadb-major-upgrade.md`](mariadb-major-upgrade.md). Covers any
PostgreSQL major bump on this cluster — `17.x → 18.x` and later — for instances
running the official `postgres` image.

It exists because on 2026-09-06 a plan for `paperclip-postgresql` 17.11 → 18.6
was stopped at pre-check after it was found that, as written, it would have
**silently destroyed the database while passing every verification gate in the
plan**. The knowledge lived only in that plan file, and plan files are deleted
once executed (`runbooks/maintenance/plans/README.md`), so `grep -rn PGDATA
docs/` returned nothing. This SOP is where it lives now.

## 2) Overview

**The trap, in one table.** PostgreSQL's official image relocated `PGDATA` at 18:

| image | `PGDATA` | `VOLUME` |
|---|---|---|
| `postgres:17.11-alpine` | `/var/lib/postgresql/data` | `/var/lib/postgresql/data` |
| `postgres:18.6-alpine` | `/var/lib/postgresql/18/docker` | `/var/lib/postgresql` |

A manifest that keeps `mountPath: /var/lib/postgresql/data` and merely repoints
`subPath` therefore mounts the PVC at a path the 18.x image **no longer uses**.
`initdb` runs, the restore succeeds, the server starts — all inside the
container's **ephemeral writable layer**.

**Why this is worse than an ordinary bug.** That failure is invisible to every
check people habitually run:

- `SELECT version()` reports 18.6 — true, the server really is 18.6
- row counts match — true, the restore really did load the data
- the application works — true, it is talking to a real database

The data is lost at the **next pod restart**, arbitrarily later, with the
maintenance window long since reported green. There is no alert for "your
database is on tmpfs".

### Why the Longhorn backup does NOT save you here

The obvious objection is "we back this volume up nightly, so worst case we
restore". For this specific failure that reasoning does not hold, and the reason
generalises.

**A backup protects the VOLUME. It cannot protect data that was never written
to the volume.** When `PGDATA` lands outside the mount, the PVC keeps the OLD
major's datadir, frozen at the moment of cutover, and every subsequent nightly
backup faithfully captures that frozen copy. The backup job succeeds,
`lastBackupAt` advances every night, robustness stays `healthy`, and the
retention window fills with pristine snapshots of a database that stopped being
the database. Nothing anywhere reports a problem.

So restoring gets you the PRE-UPGRADE state and loses every write since
cutover. And because this failure is silent by construction — `SELECT
version()` says 18.x, row counts match, the application works — "since cutover"
is not minutes. It is however long it takes someone to restart the pod, which
can be days.

Contrast a normal bad upgrade, where the new major writes to the PVC and the
backup genuinely holds the last good state. There the backup IS the mitigation.
The difference is not how good the backup is; it is whether the bytes ever
reached the volume the backup covers.

**This is why §6's datadir assertion runs FIRST and is not optional.** It is the
only check in the procedure that distinguishes the two cases, and it must pass
before the upgrade is called done — not after the application is observed
working, which proves nothing about where the data lives.

A useful sibling check when reasoning about any storage-shaped incident: ask
whether the last backup contains data that CHANGED since the one before it. A
series of identical backups of an allegedly-live database is not reassurance,
it is the signature of this bug.

## 3) Blueprints

N/A — this is a procedure, not a deployment. The manifests it governs are the
per-app `helmrelease.yaml` / `deployment.yaml` under `kubernetes/apps/*/`.

## 4) Operational Instructions

1. **Read the target image's own contract before writing any manifest.** Do not
   infer it from the previous major:

   ```bash
   # authoritative: the image config, not the docs
   docker run --rm --entrypoint sh postgres:18.6-alpine -c 'echo $PGDATA'
   # or, without a runtime, read the config blob from the registry
   ```

2. **Decide the mount from that value**, not from what the 17.x manifest did.
   Either mount the PVC at the image's `VOLUME` (`/var/lib/postgresql`) and let
   the image place `PGDATA` beneath it, or set `PGDATA` explicitly to a path
   that is definitely inside the mount.

3. **Take a verified logical dump before touching anything.** `rollback_class`
   for a major is `backup-restore`, never `git-revert`: the datadir format
   change is one-way.

   ```bash
   kubectl -n <ns> exec deploy/<db> -- pg_dump -Fc -U <user> <db> > pre-<major>.dump
   pg_restore -l pre-<major>.dump | head        # a dump that will not list is not a rollback
   ```

4. **Count tables across ALL schemas, not just `public`.** See §7.

5. Apply, then run §6 in full. Do not skip the datadir assertion because the
   application came up.

## 5) Examples

```bash
# Correct shape for 18.x: mount at the image's VOLUME, let it own the subdir
volumeMounts:
  - name: data
    mountPath: /var/lib/postgresql      # NOT /var/lib/postgresql/data

# Or pin PGDATA explicitly inside the mount
env:
  - name: PGDATA
    value: /var/lib/postgresql/data/pgdata
volumeMounts:
  - name: data
    mountPath: /var/lib/postgresql/data
```

### Executions of this procedure

Kept here deliberately: plan files are deleted on execution
(`runbooks/maintenance/plans/README.md`), so without this list the evidence that
the procedure has been *exercised* — and the shape a clean run takes — vanishes
with them. Append one row per execution; do not rewrite earlier rows.

| Date | Instance | From → To | Outage | Result |
|---|---|---|---|---|
| 2026-09-07 | `paperclip-postgresql` (`ai`) | 17.11 → 18.6 | — | First execution. Surfaced the two tooling traps in §6 (`pg_restore` version/format coupling; `kubectl exec` truncating a binary dump 12,199,508 → 196,608 bytes). |
| 2026-09-08 | `superset-pg` → `superset-pg18` (`databases`) | 17.11 → 18.6 | ~4 min | **Second, clean execution. No new traps.** Plan `superset-pg-18.6`. |

#### 2026-09-08 — `superset-pg18`, the reference clean run

Worth reading as the worked example, because it is what this SOP looks like when
nothing goes wrong.

- **Side-by-side, not in-place.** A NEW Deployment/Service/PV/PVC
  (`pg18-*.yaml`, `longhorn-static` volume `superset-pg18-data`) was stood up
  alongside the running 17.11 instance (`a753e95e`) and only then repointed
  (`d9863640`). The old `superset-pg` was **retained as the rollback** — see §11:
  a major upgrade has no manifest rollback, so the previous instance IS the
  recovery path until the soak ends.
  **Workload retired 2026-09-09 (`9d10199c`)** after the soak: the Deployment and
  Service were deleted while the volume `superset-pg-data` was retained.
  **Volume reclaimed 2026-09-11** by plan `superset-pg-decommission`, so there is
  no retained PVC left to bind and the recovery path is now a
  **restore-from-backup**: restore the surviving Longhorn backup into a new
  volume, then re-create the Deployment from git history against it.
  **There is no longer a set to choose from — as of 2026-09-11 the backup
  retention was trimmed to ONE and the path is SINGLE-COPY:**
  `backup-5876963a2bce454c` (2026-09-09) is the only surviving pre-pg18 metadata
  backup. The older dailies predated the 5.0.0→6.1.0 alembic migration, carried
  the wrong schema, and were deleted. Its source volume no longer exists, so it
  can never be re-taken; if it is lost there is no rollback across the cutover at
  all. Do not delete `BackupVolume/superset-pg-data-26df02ea` — the backup is
  owned by it and would cascade. The restore MUST reset every local db-provider
  Admin account before Superset serves traffic (that backup predates the
  2026-09-08 credential rotation). Full procedure: §6 of
  `runbooks/maintenance/plans/superset-pg-decommission.md`.
- **`PGDATA` pinned inside the mount**, `/var/lib/postgresql/data/pgdata`, per
  §5 — the whole reason this SOP exists. `POSTGRES_INITDB_ARGS` was dropped
  because PG18 enables data checksums by default, and that was **asserted with
  `SHOW data_checksums` after initdb rather than inferred from the release notes**.
- **Contents diffed before the repoint, not counted.** 53/53 tables, 50
  sequences, 127 indexes and 111 foreign keys compared identical old vs new. Row
  counts alone would not have caught a lost index or a dropped FK, and a table
  count alone would not have caught the schema-scoped miss described in §7 —
  see [`verification-contents-not-shape.md`](verification-contents-not-shape.md).
- **Restart assertion run TWICE**, per §6. Once is enough to prove the datadir is
  on the PVC; the second pass is what proves it stayed there after the cutover
  repoint, which is a different moment and a different risk.
- **The one thing that still got missed** was not a postgres failure: the app's
  init-container gate kept probing the OLD host, because `DB_HOST` in the SOPS
  Secret and `.Values.database.host` in the HelmRelease are two independent env
  sources and only the first was moved (`f297f4b5`). A PG cutover on this cluster
  is therefore not complete when the datadir assertions pass — run the datastore
  cutover checklist in
  [`container-dependencies.md`](container-dependencies.md) §4 as well, and do it
  before scheduling the old instance's decommission.

## 6) Verification Tests

**The load-bearing one first. Prove the datadir is on the PVC, not the overlay.**
Everything else in this section can pass while the database is ephemeral.

```bash
POD=$(kubectl -n <ns> get pod -l app=<db> -o jsonpath='{.items[0].metadata.name}')

# 1. where does the server think its data lives?
kubectl -n <ns> exec "$POD" -- psql -U <user> -tAc 'SHOW data_directory'

# 2. is THAT path actually a mount, or the container layer?
kubectl -n <ns> exec "$POD" -- sh -c 'df -h "$(psql -U <user> -tAc "SHOW data_directory")"'
kubectl -n <ns> exec "$POD" -- cat /proc/mounts | grep -F "$(…data_directory…)"

# A data_directory that does not appear in /proc/mounts under a PVC mount is
# THE failure this SOP exists for. Stop and roll back.
```

Then, and only then:

```bash
kubectl -n <ns> exec "$POD" -- psql -U <user> -tAc 'SELECT version()'
# table count across EVERY schema, not just public
kubectl -n <ns> exec "$POD" -- psql -U <user> -tAc \
  "SELECT table_schema, count(*) FROM information_schema.tables
     WHERE table_schema NOT IN ('pg_catalog','information_schema')
     GROUP BY 1 ORDER BY 1"
```

**Restart assertion.** The whole failure mode is deferred to the next restart,
so make it happen on purpose while you are watching:

```bash
kubectl -n <ns> rollout restart deploy/<db> && kubectl -n <ns> rollout status deploy/<db>
# then re-run the row counts. If they are gone, the datadir was ephemeral.
```

### Two tooling traps that will silently ruin a rollback

Both hit during the `paperclip-postgresql` 18.6 execution on 2026-09-07. Neither
is postgres-specific and both fail in the direction that matters.

**1. `pg_restore -l` must run with tooling AT LEAST AS NEW as the `pg_dump`
that wrote the archive.** A dump from pg_dump 17.11 is archive format 1.16; a
local pg_restore 16.14 rejects it with `unsupported version (1.16) in file
header`. That reads exactly like a corrupt dump and would panic anyone
mid-window. Run the gate INSIDE the database pod, whose client tooling matches
the server by construction:

```bash
kubectl -n <ns> exec <pod> -- pg_restore -l /tmp/pre.dump | grep -c 'TABLE DATA'
```

Related: `pg_restore -l` only reads custom/directory/tar archives. On a PLAIN
`pg_dump` (the default) it fails with *"input file appears to be a text format
dump"* — so if a plan verifies with `pg_restore -l`, its dump step MUST use
`-Fc`. Pairing a plain dump with a `pg_restore` gate makes the gate fail 100%
of the time, which is at least loud; pairing a `-Fc` dump with a `tail | grep`
gate makes it pass on a truncated file, which is not.

**2. `kubectl exec -i <pod> -- sh -c 'cat > file'` CORRUPTS binary payloads.**
Copying a 12,199,508-byte custom-format dump this way produced a 196,608-byte
file — a 98% truncation, with no error from either side. Restoring from it
would have looked like a mysteriously incomplete database. Use `kubectl cp`,
which tars the payload:

```bash
kubectl cp ./pre.dump <ns>/<pod>:/tmp/pre.dump
```

**And checksum every transfer of a rollback artifact, in both directions:**

```bash
kubectl -n <ns> exec <pod> -- sha256sum /tmp/pre.dump
shasum -a 256 ./pre.dump          # these MUST match
```

A dump you have not checksummed after moving is a dump whose integrity you are
assuming at exactly the moment you cannot afford to.

## 7) Troubleshooting

**Row counts match but a table is missing after cutover.** The count gate
probably covered only `public`. On `paperclip-postgresql` the 37th table is
`drizzle.__drizzle_migrations`, in its own schema: losing it makes the
application re-run migrations against a populated database. Always group by
`table_schema`.

**The dump-completion marker check passes on a truncated dump.** `pg_dump` 17.11
appends a `\unrestrict` line *after* the completion marker, so a naive
`tail -5 | grep` can miss it. Verify with `pg_restore -l` instead — a dump that
cannot be listed is not a rollback.

**The application works, so the upgrade must be fine.** No. See §2. Run the
datadir assertion.

## 8) Diagnose Examples

```bash
# is the data directory inside a PVC mount?
kubectl -n <ns> exec deploy/<db> -- sh -c \
  'D=$(psql -U postgres -tAc "SHOW data_directory"); echo "PGDATA=$D"; df -h "$D"; grep -F "$D" /proc/mounts || echo "NOT A MOUNT — EPHEMERAL"'

# what does the image itself declare?
kubectl -n <ns> get deploy <db> -o jsonpath='{.spec.template.spec.containers[0].env}' | jq
```

## 9) Health Check

```bash
kubectl -n <ns> get pods -l app=<db>
kubectl -n <ns> exec deploy/<db> -- pg_isready -U <user>
kubectl get pvc -n <ns> | grep <db>
```

## 10) Security Check

Dumps contain the whole database. Write them outside the repo, `chmod 0600`,
and never into a path that git tracks. Verify with `git status` before
committing anything from that directory.

## 11) Rollback Plan

`rollback_class: backup-restore`. A major upgrade rewrites the data directory
format, so there is no commit that undoes it.

1. Scale the deployment to 0.
2. Restore the manifest to the previous major (git revert of the manifest change).
3. Restore data from the pre-upgrade dump taken in §4 step 3.
4. Verify row counts against the numbers recorded before the upgrade.

If the pre-upgrade dump was never verified with `pg_restore -l`, you do not have
a rollback — you have a file.

## 12) References

- [`mariadb-major-upgrade.md`](mariadb-major-upgrade.md) — sibling SOP
- [`verification-contents-not-shape.md`](verification-contents-not-shape.md) — why "it started" is not evidence
- `runbooks/maintenance/plans/paperclip-postgresql-18.6.md` — the plan this was found in (carries a DO-NOT-EXECUTE header until reworked)

## Version History

| Version | Date | Change |
|---|---|---|
| `2026.09.06` | 2026-09-06 | Created after the PG18 PGDATA relocation was caught at pre-check on `paperclip-postgresql`. Knowledge previously existed only in a plan file, which the transient-plan convention deletes on execution. |
| `2026.09.08` | 2026-09-08 | Added an **Executions of this procedure** log and recorded the second application (`superset-pg` 17.11 -> 18.6, ~4 min outage, contents diffed 53/53 tables + 50 sequences + 127 indexes + 111 FKs before the repoint, restart assertion passed twice). Clean run, no new traps — which is itself the finding, since the first execution produced two. Cross-referenced the one thing it did miss: the app-side init-gate host, which is `container-dependencies.md` §4, not a postgres failure. |
| `2026.09.07b` | 2026-09-07 | Added the two tooling traps found executing the paperclip 18.6 upgrade: pg_restore version/format coupling, and kubectl exec truncating binary copies (12MB -> 196KB, silently). |
| `2026.09.07` | 2026-09-07 | Added "Why the Longhorn backup does NOT save you here" after the operator asked exactly that. Both affected volumes ARE enrolled in the nightly backup and were captured that morning — the point is that a volume backup cannot cover writes that never reached the volume. |
