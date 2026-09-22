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

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from lib.plan_matching import normalize_name  # noqa: E402

# ── Component identity: EXTERNAL DISPLAY NAME -> PLAN COMPONENT KEY ─────────
# F-21865cc4 / F-3bc51210. The External Infrastructure section of the version
# report names the node OS `Talos Linux`; every talos PLAN carries
# `component: talos`. assign_lane() lowercased to `talos linux`, load_plans()
# keyed `{talos}`, the sets never intersected, and so an approved, windowed
# plan (talos-1.14.1, sun-attended) was reported NEEDS A PLAN on every sweep —
# one redundant upgrade-planner dispatch per cycle, for three cycles running.
#
# Normalisation ALONE does not fix it, which is what F-3bc51210's Action
# claimed and why that Action was corrected on the record: normalize_name(
# "Talos Linux") is `talos-linux`, which still does not equal `talos`. Routing
# through lib.plan_matching.match_held_to_plan() only ever matched this pair
# via its SECOND tier (version_pair_match), a fallback that stops matching the
# moment the plan's target drifts — silently, and drift is the recurring
# condition here. An EXPLICIT alias is the fix: it is a stated identity, not an
# inference, and it survives any target drift.
#
# Keep this table SHORT and one-directional (display name -> plan key). It is
# not a place to paper over a component that should simply be renamed.
COMPONENT_ALIASES = {
    "talos linux": "talos",
    "talos-linux": "talos",
}


def _name_keys(name) -> set:
    """Every spelling a component may be matched by: raw-lowercase, normalized,
    and any explicit alias of either.

    BOTH SIDES get normalized. Measured 2026-09-21: normalisation is the
    identity for 39 of 40 plan components and 22 of 23 item components — only
    the helm-drift plan's `flux/helm-controller` and the external
    `Talos Linux` move — so normalizing one side only would have silently
    stopped matching the helm-drift plan while fixing talos.
    """
    raw = str(name or "").lower().strip()
    out = {raw, normalize_name(raw)}
    for k in list(out):
        alias = COMPONENT_ALIASES.get(k)
        if alias:
            out.add(alias)
    return {k for k in out if k}


def _item_repos(item) -> list:
    """The image repositories an item names (single or multi-image row)."""
    return [r for r in ([item.get("image_repo")] if item.get("image_repo")
                        else item.get("image_repos") or []) if r]

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
_AR_ROWS_CACHE = None


def accepted_risk_rows() -> list:
    """[(ar_id, description, justification)] for ENABLED, accepted risks.

    Best-effort: needs SWEEP_PG_DSN + psycopg, and returns [] without them.
    Every consumer must therefore degrade SAFELY on an empty list — the window
    agent runs coverage.py with no DSN, so anything gated on this must fail in
    the direction of MORE scrutiny, never less.
    """
    global _AR_ROWS_CACHE
    if _AR_ROWS_CACHE is not None:
        return _AR_ROWS_CACHE
    _AR_ROWS_CACHE = []
    dsn = os.environ.get("SWEEP_PG_DSN")
    if not dsn:
        return _AR_ROWS_CACHE
    try:
        import psycopg
        with psycopg.connect(dsn, connect_timeout=5) as conn, conn.cursor() as cur:
            cur.execute("SELECT ar_id, description, justification FROM accepted_risks "
                        "WHERE enabled = true AND status = 'accepted'")
            _AR_ROWS_CACHE = list(cur.fetchall())
    except Exception:
        _AR_ROWS_CACHE = []
    return _AR_ROWS_CACHE


def _item_finding_titles(item) -> list:
    """The finding titles this item would be emitted under.

    Mirrors findings_writer's `<name>: <kind> <repo> <cur> → <tgt>` shape,
    because an AR `description` is a SUBSTRING NEEDLE matched against finding
    titles (sweep-run.py::_apply_ar_suppression) — so the only honest way to
    ask "does an AR already dispose of this item" is to build the same string
    the needle was written against. One per candidate repo, plus a repo-less
    form for rows that carry tags only.
    """
    comp = str(item.get("component") or "")
    kind = str(item.get("kind") or "")
    cur, tgt = item.get("current"), item.get("target")
    out = [f"{comp}: {kind} {cur} → {tgt}"]
    for repo in _item_repos(item):
        out.append(f"{comp}: {kind} {repo} {cur} → {tgt}")
    return out


def ar_accepts_item(item, rows=None):
    """AR-ID of an ENABLED accepted risk that already disposes of this item.

    F-a95ba973: coverage.py received `ar_holds` but used them ONLY for
    channel_hold, so an ORDINARY acceptance could never reach the lane
    decision. AR-113 accepts the authentik bundled-postgres 17.11 -> 18.6 pin
    (the migration was EXECUTED; the 17.11 StatefulSet is the deliberate
    rollback copy, scheduled for retirement by its own plan) and DID suppress
    the matching version finding in the same run — while needs_plan still
    asked for an upgrade-planner to plan an upgrade of a database the operator
    has decided to delete.

    This NEVER changes a lane, only planner dispatch: the item stays in PLAN so
    the lane counts remain honest. An unreachable policy DB yields no rows and
    the item simply keeps its planner — the degradation costs a redundant
    dispatch, never a missed one.
    """
    rows = accepted_risk_rows() if rows is None else rows
    titles = [t.lower() for t in _item_finding_titles(item)]
    for ar_id, desc, _just in rows or []:
        needle = str(desc or "").strip().lower()
        # Short needles are matched against every finding title in the DB and
        # are linted there; here they would be indiscriminate, so require a
        # substantive one.
        if len(needle) < 8:
            continue
        if any(needle in t for t in titles):
            return ar_id
    return None


_DECLINE_RE = re.compile(r"\bDECLINED?\b")


def plan_declines(item, plans):
    """plan_id of a plan whose frontmatter DECLINES this exact bump, else None.

    The other half of F-a95ba973. `authentik-pg18-lockstep` states in its
    `target` field: "bundled/rollback postgresql image bump to 18.6-bookworm
    DECLINED — stays pinned 17.11-bookworm". That is a recorded DECISION, and
    unlike pending work a decision does not expire when the plan executes —
    which is why DEAD_PLAN_STATUSES is deliberately NOT applied here. Without
    this, the decision is invisible and rule 4d re-dispatches a planner to
    re-derive it every cycle.

    Narrow on purpose: the decline marker AND the item's exact target version
    must both appear in the plan's own current/target fields.
    """
    keys = _name_keys(str(item.get("component") or ""))
    uv = _ver_tuple(item.get("target"))
    if not uv:
        return None
    for plan in plans or []:
        if not ((plan.get("keys") or set()) | (plan.get("also_keys") or set())) & keys:
            continue
        blob = f"{plan.get('target') or ''} {plan.get('current') or ''}"
        if not _DECLINE_RE.search(blob):
            continue
        if any(_ver_tuple(t) == uv for t in _VER_TOKEN.findall(blob)):
            return plan["plan_id"]
    return None


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
    rows = accepted_risk_rows()
    if not rows:
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
    disagree about which rule is in force.

    THE FIRST RULE WHOSE GLOB MATCHES DECIDES, and its verdict is final
    (changed 2026-09-12). Ordering IS how this file expresses specificity: the
    policy YAML places `*nextcloud-mcp*` above `*nextcloud*` and says in a
    comment "first match wins", precisely so the MCP bridge is judged by its
    own reason. The traversal used to continue past a rule that matched but
    did not block, which meant a narrow `max: patch` rule fell through to a
    later catch-all — so `nextcloud-mcp` PATCH was blocked, and blocked while
    reporting the Nextcloud SERVER's occ-migration reason, which is false for a
    standalone bridge with no chart coupling and no occ. That is the exact
    failure the policy file warns about two rules above the pair: a hold
    carrying a false reason gets overridden by a human, and the real risk rides
    along unnoticed. It also silently made the operator's 2026-09-12 narrowing
    inert.

    Consequence to keep in mind when EDITING the policy: a narrow rule now
    shadows every later rule for the components it matches, so a catch-all can
    no longer backstop it. Put the specific rule first and make its reason
    true on its own.

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
            # Matched, and `max:` permits this update type: that is a decisive
            # ALLOW. Do NOT keep scanning — see the docstring.
            return None
    return None


