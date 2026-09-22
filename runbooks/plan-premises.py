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
import os
import re
import shlex
import subprocess
import sys
import urllib.parse
import urllib.request
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


def unreadable_requested(plan_ids, load_errors) -> list[tuple[str, str]]:
    """[(plan_id, error)] for requested ids whose FILE exists but did not parse.

    `load_errors` is maintenance-plan.py's PLAN_LOAD_ERRORS ("<path>: <why>").
    Matched on the file stem (`.../<plan_id>.md`), which is how every plan file
    in this repo is named; a broken file that ALSO has a mismatched name is
    still reported by --validate, just not attributed to this id.
    """
    out = []
    for pid in plan_ids:
        for err in load_errors:
            path = err.split(":", 1)[0].strip()
            if path.endswith(f"/{pid}.md") or path == f"{pid}.md":
                out.append((pid, err))
    return out


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


# ---------------------------------------------------------------------------
# Authoring-time CONTROL check (F-ab84875b)
#
# A premise or a §4 gate that reads a metric or an alert PASSES LOUDEST when
# the instrument does not exist: an empty PromQL result is not an error, and
# an `alertname` matcher that matches nothing is not an error. The
# edot-collector plan's own negative control proved it (the identical pipeline
# pointed at a nonexistent metric printed INGEST_LOW — and only because the
# author had tested that it could). Until 2026-09-22 nothing here checked that
# a named instrument was real: `grep -c "alertname\|metric" plan-premises.py`
# read 0.
#
# This is an AUTHORING-TIME check (`--controls`), run by the reviewer on a
# draft. It is deliberately NOT part of the run-time premises gate: the
# scheduler's contract on this script's exit code is unchanged.
#
# What it reads:
#   * every `CONTROL: metric <name>` / `CONTROL: alertname <Name>` line in
#     the plan body (the line plans/README.md §4 now requires);
#   * every metric name inside a premise's PromQL (`query=` parameter,
#     `{__name__="…"}` matcher) and every `alertname` matcher, in `run:`;
#   * every `alertname` matcher anywhere in the body (a silence that names a
#     non-existent alert is inert).
# Body PromQL outside CONTROL lines is NOT harvested: bodies quote negative
# controls and examples, and flagging those would teach authors to stop
# writing them.
#
# Oracles — both injectable, both fail CLOSED:
#   * alert names: the repo's PrometheusRule manifests under kubernetes/
#     (git-tracked — the only source that is true at authoring time);
#   * metric names: the live Prometheus label index. No oracle → every metric
#     is UNVERIFIED and the check FAILS. "Could not confirm" is not "confirmed".
# ---------------------------------------------------------------------------

REPO_ROOT = SCRIPT_DIR.parent

CONTROL_LINE_RE = re.compile(
    r"^\s*(?:[-*>]\s*)*(?:\*\*)?CONTROL:(?:\*\*)?\s*(metric|alertname|alert)\s+"
    r"`?([A-Za-z_:][A-Za-z0-9_:.]*)`?", re.M | re.I)
_ALERTNAME_MATCHER_RE = re.compile(r'alertname\s*(?:=~|!~|!=|=)\s*["\']([^"\']+)["\']')
_ALERTNAME_JSON_RE = re.compile(
    r'"name"\s*:\s*"alertname"\s*,\s*"value"\s*:\s*"([^"]+)"')
_QUERY_PARAM_RE = re.compile(r'[?&]query=([^&\s\'"]+)')
_NAME_LABEL_RE = re.compile(r'__name__\s*(?:=~|=)\s*["\']([^"\']+)["\']')
_IDENT_RE = re.compile(r'(?<![A-Za-z0-9_:.])([A-Za-z_:][A-Za-z0-9_:.]*)')
_ALERT_ID_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')

# PromQL words that are never a metric name. Aggregators/functions are also
# excluded structurally (an identifier followed by `(`), so this list only
# has to carry the keyword-shaped ones.
PROMQL_WORDS = {
    "by", "without", "on", "ignoring", "group_left", "group_right", "bool",
    "offset", "and", "or", "unless", "inf", "nan", "NaN", "Inf", "true", "false",
    "s", "m", "h", "d", "w", "y", "ms",
}


