"""Regression tests for alert-record.py --reconcile (2026-10-13).

Closing an alert finding used to depend on a live Claude session handling the
bridge's "resolved" frame; when none did, a recovered critical kept paging
every 3h overnight. --reconcile closes findings whose alert is no longer
firing. Pinned here, in the safe direction:

  * the stable title parses back to (alertname, namespace, key);
  * an alert that is not firing at all closes;
  * a keyed finding stays open while ITS instance fires, even when the key
    is only part of a label value (TargetDown job="scrapeConfig/.../arag-scrape");
  * one instance resolving does not keep or close another's finding wrongly
    (ICloudBackupSyncStalled [mu] closes while [andrea] fires);
  * a Prometheus read without Watchdog is refused, never treated as "nothing fires".

Run:  python3 runbooks/tests/test-alert-record-reconcile.py
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "runbooks"))
spec = importlib.util.spec_from_file_location("alert_record", REPO / "runbooks/alert-record.py")
ar = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ar)

FAILURES: list[str] = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


FIRING = [
    {"alertname": "Watchdog"},
    {"alertname": "TargetDown", "job": "scrapeConfig/monitoring/arag-scrape"},
    {"alertname": "ICloudBackupSyncStalled", "account": "andrea"},
    {"alertname": "KumaMonitorDown", "monitor_name": "nuki-opener-bridge"},
    {"alertname": "MaintenanceWindowMissed", "namespace": "monitoring"},
]


def main() -> int:
    t = ar.make_title("TargetDown", "monitoring", "arag-scrape")
    check("title round-trips", ar.parse_title(t) == ("TargetDown", "monitoring", "arag-scrape"),
          str(ar.parse_title(t)))
    check("unkeyed title round-trips",
          ar.parse_title(ar.make_title("OpenClawPodNotReady", "ai", None)) == ("OpenClawPodNotReady", "ai", None))
    check("not firing at all -> close", not ar.still_firing("OpenClawPodNotReady", None, FIRING))
    check("unkeyed and firing -> keep", ar.still_firing("MaintenanceWindowMissed", None, FIRING))
    check("key inside a label value -> keep",
          ar.still_firing("TargetDown", "arag-scrape", FIRING))
    check("other instance firing -> close this one",
          not ar.still_firing("ICloudBackupSyncStalled", "mu", FIRING))
    check("same instance firing -> keep",
          ar.still_firing("ICloudBackupSyncStalled", "andrea", FIRING))
    check("one Kuma monitor resolving does not keep another open",
          not ar.still_firing("KumaMonitorDown", "iot-bar-shelf-shellys", FIRING))

    class _R:
        def __init__(self, body): self.body = body
        def read(self): return self.body
        def __enter__(self): return self
        def __exit__(self, *a): return False

    import json
    body = json.dumps({"data": {"alerts": [{"state": "firing", "labels": {"alertname": "TargetDown"}}]}}).encode()
    with mock.patch.object(ar.subprocess, "Popen"), mock.patch.object(ar, "_stop_pf"), \
            mock.patch.object(ar.socket, "create_connection"), \
            mock.patch("urllib.request.urlopen", return_value=_R(body)):
        try:
            ar.fetch_firing()
            check("read without Watchdog is refused", False, "no exception")
        except RuntimeError:
            check("read without Watchdog is refused", True)

    print(f"\n{'FAILED' if FAILURES else 'OK'}: {len(FAILURES)} failure(s)")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
