#!/usr/bin/env python3
"""Regression tests for the accepted-risk EXPIRY gate.

GROUND TRUTH (2026-09-17). AR-042 said "accept until 2026-09-03" in its
justification. Nothing read that sentence: `_apply_ar_suppression` filtered
accepted_risks on `status` and `enabled` and nothing else, so the acceptance
kept masking F-42302ce0 fourteen days past the operator's own deadline — and
the masked device was not even the accepted one (the AR names a soil sensor
that appears nowhere in the findings record; the row it silenced names two
OTHER sensors at 0%, one offline ~17 days). A deadline only a human can parse
is a comment, not policy.

TWO TRAPS THIS FILE GUARDS, both of which a reviewed draft fell into:

  1. GOING BLIND. The obvious "enforcement" is to hunt dates in justification
     prose. Measured: any past date flags 61 of 105 enabled ARs (~58 merely
     quoting a provenance date). So the gate binds ONLY on a recorded
     metadata.expires_at — which means an AR with a prose deadline lapses
     exactly as AR-042 did. `prose_deadline()` is the control that keeps that
     class visible, and it is pinned in BOTH directions below (it must catch the
     six live dated-deadline ARs and must NOT nag the four condition-based ones).
  2. A TEST THAT CANNOT SEE THE RULE. The draft put the comparison in a SQL
     fragment the fake could not execute, and asserted string membership
     instead. Measured against that draft: a 30-day silent grace, an INVERTED
     comparison, a `->`/`->>` typo and a neutered predicate in sweep-run.py ALL
     passed 14/14. The rule is now Python, the fake returns EVERY AR row
     unfiltered, and the code under test is the only thing that can drop one —
     so the MUTANTS section below can and does kill each of those.

Run:  python3 runbooks/tests/test-ar-expiry-gate.py
  or: python3 -m pytest runbooks/tests/test-ar-expiry-gate.py -q
"""

from __future__ import annotations

import datetime as _dt
import importlib.util
import inspect
import io
import re
import sys
import types
from contextlib import redirect_stdout
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "runbooks"))

try:
    from lib.ar_expiry import (  # noqa: E402
        EXPIRY_KEY, EXPIRY_SELECT, as_date, is_expired, lapse_note,
        parse_expiry, prose_deadline,
    )
    import lib.ar_expiry as ar_expiry  # noqa: E402
except ImportError as exc:  # pragma: no cover — the pre-fix state
    print(f"  FAIL  runbooks/lib/ar_expiry.py is missing — the accepted-risk "
          f"expiry gate is not installed ({exc})")
    raise SystemExit(1)

_TODAY = _dt.date(2026, 9, 17)
_PAST = "2026-09-03"        # AR-042's real stated deadline, 14 days gone
_FUTURE = "2026-12-01"


# The fake returns EVERY AR row, expiry column included, and never filters.
# That is deliberate and load-bearing: the ONLY thing that can drop the expired
# AR is the code under test, so deleting or weakening the gate fails here.
class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.rowcount = 0
        self._rows: list = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        norm = " ".join(sql.split())
        up = norm.upper()
        self.conn.log.append((norm, params))
        if up.startswith("SELECT COUNT(*)"):
            self._mode = "count"
            self._count = self.conn.count_exempt(norm, params)
        elif "FROM ACCEPTED_RISKS" in up:
            self._mode = "ars"
            self._rows = self.conn.ar_rows(norm)
        elif up.startswith("UPDATE"):
            self._mode = "update"
            self.rowcount = self.conn.match(norm, params)
        else:
            self._mode = "other"
            self._rows = []

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        if getattr(self, "_mode", None) == "count":
            return (self._count,)
        return None


