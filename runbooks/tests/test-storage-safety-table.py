"""Regression tests for `s9_storage_safety_table` in runbooks/doc-check.py.

The check exists because docs/sops/storage-safety.md drifted from reality and
nobody noticed for months: every CIFS StorageClass had been moved to `Retain`,
17 rows still said `Delete`, and Hard Rule 1's STOP gate required
`subdir == "/" AND reclaimPolicy == Delete` — a conjunction that an all-Retain
fleet can never satisfy. The guard protecting the two `subdir: /` classes was
therefore unreachable, and the table that was supposed to encode blast radius
was wrong on most of its rows.

These tests assert the check FAILS when it should. A guard that only ever
returns green is indistinguishable from one that is broken — which is the exact
failure mode it was written to prevent, so it does not get to assume itself
correct.

Run:  python3 runbooks/tests/test-storage-safety-table.py
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

spec = importlib.util.spec_from_file_location("dc", REPO / "runbooks/doc-check.py")
dc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dc)

CRITICAL, WARNING, OK = dc.CRITICAL, dc.WARNING, dc.OK

GOOD_SOP = """
### Hard Rule 1
- `subdir == "/"` (or empty, or `..`-traversed)
  → **STOP, regardless of `reclaimPolicy`.**

### Hard Rule 3
| StorageClass | Source | Subdir | Reclaim |
|---|---|---|---|
| `cifs-plex-media` | `//NAS/media` | `/` | Retain |
| `cifs-paperless-log` | `//NAS/paperless_ngx` | `log` | Retain |
"""

LIVE = {
    "items": [
        {"metadata": {"name": "cifs-plex-media"}, "provisioner": "smb.csi.k8s.io",
         "reclaimPolicy": "Retain", "parameters": {"source": "//NAS/media", "subdir": "/"}},
        {"metadata": {"name": "cifs-paperless-log"}, "provisioner": "smb.csi.k8s.io",
         "reclaimPolicy": "Retain", "parameters": {"source": "//NAS/paperless_ngx", "subdir": "log"}},
    ]
}


def _run(sop_text: str, live_obj, *, other_files: dict[str, str] | None = None):
    """Drive s9 with a stubbed SOP + stubbed `kubectl get sc` output."""
    other = other_files or {}
    real_read, real_run = dc.read_file, dc.run

    def fake_read(path, *, scope=None):
        name = str(path)
        if name.endswith("storage-safety.md"):
            return sop_text
        for suffix, content in other.items():
            if name.endswith(suffix):
                return content
        return ""

    def fake_run(cmd, timeout=30, *, scope=None, dep=None):
        if "get sc" in cmd:
            return "" if live_obj is None else json.dumps(live_obj)
        return real_run(cmd, timeout, scope=scope, dep=dep)

    dc.read_file, dc.run = fake_read, fake_run
    try:
        return dc.s9_storage_safety_table()
    finally:
        dc.read_file, dc.run = real_read, real_run


def _msgs(f):
    return " | ".join(m for _, m in f._items)


FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}  {detail}")
        FAILURES.append(name)


def main() -> int:
    print("test-storage-safety-table")

    # --- control: the honest case must be green, or every test below is vacuous
    sev, f, _ = _run(GOOD_SOP, LIVE)
    check("control: matching table is clean", sev == OK and f.count(CRITICAL) == 0, _msgs(f))

    # --- 1. reclaim documented wrongly (the actual 17-row drift)
    sev, f, _ = _run(GOOD_SOP.replace("| `/` | Retain |", "| `/` | Delete |"), LIVE)
    check("wrong reclaim in table -> CRITICAL",
          sev == CRITICAL and "documented incorrectly" in _msgs(f), _msgs(f))

    # --- 2. live class absent from the table (Hard Rule 6, same-commit rule)
    sev, f, _ = _run(GOOD_SOP.replace(
        "| `cifs-paperless-log` | `//NAS/paperless_ngx` | `log` | Retain |\n", ""), LIVE)
    check("undocumented live class -> CRITICAL",
          sev == CRITICAL and "missing from the storage-safety table" in _msgs(f), _msgs(f))

    # --- 3. table row for a class that no longer exists
    sev, f, _ = _run(GOOD_SOP + "| `cifs-ghost` | `//NAS/x` | `y` | Retain |\n", LIVE)
    check("stale row -> WARNING",
          f.count(WARNING) >= 1 and "no longer exists" in _msgs(f), _msgs(f))

    # --- 4. the catastrophic pairing itself, live
    bad = json.loads(json.dumps(LIVE))
    bad["items"][0]["reclaimPolicy"] = "Delete"
    sev, f, _ = _run(GOOD_SOP.replace("| `/` | Retain |", "| `/` | Delete |"), bad)
    check("share-root subdir + Delete -> CRITICAL",
          sev == CRITICAL and "recursively wipes the entire share" in _msgs(f), _msgs(f))

    # --- 5. regression: the unreachable STOP gate reintroduced
    regressed = GOOD_SOP.replace(
        '- `subdir == "/"` (or empty, or `..`-traversed)\n  → **STOP, regardless of `reclaimPolicy`.**',
        '- `subdir == "/"` (or empty) AND `reclaimPolicy == Delete`\n  → **STOP.**')
    sev, f, _ = _run(regressed, LIVE)
    check("reintroduced AND-Delete gate -> CRITICAL",
          sev == CRITICAL and "unreachable" in _msgs(f), _msgs(f))

    # --- 6. THE IMPORTANT ONE: an unreadable cluster must not read as clean
    sev, f, _ = _run(GOOD_SOP, None)
    check("no live StorageClasses -> WARNING, never OK",
          sev != OK and "not** verified" in _msgs(f), _msgs(f))

    # --- 7. the corrected STOP gate must be carried by every agent doc that
    # can touch CIFS PVCs (P4.0.3). The 2026-04-26 wipe rule regressed once
    # already: media-manager.md kept the unreachable AND-Delete conjunction
    # after cluster-ops-agent.md was corrected.
    for rel in (".claude/agents/media-manager.md",
                ".claude/agents/cluster-ops-agent.md",
                "AGENTS.md"):
        text = (REPO / rel).read_text()
        stop_lines = [ln for ln in text.splitlines()
                      if "subdir" in ln and "STOP" in ln]
        ok = bool(stop_lines) and all(
            ("regardless of" in ln or "whatever" in ln) and
            not ("AND" in ln and "Delete" in ln and "STOP" in ln.split("AND")[-1])
            for ln in stop_lines)
        check(f"unconditional subdir=/ STOP gate present in {rel}", ok,
              stop_lines or ["<no STOP line found>"])

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} -> {', '.join(FAILURES)}")
        return 1
    print("all tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
