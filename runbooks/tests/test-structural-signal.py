#!/usr/bin/env python3
"""Regression test: G3 has a STRUCTURAL companion that reads the DIFF, not
the prose, on BOTH lanes (F-ea1000ff).

G3 reads release-note PROSE, so it holds when upstream writes "breaking" and
passes when upstream does not. In the measured case (2026-09-20) a held bump's
stated reason was a frontend-dependency note that could not touch the data
path, while the SAME diff carried a new database migration and a bumped
search-index schema constant — the hold was correct by accident, and the
no-PR direct-bump half would have applied it unattended had the prose been one
adjective quieter. `structural_signal()` in auto-update.py now reads the
compare API for (a) files ADDED under a migrations directory and (b) an ADDED
line assigning a SCHEMA_VERSION-style constant; classify() holds on it (gate
"structural"), and coverage.py's direct-bump exit mirrors it through
`_direct_bump_structural_gate()`.

Hermetic: auto-update.py's ONE GitHub seam (`_gh_api_json`) is replaced by a
route table, and the checker is a stub. Every assertion calls the real
functions; nothing is re-parsed from source except the two wiring pins.

Run:  python3 runbooks/tests/test-structural-signal.py
"""
from __future__ import annotations

import base64
import importlib.util
import inspect
import os
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
os.environ.setdefault("_MISE_ACTIVATED", "1")
sys.path.insert(0, str(_REPO / "runbooks"))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, _REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore
    return mod


au = _load("cberg_auto_update_under_test", "runbooks/auto-update.py")
cov = _load("cberg_coverage_under_test", "runbooks/coverage.py")

FAILURES: list[str] = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {str(detail)[:300]}"))
    if not ok:
        FAILURES.append(name)


def count_matches(population: str, pattern: str) -> int:
    """Guarded counter. An empty population or one carrying an error marker
    aborts the run instead of returning a silent zero — a zero measured on a
    crash is not a measurement."""
    if not population or not population.strip():
        raise SystemExit(f"count_matches: EMPTY population for {pattern!r}")
    for marker in ("usage:", "Traceback", "error"):
        if marker in population:
            raise SystemExit(f"count_matches: population carries {marker!r}: "
                             f"{population[:200]!r}")
    return len(re.findall(pattern, population))


# ── fakes ───────────────────────────────────────────────────────────────────
class FakeGitHub:
    """Route table standing in for `_gh_api_json`: exact path -> payload
    (or a callable). Unknown paths are a definitive 404."""

    def __init__(self, routes: dict):
        self.routes = routes
        self.calls: list[str] = []

    def __call__(self, path, timeout=15):
        self.calls.append(path)
        if path in self.routes:
            v = self.routes[path]
            return v() if callable(v) else v
        return au._NOT_FOUND


class FakeChecker:
    def get_release_notes_project(self, dep):
        return ("o", "r") if dep == "o/r" else None

    def get_repo_info_from_image(self, dep):
        return self.get_release_notes_project(dep)

    def get_chart_repo_info(self, *a, **k):
        return None

    def fetch_release_notes(self, owner, repo, tag):
        return {"body": "routine release, nothing to see", "prerelease": False,
                "published_at": "2026-01-01T00:00:00Z"}

    def detect_breaking_changes(self, body, utype):
        return []


CHECKER = FakeChecker()
RELEASES = "repos/o/r/releases?per_page=100"
COMPARE_V = "repos/o/r/compare/v1.0.0...v1.1.0"
COMPARE_BARE = "repos/o/r/compare/1.0.0...1.1.0"
RELEASE_LIST = [{"tag_name": "v1.1.0", "prerelease": False},
                {"tag_name": "v1.0.0", "prerelease": False}]


def _file(name, status="modified", patch=""):
    return {"filename": name, "status": status, "patch": patch}


def _b64(text):
    return {"encoding": "base64", "content": base64.b64encode(text.encode()).decode()}


