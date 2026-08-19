"""Unit tests for the PER-COMPONENT coverage veto on stale-finding auto-close.

Why it exists. The veto ("a coverage gap is not a fix") was right in principle
and wrong in granularity: it was SECTION-wide, so one unresolvable image
vetoed auto-close for the whole version section. That fired three cycles in a
row, each time from a different registry — docker.elastic.co (fixed by
`_is_structurally_slow`), Docker Hub 429s, then a single `public.ecr.aws` 429 —
and each time ~14 confirmed-stale rows stayed open while the other ~180
components had resolved perfectly. The board permanently overstated the estate.

The redesign makes the veto SAY WHAT IT COULD NOT COVER. A degradation that is
attributable to one leaf records a component key; auto-close then holds exactly
those rows open and proceeds for the rest. A degradation that is NOT
attributable — a Helm repo index, a dead `gh`, an unreachable Elasticsearch —
still vetoes the whole section, because there the affected component set is
unknown. And the narrowing is bounded: past an absolute cap, or past a fraction
of the attempted universe, the per-component scope is abandoned and the
section-wide veto returns, so a broad outage cannot masquerade as a pile of
isolated leaves.

Both directions are asserted here: a single forced 429 must still let the
section auto-close everything else, and a broad outage must still veto.

Run:  python3 runbooks/tests/test-autoclose-component-scope.py
  or: python3 -m pytest runbooks/tests/test-autoclose-component-scope.py -q
"""

from __future__ import annotations

import importlib.util
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "findings_writer", str(_REPO / "runbooks" / "lib" / "findings_writer.py"))
fw = importlib.util.module_from_spec(_spec)
sys.modules["findings_writer"] = fw
_spec.loader.exec_module(fw)


# ---------------------------------------------------------------------------
# Fakes — the DB is a statement recorder, so each test asserts the DECISION
# ---------------------------------------------------------------------------

def _row(pk, fid, title, meta=None, sev="warning"):
    return (pk, fid, sev, title,
            datetime(2026, 8, 17, 4, 0, tzinfo=timezone.utc), meta or {})


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self._last = ""

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self._last = " ".join(sql.split())
        self.conn.log.append((self._last, params))

    def fetchall(self):
        if self._last.startswith("SELECT id, finding_id, severity"):
            return list(self.conn.rows)
        return []

    def fetchone(self):
        return None


class FakeConn:
    def __init__(self, rows):
        self.log: list = []
        self.rows = list(rows)

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


def _writer(rows, section="version"):
    w = fw.FindingsWriter(dsn=None, section=section,
                          cycle_id="11111111-2222-3333-4444-555555555555")
    conn = FakeConn(rows)
    w._conn = conn
    w._enabled = True
    w._run_started = datetime(2026, 8, 18, 13, 0, tzinfo=timezone.utc)
    w._emitted_fps = {"deadbeef" * 8}
    return w, conn


def _closed_ids(conn):
    """Primary keys the UPDATE actually resolved."""
    for sql, params in conn.log:
        if "resolved_at = now()" in sql and "sweep_findings" in sql:
            return set(params[1])
    return set()


def _clear_env():
    for k in ("SWEEP_AUTOCLOSE", "SWEEP_AUTOCLOSE_DRYRUN",
              "SWEEP_AUTOCLOSE_FORCE", "SWEEP_CYCLE_ID"):
        os.environ.pop(k, None)


# ---------------------------------------------------------------------------
# component_key: one identity per component, stable across the version bump
# ---------------------------------------------------------------------------

def test_component_key_normalises():
    ck = fw.component_key
    assert ck("image", "public.ecr.aws/Eclipse-Mosquitto") == \
        "image:public.ecr.aws/eclipse-mosquitto"
    # the tag is the thing the finding is ABOUT — it must not fork the identity
    assert ck("image", "ghcr.io/foo/bar:1.2.3") == ck("image", "ghcr.io/foo/bar")
    assert ck("image", "ghcr.io/foo/bar@sha256:abc") == ck("image", "ghcr.io/foo/bar")
    # a registry port is not a tag
    assert ck("image", "registry.local:5000/foo") == "image:registry.local:5000/foo"


