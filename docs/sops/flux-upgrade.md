# SOP: Flux Control-Plane Upgrade (flux-operator + distribution)

> Description: How to upgrade the Flux control plane on this cluster — the `flux-operator`/`flux-instance` charts and the `FluxInstance` distribution that provisions the six controllers — as an attended, high-risk operation. Captures the three non-obvious hazards learned on the 2026-08-11 v2.5.0→v2.9.3 upgrade: strict postBuild substitution, the Flux 2.7 image-API GA storage migration, and the coordinated two-edit bump with self-rollback disabled.
> Version: `2026.08.11`
> Last Updated: `2026-08-11`
> Owner: `cberg-agent / operator`

---

## 1) Description

Covers upgrading the GitOps control plane itself: the `flux-operator` + `flux-instance` HelmReleases and the `FluxInstance` `spec.distribution.version` that installs source/kustomize/helm/notification/image-reflector/image-automation controllers. The controllers reconcile this very change, so a bad upgrade can remove the ability to reconcile or recover through Flux.

- Scope: `flux-system` namespace; `kubernetes/apps/flux-system/flux-operator/**`; effectively every namespace (all reconcile through these controllers).
- Prerequisites: operator-present attended window; local SOPS age key; `mise` toolchain; git push path; a Flux-independent (`kubectl`/`helm`) recovery path.
- Out of scope: Talos/node upgrades (see `talos-upgrade.md`); app-level Helm bumps.

---

## 2) Overview

| Setting | Value |
|---------|-------|
| Namespace | `flux-system` |
| Source of truth | `kubernetes/apps/flux-system/flux-operator/instance/helm-values.yaml` (`distribution.version`) + the two `helmrelease.yaml` (`chart.spec.version`) |
| Critical dependency | The reconcile engine for the whole cluster — highest-order shared infra |
| Two edits, one move | chart `flux-operator`+`flux-instance` bump **and** `distribution.version` bump must land together |
| CLI/distribution match | keep `.mise.toml` `fluxcd/flux2` CLI aligned to the running distribution |

The distribution version is **not** Renovate-tracked (no annotation on that line) — it is a manual edit. Bumping only the chart upgrades the operator but leaves all six controllers on the old versions.

---

## 3) Blueprints

- Source of truth file(s):
  - `kubernetes/apps/flux-system/flux-operator/instance/helm-values.yaml` — `instance.distribution.version`
  - `kubernetes/apps/flux-system/flux-operator/app/helmrelease.yaml` — operator chart version + `upgrade.remediation`
  - `kubernetes/apps/flux-system/flux-operator/instance/helmrelease.yaml` — instance chart version (`dependsOn: flux-operator`)
- Ordering is enforced in-repo: `flux-instance` `dependsOn` `flux-operator` so the operator (and its CRDs) update before the new `FluxInstance` schema is applied.

```yaml
# helm-values.yaml (distribution pin — MANUAL bump)
instance:
  distribution:
    version: v2.9.3
```

---

## 4) Operational Instructions

1. **Pre-checks (all must pass; any failure → stop):**
   - Both HRs + `FluxInstance` Ready at the current versions; entire cluster Ready (`flux get ks -A` / `hr -A` show no non-True rows).
   - **Snapshot known-good controller+operator images by digest to `/tmp` (outside the repo):**
     ```bash
     mise exec -- kubectl -n flux-system get deploy flux-operator source-controller kustomize-controller \
       helm-controller notification-controller image-reflector-controller image-automation-controller \
       -o jsonpath='{range .items[*]}{.metadata.name}{"  "}{.spec.template.spec.containers[0].image}{"\n"}{end}' \
       | tee /tmp/flux-known-good-images.txt
     ```
   - **Back up Flux + operator CRDs:** `kubectl get crd -o name | grep -E 'fluxcd\.controlplane\.io|toolkit\.fluxcd\.io' | xargs -I{} sh -c 'mise exec -- kubectl get {} -o yaml' > /tmp/flux-crds-backup-$(date +%Y%m%d).yaml`
   - Record `git rev-parse HEAD` and the last **deployed** helm revisions (`helm -n flux-system history flux-operator|flux-instance`).
   - Confirm age decrypt + git push work. Silence flux-system alerts for the window.
