---
plan_id: absenty-rebuild
component: absenty
pr: nachtschatt3n/Absenty#57          # merged 2026-08-15
kind: image
current: "ghcr.io/nachtschatt3n/absenty — image-automation managed, both namespaces"
target: "rebuilt on a current base; tag selection moved to the branch-prefixed timestamp tag"
update_type: patch                    # a rebuild, not a version change
risk: medium                          # prod + dev both move
est_duration_min: 45
needs_reboot: false
security_ref: F-c58dd98e
touches:
  namespaces: [my-software-production, my-software-development]
  resources:
    - helmrelease/absenty              # both namespaces
    - imagepolicy/absenty              # both namespaces
    - imageupdateautomation/absenty-image-updates
    - "ghcr.io/nachtschatt3n/absenty (image-automation managed)"
    - ingress/absenty                  # both namespaces
  shared: []
depends_on: []
conflicts_with: []
status: in-progress
window: null                           # released on operator GO, 2026-08-15
auto_execute: false                    # requires a build in another repo first
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/vulnerability-disclosure.md
generated: "2026-08-15"
executed: "2026-08-15"
---

# absenty: rebuild on a current base + fix image-tag provenance

> **Security driver — detail withheld from this public repo.**
> Tracked as **F-c58dd98e** (`plan` / severity `deferred`).
> Full detail (CVE IDs, counts, exposure, exploitability) lives on the
> finding record — it is deliberately not reproduced here.
>
> - Dashboard: `https://sweep.<DOMAIN>/findings/F-c58dd98e`
> - CLI: `runbooks/policy-cli.py finding show F-c58dd98e`
> - Plans: absenty-rebuild
>
> See `docs/sops/vulnerability-disclosure.md` before adding any
> vulnerability detail to a committed file.

## 1) Summary

absenty is a **self-built** image, so there is nothing upstream to bump to —
the remedy is a rebuild on a current base in the application repo, then letting
Flux image-automation pick the new tag up.

It is a private GHCR package, so trivy previously ran unauthenticated against
it and reported UNKNOWN — not clean, but not measured either. Granting the
local `gh` token `read:packages` and forwarding it via
`TRIVY_USERNAME`/`TRIVY_PASSWORD` in `sweep-run.py` made all first-party images
scannable, which is what surfaced this.

**The source is not on this Mac.** `/Users/mu/code/` has no `absenty` checkout;
the build happens in GitHub Actions in `nachtschatt3n/Absenty` (default branch
`production`, integration branch `development`).

## 2) The three defects, in the order they had to be fixed

A rebuild alone would have achieved nothing. Three independent problems:

**(a) Stale base + cache-frozen apt layer.** The Dockerfile pinned a
2025-01 snapshot of `ruby:3.3.x-slim-bookworm`, and its `RUN apt-get` line had
not changed since, so buildkit replayed a cached October-2025 package layer on
every build. Moving `FROM` invalidates the cache; `apt-get upgrade` stops it
re-freezing.

**(b) The ImagePolicy could not select a new image.** Both policies filtered on
a bare 7-char hex git-sha tag and ordered with `policy.alphabetical` — which is
not a time order. Selection had been pinned since 2025-10 to whichever sha
happened to sort highest, so **0 of the 338 tags** in the repository could ever
have been chosen. A fresh sha had roughly a 0.2% chance of sorting above the
incumbent, so a rebuild would have been silently discarded.

**(c) Tag provenance: pull requests published release-shaped tags.** Two
workflows both published to the same package. The older one (`ci-cd.yml`) built
on *every* event including `pull_request`, where `github.ref` is
`refs/pull/N/merge` — so it took a "fallback" path that built the **dev** stage
of unreviewed branch code and published it under a bare `sha-<hex>` tag, the
same shape the production ImagePolicy selected on. The last three tags
published to the package before this work (`pr-54`, `pr-55`, `pr-56`) are that
build.

