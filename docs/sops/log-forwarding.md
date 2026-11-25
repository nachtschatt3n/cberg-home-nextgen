# SOP: Off-cluster log forwarding (Talos, UniFi, UNAS) and NAS availability alert

> Description: How Talos kernel + service logs, UniFi controller syslog and UNAS syslog reach Elasticsearch through the edot-collector, and how an unreachable NAS pages.
> Version: `2026.11.25` (date versioning, e.g. `2026.02.04`)
> Last Updated: `2026-11-25`
> Owner: `platform / SRE`

---

## 1) Description

Pod logs reach `logs-generic-default` through the edot-collector. Before 2026-11-25
three other sources were not covered: Talos service logs (machined, apid,
kubelet, etcd, ...), UniFi controller/gateway events, and the NAS. A whole-host
NAS outage (2026-11-25 ~01:48Z, ICMP included) was visible only through consumer
pod errors.

- Scope: `monitoring/edot-collector`, Talos machine config patches, Uptime Kuma monitor #35, `nas-availability-alerts`.
- Prerequisites: mise env, `talosctl`/`talhelper`, ES access (port-forward + `elastic` user from `elasticsearch-es-elastic-user`).
- Out of scope: Wazuh's own UniFi syslog target (`security/wazuh-syslog-unifi`, 192.168.55.27:514) and the kernel feed design (see `docs/troubleshooting/node-reboot-observability.md`).

Status at 2026-11-25 (be precise about what is live):

| Feed | Collector side | Sender side |
|---|---|---|
| Talos kernel (kmsg) | LIVE since 2026-06-29, udp 5171 on .18 | LIVE (`KmsgLogConfig`). `talos.logging.kernel` kernel arg is NOT needed and must not be added |
| Talos service logs | LIVE, udp 5173 on .19 | LIVE on all 3 nodes (hot-applied 2026-11-25, no reboot, etcd term unchanged) |
| UniFi syslog | LIVE, udp 5174 on .19 | NOT configured (operator action, section 4.4). Measured: Wazuh receives nothing from the UDM either |
| UNAS syslog | LIVE, udp 5175 on .19 | Unconfirmed that the product can forward syslog (section 4.5) |
| NAS unreachable alert | n/a | LIVE (rules in Prometheus) |

---

## 2) Overview

| Setting | Value |
|---------|-------|
| Namespace | `monitoring` |
| Receiver Service | `edot-collector-syslog`, Cilium LB IP `192.168.55.19` (UDP only) |
| Ports | `5173` Talos service logs (json_lines), `5174` UniFi syslog (raw), `5175` UNAS syslog (raw) |
| Kernel feed (unchanged) | `edot-collector-talos-kmsg`, `192.168.55.18:5171/udp` |
| ES stream | `logs-generic-default` |
| Filters | `resource.attributes.service.name` = `talos-kernel`, `talos-<service>` (e.g. `talos-machined`), `unifi`, `unas`; `attributes.log_source` carries the same tag; node = `attributes.net.peer.ip` |
| Source of truth | `kubernetes/apps/monitoring/edot-collector/app/{configmap,deployment,service-syslog}.yaml`, `kubernetes/bootstrap/talos/patches/global/machine-service-logging.yaml`, `kubernetes/apps/monitoring/kube-prometheus-stack/app/nas-availability-alerts.yaml` |
| Why UDP | Talos senders never reconnect after a sink restart over TCP; UDP survives collector restarts |
| Why raw bodies for UniFi/UNAS | dialect (RFC3164/5424) is unknown until a sender exists; a parse failure must never drop a line. Body stays verbatim, query with `wildcard` on `body.text` (KEYWORD field) |

---

## 3) Blueprints

- Receivers: `udp_log/talos-service`, `udp_log/unifi`, `udp_log/unas` and pipelines `logs/talos-service`, `logs/unifi`, `logs/unas` in the collector ConfigMap.
- Resource attributes: processors `resource/talos-kernel`, `resource/unifi`, `resource/unas`, `transform/talos-service-name`.
- Talos: `machine.logging.destinations` -> `udp://192.168.55.19:5173/`, `format: json_lines` (listed in `talconfig.yaml` global patches).

```yaml
machine:
  logging:
    destinations:
      - endpoint: udp://192.168.55.19:5173/
        format: json_lines
```

---

## 4) Operational Instructions

### 4.1 Collector change (GitOps)

1. Edit the ConfigMap. Escape every shell-style dollar-brace as doubled-dollar (Flux postBuild runs envsubst).
2. Validate on the exact image BEFORE committing. Render, then run a throwaway pod with the config in an env var (no shell in the image):
   `kubectl -n monitoring run otelval --rm -i --restart=Never --image=otel/opentelemetry-collector-contrib:<tag> --env=ES_PASSWORD=x --env="OTEL_CFG=$(cat rendered.yml)" -- validate --config=env:OTEL_CFG`
   Silence + exit 0 = valid. Always run a negative control (reference a missing receiver) and see it fail, otherwise silence proves nothing.
