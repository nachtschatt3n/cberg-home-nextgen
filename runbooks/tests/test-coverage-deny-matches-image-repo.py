"""Regression test: a deny rule must reach the lane that would act on it
(F-7bad8aeb, 2026-09-21).

CLAUDE.md documents one procedure for holding a component back: "add a deny rule
to the policy YAML". Whether that rule fires depends on which NAME the caller
hands `deny_rule_for()`, and the two lanes hand it different ones:

  auto-update.py  PR gate      policy_block(policy, parsed['dep'], utype)
                               -> the Renovate depName, e.g. valkey/valkey
  coverage.py     direct-bump  denied(policy, key, utype) from assign_lane and
                               max_rule_fallbacks, where key is the COMPONENT

So a rule written against an image repository blocked the PR path and was
silently inert in the direct-bump lane — the one an unattended nightly applies.
Measured before the fix: denied(policy, 'penpot-cache', 'minor') was None while
denied(policy, 'valkey/valkey', 'minor') returned the rule's reason.

THE FIXTURE IS SYNTHETIC ON PURPOSE. An earlier draft of this test asserted
against the live auto-update-policy.yaml, which would make it fail the day the
interim valkey rule is correctly retired — that rule carries its own removal
condition. A test that breaks when the repo does the right thing is worse than
no test, so the policy here is built inline.

THE SAFETY PROPERTY, pinned below: repo-aware matching can only ever FIND a rule
where none was found before, so it can only move work OUT of the unattended
lane. It must never be able to unblock something the component match already
blocked.

Run:  python3 runbooks/tests/test-coverage-deny-matches-image-repo.py
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
os.environ.setdefault("_MISE_ACTIVATED", "1")
sys.path.insert(0, str(_REPO / "runbooks"))
_spec = importlib.util.spec_from_file_location(
    "coverage_under_test", _REPO / "runbooks" / "coverage.py")
_cov = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cov)

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


# A policy shaped like the real one, but owned by this test.
POLICY = {
    "deny": [
        {"match": "*valkey*", "reason": "held: only newer tag is a pre-release"},
        {"match": "*cilium*", "reason": "CNI datapath — never an unattended bump"},
        {"match": "*app-template*", "max": "patch", "reason": "breaking chart migration"},
    ]
}

# The live shape that motivated the finding: component and image disagree.
PENPOT = {"component": "penpot-cache", "kind": "image", "namespace": "office",
          "current": "9.1.2", "target": "9.2", "type": "minor",
          "image_repo": "valkey/valkey", "image_repos": ["valkey/valkey"]}

# Component itself matches a rule — must behave exactly as before.
CILIUM = {"component": "cilium", "kind": "chart", "namespace": "kube-system",
          "current": "1.20.1", "target": "1.20.2", "type": "patch",
          "image_repos": ["quay.io/cilium/cilium"]}

# Neither component nor repo matches anything.
MEMGRAPH = {"component": "memgraph", "kind": "image", "namespace": "databases",
            "current": "3.13.1", "target": "3.13.2", "type": "patch",
            "image_repo": "memgraph/lab", "image_repos": ["memgraph/lab"]}

# An item with no image repositories at all (a chart row).
NOREPO = {"component": "penpot-cache", "kind": "chart", "namespace": "office",
          "current": "1.0.0", "target": "1.1.0", "type": "minor"}

# COMPONENT matches a rule, and NO repo does. Without this fixture the superset
# property below is asserted but never exercised: CILIUM and the app-template
# row each match by component AND by repo, so dropping the component arm
# entirely would still find a rule through the repo arm and every check would
# stay green. This is the item that makes that mutation fail.
COMP_ONLY = {"component": "cilium", "kind": "chart", "namespace": "kube-system",
             "current": "1.20.1", "target": "1.20.2", "type": "patch",
             "image_repos": ["registry.example/unmatched/thing"]}


def main() -> int:
    print(__doc__.strip().splitlines()[0])
    print()

    # --- commissioning straws: the case must be non-trivial -----------------
    check("commissioning: component name alone does NOT match the rule",
          _cov.denied(POLICY, "penpot-cache", "minor") is None)
    check("commissioning: the image repo DOES match the rule",
          _cov.denied(POLICY, "valkey/valkey", "minor") is not None)

    # --- the fix -------------------------------------------------------------
    got = _cov.denied_for_item(POLICY, PENPOT, "penpot-cache", "minor")
    check("an item held only by its IMAGE REPO is now blocked",
          got is not None and "pre-release" in got, f"got {got!r}")

    # --- unchanged behaviour -------------------------------------------------
    by_comp = _cov.denied(POLICY, "cilium", "patch")
    by_item = _cov.denied_for_item(POLICY, CILIUM, "cilium", "patch")
    check("a component-matched hold keeps its own reason",
          by_item == by_comp and by_item is not None, f"{by_item!r} vs {by_comp!r}")

    check("an item matching nothing stays unblocked",
          _cov.denied_for_item(POLICY, MEMGRAPH, "memgraph", "patch") is None)

    check("an item with no image repos behaves exactly like denied()",
          _cov.denied_for_item(POLICY, NOREPO, "penpot-cache", "minor")
          == _cov.denied(POLICY, "penpot-cache", "minor"))

    # The component arm must carry its own weight: this item matches ONLY by
    # component, so it fails the moment that arm is dropped.
    check("a hold matched by COMPONENT still fires when no repo matches",
          _cov.denied_for_item(POLICY, COMP_ONLY, "cilium", "patch") is not None)
    check("commissioning: COMP_ONLY's repo genuinely matches nothing",
          _cov.denied(POLICY, "registry.example/unmatched/thing", "patch") is None)

    # --- max: rules still decide by update_type ------------------------------
    at = {"component": "x", "kind": "chart", "type": "patch",
          "image_repos": ["ghcr.io/app-template/x"]}
    check("a `max:` rule still ALLOWS an update within its ceiling",
          _cov.denied_for_item(POLICY, at, "app-template", "patch") is None)
    check("a `max:` rule still blocks an update above its ceiling",
          _cov.denied_for_item(POLICY, at, "app-template", "minor") is not None)

    # --- THE SAFETY PROPERTY -------------------------------------------------
    # Repo-aware matching is a SUPERSET: wherever the component match blocked,
    # the item match must still block. It may add holds; it may never remove one.
    violations = []
    for item, key in ((PENPOT, "penpot-cache"), (CILIUM, "cilium"),
                      (MEMGRAPH, "memgraph"), (NOREPO, "penpot-cache"),
                      (COMP_ONLY, "cilium"), (at, "app-template")):
        for ut in ("patch", "minor"):
            was = _cov.denied(POLICY, key, ut)
            now = _cov.denied_for_item(POLICY, item, key, ut)
            if was is not None and now is None:
                violations.append((key, ut, was))
    check("superset property: repo-aware matching never REMOVES a hold",
          not violations, f"violations={violations}")

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} -> {', '.join(FAILURES)}")
        return 1
    print("all tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
