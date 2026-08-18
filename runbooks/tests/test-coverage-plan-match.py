#!/usr/bin/env python3
"""Regression tests for coverage.py's plan-to-update matching.

Guards the 2026-08-18 fix: `plan_components()` read only a plan's `component`
field, so an EXECUTED or SUPERSEDED plan — and any live plan about a totally
different sub-component — still scored as live coverage. CRACK==0 is treated by
the sweep contract as a hard safety property, so a plan that cannot possibly
deliver the pending bump must not be allowed to claim it.

Run: python3 runbooks/tests/test-coverage-plan-match.py
"""

import importlib.util
import os
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "coverage_mod", os.path.join(_HERE, "..", "coverage.py"))
_cov = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cov)


def plan(component, target, status="draft", kind="image", plan_id=None, current=""):
    return {"plan_id": plan_id or f"{component}-plan", "file": f"{component}.md",
            "keys": {component}, "status": status, "kind": kind,
            "current": current, "target": target}


def item(component, target, kind="image", current="0.0.0"):
    return {"component": component, "kind": kind, "current": current,
            "target": target, "type": "minor"}


class MatchPlanTest(unittest.TestCase):
    def match(self, plans, it):
        return _cov.match_plan(it, {it["component"]}, plans)

    # ── status gate ────────────────────────────────────────────────────
    def test_executed_plan_is_not_coverage(self):
        """THE defect: nextcloud-mcp's 0.175.0 plan is EXECUTED — we are now AT
        0.175.0 and 0.177.1 is pending, with no PR and no live plan."""
        p = [plan("nextcloud-mcp", "0.175.0", status="executed")]
        self.assertEqual(self.match(p, item("nextcloud-mcp", "0.177.1"))[0], None)

    def test_superseded_plan_is_not_coverage(self):
        p = [plan("grafana", "12.10.4", status="superseded", kind="chart")]
        self.assertEqual(
            self.match(p, item("grafana", "12.10.4", kind="chart"))[0], None)

    def test_live_plan_with_matching_target_is_coverage(self):
        p = [plan("cilium", "1.20.1", kind="chart")]
        got, drift = self.match(p, item("cilium", "1.20.1", kind="chart"))
        self.assertEqual(got["plan_id"], "cilium-plan")
        self.assertIsNone(drift)

    def test_missing_status_counts_as_live_draft(self):
        p = [plan("nocodb", "2026.08.0")]
        p[0].pop("status")
        p[0]["status"] = "draft"
        self.assertIsNotNone(self.match(p, item("nocodb", "2026.08.0"))[0])

    # ── target gate ────────────────────────────────────────────────────
    def test_unrelated_sidecar_plan_does_not_cover_the_app(self):
        """superset 5.0.0 -> 6.1.0 was scored covered by a plan whose subject is
        the metadata-DB/Redis sidecar."""
        p = [plan("superset",
                  "official redis 8.10.0-alpine + postgres 17.11-alpine",
                  kind="chart")]
        self.assertEqual(self.match(p, item("superset", "6.1.0"))[0], None)

    def test_prose_target_naming_the_version_does_cover(self):
        """longhorn's plan target is prose but names 1.12.1 explicitly."""
        p = [plan("longhorn", "chart 1.12.1 + ALL volumes on engine v1.12.1",
                  kind="chart")]
        self.assertIsNotNone(
            self.match(p, item("longhorn", "1.12.1", kind="chart"))[0])

    def test_chart_plan_does_not_cover_an_image_bump(self):
        p = [plan("nextcloud", "9.2.6", kind="chart")]
        self.assertEqual(self.match(p, item("nextcloud", "9.2.6", kind="image"))[0], None)

    # ── drift is tolerated but reported ────────────────────────────────
    def test_same_major_line_drift_is_covered_but_flagged(self):
        """unpoller's v2 -> v3 plan pins v3.4.1; v3.5.0 shipped. Still the same
        migration — a refresh, not a re-plan — so cover it and SAY SO."""
        p = [plan("unpoller", "v3.4.1", current="v2.39.0")]
        got, drift = self.match(p, item("unpoller", "v3.5.0", current="v2.39.0"))
        self.assertIsNotNone(got)
        self.assertIn("v3.5.0", drift)

    def test_zero_major_uses_minor_as_the_release_line(self):
        """0.175 and 0.177 are different lines (0.x: minor is the breaking
        axis), so drift tolerance must NOT bridge them."""
        p = [plan("nextcloud-mcp", "0.175.0")]
        self.assertEqual(self.match(p, item("nextcloud-mcp", "0.177.1"))[0], None)

    def test_exact_match_wins_over_a_drifted_one(self):
        p = [plan("app", "3.4.1", plan_id="drifted"),
             plan("app", "3.5.0", plan_id="exact")]
        got, drift = self.match(p, item("app", "3.5.0"))
        self.assertEqual(got["plan_id"], "exact")
        self.assertIsNone(drift)


if __name__ == "__main__":
    unittest.main(verbosity=2)
