# SOP: Backup Procedures

> Standard Operating Procedures for cluster backup management.
> Covers Longhorn volume backups and external backup integrations.
> Description: Running, validating, and restoring Longhorn/iCloud backup workflows.
> Version: `2026.08.18`
> Last Updated: `2026-08-18`
> Owner: `Platform`

---

## Description

This SOP documents backup execution, restore procedures, and operational checks for data safety
before and after cluster changes.

---

## Overview

| Backup System | What | Schedule | Target |
|--------------|------|---------|--------|
| Longhorn volume backup | All PV data | Daily 3:00 AM | UNAS-CBERG NAS |
| iCloud backup | iCloud Drive + Photos, one instance per Apple ID (2) | Continuous | UNAS-CBERG NAS (`backups/icloud-backup/<name>`) |

Related cluster CronJob (non-backup): `kube-system/descheduler`.
When checking `kubectl get cronjobs -A`, do not treat it as a backup workload.

Backup schedule/config changes should be done via GitOps manifests in this repository.

---

## Blueprints

N/A for dedicated blueprint resources.

Source-of-truth manifests:
- Longhorn backup cronjob/resources in `kubernetes/apps/storage/longhorn/`
- iCloud integration in `kubernetes/apps/backup/icloud-docker-{mu,andrea}/`

---

## Operational Instructions

1. Verify scheduled backups and recent job health.
2. Trigger manual backup when needed (e.g., pre-upgrade).
3. Validate volume backup timestamps.
4. Use restore workflow and rebind PV/PVC if recovery is required.

---

## Examples

### Example 1: Trigger Manual Backup

```bash
kubectl create job --from=cronjob/backup-of-all-volumes \
  manual-backup-$(date +%Y%m%d-%H%M) -n storage
```

### Example 2: Verify Latest Backup Timestamps

```bash
kubectl get volumes -n storage \
  -o custom-columns=NAME:.metadata.name,LAST_BACKUP:.status.lastBackupAt --no-headers
```

> **Caveat:** `lastBackupAt` can lag a full backup cycle even when the backup
> succeeded — cross-check the volume's Backup CRs before declaring it stale
> (see Troubleshooting: "lastBackupAt Can Lag").

---

## Verification Tests

### Test 1: CronJob and Recent Job Success

```bash
kubectl get cronjob backup-of-all-volumes -n storage
kubectl get jobs -n storage --sort-by='.status.startTime' | tail -5
```

Expected:
- CronJob exists and recent jobs show completion.

If failed:
- Inspect job events and pod logs.

### Test 2: Backup Freshness

```bash
kubectl get volumes -n storage \
  -o custom-columns=NAME:.metadata.name,LAST_BACKUP:.status.lastBackupAt --no-headers
```

Expected:
- Critical volumes have recent backup timestamps.

If failed:
- First rule out the `lastBackupAt` status lag: check the volume's newest
  Completed Backup CR (see Troubleshooting: "lastBackupAt Can Lag") — a fresh
  Completed CR with an old `lastBackupAt` means the backup DID run.
- Otherwise check backup target configuration and Longhorn manager logs.

---

## Longhorn Volume Backups

### Automated Backup CronJob

A CronJob runs daily at 3:00 AM to back up all Longhorn volumes.

```bash
# CronJob details
kubectl get cronjob backup-of-all-volumes -n storage -o yaml

# View recent jobs
kubectl get jobs -n storage --sort-by='.status.startTime' | tail -10

# View latest job logs
LATEST_JOB=$(kubectl get jobs -n storage --sort-by='.status.startTime' \
  | grep backup-of-all-volumes | tail -1 | awk '{print $1}')
kubectl logs -n storage job/${LATEST_JOB} --tail=100

# Check if backup is currently running
kubectl get pods -n storage | grep backup
```

### Manual Backup (Ad-hoc)

```bash
# Trigger backup now (creates a one-off job)
kubectl create job --from=cronjob/backup-of-all-volumes \
  manual-backup-$(date +%Y%m%d-%H%M) -n storage

# Watch the job
kubectl get pods -n storage -w | grep manual-backup
```

### Verify Backup Status

```bash
# Check volume backup timestamps
kubectl get volumes -n storage \
  -o custom-columns=NAME:.metadata.name,SIZE:.spec.size,LAST_BACKUP:.status.lastBackupAt \
  --no-headers | sort

# Ground truth per volume: the newest Completed Backup CR (lastBackupAt can lag)
kubectl get backups -n storage -l backup-volume=<volume> \
  --sort-by=.metadata.creationTimestamp \
  -o custom-columns=NAME:.metadata.name,STATE:.status.state,CREATED:.metadata.creationTimestamp | tail -3

# Via Longhorn UI
kubectl port-forward -n storage svc/longhorn-frontend 8080:80 &
# Open http://localhost:8080 → Backup → verify volumes listed with recent timestamps
```

