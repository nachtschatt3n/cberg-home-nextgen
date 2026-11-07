#!/usr/bin/env python3
"""Regression (F-c1e4d0aa): G3s must see Liquibase-style XML changelogs.
traccar 6.17.0 added `schema/changelog-6.17.0.xml` (new table) and was rated
safe because _STRUCTURAL_PATH_RE only knew migrations/ style directories.

Run:  python3 runbooks/tests/test-structural-xml-changelog.py
"""
import importlib.util, os, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
os.environ.setdefault("_MISE_ACTIVATED", "1")
sys.path.insert(0, str(REPO / "runbooks"))
spec = importlib.util.spec_from_file_location("au_xml", REPO / "runbooks/auto-update.py")
au = importlib.util.module_from_spec(spec); spec.loader.exec_module(au)  # type: ignore
fails = []
def check(n, ok):
    print(f"  {'PASS' if ok else 'FAIL'}  {n}")
    if not ok: fails.append(n)
R = au._STRUCTURAL_PATH_RE
for p in ["schema/changelog-6.17.0.xml", "schema/changelog-master.xml", "src/main/resources/db/changelog-1.2.sql",
          "db/changelog.yaml", "liquibase/x.xml", "app/migrations/0001.py"]:
    check(f"matches {p}", bool(R.search(p)))
for p in ["CHANGELOG.md", "docs/changelog-2026.md", "changelog.txt", "src/changelog-view.tsx", "README.md"]:
    check(f"ignores {p}", not R.search(p))
sig = au._scan_structural_files([{"filename": "schema/changelog-6.17.0.xml", "status": "added", "patch": ""}])
check("added XML changelog yields a hold signal", sig == ["new migration file schema/changelog-6.17.0.xml"])
sig = au._scan_structural_files([{"filename": "schema/changelog-6.17.0.xml", "status": "modified", "patch": ""}])
check("a modified (not added) changelog does not signal", sig == [])
sys.exit(1 if fails else 0)
