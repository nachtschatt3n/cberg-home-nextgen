# Longhorn Backup Retention Policy Recommendations

## Current Configuration

From `kubernetes/apps/storage/longhorn/app/helmrelease.yaml`:

```yaml
failedBackupTTL: 1440  # 24 hours (failed backups)
recurringSuccessfulJobsHistoryLimit: 1  # Keep 1 successful backup per volume
recurringFailedJobsHistoryLimit: 1
recurringJobMaxRetention: 3  # Maximum 3 backups per volume
autoCleanupRecurringJobBackupSnapshot: true
```

## Issues Identified

1. **No cleanup for deleted volumes**: When volumes are deleted, their backups remain indefinitely
2. **Limited retention settings**: Only keeps 1 successful backup per volume (very minimal)
3. **No age-based cleanup**: Old backups from unused volumes accumulate
4. **No size-based limits**: Large backups can accumulate without limits

## Recommended Retention Policies

### Option 1: Conservative (Recommended)

**For Production Environments:**

```yaml
defaultSettings:
  # Existing settings
  failedBackupTTL: 1440  # 24 hours - keep as is
  
  # Increase backup retention for active volumes
  recurringSuccessfulJobsHistoryLimit: 5  # Keep 5 successful backups
  recurringJobMaxRetention: 7  # Maximum 7 backups per volume
  
  # Add automatic cleanup for old backups
  # Note: Longhorn doesn't have direct age-based cleanup, but we can use recurring jobs
```

**Manual Cleanup Script:**
- Run monthly to delete backups older than 90 days for unused volumes
- Keep system backups indefinitely
- Keep active volume backups per retention policy

### Option 2: Aggressive Cleanup

**For Cost-Conscious Environments:**

```yaml
defaultSettings:
  failedBackupTTL: 720  # 12 hours - reduce failed backup retention
  recurringSuccessfulJobsHistoryLimit: 3  # Keep 3 successful backups
  recurringJobMaxRetention: 5  # Maximum 5 backups per volume
```

**Automated Cleanup:**
- Delete backups older than 30 days for unused volumes
- Delete backups older than 90 days for active volumes (except latest)
- Keep system backups for 180 days

### Option 3: Balanced (Recommended for Your Setup)

**Balanced approach considering your current usage:**

```yaml
defaultSettings:
  # Keep existing failed backup TTL
  failedBackupTTL: 1440  # 24 hours
  
  # Increase retention for active volumes
  recurringSuccessfulJobsHistoryLimit: 3  # Keep 3 successful backups
  recurringFailedJobsHistoryLimit: 1  # Keep 1 failed backup
  recurringJobMaxRetention: 5  # Maximum 5 backups per volume
  
  # Enable automatic cleanup
  autoCleanupRecurringJobBackupSnapshot: true
  autoCleanupSystemGeneratedSnapshot: true
```

## Implementation Plan

### Step 1: Update Longhorn HelmRelease

Update `kubernetes/apps/storage/longhorn/app/helmrelease.yaml`:

```yaml
defaultSettings:
  # ... existing settings ...
  
  # Backup retention settings
  failedBackupTTL: 1440
  recurringSuccessfulJobsHistoryLimit: 3  # Changed from 1
  recurringFailedJobsHistoryLimit: 1
  recurringJobMaxRetention: 5  # Changed from 3
  
  # Cleanup settings
  autoCleanupRecurringJobBackupSnapshot: true
  autoCleanupSystemGeneratedSnapshot: true
```

### Step 2: Create Automated Cleanup CronJob

Create a CronJob to clean up old backups from unused volumes:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: longhorn-backup-cleanup
  namespace: storage
spec:
  schedule: "0 2 * * 0"  # Weekly on Sunday at 2 AM
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 1
  jobTemplate:
    spec:
      template:
        spec:
          serviceAccountName: longhorn-backup-cleanup
          containers:
          - name: cleanup
            image: bitnami/kubectl:latest
            command:
            - /bin/bash
            - -c
            - |
              # Script to delete backups older than 90 days for unused volumes
              # (Script content below)
            env:
            - name: RETENTION_DAYS
              value: "90"
          restartPolicy: OnFailure
```

### Step 3: Create Cleanup Script

Create `tools/cleanup-old-backups.sh`:

```bash
#!/bin/bash
# Cleanup old Longhorn backups for unused volumes
# Usage: ./cleanup-old-backups.sh [retention_days]

