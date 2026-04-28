# SOP: Storage Safety — Destructive Operations on Persistent Storage

> Description: Pre-flight, guardrails, and recovery procedure for destructive PVC/PV operations on shared-filesystem (CIFS/SMB/NFS) and Longhorn storage classes.
> Version: `2026.04.26`
> Last Updated: `2026-04-26`
> Owner: `cluster-ops`

| Field | Value |
|---|---|
| **Version** | 2026.04.26 |
| **Last Updated** | 2026-04-26 |
| **Owner** | cluster-ops |
| **Applies to** | All `kubectl delete pvc/pv` actions, all StorageClass changes, any teardown of stateful workloads |

---

## Description

Destructive storage operations on this cluster have **catastrophic blast radius** when performed against CIFS / SMB / NFS PVCs whose underlying StorageClass mounts a shared filesystem root with `reclaimPolicy: Delete`. Deleting one PVC can recursively wipe an entire share. This SOP exists because that happened on **2026-04-26**: a routine `kubectl delete pvc` removed ~4.7 TB of media, audiobooks, books, and backups in 17 minutes.

This document is **mandatory pre-flight** before any storage-deleting action. It applies to all human operators and to all sub-agents (`cluster-ops-agent`, `health-check-agent`, `version-check-agent`, `security-agent`, `doc-agent`).

## Overview

The `smb.csi.k8s.io` (and similar) CSI drivers honour the StorageClass spec literally. When `reclaimPolicy: Delete` and `parameters.subdir: /`, a PVC delete causes the controller to mount the share root and execute `os.RemoveAll` against it — i.e. recursively delete every file and directory below the share root, regardless of whether they "belong" to the deleted PVC.

This is **not a CSI bug**. The driver is doing exactly what `subdir: /` plus `reclaim: Delete` says to do. The fix is to either avoid that combination at StorageClass authoring time, or to neutralise the PV before deleting the PVC.

## Blueprints

N/A — this SOP governs deletion. Provisioning blueprints live in `docs/sops/new-deployment-blueprint.md` and `docs/sops/longhorn.md`.

## Operational Instructions

### Hard Rule 1 — Pre-flight before every CIFS/SMB/NFS PVC delete

Before running `kubectl delete pvc` (or authorising / scripting one) for any PVC backed by `smb.csi.k8s.io`, `cifs.csi.k8s.io`, or any NFS CSI driver, run the 3-step inspection:

```bash
PVC=<name>
NS=<namespace>
PV=$(kubectl -n $NS get pvc $PVC -o jsonpath='{.spec.volumeName}')

# 1. Print source path and subdir
kubectl get pv $PV -o jsonpath='{.spec.csi.volumeAttributes}' | jq

# 2. Print reclaim policy
kubectl get pv $PV -o jsonpath='{.spec.persistentVolumeReclaimPolicy}'

# 3. Cross-check the StorageClass default
SC=$(kubectl get pv $PV -o jsonpath='{.spec.storageClassName}')
kubectl get sc $SC -o yaml | grep -E 'reclaim|subdir|source'
```

**Decision tree:**

- `subdir == "/"` (or empty, or `..`-traversed) AND `reclaimPolicy == Delete`
  → **STOP. Do not delete the PVC.** Use one of the two safe paths below.
- `subdir` is a per-app path (e.g. `/jdownloader`, `data/<app>`) AND `reclaimPolicy == Delete`
  → Acceptable IF the path is fully owned by the PVC's app. Confirm by inspecting share contents under that subdir before deleting.
- `reclaimPolicy == Retain`
  → Safe to delete the PVC; the underlying data and PV remain. Manual cleanup of the PV (and underlying directory if desired) is a separate explicit step.

**Two safe paths to delete a PVC:**

1. **Patch PV to Retain first** (preferred):
   ```bash
   kubectl patch pv $PV --type=merge \
     -p '{"spec":{"persistentVolumeReclaimPolicy":"Retain"}}'
   kubectl delete pvc -n $NS $PVC
   # PV transitions to Released, data is untouched.
   # If you actually want the data gone, do that explicitly:
   #   - mount the share elsewhere
   #   - rm -rf the specific subdir you created
   #   - kubectl delete pv $PV
   ```
