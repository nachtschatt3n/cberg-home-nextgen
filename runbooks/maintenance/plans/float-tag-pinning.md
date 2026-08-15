---
plan_id: float-tag-pinning
component: multiple
pr: null                              # No Renovate PR is possible — that IS the defect.
                                      # Renovate's helm-values manager diffs a version-shaped
                                      # tag; a floating tag never changes, so it never emits
                                      # a PR and the image ages invisibly.
kind: config
current: "17 images on floating tags (latest / main / stable / variant-only)"
target: "each pinned to a concrete version or digest, so drift becomes visible"
update_type: security
risk: medium                          # Not from any single pin — from the number of distinct
                                      # apps touched, several stateful. Per-app the risk is low.
est_duration_min: 45                  # per batch, NOT for all 17 — see §2
needs_reboot: false
window: null                          # DELIBERATE: this is a batched programme, not one window.
                                      # See §2 — batches attach to existing windows as filler.
status: draft
security_ref: F-c58dd98e              # class reference; per-image detail lives in the ops DB
touches:
  namespaces: [ai, databases, download, home-automation, media, office]
  resources:
    - multiple HelmReleases and Deployments across the namespaces above
---

# Pin floating image tags

## 1. Why this is a security finding, not tidiness

A floating tag means **the CVE posture is unknowable**. Upstream re-publishes the
same tag in place, so the bytes running in this cluster can change with no
manifest edit, no Flux event, no Renovate PR and no diff. Every audit answer
about these images is a statement about whatever happened to be pulled last.

Two consequences already observed here:

- **Renovate is structurally silent.** Its `helm-values` manager needs a
  version-shaped tag to diff. A floating tag produces no PR ever, so these
  images were absent from every update report — not "up to date", *absent*.
- **The sweep scored them as accepted.** Until 2026-08-15 (`74ec0a9b`) the CVE
  logic conflated "no newer tag exists" with "acceptable", so floating tags were
  auto-absorbed into AR-029. That fix is what made these 17 visible; this plan
  is the remediation.

A reschedule onto a node with a cold cache is enough to change the running
bytes. That is the actual exposure: not a known CVE, but an unbounded and
unobservable one.

## 2. Why this is batched, and NOT one window

17 images across 6 namespaces including stateful services. Doing them together
means one window where a failure could come from any of 17 unrelated apps, and
a rollback that has to reason about all of them at once. Instead:

**Batch A — trivially safe (no state, no data path).** `busybox:latest`,
`busybox:stable`, `node:22-bookworm`, and the devcontainer image. These are
init/util containers; pinning is a text change with a pod restart.

**Batch B — stateless apps.** `paperless-ai`, `paperless-gpt`, `trmnl-ha`,
`hermes-agent`, `paperclip`, `actual-server`, `nocodb`, `makemkv`, `scrypted`.
Pin to the current running digest first, *then* raise to the newest release as a
separate step — conflating "stop drifting" with "upgrade" is what makes these
risky. `scrypted` and `makemkv` carry user configuration; snapshot first.

**Batch C — datastores. Do NOT batch these with anything.** `pgvector:pg16`
(a major-version alias, not a version), `phpmyadmin:latest`,
`bitnamilegacy/mariadb:latest`, `bitnamilegacy/redis:latest`. The two
`bitnamilegacy` entries are **already owned** by the bitnamilegacy-exit plans —
do not touch them here; pinning a deprecated-namespace image is wasted work when
the plan is to leave that namespace entirely.

Attach A and B to existing windows as filler where capacity allows. C follows
its own plans.

## 3. The trap that decides pin style

**Check what the registry actually publishes before choosing a pin.** Bitnami
has withdrawn semver tags on several image repos — `bitnami/mariadb` publishes
394 tags of which exactly two are non-digest; `bitnami/mongodb` the same. Where
no semver tag exists, a **digest** is the only pin available.

A digest pin is correct but has a cost that must be recorded: Renovate's
`helm-values` manager matches nothing on a `digest:`-only block, so the image
becomes invisible to update tooling in a *different* way. Any digest pin needs
an accepted-risk entry with a review date. See `mariadb-27` for the worked
example.

## 4. Steps (per batch)

1. For each image, resolve the **currently running digest** from the live pod —
   that is the known-good state and the pin target for step 2.
2. Pin to that digest (or to the equivalent concrete semver tag if one exists
   and resolves to the same digest). This is a **no-op deploy by design**: the
   bytes do not change, only their addressability. Verify the pod does not
   change image ID.
3. Only then, as a separate commit, raise to the newest release — with the
   normal per-app verification.
4. Reconcile Kustomization then HelmRelease. Verify the **live** object; a
   values pin at the wrong path silently no-ops while the HelmRelease still
   reports Ready (six occurrences in one week).

## 5. Verification

- `kubectl get pod -o jsonpath='{..imageID}'` unchanged after step 2 — proving
  the pin captured what was already running rather than moving it.
- The app serves (not merely Ready).
- After the batch: the sweep's floating-tag finding count drops by exactly the
  number pinned. If it does not, the pin landed at the wrong values path.

## 6. Rollback

Per image, `git revert` the pin — it restores the floating tag, which is the
pre-existing state. Because step 2 is byte-identical by construction, rollback
carries no data risk. Step 3 (the version raise) rolls back per the app's own
constraints; for datastores that means a dump, not a manifest revert.
