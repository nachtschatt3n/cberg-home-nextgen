#!/bin/sh
# Off-site backup runner (restic over SSH to a hosted storage box).
# Usage: run.sh backup <tier> | prune | check
#
# Public repo: no hosts, users, paths or share names in here. Everything
# environment-specific arrives via env (secretKeyRef) or mounted Secrets.
# Shell hygiene: bare $VAR only (Flux postBuild strips the brace form).
set -eu
umask 077

MODE="$1"
TIER_ARG=""
if [ $# -ge 2 ]; then TIER_ARG="$2"; fi
REPO_CORE=$(printenv REPO_CORE || true)
REPO_APPS=$(printenv REPO_APPS || true)
PUSH="http://prometheus-pushgateway.monitoring:9091/metrics/job/offsite-backup"

mkdir -p /tmp/k /tmp/cache
cp /secrets/ssh/KNOWN_HOSTS /tmp/k/known_hosts
cp "/secrets/ssh/$KEY_NAME" /tmp/k/id
chmod 600 /tmp/k/id

SSH_BASE="ssh -F /dev/null -p $SFTP_PORT -i /tmp/k/id -o IdentitiesOnly=yes -o UserKnownHostsFile=/tmp/k/known_hosts -o StrictHostKeyChecking=yes -o BatchMode=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=10 $SFTP_USER@$SFTP_HOST"

# select_tier <core|apps>: sets RESTIC_PASSWORD, PROGRAM, REPO, FILES
select_tier() {
    case "$1" in
        core) RESTIC_PASSWORD="$RESTIC_PASSWORD_CORE" ; FILES=/sources/FILES_CORE ; ADMIN_REPO="$REPO_CORE" ;;
        apps) RESTIC_PASSWORD="$RESTIC_PASSWORD_APPS" ; FILES=/sources/FILES_APPS ; ADMIN_REPO="$REPO_APPS" ;;
        *) echo "unknown tier" ; return 1 ;;
    esac
    export RESTIC_PASSWORD
    if [ "$MODE" = backup ]; then
        # Append-only key: its forced command fixes the repo directory.
        PROGRAM="$SSH_BASE"
        REPO="rclone:"
    else
        # Admin key: restic appends "serve restic --stdio ..." to this.
        PROGRAM="$SSH_BASE rclone"
        REPO="rclone:$ADMIN_REPO"
    fi
}

r() {
    restic --cache-dir /tmp/cache -o "rclone.program=$PROGRAM" -r "$REPO" "$@"
}

# push <kind> <tier>: body already in /tmp/m.prom. POST only replaces the
# metric names it carries, so the other kinds' groups are untouched.
push() {
    wget -q -O - -T 60 --post-file /tmp/m.prom "$PUSH/tier/$2/kind/$1"
    echo "pushed metrics kind=$1 tier=$2"
}

ensure_repo() {
    if ! r cat config >/dev/null 2>&1; then
        echo "repository not initialised yet: running restic init"
        r init || return 1
    fi
}

do_backup() {
    tier="$1"
    select_tier "$tier" || return 1
    ensure_repo || return 1
    start=$(date +%s)
    rc=0
    RESTIC_PROGRESS_FPS=0.05 r backup --json --host offsite --tag "$tier" \
        --limit-upload "$LIMIT_UPLOAD" --exclude '*.sparsebundle/lock' --files-from "$FILES" >/tmp/backup.json || rc=$?
    jq -c 'select(.message_type=="summary")' /tmp/backup.json >/tmp/summary.json || true
    errs=$(jq -c 'select(.message_type=="error")' /tmp/backup.json | wc -l)
    echo "restic exit=$rc read_errors=$errs"
    if [ "$errs" -gt 0 ]; then
        jq -r 'select(.message_type=="error") | "read error: " + (.error.message // "?")' /tmp/backup.json | head -20
    fi
    if [ ! -s /tmp/summary.json ]; then
        echo "FATAL: no summary from restic backup"
        return 1
    fi
    jq -c '{snapshot_id, files_new, files_changed, files_unmodified, data_added, total_files_processed, total_bytes_processed}' /tmp/summary.json
    added=$(jq -r '.data_added' /tmp/summary.json)
    files=$(jq -r '.total_files_processed' /tmp/summary.json)
    snaps=$(r snapshots --json --host offsite --tag "$tier" | jq 'length')
    end=$(date +%s)
    {
        echo "# TYPE offsite_backup_last_success_timestamp_seconds gauge"
        echo "offsite_backup_last_success_timestamp_seconds $end"
        echo "# TYPE offsite_backup_duration_seconds gauge"
        echo "offsite_backup_duration_seconds $((end - start))"
        echo "# TYPE offsite_backup_bytes_added gauge"
        echo "offsite_backup_bytes_added $added"
        echo "# TYPE offsite_backup_files_processed gauge"
        echo "offsite_backup_files_processed $files"
        echo "# TYPE offsite_backup_snapshots gauge"
        echo "offsite_backup_snapshots $snaps"
        echo "# TYPE offsite_backup_read_errors gauge"
        echo "offsite_backup_read_errors $errs"
    } >/tmp/m.prom
    # A snapshot exists for rc 0 and rc 3 (some files unreadable): record the
    # success, but still fail the job on rc 3 so it is noisy, never silent.
    if [ "$rc" -ne 0 ] && [ "$rc" -ne 3 ]; then
        return 1
    fi
    push backup "$tier" || return 1
    [ "$rc" -eq 0 ] || return 1
}

do_prune() {
    tier="$1"
    select_tier "$tier" || return 1
    start=$(date +%s)
    r unlock || return 1
    r forget --host offsite --group-by host --keep-daily 7 --keep-weekly 4 --keep-monthly 12 --prune || return 1
    size=$(r stats --mode raw-data --json | jq -r '.total_size') || return 1
    snaps=$(r snapshots --json --host offsite | jq 'length') || return 1
    end=$(date +%s)
    {
        echo "# TYPE offsite_backup_last_success_timestamp_seconds gauge"
        echo "offsite_backup_last_success_timestamp_seconds $end"
        echo "# TYPE offsite_backup_duration_seconds gauge"
        echo "offsite_backup_duration_seconds $((end - start))"
        echo "# TYPE offsite_backup_repo_bytes gauge"
        echo "offsite_backup_repo_bytes $size"
        echo "# TYPE offsite_backup_snapshots gauge"
        echo "offsite_backup_snapshots $snaps"
    } >/tmp/m.prom
    push prune "$tier"
}

do_check() {
    tier="$1"
    select_tier "$tier" || return 1
    start=$(date +%s)
    # Clear stale locks only (restic never removes a live one), as prune does.
    r unlock || return 1
    r check --read-data-subset=5% || return 1
    end=$(date +%s)
    {
        echo "# TYPE offsite_backup_last_success_timestamp_seconds gauge"
        echo "offsite_backup_last_success_timestamp_seconds $end"
        echo "# TYPE offsite_backup_duration_seconds gauge"
        echo "offsite_backup_duration_seconds $((end - start))"
    } >/tmp/m.prom
    push check "$tier"
}

case "$MODE" in
    backup)
        do_backup "$TIER_ARG"
        ;;
    prune|check)
        fail=0
        for t in core apps; do
            echo "== $MODE tier=$t"
            if ! "do_$MODE" "$t"; then
                echo "FAILED: $MODE tier=$t"
                fail=1
            fi
        done
        exit "$fail"
        ;;
    *)
        echo "usage: run.sh backup <tier> | prune | check"
        exit 2
        ;;
esac
