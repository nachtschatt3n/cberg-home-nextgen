"""Regression test: a go/no-go already answered is not re-asked
(F-0c639ada, 2026-09-22).

`reconcile()` built its AWAITING YOUR GO/NO-GO list from ONE fact:

    [ ... for p in plans if p.get("status") == "awaiting-go"]

but the GO state is `status: awaiting-go` PLUS a recorded home-operation
decision — never a status value (maintenance-plan.py says so where `approved`
was removed from VALID_STATUSES). An approved plan KEEPS `awaiting-go` until
the window agent executes it, so the sweep re-asked, every cycle, for a
decision the operator had already given — and OpenClaw's reminder cadence is
driven off exactly that list.

WHY nextcloud-34.0.4 IS ALSO APPROVED AND CORRECTLY ABSENT. It carries a
recorded operator GO (test-coverage-plan-also-covers.py calls it "vetted,
operator GO recorded") and never appeared under AWAITING — because its status
is `vetted`, so the status filter drops it for reasons that have nothing to do
with the decision. That is the trap: it looks like evidence that status already
encodes approval, and the tempting "fix" is to move the offending plan's status
or to infer approval from the lifecycle. Both are wrong. Status and approval
are ORTHOGONAL — nextcloud-34.0.4 is approved at `vetted`, and an approved plan
sits at `awaiting-go` — so approval has to be ASKED FOR, keyed on plan_id,
against the ledger that holds it. The two blocks below pin both halves.

FAIL-CLOSED: unreadable decisions (`None`) suppress NOTHING. A ledger that
cannot be read is not consent, and the cost of asking twice is a duplicate
reminder, while the cost of a wrong suppression is a go/no-go that silently
stops being asked. Same rule this module already applies to window liveness
and cron parity.

Run:  python3 runbooks/tests/test-awaiting-go-recorded-decision.py
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


def plan(pid, status, **kw):
    base = {"plan_id": pid, "_path": f"runbooks/maintenance/plans/{pid}.md",
            "component": pid, "status": status, "target": "9.9.9",
            "window": "sat-attended:2026-10-03"}
    base.update(kw)
    return base


# The live shape: one approved-and-waiting plan, one genuinely unanswered, and
# the nextcloud-34.0.4 case (approved, but at `vetted`).
APPROVED = plan("approved-and-waiting", "awaiting-go")
UNANSWERED = plan("still-unanswered", "awaiting-go")
VETTED_APPROVED = plan("vetted-but-approved", "vetted")
PLANS = [APPROVED, UNANSWERED, VETTED_APPROVED]

GO = {"key": "approved-and-waiting", "decision": "approve", "exec_state": "pending",
      "decided_by": "operator", "window": "sat-attended:2026-10-03"}
GO_VETTED = {"key": "vetted-but-approved", "decision": "approve",
             "exec_state": "pending"}


def reconcile(decisions, plans=PLANS):
    """reconcile() with every external reader stubbed: no gh, no cluster, no DB."""
    mp.load_plans = lambda cfg: [dict(p) for p in plans]
    mp.get_held = lambda: ([], None)
    mp.cron_parity = lambda cfg: ([], False)
    mp.window_liveness_report = lambda cfg, today, now=None: {
        "missing": [], "stuck": [], "verified": False}
    return mp.reconcile(CFG, TODAY, decisions=decisions)


def ids(r):
    return [a["plan_id"] for a in r["awaiting_go"]]


def main() -> int:
    print(__doc__.strip().splitlines()[0])
    print()

    # --- THE DEFECT ---------------------------------------------------------
    r = reconcile([GO, GO_VETTED])
    check("an approved plan is not re-asked", ids(r) == ["still-unanswered"], str(ids(r)))
    check("...and the suppression is legible, not silent",
          r["approved_pending_exec"] == ["approved-and-waiting"],
          str(r["approved_pending_exec"]))
    check("...and it is still an OPEN issue, so OpenClaw's reconcile cannot "
          "auto-close the standing approval before the window runs",
          "approved-and-waiting" in r["open_issue_keys"], str(r["open_issue_keys"]))

    # Commissioning: revert the cross-check and the approved plan comes back.
    _orig = mp.answered_plan_ids
    try:
        mp.answered_plan_ids = lambda decisions: set()
        pre = reconcile([GO, GO_VETTED])
        check("commissioning: with the fix reverted the approved plan is asked "
              "again (so this case is non-trivial)",
              ids(pre) == ["approved-and-waiting", "still-unanswered"], str(ids(pre)))
    finally:
        mp.answered_plan_ids = _orig

    # --- the nextcloud-34.0.4 case: approved, but suppressed by STATUS -------
    check("an approved plan at status `vetted` stays out of AWAITING "
          "(the status filter, not the decision, is what drops it)",
          "vetted-but-approved" not in ids(r))
    check("...and is NOT claimed as a suppressed go/no-go either — it was never "
          "awaiting one",
          "vetted-but-approved" not in r["approved_pending_exec"],
          str(r["approved_pending_exec"]))
    # The converse, which is the whole point: status cannot stand in for
    # approval, because an approved plan sits at `awaiting-go`.
    r_novetted = reconcile([GO], plans=[APPROVED, UNANSWERED])
    check("approval is keyed on the DECISION, not inferred from the lifecycle",
          ids(r_novetted) == ["still-unanswered"], str(ids(r_novetted)))

    # --- FAIL-CLOSED: anything short of a recorded GO keeps asking ----------
    r = reconcile(None)
    check("unreadable decisions suppress NOTHING",
          sorted(ids(r)) == ["approved-and-waiting", "still-unanswered"], str(ids(r)))
    check("...and say so", r["decisions_readable"] is False)
    check("...visibly, in the human report",
          "decision ledger UNREADABLE" in mp.human(r, CFG))
    check("an empty ledger suppresses nothing but IS readable",
          sorted(ids(reconcile([]))) == ["approved-and-waiting", "still-unanswered"]
          and reconcile([])["decisions_readable"] is True)

    deny = {"key": "approved-and-waiting", "decision": "deny", "exec_state": "pending"}
    check("a DENY does not suppress the reminder — the plan's file still has to "
          "move to blocked/superseded and the reminder is what carries that",
          sorted(ids(reconcile([deny]))) == ["approved-and-waiting", "still-unanswered"],
          str(ids(reconcile([deny]))))
    for bad in ({"key": "approved-and-waiting", "decision": "approve",
                 "exec_state": "done"},
                {"key": "approved-and-waiting", "decision": "defer",
                 "exec_state": "pending"},
                {"key": "approved-and-waiting", "exec_state": "pending"},
                {"decision": "approve", "exec_state": "pending"}):
        check(f"a non-approval row does not suppress ({bad})",
              "approved-and-waiting" in ids(reconcile([bad])))

    # --- the DEFAULT path asks the ledger, and only when it matters ---------
    calls: list[int] = []
    _fetch = mp.fetch_recorded_decisions
    try:
        def _spy(*a, **k):
            calls.append(1)
            return [GO]
        mp.fetch_recorded_decisions = _spy
        r = reconcile(mp._FETCH_DECISIONS, plans=[APPROVED, UNANSWERED])
        check("the default path consults the ledger when a plan is awaiting-go",
              calls == [1] and ids(r) == ["still-unanswered"],
              f"calls={calls} ids={ids(r)}")
        calls.clear()
        r = reconcile(mp._FETCH_DECISIONS, plans=[VETTED_APPROVED])
        check("...and does NOT exec when nothing is awaiting a go/no-go",
              calls == [] and r["awaiting_go"] == [] and r["decisions_readable"] is True,
              f"calls={calls} r={r['awaiting_go']}")
    finally:
        mp.fetch_recorded_decisions = _fetch

    # --- the ledger reader ---------------------------------------------------
    check("rc != 0 reads as UNKNOWN, never as 'nobody decided'",
          mp.parse_decisions(1, '{"decisions": []}') is None)
    check("unparseable stdout reads as UNKNOWN", mp.parse_decisions(0, "boom") is None)
    check("a non-list payload reads as UNKNOWN",
          mp.parse_decisions(0, '{"decisions": "nope"}') is None)
    check("a well-formed payload is returned",
          mp.parse_decisions(0, '{"decisions": [{"key": "a"}]}') == [{"key": "a"}])
    check("non-dict rows are dropped",
          mp.parse_decisions(0, '{"decisions": [{"key": "a"}, 7]}') == [{"key": "a"}])

    class _R:
        returncode, stdout = 0, '{"decisions": [%s]}' % (
            '{"key": "k", "decision": "approve", "exec_state": "pending"}')

    check("fetch_recorded_decisions parses its runner's output",
          mp.answered_plan_ids(mp.fetch_recorded_decisions(
              runner=lambda *a, **k: _R())) == {"k"})

    def _boom(*a, **k):
        raise OSError("no kubeconfig")

    check("a failing exec yields UNKNOWN, not an empty ledger",
          mp.fetch_recorded_decisions(runner=_boom) is None)
    check("the command is the one run-now.py uses (ONE definition of approved)",
          mp.HOME_OP_DECISIONS_CMD[-3:] == ["--json", "decisions", "--pending-exec"],
          str(mp.HOME_OP_DECISIONS_CMD))

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
