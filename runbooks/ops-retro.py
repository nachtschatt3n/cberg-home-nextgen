#!/usr/bin/env python3
"""ops-retro.py — the weekly operations-efficiency retro, measured.

Operator request 2026-09-27: "every week we do a retro about the efficiency of
the operation". The first retro (that day) was done by hand and produced the
standing decisions SD-1..SD-9 (.claude/agents/maintenance-window-agent.md).
This script is the measuring half of the weekly repeat; the judging half is
runbooks/ops-retro.md, which a Claude session in the ops console follows after
running this.

It compares the LAST 7 DAYS with the 7 DAYS BEFORE across:

  windows      expected / run / missed occurrences (maintenance-plan.py
               liveness logic), run outcomes, safe updates landed
  plans        plan_executions outcomes, draft->executed queue age,
               go/no-go issues sitting open > 7 days
  hitl         go/no-go issues opened, decisions + time-to-decision, voided
               GOs, supervised vs unsupervised executions, SD-n citations,
               operator questions (lower bound)
  automation   OpenClaw cron runs per job (ok/error, refusal exit codes
               4/8/12/13), sweep cycles by trigger, missed 48h sweeps
  findings     opened / closed / net, open-at-end by section with median age,
               oldest actionable non-AR findings
  git          commits/day, peak commits/hour (etcd-stall lesson F-baf94b64),
               reverts
  alerts       paging alert series (Prometheus ALERTS), silences created
  velocity     HEADLINE (operator 2026-09-27: "the update and security patches
               are not efficient and we are not catching up with the fast
               pace"): update backlog by lane (coverage.py) trended against the
               previous retro's snapshot, patch lead time upstream-publish ->
               landed (median/p90), share landed auto vs plan vs operator,
               open fixable HIGH/CRIT + detection->fixed time, Renovate PR
               intake, earned-autonomy lane usage (when that lane exists)

NEVER A SILENT ZERO. Every metric is either
    {"measured": true,  "value": ..., "source": "..."}
or  {"measured": false, "value": null, "reason": "..."}
and a metric whose source could not be read is `measured: false`, never 0.
Where a source only partially covers a period (retention, a convention that
started mid-period) the metric carries "coverage": "partial"/"lower-bound" and
a note. Each source also reports its own availability under `sources`.

Sources: sweep_history Postgres ($SWEEP_PG_DSN — source
runbooks/lib/sweep-pg-dsn.sh and call sweep_pg_dsn_up first), the OpenClaw pod
(home-operation sqlite + OpenClaw cron_run_logs, one read-only kubectl exec),
git, and Prometheus/Alertmanager through the API-server service proxy.

Exit: 0 all sources read; 2 at least one source failed (JSON + markdown are
still emitted, with the failed metrics unmeasured); 1 internal error.

Usage:
    source runbooks/lib/sweep-pg-dsn.sh && sweep_pg_dsn_up
    .venv/bin/python3 runbooks/ops-retro.py                 # markdown to stdout
    .venv/bin/python3 runbooks/ops-retro.py --json          # JSON to stdout
    .venv/bin/python3 runbooks/ops-retro.py --json-out r.json --md-out r.md
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import statistics
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parent
PERIOD_DAYS = 7

# Convention epochs: a metric that counts a token cannot count it before the
# token existed. Before the epoch the metric is UNMEASURED, not zero.
SD_EPOCH = datetime(2026, 9, 27, tzinfo=timezone.utc)          # d06fbaa9, SD-1..SD-9
REFUSAL_EXIT_CODES = (4, 8, 12, 13)
REFUSAL_MEANING = {4: "console unreachable/exhausted", 8: "pane busy (window)",
                   12: "delivered, never started", 13: "pane busy (operation)"}
PAGING_SEVERITIES = "critical|warning"      # routed to Telegram; info -> null receiver
AM_SILENCE_RETENTION_H = 120                 # Alertmanager default GC of expired silences
PROM = "/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy"
AM = "/api/v1/namespaces/monitoring/services/kube-prometheus-stack-alertmanager:9093/proxy"
OPEN_STATUSES = ("new", "unchanged")
ACTIONABLE_SEVERITIES = ("critical", "warning")
SD_RE = re.compile(r"\bSD-\d+\b")
QUESTION_RE = re.compile(r"AskUserQuestion|operator[- ]question|asked the operator", re.I)
REVERT_RE = re.compile(r"(?i)^revert\b|\brevert(?:s|ed)?\s+[0-9a-f]{7,40}\b")
# Vulnerability identifiers never leave this script (public-repo rule,
# docs/sops/vulnerability-disclosure.md) — titles are redacted before output.
ADVISORY_RE = re.compile(r"\b(?:CVE-\d{4}-\d+|GHSA(?:-[0-9a-z]{4}){3}|[A-Z]+-SU-[\d:-]*\d|DSA-\d+[\d-]*|"
                         r"ALSA-[\d:-]+|RHSA-[\d:-]+|USN-[\d-]+)\b")
BUMP_RE = re.compile(r"(?:->|→)")
AUTO_BUMP_RE = re.compile(r"(?i)step 0|direct-bump|auto-update|\(#\d+\)\s*$")
# F-5ca8a134 (ops-retro 2026-W40): the week read auto=5 against 13 safe updates
# landed, because three kinds of machine-landed bump fell through to "operator"
# (or were not counted at all):
#   * bot authors other than Renovate -- Flux image automation commits as
#     `fluxcdbot`, and its subject ("update container images (weekly rebuild)")
#     carries no arrow, so it was not even recognised as a bump;
#   * window/agent-landed bumps whose subject names the window rather than
#     "Step 0" ("(nightly window direct-bump)", "(sun-attended ...)", headless);
#   * self-built REBUILD-lane rolls ("roll image", "OS-fresh rebuilds",
#     "refreshed alpine packages") and any bump whose commit body carries the
#     sweep's `security_ref: F-...` -- the security lane chose the target, an
#     agent landed it; no operator decision was involved.
# A feature bump of a self-built app ("sha-a -> sha-b -- restore the dropped
# decimal") has none of these markers and stays "operator".
BOT_AUTHOR_RE = re.compile(r"(?i)\[bot\]|renovate|fluxcdbot|github-actions|dependabot")
IMAGE_AUTOMATION_RE = re.compile(r"(?i)\bupdate container images?\b|weekly rebuild|image automation")
WINDOW_BUMP_RE = re.compile(r"(?i)\b(?:nightly|sat-attended|sun-attended|maintenance) window\b|"
                            r"\((?:nightly|sat-attended|sun-attended)\b|\bheadless\b")
REBUILD_ROLL_RE = re.compile(r"(?i)\broll(?:s|ed)?\b|\brebuil(?:d|ds|t)\b|\brefreshed\b|os-fresh")
SECURITY_REF_BODY_RE = re.compile(r"(?m)^security_ref:\s*F-[0-9a-f]{8}\b")
PLAN_BUMP_RE = re.compile(r"(?i)\(plan [\w.-]+|plan [\w.-]+\)")
LANES = ("AUTO", "PLAN", "REBUILD", "HELD", "CRACK")
STATE_DIR = Path(os.path.expanduser(os.environ.get("OPS_RETRO_STATE_DIR", "~/.local/state/ops-retro")))


def redact(text):
    return ADVISORY_RE.sub("<advisory>", text or "")


# ---- metric constructors ----------------------------------------------------
def M(value, source, **extra):
    """A measured metric."""
    return {"measured": True, "value": value, "source": source, **extra}


def U(reason):
    """An unmeasured metric. Never rendered or summed as 0."""
    return {"measured": False, "value": None, "reason": reason}


def _median(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 1) if xs else None


def _p90(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    return round(xs[min(len(xs) - 1, int(round(0.9 * (len(xs) - 1))))], 1)


def _as_utc(ts):
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if isinstance(ts, datetime) and ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc) if isinstance(ts, datetime) else ts


def periods(now):
    """{'current': (start, end), 'previous': (start, end)} — half-open, UTC."""
    d = timedelta(days=PERIOD_DAYS)
    return {"current": (now - d, now), "previous": (now - 2 * d, now - d)}


def _in(ts, span):
    ts = _as_utc(ts)
    return ts is not None and span[0] <= ts < span[1]


# ---- maintenance-plan.py (liveness logic is REUSED, not re-derived) --------
def _load_mp():
    spec = importlib.util.spec_from_file_location("mp_for_retro", SCRIPT_DIR / "maintenance-plan.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ============================================================================
# Pure metric functions (unit-tested in runbooks/tests/test-ops-retro.py).
# Each takes already-fetched rows (or None = source unavailable) and a span.
# ============================================================================
def window_metrics(mp, cfg, run_rows, end_day, span):
    """run_rows: (slot, run_date, started_at, finished_at, outcome, trigger,
    safe_updates[, notes]) or None — notes feeds the explicit
    `absorbs <slot>:<date>` coverage (attended_absorbed_by_on_demand). end_day: the Berlin date the period ends on —
    expected slots are the fully-past days (end_day-7 .. end_day-1)."""
    if run_rows is None:
        why = "window_runs unreadable (sweep_history Postgres)"
        return {k: U(why) for k in ("expected", "run", "missed", "missed_slots",
                                    "outcomes", "safe_updates")}
    expected = mp.expected_slots(cfg, end_day, lookback_days=PERIOD_DAYS)
    base = [r[:6] for r in run_rows]
    od = (mp.on_demand_slot(cfg) or {}).get("id", "now")
    covered = (mp.nightly_covered_by_on_demand(base, on_demand_id=od)
               # notes is column 7 of this query (after safe_updates)
               + mp.attended_absorbed_by_on_demand(run_rows, on_demand_id=od, notes_index=7))
    missing = mp.missing_window_runs(expected, mp.completed_run_rows(base), covered)
    in_span = [r for r in run_rows if _in(r[2], span)]
    outcomes = Counter(str(r[4]) for r in in_span)
    su = [r[6] for r in in_span]
    src = "window_runs + maintenance-plan.py expected_slots/missing_window_runs"
    if not expected and cfg.get("windows"):
        exp_m = U(f"period predates the window_runs epoch {mp.WINDOW_LIVENESS_EPOCH}")
        run_m = missed_m = slots_m = exp_m
    else:
        exp_m = M(len(expected), src)
        run_m = M(len(expected) - len(missing), src)
        missed_m = M(len(missing), src)
        slots_m = M(missing, src)
    if any(v is None for v in su):
        safe = M(sum(v for v in su if v is not None), "window_runs.safe_updates",
                 coverage="lower-bound",
                 note=f"{sum(v is None for v in su)} run row(s) recorded no safe_updates figure")
    else:
        safe = M(sum(su), "window_runs.safe_updates")
    return {"expected": exp_m, "run": run_m, "missed": missed_m, "missed_slots": slots_m,
            "outcomes": M(dict(outcomes), "window_runs.outcome (rows started in period, incl. ad-hoc/now)",
                          runs=len(in_span)),
            "safe_updates": safe}


def plan_metrics(exec_rows, draft_dates, open_gng, span, now):
    """exec_rows: (plan_id, outcome, supervised, recorded_at) or None.
    draft_dates: {plan_id: datetime the plan file was first committed} or None.
    open_gng: [(key, first_opened_ts)] open go/no-go issues, or None."""
    out = {}
    if exec_rows is None:
        why = "plan_executions unreadable (sweep_history Postgres)"
        out.update(outcomes=U(why), supervised=U(why), unsupervised=U(why),
                   queue_age_days_median=U(why))
    else:
        rows = [r for r in exec_rows if _in(r[3], span)]
        out["outcomes"] = M(dict(Counter(str(r[1]) for r in rows)), "plan_executions.outcome",
                            total=len(rows))
        out["supervised"] = M(sum(1 for r in rows if r[2] is True), "plan_executions.supervised")
        out["unsupervised"] = M(sum(1 for r in rows if r[2] is False), "plan_executions.supervised")
        if draft_dates is None:
            out["queue_age_days_median"] = U("git history for plan files unreadable")
        else:
            green = [r for r in rows if str(r[1]) == "green"]
            ages, unknown = [], []
            for r in green:
                d0 = draft_dates.get(r[0])
                if d0 is None:
                    unknown.append(r[0])
                else:
                    ages.append((_as_utc(r[3]) - _as_utc(d0)).total_seconds() / 86400)
            if not green:
                out["queue_age_days_median"] = U("no plan executed green in the period")
            elif not ages:
                out["queue_age_days_median"] = U(f"no git add date found for any of {len(green)} plan(s)")
            else:
                out["queue_age_days_median"] = M(
                    _median(ages), "git first-add of runbooks/maintenance/plans/<id>.md -> plan_executions.recorded_at",
                    n=len(ages), max=round(max(ages), 1),
                    **({"coverage": "partial", "unknown_plans": unknown} if unknown else {}))
    if open_gng is None:
        out["awaiting_go_over_7d"] = U("home-operation store unreadable")
    elif span[1] < now - timedelta(hours=1):
        out["awaiting_go_over_7d"] = U("point-in-time: only measurable for the current period")
    else:
        stale = sorted(((k, round((now - _as_utc(t)).total_seconds() / 86400, 1))
                        for k, t in open_gng if t and _as_utc(t) < now - timedelta(days=7)),
                       key=lambda x: -x[1])
        out["awaiting_go_over_7d"] = M(len(stale), "home-operation open go_no_go issues, first 'opened' event",
                                       items=stale[:10])
    return out


def hitl_metrics(issues, events, window_notes, exec_notes, commit_msgs, span):
    """issues: {key: kind}; events: [(key, ts, kind, detail)] or None.
    window_notes / exec_notes: [(ts, text)] or None; commit_msgs: [(ts, text)] or None."""
    out = {}
    if events is None or issues is None:
        why = "home-operation store unreadable"
        out.update(gng_opened=U(why), decisions=U(why), time_to_decision_h=U(why), gos_voided=U(why))
    else:
        first_open = {}
        for k, ts, kind, _ in sorted(events, key=lambda e: _as_utc(e[1])):
            if kind == "opened" and k not in first_open:
                first_open[k] = _as_utc(ts)
        gng = {k for k, kd in issues.items() if kd == "go_no_go"}
        out["gng_opened"] = M(sum(1 for k in gng if k in first_open and _in(first_open[k], span)),
                              "home-operation events: first 'opened' of go_no_go issues")
        dec = [(k, _as_utc(ts), (d or "").split()[0] if d else "") for k, ts, kind, d in events
               if kind == "decided" and _in(ts, span)]
        out["decisions"] = M(dict(Counter(d for _, _, d in dec)), "home-operation events kind=decided",
                             total=len(dec))
        waits = [(t - first_open[k]).total_seconds() / 3600 for k, t, _ in dec
                 if k in first_open and first_open[k] <= t]
        if not dec:
            out["time_to_decision_h"] = U("no decisions in the period")
        elif not waits:
            out["time_to_decision_h"] = U(f"{len(dec)} decision(s) but none has an 'opened' event to measure from")
        else:
            out["time_to_decision_h"] = M(_median(waits), "decided ts - first opened ts",
                                          n=len(waits), max=round(max(waits), 1),
                                          **({"coverage": "partial"} if len(waits) < len(dec) else {}))
        out["gos_voided"] = M(sum(1 for _, ts, kind, _ in events if kind == "expired" and _in(ts, span)),
                              "home-operation events kind=expired (GO voided, window passed)")
    # SD-n citations — the convention began at SD_EPOCH.
    if span[1] <= SD_EPOCH:
        out["sd_citations"] = U(f"period ends before the SD convention existed ({SD_EPOCH.date()})")
    elif window_notes is None and exec_notes is None and commit_msgs is None:
        out["sd_citations"] = U("no evidence source readable")
    else:
        c = Counter()
        for src in (window_notes or [], exec_notes or [], commit_msgs or []):
            for ts, text in src:
                if _in(ts, span):
                    c.update(SD_RE.findall(text or ""))
        extra = {}
        if span[0] < SD_EPOCH:
            extra = {"coverage": "partial", "note": f"convention effective {SD_EPOCH.date()}"}
        missing = [n for n, s in (("window_runs", window_notes), ("plan_executions", exec_notes),
                                  ("git", commit_msgs)) if s is None]
        if missing:
            extra.update(coverage="lower-bound", unread=missing)
        out["sd_citations"] = M(dict(c), "SD-n tokens in window_runs notes, plan_executions notes, commit messages",
                                total=sum(c.values()), **extra)
    if window_notes is None:
        out["operator_questions"] = U("window_runs notes unreadable")
    else:
        runs = [(ts, t) for ts, t in window_notes if _in(ts, span)]
        if not runs:
            out["operator_questions"] = U("no window runs in the period")
        else:
            n = sum(len(QUESTION_RE.findall(t or "")) for _, t in runs)
            out["operator_questions"] = M(n, "window_runs notes (AskUserQuestion / operator question mentions)",
                                          coverage="lower-bound", runs=len(runs),
                                          per_run=round(n / len(runs), 2),
                                          note="no structured question record exists; see ops-retro.md")
    return out


def _exit_code(run):
    m = re.search(r"exited with code (\d+)", run.get("error") or "")
    if m:
        return int(m.group(1))
    return run.get("exit_code")


def cron_metrics(jobs, runs, oldest_ms, span):
    """jobs: {job_id: name}; runs: [{job_id, run_at_ms, status, error, exit_code}]
    or None; oldest_ms: the oldest retained cron_run_logs row (retention control)."""
    if runs is None or jobs is None:
        return {"per_job": U("OpenClaw cron_run_logs unreadable"), "totals": U("OpenClaw cron_run_logs unreadable")}
    if oldest_ms is None or _as_utc(oldest_ms) > span[0]:
        cov = {"coverage": "partial",
               "note": f"cron_run_logs retained only since {_as_utc(oldest_ms)}" if oldest_ms else "no runs retained"}
        if oldest_ms is None or _as_utc(oldest_ms) >= span[1]:
            why = "cron_run_logs retention does not reach this period"
            return {"per_job": U(why), "totals": U(why)}
    else:
        cov = {}
    per = defaultdict(lambda: {"ok": 0, "error": 0, "other": 0, "refusals": {}, "exit_codes": {}})
    for r in runs:
        if not _in(r["run_at_ms"], span):
            continue
        j = per[jobs.get(r["job_id"], r["job_id"][:8])]
        st = r.get("status")
        j[st if st in ("ok", "error") else "other"] += 1
        code = _exit_code(r)
        if st == "error" and code is not None:
            j["exit_codes"][str(code)] = j["exit_codes"].get(str(code), 0) + 1
            if code in REFUSAL_EXIT_CODES:
                j["refusals"][str(code)] = j["refusals"].get(str(code), 0) + 1
    per = dict(sorted(per.items()))
    tot = {"ok": sum(v["ok"] for v in per.values()), "error": sum(v["error"] for v in per.values()),
           "refusals": sum(sum(v["refusals"].values()) for v in per.values()),
           "jobs_with_errors": sorted(k for k, v in per.items() if v["error"])}
    return {"per_job": M(per, "openclaw.sqlite cron_run_logs", **cov),
            "totals": M(tot, "openclaw.sqlite cron_run_logs", **cov)}


def sweep_metrics(cycles, liveness, span):
    """cycles: [(started_at, trigger, verdict)] or None; liveness: the dict from
    maintenance-plan.sweep_cron_liveness_report for this span."""
    out = {}
    if cycles is None:
        out["cycles_by_trigger"] = U("sweep_cycles unreadable")
    else:
        rows = [c for c in cycles if _in(c[0], span)]
        out["cycles_by_trigger"] = M(dict(Counter(str(c[1]) for c in rows)), "sweep_cycles.trigger",
                                     total=len(rows),
                                     verdicts=dict(Counter(str(c[2]) for c in rows)))
    if not liveness or not liveness.get("verified"):
        out["missed_sweeps"] = U("sweep-cron liveness not verified (sweep_cycles unreadable)")
    else:
        out["missed_sweeps"] = M(liveness.get("missing_count"),
                                 "maintenance-plan.sweep_cron_liveness_report",
                                 missing=liveness.get("missing", []))
    return out


def findings_metrics(rows, span, now, is_current):
    """rows: (finding_id, section, severity, title, status, first_seen, resolved_at) or None."""
    if rows is None:
        why = "sweep_findings unreadable"
        return {k: U(why) for k in ("opened", "closed", "net", "open_at_end", "median_age_days_by_section",
                                    "oldest_actionable")}
    opened = [r for r in rows if _in(r[5], span)]
    closed = [r for r in rows if _in(r[6], span)]
    t = span[1]

    def open_at(r):
        fs, ra = _as_utc(r[5]), _as_utc(r[6])
        if fs is None or fs >= t:
            return False
        if ra is not None:
            return ra >= t
        return r[4] in OPEN_STATUSES      # resolved without a timestamp = not open
    live = [r for r in rows if open_at(r)]
    by_sec = defaultdict(list)
    for r in live:
        by_sec[r[1]].append((t - _as_utc(r[5])).total_seconds() / 86400)
    src = "sweep_findings first_seen/resolved_at"
    out = {"opened": M(len(opened), src, by_section=dict(Counter(r[1] for r in opened))),
           "closed": M(len(closed), src, by_section=dict(Counter(r[1] for r in closed))),
           "net": M(len(opened) - len(closed), src),
           "open_at_end": M(len(live), src + " (reconstructed at period end)",
                            ar_accepted=sum(1 for r in live if _is_ar(r)),
                            by_section={k: len(v) for k, v in sorted(by_sec.items())}),
           "median_age_days_by_section": M({k: _median(v) for k, v in sorted(by_sec.items())}, src)}
    if is_current:
        act = sorted((r for r in live if r[2] in ACTIONABLE_SEVERITIES and not _is_ar(r)),
                     key=lambda r: _as_utc(r[5]))[:5]
        out["oldest_actionable"] = M([{"id": r[0], "section": r[1], "severity": r[2],
                                       "age_days": round((now - _as_utc(r[5])).total_seconds() / 86400, 1),
                                       "title": redact(r[3])[:110]} for r in act],
                                     src + "; severity critical|warning, not AR-accepted")
    else:
        out["oldest_actionable"] = U("point-in-time: only listed for the current period")
    return out


def _is_ar(r):
    return r[2] == "accepted" or (r[3] or "").lstrip().startswith("[AR-")


def git_metrics(commits, span):
    """commits: [(datetime, subject)] or None."""
    if commits is None:
        why = "git log unreadable"
        return {k: U(why) for k in ("commits", "per_day", "peak_per_hour", "reverts")}
    rows = [(_as_utc(t), s) for t, s in commits if _in(t, span)]
    per_day = Counter(t.date().isoformat() for t, _ in rows)
    per_hour = Counter(t.strftime("%Y-%m-%dT%H:00Z") for t, _ in rows)
    peak = per_hour.most_common(1)[0] if per_hour else (None, 0)
    reverts = [s for _, s in rows if REVERT_RE.search(s or "")]
    return {"commits": M(len(rows), "git log (committer date)"),
            "per_day": M(dict(sorted(per_day.items())), "git log",
                         max=max(per_day.values()) if per_day else 0),
            "peak_per_hour": M(peak[1], "git log", hour=peak[0]),
            "reverts": M(len(reverts), "git log subject matches revert", subjects=reverts[:8])}


def alert_metrics(paging, silences, span, now, prom_floor):
    """paging: {'total': int, 'top': {alertname: n}} or None for this span;
    silences: [{'createdBy','startsAt'}] or None; prom_floor: oldest TSDB sample."""
    out = {}
    if paging is None:
        out["paging_series"] = U("Prometheus unreachable via the API-server proxy")
    elif prom_floor is None or _as_utc(prom_floor) > span[0]:
        out["paging_series"] = U(f"Prometheus retention starts {_as_utc(prom_floor) if prom_floor else '?'} "
                                 f"— after the period start")
    else:
        out["paging_series"] = M(paging["total"], f"Prometheus ALERTS{{severity=~'{PAGING_SEVERITIES}'}} series firing in period",
                                 top=paging["top"])
    if silences is None:
        out["silences_created"] = U("Alertmanager unreachable via the API-server proxy")
    else:
        gc_floor = now - timedelta(hours=AM_SILENCE_RETENTION_H)
        if span[1] <= gc_floor:
            out["silences_created"] = U(f"Alertmanager GCs expired silences after ~{AM_SILENCE_RETENTION_H}h; "
                                        f"this period is past that horizon")
        else:
            rows = [s for s in silences if _in(s.get("startsAt"), span)]
            out["silences_created"] = M(len(rows), "Alertmanager /api/v2/silences startsAt",
                                        by_creator=dict(Counter(s.get("createdBy") or "?" for s in rows)),
                                        coverage="lower-bound" if span[0] < gc_floor else "full",
                                        note=f"silences that expired >{AM_SILENCE_RETENTION_H}h ago are GC'd")
    return out


# ---- patch velocity (headline) ----------------------------------------------
def velocity_backlog(cov, prev_snapshot, is_current):
    """cov: coverage.py --json dict (or None); prev_snapshot: the previous
    retro's current.velocity.backlog metric (or None). Point-in-time: only the
    current period is measured live; the previous value comes from the last
    retro's stored snapshot, never re-derived."""
    if not is_current:
        if prev_snapshot and prev_snapshot.get("measured"):
            return dict(prev_snapshot, source="previous retro snapshot (" +
                        str(prev_snapshot.get("snapshot_at", "?")) + ")")
        return U("no previous retro snapshot under " + str(STATE_DIR) +
                 " (the backlog is point-in-time; the trend starts with the 2nd retro)")
    if cov is None:
        return U("coverage.py --json failed")
    counts = {k: int((cov.get("counts") or {}).get(k, 0)) for k in LANES}
    counts["needs_plan"] = len(cov.get("needs_plan") or [])
    counts["plan_drift"] = len(cov.get("plan_drift") or [])
    counts["max_rule_holds"] = sum(1 for x in (cov.get("max_rule_fallback") or [])
                                   if x.get("status") == "hold")
    pending = counts["AUTO"] + counts["PLAN"] + counts["REBUILD"] + counts["CRACK"]
    extra = {}
    if prev_snapshot and prev_snapshot.get("measured"):
        prev = prev_snapshot.get("pending")
        if isinstance(prev, int):
            extra = {"previous_pending": prev, "delta": pending - prev, "grew": pending > prev}
    age = cov.get("snapshot_age_hours")
    if isinstance(age, (int, float)) and age > 36:
        extra["coverage"] = "partial"
        extra["note"] = f"version snapshot is {age:.0f}h old"
    return M(counts, "coverage.py --json (lanes)", pending=pending,
             snapshot_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), **extra)


