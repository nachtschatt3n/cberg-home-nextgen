# Node-reboot observability — implementation plan (Tiers 1–3)

**Status:** Tier 1 DONE (live). **Tier 2 + 2d DONE (live, 2026-06-29)** — all 3
nodes ship kmsg to Elasticsearch, and `NodeKernelHardwareError` alerts on
mce/Hardware-Error/thermal kmsg lines. Tier 3 (serial/netconsole) remains. Talos
changes are applied out-of-band (talhelper + `talosctl`), not via Flux.

### Tier 2d — hardware-error alert (DONE)

edot-collector `count/hwerrors` connector taps the kmsg stream and emits
`talos_kernel_hardware_errors_total{net_peer_ip=...}` (regex
`mce:|machine check|hardware error|uncorrected|thermal throttl|critical temperature`)
via a `prometheus/hwerrors` exporter on :8889, scraped by the `hwmetrics`
ServiceMonitor endpoint. PrometheusRule `NodeKernelHardwareError`
(`increase(...[1h]) > 0`, critical, labelled by node) in node-hardware-alerts.yaml.
Verified end-to-end by transiently broadening the count regex to all-kmsg and
confirming the metric in Prometheus, then restoring. NOTE: the metric is
distroless-collector — verify via Prometheus, not `kubectl exec` (no shell/wget
in the image).

### kmsg-sender stall on collector restart (operational gotcha)

A Talos node's UDP kmsg sender can **stall after the collector pod restarts**
(connected-UDP socket pinned to the now-dead pod IP) — kmsg keeps appearing in
`talosctl dmesg` but stops reaching ES. Kick it WITHOUT a reboot via a
config-toggle once the collector is stable:
`talosctl -n <node> patch mc --patch '{apiVersion: v1alpha1, kind: KmsgLogConfig,
name: ship-kmsg-to-otel, url: udp://192.168.55.18:5172/}'` then patch back to
`5171`. (The toggle only takes once the collector is no longer churning.) So:
**minimize collector restarts**, and after an unavoidable one, spot-check
per-node kmsg counts in ES and toggle any node that went silent. Detecting a
silent node is a candidate for a future `absent`-style alert per node.

### Tier 2 — what was actually built + learnings (differs from the draft below)

- **UDP, not TCP.** Talos's kmsg sender does **not reconnect** after the sink
  closes — over TCP it wedges in `CLOSE_WAIT` and silently stops on any collector
  restart (and a wedged sender does NOT recover via config re-apply or even a
  forced URL-toggle — only a node reboot clears it). UDP is connectionless and
  survives collector restarts. KmsgLogConfig `url: udp://192.168.55.18:5171/`;
  collector `udplog/talos-kernel` receiver; LB service + container port are UDP.
- **Node attribution:** Talos kmsg carries no hostname. The `udplog` receiver
  has `add_attributes: true`, so each record gets `attributes.net.peer.ip` =
  the node (192.168.55.11/12/13). Query ES:
  `attributes.log_source:talos-kernel AND attributes.net.peer.ip:192.168.55.11`.
