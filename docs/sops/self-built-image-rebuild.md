# SOP: Self-Built Image CVE Rebuild (first-party `ghcr.io/nachtschatt3n/*`)

> Description: How to clear CVEs on container images we build ourselves, where there is
> no upstream version to bump to and remediation is a **rebuild in the source repo**
> followed by a GitOps tag bump — not a version bump.
> Version: `2026.08.18`
> Last Updated: `2026-08-18`
> Owner: `homelab-operator`

---

## 1) Description

Most cluster images are third-party: a CVE is cleared by bumping to a newer upstream
tag, and `runbooks/check-all-versions.py` finds that tag for us. **First-party images
have no upstream.** The newest tag *is* ours, so the version checker reports
"Could not determine" and the auto-updater has nothing to apply. The only remediation
is to rebuild the image in its source repository, publish a new tag, and then bump the
HelmRelease.

This is a distinct workflow with traps that are not derivable from the cluster repo,
because the fix lives in a *different* repo. It has recurred (absenty 2026-08-14,
ha-ai-harness 2026-08-15) and will recur on every first-party image as its base drifts.

- Scope: every `ghcr.io/nachtschatt3n/*` image referenced by a HelmRelease in
  `kubernetes/apps/**`. The REBUILD lane is decided on the **image repository**
  (`SELF_BUILT_REPO_PREFIXES` / `_is_self_built_repo()` in `runbooks/coverage.py`),
  NOT on the app name; the `SELF_BUILT` component set is only a fallback for rows
  whose image repo the version report does not carry. Adding an app name to
  `SELF_BUILT` because it *hosts* third-party images is the over-capture bug
  F-62007db7 (paperclip owns no self-built image).
- Prerequisites: push access to the source repo, `gh auth token` (GHCR read for trivy),
  `mise exec -- trivy`, `kubectl`, `flux`.
- Out of scope: third-party image bumps (`docs/sops/application-update.md`), chart
  bumps, and framework-major toolchain upgrades — those get their own window plan.

---

## 2) Overview