2. **Surface to the user** with the risk spelled out and ask for explicit go/no-go:
   > "This PVC delete will recursively wipe `<share>:<subdir>`. The directory currently contains: `<inventory>`. Confirm Yes/No."

### Hard Rule 2 — "Tear down the Job + PVC" is not routine for shared-fs PVCs

Treat any cluster-ops task that involves deleting storage as **non-routine**. Never infer "this is routine cleanup, safe to proceed" from the brief's wording. The PVC's StorageClass determines blast radius, not the brief.

If the brief is ambiguous (e.g. "clean up the test resources"), enumerate what each resource is before acting:
- For PVCs: run the 3-step pre-flight above
- For PVs: `kubectl get pv ... -o yaml` and check `spec.csi.volumeAttributes.subdir` + `spec.persistentVolumeReclaimPolicy`
- For StatefulSets: deletion does not delete PVCs by default, but `--cascade=foreground` and manual PVC cleanup do

### Hard Rule 3 — Dangerous StorageClasses on this cluster

**Subdir = share root (`/`) + `reclaimPolicy: Delete` — catastrophic, full share wipe on any PVC delete:**

| StorageClass | Source | Subdir | Reclaim |
|---|---|---|---|
| `cifs-jellyfin-media` | `//192.168.31.230/media` | `/` | Delete ⚠ |
| `cifs-plex-media` | `//192.168.31.230/media` | `/` | Delete ⚠ |

**Subdir = entire app share + `reclaimPolicy: Delete` — wipes the whole app share:**

| StorageClass | Source | Subdir | Reclaim |
|---|---|---|---|
| `cifs-frigate-media` | `//192.168.31.230/frigate` | `/media` | Delete |
| `cifs-scrypted-media` | `//192.168.31.230/scrypted` | `/media` | Delete |
| `cifs-icloud-docker-mu` | `//192.168.31.230/backups` | `icloud-backup/mu` | Delete |
| `cifs-jdownloader-media` | `//192.168.31.230/media/downloads` | `/jdownloader` | Delete |
| `cifs-makemkv-media` | `//192.168.31.230/media` | `/Transcode` | Delete |
| `cifs-tube-archivist-media` | `//192.168.31.230/media/downloads` | `/tube-archivist` | Delete |
| `cifs-nextcloud-data` | `//192.168.31.230/nextcloud` | `data` | Delete |
| `cifs-paperless-consume` | `//192.168.31.230/paperless_ngx` | `consume` | Delete |
| `cifs-paperless-export` | `//192.168.31.230/paperless_ngx` | `export` | Delete |
| `cifs-paperless-log` | `//192.168.31.230/paperless_ngx` | `log` | Delete |
| `cifs-paperless-media` | `//192.168.31.230/paperless_ngx` | `media` | Delete |

**Safer (`reclaimPolicy: Retain`) — PVC delete leaves data on share:**

| StorageClass | Notes |
|---|---|
| `cifs-opencode-andreamosteller` | Retain — PV must be cleaned up manually |
| `cifs-penpot-assets` | Retain — same |

A PVC against any `Delete` class above means the blast radius is the entire `<source>/<subdir>`, **not** the PVC's stated quota. Treat the quota as a cosmetic field — it does not bound deletes.

**Update this list** when StorageClasses are added or when their `subdir` / `reclaimPolicy` changes. Re-audit with:

```bash
kubectl get sc -o json | python3 -c '
import sys, json
for sc in json.load(sys.stdin)["items"]:
    if "smb.csi" in (sc.get("provisioner") or "") or "cifs" in sc["metadata"]["name"].lower():
        p = sc.get("parameters", {})
        print(f"{sc[\"metadata\"][\"name\"]:40} reclaim={sc.get(\"reclaimPolicy\")}  subdir={p.get(\"subdir\")}  source={p.get(\"source\")}")'
```

### Hard Rule 4 — Sub-agent dispatch must propagate the rules

When `cluster-ops-agent` (or any agent) dispatches a sub-task that involves PVC / PV deletion, **the brief to the sub-agent must include Rules 1–3 verbatim, plus the dangerous StorageClass list**. Do not assume sub-agents will self-discover this risk. Sub-agents are read-only by default; if they recommend a destructive storage action, they must surface it to the user with the pre-flight result attached.