2. **Disable self-rollback for the attempt (§3a guard).** On BOTH HRs set `upgrade.cleanupOnFail: false`, `upgrade.remediation.retries: 0`. This prevents a slow controller roll from tripping remediation into a half-reverted, flapping control plane. Restore afterwards.
3. **Coordinated bump:** chart `0.14.0 → 0.57.0` in both `helmrelease.yaml`, and `distribution.version` in `helm-values.yaml`. Commit + push (scoped `git add` of the flux-operator dir only).
4. **Drive the reconcile in order:** git source → `ks flux-operator` → `hr flux-operator` (watch operator roll to the new tag) → `ks flux-instance` → `hr flux-instance` (operator applies the `FluxInstance`) → watch all six controllers roll.
5. **Handle the image-API GA storage migration if the FluxInstance apply wedges** (see Example B) — this is expected on any 2.5→2.7+ span.
6. **Verify (§6), then restore the self-rollback guard** (`retries: 3`, `cleanupOnFail: true`), commit + push, drop the silence.
7. **Follow-ups:** migrate any `image.toolkit.fluxcd.io/v1beta2` objects to `/v1` once the v1 CRD is served; update `docs/infrastructure.md` + `README.md` version references and `.mise.toml` CLI pin.

---

## 5) Examples

### Example A: Clean coordinated bump

```bash
cd /Users/mu/code/cberg-home-nextgen
sed -i '' 's/version: 0.14.0/version: 0.57.0/' \
  kubernetes/apps/flux-system/flux-operator/app/helmrelease.yaml \
  kubernetes/apps/flux-system/flux-operator/instance/helmrelease.yaml
sed -i '' 's/version: v2.5.0/version: v2.9.3/' \
  kubernetes/apps/flux-system/flux-operator/instance/helm-values.yaml
git add kubernetes/apps/flux-system/flux-operator/
git commit -m "feat(flux): upgrade operator 0.14.0->0.57.0 + distribution v2.5.0->v2.9.3" && git push
```

### Example B: Image-API GA storage migration (Flux 2.7 — the v2.5→v2.9 wedge)

Symptom in operator logs, `FluxInstance` stuck `Ready=False`:
`CustomResourceDefinition/imagepolicies.image.toolkit.fluxcd.io dry-run failed (Invalid): status.storedVersions[0]: Invalid value: "v1beta2": missing from spec.versions; ... must remain in spec.versions until a storage migration ... removes v1beta2 from status.storedVersions`

Cause: v2.9.x ships **v1-only** image CRDs (`imagepolicies`, `imagerepositories`, `imageupdateautomations`) **and `ocirepositories`** (source group), but the live CRDs still list `v1beta2` in `status.storedVersions` because existing objects were stored at v1beta2. Kubernetes refuses to drop a stored version. Conversion strategy is `None` (identical schema across versions), so the migration is schema-safe. The old controllers keep running (the whole FluxInstance apply fails early at the CRD), so the cluster stays up — no rollback urgency.

Per CRD (enumerate: `kubectl get crd | grep toolkit`; act on any with a beta in `storedVersions` being dropped):

```bash
# 1. Add v1 (served+storage, schema copied from v1beta2) and demote v1beta2 — via a
#    kubectl replace of the edited CRD (out-of-band, kubectl talks to apiserver, not Flux).
# 2. Rewrite existing objects so they persist at v1:
mise exec -- bash -c 'kubectl get imagepolicies.image.toolkit.fluxcd.io -A -o json | kubectl replace -f -'
#    (repeat for imagerepositories / imageupdateautomations; ocirepositories usually has 0 objects)
# 3. Drop v1beta2 from storedVersions:
mise exec -- kubectl patch crd imagepolicies.image.toolkit.fluxcd.io \
  --subresource=status --type=merge -p '{"status":{"storedVersions":["v1"]}}'
# 4. Force-reconcile the FluxInstance; it converges to v2.9.3 and rolls the controllers.
mise exec -- kubectl -n flux-system annotate fluxinstance flux "fluxcd.controlplane.io/reconcileAt=$(date +%s)" --overwrite
```
Then migrate repo manifests `image.toolkit.fluxcd.io/v1beta2 → /v1` once v1 is served.

### Example C: Strict postBuild substitution fallout (kustomize-controller v1.9.x)

