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
import os
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
# cluster tag bump.
#
# MATCHED ON THE IMAGE, NOT THE COMPONENT (fixed 2026-08-18, F-62007db7). The
# lane is a property of the IMAGE (who builds it), never of the app that happens
# to mount it, so the set below is only a FALLBACK for items whose image
# repository could not be resolved from version-check-current.md; whenever the
# repo IS known, `_is_self_built_repo()` decides. Both directions were wrong
# before:
#   • under-capture (fixed 2026-08-15): `harness-home-frontend` was listed here
#     and never matched, because that app's component is `ha-ai-harness` — a
#     self-built image was routed to AUTO, where the auto-updater would try to
#     "bump" it to a tag that can never exist;
#   • over-capture (this fix): `paperclip` is listed here but owns NO self-built
#     image — its four images (busybox, debian, reeoss/paperclipai-paperclip,
#     ubuntu) are all third-party and CAN be tag-bumped, yet both of its updates
#     were parked in REBUILD, a lane whose remedy (rebuild in our source repo)
#     can never bump them. Parked in the wrong lane == uncovered, dressed as
#     covered.
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

# Registries/namespaces we build ourselves. An image from one of these can only
# move by a rebuild in its source repo.
SELF_BUILT_REPO_PREFIXES = ("ghcr.io/nachtschatt3n/",)

# ── Upstream release CHANNELS ───────────────────────────────────────────────
# A semver LABEL does not prove a tag is a stable successor. Some upstreams push
# pre-release builds to the SAME docker repo, with a HIGHER version number than
# their newest stable release — so the tag oracle reports "minor update
# available" and, on the label alone, `assign_lane()` routed it to AUTO, which
# the maintenance window APPLIES unattended at Step 0 (window-agent hybrid
# direct-bump). That is how a beta build reaches the cluster with nobody in the
# loop.
#
# scrypted is the live example (2026-08-18): upstream cuts GitHub releases on
# ODD minors only — v0.143.0 is the newest with prerelease=false, v0.144.x has
# NO GitHub release at all, and the v0.144.0 docker tag was pushed 2025-10-31,
# i.e. BEFORE stable v0.143.0 (2025-11-16). v0.144.x is a parallel beta channel,
# not a successor. AR-081 says so in as many words — but an AR only suppresses
# the FINDING on the board, it does not stop the AUTO lane, and the workload is
# a PRIVILEGED NVR (privileged: true, SYS_ADMIN, i915 device).
#
# These rules are CHANNEL predicates, not version pins: they keep holding as
# upstream ships 0.145 (stable) / 0.146.x (beta), so they can't drift the way a
# pinned AR description does (memory: feedback_sweep_ar_version_drift).
CHANNEL_RULES = {
    "scrypted": {
        "stable": "odd-minor",
        "ar": "AR-081",
        "why": ("upstream releases stable on ODD minors only; even minors "
                "(v0.144.x) are the beta channel — no GitHub release, and "
                "v0.144.0 predates stable v0.143.0"),
        "workload": "privileged NVR (privileged: true, SYS_ADMIN, i915)",
    },
}

# Explicit pre-release markers in a tag — universal, no per-component rule
# needed. Never AUTO, whatever the semver delta says.
_PRERELEASE_TAG = re.compile(
    r"(?:^|[-_.])(?:alpha|beta|rc\d*|pre|preview|dev|nightly|snapshot|canary|"
    r"unstable|test)(?:[-_.]|\d|$)", re.IGNORECASE)

_AR_PRERELEASE_PHRASES = (
    "pre-release channel", "prerelease channel", "beta channel",
    "pre-release build", "not an acceptable channel",
)


def _is_self_built_repo(repo: str) -> bool:
    return any(str(repo).lower().startswith(p) for p in SELF_BUILT_REPO_PREFIXES)


def _stable_by_rule(rule: str, version: str) -> bool:
    """Is `version` on the component's STABLE channel per `rule`?
    Unparseable / unknown rule → treat as stable (never invent a hold)."""
    t = _ver_tuple(version)
    if not t:
        return True
    if rule == "odd-minor":
        return t[1] % 2 == 1
    if rule == "even-minor":
        return t[1] % 2 == 0
    return True


