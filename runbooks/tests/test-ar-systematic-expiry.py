"""Regression tests for SYSTEMATIC accepted-risk expiry (F-d5486ff1).

GROUND TRUTH (2026-09-28). The expiry gate of 2026-09-17 (F-da238139) made a
RECORDED `metadata.expires_at` binding, but only 5 of 95 enabled ARs had one,
so almost nothing ever came back up for review; an expired AR stayed
`enabled=true`, so the register kept claiming a decision nobody had renewed;
and nothing warned before the date, so a lapse always arrived as a surprise.
The operator asked for: an expiry on every AR, `risk add` refusing one without
a deadline (max horizon 180 days), an automated AUTO-DISABLE of expired ARs,
and a 14-day warning on the sweep board and the weekly retro.

What each block pins:
  1. auto_disable_expired: an expired AR is disabled (with the reason stamped),
     a future / absent one is not; the sweep calls it BEFORE suppressing, and
     an expired AR is still ignored by the suppressor.
  2. policy-cli: `risk add` without --expires is refused, --no-expiry is
     refused, a date past the 180-day horizon is refused, a valid one writes
     metadata.expires_at; `risk edit --expires none` is refused; `risk disable`
     needs --reason and stamps it; `risk renew` re-enables ONLY an AR that
     lapsed, never one disabled for another reason.
  3. the pre-expiry warning fires inside 14 days (inclusive of today and of
     day 14), not on day 15, and reaches both the board and the retro.

Run:  python3 runbooks/tests/test-ar-systematic-expiry.py
"""

from __future__ import annotations

import contextlib
import datetime as dt
import importlib.util
import io
import json
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "runbooks"))

from lib import ar_expiry  # noqa: E402

FAILURES: list[str] = []
TODAY = dt.date.today()


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


def d(days: int) -> str:
    return (TODAY + dt.timedelta(days=days)).isoformat()


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------
# fakes
# --------------------------------------------------------------------------
class RegCursor:
    """A tiny accepted_risks table in memory, driven by the exact statements
    auto_disable_expired and the policy-cli handlers issue."""

    def __init__(self, table: dict):
        self.table = table          # ar_id -> {"enabled", "metadata", "description"}
        self.executed: list = []
        self._rows: list = []
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        s = " ".join(str(sql).split())
        self.executed.append((s, params))
        if s.startswith("SELECT ar_id, metadata->>'expires_at' FROM accepted_risks"):
            self._rows = [(a, (r["metadata"] or {}).get("expires_at"))
                          for a, r in sorted(self.table.items()) if r["enabled"]]
        elif s.startswith("SELECT enabled, metadata FROM accepted_risks"):
            r = self.table.get(params[0])
            self._rows = [{"enabled": r["enabled"], "metadata": r["metadata"]}] if r else []
        elif s.startswith("SELECT description FROM accepted_risks"):
            r = self.table.get(params[-1])
            self._rows = [{"description": r["description"]}] if r else []
        elif s.startswith("UPDATE accepted_risks"):
            ar_id = params[-1]
            r = self.table.get(ar_id)
            if r is None or ("AND enabled = true" in s and not r["enabled"]):
                self.rowcount = 0
                return
            meta = dict(r["metadata"] or {})
            for p in params[:-1]:
                if isinstance(p, str) and p.startswith("{"):
                    meta.update(json.loads(p))
                elif isinstance(p, str) and " - %s" in s and p in meta and not p.startswith("{"):
                    meta.pop(p, None)
            r["metadata"] = meta
            if "enabled = false" in s:
                r["enabled"] = False
            if "enabled = true" in s.split("WHERE")[0]:
                r["enabled"] = True
            self.rowcount = 1
        elif s.startswith("INSERT INTO accepted_risks"):
            self.table[params[0]] = {"enabled": True, "description": params[2],
                                     "metadata": json.loads(params[-1])}
            self.rowcount = 1
        elif "FROM sweep_findings" in s:
            # one suppressible open finding for every needle, so add's nomatch
            # gate is satisfied and the expiry gates are what is under test
            self._rows = [{"finding_id": "F-1", "severity": "warning",
                           "title": "t", "ok": True}]
        else:
            raise AssertionError(f"unexpected statement: {s[:100]}")

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


