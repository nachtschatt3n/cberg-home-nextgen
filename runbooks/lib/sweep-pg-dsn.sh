#!/usr/bin/env bash
# sweep-pg-dsn.sh — export a live SWEEP_PG_DSN for the cluster sweep_history
# Postgres via a kubectl port-forward on a GUARANTEED-FREE local port.
#
# WHY THIS EXISTS (2026-07-09):
# The operator Mac runs a local Postgres on 127.0.0.1:5432. If a sweep
# hand-rolls `kubectl port-forward ... 5432:5432` with a DSN of @127.0.0.1:5432,
# the port-forward fails to bind (5432 is taken) and the DSN silently connects
# to the LOCAL postgres instead — which has no `sweep_writer` role and none of
# the sweep tables. Result: every specialist's write fails with
# 'role "sweep_writer" does not exist', the cycle persists 0 rows, and the
# reconcile writes a FALSE green over an empty cycle. NEVER use 5432 for the
# local side — always a free port. This helper is the canonical, tested way to
# get the DSN; the daily-operation orchestrator and specialists must source it
# instead of hand-rolling a port-forward. See daily-operation.md rule 0b.
#
# Usage (MUST be sourced — it sets env in the caller's shell):
#   source runbooks/lib/sweep-pg-dsn.sh && sweep_pg_dsn_up || exit 1
#   export SWEEP_PG_DSN            # already exported; pass to specialists
#   ... run check scripts / findings_writer (they read $SWEEP_PG_DSN) ...
#   sweep_pg_dsn_down             # stop the port-forward when the sweep is done
#
# On success: $SWEEP_PG_DSN and $SWEEP_PG_PF_PID are exported, and the DSN has
# been verified to reach the real cluster db (public.sweep_findings exists).
# On any failure it tears down the port-forward and returns non-zero rather
# than hand out a possibly-shadowed DSN.

# Prefer the repo venv python (has psycopg); fall back to bare python3.
_sweep_pg_pybin() {
    local d
    d="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." 2>/dev/null && pwd)"
    if [ -x "$d/.venv/bin/python3" ]; then echo "$d/.venv/bin/python3"; else echo "python3"; fi
}

sweep_pg_dsn_up() {
    local py port raw fqdn i
    py="$(_sweep_pg_pybin)"

    # Guaranteed-free local port (bind :0). Belt-and-suspenders: never 5432.
    port=$(python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));p=s.getsockname()[1];s.close();print(p)')
    [ "$port" = "5432" ] && port=$(python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));p=s.getsockname()[1];s.close();print(p)')

    kubectl port-forward -n databases svc/postgresql "${port}:5432" \
        >"/tmp/sweep-pg-pf-${port}.log" 2>&1 &
    export SWEEP_PG_PF_PID=$!

    for i in $(seq 1 30); do
        if python3 -c "import socket;socket.create_connection(('127.0.0.1',${port}),0.3).close()" 2>/dev/null; then
            break
        fi
        sleep 0.2
    done

    raw=$(kubectl get secret -n databases sweep-history -o jsonpath='{.data.WRITER_DSN}' 2>/dev/null | base64 -d)
    if [ -z "$raw" ]; then
        echo "sweep-pg-dsn: ERROR could not decode databases/sweep-history WRITER_DSN" >&2
        sweep_pg_dsn_down; return 1
    fi

    fqdn="@postgresql.databases.svc.cluster.local:5432"
    export SWEEP_PG_DSN="${raw/${fqdn}/@127.0.0.1:${port}}"

    # Sanity: confirm we reached the CLUSTER db (sweep_findings exists), NOT a
    # local shadow. This is the explicit guard against the 5432-squat failure.
    if ! "$py" -c "
import os,sys
try:
    import psycopg
    with psycopg.connect(os.environ['SWEEP_PG_DSN'], connect_timeout=5) as c, c.cursor() as cur:
        cur.execute(\"select to_regclass('public.sweep_findings') is not null\")
        sys.exit(0 if cur.fetchone()[0] else 3)
except Exception as e:
    sys.stderr.write(f'{type(e).__name__}: {e}\n'); sys.exit(4)
" 2>/tmp/sweep-pg-sanity.err; then
        echo "sweep-pg-dsn: ERROR DSN did not reach the cluster sweep_history db — refusing to hand out a shadowed DSN:" >&2
        sed 's/^/    /' /tmp/sweep-pg-sanity.err >&2
        sweep_pg_dsn_down; return 1
    fi

    echo "sweep-pg-dsn: ready on 127.0.0.1:${port} (pf pid ${SWEEP_PG_PF_PID}); public.sweep_findings reachable"
}

sweep_pg_dsn_down() {
    [ -n "${SWEEP_PG_PF_PID:-}" ] && kill "${SWEEP_PG_PF_PID}" 2>/dev/null
    unset SWEEP_PG_PF_PID
}