class FakeConn:
    def __init__(self, ars, rows, today=_TODAY):
        self.ars = ars          # [(ar_id, description, expires_at|None), ...]
        self.rows = rows
        self.today = today
        self.log: list = []
        self.tagged: list = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        pass

    def ar_rows(self, sql):
        """EVERY row, unfiltered. No sniffing of the SQL text: the fake must not
        be the thing that implements the gate, or a gate deleted from the
        module still 'passes'."""
        if EXPIRY_SELECT.lower() not in sql.lower():
            # The caller did not even ask for the expiry column, so it cannot
            # be applying the rule. Hand back two-tuples, exactly as the pre-fix
            # statement did, and let the unpacking fail loudly.
            return [(ar_id, desc) for ar_id, desc, _e in self.ars]
        return list(self.ars)

    def count_exempt(self, sql, params) -> int:
        needle, tag, natures, ar_id = params
        n = 0
        for r in self.rows:
            meta = r.get("meta") or {}
            if r["severity"] not in ("critical", "warning", "monitor"):
                continue
            if needle not in r["title"].lower() or tag in r["title"]:
                continue
            if (meta.get("risk_nature", "") in natures
                    or re.match(r"(?i)^audit[-_]", meta.get("subsection", ""))
                    or meta.get("ar_id", "") == ar_id):
                n += 1
        return n

    def match(self, sql, params) -> int:
        prefix, needle, tag, natures, ar_id = params
        n = 0
        for r in self.rows:
            meta = r.get("meta") or {}
            if r["severity"] not in ("critical", "warning", "monitor"):
                continue
            if needle not in r["title"].lower() or tag in r["title"]:
                continue
            if meta.get("risk_nature", "") in natures:
                continue
            if re.match(r"(?i)^audit[-_]", meta.get("subsection", "")):
                continue
            if meta.get("ar_id", "") == ar_id:
                continue
            self.tagged.append((ar_id, r["finding_id"]))
            r["title"] = prefix + r["title"]
            r["severity"] = "accepted"
            n += 1
        return n


