"""Shared plan↔held-update matching.

Exists because two tools matched the same pair with different, both-broken
keys. `maintenance-plan.py` looked up plans by PR number and then by the held
dep's IMAGE BASENAME; the talos plan carries `pr: null` (the upgrade is a CR
operation, the Renovate PR is deliberately not merged) and `component:
"Talos Linux"`, while the held dep is `ghcr.io/siderolabs/installer` → key
`installer`. Both lookups missed, so an approved, windowed plan was reported
"NEEDS A PLAN" on every sweep and rule 4d dispatched a redundant planner every
cycle. The plan file's own frontmatter comment ("component MUST equal the
version-check's component") documented a contract the code never enforced.

Three key families, matched in order:

1. PR number — `pr208`. Authoritative when both sides carry it.
2. Names — normalized component, plan_id, dep basename, dep owner.
   `"Talos Linux"` → `talos-linux`. Catches ordinary same-name cases.
3. Version pair — the held update's `cur` AND `new` version tokens both appear
   in the plan's `current`/`target` prose. This is the bridge for the talos
   class, where NO name key can work: nothing relates "Talos Linux" to
   "installer" except the versions themselves. Requiring BOTH ends of the bump
   (not just the target) keeps coincidental matches rare; ambiguity is
   surfaced to the caller rather than silently resolved.
"""

from __future__ import annotations

import re

_VER = re.compile(r"\bv?(\d+\.\d+(?:\.\d+)?(?:\.\d+)?)\b")


def normalize_name(s) -> str:
    """Lowercase; every run of non-alphanumerics becomes one dash."""
    return re.sub(r"[^a-z0-9]+", "-", str(s or "").lower()).strip("-")


def _ver_tokens(s) -> set[str]:
    """All version tokens in a string, sans leading v: {'1.13.9', ...}."""
    return set(_VER.findall(str(s or "")))


def plan_match_keys(plan: dict) -> set[str]:
    keys = set()
    if plan.get("pr"):
        keys.add(f"pr{plan['pr']}")
    for field in ("component", "plan_id"):
        n = normalize_name(plan.get(field))
        if n:
            keys.add(n)
    return keys


def held_match_keys(held: dict) -> set[str]:
    keys = set()
    if held.get("number"):
        keys.add(f"pr{held['number']}")
    dep = str(held.get("dep") or "")
    parts = [p for p in dep.split("/") if p]
    if parts:
        keys.add(normalize_name(parts[-1]))                  # image basename
    if len(parts) >= 2:
        keys.add(normalize_name("/".join(parts[-2:])))       # owner/name
    return keys


def version_pair_match(plan: dict, held: dict) -> bool:
    """Both ends of the held bump appear in the plan's current/target prose."""
    cur = _ver_tokens(held.get("cur"))
    new = _ver_tokens(held.get("new"))
    if not cur or not new:
        return False
    return bool(cur & _ver_tokens(plan.get("current"))) and \
        bool(new & _ver_tokens(plan.get("target")))


def match_held_to_plan(held: dict, plans: list[dict]) -> tuple[dict | None, list[dict]]:
    """(best_plan_or_None, ambiguous_others).

    Key-intersection matches (PR / name) outrank version-pair matches. If more
    than one plan survives at the winning tier, the first is returned and the
    rest come back as `ambiguous` — the caller must WARN, never silently pick.
    """
    hk = held_match_keys(held)
    by_key = [p for p in plans if plan_match_keys(p) & hk]
    if by_key:
        return by_key[0], by_key[1:]
    by_ver = [p for p in plans if version_pair_match(p, held)]
    if by_ver:
        return by_ver[0], by_ver[1:]
    return None, []


def target_covers(plan: dict, held: dict) -> bool:
    """Does the plan's target still name the held update's NEW version?

    The staleness test, split from version_pair_match deliberately: staleness
    is about the TARGET end only. Requiring the cur-side too would mark any
    plan with a prose-only `current` field permanently stale.
    """
    new = _ver_tokens(held.get("new"))
    return bool(new) and bool(new & _ver_tokens(plan.get("target")))
