---
plan_id: nocodb-calver
component: nocodb
pr: null                          # no open Renovate PR — held major surfaced by coverage/version-check (F-f376ab55)
kind: image
current: "0.301.5"
target: "2026.08.0"
update_type: major                # versioning-scheme switch semver→calver; ~5 months of releases in one jump
risk: medium
est_duration_min: 35
needs_reboot: false
touches:
  namespaces: [databases]
  resources:
    - helmrelease/nocodb
    - deployment/nocodb
    - pvc/nocodb-data              # near-empty (20K); all real data is in shared PG
    - database/nocodb@postgresql   # schema migrations write into the SHARED postgresql instance
  shared: [postgresql]             # shared DB perturbed: nocodb's OWN database only — the
                                   # postgresql pod is NOT restarted and other DBs are untouched,
                                   # but a runaway migration shares the instance's CPU/disk
depends_on: []
conflicts_with: []                 # keep out of the same window as any plan restarting
                                   # deployment/postgresql or the shared-PG movers (see Interference)
security_ref: F-f376ab55
status: executed                   # EXECUTED 2026-08-19 (46fda565 bump, d6cec704 remediation restore)
                                   # in the operator-approved ad-hoc window, STEP 6.
# RETAIN, do not delete on the usual executed-plan convention. Two reasons, both
# time-boxed:
#   1. The migration is ONE-WAY and the operator acceptance gate in §4 (log in,
#      open each base, confirm a test edit saves) is still OPEN. Until it passes,
#      §5 is the live rollback procedure and the dump it names is the only way back.
#   2. §5's "downgrading across the calver boundary is NOT a rollback" and the
#      image=calver / npm=semver split are not recorded anywhere else in the repo.
# Retire once the operator signs off AND the calver facts are folded into
# docs/sops/auto-update.md (the auto-update-policy.yaml deny rule added
# 2026-08-19 carries the short version).
window: null                       # cleared 2026-08-19: executed ahead of the
                                   # tue-early:2026-08-25 slot, which is now released.
auto_execute: false
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/backup.md
generated: "2026-08-18"
---

# nocodb 0.301.5 → 2026.08.0 (semver → calver boundary)

## 1) Summary & why held

NocoDB abandoned `0.x` semver after `0.301.5` (published 2026-03-18, the last
`0.30x` tag on Docker Hub) and switched to calver; the published calver line is
`2026.04.0 … 2026.08.0` (`2026.08.0` published 2026-08-05, "Introducing
Interfaces"). Renovate/auto-update treats the scheme switch as a **major**, so
it was held. This single bump therefore carries **~5 months of feature releases**
(2026.04.x, 2026.05.x, 2026.06.x "NocoDB Sync / doc version history / Oracle",
2026.07.0 "Calendar Sync", 2026.08.0 "Interfaces").

What the upstream evidence says (release notes + official upgrading doc,
`https://nocodb.com/docs/self-hosting/maintenance/upgrading`):

- **DB migrations ship automatically and apply on boot** — e.g. 2026.06.0
  explicitly adds "group-by toggle state, document version-history tables, and a
  wider revision-id column ... they apply automatically on upgrade". Our
  metadata DB is **the shared `postgresql` instance in `databases`**
  (`NC_DB=pg://postgresql…`, pgvector 0.8.1-pg16), so the migration chain runs
  against a database inside shared infra.
- **Official doc: "Always back up before a major version upgrade"** (back up the
  Postgres database). It documents **no downgrade/rollback procedure** —
  **treat the migration chain as one-way**. Rollback is *restore-based*
  (pg_dump restore + git revert), never "just downgrade the tag" (see §5).
- Behavior changes in the span, none of which break our deployment shape:
  2026.08.0 API-v1 user-update endpoints no longer modify workspace access;
  Row-Level-Security now applies to base owners; 2026.06.1 deprecated pre-built
  executables (we run Docker — N/A); 2026.06.0 restricts SQLite-as-external-source
  (we use PG — N/A). New env vars are additive (`NC_AI_*`). No `NC_DB` /
  `NC_AUTH_JWT_SECRET` changes — our two secret envs stay valid.
- Headline features (Interfaces, RLS dynamic conditions) are paid-tier —
  cosmetic for us; the operative content of this upgrade is the migration chain
  itself.

**Why risk is medium, not high:** the deployment is tiny and clean — single
replica, `strategy: Recreate` (verified rendered), external PG holds ALL state
(the `nocodb-data` PVC contains 20K = `lost+found` only), Longhorn backups of
both `nocodb-data` and `postgresql-data-5g` are fresh (03:0x today), and the
migration chain is knex-sequential (skipping intermediate tags is the supported
path — upstream doc: pull new image, restart). The one-way boundary is the only
reason this isn't low.

`security_ref: F-f376ab55` is the held-update finding driving this plan
(version currency, no vulnerability detail applies).

## 2) Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) nocodb + shared PG healthy, HR Ready on app-template 5.1.0
kubectl get pods -n databases | grep -E 'nocodb|^postgresql'
kubectl get hr -n databases nocodb -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion}{"\n"}'

