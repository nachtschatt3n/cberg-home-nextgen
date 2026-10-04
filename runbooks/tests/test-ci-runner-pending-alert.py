#!/usr/bin/env python3
"""promtool unit tests for CIRunnerPodStuckPending (ci-runner-alerts.yaml).

Pins the 2026-10-04 false-positive fix: thermal-gated CI pods
(schedulingGates: ci.cberg.home/thermal) queue Pending by design and must NOT
fire, while every real runner fault (unschedulable after release,
ImagePullBackOff, hung clone, missing ConfigMap/Secret -- all just "Pending,
not gated" to kube-state-metrics) still must.

Both ways: the live rule must pass every case, AND each mutant below must FAIL
at least one case -- otherwise the suite could not see the bug it guards.
  - pre-fix rule (no exclusion)                 -> gated pod fires
  - exclusion via kube_pod_status_unschedulable -> unschedulable pod silenced
  - exclusion without "== 1"                    -> zero-valued reason silences

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
ALERT = "CIRunnerPodStuckPending"
RULE_LABELS = {
    "category": "ci-runner",
    "component": "the-ninth-banner-tests",
    "severity": "warning",
}


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


def series(pod, phase_pending, reason=None, extra=None):
    """Return input_series for one pod. values are promtool expanding notation."""
    out = [{
        "series": f'kube_pod_status_phase{{namespace="ci-runner",pod="{pod}",phase="Pending",job="kube-state-metrics"}}',
        "values": phase_pending,
    }]
    if reason:
        name, vals = reason
        out.append({
            "series": f'kube_pod_status_reason{{namespace="ci-runner",pod="{pod}",reason="{name}",job="kube-state-metrics"}}',
            "values": vals,
        })
    for metric, vals in (extra or []):
        out.append({
            "series": f'{metric}{{namespace="ci-runner",pod="{pod}",job="kube-state-metrics"}}',
            "values": vals,
        })
    return out


def firing(pod):
    return [{"exp_labels": dict(RULE_LABELS, namespace="ci-runner", pod=pod)}]


def case(input_series, checks):
    return {
        "interval": "1m",
        "input_series": input_series,
        "alert_rule_test": [
            {"eval_time": t, "alertname": ALERT, "exp_alerts": exp} for t, exp in checks
        ],
    }


TESTS = [
    # 1. thermal-gated for 2h (KSM: Pending + reason SchedulingGated, and
    #    kube_pod_status_unschedulable is ALSO 1 for gated pods) -> never fires
    case(series("gated", "1x120", ("SchedulingGated", "1x120"),
                [("kube_pod_status_unschedulable", "1x120")]),
         [("31m", []), ("2h", [])]),
    # 2. ungated + unschedulable (gate released, no node fits) -> fires after 30m
    case(series("unsched", "1x60", None,
                [("kube_pod_status_unschedulable", "1x60")]),
         [("25m", []), ("31m", firing("unsched"))]),
    # 3. ImagePullBackOff: scheduled, Pending, no reason series -> fires after 30m
    case(series("imagepull", "1x60", None,
                [("kube_pod_status_unschedulable", "0x60")]),
         [("25m", []), ("31m", firing("imagepull"))]),
    # 4. gated 40m, then released but stuck: the 30m timer starts at release
    case(series("released", "1x100", ("SchedulingGated", "1x40 stale"),
                [("kube_pod_status_unschedulable", "1x100")]),
         [("65m", []), ("72m", firing("released"))]),
    # 5. a zero-valued reason series must not silence a stuck pod
    case(series("zero-reason", "1x60", ("SchedulingGated", "0x60")),
         [("31m", firing("zero-reason"))]),
]

MUTANTS = {
    "pre-fix (no exclusion)":
        'max by (namespace, pod) (kube_pod_status_phase{namespace="ci-runner", phase="Pending"}) == 1',
    "exclusion via kube_pod_status_unschedulable":
        '(max by (namespace, pod) (kube_pod_status_phase{namespace="ci-runner", phase="Pending"}) == 1)'
        ' unless on (namespace, pod) (max by (namespace, pod) (kube_pod_status_unschedulable{namespace="ci-runner"}) == 1)',
    "exclusion without == 1":
        '(max by (namespace, pod) (kube_pod_status_phase{namespace="ci-runner", phase="Pending"}) == 1)'
        ' unless on (namespace, pod) max by (namespace, pod) (kube_pod_status_reason{namespace="ci-runner", reason="SchedulingGated"})',
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
        for name, expr in MUTANTS.items():
            m = dict(rule, expr=expr)
            rc, out = run(promtool, m, tmp, "mutant")
            if rc == 0:
                print(f"FAIL: mutant '{name}' passed every case -- suite is blind to it")
                bad += 1
            else:
                print(f"PASS: mutant '{name}' is caught")
        return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
