"""Regression tests for plan-premises.py — the thing that re-checks a plan's
assumptions at execution time instead of trusting its prose.

WHY THIS EXISTS. Twice on 2026-09-06 a plan was caught mid-execution as a
data-loss trap, both times by a human reading the body at the last moment
(paperclip PG18's PGDATA relocation; paperless-db's utf8mb4 premise). Neither
failure was "the plan was wrong when written" — both were "the plan was written
at time T and executed at T+days with nothing re-checking it".

The two halves that must both hold, and which fail in opposite directions:

  1. it must actually CATCH a stale premise, including the silent shapes —
     empty output, a command that errors, a selector that matched nothing;
  2. it must REFUSE to run anything that could change the world, because a
     premise is free text in a file and free text must never select an action
     (the G4 boundary autonomy-policy.yaml already draws).

Run:  python3 runbooks/tests/test-plan-premises.py
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("pp", REPO / "runbooks/plan-premises.py")
pp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pp)

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


def ro(cmd):
    return pp.command_is_readonly(cmd)[0]


def main() -> int:
    print("plan premises:")

    # ---- the read-only boundary ---------------------------------------------
    check("a plain kubectl get is allowed",
          ro("kubectl get deploy -n monitoring edot-collector -o jsonpath='{.spec}'"))
    check("a read pipeline is allowed",
          ro("kubectl get pods -n security | grep wazuh | wc -l"))

    for bad, why in [
        ("kubectl delete pvc foo -n bar",        "delete"),
        ("kubectl apply -f x.yaml",              "apply"),
        ("kubectl patch deploy x -p '{}'",       "patch"),
        ("kubectl scale deploy x --replicas=0",  "scale"),
        ("kubectl exec -n a pod -- rm -rf /",    "exec"),
        ("flux reconcile source git flux-system", "reconcile"),
        ("helm upgrade x y",                     "helm upgrade"),
        ("talosctl reboot",                      "reboot"),
        ("rm -rf /data",                         "rm is not allowlisted"),
    ]:
        check(f"REFUSES a mutating command ({why})", not ro(bad), bad)

    # Shell metacharacters defeat static analysis, so they are refused outright
    # rather than parsed heroically — a premise is a one-liner, not a program.
    for bad in ("kubectl get pods; kubectl delete pod x",
                "kubectl get pods && rm -rf /",
                "kubectl get pods > /etc/passwd",
                "echo $(kubectl delete pod x)",
                "kubectl get pods `rm -rf /`"):
        check(f"REFUSES shell metacharacters: {bad[:34]!r}", not ro(bad))

    check("REFUSES --watch (would never terminate)",
          not ro("kubectl get pods --watch"))
    check("REFUSES logs -f", not ro("kubectl logs -f -n a pod"))
    check("REFUSES an empty command", not ro(""))
    check("REFUSES an unparseable command", not ro("kubectl get 'unclosed"))

    # ---- evaluation, including the silent-failure shapes ---------------------
    P = {"id": "t", "expect_exact": "v1.13.10"}
    check("expect_exact matches, ignoring surrounding whitespace",
          pp.evaluate(P, "  v1.13.10\n")[0])
    check("expect_exact rejects a near miss",
          not pp.evaluate(P, "v1.13.1")[0])

    check("expect_contains matches a substring",
          pp.evaluate({"id": "t", "expect_contains": "18.6"},
                      "postgres:18.6-alpine")[0])
    check("expect_matches applies a regex",
          pp.evaluate({"id": "t", "expect_matches": r"^otel/.*:0\.158\.0$"},
                      "otel/opentelemetry-collector-contrib:0.158.0")[0])

    # THE failure mode this tool exists for: a check that could not see must
    # never read as agreement.
    check("EMPTY output fails, it does not pass",
          not pp.evaluate(P, "")[0], str(pp.evaluate(P, "")))
    check("whitespace-only output fails",
          not pp.evaluate(P, "   \n  ")[0])
    check("the empty-output failure SAYS so, so it is diagnosable",
          "NO output" in pp.evaluate(P, "")[1], pp.evaluate(P, "")[1])

    # A malformed premise is a failure, not a silent skip.
    check("a premise declaring NO expectation fails",
          not pp.evaluate({"id": "t"}, "anything")[0])
    check("a premise declaring TWO expectations fails (ambiguous)",
          not pp.evaluate({"id": "t", "expect_exact": "a",
                           "expect_contains": "b"}, "a")[0])
    check("a bad regex fails closed rather than raising",
          not pp.evaluate({"id": "t", "expect_matches": "([unclosed"}, "x")[0])

    # ---- end to end, without touching a cluster ------------------------------
    ok = pp.run_premise({"id": "echo-ok", "run": "echo v1.13.10",
                         "expect_exact": "v1.13.10"})
    check("a satisfied premise passes end to end", ok["passed"], str(ok))

    stale = pp.run_premise({"id": "echo-stale", "run": "echo v1.13.7",
                            "expect_exact": "v1.13.10"})
    check("a STALE premise is caught end to end", not stale["passed"], str(stale))

    refused = pp.run_premise({"id": "nope", "run": "kubectl delete pod x",
                              "expect_exact": "x"})
    check("a mutating premise is refused WITHOUT running",
          not refused["passed"] and refused["ran"] is False
          and "REFUSED" in refused["detail"], str(refused))

    empty = pp.run_premise({"id": "empty", "run": "echo -n ''",
                            "expect_contains": "anything"})
    check("a command matching nothing fails (the selector-matched-zero shape)",
          not empty["passed"], str(empty))

    failing = pp.run_premise({"id": "rc", "run": "test -f /nonexistent-xyz",
                              "expect_contains": "x"})
    check("a non-zero exit with no output fails", not failing["passed"], str(failing))

    # ---- plan-level ----------------------------------------------------------
    none_declared = pp.check_plan({"plan_id": "bare"})
    check("a plan with NO premises does not report passed",
          none_declared["passed"] is False and none_declared["declared"] == 0,
          str(none_declared))

    good = pp.check_plan({"plan_id": "p", "premises": [
        {"id": "a", "run": "echo 1", "expect_exact": "1"},
        {"id": "b", "run": "echo 2", "expect_exact": "2"}]})
    check("a plan whose premises all hold passes", good["passed"], str(good))

    mixed = pp.check_plan({"plan_id": "p", "premises": [
        {"id": "a", "run": "echo 1", "expect_exact": "1"},
        {"id": "b", "run": "echo 2", "expect_exact": "999"}]})
    check("ONE failed premise fails the whole plan", not mixed["passed"])

    # ---- commissioning -------------------------------------------------------
    # A checker that always fails would pass every refusal test above; one that
    # always passes would pass every acceptance test. Both must be excluded.
    check("rule discriminates (same shape, one char apart, flips the verdict)",
          pp.run_premise({"id": "x", "run": "echo abc", "expect_exact": "abc"})["passed"]
          and not pp.run_premise({"id": "x", "run": "echo abc",
                                  "expect_exact": "abd"})["passed"])

    print()
    if FAILURES:
        print(f"FAILED ({len(FAILURES)}): {', '.join(FAILURES)}")
        return 1
    print("all plan-premises tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