# b) target tag exists (verified 2026-08-18, re-verify)
curl -s "https://hub.docker.com/v2/repositories/nocodb/nocodb/tags/2026.08.0" -o /dev/null -w '%{http_code}\n'   # expect 200

# c) Longhorn backups fresh (last nightly 03:00 run succeeded for both volumes)
kubectl get volume -n storage nocodb-data postgresql-data-5g \
  -o custom-columns=NAME:.metadata.name,LAST_BACKUP:.status.lastBackupAt --no-headers

# d) MANDATORY point-in-time dump of the nocodb metadata DB (the real rollback artifact).
#    DB name comes from the d= param of NC_DB in the app secret — do not hardcode it.
NCDB_NAME=$(sops -d kubernetes/apps/databases/nocodb/app/secret.sops.yaml \
  | python3 -c "import sys,yaml,urllib.parse as u; s=yaml.safe_load(sys.stdin)['stringData']['NC_DB']; print(u.parse_qs(u.urlsplit(s).query)['d'][0])")
mkdir -p ~/backups/nocodb
kubectl exec -n databases deploy/postgresql -- sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d '"$NCDB_NAME"' --clean --if-exists' \
  | gzip > ~/backups/nocodb/nocodb-pre-2026.08.0-$(date +%F).sql.gz
gzip -t ~/backups/nocodb/nocodb-pre-2026.08.0-$(date +%F).sql.gz && \
  ls -lh ~/backups/nocodb/   # sanity: non-trivial size, gzip valid

# e) record a pre-upgrade data fingerprint to compare in §4
kubectl exec -n databases deploy/postgresql -- sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d '"$NCDB_NAME"' -tAc \
  "select count(*) from information_schema.tables where table_schema='"'"'public'"'"'"'
# note the table count; also note base/table counts from the UI if convenient

# f) no in-flight flux reconcile on databases apps
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
```

## 3) Steps

1. **Silence + marker** (attended-tier update, per `application-update.md` §4):
   ```bash
   runbooks/update-marker.sh add nocodb databases 4 "0.301.5 -> 2026.08.0 calver upgrade"
   ```
   (Optional Alertmanager silence for `namespace=databases` / `Nocodb.*|KubePod.*`
   per the SOP if paging is a concern — expected downtime is ~1-3 min.)

2. **Disable HR rollback for the attempt** — a Flux remediation rollback
   mid-migration would flip the image back while knex is writing schema. Edit
   `kubernetes/apps/databases/nocodb/app/helmrelease.yaml`:
   ```yaml
     upgrade:
       cleanupOnFail: true
       remediation:
         retries: 0
         remediateLastFailure: false   # TEMP for calver migration — restore after
   ```

3. **Bump the image tag** in the same file:
   ```yaml
               image:
                 repository: nocodb/nocodb
                 tag: 2026.08.0
   ```

4. **Commit + push** (hunk-scoped — shared worktree):
   ```bash
   git add -p kubernetes/apps/databases/nocodb/app/helmrelease.yaml
   git commit -m "feat(nocodb): 0.301.5 -> 2026.08.0 (calver line; plan nocodb-calver)"
   git push
   ```

5. **Watch the migration boot** (Recreate: old pod terminates first; probes give
   it 60s before liveness — migrations on this tiny DB should finish well inside):
   ```bash
   flux reconcile source git flux-system   # only if the webhook lags
   kubectl get pods -n databases -w | grep nocodb
   kubectl logs -n databases deploy/nocodb -f | grep -iE 'migrat|xc-|error|listen'
   ```

6. **On success:** restore `retries: 3` / remove `remediateLastFailure: false`,
   commit + push, clear the marker:
   ```bash
   runbooks/update-marker.sh clear nocodb
   ```

## 4) Verification

```bash
# HR Ready, pod on new image, stable
kubectl get hr -n databases nocodb -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'
kubectl get pods -n databases -l app.kubernetes.io/name=nocodb \
  -o jsonpath='{.items[0].spec.containers[0].image} {.items[0].status.containerStatuses[0].restartCount}{"\n"}'
