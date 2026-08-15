---
plan_id: superset-pg-standup
component: superset
pr: null
kind: infra                           # new datastore stood up ALONGSIDE; nothing cuts over
current: "metadata DB on bundled bitnamilegacy/postgresql 14.17.0-debian-12-r3 (chart subchart 16.7.27)"
target: "a second, EMPTY-then-restored postgres:17.11-alpine running alongside; Superset still on the old DB"
update_type: major
risk: medium                          # additive only — Superset is not repointed in this stage
est_duration_min: 45
needs_reboot: false
touches:
  namespaces: [databases]
  resources:
    - "new: deployment/superset-pg + service/superset-pg + pvc/superset-pg-data"
    - "new: pv/superset-pg-data + longhorn volume superset-pg-data (manual kubectl apply)"
    - "read-only: superset-postgresql (pg_dump source)"
  shared: [storage]                    # creates a new Longhorn static volume (2 replicas)
depends_on: []
conflicts_with: [mariadb-27, longhorn-1.12.1-engine]
status: draft
window: "thu-early:2026-09-03"
auto_execute: false
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/backup.md
  - docs/sops/longhorn.md
generated: "2026-08-15"
---

# Superset stage 2/4 — stand up the replacement Postgres and restore a dump into it

## 1) Summary & why held

Stage 2 of 4. **Superset is not touched in this stage.** It stands up a second
Postgres next to the bundled one and proves the dump/restore works, so that the
cutover (stage 3) is a one-line host change against a database that has already
been verified — instead of a dump, a restore, a cutover and a verification all
racing one 90-minute window.

**The driver.** The bundled metadata DB runs `bitnamilegacy/postgresql:14.17.0-debian-12-r3`
(pinned by the Superset chart itself, not by us) — **5 fixable CRITICALs on an
archived registry that will never publish another fix** (last push to
`bitnamilegacy` was 2025-08-28). `docker.io/bitnami/postgresql` no longer
publishes semver tags either. No chart bump can fix this: chart 0.22.4's own
`values.yaml` carries that exact `bitnamilegacy` pin. Only replacing the datastore
resolves it.

> ### ⚠️ Operator decision to re-confirm before executing this stage
>
> The superseded plan recorded *"DECIDED 2026-08-15 — Option A, CloudNativePG…
> the cluster already runs CNPG patterns elsewhere"*. **That justification is
> false.** CloudNativePG is not installed in this cluster: the only mention in the
> whole repo is `kubernetes/apps/office/sure/app/helmrelease.yaml`, which
> *disables* it — `cnpg.enabled: false`, `cloudnative-pg.enabled: false` — with the
> comment *"keeps the cluster free of CloudNativePG + OT-Redis-Operator just for
> one app."* Choosing Option A therefore means **installing a cluster-wide
> operator first**, which is its own plan and its own risk, and reverses a
> documented house decision.
>
> The steps below implement **Option B**: the house pattern already used twice in
> `databases/` — a plain Deployment on an official image with a real semver stream
> (`postgres:17.11-alpine`; `databases/postgresql` and `office/sure` both use
> `pgvector/pgvector:pg16`, which is the alternative if pgvector is ever wanted).
> It reaches the same goal — off `bitnamilegacy`, back on a Renovate-trackable
> image — with no new operator.
>
> **If the operator still wants CNPG, do not execute this stage:** it needs a
> preceding `cnpg-operator-install` plan and this plan must be rewritten against
> the CNPG `Cluster` CR. Ask before the window, not during it.

**Why 14 → 17 is fine here.** A `pg_dump`/`psql` logical restore is version-independent
in this direction; it is not a binary in-place upgrade. The metadata DB is small
(dashboards, charts, saved queries, users) and the old cluster keeps running
untouched throughout.

**Storage.** Per `docs/sops/longhorn.md` the new volume is `longhorn-static` with a
speaking name (`superset-pg-data`) — Longhorn Volume CR, PV, PVC and `volumeHandle`
all share that identifier. The Longhorn `Volume` CR must be applied **by hand**
(Flux's `targetNamespace: databases` would override its `namespace: storage` and
create a broken duplicate); this mirrors the existing `superset-postgresql-data`
files in the same folder.

## 2) Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) OPERATOR GATE — Option A (CNPG) vs Option B (plain Deployment, this plan).
#    Confirm CNPG is genuinely absent before relying on the argument above:
mise exec -- kubectl get crd | grep -i -E 'cnpg|postgresql.cnpg.io' || echo "no CNPG CRDs (expected)"
mise exec -- kubectl get pods -A | grep -i cloudnative || echo "no CNPG operator (expected)"

# b) current state of the source DB
mise exec -- kubectl get pods -n databases | grep superset
mise exec -- kubectl get sts -n databases superset-postgresql \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'      # bitnamilegacy/postgresql:14.17.0-...
mise exec -- kubectl exec -n databases superset-postgresql-0 -- \
  psql -U superset -d superset -c 'select version();'

# c) size the work — this determines whether 45 min is right
mise exec -- kubectl exec -n databases superset-postgresql-0 -- \
  psql -U superset -d superset -c "select pg_size_pretty(pg_database_size('superset'));"