def classify_bump(subject, author="", body=""):
    """'auto' | 'plan' | 'operator' | None (not a version bump).

    `body` is the commit body; it only ever PROMOTES a bump to auto (the
    security-lane `security_ref:` trailer), never makes a non-bump a bump."""
    s = subject or ""
    if re.match(r"(?i)^(plan|docs|test|revert)\b", s) or s.startswith("Revert"):
        return None
    bot = bool(BOT_AUTHOR_RE.search(author or ""))
    image_automation = bool(IMAGE_AUTOMATION_RE.search(s))
    if not (BUMP_RE.search(s) or re.search(r"(?i)\bupdate .*\(.*\)", s) or image_automation):
        return None
    if bot or image_automation:
        return "auto"
    if PLAN_BUMP_RE.search(s):
        return "plan"
    if (AUTO_BUMP_RE.search(s) or WINDOW_BUMP_RE.search(s) or REBUILD_ROLL_RE.search(s)
            or SECURITY_REF_BODY_RE.search(body or "")):
        return "auto"
    return "operator"


def velocity_share(commits, span):
    """commits: [(ts, subject, author[, body])] or None."""
    if commits is None:
        return U("git log unreadable")
    c = Counter()
    for ts, subj, author, *rest in commits:
        if _in(ts, span):
            k = classify_bump(subj, author, rest[0] if rest else "")
            if k:
                c[k] += 1
    total = sum(c.values())
    if not total:
        return M({}, "git log bump commits", total=0)
    return M(dict(c), "git log bump commits (subject/author classified)", total=total,
             auto_pct=round(100 * c["auto"] / total), coverage="partial",
             note="classified by author, subject and security_ref trailer; a bump with no bot/plan/window/rebuild marker counts as operator")


