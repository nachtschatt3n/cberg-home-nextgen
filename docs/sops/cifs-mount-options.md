# SOP: CIFS / SMB Mount Options

| Field | Value |
|---|---|
| Version | 2026.05.09 |
| Last Updated | 2026-05-09 |
| Owner | infra |
| Related SOPs | `docs/sops/storage-safety.md`, `docs/sops/longhorn.md` |

## Description

Reference for every CIFS/SMB mount in the cluster: the NAS share it points at, the mount options used, the trade-off it expresses, and the use case profile it belongs to. Use this when adding a new CIFS-backed PVC or troubleshooting backup/IO issues.

## Overview

All CIFS mounts target one NAS at `192.168.31.230` (UNAS-CBERG, Servers VLAN). Two consumers mount CIFS shares:

1. **Longhorn `BackupTarget`** — daily volume backups (one mount path under `/backups`).
2. **`csi-driver-smb` provisioner** — application data PVs (media, downloads, docs, etc.) via 15 StorageClasses + 18 PVs.

Three operational profiles emerged from the inventory below:

| Profile | Where used | Cache | Consistency | Resilience |
|---|---|---|---|---|
| **A — Performance** | media reads (Plex, Jellyfin, Frigate, Paperless, Penpot, iCloud-docker) | `cache=loose` | eventual (30s attr timeout) | hard mount (default) |
| **B — Strong-consistency** | continuously-written workdirs (jdownloader downloads/watch/intake, Tube Archivist, Scrypted) | `cache=none` | strict | hard mount |
| **C — POSIX-correct** | apps that need locks/symlinks (Nextcloud, opencode-andreamosteller) | `cache=strict` + `mfsymlinks`/`nobrl`/`mapposix` | strict | hard mount |
| **D — Backup** | Longhorn BackupTarget only | `cache=loose` | n/a (write-once) | **soft mount** (fails fast on hiccup) |

The Backup profile is the only one with `soft`. That's a deliberate trade-off — see "Backup vs application mounts" below.

## Inventory

### Longhorn BackupTarget (Profile D)

```
cifs://192.168.31.230/backups?cifsOptions=soft,cache=loose,retrans=5,actimeo=10,closetimeo=10,echo_interval=60
```

| Option | Effect |
|---|---|
| `soft` | Operations fail with EIO after `retrans` retries instead of blocking forever. **Fail-fast.** |
| `cache=loose` | Aggressive metadata caching (acceptable — backupstore writes are sequential, no cross-process sharing). |
| `retrans=5` | 5 retransmission attempts before EIO. |
| `actimeo=10` | Attribute cache valid for 10 seconds. |
| `closetimeo=10` | Wait up to 10s for pending writes on close. |
| `echo_interval=60` | Send SMB keepalive every 60s. |

**Trade-off:** A transient SMB hiccup (NAS slow, network blip) errors a backup mid-write. Plan B is the next CronJob 24 h later.

### csi-driver-smb StorageClasses

| StorageClass | Source / subdir | Profile | Notable |
|---|---|---|---|
| `cifs-frigate-media` | `//.../frigate` `/media` | A | uid/gid 0, RW for Frigate root container |
| `cifs-icloud-docker-mu` | `//.../backups` `/icloud-backup/mu` | A | iCloud Mu's backup |
| `cifs-jdownloader-media` | `//.../media/downloads` `/jdownloader` | **B** | strict for in-progress downloads |
| `cifs-jellyfin-media` | `//.../media` `/` | A | shared with Plex |
| `cifs-makemkv-media` | `//.../media` `/Transcode` | A | rip workdir |
| `cifs-nextcloud-data` | `//.../nextcloud` `/data` | **C** | `nounix mapposix nobrl forceuid` |
| `cifs-opencode-andreamosteller` | `//.../opencode` `/andrea-opencode` | **C** | `mfsymlinks cache=strict` |
| `cifs-paperless-{consume,export,log,media}` | `//.../paperless_ngx` `/{...}` | A | document workflow |
| `cifs-penpot-assets` | `//.../penpot` `/assets` | A | uid 1001 |
| `cifs-plex-media` | `//.../media` `/` | A | shared with Jellyfin |
| `cifs-scrypted-media` | `//.../scrypted` `/media` | **B** | NVR clip writes |
| `cifs-tube-archivist-media` | `//.../media/downloads` `/tube-archivist` | **B** | YouTube download writes |

### Profile A — Performance (read-heavy)

```
vers=3.1.1, dir_mode=0777, file_mode=0777, uid=1000, gid=1000,
noperm, noatime, rsize=1048576, wsize=1048576,
cache=loose, actimeo=30, serverino
```

Used by: 11 of 18 PVs. Optimised for read throughput on media libraries.

### Profile B — Strong-consistency (write-heavy)

```
vers=3.0, dir_mode=0777, file_mode=0777, uid=1000, gid=1000,
noperm, cache=none, actimeo=0, noserverino
```

Used by: 5 PVs (jdownloader downloads/watch/intake, tube-archivist, scrypted-media). `cache=none + actimeo=0` ensures every read sees the latest bytes — required when one pod is writing chunks while another is reading them. Still `vers=3.0` (not 3.1.1) — historical, because some download containers had issues with 3.1.1 under load. Worth re-testing on 3.1.1 next time these are touched.

### Profile C — POSIX-correct

| Mount | Extra options |
|---|---|
| Nextcloud | `cache=strict, forceuid, forcegid, nounix, mapposix, nobrl` — Nextcloud's PHP code needs locking semantics that don't crash CIFS |
| opencode-andreamosteller | `cache=strict, mfsymlinks, noserverino` — symlink emulation for git checkouts |

