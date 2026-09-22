# SOP: Flux Chart Sources — trust and pinning

> Description: Which Flux source kind to use for a Helm chart (OCIRepository + chartRef, `type: oci` HelmRepository, HTTP HelmRepository, GitRepository), what actually pins the bytes in each shape, why `spec.verify` is currently omitted, and how version tracking works — or does not — per shape.
> Version: `2026.09.22`
> Last Updated: `2026-09-22`
> Owner: `Platform`

---

## 1) Description

On 2026-09-11 an upstream deleted the GitHub Pages index a chart was sourced
from, and `cluster-apps` stopped reconciling cluster-wide until the source was
repointed. The same day three components were moved to non-HTTP sources by
three agents in three shapes — `k8s-gateway` to an **OCIRepository pinned by
tag AND digest** (`43a3b3e4`, `0c77bbb0`), `csi-driver-smb` to a
**commit-pinned GitRepository** (`001ab0ad`, `9a8eb6e5`), and later `oc8` to a
**fork-tag-pinned GitRepository** — with the reasoning living only in commit
bodies and manifest comments (`F-438afc79`). This SOP is the decision record
and the procedure.

- Scope: every `HelmRelease` under `kubernetes/apps/` and every source under
  `kubernetes/flux/meta/repositories/{git,helm,oci}` (delivered by
  `kustomization/cluster-meta`, which `cluster-apps` depends on).
- Prerequisites: `flux`, `kubectl`, `helm`, `curl`; for GitRepository work,
  `git` access to the upstream.
- Out of scope: container **image** pinning (`docs/sops/inline-image-tag-coverage.md`,
  `runbooks/maintenance/plans/float-tag-pinning.md`); the OCI migration
  programme itself (`runbooks/maintenance/plans/flux-oci-chart-sources.md`).

---

## 2) Overview

Live census, `flux get sources all -A`, 2026-09-22:

| Kind | Count | Examples | Pinned by |
|---|---|---|---|
| `OCIRepository` (+ `chartRef`) | 1 | `network/k8s-gateway` — `ref.tag: 3.7.2` + `ref.digest: sha256:3783b0b4…` | **digest** |
| `HelmRepository` `type: oci` | 10 | `bjw-s`, `bitnami`, `coredns`, `controlplaneio`, `librechat`, `n8n`, `spegel`, `stakater`, `envoyproxy`, `prometheus-community` | exact `chart.spec.version` string; no digest available in this shape |
| `HelmRepository` HTTP | 30 | `nextcloud`, `cilium`, `longhorn`, `grafana`, … | exact `version` string against a **mutable index URL** |
| `GitRepository` | 4 | `flux-system` (this repo), `csi-driver-smb` (`release-1.20@sha1:59dce96e`), `oc8` (`oc8home-2026.09.17`), `k8s-self-ai-ops` (`v1.0.4`, private) | commit / tag |

| Setting | Value |
|---------|-------|
| Source manifests | `kubernetes/flux/meta/repositories/{git,helm,oci}/*.yaml` (+ `kubernetes/apps/network/internal/k8s-gateway/ocirepository.yaml`, app-local) |
| Gate they sit in | `kustomization/cluster-meta` has `wait: true`; `cluster-apps` `dependsOn` it — a source that cannot fetch blocks **all** app reconciliation |
| Version tracking | Renovate `.github/renovate.json5` (flux manager + two customManagers), `runbooks/check-all-versions.py`, `runbooks/coverage.py` — both resolve `chartRef` since the k8s-gateway move |
| Hold rules | `runbooks/auto-update-policy.yaml` (`*k8s-gateway*` etc.) gate **git-visible** bumps only |

---

## 3) Blueprints

### Shape A — OCIRepository + `chartRef`, tag AND digest (preferred when upstream publishes an OCI chart)

```yaml
# kubernetes/apps/<ns>/<app>/ocirepository.yaml  (app-local, same kustomization as the HelmRelease)
apiVersion: source.toolkit.fluxcd.io/v1
kind: OCIRepository
metadata:
  name: <app>
spec:
  interval: 1h
  url: oci://ghcr.io/<org>/charts/<chart>
  layerSelector:
    mediaType: application/vnd.cncf.helm.chart.content.v1.tar+gzip
    operation: copy
  ref:
    tag: <x.y.z>
    digest: sha256:<manifest digest for that tag>     # THE trust anchor — see §4
---
# helmrelease.yaml
spec:
  chartRef:
    kind: OCIRepository
    name: <app>
```