3. Take a control reading first: ES doc count `now-5m` and per-node kmsg last-seen.
4. Commit, push, wait for the Recreate roll (~45 s), then repeat the control readings.
5. A collector restart can stall a Talos kmsg sender (see node-reboot-observability.md). After the roll check per-node kmsg last-seen; `TalosKernelLogsMissingFromNode` catches a silent node after 3 h.

### 4.2 Talos service logs: hot apply (no reboot) - DONE 2026-11-25 (kept for re-runs)

Prerequisite: the collector receiver on 5173 is live (it is).

```bash
cd kubernetes/bootstrap/talos
talhelper genconfig                      # writes clusterconfig/kubernetes-k8s-nuc14-0N.yaml (gitignored)
# one node at a time, start with 03 (fewest stateful DBs)
talosctl -n 192.168.55.13 apply-config --dry-run -f clusterconfig/kubernetes-k8s-nuc14-03.yaml   # expect ONLY the logging block
talosctl -n 192.168.55.13 apply-config --mode=no-reboot -f clusterconfig/kubernetes-k8s-nuc14-03.yaml
# verify within a minute (see section 6), then repeat for .12 and .11
```

The only expected diff is `machine.logging.destinations`. If the dry run shows anything else, STOP: the rendered config has drifted from the live node.

### 4.3 Kernel logs: no node roll needed

The brief's `talos.logging.kernel=udp://...` kernel arg is the older mechanism. `KmsgLogConfig` (already applied, `machine-kmsg-logging.yaml`) does the same without a reboot and is live. Do not add the kernel arg; it would double-ship and requires a node roll for nothing.

### 4.4 UniFi (UDM) syslog - OPERATOR CLICK-PATH (not done)

**Measured 2026-11-25 (read-only):** no evidence Wazuh receives UniFi syslog today. Zero alerts with a UniFi decoder/CEF origin in 9 days of Wazuh alert files, no conntrack entry from the UDM to 192.168.55.27:514 on any node, and no UDM-sourced packet seen by `cilium-dbg monitor` on all 3 nodes over 100 s. Wazuh archives are empty (archiving off), so below-alert-level events cannot be excluded, but a firewall-log feed would have produced alerts. Consequence: pointing the UDM at the collector displaces nothing that works. Still an operator click (no `unifictl` write path), and if Wazuh was intended to receive it, fix that separately.

Not changed by an agent: `unifictl` has no syslog-target read or write command (`unifictl local log settings` returns alert settings only), so the current target cannot be read back safely.

Known: the repo documents UniFi -> Wazuh at `192.168.55.27:514/udp` (`security/wazuh-syslog-unifi`). UniFi's SIEM/activity-log target is a SINGLE host:port, so pointing it at the collector DISPLACES Wazuh. Decide first:

- Option A (recommended to start): leave Wazuh as is. UniFi events stay in Wazuh only.
- Option B: change the UniFi target to `192.168.55.19:5174` (UDP). Wazuh then loses UniFi events unless a relay is added. Do not do this without an explicit decision about Wazuh.
- Option C (cleanest, needs new work): add a fan-out in the collector or Wazuh so one UDM target feeds both. Not built.

Click-path (menu names vary by Network app version, verify on screen): UniFi Network -> Settings -> Control Plane -> Integrations -> Activity Logging / SIEM Server (or "Remote Logging" for device logs) -> enable Syslog, server `192.168.55.19`, port `5174`, UDP -> Apply. The UDM reaches the LB IP via inter-VLAN routing, which is fine for log volume.

### 4.5 UNAS syslog - OPERATOR (not done, not verified)

2026-11-25 research (two web searches, standard mode): no Ubiquiti documentation or release note found that mentions syslog/remote-logging for UNAS / UniFi Drive. The UNAS is NOT adopted in the Network app (not in `unifictl local device list`), so the Network app's site remote-logging cannot cover it. Treat forwarding as unsupported until someone sees a setting in the UniFi Drive console; the NAS signal is the `NasUnreachable*` alerts.

I could not verify that the UNAS product exposes a syslog-forwarding setting. Check the UNAS/UniFi Drive console Settings for a system-log or remote-syslog entry; if present, target `192.168.55.19` port `5175` UDP. If the product has none, the honest options are: (a) no NAS logs in ES, the alert below is the signal; (b) SSH + rsyslog forwarding, which is unsupported and typically wiped by firmware updates, so do not do it without an explicit decision.

---

## 5) Examples

```bash
# ES query (port-forward and curl in the SAME call)
kubectl port-forward -n monitoring svc/elasticsearch-es-http 9200:9200 &
curl -sk -u elastic:"$PW" -H 'content-type: application/json' \
  'https://localhost:9200/logs-generic-default/_search?size=5' \
  -d '{"query":{"bool":{"filter":[{"term":{"resource.attributes.service.name":"talos-machined"}},{"range":{"@timestamp":{"gte":"now-15m"}}}]}}}'

# Send a synthetic line (throwaway pod; token makes it findable)
kubectl -n monitoring run syslog-e2e --rm -i --restart=Never --image=busybox:1.38.0 --command -- \
  sh -c "echo '<14>test TOKEN' | nc -u -w1 192.168.55.19 5174"
# then wildcard on body.text: "*TOKEN*"
```

