# Kubernetes Deployment Version Status

**Generated:** 2026-01-18 23:45:50

> **Note:** Release notes are fetched from GitHub API. If rate limited, some release notes may not be available. Check source links for full details.

## Summary

- **Total Deployments:** 63
- **Chart Updates Available:** 6
- **Image Updates Available:** 4
- **Update Breakdown:** 🔴 4 major | 🟡 5 minor | 🟢 0 patch
- **⚠️ Breaking Changes Detected:** 4 updates with potential breaking changes

---

## Recommended Next Steps

### ✅ Option 1: Safe Minor Chart Updates (Recommended First)
These are low-risk minor version updates for charts where images are already up-to-date:

1. **jellyfin** (media)
   - Chart: `2.1.0 → 2.7.0` 🟡 MINOR
   - Image already updated: `10.11.5` ✅
   - Risk: Low (minor version, image already tested)

2. **uptime-kuma** (monitoring)
   - Chart: `2.18.0 → 2.24.0` 🟡 MINOR
   - Image already updated: `2.0.2` ✅
   - Risk: Low (minor version, image already tested)

3. **adguard-home** (network)
   - Chart: `0.19.0 → 0.24.0` 🟡 MINOR
   - Image already updated: `v0.107.71` ✅
   - Risk: Low (minor version, image already tested)

4. **paperless-ngx** (office)
   - Chart: `0.19.1 → 0.24.1` 🟡 MINOR
   - Risk: Medium (review release notes for breaking changes)

### ✅ Option 2: Safe Minor Image Update
1. **nextcloud-exporter** (default/nextcloud)
   - Image: `0.6.2 → 0.9.0` 🟡 MINOR
   - Risk: Low (minor version update, separate exporter component)

### ⚠️ Option 3: Major Updates (Investigate First)
These require careful review of breaking changes before proceeding:

1. **n8n** (home-automation)
   - Image: `1.123.16 → 2.4.4` 🔴 MAJOR
   - Risk: High (major version jump, workflow automation tool)
   - Action: Review n8n v2 migration guide and breaking changes

2. **jdownloader** (default)
   - Image: `v25.02.1 → v26.01.1` 🔴 MAJOR
   - Risk: High (major version jump)
   - Action: Review release notes for breaking changes

3. **nextcloud** (default)
   - Chart: `6.6.4 → 8.8.1` 🔴 MAJOR
   - Risk: High (major version jump, critical application)
   - Action: Review NextCloud 8.x migration guide and breaking changes

4. **eck-operator** (monitoring)
   - Chart: `2.14.0 → 3.2.0` 🔴 MAJOR
   - Risk: High (major version jump, Elasticsearch operator)
   - Action: Review ECK 3.x migration guide and breaking changes

### ❓ Option 4: Unknown Complexity
1. **plex** (media)
   - Image: `1.42.1.10060-4e8b05daf → latest` ⚪ UNKNOWN
   - Risk: Unknown (version format not recognized)
   - Action: Manually check Plex release notes for latest version

---

## Quick Overview Table

