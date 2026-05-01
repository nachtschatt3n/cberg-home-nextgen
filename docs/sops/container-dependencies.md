# SOP: Container Dependency Wait-For Pattern

> Description: Standard pattern for ensuring an app pod waits for its stateful dependencies (Postgres, Redis, Mongo, S3, etc.) to be reachable before its primary container starts. Eliminates cold-start crashloops when dependencies and their consumers reschedule on the same Talos upgrade or node reboot.
> Version: `2026.05.01`
> Last Updated: `2026-05-01`
> Owner: `cluster-ops`

---

## 1) Description

When a Talos node reboots (e.g., during the v1.11.0 → v1.13.0 rolling upgrade on 2026-04-30) or the cluster cold-starts, all pods on that node are evicted and rescheduled in parallel. Apps that connect to a database/cache often start their main process before the database is reachable, hit a connect-timeout-FATAL, exit, and enter `CrashLoopBackOff`. The deployment then takes 5+ minutes to recover (kubelet backoff is exponential up to 5 min).

The fix is a one-line `initContainer` per app that blocks the main container until the dependency's TCP port is open. This SOP documents the pattern + applies it to the high-priority apps.

**Status as of 2026-05-01** — wait-for is wired in:
- `office/affine`, `ai/paperclip` (seed implementations, bjw-s app-template)
- `office/paperless-ngx`, `office/nextcloud`, `kube-system/authentik`, `office/penpot`, `ai/langfuse`, `office/sure` (added 2026-05-01)
- `databases/superset` — chart already ships default `wait-for-postgres` init; no edit needed
- `ai/openclaw`, `home-automation/n8n` — no external dep (SQLite-only); skipped

- **Scope**: every app with one or more upstream stateful dependencies (postgres, redis, mongo, mariadb, mqtt, MinIO, S3 endpoints, etc.)
- **Prerequisites**: app uses bjw-s `app-template` Helm chart (most do), OR a regular Deployment/StatefulSet manifest where `spec.template.spec.initContainers` can be set.
- **Out of scope**: Flux-level `dependsOn` between HelmReleases — that's already widely used (47 helmreleases). This SOP is about *pod-level* startup ordering, which Flux doesn't enforce.

---

## 2) Overview

| Setting | Value |
|---------|-------|
| Pattern | `initContainers.wait-for-<dep>` running `nc -z <host> <port>` in a busy loop |
| Image | `ghcr.io/groundnuty/k8s-wait-for:v2.1` (lightweight) OR `busybox:stable` for plain nc |
| Timeout | 10 min default (allow time for cluster cold-start) |
| Retry interval | 2 s |
| Failure mode | If dep never comes up: pod stays in `Init:0/1`, surfaces as `KubePodNotReady` alert after 15 min — much better signal than CrashLoopBackOff noise |

---

## 3) Blueprints

For apps using `bjw-s app-template` (most of this cluster), add to the existing `helmrelease.yaml`:

```yaml
controllers:
  <app>:
    initContainers:
      wait-for-postgres:
        image:
          repository: busybox
          tag: stable
        command:
          - sh
          - -c
          - |
            until nc -z paperclip-postgresql 5432; do
              echo "waiting for paperclip-postgresql:5432..."
              sleep 2
            done
        # Inherits podSecurityContext from the controller; no special privileges.
    containers:
      app: { ... }
```

For multi-dep apps (e.g., needs both postgres AND redis):

```yaml
initContainers:
  wait-for-postgres:
    image: { repository: busybox, tag: stable }
    command: [sh, -c, "until nc -z affine-pg 5432; do sleep 2; done"]
  wait-for-redis:
    image: { repository: busybox, tag: stable }
    command: [sh, -c, "until nc -z affine-redis-master 6379; do sleep 2; done"]
```

For raw Deployment/StatefulSet manifests, set `spec.template.spec.initContainers` directly with the same pattern.

### Naming convention

- `wait-for-<dep-svc-name>` — clear, greppable, sortable.
- One initContainer per dep. Don't combine into a single `wait-all` — failures are easier to diagnose when each is named.

### What NOT to do

- ❌ Don't use `kubectl wait` in the initContainer — requires API server creds which may not exist for the pod.
- ❌ Don't use a long fixed `sleep` — it adds cold-start latency for the happy path.
- ❌ Don't put the wait in the main container's entrypoint — that breaks the kubelet's backoff/probe semantics.

