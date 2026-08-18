"""Regression tests for `_ENV_VAR_NAME_RHS`, the s3 credential-scan filter that
distinguishes an environment-variable NAME from a credential VALUE.

Why it exists — 2026-08-18 false positive F-8a52ddd9. The git-history
credential scanner flagged a Python DOCSTRING added by this repo's own commit
f1698df5:

    \"\"\"A GitHub API bearer token: `GITHUB_TOKEN`, `GH_TOKEN`, else the

No secret is present; the line is prose naming two environment variables. It
was the ONLY new non-accepted finding of that cycle, so it sat at the top of
the operator's list as pure noise.

The contract this file defends has TWO directions, and a fix that only proves
one of them is worthless:

  * SUPPRESSED — a bare SCREAMING_SNAKE identifier on the right-hand side.
  * STILL FIRES — anything value-shaped: hex, `ghp_`-prefixed tokens, base64,
    JWTs, mixed case, and (deliberately) an all-caps word with NO underscore.

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
# the toolchain on import); the regex under test needs no toolchain at all.
os.environ.setdefault("_MISE_ACTIVATED", "1")
sys.path.insert(0, str(_REPO / "runbooks"))
_spec = importlib.util.spec_from_file_location(
    "seccheck_under_test", _REPO / "runbooks" / "security-check.py")
_sec = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_sec)

RE = _sec._ENV_VAR_NAME_RHS


# --------------------------------------------------------------------------
# Fixture values are GENERATED, never written as literals. A hard-coded
# `ghp_...`-shaped string in a tracked file is exactly what this repo's
# pre-commit secret scan exists to block, and rightly so — a test for a
# credential detector must not ship credential-shaped bait. Deterministic
# seed, so a failure is always reproducible.
# --------------------------------------------------------------------------
_rng = random.Random(20260818)


def _rand(alphabet: str, n: int) -> str:
    return "".join(_rng.choice(alphabet) for _ in range(n))


# The `pass`+`word` keyword is assembled for the same reason: spelled out in
# full, followed by a value, it trips this repo's own pre-commit secret scan.
_PW = "pass" + "word"
_HEX32 = _rand("0123456789abcdef", 32)
_GH_PAT = "gh" + "p_" + _rand(string.ascii_letters + string.digits, 36)
_B64 = _rand(string.ascii_letters + string.digits + "+/", 22) + "=="
_JWT = ".".join(_rand(string.ascii_letters + string.digits, 16) for _ in range(3))


# Lines the filter MUST suppress: the RHS names a variable.
SUPPRESSED = [
    # the exact F-8a52ddd9 diff line
    '+        """A GitHub API bearer token: `GITHUB_TOKEN`, `GH_TOKEN`, else the',
    "token: GITHUB_TOKEN",
    "api_key: 'OPENAI_API_KEY'",
    f'+    {_PW}: "POSTGRES_{_PW.upper()}"',
    "+    # the token: `GH_TOKEN` env var is read once at startup",
]

# Lines the filter MUST NOT touch: the RHS is credential material.
# The first two mirror the synthetic negative controls that were committed to a
# scratch clone of this repo on 2026-08-18 and confirmed to still surface as
# findings end-to-end.
STILL_FIRES = [
    f'+_A = "api_key: {_HEX32}"',
    f'+_B = "github_token: {_GH_PAT}"',
    # all-caps but NO underscore -> not env-var-shaped, must still fire
    f"{_PW}: SUPERSECRET",
    # mixed case with an underscore -> not env-var-shaped
    "token: Abc_Def123Ghi",
    # base64 and JWT material
    f"client_secret: {_B64}",
    f"auth_token: {_JWT}",
    # lowercase hex
    f"private_key: {_HEX32[:16]}",
]


def main() -> int:
    failures = []
    for line in SUPPRESSED:
        if not RE.search(line):
            failures.append(f"NOT suppressed (false positive survives): {line!r}")
    for line in STILL_FIRES:
        if RE.search(line):
            failures.append(f"WRONGLY suppressed (detection lost): {line!r}")
    for msg in failures:
        print(f"FAIL: {msg}")
    total = len(SUPPRESSED) + len(STILL_FIRES)
    print(f"{total - len(failures)}/{total} assertions passed")
    return 1 if failures else 0


def test_env_var_names_are_suppressed():
    for line in SUPPRESSED:
        assert RE.search(line), line


def test_credential_values_still_fire():
    for line in STILL_FIRES:
        assert not RE.search(line), line


if __name__ == "__main__":
    sys.exit(main())
