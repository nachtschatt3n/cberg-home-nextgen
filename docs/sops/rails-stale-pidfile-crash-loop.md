# SOP: Rails/Puma Stale-Pidfile Crash-Loop Recovery

> Description: Recover (and prevent recurrence of) a Rails/Puma container stuck
> in `CrashLoopBackOff` after a restart because `tmp/pids/server.pid` survived
> on a volume (emptyDir OR PVC) and the server refuses to boot with "A server
> is already running".
> Version: `2026.09.25`
> Last Updated: `2026-09-25`
> Owner: `cluster-ops`

---

## 1) Description

`rails server` writes its own PID to `tmp/pids/server.pid` on boot and refuses
to start while that file exists. If `tmp/` is on **any volume that outlives the
container**, a container that dies without a clean shutdown leaves the pidfile
behind. The next container then exits at once with "A server is already
running. Check … or delete … to continue.", which Kubernetes reports as
`KubePodCrashLooping` / `KubeDeploymentReplicasMismatch`.

**Which volumes survive a restart.** The deciding question is whether the
volume survives a **container** restart, not a pod restart:

| Where `tmp/` lives | Survives a container restart (liveness kill, OOM, crash) | Survives a pod delete/reschedule | Exposed? |
|---|---|---|---|
| container writable layer (no volume) | no, the new container gets a fresh layer | no | no |
| `emptyDir` | **yes**, it lives as long as the pod | no | **yes** |
| PVC (Longhorn, CIFS, …) | **yes** | **yes** | **yes** |

The 2026-07-05 version of this SOP scoped out `emptyDir`, on the theory that
the pidfile "doesn't survive a restart there". That was wrong. A liveness-probe
kill restarts the **container** inside the same pod, and the emptyDir with the
pidfile stays. On 2026-09-24 this crash-looped 8 apps at once (§5 Example B).

**The command override does not decide exposure.** The earlier version also
assumed that images started through their default entrypoint were safe,
because the Rails 7.1+ generated entrypoint would clear the pidfile. The
2026-09-24 apps disproved that: they used the image's own command, with no
`command:` override, and PID 1 was plain
`ruby bin/rails server` (or `script/rails server`). No wrapper ran first. Do
not assume any image guards this. Check what PID 1 actually is (§8 Diagnose
Example 2).

- Scope: any workload that runs `rails server` / Puma with its pidfile under a
  path on an `emptyDir` or a PVC, unless the start path provably removes the
  pidfile before the server starts. This applies whether or not the
  HelmRelease sets `command:`/`args:`.
- Prerequisites: `kubectl` access to the namespace; GitOps push access to edit
  the HelmRelease.
- Out of scope: apps whose pidfile path is on the container writable layer
  (a restart gives a clean layer), and apps whose server writes no pidfile at
  all (verify live, §8).

---

## 2) Overview

| Setting | Value |
|---------|-------|
| First hit | `my-software-development/absenty` (dev), 2026-06-22, commit `4239c8a8` |
| Largest hit | 8 `my-software-showcase` apps, 2026-09-24, commit `437bbeb8`. The 20:26Z basement switch reboot took the API servers away for about two minutes, liveness probes killed the containers, and each restart found the pidfile on the `/app/tmp` emptyDir. They stayed in `CrashLoopBackOff` until the pods were deleted by hand. |
| Symptom | `KubePodCrashLooping` + `KubeDeploymentReplicasMismatch`; container log ends with `A server is already running. Check .../tmp/pids/server.pid` |
| Root cause | pidfile on a volume that outlives the container, and nothing removes it before the server starts |
| Immediate unblock | delete the pod. A new pod gets a fresh emptyDir. This does NOT help for a PVC, and it does not prevent the next occurrence |
| Durable fix | start through `/bin/sh -c 'rm -f <pidfile>; exec <image's own command>'` (§3) |

### Exposure table (verified live 2026-09-25)

