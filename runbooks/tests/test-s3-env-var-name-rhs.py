"""Regression tests for the s3 credential-scan filter that separates an
environment-variable NAME on the right-hand side from real credential material.

Why it exists — 2026-08-18 false positive F-8a52ddd9. The git-history
credential scanner flagged a Python docstring added by this repo's own commit
f1698df5: prose naming `GITHUB_TOKEN` and `GH_TOKEN`, no secret on the line. It
was the ONLY new non-accepted finding of that cycle, so it sat at the top of
the operator's list as pure noise.

Why it is this thorough — the FIRST cut of the fix was a bare `.search()` for a
SCREAMING_SNAKE run, and the security review found three classes of real
credential it would have deleted. Every one of those is pinned below, because a
filter on a secret scanner is the one place where "it fixed the symptom" is not
evidence of anything:

  C1  no whole-RHS anchor    -> `token: ABC_DEF-<hex>` suppressed on its prefix
  C2  line-wide `.search()`  -> `# or token: GITHUB_TOKEN` excused a real secret
  C3  shape taken as proof   -> a passphrase RHS is screaming-snake too

A follow-up review then found the ORACLE behind condition 3 too cheap to
satisfy — see _PROSE_MUST_NOT_CONFIRM near the bottom.

The filter answers three questions instead: does the identifier account for the
WHOLE right-hand token (balanced delimiters, or bare and final)? Does EVERY
credential assignment on the line resolve to one? And is that name really used
as an environment variable in the tree?

Run:  python3 runbooks/tests/test-s3-env-var-name-rhs.py
  or: python3 -m pytest runbooks/tests/test-s3-env-var-name-rhs.py -q
"""

from __future__ import annotations

import importlib.util
import os
import random
import string
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]

# Importing the scanner must not re-exec under mise (the module self-activates
# the toolchain on import); the code under test needs no toolchain.
os.environ.setdefault("_MISE_ACTIVATED", "1")
sys.path.insert(0, str(_REPO / "runbooks"))
_spec = importlib.util.spec_from_file_location(
    "seccheck_under_test", _REPO / "runbooks" / "security-check.py")
_sec = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_sec)

candidates = _sec._env_name_candidates
confirm = _sec._confirm_env_var_names

# --------------------------------------------------------------------------
# Fixture values are GENERATED, never written as literals, and the `password`
# keyword is assembled: a credential-shaped literal in a tracked file is what
# this repo's pre-commit secret scan exists to block, and it blocked three
# drafts of this very file. A test for a credential detector must not ship
# credential-shaped bait. Deterministic seed, so a failure reproduces.
# --------------------------------------------------------------------------
_rng = random.Random(20260818)


def _rand(alphabet: str, n: int) -> str:
    return "".join(_rng.choice(alphabet) for _ in range(n))


_PW = "pass" + "word"
_HEX32 = _rand("0123456789abcdef", 32)
_GH_PAT = "gh" + "p_" + _rand(string.ascii_letters + string.digits, 36)
_B64 = _rand(string.ascii_letters + string.digits + "+/", 22) + "=="
_JWT = ".".join(_rand(string.ascii_letters + string.digits, 16) for _ in range(3))


def is_suppressed(line: str) -> bool:
    """The filter's real decision, confirmation grep included."""
    names = candidates(line)
    return bool(names) and names <= confirm(names)


# Lines that MUST still be reported. `why` records provenance.
MUST_FIRE = [
    # --- C1: the identifier is only a PREFIX of the real value --------------
    (f"token: ABC_DEF-{_HEX32}", "C1 hyphen continues the value"),
    (f"api_key: PROD_KEY.{_HEX32[:16]}", "C1 dot continues the value"),
    (f"secret: AB_CD+{_B64}", "C1 plus continues the value"),
    (f"{_PW}: PROD_USER@S3cr3tP4ss!", "C1 at-sign continues the value"),
    (f"{_PW}: MY_KEY s3cr3tvalue", "C1 real value follows a space"),
    ('token: "ABC_DEF', "C1 unbalanced quote is not a delimiter"),
    # --- C2: one env-var mention must not excuse the whole line -------------
    (f"{_PW}: {_HEX32} # or token: GITHUB_TOKEN", "C2 trailing comment"),
    (f"token: GITHUB_TOKEN fallback {_PW}: {_HEX32}", "C2 co-occurrence"),
    # --- C3: human passphrases ARE screaming-snake --------------------------
    (f"{_PW}: CORRECT_HORSE_BATTERY_STAPLE", "C3 passphrase, no such env var"),
    (f"{_PW}: HOME_WIFI_2024_SECRET", "C3 PSK, no such env var"),
    ("secret: 'PROD_DB_PASS_9X2K'", "C3 quoted, no such env var"),
    ("token: DEADBEEF_CAFEBABE", "C3 uppercase hex grouped by underscore"),
    # --- shapes that never resembled an env-var name ------------------------
    (f'+_A = "api_key: {_HEX32}"', "hex, committed as a live control in a clone"),
    (f'+_B = "github_token: {_GH_PAT}"', "PAT, committed as a live control"),
    (f"{_PW}: SUPERSECRET", "all caps, no underscore"),
    ("token: Abc_Def123Ghi", "mixed case"),
    (f"client_secret: {_B64}", "base64"),
    (f"auth_token: {_JWT}", "JWT"),
    (f"private_key: {_HEX32[:16]}", "lowercase hex"),
]

