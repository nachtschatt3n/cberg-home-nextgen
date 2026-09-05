# SOP: Failed-Job Alerting (KubeJobFailed vs. the Honest Signal)

> Description: How `KubeJobFailed` pages after the underlying outage is already
> over, why that happens, how to tell a real resolve from a rotation artifact,
> and when a scoped silence is (and is not) the right stopgap.
> Version: `2026.09.05`
> Last Updated: `2026-09-05`
> Owner: `Platform`

---

## 1) Description

`KubeJobFailed` (kube-prometheus-stack's default `kube_job_failed{...} > 0`
rule) keys on the **existence of a failed Job object**, not on whether the
underlying condition is still true. Kubernetes garbage-collects that object on
its own schedule (`failedJobsHistoryLimit` count-based rotation, or
`ttlSecondsAfterFinished` time-based cleanup) — a schedule that has nothing to
do with when the outage that caused the failure actually ended. The result:
the alert can keep paging long after the fix has landed (the failed object
just hasn't rotated out yet), or — worse — it can flap RESOLVED/FIRING every
rotation cycle while the underlying job is *still* failing, each false
RESOLVED telling the operator the problem cleared at the exact moment it
recurred.

- Scope: any `CronJob`/`Job` whose failure is expected to be **transient**
  (retries on the next schedule tick) and any Prometheus alert built on
  `kube_job_failed` / `kube_job_status_failed`.
- Prerequisites: `kubectl` access to the namespace owning the CronJob;
  `kubectl port-forward` to Alertmanager for silence management.
- Out of scope: Jobs whose failure is genuinely terminal (one-shot migration
  Jobs, etc.) — those should page and stay paged until an operator clears
  them by hand; this SOP is about jobs that **retry on a schedule** and whose
  transient failures should not outlive the outage.

---

## 2) Overview

| Setting | Value |
|---------|-------|
| Namespace | varies per CronJob (examples below: `databases`, `office`) |
| Source of truth | the CronJob's `jobTemplate.spec.ttlSecondsAfterFinished` + the PrometheusRule that alerts on it |
| Critical dependency | `kube-state-metrics` (`kube_job_failed`), Alertmanager |
| Closes | sweep finding `F-d57b90bd` |

---

## 3) Blueprints

- Source of truth: the CronJob manifest itself sets
  `jobTemplate.spec.ttlSecondsAfterFinished` — there is no separate
  cleanup controller to configure.
- Real examples in this repo:
  - `kubernetes/apps/office/mealie/app/shopping-sync-cronjob.yaml`
    (`ttlSecondsAfterFinished: 3600`, fixed in `6029d3dd`)
  - `kubernetes/apps/databases/sweep-history/app/heartbeat-cronjob.yaml`
    (`ttlSecondsAfterFinished: 21600`, fixed in `65aca390`)
- Related PrometheusRule pattern (the honest, timestamp-based alternative):
  `kubernetes/apps/monitoring/kube-prometheus-stack/app/sweep-pipeline-alerts.yaml`
  (`SweepPipelineDead`, keyed on `kube_cronjob_status_last_successful_time`).

```yaml
# Minimal pattern: bound how long a failed Job object survives
apiVersion: batch/v1
kind: CronJob
spec:
  failedJobsHistoryLimit: 3        # count-based rotation (existing default) —
                                    # NOT sufficient alone, see §4
  jobTemplate:
    spec:
      ttlSecondsAfterFinished: <N> # time-based cleanup — set N ~= one
                                    # schedule interval (see §4 sizing rule)
```

---

## 4) Operational Instructions

### Why object-presence alerting flaps under history rotation

`failedJobsHistoryLimit` retains the **N most recent failed Job objects**
per CronJob. For a CronJob that fails continuously, each new run creates a
new failed Job and evicts the oldest — so at every rotation boundary the
*specific object* `kube_job_failed` was keyed on disappears, the metric
series for that name/label combination briefly reads absent-then-zero, and
Alertmanager RESOLVES the alert. The next run creates a fresh failed Job and
the alert FIRES again. Nothing about the underlying condition changed; only
the count-based garbage collector ran. Observed directly on 2026-09-05: the
`sweep-heartbeat` CronJob (`17 */6 * * *`) failed continuously for 8 days
(root cause: `SWEEP_TRIGGER=cron` wasn't propagated by the daily-operation
skill, so every cron-driven sweep was mislabeled `manual` and the heartbeat's
`trigger='cron'` filter could never see a fresh row), and `KubeJobFailed`
resolved and re-fired roughly every 15 minutes for the full 8 days —
resolve/fire pairs captured at `10:17:46Z` and `10:32:46Z` that day.

**A false RESOLVED is worse than a false FIRING.** A page that keeps firing
is at least honest about the state; a page that flaps to RESOLVED tells the
operator "cleared" at the exact moment the job failed again, which retires
attention right when it's still needed. Object-presence alerting cannot avoid
this: it has no memory of "still broken," only "is there currently a failed
object in the retained window."

### How to tell a real resolve from a rotation artifact

Never trust `KubeJobFailed`'s FIRING/RESOLVED transitions alone as evidence
of the underlying job's health. Check a monotonic timestamp instead:

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &
# Age since the CronJob's last SUCCESS — only moves forward, immune to
# failed-Job object rotation:
curl -s 'http://localhost:9090/api/v1/query' \
  --data-urlencode 'query=time()-kube_cronjob_status_last_successful_time{namespace="<ns>",cronjob="<name>"}' \
  | python3 -m json.tool
```

If that age keeps growing, the job is still broken regardless of what
`KubeJobFailed` currently shows. If it stops growing (a fresh success landed),
the job actually recovered. This is the general lesson: **alert on a
timestamp that only moves forward (`*_last_successful_time`,
`*_last_success_seconds`), never on the existence of an object subject to
history-based rotation**, for any check where "still broken" must survive a
garbage-collection cycle.

### The fix: bound object lifetime, or split the signal

Two complementary fixes, both already applied in this repo:

1. **`ttlSecondsAfterFinished`, sized to roughly one schedule interval.**
   Too short and a still-broken job never accumulates enough history to
   diagnose; too long and a real recovery takes that long to stop paging.
   Rule of thumb used here: `mealie-shopping-sync` runs every 5 min → TTL
   3600s (1h, enough to inspect logs, still ages out promptly); `sweep
   -heartbeat` runs every 6h → TTL 21600s (one interval — a still-broken
   scheduler produces a fresh failed Job on the next run so the alert
   correctly continues, while a recovered one produces a successful Job and
   lets the failure age out immediately). Do not set the TTL much above the
   schedule interval or a real recovery goes unnoticed for that much longer.
2. **When a detector's exit status depends on a label/condition that itself
   can silently stop being true (not just "the job ran and failed"), split
   the signal** so the honest, timestamp-based check (`SweepPipelineDead`
   pattern) is what actually pages, and the object-presence alert
   (`KubeJobFailed`) is left as a secondary/debugging signal bounded by TTL.
   Fixed this way in `65aca390` for `sweep-heartbeat`.

### When a scoped, self-expiring silence is appropriate — and when it isn't

Appropriate: while you're mid-diagnosis or the fix is already merged but not
yet proven, and the flapping page itself is drowning out other signals. Scope
it as narrowly as the CronJob's generated Job names allow, and set a TTL that
expires once the fix has had time to prove itself (one full schedule interval
past the fix landing is a reasonable minimum) — not "until I remember to
remove it."

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 &
NOW=$(python3 -c "from datetime import *;print(datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
END=$(python3 -c "from datetime import *;print((datetime.now(timezone.utc)+timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
curl -s -X POST localhost:9093/api/v2/silences -H 'Content-Type: application/json' -d '{
  "matchers":[{"name":"alertname","value":"KubeJobFailed","isRegex":false,"isEqual":true},
              {"name":"namespace","value":"databases","isRegex":false,"isEqual":true},
              {"name":"job_name","value":"sweep-heartbeat-.*","isRegex":true,"isEqual":true}],
  "startsAt":"'$NOW'","endsAt":"'$END'","createdBy":"operator",
  "comment":"F-d57b90bd fix (65aca390) landed — TTL expires 1h after fix to let it prove itself. DO NOT EXTEND."}'
```

Not appropriate — a silence must **never** cover:

- The honest, timestamp-based signal (`SweepPipelineDead` or equivalent).
  Silencing the flapping symptom while leaving the ground-truth check active
  is fine — the ground-truth check is what tells you when it's actually safe
  to remove the silence. Silencing *both* removes your only way to know the
  fix worked.
- A CronJob whose failure has not yet been root-caused. A silence hides the
  page; it does not fix the job. Root-cause first (§Diagnose below), then
  silence only to bridge the gap between "fix merged" and "fix proven."
- Any alertname/namespace pair broader than the specific CronJob under
  investigation — a bare `alertname=KubeJobFailed` matcher with no `job_name`
  scope silences every failing Job cluster-wide.

---

## 5) Examples

### Example A: sizing a new CronJob's TTL from its schedule

```yaml
spec:
  schedule: "*/15 * * * *"       # every 15 min
  jobTemplate:
    spec:
      ttlSecondsAfterFinished: 900   # 1 interval: recover promptly, still
                                      # enough time to `kubectl logs` a
                                      # genuinely-broken run before it's gone
```

### Example B: confirming a KubeJobFailed page is a rotation artifact, not a real outage

```bash
# 1. Is the alert currently firing?
curl -s http://localhost:9090/api/v1/alerts | python3 -c \
  "import sys,json; a=json.load(sys.stdin)['data']['alerts']; \
   print([x for x in a if x['labels'].get('alertname')=='KubeJobFailed'])"

# 2. Does the CronJob's last-success timestamp keep advancing?
curl -s 'http://localhost:9090/api/v1/query' \
  --data-urlencode 'query=time()-kube_cronjob_status_last_successful_time{namespace="<ns>",cronjob="<name>"}' \
  | python3 -m json.tool
# If this value is NOT growing across repeated checks a few minutes apart,
# the job is succeeding between failed-object rotations — the page is
# flapping on garbage collection, not on the underlying job's health.
```

---

## 6) Verification Tests

### Test 1: TTL is set and sane relative to schedule

```bash
kubectl get cronjob -n <ns> <name> -o jsonpath='{.spec.schedule}{"\n"}{.spec.jobTemplate.spec.ttlSecondsAfterFinished}{"\n"}'
```

Expected:
- `ttlSecondsAfterFinished` is set (not empty/absent) and is on the order of
  one schedule interval, not orders of magnitude larger.

If failed:
- No TTL at all means failed Jobs accumulate until `failedJobsHistoryLimit`
  rotates them — add the field per §4.

### Test 2: a fixed job's alert actually clears via the API, not by inference

```bash
curl -s http://localhost:9090/api/v1/query \
  --data-urlencode 'query=time()-kube_cronjob_status_last_successful_time{namespace="<ns>",cronjob="<name>"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['result'])"
curl -s http://localhost:9093/api/v2/alerts | python3 -c \
  "import sys,json; a=json.load(sys.stdin); print([x['status'] for x in a if x['labels'].get('cronjob')=='<name>'])"
```

Expected:
- The last-success age is small (fresh success landed) AND the Alertmanager
  API shows no active alert for that CronJob — not just "the Telegram page
  stopped," which a rotation-artifact resolve would also produce.

If failed:
- Last-success age still growing → the job is still actually broken, TTL
  tuning will not fix that; go back to root-causing the failure.

---

## 7) Troubleshooting

| Symptom | Likely Cause | First Fix |
|---------|--------------|-----------|
| `KubeJobFailed` resolves and re-fires every few minutes | Continuous failures + `failedJobsHistoryLimit` rotation cycling the failed-object identity | Check `kube_cronjob_status_last_successful_time` age (not the alert state) to confirm it's still broken; root-cause the failure, don't just silence |
| Page for a CronJob still firing days after the fix merged | No `ttlSecondsAfterFinished`, or TTL far longer than the schedule interval | Add/shrink `ttlSecondsAfterFinished` to ~one schedule interval (§4) |
| Silence expired but page came back | Underlying job was never actually fixed, only silenced | Never silence without root-causing first; re-open investigation |
| Alert cleared but nobody is sure if the job is actually healthy | Relied on alert state instead of the timestamp metric | Query `kube_cronjob_status_last_successful_time` directly (§Diagnose) |

```bash
# Quick debugging: list recent Jobs for a CronJob and their outcomes
kubectl get jobs -n <ns> -l "app.kubernetes.io/instance=<name>" --sort-by=.metadata.creationTimestamp
kubectl logs -n <ns> job/<job-name>
```

---

## 8) Diagnose Examples

### Diagnose Example 1: is this a flapping rotation artifact?

```bash
# Poll the alert state and the failed-object identity a few minutes apart
for i in 1 2 3; do
  curl -s http://localhost:9090/api/v1/query \
    --data-urlencode 'query=kube_job_failed{namespace="<ns>",job_name=~"<name>-.*"}' \
    | python3 -c "import sys,json; r=json.load(sys.stdin)['data']['result']; print([x['metric'].get('job_name') for x in r])"
  sleep 300
done
```

Expected:
- If the `job_name` values change across polls while the CronJob's schedule
  interval is short, the alert is riding history rotation, not a single
  static failure. Confirms flapping.

If unclear:
- Compare against `kube_cronjob_status_last_successful_time` age — if it
  never advances across the whole polling window, it's a real continuous
  outage that also happens to rotate, not a false pattern.

### Diagnose Example 2: did the fix actually land, or does the CronJob still lack a TTL?

```bash
kubectl get cronjob -n <ns> <name> -o yaml | grep -A2 ttlSecondsAfterFinished
git log -1 --format=%H -- kubernetes/apps/<ns>/<app>/app/*cronjob.yaml
flux get kustomization -n <ns> <app-kustomization> 2>/dev/null
```

Expected:
- The live CronJob's TTL matches what's in git, and Flux shows the
  Kustomization as `Ready=True` (not stuck on an older revision).

If unclear:
- `flux reconcile kustomization -n <ns> <app-kustomization> --with-source`
  to force a reconcile if the live object looks stale relative to git.

---

## 9) Health Check

```bash
# Any CronJob with failedJobsHistoryLimit set but no ttlSecondsAfterFinished
# is a latent instance of this pattern — sweep for it periodically:
grep -rL "ttlSecondsAfterFinished" $(grep -rl "failedJobsHistoryLimit" kubernetes/apps --include="*cronjob*.yaml")
```

Expected:
- No output (every CronJob with a history limit also bounds Job lifetime by
  time). Any file listed is a candidate for this SOP's fix.

---

## 10) Security Check

```bash
# Silences created under this SOP must be scoped and time-boxed — audit for
# stragglers that outlived their comment's stated TTL
curl -s http://localhost:9093/api/v2/silences | python3 -c \
  "import sys,json; s=json.load(sys.stdin); \
   print([x['id'] for x in s if x['status']['state']=='active' and 'F-' not in x.get('comment','') and 'KubeJobFailed' in str(x['matchers'])])"
```

Expected:
- No plaintext secrets in repo (N/A — this SOP touches no secrets).
- No silence covering `KubeJobFailed` older than its stated TTL, and no
  silence whose matchers are broader than a single `namespace` +
  `job_name=~` scope.
- The honest/timestamp-based signal (e.g. `SweepPipelineDead`) is never
  found in the same silence's matchers as the object-presence alert.

---

## 11) Rollback Plan

```bash
# Revert a ttlSecondsAfterFinished change: git revert the commit that added it
git revert <commit-sha>
git push
# Or manually restore the previous value and commit through GitOps as usual.

# Remove an active silence early once the fix is confirmed:
curl -s -X DELETE localhost:9093/api/v2/silences/<id>
```

There is no cluster-side rollback risk: `ttlSecondsAfterFinished` only
affects how long a finished Job's metadata is retained for inspection, not
the Job's execution behavior. Shrinking it later is always safe.

---

## 12) References

- `docs/sops/monitoring.md` — general Prometheus/Alertmanager operations
- `docs/sops/control-liveness.md` — `SweepPipelineDead` and the broader
  dead-man's-switch pattern this SOP's timestamp-based check follows
- `docs/sops/application-update.md` — silence API usage during attended
  updates (same API, different use case)
- `kubernetes/apps/databases/sweep-history/app/heartbeat-cronjob.yaml`
- `kubernetes/apps/office/mealie/app/shopping-sync-cronjob.yaml`
- `kubernetes/apps/monitoring/kube-prometheus-stack/app/sweep-pipeline-alerts.yaml`
- Sweep finding `F-d57b90bd` (closed by this SOP); root-cause commit
  `65aca390`; original TTL pattern commit `6029d3dd`

---

## Version History

- `2026.09.05`: Initial SOP. Closes sweep finding `F-d57b90bd`. Documents
  the `KubeJobFailed` object-presence flapping pattern observed on the
  `sweep-heartbeat` CronJob (8-day continuous failure, ~15-minute
  resolve/refire cycle), the timestamp-based alternative
  (`kube_cronjob_status_last_successful_time`), TTL sizing, and scoped-silence
  rules.
