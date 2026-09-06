"""Regression tests for `policy-cli risk lint` classification.

GROUND TRUTH (2026-09-06). The AR register held 101 enabled acceptances. 29 of
them had NEVER matched a single finding — open or resolved — because their
descriptions were written as PROSE ("Headlamp cluster-admin ClusterRoleBinding")
rather than as the substring needle the suppressor actually matches against.

They passed both existing lint signals. `at risk` needs a volatile token in a
WORKING description; `DRIFTING NOW` needs a shorter prefix that still matches.
A description that never matched anything at any prefix trips neither, so 29
entries sat in the register reading as accepted policy while suppressing
nothing. AR-016 was one of them, inert since 2026-05-27, and it only surfaced
because a finding it was meant to cover came up for triage by hand.

An inert AR is worse than useless: the register is what the operator reads to
answer "what have we accepted", so it asserts something is handled when it is
not.

Run:  python3 runbooks/tests/test-ar-lint-inert.py
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("pc", REPO / "runbooks/policy-cli.py")
pc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pc)

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


MISS = ("some prefix", "F-abc", "a finding title")


def main() -> int:
    print("AR lint classification:")

    # ---- the signal this file exists for ------------------------------------
    check("never matched anything, ever -> INERT",
          pc.lint_flag(0, [], None, 0) == "INERT")

    # THE distinction that makes it safe to act on. An AR whose finding is
    # currently RESOLVED is doing its job and waiting; flagging it would push
    # the operator to retire a working acceptance.
    check("matches a RESOLVED finding only -> not INERT (dormant, not dead)",
          pc.lint_flag(0, [], None, 1) != "INERT",
          pc.lint_flag(0, [], None, 1))

    # ---- precedence, which is the part that is easy to get backwards --------
    check("INERT outranks 'at risk' (a description that never worked is not "
          "'about to drift')",
          pc.lint_flag(0, ["patch version"], None, 0) == "INERT")
    check("DRIFTING NOW outranks 'at risk' (drift already happened)",
          pc.lint_flag(0, ["patch version"], MISS, 1) == "DRIFTING NOW")
    check("a near-miss is never reported as INERT — a matching prefix proves "
          "the description DID work",
          pc.lint_flag(0, [], MISS, 0) == "DRIFTING NOW",
          pc.lint_flag(0, [], MISS, 0))

    # ---- the healthy cases must stay quiet ---------------------------------
    check("matching and stable -> ok", pc.lint_flag(3, [], None, 5) == "ok")
    check("matching but volatile -> at risk",
          pc.lint_flag(3, ["contains a patch-level version"], None, 5) == "at risk")

    # ---- discrimination -----------------------------------------------------
    # A classifier that returned one verdict would satisfy any single case
    # above; require that all four are reachable.
    verdicts = {
        pc.lint_flag(0, [], None, 0),
        pc.lint_flag(0, [], MISS, 1),
        pc.lint_flag(3, ["v"], None, 5),
        pc.lint_flag(3, [], None, 5),
    }
    check("all four verdicts are reachable (the rule is not constant)",
          verdicts == {"INERT", "DRIFTING NOW", "at risk", "ok"}, str(sorted(verdicts)))

    print()
    if FAILURES:
        print(f"FAILED ({len(FAILURES)}): {', '.join(FAILURES)}")
        return 1
    print("all AR-lint tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
