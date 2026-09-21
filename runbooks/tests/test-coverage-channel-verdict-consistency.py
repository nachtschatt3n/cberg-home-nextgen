#!/usr/bin/env python3
"""Regression test: one run may not emit two channel verdicts for one component.

F-5224f230, measured 2026-09-16. In a SINGLE run of coverage.py:

  max_rule_fallback : "stable channel head 2.39.5 (`stable` tag label
                       org.opencontainers.image.version=2.39.5,
                       digest-confirmed)"
  PLAN-lane reason  : "n8n ships its beta/next channel on the next MINOR line
                       (2.39.x today) …"

The upgrade-planner dispatched in that window resolved which half was wrong:
npm dist-tags stable=latest=2.39.5, rc=next=beta=2.40.0; GitHub Releases
2.39.0-2.39.4 prerelease=true and 2.39.5 prerelease=false. Upstream had
PROMOTED the 2.39 line on 2026-09-14. The max-rule half was correct; the
PLAN-lane reason — which is the deny rule's prose — is a STATIC assertion about
the component that never re-measures.

A planner briefed from the wrong half plans a pre-release bump into production,
which nearly happened in that window.

The fix does NOT change which lane wins: the operator's rule still governs. It
makes the run state what it MEASURED alongside the prose, so the two halves can
no longer be read as two independent facts. (Push time is not a usable
discriminator here — all four Docker pointers were re-pushed within 5 seconds
on 2026-09-15 — the digest identity is, and that is what the fallback already
resolves.)

Run: python3 runbooks/tests/test-coverage-channel-verdict-consistency.py
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("cov", REPO / "runbooks/coverage.py")
cov = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cov)
cov._release_tags_between = lambda *a, **k: ([], "stubbed")
cov._prerelease_digest_twin = lambda *a, **k: (None, "")

FAILURES: list[str] = []

# The live deny rule, verbatim from auto-update-policy.yaml.
N8N_POLICY = {"deny": [{
    "match": "*n8n*", "max": "patch",
    "reason": ("n8n ships its beta/next channel on the next MINOR line (2.39.x today) "
               "with no prerelease marker in the tag, so a bare semver bump can carry "
               "a beta unattended."),
}]}
EVIDENCE = "`stable` tag label org.opencontainers.image.version=2.39.8, digest-confirmed"


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


def n8n(target="2.40.3"):
    return {"component": "n8n", "namespace": "home-automation", "kind": "image",
            "current": "2.38.7", "target": target, "type": "minor",
            "image_repos": ["n8nio/n8n"]}


def main() -> int:
    print("test-coverage-channel-verdict-consistency")

    heads = {("n8n", "image"): ("2.39.8", EVIDENCE)}

    lane, reason, _ = cov.assign_lane(n8n(), N8N_POLICY, {}, [], None, heads)
    check("the deny rule still decides the lane (the operator's hold is not "
          "overridden by a measurement)", lane == "PLAN", f"{lane}: {reason}")
    check("the rule's prose survives verbatim", "beta/next channel" in reason)
    check("THE FIX: the same reason now carries what THIS RUN measured, so one "
          "run cannot emit two unattributed verdicts",
          "2.39.8" in reason and "MEASURED THIS RUN" in reason, reason)
    check("...with the evidence that backs the measurement",
          "digest-confirmed" in reason, reason)
    check("...and the prose is labelled as prose, not as a second measurement",
          "policy prose" in reason, reason)
    check("the target's relationship to the measured head is stated "
          "(2.40.3 is AHEAD of 2.39.8 — i.e. still off the stable channel)",
          "AHEAD" in reason, reason)

    lane, reason, _ = cov.assign_lane(n8n("2.39.8"), N8N_POLICY, {}, [], None, heads)
    check("a target that IS the measured head says so",
          "AT that head" in reason, reason)

    # ── no measurement => no invented one ──────────────────────────────
    lane, reason, _ = cov.assign_lane(n8n(), N8N_POLICY, {}, [], None, {})
    check("with no resolved channel the reason is the rule's prose and nothing "
          "more — an unresolved channel must not be dressed up as a finding",
          "MEASURED THIS RUN" not in reason and "beta/next channel" in reason, reason)
    lane, reason, _ = cov.assign_lane(n8n(), N8N_POLICY, {}, [], None, None)
    check("heads=None (the window agent's offline call) still works",
          lane == "PLAN" and "MEASURED" not in reason, f"{lane}: {reason}")

    # ── keyed on (component, KIND), like every other head consumer ─────
    chart = dict(n8n(), kind="chart", target="2.0.1", current="2.0.0",
                 image_repos=[])
    lane, reason, _ = cov.assign_lane(chart, N8N_POLICY, {}, [], None, heads)
    check("an IMAGE head is never attached to the same component's CHART hold",
          "2.39.8" not in reason, reason)

    # ── the generic major/unknown hold is annotated too ────────────────
    major = {"component": "n8n", "namespace": "x", "kind": "image",
             "current": "2.38.7", "target": "3.0.0", "type": "major",
             "image_repos": ["n8nio/n8n"]}
    _l, reason, _ = cov.assign_lane(major, {"deny": []}, {}, [], None, heads)
    check("a plain `major — needs an assessed window plan` hold is annotated as "
          "well (the planner is briefed from either)",
          "2.39.8" in reason, reason)

    # ── COMMISSIONING ──────────────────────────────────────────────────
    def straw_raw(reason_, item_, heads_):
        """The pre-fix behaviour: emit the deny rule's prose unchanged."""
        return reason_

    orig = cov._with_channel_measurement
    try:
        cov._with_channel_measurement = straw_raw
        _l, reason, _ = cov.assign_lane(n8n(), N8N_POLICY, {}, [], None, heads)
        check("commissioning: the PRE-FIX reason is caught — it asserts the beta "
              "line while the same run resolved 2.39.8, with nothing tying them "
              "together", "2.39.8" not in reason, f"straw gave: {reason}")
    finally:
        cov._with_channel_measurement = orig

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} -> {', '.join(FAILURES)}")
        return 1
    print("all tests passed")
    return 0


def test_pytest_entry() -> None:
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())
