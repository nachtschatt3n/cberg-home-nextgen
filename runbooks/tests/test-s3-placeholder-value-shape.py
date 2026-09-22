#!/usr/bin/env python3
"""Pin the scaffolding-PHRASE shape rule in `_hist_cred_hit_suppressed` (F-54cbd530).

The 2026-09-10 cycle carried five history rows at contextual HIGH whose values
were template tokens (`REPLACE_WITH_SECURE_…`, `your_actual_db_…`,
`changeme-<app>`, `PLACEHOLDER_ENCRYPTED_…`, a bare `placeholder` annotated
with the env var that supplies the real value). The Python predicate held only
an EXACT-match set, so a vocabulary it could plainly read still fired.

The fix is a SHAPE rule, not a word filter, because the 2026-09-08 rule is
that a value's own vocabulary may never buy silence (the leaked credential was
spelled like a placeholder). Every assertion below therefore comes in pairs:
the template phrase goes quiet AND its nearest credential-shaped neighbour
keeps firing.

Fixtures are assembled at RUNTIME (key and value concatenated from parts) so
this file never contains a credential-shaped line for the history scan or the
pre-commit guard to trip on.

COMMISSIONING STRAW: the pre-fix predicate is reconstructed by evaluating the
module's own rule set WITHOUT the two new branches, over the same five lines.
If that straw does not fire on all five, the witnesses are not witnesses.

Run: python3 runbooks/tests/test-s3-placeholder-value-shape.py
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import sys
from pathlib import Path

os.environ.setdefault("_MISE_ACTIVATED", "1")
os.environ.pop("SWEEP_PG_DSN", None)
ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
sys.argv = ["security-check.py"]
_spec = importlib.util.spec_from_file_location("sc", ROOT / "runbooks" / "security-check.py")
sc = importlib.util.module_from_spec(_spec)
with contextlib.redirect_stdout(io.StringIO()):
    _spec.loader.exec_module(sc)

PASS = FAIL = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}" + (f"\n        {detail}" if detail else ""))


# Runtime-assembled key and values: no line in this file is credential-shaped.
K = "pass" + "word"
PW = "PASS" + "WORD"


def line(value: str, key: str = K, comment: str = "", sign: str = "-") -> str:
    return f"{sign}        {key}: {value}" + (f"   # {comment}" if comment else "")


# ── the five 2026-09-10 rows, reproduced by shape ────────────────────────────
FIVE = [
    ("bare placeholder + env-var comment",
     line("placeholder", comment="overridden by ADMIN_" + PW + " env from Secret")),
    ("PLACEHOLDER_ENCRYPTED_…_REPLACE_WITH_ACTUAL_…",
     line("PLACEHOLDER_ENCRYPTED_VALUE_REPLACE_WITH_ACTUAL_" + PW)),
    ("your_actual_db_…", line("your_actual_db_" + K, key="db_" + K)),
    ("changeme-<app>", line("changeme-someapp")),
    ("REPLACE_WITH_SECURE_…", line("REPLACE_WITH_SECURE_" + PW)),
]


def old_predicate(text: str) -> bool:
    """The pre-fix rule set: the module's own branches minus the two new ones.

    Reconstructed from the module rather than transcribed, so it cannot drift
    from what the predicate actually evaluates; only the two F-54cbd530
    branches are left out.
    """
    values = []
    for m in sc._HIST_CRED_KV.finditer(text):
        raw = m.group(1)
        inner = raw[1:-1] if len(raw) >= 2 and raw[0] in "\"'`" and raw[-1] == raw[0] else raw
        values.append(inner.rstrip(",;"))
    ctx_parts = []
    for m in sc._HIST_CRED_KV.finditer(text):
        k = m.start()
        while k > 0 and (text[k - 1].isalnum() or text[k - 1] in "_-.["):
            k -= 1
        ctx_parts.append(text[k:m.start(1)])
    cm = sc.re.search(r"(#|//).*$", text)
    context = " ".join(ctx_parts) + " " + (cm.group(0) if cm else "")
    if not values:
        return bool(sc._REFERENCE_CONTEXT.search(text))
    if sc._PLACEHOLDER_CONTEXT.search(context) or sc._REFERENCE_CONTEXT.search(context):
        return True
    return all(sc._NON_LITERAL_VALUE.search(v) or sc._wrapped_value_is_reference(v)
               or v.lower() in sc._TEMPLATE_LITERALS for v in values)


print("s3 placeholder value shape\n")
print("-- COMMISSIONING STRAW: the pre-fix rule set fires on all five --")
for label, text in FIVE:
    check(f"STRAW fires: {label}", old_predicate(text) is False, text)

print("\n-- the five go quiet under the shape rule --")
for label, text in FIVE:
    check(f"quiet: {label}", sc._hist_cred_hit_suppressed(text) is True, text)

# ── every quiet phrase has a neighbour that must keep firing ─────────────────
print("\n-- neighbours: one digit, one case break, one missing anchor, one bare word --")
NEIGHBOURS = [
    ("bare `placeholder`, no env-var in context (the 2026-09-08 shape)",
     line("placeholder", sign="+")),
    ("bare `placeholder` with a prose comment only",
     line("placeholder", comment="see the docs", sign="+")),
    ("placeholder + digits (the pinned witness class)", line("placeholder7Zq", sign="+")),
    ("placeholder + case break, one word", line("placeholderXyz", sign="+")),
    ("changeme + digit", line("changemeXyz1", sign="+")),
    ("example + digits", line("exampleXyz12", sign="+")),
    ("anchor not at a word boundary", line("notaplaceholder1", sign="+")),
    ("multi-word, digit-free, but NO anchor (a real passphrase)",
     line("correct-horse-battery-staple", sign="+")),
    ("REPLACE_WITH phrase carrying a digit", line("REPLACE_WITH_SECURE_" + PW + "2", sign="+")),
    ("mixed-case word inside the phrase", line("Replace_With_Secure_" + PW, sign="+")),
    ("env-var comment does not rescue a non-bare value",
     line("placeholder7Zq", comment="overridden by ADMIN_" + PW + " env", sign="+")),
    ("punctuation inside the value", line("ChangeMe.", sign="+")),
    ("quoted real value with an anchor word elsewhere on the line",
     f'+        {K}: "Hunter2Seven"  # rotate, then replace_with the new one'),
]
for label, text in NEIGHBOURS[:-1]:
    check(f"fires: {label}", sc._hist_cred_hit_suppressed(text) is False, text)
# The last neighbour is the scaffolding-word-in-COMMENT case, which the
# pre-existing _PLACEHOLDER_CONTEXT rule already silences by design (pinned
# in test-cred-suppressor-scoping.py). It is listed here so nobody mistakes
# it for a shape-rule regression: the shape rule is not what quiets it.
check("context rule (pre-existing) still owns the comment case",
      sc._hist_cred_hit_suppressed(NEIGHBOURS[-1][1]) is True)

# ── the accepted residual, stated so it is a decision and not a surprise ─────
print("\n-- accepted residual, recorded --")
check("a digit-free multi-word phrase WITH an anchor is quiet (documented trade)",
      sc._hist_cred_hit_suppressed(line("your-secret-here", sign="+")) is True)

# ── the helpers themselves ───────────────────────────────────────────────────
print("\n-- helper contracts --")
check("shape helper needs at least two words", sc._placeholder_scaffold_value("placeholder") is False)
check("shape helper rejects any digit", sc._placeholder_scaffold_value("replace_with_1") is False)
check("shape helper accepts UPPER phrases", sc._placeholder_scaffold_value("REPLACE_WITH_VALUE") is True)
check("shape helper accepts lower phrases", sc._placeholder_scaffold_value("your_actual_value") is True)
check("shape helper strips quotes and trailing punctuation",
      sc._placeholder_scaffold_value('"changeme-app",') is True)
check("shape helper: non-ASCII words are not scaffolding",
      sc._placeholder_scaffold_value("änderung-mich") is False)
check("bare helper needs an UPPER_SNAKE identifier in context",
      sc._bare_placeholder_with_env_reference("placeholder", "password  # from env") is False
      and sc._bare_placeholder_with_env_reference("placeholder", "password  # ADMIN_X env") is True)
check("bare helper never accepts a non-bare value",
      sc._bare_placeholder_with_env_reference("placeholder7Zq", "password  # ADMIN_X") is False)

# Population guard: this file must exercise a real number of lines, or a
# refactor that empties FIVE/NEIGHBOURS would pass vacuously.
check("population: five witnesses and at least ten neighbours were evaluated",
      len(FIVE) == 5 and len(NEIGHBOURS) >= 10)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
