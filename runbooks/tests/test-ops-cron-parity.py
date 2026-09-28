"""Regression tests for window-crons.py's ops-cron parity (ops-crons.yaml).

The weekly ops retro is driven by an OpenClaw cron that lives on a PVC, not in
git. ops-crons.yaml is its reviewed mirror and `window-crons.py --check` (run
by every sweep) must notice when the cron is missing, doubled, disabled,
re-scheduled, or has a failureAlert that cannot page (F-e6dda67f).

Run:  python3 runbooks/tests/test-ops-cron-parity.py
"""

from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("wc_ops", REPO / "runbooks/window-crons.py")
wc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wc)

TZ = "Europe/Berlin"
CMD = "/home/node/.openclaw/bin/operation retro --trigger cron"
DECL = [{"id": "ops-retro", "name": "Weekly Ops Retro", "command": CMD, "cron": "30 7 * * 1",
         "period": "weekly", "failure_alert_cooldown": "6d"}]
GOOD = {"name": "Weekly Ops Retro", "enabled": True,
        "schedule": {"kind": "cron", "expr": "30 7 * * 1", "tz": TZ},
        "payload": {"kind": "command", "argv": ["sh", "-lc", CMD]},
        "failureAlert": {"after": 1, "channel": "telegram", "to": "x", "cooldownMs": 6 * 86_400_000}}
SNAP_CMD = "/home/node/.openclaw/bin/operation snapshot --trigger cron"
SNAP_GOOD = {"name": "Version Snapshot Refresh (pre-nightly)", "enabled": True,
             "schedule": {"kind": "cron", "expr": "45 2 * * *", "tz": TZ},
             "payload": {"kind": "command", "argv": ["sh", "-lc", SNAP_CMD]},
             "failureAlert": {"after": 1, "channel": "telegram", "to": "x", "cooldownMs": 20 * 3_600_000}}
FAILURES: list[str] = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


def variant(**kw):
    c = copy.deepcopy(GOOD)
    for k, v in kw.items():
        if k == "expr":
            c["schedule"]["expr"] = v
        elif k == "tz":
            c["schedule"]["tz"] = v
        elif k == "cooldown":
            c["failureAlert"]["cooldownMs"] = v
        else:
            c[k] = v
    return c


def main():
    print("test-ops-cron-parity")
    e = wc.check_ops_crons(DECL, TZ, [GOOD])
    check("matching cron -> parity holds", e == [], str(e))
    e = wc.check_ops_crons(DECL, TZ, [])
    check("no cron -> 'NO cron runs' error", len(e) == 1 and "NO cron runs" in e[0], str(e))
    e = wc.check_ops_crons(DECL, TZ, [GOOD, GOOD])
    check("two crons -> double-fire error", any("double-fires" in x for x in e), str(e))
    e = wc.check_ops_crons(DECL, TZ, [variant(enabled=False)])
    check("disabled cron -> error", any("DISABLED" in x for x in e), str(e))
    e = wc.check_ops_crons(DECL, TZ, [variant(expr="30 7 * * 2")])
    check("wrong weekday -> expr error", any("cron expr" in x for x in e), str(e))
    e = wc.check_ops_crons(DECL, TZ, [variant(tz="UTC")])
    check("wrong tz -> tz error", any("tz" in x for x in e), str(e))
    e = wc.check_ops_crons(DECL, TZ, [variant(failureAlert=None)])
    check("no failureAlert -> error", any("NO failureAlert" in x for x in e), str(e))
    e = wc.check_ops_crons(DECL, TZ, [variant(cooldown=7 * 86_400_000)])
    check("cooldown == weekly period -> error (F-e6dda67f)", any("cooldownMs" in x for x in e), str(e))
    bad = [dict(DECL[0], failure_alert_cooldown="7d")]
    e = wc.check_ops_crons(bad, TZ, [GOOD])
    check("DECLARED cooldown >= period is refused too", any("DECLARED" in x for x in e), str(e))
    other = variant(payload={"argv": ["sh", "-lc", "/home/node/.openclaw/bin/operation sweep --wait"]})
    e = wc.check_ops_crons(DECL, TZ, [other])
    check("a sweep cron does not satisfy the retro entry", any("NO cron runs" in x for x in e), str(e))
    decls, tz = wc.load_ops_crons()
    check("repo ops-crons.yaml declares ops-retro at Mon 07:30 Europe/Berlin, cooldown < 7d",
          any(d["id"] == "ops-retro" and d["cron"] == "30 7 * * 1" for d in decls) and tz == TZ
          and wc.check_ops_crons(decls, tz, [GOOD, SNAP_GOOD]) == [], str(decls))
    # F-539b186e (2026-09-28): the pre-nightly snapshot refresh is a DAILY ops cron.
    check("repo ops-crons.yaml declares version-snapshot daily 02:45, before the 03:30 nightly",
          any(d["id"] == "version-snapshot" and d["cron"] == "45 2 * * *" and d["period"] == "daily"
              and d["command"] == SNAP_CMD for d in decls), str(decls))
    e = wc.check_ops_crons(decls, tz, [GOOD])
    check("a missing snapshot cron is reported (the retro cron does not satisfy it)",
          any("version-snapshot" in x for x in e), str(e))
    bad = dict(SNAP_GOOD, failureAlert=dict(SNAP_GOOD["failureAlert"], cooldownMs=86_400_000))
    e = wc.check_ops_crons(decls, tz, [GOOD, bad])
    check("snapshot cron with a 24h cooldown on a 24h period is refused (F-e6dda67f)",
          any("cooldownMs" in x for x in e), str(e))
    r = wc.render_ops_crons(decls, tz)
    check("--render emits the cron add with the command and a failure alert",
          CMD in r and "--failure-alert-cooldown 6d" in r and "FAILURE_ALERT_TO" in r, r[:300])
    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} -> {', '.join(FAILURES)}")
        return 1
    print("all ops-cron parity tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
