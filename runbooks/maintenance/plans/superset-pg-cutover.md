---
plan_id: superset-pg-cutover
component: superset
pr: null
kind: infra
current: "Superset metadata DB = bundled bitnamilegacy/postgresql 14.17.0 (chart subchart), new postgres:17.11-alpine standing by"
target: "Superset metadata DB = postgres:17.11-alpine (superset-pg); the old bundled DB stays RUNNING as the rollback"
update_type: major
risk: high                            # the metadata DB IS Superset: dashboards, charts, users
est_duration_min: 50
needs_reboot: false
touches:
  namespaces: [databases]
  resources:
    - secret/superset-secrets          # DB_HOST repointed (SOPS edit) — the actual cutover
    - deployment/superset              # restarts onto the new DB
    - deployment/superset-worker
    - deployment/superset-celerybeat
    - deployment/superset-pg           # becomes the live metadata DB
    - "superset-postgresql (old, left RUNNING — it is the rollback)"
  shared: []
depends_on: []  # RESOLVED 2026-08-18: superset-pg-standup EXECUTED 2026-08-18 (95322f1f, 47/47 tables verified) — dependency satisfied
conflicts_with: [longhorn-1.12.1-engine]
status: draft
window: "wed-early:2026-08-26"                 # RESHUFFLED 2026-08-16 onto the daily-window cadence
                                      # (7 windows/week, was 4). Deliberate soaks are
                                      # preserved, not compressed — see the windows YAML.
auto_execute: false
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/backup.md
  - docs/sops/sops-encryption.md
generated: "2026-08-15"
---

# Superset stage 3/4 — cut Superset over to the new Postgres (old DB kept running)

## 1) Summary & why held

Stage 3 of 4. The replacement Postgres exists and has been verified (stage 2). This
stage moves Superset onto it with a **fresh** dump/restore and then proves the
application — not the pod — is healthy. **The old bundled Postgres is deliberately
left running: it is the rollback.** Decommissioning it is stage 4, after a soak.

**Why it is high risk.** The metadata DB is Superset: every dashboard, chart, saved
query, database connection and user/role lives there. A restore that "succeeds" into
a half-populated schema produces a perfectly healthy pod and an empty UI. That is why
verification below is row counts plus a human smoke test, and why this sits in a
90-minute window with 40 minutes of slack for the revert.

**Why the cutover itself is one line.** `superset-secrets` already carries
`DB_HOST`/`DB_PORT`/`DB_USER`/`DB_PASS`/`DB_NAME`, and the chart mounts it via
`envFromSecrets` **after** its own generated env Secret — later `envFrom` entries
win, so the app-side connection is decided entirely by that Secret. Verified against
chart 0.22.4's `templates/deployment.yaml` (`envFrom:` lists
`.Values.envFromSecret` first, then `range .Values.envFromSecrets`) and
`_helpers.tpl`, where `SQLALCHEMY_DATABASE_URI` is built at runtime from
`env('DB_HOST')`, `env('DB_USER')`, `env('DB_PASS')`, `env('DB_NAME')`.
So: change `DB_HOST`, restart, done. No chart values plumbing, no plaintext password
in a ConfigMap.

**The consistency requirement that makes this a window job.** The dump must be taken
with Superset **stopped**, or a dashboard saved between dump and cutover is silently
lost. The sequence below scales Superset to 0 first, so there is a real outage of
roughly 10–20 minutes. Superset is an internal analytics UI; that is acceptable in
an early-morning weekend window with the operator present.

## 2) Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen

# --- credentials (run first in EVERY shell that talks to a database) ---------
# The OLD bundled Postgres rejects passwordless local connections
# (`fe_sendauth: no password supplied`) — its password lives in a file INSIDE the
# pod, so fetch it from there rather than from SOPS. Both servers share the same
# credentials (stage 2), so this one value works against either.
OLDPW=$(mise exec -- kubectl exec -n databases superset-postgresql-0 -- \
        cat /opt/bitnami/postgresql/secrets/postgresql-password)
[ -n "$OLDPW" ] || { echo "FAILED to read the DB password — stop here"; }
NEW=$(mise exec -- kubectl get pods -n databases -l app=superset-pg -o jsonpath='{.items[0].metadata.name}')

