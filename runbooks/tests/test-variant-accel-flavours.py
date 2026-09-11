#!/usr/bin/env python3
"""Regression: hardware-accel tag flavours are VARIANTS, not version differences.

Near-miss found 2026-09-11 while bumping immich v3.1.0 -> v3.2.0 (F-aa7da9d6).

immich-machine-learning publishes `-openvino`, `-cuda`, `-rocm`, `-armnn`,
`-rknn` as sibling builds of one release, and the BARE tag is the CPU build.
_VARIANT_NAMES listed only distro names, so `_tag_variant('v3.1.0-openvino')`
returned '' -- the cross-variant guard in _pick_latest_semver_tag then read the
pin as plain, EXCLUDED variant tags, and would have proposed the bare CPU tag
as an "update".

That failure is silent in the worst way: the image pulls, the pod starts, and
inference merely stops being accelerated. No error, no alert. immich is not on
the auto-update deny-list, so the unattended nightly lane could have written the
CPU tag on the next release with nobody watching. Verified at the time: the bare
`immich-machine-learning:v3.2.0` really does exist and really is the CPU build,
so there was nothing to make the bad proposal fail loudly.

Run: python3 runbooks/tests/test-variant-accel-flavours.py
"""
import importlib.util
import os
import sys

os.environ.setdefault("_MISE_ACTIVATED", "1")
_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "check_all_versions", os.path.join(_HERE, "..", "check-all-versions.py"))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
V = _mod.VersionChecker

fails = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}: {name}" + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        fails.append(name)


# 1. each accel flavour is recognised as a variant, and is version-shaped
for tag, want in [("v3.2.0-openvino", "openvino"), ("v3.2.0-cuda", "cuda"),
                  ("1.2.3-cuda12", "cuda12"), ("2.0.0-rocm", "rocm"),
                  ("1.0.0-armnn", "armnn"), ("1.0.0-rknn", "rknn")]:
    check(f"{tag} -> variant {want!r}", V._tag_variant(tag) == want,
          f"got {V._tag_variant(tag)!r}")
    check(f"{tag} is version-shaped", bool(V._SEMVER_TAG_RE.match(tag)))

# 2. THE ACTUAL DEFECT: an accel-pinned image must never be offered the bare tag.
checker = V(os.path.join(_HERE, "..", ".."))
TAGS = ["v3.1.0", "v3.1.0-openvino", "v3.2.0", "v3.2.0-openvino",
        "v3.2.0-cuda", "v3.3.0", "v3.3.0-openvino"]
picked = checker._pick_latest_semver_tag(TAGS, current_tag="v3.1.0-openvino")
check("accel pin is NOT offered the bare CPU tag",
      picked is not None and picked.endswith("-openvino"),
      f"picked {picked!r} — a CPU build would silently replace an accelerated one")
check("accel pin is offered the newest SAME-variant tag", picked == "v3.3.0-openvino",
      f"picked {picked!r}")

# 3. the inverse must hold too: a plain pin must not be dragged onto a variant.
picked_plain = checker._pick_latest_semver_tag(TAGS, current_tag="v3.1.0")
check("plain pin stays plain", picked_plain == "v3.3.0",
      f"picked {picked_plain!r}")

# 4. a cuda pin must not cross to openvino (sibling accel flavours are distinct).
picked_cuda = checker._pick_latest_semver_tag(
    ["1.0.0-cuda", "2.0.0-cuda", "2.0.0-openvino"], current_tag="1.0.0-cuda")
check("cuda pin does not cross to openvino", picked_cuda == "2.0.0-cuda",
      f"picked {picked_cuda!r}")

# 5. ANTI-OVER-BROADENING: adding these anchors must not swallow a PRE-RELEASE
#    or a patch suffix. _pick_latest_semver_tag relies on prereleases staying
#    unshaped, so this is the guard that keeps the widening honest.
for tag in ["1.2.3-rc1", "1.2.3-beta", "1.2.3-alpha2", "1.2.3-dev"]:
    check(f"{tag} is still NOT version-shaped", not V._SEMVER_TAG_RE.match(tag),
          "a prerelease became variant-shaped — the anchor list is too broad")

# 6. the pre-existing distro + compound behaviour is untouched.
check("alpine still a variant", V._tag_variant("8.10.0-alpine") == "alpine")
check("compound distro+flavour still works",
      V._tag_variant("v0.143.0-noble-full") == "noble-full")

if fails:
    print(f"\n{len(fails)} FAILURE(S): {fails}")
    sys.exit(1)
print("\nall accel-variant guards pass")