| Deployment | Namespace | Chart | Image | App | Complexity |
|------------|-----------|-------|-------|-----|------------|
| `icloud-docker-mu` | `backup` | 3.7.1 ? | latest ✅ | - | - |
| `nocodb` | `databases` | 3.7.1 ? | latest ✅ | - | - |
| `phpmyadmin` | `databases` | 3.7.1 ? | latest ✅ | - | - |
| `actual-budget` | `default` | 3.7.1 ? | latest ✅ | - | - |
| `ai-sre` | `default` | 3.7.1 ? | 2.1.0 ? | 2.1.0 | - |
| `cert-manager` | `default` | v1.19.2 ✅ | - | - | - |
| `cilium` | `default` | 1.18.6 ✅ | - | - | - |
| `clawd-bot` | `default` | 3.7.1 ? | 22-bookworm ? | 22-bookworm | - |
| `cloudflared` | `default` | 3.7.1 ? | 2025.11.1 ✅ | 2025.11.1 | - |
| `coredns` | `default` | 1.39.0 ? | - | - | - |
| `descheduler` | `default` | 0.34.0 ✅ | - | - | - |
| `echo-server` | `default` | 3.7.1 ? | 35 ? | 35 | - |
| `external-dns` | `default` | 1.20.0 ✅ | - | - | - |
| `external-ingress-nginx` | `default` | 4.14.1 ✅ | - | - | - |
| `fluent-bit` | `default` | 0.54.1 ✅ | 3.1.9 ? | 3.1.9 | - |
| `flux-instance` | `default` | 0.14.0 ? | - | - | - |
| `flux-operator` | `default` | 0.14.0 ? | - | - | - |
| `grafana` | `default` | 10.5.8 ✅ | - | - | - |
| `homepage` | `default` | 2.1.0 ✅ | v1.8.0 ? | v1.8.0 | - |
| `intel-device-plugin-gpu` | `default` | 0.34.1 ✅ | - | - | - |
| `intel-device-plugin-operator` | `default` | 0.34.1 ✅ | - | - | - |
| `internal-ingress-nginx` | `default` | 4.14.1 ✅ | - | - | - |
| `jdownloader` | `default` | 3.7.1 ? | v25.02.1 → v26.01.1 | v25.02.1 | 🔴 MAJOR |
| `k8s-gateway` | `default` | 2.4.0 ✅ | - | - | - |
| `kube-prometheus-stack` | `default` | 68.4.4 ? | - | - | - |
| `mcpo` | `default` | 3.7.1 ? | git-44ce6d0 ? | git-44ce6d0 | - |
| `metrics-server` | `default` | 3.13.0 ✅ | - | - | - |
| `nextcloud` | `default` | 6.6.4 → 8.8.1 | 32.0.3 ? | 32.0.3 | 🔴 MAJOR |
| `node-feature-discovery` | `default` | 0.18.3 ✅ | - | - | - |
| `omni-tools` | `default` | 3.7.1 ? | 0.6.0 ✅ | 0.6.0 | - |
| `open-webui` | `default` | 10.2.1 ✅ | 0.7.2 ? | 0.7.2 | - |
| `paperless-ai` | `default` | 3.7.1 ? | latest ✅ | - | - |
| `paperless-gpt` | `default` | 3.7.1 ? | latest ✅ | - | - |
| `redis` | `default` | 3.7.1 ? | 7-alpine ? | 7-alpine | - |
| `reloader` | `default` | 1.2.1 ? | - | - | - |
| `spegel` | `default` | v0.0.30 ? | - | - | - |
| `teslamate` | `default` | 3.7.1 ? | 2.2.0 ✅ | 2.2.0 | - |
| `tube-archivist` | `default` | 3.7.1 ? | v0.5.8 ✅ | v0.5.8 | - |
| `vaultwarden` | `default` | 3.7.1 ? | 1.35.2 ✅ | 1.35.2 | - |
| `esphome` | `home-automation` | 3.7.1 ? | 2025.12.7 ? | 2025.12.7 | - |
| `frigate` | `home-automation` | 7.8.0 ✅ | 0.16.3 ? | 0.16.3 | - |
| `home-assistant` | `home-automation` | 3.7.1 ? | 2026.1.2 ? | 2026.1.2 | - |
| `mosquitto` | `home-automation` | 3.7.1 ? | 2.0.20@sha256:8b396cec28cd5e8e1a3aba1d9a... | 2.0.20@sha256:8b396cec28cd5e8e... | - |
| `music-assistant-server` | `home-automation` | 3.7.1 ? | 2.7.5 ? | 2.7.5 | - |
| `n8n` | `home-automation` | 1.0.6 ? | 1.123.16 → 2.4.4 | 1.123.16 | 🔴 MAJOR |
| `node-red` | `home-automation` | 3.7.1 ? | 4.1.3 ✅ | 4.1.3 | - |
| `scrypted` | `home-automation` | 3.7.1 ? | latest ✅ | - | - |
| `zigbee2mqtt` | `home-automation` | 3.7.1 ? | 2.7.2 ✅ | 2.7.2 | - |
| `authentik` | `kube-system` | 2025.12.1 ✅ | - | - | - |
| `csi-driver-smb` | `kube-system` | 1.19.1 ✅ | - | - | - |
| `jellyfin` | `media` | 2.1.0 → 2.7.0 | 10.11.5 ✅ | 10.11.5 | 🟡 MINOR |
| `makemkv` | `media` | 3.7.1 ? | latest ✅ | - | - |
| `plex` | `media` | 1.4.0 ✅ | 1.42.1.10060-4e8b05daf → latest | 1.42.1.10060-4e8b05daf | ⚪ UNKNOWN |
| `eck-operator` | `monitoring` | 2.14.0 → 3.2.0 | - | - | 🔴 MAJOR |
| `headlamp` | `monitoring` | 0.39.0 ✅ | - | - | - |
| `unpoller` | `monitoring` | 2.1.0 ✅ | v2.21.0 ? | v2.21.0 | - |
| `uptime-kuma` | `monitoring` | 2.18.0 → 2.24.0 | 2.0.2 ✅ | 2.0.2 | 🟡 MINOR |
| `absenty` | `my-software-development` | 3.7.1 ? | sha-ff3910e-dev ? | sha-ff3910e-dev | - |
| `absenty` | `my-software-production` | 3.7.1 ? | sha-ffa072a ? | sha-ffa072a | - |
| `adguard-home` | `network` | 0.19.0 → 0.24.0 | v0.107.71 ✅ | v0.107.71 | 🟡 MINOR |
| `paperless-ngx` | `office` | 0.19.1 → 0.24.1 | 2.20.4 ? | 2.20.4 | 🟡 MINOR |
| `penpot` | `office` | 0.32.0 ✅ | - | - | - |
| `longhorn` | `storage` | 1.10.1 ✅ | - | - | - |

---

## Namespace: `backup`

### icloud-docker-mu

- **File:** `kubernetes/apps/backup/icloud-docker-mu/app/helmrelease.yaml`

#### Chart
- **Name:** `app-template`
- **Repository:** `bjw-s`
- **Current Version:** `3.7.1`
- **Latest Version:** *Could not determine*

#### Container Images
- **Repository:** `mandarons/icloud-drive`
  - **Path:** `controllers.main.containers.app.image`
  - **Current Tag:** `latest`
  - **Latest Tag:** `1.24.0` ✅ (up-to-date)

---

## Namespace: `databases`

### nocodb

- **File:** `kubernetes/apps/databases/nocodb/app/helmrelease.yaml`

#### Chart
- **Name:** `app-template`
- **Repository:** `bjw-s`
- **Current Version:** `3.7.1`
- **Latest Version:** *Could not determine*

#### Container Images
- **Repository:** `nocodb/nocodb`
  - **Path:** `controllers.nocodb.containers.app.image`
  - **Current Tag:** `latest`
  - **Latest Tag:** `0.301.1` ✅ (up-to-date)

---

### phpmyadmin

- **File:** `kubernetes/apps/databases/phpmyadmin/app/helmrelease.yaml`

#### Chart
- **Name:** `app-template`
- **Repository:** `bjw-s`
- **Current Version:** `3.7.1`
- **Latest Version:** *Could not determine*

#### Container Images
- **Repository:** `phpmyadmin`
  - **Path:** `controllers.phpmyadmin.containers.app.image`
  - **Current Tag:** `latest`
  - **Latest Tag:** *Could not determine*

---

## Namespace: `default`

### actual-budget

- **File:** `kubernetes/apps/office/actual-budget/app/helmrelease.yaml`

#### Chart
- **Name:** `app-template`
- **Repository:** `bjw-s`
- **Current Version:** `3.7.1`
- **Latest Version:** *Could not determine*

#### Container Images
- **Repository:** `actualbudget/actual-server`
  - **Path:** `controllers.main.containers.main.image`
  - **Current Tag:** `latest`
  - **Latest Tag:** `26.1.0` ✅ (up-to-date)

---

### ai-sre

- **File:** `kubernetes/apps/ai/ai-sre/app/helmrelease.yaml`

#### Chart
- **Name:** `app-template`
- **Repository:** `bjw-s`
- **Current Version:** `3.7.1`
- **Latest Version:** *Could not determine*

