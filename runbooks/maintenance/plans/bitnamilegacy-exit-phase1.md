---
plan_id: bitnamilegacy-exit-phase1
component: paperclip
pr: null                              # archived registry — no upstream tag can fix it
kind: image
current: "docker.io/bitnamilegacy/kubectl:1.33.4 (single bash container in the backup-cleanup CronJob)"
target: "registry.k8s.io/kubectl:v1.36.0 (kubectl steps) + busybox:stable (file-cleanup step)"
update_type: major                    # 1.33 -> 1.36 AND a CronJob restructure
risk: low                             # blast radius = one CronJob + one app's replica count
est_duration_min: 25
needs_reboot: false
touches:
  namespaces: [ai, security]
  resources:
    - cronjob/paperclip-backup-cleanup      # image + container structure rewritten
    - deployment/paperclip                  # the job scales it 1->0->1 (unchanged behaviour)
    - role/paperclip-backup-cleanup         # unchanged, re-verified
    - helmrelease/falco                     # customRules: k8s-api-noise.yaml macro repointed
    - daemonset/falco                       # rolls on all 3 nodes (checksum/rules changes)
  shared: [falco]                           # host-level runtime security monitoring restarts
depends_on: []
conflicts_with: []                          # do not co-schedule with another falco-rules plan
security_ref: F-2d25e586                    # see also F-9d9a0018 (same image, fixable class)
status: draft
window: "tue-early:2026-08-18"
auto_execute: false                         # falco rules + RBAC-bearing CronJob — operator eyes
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/falco.md
generated: "2026-08-15"
---

# bitnamilegacy exit, phase 1/4 — the paperclip backup-cleanup CronJob

## 1) Summary & why held

Phase 1 of 4 in the programme that gets this cluster off the **archived**
`bitnamilegacy` registry. Phase 1 is deliberately the smallest, most separable
piece: one CronJob in `ai`, no datastore, no user-facing service.

**Why no version bump can fix this.** On 2025-08-28 Bitnami moved its free
container catalog into `docker.io/bitnamilegacy` and stopped publishing there.
The registry is an archive kept "solely to help with migration"; it receives no
further updates or patches, ever. `docker.io/bitnami/kubectl` is not a fallback
either — it no longer carries a semver tag stream Renovate can track. So there
is no tag to bump to. The only remediation is to leave the registry.

> **Security driver — detail withheld from this public repo.**
> Tracked as **F-2d25e586** and **F-9d9a0018** (both `docker.io/bitnamilegacy/kubectl:1.33.4`).
> Counts, CVE identifiers and exposure live on the finding records — they are
> deliberately not reproduced here.
>
> - Dashboard: `https://sweep.<DOMAIN>/findings/F-2d25e586`
> - CLI: `runbooks/policy-cli.py finding show F-2d25e586`
>
> See `docs/sops/vulnerability-disclosure.md` before adding any vulnerability
> detail to a committed file.

**Secondary driver — version skew.** The API server is on **v1.36.0**; this
CronJob ships a **1.33.4** client. That is three minors behind, outside the
supported kubectl ±1-minor skew window, on a pod that holds RBAC to scale a
Deployment. Moving to `registry.k8s.io/kubectl:v1.36.0` closes that as well.

### The trap: `registry.k8s.io/kubectl` is NOT a drop-in swap

This looked like a one-line image change. It is not. Verified against the live
registry on 2026-08-15 (`registry.k8s.io/v2/kubectl/manifests/v1.33.4` → config
blob):

```
Entrypoint: ["/bin/kubectl"]
Cmd:        null
LABEL description = "go based runner for distroless scenarios"
```

The image is **distroless — it has no shell**. The current CronJob runs
`command: ["/bin/bash", "-c", "<40-line script>"]` with `set -euo pipefail`,
a `restore()` function, `trap restore EXIT`, `date -d "7 days ago"`, `sed`,
`ls`, `wc` and `rm`. None of that exists in the target image. A naive
`image:` swap yields `CrashLoopBackOff` / `exec: "/bin/bash": no such file`,
and — worse — it would fail **after** the scale-down in the failure ordering an
operator would most likely improvise, leaving `paperclip` parked at 0 replicas.

The fix is to split the job by capability, which also removes the last reason
to want a shell in a cluster-credentialed container:

