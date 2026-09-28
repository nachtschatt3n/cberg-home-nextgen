"""Unit tests for runbooks/ops-retro.py metric functions.

The retro's one hard rule is NEVER A SILENT ZERO: a metric whose source could
not be read, or whose source does not cover the period (retention, a
convention that did not exist yet), must come out `measured: false` — and a
genuinely measured zero must come out `measured: true, value: 0`. Every
function here is exercised on both sides of that line.

Run:  python3 runbooks/tests/test-ops-retro.py
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("ops_retro", REPO / "runbooks/ops-retro.py")
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)
MP = R._load_mp()

FAILURES: list[str] = []
NOW = datetime(2026, 9, 28, 5, 30, tzinfo=timezone.utc)
SPANS = R.periods(NOW)
CUR, PREV = SPANS["current"], SPANS["previous"]


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


def unmeasured(m):
    return m["measured"] is False and m["value"] is None and m.get("reason")


def zero(m):
    return m["measured"] is True and m["value"] == 0


def t(days_ago, hour=2):
    return (NOW - timedelta(days=days_ago)).replace(hour=hour, minute=0)


def test_constructors_and_render():
    check("U() is unmeasured with a reason and a None value", unmeasured(R.U("x")))
    check("M(0) is a measured zero", zero(R.M(0, "src")))
    check("fmt never renders an unmeasured metric as 0",
          R.fmt(R.U("db down")).startswith("UNMEASURED") and "0" not in R.fmt(R.U("db down")))
    check("fmt renders a measured zero as 0", R.fmt(R.M(0, "s")) == "0")


def test_windows():
    cfg = {"windows": [{"id": "nightly", "day": "daily"}]}
    end = date(2026, 9, 28)
    m = R.window_metrics(MP, cfg, None, end, CUR)
    check("windows: source unavailable -> every metric unmeasured",
          all(unmeasured(v) for v in m.values()), str(m))
    rows = [("nightly", (end - timedelta(days=d)).isoformat(), t(d, 1), t(d, 2), "green", "cron", 1)
            for d in range(1, 8)]
    m = R.window_metrics(MP, cfg, rows, end, CUR)
    check("windows: 7 nightlies all run -> missed is a MEASURED 0",
          zero(m["missed"]) and m["expected"]["value"] == 7 and m["run"]["value"] == 7, str(m))
    # the 7-days-ago run started 01:00, before the span opened at 05:30
    check("windows: safe updates summed over runs STARTED in the span",
          m["safe_updates"]["value"] == 6, str(m["safe_updates"]))
    m = R.window_metrics(MP, cfg, rows[1:], end, CUR)
    check("windows: one missing row -> missed=1 naming the slot",
          m["missed"]["value"] == 1 and m["missed_slots"]["value"] == ["nightly:2026-09-27"], str(m["missed_slots"]))
    rows2 = [r[:6] + (None,) for r in rows]
    m = R.window_metrics(MP, cfg, rows2, end, CUR)
    check("windows: NULL safe_updates -> lower-bound, not a clean 0",
          m["safe_updates"].get("coverage") == "lower-bound", str(m["safe_updates"]))
    m = R.window_metrics(MP, cfg, [], date(2026, 8, 1), (NOW - timedelta(days=70), NOW - timedelta(days=63)))
    check("windows: period before the liveness epoch -> expected unmeasured, not 0",
          unmeasured(m["expected"]), str(m["expected"]))


def test_plans():
    m = R.plan_metrics(None, {}, None, CUR, NOW)
    check("plans: all sources down -> unmeasured",
          all(unmeasured(v) for v in m.values()), str(m))
    rows = [("a", "green", True, t(2)), ("b", "reverted", True, t(3)), ("c", "green", False, t(9))]
    m = R.plan_metrics(rows, {"a": t(12)}, [("x", t(10)), ("y", t(1))], CUR, NOW)
    check("plans: outcomes only count the period",
          m["outcomes"]["value"] == {"green": 1, "reverted": 1}, str(m["outcomes"]))
    check("plans: supervised/unsupervised split", m["supervised"]["value"] == 2 and zero(m["unsupervised"]))
    check("plans: queue age = draft -> executed in days", m["queue_age_days_median"]["value"] == 10.0,
          str(m["queue_age_days_median"]))
    check("plans: awaiting-go > 7d lists only the stale key",
          m["awaiting_go_over_7d"]["value"] == 1 and m["awaiting_go_over_7d"]["items"][0][0] == "x")
    m = R.plan_metrics([], {}, [], CUR, NOW)
    check("plans: no green execution -> queue age UNMEASURED (not 0 days)",
          unmeasured(m["queue_age_days_median"]))
    check("plans: empty open list -> awaiting-go is a measured 0", zero(m["awaiting_go_over_7d"]))
    m = R.plan_metrics(rows, {}, [], PREV, NOW)
    check("plans: awaiting-go is point-in-time -> previous period unmeasured",
          unmeasured(m["awaiting_go_over_7d"]))


def test_hitl():
    m = R.hitl_metrics(None, None, None, None, None, CUR)
    check("hitl: nothing readable -> all unmeasured", all(unmeasured(v) for v in m.values()), str(m))
    issues = {"p1": "go_no_go", "p2": "go_no_go", "w": "window_warning"}
    ev = [("p1", t(3, 1), "opened", ""), ("p1", t(3, 5), "decided", "approve"),
          ("p2", t(20), "opened", ""), ("p2", t(2, 2), "decided", "deny"),
          ("w", t(1), "opened", ""), ("p1", t(1), "expired", "")]
    m = R.hitl_metrics(issues, ev, [(t(1), "used SD-3 and SD-3; AskUserQuestion once")], [],
                       [(t(1), "fix: per SD-7")], CUR)
    check("hitl: go/no-go opened counts only go_no_go first-opens in period",
          m["gng_opened"]["value"] == 1, str(m["gng_opened"]))
    check("hitl: decisions by type", m["decisions"]["value"] == {"approve": 1, "deny": 1})
    check("hitl: time-to-decision from the FIRST opened event",
          m["time_to_decision_h"]["max"] > 400 and m["time_to_decision_h"]["n"] == 2,
          str(m["time_to_decision_h"]))
    check("hitl: voided GOs counted", m["gos_voided"]["value"] == 1)
    check("hitl: SD citations counted across notes + commits",
          m["sd_citations"]["value"] == {"SD-3": 2, "SD-7": 1}, str(m["sd_citations"]))
    check("hitl: operator questions are a LOWER BOUND",
          m["operator_questions"]["value"] == 1 and m["operator_questions"]["coverage"] == "lower-bound")
    m = R.hitl_metrics(issues, [], [], [], [], (R.SD_EPOCH - timedelta(days=14), R.SD_EPOCH - timedelta(days=7)))
    check("hitl: SD citations before the convention existed -> UNMEASURED, not 0",
          unmeasured(m["sd_citations"]), str(m["sd_citations"]))
    check("hitl: no decisions -> time-to-decision unmeasured", unmeasured(m["time_to_decision_h"]))
    check("hitl: no window runs -> operator questions unmeasured", unmeasured(m["operator_questions"]))
    m = R.hitl_metrics(issues, [], [(t(1), "no tokens here")], [], [], CUR)
    check("hitl: SD convention live, notes read, none cited -> measured 0",
          m["sd_citations"]["measured"] and m["sd_citations"]["total"] == 0)


def test_cron():
    m = R.cron_metrics(None, None, None, CUR)
    check("cron: unreadable -> unmeasured", unmeasured(m["totals"]) and unmeasured(m["per_job"]))
    jobs = {"j1": "sweep", "j2": "tick"}
    ms = lambda d: int(t(d).timestamp() * 1000)  # noqa: E731
    runs = [{"job_id": "j1", "run_at_ms": ms(1), "status": "error",
             "error": "command exited with code 13", "exit_code": 13},
            {"job_id": "j1", "run_at_ms": ms(3), "status": "ok", "error": None, "exit_code": 0},
            {"job_id": "j2", "run_at_ms": ms(2), "status": "error", "error": "boom", "exit_code": 1},
            {"job_id": "j2", "run_at_ms": ms(10), "status": "error", "error": "old", "exit_code": 4}]
    m = R.cron_metrics(jobs, runs, ms(30), CUR)
    pj = m["per_job"]["value"]
    check("cron: refusal exit 13 attributed to the job", pj["sweep"]["refusals"] == {"13": 1}, str(pj))
    check("cron: non-refusal error is an error, not a refusal",
          pj["tick"]["error"] == 1 and pj["tick"]["refusals"] == {})
    check("cron: totals only cover the period", m["totals"]["value"]["refusals"] == 1
          and m["totals"]["value"]["error"] == 2)
    m = R.cron_metrics(jobs, [], ms(30), CUR)
    check("cron: retained log, no runs in period -> measured 0", zero(R.M(m["totals"]["value"]["ok"], "x")))
    m = R.cron_metrics(jobs, runs, ms(2), CUR)
    check("cron: retention starts mid-period -> partial coverage", m["totals"].get("coverage") == "partial")
    m = R.cron_metrics(jobs, runs, ms(1), PREV)
    check("cron: retention after the period -> UNMEASURED", unmeasured(m["totals"]))


def test_sweep():
    m = R.sweep_metrics(None, {"verified": False}, CUR)
    check("sweep: unreadable ledger / unverified liveness -> unmeasured",
          unmeasured(m["cycles_by_trigger"]) and unmeasured(m["missed_sweeps"]))
    m = R.sweep_metrics([(t(1), "cron", "yellow"), (t(9), "manual", "red")],
                        {"verified": True, "missing_count": 0, "missing": []}, CUR)
    check("sweep: cycles by trigger in period", m["cycles_by_trigger"]["value"] == {"cron": 1})
    check("sweep: verified liveness with no misses -> measured 0", zero(m["missed_sweeps"]))


def test_findings():
    m = R.findings_metrics(None, CUR, NOW, True)
    check("findings: unreadable -> all unmeasured", all(unmeasured(v) for v in m.values()))
    rows = [("F-1", "health", "warning", "x", "new", t(20), None),
            ("F-2", "security", "accepted", "[AR-001] y", "unchanged", t(30), None),
            ("F-3", "health", "warning", "z", "resolved", t(3), t(1)),
            ("F-4", "doc", "warning", "w", "new", t(2), None)]
    m = R.findings_metrics(rows, CUR, NOW, True)
    check("findings: opened/closed in period", m["opened"]["value"] == 2 and m["closed"]["value"] == 1)
    check("findings: net = opened - closed", m["net"]["value"] == 1)
    check("findings: open at end excludes the resolved one", m["open_at_end"]["value"] == 3)
    check("findings: oldest actionable skips AR rows",
          [x["id"] for x in m["oldest_actionable"]["value"]] == ["F-1", "F-4"])
    m = R.findings_metrics(rows, PREV, NOW, False)
    check("findings: open-at-end reconstructed for the previous week (F-3 not yet open)",
          m["open_at_end"]["value"] == 2, str(m["open_at_end"]))
    check("findings: oldest actionable is current-only", unmeasured(m["oldest_actionable"]))
    m = R.findings_metrics([], CUR, NOW, True)
    check("findings: empty readable table -> measured zeros", zero(m["opened"]) and zero(m["net"]))


def test_git():
    m = R.git_metrics(None, CUR)
    check("git: unreadable -> unmeasured", all(unmeasured(v) for v in m.values()))
    c = [(t(1, 5), "feat: x"), (t(1, 5), 'Revert "feat: y"'), (t(1, 5), "fix: revert 5bdd3164 cleanly"),
         (t(2, 9), "docs"), (t(10), "old")]
    m = R.git_metrics(c, CUR)
    check("git: commits in period", m["commits"]["value"] == 4)
    check("git: peak per hour", m["peak_per_hour"]["value"] == 3)
    check("git: reverts matched by subject", m["reverts"]["value"] == 2, str(m["reverts"]))
    m = R.git_metrics([], CUR)
    check("git: no commits -> measured 0", zero(m["commits"]) and zero(m["peak_per_hour"]))


def test_alerts():
    m = R.alert_metrics(None, None, CUR, NOW, None)
    check("alerts: unreachable -> unmeasured", unmeasured(m["paging_series"]) and unmeasured(m["silences_created"]))
    floor = (NOW - timedelta(days=8)).timestamp() * 1000
    m = R.alert_metrics({"total": 0, "top": {}}, [], CUR, NOW, floor)
    check("alerts: covered period, nothing fired -> measured 0", zero(m["paging_series"]))
    check("alerts: silences in the retained horizon are a lower bound",
          m["silences_created"]["coverage"] == "lower-bound" and zero(m["silences_created"]))
    m = R.alert_metrics({"total": 5, "top": {}}, [], PREV, NOW, floor)
    check("alerts: Prometheus retention after period start -> UNMEASURED, not the partial count",
          unmeasured(m["paging_series"]))
    check("alerts: silences older than AM GC horizon -> UNMEASURED", unmeasured(m["silences_created"]))


def test_velocity():
    check("velocity backlog: coverage failed -> unmeasured", unmeasured(R.velocity_backlog(None, None, True)))
    check("velocity backlog: previous week without a stored snapshot -> UNMEASURED, not 0",
          unmeasured(R.velocity_backlog({"counts": {}}, None, False)))
    cov = {"counts": {"AUTO": 2, "PLAN": 30, "REBUILD": 3, "HELD": 4, "CRACK": 0},
           "needs_plan": [{}], "max_rule_fallback": [{"status": "hold"}, {"status": "candidate"}]}
    m = R.velocity_backlog(cov, {"measured": True, "pending": 30}, True)
    check("velocity backlog: pending = AUTO+PLAN+REBUILD+CRACK, growth flagged",
          m["pending"] == 35 and m["grew"] is True and m["delta"] == 5
          and m["value"]["max_rule_holds"] == 1, str(m))
    m = R.velocity_backlog({"counts": {}}, None, True)
    check("velocity backlog: empty lanes -> measured pending 0", m["measured"] and m["pending"] == 0)
    check("classify_bump: renovate author -> auto", R.classify_bump("feat(container): update x ( 1 → 2 )",
                                                                    "renovate[bot]") == "auto")
    check("classify_bump: plan-tagged -> plan", R.classify_bump("chore(x): 1 -> 2 (plan x-2)") == "plan")
    check("classify_bump: Step 0 direct-bump -> auto",
          R.classify_bump("chore(c): 1 -> 2 (window Step 0 direct-bump)") == "auto")
    check("classify_bump: bare bump -> operator", R.classify_bump("feat(x): 1 -> 2") == "operator")
    check("classify_bump: plan/doc commits are not bumps",
          R.classify_bump("plan(x): draft 1 -> 2") is None and R.classify_bump("Revert \"feat: 1 -> 2\"") is None)
    # F-5ca8a134: machine-landed bumps must not read as operator work.
    check("classify_bump: fluxcdbot weekly rebuild (no arrow) -> auto",
          R.classify_bump("chore(showcase): update container images (weekly rebuild)", "fluxcdbot") == "auto")
    check("classify_bump: image-automation subject without bot author -> auto",
          R.classify_bump("chore(gas-price-monitor): update container image (weekly rebuild)", "x") == "auto")
    check("classify_bump: nightly-window direct-bump -> auto",
          R.classify_bump("chore(anythingllm): 1.16.1 -> 1.16.2 (nightly window direct-bump)") == "auto")
    check("classify_bump: sun-attended window-landed -> auto",
          R.classify_bump("chore(x): 1.0 -> 1.1 (sun-attended 2026-09-27)") == "auto")
    check("classify_bump: self-built rebuild roll -> auto",
          R.classify_bump("fix(ai-sre): roll image 2.1.4 -> 2.1.5") == "auto"
          and R.classify_bump("fix(rainbow-rescue): image 0.1.2 -> 0.1.3 (refreshed alpine packages)") == "auto")
    check("classify_bump: security_ref trailer in body -> auto",
          R.classify_bump("fix(arag-web): image sha-2873ce3 -> sha-e8d9f51", "Mathias Uhl",
                          "Rebuilt on a fresh base.\n\nsecurity_ref: F-89c74756\n") == "auto")
    check("classify_bump: security_ref mentioned mid-line is NOT the trailer",
          R.classify_bump("feat(x): 1 -> 2", "", "see security_ref: F-89c74756 elsewhere") == "operator")
    check("classify_bump: plan tag still wins over a window marker",
          R.classify_bump("feat(makemkv): v1 -> v2 (plan makemkv-v2, nightly 2026-09-28)") == "plan")
    check("classify_bump: self-built FEATURE bump stays operator",
          R.classify_bump("feat(solarfocus-scraper): sha-5f31bd6 -> sha-357aa5f -- restore the dropped decimal") == "operator")
    check("classify_bump: bot author on a docs commit is still not a bump",
          R.classify_bump("docs(x): note 1 -> 2", "renovate[bot]") is None)
    check("classify_bump: 'enrolled'/'controller' do not match the roll marker",
          R.classify_bump("feat(authentik): enrolled users 1 -> 2 via controller") == "operator")
    m = R.velocity_share([(t(1), "chore(s): update container images (weekly rebuild)", "fluxcdbot", ""),
                          (t(1), "fix(a): image sha-1 -> sha-2", "Mathias Uhl", "security_ref: F-0123abcd"),
                          (t(1), "feat(b): 1 -> 2", "Mathias Uhl")], CUR)
    check("velocity share: bot rebuild + security-lane roll auto, bare bump operator (3-tuple still accepted)",
          m["value"] == {"auto": 2, "operator": 1} and m["auto_pct"] == 67, str(m))
    check("velocity share: no commits readable -> unmeasured", unmeasured(R.velocity_share(None, CUR)))
    m = R.velocity_lead_time([{"ts": t(1), "published": t(4)}, {"ts": t(2), "published": None}], CUR)
    check("lead time: publish->landed days, unresolved flagged partial",
          m["value"] == 3.0 and m["coverage"] == "partial" and m["unresolved"] == 1, str(m))
    check("lead time: no bumps -> UNMEASURED, not 0 days", unmeasured(R.velocity_lead_time([], CUR)))
    rows = [("F-1", "warning", "`img:1`: 8 fixable HIGH CVE(s) — newer upstream tag available — <id>",
             "new", t(20), None, "medium"),
            ("F-2", "warning", "`img:2`: 1 CRITICAL + 0 HIGH fixable CVE(s) — no newer upstream tag because we publish it",
             "new", t(5), None, "high"),
            ("F-3", "accepted", "[AR-001] `img:3`: 2 fixable HIGH CVE(s)", "unchanged", t(30), None, "low"),
            ("F-4", "warning", "`img:4`: 3 fixable CRITICAL CVE(s) — newer upstream tag available", "resolved",
             t(10), t(2), "high")]
    m = R.security_velocity(rows, CUR, True)
    o = m["open_fixable_high_crit"]
    check("security: open fixable HIGH/CRIT excludes AR + resolved, reads both title forms",
          o["value"] == 2 and o["by_trivy"] == {"HIGH": 1, "CRITICAL": 1}, str(o))
    check("security: 'newer upstream tag available' is recognised (silent-0 regression 2026-09-27)",
          o["newer_tag_available"] == 1, str(o))
    check("security: detect->fixed from first_seen to resolved_at", m["detect_to_fixed_days"]["value"] == 8.0,
          str(m["detect_to_fixed_days"]))
    m = R.security_velocity(None, CUR, True)
    check("security: unreadable -> unmeasured", all(unmeasured(v) for v in m.values()))
    check("security: no fix in period -> detect->fixed UNMEASURED",
          unmeasured(R.security_velocity(rows[:1], CUR, True)["detect_to_fixed_days"]))
    check("renovate: gh failed -> unmeasured", unmeasured(R.renovate_intake(None, CUR)))
    m = R.renovate_intake([{"createdAt": t(3).isoformat(), "mergedAt": t(1).isoformat(), "state": "MERGED"},
                           {"createdAt": t(9).isoformat(), "mergedAt": None, "state": "OPEN"}], CUR)
    check("renovate: intake/merged/open counted per period",
          m["value"] == 1 and m["merged"] == 1 and m["open_now"] == 1, str(m))
    check("earned lane: absent from coverage -> UNMEASURED, not 0",
          unmeasured(R.earned_lane({"lanes": {"PLAN": [{"reason": "plan exists"}]}}, None, CUR)))
    check("bump_refs: repository + tag pair and inline image refs",
          R.bump_refs("@@\n   repository: ghcr.io/a/b\n-  tag: 1.0\n+  tag: 1.1\n"
                      "@@\n+    image: docker.io/x/y:2.0@sha256:ab\n")
          == [("docker.io/x/y", "2.0"), ("ghcr.io/a/b", "1.1")])
    check("redact: advisory ids never leave the script",
          "CVE-2026" not in R.redact("x CVE-2026-12345 y GHSA-abcd-efgh-ijkl SUSE-SU-2026:2673-1")
          and "GHSA" not in R.redact("GHSA-abcd-efgh-ijkl") and "SUSE-SU" not in R.redact("SUSE-SU-2026:2673-1"))


def main():
    print("test-ops-retro")
    for fn in (test_constructors_and_render, test_windows, test_plans, test_hitl, test_cron,
               test_sweep, test_findings, test_git, test_alerts, test_velocity):
        fn()
    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} -> {', '.join(FAILURES)}")
        return 1
    print("all ops-retro tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
