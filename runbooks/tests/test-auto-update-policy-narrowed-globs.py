"""Regression test: the `*affine*` and `*n8n*` deny globs are narrowed to the
application IMAGE, and the `*authentik*` reason states the mechanism the right
way round (policy 2026.09.26.1).

Planner findings, 2026-09-25/26:
  * `*affine*` matched every sibling whose NAME contains "affine" and diverted
    two consecutive plain redis patches of `affine-redis` into window plans
    with the AFFiNE app's env->config.json reason. Now `*toeverything/affine*`.
  * `*n8n*` held the 8gears n8n Helm CHART under the image's beta-channel
    reason; the chart has no beta channel. Now `*n8nio/n8n*`.
  * `*authentik*` said a chart-only bump leaves the running image put. It is
    backwards: the main image follows the chart appVersion; what lags is the
    two `patch-session-settings` initContainers.

Reads the REAL policy file through the real matchers of BOTH lanes
(auto-update.py policy_block for Renovate PRs, coverage.py
deny_rule_for_item for direct bumps) and check-all-versions.py bump_action.

Run:  python3 runbooks/tests/test-auto-update-policy-narrowed-globs.py
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
os.environ.setdefault("_MISE_ACTIVATED", "1")
sys.path.insert(0, str(REPO / "runbooks"))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore
    return mod


au = _load("au_policy_under_test", "runbooks/auto-update.py")
cov = _load("cov_policy_under_test", "runbooks/coverage.py")
cav = _load("cav_policy_under_test", "runbooks/check-all-versions.py")
POLICY = au.load_policy()
FAILURES: list[str] = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {str(detail)[:300]}"))
    if not ok:
        FAILURES.append(name)


def item_rule(component, kind, repo, utype):
    item = {"component": component, "kind": kind, "type": utype,
            "image_repo": repo} if repo else {"component": component, "kind": kind, "type": utype}
    return cov.deny_rule_for_item(POLICY, item, component.lower(), utype)


check("policy parses and is not the deny-all fail-safe", not POLICY.get("_deny_all"), POLICY)
check("policy version bumped to 2026.09.26.x", str(POLICY.get("version", "")).startswith("2026.09.26"),
      POLICY.get("version"))

print("affine")
check("affine-redis (redis image) patch is NOT held by an affine rule",
      item_rule("affine-redis", "image", "redis", "patch") is None,
      item_rule("affine-redis", "image", "redis", "patch"))
check("PR lane: depName `redis` for affine-redis is not held",
      au.policy_block(POLICY, "redis", "patch") is None)
r = item_rule("affine", "image", "ghcr.io/toeverything/affine", "patch")
check("the AFFiNE app image patch IS still held (direct-bump lane, by repo)",
      r is not None and "affine" in r.get("match", ""), r)
check("the AFFiNE app image IS still held (PR lane, depName)",
      au.policy_block(POLICY, "ghcr.io/toeverything/affine", "patch") is not None)

print("n8n")
check("the 8gears n8n CHART minor is NOT held by the n8n channel rule",
      item_rule("n8n", "chart", None, "minor") is None, item_rule("n8n", "chart", None, "minor"))
check("PR lane: chart depName `n8n` minor is not held",
      au.policy_block(POLICY, "n8n", "minor") is None)
r = item_rule("n8n", "image", "n8nio/n8n", "minor")
check("the n8nio/n8n IMAGE minor IS held (direct-bump lane, by repo)",
      r is not None and r.get("max") == "patch", r)
check("... and its patch is ALLOWED (max: patch)",
      item_rule("n8n", "image", "n8nio/n8n", "patch") is None)
check("PR lane: depName `n8nio/n8n` minor IS held, docker.io spelling too",
      au.policy_block(POLICY, "n8nio/n8n", "minor") is not None
      and au.policy_block(POLICY, "docker.io/n8nio/n8n", "minor") is not None)
act = cav.bump_action("n8n", "image", "2.38.7", "2.41.2", "minor", POLICY, repos=["n8nio/n8n"])
check("version-finding Action for the n8n image still says held (repo-aware bump_action)",
      act.startswith("held by auto-update-policy"), act)
act = cav.bump_action("n8n", "chart", "2.0.1", "2.1.1", "minor", POLICY)
check("version-finding Action for the n8n chart no longer claims a hold",
      not act.startswith("held by auto-update-policy"), act)

print("authentik")
rule = next((x for x in POLICY["deny"] if x.get("match") == "*authentik*"), {})
reason = " ".join(str(rule.get("reason", "")).split())
check("authentik rule still holds every update type", rule and rule.get("max") is None, rule)
check("reason says a chart-only bump DOES move the running image",
      "DOES move the running image" in reason, reason[:200])
check("reason names the two patch-session-settings initContainers as what lags",
      "patch-session-settings" in reason and "initContainers" in reason, reason[:300])
check("reason no longer carries the backwards claim",
      "while the running image stays put" not in reason, reason[:300])

print("docs/sops/auto-update.md matrix names the narrowed globs")
sop = (REPO / "docs/sops/auto-update.md").read_text()
check("SOP matrix row for `*toeverything/affine*`", "| `*toeverything/affine*` |" in sop)
check("SOP matrix row for `*n8nio/n8n*`", "| `*n8nio/n8n*` |" in sop)
check("SOP matrix has no stale `*affine*` / `*n8n*` rows",
      "| `*affine*` |" not in sop and "| `*n8n*` |" not in sop)

print()
if FAILURES:
    print(f"FAILED {len(FAILURES)}: {FAILURES}")
    sys.exit(1)
print("ALL PASS")
