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
# ref like `postgres:17.10-bookworm`, a resource name, an alertname).
# Everything else in the line is human prose that gets reworded.
_RE_BACKTICK  = re.compile(r"`([^`]+)`")
_RE_ARTAG     = re.compile(r"\[AR-\d+\]\s*", re.I)

# WHICH finding-about-this-object is this? Two findings can name the same image
# and mean different things — "there is a fix, take it" vs "there is no fix".
# That distinction is part of the identity and must be in the anchor.
#
# It USED to be carried by the `[AR-0NN]` tag set, which was wrong: an AR tag is
# a SUPPRESSION DECISION, i.e. presentation, and folding it into the identity
# made an unchanged finding change identity whenever an AR was added, removed or
# re-worded. Observed 2026-08-18: F-094be167 was born 08-16, "resolved" 08-17
# when AR-063 started matching (forking F-e14cda04), and re-appeared 08-18 when
# AR-063's wording lapsed — one problem, three rows, no change in the world.
#
# These markers are matched verbatim, deliberately NOT parsed from prose — the
# same explicit-marker discipline as risk_model.S4_POLICY_MARKERS. Measured
# against all 296 open rows: this reproduces the AR-tag set's discrimination
# exactly (296 -> 296 distinct fingerprints, zero merges) while being completely
# invariant to AR tagging.
#
# ORDER MATTERS: first match wins, so the most specific marker goes first.
# Adding a marker CHANGES IDENTITY for matching findings — run
# `runbooks/refingerprint-findings.py` after any edit here.
_KIND_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("nofix",   ("with no upstream fix",)),
    ("rebuild", ("but already on the newest upstream tag",
                 "already the newest upstream tag")),
)


def _kind_token(title: str) -> str:
    """Which finding-about-this-object this is. '' = the ordinary case."""
    low = title.lower()
    for token, markers in _KIND_MARKERS:
        if any(m in low for m in markers):
            return token
    return ""


def strip_ar_tags(title: str) -> str:
    """Title with every `[AR-0NN]` tag removed. Identity is computed on this.

    An AR tag is a suppression DECISION applied on top of a finding, not a
    property of the finding. It is presentation; it must never reach the
    fingerprint.
    """
    return _RE_ARTAG.sub("", title).strip()


def _stable_anchor(title: str) -> str | None:
    """A prose-independent identity for `title`, or None if it has no anchor.

    Built from the backtick-quoted identifiers plus a KIND token. Returns None
    when the title contains no backticked span, so ordinary sentence-shaped
    findings fall back to the normalized-title fingerprint.

    Why this exists: the previous fingerprint hashed the whole normalized
    PROSE, so rewording a message forked a brand-new finding row for an
    unchanged problem (2026-08: a single title reword split 20 image findings
    into 39 rows). Backtick content is kept VERBATIM (digits included) — the
    image *version* is part of the identity: `postgres:17.10-bookworm` and
    `postgres:17.11-bookworm` are genuinely different findings, and this is
    the "hash on image@section, not on rendered prose" fix.

    The second component keeps two DISTINCT findings about the SAME object
    apart — an image's fixable line vs its no-upstream-fix line. That job used
    to belong to the `[AR-0NN]` tag set, which made identity depend on
    suppression state; see the _KIND_MARKERS comment above for why that was a
    defect and what replaced it. AR tags are stripped before anchoring, so
    tagging, re-tagging and un-tagging are all identity-preserving.
    """
    bare = strip_ar_tags(title)
    spans = _RE_BACKTICK.findall(bare)
    if not spans:
        return None
    ids = "``".join(_RE_WS.sub(" ", s.strip().lower()) for s in spans)
    return f"{ids}|{_kind_token(bare)}"


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
        # Prose fallback: strip AR tags here too, or a tagged sentence-shaped
        # finding forks from its untagged self exactly as the anchored ones did.
        basis = _normalize(strip_ar_tags(title))
    parts = (section, subsection or "", basis)
    blob = "|".join(parts).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def finding_id_from_fp(fp: str) -> str:
    """Stable DB id derived from fingerprint. Format: F-<first-8-hex>."""
    return f"F-{fp[:8]}"