| Step | Image | Why |
|---|---|---|
| initContainer `scale-down` | `registry.k8s.io/kubectl:v1.36.0` | pure kubectl verb, no shell needed |
| initContainer `wait-terminated` | `registry.k8s.io/kubectl:v1.36.0` | `kubectl wait --for=delete` |
| initContainer `cleanup` | `busybox:stable` | shell + `find`; **no** cluster credentials needed |
| container `scale-up` | `registry.k8s.io/kubectl:v1.36.0` | runs last, restores the replica count |

**Why this is safer than the `trap` it replaces.** Kubernetes runs
initContainers strictly in order and only starts the main container once every
one of them has succeeded. Making `scale-up` the *main* container gives the same
guarantee the `trap` was reaching for — and a `trap` never fired on the failure
mode that actually matters (node loss / OOM-kill), whereas a failed `cleanup`
init step here is made non-fatal explicitly. The one residual gap (node dies
between scale-down and scale-up) is unchanged from today.

**Behaviour change to accept:** retention moves from parsing `YYYYMMDD` out of
the filename to `find -mtime +7` on file mtime. For files written once at backup
time these are equivalent, and mtime does not silently keep a file forever when
a filename stops matching `paperclip-<date>-*.sql`. Called out so the window
agent does not treat it as an accidental diff.

### Coupled change you must not miss: the Falco rule exception

`kubernetes/apps/security/falco/app/helmrelease.yaml` (`customRules:` →
`k8s-api-noise.yaml`) allowlists this exact image by repository:

```yaml
- macro: user_known_contact_k8s_api_server_activities
  condition: >
    (container.image.repository = ghcr.io/nachtschatt3n/ai-sre or
     container.image.repository = docker.io/bitnamilegacy/kubectl or
     container.image.repository startswith docker.io/longhornio/)
```

Change the CronJob image without changing this macro and Falco's "Contact K8S
API" rule starts firing on every nightly run (the very noise class this macro
was written to suppress, per the 24h Wazuh triage recorded in that file). Both
edits belong in this plan; the Falco edit goes **first** so there is never a
window where the new image is unallowlisted.

### Not in scope (deliberately)

- `ai/librechat` (`bitnami/mongodb`, digest-pinned) and `databases/mariadb`
  (`bitnami/mariadb`, digest-pinned) are on the **paywalled current** catalog,
  not the archived one. They are a *different* problem — a frozen digest with no
  semver stream for Renovate to track (see `docs/sops/mariadb-major-upgrade.md`
  §Security Check). They need their own plan; do not fold them in here.
- `databases/superset` postgresql + redis are covered by
  `superset-redis-official`, `superset-pg-standup`, `superset-pg-cutover`,
  `superset-pg-decommission`.

## 2) Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) confirm what is actually deployed and that the server version is what we target
mise exec -- kubectl version -o json | python3 -c "import sys,json;print(json.load(sys.stdin)['serverVersion']['gitVersion'])"   # v1.36.0
mise exec -- kubectl get cronjob -n ai paperclip-backup-cleanup \
  -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].image}{"\n"}'   # docker.io/bitnamilegacy/kubectl:1.33.4
mise exec -- kubectl get deploy -n ai paperclip -o jsonpath='{.spec.replicas}{"\n"}'   # must be 1

# b) the target tags exist
curl -sL -o /dev/null -w 'kubectl v1.36.0 -> %{http_code}\n' \
  -H "Accept: application/vnd.docker.distribution.manifest.list.v2+json" \
  https://registry.k8s.io/v2/kubectl/manifests/v1.36.0                                  # 200
curl -s -o /dev/null -w 'busybox:stable -> %{http_code}\n' \
  https://hub.docker.com/v2/repositories/library/busybox/tags/stable                    # 200

# c) NO job may be mid-flight — a run in progress owns paperclip's replica count
mise exec -- kubectl get jobs -n ai | grep paperclip-backup-cleanup || echo "no active job (expected)"
mise exec -- kubectl get pods -n ai | grep paperclip

# d) record the current backup inventory so you can prove the new retention
#    kept the right files (read-only; do NOT delete anything here)
POD=$(mise exec -- kubectl get pods -n ai -l app.kubernetes.io/name=paperclip -o jsonpath='{.items[0].metadata.name}')
mise exec -- kubectl exec -n ai $POD -- \
  sh -c 'ls -la /paperclip/instances/default/data/backups/*.sql 2>/dev/null | wc -l; \
         ls -la /paperclip/instances/default/data/backups/ 2>/dev/null | tail -20'

