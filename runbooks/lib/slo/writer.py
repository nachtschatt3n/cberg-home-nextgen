"""Write SLO snapshots into the sweep-history Postgres.

Mirrors the contract of runbooks/lib/findings_writer.py: degrades to a
no-op when DSN is empty, opens a connection on construction, exposes
`emit(snapshot)` and `close()`.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .calc import SloSnapshot


class SloWriter:
    def __init__(self, *, dsn: str | None):
        self.dsn = dsn or None
        self._conn = None
        self._enabled = bool(self.dsn)
        if not self._enabled:
            return
        import psycopg  # lazy
        self._conn = psycopg.connect(self.dsn, autocommit=False)

    @property
    def enabled(self) -> bool:
        return self._enabled

    def emit(self, snap: SloSnapshot) -> None:
        if not self._enabled or self._conn is None:
            return
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO slo_snapshots (
                    slo_name, taken_at,
                    compliance_pct, target_pct,
                    burn_rate_1h, burn_rate_6h,
                    budget_remaining_pct,
                    window_size, source,
                    raw_numerator, raw_denominator
                ) VALUES (
                    %s, %s,
                    %s, %s,
                    %s, %s,
                    %s,
                    %s, %s,
                    %s, %s
                )
                """,
                (
                    snap.slo_name,
                    datetime.now(timezone.utc),
                    snap.compliance_pct, snap.target_pct,
                    snap.burn_rate_1h, snap.burn_rate_6h,
                    snap.budget_remaining_pct,
                    snap.window_size, snap.source,
                    snap.raw_numerator, snap.raw_denominator,
                ),
            )
        self._conn.commit()

    def close(self) -> None:
        if self._enabled and self._conn is not None:
            self._conn.close()
            self._conn = None
            self._enabled = False

    def __enter__(self) -> "SloWriter":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