Evidence: a pidfile present at `/app/tmp/pids/server.pid` in the running pod,
the volume type backing `/app/tmp`, and `/proc/1/cmdline`.

| App | `tmp` backing | Start path | Status |
|---|---|---|---|
| `my-software-development/absenty` | emptyDir `/app/tmp` (the 2026-07-05 text said PVC; the live mount is emptyDir) | custom `bash -lc 'rm -f tmp/pids/server.pid && … rails server …'` | FIXED `4239c8a8` |
| `my-software-showcase/holm-backend` | emptyDir `/app/tmp` | sh wrapper → `ruby script/rails server -b 0.0.0.0 -p 3000` | FIXED `437bbeb8` |
| `my-software-showcase/inbewegung` | emptyDir `/app/tmp` | sh wrapper → `ruby bin/rails server -b 0.0.0.0 -p 3000` | FIXED `437bbeb8` |
| `my-software-showcase/kfa-medienarchiv` | emptyDir `/app/tmp` | sh wrapper → `ruby bin/rails server -b 0.0.0.0 -p 3000` | FIXED `437bbeb8` |
| `my-software-showcase/metaldyne` | emptyDir `/app/tmp` | sh wrapper → `ruby bin/rails server -b 0.0.0.0 -p 3000` | FIXED `437bbeb8` |
| `my-software-showcase/ordiga` | emptyDir `/app/tmp` | sh wrapper → `ruby script/rails server -b 0.0.0.0 -p 3000 -e production` | FIXED `437bbeb8` |
| `my-software-showcase/see-edv-ibspm` | emptyDir `/app/tmp` | sh wrapper → `ruby script/rails server -b 0.0.0.0 -p 3000` | FIXED `437bbeb8` |
| `my-software-showcase/u-zeit` | emptyDir `/app/tmp` | sh wrapper → `ruby bin/rails server -b 0.0.0.0 -p 3000` | FIXED `437bbeb8` |
| `my-software-showcase/zuhause-betreut` | emptyDir `/app/tmp` | sh wrapper → `ruby bin/rails server -b 0.0.0.0 -p 3000` | FIXED `437bbeb8` |
| `my-software-showcase/mangold-smarthomeadvisor` | emptyDir `/app/tmp` | image default, PID 1 = `ruby bin/rails server -b 0.0.0.0 -p 3000`, no wrapper | **EXPOSED, not fixed**. Same liveness probe as the 8 above. Needs the §3 wrapper |
| `my-software-showcase/stepbystepguide` | emptyDir `/app/tmp` | image default, PID 1 = `ruby bin/rails server -b 0.0.0.0 -p 3000`, no wrapper | **EXPOSED, not fixed**. Same liveness probe as the 8 above. Needs the §3 wrapper |
| `office/sure` (`sure-web`) | container layer (the only volume is `/rails/storage`) | image default, PID 1 = `puma` | not exposed: no pidfile under `/rails/tmp/pids` |
| `office/arag-web` | container layer | image default, `thrust ./bin/rails server` | not exposed: no pidfile under `/rails/tmp/pids` |

Re-run §8 Diagnose Example 2 before relying on this table. It is a snapshot.

---

## 3) Blueprints

The pattern lives in each app's `helmrelease.yaml`, at
`spec.values.controllers.<name>.containers.<name>.command/args` (app-template).
There is no dedicated CRD or policy object for it.

### Pattern A: the app uses the image's default command (the 2026-09-24 shape)

Wrap the image's own command. Read that command from **PID 1 of the running
pod**, not from the Dockerfile or from memory. Then reproduce it exactly behind
an `rm -f` and an `exec`:

```bash
kubectl -n <ns> exec deploy/<app> -- sh -c 'tr "\0" " " </proc/1/cmdline; echo'
# e.g. /usr/local/bin/ruby bin/rails server -b 0.0.0.0 -p 3000
```