# e) falco baseline — how many "Contact K8S API" events are we at now
mise exec -- kubectl get ds -n security falco \
  -o jsonpath='{.status.numberReady}/{.status.desiredNumberScheduled}{"\n"}'            # 3/3
mise exec -- kubectl get ds -n security falco -o jsonpath='{.spec.template.metadata.annotations.checksum/rules}{"\n"}'
# record this checksum — it MUST change after step 2, that is how you know the rules rolled.

# f) no in-flight reconcile
mise exec -- flux get kustomizations -A | awk 'NR==1 || $5!="True"'
```

## 3) Steps

1. **Marker** — paperclip briefly scales to 0 during the next nightly run; Falco
   restarts on all three nodes:
   ```bash
   runbooks/update-marker.sh add paperclip ai 2 "backup-cleanup: bitnamilegacy/kubectl -> registry.k8s.io/kubectl v1.36.0"
   runbooks/update-marker.sh add falco security 2 "k8s-api-noise macro repointed to registry.k8s.io/kubectl"
   ```

2. **Falco FIRST** — edit `kubernetes/apps/security/falco/app/helmrelease.yaml`,
   `customRules:` → `k8s-api-noise.yaml`, and replace the bitnamilegacy entry:
   ```yaml
        - macro: user_known_contact_k8s_api_server_activities
          condition: >
            (container.image.repository = ghcr.io/nachtschatt3n/ai-sre or
             container.image.repository = registry.k8s.io/kubectl or
             container.image.repository startswith docker.io/longhornio/)
          override:
            condition: replace
   ```
   Update the comment block above it so it still reads true (the sources listed
   are "the ai-sre agent + standalone kubectl pods"). Commit and push on `main`:
   ```bash
   git add kubernetes/apps/security/falco/app/helmrelease.yaml
   git commit -m "chore(falco): repoint k8s-api-noise macro at registry.k8s.io/kubectl"
   git push
   ```
   **Wait for the DaemonSet to roll before step 3** — `checksum/rules` must move
   and all three pods must be Ready again (see Verification a).

3. **Rewrite the CronJob** in
   `kubernetes/apps/ai/paperclip/app/backup-cleanup.yaml`. Leave the
   ServiceAccount, Role, RoleBinding, `schedule`, `concurrencyPolicy`,
   `ttlSecondsAfterFinished`, affinity, securityContext and volumes **exactly as
   they are**; replace only the `containers:` block with:

   ```yaml
             initContainers:
               # bitnamilegacy is an ARCHIVED registry (last push 2025-08-28, no
               # future security fixes) and docker.io/bitnami/kubectl publishes no
               # semver tags. Security driver tracked as F-2d25e586.
               # registry.k8s.io/kubectl is distroless (entrypoint /bin/kubectl,
               # NO shell), so the old single bash container is split by
               # capability: kubectl steps use the k8s image, the file cleanup
               # uses busybox and needs no cluster credentials at all.
               # Ordering is the safety net: k8s runs initContainers to
               # completion, in order, before the main container — so `scale-up`
               # as the MAIN container replaces the old `trap restore EXIT`.
               - name: scale-down
                 image: registry.k8s.io/kubectl:v1.36.0
                 args: ["scale", "deployment/paperclip", "-n", "ai", "--replicas=0"]
                 resources:
                   requests: {cpu: 10m, memory: 32Mi}
                   limits:   {cpu: 100m, memory: 64Mi}
               - name: wait-terminated
                 image: registry.k8s.io/kubectl:v1.36.0
                 args:
                   - "wait"
                   - "--for=delete"
                   - "pod"
                   - "-n"
                   - "ai"
                   - "-l"
                   - "app.kubernetes.io/name=paperclip"
                   - "--timeout=120s"
                 resources:
                   requests: {cpu: 10m, memory: 32Mi}
                   limits:   {cpu: 100m, memory: 64Mi}
               - name: cleanup
                 image: busybox:stable
                 command:
                   - /bin/sh
                   - -c
                   - |
                     # Never fail: a cleanup error must not block scale-up.
                     DIR=/paperclip/instances/default/data/backups
                     if [ ! -d "$DIR" ]; then
                       echo "No backups directory, nothing to clean"
                       exit 0
                     fi
                     before=$(find "$DIR" -maxdepth 1 -name '*.sql' | wc -l)
                     find "$DIR" -maxdepth 1 -name '*.sql' -mtime +7 -print -delete || true
                     after=$(find "$DIR" -maxdepth 1 -name '*.sql' | wc -l)
                     echo "backups: $before -> $after (removed $((before - after)) older than 7 days)"
                     exit 0
                 resources:
                   requests: {cpu: 10m, memory: 32Mi}
                   limits:   {cpu: 100m, memory: 64Mi}
                 volumeMounts:
                   - name: data
                     mountPath: /paperclip
             containers:
               # Runs ONLY after every initContainer succeeded — this is the
               # guaranteed restore of paperclip's replica count.
               - name: scale-up
                 image: registry.k8s.io/kubectl:v1.36.0
                 args: ["scale", "deployment/paperclip", "-n", "ai", "--replicas=1"]
                 resources:
                   requests: {cpu: 10m, memory: 32Mi}
                   limits:   {cpu: 100m, memory: 64Mi}
   ```

   Notes for the executor:
   - `securityContext: runAsUser/runAsGroup/fsGroup: 1000` stays at pod level and
     applies to all four containers. `registry.k8s.io/kubectl` declares `User: 0`
     in its config but is overridden by the pod securityContext — it does not
     need root.
   - The `data` volumeMount moves to the `cleanup` initContainer **only**. The
     kubectl containers must not mount the PVC.
   - `kubectl wait --for=delete` exits non-zero with "no matching resources
     found" if paperclip was **already** at 0 replicas. In that case the job
     fails without having changed anything — paperclip was already down, so
     this is not a regression, but it will surface as a failed Job. Accepted
     over swallowing errors with a shell.

4. **Validate and push**:
   ```bash
   mise exec -- kubeconform -summary -exit-on-error -ignore-missing-schemas \
     kubernetes/apps/ai/paperclip
   git add kubernetes/apps/ai/paperclip/app/backup-cleanup.yaml
   git commit -m "feat(paperclip): move backup-cleanup off archived bitnamilegacy to registry.k8s.io/kubectl v1.36.0"
   git push
   ```

5. **Prove it with a manual run** — do not wait for 04:00:
   ```bash
   mise exec -- kubectl create job -n ai --from=cronjob/paperclip-backup-cleanup \
     paperclip-cleanup-verify-$(date +%Y%m%d%H%M)
   ```

6. Clear the markers on success:
   ```bash
   runbooks/update-marker.sh clear paperclip
   runbooks/update-marker.sh clear falco
   ```

## 4) Verification

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) Falco actually reloaded (do this BEFORE touching the CronJob)
mise exec -- kubectl get ds -n security falco \
  -o jsonpath='{.spec.template.metadata.annotations.checksum/rules}{"\n"}'   # MUST differ from pre-check (e)
mise exec -- kubectl rollout status ds/falco -n security --timeout=300s
mise exec -- kubectl logs -n security ds/falco --since=5m | grep -iE 'error|invalid|rule' | head
# an unparseable macro makes falco refuse to load rules — that is the failure to catch here.

# b) the CronJob spec is what we intended, on the intended images
mise exec -- kubectl get cronjob -n ai paperclip-backup-cleanup -o json | python3 -c "
import sys, json
s = json.load(sys.stdin)['spec']['jobTemplate']['spec']['template']['spec']
for c in s.get('initContainers', []): print('INIT', c['name'], c['image'])
for c in s['containers']:             print('MAIN', c['name'], c['image'])"
# expect scale-down/wait-terminated/cleanup INIT + scale-up MAIN.
# NOTHING may still say bitnamilegacy.

# c) THE load-bearing check — the manual run completed AND paperclip came back
JOB=$(mise exec -- kubectl get jobs -n ai -o name | grep paperclip-cleanup-verify | tail -1)
mise exec -- kubectl wait --for=condition=complete $JOB -n ai --timeout=600s
mise exec -- kubectl logs -n ai $JOB --all-containers --prefix | tail -30
mise exec -- kubectl get deploy -n ai paperclip -o jsonpath='{.spec.replicas} {.status.readyReplicas}{"\n"}'   # 1 1
mise exec -- kubectl rollout status deploy/paperclip -n ai --timeout=300s
# A job that "succeeded" while paperclip sits at 0 replicas is THE failure to
# catch: the scale-up container is the whole safety design.

# d) retention did the right thing — compare against pre-check (d)
POD=$(mise exec -- kubectl get pods -n ai -l app.kubernetes.io/name=paperclip -o jsonpath='{.items[0].metadata.name}')
mise exec -- kubectl exec -n ai $POD -- \
  sh -c 'ls -la /paperclip/instances/default/data/backups/ | tail -20'
# Expect: nothing newer than 7 days removed. If MORE files vanished than the old
# filename-parse would have removed, stop and restore from the Longhorn backup
# of paperclip-data before running again.

# e) Falco is not newly noisy about this pod
mise exec -- kubectl logs -n security ds/falco --since=30m \
  | grep -i 'Contact K8S API' | grep -i kubectl | head
# expect empty — the macro allowlists registry.k8s.io/kubectl.

# f) no fixable criticals introduced by the new images
mise exec -- trivy image registry.k8s.io/kubectl:v1.36.0 --severity CRITICAL --ignore-unfixed | tail -20
mise exec -- trivy image busybox:stable            --severity CRITICAL --ignore-unfixed | tail -20
```