Its own "chronological" tag was inert as well:
`docker/metadata-action` does not expand Go date layouts inside `type=raw`, so
`sha-{{date '20060102150405'}}-{{sha}}` published that string literally.

> Ordering matters: **(c) must be fixed before automation is unsuspended.**
> Unsuspending first re-arms exactly the path it closes.

### Correction to an earlier draft of this plan

An earlier revision claimed a mis-selected image would run "Rails in
development mode with host authorization disabled". **That is false** — both
HelmReleases set `RAILS_ENV`/`RACK_ENV` explicitly in the pod spec, which
overrides the image ENV. The accurate characterisation is narrower: unreviewed
branch code, dev/test gems present, and the production boot sequence skipped
(the dev stage's `CMD` omits `db:prepare` + puma).

## 3) Steps

1. **Application repo — fix tag provenance first.** Make one workflow the sole
   publisher; branch-prefix every published tag; never push from a
   `pull_request` event.
2. **Application repo — rebuild on a current base**, and unblock the red test
   that gates `build_and_push`.
3. **Cluster repo — fix both ImagePolicies** to select the branch-prefixed
   timestamp tag numerically. Safe to land while automation is suspended: it
   changes only which tag the policy *resolves to*, so resolution can be
   verified before anything is armed.
4. **Roll development first**, verify (§4), then production. Separate
   HelmReleases in separate namespaces — they can and should be staged.
5. **Only then unsuspend** both `ImageUpdateAutomation`s.

## 4) Verification

```bash
export TRIVY_USERNAME=nachtschatt3n TRIVY_PASSWORD="$(gh auth token)"

# A rebuild is only real if the build date moved. A merged PR does not imply a
# rebuilt image — see docs/sops/self-built-image-rebuild.md.
trivy image ghcr.io/nachtschatt3n/absenty:<new-tag> --severity CRITICAL --ignore-unfixed -f json \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print('built:',d['Metadata']['ImageConfig']['created'])"

# Prove the policy resolves to a real production tag, not just that it is Ready.
kubectl get imagepolicy absenty -n my-software-production -o jsonpath='{.status.latestRef.tag}'
kubectl get imagepolicy absenty -n my-software-development -o jsonpath='{.status.latestRef.tag}'

# A SUSPENDED ImageUpdateAutomation still reports READY=True. Check the field.
kubectl get imageupdateautomation absenty-image-updates -n my-software-production \
  -o jsonpath='{.spec.suspend}{"\n"}'

# Check the DEPLOYMENT image, not the automation object.
kubectl get deploy -n my-software-development -l app.kubernetes.io/name=absenty \
  -o jsonpath='{.items[*].spec.template.spec.containers[*].image}{"\n"}'

kubectl get pods -n my-software-development | grep absenty   # Ready, 0 restarts
kubectl get pods -n my-software-production  | grep absenty
# App smoke test in DEV before prod: log in and exercise one core flow.
```

## 5) Rollback

Both namespaces are separate HelmReleases, so roll back independently by
pinning the previous tag and reconciling — the old image remains in GHCR.
Staging dev before prod is the real safety net: if dev regresses, prod never
moves. If automation has been unsuspended, re-suspend it first, otherwise it
will re-apply the new tag over the rollback.

## 6) Interference notes

- Two namespaces, but no shared datastore and no shared ingress-controller
  behaviour beyond a backend swap.
- Both are on the `external` ingress class, so prefer a low-traffic slot and do
  not stack this with the Envoy Gateway phases, which also touch external
  routing.
- Cross-repo: the build is not a cluster change and can happen any time before
  the window; only the tag move needs the slot.
- **Any rollout releases a large application backlog.** The running production
  image was many commits behind the production branch tip, including a mobile
  holiday-request feature and host-authorization changes. Rebuilding
  necessarily ships all of it. That is a release, not a pure rebuild, and it
  cannot be smoke-tested unattended — it needed an explicit operator GO, which
  was given on 2026-08-15.
