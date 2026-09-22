"""Regression test: an age-cooldown hold is not a missing plan
(F-50f5de70, 2026-09-22).

auto-update.py evaluates its gates IN ORDER — draft, parse, type, policy, age,
breaking, ci — and reports the first one that holds. So `gate: "age"` is
reached only by an update that has ALREADY passed the update-type and
deny-list gates: it is safe-lane work whose sole impediment is the
`minimum_release_age_hours` timer, and the maintenance-window agent merges it
at Step 0 of the next window once the timer elapses.

`reconcile()` did not read the gate. Every held update without a plan went into
`needs_plan`, which the sweep renders as

    NEEDS A PLAN (n) — dispatch an upgrade-planner-agent for each:

so rule 4d dispatched a planner agent to write an executable maintenance plan
for a patch bump that merges itself in a few hours — and files a plan nobody
will ever run.

NOT INVISIBLE, RE-LABELLED. The same gate also holds an update whose release
age is UNKNOWN on both measures ("cannot prove the cooldown elapsed — holding"),
which clears only when a human looks. Dropping age holds would trade a false
"needs a plan" for a silent disappearance, so they move to their own bucket
that `human()` prints with its reason — the last block here pins that, because
a fix that blinds the detector is the failure this suite exists to prevent.

Run:  python3 runbooks/tests/test-held-age-cooldown-no-plan.py
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


def held(number, gate, reason="r", dep=None, cur="1.0.0", new="1.0.1"):
    return {"number": number, "dep": dep or f"ghcr.io/acme/app{number}",
            "cur": cur, "new": new, "gate": gate, "reason": reason}


# Verbatim from auto-update.py's age_gate(): the two shapes that share `age`.
COOLDOWN = held(9001, "age", "release only 6h old via registry publish date "
                             "(< 72h cooldown); auto-merges after the cooldown")
AGE_UNKNOWN = held(9002, "age", "release age UNKNOWN on both measures (cannot "
                                "prove the 72h cooldown elapsed) — holding")
POLICY_HOLD = held(9003, "policy", "deny-list: held for a maintenance window")


def reconcile(held_rows, plans=()):
    """reconcile() with every external reader stubbed: no gh, no cluster, no DB."""
    mp.load_plans = lambda cfg: [dict(p) for p in plans]
    mp.get_held = lambda: ([dict(h) for h in held_rows], None)
    mp.cron_parity = lambda cfg: ([], False)
    mp.window_liveness_report = lambda cfg, today, now=None: {
        "missing": [], "stuck": [], "verified": False}
    return mp.reconcile(CFG, TODAY, decisions=None)


def main() -> int:
    print(__doc__.strip().splitlines()[0])
    print()

    # --- THE DEFECT ---------------------------------------------------------
    r = reconcile([COOLDOWN, POLICY_HOLD])
    check("an age-cooldown hold does NOT ask for a plan",
          [n["key"] for n in r["needs_plan"]] == ["pr9003"], str(r["needs_plan"]))
    check("...and a policy hold still DOES",
          [n["key"] for n in r["needs_plan"]] == ["pr9003"]
          and [n["key"] for n in r["age_cooldown"]] == ["pr9001"],
          f"needs={r['needs_plan']} cooling={r['age_cooldown']}")

    # Commissioning: neutralise the gate token and the age hold must fall back
    # into needs_plan — i.e. the pre-fix behaviour, caught.
    _orig = mp.AGE_COOLDOWN_GATE
    try:
        mp.AGE_COOLDOWN_GATE = "__no_such_gate__"
        pre = reconcile([COOLDOWN, POLICY_HOLD])
        check("commissioning: with the fix reverted the age hold is back under "
              "NEEDS A PLAN (identical to the policy hold)",
              sorted(n["gate"] for n in pre["needs_plan"]) == ["age", "policy"]
              and pre["age_cooldown"] == [],
              f"needs={[n['gate'] for n in pre['needs_plan']]}")
    finally:
        mp.AGE_COOLDOWN_GATE = _orig

    # --- gate vocabulary: only `age` is a timer -----------------------------
    for gate in ("draft", "parse", "type", "policy", "breaking", "ci"):
        r = reconcile([held(9100, gate)])
        check(f"gate {gate!r} still needs a plan",
              len(r["needs_plan"]) == 1 and r["age_cooldown"] == [],
              f"needs={r['needs_plan']} cooling={r['age_cooldown']}")

    # normalisation — the gate is matched on its token, not its spelling
    for spelling in ("age", "AGE", " age "):
        r = reconcile([held(9101, spelling)])
        check(f"gate {spelling!r} is recognised as the cooldown gate",
              len(r["age_cooldown"]) == 1, str(r))

    # --- the DANGEROUS direction: never silent ------------------------------
    r = reconcile([AGE_UNKNOWN])
    txt = mp.human(r, CFG)
    check("an age hold is still PRINTED (bucket, not a drop)",
          AGE_UNKNOWN["dep"] in txt, txt[:400])
    check("...with its reason, so 'age UNKNOWN' stays legible",
          "UNKNOWN on both measures" in txt, txt[:400])
    check("...and is NOT announced as 'all held updates have a plan'",
          "all held updates have a plan" not in txt, txt[:400])
    check("the age hold is carried in the JSON payload for downstream readers",
          [c["key"] for c in r["age_cooldown"]] == ["pr9002"], str(r["age_cooldown"]))

    # with nothing held at all the old all-clear is unchanged
    check("no held updates at all still reports the plain all-clear",
          "all held updates have a plan" in mp.human(reconcile([]), CFG))

    # --- an age hold that HAS a plan is untouched by any of this -------------
    pl = {"plan_id": "app9001", "_path": "p.md", "component": "app9001",
          "status": "draft", "current": "1.0.0", "target": "1.0.1"}
    r = reconcile([COOLDOWN], plans=[pl])
    check("an age hold WITH a matching plan enters neither bucket",
          r["needs_plan"] == [] and r["age_cooldown"] == [],
          f"needs={r['needs_plan']} cooling={r['age_cooldown']}")

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