**Why the digest is mandatory here and nowhere else:** an OCIRepository
re-resolves tag → digest on **every interval**, and GHCR does not enforce tag
immutability, so a tag overwrite upstream would land within the hour with no
git diff and no PR. The tag alone made `k8s-gateway` *weaker* than the HTTP
source it replaced for a few hours (`0c77bbb0`). Deny rules in
`auto-update-policy.yaml` do not cover this — they gate Renovate/coverage
bumps, which are git-visible; a silent re-resolve is not.

### Shape B — `type: oci` HelmRepository + `chart.spec.version` (house default)

```yaml
# kubernetes/flux/meta/repositories/oci/<name>.yaml
apiVersion: source.toolkit.fluxcd.io/v1
kind: HelmRepository
metadata:
  name: <name>
  namespace: flux-system
spec:
  type: oci
  url: oci://ghcr.io/<org>/charts
  interval: 12h
---
# helmrelease.yaml
spec:
  chart:
    spec:
      chart: <chart>
      version: <x.y.z>            # exact string; ranges are NOT used here
      sourceRef: { kind: HelmRepository, name: <name>, namespace: flux-system }
```

`reconcileStrategy: ChartVersion` (default) means an unchanged version string
never re-pulls. There is no digest field in this shape; the pin is the version
string plus the registry's tag semantics.

### Shape C — HTTP HelmRepository (legacy; being migrated)

Same HelmRelease as B, source `url: https://…/index.yaml`. The index is a
single mutable URL; it relocated three times for one chart and was deleted
outright once (2026-09-11). Do not add new ones. When a chart's index goes
away, the cached artifact is **not** durable either — source-controller keeps
artifacts on an `emptyDir`, so a controller restart makes the chart
unrecoverable until the source is repointed.

### Shape D — GitRepository (only when no chart artifact exists)

```yaml
# kubernetes/flux/meta/repositories/git/<name>.yaml
apiVersion: source.toolkit.fluxcd.io/v1
kind: GitRepository
metadata:
  name: <name>
  namespace: flux-system
spec:
  interval: 1h
  timeout: 5m                    # the clone runs INSIDE the cluster-meta gate (§7)
  url: https://github.com/<owner>/<repo>
  ref:
    branch: <release-branch>     # scopes the clone; the commit MUST exist on it
    commit: <sha>                # content-addressed pin — stronger than a tag
  ignore: |                      # shrink the artifact to the one chart directory
    /*
    !/charts/v<x.y.z>
---
# helmrelease.yaml
spec:
  chart:
    spec:
      chart: charts/v<x.y.z>/<chart>     # a PATH, not a name; `version` does not apply
      # reconcileStrategy: Revision      # ONLY if Chart.yaml's version never moves (oc8)
      sourceRef: { kind: GitRepository, name: <name>, namespace: flux-system }
```

For a git source the version is whatever `Chart.yaml` says at the pinned ref.
`ref.commit`, `ref.branch`, the `ignore` allowlist line and the HelmRelease
`chart:` path therefore **move together** (four places for `csi-driver-smb`).

---

## 4) Operational Instructions

### 4.1 Choose the shape — in this order, stop at the first that applies

1. **Upstream publishes the chart to an OCI registry** (their own org, e.g.
   `ghcr.io/<project>/charts`) → **Shape A**, tag + digest.
2. Upstream publishes to OCI but the chart is one of many from a well-known
   publisher and the release is routine → **Shape B** is acceptable (this is
   what most of the cluster runs on today).
3. **No OCI artifact anywhere from the project** → **Shape D**, commit-pinned
   (`csi-driver-smb`: four GHCR candidate paths and `registry.k8s.io` all
   verified empty on 2026-09-11) or tag-pinned in a fork **we control**
   (`oc8`: upstream has 0 tags, 0 releases, no chart artifact, no image).
4. A **third-party mirror** (e.g. `ghcr.io/home-operations/charts-mirror/*`)
   is a **different trust decision** — the re-publisher becomes the trust root
   and its bytes must be proven equal to upstream's. It may be a legitimate
   operator choice for consistency; it is never a cleanup step of a plan.

Never leave a chart on Shape C by choice; migrate per the programme plan, one
tier at a time.

### 4.2 Before switching a source: prove it is a SOURCE change, not a CONTENT change

Both 2026-09-11 migrations did this and it is the reason they were roll-free:

