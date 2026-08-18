# Application Inventory

> Maintained manually. Update when deploying or removing applications.
> Run `python3 runbooks/doc-check.py` to detect apps missing from this inventory.
> For version status, see `runbooks/version-check-current.md`.

---

## Summary

| Namespace | App Count |
|-----------|-----------|
| ai | 9 |
| home-automation | 20 |
| databases | 11 |
| monitoring | 13 |
| office | 12 |
| media | 5 |
| download | 2 |
| kube-system | 11 |
| storage | 1 |
| cert-manager | 1 |
| network | 8 |
| default | 2 |
| flux-system | 1 |
| backup | 2 |
| security | 2 |
| my-software-development | 3 |
| my-software-production | 4 |
| my-software-showcase | 15 |
| **Total** | **122** |

---

## AI (`ai`)

| App | Purpose | Ingress | Homepage Group |
|-----|---------|---------|---------------|
| open-webui | Chat interface for AI models (LLM frontend) | Internal | AI |
| librechat | Multi-provider AI chat interface (Ollama via Mac Mini). Authentik OIDC SSO — local registration stays disabled; users are auto-provisioned on first OIDC login | External | AI |
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
| music-assistant-server | Multi-room audio management + Alexa skill bridge (alexa-skill sidecar, digest-pinned) | Internal UI; External `music-api`/`music-stream` (Alexa endpoints via Cloudflare) | Home Automation |
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
| mariadb | MariaDB database (shared cluster DB). Server 13.0.1 on chart 27.0.1. The image is pinned **by digest** (Bitnami's free tier publishes no versioned tags) — the `image.tag` field is inert, so never read a version off it; see `docs/sops/mariadb-major-upgrade.md` before any major bump. | None | Databases |
| redis | Redis in-memory cache/queue | None | Databases |
| influxdb | InfluxDB time-series database | None | Databases |
| nocodb | NocoDB — open-source Airtable alternative | Internal | Databases |
| phpmyadmin | phpMyAdmin — MySQL/MariaDB admin UI | Internal | Databases |
| pgadmin | pgAdmin — PostgreSQL admin UI | Internal | Databases |
| redisinsight | RedisInsight — Redis GUI | Internal | Databases |
| memgraph | Memgraph — in-memory graph database (Cypher/Bolt) with Lab web UI | Internal | Databases |
| superset | Apache Superset — data exploration and visualization (metadata DB still on the bundled bitnamilegacy PG; replacement `superset-pg` Deployment — official `postgres:17.11-alpine`, longhorn-static volume `superset-pg-data` — stood up alongside 2026-08-18, cutover pending per plan `superset-pg-cutover`; cache/broker on the standalone `superset-redis-official` Deployment — official `redis:8.10.0-alpine`, bundled bitnamilegacy Redis retired 2026-08-17) | Internal | Databases |
| sweep-history | Postgres holding the operator-curated policy tables (`accepted_risks`, `slo_definitions`, `noise_suppressions`, `security_acceptances`) plus sweep findings/cycles. Edited via `runbooks/policy-cli.py`. | None | Databases |

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
| prometheus-pushgateway | Push endpoint for metrics from short-lived jobs (CronJobs/scripts) that cannot be scraped. | None | Monitoring |
| prometheus-blackbox-exporter | Synthetic DNS + HTTPS probes (chart 11.17.2 / blackbox v0.28.0, prometheus-community OCI). 4 `Probe` CRs: 2 answer-validating DNS probes against k8s-gateway 192.168.55.101, 2 HTTPS probes (one representative host per ingress class). Emits `probe_success` — the SLI behind the `internal-dns-resolution` and `internal-ingress-availability` SLOs. Alerts in `kube-prometheus-stack/app/blackbox-exporter-alerts.yaml`. | None | — |
| sweep-dashboard | Web UI over the sweep_history DB — browse operator policy (`/policies/`) and sweep findings. JSON API at `/api/policies/{accepted-risks,slos,noise,security}`. | External | Monitoring |

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
| sure | Personal finance (accounts, budgets, investments, Contracts tracking w/ AI-enrichment, AI assistant) | Internal | Office |
| penpot | Design and prototyping platform | Internal | Office |
| omni-tools | Productivity utilities collection | Internal | Office |
| nextcloud-mcp | MCP server bridge for Nextcloud AI integration | Internal | Office |
| arag-web | ARAG health insurance data visualiser (Rails 8.1, SQLite, Solid Queue via Thruster) | Internal | Office |

> **Shared Sure API key — rotate in two places.** `openclaw` and `arag-web` both
> authenticate to `sure` with the **same** Sure API key (sent via the `X-Api-Key`
> header), stored in two SOPS secrets: `openclaw-secret` key `SURE_TOKEN` (`ai`
> namespace, used by the openclaw `sure` skill) and `arag-web-secret` key
> `SURE_API_KEY` (`office` namespace, used by arag-web's `SureSyncJob`). When the
> Sure key is rotated, **update both secrets together** — a stale key fails closed
> with a silent `401 unauthorized` on whichever consumer wasn't updated (this is
> exactly how the openclaw skill broke: its copy of the key was stale while
> arag-web's was current).

---

## Media (`media`)

| App | Purpose | Ingress | Homepage Group |
|-----|---------|---------|---------------|
| immich | Self-hosted photo and video library — read-only external-library viewer over the NAS iCloud backup, Intel iGPU ML, Authentik OIDC SSO. See `docs/sops/immich.md`. | Internal | Media |
| jellyfin | Open-source media server | Internal | Media |
| plex | Plex media server | Internal | Media |
| makemkv | Blu-ray/DVD ripping utility | Internal | Media |
| library-tools | Audit + organize + sidecar + episode-sidecar + rescan + cleanup + per-item-refresh + plex-fs-classifier CronJobs for the shared media library; ConfigMap-of-Python pattern. All are suspended and invoked on demand. `media-episode-sidecar` (`episode_sidecar.py`, added 2026-08-15) writes per-EPISODE `.nfo` for one show, dry-run by default and never deletes — it is **not** `media-sidecar`, which unlinks every `.nfo` in its target folder first. Owned by the `media-manager` sub-agent; standard in `docs/sops/media-library-standards.md`. | None | — |
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
| crash-ghost-reaper | CronJob (every 15m) clearing 'ghost' pods left behind by node-loss events, so stale objects do not mask real failures. See `docs/sops/crash-ghost-reaper.md`. | None | None |

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
| k8s-gateway | `network/internal/` | Internal service DNS (IP: 192.168.55.101). Chart 3.7.2 / app 1.8.0 — upstream moved orgs (ori-edge → k8s-gateway); the old repo is frozen at chart 2.4.0 / app 0.4.0, which fails closed when Gateway API CRDs are present. Image tag is pinned in the HR because the chart default lags. See `docs/sops/k8s-gateway-dns.md`. | None |
| cloudflared | `network/external/` | Cloudflare Tunnel client | None |
| external-dns | `network/external/` | Automated Cloudflare DNS record management | None |
| envoy-gateway | `network/envoy-gateway/` | Envoy Gateway (chart `gateway-helm` 1.9.0) — Gateway API control plane for the ingress-nginx replacement. Phase 0 + 0.5: `GatewayClass` + two Gateways, `envoy-internal` (192.168.55.103) and `envoy-external` (192.168.55.104), running alongside ingress-nginx with no app traffic yet. Gateway API + EG CRDs are vendored under `crds/` (standard channel) — gateway-api v1.6.1, 10 standard-channel CRDs — not chart-installed. See `docs/troubleshooting/ingress-migration-plan.md` and `docs/sops/k8s-gateway-dns.md` §8. | None |

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
| icloud-docker-andrea | Apple iCloud Drive + Photos sync for the second household Apple ID. Same `main` build digest pin as `icloud-docker-mu` — **bump both together** or the un-bumped one silently loses the iOS 26.4+ 2FA push. Data on `cifs-icloud-docker-andrea` (`icloud-backup/andrea`), session PVC on dynamic `longhorn`. | None | — |
| icloud-docker-mu | Apple iCloud Drive sync. Image pinned to a `main` build digest (not a release tag) to get icloudpy 0.9.0's iOS 26.4+ 2FA push trigger — deliberate exception, see `docs/sops/icloud-docker-reauth.md`. | None | — |

One instance per Apple ID; they share nothing but the `csi-driver-smb` credential
and the image digest. Coverage of non-Drive/Photos iCloud data (contacts,
calendars, mail, Health) is tracked in `kubernetes/apps/backup/TODO.md`.

---

## Custom Development

### `my-software-development`

| App | Purpose | Ingress |
|-----|---------|---------|
| absenty | Absence/time tracking app (dev). **Internet-facing, and unauthenticated** — unlike every other app in this namespace it uses `className: external` with no Authentik forward-auth, so the development environment is reachable from the internet exactly like production. Flux image automation is armed here, so a push to the `development` branch auto-deploys to that public endpoint. | External |
| andreamosteller | Portfolio site (dev) | Internal |
| opencode-andreamosteller | OpenCode instance for Andrea's project | Internal |

### `my-software-production`

| App | Purpose | Ingress |
|-----|---------|---------|
| absenty | Absence/time tracking app (production) | External |
| andreamosteller | Portfolio site (production) | External |
| gas-price-monitor | German fuel-price dashboard backed by the [Tankerkönig](https://creativecommons.tankerkoenig.de/) API; Bun + TypeScript, ephemeral cache + history (`emptyDir`), single-replica fair-use cap. Geocoding via komoot Photon (requires `PHOTON_USER_AGENT` env at boot). Source: [github.com/nachtschatt3n/gas-price-monitor](https://github.com/nachtschatt3n/gas-price-monitor) (public). Currently using the public Tankerkönig demo key (fixed example payloads, not real prices) wired via SOPS-encrypted Secret — rotate by editing `kubernetes/apps/my-software-production/gas-price-monitor/app/secret.sops.yaml` in place. Public exposure approved by owner on 2026-05-12 (recorded override of source-repo Architecture Decision #3); no auth, no rate-limiting — accepted risks tracked in the source repo's `CLAUDE.md`. | External |
| rainbow-rescue | Offline-capable PWA voice controller for kids party hunt | Internal |

### `my-software-showcase`

Portfolio showcase of 15 containerized legacy client apps (TYPO3 4.2/6.2, Rails, PHP era), all on bjw-s app-template 5.1.0, deployed 2026-08-18. Databases live on the shared `databases/mariadb` (legacy-compat `sql_mode=NO_ENGINE_SUBSTITUTION` + `init_connect SET NAMES utf8` persisted in its HR for these tenants). **No outbound integrations by design** (no SMTP/Sentry/Twilio etc. — see `kubernetes/apps/my-software-showcase/README.md`). Homepage group "Software Portfolio".

| App | Purpose | Ingress |
|-----|---------|---------|
| globalmobility | globalDISPO dispatch system (TYPO3 4.2) | Internal |
| haarfabrik | Salon extranet | Internal |
| holm-backend | Holm backend service | Internal |
| ibgastro | Gastronomy ordering system | Internal |
| inbewegung | Family Manager | Internal |
| kfa-medienarchiv | Media Archive Management System | Internal |
| mangold-smarthomeadvisor | Smart Home Advisory System | Internal |
| max-jung | Vehicle fleet controlling | Internal |
| metaldyne | Metaldyne Mini ERP | Internal |
| ordiga | Ordiga order management | Internal |
| see-edv-ibspm | IBSPM service management | Internal |
| stepbystepguide | Step-by-step guide | Internal |
| u-zeit | U-Zeit time management | Internal |
| uzeit-de | Uzeit corporate website (TYPO3 6.2) | Internal |
| zuhause-betreut | Caretaker Management System ("Zuhause Betreut") — Rails app, `/health/{liveness,readiness,startup}` probes, Flux image automation on the `production-*` tag, 5Gi Longhorn RWO PVC (`strategy: Recreate`) | Internal |

---

## Deployment Checklist for New Apps

When deploying a new application:

- [ ] Create `kubernetes/apps/{namespace}/{app}/` directory structure
- [ ] Add `helmrelease.yaml` with chart reference and values
- [ ] Add `kustomization.yaml` for Flux
- [ ] Create `secret.sops.yaml` for any credentials (SOPS-encrypted)
- [ ] Add Homepage annotations to ingress (see `docs/sops/homepage-integration.md`)
- [ ] Add Authentik integration if externally exposed — forward-auth, or OIDC/SAML if the app has its own user model (see `docs/sops/authentik.md`)
- [ ] Update this file (`docs/applications.md`) with the new app
- [ ] Run `python3 runbooks/doc-check.py` to verify documentation is complete
