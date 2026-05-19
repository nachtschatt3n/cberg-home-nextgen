#!/usr/bin/env python3
"""
Health-check JSON wrapper around runbooks/health-check.sh.

Runs the bash health-check end-to-end (which still owns the
markdown snapshot at runbooks/health-check-current.md) and, when a
--postgres-dsn is provided, also parses the issues summary file at
/tmp/health-check-issues-<timestamp>.txt and emits findings to the
sweep-history Postgres.

Usage:
    python3 runbooks/health-check.py
    python3 runbooks/health-check.py --postgres-dsn "$WRITER_DSN"
    SWEEP_PG_DSN=... SWEEP_CYCLE_ID=... python3 runbooks/health-check.py

Exit code mirrors the bash script (non-zero on critical issues).
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT  = SCRIPT_DIR.parent
BASH_SCRIPT = SCRIPT_DIR / "health-check.sh"

sys.path.insert(0, str(SCRIPT_DIR))
from lib.findings_writer import (  # noqa: E402
    FindingsWriter, cycle_id_from_env, trigger_from_env, git_head,
)

# Severity mapping from the issues file. The bash script uses 🔴/🟡/🔵 not
# the 🟢-and-friends scheme of the other audit scripts — translate inline.
_SEVERITY = {
    "🔴": "critical",
    "🟡": "warning",
    "🔵": "monitor",
}

# Subsection slugs derived from issue text — when the message starts with a
# recognised prefix we tag it for richer queries. Otherwise fall back to
# "general".
_SUBSECTION_PREFIXES: list[tuple[str, str]] = [
    ("HA: ",                       "home_assistant"),
    ("HA overall health",          "home_assistant"),
    ("High Home Assistant error",  "home_assistant"),
    ("UniFi",                      "unifi"),
    ("icloud-docker-mu",           "icloud_docker"),
    ("Frigate",                    "frigate"),
    ("Failed jobs",                "kubernetes_jobs"),
    ("Services without endpoints", "kubernetes_services"),
    ("Longhorn",                   "longhorn"),
    ("Talos",                      "talos"),
    ("Flux",                       "flux"),
]


def _subsection_for(msg: str) -> str:
    for prefix, slug in _SUBSECTION_PREFIXES:
        if msg.startswith(prefix):
            return slug
    return "general"


def _newest_issues_file() -> Path | None:
    """Return the most recent /tmp/health-check-issues-*.txt, or None."""
    candidates = sorted(
        glob.glob("/tmp/health-check-issues-*.txt"),
        key=lambda p: os.path.getmtime(p),
        reverse=True,
    )
    return Path(candidates[0]) if candidates else None


_SECTION_RE = re.compile(
    r"^(?P<emoji>[🔴🟡🔵])\s+(?P<label>CRITICAL|MAJOR|MINOR)\s+ISSUES\s+\((?P<count>\d+)\):"
)


def parse_issues(path: Path) -> list[tuple[str, str]]:
    """Parse the issues summary file. Returns [(severity, message), ...]."""
    findings: list[tuple[str, str]] = []
    current_emoji: str | None = None

    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.rstrip()
        m = _SECTION_RE.match(line)
        if m:
            current_emoji = m.group("emoji")
            continue
        if line.startswith("=") or not line.strip():
            current_emoji = None
            continue
        if current_emoji is None:
            continue
        # Issue line shape: `  - <message>` (with possible right-trim spaces)
        if line.lstrip().startswith("- "):
            msg = line.lstrip()[2:].strip()
            # Skip the "None - Excellent!" placeholder
            if msg.lower().startswith("none"):
                continue
            sev = _SEVERITY.get(current_emoji)
            if sev is None:
                continue
            findings.append((sev, msg))
    return findings


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Cluster health check (wraps health-check.sh).",
    )
    parser.add_argument(
        "--postgres-dsn",
        default=os.environ.get("SWEEP_PG_DSN"),
        help=(
            "Postgres DSN for sweep-history. If unset and SWEEP_PG_DSN env "
            "var is also unset, findings are written to markdown only."
        ),
    )
    parser.add_argument(
        "--issues-file",
        default=None,
        help=(
            "Path to a pre-existing issues summary file to parse instead of "
            "running health-check.sh. Useful for testing the parser."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    if args.issues_file:
        issues_path = Path(args.issues_file)
        exit_code = 0
    else:
        if not BASH_SCRIPT.is_file():
            print(f"ERROR: {BASH_SCRIPT} not found", file=sys.stderr)
            return 2
        # Run the bash script with its output streaming to our stdout.
        proc = subprocess.run(["bash", str(BASH_SCRIPT)], check=False)
        exit_code = proc.returncode
        issues_path = _newest_issues_file()

    findings: list[tuple[str, str]] = []
    if issues_path and issues_path.is_file():
        findings = parse_issues(issues_path)
        print(f"\nParsed {len(findings)} finding(s) from {issues_path}")
    else:
        print("\nNo issues file found — skipping findings parse.")

    crit = sum(1 for s, _ in findings if s == "critical")
    warn = sum(1 for s, _ in findings if s == "warning")
    verdict = "red" if crit > 0 else ("yellow" if warn > 0 else "green")

    if args.postgres_dsn:
        print(f"Sweep-history Postgres: enabled (cycle={cycle_id_from_env('<new>')})")

    with FindingsWriter(
        dsn=args.postgres_dsn,
        section="health",
        cycle_id=cycle_id_from_env(),
        trigger=trigger_from_env(),
        git_head=git_head(),
    ) as writer:
        evidence_path = str(issues_path) if issues_path else None
        if writer.enabled:
            for sev, msg in findings:
                writer.emit(
                    severity=sev,
                    title=msg,
                    subsection=_subsection_for(msg),
                    evidence_path=evidence_path,
                )
        writer.close(verdict=verdict)

    return exit_code if exit_code else (1 if crit > 0 else 0)


if __name__ == "__main__":
    sys.exit(main())
