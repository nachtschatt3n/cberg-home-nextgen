# Kubernetes Deployment Version Status

**Generated:** 2026-01-29 19:21:11

> **Note:** Release notes are fetched from GitHub API. If rate limited, some release notes may not be available. Check source links for full details.

## Summary

- **Total Deployments:** 65
- **Chart Updates Available:** 11
- **Image Updates Available:** 11
- **Update Breakdown:** 🔴 5 major | 🟡 8 minor | 🟢 6 patch
- **⚠️ Breaking Changes Detected:** 8 updates with potential breaking changes

---

## Quick Overview Table

| Deployment | Namespace | Chart | Image | App | Complexity |
|------------|-----------|-------|-------|-----|------------|
| `icloud-docker-mu` | `backup` | 3.7.1 ? | latest ✅ | - | - |
| `nocodb` | `databases` | 3.7.1 ? | latest ✅ | - | - |
| `phpmyadmin` | `databases` | 3.7.1 ? | latest ✅ | - | - |
| `actual-budget` | `default` | 3.7.1 ? | latest ✅ | - | - |
| `ai-sre` | `default` | 3.7.1 ? | 2.1.0 → 2.1.1 | 2.1.0 | 🟢 PATCH |
| `cert-manager` | `default` | v1.19.2 ✅ | - | - | - |
| `cilium` | `default` | 1.18.6 ✅ | - | - | - |
| `clawd-bot` | `default` | 3.7.1 ? | 22-bookworm ? | 22-bookworm | - |
| `cloudflared` | `default` | 3.7.1 ? | 2025.11.1 ✅ | 2025.11.1 | - |
| `coredns` | `default` | 1.39.2 ? | - | - | - |
| `descheduler` | `default` | 0.34.0 ✅ | - | - | - |
| `echo-server` | `default` | 3.7.1 ? | 35 ? | 35 | - |
| `external-dns` | `default` | 1.20.0 ✅ | - | - | - |
| `external-ingress-nginx` | `default` | 4.14.1 → 4.14.2 | - | - | 🟢 PATCH |
| `fluent-bit` | `default` | 0.54.1 → 0.55.0 | 3.1.9 ? | 3.1.9 | 🟡 MINOR |
| `flux-instance` | `default` | 0.14.0 ? | - | - | - |
| `flux-operator` | `default` | 0.14.0 ? | - | - | - |
| `grafana` | `default` | 10.5.8 → 10.5.14 | - | - | 🟢 PATCH |
| `homepage` | `default` | 2.1.0 ✅ | v1.9.0 → 1.9.0 | v1.9.0 | ⚪ UNKNOWN |
| `intel-device-plugin-gpu` | `default` | 0.34.1 ✅ | - | - | - |
| `intel-device-plugin-operator` | `default` | 0.34.1 ✅ | - | - | - |
| `internal-ingress-nginx` | `default` | 4.14.1 → 4.14.2 | - | - | 🟢 PATCH |
| `jdownloader` | `default` | 3.7.1 ? | v25.02.1 → v26.01.1 | v25.02.1 | 🔴 MAJOR |
| `k8s-gateway` | `default` | 2.4.0 ✅ | - | - | - |
| `kube-prometheus-stack` | `default` | 68.5.0 ? | - | - | - |
| `mcpo` | `default` | 3.7.1 ? | git-44ce6d0 → 0.0.19 | git-44ce6d0 | ⚪ UNKNOWN |
| `metrics-server` | `default` | 3.13.0 ✅ | - | - | - |
| `nextcloud` | `default` | 6.6.10 → 8.9.0 | 32.0.5 ? | 32.0.5 | 🔴 MAJOR |
| `node-feature-discovery` | `default` | 0.18.3 ✅ | - | - | - |
| `omni-tools` | `default` | 3.7.1 ? | 0.6.0 ✅ | 0.6.0 | - |
| `open-webui` | `default` | 10.2.1 ✅ | 0.7.2 ✅ | 0.7.2 | - |
| `paperless-ai` | `default` | 3.7.1 ? | latest ✅ | - | - |
| `paperless-gpt` | `default` | 3.7.1 ? | latest ✅ | - | - |
| `redis` | `default` | 3.7.1 ? | 7-alpine ? | 7-alpine | - |
| `reloader` | `default` | 1.3.0 ? | - | - | - |
| `spegel` | `default` | v0.0.30 ? | - | - | - |
| `teslamate` | `default` | 3.7.1 ? | 2.2.0 ✅ | 2.2.0 | - |
| `tube-archivist` | `default` | 3.7.1 ? | v0.5.8 ✅ | v0.5.8 | - |
| `vaultwarden` | `default` | 3.7.1 ? | 1.35.2 ✅ | 1.35.2 | - |
| `esphome` | `home-automation` | 3.7.1 ? | 2025.12.7 → 2026.1.2 | 2025.12.7 | 🔴 MAJOR |
| `frigate` | `home-automation` | 7.8.0 ✅ | 0.16.3 → 0.16.4 | 0.16.3 | 🟢 PATCH |
| `home-assistant` | `home-automation` | 3.7.1 ? | 2026.1.3 ✅ | 2026.1.3 | - |
| `mosquitto` | `home-automation` | 3.7.1 ? | 2.0.22 ? | 2.0.22 | - |
| `music-assistant-server` | `home-automation` | 3.7.1 ? | 2.7.5 ✅ | 2.7.5 | - |
| `n8n` | `home-automation` | 1.1.0 ? | 1.123.17 → 2.6.2 | 1.123.17 | 🔴 MAJOR |
| `node-red` | `home-automation` | 3.7.1 ? | 4.1.3 → 4.1.4 | 4.1.3 | 🟢 PATCH |
| `scrypted` | `home-automation` | 3.7.1 ? | latest ✅ | - | - |
| `zigbee2mqtt` | `home-automation` | 3.7.1 ? | 2.7.2 ✅ | 2.7.2 | - |
| `authentik` | `kube-system` | 2025.12.1 ✅ | - | - | - |
| `csi-driver-smb` | `kube-system` | 1.19.1 ✅ | - | - | - |
| `jellyfin` | `media` | 2.1.0 → 2.7.0 | 10.11.6 ✅ | 10.11.6 | 🟡 MINOR |
| `makemkv` | `media` | 3.7.1 ? | latest ✅ | - | - |
| `plex` | `media` | 1.4.0 ✅ | 1.42.1.10060-4e8b05daf → latest | 1.42.1.10060-4e8b05daf | ⚪ UNKNOWN |
| `eck-operator` | `monitoring` | 2.14.0 → 3.2.0 | - | - | 🔴 MAJOR |
| `headlamp` | `monitoring` | 0.39.0 ✅ | - | - | - |
| `unpoller` | `monitoring` | 2.1.0 ✅ | v2.21.0 → 2.25.0 | v2.21.0 | 🟡 MINOR |
| `uptime-kuma` | `monitoring` | 2.18.0 → 2.24.0 | 2.0.2 ✅ | 2.0.2 | 🟡 MINOR |
| `absenty` | `my-software-development` | 3.7.1 ? | sha-ff3910e-dev ? | sha-ff3910e-dev | - |
| `andreamosteller` | `my-software-development` | 3.7.1 ? | sha-394fe9f ? | sha-394fe9f | - |
| `absenty` | `my-software-production` | 3.7.1 ? | sha-ffa072a ? | sha-ffa072a | - |
| `andreamosteller` | `my-software-production` | 3.7.1 ? | 5d88656-unprivileged-v2 ? | 5d88656-unprivileged-v2 | - |
| `adguard-home` | `network` | 0.19.0 → 0.24.0 | v0.107.71 ✅ | v0.107.71 | 🟡 MINOR |
| `paperless-ngx` | `office` | 0.19.1 → 0.24.1 | 2.20.5 ✅ | 2.20.5 | 🟡 MINOR |
| `penpot` | `office` | 0.32.0 ✅ | - | - | - |
| `longhorn` | `storage` | 1.10.1 → 1.11.0 | - | - | 🟡 MINOR |

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
  - **Latest Tag:** `0.301.2` ✅ (up-to-date)

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
  - **Latest Tag:** `sha-19edbeb-alpine` ✅ (up-to-date)

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
  - **Latest Tag:** `2.1.1` ⚠️ **UPDATE AVAILABLE**
  - **Update Type:** 🟢 **PATCH** (low complexity)
  - **Update Description:** Patch version update: 2.1.0 → 2.1.1
  - **⚠️ Breaking Changes Detected:**
    - - No breaking changes to existing workflows

