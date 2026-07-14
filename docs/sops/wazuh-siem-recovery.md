# SOP: Wazuh SIEM Event-Flow Recovery (agents Active but SIEM silent)

> Description: Recover Wazuh alert ingestion when `agent_control -l` shows agents Active but the indexer/SIEM shows no events — typically after the wazuh-indexer loses its data (e.g. on a node reboot), which drops the filebeat ingest pipeline and index template that the long-running manager filebeat never re-pushes.
> Version: `2026.07.14`
> Last Updated: `2026-07-14`
> Owner: `platform-operator`

---

## 1) Description

Covers the failure where **Wazuh agents are healthy and connected** (Active in `agent_control -l`, keepalives current) yet **no events reach the indexer / dashboard / sweep**, so the daily security sweep flags every node agent as "silent for >2h".

Root cause pattern: the `wazuh-indexer` comes up on an **empty data directory** (indices, index templates, and ingest pipelines gone). The `wazuh-manager` `filebeat` process keeps running from **before** the indexer reset, so it never re-runs its startup `setup` — the `filebeat-7.10.2-wazuh-alerts-pipeline` ingest pipeline and `wazuh` index template are absent. Every alert filebeat publishes is rejected with `pipeline with id [filebeat-7.10.2-wazuh-alerts-pipeline] does not exist`, a per-document permanent error, so filebeat **drops the event and advances its registry offset** — the SIEM goes silent while the manager's native connector (`wazuh-states-inventory-*`) keeps working, masking the break.

- Scope: `security` namespace — `wazuh-manager-master-0`, `wazuh-indexer-0`, `wazuh-agent` DaemonSet.
- Prerequisites: `kubectl` exec into the manager pod; indexer credentials from `kubernetes/apps/security/wazuh/app/secret.sops.yaml` (`INDEXER_USERNAME` / `INDEXER_PASSWORD`).
- Root cause of the data loss (RESOLVED 2026-07-14): the indexer's OpenSearch `path.data` was unset, so with `OPENSEARCH_PATH_CONF=/usr/share/wazuh-indexer/config` it defaulted to `$ES_HOME/data` (`/usr/share/wazuh-indexer/data`) on the **ephemeral container overlay** — NOT the Longhorn PVC mounted at `/var/lib/wazuh-indexer`. Every pod restart/node reboot wiped the data. Fixed by pinning `path.data: /var/lib/wazuh-indexer` in `wazuh-indexer-statefulset.yaml`. This SOP still applies for the one-time re-`setup` after that fix rolled the pod (the PVC bootstrapped fresh), and for any future indexer reset.

---

## 2) Overview

| Setting | Value |
|---------|-------|
| Namespace | `security` |
| Source of truth | `kubernetes/apps/security/wazuh/app/` |
| Manager → indexer path | `filebeat` (module `wazuh`, alerts) → ingest pipeline `filebeat-7.10.2-wazuh-alerts-pipeline` → index `wazuh-alerts-4.x-YYYY.MM.DD` |
| Native connector path | manager `indexer` block → `wazuh-states-inventory-*` (independent of filebeat; keeps working, masks the outage) |
| filebeat config | `/etc/filebeat/filebeat.yml` — `setup.template.json` (`wazuh`), `setup.ilm.enabled: false` |
| Sweep detection | `runbooks/security-check.py` slice 4 — aggregates `wazuh-alerts-*` docs by `agent.name` over `now-2h`, cross-refs `agent_control -l` Active list |

Key tell: `agent_control -l` = **Active** for all agents, but `wazuh-alerts-*` has **no daily index** (only `wazuh-states-inventory-*`). That combination = filebeat ingest pipeline missing.

---

## 3) Blueprints

- Source of truth file(s): `kubernetes/apps/security/wazuh/app/wazuh-manager-statefulset.yaml`, `wazuh-agents-daemonset.yaml`, `wazuh-indexer-statefulset.yaml`
- Related manifests/templates: filebeat config baked into the manager image at `/etc/filebeat/filebeat.yml` + template `/etc/filebeat/wazuh-template.json`
- Required IDs/constants: pipeline `filebeat-7.10.2-wazuh-alerts-pipeline`; template `wazuh`; index pattern `wazuh-alerts-4.x-*`

