#!/usr/bin/env python3
"""
Regression test for doc-check.py's per-namespace count-table check on
docs/infrastructure.md (F-63b578f5).

The defect: section 3 compared per-namespace rows with the regex
`^\\|\\s*ns\\s*\\|\\s*(\\d+)\\s*\\|`, which hard-codes the count into column 1. That
fits the applications.md Summary (`| ns | N |`) and can NEVER match the
infrastructure.md Namespaces table (`| ns | Purpose | N |`), so that table was
validated by nothing — doc-check's only statement about the file was "exists
(262 lines)" — while 7 of 18 rows were wrong.

Contract, asserted through the module's own functions:
  1. COMMISSIONING STRAW: the pre-fix regex matches nothing on a 3-column
     table (and does match the 2-column one — the old check only ever
     covered applications.md).
  2. _ns_count_cell reads the named column of either shape; a missing row or
     a non-integer cell is None, never a silent 0.
  3. _namespace_table_mismatches reports wrong digits with both numbers and
     missing rows as mismatches, and returns None (not []) when no row at all
     could be parsed — an empty population is a coverage gap.
  4. Real reader: every namespace row in docs/infrastructure.md agrees with
     the applications.md Summary row (the two tables state the same number),
     and a single mutated digit is caught.

Run: python3 runbooks/tests/test-doc-check-namespace-table.py
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path

os.environ["_MISE_ACTIVATED"] = "1"
ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
_spec = importlib.util.spec_from_file_location("dc", ROOT / "runbooks" / "doc-check.py")
dc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dc)

PASS = FAIL = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}" + (f"\n        {detail}" if detail else ""))


TABLE3 = """\
## Namespaces

| Namespace | Purpose | App Count |
|-----------|---------|-----------|
| ai | AI/ML services | 10 |
| media | Media servers | 5 |
| backup | External backup integrations | 1 |
"""
TABLE2 = """\
| Namespace | App Count |
|-----------|-----------|
| ai | 10 |
| media | 5 |
"""
COUNTABLE = {"ai": ["a"] * 10, "media": ["m"] * 5, "backup": ["b"] * 3}


def old_regex(ns, content):
    return re.search(rf"^\|\s*{re.escape(ns)}\s*\|\s*(\d+)\s*\|", content, re.M)


# 1 — STRAW
check("STRAW: the pre-fix 2-column regex never matches a 3-column row",
      old_regex("ai", TABLE3) is None)
check("the same regex does match the 2-column Summary (old check covered only applications.md)",
      old_regex("ai", TABLE2) is not None and old_regex("ai", TABLE2).group(1) == "10")

# 2 — the parser
check("_ns_count_cell reads column 2 of the 3-column table", dc._ns_count_cell(TABLE3, "ai", 2) == 10)
check("_ns_count_cell reads column 1 of the 2-column table", dc._ns_count_cell(TABLE2, "ai", 1) == 10)
check("missing row -> None", dc._ns_count_cell(TABLE3, "office", 2) is None)
check("non-integer cell -> None, not a silent 0", dc._ns_count_cell("| ai | x | ~10 |\n", "ai", 2) is None)
check("too few columns -> None", dc._ns_count_cell(TABLE2, "ai", 2) is None)

# 3 — mismatches
mm = dc._namespace_table_mismatches(TABLE3, COUNTABLE, 2)
check("a wrong digit is reported with both numbers", mm == ["backup: table says 1, actual 3"], f"{mm}")
mm = dc._namespace_table_mismatches(TABLE3, {**COUNTABLE, "office": ["o", "o"]}, 2)
check("a namespace with no row is a mismatch, not a skip",
      "office: no parseable row (actual 2)" in mm, f"{mm}")
check("empty population -> None, never []",
      dc._namespace_table_mismatches("no table here\n", COUNTABLE, 2) is None)
check("2-column Summary parses with col=1 and agrees",
      dc._namespace_table_mismatches(TABLE2, {"ai": ["a"] * 10, "media": ["m"] * 5}, 1) == [])

# 4 — real reader: infrastructure.md rows must equal applications.md rows
infra = (ROOT / "docs" / "infrastructure.md").read_text()
apps_doc = (ROOT / "docs" / "applications.md").read_text()
namespaces = sorted(dc.find_helmrelease_apps().keys())
check("real repo has a namespace inventory to compare", len(namespaces) >= 10, f"{namespaces}")
stated_apps = {ns: dc._ns_count_cell(apps_doc, ns, 1) for ns in namespaces}
stated_infra = {ns: dc._ns_count_cell(infra, ns, 2) for ns in namespaces}
check("applications.md Summary parses for every namespace",
      all(v is not None for v in stated_apps.values()), f"{stated_apps}")
check("infrastructure.md Namespaces parses for every namespace",
      all(v is not None for v in stated_infra.values()), f"{stated_infra}")
disagree = {ns: (stated_infra[ns], stated_apps[ns]) for ns in namespaces
            if stated_infra[ns] != stated_apps[ns]}
check("infrastructure.md agrees with applications.md on every namespace (F-63b578f5: was 7 rows off)",
      not disagree, f"infra/apps: {disagree}")
# the assertion can fail: mutate one infrastructure.md digit
target = namespaces[0]
mutated = re.sub(rf"^(\|\s*{re.escape(target)}\s*\|[^|]*\|\s*)(\d+)(\s*\|)",
                 lambda m: f"{m.group(1)}{int(m.group(2)) + 1}{m.group(3)}", infra, count=1, flags=re.M)
countable_from_doc = {ns: ["x"] * stated_apps[ns] for ns in namespaces}
mm = dc._namespace_table_mismatches(mutated, countable_from_doc, 2)
check("a single mutated infrastructure.md digit is caught by the 3-column check",
      mm == [f"{target}: table says {stated_apps[target] + 1}, actual {stated_apps[target]}"], f"{mm}")

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