def velocity_lead_time(bumps, span):
    """bumps: [{'ts', 'published', 'ref'}] or None. Lead = landed - published."""
    if bumps is None:
        return U("bump commit diffs / registry publish dates unreadable")
    rows = [b for b in bumps if _in(b["ts"], span)]
    if not rows:
        return U("no image bump commits in the period")
    days = [(_as_utc(b["ts"]) - _as_utc(b["published"])).total_seconds() / 86400
            for b in rows if b.get("published")]
    if not days:
        return U(f"{len(rows)} bump(s) but no registry publish date resolvable")
    extra = {"coverage": "partial", "unresolved": len(rows) - len(days)} if len(days) < len(rows) else {}
    return M(_median(days), "bump commit time - registry publish time of the new tag",
             n=len(days), p90=_p90(days), max=round(max(days), 1), **extra)


_FIX_A = re.compile(r"fixable (HIGH|CRITICAL)")
_FIX_B = re.compile(r"(\d+) CRITICAL \+ (\d+) HIGH fixable")
# security-check.py wording, verified against live rows 2026-09-27 (the first
# draft matched "update available" and read a silent 0 for 16 rows).
_NEWER_TAG = re.compile(r"(?i)newer upstream tag available|update available|upstream fix available")


def fix_class(title):
    """Pure: 'CRITICAL' | 'HIGH' | None for a security finding title."""
    m = _FIX_A.search(title or "")
    if m:
        return m.group(1)
    m = _FIX_B.search(title or "")
    if m:
        return "CRITICAL" if int(m.group(1)) else ("HIGH" if int(m.group(2)) else None)
    return None


