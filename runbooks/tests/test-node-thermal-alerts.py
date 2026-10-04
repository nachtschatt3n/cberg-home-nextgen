#!/usr/bin/env python3
"""promtool unit tests for node-thermal-alerts.yaml (NUC14 thermals, 2026-10-04).

Covers NodeCPUPackageHot (warning + critical), NodeCPUThermalCritAlarm,
NodeCPUThermalThrottling, NodeNVMeHot (warning + critical at WCTEMP),
NodeCPUPackagePowerAtCap, and the per-node absent guards NodeRAPLMetricsMissing /
NodeCoretempMetricsMissing / NodeNVMeTempMetricsMissing.

Both ways: the live rules must pass every case, AND each mutant below must
FAIL at least one case -- otherwise the suite could not see the bug it guards.
  - temp rule without avg_over_time   -> single dipped sample resets for: (the
                                          spiky-sensor trap that made the old
                                          raw rule inert)
  - warning threshold 85              -> an 88 °C plateau fires
  - warning for: 0m                   -> fires before the 10m hold
  - critical threshold 95             -> a 99 °C plateau pages critical
  - throttle without keep_firing_for  -> one bursty episode resolves mid-gap
  - throttle threshold 50             -> healthy-node background (75/15m) fires
  - NVMe critical `>` instead of `>=` -> temp exactly at WCTEMP stays silent
  - power threshold 30 W              -> idle-ish 40 W fires
  - absent guards as global absent()  -> one node going blind stays silent

Needs promtool (Prometheus 3.x): PATH, $PROMTOOL, or a mise install.
Fails (does not skip) when promtool is missing.
"""
import copy
import glob
import os
import shutil
import subprocess
import sys
import tempfile

import yaml

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RULES = os.path.join(
    ROOT, "kubernetes/apps/monitoring/kube-prometheus-stack/app/node-thermal-alerts.yaml"
)
J = 'job="node-exporter"'
PKG = 'chip="platform_coretemp_0",sensor="temp1"'
NVME = 'chip="nvme_nvme0",sensor="temp1"'


def find_promtool():
    cand = os.environ.get("PROMTOOL") or shutil.which("promtool")
    if cand:
        return cand
    hits = sorted(glob.glob(os.path.expanduser(
        "~/.local/share/mise/installs/*prometheus*/*/promtool")))
    return hits[-1] if hits else None


def load_groups():
    doc = yaml.safe_load(open(RULES))
    return doc["spec"]["groups"]


def s(series, values):
    return {"series": series, "values": values}


def lab(inst, extra=None, **rule):
    d = {"instance": inst}
    d.update(extra or {})
    d.update(rule)
    return d


def pkg_labels(inst, sev):
    return lab(inst, {"job": "node-exporter", "chip": "platform_coretemp_0", "sensor": "temp1"},
               severity=sev, category="node-hardware", component="cpu-thermal")


def nvme_labels(inst, sev):
    return lab(inst, {"job": "node-exporter", "chip": "nvme_nvme0", "sensor": "temp1"},
               severity=sev, category="node-hardware", component="nvme-thermal")


