#!/usr/bin/env python3
"""Regression test: an `age_waive` entry can carry an EXPIRY, and a lapsed one
stops waiving — in BOTH lanes.

F-7eaae066 (2026-09-22). `age_waive` in runbooks/auto-update-policy.yaml is a
list of plain globs and the file's own comment says they are "PERMANENT until
removed — they waive the cooldown for ALL future bumps". Two of the three
entries are externally exposed services, so a one-day decision to let a fix
tag through at age 0 became a permanent supply-chain exemption that nothing
ever re-decides. Both consumers read the list as plain strings:

    auto-update.py  security_waived()        (the Renovate-PR lane)
    coverage.py     direct_bump_age_gate()   (the no-PR direct-bump lane)

The fix keeps the plain form (backward compatible — the live policy is still
all plain strings and must keep working unchanged) and adds
`{match: <glob>, until: <date>, reason: ...}`. `age_waivers()` in
auto-update.py is the ONE parser; coverage.py delegates to it so the two lanes
cannot disagree about whether a waiver has lapsed.

FAIL-CLOSED directions pinned here: an `until` that cannot be read, or a
mapping without `match`, does NOT waive (a relaxation that cannot be read must
not relax); a past `until` does not waive; and if coverage.py cannot load the
parser at all, NO waiver is in force.

Run: python3 runbooks/tests/test-age-waive-expiry.py
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import inspect
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


cov = _load("cov", "runbooks/coverage.py")
au = cov._auto_update_module()          # the SAME module object coverage.py delegates to

FAILURES: list[str] = []
TODAY = dt.date(2026, 9, 22)
PAST, FUTURE = dt.date(2026, 9, 21), dt.date(2026, 9, 23)


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


def counted(population, what: str) -> int:
    n = len(population)
    if n == 0:
        raise SystemExit(f"ABORT: empty population for {what} — instrument broken, not 'zero'")
    return n


def pr(dep="ghcr.io/example/exposed-app"):
    return {"number": 1, "title": "chore(deps): update exposed-app to v3.26.0",
            "labels": [], "_dep": dep}


def item(comp="exposed-app", repo="ghcr.io/example/exposed-app"):
    return {"component": comp, "kind": "image", "current": "3.25.1",
            "target": "3.26.0", "type": "minor", "image_repos": [repo]}


def policy(*entries):
    return {"minimum_release_age_hours": 48, "age_waive": list(entries)}


def main() -> int:
    print("test-age-waive-expiry")

    # ── the parser: every entry shape, both directions ─────────────────
    active, expired, malformed = au.age_waivers(policy("*mealie*"), today=TODAY)
    check("plain string glob is active (backward compatible)", active == ["*mealie*"])
    active, expired, malformed = au.age_waivers(
        policy({"match": "*mealie*", "until": FUTURE, "reason": "x"}), today=TODAY)
    check("mapping with a future `until` is active", active == ["*mealie*"] and not expired)
    active, expired, malformed = au.age_waivers(
        policy({"match": "*mealie*", "until": TODAY}), today=TODAY)
    check("`until` is INCLUSIVE — still active on the day itself", active == ["*mealie*"])
    active, expired, malformed = au.age_waivers(
        policy({"match": "*mealie*", "until": PAST}), today=TODAY)
    check("mapping with a past `until` is EXPIRED and not active",
          active == [] and expired == [("*mealie*", PAST)], f"{active} {expired}")
    active, expired, malformed = au.age_waivers(
        policy({"match": "*mealie*", "until": "2026-09-21"}), today=TODAY)
    check("a string date is read the same way as YAML's native date",
          active == [] and expired == [("*mealie*", PAST)])
    active, _e, _m = au.age_waivers(
        policy({"match": "*mealie*", "until": dt.datetime(2026, 9, 23, 4, 0)}), today=TODAY)
    check("a datetime `until` is read on its date", active == ["*mealie*"])
    active, _e, _m = au.age_waivers(policy({"match": "*mealie*"}), today=TODAY)
    check("a mapping WITHOUT `until` is the plain form (permanent)", active == ["*mealie*"])
    active, expired, malformed = au.age_waivers(
        policy({"match": "*mealie*", "until": "next tuesday"}), today=TODAY)
    check("an UNREADABLE `until` is malformed and does NOT waive (fail-closed)",
          active == [] and len(malformed) == 1 and "mealie" in malformed[0], str(malformed))
    active, _e, malformed = au.age_waivers(policy({"until": FUTURE}), today=TODAY)
    check("a mapping without `match` is malformed and does NOT waive", active == [] and malformed)
    active, _e, malformed = au.age_waivers(policy(42), today=TODAY)
    check("an unsupported entry shape is malformed and does NOT waive", active == [] and malformed)
    active, _e, _m = au.age_waivers({"age_waive": None}, today=TODAY)
    check("a missing/null list is simply empty", (active, _e, _m) == ([], [], []))
    active, expired, malformed = au.age_waivers(
        policy("*paperless-ngx*", {"match": "*mealie*", "until": PAST},
               {"match": "*music-assistant*", "until": FUTURE}), today=TODAY)
    check("mixed list: plain + future active, past expired, in order",
          active == ["*paperless-ngx*", "*music-assistant*"] and expired == [("*mealie*", PAST)])

    # ── the PR lane ────────────────────────────────────────────────────
    check("PR lane: plain glob waives",
          au.security_waived(pr(), policy("*exposed-app*")) is not None)
    check("PR lane: dated glob in force waives",
          au.security_waived(pr(), policy({"match": "*exposed-app*", "until": "2999-12-31"})) is not None)
    check("PR lane: LAPSED glob no longer waives",
          au.security_waived(pr(), policy({"match": "*exposed-app*", "until": "2000-01-01"})) is None)
    check("PR lane: unreadable expiry no longer waives",
          au.security_waived(pr(), policy({"match": "*exposed-app*", "until": "soon"})) is None)
    check("PR lane: a security-marked PR still waives regardless",
          au.security_waived({**pr(), "title": "fix(deps): security bump of exposed-app"},
                             policy({"match": "*exposed-app*", "until": "2000-01-01"})) is not None)

    # ── the direct-bump lane (coverage.py delegating to the same parser) ─
    cov.image_publish_age_hours = lambda repo, tag: 1.0     # young: only a waiver passes it
    check("direct lane: plain glob waives",
          cov.direct_bump_age_gate(item(), policy("*exposed-app*")) is None)
    check("direct lane: dated glob in force waives",
          cov.direct_bump_age_gate(item(), policy({"match": "*exposed-app*", "until": "2999-12-31"})) is None)
    hold = cov.direct_bump_age_gate(item(), policy({"match": "*exposed-app*", "until": "2000-01-01"}))
    check("direct lane: LAPSED glob no longer waives -> the cooldown HOLDS", hold is not None, str(hold))
    hold = cov.direct_bump_age_gate(item(), policy({"match": "*exposed-app*", "until": "?"}))
    check("direct lane: unreadable expiry -> HOLDS", hold is not None)
    check("direct lane: a repo glob still matches the image repository",
          cov.direct_bump_age_gate(item(comp="sidecar"), policy({"match": "*example/exposed-app*",
                                                                 "until": "2999-12-31"})) is None)
    real_loader = cov._auto_update_module
    try:
        def _boom():
            raise RuntimeError("parser unavailable")
        cov._auto_update_module = _boom
        check("direct lane: if the parser cannot load, NO waiver is in force (fail-closed)",
              cov.direct_bump_age_gate(item(), policy("*exposed-app*")) is not None)
    finally:
        cov._auto_update_module = real_loader
    check("coverage.py delegates rather than re-parsing (one parser, two lanes)",
          "age_waivers(" in inspect.getsource(cov._active_age_waivers)
          and "age_waive" not in inspect.getsource(cov.direct_bump_age_gate).split("_active_age_waivers")[0])

    # ── the LIVE policy file still parses under the new reader ─────────
    live = yaml.safe_load((REPO / "runbooks/auto-update-policy.yaml").read_text()) or {}
    entries = live.get("age_waive") or []
    counted(entries, "live age_waive entries")
    active, expired, malformed = au.age_waivers(live)
    check("live policy: no entry is malformed under the expiry-aware reader",
          malformed == [], str(malformed))
    check("live policy: every plain-string entry is still active (backward compatible)",
          all(e in active for e in entries if isinstance(e, str)))
    check("live policy: main() reports lapsed/unreadable entries once per run",
          "age_waivers(policy)" in inspect.getsource(au.main) and "EXPIRED" in inspect.getsource(au.main))

    # ── COMMISSIONING STRAW: the pre-fix reader (every glob permanent) ──
    real = au.age_waivers

    def straw(policy, today=None):
        globs = [e if isinstance(e, str) else (e or {}).get("match")
                 for e in (policy or {}).get("age_waive") or []]
        return [g for g in globs if g], [], []

    try:
        au.age_waivers = straw
        pr_leak = au.security_waived(pr(), policy({"match": "*exposed-app*", "until": "2000-01-01"}))
        direct_leak = cov.direct_bump_age_gate(item(), policy({"match": "*exposed-app*", "until": "2000-01-01"}))
        check("commissioning: under the pre-fix reader the LAPSED waiver waives in BOTH lanes "
              "— i.e. the two lapsed-glob assertions above would FAIL",
              pr_leak is not None and direct_leak is None,
              f"pr={pr_leak} direct={direct_leak}")
    finally:
        au.age_waivers = real

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} -> {', '.join(FAILURES)}")
        return 1
    print("all tests passed")
    return 0


def test_pytest_entry() -> None:
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())
