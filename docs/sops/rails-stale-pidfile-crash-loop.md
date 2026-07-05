# SOP: Rails/Puma Stale-Pidfile Crash-Loop Recovery

> Description: Recover (and prevent recurrence of) a Rails/Puma container stuck
> in `CrashLoopBackOff` after a restart because `tmp/pids/server.pid` survived
> on a persistent volume and Puma refuses to boot with "A server is already
> running".
> Version: `2026.07.05`
> Last Updated: `2026-07-05`
> Owner: `cluster-ops`

---

## 1) Description

Rails/Puma writes its own PID to `tmp/pids/server.pid` on boot and refuses to
start a second time while that file exists and looks live. If the app's data
directory (including `tmp/`) lives on a **persistent volume** (Longhorn PVC),
the pidfile survives a pod restart even though the previous Puma process is
gone — the new pod's first boot then immediately exits with "A server is
already running. Check … or delete … to continue.", which Kubernetes reports
as `KubePodCrashLooping` / `KubeDeploymentReplicasMismatch`.

Modern Rails (`rails new` since 7.1) generates a Docker `ENTRYPOINT` script
that already does `rm -f tmp/pids/server.pid` before exec'ing the real command
— so most Rails images are safe **by default**. The failure mode in this SOP
only bites apps whose Kubernetes `command:` **overrides that entrypoint** to
run custom boot logic (e.g. `bin/rails db:prepare && bundle exec rails server
...`) directly — the custom command bypasses the image's built-in guard.

- Scope: any HelmRelease running a Rails/Puma image with `tmp/` (or the whole
  app root) on a PVC **and** a custom `command:`/`args:` override.
- Prerequisites: `kubectl` access to the namespace; `talosctl`/GitOps push
  access if editing the HelmRelease.
