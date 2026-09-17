#!/usr/bin/env python3
"""Regression test: plan_drift must name a STABLE-CHANNEL re-target, must never
go silent to do it, and must never invent a head (F-51fb8256, 2026-09-17).

THE DEFECT. `_plan_delivers()` built its drift hint out of `item["target"]` —
the raw arrow value from the version-check snapshot, i.e. the newest tag in the
registry. For an upstream that ships its beta on a BARE semver tag, the newest
tag IS the pre-release. Measured in ONE run of coverage.py: the n8n
max_rule_fallback record resolved the stable head to 2.39.6 (`stable` tag label,
digest-confirmed) while plan_drift told the planner "plan targets 2.39.5, but
2.40.1 is now published" — 2.40.1 being the beta.

THREE TRAPS THIS FILE HOLDS SHUT, each of which a reviewed draft fell into and
each of which is killed by a MUTANT below:

  1. SILENCE. "Suppress the row when the plan is already at the head" deletes
     the row from plan_drift entirely (drift=None makes _plan_delivers return
     (True, None)). Measured on the live nocodb plan — target 2026.09.0, which
     IS the resolved head — the row vanishes the moment the snapshot moves to
     the next calver month. It also hands match_plan's early exit to a plan
     that does not deliver the item.
  2. AN INVENTED HEAD. max_rule_fallbacks()'s up-to-date branch sets
     candidate=None, so a resolver that falls back to `current` publishes the
     DEPLOYED tag as "the STABLE-channel head" — with the evidence string for a
     DIFFERENT version attached. That is the original bug with more authority.
  3. A TEST THAT CANNOT SEE THE WIRING. The first draft of this file passed
     14/14 with report() no longer threading heads into assign_lane, and again
     with the producer emitting the wrong key name. Both are pinned below.

Run:  python3 runbooks/tests/test-coverage-drift-channel.py
"""

from __future__ import annotations

import importlib.util
import inspect
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("cov", REPO / "runbooks/coverage.py")
cov = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cov)

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


def item(comp, target, kind="image", current="0.0.0", utype="minor"):
    return {"component": comp, "kind": kind, "current": current,
            "target": target, "type": utype}


def plan(comp, target, kind="image", status="draft", plan_id=None):
    return {"plan_id": plan_id or f"{comp}-plan", "file": f"{comp}.md",
            "keys": {comp}, "status": status, "kind": kind,
            "current": "", "target": target}


N8N_EVIDENCE = ("`stable` tag label org.opencontainers.image.version=2.39.6, "
                "digest-confirmed")

FALLBACKS = [
    {"component": "n8n", "kind": "image", "status": "hold", "current": "2.38.7",
     "blocked_target": "2.40.1", "candidate": "2.39.6",
     "channel_evidence": N8N_EVIDENCE},
    {"component": "nocodb", "kind": "image", "status": "hold",
     "current": "2026.08.2", "candidate": "2026.09.0",
     "channel_evidence": "`latest` tag label, digest-confirmed"},
    {"component": "nextcloud-mcp", "kind": "image", "status": "hold",
     "candidate": None,
     "reason": "stable channel NOT confirmable — `stable` unreadable (HTTPError)"},
    {"component": "kube-prometheus-stack", "kind": "chart", "status": "hold",
     "candidate": None,
     "reason": "no stable-channel oracle exists for a CHART — holding (fail-safe)"},
    {"component": "nextcloud", "kind": "image", "status": "hold",
     "current": "31.0.9", "candidate": "32.0.1",
     "channel_evidence": "`stable` tag label, digest-confirmed"},
]

A1 = "A1 names the stable head 2.39.6 with its evidence, and does not offer 2.40.1 as the re-target"
A2 = "A2 unresolved channel STILL reports drift, labelled UNRESOLVED"
A3 = "A3 the raw published tag is ALWAYS named (a pre-release plan line keeps its comparison)"
A4 = "A4 plan already AT the stable head still produces a row (never silence)"
A5 = "A5 an IMAGE head is never offered as a CHART re-target"
A6 = "A6 a head off the plan's release LINE is flagged as a re-scope"
A7 = "A7 no input of any shape produces None"