class RegConn:
    def __init__(self, table):
        self.cur = RegCursor(table)
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def cursor(self):
        return self.cur

    def commit(self):
        self.commits += 1


def table():
    return {
        "AR-001": {"enabled": True, "description": "expired one",
                   "metadata": {"expires_at": d(-1)}},
        "AR-002": {"enabled": True, "description": "expires today",
                   "metadata": {"expires_at": d(0)}},
        "AR-003": {"enabled": True, "description": "future",
                   "metadata": {"expires_at": d(60)}},
        "AR-004": {"enabled": True, "description": "no expiry", "metadata": {}},
        "AR-005": {"enabled": True, "description": "unreadable",
                   "metadata": {"expires_at": "2026-02-30"}},
        "AR-006": {"enabled": False, "description": "already off",
                   "metadata": {"expires_at": d(-30)}},
    }


def main() -> int:
    # ---- 1. auto-disable -------------------------------------------------
    print("auto_disable_expired:")
    t = table()
    conn = RegConn(t)
    done = dict(ar_expiry.auto_disable_expired(conn, today=TODAY, actor="test"))
    check("an expired AR is disabled", "AR-001" in done and t["AR-001"]["enabled"] is False)
    check("an UNREADABLE expiry is treated as expired and disabled",
          "AR-005" in done and t["AR-005"]["enabled"] is False)
    check("an AR expiring TODAY is still in force (inclusive)",
          "AR-002" not in done and t["AR-002"]["enabled"] is True)
    check("a future AR is untouched", t["AR-003"]["enabled"] is True)
    check("an AR with no expiry is not disabled (reported instead)",
          t["AR-004"]["enabled"] is True)
    check("an already-disabled AR is not re-stamped", "AR-006" not in done)
    m = t["AR-001"]["metadata"]
    check("the reason is stamped: disabled_reason=expired, disabled_at, disabled_by",
          m.get("disabled_reason") == "expired" and m.get("disabled_at") == TODAY.isoformat()
          and m.get("disabled_by") == "test" and m.get("expires_at") == d(-1), str(m))
    check("the change is committed", conn.commits >= 1)
    check("second run is a no-op (idempotent)",
          ar_expiry.auto_disable_expired(RegConn(t), today=TODAY) == [])

    # The sweep runs it BEFORE suppression, and the suppressor still ignores
    # an expired AR even if the disable could not run.
    print("sweep-run wiring:")
    events: list = []

    class SweepCur:
        rowcount = 0

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, sql, params=None):
            s = " ".join(sql.split())
            events.append(s[:60])
            self._s, self._p = s, params
            if s.startswith("UPDATE accepted_risks"):
                self.rowcount = 1
            elif s.startswith("UPDATE sweep_findings"):
                self.rowcount = 0
                events.append(("tag", params[0]))

        def fetchall(self):
            if self._s.startswith("SELECT ar_id, metadata->>'expires_at'"):
                return [("AR-001", d(-1)), ("AR-003", d(60))]
            if self._s.startswith("SELECT ar_id, description"):
                return [("AR-001", "expired needle", d(-1)),
                        ("AR-003", "future needle", d(60))]
            return []

        def fetchone(self):
            return (0,)

    class SweepConn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def cursor(self):
            return SweepCur()

        def commit(self):
            pass

    stub = types.ModuleType("psycopg")
    stub.connect = lambda dsn: SweepConn()
    saved = sys.modules.get("psycopg")
    sys.modules["psycopg"] = stub
    try:
        sr = _load("sweep_run_sysexp", "runbooks/sweep-run.py")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            sr._apply_ar_suppression("postgresql://fake")
    finally:
        if saved is not None:
            sys.modules["psycopg"] = saved
        else:
            sys.modules.pop("psycopg", None)
    strs = [e for e in events if isinstance(e, str)]
    i_dis = next((i for i, e in enumerate(strs) if e.startswith("UPDATE accepted_risks")), -1)
    i_sup = next((i for i, e in enumerate(strs) if e.startswith("SELECT ar_id, description")), -1)
    check("the sweep auto-disables BEFORE the suppression SELECT",
          0 <= i_dis < i_sup, str(strs[:6]))
    check("the sweep log names the auto-disabled AR",
          "AR-001 EXPIRED" in out.getvalue() and "AUTO-DISABLED" in out.getvalue(),
          out.getvalue()[:300])
    tags = [e[1] for e in events if isinstance(e, tuple)]
    check("the expired AR is never applied as a suppression",
          "[AR-001] " not in tags and "[AR-003] " in tags, str(tags))

    # ---- 2. policy-cli ----------------------------------------------------
    print("policy-cli:")
    pc = _load("pc_sysexp", "runbooks/policy-cli.py")
    parser = pc.build_parser()

    def run(argv, t):
        conn = RegConn(t)
        pc._connect = lambda dsn: conn
        err, out = io.StringIO(), io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
            rc = parser.parse_args(argv).handler(parser.parse_args(argv), "fake")
        return rc, err.getvalue(), out.getvalue(), conn

    t = {}
    rc, err, _, _ = run(["risk", "add", "AR-900", "--description", "x"], t)
    check("risk add WITHOUT --expires is refused", rc == 2 and "REFUSING" in err
          and "AR-900" not in t, f"{rc} {err[:80]}")
    rc, err, _, _ = run(["risk", "add", "AR-900", "--description", "x", "--no-expiry"], t)
    check("risk add --no-expiry is refused (withdrawn)", rc == 2 and "withdrawn" in err
          and "AR-900" not in t, f"{rc} {err[:80]}")
    rc, err, _, _ = run(["risk", "add", "AR-900", "--description", "x",
                         "--expires", d(181)], t)
    check("risk add past the 180-day horizon is refused",
          rc == 2 and "horizon" in err and "AR-900" not in t, f"{rc} {err[:80]}")
    rc, err, _, _ = run(["risk", "add", "AR-900", "--description", "x",
                         "--expires", "none"], t)
    check("risk add --expires none is refused", rc == 2 and "AR-900" not in t, f"{rc}")
    rc, err, out, _ = run(["risk", "add", "AR-900", "--description", "x",
                           "--expires", d(180)], t)
    check("risk add with a date at the horizon writes metadata.expires_at",
          rc in (0, None) and t.get("AR-900", {}).get("metadata", {}).get("expires_at") == d(180),
          f"{rc} {err[:80]} {t.get('AR-900')}")

    t = table()
    rc, err, _, _ = run(["risk", "edit", "AR-003", "--expires", "none"], t)
    check("risk edit --expires none is refused (cannot clear a deadline)",
          rc == 2 and t["AR-003"]["metadata"]["expires_at"] == d(60), f"{rc} {err[:80]}")
    rc, err, _, _ = run(["risk", "edit", "AR-003", "--expires", d(200)], t)
    check("risk edit past the horizon is refused", rc == 2 and "horizon" in err, f"{rc}")

    try:
        with contextlib.redirect_stderr(io.StringIO()):
            parser.parse_args(["risk", "disable", "AR-003"])
        ok = False
    except SystemExit:
        ok = True
    check("risk disable without --reason is rejected by the parser", ok)
    rc, err, _, _ = run(["risk", "disable", "AR-003", "--reason", "  "], t)
    check("risk disable with a blank reason is refused", rc == 2, f"{rc}")
    rc, err, _, _ = run(["risk", "disable", "AR-003", "--reason", "premise false"], t)
    check("risk disable stamps the reason and disables",
          rc == 0 and t["AR-003"]["enabled"] is False
          and t["AR-003"]["metadata"].get("disabled_reason") == "premise false",
          f"{rc} {t['AR-003']}")

    rc, err, _, _ = run(["risk", "renew", "AR-003"], t)
    check("risk renew does NOT re-enable an AR disabled for another reason",
          rc == 2 and t["AR-003"]["enabled"] is False, f"{rc} {err[:80]}")
    ar_expiry.auto_disable_expired(RegConn(t), today=TODAY)      # AR-001 lapses
    rc, err, out, _ = run(["risk", "renew", "AR-001"], t)
    m = t["AR-001"]["metadata"]
    check("risk renew re-enables an AR that lapsed, default +90d, clears the stamp",
          rc == 0 and t["AR-001"]["enabled"] is True
          and m.get("expires_at") == d(ar_expiry.DEFAULT_HORIZON_DAYS)
          and "disabled_reason" not in m and m.get("renew_count") == 1,
          f"{rc} {err[:80]} {t['AR-001']}")
    rc, err, _, _ = run(["risk", "renew", "AR-002", "--days", "181"], t)
    check("risk renew past the horizon is refused", rc == 2 and "horizon" in err, f"{rc}")

    # ---- 3. the pre-expiry warning ----------------------------------------
    print("pre-expiry warning:")
    rows = [("AR-010", True, "fourteen", {"expires_at": d(14)}),
            ("AR-011", True, "fifteen", {"expires_at": d(15)}),
            ("AR-012", True, "today", json.dumps({"expires_at": d(0)})),
            ("AR-013", True, "none", None),
            ("AR-014", True, "lapsed but on", {"expires_at": d(-2)}),
            ("AR-015", False, "auto-off", {"expires_at": d(-3), "disabled_reason": "expired",
                                          "disabled_at": d(-1)}),
            ("AR-016", False, "old auto-off", {"expires_at": d(-40), "disabled_reason": "expired",
                                              "disabled_at": d(-30)}),
            ("AR-017", False, "manual off", {"expires_at": d(3), "disabled_reason": "premise"})]
    rep = ar_expiry.expiry_report(rows, today=TODAY)
    exp_ids = [r["ar_id"] for r in rep["expiring"]]
    check("fires on day 14 and on day 0 (today)", "AR-010" in exp_ids and "AR-012" in exp_ids,
          str(exp_ids))
    check("does NOT fire on day 15", "AR-011" not in exp_ids, str(exp_ids))
    check("a DISABLED AR never warns", "AR-017" not in exp_ids)
    check("sorted soonest first", exp_ids[0] == "AR-012", str(exp_ids))
    check("missing expiry is reported", [r["ar_id"] for r in rep["missing"]] == ["AR-013"])
    check("expired-but-enabled is reported, not warned",
          [r["ar_id"] for r in rep["expired_enabled"]] == ["AR-014"])
    check("recently auto-disabled is reported; one from a month ago is not",
          [r["ar_id"] for r in rep["recently_disabled"]] == ["AR-015"])

    rb = _load("render_board_sysexp", "runbooks/render-board.py")
    board = {"cycle_id": "c" * 36, "started_at": "2026-09-28 04:00", "tiers": {},
             "criticals": [], "escalations": [], "high": [], "planned": {"_": ("p", "w")},
             "sections": {}, "slos": [], "ar_expiry": rep}
    text = rb.render(board, {"next": "x", "warnings": []})
    check("the board numbers an AR-RENEW? line per expiring AR",
          text.count("AR-RENEW?") == 2 and "risk renew AR-010" in text, text[:600])
    check("the board flags expired-but-enabled as AR-LAPSED", "AR-LAPSED" in text
          and "AR-014" in text)
    check("the board's expiry section names the auto-disabled AR",
          "AR-015 AUTO-DISABLED" in text)
    board["ar_expiry"] = {"error": "boom"}
    check("an unreadable register renders UNMEASURED, not 'none expiring'",
          "UNMEASURED" in rb.render(board, {"next": "x", "warnings": []}))

    retro = _load("ops_retro_sysexp", "runbooks/ops-retro.py")
    m = retro.ar_expiry_metrics(rows, today=TODAY)
    check("the retro measures the same report",
          m["measured"] and [r["ar_id"] for r in m["value"]["expiring"]] == exp_ids)
    check("the retro reports UNMEASURED without the DB",
          retro.ar_expiry_metrics(None)["measured"] is False)

    print()
    if FAILURES:
        print(f"FAILED ({len(FAILURES)}): {', '.join(FAILURES)}")
        return 1
    print("all systematic-expiry tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
