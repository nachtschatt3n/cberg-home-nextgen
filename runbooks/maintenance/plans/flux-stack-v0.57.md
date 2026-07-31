---
plan_id: flux-stack-v0.57
component: flux-stack
pr: null                            # Renovate "Flux Operator" group PR (bumps the
                                    # flux-operator + flux-instance charts 0.14.0 →
                                    # 0.57.0). No open PR found at plan time; the
                                    # distribution.version bump is NOT Renovate-tracked
                                    # (no annotation on that line) and is a MANUAL edit.
kind: chart
current: "flux-operator 0.14.0 / distribution v2.5.0"
target: "flux-operator 0.57.0 / distribution v2.9.3"
update_type: major
risk: high                          # the GitOps control plane; a bad upgrade can
                                    # break the very ability to reconcile/recover, and
                                    # Flux can roll ITSELF back mid-flight. 43-minor
                                    # operator span + 4-minor distribution span +
                                    # image-API GA (0.x → 1.x major) in one coordinated
                                    # move.
est_duration_min: 60
needs_reboot: false                 # no node reboot — but operator-present window ONLY
touches:
  namespaces:
    - flux-system                   # primary: operator, FluxInstance, all 6 controllers
    - my-software-production         # absenty ImageRepository/ImagePolicy/ImageUpdateAutomation
    - my-software-development        # absenty (dev) image-automation objects
    - "*"                            # effective: every namespace's reconcile path runs
                                    #   through the controllers being upgraded
  resources:
    - helmrelease/flux-operator
    - helmrelease/flux-instance
    - fluxinstance/flux
    - deploy/source-controller
    - deploy/kustomize-controller
    - deploy/helm-controller         # v1.2.0 → v1.6.3 — NOT in the CVE ticket's list,
                                    #   but moves with the distribution and reconciles
                                    #   ~90 HelmReleases (hidden blast radius)
    - deploy/notification-controller # also serves the github webhook Receiver
    - deploy/image-reflector-controller
    - deploy/image-automation-controller
    - crd/fluxinstances.fluxcd.controlplane.io
    - crd/{git,helm,ocirepositories}.source.toolkit.fluxcd.io
    - crd/imagerepositories,imagepolicies,imageupdateautomations.image.toolkit.fluxcd.io
  shared: [flux]                    # THE GitOps reconcile engine. Every app in the
                                    # cluster is reconciled by these controllers → a
                                    # degraded upgrade blocks every other change. Treat
                                    # as the highest-order shared infra.
depends_on: []
conflicts_with:
  - talos-v1.13.7                   # do NOT co-schedule: a rolling node reboot bounces
                                    # the flux-system controller pods; compounding a
                                    # control-plane image upgrade with a control-plane
                                    # reboot is unacceptable. (talos-v1.13.7 is targeted
                                    # sun-window:2026-08-02 — put this in a DIFFERENT
                                    # sun window, or run it first + fully verified.)
status: scheduled
window: "sun-window:2026-08-09"
                                    # operator-present, reboot-capable slot (sun-window)
                                    # ONLY — never the unattended tue/thu 05:00 slots.
                                    # This plan must run FIRST + Ready-verified before
                                    # any other plan shares its window (see §6).
auto_execute: false                 # risk:high → always operator go/no-go
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/maintenance-windows.md
  - docs/sops/disaster-recovery.md
generated: "2026-07-31"
---

# Flux stack — operator 0.14.0 → 0.57.0 + distribution v2.5.0 → v2.9.3

## 1. Summary & why held

**What changes (one coordinated move — the six controllers do NOT move on their
own).** In this repo the Flux controllers are **not** individually pinned. They
are provisioned by the **flux-operator** from a single `FluxInstance` CR, whose
`spec.distribution.version` (`kubernetes/apps/flux-system/flux-operator/instance/helm-values.yaml`)
is pinned to **`v2.5.0`**. That distribution is exactly what installs today's
controller set (confirmed live: `fluxinstance/flux` READY at `v2.5.0`):

| Controller | Now (dist v2.5.0) | Target (dist v2.9.3) |
|---|---|---|
| source-controller | v1.5.0 | v1.9.3 |
| kustomize-controller | v1.5.0 | v1.9.4 |
| helm-controller | **v1.2.0** | **v1.6.3** (not in the CVE ticket, moves anyway) |
| notification-controller | v1.5.0 | v1.9.2 |
| image-reflector-controller | v0.34.0 | v1.2.3 (**major, API GA**) |
| image-automation-controller | v0.40.0 | v1.2.3 (**major, API GA**) |

