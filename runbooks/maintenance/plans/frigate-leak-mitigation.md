---
plan_id: frigate-leak-mitigation
component: frigate
pr: null                              # not a Renovate update — 0.17.2 IS the newest
                                      # stable release; there is nothing to bump to.
kind: infra
current: "0.17.2 · limit 8Gi · restart CronJob `30 2 * * 0` (weekly, never yet fired) · leak detector structurally blind"
target: "0.17.2 · limit 10Gi · restart CronJob `30 2 * * *` (daily, proven by a one-shot run) · MALLOC_ARENA_MAX=1 · 2 mitigation-aware alert rules"
update_type: n/a
risk: medium
est_duration_min: 40
needs_reboot: false
touches:
  namespaces: [home-automation, monitoring]
  resources:
    - cronjob/frigate-restart            # schedule weekly -> daily
    - helmrelease/frigate                # memory limit 8Gi -> 10Gi, + MALLOC_ARENA_MAX env
    - deployment/frigate                 # Recreate rollout — ~60-90s with no camera recording
    - pvc/frigate-config                 # Longhorn RWO — detached + reattached by the rollout, contents untouched
    - pvc/frigate-media                  # CIFS — remounted only, NEVER deleted (see storage-safety)
    - prometheusrule/container-memory-alerts   # namespace monitoring, +2 rules in group container.memory.rules
    - node/k8s-nuc14-02                  # +2Gi of memory LIMIT accounting (request unchanged at 1Gi)
  shared: [monitoring]                   # the PrometheusRule shares a rule group with the three
                                         # existing container-memory alerts; a bad expr there
                                         # degrades cluster-wide memory alerting, not just frigate's.
depends_on: []                           # verified against `grep '^plan_id:' runbooks/maintenance/plans/*.md`
                                         # on 2026-08-26 — no prerequisite plan exists. Deliberately
                                         # empty rather than a plausible-looking dead ref
                                         # (media-naming-p3 declares `media-episode-backfill-bulk`,
                                         # which is not a real plan_id and so never gates anything).
conflicts_with: [longhorn-1.12.1-engine] # verified real plan_id, currently sat-early:2026-08-29.
                                         # Both detach/reattach Longhorn RWO volumes; must not share
                                         # a window. No conflict at the proposed window.
security_ref: F-5e6cdafc
status: awaiting-go
window: "wed-early:2026-08-26"           # PROPOSED, see §1 "Timing". The window agent may reassign,
                                         # but see the deadline: thu-early:2026-08-27 05:00 is the
                                         # LAST window before the projected ceiling.
auto_execute: false
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/monitoring.md
  - docs/sops/longhorn-rwo-multi-attach.md
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/storage-safety.md
generated: "2026-08-26"
---

# frigate — resize, prove, and re-instrument the memory-leak mitigation

## 1. Summary & why held

`home-automation/frigate` (image `0.17.2`, unchanged across every pod in the
observation window — **no version explains this**) exhausts its 8Gi memory limit
roughly **38.4 hours** after a cold start. Finding `F-5e6cdafc` (critical, cycle
`550bf019`) was triaged to the PLAN lane — "matched no rule; defaulted to a
window" — and then nothing owned it, because no plan file was ever written. This
file is that owner.

The failure mode is the bad kind, and it is why "wait for the OOMKill" is not a
strategy: frigate runs one process per camera and is **not reliably OOMKilled**.
At the cgroup ceiling the kernel fails child allocations with `ENOMEM` first, so
cameras stop recording and detectors stall while the pod stays `Ready` with
`restartCount: 0`. There is no Kubernetes event to alert on and nothing restarts
it. (Full reasoning: commit `c8279fe2`.)

### Measured evidence

| | |
|---|---|
| Pod `jb4c2` | cold start `2026-08-24T07:24:22Z` at **3.87 GiB** → tripped `ContainerMemoryLimitImminent` (>97% working_set) at `2026-08-25T21:45Z`. **38.4h, ~2.14 GiB/day.** |
| Pod `2ccdk` (current) | started `2026-08-25T21:49:38Z`. Re-confirmed at `2026-08-26T02:32Z` (age 4.76h): **working_set 4.199 GiB = 52.5%** of limit, RSS 2.932 GiB = 36.6%. |
| Pod `zw8gn` | ran ~41 days at ~0.36 GiB/day — a **different life stage**, not comparable. The load-bearing number is the measured 38.4h, whatever the curve shape. |
| Dominant consumer | `frigate.embeddings_manager`, 2.16 GiB of ~4.5 GiB total. |

Growth is **activity-shaped** — flat overnight, step-ups during daylight motion.
Re-measured `deriv(container_memory_rss[4h])` overnight = **0.264 GiB/day**,
which is the flat part of the curve, not the daily average. **Treat every date
below as a trajectory, not a guarantee.**

### Upstream evidence

- `0.17.2` (published 2026-06-28) **is the newest stable release.** `0.18.0-beta1/2/3`
  are the only newer tags and all are prereleases. **There is nothing to upgrade
  to**, so "bump to the fix" is not an available option — this is not a held
  Renovate update, which is why `pr: null`.
