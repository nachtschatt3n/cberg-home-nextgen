#!/usr/bin/env python3
"""Regression tests: sweep-run.py pushes the maintenance-window liveness
figures to the Pushgateway under the job the PrometheusRule reads
(F-2dabaddb).

`maintenance-plan.py --liveness-metrics` exposes window_runs_missing_count /
window_runs_stuck_count / window_runs_liveness_verified / lookback_days in
Prometheus text format, and the rule keys on those names plus
push_time_seconds{job="maintenance-window-liveness"} for staleness. Until
this push nothing carried the text to Prometheus, so absent() would have
fired forever and the staleness arm had nothing to measure.

Pinned here, against the REAL functions and a stub gateway (an in-process
HTTP server that records every request and keeps the last body per job, the
way pushgateway replaces a grouping wholesale):
  1. the job name and the required metric names are the rule's;
  2. liveness_metrics_payload() runs the real maintenance-plan.py: without a
     DSN the payload carries verified=0 + lookback and NO count, ends with a
     newline, and includes the sweep-cron block;
  3. push_metrics() POSTs the exact body to /metrics/job/<job> with the text
     content type; a 5xx is (False, ...) without raising; an unterminated
     body is refused before it is sent (pushgateway would 400);
  4. push_liveness_metrics() end-to-end with an injected gateway URL and an
     injected runner producing a VERIFIED payload from maintenance-plan.py's
     own liveness_figures(): every name the rule reads is in the stored body;
  5. push NOTHING on failure: a runner that exits non-zero, or a payload
     lacking the rule's names, leaves the stub's stored body untouched;
  6. the rule file, when present in the worktree, is parsed with PyYAML and
     every window_runs_* identifier in its expressions is in the verified
     payload, and its push_time_seconds job matches LIVENESS_PUSH_JOB;
  7. COMMISSIONING STRAWS: (a) a misspelled job name is NOT what the rule's
     staleness arm reads (the name check has teeth); (b) the stub confirms
     wholesale replacement — pushing an unverified payload after a verified
     one drops the count from the stored grouping — which is why a failed
     build pushes nothing.

Run: python3 runbooks/tests/test-sweep-liveness-push.py
"""
from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
import threading
from datetime import date
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

os.environ["_MISE_ACTIVATED"] = "1"
REPO = Path(__file__).resolve().parents[2]
RULE = REPO / "kubernetes/apps/monitoring/kube-prometheus-stack/app/maintenance-window-alerts.yaml"


def load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sr = load("sr", "runbooks/sweep-run.py")
mp = load("mp", "runbooks/maintenance-plan.py")

FAILURES: list[str] = []
ERROR_MARKS = ("Traceback", "Exception:", "Error:")


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


def count(population, pred) -> int:
    items = list(population)
    if not items:
        raise AssertionError("count(): EMPTY population — nothing was observed")
    joined = "\n".join(str(x) for x in items)
    if any(m in joined for m in ERROR_MARKS):
        raise AssertionError(f"count(): population carries error text: {joined[:120]!r}")
    return sum(1 for x in items if pred(x))


# ---- stub gateway ----------------------------------------------------------
REQUESTS: list[dict] = []
STORED: dict[str, str] = {}          # job -> last body (wholesale replace)


class Stub(BaseHTTPRequestHandler):
    def log_message(self, *a):        # quiet
        pass

    def do_GET(self):
        self.send_response(200 if self.path == "/-/ready" else 404)
        self.end_headers()

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n).decode("utf-8")
        REQUESTS.append({"path": self.path, "ctype": self.headers.get("Content-Type"), "body": body})
        m = re.fullmatch(r"/metrics/job/([^/]+)", self.path)
        if not m or "fail" in self.path:
            self.send_response(500)
            self.end_headers()
            return
        if not body.endswith("\n"):
            self.send_response(400)
            self.end_headers()
            return
        STORED[m.group(1)] = body
        self.send_response(200)
        self.end_headers()


srv = HTTPServer(("127.0.0.1", 0), Stub)
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{srv.server_address[1]}"

# 1 — names
check("job name is the rule's: maintenance-window-liveness", sr.LIVENESS_PUSH_JOB == "maintenance-window-liveness")
check("required metric names are the rule's verified/lookback pair",
      set(sr.LIVENESS_REQUIRED_METRICS) == {"window_runs_liveness_verified", "window_runs_liveness_lookback_days"})

# 2 — the real payload without a DSN
env_no_dsn = {k: v for k, v in os.environ.items() if k != "SWEEP_PG_DSN"}
payload, err = sr.liveness_metrics_payload(env_no_dsn)
check("real maintenance-plan.py --liveness-metrics produces a payload", payload is not None, err)
names = sr._metric_names(payload or "")
check("no DSN: verified=0 and lookback exposed, NO count (absent() is the unverified arm)",
      "window_runs_liveness_verified 0" in (payload or "") and "window_runs_liveness_lookback_days" in names
      and "window_runs_missing_count" not in names, payload)
check("the sweep-cron block rides in the same payload", "sweep_cron_liveness_verified" in names, str(names))
check("payload is newline-terminated", bool(payload) and payload.endswith("\n"))

# 3 — push_metrics against the stub
ok, why = sr.push_metrics(URL, sr.LIVENESS_PUSH_JOB, payload)
check("push_metrics: HTTP 200 on the stub", ok and why == "HTTP 200", why)
last = REQUESTS[-1]
check("push_metrics: POSTs the exact body to /metrics/job/<job> with the text content type",
      last["path"] == f"/metrics/job/{sr.LIVENESS_PUSH_JOB}" and last["body"] == payload
      and str(last["ctype"]).startswith("text/plain"), str(last)[:200])