def security_velocity(rows, span, is_current):
    """rows: security sweep_findings (id, severity, title, status, first_seen,
    resolved_at, risk_tier) or None. 'fixable' rows only."""
    if rows is None:
        why = "sweep_findings unreadable"
        return {"open_fixable_high_crit": U(why), "detect_to_fixed_days": U(why)}
    t = span[1]
    fx = [r for r in rows if "fixable" in (r[2] or "")]

    def open_at(r):
        fs, ra = _as_utc(r[4]), _as_utc(r[5])
        return fs is not None and fs < t and (ra >= t if ra else r[3] in OPEN_STATUSES)
    live = [r for r in fx if open_at(r) and fix_class(r[2])
            and not _is_ar((r[0], "security", r[1], r[2]))]
    by_cls = Counter(fix_class(r[2]) for r in live)
    by_tier = Counter(str(r[6] or "unscored") for r in live)
    newer = sum(1 for r in live if _NEWER_TAG.search(r[2] or ""))
    out = {"open_fixable_high_crit": M(len(live), "sweep_findings security 'fixable HIGH|CRITICAL' open at period end",
                                       by_trivy=dict(by_cls), by_contextual_tier=dict(by_tier),
                                       newer_tag_available=newer)}
    fixed = [(_as_utc(r[5]) - _as_utc(r[4])).total_seconds() / 86400 for r in fx
             if _in(r[5], span) and r[4] is not None]
    out["detect_to_fixed_days"] = (M(_median(fixed), "first_seen (newer tag detected) -> resolved_at (fixed tag scanned)",
                                     n=len(fixed), p90=_p90(fixed))
                                   if fixed else U("no fixable security finding resolved in the period"))
    return out