def test_component_key_rejects_unknown_kind():
    try:
        fw.component_key("banana", "x")
    except ValueError:
        return
    raise AssertionError("an unknown component kind was accepted")


# ---------------------------------------------------------------------------
# The matcher: err toward KEEPING a row open, never toward closing it
# ---------------------------------------------------------------------------

def test_matches_on_structured_metadata():
    assert fw.finding_matches_component(
        "image:public.ecr.aws/eclipse-mosquitto",
        "mosquitto: image public.ecr.aws/eclipse-mosquitto 2.0.18 → 2.0.22 (minor)",
        {"repository": "public.ecr.aws/eclipse-mosquitto"})


def test_matches_on_the_component_key_written_at_emit_time():
    assert fw.finding_matches_component(
        "image:ghcr.io/example/app", "anything at all",
        {"component": "image:ghcr.io/example/app"})


def test_matches_a_row_that_predates_the_component_metadata():
    """Stale rows are exactly the population auto-close acts on, and they were
    written before the emitter carried a component — the title has to carry it."""
    assert fw.finding_matches_component(
        "image:public.ecr.aws/eclipse-mosquitto",
        "mosquitto: image public.ecr.aws/eclipse-mosquitto 2.0.18 → 2.0.22 (minor)",
        {})


def test_matches_a_bare_dockerhub_name_recorded_as_library():
    """`library/redis` uncovered must hold a row that only ever said `redis`."""
    assert fw.finding_matches_component(
        "image:docker.io/library/redis",
        "redis: image redis 7.4.1 → 8.0.0 (major)", {"repository": "redis"})


def test_does_not_match_an_unrelated_component():
    assert not fw.finding_matches_component(
        "image:public.ecr.aws/eclipse-mosquitto",
        "nocodb: image nocodb/nocodb 0.301.5 → 2026.08.0 (major)",
        {"repository": "nocodb/nocodb"})


def test_a_too_short_ident_matches_nothing():
    """A 2-char ident would substring-match half the estate and silently widen
    the veto to everything. Refuse it instead."""
    assert not fw.finding_matches_component("image:ab", "ab: image ab 1 → 2", {})


# ---------------------------------------------------------------------------
# DIRECTION 1 — one forced 429: the section still auto-closes everything else
# ---------------------------------------------------------------------------

def test_one_uncovered_image_holds_only_its_own_row():
    _clear_env()
    rows = [
        _row(1, "F-aaaa0001",
             "mosquitto: image public.ecr.aws/eclipse-mosquitto 2.0.18 → 2.0.22 (minor)",
             {"repository": "public.ecr.aws/eclipse-mosquitto"}),
        _row(2, "F-aaaa0002", "nocodb: image nocodb/nocodb 0.301.5 → 2026.08.0 (major)",
             {"repository": "nocodb/nocodb"}),
        _row(3, "F-aaaa0003", "cilium: chart 1.20.0 → 1.20.1 (patch)", {"kind": "chart"}),
        _row(4, "F-aaaa0004", "grafana: image grafana/grafana 11.0.0 → 12.0.0 (major)",
             {"repository": "grafana/grafana"}),
    ]
    w, conn = _writer(rows)
    w.mark_uncovered("image:public.ecr.aws/eclipse-mosquitto",
                     "image public.ecr.aws/eclipse-mosquitto: HTTP 429 rate limit")
    w.close(verdict="yellow")

    closed = _closed_ids(conn)
    assert closed == {2, 3, 4}, (
        f"one unresolvable image did not stop vetoing the rest: closed={closed}")
    assert 1 not in closed, "closed a finding whose component was never resolved"


def test_the_scope_is_published_for_the_orchestrator():
    """sweep-run.py runs a SECOND auto-close after every step and cannot see
    our in-memory state — a scope enforced only here would be undone seconds
    later, in the same sweep."""
    _clear_env()
    w, conn = _writer([_row(1, "F-1", "x: image foo/bar 1 → 2", {})])
    w.mark_uncovered("image:public.ecr.aws/eclipse-mosquitto", "HTTP 429")
    w.close(verdict="green")
    notes_writes = [p for s, p in conn.log
                    if s.startswith("UPDATE sweep_cycles SET notes")]
    assert notes_writes, "the per-component scope was never persisted"
    assert "uncovered" in notes_writes[0][0]
    assert "eclipse-mosquitto" in notes_writes[0][0]


