#!/usr/bin/env python3
"""Regression test: an accepted risk and a DECLINED bump are both coverage.

F-a95ba973. `coverage.py --json` listed component=authentik, kind=image,
17.11-bookworm -> 18.6-bookworm under needs_plan with reason "major — needs an
assessed window plan". Three independent records already disposed of it:

  1. AR-113 (accepted, enabled): "STALE TARGET, NOT A HELD UPGRADE — the
     migration was EXECUTED 2026-08-20 (plan authentik-postgres-18); authentik
     now runs postgres:18.6-bookworm via deployment/authentik-pg". It DID
     suppress the matching version finding in the same run.
  2. runbooks/maintenance/plans/authentik-pg18-lockstep.md, whose `target`
     says "bundled/rollback postgresql image bump to 18.6-bookworm DECLINED —
     stays pinned 17.11-bookworm".
  3. The manifest pins 17.11-bookworm with an in-file instruction saying so.

coverage.py received `ar_holds` but used them ONLY for channel_hold, so an
ORDINARY acceptance could never reach the decision. The consequence: rule 4d
dispatches an upgrade-planner to plan an upgrade of a database the operator has
decided to DELETE, and the planner has to re-derive all three records to say no.

TWO PROPERTIES MATTER MORE THAN THE FIX ITSELF:
  * neither exemption may change a LANE — the item stays in PLAN so the lane
    counts stay honest; only the planner dispatch is suppressed;
  * both degrade toward MORE scrutiny. The policy DB is unreachable in the
    window agent (no SWEEP_PG_DSN), and an empty row set must mean "dispatch
    the planner", never "assume it is accepted".

Run: python3 runbooks/tests/test-coverage-ar-and-declined-plan.py
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("cov", REPO / "runbooks/coverage.py")
cov = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cov)

FAILURES: list[str] = []

# AR-113 exactly as stored, description first — it is a SUBSTRING NEEDLE
# matched against finding titles, not prose.
AR113 = ("AR-113",
         "authentik: image library/postgres 17.11-bookworm → 18.",
         "STALE TARGET, NOT A HELD UPGRADE - the migration was EXECUTED 2026-08-20")
AR_UNRELATED = ("AR-007", "Additional External Services Without Authentik", "…")

AUTHENTIK_PG = {"component": "authentik", "namespace": "kube-system",
                "kind": "image", "current": "17.11-bookworm",
                "target": "18.6-bookworm", "type": "major",
                "image_repos": ["library/postgres"]}
AUTHENTIK_CHART = {"component": "authentik", "namespace": "kube-system",
                   "kind": "chart", "current": "2026.8.2", "target": "2026.8.3",
                   "type": "patch"}


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


def main() -> int:
    print("test-coverage-ar-and-declined-plan")

    # ── the needle is matched against the title the sweep would emit ───
    titles = cov._item_finding_titles(AUTHENTIK_PG)
    check("the item's finding title is reconstructed in findings_writer's shape",
          "authentik: image library/postgres 17.11-bookworm → 18.6-bookworm" in titles,
          str(titles))
    check("THE defect: AR-113 is recognised as already disposing of this item",
          cov.ar_accepts_item(AUTHENTIK_PG, [AR113]) == "AR-113")
    check("an unrelated AR does not match", cov.ar_accepts_item(
        AUTHENTIK_PG, [AR_UNRELATED]) is None)
    check("the AR does NOT leak onto the component's other pending bump "
          "(the chart patch is untouched)",
          cov.ar_accepts_item(AUTHENTIK_CHART, [AR113]) is None)

    # ── fail-safe: no rows means dispatch the planner ──────────────────
    check("no policy rows (the window agent's DSN-less run) => no exemption",
          cov.ar_accepts_item(AUTHENTIK_PG, []) is None
          and cov.ar_accepts_item(AUTHENTIK_PG, None) is None)
    check("a trivially short needle can never match, however many findings it "
          "would hit in the DB", cov.ar_accepts_item(
              AUTHENTIK_PG, [("AR-X", "image", "…")]) is None)

    # ── the DECLINED plan, read from the REAL plans directory ──────────
    plans = cov.load_plans()
    dec = cov.plan_declines(AUTHENTIK_PG, plans)
    check("the live authentik-pg18-lockstep plan is recognised as DECLINING "
          "this exact bump", dec == "authentik-pg18-lockstep", f"got {dec!r}")
    lock = [p for p in plans if p["plan_id"] == "authentik-pg18-lockstep"]
    check("...even though its status is `executed` — a DECISION does not expire "
          "the way pending work does",
          bool(lock) and lock[0]["status"] in cov.DEAD_PLAN_STATUSES,
          f"status={lock and lock[0]['status']}")
    check("the decline does not spill onto the same component's chart bump",
          cov.plan_declines(AUTHENTIK_CHART, plans) is None)
    check("a plan with no decline marker declines nothing", cov.plan_declines(
        AUTHENTIK_PG, [{"plan_id": "p", "keys": {"authentik"}, "also_keys": set(),
                        "status": "draft", "kind": "image", "current": "17.11",
                        "target": "18.6-bookworm"}]) is None)
    check("a decline for a DIFFERENT version does not cover this item",
          cov.plan_declines(
              AUTHENTIK_PG,
              [{"plan_id": "q", "keys": {"authentik"}, "also_keys": set(),
                "status": "draft", "kind": "image", "current": "16.0",
                "target": "17.0 DECLINED"}]) is None)

    # ── neither exemption may move a lane ──────────────────────────────
    cov._release_tags_between = lambda *a, **k: ([], "stubbed")
    cov._prerelease_digest_twin = lambda *a, **k: (None, "")
    lane, reason, _ = cov.assign_lane(AUTHENTIK_PG, {"deny": []}, {}, [])
    check("the item is still PLAN-lane: an acceptance suppresses the PLANNER, "
          "never the lane, so counts stay honest", lane == "PLAN",
          f"{lane}: {reason}")

    # ── COMMISSIONING ──────────────────────────────────────────────────
    def straw_name_only(item, plans_):
        """Over-broad: any plan for this component that mentions a decline."""
        keys = cov._name_keys(str(item.get("component") or ""))
        for p in plans_:
            if p["keys"] & keys and cov._DECLINE_RE.search(
                    f"{p.get('target') or ''} {p.get('current') or ''}"):
                return p["plan_id"]
        return None

    check("commissioning: a version-blind decline check is caught — it would "
          "suppress the planner for the authentik CHART bump too",
          straw_name_only(AUTHENTIK_CHART, plans) is not None,
          "the chart assertion cannot discriminate")

    def straw_substring_anywhere(item, rows):
        """Over-broad: match the needle against the component name alone."""
        for ar_id, desc, _j in rows or []:
            if str(item.get("component", "")).lower() in str(desc).lower():
                return ar_id
        return None

    check("commissioning: matching on the component name alone is caught — it "
          "would accept the chart bump on AR-113's authority",
          straw_substring_anywhere(AUTHENTIK_CHART, [AR113]) == "AR-113")

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