- Out of scope: apps that don't override `command:` (they already get the
  image's default entrypoint guard) and non-persistent (`emptyDir`) tmp dirs
  (pidfile doesn't survive a restart there either way).

---

## 2) Overview

| Setting | Value |
|---------|-------|
| First hit | `my-software-development/absenty` (dev), 2026-06-22, commit `4239c8a8` |
| Symptom | `KubePodCrashLooping` + `KubeDeploymentReplicasMismatch`; pod log ends with `A server is already running. Check .../tmp/pids/server.pid` |
| Root cause | Custom `command:` runs `rails server`/`puma` directly, skipping the Rails-generated entrypoint's stale-pidfile cleanup |
| Fix | Prepend `rm -f tmp/pids/server.pid` (or the app's actual pid path) to the custom command chain |
| Currently NOT exposed | `office/sure`, `office/arag-web` — both Rails 8, both **use the image's default entrypoint** (no `command:` override on the main container), confirmed 2026-07-05. Re-check this SOP if either app's `command:`/`entrypoint` is ever customized. |

---

## 3) Blueprints

- Affected pattern lives in each app's `helmrelease.yaml`, `spec.values.controllers.<name>.containers.<name>.command` (app-template chart) or the equivalent bjw-s `command:` override block.
- No dedicated CRD/config — this is a plain container-command fix, not GitOps policy.

```yaml
# The vulnerable pattern (bypasses the Rails entrypoint's own pidfile cleanup):
command:
  - bash
  - -lc
  - bundle config set --local path '/bundle' && bin/rails db:prepare && bundle exec rails server -b 0.0.0.0 -p 3000

# The fix — prepend the cleanup, keep everything else identical:
command:
  - bash
  - -lc
  - rm -f tmp/pids/server.pid && bundle config set --local path '/bundle' && bin/rails db:prepare && bundle exec rails server -b 0.0.0.0 -p 3000
```

---

## 4) Operational Instructions

1. Confirm the crash-loop matches this signature (see Diagnose Examples below) before applying the fix — other Puma boot failures (missing `SECRET_KEY_BASE`, DB not reachable, migration pending) look similar in `KubePodCrashLooping` but need a different fix.
2. Edit the app's `helmrelease.yaml`: prepend `rm -f tmp/pids/server.pid && ` (adjust the path if the app sets a custom `pidfile` in `config/puma.rb`) to the existing `command:` string. Do not otherwise change the command.
3. Commit on `main`, push (GitOps — no direct `kubectl edit`).
4. `flux reconcile source git flux-system` then `flux reconcile hr <app> -n <namespace>`.
5. Watch the pod come up clean (see Verification Tests).

```bash
git add kubernetes/apps/<ns>/<app>/app/helmrelease.yaml
git commit -m "fix(<app>): clear stale Rails pidfile before boot"
git push
flux reconcile source git flux-system
flux reconcile hr <app> -n <namespace>
```

---

## 5) Examples

### Example A: absenty-dev (the original incident)

Custom command ran `bundle exec rails server` directly on a Longhorn-backed
PVC. A pod restart (unrelated cause) left `tmp/pids/server.pid` behind; the
next boot crash-looped. Fixed in commit `4239c8a8` by prepending the `rm -f`.
Prod (`absenty` proper) uses a different entrypoint and was never affected.

### Example B: a future Rails app that DOES override command

If you deploy a new Rails app with a custom `command:` that runs
`bundle exec rails server` / `bundle exec puma` directly (instead of the
image's default `ENTRYPOINT`), add the `rm -f tmp/pids/server.pid` prefix
**at deploy time**, before it ever crash-loops — don't wait for the incident.

---

## 6) Verification Tests

### Test 1: pod boots clean after the fix

```bash
kubectl get pods -n <namespace> -l app.kubernetes.io/name=<app>
kubectl logs -n <namespace> <pod> --tail=20
```

Expected:
- Pod reaches `1/1 Running`, 0 (or non-incrementing) restarts.
- Log shows the Rails/Puma boot banner, not "A server is already running".

If failed:
- Confirm the edited `command:` actually reconciled (`kubectl get pod -o
  jsonpath='{.spec.containers[0].command}'`); check for a typo in the `rm -f`
  path vs. the app's actual configured pidfile.

### Test 2: pidfile doesn't survive a forced restart

```bash
kubectl delete pod -n <namespace> -l app.kubernetes.io/name=<app>
kubectl get pods -n <namespace> -l app.kubernetes.io/name=<app> --watch
```

Expected:
- New pod reaches `Running` without crash-looping (proves the fix holds
  across a restart, not just the first boot after the edit).

---

## 7) Troubleshooting

| Symptom | Likely Cause | First Fix |
|---------|--------------|-----------|
| Still "server already running" after the fix | Wrong pidfile path (custom `config/puma.rb` sets a non-default path) | `grep -n pidfile <app>/config/puma.rb`; adjust the `rm -f` path to match |
| Crash-loop persists but log doesn't mention pidfile | Different root cause (DB unreachable, missing secret, pending migration) | Read the actual log tail — don't apply this fix blindly |
| Fix "worked" but only once | `command:` edit didn't survive a chart/values re-render (e.g. Renovate bumped the chart and the postRenderer patch path changed) | Re-diff the rendered manifest (`helm template`) against what's live |

```bash
kubectl logs -n <namespace> <pod> --previous --tail=30
```

---

## 8) Diagnose Examples

### Diagnose Example 1: confirm this IS the stale-pidfile pattern

```bash
kubectl logs -n <namespace> <pod> --previous --tail=15 | grep -i "already running\|pids/server.pid"
```

Expected:
- A line containing `A server is already running. Check /rails/tmp/pids/server.pid`
  (or the app's actual Rails root) confirms this SOP applies.

If unclear:
- No such line → this is a different crash-loop cause; check `SECRET_KEY_BASE`,
  DB connectivity (`wait-for-pg`/`wait-for-redis` init containers succeeding?),
  and pending migrations instead.

### Diagnose Example 2: check whether an app is currently exposed to this risk

```bash
grep -n "command:\|entrypoint" kubernetes/apps/<ns>/<app>/app/helmrelease.yaml
```

Expected:
- No `command:` override on the main container → the app uses the image's
  default Rails entrypoint (already guards against this) → not currently at
  risk.
- A `command:` that runs `rails server`/`bundle exec puma` directly → at risk;
  confirm it includes `rm -f tmp/pids/server.pid` (or add it proactively).

---

## 9) Health Check

```bash
kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded \
  -o custom-columns=NS:.metadata.namespace,POD:.metadata.name,RESTARTS:.status.containerStatuses[0].restartCount \
  2>/dev/null | grep -iE "absenty|sure|arag-web"
```

Expected:
- No matching rows (all three Rails apps `Running`, low/zero restart count).

---

## 10) Security Check

```bash
grep -n "command:" kubernetes/apps/*/*/app/helmrelease.yaml | grep -i "rails\|puma"
```

Expected:
- No secrets/credentials embedded in the `command:` string (this fix only
  ever adds a local `rm -f`, never touches env/secrets).

---

## 11) Rollback Plan

```bash
git revert <commit-sha>
git push
flux reconcile source git flux-system
flux reconcile hr <app> -n <namespace>
```

Removing the `rm -f tmp/pids/server.pid` prefix re-exposes the app to this
crash-loop on the next restart that leaves a stale pidfile — only roll back if
the prefix itself is suspected of causing a *different* regression (it has
none known; the fix is inert on a clean boot).

---

## 12) References

- Incident: commit `4239c8a8` (`fix(absenty-dev): clear stale Rails pidfile before boot`)
- `kubernetes/apps/my-software-development/absenty/app/helmrelease.yaml`
- Rails default Docker entrypoint (generated by `rails new` since 7.1) — the
  upstream pattern this SOP's fix mirrors for apps that had to override it.