#### Container Images
- **Repository:** `ghcr.io/nachtschatt3n/ai-sre`
  - **Path:** `controllers.ai-sre.containers.app.image`
  - **Current Tag:** `2.1.0`
  - **Latest Tag:** *Could not determine*

---

### cert-manager

- **File:** `kubernetes/apps/cert-manager/cert-manager/app/helmrelease.yaml`

#### Chart
- **Name:** `cert-manager`
- **Repository:** `jetstack`
- **Current Version:** `v1.19.2`
- **Latest Version:** `v1.19.2` ✅ (up-to-date)

*No container images specified in values*

---

### cilium

- **File:** `kubernetes/apps/kube-system/cilium/app/helmrelease.yaml`

#### Chart
- **Name:** `cilium`
- **Repository:** `cilium`
- **Current Version:** `1.18.6`
- **Latest Version:** `1.18.6` ✅ (up-to-date)

*No container images specified in values*

---

### clawd-bot

- **File:** `kubernetes/apps/ai/clawd-bot/app/helmrelease.yaml`

#### Chart
- **Name:** `app-template`
- **Repository:** `bjw-s`
- **Current Version:** `3.7.1`
- **Latest Version:** *Could not determine*

#### Container Images
- **Repository:** `node`
  - **Path:** `controllers.clawd-bot.containers.app.image`
  - **Current Tag:** `22-bookworm`
  - **Latest Tag:** *Could not determine*

- **Repository:** `node`
  - **Path:** `controllers.clawd-bot.initContainers.install-clawdbot.image`
  - **Current Tag:** `22-bookworm`
  - **Latest Tag:** *Could not determine*

---

### cloudflared

- **File:** `kubernetes/apps/network/external/cloudflared/helmrelease.yaml`

#### Chart
- **Name:** `app-template`
- **Repository:** `bjw-s`
- **Current Version:** `3.7.1`
- **Latest Version:** *Could not determine*

#### Container Images
- **Repository:** `docker.io/cloudflare/cloudflared`
  - **Path:** `controllers.cloudflared.containers.app.image`
  - **Current Tag:** `2025.11.1`
  - **Latest Tag:** `2025.11.1` ✅ (up-to-date)

---

### coredns

- **File:** `kubernetes/apps/kube-system/coredns/app/helmrelease.yaml`

#### Chart
- **Name:** `coredns`
- **Repository:** `coredns`
- **Current Version:** `1.39.0`
- **Latest Version:** *Could not determine*

*No container images specified in values*

---

### descheduler

- **File:** `kubernetes/apps/kube-system/descheduler/app/helmrelease.yaml`

#### Chart
- **Name:** `descheduler`
- **Repository:** `descheduler`
- **Current Version:** `0.34.0`
- **Latest Version:** `0.34.0` ✅ (up-to-date)

*No container images specified in values*

---

### echo-server

- **File:** `kubernetes/apps/default/echo-server/app/helmrelease.yaml`

#### Chart
- **Name:** `app-template`
- **Repository:** `bjw-s`
- **Current Version:** `3.7.1`
- **Latest Version:** *Could not determine*

#### Container Images
- **Repository:** `ghcr.io/mendhak/http-https-echo`
  - **Path:** `controllers.echo-server.containers.app.image`
  - **Current Tag:** `35`
  - **Latest Tag:** *Could not determine*

---

### external-dns

- **File:** `kubernetes/apps/network/external/external-dns/helmrelease.yaml`

#### Chart
- **Name:** `external-dns`
- **Repository:** `external-dns`
- **Current Version:** `1.20.0`
- **Latest Version:** `1.20.0` ✅ (up-to-date)

*No container images specified in values*

---

### external-ingress-nginx

- **File:** `kubernetes/apps/network/external/ingress-nginx/helmrelease.yaml`

#### Chart
- **Name:** `ingress-nginx`
- **Repository:** `ingress-nginx`
- **Current Version:** `4.14.1`
- **Latest Version:** `4.14.1` ✅ (up-to-date)

*No container images specified in values*

---

### fluent-bit

- **File:** `kubernetes/apps/monitoring/fluent-bit/app/helmrelease.yaml`

#### Chart
- **Name:** `fluent-bit`
- **Repository:** `fluent`
- **Current Version:** `0.54.1`
- **Latest Version:** `0.54.1` ✅ (up-to-date)

#### Container Images
- **Repository:** `cr.fluentbit.io/fluent/fluent-bit`
  - **Path:** `image`
  - **Current Tag:** `3.1.9`
  - **Latest Tag:** *Could not determine*

---

### flux-instance

- **File:** `kubernetes/apps/flux-system/flux-operator/instance/helmrelease.yaml`

#### Chart
- **Name:** `flux-instance`
- **Repository:** `controlplaneio`
- **Current Version:** `0.14.0`
- **Latest Version:** *Could not determine*

*No container images specified in values*

---

### flux-operator

- **File:** `kubernetes/apps/flux-system/flux-operator/app/helmrelease.yaml`

#### Chart
- **Name:** `flux-operator`
- **Repository:** `controlplaneio`
- **Current Version:** `0.14.0`
- **Latest Version:** *Could not determine*

*No container images specified in values*

---

### grafana

- **File:** `kubernetes/apps/monitoring/grafana/app/helmrelease.yaml`

#### Chart
- **Name:** `grafana`
- **Repository:** `grafana`
- **Current Version:** `10.5.8`
- **Latest Version:** `10.5.8` ✅ (up-to-date)

*No container images specified in values*

---

### homepage

- **File:** `kubernetes/apps/default/homepage/app/helmrelease.yaml`

#### Chart
- **Name:** `homepage`
- **Repository:** `jameswynn`
- **Current Version:** `2.1.0`
- **Latest Version:** `2.1.0` ✅ (up-to-date)

#### Container Images
- **Repository:** `ghcr.io/gethomepage/homepage`
  - **Path:** `image`
  - **Current Tag:** `v1.8.0`
  - **Latest Tag:** *Could not determine*

---

### intel-device-plugin-gpu

- **File:** `kubernetes/apps/kube-system/intel-device-plugin/gpu/helmrelease.yaml`

#### Chart
- **Name:** `intel-device-plugins-gpu`
- **Repository:** `intel`
- **Current Version:** `0.34.1`
- **Latest Version:** `0.34.1` ✅ (up-to-date)

