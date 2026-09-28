"""Regression tests for the ops-console DELIVERY path (F-b8c6b6d6, F-7d9b201b).

Both OpenClaw skills that type into the Mac mini ops console — `maintenance-window`
(nightly/sat/sun window crons) and `operation` (the 48h sweep cron) — decide what
they may do from ONE pure classifier over the pane's visible screen. This test
pins that classifier against captured pane shapes and pins the delivery rules:

  classify_pane (byte-identical block in both skills — asserted here)
    idle / idle-with-draft / idle-old-box / placeholder -> idle
    spinner "esc to interrupt"                          -> busy
    "Waiting for N background agents" (live 2026-09-25,
      no "esc to interrupt", `openclaude status` said idle) -> busy
    question menu / permission prompt / /resume list    -> menu
    exhausted + idle + empty input                      -> exhausted-idle
    exhausted + draft in input                          -> exhausted-draft
    exhausted + spinner / menu                          -> exhausted-busy
    exhaustion text only in the transcript              -> exhausted-unclear

  maintenance-window run (F-b8c6b6d6)
    * busy / background agents / menu -> exit 8, NOTHING typed (no ctrl+u, no /clear)
    * idle + cron -> one prompt, then a bounded poll for the Step 0 running row:
      row appears -> 0 "completion verified"; never -> 12 within the budget;
      ledger unreadable -> 11; a row that existed BEFORE the send does not count
    * say-so (home-operation, 180s subprocess timeout) -> no poll
    * retry of a LOST occurrence into a busy / background-agents / menu pane ->
      exit 8, nothing typed, message names the lost (slot, date) (2026-09-26,
      so the retry cron's failureAlert pages); exhausted + not clearable -> exit 4
      with the same LOST wording; a row already present -> exit 0 no-op whatever
      the pane state (nothing lost, nothing to page)
  exhausted-pane recovery (F-7d9b201b, operator decision 2026-09-25: automate)
    * exhausted-idle + unattended -> /clear, wait for a fresh prompt, log
      CONSOLE_AUTO_CLEARED, then deliver (exactly ONE /clear, no second clean)
    * exhausted-busy / exhausted-draft / exhausted-unclear -> exit 4, nothing typed
    * manual trigger and run-now -> exit 4, never auto-cleared
    * /clear that does not take -> exit 4, no prompt sent
    * the same for `operation sweep --trigger cron`
  operation sweep/fix/versions pane gate (F-28af989d, 2026-09-26)
    * busy / background agents / menu -> exit 13 (8 is restart's "survived
      TERM+KILL"), NOTHING typed, cron AND manual, --wait or not
    * idle -> ctrl+u + exactly one prompt, exit 0; exhausted-idle cron still
      auto-clears and then passes the gate
    * classify reports "REFUSE exit 13" for busy/menu; dry-run names it
  operation retro (weekly ops retro, 2026-09-27) — same delivery rules
    * busy / background agents / menu -> exit 13, NOTHING typed, cron and manual
    * cron + exhausted-idle -> one /clear, then ONE prompt that points the
      session at runbooks/ops-retro.md and carries the unattended directive
    * manual + exhausted-idle -> exit 4, never auto-cleared; exhausted-busy -> exit 4
    * idle -> ctrl+u + exactly one prompt; dry-run names exit 13 + the runbook
  headless delivery (F-bc8d3fca / F-2a965f05, 2026-09-27): unattended runs try
  the headless dispatcher pane (runbooks/headless-dispatcher.py) FIRST
    * dispatcher READY + console busy/exhausted -> ONE HRUN line to the dispatcher,
      the console untouched, the same window_runs / sweep_cycles proof, exit 0
    * dispatcher REFUSED / no marker -> exit 14, never a console fallback
    * dispatcher absent / no READY banner -> HEADLESS_UNAVAILABLE, console rules
      unchanged (busy -> 8/13); manual runs never use the dispatcher
    * the HRUN line round-trips through the real dispatcher's parse_line
    * shared headless block byte-identical in both skills
  classify intent is read-only (types nothing, exit 0) in both skills
  neither skill carries a brace-form shell var (Flux postBuild strict mode)

Fixture screens are STRUCTURAL copies of real panes with neutral text — the live
capture's conversation content is deliberately not reproduced (public repo).

No sops or no age key: prints a loud SKIP line and returns 0.
OPENCLAW_SKILLS_DIR=<dir> imports plaintext skills from <dir> instead.

Run:  python3 runbooks/tests/test-openclaw-console-delivery.py
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CONFIGMAP = REPO / "kubernetes/apps/ai/openclaw/app/skills-configmap.sops.yaml"
KEYS = ("maintenance-window.py", "operation.py")
FAILURES: list[str] = []
NB = "\xa0"
RULE = "─" * 60


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


# ---- fixture screens --------------------------------------------------------
def _pane(body: str, input_line: str, footer: str, tray: str = "") -> str:
    return (f"{body}\n{RULE} ai-server-ops ─\n{input_line}\n{RULE}\n{footer}"
            + (f"\n{tray}" if tray else ""))


FOOT = "⏵⏵ bypass permissions on (shift+tab to cycle)"
FOOT_EXH = "⏵⏵ bypass permissions on · 100% context used · /clear to save 828.6k tokens"
FOOT_EXH2 = "⏵⏵ bypass permissions on · Context limit reached · /clear to save 1.1k tokens"

S = {
    "idle": _pane("⏺ Done. Pushed the fix.\n\n✻ Brewed for 42s", f"❯{NB}", FOOT),
    "idle-draft": _pane("⏺ Done.", f"❯{NB}do #4 next", FOOT),
    "idle-old-box": "╭────────╮\n│ >      │\n╰────────╯\n  ⏵⏵ bypass permissions on",
    "idle-placeholder": _pane("", f'❯{NB}Try "how does foo.py work?"', FOOT),
    "busy-spinner": _pane("⏺ Reading 3 files…\n✻ Thinking… (12s · ↑ 1.2k tokens · esc to interrupt)",
                          f"❯{NB}", FOOT),
    "busy-bg-agents": _pane(
        "⏺ Dispatched the agents.\n✻ Waiting for 12 background agents to finish\n"
        "✔ Update installed · Restart to update",
        f"❯{NB}yes do that next",
        "⏵⏵ bypass permissions on · 2 shells · ← for agents · ↓ to manage",
        "⏺ main\n◯ general-purpose Running tests… 2m 29s · ↓ 111.0k tokens\n"
        "◯ upgrade-planner-agent Reading plan… 2m 24s · ↓ 111.3k tokens\n↓ 4 more"),
    "menu-question": ("⏺ I need a decision.\n\n Which window should this land in?\n"
                      "❯ 1. nightly\n  2. sat-attended\n  3. Type something.\n\n"
                      "Enter to select · ↑/↓ to navigate · Esc to cancel"),
    "menu-permission": ("⏺ Bash(kubectl delete pod x)\n Do you want to proceed?\n"
                        "❯ 1. Yes\n  2. Yes, and don't ask again\n"
                        "  3. No, and tell Claude what to do differently (esc)"),
    "menu-resume-list": ("Resume Session\n ❯ fix nightly window delivery   2 hours ago · 412 msgs\n"
                         "   sweep 2026-09-24               1 day ago · 90 msgs\n"
                         " ↑/↓ to select · Enter to confirm · Esc to exit · Type to search"),
    "exhausted-idle": _pane("⏺ Report complete.", f"❯{NB}", FOOT_EXH),
    "exhausted-idle-2": _pane("⏺ Report complete.", f"❯{NB}", FOOT_EXH2),
    "exhausted-draft": _pane("⏺ Report complete.", f"❯{NB}Do #4 and #1", FOOT_EXH),
    "exhausted-busy": _pane("✻ Brewing… (1m 3s · esc to interrupt)", f"❯{NB}", FOOT_EXH),
    "exhausted-bg-agents": _pane("✻ Waiting for 2 background agents to finish", f"❯{NB}",
                                 FOOT_EXH),
    "exhausted-menu": ("⏺ Bash(x)\n Do you want to proceed?\n❯ 1. Yes\n  2. No\n"
                       + FOOT_EXH),
    "exhausted-unclear": _pane("⏺ The cron refused: the pane showed '/clear to save 812k "
                               "tokens'.\n  (that was yesterday)", f"❯{NB}", FOOT),
}
EXPECT = {
    "idle": "idle", "idle-draft": "idle", "idle-old-box": "idle", "idle-placeholder": "idle",
    "busy-spinner": "busy", "busy-bg-agents": "busy",
    "menu-question": "menu", "menu-permission": "menu", "menu-resume-list": "menu",
    "exhausted-idle": "exhausted-idle", "exhausted-idle-2": "exhausted-idle",
    "exhausted-draft": "exhausted-draft", "exhausted-busy": "exhausted-busy",
    "exhausted-bg-agents": "exhausted-busy", "exhausted-menu": "exhausted-busy",
    "exhausted-unclear": "exhausted-unclear",
}


# ---- plumbing ---------------------------------------------------------------
def decrypt_into(dest: Path) -> str | None:
    if not shutil.which("sops"):
        return "sops binary not found"
    for key in KEYS:
        try:
            r = subprocess.run(["sops", "-d", "--extract", f'["data"]["{key}"]', str(CONFIGMAP)],
                               capture_output=True, text=True, timeout=60)
        except Exception as e:  # noqa: BLE001
            return f"sops failed to run: {e}"
        if r.returncode != 0:
            return f"sops could not decrypt {key} (age key unavailable?): {r.stderr.strip()[:160]}"
        p = dest / key
        p.write_text(r.stdout)
        p.chmod(0o600)
    return None


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_main(fn, argv, via_sys_argv=False):
    buf = io.StringIO()
    code = 0
    saved = sys.argv
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        try:
            if via_sys_argv:
                sys.argv = ["prog", *argv]
                rc = fn()
            else:
                rc = fn(argv)
            code = rc or 0
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
        finally:
            sys.argv = saved
    return code, buf.getvalue()


class Res:
    def __init__(self, rc=0, out="", err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


class FakeConsole:
    """openclaude stand-in: resolve -> the ops pane; screen -> current text;
    `send /clear` swaps to the post-clear screen."""

    def __init__(self, mod):
        self.mod = mod
        self.calls: list[tuple] = []
        self.text = ""
        self.after_clear: str | None = None

    def set(self, text, after_clear=None):
        self.text, self.after_clear = text, after_clear
        self.calls.clear()

    def oc(self, *args, timeout=120):
        self.calls.append(args)
        if args[0] == "resolve":
            return Res(0, json.dumps({"session_id": "EF748825-0000", "label": "ai-server-ops",
                                      "path": self.mod.OPERATION_REPO,
                                      "command_line": "caffeinate -i"}))
        if args[0] == "screen":
            return Res(0, self.text)
        if args[0] == "send" and len(args) > 2 and args[2] == "/clear":
            if self.after_clear is not None:
                self.text = self.after_clear
        return Res(0, "")

    def typed(self):
        return [c for c in self.calls if c[0] in ("send", "ask", "key")]

    def prompts(self):
        return [c for c in self.calls if c[0] in ("send", "ask") and c[2] != "/clear"]

    def clears(self):
        return [c for c in self.calls if c[0] == "send" and c[2] == "/clear"]


@contextlib.contextmanager
def fake_time():
    """time.sleep advances a fake monotonic clock — bounded polls finish instantly
    and their budget is still measurable."""
    clock = {"t": 1000.0}
    o_sleep, o_mono = time.sleep, time.monotonic
    time.sleep = lambda s: clock.__setitem__("t", clock["t"] + s)
    time.monotonic = lambda: clock["t"]
    try:
        yield clock
    finally:
        time.sleep, time.monotonic = o_sleep, o_mono


# ---- tests ------------------------------------------------------------------
def test_classifier(mod, tag):
    for name, text in S.items():
        got = mod.classify_pane(text)
        check(f"{tag} classify {name} -> {EXPECT[name]}", got == EXPECT[name], f"got {got!r}")
        check(f"{tag} console_busy({name}) is {EXPECT[name] != 'idle'}",
              mod.console_busy(text) == (EXPECT[name] != "idle"))
    check(f"{tag} pane_draft reads the draft", mod.pane_draft(S["idle-draft"]) == "do #4 next",
          repr(mod.pane_draft(S["idle-draft"])))
    check(f"{tag} pane_draft ignores the placeholder", mod.pane_draft(S["idle-placeholder"]) == "")
    check(f"{tag} pane_draft empty on an empty prompt", mod.pane_draft(S["exhausted-idle"]) == "")


def test_maintenance_window(mw):
    con = FakeConsole(mw)
    ledger = {"counts": [0], "rc": 0, "reads": 0}

    def fake_run(argv, **kw):
        if argv[:3] == ["kubectl", "-n", "databases"] and "secret" in argv:
            return Res(0, __import__("base64").b64encode(b"postgres://reader:pw@db/s").decode())
        if argv[:len(mw.PG_EXEC)] == mw.PG_EXEC:
            ledger["reads"] += 1
            if ledger["rc"]:
                return Res(ledger["rc"], "", "psql: connection refused")
            c = ledger["counts"]
            n = c.pop(0) if len(c) > 1 else c[0]
            return Res(0, f"{n}\n")
        raise AssertionError(f"unexpected subprocess {argv}")

    orig = (mw.oc, mw.subprocess.run)
    mw.oc, mw.subprocess.run = con.oc, fake_run
    try:
        with fake_time() as clock:
            # -- F-b8c6b6d6: never type into a pane that is not at the prompt --
            for name in ("busy-spinner", "busy-bg-agents", "menu-question",
                         "menu-permission", "menu-resume-list"):
                con.set(S[name])
                ledger.update(counts=[0], rc=0, reads=0)
                code, out = run_main(mw.main, ["run", "--window", "nightly", "--trigger", "cron"])
                check(f"mw run cron into {name}: exit 8", code == 8, f"{code} {out[-300:]}")
                check(f"mw run cron into {name}: NOTHING typed (no ctrl+u, /clear, prompt)",
                      not con.typed(), str(con.typed()))

            # retry of a LOST occurrence into a pane that is not at the prompt:
            # exit 8 (was a silent no-op until 2026-09-26), nothing typed
            for name in ("busy-spinner", "busy-bg-agents", "menu-question",
                         "menu-permission", "menu-resume-list"):
                con.set(S[name])
                ledger.update(counts=[0], rc=0)
                code, out = run_main(mw.main, ["retry", "--window", "nightly", "--trigger", "cron"])
                check(f"mw retry LOST occurrence into {name}: exit 8, nothing typed",
                      code == 8 and not con.typed(), f"{code} {con.typed()} {out[-300:]}")
                check(f"mw ...{name}: loud FAIL_TOKEN naming the lost (slot, date)",
                      mw.FAIL_TOKEN in out and "LOST" in out
                      and f"(nightly, {mw._today_utc()})" in out, out[-400:])

            # exhausted and NOT auto-clearable, occurrence lost: exit 4, LOST wording
            for name in ("exhausted-busy", "exhausted-draft", "exhausted-unclear"):
                con.set(S[name], after_clear=S["idle"])
                ledger.update(counts=[0], rc=0)
                code, out = run_main(mw.main, ["retry", "--window", "nightly", "--trigger", "cron"])
                check(f"mw retry LOST occurrence, {name}: exit 4, nothing typed, says LOST",
                      code == 4 and not con.typed() and "is LOST" in out,
                      f"{code} {con.typed()} {out[-300:]}")

            # nothing lost (a row exists): exit 0 no-op, whatever the pane state
            for name in ("busy-bg-agents", "menu-question", "exhausted-busy", "idle"):
                con.set(S[name])
                ledger.update(counts=[1], rc=0)
                code, out = run_main(mw.main, ["retry", "--window", "nightly", "--trigger", "cron"])
                check(f"mw retry, row exists, {name}: exit 0 no-op, nothing typed",
                      code == 0 and not con.typed() and "no-op" in out, f"{code} {out[-200:]}")

            con.set(S["busy-bg-agents"])
            ledger.update(counts=[0], rc=0)
            code, out = run_main(mw.main, ["retry", "--window", "nightly", "--trigger", "cron",
                                           "--dry-run"])
            check("mw retry dry-run (lost): states the exit-8 refusal, types nothing",
                  code == 0 and "REFUSE exit 8 (retry" in out and not con.typed(), out[:500])

            # -- idle + cron: deliver, then bounded poll for the running row --
            con.set(S["idle"])
            ledger.update(counts=[0, 0, 0, 1], rc=0, reads=0)
            code, out = run_main(mw.main, ["run", "--window", "nightly", "--trigger", "cron"])
            check("mw run cron idle: exit 0 once the running row appears",
                  code == 0 and "completion verified" in out, f"{code} {out[-300:]}")
            check("mw run cron idle: exactly one prompt sent", len(con.prompts()) == 1,
                  str(con.prompts()))

            con.set(S["idle"])
            ledger.update(counts=[0], rc=0, reads=0)
            t0 = clock["t"]
            code, out = run_main(mw.main, ["run", "--window", "nightly", "--trigger", "cron"])
            waited = clock["t"] - t0
            check("mw run cron idle, row never appears: exit 12", code == 12 and mw.FAIL_TOKEN in out,
                  f"{code} {out[-300:]}")
            check("mw ...poll is bounded: <= 300s + one poll step, under the 600s job timeout",
                  300 <= waited <= 300 + mw.CONFIRM_POLL_S, f"waited {waited}s")

            con.set(S["idle"])
            ledger.update(counts=[1], rc=0, reads=0)
            code, out = run_main(mw.main, ["run", "--window", "nightly", "--trigger", "cron"])
            check("mw run cron: a row that existed BEFORE the send does not verify (exit 12)",
                  code == 12, f"{code} {out[-200:]}")

            con.set(S["idle"])
            ledger.update(counts=[0], rc=2, reads=0)
            code, out = run_main(mw.main, ["run", "--window", "nightly", "--trigger", "cron"])
            check("mw run cron: ledger unreadable throughout -> exit 11", code == 11,
                  f"{code} {out[-200:]}")

            con.set(S["idle"])
            ledger.update(counts=[0], rc=0, reads=0)
            t0 = clock["t"]
            code, out = run_main(mw.main, ["run", "--window", "nightly", "--trigger", "say-so"])
            check("mw run say-so: no poll (home-operation's 180s timeout), exit 0",
                  code == 0 and ledger["reads"] == 0 and clock["t"] - t0 < 10,
                  f"{code} reads={ledger['reads']}")

            code, out = run_main(mw.main, ["run", "--window", "nightly", "--trigger", "cron",
                                           "--confirm-timeout", "9999", "--dry-run"])
            check("mw dry-run: states the exit-8 refusal and a clamped (<=540s) poll",
                  code == 0 and "REFUSE exit 8" in out and "up to 540s" in out, out[:600])

            # -- F-7d9b201b: exhausted-idle is auto-cleared, then delivered --
            con.set(S["exhausted-idle"], after_clear=S["idle"])
            ledger.update(counts=[0, 1], rc=0, reads=0)
            code, out = run_main(mw.main, ["run", "--window", "nightly", "--trigger", "cron"])
            check("mw run cron exhausted-idle: /clear then deliver, exit 0",
                  code == 0 and "completion verified" in out, f"{code} {out[-400:]}")
            check("mw ...logged loudly (CONSOLE_AUTO_CLEARED)", "CONSOLE_AUTO_CLEARED" in out)
            check("mw ...exactly ONE /clear (no second clean-session clear)",
                  len(con.clears()) == 1, str(con.clears()))
            order = [c[0] + (":" + c[2] if c[0] == "send" else "") for c in con.typed()]
            check("mw ...the /clear precedes the prompt",
                  order and order[0] == "send:/clear" and len(con.prompts()) == 1, str(order))

            con.set(S["exhausted-idle"], after_clear=S["idle"])
            ledger.update(counts=[0], rc=0)
            code, out = run_main(mw.main, ["retry", "--window", "nightly", "--trigger", "cron",
                                           "--confirm-timeout", "0"])
            check("mw retry cron exhausted-idle (no row today): auto-clear + deliver",
                  code == 0 and len(con.clears()) == 1 and len(con.prompts()) == 1,
                  f"{code} {con.typed()}")

            for name in ("exhausted-busy", "exhausted-bg-agents", "exhausted-menu",
                         "exhausted-draft", "exhausted-unclear"):
                con.set(S[name], after_clear=S["idle"])
                ledger.update(counts=[0], rc=0)
                code, out = run_main(mw.main, ["run", "--window", "nightly", "--trigger", "cron"])
                check(f"mw run cron {name}: exit 4, NOTHING typed", code == 4 and not con.typed(),
                      f"{code} {con.typed()} {out[-200:]}")

            con.set(S["exhausted-idle"], after_clear=S["idle"])
            code, out = run_main(mw.main, ["run", "--window", "nightly", "--trigger", "manual"])
            check("mw run MANUAL exhausted-idle: exit 4, never auto-cleared",
                  code == 4 and not con.typed(), f"{code} {con.typed()}")

            con.set(S["exhausted-idle"], after_clear=S["exhausted-idle"])
            code, out = run_main(mw.main, ["run", "--window", "nightly", "--trigger", "cron"])
            check("mw run cron: /clear that does not take -> exit 4, no prompt sent",
                  code == 4 and len(con.clears()) == 1 and not con.prompts(),
                  f"{code} {con.typed()}")

            con.set(S["exhausted-idle"], after_clear=S["idle"])
            orig_open = mw.open_now_runs
            mw.open_now_runs = lambda: []
            try:
                code, out = run_main(mw.main, ["run-now", "--plan", "x-1"])
            finally:
                mw.open_now_runs = orig_open
            check("mw run-now exhausted-idle: exit 4, never auto-cleared (attended)",
                  code == 4 and not con.typed(), f"{code} {con.typed()}")

            con.set(S["menu-question"])
            orig_open = mw.open_now_runs
            mw.open_now_runs = lambda: []
            try:
                code, out = run_main(mw.main, ["run-now", "--plan", "x-1"])
            finally:
                mw.open_now_runs = orig_open
            check("mw run-now into a menu: exit 8, nothing typed", code == 8 and not con.typed(),
                  f"{code} {con.typed()}")

            for name in ("exhausted-busy", "idle", "busy-bg-agents"):
                con.set(S[name])
                code, out = run_main(mw.main, ["classify"])
                ok = code == 0 and not con.typed()
                try:
                    ok = ok and json.loads(out)["state"] == EXPECT[name]
                except Exception:  # noqa: BLE001
                    ok = False
                check(f"mw classify ({name}): read-only, exit 0, reports the state", ok,
                      f"{code} {out[:200]}")
    finally:
        mw.oc, mw.subprocess.run = orig


def test_operation(op):
    con = FakeConsole(op)
    orig = op.oc
    op.oc = con.oc
    try:
        with fake_time():
            con.set(S["exhausted-idle"], after_clear=S["idle"])
            code, out = run_main(op.main, ["sweep", "--trigger", "cron"], via_sys_argv=True)
            check("op sweep cron exhausted-idle: /clear then the sweep prompt, exit 0",
                  code == 0 and len(con.clears()) == 1 and len(con.prompts()) == 1
                  and "CONSOLE_AUTO_CLEARED" in out, f"{code} {con.typed()} {out[-300:]}")
            for name in ("exhausted-busy", "exhausted-draft", "exhausted-menu"):
                con.set(S[name], after_clear=S["idle"])
                code, out = run_main(op.main, ["sweep", "--trigger", "cron"], via_sys_argv=True)
                check(f"op sweep cron {name}: exit 4, nothing typed",
                      code == 4 and not con.typed(), f"{code} {con.typed()}")
            con.set(S["exhausted-idle"], after_clear=S["idle"])
            code, out = run_main(op.main, ["sweep"], via_sys_argv=True)
            check("op sweep MANUAL exhausted-idle: exit 4, never auto-cleared",
                  code == 4 and not con.typed(), f"{code} {con.typed()}")
            # -- F-28af989d: the sweep path gates on busy/menu too, exit 13 --
            check("op: pane-not-at-prompt exit is 13 (8 stays restart's TERM+KILL)",
                  getattr(op, "PANE_NOT_AT_PROMPT_EXIT", None) == 13)
            for name in ("busy-spinner", "busy-bg-agents", "menu-question",
                         "menu-permission", "menu-resume-list"):
                for argv in (["sweep", "--trigger", "cron"], ["sweep", "--trigger", "cron", "--wait"],
                             ["sweep"], ["fix"], ["versions", "--trigger", "cron"],
                             ["retro", "--trigger", "cron"], ["retro"]):
                    con.set(S[name], after_clear=S["idle"])
                    code, out = run_main(op.main, argv, via_sys_argv=True)
                    check(f"op {' '.join(argv)} into {name}: exit 13, NOTHING typed",
                          code == 13 and not con.typed()
                          and "OPERATION_SWEEP_HANDOFF_FAILED" in out and "not at the prompt" in out,
                          f"{code} {con.typed()} {out[-300:]}")
            for name in ("idle", "idle-draft"):
                con.set(S[name])
                code, out = run_main(op.main, ["sweep", "--trigger", "cron"], via_sys_argv=True)
                keys = [c for c in con.calls if c[0] == "key"]
                check(f"op sweep cron into {name}: ctrl+u + one prompt, exit 0",
                      code == 0 and len(con.prompts()) == 1 and not con.clears()
                      and keys == [("key", "EF748825-0000", "ctrl+u")],
                      f"{code} {con.typed()} {out[-300:]}")
            con.set(S["busy-bg-agents"])
            code, out = run_main(op.main, ["classify"], via_sys_argv=True)
            check("op classify busy: read-only, reports REFUSE exit 13",
                  code == 0 and not con.typed() and '"busy"' in out and "REFUSE exit 13" in out,
                  f"{code} {out[:300]}")
            con.set(S["idle"])
            code, out = run_main(op.main, ["sweep", "--trigger", "cron", "--dry-run"],
                                 via_sys_argv=True)
            check("op dry-run: names the exit-13 refusal, types nothing",
                  code == 0 and "REFUSE exit 13" in out and not con.typed(), out[:400])

            # -- pre-nightly version snapshot (F-539b186e, 2026-09-28) --
            check("op: snapshot is a SENDING intent (headless-first for crons)",
                  "snapshot" in getattr(op, "SENDING_INTENTS", ()))
            sp = getattr(op, "PROMPTS", {}).get("snapshot", "")
            check("op snapshot prompt: runs check-all-versions WITHOUT the DSN and forbids "
                  "commits/bumps/auto-update", "check-all-versions.py" in sp
                  and "env -u SWEEP_PG_DSN" in sp and "Do NOT commit" in sp
                  and "auto-update.py" in sp, sp[:200])
            con.set(S["busy-spinner"], after_clear=S["idle"])
            code, out = run_main(op.main, ["snapshot"], via_sys_argv=True)
            check("op snapshot MANUAL into a busy console: exit 13, nothing typed",
                  code == 13 and not con.typed(), f"{code} {out[-200:]}")

            # -- weekly ops retro (2026-09-27): same console delivery rules --
            check("op: retro is a SENDING intent (gated like sweep/fix/versions)",
                  "retro" in getattr(op, "SENDING_INTENTS", ()))
            con.set(S["exhausted-idle"], after_clear=S["idle"])
            code, out = run_main(op.main, ["retro", "--trigger", "cron"], via_sys_argv=True)
            pr = con.prompts()
            check("op retro cron exhausted-idle: one /clear, then ONE prompt, exit 0",
                  code == 0 and len(con.clears()) == 1 and len(pr) == 1
                  and "CONSOLE_AUTO_CLEARED" in out, f"{code} {con.typed()} {out[-300:]}")
            check("op retro prompt points at runbooks/ops-retro.md + carries the unattended directive",
                  bool(pr) and "runbooks/ops-retro.md" in pr[0][2]
                  and "AUTOMATED SCHEDULED RUN" in pr[0][2] and "do not apply" in pr[0][2],
                  str(pr)[:300])
            con.set(S["exhausted-idle"], after_clear=S["idle"])
            code, out = run_main(op.main, ["retro"], via_sys_argv=True)
            check("op retro MANUAL exhausted-idle: exit 4, never auto-cleared",
                  code == 4 and not con.typed(), f"{code} {con.typed()}")
            con.set(S["exhausted-busy"], after_clear=S["idle"])
            code, out = run_main(op.main, ["retro", "--trigger", "cron"], via_sys_argv=True)
            check("op retro cron exhausted-busy: exit 4, nothing typed",
                  code == 4 and not con.typed(), f"{code} {con.typed()}")
            con.set(S["idle"])
            code, out = run_main(op.main, ["retro", "--trigger", "cron"], via_sys_argv=True)
            keys = [c for c in con.calls if c[0] == "key"]
            check("op retro cron idle: ctrl+u + one prompt, exit 0",
                  code == 0 and len(con.prompts()) == 1 and not con.clears()
                  and keys == [("key", "EF748825-0000", "ctrl+u")], f"{code} {con.typed()}")
            con.set(S["idle"])
            code, out = run_main(op.main, ["retro", "--trigger", "cron", "--dry-run"],
                                 via_sys_argv=True)
            check("op retro dry-run: names exit 13 + the runbook, types nothing",
                  code == 0 and "REFUSE exit 13" in out and "runbooks/ops-retro.md" in out
                  and not con.typed(), out[:500])
            code, out = run_main(op.main, ["sweep", "--trigger", "cron", "--dry-run"],
                                 via_sys_argv=True)
            check("op sweep prompt is untouched by the retro directive",
                  "ops-retro" not in out and "weekly ops retro" not in out, out[:300])

            con.set(S["exhausted-idle"])
            code, out = run_main(op.main, ["classify"], via_sys_argv=True)
            check("op classify: read-only, exit 0, reports exhausted-idle",
                  code == 0 and not con.typed() and '"exhausted-idle"' in out, f"{code} {out[:200]}")
    finally:
        op.oc = orig


DISPATCHER_SID = "D15FA7C0-0000"


class FakeDispatcher(FakeConsole):
    """FakeConsole plus a headless-dispatcher pane. mode: started | refused |
    silent. exit_rc: None (still running) or the rc the job exits with."""

    def __init__(self, mod):
        super().__init__(mod)
        self.up, self.ready, self.mode, self.exit_rc = True, True, "started", 0
        self.dtext, self.hrun = "", []

    def setd(self, console_text, up=True, ready=True, mode="started", exit_rc=0,
             after_clear=None):
        self.set(console_text, after_clear)
        self.up, self.ready, self.mode, self.exit_rc = up, ready, mode, exit_rc
        self.dtext = "HEADLESS_DISPATCHER_READY pid=1 running=-" if ready else "zsh ➜"
        self.hrun = []

    def oc(self, *args, timeout=120):
        if args[0] == "resolve" and args[1] == self.mod.HEADLESS_SELECTOR:
            self.calls.append(args)
            if not self.up:
                return Res(1, "", f"openclaude: no session matches {args[1]!r}")
            return Res(0, json.dumps({"session_id": DISPATCHER_SID, "label": "ai-server-cron",
                                      "path": self.mod.OPERATION_REPO,
                                      "command_line": "python3 runbooks/headless-dispatcher.py"}))
        if len(args) > 1 and args[1] == DISPATCHER_SID:
            self.calls.append(("dispatcher",) + args)
            if args[0] == "screen":
                return Res(0, self.dtext)
            if args[0] == "send":
                self.hrun.append(args[2])
                job = json.loads(__import__("base64").b64decode(args[2][5:]))
                run = job["run"]
                if self.mode == "started":
                    self.dtext += f"\nHEADLESS_STARTED run={run} pid=4242\n  kind={job['kind']} log=/x"
                    if self.exit_rc is not None:
                        self.dtext += (f"\nHEADLESS_EXITED run={run} rc={self.exit_rc} is_error=False"
                                       f"\nHEADLESS_RESULT run={run}\n  sweep summary: all green"
                                       f"\nHEADLESS_RESULT_END run={run}")
                elif self.mode == "refused":
                    self.dtext += f"\nHEADLESS_REFUSED run={run} reason={job['kind']}-already-running"
                return Res(0, "")
            return Res(0, "")
        return super().oc(*args, timeout=timeout)

    def console_typed(self):
        return [c for c in self.calls if c[0] in ("send", "ask", "key")]


def _load_dispatcher():
    return load("headless_dispatcher_under_test", REPO / "runbooks/headless-dispatcher.py")


def test_headless(mw, op):
    disp = _load_dispatcher()
    for mod, tag in ((mw, "mw"), (op, "op")):
        line = mod.headless_line("mw-nightly-0927033000-abcdef", "mw-nightly", "line1\nline2 ${x}")
        job, why = disp.parse_line(line)
        check(f"{tag} HRUN line round-trips through the real dispatcher parse_line",
              job is not None and job["prompt"] == "line1\nline2 ${x}" and job["kind"] == "mw-nightly",
              str(why))
        rid = mod.headless_run_id("op-sweep")
        check(f"{tag} run id is dispatcher-valid", bool(disp.RUN_RE.match(rid)), rid)
        m = mod.headless_markers("HEADLESS_STARTED run=r1-000000 pid=7\nHEADLESS_EXITED run=r1-000000 "
                                 "rc=0 is_error=False\nHEADLESS_RESULT run=r1-000000\n  ok line\n"
                                 "HEADLESS_RESULT_END run=r1-000000\nHEADLESS_STARTED run=r2-000000 pid=8",
                                 "r1-000000")
        check(f"{tag} markers parse started/exited/result for THIS run only",
              m["started"] == 7 and m["exited"] == 0 and m["result"] == "ok line", str(m))

    # ---- maintenance-window ------------------------------------------------
    con = FakeDispatcher(mw)
    ledger = {"counts": [0], "rc": 0}

    def fake_run(argv, **kw):
        if argv[:3] == ["kubectl", "-n", "databases"] and "secret" in argv:
            return Res(0, __import__("base64").b64encode(b"postgres://reader:pw@db/s").decode())
        if argv[:len(mw.PG_EXEC)] == mw.PG_EXEC:
            if ledger["rc"]:
                return Res(ledger["rc"], "", "psql: connection refused")
            c = ledger["counts"]
            n = c.pop(0) if len(c) > 1 else c[0]
            return Res(0, f"{n}\n")
        raise AssertionError(f"unexpected subprocess {argv}")

    orig = (mw.oc, mw.subprocess.run)
    mw.oc, mw.subprocess.run = con.oc, fake_run
    try:
        with fake_time():
            for name in ("busy-spinner", "busy-bg-agents", "menu-question", "exhausted-busy",
                         "exhausted-draft"):
                con.setd(S[name])
                ledger.update(counts=[0, 1], rc=0)
                code, out = run_main(mw.main, ["run", "--window", "nightly", "--trigger", "cron"])
                check(f"mw headless: run cron with console {name}: exit 0 + completion verified",
                      code == 0 and "completion verified" in out and "HEADLESS_STARTED" in out,
                      f"{code} {out[-300:]}")
                check(f"mw headless ...{name}: console untouched, exactly ONE HRUN line",
                      not con.console_typed() and len(con.hrun) == 1,
                      f"{con.console_typed()} {len(con.hrun)}")
            job = json.loads(__import__("base64").b64decode(con.hrun[0][5:]))
            check("mw headless: payload kind mw-nightly carries the cron preamble",
                  job["kind"] == "mw-nightly" and "MAINTENANCE_WINDOW_TRIGGER=cron" in job["prompt"],
                  job["kind"])
            # retry of a LOST occurrence while the console is busy: the whole point
            con.setd(S["busy-spinner"])
            ledger.update(counts=[0, 0, 1], rc=0)
            code, out = run_main(mw.main, ["retry", "--window", "nightly", "--trigger", "cron"])
            check("mw headless: retry of a LOST occurrence with a BUSY console runs headless, exit 0",
                  code == 0 and "completion verified" in out and not con.console_typed()
                  and len(con.hrun) == 1, f"{code} {out[-300:]}")
            con.setd(S["busy-spinner"])
            ledger.update(counts=[1], rc=0)
            code, out = run_main(mw.main, ["retry", "--window", "nightly", "--trigger", "cron"])
            check("mw headless: retry with a row already present is still a no-op (nothing typed anywhere)",
                  code == 0 and not con.hrun and not con.console_typed(), f"{code} {out[-200:]}")
            # the Step 0 row never appears: the ledger still decides
            con.setd(S["idle"])
            ledger.update(counts=[0], rc=0)
            code, out = run_main(mw.main, ["run", "--window", "nightly", "--trigger", "cron"])
            check("mw headless: started but no running row -> exit 12 (delivery is not completion)",
                  code == 12, f"{code} {out[-200:]}")
            # typed, then refused / silent: exit 14, NEVER a console fallback
            for mode in ("refused", "silent"):
                con.setd(S["idle"], mode=mode)
                ledger.update(counts=[0, 1], rc=0)
                code, out = run_main(mw.main, ["run", "--window", "nightly", "--trigger", "cron"])
                check(f"mw headless {mode}: exit 14, one HRUN line, console NOT used as fallback",
                      code == 14 and len(con.hrun) == 1 and not con.console_typed()
                      and mw.FAIL_TOKEN in out, f"{code} {con.console_typed()} {out[-300:]}")
            # dispatcher absent / not READY: console rules unchanged
            for up, ready, label in ((False, True, "absent"), (True, False, "no READY banner")):
                con.setd(S["busy-spinner"], up=up, ready=ready)
                ledger.update(counts=[0], rc=0)
                code, out = run_main(mw.main, ["run", "--window", "nightly", "--trigger", "cron"])
                check(f"mw headless {label}: HEADLESS_UNAVAILABLE, busy console still refuses exit 8",
                      code == 8 and "HEADLESS_UNAVAILABLE" in out and not con.hrun
                      and not con.console_typed(), f"{code} {out[-300:]}")
            con.setd(S["idle"], up=False)
            ledger.update(counts=[0, 1], rc=0)
            code, out = run_main(mw.main, ["run", "--window", "nightly", "--trigger", "cron"])
            check("mw headless absent + idle console: delivered via the console as before, exit 0",
                  code == 0 and len(con.prompts()) == 1 and not con.hrun, f"{code} {out[-200:]}")
            # manual never uses the dispatcher
            con.setd(S["idle"])
            ledger.update(counts=[0], rc=0)
            code, out = run_main(mw.main, ["run", "--window", "nightly"])
            check("mw headless: MANUAL run goes to the console, never the dispatcher",
                  code == 0 and not con.hrun and len(con.prompts()) == 1, f"{code} {out[-200:]}")
            con.setd(S["busy-spinner"])
            code, out = run_main(mw.main, ["run", "--window", "nightly", "--trigger", "cron",
                                           "--dry-run"])
            check("mw headless dry-run: names the dispatcher-first path, types nothing",
                  code == 0 and "headless dispatcher FIRST" in out and not con.hrun
                  and not con.console_typed(), out[:400])
            code, out = run_main(mw.main, ["classify"])
            check("mw classify reports the cron path (headless READY), types nothing",
                  code == 0 and "headless dispatcher READY" in out and not con.hrun
                  and not con.console_typed(), out[-300:])
    finally:
        mw.oc, mw.subprocess.run = orig

    # ---- operation -----------------------------------------------------------
    con = FakeDispatcher(op)
    cyc = {"n": 1}
    orig = (op.oc, op.cycles_since)
    op.oc, op.cycles_since = con.oc, (lambda t0, trig: cyc["n"])
    try:
        with fake_time():
            con.setd(S["exhausted-busy"])
            cyc["n"] = 1
            code, out = run_main(op.main, ["sweep", "--wait", "--trigger", "cron"], via_sys_argv=True)
            check("op headless: sweep --wait cron with an exhausted-busy console: exit 0, "
                  "result relayed, completion verified",
                  code == 0 and "sweep summary: all green" in out and "completion verified" in out
                  and not con.console_typed() and len(con.hrun) == 1, f"{code} {out[-300:]}")
            con.setd(S["busy-spinner"])
            cyc["n"] = 0
            code, out = run_main(op.main, ["sweep", "--wait", "--trigger", "cron"], via_sys_argv=True)
            check("op headless: job exited but no sweep_cycles row -> exit 12",
                  code == 12 and not con.console_typed(), f"{code} {out[-200:]}")
            con.setd(S["busy-spinner"], exit_rc=3)
            cyc["n"] = 1
            code, out = run_main(op.main, ["sweep", "--wait", "--trigger", "cron"], via_sys_argv=True)
            check("op headless: job exit rc!=0 -> exit 6", code == 6, f"{code} {out[-200:]}")
            con.setd(S["busy-spinner"], exit_rc=None)
            cyc["n"] = 1
            code, out = run_main(op.main, ["sweep", "--wait", "--trigger", "cron", "--timeout", "90"],
                                 via_sys_argv=True)
            check("op headless: still running at --timeout -> ledger decides (row present), exit 0, "
                  "nothing killed", code == 0 and "still running" in out
                  and not [c for c in con.calls if c[0] == "kill-job"], f"{code} {out[-200:]}")
            for intent in [i for i in ("retro", "fix", "versions", "snapshot") if i in op.SENDING_INTENTS]:
                con.setd(S["menu-question"], exit_rc=None)
                code, out = run_main(op.main, [intent, "--trigger", "cron"], via_sys_argv=True)
                check(f"op headless: {intent} cron with a console in a menu starts headless, exit 0",
                      code == 0 and "started headless" in out and len(con.hrun) == 1
                      and not con.console_typed(), f"{code} {out[-200:]}")
            con.setd(S["busy-spinner"], mode="refused")
            code, out = run_main(op.main, ["sweep", "--trigger", "cron"], via_sys_argv=True)
            check("op headless refused: exit 14, no console fallback",
                  code == 14 and not con.console_typed(), f"{code} {out[-200:]}")
            con.setd(S["busy-spinner"], up=False)
            code, out = run_main(op.main, ["sweep", "--trigger", "cron"], via_sys_argv=True)
            check("op headless absent: HEADLESS_UNAVAILABLE, busy console still refuses exit 13",
                  code == 13 and "HEADLESS_UNAVAILABLE" in out and not con.console_typed(),
                  f"{code} {out[-200:]}")
            con.setd(S["idle"])
            code, out = run_main(op.main, ["sweep"], via_sys_argv=True)
            check("op headless: MANUAL sweep goes to the console, never the dispatcher",
                  code == 0 and not con.hrun and len(con.prompts()) == 1, f"{code} {out[-200:]}")
            con.setd(S["idle"])
            code, out = run_main(op.main, ["sweep", "--trigger", "cron", "--dry-run"], via_sys_argv=True)
            check("op headless dry-run names the dispatcher-first path",
                  code == 0 and "headless dispatcher FIRST" in out and not con.hrun, out[:300])
            code, out = run_main(op.main, ["classify"], via_sys_argv=True)
            check("op classify reports the cron path (headless READY), types nothing",
                  code == 0 and "headless dispatcher READY" in out and not con.hrun
                  and not con.console_typed(), out[-300:])
    finally:
        op.oc, op.cycles_since = orig


def shared_headless_block(src: str) -> str:
    m = re.search(r"# BEGIN shared headless block.*?# END shared headless block", src, re.S)
    return m.group(0) if m else ""


def shared_block(src: str) -> str:
    m = re.search(r"# BEGIN shared pane-state block.*?# END shared pane-state block", src, re.S)
    return m.group(0) if m else ""


def main() -> int:
    print("test-openclaw-console-delivery")
    override = os.environ.get("OPENCLAW_SKILLS_DIR")
    tmp = Path(tempfile.mkdtemp(prefix="openclaw-console-test-"))
    tmp.chmod(0o700)
    try:
        if override:
            src = Path(override)
            print(f"  NOTE  importing PLAINTEXT skills from OPENCLAW_SKILLS_DIR={src}")
        else:
            src = tmp / "skills"
            src.mkdir()
            skip = decrypt_into(src)
            if skip:
                print(f"  SKIP  !!! test-openclaw-console-delivery NOT RUN: {skip}. "
                      f"The ops-console delivery path is UNTESTED on this machine. !!!")
                return 0
        sys.dont_write_bytecode = True
        mw_src = (src / "maintenance-window.py").read_text()
        op_src = (src / "operation.py").read_text()
        b1, b2 = shared_block(mw_src), shared_block(op_src)
        check("shared pane-state block present in both skills", bool(b1) and bool(b2))
        check("shared pane-state block is byte-identical in both skills", b1 == b2)
        h1, h2 = shared_headless_block(mw_src), shared_headless_block(op_src)
        check("shared headless block present in both skills", bool(h1) and bool(h2))
        check("shared headless block is byte-identical in both skills", h1 == h2)
        for key, text in (("maintenance-window.py", mw_src), ("operation.py", op_src)):
            check(f"{key}: no brace-form shell var (Flux postBuild strict mode)",
                  "${" not in text)
        mw = load("mw_console_under_test", src / "maintenance-window.py")
        op = load("op_console_under_test", src / "operation.py")
        test_classifier(mw, "mw")
        test_classifier(op, "op")
        test_maintenance_window(mw)
        test_operation(op)
        test_headless(mw, op)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} -> {', '.join(FAILURES)}")
        return 1
    print("all ops-console delivery tests passed")
    return 0


def test_pytest_entry() -> None:
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
