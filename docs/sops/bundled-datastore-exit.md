# SOP: Bundled-Subchart Datastore → Standalone Manifests

> Standard Operating Procedure for moving an app's database or cache off a Helm
> chart's bundled `bitnamilegacy/*` subchart onto plain, version-controlled
> manifests backed by an official upstream image.
> Version: `2026.08.23`
> Last Updated: `2026-08-23`
> Owner: `Platform`

---

## 1) Description

Several charts in this cluster ship their datastore as a bundled subchart
(`postgresql.enabled: true`, `mariadb.enabled: true`, `redis.enabled: true`)
pointing at `bitnamilegacy/*` images. Those images are frozen and unmaintained,
so the datastore cannot be patched independently of the chart. The exit is to
stand up the datastore as our own Deployment + Service + PV/PVC using the Docker
Official image, migrate the data, repoint the app, and keep the old datastore
running as the rollback until a soak has passed.

This has now been executed four times — `superset-pg`, `paperless-db`,
`authentik-pg` succeeded, `nextcloud-db` was rolled back — with more datastores
still bundled. This SOP is the repeatable procedure and, more importantly, the
record of the four ways it has actually tried to go wrong.

**Read [`docs/sops/verification-contents-not-shape.md`](verification-contents-not-shape.md)
before executing.** Every near-miss in this procedure has been a case where the
*shape* of the data verified clean while the *contents* were wrong.

---

## 2) Overview

| Setting | Value |
|---------|-------|
| Applies to | Any app whose chart bundles its datastore as a subchart |
| Executed for | `superset-pg`, `paperless-db`, `authentik-pg` (done); `nextcloud-db` (blocked) |
| Still bundled | see `runbooks/maintenance/plans/bitnamilegacy-exit-*.md` |
| Risk | **high** for a primary datastore — always operator go/no-go (derives HUMAN-GATED: shared storage + backup-restore rollback) |
| Window | a maintenance window; the dump must be taken with the app quiesced |
| Storage class | `longhorn-static` with a speaking PV name (`docs/sops/longhorn.md`) |
| Rollback | the OLD datastore, left running and untouched, until the soak passes |

**The four stages, and they are separate windows:**

1. **Stand-up** — new Deployment/Service/PV/PVC, additive, app untouched.
2. **Cutover** — quiesce, dump, restore, repoint, verify, resume.
3. **Soak** — the old datastore stays up and idle, a full clean week.
4. **Decommission** — `*.enabled: false`, retire the old volume.

Never compress 1–2 or 3–4 into one window. Stage 3 is not compressible by adding
window slots; it is wall-clock time during which real users exercise the app.

---

## 3) Blueprints

The standalone datastore is four plain manifests in the app's own directory. No
chart, no subchart, no operator.

```yaml
# pg-deployment.yaml — Docker Official image, explicit server parameters
apiVersion: apps/v1
kind: Deployment
metadata:
  name: <app>-pg
spec:
  replicas: 1
  strategy:
    type: Recreate          # RWO Longhorn volume — see docs/sops/longhorn-rwo-multi-attach.md
  template:
    spec:
      containers:
        - name: postgresql
          image: postgres:18.6-bookworm
          args:
            # MUST match what the bundled subchart was configured with.
            - -c
            - max_connections=500
```

```yaml
# pg-pvc.yaml — longhorn-static, speaking name, PV name == PVC name == volumeHandle
spec:
  storageClassName: longhorn-static
  volumeName: <app>-pg-data
  resources:
    requests:
      storage: 20Gi
```

`kustomization.yaml` lists `pg-deployment.yaml`, `pg-pv.yaml`, `pg-pvc.yaml` —
and **deliberately NOT `pg-longhorn-volume.yaml`**. The app Kustomization's
`targetNamespace` silently overrides the Longhorn `Volume` CR's
`namespace: storage` and creates a broken duplicate Longhorn ignores. Keep the
CR in the folder as version-controlled source and `kubectl apply` it by hand.
Skipping the apply leaves the PVC `Pending` — that is the expected failure, not
a reason to fall back to a dynamic volume. Full rule:
[`docs/sops/longhorn.md`](longhorn.md).

