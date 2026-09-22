#!/usr/bin/env python3
"""Regression test: the GHCR token exchange for OUR OWN namespace carries the
GitHub credential, so a PRIVATE self-built package lists its tags
(F-4677123a, the tractable half).

`_oci_v2_tags()` follows the registry's WWW-Authenticate challenge to the
token endpoint. That exchange succeeds anonymously for every package on
ghcr.io but only UNLOCKS the public ones: a private package answers the
anonymous bearer with 401/403, the listing returns None, and the version
report prints "Could not determine" — for our own images, where a rebuild is
the one remedy this household performs. Measured 2026-09-22: three
semver-tagged self-built images, anonymous listing 401 on all three, one
resolved (public), two did not; with the `gh` token on the exchange all
three list. The exchange now sends `auth=(username, token)` for ghcr.io when
`_github_api_token()` resolves one, and stays anonymous otherwise.

Hermetic: the module's `_get_retry_429` (every registry GET goes through it)
is replaced by a scripted registry; the checker's token is set directly.

Run:  python3 runbooks/tests/test-ghcr-authenticated-tags.py
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
os.environ.setdefault("_MISE_ACTIVATED", "1")
sys.path.insert(0, str(_REPO / "runbooks"))

_spec = importlib.util.spec_from_file_location("cberg_versions_ghcr_t",
                                               _REPO / "runbooks" / "check-all-versions.py")
cav = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cav)  # type: ignore

FAILURES: list[str] = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {str(detail)[:300]}"))
    if not ok:
        FAILURES.append(name)


def count_matches(population: str, pattern: str) -> int:
    """Guarded counter: an empty population or an error marker aborts the run
    instead of returning a silent zero."""
    if not population or not population.strip():
        raise SystemExit(f"count_matches: EMPTY population for {pattern!r}")
    for marker in ("usage:", "Traceback", "error"):
        if marker in population:
            raise SystemExit(f"count_matches: population carries {marker!r}: "
                             f"{population[:200]!r}")
    return len(re.findall(pattern, population))


class _Resp:
    def __init__(self, status, body=None, headers=None):
        self.status_code, self._body, self.headers = status, body or {}, headers or {}

    def json(self):
        return self._body


class ScriptedRegistry:
    """A private package on ghcr.io and a package on another registry.

    Rules, mirroring what was measured live:
      * tags/list without a bearer -> 401 + the Bearer challenge;
      * the token endpoint answers 200 either way, but the token it hands out
        depends on whether credentials came with the request;
      * tags/list with the CREDENTIALED bearer -> 200 + tags; with the
        anonymous bearer -> 403 (private package).
    """

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, sess, url, **kwargs):
        self.calls.append((url, kwargs))
        host = url.split("/")[2]
        if url.endswith("/token") or "/token?" in url:
            tok = "CREDENTIALED" if kwargs.get("auth") else "ANONYMOUS"
            return _Resp(200, {"token": tok})
        bearer = (kwargs.get("headers") or {}).get("Authorization", "")
        if not bearer:
            return _Resp(401, headers={"WWW-Authenticate":
                                       f'Bearer realm="https://{host}/token",service="{host}",'
                                       f'scope="repository:example-org/widget:pull"'})
        if bearer == "Bearer CREDENTIALED":
            return _Resp(200, {"tags": ["0.1.0", "0.1.1", "sha-abc1234"]}, headers={"Link": ""})
        return _Resp(403, {"errors": [{"code": "DENIED"}]})


def fresh_checker(token):
    ck = cav.VersionChecker(str(_REPO))
    ck._gh_api_token = token          # bypass GITHUB_TOKEN / `gh auth token`
    return ck


def list_tags(ck, host, reg):
    saved = cav._get_retry_429
    cav._STRUCTURALLY_SLOW_HOSTS.discard(host)
    try:
        cav._get_retry_429 = reg
        return ck._oci_v2_tags(host, "example-org/widget")
    finally:
        cav._get_retry_429 = saved


def main() -> int:
    print(__doc__.strip().splitlines()[0])
    print()

    reg = ScriptedRegistry()
    tags = list_tags(fresh_checker("TESTTOKEN"), "ghcr.io", reg)
    check("a PRIVATE ghcr.io package lists its tags when a GitHub token resolves",
          tags is not None and count_matches("\n".join(tags), r"(?m)^\d+\.\d+\.\d+$") == 2, tags)
    tok_calls = [kw for url, kw in reg.calls if "/token" in url]
    check("...because the token exchange carried the credential as HTTP basic auth",
          len(tok_calls) == 1 and tok_calls[0].get("auth")
          and tok_calls[0]["auth"][1] == "TESTTOKEN", tok_calls)
    check("...with the trivy username convention (TRIVY_USERNAME, else a placeholder)",
          tok_calls and tok_calls[0]["auth"][0] == (os.environ.get("TRIVY_USERNAME") or "token"),
          tok_calls)

    reg = ScriptedRegistry()
    tags = list_tags(fresh_checker("TESTTOKEN"), "registry.example.net", reg)
    tok_calls = [kw for url, kw in reg.calls if "/token" in url]
    check("another registry's token endpoint never receives the GitHub credential",
          len(tok_calls) == 1 and "auth" not in tok_calls[0], tok_calls)
    check("...so that (private) package stays unresolved exactly as before", tags is None, tags)

    reg = ScriptedRegistry()
    tags = list_tags(fresh_checker(None), "ghcr.io", reg)
    tok_calls = [kw for url, kw in reg.calls if "/token" in url]
    check("no token resolved -> the exchange stays ANONYMOUS (unchanged behaviour)",
          len(tok_calls) == 1 and "auth" not in tok_calls[0], tok_calls)
    check("...and the private package is None, never a guessed tag", tags is None, tags)

    # ── COMMISSIONING STRAW: revert the fix, the first assertion must fail ──
    reg = ScriptedRegistry()
    ck = fresh_checker("TESTTOKEN")
    ck._github_api_token = lambda: None     # pre-fix: the exchange never consulted the token
    straw = list_tags(ck, "ghcr.io", reg)
    check("STRAW: with the credential path reverted the SAME private package reads None — "
          "the listing assertion fails against pre-fix code", straw is None, straw)

    print()
    print("FAILED: " + ", ".join(FAILURES) if FAILURES else "all tests passed")
    return 1 if FAILURES else 0


def test_pytest_entry():
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())