- Upstream discussion #23007 documents the same process leaking
  (`frigate.embeddings_manager`, 250–490 MB/h there), which matches our
  observation. **Its root-cause analysis does NOT transfer to us**: it traces to
  ONNXRuntime's CUDA EP accumulating pinned host memory. We run **OpenVINO on the
  Intel NPU** (`detectors.ov`, `npu.intel.com/accel: 1`) with no CUDA anywhere.
  Do not import that conclusion.
- What *does* transfer is hardware-independent glibc behaviour: the same thread
  reports **`MALLOC_ARENA_MAX=1` cuts steady-state RSS roughly in half**
  (fragmentation across ~177 threads, 3.9 GB → 1.5 GB at startup). That is an
  allocator property, not a CUDA property. It is one env var and costs no
  features. It is the only upstream-sourced lever we can take today.
- `0.18.0-beta3` adds **"Remote Embeddings"** — semantic-search embeddings
  generated by an external GenAI provider instead of in-process. That is the
  **real fix**: it moves the leaking process out of the container entirely, and
  we already point `OPENAI_BASE_URL` at the Mac mini Ollama. **Do not chase it
  now** — this is the household's security-camera system and 0.18 is beta only.
  Revisit at 0.18 GA.

### The three problems this plan addresses

**(a) The existing mitigation is ~4.4x too infrequent.** CronJob
`home-automation/frigate-restart` runs `30 2 * * 0` — weekly — sized on the
reasoning "from a ~3.5 GiB cold start the ceiling is ~14 days away". Measured
reality is 38 hours. Weekly is 168h against a 38h budget.

**(b) It has never fired — and the reason is benign, which matters.**
`LAST SCHEDULE: <none>`. **Investigated before assuming a schedule change fixes
anything**, because a schedule that never triggers stays broken at any frequency.
Findings, on the live cluster:

- The CronJob was created `2026-08-24T20:34:28Z`. **2026-08-24 was a Monday.**
  The first `30 2 * * 0` occurrence is **Sunday 2026-08-30 02:30** — it is not
  broken, it is **not yet due**.
- `suspend: false`. Status is `{}` (empty), consistent with never-yet-due.
- The CronJob controller demonstrably works: **34 other CronJobs across the
  cluster have recent `lastScheduleTime`s.**
- The decisive control for the `timeZone` field (which is the plausible silent
  failure — an unsupported `timeZone` on an older API server): CronJob
  `home-automation/pallet-price-monitor`, **same namespace, same
  `timeZone: Europe/Berlin`**, last scheduled `2026-08-25T18:00:00Z`. Timezone
  handling is working on this cluster.

So a schedule change *is* sufficient — **but that conclusion currently rests on
inference, not on the job having ever run.** Step 6 therefore forces one
end-to-end run and asserts it, which proves the ServiceAccount, the Role
(`patch` on `deployments/frigate` only), the `rancher/kubectl:v1.33.4` image
pull, and the `rollout restart` path all actually work. That evidence has never
been collected. Note also `startingDeadlineSeconds: 600`: a run missed by more
than 10 minutes is **silently skipped**, which is a second way this can quietly
stop working later — covered by the new alert in Step 4.

**(c) Prometheus is structurally blind to a restart-mitigated leak, and a more
frequent restart makes it blinder.** `ContainerMemoryLeakPredicted`
(`kubernetes/apps/monitoring/kube-prometheus-stack/app/container-memory-alerts.yaml`)
requires `(time() - container_start_time_seconds) > 24*3600` **and**
`rss/limit > 0.50`, with `for: 1h`. Under a **daily** restart at 02:30 the
container's age never reaches 24h + 1h, so **the rule can never fire for frigate
again.** The mitigation parks the workload permanently inside its own detector's
blind spot.

The 24h guard is **load-bearing and must not be weakened** — it exists because
`office/sure-worker` fired at container age 6h00m40s, the exact instant a 6h
guard opened, projecting 114% off Sidekiq's post-boot arena ratchet against a
7-day asymptote of 68%. Narrowing or widening that guard to chase this case is
precisely the failure `feedback_fp_fix_can_blind_detector.md` warns about: an
FP fix that manufactures an FN. **This plan therefore leaves that rule alone and
adds two rules that cannot be blinded by a restart** (Step 4).

One trap worth recording, because it is the same class as the
`container_spec_memory_limit_bytes` mistake documented at the top of that alert
file: the obvious liveness metric,
`kube_cronjob_status_last_schedule_time{cronjob="frigate-restart"}`, **does not
exist until the job first fires.** `time() - <absent>` returns no data, so an
alert built on it would never fire in exactly the state we are in today. Verified
on the live cluster: only one such series exists in `home-automation`, and it is
`pallet-price-monitor`. The new rule asserts **container age** — the *effect* —
which covers CronJob deleted, RBAC broken, job failing, schedule wrong, and
deadline-missed all at once.

### Recommendation among the four options

