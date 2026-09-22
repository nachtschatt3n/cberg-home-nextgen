#!/usr/bin/env python3
"""
Regression test for doc-check.py section 11, the retired-rule phrase detector
(F-485655e1).

The defect: a rule stated in several files drifts when a fix updates some
copies and not others, and agents follow the STRICTER surviving copy. d147b1ce
corrected the "AUTO-NIGHT runs unattended in `mode: unattended` windows" claim
in three files; the fourth (the SOP the agent definition points at) kept it,
wrapped across two lines, and a cron-fired attended window could execute
nothing. A grep finds this in seconds; nothing ran the grep — doc-check.py had
ZERO occurrences of the words retired / unattended / auto_execute.

Contract, asserted through the module's own functions on a fixture corpus:
  1. A live single-line assertion is flagged; a WRAPPED assertion (the exact
     ac2b5a2e shape) is flagged too, once, at its first line.
  2. Historical mentions are exempt: a history marker on the line, on the
     line before or after, or a row under a History/Changelog heading.
  3. Every seeded entry is GROUNDED in git — its retired_by commit actually
     removed a match — and a bogus entry is not.
  4. The corpus excludes plan files and doc-check itself.
  5. COMMISSIONING STRAWS: (a) an empty phrase list — the pre-fix state —
     flags nothing on the same fixture; (b) a naive single-line grep misses
     the wrapped assertion the module's scanner catches.

Run: python3 runbooks/tests/test-doc-check-retired-phrases.py
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys
import tempfile
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


tmp = Path(tempfile.mkdtemp(prefix="retired-phrases-"))
FIXTURE = {
    # the updated copies (d147b1ce shape)
    "updated-agent.md": "**AUTO-NIGHT** may execute WITHOUT asking in ANY window regardless of its `mode:`.\n",
    # historical mention with the marker on the same line (maintenance-windows.yaml shape)
    "policy.yaml": "  # RETIRED knobs, do not reintroduce: `auto_execute` + `risk: low`\n",
    # THE missed fourth site: a live assertion wrapped over two lines (ac2b5a2e shape)
    "sop.md": ("- plans cannot claim a class. **AUTO-NIGHT** runs unattended in\n"
               "  `mode: unattended` windows (no unresolved interference).\n"),
    # a live single-line assertion of a retired knob
    "old-rule.md": "A plan may run WITHOUT asking only if `auto_execute: true` is set.\n",
    # history table row under a History heading
    "sop-history.md": ("## Version History\n\n| 2026.09.13 | corrected: AUTO-NIGHT runs unattended in "
                       "`mode: unattended` windows |\n"),
    # marker on the PREVIOUS line (maintenance-window-agent.md shape)
    "agent.md": "never read the retired\n`auto_execute` / `unattended_allowed` / `max_unattended_risk` knobs:\n",
    # marker on the NEXT line
    "notes.md": "the `max_unattended_risk` ceiling\nwas the old gate and is superseded.\n",
}
for name, text in FIXTURE.items():
    (tmp / name).write_text(text)
files = sorted(tmp.iterdir())

hits = dc.scan_retired_phrases(files, dc.RETIRED_PHRASES, tmp)
got = sorted((h["file"], h["line"], h["id"]) for h in hits)
want = sorted([("old-rule.md", 1, "auto_execute-knob"),
               ("sop.md", 1, "auto-night-mode-unattended-only")])
check("exactly the two live assertions are flagged (single-line + wrapped), nothing historical",
      got == want, f"got {got}")
check("the wrapped assertion is reported once, at its first line",
      sum(1 for h in hits if h["file"] == "sop.md") == 1 and
      [h["line"] for h in hits if h["file"] == "sop.md"] == [1])
check("hits carry the offending text for the operator",
      all(h["text"] for h in hits))

# 3 — grounding (reads this repo's own git history; a tracked-file exception)
for e in dc.RETIRED_PHRASES:
    check(f"seed `{e['id']}` is grounded: {e['retired_by']} removed a match", dc.retired_phrase_grounded(e))
check("a bogus commit is not grounded",
      not dc.retired_phrase_grounded({"phrase": r"\bauto_execute\b", "retired_by": "0000000"}))
check("a phrase the commit never removed is not grounded",
      not dc.retired_phrase_grounded({"phrase": r"zzz-phrase-never-there", "retired_by": "a39d8766"}))

# 4 — corpus shape
corpus = dc._retired_phrase_corpus(ROOT)
rels = {str(p.relative_to(ROOT)) for p in corpus}
check("corpus is the rule-bearing docs (well above the 10-file floor)", len(corpus) >= 10, f"{len(corpus)}")
check("corpus includes the four sites of the F-485655e1 rule",
      {"docs/sops/maintenance-windows.md", ".claude/agents/maintenance-window-agent.md",
       "runbooks/autonomy-policy.yaml", "runbooks/maintenance-windows.yaml"} <= rels)
check("corpus excludes plan files (per-change artifacts) but keeps the plan README",
      not any(r.startswith("runbooks/maintenance/plans/") and not r.endswith("README.md") for r in rels)
      and "runbooks/maintenance/plans/README.md" in rels)
check("corpus excludes doc-check.py itself", "runbooks/doc-check.py" not in rels)

# 5 — COMMISSIONING STRAWS
check("STRAW (a): with no phrase list — the pre-fix state — the same fixture yields no hit",
      dc.scan_retired_phrases(files, [], tmp) == [])
naive = [(p.name, i + 1) for p in files for i, line in enumerate(p.read_text().splitlines())
         for e in dc.RETIRED_PHRASES if re.search(e["phrase"], line, re.I)
         and not dc.RETIRED_PHRASE_HISTORY_MARKERS.search(line)]
check("STRAW (b): a naive single-line grep misses the wrapped SOP assertion",
      ("sop.md", 1) not in naive and ("sop.md", 2) not in naive, f"{naive}")
check("STRAW (b): ...and the naive grep also mis-flags the marker-on-previous-line mention",
      ("agent.md", 2) in naive, f"{naive}")

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
