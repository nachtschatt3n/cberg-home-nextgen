#!/usr/bin/env python3
"""Regression tests: sweep-run.py tears its port-forwards down on SIGTERM /
SIGHUP / any exit, not only when main() reaches its `finally` (F-b881a5b5).

main() stops its forwards in a `finally` and `_stop()` kills the forward's
process group, so every path that UNWINDS was already clean. Python's default
disposition for SIGTERM and SIGHUP is "terminate now" — no exception, so no
`finally`, no atexit — and a sweep killed by a supervisor timeout or by its
console going away left `kubectl port-forward` processes alive with ppid 1.
Measured 2026-09-17: 108 orphans on the operator Mac, 74 of them to
postgresql, the oldest 3 days.

Pinned here by driving the REAL module in a child interpreter with an
injected starter (a `sleep` in its own session stands in for kubectl):
  1. SIGTERM: the child exits 143 (SystemExit from the handler) and the
     forward's process is gone;
  2. SIGHUP: same, exit 129;
  3. an exit path that never calls stop() (sys.exit before the `finally`):
     the atexit backstop kills the forward;
  4. a deliberately IGNORED signal (nohup sets SIGHUP to SIG_IGN) is left
     alone — the install reports only the default-disposition signals;
  5. COMMISSIONING STRAW: the same child without _install_teardown_signals()
     — the pre-fix shape, `finally` only — dies with -15 on SIGTERM and the
     forward SURVIVES it (the test then reaps it).

Run: python3 runbooks/tests/test-sweep-forward-teardown-signals.py
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SWEEP_RUN = REPO / "runbooks/sweep-run.py"
FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


CHILD = r'''
import importlib.util, os, signal, subprocess, sys, time
os.environ["_MISE_ACTIVATED"] = "1"
spec = importlib.util.spec_from_file_location("sr", sys.argv[1])
sr = importlib.util.module_from_spec(spec); spec.loader.exec_module(sr)
mode = sys.argv[2]

def starter(ns, svc, lp, rp):
    # stands in for `kubectl port-forward`: its own session, like the real starter
    return subprocess.Popen(["sleep", "300"], preexec_fn=os.setsid,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

fwd = sr.Forward("databases", "postgresql", 1, 5432, probe=lambda: True, starter=starter)
if mode == "nohup":
    signal.signal(signal.SIGHUP, signal.SIG_IGN)
if mode != "prefix":
    installed = sr._install_teardown_signals()
    print("installed", " ".join(str(int(s)) for s in installed), flush=True)
fwd.dial()
print("forward", fwd.proc.pid, flush=True)
if mode == "atexit":
    sys.exit(0)            # never reaches a finally: the atexit backstop must act
try:
    time.sleep(60)
finally:
    fwd.stop()             # main()'s shape — teardown in finally
'''


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def wait_gone(pid: int, seconds: float = 4.0) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if not alive(pid):
            return True
        time.sleep(0.1)
    return not alive(pid)


def run_child(mode: str, sig=None) -> tuple[int, int | None, str]:
    """(child exit status, forward pid, installed-line)."""
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(CHILD)
        script = f.name
    p = subprocess.Popen([sys.executable, script, str(SWEEP_RUN), mode],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    fwd_pid, installed = None, ""
    deadline = time.time() + 20
    while time.time() < deadline:
        line = p.stdout.readline()
        if not line:
            break
        if line.startswith("installed"):
            installed = line.strip()
        if line.startswith("forward "):
            fwd_pid = int(line.split()[1])
            break
    if fwd_pid is None:
        p.kill()
        raise AssertionError(f"child never dialled its forward: {p.stderr.read()[:400]}")
    if sig is not None:
        time.sleep(0.3)
        os.kill(p.pid, sig)
    try:
        rc = p.wait(timeout=15)
    except subprocess.TimeoutExpired:
        p.kill()
        rc = p.wait()
    os.unlink(script)
    return rc, fwd_pid, installed


# 1 — SIGTERM unwinds and the forward dies
rc, pid, inst = run_child("fixed", signal.SIGTERM)
check("SIGTERM: the sweep exits 143 (unwound through SystemExit, not killed in place)", rc == 143, f"rc={rc}")
check("SIGTERM: the forward's process is gone", wait_gone(pid), f"forward {pid} still alive")
check("install reports both TERM and HUP re-dispositioned",
      inst.split()[1:] == [str(int(signal.SIGTERM)), str(int(signal.SIGHUP))], inst)

# 2 — SIGHUP the same way
rc, pid, _ = run_child("fixed", signal.SIGHUP)
check("SIGHUP: the sweep exits 129", rc == 129, f"rc={rc}")
check("SIGHUP: the forward's process is gone", wait_gone(pid), f"forward {pid} still alive")

# 3 — atexit backstop when no finally ever runs
rc, pid, _ = run_child("atexit")
check("sys.exit before any stop(): exit 0 and the atexit backstop killed the forward",
      rc == 0 and wait_gone(pid), f"rc={rc} forward alive={alive(pid)}")

# 4 — a deliberately ignored signal is respected
rc, pid, inst = run_child("nohup", signal.SIGTERM)
check("nohup shape (SIGHUP ignored beforehand): only TERM is installed, HUP is left ignored",
      inst.split()[1:] == [str(int(signal.SIGTERM))], inst)
check("...and TERM still tears down", rc == 143 and wait_gone(pid), f"rc={rc}")

# 5 — COMMISSIONING STRAW: the pre-fix shape leaks
rc, pid, _ = run_child("prefix", signal.SIGTERM)
leaked = alive(pid)
check("STRAW: without the signal install (finally only) SIGTERM kills the sweep in place (-15)",
      rc == -int(signal.SIGTERM), f"rc={rc}")
check("STRAW: ...and the forward SURVIVES it — the orphan class this fix ends", leaked,
      f"forward {pid} alive={leaked}")
if leaked:
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except ProcessLookupError:
        pass
    check("STRAW: reaped the leaked forward", wait_gone(pid))

print(f"\n{len(FAILURES)} failure(s)" if FAILURES else "\nall checks passed")
raise SystemExit(1 if FAILURES else 0)