---

**Full Changelog**: https://github.com/nachtschatt3n/ai-sre/compare/v2.1.0...v2.1.1
  - **Source:** https://github.com/nachtschatt3n/ai-sre/releases/tag/2.1.1
  - **Release Date:** 2025-10-18
  - **Release Notes:**
    ```markdown
    ## What's New

This release adds modern development tooling and AI capabilities to the AI-SRE container.

### New Features

**mise Runtime Manager**
- Installed mise for flexible runtime version management
- Provides foundation for managing multiple tool versions

**Node.js 18 LTS**
- Added Node.js 18 LTS support via mise
- Enables JavaScript/TypeScript tooling and npm packages
- Includes npm for package management

**Claude CLI**
- Installed @anthropics/claude-code globally
- Enables AI-assisted operations within the container
- Supports enhanced automation workflows

### Technical Details

- **Builder Stage Changes:**
  - Install mise via curl installer
  - Configure mise with global Node.js 18 installation
  - Install Claude CLI globally via npm

- **Runtime Stage Changes:**
  - Copy mise binaries and Node.js runtime to runtime stage
  - Update PATH to include Node.js binaries
  - Set MISE_DATA_DIR and MISE_CACHE_DIR environment variables

- **Container Size:** Minimal impact on image size due to multi-stage build optimization

### Version

- **Image Version:** 2.1.1
- **Base Image:** Alpine 3.20
- **Node.js Version:** 18 (LTS)

### Compatibility

- All existing MCP tools remain functional
- Backward compatible with v2.1.0
- No breaking changes to existing workflows

---

**Full Changelog**: https://github.com/nachtschatt3n/ai-sre/compare/v2.1.0...v2.1.1
    ```
  - **⚠️ Breaking Changes:**
    - - No breaking changes to existing workflows
    - ---
    - **Full Changelog**: https://github.com/nachtschatt3n/ai-sre/compare/v2.1.0...v2.1.1

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
- **Current Version:** `1.39.2`
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
- **Latest Version:** `4.14.2` ⚠️ **UPDATE AVAILABLE**
- **Update Type:** 🟢 **PATCH** (low complexity)
- **Update Description:** Patch version update: 4.14.1 → 4.14.2
- **Source:** https://github.com/kubernetes/ingress-nginx/releases/tag/4.14.2
- **Release Notes:** *Could not fetch release notes (GitHub API rate limit or release not found). Check source link above.*
- **⚠️ Breaking Changes:** *Patch updates typically don't have breaking changes - see release notes above*