def promql_metric_names(expr: str) -> set[str]:
    """The metric names an expression selects. Pure.

    Structural, not a parser: label matchers, string literals, range/offset
    brackets and `by/without/on/ignoring(...)` groups are blanked first (their
    contents are labels, not metrics); what remains and is not followed by `(`
    (a function or aggregator) and not a keyword is a metric selector. A
    `{__name__="…"}` matcher names its metric explicitly and is taken as-is,
    which is also how dotted OTel names travel."""
    expr = urllib.parse.unquote(str(expr or ""))
    names = {n for n in _NAME_LABEL_RE.findall(expr) if _IDENT_RE.fullmatch(n)}
    stripped = re.sub(r'\{[^}]*\}', ' ', expr)
    stripped = re.sub(r'"[^"]*"|\'[^\']*\'', ' ', stripped)
    stripped = re.sub(r'\[[^\]]*\]', ' ', stripped)
    stripped = re.sub(r'\b(by|without|on|ignoring|group_left|group_right)\s*\([^)]*\)',
                      ' ', stripped, flags=re.I)
    for m in _IDENT_RE.finditer(stripped):
        tok = m.group(1)
        if tok in PROMQL_WORDS:
            continue
        if stripped[m.end():].lstrip().startswith("("):
            continue                      # a call: sum(, rate(, increase(
        names.add(tok)
    return names


def alertnames_in(text: str) -> set[str]:
    """Every alert name a matcher in `text` names (PromQL `alertname="X"`,
    `alertname=~"A|B"`, or an Alertmanager silence JSON matcher). Regex
    alternatives are split; anchors stripped; only identifier-shaped names
    are kept (a `.*` is not an alert)."""
    out: set[str] = set()
    for raw in _ALERTNAME_MATCHER_RE.findall(text or "") + _ALERTNAME_JSON_RE.findall(text or ""):
        for part in str(raw).split("|"):
            part = part.strip().strip("^$").strip()
            if part and _ALERT_ID_RE.match(part):
                out.add(part)
    return out


def gate_names(plan: dict, body: str) -> dict:
    """{"metrics": {name: [sources]}, "alertnames": {name: [sources]},
    "control_lines": int} — every instrument the plan's gates name, with
    where each was named, so a miss is attributable."""
    metrics: dict = {}
    alerts: dict = {}

    def add(store, name, src):
        store.setdefault(name, [])
        if src not in store[name]:
            store[name].append(src)

    control_lines = 0
    for kind, name in CONTROL_LINE_RE.findall(body or ""):
        control_lines += 1
        if kind.lower() == "metric":
            add(metrics, name, "CONTROL line")
        else:
            add(alerts, name, "CONTROL line")
    for pr in plan.get("premises") or []:
        run = str((pr or {}).get("run") or "")
        src = f"premise {(pr or {}).get('id') or '<unnamed>'}"
        for q in _QUERY_PARAM_RE.findall(run):
            for n in promql_metric_names(q):
                add(metrics, n, src)
        for n in {n for n in _NAME_LABEL_RE.findall(run) if _IDENT_RE.fullmatch(n)}:
            add(metrics, n, src)
        for a in alertnames_in(run):
            add(alerts, a, src)
    for a in alertnames_in(body or ""):
        add(alerts, a, "body matcher")
    return {"metrics": metrics, "alertnames": alerts, "control_lines": control_lines}


def repo_alertnames(root: Path = REPO_ROOT) -> set[str]:
    """Alert names declared by PrometheusRule manifests under <root>/kubernetes.
    Git-tracked, so this is what is true at authoring time. Empty when none
    could be read — the caller treats that as UNVERIFIED, not as 'none exist'."""
    names: set[str] = set()
    base = Path(root) / "kubernetes"
    if not base.is_dir():
        return names
    for p in base.rglob("*.yaml"):
        try:
            text = p.read_text()
        except OSError:
            continue
        if "kind: PrometheusRule" not in text:
            continue
        for m in re.finditer(r'^\s*-?\s*alert:\s*["\']?([A-Za-z_][A-Za-z0-9_]*)', text, re.M):
            names.add(m.group(1))
    return names


