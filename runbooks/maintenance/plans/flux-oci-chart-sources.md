---
plan_id: flux-oci-chart-sources
component: flux-sources
pr: null                              # No Renovate PR exists or can exist: this is a
                                      # source-KIND refactor, not a version bump. Renovate
                                      # diffs versions inside a source it already
                                      # understands; it has no opinion about which KIND of
                                      # source holds the chart.
kind: infra
current: "30 HTTP HelmRepository chart sources + 10 type:oci HelmRepository + 1 OCIRepository + 2 GitRepository — recounted 2026-09-11 after 4dfc3e32 (pajikos deleted) and 001ab0ad (csi-driver-smb moved to a commit-pinned GitRepository). The 6 unreferenced HelmRepositories of Stage 1 are still live; a 7th orphan (GitRepository k8s-self-ai-ops) was measured the same day (F-c73cd510)"
target: "every referenced chart with an immutable OCI source migrated to OCIRepository pinned by tag AND digest; unreferenced sources deleted; the rest explicitly parked with a named reason — delivered in 11 stages, each independently abandonable"
update_type: refactor
risk: high                            # NOT from any single stage. Two drivers, both
                                      # measured, both in §1: (a) the migration ROLLS the
                                      # workload — 22 releases / 38 workloads carry a
                                      # chart-version-derived pod-template label, and the
                                      # set includes the CNI DaemonSet, the CSI driver for
                                      # all 19 CIFS classes, longhorn-manager, the
                                      # cert-manager webhook and the SSO server; (b) every
                                      # stage edits the Kustomization that gates delivery
                                      # for the whole cluster. Per-stage risk is in the
                                      # stage table — stages 0, 1, 3 and 4 are genuinely low.
est_duration_min: 30                  # PER STAGE, not for the programme. The stage table in
                                      # §3.1 carries each stage's own figure; the whole
                                      # thing is ~6h of work across many windows and must
                                      # never be scheduled as one unit. Same convention as
                                      # float-tag-pinning.
needs_reboot: false                   # No node reboot anywhere in this plan. But see §6:
                                      # a Talos roll RESTARTS source-controller, which is
                                      # the event this plan exists to survive, so it must
                                      # not share a window with one.
touches:
  namespaces: [flux-system, kube-system, cert-manager, storage, network, monitoring, media, office, databases, ai, home-automation, security, default]
  resources:
    - "kustomization/cluster-meta (spec.wait:true — EVERY stage removes members from the gate that blocks cluster-apps)"
    - "helmrepository/* in flux-system (36 HTTP objects: up to 30 replaced, 6 deleted)"
    - "ocirepository/* (NEW, one per migrated app, in the app's own namespace)"
    - "helmrelease/* (up to 32 releases switch spec.chart.spec -> spec.chartRef)"
    - "daemonset/csi-smb-node + deployment/csi-smb-controller (ROLL — backs all 19 CIFS StorageClasses, 21 Bound PVCs)"
    - "daemonset/cilium + deployment/cilium-operator (ROLL)"
    - "daemonset/longhorn-manager + deployment/longhorn-{ui,driver-deployer} (ROLL — 94 volumes)"
    - "deployment/cert-manager{,-webhook,-cainjector} (ROLL — webhook gap = Certificate admission failures)"
    - "deployment/authentik-{server,worker} + statefulset/authentik-postgresql (ROLL — SSO)"
    - "statefulset/nextcloud-mariadb, statefulset/open-webui, deployment/grafana, daemonset/otel-operator-daemon-collector (ROLL)"
    - "runbooks/check-all-versions.py + runbooks/coverage.py (Stage 0 — chartRef blindness)"
    - "fluxinstance/flux spec.kustomize.patches (Stage 10 — emptyDir sizeLimit)"
  shared: [flux-sources, cni-adjacent, cert-manager, storage/longhorn, dns-internal, monitoring]
depends_on: []
conflicts_with: [talos-1.14.0]         # A node roll drains nodes and restarts
                                       # source-controller, whose artifact cache is an
                                       # unbounded emptyDir holding all 122 HelmCharts.
                                       # Stacking a source-layer refactor on the one event
                                       # that empties that cache removes the only thing
                                       # standing between a mistake and an unreconcilable
                                       # cluster. Also: this plan rolls the CNI DaemonSet
                                       # and longhorn-manager; a Talos roll rebuilds ~50
                                       # Longhorn replicas per node.
security_ref: F-0e310ef2
capability_change: true                # Stage 9 gives Flux chart-provenance ENFORCEMENT it
                                       # does not have today (spec.verify fails CLOSED), and
                                       # Stage 1 deletes live cluster objects. Reviewed as a
                                       # fact, not a claim: stages 0-8 alone would be false.
rollback_class: git-revert
finding_refs: [F-0e310ef2, F-764e4fc3]
status: draft
window: null                           # DELIBERATE. Three reasons, in order:
                                       # (1) it is a staged programme — which stage runs when
                                       #     is an operator judgement, not a scheduler's;
                                       # (2) no slot currently fits. Measured 2026-09-11:
                                       #     sat-attended:2026-09-12 has 15 of 90 min and 1 of
                                       #     6 risk-points left (and already carries an
                                       #     unrelieved monitoring-namespace interference
                                       #     warning); sun-attended:2026-09-27 is at 140/150
                                       #     for the Talos roll, which this plan must not
                                       #     share anyway. The first honest candidate is
                                       #     sat-attended:2026-09-19 (45/90, load 1/6) for
                                       #     stages 0+1 together (~45 min, both low risk);
                                       # (3) stages 2, 5 and 6 roll CSI / SSO / CNI / storage,
                                       #     so they want an attended slot each, not a shared
                                       #     one.
autonomy_override: human-gated         # Staged programme; est_duration_min is per stage; the
                                       # riskiest stages roll the CNI and the CSI driver.
                                       # The scheduler must not treat this as one unit.
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/auto-update.md
  - docs/sops/maintenance-windows.md
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/audit-script-correctness.md
  - docs/sops/storage-safety.md
  - docs/sops/longhorn.md
  - docs/sops/k8s-gateway-dns.md
  - docs/sops/authentik.md
  - docs/sops/flux-upgrade.md
  - docs/sops/flux-dependency-revision-gate.md
generated: "2026-09-11"
---

# Migrate HTTP chart sources to OCIRepository + HelmRelease.chartRef

## 1. Summary & why held

### 1.1 What happened, and what it proved about the shape of our source layer

On 2026-09-11 `HelmRepository/k8s-gateway` pointed at a GitHub Pages chart index
that upstream **deleted** instead of redirecting. The index 404'd, the
HelmRepository could not go Ready, and because `cluster-meta` carries
`spec.wait: true` over `./kubernetes/flux/meta` — **verified live** —
`cluster-apps` (which `dependsOn: cluster-meta`) was blocked. For ~90 minutes
**no commit could deploy**. Nothing was down; *delivery* was.

That is the finding worth generalising: one third-party URL, owned by one person,
with no consumer outside a single app, is wired into a gate that every app in the
cluster passes through. We have **36 more of them**.

The near-miss was worse than the outage. `source-controller` stores artifacts on
an **`emptyDir`** (verified: volumes `data` and `tmp`, both `emptyDir: {}`, **no
`sizeLimit`**), and the chart tarball existed only there. One eviction or node
drain and internal DNS would have been unrecoverable — with a 3-node Talos roll
booked for `sun-attended:2026-09-27`, i.e. precisely that event.

Driver findings: **`F-0e310ef2`** (this plan's subject) and **`F-764e4fc3`** (the
emptyDir / disaster-recovery half — answered by Stage 10 and by §4.3's cold-cache
test). A third, `F-37ace39e`, asked for a digest pin on the one already-migrated
OCIRepository; it was **answered outside this plan by `0c77bbb0`** while this plan
was being written, so it is deliberately not claimed here — but the rule it
established is §1.5(a) and every stage below obeys it. Vulnerability and exposure
detail stays on those records.

### 1.2 The measured inventory (re-verify before executing; 2026-09-11 figures)