| Setting | Value |
|---------|-------|
| Namespace | varies (the app's own) |
| Source of truth (cluster) | `kubernetes/apps/{ns}/{app}/app/helmrelease.yaml` |
| Source of truth (image) | the app's own GitHub repo under `nachtschatt3n/` |
| Self-built inventory | `runbooks/coverage.py` → `SELF_BUILT_REPO_PREFIXES` (image-matched); `SELF_BUILT` = component fallback |
| Coverage lane | `REBUILD` (see `docs/sops/maintenance-windows.md` §lanes) |
| Critical dependency | GHCR auth — trivy cannot scan these images without a token |

Known first-party images and their source repos (extend as they are added):

| Image | Source repo |
|-------|-------------|
| `ghcr.io/nachtschatt3n/harness-home-server` | `nachtschatt3n/ha-ai-harrnes` (repo name is misspelled upstream) |
| `ghcr.io/nachtschatt3n/harness-home-frontend` | `nachtschatt3n/ha-ai-harrnes` |
| `ghcr.io/nachtschatt3n/absenty` | `nachtschatt3n/absenty` |
| `ghcr.io/nachtschatt3n/ai-sre` | `nachtschatt3n/ai-sre` |
| `ghcr.io/nachtschatt3n/sure` | `nachtschatt3n/sure` |
| `ghcr.io/nachtschatt3n/arag-web` | `nachtschatt3n/arag-web` |
| `ghcr.io/nachtschatt3n/sweep-dashboard` | `nachtschatt3n/sweep-dashboard` |

---

## 3) Blueprints

N/A — there is no blueprint. The declarative artifacts are:

- Cluster side: the `tag:` field(s) in
  `kubernetes/apps/{ns}/{app}/app/helmrelease.yaml`
- Image side: the `Dockerfile` and release workflow in the source repo

```yaml
# The only cluster-side change a rebuild produces:
containers:
  app:
    image:
      repository: ghcr.io/nachtschatt3n/harness-home-server
      tag: 0.5.3-alpha            # was 0.5.1-alpha
```

---

## 4) Operational Instructions

### Rule 0 — the six traps

These are the mistakes this SOP exists to prevent. Read them before starting.

1. **Base drift is usually the whole finding.** Self-built images pin a *floating*
   base (`node:22-alpine`, `python:3.12-slim`, `debian:13`). The image is only as
   fresh as its last build — both ha-ai-harness images were built 2026-04-12 and had
   accumulated an openssl critical purely from sitting still. **Check the base
   first**, before chasing individual dependencies. The single largest first-party
   finding to date (F-c58dd98e) was the same shape.
2. **A merged PR does NOT rebuild a semver-tagged image.** The recurring trap. After
   the rebuild, verify the *published build date* moved, not just that the tag exists.
3. **`npm ci` does not touch the base image's GLOBAL npm.** A `tar` critical
   bundled inside npm itself survived `npm ci` on the harness frontend. The fix is
   an explicit `npm install -g npm@<fixed>` **after** `npm ci` in the Dockerfile.
4. **A source-repo tag may never have published an image.** ha-ai-harness `v0.5.2-alpha`
   exists as a git tag but its build failed in the test job, so no image was pushed.
   Always confirm the tag resolves in GHCR before bumping the HelmRelease — a bump to
   a non-existent tag is an `ImagePullBackOff`, not a CVE fix.
5. **Before escalating a survivor to a framework major, establish who actually
   pins it.** A rebuild cannot fix a toolchain-pinned transitive binary — but a
   binary vendored into a build tool is only *framework*-pinned if the framework's
   own dependency range is what blocks the fix. Check in order:
   (a) is it a **direct** dependency? (`npm ls <pkg>` — if so, bump it and let npm
   dedupe the nested copies); (b) is the framework **on the build path at all**, or
   only a test-runner dep?; (c) what version are we *actually* on? Only when the
   constraint genuinely originates in the framework's range does this become a
   framework major — then **stop** and split it into its own maintenance-window
   plan rather than stretching the rebuild's risk envelope.
   Real framework pin: `runbooks/maintenance/plans/harness-frontend-vite7.md`
   (F-9f752afd — vite 6 genuinely pins `esbuild ^0.25.0`). Counter-example that
   looked identical and wasn't: commit `8882e3eb`, where the app was already on
   vite 7, did not build with vite at all (plain `npx esbuild`; vite was only a
   vitest dep), and carried esbuild as a direct devDependency — a one-line bump,
   not a framework major. Skipping this check cost a 45-minute windowed plan for
   work that needed no vite change.

   **Verify a bundler bump by its artifacts, not its exit code.** A bundler change
   fails silently as a *different bundle*, not a failed build — diff the emitted
   artifacts against a pre-bump baseline (in `8882e3eb`: five artifacts within
   0.1%, `application.css` byte-identical).

6. **The ImagePolicy may be unable to select your rebuild.** Rebuilding is only
   half the job when the image is delivered by Flux image automation: if the
   policy cannot *see* the new tag, a perfect rebuild is discarded silently and
   nothing anywhere reports a problem. Three distinct mistakes, all found
   together on absenty (F-c58dd98e), all of which survived for ten months:

   a. **`policy.alphabetical` over bare git shas is not a time order.** Sorting
      `sha-<7 hex>` alphabetically selects the highest *hex string*, so
      selection pins itself to whichever sha happened to start with `ff` and
      never moves again — 0 of 338 tags were selectable, and a fresh sha had
      roughly a 0.2% chance of ever displacing the incumbent. Publish a
      **branch-prefixed, fixed-width timestamp** (`production-<YYYYMMDDHHMMSS>`)
      and select it with `filterTags.extract` + `policy.numerical`.

   b. **Anchor `filterTags.pattern` with `^...$` — this is load-bearing, not
      style.** Flux matches the pattern unanchored. absenty's package contains
      18 tags shaped `sha-20060102150405-<sha>` (a `docker/metadata-action`
      bug: it does not expand Go date layouts inside `type=raw`, so the layout
      string was published literally). Unanchored, those contain a 14-digit run
      that `(?P<ts>\d{14})` happily extracts. Anchoring is the only thing that
      excludes them.

   c. **Fix tag provenance BEFORE unsuspending automation.** Check what the
      source repo publishes on a `pull_request` event. `github.ref` is
      `refs/pull/N/merge` there, so a workflow branching on `github.ref` falls
      through to its default path — absenty's published the **dev** stage of
      unreviewed branch code under a bare `sha-<hex>` tag, the exact shape the
      *production* policy selected on. With automation armed, a pull request
      could have deployed unreviewed code to an externally-exposed ingress.
      Require that image publishing is gated on `github.event_name == 'push'`
      **and** an explicit release-branch ref check, and that every published
      tag is branch-prefixed so the two environments cannot collide.

   Verify selection with `.status.latestRef.tag`, never with a Ready condition:

   ```bash
   kubectl get imagepolicy <app> -n <ns> -o jsonpath='{.status.latestRef.tag}'
   ```

   And note that **a suspended Flux object still reports `READY=True`** — `flux
   get` will not tell you that automation is off. Check `.spec.suspend`
   directly:

   ```bash
   kubectl get imageupdateautomation <name> -n <ns> -o jsonpath='{.spec.suspend}'
   ```

### Steps

1. **Scan the currently-deployed tag, authenticated.**

   ```bash
   export TRIVY_USERNAME=nachtschatt3n TRIVY_PASSWORD="$(gh auth token)"
   mise exec -- trivy image ghcr.io/nachtschatt3n/<image>:<current-tag> \
     --severity CRITICAL --ignore-unfixed
   ```

   Note the `Image created` date in the report header — that is the drift clock.

2. **Attribute the findings.** Group by the package source. OS packages
   (`openssl`, `zlib`, `busybox`) ⇒ base drift. Language packages
   (`node_modules/...`, `site-packages/...`) ⇒ dependency bump. A single binary with
   a `stdlib` finding ⇒ trap 5, likely out of scope.

3. **Fix in the source repo**: move the base tag forward, bump the offending
   dependencies, and add any explicit global-tool upgrade (trap 3). Commit, tag, push.

4. **Rebuild and verify the build date moved** (trap 2):

   ```bash
   mise exec -- trivy image ghcr.io/nachtschatt3n/<image>:<new-tag> \
     --severity CRITICAL --ignore-unfixed | head -20
   # 'Image created' MUST be today-ish. If it is the old date, the workflow
   # re-tagged a cached image instead of rebuilding.
   ```

5. **GitOps bump** the HelmRelease tag(s) and push. Do not edit the cluster.

   ```bash
   # edit kubernetes/apps/{ns}/{app}/app/helmrelease.yaml -> tag: <new-tag>
   git add kubernetes/apps/{ns}/{app}/app/helmrelease.yaml
   git commit -m "fix(<app>): rebuild image to clear CRITICAL CVEs (<old> -> <new>)"
   git push
   ```

   The commit message must record which CVEs cleared, which survived, and why — that
   is the only durable record once the plan file is deleted.

6. **Delete the plan** (if this ran from a maintenance-window plan) per the transient-plan
   convention in `docs/sops/maintenance-windows.md`, and file a follow-up plan for any
   survivor.

---

## 5) Examples

### Example A: base-drift rebuild (ha-ai-harness, 2026-08-15, commit `fb821821`)

```bash
export TRIVY_USERNAME=nachtschatt3n TRIVY_PASSWORD="$(gh auth token)"
mise exec -- trivy image ghcr.io/nachtschatt3n/harness-home-server:0.5.1-alpha \
  --severity CRITICAL --ignore-unfixed
# Image created: 2026-04-12  -> N fixable CRITICAL, debian 13.4  (record N on the finding)

# after rebuild in nachtschatt3n/ha-ai-harrnes (debian 13.4 -> 13.6,
# alpine 3.23.3 -> 3.24.1, npm -> 11.19.0 after npm ci, vitest 3.2.4 -> 3.2.7)
mise exec -- trivy image ghcr.io/nachtschatt3n/harness-home-server:0.5.3-alpha \
  --severity CRITICAL --ignore-unfixed
# Image created: 2026-08-14  -> 0 fixable CRITICAL   (a ZERO is safe to state)
```

Outcome: both images dropped to a residual the rebuild could not reach; the
survivor was trap 5 and became its own plan (F-9f752afd). **Record the actual
before/after counts on the finding record, not in this SOP** — see
`docs/sops/vulnerability-disclosure.md`.

### Example B: the tag exists but the image does not (trap 4)

```bash
mise exec -- crane manifest ghcr.io/nachtschatt3n/harness-home-frontend:0.5.2-alpha
# MANIFEST_UNKNOWN -> the git tag published no image; do NOT bump to it.
# Skip to the next tag that resolves.
```

---

## 6) Verification Tests

### Test 1: the published image is actually new

```bash
export TRIVY_USERNAME=nachtschatt3n TRIVY_PASSWORD="$(gh auth token)"
mise exec -- trivy image ghcr.io/nachtschatt3n/<image>:<new-tag> \
  --severity CRITICAL --ignore-unfixed
```

Expected:
- `Image created` is the rebuild date, and the CRITICAL count dropped as intended.

If failed:
- Same count as before ⇒ the base did not actually move; re-check the `FROM` line.
- Same `Image created` ⇒ the workflow re-tagged a cached image; force a no-cache build.

### Test 2: the cluster is running the new tag

```bash
kubectl -n <ns> get deploy -l app.kubernetes.io/name=<app> \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.template.spec.containers[*].image}{"\n"}{end}'
flux -n <ns> get helmrelease <app>
```

Expected:
- Every container image shows `<new-tag>`; HelmRelease `Ready=True`.

If failed:
- `ImagePullBackOff` ⇒ trap 4, the tag never published. Revert the bump.
- Old tag still live ⇒ Flux has not reconciled, or image-automation did not roll it
  (check the Deployment, not the automation object).

---

## 7) Troubleshooting

| Symptom | Likely Cause | First Fix |
|---------|--------------|-----------|
| trivy: `UNAUTHORIZED` / no results for a `nachtschatt3n/*` image | GHCR needs a token; the image is private | `export TRIVY_USERNAME=nachtschatt3n TRIVY_PASSWORD="$(gh auth token)"` |
| version-check shows `Latest Tag: Could not determine` | Expected — there is no upstream | Not a bug; this image belongs to the REBUILD lane |
| CVE count unchanged after rebuild | Base image tag not moved, or build cache reused | Check the `FROM` line and `Image created` |
| npm/tar CVE survives `npm ci` | Trap 3 — the base's *global* npm is the carrier | `npm install -g npm@<fixed>` after `npm ci` |
| `ImagePullBackOff` right after the bump | Trap 4 — git tag published no image | Revert the HelmRelease tag, pick a tag that resolves |
| A single `stdlib` finding in one binary | Trap 5 — toolchain-pinned | Do not stretch the rebuild; file a follow-up plan |

```bash
# Which first-party images are deployed, and at what tag
kubectl get deploy -A -o jsonpath='{range .items[*]}{.metadata.namespace}{"\t"}{.metadata.name}{"\t"}{.spec.template.spec.containers[*].image}{"\n"}{end}' \
  | grep nachtschatt3n
```

---

## 8) Diagnose Examples

### Diagnose Example 1: "the CVE is still there after we rebuilt"

```bash
export TRIVY_USERNAME=nachtschatt3n TRIVY_PASSWORD="$(gh auth token)"
mise exec -- trivy image ghcr.io/nachtschatt3n/<image>:<new-tag> \
  --severity CRITICAL --ignore-unfixed --format json \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('Metadata',{}).get('ImageConfig',{}).get('created')); [print(r['Target'], len(r.get('Vulnerabilities') or [])) for r in d.get('Results') or []]"
```

Expected:
- `created` is the rebuild date. If it is the OLD date, the tag was moved without a
  real build — that is trap 2 and the root cause.

If unclear:
- Compare the `Target` lines old-vs-new. If the OS layer target changed but the
  finding persists, it is a language dependency, not the base.

### Diagnose Example 2: "which of our own images are rotting?"

```bash
export TRIVY_USERNAME=nachtschatt3n TRIVY_PASSWORD="$(gh auth token)"
for img in $(kubectl get deploy -A -o jsonpath='{range .items[*]}{.spec.template.spec.containers[*].image}{"\n"}{end}' | grep nachtschatt3n | sort -u); do
  echo "== $img"
  mise exec -- trivy image "$img" --severity CRITICAL --ignore-unfixed --quiet 2>/dev/null | head -5
done
```

Expected:
- Any image whose `Image created` is more than ~60 days old is a rebuild candidate
  regardless of its current CVE count — the base has moved underneath it.

If unclear:
- No output at all ⇒ auth problem, not a clean result. See
  `docs/sops/audit-script-correctness.md` — never score a non-result as a result.

---

## 9) Health Check

```bash
# 1) All first-party workloads healthy on their current tags
kubectl get pods -A -o wide | grep -E 'CrashLoop|ImagePull|Error'

# 2) Every first-party image younger than the drift threshold
export TRIVY_USERNAME=nachtschatt3n TRIVY_PASSWORD="$(gh auth token)"
# (run Diagnose Example 2)

# 3) Coverage lanes have no CRACK
python3 runbooks/coverage.py
```

Expected:
- No `ImagePullBackOff`/`CrashLoop` on a first-party workload.
- No first-party image older than ~60 days without an open plan.
- `coverage.py` reports zero CRACK entries.

---

## 10) Security Check

```bash
python3 runbooks/security-check.py 2>&1 | grep -i -A3 nachtschatt3n
git log --oneline -5 -- kubernetes/apps/{ns}/{app}/app/helmrelease.yaml
```

Expected:
- No plaintext secrets introduced (the rebuild touches only a tag).
- The image bump landed via a git commit, not a live-cluster edit.
- Remaining CRITICALs on the image are all either unfixable or covered by an open
  plan under `runbooks/maintenance/plans/`.

---

## 11) Rollback Plan

The old tag stays in GHCR, so rollback is a pure revert — no data migration is involved.

```bash
git revert <bump-commit>
git push
flux -n <ns> reconcile helmrelease <app> --with-source
kubectl -n <ns> rollout status deploy/<app>
```

If Flux is slow or the revert must be immediate, revert in git first and only then
reconcile — never patch the Deployment directly (GitOps rule).

---

## 12) References

- `docs/sops/application-update.md` — third-party version bumps
- `docs/sops/maintenance-windows.md` — the REBUILD lane and the transient-plan convention
- `docs/sops/audit-script-correctness.md` — do not score an auth failure as "clean"
- `docs/sops/flux-image-automation-push-auth.md` — **why a rebuilt image may never
  reach the cluster**: `ImageUpdateAutomation` can scan, resolve the new tag, and run
  on schedule while pushing nothing, if its GitRepository has no write credential.
  Check `lastPushCommit` before assuming a published tag was rolled out.
- `docs/sops/vulnerability-disclosure.md` — **read before writing any CVE detail into a committed file**
- `runbooks/coverage.py` — image-matched REBUILD lane (`SELF_BUILT_REPO_PREFIXES`), `SELF_BUILT` fallback set
- `runbooks/maintenance/plans/harness-frontend-vite7.md` — worked example of trap 5
- Commits: `fb821821` (harness rebuild), `10adb8d6` (absenty plan),
  `1e160d5e` (GHCR token for trivy — the scan blind spot that hid all of this)

---

## Version History

- `2026.08.15`: Initial SOP, extracted from the ha-ai-harness rebuild (`fb821821`) and
  the absenty rebuild plan, which were the only written record of the five traps.
