#!/usr/bin/env python3
"""Regression: backup-coverage-check must see, and must not read silence as health.

Guards the pure parts of runbooks/backup-coverage-check.py (no cluster needed):
  * the path matcher: inside an include is "full", a parent of an include is
    "partial" (curated sub-folders of a bulk share), anything else is "no"; a
    synthetic bogus path must never match (the check's own negative control);
  * include-list parsing refuses a mount number with no source definition
    (NotMeasured) instead of silently dropping the line;
  * `..` in a source definition is refused.

Run: python3 runbooks/tests/test-backup-coverage-check.py
"""
import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("bcc", ROOT / "runbooks" / "backup-coverage-check.py")
bcc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bcc)

fails = 0


def check(name, ok):
    global fails
    print(("PASS " if ok else "FAIL ") + name)
    fails += 0 if ok else 1


inc = {"share-a/docs", "share-b"}
check("path inside include is full", bcc.covered("share-a/docs/x/y", inc) == "full")
check("exact include is full", bcc.covered("share-b", inc) == "full")
check("parent of an include is partial", bcc.covered("share-a", inc) == "partial")
check("unrelated path is no", bcc.covered("share-c/foo", inc) == "no")
check("sibling with shared prefix is no", bcc.covered("share-a/docs2", inc) == "no")
check("control path never matches", bcc.covered("zz-control-nonexistent-share/zz", inc) == "no")

src = {"FILES_CORE": "/src/1/a\n/src/2/b\n", "FILES_APPS": "", "OFFSITE_SRC_1": "Share-X", "OFFSITE_SRC_2": "share-y/sub"}
check("include list resolves mounts and lowercases",
      bcc.include_paths(src) == {"share-x/a", "share-y/sub/b"})
try:
    bcc.include_paths({"FILES_CORE": "/src/9/z", "FILES_APPS": ""})
    check("unknown mount number is NotMeasured", False)
except bcc.NotMeasured:
    check("unknown mount number is NotMeasured", True)
try:
    bcc.norm("a/../b")
    check("dotdot is refused", False)
except bcc.NotMeasured:
    check("dotdot is refused", True)
sys.exit(1 if fails else 0)
