# SOP: CIFS / SMB Mount Options

> Description: Reference for every CIFS/SMB mount in the cluster — the NAS share it points at, the mount options used, the trade-off it expresses, and the use case profile it belongs to. Use this when adding a new CIFS-backed PVC or troubleshooting backup/IO issues.
> Version: `2026.05.09`
> Last Updated: `2026-05-09`
> Owner: `infra`

---

## 1) Description

Documents the complete inventory of CIFS/SMB mount points the cluster maintains against the NAS at `192.168.31.230`, the kernel-level mount options each one uses, and the trade-offs that drove those choices. Operators consult this when adding a new CIFS-backed PVC, tuning a workload's IO profile, or diagnosing backup/mount failures.

- Scope: Longhorn `BackupTarget` + every `csi-driver-smb` StorageClass and PV
- Prerequisites: kubectl + cluster access (or read access to the GitOps repo)
- Out of scope: NFS mounts, application-layer caching, NAS-side share configuration

---

## 2) Overview

All CIFS mounts target one NAS at `192.168.31.230` (UNAS-CBERG, Servers VLAN 10). Two consumers mount CIFS shares:

| Setting | Value |
|---------|-------|
| Namespace (CSI driver) | `storage` |
| Namespace (BackupTarget) | `storage` (Longhorn) |
| Source of truth | `kubernetes/apps/kube-system/csi-driver-smb/` + per-app `kubernetes/apps/*/<app>/app/storageclass.yaml` |
| Critical dependency | NAS at `192.168.31.230`, kernel CIFS module on each Talos node |
| Reclaim policy on every CIFS class | `Retain` (per `docs/sops/storage-safety.md`) |

Three operational profiles emerged from the inventory below, plus a distinct backup profile:

| Profile | Where used | Cache | Consistency | Resilience |
|---|---|---|---|---|
| **A — Performance** | media reads (Plex, Jellyfin, Frigate, Paperless, Penpot, iCloud-docker) | `cache=loose` | eventual (30s attr timeout) | hard mount (default) |
| **B — Strong-consistency** | continuously-written workdirs (jdownloader, Tube Archivist, Scrypted) | `cache=none` | strict | hard mount |
| **C — POSIX-correct** | apps that need locks/symlinks (Nextcloud, opencode-andreamosteller) | `cache=strict` + `mfsymlinks`/`nobrl`/`mapposix` | strict | hard mount |
| **D — Backup** | Longhorn BackupTarget only | `cache=loose` | n/a (write-once) | **soft mount** (fails fast on hiccup) |

The Backup profile is the only one with `soft`. That trade-off is intentional — see `Backup vs application mounts` further down.

---

## 3) Blueprints

Source of truth is the YAML for each StorageClass / PV / BackupTarget — there is no shared blueprint object. Each mount carries its options literally in `mountOptions` (StorageClass) or `cifsOptions=...` query string (BackupTarget URL).

- Source of truth file(s):
  - `kubernetes/apps/storage/longhorn/app/helmrelease.yaml` (`defaultSettings.backupTarget` value drives the BackupTarget URL)
  - `kubernetes/apps/<ns>/<app>/app/storageclass.yaml` for per-app `cifs-*` StorageClass definitions
  - `kubernetes/apps/<ns>/<app>/app/pvc.yaml` for static PVs
- Related manifests: any `kind: PersistentVolume` with `spec.csi.driver: smb.csi.k8s.io`
- Required IDs/constants: NAS host `192.168.31.230`, share names match table below

```yaml
# Minimal blueprint pattern — Profile A StorageClass
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: cifs-<app>-<purpose>
provisioner: smb.csi.k8s.io
reclaimPolicy: Retain   # NEVER Delete on shared CIFS
parameters:
  source: //192.168.31.230/<share>
  subdir: /<non-root-path>   # NEVER `/`
  csi.storage.k8s.io/node-stage-secret-name: cifs-<app>-creds
  csi.storage.k8s.io/node-stage-secret-namespace: storage
mountOptions:
  - vers=3.1.1
  - dir_mode=0777
  - file_mode=0777
  - uid=1000
  - gid=1000
  - noperm
  - noatime
  - rsize=1048576
  - wsize=1048576
  - cache=loose
  - actimeo=30
  - serverino
```

