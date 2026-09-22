#!/usr/bin/env python3
"""Regression tests: window liveness exposes a FIGURE, with its age-out stated.

F-2dabaddb — a nightly window was silently lost and nothing alarmed: the
liveness report carried only lists for a human report. A PrometheusRule needs
a number. `window_runs_missing_count` is that number — and because the
assertion is a rolling 7-day lookback, a missed occurrence AGES OUT of it
silently a week later; a rule reading only the count would see it fall back
to 0 and call that recovery. So the lookback rides beside the count, in the
report, in the human output, and in the Prometheus exposition.

Pinned here:
  * liveness_figures() carries the count, the lookback, the floor and the
    age-out caveat; unverified => the counts are None, never 0;
  * liveness_metrics_text() exposes verified/lookback ALWAYS and the count
    ONLY when verified (absent() is the rule's unverified arm);
  * window_liveness_figures() wraps the three-key report, whose shape stays
    pinned (test-window-run-running-row asserts it by equality);
  * human() prints the figure on every verified run, 0 included, with the
    age-out caveat, and prints no figure when unverified.

Hermetic: no DB (SWEEP_PG_DSN is unset for the wrapper check).

Run: python3 runbooks/tests/test-window-liveness-figures.py
"""
from __future__ import annotations

import importlib.util
import os
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("mp", REPO / "runbooks/maintenance-plan.py")
mp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mp)

FAILURES: list[str] = []
ERROR_MARKS = ("Traceback", "Exception:", "Error:")
TODAY = date(2026, 9, 22)
CFG = {"windows": [{"id": "nightly", "day": "daily", "duration_min": 90,
                    "capacity_risk": 6, "allow_reboot": False, "mode": "unattended"}],
       "timezone": "Europe/Berlin"}


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


def report(wl):
    """A minimal reconcile() dict for human()."""
    return {"today": TODAY.isoformat(), "held_count": 0, "held_error": None,
            "next_windows": [], "needs_plan": [], "age_cooldown": [],
            "execution_classes": [], "cron_parity": {"errors": [], "verified": True},
            "window_liveness": wl, "validation_errors": [], "ambiguous_matches": [],
            "stale": [], "orphan_plans": [], "awaiting_go": [], "approved_pending_exec": [],
            "scheduled": {}, "warnings": [], "plan_status": {}}


