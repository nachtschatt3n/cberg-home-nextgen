# SOP: Frigate Memory Leak — Restart Mitigation

> Description: Why `home-automation/frigate` is restarted on a schedule, how the mitigation is monitored, and the condition under which all of it gets deleted.
> Version: `2026.08.26`
> Last Updated: `2026-08-26`
> Owner: `cluster-ops`

---

## 1) Description

Frigate 0.17.2 leaks memory at roughly **2.14 GiB/day** and exhausts an 8 GiB
limit in about **38 hours** from a cold start. There is no fix available to us
today, so the workload runs under a **daily restart mitigation**.

This SOP exists because the reasoning was previously recorded only in a commit
message (`c8279fe2`). That is why the original sizing was wrong by ~9x and
survived undetected — the estimate said "~14 days from a ~3.5 GiB cold start",
nobody re-derived it, and the CronJob was set to weekly against a 38-hour budget.

- Scope: `home-automation/frigate`, CronJob `frigate-restart`, the
  `container.memory.rules` alert group
- Prerequisites: `kubectl`, repo write access, Flux reconciliation
- Out of scope: camera configuration, detector tuning, recordings retention
- `security_ref: F-5e6cdafc`

---

## 2) Overview

**The failure mode is not an OOMKill.** Frigate's memory limit is reached by a
parent process that then fails to allocate for its children: ffmpeg and detector
subprocesses get ENOMEM and die individually while the pod stays `Running` and
`Ready`. Cameras stop recording without the pod ever restarting. That is why the
mitigation is a *scheduled* restart rather than "let the OOM killer handle it",
and why the alerting must not wait for a restart that never comes.

Three parts, and only the first is the mitigation:

| Part | Role |
|---|---|
| CronJob `frigate-restart`, `30 2 * * *` Europe/Berlin | **The mitigation.** Resets the clock every 24h against a ~38h budget. |
| `limits.memory: 10Gi` | **Headroom, not a fix.** Makes ONE missed restart a warning instead of an incident. `requests.memory` stays 1Gi, so scheduling is unaffected. |
| `MALLOC_ARENA_MAX: "1"` | Attacks the **baseline**, not the growth rate. Frigate runs ~177 threads; per-thread glibc arenas fragment badly. |

**On `MALLOC_ARENA_MAX`:** upstream discussion #23007 attributes its own case to
ONNXRuntime CUDA pinned host memory. **That analysis does not transfer** — we run
OpenVINO on the Intel NPU. Only the glibc-arena half applies, which is why it is
listed as a baseline reduction with a revert path and not as a cure.

**Rejected: `model_size: small`.** It reduces the embeddings model's footprint
but does not change the leak's slope, and it degrades search quality permanently
to buy hours against a problem the restart already bounds.

---

## 3) Blueprints

N/A — no Authentik or app blueprints. The three files are:

- `kubernetes/apps/home-automation/frigate-nvr/app/restart-cronjob.yaml`
- `kubernetes/apps/home-automation/frigate-nvr/app/helmrelease.yaml`
- `kubernetes/apps/monitoring/kube-prometheus-stack/app/container-memory-alerts.yaml`

---

## 4) Operational Instructions

All changes are GitOps. Do not edit the CronJob or Deployment in-cluster.

**To change the restart interval**, edit `schedule:` in `restart-cronjob.yaml`.
Keep it clear of 03:00 (Longhorn backup) and 04:00 (sweep). If you tighten it
below daily, the leak rate has risen — record why, and re-check whether the
budget assumptions in the alert comments still hold.

**`startingDeadlineSeconds: 600` is deliberate.** A run missed by more than ten
minutes is *skipped*, not deferred, because a restart at an unplanned hour is the
thing this exists to avoid. The consequence is that the mitigation can stop
**silently** — which is exactly what `ContainerRestartMitigationStale` is for.
Never remove one without the other.

**To force a restart out of band:**

```bash
kubectl -n home-automation create job frigate-restart-manual-$(date +%Y%m%d) \
  --from=cronjob/frigate-restart
```

A Job created with `--from` is standalone and not owned by the CronJob, so
`concurrencyPolicy: Forbid` does not block it.

---

## 5) Examples

Measured evidence behind the daily interval (pod `…-jb4c2`, image 0.17.2
throughout, no config change in the window):

```
cold start          3.87 GiB
+38.4 h             97% of the 8 GiB limit
implied rate        ~2.14 GiB/day
weekly schedule     168 h against a ~38 h budget
```

Expected steady state under this mitigation: peak ~62% of 10 GiB
(cold start ~3.87 GiB + ~2.14 GiB over 24h).

---

## 6) Verification Tests

