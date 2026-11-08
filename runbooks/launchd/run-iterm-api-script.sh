#!/bin/bash
# run-iterm-api-script.sh -- run an iTerm2 Python-API script under launchd.
#
# Why (2026-11-08): iTerm AutoLaunch starts a script ONLY when iTerm itself
# starts, and nothing restarts it when it dies. iTerm had been up since July, so
# the dispatcher keeper installed on 09-28 was never launched by AutoLaunch, and
# the manually started copy died on the 11-03 disk-full event. Nobody noticed
# until the 11-08 nightly + Sunday windows failed with HEADLESS_UNAVAILABLE.
# A LaunchAgent with KeepAlive supervises the same script instead; the iTerm API
# accepts the connection from a launchd child (verified 2026-11-08).
#
# usage: run-iterm-api-script.sh <script.py> [--while-healthy <health-url>]
#   --while-healthy  do NOT start the script while the URL answers 200 (another
#                    copy, e.g. an AutoLaunch one, already serves it); poll
#                    every 20 s and take over when it stops answering.
# Picks the newest iterm2env python that can `import iterm2` (iTerm replaces
# these directories when it upgrades its Python runtime; do not pin a version).
set -u
SCRIPT="${1:?usage: $0 <script.py> [--while-healthy URL]}"
shift
URL=""
if [[ "${1:-}" == "--while-healthy" ]]; then URL="${2:?url}"; fi

pick_python() {
    local d p
    for d in $(ls -d "$HOME"/.config/iterm2/AppSupport/iterm2env/versions/*/ 2>/dev/null | sort -rV); do
        p="${d}bin/python3"
        [[ -x "$p" ]] && "$p" -c 'import iterm2' 2>/dev/null && { echo "$p"; return 0; }
    done
    return 1
}

PY="$(pick_python)" || { echo "$(date -u +%FT%TZ) run-iterm-api-script: no iterm2env python with iterm2" >&2; exit 78; }

if [[ -n "$URL" ]]; then
    while [[ "$(curl -s -m 3 -o /dev/null -w '%{http_code}' "$URL")" == "200" ]]; do
        sleep 20
    done
fi
echo "$(date -u +%FT%TZ) run-iterm-api-script: exec $PY $SCRIPT"
exec "$PY" "$SCRIPT"
