#!/bin/sh
# Logical dump of ONE database instance to the NAS backups share (subdir db-dumps).
#
# ENGINE=postgres : pg_dump -Fc per database + pg_dumpall --globals-only
# ENGINE=mariadb  : mariadb-dump --single-transaction --routines --events per
#                   database (+ --system=users when DUMP_USERS=1)
#
# Layout:  $DUMP_ROOT/$INSTANCE/<database>/<UTC ts>.daily.<ext>[.sha256]
#          (Sundays additionally <UTC ts>.weekly.<ext>[.sha256])
#          $DUMP_ROOT/$INSTANCE/_globals (postgres) or _users (mariadb)
# A dump is GOOD only when its .sha256 sidecar exists (written last, after the
# content validated), so a half-written file is never treated as a backup.
#
# Never degrades: any failure marks the run FAILED (result file + metrics), the
# previous good dumps are never pruned on a failed or suspiciously small run
# (new < MIN_RATIO percent of the previous good one is quarantined as *.suspect).
# This script always exits 0 once it reaches the end, because the report
# container (next in the pod) pushes the metrics and then fails the Job from the
# result file. An unexpected crash exits non-zero and fails the Job directly.
#
# Metrics are derived from what is ON DISK (newest good dump per database), not
# from this run, so a failed run can never freeze a healthy-looking timestamp.
# Secrets arrive only via env (PGPASSWORD / MYSQL_PWD) and are never printed.
set -u
umask 077

ENGINE=${ENGINE:?ENGINE required}
INSTANCE=${INSTANCE:?INSTANCE required}
DB_HOST=${DB_HOST:?DB_HOST required}
DB_PORT=${DB_PORT:?DB_PORT required}
DB_USER=${DB_USER:?DB_USER required}
DB_PASSWORD=${DB_PASSWORD:?DB_PASSWORD required}
DUMP_ROOT=${DUMP_ROOT:-/dumps}
WORK_DIR=${WORK_DIR:-/work}
KEEP_DAILY=${KEEP_DAILY:-7}
KEEP_WEEKLY=${KEEP_WEEKLY:-4}
MIN_RATIO=${MIN_RATIO:-50}
MIN_PREV_BYTES=${MIN_PREV_BYTES:-65536}
DUMP_USERS=${DUMP_USERS:-0}

OUT="$DUMP_ROOT/$INSTANCE"
TS=$(date -u +%Y%m%dT%H%M%SZ)
DOW=$(date -u +%u)
FAILED=""
RUN_FILE="$WORK_DIR/run.tsv"      # database <TAB> ok(1/0) <TAB> duration_s
: > "$RUN_FILE"

log() { printf '[%s] %s\n' "$(date -u +%FT%TZ)" "$*"; }

# ---- engine setup -----------------------------------------------------------
case "$ENGINE" in
postgres)
    export PGHOST="$DB_HOST" PGPORT="$DB_PORT" PGUSER="$DB_USER" PGPASSWORD="$DB_PASSWORD"
    export PGCONNECT_TIMEOUT=15 PGAPPNAME=db-dumps
    EXT=dump
    ;;
mariadb)
    export MYSQL_PWD="$DB_PASSWORD"
    EXT=sql.gz
    MYSQL_ARGS="--host=$DB_HOST --port=$DB_PORT --user=$DB_USER --skip-ssl"
    ;;
*)
    log "FATAL unknown ENGINE=$ENGINE"
    exit 2
    ;;
esac

mkdir -p "$OUT" || { log "FATAL cannot create $OUT"; exit 2; }
# Leftovers of a crashed earlier run (never valid dumps).
rm -f "$OUT"/.tmp.* 2>/dev/null