# ---------------------------------------------------------------------------
# Per-component coverage scope
# ---------------------------------------------------------------------------
# A section-wide veto is correct in PRINCIPLE — a coverage gap is not a fix —
# but wrong in GRANULARITY when the gap is one leaf. Three consecutive cycles
# were vetoed by a single unresolvable image (docker.elastic.co, then Docker
# Hub 429s, then a public.ecr.aws 429 on one image), each time suppressing
# auto-close for the OTHER ~180 components the run resolved perfectly, so ~14
# confirmed-stale rows stayed open and the board permanently overstated the
# estate.
#
# The fix is to make the veto say WHAT it could not cover, so auto-close can
# skip exactly those rows and proceed for the rest. That is only sound when
# the degradation is at LEAF resolution — one image's tag listing failed while
# enumeration and every other lookup succeeded. A degradation ABOVE the leaf
# (the HelmRelease parse failed, a Helm repo index is down, `gh` is broken) is
# not attributable to one component and must stay a section-wide veto; that is
# why `component=` is opt-in per call site rather than inferred.

COMPONENT_KINDS = ("image", "chart", "host", "app")


def component_key(kind: str, ident: str) -> str:
    """Canonical `kind:ident` component key. Lowercased; tag/digest stripped.

    `ident` is the thing an operator would name — an image repository, a chart
    name, an external host. Tag and digest are stripped so a component stays
    the same identity across the very version bump the finding is about.
    """
    kind = (kind or "").strip().lower()
    if kind not in COMPONENT_KINDS:
        raise ValueError(f"component kind {kind!r} not one of {COMPONENT_KINDS}")
    ident = (ident or "").strip().lower()
    ident = ident.split("@", 1)[0]           # drop @sha256:...
    if "/" in ident:                          # drop :tag, but not a :port host
        head, _, tail = ident.rpartition("/")
        if ":" in tail:
            ident = f"{head}/{tail.split(':', 1)[0]}"
    elif ":" in ident and not ident.split(":", 1)[1].isdigit():
        ident = ident.split(":", 1)[0]
    return f"{kind}:{ident.strip('/')}"


def _row_idents(title: str, metadata: dict | None) -> set[str]:
    """Identifiers a stored finding row can be attributed to.

    Drawn from metadata FIRST (structured, written by the emitter) and from
    the title second (covers rows written before the emitter carried the
    component, which is precisely the stale-row population auto-close acts on).
    """
    meta = metadata if isinstance(metadata, dict) else {}
    out: set[str] = set()
    for key in ("component", "repository", "chart", "host", "image", "name"):
        val = meta.get(key)
        if isinstance(val, str) and val.strip():
            v = val.strip().lower()
            if key == "component":
                # Already a `kind:ident` key — compare on the ident half, or a
                # row stamped by the current emitter would fail to match the
                # very component key that stamped it.
                v = v.partition(":")[2] or v
            out.add(v.split("@", 1)[0])
            out.add(v.split("@", 1)[0].rsplit(":", 1)[0] if "/" in v or ":" in v else v)
    if title:
        t = title.strip().lower()
        # `name: image repo tag -> tag` / `name (host): ...` / `name: chart ...`
        head = t.split(":", 1)[0].split(" (", 1)[0].strip()
        if head:
            out.add(head)
        for span in _RE_BACKTICK.findall(title):
            out.add(span.strip().lower())
    return {o for o in out if o}


def finding_matches_component(component: str, title: str,
                              metadata: dict | None) -> bool:
    """Is this stored finding row ABOUT `component`?

    Deliberately generous: a false positive costs one stale row surviving to
    the next clean run, a false negative silently resolves a finding whose
    component was never actually checked. Erring toward "keep it open" is the
    only safe direction here.
    """
    _, _, ident = component.partition(":")
    ident = ident.strip().lower()
    if len(ident) < 3:
        return False
    idents = _row_idents(title, metadata)
    if ident in idents:
        return True
    # Structured miss -> fall back to the rendered title. Bounded by the
    # length guard above so a short ident cannot match half the estate.
    if ident in (title or "").lower():
        return True
    # `library/redis` in the uncovered set should also hold a row that only
    # ever recorded `redis`.
    tail = ident.rsplit("/", 1)[-1]
    return len(tail) >= 4 and tail in idents


