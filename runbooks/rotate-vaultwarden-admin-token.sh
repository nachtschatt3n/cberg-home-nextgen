#!/usr/bin/env bash
# Rotate the Vaultwarden admin panel token. The cluster Secret stores only an
# Argon2id HASH (key `admin-token`); the plaintext token is shown to the operator
# once and is never written to a file, a commit or chat.
#   runbooks/rotate-vaultwarden-admin-token.sh          # plaintext goes to the clipboard (macOS pbcopy / wl-copy / xclip)
#   runbooks/rotate-vaultwarden-admin-token.sh --show   # print the plaintext in THIS terminal instead
# Run it in your own terminal, not through an agent session whose output is logged.
# Afterwards: commit the one file, push; Reloader rolls the pod (about 1 min downtime).
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"
F=kubernetes/apps/office/vaultwarden/app/secret.sops.yaml
SOPS="$(command -v sops || true)"
[ -n "$SOPS" ] || SOPS="$(ls -d "$HOME"/.local/share/mise/installs/aqua-getsops-sops/*/sops 2>/dev/null | sort -V | tail -1)"
[ -x "${SOPS:-}" ] || { echo "sops not found (try: mise install)"; exit 1; }
export SOPS_AGE_KEY_FILE="${SOPS_AGE_KEY_FILE:-$REPO/age.key}"
[ -r "$SOPS_AGE_KEY_FILE" ] || { echo "age key not readable: $SOPS_AGE_KEY_FILE (this machine cannot decrypt cluster secrets)"; exit 1; }
grep -q '^  admin-token: ENC\[' "$F" || { echo "$F has no encrypted admin-token key; aborting"; exit 1; }

VENV="$(mktemp -d)"
cleanup() { rm -rf "$VENV"; unset TOKEN HASH || true; }
trap cleanup EXIT
python3 -m venv "$VENV" >/dev/null
"$VENV/bin/pip" install --quiet argon2-cffi >/dev/null

TOKEN="$(openssl rand -base64 36 | tr -d '\n=+/' | cut -c1-40)"
[ "${#TOKEN}" -ge 32 ] || { echo "token generation failed"; exit 1; }
# Vaultwarden's own `owasp` preset: Argon2id, m=19456 KiB, t=2, p=1 (PHC string)
HASH="$(TOKEN="$TOKEN" "$VENV/bin/python" -c '
import os
from argon2 import PasswordHasher
ph = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
h = ph.hash(os.environ["TOKEN"])
assert ph.verify(h, os.environ["TOKEN"])
print(h)')"
case "$HASH" in '$argon2id$v=19$m=19456,t=2,p=1$'*) ;; *) echo "unexpected hash format"; exit 1;; esac

# --set edits only this key and re-encrypts only the changed value
"$SOPS" --set "[\"stringData\"][\"admin-token\"] \"$HASH\"" "$F"
if grep -q 'ENC\[' "$F" && ! grep -qF "$HASH" "$F" && ! grep -qF "$TOKEN" "$F" \
   && [ "$(grep -c '^  smtp-' "$F")" = 3 ]; then echo "encrypted OK: $F (smtp keys intact)"
else echo "CHECK FAILED on $F; run: git checkout -- $F"; exit 1; fi

if [ "${1:-}" = "--show" ]; then
  printf 'New admin token (copy it now, it is not stored anywhere): %s\n' "$TOKEN"
else
  if command -v pbcopy >/dev/null; then printf '%s' "$TOKEN" | pbcopy; echo "token copied to the clipboard (pbcopy)"
  elif command -v wl-copy >/dev/null; then printf '%s' "$TOKEN" | wl-copy; echo "token copied to the clipboard (wl-copy)"
  elif command -v xclip >/dev/null; then printf '%s' "$TOKEN" | xclip -selection clipboard; echo "token copied to the clipboard (xclip)"
  else echo "no clipboard tool found; rerun with --show"; git checkout -- "$F"; exit 1; fi
fi
echo "Save the token in your password manager NOW. Next: git commit --only $F -F <msg>; git push"
