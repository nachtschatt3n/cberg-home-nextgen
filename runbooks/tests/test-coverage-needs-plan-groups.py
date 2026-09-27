#!/usr/bin/env python3
"""Regression test: coverage.py groups `needs_plan` into planner targets.

2026-09-27 (throughput program item C). `needs_plan` is one row per component;
a planner is one agent writing one plan. Seven `redis:*-alpine` consumers moving
to the same patch are ONE change, and every app-template wrapper is one chart
bump. Dispatching per row burned a planner per consumer and produced plans that
had to be kept in step by hand, so the sweep now dispatches per GROUP from
`needs_plan_groups`, security-driven groups first, never for a group whose live
plan already exists.

This suite pins the grouping rules (G1 image fleet, G2 same component, G3 chart
family, G4 app-template), the plan-exists detection (including that a TERMINAL
plan does not count), the security-first ordering, and the over-capture limits
(different target, different chart family, different repo never merge).

Run: python3 runbooks/tests/test-coverage-needs-plan-groups.py
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("cov", REPO / "runbooks/coverage.py")
cov = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cov)

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


def img(comp, cur, tgt, repos, reason="G3 could not verify the release notes", **kw):
    return {"component": comp, "namespace": "ns", "kind": "image", "current": cur,
            "target": tgt, "image_repo": None, "image_repos": list(repos),
            "lane": "PLAN", "reason": reason, **kw}


def chart(comp, cur, tgt, reason="0.x release-line move", **kw):
    return {"component": comp, "namespace": "ns", "kind": "chart", "current": cur,
            "target": tgt, "lane": "PLAN", "reason": reason, **kw}


def plan(pid, comp, target, status="draft", also=()):
    keys = cov._name_keys(comp)
    if "app-template" in pid:
        keys.add("app-template")
    also_keys: set = set()
    for a in also:
        also_keys |= cov._name_keys(a)
    return {"plan_id": pid, "file": f"{pid}.md", "keys": keys, "also_keys": also_keys,
            "status": status, "kind": "", "current": "", "target": target}


REDIS = [img(c, "8.10.1-alpine", "8.10.2-alpine", ["redis"]) for c in
         ("superset-redis-official", "tube-archivist-redis", "immich-redis",
          "nextcloud-redis", "paperless-redis", "sure-redis", "redis")]
APPT = [chart("app-template (≈all app-template wrappers)", "5.1.0", "5.2.1",
              reason="minor on a deny-listed chart")]
FLUX = [chart("flux-instance", "0.57.0", "0.60.0"), chart("flux-operator", "0.57.0", "0.60.0")]
LIBRE = [chart("librechat", "2.0.7", "2.0.14")]
PAPERCLIP = [img("paperclip", "24.04", "26.04", ["ubuntu"], reason="major")]


def by_id(groups):
    return {g["group_id"]: g for g in groups}


def main() -> int:
    print(__doc__.strip().splitlines()[0])
    print()

    # --- G1: the redis fleet is ONE target, not seven ------------------------
    g = by_id(cov.group_needs_plan(REDIS, plans=[]))
    check("seven redis:*-alpine consumers collapse into ONE group",
          list(g) == ["redis-fleet-8.10.2"], str(list(g)))
    rf = g.get("redis-fleet-8.10.2", {})
    check("...an image-fleet of size 7, to dispatch",
          rf.get("group_kind") == "image-fleet" and rf.get("size") == 7 and rf.get("dispatch"),
          str(rf))

    # --- plan exists: the slug matches the plan file -> never re-dispatched ---
    live = [plan("redis-fleet-8.10.2", "redis", "redis:8.10.2-alpine on all 8 consumers")]
    rf = by_id(cov.group_needs_plan(REDIS, live))["redis-fleet-8.10.2"]
    check("a live plan named like the group suppresses the dispatch",
          rf["plan"] == "redis-fleet-8.10.2" and rf["dispatch"] is False, str(rf))

    # a TERMINAL plan is history — the next bump is uncovered again
    dead = [plan("redis-fleet-8.10.2", "redis", "redis:8.10.2-alpine", status="executed")]
    rf = by_id(cov.group_needs_plan(REDIS, dead))["redis-fleet-8.10.2"]
    check("an EXECUTED plan does not count as coverage", rf["dispatch"] is True, str(rf))

    # a live plan for an OLDER target does not cover the new bump
    old = [plan("redis-8.10.1", "redis", "redis:8.10.1-alpine")]
    rf = by_id(cov.group_needs_plan(REDIS, old))["redis-fleet-8.10.2"]
    check("a live plan at a DIFFERENT version does not cover the group",
          rf["dispatch"] is True, str(rf))

    # plan target text naming member + version covers a lockstep app leg
    ow = [img("open-webui", "0.11.3", "0.11.4", ["ghcr.io/open-webui/open-webui", "redis"],
              reason="lockstep — the open-webui image is PLAN")]
    live2 = [plan("redis-fleet-8.10.2", "redis",
                  "redis:8.10.2-alpine on all 8 consumers + ghcr.io/open-webui/open-webui 0.11.4")]
    gw = by_id(cov.group_needs_plan(ow, live2))["open-webui-0.11.4"]
    check("a plan whose target names the component AND its version covers it",
          gw["plan"] == "redis-fleet-8.10.2" and not gw["dispatch"], str(gw))

    # --- G4 app-template, G3 chart family, singles ---------------------------
    everything = REDIS + APPT + FLUX + LIBRE + PAPERCLIP
    g = by_id(cov.group_needs_plan(everything, plans=[]))
    check("the mixed set yields exactly five targets",
          sorted(g) == sorted(["redis-fleet-8.10.2", "app-template-5.2.1",
                               "flux-fleet-0.60.0", "librechat-2.0.14", "paperclip-26.04"]),
          str(sorted(g)))
    check("app-template is one group of kind app-template",
          g.get("app-template-5.2.1", {}).get("group_kind") == "app-template")
    check("flux-instance + flux-operator are one chart-family group",
          g.get("flux-fleet-0.60.0", {}).get("size") == 2)
    appt_plan = [plan("app-template-5.2.1", "app-template", "app-template 5.2.1")]
    g2 = by_id(cov.group_needs_plan(APPT, appt_plan))
    check("the app-template plan file covers the app-template group",
          g2["app-template-5.2.1"]["dispatch"] is False, str(g2))

    # --- over-capture limits -------------------------------------------------
    split = [img("a-redis", "8.10.1-alpine", "8.10.2-alpine", ["redis"]),
             img("b-redis", "8.8.0-alpine", "8.10.3-alpine", ["redis"])]
    check("same repo but a DIFFERENT target stays two groups",
          len(cov.group_needs_plan(split, [])) == 2)
    diffrepo = [img("x", "1.0.0", "1.1.0", ["ghcr.io/acme/x"]),
                img("y", "1.0.0", "1.1.0", ["ghcr.io/acme/y"])]
    check("same version pair on DIFFERENT repos stays two groups",
          len(cov.group_needs_plan(diffrepo, [])) == 2)
    charts = [chart("prometheus-x", "1.0.0", "1.1.0"), chart("grafana-y", "1.0.0", "1.1.0")]
    check("charts with the same versions but different families stay separate",
          len(cov.group_needs_plan(charts, [])) == 2)

    # --- security-first ordering ---------------------------------------------
    sec_rows = [{"finding_id": "F-00000001", "repo": "ubuntu", "tag": "24.04"}]
    order = [x["group_id"] for x in cov.group_needs_plan(everything, [], sec_rows)]
    check("a group named by an open fixable security row sorts FIRST",
          order[0] == "paperclip-26.04", str(order))
    pc = by_id(cov.group_needs_plan(everything, [], sec_rows))["paperclip-26.04"]
    check("...and carries the finding id as evidence",
          pc["security_driven"] and "F-00000001" in pc["security_evidence"], str(pc))
    stale_tag = [{"finding_id": "F-00000002", "repo": "ubuntu", "tag": "22.04"}]
    pc = by_id(cov.group_needs_plan(PAPERCLIP, [], stale_tag))["paperclip-26.04"]
    check("a security row on a DIFFERENT current tag does not mark the group",
          not pc["security_driven"], str(pc))
    marked = [img("m", "1.0.0", "2.0.0", ["ghcr.io/acme/m"],
                  reason="major — upstream security advisory fixed in 2.0.0")]
    order = [x["group_id"] for x in cov.group_needs_plan(everything + marked, [])]
    check("a security marker in the member reason sorts it first", order[0] == "m-2.0.0",
          str(order))

    # plan-exists groups sort after dispatchable ones (same security tier)
    order = cov.group_needs_plan(REDIS + LIBRE, live)
    check("dispatchable groups precede already-planned ones",
          [x["dispatch"] for x in order] == [True, False], str(order))

    check("empty needs_plan -> empty groups", cov.group_needs_plan([], []) == [])

    # --- human() renders the dispatch list -----------------------------------
    r = {"counts": {k: 0 for k in ("AUTO", "PLAN", "REBUILD", "HELD", "CRACK")},
         "covered": True, "needs_plan": REDIS,
         "needs_plan_groups": cov.group_needs_plan(REDIS, []),
         "planner_dispatch_cap": 5, "lanes": {"REBUILD": []}, "cracks": []}
    out = cov.human(r)
    check("human() prints PLANNER TARGETS with the dispatch marker",
          "PLANNER TARGETS (1 group(s), 1 to dispatch, cap 5/sweep" in out
          and "redis-fleet-8.10.2" in out and "→ DISPATCH" in out, out)

    print()
    print("FAILURES:", FAILURES if FAILURES else "none")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
