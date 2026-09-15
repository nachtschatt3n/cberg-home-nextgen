"""Regression tests for runbooks/run-now.py — the on-demand NOW-run preflight.

The operator's request (2026-09-15): "run the plan with an active NOW trigger".
The say-so path existed and was dead; this preflight is what lets an attended
on-demand run replace the scheduled-window occupancy checks. Because it
REPLACES gates, every refusal it owns is pinned here separately, and each in
the fail-closed direction:

  * statuses nobody vetted (draft) or that must never run (blocked, executed,
    superseded, reference, awaiting-soak) are refused with their reason;
  * a reboot-bearing plan is refused (on_demand.allow_reboot is false);
  * a failed approvals exec is NO approval — unless the operator's console
    consent is passed explicitly, which is then recorded as the source;
  * an approval scoped to another window does not authorize a NOW run;
  * failing / raising premises refuse, and premises are not even run for a
    plan already refused on cheap grounds;
  * ordering is deterministic, and a declared conflict pair is flagged for a
    settle + health re-verify between the two steps;
  * `stamp` touches only the frontmatter window line, and one refusal writes
    nothing.

Run:  python3 runbooks/tests/test-run-now.py
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import shutil
import sys
import tempfile
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("run_now", REPO / "runbooks/run-now.py")
rn = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rn)

FAILURES: list[str] = []
TODAY = dt.date(2026, 9, 15)
OD = {"id": "now", "mode": "attended", "allow_reboot": False, "serial": True,
      "duration_min": 480}


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


def plan(pid, **kw):
    base = {"plan_id": pid, "kind": "image", "status": "vetted", "window": None,
            "risk": "medium", "est_duration_min": 30, "needs_reboot": False,
            "depends_on": [], "conflicts_with": [], "touches": {"shared": []},
            "_path": f"runbooks/maintenance/plans/{pid}.md"}
    base.update(kw)
    return base


def approve(pid, window="now:2026-09-15", decision="approve"):
    return {"key": pid, "decision": decision, "exec_state": "pending", "window": window,
            "decided_by": "operator (say-so run-now)", "decided_at": "2026-09-15T10:00:00Z"}


PASS_PREMISES = lambda pid: (True, "fixture")  # noqa: E731


def pf(ids, plans, decisions=(), operator_go=None, premises=PASS_PREMISES,
       load_errors=()):
    decs = None if decisions is None else list(decisions)
    return rn.preflight(ids, plans, list(load_errors), OD, decs, operator_go,
                        TODAY, premises)


def row(report, pid):
    return next((r for r in report["plans"] if r["plan_id"] == pid), {})


def reasons(report, pid):
    return " | ".join(row(report, pid).get("reasons", []))


def main() -> int:
    print("test-run-now")

    # ---- control ---------------------------------------------------------
    ok = pf(["good"], [plan("good")], [approve("good")])
    check("control: a vetted, approved, premise-passing plan is runnable",
          ok["ok"] and rn.exit_code(ok) == 0 and ok["sequence"][0]["plan_id"] == "good",
          str(ok))
    check("control: consent source names the home-operation approval",
          "home-operation approval" in (row(ok, "good").get("consent_source") or ""))
    check("control: window_ref and slot are the on-demand ones",
          ok["window_ref"] == "now:2026-09-15" and ok["slot"] == "now"
          and ok["trigger"] == "ad-hoc")
    for st in ("scheduled", "awaiting-go"):
        r = pf(["p"], [plan("p", status=st)], [approve("p")])
        check(f"status {st!r} is runnable", r["ok"], reasons(r, "p"))

    # ---- status refusals ---------------------------------------------------
    for st in ("draft", "blocked", "executed", "superseded", "reference", "awaiting-soak"):
        r = pf(["p"], [plan("p", status=st)], [approve("p")])
        check(f"status {st!r} is REFUSED with its reason",
              not r["ok"] and st in reasons(r, "p") and rn.exit_code(r) == 2,
              reasons(r, "p"))

    r = pf(["boot"], [plan("boot", needs_reboot=True)], [approve("boot")])
    check("needs_reboot is REFUSED", not r["ok"] and "needs_reboot" in reasons(r, "boot"),
          reasons(r, "boot"))
    r = pf(["long"], [plan("long", est_duration_min=481)], [approve("long")])
    check("est_duration_min above the on-demand ceiling is REFUSED",
          not r["ok"] and "ceiling" in reasons(r, "long"), reasons(r, "long"))
    r = pf(["ghost"], [plan("good")], [approve("ghost")])
    check("a plan id with no file is REFUSED", "no plan file" in reasons(r, "ghost"))
    r = pf(["broken"], [], [approve("broken")],
           load_errors=["runbooks/maintenance/plans/broken.md: frontmatter unparseable — x"])
    check("an UNREADABLE plan reads as unreadable, never as absent",
          "UNREADABLE" in reasons(r, "broken"), reasons(r, "broken"))
    r = pf(["Bad;id"], [plan("good")], operator_go="op")
    check("a non-plan-id string is refused", "not a plan id" in reasons(r, "Bad;id"))

    # ---- approval --------------------------------------------------------
    calls = []

    def counting(pid):
        calls.append(pid)
        return True, "fixture"

    r = pf(["p"], [plan("p")], decisions=None, premises=counting)
    check("approvals exec FAILED and no --operator-go -> REFUSED (fail closed)",
          not r["ok"] and "exec failed" in reasons(r, "p") and not r["approvals_readable"],
          reasons(r, "p"))
    check("...and premises were never run for it (cheap refusal first)", calls == [], str(calls))
    r = pf(["p"], [plan("p")], decisions=None, operator_go="Mathias at the ops console")
    check("exec failed BUT --operator-go given -> runnable, consent recorded",
          r["ok"] and row(r, "p")["consent_source"] == "operator-go: Mathias at the ops console",
          str(row(r, "p")))
    r = pf(["p"], [plan("p")], decisions=[])
    check("readable approvals with nothing for this plan -> REFUSED",
          not r["ok"] and "no operator approval" in reasons(r, "p"), reasons(r, "p"))
    r = pf(["p"], [plan("p")], [approve("p", window="sun-attended:2026-09-20")])
    check("an approval scoped to a SCHEDULED window does not authorize a NOW run",
          not r["ok"] and "scoped" in reasons(r, "p"), reasons(r, "p"))
    r = pf(["p"], [plan("p")], [approve("p", window="now:2026-09-12")])
    check("a stale now: approval (3 days old) does not authorize",
          not r["ok"], reasons(r, "p"))
    r = pf(["p"], [plan("p")], [approve("p", window="now:2026-09-14")])
    check("a now: approval from yesterday (timezone edge) authorizes", r["ok"], reasons(r, "p"))
    r = pf(["p"], [plan("p")], [approve("p", decision="deny")], operator_go="op")
    check("a recorded pending DENY refuses even with --operator-go",
          not r["ok"] and "DENIED" in reasons(r, "p"), reasons(r, "p"))
    r = pf(["p"], [plan("p")], [dict(approve("p"), exec_state="executed")])
    check("an already-executed approval is not a live GO", not r["ok"], reasons(r, "p"))

    check("parse_decisions: non-zero exec -> None (not approval)",
          rn.parse_decisions(1, '{"decisions": []}') is None)
    check("parse_decisions: garbage -> None", rn.parse_decisions(0, "error: pod not found") is None)
    check("parse_decisions: wrong shape -> None", rn.parse_decisions(0, '{"x": 1}') is None)
    check("parse_decisions: good -> rows",
          rn.parse_decisions(0, '{"decisions": [{"key": "a"}]}') == [{"key": "a"}])

    def raising_runner(*a, **k):
        raise FileNotFoundError("kubectl")

    class _R:
        returncode, stdout = 1, ""

    check("fetch_pending_decisions: runner raises -> None",
          rn.fetch_pending_decisions(runner=raising_runner) is None)
    check("fetch_pending_decisions: exec rc!=0 -> None",
          rn.fetch_pending_decisions(runner=lambda *a, **k: _R()) is None)

    # ---- premises ----------------------------------------------------------
    r = pf(["p"], [plan("p")], [approve("p")], premises=lambda pid: (False, "image-is-current FAILED"))
    check("premises FAIL -> REFUSED", not r["ok"] and "image-is-current" in reasons(r, "p"),
          reasons(r, "p"))

    def boom(pid):
        raise RuntimeError("checker crashed")

    r = pf(["p"], [plan("p")], [approve("p")], premises=boom)
    check("premises checker RAISES -> REFUSED (fail closed)",
          not r["ok"] and "fail closed" in reasons(r, "p"), reasons(r, "p"))

    # ---- partial + dependencies -------------------------------------------
    r = pf(["a", "b"], [plan("a"), plan("b", status="draft")], [approve("a"), approve("b")])
    check("partial: one refused -> exit 1, runnable remainder still sequenced",
          r["partial"] and rn.exit_code(r) == 1 and [s["plan_id"] for s in r["sequence"]] == ["a"],
          str(r["sequence"]))
    r = pf(["dep", "child"], [plan("dep", status="draft"), plan("child", depends_on=["dep"])],
           [approve("dep"), approve("child")])
    check("a dependant whose in-run dependency was refused is dropped too",
          not row(r, "child")["ok"] and "was refused" in reasons(r, "child") and not r["sequence"],
          str(r["plans"]))
    r = pf(["child"], [plan("dep", status="scheduled"), plan("child", depends_on=["dep"])],
           [approve("child")])
    check("unmet depends_on outside the run -> REFUSED",
          "unmet depends_on" in reasons(r, "child"), reasons(r, "child"))
    r = pf(["child"], [plan("dep", status="executed"), plan("child", depends_on=["dep"])],
           [approve("child")])
    check("an executed dependency does not block", r["ok"], reasons(r, "child"))
    r = pf(["child"], [plan("child", depends_on=["gone"])], [approve("child")])
    check("a dead depends_on ref refuses (unenforceable guard)",
          "names no existing plan" in reasons(r, "child"), reasons(r, "child"))

    # ---- ordering ------------------------------------------------------------
    plans = [plan("z-low", risk="low"), plan("a-medium"), plan("m-high", risk="high"),
             plan("b-high", risk="high"),
             plan("infra", risk="low", touches={"shared": ["cert-manager"]})]
    ids = [p["plan_id"] for p in plans]
    r = pf(ids, plans, [approve(i) for i in ids])
    order = [s["plan_id"] for s in r["sequence"]]
    check("order: shared infra first, then risk high->low, stable by plan_id",
          order == ["infra", "b-high", "m-high", "a-medium", "z-low"], str(order))
    check("order: step after a shared-infra step is flagged settle_before",
          r["sequence"][1]["settle_before"] and "shared infra" in r["sequence"][1]["settle_reason"],
          str(r["sequence"][1]))
    check("order: every step after the first re-verifies health",
          [s["reverify_health_before"] for s in r["sequence"]] == [False, True, True, True, True])
    r2 = pf(list(reversed(ids)), list(reversed(plans)), [approve(i) for i in ids])
    check("order is deterministic regardless of request order",
          [s["plan_id"] for s in r2["sequence"]] == order)

    dep_plans = [plan("aaa-child", risk="high", depends_on=["zzz-parent"]),
                 plan("zzz-parent", risk="low")]
    r = pf(["aaa-child", "zzz-parent"], dep_plans, [approve("aaa-child"), approve("zzz-parent")])
    check("order: an in-run depends_on precedes its dependant despite priority",
          [s["plan_id"] for s in r["sequence"]] == ["zzz-parent", "aaa-child"],
          str([s["plan_id"] for s in r["sequence"]]))
    ordered, errs = rn.order_plans([plan("x", depends_on=["y"]), plan("y", depends_on=["x"])])
    check("order: a depends_on cycle is reported, not looped on", errs and len(ordered) == 2, str(errs))

    # conflicts: one-sided declaration (the live shape, 21 of 21), flagged on the LATER step
    cplans = [plan("first", risk="high"), plan("second", risk="low", conflicts_with=["first"])]
    r = pf(["first", "second"], cplans, [approve("first"), approve("second")])
    seq = {s["plan_id"]: s for s in r["sequence"]}
    check("conflict pair (one-sided) is ALLOWED in one serial run",
          r["ok"] and r["conflict_pairs"] == [["first", "second"]], str(r))
    check("...the later step is flagged settle_before with the conflict named",
          seq["second"]["settle_before"] and "first" in seq["second"]["settle_reason"]
          and "serial" in seq["second"]["settle_reason"], str(seq["second"]))
    check("...the earlier step is not flagged, but knows its partner",
          not seq["first"]["settle_before"] and seq["first"]["conflicts_in_run"] == ["second"],
          str(seq["first"]))
    r = pf(["first", "second"], [plan("first", risk="high", conflicts_with=["second"]),
                                 plan("second", risk="low")],
           [approve("first"), approve("second")])
    check("conflict declared in the OTHER direction is flagged the same way",
          {s["plan_id"]: s for s in r["sequence"]}["second"]["settle_before"])
    r = pf(["a", "b"], [plan("a"), plan("b")], [approve("a"), approve("b")])
    check("no conflict + no shared infra -> no settle flag (the flag discriminates)",
          not any(s["settle_before"] for s in r["sequence"]))

    # ---- B3: depends_on_in_run is emitted, not only used for ordering ----------
    r = pf(["aaa-child", "zzz-parent", "solo"],
           dep_plans + [plan("solo", depends_on=["zzz-parent-executed-elsewhere"])],
           [approve("aaa-child"), approve("zzz-parent"), approve("solo")])
    seqd = {s["plan_id"]: s for s in r["sequence"]}
    check("B3: every sequence entry carries depends_on_in_run",
          r["sequence"] and all("depends_on_in_run" in s for s in r["sequence"]), str(r["sequence"]))
    r = pf(["aaa-child", "zzz-parent"],
           [plan("aaa-child", risk="high", depends_on=["zzz-parent", "done-dep"]),
            plan("zzz-parent", risk="low"), plan("done-dep", status="executed")],
           [approve("aaa-child"), approve("zzz-parent")])
    seqd = {s["plan_id"]: s for s in r["sequence"]}
    check("B3: dependant lists its in-run dependency (and NOT an already-executed one)",
          seqd.get("aaa-child", {}).get("depends_on_in_run") == ["zzz-parent"], str(seqd))
    check("B3: the dependency itself has an empty depends_on_in_run",
          seqd.get("zzz-parent", {}).get("depends_on_in_run") == [], str(seqd))

    # ---- B2 defence in depth: a plan already stamped now:<today> -------------
    stamped = plan("stamped", status="scheduled", window="now:2026-09-15")
    r = pf(["stamped"], [stamped], [approve("stamped")])
    check("B2: a plan stamped now:<today> (not executed) is REFUSED as already in a NOW run",
          not r["ok"] and "already in an on-demand run today" in reasons(r, "stamped"),
          reasons(r, "stamped"))
    r = pf(["stamped"], [stamped], [approve("stamped")], operator_go="Mathias at the console")
    check("B2: --operator-go alone does not lift it (needs --resume too)",
          not r["ok"] and "already in an on-demand run today" in reasons(r, "stamped"),
          reasons(r, "stamped"))
    r = rn.preflight(["stamped"], [stamped], [], OD, [approve("stamped")], None, TODAY,
                     PASS_PREMISES, resume=True)
    check("B2: --resume alone does not lift it",
          "already in an on-demand run today" in reasons(r, "stamped"), reasons(r, "stamped"))
    r = rn.preflight(["stamped"], [stamped], [], OD, [approve("stamped")],
                     "Mathias at the console", TODAY, PASS_PREMISES, resume=True)
    check("B2: --operator-go + --resume lets the SAME run continue it",
          r["ok"] and r["resume"] is True, reasons(r, "stamped"))
    r = pf(["y"], [plan("y", window="now:2026-09-14")], [approve("y")])
    check("B2: a stamp from YESTERDAY is not 'already in a run today'",
          "already in an on-demand run today" not in reasons(r, "y"), reasons(r, "y"))
    r = pf(["x"], [plan("x", status="executed", window="now:2026-09-15")], [approve("x")])
    check("B2: an EXECUTED plan stamped today is refused by status, not by the stamp guard",
          "already executed" in reasons(r, "x")
          and "already in an on-demand run today" not in reasons(r, "x"), reasons(r, "x"))

    # ---- N4: durable --operator-go consent ---------------------------------------
    r = pf(["p"], [plan("p")], decisions=None, operator_go="Mathias at the ops console 10:02")
    check("N4: --operator-go output carries the exact running-row notes string",
          r["running_row_notes"] == "operator-go: Mathias at the ops console 10:02"
          and "operator-go: Mathias at the ops console 10:02" in rn._human(r), str(r))
    r = pf(["p"], [plan("p")], [approve("p")])
    check("N4: without --operator-go there is no consent string to record",
          r["running_row_notes"] is None)

    r = pf(["a", "b"], [plan("a", est_duration_min=300), plan("b", est_duration_min=300)],
           [approve("a"), approve("b")])
    check("a sequence over the ceiling warns (each plan fits alone)",
          r["ok"] and any("ceiling" in w for w in r["warnings"]), str(r["warnings"]))

    # ---- stamp ---------------------------------------------------------------
    text = ('---\nplan_id: demo\nstatus: awaiting-go   # a comment\n'
            'window: "sun-attended:2026-09-20"   # old note\n'
            '                 # continuation comment\nrisk: low\n---\n'
            '# Body\nwindow: this-is-body-text\n')
    new, err = rn.stamp_text(text, "now:2026-09-15", "note")
    fm_new = yaml.safe_load(new.split("---", 2)[1]) if new else {}
    check("stamp_text: window rewritten to now:<date>",
          err is None and fm_new.get("window") == "now:2026-09-15", str(err))
    check("stamp_text: body untouched (a body 'window:' line is not frontmatter)",
          new.split("---", 2)[2] == text.split("---", 2)[2])
    check("stamp_text: only the window line differs",
          [ln for ln in new.splitlines() if ln not in text.splitlines()]
          == ['window: "now:2026-09-15"   # note'], new)
    new2, err2 = rn.stamp_text("---\nplan_id: x\nstatus: vetted\n---\nbody\n", "now:2026-09-15", "n")
    check("stamp_text: inserts a window line when absent",
          err2 is None and yaml.safe_load(new2.split("---", 2)[1])["window"] == "now:2026-09-15"
          and new2.endswith("---\nbody\n"), str(new2))
    check("stamp_text: no frontmatter -> error", rn.stamp_text("# nope\n", "now:x", "n")[1])
    check("stamp_text: two window lines -> error",
          rn.stamp_text("---\nwindow: a\nwindow: b\n---\n", "now:2026-09-15", "n")[1] is not None)

    # every real plan file: stamping changes exactly the window key and nothing else
    real = sorted(p for p in (REPO / "runbooks/maintenance/plans").glob("*.md")
                  if p.name.lower() != "readme.md")
    bad = []
    for p in real:
        t = p.read_text()
        try:
            before = yaml.safe_load(t.split("---", 2)[1])
        except Exception:  # noqa: BLE001 — unparseable plans are validate_plans' job
            continue
        n, e = rn.stamp_text(t, "now:2026-09-15", "test")
        if e or t.split("---", 2)[2] != n.split("---", 2)[2]:
            bad.append(f"{p.name}: {e}")
            continue
        after = yaml.safe_load(n.split("---", 2)[1])
        if after.get("window") != "now:2026-09-15" or \
                {k: v for k, v in after.items() if k != "window"} != \
                {k: v for k, v in before.items() if k != "window"}:
            bad.append(p.name)
    check(f"stamp_text on all {len(real)} real plan files changes only window",
          real and not bad, str(bad))

    td = Path(tempfile.mkdtemp(prefix="run-now-test-"))
    try:
        good_src = ("---\nplan_id: good-copy\nstatus: vetted\nrisk: low\n"
                    "est_duration_min: 20\nneeds_reboot: false\nwindow: null\n---\n# body\n")
        draft_src = good_src.replace("good-copy", "draft-copy").replace("vetted", "draft")
        (td / "good-copy.md").write_text(good_src)
        (td / "draft-copy.md").write_text(draft_src)
        if real:
            shutil.copy(real[0], td / real[0].name)
        tplans = []
        for f in sorted(td.glob("*.md")):
            meta = yaml.safe_load(f.read_text().split("---", 2)[1]) or {}
            meta["_path"] = str(f)
            tplans.append(meta)
        stamped, refused = rn.stamp_plans(["good-copy", "draft-copy"], tplans, OD, TODAY)
        check("stamp: one refusal writes NOTHING (all-or-nothing)",
              not stamped and refused and (td / "good-copy.md").read_text() == good_src,
              str(refused))
        stamped, refused = rn.stamp_plans(["good-copy"], tplans, OD, TODAY, dry_run=True)
        check("stamp --dry-run writes nothing",
              stamped and (td / "good-copy.md").read_text() == good_src)
        stamped, refused = rn.stamp_plans(["good-copy"], tplans, OD, TODAY)
        written = yaml.safe_load((td / "good-copy.md").read_text().split("---", 2)[1])
        check("stamp writes now:<date> on the temp copy",
              not refused and written["window"] == "now:2026-09-15"
              and written["status"] == "vetted", str(written))
        boot = [dict(p, needs_reboot=True) if p.get("plan_id") == "good-copy" else p for p in tplans]
        stamped, refused = rn.stamp_plans(["good-copy"], boot, OD, TODAY)
        check("stamp refuses a needs_reboot plan", not stamped and "needs_reboot" in str(refused))
    finally:
        shutil.rmtree(td, ignore_errors=True)

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} -> {', '.join(FAILURES)}")
        return 1
    print("all run-now tests passed")
    return 0


def test_pytest_entry() -> None:
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
