#!/usr/bin/env python3
"""Regression test: the SOPS coverage section must report denominators
(F-0823fdc3, 2026-09-22).

s1_sops_coverage runs three scans — plaintext `kind: Secret` manifests, SOPS
`.decrypted~` temp files, suspicious inline base64 — and each one printed a
bare result:

    🟢 No unencrypted Secret manifests
    🟢 No SOPS temp files
    🟢 No suspicious base64 outside sops files

That is the one answer a BROKEN scan also gives. A grep whose tree moved, whose
pattern rotted, or whose binary is missing produces an empty list, and an empty
list renders as the all-clear. The section that certifies this public repo has
no plaintext secrets was therefore indistinguishable, at a glance and in the
committed report, from a section that looked at nothing at all — the exact
"zero without a control" class catalogued in docs/sops/audit-script-
correctness.md.

The fix states the population each scan covered, and raises a BLINDNESS warning
when that population is empty. The blindness cases below are the real assertion:
a denominator you never check is just decoration.

These tests call s1_sops_coverage() itself rather than re-deriving the greps.
Hand-built stand-ins for a repo's own reader have returned plausible wrong
answers here before.

Run:  python3 runbooks/tests/test-sops-coverage-denominator.py
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import re
import sys
import types
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
os.environ.setdefault("_MISE_ACTIVATED", "1")
os.chdir(_REPO)
sys.argv = ["security-check.py"]

_SC_SRC = _REPO / "runbooks" / "security-check.py"
_spec = importlib.util.spec_from_file_location("sc", _SC_SRC)
sc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sc)

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


def run_section(mod=sc, blind=False):
    """Call the real s1_sops_coverage(). Returns (worst, findings, markdown, stdout).

    `blind=True` starves every scan of input — the shape a broken grep, a moved
    tree or a missing binary produces.
    """
    mod = mod or sc
    orig_lines, orig_run, orig_isdir = mod.run_lines, mod.run, os.path.isdir
    try:
        if blind:
            mod.run_lines = lambda cmd, timeout=30: []
            mod.run = lambda cmd, timeout=30: ""
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            worst, f, md = mod.s1_sops_coverage()
        return worst, f, md, buf.getvalue()
    finally:
        mod.run_lines, mod.run = orig_lines, orig_run
        os.path.isdir = orig_isdir


def ints(text: str) -> list[int]:
    return [int(n) for n in re.findall(r"\d+", text)]


def prefix_module():
    """The PRE-FIX module: the same source with BOTH halves of the fix reverted
    — the three reported denominators, and the three blindness guards that give
    an empty population its meaning.

    Text surgery on the real file, so the straw tracks the implementation
    instead of drifting into a hand-written imitation. Every edit below is
    asserted to have matched, because a surgery that silently no-ops produces a
    straw that passes for the wrong reason.
    """
    src = _SC_SRC.read_text()

    # 1. Drop the denominator lines from the markdown report.
    out, removed = [], 0
    for line in src.splitlines(keepends=True):
        if re.match(r'\s*lines\.append\(f"\*\*(Secret manifests|SOPS temp-file '
                    r'scan|Inline-base64 scan):\*\*', line):
            removed += 1
            continue
        out.append(line)
    if removed != 3:
        raise AssertionError(
            f"commissioning straw is broken: expected to revert 3 denominator "
            f"lines, found {removed} — re-derive it before trusting this suite")
    src = "".join(out)

    # 2. Neutralise the blindness guards and restore the unconditional `else:`
    #    that used to print the all-clear for an empty result.
    reverts = [
        ("    if not secret_manifests:\n", "    if False:\n"),
        ("    if not temp_roots or not temp_scanned:\n", "    if False:\n"),
        ("    if not b64_hits:\n", "    if False:\n"),
        ("    elif secret_manifests:\n", "    else:\n"),
        ("    elif temp_scanned:\n", "    else:\n"),
        ("    elif b64_hits:\n", "    else:\n"),
    ]
    for needle, replacement in reverts:
        if src.count(needle) != 1:
            raise AssertionError(
                f"commissioning straw is broken: {needle.strip()!r} appears "
                f"{src.count(needle)} times in security-check.py, expected 1")
        src = src.replace(needle, replacement, 1)

    mod = types.ModuleType("sc_prefix")
    mod.__file__ = str(_SC_SRC)
    exec(compile(src, str(_SC_SRC), "exec"), mod.__dict__)
    return mod


SCOPES = ("Secret manifests", "SOPS temp-file scan", "Inline-base64 scan")


def main() -> int:
    print(__doc__.strip().splitlines()[0])
    print()

    # --- THE DEFECT: every scan must state what it covered ------------------
    worst, f, md, out = run_section()
    for label in SCOPES:
        check(f"the report states a denominator for `{label}`",
              f"**{label}:**" in md, f"markdown was {md[:200]!r}")

    secret_line = next((l for l in md.splitlines() if "**Secret manifests:**" in l), "")
    nums = ints(secret_line)
    check("the Secret-manifest denominator is a real, non-zero population",
          len(nums) >= 3 and nums[0] > 0, f"got {secret_line!r}")
    check("...and encrypted + plaintext accounts for the whole population",
          len(nums) >= 3 and nums[1] + nums[2] == nums[0], f"got {secret_line!r}")

    temp_line = next((l for l in md.splitlines() if "**SOPS temp-file scan:**" in l), "")
    check("the temp-file scan states how many files it walked",
          bool(ints(temp_line)) and ints(temp_line)[0] > 0, f"got {temp_line!r}")

    b64_line = next((l for l in md.splitlines() if "**Inline-base64 scan:**" in l), "")
    check("the base64 scan states how many candidate lines it judged",
          bool(ints(b64_line)) and ints(b64_line)[0] > 0, f"got {b64_line!r}")

    check("the green console lines carry their counts too",
          "No unencrypted Secret manifests (" in out
          and "No SOPS temp files (" in out
          and "No suspicious base64 outside sops files (" in out,
          f"stdout was {out!r}")

    check("a healthy repo still scores this section clean",
          worst == sc.OK, f"got {worst!r}")

    # --- THE POINT OF A DENOMINATOR: nothing-scanned must not read clean ----
    b_worst, b_f, b_md, b_out = run_section(blind=True)
    blind_msgs = [m for _s, m, _meta in b_f._items if "BLIND" in m]
    check("a scan that saw NOTHING raises blindness findings, not a green",
          len(blind_msgs) == 3, f"got {blind_msgs!r}")
    check("...and the section no longer scores clean",
          b_worst != sc.OK, f"got {b_worst!r}")
    check("...and prints no all-clear line",
          "🟢" not in b_out, f"stdout was {b_out!r}")
    for label in SCOPES:
        check(f"...and still states the (empty) scope for `{label}`",
              f"**{label}:**" in b_md)

    # --- COMMISSIONING STRAW ------------------------------------------------
    old = prefix_module()
    _w, _f, old_md, old_out = run_section(old)
    check("commissioning: with the denominators reverted, the central assertion "
          "'the report states a denominator' FAILS",
          not any(f"**{label}:**" in old_md for label in SCOPES),
          f"got {old_md[:200]!r}")

    # And the blindness half of the straw: the pre-fix section reports a clean
    # green when it scanned nothing at all. That is the defect, reproduced.
    ob_worst, ob_f, _ob_md, ob_out = run_section(old, blind=True)
    check("commissioning: the PRE-FIX section scores a scan of NOTHING as clean",
          ob_worst == old.OK and not [m for _s, m, _x in ob_f._items if "BLIND" in m],
          f"worst={ob_worst!r} items={ob_f._items!r}")
    check("commissioning: ...and prints the all-clear while blind",
          "🟢" in ob_out)

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
