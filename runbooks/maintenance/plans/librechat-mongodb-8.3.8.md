---
plan_id: librechat-mongodb-8.3.8
component: librechat-mongodb
pr: null                            # No Renovate PR is possible. bitnami/mongodb no longer
                                    # publishes semver tags (registry has `latest` + ~502
                                    # `sha256-*` attestation tags only), so there is no
                                    # version stream for Renovate to diff. The image is
                                    # pinned by DIGEST in the librechat HelmRelease values,
                                    # and a digest bump is a hand-authored change.
kind: image                         # image digest override on the existing librechat chart
                                    # 2.0.7 / bitnami mongodb subchart 16.5.45.
                                    # The CHART version is NOT changed by this plan.
current: "8.2.6"                    # sha256:3cb21cf1de351e133da3bdf574fc61da9dc371a05d13aff91ed15a9b50becb8a
                                    # image built 2026-03-23; verified live via db.version()
target: "8.3.8"                     # sha256:0c57d0efdf2f08958e5cd1392b20664c92597c7c6da2fbd0e972bcfb96d0dc92
                                    # image built 2026-08-14; verified via image config label
                                    # org.opencontainers.image.version + APP_VERSION=8.3.8
update_type: minor                  # MongoDB 8.2 -> 8.3 (one minor step; supported upgrade path)
risk: medium                        # ONE-WAY once featureCompatibilityVersion is raised.
                                    # Binary-only rollback stays clean while FCV remains "8.2"
                                    # (see §5) -- that property is what keeps this medium and
                                    # not high. Data is small (1.4 GB) and backed up nightly.
est_duration_min: 30
needs_reboot: false                 # pod rolls in place; no node reboot
touches:
  namespaces: [ai]
  resources:
    - helmrelease/librechat
    - deployment/librechat-mongodb          # single replica, updateStrategy Recreate
    - pvc/librechat-mongodb                 # 10Gi, storageClass longhorn (dynamic)
    - pv/pvc-cb151bc0-c164-4e35-a287-58a78b859ebb
    - "longhorn:volume/pvc-cb151bc0-c164-4e35-a287-58a78b859ebb"   # backup = recovery floor
    - deployment/librechat-librechat        # in-namespace data dependent: loses its DB
                                            # backend for the duration of the roll
  shared: []                        # No cluster-wide shared infra perturbed. Does NOT touch
                                    # ingress-controller, cert-manager, cni, coredns, longhorn
                                    # itself, or any other namespace. Blast radius is the
                                    # LibreChat app only.
depends_on: []
conflicts_with: []                  # Do not co-schedule with any other plan that rolls the
                                    # `ai` namespace (openclaw / ollama-facing apps) purely to
                                    # keep the post-roll signal unambiguous -- not a hard
                                    # technical conflict.
status: executed
window: "sat-early:2026-08-15"
# Paired with librechat-mongodb-auth, sequenced AFTER it. That plan wipes the
# datadir, so this stops being a 8.2->8.3 migration at all and becomes a fresh
# 8.3.8 install -- the one-way featureCompatibilityVersion risk disappears.
# Do NOT run this one first, and do NOT run it in a window without the other.
                                    # (risk-weight 2) => fits tue/thu/sat-early. Not urgent:
                                    # there is no CVE driver (see §1) and the digest pin has
                                    # already removed the time pressure.
auto_execute: false                 # NEVER fast-track. Database minor upgrade with a one-way
                                    # FCV step and no vendor-published semver stream.
                                    # Operator go/no-go required.
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/longhorn.md
generated: "2026-08-15"
---

# librechat mongodb image 8.2.6 -> 8.3.8 (librechat chart 2.0.7, unchanged)

## 1) Summary & why held

The LibreChat chat database (`librechat-mongodb`, namespace `ai`) runs
`docker.io/bitnami/mongodb`. As of commit `43474514` (2026-08-15) it is pinned by
**digest** to `sha256:3cb21cf1...` = **MongoDB 8.2.6**. This plan tracks the deferred
move to the current `latest` = `sha256:0c57d0ef...` = **MongoDB 8.3.8**.

**This plan exists because of how the pin was created, not because of an urgent driver.**
Before 2026-08-15 the values carried `mongodb.image.tag: "latest"`. On 2026-08-14 that tag
drifted 8.2.6 -> 8.3.8, arming an *uncontrolled* minor version change on the chat database
to fire at the next reschedule onto a node with no cached layer. The digest pin defused
that. The version bump itself was deliberately **split out** into this plan so it happens
as a decided, verified, reversible change instead of a surprise.

