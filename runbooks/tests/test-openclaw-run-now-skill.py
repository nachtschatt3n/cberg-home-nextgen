"""Regression tests for the OpenClaw side of the NOW trigger.

The say-so path ("run the X upgrade now") existed and was dead: `home-operation
run` resolved the issue to its SCHEDULED window id and fired a normal window
run, whose agent found no plans due in that slot today and went idle; and both
skills still named window ids retired in the 2026-08-26 reshape. The skill code
ships SOPS-encrypted inside kubernetes/apps/ai/openclaw/app/skills-configmap.sops.yaml
(ConfigMap openclaw-skills), so a test that only read a plaintext copy would
test something that is not deployed. This test decrypts the COMMITTED ConfigMap
into a private temp dir, imports the two skills from there, and pins:

  maintenance-window.py
    * the NOW prompt starts with the machine-detectable marker line and names
      the on-demand contract (slot now, ad-hoc, Step 0, run-now.py preflight);
    * run-now REFUSES (non-zero, nothing sent, no /clear) into a mid-turn
      console, and sends — without /clear — into an idle one;
    * a cron /clear is skipped when the console is busy;
    * plan ids are validated before they reach a prompt;
    * run-now REFUSES (exit 10, nothing sent) while window_runs holds ANY OPEN
      `now` row, whatever its run_date — a NOW run waiting at an operator
      question is idle on screen, and an evening run waiting overnight is dated
      YESTERDAY (the reviewer's fixture: an open row dated yesterday only). The
      query has NO run_date predicate, the refusal names the row's run_date and
      started_at and the --finalize remedy, and it fails CLOSED (exit 7) when
      that ledger cannot be read; the query goes through the READER DSN on
      stdin (fake psql runner over a fake window_runs table);
    * `run --window now` / `retry --window now` are refused toward run-now;
    * no retired window id survives in hints, prompt or help, and a retired id
      on the command line is refused with its replacement.
  home-operation.py
    * `run --issue` records the approval (by "operator (say-so run-now)") with
      window now:<today>, so decisions --pending-exec serves it and tick
      expires it; an existing approval for another window is re-scoped;
    * `run --issue` needs the EXACT key: the reviewer's repro (go_no_go
      prometheus-crd-ownership whose title mentions unpoller-v5.2.5, then
      `run --issue unpoller-v5.2.5`) exits 3 and records nothing;
    * a dispatch that fails (rc != 0 or an exception) undoes the say-so: a
      re-scoped GO gets its window back, a new approval is withdrawn, and a
      say-so over a prior DEFER restores that defer exactly;
    * --no-push writes nothing;
    * repeatable and comma --issue values become one run-now argv;
    * no-match / ambiguous / denied exit non-zero and write NOTHING;
    * --window still triggers a scheduled window run.

No sops or no age key: prints a loud SKIP line and returns 0 — the suite must
not fail on a machine without the key, and must not pretend it tested either.
OPENCLAW_SKILLS_DIR=<dir> imports plaintext skills from <dir> instead (for
developing a change before it is encrypted).

Run:  python3 runbooks/tests/test-openclaw-run-now-skill.py
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
CONFIGMAP = REPO / "kubernetes/apps/ai/openclaw/app/skills-configmap.sops.yaml"
KEYS = ("home-operation.py", "maintenance-window.py",
        "skill-home-operation.md", "skill-maintenance-window.md")
RETIRED = ("tue-early", "thu-early", "sun-window", "sat-early")
FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


def decrypt_into(dest: Path) -> str | None:
    """Decrypt the four keys into dest. Returns a SKIP reason, or None."""
    if not shutil.which("sops"):
        return "sops binary not found"
    for key in KEYS:
        try:
            r = subprocess.run(["sops", "-d", "--extract", f'["data"]["{key}"]', str(CONFIGMAP)],
                               capture_output=True, text=True, timeout=60)
        except Exception as e:  # noqa: BLE001
            return f"sops failed to run: {e}"
        if r.returncode != 0:
            return f"sops could not decrypt {key} (age key unavailable?): {r.stderr.strip()[:160]}"
        path = dest / key
        path.write_text(r.stdout)
        path.chmod(0o600)
    return None


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_main(fn, argv):
    """(exit code, stdout+stderr) of a skill main(), SystemExit-tolerant."""
    buf = io.StringIO()
    code = 0
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        try:
            rc = fn(argv)
            code = rc or 0
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    return code, buf.getvalue()


def test_maintenance_window(mw) -> None:
    ids, bad = mw.normalize_plan_ids(["a-1,b.2", "a-1", " c "])
    check("mw: --plan values split on commas, de-duplicated, order kept",
          ids == ["a-1", "b.2", "c"] and not bad, f"{ids} {bad}")
    _, bad = mw.normalize_plan_ids(["ok", "evil; rm -rf /", "Upper"])
    check("mw: non-plan-id values are rejected before reaching a prompt",
          bad == ["evil; rm -rf /", "Upper"], str(bad))

    prompt = mw._now_prompt(["grafana-13", "absenty"])
    first = prompt.splitlines()[0]
    check("mw: NOW prompt first line is the exact marker",
          first == "[OPERATOR NOW-RUN — MAINTENANCE_WINDOW_TRIGGER=now, plans=grafana-13,absenty]",
          first)
    for needle in ("On-demand NOW runs (operator-triggered, attended)", "--slot now",
                   "--trigger ad-hoc", "Step 0", "runbooks/run-now.py preflight grafana-13 absenty",
                   "STRICTLY SERIALLY", "settle_before", "--supervised", "--finalize",
                   "EXACTLY these plans"):
        check(f"mw: NOW prompt carries {needle!r}", needle in prompt)

    check("mw: WINDOW_HINTS are exactly the current windows",
          set(mw.WINDOW_HINTS) == {"nightly", "sat-attended", "sun-attended"},
          str(sorted(mw.WINDOW_HINTS)))
    real = yaml.safe_load((REPO / "runbooks/maintenance-windows.yaml").read_text())
    check("mw: WINDOW_HINTS match runbooks/maintenance-windows.yaml windows:",
          set(mw.WINDOW_HINTS) == {w["id"] for w in real["windows"]})
    check("mw: ON_DEMAND_SLOT matches the YAML on_demand id",
          mw.ON_DEMAND_SLOT == (real.get("on_demand") or {}).get("id"))
    base = mw._base_prompt(None, "cron") + mw._base_prompt("nightly", "manual")
    helptxt = mw.build_parser().format_help()
    for rid in RETIRED:
        check(f"mw: retired id {rid!r} absent from prompt text and --help",
              rid not in base and rid not in helptxt)
    code, out = run_main(mw.main, ["run", "--window", "sun-window", "--dry-run"])
    check("mw: a retired --window id is refused, naming the replacement",
          code != 0 and "sun-attended" in out, f"{code} {out[:200]}")

    check("mw: console_busy detects a live turn", mw.console_busy("✻ Working… (esc to interrupt)"))
    check("mw: console_busy is quiet on an idle prompt",
          not mw.console_busy("╭────╮\n│ ❯          │\n╰────╯\n  ⏵⏵ bypass permissions on"))

    # ---- run-now dispatch against a fake console ------------------------
    calls: list[tuple] = []
    screen = {"text": ""}

    class Res:
        def __init__(self, rc=0, out=""):
            self.returncode, self.stdout, self.stderr = rc, out, ""

    def fake_oc(*args, timeout=120):
        calls.append(args)
        if args and args[0] == "screen":
            return Res(0, screen["text"])
        return Res(0, "")

    code, out = run_main(mw.main, ["run", "--window", "now", "--dry-run"])
    check("mw N1: run --window now is refused with a pointer to run-now --plan",
          code == 2 and "run-now --plan" in out, f"{code} {out[:200]}")
    code, out = run_main(mw.main, ["retry", "--window", "now", "--dry-run"])
    check("mw N1: retry --window now is refused with a pointer to run-now --plan",
          code == 2 and "run-now --plan" in out, f"{code} {out[:200]}")

    # fake kubectl/psql over a fake window_runs table (never the real cluster).
    # It HONOURS a run_date predicate if the SQL carries one, so a guard that
    # still filters on today would genuinely miss yesterday's open row.
    import re as _re
    ledger = {"rows": [], "psql_rc": 0}   # open `now` rows: (run_date, started_at)
    execs: list[dict] = []

    class Proc:
        def __init__(self, rc, out, err=""):
            self.returncode, self.stdout, self.stderr = rc, out, err

    def fake_subprocess_run(argv, **kw):
        execs.append({"argv": list(argv), "input": kw.get("input")})
        if argv[:3] == ["kubectl", "-n", "databases"] and "secret" in argv:
            return Proc(0, __import__("base64").b64encode(b"postgres://reader:pw@db/sweep").decode())
        if argv[:len(mw.PG_EXEC)] == mw.PG_EXEC:
            if ledger["psql_rc"]:
                return Proc(ledger["psql_rc"], "", "psql: connection refused")
            sql = argv[-1]
            rows = list(ledger["rows"])
            m = _re.search(r"run_date\s*=\s*'([^']+)'", sql)
            if m:
                rows = [r for r in rows if r[0] == m.group(1)]
            if "count(*)" in sql:
                return Proc(0, f"{len(rows)}\n")
            return Proc(0, "".join(f"{d}|{t}\n" for d, t in rows))
        raise AssertionError(f"unexpected subprocess {argv}")

    orig = (mw.oc, mw.resolve_session, mw.subprocess.run)
    mw.oc = fake_oc
    mw.resolve_session = lambda: ("sid-1234", "daily-operation")
    mw.subprocess.run = fake_subprocess_run
    try:
        # ---- B2: an OPEN on-demand run refuses a second say-so ----
        screen["text"] = "╭──╮\n│ ❯  │\n╰──╯\n ⏵⏵ bypass permissions on"   # idle-looking
        today = mw._today_utc()
        ledger.update(rows=[(today, f"{today} 07:10:00+00")], psql_rc=0)
        calls.clear(); execs.clear()
        code, out = run_main(mw.main, ["run-now", "--plan", "grafana-13"])
        check("mw B2: run-now with an OPEN now row today exits 10 (new distinct code)",
              code == 10 and "already OPEN" in out, f"{code} {out[:300]}")
        check("mw B2: ...and sends nothing into the idle-looking console",
              not [c for c in calls if c[0] in ("send", "ask", "key")], str(calls))

        # the reviewer's fixture: the ONLY open row is dated YESTERDAY (an
        # evening run opened 20:00 UTC, waiting at a question overnight)
        yday = (datetime.fromisoformat(today) - timedelta(days=1)).date().isoformat()
        ledger.update(rows=[(yday, f"{yday} 20:00:07.123+00")], psql_rc=0)
        calls.clear(); execs.clear()
        code, out = run_main(mw.main, ["run-now", "--plan", "grafana-13"])
        check("mw B2 R1: an OPEN now row dated YESTERDAY only -> exit 10",
              code == 10 and "already OPEN" in out, f"{code} {out[:400]}")
        check("mw B2 R1: ...and sends nothing (no send/ask/key) into the idle-looking console",
              not [c for c in calls if c[0] in ("send", "ask", "key")], str(calls))
        check("mw B2 R3: ...the refusal names the open row's run_date and started_at",
              f"run_date {yday}" in out and f"{yday} 20:00:07.123+00" in out, out[:500])
        check("mw B2 R3: ...and the --finalize remedy for that run_date",
              "--finalize" in out and f"--run-date {yday}" in out and "--slot now" in out, out[:600])
        psql = [e for e in execs if e["argv"][:len(mw.PG_EXEC)] == mw.PG_EXEC]
        sql = " ".join(psql[0]["argv"]) if psql else ""
        check("mw B2 R2: the ledger query is slot now + outcome running + finished_at IS NULL",
              psql and "slot = 'now'" in sql and "outcome = 'running'" in sql
              and "finished_at IS NULL" in sql, sql)
        check("mw B2 R2: ...with NO run_date predicate (any date's open row counts)",
              psql and not _re.search(r"run_date\s*(=|<|>|IN|BETWEEN)", sql, _re.I)
              and "WHERE" in sql and "run_date =" not in sql, sql)
        check("mw B2: the READER DSN travels on stdin, never in argv",
              psql and "postgres://reader" in (psql[0]["input"] or "")
              and not any("postgres://reader" in " ".join(e["argv"]) for e in execs), str(execs))

        ledger.update(rows=[("not-a-date", "x")], psql_rc=0)
        calls.clear()
        code, out = run_main(mw.main, ["run-now", "--plan", "grafana-13"])
        check("mw B2: an unparseable ledger row fails CLOSED (exit 7), nothing sent",
              code == 7 and not [c for c in calls if c[0] in ("send", "ask", "key")],
              f"{code} {out[:300]}")
        ledger.update(rows=[], psql_rc=2)
        calls.clear()
        code, out = run_main(mw.main, ["run-now", "--plan", "grafana-13"])
        check("mw B2: an unreadable ledger fails CLOSED (exit 7), nothing sent",
              code == 7 and not [c for c in calls if c[0] in ("send", "ask", "key")],
              f"{code} {out[:300]}")
        ledger.update(rows=[], psql_rc=0)
        execs.clear()
        code, out = run_main(mw.main, ["run-now", "--plan", "grafana-13", "--dry-run"])
        check("mw B2: --dry-run does not read the ledger", code == 0 and not execs, str(execs))

        screen["text"] = "⏺ running the sweep…\n✻ Thinking… (esc to interrupt)"
        calls.clear()
        code, out = run_main(mw.main, ["run-now", "--plan", "grafana-13"])
        sent = [c for c in calls if c[0] in ("send", "ask", "key")]
        check("mw: run-now into a MID-TURN console exits non-zero",
              code != 0 and mw.FAIL_TOKEN in out, f"{code} {out[:200]}")
        check("mw: ...and sends nothing (no send/ask/key, no /clear)", not sent, str(sent))

        screen["text"] = "╭──╮\n│ ❯  │\n╰──╯\n ⏵⏵ bypass permissions on"
        calls.clear()
        code, out = run_main(mw.main, ["run-now", "--plan", "grafana-13", "--plan", "absenty"])
        sends = [c for c in calls if c[0] == "send"]
        check("mw: run-now into an IDLE console sends exactly one prompt",
              code == 0 and len(sends) == 1, f"{code} {calls}")
        check("mw: ...carrying the marker for both plans",
              sends and sends[0][2].startswith(
                  "[OPERATOR NOW-RUN — MAINTENANCE_WINDOW_TRIGGER=now, plans=grafana-13,absenty]"))
        check("mw: ...and never /clears the console",
              not any("/clear" in c for c in calls), str(calls))

        calls.clear()
        code, out = run_main(mw.main, ["run-now", "--plan", "grafana-13", "--window", "nightly"])
        check("mw: run-now refuses --window (it never runs in a scheduled slot)",
              code != 0 and not [c for c in calls if c[0] == "send"])
        code, out = run_main(mw.main, ["run-now"])
        check("mw: run-now with no --plan is refused", code != 0)

        screen["text"] = "✻ Thinking… (esc to interrupt)"
        calls.clear()
        with contextlib.redirect_stderr(io.StringIO()):
            mw._clean_session("sid-1234")
        check("mw: _clean_session does NOT /clear a busy console",
              not any("/clear" in c for c in calls), str(calls))
        screen["text"] = "│ ❯  │"
        calls.clear()
        with contextlib.redirect_stderr(io.StringIO()):
            orig_sleep = __import__("time").sleep
            __import__("time").sleep = lambda s: None
            try:
                mw._clean_session("sid-1234")
            finally:
                __import__("time").sleep = orig_sleep
        check("mw: _clean_session still /clears an idle console (cron runs)",
              any("/clear" in c for c in calls), str(calls))
    finally:
        mw.oc, mw.resolve_session, mw.subprocess.run = orig

    def no_oc(*a, **k):
        raise AssertionError("dry-run must not touch openclaude")

    mw.oc = no_oc
    try:
        code, out = run_main(mw.main, ["run-now", "--plan", "grafana-13", "--dry-run"])
        check("mw: run-now --dry-run prints the exact prompt and touches no session",
              code == 0 and mw._now_prompt(["grafana-13"]) in out, out[:300])
    finally:
        mw.oc = orig[0]


def test_home_operation(ho_path: Path, state: Path) -> None:
    os.environ["HOME_OP_STATE_DIR"] = str(state)
    ho = load("home_operation_under_test", ho_path)
    argvs: list[list] = []

    class Res:
        returncode, stdout, stderr = 0, "sent", ""

    def fake_run(argv, **kw):
        argvs.append(list(argv))
        return Res()

    ho.subprocess.run = fake_run
    ho.MW_BIN = "/bin/maintenance-window"
    today = ho._local_today().isoformat()
    now_ref = f"now:{today}"

    def ingest(key, **kw):
        payload = {"key": key, "kind": "go_no_go", "source": "maintenance",
                   "action": "approve,deny,defer", "severity": "warning",
                   "title": f"{key} upgrade", "component": kw.pop("component", key),
                   "window": "sun-attended:2026-09-20",
                   "plan_path": f"runbooks/maintenance/plans/{key}.md"}
        payload.update(kw)
        code, out = run_main(ho.main, ["--no-push", "ingest", "--json", __import__("json").dumps(payload)])
        assert code == 0, out

    def issue(key):
        c = sqlite3.connect(ho.DB_PATH)
        c.row_factory = sqlite3.Row
        r = c.execute("SELECT * FROM issues WHERE key=?", (key,)).fetchone()
        c.close()
        return r

    check("ho: parse_issue_args flattens repeats + commas, de-duplicated",
          ho.parse_issue_args(["a,b", "c", "a"]) == ["a", "b", "c"])
    check("ho: run_now_argv shape",
          ho.run_now_argv("/mw", ["a", "b"], True) == ["/mw", "run-now", "--plan", "a", "--plan", "b", "--dry-run"])

    def events(key):
        c = sqlite3.connect(ho.DB_PATH)
        rows = [r[0] for r in c.execute("SELECT kind FROM events WHERE key=? ORDER BY id", (key,))]
        c.close()
        return rows

    # ---- B1: the reviewer's wrong-issue repro, exactly ---------------------
    ingest("prometheus-crd-ownership", component="kube-prometheus-stack",
           title="prometheus CRD ownership (blocks unpoller-v5.2.5)")
    before = dict(issue("prometheus-crd-ownership"))
    for flags in (["--no-push", "--json"], ["--json"]):
        argvs.clear()
        code, out = run_main(ho.main, flags + ["run", "--issue", "unpoller-v5.2.5"])
        r = issue("prometheus-crd-ownership")
        check(f"ho B1 {flags}: run --issue unpoller-v5.2.5 exits 3 (no exact key)",
              code == 3, f"{code} {out[:300]}")
        check(f"ho B1 {flags}: ...records NOTHING on prometheus-crd-ownership",
              dict(r) == before and r["decision"] is None
              and r["window"] == "sun-attended:2026-09-20", dict(r))
        check(f"ho B1 {flags}: ...dispatches nothing", not argvs, str(argvs))
        check(f"ho B1 {flags}: ...the substring hit is listed only as a suggestion",
              '"suggestions"' in out and "prometheus-crd-ownership" in out, out[:400])
    check("ho B1: no decided/rescoped event was written for the wrong issue",
          not any(k in ("decided", "rescoped") for k in events("prometheus-crd-ownership")),
          str(events("prometheus-crd-ownership")))

    ingest("grafana-13", component="grafana")
    argvs.clear()
    code, out = run_main(ho.main, ["--json", "--no-push", "run", "--issue", "grafana"])
    check("ho B1: a name that is not the exact key is refused (exit 3) even when it is unique",
          code == 3 and issue("grafana-13")["decision"] is None and not argvs
          and "grafana-13" in out, f"{code} {out[:300]}")

    # ---- N2: --no-push is a dry run, no writes ----------------------------
    before = dict(issue("grafana-13"))
    argvs.clear()
    code, out = run_main(ho.main, ["--json", "--no-push", "run", "--issue", "GRAFANA-13"])
    check("ho N2: --no-push run --issue (exact key, any case) exits 0",
          code == 0, f"{code} {out[:300]}")
    check("ho N2: ...writes NOTHING (row identical, no events)",
          dict(issue("grafana-13")) == before
          and not any(k in ("decided", "rescoped") for k in events("grafana-13")), dict(issue("grafana-13")))
    check("ho N2: ...reports would_record with the now:<today> window",
          '"would_record"' in out and now_ref in out, out[:400])
    check("ho N2: ...dispatch is run-now --dry-run",
          argvs == [["/bin/maintenance-window", "run-now", "--plan", "grafana-13", "--dry-run"]],
          str(argvs))

    argvs.clear()
    code, out = run_main(ho.main, ["--json", "run", "--issue", "grafana-13"])
    r = issue("grafana-13")
    check("ho: run --issue exits 0 on an exact go/no-go key", code == 0, out[:300])
    check("ho: ...records approve by 'operator (say-so run-now)'",
          r["decision"] == "approve" and r["decided_by"] == "operator (say-so run-now)"
          and r["status"] == "decided", dict(r))
    check("ho: ...sets exec_state=pending and window now:<today Europe/Berlin>",
          r["exec_state"] == "pending" and r["window"] == now_ref, f"{r['exec_state']} {r['window']}")
    check("ho: ...dispatches maintenance-window run-now --plan <key>",
          argvs == [["/bin/maintenance-window", "run-now", "--plan", "grafana-13"]],
          str(argvs))
    code, out = run_main(ho.main, ["--json", "decisions", "--pending-exec"])
    dec = __import__("json").loads(out)["decisions"]
    check("ho: decisions --pending-exec serves the NOW approval (the window agent's authorization path)",
          any(d["key"] == "grafana-13" and d["window"] == now_ref for d in dec), str(dec))

    # existing approval for a scheduled window gets re-scoped, not duplicated
    ingest("absenty")
    run_main(ho.main, ["--no-push", "decide", "--issue", "absenty", "--decision", "approve",
                       "--by", "operator (Mathias)"])
    argvs.clear()
    code, out = run_main(ho.main, ["run", "--issue", "absenty,grafana-13", "--issue", "absenty"])
    r = issue("absenty")
    check("ho: an existing approval is RE-SCOPED to now:<today>, decided_by kept",
          code == 0 and r["window"] == now_ref and r["decided_by"] == "operator (Mathias)", dict(r))
    check("ho: repeat + comma --issue -> one run-now argv, de-duplicated",
          argvs == [["/bin/maintenance-window", "run-now", "--plan", "absenty",
                     "--plan", "grafana-13"]], str(argvs))

    # failures write nothing
    ingest("redis-8", component="redis")
    ingest("redis-exporter", component="redis")
    argvs.clear()
    code, out = run_main(ho.main, ["--json", "run", "--issue", "redis"])
    check("ho: a name matching two issues exits 3, both only as suggestions",
          code == 3 and "redis-8" in out and "redis-exporter" in out, f"{code} {out[:300]}")
    check("ho: ...and records NOTHING and dispatches nothing",
          issue("redis-8")["decision"] is None and not argvs)
    code, out = run_main(ho.main, ["--json", "run", "--issue", "redis-8", "--issue", "nope"])
    check("ho: one unmatched issue among several -> exit 3, suggestions listed",
          code == 3 and "suggestions" in out, f"{code} {out[:300]}")
    check("ho: ...all-or-nothing: the matched one was NOT approved either",
          issue("redis-8")["decision"] is None and not argvs)
    run_main(ho.main, ["--no-push", "decide", "--issue", "redis-exporter", "--decision", "deny"])
    code, out = run_main(ho.main, ["--json", "run", "--issue", "redis-exporter"])
    check("ho: a DENIED issue is refused (exit 5), not silently re-approved",
          code == 5 and issue("redis-exporter")["decision"] == "deny" and not argvs, f"{code} {out[:200]}")
    run_main(ho.main, ["--no-push", "ingest", "--json", __import__("json").dumps(
        {"key": "F-12345678", "kind": "finding", "source": "sweep", "title": "some finding"})])
    code, out = run_main(ho.main, ["--json", "run", "--issue", "F-12345678"])
    check("ho: a non-go/no-go issue cannot be run now (exit 5)", code == 5 and not argvs, f"{code}")

    code, out = run_main(ho.main, ["--no-push", "run", "--issue", "redis-8", "--window", "nightly"])
    check("ho: --issue and --window together are refused", code == 2 and not argvs)
    code, out = run_main(ho.main, ["--no-push", "run", "--window", "sat-attended"])
    check("ho: --window still triggers a scheduled window run",
          argvs == [["/bin/maintenance-window", "run", "--window", "sat-attended",
                     "--trigger", "say-so", "--dry-run"]], str(argvs))

    # ---- B4: a say-so that did not dispatch leaves no live GO behind -------
    import json as _json
    class Busy:
        returncode, stdout, stderr = 8, "MAINTENANCE_WINDOW_HANDOFF_FAILED: console mid-turn", ""

    ho.subprocess.run = lambda argv, **kw: Busy()
    before = dict(issue("redis-8"))
    code, out = run_main(ho.main, ["--json", "run", "--issue", "redis-8"])
    r = issue("redis-8")
    check("ho B4: failing dispatch (busy, exit 8) propagates rc 8", code == 8, f"{code} {out[:300]}")
    check("ho B4: a NEW say-so approval is reverted — no pending GO remains",
          r["decision"] is None and r["exec_state"] is None and r["status"] == "open"
          and r["window"] == before["window"] and r["decided_by"] == before["decided_by"], dict(r))
    code2, out2 = run_main(ho.main, ["--json", "decisions", "--pending-exec"])
    check("ho B4: ...decisions --pending-exec does not serve it",
          not any(d["key"] == "redis-8" for d in _json.loads(out2)["decisions"]), out2[:300])
    check("ho B4: ...event sayso-approval-reverted logged",
          "sayso-approval-reverted" in events("redis-8"), str(events("redis-8")))
    try:
        res = _json.loads(out.split("\n{", 1)[0] if not out.lstrip().startswith("{") else
                          out[:out.rindex("}") + 1])
    except Exception:  # noqa: BLE001
        res = {}
    check("ho B4: ...the JSON reports exactly what was reverted",
          res.get("reverted") == [{"key": "redis-8", "reverted": "approval", "decision": None,
                                   "status": "open", "window": before["window"]}], out[:500])

    # existing scheduled GO + failing dispatch -> window restored
    ingest("loki-3", component="loki")
    run_main(ho.main, ["--no-push", "decide", "--issue", "loki-3", "--decision", "approve",
                       "--by", "operator (Mathias)"])
    before = dict(issue("loki-3"))
    code, out = run_main(ho.main, ["--json", "run", "--issue", "loki-3"])
    r = issue("loki-3")
    check("ho B4: existing scheduled GO + failing dispatch -> window restored",
          code == 8 and r["window"] == "sun-attended:2026-09-20" and r["decision"] == "approve"
          and r["exec_state"] == "pending" and r["decided_by"] == "operator (Mathias)"
          and dict(r) == before, dict(r))
    check("ho B4: ...event rescope-reverted logged",
          "rescope-reverted" in events("loki-3"), str(events("loki-3")))

    # R4: a say-so over a prior DEFER + failing dispatch -> the defer comes back exactly
    ho.subprocess.run = lambda argv, **kw: Busy()
    ingest("tempo-2", component="tempo")
    code, out = run_main(ho.main, ["--no-push", "decide", "--issue", "tempo-2", "--decision", "defer",
                                   "--until", "+48h", "--note", "after the holidays",
                                   "--by", "operator (Mathias)"])
    before = dict(issue("tempo-2"))
    check("ho R4: fixture: tempo-2 is deferred with a snooze", code == 0
          and before["decision"] == "defer" and before["snooze_until"], f"{code} {before}")
    code, out = run_main(ho.main, ["--json", "run", "--issue", "tempo-2"])
    r = issue("tempo-2")
    check("ho R4: say-so over a DEFER + failing dispatch -> rc 8", code == 8, f"{code} {out[:300]}")
    check("ho R4: ...the prior defer is restored EXACTLY (decision, status, note, "
          "decided_at/by, snooze_until, window, exec_state)",
          dict(r) == before, f"{dict(r)} != {before}")
    check("ho R4: ...decisions --pending-exec does not serve it",
          not any(d["key"] == "tempo-2" for d in _json.loads(
              run_main(ho.main, ["--json", "decisions", "--pending-exec"])[1])["decisions"]))
    try:
        res4 = _json.loads(out[:out.rindex("}") + 1])
    except Exception:  # noqa: BLE001
        res4 = {}
    check("ho R4: ...the JSON reports the restored decision, not NULL",
          res4.get("reverted") == [{"key": "tempo-2", "reverted": "approval", "decision": "defer",
                                    "status": before["status"], "window": before["window"]}],
          out[:500])

    # dispatch raises -> same undo
    def boom(argv, **kw):
        raise OSError("exec format error")

    ho.subprocess.run = boom
    before = dict(issue("redis-8"))
    code, out = run_main(ho.main, ["--json", "run", "--issue", "redis-8,loki-3"])
    check("ho B4: dispatch that RAISES -> non-zero and both kinds reverted",
          code != 0 and dict(issue("redis-8")) == before and issue("loki-3")["window"]
          == "sun-attended:2026-09-20" and issue("loki-3")["exec_state"] == "pending",
          f"{code} {dict(issue('redis-8'))} {dict(issue('loki-3'))}")

    helptxt = ""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            ho.main(["run", "--help"])
        except SystemExit:
            pass
    # argparse wraps long help at hyphens ("sat-\n   attended"); un-wrap first
    helptxt = __import__("re").sub(r"-\s+", "-", buf.getvalue())
    check("ho: run --help names the current windows, no retired ids",
          "sat-attended" in helptxt and not any(rid in helptxt for rid in RETIRED), helptxt)

    # tick expiry parses the now:<date> the run stamped
    c = sqlite3.connect(ho.DB_PATH)
    old = (datetime.now(timezone.utc) - timedelta(days=3)).date().isoformat()
    c.execute("UPDATE issues SET window=? WHERE key='grafana-13'", (f"now:{old}",))
    c.commit()
    c.close()
    code, out = run_main(ho.main, ["--json", "--no-push", "tick"])
    r = issue("grafana-13")
    check("ho: tick voids a NOW GO whose run never happened (2+ days)",
          r["decision"] is None and r["exec_state"] is None and r["status"] == "open", dict(r))


def main() -> int:
    print("test-openclaw-run-now-skill")
    override = os.environ.get("OPENCLAW_SKILLS_DIR")
    tmp = Path(tempfile.mkdtemp(prefix="openclaw-skill-test-"))
    tmp.chmod(0o700)
    try:
        if override:
            src = Path(override)
            print(f"  NOTE  importing PLAINTEXT skills from OPENCLAW_SKILLS_DIR={src} "
                  f"(not the committed ConfigMap)")
        else:
            src = tmp / "skills"
            src.mkdir()
            skip = decrypt_into(src)
            if skip:
                print(f"  SKIP  !!! test-openclaw-run-now-skill NOT RUN: {skip}. "
                      f"The OpenClaw NOW-trigger skills are UNTESTED on this machine. !!!")
                return 0
        sys.dont_write_bytecode = True
        mw = load("maintenance_window_under_test", src / "maintenance-window.py")
        test_maintenance_window(mw)
        state = tmp / "state"
        state.mkdir()
        test_home_operation(src / "home-operation.py", state)
        mdh = (src / "skill-home-operation.md").read_text()
        mdm = (src / "skill-maintenance-window.md").read_text()
        check("md: home-operation intents map 'run the X upgrade now' to run --issue",
              "run the X upgrade now" in mdh and "home-operation run --issue X" in mdh)
        check("md: maintenance-window verbs table documents run-now",
              "maintenance-window run-now --plan" in mdm)
        check("md: no retired window id is presented as current",
              not any(f"`{rid}` (" in mdm or f"--window {rid}" in mdm + mdh for rid in RETIRED))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} -> {', '.join(FAILURES)}")
        return 1
    print("all openclaw run-now skill tests passed")
    return 0


def test_pytest_entry() -> None:
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
