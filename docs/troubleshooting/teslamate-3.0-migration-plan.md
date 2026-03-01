# TeslaMate 2.2.0 → 3.0.0 Migration Plan

> Active migration plan. Delete this file after successful upgrade.
> Created: 2026-03-01

---

## Current Setup

| Component | Value |
|-----------|-------|
| TeslaMate image | `teslamate/teslamate:2.2.0` |
| PostgreSQL image | `postgres:18` |
| PostgreSQL PVC | `teslamate-db` |
| HelmRelease | `kubernetes/apps/home-automation/teslamate/app/helmrelease.yaml` |
| Postgres HelmRelease | `kubernetes/apps/home-automation/teslamate/app/postgres-helmrelease.yaml` |
| Secret | `kubernetes/apps/home-automation/teslamate/app/secret.sops.yaml` |
| DB credentials | From `teslamate-secret` (DATABASE_USER, DATABASE_PASS, DATABASE_NAME) |

---

## Pre-Upgrade: Read the Release Notes First

**This step is mandatory before proceeding.**

Read the full 3.0.0 release notes and migration guide:
- https://github.com/teslamate-org/teslamate/releases/tag/v3.0.0
- Check for: new required env vars, removed env vars, config format changes, schema migration notes

> ⚠️ TeslaMate 3.x moved to the `teslamate-org` GitHub org. The Docker image may have changed from `teslamate/teslamate` to `ghcr.io/teslamate-org/teslamate`. Verify the correct image repository in the release notes.

Known risk: TeslaMate uses Ecto database migrations. The 2.x → 3.x jump is a major version and likely includes irreversible schema migrations. **The database must be backed up before starting.**

---

## Pre-Upgrade Checklist

- [ ] Read full 3.0.0 release notes — identify breaking config/env changes
- [ ] Confirm correct image repository for 3.0.0 (`teslamate/teslamate` vs `ghcr.io/teslamate-org/teslamate`)
- [ ] Check if any new required env vars were added in 3.0.0
- [ ] Check if `DATABASE_USER`/`DATABASE_PASS`/`DATABASE_NAME`/`ENCRYPTION_KEY` env var names changed
- [ ] Back up the PostgreSQL database (mandatory — migration is irreversible)
- [ ] Confirm TeslaMate is not actively recording a drive (wait for car to be parked/asleep)

### Backup the PostgreSQL database

```bash
# Get the postgres pod name
PG_POD=$(kubectl get pod -n home-automation -l app.kubernetes.io/name=teslamate-postgres -o jsonpath='{.items[0].metadata.name}')

# Get DB credentials from secret
DB_USER=$(kubectl get secret teslamate-secret -n home-automation -o jsonpath='{.data.DATABASE_USER}' | base64 -d)
DB_NAME=$(kubectl get secret teslamate-secret -n home-automation -o jsonpath='{.data.DATABASE_NAME}' | base64 -d)

# Dump the database to local machine
kubectl exec -n home-automation $PG_POD -- pg_dump -U $DB_USER $DB_NAME > /tmp/teslamate-backup-$(date +%Y%m%d-%H%M).sql

# Verify the backup is non-empty
wc -l /tmp/teslamate-backup-*.sql
```

---

## Config Changes Required

### 1. Update image tag (and possibly repository)

In `kubernetes/apps/home-automation/teslamate/app/helmrelease.yaml`:

```yaml
# Current
image:
  repository: teslamate/teslamate
  tag: "2.2.0"

# Check release notes for correct repository. Likely:
image:
  repository: ghcr.io/teslamate-org/teslamate  # verify this
  tag: "3.0.0"
```

### 2. Update any env vars that changed

After reading the release notes, add/remove/rename env vars in `helmrelease.yaml` as required.

### 3. PostgreSQL compatibility

Current setup uses `postgres:18`. Verify that TeslaMate 3.0.0 supports PostgreSQL 18. If not, pin to a supported version in `postgres-helmrelease.yaml`.

---

## Upgrade Steps

1. **Scale TeslaMate to 0 replicas** — stop the app before migrating (prevents partial writes during migration):
   ```bash
   # Do this via GitOps: set replicas: 0 in helmrelease.yaml, commit, push, wait for reconcile
   # Then proceed with the upgrade changes below
   ```

   > Alternatively, proceed directly — TeslaMate's Ecto migration runs automatically on startup and is designed to be safe on first boot with the new version.

