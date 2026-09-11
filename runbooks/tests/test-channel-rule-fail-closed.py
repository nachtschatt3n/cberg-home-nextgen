#!/usr/bin/env python3
"""Regression: a CHANNEL_RULES component is NEVER AUTO, whatever its version says.

CHANNEL_RULES used to carry a parity predicate for scrypted, `"stable":
"odd-minor"`, and _stable_by_rule() returned stable=True for any odd minor.

Two defects, found 2026-09-11 while bumping scrypted v0.143.0 -> v0.145.0:

  DISPROVED. Parity was never upstream's rule. v0.118/120/122/124/126 and ~17
  more scrypted releases carry prerelease=false on EVEN minors. The actual gate
  is whether a non-prerelease GitHub Release exists for that EXACT tag, which no
  version string can answer — v0.146.1 was pullable from the registry with no
  Release and no git tag at all.

  FAILED OPEN, in the direction that matters. A Release-less dev tag on an ODD
  minor (v0.147.0) scored stable -> AUTO lane -> applied UNATTENDED at Step 0 of
  the nightly window, onto a privileged NVR (privileged: true, SYS_ADMIN, i915).
  The deny rule in auto-update-policy.yaml was the only thing holding that door,
  so the "defence in depth" the code comment claimed was one layer wearing two
  hats.

Fix: membership in CHANNEL_RULES is itself the hold. There is no predicate left
to fail open, and a set membership test is decidable OFFLINE — which the design
requires, since the window agent runs coverage.py without SWEEP_PG_DSN and a
DB/network-gated check would fail open exactly where it matters.

Run: python3 runbooks/tests/test-channel-rule-fail-closed.py
"""
import importlib.util
import os
import pathlib
import sys

os.environ.setdefault("_MISE_ACTIVATED", "1")
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "runbooks"))
spec = importlib.util.spec_from_file_location("coverage_mod", ROOT / "runbooks" / "coverage.py")
cov = importlib.util.module_from_spec(spec)
sys.modules["coverage_mod"] = cov
spec.loader.exec_module(cov)

fails = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}: {name}" + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        fails.append(name)


def hold(comp, target):
    return cov.channel_hold(comp, {"target": target})


# 1. THE DEFECT: an ODD-minor Release-less dev tag must be held, not AUTO'd.
for tgt in ["v0.147.0-noble-full", "v0.145.0-noble-full", "v0.149.3"]:
    h = hold("scrypted", tgt)
    check(f"odd-minor {tgt} is HELD", h is not None,
          "scored stable -> would reach the unattended AUTO lane on a privileged NVR")

# 2. Even minors stay held too (previously held for the wrong reason).
for tgt in ["v0.146.1-noble-full", "v0.148.0"]:
    check(f"even-minor {tgt} is HELD", hold("scrypted", tgt) is not None)

# 3. The hold must not claim something it cannot know. It is "cannot be shown
#    stable offline", NOT "this IS a pre-release" — v0.145.0 is genuinely stable
#    and is still held, so asserting pre-release would be a false statement.
h = hold("scrypted", "v0.145.0-noble-full")
check("hold reason does not assert the tag IS a pre-release",
      "PRE-RELEASE channel" not in h,
      f"reason overclaims: {h!r}")
check("hold reason explains the real gate (a Release for that exact tag)",
      "Release" in h and "offline" in h)
check("hold reason still names the AR and the workload",
      "AR-081" in h and "privileged NVR" in h)

# 4. The disproved predicate is GONE, not merely unused — a dormant
#    _stable_by_rule is an invitation to re-wire it.
src = (ROOT / "runbooks" / "coverage.py").read_text()
check("_stable_by_rule is removed", "def _stable_by_rule" not in src)
# Assert the DATA, not the source text: the explanatory comment quotes the old
# predicate on purpose, so a grep would match the very documentation of the fix.
parity = {c: r["stable"] for c, r in cov.CHANNEL_RULES.items() if "stable" in r}
check("no CHANNEL_RULES entry carries a 'stable' predicate", not parity,
      f"parity predicates still live: {parity}")

# 5. Components NOT in CHANNEL_RULES are unaffected (no invented holds).
check("unlisted component with a clean tag is not held",
      hold("grafana", "13.2.2") is None)
check("explicit pre-release markers still hold for ANY component",
      hold("grafana", "13.3.0-beta1") is not None)

# 6. Offline-decidability: the hold must need neither DSN nor network. Proven by
#    the calls above running with no SWEEP_PG_DSN set.
check("SWEEP_PG_DSN is absent in this process", not os.environ.get("SWEEP_PG_DSN"),
      "test cannot prove offline-decidability with a DSN present")

if fails:
    print(f"\n{len(fails)} FAILURE(S): {fails}")
    sys.exit(1)
print("\nall channel-rule fail-closed guards pass")
