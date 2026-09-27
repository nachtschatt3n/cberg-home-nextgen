#!/usr/bin/env python3
"""headless-dispatcher -- run cron-driven Claude Code jobs WITHOUT the ops console.

Why (F-bc8d3fca, F-2a965f05, 2026-09-27): the OpenClaw crons (nightly/sat/sun
maintenance windows, their retries, the 48h sweep, the weekly retro) used to
TYPE their prompt into the interactive ops console (`ai-server-ops`). Whenever
the operator was using that pane the cron refused (correctly -- it must never
type into a live turn) and the occurrence was lost: 4 of 7 nightlies in one
week. The console is a shared, interactive resource; a cron must not depend on
it being idle.

What this is: a tiny foreground loop that lives in its OWN iTerm pane on the
Mac mini (label it `ai-server-cron`; the pod finds it by its command line,
`headless-dispatcher`, so the label is cosmetic). The pod's `operation` /
`maintenance-window` skills type exactly ONE line into this pane:

    HRUN <base64 of {"v":1,"run":"<id>","kind":"<kind>","prompt":"<text>"}>

and the dispatcher starts a fresh, detached `claude -p` in the repo with that
prompt on stdin (own context -- it can never be "exhausted" -- own log file),
then prints a marker the pod polls for:

    HEADLESS_STARTED run=<id> pid=<pid>        the job is running
    HEADLESS_REFUSED run=<id> reason=<why>     nothing started (e.g. same kind running)
    HEADLESS_EXITED run=<id> rc=<rc>           the job finished (+ a bounded result excerpt)
    HEADLESS_DISPATCHER_READY ...              idle and accepting lines

Delivery is still not completion: the pod keeps its ledger proof (the window's
Step 0 `window_runs` running row, the sweep's `sweep_cycles` row).

Safety:
  * one job per kind at a time (pidfile per kind survives a dispatcher restart);
  * the pane has echo OFF and reads in cbreak mode, so a line > MAX_CANON (1024
    on macOS) is read whole and the base64 never floods the screen;
  * anything that is not a well-formed HRUN line is rejected, never executed --
    the payload is only ever a PROMPT handed to claude on stdin, never a shell
    command, so nothing typed here reaches a shell;
  * jobs run in their own session (start_new_session) and survive a dispatcher
    restart or the pane being closed.

Start it (once per Mac login; `docs/sops/maintenance-windows.md` section 7):
    cd ~/code/cberg-home-nextgen && python3 runbooks/headless-dispatcher.py
Check it from the pod: `operation classify` / `maintenance-window classify`
print which path a cron would take.

Test: python3 runbooks/headless-dispatcher.py --self-test   (no claude started)
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import select
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(os.environ.get("OPERATION_REPO", Path(__file__).resolve().parents[1]))
LOG_DIR = Path(os.environ.get("HEADLESS_LOG_DIR",
                              os.path.expanduser("~/Library/Logs/cberg-headless")))
CLAUDE = os.environ.get("HEADLESS_CLAUDE_BIN") or shutil.which("claude") or \
    os.path.expanduser("~/.local/bin/claude")
KIND_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
RUN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{5,63}$")
MAX_LINE = 256 * 1024
RESULT_LINES = 40


def parse_line(line: str):
    """Pure: (job, None) for a well-formed HRUN line, else (None, reason)."""
    line = (line or "").strip()
    if not line:
        return None, "empty"
    if not line.startswith("HRUN "):
        return None, "not an HRUN line"
    try:
        job = json.loads(base64.b64decode(line[5:].strip(), validate=True).decode())
    except Exception as e:  # noqa: BLE001
        return None, f"undecodable payload ({type(e).__name__})"
    if not isinstance(job, dict) or job.get("v") != 1:
        return None, "unsupported payload version"
    run, kind, prompt = job.get("run"), job.get("kind"), job.get("prompt")
    if not isinstance(run, str) or not RUN_RE.match(run):
        return None, "bad run id"
    if not isinstance(kind, str) or not KIND_RE.match(kind):
        return None, "bad kind"
    if not isinstance(prompt, str) or not prompt.strip():
        return None, "empty prompt"
    return {"run": run, "kind": kind, "prompt": prompt}, None


def result_excerpt(log_path: Path, n: int = RESULT_LINES) -> tuple[str, bool | None]:
    """Pure-ish: the final `result` text of a stream-json log (last n lines), and
    its is_error flag (None when no result event was written)."""
    text, is_err = "", None
    try:
        with open(log_path, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - 512 * 1024))
            tail = f.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return "", None
    for raw in reversed(tail):
        try:
            ev = json.loads(raw)
        except Exception:  # noqa: BLE001
            continue
        if isinstance(ev, dict) and ev.get("type") == "result":
            text = str(ev.get("result") or "")
            is_err = bool(ev.get("is_error"))
            break
    lines = text.strip().splitlines()
    return "\n".join(lines[-n:]), is_err


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


class Dispatcher:
    def __init__(self, log_dir: Path = LOG_DIR, claude: str = CLAUDE, out=None,
                 spawn=None):
        self.log_dir = Path(log_dir)
        self.claude = claude
        self.out = out or sys.stdout
        self.spawn = spawn or self._spawn
        self.jobs: dict[str, dict] = {}   # kind -> {run, proc, log}
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def say(self, msg: str) -> None:
        self.out.write(msg + "\n")
        self.out.flush()

    def ready(self) -> None:
        running = ",".join(sorted(self.jobs)) or "-"
        self.say(f"HEADLESS_DISPATCHER_READY pid={os.getpid()} running={running}")

    def _pidfile(self, kind: str) -> Path:
        return self.log_dir / f"{kind}.pid"

    def kind_busy(self, kind: str) -> bool:
        if kind in self.jobs:
            return True
        pf = self._pidfile(kind)
        try:
            pid = int(pf.read_text().split()[0])
        except (OSError, ValueError, IndexError):
            return False
        if not _pid_alive(pid):
            return False
        # A recycled pid must not block the kind forever: only a live process
        # that is still a claude/caffeinate job counts (pid == ours: self-test).
        if pid == os.getpid():
            return True
        try:
            cmd = subprocess.run(["ps", "-p", str(pid), "-o", "command="],
                                 capture_output=True, text=True, timeout=5).stdout
        except Exception:  # noqa: BLE001
            return True
        return ("claude" in cmd) or ("caffeinate" in cmd)

    def _spawn(self, argv, stdin, stdout, env):
        return subprocess.Popen(argv, stdin=stdin, stdout=stdout, stderr=subprocess.STDOUT,
                                cwd=str(REPO), env=env, start_new_session=True)

    def handle(self, line: str) -> None:
        job, why = parse_line(line)
        if job is None:
            if why != "empty":
                self.say(f"HEADLESS_REJECTED reason={why.replace(' ', '-')}")
            return
        run, kind = job["run"], job["kind"]
        if self.kind_busy(kind):
            self.say(f"HEADLESS_REFUSED run={run} reason={kind}-already-running")
            return
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        base = self.log_dir / f"{stamp}-{kind}-{run}"
        prompt_path, log_path = base.with_suffix(".prompt"), base.with_suffix(".log")
        prompt_path.write_text(job["prompt"])
        env = dict(os.environ, HEADLESS_RUN_ID=run, HEADLESS_KIND=kind, CBERG_HEADLESS="1")
        argv = ["caffeinate", "-i", self.claude, "-p", "--dangerously-skip-permissions",
                "--output-format", "stream-json", "--verbose"]
        try:
            with open(prompt_path, "rb") as fin, open(log_path, "wb") as fout:
                proc = self.spawn(argv, fin, fout, env)
        except OSError as e:
            self.say(f"HEADLESS_REFUSED run={run} reason=spawn-failed-{type(e).__name__}")
            return
        self._pidfile(kind).write_text(f"{proc.pid} {run}\n")
        self.jobs[kind] = {"run": run, "proc": proc, "log": log_path}
        self.say(f"HEADLESS_STARTED run={run} pid={proc.pid}")
        self.say(f"  kind={kind} log={log_path}")

    def reap(self) -> bool:
        changed = False
        for kind, j in list(self.jobs.items()):
            rc = j["proc"].poll()
            if rc is None:
                continue
            changed = True
            del self.jobs[kind]
            try:
                self._pidfile(kind).unlink()
            except OSError:
                pass
            text, is_err = result_excerpt(j["log"])
            self.say(f"HEADLESS_EXITED run={j['run']} rc={rc} is_error={is_err}")
            self.say(f"HEADLESS_RESULT run={j['run']}")
            for ln in (text or "(no result event in the log)").splitlines():
                self.say("  " + ln)
            self.say(f"HEADLESS_RESULT_END run={j['run']}")
        return changed


def _read_lines_cbreak(fd, on_idle, poll_s=2.0):
    """Yield lines typed into the tty with echo off and no MAX_CANON limit."""
    import termios
    old = termios.tcgetattr(fd)
    new = termios.tcgetattr(fd)
    new[3] &= ~(termios.ECHO | termios.ICANON)
    termios.tcsetattr(fd, termios.TCSADRAIN, new)
    buf = bytearray()
    try:
        while True:
            r, _, _ = select.select([fd], [], [], poll_s)
            if not r:
                on_idle()
                continue
            chunk = os.read(fd, 65536)
            if not chunk:
                return
            for b in chunk:
                if b in (10, 13):
                    if buf:
                        yield buf.decode("utf-8", "replace")
                    buf.clear()
                elif b == 3:          # ctrl-c
                    raise KeyboardInterrupt
                elif len(buf) < MAX_LINE:
                    buf.append(b)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def self_test() -> int:
    import io
    import tempfile
    fails = []

    def ok(name, cond):
        print(("PASS " if cond else "FAIL ") + name)
        if not cond:
            fails.append(name)

    def line(run, kind, prompt):
        p = json.dumps({"v": 1, "run": run, "kind": kind, "prompt": prompt})
        return "HRUN " + base64.b64encode(p.encode()).decode()

    ok("parse good line", parse_line(line("op-sweep-0927-ab12", "op-sweep", "hi"))[0] is not None)
    ok("reject non-HRUN", parse_line("rm -rf /")[0] is None)
    ok("reject bad b64", parse_line("HRUN !!!")[0] is None)
    ok("reject bad kind", parse_line(line("op-sweep-0927-ab12", "Op Sweep;", "x"))[0] is None)
    ok("reject bad run", parse_line(line("x", "op-sweep", "x"))[0] is None)
    ok("reject empty prompt", parse_line(line("op-sweep-0927-ab12", "op-sweep", " "))[0] is None)

    class FakeProc:
        def __init__(self):
            self.pid, self.rc = 424242, None

        def poll(self):
            return self.rc

    with tempfile.TemporaryDirectory() as td:
        out = io.StringIO()
        procs = []

        def spawn(argv, stdin, stdout, env):
            assert argv[2] and "-p" in argv and "--dangerously-skip-permissions" in argv
            stdout.write(b'{"type":"system"}\n{"type":"result","result":"all green\\nline2",'
                         b'"is_error":false}\n')
            p = FakeProc()
            procs.append((p, stdin.read().decode(), env))
            return p

        d = Dispatcher(log_dir=Path(td), claude="claude", out=out, spawn=spawn)
        d.handle(line("op-sweep-0927-ab12", "op-sweep", "run a sweep"))
        ok("started marker", "HEADLESS_STARTED run=op-sweep-0927-ab12 pid=424242" in out.getvalue())
        ok("prompt on stdin", procs and procs[0][1] == "run a sweep")
        ok("run id in env", procs and procs[0][2].get("HEADLESS_RUN_ID") == "op-sweep-0927-ab12")
        d.handle(line("op-sweep-0927-cd34", "op-sweep", "again"))
        ok("same kind refused", "HEADLESS_REFUSED run=op-sweep-0927-cd34 reason=op-sweep-already-running"
           in out.getvalue())
        d.handle(line("mw-nightly-0927-ef56", "mw-nightly", "w"))
        ok("other kind allowed", "HEADLESS_STARTED run=mw-nightly-0927-ef56" in out.getvalue())
        d2 = Dispatcher(log_dir=Path(td), claude="claude", out=io.StringIO(), spawn=spawn)
        (Path(td) / "x-live.pid").write_text(f"{os.getpid()} r\n")
        ok("pidfile of a live pid guards across a restart", d2.kind_busy("x-live"))
        (Path(td) / "x-dead.pid").write_text("999999 r\n")
        ok("stale pidfile does not block", not d2.kind_busy("x-dead"))
        procs[0][0].rc = 0
        d.reap()
        v = out.getvalue()
        ok("exited marker", "HEADLESS_EXITED run=op-sweep-0927-ab12 rc=0 is_error=False" in v)
        ok("result excerpt", "  all green" in v and "HEADLESS_RESULT_END run=op-sweep-0927-ab12" in v)
        ok("kind free after exit", "op-sweep" not in d.jobs)
        d.handle("garbage")
        ok("garbage rejected, not run", "HEADLESS_REJECTED reason=not-an-HRUN-line" in out.getvalue()
           and len(procs) == 2)
    print("self-test:", "FAIL" if fails else "ok")
    return 1 if fails else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    if not sys.stdin.isatty():
        print("headless-dispatcher must run in a terminal pane (stdin is not a tty)",
              file=sys.stderr)
        return 2
    if not os.path.exists(CLAUDE):
        print(f"claude binary not found ({CLAUDE}); set HEADLESS_CLAUDE_BIN", file=sys.stderr)
        return 2
    os.chdir(REPO)
    signal.signal(signal.SIGHUP, signal.SIG_IGN)
    # Tell iTerm2 our cwd (the pod's identity check reads the pane `path`, which
    # shell integration otherwise leaves at the directory the shell last
    # reported) and name the tab. Both are plain OSC escapes, no-ops elsewhere.
    sys.stdout.write(f"\033]1337;CurrentDir={REPO}\007\033]1;ai-server-cron\007")
    sys.stdout.flush()
    d = Dispatcher()
    d.say(f"headless-dispatcher: repo={REPO} claude={CLAUDE} logs={d.log_dir}")
    d.say("Crons type one HRUN line here; do not type into this pane. ctrl-c stops "
          "the dispatcher (running jobs keep going).")
    d.ready()

    def idle():
        if d.reap():
            d.ready()

    try:
        for ln in _read_lines_cbreak(sys.stdin.fileno(), idle):
            d.handle(ln)
            d.ready()
    except KeyboardInterrupt:
        d.say("HEADLESS_DISPATCHER_STOPPED (running jobs continue in their own session)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
