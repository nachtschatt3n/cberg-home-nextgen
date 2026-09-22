"""Regression test: a held update must never be matched to a TERMINAL plan
(F-9ec14462, 2026-09-22).

`reconcile()` asks "does this held update already have a plan?" by matching it
against EVERY plan file on disk. Plan files are long-lived — `executed`,
`superseded` and `reference` ones stay in the directory — so the match set was
full of plans that can never run again, and a dead file could absorb a live
held update.

Measured live on 2026-09-22 with the one held update in flight (PR #212,
`aqua:siderolabs/talos` 1.13.10 -> 1.14.1): BOTH talos plans match on the name
key `talos`, and load order handed the update to

    talos-1.14.0.md   status: superseded   target: v1.14.0     <- picked
    talos-1.14.1.md   status: draft        target: v1.14.1     <- the real plan

so the sweep filed the bump as STALE against a plan that will never run
("plan_target v1.14.0 / now_target 1.14.1"), reported it AMBIGUOUS every cycle,
and never mentioned the plan that will actually execute.

DIRECTION OF FAILURE. Narrowing a match set can only turn a match into a
non-match, and a non-match here means NEEDS A PLAN — loud, not silent. That is
the safe direction, and the third block below pins it: when the only candidate
is terminal, the held update must surface as needing a plan rather than
vanishing. The terminal files themselves stay on disk and stay audited
(plan_status, retired_still_windowed, the orphan and validation passes all
still read them); only the MATCH SET is narrowed.

THE FIXTURES ARE SYNTHETIC ON PURPOSE. The live talos pair is transient — the
moment talos-1.14.1 executes and its file is retired, a test anchored to it
asserts nothing. The shape (two plans for one component, the older one
terminal) is what recurs, so the shape is what is pinned.

Run:  python3 runbooks/tests/test-held-match-terminal-plans.py
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "runbooks"))
_spec = importlib.util.spec_from_file_location("mp", REPO / "runbooks/maintenance-plan.py")
mp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mp)

CFG = mp.load_windows()
TODAY = date(2026, 9, 22)
FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


def plan(pid, status, target, **kw):
    base = {"plan_id": pid, "_path": f"runbooks/maintenance/plans/{pid}.md",
            "component": "widget", "status": status,
            "current": "1.0.0", "target": target}
    base.update(kw)
    return base


# The live talos shape, de-identified: one component, an older terminal plan
# and the live one. `widget-2.0` sorts first, exactly as talos-1.14.0 did.
OLD = plan("widget-2.0", "superseded", "2.0.0")
NEW = plan("widget-2.1", "draft", "2.1.0")
HELD = {"number": 700, "dep": "ghcr.io/acme/widget", "cur": "1.0.0",
        "new": "2.1.0", "gate": "policy", "reason": "major — needs a plan"}


def reconcile(plans, held=(HELD,)):
    """reconcile() with every external reader stubbed: no gh, no cluster, no DB."""
    mp.load_plans = lambda cfg: [dict(p) for p in plans]
    mp.get_held = lambda: ([dict(h) for h in held], None)
    mp.cron_parity = lambda cfg: ([], False)
    mp.window_liveness_report = lambda cfg, today, now=None: {
        "missing": [], "stuck": [], "verified": False}
    return mp.reconcile(CFG, TODAY, decisions=None)


def main() -> int:
    print(__doc__.strip().splitlines()[0])
    print()

    # --- THE DEFECT ---------------------------------------------------------
    r = reconcile([OLD, NEW])
    check("the held update resolves to the LIVE plan, not the superseded one",
          r["stale"] == [] and r["ambiguous_matches"] == [] and r["needs_plan"] == [],
          f"stale={r['stale']} ambiguous={r['ambiguous_matches']} needs={r['needs_plan']}")

    # Commissioning: revert the fix (an empty terminal set = the pre-fix match
    # over ALL plans) and the same call must report the superseded plan again.
    _orig = mp.TERMINAL_PLAN_STATUSES
    try:
        mp.TERMINAL_PLAN_STATUSES = ()
        pre = reconcile([OLD, NEW])
        picked = (pre["ambiguous_matches"] or [{}])[0].get("picked")
        check("commissioning: with the fix reverted the SUPERSEDED plan is picked "
              "again (so this case is non-trivial)",
              picked == OLD["_path"] and pre["stale"] != [],
              f"picked={picked!r} stale={pre['stale']}")
    finally:
        mp.TERMINAL_PLAN_STATUSES = _orig

    # --- EVERY terminal status, not just `superseded` -----------------------
    for st in ("executed", "superseded", "reference"):
        r = reconcile([plan("widget-2.0", st, "2.0.0"), NEW])
        picked = r["ambiguous_matches"]
        check(f"a {st} plan is not a match candidate",
              not picked and r["stale"] == [], f"{picked} {r['stale']}")

    # --- THE SAFE DIRECTION: narrowing must never SILENCE --------------------
    r = reconcile([OLD])
    check("a held update whose ONLY plan is terminal surfaces as NEEDS A PLAN "
          "(never silently 'planned')",
          [n["key"] for n in r["needs_plan"]] == ["pr700"], str(r["needs_plan"]))

    # --- the files stay on disk and stay audited ----------------------------
    r = reconcile([OLD, NEW])
    check("the terminal plan is still counted in plan_status (file kept, not hidden)",
          r["plan_status"].get("superseded") == 1, str(r["plan_status"]))
    r = reconcile([plan("widget-2.0", "superseded", "2.0.0",
                        window="sat-attended:2026-09-26"), NEW])
    check("a terminal plan that still names a window is STILL reported "
          "(retired_still_windowed is not blinded by the match filter)",
          [x["plan_id"] for x in r["retired_windowed"]] == ["widget-2.0"],
          str(r["retired_windowed"]))

    # --- a live, non-terminal plan pair must still match normally ------------
    r = reconcile([NEW, plan("widget-2.2", "vetted", "2.2.0")])
    check("two NON-terminal candidates are still reported ambiguous "
          "(the warning is not collateral damage)",
          len(r["ambiguous_matches"]) == 1, str(r["ambiguous_matches"]))

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} -> {', '.join(FAILURES)}")
        return 1
    print("all tests passed")
    return 0


def test_pytest_entry() -> None:
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())
