# Application Inventory

> Maintained manually. Update when deploying or removing applications.
> Run `python3 runbooks/doc-check.py` to detect apps missing from this inventory.
> For version status, see `runbooks/version-check-current.md`.

---

## Summary

| Namespace | App Count |
|-----------|-----------|
| ai | 5 |
| home-automation | 14 |
| databases | 8 |
| monitoring | 11 |
| office | 8 |
| media | 3 |
| download | 2 |
| kube-system | 10 |
| storage | 1 |
| cert-manager | 1 |
| network | 6 |
| default | 2 |
| flux-system | 1 |
| backup | 1 |
| my-software-development | 3 |
| my-software-production | 2 |
| **Total** | **~78** |

---

## AI (`ai`)

| App | Purpose | Ingress | Homepage Group |
|-----|---------|---------|---------------|
| open-webui | Chat interface for AI models (LLM frontend) | Internal | AI |
| langfuse | LLM observability, tracing, and analytics | Internal | AI |
| openclaw | AI agent platform | Internal | AI |
| mcpo | Model Control Plane Orchestrator | Internal | AI |
| ai-sre | AI-powered SRE tooling | Internal | AI |

**External Ollama:** Mac Mini M4 Pro at `192.168.30.111` (not deployed in cluster)

---

## Home Automation (`home-automation`)

| App | Purpose | Ingress | Homepage Group |
|-----|---------|---------|---------------|
| home-assistant | Central home automation platform | Internal | Home Automation |
| esphome | ESP32/ESP8266 device management | Internal | Home Automation |
| node-red | Flow-based automation and integrations | Internal | Home Automation |
| frigate-nvr | AI-powered network video recorder (Coral TPU) | Internal | Home Automation |
| scrypted-nvr | Additional video management platform | Internal | Home Automation |
| zigbee2mqtt | Zigbee device integration via MQTT | Internal | Home Automation |
| mosquitto | MQTT broker for IoT communications | Internal (cluster) | — |
| music-assistant-server | Multi-room audio management | Internal | Home Automation |
| iobroker | IoT integration platform | Internal | Home Automation |
| n8n | Workflow automation | Internal | Home Automation |
| teslamate | Tesla data logger and analytics | Internal | Home Automation |
| mqttx-web | Web-based MQTT client | Internal | Home Automation |
| matter-server | Matter and Thread protocol server | Internal (cluster) | — |
| otbr | OpenThread Border Router (Matter/Thread) | Internal (cluster) | — |

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
| elasticsearch-bootstrap | Initial ES index/ILM configuration job | None | — |
| elasticsearch-exporter | Prometheus exporter for ES metrics | None | — |
| fluent-bit | Log shipping from cluster to Elasticsearch | None | — |
| kibana | Kibana log analytics UI | Internal | Monitoring |
| unpoller | UniFi metrics exporter for Prometheus | None | — |

---

## Office (`office`)

| App | Purpose | Ingress | Homepage Group |
|-----|---------|---------|---------------|
| nextcloud | Self-hosted cloud storage + collaboration | Internal + External | Office |
| paperless-ngx | Document management with OCR | Internal | Office |
| paperless-ai | AI document classification (Ollama backend) | None | — |
| paperless-gpt | AI tagging/summarization for Paperless | None | — |
| vaultwarden | Bitwarden-compatible password manager | Internal + External | Office |
| actual-budget | Personal finance management | Internal | Office |
| penpot | Design and prototyping platform | Internal | Office |
| omni-tools | Productivity utilities collection | Internal | Office |

---

## Media (`media`)

| App | Purpose | Ingress | Homepage Group |
|-----|---------|---------|---------------|
| jellyfin | Open-source media server | Internal | Media |
| plex | Plex media server | Internal | Media |
| makemkv | Blu-ray/DVD ripping utility | Internal | Media |

---

## Download (`download`)

| App | Purpose | Ingress | Homepage Group |
|-----|---------|---------|---------------|
| tube-archivist | YouTube content archival and management | Internal | Download |
| jdownloader | Download manager | Internal | Download |

---

## System / kube-system (`kube-system`)

| App | Purpose | Ingress | Homepage Group |
|-----|---------|---------|---------------|
| authentik | Identity provider + forward auth proxy | Internal + External | System |
| cilium | eBPF CNI, load balancing, network policies | None | — |
| coredns | Cluster-internal DNS resolution | None | — |
| csi-driver-smb | SMB/CIFS storage integration (NAS) | None | — |
| descheduler | Pod descheduler for resource optimization | None | — |
| intel-device-plugin | Intel GPU acceleration support | None | — |
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
