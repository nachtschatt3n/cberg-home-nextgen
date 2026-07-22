# SOP: crash-ghost-reaper — reaping node-loss "ghost" pods

> Version: `2026.07.22`
> Last Updated: `2026-07-22`

## 1) Description

`crash-ghost-reaper` is a CronJob (namespace `kube-system`, every 15 min) that
force-deletes pods left behind by an **ungraceful node reboot** (power loss,
kernel panic, hard reset). When a node loses power, its kubelet cannot clean up
the pods it was running; after the node returns `Ready`, those pods linger
forever in a "ghost" state — `phase: Running` with **every container terminated
`reason=Unknown`** — and, for RWO/Longhorn volumes, they hold the volume in a
CSI mount-deadlock so the replacement pod is stuck `FailedMount` indefinitely.

This automation was built after the **2026-07-17 power outage** hard-rebooted
all three nodes. One casualty (`paperclip`, `ai`) sat 9h in `FailedMount`
because its ghost held a Longhorn RWO volume; two others (`frigate`, `makemkv`)
were harmless leftovers. The reaper force-deletes such ghosts so their owners
(Deployment/StatefulSet/…) recreate cleanly and the volume re-attaches.

Related: [[project_power_outage_es_corruption]], `docs/sops/storage-safety.md`.

## 2) Overview

- **What runs:** `kubernetes/apps/kube-system/crash-ghost-reaper/`
  - `app/configmap.yaml` — the Python detection/reaping script (`reap.py`)
  - `app/cronjob.yaml` — `*/15 * * * *`, python:3.12-alpine, non-root, RO rootfs
  - `app/rbac.yaml` — SA + ClusterRole (`pods: get,list,delete`) + binding
  - `ks.yaml` — Flux Kustomization
- **How it talks to the API:** in-cluster ServiceAccount token + CA (urllib),
  no external deps.
- **The ghost signature (ALL must hold):**
  1. `metadata.deletionTimestamp` is empty (not already terminating), AND
  2. `metadata.ownerReferences` present (so a controller will recreate it), AND
  3. `status.reason == "NodeLost"` **OR** every `containerStatuses[].state.
     terminated.reason` is a node-loss reason (`Unknown` or
     `ContainerStatusUnknown` — the latter added 2026-07-22 after the review
     found jellyfin/scrypted ghosts of that class the Unknown-only check missed), AND
  4. the newest container `finishedAt` is older than `GRACE_MINUTES` (default
     10) — gives a genuinely-recovering node time to reconcile first.
- **Safety knob:** `DRY_RUN` env. `true` = log `would reap …` only, delete
  nothing. `false` = actually force-delete (`gracePeriodSeconds=0`).

A healthy pod never has `terminated.reason=Unknown`, so false positives are
essentially impossible — but see §6 for the mandatory observation window.

## 3) Blueprints

N/A (plain CronJob + RBAC + ConfigMap; no Authentik/Homepage/Longhorn objects).
The detection contract lives verbatim in the `configmap.yaml` header.

## 4) Operational Instructions

Change behaviour via the CronJob env in `app/cronjob.yaml`, commit, push (Flux
reconciles — never `kubectl edit`):

- `DRY_RUN`: `"true"` (observe) or `"false"` (reap). Default is `"true"` during
  the initial observation window (§6), then `"false"`.
- `GRACE_MINUTES`: minutes a ghost must persist before it is eligible.

To run once immediately (verification, safe in either mode):

```bash
kubectl create job -n kube-system ghost-reaper-adhoc \
  --from=cronjob/crash-ghost-reaper
kubectl logs -n kube-system job/ghost-reaper-adhoc
kubectl delete job -n kube-system ghost-reaper-adhoc
```

## 5) Examples

### Example A: routine run, healthy cluster

```bash
kubectl logs -n kube-system -l job-name --tail=5 \
  $(kubectl get pods -n kube-system -l app.kubernetes.io/name=crash-ghost-reaper \
    -o name | tail -1)
# 02:28:37Z done — 0 pod(s) reaped
```

### Example B: after an ungraceful reboot (what it targets)

```
02:28:37Z reaping ai/paperclip-6889468fbc-c6fwm on k8s-nuc14-01 — all-containers-terminated-Unknown
02:28:37Z   -> 200
02:28:37Z done — 1 pod(s) reaped
```

Manual equivalent (what the reaper automates):

```bash
kubectl delete pod -n <ns> <ghost-pod> --grace-period=0 --force
```

## 6) Verification Tests

### Test 1: detection is correct on the live cluster (no false positives)

Dry-run against all pods and confirm every candidate is a real ghost:

```bash
kubectl get pods -A -o json | python3 - <<'PY'
import json,sys
from datetime import datetime,timezone
pods=json.load(sys.stdin)["items"]
def ghost(p):
    m,s=p["metadata"],p.get("status",{})
    if m.get("deletionTimestamp") or not m.get("ownerReferences"): return False
    css=s.get("containerStatuses") or []
    return s.get("reason")=="NodeLost" or (bool(css) and all(
        (c.get("state",{}).get("terminated",{}) or {}).get("reason")=="Unknown" for c in css))
g=[(p["metadata"]["namespace"],p["metadata"]["name"]) for p in pods if ghost(p)]
print(f"{len(pods)} pods scanned, {len(g)} ghost(s): {g}")
PY
```

Each listed pod MUST be `0/N Unknown` with a healthy replacement already
running (or a stuck `FailedMount` replacement). If a Ready/healthy pod appears,
DO NOT enable reaping — fix the signature first.

### Test 2 (MANDATORY): 4-day observation window before enabling deletes

