#!/usr/bin/env python3
"""
Regression test for the section-6 attack-pattern query budget (F-510bd6d5).

The defect: s6_attack_patterns() issued its nine-wildcard query through
ElasticPortForward.query() with the default timeout=15, and _exec_search()
caps the curl subprocess at timeout + 25 = 40s. Replayed by hand through the
same inside-pod path the query returned HTTP 200 after 51.3s, so every attempt
was killed and a HEALTHY indexer (section 7 succeeded against the same index in
the same run) was recorded as "Elasticsearch unavailable". That DEGRADED record
set the whole security section INCOMPLETE and vetoed auto-close for findings
the run had proven fixed.

Contract, asserted through the module's own functions (no grep-rebuilt logic):
  1. The budget's wall-clock cap clears the measured latency.
  2. s6 issues the attack query WITH that budget, not the default.
  3. A None result is reported NOT MEASURED — never "no attacks", never
     "Elasticsearch unavailable".
  4. _exec_search tells a timeout ("client cap", latency) apart from an
     unreachable indexer ("failed on all 3 attempts"), and records nothing
     when the query completes.
  5. COMMISSIONING STRAW: reverting the budget to the pre-fix default drops
     the cap below the measured latency again — the defect reproduces.

Run: python3 runbooks/tests/test-s6-attack-query-timeout.py
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("_MISE_ACTIVATED", "1")
ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
_spec = importlib.util.spec_from_file_location("sc", ROOT / "runbooks" / "security-check.py")
sc = importlib.util.module_from_spec(_spec)
with contextlib.redirect_stdout(io.StringIO()):
    _spec.loader.exec_module(sc)

PASS = FAIL = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}" + (f"\n        {detail}" if detail else ""))


class EsStub:
    """Records the timeout each query is issued with; answers None (no data)."""

    def __init__(self):
        self.calls: list[int] = []

    def query(self, body, timeout=15):
        self.calls.append(timeout)
        return None


def run_s6(es):
    with contextlib.redirect_stdout(io.StringIO()):
        return sc.s6_attack_patterns(es)


# 1 + 2 — the budget, and that s6 actually uses it
cap = sc._search_cap_seconds(sc.S6_ATTACK_QUERY_TIMEOUT_S)
check("budget cap clears the replayed 51.3s latency",
      cap > sc.S6_ATTACK_QUERY_MEASURED_S, f"cap={cap}s")
es = EsStub()
status, f, body = run_s6(es)
check("attack query is issued with the S6 budget, not the default",
      bool(es.calls) and es.calls[0] == sc.S6_ATTACK_QUERY_TIMEOUT_S, f"calls={es.calls}")

# 3 — a None result is NOT MEASURED
msgs = [m for _, m, _ in f._items]
check("None result -> WARNING saying NOT MEASURED",
      status == sc.WARNING and any("NOT MEASURED" in m for m in msgs), f"{msgs}")
check("None result never reads as 'no attacks'",
      "No attack patterns" not in body and not any("no attack" in m.lower() for m in msgs))
check("no residual 'Elasticsearch unavailable' label in s6",
      not any("Elasticsearch unavailable" in m for m in msgs), f"{msgs}")


# 4 — _exec_search: timeout vs unreachable vs completed
class Done:
    def __init__(self, rc, out):
        self.returncode, self.stdout, self.stderr = rc, out, ""


def exec_search_with(runner):
    saved_run, saved_sleep = sc.subprocess.run, sc.time.sleep
    sc.subprocess.run, sc.time.sleep = runner, (lambda s: None)
    before = list(sc.DEGRADED.reasons)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            res = sc._exec_search("monitoring", "es-0", "elasticsearch", "elastic:x",
                                  "logs-generic-default", {"q": 1}, 60)
    finally:
        sc.subprocess.run, sc.time.sleep = saved_run, saved_sleep
    return res, [r for r in sc.DEGRADED.reasons if r not in before]


def raise_timeout(*a, **k):
    raise subprocess.TimeoutExpired(cmd="curl", timeout=k.get("timeout"))


res, new = exec_search_with(raise_timeout)
check("3x timeout -> None, DEGRADED names the client cap and latency",
      res is None and len(new) == 1 and "client cap" in new[0]
      and "latency, not availability" in new[0], f"{new}")
check("3x timeout is NOT labelled 'Elasticsearch unavailable'",
      not any("Elasticsearch unavailable (" in r for r in new), f"{new}")
res, new = exec_search_with(lambda *a, **k: Done(7, ""))
check("3x rc!=0 -> None, DEGRADED says failed on all 3 attempts (unreachable)",
      res is None and len(new) == 1 and "failed on all 3 attempts" in new[0]
      and "rc=7" in new[0], f"{new}")
res, new = exec_search_with(lambda *a, **k: Done(0, '{"hits": {"total": {"value": 0}}}'))
check("a completing query returns its JSON and records nothing",
      res == {"hits": {"total": {"value": 0}}} and new == [], f"{res} {new}")

# 5 — COMMISSIONING STRAW: revert the budget to the pre-fix default
orig = sc.S6_ATTACK_QUERY_TIMEOUT_S
sc.S6_ATTACK_QUERY_TIMEOUT_S = 15          # ElasticPortForward.query()'s default
try:
    es2 = EsStub()
    run_s6(es2)
    straw_cap = sc._search_cap_seconds(es2.calls[0])
    check("STRAW: with the pre-fix default the cap sits below the 51.3s latency — "
          "the query is killed on every attempt (defect reproduces)",
          straw_cap < sc.S6_ATTACK_QUERY_MEASURED_S, f"cap={straw_cap}s")
finally:
    sc.S6_ATTACK_QUERY_TIMEOUT_S = orig
check("budget restored above the measured latency",
      sc._search_cap_seconds(sc.S6_ATTACK_QUERY_TIMEOUT_S) > sc.S6_ATTACK_QUERY_MEASURED_S)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