```bash
# The schedule is daily and the CronJob is not suspended
kubectl -n home-automation get cronjob frigate-restart \
  -o custom-columns=SCHED:.spec.schedule,TZ:.spec.timeZone,SUSPEND:.spec.suspend,LAST:.status.lastScheduleTime
# EXPECT: 30 2 * * * | Europe/Berlin | false | <timestamp within the last 24h>

# The limit landed and the request did NOT change
kubectl -n home-automation get deploy frigate -o jsonpath='{.spec.template.spec.containers[0].resources}{"\n"}'
# EXPECT: limits.memory 10Gi, requests.memory 1Gi

# The arena cap is in the running container
kubectl -n home-automation exec deploy/frigate -- printenv MALLOC_ARENA_MAX
# EXPECT: 1

# All five rules healthy
kubectl -n monitoring get prometheusrule container-memory-alerts \
  -o jsonpath='{range .spec.groups[*].rules[*]}{.alert}{"\n"}{end}'
```

**Cameras must be unaffected.** Compare against a pre-change capture — every
camera present, `skipped_fps` still 0.0, detector inference speed not materially
worse. A rise in `skipped_fps` after `MALLOC_ARENA_MAX=1` is the signal that one
arena is serialising malloc across frigate's threads: revert **that line only**.

---

## 7) Troubleshooting

| Symptom | Cause | Action |
|---|---|---|
| Cameras stop recording, pod still `Running`/`Ready` | The ENOMEM failure mode — limit reached, children failing to allocate | Force a restart Job; do not wait for an OOMKill, there will not be one |
| `ContainerRestartMitigationStale` firing | CronJob deleted/suspended, RBAC revoked, image pull failing, or a run silently skipped by `startingDeadlineSeconds` | Check `lastScheduleTime`, Job history, then the ServiceAccount/Role |
| `ContainerMemoryBudgetExceeded` firing | Leak rate has risen above what daily can absorb | Tighten the interval or address the root cause — **do not raise the threshold** |
| `ContainerMemoryLeakPredicted` never fires for frigate | Expected and correct | It needs container age > 24h; a daily restart means it should not fire. That is why the two rules above exist |

---

## 8) Diagnose Examples

```bash
# Growth within the current cycle
kubectl -n home-automation top pod -l app.kubernetes.io/name=frigate

# RSS vs working_set — working_set includes the 2Gi /dev/shm charged to the
# container, which RSS does not show. The threshold rules use working_set for
# that reason; the prediction rule uses RSS because page cache is not a leak.
kubectl -n home-automation get pod -l app.kubernetes.io/name=frigate \
  -o jsonpath='{.items[0].metadata.creationTimestamp}{"\n"}'

# Camera health
kubectl -n home-automation port-forward svc/frigate 15000:5000 &
curl -s http://localhost:15000/api/stats | python3 -m json.tool | head -40
```

---

## 9) Health Check

Healthy looks like: container age < 30h, working_set < 75% of limit, all cameras
reporting `skipped_fps: 0.0`, and `lastScheduleTime` within the last 24 hours.

---

## 10) Security Check

The restart CronJob runs as uid/gid 1000, `runAsNonRoot: true`, with a Role
scoped to patching the single `frigate` Deployment in `home-automation`. It must
not be widened. Frigate's port 5000 is unauthenticated and in-cluster only; the
authenticated path is 8971 behind the ingress and its Authentik outpost.

---

## 11) Rollback Plan

Each part is independently revertible, in increasing order of caution:

1. **`MALLOC_ARENA_MAX`** — revert this line alone if detector throughput
   regresses. The daily restart and the headroom stand without it.
2. **`limits.memory: 10Gi` → `8Gi`** — safe, but removes the margin that makes a
   missed restart a warning rather than an incident.
3. **Schedule daily → weekly** — do not, unless the leak is genuinely fixed.
   Weekly against a 38h budget is what produced the incident.

Reverting any of these is a git revert plus Flux reconcile; the rollout is
`Recreate` at `replicas: 1`, so expect the same ~60–90 s camera gap.

---

## 12) References

- `runbooks/maintenance/plans/frigate-leak-mitigation.md` (deleted on execution — this SOP replaces it)
- `docs/sops/longhorn-rwo-multi-attach.md` — why the rollout is `Recreate`
- `kubernetes/apps/monitoring/kube-prometheus-stack/app/container-memory-alerts.yaml`
- Finding `F-5e6cdafc`

**EXIT CONDITION — delete this SOP and the CronJob when it is met.** The root
cause is frigate's `embeddings_manager` holding memory in-process. Frigate 0.18
moves embeddings out via Remote Embeddings, which removes the leak's source
rather than bounding it. 0.18 is **beta only** as of 2026-08-26; 0.17.2 is the
newest stable. When 0.18 reaches GA and is running here with embeddings remote,
delete the CronJob, its RBAC, `ContainerRestartMitigationStale`,
`ContainerMemoryBudgetExceeded`, and this file. Restore `limits.memory` to 8Gi
only after observing a full week of flat memory.

---

## Version History

| Version | Date | Change |
|---|---|---|
| `2026.08.26` | 2026-08-26 | Created on execution of the leak-mitigation plan: weekly→daily restart, 10Gi headroom, `MALLOC_ARENA_MAX=1`, two mitigation-aware alerts. |