def renovate_intake(prs, span):
    """prs: [{'createdAt','mergedAt','closedAt','state'}] or None."""
    if prs is None:
        return U("gh pr list failed")
    opened = [p for p in prs if _in(p.get("createdAt"), span)]
    merged = [p for p in prs if _in(p.get("mergedAt"), span)]
    waits = [(_as_utc(p["mergedAt"]) - _as_utc(p["createdAt"])).total_seconds() / 86400 for p in merged]
    return M(len(opened), "gh pr list --author app/renovate", merged=len(merged),
             open_to_merge_days_median=_median(waits), open_now=sum(1 for p in prs if p.get("state") == "OPEN"))


def earned_lane(cov, window_notes, span):
    """The earned-autonomy lane is being built (2026-09-27). Measured only once
    coverage.py emits it; until then UNMEASURED — never 0."""
    lane = (cov or {}).get("earned") if cov else None
    if lane is None and cov is not None:
        lanes = cov.get("lanes") or {}
        reasons = [str(x.get("reason", "")) for v in lanes.values() if isinstance(v, list) for x in v]
        hits = Counter(k for r in reasons for k in ("earned", "security", "normal")
                       if re.search(rf"\b{k}\b", r, re.I) and "earned" in r.lower())
        if hits:
            return M(dict(hits), "coverage.py lane reasons mentioning 'earned'")
        return U("earned-autonomy lane not present in coverage.py output yet")
    if lane is None:
        return U("coverage.py --json failed")
    return M(lane, "coverage.py --json 'earned'")


# ============================================================================
# Fetchers — each returns (data, error). data is None on failure.
# ============================================================================
def fetch_pg(dsn, since):
    if not dsn:
        return None, "SWEEP_PG_DSN not set (source runbooks/lib/sweep-pg-dsn.sh; sweep_pg_dsn_up)"
    try:
        import psycopg
        out = {}
        with psycopg.connect(dsn, connect_timeout=10) as c, c.cursor() as cur:
            cur.execute("SELECT slot, run_date::text, started_at, finished_at, outcome, trigger, "
                        "safe_updates, notes FROM window_runs WHERE run_date >= %s",
                        ((since - timedelta(days=2)).date().isoformat(),))
            out["window_runs"] = cur.fetchall()
            cur.execute("SELECT plan_id, outcome, supervised, recorded_at, notes FROM plan_executions "
                        "WHERE recorded_at >= %s", (since,))
            out["plan_executions"] = cur.fetchall()
            cur.execute("SELECT started_at, trigger, verdict FROM sweep_cycles WHERE started_at >= %s", (since,))
            out["sweep_cycles"] = cur.fetchall()
            cur.execute("SELECT finding_id, section, severity, title, status, first_seen, resolved_at "
                        "FROM sweep_findings WHERE status IN ('new','unchanged') "
                        "OR first_seen >= %s OR resolved_at >= %s", (since, since))
            out["sweep_findings"] = cur.fetchall()
            cur.execute("SELECT finding_id, severity, title, status, first_seen, resolved_at, "
                        "metadata->>'risk_tier' FROM sweep_findings WHERE section = 'security' "
                        "AND title LIKE '%%fixable%%' AND (status IN ('new','unchanged') "
                        "OR resolved_at >= %s)", (since,))
            out["security_fixable"] = cur.fetchall()
        return out, None
    except Exception as e:  # noqa: BLE001
        return None, f"sweep_history Postgres: {type(e).__name__}: {str(e)[:200]}"


