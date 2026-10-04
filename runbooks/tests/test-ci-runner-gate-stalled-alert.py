#!/usr/bin/env python3
"""promtool unit tests for CIRunnerThermalGateStalled (ci-runner-alerts.yaml).

Closes the detection gap of baaa2d7e: thermal-gated CI pods are skipped by
CIRunnerPodStuckPending and count as Job-active for CIRunnerJobStarved, so a
dead/wedged admitter (scripts/ninth-banner-admit.py, Mac-side, no metric of
its own) left them waiting silently until activeDeadlineSeconds. The rule
watches the admitter's EFFECT: the newest kube_pod_status_scheduled_time in
ci-runner is the last gate release.

Both ways: the live rule must pass every case, AND each mutant below must FAIL
at least one case -- otherwise the suite could not see the bug it guards.
  - no "never scheduled" branch      -> admitter-absent case stays silent
  - threshold 10 min (too tight)     -> healthy queue with a brake gap fires
  - no gated-pods condition          -> idle namespace with an old release fires
  - gated sum without "> 0"          -> zero-valued reason series fires
  - for: 0m                          -> fires before the 5m hold

Needs promtool (Prometheus 3.x): PATH, $PROMTOOL, or a mise install.
Fails (does not skip) when promtool is missing.
"""
import glob
import os
import shutil
import subprocess
import sys
import tempfile

import yaml

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RULES = os.path.join(
    ROOT, "kubernetes/apps/monitoring/kube-prometheus-stack/app/ci-runner-alerts.yaml"
)
ALERT = "CIRunnerThermalGateStalled"
RULE_LABELS = {
    "category": "ci-runner",
    "component": "the-ninth-banner-tests",
    "severity": "warning",
}
SPAN = 150  # minutes of input per case


def find_promtool():
    cand = os.environ.get("PROMTOOL") or shutil.which("promtool")
    if cand:
        return cand
    hits = sorted(glob.glob(os.path.expanduser(
        "~/.local/share/mise/installs/*prometheus*/*/promtool")))
    return hits[-1] if hits else None


def load_rule():
    doc = yaml.safe_load(open(RULES))
    for g in doc["spec"]["groups"]:
        for r in g["rules"]:
            if r.get("alert") == ALERT:
                return r
    raise SystemExit(f"FAIL: {ALERT} not found in {RULES}")


def gated(pod, values):
    return {
        "series": f'kube_pod_status_reason{{namespace="ci-runner",pod="{pod}",reason="SchedulingGated",job="kube-state-metrics"}}',
        "values": values,
    }


def released(pod, minute, until=SPAN):
    """Pod bound by the scheduler at `minute`; series exists from then until `until`."""
    head = f"_x{minute} " if minute else ""
    tail = " stale" if until < SPAN else ""  # pod deleted: KSM series goes stale
    return {
        "series": f'kube_pod_status_scheduled_time{{namespace="ci-runner",pod="{pod}",job="kube-state-metrics"}}',
        "values": f"{head}{minute * 60}x{until - minute - 1}{tail}",
    }


def queue(n, values=None):
    return [gated(f"q{i}", values or f"1x{SPAN}") for i in range(n)]


FIRING = [{"exp_labels": dict(RULE_LABELS, namespace="ci-runner")}]


def case(input_series, checks):
    return {
        "interval": "1m",
        "input_series": input_series,
        "alert_rule_test": [
            {"eval_time": t, "alertname": ALERT, "exp_alerts": exp} for t, exp in checks
        ],
    }


# Healthy busy queue under throttling: releases every 8 min with brake-sized
# 13-min gaps (the live max on 2026-10-04 was 13.2 min).
HEALTHY = [0, 8, 16, 29, 37, 45, 58, 66, 74, 87, 95, 103, 116, 124, 137, 145]

