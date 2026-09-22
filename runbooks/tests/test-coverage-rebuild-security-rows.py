#!/usr/bin/env python3
"""Regression test: the REBUILD lane has a second feed and a qualified zero
(F-4677123a), and openclaw-sync keys one issue per self-built IMAGE.

The lane was fed by ONE signal — "a newer tag exists for a self-built image" —
which is never true for an image already at its newest self-built tag and not
computable for the rolling tags most of ours carry. So REBUILD read 0 while
the security side filed rows on the same images, and openclaw-sync's 14-day
rebuild SLA queue was permanently empty. coverage.py now (a) reads the OPEN,
NOT-accepted security rows whose title leads with an image under
SELF_BUILT_REPO_PREFIXES and merges them into the lane, (b) collects every
self-built image the version oracle could not resolve from the snapshot, and
(c) prints both next to the lane counts so REBUILD 0 is never an unqualified
zero. openclaw-sync keys the resulting issues per image.

Hermetic: a fixture snapshot on disk, a fake `psycopg` module in sys.modules,
and openclaw-sync run with --dry-run (execs nothing).

Run:  python3 runbooks/tests/test-coverage-rebuild-security-rows.py
"""
from __future__ import annotations

import importlib.util
import inspect
import json
import os
import re
import subprocess
import sys
import tempfile
import types
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
os.environ.setdefault("_MISE_ACTIVATED", "1")
sys.path.insert(0, str(_REPO / "runbooks"))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, _REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore
    return mod


cov = _load("cberg_coverage_rebuild_t", "runbooks/coverage.py")
ocs = _load("cberg_openclaw_sync_t", "runbooks/openclaw-sync.py")
OCS_SCRIPT = _REPO / "runbooks" / "openclaw-sync.py"

FAILURES: list[str] = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {str(detail)[:300]}"))
    if not ok:
        FAILURES.append(name)


def count_matches(population: str, pattern: str) -> int:
    """Guarded counter: an empty population or an error marker aborts the run
    instead of returning a silent zero."""
    if not population or not population.strip():
        raise SystemExit(f"count_matches: EMPTY population for {pattern!r}")
    for marker in ("usage:", "Traceback", "error"):
        if marker in population:
            raise SystemExit(f"count_matches: population carries {marker!r}: "
                             f"{population[:200]!r}")
    return len(re.findall(pattern, population))


SNAPSHOT = """# Kubernetes Deployment Version Status

**Generated:** 2026-09-22 00:00:00

## Namespace: `tools`

### widget-app
- **File:** `kubernetes/apps/tools/widget-app/app/helmrelease.yaml`

#### Chart
- **Repository:** `bjw-s`

#### Container Images
- **Repository:** `ghcr.io/nachtschatt3n/widget-server`
  - **Path:** `controllers.server.containers.app.image`
  - **Current Tag:** `sha-abc1234`
  - **Latest Tag:** *Could not determine*

- **Repository:** `ghcr.io/nachtschatt3n/widget-server`
  - **Path:** `controllers.server.initContainers.bundle.image`
  - **Current Tag:** `sha-abc1234`
  - **Latest Tag:** *Could not determine*

- **Repository:** `ghcr.io/nachtschatt3n/widget-frontend`
  - **Path:** `controllers.frontend.containers.app.image`
  - **Current Tag:** `0.5.4-alpha`
  - **Latest Tag:** *Could not determine*

- **Repository:** `ghcr.io/nachtschatt3n/widget-resolved`
  - **Path:** `controllers.x.containers.app.image`
  - **Current Tag:** `0.4.1`
  - **Latest Tag:** `0.4.1` ✅ (up-to-date)

- **Repository:** `docker.io/library/redis`
  - **Path:** `controllers.cache.containers.app.image`
  - **Current Tag:** `8.0.0`
  - **Latest Tag:** *Could not determine*

---
"""

# The scanner's title shapes, with the vocabulary the fixture needs and no
# more: a backticked image reference at the head, the fix-availability word.
SEC_ROWS = [
    ("F-aaaa0001", "warning",
     "`ghcr.io/nachtschatt3n/widget-server:sha-abc1234`: fixable items in an image WE "
     "build — the remedy is a rebuild in its own app repo"),
    ("F-aaaa0002", "critical",
     "`ghcr.io/nachtschatt3n/widget-server:sha-abc1234`: fixable items — newer-tag "
     "lookup undetermined; verify upstream"),
    ("F-aaaa0003", "warning",
     "`docker.io/library/redis:8.0.0`: fixable items in a third-party image"),
    ("F-aaaa0004", "warning",
     "`ghcr.io/nachtschatt3n/widget-frontend:0.5.4-alpha@sha256:0123`: fixable items in "
     "an image WE build"),
    ("F-aaaa0005", "warning",
     "Root uid=0: `ghcr.io/nachtschatt3n/other` runs as root"),
]


