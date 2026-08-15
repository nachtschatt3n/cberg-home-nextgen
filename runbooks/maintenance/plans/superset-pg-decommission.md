---
plan_id: superset-pg-decommission
component: superset
pr: null
kind: chart
current: "bundled bitnamilegacy/postgresql 14.17.0 still running (idle) alongside the live postgres:17.11-alpine"
target: "postgresql.enabled:false — the archived-registry image is gone from the namespace"
update_type: major
risk: medium                          # removes the rollback path; the live DB is not touched
est_duration_min: 30
needs_reboot: false
touches:
  namespaces: [databases]
  resources:
    - helmrelease/superset             # postgresql.enabled: false
    - "REMOVES: statefulset/superset-postgresql + its service"
    - pvc/superset-postgresql-data     # RETAINED, not deleted (see §3 step 5)
    - "longhorn:volume/superset-postgresql-data"   # kept + final backup
  shared: []
depends_on: [superset-pg-cutover]
conflicts_with: [mariadb-27]
status: draft
window: "tue-early:2026-09-22"
auto_execute: false
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/storage-safety.md
  - docs/sops/backup.md
  - docs/sops/longhorn.md
generated: "2026-08-15"
---

# Superset stage 4/4 — retire the bundled `bitnamilegacy` Postgres

## 1) Summary & why held

Final stage. Superset has been running on `postgres:17.11-alpine` since
`superset-pg-cutover` (`sat-early:2026-09-12`); the old bundled Postgres has been
sitting idle as the rollback. This stage turns it off, which is what actually
clears **F-937701ef** from the namespace — the finding does not close until the
image stops running.

**Scheduled 10 days after the cutover, deliberately.** The soak is the point: any
metadata problem that survived verification (a missing saved query, a lost role, a
dashboard nobody opened during the window) shows up in normal use, and while the old
DB exists the fix is a one-line revert. After this stage, recovery is
restore-from-dump/backup.

**What this stage does NOT do: it does not delete data.** `postgresql.enabled: false`
removes the StatefulSet; the PVC `superset-postgresql-data` and its PV
(`persistentVolumeReclaimPolicy: Retain`) and Longhorn volume are **kept**. Reclaiming
that 20Gi is a separate, later, explicitly-decided cleanup — not window work, and not
worth the risk of doing it in the same breath as the cutoff.

**Ordering caution.** This is also the stage that asserts the whole migration is
complete: after it, **no `bitnamilegacy` image may remain in the `databases`
namespace for Superset**. If `superset-redis-official` (stage 1) has not run, that
assertion fails — the Redis half is still on the archived registry.

## 2) Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) the cutover really is live and has soaked
mise exec -- kubectl exec -n databases deploy/superset -- printenv DB_HOST        # superset-pg
mise exec -- kubectl get deploy -n databases superset-pg \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"  ready="}{.status.readyReplicas}{"\n"}'
mise exec -- kubectl get pods -n databases | grep superset                        # note ages/restarts

# b) THE gate — the old DB has been idle since the cutover, i.e. nothing quietly
#    reconnected to it
mise exec -- kubectl exec -n databases superset-postgresql-0 -- psql -U superset -d superset -At -c "
  select coalesce(sum(numbackends),0) from pg_stat_database where datname='superset';"
mise exec -- kubectl exec -n databases superset-postgresql-0 -- psql -U superset -d superset -At -c "
  select xact_commit, xact_rollback from pg_stat_database where datname='superset';"
# Near-zero backends. If something IS connected, find out what before removing it.

# c) the LIVE database still matches what the cutover verified, plus normal growth
NEW=$(mise exec -- kubectl get pods -n databases -l app=superset-pg -o jsonpath='{.items[0].metadata.name}')
mise exec -- kubectl exec -n databases $NEW -- psql -U superset -d superset -At -c "
  select 'dashboards='||count(*) from dashboards
  union all select 'slices='||count(*) from slices
  union all select 'saved_query='||count(*) from saved_query
  union all select 'dbs='||count(*) from dbs
  union all select 'ab_user='||count(*) from ab_user;"

# d) FINAL dump + fresh backup of the DB you are about to switch off. This replaces
#    the running instance as the recovery floor, so it is mandatory.
mise exec -- kubectl exec -n databases superset-postgresql-0 -- \
  pg_dump -U superset -Fc superset > /tmp/superset-legacy-final-$(date +%F).dump
