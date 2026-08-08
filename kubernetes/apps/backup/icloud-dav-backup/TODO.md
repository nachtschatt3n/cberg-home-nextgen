# TODO — `icloud-dav-backup` (Contacts + Calendars)

**Status:** not built. Design settled 2026-08-08, ready to implement.
**Covers:** iCloud Contacts and Calendars for *both* Apple IDs, one CronJob.
**Index:** [`../TODO.md`](../TODO.md)

## Why CardDAV/CalDAV and not icloud-docker

`icloud-docker` supports only `app`/`drive`/`photos` and has no open issue or PR
for contacts or calendars — it is not coming. `icloudpy`'s `ContactsService` /
`CalendarService` do work but return raw JSON, so using them means hand-writing
a vCard/iCal serializer plus incremental-sync logic. CardDAV/CalDAV is the
standard path and, critically, **survives Advanced Data Protection** — Apple
excludes Contacts and Calendars from E2EE for interoperability.

## Auth — one app-specific password per Apple ID

Generated at appleid.apple.com → Sign-In and Security → App-Specific Passwords.
Fully headless (no 2FA prompt at connect time) and revocable independently of
the Apple ID password and of the `icloud-docker` sessions. This is a deliberately *weaker, separate* credential from the one in
`icloud-docker-*-secrets`.

## Design

New app directory alongside this file:

| File | Content |
|---|---|
| `ks.yaml` | Flux Kustomization, name `icloud-dav-backup`, ns `backup` |
| `app/storageclass.yaml` | `cifs-icloud-dav`, subdir `icloud-backup/dav`, `reclaimPolicy: Retain`, Profile A mount options (copy from `../icloud-docker-mu/app/storageclass.yaml`) |
| `app/pvc.yaml` | `icloud-dav-backup-data`, 10Gi RWO — vCards/iCal are tiny |
| `app/configmap.sops.yaml` | vdirsyncer config; **SOPS-encrypted because it contains both Apple IDs** |
| `app/secret.sops.yaml` | `APP_PASSWORD_MU`, `APP_PASSWORD_ANDREA` |
| `app/cronjob.yaml` | daily, `concurrencyPolicy: Forbid` |

A **separate** CIFS StorageClass is required: the existing per-account data PVCs
are RWO and already bound to their app pods, so this CronJob cannot mount them.

### vdirsyncer config shape

Four pairs — `{mu,andrea}` × `{contacts,calendars}` — each remote:

```ini
[storage <name>_remote]
type = "carddav"                       # or "caldav"
url = "https://contacts.icloud.com/"   # or https://caldav.icloud.com/
username = "<apple-id>"
password.fetch = ["command", "/bin/cat", "/secrets/app-password-<acct>"]
```

with `collections = ["from b"]`, `conflict_resolution = "b wins"` (remote is
source of truth for a backup), and a `filesystem` local storage
(`fileext = ".vcf"` / `".ics"`).

Mount the Secret as **files, not env vars** — `password.fetch` reads a path,
which keeps the password out of the process environment.

### Mirror ≠ backup

vdirsyncer **mirrors**: a contact deleted in iCloud is deleted in the mirror.
That alone is not a backup. The CronJob does two steps:

1. `vdirsyncer discover` — it prompts per collection, so pipe `yes` for
   non-interactive use — then `vdirsyncer sync` into `/backup/mirror/`
2. `tar -czf /backup/snapshots/dav-$(date +%F).tar.gz -C /backup/mirror .`,
   pruning snapshots older than 90 days

Retention pruning: follow the existing pattern in
`../../ai/paperclip/app/backup-cleanup.yaml`.

### Image

`python:3.13-slim` + `pip install vdirsyncer` at container start.
**Slim, not alpine** — alpine has no manylinux wheels and would compile
dependencies on every run. There is no official vdirsyncer image; runtime-pip
precedent already exists in this repo (`superset`, `openclaw`, `mcpo`). If it
proves flaky, promote to a built image using the existing
`containers/sweep-dashboard/Dockerfile` + `.github/workflows/sweep-dashboard.yaml`
pattern.

## Checklist

- [ ] Generate an app-specific password per Apple ID (operator, appleid.apple.com)
- [ ] `ks.yaml`, `app/kustomization.yaml`
- [ ] `app/storageclass.yaml` — `cifs-icloud-dav`, and add it to the Profile A
      inventory in `docs/sops/cifs-mount-options.md` + the blast-radius list in
      `docs/sops/storage-safety.md`
- [ ] `app/pvc.yaml`
- [ ] `app/configmap.sops.yaml` + `app/secret.sops.yaml` — encrypt **in the repo
      path** with `sops -e -i`, never from `/tmp` (see CLAUDE.md SOPS rules)
- [ ] `app/cronjob.yaml` — sync + dated snapshot + 90-day prune
- [ ] Register in `../kustomization.yaml`
- [ ] Health check: add a `check_icloud_dav()` block to `runbooks/health-check.sh`
      — last CronJob completion within 48h, newest snapshot under 48h old.
      Finding prefix `icloud-dav-backup …`; add
      `("icloud-dav-backup", "icloud_docker")` to `_SUBSECTION_PREFIXES` in
      `runbooks/health-check.py` so it lands in the same report subsection
- [ ] `docs/applications.md` + `README.md` inventory rows
- [ ] Document each app-specific password in `docs/sops/backup.md` — what it
      grants and how to revoke it

## Verification

```bash
kubectl -n backup create job --from=cronjob/icloud-dav-backup dav-test
kubectl -n backup logs job/dav-test
# expect: non-zero .vcf and .ics counts per account, plus a dated snapshot tarball
```

## Known upstream limitations

From vdirsyncer's own iCloud docs — none block a read-only backup, but don't be
surprised by them: don't create collections via vdirsyncer (use an Apple
client); iCloud enforces a minimum collection-name length; vdirsyncer-created
calendars can't be used as tasklists.

**Reminders are deliberately out of scope** — Apple's CalDAV VTODO support is
quirky and upstream warns about it. Revisit separately if wanted.
