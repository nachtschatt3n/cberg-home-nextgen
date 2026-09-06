"""Regression tests for window-scheduler.py — the thing that stops nights idling.

GROUND TRUTH, measured 2026-09-06: eight plans derived AUTO-*, all eight sat at
`window: null`, and the nightly window had executed 0 plans across its first 7
runs. `maintenance-plan.py` derives the execution class and then does nothing
with it; assignment was a manual edit nobody performed.

The scheduler exists to close that gap. These tests pin the two halves that
matter and are easy to get wrong in opposite directions:

  1. it must actually ASSIGN — including routing a graduated category to an
     UNATTENDED window, which is the step the whole autonomy ramp was missing;
  2. it must REFUSE the things that made today's near-misses possible, and each
     refusal is checked separately so a single over-broad guard cannot stand in
     for all of them.

Every fixture below is modelled on a real plan in the queue on 2026-09-06.

Run:  python3 runbooks/tests/test-window-scheduler.py
"""

from __future__ import annotations

import datetime as dt
import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("ws", REPO / "runbooks/window-scheduler.py")
ws = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ws)

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


# Mirrors runbooks/maintenance-windows.yaml as of 2026-09-06.
CFG = {"windows": [
    {"id": "nightly", "day": "daily", "duration_min": 90,
     "capacity_risk": 6, "allow_reboot": False, "mode": "unattended"},
    {"id": "sat-attended", "day": "saturday", "duration_min": 90,
     "capacity_risk": 6, "allow_reboot": False, "mode": "attended"},
    {"id": "sun-attended", "day": "sunday", "duration_min": 150,
     "capacity_risk": 6, "allow_reboot": True, "mode": "attended"},
]}
MONDAY = dt.date(2026, 9, 7)


def plan(pid, **kw):
    base = {"plan_id": pid, "kind": "image", "status": "vetted", "window": None,
            "risk": "medium", "est_duration_min": 25, "depends_on": [],
            "conflicts_with": [], "needs_reboot": False}
    base.update(kw)
    return base


def run(plans, classes=None, graduated=None):
    classes = classes or {p["plan_id"]: "AUTO-NIGHT" for p in plans}
    return ws.assign(plans, CFG, classes, graduated or {}, MONDAY)


def reason_for(skipped, pid):
    return next((s["reason"] for s in skipped if s["plan_id"] == pid), "")


def main() -> int:
    print("window scheduler:")

    # ---- it assigns, and routes by track record -----------------------------
    a, _ = run([plan("ungraduated")])
    check("ungraduated category routes to an ATTENDED window",
          len(a) == 1 and "attended" in a[0]["slot"],
          str(a))

    a, _ = run([plan("graduated")], graduated={"image/AUTO-NIGHT": True})
    check("graduated category routes to the UNATTENDED window — the loop closes",
          len(a) == 1 and a[0]["slot"].startswith("nightly:"),
          str(a))

    # The whole reason the ramp deadlocked: no entry point. An ungraduated plan
    # must still get scheduled *somewhere*, or it can never earn its runs.
    a, s = run([plan("entrypoint")])
    check("an ungraduated plan is scheduled rather than parked forever",
          len(a) == 1 and not s, f"{a} / {s}")

    # ---- refusals, each isolated -------------------------------------------
    a, s = run([plan("drafty", status="draft")])
    check("draft is refused (paperclip-base-images says DO NOT EXECUTE and is AUTO-NIGHT)",
          not a and "draft" in reason_for(s, "drafty"), reason_for(s, "drafty"))

    for dead in ("blocked", "executed", "superseded"):
        a, s = run([plan(f"d-{dead}", status=dead)])
        check(f"status {dead!r} is refused",
              not a and dead in reason_for(s, f"d-{dead}"), reason_for(s, f"d-{dead}"))

    a, s = run([plan("gated")], classes={"gated": "AUTO-BACKUP-GATED"})
    check("AUTO-BACKUP-GATED is refused until premise validation exists",
          not a and "AUTO-BACKUP-GATED" in reason_for(s, "gated"), reason_for(s, "gated"))

    a, s = run([plan("human")], classes={"human": "HUMAN-GATED"})
    check("HUMAN-GATED is refused", not a and "HUMAN-GATED" in reason_for(s, "human"))

    a, s = run([plan("dependent", depends_on=["never-ran"])])
    check("unmet depends_on is refused (superset-pg-18.6 shape)",
          not a and "never-ran" in reason_for(s, "dependent"), reason_for(s, "dependent"))

    # A dependency that HAS executed must not block.
    a, s = run([plan("ok-dep", depends_on=["done"]),
                plan("done", status="executed", window="already")])
    check("a satisfied depends_on does not block",
          any(x["plan_id"] == "ok-dep" for x in a), f"{a} / {s}")

    # ---- conflicts and capacity --------------------------------------------
    a, _ = run([plan("c1", conflicts_with=["c2"]), plan("c2", conflicts_with=["c1"])])
    slots = {x["plan_id"]: x["slot"] for x in a}
    check("declared conflicts never share a slot",
          len(a) == 2 and slots["c1"] != slots["c2"], str(slots))

    # No window can hold it: the largest slot is sun-attended at 150 minutes,
    # and the Step 0 reserve takes 20 of those. (A 90-minute plan is NOT the
    # right fixture here — it fits sun-attended fine, which is why the first
    # version of this test failed against correct code.)
    a, s = run([plan("toolong", est_duration_min=140)])
    check("a plan that cannot fit the window minus the Step 0 reserve is refused",
          not a and "room" in reason_for(s, "toolong"), reason_for(s, "toolong"))

    # Two 40-minute plans exceed 90 - 20; the second must move to another date.
    a, _ = run([plan("h1", est_duration_min=40), plan("h2", est_duration_min=40)])
    check("time capacity is per-slot, so the second plan moves to another date",
          len(a) == 2 and a[0]["slot"] != a[1]["slot"], str([x["slot"] for x in a]))

    # risk-load: four high-risk plans (weight 4) exceed capacity_risk 6 together
    a, _ = run([plan("r1", risk="high", est_duration_min=10),
                plan("r2", risk="high", est_duration_min=10)])
    check("risk-load is enforced separately from time",
          len(a) == 2 and a[0]["slot"] != a[1]["slot"], str([x["slot"] for x in a]))

    # ---- reboot ------------------------------------------------------------
    a, _ = run([plan("rebooter", needs_reboot=True)])
    check("a reboot-bearing plan only lands in an allow_reboot slot",
          len(a) == 1 and a[0]["slot"].startswith("sun-attended:"), str(a))

    # ---- commissioning ------------------------------------------------------
    # A scheduler that assigns nothing would pass every refusal test above.
    a_all, _ = run([plan("x1"), plan("x2", est_duration_min=10)])
    check("rule is not inert (it does assign when nothing forbids it)",
          len(a_all) == 2, str(a_all))

    # ...and one that assigns everything would pass the assignment tests.
    a_none, s_none = run([plan("y1", status="draft"), plan("y2", status="blocked")])
    check("rule discriminates (refuses when something does forbid it)",
          not a_none and len(s_none) == 2, f"{a_none} / {s_none}")

    print()
    if FAILURES:
        print(f"FAILED ({len(FAILURES)}): {', '.join(FAILURES)}")
        return 1
    print("all window-scheduler tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
