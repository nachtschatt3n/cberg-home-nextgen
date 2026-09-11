#!/usr/bin/env python3
"""Regression tests for the AUTO-lane safety rules in coverage.py.

The AUTO lane is APPLIED UNATTENDED at Step 0 of every maintenance window
(window-agent hybrid: merge the Renovate PR, else direct-bump the manifest).
So anything mis-routed into AUTO lands on the cluster with nobody in the loop.
Three ways that happened, each locked down here:

  1. PRE-RELEASE CHANNEL (2026-08-18, the dangerous one) — scrypted v0.144.x is
     upstream's beta channel (stable is odd minors only; v0.144.x has no GitHub
     release and v0.144.0 predates stable v0.143.0), yet the semver label says
     "minor" and AUTO applies it to a PRIVILEGED NVR. AR-081 says the
     pre-release channel is unacceptable for that workload — but an AR only
     suppresses the board finding, it does not gate the lane.
  2. CHART/IMAGE LOCKSTEP (2026-08-18) — unpoller chart 2.4.0 (appVersion
     v3.5.0) scored a safe minor and went to AUTO while the image v2.39.0 ->
     v3.5.0 sits in PLAN, so a window could run a v3-aware chart against a v2
     image.
  3. SELF-BUILT MATCHED ON THE COMPONENT (F-62007db7) — `paperclip` is in
     SELF_BUILT but owns no self-built image, so its third-party images were
     parked in REBUILD, a lane whose remedy can never bump them.

Plus the AUTO double-count: the overview table truncates long tags, so a table
row and its detail row were not deduped and the lane count overstated itself.

Run: python3 runbooks/tests/test-coverage-lane-safety.py
"""
import importlib.util
import os
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "coverage_mod", os.path.join(_HERE, "..", "coverage.py"))
cov = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cov)

POLICY = {"deny": []}


def item(component, kind="image", current="1.0.0", target="1.1.0", type_="minor", **kw):
    d = {"component": component, "namespace": "test", "kind": kind,
         "current": current, "target": target, "type": type_, "cell": ""}
    d.update(kw)
    return d


