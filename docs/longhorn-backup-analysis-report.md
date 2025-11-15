# Longhorn CIFS Backup Analysis Report

**Generated:** 2025-11-15  
**Backup Target:** `cifs://192.168.31.230/backups`

## Executive Summary

- **Total Backup Size:** 1,111.04 GB
- **Current Active Volumes:** 50
- **Backup Volumes Found:** 135
- **Total Backups:** 226
- **Unused Volume Backups:** 604.22 GB (54% of total)
- **Active Volume Backups:** 127.13 GB (11% of total)
- **System Backups:** 214.34 GB (19% of total)

## Key Findings

### ⚠️ Significant Unused Backup Space

**604.22 GB** of backup space is being used by volumes that are no longer in the cluster. This represents **54% of total backup storage**.

### Top Unused Volumes by Size

1. **ollama-ipex-config** - 146.63 GB (Last backup: 2025-08-29)
2. **pvc-4fc9bcec-7f39-4950-8545-941ab9a78291-f9baac94** - 97.99 GB (Last backup: 2025-11-12)
3. **pvc-aa78722f-9ff1-432e-8da3-3804ca84c78f-bbac37dc** - 97.98 GB (Last backup: 2025-11-12)
4. **pvc-a1aab4ae-5eb3-49b0-8034-2d649827c946-f62af2d7** - 66.21 GB (Last backup: 2025-11-12)
5. **pvc-915629ab-67ed-437b-bc35-2bb1955faa9e** - 28.55 GB (Last backup: 2025-10-07)

### Notable Unused Volumes

- **ollama-ipex-config** (146.63 GB) - Intel IPEX Ollama configuration, last backed up in August 2025
- **open-webui** volumes (14.70 GB total) - Multiple versions of Open WebUI backups
- **tube-archivist-cache-restored** (6.15 GB) - Restored cache volume, likely temporary
- **influxdb2-data** (2.47 GB) - InfluxDB data volume no longer in use
- **mariadb-data** (0.61 GB) - Old MariaDB volume
- **postgresql-data-ea70c634** (0.57 GB) - Old PostgreSQL volume

## Space Usage Breakdown

| Category | Size (GB) | Percentage |
|----------|-----------|------------|
| Unused Volume Backups | 604.22 | 54.4% |
| System Backups | 214.34 | 19.3% |
| Active Volume Backups | 127.13 | 11.4% |
| Other/Unknown | 165.35 | 14.9% |
| **Total** | **1,111.04** | **100%** |

## Recommendations

### Immediate Actions

1. **Review and Clean Up Old Volumes**
   - **ollama-ipex-config** (146.63 GB) - Verify if Intel IPEX Ollama is still needed
   - Large PVC backups from November 2025 - May be from recent migrations or testing
   - Old database volumes (influxdb2-data, mariadb-data, postgresql-data-ea70c634)

2. **Investigate Recent Large Backups**
   - Three PVC volumes backed up on 2025-11-12 totaling ~262 GB
   - These may be from recent migrations or temporary workloads

3. **Clean Up Temporary/Restored Volumes**
   - `tube-archivist-cache-restored-e1096020` - Appears to be a restored cache
   - `open-webui` and `open-webui-10g-2dab00de` - Multiple versions

### Long-term Improvements

1. **Implement Backup Retention Policy**
   - Set automatic cleanup for backups older than X days
   - Configure Longhorn's `failedBackupTTL` and cleanup policies

2. **Regular Backup Audits**
   - Run the analysis script monthly: `tools/analyze-longhorn-backups.py`
   - Document volume lifecycle and cleanup procedures

3. **Monitor Backup Growth**
   - Track backup size trends over time
   - Set alerts for unusual backup growth

## How to Clean Up Unused Backups

### Using Longhorn UI

1. Access Longhorn UI
2. Navigate to Backup & Restore
3. Filter by volume name
4. Delete backups for unused volumes

### Using kubectl

```bash
# List backups for a specific volume
kubectl get backups -n storage -l longhorn.io/volume-name=<volume-name>

# Delete specific backup
kubectl delete backup <backup-name> -n storage

# Delete all backups for a volume (use with caution)
kubectl get backups -n storage -o json | \
  jq -r '.items[] | select(.spec.volumeName=="<volume-name>") | .metadata.name' | \
  xargs -I {} kubectl delete backup {} -n storage
```

### Using Longhorn CLI

```bash
# List backup volumes
kubectl get backupvolumes -n storage

# Delete backup volume (removes all backups for that volume)
kubectl delete backupvolume <backup-volume-name> -n storage
```

## Analysis Script

The analysis script is available at:
```
tools/analyze-longhorn-backups.py
```

Run it anytime to get an updated report:
```bash
./tools/analyze-longhorn-backups.py
```

## Notes

- System backups (214.34 GB) are important for disaster recovery and should be retained
- Some "unused" volumes may be intentionally kept for recovery purposes
- Always verify backups are not needed before deletion
- Consider archiving important backups before deletion if space is critical