---

## 4) Operational Instructions

### Audit current state

```bash
# How many helmreleases use initContainers?
grep -lr "initContainers:" kubernetes/apps/ | wc -l

# Apps that currently CrashLoopBackOff after a reboot are good candidates
mise exec -- kubectl get pods -A --no-headers | awk '$4 == "CrashLoopBackOff"'
```

### Apply to a single app

1. Identify the dep: read the helmrelease, find the `host:` / `connectionString` config.
2. Find the dep's k8s Service name: `kubectl -n <ns> get svc | grep <dep>`.
3. Edit the app's `helmrelease.yaml` — add the `initContainers.wait-for-<dep>` block per the blueprint above.
4. Commit + push. Flux reconciles, app pod restarts with the new init container.
5. Verify the next time the app's pod restarts, it transitions through `Init:0/1` → `1/1 Running` cleanly.

### Bulk apply (priority order)

Apps that crashlooped after the 2026-04-30 upgrade — apply first:
- `office/paperless-ngx` (paperless-mariadb, paperless-redis)
- `office/nextcloud` (nextcloud-mariadb, nextcloud-redis)
- `office/penpot` (penpot-postgresql, penpot-redis)
- `databases/superset` (superset-postgresql, superset-redis)
- `kube-system/authentik` (authentik-postgresql, authentik-redis)
- `ai/langfuse` (langfuse-postgresql, langfuse-redis, langfuse-clickhouse, langfuse-minio)
- `ai/paperclip` (paperclip-postgresql)
- `ai/openclaw` (openclaw-postgresql)
- `office/sure` (sure-pg, sure-redis)
- `office/actual-budget` (no deps — skip)
- `office/affine` (affine-pg, affine-redis)
- `home-automation/n8n` (n8n-postgresql)

---

## 5) Examples

### Example A: paperclip (single postgres dep)

`kubernetes/apps/ai/paperclip/app/helmrelease.yaml` — under `controllers.paperclip.initContainers`:

```yaml
initContainers:
  # Existing init container (mise-install) stays first
  mise-install: { ... }
  # NEW
  wait-for-postgres:
    image:
      repository: busybox
      tag: stable
    command:
      - sh
      - -c
      - |
        until nc -z paperclip-postgresql 5432; do
          echo "waiting for paperclip-postgresql:5432..."
          sleep 2
        done
```

### Example B: affine (postgres + redis)

`kubernetes/apps/office/affine/app/helmrelease.yaml`:

```yaml
initContainers:
  wait-for-postgres:
    image: { repository: busybox, tag: stable }
    command: [sh, -c, "until nc -z affine-pg 5432; do echo waiting pg; sleep 2; done"]
  wait-for-redis:
    image: { repository: busybox, tag: stable }
    command: [sh, -c, "until nc -z affine-redis-master 6379; do echo waiting redis; sleep 2; done"]
```

---

## 6) Verification Tests

### Test 1: pod transitions through Init phase on cold-start

```bash
# Force a clean restart
mise exec -- kubectl -n <ns> rollout restart deploy <app>

# Watch the phase progression
mise exec -- kubectl -n <ns> get pods -l app.kubernetes.io/instance=<app> --watch
```

**Expected**: `0/N` → `Init:0/1` → `Init:1/1` → `1/N Running` → `N/N Running`. The init container's logs should show "waiting" lines that stop once the dep is up.

### Test 2: dep-down isolation

```bash
# Scale dep down briefly
mise exec -- kubectl -n <ns> scale deploy <dep-app> --replicas=0

# Restart the consumer
mise exec -- kubectl -n <ns> rollout restart deploy <app>

# Consumer pod should sit in Init:0/1 (not CrashLoopBackOff)
mise exec -- kubectl -n <ns> get pods -l app.kubernetes.io/instance=<app>

# Bring dep back, consumer pod transitions to Running
mise exec -- kubectl -n <ns> scale deploy <dep-app> --replicas=1
```

**Expected**: consumer never enters `CrashLoopBackOff`. Stays in `Init:0/1` until dep is reachable, then proceeds.

### Test 3: cluster cold-start (full cluster reboot or major upgrade)

After a node reboot or cluster-wide upgrade, audit `kubectl get pods -A --no-headers | awk '$4 == "CrashLoopBackOff"'`. Apps that have the wait-for pattern should be absent.

---

## 7) Troubleshooting