def denied(policy, name, utype):
    """Return a reason if the deny-list blocks (name, utype), else None."""
    rule = deny_rule_for(policy, name, utype)
    if rule is None:
        return None
    return rule.get("reason", f"deny rule {rule.get('match')!r}")


def deny_rule_for_item(policy, item, key, utype):
    """The deny rule blocking this ITEM — matched on component OR image repo.

    `deny_rule_for()` answers about one NAME, and WHICH name it is handed
    decides whether a rule fires at all. The two lanes hand it different ones:
    auto-update.py's PR gate passes the Renovate depName
    (`policy_block(policy, parsed['dep'], …)`, e.g. `valkey/valkey`), while this
    file passed only the component (`penpot-cache`). So an operator following
    the documented procedure — CLAUDE.md's "to hold a component back, add a
    deny rule to the policy YAML" — got a rule that blocked the PR path and was
    silently inert HERE, in the lane an unattended nightly actually applies
    (F-7bad8aeb). Nothing reported the mismatch.

    Component key first, so every existing match and its reason are unchanged;
    only then the image repositories the item names.

    DIRECTION IS SAFE BY CONSTRUCTION. This can only find a rule where none was
    found before, so it can only move work OUT of the unattended lane, never
    into it — the same property `_apply_lockstep` relies on. Measured across the
    whole live item set before the change: exactly TWO items gain a hold —
    penpot-cache via `valkey/valkey`, and paperless-db via `mariadb` against the
    "a DB-engine bump is never unattended-safe" rule — and both were already in
    PLAN, so no lane outcome regressed.
    """
    rule = deny_rule_for(policy, key, utype)
    if rule:
        return rule
    for repo in _item_repos(item):
        rule = deny_rule_for(policy, str(repo).lower(), utype)
        if rule:
            return rule
    return None


def denied_for_item(policy, item, key, utype):
    """Reason the deny-list blocks this item by component OR image repo, else None."""
    rule = deny_rule_for_item(policy, item, key, utype)
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


_PR_LINE = re.compile(r"\[#(\d+)\].*?update\s+(.+?)\s*\(")
# `aqua:cloudflare/cloudflared` — a Renovate MANAGER prefix, not a registry
# host. The negative lookahead keeps `https://` and friends out of it.
_MANAGER_PREFIX = re.compile(r"^([a-z][a-z0-9_-]*):(?!//)(.+)$", re.IGNORECASE)
# Managers that can never describe a container image running in this cluster.
_NON_IMAGE_MANAGERS = {"aqua", "npm", "pypi", "gomod", "cargo", "nuget",
                       "github-release", "github-releases", "helm"}


def _pr_record(number, dep):
    m = _MANAGER_PREFIX.match(dep)
    manager, path = (m.group(1).lower(), m.group(2)) if m else (None, dep)
    return {"number": str(number), "dep": dep, "manager": manager,
            "path": path.strip().strip("/")}


def parse_renovate_prs():
    """{lookup key: [pr record, …]} for every open Renovate PR.

    A DICT OF LISTS, keyed on several spellings, because the old map stored ONE
    PR per dep BASENAME and collapsed collisions last-wins (F-ebd51739). Two
    open PRs reduced to the key `cloudflared`: #214
    `docker.io/cloudflare/cloudflared` (the internet-facing tunnel CONTAINER)
    and #215 `aqua:cloudflare/cloudflared` (the local CLI pin in `.mise.toml`).
    The snapshot lists them in ascending order, so #215 overwrote #214 and the
    operator-facing lane table named the wrong artifact for a change to an
    internet-facing tunnel. Worse, had #215 merged first the component key
    would have read as COVERED while helmrelease.yaml stayed on the old tag —
    a false negative in the crack detector, whose zero is only a safety
    property if this mapping is sound.

    Attribution is `renovate_pr_for()`, and it matches on the ARTIFACT.
    """
    prs: dict = {}
    txt = VERSION_MD.read_text() if VERSION_MD.exists() else ""
    for line in txt.splitlines():
        m = _PR_LINE.search(line)
        if not m:
            continue
        rec = _pr_record(m.group(1), m.group(2).strip())
        base = rec["path"].split("/")[-1].lower()
        for k in {rec["dep"].lower(), rec["path"].lower(), base,
                  normalize_name(base)}:
            if k:
                prs.setdefault(k, []).append(rec)
    return prs