| | count | note |
|---|---|---|
| `HelmRepository` total, in repo | 46 | was 48 this morning; `k8s-gateway` migrated (`43a3b3e4`), `pajikos` deleted (`4dfc3e32`) |
| of which `type: oci` | 10 | legacy OCI shape, healthy — out of scope except as the comparison in §1.4 |
| of which HTTP | **36** | this plan's scope |
| HTTP, referenced by a HelmRelease | **30** (32 releases) | stages 2-8 |
| HTTP, referenced by **nothing** | **6** | stage 1 — pure subtraction |
| `OCIRepository` | 1 | `network/k8s-gateway`, tag **and** digest pinned |
| cached `HelmChart` artifacts in the emptyDir | **122** | the blast radius of one source-controller restart |

The 6 unreferenced: `backube`, `democratic-csi`, `external-secrets`, `guerzon`,
`piraeus`, `rook-ceph`. Verified by grepping every `name:` in `kubernetes/`
outside `kubernetes/flux/meta/repositories/` — zero hits each. Four match the
"dormant 8-19 months" profile by last git touch: `external-secrets`
(2025-02-19), `backube` / `piraeus` / `rook-ceph` (2025-02-25); `democratic-csi`
and `guerzon` were last touched 2026-02-22 in a bulk edit and are equally
unreferenced. The fifth dormant one was `pajikos` — already deleted today, for
exactly this reason: Home Assistant does **not** run on that chart any more
(`home-automation/home-assistant` is a `bjw-s` app-template release), so its
plaintext-`http://` problem was never a Home Assistant risk, just an unreferenced
object sitting in the delivery gate.

**All 36 HTTP indexes answered 200 when probed on 2026-09-11** (three benign
redirects: `external-secrets` 302, `unpoller` 301, the since-deleted `pajikos`
301). So no second source is 404 *today* — which is the point: the one that died
was 200 yesterday too.

### 1.3 The capability gain is real, and it is OCIRepository-only

Verified against the live CRDs, not the docs:
`helmrepositories.source.toolkit.fluxcd.io` serves **only `v1`**, and `v1`'s
`spec` has **no `verify` field at all** (`accessFrom certSecretRef insecure
interval passCredentials provider secretRef suspend timeout type url`).
`ocirepositories…/v1` has `verify.{provider,secretRef,matchOIDCIdentity,trustedRootSecretRef}`
with `provider ∈ {cosign, notation}`, and `ref.{tag,digest,semver,semverFilter}`.

So chart provenance verification is not "off" for our HTTP repos — it is
**unexpressible**, and it stays unexpressible under `type: oci` too. Only
`OCIRepository` can ever carry it. Stage 9 is where it is actually turned on, per
registry, never blanket (§3.7).

### 1.4 THE GOTCHA THAT SHAPES THIS PLAN: chartRef is **not** a workload no-op

Measured on the one component already migrated, and it contradicts the
assumption the migration was designed around.

When a HelmRelease sources its chart via `chartRef: OCIRepository`,
helm-controller reports the chart version with the artifact digest as **semver
build metadata**. Live, on `network/k8s-gateway`:

```
status.lastAttemptedRevision: 3.7.2+3783b0b4bc41      # was: 3.7.2
status.history:  v8 chart 3.7.2+3783b0b4bc41 deployed / v7 chart 3.7.2 superseded
```

Charts stamp `helm.sh/chart: <name>-<version>` into the **pod template** — it is
part of Helm's standard recommended label set. Build metadata is not a legal
label value, so Helm sanitises `+` to `_`, and the pod-template label changed:

```
helm.sh/chart=k8s-gateway-3.7.2   ->   helm.sh/chart=k8s-gateway-3.7.2_3783b0b4bc41
```

A changed pod template is a changed pod-template hash, so a new ReplicaSet was
created and **all three internal-DNS pods were replaced** ~50 seconds after the
commit (`rs/k8s-gateway-64ccd5c579`, pods created 21:01:48-21:02:12Z). The chart
bytes were byte-identical. The workload rolled anyway.

By contrast a `type: oci` HelmRepository does **not** do this — `kube-system/reloader`,
sourced that way, reports a clean `2.2.16` with no build metadata. The roll is
specific to `chartRef`.

**Measured scope** (`kubectl get deploy,sts,ds -A`, checking pod-template labels
*and* annotations for a chart-version-derived key): **22 releases / 38 workloads**
carry such a key. Inside this plan's scope that includes:

- `kube-system/csi-driver-smb` — `DaemonSet/csi-smb-node` (3 nodes) + controller → **the CSI driver behind all 19 CIFS StorageClasses and 21 Bound PVCs**
- `kube-system/cilium` — `DaemonSet/cilium` + `cilium-operator` → **CNI roll**
- `storage/longhorn` — `DaemonSet/longhorn-manager` + ui + driver-deployer → **storage control plane, 94 volumes**
- `cert-manager/cert-manager` — controller + **webhook** + cainjector → admission gap for `Certificate` writes
- `kube-system/authentik` — server + worker + `StatefulSet/authentik-postgresql` → **SSO**
- `office/nextcloud` (`StatefulSet/nextcloud-mariadb`), `ai/open-webui` (+ redis), `ai/anythingllm`, `monitoring/{grafana,unpoller,eck-operator,otel-operator,prometheus-*}`, `media/{plex,jellyfin}`

And — usefully — the components whose pod templates carry **no** such key, which
therefore migrate with **no restart at all**: `external-dns`, `metrics-server`,
`descheduler`, `node-feature-discovery`, `intel-device-plugin-*`, `headlamp`,
`falco`, `frigate`, `superset`, `influxdb`, `penpot`, `paperless-ngx`, `sure`,
`uptime-kuma`, `adguard-home`, `homepage`. That split is what the stage order in
§3.1 is built on.

**Consequences baked into this plan:**

1. The "source change must be a no-op" gate cannot be "nothing restarted". It is:
   **exactly one new Helm revision, rendered manifest identical except for the
   `helm.sh/chart` version string, and nothing else different** — same images,
   same replica counts, `generation` +1 at most, replacement pods Ready with 0
   restarts. Any other diff aborts the component (§3.2 step 4).
2. Order by blast radius of a **restart**, not by the size of the edit.
3. **The roll is the price of admission and this plan pays it**, because
   `spec.verify` and digest pinning are OCIRepository-only. That is an operator
   decision recorded here, not a silent one: if the answer is "do not restart the
   CNI and the CSI driver for a source refactor", then stages 2/5/6 should be
   re-scoped to `type: oci` (no roll, no verify, stays in the `cluster-meta`
   gate) and Stage 9 dropped. **Decide before Stage 2.**

### 1.5 Four more traps, each already paid for once

**(a) A tag-only OCIRepository FOLLOWS a re-pushed tag.** This inverts the
property we rely on today: `reconcileStrategy: ChartVersion` on an HTTP source
means an unchanged version string never re-pulls — which is exactly why today's
host repoint did *not* change the deployed bytes. An OCIRepository re-resolves
tag → digest every `interval`, GHCR does not enforce tag immutability, and the
HelmRelease upgrades on any new artifact revision with no git diff and no
Renovate PR. `F-37ace39e` recorded it; `0c77bbb0` fixed it for `k8s-gateway` and
wrote the rule into the manifest. **Every OCIRepository this plan creates carries
`ref.tag` AND `ref.digest`, re-derived from the registry.** A deny rule does not
substitute: it gates git-visible version changes, not silent tag re-resolution.

**(b) A relocated or re-published tarball is usually not the same artifact.**
Today's kapsi.fi copy of 3.7.2 was a repackage: 9195 → 9616 bytes, different
digest, differing in `Chart.yaml` maintainers plus a stray dev file. It was only
*provably* safe because both tarballs were extracted and `helm template`'d
against the live release values and diffed. That diff is **mandatory per
component** (§3.2 step 4) — not optional, and not replaceable by "same version
number". Note also that `reconcileStrategy: ChartVersion` means an unchanged
version string does **not** re-pull, so a source move can leave the old tarball
deployed and look like a success.

**(c) Our own version tooling WAS blind to `chartRef` — FIXED 2026-09-11 in
`97c3e913`.** Kept here because the hazard it describes is the reason Stage 0
exists, and because one half of it is still open. What was measured:

```
# runbooks/check-all-versions.py parse_helmrelease() on the migrated file:
chart_name='' chart_version='' repo=''   chartRef={'kind': 'OCIRepository', 'name': 'k8s-gateway'}
```

