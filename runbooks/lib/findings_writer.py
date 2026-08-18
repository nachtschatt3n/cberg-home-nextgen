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

STALE-FINDING AUTO-CLOSE
------------------------
`close(verdict=...)` also RESOLVES this section's open findings that the run
did not re-emit. A finding that a section stops emitting is fixed, and it is
closed by the next successful run of THAT section — the writer is the only
component that reliably knows the section, the exact fingerprint set just
emitted, and whether the run finished.

The gate is `section_complete`, inferred from `verdict is not None` when not
passed explicitly. That distinguishes the caller's own end-of-run
`close(verdict=...)` (a verdict only exists once the section produced a
result) from `__exit__`'s bare `close()` on the exception path, and from
partial users of the writer such as auto-update.py, which emits a single
version finding and must never conclude anything about the version section.
A section that ran but knows its coverage degraded calls `mark_incomplete()`.

Auto-close additionally requires an ORCHESTRATED run (a cycle id handed
down by sweep-run.py / the daily-operation fan-out). A hand-run check
script mints its own cycle id and closes nothing — an ad-hoc run may be
scoped or degraded, and a conclusion drawn from absence would be wrong.

It never resolves a row last seen at or after the moment this section
started, so a concurrent run of the same section cannot eat the other's
rows. And it REFUSES outright when the run emitted zero findings but has
rows to close — that is a failed run far more often than a newly clean
section (SWEEP_AUTOCLOSE_FORCE=1 overrides).