def tests():
    t = []
    # --- NodeCPUPackageHot -------------------------------------------------
    # 1. sustained 95 °C: warning fires by 20m, no critical
    t.append({"interval": "30s", "input_series": [
        s(f"node_hwmon_temp_celsius{{{J},instance=\"n1\",{PKG}}}", "95x80")],
        "alert_rule_test": [
            {"eval_time": "8m", "alertname": "NodeCPUPackageHot", "exp_alerts": []},
            {"eval_time": "20m", "alertname": "NodeCPUPackageHot",
             "exp_alerts": [{"exp_labels": pkg_labels("n1", "warning")}]}]})
    # 2. spiky but hot: every 4th sample dips to 84 -> 5m avg ~92.75 -> fires
    spiky = " ".join(["95 95 95 84"] * 20)
    t.append({"interval": "30s", "input_series": [
        s(f"node_hwmon_temp_celsius{{{J},instance=\"n1\",{PKG}}}", spiky)],
        "alert_rule_test": [{"eval_time": "30m", "alertname": "NodeCPUPackageHot",
                             "exp_alerts": [{"exp_labels": pkg_labels("n1", "warning")}]}]})
    # 3. 88 °C plateau (Immich transcode band) -> silent
    t.append({"interval": "30s", "input_series": [
        s(f"node_hwmon_temp_celsius{{{J},instance=\"n1\",{PKG}}}", "88x80")],
        "alert_rule_test": [{"eval_time": "35m", "alertname": "NodeCPUPackageHot", "exp_alerts": []}]})
    # 4. 104 °C: critical by 8m (warning still pending)
    t.append({"interval": "30s", "input_series": [
        s(f"node_hwmon_temp_celsius{{{J},instance=\"n1\",{PKG}}}", "104x40")],
        "alert_rule_test": [
            {"eval_time": "3m", "alertname": "NodeCPUPackageHot", "exp_alerts": []},
            {"eval_time": "8m", "alertname": "NodeCPUPackageHot",
             "exp_alerts": [{"exp_labels": pkg_labels("n1", "critical")}]}]})
    # 5. 99 °C plateau: warning only, never critical
    t.append({"interval": "30s", "input_series": [
        s(f"node_hwmon_temp_celsius{{{J},instance=\"n1\",{PKG}}}", "99x80")],
        "alert_rule_test": [{"eval_time": "30m", "alertname": "NodeCPUPackageHot",
                             "exp_alerts": [{"exp_labels": pkg_labels("n1", "warning")}]}]})
    # --- NodeCPUThermalCritAlarm -------------------------------------------
    t.append({"interval": "30s", "input_series": [
        s(f"node_hwmon_temp_crit_alarm_celsius{{{J},instance=\"n1\",{PKG}}}", "0x10 1x20")],
        "alert_rule_test": [
            {"eval_time": "4m", "alertname": "NodeCPUThermalCritAlarm", "exp_alerts": []},
            {"eval_time": "8m", "alertname": "NodeCPUThermalCritAlarm", "exp_alerts": [
                {"exp_labels": lab("n1", {"job": "node-exporter", "chip": "platform_coretemp_0",
                                          "sensor": "temp1"}, severity="critical",
                                   category="node-hardware", component="cpu-thermal")}]}]})
    # --- NodeCPUThermalThrottling ------------------------------------------
    thr = lab("n2", {"job": "node-exporter", "package": "0"}, severity="warning",
              category="node-hardware", component="cpu-thermal")
    # 10 events / 30s = 300 per 15m for 60m, then flat (counter stops)
    t.append({"interval": "30s", "input_series": [
        s(f"node_cpu_package_throttles_total{{{J},instance=\"n2\",package=\"0\"}}",
          "0+10x120 1200x120")],
        "alert_rule_test": [
            {"eval_time": "25m", "alertname": "NodeCPUThermalThrottling", "exp_alerts": []},
            {"eval_time": "55m", "alertname": "NodeCPUThermalThrottling", "exp_alerts": [{"exp_labels": thr}]},
            # counter flat since 60m -> condition false from ~75m; keep_firing_for holds it
            {"eval_time": "95m", "alertname": "NodeCPUThermalThrottling", "exp_alerts": [{"exp_labels": thr}]},
            {"eval_time": "115m", "alertname": "NodeCPUThermalThrottling", "exp_alerts": []}]})
    # healthy-node background: 2.5 events/30s = 75 per 15m -> silent
    t.append({"interval": "30s", "input_series": [
        s(f"node_cpu_package_throttles_total{{{J},instance=\"n1\",package=\"0\"}}", "0+2.5x200")],
        "alert_rule_test": [{"eval_time": "90m", "alertname": "NodeCPUThermalThrottling", "exp_alerts": []}]})
    # --- NodeNVMeHot -------------------------------------------------------
    wct = f"node_hwmon_temp_max_celsius{{{J},instance=\"n1\",{NVME}}}"
    t.append({"interval": "30s", "input_series": [
        s(f"node_hwmon_temp_celsius{{{J},instance=\"n1\",{NVME}}}", "70x60"), s(wct, "81.85x60")],
        "alert_rule_test": [
            {"eval_time": "8m", "alertname": "NodeNVMeHot", "exp_alerts": []},
            {"eval_time": "15m", "alertname": "NodeNVMeHot",
             "exp_alerts": [{"exp_labels": nvme_labels("n1", "warning")}]}]})
    t.append({"interval": "30s", "input_series": [
        s(f"node_hwmon_temp_celsius{{{J},instance=\"n1\",{NVME}}}", "60x60"), s(wct, "81.85x60")],
        "alert_rule_test": [{"eval_time": "25m", "alertname": "NodeNVMeHot", "exp_alerts": []}]})
    # exactly AT WCTEMP -> critical (>=), warning still pending at 8m
    t.append({"interval": "30s", "input_series": [
        s(f"node_hwmon_temp_celsius{{{J},instance=\"n1\",{NVME}}}", "81.85x60"), s(wct, "81.85x60")],
        "alert_rule_test": [{"eval_time": "8m", "alertname": "NodeNVMeHot",
                             "exp_alerts": [{"exp_labels": nvme_labels("n1", "critical")}]}]})
    # --- NodeCPUPackagePowerAtCap ------------------------------------------
    pw = lab("n1", {"job": "node-exporter", "index": "0", "path": "/host/sys/class/powercap/intel-rapl:0"},
             severity="info", category="node-hardware", component="cpu-power")
    rapl = f"node_rapl_package_joules_total{{{J},instance=\"n1\",index=\"0\",path=\"/host/sys/class/powercap/intel-rapl:0\"}}"
    t.append({"interval": "30s", "input_series": [s(rapl, "0+1020x80")],  # 34 W
              "alert_rule_test": [
                  {"eval_time": "10m", "alertname": "NodeCPUPackagePowerAtCap", "exp_alerts": []},
                  {"eval_time": "25m", "alertname": "NodeCPUPackagePowerAtCap", "exp_alerts": [{"exp_labels": pw}]}]})
    t.append({"interval": "30s", "input_series": [s(rapl, "0+840x80")],  # 28 W
              "alert_rule_test": [{"eval_time": "35m", "alertname": "NodeCPUPackagePowerAtCap", "exp_alerts": []}]})
    # --- per-node absent guards --------------------------------------------
    # n1 has everything, n2 has nothing but node_uname_info -> each guard fires for n2 only
    def guard(name, comp):
        return {"eval_time": "35m", "alertname": name, "exp_alerts": [
            {"exp_labels": lab("n2", severity="warning", category="node-hardware", component=comp)}]}
    t.append({"interval": "30s", "input_series": [
        s(f"node_uname_info{{{J},instance=\"n1\"}}", "1x80"),
        s(f"node_uname_info{{{J},instance=\"n2\"}}", "1x80"),
        s(rapl, "0+300x80"),
        s(f"node_hwmon_temp_celsius{{{J},instance=\"n1\",{PKG}}}", "50x80"),
        s(f"node_hwmon_temp_celsius{{{J},instance=\"n1\",{NVME}}}", "40x80")],
        "alert_rule_test": [
            {"eval_time": "20m", "alertname": "NodeRAPLMetricsMissing", "exp_alerts": []},
            guard("NodeRAPLMetricsMissing", "cpu-power"),
            guard("NodeCoretempMetricsMissing", "cpu-thermal"),
            guard("NodeNVMeTempMetricsMissing", "nvme-thermal")]})
    # all nodes healthy -> all guards silent
    t.append({"interval": "30s", "input_series": [
        s(f"node_uname_info{{{J},instance=\"n1\"}}", "1x80"), s(rapl, "0+300x80"),
        s(f"node_hwmon_temp_celsius{{{J},instance=\"n1\",{PKG}}}", "50x80"),
        s(f"node_hwmon_temp_celsius{{{J},instance=\"n1\",{NVME}}}", "40x80")],
        "alert_rule_test": [
            {"eval_time": "35m", "alertname": a, "exp_alerts": []}
            for a in ("NodeRAPLMetricsMissing", "NodeCoretempMetricsMissing", "NodeNVMeTempMetricsMissing")]})
    return t


