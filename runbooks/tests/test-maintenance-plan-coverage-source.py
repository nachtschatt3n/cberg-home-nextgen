#!/usr/bin/env python3
"""Regression test: maintenance-plan.py's needs-a-plan comes from coverage.py.

2026-09-27 (throughput program item C). The report printed

    all held updates have a plan ✅

while `coverage.py` listed 22 needs_plan rows, 17 of them with no plan file.
`reconcile()` read only `get_held()`, i.e. auto-update.py's held list, and that
list is built from OPEN RENOVATE PRs — with 0 open PRs it is empty, so every
direct-bump-lane update needing a plan was invisible and the all-clear was a
statement about an empty input.

Contract pinned here:
  * coverage.py's `needs_plan_groups` is the source of truth; a group with
    `dispatch: true` is a planner target and suppresses the all-clear;
  * an unreadable / skipped / malformed coverage result is UNKNOWN, never zero —
    no all-clear, an explicit `!!` line instead;
  * a group whose plan already exists (`dispatch: false`) does not block it;
  * `get_coverage()` rejects an `error` payload and a payload without the keys.

Run: python3 runbooks/tests/test-maintenance-plan-coverage-source.py
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "runbooks"))
_spec = importlib.util.spec_from_file_location("mp", REPO / "runbooks/maintenance-plan.py")
mp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mp)

CFG = mp.load_windows()
TODAY = date(2026, 9, 27)
FAILURES: list[str] = []
ALL_CLEAR = "every update that needs a plan has one"


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


REDIS_GROUP = {
    "group_id": "redis-fleet-8.10.2", "group_kind": "image-fleet", "size": 7,
    "members": [{"component": c, "kind": "image", "current": "8.10.1-alpine",
                 "target": "8.10.2-alpine", "image_repos": ["redis"]}
                for c in ("sure-redis", "immich-redis", "paperless-redis", "nextcloud-redis",
                          "tube-archivist-redis", "superset-redis-official", "redis")],
    "security_driven": False, "security_evidence": [], "plan": None, "dispatch": True,
    "reason": "G3 could not verify the release notes",
}
PLANNED_GROUP = {**REDIS_GROUP, "group_id": "app-template-5.2.1", "group_kind": "app-template",
                 "size": 1, "plan": "app-template-5.2.1", "dispatch": False}


def reconcile(coverage, held=(), cov_error=None):
    mp.load_plans = lambda cfg: []
    mp.get_held = lambda: ([dict(h) for h in held], None)
    mp.get_coverage = lambda: (coverage, cov_error)
    mp.cron_parity = lambda cfg: ([], False)
    return mp.reconcile(CFG, TODAY, decisions=None)


def main() -> int:
    print(__doc__.strip().splitlines()[0])
    print()

    # --- THE DEFECT: 0 held PRs, coverage has unplanned work ----------------
    cov = {"needs_plan": [{"component": m["component"]} for m in REDIS_GROUP["members"]],
           "needs_plan_groups": [REDIS_GROUP]}
    r = reconcile(cov)
    txt = mp.human(r, CFG)
    check("0 held PRs + coverage needs_plan -> NO all-clear", ALL_CLEAR not in txt
          and "all held updates have a plan" not in txt, txt[:600])
    check("...the group is listed as a planner target",
          "redis-fleet-8.10.2" in txt and "NEEDS A PLAN" in txt, txt[:600])
    check("...JSON: all_planned is False and planner_dispatch carries the group",
          r["all_planned"] is False
          and [g["group_id"] for g in r["planner_dispatch"]] == ["redis-fleet-8.10.2"],
          json.dumps({k: r[k] for k in ("all_planned", "planner_dispatch")})[:300])
    check("...the per-row evidence is carried too", len(r["coverage_needs_plan"]) == 7)

    # --- fail loud: unreadable coverage is UNKNOWN --------------------------
    r = reconcile(None, cov_error="coverage.py did not run: TimeoutExpired")
    txt = mp.human(r, CFG)
    check("coverage unreadable -> no all-clear", ALL_CLEAR not in txt, txt[:600])
    check("...an explicit UNKNOWN line names the error",
          "needs-a-plan is UNKNOWN" in txt and "TimeoutExpired" in txt, txt[:600])
    check("...JSON: all_planned False, coverage_error set",
          r["all_planned"] is False and "TimeoutExpired" in (r["coverage_error"] or ""))

    # --- a group that already has a plan does not block the all-clear -------
    r = reconcile({"needs_plan": [{"component": "app-template"}],
                   "needs_plan_groups": [PLANNED_GROUP]})
    txt = mp.human(r, CFG)
    check("every group already planned -> all-clear", ALL_CLEAR in txt and r["all_planned"],
          txt[:600])

    # --- empty coverage + empty held -> all-clear (the control) -------------
    r = reconcile({"needs_plan": [], "needs_plan_groups": []})
    check("nothing anywhere -> all-clear (control: the check CAN pass)",
          ALL_CLEAR in mp.human(r, CFG))

    # --- a held PR without a plan still blocks it (the cross-check survives) -
    held = [{"number": 7, "dep": "ghcr.io/acme/x", "cur": "1.0.0", "new": "2.0.0",
             "gate": "type", "reason": "major"}]
    r = reconcile({"needs_plan": [], "needs_plan_groups": []}, held=held)
    check("held PR without a plan still blocks the all-clear",
          ALL_CLEAR not in mp.human(r, CFG) and r["needs_plan"], str(r["needs_plan"]))

    # --- get_coverage() parsing ---------------------------------------------
    _spec2 = importlib.util.spec_from_file_location("mp2", REPO / "runbooks/maintenance-plan.py")
    mp2 = importlib.util.module_from_spec(_spec2)
    _spec2.loader.exec_module(mp2)
    with tempfile.TemporaryDirectory() as d:
        def via(payload_text):
            p = Path(d) / "cov.json"
            p.write_text(payload_text)
            mp2.COVERAGE_JSON_PATH, mp2.COVERAGE_SKIP = str(p), None
            return mp2.get_coverage()
        data, err = via(json.dumps({"needs_plan": [], "needs_plan_groups": []}))
        check("get_coverage: a well-formed file is read", err is None and data is not None, err)
        data, err = via(json.dumps({"error": "version-check-current.md missing"}))
        check("get_coverage: an `error` payload is an error", data is None and "missing" in err)
        data, err = via(json.dumps({"needs_plan": []}))
        check("get_coverage: a payload WITHOUT needs_plan_groups is an error",
              data is None and "needs_plan_groups" in err, str(err))
        data, err = via("not json at all")
        check("get_coverage: garbage is an error", data is None and err, str(err))
        mp2.COVERAGE_SKIP = "--skip-coverage"
        data, err = mp2.get_coverage()
        check("get_coverage: a skip is reported, never an empty success",
              data is None and "--skip-coverage" in err, str(err))

    print()
    print("FAILURES:", FAILURES if FAILURES else "none")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