ls -l /tmp/superset-legacy-final-*.dump                                            # not zero bytes
mise exec -- kubectl get volume -n storage superset-postgresql-data \
  -o custom-columns=NAME:.metadata.name,STATE:.status.state,ROBUST:.status.robustness,LASTBACKUP:.status.lastBackupAt
# require lastBackupAt within the hour. Store the dump somewhere that survives /tmp.

# e) stage 1 landed (otherwise the "no bitnamilegacy left" assertion in §4 will fail)
mise exec -- kubectl get pods -n databases -o json | python3 -c "
import sys, json
for p in json.load(sys.stdin)['items']:
    if 'superset' in p['metadata']['name']:
        for c in p['spec']['containers']: print(p['metadata']['name'], c['image'])"

# f) no in-flight reconcile
mise exec -- flux get kustomizations -A | awk 'NR==1 || $5!="True"'
```

## 3) Steps

1. **Marker**:
   ```bash
   runbooks/update-marker.sh add superset databases 1 "retire bundled bitnamilegacy postgres (data retained)"
   ```
2. **Disable the bundled Postgres** in
   `kubernetes/apps/databases/superset/app/helmrelease.yaml` — replace the whole
   `postgresql:` values block with:
   ```yaml
       # Bundled Bitnami postgres retired 2026-09-22. bitnamilegacy is an ARCHIVED
       # registry (last push 2025-08-28; security driver F-937701ef; chart 0.22.4 pins
       # bitnamilegacy/postgresql:14.17.0-debian-12-r3 itself, so no chart bump can
       # fix it). The metadata DB is now postgres:17.11-alpine — pg-deployment.yaml
       # in this folder — reached via DB_HOST in superset-secrets.
       postgresql:
         enabled: false
   ```
3. **Keep the old storage declarations.** Do **not** remove `pv.yaml`,
   `data-pvc.yaml` or `longhorn-volume.yaml` for `superset-postgresql-data` from the
   folder or from `kustomization.yaml` in this stage. The PVC becomes unbound-from-a-pod
   but stays; that is intended.
4. **Render-check + validate before pushing**:
   ```bash
   cd /tmp && rm -rf ssdec && mkdir ssdec && cd ssdec
   curl -sSL -o s.tgz https://github.com/apache/superset/releases/download/superset-helm-chart-0.22.4/superset-0.22.4.tgz
   tar xzf s.tgz
   cd /Users/mu/code/cberg-home-nextgen
   mise exec -- yq '.spec.values' kubernetes/apps/databases/superset/app/helmrelease.yaml \
     | sed 's/\${SECRET_DOMAIN}/example.invalid/g' > /tmp/ssdec/values.yaml
   mise exec -- helm template superset /tmp/ssdec/superset -n databases -f /tmp/ssdec/values.yaml \
     | grep -c 'bitnamilegacy' || echo "no bitnamilegacy in the render (expected)"
   mise exec -- kubeconform -summary -exit-on-error -ignore-missing-schemas kubernetes/apps/databases/superset
   ```
5. **Commit + push** (on `main`, stage only this file):
   ```bash
   git add kubernetes/apps/databases/superset/app/helmrelease.yaml
   git commit -m "feat(superset): retire bundled bitnamilegacy postgres (metadata DB now postgres 17.11)"
   git push
   ```
   Flux removes the `superset-postgresql` StatefulSet and Service. Superset itself
   should **not** restart — its `DB_HOST` did not change. If it does restart, that is
   the reloader reacting to the release; confirm it comes back on `superset-pg`.
6. Clear the marker: `runbooks/update-marker.sh clear superset`.

## 4) Verification

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) the old StatefulSet is gone, the app is unaffected
mise exec -- kubectl get sts -n databases | grep superset-postgresql || echo "old STS gone (expected)"
mise exec -- kubectl get pods -n databases | grep superset
mise exec -- kubectl exec -n databases deploy/superset -- printenv DB_HOST         # superset-pg

# b) THE assertion this whole migration exists for — no archived-registry image left
mise exec -- kubectl get pods -n databases -o json | python3 -c "
import sys, json
bad = []
for p in json.load(sys.stdin)['items']:
    for c in p['spec'].get('initContainers', []) + p['spec']['containers']:
        if 'bitnamilegacy' in c['image']:
            bad.append((p['metadata']['name'], c['image']))
print('bitnamilegacy images still running:', bad or 'NONE')"
# Expect NONE for the superset stack. (Other apps — nextcloud-mariadb,
# paperless-ngx-mariadb, the two unpinned office/ images — are out of scope here and
# are their own hygiene item; note them, do not fix them in this window.)

# c) the data is still there and still served
NEW=$(mise exec -- kubectl get pods -n databases -l app=superset-pg -o jsonpath='{.items[0].metadata.name}')
mise exec -- kubectl exec -n databases $NEW -- psql -U superset -d superset -At -c "
  select 'dashboards='||count(*) from dashboards
  union all select 'slices='||count(*) from slices
  union all select 'saved_query='||count(*) from saved_query;"
DOM=$(mise exec -- kubectl get secret -n flux-system cluster-secrets -o jsonpath='{.data.SECRET_DOMAIN}' | base64 -d)
curl -s -o /dev/null -w '%{http_code}\n' --max-time 20 "https://superset.$DOM/health"     # 200
# Operator: log in, open a dashboard, run a saved query. Same smoke test as the cutover.

# d) the retained data is genuinely retained (this is the recovery floor now)
mise exec -- kubectl get pvc -n databases superset-postgresql-data     # still present
mise exec -- kubectl get pv superset-postgresql-data \
  -o jsonpath='{.spec.persistentVolumeReclaimPolicy}{"\n"}'           # Retain
mise exec -- kubectl get volume -n storage superset-postgresql-data \
  -o custom-columns=NAME:.metadata.name,STATE:.status.state,LASTBACKUP:.status.lastBackupAt

# e) the CVE finding actually closes
mise exec -- trivy image postgres:17.11-alpine --severity CRITICAL --ignore-unfixed | tail -20
```

