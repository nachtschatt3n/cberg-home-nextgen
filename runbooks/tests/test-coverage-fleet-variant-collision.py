#!/usr/bin/env python3
"""Regression test (F-a9351f4e): an image-fleet group id must not collide with a
live plan that does not cover it, and a tag VARIANT is part of the identity.

Reproduced 2026-11-02: three `python:3.15.2-alpine` consumers and fourteen
`python:3.15.2-slim` siblings all collapsed into one group `python-fleet-3.15.2`
(`_dedupe_tag` keeps only the version core, so alpine and slim merged). The live
plan `python-fleet-3.15.2` targets `python:3.15.2-slim` for exactly three
consumers and enumerates them in `also_covers`. Because the group id equalled
the plan's file stem, `_group_plan` declared the whole group covered:
  * the alpine trio read as covered by a plan that excludes them, and
  * a planner dispatched for them would have been told to write
    `plans/python-fleet-3.15.2.md` -- overwriting the live plan.

Contract pinned here:
  1. G1 does not merge rows whose tag variant differs (alpine vs slim);
  2. where one (image, version) has several variants, or a live plan already owns
     the plain id without covering the group, the id carries the variant
     (`python-fleet-3.15.2-alpine`);
  3. a plan with an enumerated `also_covers` covers only members it names;
  4. a plan whose target names another variant does not cover this one;
  5. the plan written for the qualified id covers it on the next sweep;
  6. the unambiguous case keeps the plain id (`redis-fleet-8.10.2`).

Run: python3 runbooks/tests/test-coverage-fleet-variant-collision.py
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("cov", REPO / "runbooks/coverage.py")
cov = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cov)

FAILURES: list[str] = []
PY = ["docker.io/library/python"]


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


def img(comp, cur, tgt, repos):
    return {"component": comp, "namespace": "ns", "kind": "image", "current": cur,
            "target": tgt, "image_repo": None, "image_repos": list(repos),
            "lane": "PLAN", "reason": "G3 could not verify the release notes"}


def plan(pid, comp, target, also=(), status="draft"):
    also_keys: set = set()
    for a in also:
        also_keys |= cov._name_keys(a)
    return {"plan_id": pid, "file": f"{pid}.md", "keys": cov._name_keys(comp),
            "also_keys": also_keys, "status": status, "kind": "image", "current": "",
            "target": target}


ALPINE = [img(c, "3.14.10-alpine", "3.15.2-alpine", PY)
          for c in ("icloud-sync-probe", "crash-ghost-reaper", "elasticsearch-obs-recovery")]
NAMED_SLIM = [img(c, "3.14.10-slim", "3.15.2-slim", PY)
              for c in ("openclaw-probe", "mcpo", "mealie-shopping-sync")]
OTHER_SLIM = [img(f"slim-sibling-{i}", "3.14.10-slim", "3.15.2-slim", PY) for i in range(4)]
SLIM_PLAN = plan("python-fleet-3.15.2", "python",
                 "python:3.15.2-slim on the same 3 consumers",
                 also=["openclaw-probe", "mcpo", "mealie-shopping-sync"])


def by_id(groups):
    return {g["group_id"]: g for g in groups}


def members(g):
    return sorted(m["component"] for m in g["members"])


def main() -> int:
    print(__doc__.strip().splitlines()[0])
    print()

    print("1. variants never merge")
    groups = cov.group_needs_plan(ALPINE + NAMED_SLIM + OTHER_SLIM, plans=[])
    check("alpine and slim rows of one (image, version) form TWO groups",
          len(groups) == 2, str([g["group_id"] for g in groups]))
    for g in groups:
        tags = {m["target"] for m in g["members"]}
        check(f"group {g['group_id']} is single-variant", len(tags) == 1, str(tags))
    ids = [g["group_id"] for g in groups]
    check("the two groups have DISTINCT ids", len(set(ids)) == 2, str(ids))
    check("ids carry the variant when several exist for one version",
          sorted(ids) == ["python-fleet-3.15.2-alpine", "python-fleet-3.15.2-slim"], str(ids))

    print("2. a live plan that owns the plain id but does not cover the group")
    g = by_id(cov.group_needs_plan(ALPINE, [SLIM_PLAN]))
    check("alpine trio is NOT reported covered by the slim plan",
          list(g) == ["python-fleet-3.15.2-alpine"] and g["python-fleet-3.15.2-alpine"]["dispatch"] is True
          and g["python-fleet-3.15.2-alpine"]["plan"] is None, str(g))
    check("its id does not equal the live plan stem (no overwrite of the plan file)",
          "python-fleet-3.15.2" not in g, str(list(g)))

    print("3. an enumerated also_covers plan covers only members it names")
    g = by_id(cov.group_needs_plan(NAMED_SLIM, [SLIM_PLAN]))
    check("the three named slim consumers ARE covered (plain id, stem match kept)",
          g["python-fleet-3.15.2"]["plan"] == "python-fleet-3.15.2"
          and g["python-fleet-3.15.2"]["dispatch"] is False, str(g))
    mixed = cov.group_needs_plan(NAMED_SLIM + OTHER_SLIM, [SLIM_PLAN])
    check("named + unnamed slim siblings are NOT covered as a whole",
          len(mixed) == 1 and mixed[0]["dispatch"] is True and mixed[0]["plan"] is None,
          str(mixed))
    check("...and the group id no longer equals the live plan's stem",
          mixed[0]["group_id"] != "python-fleet-3.15.2", mixed[0]["group_id"])

    print("4. a plan whose target names another variant does not cover this one")
    variant_only = plan("python-fleet-3.15.2", "python", "python:3.15.2-slim")  # no also_covers
    g = by_id(cov.group_needs_plan(ALPINE, [variant_only]))
    check("slim-targeting plan, no enumeration: alpine group still dispatches",
          all(x["dispatch"] for x in g.values()), str(g))
    g = by_id(cov.group_needs_plan(NAMED_SLIM + OTHER_SLIM, [variant_only]))
    check("...but the SAME-variant fleet is covered by the unenumerated plan (fleet-wide)",
          g["python-fleet-3.15.2"]["dispatch"] is False, str(g))

    print("5. the plan written for the qualified id covers it next sweep")
    alpine_plan = plan("python-fleet-3.15.2-alpine", "python", "python:3.15.2-alpine on 3 consumers")
    g = by_id(cov.group_needs_plan(ALPINE, [SLIM_PLAN, alpine_plan]))
    check("alpine group covered by python-fleet-3.15.2-alpine",
          g["python-fleet-3.15.2-alpine"]["plan"] == "python-fleet-3.15.2-alpine"
          and g["python-fleet-3.15.2-alpine"]["dispatch"] is False, str(g))

    print("6. unambiguous fleets keep the plain id")
    redis = [img(c, "8.10.1-alpine", "8.10.2-alpine", ["redis"])
             for c in ("sure-redis", "immich-redis", "redis")]
    check("redis-fleet-8.10.2 unchanged",
          [x["group_id"] for x in cov.group_needs_plan(redis, [])] == ["redis-fleet-8.10.2"])
    rplan = plan("redis-fleet-8.10.2", "redis", "redis:8.10.2-alpine on all consumers")
    check("a redis-fleet plan without an enumeration still covers the whole fleet",
          cov.group_needs_plan(redis, [rplan])[0]["dispatch"] is False)
    mixed_ver = [img("a", "1.0.0", "1.1.0", ["ghcr.io/acme/x"]),
                 img("b", "1.0.0", "1.1.0", ["ghcr.io/acme/x"])]
    check("variant-less fleet keeps the plain id",
          [x["group_id"] for x in cov.group_needs_plan(mixed_ver, [])] == ["x-fleet-1.1.0"])

    print()
    print("FAILURES:", FAILURES if FAILURES else "none")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
