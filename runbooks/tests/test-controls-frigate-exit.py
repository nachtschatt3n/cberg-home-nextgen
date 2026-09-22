#!/usr/bin/env python3
"""Regression test: controls.yaml states the frigate mitigation's REAL exit condition.

F-23bcab60 — runbooks/controls.yaml described the frigate-restart CronJob's
exit as "(exit: 0.18 GA)". The SOP (docs/sops/frigate-memory-leak.md,
v2026.09.15) and the CronJob manifest both say the opposite: 0.18 reaching GA
does NOT retire the mitigation — the exit is "0.18 running here WITH
embeddings remote", because the migrated genai provider takes only the
descriptions + chat roles and the in-process embeddings model (the leak's
source) stays. 0.18.0 is already the pinned tag, so the stale line would have
read as "exit condition met — delete the CronJob" to anyone trusting the
controls register.

This reads the three tracked files and asserts they agree on the exit
condition. The straw feeds the pre-fix line through the same predicate.

Run: python3 runbooks/tests/test-controls-frigate-exit.py
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
CONTROLS = REPO / "runbooks/controls.yaml"
SOP = REPO / "docs/sops/frigate-memory-leak.md"
CRONJOB = REPO / "kubernetes/apps/home-automation/frigate-nvr/app/restart-cronjob.yaml"

FAILURES: list[str] = []
ERROR_MARKS = ("Traceback", "Exception:", "Error:")
PRE_FIX_LINE = "daily 02:30 frigate restart bounding the 0.17.2 leak (exit: 0.18 GA)"


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


def exit_condition_is_current(what: str) -> dict:
    """The predicate under test, applied to one `what:` string."""
    w = str(what or "")
    return {
        "names the real exit: 0.18 running here WITH embeddings remote":
            bool(re.search(r"0\.18 running here with embeddings remote", w, re.I)),
        "says GA alone does not retire it":
            bool(re.search(r"GA alone does not retire", w, re.I)),
        "no longer states GA as the exit":
            not re.search(r"exit:\s*0\.18 GA\)", w),
        "no longer pins the leak to the retired 0.17.2 tag":
            "0.17.2" not in w,
    }


def main() -> int:
    print("test-controls-frigate-exit")
    doc = yaml.safe_load(CONTROLS.read_text())
    rows = [c for c in (doc.get("controls") or doc.get("items") or doc if isinstance(doc, list) else
                        next((v for v in doc.values() if isinstance(v, list)), []))
            if isinstance(c, dict)]
    frig = [c for c in rows if c.get("id") == "frigate-restart-mitigation"]
    check("controls.yaml carries exactly one frigate-restart-mitigation row",
          count(rows, lambda c: c.get("id") == "frigate-restart-mitigation") == 1)
    if not frig:
        print(f"FAILED: {FAILURES}")
        return 1
    what = str(frig[0].get("what") or "")
    for name, ok in exit_condition_is_current(what).items():
        check(f"controls.yaml: {name}", ok, what)
    check("controls.yaml: it is still one line (nothing more than the sync was changed)",
          "\n" not in what.strip())

    sop = SOP.read_text()
    check("SOP states the same exit condition (embeddings remote)",
          count(sop.splitlines(), lambda l: "embeddings remote" in l.lower()) >= 1)
    check("SOP states that GA alone does NOT retire the mitigation",
          bool(re.search(r"GA date alone does\s+NOT retire", sop, re.I)))
    cj = CRONJOB.read_text()
    check("CronJob manifest states the same exit condition (embeddings remote)",
          count(cj.splitlines(), lambda l: "embeddings remote" in l.lower()) >= 1)
    check("CronJob manifest says the 0.18 bump does NOT retire it",
          bool(re.search(r"does NOT retire this CronJob", cj)))

    print("  -- commissioning straw: the pre-fix line through the same predicate")
    under = exit_condition_is_current(PRE_FIX_LINE)
    check("straw: the pre-fix '(exit: 0.18 GA)' line FAILS every exit-condition check",
          all(v is False for v in under.values()), str(under))

    print()
    if FAILURES:
        print(f"FAILED ({len(FAILURES)}): {', '.join(FAILURES)}")
        return 1
    print("all controls-frigate-exit tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