def scenarios() -> dict:
    out = {}
    f = mp.liveness_figures(["nightly:2026-09-20"], [], True, TODAY)
    out["figures: window_runs_missing_count is the number of missing slots"] = (
        f.get("window_runs_missing_count") == 1 and f.get("window_runs_stuck_count") == 0)
    out["figures: the lookback and its floor ride beside the count"] = (
        f.get("lookback_days") == 7 and f.get("lookback_floor") == "2026-09-15")
    out["figures: the age-out caveat is stated in the report itself"] = (
        "7 days" in str(f.get("ages_out")) and "rolling" in str(f.get("ages_out")))
    out["figures: the original three keys are preserved"] = (
        f["missing"] == ["nightly:2026-09-20"] and f["stuck"] == [] and f["verified"] is True)
    u = mp.liveness_figures([], [], False, TODAY)
    out["figures: unverified => counts are None, NEVER 0"] = (
        u.get("window_runs_missing_count") is None and u.get("window_runs_stuck_count") is None
        and u["verified"] is False)
    f0 = mp.liveness_figures([], [], True, TODAY)
    out["figures: verified and clean => count is a real 0"] = f0.get("window_runs_missing_count") == 0

    t = mp.liveness_metrics_text(f).splitlines()
    out["exposition: verified gauge is 1 and the count is exposed with its lookback label"] = (
        count(t, lambda l: l == "window_runs_liveness_verified 1") == 1
        and count(t, lambda l: l == 'window_runs_missing_count{lookback_days="7"} 1') == 1
        and count(t, lambda l: l == "window_runs_stuck_count 0") == 1)
    out["exposition: the lookback is exposed as its own gauge"] = (
        count(t, lambda l: l == "window_runs_liveness_lookback_days 7") == 1)
    out["exposition: HELP text states the age-out"] = (
        count(t, lambda l: l.startswith("# HELP window_runs_liveness_lookback_days") and "AGES OUT" in l) == 1)
    tu = mp.liveness_metrics_text(u).splitlines()
    out["exposition: unverified => verified gauge 0 and NO count line (absent(), not 0)"] = (
        count(tu, lambda l: l == "window_runs_liveness_verified 0") == 1
        and count(tu, lambda l: l.startswith("window_runs_missing_count")) == 0
        and count(tu, lambda l: l == "window_runs_liveness_lookback_days 7") == 1)

    saved = os.environ.pop("SWEEP_PG_DSN", None)
    try:
        w = mp.window_liveness_figures(CFG, TODAY)
        r = mp.window_liveness_report(CFG, TODAY)
    finally:
        if saved is not None:
            os.environ["SWEEP_PG_DSN"] = saved
    out["wrapper: no DSN => unverified figures with count None"] = (
        w["verified"] is False and w.get("window_runs_missing_count") is None
        and w.get("lookback_days") == 7)
    out["wrapper: the three-key report shape stays pinned"] = (
        r == {"missing": [], "stuck": [], "verified": False})

    lines = mp.human(report(f), CFG).splitlines()
    out["human: prints the figure with the age-out caveat when verified"] = (
        count(lines, lambda l: l.startswith("window_runs_missing_count 1") and "AGED OUT" in l) == 1)
    lines0 = mp.human(report(f0), CFG).splitlines()
    out["human: prints the figure at 0 too (a verified zero is a measurement)"] = (
        count(lines0, lambda l: l.startswith("window_runs_missing_count 0")) == 1)
    linesu = mp.human(report(u), CFG).splitlines()
    out["human: prints NO figure when unverified, and says NOT VERIFIED"] = (
        count(linesu, lambda l: l.startswith("window_runs_missing_count")) == 0
        and count(linesu, lambda l: "NOT VERIFIED" in l) == 1)
    out["constant: the lookback used by expected_slots is the one exposed"] = (
        mp.WINDOW_LIVENESS_LOOKBACK_DAYS == 7
        and mp.expected_slots.__defaults__[0] == mp.WINDOW_LIVENESS_LOOKBACK_DAYS)
    return out


MUST_FAIL = [
    "figures: window_runs_missing_count is the number of missing slots",
    "figures: the lookback and its floor ride beside the count",
    "figures: the age-out caveat is stated in the report itself",
    "wrapper: no DSN => unverified figures with count None",
    "human: prints the figure with the age-out caveat when verified",
    "human: prints the figure at 0 too (a verified zero is a measurement)",
]


def main() -> int:
    print("test-window-liveness-figures")
    for name, ok in scenarios().items():
        check(name, ok)

    print("  -- commissioning straw: the three-key report only (pre-fix liveness)")
    saved = mp.liveness_figures
    mp.liveness_figures = (lambda missing, stuck, verified, today, lookback_days=7:
                           {"missing": list(missing), "stuck": list(stuck), "verified": bool(verified)})
    try:
        under = scenarios()
    finally:
        mp.liveness_figures = saved
    failed = [n for n in MUST_FAIL if under.get(n) is False]
    check("straw: every figure check FAILS with the figures reverted",
          len(failed) == len(MUST_FAIL), f"still passing: {sorted(set(MUST_FAIL) - set(failed))}")
    check("straw: the pinned three-key report still passes under the straw",
          under.get("wrapper: the three-key report shape stays pinned") is True)

    print()
    if FAILURES:
        print(f"FAILED ({len(FAILURES)}): {', '.join(FAILURES)}")
        return 1
    print("all window-liveness-figures tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
