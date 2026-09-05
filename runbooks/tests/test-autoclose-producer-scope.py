#!/usr/bin/env python3
"""Regression tests for auto-close producer scoping (F-9188fdb8, 2026-09-05).

`FindingsWriter._autoclose_stale` resolves open rows in its section that the
current run did not re-emit. That inference -- "not re-emitted" therefore
"fixed" -- is only sound when the run could plausibly have re-emitted the row.

Section `doc` has TWO producers: `doc-check.py` (the only script emitter) and
the doc-agent, whose agent-authored findings share the same section. So every
orchestrated run read "the script did not re-emit this" as "the agent's finding
is fixed". On 2026-09-05 that auto-closed 9 doc findings, of which SIX were
verified still true by re-inspection (F-e11a1d73, F-4e3ae533, F-3e646e36,
F-a1d008ba, F-aff7ffd0, F-ee4a28ef) and only ONE was genuinely fixed
(F-68c3da92). Three of the six had to be re-opened by hand and are, at the time
of writing, still open as SOP gaps.

This is the same shape as the other audit-logic bugs fixed this week: a check
that cannot distinguish two cases and silently resolves to the wrong one, while
reporting confidently. Closing a finding is the most destructive thing this
writer does -- it asserts work is done -- so the bar for it is "I own this row",
not "I did not see it".

Run: python3 runbooks/tests/test-autoclose-producer-scope.py
"""

import importlib.util
import os
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "findings_writer", os.path.join(_HERE, "..", "lib", "findings_writer.py"))
_fw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fw)


def candidate(fid, producer=_fw and None, severity="warning", title="t"):
    """Shape a _autoclose_stale candidate: (db_id, (fid, sev, title, seen, meta))."""
    meta = {} if producer is None else {"producer": producer}
    return (hash(fid) & 0xffff, (fid, severity, title, "2026-09-01", meta))


def foreign_rows(candidates, run_producer):
    """The predicate under test, mirrored from _autoclose_stale."""
    return [c for c in candidates
            if (c[1][4] or {}).get("producer") not in (None, run_producer)]


class TestProducerStamp(unittest.TestCase):
    def test_default_producer_is_script(self):
        w = _fw.FindingsWriter(dsn=None, section="doc")
        self.assertEqual(w._producer, "script")

    def test_producer_is_overridable(self):
        w = _fw.FindingsWriter(dsn=None, section="doc", producer="doc-agent")
        self.assertEqual(w._producer, "doc-agent")

    def test_disabled_writer_still_accepts_producer(self):
        # emit() short-circuits when disabled; the ctor must not blow up.
        w = _fw.FindingsWriter(dsn=None, section="doc", producer="doc-agent")
        fid = w.emit("warning", "some agent finding")
        self.assertTrue(fid.startswith("F-"))


class TestProducerScope(unittest.TestCase):
    """A run must hold rows it does not own, and still close the ones it does."""

    def test_agent_rows_are_held_from_a_script_run(self):
        # THE BUG: doc-check.py runs, agent rows are silent, all get closed.
        cands = [candidate("F-agent1", producer="doc-agent"),
                 candidate("F-agent2", producer="doc-agent")]
        self.assertEqual(len(foreign_rows(cands, "script")), 2)

    def test_script_rows_still_close_on_a_script_run(self):
        # The FP fix must not blind the detector: own rows must still close.
        cands = [candidate("F-script1", producer="script")]
        self.assertEqual(foreign_rows(cands, "script"), [])

    def test_untagged_legacy_rows_keep_historical_behaviour(self):
        # Rows written before the stamp existed have no producer. Treating
        # them as foreign would leak every pre-existing row open forever.
        cands = [candidate("F-legacy", producer=None)]
        self.assertEqual(foreign_rows(cands, "script"), [])

    def test_agent_run_holds_script_rows_symmetrically(self):
        # The rule is ownership, not a script/agent hierarchy.
        cands = [candidate("F-script1", producer="script")]
        self.assertEqual(len(foreign_rows(cands, "doc-agent")), 1)

    def test_agent_run_closes_its_own_rows(self):
        cands = [candidate("F-agent1", producer="doc-agent")]
        self.assertEqual(foreign_rows(cands, "doc-agent"), [])

    def test_mixed_batch_splits_correctly(self):
        cands = [candidate("F-script1", producer="script"),
                 candidate("F-agent1", producer="doc-agent"),
                 candidate("F-legacy", producer=None)]
        foreign = foreign_rows(cands, "script")
        self.assertEqual([c[1][0] for c in foreign], ["F-agent1"])

    def test_the_2026_09_05_incident_would_not_recur(self):
        # 9 doc rows silent on a doc-check run: 1 genuinely the script's,
        # 6 agent-authored and still true. Only the script's may close.
        agent_ids = ["F-e11a1d73", "F-4e3ae533", "F-3e646e36",
                     "F-a1d008ba", "F-aff7ffd0", "F-ee4a28ef"]
        cands = [candidate(i, producer="doc-agent") for i in agent_ids]
        cands.append(candidate("F-68c3da92", producer="script"))
        foreign = foreign_rows(cands, "script")
        self.assertEqual(sorted(c[1][0] for c in foreign), sorted(agent_ids),
                         "all six still-true agent findings must be held")
        closeable = [c for c in cands if c not in foreign]
        self.assertEqual([c[1][0] for c in closeable], ["F-68c3da92"],
                         "only the genuinely-fixed script row may close")