class ChannelGateTest(unittest.TestCase):
    def test_scrypted_dev_channel_minor_is_not_auto(self):
        """The live hazard: v0.143.0 -> v0.144.1 is a 'minor' on the DEV channel."""
        it = item("scrypted", current="v0.143.0-noble-full",
                  target="v0.144.1-noble-full")
        lane, reason, _ = cov.assign_lane(it, POLICY, {}, [])
        self.assertEqual(lane, "PLAN", f"dev build routed to {lane}: {reason}")
        # The reason must name the REAL gate, not assert "this IS a pre-release".
        # The gate cannot know that offline, and for a genuinely stable tag the
        # claim would be false — so it states what it can actually support.
        self.assertIn("cannot be shown to be a STABLE-channel successor", reason)
        self.assertIn("Release", reason)
        self.assertIn("AR-081", reason)

    def test_channel_gate_is_a_freeze_for_listed_components_only(self):
        """WHICH GUARD COVERS WHAT — REVISED 2026-09-11.

        This test used to assert the opposite: that a "stable odd minor"
        (0.143 -> 0.145) CLEARED the channel gate, and that on a hypothetical
        1.x line `v1.143.0 -> v1.145.0` reached AUTO. Both encoded the parity
        predicate as if it were evidence of stability. It is not:

          * ~17 scrypted releases carry prerelease=false on EVEN minors, so
            "stable = odd" was simply false; and
          * the predicate failed OPEN — a Release-less dev tag on an ODD minor
            (v0.147.0) scored stable. The old 1.x assertion is exactly that
            hazard written down as desired behaviour: parity alone would have
            sent a dev build to the unattended AUTO lane on a privileged NVR.

        Stable-ness depends on whether upstream published a non-prerelease
        Release for that EXACT tag, which no version string can answer and which
        coverage.py must not go to the network to ask (it runs without
        SWEEP_PG_DSN in the window agent). So for a LISTED component the gate is
        deliberately a freeze.

        The property still worth guarding is that the freeze is SCOPED: it
        applies to CHANNEL_RULES members and invents no holds for anyone else.
        The "two independent guards" structure also survives — the 0.x
        release-line rule below is still separate and still does its own work.
        """
        stable = item("scrypted", current="v0.143.0-noble-full",
                      target="v0.145.0-noble-full")
        dev = item("scrypted", current="v0.143.0-noble-full",
                   target="v0.144.1-noble-full")
        # Listed component: held on BOTH, because the channel is undecidable here.
        self.assertIsNotNone(cov.channel_hold("scrypted", stable))
        self.assertIsNotNone(cov.channel_hold("scrypted", dev))
        # ... and the freeze follows upstream to 1.x, where the old test let a
        # parity-"stable" tag through to AUTO.
        lane, _, _ = cov.assign_lane(
            item("scrypted", current="v1.143.0", target="v1.145.0"), POLICY, {}, [])
        self.assertEqual(lane, "PLAN")
        # SCOPE: an unlisted component is untouched — this is not a global freeze.
        self.assertIsNone(cov.channel_hold("grafana", item("grafana", target="13.2.2")))
        lane, _, _ = cov.assign_lane(
            item("grafana", current="13.2.1", target="13.2.2", type_="patch"),
            POLICY, {}, [])
        self.assertEqual(lane, "AUTO")

    def test_open_renovate_pr_does_not_launder_a_beta(self):
        """A PR existing is not evidence the target is a stable successor."""
        it = item("scrypted", current="v0.143.0-noble-full",
                  target="v0.144.1-noble-full")
        lane, _, _ = cov.assign_lane(it, POLICY, {"scrypted": "1234"}, [])
        self.assertEqual(lane, "PLAN")

    def test_explicit_prerelease_tag_is_never_auto(self):
        """Universal rule — no per-component entry needed."""
        for tgt in ("1.2.0-beta.1", "1.2.0-rc2", "2.0.0-nightly", "3.1.0-alpha"):
            lane, reason, _ = cov.assign_lane(item("anything", target=tgt), POLICY, {}, [])
            self.assertEqual(lane, "PLAN", f"{tgt} -> {lane}")
            self.assertIn("pre-release", reason)

    def test_normal_suffixed_tags_are_not_mistaken_for_prereleases(self):
        for tgt in ("1.2.0-noble-full", "3.14.7-slim", "13.6-bookworm", "1.2.0-alpine3"):
            lane, _, _ = cov.assign_lane(item("anything", target=tgt), POLICY, {}, [])
            self.assertEqual(lane, "AUTO", f"{tgt} wrongly held")

    def test_ar_declaring_the_channel_unacceptable_holds_the_component(self):
        """Layer 3: an ACTIVE accepted risk can add a hold with no code change."""
        it = item("someapp", target="9.9.9")
        lane, reason, _ = cov.assign_lane(it, POLICY, {}, [],
                                          {"someapp": "AR-999"})
        self.assertEqual(lane, "PLAN")
        self.assertIn("AR-999", reason)


class ZeroVerLineTest(unittest.TestCase):
    """At major 0 the MINOR is the breaking axis (this repo's own
    `_release_line` doctrine; nextcloud-mcp 0.176.0 dropped a table on a minor
    hop). A 0.x minor is a release-LINE move, not a safe in-line bump."""

    def test_zero_x_minor_is_planned(self):
        lane, reason, _ = cov.assign_lane(
            item("someapp", current="0.175.0", target="0.178.1"), POLICY, {}, [])
        self.assertEqual(lane, "PLAN")
        self.assertIn("0.x release-line", reason)

    def test_zero_x_patch_still_flows_to_auto(self):
        lane, _, _ = cov.assign_lane(
            item("someapp", current="0.27.3", target="0.27.4", type_="patch"),
            POLICY, {}, [])
        self.assertEqual(lane, "AUTO")

    def test_one_x_minor_is_unaffected(self):
        lane, _, _ = cov.assign_lane(
            item("someapp", current="1.4.0", target="1.6.2"), POLICY, {}, [])
        self.assertEqual(lane, "AUTO")