def channel_hold(comp: str, item: dict, ar_holds: dict | None = None) -> str | None:
    """Reason why `item`'s TARGET is not a stable-channel successor, else None.

    Three independent sources, any one of which disqualifies AUTO:
      1. an explicit pre-release marker in the tag (-beta/-rc/-nightly/…);
      2. a git-tracked CHANNEL_RULES predicate (works offline — the window agent
         runs coverage.py without SWEEP_PG_DSN, so a DB-only gate would
         fail OPEN exactly where it matters);
      3. an ACTIVE accepted risk that declares the component's pre-release
         channel unacceptable (`ar_holds`, best-effort from the policy DB).
    """
    tgt = str(item.get("target") or "")
    if _PRERELEASE_TAG.search(tgt):
        return f"target {tgt} is an explicit pre-release tag — never unattended"
    rule = CHANNEL_RULES.get(comp)
    if rule and not _stable_by_rule(rule["stable"], tgt):
        ar = f" ({rule['ar']}: unacceptable for a {rule['workload']})" if rule.get("ar") else ""
        return (f"{tgt} is on upstream's PRE-RELEASE channel — {rule['why']}{ar}. "
                f"Needs an assessed window plan, never an unattended bump")
    if ar_holds and comp in ar_holds:
        return (f"{ar_holds[comp]} declares this component's pre-release channel "
                f"unacceptable — {tgt} needs operator assessment, not AUTO")
    return None


_AR_HOLDS_CACHE = None


def ar_prerelease_holds() -> dict:
    """{component: AR-ID} for ENABLED accepted risks whose justification says the
    component's pre-release channel is unacceptable. Best-effort: needs
    SWEEP_PG_DSN + psycopg. This is layer 3 — it can only ADD holds, so an
    unreachable DB degrades to the git-tracked CHANNEL_RULES above rather than
    silently re-opening the AUTO lane."""
    global _AR_HOLDS_CACHE
    if _AR_HOLDS_CACHE is not None:
        return _AR_HOLDS_CACHE
    _AR_HOLDS_CACHE = {}
    dsn = os.environ.get("SWEEP_PG_DSN")
    if not dsn:
        return _AR_HOLDS_CACHE
    try:
        import psycopg
        with psycopg.connect(dsn, connect_timeout=5) as conn, conn.cursor() as cur:
            cur.execute("SELECT ar_id, description, justification FROM accepted_risks "
                        "WHERE enabled = true AND status = 'accepted'")
            rows = cur.fetchall()
    except Exception:
        return _AR_HOLDS_CACHE
    for ar_id, desc, just in rows:
        blob = (just or "").lower()
        if not any(p in blob for p in _AR_PRERELEASE_PHRASES):
            continue
        # The description names the image, e.g. `koush/scrypted` — take the
        # IMAGE NAME (last path segment, version suffix dropped), not every
        # word in it. Splitting on all separators registered generic tokens
        # ("image", "chart", "nvr") as component keys and could attach a
        # confusing hold reason to an unrelated app.
        for chunk in str(desc or "").split():
            chunk = chunk.strip().strip(",;")
            # image-ish only: a bare prose word is never a component key
            if not any(ch in chunk for ch in "/-."):
                continue
            tok = chunk.split(":")[0].rstrip("/").split("/")[-1].lower()
            if len(tok) > 3 and re.fullmatch(r"[a-z0-9][a-z0-9._-]*", tok):
                _AR_HOLDS_CACHE.setdefault(tok, ar_id)
    return _AR_HOLDS_CACHE


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
                                  "cell": cell.strip(),
                                  # the table carries tags only, never the image
                                  # repo — resolved later from the detail index
                                  "image_repo": None})
    return items


