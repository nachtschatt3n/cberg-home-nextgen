#!/usr/bin/env bash
# Regression tests for the backup-freshness verdict in runbooks/health-check.sh.
#
# Guards the 2026-08-22 fix for inverted precedence: a PRESENT, SUCCEEDED backup
# Job used to short-circuit to "Backup system operational" with no age check at
# all, so a volume stale for a week was invisible while the Job sat inside its
# TTL. Case 5 below is that exact scenario and MUST report a major issue.
#
# Also guards the companion filter: detached volumes are excluded from the
# staleness max() (their content cannot change, so an old backup still captures
# all of it) -- without that, making the age authoritative would have instantly
# manufactured a false "backups stale" critical from two orphaned volumes.
#
# Run directly:  bash runbooks/tests/test-backup-freshness.sh
set -uo pipefail
HC="$(cd "$(dirname "$0")/.." && pwd)/health-check.sh"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT

# Extract the two functions under test verbatim so the test cannot drift.
python3 - "$HC" "$TMP/funcs.sh" <<'PY'
import sys
src, out = sys.argv[1], sys.argv[2]
s = open(src).read()
def grab(name, endmark):
    i = s.index(f"{name}() {{")
    j = s.index(endmark, i) + len(endmark)
    return s[i:j]
body  = grab("longhorn_backup_age_hours", '" 2>/dev/null || echo "NONE"\n}')
body += "\n\n" + grab("assess_backup_freshness", "\n}\n")
open(out, "w").write(body)
PY

MAJOR=(); MINOR=(); OK=(); WARN=()
log_success() { OK+=("$1"); }
log_warning() { WARN+=("$1"); }
add_major_issue() { MAJOR+=("$1"); }
add_minor_issue() { MINOR+=("$1"); }

# kubectl stub: serves crafted fixtures instead of the live cluster.
kubectl() {
    case "$*" in
        *"get volumes"*)  cat "$TMP/volumes.json" ;;
        *"get backups"*)  cat "$TMP/backups.json" ;;
        *"get job"*succeeded*) printf '%s' "$JOB_SUCCEEDED" ;;
        *) return 1 ;;
    esac
}
export -f kubectl 2>/dev/null || true
source "$TMP/funcs.sh"

mkfixture() {  # $1 = python expr building volume list
    python3 - "$1" > "$TMP/volumes.json" <<'PY'
import sys, json, datetime
now = datetime.datetime.now(datetime.timezone.utc)
def ago(h): return (now - datetime.timedelta(hours=h)).strftime('%Y-%m-%dT%H:%M:%SZ')
items = []
for name, state, age in eval(sys.argv[1]):
    v = {"metadata": {"name": name}, "status": {"state": state}}
    if age is not None:
        v["status"]["lastBackupAt"] = ago(age)
    items.append(v)
print(json.dumps({"items": items}))
PY
    echo '{"items": []}' > "$TMP/backups.json"
}

PASS=0; FAIL=0
check() { # name, expect_major(yes/no), grep-needle-or-empty
    local name="$1" expect="$2" needle="${3:-}"
    local got="no"; [ ${#MAJOR[@]} -gt 0 ] && got="yes"
    local ok=1
    [ "$got" == "$expect" ] || ok=0
    if [ -n "$needle" ]; then
        printf '%s\n' "${MAJOR[@]:-}" "${OK[@]:-}" | grep -qi -- "$needle" || ok=0
    fi
    if [ $ok -eq 1 ]; then
        echo "  PASS  $name"; PASS=$((PASS+1))
    else
        echo "  FAIL  $name (major=$got expected=$expect)"
        printf '        major: %s\n' "${MAJOR[@]:-<none>}"
        printf '        ok:    %s\n' "${OK[@]:-<none>}"
        FAIL=$((FAIL+1))
    fi
    MAJOR=(); MINOR=(); OK=(); WARN=()
}

echo "backup-freshness verdict tests"

mkfixture "[('a','attached',3),('b','attached',5)]"; JOB_SUCCEEDED=""
assess_backup_freshness "" >/dev/null
check "all attached fresh, job reaped -> pass" no "fresh"

mkfixture "[('a','attached',100)]"; JOB_SUCCEEDED=""
assess_backup_freshness "" >/dev/null
check "attached volume 100h stale, job reaped -> major" yes "stale"

mkfixture "[('a','attached',3),('orphan','detached',300)]"; JOB_SUCCEEDED=""
assess_backup_freshness "" >/dev/null
check "detached orphan 300h does NOT trip staleness" no "fresh"

mkfixture "[]"; JOB_SUCCEEDED=""
assess_backup_freshness "" >/dev/null
check "no backup evidence at all -> major" yes "absent"

# THE REGRESSION: succeeded Job must not excuse a stale volume.
mkfixture "[('a','attached',100)]"; JOB_SUCCEEDED="1"
assess_backup_freshness "daily-backup-all-volumes-29999" >/dev/null
check "SUCCEEDED job + 100h stale volume -> still major" yes "stale"

mkfixture "[('a','attached',3)]"; JOB_SUCCEEDED="1"
assess_backup_freshness "daily-backup-all-volumes-29999" >/dev/null
check "succeeded job + fresh volumes -> pass" no "fresh"

echo ""
echo "  $PASS passed, $FAIL failed"
[ $FAIL -eq 0 ]