*No container images specified in values*

---

### intel-device-plugin-operator

- **File:** `kubernetes/apps/kube-system/intel-device-plugin/app/helmrelease.yaml`

#### Chart
- **Name:** `intel-device-plugins-operator`
- **Repository:** `intel`
- **Current Version:** `0.34.1`
- **Latest Version:** `0.34.1` ✅ (up-to-date)

*No container images specified in values*

---

### internal-ingress-nginx

- **File:** `kubernetes/apps/network/internal/ingress-nginx/helmrelease.yaml`

#### Chart
- **Name:** `ingress-nginx`
- **Repository:** `ingress-nginx`
- **Current Version:** `4.14.1`
- **Latest Version:** `4.14.1` ✅ (up-to-date)

*No container images specified in values*

---

### jdownloader

- **File:** `kubernetes/apps/download/jdownloader/app/helmrelease.yaml`

#### Chart
- **Name:** `app-template`
- **Repository:** `bjw-s`
- **Current Version:** `3.7.1`
- **Latest Version:** *Could not determine*

#### Container Images
- **Repository:** `jlesage/jdownloader-2`
  - **Path:** `controllers.main.containers.app.image`
  - **Current Tag:** `v25.02.1`
  - **Latest Tag:** `v26.01.1` ⚠️ **UPDATE AVAILABLE**
  - **Update Type:** 🔴 **MAJOR** (high complexity)
  - **Update Description:** Major version update: 25.x.x → 26.x.x
  - **⚠️ Breaking Changes Detected:**
    - Major version change typically indicates breaking changes
  - **Source:** https://github.com/jlesage/jdownloader-2/releases/tag/v26.01.1
  - **Release Notes:** *Could not fetch release notes (GitHub API rate limit or release not found). Check source link above.*
  - **⚠️ Breaking Changes:** *Major version update - review release notes above*

---

### k8s-gateway

- **File:** `kubernetes/apps/network/internal/k8s-gateway/helmrelease.yaml`

#### Chart
- **Name:** `k8s-gateway`
- **Repository:** `k8s-gateway`
- **Current Version:** `2.4.0`
- **Latest Version:** `2.4.0` ✅ (up-to-date)

*No container images specified in values*

---

### kube-prometheus-stack

- **File:** `kubernetes/apps/monitoring/kube-prometheus-stack/app/helmrelease.yaml`

#### Chart
- **Name:** `kube-prometheus-stack`
- **Repository:** `prometheus-community`
- **Current Version:** `68.4.4`
- **Latest Version:** *Could not determine*

*No container images specified in values*

---

### mcpo

- **File:** `kubernetes/apps/ai/mcpo/app/helmrelease.yaml`

#### Chart
- **Name:** `app-template`
- **Repository:** `bjw-s`
- **Current Version:** `3.7.1`
- **Latest Version:** *Could not determine*

#### Container Images
- **Repository:** `ghcr.io/open-webui/mcpo`
  - **Path:** `controllers.mcpo.containers.app.image`
  - **Current Tag:** `git-44ce6d0`
  - **Latest Tag:** *Could not determine*

- **Repository:** `python`
  - **Path:** `controllers.mcpo.initContainers.runtime-setup.image`
  - **Current Tag:** `3.11-slim`
  - **Latest Tag:** *Could not determine*

---

### metrics-server

- **File:** `kubernetes/apps/kube-system/metrics-server/app/helmrelease.yaml`

#### Chart
- **Name:** `metrics-server`
- **Repository:** `metrics-server`
- **Current Version:** `3.13.0`
- **Latest Version:** `3.13.0` ✅ (up-to-date)

*No container images specified in values*

---

### nextcloud

- **File:** `kubernetes/apps/office/nextcloud/app/helmrelease.yaml`

#### Chart
- **Name:** `nextcloud`
- **Repository:** `nextcloud`
- **Current Version:** `6.6.4`
- **Latest Version:** `8.8.1` ⚠️ **UPDATE AVAILABLE**
- **Update Type:** 🔴 **MAJOR** (high complexity)
- **Update Description:** Major version update: 6.x.x → 8.x.x
- **Source:** https://github.com/nextcloud/helm/releases/tag/8.8.1
- **Release Notes:** *Could not fetch release notes (GitHub API rate limit or release not found). Check source link above.*
- **⚠️ Breaking Changes:** *Major version update - review release notes above for breaking changes*

#### Container Images
- **Repository:** `nextcloud`
  - **Path:** `image`
  - **Current Tag:** `32.0.3`
  - **Latest Tag:** *Could not determine*

- **Repository:** `bitnamilegacy/mariadb`
  - **Path:** `mariadb.image`
  - **Current Tag:** `latest`
  - **Latest Tag:** `12.0.2` ✅ (up-to-date)

- **Repository:** `xperimental/nextcloud-exporter`
  - **Path:** `metrics.image`
  - **Current Tag:** `0.6.2`
  - **Latest Tag:** `0.9.0` ⚠️ **UPDATE AVAILABLE**
  - **Update Type:** 🟡 **MINOR** (medium complexity)
  - **Update Description:** Minor version update: 0.6.x → 0.9.x
  - **Source:** https://github.com/xperimental/nextcloud-exporter/releases/tag/0.9.0
  - **Release Date:** 2025-10-12
  - **Release Notes:**
    ```markdown
    ## Docker images

```plain
xperimental/nextcloud-exporter:0.9.0
ghcr.io/xperimental/nextcloud-exporter:0.9.0
```

## Changelog

### Added

- Prometheus alerting rule for notifying for updates (see `contrib/prometheus-alerts.yaml`)
- Additional labels on `nextcloud_scrape_errors_total`
  - `unavailable` for HTTP Service Unavailable (503) errors
  - `maintenance` for maintenance mode
- Panels for scrape errors and version info in Grafana Dashboard

### Changed

- Updated Go runtime and dependencies
    ```

- **Repository:** `bitnamilegacy/redis`
  - **Path:** `redis.image`
  - **Current Tag:** `latest`
  - **Latest Tag:** `8.2.1` ✅ (up-to-date)

---