RETENTION_DAYS=${1:-90}
CUTOFF_DATE=$(date -d "${RETENTION_DAYS} days ago" -u +"%Y-%m-%dT%H:%M:%SZ")

echo "Cleaning up backups older than ${RETENTION_DAYS} days (before ${CUTOFF_DATE})"

# Get all backup volumes
BACKUP_VOLUMES=$(kubectl get backupvolumes -n storage -o json | \
  jq -r '.items[] | select(.status.lastBackupAt != null) | 
    "\(.metadata.name)|\(.status.lastBackupAt)"')

# Get current active volumes
ACTIVE_VOLUMES=$(kubectl get volumes -n storage -o json | \
  jq -r '.items[].metadata.name')

# Process each backup volume
while IFS='|' read -r bv_name last_backup; do
  # Check if volume is still active
  IS_ACTIVE=false
  for active in $ACTIVE_VOLUMES; do
    if [[ "$bv_name" == "$active"* ]] || [[ "$active" == "$bv_name"* ]]; then
      IS_ACTIVE=true
      break
    fi
  done
  
  # Skip active volumes
  if [ "$IS_ACTIVE" = true ]; then
    continue
  fi
  
  # Check if backup is older than retention period
  if [[ "$last_backup" < "$CUTOFF_DATE" ]]; then
    echo "Deleting unused backup volume: $bv_name (last backup: $last_backup)"
    kubectl delete backupvolume "$bv_name" -n storage --ignore-not-found=true
  fi
done <<< "$BACKUP_VOLUMES"

echo "Cleanup complete"
```

## Recommended Settings for Your Cluster

Based on your current setup (50 active volumes, ~1.1 TB total backups):

### Immediate Changes

```yaml
defaultSettings:
  # Increase backup retention for active volumes
  recurringSuccessfulJobsHistoryLimit: 3  # Keep 3 backups instead of 1
  recurringJobMaxRetention: 5  # Maximum 5 backups instead of 3
  
  # Keep existing cleanup settings
  autoCleanupRecurringJobBackupSnapshot: true
  autoCleanupSystemGeneratedSnapshot: true
```

### Monthly Cleanup Process

1. **Run analysis script** to identify unused volumes:
   ```bash
   ./tools/analyze-longhorn-backups.py
   ```

2. **Review unused volumes** and confirm they can be deleted

3. **Run cleanup script** for volumes older than 90 days:
   ```bash
   ./tools/cleanup-old-backups.sh 90
   ```

4. **Document** any volumes kept for recovery purposes

## Retention Policy Matrix

| Volume Type | Retention Period | Max Backups | Notes |
|-------------|------------------|-------------|-------|
| Active Volumes | 30 days | 5 backups | Keep recent backups for quick recovery |
| Unused Volumes | 90 days | 1 backup | Keep for disaster recovery, then delete |
| System Backups | 180 days | All | Critical for cluster recovery |
| Failed Backups | 24 hours | 1 backup | Quick cleanup of failed attempts |

## Monitoring

### Metrics to Track

1. **Backup Storage Growth**: Monitor total backup size over time
2. **Unused Volume Count**: Track number of unused volumes in backups
3. **Backup Age Distribution**: Monitor age of oldest backups
4. **Cleanup Success Rate**: Track successful cleanup operations

### Alerts

Set up alerts for:
- Backup storage exceeding 2 TB
- Unused backup volumes exceeding 50
- Oldest backup older than 180 days
- Failed cleanup operations

## Implementation Checklist

- [ ] Update Longhorn HelmRelease with new retention settings
- [ ] Create cleanup script (`tools/cleanup-old-backups.sh`)
- [ ] Create CronJob for automated cleanup (optional)
- [ ] Test cleanup script on a few unused volumes
- [ ] Document retention policy in cluster documentation
- [ ] Set up monitoring/alerting for backup storage
- [ ] Schedule monthly review of unused backups

## Notes

- **System backups** should be kept longer as they're critical for disaster recovery
- **Active volume backups** should have shorter retention but more copies
- **Unused volume backups** should be cleaned up aggressively after a grace period
- Always verify backups before deletion
- Consider archiving important backups before deletion if space is critical