mise exec -- kubectl exec -n databases superset-postgresql-0 -- \
  psql -U superset -d superset -c "select count(*) from information_schema.tables where table_schema='public';"
# If the DB is more than a few hundred MB, re-estimate before starting.

# d) the target image tag exists
curl -s "https://hub.docker.com/v2/repositories/library/postgres/tags?page_size=100&ordering=last_updated" \
  | python3 -c "import sys,json;print([t['name'] for t in json.load(sys.stdin)['results'] if t['name'].endswith('-alpine')][:10])"

# e) free capacity for a second Longhorn volume + a fresh backup of the CURRENT one
mise exec -- kubectl get volume -n storage superset-postgresql-data \
  -o custom-columns=NAME:.metadata.name,STATE:.status.state,ROBUST:.status.robustness,LASTBACKUP:.status.lastBackupAt
mise exec -- kubectl get nodes.longhorn.io -n storage \
  -o custom-columns=NAME:.metadata.name,READY:.status.conditions[?(@.type==\"Ready\")].status

# f) no in-flight reconcile
mise exec -- flux get kustomizations -A | awk 'NR==1 || $5!="True"'
```

## 3) Steps

1. **Marker** (nothing user-visible should change, but the namespace gets a new pod):
   ```bash
   runbooks/update-marker.sh add superset databases 1 "stand up replacement postgres alongside (no cutover)"
   ```
2. **Take the logical dump FIRST** — before anything new exists, so the artefact is
   from a known-good state. A Longhorn snapshot of a running Postgres is **not** a
   substitute for `pg_dump`:
   ```bash
   mise exec -- kubectl exec -n databases superset-postgresql-0 -- \
     pg_dump -U superset -Fc superset > /tmp/superset-metadata-$(date +%F).dump
   ls -l /tmp/superset-metadata-*.dump          # must not be zero bytes
   mise exec -- kubectl exec -n databases superset-postgresql-0 -- \
     pg_dump -U superset --schema-only superset | head -40    # sanity: real DDL, not an error page
   ```
   Keep this file for stages 3 and 4.
3. **Add the storage manifests**, copying the shape of the existing
   `pv.yaml` / `data-pvc.yaml` / `longhorn-volume.yaml` in
   `kubernetes/apps/databases/superset/app/`, with the identifier `superset-pg-data`
   used identically in the Longhorn `Volume`, the `PV` name, `volumeHandle`, the PVC
   name and the PVC's `volumeName`. Size 20Gi, `numberOfReplicas: 2`,
   `persistentVolumeReclaimPolicy: Retain`, `storageClassName: longhorn-static`.
   Apply the Longhorn Volume CR by hand (it must NOT be in `kustomization.yaml`):
   ```bash
   mise exec -- kubectl apply -f kubernetes/apps/databases/superset/app/pg-longhorn-volume.yaml
   mise exec -- kubectl get volume -n storage superset-pg-data
   ```
4. **Add the Postgres manifests** in
   `kubernetes/apps/databases/superset/app/pg-deployment.yaml` — Deployment +
   Service `superset-pg`, modelled on
   `kubernetes/apps/databases/postgresql/app/deployment.yaml`:
   - image `postgres:17.11-alpine`, `strategy: Recreate`
   - `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` from `superset-secrets`
     (`DB_USER` / `DB_PASS` / `DB_NAME` — the same credentials Superset already uses,
     so the cutover in stage 3 needs no credential change)
   - `PGDATA: /var/lib/postgresql/data/pgdata`, `POSTGRES_INITDB_ARGS: --data-checksums`
   - PVC `superset-pg-data` mounted at `/var/lib/postgresql/data`
   - `pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"` liveness + readiness
   Register `pv.yaml`-equivalent + `pvc` + `pg-deployment.yaml` in
   `kustomization.yaml` (NOT the Longhorn Volume CR).
5. **Validate, commit, push** (on `main`, stage only the files you added):
   ```bash
   mise exec -- kubeconform -summary -exit-on-error -ignore-missing-schemas kubernetes/apps/databases/superset
   git add kubernetes/apps/databases/superset/app/pg-deployment.yaml \
           kubernetes/apps/databases/superset/app/pg-pv.yaml \
           kubernetes/apps/databases/superset/app/pg-pvc.yaml \
           kubernetes/apps/databases/superset/app/pg-longhorn-volume.yaml \
           kubernetes/apps/databases/superset/app/kustomization.yaml
   git commit -m "feat(superset): stand up replacement postgres 17.11 alongside the bitnamilegacy one"
   git push
   ```
   **Do not touch `helmrelease.yaml` or `secret.sops.yaml` in this stage.** Superset
   must keep pointing at the old DB.
6. **Restore the dump into the new server**:
   ```bash
   NEW=$(mise exec -- kubectl get pods -n databases -l app=superset-pg -o jsonpath='{.items[0].metadata.name}')
   mise exec -- kubectl cp /tmp/superset-metadata-$(date +%F).dump databases/$NEW:/tmp/restore.dump
   mise exec -- kubectl exec -n databases $NEW -- \
     sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-privileges /tmp/restore.dump' 2>&1 | tail -30
   # pg_restore may report benign warnings about extensions/owners; read them, do not ignore errors.
   ```
7. Clear the marker: `runbooks/update-marker.sh clear superset`.

## 4) Verification

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) the new server is healthy and on the intended image
mise exec -- kubectl get deploy -n databases superset-pg \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'        # postgres:17.11-alpine
mise exec -- kubectl rollout status deploy/superset-pg -n databases --timeout=300s
mise exec -- kubectl get pvc -n databases superset-pg-data              # Bound
mise exec -- kubectl get volume -n storage superset-pg-data \
  -o custom-columns=NAME:.metadata.name,STATE:.status.state,ROBUST:.status.robustness

# b) THE load-bearing check — the restore is COMPLETE, not merely successful.
#    Compare row counts per table between old and new. A restore that "succeeded"
#    into an empty schema looks identical to a good one at the pod level.
for TARGET in "superset-postgresql-0|superset-postgresql" "$NEW|superset-pg"; do
  POD=${TARGET%%|*}
  echo "--- $POD"
  mise exec -- kubectl exec -n databases $POD -- \
    psql -U superset -d superset -At -c "
      select relname, n_live_tup from pg_stat_user_tables order by relname;"
done
# The two lists must match table-for-table. Pay attention to: dashboards, slices,
# saved_query, ab_user, ab_user_role, dbs.
mise exec -- kubectl exec -n databases $NEW -- \
  psql -U superset -d superset -At -c "select count(*) from alembic_version;"   # must be 1

# c) the OLD database is untouched and Superset is still using it
mise exec -- kubectl get pods -n databases | grep superset
mise exec -- kubectl exec -n databases deploy/superset -- printenv DB_HOST     # still the OLD host
DOM=$(mise exec -- kubectl get secret -n flux-system cluster-secrets -o jsonpath='{.data.SECRET_DOMAIN}' | base64 -d)
curl -s -o /dev/null -w '%{http_code}\n' --max-time 20 "https://superset.$DOM/health"   # 200

# d) no CVE regression introduced by the new image
mise exec -- trivy image postgres:17.11-alpine --severity CRITICAL --ignore-unfixed | tail -20
```

Success = new Deployment Ready on `postgres:17.11-alpine`, PVC Bound on a healthy
2-replica Longhorn volume, per-table row counts matching the old DB, `alembic_version`
present, **Superset still serving from the OLD database**, and no fixable criticals
on the new image.

## 5) Rollback

This stage is purely additive, so rollback is a deletion — and it is safe precisely
because nothing was repointed.

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <standup-commit-sha>     # removes the new Deployment/Service/PVC/PV
git push
mise exec -- kubectl get pods -n databases | grep superset      # only the ORIGINAL stack remains
DOM=$(mise exec -- kubectl get secret -n flux-system cluster-secrets -o jsonpath='{.data.SECRET_DOMAIN}' | base64 -d)
curl -s -o /dev/null -w '%{http_code}\n' --max-time 20 "https://superset.$DOM/health"   # 200, unaffected
```

The Longhorn `Volume` CR was applied by hand, so Flux will not remove it; delete it
deliberately if you are abandoning the migration:
```bash
# ONLY if abandoning — this volume holds a RESTORED COPY, never the live data:
# mise exec -- kubectl delete volume -n storage superset-pg-data
```
**Storage safety:** `superset-pg-data` is a `longhorn-static` volume with
`reclaimPolicy: Retain` — it is not a CIFS/SMB class and deleting its PVC cannot
touch a share (see `docs/sops/storage-safety.md`). Confirm `reclaimPolicy=Retain`
with the pre-flight one-liner before any PVC deletion anyway.

Confirmed back = only the original superset pods, `/health` 200, old PVC untouched.

## 6) Interference notes

- **Out of order:** running stage 3 (`superset-pg-cutover`) without this one means
  repointing Superset at a host that does not exist — the chart's
  `wait-for-postgres` init container blocks for 120 s and then the pod fails, taking
  Superset down until reverted. Nothing is corrupted, but the outage is real.
- **`conflicts_with: longhorn-1.12.1-engine`** (`sat-early:2026-09-05`): this stage
  creates a new Longhorn volume and depends on healthy replica scheduling. Do not run
  storage-engine work and new-volume creation in the same window. The assigned window
  (2026-09-03) is deliberately *before* it, fully settled.
- **`conflicts_with: mariadb-27`** — same `databases` namespace; keep failures attributable.
- `shared: [storage]` is set because this stage allocates a 2-replica Longhorn volume.
  It perturbs no other app's storage, but the window agent should not pair it with
  another storage-touching plan.
- The dump taken in step 2 is the input to stage 3. **It goes stale**: stage 3
  re-dumps immediately before the cutover. Do not reuse this one as the cutover data.
- No user-visible change is expected in this window. If Superset restarts at all,
  something was edited that should not have been — check `helmrelease.yaml` and
  `secret.sops.yaml` are absent from the commit.