TESTS = [
    # 1. healthy busy queue with regular releases -> never fires
    case(queue(6) + [released(f"r{m}", m) for m in HEALTHY],
         [("30m", []), ("60m", []), ("100m", []), ("149m", [])]),
    # 2. gated pods, last release at t=0 (pod still listed) -> age > 30m from
    #    31m, +5m hold -> pending at 33m, firing by 37m
    case(queue(4) + [released("r0", 0)],
         [("30m", []), ("33m", []), ("37m", FIRING), ("120m", FIRING)]),
    # 3. admitter absent from the start: gated pods, no ci-runner pod ever
    #    scheduled (no scheduled_time series at all) -> fires after the 5m hold
    case(queue(3),
         [("3m", []), ("6m", FIRING)]),
    # 4. last released pods TTL-deleted while the queue waits -> fires
    case(queue(2) + [released("r0", 0, until=20), released("r5", 5, until=20)],
         [("19m", []), ("26m", FIRING)]),
    # 5. idle namespace (no gated pods), last release long ago -> silent
    case([released("r0", 0)],
         [("60m", []), ("149m", [])]),
    # 6. zero-valued SchedulingGated series (released pods keep a 0 series)
    #    with an old release -> silent
    case(queue(3, values=f"0x{SPAN}") + [released("r0", 0)],
         [("60m", [])]),
    # 7. queue drains: gated pods released at 40m -> stops firing
    case(queue(2, values=f"1x39 0x{SPAN - 40}") + [released("r0", 0), released("r40", 40)],
         [("38m", FIRING), ("45m", [])]),
]

LIVE = None  # filled in main()


def mutants(rule):
    e = rule["expr"]
    no_branch = (
        '(sum by (namespace) (kube_pod_status_reason{namespace="ci-runner", reason="SchedulingGated"}) > 0)'
        ' and on (namespace)'
        ' ((time() - max by (namespace) (kube_pod_status_scheduled_time{namespace="ci-runner"})) > 1800)'
    )
    no_gate = '(time() - max by (namespace) (kube_pod_status_scheduled_time{namespace="ci-runner"})) > 1800'
    no_gt0 = e.replace('reason="SchedulingGated"}) > 0\n)', 'reason="SchedulingGated"})\n)', 1)
    assert no_gt0 != e, "mutant 'gated sum without > 0' did not apply"
    tight = e.replace("> 1800", "> 600")
    assert tight != e
    return {
        "no 'never scheduled' branch": dict(rule, expr=no_branch),
        "threshold 10 min": dict(rule, expr=tight),
        "no gated-pods condition": dict(rule, expr=no_gate),
        "gated sum without > 0": dict(rule, expr=no_gt0),
        "for: 0m": dict(rule, **{"for": "0m"}),
    }


def run(promtool, rule, tmp, tag):
    r = {k: v for k, v in rule.items() if k != "annotations"}
    rules_f = os.path.join(tmp, f"rules-{tag}.yaml")
    test_f = os.path.join(tmp, f"test-{tag}.yaml")
    yaml.safe_dump({"groups": [{"name": "ci-runner.infra", "interval": "1m", "rules": [r]}]},
                   open(rules_f, "w"))
    yaml.safe_dump({"rule_files": [os.path.basename(rules_f)],
                    "evaluation_interval": "1m", "tests": TESTS}, open(test_f, "w"))
    p = subprocess.run([promtool, "test", "rules", test_f], cwd=tmp,
                       capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def main():
    promtool = find_promtool()
    if not promtool:
        print("FAIL: promtool not found (set $PROMTOOL or `mise install ubi:prometheus/prometheus`)")
        return 1
    rule = load_rule()
    with tempfile.TemporaryDirectory() as tmp:
        rc, out = run(promtool, rule, tmp, "live")
        if rc != 0:
            print("FAIL: live rule does not pass its cases\n" + out)
            return 1
        print(f"PASS: live {ALERT} passes {len(TESTS)} cases")
        bad = 0
        for name, m in mutants(rule).items():
            rc, out = run(promtool, m, tmp, "mutant")
            if rc == 0:
                print(f"FAIL: mutant '{name}' passed every case -- suite is blind to it")
                bad += 1
            else:
                print(f"PASS: mutant '{name}' is caught")
        return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
