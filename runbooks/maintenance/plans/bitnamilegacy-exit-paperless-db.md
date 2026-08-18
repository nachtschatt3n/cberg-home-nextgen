---
plan_id: bitnamilegacy-exit-paperless-db
component: paperless-ngx
pr: null                               # archived registry — no upstream tag can fix it
kind: chart                            # HelmRelease values + new sibling manifests + storage
current: "bundled bitnamilegacy/mariadb:latest (server 11.8.2-MariaDB) on PVC paperless-mariadb"
target: "mariadb:11.8.8 (Docker Official Image) as deployment/paperless-db on a NEW volume paperless-db-data"
update_type: major                     # datastore replacement (image lineage + datadir + uid)
risk: high                             # DB engine swap on a deny-listed component; document library
est_duration_min: 70
needs_reboot: false
touches:
  namespaces: [office]
  resources:
    - helmrelease/paperless-ngx                 # mariadb.enabled:false + explicit DB env
    - "new: deployment/paperless-db + service/paperless-db"
    - "new: pvc/paperless-db-data + pv/paperless-db-data + longhorn volume paperless-db-data (manual apply)"
    - secret/paperless-ngx-secret               # SOPS edit — gains mariadb-password + root password
    - statefulset/paperless-ngx-mariadb         # REMOVED by the chart
    - secret/paperless-ngx-mariadb              # chart-generated — DELETED with the subchart
    - deployment/paperless-ngx                  # full restart onto the new DB
    - pvc/paperless-mariadb                     # orphaned, Retain — the rollback data
  shared: [storage]                             # allocates a new 2-replica Longhorn volume
depends_on: [paperless-ngx-3.0.5]  # RESOLVED 2026-08-18: bitnamilegacy-exit-paperless-redis EXECUTED 2026-08-18 (2dcbfad2) — dependency satisfied
conflicts_with: [longhorn-1.12.1-engine, paperless-ngx-3.0.5, bitnamilegacy-exit-nextcloud-db, ]  # RESOLVED 2026-08-18: bitnamilegacy-exit-paperless-redis EXECUTED 2026-08-18 — dead ref removed
security_ref: F-cb42f390                        # see also F-90dd1a52 (same image, fixable class)
status: draft
window: "sun-window:2026-09-06"                 # RESHUFFLED 2026-08-16 onto the daily-window cadence
                                      # (7 windows/week, was 4). Deliberate soaks are
                                      # preserved, not compressed — see the windows YAML.
                                                # which requires a SOLO window. 09-26/10-03/10-10
                                                # have <70m free. See §6 — this date is the weakest
                                                # part of the plan and the operator should challenge it.
auto_execute: false                             # *mariadb* is on the auto-update deny-list
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/mariadb-major-upgrade.md
  - docs/sops/backup.md
  - docs/sops/storage-safety.md
  - docs/sops/longhorn.md
  - docs/sops/paperless.md
  - docs/sops/sops-encryption.md
generated: "2026-08-15"
---

# bitnamilegacy exit, phase 3/5 — paperless-ngx off the bundled Bitnami MariaDB

## 1) Summary & why held

Phase 3 of 5. Paperless is deliberately done **before** Nextcloud: same chart
pattern, same target image, one tenth the data (222 MB vs 1.2 GB), 72 tables vs
206, and a far smaller consumer set. It is the rehearsal for phase 4.

**Why this is held and can never be auto-applied.** `*mariadb*` carries a deny
rule in `runbooks/auto-update-policy.yaml`:

> "A DB-engine bump is never unattended-safe. The bitnami entrypoint can SKIP
> `mariadb-upgrade` on a server-major roll while reporting Ready and the right
> `SELECT VERSION()` — leaving old-format system tables under the new binary."

**Why no version bump can fix this.** The HelmRelease pins
`docker.io/bitnamilegacy/mariadb:latest`. `bitnamilegacy` is Bitnami's
**archived** catalog: the free images were moved there on 2025-08-28 and nothing
has been published since; it exists "solely to help with migration" and receives
no updates or patches, ever. `latest` on an archived registry is a frozen tag
pretending to be a rolling one — the pod runs **11.8.2-MariaDB** and always will.
`docker.io/bitnami/mariadb` is not a fallback: it publishes no semver stream, only
digests, which is why `databases/mariadb` had to be digest-pinned (see
`docs/sops/mariadb-major-upgrade.md` §Security Check — a pin no tooling can
surface drift on). The only remediation is to leave the registry.