def assess(note) -> dict:
    """{assertion: passed} for one (item, ptgt, pv, heads) -> str|None."""
    heads = cov.channel_resolved_heads(FALLBACKS)
    r = {}

    def call(it, ptgt, hd=heads):
        return note(it, ptgt, cov._ver_tuple(ptgt), hd)

    d = call(item("n8n", "2.40.1", current="2.38.7"), "2.39.5")
    r[A1] = bool(d and "2.39.6" in d and "digest-confirmed" in d
                 and "re-target to 2.39.6" in d)

    d = call(item("kube-prometheus-stack", "91.4.1", kind="chart", current="90.0.0"),
             "91.4.0")
    r[A2] = bool(d and "91.4.1" in d and "UNRESOLVED" in d.upper())

    d = call(item("harness-frontend", "0.5.9", current="0.5.0"), "0.5.4-alpha")
    r[A3] = bool(d and "0.5.9" in d)

    # THE SILENCE TRAP, in the shape that is live today: the nocodb plan target
    # IS the resolved head, and the snapshot has moved on one calver month.
    d = call(item("nocodb", "2026.10.0", current="2026.08.2"), "2026.09.0")
    r[A4] = bool(d) and "2026.10.0" in (d or "")

    d = call(item("nextcloud", "9.2.6", kind="chart", current="9.2.5"), "9.2.5")
    r[A5] = bool(d and "32.0.1" not in d)

    d = call(item("nextcloud", "31.1.0", current="31.0.9"), "31.0.10")
    r[A6] = bool(d and ("different release line" in d.lower()
                        or "re-scope" in d.lower()))

    # Never-None, over every shape: resolved/unresolved, ahead/behind/equal,
    # same line/different line, chart/image, missing kind.
    shapes = [
        (item("n8n", "2.40.1", current="2.38.7"), "2.39.5"),
        (item("n8n", "2.40.1", current="2.38.7"), "2.39.6"),
        (item("n8n", "2.39.6", current="2.38.7"), "2.39.6"),
        (item("n8n", "2.40.1", current="2.38.7"), "2.99.9"),
        (item("nocodb", "2026.10.0", current="2026.08.2"), "2026.09.0"),
        (item("nextcloud", "31.1.0", current="31.0.9"), "31.0.10"),
        (item("nextcloud", "9.2.6", kind="chart", current="9.2.5"), "9.2.5"),
        (item("unknown-thing", "5.0.1", current="5.0.0"), "5.0.0"),
        ({"component": "n8n", "target": "2.40.1", "current": "2.38.7",
          "type": "minor"}, "2.39.5"),          # no `kind` key at all
    ]
    r[A7] = all(isinstance(call(it, pt), str) and call(it, pt)
                for it, pt in shapes)
    return r


# ── straws: each MUST fail the assertions named against it ────────────────
def straw_open(it, ptgt, pv, heads):
    """The pre-fix behaviour: echo the snapshot's newest tag."""
    return f"plan targets {ptgt}, but {it['target']} is now published"


def straw_suppress_at_head(it, ptgt, pv, heads):
    """The reviewed draft: go SILENT when the plan is at or ahead of the head."""
    rec = (heads or {}).get((it.get("component", "").lower(), it.get("kind", "")))
    if not rec:
        return (f"plan targets {ptgt}, but {it['target']} is now published — "
                f"CHANNEL UNRESOLVED")
    hv = cov._ver_tuple(rec[0])
    if not hv or hv <= pv:
        return None
    return (f"plan targets {ptgt}; the STABLE-channel head is {rec[0]} ({rec[1]}) "
            f"— re-target to {rec[0]}, not {it['target']}")


def straw_closed(it, ptgt, pv, heads):
    """Fail-closed: say nothing unless certain. The silent zero."""
    rec = (heads or {}).get((it.get("component", "").lower(), it.get("kind", "")))
    if not rec:
        return None
    hv = cov._ver_tuple(rec[0])
    return None if (not hv or hv <= pv) else f"stable head {rec[0]}"


def straw_comp_only(it, ptgt, pv, heads):
    """Right head, wrong key: keyed on the component alone, so an IMAGE head
    leaks into a CHART drift row."""
    by_comp = {c: v for (c, _k), v in (heads or {}).items()}
    rec = by_comp.get(it.get("component", "").lower())
    if not rec:
        return (f"plan targets {ptgt}, but {it['target']} is now published — "
                f"CHANNEL UNRESOLVED")
    return (f"plan targets {ptgt}, but the STABLE-channel head is {rec[0]} "
            f"({rec[1]}) — re-target to {rec[0]}, not {it['target']}")


