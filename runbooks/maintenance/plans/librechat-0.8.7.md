---
plan_id: librechat-0.8.7
component: librechat
pr: null                              # chart-default image tag, nothing in git for
                                      # Renovate to bump. Hold source is the Trivy
                                      # scan (security-check-current.md, 2026-08-13).
kind: image
current: "librechat v0.8.4 (chart default, chart 2.0.2)"
target: "librechat v0.8.7"
update_type: patch                    # within the 0.8.x line: 0.8.4 -> 0.8.5 -> 0.8.6 -> 0.8.7
risk: medium                          # externally exposed + MongoDB behind it
est_duration_min: 30
needs_reboot: false
touches:
  namespaces: [ai]
  resources:
    - helmrelease/librechat           # values pin on the chart-default image tag
    - deployment/librechat-librechat  # image v0.8.4 -> v0.8.7
    - pvc/librechat-mongodb           # app may run schema/config migrations on start
    - pvc/librechat-meilisearch       # search index may need reindex
    - pvc/librechat-librechat-images  # user-uploaded images, untouched but in blast radius
    - ingress/librechat-librechat     # class "external" — backend swap only
  shared: []                          # librechat runs its OWN mongodb + meilisearch in
                                      # ai; NOT the cluster-shared mongo/redis/postgres.
depends_on: []
conflicts_with: []
status: draft
window: "tue-early:2026-08-18"       # assigned 2026-08-14; operator-present (externally
                                      # exposed + MongoDB behind it). Small, fits a 60m slot.
auto_execute: false                   # data store (MongoDB) + external exposure
sops_refs:
  - docs/sops/application-update.md
generated: "2026-08-14"
---

# librechat v0.8.4 → v0.8.7 (7 fixable CRITICAL CVEs)

## 1) Summary & why held

`registry.librechat.ai/danny-avila/librechat:v0.8.4` carries **7 fixable CRITICAL
CVEs** (Trivy, 2026-08-13). Upstream **v0.8.7** exists (released 2026-06-24), so
unlike immich (AR-057) this one genuinely has a fix at source.

**Why it is not a one-line bump:** the running tag is a **chart default**, not a
value in git — the HelmRelease pins only `mongodb` and `meilisearch`. Nothing in
`kubernetes/apps/ai/librechat/app/helmrelease.yaml` references `v0.8.4`, so
Renovate has no artifact to bump (hence `pr: null`). The fix is a **values pin**,
the same pattern as the open-webui websocket-redis pin (commit 03541f0f).

**Why medium risk:** externally exposed (`librechat.${SECRET_DOMAIN}`, class `external`)
and backed by its own MongoDB. LibreChat applies config/schema changes on
startup; three minor releases are being crossed in one hop.

## 2) Pre-checks

```bash
# a) confirm the chart's image values path BEFORE editing — do not guess.
#    The chart is OCI: oci://ghcr.io/danny-avila/librechat-chart (version 2.0.2).
helm show values oci://ghcr.io/danny-avila/librechat-chart --version 2.0.2 | grep -A5 -i '^image:'
#    If the OCI pull fails from the workstation, pull it in-cluster or read the
#    rendered Deployment: kubectl get deploy -n ai librechat-librechat -o yaml

# b) is there a NEWER CHART that already ships 0.8.7? Prefer a chart bump over an
#    image pin if so — a pin ahead of the chart can mismatch its config template.
helm show chart oci://ghcr.io/danny-avila/librechat-chart --version 2.0.2 | grep -E '^(version|appVersion)'

# c) baseline
kubectl get pods -n ai -l app.kubernetes.io/name=librechat
kubectl get deploy -n ai librechat-librechat -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
curl -s -o /dev/null -w '%{http_code}\n' https://librechat.${SECRET_DOMAIN}/    # expect 200

# d) FRESH Longhorn backup of all three PVCs (mandatory — MongoDB migrates on start)
kubectl get volumes -n storage -o custom-columns=NAME:.metadata.name,LASTBACKUP:.status.lastBackupAt --no-headers \
  | grep -E 'librechat'

# e) read the release notes for 0.8.5, 0.8.6 and 0.8.7 — three releases in one hop.
#    Specifically check for: librechat.yaml config schema changes, required env
#    vars, and any MongoDB migration note.
```

## 3) Steps

1. Marker: `runbooks/update-marker.sh add librechat ai 2 "librechat 0.8.4->0.8.7 (CVE)"`
2. Add the image pin to `values` in
   `kubernetes/apps/ai/librechat/app/helmrelease.yaml`, at the path confirmed in
   pre-check (a).
3. **Validate the render before commit** — this is the step that catches a wrong
   values path, which would silently no-op:
   ```bash
   helm template librechat oci://ghcr.io/danny-avila/librechat-chart --version 2.0.2 \
     -f <(yq '.spec.values' kubernetes/apps/ai/librechat/app/helmrelease.yaml) \
     | grep -E 'image: .*librechat'      # MUST show v0.8.7
   ```
4. Commit + push; let the webhook reconcile.
5. **Reconcile order matters** (open-webui lesson, plan open-webui-redis-8.10.0):
   reconcile the Kustomization FIRST so the HelmRelease spec carries the new
   values, THEN the HelmRelease — otherwise Helm upgrades with stale values and
   the HR still reports Ready. **Check the Deployment image, not just HR Ready.**

## 4) Verification

```bash
kubectl get deploy -n ai librechat-librechat -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'  # v0.8.7
kubectl get pods -n ai -l app.kubernetes.io/name=librechat        # Ready, low restarts
kubectl logs -n ai deploy/librechat-librechat --tail=60 | grep -iE 'migrat|error|mongo'
curl -s -o /dev/null -w '%{http_code}\n' https://librechat.${SECRET_DOMAIN}/    # 200
# Operator smoke test: log in, open an existing conversation (proves Mongo data
# survived), send one message (proves the model wiring still works), and check
# that search returns results (proves meilisearch index is intact).
trivy image registry.librechat.ai/danny-avila/librechat:v0.8.7 --severity CRITICAL --ignore-unfixed
#   expect the 7 fixable CRITICALs gone
```

## 5) Rollback

Revert the values pin (`git revert`), reconcile Kustomization then HelmRelease,
confirm the Deployment is back on v0.8.4. **If MongoDB migrated**, an image
downgrade is not sufficient on its own — restore `librechat-mongodb` from the
pre-change Longhorn backup per `docs/sops/backup.md`, with librechat scaled to 0
first. Clear the marker either way.

## 6) Interference notes

- Blast radius is `ai/librechat` and its own mongodb + meilisearch. No shared
  datastore, no ingress-controller restart (backend swap only).
- Do not co-schedule with other `ai`-namespace work.
- If pre-check (b) shows a newer chart shipping 0.8.7, **prefer the chart bump**
  and reclassify this plan — an image pin ahead of its chart risks a config
  template mismatch.
