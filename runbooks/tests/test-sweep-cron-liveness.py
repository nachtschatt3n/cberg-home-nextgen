#!/usr/bin/env python3
"""Regression tests: the 48h sweep cron is asserted against the sweep_cycles
ledger the way maintenance windows are asserted against window_runs
(F-8eea4d9e, F-0ad5ad13, F-74fcc1c3 — one symptom, three causes).

The in-cluster cron that fires the sweep reports `ok` on DELIVERY (prompt
typed into the Mac pane, process exited) and never on completion. Five 48h
occurrences (08-30, 09-01, 09-03, 09-05, 09-09) produced no sweep_cycles row
while the cron read ok every time; on 2026-09-21 a sixth ran 30.0 min,
recorded success and wrote nothing. Nothing on the Mac side asserted the
sweep ledger: sweep-heartbeat reads MAX(started_at), so a manual stand-in
masks a cron miss and every older miss is invisible.

Pinned here, against the module's own functions on the ledger AS READ on
2026-09-22 (sweep_cycles, last 30 days, trigger + started_at):
  1. 7-day lookback at 2026-09-22T09:00Z: exactly ONE miss, the 09-21
     occurrence — F-0ad5ad13's measured incident — and the operator's manual
     16:49Z cycle is listed as covering it, never as satisfying it.
  2. 30-day lookback reproduces the ledger audit in F-8eea4d9e VERBATIM:
     08-30, 09-01, 09-03, 09-05, 09-09 — plus 09-21.
  3. The grid is anchored, not re-anchored: a run that queued 7h behind a
     busy console still counts as its occurrence and does not shift the next
     expectation; a grid point is due only after the grace.
  4. An empty cron ledger never reads 0: missing_count is every grid point
     the lookback holds, with no_cron_cycle_in_window set.
  5. No DSN => verified False and missing_count None; the metrics exposition
     then carries verified=0 and NO count (absent() is the unverified arm);
     verified => the count and newest-cycle age are exposed.
  6. human() prints the misses with their cover note (the F-74fcc1c3 shape:
     a 'manual' cycle exactly at cron time), prints NOT VERIFIED when
     unreadable, and tolerates a report dict without the key (older fixtures).
  7. reconcile() carries the key.
  8. COMMISSIONING STRAWS: (a) the pre-fix reader — newest cycle of ANY
     trigger — calls this ledger fresh (16h) at the very moment the detector
     reports the 09-21 miss; (b) the detector with the trigger filter removed
     (every cycle treated as cron) loses HALF the 30-day misses, including
     the live one.

Hermetic: no DB, no subprocess.
Run: python3 runbooks/tests/test-sweep-cron-liveness.py
"""
from __future__ import annotations

import importlib.util
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ["_MISE_ACTIVATED"] = "1"
os.environ.pop("SWEEP_PG_DSN", None)
REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("mp", REPO / "runbooks/maintenance-plan.py")
mp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mp)

FAILURES: list[str] = []
ERROR_MARKS = ("Traceback", "Exception:", "Error:")


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


def count(population, pred) -> int:
    items = list(population)
    if not items:
        raise AssertionError("count(): EMPTY population — nothing was observed")
    joined = "\n".join(str(x) for x in items)
    if any(m in joined for m in ERROR_MARKS):
        raise AssertionError(f"count(): population carries error text: {joined[:120]!r}")
    return sum(1 for x in items if pred(x))


def ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


# sweep_cycles as read 2026-09-22 (30 days): trigger='cron' rows ...
CRON = [ts(x) for x in (
    "2026-08-24T02:02Z", "2026-08-26T02:03Z", "2026-08-28T02:00Z",
    "2026-09-07T02:00Z", "2026-09-11T02:01Z", "2026-09-13T02:01Z",
    "2026-09-15T02:02Z", "2026-09-17T02:08Z", "2026-09-19T02:03Z")]
# ... and every other trigger (manual / alert). 09-05 02:02 is a 'manual' row
# at exactly cron time — the lost-label shape of F-74fcc1c3.
OTHER = [ts(x) for x in (
    "2026-08-26T02:29Z", "2026-08-27T23:21Z", "2026-08-28T10:58Z",
    "2026-08-31T05:51Z", "2026-09-03T06:45Z", "2026-09-04T06:25Z",
    "2026-09-05T02:02Z", "2026-09-05T18:48Z", "2026-09-06T13:28Z",
    "2026-09-07T22:23Z", "2026-09-10T05:16Z", "2026-09-11T13:24Z",
    "2026-09-13T23:29Z", "2026-09-14T05:30Z", "2026-09-19T10:45Z",
    "2026-09-21T16:49Z")]
NOW = ts("2026-09-22T09:00Z")


def dates(report) -> list[str]:
    return [m["expected"][:10] for m in report["missing"]]