class _FakeCursor:
    def __init__(self, rows, log):
        self.rows, self.log = rows, log

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.log.append((sql, params))

    def fetchall(self):
        return list(self.rows)


class _FakeConn:
    def __init__(self, rows, log):
        self.rows, self.log = rows, log

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def cursor(self):
        return _FakeCursor(self.rows, self.log)


def fake_psycopg(rows, log, fail=False):
    mod = types.ModuleType("psycopg")

    def connect(dsn, **kw):
        if fail:
            raise RuntimeError("connection refused")
        return _FakeConn(rows, log)

    mod.connect = connect  # type: ignore[attr-defined]
    return mod


def security_rows_with(rows, fail=False, dsn="postgresql://fake"):
    log: list = []
    saved_mod, saved_env = sys.modules.get("psycopg"), os.environ.get("SWEEP_PG_DSN")
    try:
        sys.modules["psycopg"] = fake_psycopg(rows, log, fail)
        if dsn is None:
            os.environ.pop("SWEEP_PG_DSN", None)
        else:
            os.environ["SWEEP_PG_DSN"] = dsn
        cov._SEC_REBUILD_CACHE = None
        return cov.security_rebuild_rows(), log, cov._SEC_REBUILD_SOURCE
    finally:
        if saved_mod is not None:
            sys.modules["psycopg"] = saved_mod
        else:
            sys.modules.pop("psycopg", None)
        if saved_env is None:
            os.environ.pop("SWEEP_PG_DSN", None)
        else:
            os.environ["SWEEP_PG_DSN"] = saved_env
        cov._SEC_REBUILD_CACHE = None


