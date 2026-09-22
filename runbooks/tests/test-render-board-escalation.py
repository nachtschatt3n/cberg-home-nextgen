#!/usr/bin/env python3
"""Regression tests: an unbumpable escalation renders as a DECISION, never "no action now".

F-80128ae8 — security-check.py's magnitude rule emits a row when no newer
upstream tag can fix an image and the count is too large to absorb: the
remaining options are a variant/base switch, a replacement, or a compensating
control — a HUMAN decision. AR-029's substring then stamps the row
`[AR-029]`/accepted, and render-board's high-tier collapse folded it into
"N AR-accepted item(s), no upstream fix yet — … no action now". Measured
2026-09-22: one row.

The emitter does not yet stamp `metadata.escalation`; render-board honours
the marker when present and otherwise keys on the title shape the magnitude
branch has carried since 2026-07-31 ("no bump can fix this … Decide: …").
Both keys are pinned here, and so is the negative space: a plain AR-accepted
row, or a row with only one of the two marks, must NOT become a DECISION.

Hermetic: collect() runs against a fake cursor that answers each query by
its shape; no DB.

Run: python3 runbooks/tests/test-render-board-escalation.py
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("render_board", REPO / "runbooks/render-board.py")
rb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rb)
rb.planned_findings = lambda cur=None: {}     # plan refs are not under test

FAILURES: list[str] = []
ERROR_MARKS = ("Traceback", "Exception:", "Error:")


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


def count(population, pred) -> int:
    items = list(population)
    if not items:
        raise AssertionError("count(): EMPTY population — nothing was observed")
    joined = "\n".join(str(x) for x in items)
    if any(m in joined for m in ERROR_MARKS):
        raise AssertionError(f"count(): population carries error text: {joined[:120]!r}")
    return sum(1 for x in items if pred(x))


# Synthetic titles carrying the two marks. No advisory detail, no counts on a
# named service — this file is public.
ESC_HIGH = ("[AR-029] `img-a:1.0`: too much to absorb — no bump can fix this and this is "
            "already the newest upstream tag; upstream ships a materially vulnerable image. "
            "Decide: variant/base switch, replacement, or a compensating control")
ESC_CRIT = ("`img-b:2.0`: too much to absorb — no bump can fix this and the tag FLOATS; "
            "Decide: variant/base switch, replacement, or a compensating control")
PLAIN_AR = "[AR-029] `img-c:3.0`: awaiting an upstream release with the fix"
ONE_MARK = "[AR-031] `img-d:4.0`: Decide: whether to keep this at all"
MARKED_TITLE = "`img-e:5.0`: operator escalation by marker only"


class FakeCursor:
    """Answers collect()'s queries by their shape. Unknown query => abort."""

    def __init__(self, rows):
        self.rows = rows
        self.sql = ""

    def execute(self, sql, params=None):
        self.sql = " ".join(str(sql).split())

    def _pick(self):
        s = self.sql
        if "started_at, finished_at, verdict" in s:
            return [("2026-09-22 04:00:00", None, "amber")]
        if "SELECT notes FROM sweep_cycles" in s:
            return [('{"ran": ["security"]}',)]
        if "AS tier, count(*)" in s:
            return self.rows["tiers"]
        if "risk_tier'='critical'" in s:
            return self.rows["criticals"]
        if "no bump can fix this" in s:
            return self.rows["esc_cand"]
        if "risk_tier'='high'" in s:
            return self.rows["high"]
        if "section != 'security'" in s:
            return []
        if "AS grp, count(*)" in s:
            return self.rows["medium_groups"]
        if "count(*) FILTER" in s:
            return [("security", 5, 5)]
        if "DISTINCT ON (slo_name)" in s:
            return []
        if "SELECT 1 FROM slo_snapshots" in s:
            return []
        raise AssertionError(f"FakeCursor: unexpected query {s[:90]!r}")

    def fetchall(self):
        return list(self._pick())

    def fetchone(self):
        r = self._pick()
        return r[0] if r else None


def rows_fixture():
    # (finding_id, title, exposure, sub, severity) for the high query
    high = [
        ("F-esc-h", ESC_HIGH, None, "s4_cve_check", "accepted"),
        ("F-plain", PLAIN_AR, None, "s4_cve_check", "accepted"),
        ("F-onemark", ONE_MARK, None, "s4_cve_check", "accepted"),
        ("F-real", "`svc`: an exposed endpoint needing attention", "external", "s2", "warning"),
    ]
    # (finding_id, title, tier, severity, esc, sub) for the escalation superset
    esc_cand = [
        ("F-esc-h", ESC_HIGH, "high", "accepted", None, "s4_cve_check"),
        ("F-esc-c", ESC_CRIT, "critical", "critical", None, "s4_cve_check"),
        ("F-esc-m", MARKED_TITLE, "medium", "accepted", "true", "s4_cve_check"),
        ("F-onemark", ONE_MARK, "high", "accepted", None, "s4_cve_check"),
    ]
    return {
        "tiers": [("critical", 1), ("high", 4), ("medium", 3)],
        "criticals": [("F-esc-c", ESC_CRIT)],
        "esc_cand": esc_cand,
        "high": high,
        "medium_groups": [("s4_cve_check", 3)],
    }


