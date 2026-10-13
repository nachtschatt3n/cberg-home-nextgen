#!/usr/bin/env python3
"""Regression tests: a `waived` window_runs row removes a deliberately-skipped
occurrence from window_runs_missing_count WITHOUT ever counting as a run.

Operator decision 2026-10-13 (vacation): four declared slots were let go
unrun on purpose and paged MaintenanceWindowMissed / RepeatedlyMissed for a
week. The waiver must silence exactly that and nothing more. Pinned, each on
the side where a careless implementation fails:

  * a valid waiver leaves the missing list and appears in waived (4 -> 0 / 0 -> 4);
  * it is NEVER a run: completed_run_rows excludes it, so ops-retro's `run`
    does not rise and it covers no other slot (a waived nightly row must not
    cover a different day's nightly, nor absorb an attended slot);
  * fail closed: no notes, a run_date of today or later, an unknown slot's
    row, or an outcome that merely CONTAINS the word -> the slot stays missing;
  * a real completed row for the same slot wins (nothing is "waived");
  * the unverified report keeps its pinned three-key shape and None counts;
  * the exposition carries window_runs_waived_count only when verified;
  * the recorder refuses an unreasoned / future / finalize / non-ad-hoc waiver.

Hermetic: psycopg is replaced by a fake. Run:
  python3 runbooks/tests/test-window-liveness-waived.py
"""
from __future__ import annotations

import importlib.util
import os
import sys
import types
from datetime import date, datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


mp = load("mp", "runbooks/maintenance-plan.py")
rec = load("rec", "runbooks/window-run-record.py")
retro = load("retro", "runbooks/ops-retro.py")

FAILURES: list[str] = []
TODAY = date(2026, 10, 13)
CFG = {"windows": [
    {"id": "nightly", "day": "daily", "duration_min": 90},
    {"id": "sat-attended", "day": "saturday", "duration_min": 180},
    {"id": "sun-attended", "day": "sunday", "duration_min": 180},
], "on_demand": {"id": "now", "duration_min": 240}, "timezone": "Europe/Berlin"}


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


def ts(day, hour=3):
    return datetime(*map(int, day.split("-")), hour, 30, tzinfo=timezone.utc)


def row(slot, day, outcome, notes=None, trigger="cron", started=None):
    # slot, run_date, started_at, finished_at, outcome, trigger, notes
    st = started or ts(day)
    return (slot, day, st, None if outcome == "running" else st, outcome, trigger, notes)


def liveness(rows, today=TODAY):
    """window_liveness_report with the DB replaced by `rows`."""
    class Cur:
        def __enter__(s): return s
        def __exit__(s, *a): return False
        def execute(s, *a, **k): pass
        def fetchall(s): return list(rows)

    class Conn(Cur):
        def cursor(s): return Cur()

    fake = types.ModuleType("psycopg")
    fake.connect = lambda *a, **k: Conn()
    saved_mod, saved_dsn = sys.modules.get("psycopg"), os.environ.get("SWEEP_PG_DSN")
    sys.modules["psycopg"] = fake
    os.environ["SWEEP_PG_DSN"] = "fake"
    try:
        return mp.window_liveness_report(CFG, today, now=ts("2026-10-13", 8))
    finally:
        if saved_mod is None:
            sys.modules.pop("psycopg", None)
        else:
            sys.modules["psycopg"] = saved_mod
        if saved_dsn is None:
            os.environ.pop("SWEEP_PG_DSN", None)
        else:
            os.environ["SWEEP_PG_DSN"] = saved_dsn


def nonempty(xs):
    xs = list(xs)
    assert xs, "empty population: nothing was observed"
    return xs


# every expected slot in the 7-day lookback EXCEPT the four we waive has a real row
EXPECTED = mp.expected_slots(CFG, TODAY)
WAIVE = ["nightly:2026-10-10", "nightly:2026-10-11",
         "sat-attended:2026-10-10", "sun-attended:2026-10-11"]
RAN = [row(s.split(":")[0], s.split(":")[1], "green")
       for s in (f"{a}:{b}" for a, b in EXPECTED) if s not in WAIVE]
WAIVERS = [row(s.split(":")[0], s.split(":")[1], "waived", "operator on vacation",
               trigger="ad-hoc") for s in WAIVE]


