#!/usr/bin/env python3
"""Route every open CRITICAL sweep finding into a lane, so none can just sit.

The no-cracks coverage guarantee (daily-operation rule 4d0) proves that every
actionable VERSION UPDATE reaches a lane. Nothing did the same for findings that
are not version updates. On 2026-08-24 a frigate memory leak sat at 98.6% of its
limit with `action` NULL, no plan, no window and no owner — reported every day
and routed nowhere. Meanwhile an uptime-kuma CVE finding looked equally stuck but
had in fact already been fixed by the update pipeline five hours later; nothing
connected the two. This tool closes both halves of that gap.

Lanes (see runbooks/finding-triage-policy.yaml for the operator-owned policy):

    COVERED   already handled by the update pipeline — do nothing
    FIX_NOW   additive, revertible, restarts nothing → the sweep may apply it
    PLAN      needs a maintenance window
    DECIDE    needs an operator judgement
    CRACK     matched nothing — must be zero, pages if not

Read-only unless `--apply-fixes` is passed, and even then it only runs registered
remediation recipes for findings the policy explicitly allows. It never invents a
fix, and it never touches the cluster directly: remediations are git edits that
Flux reconciles, per the repository's GitOps rule.
"""

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
from pathlib import Path

POLICY_PATH = Path(__file__).parent / "finding-triage-policy.yaml"

LANES = ("COVERED", "FIX_NOW", "PLAN", "DECIDE", "CRACK")

# A remediation recipe must be registered here to be runnable. The policy names a
# recipe; an unknown name is a hard error rather than a silent skip, so a typo in
# the policy cannot quietly turn an auto-fix into a no-op.
REMEDIATIONS = ("doc_count_sync", "add_prometheus_rule")


def load_policy(path: Path = POLICY_PATH) -> dict:
    """Load the routing policy, failing SAFE.

    A missing or unparseable policy must not mean "nothing matched, therefore
    nothing needs doing" — that would silently disable the guarantee this tool
    exists to provide. It means "route everything to PLAN and say so".
    """
    try:
        import yaml  # noqa: PLC0415 - optional dep, only needed here
        policy = yaml.safe_load(path.read_text())
        if not isinstance(policy, dict):
            raise ValueError("policy is not a mapping")
        return policy
    except Exception as exc:  # noqa: BLE001 - any failure means fail-safe
        return {
            "_degraded": f"{type(exc).__name__}: {exc}",
            "fix_now": [], "plan": [], "decide": [],
            "default_lane": "PLAN",
        }


def _matches(rule: dict, finding: dict) -> bool:
    """Does this rule apply? Title globs are '|'-separated and case-insensitive."""
    section = rule.get("match_section")
    if section and finding.get("section") != section:
        return False
    pattern = rule.get("match_title")
    if not pattern:
        return bool(section)
    title = (finding.get("title") or "").lower()
    return any(
        fnmatch.fnmatch(title, part.strip().lower())
        for part in pattern.split("|")
    )


def covered_components(coverage_json: str | None) -> set:
    """Components the update pipeline already owns.

    A finding whose component is in an update lane is COVERED: the maintenance
    window will bump it. Acting on it here would race that pipeline and risk
    double-applying — which is exactly what happened to uptime-kuma, where the
    finding and its fix were five hours apart with nothing linking them.
    """
    if not coverage_json:
        return set()
    try:
        data = json.loads(Path(coverage_json).read_text()) \
            if Path(coverage_json).exists() else json.loads(coverage_json)
    except (json.JSONDecodeError, OSError):
        return set()
    names = set()
    for key in ("auto", "plan", "rebuild", "held", "items"):
        for item in data.get(key) or []:
            if isinstance(item, dict):
                for field in ("component", "name", "dep", "image", "app"):
                    if item.get(field):
                        names.add(str(item[field]).lower())
            elif isinstance(item, str):
                names.add(item.lower())
    return names


def _component_of(finding: dict) -> str:
    """Best-effort component name from a finding title.

    Titles are written for humans, so this is a heuristic and is only ever used
    to ask "is the update pipeline already on this?". A miss costs a redundant
    PLAN lane, never a wrong action.
    """
    title = finding.get("title") or ""
    backticked = re.findall(r"`([^`]+)`", title)
    if backticked:
        first = backticked[0]
        first = first.split("@")[0].split(":")[0]
        return first.rsplit("/", 1)[-1].lower()
    return ""