# a) stage 2 landed, and the standby is still healthy
mise exec -- kubectl get deploy -n databases superset-pg \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"  ready="}{.status.readyReplicas}{"\n"}'
mise exec -- kubectl get pvc -n databases superset-pg-data     # Bound
mise exec -- kubectl exec -n databases deploy/superset -- printenv DB_HOST    # still the OLD host

# b) both databases answer
mise exec -- kubectl exec -n databases superset-postgresql-0 -- env PGPASSWORD="$OLDPW" \
  psql -U superset -d superset -c 'select 1;'
mise exec -- kubectl exec -n databases $NEW -- env PGPASSWORD="$OLDPW" \
  psql -U superset -d superset -c 'select 1;'

# c) record the inventory you must see again after the cutover (this IS the acceptance test)
mise exec -- kubectl exec -n databases superset-postgresql-0 -- env PGPASSWORD="$OLDPW" \
  psql -U superset -d superset -At -c "
  select 'dashboards='||count(*) from dashboards
  union all select 'slices='||count(*) from slices
  union all select 'saved_query='||count(*) from saved_query
  union all select 'dbs='||count(*) from dbs
  union all select 'ab_user='||count(*) from ab_user
  union all select 'ab_user_role='||count(*) from ab_user_role;"
mise exec -- kubectl exec -n databases superset-postgresql-0 -- env PGPASSWORD="$OLDPW" \
  psql -U superset -d superset -At -c \
  "select version_num from alembic_version;"       # must match on the new DB afterwards

# d) FRESH Longhorn backup of the OLD volume before touching anything
mise exec -- kubectl get volume -n storage superset-postgresql-data \
  -o custom-columns=NAME:.metadata.name,STATE:.status.state,ROBUST:.status.robustness,LASTBACKUP:.status.lastBackupAt
# require lastBackupAt within the hour.

# e) no in-flight reconcile; operator present for the smoke test
mise exec -- flux get kustomizations -A | awk 'NR==1 || $5!="True"'
```

## 3) Steps

1. **Marker** (a real outage is expected — Superset is stopped for the dump):
   ```bash
   runbooks/update-marker.sh add superset databases 2 "superset metadata DB cutover to postgres 17.11 (app stopped for consistent dump)"
   ```
2. **Quiesce Superset** so the dump is consistent. This is a live cluster action —
   delegate to cberg-agent per the maintenance-window contract:
   ```bash
   mise exec -- kubectl scale deploy/superset deploy/superset-worker deploy/superset-celerybeat -n databases --replicas=0
   mise exec -- kubectl get pods -n databases | grep superset          # only the two DBs remain
   ```
3. **Fresh dump from the old DB, restore into the new one** (discard stage 2's dump —
   it is stale by design):
   ```bash
   STAMP=$(date +%F-%H%M)
   mise exec -- kubectl exec -n databases superset-postgresql-0 -- env PGPASSWORD="$OLDPW" \
     pg_dump -U superset -Fc superset > /tmp/superset-cutover-$STAMP.dump
   ls -l /tmp/superset-cutover-$STAMP.dump                              # not zero bytes

   NEW=$(mise exec -- kubectl get pods -n databases -l app=superset-pg -o jsonpath='{.items[0].metadata.name}')
   # start from a clean schema so a partial stage-2 restore cannot masquerade as success
   mise exec -- kubectl exec -n databases $NEW -- \
     sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "drop schema public cascade; create schema public;"'
   mise exec -- kubectl cp /tmp/superset-cutover-$STAMP.dump databases/$NEW:/tmp/cutover.dump
   mise exec -- kubectl exec -n databases $NEW -- \
     sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-privileges /tmp/cutover.dump' 2>&1 | tail -30
   ```
   **Read the `pg_restore` output.** Ownership/extension warnings are benign; any
   `error:` line is not — stop and roll back rather than cutting over onto a partial DB.
4. **Compare the two databases before repointing anything**:
   ```bash
   # EXACT per-table counts. Do NOT use pg_stat_user_tables.n_live_tup here: it is a
   # planner ESTIMATE maintained by autovacuum/ANALYZE, and it currently reads 0 for
   # every table on the OLD server while reading true counts on the freshly-restored
   # new one — i.e. the comparison would report a total mismatch on two identical
   # databases and abort a correct cutover. query_to_xml counts rows for real, and
   # runs on both PG14 and PG17.
   COUNTSQL="select c.relname||'='||(xpath('/row/c/text()',
       query_to_xml(format('select count(*) as c from %I.%I', n.nspname, c.relname),
                    false, true, '')))[1]::text::bigint
     from pg_class c join pg_namespace n on n.oid = c.relnamespace
     where c.relkind = 'r' and n.nspname = 'public' order by c.relname;"
   for POD in superset-postgresql-0 $NEW; do
     mise exec -- kubectl exec -n databases $POD -- env PGPASSWORD="$OLDPW" \
       psql -U superset -d superset -At -c "$COUNTSQL" > /tmp/pgcompare-$POD.txt
     echo "--- $POD  ($(wc -l < /tmp/pgcompare-$POD.txt) tables)"
   done
   diff /tmp/pgcompare-superset-postgresql-0.txt /tmp/pgcompare-$NEW.txt \
     && echo "IDENTICAL — safe to repoint"
   # `diff` must be silent (47 tables as of 2026-08-18). Any output: STOP — do not repoint.
   ```
5. **The cutover** — edit the SOPS secret in place (never via `/tmp`; see
   `docs/sops/sops-encryption.md` and the SOPS rules in `CLAUDE.md`):
   ```bash
   sops kubernetes/apps/databases/superset/app/secret.sops.yaml
   #   DB_HOST: superset-pg          (was superset-postgresql)
   #   DB_PORT/DB_USER/DB_PASS/DB_NAME: UNCHANGED — stage 2 gave the new server the same creds
   ```
   ```bash
   git add kubernetes/apps/databases/superset/app/secret.sops.yaml
   git commit -m "feat(superset): cut metadata DB over to postgres 17.11 (old bitnamilegacy DB kept as rollback)"
   git push
   ```
   Leave `postgresql.enabled: true` in the HelmRelease — the old DB must keep running.
6. **Bring Superset back up**:
   ```bash
   mise exec -- kubectl scale deploy/superset deploy/superset-worker deploy/superset-celerybeat -n databases --replicas=1
   mise exec -- kubectl rollout status deploy/superset -n databases --timeout=600s
   ```
   The pods must pick up the new `DB_HOST`; the `stakater.com/reload` annotation on
   the Secret plus the fresh rollout covers this — confirm in §4a, do not assume.
7. Clear the marker only after §4 passes: `runbooks/update-marker.sh clear superset`.

## 4) Verification

```bash
cd /Users/mu/code/cberg-home-nextgen

