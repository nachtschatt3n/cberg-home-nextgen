#!/usr/bin/env python3
"""Regression tests: raw-manifest workloads must enter the version-check
denominator, and non-Kubernetes YAML in kubernetes/apps/ must not veto the
whole section.

`find_helmreleases()` enumerates ONLY `kind: HelmRelease` files. A workload
authored as a plain Deployment/StatefulSet/DaemonSet manifest inside an app
directory never entered the version-tracking universe at all — not "checked
and clean", simply never looked at (F-a77181c9, 2026-08-24). 23 containers
across ~20 raw-manifest apps were invisible this way, including the ENTIRE
Wazuh SIEM (the security-monitoring stack itself unmonitored) and three
`redis:8.10.0-alpine` caches that sat a patch version behind their
chart-managed siblings with nothing to flag it. Same denominator-class bug as
doc-check.py's `find_repo_subworkloads()`, applied to version coverage.

`find_raw_manifest_workloads()` closes it by walking kubernetes/apps/ for raw
`kind: Deployment|StatefulSet|DaemonSet` manifests and returning
HelmRelease-shaped dicts the existing per-image check loop already knows how
to handle. Fixing the WIDER denominator surfaced a narrower bug immediately:
this repo also carries non-Kubernetes YAML dialects under kubernetes/apps/
(Authentik blueprints, `!KeyOf` custom tags), and the first pass crashed
PyYAML's safe loader on one, recording a SECTION-WIDE `degraded.record()` (no
`component=`) that would have vetoed auto-close for the entire version
section on every run. A cheap `kind:` line pre-filter, run before the YAML
parse, closes that without narrowing the actual coverage — a file with no
matching `kind:` line can never satisfy `_RAW_WORKLOAD_KINDS` anyway.

Run: python3 runbooks/tests/test-raw-manifest-image-coverage.py
"""
import importlib.util
import os
import pathlib
import sys
import tempfile

os.environ["_MISE_ACTIVATED"] = "1"
ROOT = pathlib.Path(__file__).resolve().parents[2]
os.chdir(ROOT)
sys.argv = ["check-all-versions.py"]
spec = importlib.util.spec_from_file_location(
    "cav", ROOT / "runbooks" / "check-all-versions.py")
cav = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cav)

PASS = FAIL = 0


def check(name, got, want):
    global PASS, FAIL
    if got == want:
        print(f"  PASS  {name}")
        PASS += 1
    else:
        print(f"  FAIL  {name}\n        got {got!r}\n        want {want!r}")
        FAIL += 1


print("raw-manifest image coverage tests\n")

# ── _split_image_ref: the parsing primitive ─────────────────────────────────
SPLIT_CASES = [
    ("redis:8.10.0-alpine", ("redis", "8.10.0-alpine")),
    ("postgres:17.11-alpine@sha256:18cfe3ef5e6815560c98237d6216d1e5119702fb0f3894c8785dd58b8bbe5d73",
     ("postgres", "17.11-alpine")),
    ("ghcr.io/nextcloud-releases/whiteboard:v1.5.9",
     ("ghcr.io/nextcloud-releases/whiteboard", "v1.5.9")),
    ("wazuh/wazuh-dashboard:4.14.5", ("wazuh/wazuh-dashboard", "4.14.5")),
    ("registry:5000/app:v1", ("registry:5000/app", "v1")),
    ("registry:5000/app", ("registry:5000/app", "latest")),  # port, no tag
    ("nginx", ("nginx", "latest")),
    ("busybox@sha256:deadbeef", ("busybox", "latest")),  # digest, no tag
    ("", ("", "latest")),
]
for ref, want in SPLIT_CASES:
    check(f"_split_image_ref({ref!r})", cav._split_image_ref(ref), want)

# ── the denominator: real inventory, must find the known instances ─────────
vc = cav.VersionChecker(str(ROOT))
raw = vc.find_raw_manifest_workloads()
by_name = {w["name"]: w for w in raw}

check("no DEGRADED events from the real inventory (the !KeyOf regression)",
      vc.degraded._reasons, [])

for name, ns in [
    ("wazuh-manager-master", "security"),
    ("wazuh-indexer", "security"),
    ("wazuh-dashboard", "security"),
    ("wazuh-agent", "security"),
    ("redisinsight", "databases"),
    ("pgadmin", "databases"),
    ("edot-collector", "monitoring"),
    ("nextcloud-whiteboard", "office"),
    ("nextcloud-notify-push", "office"),
    ("scan-inbox-validator", "office"),
    ("authentik-pg", "kube-system"),
    ("superset-pg", "databases"),
    ("paperless-db", "office"),
]:
    check(f"raw workload {name!r} is found in {ns!r}",
          name in by_name and by_name[name]["namespace"] == ns, True)

# The whole point: the entire Wazuh SIEM has real coverage now, not zero.
wazuh_images = [i for w in raw if w["namespace"] == "security"
                for i in w["images"]]
check("Wazuh SIEM has at least 4 tracked images (manager/indexer/dashboard/agent)",
      len(wazuh_images) >= 4, True)

# The three orphaned redis:8.10.0-alpine caches (coverage.py's own finding).
redis_caches = [w["name"] for w in raw
                if any(i["repository"] == "redis" for i in w["images"])]
check("all three orphaned redis caches found (superset/nextcloud/paperless)",
      sorted(redis_caches),
      sorted(["superset-redis-official", "nextcloud-redis", "paperless-redis"]))

# ── a postRenderer patch fragment (kind matches, no `image:`) must be a no-op
patch_names = [w["name"] for w in raw
               if "patch-blueprints-volumes" in str(w.get("file_path", ""))]
check("a patch fragment with no `image:` key produces no entry",
      patch_names, [])

# ── the non-Kubernetes-YAML guard, in isolation ─────────────────────────────
with tempfile.TemporaryDirectory() as td:
    apps_dir = pathlib.Path(td) / "kubernetes" / "apps" / "storage" / "longhorn" / "app"
    apps_dir.mkdir(parents=True)
    # An Authentik-blueprint-shaped file: no `kind:` line at all, and a custom
    # tag PyYAML's safe loader cannot construct.
    (apps_dir / "authentik-blueprint.yaml").write_text(
        "version: 1\nentries:\n  - id: x\n    attrs:\n      provider: !KeyOf y\n")
    vc2 = cav.VersionChecker(td)
    raw2 = vc2.find_raw_manifest_workloads()
    check("a non-Kubernetes YAML file (no matching `kind:` line) is skipped, not crashed",
          raw2, [])
    check("...and produces NO section-wide degradation",
          vc2.degraded._reasons, [])

# A genuinely broken REAL manifest (kind: Deployment present) must still
# record a degradation -- the pre-filter narrows FALSE triggers, it must not
# also swallow a real parse failure of a real workload.
with tempfile.TemporaryDirectory() as td:
    apps_dir = pathlib.Path(td) / "kubernetes" / "apps" / "test" / "app"
    apps_dir.mkdir(parents=True)
    (apps_dir / "deployment.yaml").write_text(
        "kind: Deployment\nspec:\n  template:\n    spec:\n"
        "      containers:\n        - image: !KeyOf broken\n")
    vc3 = cav.VersionChecker(td)
    raw3 = vc3.find_raw_manifest_workloads()
    check("a genuinely broken K8s manifest still records a degradation",
          len(vc3.degraded._reasons) >= 1, True)

print(f"\n  {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
