#!/usr/bin/env python3
"""
Regression tests for doc-check.py's SECTION_NAMES / report writer (2026-08-28).

Sections 9 (storage-safety table) and 10 (control ledger) were each added
without extending SECTION_NAMES. write_report() then raised IndexError AFTER
all checks had already run: no report written, no findings persisted, and the
doc section recorded INCOMPLETE on every cycle — the auto-close veto fired
forever. All ten section checks printed green while the section as a whole was
dead.

Two guards:

  1. len(SECTION_NAMES) must equal the number of `results.append(sN_...())`
     calls in _main_impl — adding a section without naming it fails loudly
     here, in a test, not at 04:00 in the sweep.

  2. section_name(i) must be total: an out-of-range index degrades to a
     visible placeholder instead of killing the whole report.

Run: python3 runbooks/tests/test-doc-check-section-names.py
"""
import importlib.util
import os
import pathlib
import re
import sys

os.environ["_MISE_ACTIVATED"] = "1"
ROOT = pathlib.Path(__file__).resolve().parents[2]
os.chdir(ROOT)

SRC = ROOT / "runbooks" / "doc-check.py"

spec = importlib.util.spec_from_file_location("doc_check", SRC)
doc_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(doc_check)

failures = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}: {name}" + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(name)


src = SRC.read_text()

# 1. Every appended section has a name.
appends = re.findall(r"results\.append\(s\d+_\w+\(\)\)", src)
check(
    "SECTION_NAMES covers every appended section",
    len(doc_check.SECTION_NAMES) == len(appends),
    f"{len(doc_check.SECTION_NAMES)} names vs {len(appends)} sections appended in _main_impl",
)
check("at least the 10 known sections are appended", len(appends) >= 10,
      f"only {len(appends)} results.append(sN_...()) calls found")

# 2. section_name is total — never raises, in range and out.
try:
    for i in range(1, len(doc_check.SECTION_NAMES) + 1):
        assert doc_check.section_name(i) == doc_check.SECTION_NAMES[i - 1]
    over = doc_check.section_name(len(doc_check.SECTION_NAMES) + 5)
    check("section_name in-range matches list, out-of-range degrades visibly",
          "missing" in over)
except Exception as e:  # noqa: BLE001
    check("section_name never raises", False, repr(e))

# 3. write_report itself no longer indexes SECTION_NAMES directly (the crash site).
wr = src[src.index("def write_report"):src.index("def ", src.index("def write_report") + 10)]
check("write_report has no direct SECTION_NAMES[...] indexing",
      "SECTION_NAMES[" not in wr)

if failures:
    print(f"\n{len(failures)} FAILURE(S): {failures}")
    sys.exit(1)
print("\nall section-name guards pass")