```yaml
# 437bbeb8, verbatim shape (holm-backend)
containers:
  app:
    # /app/tmp is an emptyDir, so it survives a CONTAINER restart: a Rails
    # server killed by its liveness probe left tmp/pids/server.pid behind and
    # every restart after that exited "A server is already running"
    # (2026-09-24 switch reboot, 8 apps in CrashLoopBackOff). Clear it first;
    # the rest is the image's own command, read from PID 1.
    command: ["/bin/sh", "-c"]
    args: ["rm -f /app/tmp/pids/server.pid; exec /usr/local/bin/ruby script/rails server -b 0.0.0.0 -p 3000"]
```

Rules for the wrapper:

- **`exec` is mandatory.** It replaces the shell, so the Rails server stays
  PID 1 and receives SIGTERM directly on pod shutdown. Without `exec`, `sh` is
  PID 1, does not forward the signal, and the pod waits for the whole
  `terminationGracePeriodSeconds` before it is SIGKILLed.
- **Use `;`, not `&&`**, after `rm -f`. `rm -f` on a missing file already
  exits 0, so this is about intent: the server must start whatever the cleanup
  did.
- **Use the absolute pidfile path** (`/app/tmp/pids/server.pid`). The working
  directory is whatever the image set, and a relative path silently misses if
  that ever changes.
- **Copy every argument PID 1 has.** For example, `ordiga` needs
  `-e production`. Dropping it would silently boot the app in development mode.
- `command:` replaces the image `ENTRYPOINT`. If the image HAS a real entrypoint
  script (PID 1 is not the server itself), put that script in front of the
  command inside the `exec`, rather than dropping it.

### Pattern B: the app already has a custom `command:` (the absenty shape)

```yaml
# vulnerable
command:
  - bash
  - -lc
  - bundle config set --local path '/bundle' && bin/rails db:prepare && bundle exec rails server -b 0.0.0.0 -p 3000

# fixed (4239c8a8): prepend the cleanup, keep everything else identical
command:
  - bash
  - -lc
  - rm -f tmp/pids/server.pid && bundle config set --local path '/bundle' && bin/rails db:prepare && bundle exec rails server -b 0.0.0.0 -p 3000
```

---

## 4) Operational Instructions

1. **Confirm the signature** (§8 Diagnose Example 1) before applying the fix.
   Other Puma boot failures, such as a missing `SECRET_KEY_BASE`, an
   unreachable DB or a pending migration, also show up as
   `KubePodCrashLooping` but need a different fix.
2. **Unblock now, if the app is down:** `kubectl -n <ns> delete pod <pod>`.
   A new pod gets a fresh emptyDir. This is a recovery action, not the fix. It
   does not work when `tmp/` is on a PVC. In that case, apply step 3 first and
   let the rollout start the new container.
3. **Apply the durable fix in git.** Read PID 1 (§3 Pattern A), then add the
   `/bin/sh -c 'rm -f …; exec …'` wrapper with a comment saying why. If the app
   already overrides `command:`, prepend the `rm -f` instead (Pattern B).
   Change nothing else.
4. Commit on `main` with `git commit --only <helmrelease path>` (shared
   worktree), then push. Flux reconciles through the webhook.
5. **Verify the running process, not the manifest** (§6). The server must be
   PID 1 with exactly the arguments it had before.
6. Sweep the namespace for siblings (§8 Diagnose Example 2). The 2026-09-24
   incident hit 8 apps built from the same template, and 2 more with the same
   exposure were missed.

```bash
git commit --only kubernetes/apps/<ns>/<app>/app/helmrelease.yaml -m "fix(<app>): clear stale Rails pidfile before boot"
git show --stat HEAD && git push
```

---

## 5) Examples

### Example A: absenty-dev (the original incident, 2026-06-22)

A custom command ran `bundle exec rails server` directly. A restart left
`tmp/pids/server.pid` behind, and the next boot crash-looped. The fix in
`4239c8a8` prepended `rm -f tmp/pids/server.pid &&` (Pattern B).