```bash
# what the live release was built from
kubectl -n flux-system get helmchart <ns>-<app> -o jsonpath='{.status.artifact.digest} {.status.artifact.size}{"\n"}'
# Shape A: the chart layer inside the OCI manifest must be that same tarball
# Shape D: diff -r the chart dir at the pinned commit against the extracted tarball
helm template <rel> <old-source-chart> -f <values> > /tmp/old.yaml
helm template <rel> <new-source-chart> -f <values> > /tmp/new.yaml
diff /tmp/old.yaml /tmp/new.yaml && echo IDENTICAL-RENDER
```

A repackaged tarball (different tar metadata, different digest, same files)
is **not** identical bytes — the GitHub Pages mirror of `csi-driver-smb` and
the hobbyist host of `k8s-gateway` both served one. Prove equivalence by
render diff, and say so in the commit.

### 4.3 Re-derive a digest from the registry, never copy it from a note

```bash
REPO=<org>/charts/<chart>; TAG=<x.y.z>
TOK=$(curl -s "https://ghcr.io/token?scope=repository:$REPO:pull" | /usr/bin/python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
curl -sI -H "Authorization: Bearer $TOK" \
  -H 'Accept: application/vnd.oci.image.manifest.v1+json, application/vnd.oci.image.index.v1+json' \
  "https://ghcr.io/v2/$REPO/manifests/$TAG" | grep -i docker-content-digest
```

Verified 2026-09-22 for `k8s-gateway/charts/k8s-gateway:3.7.2`: returns
`sha256:3783b0b4…` — the digest pinned in `ocirepository.yaml`. To move
versions, change **tag and digest together**.

### 4.4 GitRepository specifics

- `ref.commit` + `ref.branch` when the release commit is not on the default
  branch (upstream cut `v1.20.3` on `release-1.20`); the branch only scopes
  the clone, the commit decides the content. If the branch vanishes the source
  goes not-Ready — loud and git-revertable, not a silent swap.
- `spec.timeout` above the clone time: the ~118 MB `csi-driver-smb` clone sits
  inside the `cluster-meta` `wait: true` gate; the 60 s default would stop app
  reconciliation cluster-wide on a cold node (`9a8eb6e5` → 5m).
- `ignore:` rather than `sparseCheckout`: a bad pattern degrades to an
  artifact missing the chart (stops one HelmChart) instead of failing the
  GitRepository inside the gate.
- `reconcileStrategy`: default `ChartVersion` rebuilds the chart artifact only
  when `Chart.yaml`'s version changes — right for `csi-driver-smb`, **wrong**
  for a chart pinned at `0.1.0` forever (`oc8`), where a new pin tag would be
  fetched and silently ignored → set `Revision`.

### 4.5 `spec.verify` — omitted on purpose, with revisit triggers

`spec.verify` fails **closed**, inside the gate above: a wrong or drifting
signing identity stops the source, and for `k8s-gateway` that is cluster-wide
internal DNS. Recorded reasons:

- `k8s-gateway` (Shape A): the charts ARE cosign-signed (keyless Fulcio, a
  `sha256-<digest>.sig` tag exists) but the signing identity has not been
  established here. Enabling verification is a separate, independently-gated
  change (`docs/sops/k8s-gateway-dns.md`).
- `csi-driver-smb` (Shape D): the pinned commit is signed only by GitHub's
  `web-flow` key, which attests that a merge went through the GitHub UI, not
  maintainer intent; TLS + the content-addressed SHA already give what that
  would. Revisit if kubernetes-csi signs releases with maintainer keys, if
  they publish an OCI chart (then Shape A + verify), or if the repo moves to
  SHA-256 objects (git object naming is SHA-1 today, so "content-addressed" is
  a SHA-1-strength claim).

### 4.6 Commit and land

```bash
git commit --only kubernetes/flux/meta/repositories/<kind>/<name>.yaml kubernetes/apps/<ns>/<app>/helmrelease.yaml -F msg.txt
git show --stat HEAD           # shared worktree — only your files
git push
flux reconcile kustomization cluster-meta -n flux-system --with-source
flux get sources all -A | grep <name>
flux get helmreleases -A | grep <app>
```

Expect a **transient** on a GitRepository migration: the HelmChart may be
reconciled before `cluster-meta` has created the new source and log
`Warning SourceUnavailable … GitRepository <name> not found` for some minutes.
It self-heals once the source exists (observed 2026-09-11, recorded in
`F-438afc79`; not reproduced here). Treat it as a hard failure only if it
persists past two `cluster-meta` intervals.