MUST_FAIL = {
    "straw_open (echo the newest tag — the pre-fix bug)": (straw_open, [A1]),
    "straw_suppress_at_head (the reviewed draft: silence at/above the head)": (
        straw_suppress_at_head, [A4, A7]),
    "straw_closed (emit nothing unless certain)": (straw_closed, [A2, A3, A4, A7]),
    "straw_comp_only (right head, wrong key — ignores kind)": (
        straw_comp_only, [A5]),
}


def main() -> int:
    print("test-coverage-drift-channel")

    have = hasattr(cov, "_drift_note") and hasattr(cov, "channel_resolved_heads")
    check("coverage.py exposes channel_resolved_heads() and _drift_note()", have,
          "pre-fix module: the drift hint is still item['target'] verbatim")
    if not have:
        print(f"\nFAILED: {len(FAILURES)} -> {', '.join(FAILURES)}")
        return 1

    # ── resolver purity ────────────────────────────────────────────────
    heads = cov.channel_resolved_heads(FALLBACKS)
    check("only POSITIVELY resolved channels become heads, keyed (component, kind)",
          set(heads) == {("n8n", "image"), ("nocodb", "image"), ("nextcloud", "image")},
          f"got {sorted(heads)}")
    check("n8n head is the digest-confirmed 2.39.6, with its evidence attached",
          heads[("n8n", "image")][0] == "2.39.6"
          and "digest-confirmed" in heads[("n8n", "image")][1],
          f"got {heads.get(('n8n', 'image'))}")
    check("an unconfirmable channel is ABSENT, never a head of None",
          ("nextcloud-mcp", "image") not in heads)
    check("a CHART is absent — max_rule_fallbacks() resolves no oracle for one",
          ("kube-prometheus-stack", "chart") not in heads)
    check("a resolved head with NO evidence string is still a head (never dropped)",
          cov.channel_resolved_heads(
              [{"component": "y", "kind": "image", "status": "hold",
                "candidate": "9.9.9"}]) == {("y", "image"): ("9.9.9", "")})
    check("no fallback records -> no heads (the honest pre-existing state)",
          cov.channel_resolved_heads([]) == {} and cov.channel_resolved_heads(None) == {})

    # THE INVENTED-HEAD TRAP. An up-to-date record whose DEPLOYED tag is AHEAD
    # of the resolved head must publish the HEAD, never what is running.
    uptodate = [{"component": "n8n", "kind": "image", "status": "up-to-date",
                 "current": "2.40.1", "candidate": None,
                 "channel_head": "2.39.6", "channel_evidence": N8N_EVIDENCE}]
    got = cov.channel_resolved_heads(uptodate)
    check("an up-to-date record publishes the RESOLVED head, never the deployed tag "
          "(a running pre-release must not become 'the stable head')",
          got == {("n8n", "image"): ("2.39.6", N8N_EVIDENCE)}, f"got {got}")
    check("a record with no resolved head at all is ABSENT (not `current`)",
          cov.channel_resolved_heads(
              [{"component": "z", "kind": "image", "status": "up-to-date",
                "current": "9.9.9", "candidate": None}]) == {})

    # AMBIGUITY degrades to unknown, never last-write-wins.
    check("two DIFFERENT heads for one (component, kind) -> UNRESOLVED, not last-wins",
          cov.channel_resolved_heads([
              {"component": "app", "kind": "image", "candidate": "1.4.0",
               "channel_evidence": "A"},
              {"component": "app", "kind": "image", "candidate": "17.6",
               "channel_evidence": "B"}]) == {})
    check("the SAME head twice is not ambiguous",
          cov.channel_resolved_heads([
              {"component": "app", "kind": "image", "candidate": "1.4.0"},
              {"component": "app", "kind": "image", "candidate": "1.4.0"}])
          == {("app", "image"): ("1.4.0", "")})

    # ── the behaviour battery, on the REAL implementation ──────────────
    for name, ok in assess(cov._drift_note).items():
        check(name, ok)

    # ── THE PRODUCER. The fixtures above hand-write `kind` and the head; the
    # real records come from max_rule_fallbacks(). Run it for real (only the
    # network oracle is stubbed) so a renamed/dropped key cannot pass. ──
    _orig_scv = cov.stable_channel_version
    _orig_bcs = cov.breaking_change_signal
    cov.stable_channel_version = lambda repo, *a, **k: ("2.39.6", N8N_EVIDENCE)
    cov.breaking_change_signal = lambda repo, ver, *a, **k: (False, "checked")
    try:
        recs = cov.max_rule_fallbacks(
            [{"component": "n8n", "kind": "image", "current": "2.38.7",
              "target": "2.40.1", "type": "minor",
              "image_repo": "n8nio/n8n"}],
            {"deny": [{"match": "*n8n*", "max": "patch", "reason": "channel hold"}]},
            {})
    finally:
        cov.stable_channel_version = _orig_scv
        cov.breaking_change_signal = _orig_bcs
    check("the PRODUCER emits a record this resolver can read (kind + head), so a "
          "renamed key cannot leave the fix inert while this file stays green",
          bool(recs) and cov.channel_resolved_heads(recs).get(("n8n", "image"),
                                                              ("", ""))[0] == "2.39.6",
          f"records={recs!r} heads={cov.channel_resolved_heads(recs)!r}")

    # ── end to end, through the call chain the sweep actually uses ─────
    n8n_item = item("n8n", "2.40.1", current="2.38.7")
    plans = [plan("n8n", "2.39.5", plan_id="n8n-2.39.5")]
    _, drift = cov.match_plan(n8n_item, {"n8n"}, plans, heads)
    check("match_plan() threads heads into the drift hint",
          bool(drift and "2.39.6" in drift), f"got {drift!r}")
    lane, reason, drift = cov.assign_lane(n8n_item, {"deny": []}, {}, plans, None, heads)
    check("assign_lane() stays PLAN and carries the channel-resolved drift",
          lane == "PLAN" and bool(drift and "2.39.6" in drift),
          f"got lane={lane} drift={drift!r}")

    # A plan that does NOT deliver the item must never win over one that does,
    # whatever the channel says. (A suppressed drift made the wrong plan win.)
    ordered = [plan("n8n", "2.39.6", plan_id="AT-HEAD"),
               plan("n8n", "2.40.1", plan_id="EXACT")]
    got_plan, _d = cov.match_plan(n8n_item, {"n8n"}, ordered, heads)
    check("an EXACT-target plan still wins over a drifted one when heads are present",
          got_plan["plan_id"] == "EXACT", f"got {got_plan['plan_id']}")

    # ── arity guard: the window agent's offline Step 0 call still works ─
    try:
        _, d3 = cov.match_plan(n8n_item, {"n8n"}, plans)
        ok3 = bool(d3) and "2.40.1" in d3 and "UNRESOLVED" in d3.upper()
    except TypeError as e:
        ok3, d3 = False, f"TypeError: {e}"
    check("match_plan() without heads still reports drift, marked UNRESOLVED", ok3,
          f"got {d3!r}")

    # ── THE WIRING. The fix only reaches the board if report() resolves the
    # heads and threads them into assign_lane. Asserted on the real source,
    # because a draft of this file passed 14/14 with exactly that line reverted.
    rsrc = inspect.getsource(cov.reconcile)
    check("reconcile() resolves the heads", "channel_resolved_heads(" in rsrc)
    check("reconcile() THREADS them into assign_lane (the line whose removal makes "
          "the whole fix inert while every behaviour test still passes)",
          bool(re.search(r"assign_lane\([^)]*channel_heads", rsrc, re.S)),
          "assign_lane() is called without channel_heads")

    # ── COMMISSIONING: every straw must FAIL the assertions named ──────
    for label, (fn, must_fail) in MUST_FAIL.items():
        got = assess(fn)
        still_passing = [a for a in must_fail if got.get(a)]
        check(f"commissioning: {label} is caught", not still_passing,
              f"assertions that did NOT discriminate: {still_passing}")

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} -> {', '.join(FAILURES)}")
        return 1
    print("all tests passed")
    return 0


def test_pytest_entry() -> None:
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