def test_notes_roundtrip_through_the_orchestrator_parser():
    payload = ('{"uncovered": {"version": '
               '{"image:public.ecr.aws/eclipse-mosquitto": "HTTP 429"}}}')
    got = fw.uncovered_from_notes(payload)
    assert got["version"]["image:public.ecr.aws/eclipse-mosquitto"] == "HTTP 429"
    assert fw.uncovered_from_notes(None) == {}
    assert fw.uncovered_from_notes("not json") == {}
    assert fw.uncovered_from_notes('{"uncovered": "nope"}') == {}


def test_partition_helper_is_shared_and_symmetric():
    rows = [("F-1", "warning", "a: image ghcr.io/x/y 1 → 2", "t", {}),
            ("F-2", "warning", "b: image ghcr.io/p/q 1 → 2", "t", {})]
    closeable, held = fw.partition_by_uncovered(rows, ["image:ghcr.io/x/y"])
    assert [r[0] for r in closeable] == ["F-2"]
    assert [r[0][0] for r in held] == ["F-1"]
    # no scope at all -> everything closes, exactly as before this change
    assert fw.partition_by_uncovered(rows, []) == (rows, [])


# ---------------------------------------------------------------------------
# DIRECTION 2 — a broad outage still vetoes the whole section
# ---------------------------------------------------------------------------

def test_unattributable_degradation_still_vetoes_the_section():
    """A Helm repo index / dead `gh` / unreachable Elasticsearch degrades an
    UNKNOWN set of components; nothing can be scoped around that."""
    _clear_env()
    log = fw.DegradationLog("version", printer=lambda m: None)
    log.record("helm repo bjw-s", "Helm index.yaml", "HTTP 503")
    w, conn = _writer([_row(1, "F-1", "x: image foo/bar 1 → 2", {})])
    assert log.apply(w) is True, "an unattributable degradation did not veto"
    w.close(verdict="red")
    assert not _closed_ids(conn), "a section-wide veto still closed rows"


def test_broad_outage_abandons_the_per_component_scope():
    """Every failure attributed, but to 60 of 180 components — that is a
    registry outage, not a pile of isolated leaves."""
    _clear_env()
    log = fw.DegradationLog("version", printer=lambda m: None)
    for i in range(60):
        log.record(f"image reg.example/app{i}", "reg.example (HTTP 429)",
                   component=fw.component_key("image", f"reg.example/app{i}"))
    log.note_universe(180)
    w, conn = _writer([_row(1, "F-1", "unrelated: chart 1 → 2", {})])
    assert log.apply(w) is True, "a 60/180 outage was treated as isolated leaves"
    w.close(verdict="red")
    assert not _closed_ids(conn), "a broad outage still auto-closed"


def test_absolute_cap_applies_without_a_denominator():
    """`note_universe` is optional; the absolute cap must still bound the scope."""
    _clear_env()
    log = fw.DegradationLog("version", printer=lambda m: None)
    for i in range(fw.DegradationLog.MAX_SCOPED_COMPONENTS + 1):
        log.record(f"image reg.example/app{i}", "reg.example (HTTP 429)",
                   component=fw.component_key("image", f"reg.example/app{i}"))
    w, _ = _writer([])
    assert log.apply(w) is True
    assert w._incomplete_reason, "no section-wide veto was recorded"
    assert not w._uncovered, "the per-component scope survived the cap"


def test_a_single_leaf_failure_does_not_veto_the_section():
    _clear_env()
    log = fw.DegradationLog("version", printer=lambda m: None)
    log.record("image public.ecr.aws/eclipse-mosquitto",
               "public.ecr.aws (HTTP 429 rate limit)",
               "tags/list returned HTTP 429",
               component=fw.component_key("image", "public.ecr.aws/eclipse-mosquitto"))
    log.note_universe(181)
    w, _ = _writer([])
    assert log.apply(w) is False, "one 429 out of 181 vetoed the whole section"
    assert w._uncovered == {
        "image:public.ecr.aws/eclipse-mosquitto":
            "image public.ecr.aws/eclipse-mosquitto: public.ecr.aws "
            "(HTTP 429 rate limit) unavailable (tags/list returned HTTP 429)"}
    assert not w._incomplete_reason


