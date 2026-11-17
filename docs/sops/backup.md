# SOP: Backup Procedures

> Standard Operating Procedures for cluster backup management.
> Covers Longhorn volume backups and external backup integrations.
> Description: Running, validating, and restoring Longhorn/iCloud backup workflows.
> Version: `2026.11.17`
> Last Updated: `2026-11-17`
> Owner: `Platform`

---

## Description

This SOP documents backup execution, restore procedures, and operational checks for data safety
before and after cluster changes.

---

## Overview

| Backup System | What | Schedule | Target |
|--------------|------|---------|--------|
| Longhorn volume backup | All PV data | Daily 23:00 UTC (was 03:00 UTC until 2026-10-13) | UNAS-CBERG NAS |
| iCloud backup | iCloud Drive + Photos, one instance per Apple ID (2) | Continuous | UNAS-CBERG NAS (`backups/icloud-backup/<name>`) |

Off-site copy (3-2-1): since 2026-11-15 the NAS backup is uploaded off-site by
restic to a hosted storage box (section "Off-site Backup (restic, hosted storage
box)" below), with alerts on staleness and failure and a recorded restore drill.
This replaced the NAS built-in cloud upload. Still open: retention policy review
and a quarterly re-drill. Re-confirm at the quarterly DR audit
(`docs/sops/disaster-recovery.md`, "Critical prerequisites" table), where the SOPS age key's off-site custody
is recorded as well.

Related cluster CronJob (non-backup): `kube-system/descheduler`.
When checking `kubectl get cronjobs -A`, do not treat it as a backup workload.

Backup schedule/config changes should be done via GitOps manifests in this repository.

---

## Blueprints

N/A for dedicated blueprint resources.

Source-of-truth manifests:
- Longhorn backup RecurringJob `daily-backup-all-volumes` in
  `kubernetes/apps/storage/longhorn/app/recurring-backup-job.yaml`. Longhorn
  materialises it as CronJob `storage/daily-backup-all-volumes` (ownerReference →
  the RecurringJob); the CronJob itself is not a git object — change the
  schedule/retention on the RecurringJob, never on the CronJob.
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
kubectl create job --from=cronjob/daily-backup-all-volumes \
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
kubectl get cronjob daily-backup-all-volumes -n storage
kubectl get recurringjobs.longhorn.io -n storage daily-backup-all-volumes   # its owner
kubectl get jobs -n storage --sort-by='.status.startTime' | tail -5
```

Expected:
- CronJob `daily-backup-all-volumes` exists (there is NO `backup-of-all-volumes` —
  that name was never the object and returns `NotFound`), its owner RecurringJob
  exists, and recent jobs show completion.

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

A CronJob runs daily at 23:00 UTC (01:00 CEST / 00:00 CET; was 03:00 UTC until 2026-10-13) to back up all Longhorn volumes. It is
`storage/daily-backup-all-volumes`, created and owned by the Longhorn
RecurringJob of the same name (`kubectl get recurringjobs.longhorn.io -n storage`;
source `kubernetes/apps/storage/longhorn/app/recurring-backup-job.yaml`, group
`default`, `retain: 7`, `concurrency: 2`).

```bash
# CronJob details (owned by the RecurringJob — edit the RecurringJob in git, not this)
kubectl get cronjob daily-backup-all-volumes -n storage -o yaml
kubectl get recurringjobs.longhorn.io -n storage daily-backup-all-volumes -o yaml

# View recent jobs
kubectl get jobs -n storage --sort-by='.status.startTime' | tail -10

# View latest job logs
LATEST_JOB=$(kubectl get jobs -n storage --sort-by='.status.startTime' \
  | grep daily-backup-all-volumes | tail -1 | awk '{print $1}')
kubectl logs -n storage job/${LATEST_JOB} --tail=100

# Check if backup is currently running
kubectl get pods -n storage | grep backup
```

### Manual Backup (Ad-hoc)

```bash
# Trigger backup now (creates a one-off job)
kubectl create job --from=cronjob/daily-backup-all-volumes \
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

Or configure per-volume in the volume settings. The 7-daily figure covers the
on-site Longhorn store only; the off-site restic repos keep 7 daily / 4 weekly /
12 monthly (weekly `offsite-backup-prune`).

---

## Restore from Backup

### Restore a Volume via Longhorn UI

1. Open Longhorn UI: `kubectl port-forward -n storage svc/longhorn-frontend 8080:80`
2. Navigate to **Backup**
3. Select the backup → **Restore**
4. Provide a new volume name (e.g., `restored-{original-name}`)
5. Wait for restore to complete (volume appears in Volumes list)

### Substituting a backup URL into a manifest

A Longhorn `Backup` CR's `.status.url` contains `&` (query separators). In a
`sed` replacement `&` expands to the whole match, so
`sed "s#__BACKUP_URL__#$URL#"` silently writes a corrupted `fromBackup` that
still looks plausible and fails later. Substitute with Python instead:

```bash
URL="$URL" python3 -c 'import os,sys;sys.stdout.write(sys.stdin.read().replace("__BACKUP_URL__",os.environ["URL"]))' < in.tmpl > out.yaml
kubectl apply --dry-run=server -f out.yaml
```