Success = old StatefulSet gone, no `bitnamilegacy` image running for Superset, HR
Ready, Superset serving on the new DB with intact counts, and the old PVC/PV/Longhorn
volume still present with `Retain` and a fresh backup.

## 5) Rollback

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <decommission-commit-sha>    # postgresql.enabled: true
git push
mise exec -- kubectl get pods -n databases | grep superset-postgresql   # StatefulSet returns
mise exec -- kubectl exec -n databases superset-postgresql-0 -- psql -U superset -d superset -c 'select 1;'
```

The StatefulSet re-binds the retained PVC `superset-postgresql-data`, so the old
database comes back with its data as of the moment it was switched off. **Note what
this rollback does and does not give you:** it restores the *old* server, but Superset
still points at `superset-pg` (`DB_HOST` was not changed by this stage). To fall all
the way back, also revert the `superset-pg-cutover` commit — and accept that anything
written since the cutover lives only in the new DB.

If the retained volume were ever lost, restore from the final dump taken in
pre-check (d) or from the Longhorn backup of `superset-postgresql-data`
(`docs/sops/backup.md`, `docs/sops/longhorn.md`).

**Storage safety:** everything here is `longhorn-static` with `Retain`. This plan
performs **no PVC deletion of any kind**. If a later cleanup proposes deleting
`superset-postgresql-data`, run the `docs/sops/storage-safety.md` pre-flight first —
and note it is a Longhorn volume, not a CIFS/SMB class, so the catastrophic
share-wipe failure mode does not apply, but the data is still gone.

## 6) Interference notes

- **Out of order:** running this before `superset-pg-cutover` deletes the database
  Superset is actively using — an immediate outage plus a restore-from-backup. This
  is the one stage in the set whose out-of-order failure is genuinely destructive;
  the window agent must treat `depends_on` as hard.
- **This stage removes the cheap rollback for the cutover.** That is its cost and the
  reason for the 10-day gap. Do not compress it into the cutover window.
- **`conflicts_with: mariadb-27`** — same namespace; keep failures attributable.
- The `databases` namespace still hosts other `bitnamilegacy` users
  (`nextcloud-mariadb`, `paperless-ngx-mariadb`, and two unpinned
  `bitnamilegacy/{redis,mariadb}:latest` floating tags under `office/`). They are
  **out of scope** for this plan set and should get their own hygiene item — at
  minimum a pin. Do not opportunistically fix them in this window.
- Superset's chart stays at 0.22.4. The chart hold (AR-050 class) and its
  immutable-selector delete-recreate requirement are untouched by this plan set.
