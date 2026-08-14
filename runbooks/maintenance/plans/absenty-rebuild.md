---
plan_id: absenty-rebuild
component: absenty
pr: null                              # self-owned image; nothing upstream to bump to
kind: image
current: "ghcr.io/nachtschatt3n/absenty — 51 fixable CRITICAL (dev + prod)"
target: "rebuilt on a current base, 51 -> as close to 0 as the base allows"
update_type: patch                    # a rebuild, not a version change
risk: medium                          # externally exposed, and prod + dev both move
est_duration_min: 45
needs_reboot: false
touches:
  namespaces: [my-software-production, my-software-development]
  resources:
    - helmrelease/absenty              # both namespaces
    - "ghcr.io/nachtschatt3n/absenty (image-automation managed)"
    - ingress/absenty                  # class "external" in BOTH namespaces
  shared: []
depends_on: []
conflicts_with: []
status: draft
window: "tue-early:2026-08-25"        # earliest sensible slot; highest open CVE count
auto_execute: false                   # requires a build in another repo first
sops_refs:
  - docs/sops/application-update.md
generated: "2026-08-15"
---

# absenty: rebuild — 51 fixable CRITICAL, externally exposed

## 1) Summary & why this is now the top CVE item

**51 fixable CRITICAL** on `ghcr.io/nachtschatt3n/absenty`, deployed in **both**
`my-software-production` and `my-software-development`, and **both on `external`
ingresses**. That is more than double the next-largest cluster (superset's 19)
and roughly seven times any single upstream image.

**It was invisible until 2026-08-15.** absenty is a private GHCR package, so trivy
ran unauthenticated and reported it UNKNOWN — not clean, but not measured either.
Granting the local `gh` token `read:packages` (and forwarding it to trivy via
`TRIVY_USERNAME`/`TRIVY_PASSWORD` in `sweep-run.py`) made all 17 first-party
images scannable for the first time; absenty is what that uncovered.

**No bump can fix it** — we build this image. The remedy is a rebuild on a current
base in the absenty source repo, then letting Flux image-automation pick up the
new tag.

**Note the source is not on this Mac.** `/Users/mu/code/` has no `absenty`
checkout, so the build happens in GitHub Actions from a repo that must be cloned
or triggered separately. Confirm where it builds before the window.

## 2) Pre-checks

```bash
# both deployments, both tags
kubectl get pods -A -o jsonpath='{range .items[*].spec.containers[*]}{.image}{"\n"}{end}' | grep absenty | sort -u

# the number, and WHEN the image was built (a rebuild is only real if this moves)
export TRIVY_USERNAME=nachtschatt3n TRIVY_PASSWORD="$(gh auth token)"
trivy image ghcr.io/nachtschatt3n/absenty:<tag> --severity CRITICAL --ignore-unfixed -f json \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print('built:',d['Metadata']['ImageConfig']['created'])"

# what is it built FROM? 51 criticals in one image usually means a stale base
# (an old node/python/debian tag), not 51 distinct app dependencies.
#   -> inspect the Dockerfile in the absenty repo before rebuilding blindly

# how does the tag reach the cluster?
cat kubernetes/apps/my-software-development/absenty/app/image-automation.yaml
```

## 3) Steps

1. In the absenty repo: identify the base image and move it to a current tag.
   With 51 criticals, expect the base to be the dominant contributor — check that
   first rather than chasing individual dependencies.
2. Rebuild and push. **Verify the published image's build date changed** — a
   merged PR does not rebuild a semver-tagged image (the recurring trap; same as
   `harness-home-rebuild`).
3. Roll **development first**, verify (§4), then production. They are separate
   HelmReleases in separate namespaces, so they can and should be staged.
4. If Flux image-automation picks the tag up on its own, confirm it actually did
   rather than assuming — check the Deployment image, not the automation object.

## 4) Verification

```bash
export TRIVY_USERNAME=nachtschatt3n TRIVY_PASSWORD="$(gh auth token)"
trivy image ghcr.io/nachtschatt3n/absenty:<new-tag> --severity CRITICAL --ignore-unfixed
#   expect a large drop; if it is still ~51 the base did not actually change

kubectl get pods -n my-software-development | grep absenty   # Ready, 0 restarts
kubectl get pods -n my-software-production  | grep absenty
curl -s -o /dev/null -w '%{http_code}\n' https://<absenty-host>/   # 200, both envs
# App smoke test in DEV before prod: log in and exercise one core flow.
```

## 5) Rollback

Both namespaces are separate HelmReleases, so roll back independently by pinning
the previous tag and reconciling — the old image remains in GHCR. Staging dev
before prod is the real safety net: if dev regresses, prod never moves.

## 6) Interference notes

- Two namespaces, but no shared datastore and no shared ingress controller
  behaviour beyond a backend swap.
- **Externally exposed in both**, so prefer a low-traffic slot and do not stack it
  with the Envoy Gateway phases, which also touch external routing.
- Cross-repo: the build is not a cluster change and can happen any time before the
  window; only the tag move needs the slot.
