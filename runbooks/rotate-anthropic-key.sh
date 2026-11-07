#!/usr/bin/env bash
# Create or rotate the SOPS-encrypted `anthropic-api-key` Secret in BOTH namespaces.
# See docs/sops/anthropic-api-key.md. The key is read silently from the terminal;
# it never touches chat, shell history or a plaintext file (a failed run removes
# any unencrypted file it wrote).
#   runbooks/rotate-anthropic-key.sh           # rotate (files must already exist)
#   runbooks/rotate-anthropic-key.sh --create  # first-time create (files must not exist)
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"
MODE="rotate"; [ "${1:-}" = "--create" ] && MODE="create"
FILES=(
  kubernetes/apps/ai/openclaw/app/anthropic-api-key.sops.yaml                                      # ns ai (OpenClaw, Open WebUI)
  kubernetes/apps/my-software-development/opencode-andreamosteller/app/anthropic-api-key.sops.yaml  # ns my-software-development
)
# sops is a mise tool and is often not on PATH in a plain terminal
SOPS="$(command -v sops || true)"
[ -n "$SOPS" ] || SOPS="$(ls -d "$HOME"/.local/share/mise/installs/aqua-getsops-sops/*/sops 2>/dev/null | sort -V | tail -1)"
[ -x "${SOPS:-}" ] || { echo "sops not found (try: mise install)"; exit 1; }
export SOPS_AGE_KEY_FILE="${SOPS_AGE_KEY_FILE:-$REPO/age.key}"
[ -r "$SOPS_AGE_KEY_FILE" ] || { echo "age key not readable: $SOPS_AGE_KEY_FILE"; exit 1; }
for f in "${FILES[@]}"; do
  if [ "$MODE" = create ]; then [ ! -e "$f" ] || { echo "$f exists; run without --create to rotate"; exit 1; }
  else [ -e "$f" ] || { echo "$f missing; run with --create first"; exit 1; }; fi
done
TMPS=()
cleanup() { for t in "${TMPS[@]:-}"; do [ -n "$t" ] && rm -f "$t"; done
  if [ "$MODE" = create ]; then for f in "${FILES[@]}"; do [ -e "$f" ] && ! grep -q 'ENC\[' "$f" && rm -f "$f"; done; fi
  unset KEY || true; }
trap cleanup EXIT
printf 'Paste the Anthropic API key (input hidden), then Enter: '
read -rs KEY; echo
[ -n "$KEY" ] || { echo "empty key, aborting"; exit 1; }
for f in "${FILES[@]}"; do
  # write next to the target so the path-based .sops.yaml creation rule matches
  t="$(dirname "$f")/.tmp-anthropic-key.sops.yaml"; TMPS+=("$t")
  printf 'apiVersion: v1\nkind: Secret\nmetadata:\n  name: anthropic-api-key\nstringData:\n  ANTHROPIC_API_KEY: "%s"\n' "$KEY" > "$t"
  "$SOPS" -e -i "$t"
  if grep -q 'ENC\[' "$t" && ! grep -qF "$KEY" "$t"; then mv "$t" "$f"; echo "encrypted OK: $f"
  else echo "ENCRYPTION CHECK FAILED: $f"; exit 1; fi
done
echo "Done. Review with git diff, commit with git commit --only <both files>, push, then follow docs/sops/anthropic-api-key.md section 4 step 3 (restart consumers)."