> **Security driver — detail withheld from this public repo.**
> Tracked as **F-cb42f390** and **F-90dd1a52** (both `bitnamilegacy/mariadb:latest`).
> Counts, CVE identifiers and exposure live on the finding records — they are
> deliberately not reproduced here.
>
> - Dashboard: `https://sweep.<DOMAIN>/findings/F-cb42f390`
> - CLI: `runbooks/policy-cli.py finding show F-cb42f390`
>
> See `docs/sops/vulnerability-disclosure.md` before adding any vulnerability
> detail to a committed file.

### What actually changes, and what deliberately does not

| | now | after |
|---|---|---|
| image | `bitnamilegacy/mariadb:latest` | `mariadb:11.8.8` (Docker Official Image) |
| **server version** | **11.8.2** | **11.8.8 — same LTS series** |
| datadir | `/bitnami/mariadb/data` | `/var/lib/mysql` |
| runtime uid | 1001 (bitnami) | 999 (mysql) |
| volume | `paperless-mariadb` (kept, untouched) | `paperless-db-data` (new) |
| server charset | `utf8mb3` / `utf8mb3_general_ci` | **pinned to the same** |
| workload kind | StatefulSet (subchart) | Deployment (ours) |

**This is not a MariaDB major upgrade** — 11.8.2 → 11.8.8 is a patch move inside
the 11.8 LTS series. The risk here is the *replatform* (different datadir layout,
different uid, logical dump/restore), not a system-table format transition. That
is exactly why paperless goes first and why the target is 11.8.8 rather than 12.x
or 13.x: **change one thing.** A later 11.8 → 12/13 major, on the official image
with a real semver stream, is a separate plan that then follows
`docs/sops/mariadb-major-upgrade.md` end to end.

### The verification trap that must not be skipped

Even though a fresh `initdb` at 11.8.8 should write its own datadir marker,
`docs/sops/mariadb-major-upgrade.md` documents that **every signal an operator
normally trusts can lie**: `Ready=True`, a correct `SELECT VERSION()`, and a
running pod are all compatible with old-format system tables underneath. So
Verification below checks the **datadir marker** (`/var/lib/mysql/mysql_upgrade_info`)
and runs `mariadb-check --all-databases`, not just `SELECT VERSION()`. And if a
manual upgrade is ever needed, it must go over the socket
(`mariadb-upgrade --protocol=socket --skip-ssl`) — the SOP records that the
default TLS/TCP loopback resets mid-run, half-applies the privilege migration and
emits hundreds of misleading `server has gone away` errors.

### The charset trap

Read on the live cluster 2026-08-15:

```
@@character_set_server = utf8mb3      @@collation_server = utf8mb3_general_ci
schema `paperless`     = utf8mb3 / utf8mb3_general_ci     (72 tables)
@@innodb_file_per_table = 1           @@log_bin = 0
```

MariaDB **11.5+ changed the default server collation**, and the official 11.8
image will initialise a fresh datadir as `utf8mb4` with a `uca1400` collation. If
the new server is not pinned, the entrypoint creates the `paperless` database as
utf8mb4 while the dump's table DDL restores tables as utf8mb3 — a silently mixed
schema, with Django join/collation surprises to find later. The new Deployment
therefore pins `--character-set-server=utf8mb3 --collation-server=utf8mb3_general_ci`
so this window changes the **image and nothing else**. Converting paperless to
utf8mb4 is a real improvement and a **separate** plan (index-prefix lengths change).

### Two chart traps (same shape as phase 2a)

1. **`paperless-ngx-mariadb` is a chart-GENERATED Secret.** `mariadb.enabled:
   false` deletes it, taking `mariadb-password` and `mariadb-root-password` with
   it. Both must be carried into our own SOPS secret in the same commit.
2. **Disabling the subchart removes the chart-templated DB env.** In chart 0.24.1
   `templates/common.yaml`, `PAPERLESS_DBENGINE` / `DBHOST` / `DBNAME` / `DBUSER` /
   `DBPASS` are emitted only inside `{{- else if .Values.mariadb.enabled }}`. All
   five must be declared explicitly in our `env:` block.

## 2) Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) the two PREREQUISITE plans have landed
mise exec -- kubectl get deploy -n office paperless-redis \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'      # redis:8.10.0-alpine (phase 2a)
mise exec -- kubectl get deploy -n office paperless-ngx \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'      # 3.0.5 — paperless-ngx-3.0.5 ran first
# If paperless is still on 2.20.15 the 3.0.5 plan has not run. Running this plan
# first is NOT fatal, but see §6: it makes the rollback volume a pre-v3 snapshot
# for a week. Prefer to defer.

# b) current state of the source DB
mise exec -- kubectl get sts -n office paperless-ngx-mariadb \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'   # bitnamilegacy/mariadb:latest
mise exec -- kubectl exec -n office paperless-ngx-mariadb-0 -c mariadb -- mariadb --version