def metric_names(text: str) -> set[str]:
    """Sample names in a text exposition (HELP prose may mention other names)."""
    return {ln.split("{", 1)[0].split(" ", 1)[0] for ln in text.splitlines()
            if ln and not ln.startswith("#")}


def report_for(sl) -> dict:
    """A minimal reconcile() dict for human()."""
    return {"today": "2026-09-22", "held_count": 0, "held_error": None,
            "next_windows": [], "needs_plan": [], "age_cooldown": [],
            "execution_classes": [], "cron_parity": {"errors": [], "verified": True},
            "window_liveness": {"missing": [], "stuck": [], "verified": False},
            "sweep_cron_liveness": sl,
            "validation_errors": [], "ambiguous_matches": [], "stale": [],
            "orphan_plans": [], "awaiting_go": [], "approved_pending_exec": [],
            "scheduled": {}, "warnings": [], "plan_status": {}}


CFG = {"windows": [], "timezone": "Europe/Berlin"}

# 1 — the live incident, 7-day lookback
r7 = mp.missing_sweep_occurrences(CRON, NOW, OTHER)
check("7d: exactly one miss, the 2026-09-21 occurrence (F-0ad5ad13's incident)",
      r7["missing_count"] == 1 and dates(r7) == ["2026-09-21"], str(r7))
check("7d: the miss is dated on the grid (02:02Z from the anchor), not on any row",
      r7["missing"][0]["expected"].startswith("2026-09-21T02:0"), str(r7["missing"]))
check("7d: the operator's manual 16:49Z cycle is listed as COVER, never as satisfying it",
      r7["missing"][0]["covered_by_other_trigger"] == ["2026-09-21T16:49:00Z"], str(r7["missing"]))
check("7d: newest cron cycle and its age are reported",
      r7["newest_cron_at"] == "2026-09-19T02:03:00Z" and abs(r7["newest_cron_age_hours"] - 78.9) < 0.2,
      str(r7))
check("7d: an anchor older than the lookback floor is used (the read window reaches back)",
      r7["anchor"] < r7["newest_cron_at"] and not r7["no_cron_cycle_in_window"], str(r7))

# 2 — the record's 30-day ledger audit, verbatim
r30 = mp.missing_sweep_occurrences(CRON, NOW, OTHER, lookback_days=30)
check("30d: reproduces F-8eea4d9e's five misses (08-30, 09-01, 09-03, 09-05, 09-09) plus 09-21",
      dates(r30) == ["2026-08-30", "2026-09-01", "2026-09-03", "2026-09-05",
                     "2026-09-09", "2026-09-21"], str(dates(r30)))
by_date = {m["expected"][:10]: m for m in r30["missing"]}
check("30d: the 09-05 miss names the 'manual' cycle at cron time (the lost-label shape)",
      "2026-09-05T02:02:00Z" in by_date["2026-09-05"]["covered_by_other_trigger"], str(by_date["2026-09-05"]))
check("30d: the 09-01 miss has NO cover — the cluster went unaudited",
      by_date["2026-09-01"]["covered_by_other_trigger"] == [], str(by_date["2026-09-01"]))
check("30d: the satisfied grid points are exactly the cron rows (no false miss on a row 2 min early)",
      count(CRON, lambda t: t.strftime("%Y-%m-%d") in dates(r30)) == 0, str(dates(r30)))

# 3 — anchoring, lateness, grace
late = [ts("2026-09-19T02:03Z"), ts("2026-09-21T09:00Z")]      # second run queued 7h
rl = mp.missing_sweep_occurrences(late, ts("2026-09-22T09:00Z"))
check("a run 7h late still satisfies its occurrence (no miss)", rl["missing_count"] == 0, str(rl))
rl2 = mp.missing_sweep_occurrences(late, ts("2026-09-23T12:00Z"))
check("...and does NOT shift the grid: the next expectation stays at 09-23 02:03, not 09:00",
      dates(rl2) == ["2026-09-23"] and rl2["missing"][0]["expected"] == "2026-09-23T02:03:00Z", str(rl2))
on_time = [ts("2026-09-19T02:03Z"), ts("2026-09-21T02:03Z")]
check("grace: 09-23 02:03 is not due at 04:00 (grace 4h has not elapsed)",
      mp.missing_sweep_occurrences(on_time, ts("2026-09-23T04:00Z"))["missing_count"] == 0)
check("grace: ...and is due at 06:10",
      dates(mp.missing_sweep_occurrences(on_time, ts("2026-09-23T06:10Z"))) == ["2026-09-23"])
check("a run 3h EARLY (inside grace) satisfies its occurrence",
      mp.missing_sweep_occurrences([ts("2026-09-19T02:03Z"), ts("2026-09-20T23:10Z")],
                                   ts("2026-09-22T09:00Z"))["missing_count"] == 0)

