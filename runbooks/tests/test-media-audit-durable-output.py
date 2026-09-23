#!/usr/bin/env python3
"""Regression test for the media audit's durable output channel
(plan media-audit-durable-output, 2026-09-23).

The audit's only artifact used to be pod stdout; a node reboot on 2026-09-06
garbage-collected the completed pod before anyone read it. The fix has three
halves that must stay agreed on ONE line format, and this test pins the
contract between them from the repo files alone (no cluster needed):

  1. audit.py prints `AUDIT_RESULT_JSON {...}` as its LAST stdout line --
     compact, one line, the per-section Summary numbers plus a timestamp,
     never a media title.
  2. the CronJob's `persist` container extracts exactly that line with
     busybox-sh `${line#AUDIT_RESULT_JSON }` and INSERTs it as jsonb; every
     `$` in both container scripts must be `$$`-escaped or Flux postBuild
     eats it (init-job v2a history), and the audit container must be first
     + annotated so `kubectl logs job/...` still means the audit's output.
  3. dashboard.py renders a persisted row in the same '## Summary' shape and
     falls back to pod logs when the driver, secret or DB is missing.

Run: python3 runbooks/tests/test-media-audit-durable-output.py
"""
import ast
import builtins
import json
import pathlib
import re
import subprocess
import sys
import tempfile
import types
import urllib.parse

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
APP = REPO_ROOT / "kubernetes/apps/media/library-tools/app"
PASS = FAIL = 0


def check(name, got, want):
    global PASS, FAIL
    if got == want:
        print(f"  PASS  {name}")
        PASS += 1
    else:
        print(f"  FAIL  {name}\n        got {got!r}\n        want {want!r}")
        FAIL += 1


try:
    import yaml
except ImportError:
    print("  SKIP  PyYAML not installed")
    sys.exit(0)

scripts = yaml.safe_load((APP / "scripts-configmap.yaml").read_text())["data"]
dashboard_src = yaml.safe_load((APP / "dashboard-configmap.yaml").read_text())["data"]["dashboard.py"]
cronjob = yaml.safe_load((APP / "audit-cronjob.yaml").read_text())
deployment = yaml.safe_load((APP / "dashboard-deployment.yaml").read_text())
schema = yaml.safe_load((REPO_ROOT / "kubernetes/apps/databases/sweep-history/app/schema-configmap.yaml")
                        .read_text())["data"]["schema.sql"]

# --- 1. audit.py emits the line -------------------------------------------
with tempfile.TemporaryDirectory() as td:
    td = pathlib.Path(td)
    app_dir = td / "app"
    app_dir.mkdir()
    (app_dir / "common.py").write_text(scripts["common.py"])
    (app_dir / "audit.py").write_text(
        scripts["audit.py"].replace('sys.path.insert(0, "/app")', f'sys.path.insert(0, {str(app_dir)!r})'))
    media = td / "media"
    for sec in ("Movies", "TV Shows", "Music"):
        (media / sec).mkdir(parents=True)
    mov = media / "Movies" / "Fixture Movie (2020)"
    mov.mkdir()
    (mov / "Fixture Movie (2020).mkv").touch()
    (media / "Movies" / "loose.mkv").touch()
    proc = subprocess.run([sys.executable, str(app_dir / "audit.py")],
                          env={"MEDIA_ROOT": str(media), "PATH": "/usr/bin:/bin"},
                          capture_output=True, text=True, timeout=30)
    check("audit.py runs end-to-end", proc.returncode, 0)
    lines = proc.stdout.rstrip("\n").splitlines()
    last = lines[-1] if lines else ""
    check("the LAST stdout line is AUDIT_RESULT_JSON", last.startswith("AUDIT_RESULT_JSON "), True)
    check("exactly one AUDIT_RESULT_JSON line",
          sum(1 for l in lines if l.startswith("AUDIT_RESULT_JSON ")), 1)
    try:
        result = json.loads(last[len("AUDIT_RESULT_JSON "):])
    except ValueError:
        result = {}
    check("payload keys", set(result), {"timestamp", "ran_at", "sections", "worst_pct"})
    check("payload is compact (no spaces after separators)", ", " in last or ": " in last, False)
    check("payload never carries a media title", "Fixture Movie" in last, False)
    m = re.search(r"- movies: items=(\d+), nested=(\d+), flat=(\d+)", proc.stdout)
    movies = next((s for s in result.get("sections", []) if s.get("section") == "movies"), {})
    check("sections mirror the Summary numbers exactly",
          (movies.get("items"), movies.get("nested"), movies.get("flat")),
          tuple(int(x) for x in m.groups()) if m else None)
    # the persist container's extraction, in the same sh dialect it runs under
    (td / "audit.log").write_text(proc.stdout)
    sh = subprocess.run(["sh", "-c", "line=$(grep '^AUDIT_RESULT_JSON ' audit.log | tail -n 1 || true); "
                         "json=${line#AUDIT_RESULT_JSON }; printf '%s' \"$json\""],
                        cwd=td, capture_output=True, text=True)
    check("persist-container extraction reproduces the same JSON",
          json.loads(sh.stdout) if sh.stdout else None, result)