## Operational instructions

### Adding a new CIFS-backed PVC

1. **Pick the right profile** — A/B/C from the table above based on the workload's read/write pattern.
2. **Reuse an existing StorageClass** if the share + subdir match. Don't create a new SC for each app.
3. **If you need a new SC**, the StorageClass must:
   - Set `reclaimPolicy: Retain` (never `Delete` — see `docs/sops/storage-safety.md`)
   - Pin a non-root `subdir` (never `/` — that turns a PVC delete into a share wipe)
   - Reference a SOPS-encrypted credential secret
4. **Add an entry to the inventory table above** in the same PR.

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

**Caveat:** the URL is the cluster's only backup config. A bad change breaks daily backups for every Longhorn volume.

## Backup vs application mounts — why the difference

Application mounts (A/B/C) use `hard` (the default) so a NAS hiccup translates to "the app pauses for a few seconds, then continues" — kernel transparently retries. Acceptable because applications have bounded writes.

The Longhorn BackupTarget uses `soft` because a daily backup is allowed to skip a day. Without `soft`, a wedged NAS would stall every backup CronJob in the cluster forever, fill instance-manager memory, and eventually crash storage controllers. Better to fail one backup and try tomorrow.

That trade-off is currently working as intended. It also explains why **Plex/Jellyfin keep humming through SMB hiccups while backups occasionally fail mid-stream**.

## Verification tests

```bash
# 1. Confirm BackupTarget is reachable + recently synced
mise exec -- kubectl get backuptarget default -n storage -o jsonpath='{.status.available} lastSync={.status.lastSyncedAt}{"\n"}'

# 2. Confirm csi-driver-smb is healthy
mise exec -- kubectl get pods -n storage -l app=csi-smb-node 2>&1
mise exec -- kubectl get csidriver smb.csi.k8s.io 2>&1

# 3. Spot-check that an application mount is live (read-only test)
mise exec -- kubectl exec -n media deploy/plex-plex-media-server -- ls -la /data/movies/ | head -5

# 4. Confirm every CIFS PV is Bound
mise exec -- kubectl get pv -o json | python3 -c "
import sys, json
for pv in json.load(sys.stdin)['items']:
    if pv['spec'].get('csi',{}).get('driver')=='smb.csi.k8s.io':
        print(f\"  {pv['metadata']['name']}  phase={pv['status']['phase']}\")"
```

## Troubleshooting

### "host is down" during backup write

- **Cause:** SMB session torn down mid-write (NAS pause, network blip, kernel timeout).
- **Effect:** Backup CR transitions to `Error`. Other backups in the same run continue.
- **Fix:** Delete the failed Backup CR. The next daily run retries with a fresh snapshot.

### Stale mount after a backup failure

- **Symptom:** new backup attempts fail with `unmount failed: exit status 32` or `cannot mount CIFS share, file exists`.
- **Cause:** the old SMB mount on a Longhorn instance-manager pod didn't unmount cleanly.
- **Fix:** bounce the affected `instance-manager-*` pod (find via `proxyServer=...:8501 destination=...:10888` in the recurring-job logs). 67 replicas re-sync in a few minutes; volumes stay online via the second replica.

### CIFS module module errors on Talos node

If multiple instance-manager pods on the same node fail, suspect Talos kernel-side CIFS state. Reboot the node via Talos:

```bash
mise exec -- talosctl reboot --nodes 192.168.55.NN
```

This drains, reboots, and rejoins. Other 2 nodes carry traffic.

### Profile B shares (cache=none) showing slow reads

Expected — `cache=none + actimeo=0` means every read goes over SMB. Switch to Profile A only if the workload tolerates 30s of stale reads.

## Diagnose examples

```bash
# Which CIFS mounts does the kernel see on a node?
mise exec -- kubectl debug node/k8s-nuc14-01 -it --image=alpine -- chroot /host mount | grep cifs

# What's the size + last sync of every backupstore subdirectory on the NAS?
# (Run from a pod with NAS access, or directly on the NAS via SSH.)

# Backup CR errors in the last 24h
mise exec -- kubectl get backup.longhorn.io -n storage -o json \
  | python3 -c "import sys,json;[print(b['metadata']['name'], b['status'].get('error','')[:120]) for b in json.load(sys.stdin)['items'] if b['status'].get('state')=='Error']"
```

## Health check

- Every Backup CR in `Completed` state (no `Error` rows for >24 h)
- BackupTarget `available: true`, `lastSyncedAt` <10 min ago
- All `cifs-*` StorageClasses with `reclaimPolicy: Retain`
- All CIFS PVs with non-root `subDir`

## Security check

- All CIFS mount credentials referenced via `csi.storage.k8s.io/node-stage-secret-name` from a SOPS-encrypted Secret
- No CIFS share exposed beyond the cluster's NAT (NAS is on Servers VLAN 10, only k8s-network VLAN 55 has cross-VLAN allow)

## Rollback plan

Live BackupTarget changes:

```bash
# The URL pre-change is captured in git via this SOP — copy it back if a new option breaks backups.
mise exec -- kubectl patch backuptarget default -n storage --type=merge -p \
  '{"spec":{"backupTargetURL":"cifs://192.168.31.230/backups?cifsOptions=soft,cache=loose,retrans=5,actimeo=10,closetimeo=10,echo_interval=60"}}'
```

Application StorageClass / PV changes are GitOps-managed — `git revert` and let Flux reconcile.