| Option | Verdict |
|---|---|
| More frequent restart (**daily**) | **YES — this is the mitigation.** 24h against a 38.4h budget. Projected peak ~78% of the current 8Gi limit. |
| Memory limit 8Gi → 10Gi | **YES, but as headroom, not as the mitigation.** `c8279fe2` rejected a limit bump and that rejection was correct *for a limit used as the fix* ("it only picks the date of the next incident"). The argument here is different: with a daily restart the limit is never approached, so its job changes to *absorbing one missed restart* — turning a skipped run from an incident into a warning. Peak drops from ~78% to ~62%. |
| Upstream 0.17.x bump | **NO — not available.** 0.17.2 is newest stable. |
| `semantic_search.model_size: large → small` | **NO.** Rejected in `c8279fe2`: halves the embeddings baseline without stopping growth, and degrades a feature the operator deliberately enabled. Superseded by `MALLOC_ARENA_MAX=1`, which buys a comparable baseline reduction at **zero feature cost**. |
| `MALLOC_ARENA_MAX=1` (**new**) | **YES, with an abort gate.** Attacks the *baseline* (3.87 GiB cold start), which is what makes 38h so short. Hardware-independent. One env var, revertible. **Risk:** a single malloc arena serialises allocation across ~177 threads and could cost detection throughput — Step 7.4 is an explicit abort gate on `inference_speed` and `skipped_fps`. |

**Recommended: daily restart + 10Gi headroom + `MALLOC_ARENA_MAX=1` + the two
new alert rules, all in one window.** They are one rollout and they fail
together or not at all; splitting them means two camera gaps for one outcome.

### Timing — read this before scheduling

Projecting the current pod on the measured 38.4h trajectory from its
`2026-08-25T21:49:38Z` start: **97% at approximately 2026-08-27 ~14:00 CEST.**

- **`wed-early:2026-08-26 05:00` (proposed)** — empty window, 60 min, capacity 6,
  `allow_reboot: false`. This plan is 40 min / risk-weight 2. Fits alone with
  room. Leaves **~33h of margin.**
- **`thu-early:2026-08-27 05:00` is the LAST usable window** — ~9h of margin, and
  only if nothing slips.
- Anything after that is **useless**: the ceiling arrives first.

**Stated plainly: this should go today, at `wed-early:2026-08-26 05:00`.** That
window opens ~25 minutes after this plan was written, which is very little time
for an operator go/no-go, and I am not pretending otherwise. If it cannot be
approved in time, take `thu-early` and treat the margin as spent.

**Interim safety valve if no window can be approved before ~2026-08-27 12:00
CEST:** run the one-shot restart Job from Step 6 out of band. It applies the
already-reviewed mitigation from `c8279fe2` with no new config, buys another
~38h, and does not pre-empt this plan.

---

## 2. Pre-checks

```bash
export KUBECONFIG=${KUBECONFIG:-~/.kube/config}

# 2.1 Flux is settled on both Kustomizations this plan touches.
flux get kustomizations -A | grep -E 'NAME|home-automation.*frigate|monitoring.*kube-prometheus-stack'
# EXPECT: both READY=True, same revision, SUSPENDED=False. Abort if either is reconciling.

# 2.2 Nobody has already fixed this out of band (the plan must not fight a live change).
kubectl -n home-automation get cronjob frigate-restart \
  -o custom-columns=SCHED:.spec.schedule,TZ:.spec.timeZone,SUSPEND:.spec.suspend,LAST:.status.lastScheduleTime
# EXPECT: 30 2 * * 0 | Europe/Berlin | false | <none>
# If SCHED is already daily, or LAST is populated, STOP and re-read §1(b) before proceeding.

kubectl -n home-automation get deploy frigate \
  -o jsonpath='{.spec.template.spec.containers[0].resources.limits.memory}{"\n"}'
# EXPECT: 8Gi

# 2.3 Node headroom for +2Gi of limit (requests are unchanged; this is accounting only).
kubectl describe node k8s-nuc14-02 | sed -n '/Allocated resources/,/^Events/p'
# BASELINE 2026-08-26: memory requests 38%, limits 147% (already overcommitted by design).
# The +2Gi is LIMIT-only; frigate's request stays 1Gi, so scheduling is unaffected and the
# daily restart means the extra 2Gi is headroom that is never actually occupied.
# ABORT if memory REQUESTS on this node now exceed 75%.

# 2.4 The alert rule group is healthy BEFORE we touch it (baseline for "did I break it").
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 >/dev/null 2>&1 &
sleep 5
curl -s http://localhost:9090/api/v1/rules | python3 -c "
import sys,json
for g in json.load(sys.stdin)['data']['groups']:
    if g['name']=='container.memory.rules':
        print('rules:',len(g['rules']),'lastError:',repr(g.get('lastError','')))
        for r in g['rules']: print('  -',r['name'],'health=',r.get('health'))
"
# EXPECT: rules: 3, lastError: '', all health=ok

# 2.5 Memory + camera baseline. RECORD THESE — §7 diffs against them.
curl -sG --data-urlencode 'query=container_memory_working_set_bytes{namespace="home-automation",container="frigate"} / on(namespace,pod,container) group_left kube_pod_container_resource_limits{resource="memory"}' \
  http://localhost:9090/api/v1/query | python3 -c "import sys,json;print('ws/limit',json.load(sys.stdin)['data']['result'][0]['value'][1])"
curl -sG --data-urlencode 'query=(time()-container_start_time_seconds{namespace="home-automation",container="frigate"})/3600' \
  http://localhost:9090/api/v1/query | python3 -c "import sys,json;print('age_h',json.load(sys.stdin)['data']['result'][0]['value'][1])"

kubectl port-forward -n home-automation svc/frigate 15000:5000 >/dev/null 2>&1 &
sleep 5
curl -s http://localhost:15000/api/stats -o /tmp/frigate-stats-before.json
python3 -c "
import json; d=json.load(open('/tmp/frigate-stats-before.json'))
print('version', d['service']['version'])
for k,v in d['cameras'].items():
    print(f\"  {k}: camera_fps={v['camera_fps']} process_fps={v['process_fps']} skipped_fps={v['skipped_fps']}\")
print('detectors', d['detectors'])
"
# BASELINE 2026-08-26T02:35Z: 5 cameras, camera_fps 2.1/2.1/2.1/5.3/5.1,
# skipped_fps 0.0 on all five, detectors.ov.inference_speed = 6.56 ms.
# KEEP /tmp/frigate-stats-before.json — §7.4 is an abort gate against it.

# 2.6 No Longhorn work in flight (the rollout detaches/reattaches frigate-config).
kubectl -n storage get volume frigate-config -o custom-columns=STATE:.status.state,ROBUST:.status.robustness
# EXPECT: attached | healthy
```

