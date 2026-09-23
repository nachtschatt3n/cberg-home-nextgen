"""Regression tests for the REGISTER-ONLY class in `policy-cli risk lint`.

GROUND TRUTH (2026-09-22, F-5c48a0fc). `risk lint` reported 22 enabled
acceptances as INERT. Twenty-one of them were enforced somewhere the lint
never looked: five by a `security_acceptances` row citing the AR (the ingress
allowlist security-check.py reads), eight by an exemption set coded into
security-check.py (ACCEPTED_PRIVILEGED, ACCEPTED_ROOT_UID, the cluster-admin
loop in s10_flux_posture), eight by an operator posture decision no detector
exists for. Their descriptions are headings, and a heading is never a
substring of a generated title BY DESIGN. The lint told the operator to
rewrite all twenty-one as needles, and the one row that really was inert was
indistinguishable from the twenty that were doing their job.

The fix teaches the lint two anchors -- an ENABLED security_acceptances
citation (derived from the table every run) and metadata.register_only=true
with an enforced_in pointer (written by `risk add/edit --register-only`) --
and reports an anchored, never-matched AR as REGISTER-ONLY naming the anchor.
Everything else keeps INERT semantics.

COMMISSIONING STRAW. The pre-fix lint never read either anchor, so what it
saw is exactly the fixed lint fed a database with the anchors removed. The
straw below runs cmd_risk_lint twice against a fake cursor: with the anchors
present the security_acceptances-cited AR reads REGISTER-ONLY, with them
absent it reads INERT -- which proves the verdict is driven by the anchor,
not by the AR id or the description -- and an AR with neither anchor reads
INERT in both runs.

Run:  python3 runbooks/tests/test-ar-lint-register-only.py
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("pc", REPO / "runbooks/policy-cli.py")
pc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pc)

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


MISS = ("some prefix", "F-abc", "a finding title")
SEC_ANCHOR = "security_acceptances:external_ingress_accepted (id 77)"
CODE_ANCHOR = "security-check.py:ACCEPTED_PRIVILEGED"


# ---- a fake database: just enough SQL dispatch for the three commands ------

class FakeCursor:
    """Answers the queries cmd_risk_lint / cmd_risk_add / cmd_risk_edit issue,
    keyed on the table each one names. Records every statement so a test can
    assert what WOULD have been written."""

    def __init__(self, ars: list[dict], sec_rows: list[dict]):
        self.ars, self.sec_rows = ars, sec_rows
        self.executed: list[tuple[str, tuple]] = []
        self._rows: list = []
        self.rowcount = 0

    def execute(self, sql: str, params=None):
        self.executed.append((sql, tuple(params or ())))
        s = " ".join(sql.split())
        if s.startswith("SELECT") and "FROM accepted_risks" in s and "ar_id = %s" in s:
            self._rows = [r for r in self.ars if r["ar_id"] == params[0]]
        elif s.startswith("SELECT") and "FROM accepted_risks" in s:
            self._rows = [{**r, "expires_at": (r.get("metadata") or {}).get("expires_at")}
                          for r in self.ars]
        elif "FROM security_acceptances" in s:
            self._rows = [r for r in self.sec_rows if r.get("enabled", True)]
        elif "FROM sweep_findings" in s and "count(*)" in s:
            self._rows = [{"n": 0}]          # nothing ever matched
        elif "FROM sweep_findings" in s:
            self._rows = []                  # no near-miss, no would-match
        elif s.startswith("INSERT INTO accepted_risks") or s.startswith("UPDATE accepted_risks"):
            self._rows, self.rowcount = [], 1
        else:
            raise AssertionError(f"fake cursor got an unexpected statement: {s[:120]}")

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeConn:
    def __init__(self, cur: FakeCursor):
        self._cur = cur

    def cursor(self):
        return self._cur

    def commit(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def run_lint(ars: list[dict], sec_rows: list[dict], all_: bool = False) -> str:
    cur = FakeCursor(ars, sec_rows)
    pc._connect = lambda dsn: FakeConn(cur)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = pc.cmd_risk_lint(argparse.Namespace(all=all_), "fake-dsn")
    assert rc == 0, rc
    return out.getvalue()


def flag_line(text: str, ar_id: str) -> str:
    for line in text.splitlines():
        if line.startswith(ar_id + " "):
            return line
    return ""


def detail_after(text: str, ar_id: str) -> str:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith(ar_id + " "):
            return lines[i + 1] if i + 1 < len(lines) else ""
    return ""


def main() -> int:
    print("AR lint REGISTER-ONLY classification:")

    # ---- the pure classifier ------------------------------------------------
    check("anchored + never matched -> REGISTER-ONLY",
          pc.lint_flag(0, [], None, 0, register_only=SEC_ANCHOR) == "REGISTER-ONLY")
    check("no anchor + never matched -> INERT (the 4-arg call is unchanged)",
          pc.lint_flag(0, [], None, 0) == "INERT")
    check("empty anchor is no anchor -> INERT",
          pc.lint_flag(0, [], None, 0, register_only="") == "INERT")

    # Rule 3: only the never-matched case is reclassified. A register-only AR
    # whose description DOES match a title is a needle, and lints like one.
    check("anchored but matching -> ok (a needle whatever the metadata says)",
          pc.lint_flag(3, [], None, 5, register_only=CODE_ANCHOR) == "ok")
    check("anchored, matching, volatile -> at risk",
          pc.lint_flag(3, ["patch version"], None, 5, register_only=CODE_ANCHOR) == "at risk")
    check("anchored with a near-miss -> DRIFTING NOW (a prefix match proves it worked)",
          pc.lint_flag(0, [], MISS, 1, register_only=CODE_ANCHOR) == "DRIFTING NOW")
    check("anchored, matched only a RESOLVED finding -> ok (dormant, not register-only)",
          pc.lint_flag(0, [], None, 1, register_only=CODE_ANCHOR) == "ok",
          pc.lint_flag(0, [], None, 1, register_only=CODE_ANCHOR))
    check("EXPIRED still outranks REGISTER-ONLY",
          pc.lint_flag(0, [], None, 0, expired=True, register_only=CODE_ANCHOR) == "EXPIRED")

    verdicts = {
        pc.lint_flag(0, [], None, 0),
        pc.lint_flag(0, [], None, 0, register_only=CODE_ANCHOR),
        pc.lint_flag(0, [], MISS, 1),
        pc.lint_flag(3, ["v"], None, 5),
        pc.lint_flag(3, [], None, 5),
        pc.lint_flag(0, [], None, 0, expired=True),
    }
    check("all six verdicts are reachable (the rule is not constant)",
          verdicts == {"INERT", "REGISTER-ONLY", "DRIFTING NOW", "at risk", "ok", "EXPIRED"},
          str(sorted(verdicts)))

    # ---- the anchor derivation ---------------------------------------------
    print("anchor derivation:")
    sec = [{"id": 77, "category": "external_ingress_accepted", "ar_id": "AR-003"},
           {"id": 63, "category": "external_ingress_accepted", "ar_id": "AR-004"},
           {"id": 72, "category": "external_ingress_accepted", "ar_id": "AR-004"},
           {"id": 5, "category": "git_history_cred", "ar_id": None}]
    meta = {"AR-003": None,
            "AR-009": {"register_only": True, "enforced_in": CODE_ANCHOR},
            "AR-002": None,
            "AR-777": {"register_only": True},                 # no pointer
            "AR-888": {"enforced_in": CODE_ANCHOR},            # no flag
            "AR-004": {"register_only": True, "enforced_in": pc.POSTURE_ANCHOR}}
    anchors = pc.register_only_anchors(meta, sec)
    check("a security_acceptances citation anchors the AR it names",
          anchors.get("AR-003") == SEC_ANCHOR, repr(anchors.get("AR-003")))
    check("several citing rows collapse to one anchor listing every id",
          "id 63,72" in anchors.get("AR-004", ""), repr(anchors.get("AR-004")))
    check("register_only=true + enforced_in anchors the AR at that pointer",
          anchors.get("AR-009") == f"{CODE_ANCHOR} (metadata.enforced_in)",
          repr(anchors.get("AR-009")))
    check("table citation AND metadata pointer both show",
          "security_acceptances" in anchors.get("AR-004", "")
          and pc.POSTURE_ANCHOR in anchors.get("AR-004", ""), repr(anchors.get("AR-004")))
    check("a row with no ar_id anchors nothing", "None" not in anchors and None not in anchors)
    check("register_only without an enforced_in pointer is NOT an anchor",
          "AR-777" not in anchors, repr(anchors.get("AR-777")))
    check("enforced_in without register_only=true is NOT an anchor",
          "AR-888" not in anchors, repr(anchors.get("AR-888")))
    check("an AR with neither is absent", "AR-002" not in anchors)

    # ---- COMMISSIONING STRAW: cmd_risk_lint end to end -------------------------
    print("commissioning straw (cmd_risk_lint against a fake DB):")
    ars = [{"ar_id": "AR-002", "description": "Mosquitto MQTT `allow_anonymous true`",
            "justification": "posture", "metadata": None},
           {"ar_id": "AR-003", "description": "echo-server on External Ingress Without Auth",
            "justification": "debug endpoint", "metadata": None},
           {"ar_id": "AR-009", "description": "Privileged Containers for Hardware Access",
            "justification": "hardware", "metadata": {"register_only": True,
                                                       "enforced_in": CODE_ANCHOR}},
           {"ar_id": "AR-777", "description": "Half-written register-only entry",
            "justification": "x", "metadata": {"register_only": True}}]
    sec_rows = [{"id": 77, "category": "external_ingress_accepted", "ar_id": "AR-003",
                 "enabled": True}]

    fixed = run_lint(ars, sec_rows)
    check("fixed lint: security_acceptances-cited AR-003 -> [REGISTER-ONLY]",
          "[REGISTER-ONLY]" in flag_line(fixed, "AR-003"), flag_line(fixed, "AR-003"))
    check("fixed lint: AR-003's detail line names the security_acceptances row",
          "security_acceptances:external_ingress_accepted (id 77)" in detail_after(fixed, "AR-003"),
          detail_after(fixed, "AR-003"))
    check("fixed lint: metadata-anchored AR-009 -> [REGISTER-ONLY] naming ACCEPTED_PRIVILEGED",
          "[REGISTER-ONLY]" in flag_line(fixed, "AR-009")
          and CODE_ANCHOR in detail_after(fixed, "AR-009"),
          flag_line(fixed, "AR-009") + " / " + detail_after(fixed, "AR-009"))
    check("fixed lint: AR-002 with neither anchor is still [INERT]",
          "[INERT]" in flag_line(fixed, "AR-002"), flag_line(fixed, "AR-002"))
    check("fixed lint: register_only without a pointer is [INERT] and says why",
          "[INERT]" in flag_line(fixed, "AR-777") and "no enforced_in pointer" in fixed,
          flag_line(fixed, "AR-777"))
    check("fixed lint: the INERT advice is not printed under a REGISTER-ONLY row",
          "NEVER matched" not in detail_after(fixed, "AR-003"), detail_after(fixed, "AR-003"))
    check("output shape: header + `AR  open-match  'desc'  [FLAG]` rows is unchanged",
          fixed.splitlines()[0].startswith("AR ") and "open-match" in fixed.splitlines()[0]
          and flag_line(fixed, "AR-003").startswith("AR-003 ")
          and "'echo-server on External Ingress Without Auth'  [" in flag_line(fixed, "AR-003"),
          fixed.splitlines()[0])

    # The pre-fix lint read neither anchor, so its view of this register is the
    # fixed lint with the anchors stripped. Same rows, same descriptions.
    before = run_lint([{**a, "metadata": None} for a in ars], [])
    check("pre-fix view (anchors stripped): AR-003 reads [INERT]",
          "[INERT]" in flag_line(before, "AR-003"), flag_line(before, "AR-003"))
    check("pre-fix view: AR-009 reads [INERT]",
          "[INERT]" in flag_line(before, "AR-009"), flag_line(before, "AR-009"))
    check("pre-fix view: AR-002 reads [INERT] in both runs",
          "[INERT]" in flag_line(before, "AR-002") and "[INERT]" in flag_line(fixed, "AR-002"))
    check("the verdict is driven by the anchor: same AR, anchor present vs absent, differs",
          flag_line(before, "AR-003") != flag_line(fixed, "AR-003"))

    # A DISABLED citing row must not anchor: the derivation reads the table
    # every run precisely so that this stays visible.
    disabled = run_lint(ars, [{**sec_rows[0], "enabled": False}])
    check("a DISABLED security_acceptances row anchors nothing -> AR-003 back to [INERT]",
          "[INERT]" in flag_line(disabled, "AR-003"), flag_line(disabled, "AR-003"))

    # Clean-register summary: when every listed row is register-only, say so.
    clean = run_lint([a for a in ars if a["ar_id"] in ("AR-003", "AR-009")], sec_rows)
    check("all rows register-only -> closing line says the rest is clean",
          "2 register-only, enforced elsewhere" in clean, clean.splitlines()[-1])
    check("a genuinely inert row suppresses the clean closing line",
          "enforced elsewhere)" not in fixed.splitlines()[-1], fixed.splitlines()[-1])

    # ---- the anchor gate ----------------------------------------------------------
    print("--register-only anchor validation:")
    check("register-only:posture is accepted", pc._anchor_problem(pc.POSTURE_ANCHOR) is None)
    check("security-check.py:ACCEPTED_PRIVILEGED resolves against the live repo",
          pc._anchor_problem(CODE_ANCHOR) is None, str(pc._anchor_problem(CODE_ANCHOR)))
    check("security-check.py:ACCEPTED_ROOT_UID resolves",
          pc._anchor_problem("security-check.py:ACCEPTED_ROOT_UID") is None)
    check("security-check.py:s10_flux_posture resolves (the cluster-admin loop)",
          pc._anchor_problem("security-check.py:s10_flux_posture") is None)
    check("a symbol that does not occur in the file is refused",
          pc._anchor_problem("security-check.py:NO_SUCH_SYMBOL_9f3c1e") is not None)
    check("a file that does not exist is refused",
          pc._anchor_problem("no-such-script-9f3c1e.py:X") is not None)
    check("a bare word with no file:SYMBOL shape is refused",
          pc._anchor_problem("posture") is not None)
    check("an empty anchor is refused", pc._anchor_problem("  ") is not None)

    # ---- the flags reach the handlers and write exactly the two keys -------------
    print("risk add / risk edit wiring:")
    parser = pc.build_parser()
    a = parser.parse_args(["risk", "add", "AR-999", "--description", "x", "--no-expiry",
                           "--register-only", CODE_ANCHOR])
    check("risk add accepts --register-only", a.register_only == CODE_ANCHOR)
    e = parser.parse_args(["risk", "edit", "AR-009", "--register-only", "none"])
    check("risk edit accepts --register-only none", e.register_only == "none")

    cur = FakeCursor([{"ar_id": "AR-009", "description": "d"}], [])
    pc._connect = lambda dsn: FakeConn(cur)
    with contextlib.redirect_stdout(io.StringIO()):
        rc = pc.cmd_risk_edit(parser.parse_args(
            ["risk", "edit", "AR-009", "--register-only", CODE_ANCHOR]), "fake")
    upd = [(s, p) for s, p in cur.executed if s.startswith("UPDATE accepted_risks")]
    check("risk edit --register-only runs one UPDATE", rc == 0 and len(upd) == 1, str(rc))
    sql, params = upd[0] if upd else ("", ())
    written = next((json.loads(p) for p in params
                    if isinstance(p, str) and p.startswith("{")), {})
    check("it merges with the `|| %s::jsonb` idiom (not jsonb_build_object)",
          "|| %s::jsonb" in sql and "jsonb_build_object" not in sql, sql)
    check("it writes exactly register_only=true + enforced_in=<anchor>",
          written == {"register_only": True, "enforced_in": CODE_ANCHOR}, str(written))

    cur = FakeCursor([{"ar_id": "AR-009", "description": "d"}], [])
    pc._connect = lambda dsn: FakeConn(cur)
    with contextlib.redirect_stdout(io.StringIO()):
        rc = pc.cmd_risk_edit(parser.parse_args(
            ["risk", "edit", "AR-009", "--register-only", "none"]), "fake")
    sql, params = next(((s, p) for s, p in cur.executed
                        if s.startswith("UPDATE accepted_risks")), ("", ()))
    check("--register-only none removes BOTH keys",
          rc == 0 and " - %s - %s" in sql and "register_only" in params and "enforced_in" in params,
          f"{sql} {params}")

    cur = FakeCursor([{"ar_id": "AR-009", "description": "d"}], [])
    pc._connect = lambda dsn: FakeConn(cur)
    with contextlib.redirect_stdout(io.StringIO()):
        rc = pc.cmd_risk_edit(parser.parse_args(
            ["risk", "edit", "AR-009", "--expires", "2027-01-01",
             "--register-only", pc.POSTURE_ANCHOR]), "fake")
    sql, params = next(((s, p) for s, p in cur.executed
                        if s.startswith("UPDATE accepted_risks")), ("", ()))
    check("--expires and --register-only compose into ONE metadata assignment",
          rc == 0 and sql.count("metadata = ") == 1 and sql.count("|| %s::jsonb") == 2, sql)

    err = io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
        rc = pc.cmd_risk_edit(parser.parse_args(
            ["risk", "edit", "AR-009", "--register-only", "security-check.py:NOPE_9f3c1e"]), "fake")
    check("risk edit refuses a dangling anchor (exit 2, REFUSING)",
          rc == 2 and "REFUSING" in err.getvalue(), f"{rc} {err.getvalue()[:80]}")

    # risk add: an anchor satisfies the nomatch gate on its own.
    cur = FakeCursor([], [])
    pc._connect = lambda dsn: FakeConn(cur)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = pc.cmd_risk_add(parser.parse_args(
            ["risk", "add", "AR-999", "--description", "A Heading That Matches Nothing",
             "--no-expiry", "--register-only", pc.POSTURE_ANCHOR]), "fake")
    ins = next(((s, p) for s, p in cur.executed if s.startswith("INSERT")), ("", ()))
    written = json.loads(ins[1][-1]) if ins[1] else {}
    check("risk add --register-only passes the nomatch gate without --allow-nomatch",
          rc in (0, None) and "register-only" in out.getvalue(), f"{rc} {out.getvalue()[:80]}")
    check("risk add writes register_only=true + enforced_in into metadata",
          written.get("register_only") is True and written.get("enforced_in") == pc.POSTURE_ANCHOR,
          str(written))
    err = io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
        rc = pc.cmd_risk_add(parser.parse_args(
            ["risk", "add", "AR-998", "--description", "x", "--no-expiry",
             "--register-only", "none"]), "fake")
    check("risk add --register-only none is refused (nothing to clear on a new AR)",
          rc == 2 and "REFUSING" in err.getvalue())

    print()
    if FAILURES:
        print(f"FAILED ({len(FAILURES)}): {', '.join(FAILURES)}")
        return 1
    print("all AR-lint register-only tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
