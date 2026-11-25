"""WEEKEND-ATTENDED auto-slotting + needs_replan refusal (2026-11-25).

A vetted cluster-core plan (reboot / storage / cni / dns / flux / etcd / talos /
gateway) is placed into an ATTENDED window automatically; it is never placed in
the nightly, never when flagged needs_replan, never when a premise fails.

Run:  python3 runbooks/tests/test-window-scheduler-weekend.py
"""

from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def load(n, f):
    s = importlib.util.spec_from_file_location(n, REPO / "runbooks" / f)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


ws, mp = load("ws", "window-scheduler.py"), load("mp", "maintenance-plan.py")
cfg = mp.load_windows()
TODAY = date(2026, 11, 25)
FAILS = []


def check(name, cond, extra=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        FAILS.append(name)


def plan(pid, **kw):
    b = {"plan_id": pid, "kind": "chart", "status": "vetted", "risk": "medium",
         "est_duration_min": 30, "needs_reboot": False, "capability_change": False,
         "rollback_class": "git-revert", "touches": {"shared": ["cni/cilium"]},
         "window": None}
    b.update(kw)
    return b


def run(plans, weekend_ids, ok=True):
    return ws.assign(plans, cfg, {p["plan_id"]: "HUMAN-GATED" for p in plans}, {}, TODAY,
                     premises_check=lambda pid: (ok, "stub"), preapproved=set(),
                     weekend=set(weekend_ids))


cil = plan("cilium-x")
check("weekend_class: cni/cilium is weekend", mp.weekend_class(cil)[0])
check("weekend_class: reboot is weekend", mp.weekend_class(plan("t", needs_reboot=True, touches={}))[0])
check("weekend_class: plain app is not", not mp.weekend_class(plan("a", touches={"shared": []}))[0])
a, sk = run([cil], {"cilium-x"})
slot = a[0]["slot"] if a else ""
sid = slot.split(":")[0]
mode = next((w["mode"] for w in cfg["windows"] if w["id"] == sid), None)
check("vetted cluster-core plan is auto-slotted into an ATTENDED window", bool(a) and mode == "attended", str(a or sk))
check("...and the reason says the GO is still required", bool(a) and "GO still required" in a[0]["reason"])
a, sk = run([cil], set())
check("without the weekend flag a HUMAN-GATED plan is NOT slotted (unchanged)", not a)
a, sk = run([plan("cilium-x", needs_replan="premise-fail: x")], {"cilium-x"})
check("needs_replan plan is refused", not a and "needs_replan" in sk[0]["reason"])
a, sk = run([cil], {"cilium-x"}, ok=False)
check("failing premises refuse the slot (fail closed)", not a)
a, sk = run([plan("cilium-x", status="draft")], {"cilium-x"})
check("draft is never slotted", not a)
a, sk = run([plan("rb", needs_reboot=True, touches={})], {"rb"})
rm = next((w for w in cfg["windows"] if w["id"] == a[0]["slot"].split(":")[0]), {}) if a else {}
check("reboot plan lands only in a reboot-capable window", bool(a) and rm.get("allow_reboot"), str(a or sk))
print()
if FAILS:
    print(f"{len(FAILS)} FAILED: {FAILS}")
    raise SystemExit(1)
print("OK")
