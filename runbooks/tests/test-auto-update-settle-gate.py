"""Regression tests for the post-apply SETTLE gate (F-6c3043f9, 2026-10-23).

Incident: concurrent pushes to main made Flux Kustomizations read "dependency
revision not up to date" / ReconciliationFailed; the old single-reading gate
reverted six healthy merges. Must hold:
  * transient state that clears on re-poll -> NO revert
  * failure that persists across the settle window -> revert
  * a real hard signal (crashloop) persisting -> revert (early, after confirm)
  * mixed: transient clears but a real one persists -> revert, naming only the real one
  * a single bad reading at the window's end is never enough
  * main() wiring: the revert path is gated on settle_health

No network/cluster: collect/sleep/clock are injected. Any git-driving test would
scrub GIT_* env; none is needed here, but we scrub anyway.
Run:  python3 runbooks/tests/test-auto-update-settle-gate.py
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

for k in [k for k in os.environ if k.startswith("GIT_")]:
    del os.environ[k]
_REPO = Path(__file__).resolve().parents[2]
os.environ.setdefault("_MISE_ACTIVATED", "1")
os.environ.pop("SWEEP_PG_DSN", None)
sys.path.insert(0, str(_REPO / "runbooks"))
sys.path.insert(0, str(_REPO / "runbooks" / "lib"))
s = importlib.util.spec_from_file_location("au", _REPO / "runbooks" / "auto-update.py")
au = importlib.util.module_from_spec(s)
s.loader.exec_module(au)

FAILURES = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


DEP = {"kustomization:a/x": "flux kustomization not ready: a/x [ReconciliationFailed] dependency 'a/y' revision is not up to date"}
CRASH = {"pod:a/p:CrashLoopBackOff": "a/p: CrashLoopBackOff"}


def run_seq(readings, timeout=600, poll=30):
    """readings: list of (hard, soft); the last repeats forever."""
    calls = {"n": 0}
    clock = {"t": 0.0}

    def collect(_ns):
        r = readings[min(calls["n"], len(readings) - 1)]
        calls["n"] += 1
        return dict(r[0]), dict(r[1]), {}

    def sleep(sec):
        clock["t"] += sec

    ok, probs = au.settle_health({"a"}, collect=collect, sleep=sleep,
                                 now=lambda: clock["t"], timeout=timeout, poll=poll)
    return ok, probs, calls["n"]


EMPTY = ({}, {})

# 1. transient dependency-revision state that clears -> no revert
ok, probs, n = run_seq([({}, DEP), ({}, DEP), EMPTY])
check("transient dependency-revision clears -> ok", ok and not probs and n == 3, (ok, probs, n))

# 2. a single bad reading then clean -> ok
ok, probs, n = run_seq([({}, DEP), EMPTY])
check("single bad reading never reverts", ok and n == 2, (ok, n))

# 3. persistent soft failure across the whole window -> revert
ok, probs, n = run_seq([({}, DEP)])
check("persistent ReconciliationFailed across window -> not ok", (not ok) and probs and n >= 10, (ok, probs, n))

# 4. real hard signal persisting -> revert after confirmation, not instantly
ok, probs, n = run_seq([(CRASH, {})])
check("persistent crashloop -> not ok after confirm polls",
      (not ok) and n == au.HARD_CONFIRM_POLLS and any("CrashLoop" in p for p in probs), (ok, probs, n))

# 5. crashloop that recovers within confirm window (pod restarting) -> ok
ok, probs, n = run_seq([(CRASH, {}), (CRASH, {}), EMPTY])
check("crashloop clearing before confirmation -> ok", ok and n == 3, (ok, n))

# 6. mixed: transient clears, real one persists -> revert, and reason names the real one
ok, probs, n = run_seq([(CRASH, DEP), (CRASH, {}), (CRASH, {})])
check("mixed: real persists -> not ok", not ok and any("CrashLoop" in p for p in probs), (ok, probs, n))

# 7. problem appears only at the very end of the window (single reading) -> not reverted
readings = [EMPTY] * 0 + [({}, DEP)] * 1
calls = {"n": 0}


def collect_late(_ns):
    calls["n"] += 1
    # clean-ish: bad on call 1 only, then clean on the confirming poll
    return ({}, DEP if calls["n"] == 1 else {}, {})


clock = {"t": 0.0}
ok, probs = au.settle_health({"a"}, collect=collect_late,
                             sleep=lambda x: clock.__setitem__("t", clock["t"] + x),
                             now=lambda: clock["t"], timeout=0, poll=30)
check("bad only in final single reading -> ok (needs persistence)", ok, (ok, probs))

# 8. wiring: main() must route the revert through settle (post_apply_health -> settle_health)
import inspect
check("post_apply_health delegates to settle_health",
      "settle_health(" in inspect.getsource(au.post_apply_health))
check("main() still reverts on a failed gate", "revert_batch(" in inspect.getsource(au.main)
      and "post_apply_health(" in inspect.getsource(au.main))

print(f"\n{'FAILED: ' + ', '.join(FAILURES) if FAILURES else 'ALL PASS'}")
sys.exit(1 if FAILURES else 0)
