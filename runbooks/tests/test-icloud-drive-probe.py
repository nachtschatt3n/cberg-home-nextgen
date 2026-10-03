"""Regression tests for the iCloud DRIVE half of CronJob/icloud-sync-probe and
the icloud-backup.drive alert group (added 2026-10-03).

Two layers:
  1. analyse_drive() from the probe ConfigMap, against synthetic icloud-docker
     log lines shaped exactly like the live ones (ANSI colour, timestamps=true
     prefix, package errors that name no file). Includes NEGATIVE CONTROLS so a
     later "fix" cannot silently blind the detector (a broken run must reset the
     persistence clock, a different item each cycle must not accumulate, an
     open cycle must never count as a success, no drive lines -> no gauges).
  2. promtool unit tests against the live rule group: must-not-fire for a
     healthy drive sync at the real 5-8h cadence with 0 failures; must-fire for
     stalled >12h / >24h, persistent failure >24h, and each account's absent
     gauge; must-not-fire for 23h persistence or an old run with 0 failures.

Run:  python3 runbooks/tests/test-icloud-drive-probe.py
(promtool is taken from PATH or the mise install; the test FAILS if missing.)
"""

from __future__ import annotations

import calendar
import glob
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
CM = REPO / "kubernetes/apps/backup/icloud-backup-freshness/app/sync-probe-configmap.yaml"
RULES = REPO / "kubernetes/apps/monitoring/kube-prometheus-stack/app/icloud-backup-alerts.yaml"
FAILURES: list[str] = []

ns: dict = {}
exec(yaml.safe_load(CM.read_text())["data"]["icloud_sync_probe.py"], ns)  # noqa: S102
analyse_drive = ns["analyse_drive"]
analyse = ns["analyse"]

T0 = calendar.timegm(time.strptime("2026-10-01T00:00:00", "%Y-%m-%dT%H:%M:%S"))


def L(t, mod, msg, level="INFO"):
    iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)) + ".123456789Z"
    return f"{iso} \x1b[38;5;39m2026-10-01 00:00:00,000 :: {level} :: root :: {mod} :: 1 :: {msg}\x1b[0m"


def batch(t, paths, ok, bad, extra=()):
    out = [L(t, "drive_parallel_download.py", f"Starting parallel downloads with 8 threads for {len(paths)} files...")]
    out += [L(t, "drive_file_download.py", f"Downloading {p} ...") for p in paths]
    out += [L(t + 1, m, x, "ERROR") for m, x in extra]
    out.append(L(t + 2, "drive_parallel_download.py", f"Parallel downloads completed: {ok} successful, {bad} failed"))
    return out


PKG_ERR = ("drive_package_processing.py",
           "Unhandled file type - cannot unpack the package application/octet-stream.")


def cycle(t, body=()):
    return [L(t, "sync.py", "Syncing drive..."), *body, L(t + 600, "sync.py", "Drive synced")]


def check(name, got, want):
    if got != want:
        FAILURES.append(f"{name}: got {got!r}, want {want!r}")


NOW = T0 + 100 * 3600
H6 = 6 * 3600

# 1. Healthy: drive cycles at the real cadence, 0 failures.
lines = [L(T0 - 10, "config_logging.py", "Syncing drive every 3600 seconds.")]
for i in range(4):
    lines += cycle(T0 + i * H6, batch(T0 + i * H6 + 5, ["/d/a b.txt"], 1, 0))
m = analyse_drive([lines], NOW)
check("healthy last_success", m.get("icloud_drive_sync_last_success_timestamp_seconds"), T0 + 3 * H6 + 600)
check("healthy items_failed", m.get("icloud_drive_items_failed"), 0)
check("healthy since", m.get("icloud_drive_failing_item_since_timestamp_seconds"), NOW)

# 2. Same package item failing on every cycle (error line names no file).
lines = []
for i in range(4):
    lines += cycle(T0 + i * H6, batch(T0 + i * H6 + 5, ["/d/x.numbers"], 0, 1, [PKG_ERR]))
m = analyse_drive([lines], NOW)
check("persistent items_failed", m.get("icloud_drive_items_failed"), 1)
check("persistent since", m.get("icloud_drive_failing_item_since_timestamp_seconds"), T0 + 600)

