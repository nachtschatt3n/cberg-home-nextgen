# TODO — `icloud-mail-backup` (Mail via IMAP)

**Status:** not built. Research first — see the open question below.
**Index:** [`../TODO.md`](../TODO.md)

## Mechanism

iCloud Mail is reachable over plain IMAP — no CloudKit, no web-API session, no
2FA dance:

- `imap.mail.me.com:993` SSL/TLS (no POP support)
- username = the iCloud address, or its local part
- **app-specific password mandatory** — Apple rejects the primary password
  because IMAP clients can't answer a 2FA challenge

Mail is one of the three categories Apple excludes from end-to-end encryption
for interoperability, so this **survives Advanced Data Protection** — unlike
Drive and Photos. Same credential class as
[`../icloud-dav-backup/TODO.md`](../icloud-dav-backup/TODO.md); consider
reusing the same app-specific password per account and mounting it from one
Secret.

## ❓ Open question — does either account even have an iCloud mailbox?

An Apple ID that *is* a third-party address (e.g. a Gmail address used as the
Apple ID) has **no `@icloud.com` mailbox** unless one was explicitly created.
Andrea's Apple ID is a third-party address, so there may be nothing to back up.

Check before building anything: sign in at icloud.com → is there a Mail app
tile, and what address does it send from?

Second question: **does this overlap with Nextcloud Mail?** The household mail
accounts are already configured there, and Nextcloud's own data is backed up.
If IMAP mail already lands in a backed-up Nextcloud store, a separate mirror may
be redundant — decide before building, not after.

## Design sketch (once the above is settled)

CronJob in `backup`, same shape as `icloud-dav-backup`:

- Tool: `imapsync` (mirror to another IMAP), `offlineimap` or `mbsync`
  (mirror to local Maildir). For a *backup*, Maildir on CIFS is simpler than
  standing up a second IMAP server — prefer `mbsync`.
- Storage: reuse `cifs-icloud-dav` with a `mail/` subdir, or a dedicated
  `cifs-icloud-mail` class. Decide based on expected size — mailboxes are
  much larger than vCards, so a separate class with its own quota is likely
  cleaner.
- Same mirror-vs-backup caveat as the DAV job: a mirror propagates deletions.
  Either snapshot periodically, or rely on Maildir's append-mostly nature and
  accept that deletions propagate — an explicit decision to record here.

## Checklist

- [ ] **Research:** confirm an iCloud mailbox exists for each account
- [ ] **Research:** decide overlap with Nextcloud Mail — build or skip
- [ ] Generate/reuse app-specific passwords
- [ ] Choose `mbsync` vs `imapsync` and record why
- [ ] Decide storage class + retention/snapshot policy
- [ ] Manifests, SOPS secret, register in `../kustomization.yaml`
- [ ] Health check: staleness of the last successful sync
- [ ] `docs/applications.md` + `README.md` inventory rows