### Bind Restored Volume to Application

Two cases, decided by whether the app's PV/PVC are git-tracked. Two facts drive
both: `PersistentVolume.spec.csi.volumeHandle` is **immutable** (an existing PV
can never be re-pointed at the restored Longhorn volume), and a bound PVC's
`spec.volumeName` is immutable too (rebinding means delete + recreate the PVC).

**Case A — ad-hoc PV + PVC (not in git).** Create a PV and PVC pointing to the
restored volume:

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

Scale down the original deployment, delete the old PVC (storage-safety pre-flight
first — `docs/sops/storage-safety.md`), apply the new PV + PVC, scale back up.

**Case B — `longhorn-static` app with a git-tracked `pv.yaml` + PVC (the house
default: 60 static volumes as of 2026-09-11, `docs/sops/longhorn.md`).** Flux
re-applies the app's `pv.yaml` and PVC on every reconcile, so a hand-edited or
hand-created PV/PVC is reverted; the rebinding must land in git. Restore to a
NEW Longhorn volume name (e.g. `restored-<app>-data`), then:

1. Scale the consumer to 0 and confirm the old volume detached:
   `kubectl -n <ns> scale deploy/<app> --replicas=0` →
   `kubectl -n storage get volume <old-volume>` shows `detached`.
2. In git, in the app folder: add a **new** PV to `pv.yaml` whose
   `metadata.name` == `spec.csi.volumeHandle` == the restored Longhorn volume
   name (the speaking-name rule), reclaim `Retain`, class `longhorn-static`;
   set the PVC's `spec.volumeName` to that new PV. Keep the PVC **name**
   unchanged so the HelmRelease's `existingClaim`/`claimName` needs no edit.
   Commit + push (`git commit --only <app>/pv.yaml <app>/pvc.yaml`).
3. Let Flux create the new PV (`kubectl get pv <new>` → `Available`); the PVC
   update will be rejected by the API (immutable `volumeName`) — expected.
4. Delete the old PVC — **storage-safety pre-flight first**
   (`docs/sops/storage-safety.md`). Longhorn PVs here are `Retain`, so the old
   PV and Longhorn volume survive as the rollback path. Flux recreates the PVC
   from git, now bound to the new PV.
5. Scale the consumer back up, verify the data, and only then remove the old PV
   / Longhorn volume (and its `longhorn-volume.yaml`) in a later commit.

**Same-name alternative (restore under the ORIGINAL volume name).** Longhorn
can only restore a backup under a name that is free, so the original Longhorn
Volume (and its PV/PVC) must be deleted first — that deletes the on-cluster
replicas and every snapshot with them, leaving the backup-store copy as the
**only** copy for the whole gap, with nothing to fall back on if the restore
fails. Its sole advantage is that no manifest changes. Prefer Case B; use
same-name only when a new name is impossible, never without a fresh Completed
Backup CR for that volume verified first (Troubleshooting: "lastBackupAt Can
Lag"), and never on a CIFS-backed PVC (see Storage Safety).

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

**Sync-health monitoring (the load-bearing signal, since 2026-09-28).**
`CronJob/icloud-sync-probe` (every 10 min, in `kubernetes/apps/backup/icloud-backup-freshness/`)
reads each instance's pod log via the Kubernetes API (Role: pods get/list +
pods/log get in `backup` only) and pushes per-account gauges to Pushgateway:
the newest `Photos synced` timestamp, an auth-required flag and per-cycle
download failures. Alerts: `ICloudBackupSyncStalled` (6h warning / 24h
critical), `ICloudBackupAuthRequired`, `ICloudBackupPersistentDownloadFailures`
(info) and `ICloudBackupDeploymentUnavailable`, each with absence/probe guards.
It keys on the ABSENCE of the success line, so a wedged process (no log lines at
all) still ages into `SyncStalled`. Since 2026-10-03 it covers iCloud **Drive**
the same way (`Drive synced`): `ICloudDriveSyncStalled` (12h warning / 24h
critical, sized from the observed 5-8h drive cadence),
`ICloudDrivePersistentDownloadFailures` (info) and per-account absence guards
— see `docs/sops/icloud-docker-reauth.md` §9.

**File-recency backstop.** The hourly `icloud-backup-freshness` CronJob
walks the backup share from OUTSIDE the sync processes and publishes the newest
photo file's mtime per account, alerting via `ICloudBackupPhotosStale` at
**14 days**. The mtime is the photo's CAPTURE date, so this measures the user's
photo-taking, not the backup: at its former 24h/72h thresholds it paged on
2026-09-28 after two quiet days while the sync was healthy (false positive,
fixed by the sync probe above). It remains only to catch the app claiming
`Photos synced` while writing nothing to the share. It was originally added because no in-band signal can see a wedged sync: on 2026-09-06
both pods sat `Running 1/1` with 0 restarts for 14 days while backing up nothing
(F-21d7e2ec), and the log-scrape finding above read zero the whole time, because
a hung process writes no logs. The probe mounts the read-only
`cifs-immich-icloud-backup` StorageClass — a **second consumer** of that class
alongside Immich's external library, also read-only — whose `subdir` is the
`icloud-backup` parent of both per-account directories, so one mount covers both
Apple IDs. Alert-to-recovery path: `docs/sops/icloud-docker-reauth.md` §9.

