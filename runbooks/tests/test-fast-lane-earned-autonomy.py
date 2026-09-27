"""Regression tests for the Step 0 fast lanes (throughput program item B,
operator-approved 2026-09-27): earned autonomy, the per-type cooldown, and the
security cooldown bypass — in BOTH lanes (coverage.py direct-bump, auto-update.py
PR lane).

What must hold, and what each half guards against:
  * EARNED vs NOT: an unverified-notes patch lands in AUTO only for a component
    with >= 3 green records and 0 reverts in 90 days; without that record it
    keeps today's PLAN routing. An unreadable ledger is NOT a record.
  * REVERT RESETS: greens before a revert never count again, and any revert in
    the window disqualifies; auto-update.py writes a `reverted` row for every
    component of a reverted batch.
  * SECURITY BYPASS: an open, non-accepted "newer upstream tag available"
    fixable CRITICAL/HIGH finding on the CURRENT tag skips the cooldown (and
    only the cooldown); an AR-accepted title never matches.
  * A MAJOR NEVER AUTO — not earned, not security-driven, in neither lane.
  * A POSITIVE breaking or structural signal still holds an earned component.

Every DB read is stubbed at the fast_lane seam; nothing touches the network.

Run:  python3 runbooks/tests/test-fast-lane-earned-autonomy.py
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
os.environ.setdefault("_MISE_ACTIVATED", "1")
os.environ.pop("SWEEP_PG_DSN", None)
sys.path.insert(0, str(_REPO / "runbooks"))
sys.path.insert(0, str(_REPO / "runbooks" / "lib"))


def _load(name, rel):
    s = importlib.util.spec_from_file_location(name, _REPO / rel)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


import fast_lane  # noqa: E402  (the SAME module object both scripts import)

cov = _load("cov", "runbooks/coverage.py")
au = _load("au", "runbooks/auto-update.py")
assert cov.fast_lane is fast_lane and au.fast_lane is fast_lane

FAILURES: list[str] = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


NOW = dt.datetime(2026, 9, 27, 12, 0, tzinfo=dt.timezone.utc)
D = lambda days: NOW - dt.timedelta(days=days)  # noqa: E731
POLICY = {"deny": [], "age_waive": [], "minimum_release_age_hours": 48,
          "minimum_release_age_hours_by_type": {"patch": 24},
          "security_cooldown_bypass": True,
          "earned_autonomy": {"min_green": 3, "window_days": 90, "max_reverts": 0}}
KEYS = fast_lane.keys_for("exampleapp", ["docker.io/example-org/exampleapp"])


def ev(rows):
    return fast_lane.evaluate_track_record(rows, KEYS, now=NOW, window_days=90,
                                           min_green=3, max_reverts=0)[0]


def set_ledger(rows):
    """Stub the verified ledger (rows) or an UNVERIFIED one (None)."""
    fast_lane._REC_CACHE = (rows,)
    fast_lane.SOURCE["track_record"] = ("component_autonomy (stub)" if rows is not None
                                        else "unverified — stub")


def set_security(rows):
    fast_lane._SEC_CACHE = rows


GREEN3 = [("exampleapp", None, "green", D(10)), ("exampleapp", None, "green", D(20)),
          ("exampleapp", None, "green", D(30))]

ITEM = {"component": "exampleapp", "namespace": "testns", "kind": "image",
        "current": "1.2.3", "target": "1.2.4", "type": "patch",
        "image_repo": "docker.io/example-org/exampleapp"}


def lane_with(item=None, g3=(False, "unverified (release notes unavailable)"),
              rng=("clean", ""), structural=(False, "clean (diff checked: stub)"),
              age_gate=None, policy=POLICY):
    item = dict(item or ITEM)
    saved = (cov._direct_bump_breaking_gate, cov._g3_range_gate, cov.direct_bump_age_gate,
             cov.channel_hold, cov._direct_bump_structural_gate, cov.prerelease_target_hold)
    try:
        cov._direct_bump_breaking_gate = lambda it: g3
        cov._g3_range_gate = lambda it: rng
        cov._direct_bump_structural_gate = lambda it: structural
        if age_gate is not None:
            cov.direct_bump_age_gate = age_gate
        else:
            cov.direct_bump_age_gate = lambda *a, **k: None
        cov.channel_hold = lambda *a, **k: None
        cov.prerelease_target_hold = lambda *a, **k: None
        lane = cov.assign_lane(item, policy, [], [])
        return lane, item
    finally:
        (cov._direct_bump_breaking_gate, cov._g3_range_gate, cov.direct_bump_age_gate,
         cov.channel_hold, cov._direct_bump_structural_gate, cov.prerelease_target_hold) = saved


def main() -> int:
    print(__doc__.strip().splitlines()[0])
    orig_now = fast_lane.evaluate_track_record

    # ---- pure track-record evaluation ----------------------------------------
    print("\ntrack record (pure):")
    check("3 green, 0 reverts in 90d => EARNED", ev(GREEN3))
    check("2 green => not earned", not ev(GREEN3[:2]))
    check("3 green but one is 100d old => not earned (window)",
          not ev(GREEN3[:2] + [("exampleapp", None, "green", D(100))]))
    check("REVERT RESETS: 3 green then a revert => not earned",
          not ev(GREEN3 + [("exampleapp", None, "reverted", D(5))]))
    check("revert inside the window disqualifies even with 3 greens AFTER it",
          not ev([("exampleapp", None, "reverted", D(60))]
                 + [("exampleapp", None, "green", D(d)) for d in (10, 20, 30)]))
    check("revert aged out (>90d) + 3 greens after => earned again",
          ev([("exampleapp", None, "reverted", D(95))] + GREEN3))
    check("greens are counted only AFTER the latest revert",
          fast_lane.evaluate_track_record(
              [("exampleapp", None, "reverted", D(40))] + GREEN3
              + [("exampleapp", None, "green", D(50))], KEYS, now=NOW,
              max_reverts=5)[1]["green"] == 3)
    check("a record keyed on the IMAGE REPO counts for the component (docker.io/library normalised)",
          fast_lane.evaluate_track_record(
              [("other-name", "example-org/exampleapp", "green", D(d)) for d in (1, 2, 3)],
              KEYS, now=NOW)[0])
    check("another component's greens never count",
          not ev([("otherapp", "example-org/otherapp", "green", D(d)) for d in (1, 2, 3)]))

    # ---- per-type cooldown -----------------------------------------------------
    print("\ncooldown:")
    check("patch cooldown is 24h", fast_lane.cooldown_hours(POLICY, "patch") == 24)
    check("minor cooldown stays 48h", fast_lane.cooldown_hours(POLICY, "minor") == 48)
    check("malformed per-type value falls back to the base, never 0",
          fast_lane.cooldown_hours({**POLICY, "minimum_release_age_hours_by_type": {"patch": "x"}},
                                   "patch") == 48)
    live = __import__("yaml").safe_load((_REPO / "runbooks/auto-update-policy.yaml").read_text())
    check("LIVE policy: patch 24h / minor 48h",
          (fast_lane.cooldown_hours(live, "patch"), fast_lane.cooldown_hours(live, "minor")) == (24, 48))
    check("LIVE policy: earned lane is 3 green / 0 reverts / 90d",
          fast_lane.earned_policy(live) == {"min_green": 3, "window_days": 90, "max_reverts": 0})
    set_security([])
    ages = {"docker.io/example-org/exampleapp": 30.0}
    saved_age = cov.image_publish_age_hours
    cov.image_publish_age_hours = lambda repo, tag: ages.get(repo)
    try:
        check("direct-bump: a 30h-old PATCH passes the cooldown",
              cov.direct_bump_age_gate(dict(ITEM), POLICY) is None)
        held = cov.direct_bump_age_gate({**ITEM, "type": "minor", "target": "1.3.0"}, POLICY)
        check("direct-bump: a 30h-old MINOR is still held", bool(held) and "48h" in held, held)

        # ---- security bypass ---------------------------------------------------
        print("\nsecurity bypass:")
        ages["docker.io/example-org/exampleapp"] = 2.0
        sec = [("F-0000abcd", "critical",
                "`example-org/exampleapp:1.2.3`: 2 fixable CRITICAL CVE(s) — newer upstream tag available, bump the image — X")]
        set_security(sec)
        it = {**ITEM, "type": "minor", "target": "1.3.0"}
        check("a 2h-old minor fixing an open finding on the CURRENT tag skips the cooldown",
              cov.direct_bump_age_gate(it, POLICY) is None)
        check("...stamped fast_lane=security with the finding id",
              it.get("fast_lane") == "security" and it.get("security_ref") == "F-0000abcd", repr(it))
        check("the finding must name the CURRENT tag (a different tag does not bypass)",
              bool(cov.direct_bump_age_gate({**ITEM, "current": "1.2.2"}, POLICY)))
        check("bypass OFF in policy => cooldown holds",
              bool(cov.direct_bump_age_gate(dict(ITEM), {**POLICY, "security_cooldown_bypass": False})))
        set_security(None)
        check("security ledger UNREADABLE => cooldown holds (fail-safe)",
              bool(cov.direct_bump_age_gate(dict(ITEM), POLICY)))
        set_security(sec)
    finally:
        cov.image_publish_age_hours = saved_age
    check("an AR-accepted title never matches",
          fast_lane.match_security([("F-1", "accepted", "[AR-1] `example-org/exampleapp:1.2.3`: 2 fixable "
                                    "CRITICAL CVE(s) — newer upstream tag available")],
                                   ["example-org/exampleapp"], "1.2.3") is None)
    check("an 'already on the newest' title never matches",
          fast_lane.parse_security_row("`a/b:1`: 2 fixable CRITICAL CVE(s) — could NOT determine whether a newer upstream tag exists") is None)
    check("a fixable HIGH 'newer upstream tag available' title matches",
          fast_lane.parse_security_row("`a/b:v1.0`: 7 fixable HIGH CVE(s) — newer upstream tag available — X")
          == ("a/b", "1.0", "HIGH"))

    # ---- lane assignment: earned vs not -----------------------------------------
    print("\nassign_lane (direct-bump lane):")
    set_security([])
    set_ledger(GREEN3)
    (lane, reason, _), it = lane_with()
    check("EARNED: unverified-notes patch lands in AUTO", lane == "AUTO", reason)
    check("...with fast_lane=earned and the record in the reason",
          it.get("fast_lane") == "earned" and "EARNED autonomy" in reason, reason)
    (lane, reason, _), it = lane_with(rng=("unreadable", "range not read"))
    check("EARNED also covers an unreadable G3 range", lane == "AUTO", reason)
    set_ledger(GREEN3[:2])
    (lane, reason, _), _ = lane_with()
    check("NOT EARNED (2 greens): today's behaviour — PLAN", lane == "PLAN", reason)
    check("...and the reason says why it did not earn", "earned autonomy" in reason, reason)
    set_ledger(GREEN3 + [("exampleapp", None, "reverted", D(1))])
    (lane, _, _), _ = lane_with()
    check("REVERT RESETS: 3 greens + a revert => PLAN", lane == "PLAN")
    set_ledger(None)
    (lane, _, _), _ = lane_with()
    check("UNVERIFIED ledger => PLAN (never read as permission)", lane == "PLAN")
    set_ledger(GREEN3)
    (lane, _, _), _ = lane_with(g3=(True, "BREAKING CHANGE in notes"))
    check("earned + POSITIVE breaking signal => PLAN", lane == "PLAN")
    (lane, _, _), _ = lane_with(structural=(True, "migration added (stub)"))
    check("earned + POSITIVE structural signal => PLAN (structural runs on the earned path)", lane == "PLAN")
    (lane, _, _), _ = lane_with(item={**ITEM, "current": "1.2.3", "target": "2.0.0", "type": "major"})
    check("A MAJOR NEVER AUTO (earned)", lane == "PLAN")
    set_security([("F-0000abcd", "critical",
                   "`example-org/exampleapp:1.2.3`: 2 fixable CRITICAL CVE(s) — newer upstream tag available")])
    (lane, _, _), _ = lane_with(item={**ITEM, "target": "2.0.0", "type": "major"},
                                age_gate=cov.direct_bump_age_gate)
    check("A MAJOR NEVER AUTO (security-driven)", lane == "PLAN")
    set_security([])
    (lane, _, _), _ = lane_with(item={**ITEM, "current": "0.4.1", "target": "0.5.0", "type": "minor"})
    check("earned never lifts a 0.x MINOR", lane == "PLAN")
    (lane, _, _), _ = lane_with(policy={**POLICY, "deny": [{"match": "*exampleapp*", "reason": "x"}]})
    check("earned never lifts a deny rule", lane == "PLAN")
    (lane, _, _), _ = lane_with(policy={k: v for k, v in POLICY.items() if k != "earned_autonomy"})
    check("KILL SWITCH: no earned_autonomy block => PLAN", lane == "PLAN")
    (lane, reason, _), it = lane_with(g3=(False, "checked (clean)"))
    check("control: a checked clean patch is AUTO with fast_lane=normal",
          lane == "AUTO" and it.get("fast_lane") == "normal", repr((lane, it.get("fast_lane"))))

    # ---- auto-update.py PR lane ------------------------------------------------
    print("\nauto-update.py (PR lane):")
    set_security([("F-0000abcd", "critical",
                   "`example-org/exampleapp:1.2.3`: 2 fixable CRITICAL CVE(s) — newer upstream tag available")])
    saved = (au.upstream_release_age_hours, au.newest_commit_age_hours)
    au.upstream_release_age_hours = lambda *a, **k: (2.0, "stub")
    au.newest_commit_age_hours = lambda n: 2.0
    try:
        pr = {"number": 1, "title": "x", "labels": []}
        parsed = {"dep": "docker.io/example-org/exampleapp", "cur": "1.2.3", "new": "1.3.0",
                  "cur_known": True, "update_type": "minor"}
        info = {}
        check("security-driven minor passes G5 at 2h", au.age_gate(pr, parsed, POLICY, object(), info) is None)
        check("...recorded as fast_lane=security with the finding id",
              info.get("fast_lane") == "security" and info.get("security_ref") == "F-0000abcd", repr(info))
        info = {}
        held = au.age_gate(pr, {**parsed, "cur_known": False, "cur": "?"}, POLICY, object(), info)
        check("unknown current tag (bare title) => no bypass, cooldown holds", bool(held), repr(held))
        set_security([])
        au.upstream_release_age_hours = lambda *a, **k: (30.0, "stub")
        check("PR lane: 30h patch passes (24h)",
              au.age_gate(pr, {**parsed, "update_type": "patch", "new": "1.2.4"}, POLICY, object()) is None)
        check("PR lane: 30h minor held (48h)", bool(au.age_gate(pr, parsed, POLICY, object())))
        major = au.classify({"number": 2, "title": "feat(container)!: update example-org/exampleapp ( 1.2.3 → 2.0.0 )",
                             "labels": [{"name": "type/major"}]}, POLICY, None)
        check("A MAJOR NEVER AUTO in the PR lane (held at G1)",
              major["verdict"] == "hold" and major["gate"] in ("type", "parse"), repr(major))
    finally:
        au.upstream_release_age_hours, au.newest_commit_age_hours = saved

    # ---- revert resets: auto-update writes reverted rows -------------------------
    print("\nrevert recording:")
    written = []
    saved_rec = fast_lane.record
    fast_lane.record = lambda **kw: written.append(kw) or len(written)
    try:
        merged = [{"number": 7, "dep": "ghcr.io/a/one", "new": "1.0.1", "fast_lane": "earned"},
                  {"number": 8, "dep": "ghcr.io/b/two", "new": "2.0.1", "fast_lane": "security",
                   "security_ref": "F-0000abcd"}]
        out = au.record_autonomy(merged, "reverted")
        check("a reverted batch writes a `reverted` row for EVERY merged component",
              [w["outcome"] for w in written] == ["reverted", "reverted"]
              and {w["component"] for w in written} == {"one", "two"}, repr(written))
        check("...carrying each item's fast_lane and finding ref",
              written[1]["fast_lane"] == "security" and written[1]["finding_ref"] == "F-0000abcd")
        written.clear()
        au.record_autonomy(merged[:1], "green")
        check("a healthy batch writes `green`", written and written[0]["outcome"] == "green")
        fast_lane.record = lambda **kw: (_ for _ in ()).throw(RuntimeError("no DSN"))
        out = au.record_autonomy(merged[:1], "green")
        check("a failed record is LOUD in the result (error), never silent",
              out and "error" in out[0], repr(out))
    finally:
        fast_lane.record = saved_rec
    src = (_REPO / "runbooks/auto-update.py").read_text()
    check("commissioning: the revert path records BEFORE the operator notify",
          src.index('record_autonomy(merged, "reverted")') < src.index("from notify import ingest_or_notify"))
    assert fast_lane.evaluate_track_record is orig_now

    print()
    print("FAILED: " + ", ".join(FAILURES) if FAILURES else "all tests passed")
    return 1 if FAILURES else 0


def test_pytest_entry():
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())