def install(routes):
    gh = FakeGitHub(routes)
    au._gh_api_json = gh
    au._STRUCTURAL_CACHE.clear()
    au._RELEASES_CACHE.clear()
    cov._STRUCT_CACHE.clear()
    return gh


def signal(cur="1.0.0", new="1.1.0"):
    return au.structural_signal(CHECKER, "o/r", new, cur_tag=cur)


# ── the direct-bump lane, with every OTHER upstream seam stubbed ─────────────
ITEM = {"component": "widget", "namespace": "t", "kind": "image", "current": "1.0.0",
        "target": "1.1.0", "type": "minor", "image_repo": "o/r", "cell": ""}
POLICY = {"deny": [], "age_waive": []}


def lane_with(g3_note="clean (release notes checked)"):
    saved = (cov._direct_bump_breaking_gate, cov._g3_range_gate, cov.direct_bump_age_gate,
             cov.channel_hold, cov.prerelease_target_hold, cov._auto_update_module,
             cov._load_checker)
    try:
        cov._direct_bump_breaking_gate = lambda item: (False, g3_note)
        cov._g3_range_gate = lambda item: ("n/a", "")
        cov.direct_bump_age_gate = lambda *a, **k: None
        cov.channel_hold = lambda *a, **k: None
        cov.prerelease_target_hold = lambda item: None
        cov._auto_update_module = lambda: au
        cov._load_checker = lambda: CHECKER
        cov._STRUCT_CACHE.clear()
        return cov.assign_lane(dict(ITEM), POLICY, {}, [])
    finally:
        (cov._direct_bump_breaking_gate, cov._g3_range_gate, cov.direct_bump_age_gate,
         cov.channel_hold, cov.prerelease_target_hold, cov._auto_update_module,
         cov._load_checker) = saved


# ── the PR lane, with G5/G4/G3-prose stubbed ────────────────────────────────
PR = {"number": 1, "title": "feat(container): update o/r ( 1.0.0 → 1.1.0 )",
      "labels": [{"name": "type/minor"}], "isDraft": False, "url": ""}


def classify_pr():
    saved = (au.age_gate, au.ci_state, au.breaking_signal)
    try:
        au.age_gate = lambda *a, **k: None
        au.ci_state = lambda n: (True, "mergeable + all checks green")
        au.breaking_signal = lambda *a, **k: ([], True)
        au._STRUCTURAL_CACHE.clear()
        return au.classify(dict(PR), POLICY, CHECKER)
    finally:
        au.age_gate, au.ci_state, au.breaking_signal = saved


