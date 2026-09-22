#!/usr/bin/env python3
"""Regression tests: the three things that keep a flate wedge from becoming a
silent-green or a stuck runner stay in the CI workflow (F-b44621fb).

flate 0.6.5 was measured wedging CPU-bound and never exiting (139% CPU, 10 min,
no output, on a tree it renders in 5.3 s) right after a HelmRepository URL was
rewritten to an unresolvable host. The record is monitor-only: nothing to fix
upstream yet, so the mitigations are the control, and a control nobody asserts
drifts out of a workflow file one refactor later. Asserted here:

  1. the `flate` job carries `timeout-minutes` <= 10 — the ONLY thing bounding
     a wedge; without it a hang burns the runner's 6 h default;
  2. the flux-local `test` job is still there and still runs `flux-local test`
     — two gates that fail differently are the insurance while the wedge is
     unexplained;
  3. the "Run flate test" step's own no-summary guard: a wedge killed by the
     timeout (or a binary that ran nothing) produces no `N passed` line and
     the step must fail, never pass — proven by EXECUTING the step's real
     script with a fake `flate` on PATH;
  4. the same script's silent-green guard (a failing kind the regex does not
     list) and its allowlist (only `HelmRelease ai/oc8` may fail) still hold;
  5. the action ref version and the `.mise.toml` pin are in lockstep, as the
     workflow comment requires.
  6. COMMISSIONING STRAWS: (a) the step script with its no-summary guard
     removed passes the empty-output case — proving the guard, not the fake,
     is what fails it; (b) a copy of the workflow without `timeout-minutes`
     fails assertion 1.

The workflow is read with PyYAML (the reader GitHub's own schema tooling
uses); nothing here re-parses it with grep.

Run: python3 runbooks/tests/test-flate-gate-mitigations.py
"""
from __future__ import annotations

import os
import re
import stat
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github/workflows/flux-local.yaml"
MISE = REPO / ".mise.toml"
FAILURES: list[str] = []
ERROR_MARKS = ("Traceback", "Exception:", "Error:")


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


def count(population, pred) -> int:
    items = list(population)
    if not items:
        raise AssertionError("count(): EMPTY population — nothing was observed")
    joined = "\n".join(str(x) for x in items)
    if any(m in joined for m in ERROR_MARKS):
        raise AssertionError(f"count(): population carries error text: {joined[:120]!r}")
    return sum(1 for x in items if pred(x))


def timeout_ok(jobs: dict) -> tuple[bool, str]:
    """Pure: the flate job is bounded by a timeout of at most 10 minutes."""
    job = jobs.get("flate")
    if not isinstance(job, dict):
        return False, "no `flate` job"
    t = job.get("timeout-minutes")
    if t is None:
        return False, "flate job has no timeout-minutes — a wedge runs to the 6h default"
    try:
        return int(t) <= 10, f"timeout-minutes={t}"
    except (TypeError, ValueError):
        return False, f"timeout-minutes is not a number: {t!r}"


wf = yaml.safe_load(WORKFLOW.read_text())
jobs = wf["jobs"]

# 1 — the timeout
ok, why = timeout_ok(jobs)
check("flate job: timeout-minutes present and <= 10 (the only bound on a wedge)", ok, why)

# 2 — flux-local retained
test_job = jobs.get("test") or {}
runs = [str(s.get("run") or "") for s in test_job.get("steps", [])]
# source text, not tool output: the error-text-aborting count() does not apply
# (the step script legitimately prints ::error:: lines), so the population is
# asserted non-empty explicitly instead.
check("flux-local `test` job still has run steps", bool(runs), str(test_job.get("name")))
check("flux-local `test` job still runs `flux-local test`",
      sum(1 for r in runs if "flux-local" in r and " test" in r) >= 1, str(test_job.get("name")))
check("flux-local-success gate still depends on the flux-local job (two gates, not one)",
      "test" in (jobs.get("flux-local-success") or {}).get("needs", []), str(jobs.get("flux-local-success", {}).get("needs")))

# 3/4 — execute the real step script with a fake flate
flate_steps = [s for s in jobs["flate"]["steps"] if s.get("name") == "Run flate test"]
check("exactly one `Run flate test` step", len(flate_steps) == 1)
step = flate_steps[0]
script = str(step["run"])
step_env = {k: str(v) for k, v in (step.get("env") or {}).items()}
check("the step pins its allowlist in env (EXPECTED_FAILURES) and forces full mode (FLATE_BASE empty)",
      "EXPECTED_FAILURES" in step_env and step_env.get("FLATE_BASE") == "", str(step_env))