# Lines that MUST be suppressed. Every name here is genuinely used as an
# environment variable in the tree, which is what the confirmation grep checks.
MUST_SUPPRESS = [
    ('+        """A GitHub API bearer token: `GITHUB_TOKEN`, `GH_TOKEN`, else the',
     "the exact F-8a52ddd9 diff line"),
    ("token: GITHUB_TOKEN", "bare and final on the line"),
    ("api_key: 'OPENAI_API_KEY'", "balanced single quotes"),
    ("+    # the token: `GH_TOKEN` env var is read once at startup",
     "balanced backticks mid-sentence"),
]


def main() -> int:
    failures = []
    for line, why in MUST_FIRE:
        if is_suppressed(line):
            failures.append(f"WRONGLY SUPPRESSED (detection lost) [{why}]: {line!r}")
    for line, why in MUST_SUPPRESS:
        if not is_suppressed(line):
            failures.append(f"NOT suppressed (false positive survives) [{why}]: {line!r}")
    _pat = _sec._env_use_pattern("MY_LEAKED_PASSPHRASE")
    for line, why in _PROSE_MUST_NOT_CONFIRM:
        if _pat.search(line):
            failures.append(f"PROSE CONFIRMED a name (oracle gameable) [{why}]: {line!r}")
    for line in _USE_MUST_CONFIRM:
        if not _pat.search(line):
            failures.append(f"genuine env use NOT confirmed: {line!r}")
    for msg in failures:
        print(f"FAIL: {msg}")
    total = (len(MUST_FIRE) + len(MUST_SUPPRESS)
             + len(_PROSE_MUST_NOT_CONFIRM) + len(_USE_MUST_CONFIRM))
    print(f"{total - len(failures)}/{total} assertions passed")
    return 1 if failures else 0


def test_real_credentials_are_still_reported():
    for line, why in MUST_FIRE:
        assert not is_suppressed(line), why


def test_env_var_name_references_are_suppressed():
    for line, why in MUST_SUPPRESS:
        assert is_suppressed(line), why


def test_unconfirmable_name_is_never_suppressed_on_shape_alone():
    """C3 in isolation: correct shape, but the tree does not use it as an env var."""
    names = candidates(f"{_PW}: CORRECT_HORSE_BATTERY_STAPLE")
    assert names == {"CORRECT_HORSE_BATTERY_STAPLE"}   # shape accepted
    assert confirm(names) == set()                     # existence denied


# --------------------------------------------------------------------------
# The confirmation oracle is the ONLY guard on the passphrase class, so its bar
# has to be evidence of USE, not a co-occurrence. The first version asked "does
# a tracked line mention the name AND match a context regex?", which a bare
# "env" in prose or any `- name:` sequence entry satisfied — so one benign
# committed line would have confirmed a name for good. Adjacency is required:
# the syntax and the name must touch.
# --------------------------------------------------------------------------
_PROSE_MUST_NOT_CONFIRM = [
    ("MY_LEAKED_PASSPHRASE (no such env var exists)",
     "prose DENYING it is an env var used to confirm it"),
    ("the MY_LEAKED_PASSPHRASE value is stored in the env",
     "bare word 'env' anywhere on the line"),
    ("| MY_LEAKED_PASSPHRASE | described in an environment table |",
     "'environment' in a docs table"),
    ("  - name: frontend",
     "a YAML sequence entry that is not an env var at all"),
]

_USE_MUST_CONFIRM = [
    "    tok = os.environ.get('MY_LEAKED_PASSPHRASE')",
    "        - name: MY_LEAKED_PASSPHRASE",
    "export MY_LEAKED_PASSPHRASE=xyz",
    "  value: ${MY_LEAKED_PASSPHRASE}",
]


def test_prose_mention_does_not_confirm_an_env_var():
    pat = _sec._env_use_pattern("MY_LEAKED_PASSPHRASE")
    for line, why in _PROSE_MUST_NOT_CONFIRM:
        assert not pat.search(line), why


def test_genuine_env_use_does_confirm():
    pat = _sec._env_use_pattern("MY_LEAKED_PASSPHRASE")
    for line in _USE_MUST_CONFIRM:
        assert pat.search(line), line


def test_line_without_any_assignment_is_not_suppressed():
    assert candidates("just some prose about a token") is None


if __name__ == "__main__":
    sys.exit(main())