def main() -> int:
    print(__doc__.strip().splitlines()[0])
    print()

    # ── 1. the snapshot side: unresolved self-built images + indexes ────
    with tempfile.TemporaryDirectory() as td:
        p = Path(td, "version-check-current.md")
        p.write_text(SNAPSHOT)
        orig = cov.VERSION_MD
        try:
            cov.VERSION_MD = p
            repo_index: dict = {}
            unresolved: list = []
            ns_index: dict = {}
            items = cov.parse_detail_images(repo_index, unresolved, ns_index)
        finally:
            cov.VERSION_MD = orig
    check("no actionable update in the fixture (the oracle answered nothing)", items == [], items)
    check("every SELF-BUILT image the oracle could not resolve is collected, deduped on "
          "(repo, tag): 2 of the 3 blocks",
          [(u["image_repo"].rsplit("/", 1)[-1], u["current"]) for u in unresolved]
          == [("widget-server", "sha-abc1234"), ("widget-frontend", "0.5.4-alpha")], unresolved)
    check("...a third-party unresolved image and a RESOLVED self-built image are not in it",
          not any("redis" in u["image_repo"] or "widget-resolved" in u["image_repo"]
                  for u in unresolved), unresolved)
    check("...each carries the app and namespace that mount it",
          all(u["component"] == "widget-app" and u["namespace"] == "tools" for u in unresolved),
          unresolved)
    check("ns_index maps the component to its namespace", ns_index == {"widget-app": "tools"},
          ns_index)
    check("repo_index still lists every image of the app (4)",
          len(repo_index.get("widget-app", ())) == 4, repo_index)

    # ── 2. the security side: title parsing + the DB read ───────────────
    parse = cov._parse_security_rebuild_title
    check("a title leading with a self-built image ref parses to (repo, tag)",
          parse(SEC_ROWS[0][2]) == ("ghcr.io/nachtschatt3n/widget-server", "sha-abc1234"))
    check("a digest suffix is dropped from the tag",
          parse(SEC_ROWS[3][2]) == ("ghcr.io/nachtschatt3n/widget-frontend", "0.5.4-alpha"))
    check("a third-party image ref parses to None", parse(SEC_ROWS[2][2]) is None)
    check("a title that does not LEAD with a backticked ref parses to None",
          parse(SEC_ROWS[4][2]) is None)

    rows, log, source = security_rows_with(SEC_ROWS)
    check("the DB read keeps the self-built rows only (3 of 5)",
          [r["finding_id"] for r in rows] == ["F-aaaa0001", "F-aaaa0002", "F-aaaa0004"], rows)
    sql = (log[0][0] if log else "")
    check("the query is scoped to OPEN, NOT-accepted security rows (an operator's per-image "
          "AR disposes of a row exactly as ar_accepts_item() does)",
          "section = 'security'" in sql and "resolved_at IS NULL" in sql
          and "severity IN ('critical', 'warning')" in sql, sql)
    check("...and the source line reports the feed and its size",
          source.startswith("sweep_findings") and "3" in source, source)
    rows, _log, source = security_rows_with(SEC_ROWS, dsn=None)
    check("no SWEEP_PG_DSN (the window agent) -> [] and the source SAYS it was not consulted",
          rows == [] and source.startswith("unavailable") and "NOT consulted" in source, source)
    rows, _log, source = security_rows_with(SEC_ROWS, fail=True)
    check("a failed query -> [] and the source names the failure",
          rows == [] and "query failed" in source, source)

    # ── 3. the merge into the lane ──────────────────────────────────────
    rows, _log, _src = security_rows_with(SEC_ROWS)
    existing = {"component": "widget-app", "namespace": "tools", "kind": "image",
                "current": "0.5.4-alpha", "target": "0.5.5", "type": "patch",
                "image_repo": "ghcr.io/nachtschatt3n/widget-frontend", "lane": "REBUILD",
                "reason": "self-built image — rebuild in its source repo"}
    lanes = {"AUTO": [], "PLAN": [], "REBUILD": [dict(existing)], "HELD": [], "CRACK": []}
    added = cov._rebuild_from_security(lanes, repo_index, rows, ns_index)
    check("one NEW entry per self-built image the security side named (widget-server)",
          len(added) == 1 and added[0]["image_repo"].endswith("/widget-server"), added)
    check("...two scanner rows on the same image collapse into ONE entry carrying both ids",
          added and added[0]["security_refs"] == ["F-aaaa0001", "F-aaaa0002"], added)
    check("...the entry names the app that mounts the image and its namespace, from the snapshot",
          added and added[0]["component"] == "widget-app" and added[0]["namespace"] == "tools",
          added)
    check("...and is a REBUILD-lane image row with a security_ref",
          added and added[0]["lane"] == "REBUILD" and added[0]["kind"] == "image"
          and added[0]["security_ref"] == "F-aaaa0001", added)
    check("an image ALREADY in REBUILD on the version signal is not duplicated — the id is "
          "attached to the existing entry",
          len(lanes["REBUILD"]) == 2 and lanes["REBUILD"][0].get("security_refs") == ["F-aaaa0004"],
          lanes["REBUILD"])

    # ── 4. the report: a qualified zero ─────────────────────────────────
    base = {"counts": {"AUTO": 0, "PLAN": 0, "REBUILD": 0, "HELD": 0, "CRACK": 0},
            "covered": True, "lanes": {"AUTO": [], "PLAN": [], "REBUILD": [], "HELD": [], "CRACK": []},
            "needs_plan": [], "cracks": [], "snapshot_age_hours": 1.0}
    out = cov.human({**base, "rebuild_universe": {
        "security_source": "unavailable — no SWEEP_PG_DSN, the security side's self-built rows were NOT consulted",
        "security_rows": None, "from_security": [], "unresolved_self_built": unresolved}})
    check("REBUILD 0 with unresolved self-built images and no security feed is printed as "
          "NOT 'none pending'", "NOT 'none pending'" in out and "widget-server" in out, out)
    out = cov.human({**base, "counts": {**base["counts"], "REBUILD": 1},
                     "lanes": {**base["lanes"], "REBUILD": [added[0]]},
                     "rebuild_universe": {"security_source": "sweep_findings (2 open self-built row(s))",
                                          "security_rows": 2, "from_security": [],
                                          "unresolved_self_built": []}})
    check("a fed, non-zero lane prints its security_ref on the row",
          "security_ref F-aaaa0001, F-aaaa0002" in out, out)
    check("...and a fed, non-zero lane carries no zero qualifier",
          "NOT 'none pending'" not in out, out)
    check("reconcile() actually merges the security rows and reports the universe",
          "_rebuild_from_security(" in inspect.getsource(cov.reconcile)
          and "rebuild_universe" in inspect.getsource(cov.reconcile))

    # ── 5. openclaw-sync: one issue per IMAGE ───────────────────────────
    payload = {"lanes": {"REBUILD": lanes["REBUILD"], "AUTO": [], "PLAN": [], "HELD": [], "CRACK": []}}
    issues, open_keys = ocs.rebuild_issues(payload)
    keys = [i["key"] for i in issues]
    check("two images of ONE component get two DISTINCT keys carrying the image basename",
          sorted(keys) == ["rebuild:widget-app/widget-frontend", "rebuild:widget-app/widget-server"]
          and open_keys == keys, keys)
    sec = next(i for i in issues if i.get("security_ref"))
    check("the security-driven issue names the finding, the image and the SLA, and no `?` target",
          "F-aaaa0001" in sec["title"] and "widget-server" in sec["title"]
          and f"SLA {ocs.REBUILD_SLA_DAYS}d" in sec["title"] and "?" not in sec["title"], sec)
    check("...and carries the reason as detail plus the image repo",
          sec.get("detail", "").startswith("security finding F-aaaa0001")
          and sec.get("image_repo", "").endswith("/widget-server"), sec)
    check("a row WITHOUT an image repo keeps the plain `rebuild:<component>` key (contract kept)",
          ocs.rebuild_issue_key({"component": "synthetic-tool"}) == "rebuild:synthetic-tool")
    with tempfile.TemporaryDirectory() as td:
        cj = Path(td, "cov.json")
        cj.write_text(json.dumps(payload))
        p = subprocess.run([sys.executable, str(OCS_SCRIPT), "--dry-run", "--coverage-json", str(cj)],
                           capture_output=True, text=True, timeout=60)
        n = count_matches(p.stdout, r'"key": "rebuild:')
        check("openclaw-sync --dry-run ingests exactly 2 rebuild issues (guarded count)",
              p.returncode == 0 and n == 2, (p.returncode, n, p.stderr[-200:]))

    # ── COMMISSIONING STRAWS: revert each fix, the assertions above must fail ──
    orig_re = cov._NOLATEST_LINE
    try:
        cov._NOLATEST_LINE = re.compile(r"(?!x)x")      # pre-fix: no such matcher existed
        with tempfile.TemporaryDirectory() as td:
            p = Path(td, "version-check-current.md")
            p.write_text(SNAPSHOT)
            orig = cov.VERSION_MD
            try:
                cov.VERSION_MD = p
                straw_unresolved: list = []
                cov.parse_detail_images({}, straw_unresolved, {})
            finally:
                cov.VERSION_MD = orig
        check("STRAW (snapshot): with the unresolved matcher reverted the list stays empty "
              "while the fixture holds 2 — the collection assertion fails against pre-fix code",
              straw_unresolved == [], straw_unresolved)
    finally:
        cov._NOLATEST_LINE = orig_re

    pre_lanes = {"AUTO": [], "PLAN": [], "REBUILD": [], "HELD": [], "CRACK": []}
    real_merge = cov._rebuild_from_security
    try:
        cov._rebuild_from_security = lambda lanes, repo_index, rows, ns_index=None: []
        cov._rebuild_from_security(pre_lanes, repo_index, rows, ns_index)
        check("STRAW (lane): with the merge reverted the lane reads 0 while 3 security rows "
              "exist — the non-empty-queue assertion fails against pre-fix code",
              len(pre_lanes["REBUILD"]) == 0 and len(rows) == 3, (pre_lanes, len(rows)))
    finally:
        cov._rebuild_from_security = real_merge

    real_key = ocs.rebuild_issue_key
    try:
        ocs.rebuild_issue_key = lambda row: f"rebuild:{row['component']}"   # pre-fix key
        straw_issues, _ = ocs.rebuild_issues(payload)
        straw_keys = [i["key"] for i in straw_issues]
        check("STRAW (openclaw-sync): with the component-only key reverted, two images of one "
              "component COLLIDE on one key — the distinct-keys assertion fails against pre-fix code",
              len(set(straw_keys)) < len(straw_keys), straw_keys)
    finally:
        ocs.rebuild_issue_key = real_key

    print()
    print("FAILED: " + ", ".join(FAILURES) if FAILURES else "all tests passed")
    return 1 if FAILURES else 0


def test_pytest_entry():
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())
