# SOP: Container Dependency Wait-For Pattern

> Description: Standard pattern for ensuring an app pod waits for its stateful dependencies (Postgres, Redis, Mongo, S3, etc.) to be reachable before its primary container starts. Eliminates cold-start crashloops when dependencies and their consumers reschedule on the same Talos upgrade or node reboot.
> Version: `2026.09.08`
> Last Updated: `2026-09-08`
> Owner: `cluster-ops`

---

## 1) Description

When a Talos node reboots (e.g., during the v1.11.0 → v1.13.0 rolling upgrade on 2026-04-30) or the cluster cold-starts, all pods on that node are evicted and rescheduled in parallel. Apps that connect to a database/cache often start their main process before the database is reachable, hit a connect-timeout-FATAL, exit, and enter `CrashLoopBackOff`. The deployment then takes 5+ minutes to recover (kubelet backoff is exponential up to 5 min).

The fix is a one-line `initContainer` per app that blocks the main container until the dependency's TCP port is open. This SOP documents the pattern + applies it to the high-priority apps.

**Status as of 2026-05-01** — wait-for is wired in:
- `office/affine`, `ai/paperclip` (seed implementations, bjw-s app-template)
- `office/paperless-ngx`, `office/nextcloud`, `kube-system/authentik`, `office/penpot`, `office/sure` (added 2026-05-01)
- `databases/superset` — ⚠️ **RECURRED 2026-09-08. This defect has now shipped
  TWICE, on two consecutive metadata-DB cutovers of the same app**, the second
  time with the rule below already written. See §4 "Datastore cutover checklist",
  which is what the prose here failed to be.

  **2026-09-08 (second occurrence).** Cutover `superset-pg` (17.11) →
  `superset-pg18` (18.6). Commit `d9863640` moved `DB_HOST` in
  `secret.sops.yaml`; that Secret is mounted by the MAIN containers only. The
  `wait-for-postgres` init container's *only* `envFrom` is the chart-generated
  `superset-env` Secret, built from `.Values.database.host`, which still said
  `superset-pg`. Net effect: the app ran on 18.6 while its startup gate probed
  the 17.11 instance that is scheduled for deletion — the gate was being
  protected by the artifact we intend to remove, and it was validating a
  database the app does not use. Fixed in `f297f4b5` (`database.host:
  superset-pg18`), so both env sources now agree and there is no precedence
  ambiguity left for the init containers or the `superset-init-db` hook. Caught
  post-hoc by the doc-agent and security-agent verification pass, before any
  restart could hit it — luck of timing, not a control.

  **2026-09-05 (first occurrence).** The chart DOES ship a
  `wait-for-postgres` init container, but it resolves its host from
  `.Values.supersetNode.connections.db_host` via `_helpers.tpl`, which defaulted
  to the BUNDLED `superset-postgresql`. After the metadata DB was cut over to
  `superset-pg`, four workloads (`superset`, `-worker`, `-celerybeat`, and the
  `superset-init-db` hook Job) were still waiting on the *old* host through the
  stale `superset-env.DB_HOST`. The init container was present and running — and
  pointed at the wrong database. "No edit needed" was wrong, and this belief is
  what armed the 2026-09-05 decommission: switching off the bundled Postgres
  would have left every init container blocking on a host that no longer
  existed. Fixed by pinning `database.host: superset-pg` (c4694b13) BEFORE
  `postgresql.enabled: false` (90539942).

  **Why the rule did not hold.** The 2026-09-05 wording said "any bundled-datastore
  exit must re-point the init container's host in the same change set". Both words
  narrowed it out of applicability on 2026-09-08: that cutover was not a *bundled*
  datastore exit (the bundled Postgres had already been retired) and the operator
  changing `DB_HOST` reasonably believed they *had* re-pointed the host — there was
  no signal that "the host" exists in two independent places. A rule stated as a
  principle gets reasoned about; a rule stated as a named check gets run. It is now
  the latter: §4 "Datastore cutover checklist", which names both env sources
  explicitly and does not depend on the word "bundled".
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

### Datastore cutover checklist — TWO env sources, always name both

**Run this whenever an app's database/cache HOST changes**: a new instance, a
major-version replacement running side by side, a rename, or a bundled-subchart
exit. It is not specific to "bundled" datastores. It has been missed twice on
`databases/superset` (2026-09-05, 2026-09-08) because the host lives in two
places that no single edit updates together.

**The two sources, by name.** In a Helm-chart app the init container and the
main container usually do NOT read the same Secret:

| Consumer | Reads | Set by |
|---|---|---|
| main containers (`superset`, `-worker`, `-celerybeat`) | the app's own SOPS Secret, e.g. `superset-secrets` → `DB_HOST` | `secret.sops.yaml` |
| `wait-for-postgres` / `wait-for-redis` **init** containers, and chart **hook Jobs** (`superset-init-db`) | the CHART-GENERATED Secret, e.g. `superset-env` → `DB_HOST` | `.Values.database.host` / `.Values.cache.host` in `helmrelease.yaml` |

Changing one and not the other is silent. The pods stay Ready, the app works,
and the only symptom is that the startup gate is validating the wrong database —
which stays invisible for exactly as long as the OLD host still resolves.

**Steps:**