def _as_pr_records(value) -> list:
    """Normalise a `prs` entry to records. A bare number is a LEGACY entry
    (hand-built fixtures, and any caller predating the dict-of-lists shape);
    it carries no dep, so it can only ever be matched by name."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [{"number": str(value), "dep": None, "manager": None,
             "path": None, "legacy": True}]


def renovate_pr_for(prs, item, keys=None):
    """(pr_number | None, note) — the open Renovate PR covering THIS artifact.

    Name agreement is necessary but NOT sufficient: a PR claims an IMAGE item
    only when its dep names one of that item's image repositories, and a dep
    carrying a non-image manager prefix (`aqua:`, `npm:`) never claims an image
    at all. That is what separates #214 (the container) from #215 (the CLI
    pin), and it is also why `aqua:siderolabs/talos` can no longer be read as
    coverage for the Talos NODE image (the F-9a58f400 shape).

    When two PRs survive, the ambiguity is RETURNED, never resolved by picking
    one: the caller then judges the item on its own merits, which is strictly
    safer than naming the wrong artifact as its coverage.
    """
    if not prs:
        return None, ""
    comp = str(item.get("component", "")).lower()
    lookup = {comp, normalize_name(comp)} | {str(k).lower() for k in (keys or ())}
    lookup = {k for k in lookup if k}
    seen, cands, legacy = set(), [], []
    for k in lookup:
        for rec in _as_pr_records(prs.get(k)):
            ident = (rec["number"], rec.get("dep"))
            if ident in seen:
                continue
            seen.add(ident)
            (legacy if rec.get("legacy") else cands).append(rec)
    if not cands and legacy:
        return legacy[0]["number"], ""
    repos = [str(r).lower() for r in _item_repos(item)]
    kept = []
    for rec in cands:
        path = (rec.get("path") or "").lower()
        if item.get("kind") == "image":
            if rec.get("manager") in _NON_IMAGE_MANAGERS:
                continue
            if not repos:
                # An image PR cannot be attributed to an item whose image we
                # could not resolve. Unattributable is not covered.
                continue
            if not any(r == path or r.endswith("/" + path) or path.endswith("/" + r)
                       for r in repos):
                continue
        else:
            if rec.get("manager") in _NON_IMAGE_MANAGERS - {"helm"}:
                continue
            if normalize_name(path.split("/")[-1]) not in {normalize_name(x) for x in lookup}:
                continue
        kept.append(rec)
    nums = sorted({r["number"] for r in kept})
    if len(nums) == 1:
        return nums[0], ""
    if len(nums) > 1:
        return None, ("Renovate PR attribution AMBIGUOUS — #" + ", #".join(nums)
                      + " both name this component; judged on its own merits")
    if cands:
        others = sorted({r["number"] for r in cands})
        return None, ("open Renovate PR #" + ", #".join(others)
                      + " names a DIFFERENT artifact (" +
                      ", ".join(sorted({r["dep"] for r in cands if r.get("dep")})) + ")")
    return None, ""


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
        keys = _name_keys(comp)
        # app-template plan covers all its wrappers
        if "app-template" in str(fm.get("plan_id") or ""):
            keys.add("app-template")
        # `also_covers:` — the OTHER components this plan moves in the same
        # commit (F-d71bc523). nextcloud-34.0.4 bumps deployment/
        # nextcloud-notify-push's tag in lockstep and says so in its `touches`
        # prose, but nothing read prose, so notify-push was reported as
        # needing its own plan — which would have produced a second plan for a
        # bump an approved plan already performs, to be kept in step by hand.
        # An explicit machine-readable list is deliberate: inferring coverage
        # from prose is how a plan comes to claim work it does not do.
        also = fm.get("also_covers") or []
        if isinstance(also, str):
            also = [also]
        also_keys: set = set()
        for a in also:
            also_keys |= _name_keys(str(a))
        plans.append({
            "plan_id": str(fm.get("plan_id") or p.stem),
            "file": p.name,
            "keys": keys,
            "also_keys": also_keys,
            # a plan with no status is a live draft, not history
            "status": str(fm.get("status") or "draft").lower().strip(),
            "kind": str(fm.get("kind") or "").lower().strip(),
            "current": str(fm.get("current") or "").strip(),
            "target": str(fm.get("target") or "").strip(),
        })
    return plans


def _drift_note(item, ptgt, pv, heads):
    """The re-target hint for a drifted plan — CHANNEL-RESOLVED where possible.

    F-51fb8256: this used to be `f"plan targets {ptgt}, but {item['target']} is
    now published"` — and `item["target"]` is the newest tag in the version-check
    snapshot. For an upstream whose beta rides a BARE semver tag, the newest tag
    IS the pre-release: the snapshot said n8n 2.40.1 (beta) in the very run where
    this module's own stable_channel_version() had resolved the stable head to
    2.39.6, digest-confirmed. The hint therefore named a beta build as the
    re-target for a six-migration SQLite upgrade.

    THE HINT IS ADDITIVE AND ALWAYS SURVIVES. The raw published tag is still
    named — it is a true fact about the snapshot — and the resolved head is
    appended with its evidence when, and only when, a channel was POSITIVELY
    resolved. There is deliberately NO branch that returns None:

      * suppressing the row when the plan is already at the head was tried in
        review and is a silent zero on the ONE channel that reports plan
        staleness — measured on the live nocodb plan (target 2026.09.0 == the
        resolved head), whose row vanished entirely the moment the snapshot
        moved to the next calver month;
      * it also breaks match_plan(): a drift of None makes _plan_delivers
        return (True, None), so the early exit hands the item to a plan that
        does not deliver it, ahead of one that does.

    Returning the raw tag with no channel opinion is what the bug did; returning
    nothing is worse. So the row always renders, and only its CONFIDENCE moves.
    """
    raw = str(item["target"])
    base = f"plan targets {ptgt}, but {raw} is now published"
    rec = (heads or {}).get((str(item.get("component", "")).lower(),
                             str(item.get("kind", "")).lower()))
    head, why = (rec or (None, ""))
    hv = _ver_tuple(head) if head else None
    if not hv:
        # No oracle for this (component, kind). TRUE for every CHART by
        # construction — max_rule_fallbacks() refuses charts — so this is the
        # COMMON case, and blinding it to fix the rare one would be the trade
        # backwards.
        return (f"{base} — CHANNEL UNRESOLVED: confirm {raw} is on the stable "
                f"channel before re-targeting")
    ev = f" ({why})" if why else ""
    line = ("" if _release_line(hv) == _release_line(pv)
            else f", and on a DIFFERENT release line from this plan — re-scope, "
                 f"do not merely re-target")
    if _ver_tuple(raw) == hv:
        return f"{base}; {raw} IS the stable-channel head{ev}{line}"
    if hv <= pv:
        return (f"{base}; the plan is already at or ahead of the stable-channel "
                f"head {head}{ev}, so {raw} is NOT a confirmed re-target{line}")
    return (f"{base}; the STABLE-channel head is {head}{ev} — re-target to "
            f"{head}, not {raw}{line}")


def _plan_delivers(plan, item, heads=None, ignore_kind=False):
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
    # a chart plan never delivers an image bump (or vice versa) — UNLESS the
    # plan names this component in `also_covers`, which is precisely the
    # statement "my chart commit moves that image too" (nextcloud-34.0.4 is
    # kind: chart and moves three image tags in the same commit).
    if not ignore_kind and plan["kind"] in ("chart", "image") \
            and item["kind"] in ("chart", "image") and plan["kind"] != item["kind"]:
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
            return True, _drift_note(item, ptgt, pv, heads)
    return False, None


def match_plan(item, keys, plans, heads=None):
    """(plan, drift) for the best live plan covering `item`, else (None, None).
    A drift-free match always wins over a drifted one."""
    drifted = None
    for plan in plans:
        by_name = bool(plan["keys"] & keys)
        by_also = bool(plan.get("also_keys") and plan["also_keys"] & keys)
        if not (by_name or by_also):
            continue
        if plan["status"] in DEAD_PLAN_STATUSES:
            continue
        # A plan that DECLARES also_covers is, by that declaration, a
        # chart+image lockstep plan — so the kind guard is waived for the
        # components it names AND for its own. nextcloud-34.0.4 is `kind:
        # chart` and moves three image tags in the same commit; without this
        # its own server image could only ever be covered indirectly, by
        # happening to share a repository string with a sibling. A plan with no
        # also_covers keeps the guard exactly as before.
        covers, drift = _plan_delivers(plan, item, heads,
                                       ignore_kind=bool(plan.get("also_keys")))
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


def _oci_chart_created(url: str, chart: str, version: str, timeout: int = 20):
    """Publish timestamp for an OCI-hosted Helm chart, or None.

    F-88bf8743: `oci://` chart sources used to be treated as UNKNOWABLE age, and
    since unknown age is hold-fail-safe that made the hold PERMANENT rather than
    a wait — kube-prometheus-stack could never elapse its cooldown no matter how
    old the release got. It is knowable: `helm push` stamps the standard OCI
    annotation `org.opencontainers.image.created` on the chart manifest, which is
    the chart analogue of the image path _oci_created() already uses.

    Measured on ghcr.io/prometheus-community/charts/kube-prometheus-stack:
      90.0.0 -> 2026-09-06T22:41:00Z    90.2.0 -> 2026-09-12T23:55:57Z

    Returns None on ANY failure (unsupported registry, auth, missing annotation),
    which preserves the pre-existing fail-safe hold. This widens what we can
    verify; it never widens what we let through.
    """
    import urllib.request, urllib.parse, datetime
    try:
        rest = str(url)[len("oci://"):].strip("/")
        host, _, ns = rest.partition("/")
        path = f"{ns}/{chart}" if ns else str(chart)
        # docker.io splits its registry and token hosts; everything else is same-host.
        reg = "registry-1.docker.io" if host in ("docker.io", "index.docker.io") else host
        auth = "auth.docker.io" if reg == "registry-1.docker.io" else host
        svc = "registry.docker.io" if reg == "registry-1.docker.io" else host
        tok = json.loads(urllib.request.urlopen(urllib.request.Request(
            f"https://{auth}/token?scope=repository:{path}:pull&service={svc}",
            headers={"User-Agent": "cberg-coverage"}), timeout=timeout).read())
        bearer = tok.get("token") or tok.get("access_token")
        if not bearer:
            return None
        man = json.loads(urllib.request.urlopen(urllib.request.Request(
            f"https://{reg}/v2/{path}/manifests/{urllib.parse.quote(str(version))}",
            headers={"Authorization": f"Bearer {bearer}",
                     "Accept": ",".join([
                         "application/vnd.oci.image.manifest.v1+json",
                         "application/vnd.oci.image.index.v1+json",
                         "application/vnd.docker.distribution.manifest.v2+json"])}),
            timeout=timeout).read())
        created = (man.get("annotations") or {}).get("org.opencontainers.image.created")
        if not created:
            return None
        dt = datetime.datetime.fromisoformat(str(created).replace("Z", "+00:00"))
        return (datetime.datetime.now(datetime.timezone.utc) - dt).total_seconds() / 3600.0
    except Exception:
        return None


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
    # oci:// has no index.yaml, but the chart MANIFEST carries
    # org.opencontainers.image.created (F-88bf8743) -- resolve it there instead
    # of declaring the age unknowable and holding forever.
    if chart and url and str(url).startswith("oci://"):
        age = _oci_chart_created(url, chart, item["target"])
        _CHART_AGE_CACHE[key] = age
        return age
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


def _active_age_waivers(policy):
    """The `age_waive` globs in force RIGHT NOW — expiry-aware (F-7eaae066).

    Delegates to auto-update.py's `age_waivers()` so the PR lane and this
    direct-bump lane can never disagree about whether a waiver has lapsed
    (plain string = permanent; `{match, until}` = lapses after `until`).
    FAIL-CLOSED: if that module cannot be loaded, NO waiver is in force and the
    cooldown holds — a waiver is a relaxation, and a relaxation that cannot be
    read must not relax.
    """
    try:
        return list(_auto_update_module().age_waivers(policy or {})[0])
    except Exception:
        return []


def direct_bump_age_gate(item, policy):
    """None = may auto-apply; else a reason string that HOLDS it."""
    min_age = (policy or {}).get("minimum_release_age_hours") or 0
    if not min_age:
        return None
    dep = (item.get("component") or "").lower()
    repos = item.get("image_repos") or ([item["image_repo"]] if item.get("image_repo") else [])
    for pat in _active_age_waivers(policy):
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
    #
    # And when SEVERAL repos carry the target tag, the YOUNGEST decides — never
    # the first that resolves (F-9b77a91a, 2026-09-15): memgraph indexes both
    # memgraph/lab and memgraph/memgraph-mage, both carried 3.13.1, lab's was
    # 3.5 days old and mage's 13 h. The alphabetical "echoes the component"
    # sort tried lab first, it resolved, and the loop stopped — so the mage
    # bump was rated AUTO inside the cooldown and only a manual ground-truth
    # check in the window held it. Whichever carrier is youngest is the one
    # whose artifact the window would actually pull, so it bounds the risk.
    ordered = sorted(repos, key=lambda r: (dep.split("-")[0] not in (r or "").lower(), r))
    ages = {}
    for r in ordered:
        a = image_publish_age_hours(r, item["target"])
        if a is not None:
            ages[r] = a
    if not ages:
        return (f"release age UNKNOWN for {item['target']} across {len(ordered)} "
                f"candidate repo(s) (last tried {ordered[-1]}) — cannot prove the "
                f"{min_age:g}h cooldown elapsed; holding (fail-safe)")
    youngest_repo, age = min(ages.items(), key=lambda kv: kv[1])
    if age < min_age:
        carrier = (f" [{youngest_repo}, youngest of {len(ages)} repos carrying the tag]"
                   if len(ages) > 1 else "")
        return (f"published {age:.0f}h ago (< {min_age:g}h cooldown) — eligible in "
                f"{min_age - age:.0f}h{carrier}")
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
_AU_MOD = None


def _auto_update_module():
    """runbooks/auto-update.py as a module, loaded once per process.

    Cached because it used to be exec'd afresh on every G3 cache miss, and
    because the RANGE walk below needs the same release-list cache the PR lane
    fills — two lanes disagreeing about which releases exist would be the same
    class of defect as them disagreeing about what "breaking" means.
    """
    global _AU_MOD
    if _AU_MOD is None:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "cberg_auto_update", SCRIPT_DIR / "auto-update.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore
        _AU_MOD = mod
    return _AU_MOD


def _hop_skips_releases(cur, tgt) -> bool:
    """True when `tgt` is provably NOT the immediate successor of `cur`.

    Adjacent means: same major+minor (and same trailing build fields) with the
    patch advancing by exactly one. Everything else LEAPFROGS at least one
    version that upstream may have published — which is the precondition for
    the G3 range walk. Unparseable => False: a skip must be PROVEN, never
    assumed, or the gate would hold every tag it cannot read.
    """
    a, b = _version_components(cur), _version_components(tgt)
    if not a or not b:
        return False
    a, b = _padded(a, b)
    if b <= a:
        return False
    return not (a[:2] == b[:2] and b[2] == a[2] + 1 and a[3:] == b[3:])


def _crosses_minor(cur, tgt) -> bool:
    """True when the hop leaves the current MINOR line (or the major)."""
    a, b = _version_components(cur), _version_components(tgt)
    if not a or not b:
        return False
    a, b = _padded(a, b)
    return a[0] != b[0] or a[1] != b[1]


def _release_tags_between(dep, cur, tgt):
    """(tags_leapfrogged, note) for `dep`, or (None, why) when unknowable."""
    try:
        return _auto_update_module().release_tags_between(
            _load_checker(), dep, cur, tgt)
    except Exception as e:
        return None, f"release list unreadable ({type(e).__name__})"


_CHECKER = None


def _load_checker():
    global _CHECKER
    if _CHECKER is None:
        _CHECKER = _auto_update_module()._load_version_checker()
    return _CHECKER


def _g3_range_gate(item):
    """(status, note) — G3 over the release RANGE current..target.

    status is one of:
      n/a        — the hop is adjacent (or unparseable): nothing is skipped
      clean      — every leapfrogged release was read and none is breaking
      breaking   — a leapfrogged release announces a breaking change
      unreadable — releases WERE skipped and could not be read

    WHY (F-51728488). `breaking_signal()` fetches notes for the single TARGET
    tag, and nothing walked the range, so a breaking change announced in a
    release we leapfrog was never evaluated — the gate read as a
    breaking-change check while being a breaking-change check for exactly one
    version. Live: scan-inbox-validator 3.1.3 -> 3.2.0 was rated PLAN with
    reason "G3 breaking-change signal — update ng-select to v24, handle
    breaking changes"; hours later the target moved to 3.2.1 and the SAME
    component was rated AUTO, because 3.2.0 was no longer the tag whose notes
    are read. The breaking change did not go away; the reader moved past it.

    `unreadable` HOLDS only when the hop crosses a MINOR boundary. That is the
    deliberate line: within a patch line the pre-existing G3-unknown asymmetry
    still applies (an unauthenticated GitHub rate limit must not close the
    lane), but a minor hop always leapfrogs at least `X.Y.0`, so an unread
    range there is an unevaluated gate, not a missing nicety.
    """
    cur, tgt = item.get("current"), item.get("target")
    if not _hop_skips_releases(cur, tgt):
        return "n/a", ""
    dep, holdable = None, False
    if item.get("kind") == "image":
        repos = _item_repos(item)
        if repos:
            base = (item.get("component") or "").lower().split("-")[0]
            dep = sorted(repos, key=lambda r: (base not in (r or "").lower(), r))[0]
            # Only an item with a RESOLVED artifact can be held for an unread
            # range. An image whose repository the snapshot does not carry is
            # already held fail-safe one gate earlier, by G5
            # (direct_bump_age_gate: "image repository unresolved … holding"),
            # and charts have no registry artifact to read at all — so turning
            # "no source" into a hold HERE would both duplicate that gate and
            # widen this one far past the defect it closes, holding every
            # chart minor that upstream does not publish to GitHub.
            holdable = True
    elif item.get("kind") == "chart":
        dep = item.get("component")
    if not dep:
        return "n/a", ""
    between, why = _release_tags_between(dep, cur, tgt)
    if between is None:
        return (("unreadable", f"{why} for {dep}")
                if holdable and _crosses_minor(cur, tgt) else ("n/a", why))
    if not between:
        # Nothing was leapfrogged: the target-tag read already covered the hop,
        # and saying so in the AUTO reason would imply a gate that did work.
        return "n/a", ""
    for tag in between:
        is_breaking, note = breaking_change_signal(dep, tag)
        if is_breaking:
            return "breaking", (f"release {tag} is SKIPPED by this hop "
                                f"({cur} → {tgt}) and {note}")
    return "clean", f"{len(between)} skipped release(s) read and clean"


# ── Pre-release targets that carry NO pre-release marker ────────────────────
# F-aff597aa, and it CAME TRUE: the AUTO lane admitted penpot-cache valkey
# 9.1.2 -> 9.2 and an unattended Step 0 shipped it. Measured (re-verified
# 2026-09-21): `9.2` and `9.2.0-rc1` are the SAME digest
# (sha256:b0eef48f…, pushed 1.7s apart), 9.2.0 and 9.2.1 both 404 — there is no
# GA 9.2.x at all. So a RELEASE CANDIDATE is running in production, and a
# pinned 3-component tag was replaced by a FLOATING 2-component one, which a
# future reconcile can move again with no commit and no review.
#
# Two independent detectors, because each covers the other's blind spot:
#   1. ARITY (offline, decidable in the window agent with no DSN and no
#      network): the target names FEWER version components than the current
#      pin, on the SAME major. That is a series pointer replacing a fixed pin,
#      whatever it resolves to today. Scoped to the same major deliberately —
#      a cross-major hop is already a PLAN item by type, and widening it would
#      hold ordinary suffixed tags such as `13.6-bookworm`.
#   2. DIGEST TWIN (Docker Hub, best-effort, ADDITIVE): the target tag is
#      byte-identical to a sibling -rc/-beta/-alpha tag. This catches the case
#      arity cannot — a 3-component GA-looking tag that is really the RC.
# A per-component deny rule would only paper over this one instance.
_TWIN_CACHE: dict = {}


def _dockerhub_tag_digests(repo: str, timeout: int = 12):
    """{tag: digest} for one page of a Docker Hub repo's tags, or None."""
    import urllib.request
    if repo in _TWIN_CACHE:
        return _TWIN_CACHE[repo]
    _TWIN_CACHE[repo] = None
    ref = str(repo).strip()
    if ref.startswith("docker.io/"):
        ref = ref[len("docker.io/"):]
    host = ref.split("/")[0]
    if "." in host or ":" in host:
        return None                      # not Docker Hub — no oracle here
    path = ref if "/" in ref else "library/" + ref
    try:
        req = urllib.request.Request(
            f"https://hub.docker.com/v2/repositories/{path}/tags/"
            f"?page_size=100&ordering=last_updated", headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read())
    except Exception:
        return None
    out = {str(row.get("name") or ""): row.get("digest")
           for row in (data.get("results") or []) if row.get("digest")}
    _TWIN_CACHE[repo] = out
    return out