---

## 3. Steps — GitOps only, no direct cluster mutation

> Everything below is a file edit in `main` + push. Flux reconciles on webhook.
> Do **not** `flux reconcile` by hand; both Kustomizations are on a 30m interval
> and the webhook fires on push. Follow `docs/sops/application-update.md`.
> Shared-worktree rule from `CLAUDE.md`: commit with `git commit --only <paths>`,
> then `git show --stat HEAD` before pushing.

### Step 1 — CronJob: weekly → daily

File: `kubernetes/apps/home-automation/frigate-nvr/app/restart-cronjob.yaml`

```yaml
# BEFORE
  schedule: "30 2 * * 0"          # Sundays 02:30 Europe/Berlin
# AFTER
  schedule: "30 2 * * *"          # DAILY 02:30 Europe/Berlin
```

Also replace the `# WHY WEEKLY` comment block, which is now factually wrong and
will mislead the next reader:

```yaml
# WHY DAILY (was weekly; corrected 2026-08-26, finding F-5e6cdafc)
# The original "~14 days from a ~3.5 GiB cold start" estimate was wrong by ~9x.
# MEASURED: pod jb4c2 went 3.87 GiB -> 97% of the 8 GiB limit in 38.4 hours
# (~2.14 GiB/day), image 0.17.2 throughout. Weekly is 168h against a 38h budget.
# Daily at 02:30 leaves ~14h of the budget unused even before the 10Gi headroom
# and MALLOC_ARENA_MAX=1 landed in the same change.
# 02:30 stays the quietest hour for an NVR and clear of the 03:00 Longhorn backup
# and the 04:00 sweep.
#
# startingDeadlineSeconds: 600 is deliberate and unchanged — a run missed by more
# than 10 minutes is SKIPPED rather than fired late. That is the right trade for a
# camera system, but it means the mitigation can stop silently. The alert
# ContainerRestartMitigationStale (container-memory-alerts.yaml) exists to catch
# exactly that; do not remove one without the other.
```

### Step 2 — Memory limit 8Gi → 10Gi (headroom, NOT the mitigation)

File: `kubernetes/apps/home-automation/frigate-nvr/app/helmrelease.yaml`

```yaml
      limits:
        memory: 10Gi    # was 8Gi. NOT the fix — the daily restart is. This is headroom
                        # so ONE missed restart degrades into a warning instead of an
                        # ENOMEM incident. Request stays 1Gi, so scheduling is unchanged.
        gpu.intel.com/i915: 1
        npu.intel.com/accel: 1
```

Leave `requests.memory: 1Gi` alone.

### Step 3 — `MALLOC_ARENA_MAX=1`

Same file, in `values.env`:

```yaml
    env:
      TZ: "Europe/Berlin"
      LIBVA_DRIVER_NAME: "iHD"
      OPENAI_BASE_URL: "http://192.168.30.111:11434/v1"
      # Cap glibc malloc arenas at one. frigate runs ~177 threads and per-thread
      # arenas fragment badly; upstream discussion #23007 measures steady-state RSS
      # roughly halved. This is glibc behaviour, NOT the CUDA pinned-host-memory
      # theory in that thread — we run OpenVINO on the NPU and that part does not
      # apply to us. Attacks the BASELINE, not the growth rate.
      # TRADE-OFF: one arena serialises malloc across those threads. If detection
      # throughput regresses (§7.4), revert THIS LINE ONLY — the daily restart and
      # the 10Gi headroom stand on their own.
      MALLOC_ARENA_MAX: "1"
```

### Step 4 — Two mitigation-aware alert rules

File: `kubernetes/apps/monitoring/kube-prometheus-stack/app/container-memory-alerts.yaml`

**Do not modify `ContainerMemoryLeakPredicted`.** Append these two rules to the
`container.memory.rules` group, after the existing three:

