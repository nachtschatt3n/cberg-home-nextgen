#!/usr/bin/env python3
"""Regression tests for window_runs slot identity (2026-09-05).

The maintenance-window liveness check compares two things that must agree on
what a slot IS:

  * `maintenance-plan.py:expected_slots()` emits the BARE window id paired with
    a date -- ("nightly", "2026-08-29")
  * `window_runs.slot` is what `window-run-record.py` stored

Callers were passing the dated OCCURRENCE form ("nightly:2026-08-29"), because
that is how a window occurrence is named in prose, plan frontmatter and
close-out reports. The table already carries the date in its own `run_date`
column, so those rows became invisible to `missing_window_runs()` and every
correctly-recorded run was reported as a MISSING occurrence.

The check was fully inverted: of 8 slots reported missing on 2026-09-05, 3 had
rows, and the only slot that "passed" was the one row recorded in the wrong
(bare, undated) form -- i.e. the check passed exactly what it should have
failed. That is worse than no check, because it reads as a live detector.

Run: python3 runbooks/tests/test-window-run-slot-identity.py
"""

import importlib.util
import os
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(_HERE, "..", filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_rec = _load("window_run_record", "window-run-record.py")
_plan = _load("maintenance_plan", "maintenance-plan.py")


class TestNormalizeSlot(unittest.TestCase):
    def test_bare_slot_passes_through_silently(self):
        slot, warn = _rec.normalize_slot("sat-attended", "2026-09-05")
        self.assertEqual(slot, "sat-attended")
        self.assertIsNone(warn, "a correct caller must not be warned at")

    def test_dated_slot_is_stripped_to_bare_id(self):
        slot, warn = _rec.normalize_slot("sat-attended:2026-09-05", "2026-09-05")
        self.assertEqual(slot, "sat-attended")
        self.assertIsNotNone(warn, "silent normalization would hide the bug")

    def test_mismatched_embedded_date_is_called_out(self):
        slot, warn = _rec.normalize_slot("nightly:2026-08-29", "2026-09-05")
        self.assertEqual(slot, "nightly")
        self.assertIn("2026-08-29", warn)
        self.assertIn("run_date wins", warn)

    def test_window_id_containing_a_colon_is_not_mangled(self):
        # Only a trailing YYYY-MM-DD counts as an occurrence date.
        slot, warn = _rec.normalize_slot("odd:name", "2026-09-05")
        self.assertEqual(slot, "odd:name")
        self.assertIsNone(warn)

    def test_hyphenated_window_ids_survive(self):
        for wid in ("nightly", "sat-attended", "sun-attended"):
            slot, _ = _rec.normalize_slot(f"{wid}:2026-09-05", "2026-09-05")
            self.assertEqual(slot, wid)


class TestLivenessAgreesWithWriter(unittest.TestCase):
    """The two halves must agree end-to-end, not just individually."""

    def test_normalized_row_is_seen_as_present(self):
        expected = [("nightly", "2026-08-29"), ("sat-attended", "2026-08-29")]
        rows = [(_rec.normalize_slot("nightly:2026-08-29", "2026-08-29")[0],
                 "2026-08-29"),
                (_rec.normalize_slot("sat-attended:2026-08-29", "2026-08-29")[0],
                 "2026-08-29")]
        self.assertEqual(_plan.missing_window_runs(expected, rows), [])

    def test_unnormalized_dated_row_would_have_been_missed(self):
        # Documents the exact defect: this is what the ledger held before the
        # fix, and the check called a recorded run "missing".
        expected = [("nightly", "2026-08-29")]
        rows = [("nightly:2026-08-29", "2026-08-29")]
        self.assertEqual(_plan.missing_window_runs(expected, rows),
                         ["nightly:2026-08-29"])

    def test_genuinely_absent_slot_still_reported(self):
        # The check must keep FAILING for real misses -- fixing the false
        # positive must not blind the detector.
        expected = [("nightly", "2026-08-30"), ("sun-attended", "2026-08-30")]
        rows = [("nightly", "2026-08-30")]
        self.assertEqual(_plan.missing_window_runs(expected, rows),
                         ["sun-attended:2026-08-30"])



class TestMissedWindowExcludesSuperseded(unittest.TestCase):
    """A superseded plan will never run; warning about it never clears."""

    def _unrun(self, plans):
        return _plan.unrun_plans(plans)

    def test_superseded_plan_is_not_a_miss(self):
        plans = [{"plan_id": "talos-1.13.9", "status": "superseded"}]
        self.assertEqual(self._unrun(plans), [])

    def test_executed_plan_is_not_a_miss(self):
        plans = [{"plan_id": "x", "status": "executed"}]
        self.assertEqual(self._unrun(plans), [])

    def test_genuinely_unrun_plan_still_warns(self):
        # The FP fix must not blind the detector.
        for st in ("scheduled", "draft", "awaiting-go", "blocked", "vetted"):
            plans = [{"plan_id": "x", "status": st}]
            self.assertEqual(len(self._unrun(plans)), 1,
                             f"status={st} must still be reported as missed")

    def test_mixed_slot_counts_only_the_unrun(self):
        plans = [{"plan_id": "a", "status": "superseded"},
                 {"plan_id": "b", "status": "scheduled"}]
        unrun = self._unrun(plans)
        self.assertEqual([p["plan_id"] for p in unrun], ["b"])

    def test_missing_status_is_treated_as_unrun(self):
        # Fail loud: a plan with no status must not be silently exempted.
        self.assertEqual(len(self._unrun([{"plan_id": "x"}])), 1)



class TestRiskClassStacking(unittest.TestCase):
    """Two irreversible plans in one slot is the collision namespaces can't see."""

    def test_irreversible_set_is_the_non_git_revert_ones(self):
        self.assertIn("one-way", _plan.IRREVERSIBLE_ROLLBACK)
        self.assertIn("backup-restore", _plan.IRREVERSIBLE_ROLLBACK)
        self.assertNotIn("git-revert", _plan.IRREVERSIBLE_ROLLBACK)

    def _stack(self, classes, namespaces=None):
        # Distinct namespaces by default: proves the check does NOT rely on the
        # namespace intersection that the older INTERFERENCE check uses.
        ns = namespaces or [[f"ns{i}"] for i in range(len(classes))]
        return [{"plan_id": f"p{i}", "rollback_class": c,
                 "touches": {"namespaces": n, "shared": []}}
                for i, (c, n) in enumerate(zip(classes, ns))]

    def _irreversible(self, plans):
        return [p for p in plans
                if p.get("rollback_class") in _plan.IRREVERSIBLE_ROLLBACK]

    def test_two_one_way_plans_in_disjoint_namespaces_are_caught(self):
        plans = self._stack(["one-way", "backup-restore"])
        self.assertEqual(len(self._irreversible(plans)), 2)

    def test_single_irreversible_plan_is_fine(self):
        plans = self._stack(["one-way", "git-revert", "git-revert"])
        self.assertEqual(len(self._irreversible(plans)), 1)

    def test_all_reversible_is_fine(self):
        plans = self._stack(["git-revert", "git-revert"])
        self.assertEqual(self._irreversible(plans), [])

    def test_missing_rollback_class_does_not_count_as_irreversible(self):
        # Unknown != irreversible; the frontmatter-invariant check owns that gap.
        plans = [{"plan_id": "x", "rollback_class": None}]
        self.assertEqual(self._irreversible(plans), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
