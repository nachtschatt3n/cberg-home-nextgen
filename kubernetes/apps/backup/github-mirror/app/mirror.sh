#!/bin/sh
# GitHub mirror runner (python-github-backup, bare mirrors + metadata JSON).
# Usage: mirror.sh   (env: GITHUB_OWNER, OUT_DIR, TOKEN_FILE, PUSHGATEWAY)
#
# Fails LOUD, never degrades: placeholder/empty token, a failed backup, a failed
# integrity check or a repository-count mismatch all exit non-zero. NEVER prunes:
# a repository deleted upstream stays in the mirror (--no-prune, no rm anywhere).
# Shell hygiene: bare $VAR only (Flux postBuild strips the brace form).
set -eu
umask 022

OWNER=$(printenv GITHUB_OWNER)
OUT=$(printenv OUT_DIR)
TOKEN_FILE=$(printenv TOKEN_FILE)
PUSH=$(printenv PUSHGATEWAY)
export HOME=/tmp
git config --global --add safe.directory '*'

# Token gate: the SOPS secret ships with a placeholder until the operator pastes
# a real fine-grained PAT. Refuse anything that is not one, with a clear message.
TOKEN=""
if [ -r "$TOKEN_FILE" ]; then
    TOKEN=$(tr -d ' \r\n\t' <"$TOKEN_FILE")
fi
case "$TOKEN" in
    github_pat_*) ;;
    *)
        echo "FATAL: GITHUB_TOKEN in secret github-mirror-token is empty or still the placeholder."
        echo "FATAL: create a fine-grained read-only PAT (all repositories; Contents, Metadata,"
        echo "FATAL: Issues, Pull requests, Wiki: read), paste it with 'sops' into"
        echo "FATAL: kubernetes/apps/backup/github-mirror/app/secret.sops.yaml and push."
        echo "FATAL: see docs/sops/backup.md, section GitHub Mirror."
        exit 1
        ;;
esac
unset TOKEN

mkdir -p "$OUT"
start=$(date +%s)

rc=0
github-backup "$OWNER" \
    --token-fine "file://$TOKEN_FILE" \
    --output-directory "$OUT" \
    --private --fork \
    --repositories --bare --lfs --no-prune --wikis \
    --issues --issue-comments --issue-events \
    --pulls --pull-comments --pull-reviews --pull-commits --pull-details \
    --labels --milestones --releases \
    --retries 5 || rc=$?
echo "github-backup exit=$rc"

# Verify even after a failed backup so the failure is measured, not just logged.
vrc=0
python3 /scripts/verify.py \
    --owner "$OWNER" --out "$OUT" --token-file "$TOKEN_FILE" \
    --start "$start" --backup-rc "$rc" --metrics /tmp/m.prom || vrc=$?
echo "verify exit=$vrc"

# POST replaces only the metric names it carries. Success timestamp is only
# present in the file when everything passed, so a failure leaves it ageing.
if [ -s /tmp/m.prom ]; then
    wget -q -O - -T 60 --post-file /tmp/m.prom "$PUSH/metrics/job/github-mirror" \
        && echo "pushed metrics" || echo "WARNING: pushgateway push failed"
fi

if [ "$rc" -ne 0 ] || [ "$vrc" -ne 0 ]; then
    echo "FAILED: github mirror run did not complete cleanly"
    exit 1
fi
echo "OK: github mirror complete"