### node-feature-discovery

- **File:** `kubernetes/apps/kube-system/node-feature-discovery/app/helmrelease.yaml`

#### Chart
- **Name:** `node-feature-discovery`
- **Repository:** `node-feature-discovery`
- **Current Version:** `0.18.3`
- **Latest Version:** `0.18.3` ✅ (up-to-date)

*No container images specified in values*

---

### omni-tools

- **File:** `kubernetes/apps/office/omni-tools/app/helmrelease.yaml`

#### Chart
- **Name:** `app-template`
- **Repository:** `bjw-s`
- **Current Version:** `3.7.1`
- **Latest Version:** *Could not determine*

#### Container Images
- **Repository:** `iib0011/omni-tools`
  - **Path:** `controllers.main.containers.main.image`
  - **Current Tag:** `0.6.0`
  - **Latest Tag:** `0.6.0` ✅ (up-to-date)

---

### open-webui

- **File:** `kubernetes/apps/ai/open-webui/app/helmrelease.yaml`

#### Chart
- **Name:** `open-webui`
- **Repository:** `open-webui`
- **Current Version:** `10.2.1`
- **Latest Version:** `10.2.1` ✅ (up-to-date)

#### Container Images
- **Repository:** `ghcr.io/open-webui/open-webui`
  - **Path:** `image`
  - **Current Tag:** `0.7.2`
  - **Latest Tag:** *Could not determine*

---

### paperless-ai

- **File:** `kubernetes/apps/office/paperless-ai/app/helmrelease.yaml`

#### Chart
- **Name:** `app-template`
- **Repository:** `bjw-s`
- **Current Version:** `3.7.1`
- **Latest Version:** *Could not determine*

#### Container Images
- **Repository:** `clusterzx/paperless-ai`
  - **Path:** `controllers.main.containers.main.image`
  - **Current Tag:** `latest`
  - **Latest Tag:** `3.0.9` ✅ (up-to-date)

---

### paperless-gpt

- **File:** `kubernetes/apps/office/paperless-gpt/app/helmrelease.yaml`

#### Chart
- **Name:** `app-template`
- **Repository:** `bjw-s`
- **Current Version:** `3.7.1`
- **Latest Version:** *Could not determine*

#### Container Images
- **Repository:** `icereed/paperless-gpt`
  - **Path:** `controllers.main.containers.main.image`
  - **Current Tag:** `latest`
  - **Latest Tag:** `v0.24.0` ✅ (up-to-date)

---

### redis

- **File:** `kubernetes/apps/databases/redis/app/helmrelease.yaml`

#### Chart
- **Name:** `app-template`
- **Repository:** `bjw-s`
- **Current Version:** `3.7.1`
- **Latest Version:** *Could not determine*

#### Container Images
- **Repository:** `redis`
  - **Path:** `controllers.redis.containers.app.image`
  - **Current Tag:** `7-alpine`
  - **Latest Tag:** *Could not determine*

---

### reloader

- **File:** `kubernetes/apps/kube-system/reloader/app/helmrelease.yaml`

#### Chart
- **Name:** `reloader`
- **Repository:** `stakater`
- **Current Version:** `1.2.1`
- **Latest Version:** *Could not determine*

*No container images specified in values*

---

### spegel

- **File:** `kubernetes/apps/kube-system/spegel/app/helmrelease.yaml`

#### Chart
- **Name:** `spegel`
- **Repository:** `spegel`
- **Current Version:** `v0.0.30`
- **Latest Version:** *Could not determine*

*No container images specified in values*

---

### teslamate

- **File:** `kubernetes/apps/home-automation/teslamate/app/helmrelease.yaml`

#### Chart
- **Name:** `app-template`
- **Repository:** `bjw-s`
- **Current Version:** `3.7.1`
- **Latest Version:** *Could not determine*

#### Container Images
- **Repository:** `teslamate/teslamate`
  - **Path:** `controllers.main.containers.main.image`
  - **Current Tag:** `2.2.0`
  - **Latest Tag:** `2.2.0` ✅ (up-to-date)

---

### tube-archivist

- **File:** `kubernetes/apps/download/tube-archivist/app/helmrelease.yaml`

#### Chart
- **Name:** `app-template`
- **Repository:** `bjw-s`
- **Current Version:** `3.7.1`
- **Latest Version:** *Could not determine*

#### Container Images
- **Repository:** `bbilly1/tubearchivist`
  - **Path:** `controllers.main.containers.app.image`
  - **Current Tag:** `v0.5.8`
  - **Latest Tag:** `v0.5.8` ✅ (up-to-date)

---

### vaultwarden

- **File:** `kubernetes/apps/office/vaultwarden/app/helmrelease.yaml`

#### Chart
- **Name:** `app-template`
- **Repository:** `bjw-s`
- **Current Version:** `3.7.1`
- **Latest Version:** *Could not determine*

#### Container Images
- **Repository:** `vaultwarden/server`
  - **Path:** `controllers.main.containers.main.image`
  - **Current Tag:** `1.35.2`
  - **Latest Tag:** `1.35.2` ✅ (up-to-date)

---

## Namespace: `home-automation`

### esphome

- **File:** `kubernetes/apps/home-automation/esphome/app/helmrelease.yaml`

#### Chart
- **Name:** `app-template`
- **Repository:** `bjw-s`
- **Current Version:** `3.7.1`
- **Latest Version:** *Could not determine*

#### Container Images
- **Repository:** `ghcr.io/esphome/esphome`
  - **Path:** `controllers.esphome.containers.app.image`
  - **Current Tag:** `2025.12.7`
  - **Latest Tag:** *Could not determine*

---

### frigate

- **File:** `kubernetes/apps/home-automation/frigate-nvr/app/helmrelease.yaml`

#### Chart
- **Name:** `frigate`
- **Repository:** `blakeblackshear`
- **Current Version:** `7.8.0`
- **Latest Version:** `7.8.0` ✅ (up-to-date)

#### Container Images
- **Repository:** `ghcr.io/blakeblackshear/frigate`
  - **Path:** `image`
  - **Current Tag:** `0.16.3`
  - **Latest Tag:** *Could not determine*

---

### home-assistant

