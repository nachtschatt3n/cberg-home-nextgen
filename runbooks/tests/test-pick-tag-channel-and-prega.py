"""Regression: false-positive version targets (2026-11-03).
 - valkey `9.2` is a pre-GA shorthand tag (only 9.2.0-rc1 exists) -> not a target
 - n8n 2.46.4 is the beta channel; npm `stable` is 2.45.7 -> capped there

Run:  python3 runbooks/tests/test-pick-tag-channel-and-prega.py
"""
from __future__ import annotations
import importlib.util, os, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
os.environ.setdefault("_MISE_ACTIVATED", "1")
sys.path.insert(0, str(REPO / "runbooks"))
spec = importlib.util.spec_from_file_location("cav_chan", REPO / "runbooks/check-all-versions.py")
cav = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cav)  # type: ignore
V = [c for c in vars(cav).values() if isinstance(c, type) and hasattr(c, "_pick_latest_semver_tag")][0]
v = V.__new__(V)
v._major_cap = None
fails = []

def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        fails.append(name)

valkey = ["9.1", "9.1.0", "9.1.2", "9.1.3", "9", "9.2", "9.2.0-rc1", "9.2-rc", "9.2.0-rc1-alpine", "9.2-alpine", "9.1.2-alpine", "9.1.3-alpine"]
check("valkey: unreleased 9.2 shorthand is not offered", v._pick_latest_semver_tag(valkey, "9.1.2", "valkey/valkey") == "9.1.3",
      v._pick_latest_semver_tag(valkey, "9.1.2", "valkey/valkey"))
ga = valkey + ["9.2.0"]
check("valkey: once 9.2.0 GA exists the 9.2 line is offered",
      v._pick_latest_semver_tag(ga, "9.1.2", "valkey/valkey") in ("9.2", "9.2.0"), v._pick_latest_semver_tag(ga, "9.1.2", "valkey/valkey"))
check("control: repo that only publishes X.Y (no pre-release) is untouched",
      v._pick_latest_semver_tag(["16.3", "16.4", "17.0"], "16.3", "postgres") in ("16.4", "17.0"))

n8n = ["2.44.5", "2.45.7", "2.46.0", "2.46.4", "2.46.4-2616635"]
type(v)._stable_channel_cache.clear()
type(v)._stable_channel_cache["n8n"] = (2, 45, 7, 0)
check("n8n: capped at npm stable 2.45.7, beta 2.46.4 not offered",
      v._pick_latest_semver_tag(n8n, "2.44.5", "n8nio/n8n") == "2.45.7", v._pick_latest_semver_tag(n8n, "2.44.5", "n8nio/n8n"))
check("control: other repos never consult the channel",
      v._pick_latest_semver_tag(n8n, "2.44.5", "example/other") == "2.46.4")
type(v)._stable_channel_cache.clear()
real = cav.requests.get
def boom(*a, **k): raise RuntimeError("offline")
cav.requests.get = boom
try:
    got = v._pick_latest_semver_tag(n8n, "2.44.5", "n8nio/n8n")
finally:
    cav.requests.get = real
check("n8n: unreadable stable pointer fails closed (no candidate)", got is None, got)
type(v)._stable_channel_cache.clear()
sys.exit(1 if fails else 0)