It read `spec.chart.spec` only. A migrated release dropped out of the version
snapshot with **no degradation record** — it did not look broken, it looked
chart-less. `coverage.py` read that snapshot, so it would have stopped proposing
chart bumps for every migrated component: not "held", *absent*.

Both parsers now resolve `chartRef`, and an unreadable chart source is counted
and announced instead of returning empty strings (`unresolved_chart_sources` →
stderr + report table + a `warning` finding + a per-component auto-close veto).
Measured after the fix: 123 of 124 chart sources resolve, k8s-gateway among
them. **Still open:** `csi-driver-smb` resolves to nothing at all — a
GitRepository-path chart has no version in git, and Renovate's flux manager
cannot track that shape either (F-2e76c058), so the driver behind all 19 CIFS
StorageClasses currently has no automated version signal. The bucket makes that
loud; it does not close it.

And G3 (the
breaking-change scan in `auto-update.py`) resolves release notes by mapping the
dep name to a GitHub repo, which OCI chart paths break:

```
ghcr.io/k8s-gateway/charts/k8s-gateway        -> ('k8s-gateway', 'charts')          # does not exist
ghcr.io/home-operations/charts-mirror/frigate -> ('home-operations','charts-mirror') # wrong notes
quay.io/jetstack/charts/cert-manager          -> None
```

An unresolved G3 **fails open** ("relied on CI + policy"). So a naive migration
would quietly remove breaking-change scanning from chart updates while leaving
them auto-mergeable. **Stage 0 fixes the tooling first** — the
`docs/sops/audit-script-correctness.md` standard: a check that cannot measure
must not report a pass.

Status after `97c3e913`: the derivation half is fixed — a generic
`charts` / `charts-mirror` / `helm-charts` / `helm` path segment is no longer
used as a GitHub repo name (it produced the provably nonexistent
`k8s-gateway/charts`), and k8s-gateway's real repo — `k8s_gateway`, with an
underscore, verified against the GitHub API — is pinned in the mapping table.
**The FAIL-OPEN itself is NOT fixed:** `auto-update.py`'s G3 still treats an
unresolved release-note lookup as "no breaking changes", and a derived
owner/repo remains a heuristic that can 404 silently (a mirror namespace does
not own the upstream project). Closing it means making G3 refuse to pass on an
unresolvable lookup, which changes what is auto-mergeable — a policy-bearing
change that needs its own operator decision, not a side effect of a parser fix.

**(d) Signature probing by `.sig` tag alone gives false negatives.** Three cosign
layouts are in play: the legacy `sha256-<digest>.sig` tag (cert-manager, NFD,
unpoller, charts-mirror/external-dns); a bare `sha256-<digest>` tag whose child
layer is `application/vnd.dev.sigstore.bundle.v0.3+json` (falco, and 5 of the 6
charts-mirror charts); and OCI-1.1 **referrers** (cilium, and k8s-gateway — whose
signatures were twice reported absent today for exactly this reason). A first
pass that checked only `.sig` called 5 signed charts unsigned. §3.7 checks all
three.

**(e) Do not weaken a deny rule.** `runbooks/auto-update-policy.yaml` gained
`*k8s-gateway*` today (`6ec81e05`, reason text corrected in `0c77bbb0`). Globs
still match after migration because the chart name appears in the OCI path —
verify that per component (§3.2 step 6) rather than assuming it.

## 2. Pre-checks (run at the start of EVERY stage, not once for the plan)

```bash
cd /Users/mu/code/cberg-home-nextgen

# (1) Delivery is healthy BEFORE you touch the gate that controls it.
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
flux get helmreleases -A   | awk 'NR==1 || $5 != "True"'
flux get sources all -A    | awk 'NR==1 || $5 != "True"'
kubectl -n flux-system get kustomization cluster-meta \
  -o jsonpath='{.spec.wait} {.status.conditions[?(@.type=="Ready")].status}{"\n"}'   # expect: true True

# (2) Nothing else is mid-flight — this worktree is shared.
git status --porcelain; git log --oneline -3

# (3) The cache we are one restart away from losing is still intact.
kubectl -n flux-system get pod -l app=source-controller \
  -o custom-columns='NAME:.metadata.name,RESTARTS:.status.containerStatuses[*].restartCount,START:.status.startTime'
kubectl -n flux-system exec deploy/source-controller -- /bin/sh -c 'du -sh /data; ls /data/helmchart | wc -l'

# (4) Longhorn + CIFS baseline (required for stages 2 and 6; harmless elsewhere).
kubectl get volumes -n storage -o json | python3 -c "import sys,json;v=json.load(sys.stdin)['items'];print('volumes',len(v),'attached',sum(1 for x in v if x['status'].get('state')=='attached'),'healthy',sum(1 for x in v if x['status'].get('robustness')=='healthy'))"
kubectl get pvc -A -o json | python3 -c "import sys,json;p=json.load(sys.stdin)['items'];print('cifs PVCs bound:',sum(1 for x in p if (x['spec'].get('storageClassName') or '').startswith('cifs-') and x['status']['phase']=='Bound'))"

# (5) Silence + marker for the component being migrated (SOP application-update
#     §Step 1). The roll in §1.4 WILL fire pod/not-ready alerts; silence them
#     deliberately rather than explaining them afterwards.
runbooks/update-marker.sh add <component> <ns> 2 "chart source -> OCIRepository"

# (6) ABORT the stage if any of these hold:
#   - any Kustomization or HelmRelease not Ready
#   - source-controller restarted within the last hour (cold cache: a migration
#     on a cold cache cannot be distinguished from one that broke the cache)
#   - a Talos roll, Longhorn upgrade or Cilium change is in the same window
#   - the component's deny rule in auto-update-policy.yaml would stop matching
```

## 3. Steps

### 3.1 Stage table — sequence, size, risk, and what each stage buys

Run in order. Every stage is one or more independent commits and the plan is
**safely abandonable after any stage**: stopping leaves a mixture of HTTP and OCI
sources, which is the state the cluster is in today. The full per-component
source inventory this table is derived from is in §7.

| # | Stage | components | min | risk | rolls? | buys |
|---|---|---|---|---|---|---|
| 0 | **Teach the version/update pipeline about `chartRef`** — **3 of 4 items DONE `97c3e913`; item 3's G3 fail-open still OPEN, and Stage 0 has not yet survived a sweep, so the §4.1 gate on stages 2-7 HOLDS** | tooling only | 30 → ~10 left | low | no | stops the migration from blinding `coverage.py` and fail-open-ing G3 |
| 1 | **Delete the 6 unreferenced HelmRepositories** | backube, democratic-csi, external-secrets, guerzon, piraeus, rook-ceph | 15 | low | no | removes 6 third-party URLs from the `cluster-meta` gate — the best risk-per-minute in this plan |
| 2 | ~~`csi-driver-smb` → charts-mirror OCI~~ **DONE 2026-09-11 via a DIFFERENT route — see §3.4** | csi-driver-smb | 0 | — | **no roll occurred** | executed as a GitRepository pinned to commit `59dce96e` (the v1.20.3 cut), NOT charts-mirror. **Do not execute this row.** |
| 3 | **No-roll, upstream-native OCI** | intel (3 releases), node-feature-discovery, gabe565/paperless-ngx, falcosecurity/falco | 15 ea | low | **no** | 6 releases off HTTP with zero workload impact — build confidence here |
| 4 | **No-roll, charts-mirror** | descheduler, external-dns, headlamp, metrics-server | 15 ea | low-med | **no** | external-dns is DNS-adjacent; still no pod roll |
| 5 | **Rolling, upstream-native OCI, app tier** | authentik, grafana, nextcloud, open-webui, opentelemetry, mintplex-labs | 25 ea | medium | yes | the apps where a restart is tolerable but not free |
| 6 | **Rolling, cluster-critical — ONE PER WINDOW** | cilium, jetstack/cert-manager, longhorn | 30 ea | **high** | yes | the sources whose failure blocks recovery |
| 7 | **The 11 charts with no OCI anywhere — mirror track** | plex FIRST (mutable branch), then apache-superset, blakeblackshear, dirsigler, elastic, influxdata, jameswynn, jellyfin, penpot, rm3l, sure | decision + 20 ea | medium | some | the long tail; needs §3.6 decided first |
| 8 | **`unpoller` — blocked, coupled to a chart upgrade** | unpoller | — | — | — | own plan; see §3.5 |
| 9 | **`spec.verify` — pilot, then per registry** | signed registries only | 30 pilot | medium | no | the capability gain from §1.3 |
| 10 | **`source-controller` emptyDir `sizeLimit`** | flux-system | 15 | low | yes (source-controller) | caps an unbounded emptyDir on a 69%-full node disk; answers the other half of `F-764e4fc3` |