### Example B: 8 showcase apps after a switch reboot (2026-09-24, `437bbeb8`)

The 20:26Z basement switch reboot cut the Kubernetes API for about two
minutes. The liveness probes of eight Rails apps in `my-software-showcase`
failed and killed their containers. `/app/tmp` was an emptyDir, so every
restarted container found the old pidfile and exited "A server is already
running". None of them had a `command:` override. Recovery took a manual
`kubectl delete pod` per app. The durable fix was the Pattern A wrapper, with
each app's exact PID-1 command (`script/rails` or `bin/rails server`, and
`-e production` for `ordiga`).

This one event disproved both scope exclusions in the old SOP: "emptyDir is
safe" and "default entrypoint is safe".

### Example C: a new Rails app

At deploy time, check where the pidfile lands (§8 Diagnose Example 2). If it
is on an emptyDir or a PVC, add the wrapper before the first incident.

---

## 6) Verification Tests

### Test 1: the server is PID 1 with the original arguments

```bash
kubectl -n <ns> exec deploy/<app> -- sh -c 'tr "\0" " " </proc/1/cmdline; echo'
```

Expected:
- Exactly the pre-change command, for example
  `/usr/local/bin/ruby bin/rails server -b 0.0.0.0 -p 3000`. It must not be
  `/bin/sh -c …`.

If failed:
- `sh` as PID 1 means the `exec` is missing. Fix the `args` string.

### Test 2: the `rm -f` path is the pidfile the server actually writes

```bash
kubectl -n <ns> exec deploy/<app> -- sh -c 'ls -l /app/tmp/pids/'
kubectl -n <ns> get deploy <app> -o jsonpath='{.spec.template.spec.containers[0].args}{"\n"}'
```

Expected:
- `server.pid` exists at exactly the path named after `rm -f` in `args`.

If failed:
- The pidfile lives elsewhere, for example because of a `pidfile` setting in
  `config/puma.rb` or a `PIDFILE` env var. Point `rm -f` at the real path.

You cannot reproduce the crash on demand from inside the pod. The kernel does
not deliver SIGKILL to a namespace's PID 1 from inside that namespace, so
`kubectl exec … kill -9 1` is a no-op. A SIGTERM (`kill 1`) is a graceful
stop, and Rails deletes its own pidfile on the way out, so it proves nothing.
Deleting the pod proves nothing either, because the new pod gets a fresh
emptyDir. The durable evidence is Test 1 plus Test 2, and then the absence of
"already running" in `logs --previous` the next time a liveness kill happens.

---

## 7) Troubleshooting

