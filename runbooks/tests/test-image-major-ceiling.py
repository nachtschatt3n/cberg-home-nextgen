"""Regression: the openclaw init image (node) is capped at the 22.x line via
policy `image_major_ceiling` (F-6a859080, 2026-10-23); other consumers are not.

Run:  python3 runbooks/tests/test-image-major-ceiling.py
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
os.environ.setdefault("_MISE_ACTIVATED", "1")
sys.path.insert(0, str(REPO / "runbooks"))
spec = importlib.util.spec_from_file_location("cav_ceiling", REPO / "runbooks/check-all-versions.py")
cav = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cav)  # type: ignore

V = [c for c in vars(cav).values() if isinstance(c, type) and hasattr(c, "_pick_latest_semver_tag")][0]
v = V.__new__(V)
fails = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        fails.append(name)


tags = ["22.23.3-bookworm", "22.23.4-bookworm", "24.22.1-bookworm", "26.12.0-bookworm"]
cur = "22.23.3-bookworm@sha256:0e5f"
cap = v._image_major_cap("openclaw", "node")
check("policy caps openclaw/node at 22", cap == 22, cap)
check("other component using node is uncapped", v._image_major_cap("other-app", "node") is None)
check("openclaw other image uncapped", v._image_major_cap("openclaw", "redis") is None)
v._major_cap = cap
check("26.12.0 candidate is held; 22.x patch is proposed",
      v._pick_latest_semver_tag(tags, cur, "node") == "22.23.4-bookworm",
      v._pick_latest_semver_tag(tags, cur, "node"))
check("capped, exhausted 22 line yields no 26 (current head stays)",
      v._pick_latest_semver_tag(["22.23.3-bookworm", "26.12.0-bookworm"], cur, "node") == "22.23.3-bookworm")
v._major_cap = None
check("uncapped consumer still sees the 26 line",
      v._pick_latest_semver_tag(["22.23.3-bookworm", "26.12.0-bookworm"], "22.23.3-bookworm", "node") == "26.12.0-bookworm")
print("FAILED %s" % fails if fails else "ALL PASS")
sys.exit(1 if fails else 0)
