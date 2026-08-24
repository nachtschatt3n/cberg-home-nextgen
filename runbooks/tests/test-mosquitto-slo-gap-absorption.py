#!/usr/bin/env python3
"""Regression test for the mosquitto-broker-up SLO's present-gate fix
(sweep_history Postgres `slo_definitions`, 2026-08-24).

Unlike most fixes in this repo, this one lives entirely in Postgres, not git
-- `slo_definitions` is operator-curated policy (see CLAUDE.md "Operator-
Curated Policy lives in sweep_history Postgres"), edited via
`runbooks/policy-cli.py slo`. There is no file for this test to extract from,
so it connects to the live DB and Prometheus instead, same best-effort
"skip gracefully if unreachable" pattern the rest of this suite uses for
live-cluster proofs.

The bug: `denominator: vector(1)` is a CONSTANT -- it can never go absent.
`numerator: (max(up{job="mosquitto-metrics"}) or on() vector(0))` falls back
to 0 whenever the `up` series is missing. Together, a Prometheus scrape
BLACKOUT (the up series vanishes because Prometheus itself couldn't reach
the target -- not because the broker was down) scored as numerator=0 /
denominator=1 = a full outage for that step, identical to a genuine broker
crash. `avg_over_time()` then baked that false 0 into the whole 7d window.

The fix, same present-gated pattern already used by longhorn-volume-health
and unifi-device-availability: `denominator: (count(up{job="..."}) * 0 + 1)`
evaluates to exactly 1 whenever Prometheus has ANY up{} series for the job
(up=1 or up=0 -- a genuine scrape that found the broker down still counts),
and goes ABSENT when the job has zero series at all. A blackout then makes
numerator/denominator empty for that step, and avg_over_time() skips it
instead of scoring it as 0% -- while a real broker-down scrape (up=0, series
still present) still scores as a real, un-skipped 0.

Run: python3 runbooks/tests/test-mosquitto-slo-gap-absorption.py
"""
import base64
import json
import shutil
import subprocess
import sys

PASS = FAIL = 0


def check(name, got, want):
    global PASS, FAIL
    if got == want:
        print(f"  PASS  {name}")
        PASS += 1
    else:
        print(f"  FAIL  {name}\n        got {got!r}\n        want {want!r}")
        FAIL += 1


if not shutil.which("kubectl"):
    print("  SKIP  kubectl not available")
    sys.exit(0)

dsn_secret = subprocess.run(
    ["kubectl", "get", "secret", "-n", "databases", "sweep-history", "-o", "json"],
    capture_output=True, text=True, timeout=15,
)
if dsn_secret.returncode != 0:
    print("  SKIP  cluster unreachable -- sweep-history secret not fetched")
    sys.exit(0)

try:
    raw_dsn = base64.b64decode(json.loads(dsn_secret.stdout)["data"]["WRITER_DSN"]).decode()
except (KeyError, json.JSONDecodeError):
    print("  SKIP  could not decode WRITER_DSN")
    sys.exit(0)

try:
    import psycopg
except ImportError:
    print("  SKIP  psycopg not installed")
    sys.exit(0)

# Rewrite the in-cluster FQDN to a local port-forward -- same technique
# sweep-run.py uses (see _kubectl_secret_dsn()'s own docstring on this).
FQDN = "postgresql.databases.svc.cluster.local"
pf = subprocess.Popen(
    ["kubectl", "port-forward", "-n", "databases", "svc/postgresql", "0:5432"],
    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
)
import re
import time
local_port = None
deadline = time.time() + 15
while time.time() < deadline:
    line = pf.stdout.readline()
    m = re.search(r"127\.0\.0\.1:(\d+)", line or "")
    if m:
        local_port = m.group(1)
        break

try:
    if not local_port:
        print("  SKIP  postgresql port-forward did not report a local port")
        sys.exit(0)

    dsn = raw_dsn.replace(f"{FQDN}:5432", f"127.0.0.1:{local_port}")

    with psycopg.connect(dsn, connect_timeout=10) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT query_json FROM slo_definitions WHERE name = %s",
            ("mosquitto-broker-up",),
        )
        row = cur.fetchone()

    check("mosquitto-broker-up SLO exists in slo_definitions", row is not None, True)
    if row:
        q = row[0]
        check("denominator is no longer the bare constant vector(1) -- the bug",
              q["denominator"].strip() == "vector(1)", False)
        check("denominator is now present-gated on the up{} series",
              "up{job=\"mosquitto-metrics\"}" in q["denominator"]
              and "count(" in q["denominator"], True)

        # --- behavioural proof against live Prometheus ---------------------
        if not shutil.which("curl"):
            print("  SKIP  curl not available -- live PromQL behaviour not exercised")
        else:
            ppf = subprocess.Popen(
                ["kubectl", "port-forward", "-n", "monitoring",
                 "svc/kube-prometheus-stack-prometheus", "0:9090"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
            )
            try:
                prom_port = None
                deadline2 = time.time() + 15
                while time.time() < deadline2:
                    line = ppf.stdout.readline()
                    m2 = re.search(r"127\.0\.0\.1:(\d+)", line or "")
                    if m2:
                        prom_port = m2.group(1)
                        break
                if not prom_port:
                    print("  SKIP  prometheus port-forward did not report a local port")
                else:
                    base = f"http://127.0.0.1:{prom_port}/api/v1/query"

                    def promql(query):
                        r = subprocess.run(
                            ["curl", "-s", "--data-urlencode", f"query={query}", base],
                            capture_output=True, text=True, timeout=15,
                        )
                        return json.loads(r.stdout)["data"]["result"]

                    # the OLD denominator: never goes absent, even for a job
                    # that has never existed -- this IS the bug, reproduced.
                    old_den = promql('vector(1)')
                    check("OLD denominator (vector(1)) is present even for a "
                          "nonexistent job (reproduces the bug)",
                          len(old_den) > 0, True)

                    # the NEW denominator: absent for a job that has zero series
                    fake_job = "totally-nonexistent-job-for-this-test-xyz"
                    new_den_absent = promql(f'(count(up{{job="{fake_job}"}}) * 0 + 1)')
                    check("NEW denominator is ABSENT for a job with zero series "
                          "(the fix: a genuine blackout is now distinguishable)",
                          len(new_den_absent), 0)

                    # the NEW denominator: present (=1) for the real job, whatever
                    # its current up value is
                    new_den_real = promql(q["denominator"])
                    check("NEW denominator is exactly 1 for the real mosquitto job "
                          "(unchanged behaviour in the normal case)",
                          new_den_real[0]["value"][1] if new_den_real else None, "1")

                    # full ratio, absence case -> must be empty (skipped by
                    # avg_over_time, not scored as a false 0)
                    full_ratio_absent = promql(
                        f'(max(up{{job="{fake_job}"}})) / '
                        f'(count(up{{job="{fake_job}"}}) * 0 + 1)'
                    )
                    check("the full ratio is EMPTY during a simulated blackout "
                          "-- avg_over_time() will skip this step, not score 0%",
                          len(full_ratio_absent), 0)
            finally:
                ppf.terminate()
                try:
                    ppf.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    ppf.kill()
finally:
    pf.terminate()
    try:
        pf.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pf.kill()

print(f"\n  {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
