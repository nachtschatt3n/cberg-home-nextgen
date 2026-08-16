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
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

# Transient-connection retry policy, shared by the write preflight and the
# constructor. A daily-operation run spends many minutes in Elasticsearch and
# Wazuh port-forwards before it ever writes, so a momentary DB blip must not
# throw away a completed run's findings.
_CONNECT_ATTEMPTS = 3
_CONNECT_BACKOFF_S = 2.0


def _connect_with_retry(dsn: str, *, autocommit: bool = False,
                        attempts: int = _CONNECT_ATTEMPTS,
                        backoff_s: float = _CONNECT_BACKOFF_S):
    """psycopg.connect with a small bounded retry on transient failures.

    Raises the last exception if every attempt fails, so callers can decide
    between fail-fast (preflight) and degrade-to-no-op.
    """
    import psycopg  # type: ignore
    last: Exception | None = None
    for i in range(attempts):
        try:
            return psycopg.connect(dsn, autocommit=autocommit, connect_timeout=10)
        except Exception as e:  # noqa: BLE001 — surface after final attempt
            last = e
            if i < attempts - 1:
                time.sleep(backoff_s * (i + 1))
    assert last is not None
    raise last

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

# A finding's stable IDENTITY is the code-identifier(s) it names, not the prose
# around them. Audit messages put those identifiers in `backticks` (an image
# ref like `postgres:17.10-bookworm`, a resource name, an alertname) and carry
# any accepted-risk `[AR-0NN]` tags that qualify which finding-of-that-object
# this is. Everything else in the line is human prose that gets reworded.
_RE_BACKTICK  = re.compile(r"`([^`]+)`")
_RE_ARTAG     = re.compile(r"\[AR-\d+\]", re.I)


def _stable_anchor(title: str) -> str | None:
    """A prose-independent identity for `title`, or None if it has no anchor.

    Built from the backtick-quoted identifiers plus the sorted set of
    `[AR-0NN]` tags. Returns None when the title contains no backticked span,
    so ordinary sentence-shaped findings fall back to the normalized-title
    fingerprint (unchanged behaviour).

    Why this exists: the previous fingerprint hashed the whole normalized
    PROSE, so rewording a message forked a brand-new finding row for an
    unchanged problem (2026-08: a single title reword split 20 image findings
    into 39 rows). Backtick content is kept VERBATIM (digits included) — the
    image *version* is part of the identity: `postgres:17.10-bookworm` and
    `postgres:17.11-bookworm` are genuinely different findings, and this is
    the "hash on image@section, not on rendered prose" fix. The AR-tag set is
    what keeps two DISTINCT findings about the SAME object apart — e.g. an
    image's fixable-CRITICAL line (often untagged, or `[AR-052]`) vs its
    no-upstream-fix accepted line (always `[AR-029]`) — which a bare image key
    would wrongly collapse into one row.
    """
    spans = _RE_BACKTICK.findall(title)
    if not spans:
        return None
    ids = "``".join(_RE_WS.sub(" ", s.strip().lower()) for s in spans)
    ar = ",".join(sorted({m.upper() for m in _RE_ARTAG.findall(title)}))
    return f"{ids}|{ar}"


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

    Keys on the title's stable ANCHOR (backticked identifiers + AR-tag set)
    when it has one, else the normalized prose. This is what makes the id
    survive a message reword instead of forking a new row. sha256 hex digest.
    """
    basis = _stable_anchor(title)
    if basis is None:
        basis = _normalize(title)
    parts = (section, subsection or "", basis)
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
        # Cycle grouping precedence: explicit arg > SWEEP_CYCLE_ID env > new UUID.
        # The env fallback is what lets the daily-operation fan-out group every
        # specialist's check script into ONE shared sweep_cycles row (the
        # orchestrator sets SWEEP_CYCLE_ID once and passes it to all specialists),
        # instead of each check script minting its own cycle → dashboard fragments.
        self._cycle_id = (
            cycle_id or os.environ.get("SWEEP_CYCLE_ID") or str(uuid.uuid4())
        )
        # Cycle-row metadata is stashed for the LAZY insert (see _ensure_cycle_row).
        self._trigger = trigger
        self._git_head = git_head
        self._notes = notes
        # The sweep_cycles row is created on the FIRST emit(), never on
        # construction. A writer that is built and then closed WITHOUT emitting
        # anything (a clean section that joins someone else's shared cycle, or a
        # stray writer that mints a fresh uuid because SWEEP_CYCLE_ID wasn't
        # exported) must leave NO row behind — eagerly inserting here is what
        # produced the "5 empty sweep_cycles rows per run" create-then-abandon
        # orphans (N-20). Deferring makes the write path self-cleaning: no
        # finding → no cycle row.
        self._cycle_ensured = False
        self._enabled = bool(self.dsn)

        if not self._enabled:
            return

        # Retry a transient blip rather than losing a whole completed run's
        # findings. If the DB is genuinely down this still raises — callers
        # that want to fail BEFORE doing the work should call preflight().
        self._conn = _connect_with_retry(self.dsn, autocommit=False)

    def _ensure_cycle_row(self, cur) -> None:
        """Create the shared sweep_cycles row on demand (first emit).

        Idempotent per-instance (guarded by `_cycle_ensured`) and idempotent
        cross-process (`ON CONFLICT (cycle_id) DO NOTHING`) — so the first
        specialist to actually emit a finding creates the one shared row, and
        every other specialist that joins the same SWEEP_CYCLE_ID no-ops. A
        writer that never emits never calls this, so it creates no orphan.
        """
        if self._cycle_ensured or self._conn is None:
            return
        cur.execute(
            """
            INSERT INTO sweep_cycles
                (cycle_id, started_at, trigger, git_head, notes)
            VALUES (%s, now(), %s, %s, %s)
            ON CONFLICT (cycle_id) DO NOTHING
            """,
            (self._cycle_id, self._trigger, self._git_head, self._notes),
        )
        self._cycle_ensured = True

    @staticmethod
    def preflight(dsn: str | None, *, attempts: int = _CONNECT_ATTEMPTS) -> bool:
        """Verify the findings DB is writable BEFORE a run does its work.

        Returns True when `dsn` is empty/None (markdown-only mode is a valid,
        supported way to run the audit — nothing to preflight). Otherwise it
        opens a connection (with the shared retry) and runs `SELECT 1`,
        returning True on success and RAISING on failure.

        Call this at the very start of an audit. Findings are only persisted at
        the END, after minutes of section work and several port-forwards, so a
        DB that is unreachable at write time silently discards a fully
        completed run (observed: all 13/13 security sections ran, then the
        end-of-run connect threw and every finding was lost). Failing fast here
        converts that into an obvious up-front error the operator can fix.
        """
        if not dsn:
            return True
        conn = _connect_with_retry(dsn, autocommit=True, attempts=attempts)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        finally:
            conn.close()
        return True

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
            # Create the shared cycle row lazily, on the first finding only.
            self._ensure_cycle_row(cur)
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
