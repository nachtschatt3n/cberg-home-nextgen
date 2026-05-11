# Application Inventory

> Maintained manually. Update when deploying or removing applications.
> Run `python3 runbooks/doc-check.py` to detect apps missing from this inventory.
> For version status, see `runbooks/version-check-current.md`.

---

## Summary

| Namespace | App Count |
|-----------|-----------|
| ai | 10 |
| home-automation | 20 |
| databases | 10 |
| monitoring | 11 |
| office | 11 |
| media | 5 |
| download | 2 |
| kube-system | 12 |
| storage | 1 |
| cert-manager | 1 |
| network | 6 |
| default | 2 |
| flux-system | 1 |
| backup | 1 |
| my-software-development | 3 |
| my-software-production | 4 |
| **Total** | **~99** |

---

## AI (`ai`)

| App | Purpose | Ingress | Homepage Group |
|-----|---------|---------|---------------|
| open-webui | Chat interface for AI models (LLM frontend) | Internal | AI |
| librechat | Multi-provider AI chat interface (Ollama via Mac Mini) | External | AI |
| langfuse | LLM observability, tracing, and analytics | Internal | AI |
| openclaw | AI agent platform | Internal | AI |
| anythingllm | Private RAG workspace with local AI | Internal | AI |
| mcpo | Model Control Plane Orchestrator | Internal | AI |
| ai-sre | AI-powered SRE tooling | Internal | AI |
| next-ai-draw-io | AI-assisted diagram editor (natural language → diagrams) | Internal | AI |
| paperclip | AI agent orchestration — multi-agent company management | Internal | AI |
| hermes-agent | Self-improving AI agent with Telegram gateway and skill learning | Internal | AI |

**External Ollama:** Mac Mini M4 Pro at `192.168.30.111` (not deployed in cluster)

---

## Home Automation (`home-automation`)

