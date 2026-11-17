#!/bin/sh
# Monthly automated restore proof for the off-site backup.
# For each tier: restore a RANDOM, per-source-stratified sample of files from the
# latest snapshot into a scratch emptyDir with `restic restore --verify` (hashes
# re-checked against the snapshot's own metadata), then compare every restored
# file whose live source copy is unchanged (same size and mtime) byte for byte.
# For core also: the newest UniFi autobackup in the snapshot passes the same
# structural check the backup job applies when it stores it.
#
# Append-only keys only (restore needs no write access to the repository), --no-lock,
# --limit-download. Nothing is written to the repository or to any source
# (sources are mounted read-only). NOT built here: the database-dump restore into
# a scratch engine (open gap, docs/sops/backup.md Continuous assurance).
#
# Public repo: no hosts, users, paths or share names in here. Mount numbers
# (/src/N) are neutral. Shell hygiene: bare $VAR only.
set -eu
umask 077

PUSH="http://prometheus-pushgateway.monitoring:9091/metrics/job/offsite-restore-proof"
SAMPLE_PER_MOUNT=$(printenv SAMPLE_PER_MOUNT || echo 6)
MAX_FILE_BYTES=$(printenv MAX_FILE_BYTES || echo 5242880)
MOUNTS_CORE=$(printenv MOUNTS_CORE || echo "1 2 3 6 7 8 9")
MOUNTS_APPS=$(printenv MOUNTS_APPS || echo "4 5")
UNIFI_PATH=$(printenv UNIFI_PATH || echo "/src/1/unifi")
MIN_COMPARED=$(printenv MIN_COMPARED || echo 5)
fail=0

mkdir -p /tmp/k /tmp/cache /restore
cp /secrets/ssh/KNOWN_HOSTS /tmp/k/known_hosts

push_metrics() {
    # $1 tier; body in /tmp/m.prom
    wget -q -O - -T 60 --post-file /tmp/m.prom "$PUSH/tier/$1" || {
        echo "FATAL: pushgateway rejected the metrics for tier=$1"
        return 1
    }
}

