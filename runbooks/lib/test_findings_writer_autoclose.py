"""Unit tests for FindingsWriter's stale-finding auto-close gate.

Proves the SAFETY contract without a database: the connection and cursor are
fakes that record the SQL they were handed, so each test asserts the DECISION
(did auto-close run at all? did it scope to this section? did it spare the
fingerprints this run re-emitted?) rather than a DB side effect.

The behaviour under test exists because of the 2026-08-18 app-template
incident: the version section completed, stopped emitting 78 obsolete
`chart 3.7.3 → 5.1.0` criticals, and nothing closed them — auto-close lived
only in the orchestrator's separately-sequenced reconcile step, whose passes
that day ran BEFORE the version section finished. A human hand-resolved 82
rows. Auto-close now runs in the writer, which always knows the section, the
fingerprints just emitted, and whether the run completed.

Run:  python3 runbooks/lib/test_findings_writer_autoclose.py
  or: python3 -m pytest runbooks/lib/test_findings_writer_autoclose.py -q
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "findings_writer", str(Path(__file__).with_name("findings_writer.py")))
fw = importlib.util.module_from_spec(_spec)
sys.modules["findings_writer"] = fw
_spec.loader.exec_module(fw)


# One plausible open, stale row for the candidate SELECT to return. Auto-close
# is now a SELECT-then-filter-then-UPDATE-by-id (the per-component coverage
# scope is a metadata/title match SQL cannot express without a second, drifting
# copy of the rule), so a fake that returns no candidates would make every
# auto-close look like a no-op.
# Shape: (id, finding_id, severity, title, last_seen, metadata)
DEFAULT_CANDIDATE = (
    101, "F-aaaa1111", "critical",
    "someapp: image ghcr.io/example/app 1.0.0 → 2.0.0 (major)",
    datetime(2026, 8, 17, 4, 0, tzinfo=timezone.utc),
    {"namespace": "default", "kind": "image", "repository": "ghcr.io/example/app"},
)


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.log = conn.log
        self._last = ""

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self._last = " ".join(sql.split())
        self.log.append((self._last, params))

    def fetchall(self):
        if self._last.startswith("SELECT") and "FROM sweep_findings" in self._last:
            return list(self.conn.rows)
        return []

    def fetchone(self):
        # `SELECT notes FROM sweep_cycles ... FOR UPDATE` is the read half of
        # the veto-note read-modify-write. Defaults to None, so every test
        # written before the notes were readable behaves exactly as it did.
        if self._last.startswith("SELECT notes") and self.conn.notes is not None:
            return (self.conn.notes,)
        return None


class FakeConn:
    """Records every statement; commit/close are inert."""

    def __init__(self, rows=None, notes=None):
        self.log: list = []
        self.notes = notes
        self.rows: list = [DEFAULT_CANDIDATE] if rows is None else list(rows)

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


def _writer(section="version", orchestrated=True):
    """A writer wired to a fake connection, as if a DSN had been given.

    Returns (writer, conn) — close() nulls the writer's own `_conn`, so the
    test has to keep its own handle on the statement log.

    `orchestrated` mirrors reality: sweep-run.py / the daily-operation
    fan-out always hand a cycle id down, a hand-run script does not.
    """
    cid = "11111111-2222-3333-4444-555555555555" if orchestrated else None
    w = fw.FindingsWriter(dsn=None, section=section, cycle_id=cid)
    conn = FakeConn()
    w._conn = conn
    w._enabled = True
    w._run_started = datetime(2026, 8, 18, 13, 0, tzinfo=timezone.utc)
    # Most tests exercise the gate, not the circuit breaker, so give the run
    # a plausible emitted set unless the test overrides it.
    w._emitted_fps = {"deadbeef" * 8}
    return w, conn


def _autoclose_stmts(conn):
    return [s for s, _ in conn.log if "sweep_findings" in s and "resolved_at = now()" in s]


def _candidate_query(conn):
    """The SELECT that decides WHICH rows are eligible — where the scope lives."""
    return next((s, p) for s, p in conn.log
                if s.startswith("SELECT id, finding_id, severity")
                and "sweep_findings" in s)


def _clear_env():
    os.environ.pop("SWEEP_AUTOCLOSE", None)
    os.environ.pop("SWEEP_AUTOCLOSE_DRYRUN", None)


# --------------------------------------------------------------------------
# The gate: a verdict means the section completed; no verdict means it did not
# --------------------------------------------------------------------------

def test_close_with_verdict_runs_autoclose():
    _clear_env()
    w, conn = _writer()
    w.close(verdict="red")
    assert _autoclose_stmts(conn), "auto-close did not run on a completed section"


def test_close_without_verdict_skips_autoclose():
    """__exit__'s bare close() is the CRASH path — absence proves nothing."""
    _clear_env()
    w, conn = _writer()
    w.close()
    assert not _autoclose_stmts(conn), "auto-close ran on a run with no verdict"