*No container images specified in values*

---

### fluent-bit

- **File:** `kubernetes/apps/monitoring/fluent-bit/app/helmrelease.yaml`

#### Chart
- **Name:** `fluent-bit`
- **Repository:** `fluent`
- **Current Version:** `0.54.1`
- **Latest Version:** `0.55.0` ⚠️ **UPDATE AVAILABLE**
- **Update Type:** 🟡 **MINOR** (medium complexity)
- **Update Description:** Minor version update: 0.54.x → 0.55.x
- **Source:** https://github.com/fluent/helm-charts/releases/tag/0.55.0
- **Release Notes:** *Could not fetch release notes (GitHub API rate limit or release not found). Check source link above.*
- **⚠️ Breaking Changes:** *Review release notes above for potential breaking changes*

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
- **Latest Version:** `10.5.14` ⚠️ **UPDATE AVAILABLE**
- **Update Type:** 🟢 **PATCH** (low complexity)
- **Update Description:** Patch version update: 10.5.8 → 10.5.14
- **Source:** https://github.com/grafana/helm-charts/releases/tag/10.5.14
- **Release Notes:** *Could not fetch release notes (GitHub API rate limit or release not found). Check source link above.*
- **⚠️ Breaking Changes:** *Patch updates typically don't have breaking changes - see release notes above*

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
  - **Current Tag:** `v1.9.0`
  - **Latest Tag:** `1.9.0` ⚠️ **UPDATE AVAILABLE**
  - **Update Type:** ⚪ **UNKNOWN** (unknown complexity)
  - **Update Description:** Versions appear equal or downgrade detected
  - **⚠️ Breaking Changes Detected:**
    - * Enhancement: support netalertx v26.1.17 breaking changes by @shamoon in https://github.com/gethomepage/homepage/pull/6196
