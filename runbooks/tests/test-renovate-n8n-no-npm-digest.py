#!/usr/bin/env python3
"""Regression test (F-629a2f82): the n8n Renovate rule must not leak an npm
integrity as an image digest.

2026-11-02: PR #252 rewrote the n8n image tag to `2.45.7@sha512-<integrity>`, an
invalid image reference. Cause (reproduced with a local `renovate
--platform=local --dry-run=lookup`, renovate 44.133.0): the rule used
`overrideDatasource: npm`; the npm datasource attaches `dist.integrity` to every
release as `newDigest`, Renovate copies it into the update, and the flux
manager's replacement template appends `@{{newDigest}}`. `pinDigests: false` is
NOT a fix -- once the datasource is npm the digest stage that honours it is
skipped. The channel pointer now comes from a custom datasource that returns one
release (the `stable` dist-tag) and no digest.

This test pins the config shape. The behavioural proof is the dry-run recorded in
the commit; re-run it when touching the rule:
  renovate-config-validator --strict .github/renovate.json5

Run: python3 runbooks/tests/test-renovate-n8n-no-npm-digest.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FAILURES: list[str] = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {str(detail)[:300]}"))
    if not ok:
        FAILURES.append(name)


def load_json5(path: Path) -> dict:
    """Tolerant loader for this file only: full-line // comments and trailing commas."""
    text = "\n".join(l for l in path.read_text().splitlines() if not l.strip().startswith("//"))
    return json.loads(re.sub(r",(\s*[\]}])", r"\1", text))


cfg = load_json5(REPO / ".github/renovate.json5")
rules = [r for r in cfg.get("packageRules", []) if "n8nio/n8n" in (r.get("matchPackageNames") or [])]

check("exactly one packageRule targets n8nio/n8n", len(rules) == 1, len(rules))
rule = rules[0] if rules else {}
override = str(rule.get("overrideDatasource", ""))
check("the rule does NOT override the datasource to npm (npm emits integrity as newDigest)",
      override != "npm", override)
check("the rule reads the channel pointer from the custom datasource",
      override == "custom.n8n-stable", override)

ds = (cfg.get("customDatasources") or {}).get("n8n-stable", {})
check("custom datasource n8n-stable is defined", bool(ds), cfg.get("customDatasources"))
check("it reads the npm `n8n` dist-tags endpoint",
      "registry.npmjs.org/-/package/n8n/dist-tags" in str(ds.get("defaultRegistryUrlTemplate")), ds)
tpl = " ".join(ds.get("transformTemplates") or [])
check("it yields exactly the `stable` tag as the one release, with no digest field",
      "stable" in tpl and "newDigest" not in tpl and "digest" not in tpl.lower(), tpl)
check("followTag is gone (the docker/npm tag map it needed is not used)",
      "followTag" not in rule, rule)
check("pinDigests is not relied on (it is a no-op for this path)",
      "pinDigests" not in rule, rule)

print()
if FAILURES:
    print(f"FAILED {len(FAILURES)}: {FAILURES}")
    sys.exit(1)
print("ALL PASS")
