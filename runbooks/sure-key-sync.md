# Sure ↔ bank-sync API key auto-sync (Mac)

Keeps the MoneyMoney→Sure bank-sync (`sure-monmon`, runs on the Mac Mini) authenticated
across **monthly Sure API-key rotations**, by treating the `arag-web` SOPS secret as the
single source of truth for the shared `SURE_API_KEY` and auto-syncing it to the Mac.

## Why this exists

`sure-monmon` and the in-cluster `arag-web` app **share one Sure API key**. The key is
rotated monthly (`arag-sync-YYYY.MM`), and each rotation **revokes the previous key**.
`arag-web` survives because its key comes from a SOPS-encrypted k8s secret that is updated
on rotation. `sure-monmon` used to break (HTTP 401) every rotation because its key lived as
a frozen copy in `~/.sure/config.toml` on the Mac.

History: bank-sync 401'd on 2026-06-15 and again 2026-06-27, both immediately after a
rotation. This runbook documents the permanent fix.

## How it works

- **Source of truth:** `kubernetes/apps/office/arag-web/app/secret.sops.yaml` → `SURE_API_KEY`.
- The Mac holds the repo checkout **and** the SOPS age key, so it can decrypt that secret.
- A launchd agent runs a sync script every 30 min: it `git fetch`es + checks out just that
  one secret file from `origin/main`, decrypts it, and rewrites the `api_key` line in
  `~/.sure/config.toml` only when the value changed.
- bank-refresh (the 2-hourly Swift menu-bar app) reads `config.toml` as before — unchanged.
  The 30-min sync interval is well under the 2-hour refresh interval, so the key is always
  current before a sync runs.

## Components (all on the Mac Mini, user `mu`)

| Path | Role |
|---|---|
| `~/.sure/sync-key.sh` | the sync script (content below) |
| `~/Library/LaunchAgents/com.mathiasuhl.sure.keysync.plist` | launchd agent, 30-min `StartInterval` + `RunAtLoad` |
| `~/.sure/config.toml` | sure-monmon config; `api_key` line is what gets rewritten |
| `~/.sure/sync-key.log` | rotation events (only logs when the key actually changes) |
| `~/.sure/sync-key.{out,err}.log` | launchd stdout/stderr |
| `kubernetes/apps/office/arag-web/app/secret.sops.yaml` | source-of-truth secret (in this repo) |

### `~/.sure/sync-key.sh`

```sh
#!/bin/zsh
set -u
REPO=/Users/mu/code/cberg-home-nextgen
SECRET=kubernetes/apps/office/arag-web/app/secret.sops.yaml
CONFIG="$HOME/.sure/config.toml"
LOG="$HOME/.sure/sync-key.log"
MISE=/opt/homebrew/bin/mise
ts() { date '+%Y-%m-%dT%H:%M:%S%z'; }
cd "$REPO" 2>/dev/null || { echo "$(ts) ERROR: repo not found at $REPO" >>"$LOG"; exit 1; }
# best-effort refresh so a rotation done on another machine is picked up
"$MISE" exec -- git fetch --quiet origin main 2>/dev/null \
  && "$MISE" exec -- git checkout --quiet origin/main -- "$SECRET" 2>/dev/null
KEY=$("$MISE" exec -- sops -d "$SECRET" 2>>"$LOG" \
  | grep -iE 'SURE_API_KEY' | head -1 \
  | sed -E 's/.*SURE_API_KEY:?[= ]+"?([a-f0-9]+)"?.*/\1/')
if [ "${#KEY}" -ne 64 ]; then
  echo "$(ts) ERROR: extracted key length ${#KEY} (expected 64); leaving config untouched" >>"$LOG"; exit 1
fi
CURRENT=$(grep '^api_key' "$CONFIG" 2>/dev/null | sed -E 's/.*"(.*)".*/\1/')
[ "$KEY" = "$CURRENT" ] && exit 0
TMP=$(mktemp)
sed -E "s/^api_key = \"[a-f0-9]+\"/api_key = \"$KEY\"/" "$CONFIG" >"$TMP" && mv "$TMP" "$CONFIG"
echo "$(ts) rotated api_key -> ${KEY:0:8}... (was ${CURRENT:0:8}...)" >>"$LOG"
```

### launchd plist

`Label` `com.mathiasuhl.sure.keysync`, `ProgramArguments` → `/Users/mu/.sure/sync-key.sh`,
`StartInterval` `1800`, `RunAtLoad` `true`, stdout/err to `~/.sure/sync-key.{out,err}.log`.

Load: `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.mathiasuhl.sure.keysync.plist`

## Monthly rotation procedure (operator)

1. In Sure, create the new key `arag-sync-YYYY.MM` (read_write) and revoke the previous one
   — same as today.
2. Update `SURE_API_KEY` in `kubernetes/apps/office/arag-web/app/secret.sops.yaml`
   (`sops kubernetes/apps/office/arag-web/app/secret.sops.yaml`), commit + push. Flux rolls
   `arag-web` onto the new key.
3. **Nothing to do on the Mac.** Within 30 min the launchd agent pulls the new key into
   `~/.sure/config.toml`; bank-sync keeps running. (To apply immediately:
   `launchctl kickstart -k gui/$(id -u)/com.mathiasuhl.sure.keysync`.)

## Verification

```sh
launchctl list | grep keysync                 # registered; 2nd column = last exit (0 = ok)
tail ~/.sure/sync-key.log                      # last rotation events
grep '^api_key' ~/.sure/config.toml            # current key in use
# self-heal test: set a bad key, kick the agent, confirm it restores
```

## Troubleshooting

- **bank-sync 401 again:** confirm the agent is loaded (`launchctl list | grep keysync`),
  check `~/.sure/sync-key.err.log` for sops/git errors, then force a run with
  `launchctl kickstart -k gui/$(id -u)/com.mathiasuhl.sure.keysync`.
- **`sops` fails in the agent:** the agent runs `sops` via the absolute mise binary
  (`/opt/homebrew/bin/mise exec -- sops`) from the repo dir so the repo `.mise.toml` provides
  `SOPS_AGE_KEY_FILE`. If decryption fails, verify the age key still exists and the repo path
  is unchanged.

## Accepted caveats (operator-acknowledged)

These are deliberate and accepted; revisit only if the environment changes:

1. **Hardcoded paths.** The script hardcodes `REPO=/Users/mu/code/cberg-home-nextgen` and
   `MISE=/opt/homebrew/bin/mise`. If the repo is moved or Homebrew/mise relocates, update
   `~/.sure/sync-key.sh` accordingly.
2. **Depends on the local SOPS age key.** If the age key is rotated/moved, the agent can no
   longer decrypt the secret and the key will go stale (bank-sync 401). The fix is the same
   as any sops access issue on this host.
3. **Single shared key for two consumers.** `arag-web` and `sure-monmon` share one Sure key
   by design. The blast radius of revoking it is both integrations. Acceptable because the
   sync makes rotation a non-event; the alternative (a dedicated non-rotating key for
   sure-monmon) was declined in favor of one source of truth.
4. **Plaintext key on the Mac.** `~/.sure/config.toml` holds the key in plaintext (as it
   always has). It is a local user file on a single-user host, not committed to the repo.
5. **`git checkout origin/main -- <secret>`** touches only that one file in the working tree;
   it will not disturb other local repo work, but it does require the working copy of that
   path to be clean (it is, in normal operation).