# ---- helpers ----------------------------------------------------------------
# newest GOOD daily dump (has sidecar) in directory $1 -> prints path or nothing
newest_good() {
    _best=""
    for _f in "$1"/*.daily.*; do
        case "$_f" in *.sha256 | *.tmp | *.suspect) continue ;; esac
        [ -f "$_f" ] && [ -f "$_f.sha256" ] && _best="$_f"
    done
    [ -n "$_best" ] && printf '%s\n' "$_best"
}

# keep newest $2 files of kind $3 (daily|weekly) in directory $1, drop the rest
prune_kind() {
    _dir=$1 _keep=$2 _kind=$3 _n=0
    for _f in "$_dir"/*."$_kind".*; do
        case "$_f" in *.sha256 | *.tmp) continue ;; esac
        [ -f "$_f" ] && [ -f "$_f.sha256" ] && _n=$((_n + 1))
    done
    _drop=$((_n - _keep))
    for _f in "$_dir"/*."$_kind".*; do
        case "$_f" in *.sha256 | *.tmp) continue ;; esac
        [ "$_drop" -gt 0 ] || break
        [ -f "$_f" ] && [ -f "$_f.sha256" ] || continue
        rm -f "$_f" "$_f.sha256" && log "pruned $(basename "$_f") from $(basename "$_dir")"
        _drop=$((_drop - 1))
    done
}

# content check of $1; 0 = valid
validate() {
    case "$ENGINE" in
    postgres)
        case "$2" in
        globals) gzip -t "$1" && zcat "$1" | grep -q 'CREATE ROLE' ;;
        *) pg_restore --list "$1" > /dev/null ;;
        esac
        ;;
    mariadb)
        gzip -t "$1" && zcat "$1" | tail -c 400 | grep -q 'Dump completed'
        ;;
    esac
}

# dump_one <name> <kind: db|globals|users>; the engine-specific writer is run_dump
# name is the database (or _globals/_users); writes to $TMP.
finish_one() {
    _name=$1 _kind=$2 _start=$3
    _dir="$OUT/$_name"
    _tmp="$OUT/.tmp.$TS.$_name"
    _size=$(stat -c %s "$_tmp" 2> /dev/null || echo 0)
    if [ "$_size" -le 0 ]; then
        log "FAIL $_name: empty output"
        rm -f "$_tmp"; return 1
    fi
    if ! validate "$_tmp" "$_kind"; then
        log "FAIL $_name: validation of the new dump failed"
        rm -f "$_tmp"; return 1
    fi
    mkdir -p "$_dir" || return 1
    _prev=$(newest_good "$_dir")
    if [ -n "$_prev" ]; then
        _psize=$(stat -c %s "$_prev" 2> /dev/null || echo 0)
        if [ "$_psize" -ge "$MIN_PREV_BYTES" ] && [ $((_size * 100)) -lt $((_psize * MIN_RATIO)) ]; then
            log "FAIL $_name: new dump ${_size}B < ${MIN_RATIO}% of previous good ${_psize}B; quarantined, nothing pruned"
            mv "$_tmp" "$_dir/$TS.suspect" 2> /dev/null || rm -f "$_tmp"
            _s=0
            for _x in $(ls -1r "$_dir"/*.suspect 2> /dev/null); do
                _s=$((_s + 1)); [ "$_s" -gt 2 ] && rm -f "$_x"
            done
            return 1
        fi
    fi
    _sum=$(sha256sum "$_tmp" | cut -d' ' -f1)
    _final="$_dir/$TS.daily.$EXT"
    mv "$_tmp" "$_final" || return 1
    printf '%s  %s\n' "$_sum" "$(basename "$_final")" > "$_final.sha256.tmp" \
        && mv "$_final.sha256.tmp" "$_final.sha256" || return 1
    if [ "$DOW" = 7 ]; then
        _wk="$_dir/$TS.weekly.$EXT"
        cp "$_final" "$_wk.tmp" && mv "$_wk.tmp" "$_wk" \
            && printf '%s  %s\n' "$_sum" "$(basename "$_wk")" > "$_wk.sha256.tmp" \
            && mv "$_wk.sha256.tmp" "$_wk.sha256" || { log "FAIL $_name: weekly copy"; return 1; }
    fi
    prune_kind "$_dir" "$KEEP_DAILY" daily
    prune_kind "$_dir" "$KEEP_WEEKLY" weekly
    rm -f "$_dir"/*.tmp 2> /dev/null
    log "OK   $_name: ${_size}B in $(($(date +%s) - _start))s"
    return 0
}

record() { # name ok start
    printf '%s\t%s\t%s\n' "$1" "$2" "$(($(date +%s) - $3))" >> "$RUN_FILE"
    [ "$2" = 1 ] || FAILED="$FAILED $1"
}

list_databases() {
    case "$ENGINE" in
    postgres)
        psql -d postgres -Atc "select datname from pg_database where not datistemplate and datallowconn order by 1"
        ;;
    mariadb)
        # shellcheck disable=SC2086
        mariadb $MYSQL_ARGS --connect-timeout=15 -N -B -e 'SHOW DATABASES' | grep -v -x -e information_schema -e performance_schema -e sys -e mysql
        ;;
    esac
}

dump_database() { # db tmp
    case "$ENGINE" in
    postgres)
        nice -n 19 pg_dump --format=custom --compress=6 --no-sync --file="$2" --dbname="$1"
        ;;
    mariadb)
        # shellcheck disable=SC2086
        nice -n 19 mariadb-dump $MYSQL_ARGS --single-transaction --routines --events --triggers \
            --hex-blob --default-character-set=utf8mb4 --databases "$1" --result-file="$2.sql" \
            && nice -n 19 gzip -6 -c "$2.sql" > "$2"; _rc=$?
        rm -f "$2.sql"
        return "$_rc"
        ;;
    esac
}

# ---- run --------------------------------------------------------------------
log "instance=$INSTANCE engine=$ENGINE host=$DB_HOST ts=$TS"

DBS=$(list_databases) || { log "FATAL cannot list databases (auth/network?)"; DBS=""; FAILED="$FAILED _enumerate"; }

for db in $DBS; do
    case "$db" in
    *[!A-Za-z0-9_.-]* | "" | .* ) log "FAIL unsafe database name skipped"; FAILED="$FAILED _unsafe-name"; continue ;;
    esac
    start=$(date +%s)
    log "dumping $db"
    if dump_database "$db" "$OUT/.tmp.$TS.$db" && finish_one "$db" db "$start"; then
        record "$db" 1 "$start"
    else
        rm -f "$OUT/.tmp.$TS.$db" "$OUT/.tmp.$TS.$db.sql"
        record "$db" 0 "$start"
    fi
done

EXT=sql.gz   # globals / users files are gzipped SQL for both engines
if [ "$ENGINE" = postgres ]; then
    start=$(date +%s)
    log "dumping globals"
    if nice -n 19 pg_dumpall --globals-only -l postgres --file="$OUT/.tmp.$TS._globals.sql" \
        && nice -n 19 gzip -6 -c "$OUT/.tmp.$TS._globals.sql" > "$OUT/.tmp.$TS._globals" \
        && rm -f "$OUT/.tmp.$TS._globals.sql" \
        && finish_one _globals globals "$start"; then
        record _globals 1 "$start"
    else
        rm -f "$OUT/.tmp.$TS._globals" "$OUT/.tmp.$TS._globals.sql"
        record _globals 0 "$start"
    fi
elif [ "$DUMP_USERS" = 1 ]; then
    start=$(date +%s)
    log "dumping users/grants"
    # shellcheck disable=SC2086
    if mariadb-dump $MYSQL_ARGS --system=users --result-file="$OUT/.tmp.$TS._users.sql" \
        && gzip -6 -c "$OUT/.tmp.$TS._users.sql" > "$OUT/.tmp.$TS._users" \
        && rm -f "$OUT/.tmp.$TS._users.sql" \
        && finish_one _users users "$start"; then
        record _users 1 "$start"
    else
        rm -f "$OUT/.tmp.$TS._users" "$OUT/.tmp.$TS._users.sql"
        record _users 0 "$start"
    fi
fi

# ---- metrics from disk truth ------------------------------------------------
M="$WORK_DIR/metrics.prom"
{
    echo '# TYPE db_dump_last_success_timestamp_seconds gauge'
    echo '# TYPE db_dump_size_bytes gauge'
    echo '# TYPE db_dump_duration_seconds gauge'
    echo '# TYPE db_dump_last_run_ok gauge'
    echo '# TYPE db_dump_instance_last_run_ok gauge'
    echo '# TYPE db_dump_instance_run_timestamp_seconds gauge'
} > "$M"
for d in "$OUT"/*/; do
    [ -d "$d" ] || continue
    name=$(basename "$d")
    best=$(newest_good "$d")
    if [ -n "$best" ]; then
        printf 'db_dump_last_success_timestamp_seconds{database="%s"} %s\n' "$name" "$(stat -c %Y "$best")" >> "$M"
        printf 'db_dump_size_bytes{database="%s"} %s\n' "$name" "$(stat -c %s "$best")" >> "$M"
    fi
done
while IFS="$(printf '\t')" read -r name ok dur; do
    printf 'db_dump_last_run_ok{database="%s"} %s\n' "$name" "$ok" >> "$M"
    printf 'db_dump_duration_seconds{database="%s"} %s\n' "$name" "$dur" >> "$M"
done < "$RUN_FILE"

if [ -z "$FAILED" ] && [ -s "$RUN_FILE" ]; then
    echo ok > "$WORK_DIR/result"
    printf 'db_dump_instance_last_run_ok 1\n' >> "$M"
    log "RESULT ok"
else
    echo fail > "$WORK_DIR/result"
    printf 'db_dump_instance_last_run_ok 0\n' >> "$M"
    log "RESULT FAIL:${FAILED:- no databases dumped}"
fi
printf 'db_dump_instance_run_timestamp_seconds %s\n' "$(date +%s)" >> "$M"
exit 0