### Hard Rule 5 — Reporting after destructive actions

After any `kubectl delete pv|pvc|pod|sts|deploy` against persistent storage, the agent's report must include:

1. The PV name(s) that were affected
2. `spec.csi.volumeAttributes` for each (source, subdir)
3. `spec.persistentVolumeReclaimPolicy` at the time of deletion
4. The path/inventory that the underlying directory contained immediately before the action
5. Whether reclaim actually fired (CSI controller logs: search for `removing subdirectory at`)

This lets the user verify blast radius matches expectation. Silence on the post-report = treat as a near-miss to investigate.

### Hard Rule 6 — StorageClass authoring

When introducing a new CIFS / SMB / NFS StorageClass:

- **Never** set `subdir: /` (share root) with `reclaimPolicy: Delete`
- Prefer `reclaimPolicy: Retain` for any class that points at user data
- Subdir must be a per-app path that is exclusively owned by PVCs of that class
- Add the new class to the table in this SOP in the same commit
- A storage-introducing PR must reference this SOP in the description

### Recommended wrapper

A safe wrapper script lives at `runbooks/kubectl-rm-pvc-safe.sh` (TODO — to be added). It runs the 3-step pre-flight automatically and refuses if `subdir == "/"` + `reclaim == Delete`. Use it in place of raw `kubectl delete pvc` for any CIFS/SMB/NFS class.

## Examples

### Example 1: Refuse to delete a dangerous PVC

```
$ kubectl delete pvc extract-sort-nas -n download
# DON'T. Run pre-flight first:
$ PV=$(kubectl -n download get pvc extract-sort-nas -o jsonpath='{.spec.volumeName}')
$ kubectl get pv $PV -o jsonpath='{.spec.csi.volumeAttributes}' | jq
{
  "subdir": "/",
  "source": "//192.168.31.230/media",
  ...
}
$ kubectl get pv $PV -o jsonpath='{.spec.persistentVolumeReclaimPolicy}'
Delete
# subdir=/ AND reclaim=Delete → STOP.
$ kubectl patch pv $PV --type=merge \
    -p '{"spec":{"persistentVolumeReclaimPolicy":"Retain"}}'
$ kubectl delete pvc extract-sort-nas -n download
# PV is now Released, data is untouched.
```

### Example 2: Safe deletion of a PVC on a Retain class

```
$ PV=$(kubectl -n office get pvc opencode-andrea-data -o jsonpath='{.spec.volumeName}')
$ kubectl get pv $PV -o jsonpath='{.spec.persistentVolumeReclaimPolicy}'
Retain
# Safe — PV will go to Released; data stays. Proceed.
$ kubectl delete pvc opencode-andrea-data -n office
# Optionally clean up PV manually after verifying you no longer need the data:
$ kubectl delete pv $PV
```

## Verification Tests

### Test 1: All Released PVs on dangerous classes are on `Retain`

```bash
kubectl get pv -o json | python3 -c '
import sys, json
bad = []
for pv in json.load(sys.stdin)["items"]:
    csi = pv.get("spec",{}).get("csi") or {}
    if "smb.csi" in csi.get("driver",""):
        sub = csi.get("volumeAttributes",{}).get("subdir","")
        rp = pv["spec"].get("persistentVolumeReclaimPolicy")
        ph = pv["status"].get("phase")
        if (sub == "/" or sub == "") and rp == "Delete":
            bad.append(f"{pv[\"metadata\"][\"name\"]} sc={pv[\"spec\"].get(\"storageClassName\")} phase={ph}")
print("DANGEROUS:" if bad else "OK")
for b in bad: print(" ", b)'
```

Expected: `OK` (no PVs with `subdir:/` + `reclaim:Delete` should remain on the cluster).

### Test 2: No new StorageClass introduces the foot-gun

