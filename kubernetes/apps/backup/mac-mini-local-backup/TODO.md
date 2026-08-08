# TODO — Messages + Voice Memos via the Mac mini (research)

**Status:** research only — nothing designed yet.
**Index:** [`../TODO.md`](../TODO.md)

> **No Kubernetes deployment lives here.** Both data types are unreachable from
> any server-side API; the only access path is a *signed-in Mac*. The agent
> would run on the Mac mini (192.168.30.111) and push to the NAS or an
> in-cluster destination. This directory exists to keep the open work next to
> its sibling backup jobs — it will likely never hold a HelmRelease.

## Why there is no cluster-side option

Both are end-to-end encrypted and exposed through no third-party API at any
price. Neither `icloudpy` nor `pyicloud` nor any DAV/IMAP endpoint touches
them. Anything that claims otherwise is forensic tooling operating on a local
device backup. So: read the local files on a Mac that is signed in and syncing,
or don't back them up.

## Messages

Messages in iCloud syncs to the local store on any signed-in Mac:

- `~/Library/Messages/chat.db` (SQLite) + `chat.db-wal`, `chat.db-shm`
- `~/Library/Messages/Attachments/`

Research questions:

- [ ] Is the Mac mini signed into iMessage, and with **which** Apple ID?
- [ ] **Blocker to confirm:** a Mac can be signed into only one Apple ID at a
      time. Does covering both accounts require a second machine, a second
      macOS user account with its own iCloud login, or is one account enough?
- [ ] The process reading `chat.db` needs **Full Disk Access** (TCC). How is
      that granted to a headless/LaunchDaemon context, and does it survive
      macOS updates?
- [ ] Copy safely — the DB is WAL-mode and live. Use
      `sqlite3 chat.db ".backup"` rather than `cp`, or snapshot after
      checkpointing. Never copy the file while Messages is writing.
- [ ] Is `chat.db` complete, or does macOS prune old messages locally when
      "Messages in iCloud" is on with limited local storage? This determines
      whether the backup is actually complete or just a recent window.
- [ ] Attachments can be large — size the destination before designing.

## Voice Memos

Not in iCloud Drive; syncs via a private CloudKit container, surfaced locally at:

- `~/Library/Group Containers/group.com.apple.VoiceMemos.shared/Recordings/`

Research questions:

- [ ] Confirm the path on the current macOS version and that recordings from
      the signed-in Apple ID actually land there.
- [ ] Are files fully downloaded, or dataless/evicted placeholders needing
      materialisation first? (Check for `.icloud` stubs / `brctl`.)
- [ ] Same TCC / Full Disk Access question as Messages.
- [ ] Metadata: recordings carry names and dates in a sidecar/plist — decide
      whether to preserve it or just copy the audio.

## Shared design questions

- [ ] **Delivery vehicle:** a `launchd` job on the Mac mini writing to the NAS
      SMB share, or `rsync`/`rclone` to an in-cluster destination? Note the
      Mac mini already hosts the ARAG scraper and Ollama — follow whatever
      scheduling pattern those use rather than inventing a third.
- [ ] **Retention:** snapshot-with-history, or plain mirror? Messages is
      append-mostly; Voice Memos can be deleted by the user, so a mirror would
      lose them.
- [ ] **Monitoring:** the sweep can't see a Mac-local job. How does staleness
      surface — a heartbeat file on the NAS that `health-check.sh` checks for
      freshness? That is the cheapest option and matches how the sweep already
      works.
- [ ] **Encryption at rest:** message history is the most sensitive data in
      this whole backup set. Decide whether it lands encrypted on the NAS
      rather than as a readable SQLite file on an SMB share.

## Not pursued

Keychain / stored logins (**we use Bitwarden**) and Safari bookmarks/history — both
are local-macOS-only for the same TCC reasons, and neither is wanted.
