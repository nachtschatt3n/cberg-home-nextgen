#!/usr/bin/env python3
r"""Regression tests: a credential VALUE wrapped in quoting debris must still be
recognised as a reference -- and a LITERAL wearing the same debris must not.

Incident (2026-09-17, five contextual-HIGH rows). `_HIST_CRED_KV` lifts a value
out of a diff line as raw text, but only a BALANCED run of REAL quotes is
unwrapped. A value that arrives inside a NESTED string keeps its punctuation:

    -H "Authorization: MediaBrowser Token=\"$JF_KEY\""   ->  value  \"$JF_KEY\""
    f"        api_key: {m.group(1)}\n"                   ->  value  {m.group(1)}\n"

Every reference rule in `_NON_LITERAL_VALUE` is ANCHORED (`^\$VAR$`,
`^\{name\}$`), so the debris ALONE defeats all of them and a shell variable was
filed as a leaked credential. The unescaped spelling of the same shape had
already been patched at the grep layer on 2026-09-15 (F-6bf496a1 / F-d6b2bd92 /
F-3d1d7147); the escaped spelling was the next one along. That is the papering
cycle this file exists to stop, so the fix is value-scoped, in Python.

THE DANGER THIS FILE GUARDS AGAINST IS THE FIX, NOT THE BUG. This repo has
repeatedly turned a false-positive fix into a false negative. The rule's whole
safety rests on TWO properties, and this file pins each one with a true
positive AND a mutation that kills it:

  ENDS-ONLY   debris is stripped from the ends, never from the middle, so a
              literal with an embedded quote or comma stays visible.
  FULL-MATCH  the remainder must match a reference in FULL, so a
              reference-shaped PREFIX followed by literal text stays visible.

Both mutations passed the first version of this suite (measured 2026-09-17,
25/25 green against each), which is why the rows below exist.

Fixture values are GENERATED, never written as literals, and the credential
keywords are assembled at runtime: a credential-shaped literal in a tracked file
is what this repo's pre-commit secret scan exists to block. The fixture file is
itself excluded from the s3 history pathspec, and that exclusion is asserted
below.

Run:  python3 runbooks/tests/test-s3-escaped-value-reference.py
"""

from __future__ import annotations

import contextlib
import importlib.util
import os
import pathlib
import random
import re
import string
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
SC_PATH = ROOT / "runbooks" / "security-check.py"
os.environ["_MISE_ACTIVATED"] = "1"
os.chdir(ROOT)
sys.argv = ["security-check.py"]
_spec = importlib.util.spec_from_file_location("sc_under_test", SC_PATH)
sc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sc)

PASS = FAIL = SKIP = 0
_rng = random.Random(20260917)

# keywords assembled so no line of this file reads as a credential assignment
TOK = "tok" + "en"
PW = "pass" + "word"
AK = "api_" + "key"
Q = chr(92) + '"'          # the two characters  \"  -- an ESCAPED quote
NL = chr(92) + "n"         # the two characters  \n  -- inside a python string


def check(name: str, got, want) -> None:
    global PASS, FAIL
    if got == want:
        print(f"  PASS  {name}")
        PASS += 1
    else:
        print(f"  FAIL  {name}\n        got {got!r}  want {want!r}")
        FAIL += 1


def skip(name: str, why: str) -> None:
    global SKIP
    print(f"  SKIP  {name}\n        {why}")
    SKIP += 1


def gen(n: int) -> str:
    return "".join(_rng.choice(string.ascii_letters + string.digits) for _ in range(n))


LIT = gen(44)                       # a credential-shaped literal, generated
DOLLAR_LIT = "$" + gen(1).lower() + gen(16)   # a literal that merely starts with `$`

HAS_FIX = hasattr(sc, "_wrapped_value_is_reference")


@contextlib.contextmanager
def pre_fix():
    """Run `_hist_cred_hit_suppressed` with the new rule disabled.

    This reproduces the PRE-FIX verdict through the real function, so every
    witness below is PROVEN to be a witness rather than a row that would have
    passed either way.
    """
    if not HAS_FIX:
        yield False
        return
    orig = sc._wrapped_value_is_reference
    sc._wrapped_value_is_reference = lambda _v: False
    try:
        yield True
    finally:
        sc._wrapped_value_is_reference = orig


