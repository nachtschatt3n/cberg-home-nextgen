"""Unit tests for finding-triage lane assignment.

The tool decides, unattended at 04:00, whether a critical finding gets touched
automatically or waits for a maintenance window. The dangerous direction is
FIX_NOW: a missed auto-fix costs one window, a wrong one edits a live cluster
with nobody watching. So most of these tests assert that things do NOT reach
FIX_NOW, and the fail-safe holds when the policy itself is broken.

They also pin the guarantee the tool exists to provide: every critical finding
gets exactly one lane and CRACK is zero. The frigate memory leak of 2026-08-24
sat at 98.6% of its limit with `action` NULL because nothing assigned it an
owner — a lane it could fall out of would reproduce that.

Run:  python3 runbooks/tests/test-finding-triage-lanes.py
  or: python3 -m pytest runbooks/tests/test-finding-triage-lanes.py -q
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
MODULE = REPO / "runbooks" / "finding-triage.py"

spec = importlib.util.spec_from_file_location("finding_triage", MODULE)
ft = importlib.util.module_from_spec(spec)
sys.modules["finding_triage"] = ft
spec.loader.exec_module(ft)


def _finding(title, section="health", fid="F-test"):
    return {"finding_id": fid, "section": section, "severity": "critical",
            "title": title, "status": "new", "action": None, "metadata": {}}


def _lane(title, policy, section="health", covered=frozenset()):
    return ft.triage([_finding(title, section)], policy, set(covered))[0]


REAL_POLICY = ft.load_policy()


# --- the fail-safe direction -------------------------------------------------

def test_unmatched_finding_defaults_to_plan_never_fix_now():
    """An unrecognised critical finding must still get an owner, and must not be
    touched automatically. This is the whole asymmetry of the design."""
    r = _lane("Some entirely novel critical condition nobody anticipated", REAL_POLICY)
    assert r["lane"] == "PLAN", r
    assert r["rule"] == "default", r


def test_broken_policy_routes_everything_to_plan():
    """A policy that fails to load must not read as 'nothing matched, all clear'.

    That failure mode is indistinguishable from a healthy quiet day, which is
    exactly how a guarantee silently stops guaranteeing anything.
    """
    degraded = ft.load_policy(Path("/nonexistent/policy.yaml"))
    assert degraded.get("_degraded"), "missing policy should report degradation"
    assert degraded["default_lane"] == "PLAN"
    r = _lane("`app`: newer upstream tag available, bump the image", degraded)
    assert r["lane"] == "PLAN", r


def test_unknown_remediation_downgrades_to_plan():
    """A policy naming a recipe that does not exist is a bug, not permission.

    Skipping silently would leave the finding unactioned while the counts said
    it was handled.
    """
    policy = {"fix_now": [{"id": "typo", "match_title": "*widget*",
                           "remediation": "nonexistent_recipe"}],
              "default_lane": "PLAN"}
    r = _lane("The widget needs adjusting", policy)
    assert r["lane"] == "PLAN", r
    assert "unknown remediation" in (r["reason"] or ""), r


# --- precedence --------------------------------------------------------------

def test_plan_rule_vetoes_a_fix_now_match():
    """PLAN is evaluated before FIX_NOW, so a restart-causing change can never be
    auto-applied because some broader fix_now glob also matched it."""
    policy = {
        "fix_now": [{"id": "greedy", "match_title": "*", "remediation": "doc_count_sync"}],
        "plan": [{"id": "memory-limit-change", "match_title": "*memory limit*",
                  "reason": "restarts the container"}],
        "default_lane": "PLAN",
    }
    r = _lane("Container is walking into its memory limit", policy)
    assert r["lane"] == "PLAN", r
    assert r["rule"] == "memory-limit-change", r


def test_decide_beats_plan():
    """An exposure question must not be silently converted into a scheduled change."""
    policy = {
        "decide": [{"id": "exposure", "match_title": "*publicly reachable*",
                    "reason": "operator posture call"}],
        "plan": [{"id": "catchall", "match_title": "*", "reason": "window"}],
        "default_lane": "PLAN",
    }
    assert _lane("Service is publicly reachable without auth", policy)["lane"] == "DECIDE"


def test_update_pipeline_ownership_wins_over_everything():
    """If the update pipeline already owns the component, nothing else may act —
    two pipelines making the same change is worse than neither."""
    policy = {"plan": [{"id": "catchall", "match_title": "*", "reason": "window"}],
              "default_lane": "PLAN"}
    r = _lane("`louislam/uptime-kuma:2.5.0`: bump the image", policy,
              covered={"uptime-kuma"})
    assert r["lane"] == "COVERED", r
    assert r["rule"] == "update-pipeline", r


# --- the real policy, against the findings that motivated it -----------------

def test_real_policy_routes_the_frigate_leak_to_a_window():
    r = _lane("Container `home-automation/frigate` is walking into its memory "
              "limit: 98.6% of its memory limit", REAL_POLICY)
    assert r["lane"] == "PLAN", r
    assert r["rule"] == "memory-limit-change", r


def test_real_policy_marks_a_version_finding_as_covered():
    r = _lane("`louislam/uptime-kuma:2.5.0`: fixable CVEs — newer upstream tag "
              "available, bump the image", REAL_POLICY, section="security")
    assert r["lane"] == "COVERED", r


def test_real_policy_never_auto_fixes_storage_or_auth():
    """The two categories where an unattended mistake is unrecoverable."""
    for title in ("Longhorn volume is degraded",
                  "PVC is close to full",
                  "certificate expires in 3 days",
                  "authentik token rotation overdue"):
        r = _lane(title, REAL_POLICY)
        assert r["lane"] != "FIX_NOW", f"{title!r} must never auto-fix: {r}"


# --- the guarantee -----------------------------------------------------------

def test_every_finding_gets_exactly_one_known_lane():
    titles = ["memory limit reached", "publicly reachable", "bump the image",
              "summary count drift", "something unclassifiable", ""]
    results = ft.triage([_finding(t) for t in titles], REAL_POLICY, set())
    assert len(results) == len(titles), "a finding was dropped"
    for r in results:
        assert r["lane"] in ft.LANES, r
    assert sum(1 for r in results if r["lane"] == "CRACK") == 0, \
        "default_lane must absorb everything; a CRACK means the guarantee is broken"


def test_case_insensitive_title_matching():
    """Findings are written by several tools with inconsistent capitalisation."""
    assert _lane("CONTAINER IS AT ITS MEMORY LIMIT", REAL_POLICY)["lane"] == "PLAN"


def _main() -> int:
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_main())