# 3. NEGATIVE CONTROL: a cycle where the item succeeded breaks the run.
lines = []
for i, (ok, bad) in enumerate([(0, 1), (0, 1), (1, 0), (0, 1)]):
    lines += cycle(T0 + i * H6, batch(T0 + i * H6 + 5, ["/d/x.numbers"], ok, bad, [PKG_ERR] if bad else []))
m = analyse_drive([lines], NOW)
check("broken-run since", m.get("icloud_drive_failing_item_since_timestamp_seconds"), T0 + 3 * H6 + 600)

# 4. NEGATIVE CONTROL: a different item failing each cycle does not accumulate.
lines = []
for i in range(4):
    lines += cycle(T0 + i * H6, batch(T0 + i * H6 + 5, [f"/d/item{i}"], 0, 1, [PKG_ERR]))
m = analyse_drive([lines], NOW)
check("rotating since", m.get("icloud_drive_failing_item_since_timestamp_seconds"), T0 + 3 * H6 + 600)

# 5. Mixed batch: only the explicitly named failure is attributed; an anonymous
#    package error in a mixed batch counts but cannot extend a run.
lines = []
for i in range(3):
    lines += cycle(T0 + i * H6, batch(T0 + i * H6 + 5, ["/d/ok", "/d/bad one.json"], 1, 1,
                                      [("drive_file_download.py", "Failed to download /d/bad one.json Unknown reason")]))
m = analyse_drive([lines], NOW)
check("mixed named items_failed", m.get("icloud_drive_items_failed"), 1)
check("mixed named since", m.get("icloud_drive_failing_item_since_timestamp_seconds"), T0 + 600)
lines = []
for i in range(3):
    lines += cycle(T0 + i * H6, batch(T0 + i * H6 + 5, ["/d/ok", "/d/p.band"], 1, 1, [PKG_ERR]))
m = analyse_drive([lines], NOW)
check("mixed anon items_failed", m.get("icloud_drive_items_failed"), 1)
check("mixed anon since (late, never early)", m.get("icloud_drive_failing_item_since_timestamp_seconds"), NOW)

# 6. NEGATIVE CONTROL: an open cycle (crash/wedge mid-drive) is never a success.
lines = cycle(T0) + [L(T0 + H6, "sync.py", "Syncing drive...")] + batch(T0 + H6 + 5, ["/d/x"], 0, 1, [PKG_ERR])
m = analyse_drive([lines], NOW)
check("open-cycle last_success", m.get("icloud_drive_sync_last_success_timestamp_seconds"), T0 + 600)
check("open-cycle items_failed (last COMPLETED cycle)", m.get("icloud_drive_items_failed"), 0)

# 7. No drive lines (drive disabled / silent wedge / rotated log): emit NOTHING.
lines = [L(T0, "sync.py", "Syncing photos..."), L(T0 + 60, "sync.py", "Photos synced"),
         L(T0 - 10, "config_logging.py", "Syncing drive every 3600 seconds.")]
check("no-drive keys", sorted(analyse_drive([lines], NOW)), [])

# 8. Drive failures must not leak into the PHOTO failure count.
lines = (cycle(T0, batch(T0 + 5, ["/d/x"], 0, 1,
                         [("drive_file_download.py", "Failed to download /d/x Unknown reason")]))
         + [L(T0 + 700, "sync.py", "Syncing photos..."), L(T0 + 800, "sync.py", "Photos synced")])
check("photo isolation", analyse([lines], NOW).get("icloud_sync_items_failed"), 0)

# 9. Restart: previous + current container, the run spans both.
prev = cycle(T0, batch(T0 + 5, ["/d/x.numbers"], 0, 1, [PKG_ERR]))
cur = cycle(T0 + H6, batch(T0 + H6 + 5, ["/d/x.numbers"], 0, 1, [PKG_ERR]))
check("restart since", analyse_drive([prev, cur], NOW).get("icloud_drive_failing_item_since_timestamp_seconds"), T0 + 600)

