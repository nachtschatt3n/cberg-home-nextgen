#!/usr/bin/env python3
"""run-now — preflight + stamp for an operator-triggered on-demand NOW run.

WHY THIS EXISTS
An operator must be able to say "run X now" — to OpenClaw
(`home-operation run --issue X`) or in the Mac ops console — and have vetted,
approved plans executed immediately in an ATTENDED run instead of waiting for
the next scheduled window. The say-so path existed but was dead: it resolved an
issue to its SCHEDULED window and fired a normal window run, whose agent then
looked for plans due in that window today (usually none) and exited idle.

An on-demand run replaces the scheduled-window occupancy checks (capacity,
weekday, "is this plan due in this slot?") with a per-plan PREFLIGHT, because
the operator picked the plans and is present. This script is that preflight,
and the helper that stamps the chosen plans for the run. The window agent's
"On-demand NOW runs" section (.claude/agents/maintenance-window-agent.md) is
the execution contract that calls it.

    run-now.py preflight <plan_id>... [--operator-go "<who/how>" [--resume]] [--json]
    run-now.py stamp <plan_id>... [--date YYYY-MM-DD] [--dry-run]

PREFLIGHT — per plan, cheapest refusal first, fail CLOSED everywhere:
  1. the plan file exists and its frontmatter parses (an UNREADABLE plan is
     reported as unreadable, never as absent — F-6a398b8b);
  2. status is vetted|scheduled|awaiting-go. draft (nobody has confirmed it),
     blocked, awaiting-soak, executed, superseded and reference are REFUSED
     with the reason;
  3. needs_reboot is REFUSED — on_demand.allow_reboot is false; node rolls keep
     the reboot-capable Sunday window and its sized rollback budget;
  4. est_duration_min fits the on_demand ceiling; every depends_on is either
     executed or part of this same run (it is then ordered first);
  5. an operator approval: a PENDING `approve` in
     `home-operation --json decisions --pending-exec` whose window is this
     on-demand run (`now:<today|yesterday>`, which `home-operation run --issue`
     stamps) — OR `--operator-go "<who/how>"`, recorded in the output as the
     consent source. A recorded pending DENY refuses even with --operator-go
     (revoke it first). The approvals exec failing is "NO approval", never
     "approved": without --operator-go the plan is refused;
  6. premises PASS via `plan-premises.py <id> --require-premises --json` (the
     same fail-closed verdict window-scheduler.py applies).
  Also (B2, 2026-09-15): a plan already stamped `window: now:<today>` whose
  status is not executed is REFUSED — "already in an on-demand run today" — so a
  second say-so cannot start the same plans a second time while the first NOW
  run is waiting at an operator question. Only `--operator-go "<who/how>"`
  TOGETHER with `--resume` lets the SAME run pick them up again (e.g. after the
  operator answered a partial-preflight question).

DURABLE CONSENT (N4). With --operator-go the output carries
`running_row_notes: "operator-go: <exact string>"`; the agent contract writes
that exact string into the `window-run-record.py --slot now` running row's
--notes (same --started, so the row is upserted, not duplicated).

WHY AN APPROVAL FOR ANOTHER WINDOW DOES NOT COUNT. An approval is scoped to the
window it was given for (docs/sops/maintenance-windows.md). A GO recorded for
`sun-attended:<date>` was given for an attended Sunday slot with its own
budget; running it on a Tuesday afternoon is a different decision. The OpenClaw
path re-scopes the approval to `now:<today>` when the operator says "run it
now"; from the console the operator passes --operator-go.

ORDER — deterministic and SERIAL: plans touching shared infra (touches.shared
non-empty) first, then by risk high→low, stable by plan_id, with depends_on
inside the run honoured. Ordering alone is not enough: every sequence entry
carries `depends_on_in_run` (its depends_on that are steps of THIS run), and the
executor must not start a step unless each of those executed GREEN in this run —
a dependency that aborted or rolled back cleanly still leaves its dependant
unsafe to run. A declared conflicts_with pair (EITHER direction —
the field is one-sided in practice) is allowed in one on-demand run ONLY
because execution is strictly serial; the later plan of such a pair is marked
`settle_before: true` so the executor re-verifies cluster-wide health and lets
the first change settle before starting it. The same flag follows a
shared-infra step.

STAMP rewrites each plan's `window:` frontmatter line to `now:<date>` (nothing
else in the file changes; the result is re-parsed and compared key-by-key
before anything is written, and one refusal writes nothing). It applies the
static refusals (2-4) so a plan preflight would refuse is never stamped.

Pure functions (no cluster, no clock) carry every decision; the CLI is the
only impure layer. Exit codes: preflight 0 = every requested plan runnable,
1 = some refused (the runnable remainder is still sequenced — ask the
operator), 2 = nothing runnable / usage / on_demand slot not declared;
stamp 0 = stamped, 1 = refused (nothing written), 2 = usage.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent

RUNNABLE_STATUSES = ("vetted", "scheduled", "awaiting-go")
REFUSED_STATUS_WHY = {
    "draft": "nobody has confirmed a draft is correct — a plan-reviewer must vet it first",
    "blocked": "blocked plans are re-planned, never re-run on say-so",
    "awaiting-soak": "the plan is inside a deliberate soak; a NOW run must not collapse it",
    "executed": "already executed",
    "superseded": "superseded by a newer plan and will never run",
    "reference": "reference/break-glass material, not an executable unit",
}
RISK_RANK = {"high": 3, "medium": 2, "low": 1}
PLAN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
DECISIONS_CMD = ["kubectl", "-n", "ai", "exec", "deploy/openclaw", "-c", "app", "--",
                 "/home/node/.openclaw/bin/home-operation", "--json",
                 "decisions", "--pending-exec"]
TZ = "Europe/Berlin"


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, SCRIPT_DIR / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def today_local(now: dt.datetime | None = None) -> dt.date:
    """Today in Europe/Berlin (the schedule's timezone), not the Mac's."""
    from zoneinfo import ZoneInfo
    return (now or dt.datetime.now(dt.timezone.utc)).astimezone(ZoneInfo(TZ)).date()


def risk_of(plan: dict) -> str:
    toks = str(plan.get("risk") or "medium").split()
    return toks[0].strip().lower() if toks else "medium"


def shared_of(plan: dict) -> list:
    return list(((plan.get("touches") or {}).get("shared")) or [])


# --------------------------------------------------------------------------
# pure decision functions
# --------------------------------------------------------------------------

def static_refusals(plan: dict, by_id: dict, on_demand: dict, run_ids) -> list[str]:
    """Refusals decidable from the plan files alone (no cluster, no DB)."""
    out = []
    status = str(plan.get("status") or "").strip()
    if status not in RUNNABLE_STATUSES:
        why = REFUSED_STATUS_WHY.get(status, "not a runnable status")
        out.append(f"status {status or '<none>'!r} is not runnable "
                   f"(only {'|'.join(RUNNABLE_STATUSES)}): {why}")
    if plan.get("needs_reboot") and not on_demand.get("allow_reboot"):
        out.append("needs_reboot: an on-demand run may not reboot nodes — "
                   "schedule it into the reboot-capable window")
    dur = plan.get("est_duration_min")
    ceiling = int(on_demand.get("duration_min") or 0)
    if isinstance(dur, (int, float)) and ceiling and dur > ceiling:
        out.append(f"est_duration_min {dur} exceeds the on-demand ceiling ({ceiling}m)")
    for dep in (plan.get("depends_on") or []):
        dep = str(dep)
        if dep in run_ids:
            continue
        d = by_id.get(dep)
        if d is None:
            out.append(f"depends_on {dep!r} names no existing plan — the guard is "
                       f"unenforceable, fix the ref before running")
        elif str(d.get("status") or "").strip() != "executed":
            out.append(f"unmet depends_on {dep!r} (status {d.get('status')!r}) — "
                       f"run it first or include it in this run")
    return out


def already_stamped_today(plan: dict, on_demand_id: str, today: dt.date) -> bool:
    """True when the plan is stamped for an on-demand run TODAY and has not
    executed — i.e. it is already part of a NOW run that may still be live."""
    window = str(plan.get("window") or "").strip()
    status = str(plan.get("status") or "").strip()
    return window == f"{on_demand_id}:{today.isoformat()}" and status != "executed"


def stamped_refusal(plan: dict, on_demand_id: str, today: dt.date,
                    operator_go: str | None, resume: bool) -> str | None:
    if not already_stamped_today(plan, on_demand_id, today):
        return None
    if (operator_go or "").strip() and resume:
        return None
    return (f"already in an on-demand run today (window {plan.get('window')!r}, "
            f"status {plan.get('status')!r}) — a second NOW run must not start it "
            f"again. Only the SAME run may continue it, and only with the operator's "
            f"explicit yes: --operator-go \"<who/how>\" --resume")


def parse_decisions(returncode, stdout) -> list | None:
    """The pending-exec decision rows, or None when they could not be READ.

    None is "no confirmed approvals available" and must never be read as
    approval — an exec that failed (pod mid-roll) is not consent."""
    if returncode != 0:
        return None
    try:
        doc = json.loads(stdout or "")
    except ValueError:
        return None
    rows = doc.get("decisions") if isinstance(doc, dict) else None
    if not isinstance(rows, list):
        return None
    return [r for r in rows if isinstance(r, dict)]


def approval_verdict(plan_id: str, decisions: list | None, operator_go: str | None,
                     on_demand_id: str, today: dt.date) -> tuple[bool, str]:
    """(ok, consent source | refusal reason)."""
    rows = [d for d in (decisions or []) if str(d.get("key")) == plan_id]
    if any(d.get("decision") == "deny" for d in rows):
        return False, ("the operator DENIED this plan (pending deny in home-operation) — "
                       "revoke it (`home-operation resolve --issue <key> --by cleared`) "
                       "and re-approve before a NOW run")
    approved = [d for d in rows
                if d.get("decision") == "approve" and d.get("exec_state") == "pending"]
    ref = re.compile(rf"^{re.escape(on_demand_id)}:(\d{{4}}-\d{{2}}-\d{{2}})$")
    for d in approved:
        m = ref.match(str(d.get("window") or ""))
        if not m:
            continue
        try:
            age = (today - dt.date.fromisoformat(m.group(1))).days
        except ValueError:
            continue
        if 0 <= age <= 1:
            return True, (f"home-operation approval by {d.get('decided_by') or '?'} "
                          f"at {d.get('decided_at') or '?'} for {d.get('window')}")
    go = (operator_go or "").strip()
    if go:
        return True, f"operator-go: {go}"
    if decisions is None:
        return False, ("could not read home-operation approvals (exec failed) — "
                       "fail closed: no confirmed approval. If the operator is at the "
                       "console, pass --operator-go \"<who/how>\"")
    if approved:
        wins = ", ".join(sorted({str(d.get('window') or '<no window>') for d in approved}))
        return False, (f"approved for {wins}, not for an on-demand {on_demand_id} run "
                       f"(an approval is scoped to its window) — re-approve via "
                       f"`home-operation run --issue {plan_id}` or pass --operator-go")
    return False, "no operator approval pending for this plan"


def conflict_pairs(plans: list) -> list[tuple[str, str]]:
    """Declared conflicts among the plans in this run, symmetric, sorted."""
    ids = {p.get("plan_id") for p in plans}
    pairs = set()
    for p in plans:
        for other in (p.get("conflicts_with") or []):
            if other in ids and other != p.get("plan_id"):
                pairs.add(tuple(sorted((str(p.get("plan_id")), str(other)))))
    return sorted(pairs)


def order_plans(plans: list) -> tuple[list, list[str]]:
    """(ordered plans, errors). Shared infra first, then risk high→low, stable
    by plan_id; a depends_on inside the run always precedes its dependant."""
    base = sorted(plans, key=lambda p: (0 if shared_of(p) else 1,
                                         -RISK_RANK.get(risk_of(p), 2),
                                         str(p.get("plan_id"))))
    ids = {p.get("plan_id") for p in base}
    done, ordered, remaining, errors = set(), [], list(base), []
    while remaining:
        for p in remaining:
            waiting = [d for d in (p.get("depends_on") or []) if d in ids and d not in done]
            if not waiting:
                ordered.append(p)
                done.add(p.get("plan_id"))
                remaining.remove(p)
                break
        else:
            errors.append("depends_on cycle among: "
                          + ", ".join(str(p.get("plan_id")) for p in remaining))
            ordered.extend(remaining)
            break
    return ordered, errors


def build_sequence(plans: list) -> tuple[list[dict], list[tuple[str, str]], list[str]]:
    ordered, errors = order_plans(plans)
    pairs = conflict_pairs(plans)
    partners: dict[str, set] = {}
    for a, b in pairs:
        partners.setdefault(a, set()).add(b)
        partners.setdefault(b, set()).add(a)
    in_run = {str(p.get("plan_id")) for p in ordered}
    seq, seen, prev = [], set(), None
    for i, p in enumerate(ordered):
        pid = str(p.get("plan_id"))
        earlier_conflicts = sorted(partners.get(pid, set()) & seen)
        reasons = []
        if earlier_conflicts:
            reasons.append("declared conflict with earlier step(s) "
                           + ", ".join(earlier_conflicts)
                           + " — allowed in one run ONLY because execution is serial")
        if prev is not None and shared_of(prev):
            reasons.append(f"previous step {prev.get('plan_id')} touched shared infra "
                           f"{shared_of(prev)}")
        seq.append({
            "step": i + 1,
            "plan_id": pid,
            "component": p.get("component"),
            "kind": p.get("kind"),
            "risk": risk_of(p),
            "est_duration_min": p.get("est_duration_min"),
            "shared": shared_of(p),
            "rollback_class": p.get("rollback_class"),
            "conflicts_in_run": sorted(partners.get(pid, set())),
            # the executor must not start this step unless every one of these
            # executed GREEN earlier in this run (ordering alone is not a guard)
            "depends_on_in_run": [str(d) for d in (p.get("depends_on") or [])
                                  if str(d) in in_run],
            "settle_before": bool(reasons),
            "settle_reason": "; ".join(reasons) or None,
            # serial run: re-verify cluster-wide health before EVERY step after
            # the first; settle_before marks where it is load-bearing.
            "reverify_health_before": i > 0,
        })
        seen.add(pid)
        prev = p
    return seq, pairs, errors


def unreadable_for(plan_id: str, load_errors) -> str | None:
    for err in load_errors or []:
        path = err.split(":", 1)[0].strip()
        if path.endswith(f"/{plan_id}.md") or path == f"{plan_id}.md":
            return err
    return None


def preflight(plan_ids, plans, load_errors, on_demand, decisions, operator_go,
              today, premises_check, resume=False) -> dict:
    """The whole verdict. `premises_check(plan_id) -> (ok, reason)` is the only
    impure step and is injected; one that raises fails closed."""
    requested = []
    for pid in plan_ids:
        if pid not in requested:
            requested.append(pid)
    by_id = {p.get("plan_id"): p for p in plans if p.get("plan_id")}
    run_ids = set(requested)
    od_id = on_demand["id"]
    results = []
    for pid in requested:
        reasons, consent = [], None
        if not PLAN_ID_RE.match(pid):
            reasons.append("not a plan id")
        elif (err := unreadable_for(pid, load_errors)):
            reasons.append(f"plan file UNREADABLE — {err}")
        elif pid not in by_id:
            reasons.append("no plan file with this plan_id")
        else:
            reasons += static_refusals(by_id[pid], by_id, on_demand, run_ids)
            why = stamped_refusal(by_id[pid], od_id, today, operator_go, resume)
            if why:
                reasons.append(why)
        if not reasons:
            ok, why = approval_verdict(pid, decisions, operator_go, od_id, today)
            if ok:
                consent = why
            else:
                reasons.append(why)
        if not reasons:
            try:
                ok, why = premises_check(pid)
            except Exception as e:  # noqa: BLE001
                ok, why = False, f"premises check raised {type(e).__name__}: {e} — fail closed"
            if not ok:
                reasons.append(f"premises not verified — {why}")
        results.append({"plan_id": pid, "ok": not reasons, "reasons": reasons,
                        "consent_source": consent})
    runnable = [by_id[r["plan_id"]] for r in results if r["ok"]]
    # a dependant is only runnable if its in-run dependency is too
    dropped = True
    while dropped:
        dropped = False
        ok_ids = {p.get("plan_id") for p in runnable}
        for r in results:
            if not r["ok"]:
                continue
            missing = [d for d in (by_id[r["plan_id"]].get("depends_on") or [])
                       if d in run_ids and d not in ok_ids]
            if missing:
                r["ok"] = False
                r["consent_source"] = None
                r["reasons"].append(f"depends_on {', '.join(missing)} was refused in this run")
                runnable = [p for p in runnable if p.get("plan_id") != r["plan_id"]]
                dropped = True
    seq, pairs, seq_errors = build_sequence(runnable)
    total = sum(int(p.get("est_duration_min") or 0) for p in runnable)
    ceiling = int(on_demand.get("duration_min") or 0)
    warnings = []
    if ceiling and total > ceiling:
        warnings.append(f"sequence estimates {total}m against the {ceiling}m on-demand "
                        f"ceiling — the window_runs row will read as stuck; split the run")
    all_ok = bool(results) and all(r["ok"] for r in results) and not seq_errors
    return {
        "slot": od_id,
        "window_ref": f"{od_id}:{today.isoformat()}",
        "run_date": today.isoformat(),
        "trigger": "ad-hoc",
        "mode": on_demand.get("mode", "attended"),
        "serial": True,
        "requested": requested,
        "ok": all_ok,
        "partial": bool(runnable) and not all_ok,
        "operator_go": (operator_go or "").strip() or None,
        "resume": bool(resume),
        # the exact consent string the agent must put in the running row's --notes
        "running_row_notes": (f"operator-go: {(operator_go or '').strip()}"
                              if (operator_go or "").strip() else None),
        "approvals_readable": decisions is not None,
        "plans": results,
        "sequence": seq,
        "conflict_pairs": [list(p) for p in pairs],
        "total_est_duration_min": total,
        "ceiling_min": ceiling,
        "warnings": warnings,
        "errors": seq_errors,
    }


def exit_code(report: dict) -> int:
    if report["ok"]:
        return 0
    return 1 if report["sequence"] else 2


def stamp_text(text: str, window_ref: str, note: str) -> tuple[str | None, str | None]:
    """(new_text, error). Rewrites ONLY the frontmatter `window:` line."""
    if not text.startswith("---"):
        return None, "no frontmatter"
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None, "unterminated frontmatter"
    fm = parts[1]
    try:
        before = yaml.safe_load(fm) or {}
    except yaml.YAMLError as e:
        return None, f"frontmatter unparseable: {str(e).splitlines()[0]}"
    if not isinstance(before, dict):
        return None, "frontmatter is not a mapping"
    lines = fm.split("\n")
    idx = [i for i, ln in enumerate(lines) if re.match(r"^window\s*:", ln)]
    if len(idx) > 1:
        return None, "more than one top-level window: line"
    line = f'window: "{window_ref}"   # {note}'
    if idx:
        lines[idx[0]] = line
    else:
        at = len(lines) - 1 if lines and lines[-1] == "" else len(lines)
        lines.insert(at, line)
    new_fm = "\n".join(lines)
    try:
        after = yaml.safe_load(new_fm) or {}
    except yaml.YAMLError as e:
        return None, f"stamped frontmatter no longer parses: {str(e).splitlines()[0]}"
    if after.get("window") != window_ref:
        return None, f"stamp did not take (window reads {after.get('window')!r})"
    if {k: v for k, v in after.items() if k != "window"} != \
            {k: v for k, v in before.items() if k != "window"}:
        return None, "stamp would change keys other than window — refusing"
    return "---".join([parts[0], new_fm, parts[2]]), None


def stamp_plans(plan_ids, plans, on_demand, date: dt.date, dry_run=False) -> tuple[list, list]:
    """(stamped, refused). All-or-nothing: any refusal writes nothing."""
    by_id = {p.get("plan_id"): p for p in plans if p.get("plan_id")}
    ref = f"{on_demand['id']}:{date.isoformat()}"
    run_ids = set(plan_ids)
    staged, refused = [], []
    for pid in plan_ids:
        p = by_id.get(pid)
        if p is None:
            refused.append({"plan_id": pid, "reasons": ["no plan file with this plan_id"]})
            continue
        why = static_refusals(p, by_id, on_demand, run_ids)
        if why:
            refused.append({"plan_id": pid, "reasons": why})
            continue
        path = Path(p["_path"])
        if not path.is_absolute():
            path = SCRIPT_DIR.parent / path
        note = (f"ON-DEMAND NOW run {date.isoformat()} (run-now.py stamp; "
                f"was {p.get('window')!r})")
        new, err = stamp_text(path.read_text(), ref, note)
        if err:
            refused.append({"plan_id": pid, "reasons": [err]})
            continue
        staged.append((pid, path, new))
    if refused:
        return [], refused
    if not dry_run:
        for _, path, new in staged:
            path.write_text(new)
    return [{"plan_id": pid, "path": str(path), "window": ref} for pid, path, _ in staged], []


# --------------------------------------------------------------------------
# impure layer
# --------------------------------------------------------------------------

def fetch_pending_decisions(runner=subprocess.run, timeout=60) -> list | None:
    try:
        r = runner(DECISIONS_CMD, capture_output=True, text=True, timeout=timeout)
    except Exception:  # noqa: BLE001 — any failure is "not readable"
        return None
    return parse_decisions(r.returncode, r.stdout)


def _human(report: dict) -> str:
    L = [f"== on-demand {report['window_ref']} preflight ({report['mode']}, serial) =="]
    if report.get("running_row_notes"):
        L.append(f"  record VERBATIM in the window-run-record --slot now running row --notes: "
                 f"{report['running_row_notes']}")
    for r in report["plans"]:
        if r["ok"]:
            L.append(f"  OK       {r['plan_id']}  consent: {r['consent_source']}")
        else:
            L.append(f"  REFUSED  {r['plan_id']}")
            for why in r["reasons"]:
                L.append(f"             - {why}")
    if report["sequence"]:
        L.append("")
        L.append(f"sequence ({report['total_est_duration_min']}m of {report['ceiling_min']}m ceiling):")
        for s in report["sequence"]:
            flag = "  [SETTLE + RE-VERIFY HEALTH FIRST]" if s["settle_before"] else ""
            L.append(f"  {s['step']}. {s['plan_id']:<34} risk={s['risk']:<6} "
                     f"{s['est_duration_min']}m shared={s['shared']}{flag}")
            if s["settle_reason"]:
                L.append(f"       why: {s['settle_reason']}")
            if s["depends_on_in_run"]:
                L.append(f"       only if GREEN earlier in this run: {', '.join(s['depends_on_in_run'])}")
    for w in report["warnings"] + report["errors"]:
        L.append(f"  ! {w}")
    if report["partial"]:
        L.append("\nPARTIAL: some requested plans were refused — ask the operator "
                 "before running the remainder.")
    elif not report["ok"]:
        L.append("\nNOTHING RUNNABLE.")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    pf = sub.add_parser("preflight", help="verdict + serial order for a NOW run (read-only)")
    pf.add_argument("plan_id", nargs="+")
    pf.add_argument("--operator-go", default=None,
                    help="record operator consent given at the console (who/how)")
    pf.add_argument("--resume", action="store_true",
                    help="with --operator-go only: let the SAME on-demand run continue "
                         "plans already stamped now:<today>")
    pf.add_argument("--json", action="store_true")
    st = sub.add_parser("stamp", help="rewrite window: to now:<date> in plan frontmatter")
    st.add_argument("plan_id", nargs="+")
    st.add_argument("--date", default=None, help="YYYY-MM-DD (default: today Europe/Berlin)")
    st.add_argument("--dry-run", action="store_true")
    st.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    mp = _load("mp", "maintenance-plan.py")
    cfg = mp.load_windows()
    od = mp.on_demand_slot(cfg)
    if not od:
        print("run-now: maintenance-windows.yaml declares no on_demand slot — refusing",
              file=sys.stderr)
        return 2
    plans = mp.load_plans(cfg)
    load_errors = list(mp.PLAN_LOAD_ERRORS)
    ids = [x.strip() for raw in args.plan_id for x in raw.split(",") if x.strip()]

    if args.cmd == "stamp":
        try:
            date = dt.date.fromisoformat(args.date) if args.date else today_local()
        except ValueError:
            print(f"run-now: --date {args.date!r} is not YYYY-MM-DD", file=sys.stderr)
            return 2
        stamped, refused = stamp_plans(ids, plans, od, date, dry_run=args.dry_run)
        out = {"stamped": stamped, "refused": refused, "dry_run": args.dry_run}
        if args.json:
            print(json.dumps(out, indent=2))
        else:
            for s in stamped:
                print(f"  {'WOULD STAMP' if args.dry_run else 'STAMPED'}  {s['plan_id']} -> {s['window']}")
            for r in refused:
                print(f"  REFUSED  {r['plan_id']}: {'; '.join(r['reasons'])}")
            if refused:
                print("nothing written (all-or-nothing)")
        return 1 if refused else 0

    if args.resume and not (args.operator_go or "").strip():
        print("run-now: --resume requires --operator-go \"<who/how>\" (the operator's "
              "explicit yes to continue plans already in today's NOW run)", file=sys.stderr)
        return 2
    ws = _load("ws", "window-scheduler.py")
    report = preflight(ids, plans, load_errors, od, fetch_pending_decisions(),
                       args.operator_go, today_local(), ws.check_premises_subprocess,
                       resume=args.resume)
    print(json.dumps(report, indent=2) if args.json else _human(report))
    return exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
