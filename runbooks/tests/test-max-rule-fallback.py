#!/usr/bin/env python3
"""Regression tests for coverage.py's `max:` deny-rule FALLBACK lane.

THE GAP THIS CLOSES (measured 2026-09-12). A deny rule carrying `max: patch`
says "patches are fine, minor+ is not". Neither half of Step 0 could act on the
first clause:

  * `auto-update.py` only ever sees OPEN Renovate PRs, and Renovate proposes the
    NEWEST version — which for a `max:`-held component is by definition the
    blocked one (n8n PR #213: 2.38.4 -> 2.39.4, the beta line). G2 holds it.
  * `coverage.py`'s direct-bump lane is the NO-PR path, and n8n HAS a PR, so the
    Renovate-PR shortcut in `assign_lane()` claimed the component as covered.

So 2.38.4 -> 2.38.7 — a plain patch on the STABLE line, explicitly permitted by
that same rule — was invisible to both halves and could never land.

THE DANGEROUS WAY TO "FIX" IT is to take the newest semver the rule allows. The
only reason these components carry `max:` at all is that registry semver cannot
tell their stable line from their beta line, so that inference re-creates the
exact hazard one minor lower. Every test below therefore also pins the
FAIL-SAFE direction: an unconfirmable channel HOLDS, it never falls through.

Run: python3 runbooks/tests/test-max-rule-fallback.py
"""
import importlib.util
import os
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "coverage_max_rule", os.path.join(_HERE, "..", "coverage.py"))
cov = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cov)


# ── fixtures ────────────────────────────────────────────────────────────────
N8N_POLICY = {
    "deny": [
        {"match": "*n8n*", "reason": "n8n ships its beta channel on the next MINOR line",
         "max": "patch"},
    ],
}
NOCODB_POLICY = {
    "deny": [
        {"match": "*nocodb*", "reason": "calver month bumps run one-way migrations",
         "max": "patch"},
    ],
}
FULL_BLOCK_POLICY = {
    "deny": [{"match": "*cilium*", "reason": "CNI datapath — never unattended"}],
}
NO_RULE_POLICY = {"deny": []}


def item(component, current, target, type_, kind="image", repo=None, ns="test"):
    d = {"component": component, "namespace": ns, "kind": kind,
         "current": current, "target": target, "type": type_,
         "cell": f"{current} → {target}", "image_repo": None}
    d["image_repos"] = [repo] if repo else []
    return d


def n8n_item():
    return item("n8n", "2.38.4", "2.39.4", "minor", repo="n8nio/n8n")


class _Stubbed(unittest.TestCase):
    """Every test stubs the two NETWORK oracles. They are exercised for real by
    the live dry-run, not by a unit test that would be flaky and slow."""

    def setUp(self):
        self._chan = cov.stable_channel_version
        self._g3 = cov.breaking_change_signal
        self._age = cov.direct_bump_age_gate
        cov.breaking_change_signal = lambda repo, tag: (False, "clean (stubbed)")
        cov.direct_bump_age_gate = lambda it, policy: None

    def tearDown(self):
        cov.stable_channel_version = self._chan
        cov.breaking_change_signal = self._g3
        cov.direct_bump_age_gate = self._age

    def channel(self, version, evidence="stubbed stable channel"):
        cov.stable_channel_version = lambda repo, timeout=None: (version, evidence)

    def channel_fails(self, why="registry unreachable"):
        cov.stable_channel_version = lambda repo, timeout=None: (None, why)


