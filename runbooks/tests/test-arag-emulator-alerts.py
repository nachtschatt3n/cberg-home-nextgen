#!/usr/bin/env python3
"""promtool unit tests for the arag-scrape emulator rules in macos-apps-alerts.yaml.

Covers the 2026-10-04 user-stopped exclusion on AragScrapeEmulatorDown and its
guard AragScrapeEmulatorUserStoppedLong:
  - user_stopped=1, up=0, process_up=0 for 60m -> Down must NOT fire
  - user_stopped=0, up=0, process_up=0 for 60m -> Down MUST fire
  - no user_stopped series at all (older build) -> Down MUST fire
  - process_up=1, up=0                         -> Down must NOT fire
  - user_stopped=1 for 8h                      -> UserStoppedLong fires
  - user_stopped=1 for 6h                      -> UserStoppedLong not yet

Both ways: the live rules must pass every case, AND each mutant must FAIL at
least one case -- otherwise the suite could not see the bug it guards.

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
    ROOT, "kubernetes/apps/monitoring/kube-prometheus-stack/app/macos-apps-alerts.yaml"
)
GROUP = "arag-scrape.health"
INST = "mac-mini:9100"
JOB = "scrapeConfig/monitoring/arag-scrape"
SEL = f'instance="{INST}",job="{JOB}"'
DOWN = "AragScrapeEmulatorDown"
LONG = "AragScrapeEmulatorUserStoppedLong"


def find_promtool():
    cand = os.environ.get("PROMTOOL") or shutil.which("promtool")
    if cand:
        return cand
    hits = sorted(glob.glob(os.path.expanduser(
        "~/.local/share/mise/installs/*prometheus*/*/promtool")))
    return hits[-1] if hits else None


def load_groups():
    doc = yaml.safe_load(open(RULES))
    return [g for g in doc["spec"]["groups"] if g["name"] == GROUP]


def s(metric, values):
    return {"series": f"arag_scrape_emulator_{metric}{{{SEL}}}", "values": values}


def labels():
    return {"instance": INST, "job": JOB, "severity": "warning",
            "category": "macos", "component": "arag-scrape"}


def case(series, alert, at, fires):
    return {"interval": "1m", "input_series": series,
            "alert_rule_test": [{"eval_time": at, "alertname": alert,
                                 "exp_alerts": [{"exp_labels": labels()}] if fires else []}]}


def tests():
    return [
        # deliberate stop: excluded
        case([s("up", "0x60"), s("process_up", "0x60"), s("user_stopped", "1x60")],
             DOWN, "60m", False),
        # crash (not user-stopped): fires
        case([s("up", "0x60"), s("process_up", "0x60"), s("user_stopped", "0x60")],
             DOWN, "60m", True),
        # older build without the gauge: still fires
        case([s("up", "0x60"), s("process_up", "0x60")], DOWN, "60m", True),
        # process alive, adb dead: that is Unresponsive, not Down
        case([s("up", "0x60"), s("process_up", "1x60")], DOWN, "60m", False),
        # guard: stuck in user-stopped past the 6h cycle
        case([s("user_stopped", "1x480")], LONG, "8h", True),
        case([s("user_stopped", "1x360")], LONG, "6h", False),
        case([s("user_stopped", "0x480")], LONG, "8h", False),
    ]


def set_rule(groups, alert, **kw):
    g = copy.deepcopy(groups)
    for grp in g:
        for r in grp["rules"]:
            if r.get("alert") == alert:
                r.update(kw)
    return g


def mutants(groups):
    return {
        "Down without user_stopped exclusion": set_rule(
            groups, DOWN,
            expr="arag_scrape_emulator_up == 0 unless on(instance, job) "
                 "arag_scrape_emulator_process_up == 1"),
        "Down excludes user_stopped presence (any value)": set_rule(
            groups, DOWN,
            expr="(arag_scrape_emulator_up == 0 unless on(instance, job) "
                 "arag_scrape_emulator_process_up == 1) unless on(instance, job) "
                 "arag_scrape_emulator_user_stopped"),
        "UserStoppedLong for: 0m": set_rule(groups, LONG, **{"for": "0m"}),
        "UserStoppedLong for: 9h": set_rule(groups, LONG, **{"for": "9h"}),
    }


def run(promtool, groups, tmp, tag):
    rf = os.path.join(tmp, f"{tag}-rules.yaml")
    tf = os.path.join(tmp, f"{tag}-test.yaml")
    groups = copy.deepcopy(groups)
    for g in groups:
        for r in g["rules"]:
            r.pop("annotations", None)
    yaml.safe_dump({"groups": groups}, open(rf, "w"), sort_keys=False)
    yaml.safe_dump({"rule_files": [os.path.basename(rf)], "evaluation_interval": "1m",
                    "tests": tests()}, open(tf, "w"), sort_keys=False)
    p = subprocess.run([promtool, "test", "rules", tf], cwd=tmp, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def main():
    promtool = find_promtool()
    if not promtool:
        print("FAIL: promtool not found (PATH, $PROMTOOL or mise install)")
        return 1
    groups = load_groups()
    if not groups:
        print(f"FAIL: group {GROUP} not found in {RULES}")
        return 1
    fails = 0
    with tempfile.TemporaryDirectory() as tmp:
        rc, out = run(promtool, groups, tmp, "live")
        print(out.strip())
        if rc != 0:
            print("FAIL: live rules fail the suite")
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
