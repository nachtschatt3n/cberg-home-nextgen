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

A FOURTH source of candidates was added 2026-09-12: `max_rule_fallbacks()`. A
deny rule carrying `max: patch` permits patches, but Renovate only ever proposes
the NEWEST version — the blocked one — and the Renovate-PR shortcut then counted
that PR as coverage, so the permitted update was invisible to both halves of
Step 0. It now emits the stable-channel head as an ordinary direct-bump
candidate, holding fail-safe when the channel cannot be positively confirmed.

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
# CHANNEL_RULES lists components whose STABLE channel CANNOT be decided from a
# version string. Membership alone is the hold: never AUTO, always an assessed
# window plan. There is deliberately no predicate to evaluate.
#
# It used to hold a parity predicate ("stable": "odd-minor"), and that was
# DISPROVED on 2026-09-11: v0.118/120/122/124/126 and ~17 more scrypted releases
# all carry prerelease=false on EVEN minors. Parity was never the rule — the
# real gate is "does upstream publish a non-prerelease Release for this EXACT
# tag", which a version string cannot answer.
#
# Worse, the predicate failed OPEN in the direction that matters. `odd-minor`
# returned stable=True for ANY odd minor, so a Release-less dev tag such as
# v0.147.0 would have scored stable, routed to AUTO, and been applied unattended
# at Step 0 onto a privileged NVR. The deny rule in auto-update-policy.yaml was
# the only thing holding that door — so the "defence in depth" this comment used
# to claim was a single layer wearing two hats.
#
# Membership must stay OFFLINE-decidable: the window agent runs coverage.py
# without SWEEP_PG_DSN, so a DB- or network-gated check would fail open exactly
# where it matters. A set membership test cannot fail open.
CHANNEL_RULES = {
    "scrypted": {
        "ar": "AR-081",
        "why": ("upstream pushes dev builds to the SAME docker repo as stable, "
                "and stable-ness is decided by whether a non-prerelease GitHub "
                "Release exists for that exact tag — not by the version string. "
                "v0.146.1 was pullable from the registry with NO Release and no "
                "git tag at all (verified 2026-09-11)"),
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
    # Membership IS the hold — see CHANNEL_RULES. No predicate to fail open.
    rule = CHANNEL_RULES.get(comp)
    if rule:
        ar = f" ({rule['ar']}: unacceptable for a {rule['workload']})" if rule.get("ar") else ""
        return (f"{tgt} cannot be shown to be a STABLE-channel successor "
                f"offline — {rule['why']}{ar}. "
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


def deny_rule_for(policy, name, utype):
    """The deny rule that BLOCKS (name, utype), else None.

    Same traversal `denied()` uses — deliberately, because the two must never
    disagree about which rule is in force. Note the traversal does NOT stop at
    the first rule whose glob matches: it stops at the first rule that actually
    blocks, so a narrow `max:` rule can still fall through to a later catch-all
    (e.g. `*nextcloud-mcp*` max:patch → `*nextcloud*` full block for a PATCH).
    `auto-update.py::policy_block` has the identical shape; keep them in step.

    Split out so the `max:` fallback lane below can read the rule ITSELF (its
    `max`, its `reason`) rather than only the string `denied()` returns.
    """
    for rule in policy.get("deny", []) or []:
        pat = rule.get("match", "")
        if pat and _match_anywhere(name, pat):
            mx = rule.get("max")
            if mx is None or RANK.get(utype, 99) > RANK.get(mx, -1):
                return rule
    return None


def denied(policy, name, utype):
    """Return a reason if the deny-list blocks (name, utype), else None."""
    rule = deny_rule_for(policy, name, utype)
    if rule is None:
        return None
    return rule.get("reason", f"deny rule {rule.get('match')!r}")


_ROW = re.compile(r"^\|\s*`?([^`|]+?)`?\s*\|\s*`?([^`|]*)`?\s*\|\s*([^|]*)\|\s*([^|]*)\|\s*([^|]*)\|\s*([^|]*)\|\s*$")
_ARROW = re.compile(r"(\S+)\s*(?:→|->)\s*(\S+)")


def _version_components(v: str) -> list:
    """Every numeric component of a tag, never just the first three.

    `[:3]` made two Plex builds that differ ONLY in the 4th field
    (`1.43.3.10861` vs `1.43.3.10896`) parse identically — see
    `_is_strictly_newer` for what that cost. Callers pad with `_padded()`.
    """
    v = v.lstrip("vV").split("-")[0].split("+")[0].split("@")[0]
    return [int(x) for x in re.findall(r"\d+", v)]


def _padded(a: list, b: list, minimum: int = 3):
    """Zero-pad two component lists to a common length so they are
    comparable. Equates only the formatting difference (`1.38` vs `1.38.0`);
    every real ordering, 4+ components included, survives."""
    n = max(len(a), len(b), minimum)
    return a + [0] * (n - len(a)), b + [0] * (n - len(b))


def _semver_type(cur: str, tgt: str) -> str:
    """patch/minor/major from two versions (handles v-prefix, date tags like
    2026.7.2, alpine suffixes). unknown if unparseable."""
    a, b = _version_components(cur), _version_components(tgt)
    if not a or not b:
        return "unknown"
    a, b = _padded(a, b)
    if b[0] != a[0]:
        return "major"
    if b[1] != a[1]:
        return "minor"
    if b[2] != a[2]:
        return "patch"
    if b != a:
        # Equal through patch but not equal overall: the difference is in a
        # 4th or later component, i.e. a vendor BUILD bump. Returning
        # "unknown" here handed classification to the row's complexity
        # column, which describes the CHART, not this image.
        return "patch"
    return "unknown"


def _is_strictly_newer(cur: str, tgt: str) -> bool:
    """True only when `tgt` parses to a strictly-higher semver than `cur`.
    Defence-in-depth against a DOWNGRADE arrow leaking in from a stale/hand-
    edited version-check-current.md: `v3.1.0 → v1.116.0` is a downgrade, not
    an actionable update, and must never manufacture a PLAN-lane item. When
    either side is unparseable we keep the arrow (can't prove a downgrade, so
    don't silently drop a possibly-real update).

    It must be equally careful in the other direction. Truncating at three
    components made two Plex builds differing only in the 4th field compare
    EQUAL, so a real patch update returned False and was dropped before it
    ever reached a lane -- and an item that never enters the enumeration can
    never be reported as a crack, so `covered: YES (no cracks)` was printed
    over it. A suppressor that is also a denominator has to be right twice.
    """
    a, b = _version_components(cur), _version_components(tgt)
    if not a or not b:
        return True  # unparseable → don't suppress
    a, b = _padded(a, b)
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
        # NOTE: there is deliberately NO bare `line.startswith("## ")` reset here.
        # Upstream release notes are dumped verbatim into this document and
        # their own `##` headings are indistinguishable from structural ones --
        # 14 of the 32 `## ` lines in a typical snapshot are changelog noise
        # (`## 🐛 Bug fixes`, but also plain-ASCII ones like `## Availability`),
        # so no emoji or wording test separates them.
        #
        # The old blanket reset set ns=None on the FIRST such heading and thus
        # silently dropped every remaining app in that namespace from the repo
        # index. Observed 2026-09-04: mealie's changelog at lines 2801-2816
        # blinded paperless-db and paperless-ngx, so `image_repos` came back []
        # for both -- which fed a "cannot resolve" hold into the new G5 gate and
        # previously made REBUILD/self-built detection guess from a fallback set.
        # It is the same class the `- **File:**` guard already fixes for `###`.
        #
        # Dropping the reset is safe because `comp` is only ever set by an
        # `### app` heading that IS followed by `- **File:**`, and that line is
        # generated by check-all-versions.py -- release notes never contain it.
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


# ── G5 release-age cooldown for the DIRECT-BUMP lane ─────────────────────────
# WHY THIS EXISTS (F-0bd870a4, 2026-09-04). `minimum_release_age_hours` lived
# ONLY in auto-update.py, which gates Renovate PRs. The direct-bump exit below
# had no age check at all, so the lane with NO reviewable PR got LESS scrutiny
# than the lane with one. That is not theoretical: in the 2026-09-03 window PR
# #211 (curl) was held by G5 at 21h while gethomepage/homepage v2.2.0 was
# direct-bumped in 28c68f59 at ~40h -- inside the same 48h cooldown.
#
# Policy semantics are inherited verbatim from auto-update-policy.yaml:
#   * 0 disables the gate
#   * `age_waive` globs skip it
#   * UNKNOWN AGE HOLDS (fail-safe) -- the policy says so explicitly
#
# NOTE ON CVE BUMPS: auto-update.py can waive the cooldown on a security marker
# in the PR TITLE/LABELS. A direct bump has no PR, so that signal does not
# exist here and a CVE fix WILL be held for the cooldown. The operator lever is
# an `age_waive` glob in auto-update-policy.yaml. This is a deliberate,
# documented trade -- silently shipping unaged artifacts is what caused F-0bd870a4.
_AGE_CACHE: dict = {}


def _oci_created(host: str, path: str, tag: str, timeout: int = 20):
    """Image build timestamp from an OCI/Docker v2 registry, or None."""
    import urllib.request, urllib.parse
    def _get(url, hdrs):
        req = urllib.request.Request(url, headers=hdrs)
        return json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    tok = _get(f"https://{host}/token?scope=repository:{path}:pull&service={host}",
               {"User-Agent": "cberg-coverage"})
    bearer = tok.get("token") or tok.get("access_token")
    if not bearer:
        return None
    h = {"Authorization": f"Bearer {bearer}",
         "Accept": ",".join([
             "application/vnd.oci.image.index.v1+json",
             "application/vnd.docker.distribution.manifest.list.v2+json",
             "application/vnd.oci.image.manifest.v1+json",
             "application/vnd.docker.distribution.manifest.v2+json"])}
    man = _get(f"https://{host}/v2/{path}/manifests/{urllib.parse.quote(tag)}", h)
    if "manifests" in man:
        # Skip attestation/SBOM children: their platform is unknown/unknown and
        # they carry no image config blob. Picking manifests[0] blindly 404s.
        real = [m for m in man["manifests"]
                if (m.get("platform") or {}).get("architecture") not in (None, "unknown")]
        if not real:
            return None
        man = _get(f"https://{host}/v2/{path}/manifests/{real[0]['digest']}", h)
    cfg = (man.get("config") or {}).get("digest")
    if not cfg:
        return None
    blob = _get(f"https://{host}/v2/{path}/blobs/{cfg}",
                {"Authorization": f"Bearer {bearer}", "Accept": "*/*"})
    return blob.get("created")


def _dockerhub_created(repo: str, tag: str, timeout: int = 20):
    import urllib.request, urllib.parse
    if "/" not in repo:
        repo = "library/" + repo
    req = urllib.request.Request(
        f"https://hub.docker.com/v2/repositories/{repo}/tags/{urllib.parse.quote(tag)}",
        headers={"User-Agent": "cberg-coverage"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read()).get("last_updated")


def image_publish_age_hours(image_ref: str, tag: str):
    """Hours since `image_ref:tag` was published, or None when unknowable."""
    import datetime
    key = f"{image_ref}:{tag}"
    if key in _AGE_CACHE:
        return _AGE_CACHE[key]
    ts = None
    try:
        ref = image_ref.strip()
        host = ref.split("/")[0]
        if ref.startswith("docker.io/") or "." not in host:
            ts = _dockerhub_created(ref.replace("docker.io/", ""), tag)
        else:
            ts = _oci_created(host, "/".join(ref.split("/")[1:]), tag)
    except Exception:
        ts = None
    age = None
    if ts:
        try:
            dt = datetime.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            age = (datetime.datetime.now(datetime.timezone.utc) - dt).total_seconds() / 3600
        except Exception:
            age = None
    _AGE_CACHE[key] = age
    return age


# ── Chart publish age (the direct-bump cooldown, chart half) ────────────────
# Added 2026-09-07. The chart branch of direct_bump_age_gate used to return
# None ("may auto-apply") with the rationale "auto-update.py still gates their
# PRs". That premise is FALSE for exactly the items this gate governs: a
# DIRECT bump is by definition the no-PR path, so auto-update.py never sees it
# and no cooldown applied anywhere. Measured case that exposed it: plex chart
# 1.9.0, published 2026-09-07T20:22Z, would have been applied by the 03:30
# nightly ~5.5h old, while the identical hazard for IMAGES had been closed on
# 2026-09-05. Chart repos publish a per-version `created` in index.yaml, so
# the age IS measurable for HTTP repos and this closes the hole properly
# rather than by blanket-holding every chart.
_CHART_AGE_CACHE: dict = {}
_HELM_REPO_URL_CACHE: dict = {}


def _helm_repo_urls() -> dict:
    """HelmRepository name -> url, from the manifests in git."""
    if _HELM_REPO_URL_CACHE:
        return _HELM_REPO_URL_CACHE
    for f in sorted((REPO_ROOT / "kubernetes").rglob("*.yaml")):
        try:
            docs = list(yaml.safe_load_all(f.read_text(errors="ignore")))
        except Exception:
            continue
        for d in docs:
            if isinstance(d, dict) and d.get("kind") == "HelmRepository":
                nm = (d.get("metadata") or {}).get("name")
                url = (d.get("spec") or {}).get("url")
                if nm and url:
                    _HELM_REPO_URL_CACHE[nm] = url
    return _HELM_REPO_URL_CACHE


_CHART_REF_CACHE: dict = {}
# Sentinel, not `if _CHART_REF_CACHE:` — on a tree with no OCIRepository /
# HelmChart the cache stays legitimately EMPTY, and an emptiness test would
# re-walk every kubernetes/**/*.yaml with read_text on every call.
_CHART_REF_SCANNED = False


def _chart_ref_sources() -> dict:
    """(kind, name) -> (chart_name, version, repo_url) for chartRef targets.

    A HelmRelease names its chart EITHER inline under `spec.chart.spec` OR by
    pointing `spec.chartRef` at a source CR -- and in the second shape the
    version is NOT in the HelmRelease, it is on the referenced object
    (`OCIRepository.spec.ref.tag`, `HelmChart.spec.version`). This file knew
    only the first shape, so when k8s-gateway migrated to an OCIRepository on
    2026-09-11 `_chart_source_for()` stopped finding it at all. The symptom was
    invisible here because the age gate holds fail-safe on a None -- a correct
    HOLD reached for the wrong reason ("chart not found" rather than "OCI has
    no publish dates"), which is exactly the kind of right-answer-by-accident
    that stops being right when the surrounding logic changes.

    The digest on an OCIRepository ref is an immutability pin, never the
    version: k8s-gateway carries `tag: 3.7.2` AND a `digest:` together, and the
    tag is the human-meaningful version.
    """
    global _CHART_REF_SCANNED
    if _CHART_REF_SCANNED:
        return _CHART_REF_CACHE
    _CHART_REF_SCANNED = True
    for f in sorted((REPO_ROOT / "kubernetes").rglob("*.yaml")):
        try:
            text = f.read_text(errors="ignore")
        except OSError:
            continue
        # Cheap pre-filter: kubernetes/ also holds non-Kubernetes YAML dialects
        # (Authentik blueprints use a `!KeyOf` tag safe_load cannot construct).
        if "OCIRepository" not in text and "HelmChart" not in text:
            continue
        try:
            docs = list(yaml.safe_load_all(text))
        except Exception:
            continue
        for d in docs:
            if not isinstance(d, dict):
                continue
            kind = d.get("kind")
            name = ((d.get("metadata") or {}).get("name") or "").strip()
            spec = d.get("spec") or {}
            if kind == "OCIRepository" and name:
                url = str(spec.get("url") or "").strip().rstrip("/")
                ref = spec.get("ref") or {}
                chart = url.rpartition("/")[2]
                parent = url.rpartition("/")[0]
                # ONLY ref.tag. `ref.semver` is a RANGE resolved against the
                # registry at reconcile time, so it is not the deployed
                # version; accepting it would make the `ver == cur` equality
                # below match on a garbage string.
                ver = str(ref.get("tag") or "").strip()
                entry = (chart, ver, parent)
            elif kind == "HelmChart" and name:
                ref = (spec.get("sourceRef") or {}).get("name")
                entry = (
                    str(spec.get("chart") or "").strip(),
                    str(spec.get("version") or "").strip(),
                    _helm_repo_urls().get(ref),
                )
            else:
                continue
            prev = _CHART_REF_CACHE.get((kind, name))
            if prev is not None and prev != entry:
                # Two DIFFERENT objects sharing a (kind, name) key: last one
                # wins, so a chartRef could resolve to the wrong chart. Drop
                # the key entirely rather than pick a winner — `_chart_source_for`
                # then returns (None, None) and `direct_bump_age_gate` holds
                # fail-safe, which is the correct answer to an ambiguous
                # source. Silently overwriting risks the mask-a-stale-chart
                # direction instead.
                _CHART_REF_CACHE[(kind, name)] = (None, None, None)
                continue
            _CHART_REF_CACHE[(kind, name)] = entry
    return _CHART_REF_CACHE


def _chart_source_for(item):
    """(chart_name, repo_url) for a chart item, or (None, None).

    The HelmRelease is pinned by matching its DEPLOYED chart version against
    item['current'] within the item's namespace, rather than guessing from the
    component label -- report-side names (`otel-operator`, `open-webui`) do not
    map onto directory or release names, which is the same trap _namespace_text
    documents.

    Handles BOTH chart-source shapes -- see _chart_ref_sources().
    """
    ns, cur = (item.get("namespace") or "").strip(), item.get("current")
    if not ns or not cur:
        return None, None
    d = REPO_ROOT / "kubernetes" / "apps" / ns
    if not d.is_dir():
        return None, None
    for f in sorted(d.rglob("*.yaml")):
        try:
            docs = list(yaml.safe_load_all(f.read_text(errors="ignore")))
        except Exception:
            continue
        for doc in docs:
            if not isinstance(doc, dict) or doc.get("kind") != "HelmRelease":
                continue
            spec = doc.get("spec") or {}
            cs = ((spec.get("chart") or {}).get("spec") or {})
            if cs:
                if str(cs.get("version") or "").strip() != str(cur).strip():
                    continue
                chart = cs.get("chart")
                ref = (cs.get("sourceRef") or {}).get("name")
                if chart and ref:
                    return chart, _helm_repo_urls().get(ref)
                continue
            cref = spec.get("chartRef") or {}
            key = (str(cref.get("kind") or "").strip(),
                   str(cref.get("name") or "").strip())
            if not all(key):
                continue
            chart, ver, url = _chart_ref_sources().get(key, (None, None, None))
            if ver and str(ver).strip() == str(cur).strip() and chart:
                return chart, url
    return None, None


def chart_publish_age_hours(item):
    """Hours since this chart item's TARGET version was published, or None.

    None means UNKNOWABLE (OCI repo, unreachable index, or no `created` on the
    entry) -- the caller must treat that as hold-fail-safe, never as a pass.
    """
    import datetime
    key = f"{item.get('namespace')}/{item.get('component')}:{item.get('target')}"
    if key in _CHART_AGE_CACHE:
        return _CHART_AGE_CACHE[key]
    age = None
    chart, url = _chart_source_for(item)
    # oci:// indexes carry no per-version created date -- unverifiable, not old.
    if chart and url and not str(url).startswith("oci://"):
        import urllib.request
        try:
            req = urllib.request.Request(url.rstrip("/") + "/index.yaml",
                                         headers={"User-Agent": "coverage.py"})
            with urllib.request.urlopen(req, timeout=20) as r:
                entries = (yaml.safe_load(r.read()) or {}).get("entries") or {}
            for e in entries.get(chart) or []:
                if str(e.get("version") or "").strip() != str(item["target"]).strip():
                    continue
                c = e.get("created")
                if not c:
                    break
                dt = datetime.datetime.fromisoformat(str(c).replace("Z", "+00:00"))
                now = datetime.datetime.now(datetime.timezone.utc)
                age = (now - dt).total_seconds() / 3600.0
                break
        except Exception:
            age = None
    _CHART_AGE_CACHE[key] = age
    return age


def direct_bump_age_gate(item, policy):
    """None = may auto-apply; else a reason string that HOLDS it."""
    min_age = (policy or {}).get("minimum_release_age_hours") or 0
    if not min_age:
        return None
    dep = (item.get("component") or "").lower()
    repos = item.get("image_repos") or ([item["image_repo"]] if item.get("image_repo") else [])
    for pat in ((policy or {}).get("age_waive") or []):
        if fnmatch.fnmatch(dep, str(pat).lower()) or any(
                fnmatch.fnmatch((r or "").lower(), str(pat).lower()) for r in repos):
            return None
    if item.get("kind") == "chart":
        # Charts ARE gated (2026-09-07). See chart_publish_age_hours above for
        # why the old blanket exemption was wrong: the direct-bump lane is the
        # no-PR path, so "auto-update.py gates their PRs" did not apply to it.
        cage = chart_publish_age_hours(item)
        if cage is None:
            return (f"chart release age UNKNOWN for {item['component']} "
                    f"{item['target']} (OCI repo or no `created` in index.yaml) "
                    f"— cannot prove the {min_age:g}h cooldown elapsed; holding "
                    f"(fail-safe). Add an `age_waive` entry to accept it.")
        if cage < min_age:
            return (f"chart published {cage:.0f}h ago (< {min_age:g}h cooldown) "
                    f"— eligible in {min_age - cage:.0f}h")
        return None
    if item.get("kind") != "image":
        # Non-chart, non-image (external infra rows) keep the old behaviour.
        return None
    if not repos:
        # An IMAGE whose repository could not be resolved from the snapshot is
        # UNMEASURABLE, not safe. Returning None here would be the exact bug
        # this gate exists to close: a check that cannot see reporting a pass.
        # (Observed: paperless-ngx and scan-inbox-validator both reach this
        # branch with image_repos == [], and paperless-ngx:3.1.3 was 4.6h old.)
        return (f"image repository unresolved for {item['component']} — cannot "
                f"prove the {min_age:g}h cooldown elapsed; holding (fail-safe)")
    # An app can index SEVERAL repos (init containers, sidecars, base images),
    # so repos[0] is arbitrary -- it picked `busybox` for mealie and reported
    # the age of a tag that repo has never had. Prefer a repo whose name echoes
    # the component, then try each until one actually resolves THIS target tag:
    # a wrong repo simply does not carry `v3.25.1`, so it self-eliminates.
    ordered = sorted(repos, key=lambda r: (dep.split("-")[0] not in (r or "").lower(), r))
    age = tried = None
    for r in ordered:
        tried = r
        age = image_publish_age_hours(r, item["target"])
        if age is not None:
            break
    if age is None:
        return (f"release age UNKNOWN for {item['target']} across {len(ordered)} "
                f"candidate repo(s) (last tried {tried}) — cannot prove the "
                f"{min_age:g}h cooldown elapsed; holding (fail-safe)")
    if age < min_age:
        return (f"published {age:.0f}h ago (< {min_age:g}h cooldown) — eligible in "
                f"{min_age - age:.0f}h")
    return None


# ── The `max:` fallback — an ALLOWED update masked by a BLOCKED one ─────────
# WHY THIS EXISTS (2026-09-12, operator lever #3). A deny rule carrying `max:`
# says "patches are fine, minor+ is not". Nothing in the pipeline could act on
# the first half:
#
#   * auto-update.py only ever sees OPEN Renovate PRs, and Renovate proposes the
#     NEWEST version — which for a `max:`-held component is by definition the
#     blocked one. G2 holds it. Correct, and the end of that road.
#   * coverage.py's direct-bump lane is the no-PR path, and the component HAS a
#     PR, so the Renovate-PR shortcut in assign_lane() claimed it as covered.
#
# Measured case: n8n publishes beta/next on the next MINOR line with no
# prerelease marker, so it is held at `max: patch`. Renovate's PR proposed
# 2.38.4 -> 2.39.4 (the beta, correctly blocked) while 2.38.4 -> 2.38.7 — a
# plain patch on the STABLE line, explicitly permitted by that same rule — was
# invisible to both halves of Step 0 and could never land.
#
# This lane adds a SOURCE of candidates, never a bypass: every candidate it
# emits is re-run through assign_lane() and must clear G1 (type), G2 (the rule's
# own `max:`), G3 (breaking signal), G5 (release-age cooldown) exactly like any
# other direct bump. G4 (CI) is not applicable — a direct bump has no PR, which
# is the pre-existing property of this whole lane.
#
# THE HARD PART IS THE CHANNEL, and it is where this fails SAFE. The only
# reason a component carries `max:` at all is that registry semver cannot
# distinguish its stable line from its beta line; so "newest semver the rule
# allows" is precisely the wrong oracle — it would re-create the hazard the rule
# exists to prevent, one minor lower. A candidate is therefore eligible ONLY
# when upstream's own STABLE channel pointer is read and positively confirms it.
# An unresolvable channel is a HOLD, never a pass.
#
# The lookup is a read-only, timeout-bounded registry read kept inside this
# module on purpose: `plan-premises.py`'s allowlist refuses network verbs and
# must NOT be widened to accommodate this.
_UA = "cberg-coverage"
_CHANNEL_TAGS = ("stable", "latest")
_VERSION_LABELS = ("org.opencontainers.image.version", "org.label-schema.version")
_PLAIN_VERSION = re.compile(r"^v?\d+(?:\.\d+){1,3}$")
_CHANNEL_TIMEOUT = 12
_MANIFEST_ACCEPT = ",".join([
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
])
_STABLE_HEAD_CACHE: dict = {}


def _registry_coords(image_ref: str):
    """(registry_host, auth_host, auth_service, repo_path) for an image ref."""
    ref = str(image_ref).strip()
    if ref.startswith("docker.io/"):
        ref = ref[len("docker.io/"):]
    host = ref.split("/")[0]
    if "." not in host and ":" not in host:
        path = ref if "/" in ref else "library/" + ref
        return "registry-1.docker.io", "auth.docker.io", "registry.docker.io", path
    return host, host, host, "/".join(ref.split("/")[1:])


def _http_json(url: str, headers: dict, timeout: int):
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": _UA, **headers})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read()), dict(resp.headers)


def _registry_token(auth_host: str, service: str, path: str, timeout: int):
    d, _ = _http_json(
        f"https://{auth_host}/token?service={service}&scope=repository:{path}:pull",
        {}, timeout)
    return d.get("token") or d.get("access_token")


def _manifest_and_digest(reg: str, path: str, ref: str, bearer: str, timeout: int):
    import urllib.parse
    return _http_json(
        f"https://{reg}/v2/{path}/manifests/{urllib.parse.quote(str(ref))}",
        {"Authorization": f"Bearer {bearer}", "Accept": _MANIFEST_ACCEPT}, timeout)


def _tag_labels_and_digest(reg: str, path: str, tag: str, bearer: str, timeout: int):
    """(config labels dict, content digest of the tag) — ({}, None) on miss."""
    man, hdrs = _manifest_and_digest(reg, path, tag, bearer, timeout)
    digest = hdrs.get("Docker-Content-Digest") or hdrs.get("docker-content-digest")
    if "manifests" in man:
        # attestation/SBOM children carry no image config; skip them (same
        # filter as _oci_created).
        real = [m for m in man["manifests"]
                if (m.get("platform") or {}).get("architecture") not in (None, "unknown")]
        if not real:
            return {}, digest
        man, _ = _manifest_and_digest(reg, path, real[0]["digest"], bearer, timeout)
    cfg = (man.get("config") or {}).get("digest")
    if not cfg:
        return {}, digest
    blob, _ = _http_json(f"https://{reg}/v2/{path}/blobs/{cfg}",
                         {"Authorization": f"Bearer {bearer}", "Accept": "*/*"}, timeout)
    return ((blob.get("config") or {}).get("Labels") or {}), digest


def _dockerhub_version_for_digest(repo: str, digest: str, timeout: int):
    """Newest plain-semver Docker Hub tag sharing `digest`, or None.

    Secondary oracle, used only when the image carries no version label. It
    reads ONE page of tags ordered by recency: a channel pointer that was just
    moved has its version twin on that page, and if it does not, we return None
    and the caller HOLDS — which is the right direction to be wrong in.
    """
    d, _ = _http_json(
        f"https://hub.docker.com/v2/repositories/{repo}/tags/"
        f"?page_size=100&ordering=last_updated", {}, timeout)
    best = None
    for row in d.get("results") or []:
        name = str(row.get("name") or "")
        if row.get("digest") != digest or not _PLAIN_VERSION.match(name):
            continue
        if _PRERELEASE_TAG.search(name):
            continue
        t = _ver_tuple(name)
        if t and (best is None or t > _ver_tuple(best)):
            best = name
    return best


def stable_channel_version(image_ref: str, timeout: int = _CHANNEL_TIMEOUT):
    """(version, evidence) for the tag upstream's STABLE channel points at.

    Returns (None, why) when it cannot be established — which the caller MUST
    treat as a hold. Two positive oracles, in order:

      1. the `stable` (then `latest`) tag's OCI config label
         `org.opencontainers.image.version`, CROSS-CHECKED by resolving that
         version as a tag and requiring the same content digest. A label alone
         is upstream prose; label + digest identity is proof the channel
         pointer and the version tag are the same image.
      2. Docker Hub only: reverse-lookup of the channel digest across one page
         of recent tags.

    Never infers from version ordering. That inference is the exact failure the
    `max:` rules exist to prevent.
    """
    key = str(image_ref)
    if key in _STABLE_HEAD_CACHE:
        return _STABLE_HEAD_CACHE[key]
    result = (None, "channel lookup not attempted")
    try:
        reg, auth_host, service, path = _registry_coords(image_ref)
        bearer = _registry_token(auth_host, service, path, timeout)
        if not bearer:
            result = (None, f"no pull token for {image_ref}")
        else:
            misses = []
            for ch in _CHANNEL_TAGS:
                try:
                    labels, ch_digest = _tag_labels_and_digest(reg, path, ch, bearer, timeout)
                except Exception as e:
                    misses.append(f"`{ch}` unreadable ({type(e).__name__})")
                    continue
                ver = None
                for lbl in _VERSION_LABELS:
                    v = str(labels.get(lbl) or "").strip()
                    if _PLAIN_VERSION.match(v) and not _PRERELEASE_TAG.search(v):
                        ver, lbl_used = v, lbl
                        break
                if ver:
                    try:
                        _, vd = _manifest_and_digest(reg, path, ver, bearer, timeout)
                        v_digest = (vd.get("Docker-Content-Digest")
                                    or vd.get("docker-content-digest"))
                    except Exception:
                        v_digest = None
                    if ch_digest and v_digest and ch_digest != v_digest:
                        misses.append(
                            f"`{ch}` label says {ver} but tag {ver} is a DIFFERENT image")
                        continue
                    result = (ver, f"`{ch}` tag label {lbl_used}={ver}"
                                   + (", digest-confirmed" if ch_digest and v_digest else ""))
                    break
                if ch_digest and reg == "registry-1.docker.io":
                    hub = _dockerhub_version_for_digest(path, ch_digest, timeout)
                    if hub:
                        result = (hub, f"Docker Hub `{ch}` digest == tag {hub}")
                        break
                misses.append(f"`{ch}` carries no version label")
            else:
                result = (None, "; ".join(misses) or "no stable/latest channel tag")
    except Exception as e:
        result = (None, f"channel lookup failed ({type(e).__name__})")
    _STABLE_HEAD_CACHE[key] = result
    return result


_G3_CACHE: dict = {}


def breaking_change_signal(image_repo: str, tag: str):
    """(is_breaking, note) — G3 for a candidate that has no Renovate PR.

    Reuses auto-update.py's engine so the two lanes agree on what "breaking"
    means. Best-effort by design and it says so: a POSITIVE signal holds, an
    unfetchable release note is reported as `unverified` and does NOT hold.
    That asymmetry is deliberate. G3-unknown is the pre-existing baseline of
    every direct bump in this lane, so demanding certainty here would be a NEW
    gate (and, under an unauthenticated GitHub rate limit, a permanently closed
    one) rather than honouring an existing one. The CHANNEL gate above is the
    opposite — it holds on unknown — because the channel IS the hazard the
    `max:` rule was written for.
    """
    key = f"{image_repo}:{tag}"
    if key in _G3_CACHE:
        return _G3_CACHE[key]
    out = (False, "unverified (release notes unavailable)")
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "cberg_auto_update", SCRIPT_DIR / "auto-update.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore
        notes, resolved = mod.breaking_signal(mod._load_version_checker(), image_repo, tag)
        if notes:
            out = (True, "breaking-change signal in release notes: "
                         + "; ".join(str(n)[:100] for n in notes[:2]))
        elif resolved:
            out = (False, "clean (release notes checked)")
    except Exception:
        pass
    _G3_CACHE[key] = out
    return out


def _fallback_item(item, target, utype, rule, evidence, pr=None, g3=None):
    """A synthetic actionable item for the allowed-but-masked update."""
    return {**{k: v for k, v in item.items() if k not in ("cell", "source")},
            "target": target,
            "type": utype,
            "cell": f"{item['current']} → {target}",
            "source": "max-rule-allowed",
            "max_rule_fallback": True,
            "origin_target": item["target"],
            "deny_match": rule.get("match"),
            "deny_max": rule.get("max"),
            "blocked_pr": pr,
            "channel_evidence": evidence,
            "g3": g3}


def max_rule_fallbacks(actionable, policy, prs=None):
    """[(record, item_or_None)] — the ALLOWED update hiding behind a BLOCKED one.

    One record per item whose target is blocked by a `max:` rule, with
    `status` one of:
      candidate   — a stable-channel version the rule allows; `item` is a real
                    actionable entry appended to the universe
      hold        — the channel could not be confirmed, or the stable head is
                    itself blocked; reported, never applied
      up-to-date  — the stable channel head is already deployed; nothing to do
    """
    prs = prs or {}
    out = []
    seen = {(i["component"].lower(), i["kind"], _dedupe_tag(i["current"]),
             _dedupe_tag(i["target"])) for i in actionable}
    for item in actionable:
        comp = item["component"].lower()
        if item.get("max_rule_fallback") or comp in HELD:
            continue
        is_app_template = item["kind"] == "chart" and str(item["target"]).startswith("5.")
        key = "app-template" if is_app_template else comp
        rule = deny_rule_for(policy, key, item["type"])
        mx = (rule or {}).get("max")
        if not rule or mx not in RANK:
            continue                      # no rule, or a FULL block: nothing is allowed
        if RANK.get(item["type"], 99) <= RANK.get(mx, -1):
            continue                      # not actually blocked by the `max:`
        rec = {"component": item["component"], "kind": item["kind"],
               "current": item["current"], "blocked_target": item["target"],
               "blocked_type": item["type"], "deny_match": rule.get("match"),
               "deny_max": mx, "blocked_pr": prs.get(comp) or prs.get(key)}
        if is_self_built(item, comp):
            continue                      # REBUILD lane — a tag bump can't move it
        if item["kind"] != "image":
            out.append({**rec, "status": "hold", "candidate": None,
                        "reason": "no stable-channel oracle exists for a CHART "
                                  "(registries publish channel pointers, chart "
                                  "repos do not) — holding (fail-safe)"})
            continue
        repos = [r for r in ([item.get("image_repo")] if item.get("image_repo")
                             else item.get("image_repos") or []) if r]
        if len(repos) != 1:
            out.append({**rec, "status": "hold", "candidate": None,
                        "reason": f"image repository {'unresolved' if not repos else 'ambiguous'} "
                                  f"({len(repos)} candidates) — the channel cannot be read "
                                  f"from a repo we cannot name; holding (fail-safe)"})
            continue
        repo = repos[0]
        ver, why = stable_channel_version(repo)
        if not ver:
            out.append({**rec, "status": "hold", "candidate": None,
                        "reason": f"stable channel of {repo} NOT confirmable — {why}. "
                                  f"Refusing to fall back to 'newest semver wins': that "
                                  f"inference is the hazard `max: {mx}` exists to prevent"})
            continue
        if not _is_strictly_newer(item["current"], ver):
            out.append({**rec, "status": "up-to-date", "candidate": None,
                        "reason": f"stable channel head is {ver} ({why}); "
                                  f"{item['current']} is already at or ahead of it"})
            continue
        utype = _semver_type(item["current"], ver)
        blocked = denied(policy, key, utype)
        if blocked:
            out.append({**rec, "status": "hold", "candidate": ver,
                        "reason": f"stable channel head {ver} ({why}) is a {utype} bump, "
                                  f"which the policy still blocks — {str(blocked)[:120]}"})
            continue
        k = (comp, item["kind"], _dedupe_tag(item["current"]), _dedupe_tag(ver))
        if k in seen:
            # Already enumerated in its own right, so it is NOT masked and must
            # not be appended twice (a double-counted lane is the same class of
            # bug as a missed one). Still reported — silently swallowing it
            # would make the two cases indistinguishable in the output.
            out.append({**rec, "status": "already-enumerated", "candidate": ver,
                        "reason": f"stable channel head {ver} ({why}) is already in "
                                  f"the actionable universe on its own — no masking"})
            continue
        seen.add(k)
        is_breaking, g3 = breaking_change_signal(repo, ver)
        if is_breaking:
            out.append({**rec, "status": "hold", "candidate": ver,
                        "reason": f"G3 — {g3}"})
            continue
        new = _fallback_item(item, ver, utype, rule, why,
                             pr=rec["blocked_pr"], g3=g3)
        out.append({**rec, "status": "candidate", "candidate": ver, "item": new,
                    "channel_evidence": why, "g3": g3,
                    "reason": f"{utype} to {ver} on the stable channel ({why}) — "
                              f"permitted by `max: {mx}`, masked by the blocked "
                              f"{item['type']} to {item['target']}"})
    return out


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
    # The Renovate-PR shortcut is SKIPPED for a `max:`-fallback candidate. That
    # PR exists, but it proposes the BLOCKED target — claiming this candidate as
    # "covered by PR #N" is exactly the masking max_rule_fallbacks() was written
    # to undo, and it would also route the item away from the direct-bump half
    # of Step 0 (the window agent skips AUTO items whose reason names a PR).
    if not item.get("max_rule_fallback") and (prs.get(comp) or prs.get(key)):
        return "AUTO", f"Renovate PR #{prs.get(comp) or prs.get(key)}", None
    dn = denied(policy, key, utype)
    if dn or utype == "major" or utype == "unknown":
        return "PLAN", (dn or f"{utype} — needs an assessed window plan"), None
    if utype in ("patch", "minor"):
        # G5 cooldown applies to the DIRECT-BUMP lane too (F-0bd870a4). The
        # Renovate-PR exit above is deliberately NOT gated here: auto-update.py
        # already applies G5 to PRs, and double-gating would hold them twice.
        cooldown = direct_bump_age_gate(item, policy)
        if cooldown:
            return "HELD", f"G5 release-age cooldown — {cooldown}", None
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


# ── Live-repo cross-check (the snapshot is not the cluster) ─────────────────
# version-check-current.md is a SNAPSHOT the sweep writes every 48h. Maintenance
# windows apply bumps BETWEEN sweeps, so the snapshot keeps proposing updates
# that already landed: on 2026-08-23 the sun-window applied 10 of the 12 AUTO
# items and re-running this reconciler returned byte-identical output. The AUTO
# lane could never self-clear, so every window re-proposed the same batch and
# the operator could not tell a pending bump from a done one. Cross-check each
# item against the manifests actually in git before counting it actionable.
_NS_TEXT_CACHE: dict = {}
_YAML_COMMENT = re.compile(r"(?m)(?:^[ \t]*#.*$|[ \t]+#.*$)")


def _strip_yaml_comments(text: str) -> str:
    """Drop YAML comments before version matching.

    A bump's changelog comment routinely names the version it REPLACED
    (`# 2026-08-18: chart 12.11.0 (Grafana 13.2.0) — routine minor`), so the old
    version lingers in the file long after the bump landed and the
    already_applied test never fired. Grafana's 12.11.0→12.11.1 stayed in AUTO
    for exactly that reason. A comment is not a deployed version.
    """
    return _YAML_COMMENT.sub("", text)


def _namespace_text(ns: str):
    """Concatenated manifest text under kubernetes/apps/<ns>/, else None.

    Scoped by NAMESPACE, not component: the namespace comes straight off the
    report row and is reliable, whereas component labels here are report-side
    names (`otel-operator`, `tube-archivist-redis`, `open-webui` for its redis
    sidecar) that do not map onto directory names.
    """
    if ns in _NS_TEXT_CACHE:
        return _NS_TEXT_CACHE[ns]
    d = REPO_ROOT / "kubernetes" / "apps" / ns
    txt = None
    if d.is_dir():
        parts = []
        for f in sorted(d.rglob("*.yaml")):
            try:
                parts.append(_strip_yaml_comments(f.read_text(errors="ignore")))
            except OSError:
                pass
        txt = "\n".join(parts)
    _NS_TEXT_CACHE[ns] = txt
    return txt


def already_applied(item) -> bool:
    """True only when the bump is PROVABLY in git already.

    Deliberately conservative in one direction. A false "already applied"
    silently drops a real update — the exact CRACK this file exists to prevent —
    so the test demands BOTH that the target version is present in the namespace
    AND that the current one is gone. If the old version still appears anywhere
    in that namespace we keep the item and re-propose an applied bump, which
    costs a redundant no-op and nothing else.
    """
    cur, tgt = item.get("current"), item.get("target")
    ns = (item.get("namespace") or "").strip()
    if not ns or not cur or not tgt:
        return False
    if _is_truncated(cur) or _is_truncated(tgt):
        return False          # a clipped tag cannot be matched literally
    txt = _namespace_text(ns)
    if txt is None:
        return False          # external infra / unresolvable ns → never assume
    return (tgt in txt) and (cur not in txt)


def snapshot_age_hours():
    """Age of version-check-current.md in hours, or None if absent."""
    if not VERSION_MD.exists():
        return None
    import time
    return (time.time() - VERSION_MD.stat().st_mtime) / 3600.0


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
            holders.setdefault(str(e.get("component", "")).lower(), []).append((lane, e))
    moved = []
    for e in list(lanes["AUTO"]):
        comp = str(e.get("component", "")).lower()
        cands = list(holders.get(comp) or ())
        if e.get("max_rule_fallback"):
            # A `max:`-fallback candidate's own ORIGIN (the same image on the
            # blocked higher target) is not a "sibling half" — it is the very
            # item this candidate exists to unmask, and it is ALWAYS in PLAN.
            # Letting it lockstep would make the new lane permanently inert.
            cands = [(l, h) for l, h in cands
                     if not (h.get("kind") == e.get("kind")
                             and _dedupe_tag(h.get("target")) == _dedupe_tag(e.get("origin_target")))]
        if not cands:
            continue
        hlane, he = cands[0]
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
    # An update the deny rule ALLOWS can be masked by one it blocks — surface it
    # as an ordinary candidate (see max_rule_fallbacks). Emitted BEFORE the
    # already_applied filter and the lane loop so it is subject to both.
    fallbacks = max_rule_fallbacks(actionable, policy, prs)
    for rec in fallbacks:
        if rec.get("item") is not None:
            actionable.append(rec["item"])
    # Drop what the maintenance window already applied (see already_applied).
    # Reported, never silently swallowed: a suppressed item that was NOT really
    # applied would be an invisible crack, so the operator sees the list.
    applied = [i for i in actionable if already_applied(i)]
    if applied:
        _drop = {id(i) for i in applied}
        actionable = [i for i in actionable if id(i) not in _drop]

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

    # Stamp each fallback's FINAL lane back onto its record, so the operator can
    # see a candidate that was generated correctly and then legitimately parked
    # (a live plan already targets it, or G5's cooldown has not elapsed). A
    # candidate reported without its lane would read as "will apply".
    placed = {}
    for lane, entries in lanes.items():
        for e in entries:
            if e.get("max_rule_fallback"):
                placed[(str(e["component"]).lower(), e["kind"],
                        _dedupe_tag(e["current"]), _dedupe_tag(e["target"]))] = (lane, e["reason"])
    for rec in fallbacks:
        if rec.get("status") != "candidate":
            continue
        k = (str(rec["component"]).lower(), rec["kind"],
             _dedupe_tag(rec["current"]), _dedupe_tag(rec["candidate"]))
        rec["lane"], rec["lane_reason"] = placed.get(k, ("DROPPED", "already applied in git"))
        rec.pop("item", None)

    return {
        "counts": {k: len(v) for k, v in lanes.items()},
        "max_rule_fallback": fallbacks,     # allowed update masked by a blocked one
        "already_applied": applied,         # in the snapshot, already in git
        "snapshot_age_hours": snapshot_age_hours(),
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
    age = r.get("snapshot_age_hours")
    if age is not None:
        stale = age > 50            # the sweep runs every 48h; 50 allows for jitter
        L.append(f"source: version-check-current.md, {age:.0f}h old"
                 + ("  ⚠️  STALE — an update published since the last sweep is NOT "
                    "in this report; these lanes describe the last snapshot, not "
                    "live upstream" if stale else ""))
    if r.get("already_applied"):
        L.append(f"\nALREADY APPLIED ({len(r['already_applied'])}) — in the snapshot, "
                 f"already in git; dropped from the lanes below:")
        for e in r["already_applied"]:
            L.append(f"  • {e['component']} [{e['kind']} {e['current']}→{e['target']}]")
    fb = r.get("max_rule_fallback") or []
    if fb:
        L.append(f"\n`max:` RULE FALLBACK ({len(fb)}) — the deny rule blocks the newest "
                 f"version but ALLOWS a lower one; Renovate only ever proposes the newest:")
        for e in fb:
            tag = {"candidate": "✅ candidate", "hold": "⛔ hold",
                   "up-to-date": "· up-to-date",
                   "already-enumerated": "· already enumerated"}.get(
                       e.get("status"), e.get("status"))
            lane = f" → {e['lane']} ({str(e.get('lane_reason'))[:50]})" if e.get("lane") else ""
            L.append(f"  • {e['component']} [{e['kind']}] blocked {e['current']}→"
                     f"{e['blocked_target']} ({e['blocked_type']}, max: {e['deny_max']}) "
                     f"— {tag}{lane}")
            L.append(f"      {str(e.get('reason'))[:160]}")
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