* Enhancement: booklore service widget by @shamoon in https://github.com/gethomepage/homepage/pull/6202

## New Contributors
* @camhorn made their first contribution in https://github.com/gethomepage/homepage/pull/6126
  - **Source:** https://github.com/gethomepage/homepage/releases/tag/1.9.0
  - **Release Date:** 2026-01-19
  - **Release Notes:**
    ```markdown
    ## What's Changed
* Enhancement: refactor UptimeRobot widget by @shamoon in https://github.com/gethomepage/homepage/pull/6088
* Fix: retrieve stats from all network interfaces by @shamoon in https://github.com/gethomepage/homepage/pull/6102
* Enhancement: fully support custom headers by @shamoon in https://github.com/gethomepage/homepage/pull/6125
* Fix: prevent cache collision with multiple plex widgets by @camhorn in https://github.com/gethomepage/homepage/pull/6126
* Enhancement: include prefix length when displaying ipv6 prefix by @I-am-not-a-number in https://github.com/gethomepage/homepage/pull/6130
* Fix: ensure minimum gap for resource widget items by @DocBrown101 in https://github.com/gethomepage/homepage/pull/6137
* Fix: support latest homebridge status labels by @shamoon in https://github.com/gethomepage/homepage/pull/6139
* Enhancement: Add support for Pyload-ng 0.5.0 CSRF-protected API by @shamoon in https://github.com/gethomepage/homepage/pull/6142
* Fix: fix default configured service weight = 0 by @faeibson in https://github.com/gethomepage/homepage/pull/6151
* Fix: correct month handling for Wallos widget by @JanGrosse in https://github.com/gethomepage/homepage/pull/6150
* Tweak: skip chown operations when running as root by @shamoon in https://github.com/gethomepage/homepage/pull/6170
* Enhancement: TrueNAS widget web socket API support by @shamoon in https://github.com/gethomepage/homepage/pull/6161
* Enhancement: support netalertx v26.1.17 breaking changes by @shamoon in https://github.com/gethomepage/homepage/pull/6196
* Enhancement: booklore service widget by @shamoon in https://github.com/gethomepage/homepage/pull/6202

## New Contributors
* @camhorn made their first contribution in https://github.com/gethomepage/homepage/pull/6126
* @I-am-not-a-number made their first contribution in https://github.com/gethomepage/homepage/pull/6130
* @DocBrown101 made their first contribution in https://github.com/gethomepage/homepage/pull/6137
* @faeibson made their first contribution in https://github.com/gethomepage/homepage/pull/6151
* @JanGrosse made their first contribution in https://github.com/gethomepage/homepage/pull/6150

**Full Changelog**: https://github.com/gethomepage/homepage/compare/v1.8.0...v1.9.0
    ```
  - **⚠️ Breaking Changes:**
    - * Enhancement: support netalertx v26.1.17 breaking changes by @shamoon in https://github.com/gethomepage/homepage/pull/6196
    - * Enhancement: booklore service widget by @shamoon in https://github.com/gethomepage/homepage/pull/6202
    - ## New Contributors
    - * @camhorn made their first contribution in https://github.com/gethomepage/homepage/pull/6126

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
- **Latest Version:** `4.14.2` ⚠️ **UPDATE AVAILABLE**
- **Update Type:** 🟢 **PATCH** (low complexity)
- **Update Description:** Patch version update: 4.14.1 → 4.14.2
- **Source:** https://github.com/kubernetes/ingress-nginx/releases/tag/4.14.2
- **Release Notes:** *Could not fetch release notes (GitHub API rate limit or release not found). Check source link above.*
- **⚠️ Breaking Changes:** *Patch updates typically don't have breaking changes - see release notes above*

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
- **Current Version:** `68.5.0`
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
  - **Latest Tag:** `0.0.19` ⚠️ **UPDATE AVAILABLE**
  - **Update Type:** ⚪ **UNKNOWN** (unknown complexity)
  - **Update Description:** Version format not recognized
  - **Source:** https://github.com/open-webui/mcpo/releases/tag/0.0.19
  - **Release Date:** 2025-10-14
  - **Release Notes:**
    ```markdown
    ## [0.0.19] - 2025-10-14

### Fixed

* 🔁 **Reverted Client Header Forwarding**: Reverted changes introduced in 0.0.18.
    ```

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
- **Current Version:** `6.6.10`
- **Latest Version:** `8.9.0` ⚠️ **UPDATE AVAILABLE**
- **Update Type:** 🔴 **MAJOR** (high complexity)
- **Update Description:** Major version update: 6.x.x → 8.x.x
- **Source:** https://github.com/nextcloud/helm/releases/tag/8.9.0
- **Release Notes:** *Could not fetch release notes (GitHub API rate limit or release not found). Check source link above.*
- **⚠️ Breaking Changes:** *Major version update - review release notes above for breaking changes*

