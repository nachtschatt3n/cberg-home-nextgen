"""Findings writer — emits audit findings to the sweep-history Postgres.

Used by runbooks/{security,version,doc,health}-check.py to persist findings
across cycles. Dedup is by stable fingerprint = sha256(section || normalized
title); same wording tomorrow keeps the same finding_id and updates
last_seen. Differences in numeric counts/timestamps don't break the match
because of the title-normalisation pass.

Schema lives at kubernetes/apps/databases/sweep-history/app/schema-configmap.yaml.

Usage:
    from runbooks.lib.findings_writer import FindingsWriter

    writer = FindingsWriter(
        dsn=os.environ["SWEEP_PG_DSN"],
        section="security",
        trigger="manual",
        git_head=current_git_sha(),
    )
    try:
        writer.emit("critical", "289 HA errors on Frigate integration",
                    action="filter at Logstash",
                    subsection="s6a_error_rate_spikes")
        ...
    finally:
        writer.close(verdict="red")

The library degrades gracefully: if DSN is empty or None, all calls become
no-ops so existing markdown-only invocations of the audit scripts still
work unchanged.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

# Severity emoji → DB string mapping. Matches the emoji constants used
# in the audit scripts (CRITICAL/WARNING/OK/ACCEPTED).
SEVERITY_MAP = {
    "🔴": "critical",
    "🟡": "warning",
    "🟢": "clean",
    "🛡️": "accepted",
    # Allow direct string passes too
    "critical": "critical",
    "warning":  "warning",
    "clean":    "clean",
    "accepted": "accepted",
    "monitor":  "monitor",
    "deferred": "deferred",
}

VALID_SECTIONS = {
    "health", "security", "version", "doc",
    "media", "smarthome", "slo", "infra", "carry",
}

_RE_DIGITS    = re.compile(r"\d+")
_RE_TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}[Tt ]?\d{2}:\d{2}(:\d{2})?([Zz]|[+-]\d{2}:?\d{2})?"
)
_RE_UUID      = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
_RE_IPV4      = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_RE_MAC       = re.compile(r"\b[0-9a-f]{2}(?::[0-9a-f]{2}){5}\b", re.I)
_RE_SHA       = re.compile(r"\b[0-9a-f]{7,40}\b")
_RE_WS        = re.compile(r"\s+")


def _normalize(title: str) -> str:
    """Strip volatile substrings so the fingerprint is stable across cycles.

    Order matters — timestamps first so they don't get partially mangled
    by the bare-digit pass.
    """
    s = title.lower().strip()
    s = _RE_TIMESTAMP.sub("<ts>", s)
    s = _RE_UUID.sub("<uuid>", s)
    s = _RE_IPV4.sub("<ip>", s)
    s = _RE_MAC.sub("<mac>", s)
    s = _RE_SHA.sub("<sha>", s)
    s = _RE_DIGITS.sub("<n>", s)
    s = _RE_WS.sub(" ", s)
    return s


def fingerprint(section: str, subsection: str | None, title: str) -> str:
    """Stable identifier for a finding across cycles.

    sha256 hex digest. Truncated to 64 chars (full digest fits — no overflow).
    """
    parts = (section, subsection or "", _normalize(title))
    blob = "|".join(parts).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def finding_id_from_fp(fp: str) -> str:
    """Stable DB id derived from fingerprint. Format: F-<first-8-hex>."""
    return f"F-{fp[:8]}"


class FindingsWriter:
    """Append-or-update findings into sweep-history Postgres.

    One instance per (script run × section). The cycle row is created
    on construction and finalised on close().

    Degrades to no-op if dsn is empty or None — emit() returns the
    derived finding_id but performs no DB write. Lets the existing
    markdown-only workflow keep working.
    """

    def __init__(
        self,
        *,
        dsn: str | None,
        section: str,
        cycle_id: str | None = None,
        trigger: str = "manual",
        git_head: str | None = None,
        notes: str | None = None,
    ):
        if section not in VALID_SECTIONS:
            raise ValueError(
                f"section={section!r} not one of {sorted(VALID_SECTIONS)}"
            )
        self.section = section
        self.dsn = dsn or None
        self._conn = None
        self._cycle_id = cycle_id or str(uuid.uuid4())
        self._enabled = bool(self.dsn)

        if not self._enabled:
            return

        # Defer the import so absence of psycopg doesn't break no-DSN runs.
        import psycopg  # type: ignore

        self._conn = psycopg.connect(self.dsn, autocommit=False)
        with self._conn.cursor() as cur:
            # Idempotent: if the cycle row already exists (caller passed an
            # existing cycle_id) we leave it alone. New cycle_id → fresh row.
            cur.execute(
                """
                INSERT INTO sweep_cycles
                    (cycle_id, started_at, trigger, git_head, notes)
                VALUES (%s, now(), %s, %s, %s)
                ON CONFLICT (cycle_id) DO NOTHING
                """,
                (self._cycle_id, trigger, git_head, notes),
            )
        self._conn.commit()

    @property
    def cycle_id(self) -> str:
        return self._cycle_id

    @property
    def enabled(self) -> bool:
        return self._enabled

    def emit(
        self,
        severity: str,
        title: str,
        *,
        action: str | None = None,
        evidence_path: str | None = None,
        subsection: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Emit one finding.

        Returns the finding_id (stable across cycles by fingerprint).
        Safe to call even when disabled — returns the id without writing.
        """
        sev = SEVERITY_MAP.get(severity, severity)
        if sev not in {
            "critical", "warning", "clean", "accepted",
            "monitor", "deferred",
        }:
            raise ValueError(f"unknown severity {severity!r}")

        fp = fingerprint(self.section, subsection, title)
        fid = finding_id_from_fp(fp)

        if not self._enabled or self._conn is None:
            return fid

        meta = dict(metadata or {})
        if subsection:
            meta.setdefault("subsection", subsection)

        with self._conn.cursor() as cur:
            # Look up the currently-open row (resolved_at IS NULL) by fingerprint.
            cur.execute(
                """
                SELECT id, finding_id
                  FROM sweep_findings
                 WHERE fingerprint = %s AND resolved_at IS NULL
                 ORDER BY first_seen DESC
                 LIMIT 1
                """,
                (fp,),
            )
            row = cur.fetchone()

            if row is not None:
                # Carry-over: same finding, new cycle. Keep finding_id stable.
                existing_id, existing_fid = row
                cur.execute(
                    """
                    UPDATE sweep_findings
                       SET last_seen = now(),
                           severity  = %s,
                           title     = %s,
                           status    = 'unchanged',
                           action    = COALESCE(%s, action),
                           evidence_path = COALESCE(%s, evidence_path),
                           cycle_id  = %s,
                           metadata  = COALESCE(metadata, '{}'::jsonb) || %s::jsonb
                     WHERE id = %s
                    """,
                    (
                        sev, title, action, evidence_path,
                        self._cycle_id, json.dumps(meta), existing_id,
                    ),
                )
                fid = existing_fid
            else:
                # New finding this cycle.
                cur.execute(
                    """
                    INSERT INTO sweep_findings (
                        finding_id, fingerprint, section, severity,
                        title, status, action, evidence_path,
                        first_seen, last_seen, cycle_id, metadata
                    ) VALUES (
                        %s, %s, %s, %s,
                        %s, 'new', %s, %s,
                        now(), now(), %s, %s::jsonb
                    )
                    """,
                    (
                        fid, fp, self.section, sev,
                        title, action, evidence_path,
                        self._cycle_id, json.dumps(meta),
                    ),
                )
        self._conn.commit()
        return fid

    def close(self, *, verdict: str | None = None) -> None:
        """Finalise the cycle row.

        verdict is one of: green | yellow | red (or None to leave unset).
        Idempotent for the same cycle — if called twice, last call wins
        on finished_at and verdict.
        """
        if not self._enabled or self._conn is None:
            return
        with self._conn.cursor() as cur:
            cur.execute(
                """
                UPDATE sweep_cycles
                   SET finished_at = now(),
                       verdict     = COALESCE(%s, verdict)
                 WHERE cycle_id = %s
                """,
                (verdict, self._cycle_id),
            )
        self._conn.commit()
        self._conn.close()
        self._conn = None
        self._enabled = False

    def __enter__(self) -> "FindingsWriter":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        # On exception, still close the cycle row so it's not left open
        # forever. Verdict stays whatever the caller set explicitly via
        # close() before the exception, or None if they never did.
        if self._enabled and self._conn is not None:
            try:
                self.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Convenience: derive cycle/trigger context from environment
# ---------------------------------------------------------------------------


def cycle_id_from_env(default: str | None = None) -> str | None:
    """Return $SWEEP_CYCLE_ID if set, else the provided default.

    Lets the orchestrator / sweep-run.py wrapper pass one cycle_id to all
    audit scripts so they share a single cycle row.
    """
    return os.environ.get("SWEEP_CYCLE_ID") or default


def trigger_from_env(default: str = "manual") -> str:
    return os.environ.get("SWEEP_TRIGGER", default)


def git_head() -> str | None:
    """Return the current git HEAD sha (7 chars) or None if unavailable."""
    import subprocess
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short=40", "HEAD"],
            stderr=subprocess.DEVNULL,
        )
        return out.decode().strip() or None
    except Exception:
        return None
