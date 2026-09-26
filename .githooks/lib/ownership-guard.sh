#!/bin/bash
# ownership-guard.sh -- sourced by .githooks/pre-commit and .githooks/pre-rebase.
#
# Why: on 2026-09-25/26 a Claude Remote Control host (`claude rc`) had been
# started from a `sudo -s` root shell in an iTerm tab, so every remote session
# it spawned ran as ROOT in this worktree. Its writes left root-owned files,
# directories and .git objects behind (kubernetes/apps/ai/gods-eye-view/,
# a 0600 authentik configmap). Every other session then hit PermissionError in
# the pre-commit test suite and failed `git rebase`.
#
# Two checks:
#   1. Refuse to run as root at all (the cause). A git operation as root is
#      exactly what creates the foreign-owned objects.
#   2. Find paths in the worktree and .git NOT owned by the invoking user
#      (the symptom). Unreadable files always BLOCK (the pre-commit test
#      suite dies on them with PermissionError). Unwritable directories BLOCK
#      only in strict mode (pre-rebase: rebase/checkout must write into them);
#      in pre-commit they WARN, so unrelated commits are not held hostage.
#      Either way the one-line fix is printed.
#
# Usage: ownership_guard "<hook name>" [strict]  -> 0 (ok/warn) or 1 (block)

ownership_guard() {
    local hook="${1:-hook}" strict="${2:-}"
    local red='\033[0;31m' yellow='\033[1;33m' nc='\033[0m'
    local top gitdir me list f blocking=0 n=0

    top=$(git rev-parse --show-toplevel 2>/dev/null) || return 0
    gitdir=$(git rev-parse --absolute-git-dir 2>/dev/null) || return 0

    if [ "$(id -u)" -eq 0 ]; then
        echo -e "${red}━━━ ${hook} BLOCKED: running as root ━━━${nc}" >&2
        echo -e "${yellow}git as root in this worktree leaves root-owned files and .git objects" >&2
        echo -e "that break every other session (pre-commit PermissionError, rebase)." >&2
        echo -e "Likely cause: a Claude session / 'claude rc' started from 'sudo -s'." >&2
        echo -e "Exit the root shell and restart the session as your normal user.${nc}" >&2
        return 1
    fi

    me=$(id -un)
    # Worktree (excluding .git) plus the git dir; capped so a mass chown
    # accident cannot make the hook itself slow.
    list=$( { find "$top" -path "$top/.git" -prune -o ! -user "$me" -print 2>/dev/null
              find "$gitdir" ! -user "$me" -print 2>/dev/null; } | head -200 )
    [ -z "$list" ] && return 0

    while IFS= read -r f; do
        [ -z "$f" ] && continue
        n=$((n + 1))
        if [ ! -r "$f" ] || { [ -n "$strict" ] && [ -d "$f" ] && [ ! -w "$f" ]; }; then
            blocking=1
        fi
    done <<< "$list"

    if [ "$blocking" -eq 1 ]; then
        echo -e "${red}━━━ ${hook} BLOCKED: ${n} path(s) in the repo are not owned by ${me} ━━━${nc}" >&2
    else
        echo -e "${yellow}━━━ ${hook} WARNING: ${n} path(s) in the repo are not owned by ${me} ━━━${nc}" >&2
    fi
    echo "$list" | sed "s|^$top/||" | head -20 | sed 's/^/  /' >&2
    [ "$n" -gt 20 ] && echo "  ... ($n total, list capped at 200)" >&2
    echo -e "${yellow}Fix (operator, one line):  sudo chown -R ${me}:staff '${top}'${nc}" >&2
    echo -e "${yellow}Cause is usually a root session writing here -- check:  ps -axo user,pid,command | awk '\$1==\"root\"' | grep -i claude${nc}" >&2
    return "$blocking"
}
