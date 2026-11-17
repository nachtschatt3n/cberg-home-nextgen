#!/bin/sh
# Off-site backup continuous assurance: source canary + shrink detector.
# READ-ONLY: append-only keys, --no-lock, --limit-download; never writes to the
# repository and never reads file content (metadata listings only).
#
# Public repo: no hosts, users, paths or share names in here; everything
# environment-specific arrives via env (secretKeyRef) or mounted Secrets.
# Shell hygiene: bare $VAR only (Flux postBuild strips the brace form).
#
# Why a "canary" is NOT a file we write into the sources: the sources are
# mounted read-only on purpose and the media-class shares are not ours to
# litter. Instead the canary is a file that an EXISTING job already rewrites on
# a known cadence (nightly DB dumps, weekly UniFi autobackup, monthly GitHub
# mirror). If the latest snapshot holds a file from that tree whose mtime is
# fresh relative to the snapshot time, the whole chain NAS -> mount -> include
# list -> restic is proven alive. An empty mount, a wrong subdir or an
# unmounted share yields zero files or a stale mtime and fails LOUD.
#
# For trees with no known write cadence the signal is the shrink detector:
# files/bytes of the latest snapshot versus the previous one, per tier.
#
# Metrics go to the Pushgateway under job=offsite-assure (own group per tier),
# so the backup jobs' own metric groups are untouched.
set -eu
umask 077

PUSH="http://prometheus-pushgateway.monitoring:9091/metrics/job/offsite-assure"
# CANARIES: space separated "name=path=max_age_seconds" entries, core tier only.
CANARIES=$(printenv CANARIES || true)
fail=0
# RFC3339 with fractional seconds and any UTC offset -> epoch seconds (0 if unparsable).
TS_DEF='def ts: (capture("^(?<t>[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2})(\\.[0-9]+)?(?<z>Z|[+-][0-9]{2}:[0-9]{2})$")) as $c | (($c.t + "Z") | fromdateiso8601) - (if $c.z == "Z" then 0 else ((if $c.z[0:1] == "-" then -1 else 1 end) * (($c.z[1:3] | tonumber) * 3600 + ($c.z[4:6] | tonumber) * 60)) end);'

mkdir -p /tmp/k /tmp/cache
cp /secrets/ssh/KNOWN_HOSTS /tmp/k/known_hosts

