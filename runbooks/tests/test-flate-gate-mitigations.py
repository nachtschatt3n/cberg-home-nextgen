#!/usr/bin/env python3
"""Regression tests: the things that keep a flate wedge from becoming a
silent-green or a stuck runner stay in the CI workflow (F-b44621fb), and the
Flate Render Gate stays the SINGLE render gate (F-6b1dd22b).

flate 0.6.5 was measured wedging CPU-bound and never exiting (139% CPU, 10 min,
no output, on a tree it renders in 5.3 s) right after a HelmRepository URL was
rewritten to an unresolvable host. The record is monitor-only: nothing to fix
upstream yet, so the mitigations are the control, and a control nobody asserts
drifts out of a workflow file one refactor later. Asserted here:

  1. the `flate` job carries `timeout-minutes` <= 10 — the ONLY thing bounding
     a wedge; without it a hang burns the runner's 6 h default;
  2. the flux-local `test` job is GONE and stays gone (retired 2026-09-23,
     operator decision on F-6b1dd22b): flux-local is archived at v8.4.0, its
     hand-rolled `docker run` invocation froze the auto-update G4 lane for
     nine days once (F-00235e5c), and its allowlist had drifted again
     (media/plex moved to a GitRepository chart flux-local cannot clone while
     flate rendered it). Exactly ONE job runs a renderer's test command and it
     is `flate`; the `flux-local-success` aggregate is gone (nothing consumed
     it — no branch protection, and G4 reads the whole rollup); the flux-local
     DIFF jobs are kept (they post PR diffs flate does not replace); every
     `needs` names a job that exists;
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
     fails assertion 1; (c) a copy with a flux-local test job re-added fails
     the single-gate assertion; (d) a copy whose flate step no longer invokes
     `flate test` fails it too — the detector sees the invocation, not merely
     the absence of the other tool.

The workflow is read with PyYAML (the reader GitHub's own schema tooling
uses); nothing here re-parses it with grep.

Run: python3 runbooks/tests/test-flate-gate-mitigations.py
"""
from __future__ import annotations

import copy
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


def _code(text: str) -> str:
    """Drop comment/blank lines so a comment that MENTIONS a tool is not an invocation."""
    return "\n".join(l for l in str(text).splitlines() if l.strip() and not l.strip().startswith("#"))


def _step_text(step: dict) -> str:
    w = step.get("with") if isinstance(step.get("with"), dict) else {}
    return _code("\n".join(str(x) for x in (step.get("run"), step.get("uses"), w.get("args")) if x))


def renderers(jobs: dict) -> dict[str, set[str]]:
    """Pure: job id -> the render tools whose TEST command that job invokes.
    Reads run scripts, `uses:` images and `with.args`, comments stripped."""
    found: dict[str, set[str]] = {}
    for jid, job in jobs.items():
        if not isinstance(job, dict):
            continue
        text = "\n".join(_step_text(s) for s in job.get("steps", []) if isinstance(s, dict))
        tools = set()
        if re.search(r"\bflate\s+test\b", text):
            tools.add("flate")
        if "flux-local" in text and re.search(r"(^|\s)test(\s|$)", text):
            tools.add("flux-local")
        if tools:
            found[jid] = tools
    return found


wf = yaml.safe_load(WORKFLOW.read_text())
jobs = wf["jobs"]

# 1 — the timeout
ok, why = timeout_ok(jobs)
check("flate job: timeout-minutes present and <= 10 (the only bound on a wedge)", ok, why)

# 2 — flux-local test RETIRED; flate is the single render gate (F-6b1dd22b)
seen = renderers(jobs)
check("exactly one job runs a renderer's test command, and it is `flate` (single render gate)",
      seen == {"flate": {"flate"}}, str(seen))
check("no job runs `flux-local test` (retired 2026-09-23 — EOL tool, hand-maintained invocation)",
      "flux-local" not in set().union(*seen.values()) if seen else False, str(seen))
check("no `flux-local-success` aggregate job (nothing consumed it; G4 reads the whole rollup)",
      "flux-local-success" not in jobs and not any(
          str(j.get("name", "")).strip().lower() == "flux local successful"
          for j in jobs.values() if isinstance(j, dict)), str(list(jobs)))
check("the render gate's check name is exactly `Flate Render Gate` (what `gh pr checks` and G4 print)",
      jobs.get("flate", {}).get("name") == "Flate Render Gate", str(jobs.get("flate", {}).get("name")))
diff_text = "\n".join(_step_text(s) for s in (jobs.get("diff") or {}).get("steps", []) if isinstance(s, dict))
check("the flux-local `diff` jobs are kept (they post PR diffs flate's test does not replace)",
      "diff" in jobs and "allenporter/flux-local" in diff_text
      and re.search(r"(^|\s)diff\s", diff_text) is not None, diff_text[:120])
dangling = [(jid, n) for jid, j in jobs.items() if isinstance(j, dict)
            for n in ([j.get("needs")] if isinstance(j.get("needs"), str) else (j.get("needs") or []))
            if n not in jobs]
check("every `needs` names a job that exists (a dangling needs is a workflow GitHub refuses to run)",
      not dangling, str(dangling))

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
# (c) the retired job comes back, in the exact shape it had (comment lines
# mentioning the tool must NOT trip the detector — only the invocation does).
readded = copy.deepcopy(jobs)
readded["test"] = {"name": "Flux Local Test", "runs-on": "ubuntu-latest", "steps": [
    {"name": "Run flux-local test", "run":
        "# flux-local is archived; this comment alone must not count\n"
        "docker run --rm ghcr.io/allenporter/flux-local:v8.4.0 \\\n"
        "  test --enable-helm --all-namespaces --path kubernetes/flux/cluster\n"}]}
seen_c = renderers(readded)
check("STRAW (c): a workflow copy with a flux-local test job re-added FAILS the single-gate assertion",
      seen_c != {"flate": {"flate"}} and "flux-local" in seen_c.get("test", set()), str(seen_c))
commented = copy.deepcopy(jobs)
commented["flate"]["steps"] = [
    {**s, "run": "# a comment saying flate test and flux-local test\n" + str(s.get("run"))}
    if s.get("name") == "Run flate test" else s for s in commented["flate"]["steps"]]
check("STRAW (c) control: a comment that merely MENTIONS both tools does not change the reading",
      renderers(commented) == {"flate": {"flate"}}, str(renderers(commented)))
# (d) the flate step stops invoking flate: the gate is hollow and the detector says so.
hollow = copy.deepcopy(jobs)
hollow["flate"]["steps"] = [
    {**s, "run": "echo 'nothing rendered'\n"} if s.get("name") == "Run flate test" else s
    for s in hollow["flate"]["steps"]]
check("STRAW (d): a workflow copy whose flate step no longer runs `flate test` FAILS the single-gate assertion",
      renderers(hollow) == {}, str(renderers(hollow)))

print(f"\n{len(FAILURES)} failure(s)" if FAILURES else "\nall checks passed")
sys.exit(1 if FAILURES else 0)