Success = Falco 3/3 Ready with a new `checksum/rules` and no rule-load errors;
no `bitnamilegacy` reference anywhere in `kubernetes/apps/ai/paperclip` or
`kubernetes/apps/security/falco`; the manual Job Complete; `paperclip` back at
1/1; the backup inventory reduced only by files older than 7 days; no new Falco
"Contact K8S API" events.

## 5) Rollback

Two independent commits — revert the one that failed, newest first.

```bash
cd /Users/mu/code/cberg-home-nextgen

# CronJob rewrite failed:
git revert --no-edit <cronjob-commit-sha>
git push
mise exec -- kubectl get cronjob -n ai paperclip-backup-cleanup \
  -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].image}{"\n"}'   # back to bitnamilegacy/kubectl:1.33.4

# Falco macro change failed (rules would not load):
git revert --no-edit <falco-commit-sha>
git push
mise exec -- kubectl rollout status ds/falco -n security --timeout=300s
mise exec -- kubectl logs -n security ds/falco --since=5m | grep -iE 'error|invalid' | head   # clean
```

**If a failed run left `paperclip` at 0 replicas**, that is a cluster state the
revert does NOT fix — restore it explicitly and confirm:
```bash
mise exec -- kubectl scale deployment/paperclip -n ai --replicas=1
mise exec -- kubectl rollout status deploy/paperclip -n ai --timeout=300s
```