# --- 2. the CronJob wiring -------------------------------------------------
pod = cronjob["spec"]["jobTemplate"]["spec"]["template"]
containers = pod["spec"]["containers"]
check("audit container is FIRST (kubectl logs default)", containers[0]["name"], "audit")
check("default-container annotation names the audit",
      pod["metadata"].get("annotations", {}).get("kubectl.kubernetes.io/default-container"), "audit")
check("persist container exists", [c["name"] for c in containers], ["audit", "persist"])
audit_c, persist_c = containers
check("audit still mounts the share read-only",
      next(v.get("readOnly") for v in audit_c["volumeMounts"] if v["name"] == "media"), True)
check("audit container holds NO DB credential",
      any("DSN" in e["name"] for e in audit_c.get("env", [])), False)
check("persist container never mounts the share",
      any(v["name"] == "media" for v in persist_c["volumeMounts"]), False)
check("persist takes WRITER_DSN from secret media-audit-db",
      persist_c["env"][0]["valueFrom"]["secretKeyRef"], {"name": "media-audit-db", "key": "WRITER_DSN"})
check("shared emptyDir is the only writable link between them",
      [v["name"] for v in pod["spec"]["volumes"] if "emptyDir" in v], ["out"])


def unescaped_dollars(script):
    return re.findall(r"(?<!\$)\$(?!\$)", script.replace("$$", ""))


for c, shell in ((audit_c, "bash"), (persist_c, "sh"),
                 (deployment["spec"]["template"]["spec"]["containers"][0], "bash")):
    script = c["args"][0]
    check(f"{c['name']}: every $ is $$-escaped for Flux postBuild", unescaped_dollars(script), [])
    rendered = script.replace("$$", "$")
    r = subprocess.run([shell, "-n"], input=rendered, capture_output=True, text=True)
    check(f"{c['name']}: rendered script passes {shell} -n", r.returncode, 0)
check("persist greps the same prefix audit.py prints",
      "grep '^AUDIT_RESULT_JSON ' /out/audit.log" in persist_c["args"][0], True)
persist_code = "\n".join(l for l in persist_c["args"][0].splitlines() if not l.lstrip().startswith("#"))
check("persist INSERTs via psql :'result' interpolation (stdin, not -c)",
      "VALUES (:'result'::jsonb)" in persist_code and " -c " not in persist_code, True)
check("schema.sql creates media_audit_runs idempotently",
      "CREATE TABLE IF NOT EXISTS media_audit_runs" in schema, True)

# --- 3. the dashboard -------------------------------------------------------
tree = ast.parse(dashboard_src)
want = {"pg_connect", "render_audit_result", "db_latest_audit", "latest_audit_summary"}
funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in want]
check("dashboard defines the DB-first functions", {f.name for f in funcs}, want)
check("dashboard keeps exactly one latest_audit_summary (plan premise grep)",
      dashboard_src.count("def latest_audit_summary"), 1)
check("pod-log fallback names the audit container explicitly",
      "log?container=audit" in dashboard_src, True)
calls = []


class FakeConn:
    def __init__(self, user, **kw):
        calls.append((user, kw))

    def run(self, q):
        return [("2026-09-23T04:15:26+00:00",
                 {"timestamp": 1, "ran_at": "2026-09-23T04:15:26Z", "worst_pct": 66.7,
                  "sections": [{"section": "movies", "items": 3, "nfo_pct": 66.7}]})]

    def close(self):
        pass


native = types.ModuleType("pg8000.native")
native.Connection = FakeConn
stub = types.ModuleType("pg8000")
stub.native = native
sys.modules["pg8000"], sys.modules["pg8000.native"] = stub, native
ns = {"urllib": urllib, "json": json, "latest_audit_from_pod_logs": lambda: "FALLBACK",
      # built from parts so no literal scheme://user:pw@ string sits in the repo
      "READER_DSN": urllib.parse.urlunsplit(("postgresql", "ro_user:pw%40x@db.example.svc:5433", "/sweep_history", "", ""))}
exec(compile(ast.Module(body=funcs, type_ignores=[]), "dashboard-funcs", "exec"), ns)
out = ns["latest_audit_summary"]()
check("DSN URL is parsed into pg8000 kwargs (user, host, port, db, unquoted password)",
      calls, [("ro_user", {"host": "db.example.svc", "port": 5433, "database": "sweep_history",
                           "password": "pw@x", "timeout": 5})])
check("DB row renders in the audit's own Summary shape",
      out.splitlines()[:2], ["## Summary", "- movies: items=3, nfo_pct=66.7"])
check("rendered text names its source", "source: sweep_history.media_audit_runs" in out, True)
ns["READER_DSN"] = ""
check("no READER_DSN -> pod-log fallback", ns["latest_audit_summary"](), "FALLBACK")
ns["READER_DSN"] = urllib.parse.urlunsplit(("postgresql", "u:p@h", "/d", "", ""))
del sys.modules["pg8000"], sys.modules["pg8000.native"]
real_import = builtins.__import__


def no_pg8000(name, *a, **k):
    if name.startswith("pg8000"):
        raise ImportError(name)
    return real_import(name, *a, **k)


builtins.__import__ = no_pg8000
try:
    check("pg8000 not installed -> pod-log fallback", ns["latest_audit_summary"](), "FALLBACK")
finally:
    builtins.__import__ = real_import

print(f"\n  {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
