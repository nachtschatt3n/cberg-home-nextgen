#!/usr/bin/env python3
"""Pre-commit layer 4 — vulnerability-disclosure boundary over STAGED ADDED LINES.

The commit-msg hook has enforced this policy on commit MESSAGES since it was
written, and explicitly strips the diff below the `git commit -v` scissors line
— so added lines were out of scope by design. Nothing checked them. On
2026-08-18 the same test-fixture defect (a real deployed image paired with a
non-zero finding count) shipped twice in one evening, in a file whose own
README states the rule, and was caught both times by a human-run audit rather
than by tooling. This closes that gap with the same pattern library the
commit-msg hook uses.

Scope note: this scans ADDED lines only. Pre-existing violations in a file you
are editing are not your commit's problem, and flagging them would make the
hook unfixable-by-design on legacy files.

WARN-ONLY, deliberately — it always exits 0. Measured over the whole tracked
tree, the tuned patterns still flag 73 lines, and the residual is dominated by
fixtures that are already CORRECT under the policy: a synthetic component
(`example-org/widget`) paired with a count is exactly the remediation we ask
for, and the regex cannot tell it from a real one. A gate that blocks the fix
is worse than no gate. It also cannot distinguish prose ABOUT the policy from a
disclosure.

So this raises the thing a human should look at, and leaves the judgement with
them. Both 2026-08-18 breaches were obvious on sight — the failure was that
nothing put them in front of anyone's eyes.

Promotion path to blocking: run warn-only until the observed false-positive
rate on ADDED lines is near zero, tighten the patterns (or teach them a
synthetic-component allowlist) using what shows up, then flip `return 0` at the
end of main() to `return 1`. Do not flip it on the strength of this file's
current tuning.
"""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

HOOKS = Path(__file__).resolve().parent.parent

# Files that legitimately CONTAIN the vocabulary because they define, document,
# or test the boundary itself. Excluding them is not a loophole — a scanner
# cannot be written in a repo that forbids naming what it scans for. Anything
# here must be reviewed by a human on change; that is the trade.
SELF_REFERENTIAL = (
    ".githooks/",                                   # these hooks
    "docs/sops/vulnerability-disclosure.md",        # the policy itself
    "runbooks/security-check.py",                   # the scanner
    "runbooks/check-all-versions.py",               # the version/CVE oracle
    "runbooks/doc-check.py",
    "runbooks/lib/risk_model.py",                   # severity vocabulary
    "runbooks/security-check.md",
    "runbooks/version-check.md",
    "runbooks/maintenance/plans/README.md",         # explains the boundary
    # Agent-instruction files: they QUOTE the policy ("vulnerability counts,
    # exploitability notes … must NOT be committed"), which trips the
    # exploitability rule on the sentence that forbids exploitability detail.
    "AGENTS.md", "CLAUDE.md", "CODEX.md", "GEMINI.md",
    ".opencode/", ".codex/", ".claude/",
)
# Generated snapshots — gitignored, but belt-and-braces if one is ever forced.
GENERATED = re.compile(r"runbooks/[\w-]+-current\.md$")
# Vendored upstream CRDs and charts: their API docs cite upstream CVEs that are
# neither ours nor unfixed-on-our-fleet. We do not author these files.
VENDORED = re.compile(r"(^|/)(crds|charts|vendor)/")


def _skip(path: str) -> bool:
    return (path.startswith(SELF_REFERENTIAL)
            or bool(GENERATED.search(path))
            or bool(VENDORED.search(path)))


# Scanner INVOCATIONS are not disclosures. `--severity CRITICAL`,
# `--ignore-unfixed`, `severity=HIGH` are how you ASK the question; they say
# nothing about the answer. Stripped before matching so a runbook can document
# the command that produces the detail without leaking the detail.
TOOLING_NOISE = re.compile(
    r"--[a-z][a-z-]*(?:[= ](?:CRITICAL|HIGH|MEDIUM|LOW)(?:,(?:CRITICAL|HIGH|MEDIUM|LOW))*)?"
    r"|\bseverity\s*[=:]\s*[\"\']?(?:critical|high|medium|low)"
    r"|\b(?:ignore|include)[-_]unfixed\b",
    re.IGNORECASE,
)


