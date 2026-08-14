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
status: blocked
window: "tue-early:2026-08-25"        # earliest sensible slot; highest open CVE count
auto_execute: false                   # requires a build in another repo first
sops_refs:
  - docs/sops/application-update.md
generated: "2026-08-15"
executed: "2026-08-15"          # partial - see Execution Log
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
   merged PR does not rebuild a semver-tagged image (the recurring trap; see
   `docs/sops/self-built-image-rebuild.md`).
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

## 7) Execution Log — 2026-08-15 (unattended run, PARTIAL / BLOCKED)

### Root cause found — it was NOT just a stale base

Two independent causes, plus a third that would have silently discarded the fix.

**(a) Stale base.** `ruby:3.3.6-slim-bookworm` is a 2025-01 snapshot of
debian 12.9. Scanned alone it carries 11 fixable CRITICALs.
`ruby:3.3.12-slim-bookworm` (debian 12.15, built 2026-08-05) carries **0**.

**(b) Cache-frozen apt layer.** The other ~34 OS CVEs (imagemagick x20,
mariadb-client x10, libnss3, glib) come from packages the Dockerfile
apt-installs. The `RUN apt-get` line never changed, so buildkit replayed a
cached October-2025 layer on every build. Changing `FROM` invalidates it;
`apt-get upgrade` stops it re-freezing.

**(c) The image automation is broken — this is the real finding.** The
ImagePolicy sorts 7-char hex git shas with `policy.alphabetical`, so it
selects the highest *hex string*, not the newest build. Both namespaces have
been pinned since 2025-10 to whatever tag happened to start with `ff`:

| ns | deployed tag | built | newest build that exists |
|---|---|---|---|
| my-software-production | `sha-ffa072a` | 2025-10-05 | `production-20251011222540` |
| my-software-development | `sha-ff3910e-dev` | 2025-10-05 | `development-20251102231017` |

A rebuild would have been discarded the same way: a fresh sha has ~0.2%
chance of sorting above `ffa072a`. **Fixing the Dockerfile alone would have
achieved nothing.**

Armed, it was also a live hazard: PR builds push a plain `sha-<merge-sha>`
tag matching the prod pattern `^sha-[0-9a-f]+$`, so any PR whose merge sha
sorted high would have deployed a **dev-target** image (Rails in development
mode, host authorization disabled) into externally-exposed production.

### Done

- `fix(absenty): suspend broken image automation in both namespaces`
  (cberg-home-nextgen `224ec52f`) — `suspend: true` on both
  ImageUpdateAutomations. Changes no running image; removes the hazard above.
- nachtschatt3n/Absenty PR #57 `chore/base-image-cve-rebuild` — base
  3.3.6 -> 3.3.12, `apt-get upgrade`, node 20 -> 22, gems rails 8.0.3 ->
  8.0.5.1 / concurrent-ruby -> 1.3.8 / net-imap -> 0.6.6 / rack-session ->
  2.1.2. **Not merged.**

### Blocked — two operator decisions required

1. **CI is red on an unrelated pre-existing test.**
   `UserTest#test_age_should_calculate_correct_age` fails (expected 30, got
   29). `User#age` is `((Date.current - birthday)/365.25).floor`, off-by-one
   on exact anniversaries; it broke through calendar drift, last green
   2025-11-24. Not fixed here: `age` is HR business logic that can drive
   holiday entitlement. The test gate blocks `build_and_push`, so **no image
   could be built and the CVE drop could not be verified on a real image.**

2. **Any rollout releases a 135-file application backlog.** The running
   production image is 51 commits / +35,238 / -12,650 behind the production
   branch tip, including a mobile holiday-request feature and host-
   authorization changes. Rebuilding necessarily ships all of it. That is a
   release, not the "rebuild, not a version change" this plan scoped, and it
   cannot be smoke-tested unattended.

### Not done (deliberately)

- Neither namespace was rolled. Cluster baseline preserved.
- The ImagePolicy fix (switch to the chronological `production-<timestamp>` /
  `development-<timestamp>` tag the CI already emits, via
  `filterTags.extract`) is **prepared but not applied** — applying it also
  releases the backlog in (2).

### Next window

1. Operator decides on `User#age` and on releasing the backlog.
2. Fix `age`, merge PR #57, confirm a green build.
3. Flip both ImagePolicies to the timestamp pattern, unsuspend automation.
4. Verify the published image's build date moved and trivy CRITICAL count
   dropped from 51 to ~0-1 (npm's bundled `tar` may survive; the real fix is
   not shipping node/npm in the production stage at all — follow-up).
5. Roll development, health-gate, then production.