---

## 4) Operational Instructions

### Adding a new CIFS-backed PVC

1. Pick the right profile (A/B/C from the table above) based on read/write pattern.
2. Reuse an existing StorageClass if the share + subdir match. Don't create a new SC for each app.
3. If you must create a new SC, the StorageClass must:
   - Set `reclaimPolicy: Retain` (never `Delete` — see `docs/sops/storage-safety.md`)
   - Pin a non-root `subdir` (never `/` — that turns a PVC delete into a share wipe)
   - Reference a SOPS-encrypted credential secret
4. Add an entry to the inventory table in this SOP in the same PR.
5. Standard GitOps commit/push:

```bash
git add kubernetes/apps/<app>/...
git commit -m "feat(<app>): add cifs-<purpose> StorageClass + PVC"
git push
```

6. Verify Flux reconciles and the PVC binds:

```bash
mise exec -- kubectl get pvc -n <ns> <name>
```

### Tuning the Longhorn BackupTarget

Don't tune unless backups are failing for >2 consecutive runs. Knobs (in order of impact):

| Symptom | Try |
|---|---|
| Frequent "host is down" mid-write | Drop `closetimeo=10` → `closetimeo=30`, drop `actimeo=10` → `actimeo=30` |
| Backup blocks indefinitely on NAS outage | Already mitigated by `soft` — don't change |
| Slow first backup of a new large volume | Add `vers=3.1.1` explicitly + raise `retrans=5` → `retrans=10` |
| Stale mount after backup failure | Bounce the affected `instance-manager-*` pod (other replicas keep volumes online) |

The BackupTarget URL is patched live via:

```bash
mise exec -- kubectl edit backuptarget default -n storage
```

The URL is the cluster's only backup config. A bad change breaks daily backups for every Longhorn volume.

---

## 5) Examples

### Example A: existing Profile A inventory (read-heavy media)

| StorageClass | Source / subdir | Profile |
|---|---|---|
| `cifs-frigate-media` | `//.../frigate` `/media` | A |
| `cifs-icloud-docker-mu` | `//.../backups` `/icloud-backup/mu` | A |
| `cifs-jellyfin-media` | `//.../media` `/` | A |
| `cifs-makemkv-media` | `//.../media` `/Transcode` | A |
| `cifs-paperless-{consume,export,log,media}` | `//.../paperless_ngx` `/{...}` | A |
| `cifs-penpot-assets` | `//.../penpot` `/assets` | A |
| `cifs-plex-media` | `//.../media` `/` | A |

Mount options shared by Profile A:

```
vers=3.1.1, dir_mode=0777, file_mode=0777, uid=1000, gid=1000,
noperm, noatime, rsize=1048576, wsize=1048576,
cache=loose, actimeo=30, serverino
```

### Example B: Profile B (strong consistency, write-heavy)

| StorageClass | Source / subdir | Profile |
|---|---|---|
| `cifs-jdownloader-media` | `//.../media/downloads` `/jdownloader` | B |
| `cifs-scrypted-media` | `//.../scrypted` `/media` | B |
| `cifs-tube-archivist-media` | `//.../media/downloads` `/tube-archivist` | B |

Mount options:

```
vers=3.0, dir_mode=0777, file_mode=0777, uid=1000, gid=1000,
noperm, cache=none, actimeo=0, noserverino
```

`cache=none + actimeo=0` ensures every read sees the latest bytes — required when one pod is writing chunks while another is reading them. Still `vers=3.0` (not 3.1.1) — historical, because some download containers had issues with 3.1.1 under load.

### Example C: Profile C (POSIX-correct)

| Mount | Extra options |
|---|---|
| Nextcloud | `cache=strict, forceuid, forcegid, nounix, mapposix, nobrl` |
| opencode-andreamosteller | `cache=strict, mfsymlinks, noserverino` |

### Example D: Profile D (Longhorn BackupTarget)

```
cifs://192.168.31.230/backups?cifsOptions=soft,cache=loose,retrans=5,actimeo=10,closetimeo=10,echo_interval=60
```