**Stage 1 coordination note:** other sessions were editing `k8s-gateway` and
`pajikos` manifests on 2026-09-11 (`43a3b3e4`, `0c77bbb0`, `5a7baeb5`,
`4dfc3e32`). Re-read `kubernetes/flux/meta/repositories/helm/` before Stage 1 and
adjust the list — do not revert someone else's work.

### 3.2 The per-component recipe (stages 2-7) — follow it verbatim, per component

One component per commit. Never batch two components into one commit: the
rollback must be able to name exactly one thing.

```bash
cd /Users/mu/code/cberg-home-nextgen
S=/Users/mu/.claude/jobs/flux-oci/$1-$$        # scratch; NOT /tmp, and namespaced —
mkdir -p "$S"                                   # the shared scratch dir has had filename collisions
NS=<namespace>; REL=<helmrelease>; CHART=<chart-name>; VER=<pinned-version>
REPO=<helmrepository-name>; APPDIR=kubernetes/apps/$NS/.../$REL; OCI_PATH=<from §7>
```

**Step 1 — baseline the workload (before any edit).** Save it; §4.2 diffs against it.

```bash
cat > "$S/collect.sh" <<'EOS'
kubectl -n $NS get helmrelease $REL -o json | python3 -c "import sys,json;d=json.load(sys.stdin);print('HR revision',d['status'].get('lastAttemptedRevision'));print('history',[(h['version'],h['chartVersion'],h['status']) for h in d['status'].get('history',[])])"
kubectl -n $NS get deploy,sts,ds -l app.kubernetes.io/instance=$REL -o json | python3 -c "
import sys,json
for i in json.load(sys.stdin)['items']:
    m=i['metadata']; t=i['spec']['template']
    print(i['kind'], m['name'], 'gen', m['generation'],
          'chartlabel', (t['metadata'].get('labels') or {}).get('helm.sh/chart'),
          'images', sorted(c['image'] for c in t['spec']['containers']))"
kubectl -n $NS get pods -l app.kubernetes.io/instance=$REL -o json | python3 -c "
import sys,json
for p in json.load(sys.stdin)['items']:
    print(p['metadata']['name'], p['metadata']['creationTimestamp'],
          [c['restartCount'] for c in p['status'].get('containerStatuses',[])])"
kubectl -n flux-system get helmchart $NS-$REL -o jsonpath='{.status.artifact.revision} {.status.artifact.digest}{"\n"}'
EOS
bash "$S/collect.sh" | tee "$S/baseline.txt"
```

**Step 2 — copy the tarball that is ACTUALLY DEPLOYED out of the cache.** Do not
re-download from the HTTP index: the index may already serve a different artifact
(that is the failure mode), and the cache is the only record of what is running.

```bash
POD=$(kubectl -n flux-system get pod -l app=source-controller -o name | cut -d/ -f2)
P=$(kubectl -n flux-system exec "$POD" -- /bin/sh -c "ls /data/helmchart/$NS/$REL/*.tgz | tail -1")
kubectl -n flux-system cp "flux-system/$POD:$P" "$S/deployed.tgz"
shasum -a 256 "$S/deployed.tgz"; ls -l "$S/deployed.tgz"
```

**Step 3 — fetch the candidate OCI chart and record the digest you will pin.**

```bash
mise exec -- helm pull "oci://$OCI_PATH" --version "$VER" -d "$S"
shasum -a 256 "$S/$CHART-$VER.tgz"; ls -l "$S/$CHART-$VER.tgz"

# ref.digest is the MANIFEST digest (not the chart-layer digest):
REG=<ghcr.io|quay.io|registry.k8s.io>; PATH_=<org/path/chart>
TOK=$(curl -s "https://$REG/token?scope=repository:$PATH_:pull&service=$REG" \
       | python3 -c 'import sys,json;print(json.load(sys.stdin).get("token",""))')
curl -sI -H "Authorization: Bearer $TOK" \
  -H 'Accept: application/vnd.oci.image.manifest.v1+json' \
  "https://$REG/v2/$PATH_/manifests/$VER" | grep -i docker-content-digest | tee "$S/digest.txt"
```

If the tarball digests match, note it. **If they differ, do not stop** — a
repackage is common and usually benign. What matters is step 4.

**Step 4 — MANDATORY GATE: render both charts against the LIVE values and diff.**

```bash
mise exec -- helm -n $NS get values $REL --all -o yaml > "$S/live-values.yaml"
mkdir -p "$S/old" "$S/new"
tar xzf "$S/deployed.tgz"    -C "$S/old"
tar xzf "$S/$CHART-$VER.tgz" -C "$S/new"
KV=$(kubectl version -o json | python3 -c 'import sys,json;v=json.load(sys.stdin)["serverVersion"];print(v["major"]+"."+v["minor"])')
for w in old new; do
  mise exec -- helm template $REL "$S/$w/$CHART" -n $NS -f "$S/live-values.yaml" \
    --kube-version "$KV" > "$S/render-$w.yaml"
done
diff -u "$S/render-old.yaml" "$S/render-new.yaml" | tee "$S/render.diff"
```

**Gate:** `render.diff` must be **empty**, or contain only differences you can
name and justify in the commit message (`Chart.yaml` maintainers, a stray dev file
the `.helmignore` misses). **Any rendered-object difference — an image, an RBAC
rule, a probe, a resource limit, a NetworkPolicy — aborts this component.** It is
then a chart *change* wearing a source change's clothes, and needs its own plan.

Then predict the roll, so verification knows what to expect:

```bash
python3 - "$S/render-new.yaml" <<'PY'
import sys, yaml
for d in yaml.safe_load_all(open(sys.argv[1])):
    if not d or d.get("kind") not in ("Deployment","StatefulSet","DaemonSet"): continue
    l = ((d["spec"]["template"]["metadata"] or {}).get("labels") or {})
    if "helm.sh/chart" in l:
        print("WILL ROLL:", d["kind"], d["metadata"]["name"], l["helm.sh/chart"])
PY
```

**Step 5 — write the manifests.** `ocirepository.yaml` goes in the **app's own
folder**, not in `kubernetes/flux/meta`. That is the second half of the fix: a
source inside `cluster-apps` can only break its own app's Kustomization, while
every object under `./kubernetes/flux/meta` sits behind `cluster-meta`'s
`wait: true` and can block the whole tree. Follow `43a3b3e4` + `0c77bbb0`.

```yaml
---
# yaml-language-server: $schema=https://raw.githubusercontent.com/fluxcd-community/flux2-schemas/main/ocirepository-source-v1.json
apiVersion: source.toolkit.fluxcd.io/v1
kind: OCIRepository
metadata:
  name: <chart>
# Replaces HelmRepository/<repo> (HTTP). Why: an HTTP chart index is a mutable
# third-party URL wired into cluster-meta's wait gate, and spec.verify does not
# exist on the HelmRepository v1 API. See
# runbooks/maintenance/plans/flux-oci-chart-sources.md §1.
#
# THE DIGEST IS THE TRUST ANCHOR, not the tag and not the deny rule. An
# OCIRepository re-resolves tag -> digest every interval and the registry does
# not enforce tag immutability, so a tag overwrite upstream would replace this
# workload within the hour with NO git diff and NO PR. To move versions, change
# tag AND digest together, re-derived from the registry.
spec:
  interval: 1h
  layerSelector:
    mediaType: application/vnd.cncf.helm.chart.content.v1.tar+gzip
    operation: copy
  ref:
    tag: "<VER>"
    digest: sha256:<manifest-digest-from-step-3>
  url: oci://<registry>/<path>
```

Then, in the same commit:

```bash
# add to the app kustomization, BEFORE the helmrelease entry (as in 43a3b3e4):
#   resources: [./ocirepository.yaml, ./helmrelease.yaml, ...]
# switch the HelmRelease:
#   -  chart: {spec: {chart: ..., version: ..., sourceRef: {kind: HelmRepository, ...}}}
#   +  chartRef: {kind: OCIRepository, name: <chart>}
# delete the HTTP source ONLY if nothing else references it:
grep -rn "name: $REPO" kubernetes/ | grep -v 'meta/repositories'       # must be empty
git rm kubernetes/flux/meta/repositories/helm/$REPO.yaml
#   and remove its line from kubernetes/flux/meta/repositories/helm/kustomization.yaml
```

**Step 6 — validate, then commit (shared-worktree rules).**

```bash
task kubeconform
grep -n "$CHART\|$REL" runbooks/auto-update-policy.yaml    # deny globs must still match the new dep name
git commit --only $APPDIR/ocirepository.yaml $APPDIR/kustomization.yaml \
  $APPDIR/helmrelease.yaml kubernetes/flux/meta/repositories/helm/$REPO.yaml \
  kubernetes/flux/meta/repositories/helm/kustomization.yaml -F "$S/msg.txt"
git show --stat HEAD        # every file here must be yours
git push
```

The commit message must state: the deployed tarball digest/size, the OCI layer
digest/size, that `render.diff` was empty (or exactly what it contained), the
pinned `ref.digest`, and **which workloads are expected to roll**.

### 3.3 Stage 0 — teach the pipeline about `chartRef` (do this first)

> **STATUS 2026-09-11: items 1, 2 and 4 are DONE in `97c3e913`; item 3 is
> PARTIALLY done and its fail-open half is still OPEN.** Stage 0 has not yet
> survived a sweep, so the §4.1 gate on stages 2-7 still stands. Do not read
> three ticked boxes as Stage 0 complete — item 3's fail-open is the half that
> silently removes breaking-change scanning, which is the risk this stage was
> created to prevent.

Repo-only; no cluster change. Three edits plus a ground-truth test:

1. **DONE (`97c3e913`).** `runbooks/check-all-versions.py` → `parse_helmrelease()`: when `spec.chartRef`
   is present, resolve the sibling `ocirepository.yaml` in the same directory to
   recover `chart_name` (OCI path's last segment / CR name) and `chart_version`
   (from `ref.tag`), and register the `oci://` URL so
   `get_latest_chart_version()` takes its existing OCI branch.
2. **DONE (`97c3e913`).** Same for `coverage.py` → `_chart_source_for()`, so the chart-publish-age
   cooldown keeps working instead of silently returning `None`.
3. **PARTIAL — derivation fixed, FAIL-OPEN STILL OPEN.** `get_repo_info_from_image()` / `get_chart_repo_info()`: strip a
   `charts` / `charts-mirror` / `helm-charts` / `helm` path segment so G3
   resolves real upstream release notes. Today
   `ghcr.io/k8s-gateway/charts/k8s-gateway` resolves to the nonexistent repo
   `k8s-gateway/charts` and G3 fails **open**.
   The segment strip landed in `97c3e913`, and k8s-gateway's real repo
   (`k8s-gateway/k8s_gateway`, underscore — API-verified) is pinned in the
   mapping table. What remains: a derived `owner/chart` is still a HEURISTIC
   that can 404 (a mirror namespace does not own the upstream project), and
   `auto-update.py`'s G3 still treats an unresolvable lookup as "no breaking
   changes". **Closing this means G3 must refuse to pass when it cannot
   measure**, which changes what is auto-mergeable — own operator decision.
4. **DONE (`97c3e913`).** `runbooks/tests/` — a test that feeds the real migrated
   `kubernetes/apps/network/internal/k8s-gateway/helmrelease.yaml` in and asserts
   `chart_name == 'k8s-gateway'` and `chart_version == '3.7.2'`, with the
   pre-migration file as the negative case. Per
   `docs/sops/audit-script-correctness.md`, a check validated only on synthetic
   input is not validated.

**Do not start Stage 2 until Stage 0 has survived one sweep** — proof in §4.1.

### 3.4 Stage 2 — `csi-driver-smb` ✅ EXECUTED 2026-09-11, by a different route

> **STOP. DO NOT EXECUTE THE BODY OF THIS STAGE.** It was completed on
> 2026-09-11 in `001ab0ad` + `9a8eb6e5`, but **not** via charts-mirror OCI as
> planned below. Running the text as written would REPLACE an upstream commit
> pin with a third-party mirror pin — a regression, not progress.
>
> What shipped instead, and why it is stronger:
> * **`GitRepository` pinned to `ref.commit: 59dce96e11522a46354d6970393b00b1c2a57351`**
>   (the commit tagged v1.20.3), with `ref.branch: release-1.20` — required
>   because the release is not reachable from `master`, which has diverged.
>   A git commit SHA **is** the content address, so this needs no separate
>   digest pin the way an OCI tag does.
> * **Trust root stays on kubernetes-csi.** charts-mirror is a re-publisher;
>   using it would have moved the root off upstream and required proving the
>   mirror's bytes equal upstream's. That remains a legitimate operator choice,
>   just not the one taken.
> * **A trap this stage's original plan would have walked into:** the repo's
>   `index.yaml` hardcodes an **absolute** tarball URL back to the branch
>   (`…/csi-driver-smb/master/charts/v1.20.3/…`). Pinning the *index* to a
>   version path would still have fetched the *chart* from `master` — a fix
>   that looks real and is not. The GitHub Pages mirror is equally mutable and
>   additionally serves a repackaged 1.20.3.
> * **Verified no-op:** Helm release stayed at **v5** (no v6 secret), all three
>   workload generations 5/5, 0 restarts, 19/19 CIFS StorageClasses, 114/114
>   PVCs Bound, and six real CIFS mounts read including both catastrophic-tier
>   shares. `helm template` identical 619/619 lines, 12/12 objects matching live.
> * **`spec.timeout: 5m` was required** (`9a8eb6e5`): this swapped a few-KB index
>   fetch for a ~118 MB clone **inside the `wait: true` gate** that blocks
>   `cluster-apps`, against a 60s default. Any future GitRepository source in
>   this gate needs the same consideration.
> * **REGRESSION TO CLOSE — version tracking is gone.** Renovate's flux manager
>   reads a GitRepository only via `ref.tag`, and the HelmRelease no longer has
>   a `version:` field, so neither Renovate nor `check-all-versions.py` can
>   compare against upstream; the chart's image tags are frozen at the pinned
>   commit too. Needs a Renovate `customManagers` decision. Do not "fix" it with
>   a comment-only bump PR that auto-update could merge as safe.

#### Original Stage 2 plan (superseded, retained for its reasoning)

It is first because its source is the worst (a **mutable git branch** via
`raw.githubusercontent.com/kubernetes-csi/csi-driver-smb/master/charts` — the same
silent-404 shape that caused today's outage) and its blast radius is the largest
(**all 19 CIFS StorageClasses**, 21 Bound PVCs, including the catastrophic-tier
`cifs-jellyfin-media` / `cifs-plex-media`).

Three things that bound the risk, all verified:

- **No data risk.** All 19 CIFS classes are `reclaimPolicy: Retain`. This stage
  creates and deletes **no PVC** — `docs/sops/storage-safety.md` forbids it for
  CIFS classes and a root-`subdir` class is the 4.7 TB incident. The test in §4.2
  writes through an *already-mounted* volume instead.
- **A node-plugin restart does not unmount.** Existing mounts live in the node's
  mount namespace and survive. What fails during the roll is *in-flight*
  attach/provision, which is why this runs in a window with no other storage work.
- **The source exists and is signed.** `oci://ghcr.io/home-operations/charts-mirror/csi-driver-smb`
  carries `1.20.3` — our exact pin — and is cosign-signed (sigstore bundle, not a
  `.sig` tag; see §1.5(d)).

Read `docs/sops/storage-safety.md` before this stage, not after.

### 3.5 Stage 8 — `unpoller` is blocked, and must not be smuggled in

`oci://ghcr.io/unpoller/helm-chart/unpoller` exists and is signed, but carries
only **2.5.0 → 2.8.0**; a manifest `HEAD` on `2.4.0` returns 404. Our pin is
`2.4.0`. So migrating `unpoller` to OCI **forces a chart upgrade in the same
change**, which violates the §3.2 step-4 gate by construction (the render diff
cannot be empty across a minor bump).

Do not "just take 2.5.0 while we're in there". Write a separate
`unpoller-2.5.0`-style plan with its own release-notes review, and leave
`unpoller` on HTTP until then. It is an internal monitoring exporter with no
consumer depending on its availability for recovery, so parking it is cheap.

### 3.6 Stage 7 — the 11 charts with no OCI source, and which option creates work

Eleven referenced charts have **no OCI artifact anywhere** — not upstream, not in
`charts-mirror`: `apache-superset`, `blakeblackshear` (frigate), `dirsigler`
(uptime-kuma), `elastic` (eck-operator), `influxdata`, `jameswynn` (homepage),
`jellyfin`, `penpot`, `plex`, `rm3l` (adguard-home), `sure`. All 11 publish via
`chart-releaser-action` to a gh-pages `index.yaml` and never run `helm push` —
a reliable negative signal, though a private-but-existing package is
indistinguishable from an absent one over anonymous pulls, so treat each as
*unconfirmed-absent* rather than proven-absent.

| option | ongoing work for us | trust | verdict |
|---|---|---|---|
| **Upstream's own OCI registry** | **none** — Renovate tracks the tag, upstream carries publishing | highest: the chart's canonical distribution point | **always first choice** — it is what stages 3, 5 and 6 use |
| **Contribute the chart to `home-operations/charts-mirror`** | **none per version** after the PR lands — the community runs the sync, artifacts are cosign-signed and Renovate-tracked. **But:** its README prunes a chart **6 months after upstream ships OCI** and says it is our responsibility to move to the official source, so this adds a **recurring re-check**, not a permanent home | maintained community project rather than one person's Pages site | **second choice** and the right answer for most of the 11; one upstream PR per chart |
| **`flux mirror` into `ghcr.io/nachtschatt3n`** | **yes, bounded**: one config file + one scheduled runner (GitHub Action cron or a CronJob) + a GHCR push credential. New upstream versions are picked up automatically by a `version:` semver range — **no per-version push** — but a failing mirror job becomes a new way for a pinned version to be missing | we control the registry; nothing signed upstream to carry over, so we would sign our own | **third choice**, and the right one for `plex` if upstream stays HTTP-only. **Explicitly NOT a fork — it is an automated re-publish, there is nothing to hand-merge.** Note it is v0.x (`flux plugin install mirror` works on our v2.9.0; not installed today) |

What none of these is: **vendoring the chart into this repo.** The operator
rejected that on maintenance-burden grounds and it stays rejected — it is the one
option that creates unbounded per-version hand-work.

**Recommended split for the 11:** propose `plex` and `jellyfin` to
`charts-mirror` first (both are widely used, so the contribution is likely
welcome and the mirror is signed); if `plex` is declined or slow, `flux mirror` it
into our own GHCR, because its mutable-branch source is the second-worst in the
estate. Leave the remaining nine on HTTP **with their risk named in this plan**
rather than pretending the migration is complete — an HTTP source that is
honestly listed as HTTP is not the failure mode that caused today's outage; an
unowned one is.

### 3.7 Stage 9 — `spec.verify`: pilot it, then per registry, never blanket

`spec.verify` fails **closed**: on an artifact it cannot verify, the source stops
reconciling — which on `cilium` or `csi-driver-smb` is not cosmetic.

```bash
# All THREE cosign layouts must be checked (see §1.5(d)):
TOK=$(curl -s "https://ghcr.io/token?scope=repository:<path>:pull&service=ghcr.io" | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
# (1) legacy .sig tag   (2) bare sha256-<digest> tag holding a sigstore bundle
curl -s -H "Authorization: Bearer $TOK" "https://ghcr.io/v2/<path>/tags/list" \
  | python3 -c 'import sys,json;t=json.load(sys.stdin).get("tags") or [];print("sig-tags",sum(1 for x in t if x.endswith(".sig")),"bare-sha-tags",sum(1 for x in t if x.startswith("sha256-") and not x.endswith(".sig")),"of",len(t))'
# (3) OCI 1.1 referrers
curl -s -H "Authorization: Bearer $TOK" "https://ghcr.io/v2/<path>/referrers/sha256:<manifest-digest>" \
  | python3 -c 'import sys,json;d=json.load(sys.stdin);print([m.get("artifactType") for m in d.get("manifests",[])])'
```

**Pilot first, on something expendable.** It is **unverified** whether Flux
2.9.0's `verify.provider: cosign` accepts the newer
`application/vnd.dev.sigstore.bundle.v0.3+json` layout, and that layout covers 5
of the 6 charts-mirror charts plus falco. So: enable `verify` on **one** low-stakes
signed component (`falcosecurity` or `descheduler`), confirm the source still
reconciles **after a deliberate `flux reconcile source oci …`**, and only then
extend it. `matchOIDCIdentity` must be pinned to an identity actually observed —
a drifting identity is the same fail-closed outage with extra steps. Never enable
it on `cilium`, `csi-driver-smb` or `longhorn` until it has soaked a week
elsewhere.

### 3.8 Stage 10 — `source-controller` storage: cap the emptyDir, do NOT give it a PVC

Measured, so the recommendation is evidence-led and the answer is **no PVC**:

- `/data` holds **41.8 MB / 328 files** (helmchart 19.1 MB, helmrepository
  16.0 MB, gitrepository 6.8 MB, ocirepository 16 KB) after 5 days and **0
  restarts**. A PVC would be ~24× oversized for it.
- `deploy/source-controller` is already `replicas: 1` + `strategy: Recreate` in
  the vendored upstream manifest, so the `longhorn-rwo-multi-attach` trap does
  not apply — but an RWO Longhorn volume **pins the pod's reschedule** to a node
  that can attach it. Today a drain reschedules instantly and re-downloads 42 MB;
  with a PVC it waits for detach/reattach. For this cache the PVC makes failover
  *slower*, and it adds a 95th Longhorn volume to the nightly backup set holding
  data that is 100% re-derivable.
- `flux-operator` does support it (`FluxInstance.spec.storage.{class,size}`, both
  required; it templates a hardcoded `PersistentVolumeClaim/source-controller`
  with `ReadWriteOnce` and no PV-name knob, which also collides with the
  speaking-PV-name rule in `docs/sops/longhorn.md`). The option exists and is
  still the wrong one here.
- **The real defect is that both emptyDirs have no `sizeLimit`** while `/data`
  sits on the node root filesystem already at **69% (638 of 930 GB)**. Cap it via
  `FluxInstance.spec.kustomize.patches` (currently `[]`): `sizeLimit: 2Gi` on
  `data`, something small on `tmp`.
- **And the honest correction to a claim made today:** an OCIRepository's stored
  artifact lives in *the same emptyDir* (`/data/ocirepository`, 2 files measured),
  so migrating to OCI does **not** make chart recovery survive a pod restart. What
  it buys is that the artifact can be **re-fetched** afterwards — an immutable
  digest in a live registry is re-fetchable, a deleted Pages index is not.
  Durability comes from the source being alive and immutable, never from the cache.

This stays in this plan rather than being spun out because it is the other half of
`F-764e4fc3` and is meaningless without the re-fetchability the earlier stages
deliver. It rolls `source-controller` itself — schedule it **last**, alone.

## 4. Verification

`Ready=True` is worthless here on its own: it has been green through two total
internal-DNS outages, and worse, a `Ready` can be served **off the stale emptyDir
cache**. Every assertion below is written to exclude that.

### 4.1 Stage 0 (tooling) — CONTENTS ASSERTION

> **CONTENTS ASSERTION:** the migrated, `chartRef`-sourced component still appears
> in the version snapshot **with a non-empty chart name and version** — measured
> by `runbooks/check-all-versions.py` output and the Quick Overview row for
> `k8s-gateway`, compared to the pre-Stage-0 run where that row's chart cell is
> empty.

```bash
python3 runbooks/check-all-versions.py                        # or the sweep's rule 4c dry-run
grep -n '| `k8s-gateway`' runbooks/version-check-current.md   # chart cell must read 3.7.2, not '-'
python3 runbooks/coverage.py --json | python3 -c "import sys,json;d=json.load(sys.stdin);print([i for i in d.get('items',[]) if i.get('component')=='k8s-gateway'])"
python3 runbooks/maintenance-plan.py --validate && echo VALIDATE_OK
```

A still-empty chart cell means Stage 0 did not work and **stages 2-7 must not
start** — each would delete a component from the update pipeline.

### 4.2 Stages 2-7, per component — three assertions, all required

> **CONTENTS ASSERTION 1 (fresh artifact, not stale cache):** the new
> OCIRepository's `status.artifact.revision` equals `<VER>@<the digest we pinned>`
> **and** its `status.artifact.lastUpdateTime` is **after** the push commit's
> timestamp — measured below, compared to the commit time. A `Ready` whose
> artifact predates the commit is the cache answering.

```bash
kubectl -n $NS get ocirepository $CHART -o json | python3 -c "
import sys,json;d=json.load(sys.stdin)['status']['artifact']
print('revision',d['revision']);print('lastUpdateTime',d['lastUpdateTime'])"
git log -1 --format=%cI HEAD
```

> **CONTENTS ASSERTION 2 (workload no-op modulo the chart label):** exactly **one**
> new Helm revision; every Deployment/StatefulSet/DaemonSet keeps the same images,
> replica counts and container set; `generation` advances by at most 1; the only
> pod-template difference is `helm.sh/chart` gaining `_<digest>`; replacement pods
> reach Ready with **0 restarts** — measured by re-running Step 1's collector and
> diffing against `$S/baseline.txt`.

```bash
diff <(bash "$S/collect.sh") "$S/baseline.txt"
kubectl -n $NS get events --field-selector type=Warning --sort-by=.lastTimestamp | tail -20
```

> **CONTENTS ASSERTION 3 (behavioural, per component):** the thing the chart
> delivers still works, asserted directly. Use the row for the component:

| component | the assertion — not `Ready`, not `Running` |
|---|---|
| `csi-driver-smb` | **A real read/write round-trip through an already-mounted CIFS volume** in an existing pod (write a probe file, read it back, remove it), on a **non-catastrophic** class; plus all 21 CIFS PVCs still `Bound` and `csi-smb-node` 3/3 Ready. **Create and delete NO CIFS PVC** (`docs/sops/storage-safety.md`). |
| `longhorn` | RW round-trip through an existing `longhorn` PVC, **and** volume counts by `state`/`robustness` identical to the §2(4) baseline, **and** the next `storage/backup-of-all-volumes` run completes. |
| `cilium` | Cross-node pod-to-pod reachability **and** in-cluster DNS resolution from a pod, after the DaemonSet settles; `cilium-dbg status --brief` on each node; zero `NetworkPluginNotReady` events. |
| `jetstack` (cert-manager) | Create a throwaway `Certificate` in a scratch namespace, assert it reaches `Ready` within 2 min (this exercises the webhook, which is the part that rolls), then delete it. |
| `authentik` | **A real login through each affected path** (`docs/sops/authentik.md`); do not trust `/-/health/ready`. Re-run the outpost `kubernetes_disabled_components` audit **from the live outpost list**, not a repo grep. |
| `grafana`, `opentelemetry`, `unpoller`, `elastic` | **The series still arrive**: scrape target `up == 1` *and* a representative series non-empty over a window starting **after** the roll; for log-emitting components a **non-zero document floor** in Elasticsearch, not just a ceiling. |
| `external-dns` | A record it owns still resolves publicly **and** internal names still resolve through the internal resolver; zero error-level log lines about the zone. Counts, not names. |
| `nextcloud` | `occ status` plus a file listing returning a non-zero count — its MariaDB StatefulSet rolls. |
| `gabe565` (paperless-ngx) | A document count equal to the pre-change count **and** one consume-directory round trip. |
| `plex`, `jellyfin` | Library item **counts** match the pre-roll baseline (counts only — never titles, in any committed artifact). |
| `intel`, `node-feature-discovery` | The node labels / device-plugin capacity they publish are still present on all 3 nodes (`kubectl get node -o json` → `status.capacity` for the `gpu.intel.com/*` resources) — an empty capacity map is the silent failure. |
| `falcosecurity` | A deliberate benign trigger produces a rule event in the expected sink. |
| everything else | The app's own HTTPRoute returns its real content (non-empty, not an error page) on the path a user would use. |

### 4.3 Whole-plan assertion, at the end of every stage

```bash
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'     # cluster-meta AND cluster-apps
kubectl get helmrepository -A --no-headers | wc -l           # falls by exactly what the stage removed
kubectl get ocirepository  -A --no-headers | wc -l           # rises by exactly what the stage added
```

And the one that actually proves the point of the whole plan — run it **once**,
after the last app stage, in an attended window:

```bash
kubectl -n flux-system rollout restart deploy/source-controller
# then assert EVERY HelmRelease re-reconciles from its source with a COLD cache:
flux get sources all -A | awk 'NR==1 || $5 != "True"'
flux get helmreleases -A | awk 'NR==1 || $5 != "True"'
```

This is the scenario `F-764e4fc3` is about. It is the only real test of
re-fetchability, and it is exactly why it does not run mid-stage: a component
still on HTTP whose upstream has died will fail here, and that is the finding, not
a regression of this plan.

## 5. Rollback

Per component, and always the same shape because every stage is
`rollback_class: git-revert`:

```bash
git revert --no-edit <sha>    # restores the HelmRepository file + its kustomization
                              # entry + the HelmRelease chart block, atomically
git push
```

Then **confirm the cluster is actually back** — do not assume:

```bash
kubectl -n flux-system get helmrepository $REPO -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'   # True
kubectl -n flux-system get helmchart $NS-$REL -o jsonpath='{.status.artifact.revision}{"\n"}'                         # re-created
kubectl -n $NS get helmrelease $REL -o json | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['status'].get('lastAttemptedRevision'), [(h['version'],h['chartVersion'],h['status']) for h in d['status']['history']])"
bash "$S/collect.sh" | diff - "$S/baseline.txt"   # images/replicas/containers back to baseline
```

Three revert-specific facts, so they are not mistaken for failure:

1. **The revert rolls the workload a second time** — `helm.sh/chart` loses its
   `_<digest>` suffix, so the pod template changes back. Budget **two** rolls per
   component, not one. This is the main reason stages 2, 5 and 6 want an attended
   window with slack.
2. **The revert re-creates a dependency on the HTTP index.** If the revert is
   because the OCI path was wrong, fine. If the HTTP source is *also* sick,
   reverting restores a broken source into `cluster-meta`'s wait gate and
   re-blocks all delivery. Check first:
   `curl -sS -o /dev/null -w '%{http_code}\n' <repo-url>/index.yaml`.
3. **Stage 1 (the 6 deletions) reverts cleanly but pointlessly** — the objects
   were referenced by nothing. If something broke after Stage 1 the cause is
   elsewhere; re-adding the sources will not fix it.

For Stage 0 the rollback is the same `git revert`, confirmed by the version
snapshot regaining its pre-change row count. For Stage 10 it removes the
`kustomize.patches` entry and `source-controller` returns to an unbounded
emptyDir.

## 6. Interference notes

- **Every stage perturbs the delivery path itself.** `cluster-meta` has
  `wait: true` and `cluster-apps` `dependsOn` it, so a mistake in any stage blocks
  *all* deployments, not just the component's. **No other plan should share a
  window with a stage of this plan**, and the window agent should run this plan's
  stage **first** so a failure is diagnosed before other work is misattributed to
  it.
- **`conflicts_with: [talos-1.14.0]` is load-bearing, not bookkeeping.** A node
  roll restarts `source-controller` and empties the 122-artifact cache; it also
  rebuilds ~50 Longhorn replicas per node. Stages 2 and 6 roll the CSI driver,
  `longhorn-manager` and the CNI DaemonSet. Never the same window, preferably not
  the same weekend.
- **`shared: [flux-sources, cni-adjacent, cert-manager, storage/longhorn, dns-internal, monitoring]`**
  — `flux-sources` is the gate above; the rest name what the §1.4 roll touches.
  Stage 5 and Stage 9's pilot touch `monitoring`, which already carries an
  unrelieved interference warning on `sat-attended:2026-09-12` between
  `edot-collector-0.160.0` and `grafana-orphan-dashboard-uid` — do not add a
  monitoring stage to a slot that already holds two monitoring plans.
- **Ordering is fixed by dependency, not preference.** Stage 0 before any of 2-7
  (otherwise each migration silently deletes a component from the update
  pipeline). Stage 1 may share Stage 0's window — it is subtraction only. Stage 2
  before 3-7 only because blast radius should be retired while attention is high;
  if that feels wrong on the day, run Stage 3 first as a rehearsal — it is the one
  stage with no workload impact at all. Stage 9 only after a soak. Stage 10 last,
  alone.
- **At most one component per window in Stage 6**, and never `cilium` +
  `longhorn` together: CNI churn plus storage-control-plane churn in one window is
  how a recoverable mistake becomes an unrecoverable one.
- **Capacity reality at the time of writing (2026-09-11).**
  `sat-attended:2026-09-12`: 75/90 min, risk-load 5/6 — 15 min and 1 risk-point
  of slack (it was over-capacity earlier today and was relieved only by retiring a
  scrypted plan), so nothing from this plan fits.
  `sat-attended:2026-09-19`: 45/90, load 1/6 — **fits stages 0+1 together**
  (~45 min, both low risk, no workload impact).
  `sat-attended:2026-09-26`: 45/90, load 2/6 — candidate for Stage 3.
  `sun-attended:2026-09-27`: 140/150 for `talos-1.14.0` — excluded by
  `conflicts_with`. `sat-attended:2026-10-03`: 40/90, load 2/6 — first plausible
  slot for Stage 2. `nightly` is unattended and must never take a stage of this
  plan: `autonomy_override: human-gated`, and §1.4 means every stage restarts
  something.
- **Concurrent sessions.** Four commits touched this area on 2026-09-11
  (`43a3b3e4`, `0c77bbb0`, `5a7baeb5`, `4dfc3e32`). Re-read
  `kubernetes/flux/meta/repositories/helm/` and the `k8s-gateway` app folder
  before Stage 1, and adjust rather than reverting anyone's work. Commit with
  `git commit --only <explicit paths>`; verify with `git show --stat HEAD`.
- **This plan merges no Renovate PR and changes no chart version.** If a
  component's `render.diff` is non-empty, that is a version change in disguise:
  stop, and let it be planned as one (`unpoller` is the known instance, §3.5).

## 7. Appendix — per-component source inventory (probed 2026-09-11)

Verdicts came from live registry `tags/list` + per-version manifest `HEAD` calls;
nothing is listed as present unless a call returned it. **Re-derive the digest at
execution time** — the digests are deliberately not recorded here, because a
stale digest in a plan is worse than no digest.

### Upstream-native OCI (13 repos) — first choice, no mirror needed

| HelmRepository | OCI path | pinned version present | signed | rolls? | stage |
|---|---|---|---|---|---|
| `authentik` | `ghcr.io/goauthentik/helm-charts/authentik` | 2026.8.1 ✓ | no | yes | 5 |
| `cilium` | `quay.io/cilium/charts/cilium` | 1.20.1 ✓ | yes (referrers) | yes | 6 |
| `falcosecurity` | `ghcr.io/falcosecurity/charts/falco` | 9.1.0 ✓ | yes (bundle v0.3) | no | 3 |
| `gabe565` | `ghcr.io/gabe565/charts/paperless-ngx` | 0.24.1 ✓ | no | no | 3 |
| `grafana` | `ghcr.io/grafana-community/helm-charts/grafana` | 13.2.1 ✓ | no | yes | 5 |
| `intel` | `ghcr.io/intel/helm-charts/intel-device-plugins-{operator,gpu,npu}` | 0.36.0 ✓ (all 3) | no | no | 3 |
| `jetstack` | `quay.io/jetstack/charts/cert-manager` | `v1.21.1` and `1.21.1` ✓ | yes (legacy `.sig`) | yes | 6 |
| `mintplex-labs` | `ghcr.io/mintplex-labs/helm-charts/anythingllm` | 1.0.0 ✓ | no | yes | 5 |
| `nextcloud` | `ghcr.io/nextcloud/helm/nextcloud` | 9.2.6 ✓ | no | yes | 5 |
| `node-feature-discovery` | `registry.k8s.io/nfd/charts/node-feature-discovery` | 0.19.0 ✓ | yes (legacy `.sig`) | no | 3 |
| `open-webui` | `ghcr.io/open-webui/helm-charts/open-webui` | 16.5.0 ✓ | no | yes | 5 |
| `opentelemetry` | `ghcr.io/open-telemetry/opentelemetry-helm-charts/opentelemetry-kube-stack` | 0.20.6 ✓ | no | yes | 5 |
| `unpoller` | `ghcr.io/unpoller/helm-chart/unpoller` | **2.4.0 ABSENT** (2.5.0-2.8.0 only) | yes (legacy `.sig`) | yes | **8 — blocked** |

**Two traps in this table.** `grafana`: the obvious path
`ghcr.io/grafana/helm-charts/grafana` **exists but is stale** — 138 tags ending at
9.4.5/10.5.x, no 12.x or 13.x. Pinning it would silently move us three major
chart versions backwards. Use `grafana-community`, which matches the HTTP repo we
already use. `jetstack`: both `v1.21.1` and `1.21.1` resolve — pin the form the
HelmRelease already uses (`v1.21.1`) so the render diff stays empty.

### `charts-mirror` only (6 repos) — all cosign-signed, all pinned versions present

`oci://ghcr.io/home-operations/charts-mirror/<chart>`: `csi-driver-smb` 1.20.3
(stage 2) · `descheduler` 0.36.0 · `external-dns` 1.21.1 · `headlamp` 0.45.0 ·
`metrics-server` 3.14.0 (stage 4) · `longhorn` 1.12.1 (stage 6).

Two things to carry forward: the mirror **prunes a chart 6 months after upstream
ships OCI**, so these six need a recurring upstream re-check (fold it into the
sweep rather than remembering it). And `headlamp`'s apparent upstream OCI
(`ghcr.io/kubernetes-sigs/headlamp/charts`) is a **private** package —
anonymous pull denied, and the maintainers intend `registry.k8s.io` instead — so
charts-mirror is the correct source for it today, not the ghcr path.

### No OCI anywhere (11 repos) — stage 7, mirror decision required

`apache-superset` · `blakeblackshear` (frigate) · `dirsigler` (uptime-kuma) ·
`elastic` (eck-operator) · `influxdata` · `jameswynn` (homepage) · `jellyfin` ·
`penpot` · **`plex`** · `rm3l` (adguard-home) · `sure`.

`plex` is the priority of the eleven: like `csi-driver-smb` it tracks a **mutable
git branch** (`raw.githubusercontent.com/plexinc/pms-docker/gh-pages`). `elastic`
is worth a note because it looks migratable and is not:
`docker.elastic.co/eck/eck-operator:3.5.0` is the **operator image**, not a chart
(it resolves as an OCI image index, whereas every real Helm chart probed returned
config mediaType `application/vnd.cncf.helm.config.v1+json`).

### Unreferenced (6 repos) — stage 1, delete

`backube` (its `volsync` chart *is* in charts-mirror, if it is ever wanted again) ·
`democratic-csi` · `external-secrets` · `guerzon` · `piraeus` · `rook-ceph`.

### Stated as unverified

- **No signature was *validated*.** Only the presence of a signature artifact at
  the expected location was checked; no `cosign verify` ran (cosign is not
  installed locally).
- **Whether Flux 2.9.0 accepts the sigstore-bundle-v0.3 layout** — untested, and
  it gates 6 of the signed candidates. Hence the pilot in §3.7.
- **`registry.k8s.io` cannot be tag-enumerated anonymously** (`tags/list` returns
  an empty array for every path). NFD 0.19.0 was instead confirmed positively by
  `helm show chart … --version 0.19.0`.
- **The 11 "no OCI" verdicts rest on anonymous-pull 401s**, which cannot
  distinguish private-but-existing from absent — the `headlamp` case proves the
  failure mode. Each was corroborated by the project's release automation using
  `chart-releaser`, but treat them as unconfirmed-absent and re-probe before
  committing to a mirror.
- **`flux mirror` is v0.x** and not installed here; its behaviour is documented,
  not exercised.
