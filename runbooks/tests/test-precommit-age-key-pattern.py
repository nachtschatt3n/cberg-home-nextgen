"""Regression test: the pre-commit hook detects a SOPS age PRIVATE key
(F-c1ca08f0, 2026-09-21).

The age key that decrypts every cluster secret lives at the repo root as
`age.key` (SOPS_AGE_KEY_FILE in .envrc / .mise.toml), inside a checkout of a
PUBLIC repository. It was protected only by a generic `*.key` line in
.gitignore, and Layer 3 of the pre-commit hook — which knows AWS keys, GitHub
tokens, JWTs and PEM private keys — had no pattern for it. So `git add -f
age.key` would have passed every layer.

NO KEY LITERAL LIVES IN THIS FILE. The positive fixture is assembled at run
time from the bech32 alphabet. Committing a real-shaped key to prove a detector
for real-shaped keys would be the defect, not the test.

THE CONTROL THAT MATTERS MOST is the last one. `age1...` PUBLIC recipients
appear in .sops.yaml and AGENTS.md and are committed on purpose. A pattern
loose enough to match those would block every ordinary commit — a fix that
breaks the repo is worse than the hole it closes.

The pattern is EXTRACTED FROM THE SHIPPED HOOK rather than restated here, so
deleting or weakening it in .githooks/pre-commit fails this test instead of
leaving a test that passes against its own copy.

Run:  python3 runbooks/tests/test-precommit-age-key-pattern.py
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
HOOK = _REPO / ".githooks" / "pre-commit"

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


def shipped_pattern() -> str | None:
    """The age-key ERE exactly as the hook ships it."""
    for line in HOOK.read_text().splitlines():
        if "AGE-SECRET-KEY" in line and "grep -qE" in line:
            m = re.search(r"grep -qE '([^']+)'", line)
            if m:
                return m.group(1)
    return None


def matches(pattern: str, text: str) -> bool:
    """Run the REAL grep the hook runs, not a Python re approximation."""
    return subprocess.run(["grep", "-qE", pattern],
                          input=text, text=True).returncode == 0


# bech32: no 1, B, I or O after the mandatory leading 1.
BECH32 = "023456789ACDEFGHJKLMNPQRSTUVWXYZ"


def synth_key(body_len: int = 58, alphabet: str = BECH32) -> str:
    """A correctly-SHAPED age secret key, built here, never stored."""
    body = (alphabet * ((body_len // len(alphabet)) + 1))[:body_len]
    return "AGE-SECRET-KEY-1" + body


def main() -> int:
    print(__doc__.strip().splitlines()[0])
    print()

    pat = shipped_pattern()
    check("the hook ships an age-key detector at all", pat is not None,
          "no `grep -qE` line mentioning AGE-SECRET-KEY in .githooks/pre-commit")
    if pat is None:
        print("\nFAILED: 1 -> detector absent")
        return 1
    print(f"  (pattern under test, from the hook: {pat})")
    print()

    # --- POSITIVE ------------------------------------------------------------
    check("a correctly-shaped age PRIVATE key is caught",
          matches(pat, synth_key()))
    check("...also when embedded in a line of YAML",
          matches(pat, f"  sops_age_key: {synth_key()}\n"))

    # --- NEGATIVE CONTROLS: without these the pattern could be `.` -----------
    check("control: a 57-character body is NOT matched (length is enforced)",
          not matches(pat, synth_key(57)))
    check("control: bech32-excluded characters are NOT matched",
          not matches(pat, "AGE-SECRET-KEY-1" + "B" * 58))
    check("control: ordinary prose is NOT matched",
          not matches(pat, "the age key is stored at the repo root as age.key\n"))

    # THE ONE THAT PROTECTS DAILY WORK: public recipients are committed on
    # purpose, in .sops.yaml and AGENTS.md.
    public_recipient = "age1nw624gkjpl0sattullahnekdswjcvsgarf8gwwyf9jdqc0zm9enqyp2pf6"
    check("control: a PUBLIC age recipient is NOT matched (else every commit "
          "touching .sops.yaml or AGENTS.md would be blocked)",
          not matches(pat, public_recipient))

    # --- THE REPO ITSELF MUST BE CLEAN --------------------------------------
    tracked = subprocess.run(
        ["git", "grep", "-IlE", pat, "--", "."],
        cwd=_REPO, capture_output=True, text=True).stdout.strip()
    check("no tracked file currently contains an age private key",
          tracked == "", f"matches in: {tracked!r}")

    # --- AND THE KEY MUST STAY IGNORED --------------------------------------
    ignored = subprocess.run(["git", "check-ignore", "age.key"],
                             cwd=_REPO, capture_output=True, text=True)
    check("age.key is git-ignored", ignored.returncode == 0)
    check("...by an EXPLICIT rule, not only the generic *.key glob",
          "\nage.key\n" in (_REPO / ".gitignore").read_text(),
          "a future narrowing of *.key would silently make the key committable")

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} -> {', '.join(FAILURES)}")
        return 1
    print("all tests passed")
    return 0


def test_pytest_entry() -> None:
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())