def test_mixed_run_falls_back_to_the_section_veto():
    """One attributable + one not = the unknown set wins. Both are reported."""
    _clear_env()
    log = fw.DegradationLog("version", printer=lambda m: None)
    log.record("image ghcr.io/x/y", "ghcr.io (HTTP 429)",
               component=fw.component_key("image", "ghcr.io/x/y"))
    log.record("github", "gh CLI", "not authenticated")
    w, conn = _writer([_row(1, "F-1", "z: image a/b 1 → 2", {})])
    assert log.apply(w) is True
    assert "gh CLI" in w._incomplete_reason
    assert "ghcr.io/x/y" in w._incomplete_reason, "the scoped reason was dropped"
    w.close(verdict="red")
    assert not _closed_ids(conn)


def test_an_unparseable_component_degrades_to_the_section_veto():
    """A bad key would scope-match NOTHING and silently widen auto-close."""
    _clear_env()
    w, conn = _writer([_row(1, "F-1", "z: image a/b 1 → 2", {})])
    w.mark_uncovered("no-colon-here", "registry timed out")
    assert w._incomplete_reason, "a malformed component key did not veto"
    w.close(verdict="red")
    assert not _closed_ids(conn)


# ---------------------------------------------------------------------------
# The 429 backoff — retried, bounded, and never hiding an exhausted budget
# ---------------------------------------------------------------------------

def _load_cav():
    os.environ.setdefault("_MISE_ACTIVATED", "1")
    sys.path.insert(0, str(_REPO / "runbooks"))
    spec = importlib.util.spec_from_file_location(
        "cav_under_test", _REPO / "runbooks" / "check-all-versions.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Resp:
    def __init__(self, code, headers=None):
        self.status_code = code
        self.headers = headers or {}


class _Sess:
    def __init__(self, codes):
        self.codes = list(codes)
        self.calls = 0

    def get(self, url, **kw):
        self.calls += 1
        c = self.codes.pop(0) if self.codes else 200
        return c if isinstance(c, _Resp) else _Resp(c)


def test_429_is_retried_and_can_succeed():
    cav = _load_cav()
    slept: list = []
    sess = _Sess([429, 200])
    r = cav._get_retry_429(sess, "https://public.ecr.aws/v2/x/tags/list",
                           sleeper=slept.append)
    assert r.status_code == 200 and sess.calls == 2
    assert slept and slept[0] > 0, "no backoff between attempts"


def test_retry_after_header_is_honoured():
    cav = _load_cav()
    slept: list = []
    sess = _Sess([_Resp(429, {"Retry-After": "3"}), 200])
    cav._get_retry_429(sess, "https://example/x", sleeper=slept.append)
    assert slept == [3.0], f"Retry-After ignored: {slept}"


def test_backoff_is_bounded_and_surfaces_the_last_429():
    """An exhausted retry budget must still hand the 429 back, so the caller's
    transient classification (and the coverage bookkeeping) still runs."""
    cav = _load_cav()
    slept: list = []
    sess = _Sess([429, 429, 429, 429, 429])
    r = cav._get_retry_429(sess, "https://example/x", sleeper=slept.append)
    assert r.status_code == 429, "a retried-out 429 was swallowed"
    assert sess.calls == cav._RETRY_429_ATTEMPTS
    assert sum(slept) <= cav._RETRY_429_MAX_SLEEP_S


def test_non_429_is_never_retried():
    cav = _load_cav()
    for code in (500, 503, 404, 401):
        sess = _Sess([code, 200])
        r = cav._get_retry_429(sess, "https://example/x", sleeper=lambda _s: None)
        assert sess.calls == 1 and r.status_code == code, (
            f"HTTP {code} was retried; only 429 asks to be")


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
            print(f"FAIL {name}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
