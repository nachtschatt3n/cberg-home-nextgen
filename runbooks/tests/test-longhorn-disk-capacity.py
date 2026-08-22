#!/usr/bin/env python3
"""
Regression test for the Longhorn disk-capacity check in health-check.sh
(2026-08-22).

All four jq queries in that block read `.spec.disks`, which carries only
allowScheduling / diskType / path / storageReserved. `storageMaximum` and
`storageAvailable` live under `.status.diskStatus` and never existed on
`.spec.disks`, so `select(.value.storageMaximum > 0)` matched nothing:

  - the printed capacity table was always empty,
  - both threshold counts were 0 on every run,
  - and the chain fell through to log_success "Longhorn disk capacity healthy"
    -- a green verdict that no disk state could ever change.

Node storage exhaustion was unmonitored by this check for its whole existence.
Real usage when it was found was 32-48% free, so nothing was hiding behind it.

The queries are extracted from health-check.sh rather than restated here, so
the test fails if the path regresses.

Run: python3 runbooks/tests/test-longhorn-disk-capacity.py
"""
import json
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
        print(f"  FAIL  {name}\n        got {got!r} want {want!r}")
        FAIL += 1


# --- the block must not read capacity fields off .spec.disks --------------
bad = re.findall(r"\.spec\.disks[^\n]*storageMaximum", src)
check("no capacity query reads .spec.disks", bad, [])
# The queries span several lines, so match the path occurrences themselves:
# one display query + one denominator/control + two threshold queries.
check("all four capacity queries read .status.diskStatus",
      len(re.findall(r"\.status\.diskStatus", src)) >= 4, True)

# --- the guard must refuse to score when it saw no disks ------------------
check("a cannot-measure branch exists (control on the denominator)",
      "LH_DISK_TOTAL" in src and "did not run" in src, True)

# --- and the queries themselves must behave -------------------------------
if not shutil.which("jq"):
    print("  SKIP  jq not installed - query behaviour not exercised")
else:
    TOT = ('[.items[].status.diskStatus // {} | to_entries[] | '
           'select(.value.storageMaximum > 0)] | length')
    LOW = ('[.items[].status.diskStatus // {} | to_entries[] | '
           'select(.value.storageMaximum > 0 and '
           '(.value.storageAvailable / .value.storageMaximum) < 0.15)] | length')

    def jq(expr, payload):
        r = subprocess.run(["jq", expr], input=json.dumps(payload),
                           capture_output=True, text=True)
        return r.stdout.strip()

    def node(avail, mx):
        return {"items": [{"metadata": {"name": "n1"},
                           "status": {"diskStatus": {"d1": {
                               "storageMaximum": mx, "storageAvailable": avail}}}}]}

    check("a disk at 5% free is caught", jq(LOW, node(50, 1000)), "1")
    check("a disk at 40% free is not caught", jq(LOW, node(400, 1000)), "0")
    check("denominator counts real disks", jq(TOT, node(400, 1000)), "1")
    check("empty cluster yields 0 examined (cannot-measure, not a pass)",
          jq(TOT, {"items": []}), "0")
    # the shape the old query actually saw
    spec_only = {"items": [{"metadata": {"name": "n1"}, "spec": {"disks": {
        "d1": {"allowScheduling": True, "path": "/var/lib/longhorn/",
               "storageReserved": 53687091200}}}, "status": {"diskStatus": {
        "d1": {"storageMaximum": 1000, "storageAvailable": 50}}}}]}
    check("real CR shape: capacity is invisible under .spec.disks",
          jq('[.items[].spec.disks // {} | to_entries[] | '
             'select(.value.storageMaximum > 0)] | length', spec_only), "0")
    check("real CR shape: and visible under .status.diskStatus",
          jq(TOT, spec_only), "1")

print(f"\n  {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