def test_report():
    nonempty(EXPECTED)
    check("setup: all four target slots are really expected",
          all(tuple(w.split(":")) in set(EXPECTED) for w in WAIVE))
    before = liveness(RAN)
    check("before: the four deliberate skips are missing",
          sorted(before["missing"]) == sorted(WAIVE) and before["waived"] == [],
          str(before))
    after = liveness(RAN + WAIVERS)
    check("after: missing 4 -> 0", after["missing"] == [], str(after))
    check("after: waived 0 -> 4, listing exactly the four",
          sorted(after["waived"]) == sorted(WAIVE), str(after["waived"]))
    f = mp.liveness_figures(after["missing"], after["stuck"], True, TODAY, waived=after["waived"])
    check("figures: missing 0 and waived 4 side by side",
          f["window_runs_missing_count"] == 0 and f["window_runs_waived_count"] == 4)

    # one waiver only -> only that slot leaves
    one = liveness(RAN + WAIVERS[:1])
    check("one waiver removes only its own slot",
          sorted(one["missing"]) == sorted(WAIVE[1:]) and one["waived"] == WAIVE[:1], str(one))

    # fail-closed edges
    nonotes = [row(*w.split(":")[:1], w.split(":")[1], "waived", None, trigger="ad-hoc") for w in WAIVE]
    blank = [row(w.split(":")[0], w.split(":")[1], "waived", "   ", trigger="ad-hoc") for w in WAIVE]
    check("fail closed: a waiver with no notes waives nothing",
          sorted(liveness(RAN + nonotes)["missing"]) == sorted(WAIVE))
    check("fail closed: a whitespace-only reason waives nothing",
          sorted(liveness(RAN + blank)["missing"]) == sorted(WAIVE))
    future = [row("nightly", "2026-10-13", "waived", "pre-silence", trigger="ad-hoc"),
              row("nightly", "2026-10-20", "waived", "pre-silence", trigger="ad-hoc")]
    check("fail closed: a waiver dated today/future is ignored",
          mp.waived_slots(future, today=TODAY) == [])
    lookalike = [row(w.split(":")[0], w.split(":")[1], "waived-by-mistake", "x", trigger="ad-hoc")
                 for w in WAIVE]
    check("fail closed: only the exact outcome 'waived' counts",
          mp.waived_slots(lookalike, today=TODAY) == [])
    # waived row for a slot the YAML never expected: harmless, reported nowhere
    stray = [row("nightly", "2026-08-01", "waived", "ancient", trigger="ad-hoc")]
    check("a waiver for a non-expected slot changes nothing",
          liveness(RAN + stray)["waived"] == [] and sorted(liveness(RAN + stray)["missing"]) == sorted(WAIVE))
    # a real row beats a waiver
    both = RAN + WAIVERS + [row("nightly", "2026-10-10", "green")]
    r = liveness([x for x in both if x not in RAN[:0]])
    check("a real completed row for the slot wins: it is not reported as waived",
          "nightly:2026-10-10" not in r["waived"] and "nightly:2026-10-10" not in r["missing"], str(r))


def test_not_a_run():
    rows = [row("nightly", "2026-10-10", "waived", "vacation", trigger="ad-hoc")]
    check("completed_run_rows excludes a waived row", mp.completed_run_rows(rows) == [])
    check("completed_run_rows still includes a green row",
          mp.completed_run_rows([row("nightly", "2026-10-10", "green")]) == [("nightly", "2026-10-10")])
    # a waived row in slot `now`/ad-hoc must not cover that day's nightly or absorb anything
    now_w = row("now", "2026-10-10", "waived", "absorbs sat-attended:2026-10-10", trigger="ad-hoc")
    check("a waived row covers no nightly", mp.nightly_covered_by_on_demand([now_w]) == [])
    check("a waived row absorbs no attended slot",
          mp.attended_absorbed_by_on_demand([now_w]) == [])
    # waiving 10-10 must not cover 10-11
    r = liveness([x for x in RAN if x[:2] != ("nightly", "2026-10-11")] + WAIVERS[:1])
    check("a waiver is per-occurrence: it does not leak to the next day",
          "nightly:2026-10-11" in r["missing"] and "nightly:2026-10-10" not in r["missing"], str(r))


