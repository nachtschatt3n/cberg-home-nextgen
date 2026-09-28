#!/usr/bin/env python3
"""iTerm2 AutoLaunch script: keep runbooks/headless-dispatcher.py in an iTerm pane.

Why inside iTerm (2026-09-28): the OpenClaw pod reaches the dispatcher THROUGH
iTerm (iterm2-harness `resolve headless-dispatcher` by command line, `send` of
one HRUN line, `screen` polling), so the dispatcher must live in an iTerm
session with a real tty -- a plain launchd job would be invisible to the pod.
Creating that session from a launchd process needs Apple Events, which macOS
gates behind a per-binary Automation consent ("bash wants to control iTerm");
iTerm's `open file` path pops an "OK to run script?" modal instead. An iTerm
AutoLaunch script uses iTerm's own Python API: no consent, no modal, and it is
restarted by iTerm itself on every iTerm start.

The launchd side (runbooks/launchd/com.cberg.headless-dispatcher.plist) keeps
iTerm running after a reboot or quit; this script keeps the dispatcher running
inside it. Every POLL_S seconds: if no session's commandLine contains
`headless-dispatcher`, open a new window whose program is
start-headless-dispatcher.command. After a spawn it waits SPAWN_GRACE_S before
judging again (never a window storm), doubling up to BACKOFF_MAX_S while
spawns keep failing.

Install: symlink into ~/.config/iterm2/AppSupport/Scripts/AutoLaunch/
(docs/sops/maintenance-windows.md section 7).
"""
import asyncio
import fcntl
import os
import sys
import time

import iterm2

REPO = os.environ.get("OPERATION_REPO", "/Users/mu/code/cberg-home-nextgen")
LAUNCHER = f"{REPO}/runbooks/launchd/start-headless-dispatcher.command"
LOG = os.path.expanduser("~/Library/Logs/cberg-headless-keeper.log")
LOCK = os.path.expanduser("~/Library/Logs/cberg-headless/iterm-keeper.lock")
MARKER = "headless-dispatcher"
POLL_S = 30
SPAWN_GRACE_S = 60
BACKOFF_MAX_S = 900


def log(msg):
    with open(LOG, "a") as f:
        f.write(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                + f" iterm-keeper: {msg}\n")


async def dispatcher_session(app):
    for w in app.terminal_windows:
        for t in w.tabs:
            for s in t.sessions:
                try:
                    cmd = await s.async_get_variable("commandLine") or ""
                except Exception:  # noqa: BLE001
                    continue
                if MARKER in cmd and "--self-test" not in cmd \
                        and "keeper" not in cmd:
                    return s
    return None


async def main(connection):
    app = await iterm2.async_get_app(connection)
    log(f"start pid={os.getpid()} launcher={LAUNCHER}")
    backoff, last = SPAWN_GRACE_S, None
    while True:
        s = await dispatcher_session(app)
        if s is not None:
            if s.session_id != last:
                log(f"dispatcher present session={s.session_id}")
                last = s.session_id
            backoff = SPAWN_GRACE_S
            await asyncio.sleep(POLL_S)
            continue
        log(f"dispatcher absent (last session={last or 'none'}) -- opening a window")
        last = None
        try:
            w = await iterm2.Window.async_create(connection, command=LAUNCHER)
            log(f"spawned window={getattr(w, 'window_id', '?')}")
        except Exception as e:  # noqa: BLE001
            log(f"spawn FAILED: {type(e).__name__}: {e}")
        await asyncio.sleep(backoff)
        if await dispatcher_session(app) is None:
            backoff = min(backoff * 2, BACKOFF_MAX_S)
            log(f"still absent after spawn; next grace {backoff}s")


def single_instance():
    """Exit if another keeper holds the lock. Two keepers each see "absent" in
    the same poll and open two dispatchers (happened in the 2026-09-28 install
    test: the AutoLaunch copy plus a `launch API script` copy)."""
    os.makedirs(os.path.dirname(LOCK), exist_ok=True)
    fh = open(LOCK, "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        log(f"another keeper holds {LOCK}; pid={os.getpid()} exiting")
        sys.exit(0)
    fh.write(f"{os.getpid()}\n")
    fh.flush()
    return fh  # keep the fd (and the lock) for the process lifetime


_LOCK_FH = single_instance()
iterm2.run_forever(main)
