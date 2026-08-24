#!/usr/bin/env python3
"""Regression tests for the three ES "error context" queries in
health-check.sh (2026-08-24).

Two independent bugs, present in all three copies of this query (infra
namespaces, home-automation, and the standalone "ES Log Insights" section):

  1. A `#` comment sat on a line INSIDE the JSON body passed to
     Elasticsearch's `_search` endpoint. Elasticsearch's JSON parser rejects
     it outright (`x_content_parse_exception`), so the query has been
     completely dead since it was written -- not silently wrong, silently
     NOTHING: the except branch in the Python that parses the response
     printed "ES query parse error: 'hits'" and the section moved on.

  2. Independent of (1): `{"bool": {"must_not": {...}}}` was nested as a
     THIRD entry inside the `should` array, with `minimum_should_match: 1`.
     That does not exclude anything -- it is an OR-branch that matches every
     document NOT containing the excluded term, which is nearly the entire
     index. Verified live against this cluster 2026-08-24: the should-branch
     form returns 30,077,958 hits over 7 days; moving `must_not` to its
     correct place, a TOP-LEVEL sibling of `should` (the form already used at
     the already-fixed 24h check elsewhere in this file), returns 38,213 --
     an ~800x over-count on this run (this had been separately measured as a
     77x over-count on an earlier cycle; the exact multiplier depends on the
     day's DNS traffic, the defect's presence does not).

Run: python3 runbooks/tests/test-es-log-insights-query.py
"""
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

HC = pathlib.Path(__file__).resolve().parents[1] / "health-check.sh"
src = HC.read_text()
PASS = FAIL = 0


def check(name, got, want):
    global PASS, FAIL
    if got == want:
        print(f"  PASS  {name}")
        PASS += 1
    else:
        print(f"  FAIL  {name}\n        got {got!r}\n        want {want!r}")
        FAIL += 1


# --- locate and extract all three query bodies -----------------------------
ANCHORS = [
    "ES enrichment: 7-day error context for infra namespaces",
    "ES enrichment: 7-day HA error trends by pod",
    "Top Error Producers (7d)",
]

bodies = {}
for anchor in ANCHORS:
    i = src.index(anchor)
    start = src.index("'{", i) + 1
    end = src.index("}')", start) + 1
    bodies[anchor] = src[start:end]

check("all three query anchors were found", len(bodies), len(ANCHORS))

for anchor, body in bodies.items():
    # --- bug 1: no bare '#' inside the JSON body ---------------------------
    check(f"[{anchor[:30]}...] no stray '#' character in the JSON body",
          "#" in body, False)

    # --- bug 1, the control: the body must actually PARSE as JSON ----------
    try:
        parsed = json.loads(body)
        check(f"[{anchor[:30]}...] body parses as valid JSON", True, True)
    except json.JSONDecodeError as e:
        check(f"[{anchor[:30]}...] body parses as valid JSON ({e})", False, True)
        continue

    # --- bug 2: must_not must be a TOP-LEVEL sibling of should --------------
    bool_query = parsed["query"]["bool"]
    check(f"[{anchor[:30]}...] must_not is a top-level key of the bool query",
          "must_not" in bool_query, True)
    should_entries = bool_query.get("should", [])
    nested_must_not = any(
        isinstance(e, dict) and "bool" in e and "must_not" in e.get("bool", {})
        for e in should_entries
    )
    check(f"[{anchor[:30]}...] must_not is NOT nested inside a should-branch "
          "(the bug: matches nearly everything, defeats the exclusion)",
          nested_must_not, False)

    # --- the total must be trustworthy, not silently capped at 10000 -------
    check(f"[{anchor[:30]}...] track_total_hits is set (the printed total "
          "would otherwise silently cap at Elasticsearch's 10000 default)",
          parsed.get("track_total_hits"), True)

# --- behavioural proof: run the ACTUAL fixed query text against a synthetic
# in-memory match set, replicating Elasticsearch's own should/must_not
# semantics, so a future regression that reintroduces the nested form fails
# this test even without a live cluster.
def es_bool_would_match(bool_query, doc_text):
    should = bool_query.get("should", [])
    msm = bool_query.get("minimum_should_match", 0)
    must_not = bool_query.get("must_not", [])

    def wildcard_hit(clause, text):
        if "wildcard" in clause:
            pattern = clause["wildcard"]["body.text"]
            needle = pattern.strip("*").upper()
            return needle in text.upper()
        if "bool" in clause and "must_not" in clause["bool"]:
            inner = clause["bool"]["must_not"]
            return not wildcard_hit(inner, text)
        return False

    should_matches = sum(1 for c in should if wildcard_hit(c, doc_text))
    if should and should_matches < msm:
        return False
    for c in must_not:
        if wildcard_hit(c, doc_text):
            return False
    return True


# a real CoreDNS "successful answer" log line -- must NOT match "error"
DNS_SUCCESS = "10.0.0.1:53 - NOERROR"
# a genuine error line
REAL_ERROR = "connection refused: ERROR dialing upstream"

for anchor, body in bodies.items():
    parsed = json.loads(body)
    bq = parsed["query"]["bool"]
    check(f"[{anchor[:30]}...] a genuine ERROR line still matches",
          es_bool_would_match(bq, REAL_ERROR), True)
    check(f"[{anchor[:30]}...] a NOERROR (successful DNS) line does NOT match "
          "-- this is the exact defect: it used to",
          es_bool_would_match(bq, DNS_SUCCESS), False)

# --- live behavioural proof against the real cluster, best-effort ----------
def es_available():
    return shutil.which("kubectl") is not None


if not es_available():
    print("  SKIP  kubectl not available -- live ES check not exercised")
else:
    pw = subprocess.run(
        ["kubectl", "get", "secret", "elasticsearch-es-elastic-user",
         "-n", "monitoring", "-o", "jsonpath={.data.elastic}"],
        capture_output=True, text=True, timeout=15,
    )
    if pw.returncode != 0 or not pw.stdout.strip():
        print("  SKIP  ES credentials unavailable -- live check not exercised")
    else:
        import base64
        password = base64.b64decode(pw.stdout).decode()
        pf = subprocess.Popen(
            ["kubectl", "port-forward", "-n", "monitoring",
             "svc/elasticsearch-es-http", "19277:9200"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            import time
            connected = False
            for _ in range(15):
                r = subprocess.run(
                    ["curl", "-k", "-s", "-m", "2", "-u", f"elastic:{password}",
                     "https://127.0.0.1:19277/"],
                    capture_output=True, text=True,
                )
                if r.returncode == 0:
                    connected = True
                    break
                time.sleep(0.5)
            if not connected:
                print("  SKIP  ES unreachable via port-forward -- live check not exercised")
            else:
                body = bodies["Top Error Producers (7d)"]
                r = subprocess.run(
                    ["curl", "-k", "-s", "-m", "20", "-u", f"elastic:{password}",
                     "-X", "POST", "https://127.0.0.1:19277/logs-generic-default/_search",
                     "-H", "Content-Type: application/json", "-d", body],
                    capture_output=True, text=True,
                )
                d = json.loads(r.stdout)
                check("live cluster: the fixed query returns a hits.total (no parse error)",
                      "error" in d, False)
                total = d.get("hits", {}).get("total", {}).get("value")
                check("live cluster: total is a plausible 7d error count, not a "
                      "should-branch over-count in the tens of millions",
                      isinstance(total, int) and total < 1_000_000, True)
        finally:
            pf.terminate()
            try:
                pf.wait(timeout=3)
            except subprocess.TimeoutExpired:
                pf.kill()

print(f"\n  {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