# 4 — empty cron ledger never reads 0
r0 = mp.missing_sweep_occurrences([], NOW, OTHER)
check("no cron cycle in the read window: no_cron_cycle_in_window, count = every grid point (3 in 7d)",
      r0["no_cron_cycle_in_window"] and r0["missing_count"] == 3 and r0["missing"] == [], str(r0))

# 5 — verified / unverified through the report + exposition
unv = mp.sweep_cron_liveness_report(now=NOW)
check("no SWEEP_PG_DSN: verified False and missing_count None, never 0",
      unv["verified"] is False and unv["missing_count"] is None, str(unv))
mt_unv = mp.sweep_cron_metrics_text(unv)
check("metrics unverified: verified=0 exposed, lookback exposed, NO count sample",
      "sweep_cron_liveness_verified 0" in mt_unv and "sweep_cron_lookback_days 7" in mt_unv
      and "sweep_cron_missing_count" not in metric_names(mt_unv)
      and "sweep_cron_newest_cycle_timestamp_seconds" not in metric_names(mt_unv), mt_unv)
ver = {**unv, **r7, "verified": True}
mt = mp.sweep_cron_metrics_text(ver)
check("metrics verified: the count carries the lookback label and the newest cycle is a TIMESTAMP, not an age",
      'sweep_cron_missing_count{lookback_days="7"} 1' in mt
      and f"sweep_cron_newest_cycle_timestamp_seconds {int(ts('2026-09-19T02:03Z').timestamp())}" in mt
      and "age_hours" not in mt and "sweep_cron_liveness_verified 1" in mt, mt)

# 6 — human()
h = mp.human(report_for({**unv, **r30, "verified": True}), CFG)
check("human: the misses are printed with their dates",
      "SWEEP CRON OCCURRENCES WITHOUT A CYCLE (6)" in h and "expected 2026-09-21T02:0" in h, h)
check("human: a covered miss names the lost-label possibility (F-74fcc1c3), an uncovered one says unaudited",
      "F-74fcc1c3" in h and "went unaudited" in h, h)
check("human: the figure line carries the lookback and the age-out caveat",
      "sweep_cron_missing_count 6" in h and "AGED OUT" in h, h)
h_unv = mp.human(report_for(unv), CFG)
check("human unverified: NOT VERIFIED line, no figure, no misses",
      "sweep-cron liveness NOT VERIFIED" in h_unv and "sweep_cron_missing_count" not in h_unv, h_unv)
r_no_key = report_for(unv)
del r_no_key["sweep_cron_liveness"]
h_none = mp.human(r_no_key, CFG)
check("human: a report without the key (older fixture shape) renders with no sweep-cron lines",
      "sweep-cron" not in h_none and "sweep_cron" not in h_none, h_none)
r_empty = mp.human(report_for({**unv, **r0, "verified": True}), CFG)
check("human: an empty cron ledger is a loud line naming every expected occurrence unaccounted for",
      "NO trigger=cron SWEEP CYCLE" in r_empty and "3 expected" in r_empty, r_empty)

# 7 — reconcile() carries the key (held / parity / plans stubbed; no DSN => unverified)
mp.get_held = lambda: ([], None)
mp.cron_parity = lambda cfg: ([], True)
mp.load_plans = lambda cfg: []
rec = mp.reconcile({**CFG, "planning": {"stale_after_days": 14}}, NOW.date(), decisions=[])
check("reconcile(): sweep_cron_liveness is in the report, unverified without a DSN",
      isinstance(rec.get("sweep_cron_liveness"), dict) and rec["sweep_cron_liveness"]["verified"] is False,
      str(rec.get("sweep_cron_liveness")))

# 8 — COMMISSIONING STRAWS
newest_any = max(CRON + OTHER)
age_any_h = (NOW - newest_any).total_seconds() / 3600
check("STRAW (a): the pre-fix reader — newest cycle of ANY trigger — calls this ledger fresh "
      "(16h old, under the 50h page) while the detector reports the 09-21 cron miss",
      age_any_h < 50 and r7["missing_count"] == 1, f"any-trigger age {age_any_h:.1f}h")
r_unfiltered = mp.missing_sweep_occurrences(sorted(CRON + OTHER), NOW, [], lookback_days=30)
check("STRAW (b): without the trigger filter (every cycle treated as cron) HALF the 30-day misses "
      "vanish — including the live 09-21 one",
      r_unfiltered["missing_count"] == 3 and "2026-09-21" not in dates(r_unfiltered)
      and r30["missing_count"] == 6, str(dates(r_unfiltered)))

print(f"\n{len(FAILURES)} failure(s)" if FAILURES else "\nall checks passed")
raise SystemExit(1 if FAILURES else 0)