```yaml
        # ---- Restart-mitigated workloads (added 2026-08-26, finding F-5e6cdafc) ----
        #
        # ContainerMemoryLeakPredicted above is STRUCTURALLY BLIND to any workload
        # under a restart mitigation: it needs container age > 24h plus for:1h, and
        # frigate is now restarted every 24h at 02:30. Making the restart more
        # frequent makes that alert LESS likely to ever fire. The two rules below
        # exist so the mitigation is observable; neither depends on container age
        # being large, so neither can be blinded by the restart.
        #
        # The 24h guard on ContainerMemoryLeakPredicted is deliberately UNTOUCHED.
        # It is load-bearing: office/sure-worker fired at container age 6h00m40s --
        # the exact instant a 6h guard opened -- projecting 114% of limit off
        # Sidekiq's post-boot arena ratchet, against a 7-day asymptote of 68%.
        # Loosening it to cover frigate would trade this false negative for that
        # false positive. Add coverage; do not move the guard.
        #
        # Scoped by an explicit selector rather than applied cluster-wide: a
        # restart mitigation is a rare, deliberate, per-workload decision, and a
        # cluster-wide version of either rule would fire on every normal deploy.
        # To put another workload under a restart mitigation, add it here.

        - alert: ContainerRestartMitigationStale
          # The restart is the mitigation, so the restart itself must be monitored.
          # Asserts the EFFECT (the container actually got younger), not the
          # mechanism -- so it covers CronJob deleted, RBAC revoked, image pull
          # failing, job erroring, schedule edited wrong, and
          # startingDeadlineSeconds silently skipping a run, all in one expression.
          #
          # NOT built on kube_cronjob_status_last_schedule_time: that series does
          # not exist until the CronJob first fires, so `time() - <absent>` returns
          # no data and never fires in exactly the broken state this rule is for.
          # Same class of mistake as container_spec_memory_limit_bytes at the top
          # of this file. Verified 2026-08-26: no such series exists for
          # frigate-restart.
          #
          # The `or absent(...)` arm is not decoration. Without it, frigate's pod
          # disappearing entirely makes this rule return no data -- which reads as
          # "all clear", the exact failure the rule is meant to prevent.
          #
          # 30h = the 24h schedule plus one skipped run's grace. Warning, not
          # critical: at 30h the container is well inside the 10Gi budget, so this
          # is a day of lead time rather than an emergency. ContainerMemoryNearLimit
          # and ContainerMemoryLimitImminent remain the critical tier. Expect it to
          # fire if the CronJob is deliberately suspended -- that is correct.
          expr: |
            (
              (time() - container_start_time_seconds{namespace="home-automation",container="frigate"}) > 30 * 3600
            )
            or
            absent(container_start_time_seconds{namespace="home-automation",container="frigate"})
          for: 30m
          labels:
            severity: warning
            category: capacity
            component: container
          annotations:
            summary: "frigate has not been restarted on schedule — its leak mitigation may be dead"
            description: >-
              home-automation/frigate is under a DAILY restart mitigation (CronJob frigate-restart,
              30 2 * * *) because it exhausts its memory limit in roughly 38 hours. The container has
              now gone more than 30 hours without a restart, or has vanished entirely. The mitigation
              is not running. Check the CronJob's lastScheduleTime, its Job history, and its RBAC.
              Do not silence this — at the ceiling frigate degrades silently (ENOMEM to child
              processes) instead of being OOMKilled.

        - alert: ContainerMemoryBudgetExceeded
          # "The restart interval is no longer sized correctly." Age-independent,
          # so the restart cannot hide it. Fires an entire tier earlier than
          # ContainerMemoryNearLimit (0.90) and much earlier than Imminent (0.97).
          #
          # working_set, matching the two threshold rules and matching what the
          # cgroup actually enforces -- frigate has a 2Gi /dev/shm for ffmpeg
          # frames, which is charged to the container and is NOT visible in RSS.
          # (RSS is the right metric for the PREDICTION rule and the wrong one here.)
          #
          # 0.75 of 10Gi = 7.5 GiB. Expected daily peak under this mitigation is
          # ~62% (cold start ~3.87 GiB + ~2.14 GiB over 24h), and the pre-change
          # 8Gi-era peak was ~7.76 GiB, so crossing 7.5 GiB within one restart
          # cycle means the leak rate has risen above what daily can absorb.
          # Response: tighten the interval or act on the root cause -- do not
          # raise this threshold.
          expr: |
            (
              container_memory_working_set_bytes{namespace="home-automation",container="frigate"}
              / on(namespace,pod,container) group_left
              kube_pod_container_resource_limits{resource="memory"}
            ) > 0.75
          for: 30m
          labels:
            severity: warning
            category: capacity
            component: container
          annotations:
            summary: "frigate reached {{ $value | humanizePercentage }} of its limit inside one restart cycle"
            description: >-
              home-automation/frigate crossed 75% of its memory limit within a single daily restart
              cycle. The daily restart is no longer sufficient to bound the leak. Tighten the
              frigate-restart schedule or address the root cause (frigate.embeddings_manager);
              see docs/sops/frigate-memory-leak.md and finding F-5e6cdafc.
```

### Step 5 — Capture the reasoning in an SOP

There is no `docs/sops/frigate-memory-leak.md`; the entire rationale currently
lives in one commit message (`c8279fe2`), which is why the sizing error survived
and why this plan had to re-derive it. **This plan file is deleted on execution**
(README lifecycle rule), so without this step the reasoning is lost a second time.