ok5, why5 = sr.push_metrics(URL, "fail-job", payload)
check("push_metrics: a 5xx is (False, HTTP 500) — no raise", ok5 is False and "HTTP 500" in why5, why5)
before = len(REQUESTS)
oku, whyu = sr.push_metrics(URL, sr.LIVENESS_PUSH_JOB, payload.rstrip("\n"))
check("push_metrics: an unterminated body is refused BEFORE it is sent",
      oku is False and "newline" in whyu and len(REQUESTS) == before, whyu)

# 4 — end-to-end with a VERIFIED payload from maintenance-plan.py's own figures
fig = mp.liveness_figures(["nightly:2026-09-20"], ["nightly:2026-09-21"], True, date(2026, 9, 22))
sweep = {"verified": True, "missing": [], "missing_count": 0, "lookback_days": 7,
         "newest_cron_epoch": 1789000000}
VERIFIED = mp.liveness_metrics_text(fig) + mp.sweep_cron_metrics_text(sweep)


class Proc:
    def __init__(self, rc, out, err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


def runner_ok(cmd, **kw):
    assert cmd[1].endswith("maintenance-plan.py") and "--liveness-metrics" in cmd, cmd
    return Proc(0, VERIFIED)


ok, why = sr.push_liveness_metrics(env_no_dsn, gateway_url=URL, runner=runner_ok)
stored = STORED.get(sr.LIVENESS_PUSH_JOB, "")
RULE_NAMES = {"window_runs_missing_count", "window_runs_stuck_count",
              "window_runs_liveness_verified", "window_runs_liveness_lookback_days"}
check("end-to-end: verified payload pushed under the rule's job", ok and sr.LIVENESS_PUSH_JOB in why, why)
check("end-to-end: every name the rule reads is in the STORED grouping",
      RULE_NAMES <= sr._metric_names(stored), str(sorted(sr._metric_names(stored))))
check("end-to-end: the stored figures are the ones computed (1 missing, 1 stuck, verified 1)",
      'window_runs_missing_count{lookback_days="7"} 1' in stored and "window_runs_stuck_count 1" in stored
      and "window_runs_liveness_verified 1" in stored, stored)

# 5 — push NOTHING on failure
n_before, stored_before = len(REQUESTS), STORED.get(sr.LIVENESS_PUSH_JOB)
ok, why = sr.push_liveness_metrics(env_no_dsn, gateway_url=URL, runner=lambda *a, **k: Proc(1, "", "boom"))
check("runner exits non-zero: (False, nothing pushed) and the stub saw NO request",
      ok is False and "nothing pushed" in why and len(REQUESTS) == n_before, why)
ok, why = sr.push_liveness_metrics(env_no_dsn, gateway_url=URL,
                                   runner=lambda *a, **k: Proc(0, mp.sweep_cron_metrics_text(sweep)))
check("payload lacking the rule's names (sweep-cron block only): refused, NO request",
      ok is False and "lacks" in why and len(REQUESTS) == n_before, why)
check("...and the stored grouping is untouched (the previous snapshot keeps ageing on push_time_seconds)",
      STORED.get(sr.LIVENESS_PUSH_JOB) == stored_before)
ok, why = sr.push_liveness_metrics(env_no_dsn, gateway_url=URL,
                                   runner=lambda *a, **k: (_ for _ in ()).throw(OSError("no python")))
check("runner raising: (False, nothing pushed), no exception escapes", ok is False and "nothing pushed" in why, why)

# 6 — the rule file, when present
if RULE.exists():
    import yaml
    doc = yaml.safe_load(RULE.read_text())
    exprs = [" ".join(str(r.get("expr")).split()) for g in doc["spec"]["groups"] for r in g["rules"]]
    rule_metrics = {m for e in exprs for m in re.findall(r"\bwindow_runs_\w+", e)}
    rule_jobs = {m for e in exprs for m in re.findall(r'push_time_seconds\{job="([^"]+)"\}', e)}
    check("rule file: every window_runs_* the rule reads is in the verified payload",
          bool(rule_metrics) and rule_metrics <= sr._metric_names(VERIFIED), str(sorted(rule_metrics)))
    check("rule file: the staleness arm reads exactly this push's job",
          rule_jobs == {sr.LIVENESS_PUSH_JOB}, str(rule_jobs))
    check("rule file: an unverified run is an alert condition, not silence",
          count(exprs, lambda e: "window_runs_liveness_verified == 0" in e) >= 1, str(exprs))
    # 7a — STRAW: the name check has teeth
    check("STRAW (a): a misspelled job is NOT what the staleness arm reads",
          f"{sr.LIVENESS_PUSH_JOB}-x" not in rule_jobs)
else:
    print("  NOTE  rule file not in this worktree — names pinned from the rule's spec above; "
          "cross-check skipped (kubernetes/apps/monitoring/kube-prometheus-stack/app/maintenance-window-alerts.yaml)")

# 7b — STRAW: wholesale replacement is real, hence push-nothing-on-failure
sr.push_metrics(URL, sr.LIVENESS_PUSH_JOB, payload)            # the unverified payload
check("STRAW (b): pushing an unverified payload after a verified one DROPS the count from the grouping "
      "— a partial/failed push must therefore send nothing",
      "window_runs_missing_count" not in sr._metric_names(STORED[sr.LIVENESS_PUSH_JOB]))

srv.shutdown()
print(f"\n{len(FAILURES)} failure(s)" if FAILURES else "\nall checks passed")
sys.exit(1 if FAILURES else 0)
