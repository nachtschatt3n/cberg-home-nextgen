# Off-site backup replacement plan

Status: approved direction (operator, 2026-11-15), not yet deployed.
Delete this file once the new backup is live and `docs/sops/backup.md` carries the procedure.

## Goal

Replace the NAS's built-in cloud upload with a versioned, encrypted, monitored
off-site backup that the cluster can observe and that has a tested restore.
Provider name, hostname and account stay in SOPS only (public repo).

## Decisions (operator, 2026-11-15)

- Tool: restic, run as CronJobs in the cluster. The NAS cannot run it.
- Target: a hosted SFTP storage box, 5 TB tier, budget ceiling 20 EUR/month.
- Scope now: the irreplaceable set below. Grow the box later for more.
- Deferred, not now: the `emulation` folder (about 1.1 TiB), both Time Machine
  bundles (about 1.8 TiB), the media library (about 3.7 TB), media downloads,
  camera recordings.

## Scope (measured 2026-11-15)

| Source (NAS share / folder) | Size |
|---|---|
| `backups/backupstore` (Longhorn backup store, covers all cluster PVs) | 522 GiB |
| `backups/icloud-backup` | 342 GiB |
| `backups/backup`, `backups/k8s`, `backups/teslamate` | 194 GiB |
| `backups/` laptop backup folder | 219 GiB |
| `nextcloud`, `paperless_ngx` | about 53 GB |
| `penpot`, `opencode` | under 1 GB |
| Total | about 1.3 TiB |

## Design

1. Namespace `backup`. One restic repository per tier (core data, small app data)
   so one failure does not block the other.
2. Sources are static SMB PVs mounted `ro`. Reuse the existing CIFS credentials;
   new PVs only, no change to existing StorageClasses or PVCs
   (`docs/sops/storage-safety.md` applies to anything touching them).
3. Transport: SFTP to a sub-account confined to one directory.
4. Ransomware protection: nightly job uses an append-only key (to be proven in a
   test before relying on it); prune runs weekly from a separate key; the
   provider's automatic snapshots are the second safeguard.
5. Schedule: nightly, after the 23:00 UTC Longhorn backup has finished.
   Retention: 7 daily, 4 weekly, 12 monthly.
6. Secrets: repository password and SSH keys in a `.sops.yaml` Secret, with a
   second copy in the operator's hosted password manager so a restore works with
   both cluster and NAS gone.
7. Monitoring: each run pushes last-success time, duration and added bytes to
   Pushgateway. Alerts: stale backup, failed run, and an `absent()` guard.
   The PrometheusRule carries `release: kube-prometheus-stack`.
8. Verification: weekly `restic check` with a data sample; monthly automated
   restore of known files compared by checksum.

## Rollout

1. Operator orders the storage box, creates the sub-account, hands over host and
   user (never in git unencrypted).
2. GitOps: namespace, `ro` PVs, Secret, CronJobs, alert rules.
3. Prove append-only access and prune from the second key on a throwaway repo.
4. Seed core data (about 10 hours at the measured uplink), then small app data.
5. Restore drill: one Longhorn volume backup, one document set, one iCloud folder.
6. Run in parallel with the old upload for 2 to 4 weeks; cancel the old one only
   after a clean drill.
7. Move the procedure into `docs/sops/backup.md` and the disaster-recovery SOP,
   then delete this file.

## Open points

- restic memory on the iCloud and Longhorn trees is unmeasured; start at a
  2 to 4 GiB limit and measure during the seed.
- The old upload has checksum verification off and no retention visible on the
  NAS; do not treat it as a verified copy during the parallel run.
- Time Machine bundles and the laptop folder had no off-site copy before this plan;
  only the laptop folder is added now.
