# SOP: Wazuh SIEM Event-Flow Recovery (agents Active but SIEM silent)

> Description: Recover Wazuh alert ingestion when `agent_control -l` shows agents Active but the indexer/SIEM shows no events — typically after the wazuh-indexer loses its data (e.g. on a node reboot), which drops the filebeat ingest pipeline and index template that the long-running manager filebeat never re-pushes.
> Version: `2026.09.25`
> Last Updated: `2026-09-25`
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

### File integrity monitoring (FIM) scope (since `e503d904`, 2026-09-23)

FIM (`wazuh-syscheckd`) watches the **Talos host** through the DaemonSet's
read-only hostPath mount of `/` at `/host` (`wazuh-agents-daemonset.yaml`:
privileged, `mountPropagation: HostToContainer`). It does **not** watch the
agent container's own filesystem. Before `e503d904` the stanza named `/etc`,
`/usr/bin`, … and those paths resolved **inside the container**, so the nodes
were never watched. The control was mis-pointed, not missing (F-7a099e09).

The agent stanza is the `<syscheck>` block under the `agent.conf` key of
`wazuh-config-configmap.yaml`, mounted by `subPath` as the agent's `ossec.conf`.
The `<syscheck>` block under `master.conf` belongs to the manager.

| Setting | Value | Why |
|---|---|---|
| Realtime (inotify) watch | `/host/etc`, `/host/opt/cni/bin`, `/host/usr/local` | The surfaces that can change on an immutable OS. `/host/etc` holds the generated node config: `kubernetes/` (kubelet kubeconfig + `pki/`), `cri/`, `cni/`, `containerd/`, `pki/`, `extensions.yaml`. `/opt/cni/bin` holds the CNI plugins. `/usr/local` holds the system extensions |
| Scheduled scan only (`frequency` 43200 = 12h, plus `scan_on_start`) | `/host/boot`, `/host/usr/bin`, `/host/usr/sbin`, `/host/bin`, `/host/sbin` | A baseline hash of the EFI dir and the squashfs root. It changes only on a Talos upgrade, so realtime watches would be wasted |
| Ignored (Talos regenerates these at every boot) | `/host/etc/mtab`, `/host/etc/resolv.conf`, `/host/etc/hosts`, `/host/etc/machine-id`, `/host/etc/localtime` | Without the ignores, every node reboot produces a burst of "modified" alerts |
| Deliberately out | `/host/var` | kubelet pod churn |
| `report_changes` | **off, deliberately** | `/host/etc/kubernetes/kubeconfig-kubelet` and `pki/` are secrets. With `report_changes` on, their content diffs would be copied into alerts and into the indexer |
| NOT visible to FIM | the Talos **STATE** partition (machine config) | Talos mounts it at `/system/state`, and that mount does not propagate into the pod: `/host/system/state` is an empty directory (verified 2026-09-25). FIM cannot see machine-config changes. Check those out of band, with `talosctl get machineconfig` compared against the talhelper-generated config |

**After editing the stanza, bump `checksum/wazuh-config`** in the DaemonSet
pod-template annotations. The ConfigMap is mounted with `subPath`, which never
refreshes in a running pod, so without the bump the agents keep the old
config.

**inotify limit.** Realtime FIM uses one inotify watch per directory. The
extension trees under `/host/usr/local` are the largest realtime surface. If
the node limit is hit, syscheckd logs it and those directories fall back to
the 12h scan without any other signal. Live on 2026-09-25: all 3 nodes had
`fs.inotify.max_user_watches = 1048576` and `max_user_instances = 8192`,
`ossec.log` held no inotify or limit messages, and the full scan took about
50 s per node. Check with §6 Test 3.

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

### Test 3: FIM watches the host, and realtime did not hit the inotify limit

```bash
for p in $(kubectl -n security get pods -o name | grep wazuh-agent); do
  echo "== $p"
  kubectl -n security exec $p -- sh -c '
    cat /proc/sys/fs/inotify/max_user_watches
    grep "(6003): Monitoring path" /var/ossec/logs/ossec.log | tail -3
    grep -iE "inotify|maximum limit" /var/ossec/logs/ossec.log | tail -3
    grep -E "\(600[89]\)" /var/ossec/logs/ossec.log | tail -2'
done
```
Expected: `Monitoring path: '/host/etc'`, `'/host/opt/cni/bin'`, `'/host/usr/local'` with `realtime` in the options; **no** inotify or "maximum limit" lines; a `(6008) scan started` followed by `(6009) scan ended`.
If failed: `Monitoring path: '/etc'` (without `/host`) means the old stanza is still loaded, so bump `checksum/wazuh-config` and let the DaemonSet roll. An inotify-limit line means realtime has silently degraded to the 12h scan for the affected tree. Narrow the realtime set before you consider raising the node sysctl, which is a Talos machine-config change.

---

## 7) Troubleshooting