def _prerelease_digest_twin(repo: str, tag: str):
    """(twin_tag, evidence) when `tag` IS a pre-release under another name."""
    tags = _dockerhub_tag_digests(repo)
    if not tags:
        return None, ""
    digest = tags.get(str(tag))
    if not digest:
        return None, ""
    for name, dg in tags.items():
        if dg == digest and name != tag and _PRERELEASE_TAG.search(name):
            return name, (f"{repo}:{tag} and {repo}:{name} are the same image "
                          f"({str(digest)[:19]}…)")
    return None, ""


def prerelease_target_hold(item):
    """Reason why the TARGET is a pre-release/floating pin in disguise, else None."""
    cur, tgt = str(item.get("current") or ""), str(item.get("target") or "")
    a, b = _version_components(cur), _version_components(tgt)
    if a and b and len(b) < len(a) and a[0] == b[0]:
        return (f"target {tgt} names FEWER version components than the pinned "
                f"{cur} on the same major line — a floating series pointer, not "
                f"a fixed version: it cannot be shown to be GA (valkey `9.2` was "
                f"digest-identical to `9.2.0-rc1` with no GA 9.2.x published), "
                f"and once applied a reconcile can move the artifact again with "
                f"no commit. Needs an assessed window plan")
    if item.get("kind") == "image":
        for repo in _item_repos(item):
            twin, ev = _prerelease_digest_twin(repo, tgt)
            if twin:
                return (f"target {tgt} is byte-identical to the PRE-RELEASE tag "
                        f"{twin} — {ev}. A release candidate wearing a GA-looking "
                        f"tag is still a release candidate; never unattended")
    return None