# c) RECORD THE BASELINE — this is what Verification compares against.
#    Per docs/sops/mariadb-major-upgrade.md step 1: risk follows the data.
mise exec -- kubectl exec -n office paperless-ngx-mariadb-0 -c mariadb -- sh -c \
  'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" -N -e "
     select @@version, @@character_set_server, @@collation_server, @@innodb_file_per_table, @@log_bin;
     select table_schema, count(*) from information_schema.tables group by 1;
     select schema_name, default_character_set_name, default_collation_name from information_schema.schemata;
     select count(*) from mysql.user;"' | tee /tmp/paperless-db-baseline.txt
mise exec -- kubectl exec -n office paperless-ngx-mariadb-0 -c mariadb -- sh -c \
  'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" -N -e "
     select table_name, table_rows, table_collation from information_schema.tables
     where table_schema=\"paperless\" order by table_name;"' | tee /tmp/paperless-db-tables-before.txt
wc -l /tmp/paperless-db-tables-before.txt        # expect 72 rows
mise exec -- kubectl exec -n office paperless-ngx-mariadb-0 -c mariadb -- df -h /bitnami/mariadb

# d) application-level baseline (a DB that starts but that the app cannot use is
#    the failure worth catching — SOP §Verification Tests)
mise exec -- kubectl exec -n office deploy/paperless-ngx -- \
  python3 manage.py shell -c "
from documents.models import Document, Correspondent, Tag, DocumentType
print('documents', Document.objects.count())
print('correspondents', Correspondent.objects.count())
print('tags', Tag.objects.count())
print('types', DocumentType.objects.count())" | tee /tmp/paperless-app-baseline.txt
mise exec -- kubectl exec -n office deploy/paperless-ngx -- python3 manage.py showmigrations --list | tail -20

# e) DRAIN the pipeline — no scan may be mid-consume when the DB goes away
mise exec -- kubectl exec -n office deploy/paperless-ngx -- ls -la /usr/src/paperless/consume/ | tail
mise exec -- kubectl exec -n office deploy/paperless-ngx -- ls -la /usr/src/paperless/inbox/ 2>/dev/null | tail
mise exec -- kubectl logs -n office deploy/paperless-ngx --since=15m | grep -iE 'consum|task' | tail
# Pause the scanner path if scans are arriving (docs/sops/paperless.md):
#   mise exec -- kubectl scale deploy/scan-inbox-validator -n office --replicas=0

# f) Longhorn backup of the source volume — the disaster floor. The logical dump
#    in step 2 is the WORKING rollback; this is the layer beneath it.
#    The storage/backup-of-all-volumes CronJob runs nightly at 03:00, so in a
#    05:00/09:00 window there is normally already a backup a few hours old:
mise exec -- kubectl get volume -n storage paperless-mariadb \
  -o custom-columns=NAME:.metadata.name,STATE:.status.state,ROBUST:.status.robustness,LASTBACKUP:.status.lastBackupAt
# If lastBackupAt is NOT within the last 24h, trigger one and WAIT — but budget
# for it, a full-cluster backup run can take a long time
# (docs/sops/backup.md §Pre-Upgrade Backup Procedure):
#   mise exec -- kubectl create job --from=cronjob/backup-of-all-volumes \
#     pre-paperless-db-$(date +%Y%m%d) -n storage
#   mise exec -- kubectl wait --for=condition=complete job/pre-paperless-db-$(date +%Y%m%d) \
#     -n storage --timeout=3600s

# g) the old volume is Retain (rollback depends on it) and there is room for a new one
mise exec -- kubectl get pv paperless-mariadb \
  -o custom-columns=NAME:.metadata.name,RECLAIM:.spec.persistentVolumeReclaimPolicy,SC:.spec.storageClassName