---

## 5) Examples

### Example A: HTTP index → OCIRepository with digest (`k8s-gateway`, `43a3b3e4` + `0c77bbb0`)

```bash
# 1. layer digest of the live HelmChart artifact == chart layer in the OCI manifest (9195 B)
# 2. ocirepository.yaml with tag 3.7.2, digest from §4.3
# 3. helmrelease: spec.chart.spec -> spec.chartRef
# 4. delete the HelmRepository + its kustomization line; verify nothing else references it
grep -rn "name: <old-helmrepo>" kubernetes/ | grep -v "repositories/helm"
```

### Example B: mutable-branch index → commit-pinned GitRepository (`csi-driver-smb`, `001ab0ad`)

Pinning the HTTP index to a release tag **looked** like a fix and was not: the
index hardcodes an absolute tarball URL back to `master`, so the index would
have been pinned and the chart still fetched from the branch. The fix was the
commit tagged `v1.20.3` on `release-1.20`, with `diff -r` and render-diff proof.

---

## 6) Verification Tests

### Test 1: the source is Ready and stores the revision you pinned

```bash
flux get sources all -A | grep -E "<name>"
```

Expected:
- `READY True`; for Shape A the REVISION column shows the pinned digest prefix, for Shape D `<branch>@sha1:<commit prefix>`

If failed:
- `kubectl -n flux-system describe <kind> <name>` — auth, timeout, or a `ref` that does not exist on that branch

### Test 2: the HelmRelease built from the new source and did not roll the workload

```bash
kubectl -n flux-system get helmchart <ns>-<app> -o jsonpath='{.status.artifact.digest} {.spec.sourceRef.kind}/{.spec.sourceRef.name}{"\n"}'
kubectl -n <ns> get deploy <app> -o jsonpath='{.metadata.generation} {.status.observedGeneration}{"\n"}'
helm history <app> -n <ns> | tail -3
```

Expected:
- `sourceRef` names the new source; the artifact digest matches the one you proved byte-identical in §4.2; no new Helm revision unless values changed

If failed:
- a new revision with a changed pod template means the bytes were NOT identical — compare `helm get manifest` across the two revisions before deciding whether to keep it

### Test 3: version tooling still sees the chart

```bash
/usr/bin/python3 runbooks/check-all-versions.py --help >/dev/null && grep -n "<app>" runbooks/version-check-current.md | head -3
```

Expected:
- Shape A/B: a version row with a comparison; Shape D: a row plus the explicit "chart comes from GitRepository … no version in git" note (that is the honest state, not an error)

If failed:
- a missing row on a chartRef consumer means the resolver regressed — `runbooks/coverage.py` and `check-all-versions.py` both carry chartRef resolution since 2026-09

---

## 7) Troubleshooting

| Symptom | Likely Cause | First Fix |
|---------|--------------|-----------|
| `cluster-apps` NotReady, every app stalled, one HelmRepository `NotReady` with a 404 | an HTTP chart index was deleted or relocated upstream | repoint (or migrate the shape, §4.1); the cached artifact does not survive a controller restart |
| HelmChart `SourceUnavailable: GitRepository <x> not found` minutes after a migration commit | ordering transient — HelmChart reconciled before `cluster-meta` created the source | wait two intervals; persistent → the source is not in `repositories/git/kustomization.yaml` |
| GitRepository `NotReady`, timeout | clone larger than `spec.timeout` (60 s default) inside the gate | raise `timeout` (`9a8eb6e5`: 5m); consider `ignore` |
| OCIRepository revision changed with no git diff | tag re-resolved to a new digest — `ref.digest` is missing | pin the digest (§4.3); check what landed before trusting it |
| New pin tag on a git-sourced chart fetched but nothing changed | `reconcileStrategy: ChartVersion` and `Chart.yaml` version unchanged | `reconcileStrategy: Revision` on the HelmRelease chart spec |
| Renovate proposes a "digest bump" moving a commit pin to `master` HEAD | flux manager's `git-refs` path resolves the DEFAULT branch when no tag is set | that rule is disabled for `csi-driver-smb` in `renovate.json5`; never merge such a PR |
| Renovate shows NO update for a chart for a long time | the OCI repo moved (bjw-s → bjw-s-labs, grafana, k8s-gateway) or the shape is invisible to it (Shape D) | repoint the source (verify the current version exists there first); for Shape D rely on the customManager + dashboard entry |