_APP_HEAD = re.compile(r"^### (.+?)\s*$")
_NS_HEAD = re.compile(r"^## Namespace: `([^`]+)`")
_REPO_LINE = re.compile(r"^- \*\*Repository:\*\* `([^`]+)`")
_CURTAG_LINE = re.compile(r"^\s+- \*\*Current Tag:\*\* `([^`]+)`")
_LATESTTAG_LINE = re.compile(r"^\s+- \*\*Latest Tag:\*\* `([^`]+)`(.*)$")
_UPDTYPE_LINE = re.compile(r"^\s+- \*\*Update Type:\*\*.*\*\*([A-Z]+)\*\*")
_EXT_HEAD = re.compile(r"^### (.+?) \(`[^`]+`\)\s*$")
_EXT_VER = re.compile(r"^- \*\*Version:\*\* `([^`]+)`.*?(?:→|->) `([^`]+)`")


def parse_detail_images(repo_index=None):
    """Every image update from the PER-APP detail sections.

    `repo_index` (optional dict) is filled with {component: {image repos}} for
    EVERY app in the report, update or not — the overview table lists tags
    without their repository, so this is how an overview row learns which image
    it is talking about (needed to decide REBUILD on the image, not the app).

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
    in_images = False           # `#### Container Images` vs `#### Chart`
    for line in VERSION_MD.read_text().splitlines():
        m = _NS_HEAD.match(line)
        if m:
            ns, comp, pending_app, in_images = m.group(1), None, None, False
            continue
        if line.startswith("## "):          # left the namespace sections
            ns = comp = pending_app = None
            in_images = False
            continue
        m = _APP_HEAD.match(line)
        if m and ns:
            pending_app = m.group(1).strip().strip("`")
            continue
        if pending_app and line.startswith("- **File:**"):
            comp, pending_app, in_images = pending_app, None, False
            continue
        if not comp:
            continue
        if line.startswith("#### "):
            # the CHART block carries a `Repository:` line too (`bjw-s`); only
            # the image block may feed the repo index, or every app-template
            # app would look like it mounts a non-self-built image.
            in_images = line.startswith("#### Container Images")
            continue
        m = _REPO_LINE.match(line)
        if m:
            repo, cur = m.group(1), None
            if in_images and repo_index is not None:
                repo_index.setdefault(comp.lower(), set()).add(repo)
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
                              "source": f"detail:{repo}", "image_repo": repo})
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


def is_self_built(item, comp) -> bool:
    """Is THIS item's image one we build ourselves?

    Decided on the IMAGE repository whenever it is known — a component name only
    says which app mounts the image, not who builds it (F-62007db7: paperclip is
    in SELF_BUILT but every one of its four images is third-party). The
    component set is the fallback for items whose repo the version report does
    not carry (e.g. overview-table rows for apps with no detail section).
    """
    if item["kind"] != "image":
        return False                       # a chart is never a self-built image
    repos = [r for r in ([item.get("image_repo")] if item.get("image_repo")
                         else item.get("image_repos") or []) if r]
    if repos:
        # ALL of them, not ANY: on a multi-image row we cannot attribute the
        # bump, and calling a third-party image "self-built" parks a bumpable
        # update in a lane that can never bump it.
        return all(_is_self_built_repo(r) for r in repos)
    return comp in SELF_BUILT


def assign_lane(item, policy, prs, plans, ar_holds=None):
    """(lane, reason, drift) for one actionable update."""
    comp = item["component"].lower()
    utype = item["type"]
    # app-template chart bump: one migration wearing ~40 hats — collapse.
    is_app_template = item["kind"] == "chart" and item["target"].startswith("5.")
    key = "app-template" if is_app_template else comp

    if comp in HELD or key in HELD:
        return "HELD", HELD.get(comp) or HELD.get(key, "held"), None
    if is_self_built(item, comp):
        return "REBUILD", "self-built image — rebuild in its source repo (not a cluster tag bump)", None
    plan, drift = match_plan(item, {comp, key}, plans)
    if plan:
        return "PLAN", f"plan exists: {plan['plan_id']} ({plan['status']})", (
            f"{plan['file']}: {drift}" if drift else None)
    # CHANNEL GATE — must sit ABOVE both AUTO exits (the Renovate-PR shortcut and
    # the safe patch/minor default): a pre-release target is not made safe by a
    # PR existing for it, and the window applies the AUTO lane unattended.
    ch = channel_hold(comp, item, ar_holds)
    if ch:
        return "PLAN", ch, None
    # 0.x: the MINOR is the breaking axis, so a "minor" label there is a
    # release-LINE move, not a safe in-line bump. This repo already encodes that
    # in `_release_line` (plan matching) and lives it: nextcloud-mcp 0.176.0
    # removed an API and dropped a table on a minor hop. It is also the second,
    # component-agnostic reason scrypted 0.143 -> 0.144 must not be unattended —
    # `_semver_type` calls it "minor" only because both majors are 0.
    zt, zc = _ver_tuple(item["target"]), _ver_tuple(item["current"])
    if zt and zc and zc[0] == 0 and zt[0] == 0 and zt[1] != zc[1]:
        return "PLAN", ("0.x release-line move (0.%d -> 0.%d) — at major 0 the minor "
                        "IS the breaking axis; needs an assessed window plan"
                        % (zc[1], zt[1])), None
    if prs.get(comp) or prs.get(key):
        return "AUTO", f"Renovate PR #{prs.get(comp) or prs.get(key)}", None
    dn = denied(policy, key, utype)
    if dn or utype == "major" or utype == "unknown":
        return "PLAN", (dn or f"{utype} — needs an assessed window plan"), None
    if utype in ("patch", "minor"):
        return "AUTO", "safe patch/minor — window applies (hybrid: PR or direct-bump)", None
    return "CRACK", "actionable but unclassifiable — MUST be triaged", None


_TRUNC = re.compile(r"(?:\.{3}|…)\s*$")


def _is_truncated(v) -> bool:
    """The overview table clips long cells; the detail sections do not."""
    return bool(v) and bool(_TRUNC.search(str(v)))


def _dedupe_tag(v) -> str:
    """Canonical form of a tag for DEDUPE only — the leading version core.

    `v0.144.1-noble-ful...` (table, truncated) and `v0.144.1-noble-full`
    (detail) are the same bump; comparing the raw strings said otherwise and
    double-counted the item in its lane.
    """
    s = _TRUNC.sub("", str(v or "").strip()).lstrip("vV")
    m = re.match(r"\d+(?:\.\d+)*", s)
    core = m.group(0) if m else s.lower()
    # A pre-release marker must SURVIVE dedupe. Without this, `1.2.3` (table)
    # and `1.2.3-beta` (detail) collide on one key, the beta record loses the
    # merge, and the surviving row has no marker left for the channel gate to
    # see — the dedupe would quietly re-open the very door this file closes.
    return core + ("-pre" if _PRERELEASE_TAG.search(s) else "")


def _apply_lockstep(lanes, needs_plan):
    """Pull an AUTO item back to PLAN when a SIBLING of the same component is held.

    A chart and the image it deploys are ONE deployable unit. unpoller made the
    hazard concrete (2026-08-18): chart `2.1.0 → 2.4.0` scored a safe minor and
    landed in AUTO, while the image `v2.39.0 → v3.5.0` is PLAN-held for
    mon-early 2026-08-24 — so the next window would have moved the chart (whose
    appVersion is v3.5.0, i.e. it crosses the held image's major) while
    `image.tag` stayed pinned at v2.39.0: a v3-aware chart driving a v2 image,
    unattended, with none of the plan's vetting.

    The rule deliberately does NOT try to read appVersion (the version report
    does not carry it, and a rule that needs data we may not have fails open).
    Same component + a held sibling is sufficient and strictly safer: it can
    only ever move work OUT of the unattended lane, and it self-clears the
    moment the plan executes and the hold disappears.
    """
    holders = {}
    for lane in ("PLAN", "HELD"):
        for e in lanes[lane]:
            holders.setdefault(str(e.get("component", "")).lower(), (lane, e))
    moved = []
    for e in list(lanes["AUTO"]):
        comp = str(e.get("component", "")).lower()
        held = holders.get(comp)
        if not held:
            continue
        hlane, he = held
        e["lane"] = "PLAN"
        e["lockstep_with"] = f"{he['kind']} {he['current']}→{he['target']} [{hlane}]"
        e["reason"] = (f"lockstep — the {comp} {he['kind']} is {hlane} "
                       f"({str(he.get('reason', ''))[:60]}); a {e['kind']} bump must move "
                       f"WITH it in the same window, never unattended ahead of it")
        lanes["AUTO"].remove(e)
        lanes["PLAN"].append(e)
        moved.append(e)
        # covered by the sibling's plan / planner dispatch — but that plan must
        # now describe BOTH halves, so flag it for the operator.
        if any(n.get("component", "").lower() == comp for n in needs_plan) and e not in needs_plan:
            needs_plan.append(e)
    return moved


def reconcile():
    policy = load_policy()
    actionable = parse_actionable()
    if actionable is None:
        return {"error": "version-check-current.md missing — run version-check first",
                "cracks": [{"component": "version-check", "reason": "no version data"}]}
    # Widen the universe beyond the one-image-per-app overview table, then
    # dedupe: the table row and the detail block describe the SAME bump.
    #
    # Dedupe on a NORMALISED target. The overview table TRUNCATES long cells
    # (`v0.143.0-noble-full → v0.144.1-noble-ful...`), so an exact-string key
    # never matched its own detail row and scrypted was counted twice — AUTO
    # read 4 when it was really 3. A lane count that overstates itself is the
    # same class of bug as CRACK 0 meaning "never looked at".
    repo_index: dict = {}
    detail = parse_detail_images(repo_index)
    by_key: dict = {}
    for i in actionable:
        by_key[(i["component"].lower(), i["kind"], _dedupe_tag(i["current"]),
                _dedupe_tag(i["target"]))] = i
    for extra in detail + parse_external_infra():
        k = (extra["component"].lower(), extra["kind"], _dedupe_tag(extra["current"]),
             _dedupe_tag(extra["target"]))
        dup = by_key.get(k)
        if (dup is not None and dup.get("image_repo") and extra.get("image_repo")
                and dup["image_repo"] != extra["image_repo"]):
            # two genuinely different images that merely share a version pair
            dup, k = None, k + (extra["image_repo"],)
        if dup is None:
            by_key[k] = extra
            actionable.append(extra)
        elif _is_truncated(dup.get("target")) and not _is_truncated(extra.get("target")):
            # same bump, but the detail row has the UNTRUNCATED tag and the
            # image repo — keep the better record in place.
            dup.update({kk: vv for kk, vv in extra.items() if vv is not None})
    # Attach the component's image repos to rows that carry tags only, so the
    # REBUILD decision can be made on the IMAGE (see is_self_built).
    for i in actionable:
        if i["kind"] == "image" and not i.get("image_repo"):
            i["image_repos"] = sorted(repo_index.get(i["component"].lower(), ()))
    prs = parse_renovate_prs()
    plans = load_plans()
    ar_holds = ar_prerelease_holds()

    lanes = {"AUTO": [], "PLAN": [], "REBUILD": [], "HELD": [], "CRACK": []}
    needs_plan = []  # PLAN-lane items with NO plan file yet → sweep must dispatch a planner
    plan_drift = []  # live plans whose target has fallen behind upstream
    seen_app_template = False
    for it in actionable:
        lane, reason, drift = assign_lane(it, policy, prs, plans, ar_holds)
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

    lockstep = _apply_lockstep(lanes, needs_plan)

    return {
        "counts": {k: len(v) for k, v in lanes.items()},
        "lockstep": lockstep,               # AUTO items pulled back to PLAN
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
    if r.get("lockstep"):
        L.append(f"\nLOCKSTEP HOLDS ({len(r['lockstep'])}) — pulled OUT of AUTO: a sibling of the "
                 f"same component is held, so this must move with it, not before it:")
        for e in r["lockstep"]:
            L.append(f"  • {e['component']} [{e['kind']} {e['current']}→{e['target']}] "
                     f"— held sibling: {e.get('lockstep_with')}")
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