# ── 1. the n8n shape ────────────────────────────────────────────────────────
class N8nShapeTest(_Stubbed):
    def test_allowed_patch_is_surfaced_behind_the_blocked_minor(self):
        self.channel("2.38.7", "`stable` tag label org.opencontainers.image.version=2.38.7")
        recs = cov.max_rule_fallbacks([n8n_item()], N8N_POLICY, {"n8n": "213"})
        self.assertEqual(len(recs), 1, recs)
        r = recs[0]
        self.assertEqual(r["status"], "candidate", r["reason"])
        self.assertEqual(r["candidate"], "2.38.7")
        self.assertEqual(r["deny_max"], "patch")
        self.assertEqual(r["blocked_target"], "2.39.4")
        self.assertEqual(r["blocked_pr"], "213")
        self.assertEqual(r["item"]["type"], "patch")
        self.assertEqual(r["item"]["target"], "2.38.7")
        self.assertTrue(r["item"]["max_rule_fallback"])

    def test_candidate_reaches_the_auto_lane(self):
        """G1/G2 must PASS for the lower target — that is the whole point."""
        self.channel("2.38.7")
        rec = cov.max_rule_fallbacks([n8n_item()], N8N_POLICY, {"n8n": "213"})[0]
        lane, reason, _ = cov.assign_lane(rec["item"], N8N_POLICY, {"n8n": "213"}, [])
        self.assertEqual(lane, "AUTO", f"{lane}: {reason}")
        # It must NOT be claimed by the blocked PR: the window agent skips AUTO
        # items whose reason names a PR (auto-update.py handles those), so that
        # reason would re-mask the very update this lane exists to surface.
        self.assertNotIn("Renovate PR", reason)
        self.assertIn("direct-bump", reason)

    def test_the_blocked_minor_itself_still_goes_to_plan(self):
        """Nothing is dropped: the beta bump remains visible and held."""
        lane, reason, _ = cov.assign_lane(n8n_item(), N8N_POLICY, {}, [])
        self.assertEqual(lane, "PLAN")
        self.assertIn("beta", reason)


# ── 2. the channel lookup FAILS — must hold, never guess ────────────────────
class ChannelUnconfirmableTest(_Stubbed):
    def test_lookup_failure_holds(self):
        self.channel_fails("`stable` unreadable (HTTPError); `latest` carries no version label")
        recs = cov.max_rule_fallbacks([n8n_item()], N8N_POLICY, {"n8n": "213"})
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["status"], "hold")
        self.assertIsNone(recs[0].get("item"))
        self.assertIn("NOT confirmable", recs[0]["reason"])
        self.assertIn("newest semver wins", recs[0]["reason"])

    def test_unresolved_image_repo_holds(self):
        """No repo => no channel to read. Unmeasurable is not safe."""
        self.channel("2.38.7")
        it = n8n_item()
        it["image_repos"] = []
        rec = cov.max_rule_fallbacks([it], N8N_POLICY, {})[0]
        self.assertEqual(rec["status"], "hold")
        self.assertIn("unresolved", rec["reason"])

    def test_ambiguous_image_repos_hold(self):
        """A multi-image row cannot attribute the bump to one channel."""
        self.channel("2.38.7")
        it = n8n_item()
        it["image_repos"] = ["n8nio/n8n", "busybox"]
        rec = cov.max_rule_fallbacks([it], N8N_POLICY, {})[0]
        self.assertEqual(rec["status"], "hold")
        self.assertIn("ambiguous", rec["reason"])

    def test_chart_holds_no_oracle_exists(self):
        self.channel("13.2.3")
        it = item("grafana", "13.2.1", "14.0.0", "major", kind="chart")
        rec = cov.max_rule_fallbacks(
            [it], {"deny": [{"match": "*grafana*", "reason": "appVersion", "max": "patch"}]}, {})[0]
        self.assertEqual(rec["status"], "hold")
        self.assertIn("CHART", rec["reason"])


