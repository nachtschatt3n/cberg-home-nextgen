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
import os
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "findings_writer", str(Path(__file__).with_name("findings_writer.py")))
fw = importlib.util.module_from_spec(_spec)
sys.modules["findings_writer"] = fw
_spec.loader.exec_module(fw)


class FakeCursor:
    def __init__(self, log):
        self.log = log

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.log.append((" ".join(sql.split()), params))

    def fetchall(self):
        return []

    def fetchone(self):
        return None


class FakeConn:
    """Records every statement; commit/close are inert."""

    def __init__(self):
        self.log: list = []

    def cursor(self):
        return FakeCursor(self.log)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


def _writer(section="version"):
    """A writer wired to a fake connection, as if a DSN had been given.

    Returns (writer, conn) — close() nulls the writer's own `_conn`, so the
    test has to keep its own handle on the statement log.
    """
    w = fw.FindingsWriter(dsn=None, section=section)
    conn = FakeConn()
    w._conn = conn
    w._enabled = True
    return w, conn


def _autoclose_stmts(conn):
    return [s for s, _ in conn.log if "sweep_findings" in s and "resolved_at = now()" in s]


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


def test_kill_switch_disables_autoclose():
    _clear_env()
    os.environ["SWEEP_AUTOCLOSE"] = "0"
    try:
        w, conn = _writer()
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
                   if s.startswith("SELECT finding_id, severity, title, last_seen")]
        assert selects, "dry run did not even probe what would close"
    finally:
        _clear_env()


# --------------------------------------------------------------------------
# The scope: this section only, and never a fingerprint this run re-emitted
# --------------------------------------------------------------------------

def test_autoclose_is_scoped_to_this_section_and_spares_emitted():
    _clear_env()
    w, conn = _writer("version")
    w.emit("critical", "nocodb: image nocodb/nocodb 0.301.5 → 2026.08.0 (major)")
    w.emit("monitor", "cilium: chart 1.20.0 → 1.20.1 (patch)")
    emitted = set(w._emitted_fps)
    assert len(emitted) == 2
    w.close(verdict="red")

    stmt = next((s, p) for s, p in conn.log
                if "resolved_at = now()" in s and "sweep_findings" in s)
    sql, params = stmt
    assert "section = %s" in sql, "auto-close is not section-scoped"
    assert "NOT (fingerprint = ANY(%s))" in sql, "auto-close does not spare re-emitted rows"
    # params = (git_head, section, fingerprints)
    assert params[1] == "version", f"wrong section scope: {params[1]!r}"
    assert set(params[2]) == emitted, "the spared set is not what this run emitted"


def test_emitted_fingerprints_are_stable_across_a_reword():
    """Auto-close keys on fingerprint, so a reworded title must NOT look new.

    This is why the writer-side close survives things the cycle_id-keyed
    reconcile does not: an out-of-band process that stamps the current
    cycle_id onto a row it never re-emitted (which is exactly what the
    2026-08-18 hand-resolve did) blinds a cycle_id comparison, but cannot
    forge a fingerprint.
    """
    a = fw.fingerprint("security", None, "`postgres:17.11-bookworm`: 1 fixable CRITICAL CVE(s)")
    b = fw.fingerprint("security", None, "`postgres:17.11-bookworm`: 4 fixable CRITICAL CVE(s) — bump it")
    assert a == b, "a reworded/recounted title forked a new fingerprint"
    c = fw.fingerprint("security", None, "`postgres:18.6-bookworm`: 1 fixable CRITICAL CVE(s)")
    assert a != c, "a different image version collapsed onto the same fingerprint"


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