def main() -> int:
    print(__doc__.strip().splitlines()[0])
    print()

    # ── 1. the signals themselves ───────────────────────────────────────
    gh = install({RELEASES: RELEASE_LIST,
                  COMPARE_V: {"total_commits": 3, "files": [
                      _file("src/app/models.py", patch="+x = 1"),
                      _file("src/app/migrations/0026_add_column.py", status="added",
                            patch="+class Migration:\n+    pass")]}})
    sigs, resolved, note = signal()
    check("a file ADDED under migrations/ is a structural signal",
          sigs == ["new migration file src/app/migrations/0026_add_column.py"], (sigs, note))
    check("...and the scan is RESOLVED (a complete read)", resolved is True, note)
    check("the compare is read on the REAL git tags from the release list, not the docker "
          "spelling (v1.0.0...v1.1.0 first, bare pair never tried)",
          count_matches("\n".join(gh.calls), r"compare/v1\.0\.0\.\.\.v1\.1\.0$") == 1
          and count_matches("\n".join(gh.calls), r"compare/1\.0\.0\.\.\.1\.1\.0$") == 0,
          gh.calls)

    install({RELEASES: RELEASE_LIST,
             COMPARE_V: {"total_commits": 1, "files": [
                 _file("src/search/_schema.py",
                       patch="@@ -1 +1 @@\n-SCHEMA_VERSION: Final[int] = 1\n+SCHEMA_VERSION: Final[int] = 2")]}})
    sigs, resolved, note = signal()
    check("an ADDED line assigning a SCHEMA_VERSION-style constant is a structural signal",
          len(sigs) == 1 and sigs[0].startswith("src/search/_schema.py: SCHEMA_VERSION"), sigs)

    install({RELEASES: RELEASE_LIST,
             COMPARE_V: {"total_commits": 2, "files": [
                 _file("src/app/views.py", patch="+if SCHEMA_VERSION == 2:\n+    pass"),
                 _file("docs/schema.md", patch="+SCHEMA_VERSION = 9"),
                 _file("tests/test_schema.py", patch="+DB_VERSION = 3"),
                 _file("src/app/migrations/0001_initial.py", patch="+# touched, not added")]}})
    sigs, resolved, note = signal()
    check("a comparison, a docs file, a test file and a MODIFIED old migration are not signals",
          sigs == [] and resolved is True, (sigs, note))

    # ── 2. truncation: the measured diff was exactly the 300-file cap ───
    big = [_file(f"src-ui/component_{i:03d}.ts", patch="+// ui") for i in range(300)]
    install({RELEASES: RELEASE_LIST,
             COMPARE_V: {"total_commits": 145, "files": big},
             "repos/o/r/git/trees/v1.0.0?recursive=1": {"truncated": False, "tree": [
                 {"path": "src/a.py", "type": "blob", "sha": "1"},
                 {"path": "src/search/schema.py", "type": "blob", "sha": "s1"}]},
             "repos/o/r/git/trees/v1.1.0?recursive=1": {"truncated": False, "tree": [
                 {"path": "src/a.py", "type": "blob", "sha": "1"},
                 {"path": "src/search/schema.py", "type": "blob", "sha": "s2"},
                 {"path": "db/migrate/20260101_add.rb", "type": "blob", "sha": "m"}]},
             "repos/o/r/contents/src/search/schema.py?ref=v1.1.0": _b64("SCHEMA_VERSION = 2\n"),
             "repos/o/r/contents/src/search/schema.py?ref=v1.0.0": _b64("SCHEMA_VERSION = 1\n")})
    sigs, resolved, note = signal()
    check("a compare TRUNCATED at 300 files falls back to a tree diff: the migration "
          "beyond the cap is found", "new migration file db/migrate/20260101_add.rb" in sigs,
          (sigs, note))
    check("...and the schema constant beyond the cap is found by reading the schema-named file",
          any(s.startswith("src/search/schema.py: SCHEMA_VERSION = 2") for s in sigs), sigs)
    check("...and with every candidate read the scan is RESOLVED", resolved is True, note)

    install({RELEASES: RELEASE_LIST,
             COMPARE_V: {"total_commits": 145, "files": big}})
    sigs, resolved, note = signal()
    check("truncated + unreadable trees: NOT resolved, note says INCOMPLETE (never 'clean')",
          sigs == [] and resolved is False and "INCOMPLETE" in note, (sigs, resolved, note))

    # ── 3. unknowable shapes are reported, never read as clean ──────────
    gh = install({RELEASES: RELEASE_LIST})
    sigs, resolved, note = signal()
    check("no compare ref resolves -> unresolved, with the spellings tried",
          sigs == [] and resolved is False and "compare refs unresolved" in note, note)
    gh = install({})
    sigs, resolved, note = signal()
    check("a MISSING source repository is settled in one probe, no compare attempted",
          resolved is False and "not found on GitHub" in note
          and count_matches("\n".join(gh.calls), r"compare/") == 0, (note, gh.calls))
    sigs, resolved, note = signal(cur="?")
    check("an unknown current version (bare PR title) cannot be compared -> unresolved",
          resolved is False and "current version unknown" in note, note)

    # ── 4. the PR lane holds on it ──────────────────────────────────────
    install({RELEASES: RELEASE_LIST,
             COMPARE_V: {"total_commits": 3, "files": [
                 _file("src/app/migrations/0026_add_column.py", status="added", patch="+m")]}})
    v = classify_pr()
    check("classify(): a migration in the diff HOLDS the PR on gate 'structural'",
          v["verdict"] == "hold" and v["gate"] == "structural"
          and "0026_add_column" in v["reason"], v)
    install({RELEASES: RELEASE_LIST,
             COMPARE_V: {"total_commits": 3, "files": [_file("README.md", patch="+hi")]}})
    v = classify_pr()
    check("classify(): a clean diff stays 'safe' and records structural_checked=True",
          v["verdict"] == "safe" and v.get("structural_checked") is True, v)
    install({RELEASES: RELEASE_LIST})
    v = classify_pr()
    check("classify(): an UNREADABLE diff stays 'safe' (G3 asymmetry) but SAYS so in the reason",
          v["verdict"] == "safe" and v.get("structural_checked") is False
          and "diff not inspected" in v["reason"], v)

    # ── 5. the direct-bump lane mirrors it ──────────────────────────────
    install({RELEASES: RELEASE_LIST,
             COMPARE_V: {"total_commits": 3, "files": [
                 _file("src/app/migrations/0026_add_column.py", status="added", patch="+m")]}})
    lane = lane_with()
    check("assign_lane(): a migration in the diff routes a 'safe minor' to PLAN",
          lane[0] == "PLAN" and "G3 structural signal" in lane[1], lane)
    install({RELEASES: RELEASE_LIST,
             COMPARE_V: {"total_commits": 3, "files": [_file("README.md", patch="+hi")]}})
    lane = lane_with()
    check("assign_lane(): a clean diff still reaches AUTO", lane[0] == "AUTO", lane)
    install({RELEASES: RELEASE_LIST})
    lane = lane_with()
    check("assign_lane(): an unreadable diff reaches AUTO annotated 'G3-structural unverified'",
          lane[0] == "AUTO" and "G3-structural unverified" in lane[1], lane)
    gh = install({RELEASES: RELEASE_LIST,
                  COMPARE_V: {"total_commits": 3, "files": [
                      _file("src/app/migrations/0026_add_column.py", status="added", patch="+m")]}})
    lane = lane_with(g3_note="unverified (RuntimeError)")
    check("assign_lane(): when the notes resolver itself failed the structural gate is NOT "
          "consulted (no second network reach; the G3 note already annotates)",
          lane[0] == "AUTO" and not gh.calls, (lane, gh.calls))

    # ── 6. wiring pins ──────────────────────────────────────────────────
    check("classify() actually calls structural_signal()",
          "structural_signal(" in inspect.getsource(au.classify))
    check("assign_lane() actually calls _direct_bump_structural_gate()",
          "_direct_bump_structural_gate(" in inspect.getsource(cov.assign_lane))

    # ── COMMISSIONING STRAWS: revert the fix, the assertions above must fail ──
    install({RELEASES: RELEASE_LIST,
             COMPARE_V: {"total_commits": 3, "files": [
                 _file("src/app/migrations/0026_add_column.py", status="added", patch="+m")]}})
    real_ss = au.structural_signal
    try:
        au.structural_signal = lambda *a, **k: ([], False, "straw: pre-fix, no structural gate")
        v = classify_pr()
        check("STRAW (PR lane): with structural_signal reverted to 'no information' the "
              "migration PR is rated SAFE — the hold assertion fails against pre-fix code",
              v["verdict"] == "safe", v)
    finally:
        au.structural_signal = real_ss
    real_gate = cov._direct_bump_structural_gate
    try:
        cov._direct_bump_structural_gate = lambda item: (False, "unverified (straw)")
        lane = lane_with()
        check("STRAW (direct-bump lane): with the gate reverted the same item reaches AUTO — "
              "the PLAN assertion fails against pre-fix code", lane[0] == "AUTO", lane)
    finally:
        cov._direct_bump_structural_gate = real_gate

    print()
    print("FAILED: " + ", ".join(FAILURES) if FAILURES else "all tests passed")
    return 1 if FAILURES else 0


def test_pytest_entry():
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())