def _run(ars, rows, today=_TODAY):
    conn = FakeConn(ars, rows, today)
    stub = types.ModuleType("psycopg")
    stub.connect = lambda dsn: conn
    sys.modules["psycopg"] = stub
    # Pin "today" for the run so inclusivity is testable without waiting for
    # midnight. Wraps whatever is CURRENTLY installed, so it composes with the
    # mutants below instead of silently replacing them.
    current = ar_expiry.is_expired
    ar_expiry.is_expired = (
        lambda v, t=None, _f=current: _f(v, t if t is not None else today))
    try:
        spec = importlib.util.spec_from_file_location(
            "sweep_run_expiry", str(_REPO / "runbooks" / "sweep-run.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        buf = io.StringIO()
        with redirect_stdout(buf):
            tagged = mod._apply_ar_suppression("postgresql://fake")
    finally:
        ar_expiry.is_expired = current
    return conn, tagged, buf.getvalue()


_BATTERY = "Critical battery levels (<10%)"
_OTHER = "example-org/widget"


def _rows():
    return [
        dict(finding_id="F-masked", severity="warning",
             title=f"{_BATTERY}: 1 devices need immediate replacement",
             meta={"subsection": "general"}),
        dict(finding_id="F-live", severity="critical",
             title=f"`{_OTHER}:1.0.0`: fixable CRITICAL CVE(s) — bump the image",
             meta={"risk_nature": "vuln", "subsection": "s4_cve_check"}),
    ]


def _ars(battery_expiry):
    return [("AR-900", _BATTERY, battery_expiry), ("AR-901", _OTHER, None)]


# ---- 1. the defect itself -------------------------------------------------

def test_expired_ar_no_longer_suppresses():
    rows = _rows()
    _conn, tagged, _ = _run(_ars(_PAST), rows)
    by_id = {r["finding_id"]: r for r in rows}
    assert by_id["F-masked"]["severity"] == "warning", (
        "an acceptance 14 days past its stated expiry still masked its finding")
    assert not by_id["F-masked"]["title"].startswith("[AR-900]")
    assert tagged == 1, f"expected only the unexpired AR to tag, tagged={tagged}"


def test_the_lapse_is_announced_not_silent():
    _c, _t, out = _run(_ars(_PAST), _rows())
    assert "AR-900" in out and "EXPIRED" in out, out
    assert _PAST in out, "the log line must quote the date that passed"


def test_an_unreadable_expiry_is_announced_too_quoting_the_raw_value():
    """The draft printed NOTHING for an unreadable value — it stopped
    suppressing in silence, which is the silent half of the original bug."""
    _c, tagged, out = _run(_ars("whenever"), _rows())
    assert tagged == 1, "an unparseable expiry must fail toward visibility"
    assert "AR-900" in out and "whenever" in out, out
    assert "UNREADABLE" in out.upper(), out


# ---- 2. the control: the gate must not blind the suppressor ---------------

def test_ar_without_an_expiry_still_suppresses():
    """105 of 105 live ARs have no recorded expiry. If this fails, the fix
    silently un-suppressed the entire register."""
    rows = _rows()
    _c, tagged, _ = _run(_ars(None), rows)
    assert tagged == 2, f"both ARs should still tag, tagged={tagged}"
    assert all(r["severity"] == "accepted" for r in rows)


def test_future_expiry_still_suppresses():
    _c, tagged, _ = _run(_ars(_FUTURE), _rows())
    assert tagged == 2, f"a future deadline must not lapse early: {tagged}"


def test_expiry_is_inclusive_of_the_stated_day():
    """"accept until 2026-09-03" is in force ON the 3rd, gone on the 4th."""
    _c, on_day, _ = _run(_ars(_PAST), _rows(), today=_dt.date(2026, 9, 3))
    assert on_day == 2, "the acceptance must still hold on its last day"
    _c, after, _ = _run(_ars(_PAST), _rows(), today=_dt.date(2026, 9, 4))
    assert after == 1, "the acceptance must lapse the day after"


def test_both_outcomes_are_reachable_in_one_run():
    """A constant gate — always suppress, or never — passes half the cases
    above. It cannot pass this one."""
    rows = _rows()
    _run(_ars(_PAST), rows)
    sev = {r["finding_id"]: r["severity"] for r in rows}
    assert sev["F-masked"] == "warning" and sev["F-live"] == "accepted", sev


def test_the_suppressor_actually_asks_for_the_expiry_column():
    conn, _t, _ = _run(_ars(_PAST), _rows())
    sel = [s for s, _ in conn.log if "FROM ACCEPTED_RISKS" in s.upper()]
    assert sel, "no accepted_risks SELECT was issued"
    assert any(EXPIRY_SELECT.lower() in s.lower() for s in sel), (
        f"the shipped AR SELECT does not read the expiry column: {sel}")


def test_the_rule_is_never_evaluated_in_sql():
    """A `::date` cast raises on '2026-02-30' — measured live on PostgreSQL 16 —
    and that exception zeroes a whole cycle's suppression (sweep-run's
    `except Exception: return 0`) or ABORTs the security audit
    (`_POLICY_LOAD_FAILED`). Asserted on the statements ACTUALLY ISSUED, not on
    the source text, so the module may keep explaining why in a comment."""
    conn, _t, _ = _run(_ars(_PAST), _rows())
    for sql, _p in conn.log:
        assert "::date" not in sql.lower(), f"the expiry is cast in SQL: {sql}"
    assert not [n for n in dir(ar_expiry) if n.endswith("_SQL")], (
        "ar_expiry exposes a SQL predicate again — the regression suite cannot "
        "execute one, so a grace period or an inverted comparison would pass")


# ---- 3. MUTANTS: proof the suite can see the rule -------------------------
# Each mutation is one a maintainer could plausibly make. Every one MUST break
# at least one assertion above. The draft of this file survived all of them.

def _mutation_survives(fn) -> bool:
    """True if the whole battery still passes with `is_expired` replaced."""
    orig = ar_expiry.is_expired
    ar_expiry.is_expired = fn
    try:
        for t in (test_expired_ar_no_longer_suppresses,
                  test_the_lapse_is_announced_not_silent,
                  test_ar_without_an_expiry_still_suppresses,
                  test_future_expiry_still_suppresses,
                  test_expiry_is_inclusive_of_the_stated_day,
                  test_both_outcomes_are_reachable_in_one_run,
                  test_an_unreadable_expiry_is_announced_too_quoting_the_raw_value):
            try:
                t()
            except Exception:
                return False
        return True
    finally:
        ar_expiry.is_expired = orig


def test_mutants_are_all_caught():
    def _grace(value, today=None):
        d = as_date(value)
        if value is None:
            return False
        if d is None:
            return True
        return d < (today or _TODAY) - _dt.timedelta(days=30)

    mutants = {
        "never expires (the pre-fix behaviour)": lambda v, today=None: False,
        "always expires (un-suppresses the whole register)":
            lambda v, today=None: True,
        "silent 30-day grace": _grace,
        "exclusive boundary (lapses ON the stated day)":
            lambda v, today=None: False if v is None else (
                as_date(v) is None or as_date(v) <= (today or _TODAY)),
        "absent treated as expired (nags every open-ended acceptance)":
            lambda v, today=None: True if v is None else (
                as_date(v) is None or as_date(v) < (today or _TODAY)),
        "unreadable treated as still-in-force (fails toward SILENCE)":
            lambda v, today=None: (
                as_date(v) is not None and as_date(v) < (today or _TODAY)),
    }
    survivors = [name for name, fn in mutants.items() if _mutation_survives(fn)]
    assert not survivors, f"these broken gates pass the suite: {survivors}"


# ---- 4. the predicate ------------------------------------------------------

def test_python_predicate_boundaries():
    cases = {
        None: False,                               # no deadline recorded
        "2026-12-01": False, "2026-09-17": False,  # future / today
        "2026-09-03": True,                        # past
        "": True,                                  # recorded but unreadable
        "not-a-date": True, " 2026-09-03 ": True,
        "2026-13-45": True, "2026-02-30": True,    # date-SHAPED, not a date
    }
    for value, expected in cases.items():
        assert is_expired(value, _TODAY) is expected, f"is_expired({value!r})"
    assert as_date("2026-09-03") == _dt.date(2026, 9, 3)
    assert as_date("2026-13-45") is None and as_date("2026-02-30") is None
    assert lapse_note("AR-1", None, _TODAY) is None
    assert lapse_note("AR-1", _FUTURE, _TODAY) is None
    assert "2026-09-03" in lapse_note("AR-1", _PAST, _TODAY)
    assert "UNREADABLE" in lapse_note("AR-1", "zzz", _TODAY).upper()


def test_parse_expiry_refuses_garbage_and_clears_explicitly():
    assert parse_expiry("2026-12-01") == _dt.date(2026, 12, 1)
    for clear in ("none", "NONE", "never", ""):
        assert parse_expiry(clear) is None
    for bad in ("2026-12", "tomorrow", "01-12-2026", "2026-13-45", "2026-02-30"):
        try:
            parse_expiry(bad)
        except ValueError:
            continue
        raise AssertionError(f"parse_expiry({bad!r}) should refuse")


# ---- 5. the blindness control: deadlines the gate cannot enforce ----------

def test_prose_deadline_catches_the_live_unenforced_ones():
    """The six shapes measured in the live register on 2026-09-17. If this
    stops matching, the only signal for a prose deadline is gone and the class
    goes back to being invisible."""
    live = [
        "Extended by operator 2026-07-09: accept until 2026-09-03 (8 weeks).",
        "Covered by maintenance plan app-template-5.0. Revisit after window: 2026-08-16",
        "Drift-stable description. Revisit after window: 2026-08-09",
        "REVIEW BY 2026-11-15: by then either per-repo CI scanning is live or ...",
        "REVIEW BY 2026-11-16 (3-month): re-check whether upstream has shipped ...",
        "Re-review by 2026-11-19 regardless.",
    ]
    for j in live:
        got = prose_deadline(j)
        assert got is not None, f"missed a dated deadline: {j!r}"
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", got[1]), got


def test_prose_deadline_does_not_nag_condition_based_acceptances():
    """The over-inclusive alternative (phrase with no date) wrongly flags these
    four live ARs, which are legitimately open-ended."""
    for j in [
        "Accepted until a fixed tag is published upstream.",
        "Accepted until upstream rebuilds the image.",
        "The version pin is the lapse trigger, not drift.",
        "lapse trigger - the moment the decommission lands, the title stops matching.",
        "Verified 2026-08-19 against the live cluster.",      # provenance date only
        "Accepted 2026-05-27 by the operator.",
    ]:
        assert prose_deadline(j) is None, f"wrongly nagged: {j!r}"


# ---- 6. the register view and the second suppression layer ---------------

def test_lint_flags_expired_above_every_other_verdict():
    spec = importlib.util.spec_from_file_location(
        "pc_expiry", _REPO / "runbooks/policy-cli.py")
    pc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pc)
    miss = ("some prefix", "F-abc", "a title")
    assert pc.lint_flag(1, [], None, 1, expired=True) == "EXPIRED"
    assert pc.lint_flag(0, [], None, 0, expired=True) == "EXPIRED", "beats INERT"
    assert pc.lint_flag(0, [], miss, 1, expired=True) == "EXPIRED", "beats DRIFT"
    # back-compat: the 4-argument call other tests make must be unchanged
    assert pc.lint_flag(0, [], None, 0) == "INERT"
    assert pc.lint_flag(3, [], None, 5) == "ok"
    verdicts = {pc.lint_flag(1, [], None, 1, expired=True),
                pc.lint_flag(0, [], None, 0),
                pc.lint_flag(0, [], miss, 1),
                pc.lint_flag(3, ["v"], None, 5),
                pc.lint_flag(3, [], None, 5)}
    assert verdicts == {"EXPIRED", "INERT", "DRIFTING NOW", "at risk", "ok"}, (
        f"not all five verdicts are reachable: {sorted(verdicts)}")


def test_risk_edit_uses_the_jsonb_idiom_that_actually_runs():
    """`jsonb_build_object(%s, %s)` fails with IndeterminateDatatype under
    psycopg's untyped parameters — measured by EXPLAIN against the live DB. The
    operator command this whole fix depends on would not run."""
    src = (_REPO / "runbooks" / "policy-cli.py").read_text()
    body = src.split("def cmd_risk_edit", 1)[1].split("\ndef ", 1)[0]
    # CODE only — the comment above the statement names the broken idiom on
    # purpose, so that a future edit back to it is recognisable.
    body = "\n".join(l for l in body.splitlines()
                     if not l.lstrip().startswith("#"))
    assert "jsonb_build_object" not in body, (
        "risk edit builds jsonb from untyped parameters — this raises "
        "IndeterminateDatatype and the expiry is never written")
    assert "|| %s::jsonb" in body, "the working idiom is missing"


def test_security_checks_own_suppressor_is_gated_too():
    """security-check.py re-tags findings at emit time from the same table.
    Gating only the sweep leaves that layer masking on an expired AR."""
    text = (_REPO / "runbooks" / "security-check.py").read_text()
    assert "from lib.ar_expiry import" in text, (
        "security-check.py does not import the shared expiry predicate")
    parts = text.split("def _load_accepted_risks_from_db", 1)
    assert len(parts) == 2, "loader function not found"
    head = parts[1][:1400]
    assert "is_expired(" in head, (
        "the second suppression layer still loads expired ARs")


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