**Nothing to restore data-wise** unless step (d) shows over-deletion; the
CronJob only removes files it considers expired. `paperclip-data` is a
`longhorn` (dynamic) RWO volume backed up nightly by
`storage/backup-of-all-volumes` — restore per `docs/sops/backup.md` §"Restore
from Backup" if the retention change removed more than intended.

Confirmed back = old image in the CronJob spec, Falco 3/3 with the previous
`checksum/rules`, `paperclip` 1/1 Ready.

## 6) Interference notes

- **`shared: [falco]`** — this rolls the Falco DaemonSet on all three nodes.
  Host runtime-security detection is briefly absent per node during the roll.
  Do not co-schedule with any other plan that edits `falco` `customRules`, and
  do not co-schedule with a node-drain/reboot plan (Falco would roll twice).
- **Ordering inside the window is not optional:** Falco commit → verify rolled →
  CronJob commit. Reversed, the new image runs unallowlisted and generates
  exactly the alert class the macro exists to suppress.
- **Do not run while a `paperclip-backup-cleanup` Job is in flight.** Two jobs
  fighting over `deployment/paperclip`'s replica count is the one way to strand
  it at 0. `concurrencyPolicy: Forbid` protects the scheduled runs from each
  other but not from a manual `kubectl create job`.
- **Independent of phases 2–4.** This plan shares no namespace, datastore or
  chart with the office MariaDB/Redis work and may run before, after, or between
  them. It is listed first only because it is the cheapest.
- The three later phases (`bitnamilegacy-exit-office-redis`,
  `bitnamilegacy-exit-paperless-db`, `bitnamilegacy-exit-nextcloud-db`) assume
  this one has run when they assert "no `bitnamilegacy` image runs anywhere in
  the cluster". Running them first is fine; that final assertion just fails.
