"""Regression tests for runbooks/alert-record.py (P4.1.2).

Pins the identity contract that makes re-fires dedupe and resolves land:

1. Alert identity = (alertname, namespace, instance-key). A 4-hourly
   Alertmanager re-fire must hit the SAME fingerprint, and the resolve event
   (which arrives with the same labels) must find the row it closes.
2. Pod is NOT identity — pods churn on restart; a churned pod must not fork
   a second finding for the same alert.
3. instance-key IS identity — one alertname can cover many subjects
   (KumaMonitorDown fires per monitor); two monitors must not collapse onto
   one row, or resolving one would close the other.
4. The 'alert' section is a valid findings section, and stays OUT of the
   board's EXPECTED_SECTIONS — ad-hoc alert cycles must not render every
   sweep as "alert: DID NOT REPORT" (absence of alerts is not a gap).

Run:  python3 runbooks/tests/test-alert-record-identity.py
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ar = _load("ar", "runbooks/alert-record.py")
fw = _load("fw", "runbooks/lib/findings_writer.py")
rb = _load("rb", "runbooks/render-board.py")

FAILURES: list[str] = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


def main() -> int:
    print("test-alert-record-identity")

    t1, fp1, fid1 = ar.identity("SyntheticAlert", "office", None)
    t2, fp2, fid2 = ar.identity("SyntheticAlert", "office", None)
    check("re-fire hits the same fingerprint", fp1 == fp2 and fid1 == fid2)

    _, fp_a, _ = ar.identity("KumaMonitorDown", "monitoring", "Monitor A")
    _, fp_b, _ = ar.identity("KumaMonitorDown", "monitoring", "Monitor B")
    check("instance-key IS identity (per-monitor rows stay distinct)",
          fp_a != fp_b)

    _, fp_ns1, _ = ar.identity("SyntheticAlert", "office", None)
    _, fp_ns2, _ = ar.identity("SyntheticAlert", "media", None)
    check("namespace IS identity", fp_ns1 != fp_ns2)

    check("title carries no pod and no severity (stable across churn)",
          "pod" not in t1.lower() and "warning" not in t1.lower(), t1)

    check("finding_id derives from the fingerprint (resolve can rebuild it)",
          fid1 == fw.finding_id_from_fp(fp1))

    check("'alert' is a valid findings section",
          "alert" in fw.VALID_SECTIONS, sorted(fw.VALID_SECTIONS))
    check("'alert' stays OUT of board EXPECTED_SECTIONS "
          "(no phantom DID-NOT-REPORT gap)",
          "alert" not in rb.EXPECTED_SECTIONS, rb.EXPECTED_SECTIONS)

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} -> {', '.join(FAILURES)}")
        return 1
    print("all tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