# --- credentials (run first in EVERY shell that talks to a database) ---------
# The OLD bundled Postgres rejects passwordless local connections
# (`fe_sendauth: no password supplied`) — its password lives in a file INSIDE the
# pod, so fetch it from there rather than from SOPS. Both servers share the same
# credentials (stage 2), so this one value works against either.
OLDPW=$(mise exec -- kubectl exec -n databases superset-postgresql-0 -- \
        cat /opt/bitnami/postgresql/secrets/postgresql-password)
[ -n "$OLDPW" ] || { echo "FAILED to read the DB password — stop here"; }
NEW=$(mise exec -- kubectl get pods -n databases -l app=superset-pg -o jsonpath='{.items[0].metadata.name}')

# a) THE first check — the app really is talking to the new host
mise exec -- kubectl exec -n databases deploy/superset -- printenv DB_HOST         # superset-pg
mise exec -- kubectl exec -n databases deploy/superset-worker -- printenv DB_HOST  # superset-pg
# A pod still showing the old host means the restart did not pick up the Secret —
# the cutover has NOT happened, whatever the UI shows.

# b) pods healthy
mise exec -- kubectl get pods -n databases | grep superset
mise exec -- kubectl logs -n databases deploy/superset --since=15m \
  | grep -iE 'error|traceback|could not connect|alembic' | head -20
mise exec -- kubectl logs -n databases deploy/superset-worker --since=15m | tail -20

# c) data intact — compare against the pre-check inventory, on the NEW database
mise exec -- kubectl exec -n databases $NEW -- env PGPASSWORD="$OLDPW" \
  psql -U superset -d superset -At -c "
  select 'dashboards='||count(*) from dashboards
  union all select 'slices='||count(*) from slices
  union all select 'saved_query='||count(*) from saved_query
  union all select 'dbs='||count(*) from dbs
  union all select 'ab_user='||count(*) from ab_user
  union all select 'ab_user_role='||count(*) from ab_user_role;"
