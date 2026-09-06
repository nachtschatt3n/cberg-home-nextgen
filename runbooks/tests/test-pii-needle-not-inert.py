"""Regression test: the PII scan must never go quietly inert.

GROUND TRUTH (F-13354b57). `git config user.email` in this checkout is a BARE
HANDLE with no "@". The EMAIL needle was derived from it and guarded by a
shape check -- a correct guard, added because fixed-string scanning a bare
handle matched legitimate reverse-DNS launchd labels (com.<handle>.*) as an
email leak.

But the guard set the needle to "" and section 2A then `continue`d. It printed
NOTHING for email: not a hit, not a green line. Operator PII subsequently
reached public git history with no check watching. Fixing a false positive had
manufactured a false negative -- the third time that trade has been made in
this repo.

So this file pins the property, not the implementation: a needle that cannot be
derived must SAY the scan did not run.

Run:  python3 runbooks/tests/test-pii-needle-not-inert.py
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("sc", REPO / "runbooks/security-check.py")
sc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sc)

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


def main() -> int:
    print("PII needle:")

    email = sc._dominant_author_email()

    # The needle must EXIST here. If this fails, the email scan is inert again
    # and the whole point of the fix is gone.
    check("a needle is derived even though git config user.email is a bare handle",
          bool(email), "no needle -> the email scan is inert again")
    check("the derived needle is email-shaped",
          "@" in email and "." in email.rsplit("@", 1)[-1])

    # It must not be a bot address: those are in every repo's history and would
    # make the scan noisy-but-useless rather than absent-but-useless.
    check("noreply bot addresses are excluded",
          not email.endswith(("noreply.github.com", "users.noreply.github.com")),
          "a bot needle is not the identity at risk")

    # The needle is derived at RUNTIME from history. It must never be a literal
    # in the source, or this public repo would carry the very PII it scans for.
    src = (REPO / "runbooks/security-check.py").read_text()
    check("the needle is NOT hardcoded in the scanner source",
          email not in src,
          "a literal here would commit the PII the scan exists to find")

    # The absent-needle path must emit something. Asserted on the source
    # because the branch needs a fully-wired Findings run to reach, but the
    # assertion is specific enough to fail if someone restores a bare
    # `continue`.
    check("an unavailable needle is reported as UNMEASURED, not skipped",
          "scan did NOT run" in src and "UNMEASURED" in src,
          "a silent skip is what let PII reach public history")

    # Discrimination: the shape guard must still reject a bare handle, or the
    # original false positive returns.
    for bad in ("mathiasuhl", "com.example.agent", "", "no-at-sign", "a@b"):
        shaped = "@" in bad and "." in bad.rsplit("@", 1)[-1]
        check(f"bare/malformed value {bad!r} is not treated as an email needle",
              not shaped)

    print()
    if FAILURES:
        print(f"FAILED ({len(FAILURES)}): {', '.join(FAILURES)}")
        return 1
    print("all PII-needle tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
