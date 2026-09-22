#!/usr/bin/env python3
"""Regression tests: the external-dns-unowned-cnames plan carries its 7-day
soak as an executable, TIME-AWARE premise (F-9404f24b).

The soak used to be enforced by `depends_on: [external-dns-1.22.0]`. When that
plan executed and was retired the ref became a DEAD-REF error and was cleared,
so the ordering half was satisfied and the soak half became a comment. The
window agent gates every sequenced plan with `plan-premises.py
--require-premises`, so a premise is the mechanical refusal the plan lost.

Pinned here through the modules' own functions (the plan is loaded by
maintenance-plan.py's loader; the premise is judged by plan-premises.py's
evaluate(); the pipeline TAIL after the kubectl stage is executed for real on
fixture JSON — the cluster is never touched):
  1. the plan declares the soak premise and a v0.22.0 image premise, both
     accepted by the read-only allowlist and well-formed (one expect_* each);
  2. the soak pipeline says SOAKED on a chart-1.22.0 fixture deployed 8 days
     ago, NOT-SOAKED at 6d23h, and NOTHING on a chart other than 1.22.0
     (evaluate() reads no output as a failure); fractional-second timestamps
     parse;
  3. window-scheduler.py's premises_verdict refuses on that failure the way
     the window agent will;
  4. the image premise passes on v0.22.0 and refuses v0.21.0;
  5. the frontmatter still validates and depends_on stays empty (the soak
     lives in premises now, not in a dead ref);
  6. COMMISSIONING STRAWS: (a) the record's own suggestion — a static-date
     expect_matches on lastDeployed — PASSES on a fixture deployed one day
     ago (it cannot see time) where the shipped pipeline says NOT-SOAKED;
     (b) the shipped pipeline with the soak constant lowered to 6 days says
     SOAKED on the 6d23h fixture — the verdict turns on the constant, not on
     an accident of the fixture.

Run: python3 runbooks/tests/test-plan-soak-premise-external-dns.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ["_MISE_ACTIVATED"] = "1"
REPO = Path(__file__).resolve().parents[2]


def load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mp = load("mp", "runbooks/maintenance-plan.py")
pp = load("pp", "runbooks/plan-premises.py")
ws = load("ws", "runbooks/window-scheduler.py")

PLAN_ID = "external-dns-unowned-cnames"
SOAK_ID = "chart-1.22.0-soaked-7d"
IMAGE_ID = "pod-runs-v0.22.0"
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


cfg = mp.load_windows()
plans = mp.load_plans(cfg)
plan = next((p for p in plans if p.get("plan_id") == PLAN_ID), None)
if plan is None:
    raise SystemExit(f"plan {PLAN_ID} not found — nothing to test")
premises = plan.get("premises") or []
check("the plan declares premises", bool(premises))
check("exactly one soak premise and one image premise",
      count(premises, lambda p: p.get("id") == SOAK_ID) == 1
      and count(premises, lambda p: p.get("id") == IMAGE_ID) == 1,
      str([p.get("id") for p in premises]))
soak = next(p for p in premises if p.get("id") == SOAK_ID)
image = next(p for p in premises if p.get("id") == IMAGE_ID)

# 1 — shape and read-only
for pr in (soak, image):
    ok, why = pp.command_is_readonly(pr["run"])
    check(f"{pr['id']}: accepted by the read-only allowlist", ok, why)
    kinds = [k for k in pp.EXPECT_KINDS if pr.get(k) is not None]
    check(f"{pr['id']}: exactly one expect_* kind", len(kinds) == 1, str(kinds))
check("the soak premise reads the HelmRelease and its time gate is jq's now (time-aware)",
      soak["run"].startswith("kubectl get helmrelease -n network external-dns")
      and "<= now" in soak["run"] and "604800" in soak["run"], soak["run"])
tail = soak["run"].split("|", 1)[1]


def run_tail(fixture: dict, pipeline_tail: str = tail) -> str:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(fixture, f)
        path = f.name
    p = subprocess.run(["bash", "-o", "pipefail", "-c", f"cat {path} | {pipeline_tail}"],
                       capture_output=True, text=True, timeout=60)
    os.unlink(path)
    if p.returncode != 0:
        raise AssertionError(f"pipeline tail failed rc={p.returncode}: {p.stderr[:300]}")
    return p.stdout


def fixture(chart: str, deployed: datetime, fmt: str = "%Y-%m-%dT%H:%M:%SZ") -> dict:
    return {"status": {"history": [{"chartVersion": chart, "appVersion": "0.22.0",
                                    "lastDeployed": deployed.strftime(fmt),
                                    "status": "deployed", "version": 12}]}}


now = datetime.now(timezone.utc)

# 2 — the pipeline on fixtures, judged by evaluate()
out8 = run_tail(fixture("1.22.0", now - timedelta(days=8)))
ok8, det8 = pp.evaluate(soak, out8)
check("8 days on chart 1.22.0: SOAKED and the premise PASSES", ok8 and out8.startswith("SOAKED chart=1.22.0"),
      f"{out8!r} {det8}")
out6 = run_tail(fixture("1.22.0", now - timedelta(days=6, hours=23)))
ok6, det6 = pp.evaluate(soak, out6)
check("6d23h on chart 1.22.0: NOT-SOAKED and the premise FAILS", (not ok6) and out6.startswith("NOT-SOAKED"),
      f"{out6!r} {det6}")
out21 = run_tail(fixture("1.21.0", now - timedelta(days=30)))
ok21, det21 = pp.evaluate(soak, out21)
check("a chart other than 1.22.0 yields NO output and evaluate() fails CLOSED on it",
      out21.strip() == "" and not ok21 and "NO output" in det21, f"{out21!r} {det21}")
outf = run_tail(fixture("1.22.0", now - timedelta(days=8), fmt="%Y-%m-%dT%H:%M:%S.123456Z"))
check("a fractional-second lastDeployed still parses (the [0:19] slice)", outf.startswith("SOAKED"), outf)

# 3 — the window agent's verdict on that failure
doc = {"plans": [{"plan_id": PLAN_ID, "status": plan.get("status"), "window": plan.get("window"),
                  "declared": 2,
                  "results": [{"id": SOAK_ID, "passed": False, "ran": True, "detail": det6},
                              {"id": IMAGE_ID, "passed": True, "ran": True, "detail": "ok"}],
                  "passed": False}], "ok": False}
vok, vwhy = ws.premises_verdict(1, json.dumps(doc), PLAN_ID)
check("window-scheduler/run-now verdict: REFUSED naming the soak premise",
      vok is False and SOAK_ID in vwhy and "FAILED" in vwhy, vwhy)

# 4 — the image premise
iok, _ = pp.evaluate(image, "registry.k8s.io/external-dns/external-dns:v0.22.0\n")
inok, _ = pp.evaluate(image, "registry.k8s.io/external-dns/external-dns:v0.21.0\n")
check("image premise: passes on v0.22.0, refuses v0.21.0", iok and not inok)

# 5 — frontmatter still valid; the soak is not a dead ref any more
errs = [e for e in mp.validate_plans(cfg, plans) if e.startswith(PLAN_ID)]
check("validate_plans: no error for this plan", errs == [], str(errs))
check("depends_on stays empty (the soak is carried by premises, not by a dead ref)",
      (plan.get("depends_on") or []) == [], str(plan.get("depends_on")))

# 6 — COMMISSIONING STRAWS
one_day = now - timedelta(days=1)
static_premise = {"id": "static", "run": "true",
                  "expect_matches": "^" + one_day.strftime("%Y-%m-%d")}
sok, _ = pp.evaluate(static_premise, one_day.strftime("%Y-%m-%dT%H:%M:%SZ"))
out1 = run_tail(fixture("1.22.0", one_day))
check("STRAW (a): a static-date premise (the record's suggestion) PASSES one day after the deploy — "
      "it cannot see time — where the shipped pipeline says NOT-SOAKED",
      sok and out1.startswith("NOT-SOAKED"), f"static={sok} shipped={out1!r}")
tail6d = tail.replace("604800", "518400")
check("STRAW (b): lowering the constant to 6 days flips the 6d23h fixture to SOAKED — "
      "the verdict turns on the constant", run_tail(fixture("1.22.0", now - timedelta(days=6, hours=23)),
                                                    tail6d).startswith("SOAKED"))
check("STRAW (b): ...the shipped tail carries the 7-day constant (gate + both report branches) and "
      "the straw replaced every occurrence", tail.count("604800") == 3 and tail6d.count("604800") == 0, tail)

print(f"\n{len(FAILURES)} failure(s)" if FAILURES else "\nall checks passed")
raise SystemExit(1 if FAILURES else 0)