def test_context_manager_exception_path_skips_autoclose():
    _clear_env()
    w, conn = _writer()
    try:
        with w:
            raise RuntimeError("scanner blew up mid-section")
    except RuntimeError:
        pass
    assert not _autoclose_stmts(conn), "auto-close ran after an exception"


def test_explicit_section_complete_false_overrides_verdict():
    _clear_env()
    w, conn = _writer()
    w.close(verdict="green", section_complete=False)
    assert not _autoclose_stmts(conn)


def test_mark_incomplete_vetoes_autoclose():
    """A section that ran but covered less than usual must not conclude."""
    _clear_env()
    w, conn = _writer("security")
    w.mark_incomplete("trivy could not authenticate to ghcr for 9 images")
    w.close(verdict="red")
    assert not _autoclose_stmts(conn), "auto-close ran on a declared-partial run"


def test_adhoc_run_does_not_autoclose_by_default():
    """A hand-run check script minted its own cycle id — it may be scoped,
    exploratory or degraded, so absence must not read as resolution."""
    _clear_env()
    w, conn = _writer(orchestrated=False)
    w.close(verdict="red")
    assert not _autoclose_stmts(conn), "an ad-hoc run auto-closed findings"


def test_adhoc_run_can_opt_in():
    _clear_env()
    os.environ["SWEEP_AUTOCLOSE"] = "1"
    try:
        w, conn = _writer(orchestrated=False)
        w.close(verdict="red")
        assert _autoclose_stmts(conn), "SWEEP_AUTOCLOSE=1 did not opt the run in"
    finally:
        _clear_env()


def test_orchestrated_via_env_cycle_id_autocloses():
    """The fan-out exports SWEEP_CYCLE_ID rather than passing the arg."""
    _clear_env()
    os.environ["SWEEP_CYCLE_ID"] = "99999999-8888-7777-6666-555555555555"
    try:
        w, conn = _writer(orchestrated=False)   # no arg — env supplies it
        w.close(verdict="red")
        assert _autoclose_stmts(conn), "an env-orchestrated run did not auto-close"
    finally:
        os.environ.pop("SWEEP_CYCLE_ID", None)
        _clear_env()


def test_zero_emit_run_is_refused():
    """Emitted nothing but has rows to close = a failed run, not a clean one."""
    _clear_env()
    w, conn = _writer()
    w._emitted_fps = set()

    closed = []

    def fake(*, dry_run):
        return closed if dry_run else [("F-1", "critical", "t", "2026-08-17")]
    closed.append(("F-1", "critical", "t", "2026-08-17"))
    w._autoclose_stale = fake
    w.close(verdict="green")
    # the breaker probes with dry_run=True and must not proceed to the write
    assert not _autoclose_stmts(conn)


def test_zero_emit_refusal_can_be_forced():
    _clear_env()
    os.environ["SWEEP_AUTOCLOSE_FORCE"] = "1"
    try:
        w, conn = _writer()
        w._emitted_fps = set()
        w.close(verdict="green")
        assert _autoclose_stmts(conn), "SWEEP_AUTOCLOSE_FORCE=1 did not override"
    finally:
        os.environ.pop("SWEEP_AUTOCLOSE_FORCE", None)
        _clear_env()


def test_autoclose_never_touches_rows_seen_since_the_run_started():
    """Guards against a concurrent run of the same section eating its rows."""
    _clear_env()
    w, conn = _writer()
    w.close(verdict="red")
    sql, params = _candidate_query(conn)
    assert "last_seen < %s" in sql, "no run-start guard in the auto-close clause"
    # params = (section, fingerprints, run_started)
    assert params[2] == w_run_started_expected(), "wrong run-start bound"


def w_run_started_expected():
    return datetime(2026, 8, 18, 13, 0, tzinfo=timezone.utc)


