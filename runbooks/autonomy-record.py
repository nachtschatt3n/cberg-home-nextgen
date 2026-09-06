#!/usr/bin/env python3
"""autonomy-record — the track record behind `first_runs_supervised`.

WHY THIS EXISTS
`runbooks/autonomy-policy.yaml` gates unattended execution on a plan CATEGORY
having N clean SUPERVISED runs. The window agent was told to read that from
`window_runs` notes. Nothing structured was ever written there, and the
documented fallback is "when in doubt, treat as unsupervised" — so the gate
answered *no* every single time. Measured 2026-09-06: the nightly window had
executed 0 plans across its first 7 runs while 8 plans derived AUTO-*.

That is not a policy disagreement. It is a gate with no key.

THE CATEGORY IS DERIVED, NEVER DECLARED
    category = "<plan_kind>/<execution_class>"     e.g. "image/AUTO-NIGHT"

Keying on `plan_id` could never accumulate: plans are one-shot and retired once
they execute, which is exactly why nothing graduated. Keying on `kind` alone
would let a git-revert image bump vouch for a backup-restore one — different
recovery story, same word. Pairing kind with the derived execution class keeps
the cohort homogeneous in the property autonomy actually turns on:
reversibility.

A plan can no more choose its category than it can choose its execution class.

SUPERVISED IS RECORDED, NOT INFERRED
`supervised` means a human could have intervened — an attended window, or an
unattended one explicitly babysat. It is written by the caller at close-out and
never derived from the slot name, so an unattended cron run can never quietly
promote itself into supervision by running in a window that happens to be
labelled attended.

USAGE
    # at window close-out, once per plan executed
    autonomy-record.py record --plan-id grafana-13.0.0 --kind chart \\
        --class AUTO-NIGHT --slot sat-attended --run-date 2026-09-06 \\
        --supervised --outcome green --notes "operator present"

    # the graduation question, for one category or all of them
    autonomy-record.py track-record --category image/AUTO-NIGHT
    autonomy-record.py track-record --json

    # would THIS plan be allowed to run unattended tonight?
    autonomy-record.py eligible --plan-id edot-collector-0.160.0 --json

Reads SWEEP_PG_DSN (see runbooks/lib/sweep-pg-dsn.sh). Without it, every query
returns `verified: false` and eligibility is DENIED — an unreadable ledger must
never read as permission. That is the same failure this tool exists to fix, so
it does not get to reappear here.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
VALID_CLASSES = ("AUTO-NIGHT", "AUTO-BACKUP-GATED", "HUMAN-GATED")
VALID_OUTCOMES = ("green", "blocked", "reverted", "aborted")

# Only a CLEAN run counts toward graduation. A blocked or reverted run is
# evidence the category is NOT ready, so it must not be quietly ignored — it is
# counted separately and reported, because "2 clean out of 2" and "2 clean out
# of 5" are very different track records and the second should give pause.
CLEAN_OUTCOME = "green"


def derive_category(plan_kind: str, execution_class: str) -> str:
    """The one place the category string is built. Pure, so it is testable and
    so a caller cannot invent a category by writing a different string."""
    return f"{(plan_kind or 'unknown').strip()}/{(execution_class or 'HUMAN-GATED').strip()}"


def load_policy():
    """first_runs_supervised, or None if the policy is unreadable.

    Fail-safe: an unreadable policy means we cannot know the threshold, and the
    answer to "may this run unattended" is then no."""
    try:
        import yaml
        d = yaml.safe_load((SCRIPT_DIR / "autonomy-policy.yaml").read_text()) or {}
        n = d.get("first_runs_supervised")
        return int(n) if n is not None else None
    except Exception:
        return None


def _connect():
    dsn = os.environ.get("SWEEP_PG_DSN")
    if not dsn:
        return None
    try:
        import psycopg
        return psycopg.connect(dsn, connect_timeout=10)
    except Exception:
        return None


def cmd_record(args) -> int:
    if args.execution_class not in VALID_CLASSES:
        print(f"ERROR: --class must be one of {VALID_CLASSES}", file=sys.stderr)
        return 2
    if args.outcome not in VALID_OUTCOMES:
        print(f"ERROR: --outcome must be one of {VALID_OUTCOMES}", file=sys.stderr)
        return 2
    category = derive_category(args.kind, args.execution_class)
    conn = _connect()
    if conn is None:
        print("ERROR: SWEEP_PG_DSN unset or unreachable — execution NOT recorded.",
              file=sys.stderr)
        print("       source runbooks/lib/sweep-pg-dsn.sh && sweep_pg_dsn_up",
              file=sys.stderr)
        return 1
    with conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO plan_executions
                 (plan_id, category, execution_class, plan_kind, window_slot,
                  run_date, supervised, outcome, notes)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (args.plan_id, category, args.execution_class, args.kind,
             args.slot, args.run_date, args.supervised, args.outcome,
             args.notes))
        rid = cur.fetchone()[0]
    print(json.dumps({"recorded": rid, "plan_id": args.plan_id,
                      "category": category, "supervised": args.supervised,
                      "outcome": args.outcome}))
    return 0


def _track_record(cur, category=None):
    q = """SELECT category,
                  count(*) FILTER (WHERE supervised AND outcome = %s) AS clean_supervised,
                  count(*) FILTER (WHERE supervised)                  AS supervised_total,
                  count(*)                                            AS runs_total,
                  max(run_date)                                       AS last_run
             FROM plan_executions {where}
            GROUP BY category ORDER BY category"""
    if category:
        cur.execute(q.format(where="WHERE category = %s"), (CLEAN_OUTCOME, category))
    else:
        cur.execute(q.format(where=""), (CLEAN_OUTCOME,))
    return [{"category": r[0], "clean_supervised": r[1], "supervised_total": r[2],
             "runs_total": r[3], "last_run": str(r[4]) if r[4] else None}
            for r in cur.fetchall()]


def cmd_track_record(args) -> int:
    threshold = load_policy()
    conn = _connect()
    if conn is None:
        out = {"verified": False, "threshold": threshold, "categories": [],
               "reason": "SWEEP_PG_DSN unset or unreachable — track record NOT checked"}
        print(json.dumps(out, indent=2) if args.json else
              "track record NOT VERIFIED (no DB access) — absence of rows here is "
              "not evidence a category is unproven, and must not be read as one")
        return 1
    with conn, conn.cursor() as cur:
        rows = _track_record(cur, args.category)
    for r in rows:
        r["graduated"] = (threshold is not None
                          and r["clean_supervised"] >= threshold)
    out = {"verified": True, "threshold": threshold, "categories": rows}
    if args.json:
        print(json.dumps(out, indent=2))
    else:
        if threshold is None:
            print("threshold UNKNOWN (autonomy-policy.yaml unreadable) — all denied")
        print(f"{'category':34} {'clean/sup':>10} {'total':>6}  graduated")
        for r in rows:
            print(f"{r['category']:34} "
                  f"{str(r['clean_supervised'])+'/'+str(r['supervised_total']):>10} "
                  f"{r['runs_total']:>6}  {'YES' if r['graduated'] else 'no'}")
        if not rows:
            print("(no plan executions recorded yet — every category is unproven)")
    return 0


# Statuses that mean "this plan must not execute", regardless of what its
# declared facts derive to. Discovered the hard way 2026-09-06: paperless-db was
# set `status: blocked` after its pre-check caught a premise that would have
# dropped an integrity check from the document library's dump — and it STILL
# derived AUTO-BACKUP-GATED, because the derivation reads facts and never looks
# at status. `blocked` is likewise absent from coverage.py's DEAD_PLAN_STATUSES.
# Only `window: null` was keeping it out of an auto lane, which is not a control.
DEAD_STATUSES = ("blocked", "executed", "superseded")


def eligibility_verdict(status, execution_class, threshold,
                        clean_supervised, verified):
    """(eligible, reason). Pure — no DB, no filesystem — so the refusals can be
    tested directly instead of inferred from the source text.

    Every unknown resolves to DENY. This tool exists because a gate that could
    not be answered defaulted to no; the mirror-image bug would be an
    unanswerable gate defaulting to yes."""
    if status in DEAD_STATUSES:
        return False, f"plan status is {status!r} — must not execute"
    if not str(execution_class or "").startswith("AUTO"):
        return False, "class is not auto-executable"
    if threshold is None:
        return False, "autonomy policy unreadable (fail-safe)"
    if not verified:
        return False, "track record unreadable — denied, not assumed"
    if clean_supervised >= threshold:
        return True, f"{clean_supervised} clean supervised run(s) of {threshold} required"
    return False, f"{clean_supervised} clean supervised run(s) of {threshold} required"


def cmd_eligible(args) -> int:
    """May this plan execute unattended tonight? Fail-safe in every direction."""
    sys.path.insert(0, str(SCRIPT_DIR))
    import importlib.util
    spec = importlib.util.spec_from_file_location("mp", SCRIPT_DIR / "maintenance-plan.py")
    mp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mp)

    plans = [p for p in mp.load_plans(mp.load_windows()) if p.get("plan_id") == args.plan_id]
    if not plans:
        print(json.dumps({"eligible": False, "reason": f"no plan {args.plan_id!r}"}))
        return 1
    plan = plans[0]
    policy = mp.load_autonomy_policy()
    klass, reason = mp.execution_class(plan, policy)
    threshold = load_policy()
    category = derive_category(plan.get("kind"), klass)

    status = str(plan.get("status") or "").strip()
    verdict = {"plan_id": args.plan_id, "category": category, "status": status,
               "execution_class": klass, "class_reason": reason,
               "threshold": threshold}

    clean, verified = 0, False
    # Only reach for the DB when the cheap, local refusals have not already
    # decided it — a blocked plan is not eligible whether or not Postgres is up.
    if status not in DEAD_STATUSES and str(klass).startswith("AUTO") and threshold is not None:
        conn = _connect()
        if conn is not None:
            with conn, conn.cursor() as cur:
                rows = _track_record(cur, category)
            clean = rows[0]["clean_supervised"] if rows else 0
            verified = True

    eligible, why = eligibility_verdict(status, klass, threshold, clean, verified)
    verdict.update(eligible=eligible, reason=why,
                   verified=verified, clean_supervised=clean)
    print(json.dumps(verdict, indent=2) if args.json else json.dumps(verdict))
    return 0 if verdict.get("eligible") else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("record", help="record one executed plan at window close-out")
    r.add_argument("--plan-id", required=True)
    r.add_argument("--kind", required=True, help="plan frontmatter `kind:` (image|chart|os|...)")
    r.add_argument("--class", dest="execution_class", required=True,
                   help=f"derived execution class, one of {VALID_CLASSES}")
    r.add_argument("--slot", required=True, help="window id, e.g. nightly")
    r.add_argument("--run-date", required=True, help="YYYY-MM-DD")
    r.add_argument("--supervised", action="store_true",
                   help="a human could have intervened (attended, or explicitly babysat)")
    r.add_argument("--outcome", required=True, help=f"one of {VALID_OUTCOMES}")
    r.add_argument("--notes")
    r.set_defaults(func=cmd_record)

    t = sub.add_parser("track-record", help="clean supervised runs per category")
    t.add_argument("--category")
    t.add_argument("--json", action="store_true")
    t.set_defaults(func=cmd_track_record)

    e = sub.add_parser("eligible", help="may this plan run unattended tonight?")
    e.add_argument("--plan-id", required=True)
    e.add_argument("--json", action="store_true")
    e.set_defaults(func=cmd_eligible)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