def _with_channel_measurement(reason, item, heads):
    """Append THIS RUN's channel measurement to a policy-prose hold reason.

    F-5224f230: one run emitted two contradictory verdicts for n8n — the
    max-rule fallback reported "stable channel head 2.39.5, digest-confirmed"
    while the PLAN-lane reason (the deny rule's prose) asserted 2.39.x IS the
    beta/next line. The prose is a STATIC assertion about the component that
    does not re-measure when upstream promotes a line, and a planner briefed
    from the wrong half plans a pre-release bump into production. The rule text
    still governs the lane — only the operator is now told what the same run
    actually measured, so the two halves can no longer be read as two facts.
    """
    rec = (heads or {}).get((str(item.get("component", "")).lower(),
                             str(item.get("kind", "")).lower()))
    if not rec:
        return reason
    head, why = rec[0], rec[1]
    hv, tv = _ver_tuple(head), _ver_tuple(item.get("target"))
    rel = ""
    if hv and tv:
        rel = (f"; the target {item.get('target')} is "
               + ("AT that head" if tv == hv else
                  "AHEAD of it" if tv > hv else "BEHIND it"))
    return (f"{reason} [MEASURED THIS RUN: upstream's stable-channel head is "
            f"{head} ({why}){rel} — the hold reason above is policy prose, not "
            f"a measurement]")


