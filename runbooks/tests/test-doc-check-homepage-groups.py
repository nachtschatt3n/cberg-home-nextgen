#!/usr/bin/env python3
"""Regression tests for doc-check.py's Homepage-group source (2026-09-20).

s5_integration_docs() used to read the group names out of the `config.services`
block of the homepage HelmRelease. That block moved into a SOPS-encrypted
Secret (security_ref: F-93102d77) because, in a public repo, it paired private
LAN addresses with each device's role and model.

The failure mode this pins is NOT the move — it is what a stale parser does
afterwards: `re.search('      services:', ...)` would find nothing, take the
else-branch, and the Homepage-group comparison would be skipped on every cycle
while the section still printed green. Same shape as the section-names bug in
test-doc-check-section-names.py, and the reason this repo insists a check that
cannot see must say so (docs/sops/audit-script-correctness.md).

Directions pinned here:
  1. The real helmrelease yields the real layout groups (measured from the
     tracked file, not hardcoded — a group added tomorrow must not fail this).
  2. A two-letter group ("AI") survives. The old code filtered `len > 2`, which
     would drop it silently — harmless while the source was `services:` (no AI
     group there), a false negative now that the source is `layout:`.
  3. A quoted multi-word group ("Network Services") keeps its space.
  4. Properties, comments and the trailing dedented comment block are not
     mistaken for groups.
  5. No layout block => [] AND the caller degrades — never a silent pass.
  6. The extractor does NOT depend on `config.services` existing. This is the
     assertion that would have caught the stale parser.
  7. Every extracted group is actually documented in docs/integration.md, which
     is the check's real job.

Run: python3 runbooks/tests/test-doc-check-homepage-groups.py
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

HR = ROOT / "kubernetes/apps/default/homepage/app/helmrelease.yaml"

failures: list[str] = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}: {name}" + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(name)


groups = doc_check.homepage_layout_groups(HR.read_text())

# 1. The real file parses, and into a plausible number of groups.
check("real helmrelease yields layout groups", len(groups) >= 4,
      f"got {len(groups)}: {groups}")

# 2+3. The two cases the old length filter / quote handling would have broken.
check("two-letter group survives the length bound", "AI" in groups, f"got {groups}")
check("quoted multi-word group keeps its space", "Network Services" in groups,
      f"got {groups}")

# 4. Nothing that is not a group name leaked in.
bad = [g for g in groups if g.startswith("#") or ":" in g or g != g.strip()
       or g in {"style", "columns", "icon"}]
check("no properties/comments parsed as groups", not bad, f"leaked: {bad}")
check("groups are unique", len(groups) == len(set(groups)),
      f"duplicates in {groups}")

# 5. A layout-less file degrades rather than passing quietly.
check("no layout block => empty list",
      doc_check.homepage_layout_groups("spec:\n  values:\n    config: {}\n") == [],
      "expected []")
src = SRC.read_text()
degrade_m = re.search(
    r'hr_groups = homepage_layout_groups\(hr_content\)\s*\n\s*if not hr_groups:'
    r'(?:\s*\n\s*#.*)*\s*\n\s*DEGRADED\.record\(', src)
check("caller records DEGRADED on an empty parse", bool(degrade_m),
      "s5_integration_docs must not treat an unparseable layout as 'nothing to check'")

# 6. THE REGRESSION: extraction must not depend on `config.services`, which is
#    encrypted and therefore absent from the HelmRelease.
no_services = """\
spec:
  values:
    config:
      settingsString: |
        layout:
          AI:
            style: row
          "Home Automation":
            columns: 3
            # a comment inside the block
        # title: Homepage
        # layout:
        #   My First Group:
"""
check("works with no config.services block present",
      doc_check.homepage_layout_groups(no_services) == ["AI", "Home Automation"],
      f'got {doc_check.homepage_layout_groups(no_services)}')
check("helmrelease really has no plaintext services block",
      not re.search(r'^      services:', HR.read_text(), re.MULTILINE),
      "config.services is back in the public file — it belongs in secret.sops.yaml")

# 7. The check's actual job, against the real docs.
doc = (ROOT / "docs/integration.md").read_text()
undocumented = [g for g in groups if g not in doc]
check("every layout group is documented in docs/integration.md", not undocumented,
      f"missing: {undocumented}")

print()
if failures:
    print(f"  {len(failures)} FAILED: {', '.join(failures)}")
    sys.exit(1)
print("  all homepage-group checks passed")