- **Index:** kmsg shares `logs-generic-default` (a dedicated
  `logs-talos.kernel-default` index was tried and reverted — no matching ES
  index template, so the data stream couldn't bootstrap).
- **applies with no reboot** via `talosctl apply-config` — confirmed. BUT the
  one node that went through the tcp→udp transition (nuc14-01) had a wedged
  sender and needed a graceful `talosctl reboot` to start shipping. A reboot of
  a node hosting many stateful DBs causes a multi-minute recovery (Longhorn RWO
  volumes reattach; delete the reboot's orphaned `Error`/`ContainerStatusUnknown`
  pods to release held volumes — `kubectl get pods -A | awk '$4=="Error"...'`).
- **Verify:** `attributes.facility:kern` lines (incl. boot sequence) confirm
  kernel-level capture; `facility:user` lines are Talos service logs also on kmsg.



## Why this exists

On **2026-06-29 04:00:58 UTC**, control-plane node **k8s-nuc14-01** rebooted with
no identifiable cause and surfaced only as a downstream `PaperclipPodNotReady`
page (the 04:00 backup-cleanup CronJob pod orphaned by the reboot). Post-mortem
ruled out — with evidence — thermal (CPU 55–68 °C vs 110 °C Tjmax), OOM (33 GB
free), load (~3/18 cores), ECC (EDAC counters 0), and **power** (the node's own
Shelly plug "Server 1" / 192.168.33.52 had 101 days uptime; mains 234 V steady).
The node logged normally until an abrupt cutoff at 04:00:37 then hard-reset —
signature of an internal kernel panic / hardware watchdog. **We could not name
the trigger because Talos kernel logs aren't shipped anywhere and dmesg wipes on
reboot.** This plan closes that gap.

Key Talos facts (verified against `siderolabs/pkgs` kernel config + issue #13192):
- On immutable Talos, **kdump, ramoops, rasdaemon, mcelog, and a custom
  node-exporter EDAC build all do NOT work** — do not attempt them.
- `machine.logging` ships **service** logs only (machined/apid/kubelet/etcd).
  **Kernel** logs (kmsg — where `mce:` / `Hardware Error` / panic lines appear)
  are a **separate** mechanism: the `KmsgLogConfig` document or the
  `talos.logging.kernel=` kernel arg.
- Kernel args (`install.extraKernelArgs`) apply **only on `talosctl upgrade`**,
  not on `apply-config`, and on v1.12+ are filtered/baked into the factory
  schematic (see `patches/global/machine-intelgpu.yaml`). `KmsgLogConfig`
  applies on a normal config apply with **no reboot** — prefer it.

---

## Tier 1 — node-level alerts (DONE, live)

`kubernetes/apps/monitoring/kube-prometheus-stack/app/node-hardware-alerts.yaml`
(commit on 2026-06-29). All metrics verified present on the NUC14 nodes; rules
live in Prometheus:

- `NodeUnexpectedReboot` (critical, offset-guarded) + `NodeRebootFlapping` (warning)
- `NodeCPUTemperatureHigh`/`Critical` (`node_thermal_zone_temp{type=x86_pkg_temp}`)
  + `NodeCPUThermalCritAlarm` (chip hardware alarm flag)
- `NodeMemoryECC{Correctable,Uncorrectable}Errors` (`node_edac_*` — works on our
  image) + `NodeEDACMetricsAbsent` guard

> Note: `node_edac_*` and `coretemp`/`x86_pkg_temp` are all already exported on
> our nodes — no Talos change was needed for Tier 1. (Stock Talos lacks EDAC; our
> factory image evidently includes it. The absent-guard alert tells us if that
> ever regresses.)

---

## Tier 2 — ship kernel logs off-box (HIGH ROI)

Goal: stream each node's kmsg (kernel ring buffer) to the existing
edot-collector → Elasticsearch, so MCE / `Hardware Error` / thermal / most panic
lines survive the reboot and are searchable.

### 2a. edot-collector — add a kernel-log TCP receiver

The collector is `otel/opentelemetry-collector-contrib:0.147.0` (contrib image →
`tcplog` receiver is compiled in). Diff to
`kubernetes/apps/monitoring/edot-collector/app/configmap.yaml`:

```yaml
    receivers:
      otlp:
        protocols:
          grpc: { endpoint: 0.0.0.0:4317 }
          http: { endpoint: 0.0.0.0:4318 }
      # NEW — Talos kmsg (json_lines over TCP)
      tcplog/talos-kernel:
        listen_address: "0.0.0.0:5171"
        operators:
          - type: json_parser
            parse_from: body
            parse_to: attributes
          - type: move
            from: attributes.msg
            to: body
        # adds resource attr so these are filterable in ES
        attributes:
          log_source: talos-kernel

    service:
      pipelines:
        logs:                       # existing OTLP app-log pipeline (unchanged)
          receivers: [otlp]
          processors: [memory_limiter, filter/drop-malformed-json-log-keys, batch]
          exporters: [elasticsearch/logs]
        logs/talos-kernel:          # NEW pipeline
          receivers: [tcplog/talos-kernel]
          processors: [memory_limiter, batch]
          exporters: [elasticsearch/logs]
```

Expose the port on the Deployment
(`kubernetes/apps/monitoring/edot-collector/app/deployment.yaml`, add to
`ports:`):

```yaml
            - { name: talos-kmsg, containerPort: 5171, protocol: TCP }
```

### 2b. Reachable endpoint for the nodes

Talos nodes (host net 192.168.55.11-13) must dial the collector at a stable IP.
Add a LoadBalancer service on VLAN 55 (Cilium LB pool — pick a free IP in
.14-.199/.211-.239; verify with `kubectl get svc -A | grep LoadBalancer`):

```yaml
---
apiVersion: v1
kind: Service
metadata:
  name: edot-collector-talos-kmsg
  namespace: monitoring
  annotations:
    lbipam.cilium.io/ips: "192.168.55.18"   # <-- pick & confirm free
spec:
  type: LoadBalancer
  selector: { app.kubernetes.io/name: edot-collector }   # match the Deployment's pod labels
  ports:
    - { name: talos-kmsg, port: 5171, targetPort: 5171, protocol: TCP }
```

### 2c. Talos — point kmsg at the collector (no reboot)

`KmsgLogConfig` is a separate machineconfig document. Apply via talhelper or
directly. Document:

```yaml
apiVersion: v1alpha1
kind: KmsgLogConfig
name: ship-kmsg-to-otel
url: tcp://192.168.55.18:5171/
```

**talhelper integration:** talhelper `patches:` strategic-merge into the
`v1alpha1.Config` document and do NOT append separate document kinds, so this
needs one of:
- (preferred) `talosctl apply-config --patch @kmsglog.yaml` per node after
  `talhelper genconfig` — but that drifts from git. OR
- add to talconfig via a mechanism that emits the extra doc (confirm current
  talhelper support for multi-doc output before relying on it). OR
- the kernel-arg form `machine.install.extraKernelArgs:
  [talos.logging.kernel=tcp://192.168.55.18:5171/]` baked into the **factory
  schematic** (these nodes already use a custom schematic) — applies on the next
  `talosctl upgrade` (Tier 3 reboots anyway, so this composes well).

Apply procedure (KmsgLogConfig, no reboot), one node at a time:
```bash
talhelper genconfig
talosctl -n 192.168.55.11 apply-config -f clusterconfig/<...>-k8s-nuc14-01.yaml
talosctl -n 192.168.55.11 dmesg --tail | head     # sanity
# repeat .12, .13
```

### 2d. Companion ES alert (MCE / hardware-error pattern)

Once kmsg flows to ES, add a detection rule (Kibana alert or a logs-pipeline
check) on `log_source: talos-kernel` matching `mce:` / `Machine check` /
`Hardware Error` / `Uncorrected error`. This is the durable MCE signal that
survives a reboot (complements the live `NodeMemoryECC*` Prometheus alerts).

### Risks / caveats
- `tcplog` is alpha stability in contrib — fine for diagnostics.
- No buffering: if the collector is down, kmsg lines are dropped. The collector
  is a single Deployment; if it lands on the rebooting node, that node's final
  lines may be lost. Consider 2 replicas / anti-affinity if this matters.
- Opening a plaintext TCP log port on a LB IP — VLAN 55 is the private cluster
  net; acceptable. Do not expose externally.

---

## Tier 3 — capture a hard reset (serial console / netconsole)

For a panic so fast nothing flushes over TCP, the only survivors are serial
console or netconsole. **NUC14 has no BMC/iLO**, so serial capture needs Intel
AMT/SOL (if provisioned) or a USB-serial harness — otherwise rely on netconsole
to the same collector host.

Kernel args (apply on `talosctl upgrade`, baked into the factory schematic since
v1.12 filters `extraKernelArgs`):
```
console=ttyS0,115200n8
panic=0                       # freeze instead of auto-reboot, so the panic is readable
netconsole=6666@192.168.55.11/eth0,514@192.168.55.18/<collector-mac>
```
`netconsole` needs the destination MAC; on a routed L2 it's the next-hop/gateway
MAC. Captures any panic that reaches printk (not instant MCE resets).

Procedure (reboots each node — do ONE at a time, wait for etcd quorum + Ready
between):
```bash
# update the factory schematic to add the kernel args, get new schematic id
talhelper genconfig
talosctl -n 192.168.55.11 upgrade --image factory.talos.dev/installer/<new-schematic-id>:v1.13.5
talosctl -n 192.168.55.11 health --wait-timeout 10m
kubectl get nodes ; flux get ks -A | grep -v True   # confirm green before next node
```

### Do NOT attempt on Talos (confirmed non-functional)
kdump/crashkernel · ramoops/pstore-RAM · rasdaemon · mcelog · custom
node-exporter EDAC collector. Reasons in the research (kernel config lacks
`KEXEC`, `PSTORE_RAM`, tracefs/writable-host requirements).

---

## Recommended rollout order
1. **Tier 1** — DONE.
2. **Tier 2a/2b** (collector receiver + LB svc) — GitOps, low risk, reversible.
3. **Tier 2c** (KmsgLogConfig) — out-of-band, no reboot. → biggest ROI.
4. **Tier 2d** (ES MCE alert).
5. **Tier 3** (serial/netconsole via schematic + rolling `talosctl upgrade`) —
   only if Tier 2 proves insufficient (i.e. a future reboot is still a hard reset
   that drops its kmsg before it ships).
