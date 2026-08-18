#!/usr/bin/env python3
"""coverage — enforce that EVERY actionable update has a lane (NO CRACKS).

The auto-updater only ever sees OPEN Renovate PRs, so an actionable fix with no
PR and no plan silently falls through. This reconciler closes that hole: it
enumerates the FULL actionable universe from `runbooks/version-check-current.md`
— the Quick Overview Table (charts + the primary image), the PER-APP detail
sections (init containers, sidecars and base images, which the table cannot
express) and the External Infrastructure section (Talos, npm, UniFi, PiKVM) —
assigns each update to a
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

CRACK==0 is only a safety property if the UNIVERSE is complete. Until
2026-08-18 it was not: the detector read the overview table alone, which lists
ONE image per app, so every init/sidecar/base image and every non-HelmRelease
component was invisible and `CRACK 0` / `HELD 0` meant "never looked at". If a
future source of updates is added to version-check-current.md, it MUST be added
to the universe here as well — an honest metric matters more than a clean one.

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
# NOTE the matching key: this is compared against the COMPONENT name (the app /
# HelmRelease name), NOT the image name. `harness-home-frontend` was listed here
# and never matched, because that app's component is `ha-ai-harness` — so a
# self-built image with no upstream was being routed to the AUTO lane, where the
# auto-updater would try to "bump" it to a tag that can never exist. `ai-sre`
# only worked by coincidence: its app and image names happen to be identical.
# Verified 2026-08-15 against the running inventory of ghcr.io/nachtschatt3n/*.
SELF_BUILT = {
    "ai-sre", "ha-ai-harness", "sure", "sweep-dashboard", "arag-web",
    "opencode-project_name", "opencode-andreamosteller", "paperclip",
    # Added 2026-08-15 — all confirmed self-built (ghcr.io/nachtschatt3n/*) and
    # running, but absent from this set, so each had the same mis-routing bug:
    "absenty", "andreamosteller", "pellet-price-monitor", "solarfocus-scraper",
    "zero-export-controller", "gas-price-monitor", "rainbow-rescue",
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


def _is_strictly_newer(cur: str, tgt: str) -> bool:
    """True only when `tgt` parses to a strictly-higher semver than `cur`.
    Defence-in-depth against a DOWNGRADE arrow leaking in from a stale/hand-
    edited version-check-current.md: `v3.1.0 → v1.116.0` is a downgrade, not
    an actionable update, and must never manufacture a PLAN-lane item. When
    either side is unparseable we keep the arrow (can't prove a downgrade, so
    don't silently drop a possibly-real update)."""
    def parse(v):
        v = v.lstrip("vV").split("-")[0].split("+")[0].split("@")[0]
        return [int(x) for x in re.findall(r"\d+", v)[:3]]
    a, b = parse(cur), parse(tgt)
    if not a or not b:
        return True  # unparseable → don't suppress
    a += [0] * (3 - len(a)); b += [0] * (3 - len(b))
    return b > a


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
                if am and "✅" not in cell and _is_strictly_newer(am.group(1), am.group(2)):
                    # per-ITEM type from its own version diff — the row's
                    # complexity column reflects the (app-template) CHART major
                    # and would mislabel a patch image bump on the same row.
                    st = _semver_type(am.group(1), am.group(2))
                    items.append({"component": comp, "namespace": ns, "kind": kind,
                                  "current": am.group(1), "target": am.group(2),
                                  "type": st if st != "unknown" else row_type,
                                  "cell": cell.strip()})
    return items


_APP_HEAD = re.compile(r"^### (.+?)\s*$")
_NS_HEAD = re.compile(r"^## Namespace: `([^`]+)`")
_REPO_LINE = re.compile(r"^- \*\*Repository:\*\* `([^`]+)`")
_CURTAG_LINE = re.compile(r"^\s+- \*\*Current Tag:\*\* `([^`]+)`")
_LATESTTAG_LINE = re.compile(r"^\s+- \*\*Latest Tag:\*\* `([^`]+)`(.*)$")
_UPDTYPE_LINE = re.compile(r"^\s+- \*\*Update Type:\*\*.*\*\*([A-Z]+)\*\*")
_EXT_HEAD = re.compile(r"^### (.+?) \(`[^`]+`\)\s*$")
_EXT_VER = re.compile(r"^- \*\*Version:\*\* `([^`]+)`.*?(?:→|->) `([^`]+)`")


def parse_detail_images():
    """Every image update from the PER-APP detail sections.

    The Quick Overview Table carries ONE image per app, so init containers,
    sidecars and base images never reached the crack detector at all — for
    those, `CRACK 0` meant "not looked at", not "none uncovered", while the
    sweep contract reads CRACK==0 as a hard safety property. The detail
    sections list every container, so this closes the universe instead of
    merely documenting the hole. Today it adds e.g. mcpo's `python` base image
    and paperclip's `ubuntu`/`debian` tool+init images, none of which the table
    can express.

    `### <app>` is only trusted as an app heading when a `- **File:**` line
    follows it: upstream changelogs are dumped verbatim into this document and
    their own `###` headings (`### Backend`, `### Availability`) would
    otherwise be read as apps.
    """
    if not VERSION_MD.exists():
        return []
    items, ns, comp, pending_app = [], None, None, None
    repo = cur = None
    for line in VERSION_MD.read_text().splitlines():
        m = _NS_HEAD.match(line)
        if m:
            ns, comp, pending_app = m.group(1), None, None
            continue
        if line.startswith("## "):          # left the namespace sections
            ns = comp = pending_app = None
            continue
        m = _APP_HEAD.match(line)
        if m and ns:
            pending_app = m.group(1).strip().strip("`")
            continue
        if pending_app and line.startswith("- **File:**"):
            comp, pending_app = pending_app, None
            continue
        if not comp:
            continue
        m = _REPO_LINE.match(line)
        if m:
            repo, cur = m.group(1), None
            continue
        m = _CURTAG_LINE.match(line)
        if m:
            cur = m.group(1)
            continue
        m = _LATESTTAG_LINE.match(line)
        if m and repo and cur and "UPDATE AVAILABLE" in m.group(2):
            tgt = m.group(1)
            if _is_strictly_newer(cur, tgt):
                items.append({"component": comp, "namespace": ns, "kind": "image",
                              "current": cur, "target": tgt,
                              "type": _semver_type(cur, tgt), "cell": f"{repo} {cur} → {tgt}",
                              "source": f"detail:{repo}"})
    return items


def parse_external_infra():
    """Updates for the non-HelmRelease components (Talos, the npm packages,
    UniFi, PiKVM). These live in their own section and were likewise outside
    the detector's universe — which is why the HELD lane read 0 even though
    both of its entries (openclaw / @openclaw/discord) are npm components."""
    if not VERSION_MD.exists():
        return []
    items, name, in_ext = [], None, False
    for line in VERSION_MD.read_text().splitlines():
        if line.startswith("## External Infrastructure"):
            in_ext = True
            continue
        if in_ext and line.startswith("## "):
            break
        if not in_ext:
            continue
        m = _EXT_HEAD.match(line)
        if m:
            # `openclaw (npm)` is the component `openclaw`
            name = re.sub(r"\s*\((?:npm|pypi|helm)\)\s*$", "", m.group(1)).strip()
            continue
        m = _EXT_VER.match(line)
        if m and name and _is_strictly_newer(m.group(1), m.group(2)):
            items.append({"component": name, "namespace": "external", "kind": "image",
                          "current": m.group(1), "target": m.group(2),
                          "type": _semver_type(m.group(1), m.group(2)),
                          "cell": f"{m.group(1)} → {m.group(2)}", "source": "external"})
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


# A plan file is only EVIDENCE OF COVERAGE while it is still going to run.
# `executed` and `superseded` plans are history: the work they describe has
# already landed (or been replaced), so the NEXT bump of that component is
# uncovered again. Counting them was scoring stale artifacts as live lanes.
DEAD_PLAN_STATUSES = {
    "executed", "superseded", "retired", "cancelled", "canceled",
    "abandoned", "obsolete", "done", "rolled-back", "rolled_back",
}

_VER_TOKEN = re.compile(r"\bv?\d+\.\d+(?:\.\d+)?\b")
_CONCRETE_VER = re.compile(
    r"^v?\d+\.\d+(?:\.\d+)?(?:\.\d+)?"
    r"(?:-(?:alpine\d*|bookworm|bullseye|buster|slim|debian|ubuntu|focal|jammy|noble)"
    r"(?:-[a-z0-9]+)*)?$",
    re.IGNORECASE,
)


def _ver_tuple(v: str):
    """(major, minor, patch) from a version token, or None."""
    nums = [int(x) for x in re.findall(r"\d+", str(v).lstrip("vV").split("@")[0])[:3]]
    if not nums:
        return None
    return tuple(nums + [0] * (3 - len(nums)))


def _release_line(t):
    """The line a plan is 'about'. For 1.x+ that's the MAJOR (a v2->v3
    migration plan stays valid as v3 gains patches). For 0.x the minor is the
    breaking axis, so 0.175 and 0.177 are different lines."""
    return (t[0],) if t[0] else (0, t[1])


def load_plans():
    """Every maintenance-window plan, as records (not just names) — the lane
    decision needs `status` and `target`, not merely `component`."""
    plans = []
    if not PLANS_DIR.exists():
        return plans
    for p in sorted(PLANS_DIR.glob("*.md")):
        if p.name.lower() == "readme.md":
            continue
        try:
            fm = yaml.safe_load(p.read_text().split("---", 2)[1]) or {}
        except Exception:
            continue
        comp = str(fm.get("component") or "").lower().strip()
        if not comp:
            continue
        keys = {comp}
        # app-template plan covers all its wrappers
        if "app-template" in str(fm.get("plan_id") or ""):
            keys.add("app-template")
        plans.append({
            "plan_id": str(fm.get("plan_id") or p.stem),
            "file": p.name,
            "keys": keys,
            # a plan with no status is a live draft, not history
            "status": str(fm.get("status") or "draft").lower().strip(),
            "kind": str(fm.get("kind") or "").lower().strip(),
            "current": str(fm.get("current") or "").strip(),
            "target": str(fm.get("target") or "").strip(),
        })
    return plans


def _plan_delivers(plan, item):
    """(covers, drift) — does this LIVE plan actually deliver `item`'s bump?

    Matching on the component name alone made any plan mentioning an app cover
    every future update to it: superset 5.0.0 -> 6.1.0 was scored covered by a
    plan whose subject is the metadata-DB sidecar, and nextcloud chart
    9.2.5 -> 9.2.6 by a bitnamilegacy MariaDB exit plan. So the plan's TARGET
    has to name the bump.

    Drift is deliberately tolerated but REPORTED: a v2->v3 plan written against
    v3.4.1 still covers the same migration once v3.5.0 ships — the plan needs a
    refresh, not a re-plan, and calling that a CRACK would bury the real ones.
    """
    ptgt = plan["target"]
    if not ptgt:
        return False, None
    # a chart plan never delivers an image bump (or vice versa)
    if plan["kind"] in ("chart", "image") and item["kind"] in ("chart", "image") \
            and plan["kind"] != item["kind"]:
        return False, None
    uv = _ver_tuple(item["target"])
    # the exact target version named anywhere in the plan's target field —
    # works for prose targets like "mariadb:11.8.8 (Docker Official Image)"
    if uv and any(_ver_tuple(t) == uv for t in _VER_TOKEN.findall(ptgt)):
        return True, None
    # a CONCRETE (non-prose) plan target that has merely drifted behind upstream
    if uv and _CONCRETE_VER.match(ptgt):
        pv = _ver_tuple(ptgt)
        if pv and _release_line(pv) == _release_line(uv):
            return True, f"plan targets {ptgt}, but {item['target']} is now published"
    return False, None


def match_plan(item, keys, plans):
    """(plan, drift) for the best live plan covering `item`, else (None, None).
    A drift-free match always wins over a drifted one."""
    drifted = None
    for plan in plans:
        if not (plan["keys"] & keys):
            continue
        if plan["status"] in DEAD_PLAN_STATUSES:
            continue
        covers, drift = _plan_delivers(plan, item)
        if covers and not drift:
            return plan, None
        if covers and drifted is None:
            drifted = (plan, drift)
    return drifted if drifted else (None, None)


def assign_lane(item, policy, prs, plans):
    """(lane, reason, drift) for one actionable update."""
    comp = item["component"].lower()
    utype = item["type"]
    # app-template chart bump: one migration wearing ~40 hats — collapse.
    is_app_template = item["kind"] == "chart" and item["target"].startswith("5.")
    key = "app-template" if is_app_template else comp

    if comp in HELD or key in HELD:
        return "HELD", HELD.get(comp) or HELD.get(key, "held"), None
    if comp in SELF_BUILT:
        return "REBUILD", "self-built image — rebuild in its source repo (not a cluster tag bump)", None
    plan, drift = match_plan(item, {comp, key}, plans)
    if plan:
        return "PLAN", f"plan exists: {plan['plan_id']} ({plan['status']})", (
            f"{plan['file']}: {drift}" if drift else None)
    if prs.get(comp) or prs.get(key):
        return "AUTO", f"Renovate PR #{prs.get(comp) or prs.get(key)}", None
    dn = denied(policy, key, utype)
    if dn or utype == "major" or utype == "unknown":
        return "PLAN", (dn or f"{utype} — needs an assessed window plan"), None
    if utype in ("patch", "minor"):
        return "AUTO", "safe patch/minor — window applies (hybrid: PR or direct-bump)", None
    return "CRACK", "actionable but unclassifiable — MUST be triaged", None


def reconcile():
    policy = load_policy()
    actionable = parse_actionable()
    if actionable is None:
        return {"error": "version-check-current.md missing — run version-check first",
                "cracks": [{"component": "version-check", "reason": "no version data"}]}
    # Widen the universe beyond the one-image-per-app overview table, then
    # dedupe: the table row and the detail block describe the SAME bump.
    seen = {(i["component"].lower(), i["kind"], i["current"], i["target"])
            for i in actionable}
    for extra in parse_detail_images() + parse_external_infra():
        k = (extra["component"].lower(), extra["kind"], extra["current"], extra["target"])
        if k not in seen:
            seen.add(k)
            actionable.append(extra)
    prs = parse_renovate_prs()
    plans = load_plans()

    lanes = {"AUTO": [], "PLAN": [], "REBUILD": [], "HELD": [], "CRACK": []}
    needs_plan = []  # PLAN-lane items with NO plan file yet → sweep must dispatch a planner
    plan_drift = []  # live plans whose target has fallen behind upstream
    seen_app_template = False
    for it in actionable:
        lane, reason, drift = assign_lane(it, policy, prs, plans)
        # dedupe the ~40 app-template rows into one PLAN item
        if it["kind"] == "chart" and it["target"].startswith("5."):
            if seen_app_template:
                continue
            seen_app_template = True
            it = {**it, "component": "app-template (≈all app-template wrappers)"}
        entry = {**it, "lane": lane, "reason": reason}
        if drift:
            entry["drift"] = drift
            plan_drift.append(entry)
        lanes[lane].append(entry)
        if lane == "PLAN" and not reason.startswith("plan exists"):
            needs_plan.append(entry)

    return {
        "counts": {k: len(v) for k, v in lanes.items()},
        "lanes": lanes,
        "needs_plan": needs_plan,           # dispatch an upgrade-planner for each
        "plan_drift": plan_drift,           # plan exists but its target is stale
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
    if r.get("plan_drift"):
        L.append(f"\nPLAN TARGET DRIFT ({len(r['plan_drift'])}) — covered, but the plan needs a refresh:")
        for e in r["plan_drift"]:
            L.append(f"  • {e['component']} [{e['kind']} {e['current']}→{e['target']}] — {e['drift']}")
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