def quiet(line: str) -> bool:
    return sc._hist_cred_hit_suppressed(line)


# ---------------------------------------------------------------------------
# The witnesses: the five HIGH rows of 2026-09-17, by shape.
# ---------------------------------------------------------------------------
print("test-s3-escaped-value-reference\n")
print("-- witnesses: an escaped/interpolated REFERENCE must go quiet --")

WITNESSES = [
    ("shell: escaped-quoted $VAR in an auth header",
     '+curl -s -H "Authorization: MediaBrowser ' + TOK.title() + "=" + Q + "$JF_KEY" + Q
     + '" http://localhost:8097/Items/Counts'),
    ("python: f-string placeholder with a dotted call",
     '-       f"        ' + AK + ": {m.group(1)}" + NL + '"'),
]
for label, line in WITNESSES:
    with pre_fix() as simulated:
        was = quiet(line)
    if simulated:
        check(f"PRE-FIX reported it (so it is a real witness) -- {label}", was, False)
    else:
        print(f"  ....  fix ABSENT from {SC_PATH.name}; the row below IS the pre-fix measurement")
    check(f"now quiet -- {label}", quiet(line), True)

# Already covered BEFORE this fix, kept as a pin so nobody patches it a third
# time: `_NON_LITERAL_VALUE`'s `\$\{` branch is UNANCHORED, so the braced
# spelling survives its own debris by accident. It is not a witness -- it was
# already quiet -- and saying so here is the difference between a pin and a row
# that passes for the wrong reason.
check("pin (NOT a witness -- already quiet pre-fix via the unanchored `${` branch): "
      "escaped-quoted ${BRACED} in a header",
      quiet('+  -H "X-Emby-' + TOK.title() + ": " + Q + "${JF_KEY}" + Q + '"'), True)

# ---------------------------------------------------------------------------
# THE LOAD-BEARING HALF. Debris is stripped from the ENDS ONLY and the remainder
# must match a reference in FULL, so a literal anywhere inside the value keeps
# the hit visible. If any of these flips to quiet, the detector went blind.
# ---------------------------------------------------------------------------
print("\n-- true positives: a literal in the SAME wrapper must stay visible --")

TRUE_POSITIVES = [
    ("escaped-quoted LITERAL, byte-identical header shape",
     '+curl -s -H "Authorization: MediaBrowser ' + TOK.title() + "=" + Q + LIT + Q
     + '" http://x'),
    ("reference AND literal on the same line",
     '+curl -H "X-Emby-' + TOK.title() + ': $JF_KEY" -H "X-Api-Key: ' + LIT + '" http://x'),
    ("escaped lowercase $ab is not the shell-constant shape",
     "+  " + PW + ": " + Q + "$ab" + Q),
    ("escaped two-character $AB is too short to be a constant",
     "+  " + PW + ": " + Q + "$AB" + Q),
    ("escaped literal that merely STARTS with `$`",
     "+  " + PW + ": " + Q + DOLLAR_LIT + Q),
    ("escaped ALL-CAPS literal with no `$`",
     "+  " + PW + ": " + Q + "HUNTER2SEVENXY" + Q),
    ("literal glued to an f-string placeholder",
     '-       f"        ' + AK + ": {m.group(1)}" + LIT + NL + '"'),
    ("plain unwrapped literal",
     "+      " + PW + ": Hunter2Seven"),
    # ---- ENDS-ONLY pins. Debris stripped from the MIDDLE would swallow these.
    ("ALL-CAPS literal with an embedded comma (pins ENDS-ONLY stripping)",
     "+  " + PW + ": " + Q + "$FOO,BAR9XK" + Q),
    ("ALL-CAPS literal with an embedded escaped quote (pins ENDS-ONLY stripping)",
     "+  " + PW + ": " + Q + '$FOO"BAR9XK' + Q),
    # ---- FULL-MATCH pin. A reference-shaped PREFIX is not a reference.
    ("reference-shaped PREFIX plus literal tail (pins FULL match, not prefix match)",
     "+  " + PW + ": " + Q + "$AWSKEY-abc/123=" + Q),
    # ---- a malformed reference must not be trusted (brace pairing). The
    # original rule wrote the braces as INDEPENDENTLY optional (`\$\{?NAME\}?`),
    # so a stray closing brace was accepted as a reference.
    ("malformed reference: stray CLOSING brace",
     "+  " + PW + ": " + Q + "$HUNTER2SEVEN}" + Q),
]
for label, line in TRUE_POSITIVES:
    check(f"stays visible -- {label}", quiet(line), False)