> **Caveat:** `lastBackupAt` can lag a full backup cycle even when the backup
> succeeded — cross-check the volume's Backup CRs before declaring it stale
> (see Troubleshooting: "lastBackupAt Can Lag").

---

## Backup Retention Policy

Configure in Longhorn UI → Settings → Backup Retention:

| Setting | Recommended Value |
|---------|-----------------|
| Recurring backup retain count | 7 (7 daily backups) |
| Delete old backup job interval | 24h |

Or configure per-volume in the volume settings.

---

## Restore from Backup

### Restore a Volume via Longhorn UI

1. Open Longhorn UI: `kubectl port-forward -n storage svc/longhorn-frontend 8080:80`
2. Navigate to **Backup**
3. Select the backup → **Restore**
4. Provide a new volume name (e.g., `restored-{original-name}`)
5. Wait for restore to complete (volume appears in Volumes list)

### Bind Restored Volume to Application

After restore, create PV and PVC pointing to the restored volume:

```yaml
# PersistentVolume
apiVersion: v1
kind: PersistentVolume
metadata:
  name: restored-my-app-data
spec:
  capacity:
    storage: 10Gi
  volumeMode: Filesystem
  accessModes:
    - ReadWriteOnce
  persistentVolumeReclaimPolicy: Retain
  storageClassName: longhorn-static
  csi:
    driver: driver.longhorn.io
    fsType: ext4
    volumeAttributes:
      numberOfReplicas: "2"
    volumeHandle: restored-my-app-data   # Must match restored volume name
---
# PersistentVolumeClaim
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: my-app-data
  namespace: my-namespace
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
  storageClassName: longhorn-static
  volumeName: restored-my-app-data
```

Scale down the original deployment, delete old PVC, apply new PVC, scale back up.

---

## iCloud Backup Integration

**Deployments:** `kubernetes/apps/backup/icloud-docker-mu/`,
`kubernetes/apps/backup/icloud-docker-andrea/`

One instance per Apple ID, syncing that account's iCloud **Drive + Photos** to
the NAS for archival. The instances share nothing but the `csi-driver-smb`
credential and the image digest: each has its own SOPS secret, ConfigMap, CIFS
StorageClass (`cifs-icloud-docker-<name>` → `icloud-backup/<name>`) and Longhorn
session PVC. Apple's 2FA quota is per account, so they fail and recover
independently.

```bash
# Check iCloud sync pod status (one deployment per Apple ID)
kubectl get pods -n backup

# View sync logs for one instance
kubectl logs -n backup -l app.kubernetes.io/name=icloud-docker-mu --tail=50
kubectl logs -n backup -l app.kubernetes.io/name=icloud-docker-andrea --tail=50

# Check sync volumes (one -data + one -session per instance)
kubectl get pvc -n backup
```

Sessions expire every ~30-60 days and need an interactive re-auth:
`docs/sops/icloud-docker-reauth.md` (export `INSTANCE` first). The daily sweep
surfaces this as `icloud-docker-<instance> auth/session errors (re-auth
needed): N` — the leading token tells you which Apple ID.

**Coverage beyond Drive + Photos** — contacts, calendars, mail, Health,
Messages — is tracked in `kubernetes/apps/backup/TODO.md`. Note `icloud-docker`
itself supports only `app`/`drive`/`photos`; everything else needs a different
mechanism.

---

## Pre-Upgrade Backup Procedure

Before any significant cluster upgrade (Longhorn, Kubernetes, Talos):

```bash
# 1. Trigger manual backup of all volumes
kubectl create job --from=cronjob/backup-of-all-volumes \
  pre-upgrade-backup-$(date +%Y%m%d) -n storage

# 2. Wait for backup to complete
kubectl wait --for=condition=complete \
  job/pre-upgrade-backup-$(date +%Y%m%d) \
  -n storage --timeout=3600s

# 3. Verify all volumes backed up
#    NOTE: lastBackupAt can lag one cycle — for any volume that looks stale,
#    cross-check its newest Completed Backup CR before re-running the backup
#    (see Troubleshooting: "lastBackupAt Can Lag")
kubectl get volumes -n storage \
  -o custom-columns=NAME:.metadata.name,LAST_BACKUP:.status.lastBackupAt \
  --no-headers | awk '{ print $1, $2 }'

# 4. Proceed with upgrade
```

---

## Health Check

Include in the health check runbook (`runbooks/health-check.md`):

