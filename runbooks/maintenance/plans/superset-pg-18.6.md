---
plan_id: superset-pg-18.6
component: superset-pg
pr: null                              # no open Renovate PR — plain Deployment manifest,
                                      # image tag maintained by hand (see pg-deployment.yaml)
kind: image
current: "postgres:17.11-alpine (superset-pg, the standalone metadata-DB Deployment;
  live since the 2026-08-19 cutover and sole metadata DB since the 2026-09-05
  bitnamilegacy decommission)"
target: "postgres:18.6-alpine, stood up as a NEW Deployment (superset-pg18) and
  reached via a dump/restore cutover; the current superset-pg (17.11) is kept
  running as the rollback through a soak, exactly like the prior superset-pg
  migration"
update_type: major
risk: high                            # superset-pg IS the Superset metadata DB: every
                                      # dashboard/chart/saved query/connection/user lives
                                      # here. Same class of risk as superset-pg-cutover.
est_duration_min: 90                  # stand-up + cutover combined in one window (the
                                      # authentik-postgres-18 precedent ran both phases
                                      # ~70 min apart same session); includes the human
                                      # dashboard/SQL-Lab smoke test
needs_reboot: false
touches:
  namespaces: [databases]
  resources:
    - deployment/superset-pg18          # NEW — becomes the live metadata DB
    - service/superset-pg18             # NEW
    - pvc/superset-pg18-data            # NEW, longhorn-static, speaking name
    - "longhorn:volume/superset-pg18-data"   # NEW — hand-applied per docs/sops/longhorn.md
    - secret/superset-secrets            # DB_HOST repointed (SOPS edit) — the actual cutover
    - deployment/superset                # restarts onto the new DB
    - deployment/superset-worker
    - deployment/superset-celerybeat
    - "deployment/superset-pg (old, 17.11-alpine — LEFT RUNNING as the rollback;
       its own decommission is a separate follow-up plan after the soak, not this one)"
  shared: []                           # isolated to Superset's own metadata-DB stack;
                                       # does not touch ingress, cert-manager, CNI, coredns,
                                       # or any OTHER app's database. Superset's only
                                       # data-source connection (`Pellets` ->
                                       # postgresql.databases.svc:5432) is untouched — this
                                       # plan only moves the METADATA store.
depends_on: [superset-6.1.0]          # HARD — see "Interference notes". Running this
                                      # before superset-6.1.0 breaks that plan's own
                                      # ordering gate (`printenv DB_HOST` must literally
                                      # read `superset-pg`) and stacks an app major on top
                                      # of a DB-engine major in the same soak window.
conflicts_with: [superset-6.1.0, paperclip-postgresql-18.6]
                                      # superset-6.1.0: must not share a window even if it
                                      # somehow executes same-day — its rollback path
                                      # assumes DB_HOST does not move under it.
                                      # paperclip-postgresql-18.6: reciprocal of that plan's
                                      # own ref (added 2026-09-05). NOT a namespace clash —
                                      # `databases` vs `ai`, empty `shared` — so
                                      # maintenance-plan.py's namespace-intersection
                                      # INTERFERENCE check is structurally blind to it.
                                      # Both are one-way postgres majors: stacking them in
                                      # one slot leaves the window with no rollback path if
                                      # the second fails. Now also caught mechanically by
                                      # the RISK-CLASS STACKING check.
security_ref: F-1c825ced              # accepted finding on the CURRENT postgres:17.11-
                                      # alpine image (AR-080). Note: per the finding's own
                                      # record it is a residual not fixed by the 18.6 tag
                                      # either — this bump is fleet-currency (superset-pg is
                                      # now the last non-18.x standalone Postgres in
                                      # `databases`; authentik-pg, mealie-pg,
                                      # teslamate-postgres, traccar-postgres and penpot-db
                                      # are already on 18.6), not a CVE remediation. Detail:
                                      # `runbooks/policy-cli.py finding show F-1c825ced`.
capability_change: false              # engine swap only; Superset's behaviour, schema and
                                      # data are unchanged by this plan
rollback_class: git-revert            # the OLD superset-pg (17.11) is never touched or
                                      # scaled down by this plan — it keeps running with the
                                      # pre-cutover data for the whole soak, so reverting the
                                      # DB_HOST edit is a complete, immediate rollback exactly
                                      # like superset-pg-cutover's.
