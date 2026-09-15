"""Regression tests for the s5 cross-app auth-failure RECENCY qualifier
(F-ddd38e77, 2026-09-15).

The 7-day window on the cross-app 401/403 count is the right net for a
low-and-slow pattern. It also kept a one-day burst on the board as a WARNING
for a full week after its cause was fixed: arag-web retried Paperless with a
deleted token for seven hours on 2026-09-14 (5,633 log lines), the token was
re-minted the same morning, and the namespace stayed >500/7d until the day
aged out of the window — re-reported every cycle with nothing left to do.

The qualifier asks the same query over the last 24 h and warns only while
the namespace is STILL failing at the 7-day bar's own daily rate (500/7 ≈
71/day). Both directions are pinned, because a suppressor on a security
detector is the one place "it fixed the symptom" is not evidence:

  * a steady attacker at >= 72/day still warns;
  * a burst that ended reads as subsided;
  * an UNKNOWN 24 h count (ES error) warns — a failed recency read can never
    silence a warning;
  * the 24 h query is the same body with only the time range swapped, so it
    counts the same thing the 7 d query counted.

Run:  python3 runbooks/tests/test-s5-auth-burst-recency.py
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
os.environ.setdefault("_MISE_ACTIVATED", "1")
sys.path.insert(0, str(_REPO / "runbooks"))
_spec = importlib.util.spec_from_file_location(
    "seccheck_under_test", _REPO / "runbooks" / "security-check.py")
_sec = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_sec)

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


class StubES:
    """Returns a canned aggregation; records the bodies it was asked."""

    def __init__(self, buckets, fail=False):
        self.buckets, self.fail, self.bodies = buckets, fail, []

    def query(self, body, timeout=15):
        self.bodies.append(body)
        if self.fail:
            return None
        return {"hits": {"total": {"value": sum(b["doc_count"] for b in self.buckets)}},
                "aggregations": {"by_namespace": {"buckets": self.buckets}}}


def main() -> int:
    print("test-s5-auth-burst-recency")
    T = _sec.AUTH_FAIL_7D_THRESHOLD
    daily = T / 7

    v = _sec.auth_burst_verdict
    check("under the 7d bar -> ok regardless of 24h", v(T, 400) == "ok")
    check("the live case: 5646/7d but 0/24h -> subsided", v(5646, 0) == "subsided")
    check("burst tail just under the daily rate -> subsided", v(5646, int(daily)) == "subsided")
    check("steady attacker at the daily rate -> still warns", v(5646, int(daily) + 1) == "warn")
    check("still hammering -> warns", v(5646, 4000) == "warn")
    check("UNKNOWN 24h count -> warns (fail toward surfacing)", v(5646, None) == "warn")

    # the 24h query is the SAME query with only the range swapped
    body = {"size": 0,
            "query": {"bool": {"should": [{"wildcard": {"body.text": {"value": "*unauthorized*"}}}],
                               "minimum_should_match": 1,
                               "filter": [{"range": {"@timestamp": {"gte": "now-7d"}}}]}},
            "aggs": {"by_namespace": {"terms": {"field": "resource.attributes.k8s.namespace.name", "size": 15}}}}
    es = StubES([{"key": "office", "doc_count": 3}, {"key": "ai", "doc_count": 1}])
    got = _sec.auth_recent_counts(es, body)
    check("recent counts keyed by namespace", got == {"office": 3, "ai": 1}, f"got {got}")
    sent = es.bodies[-1]
    check("24h query keeps the should-clauses and aggregation of the 7d query",
          sent["query"]["bool"]["should"] == body["query"]["bool"]["should"]
          and sent["aggs"] == body["aggs"])
    check("24h query swaps ONLY the range",
          sent["query"]["bool"]["filter"] == [{"range": {"@timestamp": {"gte": "now-24h"}}}])
    check("the caller's 7d body is not mutated",
          body["query"]["bool"]["filter"][0]["range"]["@timestamp"]["gte"] == "now-7d")
    check("ES failure -> None (caller keeps the plain 7d verdict)",
          _sec.auth_recent_counts(StubES([], fail=True), body) is None)

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
