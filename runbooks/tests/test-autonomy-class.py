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


def assert_true(name, ok, detail=""):
    """Boolean assert. `check` above compares a (class, reason) tuple, which
    cannot express "this file contains X"."""
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
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

    # risk:medium deliberately does NOT gate. This is doctrine, not an
    # oversight: "a medium-risk change that is reversible, non-interrupting and
    # capability-neutral is exactly what nights are for". Do not tighten it.
    check("risk:medium does not human-gate (by design)",
          mp.execution_class(plan(risk="medium"), POLICY), "AUTO-NIGHT")

    # risk:high DOES gate, added 2026-09-06. Found by audit: superset-pg-18.6
    # derived AUTO-NIGHT while being a 90-minute dump/restore cutover of
    # Superset's entire metadata DB plus a SOPS secret repoint. Every
    # MECHANICAL fact was individually defensible -- the old 17.11 Deployment
    # is kept running, so rollback genuinely is a revert -- which is the point:
    # capability_change/rollback_class/needs_reboot/shared cannot express
    # "moves live data between two systems", and risk:high is where the
    # operator says so. Only `status: draft` was keeping it out of a window,
    # and status is clerical state, not a control.
    check("risk:high human-gates a plan that matches on mechanics",
          mp.execution_class(plan(risk="high"), POLICY), "HUMAN-GATED")

    # the veto must survive the trailing comments these files actually carry
    check("risk:high still gates when the value has a trailing comment",
          mp.execution_class(plan(risk="high   # metadata DB"), POLICY),
          "HUMAN-GATED")

    # ...and it must VETO only, never grant. A risk level cannot rescue a plan
    # that fails on mechanics, or the gate becomes an escalation path.
    check("risk:low cannot rescue a capability-changing plan",
          mp.execution_class(plan(risk="low", capability_change=True), POLICY),
          "HUMAN-GATED")
    check("risk:low cannot rescue a reboot-bearing plan",
          mp.execution_class(plan(risk="low", needs_reboot=True), POLICY),
          "HUMAN-GATED")

    # ---- the LIVE policy file, not the fixture -----------------------------
    # This block exists because the fixture above passed while the shipped
    # policy was wrong. `forbid_risk: [high]` was added to auto-night on
    # 2026-09-06 and the commit message claimed BOTH auto classes carried it;
    # the edit to auto-backup-gated silently did not match, and nothing noticed
    # until a risk:high Postgres major derived AUTO-BACKUP-GATED on 2026-09-07.
    # A fixture tests the mechanism; only the real file tests the deployment.
    import yaml
    live = yaml.safe_load((REPO / "runbooks/autonomy-policy.yaml").read_text())
    auto = {n: spec for n, spec in (live.get("classes") or {}).items()
            if n.startswith("auto")}
    assert_true("the live policy actually defines auto classes", bool(auto), str(list(auto)))
    for name, spec in sorted(auto.items()):
        assert_true(f"live class {name!r} forbids risk:high",
                    "high" in [str(x).lower() for x in (spec.get("forbid_risk") or [])],
                    f"forbid_risk={spec.get('forbid_risk')!r} — a high-risk plan "
                    f"can derive {name.upper()}")

    # And prove it end-to-end through the real derivation, per auto class.
    for name, spec in sorted(auto.items()):
        facts = dict(spec.get("require") or {})
        pl = plan(risk="high", **facts)
        if spec.get("require_backup_gate"):
            pl["backup_gate"] = "some gate"
        check(f"a risk:high plan matching {name!r} on mechanics is HUMAN-GATED",
              mp.execution_class(pl, live), "HUMAN-GATED")

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} -> {', '.join(FAILURES)}")
        return 1
    print("all tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