Create `docs/sops/frigate-memory-leak.md` from `docs/sops/SOP-TEMPLATE.md`, with
`Version: 2026.08.26`. Required sections per `CLAUDE.md`. Carry across: the
ENOMEM-not-OOMKill failure mode; the measured 38.4h; why a limit bump is headroom
and not the fix; why `model_size: small` was rejected; why the upstream CUDA
root-cause analysis does not apply to our OpenVINO/NPU setup; the two new alert
rules and why `ContainerMemoryLeakPredicted`'s 24h guard must not be moved; and
the exit condition — **delete the CronJob and this SOP when 0.18 GA lands with
Remote Embeddings**, `security_ref: F-5e6cdafc`.

**No CVE detail, no secret domains, no camera stream URLs in that file.**

### Step 6 — Commit, push, and PROVE the restart path

```bash
cd /Users/mu/code/cberg-home-nextgen

git commit --only \
  kubernetes/apps/home-automation/frigate-nvr/app/restart-cronjob.yaml \
  kubernetes/apps/home-automation/frigate-nvr/app/helmrelease.yaml \
  kubernetes/apps/monitoring/kube-prometheus-stack/app/container-memory-alerts.yaml \
  docs/sops/frigate-memory-leak.md \
  -F /tmp/frigate-msg.txt

git show --stat HEAD        # MANDATORY: is every file here actually yours?
git push
```

Commit message: state the measured 38.4h, weekly→daily, limit as headroom not
fix, arena var, the two alert rules, and that the CronJob had never fired because
it was created on a Monday with a Sunday schedule. **Reference `F-5e6cdafc`; do
not restate finding detail.**

Then, once Flux has applied (§7.1), **force one end-to-end run.** This is the
single most important step in the plan and the one thing §1(b) could not prove
by inference:

```bash
# Delegated to cberg-agent; this is a cluster mutation, executed inside the window.
kubectl -n home-automation create job frigate-restart-proof-$(date +%Y%m%d) \
  --from=cronjob/frigate-restart

kubectl -n home-automation wait --for=condition=complete \
  job/frigate-restart-proof-$(date +%Y%m%d) --timeout=15m
kubectl -n home-automation logs job/frigate-restart-proof-$(date +%Y%m%d)
```

A Job created with `--from` is standalone and not owned by the CronJob, so
`concurrencyPolicy: Forbid` does not apply.

> **If Steps 2–3 were skipped** (operator declines the HelmRelease change), this
> Job is the ONLY thing that resets the memory clock — the CronJob edit alone
> changes nothing until 02:30 tomorrow. Do not skip it.
>
> **If Steps 2–3 were applied**, the HelmRelease change already triggers a
> `Recreate` rollout, so the clock is reset either way — run the Job regardless,
> because proving the CronJob's own path works is its entire purpose.

Clean up after verification: `kubectl -n home-automation delete job frigate-restart-proof-$(date +%Y%m%d)`

---

## 4. Verification

### CONTENTS ASSERTIONS

> **CONTENTS ASSERTION 1 — the restart mechanism actually works end to end**:
> the `frigate-restart` Job template, run for real, completes AND moves
> `container_start_time_seconds` forward — measured by §7.2, compared to the
> §2.5 baseline age. *"CronJob schedule reads `30 2 * * *`" is the shape check
> that lies here: the object has read `30 2 * * 0` correctly for two days while
> having never executed once.*

> **CONTENTS ASSERTION 2 — all five cameras are still recording**: every entry
> in `/api/stats.cameras` has `camera_fps > 0` — measured by §7.3, compared to
> the §2.5 baseline. *`Ready` + `restartCount: 0` is precisely the state frigate
> holds while its cameras have stopped, so pod health cannot verify this.* A
> **floor**, not a ceiling: a total disappearance of cameras must not read as
> success, hence the `len(cameras) == 5` assertion alongside.

> **CONTENTS ASSERTION 3 — the new alert rules return series**: both new
> expressions evaluate to a non-empty result set with `health: ok` — measured by
> §7.5. *A rule whose selector typo makes it return no data never fires and is
> indistinguishable from "nothing is wrong" — the exact
> `container_spec_memory_limit_bytes` trap documented in that file's header.*