1. **Enumerate every place the host string appears — before editing anything.**
   ```bash
   OLD=superset-pg; NEW=superset-pg18; APP=kubernetes/apps/databases/superset
   grep -rn "$OLD" "$APP"                                   # plaintext manifests
   mise exec -- sops -d "$APP/app/secret.sops.yaml" | grep -n "$OLD"   # SOPS side
   ```
   Expect **two or more** hits across **both** commands. One hit in only one of
   them is the defect, not a clean result.

2. **Change every hit in ONE change set.** Both `secret.sops.yaml` and the
   HelmRelease's `database.host` / `cache.host` go in the same commit, or in
   commits pushed together. A cutover that lands in two pushes has a window in
   which the gate guards the wrong instance.

3. **Assert agreement in the RENDERED objects, not in git.** The chart, not the
   file, decides what `superset-env` contains:
   ```bash
   NS=databases
   mise exec -- kubectl -n $NS get secret superset-env \
     -o jsonpath='{.data.DB_HOST}' | base64 -d; echo   # chart-generated
   mise exec -- kubectl -n $NS get secret superset-secrets \
     -o jsonpath='{.data.DB_HOST}' | base64 -d; echo   # app SOPS Secret
   ```
   **These two strings MUST be identical.** If they differ, stop — the init gate
   and the app are pointed at different databases.

4. **Prove the gate is EXERCISED, not merely present.** Roll the pods and read
   the init container's own log for the NEW host:
   ```bash
   mise exec -- kubectl -n $NS rollout restart deploy/superset
   mise exec -- kubectl -n $NS logs deploy/superset -c wait-for-postgres | tail -5
   ```
   The log must name `$NEW`. An init container that exists and is Running proves
   nothing about which host it is probing.

5. **Only then schedule the old instance's decommission.** Until steps 3 and 4
   pass, the old datastore is load-bearing: it is what the init gate is
   succeeding against, so deleting it converts a silent misconfiguration into a
   120 s hang and `exit 1` on every subsequent pod restart.

**Anti-pattern that caused both occurrences:** treating `DB_HOST` in the SOPS
Secret as "the" host. It is one of two. Grep for the OLD host name after the
edit — a zero-hit grep across both sources is the only evidence that matters.

### Bulk apply (priority order)

Apps that crashlooped after the 2026-04-30 upgrade — apply first:
- `office/paperless-ngx` (paperless-db, paperless-redis)
- `office/nextcloud` (nextcloud-mariadb, nextcloud-redis)
- `office/penpot` (penpot-postgresql, penpot-redis)
- `databases/superset` (superset-postgresql, superset-redis)
- `kube-system/authentik` (authentik-postgresql, authentik-redis)
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

### Test 3: init gate and app agree on the SAME host (run after any cutover)

```bash
NS=databases
CHART=$(mise exec -- kubectl -n $NS get secret superset-env      -o jsonpath='{.data.DB_HOST}' | base64 -d)
APPS=$( mise exec -- kubectl -n $NS get secret superset-secrets  -o jsonpath='{.data.DB_HOST}' | base64 -d)
echo "chart-generated superset-env DB_HOST = $CHART"
echo "app SOPS superset-secrets   DB_HOST = $APPS"
[ "$CHART" = "$APPS" ] && echo OK || echo "MISMATCH — init gate guards a different database than the app uses"
```

**Expected**: identical strings, `OK`.

**If failed**: `.Values.database.host` in `helmrelease.yaml` and `DB_HOST` in
`secret.sops.yaml` disagree. Do NOT decommission the old datastore until they
agree — see §4 "Datastore cutover checklist". This exact mismatch shipped on
2026-09-05 and again on 2026-09-08.

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
| App works, init gate passes, but a DB cutover just happened | The init container reads the CHART-generated Secret (`.Values.database.host`), the app reads the SOPS Secret (`DB_HOST`) — only one was moved | Compare both Secrets (Test 3); fix `helmrelease.yaml`; do not decommission the old DB until they match |
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
- `paperless-ngx` waits for `paperless-db:3306` + `paperless-redis:6379` (the bundled `paperless-mariadb` subchart was retired 2026-08-19 and its volume deleted 2026-08-30)
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

- `2026.09.08` — **RECURRENCE.** The same defect shipped again on the next
  `databases/superset` metadata-DB cutover (17.11 → 18.6), with the 2026-09-05
  rule already in this document: `d9863640` moved only the SOPS `DB_HOST`, so
  the init gate kept probing the instance being retained for rollback while the
  app ran on the new one (fixed in `f297f4b5`). The rule was stated as a
  principle about "bundled-datastore exits", which both narrowed it out of scope
  (nothing bundled was involved) and gave no hint that the host exists in two
  independent env sources. Replaced with §4 "Datastore cutover checklist", which
  names BOTH sources in a table, greps for the old host across both, asserts the
  two rendered Secrets are byte-identical, and requires reading the init log for
  the NEW host before the old instance may be decommissioned. Added Test 3 and a
  troubleshooting row for the mismatch.

- `2026.09.05` — CORRECTED the `databases/superset` status line. It claimed the
  chart's bundled `wait-for-postgres` init meant "no edit needed"; in fact the init
  resolved its host from the bundled Postgres, so after the metadata cutover four
  workloads were waiting on the wrong database. Added the generalised rule for
  bundled-datastore exits: re-point the init host in the same change set as the
  cutover, and verify it is exercised rather than merely present.

- `2026.04.30`: Initial SOP — wait-for pattern documented + applied to high-priority apps after Talos v1.13 upgrade exposed the gap.