| Symptom | Likely Cause | First Fix |
|---------|--------------|-----------|
| Still "server already running" after the fix | `rm -f` path differs from the real pidfile (custom `config/puma.rb` / `PIDFILE`) | `ls` the pids dir in-pod; match the path |
| Pod takes the full grace period to stop | wrapper lacks `exec`, so `sh` is PID 1 and swallows SIGTERM | add `exec` (§6 Test 1) |
| App boots in the wrong environment after the fix | an argument from PID 1 (e.g. `-e production`) was dropped | re-read the old PID 1 from `git show` of the comment / a sibling, restore the flag |
| Crash-loop persists but log does not mention the pidfile | different root cause (DB, secret, migration) | read the log tail; do not apply this fix blindly |
| Many apps crash-loop right after a network or API outage | liveness kills across a shared template, as on 2026-09-24 | delete pods to unblock, then roll out the wrapper to every sibling (§8 Example 2) |

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
- A line containing `A server is already running. Check /app/tmp/pids/server.pid`
  (or the app's actual Rails root) confirms this SOP applies.

If unclear:
- No such line means a different cause. Check `SECRET_KEY_BASE`, DB
  connectivity (are the `wait-for-pg`/`wait-for-redis` init containers
  succeeding?) and pending migrations.

### Diagnose Example 2: which running apps are exposed right now

Exposed means all three: a pidfile exists, it is on an emptyDir or a PVC, and
PID 1 is the server itself with no wrapper that removed the file.

```bash
for ns in my-software-showcase my-software-development office; do
  for p in $(kubectl -n $ns get pods --field-selector=status.phase=Running -o name); do
    r=$(kubectl -n $ns exec $p -- sh -c 'for d in /app /rails; do [ -f $d/tmp/pids/server.pid ] && echo $d; done; true' 2>/dev/null)
    [ -n "$r" ] && echo "$ns $p root=$r cmd=$(kubectl -n $ns get $p -o jsonpath='{.spec.containers[0].command}')"
  done
done
# then, for each hit: is <root>/tmp a volume, and of what type?
kubectl -n <ns> get pod <pod> -o jsonpath='{range .spec.containers[0].volumeMounts[*]}{.mountPath}{" <- "}{.name}{"\n"}{end}'
```

Expected:
- Every hit whose tmp is an emptyDir or PVC has `cmd=["/bin/sh","-c"]` with the
  wrapper, or a custom command that starts with `rm -f`.
- An empty `cmd=` on a volume-backed tmp is **exposed**. Add it to the §2 table
  and fix it with Pattern A.

---

## 9) Health Check

```bash
kubectl get pods -n my-software-showcase -o custom-columns=POD:.metadata.name,RESTARTS:.status.containerStatuses[0].restartCount,READY:.status.containerStatuses[0].ready
kubectl get pods -n my-software-development -l app.kubernetes.io/name=absenty
```

Expected:
- All Rails apps are `Running` and ready. Restart counts can be non-zero, since
  liveness kills still happen, but they are not climbing.

---

## 10) Security Check

```bash
grep -n -A1 'command: \["/bin/sh", "-c"\]' kubernetes/apps/*/*/app/helmrelease.yaml | grep args
```

Expected:
- The wrapper `args` contain only `rm -f <pidfile>; exec <server command>`: no
  secrets, no env interpolation and no network calls. The fix adds a local
  file removal and nothing else. It does not change the image, the user or the
  securityContext.

---

## 11) Rollback Plan

```bash
git revert <commit-sha>
git push
```

Removing the wrapper re-exposes the app to this crash-loop on the next
container restart. Roll back only if the wrapper itself causes a different
regression, such as a dropped argument or a missing `exec`. The better fix for
that is to correct the `args` string, not to revert.

---

## 12) References

- `4239c8a8`: `fix(absenty-dev): clear stale Rails pidfile before boot`
- `437bbeb8`: `fix(showcase): Rails apps clear a stale server.pid before starting` (8 apps, Pattern A)
- `kubernetes/apps/my-software-showcase/*/app/helmrelease.yaml`
- `kubernetes/apps/my-software-development/absenty/app/helmrelease.yaml`
- Kubernetes docs: an emptyDir lives for the life of the **pod**, and a
  container crash does not remove it.

---

## Version History

- `2026.09.25`: Scope corrected (F-4fa1f9da). The 2026-09-24 incident
  (`437bbeb8`) disproved both exclusions in the earlier version. An `emptyDir`
  survives a container restart after a liveness kill. Apps started through the
  image's default command were exposed too: their PID 1 was plain
  `rails server` with no pidfile guard. Changes in this version: added
  exposure-by-volume-type as the scope rule, documented the `/bin/sh -c
  'rm -f …; exec …'` wrapper (Pattern A), and rebuilt the exposure table from
  live pods. The table lists the 8 fixed showcase apps and 2 more that are
  exposed and not fixed (`mangold-smarthomeadvisor`, `stepbystepguide`). It
  also corrects absenty's backing (emptyDir, not PVC) and replaces the
  `sure`/`arag-web` reasoning (no pidfile written, tmp not on a volume).
  Verification now checks PID 1 and the pidfile path. It explains why neither
  a pod delete nor an in-pod `kill` can reproduce the failure.
- `2026.07.05`: Initial SOP after the absenty-dev incident (`4239c8a8`).
