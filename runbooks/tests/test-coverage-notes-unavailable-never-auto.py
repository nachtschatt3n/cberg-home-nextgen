"""Regression test: a bump whose release notes were UNAVAILABLE never lands in
the unattended lane, while a gate EXCEPTION still passes through (retrospective
plan item 2, narrowed with the operator, 2026-09-22).

assign_lane() runs the G3 breaking-change gate on the direct-bump path. When
the gate could not read the release notes it returned (False, "unverified
(release notes unavailable)"), and assign_lane appended that as a note and fell
through to AUTO -- the lane the nightly window applies at 03:30 unattended.
"Could not check" is the one verdict that must not reach that lane. On
2026-09-22 the authentik chart sat in AUTO with exactly this note, held only by
a manual deny rule written that evening.

Measured on the live rows the day this was added: zero flips. The change is
preventive; the fixtures below are synthetic on purpose.

Run:  python3 runbooks/tests/test-coverage-unverified-never-auto.py
"""
from __future__ import annotations
import importlib.util, os, sys
from pathlib import Path
_REPO = Path(__file__).resolve().parents[2]
os.environ.setdefault("_MISE_ACTIVATED", "1"); sys.path.insert(0, str(_REPO / "runbooks"))
_s = importlib.util.spec_from_file_location("cov", _REPO / "runbooks" / "coverage.py")
cov = importlib.util.module_from_spec(_s); _s.loader.exec_module(cov)
cov._direct_bump_structural_gate = lambda item: (False, "clean (diff checked: stubbed — the G3 structural companion reaches the compare API; pinned by test-structural-signal.py)")
FAILURES: list[str] = []
def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok: FAILURES.append(name)
ITEM = {"component": "exampleapp", "namespace": "testns", "kind": "image", "current": "1.2.3",
        "target": "1.2.4", "type": "patch", "image_repo": "example-org/exampleapp"}
POLICY = {"deny": [], "age_waive": []}
def lane_with(g3_result, range_result=("clean", "")):
    saved = (cov._direct_bump_breaking_gate, cov._g3_range_gate, cov.direct_bump_age_gate, getattr(cov, "channel_hold", None))
    try:
        cov._direct_bump_breaking_gate = lambda item: g3_result
        cov._g3_range_gate = lambda item: range_result
        cov.direct_bump_age_gate = lambda *a, **k: None
        if saved[3] is not None: cov.channel_hold = lambda *a, **k: None
        return cov.assign_lane(dict(ITEM), POLICY, [], [])
    finally:
        cov._direct_bump_breaking_gate, cov._g3_range_gate, cov.direct_bump_age_gate = saved[:3]
        if saved[3] is not None: cov.channel_hold = saved[3]
def main() -> int:
    print(__doc__.strip().splitlines()[0]); print()
    lane = lane_with((False, "checked (clean)"))
    check("control: a CHECKED clean patch still lands in AUTO", lane[0] == "AUTO", repr(lane))
    lane = lane_with((False, "unverified (release notes unavailable)"))
    check("an UNVERIFIED patch routes to PLAN", lane[0] == "PLAN", repr(lane))
    check("...and the reason says why", "could not verify" in str(lane[1]))
    lane = lane_with((False, "unverified (RuntimeError)"))
    check("a gate EXCEPTION (network, rate limit) still passes through to AUTO — the starvation guard", lane[0] == "AUTO", repr(lane))
    lane = lane_with((False, "unverified (no image repository to read notes for)"))
    check("no-repository still passes through (G5 holds that case one gate earlier)", lane[0] == "AUTO", repr(lane))
    lane = lane_with((True, "BREAKING CHANGE in notes"))
    check("a breaking signal still routes to PLAN (unchanged)", lane[0] == "PLAN")
    src = (_REPO / "runbooks" / "coverage.py").read_text()
    check("commissioning: the branch exists in source and precedes the AUTO return",
          src.index('if "release notes unavailable" in str(g3):') < src.index('return "AUTO", f"safe patch/minor'))
    print(); print("FAILED: " + ", ".join(FAILURES) if FAILURES else "all tests passed"); return 1 if FAILURES else 0
def test_pytest_entry(): assert main() == 0
if __name__ == "__main__": raise SystemExit(main())