N/A — no git-tracked blueprint changes are part of the recovery (it is a runtime re-`setup`, not a manifest edit).

---

## 4) Operational Instructions

Recovery is a **non-destructive, additive** runtime action (recreates a pipeline + template; deletes nothing, touches no PVC). Not a GitOps change — treat as a recovery/unblock.

1. Confirm the pattern (see §8 Diagnose Example 1): agents Active, no `wazuh-alerts-*` index, filebeat log shows `pipeline ... does not exist`.
2. Re-run filebeat setup inside the manager pod to reload the template + ingest pipeline:

```bash
kubectl exec -n security wazuh-manager-master-0 -c wazuh-manager -- \
  filebeat setup --index-management --pipelines --modules wazuh -c /etc/filebeat/filebeat.yml
# Expect: "Index setup finished." + "Loaded Ingest pipelines"
```

3. No filebeat restart needed — the running harvester publishes new alerts through the now-present pipeline on its next batch. (Events dropped during the outage are lost; recovery is forward-only.)
4. Verify (see §6): the `wazuh-alerts-4.x-<today>` index appears and all agents populate it.

> GitOps note: there is no manifest to commit for the recovery itself. Do **not** delete the manager or indexer pod as a first response — that risks another indexer data-loss window and loses in-flight state.

---

## 5) Examples

### Example A: post-reboot recovery (the common case)

```bash
# 1. verify pipeline missing
kubectl exec -n security wazuh-manager-master-0 -c wazuh-manager -- sh -c '
  U=$INDEXER_USERNAME P=$INDEXER_PASSWORD
  curl -s -k -o /dev/null -w "%{http_code}\n" -u "$U:$P" \
    https://wazuh-indexer:9200/_ingest/pipeline/filebeat-7.10.2-wazuh-alerts-pipeline'   # 404

# 2. fix
kubectl exec -n security wazuh-manager-master-0 -c wazuh-manager -- \
  filebeat setup --index-management --pipelines --modules wazuh -c /etc/filebeat/filebeat.yml
```

### Example B: also clean up any manual probe index created during diagnosis

```bash
# if you POSTed a test doc to wazuh-alerts-4.x-probe while diagnosing
curl -s -k -u "$U:$P" -X DELETE https://wazuh-indexer:9200/wazuh-alerts-4.x-probe
```

---

## 6) Verification Tests

Load creds first (never echo them):
```bash
eval "$(sops -d kubernetes/apps/security/wazuh/app/secret.sops.yaml \
  | grep -E 'INDEXER_(USERNAME|PASSWORD):' \
  | sed -E 's/^ *([A-Z_]+): *"?([^"]*)"?/\1=\x27\2\x27/')"
```

### Test 1: pipeline + template present

```bash
kubectl exec -n security wazuh-manager-master-0 -c wazuh-manager -- \
  env U="$INDEXER_USERNAME" P="$INDEXER_PASSWORD" sh -c '
  curl -s -k -o /dev/null -w "pipeline=%{http_code}\n" -u "$U:$P" https://wazuh-indexer:9200/_ingest/pipeline/filebeat-7.10.2-wazuh-alerts-pipeline
  curl -s -k -o /dev/null -w "template=%{http_code}\n" -u "$U:$P" https://wazuh-indexer:9200/_template/wazuh'
```
Expected: `pipeline=200`, `template=200`.
If failed: re-run the §4 setup; check `filebeat setup` output for a template-load error.

### Test 2: all agents indexing (mirrors the sweep query)