| Option | Effect |
|---|---|
| `soft` | Operations fail with EIO after `retrans` retries instead of blocking forever. **Fail-fast.** |
| `cache=loose` | Aggressive metadata caching (acceptable — backupstore writes are sequential). |
| `retrans=5` | 5 retransmission attempts before EIO. |
| `actimeo=10` | Attribute cache valid for 10 seconds. |
| `closetimeo=10` | Wait up to 10s for pending writes on close. |
| `echo_interval=60` | Send SMB keepalive every 60s. |

### Backup vs application mounts — why the difference

Application mounts (A/B/C) use `hard` (default): a NAS hiccup translates to "the app pauses for a few seconds, then continues" — kernel transparently retries.

The Longhorn BackupTarget uses `soft` because a daily backup is allowed to skip a day. Without `soft`, a wedged NAS would stall every backup CronJob in the cluster forever, fill instance-manager memory, and eventually crash storage controllers. Better to fail one backup and try tomorrow.

That's why Plex/Jellyfin keep humming through SMB hiccups while backups occasionally fail mid-stream.

---

## 6) Verification Tests

### Test 1: BackupTarget reachable + recently synced

```bash
mise exec -- kubectl get backuptarget default -n storage \
  -o jsonpath='available={.status.available} lastSync={.status.lastSyncedAt}{"\n"}'
```

Expected:
- `available=true lastSync=<timestamp within last 10 minutes>`

If failed:
- Inspect Longhorn manager logs: `mise exec -- kubectl logs -n storage -l app=longhorn-manager --tail=50 | grep -i backup`

### Test 2: csi-driver-smb is healthy and every CIFS PV bound

```bash
mise exec -- kubectl get pods -n storage -l app=csi-smb-node
mise exec -- kubectl get pv -o json | python3 -c "
import sys, json
for pv in json.load(sys.stdin)['items']:
    if pv['spec'].get('csi',{}).get('driver')=='smb.csi.k8s.io':
        print(f\"  {pv['metadata']['name']}  phase={pv['status']['phase']}\")"
```

Expected:
- All `csi-smb-node-*` pods Running
- Every smb.csi.k8s.io PV in `phase=Bound`

If failed:
- For an unbound PV: check `kubectl describe pv <name>` for `Events:` — typically a credential or unreachable-share error.

---

## 7) Troubleshooting

| Symptom | Likely Cause | First Fix |
|---------|--------------|-----------|
| Backup CR transitions to `Error` with `host is down` mid-write | SMB session torn down mid-write (NAS pause, network blip, kernel timeout) | Delete failed Backup CR; the next daily run retries with a fresh snapshot |
| New backup attempts fail with `unmount failed: exit status 32` | Stale CIFS mount on Longhorn instance-manager pod | Bounce the affected `instance-manager-*` pod (find via `proxyServer=...:8501 destination=...:10888` in recurring-job logs) |
| Multiple instance-manager pods on same node failing | Talos kernel-side CIFS module state | Reboot the node via `mise exec -- talosctl reboot --nodes 192.168.55.NN` |
| Profile B share showing slow reads | Expected — `cache=none + actimeo=0` means every read goes over SMB | Switch to Profile A only if workload tolerates 30s of stale reads |

```bash
# Backup CR errors in the last 24h
mise exec -- kubectl get backup.longhorn.io -n storage -o json \
  | python3 -c "import sys,json;[print(b['metadata']['name'], b['status'].get('error','')[:120]) for b in json.load(sys.stdin)['items'] if b['status'].get('state')=='Error']"
```

---

## 8) Diagnose Examples

### Diagnose Example 1: backup keeps failing for one specific volume

```bash
# Identify which instance-manager hosts the failing volume's primary replica
PV=<pv-name>
mise exec -- kubectl get replica.longhorn.io -n storage -o json \
  | python3 -c "
import sys,json
for r in json.load(sys.stdin)['items']:
    if r['spec'].get('volumeName')=='$PV':
        print(r['metadata']['name'], '→', r['status'].get('instanceManagerName'))"
```