# ---------------------------------------------------------------------------
# DISCRIMINATOR. A true-positive list is only worth what it REJECTS. Install
# over-broad suppressors -- the shortcuts someone reaching for "just make the
# finding go away" would actually write, INCLUDING the two that defeated the
# first version of this file -- and require that the list above catches each.
# ---------------------------------------------------------------------------
print("\n-- discriminator: the true-positive list must REJECT a blindfold --")

if HAS_FIX:
    def _strip(v: str) -> str:
        s, prev = v, None
        while prev != s:
            prev = s
            s = sc._VALUE_DEBRIS.sub("", s)
        return s

    _REF = r"\$\{?[A-Z_][A-Z0-9_]{2,}\}?"

    MUTANTS = {
        "`$` anywhere in the value": lambda v: "$" in v,
        "case-PERMISSIVE identifier after stripping debris":
            lambda v: bool(re.match(r"^\$\{?[A-Za-z_][A-Za-z0-9_]*\}?$", _strip(v))),
        "any value that HAD debris counts as a reference": lambda v: _strip(v) != v,
        # The two that shipped green against the first version of this suite.
        "debris stripped ANYWHERE, not ends-only":
            lambda v: bool(re.fullmatch(
                _REF, re.sub(r"""\\*["'`]|\\[nrt]|[,;]""", "", v))),
        "reference matched as a PREFIX, not in full":
            lambda v: _strip(v) != v and bool(re.match("^" + _REF, _strip(v))),
    }
    orig = sc._wrapped_value_is_reference
    for name, mutant in MUTANTS.items():
        sc._wrapped_value_is_reference = mutant
        try:
            blinded = [lbl for lbl, ln in TRUE_POSITIVES if quiet(ln)]
        finally:
            sc._wrapped_value_is_reference = orig
        check(f"mutant REJECTED ({len(blinded)} true positive(s) go quiet) -- {name}",
              bool(blinded), True)
        for lbl in blinded:
            print(f"          caught by: {lbl}")
else:
    check("discriminator needs the fix present", HAS_FIX, True)

# ---------------------------------------------------------------------------
# CORPUS CONTROL. Synthetic rows prove the rule; only history proves the
# SCANNER. Every credential literal on the acceptance register is a real leaked
# value in this repo's history. None of the lines carrying one may become
# invisible because of this fix.
#
# The register lives in sweep_history Postgres, so this control needs
# SWEEP_PG_DSN. It is SKIPPED LOUDLY without one rather than failed: this file
# runs inside `runbooks/tests/run-all.sh`, which `.githooks/pre-commit` invokes
# fail-closed with no DSN, so failing here would block every commit that touches
# runbooks/. When the DSN IS present the control is HARD -- a register that
# loads empty or a pickaxe that sees nothing fails, because a silent zero is
# never a pass.
# ---------------------------------------------------------------------------
print("\n-- corpus control: real leaked literals in real history --")

if not os.environ.get("SWEEP_PG_DSN"):
    skip("corpus control (real history lines carrying known leaked literals)",
         "SWEEP_PG_DSN unset -- the acceptance register is DB-backed. This is a "
         "REAL GAP in this run, not a pass: re-run with the sweep DSN exported "
         "(source runbooks/lib/sweep-pg-dsn.sh) to exercise it.")
else:
    needles = [p for p in getattr(sc, "GIT_HISTORY_CRED_PATTERNS", ())
               if len(p) >= 20 and re.fullmatch(r"[A-Za-z0-9_\-]+", p)
               and any(c.isupper() for c in p) and any(c.islower() for c in p)
               and any(c.isdigit() for c in p)]
    check("acceptance register loaded (fails CLOSED if the policy DB is unreachable)",
          len(needles) > 0, True)

    corpus: set[str] = set()
    for p in needles:
        out = subprocess.run(f"git log --all -p -S{p!r} -- . | grep -F {p!r}",
                             shell=True, capture_output=True, text=True).stdout
        corpus.update(x.rstrip() for x in out.splitlines() if x.strip())
    check("the pickaxe can SEE (non-zero history lines carrying a known literal)",
          len(corpus) > 0, True)
    print(f"          corpus: {len(corpus)} distinct history lines from {len(needles)} needles")

    with pre_fix() as simulated:
        before = {ln for ln in corpus if not quiet(ln)}
    after = {ln for ln in corpus if not quiet(ln)}
    check("the corpus control has POWER (some lines were visible pre-fix, so the "
          "delta below could have been non-empty)", len(before) > 0, True)
    check("no history line carrying a known leaked literal was newly blinded",
          sorted(before - after), [])