| Symptom | Likely Cause | First Fix |
|---------|--------------|-----------|
| Agents Active in `agent_control -l` but SIEM/sweep says silent | filebeat ingest pipeline + template lost after indexer data reset | §4 `filebeat setup --index-management --pipelines` |
| filebeat log: `pipeline ... does not exist` | pipeline dropped from indexer; filebeat never re-`setup` | §4 setup |
| Only `wazuh-states-inventory-*` indices exist, no `wazuh-alerts-*` | native connector works, filebeat path broken | §4 setup |
| Recovery works, then breaks again on next reboot | ~~indexer lost its Longhorn data on reboot~~ **FIXED 2026-07-14**: `path.data` was unset → data lived on the ephemeral overlay, not the PVC | verify `path.data: /var/lib/wazuh-indexer` is present in `wazuh-indexer-statefulset.yaml`'s opensearch.yml; `df -h /var/lib/wazuh-indexer` inside the pod must show `/dev/longhorn/...` |
| FIM produces (almost) no syscheck alerts from the nodes | stanza watches container paths (`/etc`, `/usr/bin`) instead of `/host/...`. This was the state before `e503d904`: 2 syscheck alerts in 30 days | §3 FIM scope; §6 Test 3 |
| Burst of FIM "modified" alerts after every node reboot | a file Talos regenerates at boot is not in the `<ignore>` list | add it as `<ignore>/host/etc/<file></ignore>` and bump `checksum/wazuh-config` |
| FIM config edit has no effect | ConfigMap is `subPath`-mounted, and the DaemonSet checksum annotation was not bumped | bump `checksum/wazuh-config` in `wazuh-agents-daemonset.yaml` |
| A Talos machine-config change raised no FIM alert | expected: the STATE partition is not visible from the pod | check machine config out of band (`talosctl get machineconfig`) |
| One node agent still silent minutes after fix | that node is simply low-volume (no rule match yet) | confirm it produces events in `alerts.json`; wait or trigger a real alert |
| A rule floods from Wazuh's OWN logs (e.g. rule 2501 "User authentication failure" sourced from `/host/var/log/containers/wazuh-manager-*`), and a `<localfile>` has multiple `<exclude>` entries but only one takes effect | **Wazuh logcollector honors only ONE `<exclude>` per `<localfile>`** — the parser overwrites `logf->exclude` on each element, so the LAST `<exclude>` wins and the earlier ones are silently ignored. Fixed 2026-07-14 (commit `89490aaa`). | Collapse all patterns into a SINGLE `<exclude>` glob. For the container-log tail we use `<exclude>/host/var/log/containers/*_security_*.log</exclude>` — the CRI symlink is `<pod>_<namespace>_<container>-<hash>.log` and k8s forbids `_` in those fields, so `_security_` matches only the namespace, dropping the whole Wazuh+Falco stack's self-loops. Verify per-agent: `kubectl exec -n security <agent-pod> -- grep -i 'File excluded' /var/ossec/logs/ossec.log` should list the manager+agent container logs. **Caveat:** this drops *stdout* for ANY workload in the `security` ns — a future security app whose stdout is a real detection source must use its own dedicated `<localfile>` (as Falco does via `falco.log`). |

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
FIM: §6 Test 3 is clean on every agent (host paths monitored, no inotify-limit lines).

---

## 10) Security Check

```bash
# no plaintext indexer creds committed
grep -rniE "INDEXER_PASSWORD" kubernetes/apps/security/wazuh/ | grep -v sops
# secret still SOPS-encrypted
head -5 kubernetes/apps/security/wazuh/app/secret.sops.yaml | grep -q ENC || echo "WARN: not encrypted"
```
```bash
# FIM must never diff the kubelet secrets into alerts
grep -n "report_changes" kubernetes/apps/security/wazuh/app/wazuh-config-configmap.yaml
```
Expected: no `report_changes` on the `/host/etc` directories (see §3 FIM scope).

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
- `e503d904`: FIM re-pointed at the Talos host (`/host`), F-7a099e09
- `docs/sops/disaster-recovery.md` (Wazuh indexer/manager/agent credentials)
- `docs/applications.md` (wazuh-manager / wazuh-agent rows)
- Memory: `project_node_reboot_logging_gap.md` (Talos reboots as a recurring disruption class)

---

## Version History

- `2026.09.25`: Documented the FIM scope from `e503d904` (F-eef53afd). Covers the realtime `/host` paths, the 12h baseline paths, the boot-regenerated ignore list, why `report_changes` is off, and that the Talos STATE partition is not visible from the pod (`/host/system/state` is empty, verified live). Also the `subPath` checksum-bump rule and an inotify-limit check (§6 Test 3; live baseline `max_user_watches=1048576`, no limit messages on any of the 3 agents). Added troubleshooting rows.
- `2026.07.14`: **Root cause of the data loss found and fixed.** The indexer's OpenSearch `path.data` was never set; with `OPENSEARCH_PATH_CONF=/usr/share/wazuh-indexer/config`, `path.data` defaulted to `$ES_HOME/data` (`/usr/share/wazuh-indexer/data`) on the ephemeral container overlay instead of the Longhorn PVC mounted at `/var/lib/wazuh-indexer` (verified live: the 12M active `nodes/` dir sat on overlay while the PVC held only a stale 212K May-7 bootstrap). Every pod restart/reboot bootstrapped an empty data dir. Fixed by pinning `path.data: /var/lib/wazuh-indexer` in `wazuh-indexer-statefulset.yaml` + a `checksum/indexer-config` pod annotation to roll it. Post-roll the PVC bootstrapped fresh (`.opendistro_security` survived from the old PVC data, so no securityadmin re-run was needed); this SOP's `filebeat setup` restored the pipeline + template and event flow resumed. The data-loss trigger is now closed — reboots no longer wipe the indexer.
- `2026.07.13`: Initial SOP. Written after the 2026-07-12 Talos v1.13.6 reboot reset the wazuh-indexer to an empty data dir, dropping the `filebeat-7.10.2-wazuh-alerts-pipeline` and `wazuh` template; the long-running manager filebeat never re-`setup`, so all alerts were rejected (`pipeline ... does not exist`) and dropped — the daily sweep flagged all 3 node agents "silent >2h" while `agent_control -l` showed them Active. Fix: `filebeat setup --index-management --pipelines`. Open follow-up: determine why the indexer's Longhorn volume (`healthy`, 2 replicas) came up empty on reboot.
