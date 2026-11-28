#!/usr/bin/env python3
"""The nightly window refreshes the Pushgateway liveness figures after
`window-run-record.py --finalize` (2026-11-28). Before, only sweep-run.py's
--reconcile-only branch pushed them, so MaintenanceWindowMissed* read a
snapshot up to 48h old after the nightly.

Pinned: push after a successful finalize; NOT on non-finalize or failed
record; a push failure / raise never changes the exit code; the real sweep-run
module exposes push_liveness_metrics (the importlib load works).
Run: python3 runbooks/tests/test-window-run-liveness-push.py"""
import importlib.util, os, sys, types
from pathlib import Path

for k in [k for k in os.environ if k.startswith("GIT_")]:
    del os.environ[k]
R = Path(__file__).resolve().parents[1]
os.environ.setdefault("_MISE_ACTIVATED", "1")
os.environ.pop("SWEEP_PG_DSN", None)
sys.path.insert(0, str(R)); sys.path.insert(0, str(R / "lib"))
sp = importlib.util.spec_from_file_location("wrr", R / "window-run-record.py")
wrr = importlib.util.module_from_spec(sp); sp.loader.exec_module(wrr)
FAIL = []


def check(n, ok, d=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {n}" + ("" if ok else f"  {d}"))
    if not ok:
        FAIL.append(n)


calls = []
wrr.push_liveness_best_effort = lambda *a, **k: calls.append(1)
FIN = ["--slot", "nightly", "--outcome", "green", "--trigger", "cron", "--finalize"]
real_record = wrr._record

wrr._record = lambda argv=None: 0
calls.clear(); rc = wrr.main(FIN)
check("finalize ok -> pushes once, rc 0", rc == 0 and calls == [1], (rc, calls))
calls.clear(); rc = wrr.main(["--slot", "nightly", "--outcome", "green", "--trigger", "cron"])
check("plain insert (no --finalize) -> no push", rc == 0 and not calls, calls)
wrr._record = lambda argv=None: 2
calls.clear(); rc = wrr.main(FIN)
check("record failed (rc 2) -> no push, rc preserved", rc == 2 and not calls, (rc, calls))
wrr._record = lambda argv=None: 0

# best-effort contract with the real function
mod = types.SimpleNamespace(push_liveness_metrics=lambda env: (True, "job x: ok"))
import importlib
sp.loader.exec_module(wrr)  # restore the real push function
line = wrr.push_liveness_best_effort(env={}, loader=lambda: mod)
check("success logs one 'pushed' line", "liveness metrics pushed" in line, line)
mod = types.SimpleNamespace(push_liveness_metrics=lambda env: (False, "nothing pushed — x"))
check("push failure logs NOT pushed, no raise", "NOT pushed" in wrr.push_liveness_best_effort(env={}, loader=lambda: mod))
def boom(env): raise RuntimeError("kaboom")
mod = types.SimpleNamespace(push_liveness_metrics=boom)
check("raising pusher is swallowed", "kaboom" in wrr.push_liveness_best_effort(env={}, loader=lambda: mod))
def bad_loader(): raise SystemExit(3)
check("SystemExit during load is swallowed", "NOT pushed" in wrr.push_liveness_best_effort(env={}, loader=bad_loader))
# main() with a raising pusher keeps rc 0
wrr._record = lambda argv=None: 0
wrr.push_liveness_best_effort = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x"))
check("main() exit code unchanged when the push raises", wrr.main(FIN) == 0)

# real sweep-run loads via importlib and exposes the function (hyphenated filename)
s = importlib.util.spec_from_file_location("sr", R / "sweep-run.py")
m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
check("sweep-run.py loads by path and has push_liveness_metrics", callable(getattr(m, "push_liveness_metrics", None)))
check("wiring: main() calls push after _record only on finalize",
      "if build_parser().parse_args(argv).finalize" in open(R / "window-run-record.py").read())
print("\nFAILED: " + ", ".join(FAIL) if FAIL else "\nALL PASS")
sys.exit(1 if FAIL else 0)