#### Container Images
- **Repository:** `nextcloud`
  - **Path:** `image`
  - **Current Tag:** `32.0.5`
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
  - **Latest Tag:** `0.7.2` ✅ (up-to-date)

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
- **Current Version:** `1.3.0`
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
  - **Latest Tag:** `2026.1.2` ⚠️ **UPDATE AVAILABLE**
  - **Update Type:** 🔴 **MAJOR** (high complexity)
  - **Update Description:** Major version update: 2025.x.x → 2026.x.x
  - **⚠️ Breaking Changes Detected:**
    - Major version change typically indicates breaking changes
    - Major version update - breaking changes likely. Review full release notes for details.
  - **Source:** https://github.com/esphome/esphome/releases/tag/2026.1.2
  - **Release Date:** 2026-01-25
  - **Release Notes:**
    ```markdown
    - [st7701s] Fix dump_summary deprecation warning [esphome#13462](https://github.com/esphome/esphome/pull/13462) by [@bdraco](https://github.com/bdraco)
- [mipi_rgb] Fix dump_summary deprecation warning [esphome#13463](https://github.com/esphome/esphome/pull/13463) by [@bdraco](https://github.com/bdraco)
- [rpi_dpi_rgb] Fix dump_summary deprecation warning [esphome#13461](https://github.com/esphome/esphome/pull/13461) by [@bdraco](https://github.com/bdraco)
- [ir_rf_proxy] Remove unnecessary headers, add tests [esphome#13464](https://github.com/esphome/esphome/pull/13464) by [@kbx81](https://github.com/kbx81)
- [mipi_rgb] Add software reset command to st7701s init sequence [esphome#13470](https://github.com/esphome/esphome/pull/13470) by [@clydebarrow](https://github.com/clydebarrow)
- [slow_pwm] Fix dump_summary deprecation warning [esphome#13460](https://github.com/esphome/esphome/pull/13460) by [@bdraco](https://github.com/bdraco)
- [sen5x] Fix store baseline functionality [esphome#13469](https://github.com/esphome/esphome/pull/13469) by [@mikelawrence](https://github.com/mikelawrence)
- [lvgl] Fix setting empty text [esphome#13494](https://github.com/esphome/esphome/pull/13494) by [@clydebarrow](https://github.com/clydebarrow)
- [light] Fix cwww state restore [esphome#13493](https://github.com/esphome/esphome/pull/13493) by [@kbx81](https://github.com/kbx81)
- [rd03d] Fix speed and resolution field order [esphome#13495](https://github.com/esphome/esphome/pull/13495) by [@jasstrong](https://github.com/jasstrong)
- [modbus_controller] Fix YAML serialization error with custom_command [esphome#13482](https://github.com/esphome/esphome/pull/13482) by [@swoboda1337](https://github.com/swoboda1337)
- [i2c] Increase ESP-IDF I2C transaction timeout from 20ms to 100ms [esphome#13483](https://github.com/esphome/esphome/pull/13483) by [@swoboda1337](https://github.com/swoboda1337)
- [wifi] Fix watchdog timeout on P4 WiFi scan [esphome#13520](https://github.com/esphome/esphome/pull/13520) by [@clydebarrow](https://github.com/clydebarrow)
- [wifi] Fix scan flag race condition causing reconnect failure on ESP8266/LibreTiny [esphome#13514](https://github.com/esphome/esphome/pull/13514) by [@bdraco](https://github.com/bdraco)
    ```
  - **⚠️ Breaking Changes:** *Major version update - review release notes above*

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
  - **Latest Tag:** `0.16.4` ⚠️ **UPDATE AVAILABLE**
  - **Update Type:** 🟢 **PATCH** (low complexity)
  - **Update Description:** Patch version update: 0.16.3 → 0.16.4
  - **Source:** https://github.com/blakeblackshear/frigate/releases/tag/0.16.4
  - **Release Date:** 2026-01-29
  - **Release Notes:**
    ```markdown
    ## Images

- [ghcr.io/blakeblackshear/frigate:0.16.4](https://github.com/blakeblackshear/frigate/pkgs/container/frigate/660761432?tag=0.16.4)
- [ghcr.io/blakeblackshear/frigate:0.16.4-standard-arm64](https://github.com/blakeblackshear/frigate/pkgs/container/frigate/660757850?tag=0.16.4-standard-arm64)
- [ghcr.io/blakeblackshear/frigate:0.16.4-tensorrt](https://github.com/blakeblackshear/frigate/pkgs/container/frigate/660772919?tag=0.16.4-tensorrt)
- [ghcr.io/blakeblackshear/frigate:0.16.4-rk](https://github.com/blakeblackshear/frigate/pkgs/container/frigate/660781033?tag=0.16.4-rk)
- [ghcr.io/blakeblackshear/frigate:0.16.4-rocm](https://github.com/blakeblackshear/frigate/pkgs/container/frigate/660792419?tag=0.16.4-rocm)
- [ghcr.io/blakeblackshear/frigate:0.16.4-tensorrt-jp6](https://github.com/blakeblackshear/frigate/pkgs/container/frigate/661068168?tag=0.16.4-tensorrt-jp6)

## Security Advisory
A security vulnerability was reported and addressed with this release. Exploiting this vulnerability requires authenticated access to Frigate.

- [Authenticated Remote Command Execution (RCE) and Container Escape](https://github.com/blakeblackshear/frigate/security/advisories/GHSA-4c97-5jmr-8f6x)

## What's Changed
* docs: fix the missing quotes in the Reolink example within the docume… by @ZhaiSoul in https://github.com/blakeblackshear/frigate/pull/21178
* Update camera_specific.md for Wyze Cameras (Thingino) by @User873902 in https://github.com/blakeblackshear/frigate/pull/21221
* docs: update OpenVINO D-FINE configuration default device by @ZhaiSoul in https://github.com/blakeblackshear/frigate/pull/21231
* Update Hikvision camera link in hardware documentation by @NickM-27 in https://github.com/blakeblackshear/frigate/pull/21256
* update copyright by @blakeblackshear in https://github.com/blakeblackshear/frigate/pull/21485
* Port go2rtc check by @blakeblackshear in https://github.com/blakeblackshear/frigate/pull/21808

## New Contributors
* @User873902 made their first contribution in https://github.com/blakeblackshear/frigate/pull/21221

**Full Changelog**: https://github.com/blakeblackshear/frigate/compare/v0.16.3...v0.16.4
    ```

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
  - **Current Tag:** `2026.1.3`
  - **Latest Tag:** `2026.1.3` ✅ (up-to-date)

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
  - **Current Tag:** `2.0.22`
  - **Latest Tag:** *Could not determine*