# expect nocodb/nocodb:2026.08.0, 0 restarts after settle (~5 min)

# app answers behind the ingress (Authentik forward-auth → expect 302 to outpost, not 5xx)
curl -sk -o /dev/null -w '%{http_code}\n' https://nocodb.<SECRET_DOMAIN>/   # 302/200, NOT 502/503

# migrations completed cleanly
kubectl logs -n databases deploy/nocodb | grep -iE 'migrat' | tail -20   # no errors/rollbacks

# data intact: table count grew (new migration tables) and UI spot-check
kubectl exec -n databases deploy/postgresql -- sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d '"$NCDB_NAME"' -tAc \
  "select count(*) from information_schema.tables where table_schema='"'"'public'"'"'"'
# expect >= pre-upgrade count from §2e

# OPERATOR: log in via browser, open each existing base, confirm tables/views/
# records render and a test edit saves. This is the real acceptance gate.
```

## 5) Rollback

**Downgrading the image across the calver boundary is NOT a rollback.** Upstream
documents no downgrade; 2026.x migrations (new tables, widened columns) leave a
schema 0.301.5 has never seen. Rollback is **revert + restore**:

```bash
# 1) revert the bump (and the temp remediation change if separate)
git revert <bump-commit-sha> && git push
# wait for flux; nocodb pod comes back on 0.301.5 but MUST NOT serve the migrated DB yet:
kubectl scale deploy -n databases nocodb --replicas=0

# 2) restore the pre-upgrade dump (drops+recreates objects via --clean --if-exists)
gunzip -c ~/backups/nocodb/nocodb-pre-2026.08.0-<date>.sql.gz | \
  kubectl exec -i -n databases deploy/postgresql -- sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d '"$NCDB_NAME"''

# 3) bring nocodb back and confirm
kubectl scale deploy -n databases nocodb --replicas=1
kubectl get pods -n databases | grep nocodb          # Running, image 0.301.5
curl -sk -o /dev/null -w '%{http_code}\n' https://nocodb.<SECRET_DOMAIN>/   # 302/200
# OPERATOR: open a base, confirm pre-upgrade data is back
```

(The scale commands are the one sanctioned direct-cluster action here — they
fence the restore; Flux's desired state is restored by the git revert itself.
`postgresql-data-5g` Longhorn backup from 03:03 today is the disaster fallback
if the dump itself is bad — but restoring THAT rolls back every DB in the shared
instance to 03:03 and is a last resort, coordinate per `docs/sops/backup.md`.)

## 6) Interference notes

- **Shared PG is the interference surface.** The `postgresql` pod is not
  restarted, but migrations write to one database inside it. Do NOT share a
  window with: anything that restarts `deployment/postgresql`, the
  `superset-pg-*` shared-PG movers, or `sweep-history`/`pgadmin` maintenance.
- The `nocodb-data` PVC is Longhorn RWO but effectively empty; `Recreate`
  strategy already guards Multi-Attach. No storage-class hazards (longhorn-static,
  reclaim Retain).
- Expected user-visible downtime ~1-3 min (Recreate + migration boot). Homepage
  tile + Authentik forward-auth unaffected (ingress untouched).
- One-way boundary: once §4's operator check passes and the window closes,
  **the pre-upgrade dump is the only way back** — keep
  `~/backups/nocodb/nocodb-pre-2026.08.0-2026-08-19.sql.gz` until at least the next
  nightly Longhorn backup after sign-off. AS TAKEN 2026-08-19 (mode 0600):
  13,307,624 B gzip, 797 MB raw, 98,103 lines, verified complete (ends in the
  pg_dump completion marker, empty stderr log); 116 CREATE TABLE / 116 COPY /
  116 DROP TABLE IF EXISTS + 1 CREATE SCHEMA, matching the live DB exactly;
  90,032 data rows incl. the 44,568-row base table.
- Attended preferred: the acceptance gate (bases/tables render, edit saves) is
  a human check.