# ── 3. no `max:` rule — behave EXACTLY as before ─────────────────────────────
class NoRegressionTest(_Stubbed):
    def test_component_with_no_deny_rule_emits_nothing(self):
        self.channel("9.9.9")   # would be a juicy candidate if anything asked
        it = item("cloudflared", "2026.8.3", "2026.9.1", "minor", repo="cloudflare/cloudflared")
        self.assertEqual(cov.max_rule_fallbacks([it], NO_RULE_POLICY, {}), [])
        lane, reason, _ = cov.assign_lane(it, NO_RULE_POLICY, {"cloudflared": "215"}, [])
        self.assertEqual(lane, "AUTO")
        self.assertEqual(reason, "Renovate PR #215")

    def test_full_block_rule_emits_nothing(self):
        """No `max:` means NOTHING is allowed — there is no lower target to find."""
        self.channel("1.19.9")
        it = item("cilium", "1.19.0", "1.20.0", "minor", repo="quay.io/cilium/cilium")
        self.assertEqual(cov.max_rule_fallbacks([it], FULL_BLOCK_POLICY, {}), [])

    def test_item_already_within_max_emits_nothing(self):
        """A PATCH under `max: patch` is not blocked, so nothing is masked."""
        self.channel("2.38.7")
        it = item("n8n", "2.38.4", "2.38.5", "patch", repo="n8nio/n8n")
        self.assertEqual(cov.max_rule_fallbacks([it], N8N_POLICY, {}), [])

    def test_deny_semantics_unchanged_by_the_refactor(self):
        """`denied()` was re-expressed via `deny_rule_for()`. It must still scan
        PAST a non-blocking `max:` rule to a later catch-all — auto-update.py's
        `policy_block()` has that same shape and the two must not diverge."""
        pol = {"deny": [
            {"match": "*nextcloud-mcp*", "reason": "mcp minors", "max": "patch"},
            {"match": "*nextcloud*", "reason": "occ migrations"},
        ]}
        self.assertIn("mcp minors", cov.denied(pol, "nextcloud-mcp", "minor"))
        self.assertIn("occ migrations", cov.denied(pol, "nextcloud-mcp", "patch"))
        self.assertIsNone(cov.denied(pol, "unrelated-app", "patch"))


# ── 4. the fallback is a SOURCE, not a bypass ───────────────────────────────
class GatesStillApplyTest(_Stubbed):
    def test_stable_head_that_is_itself_blocked_holds(self):
        """nocodb shape: the stable channel head IS the blocked minor."""
        self.channel("2026.09.0", "Docker Hub `latest` digest == tag 2026.09.0")
        it = item("nocodb", "2026.08.2", "2026.09.0", "minor", repo="nocodb/nocodb")
        rec = cov.max_rule_fallbacks([it], NOCODB_POLICY, {})[0]
        self.assertEqual(rec["status"], "hold")
        self.assertIn("still blocks", rec["reason"])
        self.assertIsNone(rec.get("item"))

    def test_a_prerelease_stable_head_is_refused(self):
        """If the oracle ever returns a marked pre-release, G2/the channel gate
        must catch it rather than the fallback laundering it into AUTO."""
        self.channel("2.39.0-beta.1")
        rec = cov.max_rule_fallbacks([n8n_item()], N8N_POLICY, {})[0]
        if rec["status"] == "candidate":
            lane, reason, _ = cov.assign_lane(rec["item"], N8N_POLICY, {}, [])
            self.assertEqual(lane, "PLAN", reason)
            self.assertIn("pre-release", reason)
        else:
            self.assertEqual(rec["status"], "hold")

    def test_g5_cooldown_still_holds_the_candidate(self):
        self.channel("2.38.7")
        cov.direct_bump_age_gate = self._age          # restore the REAL gate
        rec = cov.max_rule_fallbacks([n8n_item()], N8N_POLICY, {"n8n": "213"})[0]
        real_age = cov.image_publish_age_hours
        try:
            cov.image_publish_age_hours = lambda repo, tag: 3.0
            lane, reason, _ = cov.assign_lane(
                rec["item"], {**N8N_POLICY, "minimum_release_age_hours": 48},
                {"n8n": "213"}, [])
        finally:
            cov.image_publish_age_hours = real_age
        self.assertEqual(lane, "HELD", reason)
        self.assertIn("G5 release-age cooldown", reason)

    def test_g3_breaking_signal_holds_the_candidate(self):
        self.channel("2.38.7")
        cov.breaking_change_signal = lambda repo, tag: (True, "breaking-change signal in release notes: drops a table")
        rec = cov.max_rule_fallbacks([n8n_item()], N8N_POLICY, {})[0]
        self.assertEqual(rec["status"], "hold")
        self.assertIn("G3", rec["reason"])
        self.assertIsNone(rec.get("item"))

    def test_self_built_image_is_left_to_the_rebuild_lane(self):
        self.channel("1.2.3")
        it = item("sure", "1.2.0", "2.0.0", "major",
                  repo="ghcr.io/nachtschatt3n/sure")
        pol = {"deny": [{"match": "*sure*", "reason": "x", "max": "patch"}]}
        self.assertEqual(cov.max_rule_fallbacks([it], pol, {}), [])

    def test_candidate_already_in_the_universe_is_not_duplicated(self):
        self.channel("2.38.7")
        twin = item("n8n", "2.38.4", "2.38.7", "patch", repo="n8nio/n8n")
        recs = cov.max_rule_fallbacks([n8n_item(), twin], N8N_POLICY, {})
        self.assertEqual([r["status"] for r in recs], ["already-enumerated"])
        self.assertIsNone(recs[0].get("item"), "duplicate item appended to the universe")