- **Repository:** `sapcc/mosquitto-exporter`
  - **Path:** `controllers.mosquitto.containers.exporter.image`
  - **Current Tag:** `0.8.0`
  - **Latest Tag:** `0.8.0` ✅ (up-to-date)

- **Repository:** `public.ecr.aws/docker/library/eclipse-mosquitto`
  - **Path:** `controllers.mosquitto.initContainers.init-config.image`
  - **Current Tag:** `2.0.22`
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
  - **Latest Tag:** `2.7.5` ✅ (up-to-date)

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
- **Current Version:** `1.1.0`
- **Latest Version:** *Could not determine*

#### Container Images
- **Repository:** `n8nio/n8n`
  - **Path:** `image`
  - **Current Tag:** `1.123.17`
  - **Latest Tag:** `2.6.2` ⚠️ **UPDATE AVAILABLE**
  - **Update Type:** 🔴 **MAJOR** (high complexity)
  - **Update Description:** Major version update: 1.x.x → 2.x.x
  - **⚠️ Breaking Changes Detected:**
    - Major version change typically indicates breaking changes
  - **Source:** https://github.com/n8nio/n8n/releases/tag/2.6.2
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
  - **Latest Tag:** `4.1.4` ⚠️ **UPDATE AVAILABLE**
  - **Update Type:** 🟢 **PATCH** (low complexity)
  - **Update Description:** Patch version update: 4.1.3 → 4.1.4
  - **Source:** https://github.com/nodered/node-red/releases/tag/4.1.4
  - **Release Notes:** *Could not fetch release notes (GitHub API rate limit or release not found). Check source link above.*

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
  - **Current Tag:** `10.11.6`
  - **Latest Tag:** `10.11.6` ✅ (up-to-date)

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
  - **Latest Tag:** `2.25.0` ⚠️ **UPDATE AVAILABLE**
  - **Update Type:** 🟡 **MINOR** (medium complexity)
  - **Update Description:** Minor version update: 2.21.x → 2.25.x
  - **Source:** https://github.com/unpoller/unpoller/releases/tag/2.25.0
  - **Release Date:** 2026-01-28
  - **Release Notes:**
    ```markdown
    ## Changelog
* d26d84e8ade1867eb74e1934c4bb023460ebe4d7 Merge pull request #923 from unpoller/issue-921
* 5e68016564888479044c9489cd4505bc459469e6 fix client side log error
* a14d5c4150497bc882c10bebcfb4577a129b35ab Merge pull request #922 from brngates98/add-ai-context-files
* 969445fadec99dfbbb9b924dd5a6ac8fb74b5dd5 Add AI context files for major LLMs
    ```

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

