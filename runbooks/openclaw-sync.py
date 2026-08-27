#!/usr/bin/env python3
"""openclaw-sync.py — ONE idempotent OpenClaw home-operation reconciler (P4.1.1).

Why this exists: three ingest paths lived only as instruction text in agent
briefs (daily-operation rules 4d/4e). A prompt-instructed ingest fails
SILENTLY when the orchestrating agent skips it, degrades, or times out — the
exact failure shape (a decision with no reminder, sitting forever) that rule
4e was written to kill, reintroduced one level up. This script is the same
migration `window-crons.py --check` made for cron parity: the prompt now
merely INVOKES a script that either syncs or fails loudly.

Three subjects, all glue over outputs the sweep has already produced:

  --plan-json      maintenance-plan.py --json   → awaiting-go plans as
                   go_no_go issues (source "maintenance") + reconcile over
                   open_issue_keys (EVERY non-terminal plan — scheduled plans
                   with a standing GO must NOT auto-close; see
                   maintenance-plan.py open_issue_keys comment). Also
                   reconciles legacy source "maintenance-window".
  --triage-json    finding-triage.py --json     → DECIDE-lane findings as
                   go_no_go issues, source "triage".
  --coverage-json  coverage.py --json           → REBUILD-lane components as
                   14d-SLA task issues, source "rebuild".

SOURCE ISOLATION IS LOAD-BEARING. The old prompt contract told 4e to ingest
DECIDE findings under source "maintenance" — but 4d's reconcile over that
source uses PLAN ids as the open set, so every DECIDE issue would have been
auto-closed one sweep after it was opened. Each subject here gets its own
source and its own reconcile set; a subject whose input is ABSENT is skipped
entirely — including its reconcile, because reconciling against an empty set
that only reflects a missing input would close every open issue of that
source ("a coverage gap is not a fix").

Fail-safe: OpenClaw pod unreachable → one raw-Telegram fallback per failed
subject (lib/notify.py) + exit 2. A notification failure never crashes the
caller (fail-soft transport), but the EXIT CODE is loud so the sweep records
the sync as degraded instead of assuming it happened.

Usage (from the sweep / window close-out):
    .venv/bin/python3 runbooks/openclaw-sync.py \
        --plan-json /tmp/plan.json --triage-json /tmp/triage.json \
        --coverage-json /tmp/coverage.json
    # --dry-run prints the planned ingests/reconciles as JSON, execs nothing.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import notify  # noqa: E402  (ingest_issue, notify, _HOME_OP_EXEC)

REBUILD_SLA_DAYS = 14


# ── input loading ────────────────────────────────────────────────────────────

def _load(arg: str | None) -> dict | None:
    """File path or literal JSON; None if the argument was not given."""
    if not arg:
        return None
    p = Path(arg)
    text = p.read_text() if p.exists() else arg
    return json.loads(text)


# ── issue builders (the payload contract, in code instead of prose) ──────────

def plan_issues(plan_json: dict) -> tuple[list[dict], list[str]]:
    issues = [{
        "key": a["plan_id"],
        "kind": "go_no_go",
        "source": "maintenance",
        "severity": "warning",
        "action": "approve,deny,defer",
        "title": f"GO/NO-GO: {a.get('component') or a['plan_id']} → "
                 f"{a.get('target') or '?'} ({a.get('window') or 'unwindowed'})",
        "component": a.get("component"),
        "target": a.get("target"),
        "window": a.get("window"),
        "plan_path": a.get("plan"),
    } for a in plan_json.get("awaiting_go", []) if a.get("plan_id")]
    open_keys = [k for k in plan_json.get("open_issue_keys", []) if k]
    return issues, open_keys


def decide_issues(triage_json: dict) -> tuple[list[dict], list[str]]:
    rows = [r for r in triage_json.get("results", [])
            if (r.get("lane") or "").upper() == "DECIDE" and r.get("finding_id")]
    issues = [{
        "key": r["finding_id"],
        "kind": "go_no_go",
        "source": "triage",
        "severity": "warning",
        "action": "approve,deny,defer",
        "title": f"DECIDE: {(r.get('title') or r['finding_id'])[:140]}",
        "detail": (r.get("reason") or "")[:300],
    } for r in rows]
    return issues, [r["finding_id"] for r in rows]


def rebuild_issues(coverage_json: dict) -> tuple[list[dict], list[str]]:
    rows = [r for r in (coverage_json.get("lanes") or {}).get("REBUILD", [])
            if r.get("component")]
    issues = [{
        "key": f"rebuild:{r['component']}",
        "kind": "finding",
        "source": "rebuild",
        "severity": "warning",
        "action": "ack",
        "title": f"REBUILD: {r['component']} {r.get('current') or '?'} → "
                 f"{r.get('target') or '?'} — rebuild in its source repo, "
                 f"then cberg-agent bumps the tag (SLA {REBUILD_SLA_DAYS}d)",
        "component": r.get("component"),
        "target": r.get("target"),
        "url": "docs/sops/self-built-image-rebuild.md",
    } for r in rows]
    return issues, [i["key"] for i in issues]


# ── transport ────────────────────────────────────────────────────────────────

def _reconcile(source: str, open_keys: list[str], dry: bool,
               log: list[dict]) -> bool:
    cmd = notify._HOME_OP_EXEC + ["reconcile", "--source", source,
                                  "--open", json.dumps(open_keys)]
    log.append({"op": "reconcile", "source": source, "open": open_keys})
    if dry:
        return True
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return p.returncode == 0
    except Exception as e:
        print(f"openclaw-sync: reconcile {source} failed ({e})", file=sys.stderr)
        return False


def sync_subject(name: str, issues: list[dict], sources_open: dict[str, list[str]],
                 dry: bool, log: list[dict]) -> bool:
    ok = True
    if issues:
        log.append({"op": "ingest", "subject": name, "issues": issues})
        if not dry and not notify.ingest_issue(issues):
            ok = False
    for source, open_keys in sources_open.items():
        if not _reconcile(source, open_keys, dry, log):
            ok = False
    if not ok and not dry:
        notify.notify(f"🔔 openclaw-sync: {name} sync FAILED — "
                      f"{len(issues)} issue(s) may lack reminders", urgent=False)
    return ok


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--plan-json", help="maintenance-plan.py --json (file or literal)")
    ap.add_argument("--triage-json", help="finding-triage.py --json (file or literal)")
    ap.add_argument("--coverage-json", help="coverage.py --json (file or literal)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print planned ingests/reconciles as JSON; exec nothing")
    args = ap.parse_args(argv)

    log: list[dict] = []
    failed, skipped = [], []

    plan = _load(args.plan_json)
    if plan is None:
        skipped.append("plans")
    else:
        issues, open_keys = plan_issues(plan)
        # legacy belt-and-suspenders: a stray emitter that used
        # "maintenance-window" must still get reconciled (rule 4d note)
        if not sync_subject("plans", issues,
                            {"maintenance": open_keys,
                             "maintenance-window": open_keys}, args.dry_run, log):
            failed.append("plans")

    triage = _load(args.triage_json)
    if triage is None:
        skipped.append("decide")
    else:
        issues, open_keys = decide_issues(triage)
        if not sync_subject("decide", issues, {"triage": open_keys},
                            args.dry_run, log):
            failed.append("decide")

    coverage = _load(args.coverage_json)
    if coverage is None:
        skipped.append("rebuild")
    else:
        issues, open_keys = rebuild_issues(coverage)
        if not sync_subject("rebuild", issues, {"rebuild": open_keys},
                            args.dry_run, log):
            failed.append("rebuild")

    out = {"dry_run": args.dry_run, "synced": log,
           "skipped": skipped, "failed": failed}
    print(json.dumps(out, indent=1))
    if failed:
        return 2          # loud: the sweep must record a degraded sync
    if len(skipped) == 3:
        print("openclaw-sync: no inputs given — nothing synced", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