def test_kill_switch_disables_autoclose():
    _clear_env()
    os.environ["SWEEP_AUTOCLOSE"] = "0"
    try:
        w, conn = _writer()          # orchestrated: only the switch can stop it
        w.close(verdict="red")
        assert not _autoclose_stmts(conn)
    finally:
        _clear_env()


def test_dry_run_issues_no_update():
    _clear_env()
    os.environ["SWEEP_AUTOCLOSE_DRYRUN"] = "1"
    try:
        w, conn = _writer()
        w.close(verdict="red")
        assert not _autoclose_stmts(conn), "dry run issued an UPDATE"
        selects = [s for s, _ in conn.log
                   if s.startswith("SELECT id, finding_id, severity, title")]
        assert selects, "dry run did not even probe what would close"
    finally:
        _clear_env()


# --------------------------------------------------------------------------
# The scope: this section only, and never a fingerprint this run re-emitted
# --------------------------------------------------------------------------

def test_autoclose_is_scoped_to_this_section_and_spares_emitted():
    _clear_env()
    w, conn = _writer("version")
    w._emitted_fps.clear()          # drop the helper's sentinel
    w.emit("critical", "nocodb: image nocodb/nocodb 0.301.5 → 2026.08.0 (major)")
    w.emit("monitor", "cilium: chart 1.20.0 → 1.20.1 (patch)")
    emitted = set(w._emitted_fps)
    assert len(emitted) == 2
    w.close(verdict="red")

    sql, params = _candidate_query(conn)
    assert "section = %s" in sql, "auto-close is not section-scoped"
    assert "NOT (fingerprint = ANY(%s))" in sql, "auto-close does not spare re-emitted rows"
    # params = (section, fingerprints, run_started)
    assert params[0] == "version", f"wrong section scope: {params[0]!r}"
    assert set(params[1]) == emitted, "the spared set is not what this run emitted"
    # and the write itself is by primary key, never a re-stated predicate
    upd = next(st for st in _autoclose_stmts(conn))
    assert "WHERE id = ANY(%s)" in upd, "auto-close UPDATE re-states its own scope"


def test_emitted_fingerprints_are_stable_across_a_reword():
    """Auto-close keys on fingerprint, so a reworded title must NOT look new.

    This is why the writer-side close survives things the cycle_id-keyed
    reconcile does not: an out-of-band process that stamps the current
    cycle_id onto a row it never re-emitted (which is exactly what the
    2026-08-18 hand-resolve did) blinds a cycle_id comparison, but cannot
    forge a fingerprint.
    """
    # Neutral placeholders on purpose: this repo is public and a fixture
    # naming a real in-use image alongside a vulnerability count would state
    # currently-unfixed exposure (CLAUDE.md, docs/sops/vulnerability-disclosure.md).
    # The assertions only need two rewordings of one identifier.
    a = fw.fingerprint("security", None, "`example/app:1.2.3`: 1 finding of some kind")
    b = fw.fingerprint("security", None, "`example/app:1.2.3`: 4 findings of some kind — act")
    assert a == b, "a reworded/recounted title forked a new fingerprint"
    c = fw.fingerprint("security", None, "`example/app:4.5.6`: 1 finding of some kind")
    assert a != c, "a different image version collapsed onto the same fingerprint"


# --------------------------------------------------------------------------
# The incomplete veto: a degraded dependency must not let absence read as fixed
# --------------------------------------------------------------------------

def test_mark_incomplete_vetoes_autoclose():
    """The core security property: degraded coverage never resolves anything."""
    _clear_env()
    w, conn = _writer(section="security")
    w.mark_incomplete("s6_attack_patterns: Elasticsearch unavailable")
    w.close(verdict="green")
    assert not _autoclose_stmts(conn), (
        "auto-close ran on a run that declared itself incomplete — a monitoring "
        "outage would silently clear the finding backlog")


def test_mark_incomplete_accumulates_every_reason():
    """A run that trips four dependencies must report four, not the last one."""
    w, _ = _writer(section="security")
    w.mark_incomplete("s5: Elasticsearch unavailable")
    w.mark_incomplete("s11: UniFi controller unavailable")
    w.mark_incomplete("s5: Elasticsearch unavailable")     # duplicate collapses
    w.mark_incomplete("")                                   # empty is ignored
    w.mark_incomplete("s13: Wazuh indexer unavailable")
    assert w._incomplete_reason == (
        "s5: Elasticsearch unavailable; s11: UniFi controller unavailable; "
        "s13: Wazuh indexer unavailable"), w._incomplete_reason


