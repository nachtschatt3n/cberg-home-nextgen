"""Unit tests for the audit-integrity guards in `_apply_ar_suppression`.

Proves the SAFETY contract without a database: psycopg is stubbed with fakes
that record the SQL and parameters they were handed, so each test asserts the
DECISION (which rows would this predicate reach?) rather than a DB side
effect.

The behaviour under test exists because of the 2026-08-18 incident
(F-21ceb683): an audit-integrity finding whose entire point was to report
"AR-063 no longer suppresses its target" got tagged `[AR-063] accepted` — the
finding quoted the AR's own description verbatim, so the AR silenced the
report of its own breakage. A detector that the thing it detects can switch
off is not a detector.

Two independent guards, because they fail in different directions:
  * nature/subsection — catches audit-integrity rows carrying no `ar_id`
  * self-reference    — catches rows carrying an `ar_id` but an ordinary nature

Run:  python3 runbooks/tests/test-ar-suppression-guard.py
  or: python3 -m pytest runbooks/tests/test-ar-suppression-guard.py -q
"""

from __future__ import annotations

import importlib.util
import re
import sys
import types
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------
# Load sweep-run.py with psycopg stubbed out (the module imports it lazily
# inside the function, so the stub only has to exist in sys.modules).
# --------------------------------------------------------------------------

class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.rowcount = 0
        self._last_select = 0

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        norm = " ".join(sql.split())
        self.conn.log.append((norm, params))
        if norm.upper().startswith("SELECT AR_ID"):
            self._mode = "ars"
        elif norm.upper().startswith("SELECT COUNT(*)"):
            self._mode = "count"
            self._count = self.conn.count_exempt(norm, params)
        elif norm.upper().startswith("UPDATE"):
            self._mode = "update"
            self.rowcount = self.conn.match(norm, params)
        else:
            self._mode = "select"

    def fetchall(self):
        return list(self.conn.ars)

    def fetchone(self):
        if getattr(self, "_mode", None) == "count":
            return (self._count,)
        return None


class FakeConn:
    """Records every statement; evaluates the UPDATE predicate in Python."""

    def __init__(self, ars, rows):
        self.ars = ars          # [(ar_id, description), ...]
        self.rows = rows        # [dict(finding_id, title, severity, meta), ...]
        self.log: list = []
        self.tagged: list[tuple[str, str]] = []   # (ar_id, finding_id)
        self.exempt_count = 0

    # context-manager protocol used by `with psycopg.connect(dsn) as conn:`
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        pass

    def count_exempt(self, sql, params) -> int:
        """Re-implement the exemption-count SELECT's WHERE. Mirrors `match`
        but in POSITIVE form: a row is counted when it WOULD have been tagged
        by the old predicate and is now held back by one of the guards."""
        needle, tag, natures, ar_id = params
        n = 0
        for r in self.rows:
            meta = r.get("meta") or {}
            if r.get("resolved_at") is not None:
                continue
            if r["severity"] not in ("critical", "warning", "monitor"):
                continue
            if needle not in r["title"].lower():
                continue
            if tag in r["title"]:
                continue
            if (meta.get("risk_nature", "") in natures
                    or re.match(r"(?i)^audit[-_]", meta.get("subsection", ""))
                    or meta.get("ar_id", "") == ar_id):
                n += 1
        self.exempt_count += n
        return n

    def match(self, sql, params) -> int:
        """Re-implement the UPDATE's WHERE in Python, honouring exactly the
        guard clauses PRESENT in the SQL. A guard that gets deleted from the
        SQL therefore stops being applied here too, and the test fails."""
        prefix, needle, tag, natures, ar_id = params
        has_nature = "risk_nature" in sql and "<> ALL" in sql
        has_subsec = "subsection" in sql and "!~*" in sql
        has_selfref = "'ar_id'" in sql and "<>" in sql
        n = 0
        for r in self.rows:
            meta = r.get("meta") or {}
            if r.get("resolved_at") is not None:
                continue
            if r["severity"] not in ("critical", "warning", "monitor"):
                continue
            if needle not in r["title"].lower():
                continue
            if tag in r["title"]:
                continue
            if has_nature and meta.get("risk_nature", "") in natures:
                continue
            if has_subsec and re.match(r"(?i)^audit[-_]", meta.get("subsection", "")):
                continue
            if has_selfref and meta.get("ar_id", "") == ar_id:
                continue
            self.tagged.append((ar_id, r["finding_id"]))
            r["title"] = prefix + r["title"]
            r["severity"] = "accepted"
            n += 1
        return n