mise exec -- kubectl exec -n databases $NEW -- env PGPASSWORD="$OLDPW" \
  psql -U superset -d superset -At -c \
  "select version_num from alembic_version;"      # identical to pre-check

# d) the old DB is still running and now IDLE (it is the rollback — do not stop it)
mise exec -- kubectl get pods -n databases | grep superset-postgresql
mise exec -- kubectl exec -n databases superset-postgresql-0 -- env PGPASSWORD="$OLDPW" \
  psql -U superset -d superset -At -c \
  "select count(*) from pg_stat_activity where datname='superset' and state='active';"   # ~0

# e) THE load-bearing check is human. A restored-but-wrong metadata DB is invisible
#    at pod level and empty in the UI:
DOM=$(mise exec -- kubectl get secret -n flux-system cluster-secrets -o jsonpath='{.data.SECRET_DOMAIN}' | base64 -d)
curl -s -o /dev/null -w '%{http_code}\n' --max-time 20 "https://superset.$DOM/health"    # 200
#   * log in via Authentik OIDC and confirm your ROLE survived (Admin, not a fresh Gamma);
#   * open a dashboard that uses a saved chart and confirm panels render;
#   * open SQL Lab, run a SAVED query against a configured database connection;
#   * confirm the Databases list still shows every configured connection.
```

Success = both app pods reporting the new `DB_HOST`, no connection/alembic errors,
row counts and `alembic_version` identical to the pre-check, the old DB idle but
running, `/health` 200, and the operator smoke test passing on dashboards, roles and
saved queries.

## 5) Rollback

**The old database is still running and still holds the pre-cutover data — that is
the rollback, and it is why stage 4 is separate.**

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <cutover-commit-sha>      # restores DB_HOST -> superset-postgresql
git push
mise exec -- kubectl rollout restart deploy/superset deploy/superset-worker deploy/superset-celerybeat -n databases
mise exec -- kubectl rollout status deploy/superset -n databases --timeout=600s
mise exec -- kubectl exec -n databases deploy/superset -- printenv DB_HOST     # superset-postgresql
DOM=$(mise exec -- kubectl get secret -n flux-system cluster-secrets -o jsonpath='{.data.SECRET_DOMAIN}' | base64 -d)
curl -s -o /dev/null -w '%{http_code}\n' --max-time 20 "https://superset.$DOM/health"   # 200
```
Then re-run the pre-check inventory query against `superset-postgresql-0` (with the
`$OLDPW` preamble from §2 — a bare `psql` in that pod fails `fe_sendauth: no password
supplied`) and confirm it matches what you recorded before the window.

**Anything written to the new DB after the cutover is lost by this revert.** Within a
single window that is at most a few minutes of UI activity, which is why the revert
decision must be made inside the window and not deferred.

**Recovery floor** (only if the old DB is somehow damaged): restore Longhorn volume
`superset-postgresql-data` from the pre-check backup per `docs/sops/backup.md` +
`docs/sops/longhorn.md`, and keep `/tmp/superset-cutover-*.dump` — it is a second,
independent copy of the same data.

## 6) Interference notes

- **Out of order:** without `superset-pg-standup` the target host does not exist. The
  chart's `wait-for-postgres` init container blocks for 120 s and the pod then fails —
  Superset stays down until the Secret is reverted. Nothing is corrupted, but the
  window is lost. Running stage 4 before this one deletes the source database.
- **Do not fold stage 4 into this window.** Keeping the old Postgres alive is the
  entire rollback story; `postgresql.enabled: false` in the same window converts a
  one-line revert into a restore-from-dump.
- **Real outage:** Superset is scaled to 0 for the consistent dump (~10–20 min).
  Alerts/reports (`ALERT_REPORTS: True`) do not fire during it. Do not schedule
  alongside anything that queries Superset.
- **`conflicts_with: longhorn-1.12.1-engine`** — shared storage layer; a DB
  cutover must not run under storage-engine work.
- Superset's chart stays at 0.22.4 throughout. Per
  `project_superset_chart_020_redis_auth`, a chart up/down bump requires deleting the
  immutable-selector Deployments — never combine that with a data cutover.
- After this stage the namespace still contains the `bitnamilegacy/postgresql` image
  (idle). The CVE finding does **not** clear until stage 4.