class TestBackstopProducerGate(unittest.TestCase):
    """The ORCHESTRATOR's auto-close is a second, independent implementation.

    F-73bcfaf6 (2026-09-05): the writer-side gate above was INERT on the path
    that is actually armed. `sweep-run.py:_auto_close_stale_findings()` runs
    after every step of a full orchestrated sweep -- the only mode where
    auto-close fires at all -- and it never read `metadata->>'producer'`. So a
    doc-agent row written in cycle N was still closed by the backstop in cycle
    N+1, which is precisely the failure the writer gate was added to stop.

    Every test in this file above drives the WRITER, so the suite stayed 10/10
    green while the armed path was unguarded. That is the specific hole this
    class exists to close: a gate is only real if the test drives the code
    that is actually reached in production.

    Third divergence between the two implementations -- SWEEP_AUTOCLOSE and
    SWEEP_AUTOCLOSE_DRYRUN diverged the same way and cost four live findings on
    2026-09-03. docs/sops/sweep-findings-lifecycle.md sec 4.8 is the standing rule.
    """

    @staticmethod
    def _backstop_partition(candidates):
        """Mirrors the producer gate in sweep-run.py:_auto_close_stale_findings.

        candidates: [(pk, finding_id, section, title, metadata)]
        returns (closeable_ids, foreign_ids)
        """
        closeable, foreign = [], []
        for pk, fid, sec, title, meta in candidates:
            producer = (meta or {}).get("producer")
            if producer is not None and producer != "script":
                foreign.append(fid)
            else:
                closeable.append(fid)
        return closeable, foreign

    def test_agent_row_survives_the_backstop(self):
        cands = [(1, "F-agent", "doc", "still true", {"producer": "doc-agent"})]
        closeable, foreign = self._backstop_partition(cands)
        self.assertEqual(foreign, ["F-agent"])
        self.assertEqual(closeable, [])

    def test_script_row_still_closes_in_the_backstop(self):
        # The FP fix must not blind the backstop -- script rows are its job.
        cands = [(1, "F-script", "doc", "fixed", {"producer": "script"})]
        closeable, foreign = self._backstop_partition(cands)
        self.assertEqual(closeable, ["F-script"])
        self.assertEqual(foreign, [])

    def test_untagged_legacy_row_still_closes_in_the_backstop(self):
        # Same deliberate compromise as the writer: rows predating the stamp
        # keep historical behaviour or they leak open forever.
        cands = [(1, "F-legacy", "doc", "old", {})]
        closeable, foreign = self._backstop_partition(cands)
        self.assertEqual(closeable, ["F-legacy"])

    def test_null_metadata_does_not_crash_the_backstop(self):
        cands = [(1, "F-nullmeta", "doc", "old", None)]
        closeable, foreign = self._backstop_partition(cands)
        self.assertEqual(closeable, ["F-nullmeta"])

    def test_any_non_script_producer_is_foreign_not_just_doc_agent(self):
        # The orchestrator cannot know WHICH agents ran, so the rule is
        # "not script", not an allowlist of known agent names.
        for prod in ("doc-agent", "media-manager", "security-agent", "future-thing"):
            cands = [(1, "F-x", "doc", "t", {"producer": prod})]
            _, foreign = self._backstop_partition(cands)
            self.assertEqual(foreign, ["F-x"], f"producer={prod} must be held")

    def test_the_2026_09_05_incident_would_not_recur_in_the_backstop(self):
        agent_ids = ["F-e11a1d73", "F-4e3ae533", "F-3e646e36",
                     "F-a1d008ba", "F-aff7ffd0", "F-ee4a28ef"]
        cands = [(i, fid, "doc", "still true", {"producer": "doc-agent"})
                 for i, fid in enumerate(agent_ids)]
        cands.append((99, "F-68c3da92", "doc", "genuinely fixed",
                      {"producer": "script"}))
        closeable, foreign = self._backstop_partition(cands)
        self.assertEqual(sorted(foreign), sorted(agent_ids))
        self.assertEqual(closeable, ["F-68c3da92"])

    def test_backstop_source_actually_reads_producer(self):
        """Guard against the gate being removed or never wired up.

        The mirror above can pass while the real code does not implement it --
        which is exactly how this bug survived. Assert against the source.
        """
        import os as _os
        src = open(_os.path.join(_HERE, "..", "sweep-run.py")).read()
        self.assertIn('"producer"', src,
                      "sweep-run.py must read metadata['producer'] — the "
                      "writer-side gate alone is inert on the armed path")
        self.assertIn('!= "script"', src,
                      "sweep-run.py must hold non-script producers")


if __name__ == "__main__":
    unittest.main(verbosity=2)
