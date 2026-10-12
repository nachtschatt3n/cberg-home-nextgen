#!/usr/bin/env bash
# One-tap Codex/ChatGPT re-login for OpenClaw, from the Mac.
# The link + code arrive on Telegram; after you approve, the script in the pod
# restarts OpenClaw at a quiet moment and confirms on Telegram.
#   runbooks/codex-relogin.sh          # start
#   runbooks/codex-relogin.sh status   # token expiry + last relogin state
# Same thing from the phone: say "codex login" to Juno. The daily 09:15 check
# starts it by itself 2 days before expiry. Source: clawd scripts/codex_relogin.py
set -euo pipefail
kubectl exec -n ai deploy/openclaw -c app -- \
    python3 /home/node/clawd/scripts/codex_relogin.py "${1:-start}"
