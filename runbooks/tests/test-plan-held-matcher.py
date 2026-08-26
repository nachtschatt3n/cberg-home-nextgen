"""Regression tests for lib/plan_matching — the plan↔held-update matcher.

Ground truth is the live 2026-08-26 miss: the talos plan carried `pr: null`
(the Renovate PR is deliberately never merged — the upgrade is a Talos CR
operation) and `component: "Talos Linux"`, while the held update was
`{number: 208, dep: "ghcr.io/siderolabs/installer"}`. The old inline matcher
keyed plans by PR string and by the dep's image basename (`installer`); both
missed, so an approved, windowed plan was reported "NEEDS A PLAN" on every
sweep and rule 4d dispatched a redundant upgrade-planner every cycle.

No name key can bridge that pair — nothing relates "Talos Linux" to
"installer" except the versions themselves, which is why the matcher has a
version-pair tier and why these tests pin it.

Run:  python3 runbooks/tests/test-plan-held-matcher.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.plan_matching import (  # noqa: E402
    held_match_keys, match_held_to_plan, normalize_name, plan_match_keys,
    target_covers, version_pair_match,
)

# The exact live pair that was missed for a week.
TALOS_PLAN = {
    "plan_id": "talos-1.13.9", "pr": None, "component": "Talos Linux",
    "current": "talosVersion v1.13.8 on all 3 nodes (k8s-nuc14-01/02/03)",
    "target": "talosVersion v1.13.9", "_path": "plans/talos-1.13.9.md",
}
TALOS_HELD = {
    "number": 208, "dep": "ghcr.io/siderolabs/installer",
    "cur": "v1.13.8", "new": "v1.13.9",
}

FAILURES: list[str] = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + ("" if cond else f"  {detail}"))
    if not cond:
        FAILURES.append(name)


def main() -> int:
    print("test-plan-held-matcher")

    # --- the live miss MUST match (via the version-pair tier)
    plan, amb = match_held_to_plan(TALOS_HELD, [TALOS_PLAN])
    check("live talos case matches", plan is TALOS_PLAN and not amb)
    check("  ...and only via version pair (name keys correctly disjoint)",
          not (plan_match_keys(TALOS_PLAN) & held_match_keys(TALOS_HELD))
          and version_pair_match(TALOS_PLAN, TALOS_HELD))

    # --- PR tier: authoritative when both sides carry it
    p = dict(TALOS_PLAN, pr=208, current="prose only", target="prose only")
    plan, _ = match_held_to_plan(TALOS_HELD, [p])
    check("PR number alone matches", plan is p)

    # --- name tier: normalized component vs dep basename
    p = {"plan_id": "unpoller-v4", "pr": None, "component": "Unpoller",
         "current": "", "target": ""}
    h = {"number": 300, "dep": "ghcr.io/unpoller/unpoller", "cur": "2.0", "new": "4.0"}
    plan, _ = match_held_to_plan(h, [p])
    check("normalized name matches dep basename", plan is p)
    check("normalize_name collapses punctuation",
          normalize_name("Talos Linux") == "talos-linux")

    # --- NEGATIVE: an unrelated plan must NOT match (matcher can say no)
    other = {"plan_id": "superset-6.1.0", "pr": None, "component": "superset",
             "current": "5.0.0", "target": "6.1.0"}
    plan, _ = match_held_to_plan(TALOS_HELD, [other])
    check("unrelated plan does not match", plan is None)

    # --- version-pair requires BOTH ends (target alone is not identity)
    half = dict(TALOS_PLAN, current="prose with no version tokens at all")
    check("version pair needs cur AND new", not version_pair_match(half, TALOS_HELD))

    # --- ambiguity is surfaced, never silently resolved
    twin = dict(TALOS_PLAN, plan_id="talos-1.13.9-copy", _path="plans/copy.md")
    plan, amb = match_held_to_plan(TALOS_HELD, [TALOS_PLAN, twin])
    check("ambiguous match surfaced", plan is TALOS_PLAN and amb == [twin])

    # --- staleness: target-end only
    check("target_covers: current-drift is fine",
          target_covers(dict(TALOS_PLAN, current="no versions here"), TALOS_HELD))
    check("target_covers: upstream moved on -> stale",
          not target_covers(TALOS_PLAN, dict(TALOS_HELD, new="v1.13.10")))

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} -> {', '.join(FAILURES)}")
        return 1
    print("all tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