Env escape hatches: SWEEP_AUTOCLOSE=0 disables; SWEEP_AUTOCLOSE=1 forces it
on for an ad-hoc run; SWEEP_AUTOCLOSE_DRYRUN=1 prints what WOULD close and
writes nothing; SWEEP_AUTOCLOSE_FORCE=1 overrides the zero-emit refusal.
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

    One instance per (script run × section). The cycle row is created LAZILY
    on the first emit() — never on construction, so a writer that emits
    nothing leaves no orphan row — and finalised on close().

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
        # Did this run join an ORCHESTRATED cycle, or mint its own?
        # sweep-run.py and the daily-operation fan-out always hand the cycle
        # id down (arg or SWEEP_CYCLE_ID); an operator running a check script
        # by hand does not. Auto-close defaults to firing only in the
        # orchestrated case, because only there is "the section ran to
        # completion, in full, as part of a sweep" a safe reading of a run
        # that emitted fewer findings than last time. An ad-hoc run may well
        # be scoped, exploratory, or degraded — see close().
        self._orchestrated = bool(
            cycle_id or os.environ.get("SWEEP_CYCLE_ID")
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
        # Every fingerprint this RUN emitted, in emit() order. This is the
        # authority for stale-finding auto-close: a row that this section
        # owns and did NOT re-emit is, by definition, no longer firing.
        self._emitted_fps: set[str] = set()
        self._run_started = None
        # Set by mark_incomplete() when the section knows its coverage was
        # partial (a scanner failed, a port-forward died). Auto-close is a
        # conclusion drawn from ABSENCE, so it must never run on a partial
        # result — the absence would be a tooling gap, not a resolution.
        # The AUTHORITATIVE list; `_incomplete_reason` is the joined view of it.
        # Kept as a list because reason details routinely contain "; "
        # themselves ("HTTP 429; tag list is empty"), so de-duplicating by
        # splitting the joined string on "; " matches against fragments and can
        # silently drop a genuinely distinct reason — the exact class of silent
        # loss this whole mechanism exists to prevent.
        self._incomplete_reasons: list[str] = []
        self._incomplete_reason: str | None = None

        if not self._enabled:
            return

        # Retry a transient blip rather than losing a whole completed run's
        # findings. If the DB is genuinely down this still raises — callers
        # that want to fail BEFORE doing the work should call preflight().
        self._conn = _connect_with_retry(self.dsn, autocommit=False)
        # The DB's own clock at the moment this section STARTED. Auto-close
        # only ever resolves rows last seen BEFORE this — so a concurrent or
        # out-of-band run of the same section (an operator running the script
        # by hand while a sweep is mid-flight) cannot have its just-written
        # rows resolved by the other run. Taken from the server, not the
        # local host, so clock skew between the Mac and the cluster cannot
        # widen the window.
        with self._conn.cursor() as _cur:
            _cur.execute("SELECT now()")
            self._run_started = _cur.fetchone()[0]
        self._conn.commit()

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
        # Recorded even when disabled so the no-op path stays behaviourally
        # identical, and so a caller can introspect what a dry run emitted.
        self._emitted_fps.add(fp)

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

    def mark_incomplete(self, reason: str) -> None:
        """Declare that this run's coverage was PARTIAL.

        Auto-close infers "resolved" from ABSENCE, so it is only sound when
        the section covered everything it normally covers. A section that
        knows it degraded (a scanner errored, a port-forward died, an API
        rate-limited) must say so — otherwise the missing findings look
        fixed. Call this and close() will skip auto-close and say why.

        ACCUMULATES. security-check.py alone has a dozen independent
        degrade paths, and a run that hits four of them must report four
        reasons — last-write-wins would show the operator one arbitrary
        dependency and hide the rest, which is exactly the diagnosis they
        need. Duplicate reasons collapse; order of first occurrence is kept.
        """
        reason = (reason or "").strip()
        if not reason:
            return
        if reason in self._incomplete_reasons:
            return
        self._incomplete_reasons.append(reason)
        self._incomplete_reason = "; ".join(self._incomplete_reasons)

    def _persist_incomplete(self) -> None:
        """Record this section's incompleteness on the shared cycle row.

        The veto is worthless if only this process knows about it.
        sweep-run.py runs its OWN auto-close SQL after every step
        (_auto_close_stale_findings), which is a separate implementation that
        cannot see our in-memory `_incomplete_reason` — so the writer would
        print "auto-close SKIPPED ... INCOMPLETE" and the orchestrator would
        close exactly those rows seconds later, in the same sweep. Persisting
        here is what makes the veto survive process boundaries.

        `notes` is TEXT, and up to five specialists finish concurrently, so the
        read-modify-write is done under a row lock in one transaction.
        """
        if self._conn is None:
            return
        try:
            with self._conn.cursor() as cur:
                # Guarantee the row exists (a clean-but-degraded section may
                # never have emitted, so the lazy insert never fired).
                cur.execute(
                    "INSERT INTO sweep_cycles (cycle_id, started_at, trigger, "
                    "git_head) VALUES (%s, now(), %s, %s) "
                    "ON CONFLICT (cycle_id) DO NOTHING",
                    (self._cycle_id, self._trigger, self._git_head),
                )
                cur.execute(
                    "SELECT notes FROM sweep_cycles WHERE cycle_id = %s FOR UPDATE",
                    (self._cycle_id,),
                )
                row = cur.fetchone()
                notes: dict = {}
                if row and row[0]:
                    try:
                        notes = json.loads(row[0])
                        if not isinstance(notes, dict):
                            notes = {"legacy_notes": row[0]}
                    except (ValueError, TypeError):
                        notes = {"legacy_notes": row[0]}
                incomplete = notes.get("incomplete")
                if not isinstance(incomplete, dict):
                    incomplete = {}
                incomplete[self.section] = self._incomplete_reason
                notes["incomplete"] = incomplete
                cur.execute(
                    "UPDATE sweep_cycles SET notes = %s WHERE cycle_id = %s",
                    (json.dumps(notes), self._cycle_id),
                )
            self._conn.commit()
            print(f"==> recorded section {self.section} as INCOMPLETE on cycle "
                  f"{self._cycle_id} — the orchestrator's auto-close will skip it too")
        except Exception as e:  # noqa: BLE001 — never lose the cycle close
            print(f"==> WARNING: could not persist incomplete state for "
                  f"{self.section}: {type(e).__name__}: {e}")
            try:
                self._conn.rollback()
            except Exception:  # noqa: BLE001
                pass

    def _autoclose_stale(self, *, dry_run: bool) -> list[tuple[str, str, str, str]]:
        """Resolve open findings THIS section owns that it did not re-emit.

        Returns (finding_id, severity, title, last_seen) for each row closed
        (or, under dry_run, that WOULD close). Never touches another
        section's rows, and never touches a row this run re-emitted.
        """
        if self._conn is None:
            return []
        fps = list(self._emitted_fps)
        sql_where = """
             WHERE resolved_at IS NULL
               AND section = %s
               AND NOT (fingerprint = ANY(%s))
               AND last_seen < %s
        """
        with self._conn.cursor() as cur:
            if dry_run:
                cur.execute(
                    "SELECT finding_id, severity, title, last_seen "
                    "FROM sweep_findings" + sql_where +
                    " ORDER BY severity, finding_id",
                    (self.section, fps, self._run_started),
                )
            else:
                cur.execute(
                    """
                    UPDATE sweep_findings
                       SET resolved_at = now(),
                           status = 'resolved',
                           resolved_commit = COALESCE(
                               NULLIF(%s, ''), resolved_commit)
                    """ + sql_where +
                    " RETURNING finding_id, severity, title, last_seen",
                    (self._git_head or "", self.section, fps, self._run_started),
                )
            rows = cur.fetchall()
        if not dry_run:
            self._conn.commit()
        return [(r[0], r[1], r[2], str(r[3])) for r in rows]

    def _report_autoclose(self, rows, *, dry_run: bool) -> None:
        """Print what closed and WHY, in the shape the reconcile step uses.

        AR-tagged / accepted rows are reported in their own block rather than
        folded into the bulk count — an operator-accepted risk disappearing
        must be visible, never silent.
        """
        verb = "WOULD auto-close" if dry_run else "auto-closed"
        accepted = [r for r in rows if r[1] == "accepted" or "[AR-" in r[2]]
        plain = [r for r in rows if r not in accepted]
        if plain:
            print(f"==> {verb} {len(plain)} {self.section} finding(s) that this "
                  f"run did not re-emit (section completed, so absence == resolved):")
            for fid, sev, title, seen in plain[:20]:
                print(f"      ✓ resolved {self.section}/{fid} [{sev}] "
                      f"(last fired {seen[:19]}): {title[:80]}")
            if len(plain) > 20:
                print(f"      … and {len(plain) - 20} more")
        if accepted:
            print(f"==> {verb} {len(accepted)} ACCEPTED/AR-tagged {self.section} "
                  f"finding(s) — the accepted risk stopped firing, review whether "
                  f"the AR is still needed:")
            for fid, sev, title, seen in accepted:
                print(f"      ✓ resolved {self.section}/{fid} [{sev}] "
                      f"(last fired {seen[:19]}): {title[:80]}")

    def close(self, *, verdict: str | None = None,
              section_complete: bool | None = None) -> None:
        """Finalise the cycle row, and auto-close this section's stale findings.

        verdict is one of: green | yellow | red (or None to leave unset).
        Idempotent for the same cycle — if called twice, last call wins
        on finished_at and verdict.

        AUTO-CLOSE (added 2026-08-18). A finding that this section stops
        emitting is resolved, and it is resolved on the next successful run
        of THIS section — not whenever someone remembers to run a correctly
        scoped `sweep-run.py --reconcile-only --ran <sections>`. That
        orchestrator-only design is what left 78 obsolete app-template
        chart-major criticals open after the 3.7.3→5.1.0 migration: the
        version section completed at 13:52 and never re-emitted them, but
        the only reconcile passes that day ran at 13:33 and 13:37 — BEFORE
        it finished — so a human had to hand-resolve 82 rows. The writer is
        the one place that always knows the section, the exact fingerprint
        set it just emitted, and whether the run finished.

        `section_complete` is the safety gate. When None it is INFERRED as
        `verdict is not None`, which cleanly separates the two existing call
        shapes with no call-site change:
          * the caller's own `close(verdict=...)` at the end of a full run
            — a verdict only exists once the section computed a result;
          * `__exit__`'s bare `close()` on the exception path — a crashed,
            partial run, which must NOT conclude anything from absence.
        A section can also veto explicitly via mark_incomplete().

        It also only fires for an ORCHESTRATED run — one that was handed a
        cycle id by sweep-run.py or the daily-operation fan-out. A check
        script an operator runs by hand mints its own cycle id and closes
        nothing, because an ad-hoc run may be scoped, exploratory or
        degraded, and auto-close reasons from ABSENCE. `SWEEP_AUTOCLOSE=1`
        opts an ad-hoc run in.

        Escape hatches (env): SWEEP_AUTOCLOSE=0 disables it entirely;
        SWEEP_AUTOCLOSE=1 forces it on even for an ad-hoc run;
        SWEEP_AUTOCLOSE_DRYRUN=1 reports what WOULD close and writes nothing.
        """
        if not self._enabled or self._conn is None:
            return

        if section_complete is None:
            section_complete = verdict is not None

        mode = os.environ.get("SWEEP_AUTOCLOSE", "")
        if mode == "0":
            pass  # kill-switch: leave stale rows for a human
        elif mode != "1" and not self._orchestrated:
            print(f"==> auto-close SKIPPED for section {self.section}: this run "
                  f"minted its own cycle id, so it is an AD-HOC run, not part of "
                  f"a sweep — it may be scoped or exploratory, and a smaller "
                  f"result set would wrongly read as 'fixed'. Set "
                  f"SWEEP_AUTOCLOSE=1 to opt in, or SWEEP_AUTOCLOSE_DRYRUN=1 to "
                  f"preview")
        elif self._incomplete_reason:
            print(f"==> auto-close SKIPPED for section {self.section}: run "
                  f"declared INCOMPLETE ({self._incomplete_reason}) — its open "
                  f"findings are left untouched, a coverage gap is not a fix")
            self._persist_incomplete()
        elif not section_complete:
            print(f"==> auto-close SKIPPED for section {self.section}: run did "
                  f"not complete (no verdict) — its open findings are left "
                  f"untouched, a failed run is not a resolution")
        else:
            dry = os.environ.get("SWEEP_AUTOCLOSE_DRYRUN", "0") == "1"
            try:
                # CIRCUIT BREAKER. A section that emitted NOTHING and yet has
                # open rows to close is the signature of a broken run, not a
                # clean one: the script fell over before producing findings,
                # its evidence file was missing or stale, or its data source
                # was unreachable. A genuinely clean section that just fixed
                # its last finding is indistinguishable from that at this
                # layer, so it costs one forced run — cheap next to silently
                # resolving a whole section. Not a substitute for
                # mark_incomplete(); a backstop for the scripts that do not
                # yet call it.
                probe = self._autoclose_stale(dry_run=True) if not self._emitted_fps else None
                if probe and os.environ.get("SWEEP_AUTOCLOSE_FORCE", "0") != "1":
                    print(f"==> auto-close REFUSED for section {self.section}: the "
                          f"run emitted 0 findings but {len(probe)} would close. "
                          f"A section that produced nothing has almost certainly "
                          f"failed rather than gone clean. Verify, then re-run "
                          f"with SWEEP_AUTOCLOSE_FORCE=1 if the section really is "
                          f"clean. Would have closed:")
                    self._report_autoclose(probe, dry_run=True)
                    rows = []
                else:
                    rows = self._autoclose_stale(dry_run=dry)
                if rows:
                    self._report_autoclose(rows, dry_run=dry)
            except Exception as e:  # noqa: BLE001 — never lose the cycle close
                print(f"==> auto-close failed for section {self.section}: "
                      f"{type(e).__name__}: {e}")
                try:
                    self._conn.rollback()
                except Exception:  # noqa: BLE001
                    pass

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


# ---------------------------------------------------------------------------
# Degraded-coverage recorder
# ---------------------------------------------------------------------------


class DegradationLog:
    """Collects graceful-degradation events during a run, then vetoes auto-close.

    This is NOT a second mechanism — it is a collection point that terminates
    in `FindingsWriter.mark_incomplete()`. health-check.py can get away with a
    single local `incomplete` variable because it has exactly one degrade
    path (a missing/stale issues file). The other three audit scripts degrade
    gracefully in a dozen independent places, buried inside section functions
    that have no access to the writer (it is only constructed at the very end
    of main()). They record here as they go; main() calls `apply(writer)` once.

    Why any of this matters: auto-close reasons from ABSENCE. If Elasticsearch
    is unreachable, the attack-pattern section emits nothing — and without a
    veto, `close(verdict=...)` reads that silence as "every one of those
    findings got fixed" and resolves them. A monitoring outage would quietly
    clear the security backlog. The zero-emit circuit breaker only catches a
    TOTAL wipeout; partial degradation has to be declared explicitly.

    The veto is SECTION-scoped, because that is the granularity auto-close
    itself works at: one degraded dependency suppresses auto-close for the
    whole section, and the section still completes and reports everything it
    *could* measure. Over-suppressing costs a stale row until the next clean
    run; under-suppressing loses real findings.

    Usage:
        DEGRADED = DegradationLog("security", printer=warn)
        ...
        except Exception as e:
            DEGRADED.record("s6_attack_patterns", "Elasticsearch", repr(e))
            return OK, findings, body
        ...
        with FindingsWriter(...) as writer:
            emit(...)
            DEGRADED.apply(writer)
            writer.close(verdict=verdict)
    """

    def __init__(self, section: str, printer=None):
        self.section = section
        self._reasons: list[str] = []
        # Default printer keeps this usable from scripts with no colour helper.
        self._printer = printer or (lambda msg: print(msg))

    def record(self, scope: str, dependency: str, detail: str = "") -> None:
        """Note that `scope` could not fully run because `dependency` failed.

        `scope` should be the subsection slug / function name the operator
        would grep for; `dependency` the external thing that was unavailable.
        Logged immediately — the operator must be able to see the veto being
        armed at the moment it happens, not only in the summary at the end.
        """
        reason = f"{scope}: {dependency} unavailable"
        if detail:
            reason += f" ({_truncate(str(detail), 160)})"
        if reason in self._reasons:
            return
        self._reasons.append(reason)
        self._printer(
            f"  ⚠ DEGRADED — {reason}. Coverage for this check is partial, so "
            f"stale-finding auto-close will be VETOED for the entire "
            f"'{self.section}' section (a coverage gap is not a fix)."
        )

    @property
    def reasons(self) -> list[str]:
        return list(self._reasons)

    def __bool__(self) -> bool:
        return bool(self._reasons)

    def __len__(self) -> int:
        return len(self._reasons)

    def reason_text(self) -> str:
        return "; ".join(self._reasons)

    def apply(self, writer: "FindingsWriter") -> bool:
        """Hand the accumulated reasons to the writer. Returns True if vetoed.

        Safe to call unconditionally; a run with no degradation is a no-op and
        auto-close proceeds normally.
        """
        if not self._reasons:
            return False
        writer.mark_incomplete(self.reason_text())
        self._printer(
            f"  ⚠ {len(self._reasons)} degraded dependency/dependencies this run "
            f"— auto-close vetoed for section '{self.section}':"
        )
        for r in self._reasons:
            self._printer(f"      • {r}")
        return True


def _truncate(s: str, n: int) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1] + "…"