do_tier() {
    tier="$1"
    case "$tier" in
        core) RESTIC_PASSWORD="$RESTIC_PASSWORD_CORE" ; key=SSH_KEY ;;
        apps) RESTIC_PASSWORD="$RESTIC_PASSWORD_APPS" ; key=SSH_KEY_APPS ;;
        *) echo "unknown tier"; return 1 ;;
    esac
    export RESTIC_PASSWORD
    cp "/secrets/ssh/$key" "/tmp/k/id-$tier"
    chmod 600 "/tmp/k/id-$tier"
    PROGRAM="ssh -F /dev/null -p $SFTP_PORT -i /tmp/k/id-$tier -o IdentitiesOnly=yes -o UserKnownHostsFile=/tmp/k/known_hosts -o StrictHostKeyChecking=yes -o BatchMode=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=10 $SFTP_USER@$SFTP_HOST"
    rr() {
        restic --cache-dir /tmp/cache --no-lock --limit-download "$LIMIT_DOWNLOAD" \
            -o "rclone.program=$PROGRAM" -r "rclone:" "$@"
    }

    rr snapshots --json --host offsite --tag "$tier" >/tmp/snaps.json
    # Fail closed: fewer than 2 snapshots or missing summaries means the
    # shrink detector could not measure. That is a failure, never a pass.
    jq -e 'length >= 2 and (sort_by(.time) | .[-2:] | all(.summary.total_files_processed != null and .summary.total_bytes_processed != null))' /tmp/snaps.json >/dev/null || {
        echo "FATAL: tier=$tier needs >=2 snapshots with summaries to measure shrink"
        return 1
    }
    jq -r "$TS_DEF"'sort_by(.time) | .[-2:] | "\(.[1].id[0:8]) \(.[1].summary.total_files_processed) \(.[0].summary.total_files_processed) \(.[1].summary.total_bytes_processed) \(.[0].summary.total_bytes_processed) \(.[1].time | ts)" ' /tmp/snaps.json >/tmp/delta.txt
    read -r sid files_now files_prev bytes_now bytes_prev snap_ts </tmp/delta.txt
    if [ "$files_prev" -le 0 ] || [ "$bytes_prev" -le 0 ]; then
        echo "FATAL: previous snapshot of tier=$tier is empty, ratio undefined"
        return 1
    fi
    now=$(date +%s)
    files_ratio=$(awk -v a="$files_now" -v b="$files_prev" 'BEGIN { printf "%.6f", a / b }')
    bytes_ratio=$(awk -v a="$bytes_now" -v b="$bytes_prev" 'BEGIN { printf "%.6f", a / b }')
    echo "== tier=$tier snapshot $sid files $files_now (prev $files_prev, ratio $files_ratio) bytes $bytes_now (prev $bytes_prev, ratio $bytes_ratio)"
    {
        echo "# TYPE offsite_assure_files_ratio gauge"
        echo "offsite_assure_files_ratio $files_ratio"
        echo "# TYPE offsite_assure_bytes_ratio gauge"
        echo "offsite_assure_bytes_ratio $bytes_ratio"
        echo "# TYPE offsite_assure_snapshot_files gauge"
        echo "offsite_assure_snapshot_files $files_now"
        echo "# TYPE offsite_assure_snapshot_age_seconds gauge"
        echo "offsite_assure_snapshot_age_seconds $((now - snap_ts))"
    } >/tmp/m.prom

    if [ "$tier" = core ] && [ -n "$CANARIES" ]; then
        # Full snapshot id (restic ls needs the id or a unique prefix; 8 chars is unique).
        for entry in $CANARIES; do
            name=${entry%%=*}
            rest=${entry#*=}
            cpath=${rest%%=*}
            maxage=${rest#*=}
            rr ls --json --recursive "$sid" "$cpath" >/tmp/canary-ls.json
            # files only; newest mtime; count; distinct first-level dirs holding a file
            # newer than (snapshot time - maxage).
            jq -n -r --argjson snap "$snap_ts" --argjson max "$maxage" --arg cpath "$cpath" "$TS_DEF"'
                [inputs | select(.type == "file")
                 | {m: (.mtime | ts? // 0),
                    d: (.path | ltrimstr($cpath + "/") | split("/") | .[0])}] as $f
                | ($f | length) as $n
                | (if $n > 0 then ($f | map(.m) | max) else 0 end) as $newest
                | ([$f[] | select(.m >= ($snap - $max)) | .d] | unique | length) as $fresh
                | "\($n) \($newest) \($fresh)"' /tmp/canary-ls.json >/tmp/canary.txt
            read -r cn cnewest cfresh </tmp/canary.txt
            if [ "$cn" -gt 0 ] && [ "$cnewest" -gt 0 ]; then cage=$((snap_ts - cnewest)); else cage=-1; fi
            if [ "$cn" -gt 0 ] && [ "$cage" -le "$maxage" ]; then cok=1; else cok=0; fi
            echo "canary $name: files=$cn newest_age_at_snapshot=${cage}s max=${maxage}s fresh_dirs=$cfresh ok=$cok"
            {
                echo "# TYPE offsite_assure_canary_ok gauge"
                echo "offsite_assure_canary_ok{canary=\"$name\"} $cok"
                echo "# TYPE offsite_assure_canary_files gauge"
                echo "offsite_assure_canary_files{canary=\"$name\"} $cn"
                echo "# TYPE offsite_assure_canary_age_seconds gauge"
                echo "offsite_assure_canary_age_seconds{canary=\"$name\"} $cage"
                echo "# TYPE offsite_assure_canary_max_age_seconds gauge"
                echo "offsite_assure_canary_max_age_seconds{canary=\"$name\"} $maxage"
                echo "# TYPE offsite_assure_canary_fresh_dirs gauge"
                echo "offsite_assure_canary_fresh_dirs{canary=\"$name\"} $cfresh"
            } >>/tmp/m.prom
            if [ "$cok" -ne 1 ]; then
                echo "CANARY FAILED: $name (empty or stale source in the latest snapshot)"
                fail=1
            fi
        done
    fi

    echo "# TYPE offsite_assure_last_success_timestamp_seconds gauge" >>/tmp/m.prom
    echo "offsite_assure_last_success_timestamp_seconds $(date +%s)" >>/tmp/m.prom
    wget -q -O - -T 60 --post-file /tmp/m.prom "$PUSH/tier/$tier"
    echo "pushed assurance metrics tier=$tier"
}

for t in core apps; do
    if ! do_tier "$t"; then
        echo "FAILED: tier=$t"
        fail=1
    fi
done
exit "$fail"
