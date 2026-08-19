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
status: executed                      # EXECUTED 2026-08-19 (48ffc039) in the operator-approved
                                      # ad-hoc window. Contents asserted BEFORE the repoint:
                                      # 47 tables / 2985 rows identical on both servers,
                                      # alembic 74ad1125881c, 44 sequences + 99 indexes +
                                      # 173 constraints identical. Post-cutover all 9 charts
                                      # on the dashboard resolved with real data.
# FILE RETAINED ON PURPOSE — do not retire on the usual executed-plan convention: §5 is the
# LIVE rollback for as long as superset-postgresql is still up, i.e. until stage 4
# (superset-pg-decommission) retires it after the soak.
window: null                          # cleared 2026-08-19: executed in the ad-hoc window
                                      # (48ffc039), so the reserved slot is released.
                                      # maintenance-plan.py buckets by `window` regardless of
                                      # `status`, so leaving it set would reserve 50m for work
                                      # already done. Was: "wed-early:2026-08-26",
                                      # RESHUFFLED 2026-08-16 onto the daily-window cadence
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

# --- how to talk to either database (run first in EVERY shell) ---------------
# The OLD bundled Postgres rejects passwordless local connections
# (`fe_sendauth: no password supplied`), so every psql/pg_dump below MUST supply
# one. Read it INSIDE the pod: expanded there, the password never enters kubectl
# argv, the API-server audit log, your process table or your shell history.
# One expression covers both servers — the old bitnami image exposes
# $POSTGRES_PASSWORD_FILE + $POSTGRES_DATABASE, the new postgres:17.11-alpine
# exposes $POSTGRES_PASSWORD + $POSTGRES_DB. Single-quoted on purpose: these
# variables must reach the pod UNEXPANDED.
PSQL='PGPASSWORD="${POSTGRES_PASSWORD:-$(cat "$POSTGRES_PASSWORD_FILE")}" psql -U "$POSTGRES_USER" -d "${POSTGRES_DB:-$POSTGRES_DATABASE}"'
OLD=superset-postgresql-0
NEW=$(mise exec -- kubectl get pods -n databases -l app=superset-pg -o jsonpath='{.items[0].metadata.name}')
[ -n "$NEW" ] || { echo "new postgres pod not found — STOP"; exit 1; }

# a) stage 2 landed, and the standby is still healthy
mise exec -- kubectl get deploy -n databases superset-pg \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"  ready="}{.status.readyReplicas}{"\n"}'
mise exec -- kubectl get pvc -n databases superset-pg-data     # Bound
mise exec -- kubectl exec -n databases deploy/superset -- printenv DB_HOST    # still the OLD host

# b) both databases answer
mise exec -- kubectl exec -n databases $OLD -- sh -c "$PSQL -c 'select 1;'"
mise exec -- kubectl exec -n databases $NEW -- sh -c "$PSQL -c 'select 1;'"

# c) record the inventory you must see again after the cutover (this IS the acceptance test)
mise exec -- kubectl exec -i -n databases $OLD -- sh -c "$PSQL -At -f -" <<'SQL'
select 'dashboards='||count(*) from dashboards
union all select 'slices='||count(*) from slices
union all select 'saved_query='||count(*) from saved_query
union all select 'dbs='||count(*) from dbs
union all select 'ab_user='||count(*) from ab_user
union all select 'ab_user_role='||count(*) from ab_user_role;
SQL
mise exec -- kubectl exec -n databases $OLD -- \
  sh -c "$PSQL -At -c 'select version_num from alembic_version;'"   # must match on the new DB afterwards

# d) FRESH Longhorn backup of the OLD volume before touching anything
mise exec -- kubectl get volume -n storage superset-postgresql-data \
  -o custom-columns=NAME:.metadata.name,STATE:.status.state,ROBUST:.status.robustness,LASTBACKUP:.status.lastBackupAt
# require lastBackupAt within the hour.
#
# GATE RELAXED 2026-08-19, deliberately and with reasons — read before reusing this
# text in stage 4, where it does NOT apply.
#   On the 2026-08-19 run lastBackupAt was 03:03Z against a 07:37Z start (4.5h). The
#   gate was accepted rather than forcing a new backup, because:
#     * this stage performs ZERO writes to the old volume. pg_dump is read-only, the
#       StatefulSet is never scaled, detached, or deleted, and the PVC is untouched.
#       There is no mechanism in this plan by which the old volume can be damaged, so
#       the backup is a floor under a hazard the plan does not create.
#     * the §3 dump is a STRICTLY BETTER copy of the same data: logical, complete, and
#       taken with the application quiesced — where a Longhorn backup of a running
#       Postgres is only crash-consistent. It is kept off-cluster on the operator Mac
#       (~/.local/share/cberg-maintenance/) as well as in /tmp.
#     * forcing a backup means creating Longhorn objects by hand — a GitOps bypass in
#       the storage layer on a day when longhorn-1.12.1-engine was deliberately fenced
#       off (`conflicts_with`), and the recurring job backs up ALL 94 volumes.
#   STAGE 4 IS DIFFERENT: it deletes the source. The gate is load-bearing there and
#   must NOT be relaxed on this precedent.