```bash
# 1. Is the CronJob enabled and scheduled?
kubectl get cronjob backup-of-all-volumes -n storage

# 2. Was the last job successful?
kubectl get jobs -n storage --sort-by='.status.startTime' | tail -5

# 3. Any failed backup jobs?
kubectl get jobs -n storage | grep -i fail

# 4. Are volumes backing up?
#    NOTE: a STALE hit here is not proof of a failed backup — lastBackupAt can
#    lag one cycle; confirm via the volume's Completed Backup CRs first.
#    runbooks/health-check.sh longhorn_backup_age_hours() already judges
#    per-volume freshness Backup-CR-first with lastBackupAt as fallback.
kubectl get volumes -n storage \
  -o custom-columns=NAME:.metadata.name,LAST_BACKUP:.status.lastBackupAt \
  --no-headers | awk -v cutoff="$(date -d '2 days ago' -Iseconds 2>/dev/null || date -v-2d -Iseconds)" \
  '$2 < cutoff || $2 == "<none>" { print "STALE/MISSING:", $1 }'
```

---

## Troubleshooting

### lastBackupAt Can Lag — Verify via Backup CRs

`volume.status.lastBackupAt` is derived from the per-volume `volume.cfg` file
in the backup store, which Longhorn rewrites after every backup. Under
parallel backup load (the nightly all-volumes job) that rewrite on the CIFS
backup target can get lost (soft/cache=loose mount semantics), so
`lastBackupAt` keeps the PREVIOUS backup's timestamp even though the new
backup completed — and it only self-corrects at the NEXT successful backup.
Observed 2026-08-18: 16/93 volumes showed a day-old `lastBackupAt` despite
same-day Completed Backup CRs. This is a status-reporting lag, not a failed
backup — do NOT change the CIFS mount options for it, and do not re-trigger
backups based on `lastBackupAt` alone.

Ground truth is the Backup CR:

```bash
# Newest Backup CRs for one volume — a Completed CR <25h old means the
# backup ran, regardless of what lastBackupAt says
kubectl get backups -n storage -l backup-volume=<volume> \
  --sort-by=.metadata.creationTimestamp \
  -o custom-columns=NAME:.metadata.name,STATE:.status.state,CREATED:.metadata.creationTimestamp | tail -3
```

`runbooks/health-check.sh` (`longhorn_backup_age_hours`, incl.
`--per-volume`) implements this judgment: newest Completed Backup CR per
volume first, `lastBackupAt` as fallback.

### Backup Job Failing

```bash
# View job events
kubectl describe job {job-name} -n storage

# View pod logs
kubectl logs -n storage -l job-name={job-name}

# Check Longhorn backup controller
kubectl logs -n storage -l app=longhorn-manager --tail=50 | grep -i backup
```

### Volume Not Backing Up

Common causes:
- Backup target not configured (check Longhorn → Settings → Backup Target)
- NAS unreachable (verify `ping 192.168.55.240`)
- Volume in degraded state (check `kubectl get volumes -n storage`)

```bash
# Check backup target setting in Longhorn
kubectl get setting backup-target -n storage -o jsonpath='{.value}'

# Test NAS connectivity from cluster pod
kubectl run test-pod --rm -it --image=alpine -- ping 192.168.55.240
```

### Longhorn UI Backup Tab Empty

If backup tab shows no backups:
- Verify backup target URL is configured correctly
- Check Longhorn Manager logs for backup-target errors
- Verify NAS share is mounted and accessible

---

## Diagnose Examples

### Diagnose Example 1: Manual Backup Job Stuck

```bash
kubectl describe job {job-name} -n storage
kubectl logs -n storage -l job-name={job-name} --tail=100
```

Expected:
- Events/logs identify a concrete failure reason (target, permissions, connectivity).

If unclear:
- Check Longhorn manager logs for controller-level errors.

### Diagnose Example 2: Volume Missing Recent Backups

```bash
kubectl get volume {volume-name} -n storage -o yaml | rg "lastBackup|robustness|state"
kubectl get setting backup-target -n storage -o jsonpath='{.value}'
```

Expected:
- Volume is healthy and backup target is configured.

If unclear:
- Verify NAS connectivity from cluster.

---

## Security Check

```bash
# Backup credentials should remain SOPS-encrypted
find kubernetes/apps/storage/longhorn -name '*.sops.yaml' -print
head -20 kubernetes/apps/storage/longhorn/app/backup-credentials.sops.yaml | rg "sops:"
```

Expected:
- Backup credentials remain encrypted and not exposed in plaintext files.

---

## Rollback Plan

```bash
# Revert backup configuration changes if jobs begin failing after update
git log -- kubernetes/apps/storage/longhorn kubernetes/apps/backup/
git revert <commit-sha>
git push
```

Rollback validation:
- Re-run `Verification Tests` and `Health Check`.