setup = [s for s in jobs["flate"]["steps"] if str(s.get("uses", "")).startswith("home-operations/flate/action@")]
check("Setup flate pins the action to a version", len(setup) == 1 and "@v" in setup[0]["uses"])


def run_step(fake_output: str, fake_rc: int = 0, script_text: str = script,
             expected_failures: str | None = None) -> tuple[int, str]:
    tmp = Path(tempfile.mkdtemp(prefix="flate-gate-"))
    binp = tmp / "bin"
    binp.mkdir()
    out_file = tmp / "flate.out"
    out_file.write_text(fake_output)
    fake = binp / "flate"
    fake.write_text("#!/bin/bash\ncat \"$FAKE_FLATE_OUTPUT\"\nexit \"$FAKE_FLATE_RC\"\n")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    sp = tmp / "step.sh"
    sp.write_text(script_text)
    env = {**os.environ, **step_env,
           **({"EXPECTED_FAILURES": expected_failures} if expected_failures is not None else {}),
           "PATH": f"{binp}:{os.environ.get('PATH', '')}",
           "FAKE_FLATE_OUTPUT": str(out_file), "FAKE_FLATE_RC": str(fake_rc),
           "LC_ALL": "en_US.UTF-8", "LANG": "en_US.UTF-8"}
    p = subprocess.run(["bash", "-e", str(sp)], cwd=tmp, env=env,
                       capture_output=True, text=True, timeout=60)
    return p.returncode, p.stdout + p.stderr


OK_LOG = "  ✗ HelmRelease ai/oc8\n\n333 passed, 1 failed\n"
rc, out = run_step(OK_LOG, fake_rc=1)
check("allowlisted failure only (oc8): the step passes", rc == 0 and "matches the known-unrenderable allowlist" in out,
      f"rc={rc}\n{out[-400:]}")
rc, out = run_step("", fake_rc=137)
check("NO summary (a wedge killed by the timeout, or a binary that ran nothing): the step FAILS",
      rc == 1 and "no result summary" in out, f"rc={rc}\n{out[-400:]}")
rc, out = run_step("  ✗ HelmRepository flux-system/broken\n\n332 passed, 1 failed\n", fake_rc=1)
check("a failing kind the regex does not list: the silent-green guard FAILS the step",
      rc == 1 and "not in the regex" in out, f"rc={rc}\n{out[-400:]}")
rc, out = run_step("  ✗ HelmRelease ai/oc8\n  ✗ HelmRelease media/plex\n\n332 passed, 2 failed\n", fake_rc=1)
check("a new real failure beside the allowlisted one: the step FAILS (failure set changed)",
      rc == 1 and "failure set changed" in out, f"rc={rc}\n{out[-400:]}")

# 5 — lockstep with .mise.toml
m = re.search(r"@v(\d+\.\d+\.\d+)$", setup[0]["uses"]) if setup else None
pin = (tomllib.loads(MISE.read_text()).get("tools") or {}).get("github:home-operations/flate")
check("action ref version == .mise.toml flate pin (lockstep, as the workflow comment requires)",
      m is not None and pin is not None and m.group(1) == str(pin), f"action={m and m.group(1)} mise={pin}")

# 6 — COMMISSIONING STRAWS
guard = re.compile(r"\n\s*if ! grep -qE '\[0-9\]\+ passed' flate-test\.log; then.*?\n\s*fi\n", re.S)
stripped = guard.sub("\n", script, count=1)
check("STRAW (a): the no-summary guard is identifiable in the script (so it can be removed for the straw)",
      stripped != script)
# The day the allowlist is EMPTY (oc8 renders; the workflow says "delete the
# entry then") is when the guard is load-bearing: expected "" == actual "" and
# 0 failed == 0 parsed, so an empty log would otherwise be a green gate.
rc, out = run_step("", fake_rc=137, expected_failures="")
check("STRAW (a) control: with an EMPTY allowlist the shipped script still FAILS the empty-output case",
      rc == 1 and "no result summary" in out, f"rc={rc}\n{out[-300:]}")
rc, out = run_step("", fake_rc=137, script_text=stripped, expected_failures="")
check("STRAW (a): with the no-summary guard removed and an empty allowlist the empty-output case PASSES "
      "— the guard is what fails it", rc == 0, f"rc={rc}\n{out[-300:]}")
no_timeout = {k: ({kk: vv for kk, vv in v.items() if kk != "timeout-minutes"} if k == "flate" else v)
              for k, v in jobs.items()}
ok2, why2 = timeout_ok(no_timeout)
check("STRAW (b): a workflow copy without timeout-minutes fails the timeout assertion", not ok2, why2)

print(f"\n{len(FAILURES)} failure(s)" if FAILURES else "\nall checks passed")
sys.exit(1 if FAILURES else 0)
