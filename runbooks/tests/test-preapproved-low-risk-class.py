"""Regression tests for SD-10 pre-approval (throughput program item D,
operator-approved 2026-09-27): low-risk, reviewed, reversible plans run in the
NIGHTLY window without an operator GO.

maintenance-plan.py::preapproval() derives it from facts; nothing is claimed.
ALL of these must hold, and each is tested ALONE so one over-broad guard
cannot stand in for the rest:
  class AUTO-NIGHT (reversible git-revert, no reboot, no capability change,
  no shared-infra floor, not autonomy_override: human-gated), risk: low,
  `review: ready-for-go@<date>` recorded and fresh, status runnable.
Medium/high risk, reboots and capability changes still need a GO.

Also pinned: the eligibility verdict and the scheduler honour it (nightly
only), a malformed `review:` is a validation error, and the LIVE
autonomy-policy.yaml carries the block (the kill switch is deleting it).

Run:  python3 runbooks/tests/test-preapproved-low-risk-class.py
"""
from __future__ import annotations

import datetime as dt
import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _load(name, rel):
    s = importlib.util.spec_from_file_location(name, REPO / rel)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


mp = _load("mp", "runbooks/maintenance-plan.py")
ar = _load("ar", "runbooks/autonomy-record.py")
ws = _load("ws", "runbooks/window-scheduler.py")

POLICY = mp.load_autonomy_policy()
TODAY = dt.date(2026, 9, 27)
FAILURES: list[str] = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


def plan(**kw):
    base = {"plan_id": "exampleapp-1.2.4", "kind": "image", "status": "vetted",
            "window": None, "risk": "low", "est_duration_min": 20,
            "capability_change": False, "rollback_class": "git-revert",
            "needs_reboot": False, "touches": {"namespaces": ["testns"], "shared": []},
            "review": "ready-for-go@2026-09-26", "depends_on": [], "conflicts_with": []}
    base.update(kw)
    return base


def derive(p, policy=POLICY):
    klass = mp.execution_class(p, policy)[0]
    return klass, mp.preapproval(p, policy, klass, TODAY)