---

## 4) Operational Instructions

### Stage 1 — Stand up (additive, safe, its own window)

1. Write the four manifests. Pick the image from the **same major** the bundled
   subchart ran, unless the plan explicitly assesses a major move.
2. Hand-apply the Longhorn `Volume` CR, then let Flux apply the rest.
3. Confirm the new datastore is up and **empty**. It must be reachable from the
   app namespace but referenced by nothing yet.

### Stage 2 — Cutover (the dangerous one)

**Server-parameter parity first.** Read the parameters off the OLD server and
carry them across. `max_connections` is the one that has mattered: a parity miss
does not fail at cutover, it surfaces days later as intermittent connection
errors under load.

```bash
kubectl -n <ns> exec <old-datastore-pod> -- psql -U <user> -c 'SHOW max_connections;'
```

**Quiesce, and prove the quiesce held.** `kubectl scale --replicas=0` DOES NOT
HOLD — Flux drift-corrects it back, and the reconcile that restores it is the
very one your cutover commit triggers.

```bash
# suspend BOTH — the Kustomization alone is not enough, the HelmRelease-owned
# Deployment is reconciled back independently
flux suspend helmrelease  <app> -n <ns>
flux suspend kustomization <app> -n <ns>
kubectl scale deploy/<app> -n <ns> --replicas=0
```

Then assert the hold **at the database**, which is the only signal a stale cache
cannot fake:

```sql
select coalesce(string_agg(distinct application_name || '/' || state, ', '), 'NONE')
from pg_stat_activity where datname='<db>' and pid <> pg_backend_pid();
```

Re-assert it *again* immediately after the cutover commit is applied. That
reconcile is the dangerous one.

> **Setting `replicas: 0` in the chart values is the house-preferred hold, but
> check for post-upgrade hooks first.** On Superset it is actively wrong: any
> change to `spec.values` triggers a Helm upgrade, which fires the
> `superset-init-db` post-upgrade hook, which runs `db upgrade` against whatever
> `DB_HOST` currently resolves to — performing the empty-target write from the
> hook while the app is scaled to 0 and every pod-level signal is green.

**Dump — pin the character set explicitly.** See §7; this is what blocked
`nextcloud-db`.

```bash
# MariaDB/MySQL
mariadb-dump --default-character-set=utf8mb4 --add-drop-table ...
# PostgreSQL
pg_dump -Fc ...
```

**Restore, then verify contents before repointing** (§6).

**Repoint** the app at the new host in git, push, let Flux apply.

**Resume in order**: Kustomization first (applies the new Secret while replicas
are still 0, confirm the hold survived), then the HelmRelease, then scale up by
hand. Resuming a HelmRelease with unchanged values does not fire a Helm
upgrade — that is the desired outcome, because it means no hook runs.

### Stage 3 — Soak

The old datastore stays **running and idle** for a full clean week. It is the
rollback. Do not `*.enabled: false` it, do not delete its volume, do not
"tidy up" its Secret.

### Stage 4 — Decommission