**Coverage beyond Drive + Photos** — contacts, calendars, mail, Health,
Messages — is tracked in `kubernetes/apps/backup/TODO.md`. Note `icloud-docker`
itself supports only `app`/`drive`/`photos`; everything else needs a different
mechanism.

---

## Off-site Backup (restic, hosted storage box)

Since 2026-11-15. Replaces the NAS built-in cloud upload as the verified,
monitored off-site copy. Manifests: `kubernetes/apps/backup/offsite-backup/`
(`secrets/` and `app/` are separate Flux Kustomizations), alerts:
`kubernetes/apps/monitoring/kube-prometheus-stack/app/offsite-backup-alerts.yaml`.

**Privacy rule (public repo):** hosts, accounts, share names, folder lists and
repository paths exist ONLY inside the SOPS Secrets `offsite-backup-write`,
`offsite-backup-prune` and `offsite-backup-sources`. Plaintext manifests use
neutral names (`backup-src-1..9`, `offsite-backup-{core,apps,prune,check}`);
PV sources are Flux postBuild variables read from `offsite-backup-sources`.

**Coverage (categories only):**

| Tier | Repository | Contents |
|---|---|---|
| `core` | 1 restic repo | Longhorn backup store (all cluster PV data), phone-cloud backups, other backup folders, document and app-data shares, the two Mac Time Machine sparsebundle images (since 2026-11-16), the monthly GitHub mirror directory (see "GitHub Mirror"), the weekly UniFi autobackup copies (see "UniFi Controller Backup"), and the small curated media trees: music, books, audiobooks, archive (since 2026-11-16) |
| `apps` | 1 restic repo | Small application data shares |

Deliberately NOT covered (operator decisions 2026-11-15/16): the bulk media
library (movies, TV, downloads, transcode scratch, derived photo cache) and
other large lower-priority trees (list kept in the encrypted Secret notes).
Mounting a whole share and using an include list is intended; excluded trees
are never read. Sources are mounted read-only (`ro`), PVs are `Retain`.
The media share is not mounted whole: `backup-src-6..9` are four read-only PVs
whose SMB source is a SUBPATH of that share (one per included tree), so the
excluded trees are not even visible to the job. Their share paths live in
`offsite-backup-sources` as `OFFSITE_SRC_6..9`; no PV uses subdir `/`.

**First run after the 2026-11-16 extension.** The Time Machine images add
about 1.9 TiB, so the first nightly core run uploads roughly 2 TiB (about 15 h
at the 40000 KiB/s cap). Job limits cover it: `activeDeadlineSeconds` 172800
(48 h), `backoffLimit: 0`, and `concurrencyPolicy: Forbid` simply skips the
overlapping night if a run exceeds 24 h (it never kills or stacks runs).
`OffsiteBackupStale` is therefore per tier: apps 36 h, core 60 h (the gap
between two successes can reach ~40 h once, and 60 h also tolerates one skipped
night). Later runs only upload changed bands (minutes to a few GB).

**Crash-consistency caveat.** Sparsebundles are live-written band files
(Time Machine on the Macs writes them during the nightly read). The copy is
crash-consistent at best: a band set read mid-backup can be internally torn.
Restore means attaching the restored bundle and letting macOS verify/repair
it; older restic snapshots (daily/weekly/monthly retention) are the fallback
if the newest one will not mount.

**Jobs (namespace `backup`, UTC):**

| CronJob | Schedule | Key | What |
|---|---|---|---|
| `offsite-backup-apps` | 00:30 daily | append-only | restic backup, tier apps |
| `offsite-backup-core` | 00:40 daily | append-only | restic backup, tier core, upload limited to 40000 KiB/s |
| `offsite-backup-prune` | Sun 04:30 | admin | `forget --prune`, keep 7 daily / 4 weekly / 12 monthly, both tiers |
| `offsite-backup-check` | Wed 04:30 | admin | `check --read-data-subset=5%`, both tiers |
| `offsite-backup-contents` | Mon 06:00 | append-only (read) | read-only contents exporter, see "Dashboard and contents view" |

Longhorn backups run at 23:00 UTC and the nightly maintenance window at 02:30
UTC; `concurrencyPolicy: Forbid` everywhere. Snapshots use a fixed host
(`offsite`) so retention groups correctly across pods.

**Ransomware protection.** Nightly jobs use SSH keys locked on the box to the
forced command `rclone serve restic --stdio --append-only <repo-dir>` (one key
and one directory per tier, so the key can neither read other directories nor
delete data). Proven 2026-11-15 on a throwaway repo: with the append-only key,
`forget --prune` and snapshot removal return HTTP 403 and all data remains
(`check --read-data` clean); with the admin key prune works. Only the weekly
prune/check jobs hold the admin key. The provider's own snapshots are the
second safeguard. NOTE: restic itself appends `serve restic --stdio` to the
`rclone.program` command, so the program string must end at `user@host` (append
key) or at `user@host rclone` (admin key, repo `rclone:<dir>`).

