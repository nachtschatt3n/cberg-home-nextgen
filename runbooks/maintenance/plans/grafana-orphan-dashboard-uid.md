---
plan_id: grafana-orphan-dashboard-uid
component: grafana
pr: null                              # not a version bump; stale runtime state
kind: config
current: "dashboard uid 9fa0d141-d019-4ad7-8bc5-42196ee308bd ('Prometheus / Overview') is held by an orphaned provisioning record with an EMPTY provisionedExternalId, so the kube-prometheus-stack sidecar cannot claim it"
target: "the uid is owned by sidecarProvider; the sidecar provisions prometheus.json without error"
update_type: state-repair
risk: low
est_duration_min: 30
needs_reboot: false
touches:
  namespaces: [monitoring]
  resources:
    - deployment/grafana
    - pvc/grafana-config                        # sqlite lives here
  shared: []
depends_on: []
conflicts_with: []
capability_change: false
rollback_class: backup-restore   # DECLARED 2026-09-06. The change is a DELETE
                          # against grafana's sqlite, so there is no commit to
                          # revert. It is nevertheless cheap to undo: the
                          # dashboard's content is byte-equivalent to the
                          # chart ConfigMap that will immediately re-provision
                          # it, so the ConfigMap IS the backup.
status: awaiting-go   # 2026-09-08 nightly window: condition RE-VERIFIED live (60 x
                      # "same uid already exists" in 30m on grafana-598f7c549c-rgkxh,
                      # matching the plan's ~2880/day). NOT run: derived class is
                      # HUMAN-GATED (rollback_class: backup-restore names no
                      # backup_gate), and nightly is mode: unattended. go/no-go is
                      # with OpenClaw home-operation, proposed sat-attended:2026-09-12.
window: null          # left for the window-scheduler/operator; the proposed slot
                      # rides on the go/no-go issue, not self-assigned here.
---

# Grafana: free the dashboard uid held by an orphaned provisioning record

## Why this is not just log noise

~2,880 `failed to save dashboard ... A dashboard with the same uid already
exists` errors per day, and they are permanent: every sidecar reconcile (30s)
retries and fails. The visible cost is a poisoned error stream — any future
"is Grafana healthy" check that counts errors is reading 2,880/day of a known
non-event, which is how a real error gets missed.

The dashboard itself renders fine. This is about **ownership**, not content.

## What was established on 2026-09-06 (do not re-derive)

- The uid is `9fa0d141-d019-4ad7-8bc5-42196ee308bd`, title `Prometheus / Overview`.
- **Only one** ConfigMap ships it: `monitoring/kube-prometheus-stack-prometheus`,
  key `prometheus.json`. This is NOT two competing sources.
- Live DB copy vs ConfigMap copy: **identical** — same uid, same title, all 15
  panel titles equal. Nothing is lost by deleting the DB copy.
- The DB record: `provisioned: true`, **`provisionedExternalId: ""`**,
  folder `General` (folderUid `""`), version 2, created 2026-02-07, "updated"
  2026-07-17 by `Anonymous` (the power-outage date — a re-save, not a human edit).
- `DELETE /api/dashboards/uid/<uid>` is **refused**: `provisioned dashboard
  cannot be deleted`. The API declines regardless of the provider's
  `disableDeletion: false`.
- Grafana's own orphan cleanup cannot fix it either: with an EMPTY external id
  there is no file path to match against, so the record is unreachable from
  both directions. That is what makes this stuck rather than self-healing.
- The grafana image is **`-distroless`**: no `sh`, no `wget`, no `ls`. Any step
  that shells into the grafana container is unrunnable — see
  `docs/sops/grafana-image-changes.md`.

## Pre-checks

1. Confirm the uid is still stuck and still orphaned:
   ```bash
   curl -s -u "$U:$P" http://localhost:3000/api/dashboards/uid/9fa0d141-d019-4ad7-8bc5-42196ee308bd \
     | python3 -c "import sys,json;m=json.load(sys.stdin)['meta'];print(m['provisioned'], repr(m['provisionedExternalId']))"
   # EXPECT: True ''
   ```
   If `provisionedExternalId` is non-empty, STOP — the situation changed and
   this plan's premise no longer holds.
2. Re-confirm content equivalence before deleting anything (panel titles, uid).
3. Snapshot the dashboard JSON to a path outside the repo.

## Execution

The sqlite file is on the `grafana-config` Longhorn PVC and the container has no
shell, so use an ephemeral debug container rather than `kubectl exec`:

```bash
kubectl debug -n monitoring deploy/grafana -it \
  --image=alpine:3 --target=grafana -- sh
# inside: apk add --no-cache sqlite
# sqlite3 /var/lib/grafana/grafana.db \
#   "DELETE FROM dashboard_provisioning WHERE dashboard_id =
#      (SELECT id FROM dashboard WHERE uid='9fa0d141-d019-4ad7-8bc5-42196ee308bd');"
```

Deleting only the PROVISIONING row (not the dashboard row) is deliberate: it
makes the dashboard an ordinary DB dashboard, which the sidecar is then allowed
to overwrite on its next reconcile. Deleting the dashboard row as well is the
fallback if the sidecar still refuses.

`strategy: Recreate` is NOT needed — no pod restart is required; the sidecar
reconciles every 30s.

## Verification

```bash
# 1. the error must STOP (this is the whole point)
kubectl logs -n monitoring deploy/grafana -c grafana --since=5m | grep -c "same uid already exists"
# EXPECT: 0

# 2. the dashboard must still exist, now owned by the sidecar
curl -s -u "$U:$P" .../api/dashboards/uid/9fa0d141-... \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['meta']['provisionedExternalId'], len(d['dashboard']['panels']))"
# EXPECT: a non-empty path ending prometheus.json, and 15 panels
```

A zero in check 1 with the dashboard MISSING in check 2 is a failure, not a
pass — check them together.

## Rollback

The ConfigMap re-provisions identical content within 30s, so the failure mode is
self-healing. If the dashboard is genuinely gone, POST the snapshot back:

```bash
curl -s -X POST -u "$U:$P" -H 'Content-Type: application/json' \
  --data @grafana-prom-overview.backup.json http://localhost:3000/api/dashboards/db
```