```bash
# 7.1 Flux applied both Kustomizations at the new revision.
flux get kustomizations -A | grep -E 'home-automation.*frigate|monitoring.*kube-prometheus-stack'
# EXPECT: READY=True on both, revision == the pushed SHA.

kubectl -n home-automation get cronjob frigate-restart -o jsonpath='{.spec.schedule}{"\n"}'
# EXPECT: 30 2 * * *
kubectl -n home-automation get deploy frigate \
  -o jsonpath='{.spec.template.spec.containers[0].resources.limits.memory}{"\n"}'
# EXPECT: 10Gi
kubectl -n home-automation get deploy frigate -o json \
  | python3 -c "import sys,json;e=json.load(sys.stdin)['spec']['template']['spec']['containers'][0]['env'];print([x for x in e if x['name']=='MALLOC_ARENA_MAX'])"
# EXPECT: [{'name': 'MALLOC_ARENA_MAX', 'value': '1'}]

# 7.2 CONTENTS ASSERTION 1 — the proof Job completed and the clock reset.
kubectl -n home-automation get job -l job-name --no-headers | grep frigate-restart-proof
# EXPECT: COMPLETIONS 1/1
kubectl -n home-automation get pods -l app.kubernetes.io/name=frigate \
  -o jsonpath='{.items[0].status.startTime}{"\n"}'
# EXPECT: a timestamp INSIDE the window, i.e. age < 15 minutes. NOT 2026-08-25T21:49:38Z.

# 7.3 CONTENTS ASSERTION 2 — cameras recording, not merely Ready.
kubectl port-forward -n home-automation svc/frigate 15000:5000 >/dev/null 2>&1 &
sleep 30    # let fps counters populate after the restart
curl -s http://localhost:15000/api/stats -o /tmp/frigate-stats-after.json
python3 - <<'PY'
import json
b=json.load(open('/tmp/frigate-stats-before.json'))['cameras']
a=json.load(open('/tmp/frigate-stats-after.json'))['cameras']
assert len(a)==len(b)==5, f"camera COUNT changed: {len(b)} -> {len(a)}"   # the floor
bad=[k for k,v in a.items() if not v['camera_fps']>0]
assert not bad, f"cameras with camera_fps==0: {bad}"
for k in a:
    print(f"{k}: fps {b[k]['camera_fps']} -> {a[k]['camera_fps']}, skipped {b[k]['skipped_fps']} -> {a[k]['skipped_fps']}")
print("PASS: all 5 cameras recording")
PY

# 7.4 ABORT GATE for MALLOC_ARENA_MAX — detection throughput must not regress.
python3 - <<'PY'
import json
b=json.load(open('/tmp/frigate-stats-before.json'))
a=json.load(open('/tmp/frigate-stats-after.json'))
bi=b['detectors']['ov']['inference_speed']; ai=a['detectors']['ov']['inference_speed']
print(f"inference_speed {bi} -> {ai} ms")
sk=[(k,v['skipped_fps']) for k,v in a['cameras'].items() if v['skipped_fps']>0]
print("cameras skipping frames:", sk or "none")
if ai > bi*1.25 or sk:
    print("REGRESSION -> revert ONLY the MALLOC_ARENA_MAX line (see §5). "
          "The daily restart and the 10Gi headroom stay.")
PY
# BASELINE: inference_speed 6.56 ms, skipped_fps 0.0 on all five cameras.

# 7.5 CONTENTS ASSERTION 3 — the new rules loaded AND return series.
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 >/dev/null 2>&1 &
sleep 5
curl -s http://localhost:9090/api/v1/rules | python3 -c "
import sys,json
g=[x for x in json.load(sys.stdin)['data']['groups'] if x['name']=='container.memory.rules'][0]
names=[r['name'] for r in g['rules']]
assert len(g['rules'])==5, f'expected 5 rules, got {len(g[\"rules\"])}: {names}'
assert not g.get('lastError'), g['lastError']
for r in g['rules']:
    assert r.get('health')=='ok', (r['name'], r.get('health'), r.get('lastError'))
assert 'ContainerRestartMitigationStale' in names and 'ContainerMemoryBudgetExceeded' in names, names
print('PASS rule group:', names)
"

# The rules must not merely LOAD — their selectors must MATCH something.
for Q in \
  'container_start_time_seconds{namespace=\"home-automation\",container=\"frigate\"}' \
  'container_memory_working_set_bytes{namespace=\"home-automation\",container=\"frigate\"} / on(namespace,pod,container) group_left kube_pod_container_resource_limits{resource=\"memory\"}'
do
  curl -sG --data-urlencode "query=$Q" http://localhost:9090/api/v1/query \
    | python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];assert r,'EMPTY RESULT — selector matches nothing, this rule can never fire';print('ok, series:',len(r),'value:',r[0]['value'][1])"
done

# 7.6 The three pre-existing alerts still evaluate (shared rule group).
curl -s http://localhost:9090/api/v1/rules | python3 -c "
import sys,json
g=[x for x in json.load(sys.stdin)['data']['groups'] if x['name']=='container.memory.rules'][0]
for n in ['ContainerMemoryNearLimit','ContainerMemoryLimitImminent','ContainerMemoryLeakPredicted']:
    r=[x for x in g['rules'] if x['name']==n][0]
    print(n,'health=',r.get('health'))
    assert r.get('health')=='ok'
"

# 7.7 Longhorn volume came back cleanly after the Recreate rollout.
kubectl -n storage get volume frigate-config -o custom-columns=STATE:.status.state,ROBUST:.status.robustness
# EXPECT: attached | healthy. If Multi-Attach appears, see docs/sops/longhorn-rwo-multi-attach.md
# (frigate is already strategy: Recreate, so this should not occur).
```

### 7.8 T+26h follow-up — the only proof that DAILY works

**Not optional, and it cannot be done inside the window.** Schedule an OpenClaw
reminder for **2026-08-27 ~04:00 CEST**, after the first real `30 2 * * *` fire:

```bash
kubectl -n home-automation get cronjob frigate-restart \
  -o custom-columns=LAST:.status.lastScheduleTime
# EXPECT: a timestamp on 2026-08-27 ~00:30Z (02:30 CEST). Still <none> => the mitigation
# is dead for a reason §1(b) did not find; re-open F-5e6cdafc, do not close it.

kubectl -n home-automation get pods -l app.kubernetes.io/name=frigate \
  -o jsonpath='{.items[0].status.startTime}{"\n"}'
# EXPECT: age < 2h.
```