# 10. icloud-docker >= 2.1.0 sign-in failure lines (real text, rendered with
#     icloudpy 0.10.0's exception classes). Credential/SRP failures are
#     auth-required; a plain network fault at sign-in is NOT (left to the
#     sync-stalled alert).
photos_ok = [L(T0, "sync.py", "Syncing photos..."), L(T0 + 600, "sync.py", "Photos synced")]
SIGNIN = "Sign-in failed and will be retried: "
for name, err, want in [
    ("signin-auth-real", "('Invalid email/password combination.', "
                         "ICloudPyAPIResponseException('Unauthorized (401)'))", 1),
    ("signin-srp-real", "('Failed to initiate srp authentication.', "
                        "ICloudPyAPIResponseException('Conflict (409)'))", 1),
    ("signin-network (negative control)", "HTTPSConnectionPool(host='idmsa.apple.com', port=443): "
                                          "Read timed out.", 0),
]:
    lines = photos_ok + [L(T0 + 1200, "sync.py", SIGNIN + err, "ERROR")]
    check(f"{name} auth_required", analyse([lines], NOW).get("icloud_auth_required"), want)
check("clean auth_required", analyse([photos_ok], NOW).get("icloud_auth_required"), 0)


# ---------------------------------------------------------------- promtool
def promtool():
    # A mise shim with no pinned version is on PATH on the Mac and dies with
    # "No version is set for shim: promtool" -- so every candidate must prove
    # it RUNS, not merely exist, before it is used.
    cands = [shutil.which("promtool")] + sorted(
        glob.glob(os.path.expanduser("~/.local/share/mise/installs/ubi-prometheus-prometheus/*/promtool")),
        reverse=True)
    for c in cands:
        if not c:
            continue
        try:
            if subprocess.run([c, "--version"], capture_output=True, timeout=120).returncode == 0:
                return c
        except (OSError, subprocess.TimeoutExpired):
            pass
    return None


PT = promtool()
if not PT:
    FAILURES.append("promtool not found (PATH or mise ubi-prometheus-prometheus install)")