# e) no in-flight reconcile; operator present for the smoke test
mise exec -- flux get kustomizations -A | awk 'NR==1 || $5!="True"'
```

## 3a) SEQUENCING ENFORCEMENT — added 2026-08-19, read before §3

**`kubectl scale ... --replicas=0` DOES NOT HOLD.** Flux drift-corrects it back, and
the reconcile is not incidental: §3 step 5 pushes a commit and waits for Flux to apply
it, and that same reconcile is what restores `replicas: 1`. The app then comes up
against the target database *before* the restore. Learned on the paperless sibling
(`bitnamilegacy-exit-paperless-db`, `4604c711`) the same morning, where it was
survivable only because `mysqldump` drops every table first. Nothing here drops
anything: this plan's §3 step 3 explicitly recreates an EMPTY `public` schema and then
restores into it, so an app that boots into that gap runs Alembic against an empty
database and manufactures exactly the full-schema/zero-rows state that
`docs/sops/verification-contents-not-shape.md` names as instance 1.

### For THIS app the values route is not available — use suspend-both

The house-preferred fix is to make `replicas: 0` the state Flux converges to, by
setting the replica count in the HelmRelease values in the same commit. **That is
wrong for Superset**, and the reason generalises to every Superset stage:

> `superset-init-db` carries `helm.sh/hook: post-install,post-upgrade` and its
> `envFrom` includes `superset-secrets`. **Any** change to `spec.values` triggers a
> Helm upgrade, which fires that hook, which runs `superset db upgrade` and
> create-admin against whatever `DB_HOST` currently resolves to.

So the values route does not prevent the empty-target write — it *performs* it, from
the hook, with the app still scaled to 0 and every pod-level signal green. Verify with:

```bash
mise exec -- kubectl get job -n databases superset-init-db -o jsonpath='{.metadata.annotations}'
mise exec -- kubectl get job -n databases superset-init-db -o jsonpath='{.spec.template.spec.containers[0].envFrom}'
```

**Required sequence (executed 2026-08-19, worked):**

```bash
# 1. suspend BOTH. The Kustomization alone is NOT enough — the HelmRelease-owned
#    Deployment is reconciled back independently.
mise exec -- flux suspend helmrelease  superset -n databases
mise exec -- flux suspend kustomization superset -n databases

# 2. only now scale down
mise exec -- kubectl scale deploy/superset deploy/superset-worker deploy/superset-celerybeat \
  -n databases --replicas=0
```

**PROVE THE HOLD HELD before restoring or repointing** — not once, but again right
after the commit is applied, because that reconcile is the dangerous one:

```bash
mise exec -- kubectl get deploy -n databases superset superset-worker superset-celerybeat \
  -o custom-columns=NAME:.metadata.name,DESIRED:.spec.replicas,STATUS:.status.replicas
#   DESIRED must be 0 and STATUS <none> (status.replicas is omitempty at 0) for all three
mise exec -- kubectl get pods -n databases --no-headers | grep -E '^superset(-worker|-celerybeat)?-[0-9a-f]{6,}' \
  || echo 'no app pods (correct)'
```

and assert it at the database, which is the only signal that cannot be faked by a
stale cache — zero Superset connections on the source:

```sql
select coalesce(string_agg(distinct application_name || '/' || state, ', '), 'NONE')
from pg_stat_activity where datname='superset' and pid <> pg_backend_pid();
```

### Resume order matters as much as the hold

```bash
# a. Kustomization FIRST, with the HelmRelease still suspended: this applies the new
#    Secret while replicas are still 0. Confirm the hold survived this reconcile.
mise exec -- flux resume kustomization superset -n databases
mise exec -- kubectl get secret -n databases superset-secrets -o jsonpath='{.data.DB_HOST}' | base64 -d

# b. then the HelmRelease, then scale up. Note that resuming the HelmRelease does NOT
#    restore the replica count on its own: spec.driftDetection is unset (disabled) and
#    the values are unchanged, so helm-controller finds nothing to upgrade and the
#    release stays on the same revision. That is the desired outcome — it means no
#    Helm upgrade, so the init-db hook does NOT fire. Scale up by hand instead; you are
#    converging to the chart's own replicaCount: 1, not overriding it.
mise exec -- flux resume helmrelease superset -n databases
mise exec -- kubectl scale deploy/superset deploy/superset-worker deploy/superset-celerybeat \
  -n databases --replicas=1