2. **Update the HelmRelease** with new image tag (and repo if changed), plus any new env vars:
   ```bash
   # Edit helmrelease.yaml
   vim kubernetes/apps/home-automation/teslamate/app/helmrelease.yaml
   ```

3. **Commit and push:**
   ```bash
   git add kubernetes/apps/home-automation/teslamate/app/helmrelease.yaml
   git commit -m "chore(teslamate): upgrade 2.2.0 → 3.0.0"
   git push
   ```

4. **Monitor pod startup and migration logs** — the Ecto migration runs on first boot:
   ```bash
   kubectl logs -n home-automation -l app.kubernetes.io/name=teslamate -f
   ```

   Expected output during healthy migration:
   ```
   Running migrations...
   [info] == Running XXXXXXXXXX <module>.Migration ...
   [info] == Migrated XXXXXXXXXX in X.Xs
   ...
   [info] TeslaMateWeb.Endpoint init, port: 4000
   ```

   If you see migration errors, **do not restart** — check logs carefully before any action.

5. **Verify the web UI is accessible:**
   ```bash
   kubectl get pods -n home-automation -l app.kubernetes.io/name=teslamate
   # Should be Running

   # Check readiness probe is passing
   kubectl describe pod -n home-automation -l app.kubernetes.io/name=teslamate | grep -A5 "Readiness"
   ```

---

## Rollback

**Important:** If schema migrations have already run, a rollback to 2.2.0 will likely fail because the 3.x schema is incompatible with 2.x. The only clean rollback path is restoring the database backup.

### Full rollback (restore from backup)

```bash
# Step 1: Revert the image tag in helmrelease.yaml to 2.2.0 and push
git revert HEAD
git push

# Step 2: Wait for Flux to roll back the TeslaMate pod (it will fail to start on the migrated DB)

# Step 3: Scale TeslaMate to 0 (set replicas: 0, commit, push)

# Step 4: Restore the database backup
PG_POD=$(kubectl get pod -n home-automation -l app.kubernetes.io/name=teslamate-postgres -o jsonpath='{.items[0].metadata.name}')
DB_USER=$(kubectl get secret teslamate-secret -n home-automation -o jsonpath='{.data.DATABASE_USER}' | base64 -d)
DB_NAME=$(kubectl get secret teslamate-secret -n home-automation -o jsonpath='{.data.DATABASE_NAME}' | base64 -d)

# Drop and recreate DB (DESTRUCTIVE — only if migrations already ran)
kubectl exec -n home-automation $PG_POD -- psql -U $DB_USER -c "DROP DATABASE $DB_NAME;"
kubectl exec -n home-automation $PG_POD -- psql -U $DB_USER -c "CREATE DATABASE $DB_NAME;"
cat /tmp/teslamate-backup-YYYYMMDD-HHMM.sql | kubectl exec -i -n home-automation $PG_POD -- psql -U $DB_USER -d $DB_NAME

# Step 5: Scale TeslaMate back to 1 replica
```

> Data logged between the backup and the failed upgrade attempt will be lost on rollback. This is unavoidable — plan the upgrade during a period of low activity (car parked/asleep).

---

## Verification After Upgrade

- [ ] TeslaMate pod is Running and readiness probe passes
- [ ] Web UI loads at `https://teslamate.<domain>`
- [ ] Car status shows correctly (online/asleep/charging)
- [ ] Historical data is visible in the dashboard
- [ ] Grafana dashboards load (Grafana URL configured in env)
- [ ] MQTT events flowing to Home Assistant

```bash
# Check pod health
kubectl get pods -n home-automation -l app.kubernetes.io/name=teslamate
kubectl logs -n home-automation -l app.kubernetes.io/name=teslamate --tail=30 | grep -i "error\|warn"

# Verify DB connection is healthy
kubectl exec -n home-automation -l app.kubernetes.io/name=teslamate-postgres -- \
  psql -U $DB_USER -d $DB_NAME -c "SELECT COUNT(*) FROM drives;"
```