def triage(findings: list, policy: dict, covered: set) -> list:
    """Assign exactly one lane to every finding. Order of precedence matters."""
    results = []
    for finding in findings:
        component = _component_of(finding)
        lane, rule_id, reason, remediation = None, None, None, None

        # COVERED wins over everything: if the update pipeline owns this
        # component, no other lane should touch it.
        if component and component in covered:
            lane, rule_id = "COVERED", "update-pipeline"
            reason = f"component '{component}' already has an update lane"

        # Policy-declared COVERED next: a finding another pipeline owns must not
        # also get a plan, or two things try to make the same change.
        if lane is None:
            for rule in policy.get("covered") or []:
                if _matches(rule, finding):
                    lane, rule_id, reason = "COVERED", rule.get("id"), rule.get("reason")
                    break

        # DECIDE before PLAN: an exposure question must not be quietly turned
        # into a scheduled change.
        if lane is None:
            for rule in policy.get("decide") or []:
                if _matches(rule, finding):
                    lane, rule_id, reason = "DECIDE", rule.get("id"), rule.get("reason")
                    break

        # PLAN before FIX_NOW: an explicit plan rule is a veto on auto-fixing,
        # so "memory limit" cannot be auto-applied even if some fix_now glob
        # would also have matched it.
        if lane is None:
            for rule in policy.get("plan") or []:
                if _matches(rule, finding):
                    lane, rule_id, reason = "PLAN", rule.get("id"), rule.get("reason")
                    break

        if lane is None:
            for rule in policy.get("fix_now") or []:
                if _matches(rule, finding):
                    recipe = rule.get("remediation")
                    if recipe not in REMEDIATIONS:
                        # A policy naming a recipe that does not exist is a bug,
                        # not a reason to skip: route to PLAN and say why.
                        lane, rule_id = "PLAN", rule.get("id")
                        reason = f"policy names unknown remediation '{recipe}'"
                    else:
                        lane, rule_id = "FIX_NOW", rule.get("id")
                        reason, remediation = rule.get("why_safe"), recipe
                    break

        if lane is None:
            lane = policy.get("default_lane", "PLAN")
            rule_id, reason = "default", "matched no rule; defaulted to a window"

        results.append({
            "finding_id": finding.get("finding_id"),
            "section": finding.get("section"),
            "severity": finding.get("severity"),
            "title": finding.get("title"),
            "first_seen": finding.get("first_seen"),
            "component": component,
            "lane": lane,
            "rule": rule_id,
            "reason": reason,
            "remediation": remediation,
        })
    return results


# --- finding store -----------------------------------------------------------

# ── plan-or-page (P2.2) ──────────────────────────────────────────────────────
# "Routed to PLAN" used to be where the guarantee quietly ended: the lane was
# assigned, rule 4e's prose said "dispatch a planner", and whether a plan file
# ever appeared was checked by nobody — criticals sat with lane=PLAN, no plan,
# no window, owned on paper and orphaned in fact (found 2026-08-26; the
# specifics live on the finding records, not here — public repo).
# This pass closes the loop the same way CRACK does — as data the
# sweep can assert on, with an SLA and a page, not as an instruction.

PLANS_DIR = Path(__file__).resolve().parent / "maintenance" / "plans"


def plans_by_finding_ref(plans_dir: Path | None = None) -> dict:
    """{finding_id: plan_filename} from every live plan's `finding_refs`.
    Executed/superseded plans do not count — their work is history, and a new
    finding on the same component needs a NEW plan (same rule coverage.py
    applies to version plans)."""
    import yaml  # noqa: PLC0415
    # resolved at CALL time, not def time — a def-time default freezes the
    # module-level path and silently ignores later rebinding (tests included)
    plans_dir = plans_dir or PLANS_DIR
    out = {}
    if not plans_dir.exists():
        return out
    for f in sorted(plans_dir.glob("*.md")):
        if f.name.lower() == "readme.md":
            continue
        try:
            fm = yaml.safe_load(f.read_text().split("---", 2)[1]) or {}
        except Exception:
            continue
        if str(fm.get("status") or "").strip() in ("executed", "superseded"):
            continue
        for ref in (fm.get("finding_refs") or []):
            out[str(ref)] = f.name
    return out