Only after 7.8 passes should `F-5e6cdafc` be closed and this plan set to
`executed` + deleted.

---

## 5. Rollback

All three changes are in one commit and revert together. The rollout is
self-reverting by nature: the failure mode is *slow memory growth*, so a bad
outcome is never sudden.

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <sha-from-step-6>
git show --stat HEAD          # confirm only the four intended files
git push

# Confirm the cluster is back:
flux get kustomizations -A | grep -E 'home-automation.*frigate|monitoring.*kube-prometheus-stack'
kubectl -n home-automation get cronjob frigate-restart -o jsonpath='{.spec.schedule}{"\n"}'   # -> 30 2 * * 0
kubectl -n home-automation get deploy frigate -o jsonpath='{.spec.template.spec.containers[0].resources.limits.memory}{"\n"}'  # -> 8Gi
curl -s http://localhost:9090/api/v1/rules | python3 -c "
import sys,json;g=[x for x in json.load(sys.stdin)['data']['groups'] if x['name']=='container.memory.rules'][0]
print('rules:',len(g['rules']),'lastError:',repr(g.get('lastError','')))"     # -> 3, ''
# Then re-run §7.3 (all 5 cameras camera_fps > 0) — a revert is a second rollout.
```

**Partial rollback — the likely one.** If §7.4 trips, revert **only** the
`MALLOC_ARENA_MAX` line in `helmrelease.yaml` and push. The daily CronJob and the
10Gi limit are independent of it and should stay; they are the mitigation.

**Three things to know before reverting:**

1. **A revert is a second `Recreate` rollout** — another ~60-90s with no camera
   recording. Weigh that against whatever you are reverting for.
2. **Reverting 10Gi → 8Gi is only safe on a fresh container.** The revert
   triggers a rollout, so the new pod starts at ~3.9 GiB and 8Gi is fine. Never
   hand-patch the limit downward on a long-running pod near the ceiling.
3. **A full revert restores a mitigation known to be ~4.4x undersized**, and the
   ceiling is projected for ~2026-08-27 14:00 CEST. If you fully revert, you must
   still restart frigate manually (§3 Step 6 Job) or re-plan before then. A
   revert here is not a return to safety — it is a return to the incident clock.

---

## 6. Interference notes

**For the window agent:**

- **`shared: [monitoring]` is the one to respect.** Step 4 edits a PrometheusRule
  whose rule group also contains the three existing container-memory alerts. A
  malformed expression fails the whole group and degrades **cluster-wide** memory
  alerting, not just frigate's. §7.6 explicitly re-asserts the three pre-existing
  rules for that reason. **Do not co-schedule with any other plan that touches
  `kube-prometheus-stack`** — two edits to one rule group in one window makes a
  rollback ambiguous.
- **`conflicts_with: [longhorn-1.12.1-engine]`** (a verified-real plan_id,
  currently `sat-early:2026-08-29`). The `Recreate` rollout detaches and
  reattaches the Longhorn RWO volume `frigate-config`; a Longhorn engine upgrade
  in the same window turns a routine reattach into a race. No conflict at the
  proposed window — this is a guard against reshuffling.
- **`needs_reboot: false`.** No node reboot, no Talos work, no CNI/ingress/
  cert-manager/CoreDNS/shared-DB perturbation. Fits a 60-minute no-reboot weekday
  window.
- **Camera blackout: ~60-90 seconds, once** (twice if you also revert). This is
  the household's security-camera system. `strategy: Recreate` + `replicas: 1`
  means the old pod releases before the new one starts — that is deliberate
  (Longhorn RWO) and must not be "optimised" to `RollingUpdate`; see
  `docs/sops/longhorn-rwo-multi-attach.md`.
- **The unauthenticated `:5000` service goes away during the rollout.** Per the
  HelmRelease's own comment that port is the internal (Home Assistant) path, so
  in-cluster consumers of frigate see a brief connection failure. Ingress/
  Authentik outpost (`:8971`) is unaffected in configuration but likewise
  unavailable for the same ~90s.
- **No PVC is created, resized, or deleted.** `frigate-media` is a **CIFS** PVC —
  `docs/sops/storage-safety.md` applies in full. Nothing in this plan deletes a
  PVC and nothing in it should ever be extended to.
- **Ordering within the plan matters**: Step 6's proof Job must run **after**
  Flux has applied Step 1, or it proves the old template. §7.1 gates it.
- **Node accounting:** `k8s-nuc14-02` memory *limits* are already 147%
  overcommitted; this adds 2Gi to that figure. It adds **nothing** to requests
  (38%), so scheduling is unchanged, and the daily restart means the headroom is
  never occupied. Frigate is effectively pinned to a node with a free
  `npu.intel.com/accel` — all three nodes have one, so a reschedule is possible
  but the NPU must be free on the target.
- **Do not close `F-5e6cdafc` at the end of the window.** The window can only
  prove the mechanism (§7.2); only the T+26h check (§7.8) proves *daily* actually
  happens. Closing early re-creates the exact gap that produced this plan.