### andreamosteller

- **File:** `kubernetes/apps/my-software-development/andreamosteller/app/helmrelease.yaml`

#### Chart
- **Name:** `app-template`
- **Repository:** `bjw-s`
- **Current Version:** `3.7.1`
- **Latest Version:** *Could not determine*

#### Container Images
- **Repository:** `ghcr.io/nachtschatt3n/andreamosteller.com`
  - **Path:** `controllers.andreamosteller.containers.app.image`
  - **Current Tag:** `sha-394fe9f`
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

### andreamosteller

- **File:** `kubernetes/apps/my-software-production/andreamosteller/app/helmrelease.yaml`

#### Chart
- **Name:** `app-template`
- **Repository:** `bjw-s`
- **Current Version:** `3.7.1`
- **Latest Version:** *Could not determine*

#### Container Images
- **Repository:** `ghcr.io/nachtschatt3n/andreamosteller.com`
  - **Path:** `controllers.andreamosteller.containers.app.image`
  - **Current Tag:** `5d88656-unprivileged-v2`
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
  - **Current Tag:** `2.20.5`
  - **Latest Tag:** `2.20.5` ✅ (up-to-date)

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
- **Latest Version:** `1.11.0` ⚠️ **UPDATE AVAILABLE**
- **Update Type:** 🟡 **MINOR** (medium complexity)
- **Update Description:** Minor version update: 1.10.x → 1.11.x
- **Source:** https://github.com/longhorn/longhorn/releases/tag/1.11.0
- **Release Date:** 2026-01-29
- **Release Notes:**
  ```markdown
  # Longhorn v1.11.0 Release Notes

The Longhorn team is excited to announce the release of Longhorn v1.11.0. This release marks a major milestone, with the **V2 Data Engine** officially entering the **Technical Preview** stage following significant stability improvements.

Additionally, this version optimizes the stability of the whole system and introduces critical improvements in resource observability, scheduling, and utilization.

For terminology and background on Longhorn releases, see [Releases](https://github.com/longhorn/longhorn#releases).

## Deprecation

### V2 Backing Image Deprecation

The Backing Image feature for the V2 Data Engine is now deprecated in v1.11.0 and is scheduled for removal in v1.12.0.

Users using V2 volumes for virtual machines are encouraged to adopt the [Containerized Data Importer (CDI)](https://kubevirt.io/user-guide/operations/containerized_data_importer/) for volume population instead.

[GitHub Issue #12237](https://github.com/longhorn/longhorn/issues/12237)

## Primary Highlights

### V2 Data Engine

#### Now in Technical Preview Stage

We are pleased to announce that the V2 Data Engine has officially graduated to the **Technical Preview** stage. This indicates increased stability and feature maturity as we move toward General Availability.

> **Limitation:** While the engine is in Technical Preview, live upgrade is not supported yet. V2 volumes must be detached (offline) before engine upgrade.

#### Support for `ublk` Frontend

Users can now configure `ublk` (Userspace Block Device) as the frontend for V2 Data Engine volumes. This provides a high-performance alternative to the NVMe-oF frontend for environments running Kernel v6.0+.

[GitHub Issue #11039](https://github.com/longhorn/longhorn/issues/11039)

### V1 Data Engine

#### Faster Replica Rebuilding from Multiple Sources

The V1 Data Engine now supports parallel rebuilding. When a replica needs to be rebuilt, the engine can now stream data from multiple healthy replicas simultaneously rather than a single source. This significantly reduces the time required to restore redundancy for volumes containing tons of scattered data chunks.

[GitHub Issue #11331](https://www.google.com/search?q=https://github.com/longhorn/longhorn/issues/11331)

### General

#### Balance-Aware Algorithm Disk Selection For Replica Scheduling

Longhorn improves the disk selection for the replica scheduling by introducing an intelligent `balance-aware` scheduling algorithm, reducing uneven storage usage across nodes and disks.

[GitHub Issue #10512](https://github.com/longhorn/longhorn/issues/10512)

#### Node Disk Health Monitoring

Longhorn now actively monitors the physical health of the underlying disks used for storage by using S.M.A.R.T. data. This allows administrators to identify issues and raise alerts when abnormal SMART metrics are detected, helping prevent failed volumes.

[GitHub Issue #12016](https://github.com/lo
  ... (truncated, see source link above for full notes)
  ```
- **⚠️ Breaking Changes:**
  - Migration/Upgrade Guide:
  - > [!IMPORTANT]
  - **Ensure that your cluster is running Kubernetes v1.25 or later before upgrading from Longhorn v1.10.x to v1.11.0.**
  - Longhorn only allows upgrades from supported versions. For more information about upgrade paths and procedures, see [Upgrade](https://longhorn.io/docs/1.11.0/deploy/upgrade/) in the Longhorn documentation.

*No container images specified in values*

---