def plan_or_page(results: list, policy: dict, now=None) -> tuple[list, list]:
    """(needs_plan, overdue). Annotates PLAN-lane results with plan_file /
    age_days; anything past `plan_sla_days` with no plan is OVERDUE."""
    from datetime import datetime, timezone  # noqa: PLC0415
    now = now or datetime.now(timezone.utc)
    _sla = policy.get("plan_sla_days")
    # explicit None-check, NOT `or 4`: an SLA of 0 is a legitimate value (the
    # commissioning override) and `0 or 4` silently rewrites it to 4 — the
    # falsy-zero bug, same family as a shell's ${var:-0} turning "query failed"
    # into "zero jobs left".
    sla = 4.0 if _sla is None else float(_sla)
    refs = plans_by_finding_ref()
    needs, overdue = [], []
    for r in results:
        if r["lane"] != "PLAN":
            continue
        r["plan_file"] = refs.get(r["finding_id"])
        fs = r.get("first_seen")
        age = None
        if fs is not None:
            ts = fs if hasattr(fs, "tzinfo") else datetime.fromisoformat(str(fs))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            age = (now - ts).total_seconds() / 86400
        r["age_days"] = round(age, 1) if age is not None else None
        if not r["plan_file"]:
            needs.append(r)
            # unknown age counts as overdue: a finding we cannot age must not
            # get an implicit SLA extension
            if age is None or age > sla:
                overdue.append(r)
    return needs, overdue


def page_overdue(overdue: list) -> bool:
    """Best-effort OpenClaw page for overdue unplanned criticals. Loud on
    failure (returns False), never raises — a broken pager must not kill the
    triage run whose output the sweep still needs."""
    import subprocess  # noqa: PLC0415
    issues = [{
        "key": f"unplanned-{r['finding_id']}",
        "kind": "blocked_plan", "source": "maintenance", "severity": "critical",
        "title": (f"PLAN-lane critical {r['finding_id']} has NO PLAN after "
                  f"{r.get('age_days')}d (SLA breach): {(r.get('title') or '')[:100]}"),
        "action": "ack",
    } for r in overdue]
    try:
        p = subprocess.run(
            ["kubectl", "-n", "ai", "exec", "deploy/openclaw", "-c", "app", "--",
             "/home/node/.openclaw/bin/home-operation", "ingest", "--json",
             json.dumps(issues)],
            capture_output=True, text=True, timeout=60)
        return p.returncode == 0
    except Exception:
        return False