do_tier() {
    tier="$1"
    start=$(date +%s)
    case "$tier" in
        core) RESTIC_PASSWORD="$RESTIC_PASSWORD_CORE" ; key=SSH_KEY ; mounts="$MOUNTS_CORE" ;;
        apps) RESTIC_PASSWORD="$RESTIC_PASSWORD_APPS" ; key=SSH_KEY_APPS ; mounts="$MOUNTS_APPS" ;;
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
    jq -e 'length > 0' /tmp/snaps.json >/dev/null || { echo "FATAL: no snapshots for tier=$tier"; return 1; }
    sid=$(jq -r 'sort_by(.time) | last | .id' /tmp/snaps.json)
    echo "== tier=$tier restore proof of snapshot $(echo "$sid" | cut -c1-8)"

    rr ls --json --recursive "$sid" >/tmp/ls.json
    : >/tmp/sample.txt
    mount_fail=0
    for n in $mounts; do
        # eligible: regular files, 1 KiB .. MAX, no glob characters in the path
        # (restic --include-file treats entries as patterns).
        jq -r --arg pre "/src/$n/" --argjson max "$MAX_FILE_BYTES" \
            'select(.type == "file" and (.size // 0) >= 1024 and .size <= $max and (.path | startswith($pre)) and ((.path | test("[][*?\\\\]")) | not)) | .path' \
            /tmp/ls.json >/tmp/elig.txt
        ne=$(wc -l </tmp/elig.txt)
        if [ "$ne" -lt 1 ]; then
            echo "MOUNT $n: no eligible files in the snapshot (empty or missing source)"
            mount_fail=1
            continue
        fi
        awk -v k="$SAMPLE_PER_MOUNT" -v seed="$(date +%s)$n" 'BEGIN { srand(seed) }
            { c++; if (c <= k) a[c] = $0; else { j = int(rand() * c) + 1; if (j <= k) a[j] = $0 } }
            END { m = (c < k) ? c : k; for (i = 1; i <= m; i++) print a[i] }' /tmp/elig.txt >>/tmp/sample.txt
    done
    nsample=$(wc -l </tmp/sample.txt)
    echo "sampled $nsample files over mounts: $mounts"
    rm -f /tmp/ls.json /tmp/elig.txt
    if [ "$nsample" -lt 1 ]; then
        echo "FATAL: empty sample"
        return 1
    fi

    rm -rf /restore/*
    rc=0
    rr restore "$sid" --target /restore --include-file /tmp/sample.txt --verify || rc=$?
    echo "restic restore --verify exit=$rc"

    restored=0; missing=0; equal=0; mismatch=0; changed=0; bytes=0
    while IFS= read -r p; do
        f="/restore$p"
        if [ ! -f "$f" ]; then
            mn=${p#/src/}; mn=${mn%%/*}
            missing=$((missing + 1)); echo "MISSING after restore (mount $mn)"; continue
        fi
        restored=$((restored + 1))
        sz=$(stat -c %s "$f"); bytes=$((bytes + sz))
        if [ -f "$p" ] && [ "$(stat -c '%s %Y' "$p")" = "$(stat -c '%s %Y' "$f")" ]; then
            if cmp -s "$p" "$f"; then equal=$((equal + 1)); else mismatch=$((mismatch + 1)); echo "CONTENT MISMATCH in tier=$tier"; fi
        else
            changed=$((changed + 1))
        fi
    done </tmp/sample.txt
    compared=$((equal + mismatch))
    echo "restored=$restored missing=$missing compared=$compared equal=$equal mismatch=$mismatch changed_since_snapshot=$changed"

    ok=1
    [ "$rc" -eq 0 ] || ok=0
    [ "$missing" -eq 0 ] || ok=0
    [ "$mismatch" -eq 0 ] || ok=0
    [ "$mount_fail" -eq 0 ] || ok=0
    if [ "$compared" -lt "$MIN_COMPARED" ]; then
        # Not enough unchanged files to compare: the live-diff proof is
        # undetermined, which is a failure, never a pass (restic --verify alone
        # still passed, but the sample comparison is the part that catches a
        # wrong source).
        echo "FAIL: only $compared file(s) comparable against the live source (need $MIN_COMPARED)"
        ok=0
    fi

    unifi_ok=-1
    if [ "$tier" = core ]; then
        unifi_ok=0
        rr ls --json "$sid" "$UNIFI_PATH" >/tmp/unifi-ls.json || true
        upath=$(jq -r 'select(.type == "file" and (.name | endswith(".unf"))) | [.mtime, .path] | @tsv' /tmp/unifi-ls.json | sort | tail -1 | cut -f2)
        if [ -n "$upath" ]; then
            rm -rf /restore-unf; mkdir -p /restore-unf
            if rr restore "$sid" --target /restore-unf --include "$upath" --verify >/dev/null 2>&1 && [ -f "/restore-unf$upath" ]; then
                f="/restore-unf$upath"
                usz=$(stat -c %s "$f")
                head1=$(head -c 1 "$f")
                magic=$(head -c 4 "$f" | od -An -tx1 | tr -d ' \n')
                if [ "$usz" -gt 102400 ] && [ "$head1" != "<" ] && [ "$head1" != "{" ] && { [ "$magic" = "504b0304" ] || [ $((usz % 16)) -eq 0 ]; }; then
                    unifi_ok=1
                fi
                echo "unifi autobackup: size=$usz magic_zip=$([ "$magic" = 504b0304 ] && echo yes || echo no) ok=$unifi_ok"
            else
                echo "unifi autobackup: restore failed"
            fi
        else
            echo "unifi autobackup: no .unf in the snapshot"
        fi
        [ "$unifi_ok" -eq 1 ] || ok=0
    fi

    end=$(date +%s)
    {
        echo "# TYPE offsite_restore_proof_last_run_ok gauge"
        echo "offsite_restore_proof_last_run_ok $ok"
        echo "# TYPE offsite_restore_proof_last_run_timestamp_seconds gauge"
        echo "offsite_restore_proof_last_run_timestamp_seconds $end"
        echo "# TYPE offsite_restore_proof_files_restored gauge"
        echo "offsite_restore_proof_files_restored $restored"
        echo "# TYPE offsite_restore_proof_files_compared gauge"
        echo "offsite_restore_proof_files_compared $compared"
        echo "# TYPE offsite_restore_proof_files_mismatch gauge"
        echo "offsite_restore_proof_files_mismatch $mismatch"
        echo "# TYPE offsite_restore_proof_files_missing gauge"
        echo "offsite_restore_proof_files_missing $missing"
        echo "# TYPE offsite_restore_proof_bytes_restored gauge"
        echo "offsite_restore_proof_bytes_restored $bytes"
        echo "# TYPE offsite_restore_proof_duration_seconds gauge"
        echo "offsite_restore_proof_duration_seconds $((end - start))"
        if [ "$unifi_ok" -ge 0 ]; then
            echo "# TYPE offsite_restore_proof_unifi_ok gauge"
            echo "offsite_restore_proof_unifi_ok $unifi_ok"
        fi
        if [ "$ok" -eq 1 ]; then
            echo "# TYPE offsite_restore_proof_last_success_timestamp_seconds gauge"
            echo "offsite_restore_proof_last_success_timestamp_seconds $end"
        fi
    } >/tmp/m.prom
    push_metrics "$tier" || return 1
    echo "pushed restore-proof metrics tier=$tier ok=$ok"
    [ "$ok" -eq 1 ]
}

for t in core apps; do
    if ! do_tier "$t"; then
        echo "FAILED: restore proof tier=$t"
        fail=1
    fi
done
exit "$fail"