def test_veto_reports_the_reason_to_the_operator():
    """An operator must be able to see WHICH dependency armed the veto."""
    _clear_env()
    import io, contextlib
    w, conn = _writer(section="security")
    w.mark_incomplete("s13_wazuh_siem: Wazuh indexer unavailable")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        w.close(verdict="yellow")
    out = buf.getvalue()
    assert "auto-close SKIPPED" in out and "INCOMPLETE" in out, out
    assert "Wazuh indexer unavailable" in out, out
    assert "security" in out, out


def test_veto_is_persisted_so_the_orchestrator_can_honour_it():
    """The veto must survive the process boundary, or it does nothing.

    sweep-run.py runs its OWN auto-close SQL after every step — a separate
    implementation that shares none of these gates and cannot see an
    in-memory `_incomplete_reason`. Before this, the writer printed
    "auto-close SKIPPED ... INCOMPLETE" and the orchestrator closed exactly
    those rows seconds later in the same sweep, making the veto inoperative
    in the only mode where auto-close is armed at all.
    """
    _clear_env()
    w, conn = _writer(section="security")
    w.mark_incomplete("s6_attack_patterns: Elasticsearch unavailable")
    w.close(verdict="green")
    notes_writes = [(sql, params) for sql, params in conn.log
                    if "UPDATE sweep_cycles" in sql and "notes" in sql]
    assert notes_writes, "incomplete state was never persisted to the cycle row"
    payload = notes_writes[-1][1][0]
    assert "incomplete" in payload, payload
    assert "security" in payload, payload
    assert "Elasticsearch unavailable" in payload, payload
    # And it must still refuse to close locally.
    assert not _autoclose_stmts(conn)


def test_complete_run_persists_no_incomplete_marker():
    """A healthy section must not poison the shared cycle row."""
    _clear_env()
    w, conn = _writer(section="security")
    w.close(verdict="green")
    notes_writes = [sql for sql, _p in conn.log
                    if "UPDATE sweep_cycles" in sql and "notes" in sql]
    assert not notes_writes, "a complete run wrote an incomplete marker"


# --------------------------------------------------------------------------
# Retracting the veto: the notes were write-only, so a section that recovered
# went on broadcasting the previous pass's reason
# --------------------------------------------------------------------------

def _notes_payload(conn):
    """The JSON handed to the last `UPDATE sweep_cycles ... notes` statement."""
    writes = [p for sql, p in conn.log
              if "UPDATE sweep_cycles" in sql and "notes" in sql]
    return json.loads(writes[-1][0]) if writes else None


def test_clean_run_clears_its_own_stale_incomplete_note():
    """The bug: `_persist_incomplete` only ever ADDED.

    A cycle is shared and outlives one run of one specialist, so a section
    that was degraded earlier and clean later kept the old reason on the row:
    the orchestrator went on skipping auto-close for a section that had since
    answered in full, and the board kept rendering the cycle incomplete.
    Observed on cycle 2d6b4635, which carried a prior degraded run's reasons
    verbatim through a 185/185, no-veto security run.
    """
    _clear_env()
    w, conn = _writer(section="security")
    conn.notes = json.dumps(
        {"incomplete": {"security": "s4_cve_check: trivy could not reach ghcr"}})
    w.close(verdict="green")
    assert _autoclose_stmts(conn), "precondition: this run must actually close"
    payload = _notes_payload(conn)
    assert payload is not None, "the stale note was never retracted"
    assert "incomplete" not in payload, (
        f"the last incomplete key must be dropped whole, got {payload}")


def test_clean_run_clears_only_its_own_section_note():
    """Scoped hard: a clean security run says nothing about the other sections.

    Clearing a sibling's key would turn this fix into the very fail-open it
    repairs — the orchestrator would close rows for a section that never got
    its answers.
    """
    _clear_env()
    w, conn = _writer(section="security")
    conn.notes = json.dumps({"incomplete": {
        "security": "s6_attack_patterns: Elasticsearch unavailable",
        "version": "renovate API unreachable",
    }})
    w.close(verdict="green")
    payload = _notes_payload(conn)
    assert payload["incomplete"] == {"version": "renovate API unreachable"}, payload


