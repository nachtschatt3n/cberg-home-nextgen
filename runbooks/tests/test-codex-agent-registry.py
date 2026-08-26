"""Regression tests for the .codex agent registry.

This exists because the registry silently rotted in three separate ways at once,
and none of them were visible from a passing build:

  * `.codex/config.toml` pointed every `config_file` at `/home/mu/code/...` — a
    Linux path. On the Mac that actually runs these agents (`/Users/mu`) not one
    of them resolved, so a clean checkout produced agents that could not load
    their own definitions.
  * It registered 4 agents while 7 definition files were committed. daily-operation,
    maintenance-window-agent and upgrade-planner-agent existed and were unreachable.
  * A rename bringing `.codex` to parity with `.claude/agents/` was left 90% done
    and uncommitted for a week: 8 new `*-agent.toml` on disk, 4 superseded
    originals still present, config still pointing at the old names.

Every one of those is the same shape — a registry nobody verified against the
filesystem. So this verifies it.

Run:  python3 runbooks/tests/test-codex-agent-registry.py
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CODEX = REPO / ".codex"
CLAUDE_AGENTS = REPO / ".claude/agents"

# .claude agents with no .codex counterpart, deliberately. Listed so the gap is
# visible and reviewed rather than silently absent — if you add one to .codex,
# delete it from here and the parity assertion starts covering it.
KNOWN_CODEX_GAPS = {
    "alert-triage-agent",   # driven by the main session's Monitor ws watcher,
                            # which has no codex equivalent (runbooks/alert-watcher.md)
}

FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}  {detail}")
        FAILURES.append(name)


def main() -> int:
    print("test-codex-agent-registry")

    cfg_path = CODEX / "config.toml"
    check("config.toml exists", cfg_path.is_file(), str(cfg_path))
    if not cfg_path.is_file():
        return 1

    try:
        cfg = tomllib.loads(cfg_path.read_text())
        parsed = True
    except Exception as e:  # noqa: BLE001
        cfg, parsed = {}, False
        check("config.toml parses", False, repr(e))
    if not parsed:
        return 1
    check("config.toml parses", True)

    agents = cfg.get("agents", {})
    check("at least one agent registered", bool(agents), f"{len(agents)} found")

    on_disk = {p.stem: p for p in sorted((CODEX / "agents").glob("*.toml"))}

    # 1. Every registered config_file must resolve. This is the one that was
    #    broken: absolute /home/mu paths on a /Users/mu machine.
    unresolved = []
    for key, spec in agents.items():
        rel = spec.get("config_file", "")
        target = (CODEX / rel) if not rel.startswith("/") else Path(rel)
        if not target.is_file():
            unresolved.append(f"{key} -> {rel}")
    check("every registered config_file resolves", not unresolved, "; ".join(unresolved))

    # 2. No absolute paths — they are machine-specific by construction.
    absolute = [f"{k} -> {v.get('config_file')}" for k, v in agents.items()
                if str(v.get("config_file", "")).startswith("/")]
    check("no absolute config_file paths", not absolute, "; ".join(absolute))

    # 3. Every definition file on disk is registered — no orphans.
    registered_files = {Path(v.get("config_file", "")).stem for v in agents.values()}
    orphans = sorted(set(on_disk) - registered_files)
    check("no unregistered agent definitions", not orphans, ", ".join(orphans))

    # 4. Each file's `name` matches its filename, and the config key matches the
    #    name. Drift here means an agent answers to a name nobody expects.
    bad_name, bad_key, drifted_desc = [], [], []
    for key, spec in agents.items():
        stem = Path(spec.get("config_file", "")).stem
        p = on_disk.get(stem)
        if not p:
            continue
        d = tomllib.loads(p.read_text())
        if d.get("name") != stem:
            bad_name.append(f"{stem}: name={d.get('name')!r}")
        if key != stem.replace("-", "_"):
            bad_key.append(f"[agents.{key}] -> {stem}")
        if d.get("description") and spec.get("description") != d.get("description"):
            drifted_desc.append(stem)
    check("agent name matches its filename", not bad_name, "; ".join(bad_name))
    check("config key matches agent name", not bad_key, "; ".join(bad_key))
    check("config description matches the file's", not drifted_desc, ", ".join(drifted_desc))

    # 5. Required keys — a definition without instructions is a silent no-op.
    missing = [stem for stem, p in on_disk.items()
               if not tomllib.loads(p.read_text()).get("developer_instructions")]
    check("every definition has developer_instructions", not missing, ", ".join(missing))

    # 6. Roster parity with .claude/agents, minus documented gaps.
    claude = {p.stem for p in CLAUDE_AGENTS.glob("*.md")}
    codex = set(on_disk)
    missing_in_codex = sorted(claude - codex - KNOWN_CODEX_GAPS)
    extra_in_codex = sorted(codex - claude)
    check("no .claude agent missing from .codex (excl. documented gaps)",
          not missing_in_codex, ", ".join(missing_in_codex))
    check("no .codex agent absent from .claude", not extra_in_codex, ", ".join(extra_in_codex))

    stale_gap = sorted(KNOWN_CODEX_GAPS - claude)
    check("documented gaps still exist in .claude", not stale_gap,
          f"stale entries in KNOWN_CODEX_GAPS: {', '.join(stale_gap)}")

    print()
    print(f"  registered: {len(agents)}  on disk: {len(on_disk)}  "
          f".claude: {len(claude)}  documented gaps: {len(KNOWN_CODEX_GAPS)}")
    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} -> {', '.join(FAILURES)}")
        return 1
    print("all tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
