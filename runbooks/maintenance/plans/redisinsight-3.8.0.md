---
plan_id: redisinsight-3.8.0
component: redisinsight
pr: null                              # no Renovate PR has ever existed for a 3.x bump
                                      # (only #82, the 2.58.0→2.70.1 in-major one). See §1
                                      # "why this was invisible". If Renovate opens one before
                                      # the window, record the number here and re-verify the tag.
kind: image                           # plain Deployment image tag. NOT a HelmRelease — see §6.
current: "2.70.1"
target: "3.8.0"                       # verified on Docker Hub 2026-08-15: pushed 2026-07-21,
                                      # and `latest` resolves to it. Newest 3.x line.
update_type: major                    # 2.x -> 3.x
risk: low                             # honest rating, not deflation. See §1 "risk honesty":
                                      # a GUI/admin tool in no data path, no other workload
                                      # depends on it, no shared infra is perturbed, and the
                                      # image's port/data-dir/user/entrypoint are IDENTICAL
                                      # between 2.70.1 and 3.8.0 (proven from the registry
                                      # config blobs, §1.2). The one non-trivial edge — a
                                      # forward-only sqlite migration — is covered by a
                                      # 300 KB file copy in pre-check (c).
est_duration_min: 20
needs_reboot: false
touches:
  namespaces: [databases]
  resources:
    - kustomization/redisinsight       # ns `databases`, NOT flux-system — see §6, load-bearing
    - deployment/redisinsight          # image tag; rolls with maxSurge:0 -> brief outage
    - pvc/redisinsight-data            # /data, RWO longhorn — MOUNTED ONLY, never deleted
    - "longhorn:volume/pvc-a545f6e7-2134-4b43-98b5-f0e8a3c1fe69"  # dynamic PV, reclaim=Delete
    - service/redisinsight             # UNCHANGED (port 5540) — verify, do not edit
    - ingress/redisinsight             # UNCHANGED (backend port 5540, Homepage annotations)
  shared: []                           # nothing shared is mutated. It holds an Ingress object
                                       # but does not restart the ingress controller; it mounts
                                       # one Longhorn PVC but performs no storage-layer
                                       # operation (no create/resize/delete) — an ordinary
                                       # detach/attach on pod roll. See §6.
depends_on: []
conflicts_with: [superset-redis-official, bitnamilegacy-exit-paperless-redis, bitnamilegacy-exit-nextcloud-redis, homepage-2.0.0]
                                       # VERIFICATION-CONFOUND conflicts, not danger conflicts.
                                       # Each of these moves something this plan's Section 4
                                       # asserts against (a saved connection endpoint, or the
                                       # Homepage tile). Explained in §6.
security_ref: F-6639e79c
status: draft
window: "sat-early:2026-08-22"         # 90m no-reboot slot, capacity_risk 6. Co-tenant is
                                       # kube-prometheus-stack-88 (high/3, 45m) -> 4/6 risk,
                                       # 65/90 min. Different namespaces, no shared resource.
                                       # Ordering + the alternative slot are in §6.
auto_execute: false                    # major version bump — operator go/no-go, despite risk:low
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/longhorn.md
  - docs/sops/longhorn-rwo-multi-attach.md
  - docs/sops/backup.md
  - docs/sops/homepage-integration.md
  - docs/sops/vulnerability-disclosure.md
generated: "2026-08-15"
---

# RedisInsight: image `2.70.1` → `3.8.0` (major, plain Deployment)

## 1) Summary & why held