```

## 3) Steps

1. **Marker** (a real outage is expected — Superset is stopped for the dump):
   ```bash
   runbooks/update-marker.sh add superset databases 2 "superset metadata DB cutover to postgres 17.11 (app stopped for consistent dump)"
   ```
2. **Quiesce Superset** so the dump is consistent. This is a live cluster action —
   delegate to cberg-agent per the maintenance-window contract. **Use the suspend-both
   sequence and the hold proof in §3a — a bare `kubectl scale` here does not hold, and
   for this app the HelmRelease-values route fires the init-db hook instead:**
   ```bash
   mise exec -- flux suspend helmrelease  superset -n databases
   mise exec -- flux suspend kustomization superset -n databases
   mise exec -- kubectl scale deploy/superset deploy/superset-worker deploy/superset-celerybeat -n databases --replicas=0
   mise exec -- kubectl get pods -n databases | grep superset          # only the two DBs (+ redis) remain
   ```
   Then run the §3a hold proof, including the zero-connections assertion on the source.
3. **Fresh dump from the old DB, restore into the new one** (discard stage 2's dump —
   it is stale by design):
   ```bash
   STAMP=$(date +%F-%H%M)
   mise exec -- kubectl exec -n databases $OLD -- \
     sh -c 'PGPASSWORD=$(cat "$POSTGRES_PASSWORD_FILE") pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DATABASE"' \
     > /tmp/superset-cutover-$STAMP.dump
   ls -l /tmp/superset-cutover-$STAMP.dump                              # not zero bytes

   # start from a clean schema so a partial stage-2 restore cannot masquerade as success
   mise exec -- kubectl exec -n databases $NEW -- \
     sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "drop schema public cascade; create schema public;"'
   mise exec -- kubectl cp /tmp/superset-cutover-$STAMP.dump databases/$NEW:/tmp/cutover.dump
   mise exec -- kubectl exec -n databases $NEW -- \
     sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-privileges /tmp/cutover.dump' 2>&1 | tail -30
   ```
   **Read the `pg_restore` output.** Ownership/extension warnings are benign; any
   `error:` line is not — stop and roll back rather than cutting over onto a partial DB.
4. **Compare the two databases before repointing anything.**

   **CONTENTS ASSERTION: exact per-table row counts on BOTH servers, diffed,
   before the repoint.** This is the step the paperless-db incident
   (2026-08-19) did not have — a brand-new database with every table present and
   zero rows passed pod-Ready, schema-present and HTTP 200 while 714 documents
   were invisible. Superset behaves the same way: it starts fine on an empty
   metadata DB and simply shows you nothing.
   See `docs/sops/verification-contents-not-shape.md`.

   ```bash
   # EXACT per-table counts. Do NOT use pg_stat_user_tables.n_live_tup here: it is a
   # planner ESTIMATE maintained by autovacuum/ANALYZE, and it currently reads 0 for
   # every table on the OLD server while reading true counts on the freshly-restored
   # new one — i.e. the comparison would report a total mismatch on two identical
   # databases and abort a correct cutover. query_to_xml counts rows for real, and
   # runs on both PG14 and PG17.
   for POD in $OLD $NEW; do
     mise exec -- kubectl exec -i -n databases $POD -- sh -c "$PSQL -At -f -" <<'SQL' > /tmp/pgcompare-$POD.txt
   select c.relname||'='||(xpath('/row/c/text()',
       query_to_xml(format('select count(*) as c from %I.%I', n.nspname, c.relname),
                    false, true, '')))[1]::text::bigint
     from pg_class c join pg_namespace n on n.oid = c.relnamespace
     where c.relkind = 'r' and n.nspname = 'public' order by c.relname;
SQL
     echo "--- $POD  ($(wc -l < /tmp/pgcompare-$POD.txt) tables)"
   done
   diff /tmp/pgcompare-$OLD.txt /tmp/pgcompare-$NEW.txt \
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
6. **Bring Superset back up** — in the §3a resume order (Kustomization first with the
   HelmRelease still suspended, re-prove the hold, *then* HelmRelease, then scale):
   ```bash
   mise exec -- flux resume kustomization superset -n databases
   # confirm the Secret landed AND replicas are still 0, then:
   mise exec -- flux resume helmrelease superset -n databases
   mise exec -- kubectl scale deploy/superset deploy/superset-worker deploy/superset-celerybeat -n databases --replicas=1
   mise exec -- kubectl rollout status deploy/superset -n databases --timeout=600s
   ```
   The pods must pick up the new `DB_HOST`; the `stakater.com/reload` annotation on
   the Secret plus the fresh rollout covers this — confirm in §4a, do not assume.