def test_shapes_and_exposition():
    check("unverified report keeps its pinned three-key shape",
          (lambda: (os.environ.pop("SWEEP_PG_DSN", None),
                    mp.window_liveness_report(CFG, TODAY))[1])()
          == {"missing": [], "stuck": [], "verified": False})
    u = mp.liveness_figures([], [], False, TODAY)
    check("unverified => waived count is None, never 0", u["window_runs_waived_count"] is None)
    tu = mp.liveness_metrics_text(u)
    check("unverified exposition has no waived line", "window_runs_waived_count " not in tu)
    f = mp.liveness_figures([], [], True, TODAY, waived=WAIVE)
    t = mp.liveness_metrics_text(f).splitlines()
    check("verified exposition: waived 4 beside missing 0",
          "window_runs_waived_count 4" in t
          and 'window_runs_missing_count{lookback_days="7"} 0' in t, "\n".join(t))
    check("exposition HELP says waived did NOT run",
          any(l.startswith("# HELP window_runs_waived_count") and "did NOT run" in l for l in t))
    plain = mp.liveness_figures(["nightly:2026-10-10"], [], True, TODAY)
    check("no waivers => waived count is a real 0", plain["window_runs_waived_count"] == 0)
    rep = {"today": TODAY.isoformat(), "held_count": 0, "held_error": None, "next_windows": [],
           "needs_plan": [], "age_cooldown": [], "execution_classes": [],
           "cron_parity": {"errors": [], "verified": True}, "window_liveness": f,
           "validation_errors": [], "ambiguous_matches": [], "stale": [], "orphan_plans": [],
           "awaiting_go": [], "approved_pending_exec": [], "scheduled": {}, "warnings": [],
           "plan_status": {}}
    lines = mp.human(rep, CFG).splitlines()
    check("human report prints waived beside missing, labelled not-a-run",
          any(l.startswith("window_runs_missing_count 0") and "waived 4" in l
              and "NOT counted as run" in l for l in lines))


def test_recorder():
    ap = rec.build_parser()

    def v(*argv, today="2026-10-13"):
        return rec.validate_args(ap.parse_args(list(argv)), today=today)

    base = ["--slot", "nightly", "--outcome", "waived", "--trigger", "ad-hoc"]
    good = base + ["--run-date", "2026-10-10", "--notes", "vacation"]
    check("recorder accepts a reasoned past ad-hoc waiver", v(*good) is None)
    check("recorder refuses no notes", v(*base, "--run-date", "2026-10-10") is not None)
    check("recorder refuses blank notes",
          v(*base, "--run-date", "2026-10-10", "--notes", "  ") is not None)
    check("recorder refuses a missing --run-date", v(*base, "--notes", "x") is not None)
    check("recorder refuses today", v(*base, "--run-date", "2026-10-13", "--notes", "x") is not None)
    check("recorder refuses the future", v(*base, "--run-date", "2026-10-14", "--notes", "x") is not None)
    check("recorder refuses --finalize", v(*good, "--finalize") is not None)
    check("recorder refuses a cron trigger",
          v("--slot", "nightly", "--outcome", "waived", "--trigger", "cron",
            "--run-date", "2026-10-10", "--notes", "x") is not None)
    check("recorder refuses a waiver that claims work done",
          v(*good, "--safe-updates", "3") is not None)
    check("other outcomes are unaffected",
          v("--slot", "nightly", "--outcome", "green", "--trigger", "cron") is None)


def test_retro():
    end = date(2026, 10, 13)
    base_rows = []
    for a, b in mp.expected_slots(CFG, end, lookback_days=retro.PERIOD_DAYS):
        if f"{a}:{b}" in WAIVE:
            continue
        # slot, run_date, started_at, finished_at, outcome, trigger, safe_updates, notes
        base_rows.append((a, b, ts(b), ts(b), "green", "cron", 1, None))
    waiver_rows = [(w.split(":")[0], w.split(":")[1], ts("2026-10-13", 7), ts("2026-10-13", 7),
                    "waived", "ad-hoc", 0, "vacation") for w in WAIVE]
    span = (datetime(2026, 10, 6, 6, tzinfo=timezone.utc), datetime(2026, 10, 13, 6, tzinfo=timezone.utc))
    b = retro.window_metrics(mp, CFG, base_rows, end, span)
    a = retro.window_metrics(mp, CFG, base_rows + waiver_rows, end, span)
    check("retro before: 4 missed", b["missed"]["value"] == 4, str(b["missed"]))
    check("retro after: 0 missed, 4 waived",
          a["missed"]["value"] == 0 and len(a["waived"]["value"]) == 4, str((a["missed"], a["waived"])))
    check("retro: waived slots are NOT counted as run (run unchanged)",
          a["run"]["value"] == b["run"]["value"], f"{b['run']['value']} vs {a['run']['value']}")
    check("retro: expected = run + missed + waived",
          a["expected"]["value"] == a["run"]["value"] + a["missed"]["value"] + len(a["waived"]["value"]))
    check("retro: the unreadable ledger reports waived as unmeasured too",
          retro.window_metrics(mp, CFG, None, end, span)["waived"]["measured"] is False)


for fn in (test_report, test_not_a_run, test_shapes_and_exposition, test_recorder, test_retro):
    print(fn.__name__)
    fn()

print()
if FAILURES:
    print(f"FAILED {len(FAILURES)}: " + "; ".join(FAILURES))
    sys.exit(1)
print("all passed")