**Metrics and alerts.** Each successful run pushes to the Pushgateway
(`job=offsite-backup`, labels `tier=core|apps`, `kind=backup|prune|check`):
`offsite_backup_last_success_timestamp_seconds`, `_duration_seconds`,
`_bytes_added`, `_files_processed`, `_snapshots`, `_read_errors` (prune also
`_repo_bytes`). Nothing is pushed on failure, so staleness is visible.
Alerts: `OffsiteBackupStale` (apps >36h, core >60h), `OffsiteBackupJobFailed`,
`OffsiteBackupNeverSucceeded` (absent guard), `OffsiteBackupMaintenanceStale`,
`OffsiteBackupCheckMissing`, `OffsiteBackupContentsStale` (>9d).

**Dashboard and contents view.** Grafana dashboard `Off-site backup` (uid
`offsite-backup`, folder Backup, sidecar ConfigMap `offsite-backup-dashboard` in
`app/grafana-dashboard.yaml`): last-success age per tier and kind (prune/check
show "not run yet" until their first weekly run), firing `OffsiteBackup*`
alerts, read errors (must be 0), size added, snapshots, duration, files, repo
size, and the contents view. The contents view comes from the weekly CronJob
`offsite-backup-contents` (`app/contents.sh`): it uses the existing append-only
keys read-only (`--no-lock`, `--limit-download 20000`, 2Gi limit, no new
secrets, never the admin key), lists the latest snapshot per tier once and
pushes `offsite_backup_snapshot_info`, `_snapshot_time_seconds`,
`_snapshot_bytes` and `offsite_backup_path_bytes{tier,path}` (first 3 path
components, capped at 40 series plus `(other)`) with `kind=contents`. Run it
on demand with `kubectl create job -n backup x --from=cronjob/offsite-backup-contents`
(about 70 s). Alert `OffsiteBackupContentsStale` (>9d). Path names exist only
as metric labels in the cluster, never in git.

**Operations:**

```bash
# Seed or run now (one-off Job from the CronJob; apps first, then core)
kubectl create job -n backup offsite-run-apps --from=cronjob/offsite-backup-apps
kubectl logs -n backup job/offsite-run-apps -f
# Last runs
kubectl get cronjob,job -n backup | grep offsite
```

First run of each job initialises its repository if missing (idempotent).
Restic exit code 3 (some files unreadable) still records the snapshot but fails
the job on purpose.

**Restore (works with the cluster and NAS both gone).** Needed: the two repo
passwords, the SSH key for each tier (or the admin key) and the host key line,
plus the storage-box host and account. These live in the Secrets above and MUST
also be kept in the operator password manager.

```bash
# On any machine with restic >= 0.17 and ssh
restic -o rclone.program="ssh -p <port> -i <keyfile> -o UserKnownHostsFile=<known_hosts> \
  -o StrictHostKeyChecking=yes <user>@<host>" -r rclone: snapshots
restic ... -r rclone: restore latest --host offsite --tag <core|apps> \
  --target /restore --include <path-in-snapshot>
```

Restored files keep content and mtimes; ownership is the mount's uid/gid 1000
(sources are mounted with fixed ownership), so re-apply ownership on the target.
The Longhorn backup store is inside tier `core`: restore it to the NAS path of
the backup target, then restore volumes through Longhorn as usual.

**Restore drill record.** 2026-11-15 tier apps: 12 random files restored from
the latest snapshot to a scratch emptyDir and compared by sha256, 12/12 equal.
2026-11-16 tier core (snapshot `691077a4`, 1.27 TiB, first full seed): one-off Job
`offsite-restore-drill-core` in namespace `backup` with the append-only key,
`--limit-download 25000` (KiB/s), 2Gi memory limit, read-only source PVCs for
comparison. Restored 3 representative subtrees (Longhorn `system-backups`, one
small Longhorn volume dir, one document-share folder): 327 files / 62 MiB in 12 s,
sha256 against the live source 327/327 equal, 0 mismatches. Peak memory (cgroup
`memory.peak`) 509 MB for restore. Then `restic check --read-data-subset=1%
--no-lock` read 705 packs in 8 min 37 s at the 25 MB/s cap, no errors, peak
memory 652 MB. etcd leader-change counters unchanged across the drill (89/89/93,
`has_leader` 1 on all members). The job needs `CHOWN FOWNER DAC_OVERRIDE FSETID`
added back on top of `drop: ALL` for restore (lchown otherwise fails, restic
exits non-zero); read-only `check` needs no capabilities.
Gotcha: a seed run that ends without releasing its repo lock blocks any
exclusive-lock command (`check`, `prune`) until the lock goes stale (30 min
without refresh); `--no-lock` is acceptable for a read-only drill check. The
non-fatal "additional files found in the repo" note after the seed is cleaned by
the first weekly prune.
Repeat the drill after any change to sources, and at least quarterly.