So the CVE fix is achieved by **two** git edits, not one:
1. **chart bump** `flux-operator` + `flux-instance` HelmReleases `0.14.0 → 0.57.0`
   (the Renovate "Flux Operator" group PR — `.github/renovate.json5` groups
   `flux-operator`/`flux-instance`).
2. **distribution bump** `distribution.version: v2.5.0 → v2.9.3` in
   `instance/helm-values.yaml` — **MANUAL**; that line carries no Renovate
   annotation, so merging the chart PR alone would upgrade the *operator* while
   leaving all six controllers on v1.5.0/v0.x and delivering **none** of the
   controller CVE reduction. Both edits must land together.

**Why it was held (gate: G1 type = major; and correctly so).** This is the
GitOps control plane. The controllers being upgraded are the same ones that
reconcile this very change (kustomize-controller applies the FluxInstance edit;
helm-controller upgrades the flux-operator chart; the operator then re-rolls
kustomize/helm/source-controller underneath the in-flight reconcile). Both
HelmReleases carry `upgrade.remediation.strategy: rollback` — **Flux can roll
itself back mid-upgrade**, which on a bad attempt produces a half-migrated,
flapping control plane. A failure here can remove the ability to reconcile or
recover *through Flux at all* — hence `risk: high` and the Flux-independent,
`kubectl`/`helm`-only rollback in §5.