def test_full_coverage_clears_its_own_stale_uncovered_note():
    """`_persist_uncovered` had the identical write-only defect.

    It returned early when nothing was uncovered, so a component that
    resolved on a later pass stayed vetoed forever.
    """
    _clear_env()
    w, conn = _writer(section="security")
    conn.notes = json.dumps(
        {"uncovered": {"security": {"ghcr.io/example/app": "manifest unreadable"}}})
    assert not w._uncovered, "precondition: this run covered everything"
    w.close(verdict="green")
    payload = _notes_payload(conn)
    assert payload is not None and "uncovered" not in payload, payload


def test_clean_run_leaves_a_cycle_with_no_notes_untouched():
    """No stale note means no write at all — not an empty-dict rewrite."""
    _clear_env()
    w, conn = _writer(section="security")
    conn.notes = json.dumps({"incomplete": {"version": "renovate unreachable"}})
    w.close(verdict="green")
    assert _notes_payload(conn) is None, (
        "a section with nothing of its own to retract still rewrote the row")


def test_refused_autoclose_does_not_clear_the_note():
    """The circuit breaker is the one gate that says 'this did not really run'.

    Clearing there would hand the orchestrator — which has no breaker of its
    own — permission to close exactly the rows the writer just refused.
    """
    _clear_env()
    w, conn = _writer(section="version")
    w._emitted_fps = set()          # zero-emit: trips the breaker
    conn.notes = json.dumps({"incomplete": {"version": "scraper fell over"}})
    w.close(verdict="green")
    assert not _autoclose_stmts(conn), "precondition: the breaker must refuse"
    assert _notes_payload(conn) is None, "a refused run retracted the veto anyway"


def test_dry_run_clears_nothing():
    """SWEEP_AUTOCLOSE_DRYRUN writes nothing — the note is a write."""
    _clear_env()
    os.environ["SWEEP_AUTOCLOSE_DRYRUN"] = "1"
    try:
        w, conn = _writer(section="security")
        conn.notes = json.dumps({"incomplete": {"security": "trivy unavailable"}})
        w.close(verdict="green")
        assert _notes_payload(conn) is None, "a dry run mutated the cycle row"
    finally:
        _clear_env()


def test_healthy_run_still_autocloses():
    """The veto must not be a blanket off-switch — a clean run still resolves."""
    _clear_env()
    w, conn = _writer(section="security")
    log = fw.DegradationLog("security", printer=lambda m: None)
    assert not log, "a fresh DegradationLog must be falsy"
    assert log.apply(w) is False, "apply() vetoed with nothing recorded"
    w.close(verdict="green")
    assert _autoclose_stmts(conn), (
        "auto-close did not run on a fully-healthy completed section")


def test_degradation_log_applies_and_dedups():
    _clear_env()
    log = fw.DegradationLog("version", printer=lambda m: None)
    log.record("dockerhub", "Docker Hub (HTTP 429 rate limit)", "redis")
    log.record("dockerhub", "Docker Hub (HTTP 429 rate limit)", "redis")  # dup
    log.record("helm_index", "Helm repo index", "timeout")
    assert len(log) == 2, log.reasons
    w, conn = _writer(section="version")
    assert log.apply(w) is True
    w.close(verdict="green")
    assert not _autoclose_stmts(conn), (
        "a rate-limited registry lookup auto-closed real version findings")


def test_veto_survives_the_force_and_autoclose_env_overrides():
    """There is deliberately NO escape hatch for a degraded run."""
    w, conn = _writer(section="security")
    os.environ["SWEEP_AUTOCLOSE"] = "1"
    os.environ["SWEEP_AUTOCLOSE_FORCE"] = "1"
    try:
        w.mark_incomplete("s4_cve_check: trivy binary unavailable")
        w.close(verdict="green")
        assert not _autoclose_stmts(conn), (
            "an env override defeated the incomplete veto")
    finally:
        os.environ.pop("SWEEP_AUTOCLOSE", None)
        os.environ.pop("SWEEP_AUTOCLOSE_FORCE", None)


def test_disabled_writer_never_touches_the_db():
    _clear_env()
    w = fw.FindingsWriter(dsn=None, section="version")   # markdown-only mode
    w.emit("critical", "something")
    w.close(verdict="red")
    assert w._conn is None


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in fns:
        try:
            fn()
            print(f"PASS {name}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {name}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