def find(groups, alert, severity=None):
    for g in groups:
        for r in g["rules"]:
            if r.get("alert") == alert and (severity is None or r["labels"]["severity"] == severity):
                return r
    raise SystemExit(f"FAIL: rule {alert}/{severity} not found")


def mutants(groups):
    out = {}

    def mut(name, fn):
        g = copy.deepcopy(groups)
        before = yaml.safe_dump(g)
        fn(g)
        assert yaml.safe_dump(g) != before, f"mutant '{name}' did not apply"
        out[name] = g

    def unsmooth(g):
        r = find(g, "NodeCPUPackageHot", "warning")
        r["expr"] = r["expr"].replace("avg_over_time(", "(").replace("[5m])", ")")
    mut("warning without avg_over_time", unsmooth)
    mut("warning threshold 85", lambda g: find(g, "NodeCPUPackageHot", "warning").update(
        expr=find(g, "NodeCPUPackageHot", "warning")["expr"].replace("> 90", "> 85")))
    mut("warning for: 0m", lambda g: find(g, "NodeCPUPackageHot", "warning").update({"for": "0m"}))
    mut("critical threshold 95", lambda g: find(g, "NodeCPUPackageHot", "critical").update(
        expr=find(g, "NodeCPUPackageHot", "critical")["expr"].replace("> 100", "> 95")))
    mut("throttle without keep_firing_for", lambda g: find(g, "NodeCPUThermalThrottling").pop("keep_firing_for"))
    mut("throttle threshold 50", lambda g: find(g, "NodeCPUThermalThrottling").update(
        expr=find(g, "NodeCPUThermalThrottling")["expr"].replace("> 100", "> 50")))
    mut("NVMe critical > instead of >=", lambda g: find(g, "NodeNVMeHot", "critical").update(
        expr=find(g, "NodeNVMeHot", "critical")["expr"].replace(">=", ">")))
    mut("power threshold 25", lambda g: find(g, "NodeCPUPackagePowerAtCap").update(
        expr=find(g, "NodeCPUPackagePowerAtCap")["expr"].replace("> 31", "> 25")))
    for a, m in (("NodeRAPLMetricsMissing", "node_rapl_package_joules_total"),
                 ("NodeCoretempMetricsMissing", f'node_hwmon_temp_celsius{{{PKG}}}'),
                 ("NodeNVMeTempMetricsMissing", f'node_hwmon_temp_celsius{{{NVME}}}')):
        mut(f"{a} as global absent()", lambda g, a=a, m=m: find(g, a).update(expr=f"absent({m})"))
    return out