def main() -> int:
    print(__doc__.strip().splitlines()[0])
    check("LIVE autonomy-policy.yaml carries preapproved_low_risk (nightly only)",
          (POLICY or {}).get("preapproved_low_risk", {}).get("windows") == ["nightly"])

    print("\nderivation:")
    klass, (pre, why) = derive(plan())
    check("all conditions => AUTO-NIGHT + pre-approved", klass == "AUTO-NIGHT" and pre, repr((klass, why)))
    check("...and the basis names SD-10 and the review", pre and "SD-10" in why[0] and "ready-for-go" in why[0])

    cases = [
        ("risk: medium still needs a GO", plan(risk="medium")),
        ("risk: high still needs a GO", plan(risk="high")),
        ("risk undeclared is not low", plan(risk=None)),
        ("a REBOOT still needs a GO", plan(needs_reboot=True)),
        ("needs_reboot undeclared is not 'no reboot'", plan(needs_reboot=None)),
        ("a CAPABILITY CHANGE still needs a GO", plan(capability_change=True)),
        ("backup-restore rollback is not the reversible class", plan(rollback_class="backup-restore", backup_gate="x")),
        ("one-way rollback is never pre-approved", plan(rollback_class="one-way")),
        ("autonomy_override: human-gated restricts", plan(autonomy_override="human-gated")),
        ("shared infra (gateway/envoy) is never pre-approved", plan(touches={"shared": ["gateway/envoy"]})),
        ("no recorded review", plan(review=None)),
        ("review verdict needs-fix", plan(review="needs-fix@2026-09-26")),
        ("review older than 30d re-reviews", plan(review="ready-for-go@2026-08-01")),
        ("review dated in the future", plan(review="ready-for-go@2026-10-30")),
        ("malformed review", plan(review="ready-for-go 2026-09-26")),
        ("status draft", plan(status="draft")),
        ("status blocked", plan(status="blocked")),
        ("status executed", plan(status="executed")),
    ]
    for name, p in cases:
        k, (pre, why) = derive(p)
        check(f"NOT pre-approved: {name}", not pre, repr((k, why)))
    for st in ("scheduled", "awaiting-go"):
        k, (pre, _) = derive(plan(status=st))
        check(f"status {st} is runnable", pre)
    k, (pre, why) = derive(plan(), {k: v for k, v in POLICY.items() if k != "preapproved_low_risk"})
    check("KILL SWITCH: no preapproved_low_risk block => nothing pre-approved", not pre, repr(why))
    k, (pre, why) = derive(plan(risk="medium", review=None, status="draft"))
    check("every unmet condition is reported, not just the first", len(why) >= 3, repr(why))

    print("\nvalidation:")
    errs = mp.validate_plans({"windows": []}, [plan(review="ready-for-go 2026-09-26")])
    check("a malformed review: is a validation error", any("review" in e for e in errs), repr(errs))
    errs = mp.validate_plans({"windows": []}, [plan()])
    check("a well-formed review: validates", not any("review" in e for e in errs), repr(errs))

    print("\neligibility (autonomy-record.py):")
    ok, why = ar.eligibility_verdict("vetted", "AUTO-NIGHT", 2, 0, False, preapproved=True)
    check("pre-approved AUTO-NIGHT is eligible with NO track record", ok, why)
    ok, _ = ar.eligibility_verdict("vetted", "AUTO-NIGHT", 2, 0, False, preapproved=False)
    check("control: without pre-approval an unreadable track record still denies", not ok)
    ok, _ = ar.eligibility_verdict("blocked", "AUTO-NIGHT", 2, 0, True, preapproved=True)
    check("a dead status beats pre-approval", not ok)
    ok, _ = ar.eligibility_verdict("vetted", "HUMAN-GATED", 2, 0, True, preapproved=True)
    check("pre-approval can never lift HUMAN-GATED", not ok)
    ok, _ = ar.eligibility_verdict("vetted", "AUTO-BACKUP-GATED", 2, 0, False, preapproved=True)
    check("pre-approval does not cover AUTO-BACKUP-GATED", not ok)

    print("\nscheduler (window-scheduler.py):")
    cfg = {"windows": [
        {"id": "nightly", "day": "daily", "duration_min": 90, "capacity_risk": 6,
         "allow_reboot": False, "mode": "unattended"},
        {"id": "sat-attended", "day": "saturday", "duration_min": 90, "capacity_risk": 6,
         "allow_reboot": False, "mode": "attended"},
    ]}
    p = plan()
    a, s = ws.assign([dict(p)], cfg, {p["plan_id"]: "AUTO-NIGHT"}, {}, dt.date(2026, 9, 28),
                     premises_check=lambda pid: (True, "fixture"),
                     preapproved={p["plan_id"]}, preapproved_windows=["nightly"])
    check("a pre-approved plan routes to the NIGHTLY window with no graduated category",
          len(a) == 1 and a[0]["slot"].startswith("nightly:"), repr((a, s)))
    check("...and the assignment says SD-10", a and "SD-10" in a[0]["reason"], repr(a))
    a, _ = ws.assign([dict(p)], cfg, {p["plan_id"]: "AUTO-NIGHT"}, {}, dt.date(2026, 9, 28),
                     premises_check=lambda pid: (True, "fixture"))
    check("control: the same plan NOT pre-approved routes to an ATTENDED window",
          len(a) == 1 and a[0]["slot"].startswith("sat-attended:"), repr(a))
    a, s = ws.assign([dict(p)], cfg, {p["plan_id"]: "AUTO-NIGHT"}, {}, dt.date(2026, 9, 28),
                     premises_check=lambda pid: (False, "premise P1 FAIL"),
                     preapproved={p["plan_id"]})
    check("premises still gate a pre-approved plan", not a, repr(s))

    print()
    print("FAILED: " + ", ".join(FAILURES) if FAILURES else "all tests passed")
    return 1 if FAILURES else 0


def test_pytest_entry():
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())
