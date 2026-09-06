"""Regression test: a RETIRED plan must not occupy a maintenance window.

Ground truth, both live in the repo on 2026-09-06 and both invisible:

  * `superset-pg-decommission` was `status: executed` (2026-09-05, commits
    c4694b13 + 90539942 in main) yet still carried
    `window: "sat-attended:2026-09-05"`, so it kept appearing in the
    reconciler's `scheduled` map as queued work.
  * `talos-1.13.9` was `status: superseded` (by talos-1.13.10) yet still
    carried `window: "sun-attended:2026-08-30"` — a slot whose date had
    already passed.

`unrun_plans()` already exempted both statuses from the MISSED-window
warning, which is exactly why nothing surfaced them: they were exempt from
the only check that looked at them, and no check looked at their OCCUPANCY.
A retired plan in the map inflates its slot's risk-load and time budget
against work that will never run.

The fix must satisfy BOTH halves, and this file commissions both:

  1. retired plans are excluded from window occupancy;
  2. they are still REPORTED, so removing them from the map does not make
     the file-hygiene miss invisible. Fixing a false positive by blinding
     the detector is the failure mode this repo has hit before
     (docs/sops/audit-script-correctness.md).

Run:  python3 runbooks/tests/test-retired-plan-occupancy.py
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("mp", REPO / "runbooks/maintenance-plan.py")
mp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mp)

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


# The two real files, as they stood before they were retired.
EXECUTED = {"plan_id": "superset-pg-decommission", "status": "executed",
            "window": "sat-attended:2026-09-05", "risk": "medium",
            "est_duration_min": 30}
SUPERSEDED = {"plan_id": "talos-1.13.9", "status": "superseded",
              "window": "sun-attended:2026-08-30", "risk": "medium",
              "est_duration_min": 60}
LIVE = {"plan_id": "talos-1.13.10", "status": "scheduled",
        "window": "sun-attended:2026-09-06", "risk": "medium",
        "est_duration_min": 70}
# A terminal plan that was retired PROPERLY (window already cleared) must not
# be reported — otherwise the new warning cries wolf on every programme index.
PROGRAMME = {"plan_id": "superset-bitnamilegacy-migration",
             "status": "superseded", "window": None, "risk": "high"}


def main() -> int:
    print("retired-plan occupancy:")

    got = {p["plan_id"] for p in mp.retired_still_windowed(
        [EXECUTED, SUPERSEDED, LIVE, PROGRAMME])}

    check("executed plan still holding a window is reported",
          "superset-pg-decommission" in got, f"got {got}")
    check("superseded plan still holding a window is reported",
          "talos-1.13.9" in got, f"got {got}")
    check("live scheduled plan is NOT reported",
          "talos-1.13.10" not in got, f"got {got}")
    check("properly-retired plan (window already null) is NOT reported",
          "superset-bitnamilegacy-migration" not in got, f"got {got}")

    # The occupancy half: the same statuses must be absent from the map the
    # capacity/interference checks read.
    def occupancy(plans):
        out: dict[str, list] = {}
        for p in plans:
            slot = p.get("window")
            if slot and p.get("status") not in mp.MISSED_EXEMPT_STATUSES:
                out.setdefault(slot, []).append(p)
        return out

    occ = occupancy([EXECUTED, SUPERSEDED, LIVE, PROGRAMME])
    check("retired plans do not occupy any slot",
          "sat-attended:2026-09-05" not in occ and "sun-attended:2026-08-30" not in occ,
          f"got slots {sorted(occ)}")
    check("live plan still occupies its slot",
          [p["plan_id"] for p in occ.get("sun-attended:2026-09-06", [])] == ["talos-1.13.10"],
          f"got slots {sorted(occ)}")

    # Commissioning guard: a validator that only ever passes is worthless.
    # Prove the rule can FAIL by feeding it the shape it must catch.
    check("rule is not inert (fires on at least one input)",
          len(got) == 2, f"expected exactly the 2 retired-windowed plans, got {got}")

    print()
    if FAILURES:
        print(f"FAILED ({len(FAILURES)}): {', '.join(FAILURES)}")
        return 1
    print("all retired-plan occupancy tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