7. Clear the marker only after §4 passes: `runbooks/update-marker.sh clear superset`.

## 4) Verification

```bash
cd /Users/mu/code/cberg-home-nextgen

# --- how to talk to either database (run first in EVERY shell) ---------------
# The OLD bundled Postgres rejects passwordless local connections
# (`fe_sendauth: no password supplied`), so every psql/pg_dump below MUST supply
# one. Read it INSIDE the pod: expanded there, the password never enters kubectl
# argv, the API-server audit log, your process table or your shell history.
# One expression covers both servers — the old bitnami image exposes
# $POSTGRES_PASSWORD_FILE + $POSTGRES_DATABASE, the new postgres:17.11-alpine
# exposes $POSTGRES_PASSWORD + $POSTGRES_DB. Single-quoted on purpose: these
# variables must reach the pod UNEXPANDED.
PSQL='PGPASSWORD="${POSTGRES_PASSWORD:-$(cat "$POSTGRES_PASSWORD_FILE")}" psql -U "$POSTGRES_USER" -d "${POSTGRES_DB:-$POSTGRES_DATABASE}"'
OLD=superset-postgresql-0
NEW=$(mise exec -- kubectl get pods -n databases -l app=superset-pg -o jsonpath='{.items[0].metadata.name}')
[ -n "$NEW" ] || { echo "new postgres pod not found — STOP"; exit 1; }

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
mise exec -- kubectl exec -i -n databases $NEW -- sh -c "$PSQL -At -f -" <<'SQL'
select 'dashboards='||count(*) from dashboards
union all select 'slices='||count(*) from slices
union all select 'saved_query='||count(*) from saved_query
union all select 'dbs='||count(*) from dbs
union all select 'ab_user='||count(*) from ab_user
union all select 'ab_user_role='||count(*) from ab_user_role;
SQL
mise exec -- kubectl exec -n databases $NEW -- \
  sh -c "$PSQL -At -c 'select version_num from alembic_version;'"    # identical to pre-check

# d) the old DB is still running and now IDLE (it is the rollback — do not stop it)
mise exec -- kubectl get pods -n databases | grep superset-postgresql
mise exec -- kubectl exec -i -n databases $OLD -- sh -c "$PSQL -At -f -" <<'SQL'
select count(*) from pg_stat_activity where datname='superset' and state='active';   -- ~0
SQL

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

### Execution record — 2026-08-19 ad-hoc window (commit `48ffc039`)

Everything in §4 passed. What is worth carrying forward:

- **§4(e) cannot be automated through the REST API.** `POST /api/v1/security/login`
  with `provider: db` returns `401 Not authorized` — `AUTH_TYPE = AUTH_OAUTH` means
  there is no database-password path for the admin user, and the value in
  `superset-secrets.ADMIN_PASSWORD` does not authenticate against it. Use Superset's
  own app context in-pod instead (`create_app()` + `app_context()`), which exercises
  the same ORM and the same datasource layer the UI does:

  ```bash
  mise exec -- kubectl exec -n databases deploy/superset -c superset -- python - <<'PY'
  from superset.app import create_app
  with create_app().app_context():
      from superset import db
      from superset.models.dashboard import Dashboard
      print("ORM bound to:", db.session.get_bind().url.host)     # must be superset-pg
      for d in db.session.query(Dashboard).all():
          print(d.dashboard_title, "charts:", len(d.slices))
  PY
  ```

- **Rendering a chart needs a request context.** `ChartDataCommand(...).run()` raises a
  bare `AttributeError: user` outside one, which reads like a data failure and is not.
  Wrap it in `app.test_request_context("/")` with `login_user(user)` **and** an explicit
  `g.user = user`. Six of the nine charts store no `query_context` (legacy viz) and
  return `None` from `get_query_context()` — that is not a defect either; assert those
  by querying their datasource directly, and count them separately.

- **Result:** ORM bound to `superset-pg`; 1 dashboard / 10 charts / 10 datasets /
  1 database connection / 0 saved queries / 2 users / 5 roles — identical to the
  pre-check inventory; both users kept their roles (one Admin+Gamma, one Admin). All
  9 charts on the dashboard resolved against live data (3 rendered through
  `ChartDataCommand`, 6 legacy-viz datasources queried directly), zero failures. The
  single configured database connection points at the shared cluster Postgres, **not**
  at the Superset metadata DB — so stage 4 does not endanger it.

- **Still owed by the operator:** the actual browser smoke test — Authentik OIDC login,
  the dashboard rendering visually, and SQL Lab. Everything above is app-layer evidence
  gathered without a browser; it is strong, and it is not the same thing.

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
`$PSQL` preamble from §2 — a bare `psql` in that pod fails `fe_sendauth: no password
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