```bash
kubectl get sc -o json | python3 -c '
import sys, json
bad = []
for sc in json.load(sys.stdin)["items"]:
    if "smb.csi" in (sc.get("provisioner") or ""):
        p = sc.get("parameters", {})
        sub = p.get("subdir","")
        rp = sc.get("reclaimPolicy")
        if (sub == "/" or sub == "") and rp == "Delete":
            bad.append(f"{sc[\"metadata\"][\"name\"]}")
print("DANGEROUS:" if bad else "OK")
for b in bad: print(" ", b)'
```

Expected: `OK`. Any class flagged here is a landmine waiting for the next operator.

## Troubleshooting

### CSI controller still tries to reap a Released PV

Symptom: `csi-smb-controller` logs show `removing subdirectory at /tmp/pvc-...` for an already-Released PV.

Action:
1. Patch the PV to `Retain` immediately:
   ```bash
   kubectl patch pv <name> --type=merge \
     -p '{"spec":{"persistentVolumeReclaimPolicy":"Retain"}}'
   ```
2. Inspect what the CSI was about to delete (or already deleted):
   ```bash
   kubectl logs -n kube-system -l app=csi-smb-controller --since=1h | grep -E "removing|RemoveAll"
   ```
3. If data has already been removed, treat as P0 incident — see this SOP's "Diagnose Examples".

### A pod's CIFS mount shows `?????????` for files

Likely the SMB connection lost state mid-operation, or the underlying share was modified. Don't panic-remount; first cross-check from another pod that mounts the same share. If both confirm data missing, that's a real loss — escalate, do not attempt another delete, and do not restart workloads holding open handles (they may be the only thing preserving in-memory cached data).

## Diagnose Examples

### Example: 2026-04-26 incident

| Step | Detail |
|---|---|
| 1. Trigger | `kubectl delete pvc extract-sort-nas` in `download` namespace, after a one-shot `extract-sort` Job completed |
| 2. PV | `pvc-806b0642-f818-40c4-aaba-658394a847b4` |
| 3. StorageClass | `cifs-jellyfin-media` — `source=//192.168.31.230/media`, `subdir=/`, `reclaim=Delete` |
| 4. CSI action | Mounted the share root, ran `os.RemoveAll`. Smoking gun in `csi-smb-controller` logs: `controllerserver.go:251] removing subdirectory at /tmp/pvc-806b0642-…` |
| 5. Duration | ~17 minutes (21:15–21:32 UTC) |
| 6. Loss | ~4.7 TB across audiobooks, books, kopia backups, music, transcode, downloads, most of `data/Movies`, `data/TV Shows`, `data/Music` |
| 7. Stopped by | Patching the PV to `reclaimPolicy: Retain` so the controller stopped retrying |
| 8. Why agent missed it | Brief said "tear down the Job + PVC". Agent did not inspect `volumeAttributes.subdir` or `reclaimPolicy` before deleting. The "10 Gi RWX" claim shape did not signal that the underlying mount was the entire share root. |

## Health Check

Run Tests 1 and 2 above. Both must return `OK`. Add to `runbooks/health-check.md` if not already covered.

## Security Check

A StorageClass that allows tenants (or any operator with `pvc:delete` RBAC) to wipe a shared filesystem is a privilege escalation primitive. Treat the dangerous-class table as a security finding to remediate, not a steady state.

## Rollback Plan

Destructive storage operations are **not rollback-able** unless backups exist. Rollback strategy must precede the action, not follow it:

- Verify backups (Longhorn snapshot, kopia, NAS-level snapshot) of the relevant share are recent
- For NAS-side restore: Longhorn snapshot ≠ NAS share snapshot. CIFS-mounted shares are restored from the NAS, not from Longhorn
- If you are about to perform a destructive action without a confirmed restore path, **do not perform it**

For the 2026-04-26 incident, rollback was attempted by restoring from kopia (where covered) and accepting loss for paths without backup coverage. Document recovery state in `docs/security-accepted-risks.md` if any data is unrecoverable.

## See also

- `docs/sops/longhorn.md` — Longhorn-specific storage (block-level, single-PVC blast radius — different risk profile)
- `docs/sops/new-deployment-blueprint.md` — provisioning blueprint; references this SOP for storage authoring
- `docs/sops/backup.md` — backup strategy; rollback paths
- `.claude/agents/cluster-ops-agent.md` — agent must enforce these rules
