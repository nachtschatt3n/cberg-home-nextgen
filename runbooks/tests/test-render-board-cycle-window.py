#!/usr/bin/env python3
"""Regression: the action list must not be scoped by cycle_id ALONE.

`collect()`'s new_other query keyed only on `cycle_id=%s`. But the P4.1.6
contract REQUIRES a specialist to file any state-change recommendation via
`policy-cli.py finding add`, and `_policy_cli_cycle()` deliberately pins those
rows to a sentinel 'policy-cli' cycle -- "a real sweep cycle would be a lie
about provenance". Both designs are defensible; their intersection dropped
every agent-written row from the board.

Measured on cycle 0e37c7d3 (2026-09-11): 17 of 17 findings authored by that
cycle's own six specialists -- including an SLO burn-rate blind spot and a
Home Assistant availability blind spot -- rendered NOWHERE, while the board
still looked complete. That is worse than the 2026-08-16 failure, which at
least announced itself by producing no board at all.

The fix scopes by authorship WINDOW in addition to cycle_id, bounded by the
NEXT cycle's start (not this cycle's finished_at, which the reconcile stamps
mid-run -- a row authored after it would be dropped; on 0e37c7d3 that passed
only by a 55-second margin).

These are source-level guards: the query shape is the invariant, and asserting
it needs no database.

Run: python3 runbooks/tests/test-render-board-cycle-window.py
"""
import pathlib
import re
import sys

SRC = pathlib.Path("/Users/mu/code/cberg-home-nextgen/runbooks/render-board.py")
src = SRC.read_text()

fails = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}: {name}" + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        fails.append(name)


# Isolate the new_other query — the one that feeds the numbered action list.
m = re.search(r'out\["new_other"\]', src)
check("new_other assignment present", bool(m))
if not m:
    print(f"\n{len(fails)} FAILURE(S)")
    sys.exit(1)

# The SQL is the statement immediately preceding the assignment.
head = src[:m.start()]
q_start = head.rfind('"""SELECT')
query = head[q_start:head.find('"""', q_start + 3) + 3]

check("action-list query selects the finding id and section",
      "finding_id" in query and "section" in query)

# 1. The defect itself: cycle_id must not be the ONLY scoping predicate.
check(
    "query is NOT scoped by cycle_id alone",
    "first_seen" in query,
    "no first_seen predicate — hand-authored rows pinned to the policy-cli "
    "sentinel cycle will be invisible on the board",
)

# 2. It must still honour cycle_id (rows the scripts DO stamp).
check("query still matches rows stamped with the cycle", "cycle_id" in query)

# 3. The two predicates must be OR'd, not AND'd — an AND reintroduces the bug
#    while looking like the fix.
lowered = " ".join(query.split()).lower()
check(
    "cycle_id and first_seen are OR'd, not AND'd",
    re.search(r"cycle_id\s*=\s*%\(cid\)s\s+or\s+first_seen", lowered) is not None,
    "an AND between them still drops every unstamped row",
)

# 4. The upper bound must not be finished_at (stamped mid-run by the reconcile).
check(
    "upper bound is not this cycle's finished_at",
    not re.search(r"first_seen\s*<=?\s*coalesce\(\s*\(\s*select\s+finished_at", lowered),
    "finished_at as the ceiling drops rows authored after the reconcile",
)
check(
    "upper bound is derived from the next cycle's start",
    "min(started_at)" in lowered and "started_at >" in lowered,
    "expected MIN(started_at) of later cycles as the ceiling",
)

# 5. The lower bound must exist, or an old cycle's board absorbs today's rows.
check(
    "lower bound anchors on this cycle's started_at",
    re.search(r"first_seen\s*>=\s*\(\s*select\s+started_at", lowered) is not None,
    "without a lower bound, re-rendering an OLD cycle pulls in newer findings",
)

# 6. Pass-confirmation and AR-accepted rows stay excluded (pre-existing rule).
check("clean/accepted rows remain excluded",
      "'clean'" in query and "'accepted'" in query)

if fails:
    print(f"\n{len(fails)} FAILURE(S): {fails}")
    sys.exit(1)
print("\nall cycle-window guards pass")