```bash
flux get sources all -A | awk 'NR==1 || $5 != "True"'
kubectl -n flux-system get helmcharts | grep -v True
kubectl -n flux-system get events --field-selector type=Warning --sort-by=.lastTimestamp | tail -20
```

---

## 8) Diagnose Examples

### Diagnose Example 1: "did the upstream tag move under us?" (Shape A without digest, or Shape B)

```bash
kubectl -n flux-system get ocirepository -A -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name,REV:.status.artifact.revision
# then re-derive the digest for the pinned tag (§4.3) and compare
```

Expected:
- the stored revision equals the registry's current digest for that tag AND the digest in git

If unclear:
- `helm get manifest <app> -n <ns> | sha256sum` against the previous revision's manifest — a differing render on an unchanged version string is the tell

### Diagnose Example 2: "which four places carry the csi-driver-smb version, and do they agree?"

```bash
f=kubernetes/flux/meta/repositories/git/csi-driver-smb.yaml
grep -nE "commit:|branch:|!/charts/v" $f
grep -n "chart: charts/v" kubernetes/apps/kube-system/csi-driver-smb/app/helmrelease.yaml
git ls-remote https://github.com/kubernetes-csi/csi-driver-smb refs/tags/v<x.y.z>   # commit for the tag
```

Expected:
- one version string in the `ignore` line and the chart path; the commit equals the tag's commit; the branch is the release branch that contains it

If unclear:
- `git ls-remote … refs/heads/release-<major.minor>` and confirm the commit is an ancestor there

---

## 9) Health Check

```bash
flux get sources all -A | awk 'NR==1 || $5 != "True"'                      # everything Ready
kubectl get ocirepository -A -o jsonpath='{range .items[*]}{.metadata.name}{" digest="}{.spec.ref.digest}{"\n"}{end}'   # every OCIRepository carries a digest
grep -L "type: oci" kubernetes/flux/meta/repositories/helm/*.yaml | grep -v kustomization | wc -l   # HTTP sources remaining (30 on 2026-09-22; should only fall)
```

Expected:
- no NotReady source; no OCIRepository without `ref.digest`; the HTTP count not rising

---

## 10) Security Check

```bash
# trust roots are the project's own, not a re-publisher's
grep -rn "url:" kubernetes/flux/meta/repositories/ kubernetes/apps/*/*/*/ocirepository.yaml 2>/dev/null | grep -iE "mirror|proxy"
# no source pulls a mutable ref without a content pin
kubectl get gitrepository -A -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.spec.ref}{"\n"}{end}'
```

Expected:
- no mirror/re-publisher URL unless that trust decision is recorded in the manifest comment
- every GitRepository pins a commit or a tag in a repo we control; every OCIRepository pins a digest
- no `spec.verify` block added without its signing identity established and the fail-closed blast radius written down

---

## 11) Rollback Plan

A source change is a git revert: the HelmRelease returns to its previous
source and, if §4.2 held, the workload does not roll.

```bash
git revert <source-commit> && git push
flux reconcile kustomization cluster-meta -n flux-system --with-source
flux reconcile helmrelease <app> -n <ns>
```

If the OLD source is the thing that broke (index deleted), rollback is not
available — that is the failure this SOP exists to prevent; move forward to
Shape A/D instead.

---

## 12) References

- Commits: `43a3b3e4`, `0c77bbb0` (k8s-gateway OCI + digest); `001ab0ad`, `9a8eb6e5` (csi-driver-smb GitRepository); `e617d4e5` (Renovate customManager for commit-pinned git charts)
- Manifests with the full reasoning inline: `kubernetes/apps/network/internal/k8s-gateway/ocirepository.yaml`, `kubernetes/flux/meta/repositories/git/{csi-driver-smb,oc8}.yaml`
- `.github/renovate.json5` — `customManagers` and the `dependencyDashboardApproval` rules
- `runbooks/maintenance/plans/flux-oci-chart-sources.md` — the migration programme
- `docs/sops/helm-chart-source-outage.md`, `docs/sops/k8s-gateway-dns.md`, `docs/sops/auto-update.md`

---

## Version History

- `2026.09.22`: Initial SOP (F-438afc79). Census from the live cluster; digest re-derivation verified against GHCR; Renovate behaviour taken from the 2026-09-22 customManager commit, not assumed.