else:
    groups = [g for g in yaml.safe_load(RULES.read_text())["spec"]["groups"] if g["name"] == "icloud-backup.drive"]
    if len(groups) != 1:
        FAILURES.append("icloud-backup.drive group not found exactly once")
    G = 'job="icloud-sync-probe"'
    H = 3600

    # Test clock: one sample per MINUTE for 72h (pushgateway is scraped
    # continuously; 10m spacing would exceed the 5m lookback, blank the series
    # between samples and reset every `for:` clock). Values are unix seconds
    # relative to promtool's t=0, so "now" == eval_time.
    STEPS = 72 * 60

    def gauge(account, metric, values):
        return {"series": f'{metric}{{{G},account="{account}"}}', "values": values}

    def sawtooth(period_s, steps):
        # last_success refreshed every period_s, sampled every 60s
        return " ".join(str((i * 60) // period_s * period_s) for i in range(steps))

    healthy = [
        gauge(a, "icloud_drive_sync_last_success_timestamp_seconds", sawtooth(8 * H, STEPS)) for a in ("mu", "andrea")
    ] + [
        gauge(a, "icloud_drive_items_failed", f"0+0x{STEPS}") for a in ("mu", "andrea")
    ] + [
        gauge(a, "icloud_drive_failing_item_since_timestamp_seconds", f"0+60x{STEPS}")
        for a in ("mu", "andrea")
    ]
    tests = {
        "rule_files": ["rules.yaml"],
        "evaluation_interval": "1m",
        "tests": [
            {   # MUST NOT FIRE: healthy at the real (8h worst-case) cadence, 0 failures.
                "interval": "1m", "input_series": healthy,
                "alert_rule_test": [{"eval_time": t, "alertname": a, "exp_alerts": []}
                                    for t in ("20h", "47h", "71h")
                                    for a in ("ICloudDriveSyncStalled", "ICloudDriveSyncStalledCritical",
                                              "ICloudDrivePersistentDownloadFailures", "ICloudDriveSyncMetricMissing",
                                              "ICloudDriveSyncMetricMissingAndrea")],
            },
            {   # MUST FIRE: mu stalled (last success frozen at t=0); andrea healthy.
                "interval": "1m",
                "input_series": [gauge("mu", "icloud_drive_sync_last_success_timestamp_seconds", f"0+0x{STEPS}"),
                                 gauge("andrea", "icloud_drive_sync_last_success_timestamp_seconds", sawtooth(6 * H, STEPS))],
                "alert_rule_test": [
                    {"eval_time": "11h", "alertname": "ICloudDriveSyncStalled", "exp_alerts": []},
                    {"eval_time": "13h", "alertname": "ICloudDriveSyncStalled",
                     "exp_alerts": [{"exp_labels": {"account": "mu", "severity": "warning",
                                                    "category": "backup", "component": "icloud-docker"}}]},
                    {"eval_time": "23h", "alertname": "ICloudDriveSyncStalledCritical", "exp_alerts": []},
                    {"eval_time": "25h", "alertname": "ICloudDriveSyncStalledCritical",
                     "exp_alerts": [{"exp_labels": {"account": "mu", "severity": "critical",
                                                    "category": "backup", "component": "icloud-docker"}}]},
                ],
            },
            {   # MUST FIRE: same item failing since t=0 with failures > 0 (mu);
                # NEGATIVE CONTROL andrea: old run but items_failed 0 -> silent.
                "interval": "1m",
                "input_series": [gauge("mu", "icloud_drive_failing_item_since_timestamp_seconds", f"0+0x{STEPS}"),
                                 gauge("mu", "icloud_drive_items_failed", f"10+0x{STEPS}"),
                                 gauge("andrea", "icloud_drive_failing_item_since_timestamp_seconds", f"0+0x{STEPS}"),
                                 gauge("andrea", "icloud_drive_items_failed", f"0+0x{STEPS}")],
                "alert_rule_test": [
                    {"eval_time": "23h", "alertname": "ICloudDrivePersistentDownloadFailures", "exp_alerts": []},
                    {"eval_time": "25h", "alertname": "ICloudDrivePersistentDownloadFailures",
                     "exp_alerts": [{"exp_labels": {"account": "mu", "severity": "info",
                                                    "category": "backup", "component": "icloud-docker"}}]},
                ],
            },
            {   # MUST FIRE: absent gauge, per account (only mu present -> andrea guard fires).
                "interval": "1m",
                "input_series": [gauge("mu", "icloud_drive_sync_last_success_timestamp_seconds", sawtooth(6 * H, STEPS))],
                "alert_rule_test": [
                    {"eval_time": "2h", "alertname": "ICloudDriveSyncMetricMissing", "exp_alerts": []},
                    {"eval_time": "2h", "alertname": "ICloudDriveSyncMetricMissingAndrea",
                     "exp_alerts": [{"exp_labels": {"account": "andrea", "severity": "warning",
                                                    "category": "backup", "component": "icloud-docker"}}]},
                ],
            },
            {   # MUST FIRE: both absent.
                "interval": "1m",
                "input_series": [gauge("mu", "icloud_sync_last_success_timestamp_seconds", "0+0x200")],
                "alert_rule_test": [
                    {"eval_time": "2h", "alertname": "ICloudDriveSyncMetricMissing",
                     "exp_alerts": [{"exp_labels": {"account": "mu", "severity": "warning",
                                                    "category": "backup", "component": "icloud-docker"}}]},
                ],
            },
        ],
    }
    with tempfile.TemporaryDirectory() as d:
        d = os.environ.get("ICLOUD_TEST_KEEPDIR") or d  # debugging: keep the generated files
        # Annotations are prose with templated durations; these tests pin the
        # EXPRESSIONS, labels and `for` windows, so annotations are stripped.
        for g in groups:
            for r in g["rules"]:
                r.pop("annotations", None)
        Path(d, "rules.yaml").write_text(yaml.safe_dump({"groups": groups}))
        Path(d, "tests.yaml").write_text(yaml.safe_dump(tests))
        r = subprocess.run([PT, "test", "rules", "tests.yaml"], cwd=d, capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            FAILURES.append("promtool test rules failed:\n" + r.stdout + r.stderr)
        else:
            print("promtool: " + (r.stdout.strip().splitlines() or ["ok"])[-1])

if FAILURES:
    print("FAIL")
    for f in FAILURES:
        print(" -", f)
    sys.exit(1)
print("OK: icloud drive probe + alert tests passed")
