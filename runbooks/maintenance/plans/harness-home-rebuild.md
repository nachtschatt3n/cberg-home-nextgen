---
plan_id: harness-home-rebuild
component: ha-ai-harness
pr: null                              # self-owned image; nothing upstream to bump to
kind: image
current: "ghcr.io/nachtschatt3n/harness-home-{server,frontend}:0.5.1-alpha"
target: "same version, REBUILT on a current base (or a new tagged release)"
update_type: patch
risk: low
est_duration_min: 30
needs_reboot: false
touches:
  namespaces: [home-automation]
  resources:
    - helmrelease/ha-ai-harness
    - "ghcr.io/nachtschatt3n/harness-home-server:0.5.1-alpha"
    - "ghcr.io/nachtschatt3n/harness-home-frontend:0.5.1-alpha"
  shared: []
depends_on: []
conflicts_with: []
status: draft
window: "tue-early:2026-09-08"
auto_execute: false                   # requires a build in another repo first
sops_refs:
  - docs/sops/application-update.md
generated: "2026-08-15"
---

# harness-home: rebuild the self-owned image (3 fixable CRITICAL)

## 1) Summary & why held

`ghcr.io/nachtschatt3n/harness-home-server:0.5.1-alpha` carries **3 fixable
CRITICAL** CVEs. Unlike every other CVE in the register there is **no upstream to
bump to** — we build this image. The fix is a rebuild on a current base, in
`/Users/mu/code/ha-ai-harrnes` (note the repo directory's spelling), then a tag
or digest move here.

**The trap this plan exists for:** *a merged PR does not rebuild a semver-tagged
image.* Bumping the manifest to the same tag changes nothing if CI did not
republish it. Always verify the image's **build date**, not its tag.

Also note the frontend image shares the tag; check both.

## 2) Pre-checks

```bash
# what is running, and WHEN was it actually built
kubectl get pods -n home-automation -o jsonpath='{range .items[*].spec.containers[*]}{.image}{"\n"}{end}' | grep harness
trivy image ghcr.io/nachtschatt3n/harness-home-server:0.5.1-alpha \
  --severity CRITICAL --ignore-unfixed -f json | \
  python3 -c "import sys,json;d=json.load(sys.stdin);print('built:',d['Metadata']['ImageConfig']['created'])"

# NOTE: these are PRIVATE ghcr packages — trivy needs a token with read:packages
# (see sweep-run's TRIVY_PASSWORD passthrough). Without it you get UNAUTHORIZED,
# which is why this image sat as "could NOT determine" rather than measured.

# what base does it build FROM?
grep -n '^FROM' /Users/mu/code/ha-ai-harrnes/Dockerfile*  2>/dev/null
```

## 3) Steps

1. In `/Users/mu/code/ha-ai-harrnes`: update the base image in the Dockerfile(s)
   to a current tag, rebuild and push **both** server and frontend.
2. Prefer a **new version tag** (e.g. `0.5.2-alpha`) over rebuilding
   `0.5.1-alpha` in place — an immutable tag makes "did it actually rebuild?"
   answerable, which is exactly the failure mode above.
3. Update the tag in
   `kubernetes/apps/home-automation/ha-ai-harness/app/helmrelease.yaml`, commit,
   push, reconcile.

## 4) Verification

```bash
# the image REALLY changed — compare build date, not tag
trivy image <new-tag> --severity CRITICAL --ignore-unfixed -f json | \
  python3 -c "import sys,json;d=json.load(sys.stdin);print('built:',d['Metadata']['ImageConfig']['created'])"
trivy image <new-tag> --severity CRITICAL --ignore-unfixed   # expect 0
kubectl get pods -n home-automation | grep harness           # Ready, 0 restarts
# app smoke test: the harness UI loads and reaches Home Assistant
```

## 5) Rollback

`git revert` the tag change and reconcile — the old image is still in ghcr. The
build in the other repo needs no rollback; an unused tag is harmless.

## 6) Interference notes

- Single app in `home-automation`, no shared datastore, no ingress-controller
  involvement. Safe to co-schedule with unrelated small plans.
- Cross-repo: the build step is NOT a cluster change and can be done any time
  before the window. Only the tag move needs the window.