def _load_sweep_run(conn: FakeConn):
    stub = types.ModuleType("psycopg")
    stub.connect = lambda dsn: conn
    sys.modules["psycopg"] = stub
    spec = importlib.util.spec_from_file_location(
        "sweep_run", str(_REPO / "runbooks" / "sweep-run.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------
# Fixtures — the row shapes that matter
#
# DISCLOSURE: the images and AR ids below are SYNTHETIC. Pairing a real
# deployed tag with a non-zero fixable-CRITICAL count is not publishable
# (docs/sops/vulnerability-disclosure.md §2.1: "a non-zero count for anything
# we run"), and a fixture is a committed file. The tests assert substring and
# tag behaviour only, so the values are free variables — keep them synthetic.
# The incident these guards exist for is F-21ceb683; the register holds the
# real strings.
# --------------------------------------------------------------------------

# A repository we do not run, and an AR id outside the allocated range.
_IMG = "example-org/widget"
_AR = "AR-900"


def _rows():
    return [
        # 1. the real target of the AR: an ordinary CVE finding. MUST tag.
        dict(finding_id="F-canon", severity="critical",
             title=f"`{_IMG}:1.0.0`: fixable CRITICAL CVE(s) — bump the image",
             meta={"risk_nature": "vuln", "subsection": "s4_cve_check"},
             resolved_at=None),
        # 2. the incident shape: audit-integrity, quotes the AR description
        #    verbatim, which is exactly why the old matcher ate it.
        dict(finding_id="F-incident", severity="warning",
             title=(f"{_AR} no longer suppresses its target: the description "
                    f"`{_IMG}` is not a substring of the finding title"),
             meta={"risk_nature": "policy-drift", "subsection": "s4_cve_check",
                   "ar_id": _AR},
             resolved_at=None),
        # 3. self-reference only: ordinary nature, but it is ABOUT the AR.
        dict(finding_id="F-selfref", severity="warning",
             title=f"{_AR} review overdue for `{_IMG}`",
             meta={"risk_nature": "policy", "subsection": "s10_flux_posture",
                   "ar_id": _AR},
             resolved_at=None),
        # 4. nature-only: audit-integrity, no ar_id key at all.
        dict(finding_id="F-cover", severity="warning",
             title=f"Trivy could not scan `{_IMG}:1.0.0` this run",
             meta={"risk_nature": "audit-coverage-gap", "subsection": "s4_cve_check"},
             resolved_at=None),
        # 5. subsection-only: media-style audit row, no risk_nature.
        dict(finding_id="F-mediaaudit", severity="warning",
             title=f"audit false positive on `{_IMG}` classifier",
             meta={"subsection": "audit_false_positive_multipart"},
             resolved_at=None),
    ]


def _run(ars, rows):
    conn = FakeConn(ars, rows)
    mod = _load_sweep_run(conn)
    tagged = mod._apply_ar_suppression("postgresql://fake")
    return mod, conn, tagged


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------

def test_audit_integrity_rows_are_exempt():
    rows = _rows()
    _, conn, tagged = _run([(_AR, _IMG)], rows)
    got = {fid for _, fid in conn.tagged}
    assert got == {"F-canon"}, f"expected only the real target to tag, got {got}"
    assert tagged == 1


def test_the_incident_row_is_never_silenced_by_its_own_ar():
    """The F-21ceb683 shape: the report of an AR's breakage, vs that AR."""
    rows = _rows()
    _run([(_AR, _IMG)], rows)
    row = next(r for r in rows if r["finding_id"] == "F-incident")
    assert row["severity"] == "warning", "audit-integrity finding was suppressed"
    assert not row["title"].startswith(f"[{_AR}]")


def test_each_guard_is_load_bearing_on_its_own():
    """Self-reference, nature and subsection must each independently exempt."""
    rows = _rows()
    _run([(_AR, _IMG)], rows)
    by_id = {r["finding_id"]: r for r in rows}
    # ordinary nature, but about the AR -> caught by the self-ref guard
    assert by_id["F-selfref"]["severity"] == "warning"
    # no ar_id, but audit-integrity nature -> caught by the nature guard
    assert by_id["F-cover"]["severity"] == "warning"
    # no ar_id and no nature, but an `audit_` subsection -> subsection guard
    assert by_id["F-mediaaudit"]["severity"] == "warning"


def test_audit_integrity_is_exempt_from_every_ar_not_only_its_own():
    """Precedence pin. The self-reference guard is scoped to the SAME AR, so
    on its own an UNRELATED AR could still eat an audit-integrity row. The
    NATURE guard deliberately widens that to all ARs. This test fails if a
    future edit narrows the nature guard to self-reference only."""
    rows = _rows()
    _run([("AR-901", f"{_AR} no longer suppresses")], rows)
    row = next(r for r in rows if r["finding_id"] == "F-incident")
    assert row["severity"] == "warning", (
        "an audit-integrity finding must be exempt from every AR, not only "
        "the one it names")


def test_ordinary_suppression_still_works():
    rows = [dict(finding_id="F-plain", severity="critical",
                 title=f"`{_IMG}:1.0.0`: fixable CRITICAL CVE(s)",
                 meta={"risk_nature": "vuln", "subsection": "s4_cve_check"},
                 resolved_at=None)]
    _, conn, tagged = _run([(_AR, _IMG)], rows)
    assert tagged == 1 and rows[0]["severity"] == "accepted"
    assert rows[0]["title"].startswith(f"[{_AR}] ")


def test_already_tagged_rows_are_idempotent():
    rows = [dict(finding_id="F-plain", severity="critical",
                 title=f"[{_AR}] `{_IMG}:1.0.0`: fixable CRITICAL CVE(s)",
                 meta={"risk_nature": "vuln", "subsection": "s4_cve_check"},
                 resolved_at=None)]
    _, _, tagged = _run([(_AR, _IMG)], rows)
    assert tagged == 0


def test_guard_clauses_are_present_in_the_emitted_sql():
    """Structural backstop: the Python re-implementation above only applies a
    guard it can SEE, so this asserts the SQL actually carries all three."""
    rows = _rows()
    _, conn, _ = _run([(_AR, _IMG)], rows)
    upd = [s for s, _ in conn.log if s.upper().startswith("UPDATE")]
    assert upd, "no UPDATE was issued"
    sql = upd[0]
    assert "risk_nature" in sql and "<> ALL" in sql, "nature guard missing"
    assert "subsection" in sql and "!~*" in sql, "subsection guard missing"
    assert "'ar_id'" in sql, "self-reference guard missing"


def test_the_exemption_count_matches_what_was_held_back():
    """The operator-visible log line is a real assertion, not decoration.

    The count SELECT is a SEPARATE statement from the UPDATE, mirroring the
    guard predicate in POSITIVE form. Nothing else checks it, so an edit that
    inverts one of the two predicates would leave suppression correct and the
    log line silently lying about it."""
    rows = _rows()
    _, conn, _ = _run([(_AR, _IMG)], rows)
    sel = [(s, p) for s, p in conn.log if s.upper().startswith("SELECT COUNT(*)")]
    assert sel, "no exemption-count SELECT was issued"
    sql, _params = sel[0]
    assert "= ANY" in sql, "count query does not mirror the nature guard"
    assert "~*" in sql and "!~*" not in sql, (
        "count query must mirror the subsection guard in POSITIVE form")
    assert "'ar_id'" in sql and "=" in sql, (
        "count query does not mirror the self-reference guard")
    # 4 of the 5 fixture rows are exempt; only F-canon is tagged.
    assert conn.exempt_count == 4, (
        f"expected 4 exemptions, predicate counted {conn.exempt_count}")


def test_nature_vocabulary_covers_the_values_in_use():
    mod, _, _ = _run([], [])
    for nature in ("policy-drift", "audit-coverage-gap"):
        assert nature in mod.AUDIT_INTEGRITY_NATURES, (
            f"{nature} is in use on live rows and must stay exempt")


def _main() -> int:
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_main())