def scenarios() -> dict:
    out = {}
    d = rb.collect(FakeCursor(rows_fixture()), "cycle-1")
    esc_ids = {e["id"] for e in d.get("escalations", [])}
    out["collect: both title-shape rows AND the marker-only row are escalations"] = (
        esc_ids == {"F-esc-h", "F-esc-c", "F-esc-m"})
    out["collect: a plain AR-accepted row is NOT an escalation"] = "F-plain" not in esc_ids
    out["collect: a row with only one mark is NOT an escalation"] = "F-onemark" not in esc_ids
    out["collect: the escalation is taken OUT of the AR-accepted count (2, not 3)"] = (
        d["high_accepted"] == 2)
    out["collect: the escalation is not in the individual HIGH list either"] = (
        all(h["id"] != "F-esc-h" for h in d["high"]) and any(h["id"] == "F-real" for h in d["high"]))
    out["collect: a critical-tier escalation is removed from criticals (rendered once, as a decision)"] = (
        all(c["id"] != "F-esc-c" for c in d["criticals"]))
    out["collect: a medium-tier escalation is subtracted from its subsection count"] = (
        d["medium_groups"] == [("s4_cve_check", 2)])

    lines = rb.render(d, {"warnings": []}).splitlines()
    out["render: one **[DECISION]** line per escalation"] = (
        count(lines, lambda l: "**[DECISION]**" in l) == 3)
    out["render: the DECISION line names the decision, not an acceptance"] = (
        count(lines, lambda l: "**[DECISION]**" in l and "DECISION REQUESTED" in l
              and "not an accepted risk" in l) == 3)
    out["render: the DECISION category carries the tier"] = (
        count(lines, lambda l: "`security/escalation/high`" in l) == 1
        and count(lines, lambda l: "`security/escalation/critical`" in l) == 1
        and count(lines, lambda l: "`security/escalation/medium`" in l) == 1)
    na = [l for l in lines if "no action now" in l]
    out["render: the 'no action now' line counts only the plain AR rows"] = (
        len(na) == 1 and "2 AR-accepted" in na[0])
    out["render: no escalation title fragment sits inside the 'no action now' line"] = (
        len(na) == 1 and "img-a" not in na[0] and "img-b" not in na[0] and "img-e" not in na[0])
    out["render: nothing renders as a bare CRITICAL (the critical escalation is a DECISION)"] = (
        count(lines, lambda l: "**[CRITICAL]**" in l) == 0)
    out["render: the header says the list starts at DECISION"] = (
        count(lines, lambda l: "list starts at DECISION" in l) == 1)

    # render alone, with pre-split data: an escalations list is honoured
    # whatever tier it came from, and an absent key is tolerated
    base = {"cycle_id": "c" * 16, "started_at": "2026-09-22 04:00", "tiers": {},
            "criticals": [], "high": [], "high_accepted": 1, "sections": {}, "slos": [],
            "planned": {}, "medium_groups": [], "new_other": [], "ran": [], "warnings": []}
    out["render: tolerates a board dict with no escalations key"] = (
        "**[DECISION]**" not in rb.render(dict(base), {"warnings": []}))
    out["render: is_escalation honours the marker without the title shape"] = (
        rb.is_escalation({"title": "anything", "meta": {"escalation": "true"}}) is True)
    out["render: is_escalation needs BOTH title marks without the marker"] = (
        rb.is_escalation({"title": ESC_CRIT, "meta": {}}) is True
        and rb.is_escalation({"title": ONE_MARK, "meta": {}}) is False
        and rb.is_escalation({"title": PLAIN_AR, "meta": {"escalation": "false"}}) is False)
    return out


# NOT in this list on purpose: "the escalation is not in the individual HIGH
# list" — pre-fix, the accepted `[AR-…]` row was already out of `high` (it was
# folded into the count line), so that check does not discriminate the fix;
# the discriminating one is the high_accepted count.
MUST_FAIL = [
    "collect: both title-shape rows AND the marker-only row are escalations",
    "collect: the escalation is taken OUT of the AR-accepted count (2, not 3)",
    "collect: a critical-tier escalation is removed from criticals (rendered once, as a decision)",
    "collect: a medium-tier escalation is subtracted from its subsection count",
    "render: one **[DECISION]** line per escalation",
    "render: the 'no action now' line counts only the plain AR rows",
    "render: the header says the list starts at DECISION",
]


def main() -> int:
    print("test-render-board-escalation")
    for name, ok in scenarios().items():
        check(name, ok)

    print("  -- commissioning straw: nothing is an escalation (the pre-fix collapse)")
    saved = rb.is_escalation
    rb.is_escalation = lambda row: False
    try:
        under = scenarios()
    finally:
        rb.is_escalation = saved
    failed = [n for n in MUST_FAIL if under.get(n) is False]
    check("straw: every escalation check FAILS with the split reverted",
          len(failed) == len(MUST_FAIL), f"still passing: {sorted(set(MUST_FAIL) - set(failed))}")
    check("straw: the plain-AR control still holds under the straw",
          under.get("collect: a plain AR-accepted row is NOT an escalation") is True)

    print()
    if FAILURES:
        print(f"FAILED ({len(FAILURES)}): {', '.join(FAILURES)}")
        return 1
    print("all render-board-escalation tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