def _load():
    spec = importlib.util.spec_from_file_location(
        "disclosure_patterns", str(HOOKS / "lib" / "disclosure_patterns.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _staged_added() -> dict[str, list[tuple[int, str]]]:
    """{path: [(lineno, added_line), ...]} from the staged diff."""
    out = subprocess.run(
        ["git", "diff", "--cached", "-U0", "--no-color", "--diff-filter=ACMR"],
        capture_output=True, text=True, errors="replace").stdout
    files: dict[str, list[tuple[int, str]]] = {}
    path, lineno = None, 0
    for raw in out.splitlines():
        if raw.startswith("+++ b/"):
            path = raw[6:]
            continue
        if raw.startswith("@@"):
            m = re.search(r"\+(\d+)", raw)
            lineno = int(m.group(1)) if m else 0
            continue
        if path and raw.startswith("+") and not raw.startswith("+++"):
            files.setdefault(path, []).append((lineno, raw[1:]))
            lineno += 1
    return files


def main() -> int:
    try:
        dp = _load()
    except Exception as e:  # noqa: BLE001
        print(f"  \033[1;33m⚠  disclosure scan skipped ({type(e).__name__})\033[0m")
        return 0

    violations = []
    for path, lines in _staged_added().items():
        if _skip(path):
            continue
        for lineno, text in lines:
            if dp.SECURITY_REF_LINE.match(text):
                continue
            # Per LINE here, unlike the commit-msg hook: source and docs are not
            # hard-wrapped mid-sentence the way a commit body is, and joining a
            # whole file would manufacture matches across unrelated lines.
            norm = re.sub(r"\s+", " ", TOOLING_NOISE.sub(" ", text)).strip()
            if not norm:
                continue
            for excerpt, matched, label in dp.scan(norm):
                violations.append((path, lineno, matched, label, norm))
                break

    if not violations:
        return 0

    R, Y, D, N = "\033[0;31m", "\033[1;33m", "\033[2m", "\033[0m"
    print("")
    print(f"{Y}╔══════════════════════════════════════════════════════════════════╗{N}")
    print(f"{Y}║  REVIEW — possible vulnerability disclosure in added lines       ║{N}")
    print(f"{Y}╚══════════════════════════════════════════════════════════════════╝{N}")
    print("")
    print(f"  Policy: {Y}docs/sops/vulnerability-disclosure.md{N}")
    print(f"  {D}Not blocking — this hook warns only. Judge it yourself.{N}")
    print("")
    print("  This repository is PUBLIC. A committed FILE must not state")
    print("  currently-unfixed vulnerability state on a SPECIFIC service we")
    print("  run — test fixtures, comments and docs included. A SYNTHETIC")
    print("  component with a count is fine and will still show up here.")
    print("")
    for path, lineno, matched, label, text in violations[:10]:
        snippet = text if len(text) <= 96 else text[:95] + "…"
        print(f"  {R}{path}:{lineno}{N}")
        print(f"    {D}{snippet}{N}")
        print(f"    {R}^ matched '{matched}' — {label}{N}")
        print("")
    if len(violations) > 10:
        print(f"  {D}… and {len(violations) - 10} more{N}")
        print("")
    print(f"  {chr(27)}[0;32mHow to fix:{N}")
    print("")
    print("    1. In a FIXTURE: use a synthetic component and drop the count.")
    print("       The assertions almost never depend on the real values.")
    print("    2. In a DOC or comment: describe the mechanism, not the counts,")
    print(f"       and point at the record — {D}security_ref: F-xxxxxxxx{N}")
    print("    3. Real detail belongs on the finding, never in git:")
    print(f"       {D}runbooks/policy-cli.py finding detail F-xxxxxxxx{N}")
    print("")
    print(f"  {D}Synthetic fixture or prose about the policy? Then it is fine —{N}")
    print(f"  {D}this hook cannot tell those apart, which is why it does not block.{N}")
    print("")
    return 0  # WARN-ONLY. See the module docstring before changing this.


if __name__ == "__main__":
    sys.exit(main())