| Symptom | Likely Cause | First Fix |
|---|---|---|
| Init container stuck `Init:0/1` for >15 min | Dep service really isn't coming up | Check `kubectl -n <dep-ns> get pods -l app.kubernetes.io/instance=<dep>`; verify dep is in `Running` state |
| `nc: command not found` | Container image lacks netcat | Use `busybox` or `nicolaka/netshoot` |
| Wait fires forever even after dep is Running | Wrong service name or port | `kubectl -n <ns> get svc` to confirm; common gotcha: `<app>-postgresql` vs `<app>-postgres` |
| Pod shows `Init:RunContainerError` | Init container has a syntax error or bad image | `kubectl -n <ns> describe pod <pod>` to see the failure reason |
| Cross-namespace dep | Service DNS needs FQDN | Use `<svc>.<ns>.svc.cluster.local:<port>` instead of bare `<svc>` |

```bash
# Quick debug
mise exec -- kubectl -n <ns> describe pod <pod>
mise exec -- kubectl -n <ns> logs <pod> -c wait-for-<dep>
mise exec -- kubectl -n <ns> get endpoints <dep-svc>   # verify dep has endpoints
```

---

## 8) Diagnose Examples

### After 2026-04-30 Talos v1.11→v1.13 upgrade

Pods stuck in CrashLoopBackOff post-upgrade because they restarted before their stateful deps:
- `paperless-ngx` waits for `paperless-mariadb` + `paperless-redis`
- `affine` waits for `affine-pg` + `affine-redis`
- `nextcloud` waits for `nextcloud-mariadb` + `nextcloud-redis`

Without this pattern, these spent 5–10 min cycling through CrashLoopBackOff exponential backoff. With the pattern, they sit cleanly in `Init:0/1` and transition to Running as soon as the dep's Service has endpoints.

---

## 9) Health Check

Run after any cluster-wide reboot to confirm the pattern is helping:

```bash
# Count of currently-CrashLoopBackOff pods 5 min after reboot
mise exec -- kubectl get pods -A --no-headers | awk '$4 == "CrashLoopBackOff"' | wc -l

# List of apps that are still in CrashLoopBackOff after 10 min — these are candidates for wait-for additions
mise exec -- kubectl get pods -A --no-headers | awk '$4 == "CrashLoopBackOff" && $5+0 > 600' | awk '{print $1}'
```

**Expected**: count drops materially after applying the pattern to the 12 priority apps.

---

## 10) Security Check

The wait-for pattern uses a vanilla `busybox` image — no secrets, no API access, no host paths. Per CLAUDE.md performance/security trade-off rules, this is unconditionally safe.

```bash
# Confirm wait-for containers don't request privileged
mise exec -- kubectl get pods -A -o json | python3 -c "
import sys, json
data = json.load(sys.stdin)
for p in data['items']:
    for c in (p['spec'].get('initContainers') or []):
        if not c['name'].startswith('wait-for'): continue
        sc = c.get('securityContext', {}) or {}
        if sc.get('privileged'): print(f'  WARN: {p[\"metadata\"][\"namespace\"]}/{p[\"metadata\"][\"name\"]} {c[\"name\"]} privileged')
"
# Expected: no output
```

---

## 11) Rollback Plan

If a wait-for pattern is itself faulty (wrong service name or port → app stuck in Init forever):

```bash
# Single-app rollback
git revert <wait-for-commit>
git push
# Flux reconciles; app's previous helmrelease (without the wait) is reapplied.

# Or temporarily delete the init container via kubectl edit (loses on next Flux reconcile)
mise exec -- kubectl -n <ns> edit deploy <app>   # remove the wait-for-<dep> block
```

The pattern is purely additive — removing it returns the app to its previous (crash-on-cold-start) behavior.

---

## 12) References

- Kubernetes initContainers: <https://kubernetes.io/docs/concepts/workloads/pods/init-containers/>
- bjw-s app-template `initContainers`: <https://bjw-s.github.io/helm-charts/docs/app-template/#init-containers>
- 2026-04-30 incident: post-Talos-v1.13-upgrade audit found 9 apps in CrashLoopBackOff for 10+ min, all due to dep-not-ready cold-starts — see git commits between `676531ac` and `25f26a7a`.

---

## Version History

- `2026.04.30`: Initial SOP — wait-for pattern documented + applied to high-priority apps after Talos v1.13 upgrade exposed the gap.
