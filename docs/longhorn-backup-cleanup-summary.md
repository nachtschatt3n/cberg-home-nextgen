# Longhorn Backup Cleanup Summary

**Date:** 2025-11-15

## Actions Completed

### 1. Deleted ollama-ipex-config Backups ✅
- **Backup Volume:** `ollama-ipex-config`
- **Size Freed:** ~146.63 GB
- **Last Backup:** 2025-08-29
- **Status:** Deleted successfully

### 2. Three Large PVC Volumes from Nov 12, 2025

These are UUID-based PVC volumes (dynamically provisioned) that are no longer in use:

| Backup Volume | Backup Name | Size | Last Backup | Status |
|--------------|-------------|------|-------------|--------|
| `pvc-4fc9bcec-7f39-4950-8545-941ab9a78291-f9baac94` | `backup-0ea1b98e527b4a0b` | 97.99 GB | 2025-11-12 03:46:04Z | ⚠️ Unused |
| `pvc-aa78722f-9ff1-432e-8da3-3804ca84c78f-bbac37dc` | `backup-bfed6b113a854285` | 97.98 GB | 2025-11-12 03:33:06Z | ⚠️ Unused |
| `pvc-a1aab4ae-5eb3-49b0-8034-2d649827c946-f62af2d7` | `backup-064d71f11008476b` | 66.21 GB | 2025-11-12 03:32:16Z | ⚠️ Unused |

**Total Size:** ~262.18 GB

**Analysis:**
- These are UUID-based PVCs, indicating they were dynamically provisioned volumes
- All backed up on the same day (Nov 12, 2025) within a 14-minute window
- No matching PVs exist in the cluster, confirming they're unused
- Likely from:
  - Application migrations or upgrades
  - Temporary workloads or testing
  - Volume migrations or restores

**Recommendation:** These can be safely deleted if confirmed unused. They may have been created during a migration or testing phase.

### 3. Cleaned Up Temporary Volumes ✅

| Volume | Size | Last Backup | Status |
|--------|------|-------------|--------|
| `tube-archivist-cache-restored-e1096020` | 6.15 GB | 2025-11-13 | ✅ Deleted |
| `open-webui` | 7.35 GB | 2025-10-06 | ✅ Deleted |
| `open-webui-10g-2dab00de` | 7.35 GB | 2025-11-15 | ✅ Deleted |

**Total Size Freed:** ~20.85 GB

## Space Savings Summary

| Action | Size Freed |
|--------|------------|
| ollama-ipex-config | 146.63 GB |
| Temporary volumes | 20.85 GB |
| **Total Freed** | **167.48 GB** |

**Remaining Unused Backups:** ~436.74 GB (after cleanup)

## Next Steps

### Option 1: Delete the Three Large PVC Volumes

If you confirm these are no longer needed, delete them:

```bash
# Delete the three large PVC backup volumes
kubectl delete backupvolume pvc-4fc9bcec-7f39-4950-8545-941ab9a78291-f9baac94 -n storage
kubectl delete backupvolume pvc-aa78722f-9ff1-432e-8da3-3804ca84c78f-bbac37dc -n storage
kubectl delete backupvolume pvc-a1aab4ae-5eb3-49b0-8034-2d649827c946-f62af2d7 -n storage
```

This would free an additional **262.18 GB**.

### Option 2: Investigate Before Deleting

If you want to investigate what these volumes contained:

1. Check application logs from Nov 12, 2025
2. Review Git history for deployments/migrations around that date
3. Check if any applications were upgraded or migrated

## Verification

Run the analysis script to verify cleanup:

```bash
./tools/analyze-longhorn-backups.py
```