def run(promtool, groups, tmp, tag):
    rf = os.path.join(tmp, f"{tag}-rules.yaml")
    tf = os.path.join(tmp, f"{tag}-test.yaml")
    # Annotations are prose; cases assert labels only (promtool compares both).
    groups = copy.deepcopy(groups)
    for g in groups:
        for r in g["rules"]:
            r.pop("annotations", None)
    yaml.safe_dump({"groups": groups}, open(rf, "w"), sort_keys=False)
    yaml.safe_dump({"rule_files": [os.path.basename(rf)], "evaluation_interval": "30s",
                    "tests": tests()}, open(tf, "w"), sort_keys=False)
    p = subprocess.run([promtool, "test", "rules", tf], cwd=tmp, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def main():
    promtool = find_promtool()
    if not promtool:
        print("FAIL: promtool not found (PATH, $PROMTOOL or mise install)")
        return 1
    groups = load_groups()
    fails = 0
    with tempfile.TemporaryDirectory() as tmp:
        rc, out = run(promtool, groups, tmp, "live")
        if rc != 0:
            print("FAIL: live rules fail the suite\n" + out)
            return 1
        print(f"PASS: live rules pass all {len(tests())} cases")
        for name, g in mutants(groups).items():
            safe = "".join(c if c.isalnum() else "-" for c in name)
            rc, _ = run(promtool, g, tmp, f"mut-{safe}")
            if rc == 0:
                print(f"FAIL: mutant '{name}' passed every case -- suite is blind to it")
                fails += 1
            else:
                print(f"PASS: mutant '{name}' is caught")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