# MUST read Retain / longhorn-static. If not, STOP — docs/sops/storage-safety.md.
mise exec -- kubectl get nodes.longhorn.io -n storage \
  -o custom-columns=NAME:.metadata.name,READY:.status.conditions[?\(@.type==\"Ready\"\)].status

# h) the target tag exists
curl -s "https://hub.docker.com/v2/repositories/library/mariadb/tags?page_size=100&ordering=last_updated&name=11.8" \
  | python3 -c "import sys,json;print([t['name'] for t in json.load(sys.stdin)['results']][:12])"   # 11.8.8 present

# i) capture the DB credentials for the SOPS carry-over (do not persist them)
mise exec -- kubectl get secret -n office paperless-ngx-mariadb \
  -o jsonpath='{.data.mariadb-password}' | base64 -d | pbcopy   # paste into sops in step 4

# j) no in-flight reconcile
mise exec -- flux get kustomizations -A | awk 'NR==1 || $5!="True"'
```

## 3) Steps

1. **Marker + silence.** Paperless is fully down for the cutover:
   ```bash
   runbooks/update-marker.sh add paperless-ngx office 3 "mariadb: bitnamilegacy 11.8.2 -> official mariadb:11.8.8"
   ```
   Silence `namespace=office` rollout alerts for 4h per
   `docs/sops/application-update.md` §4 Step 1.

2. **Quiesce the app, THEN dump.** Scale paperless to 0 first so the dump is of a
   database nothing is writing to:
   ```bash
   mise exec -- kubectl scale deploy/paperless-ngx -n office --replicas=0
   mise exec -- kubectl scale deploy/scan-inbox-validator -n office --replicas=0
   mise exec -- kubectl wait --for=delete pod -n office -l app.kubernetes.io/name=paperless-ngx --timeout=180s
   ```
   Take the logical dump — per `docs/sops/mariadb-major-upgrade.md` step 2 this is
   **the only rollback that works**, and it must be protected:
   ```bash
   umask 077 && mkdir -p ~/db-dumps && chmod 700 ~/db-dumps
   D=~/db-dumps/paperless-$(date +%F).sql
   mise exec -- kubectl exec -n office paperless-ngx-mariadb-0 -c mariadb -- sh -c \
     'mariadb-dump -uroot -p"$MARIADB_ROOT_PASSWORD" \
        --single-transaction --routines --triggers --events \
        --databases paperless' > "$D"
   chmod 600 "$D"
   ls -l "$D"                       # must NOT be zero bytes
   tail -1 "$D"                     # must read "-- Dump completed"
   grep -c 'CREATE TABLE' "$D"      # expect 72
   grep -m1 'CREATE DATABASE' "$D"  # must carry utf8mb3 / utf8mb3_general_ci
   ```
   The dump contains password hashes only if you dump `mysql` — we deliberately
   dump **only the `paperless` schema**; the new server's entrypoint creates the
   user from `MARIADB_USER`/`MARIADB_PASSWORD`. Keep the file `0600` in a `0700`
   directory and **do not commit it**.

3. **Carry the credentials into our own SOPS secret** — edit in place
   (`docs/sops/sops-encryption.md`; never decrypt to `/tmp` and re-encrypt from
   there):
   ```bash
   sops kubernetes/apps/office/paperless-ngx/app/secret.sops.yaml
   #   add:  mariadb-password:      <value from pre-check (i)>
   #   add:  mariadb-root-password: <generate a NEW strong password — the old root
   #                                 password belongs to a server we are retiring>
   #   keep: PAPERLESS_KEY, PAPERLESS_EMAIL_*, PAPERLESS_TOKEN, redis-password
   ```
   Reuse the **app** password unchanged (so the client needs no coordinated
   change); generate a fresh **root** password (nothing depends on the old one).

4. **Add the storage manifests**, following `docs/sops/longhorn.md`: a
   `longhorn-static` volume with a **speaking name** used identically in the
   Longhorn `Volume` CR, the `PV` name, the PV `volumeHandle`, the PVC name and
   the PVC's `volumeName` — `paperless-db-data`. Model them on the existing
   `nextcloud`/`superset` static-volume files. Size 5Gi, `numberOfReplicas: 2`,
   `persistentVolumeReclaimPolicy: Retain`, `storageClassName: longhorn-static`.
   New files:
   `kubernetes/apps/office/paperless-ngx/app/db-pv.yaml`,
   `db-pvc.yaml`, `db-longhorn-volume.yaml`.

   The Longhorn `Volume` CR must be applied **by hand** and must **not** be in
   `kustomization.yaml` — the app Kustomization's `targetNamespace: office` would
   override its `namespace: storage` and create a broken duplicate Longhorn
   ignores (`CLAUDE.md` §Longhorn, `docs/sops/longhorn.md`):
   ```bash
   mise exec -- kubectl apply -f kubernetes/apps/office/paperless-ngx/app/db-longhorn-volume.yaml
   mise exec -- kubectl get volume -n storage paperless-db-data
   ```

5. **Add the MariaDB manifests** in
   `kubernetes/apps/office/paperless-ngx/app/db-deployment.yaml` — Deployment +
   Service `paperless-db`, modelled on
   `kubernetes/apps/databases/postgresql/app/deployment.yaml`:
   - image `mariadb:11.8.8`, `strategy: Recreate`, `replicas: 1`
   - env from `paperless-ngx-secret`:
     `MARIADB_ROOT_PASSWORD` ← `mariadb-root-password`,
     `MARIADB_PASSWORD` ← `mariadb-password`;
     plain: `MARIADB_DATABASE: paperless`, `MARIADB_USER: paperless`
   - **charset pin — do not omit:**
     ```yaml
     args:
       - --character-set-server=utf8mb3
       - --collation-server=utf8mb3_general_ci
       - --innodb-file-per-table=1
     ```
   - PVC `paperless-db-data` mounted at `/var/lib/mysql`
   - liveness/readiness `healthcheck.sh --connect --innodb_initialized`
     (shipped in the official image) with `initialDelaySeconds: 30`
   - resources: requests 100m/256Mi, limits 500m/1Gi (matches the subchart)
   - Service `paperless-db`, port 3306, ClusterIP
   Register `db-pv.yaml`, `db-pvc.yaml`, `db-deployment.yaml` in
   `kustomization.yaml` (**not** the Longhorn Volume CR).

6. **Edit `kubernetes/apps/office/paperless-ngx/app/helmrelease.yaml`**:
   - Replace the whole `mariadb:` values block (around line 164) with:
     ```yaml
         # Bundled Bitnami mariadb retired 2026-XX-XX: bitnamilegacy is an
         # ARCHIVED registry (last push 2025-08-28, no future security fixes) and
         # docker.io/bitnami/mariadb publishes no semver tags (digest-only).
         # Security driver tracked as F-cb42f390. Paperless now uses the official
         # mariadb image deployed by db-deployment.yaml in this folder.
         # Server charset is PINNED to utf8mb3/utf8mb3_general_ci to match the
         # retired server — see the plan; utf8mb4 is a separate migration.
         mariadb:
           enabled: false
     ```
   - Add to the `env:` block (the chart only templates these when
     `mariadb.enabled` is true — chart 0.24.1 `templates/common.yaml`):
     ```yaml
           PAPERLESS_DBENGINE: mariadb
           PAPERLESS_DBHOST: paperless-db
           PAPERLESS_DBPORT: 3306
           PAPERLESS_DBNAME: paperless
           PAPERLESS_DBUSER: paperless
           PAPERLESS_DBPASS:
             valueFrom:
               secretKeyRef:
                 name: paperless-ngx-secret
                 key: mariadb-password
     ```
     (`PAPERLESS_DBENGINE` being explicit is also what paperless-ngx v3 requires —
     see Interference notes.)
   - Update the `wait-for-mariadb` initContainer to `until nc -z paperless-db 3306; do`
     and fix its echo string.

7. **Validate, commit, push** (on `main`, stage only the files you touched):
   ```bash
   mise exec -- kubeconform -summary -exit-on-error -ignore-missing-schemas \
     kubernetes/apps/office/paperless-ngx
   git add kubernetes/apps/office/paperless-ngx/app/db-deployment.yaml \
           kubernetes/apps/office/paperless-ngx/app/db-pv.yaml \
           kubernetes/apps/office/paperless-ngx/app/db-pvc.yaml \
           kubernetes/apps/office/paperless-ngx/app/db-longhorn-volume.yaml \
           kubernetes/apps/office/paperless-ngx/app/kustomization.yaml \
           kubernetes/apps/office/paperless-ngx/app/secret.sops.yaml \
           kubernetes/apps/office/paperless-ngx/app/helmrelease.yaml
   git commit -m "feat(paperless-ngx): replatform mariadb from archived bitnamilegacy to official mariadb:11.8.8"
   git push
   ```
   Flux reconciles: the new MariaDB initialises an empty datadir, the bundled
   StatefulSet is removed, paperless comes back up pointing at an **empty**
   database and will report errors until step 8. That is expected.

8. **Restore into the new server**, with paperless scaled to 0 so nothing races
   the restore:
   ```bash
   mise exec -- kubectl scale deploy/paperless-ngx -n office --replicas=0
   mise exec -- kubectl rollout status deploy/paperless-db -n office --timeout=600s
   NEW=$(mise exec -- kubectl get pods -n office -l app=paperless-db -o jsonpath='{.items[0].metadata.name}')
   mise exec -- kubectl cp "$D" office/$NEW:/tmp/restore.sql
   mise exec -- kubectl exec -n office $NEW -- sh -c \
     'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" < /tmp/restore.sql' 2>&1 | tail -30
   # Read every warning. Grant/definer warnings are benign; ERROR lines are not.
   mise exec -- kubectl exec -n office $NEW -- rm -f /tmp/restore.sql
   mise exec -- kubectl scale deploy/paperless-ngx -n office --replicas=1
   mise exec -- kubectl scale deploy/scan-inbox-validator -n office --replicas=1
   ```

9. Clear the marker and drop the silence on success:
   `runbooks/update-marker.sh clear paperless-ngx`.

## 4) Verification

```bash
cd /Users/mu/code/cberg-home-nextgen
DOM=$(mise exec -- kubectl get secret -n flux-system cluster-secrets -o jsonpath='{.data.SECRET_DOMAIN}' | base64 -d)
NEW=$(mise exec -- kubectl get pods -n office -l app=paperless-db -o jsonpath='{.items[0].metadata.name}')

# a) the release reconciled and the old objects are gone
mise exec -- kubectl get hr -n office paperless-ngx \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.lastAppliedRevision}{"\n"}'
mise exec -- kubectl get sts -n office | grep -i paperless || echo "bundled mariadb StatefulSet gone (expected)"
mise exec -- kubectl get secret -n office paperless-ngx-mariadb 2>&1 | grep -q NotFound \
  && echo "chart-generated mariadb secret gone (expected)"
mise exec -- kubectl get deploy -n office paperless-db \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'      # mariadb:11.8.8
mise exec -- kubectl get pvc -n office paperless-db-data             # Bound
mise exec -- kubectl get volume -n storage paperless-db-data \
  -o custom-columns=NAME:.metadata.name,STATE:.status.state,ROBUST:.status.robustness

# b) *** THE MARIADB TRAP — version alone is NOT sufficient ***
#    docs/sops/mariadb-major-upgrade.md: Ready=True + a correct SELECT VERSION()
#    are both compatible with old-format system tables. Check the DATADIR MARKER.
mise exec -- kubectl exec -n office $NEW -- sh -c 'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" -N -e "select version();"'
mise exec -- kubectl exec -n office $NEW -- cat /var/lib/mysql/mysql_upgrade_info
#    ^ MUST show 11.8.8. If it lags, run the upgrade BY HAND OVER THE SOCKET —
#      the default TLS/TCP loopback resets mid-run and half-applies the privilege
#      migration (two runs failing at DIFFERENT lines is the tell):
#        mise exec -- kubectl exec -n office $NEW -- sh -c \
#          'mariadb-upgrade --protocol=socket --skip-ssl -uroot -p"$MARIADB_ROOT_PASSWORD"'
#      Expect all 8 phases to complete.
mise exec -- kubectl exec -n office $NEW -- sh -c \
  'mariadb-check --protocol=socket --all-databases -uroot -p"$MARIADB_ROOT_PASSWORD"' | grep -v ' OK$' | head
#    ^ every table must be OK; the grep should print (almost) nothing.

# c) charset did NOT drift (the second trap)
mise exec -- kubectl exec -n office $NEW -- sh -c 'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" -N -e "
  select @@version, @@character_set_server, @@collation_server, @@innodb_file_per_table;
  select schema_name, default_character_set_name, default_collation_name
    from information_schema.schemata where schema_name=\"paperless\";"'
# MUST read utf8mb3 / utf8mb3_general_ci — compare to /tmp/paperless-db-baseline.txt.
# utf8mb4/uca1400 here means the args pin was dropped: the restore is schema-mixed.

# d) THE load-bearing check — the restore is COMPLETE, not merely "successful".
#    A restore into an empty schema looks identical to a good one at pod level.
mise exec -- kubectl exec -n office $NEW -- sh -c 'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" -N -e "
  select table_name, table_rows, table_collation from information_schema.tables
  where table_schema=\"paperless\" order by table_name;"' > /tmp/paperless-db-tables-after.txt
diff /tmp/paperless-db-tables-before.txt /tmp/paperless-db-tables-after.txt
# `table_rows` is an InnoDB ESTIMATE and will differ slightly — the TABLE LIST and
# the COLLATIONS must match exactly. 72 tables before, 72 after.
mise exec -- kubectl exec -n office $NEW -- sh -c 'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" -N -e "
  select count(*) from paperless.django_migrations;"'    # non-zero

# e) the APPLICATION can use it — "a database that starts but that its app cannot
#    use is the failure worth catching" (SOP §Verification Tests)
mise exec -- kubectl rollout status deploy/paperless-ngx -n office --timeout=600s
mise exec -- kubectl exec -n office deploy/paperless-ngx -- \
  python3 manage.py shell -c "
from documents.models import Document, Correspondent, Tag, DocumentType
print('documents', Document.objects.count())
print('correspondents', Correspondent.objects.count())
print('tags', Tag.objects.count())
print('types', DocumentType.objects.count())" > /tmp/paperless-app-after.txt
diff /tmp/paperless-app-baseline.txt /tmp/paperless-app-after.txt \
  && echo "counts match baseline (expected)"      # ANY diff here = incomplete restore
mise exec -- kubectl exec -n office deploy/paperless-ngx -- python3 manage.py showmigrations --list | grep '\[ \]' \
  && echo "UNAPPLIED MIGRATIONS — investigate" || echo "all migrations applied (expected)"
curl -s -o /dev/null -w 'paperless %{http_code}\n' --max-time 20 "https://paperless.$DOM/"

# f) operator smoke test — end to end, the part that fails silently:
#    1. Log in via the UI, open a document, confirm its content + thumbnail render.
#    2. Search for a known term (the DB-backed index path).
#    3. Drop a test PDF into the consume share; confirm it is consumed, OCR'd,
#       and appears in the library. Then delete the test document.
#    4. Confirm paperless-ai and paperless-gpt reconnect:
mise exec -- kubectl logs -n office deploy/paperless-ai  --since=15m | tail -10
mise exec -- kubectl logs -n office deploy/paperless-gpt --since=15m | tail -10

# g) the old volume is untouched and still the rollback
mise exec -- kubectl get pv paperless-mariadb \
  -o custom-columns=NAME:.metadata.name,STATUS:.status.phase,RECLAIM:.spec.persistentVolumeReclaimPolicy
mise exec -- kubectl get volume -n storage paperless-mariadb \
  -o custom-columns=NAME:.metadata.name,STATE:.status.state,LASTBACKUP:.status.lastBackupAt

# h) no fixable criticals introduced by the new image
mise exec -- trivy image mariadb:11.8.8 --severity CRITICAL --ignore-unfixed | tail -20
```

Success = HR Ready; no `bitnamilegacy/mariadb` in `office`; `paperless-db` Ready
on `mariadb:11.8.8` with the datadir marker reading **11.8.8** and
`mariadb-check` all-OK; server + schema charset still `utf8mb3_general_ci`; the
72-table list and collations identical to the baseline; document/correspondent/
tag/type counts identical to the baseline; no unapplied migrations; a test
document consumed end-to-end; `paperless-mariadb` volume untouched and Retain.

## 5) Rollback

**There is no in-place downgrade of a MariaDB datadir** — but this plan never
upgraded one. The old server's volume was never opened by the new binary, so
rollback is a revert plus a re-bind, and the logical dump is the belt to that
braces.

```bash
cd /Users/mu/code/cberg-home-nextgen
mise exec -- kubectl scale deploy/paperless-ngx -n office --replicas=0

git revert --no-edit <paperless-db-commit-sha>   # restores mariadb.enabled:true + the chart env + the secret hunk
git push

# the bundled StatefulSet comes back and re-binds the UNTOUCHED paperless-mariadb PVC
mise exec -- kubectl rollout status sts/paperless-ngx-mariadb -n office --timeout=600s
mise exec -- kubectl exec -n office paperless-ngx-mariadb-0 -c mariadb -- sh -c \
  'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" -N -e "
     select version(); select count(*) from information_schema.tables where table_schema=\"paperless\";"'
# expect 11.8.2 and 72 — byte-identical to the baseline, because nothing wrote to it.
mise exec -- kubectl scale deploy/paperless-ngx -n office --replicas=1
mise exec -- kubectl rollout status deploy/paperless-ngx -n office --timeout=600s
DOM=$(mise exec -- kubectl get secret -n flux-system cluster-secrets -o jsonpath='{.data.SECRET_DOMAIN}' | base64 -d)
curl -s -o /dev/null -w 'paperless %{http_code}\n' --max-time 20 "https://paperless.$DOM/"
mise exec -- kubectl exec -n office deploy/paperless-ngx -- \
  python3 manage.py shell -c "from documents.models import Document; print(Document.objects.count())"
```

The revert also reverts the SOPS secret hunk and the `env:` block, so client and
server move back together — **do not revert the HelmRelease without the secret**.

**If `paperless-mariadb` is somehow damaged**, restore in this order:
1. the logical dump from step 2 (`~/db-dumps/paperless-<date>.sql`) into a fresh
   datadir — per `docs/sops/mariadb-major-upgrade.md` §Rollback Plan, "scale to 0,
   restore the pre-upgrade dump into a fresh datadir on the previous image, scale
   up";
2. failing that, the Longhorn backup taken in pre-check (f), per
   `docs/sops/backup.md` §"Restore from Backup" → §"Bind Restored Volume to
   Application".

**Storage safety:** `paperless-mariadb` and `paperless-db-data` are
`longhorn-static` with `reclaimPolicy: Retain` — neither is a CIFS/SMB class, so
a PVC delete cannot reach a share (`docs/sops/storage-safety.md`). Run the
pre-flight one-liner anyway before any PVC deletion. The Longhorn `Volume` CR for
`paperless-db-data` was applied by hand, so Flux will not remove it on revert;
delete it deliberately only if abandoning:
```bash
# ONLY if abandoning — this volume holds a RESTORED COPY, never the live data:
# mise exec -- kubectl delete volume -n storage paperless-db-data
```

**Do not delete `paperless-mariadb` in this window.** It is the rollback. Retire
it in a later cleanup after a full week clean.

Confirmed back = bundled StatefulSet Running on 11.8.2 with 72 tables, paperless
200 with the baseline document count.

## 6) Interference notes

- **Window choice: `sat-early:2026-10-17`, and the operator should challenge it.**
  This needs a 90-minute no-reboot slot, and `sat-early` is the only one
  (`runbooks/maintenance-windows.yaml` reserves `sun-window` for reboot work and
  explicitly says to push `needs_reboot:false` mariadb/nextcloud plans to
  Tue/Thu/Sat). Every earlier `sat-early` is taken: 08-22 kube-prometheus-stack,
  08-29 app-template-5.0, 09-05 longhorn engine, 09-12 superset-pg-cutover,
  **09-19 paperless-ngx-3.0.5 (solo)**, 09-26 grafana-13-app, 10-03/10-10 the
  media plans — none with 70 free minutes. If two months on an archived registry
  is unacceptable, the cheapest fix is to re-slot a *draft* plan (`grafana-13-app`
  09-26, `media-naming-p3` 10-10) rather than to compress this one.
- **`conflicts_with: longhorn-1.12.1-engine`** (`sat-early:2026-09-05`): this plan
  creates a new Longhorn volume and depends on healthy replica scheduling. Never
  pair storage-engine work with new-volume creation. The assigned window is six
  weeks *after* it, fully settled.
- **`conflicts_with: bitnamilegacy-exit-nextcloud-db`** — phase 4 is the same
  operation on a bigger, more critical database. One MariaDB replatform per
  window: a shared-mode failure (charset pin dropped, restore semantics wrong)
  should be found on the small one before it is repeated on the family's file
  server.
- **`paperless-ngx-3.0.5` — ordering REVERSED after investigation. It runs FIRST
  (`sat-early:2026-09-19`); this plan runs after.** It is both `depends_on` and
  `conflicts_with`: they edit the same HelmRelease `env:` block so they may never
  share a window, and the sequence matters for a reason that is easy to miss.
  - **They are not in conflict on substance.** Verified against the upstream v3
    migration guide: MariaDB is **not** removed or deprecated in paperless-ngx
    3.x, so nothing forces a DB engine change and the two plans are independent
    on the merits. What v3 *does* require is `PAPERLESS_DBENGINE` set explicitly
    ("Previously, the engine was inferred from the presence of
    `PAPERLESS_DBHOST`"). The 3.0.5 plan gets that from the chart template while
    `mariadb.enabled` is still true; step 6 here makes it explicit permanently.
  - **The reason 3.0.5 must go first is the ROLLBACK VOLUME.** This plan keeps
    `paperless-mariadb` as the untouched revert target for a week afterwards. If
    v3's irreversible Django migrations ran on the *new* database during that
    week, `paperless-mariadb` would be a **pre-v3 snapshot** — and reverting this
    plan would drop paperless-ngx v3 onto a 2.x schema. Running 3.0.5 first means
    both the old and the new volume hold a v3 schema at every moment, so the
    revert is always valid.
  - **The 3.0.5 plan's `conflicts_with` has a commented-out placeholder awaiting
    this plan_id** — fill in `bitnamilegacy-exit-paperless-db` when vetting.
  - One more v3 note for that plan: it removes `CONSUMER_BARCODE_SCANNER`, and
    our values still set `"ZXING"`.
- **`depends_on: bitnamilegacy-exit-paperless-redis`** (phase 2a,
  `tue-early:2026-08-25`) — that plan restructures the same `env:` block for
  Redis. Running phase 3 first is technically possible but produces two
  overlapping rewrites of one block across two windows. It is also
  `conflicts_with` for the same reason: never the same window.
- **`shared: [storage]`** — allocates a 2-replica `longhorn-static` volume. It
  perturbs no other app's storage, but the window agent should not pair it with
  another storage-touching plan.
- **Paperless is fully DOWN for most of this window** (scaled to 0 across dump,
  cutover and restore). Downstream: `paperless-ai` and `paperless-gpt` will log
  API errors throughout; `scan-inbox-validator` is scaled to 0 deliberately so no
  scan is lost — **remember to scale it back** (step 8). Email ingestion
  (`docs/sops/paperless.md`) simply picks up on the next poll.
- The dump in step 2 is a **credential-adjacent artefact** even though it excludes
  the `mysql` schema. Keep it `0600` in a `0700` directory outside the repo,
  and delete it once phase 3 has been clean for a week.