```bash
kubectl exec -n security wazuh-manager-master-0 -c wazuh-manager -- \
  env U="$INDEXER_USERNAME" P="$INDEXER_PASSWORD" sh -c '
  curl -s -k -u "$U:$P" https://wazuh-indexer:9200/wazuh-alerts-*/_search -H "Content-Type: application/json" \
    -d "{\"size\":0,\"query\":{\"range\":{\"@timestamp\":{\"gte\":\"now-2h\"}}},\"aggs\":{\"by_agent\":{\"terms\":{\"field\":\"agent.name\",\"size\":50}}}}"'
```
Expected: a bucket per node agent (`k8s-nuc14-01/02/03`). Low-volume nodes may take a few minutes to appear — they only write to `wazuh-alerts` on rule matches, not keepalives.
If failed: confirm alerts.json is fresh (`stat /var/ossec/logs/alerts/alerts.json`) and filebeat is up (`ps -o etimes -C filebeat`).

---

## 7) Troubleshooting

| Symptom | Likely Cause | First Fix |
|---------|--------------|-----------|
| Agents Active in `agent_control -l` but SIEM/sweep says silent | filebeat ingest pipeline + template lost after indexer data reset | §4 `filebeat setup --index-management --pipelines` |
| filebeat log: `pipeline ... does not exist` | pipeline dropped from indexer; filebeat never re-`setup` | §4 setup |
| Only `wazuh-states-inventory-*` indices exist, no `wazuh-alerts-*` | native connector works, filebeat path broken | §4 setup |
| Recovery works, then breaks again on next reboot | ~~indexer lost its Longhorn data on reboot~~ **FIXED 2026-07-14**: `path.data` was unset → data lived on the ephemeral overlay, not the PVC | verify `path.data: /var/lib/wazuh-indexer` is present in `wazuh-indexer-statefulset.yaml`'s opensearch.yml; `df -h /var/lib/wazuh-indexer` inside the pod must show `/dev/longhorn/...` |
| One node agent still silent minutes after fix | that node is simply low-volume (no rule match yet) | confirm it produces events in `alerts.json`; wait or trigger a real alert |

```bash
# filebeat harvesting? (offset should track alerts.json size; process should be long-lived)
kubectl exec -n security wazuh-manager-master-0 -c wazuh-manager -- sh -c \
  'ls -l /var/ossec/logs/alerts/alerts.json; ps -o pid,etimes,cmd -C filebeat | grep -v grep'
# NB: `filebeat test output` writes a startup banner to /var/log/filebeat/filebeat — do not mistake it for a filebeat restart.
```

---

## 8) Diagnose Examples

### Diagnose Example 1: confirm the "silent but Active" pattern

```bash
# agents Active?
kubectl exec -n security wazuh-manager-master-0 -c wazuh-manager -- /var/ossec/bin/agent_control -l
# any wazuh-alerts index? (creds loaded as in §6)
kubectl exec -n security wazuh-indexer-0 -c wazuh-indexer -- \
  env U="$INDEXER_USERNAME" P="$INDEXER_PASSWORD" sh -c \
  'curl -s -k -u "$U:$P" "https://localhost:9200/_cat/indices/wazuh-alerts-*?v"'
# filebeat rejection reason
kubectl logs -n security wazuh-manager-master-0 -c wazuh-manager --tail=2000 | grep -i "does not exist" | tail -3
```
Expected root-cause confirmation: agents `Active`; **no** `wazuh-alerts-*` index; log shows `pipeline with id [filebeat-7.10.2-wazuh-alerts-pipeline] does not exist`.
If unclear: check the manual write path — `POST wazuh-alerts-4.x-probe/_doc` should succeed (proves auth/connectivity are fine and isolates the fault to the missing pipeline/template).

### Diagnose Example 2: did the indexer come up empty?

```bash
kubectl exec -n security wazuh-indexer-0 -c wazuh-indexer -- \
  env U="$INDEXER_USERNAME" P="$INDEXER_PASSWORD" sh -c \
  'curl -s -k -u "$U:$P" "https://localhost:9200/_cat/indices?v&h=index,creation.date.string&s=creation.date.string"'
```
Expected: if `.opendistro_security` / `.plugins-ml-config` were (re)created at the same timestamp as the last indexer pod start, the indexer bootstrapped on an **empty** data dir — the data-loss trigger for this incident.
If unclear: correlate `kubectl get pod wazuh-indexer-0 -o jsonpath='{.status.startTime}'` with the index creation timestamps.