Expected:
- One or more replicas listed with their hosting instance-manager pod

If unclear:
- Bounce the instance-manager pod hosting the primary replica:
  `mise exec -- kubectl delete pod -n storage <instance-manager-name>`
- Retry by deleting the failed Backup CR and creating a new one referencing a fresh Snapshot.

### Diagnose Example 2: which CIFS mounts does a node currently see?

```bash
mise exec -- kubectl debug node/k8s-nuc14-01 -it --image=alpine -- chroot /host mount | grep cifs
```

Expected:
- One mount entry per CIFS PV active on that node

If unclear:
- Compare against `kubectl get pods --field-selector spec.nodeName=k8s-nuc14-01` joined to PVCs of those pods.

---

## 9) Health Check

```bash
# 1. Every Backup CR in Completed (no Error rows >24h)
mise exec -- kubectl get backup.longhorn.io -n storage --no-headers \
  | awk '$5=="Error"{print}' | head

# 2. BackupTarget available + recent
mise exec -- kubectl get backuptarget default -n storage \
  -o jsonpath='{.status.available}/{.status.lastSyncedAt}{"\n"}'

# 3. All CIFS classes Retain
mise exec -- kubectl get sc -o json \
  | python3 -c "
import sys,json
for sc in json.load(sys.stdin)['items']:
    if sc['provisioner']=='smb.csi.k8s.io' and sc.get('reclaimPolicy')!='Retain':
        print('UNSAFE:', sc['metadata']['name'])"
```

Expected:
- Test 1 returns no rows
- Test 2: `True/<timestamp>` < 10 min ago
- Test 3 prints nothing

---

## 10) Security Check

```bash
# Every CIFS mount references a SOPS-encrypted credential Secret
mise exec -- kubectl get sc -o json \
  | python3 -c "
import sys,json
for sc in json.load(sys.stdin)['items']:
    if sc['provisioner']=='smb.csi.k8s.io':
        p = sc.get('parameters',{})
        if 'csi.storage.k8s.io/node-stage-secret-name' not in p:
            print('NO SECRET REF:', sc['metadata']['name'])"

# No CIFS class pairs subdir:/ with reclaim:Delete
mise exec -- kubectl get sc -o json \
  | python3 -c "
import sys,json
for sc in json.load(sys.stdin)['items']:
    if sc['provisioner']=='smb.csi.k8s.io':
        p = sc.get('parameters',{})
        if p.get('subdir') in ('/', '') and sc.get('reclaimPolicy')=='Delete':
            print('CATASTROPHIC:', sc['metadata']['name'])"
```

Expected:
- No plaintext secrets in repo (covered by `.githooks/pre-commit` Layer 2)
- Authentik / RBAC unchanged by mount-only changes
- No StorageClass pairs `subdir:/` with `reclaim:Delete`

---

## 11) Rollback Plan

Live BackupTarget changes:

```bash
# Restore the URL captured in this SOP (Example D) if a tuning change broke backups.
mise exec -- kubectl patch backuptarget default -n storage --type=merge -p \
  '{"spec":{"backupTargetURL":"cifs://192.168.31.230/backups?cifsOptions=soft,cache=loose,retrans=5,actimeo=10,closetimeo=10,echo_interval=60"}}'
```

Application StorageClass / PV changes are GitOps-managed — `git revert <sha>` and let Flux reconcile.

---

## 12) References

- `docs/sops/storage-safety.md` — PVC delete blast-radius rules; the master safety SOP for any CIFS/SMB/NFS deletion
- `docs/sops/longhorn.md` — Longhorn dynamic vs static class guidance
- `docs/applications.md` — application inventory (which apps consume which CIFS share)
- `kubernetes/apps/kube-system/csi-driver-smb/` — csi-driver-smb HelmRelease
- `kubernetes/apps/storage/longhorn/` — Longhorn HelmRelease + BackupTarget

---

## Version History

- `2026.05.09`: Initial version. Captures the full inventory + 4 profiles after the wazuh-manager backup CIFS-mount incident on 2026-05-09 (commit `6e88f1c0` first revision; this is the SOP-template-conformant rewrite).
