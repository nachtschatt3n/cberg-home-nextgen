#!/usr/bin/env python3
"""Regression tests: G4 (auto-update.py::ci_state) names no check, and a check
run left on a PR's head SHA by a job that no longer exists is HELD with a
reason that says so (F-6b1dd22b).

When the flux-local test job was retired (2026-09-23) nothing in G4 needed
re-pointing: it never required a check by name — it holds on any non-green
rollup entry. But GitHub keeps the check runs a removed job had already
attached to a PR's head SHA until a fresh run replaces them, and nothing
re-runs PR workflows when main changes, so PR #219 carried
`Flux Local Test=FAILURE` beside a green `Flate Render Gate` on the SAME SHA.
Read as a plain "CI failing" that is the shape that hid a 9-day lane freeze
(F-00235e5c). Asserted here:

  1. workflow_check_names() reads the REAL workflow files: `Flate Render Gate`
     is a job of the `Flux Local` workflow; the retired names are not;
  2. stale_check_note() is pure and one-directional: '' for a live job, for a
     matrix leg ("Name (leg)"), and for a check from no workflow of ours; a
     diagnosis for a retired name — against the real files AND a synthetic dir;
  3. ci_state() semantics are unchanged: a stale FAILURE still HOLDS (ok=False)
     with the note appended; a stale PENDING holds; all-green passes; a
     non-mergeable PR holds before any check is read;
  4. G4 hardcodes no check name: the retired names appear nowhere in
     auto-update.py or the policy YAML;
  5. STRAWS: (a) re-adding a job named `Flux Local Test` to a synthetic copy
     of the workflow makes the note vanish — the detector reads the file, not
     a list; (b) with the note stubbed to '' the verdict is STILL hold — the
     note is diagnostic, never load-bearing for the verdict.

Run: python3 runbooks/tests/test-g4-stale-check-diagnosis.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("au", REPO / "runbooks/auto-update.py")
au = importlib.util.module_from_spec(spec)
spec.loader.exec_module(au)

FAILURES: list[str] = []
RETIRED = ("Flux Local Test", "Flux Local successful")


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


def cr(name, concl="SUCCESS", status="COMPLETED", wf="Flux Local"):
    return {"__typename": "CheckRun", "name": name, "status": status,
            "conclusion": concl, "workflowName": wf}


# 1 — real workflow files
real = au.workflow_check_names()
check("workflow_check_names() sees the real workflows (non-empty, includes `Flux Local`)",
      bool(real) and "Flux Local" in real, str(real))
check("`Flate Render Gate` is a job of the `Flux Local` workflow",
      "Flate Render Gate" in real.get("Flux Local", set()), str(real.get("Flux Local")))
check("the retired names are not jobs of any workflow",
      not any(r in names for names in real.values() for r in RETIRED), str(real))

# 2 — stale_check_note is pure and one-directional
check("live job -> no note", au.stale_check_note(cr("Flate Render Gate", "FAILURE"), real) == "")
check("matrix leg of a live job -> no note",
      au.stale_check_note(cr("Flux Local Diff (helmrelease)", "FAILURE"), real) == "")
check("check from a workflow that is not ours (no workflowName) -> no note (nothing to judge)",
      au.stale_check_note({"__typename": "StatusContext", "context": "renovate/x", "state": "FAILURE"}, real) == "")
note = au.stale_check_note(cr("Flux Local Test", "FAILURE"), real)
check("retired `Flux Local Test` -> stale-run diagnosis naming the workflow and the remedy",
      "stale check run" in note and "'Flux Local'" in note and "reopen or rebase" in note, note)

# 3 — ci_state semantics unchanged; note appended, never used to skip
def fake_view(rollup, mergeable="MERGEABLE", state="UNSTABLE"):
    payload = json.dumps({"mergeable": mergeable, "mergeStateStatus": state, "statusCheckRollup": rollup})
    return lambda cmd, timeout=60, check=False: (0, payload, "")


orig_run = au.run
try:
    au.run = fake_view([cr("Flux Local Test", "FAILURE"), cr("Flate Render Gate"),
                        cr("Flux Local successful", "FAILURE"), cr("Labeler", wf="Labeler")])
    ok, detail = au.ci_state(219)
    check("stale FAILURE beside a green render gate: STILL HELD (ok=False)", ok is False, detail)
    check("... and the reason carries the diagnosis for the stale check",
          detail.startswith("CI failing:") and "Flux Local Test=FAILURE [" in detail
          and "stale check run" in detail, detail)
    check("... and the green `Flate Render Gate` is not in the reason", "Flate Render Gate" not in detail, detail)

    au.run = fake_view([cr("Flux Local successful", None, status="QUEUED"), cr("Flate Render Gate")])
    ok, detail = au.ci_state(1)
    check("stale PENDING: held with 'CI pending' + diagnosis",
          ok is False and detail.startswith("CI pending:") and "stale check run" in detail, detail)

    au.run = fake_view([cr("Flate Render Gate"), cr("Flux Local Diff (kustomization)"), cr("Labeler", wf="Labeler")])
    ok, detail = au.ci_state(2)
    check("all green, only live jobs: passes", ok is True and "all checks green" in detail, detail)

    au.run = fake_view([cr("Flate Render Gate", "FAILURE")])
    ok, detail = au.ci_state(3)
    check("a LIVE job failing: held, no stale note (this is a real CI failure)",
          ok is False and "Flate Render Gate=FAILURE" in detail and "stale" not in detail, detail)

    au.run = fake_view([], mergeable="CONFLICTING", state="DIRTY")
    ok, detail = au.ci_state(4)
    check("not mergeable: held before any check is read", ok is False and "not mergeable" in detail, detail)

    # 5b — the note is diagnostic, not load-bearing for the verdict
    orig_note = au.stale_check_note
    au.stale_check_note = lambda c, d: ""
    au.run = fake_view([cr("Flux Local Test", "FAILURE"), cr("Flate Render Gate")])
    ok, detail = au.ci_state(219)
    check("STRAW (b): with the note stubbed to '' the verdict is STILL hold (note never decides)",
          ok is False and detail == "CI failing: Flux Local Test=FAILURE", detail)
    au.stale_check_note = orig_note
finally:
    au.run = orig_run

# 4 — no hardcoded check names in the engine or the policy
for f in ("runbooks/auto-update.py", "runbooks/auto-update-policy.yaml"):
    src = (REPO / f).read_text()
    # the engine's own comment may cite the retired name as HISTORY (`Flux Local Test=FAILURE`
    # in a comment), so look at code/config lines only
    code = "\n".join(l for l in src.splitlines() if l.strip() and not l.strip().startswith("#"))
    check(f"{f}: no retired check name in code/config lines (G4 names no check)",
          not any(r in code for r in RETIRED), [r for r in RETIRED if r in code].__repr__())

# 5a — the detector reads the file, not a list: re-add the job, the note vanishes
with tempfile.TemporaryDirectory(prefix="g4-wf-") as td:
    wf = yaml.safe_load((REPO / ".github/workflows/flux-local.yaml").read_text())
    wf["jobs"]["test"] = {"name": "Flux Local Test", "runs-on": "ubuntu-latest",
                          "steps": [{"run": "echo re-added"}]}
    (Path(td) / "flux-local.yaml").write_text(yaml.safe_dump(wf))
    defined = au.workflow_check_names(td)
    check("STRAW (a): synthetic workflow dir is read (only the one file, `Flux Local`)",
          set(defined) == {"Flux Local"}, str(defined))
    check("STRAW (a): with `Flux Local Test` re-added as a job the note VANISHES",
          au.stale_check_note(cr("Flux Local Test", "FAILURE"), defined) == "",
          au.stale_check_note(cr("Flux Local Test", "FAILURE"), defined))
    check("STRAW (a) control: `Flux Local successful` (not re-added) is still diagnosed as stale",
          "stale check run" in au.stale_check_note(cr("Flux Local successful", "FAILURE"), defined))
    (Path(td) / "broken.yml").write_text("jobs: [not, a, mapping\n")
    check("an unparseable workflow file is skipped, not fatal", set(au.workflow_check_names(td)) == {"Flux Local"})

print(f"\n{len(FAILURES)} failure(s)" if FAILURES else "\nall checks passed")
sys.exit(1 if FAILURES else 0)
