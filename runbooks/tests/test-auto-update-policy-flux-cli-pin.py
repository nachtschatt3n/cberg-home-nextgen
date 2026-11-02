"""Regression test (F-39ab2c30): the flux CLI pin is held, with its own reason.

`.mise.toml` pinned flux 2.10.0 (Renovate #448, auto-merged) while the cluster
runs distribution v2.9.6. docs/sops/flux-upgrade.md requires the CLI to match the
distribution. The pin was reverted to the distribution, and `aqua:fluxcd/flux2`
is held in the policy so the next Renovate PR cannot re-apply it.

Pins: the rule exists, holds every update_type in BOTH lanes, carries its own
reason (not the Talos node-image one), and no other glob matches first.

Run:  python3 runbooks/tests/test-auto-update-policy-flux-cli-pin.py
"""
from __future__ import annotations

import importlib.util
import os
import re
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


au = _load("au_flux_cli", "runbooks/auto-update.py")
cov = _load("cov_flux_cli", "runbooks/coverage.py")
POLICY = au.load_policy()
FAILURES: list[str] = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {str(detail)[:300]}"))
    if not ok:
        FAILURES.append(name)


check("policy parses and is not the deny-all fail-safe", not POLICY.get("_deny_all"), POLICY)
check("policy version >= 2026.11.04", str(POLICY.get("version", "")) >= "2026.11.04", POLICY.get("version"))

DEP = "aqua:fluxcd/flux2"
for utype in ("patch", "minor", "major"):
    why = au.policy_block(POLICY, DEP, utype) or ""
    check(f"PR lane {utype}: held", bool(why))
    check(f"PR lane {utype}: reason is the CLI pin's own",
          "flux CLI pin" in why and "Talos node image" not in why, why[:160])
    rule = cov.deny_rule_for(POLICY, DEP, utype)
    check(f"direct-bump lane {utype}: rule is `aqua:fluxcd/flux2`",
          rule is not None and rule.get("match") == DEP, rule)

rule = next((r for r in POLICY["deny"] if r.get("match") == DEP), {})
check("no `max:` (held at every update_type)", rule and rule.get("max") is None, rule)
check("the flux-operator / controller images are NOT caught by the CLI rule",
      au.policy_block(POLICY, "ghcr.io/controlplaneio-fluxcd/flux-operator", "patch") is None
      or "flux CLI pin" not in au.policy_block(POLICY, "ghcr.io/controlplaneio-fluxcd/flux-operator", "patch"))

print("repo state")
mise = (REPO / ".mise.toml").read_text()
m = re.search(r'"aqua:fluxcd/flux2"\s*=\s*"([^"]+)"', mise)
check(".mise.toml pins the flux CLI at a concrete version", bool(m) and bool(re.match(r"\d+\.\d+\.\d+$", m.group(1))))
# Deliberately NOT asserted: pin == distribution. A distribution upgrade (flux-fleet
# plans) moves helm-values.yaml first and the CLI pin after it, so an equality gate
# would block the very commit that performs the planned upgrade.

sop = (REPO / "docs/sops/auto-update.md").read_text()
check("SOP matrix has the `aqua:fluxcd/flux2` row", "| `aqua:fluxcd/flux2` |" in sop)

print()
if FAILURES:
    print(f"FAILED {len(FAILURES)}: {FAILURES}")
    sys.exit(1)
print("ALL PASS")