# ---------------------------------------------------------------------------
# ACCEPTED MISSES, stated in code. These are suppressed ON PURPOSE and are the
# price of the rule. If one ever flips, the boundary moved and this file is the
# place that says so.
# ---------------------------------------------------------------------------
print("\n-- accepted misses (documented, not accidents) --")

check("MISS: a literal whose whole text is $UPPER_SNAKE-shaped is indistinguishable "
      "from a shell reference (same miss S3_SHELL_VAR_RHS_ERE already accepts)",
      quiet("+  " + PW + ": " + Q + "$HUNTER2SEVENXY" + Q), True)
check("MISS: a literal CONCATENATED onto a reference, where the whole is still "
      "$UPPER_SNAKE-shaped -- the ends-only/full-match property does NOT save this "
      "case, and saying so here is the difference between a boundary and a surprise",
      quiet("+  " + PW + ": " + Q + "$JF_KEYHUNTER2SEVEN" + Q), True)
check("MISS: a placeholder-SHAPED literal inside escaped quotes ({SOMENAME}) -- "
      "_NON_LITERAL_VALUE already accepts the bare spelling; this reaches the "
      "wrapped one",
      quiet("+  " + PW + ": " + Q + "{SOMENAME}" + Q), True)
check("PRE-EXISTING MISS (NOT introduced here): an UNMATCHED OPENING brace "
      "(${NAME with no close) is already quiet on the unpatched module, via "
      "_NON_LITERAL_VALUE's unanchored `${` branch — measured, so the brace "
      "tightening in _WRAPPED_REFERENCE cannot reach it",
      quiet("+  " + PW + ": " + Q + "${HUNTER2SEVEN" + Q), True)
check("WIDER THAN 'escaped': one UNBALANCED REAL quote is debris too, with no "
      "backslash anywhere on the line -- pinned so the trigger surface is visible",
      quiet("+  " + PW + ': "$HUNTER2SEVENXYZ'), True)
check("PRE-EXISTING MISS (NOT introduced here): _NON_LITERAL_VALUE's own `$VAR` "
      "branch is case-PERMISSIVE, so a REAL-quoted literal starting with `$` is "
      "suppressed with or without this fix -- flip this row if that branch is tightened",
      quiet("+  " + PW + ': "' + DOLLAR_LIT + '"'), True)

# ---------------------------------------------------------------------------
# Wiring: the rule must be reachable, the fixture file must be out of scope, the
# report must stop hiding its own count -- and that count must NOT become a
# finding (it scores contextual HIGH and can never clear).
# ---------------------------------------------------------------------------
print("\n-- wiring --")

src = SC_PATH.read_text()
check("the verdict actually calls the new rule",
      "_wrapped_value_is_reference(v)" in src, True)
check("this fixture file is excluded from the s3 history pathspec",
      "':(exclude)runbooks/tests/test-s3-escaped-value-reference.py'" in src, True)
check("the history report emits its TOTAL, not just the first 5 (a truncated "
      "list with no count is a silent zero wearing a number)",
      "len(cred_hits) > 5" in src and "surviving hits" in src, True)

_blk = src.split("if len(cred_hits) > 5:", 1)
check("the total is CONSOLE ONLY -- filing it as a finding in s3_git_history "
      "scores contextual HIGH (vuln + external-unauth) and its `> 5` condition "
      "can never clear, i.e. a permanent unactionable row",
      len(_blk) == 2 and "f.add(" not in _blk[1][:400], True)

print(f"\n{PASS} passed, {FAIL} failed, {SKIP} skipped")


def test_pytest_entry() -> None:
    assert FAIL == 0


if __name__ == "__main__":
    sys.exit(1 if FAIL else 0)
