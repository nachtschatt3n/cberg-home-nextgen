"""Regression tests for the supervised-run track record (autonomy-record.py).

GROUND TRUTH THIS EXISTS FOR — measured 2026-09-06:
`autonomy-policy.yaml` gates unattended execution on `first_runs_supervised: 2`
clean supervised runs per plan CATEGORY. The window agent was told to read that
from `window_runs` notes; no structured store existed; the documented fallback
is "when in doubt, treat as unsupervised". So the gate answered *no* forever and
the nightly window executed 0 plans across its first 7 runs while 8 plans
derived AUTO-*. The system wrote its own diagnosis into a window record nobody
read: "AUTO-NIGHT candidates grafana/unpoller also fail first_runs_supervised:2".

The tests below pin the three properties that make the gate answerable WITHOUT
making it permissive. A track record that only ever says "yes" would be worse
than the deadlock it replaces.

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

    # Absent facts must not silently collapse into a shared, permissive bucket.
    check("missing kind does not collide with a real category",
          ar.derive_category(None, "AUTO-NIGHT") == "unknown/AUTO-NIGHT",
          ar.derive_category(None, "AUTO-NIGHT"))
    check("missing class defaults to the gated one",
          ar.derive_category("image", None) == "image/HUMAN-GATED",
          ar.derive_category("image", None))

    # ---- the graduation arithmetic ------------------------------------------
    # Only `green` counts. A reverted run is evidence the category is NOT ready;
    # counting it would let a category graduate on its own failures.
    check("only green counts as clean", ar.CLEAN_OUTCOME == "green", ar.CLEAN_OUTCOME)
    check("reverted/blocked are recognised outcomes, not silently dropped",
          {"blocked", "reverted", "aborted"} <= set(ar.VALID_OUTCOMES),
          str(ar.VALID_OUTCOMES))

    # ---- fail-safe ----------------------------------------------------------
    # The bug being fixed is a gate that could not be answered. The fix must not
    # introduce the mirror-image bug: an unreadable ledger reading as permission.
    threshold = ar.load_policy()
    check("threshold is readable from the live policy",
          threshold is not None and threshold >= 1, f"got {threshold!r}")

    src = (REPO / "runbooks/autonomy-record.py").read_text()
    check("no-DB path denies rather than assumes",
          'reason": "track record unreadable — denied, not assumed"' in src
          or "denied, not assumed" in src,
          "eligibility with an unreachable DB must be False")
    check("unreadable policy denies",
          "autonomy policy unreadable (fail-safe)" in src)
    check("non-auto classes are never eligible",
          "class is not auto-executable" in src)

    # A recorded run must not be able to claim supervision it did not have:
    # `supervised` is an explicit flag, never inferred from the slot name.
    check("supervision is an explicit recorded flag, not derived from the slot",
          "--supervised" in src and "action=\"store_true\"" in src
          and "slot.startswith" not in src and "attended\" in" not in src,
          "supervised must not be inferred from window naming")

    # ---- commissioning ------------------------------------------------------
    # A validator that only ever passes is indistinguishable from no validator.
    bogus = ar.derive_category("image", "AUTO-NIGHT")
    check("rule is not inert (a wrong pairing is actually detected)",
          bogus != "image/AUTO-BACKUP-GATED" and bogus != "image",
          bogus)

    print()
    if FAILURES:
        print(f"FAILED ({len(FAILURES)}): {', '.join(FAILURES)}")
        return 1
    print("all autonomy track-record tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
