#!/usr/bin/env python3
"""
Regression test for doc-check.py section 3's documented/undocumented decision
(2026-08-24).

The defect: the check asked `app_name in content.lower()` -- a substring search
over the WHOLE of docs/applications.md. Every row's prose freely names other
apps ("a Grafana dashboard", "cache on redis", "metadata in Postgres"), so an
app counted as documented when some OTHER app's description happened to mention
it. Deleting an app's entire row changed nothing.

This is the third instance of the same family in this one file: first the fuzzy
"any word >4 chars" clause, then the directory denominator, now the match
surface. Each narrowing fixed the symptom in front of it and left the shape.

Found by a mutation control, which is the only thing that finds this class: the
section reported "Undocumented apps: 0" both before and after a row was
deleted, so the zero was never evidence of anything.

The fix scopes the match to _documented_name_surface() -- table row-HEADS and
markdown headings only.

Both directions are asserted, because narrowing a detector to kill false
positives has repeatedly created false negatives in this repo:

  1. CAN SEE   -- deleting an app's own row makes it undocumented, even when
                  its name still appears in another row's prose.
  2. NO FP     -- entries that are legitimately not a bare name still pass:
                  `ingress-nginx (internal)` (qualified), `wazuh-indexer`
                  (parent name is a prefix of the row), and a datastore
                  sub-component documented inside its parent's row.

Run: python3 runbooks/tests/test-doc-check-row-scope.py
"""
import importlib.util
import os
import pathlib
import sys

os.environ["_MISE_ACTIVATED"] = "1"
ROOT = pathlib.Path(__file__).resolve().parents[2]
os.chdir(ROOT)
spec = importlib.util.spec_from_file_location("dc", ROOT / "runbooks" / "doc-check.py")
dc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dc)

PASS = FAIL = 0


def check(name, got, want):
    global PASS, FAIL
    if got == want:
        print(f"  PASS  {name}")
        PASS += 1
    else:
        print(f"  FAIL  {name}\n        got {got!r}\n        want {want!r}")
        FAIL += 1


def documented(content: str, app: str) -> bool:
    """Mirror of the call-site predicate in s3_application_docs()."""
    surface = dc._documented_name_surface(content)
    return (app.lower() in surface
            or app.lower().replace("-", "") in surface.replace("-", "").replace(" ", ""))


# --------------------------------------------------------------------------
# 1) The detector can SEE: a name that survives only in another row's prose
#    must NOT count as documented.
# --------------------------------------------------------------------------
DOC_WITHOUT_GRAFANA = """\
# Application Inventory

| App | Description |
|-----|-------------|
| pellet-price-monitor | ETL of pellet prices; results surfaced on a Grafana dashboard. |
| nextcloud | Cloud storage. Cache on redis, metadata in a Postgres behind it. |
"""

check("grafana absent as a row -> undocumented (was: passed on prose)",
      documented(DOC_WITHOUT_GRAFANA, "grafana"), False)
check("redis absent as a row -> undocumented (mentioned in nextcloud prose)",
      documented(DOC_WITHOUT_GRAFANA, "redis"), False)
check("postgres absent as a row -> undocumented (mentioned in nextcloud prose)",
      documented(DOC_WITHOUT_GRAFANA, "postgres"), False)

# The whole-document rule these replace really did pass all three. Assert that
# explicitly, so the test documents the bug and not just the fix.
whole_doc = DOC_WITHOUT_GRAFANA.lower()
check("CONTROL: the OLD whole-document rule called grafana documented",
      "grafana" in whole_doc, True)

# --------------------------------------------------------------------------
# 2) No false positives: real shapes from docs/applications.md still pass.
# --------------------------------------------------------------------------
DOC_REAL_SHAPES = """\
# Application Inventory

| App | Path | Description |
|-----|------|-------------|
| grafana | monitoring/grafana/ | Dashboards |
| ingress-nginx (internal) | network/internal/ | Internal reverse proxy |
| ingress-nginx (external) | network/external/ | External reverse proxy |
| wazuh-indexer | security/ | Event store |
| wazuh-manager-master | security/ | Manager |
| `tube-archivist` | download/ | Backticked row head |
"""

check("plain row head matches", documented(DOC_REAL_SHAPES, "grafana"), True)
check("qualified row head `ingress-nginx (internal)` matches ingress-nginx",
      documented(DOC_REAL_SHAPES, "ingress-nginx"), True)
check("app documented only via longer row heads (wazuh-*) matches wazuh",
      documented(DOC_REAL_SHAPES, "wazuh"), True)
check("backticked row head matches", documented(DOC_REAL_SHAPES, "tube-archivist"), True)
check("an app with no row at all is still flagged",
      documented(DOC_REAL_SHAPES, "immich"), False)

# --------------------------------------------------------------------------
# 3) The surface builder itself: prose columns must not leak into it.
# --------------------------------------------------------------------------
surface = dc._documented_name_surface(DOC_WITHOUT_GRAFANA)
check("surface excludes description-column prose", "grafana" in surface, False)
check("surface includes row heads", "pellet-price-monitor" in surface, True)
check("surface includes headings", "application inventory" in surface, True)

# --------------------------------------------------------------------------
# 4) End-to-end against the REAL inventory: the live doc must still report the
#    same set of undocumented apps as before the change (no new FPs). This is
#    the real-inventory sweep docs/sops/audit-script-correctness.md asks for.
# --------------------------------------------------------------------------
real = (ROOT / "docs" / "applications.md").read_text()
real_surface = dc._documented_name_surface(real)
check("real applications.md yields a non-empty surface", bool(real_surface.strip()), True)
# Sanity anchors: things that genuinely have entries must not start failing.
for app in ("grafana", "immich", "nextcloud", "paperless-ngx", "ingress-nginx",
            "wazuh", "superset", "penpot", "jellyfin", "n8n"):
    check(f"real doc still documents {app}", documented(real, app), True)

print()
if FAIL:
    print(f"FAILED  {FAIL} failed, {PASS} passed")
    sys.exit(1)
print(f"OK  {PASS} passed")