_POD_READER = r"""
import json, os, sqlite3, sys
since_ms = int(sys.argv[1]); since_iso = sys.argv[2]
out = {}
def ro(p):
    return sqlite3.connect('file:' + p + '?mode=ro', uri=True, timeout=30)
try:
    h = ro(os.path.expanduser('~/clawd/state/home-operation/issues.db'))
    out['issues'] = [list(r) for r in h.execute('SELECT key, kind, status, opened_at FROM issues')]
    out['events'] = [list(r) for r in h.execute(
        "SELECT key, ts, kind, detail FROM events WHERE ts >= ? OR kind = 'opened'", (since_iso,))]
    out['events_oldest'] = h.execute('SELECT min(ts) FROM events').fetchone()[0]
except Exception as e:
    out['home_op_error'] = repr(e)[:300]
try:
    s = ro('/home/node/.openclaw/state/openclaw.sqlite')
    out['jobs'] = {r[0]: r[1] for r in s.execute('SELECT job_id, name FROM cron_jobs')}
    runs = []
    for jid, at, st, err, ej in s.execute(
            'SELECT job_id, run_at_ms, status, error, entry_json FROM cron_run_logs WHERE run_at_ms >= ?',
            (since_ms,)):
        code = None
        try:
            for e in (json.loads(ej or '{}').get('diagnostics') or {}).get('entries') or []:
                if e.get('exitCode') is not None:
                    code = e['exitCode']
        except Exception:
            pass
        runs.append({'job_id': jid, 'run_at_ms': at, 'status': st, 'error': err, 'exit_code': code})
    out['runs'] = runs
    out['runs_oldest_ms'] = s.execute('SELECT min(run_at_ms) FROM cron_run_logs').fetchone()[0]
except Exception as e:
    out['cron_error'] = repr(e)[:300]
print(json.dumps(out))
"""


def fetch_openclaw(since):
    try:
        p = subprocess.run(
            ["kubectl", "-n", "ai", "exec", "-i", "deploy/openclaw", "-c", "app", "--",
             "python3", "-", str(int(since.timestamp() * 1000)), since.strftime("%Y-%m-%dT%H:%M:%SZ")],
            input=_POD_READER, capture_output=True, text=True, timeout=120)
        if p.returncode != 0:
            return None, f"kubectl exec openclaw rc={p.returncode}: {(p.stderr or '').strip()[-200:]}"
        return json.loads(p.stdout.strip().splitlines()[-1]), None
    except Exception as e:  # noqa: BLE001
        return None, f"openclaw pod: {type(e).__name__}: {str(e)[:200]}"


def _git(*args):
    p = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True, timeout=120)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip()[:200])
    return p.stdout


def fetch_git(since):
    try:
        raw = _git("log", f"--since={since.isoformat()}", "--format=%cI%x1f%s%x1f%an%x1f%H%x1f%b%x1e")
        commits, msgs, authored = [], [], []
        for rec in raw.split("\x1e"):
            rec = rec.strip("\n")
            if not rec:
                continue
            ts, subj, author, sha, body = (rec.split("\x1f") + ["", "", "", ""])[:5]
            t = _as_utc(ts)
            commits.append((t, subj))
            msgs.append((t, subj + "\n" + body))
            authored.append((t, subj, author, sha, body))
        return {"commits": commits, "messages": msgs, "authored": authored}, None
    except Exception as e:  # noqa: BLE001
        return None, f"git: {e}"


def fetch_draft_dates(plan_ids):
    """{plan_id: first commit date of its plan file} — None on git failure."""
    out = {}
    try:
        for pid in sorted(set(plan_ids)):
            raw = _git("log", "--diff-filter=A", "--format=%cI", "--",
                       f"runbooks/maintenance/plans/{pid}.md").split()
            if raw:
                out[pid] = _as_utc(raw[-1])
        return out, None
    except Exception as e:  # noqa: BLE001
        return None, f"git plan history: {e}"


_IMG_LINE = re.compile(r"^\+\s*(?:-\s*)?image:\s*[\"']?([\w./-]+):([\w.+-]+)")
_TAG_LINE = re.compile(r"^\+\s*tag:\s*[\"']?([\w.+-]+)")
_REPO_LINE = re.compile(r"^[ +-]\s*repository:\s*[\"']?([\w./-]+)")


def bump_refs(diff_text):
    """Pure: [(image_repo, new_tag)] added by a bump commit's diff."""
    refs, repo = [], None
    for ln in (diff_text or "").splitlines():
        if ln.startswith("@@") or ln.startswith("diff "):
            repo = None
            continue
        m = _REPO_LINE.match(ln)
        if m:
            repo = m.group(1)
            continue
        m = _IMG_LINE.match(ln)
        if m:
            refs.append((m.group(1), m.group(2).split("@")[0]))
            continue
        m = _TAG_LINE.match(ln)
        if m and repo:
            refs.append((repo, m.group(1).split("@")[0]))
    return sorted(set(refs))


def fetch_bumps(authored, max_commits=60):
    """[{'ts','ref','published'}] for image bump commits; None on failure."""
    try:
        spec = importlib.util.spec_from_file_location("cov_for_retro", SCRIPT_DIR / "coverage.py")
        cov = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cov)
        out = []
        for ts, subj, author, sha, *rest in authored:
            if not classify_bump(subj, author, rest[0] if rest else "") or len(out) >= max_commits:
                continue
            refs = bump_refs(_git("show", "--format=", "--unified=6", sha, "--", "*.yaml", "*.yml"))
            if not refs:
                out.append({"ts": ts, "ref": None, "published": None, "subject": subj})
                continue
            repo, tag = refs[0]
            age = cov.image_publish_age_hours(repo, tag)
            pub = (datetime.now(timezone.utc) - timedelta(hours=age)) if isinstance(age, (int, float)) else None
            out.append({"ts": ts, "ref": f"{repo}:{tag}", "published": pub, "subject": subj})
        return out, None
    except Exception as e:  # noqa: BLE001
        return None, f"bump lead-time: {type(e).__name__}: {str(e)[:200]}"


def fetch_coverage():
    try:
        p = subprocess.run([sys.executable, str(SCRIPT_DIR / "coverage.py"), "--json"],
                           capture_output=True, text=True, timeout=240)
        if p.returncode not in (0, 1):
            return None, f"coverage.py rc={p.returncode}: {(p.stderr or '').strip()[-200:]}"
        return json.loads(p.stdout), None
    except Exception as e:  # noqa: BLE001
        return None, f"coverage.py: {type(e).__name__}: {str(e)[:200]}"


def fetch_renovate_prs(since):
    try:
        p = subprocess.run(["gh", "pr", "list", "--author", "app/renovate", "--state", "all",
                            "--search", f"updated:>={since.date().isoformat()}", "--limit", "300",
                            "--json", "number,createdAt,mergedAt,closedAt,state"],
                           capture_output=True, text=True, timeout=60, cwd=str(REPO))
        if p.returncode != 0:
            return None, f"gh: {(p.stderr or '').strip()[-200:]}"
        return json.loads(p.stdout), None
    except Exception as e:  # noqa: BLE001
        return None, f"gh: {type(e).__name__}: {str(e)[:200]}"


