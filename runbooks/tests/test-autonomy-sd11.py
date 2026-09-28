"""Regression tests for SD-11 "interruption acceptable, loss not" (2026-09-28).

maintenance-plan.py::sd11_eligibility() / effective_class() pre-approve a
reviewed plan for the nightly window WITHOUT a GO when the only cost is
downtime. They must still refuse every case the operator named as a reason
to be asked: possible data loss, capability/feature loss, quorum loss (and
the self-revert path), an author's human-gated restriction, a reboot, a plan
that does not fit the window, a stale/missing review. Pure; no cluster, no DB.

Run:  python3 runbooks/tests/test-autonomy-sd11.py
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("mp", REPO / "runbooks/maintenance-plan.py")
mp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mp)

POLICY = mp.load_autonomy_policy()
CFG = {"windows": [{"id": "nightly", "duration_min": 90},
                   {"id": "sat-attended", "duration_min": 90}]}
TODAY = date(2026, 9, 28)
FAILURES: list[str] = []


def plan(**kw):
    base = {"plan_id": "t", "kind": "helm-chart", "status": "vetted",
            "risk": "medium", "capability_change": False,
            "rollback_class": "git-revert", "needs_reboot": False,
            "est_duration_min": 40, "review": "ready-for-go@2026-09-27",
            "touches": {"shared": []}}
    base.update(kw)
    return base


def expect(name, p, want_pre, want_class=None, policy=POLICY, cfg=CFG):
    klass, why, pre, reasons = mp.effective_class(p, policy, TODAY, cfg)
    ok = pre is want_pre and (want_class is None or klass == want_class)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}: class={klass} pre={pre}"
          + ("" if ok else f"  (wanted pre={want_pre} class={want_class}; {why}; {reasons})"))
    if not ok:
        FAILURES.append(name)


def main() -> int:
    print("test-autonomy-sd11")
    assert POLICY and isinstance(POLICY.get("interruption_tolerant"), dict), \
        "autonomy-policy.yaml must carry interruption_tolerant for these tests"
    assert mp.sd11_budget_min(CFG, POLICY["interruption_tolerant"]) == 70

    # the operator's motivating case: a restart that logs users out
    expect("medium-risk reversible capability-neutral -> SD-11", plan(), True, "AUTO-NIGHT")
    expect("risk high is NOT a condition (capacity weight only)", plan(risk="high"), True, "AUTO-NIGHT")
    expect("gateway is interruption, not loss", plan(touches={"shared": ["gateway/envoy", "monitoring"]}),
           True, "AUTO-NIGHT")
    # SD-10 still wins for low-risk AUTO-NIGHT plans (reason stays SD-10)
    k, why, pre, r = mp.effective_class(plan(risk="low"), POLICY, TODAY, CFG)
    ok = pre and why.startswith("policy class") and r[0].startswith("SD-10")
    print(f"  {'PASS' if ok else 'FAIL'}  low-risk stays SD-10")
    if not ok:
        FAILURES.append("low-risk stays SD-10")

    # escalations the operator named — every one must still need a GO
    expect("capability change (feature loss)", plan(capability_change=True), False)
    expect("capability undeclared", plan(capability_change=None), False)
    expect("one-way rollback (data loss)", plan(rollback_class="one-way"), False)
    expect("backup-restore without a restore proof",
           plan(rollback_class="backup-restore", backup_gate="nightly backup < 26h"), False)
    expect("backup-restore with restore proof but no gate",
           plan(rollback_class="backup-restore", restore_proof="restore into scratch db, counts match"),
           False)
    expect("backup-restore WITH gate + restore proof -> AUTO-BACKUP-GATED",
           plan(rollback_class="backup-restore", backup_gate="pg_dump pre-step",
                restore_proof="restore dump into scratch db; row counts equal"),
           True, "AUTO-BACKUP-GATED")
    for tok in ("storage/longhorn", "etcd-encryption", "control-plane/kube-apiserver",
                "cni-adjacent", "dns/coredns", "flux", "talos-machineconfig"):
        expect(f"floor: {tok}", plan(touches={"shared": [tok]}), False)
    expect("author restriction (credentials/physical)", plan(autonomy_override="human-gated"), False)
    expect("reboot", plan(needs_reboot=True), False)
    expect("over the 70-min nightly budget", plan(est_duration_min=85), False)
    expect("duration undeclared", plan(est_duration_min=None), False)
    expect("no review", plan(review=None), False)
    expect("review not ready", plan(review="needs-fix@2026-09-27"), False)
    expect("stale review (>30d)", plan(review="ready-for-go@2026-08-01"), False)
    expect("future review", plan(review="ready-for-go@2026-10-30"), False)
    expect("draft", plan(status="draft"), False)
    expect("blocked", plan(status="blocked"), False)

    # kill switch + fail-safe
    no_sd11 = {k: v for k, v in POLICY.items() if k != "interruption_tolerant"}
    expect("kill switch: block removed", plan(), False, policy=no_sd11)
    expect("policy unreadable", plan(), False, "HUMAN-GATED", policy=None)

    # windows: nightly only
    ok = "nightly" in mp.preapproved_windows(POLICY) and "sat-attended" not in mp.sd11_windows(POLICY)
    print(f"  {'PASS' if ok else 'FAIL'}  SD-11 windows are nightly only")
    if not ok:
        FAILURES.append("windows")

    print(f"\n{'OK' if not FAILURES else 'FAILED: ' + ', '.join(FAILURES)}")
    return 1 if FAILURES else 0


def test_pytest_entry():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
