#!/bin/sh
# Off-site backup "what is in it" exporter. READ-ONLY: uses the append-only
# keys (no admin key), --no-lock, --limit-download, and never writes to the
# repository. For the latest snapshot of each tier it pushes snapshot info and
# per-top-level-path sizes to the Pushgateway (kind=contents).
#
# Public repo: no hosts, users, paths or share names in here; everything
# environment-specific arrives via env (secretKeyRef) or mounted Secrets.
# Shell hygiene: bare $VAR only (Flux postBuild strips the brace form).
set -eu
umask 077

PUSH="http://prometheus-pushgateway.monitoring:9091/metrics/job/offsite-backup"
DEPTH="${PATH_DEPTH:-3}"
MAX_PATHS="${MAX_PATHS:-40}"

mkdir -p /tmp/k /tmp/cache
cp /secrets/ssh/KNOWN_HOSTS /tmp/k/known_hosts

do_tier() {
    tier="$1"
    case "$tier" in
        core) RESTIC_PASSWORD="$RESTIC_PASSWORD_CORE" ; key=SSH_KEY ;;
        apps) RESTIC_PASSWORD="$RESTIC_PASSWORD_APPS" ; key=SSH_KEY_APPS ;;
    esac
    export RESTIC_PASSWORD
    cp "/secrets/ssh/$key" "/tmp/k/id-$tier"
    chmod 600 "/tmp/k/id-$tier"
    # Append-only key: its forced command fixes the repo directory; the
    # program string must end at user@host (restic appends the rest).
    PROGRAM="ssh -F /dev/null -p $SFTP_PORT -i /tmp/k/id-$tier -o IdentitiesOnly=yes -o UserKnownHostsFile=/tmp/k/known_hosts -o StrictHostKeyChecking=yes -o BatchMode=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=10 $SFTP_USER@$SFTP_HOST"

    # shellcheck disable=SC2086
    rr() {
        restic --cache-dir /tmp/cache --no-lock --limit-download "$LIMIT_DOWNLOAD" \
            -o "rclone.program=$PROGRAM" -r "rclone:" "$@"
    }

    rr snapshots --json --host offsite --tag "$tier" >/tmp/snaps.json
    jq -e 'length > 0' /tmp/snaps.json >/dev/null
    jq -c 'sort_by(.time) | last | {id, time, hostname, paths: (.paths | length), total: (.summary.total_bytes_processed // 0)}' /tmp/snaps.json >/tmp/latest.json
    sid=$(jq -r '.id' /tmp/latest.json)
    echo "== tier=$tier latest snapshot $(jq -r '.id[0:8]' /tmp/latest.json): $(cat /tmp/latest.json)"

    # One recursive listing (tree metadata only, cached), streamed to disk.
    rr ls --json --recursive "$sid" >/tmp/ls.json
    echo "listing lines: $(wc -l </tmp/ls.json)"

    # Aggregate file sizes by the first DEPTH path components. Largest
    # MAX_PATHS are kept; the rest collapse into one "(other)" series.
    jq -n -r --argjson d "$DEPTH" --argjson max "$MAX_PATHS" --arg tier "$tier" '
        reduce (inputs | select(.type == "file")) as $f ({};
            ($f.path | split("/") | .[1:] | .[0:$d] | "/" + join("/")) as $k
            | .[$k] += ($f.size // 0))
        | to_entries | sort_by(-.value) as $all
        | ($all[0:$max]) as $top
        | ($all[$max:] | map(.value) | add // 0) as $rest
        | ($top + (if $rest > 0 then [{key: "(other)", value: $rest}] else [] end))[]
        | "offsite_backup_path_bytes{tier=\"\($tier)\",path=\(.key | @json)} \(.value)"
    ' /tmp/ls.json >/tmp/paths.prom
    n=$(wc -l </tmp/paths.prom)
    if [ "$n" -lt 1 ]; then
        echo "FATAL: no paths aggregated"
        return 1
    fi
    echo "path series: $n"
    cat /tmp/paths.prom

    {
        echo "# TYPE offsite_backup_snapshot_info gauge"
        jq -r --arg tier "$tier" '"offsite_backup_snapshot_info{tier=\"\($tier)\",snapshot_id=\"\(.id[0:8])\",host=\(.hostname | @json),snapshot_time=\"\(.time[0:19])\",paths=\"\(.paths)\"} 1"' /tmp/latest.json
        echo "# TYPE offsite_backup_snapshot_time_seconds gauge"
        jq -r '"offsite_backup_snapshot_time_seconds \(.time | sub("\\.[0-9]+"; "") | sub("\\+00:00$"; "Z") | fromdateiso8601? // 0)"' /tmp/latest.json
        echo "# TYPE offsite_backup_snapshot_bytes gauge"
        jq -r '"offsite_backup_snapshot_bytes \(.total)"' /tmp/latest.json
        echo "# TYPE offsite_backup_path_bytes gauge"
        cat /tmp/paths.prom
        echo "# TYPE offsite_backup_contents_last_success_timestamp_seconds gauge"
        echo "offsite_backup_contents_last_success_timestamp_seconds $(date +%s)"
    } >/tmp/m.prom
    wget -q -O - -T 60 --post-file /tmp/m.prom "$PUSH/tier/$tier/kind/contents"
    echo "pushed metrics kind=contents tier=$tier"
    rm -f /tmp/ls.json /tmp/paths.prom /tmp/m.prom
}

fail=0
for t in core apps; do
    if ! do_tier "$t"; then
        echo "FAILED: tier=$t"
        fail=1
    fi
done
exit "$fail"