`redis/redisinsight` is pinned at `2.70.1` in a **plain Deployment** (no
HelmRelease) at
`kubernetes/apps/databases/redisinsight/app/deployment.yaml`. Upstream moved to a
3.x line on 2026-01-07 (`3.0.1`) and is now at **`3.8.0`** (pushed 2026-07-21;
Docker Hub's `latest` resolves to it). We are a full major behind and have been
for roughly seven months.

> **Security driver — detail withheld from this public repo.**
> Tracked as **F-6639e79c** (`security` / severity `accepted`).
> Full detail (CVE IDs, counts, exposure, exploitability) lives on the
> finding record — it is deliberately not reproduced here.
>
> - Dashboard: `https://sweep.<DOMAIN>/findings/F-6639e79c`
> - CLI: `runbooks/policy-cli.py finding show F-6639e79c`
>
> See `docs/sops/vulnerability-disclosure.md` before adding any
> vulnerability detail to a committed file.

### 1.1 Why this was invisible — an audit bug, not an accepted decision

The finding above sits in the **accepted** bucket under AR-029, and its title
asserts we are *"already on the newest upstream tag"*. **That assertion is
false**, and it is false for a mechanical reason worth fixing.

`runbooks/check-all-versions.py::_pick_latest_semver_tag` prefers the *current*
tag's major when choosing "latest":

```python
        cp = self.parse_version(current_tag) if current_tag else None
        if cp:
            same_major = [t for t in version_tags if self._semver_tag_key(t)[0] == cp[0]]
            if same_major:
                return same_major[0]
        return version_tags[0]
```

For a component already a **full major behind**, `same_major` is non-empty and
the function returns the newest tag *within the stale major* — i.e. the tag we
are already on. The component then reports as up-to-date, the CVE check files it
as "no fix available upstream", and it lands in the accepted bucket instead of
the PLAN lane. Renovate has `docker:enableMajor` and *should* have opened a PR
independently, but never has (only #82, the in-major `2.58.0 → 2.70.1`), so
nothing surfaced this from either direction.

**Follow-up, deliberately NOT in this plan:** the picker bug is a code fix in
`runbooks/check-all-versions.py` plus a re-audit of every component it may have
masked, and AR-029 / F-6639e79c need re-filing once corrected. Fixing an audit
script is not maintenance-window work and must not be folded into a 20-minute
image bump. Raise it as its own change. Per
`feedback_false_positive_root_cause`, the root cause is what gets fixed — do not
AR-suppress the symptom.

### 1.2 What actually changes between 2.70.1 and 3.8.0 — the container is boringly identical

The usual 2.x→3.x fears for this image are a moved listen port and a moved data
directory. **Both were checked directly against the registry config blobs for
each tag (linux/amd64), and both are unchanged:**

| Image config field | `2.70.1` | `3.8.0` | Impact here |
|---|---|---|---|
| `ExposedPorts` | `5540/tcp` | `5540/tcp` | **No change.** Service, Ingress backend port, and both probes stay on 5540. Do not touch them. |
| `RI_APP_FOLDER_ABSOLUTE_PATH` | `/data` | `/data` | **No change.** Same mountPath, same PVC, same volume layout. |
| `User` | `node` (uid 1000) | `node` (uid 1000) | **No change.** The `chmod -R 777 /data` initContainer stays valid; no UID/permission rework. |
| `Entrypoint` | `./docker-entry.sh node redisinsight/api/dist/src/main` | identical | **No change.** |
| `RI_BUILD_TYPE` / `RI_SERVE_STATICS` | `DOCKER_ON_PREMISE` / `true` | identical | **No change.** |
| `Env` delta | — | `+ RI_APP_BUILD_COMMIT_SHA` | Cosmetic build metadata only. |

Reproduce this yourself in pre-check (b) — do not take the table on trust.

**So this bump is a one-line tag edit.** No Service change, no Ingress change, no
probe change, no manifest restructuring. That is the single most important fact
in this plan, and it is why `risk: low` is the honest rating rather than a
deflated one.

### 1.3 The one thing that is genuinely one-way: `/data/redisinsight.db`

The live pod holds **6 saved database-connection profiles** in a ~300 KB TypeORM
sqlite database at `/data/redisinsight.db` (cluster-internal Redis services
across the `databases`, `office`, `ai`, and `download` namespaces). The running
instance reports `encryptionStrategies: ["PLAIN"]` — no `RI_ENCRYPTION_KEY` is
set, so there is **no key-mismatch failure mode** on upgrade.

Because the data directory and the db filename are unchanged, 3.8.0 opens the
**same** file and runs its own schema migrations against it on first boot.
Expected outcome: **the 6 profiles carry over automatically; nothing is re-added
by hand.** Verify it in §4 — do not assume it.

The asymmetry is the rollback: an app-run schema migration is **forward-only**.
Once 3.8.0 has started and migrated the file, `2.70.1` may refuse to open it or
may start against a schema it does not understand. **`git revert` alone is
therefore not a guaranteed rollback** — the revert must be paired with restoring
the pre-upgrade `redisinsight.db`. That file is 300 KB, so pre-check (c) copies
it out in about a second. This is cheap insurance and is not optional.

### 1.4 Items to confirm at execution time rather than assume

These could not be pinned from the image config alone. Each is written as a
concrete check rather than an assumption:

- **`RITRUSTEDORIGINS`** — set by our manifest (not baked into either image).
  Upstream has been migrating env vars to an `RI_`-prefixed scheme. If 3.8.0
  ignores the old spelling, the symptom is a CORS/origin rejection in the
  **browser** while `/api/health` still returns `up`. Pre-check (d) records the
  current behaviour; §4 step (e) is what catches it; §6 says what to do.
- **`/api/health`** — both probes use it. If 3.8.0 moved it, the pod fails
  readiness and never becomes Ready, which is a loud, self-limiting failure that
  the rollout watch in Step 6 catches immediately.
- **A new login/auth screen.** The Ingress carries **no Authentik forward-auth
  annotations** — access control today is the `internal` ingressClass alone. If
  3.x introduces a first-run auth prompt, that is a UX change to note (and
  arguably an improvement), not a failure. It does not break any automation:
  nothing in this repo calls the RedisInsight API.

## 2) Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) target tag really exists (SOP application-update.md Step 0)
curl -s "https://hub.docker.com/v2/repositories/redis/redisinsight/tags/3.8.0" -o /dev/null -w '%{http_code}\n'   # expect 200

# b) re-prove the §1.2 table for yourself — port / data dir / user must be IDENTICAL.
#    If ANY row differs from the table, STOP: this plan's "one-line edit" premise is void.
TOKEN=$(curl -s "https://auth.docker.io/token?service=registry.docker.io&scope=repository:redis/redisinsight:pull" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
for TAG in 2.70.1 3.8.0; do
  echo "--- $TAG ---"
  IDX=$(curl -s -H "Authorization: Bearer $TOKEN" \
    -H "Accept: application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.list.v2+json" \
    "https://registry-1.docker.io/v2/redis/redisinsight/manifests/$TAG")
  MD=$(echo "$IDX" | python3 -c "
import sys,json
for x in json.load(sys.stdin)['manifests']:
    p=x.get('platform',{})
    if p.get('architecture')=='amd64' and p.get('os')=='linux': print(x['digest']); break")
  CD=$(curl -s -H "Authorization: Bearer $TOKEN" \
    -H "Accept: application/vnd.oci.image.manifest.v1+json" \
    "https://registry-1.docker.io/v2/redis/redisinsight/manifests/$MD" \
    | python3 -c "import sys,json;print(json.load(sys.stdin)['config']['digest'])")
  curl -sL -H "Authorization: Bearer $TOKEN" \
    "https://registry-1.docker.io/v2/redis/redisinsight/blobs/$CD" | python3 -c "
import sys,json
c=json.load(sys.stdin)['config']
print('  ports:', list(c.get('ExposedPorts',{}).keys()))
print('  user :', c.get('User'))
print('  datadir:', [e for e in c.get('Env',[]) if e.startswith('RI_APP_FOLDER')])"
done

# c) THE BACKUP — this is the rollback (§1.3). 300 KB, takes a second. Not optional.
POD=$(mise exec -- kubectl get pod -n databases -l app=redisinsight -o jsonpath='{.items[0].metadata.name}')
mkdir -p /tmp/ri-backup
mise exec -- kubectl cp "databases/$POD:/data/redisinsight.db" /tmp/ri-backup/redisinsight.db.pre-3.8.0
ls -l /tmp/ri-backup/redisinsight.db.pre-3.8.0        # expect ~300 KB, non-zero

#    plus the Longhorn floor (nightly CronJob storage/backup-of-all-volumes, 03:00).
#    The sat-early window is 09:00, so that morning's backup should be ~6h old.
mise exec -- kubectl get volume -n storage pvc-a545f6e7-2134-4b43-98b5-f0e8a3c1fe69 \
  -o custom-columns=NAME:.metadata.name,STATE:.status.state,ROBUST:.status.robustness,LASTBACKUP:.status.lastBackupAt
#    require: state=attached, robustness=healthy, lastBackupAt from today.

# d) record the pre-upgrade inventory you must see again in §4
mise exec -- kubectl port-forward -n databases svc/redisinsight 15540:5540 >/tmp/pf-ri.log 2>&1 &
sleep 3
curl -s --max-time 5 http://localhost:15540/api/health                        # {"status":"up"}
curl -s --max-time 5 http://localhost:15540/api/info                          # note appVersion 2.70.1
curl -s --max-time 5 http://localhost:15540/api/databases \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('saved connections:',len(d)); [print(' -',x.get('name')) for x in d]" \
  | tee /tmp/ri-backup/connections.pre.txt                                    # expect 6
pkill -f "port-forward -n databases svc/redisinsight" || true

# e) cluster is quiet: Kustomization Ready, single pod stable, nothing in flight.
#    NOTE THE NAMESPACE — `databases`, not flux-system. See §6.
mise exec -- flux get kustomization redisinsight -n databases
mise exec -- kubectl get pods -n databases -l app=redisinsight
mise exec -- flux get kustomizations -A | awk 'NR==1 || $5!="True"'
```

## 3) Steps

1. **Marker** so the `alert-triage-agent` treats the rollout gap as expected:
   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   runbooks/update-marker.sh add redisinsight databases 2 "redisinsight 2.70.1 -> 3.8.0 (major)"
   ```
   No Alertmanager silence is needed for a single-pod GUI with a ~1–2 min roll,
   but take one per `docs/sops/application-update.md` Step 1 if the window agent
   prefers uniformity.

2. **The edit — one line.** In
   `kubernetes/apps/databases/redisinsight/app/deployment.yaml` line 36:
   ```yaml
   -        image: redis/redisinsight:2.70.1
   +        image: redis/redisinsight:3.8.0
   ```

   **Change nothing else.** Explicitly leave alone:
   - `containerPort: 5540`, the Service `port`/`targetPort` 5540, and the Ingress
     backend port 5540 — unchanged upstream (§1.2);
   - both probes on `/api/health:5540`;
   - `strategy.rollingUpdate.maxSurge: 0` / `maxUnavailable: 1` — this is a
     deliberate RWO-multi-attach guard with three commits of history behind it
     (#87/#88/#89, and `docs/sops/longhorn-rwo-multi-attach.md` §3 names this
     Deployment as the house precedent). **Do not "modernise" it to
     `type: Recreate`** — on an existing plain manifest that leaves a stale
     `rollingUpdate` field Flux cannot remove, the Kustomization fails its
     dry-run, and every Kustomization that `dependsOn` it stalls;
   - the `busybox` `fix-permissions` initContainer — still required (uid 1000
     unchanged, `/data` root owned by 1001);
   - `RITRUSTEDORIGINS` — keep the existing spelling for this run. If §4 (e)
     shows a browser-side origin rejection, fix it as a follow-up commit (§6),
     not pre-emptively.

3. **Validate and push** (on `main`, stage only this file — the worktree is
   shared, per `feedback_stage_specific_hunks`):
   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   mise exec -- kubeconform -summary -exit-on-error -ignore-missing-schemas kubernetes/apps/databases/redisinsight
   git add kubernetes/apps/databases/redisinsight/app/deployment.yaml
   git commit -m "feat(redisinsight): 2.70.1 -> 3.8.0 (major; port/data-dir unchanged)"
   git push
   ```
   Keep the commit message free of vulnerability detail —
   `docs/sops/vulnerability-disclosure.md` covers commit messages too.

4. **Let Flux reconcile via the webhook.** Do not hand-reconcile by default. If
   the window is time-boxed and the webhook is slow, the *correct* command
   carries the right namespace:
   ```bash
   mise exec -- flux reconcile kustomization redisinsight -n databases --with-source
   ```

5. **Watch the roll.** `maxSurge: 0` means the old pod is fully terminated and
   its RWO volume detached **before** the new pod starts — expect a **~1–2 minute
   UI outage**, and a `Pending`/`ContainerCreating` gap while Longhorn reattaches.
   That is correct behaviour, not a fault:
   ```bash
   mise exec -- kubectl rollout status deploy/redisinsight -n databases --timeout=300s
   mise exec -- kubectl logs -n databases deploy/redisinsight -f | grep -iE 'migrat|error|fatal|listen|5540'
   ```
   First boot on 3.8.0 runs the sqlite schema migration (§1.3) — a slightly
   longer-than-usual startup is expected.

6. **Clear the marker only after §4 fully passes:**
   ```bash
   runbooks/update-marker.sh clear redisinsight
   ```

## 4) Verification

**There is no HelmRelease here.** `flux get hr` will find nothing, and a Ready
Kustomization only proves the manifest applied — not that the new image is
running. **Assert against the live Deployment and pod.**

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) GitOps applied — note the namespace is `databases`, not flux-system
mise exec -- flux get kustomization redisinsight -n databases          # Ready=True, current revision

# b) THE image assertion — live Deployment spec AND the running container
mise exec -- kubectl get deploy -n databases redisinsight \
  -o jsonpath='{range .spec.template.spec.containers[*]}{.name}={.image}{"\n"}{end}'   # redis/redisinsight:3.8.0
mise exec -- kubectl get pods -n databases -l app=redisinsight -o json | python3 -c "
import sys, json
for p in json.load(sys.stdin)['items']:
    for cs in p['status'].get('containerStatuses', []):
        print(cs['name'], cs['image'], 'ready', cs['ready'], 'restarts', cs['restartCount'])"
# require: image 3.8.0, ready True, restarts 0 after settle (a climbing count = probe mismatch)

# c) the app agrees it is 3.8.0, and is healthy
mise exec -- kubectl port-forward -n databases svc/redisinsight 15540:5540 >/tmp/pf-ri.log 2>&1 &
sleep 3
curl -s --max-time 5 http://localhost:15540/api/health                 # {"status":"up"}
curl -s --max-time 5 http://localhost:15540/api/info                   # appVersion MUST read 3.8.0

# d) THE data assertion — the 6 profiles migrated (§1.3). Diff against the pre-check capture.
curl -s --max-time 5 http://localhost:15540/api/databases \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('saved connections:',len(d)); [print(' -',x.get('name')) for x in d]" \
  > /tmp/ri-backup/connections.post.txt
diff /tmp/ri-backup/connections.pre.txt /tmp/ri-backup/connections.post.txt && echo "PROFILES INTACT"
pkill -f "port-forward -n databases svc/redisinsight" || true
# An empty or short list = the migration did not carry the db forward -> go to §5 Case B.

# e) THE load-bearing check is human. A healthy pod proves nothing about the UI.
#    Open https://redisinsight.${SECRET_DOMAIN} in a browser and confirm:
#      * the page loads over TLS with no cert error (Ingress/cert unchanged, so it should);
#      * NO CORS / "origin not allowed" error in the browser console — that is the
#        RITRUSTEDORIGINS rename symptom from §1.4, and /api/health will look fine while
#        it happens;
#      * all 6 saved connections are listed, and at least TWO of them actually CONNECT
#        and browse keys (pick one in `databases` and one in another namespace);
#      * note whether 3.x presents a new login/auth prompt (expected-change, not a failure).

# f) Homepage tile still discovered (annotations untouched, so this should be a no-op)
mise exec -- kubectl get ingress -n databases redisinsight \
  -o jsonpath='{.metadata.labels}{"\n"}{.metadata.annotations}{"\n"}'
#    then confirm the RedisInsight tile under the "Databases" group on the Homepage dashboard.

# g) storage did not get disturbed
mise exec -- kubectl get volume -n storage pvc-a545f6e7-2134-4b43-98b5-f0e8a3c1fe69 \
  -o custom-columns=STATE:.status.state,ROBUST:.status.robustness    # attached / healthy
```

Success = Kustomization Ready, live pod on `3.8.0` with 0 restarts, `/api/info`
reporting `3.8.0`, **all 6 connection profiles present and at least two of them
connecting from the browser**, no console CORS error, Homepage tile present, and
the Longhorn volume attached+healthy.

## 5) Rollback

**Case A — the pod never became Ready (probe mismatch, crash-loop, bad start).**
No successful 3.8.0 boot means the sqlite file was almost certainly not migrated;
a plain revert is sufficient.

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <redisinsight-3.8.0-commit-sha>
git push
mise exec -- flux reconcile kustomization redisinsight -n databases --with-source
mise exec -- kubectl rollout status deploy/redisinsight -n databases --timeout=300s
mise exec -- kubectl get deploy -n databases redisinsight \
  -o jsonpath='{range .spec.template.spec.containers[*]}{.name}={.image}{"\n"}{end}'   # 2.70.1
```
Confirm recovery by re-running §4 (c) and (d): `/api/info` reads `2.70.1` and the
6 profiles are listed. If both hold, you are back.

**Case B — 3.8.0 started and migrated `redisinsight.db`, and the app or its data
is wrong.** Revert as in Case A, **and restore the db file**, or 2.70.1 will run
against a forward-migrated schema:

```bash
cd /Users/mu/code/cberg-home-nextgen
# 1. revert + push as in Case A, then release the RWO volume:
mise exec -- kubectl scale deploy/redisinsight -n databases --replicas=0
mise exec -- kubectl wait --for=delete pod -n databases -l app=redisinsight --timeout=180s

# 2. bring the pod back on 2.70.1, then copy the pre-upgrade file back in and restart it once.
mise exec -- kubectl scale deploy/redisinsight -n databases --replicas=1
mise exec -- kubectl rollout status deploy/redisinsight -n databases --timeout=300s
POD=$(mise exec -- kubectl get pod -n databases -l app=redisinsight -o jsonpath='{.items[0].metadata.name}')
mise exec -- kubectl cp /tmp/ri-backup/redisinsight.db.pre-3.8.0 "databases/$POD:/data/redisinsight.db"
mise exec -- kubectl delete pod -n databases "$POD"          # single pod, no PDB — safe restart
mise exec -- kubectl rollout status deploy/redisinsight -n databases --timeout=300s
```
Then re-run §4 (c)+(d): `2.70.1`, 6 profiles.

**Recovery floor** (only if the copy in pre-check (c) is missing or corrupt):
restore Longhorn volume `pvc-a545f6e7-2134-4b43-98b5-f0e8a3c1fe69` from the
nightly backup per `docs/sops/longhorn.md` + `docs/sops/backup.md`, with the
Deployment scaled to 0.

> **NEVER delete `pvc/redisinsight-data` or its PV as part of any rollback.** The
> PV is dynamic `longhorn` class with `persistentVolumeReclaimPolicy: Delete` — a
> PVC delete destroys the volume and every saved profile with it. This is not a
> CIFS/SMB catastrophic class (`docs/sops/storage-safety.md`), so it is not a
> share-wipe, but it is still unrecoverable-by-delete. Deleting the PVC is never
> a step in this plan, in any branch.

Worst realistic case if everything fails: 6 connection profiles are re-added by
hand in the UI in a couple of minutes. Nothing else in the cluster is affected.

## 6) Interference notes

- **`shared: []` is deliberate and defensible.** RedisInsight is a read/write
  admin **GUI** — no workload, job, script, or integration in this repo talks to
  it (`grep -ri redisinsight` outside its own directory returns only doc/index
  rows). It owns an Ingress object but does not restart the ingress controller,
  and it mounts one Longhorn PVC but performs **no** storage-layer operation —
  just an ordinary detach/attach on pod roll. This is why it does **not** inherit
  the `shared: [storage]` treatment that got `longhorn-1.12.1-engine` moved off
  this very window. Blast radius if it goes wrong: an operator cannot browse
  Redis by GUI until it is reverted.

- **NOT a HelmRelease — the two mechanics that differ.** (1) `flux get hr -n
  databases redisinsight` returns nothing; there is no chart, no
  `helm rollback`, no `pending-upgrade` failure mode. (2) **The Kustomization
  lives in namespace `databases`, not `flux-system`** — `ks.yaml` declares
  `namespace: flux-system`, but the parent
  `kubernetes/apps/databases/kustomization.yaml` sets `namespace: databases`,
  which overrides it. `flux get kustomization redisinsight` **fails with "not
  found"**; every command in this plan carries `-n databases`. Do not read that
  error as a broken deployment.

- **Verify the live image, never a Ready status.** With a plain manifest the
  Kustomization goes Ready as soon as the object applies. §4 (b) asserts against
  `deploy/.spec.template.spec.containers[].image` **and** the running pod's
  `containerStatuses[].image` for exactly this reason.

- **Expect a short outage; do not treat it as a fault.** `maxSurge: 0` forces
  scale-down-before-up so the RWO volume is released first. ~1–2 minutes of UI
  downtime is the designed behaviour. Anyone watching who "helpfully" sets
  `maxSurge: 1` reintroduces the multi-attach bug that #87–#89 fixed.

- **`conflicts_with` is about verification confounds, not danger.** Three queued
  plans replace Redis endpoints that RedisInsight holds saved profiles for —
  `superset-redis-official` (thu-early 2026-08-20),
  `bitnamilegacy-exit-paperless-redis` (tue-early 2026-08-25), and
  `bitnamilegacy-exit-nextcloud-redis` (tue-early 2026-09-08). If one of those
  runs in the same window, §4 (d)/(e) cannot distinguish "the 3.8.0 migration
  dropped a profile" from "the co-tenant plan moved that Redis". `homepage-2.0.0`
  (tue-early 2026-08-18) rebuilds the dashboard that §4 (f) checks the tile on.
  None of these can *damage* this plan — they only make its evidence ambiguous.
  > **Standing side effect, independent of scheduling:** after each of those three
  > plans lands, the corresponding RedisInsight profile points at a dead endpoint
  > and must be re-pointed in the UI. Worth adding as a closing step to each of
  > those plans rather than rediscovering it here.

- **Co-tenancy with `kube-prometheus-stack-88` in `sat-early:2026-08-22`.** Risk
  4/6, duration 65/90, namespaces disjoint (`monitoring`+`storage` vs
  `databases`), no shared resource. The kps plan asks to be run **first** and
  fully verified before anything else, because its ~2–5 min metrics/alert
  blackout makes co-tenants' verification read false-clean — **honour that
  ordering.** The confound does not actually bite this plan: every assertion in
  §4 is a direct HTTP/`kubectl` check, and none of it depends on Prometheus
  targets or on an alert failing to fire.
  **Cheap alternative if the window agent would rather keep kps solo:**
  `tue-early:2026-08-25` fits on capacity (3/6) and duration (50/60), but its
  co-tenant is `bitnamilegacy-exit-paperless-redis` — a listed conflict — so it
  would need this plan serialised **first**, with the profile re-point handled
  afterwards. `thu-early:2026-09-10` is entirely free but is four weeks out,
  which is poor for a security-driven bump.

- **`sat-early` has no auto-fire cron.** The window→cron table in
  `docs/sops/maintenance-windows.md` §4 lists only `tue-early`, `thu-early`, and
  `sun-window`; `sat-early` was added later (2026-08-02) and has no OpenClaw cron
  id. A plan slotted here is reached via the sweep's schedule report + the
  operator, not by an automatic trigger. That is fine for an operator-present
  Saturday 09:00 slot and matches how the other sat-early plans are already
  scheduled — but do not assume this one will fire on its own.

- **`auto_execute: false` despite `risk: low`.** Policy allows unattended runs at
  low risk, but this crosses a major boundary and touches a persisted sqlite
  database. It gets a go/no-go. The `risk: low` rating is about **blast radius**,
  not about skipping the operator.

- **Do not fold in the audit-script fix.** §1.1's `_pick_latest_semver_tag` bug
  is a Python change plus a re-audit plus an AR/finding re-file. It belongs in
  its own change, reviewed on its own merits — not in a maintenance window whose
  job is to move one image tag.