def load_prev_snapshot(now, state_dir=None):
    """The newest earlier retro's current.velocity.backlog (>= 3 days old)."""
    best = None
    for f in sorted(Path(state_dir or STATE_DIR).glob("*/retro.json")):
        try:
            r = json.loads(f.read_text())
            g = _as_utc(r.get("generated_at"))
            if g and g <= now - timedelta(days=3) and (best is None or g > best[0]):
                best = (g, r["current"]["velocity"]["backlog"])
        except Exception:  # noqa: BLE001
            continue
    return best[1] if best else None


def _kraw(path):
    p = subprocess.run(["kubectl", "get", "--raw", path], capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or "").strip()[:200])
    return json.loads(p.stdout)


def fetch_prom(spans):
    try:
        q = (f'max_over_time(ALERTS{{alertstate="firing",severity=~"{PAGING_SEVERITIES}",'
             f'alertname!~"Watchdog|InfoInhibitor"}}[{PERIOD_DAYS}d])')
        res = {}
        for name, (_, end) in spans.items():
            d = _kraw(f"{PROM}/api/v1/query?query={quote(q)}&time={end.timestamp():.0f}")
            series = d["data"]["result"]
            top = Counter(s["metric"].get("alertname", "?") for s in series)
            res[name] = {"total": len(series), "top": dict(top.most_common(8))}
        floor = _kraw(f"{PROM}/api/v1/query?query={quote('min(prometheus_tsdb_lowest_timestamp_seconds)')}")
        vals = floor["data"]["result"]
        res["_floor"] = float(vals[0]["value"][1]) * 1000 if vals else None
        return res, None
    except Exception as e:  # noqa: BLE001
        return None, f"prometheus: {e}"


def fetch_silences():
    try:
        return _kraw(f"{AM}/api/v2/silences"), None
    except Exception as e:  # noqa: BLE001
        return None, f"alertmanager: {e}"


# ============================================================================
def build(now=None):
    now = now or datetime.now(timezone.utc)
    spans = periods(now)
    since = spans["previous"][0]
    sources = {}

    pg, err = fetch_pg(os.environ.get("SWEEP_PG_DSN"), since)
    sources["postgres"] = {"ok": pg is not None, "error": err}
    oc, err = fetch_openclaw(since - timedelta(days=1))
    home_ok = oc is not None and "home_op_error" not in oc
    cron_ok = oc is not None and "cron_error" not in oc
    sources["home_operation"] = {"ok": home_ok, "error": err or (oc or {}).get("home_op_error")}
    sources["openclaw_cron"] = {"ok": cron_ok, "error": err or (oc or {}).get("cron_error")}
    gitd, err = fetch_git(since)
    sources["git"] = {"ok": gitd is not None, "error": err}
    prom, err = fetch_prom(spans)
    sources["prometheus"] = {"ok": prom is not None, "error": err}
    sil, err = fetch_silences()
    sources["alertmanager"] = {"ok": sil is not None, "error": err}
    cov, err = fetch_coverage()
    sources["coverage"] = {"ok": cov is not None, "error": err}
    prs, err = fetch_renovate_prs(since)
    sources["renovate_prs"] = {"ok": prs is not None, "error": err}
    bumps, err = fetch_bumps(gitd["authored"]) if gitd else (None, "git log unreadable")
    sources["registry_publish_dates"] = {"ok": bumps is not None, "error": err}
    prev_backlog = load_prev_snapshot(now)

    mp = _load_mp()
    cfg = mp.load_windows()
    wr = pg["window_runs"] if pg else None
    pe = pg["plan_executions"] if pg else None
    draft = None
    if pe is not None:
        draft, err = fetch_draft_dates([r[0] for r in pe])
        if err:
            sources["git"] = {"ok": False, "error": err}

    issues = {r[0]: r[1] for r in oc["issues"]} if home_ok else None
    events = [tuple(e) for e in oc["events"]] if home_ok else None
    open_gng = None
    if home_ok:
        first = {}
        for k, ts, kind, _ in sorted(events, key=lambda e: e[1]):
            if kind == "opened":
                first.setdefault(k, ts)
        open_gng = [(r[0], first.get(r[0]) or r[3]) for r in oc["issues"]
                    if r[1] == "go_no_go" and r[2] == "open"]
    window_notes = [(r[2], r[7]) for r in wr] if wr is not None else None
    exec_notes = [(r[3], r[4]) for r in pe] if pe is not None else None

    report = {"generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "period_days": PERIOD_DAYS,
              "periods": {k: [v[0].strftime("%Y-%m-%dT%H:%MZ"), v[1].strftime("%Y-%m-%dT%H:%MZ")]
                          for k, v in spans.items()},
              "sources": sources, "current": {}, "previous": {}}
    from zoneinfo import ZoneInfo
    for name, span in spans.items():
        end_day = span[1].astimezone(ZoneInfo("Europe/Berlin")).date()
        sec = report[name]
        sec["windows"] = window_metrics(mp, cfg, [r[:8] for r in wr] if wr is not None else None,
                                        end_day, span)
        sec["plans"] = plan_metrics([r[:4] for r in pe] if pe is not None else None, draft,
                                    open_gng, span, now)
        sec["hitl"] = hitl_metrics(issues, events, window_notes, exec_notes,
                                   gitd["messages"] if gitd else None, span)
        sec["automation"] = cron_metrics(oc.get("jobs") if cron_ok else None,
                                         oc.get("runs") if cron_ok else None,
                                         oc.get("runs_oldest_ms") if cron_ok else None, span)
        liv = mp.sweep_cron_liveness_report(now=span[1], lookback_days=PERIOD_DAYS) if pg else None
        sec["automation"].update(sweep_metrics(pg["sweep_cycles"] if pg else None, liv, span))
        sec["findings"] = findings_metrics(pg["sweep_findings"] if pg else None, span, now,
                                           is_current=(name == "current"))
        sec["git"] = git_metrics(gitd["commits"] if gitd else None, span)
        sec["alerts"] = alert_metrics(prom.get(name) if prom else None, sil, span, now,
                                      prom.get("_floor") if prom else None)
        cur_ = name == "current"
        sec["velocity"] = {
            "backlog": velocity_backlog(cov, prev_backlog, cur_),
            "lead_time_days": velocity_lead_time(bumps, span),
            "landed_by": velocity_share(gitd["authored"] and [(t, s_, a, b) for t, s_, a, _, b in gitd["authored"]]
                                        if gitd else None, span),
            **security_velocity(pg["security_fixable"] if pg else None, span, cur_),
            "renovate_prs_opened": renovate_intake(prs, span),
            "earned_lane": earned_lane(cov, None, span) if cur_ else U("point-in-time: current period only"),
        }
    return report