def prom_metric_names(url: str, timeout: int = 20):
    """The live Prometheus `__name__` label index, or None when unreachable /
    not a success response. Impure; injected into check_controls()."""
    if not url:
        return None
    try:
        req = urllib.request.Request(f"{url.rstrip('/')}/api/v1/label/__name__/values",
                                     headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            doc = json.load(r)
    except Exception:  # noqa: BLE001 — any failure is "no oracle"
        return None
    if not isinstance(doc, dict) or doc.get("status") != "success":
        return None
    data = doc.get("data")
    return set(data) if isinstance(data, list) else None


def check_controls(plan: dict, body: str, alert_oracle, metric_oracle) -> dict:
    """Pure verdict over one plan. `alert_oracle`: set of declared alert names
    (empty = could not read any → UNVERIFIED). `metric_oracle`: set of live
    metric names, or None (no oracle → UNVERIFIED). UNVERIFIED FAILS."""
    names = gate_names(plan, body)
    results = []
    for a, srcs in sorted(names["alertnames"].items()):
        if not alert_oracle:
            passed, detail = False, ("UNVERIFIED — no PrometheusRule manifest could be "
                                     "read under kubernetes/")
        elif a in alert_oracle:
            passed, detail = True, "declared by a PrometheusRule manifest"
        else:
            passed, detail = False, ("NOT declared by any PrometheusRule manifest under "
                                     "kubernetes/ — a matcher on it matches nothing")
        results.append({"kind": "alertname", "name": a, "sources": srcs,
                        "passed": passed, "detail": detail})
    for mname, srcs in sorted(names["metrics"].items()):
        if metric_oracle is None:
            passed, detail = False, ("UNVERIFIED — no Prometheus oracle (pass --prom-url "
                                     "or set SLO_PROM_URL)")
        elif not metric_oracle:
            passed, detail = False, "UNVERIFIED — the Prometheus label index came back EMPTY"
        elif mname in metric_oracle:
            passed, detail = True, "present in the Prometheus label index"
        else:
            passed, detail = False, ("NOT in the Prometheus label index — a query on it "
                                     "returns an empty result, which is not an error")
        results.append({"kind": "metric", "name": mname, "sources": srcs,
                        "passed": passed, "detail": detail})
    problems = [f"{r['kind']} {r['name']}: {r['detail']}" for r in results if not r["passed"]]
    if names["control_lines"] == 0:
        problems.insert(0, "no CONTROL: line in the plan body — §4 names no instrument, "
                           "so it has no gate (plans/README.md §4)")
    return {
        "plan_id": plan.get("plan_id"),
        "status": plan.get("status"),
        "control_lines": names["control_lines"],
        "results": results,
        "problems": problems,
        "passed": not problems,
    }


def plan_body(plan: dict) -> str:
    """The plan file's body (everything after the frontmatter). Empty when
    the file cannot be read — which check_controls then reports as 'no
    CONTROL: line', the fail-closed reading."""
    rel = plan.get("_path")
    if not rel:
        return ""
    path = Path(rel)
    if not path.is_absolute():
        path = REPO_ROOT / rel
    try:
        text = path.read_text()
    except OSError:
        return ""
    parts = text.split("---", 2)
    return parts[2] if len(parts) == 3 else text


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
    ap.add_argument("--controls", action="store_true",
                    help="AUTHORING-TIME check: every metric / alertname a plan's gates "
                         "name (CONTROL: lines, premises PromQL, alertname matchers) must "
                         "exist — alerts in the repo's PrometheusRule manifests, metrics in "
                         "the live Prometheus label index. Unverifiable FAILS. Runs no premise.")
    ap.add_argument("--prom-url", default=os.environ.get("SLO_PROM_URL"),
                    help="Prometheus base URL for the metric oracle (default: $SLO_PROM_URL)")
    args = ap.parse_args()

    mp = _load("mp", "maintenance-plan.py")
    cfg = mp.load_windows()
    plans = mp.load_plans(cfg)
    load_errors = list(getattr(mp, "PLAN_LOAD_ERRORS", []))

    if args.controls:
        # Authoring-time instrument check (F-ab84875b). Separate branch on
        # purpose: it never runs a premise and never touches the run-time exit
        # contract the scheduler gates on.
        if args.plan_id:
            want = set(args.plan_id)
            unreadable = unreadable_requested(sorted(want), load_errors)
            selected = [p for p in plans if p.get("plan_id") in want]
            absent = sorted(pid for pid in want
                            if pid not in {p.get("plan_id") for p in selected}
                            and pid not in {u[0] for u in unreadable})
        elif args.window:
            unreadable, absent = [], []
            selected = [p for p in plans if p.get("window") == args.window]
        else:
            unreadable, absent = [], []
            terminal = tuple(getattr(mp, "TERMINAL_PLAN_STATUSES", ("executed", "superseded", "reference")))
            selected = [p for p in plans if str(p.get("status") or "") not in terminal]
        alert_oracle = repo_alertnames()
        metric_oracle = prom_metric_names(args.prom_url) if args.prom_url else None
        reports = [check_controls(p, plan_body(p), alert_oracle, metric_oracle) for p in selected]
        failed = bool(unreadable or absent) or any(not r["passed"] for r in reports)
        if args.json:
            print(json.dumps({"controls": reports, "ok": not failed,
                              "unreadable": [{"plan_id": p, "error": e} for p, e in unreadable],
                              "absent": absent,
                              "alert_oracle_size": len(alert_oracle),
                              "metric_oracle": (None if metric_oracle is None
                                                else len(metric_oracle))}, indent=2))
            return 1 if failed else 0
        for pid, err in unreadable:
            print(f"  UNREADABLE  {pid}  ({err})")
        for pid in absent:
            print(f"  ABSENT      {pid}  (no plan file)")
        if not reports and not failed:
            print("no matching plans")
            return 0
        print(f"  oracles: {len(alert_oracle)} alert name(s) from PrometheusRule manifests; "
              + ("no Prometheus metric oracle — every metric reads UNVERIFIED"
                 if metric_oracle is None else f"{len(metric_oracle)} metric name(s) from {args.prom_url}"))
        for r in reports:
            print(f"  {'PASS' if r['passed'] else 'FAIL':11} {r['plan_id']}  "
                  f"({r['control_lines']} CONTROL line(s), {len(r['results'])} instrument(s))")
            for p in r["problems"]:
                print(f"                 ✗ {p}")
        if failed:
            print("\nAt least one plan names an instrument that could not be confirmed to "
                  "exist, or names none. A gate on a nonexistent metric or alert passes "
                  "on an empty result — fix the plan before it is vetted.")
        return 1 if failed else 0

    if args.plan_id:
        want = set(args.plan_id)
        plans = [p for p in plans if p.get("plan_id") in want]
        # A plan named on the command line that the loader could not READ must
        # fail loudly, never fold into "no matching plans" (F-6a398b8b): the
        # window agent gates execution on this exit code, and a broken plan
        # that reads as absent is the plan-or-page gap in another shape. With
        # --require-premises a named plan with NO file at all fails too — a
        # typo in a plan id is not a pass.
        unreadable = unreadable_requested(sorted(want), load_errors)
        found = {p.get("plan_id") for p in plans}
        absent = sorted(pid for pid in want if pid not in found
                        and pid not in {u[0] for u in unreadable})
        if unreadable or (absent and args.require_premises):
            if args.json:
                print(json.dumps({"plans": [], "ok": False,
                                  "unreadable": [{"plan_id": p, "error": e} for p, e in unreadable],
                                  "absent": absent}, indent=2))
                return 1
            for pid, err in unreadable:
                print(f"  UNREADABLE  {pid}  ({err})")
            for pid in absent:
                print(f"  ABSENT      {pid}  (no plan file — with --require-premises this is a failure, not a pass)")
            return 1
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
