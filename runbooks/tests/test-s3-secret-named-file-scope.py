#!/usr/bin/env python3
"""Pin the scope of s3_git_history's "Secret-named files" rule (F-96b71f86).

That rule greps COMMITTED FILENAMES for secret/password/credential/private.key
and never inspects content, so a file named after the thing it detects trips it
on its own name. The repo's own Layer-3 pre-commit credential guard did exactly
that.

The fix excludes two literal paths. The danger in any such narrowing is that it
blinds the detector -- the failure mode recorded in the operator's
`feedback_fp_fix_can_blind_detector` note -- so BOTH directions are pinned here,
and each assertion carries a control that fails if the test itself goes vacuous.

Run directly:  python3 runbooks/tests/test-s3-secret-named-file-scope.py
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SECURITY_CHECK = ROOT / "runbooks" / "security-check.py"

EXCLUDED = (
    ".githooks/lib/password-guard.awk",
    "docs/sops/pre-commit-secret-scan.md",
    # This file. The rule matches FILENAMES, so the regression test that pins
    # its scope trips it on its own name (F-afd39842, raised 2026-09-21 — the
    # test was added 2026-09-20 and immediately became an instance of the very
    # false positive it documents). Excluded by literal path like the other
    # two: a `runbooks/tests/*` glob would hide a genuine secret-named file
    # committed anywhere under that directory.
    "runbooks/tests/test-s3-secret-named-file-scope.py",
)

passed = failed = 0


def check(label, got, want):
    global passed, failed
    if got == want:
        passed += 1
        print(f"  PASS  {label}")
    else:
        failed += 1
        print(f"  FAIL  {label}\n          got={got!r} want={want!r}")


def _scan(exclusions: bool) -> set[str]:
    """Run the real filename scan, with or without the exclusion pathspecs."""
    excl = ""
    if exclusions:
        excl = "".join(f" ':(exclude){p}'" for p in EXCLUDED)
    cmd = (
        "git log --all --diff-filter=A --name-only --pretty=format: "
        f"-- .{excl} "
        "| grep -i 'secret\\|password\\|credential\\|private.key' "
        "| grep -v '\\.sops\\.yaml$' | sort -u"
    )
    out = subprocess.run(
        ["bash", "-c", cmd], cwd=ROOT, capture_output=True, text=True
    ).stdout
    return {line.strip() for line in out.splitlines() if line.strip()}


print("s3 secret-named-file scope")

without = _scan(exclusions=False)
with_ = _scan(exclusions=True)

# --- CONTROL: the unexcluded scan must actually see the guard file. ----------
# Without this, every assertion below would pass trivially if the git query
# broke, the file were renamed, or grep silently matched nothing -- the
# false-zero class that has bitten this repo repeatedly on BSD tooling.
check(
    "control: the UNEXCLUDED scan really does flag the guard file "
    "(else this whole test is vacuous)",
    ".githooks/lib/password-guard.awk" in without,
    True,
)
check(
    "control: the unexcluded scan returns a non-trivial number of paths",
    len(without) >= 10,
    True,
)

# --- Direction 1: the two detector sources are no longer reported. -----------
for path in EXCLUDED:
    check(f"excluded from the scan: {path}", path in with_, False)

# --- Direction 2: the narrowing removed ONLY those two. ----------------------
# This is the anti-blinding assertion. If someone widens the exclusion to a
# glob such as `.githooks/*` or `docs/sops/*`, this fails.
check(
    "the exclusion removed EXACTLY the named paths and nothing else",
    without - with_,
    set(EXCLUDED),
)

# --- Direction 3: genuine secret-named files are still reported. -------------
real_secret_files = {
    p for p in with_
    if re.search(r"(^|/)(secret|secrets|credentials?)[^/]*\.ya?ml$", p)
}
check(
    "genuine secret-named manifests are STILL flagged "
    f"(found {len(real_secret_files)})",
    len(real_secret_files) >= 5,
    True,
)

# --- Direction 4: the source actually carries the pathspecs. -----------------
# Guards against the exclusions being reverted in code while this test keeps
# passing off its own locally-built command string.
src = SECURITY_CHECK.read_text()
for path in EXCLUDED:
    check(
        f"security-check.py itself carries the exclusion for {path}",
        f"':(exclude){path}'" in src,
        True,
    )

# --- Direction 5: the exclusion must not be a directory glob. ---------------
check(
    "no directory-glob exclusion was introduced into this rule "
    "(a glob makes a real secret invisible by location)",
    bool(re.search(r"':\(exclude\)[^']*\*", src.split("secret_files = run_lines")[1][:600]))
    if "secret_files = run_lines" in src else True,
    False,
)

print(f"\n  {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
