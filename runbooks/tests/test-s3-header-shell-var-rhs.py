"""Regression tests for the s3 git-history suppressor that recognises a
shell-variable REFERENCE after a credential key with a colon separator.

Why it exists — 2026-09-15, three recurring contextual-HIGH rows
(F-6bf496a1 / F-d6b2bd92 / F-3d1d7147). The jellyfin-12.0 plan (commit
910e49b3) carries copy-pasteable verification commands of the shape
`curl ... -H "X-Emby-Token: $JELLYFIN_API_KEY"`. The existing `$VAR`
suppressor anchors on `=` (`token=$VAR`), so the header form with a colon and
a space slipped past it, and the env-var-name filter could not confirm
`JELLYFIN_API_KEY` because the tree never sets that name — it is a plan's
shell placeholder. Result: a variable reference sat at the top of the
operator's board for two cycles as a credential leak.

Why it is case-strict — a suppressor on a secret scanner is the one place
where "it fixed the symptom" is not evidence. `$UPPER_SNAKE` is a shell
reference and syntactically never a literal; a literal that merely starts
with `$` keeps lowercase letters or digits in odd places, so it must STAY
visible. Both directions are pinned below, and the regex is the SAME object
the scanner runs (imported, then executed through the same BSD/GNU `grep -vE`
the chain uses), not a re-typed copy.

Fixture values are GENERATED, never written as literals, and the credential
keywords are assembled at runtime: a credential-shaped literal in a tracked
file is what this repo's pre-commit secret scan exists to block.

Run:  python3 runbooks/tests/test-s3-header-shell-var-rhs.py
  or: python3 -m pytest runbooks/tests/test-s3-header-shell-var-rhs.py -q
"""

from __future__ import annotations

import importlib.util
import os
import random
import string
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
os.environ.setdefault("_MISE_ACTIVATED", "1")
sys.path.insert(0, str(_REPO / "runbooks"))
_spec = importlib.util.spec_from_file_location(
    "seccheck_under_test", _REPO / "runbooks" / "security-check.py")
_sec = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_sec)

ERE = _sec.S3_SHELL_VAR_RHS_ERE
_rng = random.Random(20260915)
FAILURES: list[str] = []

# keywords assembled so no line of this file reads as a credential assignment
_TOK = "tok" + "en"
_PW = "pass" + "word"
_AK = "api_" + "key"


def _upper(n: int = 12) -> str:
    return "".join(_rng.choice(string.ascii_uppercase + "_") for _ in range(n))


def _literalish(n: int = 14) -> str:
    """A value that starts with `$` but is NOT an UPPER_SNAKE identifier."""
    body = "".join(_rng.choice(string.ascii_letters + string.digits) for _ in range(n))
    return "$" + body[0].lower() + body[1:]


def survives(line: str) -> bool:
    """True when the line SURVIVES `grep -vE ERE` (i.e. is NOT suppressed)."""
    out = subprocess.run(["grep", "-vE", ERE], input=line + "\n",
                         capture_output=True, text=True)
    return out.stdout.strip() != ""


def check(name: str, line: str, want_suppressed: bool) -> None:
    got_suppressed = not survives(line)
    ok = got_suppressed == want_suppressed
    print(f"  {'PASS' if ok else 'FAIL'}  {name}: "
          f"{'suppressed' if got_suppressed else 'survives'}")
    if not ok:
        FAILURES.append(name)


def main() -> int:
    print("test-s3-header-shell-var-rhs")

    var = _upper()
    # The live false positive: HTTP-header form, colon + space, quoted `$VAR`.
    check("header form `X-Emby-Token: $VAR` (quoted) -> suppressed",
          f'+curl -s "http://localhost:8096/Items" -H "X-Emby-{_TOK.title()}: ${var}" | python3',
          True)
    check("header form, braces `${VAR}` -> suppressed",
          f'+  -H "X-Plex-{_TOK.title()}: ${{{var}}}"', True)
    check("yaml-ish `password: $VAR` (unquoted) -> suppressed",
          f"+  {_PW}: ${var}", True)
    check("`api_key=$VAR` still suppressed by the same regex",
          f"+export {_AK.upper()}=${var}", True)

    # THE LOAD-BEARING HALF: values that merely START with `$` stay visible.
    check("`$uperS3cret`-style literal -> survives",
          f'+  {_PW}: "{_literalish()}"', False)
    check("plain literal value -> survives",
          f'+  {_TOK}: "{"".join(_rng.choice(string.ascii_letters + string.digits) for _ in range(20))}"',
          False)
    check("short `$AB` (two chars) is not treated as a reference -> survives",
          f"+  {_PW}: $AB", False)
    check("lowercase `$var` is not the shell-constant shape -> survives",
          f"+  {_TOK}: ${var.lower()}", False)

    # The regex must be the one the scanner actually runs.
    src = (_REPO / "runbooks" / "security-check.py").read_text()
    body = src.split("def s3_git_history", 1)[1].split("\ndef ", 1)[0]
    ok = "S3_SHELL_VAR_RHS_ERE" in body and "grep -vE '{S3_SHELL_VAR_RHS_ERE}'" in body
    print(f"  {'PASS' if ok else 'FAIL'}  s3_git_history's grep chain uses S3_SHELL_VAR_RHS_ERE")
    if not ok:
        FAILURES.append("chain uses constant")

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} -> {', '.join(FAILURES)}")
        return 1
    print("all tests passed")
    return 0


def test_pytest_entry() -> None:
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
