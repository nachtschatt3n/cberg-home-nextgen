#!/usr/bin/env python3
"""Regression test: two components on ONE image move together, or not at all.

F-dc4066f9, caught 2026-09-21 by the maintenance-window agent at Step 0, which
deferred the bump rather than applying it.

`scan-inbox-validator` runs ghcr.io/paperless-ngx/paperless-ngx — the SAME
image repository as the main paperless-ngx workload — but it is a bare
Deployment, so coverage.py scored it as its own component:

  paperless-ngx        3.1.3 -> 3.2.1, lane PLAN (plan paperless-ngx-3.2.0)
  scan-inbox-validator 3.1.3 -> 3.2.1, lane AUTO ("safe patch/minor")

One half of a single ingestion pipeline sat in the lane an unattended window
applies while the other half was deliberately held, on the same image.

This is a COMPONENT IDENTITY defect, not a lane-policy one: the lane rules
behaved correctly given the inputs they were handed. It recurs for any
sidecar/helper Deployment sharing an image with a workload tracked under a
different component name.

The coupling is keyed on (image repository, TARGET tag) — the same artifact
moving to the same version. Keying on the repository alone would couple every
component that merely shares a common base image, which is the over-capture
direction; that limit is pinned below.

Run: python3 runbooks/tests/test-coverage-shared-image-lockstep.py
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("cov", REPO / "runbooks/coverage.py")
cov = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cov)

FAILURES: list[str] = []
IMG = "ghcr.io/paperless-ngx/paperless-ngx"


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


def entry(component, lane, reason, target="3.2.1", repos=(IMG,), kind="image",
          current="3.1.3", **kw):
    d = {"component": component, "namespace": "office", "kind": kind,
         "current": current, "target": target, "type": "minor",
         "image_repos": list(repos), "lane": lane, "reason": reason}
    d.update(kw)
    return d


def lanes_with(*entries):
    out = {"AUTO": [], "PLAN": [], "REBUILD": [], "HELD": [], "CRACK": []}
    for e in entries:
        out[e["lane"]].append(e)
    return out


def main() -> int:
    print("test-coverage-shared-image-lockstep")

    # ── THE live pair ──────────────────────────────────────────────────
    val = entry("scan-inbox-validator", "AUTO", "safe patch/minor — window applies")
    main_wl = entry("paperless-ngx", "PLAN", "plan exists: paperless-ngx-3.2.0 (draft)")
    lanes = lanes_with(val, main_wl)
    moved = cov._apply_lockstep(lanes, [])
    check("the AUTO half is pulled back to PLAN", val["lane"] == "PLAN"
          and val in lanes["PLAN"] and val not in lanes["AUTO"], val["lane"])
    check("...and reported as a lockstep move", moved == [val])
    check("the reason names the SHARED IMAGE, so the operator can see why two "
          "differently-named components are coupled",
          IMG in val["reason"], val["reason"])
    check("the held sibling is named too", "paperless-ngx" in val["reason"])

    # ── the planner is not dispatched twice ────────────────────────────
    val2 = entry("scan-inbox-validator", "PLAN",
                 "G3 breaking-change signal in a SKIPPED release — 3.2.0")
    lanes = lanes_with(val2, main_wl)
    needs = [val2]
    dropped = cov._prune_needs_plan_shared_image(lanes, needs)
    check("a planner target whose artifact ANOTHER component's plan already "
          "delivers is dropped", needs == [] and dropped == [val2])
    check("...and says which plan covers it instead of vanishing silently",
          "paperless-ngx" in val2["reason"] and "no second planner" in val2["reason"],
          val2["reason"])
    check("the item STAYS in the PLAN lane, so the lane counts remain honest",
          val2 in lanes["PLAN"])

    # ── SCOPE: the coupling must not over-capture ──────────────────────
    other_ver = entry("scan-inbox-validator", "AUTO", "safe patch/minor",
                      target="4.0.0", current="3.9.9")
    lanes = lanes_with(other_ver, main_wl)
    cov._apply_lockstep(lanes, [])
    check("the same image at a DIFFERENT target is not coupled (a shared base "
          "image must not freeze every component that mounts it)",
          other_ver["lane"] == "AUTO", other_ver["reason"])

    diff_repo = entry("unrelated-app", "AUTO", "safe patch/minor",
                      repos=("ghcr.io/other/app",))
    lanes = lanes_with(diff_repo, main_wl)
    cov._apply_lockstep(lanes, [])
    check("a different image is not coupled", diff_repo["lane"] == "AUTO")

    free = entry("scan-inbox-validator", "AUTO", "safe patch/minor")
    lanes = lanes_with(free)
    cov._apply_lockstep(lanes, [])
    check("with no held sibling at all the item still reaches AUTO — this gate "
          "only ever moves work OUT of the unattended lane when a hold exists",
          free["lane"] == "AUTO")

    # ── the pre-existing max-rule exemption must survive ───────────────
    cand = entry("n8n", "AUTO", "safe patch/minor", current="2.38.7",
                 target="2.38.9", repos=("n8nio/n8n",),
                 max_rule_fallback=True, origin_target="2.40.3")
    origin = entry("n8n", "PLAN", "beta channel", current="2.38.7",
                   target="2.40.3", repos=("n8nio/n8n",))
    lanes = lanes_with(cand, origin)
    cov._apply_lockstep(lanes, [])
    check("a `max:`-fallback candidate is NOT locksteped to its own blocked "
          "origin (that would make the fallback lane permanently inert)",
          cand["lane"] == "AUTO", cand["reason"])

    # ── the prune only trusts a REAL plan ──────────────────────────────
    holder_no_plan = entry("paperless-ngx", "PLAN", "major — needs an assessed window plan")
    tgt = entry("scan-inbox-validator", "PLAN", "G3 signal")
    lanes = lanes_with(tgt, holder_no_plan)
    needs = [tgt]
    cov._prune_needs_plan_shared_image(lanes, needs)
    check("a sibling that itself has NO plan does not suppress the planner — "
          "otherwise both halves would wait for each other forever",
          needs == [tgt])

    # ── COMMISSIONING ──────────────────────────────────────────────────
    def straw_component_only(lanes, needs_plan):
        """The pre-fix lockstep: holders keyed on the component name alone."""
        holders = {}
        for lane in ("PLAN", "HELD"):
            for e in lanes[lane]:
                holders.setdefault(str(e.get("component", "")).lower(), []).append((lane, e))
        moved = []
        for e in list(lanes["AUTO"]):
            if holders.get(str(e.get("component", "")).lower()):
                e["lane"] = "PLAN"
                lanes["AUTO"].remove(e)
                lanes["PLAN"].append(e)
                moved.append(e)
        return moved

    val3 = entry("scan-inbox-validator", "AUTO", "safe patch/minor")
    lanes = lanes_with(val3, entry("paperless-ngx", "PLAN", "plan exists: p (draft)"))
    straw_component_only(lanes, [])
    check("commissioning: the PRE-FIX component-keyed lockstep is caught — the "
          "validator stays in the unattended lane", val3["lane"] == "AUTO",
          f"straw gave {val3['lane']}")

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} -> {', '.join(FAILURES)}")
        return 1
    print("all tests passed")
    return 0


def test_pytest_entry() -> None:
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())
