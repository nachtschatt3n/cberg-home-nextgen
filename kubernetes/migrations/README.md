# Kubernetes Migrations

This directory contains migration tools and documentation for Kubernetes resource migrations.

## Current Status

✅ **PV/PVC Migration Complete** (2025-11-02)

See `MIGRATION_COMPLETE.md` for full details.

## Files

- **MIGRATION_COMPLETE.md** - Summary of completed PV/PVC migration (17 volumes, 183Gi)
- **migrate-volume.sh** - Reusable script for migrating Longhorn volumes
- **archive/** - Historical migration planning documents and logs

## Using the Migration Script

The `migrate-volume.sh` script can be used for future volume migrations:

```bash
./migrate-volume.sh <namespace> <old-pvc> <new-pvc> <size-gi> <app-name>
```

**Example:**
```bash
./migrate-volume.sh ai my-app-data my-app-data 10 my-app
```

**Prerequisites:**
- Ensure Longhorn backups are current
- Application must be a Deployment (not StatefulSet)
- Script scales down app, creates new volume, copies data, creates migration job

**Always verify:**
1. Migration job completes successfully
2. Data copy size matches source
3. Application starts correctly with new volume
4. Keep old volume as backup for 7+ days

## Archive

The `archive/` directory contains historical documents from the 2025-11-02 migration:
- Detailed migration status logs
- Migration planning documents
- Lessons learned documentation

These are kept for reference but are no longer actively maintained.