**Why it cannot flow through the auto-updater.**

- `bitnami/mongodb` **no longer publishes semver tags.** Verified against the Docker Hub
  registry API on 2026-08-15:

  | reference | HTTP | resolves to |
  |---|---|---|
  | `latest` | 200 | `sha256:0c57d0ef...` (8.3.8, built 2026-08-14) |
  | `sha256:3cb21cf1...` | 200 | 8.2.6, built 2026-03-23 (current pin) |
  | `8.2.6` | **404** | — |
  | `8.3.8` | **404** | — |
  | `8.0.13-debian-12-r0` | **404** | — (this is the *chart's own default*, see below) |

  With no version stream, Renovate has nothing to diff and no PR to raise. A digest bump
  is inherently hand-authored.
- It is a **database minor upgrade**, which the auto-update policy holds regardless.

**Important adjacent finding — the chart's default tag is broken.** Bitnami mongodb subchart
16.5.45 defaults to `image.tag: 8.0.13-debian-12-r0`, and that tag **404s**. So "just drop
our override and take the chart default" is *not* an available fallback — it would produce
an unpullable image. The digest pin is **mandatory**, not merely preferable. Any future
chart bump must be checked for the same trap.

**Strategic note the operator should weigh before approving (this is the real decision).**
MongoDB 8.0 is the LTS line; 8.1/8.2/8.3 are *rapid releases*, each supported only until the
next rapid release supersedes it. Because Bitnami now publishes only `latest` on the public
repo, we cannot *choose* an LTS image here — we get whatever `latest` happens to be on the
day we look. That means this plan will recur indefinitely, always one-way, always on a
rapid-release train. Two alternatives worth considering **instead of** executing this plan:

1. **Stay on the 8.2.6 digest indefinitely.** Cheapest. Legitimate while there is no CVE
   driver. Cost: the image ages and eventually accrues unpatched CVEs.
2. **Migrate off the Bitnami public repo** — to the official `mongo` image (which *does*
   publish real semver tags, including the 8.0 LTS line) or to a MongoDB operator. This is
   the durable fix; it restores a version stream, restores Renovate coverage, and lets us
   sit on LTS. It is a larger change (the Bitnami subchart's entrypoint, env-var contract
   and non-root UID differ from the official image) and warrants its own plan.

**Recommendation: do not execute this plan on autopilot.** Prefer option 1 until a CVE
driver appears, and open a separate plan for option 2. Execute this bump only if a scan
flags fixable CVEs on `sha256:3cb21cf1...`, and re-verify at that time that `latest` has
not drifted to yet another version (it is a moving target — re-resolve the digest, do not
trust the one recorded above).

**Live baseline captured 2026-08-15** (post digest-pin, all verified in-cluster):

- mongod `8.2.6`, `featureCompatibilityVersion: "8.2"`, storage engine `wiredTiger`
- **standalone** (no replica set) — so no rolling upgrade is possible; this is a
  stop-start replace, which is why `updateStrategy: Recreate` is already set
- `auth.enabled: false` (see §6 — an open security item, deliberately out of scope here)
- database `LibreChat`: 30 collections, small — 1 user, 1 conversation, 2 messages,
  23 systemgrants, 10 transactions
- Longhorn volume 10Gi, nightly backups healthy (latest 2026-08-14T23:06Z, 1.4 GB, 100%)

## 2) Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) RE-RESOLVE the target digest -- `latest` is a moving target and the digest recorded
#    in this plan's frontmatter WILL go stale. Do not skip this.
TOKEN=$(curl -s "https://auth.docker.io/token?service=registry.docker.io&scope=repository:bitnami/mongodb:pull" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
curl -s -o /dev/null -w 'latest -> %{http_code}\n' \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.list.v2+json" \
  -I "https://registry-1.docker.io/v2/bitnami/mongodb/manifests/latest"
# then read the docker-content-digest header + the config-blob label
# org.opencontainers.image.version to confirm WHICH MongoDB version you are about to install.
# If it is no longer 8.3.8, STOP and re-plan -- a 8.2 -> 8.4+ jump is >1 minor and is NOT a
# supported single-step upgrade path.

# b) current state: HR Ready, pod on the 8.2.6 digest, 0 restarts
mise exec -- kubectl get hr -n ai librechat \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'                 # True
mise exec -- kubectl get deploy -n ai librechat-mongodb \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'                       # ...@sha256:3cb21cf1...
mise exec -- kubectl get pods -n ai -l app.kubernetes.io/name=mongodb -o wide         # 1/1 Running, 0 restarts

# c) THE load-bearing pre-check -- FCV must be "8.2" before a binary move to 8.3
POD=$(mise exec -- kubectl get pods -n ai -l app.kubernetes.io/name=mongodb -o jsonpath='{.items[0].metadata.name}')
mise exec -- kubectl exec -n ai $POD -c mongodb -- mongosh --quiet admin --eval '
  print("version: " + db.version());
  print("fcv    : " + JSON.stringify(db.adminCommand({getParameter:1, featureCompatibilityVersion:1}).featureCompatibilityVersion));'
# expect version 8.2.6, fcv {"version":"8.2"}. If fcv is LOWER than 8.2, raise it to 8.2 and
# soak BEFORE attempting 8.3 -- MongoDB refuses to start a binary more than one minor ahead
# of the persisted FCV.

# d) record a data baseline to diff against after the upgrade
mise exec -- kubectl exec -n ai $POD -c mongodb -- mongosh --quiet LibreChat --eval '
  db.getCollectionNames().sort().forEach(function(c){ print(c + "=" + db.getCollection(c).countDocuments({})); });'

# e) FRESH backup immediately before the change (do not rely on the nightly)
#    Longhorn UI or a manual Backup CR against volume pvc-cb151bc0-c164-4e35-a287-58a78b859ebb.
mise exec -- kubectl get volume -n storage pvc-cb151bc0-c164-4e35-a287-58a78b859ebb \
  -o custom-columns=NAME:.metadata.name,STATE:.status.state,ROBUST:.status.robustness,LASTBACKUP:.status.lastBackupAt
# require: state=attached, robustness=healthy, lastBackupAt within the hour

# f) no in-flight reconcile
mise exec -- flux get kustomizations -A | awk 'NR==1 || $5!="True"'
```

## 3) Steps (GitOps, copy-pasteable)

> Single change: swap the `digest` value in the librechat HelmRelease values. The chart
> version stays `2.0.7`. Do NOT touch `spec.chart.spec.version`, `updateStrategy`, or the
> `tag` key (which is inert — the digest overrides it).

1. **Active-update marker** so the alert-triage-agent treats the DB gap and any
   `PodNotReady` / LibreChat 5xx as EXPECTED:
   ```bash
   runbooks/update-marker.sh add librechat-mongodb ai 1 "mongodb 8.2.6->8.3.8 digest bump"
   ```

2. **Swap the digest** in
   `kubernetes/apps/ai/librechat/app/helmrelease.yaml`, under `spec.values.mongodb.image`:
   ```yaml
         image:
           registry: docker.io
           repository: bitnami/mongodb
           tag: "latest"
           digest: "sha256:<THE DIGEST YOU RE-RESOLVED IN PRE-CHECK (a)>"
   ```
   Update the explanatory comment block above it to name the new version + build date.
   Confirm the chart version is untouched:
   ```bash
   grep -n 'version: "2.0.7"' kubernetes/apps/ai/librechat/app/helmrelease.yaml   # still 2.0.7
   grep -c 'digest:' kubernetes/apps/ai/librechat/app/helmrelease.yaml            # exactly 1
   ```

3. **Prove the render** before pushing — a values pin at the wrong path silently no-ops
   while the HelmRelease still reports Ready:
   ```bash
   helm pull oci://ghcr.io/danny-avila/librechat-chart/librechat --version 2.0.7 \
     --untar --untardir /tmp/lc-chart          # NOTE: --untardir lands relative to CWD on
                                               # some helm builds -- verify it did NOT land
                                               # inside the repo, and move it out if it did
   mise exec -- yq '.spec.values' kubernetes/apps/ai/librechat/app/helmrelease.yaml \
     | sed 's/\${SECRET_DOMAIN}/example.invalid/g' > /tmp/lc-values.yaml
   mise exec -- helm template librechat /tmp/lc-chart/librechat -n ai -f /tmp/lc-values.yaml \
     | mise exec -- yq 'select(.kind=="Deployment" and .metadata.name=="librechat-mongodb")
                        | [.spec.template.spec.containers[].image,
                           .spec.template.spec.initContainers[].image]'
   # expect BOTH the container and the init container on the new digest
   ```

4. **Validate + commit + push** (work on `main`, stage only this hunk):
   ```bash
   mise exec -- kubeconform -summary -exit-on-error -ignore-missing-schemas kubernetes/apps/ai/librechat
   git add kubernetes/apps/ai/librechat/app/helmrelease.yaml   # ONLY this file
   git commit -m "feat(librechat): bump mongodb 8.2.6 -> 8.3.8 (digest pin)"
   git push
   ```
   Flux reconciles; the Deployment replaces the single pod (Recreate: old pod terminates
   FIRST, so there is a genuine DB gap of roughly 30-60 s).

5. **Do NOT raise featureCompatibilityVersion in the same change.** Leave FCV at `"8.2"`
   and soak for at least one week. This is what keeps rollback cheap (§5). Raising FCV to
   `"8.3"` is a *separate, later, deliberate* step:
   ```bash
   # ONLY after a successful soak, and only if you accept losing the cheap rollback:
   # mongosh admin --eval 'db.adminCommand({setFeatureCompatibilityVersion:"8.3", confirm:true})'
   ```

6. **On success**, clear the marker:
   ```bash
   runbooks/update-marker.sh clear librechat-mongodb
   ```

## 4) Verification

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) HR reconciled, pod rolled to the new digest, 0 restarts
mise exec -- kubectl get hr -n ai librechat \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'                  # True
mise exec -- kubectl rollout status deploy/librechat-mongodb -n ai --timeout=300s
mise exec -- kubectl get deploy -n ai librechat-mongodb \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'                        # new digest

# b) live-object proof -- check the POD SPEC, not just the Deployment, and the resolved
#    imageID. (containerStatuses[].image may report the cached `:latest` alias; that is a
#    known cosmetic artifact of the tag being present in the local image store. The pod
#    SPEC field and the imageID digest are authoritative.)
mise exec -- kubectl get pods -n ai -l app.kubernetes.io/name=mongodb -o json | python3 -c "
import sys,json
for p in json.load(sys.stdin)['items']:
    for c in p['spec'].get('initContainers',[]) + p['spec']['containers']:
        print('SPEC', c['name'], '->', c['image'])
    for cs in p['status'].get('containerStatuses',[]):
        print('imageID', cs['imageID'], 'ready', cs['ready'], 'restarts', cs['restartCount'])"

# c) THE load-bearing check -- the DB actually came up on the new version, FCV unchanged,
#    and the data is intact (diff against the pre-check (d) baseline)
POD=$(mise exec -- kubectl get pods -n ai -l app.kubernetes.io/name=mongodb -o jsonpath='{.items[0].metadata.name}')
mise exec -- kubectl exec -n ai $POD -c mongodb -- mongosh --quiet admin --eval '
  print("version: " + db.version());
  print("fcv    : " + JSON.stringify(db.adminCommand({getParameter:1, featureCompatibilityVersion:1}).featureCompatibilityVersion));'
# expect version 8.3.8, fcv still {"version":"8.2"}
mise exec -- kubectl exec -n ai $POD -c mongodb -- mongosh --quiet LibreChat --eval '
  db.getCollectionNames().sort().forEach(function(c){ print(c + "=" + db.getCollection(c).countDocuments({})); });'
# counts must MATCH the pre-check baseline

# d) mongod startup log -- no unsupported-downgrade / FCV / WiredTiger errors
mise exec -- kubectl logs -n ai $POD -c mongodb --tail=80 | grep -iE 'error|fatal|fcv|featureCompat|corrupt' || echo "clean"

# e) the failure worth catching -- LibreChat can actually TALK to the DB again
mise exec -- kubectl get pods -n ai | grep librechat            # librechat pod 1/1
LC=$(mise exec -- kubectl get pods -n ai -o name | grep librechat-librechat | head -1 | cut -d/ -f2)
mise exec -- kubectl logs -n ai $LC --since=15m | grep -iE 'mongo|econnrefused|topology|disconnect' || echo "no mongo errors"
DOM=$(mise exec -- kubectl get secret -n flux-system cluster-secrets -o jsonpath='{.data.SECRET_DOMAIN}' | base64 -d)
for P in / /health /api/config; do
  echo -n "$P -> "; curl -s -o /dev/null -w '%{http_code}\n' --max-time 20 "https://librechat.$DOM$P"
done
# expect 200 / 200 / 200. A mongodb that starts but that LibreChat cannot reach is the
# real failure mode -- do not declare success on pod-Ready alone.
```

Success = HR Ready=True on chart 2.0.7, one mongodb pod Ready on the new digest with 0
restarts, `db.version()` = 8.3.8, FCV still `"8.2"`, collection counts identical to the
baseline, and LibreChat serving 200 on `/`, `/health` and `/api/config`.

## 5) Rollback

**The rollback is cheap ONLY while `featureCompatibilityVersion` is still `"8.2"`.** That is
the entire reason step 3.5 defers the FCV raise. Two distinct cases:

**Case A — FCV still `"8.2"` (the expected state): plain git revert.** MongoDB 8.3 running at
FCV 8.2 has not written 8.3-only on-disk features, so the 8.2.6 binary can reopen the same
data files.
```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <bump-commit-sha>     # restores digest sha256:3cb21cf1... (8.2.6)
git push
mise exec -- kubectl rollout status deploy/librechat-mongodb -n ai --timeout=300s
POD=$(mise exec -- kubectl get pods -n ai -l app.kubernetes.io/name=mongodb -o jsonpath='{.items[0].metadata.name}')
mise exec -- kubectl exec -n ai $POD -c mongodb -- mongosh --quiet --eval 'db.version()'   # 8.2.6
```

**Case B — FCV was already raised to `"8.3"`: git revert alone WILL NOT WORK.** The 8.2.6
binary refuses to start against FCV 8.3 data files and the pod will crash-loop. You must
either lower FCV *before* reverting the image (while 8.3.8 is still running):
```bash
# while still on 8.3.8:
mongosh admin --eval 'db.adminCommand({setFeatureCompatibilityVersion:"8.2", confirm:true})'
# then perform Case A
```
…or, if the pod is already crash-looping, **restore the Longhorn volume from backup** —
volume `pvc-cb151bc0-c164-4e35-a287-58a78b859ebb`, per `docs/sops/longhorn.md`. Scale
`deployment/librechat-mongodb` to 0 first so nothing holds the RWO volume. Data written
since the backup is lost; for this workload that is chat history only.

**Recovery floor:** the nightly Longhorn backup of
`pvc-cb151bc0-c164-4e35-a287-58a78b859ebb` (CronJob `storage/backup-of-all-volumes`, 03:00).
Confirm a fresh one exists per pre-check (e) before starting.

## 6) Interference notes

- **Blast radius: the LibreChat app only.** One Deployment in `ai` plus its own PVC. No
  shared cluster infra (ingress-controller, cert-manager, cni, coredns, longhorn itself)
  is perturbed, and no other namespace is touched.
- **There IS a real service gap, unlike a rolling upgrade.** `librechat-mongodb` is a
  **standalone** mongod (no replica set) on an RWO Longhorn volume with
  `updateStrategy: Recreate` — deliberately so, because the chart default RollingUpdate
  surges a second pod and deadlocks on Multi-Attach. Recreate tears the old pod down FIRST,
  so LibreChat is DB-less for roughly 30-60 s. The `librechat-librechat` pod is not
  restarted and reconnects on its own; it does not need to be rolled.
- **One-way once FCV is raised.** Until then, binary rollback is clean. Treat the FCV raise
  as its own decision with its own soak — never bundle it into the image bump.
- **Do not co-schedule** with other `ai`-namespace plans (openclaw / ollama-facing work).
  Not a hard technical conflict — the concern is diagnostic ambiguity if something in the
  namespace misbehaves mid-window.
- **`needs_reboot: false`**, medium risk (weight 2), ~30 min ⇒ fits any no-reboot window
  (tue/thu/sat-early). No urgency driver, so there is no argument for the nearest slot.
- **Out of scope but adjacent (flagged, not fixed by this plan):** this mongodb runs with
  `mongodb.auth.enabled: false` and the namespace NetworkPolicy has no `from:` selector,
  so the database is reachable **unauthenticated from any namespace in the cluster**. That
  is an independent security decision for the operator — either a real fix (enable auth +
  scope the NetworkPolicy) or an explicit `runbooks/policy-cli.py risk add` acceptance.
  It is called out here because this plan's window is a natural moment to fix it (the DB
  is already being restarted), but it must not be silently folded in.