| App | Purpose | Ingress | Homepage Group |
|-----|---------|---------|---------------|
| home-assistant | Central home automation platform | Internal | Home Automation |
| esphome | ESP32/ESP8266 device management | Internal | Home Automation |
| node-red | Flow-based automation and integrations | Internal | Home Automation |
| frigate-nvr | AI-powered network video recorder (Intel NPU / OpenVINO) | Internal | Home Automation |
| scrypted-nvr | Additional video management platform | Internal | Home Automation |
| solarfocus-scraper | Solarfocus pellet^top heater scraper (VNC + OCR → MQTT with HA auto-discovery) — source: [github.com/nachtschatt3n/solarfocus-scraper](https://github.com/nachtschatt3n/solarfocus-scraper) | External (Authentik forward-auth, status UI) | Home Automation |
| pallet-price-monitor | Twice-daily ETL of German wood-pellet prices (PLZ 65520 / 6 t loose ENplus A1) plus leading indicators (Destatis EPI, Eurostat trade, DWD HDD), news (agrarheute, Holzkurier, DEPV), substitute fuels (Heizöl), and step-change events (Toll Collect). Computes a weighted spot+structural buy/wait verdict, persists in shared Postgres, surfaces via Grafana + Superset, alerts via AlertManager Telegram on BUY. Source: [github.com/nachtschatt3n/pellet-price-monitor](https://github.com/nachtschatt3n/pellet-price-monitor) (private). | Internal (CronJob, no UI) | Home Automation |
| zigbee2mqtt | Zigbee device integration via MQTT | Internal | Home Automation |
| mosquitto | MQTT broker for IoT communications | Internal (cluster) | — |
| music-assistant-server | Multi-room audio management | Internal | Home Automation |
| iobroker | IoT integration platform | Internal | Home Automation |
| n8n | Workflow automation | Internal | Home Automation |
| teslamate | Tesla data logger and analytics | Internal | Home Automation |
| mqttx-web | Web-based MQTT client | Internal | Home Automation |
| matter-server | Matter and Thread protocol server | Internal (cluster) | — |
| otbr | OpenThread Border Router (Matter/Thread) — re-enabled 2026-04-30 with Talos v1.13.0 (kernel 6.18.24 has `CONFIG_IPV6_MROUTE=y`) | Internal (cluster) | — |
| traccar | GPS/location tracking server | Internal | Home Automation |
| trmnl-ha | TRMNL e-ink display integration for Home Assistant | Internal (cluster) | — |
| ha-ai-harness | AI assistant server for Home Assistant (FastAPI + Vue dashboard, dual-model Ollama) | Internal (`ha-harness.${SECRET_DOMAIN}`) | Home Automation |
| zero-export-controller | Balcony PV zero-export controller (Tibber Pulse + OpenDTU via HA REST → per-inverter `number.set_value`) — holds grid at −50 W, caps summed feed at 800 W (Bagatellgrenze), live-tunable via HA helpers, killed by `input_boolean.solar_zero_export_enabled`. Source: [github.com/nachtschatt3n/tibber-openDTU-home-assitant-solar-monitor](https://github.com/nachtschatt3n/tibber-openDTU-home-assitant-solar-monitor) | Internal (cluster, /metrics ServiceMonitor) | — |

---

## Databases (`databases`)

| App | Purpose | Ingress | Homepage Group |
|-----|---------|---------|---------------|
| postgresql | PostgreSQL database (shared cluster DB) | None | Databases |
| mariadb | MariaDB database (shared cluster DB) | None | Databases |
| redis | Redis in-memory cache/queue | None | Databases |
| influxdb | InfluxDB time-series database | None | Databases |
| nocodb | NocoDB — open-source Airtable alternative | Internal | Databases |
| phpmyadmin | phpMyAdmin — MySQL/MariaDB admin UI | Internal | Databases |
| pgadmin | pgAdmin — PostgreSQL admin UI | Internal | Databases |
| redisinsight | RedisInsight — Redis GUI | Internal | Databases |
| memgraph | Memgraph — in-memory graph database (Cypher/Bolt) with Lab web UI | Internal | Databases |
| superset | Apache Superset — data exploration and visualization (bundled PG + Redis) | Internal | Databases |

---

## Monitoring (`monitoring`)

| App | Purpose | Ingress | Homepage Group |
|-----|---------|---------|---------------|
| kube-prometheus-stack | Prometheus + Alertmanager + rules | Internal | Monitoring |
| grafana | Dashboards and data visualization | Internal | Monitoring |
| uptime-kuma | Service monitoring and status pages | Internal | Monitoring |
| headlamp | Kubernetes web UI | Internal | Monitoring |
| eck-operator | Elastic Cloud on Kubernetes operator | None | — |
| elasticsearch | Elasticsearch cluster (via ECK) | Internal | Monitoring |
| elasticsearch-bootstrap | Initial ES index/ILM configuration Job (within `elasticsearch/` dir, no standalone directory) | None | — |
| edot-collector | Log collection and forwarding to Elasticsearch (EDOT) | None | — |
| otel-operator | OpenTelemetry Operator for collector management | None | — |
| kibana | Kibana log analytics UI | Internal | Monitoring |
| unpoller | UniFi metrics exporter for Prometheus | None | — |

---

## Office (`office`)

| App | Purpose | Ingress | Homepage Group |
|-----|---------|---------|---------------|
| affine | Collaborative knowledge base and workspace | Internal | Office |
| nextcloud | Self-hosted cloud storage + collaboration | Internal + External | Office |
| paperless-ngx | Document management with OCR | Internal | Office |
| paperless-ai | AI document classification (Ollama backend) | None | — |
| paperless-gpt | AI tagging/summarization for Paperless | None | — |
| vaultwarden | Bitwarden-compatible password manager | Internal + External | Office |
| actual-budget | Personal finance management (budgeting, envelope method) | Internal | Office |
| sure | Personal finance (accounts, budgets, investments, AI assistant) | Internal | Office |
| penpot | Design and prototyping platform | Internal | Office |
| omni-tools | Productivity utilities collection | Internal | Office |
| nextcloud-mcp | MCP server bridge for Nextcloud AI integration | Internal | Office |

---

## Media (`media`)

| App | Purpose | Ingress | Homepage Group |
|-----|---------|---------|---------------|
| jellyfin | Open-source media server | Internal | Media |
| plex | Plex media server | Internal | Media |
| makemkv | Blu-ray/DVD ripping utility | Internal | Media |
| library-tools | Audit + organize + sidecar + rescan + cleanup + per-item-refresh + plex-fs-classifier CronJobs for the shared media library; ConfigMap-of-Python pattern. Owned by the `media-manager` sub-agent; standard in `docs/sops/media-library-standards.md`. | None | — |
| media-dashboard | Internal status dashboard with live intake queue + recent jobs + trigger buttons (audit, rescan, TA bridge). Part of `library-tools`. | Internal | Media |

---

## Download (`download`)

| App | Purpose | Ingress | Homepage Group |
|-----|---------|---------|---------------|
| tube-archivist | YouTube content archival and management. Hourly NFO + image sync CronJobs write Kodi-style sidecars next to each video; Jellyfin scans this tree directly. Plex is intentionally not configured for YouTube. | Internal | Download |
| jdownloader | Download manager. Intake source for the `media-manager` sub-agent. | Internal | Download |

---

## System / kube-system (`kube-system`)

| App | Purpose | Ingress | Homepage Group |
|-----|---------|---------|---------------|
| authentik | Identity provider + forward auth proxy | Internal + External | System |
| cilium | eBPF CNI, load balancing, network policies | None | — |
| coredns | Cluster-internal DNS resolution | None | — |
| csi-driver-smb | SMB/CIFS storage integration (NAS) | None | — |
| descheduler | Pod descheduler for resource optimization | None | — |
| intel-device-plugin | Intel device plugin operator (manages GPU + NPU sub-charts) | None | — |
| intel-device-plugin-gpu | Intel GPU device plugin — exposes `gpu.intel.com/i915` to pods (Jellyfin, Plex, Frigate, Scrypted, MakeMKV) | None | — |
| intel-device-plugin-npu | Intel NPU/VPU device plugin — exposes `npu.intel.com/accel` to pods (Meteor Lake VPU 8086:7d1d, added 2026-04-30 with Talos v1.13.0) | None | — |
| metrics-server | Kubernetes resource usage metrics API | None | — |
| node-feature-discovery | Hardware feature detection and labeling | None | — |
| reloader | Automatic pod restart on ConfigMap/Secret changes | None | — |
| spegel | Distributed container image caching (P2P mirror) | None | — |

---

## Storage (`storage`)

| App | Purpose | Ingress | Homepage Group |
|-----|---------|---------|---------------|
| longhorn | Distributed block storage with replication + backups | Internal | System |

---

## Certificate Management (`cert-manager`)

| App | Purpose | Ingress | Homepage Group |
|-----|---------|---------|---------------|
| cert-manager | TLS certificate management via Let's Encrypt | None | — |

---

## Network (`network`)

| App | Sub-path | Purpose | Ingress |
|-----|---------|---------|---------|
| ingress-nginx (internal) | `network/internal/` | Internal reverse proxy | — (is the ingress) |
| ingress-nginx (external) | `network/external/` | External reverse proxy | — (is the ingress) |
| adguard-home | `network/internal/` | DNS + ad blocking (IP: 192.168.55.5) | Internal |
| k8s-gateway | `network/internal/` | Internal service DNS (IP: 192.168.55.101) | None |
| cloudflared | `network/external/` | Cloudflare Tunnel client | None |
| external-dns | `network/external/` | Automated Cloudflare DNS record management | None |

---

## Default (`default`)

| App | Purpose | Ingress | Homepage Group |
|-----|---------|---------|---------------|
| homepage | Dashboard with Kubernetes service auto-discovery | Internal | — |
| echo-server | HTTP echo server for testing | Internal | — |

---

## Flux (`flux-system`)

| App | Purpose | Ingress | Homepage Group |
|-----|---------|---------|---------------|
| flux-operator | Flux GitOps operator + webhook receiver | Internal (webhook) | — |

---

## Security (`security`)

| App | Purpose | Ingress | Homepage Group |
|-----|---------|---------|---------------|
| wazuh-indexer | Single-node OpenSearch-based event store for Wazuh SIEM (10Gi, longhorn). ES7 compat enabled for Filebeat 7.10.2 | None | — |
| wazuh-manager-master | Single-node Wazuh Manager — agent enrollment (1515), comms (1514), REST API (55000), UniFi syslog/CEF (UDP 514, LB IP 192.168.55.27). 10Gi (live: 20Gi) single PVC with subPath layout. Cluster mode disabled. Custom decoder sets mounted at `etc/decoders/{unifi,ingress-nginx}` + matching `etc/rules/` dirs (each path listed explicitly in `ossec.conf` — `<decoder_dir>` is non-recursive); ingress-nginx decoder lifts `cf_connecting_ip` from CRI-wrapped JSON for true-source-IP correlation, uses the bare reserved `<status>` match element (not `<field name="status">`, which crashes analysisd at startup with "Field 'status' is static"). Runbook: [wazuh-unifi-syslog.md](../runbooks/wazuh-unifi-syslog.md) | None | — |
| wazuh-dashboard | Wazuh SIEM web UI (4.14.5). API connection pre-registered via mounted wazuh.yml (`run_as: false`) | Internal + Authentik SAML SSO | Security |
| wazuh-agent | DaemonSet — one privileged Wazuh agent per cluster node, enrolled with stable identity `k8s-nuc14-{01,02,03}` (pinned via `WAZUH_AGENT_NAME=$(NODE_NAME)` so DaemonSet rollouts don't create zombie agent IDs; manager `<auth><purge>yes</purge>` reuses the same ID on re-enrollment). Collects FIM (rootcheck on `/etc /usr/bin /usr/sbin /bin /sbin /boot`), Talos node logs (kubelet, kernel, machined, containerd, cri), Kubernetes pod stdout via `/host/var/log/containers/*.log` (every CRI log on the node, except `wazuh-*` and `longhorn-manager-*` to avoid feedback loops), and Falco syscall events from `/var/run/falco/falco.log`. 4.14.5, AR-023 + AR-025. | None | — |
| falco | DaemonSet — runtime syscall monitoring on every node via modern_ebpf driver (Talos kernel ≥5.8, no kmod build). JSON-formatted events written to `/var/run/falco/falco.log` and tailed by wazuh-agent. Wazuh rules `100400-100404` map Falco priorities to alert levels; rules `100410` (suppress wazuh-* daemon FIM-cycle reads), `100411` (suppress cilium-cni plugin invocations) and `100412` (suppress postgres pg_isready liveness probes — perl wrapper reads /etc/shadow) silence the dominant false-positive families. Chart `falcosecurity/falco@8.0.3`, AR-026. | None | — |

---

## Backup (`backup`)

| App | Purpose | Ingress | Homepage Group |
|-----|---------|---------|---------------|
| icloud-docker-mu | Apple iCloud Drive sync | None | — |

---

## Custom Development

### `my-software-development`

| App | Purpose | Ingress |
|-----|---------|---------|
| absenty | Absence/time tracking app (dev) | Internal |
| andreamosteller | Portfolio site (dev) | Internal |
| opencode-andreamosteller | OpenCode instance for Andrea's project | Internal |

### `my-software-production`

| App | Purpose | Ingress |
|-----|---------|---------|
| absenty | Absence/time tracking app (production) | External |
| andreamosteller | Portfolio site (production) | External |
| gas-price-monitor | German fuel-price dashboard backed by the [Tankerkönig](https://creativecommons.tankerkoenig.de/) API; Bun + TypeScript, ephemeral cache + history (`emptyDir`), single-replica fair-use cap. Source: [github.com/nachtschatt3n/gas-price-monitor](https://github.com/nachtschatt3n/gas-price-monitor) (public). First-deploy is intentionally keyless (`/api/stations` 500s until the Tankerkönig key is wired in via SOPS). | Internal |
| rainbow-rescue | Offline-capable PWA voice controller for kids party hunt | Internal |

---

## Deployment Checklist for New Apps

When deploying a new application:

- [ ] Create `kubernetes/apps/{namespace}/{app}/` directory structure
- [ ] Add `helmrelease.yaml` with chart reference and values
- [ ] Add `kustomization.yaml` for Flux
- [ ] Create `secret.sops.yaml` for any credentials (SOPS-encrypted)
- [ ] Add Homepage annotations to ingress (see `docs/sops/homepage-integration.md`)
- [ ] Add Authentik forward auth if externally exposed (see `docs/sops/authentik.md`)
- [ ] Update this file (`docs/applications.md`) with the new app
- [ ] Run `python3 runbooks/doc-check.py` to verify documentation is complete
