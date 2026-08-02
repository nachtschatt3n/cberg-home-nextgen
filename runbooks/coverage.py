#!/usr/bin/env python3
"""coverage — enforce that EVERY actionable update has a lane (NO CRACKS).

The auto-updater only ever sees OPEN Renovate PRs, so an actionable fix with no
PR and no plan silently falls through. This reconciler closes that hole: it
enumerates the FULL actionable universe from `runbooks/version-check-current.md`
(every chart/image with a newer version available), assigns each update to a
LANE, checks it has a concrete ARTIFACT proving it's being handled, and emits a
CRITICAL finding for anything uncovered. That CRACK detector is what makes
"nothing falls between the cracks" enforceable instead of aspirational.

Lanes (operator policy, 2026-08-02):
  AUTO    — safe (patch/minor, not deny-listed). Applied automatically in the
            maintenance window: merge the Renovate PR if one exists, else
            direct-bump (hybrid). Always covered by the window.
  PLAN    — non-safe (major / deny-listed) upstream bump → needs a
            maintenance-window plan (upgrade-planner). Low-risk plans auto-run
            in-window; medium+ require operator go/no-go. Artifact: a plan file.
  REBUILD — self-built image (ghcr.io/nachtschatt3n/*) → can't be tag-bumped;
            needs a rebuild in its own source repo. Surfaced (human), never
            silently dropped.
  HELD    — explicitly held/accepted (e.g. openclaw node 22). No action.
  CRACK   — actionable but in NONE of the above. MUST never happen → CRITICAL.

Read-only. Run in the sweep (report + drive planner dispatch) and before a
window (confirm coverage). Usage:
    python3 runbooks/coverage.py            # human report
    python3 runbooks/coverage.py --json     # machine-readable (for the sweep)
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT = SCRIPT_DIR.parent
VERSION_MD = SCRIPT_DIR / "version-check-current.md"
POLICY = SCRIPT_DIR / "auto-update-policy.yaml"
PLANS_DIR = SCRIPT_DIR / "maintenance" / "plans"

# Components intentionally held/accepted — actionable but we don't act (with why).
# Keep in sync with the operator's real holds; these are NOT cracks.
HELD = {
    "openclaw": "held at node 22 / 2026.6.11 pending Memory Core migration",
    "@openclaw/discord": "moves in lockstep with the held openclaw host",
}
# Self-built images we own — remediation is a rebuild in the source repo, not a
# cluster tag bump. (Matched against the component name.)
SELF_BUILT = {
    "ai-sre", "harness-home-frontend", "sure", "sweep-dashboard", "arag-web",
    "opencode-project_name", "opencode-andreamosteller", "paperclip",
}
RANK = {"patch": 0, "minor": 1, "major": 2}


def _match_anywhere(name: str, pat: str) -> bool:
    return any(fnmatch.fnmatch(name, g) for g in (pat, f"*{pat}", f"{pat}*", f"*{pat}*"))


def load_policy():
    try:
        return yaml.safe_load(POLICY.read_text()) or {}
    except Exception:
        return {"deny": []}


def denied(policy, name, utype):
    """Return a reason if the deny-list blocks (name, utype), else None."""
    for rule in policy.get("deny", []) or []:
        pat = rule.get("match", "")
        if pat and _match_anywhere(name, pat):
            mx = rule.get("max")
            if mx is None or RANK.get(utype, 99) > RANK.get(mx, -1):
                return rule.get("reason", f"deny rule {pat!r}")
    return None


_ROW = re.compile(r"^\|\s*`?([^`|]+?)`?\s*\|\s*`?([^`|]*)`?\s*\|\s*([^|]*)\|\s*([^|]*)\|\s*([^|]*)\|\s*([^|]*)\|\s*$")
_ARROW = re.compile(r"(\S+)\s*(?:→|->)\s*(\S+)")


def _semver_type(cur: str, tgt: str) -> str:
    """patch/minor/major from two versions (handles v-prefix, date tags like
    2026.7.2, alpine suffixes). unknown if unparseable."""
    def parse(v):
        v = v.lstrip("vV").split("-")[0].split("+")[0].split("@")[0]
        return [int(x) for x in re.findall(r"\d+", v)[:3]]
    a, b = parse(cur), parse(tgt)
    if not a or not b:
        return "unknown"
    a += [0] * (3 - len(a)); b += [0] * (3 - len(b))
    if b[0] != a[0]:
        return "major"
    if b[1] != a[1]:
        return "minor"
    if b[2] != a[2]:
        return "patch"
    return "unknown"


def parse_actionable():
    """Every actionable update from version-check-current.md's overview table:
    a dict per (component, kind) with a chart or image bump available."""
    if not VERSION_MD.exists():
        return None  # signal: version data missing (itself a coverage failure)
    items = []
    in_table = False
    for line in VERSION_MD.read_text().splitlines():
        if line.startswith("| Deployment"):
            in_table = True
            continue
        if in_table:
            if not line.startswith("|") or set(line.strip()) <= set("|-"):
                if line.strip() and not line.startswith("|"):
                    break
                continue
            m = _ROW.match(line)
            if not m:
                continue
            comp, ns, chart, image, app, cx = (x.strip() for x in m.groups())
            cx_l = cx.lower()
            row_type = ("major" if "major" in cx_l else "minor" if "minor" in cx_l
                        else "patch" if "patch" in cx_l else "unknown")
            for kind, cell in (("chart", chart), ("image", image)):
                am = _ARROW.search(cell)
                if am and "✅" not in cell:
                    # per-ITEM type from its own version diff — the row's
                    # complexity column reflects the (app-template) CHART major
                    # and would mislabel a patch image bump on the same row.
                    st = _semver_type(am.group(1), am.group(2))
                    items.append({"component": comp, "namespace": ns, "kind": kind,
                                  "current": am.group(1), "target": am.group(2),
                                  "type": st if st != "unknown" else row_type,
                                  "cell": cell.strip()})
    return items


def parse_renovate_prs():
    """Component names that already have an open Renovate PR (AUTO artifact)."""
    prs = {}
    txt = VERSION_MD.read_text() if VERSION_MD.exists() else ""
    for line in txt.splitlines():
        m = re.search(r"\[#(\d+)\].*?update\s+(.+?)\s*\(", line)
        if m:
            dep = m.group(2).strip().split("/")[-1]
            prs[dep.lower()] = m.group(1)
    return prs


def plan_components():
    """Component names that already have a maintenance-window plan."""
    comps = set()
    if PLANS_DIR.exists():
        for p in PLANS_DIR.glob("*.md"):
            if p.name.lower() == "readme.md":
                continue
            try:
                fm = yaml.safe_load(p.read_text().split("---", 2)[1]) or {}
                if fm.get("component"):
                    comps.add(str(fm["component"]).lower())
                # app-template plan covers all its wrappers
                if "app-template" in (fm.get("plan_id") or ""):
                    comps.add("app-template")
            except Exception:
                pass
    return comps


def assign_lane(item, policy, prs, plans):
    comp = item["component"].lower()
    utype = item["type"]
    # app-template chart bump: one migration wearing ~40 hats — collapse.
    is_app_template = item["kind"] == "chart" and item["target"].startswith("5.")
    key = "app-template" if is_app_template else comp

    if comp in HELD or key in HELD:
        return "HELD", HELD.get(comp) or HELD.get(key, "held")
    if comp in SELF_BUILT:
        return "REBUILD", "self-built image — rebuild in its source repo (not a cluster tag bump)"
    if key in plans or comp in plans:
        return "PLAN", "plan exists"
    if prs.get(comp) or prs.get(key):
        return "AUTO", f"Renovate PR #{prs.get(comp) or prs.get(key)}"
    dn = denied(policy, key, utype)
    if dn or utype == "major" or utype == "unknown":
        return "PLAN", (dn or f"{utype} — needs an assessed window plan")
    if utype in ("patch", "minor"):
        return "AUTO", "safe patch/minor — window applies (hybrid: PR or direct-bump)"
    return "CRACK", "actionable but unclassifiable — MUST be triaged"


def reconcile():
    policy = load_policy()
    actionable = parse_actionable()
    if actionable is None:
        return {"error": "version-check-current.md missing — run version-check first",
                "cracks": [{"component": "version-check", "reason": "no version data"}]}
    prs = parse_renovate_prs()
    plans = plan_components()

    lanes = {"AUTO": [], "PLAN": [], "REBUILD": [], "HELD": [], "CRACK": []}
    needs_plan = []  # PLAN-lane items with NO plan file yet → sweep must dispatch a planner
    seen_app_template = False
    for it in actionable:
        lane, reason = assign_lane(it, policy, prs, plans)
        # dedupe the ~40 app-template rows into one PLAN item
        if it["kind"] == "chart" and it["target"].startswith("5."):
            if seen_app_template:
                continue
            seen_app_template = True
            it = {**it, "component": "app-template (≈all app-template wrappers)"}
        entry = {**it, "lane": lane, "reason": reason}
        lanes[lane].append(entry)
        if lane == "PLAN" and reason != "plan exists":
            needs_plan.append(entry)

    return {
        "counts": {k: len(v) for k, v in lanes.items()},
        "lanes": lanes,
        "needs_plan": needs_plan,           # dispatch an upgrade-planner for each
        "cracks": lanes["CRACK"],           # MUST be empty
        "covered": len(lanes["CRACK"]) == 0,
    }


def human(r):
    if "error" in r:
        return f"!! COVERAGE FAILED: {r['error']}"
    c = r["counts"]
    L = [f"== update coverage — AUTO {c['AUTO']} · PLAN {c['PLAN']} · REBUILD {c['REBUILD']} "
         f"· HELD {c['HELD']} · CRACK {c['CRACK']} =="]
    L.append(f"covered: {'YES ✅ (no cracks)' if r['covered'] else 'NO 🚨 CRACKS PRESENT'}")
    if r["needs_plan"]:
        L.append(f"\nNEEDS A PLAN ({len(r['needs_plan'])}) — dispatch an upgrade-planner for each:")
        for e in r["needs_plan"]:
            L.append(f"  • {e['component']} [{e['kind']} {e['current']}→{e['target']}] — {e['reason'][:70]}")
    if r["lanes"]["REBUILD"]:
        L.append(f"\nREBUILD (self-built, source-repo rebuild) ({len(r['lanes']['REBUILD'])}):")
        for e in r["lanes"]["REBUILD"]:
            L.append(f"  • {e['component']} [{e['kind']} {e['current']}→{e['target']}]")
    if r["cracks"]:
        L.append(f"\n🚨 CRACKS ({len(r['cracks'])}) — actionable with NO lane, MUST triage:")
        for e in r["cracks"]:
            L.append(f"  • {e.get('component')} [{e.get('kind')} {e.get('current')}→{e.get('target')}] — {e.get('reason')}")
    else:
        L.append("\n✅ zero cracks — every actionable update is AUTO / PLAN / REBUILD / HELD")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    r = reconcile()
    print(json.dumps(r, indent=2) if args.json else human(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