The reaper ships with `DRY_RUN=true`. For **4 days (through 2026-07-22)** it logs
`would reap …` lines (captured in Elasticsearch, 14d retention). Review them:

```bash
# From the sweep/ELK: every reaper decision over the window
# Kibana Discover, index logs-*, query:
#   kubernetes.pod_name: crash-ghost-reaper* and message: "would reap"
# Or via the collector logs while pods still exist:
kubectl logs -n kube-system -l app.kubernetes.io/name=crash-ghost-reaper \
  --tail=-1 --prefix | grep "would reap"
```

**Go/no-go:** if 100% of `would reap` targets over the 4 days were genuine
node-loss ghosts (each was `0/N Unknown`, owner-managed, replacement present)
and NO healthy pod was ever named → flip `DRY_RUN` to `"false"` (§11 in
reverse), commit, push. If ANY healthy/legitimately-terminating pod was named →
keep `DRY_RUN=true`, tighten the signature, and restart the window.

## 7) Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| Job `Error`, logs show 401/403 | RBAC not applied | `kubectl get clusterrole,clusterrolebinding crash-ghost-reaper` |
| `0 reaped` but a ghost persists | ghost younger than `GRACE_MINUTES`, or missing ownerReferences (unmanaged pod — intentionally skipped) | wait one cycle; unmanaged pods are left for a human |
| Reaper named a healthy pod | signature too loose (should be impossible) | set `DRY_RUN=true` immediately, open an incident, tighten `reap.py` |
| Ghost reaped but replacement still `FailedMount` | Longhorn volume still attached to old node | check `kubectl get volume -n storage <pv>`; see `docs/sops/storage-safety.md` |

```bash
# Quick debugging
kubectl get cronjob -n kube-system crash-ghost-reaper
kubectl get jobs -n kube-system | grep ghost
kubectl logs -n kube-system job/<latest-ghost-reaper-job>
```

## 8) Diagnose Examples

### Diagnose Example 1: replacement pod stuck FailedMount after a reboot

```bash
kubectl get pods -n <ns> | grep <app>          # expect a 0/N Unknown ghost + a stuck new pod
kubectl describe pod -n <ns> <new-pod> | grep -i FailedMount
# -> reaper (or manual --grace-period=0 --force on the ghost) clears it
```

### Diagnose Example 2: reaper "did nothing" but you expected a reap

```bash
# Is the candidate actually owner-managed and old enough?
kubectl get pod -n <ns> <pod> -o jsonpath='{.metadata.ownerReferences[*].kind}{"\n"}{.status.reason}{"\n"}'
kubectl get pod -n <ns> <pod> -o jsonpath='{range .status.containerStatuses[*]}{.state.terminated.reason}={.state.terminated.finishedAt}{"\n"}{end}'
```

## 9) Health Check

```bash
# CronJob scheduling normally + last runs succeeded
kubectl get cronjob -n kube-system crash-ghost-reaper
kubectl get jobs -n kube-system -l app.kubernetes.io/name=crash-ghost-reaper
# Current mode (expect DRY_RUN during the observation window)
kubectl get cronjob -n kube-system crash-ghost-reaper \
  -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].env}'
```

Ongoing: after enabling, a spike of reaps should only ever follow a real node
reboot (`node_boot_time_seconds` change). Reaps with no preceding reboot are a
red flag — investigate the named pods.

## 10) Security Check

- RBAC is least-privilege: `pods: get,list,delete` cluster-wide and nothing
  else. Confirm no extra verbs/resources crept in:
  ```bash
  kubectl get clusterrole crash-ghost-reaper -o yaml | grep -A4 rules
  ```
- Pod runs non-root, `readOnlyRootFilesystem`, `allowPrivilegeEscalation:false`,
  all caps dropped, `seccompProfile: RuntimeDefault`.
- The delete verb is powerful; the ghost signature + `GRACE_MINUTES` + the
  observation window (§6) are the compensating controls. Never widen the
  ClusterRole to `deployments`/`statefulsets` — the reaper only deletes pods.

## 11) Rollback Plan

```bash
# Fastest: make it observe-only (stops all deletes, keeps logging)
# Edit app/cronjob.yaml -> DRY_RUN: "true", commit, push (Flux reconciles).

# Suspend entirely (no runs at all):
# add `spec.suspend: true` to app/cronjob.yaml, commit, push.

# Full removal: delete ./crash-ghost-reaper/ks.yaml from
# kubernetes/apps/kube-system/kustomization.yaml, commit, push
# (prune: true removes the CronJob, RBAC, ConfigMap).
```

Emergency only (violates GitOps; reconcile will revert): `kubectl -n kube-system
patch cronjob crash-ghost-reaper -p '{"spec":{"suspend":true}}'`.

## 12) References

- Manifests: `kubernetes/apps/kube-system/crash-ghost-reaper/`
- Incident + prevention decisions: memory `project_power_outage_es_corruption`
- Storage-side deadlocks: `docs/sops/storage-safety.md`
- Ingestion/ES recovery sibling automation: `kubernetes/apps/monitoring/elasticsearch/app/obs-recovery-*`

## Version History

| Version | Date | Change |
|---|---|---|
| 2026.07.18 | 2026-07-18 | Initial SOP; reaper shipped `DRY_RUN=true` for a 4-day observation window (review 2026-07-22). |
| 2026.07.22 | 2026-07-22 | Go/no-go review PASSED: 0 pods flagged over the 4-day window (0 false positives). Flipped `DRY_RUN=false` (active). Broadened the ghost signature to also match `ContainerStatusUnknown`. |