- **File:** `kubernetes/apps/home-automation/home-assistant/app/helmrelease.yaml`

#### Chart
- **Name:** `app-template`
- **Repository:** `bjw-s`
- **Current Version:** `3.7.1`
- **Latest Version:** *Could not determine*

#### Container Images
- **Repository:** `ghcr.io/home-assistant/home-assistant`
  - **Path:** `controllers.home-assistant.containers.app.image`
  - **Current Tag:** `2026.1.2`
  - **Latest Tag:** *Could not determine*

---

### mosquitto

- **File:** `kubernetes/apps/home-automation/mosquitto/app/helmrelease.yaml`

#### Chart
- **Name:** `app-template`
- **Repository:** `bjw-s`
- **Current Version:** `3.7.1`
- **Latest Version:** *Could not determine*

#### Container Images
- **Repository:** `public.ecr.aws/docker/library/eclipse-mosquitto`
  - **Path:** `controllers.mosquitto.containers.app.image`
  - **Current Tag:** `2.0.20@sha256:8b396cec28cd5e8e1a3aba1d9abdbddd42c454c80f703e77c1bec56e152fa54e`
  - **Latest Tag:** *Could not determine*

- **Repository:** `public.ecr.aws/docker/library/eclipse-mosquitto`
  - **Path:** `controllers.mosquitto.initContainers.init-config.image`
  - **Current Tag:** `2.0.20@sha256:8b396cec28cd5e8e1a3aba1d9abdbddd42c454c80f703e77c1bec56e152fa54e`
  - **Latest Tag:** *Could not determine*

---

### music-assistant-server

- **File:** `kubernetes/apps/home-automation/music-assistant-server/app/helmrelease.yaml`

#### Chart
- **Name:** `app-template`
- **Repository:** `bjw-s`
- **Current Version:** `3.7.1`
- **Latest Version:** *Could not determine*

#### Container Images
- **Repository:** `ghcr.io/music-assistant/server`
  - **Path:** `controllers.music-assistant-server.containers.app.image`
  - **Current Tag:** `2.7.5`
  - **Latest Tag:** *Could not determine*

- **Repository:** `ghcr.io/alams154/music-assistant-alexa-api`
  - **Path:** `controllers.music-assistant-server.containers.alexa-api.image`
  - **Current Tag:** `latest`
  - **Latest Tag:** *Could not determine*

---

### n8n

- **File:** `kubernetes/apps/home-automation/n8n/app/helmrelease.yaml`

#### Chart
- **Name:** `n8n`
- **Repository:** `n8n`
- **Current Version:** `1.0.6`
- **Latest Version:** *Could not determine*

#### Container Images
- **Repository:** `n8nio/n8n`
  - **Path:** `image`
  - **Current Tag:** `1.123.16`
  - **Latest Tag:** `2.4.4` ⚠️ **UPDATE AVAILABLE**
  - **Update Type:** 🔴 **MAJOR** (high complexity)
  - **Update Description:** Major version update: 1.x.x → 2.x.x
  - **⚠️ Breaking Changes Detected:**
    - Major version change typically indicates breaking changes
  - **Source:** https://github.com/n8nio/n8n/releases/tag/2.4.4
  - **Release Notes:** *Could not fetch release notes (GitHub API rate limit or release not found). Check source link above.*
  - **⚠️ Breaking Changes:** *Major version update - review release notes above*

---

### node-red

- **File:** `kubernetes/apps/home-automation/node-red/app/helmrelease.yaml`

#### Chart
- **Name:** `app-template`
- **Repository:** `bjw-s`
- **Current Version:** `3.7.1`
- **Latest Version:** *Could not determine*

#### Container Images
- **Repository:** `nodered/node-red`
  - **Path:** `controllers.node-red.containers.app.image`
  - **Current Tag:** `4.1.3`
  - **Latest Tag:** `4.1.3` ✅ (up-to-date)

---

### scrypted

- **File:** `kubernetes/apps/home-automation/scrypted-nvr/app/helmrelease.yaml`

#### Chart
- **Name:** `app-template`
- **Repository:** `bjw-s`
- **Current Version:** `3.7.1`
- **Latest Version:** *Could not determine*

#### Container Images
- **Repository:** `koush/scrypted`
  - **Path:** `controllers.scrypted.containers.app.image`
  - **Current Tag:** `latest`
  - **Latest Tag:** `latest` ✅ (up-to-date)

---

### zigbee2mqtt

- **File:** `kubernetes/apps/home-automation/zigbee2mqtt/app/helmrelease.yaml`

#### Chart
- **Name:** `app-template`
- **Repository:** `bjw-s`
- **Current Version:** `3.7.1`
- **Latest Version:** *Could not determine*

#### Container Images
- **Repository:** `koenkk/zigbee2mqtt`
  - **Path:** `controllers.zigbee2mqtt.containers.app.image`
  - **Current Tag:** `2.7.2`
  - **Latest Tag:** `2.7.2` ✅ (up-to-date)

---

## Namespace: `kube-system`

### authentik

- **File:** `kubernetes/apps/kube-system/authentik/app/helmrelease.yaml`

#### Chart
- **Name:** `authentik`
- **Repository:** `authentik`
- **Current Version:** `2025.12.1`
- **Latest Version:** `2025.12.1` ✅ (up-to-date)

*No container images specified in values*

---

### csi-driver-smb

- **File:** `kubernetes/apps/kube-system/csi-driver-smb/app/helmrelease.yaml`

#### Chart
- **Name:** `csi-driver-smb`
- **Repository:** `csi-driver-smb`
- **Current Version:** `1.19.1`
- **Latest Version:** `1.19.1` ✅ (up-to-date)

*No container images specified in values*

---

## Namespace: `media`

### jellyfin

- **File:** `kubernetes/apps/media/jellyfin/app/helmrelease.yaml`

#### Chart
- **Name:** `jellyfin`
- **Repository:** `jellyfin`
- **Current Version:** `2.1.0`
- **Latest Version:** `2.7.0` ⚠️ **UPDATE AVAILABLE**
- **Update Type:** 🟡 **MINOR** (medium complexity)
- **Update Description:** Minor version update: 2.1.x → 2.7.x
- **Source:** https://github.com/jellyfin/jellyfin/releases/tag/2.7.0
- **Release Notes:** *Could not fetch release notes (GitHub API rate limit or release not found). Check source link above.*
- **⚠️ Breaking Changes:** *Review release notes above for potential breaking changes*