**Memory.** The core backup job runs with a 4Gi limit and `GOMEMLIMIT=3500MiB`
(the seed's own peak was not captured). Measured peaks in the 2026-11-16 drill:
509 MB restore, 652 MB `check --read-data-subset=1%`.

---

## GitHub Mirror (monthly, bare mirrors plus metadata)

Since 2026-11-16. A second, independent copy of every GitHub repository of the
owner account, so a deleted repo, a compromised account or a GitHub outage does
not lose source history. Manifests: `kubernetes/apps/backup/github-mirror/`
(own Flux Kustomization), alerts:
`kubernetes/apps/monitoring/kube-prometheus-stack/app/github-mirror-alerts.yaml`,
dashboard panels: the `Off-site backup` dashboard (last row).

**What runs.** CronJob `github-mirror` (namespace `backup`, `0 2 1 * *` UTC,
`concurrencyPolicy: Forbid`, `activeDeadlineSeconds` 4h, `backoffLimit: 0`).
Image: the upstream `ghcr.io/josegonzalez/python-github-backup` image (alpine,
git, git-lfs), pinned by tag AND index digest; we never build it. Bump it like
any other image (Renovate/version-check). Options: bare mirrors
(`--repositories --bare --lfs`), `--private --fork`, wikis, issues (+comments,
events), pull requests (+comments, reviews, commits, details), labels,
milestones, releases. Not `--all`: that adds hooks (needs admin), security
advisories and discussions (need extra permissions) which a read-only PAT
cannot read, and an unreadable endpoint would fail the whole run. Release
assets, gists and starred repositories are not mirrored. Owner only, no orgs.

**NEVER prunes.** `--no-prune` on every fetch and no delete anywhere in the
scripts: a repository deleted or force-pushed away upstream stays in the
mirror. `verify.py` only counts such leftovers (`github_mirror_retained_repos`).

**Destination.** StorageClass `cifs-github-mirror` (source: the NAS backups
share, `subdir: github-mirror`, `Retain`, never `/`), PVC `github-mirror-data`
(dynamic; the CSI driver creates the directory on first provisioning).
Layout: `repositories/<name>/repository` (bare clone), `repositories/<name>/wiki`,
`repositories/<name>/{issues,pulls,...}` JSON. The nightly off-site core backup
includes the directory, so GitHub history also reaches the storage box.

**Token (operator action).** Secret `github-mirror-token`, key `GITHUB_TOKEN`
(SOPS, `kubernetes/apps/backup/github-mirror/app/secret.sops.yaml`). It ships
with a PLACEHOLDER value; the job refuses to run until it is a real fine-grained
PAT (`github_pat_...`) and exits non-zero with a clear FATAL message.

1. GitHub, Settings, Developer settings, Fine-grained tokens: new token,
   resource owner = the account, All repositories, repository permissions
   READ-ONLY: Contents, Metadata, Issues, Pull requests, Wiki (nothing else).
   Choose an expiry and put a reminder in the calendar; an expired token fails
   the job loudly (`GithubMirrorJobFailed`).
2. `sops kubernetes/apps/backup/github-mirror/app/secret.sops.yaml`, replace the
   value, save, commit and push (never paste the token anywhere else).
3. First run: `kubectl create job -n backup github-mirror-first --from=cronjob/github-mirror`
   and `kubectl logs -n backup job/github-mirror-first -f`. Expect
   `OK: github mirror complete` and a pushed-metrics line.

**Integrity checks per run (`verify.py`).** Lists the owner's repositories via
the API (private and forks included) and requires, for each, a bare clone that
passes `git fsck --connectivity-only` (wiki clone too). A repository the API
reports with size 0 may lack a clone (empty repo). The run fails if any
repository is missing or corrupt, if the API list cannot be fetched, or if
`github-backup` itself exits non-zero. The tool stores the authenticated clone
URL as the git remote; `verify.py` rewrites it to the token-free URL and fails
the run if a token is still present in any git config, because the mirror is
itself backed up off-site.

**Metrics and alerts** (Pushgateway `job=github-mirror`):
`github_mirror_last_success_timestamp_seconds` (only on a fully clean run),
`github_mirror_repos`, `github_mirror_bytes`, `github_mirror_failed_repos`,
`github_mirror_retained_repos`, `github_mirror_duration_seconds`. Alerts:
`GithubMirrorStale` (>35 d, warning), `GithubMirrorFailed`
(`failed_repos > 0`, critical), `GithubMirrorJobFailed` (CronJob ran without a
success, covers placeholder/expired token; critical), `GithubMirrorNeverSucceeded`
(absent guard, 3 d, warning; fires after deploy until the first run). Confirm
the rules loaded: `curl -s localhost:9090/api/v1/rules` via a Prometheus
port-forward and look for group `github-mirror`.

**Restore.**

```bash
# 1. Recover a repository: clone from the bare mirror (works offline from the NAS
#    copy or from a restic restore of the github-mirror directory)
git clone <mirror>/repositories/<name>/repository /tmp/restore-<name>
# 2. Push everything (all branches and tags) into a NEW empty repository
cd /tmp/restore-<name> && git push --mirror <new-remote-url>
# 3. LFS objects (if the repo used LFS): git lfs push --all <new-remote-url>
# 4. Issues / pull requests / releases are JSON under
#    repositories/<name>/issues, pulls, releases: re-import is MANUAL (GitHub has
#    no import API for them); use the JSON as the reference or script the
#    re-creation with the GitHub API.
# 5. Wiki: git push --mirror to <new-remote-url with .wiki.git> from repositories/<name>/wiki
```

**Monthly fire-drill (5 minutes, after the 1st).** Pick a random repository
and prove the mirror is usable, not just present:

```bash
R=$(ls <mirror>/repositories | shuf -n1)
git clone <mirror>/repositories/$R/repository /tmp/drill-$R
git -C /tmp/drill-$R fsck --full && git -C /tmp/drill-$R log --oneline | head -3
rm -rf /tmp/drill-$R
```

Also compare `github_mirror_repos` on the dashboard with the repository count
shown on the GitHub profile (empty repositories are the only legitimate gap).

**Rollback.** `git revert` the commit that added `github-mirror/`; Flux prunes
the CronJob, ConfigMap, PVC and StorageClass objects. The StorageClass is
`Retain`, so the mirrored data on the NAS stays untouched. Remove the
`/src/1/github-mirror` include path only if the directory is also removed
(a missing include path makes restic report a read error).

## UniFi Controller Backup (weekly copy of the gateway autobackup)

Since 2026-11-16. The UniFi OS gateway writes its `.unf` autobackups to its own
disk only; nothing copied them off. CronJob `unifi-backup` (namespace `backup`,
`15 5 * * 1` UTC, `concurrencyPolicy: Forbid`) copies the newest one to the NAS
backups share, directory `unifi` (StorageClass `cifs-unifi-backup`, `Retain`,
never `/`; the SMB CSI driver creates the directory when the PVC provisions).
The nightly off-site core job includes `/src/1/unifi` (read-only mount of the
backups share; restic keeps the history, the NAS keeps the newest 8 files).
Manifests: `kubernetes/apps/backup/unifi-backup/`, alerts
`kubernetes/apps/monitoring/kube-prometheus-stack/app/unifi-backup-alerts.yaml`.
No overlap with the off-site jobs (00:30/00:40 UTC), prune (Sun 04:30) or check
(Wed 04:30).

**API flow (stdlib Python, `backup.py`).** ONE `POST /api/auth/login` per run
(rate-limited endpoint: a 429 is terminal, never retried; see
`docs/sops/unifi-controller-rate-limit.md`), then with the session cookie and
CSRF header `POST /proxy/network/api/s/default/cmd/backup {"cmd":"list-backups"}`
and `GET /proxy/network/dl/autobackup/<file>.unf`. unifictl does not implement
backup listing, so these endpoints come from the UniFi Network application API,
not from a local source; they are verified against a stub only until the first
real run (see Residual risks below).

**Account role (feasibility, important).** `list-backups` is a POST command
(`cmd/backup`). The UniFi Network application rejects command POSTs for
read-only/Viewer roles, so a Viewer-only account is expected to get HTTP 403 and
the job then fails loudly with a message saying so. This was NOT verified against
the live controller (no login was attempted: rate limit). Least privilege that
should work: a dedicated local-only account with the Network application role
Limited Admin (or Admin) without Super Admin, remote access disabled. If the
first run logs a 403 on list-backups, raise the role one step and retry; do not
use the personal admin account.

**TLS.** The gateway certificate is self-signed. Chain verification is off and the
leaf certificate is pinned by SHA-256 fingerprint (`UNIFI_CERT_SHA256`), checked on
every connection before credentials are sent. A renewed certificate makes the job
fail with "TLS pin mismatch" until the pin is updated. Fingerprint:

```bash
openssl s_client -connect 192.168.30.1:443 </dev/null 2>/dev/null \
  | openssl x509 -noout -fingerprint -sha256 | sed 's/.*=//; s/://g' | tr 'A-F' 'a-f'
```

**Operator action: paste the credentials** (secret `unifi-backup-credentials`;
ships as `REPLACE_ME` placeholders, the job fails loudly until replaced):

```bash
cd /Users/mu/code/cberg-home-nextgen
mise exec -- sops kubernetes/apps/backup/unifi-backup/app/secret.sops.yaml
# replace UNIFI_USER, UNIFI_PASSWORD, UNIFI_CERT_SHA256, save, then commit + push
```

First run after Flux applies the change (single login, do not repeat on error):
`kubectl create job -n backup unifi-backup-first --from=cronjob/unifi-backup`
then `kubectl logs -n backup job/unifi-backup-first`.

**Validation per run.** File size above 100 KB; not an HTML/JSON error page; a
plain zip header, or AES-block-aligned high-entropy content (a `.unf` is an
encrypted zip, so the header check is structural, not a decrypt); size equals the
size listed by the gateway; written to `.tmp-<name>` and renamed; newest 8 `.unf`
kept. The newest autobackup on the gateway older than 9 days is a failure too
(copy is still stored).

**Metrics and alerts** (Pushgateway `job=unifi-backup`):
`unifi_backup_last_success_timestamp` (only on a fully clean run),
`unifi_backup_file_bytes`, `unifi_backup_last_run_ok`,
`unifi_backup_source_age_seconds`. Alerts: `UnifiBackupStale` (>9d),
`UnifiBackupRunFailed`, `UnifiBackupJobFailed` (CronJob state), and the
`UnifiBackupNeverSucceeded` absent() guard.

**Restore.** Copy the newest `.unf` from the NAS (`backups/unifi`) or from a restic
restore of `/src/1/unifi`, then UniFi OS Settings, System, Restore. See
`docs/sops/disaster-recovery.md` section 4.10.

**Rollback.** `git revert` the commit that added `unifi-backup/`; Flux prunes the
CronJob, ConfigMap, PVC and StorageClass. The StorageClass is `Retain`, so the NAS
data stays. Remove the `/src/1/unifi` include only if the directory is also
removed (a missing include path makes restic report a read error).

## Database Dumps (nightly logical dumps, 14 instances)

Since 2026-11-17. Longhorn volume backups are the only other copy of the
databases, and a corrupted volume is backed up as a corrupted volume. CronJobs
`db-dump-<instance>` (one per instance, namespace = the database's own, because a
Secret can only be referenced from its namespace) write logical dumps to the NAS
backups share, directory `db-dumps/<instance>/` (StorageClass `cifs-db-dumps`,
`Retain`, never `/`; one PVC `db-dumps` per namespace, mounted read-write only by
these Jobs). The nightly off-site core job includes `/src/1/db-dumps`, so restic
keeps the long history; the NAS keeps 7 daily + 4 weekly (Sunday) per database.
Manifests: `kubernetes/apps/backup/db-dumps/` (Flux Kustomizations
`db-dumps-common` and `db-dumps-<namespace>`), alerts
`kubernetes/apps/monitoring/kube-prometheus-stack/app/db-dumps-alerts.yaml`.

| Instance (service) | Namespace | Engine | Dumped how | Credentials |
|---|---|---|---|---|
| postgresql (shared fleet) | databases | Postgres 16 (pgvector) | pg_dump -Fc per database + globals | instance superuser Secret |
| superset-pg18 | databases | Postgres 18 | same | superuser Secret |
| mariadb | databases | MariaDB 13.1 | mariadb-dump per database + `--system=users` | root Secret (7 databases, several users) |
| paperclip-postgresql | ai | Postgres 18 | same | superuser |
| teslamate-postgres, traccar-postgres | home-automation | Postgres 18 | same | superuser |
| authentik-pg | kube-system | Postgres 18 | same | superuser |
| immich-postgres | media | Postgres 14 (vectorchord) | same, pg 18 client | superuser |
| affine-pg, sure-pg | office | Postgres 16 (pgvector) | same | superuser |
| mealie-pg, penpot-db | office | Postgres 18 | same | superuser |
| nextcloud-mariadb | office | MariaDB 11.8 | mariadb-dump per database | app user (ALL on its own database) |
| paperless-db | office | MariaDB 13.0 | mariadb-dump per database | app user (ALL on its own database) |

Schedule: one job every 3 minutes from 21:15 UTC (finished before 22:00), so
nothing overlaps the Longhorn backups (23:00), the off-site jobs (00:30/00:40),
prune (Sun 04:30), check (Wed 04:30) or unifi (Mon 05:15) and the nightly dump set
is inside the same night's off-site run. `concurrencyPolicy: Forbid`,
`nice -n 19`, 500m CPU / 512Mi limits, one database at a time. Pod layout: init
container `dump` (the engine image, `/scripts/db-dump.sh`) then container
`report` (python, pushes metrics, fails the Job when the dump failed).

**Integrity rules** (all in `base/db-dump.sh`): dump to `.tmp.*`, validate
(`pg_restore --list`; `gzip -t` plus the `Dump completed` marker for MariaDB),
rename, write the `.sha256` sidecar last (a file without sidecar is not a backup
and is ignored by rotation and metrics). A new dump smaller than 50 percent of the
previous good one is quarantined as `<ts>.suspect`, the run FAILS and nothing is
pruned. Pruning happens only after the new dump of that database is good. Postgres
instances also get `_globals` (roles incl. password hashes; MariaDB `mariadb`
gets `_users`). Dumps contain the data in clear text: treat the NAS share and the
off-site repository (encrypted) accordingly.

**Metrics and alerts** (Pushgateway `job=db-dumps`, group `dbinstance`):
`db_dump_last_success_timestamp_seconds` and `db_dump_size_bytes` (derived from the
newest good dump ON DISK, per `database`), `db_dump_last_run_ok`,
`db_dump_duration_seconds`, `db_dump_instance_last_run_ok`,
`db_dump_instance_run_timestamp_seconds`. Alerts: `DbDumpStale` (>36h per
database, critical), `DbDumpRunFailed`, `DbDumpInstanceFailed`, `DbDumpJobFailed`,
`DbDumpInstanceMissing` (count < 14 or absent; update the number when an instance
is added). A dropped database keeps its directory and will go stale: remove
`db-dumps/<instance>/<database>` on the NAS to retire it.

**Adding an instance.** Copy an existing `cronjob-*.yaml` in the namespace
directory (or add the namespace directory plus a `db-dumps-<ns>` entry in `ks.yaml`),
reference the existing Secret with `secretKeyRef`, pick a schedule 3 minutes
after the last one, and bump the count in `DbDumpInstanceMissing`. Flux postBuild
substitution is disabled on the script ConfigMap (the script uses shell `${var}`).

**Manual run** (one at a time, off-hours, check `etcd_server_leader_changes_seen_total`
is flat first): `kubectl create job -n <ns> db-dump-<instance>-m1 --from=cronjob/db-dump-<instance>`,
then `kubectl logs -n <ns> job/db-dump-<instance>-m1 -c dump`.

### Restore (always into a SCRATCH instance first)

```bash
# Locate: the NAS share backups/db-dumps/<instance>/<database>/<UTC ts>.daily.dump
# (or a restic restore of /src/1/db-dumps). Verify the sidecar first:
cd <dir> && sha256sum -c <file>.sha256

# Postgres (use a client of the same or newer major than the dump)
psql -U postgres -c 'create database <name>'
pg_restore -U postgres -d <name> --no-owner --exit-on-error <file>.dump   # --clean --if-exists to overwrite
zcat <ts>.daily.sql.gz | psql -U postgres        # _globals: roles first, then databases

# MariaDB (the dump contains CREATE DATABASE + USE)
zcat <ts>.daily.sql.gz | mariadb -uroot
zcat <ts>.daily.sql.gz | mariadb -uroot          # _users: users and grants (databases/mariadb)
```

For a real recovery stop the app first, restore into a fresh database (extensions
such as pgvector or vectorchord must exist in the target image), compare row
counts, then repoint or rename. Scratch pattern used for the proof: a pod with the
engine image, `emptyDir` data, `listen_addresses=localhost` / `--bind-address=127.0.0.1`,
the namespace's `db-dumps` PVC mounted `readOnly: true`, deleted afterwards.

### Restore proof (2026-11-17)

| Dump | Scratch target | Result |
|---|---|---|
| teslamate (Postgres 18, 92 MB dump, 665 MB database) | postgres:18.6-alpine, emptyDir | `pg_restore --exit-on-error` clean; sha256 OK; row counts identical to the live source: cars 1, drives 1828, charging_processes 391, positions 4887989; globals file contains the role |
| paperless (MariaDB 13.0, 44 MB) | mariadb:13.0.2, emptyDir | sha256 OK, import rc 0; counts identical: documents_document 1241, correspondent 189, tag 51, documenttype 13 |

Scratch pods deleted afterwards; no production database was written to.

**Rollback.** `git revert` the db-dumps commits; Flux prunes the CronJobs,
ConfigMaps and PVCs. The StorageClass is `Retain`, so the NAS data stays. Remove the
`/src/1/db-dumps` include only if the directory is also removed.

## Pre-Upgrade Backup Procedure

Before any significant cluster upgrade (Longhorn, Kubernetes, Talos):

```bash
# 1. Trigger manual backup of all volumes
kubectl create job --from=cronjob/daily-backup-all-volumes \
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
# 1. Is the CronJob enabled and scheduled? (owned by RecurringJob daily-backup-all-volumes)
kubectl get cronjob daily-backup-all-volumes -n storage

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

### Backup CR status can stay UNSYNCED — gate with the shared helper

The opposite failure also happens (F-a915dd47, 2026-09-26 and 2026-09-28): the
nightly RecurringJob's Backup CR is `state: Completed` but its status never
syncs — `status.volumeName` and `status.backupCreatedAt` empty,
`status.lastSyncedAt` null — for hours. Any gate that filters Backup CRs on
`status.volumeName` then silently reads the PREVIOUS night's backup (~26h) and
false-aborts. So neither `lastBackupAt` nor `Backup.status.volumeName` alone is
trustworthy.

**Every plan premise / pre-check / backup_gate uses the shared helper:**

```bash
python3 runbooks/longhorn-backup-age.py <volume> [<volume> ...] --max-hours 26
# -> "<vol> 2.6h FRESH via backup-cr-label backup=backup-... at=..."
# exit 0 = all FRESH, 1 = any STALE/NONE, 2 = lookup error (fails closed)
```

It takes the freshest CONFIRMED evidence of: a Completed CR by
`status.volumeName`; a Completed CR with unsynced status matched by its
`backup-volume` label; `Volume.status.lastBackup/lastBackupAt` only when the
BackupVolume's `lastBackupName` (or a Completed CR of that name) corroborates
it; the BackupVolume's `lastBackupName/lastBackupAt` when that CR exists.
Uncorroborated claims are printed as notes and never counted. Inline
`status.volumeName` freshness filters in active plans are rejected by
`runbooks/tests/test-longhorn-backup-age.py`.

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

---

## Version History

- `2026.11.17`: Database Dumps section: nightly logical dumps (pg_dump -Fc +
  globals, mariadb-dump) of 14 instances to the NAS `db-dumps` directory, carried
  off-site by the core job; restore commands and a scratch-restore proof.
- `2026.09.15`: CronJob name corrected everywhere — the object is
  `storage/daily-backup-all-volumes` (owned by the Longhorn RecurringJob of the
  same name); `backup-of-all-volumes` never existed and returned `NotFound` from
  Example 1, Test 1, the manual/pre-upgrade recipes and the Health Check.
  "Bind Restored Volume to Application" now covers the git-tracked
  `longhorn-static` case (immutable `volumeHandle`/`volumeName`, Flux re-apply,
  new PV name in `pv.yaml`, PVC name unchanged, storage-safety pre-flight) and
  the same-name restore's cascade-delete caveat.
- `2026.09.14`: off-site cloud copy + age-key custody attested (see
  `disaster-recovery.md`).
- earlier: `git log -- docs/sops/backup.md`.
