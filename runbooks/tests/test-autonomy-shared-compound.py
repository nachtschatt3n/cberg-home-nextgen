"""Regression test: the shared-infrastructure guard must see COMPOUND keys
(F-724dc4df, 2026-09-22).

`execution_class()` refuses to pre-approve unattended execution for a plan that
touches shared infrastructure. The test was a bare set intersection:

    shared & {x.lower() for x in spec.get("forbid_shared", [])}   # [storage, longhorn]

but `touches.shared` is an INTERSECTION KEY and the house spells it COMPOUND —
`storage/longhorn`, `gateway/envoy`, `cni/cilium`, `dns-internal`,
`k8s-gateway DNS`. Measured over the live plan corpus on 2026-09-22: 19 distinct
`touches.shared` values, of which exactly ONE (`storage`) intersected the
policy list. The guard was inert for every key that qualified itself — including
`storage/longhorn`, the very substrate the policy names.

The visible consequence: wazuh-2xx-edge-coverage (shared: [gateway/envoy],
capability_change: false, rollback_class: git-revert, needs_reboot: false,
risk: medium) derives AUTO-NIGHT on mechanics. It is held back only by a
hand-written `autonomy_override: human-gated` — that is, by an author
remembering, which is the job the guard exists to do.

Two halves to the fix, and both are needed: tokenise the plan's keys (so
`gateway/envoy` yields `gateway`), and widen the vocabulary (so `gateway` is
forbidden at all). Either alone leaves the wazuh case deriving AUTO-NIGHT.

OVER-MATCHING IS THE SAFE DIRECTION — a hit means HUMAN-GATED, the default this
module fails toward — but it must not become "gate everything", or the classes
would be dead letters. The second block pins that: ordinary app-level keys
(media, monitoring, postgresql, igpu-i915) must still derive AUTO-NIGHT.

Run:  python3 runbooks/tests/test-autonomy-shared-compound.py
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "runbooks"))
_spec = importlib.util.spec_from_file_location("mp", REPO / "runbooks/maintenance-plan.py")
mp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mp)

# The shipped policy, read the way the script reads it.
LIVE_POLICY = mp.load_autonomy_policy()
LIVE_PLANS = mp.load_plans(mp.load_windows())
FLOOR = set(mp.SHARED_INFRA_FLOOR)

# A fixture mirroring the live auto-night class, so the mechanism is tested
# independently of what the YAML happens to say today.
POLICY = {"classes": {"auto-night": {
    "require": {"capability_change": False, "rollback_class": "git-revert",
                "needs_reboot": False},
    "forbid_shared": ["storage", "longhorn"],
    "forbid_risk": ["high"]}}}

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


def plan(shared, **kw):
    base = {"plan_id": "t", "capability_change": False, "risk": "medium",
            "rollback_class": "git-revert", "needs_reboot": False,
            "touches": {"shared": shared}}
    base.update(kw)
    return base


def cls(shared, policy=POLICY, **kw):
    return mp.execution_class(plan(shared, **kw), policy)[0]


def main() -> int:
    print(__doc__.strip().splitlines()[0])
    print()

    # --- THE DEFECT: every compound spelling in the live corpus -------------
    for key in ("gateway/envoy", "gateway/envoy-internal", "cni/cilium",
                "storage/longhorn", "dns-internal", "cni-adjacent",
                "k8s-gateway DNS", "etcd"):
        check(f"shared {key!r} human-gates an otherwise pre-approved plan",
              cls([key]) == "HUMAN-GATED", f"got {cls([key])}")

    # Commissioning: restore BOTH pre-fix halves (no tokenising, policy list
    # only) and the wazuh shape must derive AUTO-NIGHT again.
    _tok, _forb = mp.shared_tokens, mp.forbidden_shared
    try:
        mp.shared_tokens = lambda vals: {str(x).lower() for x in (vals or [])}
        mp.forbidden_shared = lambda spec: {str(x).lower()
                                            for x in spec.get("forbid_shared", [])}
        check("commissioning: with the fix reverted, shared 'gateway/envoy' "
              "derives AUTO-NIGHT again (so this case is non-trivial)",
              cls(["gateway/envoy"]) == "AUTO-NIGHT", f"got {cls(['gateway/envoy'])}")
        check("commissioning: even 'storage/longhorn' escaped the policy's own "
              "[storage, longhorn] list",
              cls(["storage/longhorn"]) == "AUTO-NIGHT",
              f"got {cls(['storage/longhorn'])}")
    finally:
        mp.shared_tokens, mp.forbidden_shared = _tok, _forb

    # --- it must NOT become "gate everything" -------------------------------
    for key in ("media", "monitoring", "postgresql", "igpu-i915",
                "identity-provider", "flux-sources", "cert-manager"):
        check(f"app-level shared key {key!r} still derives AUTO-NIGHT",
              cls([key]) == "AUTO-NIGHT", f"got {cls([key])}")
    check("no shared keys at all still derives AUTO-NIGHT", cls([]) == "AUTO-NIGHT")
    check("a null touches.shared does not crash", cls(None) == "AUTO-NIGHT")
    check("a plan with no touches block at all does not crash",
          mp.execution_class({"plan_id": "t", "capability_change": False,
                              "rollback_class": "git-revert",
                              "needs_reboot": False}, POLICY)[0] == "AUTO-NIGHT")

    # --- the floor is a floor: a class may widen it, never narrow it ---------
    bare = {"classes": {"auto-night": {"require": POLICY["classes"]["auto-night"]["require"]}}}
    check("a class declaring NO forbid_shared still cannot take `storage`",
          cls(["storage"], policy=bare) == "HUMAN-GATED")
    check("a class declaring an EMPTY forbid_shared still cannot take `etcd`",
          cls(["etcd"], policy={"classes": {"auto-night": {
              "require": POLICY["classes"]["auto-night"]["require"],
              "forbid_shared": []}}}) == "HUMAN-GATED")
    widened = {"classes": {"auto-night": {
        "require": POLICY["classes"]["auto-night"]["require"],
        "forbid_shared": ["media"]}}}
    check("a class may still WIDEN the list with its own entries",
          cls(["media"], policy=widened) == "HUMAN-GATED")
    check("the kill switch is untouched: no classes => HUMAN-GATED",
          mp.execution_class(plan([]), {"classes": {}})[0] == "HUMAN-GATED")

    # --- tokeniser contract --------------------------------------------------
    check("the whole value is kept, so a literal policy entry still matches",
          "storage/longhorn" in mp.shared_tokens(["storage/longhorn"]))
    check("slash-separated segments become tokens",
          {"gateway", "envoy"} <= mp.shared_tokens(["gateway/envoy"]))
    check("empty and blank entries are dropped",
          mp.shared_tokens(["", "   ", None]) == set(),
          str(mp.shared_tokens(["", "   ", None])))

    # --- THE LIVE POLICY + THE LIVE CORPUS -----------------------------------
    # A fixture tests the mechanism; only the real files test the deployment
    # (the lesson of the forbid_risk near-miss in test-autonomy-class.py).
    live_auto = {n: s for n, s in (LIVE_POLICY.get("classes") or {}).items()
                 if n.startswith("auto")}
    check("the live policy still defines auto classes", bool(live_auto), str(list(live_auto)))
    for name, spec in sorted(live_auto.items()):
        missing = sorted(FLOOR - mp.forbidden_shared(spec))
        check(f"live class {name!r} forbids every floor substrate", not missing,
              f"missing {missing}")

    shared_plans = [p for p in LIVE_PLANS
                    if mp.shared_tokens((p.get("touches") or {}).get("shared")) & FLOOR]
    print(f"  ---- live corpus: {len(shared_plans)} of {len(LIVE_PLANS)} plans name a "
          f"floor-level shared substrate ----")
    check("the live corpus still exercises this guard (a zero here means the "
          "instrument stopped measuring, not that the repo got clean)",
          len(shared_plans) > 0, f"{len(shared_plans)}/{len(LIVE_PLANS)}")
    for p in shared_plans:
        # autonomy_override is the AUTHOR remembering; strip it so the
        # MECHANISM is what is under test.
        stripped = {k: v for k, v in p.items() if k != "autonomy_override"}
        got = mp.execution_class(stripped, LIVE_POLICY)[0]
        check(f"live plan {p.get('plan_id')} cannot derive AUTO-* on mechanics alone "
              f"(shared={(p.get('touches') or {}).get('shared')})",
              not got.startswith("AUTO"), f"got {got}")

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