# ── 5. lockstep must not make the new lane inert ────────────────────────────
class LockstepTest(_Stubbed):
    def _lanes(self, auto, plan):
        return {"AUTO": list(auto), "PLAN": list(plan), "REBUILD": [], "HELD": [], "CRACK": []}

    def test_own_origin_does_not_lockstep_the_candidate_back(self):
        """The blocked minor is ALWAYS in PLAN, so without this the fallback
        would be pulled back to PLAN every single time — inert by construction."""
        self.channel("2.38.7")
        rec = cov.max_rule_fallbacks([n8n_item()], N8N_POLICY, {})[0]
        cand = {**rec["item"], "lane": "AUTO", "reason": "safe patch/minor"}
        origin = {**n8n_item(), "lane": "PLAN", "reason": "beta line"}
        lanes = self._lanes([cand], [origin])
        moved = cov._apply_lockstep(lanes, [])
        self.assertEqual(moved, [])
        self.assertEqual(len(lanes["AUTO"]), 1)

    def test_a_genuine_held_sibling_still_locksteps(self):
        """A CHART held for the same component is a real deployable half."""
        self.channel("2.38.7")
        rec = cov.max_rule_fallbacks([n8n_item()], N8N_POLICY, {})[0]
        cand = {**rec["item"], "lane": "AUTO", "reason": "safe patch/minor"}
        chart = {**item("n8n", "2.0.1", "3.0.0", "major", kind="chart"),
                 "lane": "PLAN", "reason": "chart major"}
        lanes = self._lanes([cand], [chart])
        moved = cov._apply_lockstep(lanes, [])
        self.assertEqual(len(moved), 1)
        self.assertEqual(lanes["AUTO"], [])


# ── 6. the reported record is honest about where the candidate ended up ─────
class ReportShapeTest(_Stubbed):
    def test_record_carries_the_evidence_and_the_gates(self):
        self.channel("2.38.7", "`stable` tag label org.opencontainers.image.version=2.38.7")
        rec = cov.max_rule_fallbacks([n8n_item()], N8N_POLICY, {"n8n": "213"})[0]
        for field in ("component", "kind", "current", "blocked_target", "blocked_type",
                      "deny_match", "deny_max", "blocked_pr", "status", "candidate",
                      "channel_evidence", "g3", "reason"):
            self.assertIn(field, rec, f"missing {field}")
        self.assertIn("stable", rec["channel_evidence"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
