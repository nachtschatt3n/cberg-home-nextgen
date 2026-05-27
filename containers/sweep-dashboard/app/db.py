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


# ---------------------------------------------------------------------------
# SLO queries
# ---------------------------------------------------------------------------


def latest_slo_snapshots() -> list[dict[str, Any]]:
    """One row per slo_name — the most recent snapshot.

    DISTINCT ON keeps each name's newest sample. Burn-rate badge logic
    in the template uses these values; the underlying values may be
    NULL when the long-window query had a NaN gap.
    """
    return fetch_all(
        """
        SELECT DISTINCT ON (slo_name)
               slo_name, taken_at, compliance_pct, target_pct,
               burn_rate_1h, burn_rate_6h, budget_remaining_pct,
               window_size, source, raw_numerator, raw_denominator
          FROM slo_snapshots
         ORDER BY slo_name, taken_at DESC
        """
    )


def slo_history(name: str, limit: int = 200) -> list[dict[str, Any]]:
    """Recent snapshots for one SLO, newest first."""
    return fetch_all(
        """
        SELECT id, slo_name, taken_at, compliance_pct, target_pct,
               burn_rate_1h, burn_rate_6h, budget_remaining_pct,
               window_size, source, raw_numerator, raw_denominator
          FROM slo_snapshots
         WHERE slo_name = %s
         ORDER BY taken_at DESC
         LIMIT %s
        """,
        (name, limit),
    )


# ---------------------------------------------------------------------------
# Policy queries (sweep_history v3 — Phase 2 dashboard surface)
# ---------------------------------------------------------------------------


def accepted_risks() -> list[dict[str, Any]]:
    return fetch_all(
        """
        SELECT ar_id, severity, description, justification, status, enabled,
               accepted_at, last_reviewed_at, metadata
          FROM accepted_risks
         ORDER BY ar_id
        """
    )


def slo_definitions() -> list[dict[str, Any]]:
    return fetch_all(
        """
        SELECT name, description, source, kind, target, window_size,
               query_json, burn_rate_windows, tags, enabled,
               created_at, updated_at
          FROM slo_definitions
         ORDER BY name
        """
    )


def noise_suppressions() -> list[dict[str, Any]]:
    return fetch_all(
        """
        SELECT id, category, match_key, match_value, threshold, note,
               enabled, created_at
          FROM noise_suppressions
         ORDER BY category, id
        """
    )


def security_acceptances() -> list[dict[str, Any]]:
    return fetch_all(
        """
        SELECT id, category, pattern, note, ar_id, enabled, created_at
          FROM security_acceptances
         ORDER BY category, id
        """
    )


def policy_counts() -> dict[str, dict[str, int]]:
    """Per-table totals + enabled-only subtotals for the /policies landing page."""
    out: dict[str, dict[str, int]] = {}
    for table in ("accepted_risks", "slo_definitions",
                  "noise_suppressions", "security_acceptances"):
        row = fetch_one(
            f"SELECT COUNT(*) AS total, "
            f"SUM(CASE WHEN enabled THEN 1 ELSE 0 END) AS enabled "
            f"FROM {table}"
        )
        out[table] = {
            "total":   int(row["total"]) if row else 0,
            "enabled": int(row["enabled"] or 0) if row else 0,
        }
    return out