def fetch_open_criticals(severities: list) -> list:
    import psycopg  # noqa: PLC0415
    dsn = os.environ["SWEEP_PG_DSN"]
    with psycopg.connect(dsn, connect_timeout=10) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT finding_id, section, severity, title, status, action, metadata, first_seen
                FROM sweep_findings
                WHERE status <> 'resolved'
                  AND resolved_at IS NULL
                  AND severity = ANY(%s)
                ORDER BY first_seen
                """,
                (severities,),
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]


def record_lanes(results: list) -> int:
    """Write the lane back onto the finding.

    The lane belongs ON the finding rather than in a side report: `action` NULL
    is precisely what made frigate invisible, and a report nobody reads would
    reproduce that.
    """
    import psycopg  # noqa: PLC0415
    dsn = os.environ["SWEEP_PG_DSN"]
    written = 0
    with psycopg.connect(dsn, connect_timeout=10) as conn:
        with conn.cursor() as cur:
            for r in results:
                cur.execute(
                    """
                    UPDATE sweep_findings
                       SET action = %s,
                           metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb
                     WHERE finding_id = %s
                    """,
                    (
                        f"{r['lane']}: {r['reason']}"[:500],
                        json.dumps({
                            "triage_lane": r["lane"],
                            "triage_rule": r["rule"],
                            "triage_remediation": r["remediation"],
                        }),
                        r["finding_id"],
                    ),
                )
                written += cur.rowcount
        conn.commit()
    return written


# --- remediations ------------------------------------------------------------

def run_remediation(result: dict, repo_root: Path) -> dict:
    """Apply one registered recipe. Returns an outcome dict; never raises.

    Every recipe must be a git-visible edit. Nothing here touches the cluster
    directly — Flux reconciles, per the repository's GitOps rule — so a bad fix
    is caught in review or reverted with one commit.
    """
    recipe = result["remediation"]
    try:
        if recipe == "doc_count_sync":
            proc = subprocess.run(
                [sys.executable, str(repo_root / "runbooks" / "doc-check.py"), "--fix-counts"],
                capture_output=True, text=True, cwd=repo_root, timeout=600,
            )
            ok = proc.returncode == 0
            return {"applied": ok, "detail": (proc.stdout or proc.stderr)[-400:]}
        # add_prometheus_rule has no safe generic implementation: the rule body
        # depends entirely on the finding. It stays registered so the policy can
        # reference it, but it routes to a human until a generator exists.
        return {"applied": False,
                "detail": f"recipe '{recipe}' has no automated implementation yet"}
    except (subprocess.SubprocessError, OSError) as exc:
        return {"applied": False, "detail": f"{type(exc).__name__}: {exc}"}


# --- main --------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--severity", default="critical",
                        help="comma-separated severities to triage (default: critical)")
    parser.add_argument("--coverage-json",
                        help="output of `coverage.py --json` (file or literal), so findings "
                             "already owned by the update pipeline are marked COVERED")
    parser.add_argument("--record", action="store_true",
                        help="write the assigned lane back onto each finding")
    parser.add_argument("--apply-fixes", action="store_true",
                        help="run remediations for FIX_NOW findings (implies --record)")
    parser.add_argument("--plan-sla-days", type=float, default=None,
                        help="override the policy plan_sla_days (commissioning/tests)")
    parser.add_argument("--no-page", action="store_true",
                        help="suppress the OpenClaw page for overdue unplanned findings")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args()

    severities = [s.strip() for s in args.severity.split(",") if s.strip()]
    policy = load_policy()
    findings = fetch_open_criticals(severities)
    results = triage(findings, policy, covered_components(args.coverage_json))

    if args.apply_fixes:
        repo_root = Path(__file__).resolve().parent.parent
        for r in results:
            if r["lane"] == "FIX_NOW":
                r["fix"] = run_remediation(r, repo_root)
                if not r["fix"]["applied"]:
                    # An un-appliable auto-fix is not "done" — it needs a window
                    # like anything else, or it silently disappears.
                    r["lane"] = "PLAN"
                    r["reason"] = f"auto-fix unavailable: {r['fix']['detail']}"

    if args.record or args.apply_fixes:
        record_lanes(results)

    if args.plan_sla_days is not None:
        policy["plan_sla_days"] = args.plan_sla_days
    needs_plan, overdue = plan_or_page(results, policy)
    paged = None
    if overdue and not args.no_page:
        paged = page_overdue(overdue)

    counts = {lane: sum(1 for r in results if r["lane"] == lane) for lane in LANES}
    payload = {
        "policy_version": policy.get("version"),
        "policy_degraded": policy.get("_degraded"),
        "severities": severities,
        "total": len(results),
        "counts": counts,
        # The guarantee, stated as data so the sweep can assert on it.
        "no_cracks": counts["CRACK"] == 0,
        # PLAN-lane accountability: lane assignment is not plan existence.
        "needs_plan_findings": [r["finding_id"] for r in needs_plan],
        "overdue_unplanned": [r["finding_id"] for r in overdue],
        "overdue_paged": paged,
        "results": results,
    }

    if args.json:
        print(json.dumps(payload, indent=1, default=str))
    else:
        if policy.get("_degraded"):
            print(f"!! POLICY DEGRADED ({policy['_degraded']}) — everything routed to PLAN")
        print(f"open {'/'.join(severities)} findings: {len(results)}")
        print("lanes: " + "  ".join(f"{k}={v}" for k, v in counts.items()))
        for r in results:
            print(f"  [{r['lane']:<7}] {r['finding_id']}  {(r['title'] or '')[:88]}")
            print(f"            rule={r['rule']}  {(r['reason'] or '')[:110]}")
    if not args.json and overdue:
        print(f"!! OVERDUE UNPLANNED ({len(overdue)}): " +
              ", ".join(r["finding_id"] for r in overdue) +
              (f"  (paged={paged})" if paged is not None else "  (page suppressed)"))
    return 0 if (counts["CRACK"] == 0 and not overdue) else 1


if __name__ == "__main__":
    sys.exit(main())