---

## 6) Verification Tests

| Test | Pass |
|------|------|
| `kubectl get svc -n monitoring edot-collector-syslog` | EXTERNAL-IP `192.168.55.19`, 3 UDP ports |
| Collector Ready, ES doc count `now-5m` rising before/after a roll | yes |
| Synthetic line per port | found in ES with the right `service.name` (measured 2026-11-25: all three within about 20 s) |
| After 4.2 per node: `service.name: talos-*` docs with `attributes.net.peer.ip` = node IP | yes, within a minute |
| `/api/v1/rules` lists `NasUnreachable`, `NasUnreachableCritical`, `NasUnreachableMonitorAbsent`, state inactive | yes |
| Replay `max_over_time(monitor_status{monitor_id="35",monitor_type="ping"}[1m]) == 0` over 2026-11-25 01:30-02:30Z | true at 01:48:30 and 01:49:00 only |

---

## 7) Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| No `talos-*` docs after 4.2 | sender stalled or wrong IP | `talosctl -n <node> get machineconfig v1alpha1 -o yaml` shows the destination; same url-toggle recipe as kmsg |
| kmsg silent on one node after a collector roll | known sender stall | url-toggle recipe in node-reboot-observability.md (operator) |
| UniFi/UNAS lines missing though configured | UDP from VLAN 30 blocked, or wrong port | `tcpdump`-free check: send a synthetic line from the sender's VLAN |
| `NasUnreachableMonitorAbsent` fires | Kuma monitor renamed/recreated (new id) or scrape gone | fix the monitor id in the rule file, check the Kuma ServiceMonitor |

---

## 8) Diagnose Examples

```bash
kubectl -n monitoring logs deploy/edot-collector --tail=100 | grep -i -E 'udp_log|error'
kubectl -n monitoring get endpoints edot-collector-syslog
# rule loaded?
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &
curl -s localhost:9090/api/v1/rules | python3 -c "import sys,json;[print(r['name'],r['state']) for g in json.load(sys.stdin)['data']['groups'] for r in g['rules'] if r['name'].startswith('NasUnreachable')]"
```

---

## 9) Health Check

`runbooks/health-check.sh` plus: collector Ready with 0 unexplained restarts, `TalosKernelLogsMissingFromNode` quiet, NasUnreachable* inactive.

---

## 10) Security Check

- Receivers accept unauthenticated UDP only from the sources allowed by `edot-collector-ingress` (nodes, UDM, UNAS) (see Ingress restriction); the LB IP is on the LAN-only VLAN 55 pool and is not published through any Gateway. A spoofed sender can inject log lines (log integrity is therefore advisory, not forensic).
- Talos service logs can contain operational detail; the stream stays inside the cluster ES.
- No credentials in any committed file; the collector password still comes from `elasticsearch-es-elastic-user`.

---

### Ingress restriction and queue isolation (2026-11-25)

- `edot-collector-ingress` (CiliumNetworkPolicy, `networkpolicy-syslog.yaml`): there is no default-deny anywhere else in the cluster, so selecting the collector makes ITS ingress default-deny. Allowed: `cluster` entity to TCP 4317/4318/8888/8889/13133; `host`/`remote-node` to UDP 5171/5173-5175; UDM address to 5174; UNAS address to 5175. Ordinary pods cannot reach 5173-5175. Validated live: from a normal pod 0 of 9 synthetic lines landed, from a hostNetwork pod 9 of 9; Talos senders and OTLP kept ingesting. UDM/UNAS CIDR rules are unproven until those senders exist (if SNATed to a node IP they still match the node rule).
- `elasticsearch/syslog` exporter with its own 512 MiB persistent queue serves the talos-service, unifi and unas pipelines (kernel feed unchanged). Queue budget total ~6.75 GiB of the 10 GiB PVC.

## 11) Rollback Plan

- Collector/alerts: `git revert <sha>` and push (Recreate roll, ~45 s; re-check kmsg senders).
- Talos service logs: remove `machine-service-logging.yaml` from `talconfig.yaml`, regenerate, `apply-config --mode=no-reboot` per node.
- UniFi/UNAS: set the previous target back (Wazuh `192.168.55.27:514` for UniFi).

---

## 12) References

- `docs/troubleshooting/node-reboot-observability.md` (kmsg design, sender stall)
- `docs/sops/monitoring.md`
- `docs/sops/storage-safety.md` (do not delete CIFS PVCs during a NAS outage)
- `kubernetes/apps/monitoring/kube-prometheus-stack/app/uptime-kuma-alerts.yaml` (generic Kuma alert, 2 m)

## Version History

| Version | Date | Change |
|---|---|---|
| 2026.11.25b | 2026-11-25 | Talos service logs applied; Wazuh/UniFi measurement; UNAS finding; ingress CNP; syslog exporter queue |
| 2026.11.25 | 2026-11-25 | Initial: collector receivers, Talos service-log patch (prepared), NAS alert, operator click-paths |
