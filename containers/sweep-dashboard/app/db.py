"""Postgres connection pool + helpers for the sweep-dashboard.

Reads via the sweep_reader role only — no INSERT/UPDATE/DELETE methods
are exposed. The DSN comes from the SWEEP_PG_DSN env var (mounted from
the sweep-dashboard Secret).
"""
from __future__ import annotations

import os
from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

_DSN = os.environ.get("SWEEP_PG_DSN") or ""
if not _DSN:
    raise RuntimeError("SWEEP_PG_DSN env var is required")

# Tuned for small dashboard load. min_size=1 keeps a warm connection.
pool = ConnectionPool(
    conninfo=_DSN,
    min_size=1,
    max_size=4,
    open=False,  # opened on FastAPI startup
    kwargs={"row_factory": dict_row, "autocommit": True},
)


def fetch_all(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return list(cur.fetchall())


def fetch_one(sql: str, params: tuple = ()) -> dict[str, Any] | None:
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def health() -> bool:
    """Liveness probe — true iff we can SELECT 1 from Postgres."""
    try:
        with pool.connection(timeout=2) as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            return cur.fetchone() is not None
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Queries used by the routes — kept here so main.py stays presentation-only.
# ---------------------------------------------------------------------------


def latest_cycle() -> dict[str, Any] | None:
    return fetch_one(
        """
        SELECT cycle_id, started_at, finished_at, trigger, git_head, verdict, notes
          FROM sweep_cycles
         ORDER BY started_at DESC
         LIMIT 1
        """
    )


def recent_cycles(limit: int = 30) -> list[dict[str, Any]]:
    return fetch_all(
        """
        SELECT cycle_id, started_at, finished_at, trigger, git_head, verdict,
               EXTRACT(EPOCH FROM (finished_at - started_at)) AS duration_seconds
          FROM sweep_cycles
         ORDER BY started_at DESC
         LIMIT %s
        """,
        (limit,),
    )


def open_findings_counts() -> list[dict[str, Any]]:
    """Counts of open findings grouped by section × severity."""
    return fetch_all(
        """
        SELECT section, severity, count(*) AS n
          FROM sweep_findings
         WHERE resolved_at IS NULL
         GROUP BY section, severity
         ORDER BY section, severity
        """
    )


def open_findings(
    section: str | None = None,
    severity: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    where = ["resolved_at IS NULL"]
    params: list[Any] = []
    if section:
        where.append("section = %s")
        params.append(section)
    if severity:
        where.append("severity = %s")
        params.append(severity)
    params.append(limit)
    return fetch_all(
        f"""
        SELECT finding_id, section, severity, status, title, action,
               first_seen, last_seen,
               EXTRACT(EPOCH FROM (now() - first_seen)) / 86400 AS age_days
          FROM sweep_findings
         WHERE {" AND ".join(where)}
         ORDER BY
             CASE severity
               WHEN 'critical' THEN 0
               WHEN 'warning'  THEN 1
               WHEN 'monitor'  THEN 2
               WHEN 'deferred' THEN 3
               ELSE 9
             END,
             first_seen ASC
         LIMIT %s
        """,
        tuple(params),
    )


def finding_history(finding_id: str) -> list[dict[str, Any]]:
    """Every row in sweep_findings sharing this finding_id (newest first)."""
    return fetch_all(
        """
        SELECT id, finding_id, section, severity, status, title, action,
               first_seen, last_seen, resolved_at, cycle_id, metadata
          FROM sweep_findings
         WHERE finding_id = %s
         ORDER BY last_seen DESC
        """,
        (finding_id,),
    )
