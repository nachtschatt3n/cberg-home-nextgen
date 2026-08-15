# Apple account backup — coverage index

Status of every iCloud data type. **Scope is FINAL (operator decision
2026-08-15): Drive + Photos only, both Apple IDs.** Nothing else will be
built — do not resurface the closed rows as open work. The mechanism notes
are kept so the research doesn't have to be redone if the decision is ever
revisited.

`icloud-docker` supports exactly three config sections — `app`, `drive`,
`photos`. Everything below the first two rows would therefore have needed a
*different* mechanism, not more config. The `icloudpy` 0.9.0 library
underneath does ship working `contacts`/`calendar`/`reminders` services, but
they return raw JSON (not vCard/iCal) and icloud-docker never calls them —
not a viable shortcut.

| Data | Status | Mechanism (kept for reference) |
|---|---|---|
| iCloud Drive | ✅ live | `icloud-docker-{mu,andrea}` `drive:` |
| Photos | ✅ live | `icloud-docker-{mu,andrea}` `photos:` |
| Health | ✅ live (mu, device-side — see below) | Health Auto Export (iOS) → iCloud Drive → picked up by `drive:` |
| Contacts | ❌ closed 2026-08-15 | would be CardDAV `contacts.icloud.com` + vdirsyncer, app-specific password, mirror + dated snapshots (mirror alone propagates deletions); survives ADP |
| Calendars | ❌ closed 2026-08-15 | would be CalDAV `caldav.icloud.com` + vdirsyncer, same shape as Contacts |
| Mail | ❌ closed 2026-08-15 | would be IMAP `imap.mail.me.com:993` + app-specific password + `mbsync` Maildir; open question was whether the accounts even have an `@icloud.com` mailbox (both Apple IDs are third-party addresses) and overlap with Nextcloud Mail |
| Messages | ❌ closed 2026-08-15 | no server-side path (E2EE); only route is local `chat.db` on a signed-in Mac |
| Voice Memos | ❌ closed 2026-08-15 | no server-side path; local macOS group container on a signed-in Mac |
| Reminders | ❌ closed 2026-08-15 | CalDAV VTODO — Apple's tasklist support is quirky, upstream warns |
| Notes | ❌ closed 2026-08-15 | `pyicloud` ≥2.6 CloudKit `NotesService` — young code, no field reports |
| Keychain (stored logins) | ❌ not needed | **we use Bitwarden** |
| Safari bookmarks / history | ❌ not needed | — |

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

**Status: confirmed OFF on both Apple IDs (2026-08-08).** Re-check before adding
a third account, and treat any future "Drive/Photos suddenly stopped syncing,
credentials unchanged" as a possible ADP toggle before debugging anything else.

With ADP enabled, Apple's web servers hold no decryption keys. `icloud-docker`
authenticates exactly like iCloud.com, so **Drive and Photos sync stop working
entirely**. This is cryptographic, not a missing feature (`icloudpy#20`, open
since 2023, will not be fixed).

- **Breaks under ADP:** Drive, Photos, Notes, Find My, Voice Memos, Safari.
- **Survives ADP:** Contacts, Calendars, Mail — Apple excludes these three from
  E2EE for interoperability with the global mail/contacts/calendar systems.
- **Impossible either way:** Health, Keychain, Messages.

With the 2026-08-15 scope decision, the entire live backup surface
(Drive/Photos) depends on ADP staying off. Check ADP state before adding any
account to `icloud-docker`.

## References

- `docs/sops/icloud-docker-reauth.md` — 2FA session re-auth (sessions last ~30-60d)
- `docs/sops/backup.md` — backup SOP
- `docs/sops/storage-safety.md` — CIFS StorageClass blast radius