Symptom after the controllers roll: some Kustomizations flip to `post build failed ... envsubst error: variable substitution failed: variable not set (strict mode): "FOO"`. v1.5.0 silently blanked undefined `${VAR}`; v1.9.x **hard-fails**. Existing pods keep running (failed postBuild = no apply); it is a reconcile block, not an outage.

Fix — for each failing app, scan for ALL undefined `${VAR}` (strict mode reports only the first; also scan **decrypted** `*.sops.yaml` — postBuild runs on decrypted secret content too), then:
- **shell/script literals** (`${GH_VERSION}`, `${MINIO_ROOT_USER}`, `${secret_file}`, ...): escape to `$${VAR}` (leaves `${VAR}` for bash at runtime).
- **intended config values**: add the key to `cluster-secrets` (`kubernetes/flux/components/common/cluster-secrets.sops.yaml`), sourced from the app's own secret; verify single-consumer first (`grep -rn '${VAR}'`) so a cluster-wide var doesn't inject elsewhere.
- Defined cluster vars stay bare (`SECRET_DOMAIN`, `NAS_HOSTNAME`, `SECRET_CLOUDFLARE_TUNNEL_ID`, `TIMEZONE`, `SETTING_EXAMPLE`).

---

## 6) Verification Tests

### Test 1: Operator + distribution + controllers on target

```bash
mise exec -- kubectl -n flux-system get hr flux-operator flux-instance \
  -o custom-columns='NAME:.metadata.name,READY:.status.conditions[?(@.type=="Ready")].status,VER:.status.history[0].chartVersion'
mise exec -- kubectl -n flux-system get fluxinstance flux \
  -o custom-columns='READY:.status.conditions[?(@.type=="Ready")].status,REV:.status.lastAppliedRevision'
mise exec -- kubectl -n flux-system get deploy -o custom-columns='NAME:.metadata.name,IMAGE:.spec.template.spec.containers[0].image,AVAIL:.status.availableReplicas'
```

Expected: both HRs Ready at target chart; `FluxInstance` Ready at target REV; each controller on its target image, AVAIL≥1.

If failed: check operator logs for a CRD dry-run/validation error (Example B).

### Test 2: The whole cluster still reconciles

```bash
mise exec -- flux get kustomizations -A | grep -vE "True|^NAMESPACE"   # must be empty
mise exec -- flux get helmreleases   -A | grep -vE "True|^NAMESPACE"   # must be empty
mise exec -- flux -n flux-system reconcile ks cluster-apps            # a real end-to-end reconcile completes
```

Expected: no non-True rows; forced reconcile completes. (Transient `dependency not ready` / `artifact not found` right after the controller roll self-heals within ~1 interval — source-controller rebuilds artifacts on restart.)

If failed: distinguish transient (source rebuild) from real (Example C strict-substitution) by the message.

---

## 7) Troubleshooting

| Symptom | Likely Cause | First Fix |
|---------|--------------|-----------|
| `FluxInstance` Ready=False, operator loops on a CRD `dry-run failed (Invalid) ... storedVersions ... v1beta2` | Image-API GA ships v1-only CRD; objects stored at v1beta2 | Storage migration (Example B) |
| Many HRs `Source not ready: artifact not found` right after roll | source-controller restarted (ephemeral storage), rebuilding artifacts | Wait one interval / `reconcile source git flux-system`; self-heals |
| App ks `post build failed ... variable not set (strict mode)` | kustomize-controller v1.9.x strict postBuild | Escape `$${VAR}` or wire the var (Example C) |
| Bump merged but controllers unchanged | Only the chart bumped, not `distribution.version` | Bump `helm-values.yaml` distribution too |
| Control plane half-migrated / flapping | self-rollback tripped mid-roll | Ensure `retries:0` during the attempt; use Rollback Plan |

---

## 8) Diagnose Examples

### Diagnose Example 1: Is the wedge the CRD migration or a real failure?

```bash
mise exec -- kubectl -n flux-system logs deploy/flux-operator --tail=40 | grep 'dry-run failed' | tail -1
mise exec -- kubectl get crd imagepolicies.image.toolkit.fluxcd.io \
  -o jsonpath='{range .spec.versions[*]}{.name}{"="}{.storage}{" "}{end}{"| stored="}{.status.storedVersions}{"\n"}'
```