class LockstepTest(unittest.TestCase):
    def test_chart_follows_its_plan_held_image(self):
        lanes = {"AUTO": [], "PLAN": [], "REBUILD": [], "HELD": [], "CRACK": []}
        chart = {**item("unpoller", kind="chart", current="2.1.0", target="2.4.0"),
                 "lane": "AUTO", "reason": "safe patch/minor"}
        image = {**item("unpoller", current="v2.39.0", target="v3.5.0", type_="major"),
                 "lane": "PLAN", "reason": "plan exists: unpoller-v3 (draft)"}
        lanes["AUTO"].append(chart)
        lanes["PLAN"].append(image)
        moved = cov._apply_lockstep(lanes, [])
        self.assertEqual(lanes["AUTO"], [])
        self.assertEqual(len(moved), 1)
        self.assertIn("lockstep", moved[0]["reason"])
        self.assertIn("v3.5.0", moved[0]["lockstep_with"])

    def test_unrelated_component_still_reaches_auto(self):
        lanes = {"AUTO": [], "PLAN": [], "REBUILD": [], "HELD": [], "CRACK": []}
        kps = {**item("kube-prometheus-stack", kind="chart",
                      current="88.3.0", target="88.5.0"), "lane": "AUTO", "reason": "safe"}
        lanes["AUTO"].append(kps)
        lanes["PLAN"].append({**item("unpoller", current="v2.39.0", target="v3.5.0"),
                              "lane": "PLAN", "reason": "plan exists"})
        cov._apply_lockstep(lanes, [])
        self.assertEqual([e["component"] for e in lanes["AUTO"]], ["kube-prometheus-stack"])


class SelfBuiltMatchingTest(unittest.TestCase):
    def test_third_party_image_of_a_self_built_app_is_not_rebuild(self):
        """paperclip is in SELF_BUILT, but `ubuntu` is not our image."""
        it = item("paperclip", current="24.04", target="26.04",
                  type_="major", image_repo="ubuntu")
        lane, _, _ = cov.assign_lane(it, POLICY, {}, [])
        self.assertNotEqual(lane, "REBUILD")

    def test_self_built_image_under_a_differently_named_app_is_rebuild(self):
        """The 2026-08-15 under-capture, now decided on the image."""
        it = item("ha-ai-harness", image_repo="ghcr.io/nachtschatt3n/harness-home-frontend")
        lane, _, _ = cov.assign_lane(it, POLICY, {}, [])
        self.assertEqual(lane, "REBUILD")

    def test_multi_image_row_is_only_rebuild_when_every_image_is_ours(self):
        mixed = item("paperclip", image_repos=["ghcr.io/nachtschatt3n/x", "ubuntu"])
        self.assertFalse(cov.is_self_built(mixed, "paperclip"))
        ours = item("absenty", image_repos=["ghcr.io/nachtschatt3n/absenty"])
        self.assertTrue(cov.is_self_built(ours, "absenty"))

    def test_component_set_is_still_the_fallback_without_image_evidence(self):
        self.assertTrue(cov.is_self_built(item("sure"), "sure"))

    def test_a_chart_is_never_a_self_built_image(self):
        self.assertFalse(cov.is_self_built(item("sure", kind="chart"), "sure"))


class DedupeTest(unittest.TestCase):
    def test_truncated_table_tag_matches_its_untruncated_detail_tag(self):
        self.assertEqual(cov._dedupe_tag("v0.144.1-noble-ful..."),
                         cov._dedupe_tag("v0.144.1-noble-full"))
        self.assertTrue(cov._is_truncated("v0.144.1-noble-ful..."))
        self.assertFalse(cov._is_truncated("v0.144.1-noble-full"))

    def test_prerelease_marker_survives_dedupe(self):
        """A dedupe that erases the marker would re-open the AUTO lane."""
        self.assertNotEqual(cov._dedupe_tag("1.2.3"), cov._dedupe_tag("1.2.3-beta"))
        self.assertEqual(cov._dedupe_tag("1.2.3-alpine"), cov._dedupe_tag("1.2.3"))

    def test_different_versions_still_differ(self):
        self.assertNotEqual(cov._dedupe_tag("v0.144.1-noble-full"),
                            cov._dedupe_tag("v0.144.2-noble-full"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
