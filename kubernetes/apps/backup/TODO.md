# Apple account backup — coverage index

Status of every iCloud data type, and where the open work lives.
Decisions recorded 2026-08-08. Update this table when anything ships.

`icloud-docker` supports exactly three config sections — `app`, `drive`,
`photos`. Everything below the first two rows therefore needs a *different*
mechanism, not more config. The `icloudpy` 0.9.0 library underneath does ship
working `contacts`/`calendar`/`reminders` services, but they return raw JSON
(not vCard/iCal) and icloud-docker never calls them — not a viable shortcut.

| Data | Status | Mechanism | Where |
|---|---|---|---|
| iCloud Drive | ✅ live | `icloud-docker-*` `drive:` | `icloud-docker-mu/`, `icloud-docker-andrea/` |
| Photos | ✅ live | `icloud-docker-*` `photos:` | same |
| Health | ✅ live — **excluded from further work** | Health Auto Export (iOS) → iCloud Drive → picked up by `drive:` | see below |
| Contacts | 📋 todo | CardDAV + vdirsyncer | [`icloud-dav-backup/TODO.md`](icloud-dav-backup/TODO.md) |
| Calendars | 📋 todo | CalDAV + vdirsyncer | same |
| Mail | 📋 todo | IMAP + app-specific password | [`icloud-mail-backup/TODO.md`](icloud-mail-backup/TODO.md) |
| Messages | 🔬 research | local macOS `chat.db` on the Mac mini | [`mac-mini-local-backup/TODO.md`](mac-mini-local-backup/TODO.md) |
| Voice Memos | 🔬 research | local macOS container on the Mac mini | same |
| Reminders | ⏸️ deferred | CalDAV VTODO — Apple's tasklist support is quirky, upstream warns | — |
| Notes | ⏸️ deferred | `pyicloud` ≥2.6 CloudKit `NotesService` — young code, no field reports | — |
| Keychain (stored logins) | ❌ not needed | **we use Bitwarden** | — |
| Safari bookmarks / history | ❌ not needed | — | — |

## Health — why it's excluded

Not because it's unsolved: it already works, on the `mu` account, and was never
written down. There is no server-side Health API (Health is end-to-end
encrypted by default, even without ADP), so the only automatable route is a
device-side push into iCloud Drive, which the existing `drive:` sync then
picks up. Live evidence in the `mu` pod:

```
/icloud/drive/Auto Export/AutoSync/HealthMetrics
/icloud/drive/Auto Export/New Automation/HealthAutoExport-YYYY-MM-DD.json
```

That is the **Health Auto Export – JSON+CSV** iOS app (App Store id
`1115567069`; the iCloud Drive export target is a paid tier). It also explains
commit `a83008fb` — Apple was 503-throttling that `.hae` folder on every 5-min
Drive poll, hence `drive.sync_interval: 3600`.

Caveat worth knowing even though no work is planned: **iOS scheduling is
best-effort**. Apps cannot read HealthKit while the device is locked and iOS
won't guarantee background execution at a set time, so gaps are normal and
silent. To cover a second account, install the same app and point it at the
same Drive path — no cluster changes.

## Advanced Data Protection — the constraint behind this whole table

With ADP enabled, Apple's web servers hold no decryption keys. `icloud-docker`
authenticates exactly like iCloud.com, so **Drive and Photos sync stop working
entirely**. This is cryptographic, not a missing feature (`icloudpy#20`, open
since 2023, will not be fixed).

- **Breaks under ADP:** Drive, Photos, Notes, Find My, Voice Memos, Safari.
- **Survives ADP:** Contacts, Calendars, Mail — Apple excludes these three from
  E2EE for interoperability with the global mail/contacts/calendar systems.
- **Impossible either way:** Health, Keychain, Messages.

So the CardDAV/CalDAV/IMAP work below is the ADP-proof part of the backup
surface. Check ADP state before adding any account to `icloud-docker`.

## References

- `docs/sops/icloud-docker-reauth.md` — 2FA session re-auth (sessions last ~30-60d)
- `docs/sops/backup.md` — backup SOP
- `docs/sops/storage-safety.md` — CIFS StorageClass blast radius
