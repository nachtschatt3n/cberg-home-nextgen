#!/usr/bin/env python3
"""Regression test: an external DISPLAY NAME must reach its plan's component key.

F-21865cc4 and F-3bc51210 (filed separately, same defect). The External
Infrastructure section of the version report names the node OS `Talos Linux`;
every talos plan carries `component: talos`. `assign_lane()` lowercased to
`talos linux`, `load_plans()` keyed `{talos}`, the sets never intersected, so
`match_plan()` returned None and Talos was reported NEEDS A PLAN on every
sweep — one redundant upgrade-planner dispatch per cycle — while an approved,
windowed plan sat in the plans directory.

WHY THE OBVIOUS FIX IS NOT THE FIX. F-3bc51210's Action prescribed routing
coverage.py through `lib.plan_matching`. That was EXECUTED before implementing
and does not work: `normalize_name("Talos Linux")` is `talos-linux`, which
still does not equal `talos`. `match_held_to_plan()` does return the plan, but
only via its SECOND tier, `version_pair_match` — a fallback that stops matching
the moment the plan's target drifts from the published version, which is
precisely the recurring condition here, and it would fail SILENTLY. Both
properties are pinned below: the name keys must intersect on their own, and the
match must survive target drift.

Normalisation still has to happen on BOTH sides. Measured 2026-09-21: it is the
identity for 39 of 40 plan components and 22 of 23 item components — only the
helm-drift plan's `flux/helm-controller` and `Talos Linux` move — so
normalising one side alone would have silently stopped matching the helm-drift
plan while fixing talos. That pair is pinned too.

Run: python3 runbooks/tests/test-coverage-component-alias.py
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "runbooks"))
from lib.plan_matching import normalize_name  # noqa: E402

_spec = importlib.util.spec_from_file_location("cov", REPO / "runbooks/coverage.py")
cov = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cov)
cov._release_tags_between = lambda *a, **k: ([], "stubbed")
cov._prerelease_digest_twin = lambda *a, **k: (None, "")

FAILURES: list[str] = []
POLICY = {"deny": []}


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


# The live pair, verbatim from version-check-current.md and talos-1.14.1.md.
TALOS_ITEM = {"component": "Talos Linux", "namespace": "external", "kind": "image",
              "current": "v1.13.10", "target": "v1.14.1", "type": "minor"}


def plan(component, target, status="draft", kind="infra", plan_id=None, also=()):
    return {"plan_id": plan_id or f"{component}-plan", "file": f"{component}.md",
            "keys": cov._name_keys(component), "also_keys": {normalize_name(a) for a in also},
            "status": status, "kind": kind, "current": "", "target": target}


def main() -> int:
    print("test-coverage-component-alias")

    # ── the corrected diagnosis, pinned so it cannot be re-litigated ───
    check("normalize_name alone does NOT bridge the pair (this is why "
          "F-3bc51210's prescribed Action was wrong)",
          normalize_name("Talos Linux") == "talos-linux" != "talos")
    check("the explicit alias does bridge it", "talos" in cov._name_keys("Talos Linux"))
    check("the raw lowercase spelling is still a key (nothing was traded away)",
          "talos linux" in cov._name_keys("Talos Linux"))

    # ── the live miss must now match ───────────────────────────────────
    p = plan("talos", "v1.14.1", plan_id="talos-1.14.1")
    lane, reason, _ = cov.assign_lane(TALOS_ITEM, POLICY, {}, [p])
    check("the live Talos item matches its plan", lane == "PLAN"
          and reason.startswith("plan exists: talos-1.14.1"), f"{lane}: {reason}")

    # ── and must survive TARGET DRIFT, which version_pair_match cannot ──
    drifted = plan("talos", "v1.14.5", plan_id="talos-1.14.5")
    lane, reason, _ = cov.assign_lane(TALOS_ITEM, POLICY, {}, [drifted])
    check("it still matches when the plan's target has DRIFTED past the "
          "published version (the property the version-pair fallback loses)",
          lane == "PLAN" and "plan exists" in reason, f"{lane}: {reason}")

    # ── the real plans directory, not a fixture ────────────────────────
    live = [p for p in cov.load_plans() if p["plan_id"].startswith("talos-")]
    check("the real plans dir still keys a talos plan this item can reach",
          any(cov._name_keys("Talos Linux") & p["keys"] for p in live),
          f"talos plans: {[(p['plan_id'], sorted(p['keys'])) for p in live]}")

    # ── BOTH SIDES normalized: the other component that moves ──────────
    hd = plan("flux/helm-controller", "1.2.3", kind="config")
    it = {"component": "flux/helm-controller", "kind": "config", "current": "1.2.2",
          "target": "1.2.3", "type": "patch"}
    got, _ = cov.match_plan(it, cov._name_keys(it["component"]), [hd])
    check("the OTHER component normalisation touches (`flux/helm-controller`) "
          "still matches its plan — one-sided normalisation would have broken it",
          got is not None)

    # ── SCOPE: the alias invents no other matches ──────────────────────
    other = {"component": "talosctl-cli", "kind": "image", "current": "1.13.10",
             "target": "1.14.1", "type": "minor"}
    got, _ = cov.match_plan(other, cov._name_keys(other["component"]), [p])
    check("an unrelated similarly-named component does NOT claim the talos plan",
          got is None)
    got, _ = cov.match_plan({"component": "grafana", "kind": "chart",
                             "current": "1.0", "target": "2.0", "type": "major"},
                            cov._name_keys("grafana"), [p])
    check("and neither does an unrelated component", got is None)

    # ── COMMISSIONING: straws that must fail the assertions above ──────
    def straw_raw(name):
        """The pre-fix key builder: raw lowercase only."""
        return {str(name or "").lower().strip()}

    def straw_normalize_only(name):
        """F-3bc51210's prescribed Action: normalise, no alias table."""
        raw = str(name or "").lower().strip()
        return {raw, normalize_name(raw)}

    orig = cov._name_keys
    try:
        for label, straw in (("pre-fix raw-lowercase keys", straw_raw),
                             ("normalize-only (the corrected-away Action)",
                              straw_normalize_only)):
            cov._name_keys = straw
            pp = {"plan_id": "talos-1.14.1", "file": "t.md", "keys": straw("talos"),
                  "also_keys": set(), "status": "draft", "kind": "infra",
                  "current": "", "target": "v1.14.1"}
            lane, _r, _ = cov.assign_lane(TALOS_ITEM, POLICY, {}, [pp])
            check(f"commissioning: {label} is caught (Talos falls through to "
                  f"needs_plan)", lane != "PLAN" or "plan exists" not in _r,
                  f"straw still matched: {lane}/{_r}")
    finally:
        cov._name_keys = orig

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