---

## 9) Health Check

```bash
# 1. all 3 node agents Active
kubectl exec -n security wazuh-manager-master-0 -c wazuh-manager -- /var/ossec/bin/agent_control -l | grep -c Active
# 2. pipeline + template present (Test 1)
# 3. today's alerts index growing
kubectl exec -n security wazuh-indexer-0 -c wazuh-indexer -- env U="$INDEXER_USERNAME" P="$INDEXER_PASSWORD" \
  sh -c 'curl -s -k -u "$U:$P" "https://localhost:9200/_cat/indices/wazuh-alerts-4.x-*?v&h=index,docs.count"'
```
Expected: ≥3 Active (plus server), `pipeline=200`/`template=200`, `docs.count` increasing.

---

## 10) Security Check

```bash
# no plaintext indexer creds committed
grep -rniE "INDEXER_PASSWORD" kubernetes/apps/security/wazuh/ | grep -v sops
# secret still SOPS-encrypted
head -5 kubernetes/apps/security/wazuh/app/secret.sops.yaml | grep -q ENC || echo "WARN: not encrypted"
```
Expected: no plaintext credentials in repo; `secret.sops.yaml` still encrypted. The recovery adds an ingest pipeline + template only — no auth, RBAC, or exposure change.

---

## 11) Rollback Plan

The recovery is additive (loads a template + pipeline). There is nothing to roll back — if `filebeat setup` misbehaves you can safely re-run it (`setup.template.overwrite: true`). Do **not** delete indices or the indexer PVC to "reset" — that reproduces the original data-loss.

```bash
# re-run setup is idempotent
kubectl exec -n security wazuh-manager-master-0 -c wazuh-manager -- \
  filebeat setup --index-management --pipelines --modules wazuh -c /etc/filebeat/filebeat.yml
```

---

## 12) References

- `runbooks/security-check.py` (slice 4 — per-agent heartbeat silence detection)
- `runbooks/wazuh-unifi-syslog.md`
- `docs/sops/disaster-recovery.md` (Wazuh indexer/manager/agent credentials)
- `docs/applications.md` (wazuh-manager / wazuh-agent rows)
- Memory: `project_node_reboot_logging_gap.md` (Talos reboots as a recurring disruption class)

---

## Version History

- `2026.07.14`: **Root cause of the data loss found and fixed.** The indexer's OpenSearch `path.data` was never set; with `OPENSEARCH_PATH_CONF=/usr/share/wazuh-indexer/config`, `path.data` defaulted to `$ES_HOME/data` (`/usr/share/wazuh-indexer/data`) on the ephemeral container overlay instead of the Longhorn PVC mounted at `/var/lib/wazuh-indexer` (verified live: the 12M active `nodes/` dir sat on overlay while the PVC held only a stale 212K May-7 bootstrap). Every pod restart/reboot bootstrapped an empty data dir. Fixed by pinning `path.data: /var/lib/wazuh-indexer` in `wazuh-indexer-statefulset.yaml` + a `checksum/indexer-config` pod annotation to roll it. Post-roll the PVC bootstrapped fresh (`.opendistro_security` survived from the old PVC data, so no securityadmin re-run was needed); this SOP's `filebeat setup` restored the pipeline + template and event flow resumed. The data-loss trigger is now closed — reboots no longer wipe the indexer.
- `2026.07.13`: Initial SOP. Written after the 2026-07-12 Talos v1.13.6 reboot reset the wazuh-indexer to an empty data dir, dropping the `filebeat-7.10.2-wazuh-alerts-pipeline` and `wazuh` template; the long-running manager filebeat never re-`setup`, so all alerts were rejected (`pipeline ... does not exist`) and dropped — the daily sweep flagged all 3 node agents "silent >2h" while `agent_control -l` showed them Active. Fix: `filebeat setup --index-management --pipelines`. Open follow-up: determine why the indexer's Longhorn volume (`healthy`, 2 replicas) came up empty on reboot.