# ---- rendering --------------------------------------------------------------
def fmt(m):
    if not isinstance(m, dict) or "measured" not in m:
        return str(m)
    if not m["measured"]:
        return f"UNMEASURED ({m['reason']})"
    v = m["value"]
    if isinstance(v, dict):
        v = ", ".join(f"{k}={x}" for k, x in v.items()) or "none"
    elif isinstance(v, list):
        v = ", ".join(str(x) for x in v) or "none"
    tag = f" [{m['coverage']}]" if m.get("coverage") in ("partial", "lower-bound") else ""
    mx = f" (n={m['n']}, max {m['max']})" if "n" in m and "max" in m else ""
    return f"{v}{mx}{tag}"


def render_md(r):
    c, p = r["current"], r["previous"]
    L = [f"# Ops retro — {r['periods']['current'][0][:10]} .. {r['periods']['current'][1][:10]}",
         "", f"_generated {r['generated_at']}; previous week = {r['periods']['previous'][0][:10]} .. "
             f"{r['periods']['previous'][1][:10]}_", ""]
    bad = [k for k, v in r["sources"].items() if not v["ok"]]
    L.append("**Sources:** " + ("all read" if not bad else
                                "FAILED: " + "; ".join(f"{k} ({r['sources'][k]['error']})" for k in bad)))
    vb = c["velocity"]["backlog"]
    if vb["measured"] and vb.get("grew"):
        L += ["", f"**BACKLOG GREW: {vb['previous_pending']} -> {vb['pending']} pending updates "
                  f"(+{vb['delta']}) — we are not keeping pace.**"]
    L += ["", "## Patch velocity (headline)", "", "| Metric | This week | Previous week |", "|---|---|---|"]
    for label, key in (("Update backlog by lane (pending = AUTO+PLAN+REBUILD+CRACK)", "backlog"),
                       ("Patch lead time publish->landed, median d", "lead_time_days"),
                       ("Bumps landed by (auto / plan / operator)", "landed_by"),
                       ("Open fixable HIGH/CRIT (non-AR)", "open_fixable_high_crit"),
                       ("Security detect->fixed, median d", "detect_to_fixed_days"),
                       ("Renovate PRs opened", "renovate_prs_opened"),
                       ("Earned-autonomy lane", "earned_lane")):
        cv, pv = c["velocity"][key], p["velocity"][key]
        def _v(m):
            s_ = fmt(m)
            if m.get("measured") and "p90" in m:
                s_ += f" p90 {m['p90']}"
            if m.get("measured") and "pending" in m:
                s_ = f"pending {m['pending']} ({s_})"
            if m.get("measured") and "merged" in m:
                s_ += f"; merged {m['merged']}, open->merge median {m.get('open_to_merge_days_median')}d"
            if m.get("measured") and "auto_pct" in m:
                s_ += f" — {m['auto_pct']}% auto"
            if m.get("measured") and "by_contextual_tier" in m:
                s_ += f" (contextual {m['by_contextual_tier']}; newer tag available {m['newer_tag_available']})"
            return s_
        L.append(f"| {label} | {_v(cv)} | {_v(pv)} |")
    L += ["", "## Operations", ""]
    rows = [
        ("Windows expected / run / missed", "windows", ("expected", "run", "missed")),
        ("Window missed slots", "windows", ("missed_slots",)),
        ("Window outcomes", "windows", ("outcomes",)),
        ("Safe updates landed", "windows", ("safe_updates",)),
        ("Plan outcomes", "plans", ("outcomes",)),
        ("Plans supervised / unsupervised", "plans", ("supervised", "unsupervised")),
        ("Plan queue age median (d)", "plans", ("queue_age_days_median",)),
        ("Go/no-go awaiting > 7d", "plans", ("awaiting_go_over_7d",)),
        ("Go/no-go opened", "hitl", ("gng_opened",)),
        ("Decisions", "hitl", ("decisions",)),
        ("Time-to-decision median (h)", "hitl", ("time_to_decision_h",)),
        ("GOs voided (expired)", "hitl", ("gos_voided",)),
        ("SD-n citations", "hitl", ("sd_citations",)),
        ("Operator questions (lower bound)", "hitl", ("operator_questions",)),
        ("Cron runs ok / error / refusals", "automation", ("totals",)),
        ("Sweep cycles by trigger", "automation", ("cycles_by_trigger",)),
        ("Missed 48h sweeps", "automation", ("missed_sweeps",)),
        ("Findings opened / closed / net", "findings", ("opened", "closed", "net")),
        ("Findings open at period end", "findings", ("open_at_end",)),
        ("Commits / peak per hour / reverts", "git", ("commits", "peak_per_hour", "reverts")),
        ("Paging alert series", "alerts", ("paging_series",)),
        ("Silences created", "alerts", ("silences_created",)),
    ]
    L += ["| Metric | This week | Previous week |", "|---|---|---|"]
    for label, grp, keys in rows:
        cv = " / ".join(fmt(c[grp][k]) for k in keys)
        pv = " / ".join(fmt(p[grp][k]) for k in keys)
        L.append(f"| {label} | {cv} | {pv} |")
    t = c["automation"]["totals"]
    if t["measured"] and t["value"]["jobs_with_errors"]:
        L += ["", "**Cron jobs with errors this week:**"]
        for name, v in c["automation"]["per_job"]["value"].items():
            if v["error"]:
                ref = ", ".join(f"exit {k}×{n} ({REFUSAL_MEANING.get(int(k), '?')})"
                                for k, n in v["refusals"].items())
                L.append(f"- {name}: ok {v['ok']}, error {v['error']}"
                         + (f"; refusals: {ref}" if ref else "")
                         + (f"; exit codes {v['exit_codes']}" if v["exit_codes"] else ""))
    ma = c["findings"]["median_age_days_by_section"]
    if ma["measured"]:
        L += ["", "**Median age of open findings by section (days):** "
              + ", ".join(f"{k} {v}" for k, v in ma["value"].items())]
    oa = c["findings"]["oldest_actionable"]
    if oa["measured"]:
        L += ["", "**Oldest actionable (non-AR) findings:**"]
        L += [f"- {x['id']} [{x['section']}/{x['severity']}] {x['age_days']}d — {x['title']}" for x in oa["value"]] \
            or ["- none"]
    ag = c["plans"]["awaiting_go_over_7d"]
    if ag["measured"] and ag["value"]:
        L += ["", "**Go/no-go open > 7 days:** " + ", ".join(f"{k} ({d}d)" for k, d in ag["items"])]
    pk = c["git"]["peak_per_hour"]
    if pk["measured"]:
        L += ["", f"**Git:** peak {pk['value']} commits in {pk.get('hour')}; "
                  f"max/day {c['git']['per_day'].get('max')}"]
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true", help="print JSON instead of markdown")
    ap.add_argument("--json-out")
    ap.add_argument("--md-out")
    a = ap.parse_args(argv)
    r = build()
    md = render_md(r)
    if a.json_out:
        Path(a.json_out).write_text(json.dumps(r, indent=2, default=str))
    if a.md_out:
        Path(a.md_out).write_text(md)
    print(json.dumps(r, indent=2, default=str) if a.json else md)
    failed = [k for k, v in r["sources"].items() if not v["ok"]]
    if failed:
        print(f"ops-retro: DATA SOURCE FAILURE: {', '.join(failed)} — affected metrics are "
              f"UNMEASURED, not zero", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
