"""Regression tests for the supervised-run track record (autonomy-record.py).

GROUND TRUTH THIS EXISTS FOR — measured 2026-09-06:
`autonomy-policy.yaml` gates unattended execution on `first_runs_supervised: 2`
clean supervised runs per plan CATEGORY. The window agent was told to read that
from `window_runs` notes; no structured store existed; the documented fallback
is "when in doubt, treat as unsupervised". So the gate answered *no* forever and
the nightly window executed 0 plans across its first 7 runs while 8 plans
derived AUTO-*. The system wrote its own diagnosis into a window record nobody
read: "AUTO-NIGHT candidates grafana/unpoller also fail first_runs_supervised:2".

These tests pin the properties that make the gate answerable WITHOUT making it
permissive. A track record that only ever says "yes" is worse than the deadlock
it replaces.

A NOTE ON HOW THESE ARE WRITTEN
The first version of this file asserted that the fail-safe *strings* appeared in
the source. It passed while `cmd_eligible` raised TypeError on every single
invocation — `load_plans()` was called without its required argument, in the
exact path the tests claimed to cover. Grepping source is not testing behaviour.
The refusal logic is now a pure function and is executed here.

Run:  python3 runbooks/tests/test-autonomy-track-record.py
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("ar", REPO / "runbooks/autonomy-record.py")
ar = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ar)

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


def main() -> int:
    print("autonomy track record:")

    # ---- category derivation -------------------------------------------------
    # Keying on plan_id can never accumulate (plans are retired after they run),
    # and keying on kind alone lets a git-revert bump vouch for a
    # backup-restore one. The pair is the whole point.
    check("category pairs kind with execution class",
          ar.derive_category("image", "AUTO-NIGHT") == "image/AUTO-NIGHT",
          ar.derive_category("image", "AUTO-NIGHT"))
    check("same kind, different class => DIFFERENT categories",
          ar.derive_category("image", "AUTO-NIGHT")
          != ar.derive_category("image", "AUTO-BACKUP-GATED"),
          "a reversible image bump must not vouch for a backup-restore one")
    check("same class, different kind => DIFFERENT categories",
          ar.derive_category("image", "AUTO-NIGHT")
          != ar.derive_category("os", "AUTO-NIGHT"),
          "an image bump must not vouch for a node OS roll")
    check("missing kind does not collide with a real category",
          ar.derive_category(None, "AUTO-NIGHT") == "unknown/AUTO-NIGHT",
          ar.derive_category(None, "AUTO-NIGHT"))
    check("missing class defaults to the gated one",
          ar.derive_category("image", None) == "image/HUMAN-GATED",
          ar.derive_category("image", None))

    # ---- graduation arithmetic ----------------------------------------------
    # Only `green` counts. A reverted run is evidence the category is NOT ready;
    # counting it would let a category graduate on its own failures.
    check("only green counts as clean", ar.CLEAN_OUTCOME == "green", ar.CLEAN_OUTCOME)
    check("reverted/blocked are recognised outcomes, not silently dropped",
          {"blocked", "reverted", "aborted"} <= set(ar.VALID_OUTCOMES),
          str(ar.VALID_OUTCOMES))
    check("threshold is readable from the live policy",
          (t := ar.load_policy()) is not None and t >= 1, f"got {ar.load_policy()!r}")

    # ---- the refusal logic, EXECUTED ----------------------------------------
    ok, why = ar.eligibility_verdict("scheduled", "AUTO-NIGHT", 2, 2, True)
    check("graduated auto plan IS eligible", ok is True, why)

    ok, why = ar.eligibility_verdict("scheduled", "AUTO-NIGHT", 2, 1, True)
    check("one clean run short => denied", ok is False, why)

    ok, why = ar.eligibility_verdict("scheduled", "AUTO-NIGHT", 2, 5, False)
    check("unreadable track record denies even with runs on record",
          ok is False and "denied, not assumed" in why, why)

    ok, why = ar.eligibility_verdict("scheduled", "AUTO-NIGHT", None, 9, True)
    check("unreadable policy denies", ok is False and "fail-safe" in why, why)

    ok, why = ar.eligibility_verdict("scheduled", "HUMAN-GATED", 2, 9, True)
    check("human-gated is never eligible, whatever the record",
          ok is False and "not auto-executable" in why, why)

    # The check that caught a real gap: the class derivation reads declared
    # facts and never looks at status, so paperless-db — BLOCKED that same day
    # because its premise would have dropped an integrity check from the
    # document library's dump — still derived AUTO-BACKUP-GATED. Only
    # `window: null` was keeping it out of an auto lane, and that is not a
    # control.
    for dead in ("blocked", "executed", "superseded"):
        ok, why = ar.eligibility_verdict(dead, "AUTO-NIGHT", 2, 99, True)
        check(f"status {dead!r} is never eligible, whatever the class or record",
              ok is False and dead in why, why)

    # ---- supervision cannot be self-awarded ---------------------------------
    src = (REPO / "runbooks/autonomy-record.py").read_text()
    check("supervision is an explicit recorded flag, not derived from the slot",
          "--supervised" in src and 'action="store_true"' in src
          and "slot.startswith" not in src,
          "supervision must not be inferred from window naming")

    # ---- commissioning ------------------------------------------------------
    # A validator that only ever passes is indistinguishable from no validator.
    # Every refusal above must be reachable, and the happy path must exist too.
    happy, _ = ar.eligibility_verdict("scheduled", "AUTO-NIGHT", 1, 1, True)
    denied, _ = ar.eligibility_verdict("scheduled", "AUTO-NIGHT", 1, 0, True)
    check("rule discriminates (same inputs but one run apart flip the verdict)",
          happy is True and denied is False, f"{happy}/{denied}")

    print()
    if FAILURES:
        print(f"FAILED ({len(FAILURES)}): {', '.join(FAILURES)}")
        return 1
    print("all autonomy track-record tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
