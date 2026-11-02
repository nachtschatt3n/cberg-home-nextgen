"""Regression test: `*immich-redis*` is matched BEFORE `*immich*` (policy 2026.11.03).

First match wins in BOTH lanes (auto-update.py policy_block for Renovate PRs,
coverage.py deny_rule_for for direct bumps). With only `*immich*`, the immich
redis sidecar -- a non-persistent BullMQ queue store with no database -- was held
under the Immich SERVER's forward-only-DB-migration reason, which is false for it.

The new rule must change the REASON only: every verdict (held at every
update_type) stays identical, for the redis sidecar and for the server.

Run:  python3 runbooks/tests/test-auto-update-policy-immich-redis-order.py
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


au = _load("au_immich_redis", "runbooks/auto-update.py")
cov = _load("cov_immich_redis", "runbooks/coverage.py")
POLICY = au.load_policy()
FAILURES: list[str] = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {str(detail)[:300]}"))
    if not ok:
        FAILURES.append(name)


check("policy parses and is not the deny-all fail-safe", not POLICY.get("_deny_all"), POLICY)
check("policy version >= 2026.11.03", str(POLICY.get("version", "")) >= "2026.11.03", POLICY.get("version"))

matches = [r.get("match") for r in POLICY["deny"]]
check("both globs present", "*immich-redis*" in matches and "*immich*" in matches, matches)
check("`*immich-redis*` is ABOVE `*immich*` (first match wins)",
      matches.index("*immich-redis*") < matches.index("*immich*"), matches)

print("immich-redis: own reason, still held at every update_type")
for utype in ("patch", "minor", "major"):
    why = au.policy_block(POLICY, "immich-redis", utype) or ""
    check(f"PR lane {utype}: held", bool(why))
    check(f"PR lane {utype}: reason is the redis rule's own, not the server's",
          "BullMQ" in why and "forward-only DB migrations" not in why, why[:160])
    rule = cov.deny_rule_for(POLICY, "immich-redis", utype)
    check(f"direct-bump lane {utype}: rule is `*immich-redis*`",
          rule is not None and rule.get("match") == "*immich-redis*", rule)

print("immich server: verdict and reason unchanged")
for dep in ("immich", "immich-server", "ghcr.io/immich-app/immich-server"):
    for utype in ("patch", "minor", "major"):
        why = au.policy_block(POLICY, dep, utype) or ""
        check(f"PR lane {dep} {utype}: held with the server reason",
              "forward-only DB migrations" in why, why[:160])
        rule = cov.deny_rule_for(POLICY, dep, utype)
        check(f"direct-bump lane {dep} {utype}: rule is `*immich*`",
              rule is not None and rule.get("match") == "*immich*", rule)

print("nothing loosened: the new rule carries no `max:`")
rule = next(r for r in POLICY["deny"] if r.get("match") == "*immich-redis*")
check("no `max:` on `*immich-redis*`", rule.get("max") is None, rule)
check("a plain `redis` depName is still NOT held by it (rule is consumer-scoped)",
      au.policy_block(POLICY, "redis", "patch") is None)

print()
if FAILURES:
    print(f"FAILED {len(FAILURES)}: {FAILURES}")
    sys.exit(1)
print("ALL PASS")