#### Container Images
- **Repository:** `docker.io/jellyfin/jellyfin`
  - **Path:** `image`
  - **Current Tag:** `10.11.5`
  - **Latest Tag:** `10.11.5` ✅ (up-to-date)

---

### makemkv

- **File:** `kubernetes/apps/media/makemkv/app/helmrelease.yaml`

#### Chart
- **Name:** `app-template`
- **Repository:** `bjw-s`
- **Current Version:** `3.7.1`
- **Latest Version:** *Could not determine*

#### Container Images
- **Repository:** `jlesage/makemkv`
  - **Path:** `image`
  - **Current Tag:** `latest`
  - **Latest Tag:** `v26.01.1` ✅ (up-to-date)

- **Repository:** `jlesage/makemkv`
  - **Path:** `controllers.main.containers.main.image`
  - **Current Tag:** `latest`
  - **Latest Tag:** `v26.01.1` ✅ (up-to-date)

---

### plex

- **File:** `kubernetes/apps/media/plex/app/helmrelease.yaml`

#### Chart
- **Name:** `plex-media-server`
- **Repository:** `plex`
- **Current Version:** `1.4.0`
- **Latest Version:** `1.4.0` ✅ (up-to-date)

#### Container Images
- **Repository:** `plexinc/pms-docker`
  - **Path:** `image`
  - **Current Tag:** `1.42.1.10060-4e8b05daf`
  - **Latest Tag:** `latest` ⚠️ **UPDATE AVAILABLE**
  - **Update Type:** ⚪ **UNKNOWN** (unknown complexity)
  - **Update Description:** Version format not recognized
  - **Source:** https://github.com/plexinc/pms-docker/releases/tag/latest
  - **Release Notes:** *Could not fetch release notes (GitHub API rate limit or release not found). Check source link above.*

---

## Namespace: `monitoring`

### eck-operator

- **File:** `kubernetes/apps/monitoring/eck-operator/app/helmrelease.yaml`

#### Chart
- **Name:** `eck-operator`
- **Repository:** `elastic`
- **Current Version:** `2.14.0`
- **Latest Version:** `3.2.0` ⚠️ **UPDATE AVAILABLE**
- **Update Type:** 🔴 **MAJOR** (high complexity)
- **Update Description:** Major version update: 2.x.x → 3.x.x
- **Source:** https://github.com/elastic/cloud-on-k8s/releases/tag/3.2.0
- **Release Date:** 2025-10-30
- **Release Notes:**
  ```markdown
  # Elastic Cloud on Kubernetes 3.2.0
- [Quickstart guide](https://www.elastic.co/docs/deploy-manage/deploy/cloud-on-k8s#eck-quickstart)

### Release Highlights

#### Automatic pod disruption budget (Enterprise feature)

ECK now offers better out-of-the-box PodDisruptionBudgets that automatically keep your cluster available as Pods move across nodes. The new policy calculates the number of Pods per tier that can sustain replacement and automatically generates a PodDisruptionBudget for each tier, enabling the Elasticsearch cluster to vacate Kubernetes nodes more quickly, while considering cluster health, without interruption.

#### User Password Generation (Enterprise feature)

ECK will now generate longer passwords by default for the administrative user of each Elasticsearch cluster. The password is 24 characters in length by default (can be configured to a maximum of 72 characters), incorporating alphabetic and numeric characters, to make password complexity stronger.

### Features and enhancements

- Enable certificate reloading for stack monitoring Beats [#8833](https://github.com/elastic/cloud-on-k8s/pull/8833) (issue: [#5448](https://github.com/elastic/cloud-on-k8s/issues/5448))
- Allow configuration of file-based password character set and length [#8817](https://github.com/elastic/cloud-on-k8s/pull/8817) (issues: [#2795](https://github.com/elastic/cloud-on-k8s/issues/2795), [#8693](https://github.com/elastic/cloud-on-k8s/issues/8693))
- Automatically set GOMEMLIMIT based on cgroups memory limits [#8814](https://github.com/elastic/cloud-on-k8s/pull/8814) (issue: [#8790](https://github.com/elastic/cloud-on-k8s/issues/8790))
- Introduce granular PodDisruptionBudgets based on node roles [#8780](https://github.com/elastic/cloud-on-k8s/pull/8780) (issue: [#2936](https://github.com/elastic/cloud-on-k8s/issues/2936))

### Fixes

- Gate advanced Fleet config logic to Agent v8.13 and later [#8869](https://github.com/elastic/cloud-on-k8s/pull/8869)
- Ensure Agent configuration and state persist across restarts in Fleet mode [#8856](https://github.com/elastic/cloud-on-k8s/pull/8856) (issue: [#8819](https://github.com/elastic/cloud-on-k8s/issues/8819))
- Do not set credentials label on Kibana config secret [#8852](https://github.com/elastic/cloud-on-k8s/pull/8852) (issue: [#8839](https://github.com/elastic/cloud-on-k8s/issues/8839))
- Allow elasticsearchRef.secretName in Kibana helm validation [#8822](https://github.com/elastic/cloud-on-k8s/pull/8822) (issue: [#8816](https://github.com/elastic/cloud-on-k8s/issues/8816))

### Documentation improvements

- Update Logstash recipes from to filestream input [#8801](https://github.com/elastic/cloud-on-k8s/pull/8801)
- Recipe for exposing Fleet server to outside of the Kubernetes cluster [#8788](https://github.com/elastic/cloud-on-k8s/pull/8788)
- Clarify secretName restrictions [#8782](https://github.com/elastic/cloud-on-k8s/pull/8782)
- Update ES_JAVA_OPTS comments and explain a
  ... (truncated, see source link above for full notes)
  ```
- **⚠️ Breaking Changes:** *Major version update - review release notes above for breaking changes*

*No container images specified in values*

---

### headlamp

- **File:** `kubernetes/apps/monitoring/headlamp/app/helmrelease.yaml`