Expected: a `storedVersions ... v1beta2` message + a CRD whose `storedVersions` still lists a beta → Example B. Controllers still on OLD images + all Available = safe to fix forward, no rollback.

### Diagnose Example 2: Which apps have unescaped/undefined postBuild vars

```bash
# defined cluster vars (these must stay bare):
mise exec -- kubectl -n flux-system get secret cluster-secrets -o jsonpath='{.data}' | python3 -c 'import sys,json;print(sorted(json.load(sys.stdin)))'
# scan an app (include decrypted secrets):
mise exec -- sops -d kubernetes/apps/<ns>/<app>/app/secret.sops.yaml | grep -oE '\$\{[A-Za-z_][A-Za-z0-9_]*\}'
```

---

## 9) Health Check

```bash
mise exec -- flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
mise exec -- flux get helmreleases   -A | awk 'NR==1 || $5 != "True"'
mise exec -- kubectl -n flux-system get pods | grep -vE 'Running|Completed'
mise exec -- kubectl -n flux-system get fluxinstance flux -o jsonpath='{.status.lastAppliedRevision}{"\n"}'
```

Expected: no non-True ks/hr; all flux-system pods Running; FluxInstance at the intended distribution.

---

## 10) Security Check

```bash
# cluster-secrets fully encrypted (any newly-wired postBuild vars):
mise exec -- grep -c 'ENC\[' kubernetes/flux/components/common/cluster-secrets.sops.yaml
# no plaintext secret in the upgrade commits:
git diff <pre-upgrade-sha>..HEAD -- ':!*.sops.yaml' | grep -iE 'password|token|api.?key' || echo OK
```

Expected:
- cluster-secrets values are `ENC[...]`; `sops -d` succeeds (MAC valid).
- No plaintext secrets added; a var wired to empty (e.g. `MCPO_API_KEY: ""`) is only acceptable when its consumer is unexposed (check ingress `enabled`).

---

## 11) Rollback Plan

Self-rollback is disabled during the attempt (`retries:0`), so the operator owns the decision.

1. **GitOps revert (preferred, while Flux still reconciles):** `git revert <core-sha> [<followup-sha>] && git push`, then `flux reconcile hr flux-operator|flux-instance --with-source`.
2. **Flux-independent (control plane degraded):** `kubectl`/`helm` talk to the apiserver directly.
   ```bash
   for hr in flux-operator flux-instance; do mise exec -- kubectl -n flux-system patch hr $hr --type merge -p '{"spec":{"suspend":true}}'; done
   mise exec -- helm -n flux-system rollback flux-operator <last-good-rev>
   mise exec -- helm -n flux-system rollback flux-instance  <last-good-rev>
   # if a pod still crashloops, pin its image from /tmp/flux-known-good-images.txt:
   mise exec -- kubectl -n flux-system set image deploy/flux-operator manager=ghcr.io/controlplaneio-fluxcd/flux-operator:<old>
   # re-apply the backed-up CRDs only if a schema mismatch blocks the old controllers:
   mise exec -- kubectl apply -f /tmp/flux-crds-backup-<date>.yaml
   ```
   Once a known-good control plane reconciles, `git revert` + push, then un-suspend. If even this fails, escalate to `docs/sops/disaster-recovery.md`.

---

## 12) References

- `kubernetes/apps/flux-system/flux-operator/instance/helm-values.yaml` (distribution source of truth)
- `docs/sops/disaster-recovery.md` · `docs/sops/talos-upgrade.md` · `docs/sops/application-update.md`
- `runbooks/maintenance/plans/flux-stack-v0.57.md` — the executed plan this SOP generalizes; **file retired** (`d3b081f9`), recoverable via `git show d3b081f9^:runbooks/maintenance/plans/flux-stack-v0.57.md`
- Upstream: [Flux 2.7 GA notes](https://fluxcd.io/blog/2025/09/flux-v2.7.0/) (image-API v1 GA) · [flux-operator releases](https://github.com/controlplaneio-fluxcd/flux-operator/releases)
- User memory: `feedback_flux_postbuild_escape` (now enforced hard by strict mode)

---

## Version History

- `2026.08.11`: Initial SOP from the v2.5.0→v2.9.3 / operator 0.14.0→0.57.0 upgrade — strict postBuild substitution, Flux 2.7 image-API GA storage migration, attended-upgrade guard mechanics, Flux-independent rollback.