def partition_by_uncovered(rows, uncovered, *, title_idx: int = 2,
                           meta_idx: int = 4):
    """Split candidate auto-close rows into (closeable, held).

    `rows` are tuples shaped (finding_id, severity, title, last_seen, metadata).
    `held` rows belong to a component this run could not resolve, so their
    absence proves nothing and they stay open. Returned as
    (closeable, [(row, component), ...]).

    Lives here, at module scope, because there are TWO auto-close
    implementations — this writer's and sweep-run.py's post-step SQL — and a
    scope rule enforced in only one of them is no scope rule at all.
    """
    uncovered = list(uncovered or [])
    if not uncovered:
        return list(rows), []
    closeable, held = [], []
    for r in rows:
        meta = r[meta_idx] if len(r) > meta_idx else None
        hit = next(
            (c for c in uncovered
             if finding_matches_component(c, r[title_idx], meta)),
            None,
        )
        (held.append((r, hit)) if hit else closeable.append(r))
    return closeable, held


def uncovered_from_notes(notes_json) -> dict[str, dict[str, str]]:
    """Read `notes.uncovered` -> {section: {component: reason}} defensively."""
    if not notes_json:
        return {}
    try:
        notes = json.loads(notes_json) if isinstance(notes_json, str) else notes_json
    except (ValueError, TypeError):
        return {}
    if not isinstance(notes, dict):
        return {}
    unc = notes.get("uncovered")
    if not isinstance(unc, dict):
        return {}
    out: dict[str, dict[str, str]] = {}
    for sec, comps in unc.items():
        if isinstance(comps, dict):
            out[sec] = {str(k): str(v) for k, v in comps.items()}
        elif isinstance(comps, list):
            out[sec] = {str(k): "" for k in comps}
    return out


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
        # Set by mark_uncovered() when the section knows EXACTLY WHICH
        # components it failed to resolve. Unlike _incomplete_reasons (which
        # vetoes the whole section), this narrows the veto to the named
        # components: the section still completed, so absence is a valid
        # "resolved" signal for everything it DID cover. component -> reason.
        self._uncovered: dict[str, str] = {}

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

    def mark_uncovered(self, component: str, reason: str) -> None:
        """Declare that THIS COMPONENT could not be resolved, but the rest could.

        The narrow sibling of `mark_incomplete()`. Use it when the failure is
        attributable to one leaf — a single image's tag listing 429'd — and the
        section's enumeration and every other lookup completed. close() then
        auto-closes normally EXCEPT for findings about the named components,
        which are left open because their absence is a coverage gap, not a fix.

        Do NOT use it for a failure above the leaf (a Helm repo index, a broken
        `gh`, a dead port-forward): those degrade an unknown set of components,
        and the honest answer there is still `mark_incomplete()`.

        ACCUMULATES, first reason per component wins.
        """
        component = (component or "").strip().lower()
        reason = (reason or "").strip()
        if not component or ":" not in component:
            # An unparseable key would silently scope-match NOTHING and quietly
            # widen auto-close. Degrade to the safe, section-wide veto instead.
            self.mark_incomplete(reason or f"unattributable coverage gap ({component!r})")
            return
        self._uncovered.setdefault(component, reason)

    def _persist_uncovered(self) -> None:
        """Publish the per-component scope onto the shared cycle row.

        Same reason `_persist_incomplete` exists: sweep-run.py runs its own
        auto-close SQL after every step and cannot see our in-memory state, so
        a scope enforced only here would be undone seconds later by the
        orchestrator closing exactly the rows we held back.
        """
        if self._conn is None or not self._uncovered:
            return
        try:
            with self._conn.cursor() as cur:
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
                unc = notes.get("uncovered")
                if not isinstance(unc, dict):
                    unc = {}
                merged = dict(unc.get(self.section) or {}) if isinstance(
                    unc.get(self.section), dict) else {}
                merged.update(self._uncovered)
                unc[self.section] = merged
                notes["uncovered"] = unc
                cur.execute(
                    "UPDATE sweep_cycles SET notes = %s WHERE cycle_id = %s",
                    (json.dumps(notes), self._cycle_id),
                )
            self._conn.commit()
            print(f"==> recorded {len(self._uncovered)} UNCOVERED component(s) for "
                  f"section {self.section} on cycle {self._cycle_id} — the "
                  f"orchestrator's auto-close will hold those rows back too")
        except Exception as e:  # noqa: BLE001 — never lose the cycle close
            print(f"==> WARNING: could not persist uncovered scope for "
                  f"{self.section}: {type(e).__name__}: {e}. Falling back to a "
                  f"SECTION-WIDE veto rather than closing rows the orchestrator "
                  f"cannot hold back.")
            self.mark_incomplete(
                f"could not publish per-component coverage scope "
                f"({len(self._uncovered)} uncovered)")
            try:
                self._conn.rollback()
            except Exception:  # noqa: BLE001
                pass

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

    def _autoclose_stale(self, *, dry_run: bool) -> list[tuple[str, str, str, str, dict]]:
        """Resolve open findings THIS section owns that it did not re-emit.

        Returns (finding_id, severity, title, last_seen, metadata) for each row
        closed (or, under dry_run, that WOULD close). Never touches another
        section's rows, and never touches a row this run re-emitted.

        Rows about a component recorded via `mark_uncovered()` are HELD: the
        run never got an answer for that component, so its silence is a
        coverage gap and closing on it would be exactly the bug the veto
        exists to prevent. Everything else closes normally — one unresolvable
        image must not speak for the other ~180.

        Candidates are SELECTed and filtered in Python, then updated by
        primary key, rather than expressed as one UPDATE ... WHERE. The scope
        predicate is a metadata-and-title match that SQL cannot state without
        duplicating `finding_matches_component`, and a second, drifting copy of
        that rule is precisely what makes a veto stop working.
        """
        if self._conn is None:
            return []
        fps = list(self._emitted_fps)
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, finding_id, severity, title, last_seen, metadata
                  FROM sweep_findings
                 WHERE resolved_at IS NULL
                   AND section = %s
                   AND NOT (fingerprint = ANY(%s))
                   AND last_seen < %s
                 ORDER BY severity, finding_id
                """,
                (self.section, fps, self._run_started),
            )
            candidates = [
                (r[0], (r[1], r[2], r[3], str(r[4]), r[5] or {}))
                for r in cur.fetchall()
            ]

            closeable, held = partition_by_uncovered(
                [c[1] for c in candidates], sorted(self._uncovered),
                title_idx=2, meta_idx=4,
            )
            if held:
                print(f"==> auto-close HELD BACK {len(held)} {self.section} "
                      f"finding(s) whose component this run could not resolve "
                      f"(a coverage gap is not a fix):")
                for row, comp in held[:20]:
                    print(f"      ⏸ kept open {self.section}/{row[0]} [{row[1]}] "
                          f"— uncovered {comp}: {row[2][:70]}")
                if len(held) > 20:
                    print(f"      … and {len(held) - 20} more")

            if dry_run or not closeable:
                return closeable

            close_fids = {r[0] for r in closeable}
            ids = [pk for pk, row in candidates if row[0] in close_fids]
            cur.execute(
                """
                UPDATE sweep_findings
                   SET resolved_at = now(),
                       status = 'resolved',
                       resolved_commit = COALESCE(NULLIF(%s, ''), resolved_commit)
                 WHERE id = ANY(%s)
                   AND resolved_at IS NULL
                """,
                (self._git_head or "", ids),
            )
        self._conn.commit()
        return closeable

    def _report_autoclose(self, rows, *, dry_run: bool) -> None:
        """Print what closed and WHY, in the shape the reconcile step uses.

        AR-tagged / accepted rows are reported in their own block rather than
        folded into the bulk count — an operator-accepted risk disappearing
        must be visible, never silent.
        """
        verb = "WOULD auto-close" if dry_run else "auto-closed"
        # Rows are (finding_id, severity, title, last_seen[, metadata]) — the
        # metadata tail is optional so a caller that stubs this out with the
        # older 4-tuple shape still reports correctly.
        acc_idx = [i for i, r in enumerate(rows)
                   if r[1] == "accepted" or "[AR-" in r[2]]
        accepted = [rows[i] for i in acc_idx]
        plain = [r for i, r in enumerate(rows) if i not in set(acc_idx)]

        def _line(row) -> str:
            fid, sev, title, seen = row[0], row[1], row[2], str(row[3])
            return (f"      ✓ resolved {self.section}/{fid} [{sev}] "
                    f"(last fired {seen[:19]}): {title[:80]}")

        if plain:
            print(f"==> {verb} {len(plain)} {self.section} finding(s) that this "
                  f"run did not re-emit (section completed, so absence == resolved):")
            for row in plain[:20]:
                print(_line(row))
            if len(plain) > 20:
                print(f"      … and {len(plain) - 20} more")
        if accepted:
            print(f"==> {verb} {len(accepted)} ACCEPTED/AR-tagged {self.section} "
                  f"finding(s) — the accepted risk stopped firing, review whether "
                  f"the AR is still needed:")
            for row in accepted:
                print(_line(row))

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
            # Publish the per-component scope BEFORE closing anything. If this
            # fails it converts itself into a section-wide veto, which must be
            # honoured here rather than discovered after the UPDATE.
            self._persist_uncovered()
            if self._incomplete_reason:
                print(f"==> auto-close SKIPPED for section {self.section}: run "
                      f"declared INCOMPLETE ({self._incomplete_reason}) — its "
                      f"open findings are left untouched, a coverage gap is "
                      f"not a fix")
                self._persist_incomplete()
                self._finalise_cycle_row(verdict)
                return
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

        self._finalise_cycle_row(verdict)

    def _finalise_cycle_row(self, verdict: str | None) -> None:
        """Stamp finished_at/verdict and tear the connection down. Idempotent."""
        if self._conn is None:
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

    GRANULARITY (revised 2026-08-19). The veto used to be SECTION-scoped
    unconditionally, and that over-suppressed badly: a single unresolvable
    image vetoed auto-close for the whole version section for three
    consecutive cycles, leaving ~14 confirmed-stale rows open while the other
    ~180 components were resolved perfectly. A call site that can name the ONE
    component it failed on now passes `component=`, and the veto narrows to
    that leaf. A call site that cannot — because the failure sits above the
    leaf (a Helm repo index, a dead `gh`, an unreachable Elasticsearch) —
    omits it and gets the section-wide veto exactly as before, because there
    the affected component set is genuinely unknown.

    The narrowing is bounded: past MAX_SCOPED_COMPONENTS, or past
    MAX_UNCOVERED_FRACTION of the attempted universe, `apply()` abandons the
    per-component scope and reverts to the section-wide veto. A broad outage
    stays a broad outage however precisely its individual failures were
    attributed. Over-suppressing costs a stale row until the next clean run;
    under-suppressing loses real findings — so every ambiguity resolves toward
    the wider veto.

    Usage:
        DEGRADED = DegradationLog("security", printer=warn)
        ...
        except Exception as e:
            DEGRADED.record("s6_attack_patterns", "Elasticsearch", repr(e))
            return OK, findings, body
        ...
        # attributable to one leaf -> narrow scope, section still auto-closes
        DEGRADED.record("image ghcr.io/foo/bar", "ghcr.io (HTTP 429)",
                        component=component_key("image", "ghcr.io/foo/bar"))
        ...
        with FindingsWriter(...) as writer:
            emit(...)
            DEGRADED.note_universe(len(all_components))
            DEGRADED.apply(writer)
            writer.close(verdict=verdict)
    """

    # A per-component scope is only a narrowing of the veto while the
    # uncovered set stays SMALL relative to what the section covers. Past
    # these bounds the run is not "complete except for a leaf" — it is a broad
    # outage wearing per-component clothing, and the honest answer reverts to
    # the section-wide veto. Both bounds are checked; the ratio needs a
    # denominator (`universe`), the absolute cap works without one.
    MAX_SCOPED_COMPONENTS = 10
    MAX_UNCOVERED_FRACTION = 0.10

    def __init__(self, section: str, printer=None):
        self.section = section
        self._reasons: list[str] = []
        # component -> reason, for degradations attributable to ONE leaf.
        self._uncovered: dict[str, str] = {}
        # How many components this section attempted to resolve. Set by the
        # caller via note_universe(); None means "unknown", which disables the
        # ratio bound and leaves only the absolute cap.
        self._universe: int | None = None
        # Default printer keeps this usable from scripts with no colour helper.
        self._printer = printer or (lambda msg: print(msg))

    def note_universe(self, n: int) -> None:
        """Record how many components this run attempted (the denominator).

        Without it the coverage FRACTION is unknowable and only the absolute
        cap applies — which is safe but blunt: 8 uncovered out of 12 would
        still scope rather than veto.
        """
        try:
            n = int(n)
        except (TypeError, ValueError):
            return
        if n > 0:
            self._universe = n

    def record(self, scope: str, dependency: str, detail: str = "",
               *, component: str | None = None) -> None:
        """Note that `scope` could not fully run because `dependency` failed.

        `scope` should be the subsection slug / function name the operator
        would grep for; `dependency` the external thing that was unavailable.
        Logged immediately — the operator must be able to see the veto being
        armed at the moment it happens, not only in the summary at the end.

        `component` (a `component_key()` string) narrows the veto to that one
        leaf. Pass it ONLY when the failure is attributable to a single
        component and the section's enumeration plus every other lookup
        completed — a failed image-tag listing qualifies, a dead Helm repo
        index or a broken `gh` does not, because those degrade an unknown set
        of components and the honest answer for them is still a section-wide
        veto. Omitting it keeps the original behaviour exactly.
        """
        reason = f"{scope}: {dependency} unavailable"
        if detail:
            reason += f" ({_truncate(str(detail), 160)})"
        if component:
            if component in self._uncovered:
                return
            self._uncovered[component] = reason
            self._printer(
                f"  ⚠ DEGRADED — {reason}. Coverage is partial for THIS "
                f"COMPONENT only ({component}); stale-finding auto-close will "
                f"hold its findings open and proceed for the rest of the "
                f"'{self.section}' section."
            )
            return
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

    @property
    def uncovered(self) -> dict[str, str]:
        return dict(self._uncovered)

    def __bool__(self) -> bool:
        return bool(self._reasons) or bool(self._uncovered)

    def __len__(self) -> int:
        return len(self._reasons) + len(self._uncovered)

    def reason_text(self) -> str:
        return "; ".join(self._reasons)

    def _breaches_coverage_floor(self) -> str | None:
        """Is the uncovered set too big to still call this run 'complete'?

        Returns the operator-facing explanation, or None when scoping holds.
        """
        n = len(self._uncovered)
        if n > self.MAX_SCOPED_COMPONENTS:
            return (f"{n} components uncovered (> {self.MAX_SCOPED_COMPONENTS}) "
                    f"— too many to treat as isolated leaves")
        if self._universe:
            frac = n / self._universe
            if frac > self.MAX_UNCOVERED_FRACTION:
                return (f"{n}/{self._universe} components uncovered "
                        f"({frac:.0%} > {self.MAX_UNCOVERED_FRACTION:.0%}) "
                        f"— coverage fell below the floor")
        return None

    def apply(self, writer: "FindingsWriter") -> bool:
        """Hand the accumulated degradation to the writer. Returns True if VETOED.

        Safe to call unconditionally; a run with no degradation is a no-op and
        auto-close proceeds normally.

        Three outcomes, in order of severity:
          * any UNATTRIBUTABLE degradation -> section-wide veto (unchanged
            behaviour: the affected component set is unknown, so nothing can
            be scoped around it);
          * an attributable set that breaches the coverage floor -> section-wide
            veto, with the uncovered components reported. A broad registry
            outage is a broad registry outage no matter how precisely each of
            its failures was attributed;
          * otherwise -> per-component scope. The section completes, auto-close
            runs, and only the named components' findings are held open.
        Returns True in the first two cases.
        """
        if not self._reasons and not self._uncovered:
            return False

        if self._reasons:
            # Mixed run: fold the scoped reasons into the section-wide veto
            # rather than dropping them, or the operator loses the detail.
            all_reasons = list(self._reasons) + [
                f"{c} -> {r}" for c, r in sorted(self._uncovered.items())]
            writer.mark_incomplete("; ".join(all_reasons))
            self._printer(
                f"  ⚠ {len(all_reasons)} degraded dependency/dependencies this run "
                f"— auto-close vetoed for section '{self.section}':"
            )
            for r in all_reasons:
                self._printer(f"      • {r}")
            return True

        breach = self._breaches_coverage_floor()
        if breach:
            # The full list goes to the operator's console below; the DB-bound
            # reason stays bounded — a 60-component outage would otherwise
            # write multiple kilobytes into sweep_cycles.notes.
            listed = sorted(self._uncovered)[:8]
            tail = ("" if len(self._uncovered) <= len(listed)
                    else f" … and {len(self._uncovered) - len(listed)} more")
            writer.mark_incomplete(f"{breach}: " + ", ".join(listed) + tail)
            self._printer(
                f"  ⚠ per-component scope ABANDONED for section "
                f"'{self.section}' — {breach}. Auto-close is vetoed for the "
                f"whole section. Uncovered:"
            )
            for c, r in sorted(self._uncovered.items()):
                self._printer(f"      • {c}: {r}")
            return True

        for comp, reason in sorted(self._uncovered.items()):
            writer.mark_uncovered(comp, reason)
        denom = f"/{self._universe}" if self._universe else ""
        self._printer(
            f"  ⚠ {len(self._uncovered)}{denom} component(s) uncovered this run "
            f"— auto-close proceeds for section '{self.section}' but HOLDS "
            f"OPEN the findings of:"
        )
        for c, r in sorted(self._uncovered.items()):
            self._printer(f"      • {c}: {r}")
        return False


def _truncate(s: str, n: int) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1] + "…"