def breaking_change_signal(image_repo: str, tag: str):
    """(is_breaking, note) — G3 for a candidate that has no Renovate PR.

    Reuses auto-update.py's engine so the two lanes agree on what "breaking"
    means — including WHERE the notes are read from: the engine resolves the
    image repo through check-all-versions.py's `get_release_notes_project()`,
    i.e. the git-tracked IMAGE_RELEASE_NOTES_PROJECTS map first, then the
    registry-path derivation (F-d6f1b7c7: `memgraph/memgraph-mage` derives a
    GitHub project that does not exist, so this gate could never verify a
    memgraph bump and the asymmetry below waved every one through).
    Best-effort by design and it says so: a POSITIVE signal holds, an
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
        mod = _auto_update_module()
        notes, resolved = mod.breaking_signal(_load_checker(), image_repo, tag)
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
      already-enumerated
                  — the stable head is in the actionable universe in its own
                    right, so nothing is masked; reported, never appended
                    twice (F-7b04b03f: this fourth status was emitted below
                    and branched on downstream, but only the SOP documented
                    it — a caller writing an exhaustive switch off this
                    docstring would have missed it).
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
        rule = deny_rule_for_item(policy, item, key, item["type"])
        mx = (rule or {}).get("max")
        if not rule or mx not in RANK:
            continue                      # no rule, or a FULL block: nothing is allowed
        if RANK.get(item["type"], 99) <= RANK.get(mx, -1):
            continue                      # not actually blocked by the `max:`
        rec = {"component": item["component"], "kind": item["kind"],
               "current": item["current"], "blocked_target": item["target"],
               "blocked_type": item["type"], "deny_match": rule.get("match"),
               "deny_max": mx,
               "blocked_pr": renovate_pr_for(prs, item, {comp, key})[0]}
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
                        # The head must survive as DATA, not only inside the
                        # prose reason. Without this, channel_resolved_heads()
                        # has nothing to read on an up-to-date record and the
                        # obvious fallback — `current`, the DEPLOYED tag — would
                        # publish a running pre-release as "the stable head",
                        # stapled to evidence naming a different version.
                        "channel_head": ver, "channel_evidence": why,
                        "reason": f"stable channel head is {ver} ({why}); "
                                  f"{item['current']} is already at or ahead of it"})
            continue
        utype = _semver_type(item["current"], ver)
        blocked = denied_for_item(policy, item, key, utype)
        if blocked:
            out.append({**rec, "status": "hold", "candidate": ver,
                        "channel_evidence": why,
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
                        "channel_evidence": why,
                        "reason": f"stable channel head {ver} ({why}) is already in "
                                  f"the actionable universe on its own — no masking"})
            continue
        seen.add(k)
        is_breaking, g3 = breaking_change_signal(repo, ver)
        if is_breaking:
            out.append({**rec, "status": "hold", "candidate": ver,
                        "channel_evidence": why,
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


def up_to_date_components(fallbacks) -> set:
    """Components whose `max:`-rule fallback says the STABLE head is deployed.

    F-52e5637f (2026-09-15): n8n 2.38.7 -> 2.39.5 sat in needs_plan every
    cycle — a planner target for a beta-channel bump that policy will never
    admit — while the same run's max_rule_fallback record said `up-to-date`
    (npm dist-tag stable == the deployed tag). Two outputs of one script
    contradicted each other and the planner dispatch believed the wrong one.
    """
    return {str(r.get("component", "")).lower()
            for r in (fallbacks or []) if r.get("status") == "up-to-date"}


def channel_resolved_heads(fallbacks) -> dict:
    """{(component, kind): (stable_head, evidence)} — channels POSITIVELY resolved.

    Same records as up_to_date_components() (F-52e5637f), widened from the one
    status that answers the planner question to every record that actually
    RESOLVED a head.

    THE HEAD COMES FROM THE ORACLE, NEVER FROM WHAT WE RUN. Only `candidate`
    (the resolved head on a hold/already-enumerated/candidate record) and
    `channel_head` (the same value on an up-to-date record) are read. Falling
    back to `current` was tried in review and is how a DEPLOYED pre-release
    becomes "the STABLE-channel head": measured, a record with
    current=2.40.1 whose own evidence string names 2.39.6 published 2.40.1 as
    the head, wearing the digest-confirmed evidence for a different version.
    A record that resolved nothing is deliberately ABSENT, so a caller can tell
    "resolved" from "unknown" instead of reading a missing key as a head of None.

    Keyed on (component, KIND) on purpose: max_rule_fallbacks() reads the
    channel off an IMAGE registry and refuses charts outright, so an image head
    must never be offered as the head of the same component's CHART bump.

    A key claimed twice with DIFFERENT heads is dropped to unknown rather than
    last-write-wins: one row's head silently applied to another row's drift
    note is the same class of error as the beta this function exists to stop.
    Missing EVIDENCE never drops a head — an unattributed head is still a
    resolved one.
    """
    out, ambiguous = {}, set()
    for r in (fallbacks or []):
        comp = str(r.get("component", "")).lower()
        kind = str(r.get("kind", "")).lower()
        if not comp:
            continue
        head = r.get("candidate") or r.get("channel_head")
        if not head:
            continue
        key = (comp, kind)
        if key in ambiguous:
            continue
        if key in out and out[key][0] != str(head):
            del out[key]
            ambiguous.add(key)
            continue
        out[key] = (str(head), str(r.get("channel_evidence") or "")[:140])
    return out


def needs_plan_exempt(item, channel_current: set) -> bool:
    """True when a PLAN-lane item must NOT become a planner target because the
    stable-channel head is already what runs (see up_to_date_components)."""
    return str(item.get("component", "")).lower() in (channel_current or set())


def _direct_bump_breaking_gate(item):
    """(is_breaking, note) — G3 for a NO-PR candidate on the direct-bump path.

    WHY THIS EXISTS (F-ec4c1644, 2026-09-15). `breaking_change_signal()` was
    called from exactly one place, `max_rule_fallbacks()`, so only the
    allowed-behind-a-max-rule candidates were ever scanned for a breaking
    signal. The ordinary "safe patch/minor" exit in `assign_lane()` went
    straight to AUTO after G5 — and G5 is WAIVED for `age_waive` components —
    so mealie v3.25.1 -> v3.26.0, whose release notes open with a BREAKING
    CHANGE (server-initiated HTTP refuses private-network targets unless
    HTTP_ALLOW_LIST is set), was rated AUTO for an unattended window. It was
    caught by a human reading the notes in the window; this is that reading,
    made mechanical, with the SAME asymmetry the helper documents: a positive
    signal holds, unfetchable notes do NOT (G3-unknown is the pre-existing
    baseline of every direct bump, and an unauthenticated GitHub rate limit
    must not close the lane). auto-update.py applies G3 to PRs already, so
    the Renovate-PR shortcut above this gate is deliberately not double-gated.
    Off the network when the item names no repository.
    """
    try:
        if item.get("kind") == "image":
            dep = (item.get("component") or "").lower()
            repos = [r for r in ([item.get("image_repo")] if item.get("image_repo")
                                 else item.get("image_repos") or []) if r]
            if not repos:
                return False, "unverified (no image repository to read notes for)"
            ordered = sorted(repos, key=lambda r: (dep.split("-")[0] not in (r or "").lower(), r))
            last = (False, "unverified (release notes unavailable)")
            for r in ordered:
                is_b, note = breaking_change_signal(r, item["target"])
                if is_b:
                    return True, f"{note} [{r}]"
                if "checked" in note:
                    last = (False, note)
            return last
        if item.get("kind") == "chart":
            return breaking_change_signal(item.get("component") or "", item["target"])
        return False, "unverified (not an image or chart)"
    except Exception as e:  # never let a gate failure read as a pass CLAIM
        return False, f"unverified ({type(e).__name__})"


def assign_lane(item, policy, prs, plans, ar_holds=None, heads=None):
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
    plan, drift = match_plan(item, _name_keys(comp) | {key}, plans, heads)
    if plan:
        return "PLAN", f"plan exists: {plan['plan_id']} ({plan['status']})", (
            f"{plan['file']}: {drift}" if drift else None)
    # CHANNEL GATE — must sit ABOVE both AUTO exits (the Renovate-PR shortcut and
    # the safe patch/minor default): a pre-release target is not made safe by a
    # PR existing for it, and the window applies the AUTO lane unattended.
    ch = channel_hold(comp, item, ar_holds)
    if ch:
        return "PLAN", ch, None
    # Same position, same reason: a target that IS a pre-release under another
    # name (or a floating series pointer) must not be laundered by a PR
    # existing for it, and the window applies AUTO unattended (F-aff597aa).
    pre = prerelease_target_hold(item)
    if pre:
        return "PLAN", pre, None
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
    pr_num, pr_note = renovate_pr_for(prs, item, {comp, key})
    if not item.get("max_rule_fallback") and pr_num:
        return "AUTO", f"Renovate PR #{pr_num}", None
    dn = denied_for_item(policy, item, key, utype)
    if dn or utype == "major" or utype == "unknown":
        return "PLAN", _with_channel_measurement(
            dn or f"{utype} — needs an assessed window plan", item, heads), None
    if utype in ("patch", "minor"):
        # G5 cooldown applies to the DIRECT-BUMP lane too (F-0bd870a4). The
        # Renovate-PR exit above is deliberately NOT gated here: auto-update.py
        # already applies G5 to PRs, and double-gating would hold them twice.
        cooldown = direct_bump_age_gate(item, policy)
        if cooldown:
            return "HELD", f"G5 release-age cooldown — {cooldown}", None
        # G3 on the direct-bump path too (F-ec4c1644): a positive breaking-change
        # signal in the target's release notes is a PLAN item, whatever the
        # semver label says. Unfetchable notes do not hold (see the helper).
        is_breaking, g3 = _direct_bump_breaking_gate(item)
        if is_breaking:
            return "PLAN", f"G3 breaking-change signal — {g3}", None
        # G3 over the RANGE, not the target alone (F-51728488): a breaking
        # change announced in a release this hop LEAPFROGS is exactly as
        # breaking as one in the target, and the target-only read made the
        # defect invisible whenever upstream published one more patch.
        rstatus, rnote = _g3_range_gate(item)
        if rstatus == "breaking":
            return "PLAN", f"G3 breaking-change signal in a SKIPPED release — {rnote}", None
        if rstatus == "unreadable":
            return "PLAN", (f"G3 range UNEVALUATED across a minor boundary — {rnote}. "
                            f"The hop leapfrogs at least one release whose notes were "
                            f"not read; needs an assessed window plan"), None
        g3_note = "" if "checked" in g3 else f"; G3 {g3}"
        if rstatus == "clean" and rnote:
            g3_note += f"; G3 range: {rnote}"
        if pr_note:
            g3_note += f"; {pr_note}"
        return "AUTO", f"safe patch/minor — window applies (hybrid: PR or direct-bump){g3_note}", None
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


# The SOPS metadata trailer: a top-level `sops:` key followed by its indented
# block, written at the END of every encrypted file.
_SOPS_TRAILER = re.compile(r"(?ms)^sops:[ \t]*\n(?:(?:[ \t]+[^\n]*)?\n)*")


def _strip_sops_trailer(text: str) -> str:
    """Drop the `sops:` metadata block before version matching.

    F-a52c69d7. `already_applied()` proves a bump landed with a NAMESPACE-WIDE
    substring test — target present AND current absent — and the SOPS trailer
    carries `version: <sops binary version>`, a version-shaped string that has
    nothing to do with any workload. Measured 2026-09-17: memgraph was bumped
    3.13.0 -> 3.13.1 in git, but `3.13.0` still appeared in TWO unrelated
    `secret.sops.yaml` trailers in the same namespace (the local sops binary
    was 3.13.0), so `cur not in txt` was False, the bump never self-cleared,
    and counts.AUTO reported 2 where the true actionable AUTO was 1 — a number
    the maintenance-window agent reads at Step 0.

    The trailer is STABLE (it moves only when the sops binary moves), so any
    component whose CURRENT version happens to equal the sops version is stuck
    in AUTO indefinitely. `_strip_yaml_comments` already handles the
    changelog-comment source of stale version strings; this is the second one.
    Three files in `kubernetes/apps/databases/` carry `version: 3.13.0` today.
    """
    return _SOPS_TRAILER.sub("", text)


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
                parts.append(_strip_sops_trailer(
                    _strip_yaml_comments(f.read_text(errors="ignore"))))
            except OSError:
                pass
        txt = "\n".join(parts)
    _NS_TEXT_CACHE[ns] = txt
    return txt


def _norm_repo(repo) -> str:
    """Registry-qualified spellings of one image reduced to a comparable key.

    The snapshot writes `docker.io/jellyfin/jellyfin` and `library/postgres`
    where the manifests write `jellyfin/jellyfin` and `postgres`. Measured
    2026-09-21: without this, 2 of the 13 single-repo rows fail to reconcile and
    the scoped branch below silently never engages — a fix that reads as correct
    and does nothing.
    """
    r = str(repo or "").strip().lower()
    for p in ("docker.io/", "index.docker.io/"):
        if r.startswith(p):
            r = r[len(p):]
    if r.startswith("library/"):
        r = r[len("library/"):]
    return r


def _namespace_repo_tags(ns: str) -> dict:
    """{normalised image repo -> {tags pinned in git}} under kubernetes/apps/<ns>/.

    Cached inside `_NS_TEXT_CACHE` under a TUPLE key on purpose. Both test
    suites clear that dict between fixtures (11 call sites); a second cache of
    its own would keep serving the PREVIOUS fixture's tree while every
    `.clear()` still looked correct — a stale read dressed as a passing test.
    Tuple keys cannot collide with the plain-string keys `_namespace_text` uses.
    """
    key = ("repos", ns)
    if key in _NS_TEXT_CACHE:
        return _NS_TEXT_CACHE[key]
    out: dict = {}

    def add(repo, tag):
        # `1.38.0@sha256:...` is the same deployed version as the bare tag the
        # report carries, so the digest must not defeat the comparison.
        t = str(tag).split("@")[0].strip()
        if repo and t:
            out.setdefault(_norm_repo(repo), set()).add(t)

    def walk(node):
        if isinstance(node, dict):
            if isinstance(node.get("repository"), str) and node.get("tag") is not None:
                add(node["repository"], node["tag"])
            for k, v in node.items():
                if k == "image" and isinstance(v, str) and ":" in v:
                    repo, _, tag = v.rpartition(":")
                    if repo and "/" not in tag:   # not a registry:port hostname
                        add(repo, tag)
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    d = REPO_ROOT / "kubernetes" / "apps" / ns
    if d.is_dir():
        for f in sorted(d.rglob("*.yaml")):
            try:
                docs = list(yaml.safe_load_all(f.read_text(errors="ignore")))
            except Exception:
                continue      # Authentik blueprints carry tags safe_load rejects
            for doc in docs:
                walk(doc)
    _NS_TEXT_CACHE[key] = out
    return out


def already_applied(item) -> bool:
    """True only when the bump is PROVABLY in git already.

    Deliberately conservative in one direction. A false "already applied"
    silently drops a real update — the exact CRACK this file exists to prevent —
    so the test demands BOTH that the target version is present AND that the
    current one is gone. Anything unprovable keeps the item, which costs a
    redundant no-op and nothing else.

    SCOPED TO THE ITEM'S OWN IMAGE when exactly one repository resolves
    (F-a52c69d7, the second disjunct). The namespace-wide text answers "does
    this version string appear anywhere under kubernetes/apps/<ns>/", and a
    SECOND IMAGE legitimately still pinning the old version answers that
    wrongly: memgraph moved `memgraph/lab` 3.13.1 -> 3.13.2 while
    `memgraph/memgraph-mage` deliberately stayed at 3.13.1 ("lab controller
    only, mage unchanged"), so the landed bump never self-cleared and the AUTO
    lane kept re-proposing it — an unattended bump that risked dragging mage
    along. 12 of 18 namespaces carry that shape (>1 repo, >1 distinct tag), so
    it re-arms whenever a snapshot goes stale mid-window, which is the exact
    condition this function exists for.

    The scoped branch is a REFINEMENT, not a loosening: it asks whether THIS
    image is pinned at the target and not at the current, which is the real
    question. It engages only when exactly one repo resolves AND that repo is
    actually found in git; multi-image rows (nextcloud pins three) and
    unresolvable repos fall through to the namespace-wide test rather than
    assume. Measured across all 22 live rows on 2026-09-21: zero behaviour
    change today — the memgraph instance had already self-resolved, so this is
    preventive, not corrective.
    """
    cur, tgt = item.get("current"), item.get("target")
    ns = (item.get("namespace") or "").strip()
    if not ns or not cur or not tgt:
        return False
    if _is_truncated(cur) or _is_truncated(tgt):
        return False          # a clipped tag cannot be matched literally
    repos = _item_repos(item)
    if item.get("kind") == "image" and len(repos) == 1:
        tags = _namespace_repo_tags(ns).get(_norm_repo(repos[0]))
        if tags:
            return (str(tgt) in tags) and (str(cur) not in tags)
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
    repo_holders = {}
    for lane in ("PLAN", "HELD"):
        for e in lanes[lane]:
            holders.setdefault(str(e.get("component", "")).lower(), []).append((lane, e))
            # …and by the IMAGE ARTIFACT itself (F-dc4066f9). scan-inbox-validator
            # runs ghcr.io/paperless-ngx/paperless-ngx — the SAME image as the
            # main paperless-ngx workload — but it is a bare Deployment, so it
            # is scored as its own component and landed in AUTO while the other
            # half of one ingestion pipeline was deliberately PLAN-held, on the
            # same image. Applying the AUTO half alone splits the version across
            # the pipeline. The lane rules were right; the component IDENTITY
            # was wrong, and it recurs for any sidecar/helper Deployment sharing
            # an image with a workload tracked under a different name.
            if e.get("kind") == "image":
                for r in _item_repos(e):
                    repo_holders.setdefault(
                        (str(r).lower(), _dedupe_tag(e.get("target"))), []).append((lane, e))
    moved = []
    for e in list(lanes["AUTO"]):
        comp = str(e.get("component", "")).lower()
        cands = list(holders.get(comp) or ())
        if e.get("kind") == "image":
            # Keyed on (repo, TARGET tag): the same artifact moving to the same
            # tag. Requiring the target too keeps this to the genuine shared-
            # image case instead of coupling every component that happens to
            # mount a common base image.
            for r in _item_repos(e):
                for lane_e in repo_holders.get((str(r).lower(), _dedupe_tag(e.get("target"))), []):
                    if lane_e[1] is not e and lane_e not in cands:
                        cands.append(lane_e)
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
        hcomp = str(he.get("component", "")).lower()
        shared = sorted(set(str(r).lower() for r in _item_repos(e))
                        & set(str(r).lower() for r in _item_repos(he)))
        e["lane"] = "PLAN"
        e["lockstep_with"] = f"{he['kind']} {he['current']}→{he['target']} [{hlane}]"
        if hcomp != comp and shared:
            e["lockstep_image"] = shared[0]
            e["reason"] = (f"lockstep — {hcomp} is {hlane} on the SAME image "
                           f"{shared[0]} at the same target ({str(he.get('reason', ''))[:60]}); "
                           f"applying this half alone splits one deployable unit "
                           f"across two versions")
        else:
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


def _prune_needs_plan_shared_image(lanes, needs_plan):
    """Drop a planner target that ANOTHER component's plan already delivers.

    The other half of F-dc4066f9. Once the shared-image lockstep above pulls
    the sidecar back to PLAN, the sidecar becomes a PLAN-lane item with no plan
    of its own — i.e. a needs_plan entry — and rule 4d would dispatch a SECOND
    upgrade-planner for the very bump the first plan performs, leaving two
    plans to be kept in step by hand. Same shape as F-d71bc523, reached from
    the other direction.

    Keyed on (image repository, TARGET tag), so it only ever suppresses a
    planner for the identical artifact moving to the identical version.
    """
    covered = {}
    for e in lanes["PLAN"]:
        if e.get("kind") != "image":
            continue
        if not str(e.get("reason", "")).startswith("plan exists"):
            continue
        for r in _item_repos(e):
            covered[(str(r).lower(), _dedupe_tag(e.get("target")))] = e
    dropped = []
    for e in list(needs_plan):
        if e.get("kind") != "image":
            continue
        for r in _item_repos(e):
            owner = covered.get((str(r).lower(), _dedupe_tag(e.get("target"))))
            if owner is None or owner is e:
                continue
            e["covered_by_sibling"] = f"{owner.get('component')}: {owner.get('reason')}"
            e["reason"] += (f" — but {owner.get('component')} already has a plan for the "
                            f"SAME image {r} at {e.get('target')}; no second planner")
            needs_plan.remove(e)
            dropped.append(e)
            break
    return dropped


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
    ar_rows = accepted_risk_rows()

    lanes = {"AUTO": [], "PLAN": [], "REBUILD": [], "HELD": [], "CRACK": []}
    needs_plan = []  # PLAN-lane items with NO plan file yet → sweep must dispatch a planner
    plan_drift = []  # live plans whose target has fallen behind upstream
    seen_app_template = False
    channel_current = up_to_date_components(fallbacks)
    channel_heads = channel_resolved_heads(fallbacks)
    for it in actionable:
        lane, reason, drift = assign_lane(it, policy, prs, plans, ar_holds,
                                          channel_heads)
        # dedupe the ~40 app-template rows into one PLAN item
        if it["kind"] == "chart" and it["target"].startswith("5."):
            if seen_app_template:
                continue
            seen_app_template = True
            it = {**it, "component": "app-template (≈all app-template wrappers)"}
        entry = {**it, "lane": lane, "reason": reason}
        if drift:
            entry["drift"] = drift
            # Also as DATA, for readers that consume the record rather than the
            # sentence: `target` is the snapshot's newest tag by definition, so
            # without this a structured reader still sees only the beta.
            _h = channel_heads.get((str(it.get("component", "")).lower(),
                                    str(it.get("kind", "")).lower()))
            if _h:
                entry["channel_head"] = _h[0]
            plan_drift.append(entry)
        if lane == "PLAN" and not reason.startswith("plan exists"):
            if needs_plan_exempt(it, channel_current):
                # The blocked target IS the pre-release line the `max:` rule
                # exists to hold, and the stable head is already deployed —
                # there is nothing to plan (F-52e5637f). Stays in PLAN so the
                # lane counts are honest; just never a planner target.
                entry["reason"] += (" — stable channel head already deployed (see "
                                    "max_rule_fallback); no plan needed")
            elif ar_accepts_item(it, ar_rows):
                # An ENABLED accepted risk already disposes of this item
                # (F-a95ba973). Lane unchanged — only the planner dispatch.
                _ar = ar_accepts_item(it, ar_rows)
                entry["accepted_risk"] = _ar
                entry["reason"] += (f" — accepted risk {_ar} already disposes of this "
                                    f"item; no plan needed")
            elif plan_declines(it, plans):
                _pl = plan_declines(it, plans)
                entry["declined_by"] = _pl
                entry["reason"] += (f" — plan {_pl} explicitly DECLINES this bump; that "
                                    f"is a recorded decision, not pending work; no plan "
                                    f"needed")
            else:
                needs_plan.append(entry)
        lanes[lane].append(entry)

    lockstep = _apply_lockstep(lanes, needs_plan)
    _prune_needs_plan_shared_image(lanes, needs_plan)

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
