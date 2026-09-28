#!/bin/bash
# headless-dispatcher-keeper -- launchd half of "the headless cron dispatcher
# survives a Mac reboot / iTerm restart" (2026-09-28). Run by the LaunchAgent
# com.cberg.headless-dispatcher in the user's gui/<uid> domain -- NEVER root.
#
# Two halves, because the OpenClaw pod reaches runbooks/headless-dispatcher.py
# THROUGH iTerm (iterm2-harness resolve/send/screen) and so the dispatcher must
# live in an iTerm session with a tty:
#   * this keeper (launchd, KeepAlive): keeps iTerm itself running -- starts it
#     at login and relaunches it within one poll after it quits/crashes, via
#     `open -g -a iTerm` (LaunchServices; no Apple Events, no consent prompt);
#   * iterm2-headless-dispatcher-keeper.py (iTerm AutoLaunch script): keeps a
#     session running the dispatcher inside iTerm, using iTerm's own API.
# Driving iTerm from here with osascript was tried and rejected on 2026-09-28:
# creating a window needs a macOS Automation grant ("bash wants to control
# iTerm") that no one is present to click after an unattended reboot.
#
# It also logs dispatcher up/down transitions, so the keeper log is the one
# place to read "when was the cron path unavailable".
# `--check` prints the state and exits 0 (dispatcher running) / 1 (absent).

set -u

POLL_S="${KEEPER_POLL_S:-30}"

log() {
    printf '%s keeper: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

# Capture ps first, then match in-shell: a pipeline into grep would see the
# grep's own command line (pgrep -f self-match lesson).
dispatcher_pid() {
    local out line pid tty cmd
    out="$(ps -axo pid=,tty=,command=)"
    while IFS= read -r line; do
        read -r pid tty cmd <<<"$line"
        [[ "$tty" == "??" ]] && continue
        [[ "$cmd" == *"runbooks/headless-dispatcher.py"* ]] || continue
        [[ "$cmd" == *"--self-test"* ]] && continue
        echo "$pid"
        return 0
    done <<<"$out"
    return 1
}

iterm_running() {
    local out
    out="$(ps -axo comm=)"
    [[ "$out" == *"/iTerm.app/Contents/MacOS/iTerm2"* ]]
}

if [[ "${1:-}" == "--check" ]]; then
    iterm_running && echo "iTerm running" || echo "iTerm NOT running"
    if pid="$(dispatcher_pid)"; then
        echo "dispatcher running pid=${pid}"
        exit 0
    fi
    echo "dispatcher absent"
    exit 1
fi

if [[ "$(id -u)" == "0" ]]; then
    log "refusing to run as root (the dispatcher must run as the operator user)"
    exit 2
fi
log "start pid=$$ uid=$(id -u) poll=${POLL_S}s"

last=""
while true; do
    if ! iterm_running; then
        log "iTerm not running -- launching it (AutoLaunch starts the dispatcher)"
        open -g -a iTerm || log "open -a iTerm FAILED rc=$?"
    fi
    if pid="$(dispatcher_pid)"; then
        now="up:${pid}"
    else
        now="down"
    fi
    if [[ "$now" != "$last" ]]; then
        log "dispatcher ${now}"
        last="$now"
    fi
    sleep "$POLL_S"
done
