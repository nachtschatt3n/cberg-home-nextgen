---
plan_id: media-audit-durable-output
component: library-tools
pr: null
kind: config
current: "media-library-audit CronJob's only artifact is pod stdout; the dashboard's latest_audit_summary() reads the same pod logs"
target: "each audit run persists its result outside pod stdout, and the dashboard reads the persisted copy"
update_type: feature
risk: low
est_duration_min: 45
needs_reboot: false
touches:
  namespaces: [media, databases]
  resources:
    - cronjob/media-library-audit
    - configmap/library-tools-scripts   # holds audit.py — step 1's edit target
    - configmap/media-dashboard         # CORRECTED 2026-09-20 (F-5e5c14e6): this plan named
                                        # `deployment/library-tools-dashboard`, which exists
                                        # NOWHERE. `library-tools` is the app DIRECTORY and the
                                        # Flux Kustomization; every object it renders is
                                        # `media-*`. Step 2 edits dashboard-configmap.yaml, and
                                        # THIS is the object that file renders — the edit
                                        # target the old entry left undeclared.
    - deployment/media-dashboard        # consumer: mounts cm/media-dashboard at volume `app`
                                        # (verified live 2026-09-20). Named so the interference
                                        # check and Step 4 verification can both see the
                                        # dashboard half; the old name resolved to nothing, so
                                        # it could neither collide nor be verified.
    - "postgres: sweep_history"
  shared: []
depends_on: []
conflicts_with: []
capability_change: false
rollback_class: git-revert
status: awaiting-go   # DEFERRED 2026-09-19 sat-attended: AUTO-NIGHT but category config/AUTO-NIGHT is 0/2 clean supervised runs, so the first run must be supervised. go/no-go ingested, scoped sat-attended:2026-09-26.
window: "sat-attended:2026-10-10"   # RESCOPED TWICE on 2026-09-19: off :2026-09-19 because that run was cron-fired/unattended (an approval on a closed window is a stranded GO), then off :2026-09-26 because media-audit(45m) + prometheus-crd-ownership(30m) + wazuh-2xx-edge-coverage(45m) = 120m overflows a 90m window. This is the lowest-priority of the three (risk low, observability improvement), so per the capacity rule it is the one that moves. :2026-10-03 was rejected too — it already holds 70m.
premises:
  - id: audit-still-has-no-writable-mount
    why: >-
      This plan exists because the audit container mounts media READ-ONLY and
      has no other writable volume. If a writable mount was added meanwhile,
      the design below is solved differently and should be re-planned.
    run: kubectl get cronjob -n media media-library-audit -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].volumeMounts}'
    expect_contains: '"readOnly":true'
  - id: dashboard-object-is-media-dashboard
    why: >-
      ADDED 2026-09-20 (F-5e5c14e6). The premises above cover only the audit
      half, so the gate passed while the dashboard half was named after an
      object that does not exist — unverifiable by construction. Step 2 edits
      dashboard-configmap.yaml, so it is executable only if that file still
      renders cm/media-dashboard AND deployment/media-dashboard still serves
      it. One command asserts both: it names the Deployment (so a rename fails
      the gate instead of resolving to nothing) and reads back the ConfigMap it
      actually mounts (so the file->object link is proven, not assumed).
    run: kubectl get deploy -n media media-dashboard -o jsonpath='{.spec.template.spec.volumes[?(@.name=="app")].configMap.name}'
    expect_exact: media-dashboard
  - id: dashboard-still-reads-audit-from-pod-logs
    why: >-
      Step 2 exists to REPLACE a pod-log read. If latest_audit_summary() is
      gone or someone already repointed it, this plan is stale and the "the
      dashboard is equally blind" claim in Why no longer describes the cluster.
      Asserted against the LIVE ConfigMap rather than the repo file, so drift
      or a hand-edit fails the gate instead of passing on git's say-so.
    run: kubectl get cm -n media media-dashboard -o jsonpath='{.data.dashboard\.py}' | grep -c 'def latest_audit_summary'
    expect_exact: "1"
---

# Give the daily media audit a durable output channel

## Why

The audit runs at 04:15 and its result exists ONLY as pod stdout. On
2026-09-06 the scheduled run succeeded and then became unreadable when a node
reboot garbage-collected the completed pod, so the day's numbers had to be
recovered by re-running the whole audit. The dashboard's
`latest_audit_summary()` reads those same pod logs and is equally blind after
any node event.

Cost today was one extra Job. The real cost is on a day when the share is
unhealthy: the comparison baseline is exactly what you lose, exactly when you
need it.

## Constraints established 2026-09-06 (do not re-derive)

- The audit container mounts `plex-media-smb` **read-only** and has no other
  writable volume, no DB credentials, and no network policy to `databases`.
- **A shared Longhorn RWO PVC between the audit Job and the dashboard
  Deployment is NOT an option.** They are separate pods that can land on
  different nodes, which is the `Multi-Attach` trap in
  `docs/sops/longhorn-rwo-multi-attach.md`. Do not "just add a PVC".
- Writing audit state into the media share itself is rejected: the share is
  user data, not application state, and it is the thing being audited.
- `coverage.py` already prints a parseable `COVERAGE_RESULT_JSON <json>` line
  (scripts-configmap.yaml). Mirroring that shape for the audit is the cheap
  half and should happen regardless.

## Approach

Two steps, in this order, because the first is useful even if the second slips:

1. **Emit `AUDIT_RESULT_JSON <json>`** from `audit.py`'s summary block, exactly
   mirroring `COVERAGE_RESULT_JSON`. One machine-readable line instead of a
   markdown block someone has to re-parse.

2. **Persist it to `sweep_history`**, which is already this cluster's home for
   operator-visible state that must outlive a pod. Needs:
   - the postgres credential available in `media` (mirror how another
     namespace obtains it — do NOT hand-copy a decoded secret),
   - a small table or a reuse of the existing findings/snapshot shape,
   - `latest_audit_summary()` in dashboard-configmap.yaml repointed at the DB,
     keeping the pod-log path as a fallback for the current run. That file
     renders `cm/media-dashboard`, served by `deployment/media-dashboard` —
     the dashboard is NOT called `library-tools-dashboard`; that is the app
     directory (F-5e5c14e6).

## Verification

```bash
# 1. the line exists and parses
kubectl logs -n media job/<latest audit job> | grep -c '^AUDIT_RESULT_JSON '   # 1

# 2. THE point of the plan: delete the pod, then read the result anyway
kubectl delete pod -n media -l job-name=<latest audit job>

# dashboard must still show the same numbers, with no audit pod left to read:
kubectl port-forward -n media svc/media-dashboard 8088:80 &
curl -s localhost:8088 | grep -A5 'Summary'
```

Check 2 is the whole plan. A green check 1 with a blind check 2 is the state
we are already in.

## Rollback

`git-revert`. The emit line is additive; the dashboard keeps its pod-log
fallback, so reverting restores exactly today's behaviour.