A separate plan, `status: awaiting-soak`, HUMAN-GATED (one-way: it destroys
the rollback path, so it never runs on a schedule.

---

## 5) Examples

### Example A: PostgreSQL, succeeded (`superset-pg`, 2026-08-19, `48ffc039`)

47 tables / 2985 rows verified identical before the repoint. The chart's
`wait-for-postgres` init container still gated on the OLD host — it reads only
the chart-generated `superset-env` Secret, whose `DB_HOST` defaults to
`<release>-postgresql`, so `database.host` had to be set in the HelmRelease
before the old Service could be removed, or every pod restart blocks 120 s and
fails.

### Example B: MariaDB, rolled back (`nextcloud-db`, 2026-08-19, revert `d1dbbdd1`)

Rolled back mid-restore, before the app was allowed up. No data lost. See §7 and
§8 — this is the instructive one.

---

## 6) Verification Tests

Row counts are necessary and **not sufficient**. Run all four.

### Test 1: table and row counts, per table, diffed

```bash
# on BOTH servers, then diff the two files
for t in $(list_tables); do echo "$t=$(count_rows "$t")"; done | sort
```
**Pass:** byte-identical. A missing table or a short count fails immediately.

### Test 2: 4-byte round-trip (the contents assertion)

Counts pass over silently transcoded content. Prove multi-byte data survived.

```sql
-- SOURCE: how many rows actually hold multi-byte characters?
select count(*) from <table> where char_length(<col>) <> octet_length(<col>);
```
```bash
# the dump must still contain real 4-byte lead bytes
LC_ALL=C grep -c $'[\xf0-\xf4]' "$DUMP" || echo "NO 4-BYTE SEQUENCES IN DUMP — ABORT"
```
**Pass:** if the source count is > 0, the dump must contain `\xf0-\xf4` lead
bytes, and the same rows must still differ in `char_length` vs `octet_length`
**on the target** after restore. Zero 4-byte sequences from a non-zero source is
a lossy dump — do not restore it.

### Test 3: server-parameter parity

```bash
kubectl -n <ns> exec deploy/<app>-pg -- psql -U <user> -c 'SHOW max_connections;'
```
**Pass:** identical to the value read off the old server in Stage 2.

### Test 4: application-level smoke test

`occ status`, an Alembic/`alembic_version` check, a login, and one real read of
user-visible content. Automated checks verify shape; a human verifies meaning.

---

## 7) Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Restore aborts on a duplicate-key error | The dump was transcoded lossily; two rows that differed only in a 4-byte character both became `?` and collided on a UNIQUE index | **Do not retry the restore.** The error is proof of corruption — re-dump with `--default-character-set=utf8mb4`. |
| App comes up mid-cutover against the empty target | `kubectl scale --replicas=0` did not hold; Flux drift-corrected it | Suspend HelmRelease **and** Kustomization, then scale. Re-assert the hold after the commit lands. |
| App writes a full schema with zero rows into the target | A post-upgrade Helm hook (e.g. `superset-init-db`) fired against the new `DB_HOST` | Do not use the values route to hold replicas on charts with post-upgrade hooks; use suspend-both. |
| PVC stuck `Pending` | The Longhorn `Volume` CR was not hand-applied | Apply it by hand; it is deliberately out of `kustomization.yaml`. |
| Pod restarts block 120 s then fail after the old Service is removed | A chart init container still gates on the chart-generated Secret's default `DB_HOST` | Set `database.host` in the HelmRelease **before** removing the old Service. |
| Intermittent connection errors days after a clean cutover | Server-parameter parity miss (`max_connections`) | Compare against the old server's value; the default of 100 is far below what a multi-replica app needs. |

---

## 8) Diagnose Examples

### Diagnose Example 1: was the dump lossy? (`nextcloud-db`, 2026-08-19)

`mariadb-dump` was invoked without `--default-character-set`, so the connection
negotiated the **server default**, `utf8mb3`. But the server default is not what
the data is stored in: all 206 tables were `utf8mb4_bin`, and only the server
and schema *defaults* were `utf8mb3`. The server transcoded every 4-byte
character to `?` on its way out.

**How nearly it wasn't caught.** The restore failed on a duplicate-key error in
`oc_reactions`. Had that table carried no unique index, the restore would have
completed and passed every check the plan then defined: 206/206 tables,
1,816,443/1,816,443 rows, matching per-table collations, `occ status` clean —
and the source would have been decommissioned a week later.

**The check pointed the wrong way.** The plan asserted that `CREATE DATABASE` in
the dump "must carry utf8mb3 / utf8mb3_general_ci". That is the schema
*default*, and it is exactly what a lossy utf8mb3 dump looks like: the check
confirmed the bug instead of catching it.

```bash
# the assertion that actually discriminates
SRC4=$(mysql -N -e "select count(*) from <db>.<table>
                    where char_length(<col>) <> octet_length(<col>);")
DMP4=$(LC_ALL=C grep -c $'[\xf0-\xf4]' "$DUMP" || echo 0)
[ "$SRC4" -gt 0 ] && [ "$DMP4" -eq 0 ] && echo "LOSSY DUMP — ABORT"
```

### Diagnose Example 2: did the quiesce actually hold?

```bash
kubectl get deploy -n <ns> <app> \
  -o custom-columns=NAME:.metadata.name,DESIRED:.spec.replicas,STATUS:.status.replicas
#   DESIRED must be 0 and STATUS <none> (status.replicas is omitempty at 0)
kubectl get pods -n <ns> --no-headers | grep -E "^<app>-[0-9a-f]{6,}" \
  || echo 'no app pods (correct)'
```

Then confirm at the database with the `pg_stat_activity` query in §4. Pod-level
signals can be stale; the connection list cannot.

---

## 9) Health Check

```bash
# the standalone datastore is up, and on the image we intended
kubectl -n <ns> get deploy <app>-pg -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'

# its volume is bound and healthy
kubectl get pvc -n <ns> <app>-pg-data
kubectl get volume -n storage <app>-pg-data \
  -o custom-columns=NAME:.metadata.name,STATE:.status.state,ROBUST:.status.robustness

# during the soak: the OLD datastore is still running and IDLE
kubectl -n <ns> get statefulset <app>-postgresql
```

A non-idle old datastore during the soak means something is still pointed at it —
find it before decommissioning.

---

## 10) Security Check

- **Rotate the database credential as part of the cutover.** A migration is the
  natural rotation point, and reusing the bundled subchart's generated password
  carries a secret that was never operator-chosen into the new deployment.
  Where several keys in one Secret share a single value, rotate them together.
- Confirm the new Secret is SOPS-encrypted and that the chart-generated Secret
  is retired only at Stage 4, not before.
- The new datastore must not be exposed beyond its namespace: no LoadBalancer,
  no ingress, ClusterIP only.
- Dumps contain the entire database in plaintext. Write them to a `0700`
  directory (`umask 077 && mkdir -p ~/db-dumps && chmod 700 ~/db-dumps`), never
  to `/tmp`, and delete them once the soak passes.

---

## 11) Rollback Plan

**The old datastore is still running and still holds the pre-cutover data —
that is the whole point of the staged design.** Rollback is a `git revert` of
the repoint commit plus a Flux reconcile.

```bash
git revert <repoint-commit>
git push
flux reconcile kustomization <app> -n <ns> --with-source
```

**Anything written to the new datastore after the cutover is lost by this
revert.** Within a window that is usually nothing, because the app was quiesced;
after a resume it is not. Roll back early or not at all.

**Recovery floor** (only if the old datastore is somehow damaged): restore its
Longhorn volume from the backup taken in Stage 2 pre-checks. Take that backup —
the logical dump is the working rollback, the Longhorn backup is the layer
beneath it.

**Storage safety:** do not delete the new volume as part of a rollback. Leave it
in place and re-initialise it explicitly on the next attempt; attempt 2 must not
assume an empty datadir. See [`docs/sops/storage-safety.md`](storage-safety.md).

---

## Version History

| Version | Date | Change |
|---|---|---|
| 2026.08.23 | 2026-08-23 | Initial SOP (F-98e33f1b), written from the four executed migrations: superset-pg, paperless-db, authentik-pg succeeded; nextcloud-db rolled back on a lossy utf8mb3 dump. Captures parameter parity, the suspend-both quiesce, the post-upgrade-hook trap, and the 4-byte round-trip assertion. |