**Upstream evidence — the real breaking change is the image-API GA at Flux 2.7**
(in the 2.5→2.9 span), [Flux 2.7 GA notes](https://fluxcd.io/blog/2025/09/flux-v2.7.0/):
- **`ImageRepository`, `ImagePolicy`, `ImageUpdateAutomation` promoted to stable
  `image.toolkit.fluxcd.io/v1`** (this is why the image controllers go 0.x → 1.x).
- image-reflector-controller **removed the deprecated autologin flags** — cloud
  auth must use `ImageRepository.spec.provider`.
- ImageUpdateAutomation **removed the deprecated commit-template fields**
  `.Updated` and `.Changed.ImageResult` — use `.Changed.FileChanges` /
  `.Changed.Objects` / `.Changed.Changes`.
- Five **v1beta1** APIs reached EOL and were removed: `source…/v1beta1`,
  `kustomize…/v1beta1`, `helm…/v2beta1`, `image…/v1beta1`, `notification…/v1beta1`.

**How much of that actually bites THIS repo — audited, and it is small:**
- Deprecated **v1beta1 APIs: none in the repo.** All Flux resources use
  `…toolkit.fluxcd.io/v1` (173×) or `/v2` (105×). The only pre-GA apiVersion in
  use is `image.toolkit.fluxcd.io/**v1beta2**` (6 objects, see below), and
  **v1beta2 is *not* in the EOL list** (only v1beta1 was removed at 2.7) — so it
  is still served at v2.9.3. The five-API removal does **not** affect us.
- **image-automation objects: 2 files, 6 objects** — `absenty` prod + dev
  (`kubernetes/apps/my-software-{production,development}/absenty/app/image-automation.yaml`),
  all `image.toolkit.fluxcd.io/v1beta2`. Audited against the two field/flag
  removals and **neither bites**: the `ImageRepository` already uses an explicit
  `secretRef: ghcr-secret` (not autologin), and the `ImageUpdateAutomation`
  commit template already uses the **new** `.Changed.FileChanges` /
  `.Changed.Objects` fields. The only migration is the cosmetic apiVersion bump
  `v1beta2 → v1`, done as a *follow-up* step §3d (deliberately decoupled from the
  risky core so the v1 CRD is provably served first).
- `kubernetes/apps/ai/ai-sre/app/rbac.yaml` grants read on
  `image.toolkit.fluxcd.io` **by apiGroup + resource name** — version-agnostic,
  **no change needed**.

This is **not** a false-positive hold: the resource-level exposure is small, but
the *mechanism* (self-upgrading control plane, self-rollback, 43-minor operator
span, image-API major) is exactly what a high-risk attended window exists for.

**flux-operator 0.14.0 → 0.57.0 caveats** ([operator releases](https://github.com/controlplaneio-fluxcd/flux-operator/releases)):
- v0.57.0 adds *"defense in depth: input validation, resource caps, stricter
  defaults"* — the operator now **validates the FluxInstance more strictly**. Our
  FluxInstance is minimal (networkPolicy:false, distribution.version, the 6
  components, git sync) and should pass, but a rejected/invalid FluxInstance is a
  named failure mode to watch (§4).
- The operator ships/owns the `FluxInstance` CRD (+ ResourceSet CRDs). CRD schema
  moved across this span; the chart must update the CRD **before** the new
  FluxInstance schema is applied. Ordering is already enforced in-repo:
  `flux-instance` HelmRelease `dependsOn: flux-operator` (`instance/helmrelease.yaml`).

## 2. Pre-checks

Run from repo root (`cd /Users/mu/code/cberg-home-nextgen`). **All must pass; any
failure → stop and surface.** This is `docs/sops/application-update.md` §Attended
tier applied to the control plane.

```bash
# 2.1 Both HelmReleases + the FluxInstance are Ready at the expected OLD versions
mise exec -- kubectl -n flux-system get hr flux-operator flux-instance \
  -o custom-columns='NAME:.metadata.name,READY:.status.conditions[?(@.type=="Ready")].status,VER:.status.history[0].chartVersion'
# Expected: both Ready=True, chartVersion 0.14.0
mise exec -- kubectl -n flux-system get fluxinstance flux \
  -o custom-columns='READY:.status.conditions[?(@.type=="Ready")].status,REV:.status.lastAppliedRevision'
# Expected: Ready=True, REV v2.5.0

# 2.2 The ENTIRE cluster is Ready (this upgrade will freeze reconcile briefly —
#     do not start on top of an already-broken reconcile)
mise exec -- flux get kustomizations -A | grep -vE "True|^NAMESPACE"   # must be empty
mise exec -- flux get helmreleases   -A | grep -vE "True|^NAMESPACE"   # must be empty

# 2.3 SNAPSHOT the exact known-good controller + operator images (BY DIGEST) to a
#     file — this is the out-of-band rollback source of truth (§5). Save it OUTSIDE
#     the repo so a bad `git revert` can't touch it.
mise exec -- kubectl -n flux-system get deploy \
  flux-operator source-controller kustomize-controller helm-controller \
  notification-controller image-reflector-controller image-automation-controller \
  -o jsonpath='{range .items[*]}{.metadata.name}{"  "}{.spec.template.spec.containers[0].image}{"\n"}{end}' \
  | tee /tmp/flux-known-good-images.txt
# Confirmed at plan time (2026-07-31): flux-operator v0.14.0, helm-controller v1.2.0,
# source/kustomize/notification-controller v1.5.0, image-automation v0.40.0,
# image-reflector v0.34.0 (all digest-pinned).

# 2.4 BACK UP the Flux + flux-operator CRDs (schema changes across the span; a
#     backup lets you re-apply the old CRD if a migration wedges an object)
mise exec -- kubectl get crd -o name \
  | grep -E 'fluxcd\.controlplane\.io|toolkit\.fluxcd\.io' \
  | xargs -I{} sh -c 'mise exec -- kubectl get {} -o yaml' \
  > /tmp/flux-crds-backup-$(date +%Y%m%d).yaml
wc -l /tmp/flux-crds-backup-*.yaml   # sanity: non-empty

# 2.5 Note the current git HEAD (the revert anchor) and the pre-upgrade helm
#     revisions (the helm-CLI rollback anchor)
git -C /Users/mu/code/cberg-home-nextgen rev-parse HEAD | tee /tmp/flux-pre-upgrade-head.txt
mise exec -- helm -n flux-system history flux-operator | tail -3
mise exec -- helm -n flux-system history flux-instance | tail -3
# Record the last DEPLOYED revision number for each (the §5 helm-rollback target).

# 2.6 age key + git push work (recovery depends on both)
mise exec -- sops -d kubernetes/apps/flux-system/flux-operator/instance/git-auth-secret.sops.yaml >/dev/null && echo "age OK"
git -C /Users/mu/code/cberg-home-nextgen ls-remote origin -h refs/heads/main >/dev/null && echo "git push path OK"

# 2.7 Silence flux-system + absenty alert noise for the window (application-update.md §1)
mise exec -- bash -c 'kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 &>/dev/null &
sleep 2
NOW=$(python3 -c "from datetime import *;print(datetime.now(timezone.utc).strftime(\"%Y-%m-%dT%H:%M:%S.000Z\"))")
END=$(python3 -c "from datetime import *;print((datetime.now(timezone.utc)+timedelta(hours=2)).strftime(\"%Y-%m-%dT%H:%M:%S.000Z\"))")
curl -s -X POST localhost:9093/api/v2/silences -H "Content-Type: application/json" -d "{\"matchers\":[{\"name\":\"namespace\",\"value\":\"flux-system|my-software-.*\",\"isRegex\":true,\"isEqual\":true}],\"startsAt\":\"$NOW\",\"endsAt\":\"$END\",\"createdBy\":\"operator\",\"comment\":\"flux stack v0.57/v2.9.3 upgrade — 2h TTL\"}"
kill %1 2>/dev/null'
runbooks/update-marker.sh add flux-stack flux-system 2 "flux 0.14->0.57 / v2.5->v2.9.3"
```

**Go criteria:** both HRs + FluxInstance Ready at old versions; all Ks + HRs
cluster-wide Ready; images + CRDs backed up to `/tmp`; helm revisions recorded;
age + git push verified; silence + marker in place. Any miss → **do not start**.

## 3. Steps

GitOps-first, delegated to `cberg-agent`. **Disable Flux's self-rollback for the
attempt** (the #1 hazard: a slow controller roll trips `remediation` and Flux
half-reverts itself). Land the core bump, let it fully converge and verify, and
only then do the cosmetic image-API migration.

### 3a. Disable self-rollback on both Flux HelmReleases (attended-upgrade guard)

Edit `kubernetes/apps/flux-system/flux-operator/app/helmrelease.yaml` **and**
`…/instance/helmrelease.yaml` — change each `upgrade` block:

```yaml
  upgrade:
    cleanupOnFail: true
    remediation:
      strategy: rollback
      retries: 3
```
→
```yaml
  upgrade:
    cleanupOnFail: false            # keep the failed release inspectable
    remediation:
      retries: 0                    # do NOT auto-rollback mid-migration
      strategy: rollback            # (irrelevant with retries:0; restored in 3e)
```

### 3b. Bump the operator + instance charts, and the distribution

```bash
cd /Users/mu/code/cberg-home-nextgen
# chart 0.14.0 → 0.57.0 in BOTH helmreleases (this is what the Renovate group PR does)
sed -i '' 's/version: 0.14.0/version: 0.57.0/' \
  kubernetes/apps/flux-system/flux-operator/app/helmrelease.yaml \
  kubernetes/apps/flux-system/flux-operator/instance/helmrelease.yaml
# distribution v2.5.0 → v2.9.3 (MANUAL — Renovate does not touch this line)
sed -i '' 's/version: v2.5.0/version: v2.9.3/' \
  kubernetes/apps/flux-system/flux-operator/instance/helm-values.yaml

# Sanity — 3 edits present, nothing else changed
git diff --stat
grep -n 'version:' kubernetes/apps/flux-system/flux-operator/app/helmrelease.yaml \
  kubernetes/apps/flux-system/flux-operator/instance/helmrelease.yaml \
  kubernetes/apps/flux-system/flux-operator/instance/helm-values.yaml
```

### 3c. Commit + push, then DRIVE the reconcile (don't wait passively)

```bash
git add kubernetes/apps/flux-system/flux-operator/
git commit -m "feat(flux): upgrade operator 0.14.0->0.57.0 + distribution v2.5.0->v2.9.3"
git push
```

Then watch, in order (the operator upgrades first, then re-rolls the controllers):

```bash
# i. helm-controller reconciles the flux-operator HR → new operator pod (0.57.0)
mise exec -- flux -n flux-system reconcile hr flux-operator --with-source   # ok to nudge
mise exec -- kubectl -n flux-system rollout status deploy/flux-operator --timeout=5m
mise exec -- kubectl -n flux-system get deploy flux-operator \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'   # …flux-operator:v0.57.0

# ii. flux-instance HR (dependsOn operator) applies the FluxInstance with dist v2.9.3
mise exec -- flux -n flux-system reconcile hr flux-instance --with-source
mise exec -- kubectl -n flux-system get fluxinstance flux \
  -o custom-columns='READY:.status.conditions[?(@.type=="Ready")].status,REV:.status.lastAppliedRevision'
# Expected: Ready=True, REV v2.9.3. If Ready=False with a validation/schema message,
# STOP → this is the "stricter FluxInstance validation" failure mode → §5.

# iii. the operator now rolls all 6 controllers to v2.9.3 — watch them cycle
mise exec -- kubectl -n flux-system rollout status deploy/source-controller --timeout=5m
mise exec -- kubectl -n flux-system rollout status deploy/kustomize-controller --timeout=5m
mise exec -- kubectl -n flux-system rollout status deploy/helm-controller --timeout=5m
mise exec -- kubectl -n flux-system rollout status deploy/notification-controller --timeout=5m
mise exec -- kubectl -n flux-system rollout status deploy/image-reflector-controller --timeout=5m
mise exec -- kubectl -n flux-system rollout status deploy/image-automation-controller --timeout=5m
```

> **If a controller restarts mid-reconcile and a Ks/HR flips to a transient
> `Reconciling`/`Unknown`:** that is expected while source/kustomize-controller
> bounce under themselves. Give it one full interval before treating it as a
> failure. Do NOT `git revert` on the first transient blip.

### 3d. (follow-up, after §4 green) Migrate absenty image-automation v1beta2 → v1

Only after the core upgrade verifies healthy AND the v1 CRD is confirmed served:

```bash
# confirm v1 is a served version of each image CRD (it is, at dist v2.9.3)
mise exec -- kubectl get crd imagerepositories.image.toolkit.fluxcd.io \
  -o jsonpath='{.spec.versions[*].name}{"\n"}'   # must include v1

sed -i '' 's#image.toolkit.fluxcd.io/v1beta2#image.toolkit.fluxcd.io/v1#g' \
  kubernetes/apps/my-software-production/absenty/app/image-automation.yaml \
  kubernetes/apps/my-software-development/absenty/app/image-automation.yaml
git add kubernetes/apps/my-software-*/absenty/app/image-automation.yaml
git commit -m "chore(absenty): migrate image automation to image.toolkit.fluxcd.io/v1 (Flux 2.7 GA)"
git push
mise exec -- flux -n my-software-production reconcile ks cluster-apps --with-source 2>/dev/null || true
mise exec -- kubectl get imagerepository,imagepolicy,imageupdateautomation \
  -n my-software-production; mise exec -- kubectl get imagerepository,imagepolicy,imageupdateautomation \
  -n my-software-development
# Expected: all present + Ready; last-scan/last-run timestamps advance.
```

(The commit templates already use `.Changed.FileChanges`/`.Changed.Objects`, and
`secretRef` not autologin, so no template/auth edits are needed — audited in §1.)

### 3e. Restore self-rollback

Once §4 is fully green, revert the §3a guard (`retries: 3`, `cleanupOnFail: true`,
`strategy: rollback`) on both HelmReleases; commit + push; confirm both HRs stay
Ready. Then drop the silence + clear the marker:

```bash
runbooks/update-marker.sh clear flux-stack
# delete the alertmanager silence early if still open (id from the POST in 2.7)
```

## 4. Verification

```bash
# 4.1 Charts + operator + distribution all at target
mise exec -- kubectl -n flux-system get hr flux-operator flux-instance \
  -o custom-columns='NAME:.metadata.name,READY:.status.conditions[?(@.type=="Ready")].status,VER:.status.history[0].chartVersion'
# Expected: both Ready=True, chartVersion 0.57.0
mise exec -- kubectl -n flux-system get fluxinstance flux \
  -o custom-columns='READY:.status.conditions[?(@.type=="Ready")].status,REV:.status.lastAppliedRevision'
# Expected: Ready=True, REV v2.9.3

# 4.2 Every controller on its target image + Available
mise exec -- kubectl -n flux-system get deploy \
  -o custom-columns='NAME:.metadata.name,IMAGE:.spec.template.spec.containers[0].image,AVAIL:.status.availableReplicas'
# Expected: source v1.9.3, kustomize v1.9.4, helm v1.6.3, notification v1.9.2,
#           image-reflector v1.2.3, image-automation v1.2.3, operator v0.57.0; AVAIL≥1 each

# 4.3 THE decisive test — Flux still reconciles the whole cluster
mise exec -- flux get kustomizations -A | grep -vE "True|^NAMESPACE"   # must be empty
mise exec -- flux get helmreleases   -A | grep -vE "True|^NAMESPACE"   # must be empty
# Force a real end-to-end reconcile to prove the new source+kustomize controllers work
mise exec -- flux -n flux-system reconcile source git flux-system
mise exec -- flux -n flux-system reconcile ks cluster-apps

# 4.4 No crashloop / imagepull in flux-system
mise exec -- kubectl -n flux-system get pods | grep -vE "Running|Completed|^NAME"

# 4.5 Image automation still functions (after 3d): objects Ready, scans advancing
mise exec -- kubectl get imagerepository,imagepolicy,imageupdateautomation -A

# 4.6 A user-facing app still serves through the (Flux-managed) ingress path
mise exec -- kubectl get hr -A | grep -iE 'ingress-nginx|authentik' | grep -i true
# and spot-check an app pod is Running as a proxy for "reconcile did not disturb workloads"

# 4.7 Zero firing alerts once the silence lifts (Watchdog/InfoInhibitor excluded)
mise exec -- bash -c 'kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &>/dev/null &
sleep 2
curl -s http://localhost:9090/api/v1/alerts | python3 -c "
import sys,json
a=[x for x in json.load(sys.stdin)[\"data\"][\"alerts\"] if x[\"state\"]==\"firing\" and x[\"labels\"][\"alertname\"] not in (\"Watchdog\",\"InfoInhibitor\")]
print(f\"Firing: {len(a)}\")"
kill %1 2>/dev/null'
```

**Success = operator v0.57.0, FluxInstance REV v2.9.3 Ready, all 6 controllers on
target images + Available, every Ks + HR cluster-wide Ready, a forced
`cluster-apps` reconcile completes, absenty image objects Ready on `…/v1`, 0
firing alerts.**

## 5. Rollback

Two revert paths. **§3a set `retries:0`, so Flux will NOT auto-rollback** — you
own the decision. Try the GitOps revert first; if Flux itself is too degraded to
reconcile the revert, use the Flux-independent (`kubectl`/`helm`-only) path.

### 5.1 GitOps revert (preferred — use while Flux still reconciles)

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <core-upgrade-sha>            # from /tmp/flux-pre-upgrade-head.txt+1
git revert --no-edit <absenty-migration-sha>       # only if §3d landed
git push
# Nudge the reconcile (operator downgrades → re-rolls controllers to v2.5.0)
mise exec -- flux -n flux-system reconcile hr flux-operator --with-source
mise exec -- flux -n flux-system reconcile hr flux-instance --with-source
```

Confirm restore: FluxInstance REV back to `v2.5.0`, all 6 controllers back to the
digests in `/tmp/flux-known-good-images.txt`, all Ks + HRs Ready (§4.1–4.3).

### 5.2 Out-of-band revert (Flux is degraded — DO NOT rely on reconcile)

`kubectl`, `helm`, and `talosctl` all talk to the kube-apiserver (Talos/etcd),
which is **independent of Flux** — they work even when every Flux controller is
down. Order: stop Flux from fighting you → restore the operator → let it (or you)
restore the controllers.

```bash
# a. Freeze the two Flux HelmReleases so nothing re-applies the bad version.
#    `flux suspend` is just a kubectl patch — works with notification/source down.
for hr in flux-operator flux-instance; do
  mise exec -- kubectl -n flux-system patch hr $hr --type merge -p '{"spec":{"suspend":true}}'
done

# b. Roll the Helm releases back with the helm CLI (NOT helm-controller). Uses the
#    same release-secret storage in flux-system; revisions from Pre-check 2.5.
mise exec -- helm -n flux-system history flux-operator
mise exec -- helm -n flux-system rollback flux-operator <last-0.14.0-rev>
mise exec -- helm -n flux-system history flux-instance
mise exec -- helm -n flux-system rollback flux-instance  <last-0.14.0-rev>

# c. If the operator pod is still bad (0.57.0 crashloop), hard-pin its image
#    directly — the reverted operator then reconciles the FluxInstance back to v2.5.0:
mise exec -- kubectl -n flux-system set image deploy/flux-operator \
  manager=ghcr.io/controlplaneio-fluxcd/flux-operator:v0.14.0
mise exec -- kubectl -n flux-system rollout status deploy/flux-operator --timeout=5m

# d. ABSOLUTE FLOOR — if the operator still won't roll the controllers back, pin
#    each controller Deployment to the exact known-good digest from Pre-check 2.3.
#    This gets a working control plane back so Flux can reconcile again:
#    (read the digests from /tmp/flux-known-good-images.txt)
#      kubectl -n flux-system set image deploy/source-controller     manager=<sc v1.5.0@sha256:…>
#      kubectl -n flux-system set image deploy/kustomize-controller   manager=<kc v1.5.0@sha256:…>
#      kubectl -n flux-system set image deploy/helm-controller        manager=<hc v1.2.0@sha256:…>
#      kubectl -n flux-system set image deploy/notification-controller manager=<nc v1.5.0@sha256:…>
#      kubectl -n flux-system set image deploy/image-reflector-controller   manager=<ir v0.34.0@sha256:…>
#      kubectl -n flux-system set image deploy/image-automation-controller  manager=<ia v0.40.0@sha256:…>
#    Then re-apply the backed-up CRDs ONLY if a v1→v1beta2 schema mismatch blocks
#    the old controllers:  kubectl apply -f /tmp/flux-crds-backup-<date>.yaml

# e. Once a known-good control plane is reconciling: `git revert` the upgrade
#    commit(s) + push (§5.1), then UN-suspend so git == cluster again:
for hr in flux-operator flux-instance; do
  mise exec -- kubectl -n flux-system patch hr $hr --type merge -p '{"spec":{"suspend":false}}'
done
```

**Confirm cluster is back:** FluxInstance REV `v2.5.0` Ready; all 6 controllers on
the `/tmp/flux-known-good-images.txt` digests + Available; `flux get ks -A` and
`flux get hr -A` all Ready; a forced `flux reconcile ks cluster-apps` completes;
0 firing alerts. If even the out-of-band path can't restore Flux, escalate to
`docs/sops/disaster-recovery.md` §4.7 (source-controller cache keeps the cluster
serving on the last good commit while you rebuild the Flux bootstrap).

## 6. Interference notes

- **Operator-present, reboot-capable window ONLY (sun-window).** `needs_reboot`
  is false, but the blast radius (the reconcile engine for the whole cluster,
  self-rollback hazard, Flux-independent recovery that needs a human at a
  terminal) makes this an attended `sun-window` item. It must **never** run in
  the unattended tue/thu 05:00 slots — the maintenance-window SOP defers anything
  above low-risk when the operator is asleep, and an out-of-band rollback here
  cannot be driven by cron. Risk weight 3.
- **Run FIRST and fully verified before any other plan in the window.** Every
  other plan's GitOps apply flows through these controllers — `shared: [flux]` is
  the highest-order shared infra. If the window agent has other plans queued,
  sequence this one first, confirm §4 green (a real `cluster-apps` reconcile
  completes), and only then proceed. If this plan fails, **abort the rest of the
  window** — you cannot trust GitOps until Flux is restored.
- **Do NOT co-schedule with `talos-v1.13.7`** (`conflicts_with`). A rolling node
  reboot bounces the flux-system controller pods; stacking a control-plane image
  upgrade on a control-plane reboot is unacceptable. talos-v1.13.7 targets
  `sun-window:2026-08-02` — put this Flux plan in a **different** sun window.
- **helm-controller moves too (v1.2.0 → v1.6.3) though it's not in the CVE
  ticket.** It reconciles ~90 HelmReleases; treat any post-upgrade HR churn as
  part of this plan's blast radius, not an unrelated incident.
- **notification-controller (v1.5.0 → v1.9.2) also serves the GitHub webhook
  Receiver** (`instance/github/webhooks/`). If fast push-triggered reconciles
  stop after the upgrade, check the Receiver/ingress; the cluster still
  reconciles on the 30m `GitRepository` interval regardless, so it's not
  window-blocking.
- **`prune: false` on both flux-operator Ks is a safety net** — a misfired
  reconcile will not garbage-collect the operator or FluxInstance out from under
  you. Don't "fix" that to `true` during this window.
- **Self-rollback disabled for the attempt (§3a).** The window agent must ensure
  §3e restores `retries: 3` before the window closes — leaving `retries: 0` on
  the Flux HelmReleases removes Flux's own safety net for future reconciles.
- **cberg-agent does the GitOps; the operator drives + gates the reconcile.** The
  file edits/commits are delegated, but the go/no-go at each stage (operator
  healthy → FluxInstance v2.9.3 Ready → controllers rolled → cluster-wide Ready)
  and any rollback decision are operator-in-the-loop.