#### Chart
- **Name:** `headlamp`
- **Repository:** `headlamp`
- **Current Version:** `0.39.0`
- **Latest Version:** `0.39.0` ✅ (up-to-date)

*No container images specified in values*

---

### unpoller

- **File:** `kubernetes/apps/monitoring/unpoller/app/helmrelease.yaml`

#### Chart
- **Name:** `unpoller`
- **Repository:** `unpoller`
- **Current Version:** `2.1.0`
- **Latest Version:** `2.1.0` ✅ (up-to-date)

#### Container Images
- **Repository:** `ghcr.io/unpoller/unpoller`
  - **Path:** `image`
  - **Current Tag:** `v2.21.0`
  - **Latest Tag:** *Could not determine*

---

### uptime-kuma

- **File:** `kubernetes/apps/monitoring/uptime-kuma/app/helmrelease.yaml`

#### Chart
- **Name:** `uptime-kuma`
- **Repository:** `dirsigler`
- **Current Version:** `2.18.0`
- **Latest Version:** `2.24.0` ⚠️ **UPDATE AVAILABLE**
- **Update Type:** 🟡 **MINOR** (medium complexity)
- **Update Description:** Minor version update: 2.18.x → 2.24.x
- **Source:** https://github.com/louislam/uptime-kuma/releases/tag/2.24.0
- **Release Notes:** *Could not fetch release notes (GitHub API rate limit or release not found). Check source link above.*
- **⚠️ Breaking Changes:** *Review release notes above for potential breaking changes*

#### Container Images
- **Repository:** `louislam/uptime-kuma`
  - **Path:** `image`
  - **Current Tag:** `2.0.2`
  - **Latest Tag:** `2.0.2` ✅ (up-to-date)

---

## Namespace: `my-software-development`

### absenty

- **File:** `kubernetes/apps/my-software-development/absenty/app/helmrelease.yaml`

#### Chart
- **Name:** `app-template`
- **Repository:** `bjw-s`
- **Current Version:** `3.7.1`
- **Latest Version:** *Could not determine*

#### Container Images
- **Repository:** `ghcr.io/nachtschatt3n/absenty`
  - **Path:** `controllers.absenty.containers.app.image`
  - **Current Tag:** `sha-ff3910e-dev`
  - **Latest Tag:** *Could not determine*

- **Repository:** `ghcr.io/nachtschatt3n/absenty`
  - **Path:** `controllers.absenty.initContainers.bundle-install.image`
  - **Current Tag:** `sha-ff3910e-dev`
  - **Latest Tag:** *Could not determine*

---

## Namespace: `my-software-production`

### absenty

- **File:** `kubernetes/apps/my-software-production/absenty/app/helmrelease.yaml`

#### Chart
- **Name:** `app-template`
- **Repository:** `bjw-s`
- **Current Version:** `3.7.1`
- **Latest Version:** *Could not determine*

#### Container Images
- **Repository:** `ghcr.io/nachtschatt3n/absenty`
  - **Path:** `controllers.absenty.containers.app.image`
  - **Current Tag:** `sha-ffa072a`
  - **Latest Tag:** *Could not determine*

---

## Namespace: `network`

### adguard-home

- **File:** `kubernetes/apps/network/internal/adguard-home/app/helmrelease.yaml`

#### Chart
- **Name:** `adguard-home`
- **Repository:** `rm3l`
- **Current Version:** `0.19.0`
- **Latest Version:** `0.24.0` ⚠️ **UPDATE AVAILABLE**
- **Update Type:** 🟡 **MINOR** (medium complexity)
- **Update Description:** Minor version update: 0.19.x → 0.24.x
- **Source:** https://github.com/AdguardTeam/AdGuardHome/releases/tag/0.24.0
- **Release Notes:** *Could not fetch release notes (GitHub API rate limit or release not found). Check source link above.*
- **⚠️ Breaking Changes:** *Review release notes above for potential breaking changes*

#### Container Images
- **Repository:** `adguard/adguardhome`
  - **Path:** `image`
  - **Current Tag:** `v0.107.71`
  - **Latest Tag:** `v0.107.71` ✅ (up-to-date)

---

## Namespace: `office`

### paperless-ngx

- **File:** `kubernetes/apps/office/paperless-ngx/app/helmrelease.yaml`

#### Chart
- **Name:** `paperless-ngx`
- **Repository:** `gabe565`
- **Current Version:** `0.19.1`
- **Latest Version:** `0.24.1` ⚠️ **UPDATE AVAILABLE**
- **Update Type:** 🟡 **MINOR** (medium complexity)
- **Update Description:** Minor version update: 0.19.x → 0.24.x
- **Source:** https://github.com/paperless-ngx/paperless/releases/tag/0.24.1
- **Release Notes:** *Could not fetch release notes (GitHub API rate limit or release not found). Check source link above.*
- **⚠️ Breaking Changes:** *Review release notes above for potential breaking changes*

#### Container Images
- **Repository:** `ghcr.io/paperless-ngx/paperless-ngx`
  - **Path:** `image`
  - **Current Tag:** `2.20.4`
  - **Latest Tag:** *Could not determine*

- **Repository:** `bitnamilegacy/mariadb`
  - **Path:** `mariadb.image`
  - **Current Tag:** `latest`
  - **Latest Tag:** `12.0.2` ✅ (up-to-date)

- **Repository:** `bitnamilegacy/redis`
  - **Path:** `redis.image`
  - **Current Tag:** `latest`
  - **Latest Tag:** `8.2.1` ✅ (up-to-date)

---

### penpot

- **File:** `kubernetes/apps/office/penpot/app/helmrelease.yaml`

#### Chart
- **Name:** `penpot`
- **Repository:** `penpot`
- **Current Version:** `0.32.0`
- **Latest Version:** `0.32.0` ✅ (up-to-date)

*No container images specified in values*

---

## Namespace: `storage`

### longhorn

- **File:** `kubernetes/apps/storage/longhorn/app/helmrelease.yaml`

#### Chart
- **Name:** `longhorn`
- **Repository:** `longhorn`
- **Current Version:** `1.10.1`
- **Latest Version:** `1.10.1` ✅ (up-to-date)

*No container images specified in values*

---
