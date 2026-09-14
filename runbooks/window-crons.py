#!/usr/bin/env python3
"""Cron↔YAML parity for maintenance windows (P1.2).

`runbooks/maintenance-windows.yaml` declares the schedule; OpenClaw crons
execute it. Nothing tied them together: four of seven declared windows had no
driving cron for weeks, plans (one carrying a live operator GO) were scheduled
into slots that structurally could not fire, and the only way anyone found out
was archaeology. A schedule whose executor is unverified is fiction.

  --render   print the exact `openclaw cron add` command for every declared
             window (the human pastes them — PVC mutations stay an explicit
             operator act, but a deterministic copy-paste one)
  --check    compare live crons against the YAML; exit 1 on any mismatch
  --json     machine output for --check

The check asserts, per declared window: a cron exists whose payload runs
`maintenance-window run --window <id>`, enabled, with the schedule/timezone
the YAML implies — and that no cron drives a window the YAML no longer
declares (an orphan cron is a schedule nobody reviews). It runs inside
`maintenance-plan.py reconcile()` on every sweep; an unreadable cron list
reports NOT VERIFIED, never clean.

Retry crons (2026-09-14). A window that declares `retry_after_min: N` also
needs a SECOND cron at start+N running `maintenance-window retry --window
<id>` — the skill's retry verb is a no-op whenever ANY window_runs row exists
for (slot, today), so it only re-fires an occurrence the console never picked
up. The driving cron cannot tell those apart: it reports `ok` on DELIVERY of
the prompt, not on completion, and five nightly dates were lost that way.
--render prints the retry `cron add`; --check asserts it exists/enabled/at the
derived expression, and flags a retry cron for a window that declares no
retry (or no longer exists) as an orphan. A retry cron is never counted as a
driver — a window with only a retry cron is still undriven.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
WINDOWS_YAML = Path(__file__).resolve().parent / "maintenance-windows.yaml"

_DOW = {"sunday": 0, "monday": 1, "tuesday": 2, "wednesday": 3,
        "thursday": 4, "friday": 5, "saturday": 6}


def expected_cron_expr(win: dict) -> str:
    hh, mm = str(win.get("start", "00:00")).split(":")
    day = str(win.get("day", "")).lower()
    if day == "daily":
        return f"{int(mm)} {int(hh)} * * *"
    return f"{int(mm)} {int(hh)} * * {_DOW[day]}"


def expected_retry_cron_expr(win: dict) -> str | None:
    """Cron expr for the window's retry, start + retry_after_min, or None if
    the window declares no retry. Crossing midnight shifts the weekday."""
    after = win.get("retry_after_min")
    if not after:
        return None
    hh, mm = (int(x) for x in str(win.get("start", "00:00")).split(":"))
    total = hh * 60 + mm + int(after)
    days, rem = divmod(total, 24 * 60)
    rhh, rmm = divmod(rem, 60)
    day = str(win.get("day", "")).lower()
    if day == "daily":
        return f"{rmm} {rhh} * * *"
    return f"{rmm} {rhh} * * {(_DOW[day] + days) % 7}"


def load_windows(path: Path = WINDOWS_YAML) -> tuple[list, str]:
    cfg = yaml.safe_load(path.read_text())
    return cfg.get("windows", []), cfg.get("timezone", "Europe/Berlin")


def fetch_crons() -> list | None:
    """Live OpenClaw crons, or None when unreadable (None != empty!)."""
    try:
        p = subprocess.run(
            ["kubectl", "-n", "ai", "exec", "deploy/openclaw", "-c", "app", "--",
             "/home/node/.openclaw/bin/openclaw", "cron", "list", "--json"],
            capture_output=True, text=True, timeout=60)
        if p.returncode != 0:
            return None
        d = json.loads(p.stdout)
        return d if isinstance(d, list) else d.get("jobs", d.get("crons", []))
    except Exception:
        return None


def _window_arg(cron: dict, verb: str) -> str | None:
    argv = (cron.get("payload") or {}).get("argv") or []
    text = " ".join(str(a) for a in argv)
    if f"maintenance-window {verb}" not in text or "--window" not in text:
        return None
    try:
        return text.split("--window", 1)[1].split()[0]
    except IndexError:
        return None


def window_of_cron(cron: dict) -> str | None:
    """The window id a cron DRIVES (`maintenance-window run`), else None.
    A retry cron is deliberately not a driver."""
    return _window_arg(cron, "run")


def retry_window_of_cron(cron: dict) -> str | None:
    """The window id a cron RETRIES (`maintenance-window retry`), else None."""
    return _window_arg(cron, "retry")


def check(windows: list, tz: str, crons: list) -> list[str]:
    """Pure logic (testable): mismatch strings, empty = parity holds."""
    errs = []
    by_window: dict[str, list] = {}
    for c in crons:
        w = window_of_cron(c)
        if w:
            by_window.setdefault(w, []).append(c)

    declared = {str(w["id"]) for w in windows}
    for w in windows:
        wid = str(w["id"])
        matches = by_window.get(wid, [])
        if not matches:
            errs.append(f"window {wid!r} declared but NO cron drives it — "
                        f"plans scheduled here silently never run")
            continue
        if len(matches) > 1:
            errs.append(f"window {wid!r} driven by {len(matches)} crons — "
                        f"double-fires the window")
        c = matches[0]
        if not c.get("enabled", True):
            errs.append(f"window {wid!r}: cron exists but is DISABLED")
        sched = c.get("schedule") or {}
        want = expected_cron_expr(w)
        if sched.get("expr") != want:
            errs.append(f"window {wid!r}: cron expr {sched.get('expr')!r} != "
                        f"YAML-implied {want!r}")
        if sched.get("tz") not in (tz, None) and sched.get("tz") != tz:
            errs.append(f"window {wid!r}: cron tz {sched.get('tz')!r} != {tz!r}")
    for wid in sorted(set(by_window) - declared):
        errs.append(f"ORPHAN cron drives window {wid!r}, which the YAML no "
                    f"longer declares — a schedule nobody reviews")

    # Retry crons: required exactly where the YAML declares retry_after_min,
    # forbidden everywhere else (a retry nobody declared re-fires a window on
    # a schedule nobody reviews).
    by_retry: dict[str, list] = {}
    for c in crons:
        w = retry_window_of_cron(c)
        if w:
            by_retry.setdefault(w, []).append(c)
    retrying = {str(w["id"]) for w in windows if w.get("retry_after_min")}
    for w in windows:
        wid = str(w["id"])
        matches = by_retry.get(wid, [])
        if wid not in retrying:
            continue
        if not matches:
            errs.append(f"window {wid!r} declares retry_after_min but NO retry "
                        f"cron exists — a lost occurrence is never retried")
            continue
        if len(matches) > 1:
            errs.append(f"window {wid!r} has {len(matches)} retry crons")
        c = matches[0]
        if not c.get("enabled", True):
            errs.append(f"window {wid!r}: retry cron exists but is DISABLED")
        sched = c.get("schedule") or {}
        want = expected_retry_cron_expr(w)
        if sched.get("expr") != want:
            errs.append(f"window {wid!r}: retry cron expr {sched.get('expr')!r} "
                        f"!= YAML-implied {want!r} (start + retry_after_min)")
        if sched.get("tz") not in (tz, None):
            errs.append(f"window {wid!r}: retry cron tz {sched.get('tz')!r} != {tz!r}")
    for wid in sorted(set(by_retry) - retrying):
        why = ("declares no retry_after_min" if wid in declared
               else "the YAML no longer declares")
        errs.append(f"ORPHAN retry cron for window {wid!r}, which {why} — "
                    f"it would re-fire a window nobody asked to retry")
    return errs


def render(windows: list, tz: str) -> str:
    # The operations pane label. Changed 2026-09-03 from the historical
    # daily-operation / server-operation to ai-server-ops.
    ops_session = os.environ.get("OPERATION_SESSION", "ai-server-ops")
    out = []
    for w in windows:
        wid = w["id"]
        out.append(
            "kubectl -n ai exec deploy/openclaw -c app -- "
            "/home/node/.openclaw/bin/openclaw cron add \\\n"
            f"  --name \"Maintenance Window — {wid}\" \\\n"
            f"  --cron \"{expected_cron_expr(w)}\" --tz {tz} --exact \\\n"
            "  --session isolated \\\n"
            "  --command-argv '[\"sh\",\"-lc\",\"/home/node/.openclaw/bin/"
            f"maintenance-window run --window {wid}\"]' \\\n"
            # OPERATION_SESSION pins the target pane by exact label. Without
            # it, maintenance-window falls back to SESSION_CANDIDATES
            # ["daily-operation", "server-operation"] -- and on 2026-08-27 the
            # pane carrying those labels was repurposed into an unrelated
            # conversation. Resolution still SUCCEEDED (the pane was a live
            # Claude TUI, just the wrong one), so every window prompt was typed
            # into a Paperless session for six days with no error anywhere.
            # Pinning the label makes a future relabel fail loudly instead of
            # silently redirecting the scheduler. See F-8eea4d9e.
            "  --command-cwd /home/node/clawd "
            "--command-env MAINTENANCE_WINDOW_TRIGGER=cron "
            f"--command-env OPERATION_SESSION={ops_session} \\\n"
            "  --no-output-timeout-seconds 600 --timeout-seconds 600 --no-deliver\n")
        retry_expr = expected_retry_cron_expr(w)
        if retry_expr:
            # The retry verb checks window_runs for (slot, today) FIRST and
            # exits 0 without sending when any row exists — including the
            # `running` row the window agent writes at Step 0 start — so this
            # cron is safe to fire every day; it only acts on a lost occurrence.
            out.append(
                "kubectl -n ai exec deploy/openclaw -c app -- "
                "/home/node/.openclaw/bin/openclaw cron add \\\n"
                f"  --name \"Maintenance Window — {wid} retry\" \\\n"
                f"  --cron \"{retry_expr}\" --tz {tz} --exact \\\n"
                "  --session isolated \\\n"
                "  --command-argv '[\"sh\",\"-lc\",\"/home/node/.openclaw/bin/"
                f"maintenance-window retry --window {wid}\"]' \\\n"
                "  --command-cwd /home/node/clawd "
                "--command-env MAINTENANCE_WINDOW_TRIGGER=cron "
                f"--command-env OPERATION_SESSION={ops_session} \\\n"
                "  --no-output-timeout-seconds 600 --timeout-seconds 600 --no-deliver\n")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--render", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    windows, tz = load_windows()
    if a.render:
        print(render(windows, tz))
        return 0
    crons = fetch_crons()
    if crons is None:
        msg = {"verified": False, "errors": [],
               "note": "cron list unreadable — parity NOT verified (this is not a pass)"}
        print(json.dumps(msg) if a.json else f"⚠️  {msg['note']}")
        return 2
    errs = check(windows, tz, crons)
    if a.json:
        print(json.dumps({"verified": True, "errors": errs}))
    else:
        if errs:
            print(f"CRON↔YAML PARITY FAILURES ({len(errs)}):")
            for e in errs:
                print(f"  ! {e}")
        else:
            n_retry = sum(1 for w in windows if w.get("retry_after_min"))
            print(f"parity holds: {len(windows)} window(s), each driven by exactly "
                  f"one enabled cron ({n_retry} with a retry cron)")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
