"""Regression tests for execution_class() in maintenance-plan.py (P2.1a).

The rubric replaces the blunt `auto_execute` + `risk: low` pair, which
human-gated work the operator explicitly wanted autonomous (a nightly
service-restart mitigation) while expressing nothing about WHY something
needs a human. Classes are DERIVED from declared facts against
runbooks/autonomy-policy.yaml; plans cannot claim one.

Ground truth is the operator's own examples: the frigate restart mitigation
should have been AUTO-NIGHT; a postgres major with a restore-proof gate is
AUTO-BACKUP-GATED; the longhorn engine drain (one-way, storage-wide) and the
envoy migration (capability-changing) genuinely earn a human.

Run:  python3 runbooks/tests/test-autonomy-class.py
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("mp", REPO / "runbooks/maintenance-plan.py")
mp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mp)

POLICY = mp.load_autonomy_policy()
FAILURES: list[str] = []


def check(name, got, want):
    ok = got[0] == want
    print(f"  {'PASS' if ok else 'FAIL'}  {name}: {got[0]}"
          + ("" if ok else f"  (wanted {want}; reason: {got[1]})"))
    if not ok:
        FAILURES.append(name)


def plan(**kw):
    base = {"plan_id": "t", "capability_change": False,
            "rollback_class": "git-revert", "needs_reboot": False,
            "touches": {"shared": []}}
    base.update(kw)
    return base


def main() -> int:
    print("test-autonomy-class")
    assert POLICY, "autonomy-policy.yaml must load for these tests"

    # the operator's motivating case: nightly restart mitigation
    check("frigate-restart shape -> AUTO-NIGHT",
          mp.execution_class(plan(), POLICY), "AUTO-NIGHT")

    # pg major with a named restore-proof gate
    check("pg-major with backup_gate -> AUTO-BACKUP-GATED",
          mp.execution_class(plan(rollback_class="backup-restore",
                                  backup_gate="scratch-restore-postgres"), POLICY),
          "AUTO-BACKUP-GATED")

    # pg major WITHOUT a gate: matches the class shape but is not pre-approved
    check("backup-restore without gate -> HUMAN-GATED",
          mp.execution_class(plan(rollback_class="backup-restore"), POLICY),
          "HUMAN-GATED")

    # longhorn drain: one-way + storage-wide — two independent reasons
    check("one-way rollback -> HUMAN-GATED",
          mp.execution_class(plan(rollback_class="one-way"), POLICY), "HUMAN-GATED")
    check("shared storage forbidden even if otherwise clean",
          mp.execution_class(plan(touches={"shared": ["storage"]}), POLICY),
          "HUMAN-GATED")

    # envoy migration: capability change is decisive on its own
    check("capability_change true -> HUMAN-GATED",
          mp.execution_class(plan(capability_change=True,
                                  rollback_class=None), POLICY), "HUMAN-GATED")

    # reboots never run unattended
    check("needs_reboot -> HUMAN-GATED",
          mp.execution_class(plan(needs_reboot=True), POLICY), "HUMAN-GATED")

    # fail-safes: missing facts, missing policy
    check("facts not declared -> HUMAN-GATED",
          mp.execution_class({"plan_id": "bare"}, POLICY), "HUMAN-GATED")
    check("no policy -> HUMAN-GATED (fail-safe)",
          mp.execution_class(plan(), None), "HUMAN-GATED")

    # override may only restrict
    check("autonomy_override restricts an otherwise-AUTO plan",
          mp.execution_class(plan(autonomy_override="human-gated"), POLICY),
          "HUMAN-GATED")

    # risk deliberately does NOT gate: medium-risk reversible work stays AUTO
    check("risk:medium does not human-gate (by design)",
          mp.execution_class(plan(risk="medium"), POLICY), "AUTO-NIGHT")

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} -> {', '.join(FAILURES)}")
        return 1
    print("all tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
