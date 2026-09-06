#!/usr/bin/env python3
"""plan-premises — check a maintenance plan's stated premises against reality.

WHY THIS EXISTS
Twice on 2026-09-06 a plan was caught MID-EXECUTION as a data-loss trap, both
times by a human reading the body at the last moment:

  * `paperclip-postgresql-18.6` would have mounted the PVC at a path
    postgres:18 no longer uses, so initdb and the restore would have landed in
    the container's ephemeral layer. version(), row counts and the application
    would ALL have passed, and the data would have vanished at the next pod
    restart (docs/sops/postgres-major-upgrade.md).
  * `paperless-db` rested on a utf8mb4 premise that would have dropped an
    integrity check from the document library's dump.

The recurring shape is not "the plan was wrong when written". It is that a plan
is written at time T, executed at T+days, and NOTHING re-checks whether what it
assumed is still true. A plan asserting its own premise in prose is not
evidence; it is the claim under test.

WHAT A PREMISE IS
A named, executable, READ-ONLY assertion in the plan's frontmatter:

    premises:
      - id: image-is-current
        why: "`current:` claims 0.158.0. If the cluster already moved, this
               plan is stale and its verification baseline is wrong."
        run: kubectl get deploy -n monitoring edot-collector -o jsonpath='{.spec.template.spec.containers[0].image}'
        expect_exact: otel/opentelemetry-collector-contrib:0.158.0

`expect_exact` (string equality, whitespace-stripped), `expect_contains`
(substring) or `expect_matches` (regex) — exactly one per premise.

THREE RULES THAT MAKE THIS WORTH HAVING

1. FAIL CLOSED. A premise whose command errors, times out, or returns nothing
   is a FAILURE, never a skip. The entire class of bug this guards against is
   "the check could not see, and silence was read as consent".

2. NO PREMISES IS "UNVERIFIED", NOT "PASS". A plan that declares none exits
   non-zero under --require-premises. Otherwise the field is optional, nobody
   adds it, and nothing changes.

3. READ-ONLY BY CONSTRUCTION. Commands are matched against an allowlist of
   read verbs before anything runs. This is the same G4 boundary
   autonomy-policy.yaml already draws: plan files are reviewed, but a premise
   is still free text, and free text must never be able to select an action.
   A premise that mutates is a config error and refuses to run.

    plan-premises.py --all                  # every plan that declares premises
    plan-premises.py edot-collector-0.160.0
    plan-premises.py --window sat-attended:2026-09-12 --require-premises
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

# Read verbs only. A premise exists to OBSERVE the world; anything that can
# change it does not belong in a precondition, and a plan that needs a mutation
# to establish its premise is a plan whose premise is wrong.
ALLOWED = {
    "kubectl": {"get", "describe", "logs", "top", "version", "api-resources",
                "explain", "cluster-info", "auth"},
    "flux": {"get", "check", "stats", "diff"},
    "talosctl": {"get", "version", "read", "list", "df", "health", "dmesg"},
    "helm": {"get", "list", "status", "show", "history"},
    "git": {"log", "show", "status", "diff", "rev-parse", "ls-files"},
}
# Argv-0 commands with no subcommand, safe in full.
ALLOWED_BARE = {"grep", "sed", "awk", "head", "tail", "wc", "cut", "sort",
                "uniq", "tr", "jq", "cat", "echo", "test", "true", "false"}

# Explicitly refused even though the parent verb might look read-only.
DENY_FLAGS = {"--watch", "-w", "--follow", "-f"}   # would never terminate

EXPECT_KINDS = ("expect_exact", "expect_contains", "expect_matches")


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, SCRIPT_DIR / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def command_is_readonly(cmd: str) -> tuple[bool, str]:
    """(ok, reason). Every pipeline stage must independently be a read verb.

    Conservative on purpose: anything unparseable is refused rather than
    guessed at. A premise that cannot be proven read-only does not run.
    """
    if not str(cmd or "").strip():
        return False, "empty command"
    # Refuse the shell metacharacters that make static analysis meaningless.
    for bad in (";", "&&", "||", "`", "$(", ">", ">>", "&"):
        if bad in cmd:
            return False, f"command contains {bad!r} — premises must be a simple pipeline"
    for stage in cmd.split("|"):
        try:
            parts = shlex.split(stage)
        except ValueError as e:
            return False, f"unparseable stage {stage.strip()!r}: {e}"
        if not parts:
            return False, "empty pipeline stage"
        argv0 = Path(parts[0]).name
        flags = {p for p in parts if p.startswith("-")}
        if flags & DENY_FLAGS:
            return False, f"{argv0}: watch/follow flags never terminate"
        if argv0 in ALLOWED_BARE:
            continue
        if argv0 not in ALLOWED:
            return False, f"{argv0!r} is not an allowed read command"
        sub = next((p for p in parts[1:] if not p.startswith("-")), None)
        if sub not in ALLOWED[argv0]:
            return False, f"{argv0} {sub!r} is not a read-only subcommand"
    return True, "read-only"


def evaluate(premise: dict, output: str) -> tuple[bool, str]:
    """(passed, detail). Pure — the whole point is that this is testable."""
    kinds = [k for k in EXPECT_KINDS if premise.get(k) is not None]
    if len(kinds) != 1:
        return False, (f"premise must declare exactly one of {', '.join(EXPECT_KINDS)}"
                       f" (found {len(kinds)})")
    kind = kinds[0]
    want = str(premise[kind])
    got = (output or "").strip()
    if not got:
        # Fail closed. An empty result is the signature of a selector that
        # matched nothing, and that must never read as agreement.
        return False, f"command produced NO output — cannot satisfy {kind}={want!r}"
    if kind == "expect_exact":
        return got == want, f"got {got!r}, want exactly {want!r}"
    if kind == "expect_contains":
        return want in got, f"got {got!r}, want it to contain {want!r}"
    try:
        return bool(re.search(want, got)), f"got {got!r}, want match /{want}/"
    except re.error as e:
        return False, f"bad regex {want!r}: {e}"


def run_premise(premise: dict, timeout: int = 60) -> dict:
    pid = premise.get("id") or "<unnamed>"
    cmd = premise.get("run") or ""
    ok, why = command_is_readonly(cmd)
    if not ok:
        return {"id": pid, "passed": False, "detail": f"REFUSED: {why}", "ran": False}
    try:
        p = subprocess.run(["bash", "-o", "pipefail", "-c", cmd],
                           capture_output=True, text=True, timeout=timeout)
        out = p.stdout
        if p.returncode != 0 and not out.strip():
            return {"id": pid, "passed": False, "ran": True,
                    "detail": f"command failed (rc={p.returncode}): "
                              f"{(p.stderr or '').strip()[:200]}"}
    except subprocess.TimeoutExpired:
        return {"id": pid, "passed": False, "ran": True,
                "detail": f"timed out after {timeout}s"}
    except Exception as e:  # noqa: BLE001
        return {"id": pid, "passed": False, "ran": True, "detail": f"{type(e).__name__}: {e}"}
    passed, detail = evaluate(premise, out)
    return {"id": pid, "passed": passed, "ran": True, "detail": detail}


def check_plan(plan: dict, timeout: int = 60) -> dict:
    premises = plan.get("premises") or []
    results = [run_premise(p, timeout) for p in premises]
    return {
        "plan_id": plan.get("plan_id"),
        "status": plan.get("status"),
        "window": plan.get("window"),
        "declared": len(premises),
        "results": results,
        "passed": bool(premises) and all(r["passed"] for r in results),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plan_id", nargs="*", help="plan ids (default: all with premises)")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--window", help="only plans assigned to this window slot")
    ap.add_argument("--require-premises", action="store_true",
                    help="a plan declaring NO premises is a failure, not a pass")
    ap.add_argument("--timeout", type=int, default=60)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    mp = _load("mp", "maintenance-plan.py")
    cfg = mp.load_windows()
    plans = mp.load_plans(cfg)

    if args.plan_id:
        want = set(args.plan_id)
        plans = [p for p in plans if p.get("plan_id") in want]
    elif args.window:
        plans = [p for p in plans if p.get("window") == args.window]
    elif not args.all:
        plans = [p for p in plans if p.get("premises")]

    reports, failed = [], False
    for plan in plans:
        r = check_plan(plan, args.timeout)
        reports.append(r)
        if r["declared"] == 0:
            if args.require_premises:
                failed = True
        elif not r["passed"]:
            failed = True

    if args.json:
        print(json.dumps({"plans": reports, "ok": not failed}, indent=2))
        return 1 if failed else 0

    if not reports:
        print("no matching plans")
        return 0
    for r in reports:
        if r["declared"] == 0:
            mark = "UNVERIFIED" if args.require_premises else "no premises"
            print(f"  {mark:11} {r['plan_id']}  (declares none — its assumptions "
                  f"are unchecked)")
            continue
        print(f"  {'PASS' if r['passed'] else 'FAIL':11} {r['plan_id']}  "
              f"({r['declared']} premise(s))")
        for x in r["results"]:
            if not x["passed"]:
                print(f"                 ✗ {x['id']}: {x['detail']}")
    if failed:
        print("\nAt least one premise failed or is undeclared. A plan whose premises "
              "no longer hold must NOT execute — re-plan it instead.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
