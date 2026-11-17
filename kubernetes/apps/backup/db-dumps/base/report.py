#!/usr/bin/env python3
"""Push the dump metrics to the Pushgateway, then fail the Job if the dump failed.

Runs as the main container after the dump init container. Reads
/work/metrics.prom and /work/result. POST (not PUT) so only the metric names
pushed here are replaced inside the group job=db-dumps,dbinstance=<INSTANCE>.
A failed push is itself a failure (fail loud). Stdlib only.
"""
import os
import sys
import urllib.error
import urllib.request


def main():
    instance = os.environ["INSTANCE"]
    gateway = os.environ.get("PUSHGATEWAY", "http://prometheus-pushgateway.monitoring:9091")
    work = os.environ.get("WORK_DIR", "/work")
    try:
        result = open(os.path.join(work, "result")).read().strip()
        body = open(os.path.join(work, "metrics.prom"), "rb").read()
    except OSError as exc:
        print("FATAL no dump result/metrics: %s" % exc)
        return 1
    url = "%s/metrics/job/db-dumps/dbinstance/%s" % (gateway.rstrip("/"), instance)
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "text/plain; version=0.0.4"})
    push_ok = True
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            print("pushed metrics (HTTP %s)" % resp.status)
    except (urllib.error.URLError, OSError) as exc:
        print("FATAL metrics push failed: %s" % exc)
        push_ok = False
    if result != "ok":
        print("dump result: %s" % result)
        return 1
    return 0 if push_ok else 1


if __name__ == "__main__":
    sys.exit(main())