finding_refs: []                      # no PLAN-lane sweep finding drives this; it is a
                                      # held Renovate-class update (major, direct-bump), not
                                      # a triaged finding
status: draft
window: null                          # earliest feasible slot is AFTER superset-6.1.0
                                      # (sun-attended:2026-09-20) executes and settles —
                                      # do not schedule this into any window before that.
                                      # The window agent assigns the actual slot.
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/bundled-datastore-exit.md
  - docs/sops/backup.md
  - docs/sops/sops-encryption.md
  - docs/sops/longhorn.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-09-05"
---

# Bump superset-pg from postgres 17.11-alpine to 18.6-alpine

## 1) Summary & why held

`superset-pg` (the standalone Deployment that has been Superset's sole metadata
DB since the 2026-09-05 bitnamilegacy decommission) is still on
`postgres:17.11-alpine`. `18.6-alpine` is a Postgres **major** version — the
auto-updater correctly holds any Postgres major, because **major versions are
not on-disk compatible**: 18.x binaries cannot start against a 17.x data
directory, so this cannot be a tag-and-restart like a patch bump. It requires
the same dump/restore/cutover mechanism already used twice in this namespace
(`superset-pg-cutover`, `authentik-postgres-18`), not an image edit.

**What actually changed upstream (PostgreSQL 18 release notes,
`postgresql.org/docs/18/release-18.html`):** no on-disk format change *within*
18.x, but confirms the major-version incompatibility above, and:
- `initdb` now enables data checksums **by default** ("Change initdb default to
  enable data checksums… Checksums can be disabled with the new initdb option
  `--no-data-checksums`.") — irrelevant here since the new pod does a fresh
  `initdb`; the current Deployment's explicit `POSTGRES_INITDB_ARGS:
  --data-checksums` becomes redundant, not wrong, and can be dropped.
- MD5 password authentication is deprecated (not removed) in favour of
  SCRAM — no action needed, this Deployment already authenticates via
  `POSTGRES_PASSWORD`/SCRAM, not an MD5 role.
- A new async-I/O subsystem (`io_method`) with new defaults for
  `effective_io_concurrency`/`maintenance_io_concurrency` (16, up from 4/1) —
  worth a resource-usage glance post-cutover, not a blocker for a 20Gi/1Gi-limit
  single-instance metadata DB.

**The image-layout change that actually matters for THIS plan** is the one the
`authentik-postgres-18` migration already hit and solved
(`docs/sops/bundled-datastore-exit.md`, commit `a469b176`): the `postgres:18+`
Docker images changed their default data directory to
`/var/lib/postgresql/18/docker` (mounted at `/var/lib/postgresql`), no longer
`/var/lib/postgresql/data/pgdata`. Follow that precedent exactly — do **not**
set `PGDATA` on the new Deployment; mount the volume at `/var/lib/postgresql`.
This is also what keeps the *next* major (18→19) a `pg_upgrade` candidate
instead of another dump/restore.

**Why held rather than auto-applied:** this is exactly the class
`docs/sops/auto-update.md` reserves for a window — a one-way data-bearing major
on the application's own metadata store, no automatic verification of *row
contents* exists, and a bad restore is invisible at the pod-health level
(`docs/sops/verification-contents-not-shape.md`).

**Is this covered by an existing plan?** No — checked all three sibling
Superset plans before writing this:
- `superset-pg-cutover.md` (executed) moved Superset from the *bundled
  bitnamilegacy pg14* onto the *first* `superset-pg` (17.11-alpine). Different
  migration, already done.
- `superset-pg-decommission.md` (executed 2026-09-05) retired that old
  bitnamilegacy pg14 StatefulSet. Also done, and confirmed live: no
  `superset-postgresql` pod exists in `databases` any more.
- `superset-6.1.0.md` (`status: draft`, `window:
  sun-attended:2026-09-20`) bumps the **application** image (`apache/superset`
  5.0.0 → 6.1.0) and runs 13 Alembic migrations *against* `superset-pg` — its
  frontmatter is explicit that Postgres stays at **17.11** throughout
  (`current`/`target` both say "postgres 17.11" is the metadata DB; only the
  Alembic head moves). It does not touch the Postgres *engine* version.

None of the three plans a Postgres 17→18 engine bump for `superset-pg`. This
plan is genuinely additional, not a duplicate.

**Fresh-eyes call on whether this is a "false-positive hold":** it is not. A
metadata-DB Postgres major is exactly the risk class this repo's own
`docs/sops/bundled-datastore-exit.md` was written for, and it has burned once
already in this very namespace (rolled back on `nextcloud-db` for a lossy
dump). `risk: high` stands.

## 2) Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) THE ORDERING GATE — superset-6.1.0 must already be executed and soaked.
#    Do not proceed if this plan still exists with status != executed, or if
#    it is mid-window.
test -f runbooks/maintenance/plans/superset-6.1.0.md && \
  echo "STOP: superset-6.1.0 has not executed yet (its plan file still exists)" || \
  echo "OK: superset-6.1.0.md retired (executed) — safe to proceed"
mise exec -- kubectl exec -n databases deploy/superset -- printenv DB_HOST   # must read: superset-pg

# b) current state: image, health, backup freshness of the volume you are copying FROM
mise exec -- kubectl get deploy -n databases superset-pg \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"  ready="}{.status.readyReplicas}{"\n"}'
mise exec -- kubectl get pvc -n databases superset-pg-data      # Bound
mise exec -- kubectl get volume -n storage superset-pg-data \
  -o custom-columns=NAME:.metadata.name,STATE:.status.state,ROBUST:.status.robustness,LASTBACKUP:.status.lastBackupAt
# require lastBackupAt within the last 24h; if stale, trigger a manual Longhorn
# backup per docs/sops/backup.md before continuing — this plan deletes nothing
# from superset-pg, but a fresh backup is cheap insurance before any window
# that touches the live metadata DB.

# c) target tag really exists (verified 2026-09-05, multi-arch index):
#    postgres:18.6-alpine -> index digest sha256:d3e1620b530c944afa6e887d22eb899824da68e19c52024bf98f5220c88a65b2
#    amd64 manifest digest sha256:63bdc97d67b5133bf0e5ebd500bec6d046fa851dc81340d838f0347e616107e8
curl -s "https://hub.docker.com/v2/repositories/library/postgres/tags/18.6-alpine" \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print('digest:',d['digest'],'pushed:',d['last_updated'])"

# d) record the inventory you must see again after the cutover (the acceptance test)
OLD=$(mise exec -- kubectl get pods -n databases -l app=superset-pg -o jsonpath='{.items[0].metadata.name}')
PSQL='PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
mise exec -- kubectl exec -i -n databases $OLD -- sh -c "$PSQL -At -f -" <<'SQL'
select 'dashboards='||count(*) from dashboards
union all select 'slices='||count(*) from slices
union all select 'saved_query='||count(*) from saved_query
union all select 'dbs='||count(*) from dbs
union all select 'ab_user='||count(*) from ab_user
union all select 'ab_user_role='||count(*) from ab_user_role;
SQL
mise exec -- kubectl exec -n databases $OLD -- sh -c "$PSQL -At -c 'select version_num from alembic_version;'"
mise exec -- kubectl exec -n databases $OLD -- sh -c "$PSQL -At -c 'show max_connections;'"
mise exec -- kubectl exec -n databases $OLD -- sh -c "$PSQL -At -c \"show server_encoding;\" -c \"show lc_collate;\""

# e) no in-flight reconcile
mise exec -- flux get kustomizations -A | awk 'NR==1 || $5!="True"'
```

## 3) Steps

### Stage A — stand up the new (18.6) DB, additive, app untouched

1. **New manifests** in `kubernetes/apps/databases/superset/app/`:

   `pg18-deployment.yaml` (model: `pg-deployment.yaml`, adjusted for the
   postgres:18 image layout per §1 — no `PGDATA`, no `POSTGRES_INITDB_ARGS`,
   volume mounts at `/var/lib/postgresql`):
   ```yaml
   ---
   # Replacement Superset metadata DB (postgres 18.6), plan superset-pg-18.6.
   # Runs ALONGSIDE the current superset-pg (17.11) until this plan's cutover,
   # and superset-pg (17.11) then stays up as the rollback through a soak.
   # postgres:18+ image layout: PGDATA defaults to /var/lib/postgresql/18/docker
   # under the /var/lib/postgresql mount — do NOT override PGDATA (see
   # docs/sops/bundled-datastore-exit.md, authentik-postgres-18 precedent).
   apiVersion: apps/v1
   kind: Deployment
   metadata:
     name: superset-pg18
     namespace: databases
     labels:
       app: superset-pg18
   spec:
     replicas: 1
     strategy:
       type: Recreate   # RWO Longhorn PVC — see docs/sops/longhorn-rwo-multi-attach.md
     selector:
       matchLabels:
         app: superset-pg18
     template:
       metadata:
         labels:
           app: superset-pg18
       spec:
         containers:
         - name: postgresql
           image: postgres:18.6-alpine@sha256:63bdc97d67b5133bf0e5ebd500bec6d046fa851dc81340d838f0347e616107e8
           imagePullPolicy: IfNotPresent
           ports:
           - containerPort: 5432
             name: postgresql
           env:
           - name: POSTGRES_USER
             valueFrom: {secretKeyRef: {name: superset-secrets, key: DB_USER}}
           - name: POSTGRES_PASSWORD
             valueFrom: {secretKeyRef: {name: superset-secrets, key: DB_PASS}}
           - name: POSTGRES_DB
             valueFrom: {secretKeyRef: {name: superset-secrets, key: DB_NAME}}
           # no PGDATA override, no POSTGRES_INITDB_ARGS — see header comment
           resources:
             requests: {cpu: 100m, memory: 256Mi}
             limits: {memory: 1Gi}
           volumeMounts:
           - name: data
             mountPath: /var/lib/postgresql
           readinessProbe:
             exec: {command: ["/bin/sh","-c","exec pg_isready -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\""]}
             initialDelaySeconds: 15
             timeoutSeconds: 2
             periodSeconds: 10
           livenessProbe:
             exec: {command: ["/bin/sh","-c","exec pg_isready -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\""]}
             initialDelaySeconds: 30
             timeoutSeconds: 2
             periodSeconds: 10
         volumes:
         - name: data
           persistentVolumeClaim:
             claimName: superset-pg18-data
   ---
   apiVersion: v1
   kind: Service
   metadata:
     name: superset-pg18
     namespace: databases
     labels:
       app: superset-pg18
   spec:
     type: ClusterIP
     ports:
     - port: 5432
       targetPort: 5432
       protocol: TCP
       name: postgresql
     selector:
       app: superset-pg18
   ```

   `pg18-pvc.yaml` / `pg18-pv.yaml` / `pg18-longhorn-volume.yaml`: copy
   `pg-pvc.yaml`/`pg-pv.yaml`/`pg-longhorn-volume.yaml` with every
   `superset-pg-data` renamed to `superset-pg18-data` (PV name == PVC name ==
   volumeHandle == Longhorn Volume name, per `docs/sops/longhorn.md`). Keep
   the same 20Gi size and `numberOfReplicas: 2`.

2. Add `pg18-pv.yaml` and `pg18-pvc.yaml` (NOT `pg18-longhorn-volume.yaml`) to
   `kustomization.yaml`'s `resources:`, matching the existing comment pattern
   for why the Longhorn Volume CR is excluded.

3. Hand-apply the Longhorn Volume CR (Flux cannot own it — `targetNamespace`
   would break it):
   ```bash
   mise exec -- kubectl apply -f kubernetes/apps/databases/superset/app/pg18-longhorn-volume.yaml
   ```

4. Validate, commit, push (additive only — nothing repointed yet):
   ```bash
   mise exec -- kubeconform -summary -exit-on-error -ignore-missing-schemas kubernetes/apps/databases/superset
   git add kubernetes/apps/databases/superset/app/pg18-deployment.yaml \
           kubernetes/apps/databases/superset/app/pg18-pv.yaml \
           kubernetes/apps/databases/superset/app/pg18-pvc.yaml \
           kubernetes/apps/databases/superset/app/pg18-longhorn-volume.yaml \
           kubernetes/apps/databases/superset/app/kustomization.yaml
   git commit -m "feat(superset): stand up postgres 18.6 replacement metadata DB (superset-pg18)"
   git push
   ```

5. Confirm the new DB is up, empty, and reachable — nothing references it yet:
   ```bash
   mise exec -- kubectl get pods -n databases -l app=superset-pg18
   mise exec -- kubectl get pvc -n databases superset-pg18-data     # Bound
   NEW=$(mise exec -- kubectl get pods -n databases -l app=superset-pg18 -o jsonpath='{.items[0].metadata.name}')
   mise exec -- kubectl exec -n databases $NEW -- sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\dt"'   # no tables (expected)
   ```

### Stage B — cutover (dump/restore/repoint)

Same suspend-both pattern as `superset-pg-cutover.md` §3a — Superset's
`superset-init-db` hook fires `superset db upgrade` against whatever
`DB_HOST` currently resolves to on **any** `spec.values` change, so a bare
`kubectl scale --replicas=0` does not hold (Flux drift-corrects it) and the
values route performs the empty-target write from the hook. Read that plan's
§3a in full before running the commands below; it is not repeated verbatim
here.

6. **Marker**:
   ```bash
   runbooks/update-marker.sh add superset databases 2 "superset-pg engine upgrade 17.11 -> 18.6 (app stopped for consistent dump)"
   ```
7. **Quiesce**, per `superset-pg-cutover.md` §3a (suspend HelmRelease AND
   Kustomization, scale to 0, prove the hold at the database with a
   `pg_stat_activity` check — not just at the pod level).
8. **Fresh dump from `superset-pg` (17.11), restore into `superset-pg18`:**
   ```bash
   STAMP=$(date +%F-%H%M)
   OLD=$(mise exec -- kubectl get pods -n databases -l app=superset-pg  -o jsonpath='{.items[0].metadata.name}')
   NEW=$(mise exec -- kubectl get pods -n databases -l app=superset-pg18 -o jsonpath='{.items[0].metadata.name}')
   mise exec -- kubectl exec -n databases $OLD -- \
     sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB"' \
     > /tmp/superset-pg18-$STAMP.dump
   ls -l /tmp/superset-pg18-$STAMP.dump                     # not zero bytes
   mise exec -- kubectl cp /tmp/superset-pg18-$STAMP.dump databases/$NEW:/tmp/cutover.dump
   mise exec -- kubectl exec -n databases $NEW -- \
     sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-privileges /tmp/cutover.dump' 2>&1 | tail -30
   ```
   Read the `pg_restore` output — ownership/extension warnings are benign, any
   `error:` line is not. Stop and roll back (nothing to revert yet — just
   delete the failed restore's contents and re-restore) rather than cutting
   over onto a partial DB.

9. **CONTENTS ASSERTION — exact per-table row counts on BOTH servers, diffed,
   BEFORE the repoint.** Do not use `pg_stat_user_tables.n_live_tup` — it is a
   planner estimate (`docs/sops/verification-contents-not-shape.md`).
   ```bash
   PSQL='PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
   for POD in $OLD $NEW; do
     mise exec -- kubectl exec -i -n databases $POD -- sh -c "$PSQL -At -f -" <<'SQL' > /tmp/pg18compare-$POD.txt
   select c.relname||'='||(xpath('/row/c/text()',
       query_to_xml(format('select count(*) as c from %I.%I', n.nspname, c.relname),
                    false, true, '')))[1]::text::bigint
     from pg_class c join pg_namespace n on n.oid = c.relnamespace
     where c.relkind = 'r' and n.nspname = 'public' order by c.relname;
   SQL
     echo "--- $POD ($(wc -l < /tmp/pg18compare-$POD.txt) tables)"
   done
   diff /tmp/pg18compare-$OLD.txt /tmp/pg18compare-$NEW.txt && echo "IDENTICAL — safe to repoint"
   # Any diff output: STOP — do not repoint.
   ```
   Also run the fidelity checks from `docs/sops/bundled-datastore-exit.md` §6
   Test 2 (4-byte round-trip) and Test 3 (`max_connections`/encoding/collation
   parity against the pre-check values from §2d) — counts alone pass over
   silent transcoding.

10. **The cutover** — edit the SOPS secret in place:
    ```bash
    sops kubernetes/apps/databases/superset/app/secret.sops.yaml
    #   DB_HOST: superset-pg18    (was superset-pg)
    #   DB_PORT/DB_USER/DB_PASS/DB_NAME: UNCHANGED
    ```
    ```bash
    git add kubernetes/apps/databases/superset/app/secret.sops.yaml
    git commit -m "feat(superset): cut metadata DB over to postgres 18.6 (superset-pg18; old superset-pg kept as rollback)"
    git push
    ```

11. **Resume**, in the §3a order (Kustomization first with HelmRelease still
    suspended, re-prove the hold, then HelmRelease, then scale up):
    ```bash
    mise exec -- flux resume kustomization superset -n databases
    mise exec -- kubectl get secret -n databases superset-secrets -o jsonpath='{.data.DB_HOST}' | base64 -d   # superset-pg18
    mise exec -- flux resume helmrelease superset -n databases
    mise exec -- kubectl scale deploy/superset deploy/superset-worker deploy/superset-celerybeat -n databases --replicas=1
    mise exec -- kubectl rollout status deploy/superset -n databases --timeout=600s
    ```
12. Clear the marker only after §4 passes: `runbooks/update-marker.sh clear superset`.

## 4) Verification

```bash
cd /Users/mu/code/cberg-home-nextgen
PSQL='PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
NEW=$(mise exec -- kubectl get pods -n databases -l app=superset-pg18 -o jsonpath='{.items[0].metadata.name}')
OLD=$(mise exec -- kubectl get pods -n databases -l app=superset-pg  -o jsonpath='{.items[0].metadata.name}')

# a) the app really is talking to the new host
mise exec -- kubectl exec -n databases deploy/superset        -- printenv DB_HOST   # superset-pg18
mise exec -- kubectl exec -n databases deploy/superset-worker -- printenv DB_HOST   # superset-pg18

# b) pods healthy, no connection/alembic errors
mise exec -- kubectl get pods -n databases | grep superset
mise exec -- kubectl logs -n databases deploy/superset --since=15m \
  | grep -iE 'error|traceback|could not connect|alembic' | head -20

# c) CONTENTS ASSERTION (repeat, post-repoint) — identical to the pre-check baseline
#    from §2d, on the NEW database:
mise exec -- kubectl exec -i -n databases $NEW -- sh -c "$PSQL -At -f -" <<'SQL'
select 'dashboards='||count(*) from dashboards
union all select 'slices='||count(*) from slices
union all select 'saved_query='||count(*) from saved_query
union all select 'dbs='||count(*) from dbs
union all select 'ab_user='||count(*) from ab_user
union all select 'ab_user_role='||count(*) from ab_user_role;
SQL
mise exec -- kubectl exec -n databases $NEW -- sh -c "$PSQL -At -c 'select version_num from alembic_version;'"   # identical to §2d
mise exec -- kubectl exec -n databases $NEW -- sh -c "$PSQL -At -c 'show max_connections;'"                      # matches §2d

# d) old superset-pg (17.11) still running and now idle — it is the rollback
mise exec -- kubectl get pods -n databases | grep -w superset-pg
mise exec -- kubectl exec -i -n databases $OLD -- sh -c "$PSQL -At -c \"select count(*) from pg_stat_activity where datname=current_database() and pid<>pg_backend_pid();\""   # ~0

# e) THE load-bearing check is human — a restored-but-empty/wrong metadata DB
#    is invisible at pod level (docs/sops/verification-contents-not-shape.md):
DOM=$(mise exec -- kubectl get secret -n flux-system cluster-secrets -o jsonpath='{.data.SECRET_DOMAIN}' | base64 -d)
curl -s -o /dev/null -w '%{http_code}\n' --max-time 20 "https://superset.$DOM/health"   # 200 is the FLOOR, not the check
#   * log in via Authentik OIDC, confirm your role survived;
#   * open the dashboard, confirm charts render with real data;
#   * open SQL Lab, run a saved query against the `Pellets` database connection.
```

Success = both app pods reporting `DB_HOST=superset-pg18`, no
connection/alembic errors, row counts and `alembic_version` **identical** to
the pre-check baseline, `max_connections` at parity, old `superset-pg` idle
but running, `/health` 200, and the operator smoke test passing.

## 5) Rollback

The old `superset-pg` (17.11) is never modified by this plan and keeps running
with the pre-cutover data for the whole soak — rollback is a plain revert:

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <cutover-commit-sha>      # restores DB_HOST -> superset-pg
git push
mise exec -- kubectl rollout restart deploy/superset deploy/superset-worker deploy/superset-celerybeat -n databases
mise exec -- kubectl rollout status deploy/superset -n databases --timeout=600s
mise exec -- kubectl exec -n databases deploy/superset -- printenv DB_HOST     # superset-pg
DOM=$(mise exec -- kubectl get secret -n flux-system cluster-secrets -o jsonpath='{.data.SECRET_DOMAIN}' | base64 -d)
curl -s -o /dev/null -w '%{http_code}\n' --max-time 20 "https://superset.$DOM/health"   # 200
```

**Anything written to `superset-pg18` after the cutover is lost by this
revert** — at most a few minutes of UI activity within the window, which is
why the revert decision must be made inside the window.

**Recovery floor** (only if `superset-pg` were somehow damaged in the
meantime, which this plan does not touch): restore Longhorn volume
`superset-pg-data` from its most recent backup (`docs/sops/backup.md`), or
`pg_restore` from `/tmp/superset-pg18-*.dump` — a second, independent copy.

If the failure is discovered only AFTER `superset-pg18` has been running as
the live DB for a while (post-soak), do not attempt this revert — that is what
the future decommission plan's own gate exists to prevent by requiring ≥7
days of clean operation first (same pattern as `authentik-pg17-decommission`).

## 6) Interference notes

- **`depends_on: [superset-6.1.0]` is the one that matters.** `superset-6.1.0`
  (`status: draft`, `window: sun-attended:2026-09-20`) has a **hard, literal**
  ordering gate baked into its own §2a: `printenv DB_HOST` on `deploy/superset`
  "MUST print: `superset-pg` — if it still prints `superset-postgresql`, STOP."
  That gate checks for the exact string `superset-pg`. If THIS plan runs
  first and repoints `DB_HOST` to `superset-pg18`, `superset-6.1.0`'s
  pre-check fails outright (its check has no branch for a *further-renamed*
  host) and would need hand-correction mid-window to even proceed — exactly
  the kind of surprise a window agent should not discover live. Independent of
  the literal string match, `superset-6.1.0`'s own frontmatter explains
  **why** it was scheduled after the prior DB soak rather than compressed
  into it: stacking an app major's 13 one-way Alembic migrations on top of a
  freshly-cut-over (or, worse, mid-cutover) database means an app-level
  failure and a DB-engine failure become inseparable to unwind. The same
  reasoning applies here in reverse — run the Postgres engine bump only AFTER
  `superset-6.1.0` has executed and soaked, not before and not concurrently.
  **Do not schedule this plan into any window before `superset-6.1.0` shows
  `status: executed`.**
- **`paperclip-postgresql`** (`ai` namespace) is the other standalone
  `postgres:17.11-alpine → 18.6-alpine` MAJOR still open
  (`runbooks/version-check-current.md`). It shares no namespace, resource, or
  storage with this plan — there is no *technical* interference — but it is
  the same risk CLASS (one-way metadata/app-DB major) and the operator has
  shown a consistent preference (see `superset-6.1.0`'s own scheduling
  rationale) for not stacking more than one such migration in a single
  window. Recommend the window agent schedule `superset-pg-18.6` and any
  future `paperclip-postgresql-18.6` plan into **separate** windows even
  though nothing here technically conflicts.
- **`authentik-pg17-decommission`** (`kube-system`, `status: awaiting-soak`)
  is unrelated in namespace and resources — authentik's own Postgres 17→18
  migration (`authentik-postgres-18`) already executed 2026-08-20; what
  remains open there is retiring the *old* 17.11 bitnamilegacy StatefulSet,
  not a pg18 stand-up. No shared surface with this plan; noted only because
  it is the same SOP (`docs/sops/bundled-datastore-exit.md`) and the same
  "old DB kept as rollback through a soak" shape, so a window agent scanning
  for "two DB migrations this week" should not conflate the two.
- **Real outage:** Superset is scaled to 0 for the consistent dump
  (~10–20 min), same as `superset-pg-cutover`. `ALERT_REPORTS` does not fire
  during it. Do not schedule alongside anything that queries Superset.
- **Do not fold a decommission of the old `superset-pg` (17.11) into this
  window.** Keeping it alive and idle is the entire rollback story for the
  soak period, exactly like `superset-pg-decommission` was kept separate from
  `superset-pg-cutover` by design. A follow-up plan (analogous to
  `authentik-pg17-decommission`) should be written after ≥7 clean days on
  `superset-pg18`, not now.
- Superset's chart stays at whatever `superset-6.1.0` leaves it at
  (0.22.4 as of this writing). This plan touches no HelmRelease values other
  than triggering the same suspend/resume dance `superset-pg-cutover` used —
  it does not itself cause a Helm upgrade, so no post-upgrade hook fires
  outside the deliberate suspend window.
- Storage safety: both PVCs here are `longhorn-static` with `Retain`, not a
  CIFS/SMB/NFS class — the catastrophic share-wipe failure mode in
  `docs/sops/storage-safety.md` does not apply. This plan performs no PVC
  deletion of any kind.
