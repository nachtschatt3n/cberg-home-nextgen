# Kubernetes Deployment Version Status

**Generated:** 2026-02-22 14:09:38

> **Note:** Release notes are fetched from GitHub API. If rate limited, some release notes may not be available. Check source links for full details.

## Summary

- **Total Deployments:** 70
- **Chart Updates Available:** 4
- **Image Updates Available:** 10
- **Update Breakdown:** 🔴 2 major | 🟡 2 minor | 🟢 5 patch
- **⚠️ Breaking Changes Detected:** 4 updates with potential breaking changes

---

## Quick Overview Table

| Deployment | Namespace | Chart | Image | App | Complexity |
|------------|-----------|-------|-------|-----|------------|
| `icloud-docker-mu` | `backup` | 3.7.3 ? | latest ✅ | - | - |
| `influxdb` | `databases` | 2.1.2 ✅ | 2.8.0-alpine → 2.8.0 | 2.8.0-alpine | ⚪ UNKNOWN |
| `mariadb` | `databases` | 11.5.7 → 25.0.0 | latest ✅ | - | 🔴 MAJOR |
| `nocodb` | `databases` | 3.7.3 ? | latest ✅ | - | - |
| `phpmyadmin` | `databases` | 3.7.3 ? | latest ✅ | - | - |
| `actual-budget` | `default` | 3.7.3 ? | latest ✅ | - | - |
| `ai-sre` | `default` | 3.7.3 ? | 2.1.0 → 2.1.1 | 2.1.0 | 🟢 PATCH |
| `cert-manager` | `default` | v1.19.3 ✅ | - | - | - |
| `cilium` | `default` | 1.18.6 → 1.19.1 | - | - | 🟡 MINOR |
| `cloudflared` | `default` | 3.7.3 ? | 2026.2.0 ✅ | 2026.2.0 | - |
| `coredns` | `default` | 1.45.2 ? | - | - | - |
| `descheduler` | `default` | 0.35.0 ✅ | - | - | - |
| `echo-server` | `default` | 3.7.3 ? | 35 ? | 35 | - |
| `external-dns` | `default` | 1.20.0 ✅ | - | - | - |
| `external-ingress-nginx` | `default` | 4.14.3 ✅ | - | - | - |
| `fluent-bit` | `default` | 0.55.0 ✅ | 4.2.2 ? | 4.2.2 | - |
| `flux-instance` | `default` | 0.14.0 ? | - | - | - |
| `flux-operator` | `default` | 0.14.0 ? | - | - | - |
| `grafana` | `default` | 10.5.15 ✅ | - | - | - |
| `homepage` | `default` | 2.1.0 ✅ | v1.10.1 → 1.10.1 | v1.10.1 | ⚪ UNKNOWN |
| `intel-device-plugin-gpu` | `default` | 0.35.0 ✅ | - | - | - |
| `intel-device-plugin-operator` | `default` | 0.35.0 ✅ | - | - | - |
| `internal-ingress-nginx` | `default` | 4.14.3 ✅ | - | - | - |
| `jdownloader` | `default` | 3.7.3 ? | v26.02.2 ✅ | v26.02.2 | - |
| `k8s-gateway` | `default` | 2.4.0 ✅ | - | - | - |
| `kube-prometheus-stack` | `default` | 81.6.9 ? | - | - | - |
| `mcpo` | `default` | 3.7.3 ? | git-44ce6d0 → 0.0.19 | git-44ce6d0 | ⚪ UNKNOWN |
| `metrics-server` | `default` | 3.13.0 ✅ | - | - | - |
| `nextcloud` | `default` | 6.6.10 → 8.9.1 | 32.0.6 ? | 32.0.6 | 🔴 MAJOR |
| `node-feature-discovery` | `default` | 0.18.3 ✅ | - | - | - |
| `omni-tools` | `default` | 3.7.3 ? | 0.6.0 ✅ | 0.6.0 | - |
| `open-webui` | `default` | 12.3.0 ✅ | 0.8.3 ✅ | 0.8.3 | - |
| `openclaw` | `default` | 3.7.3 ? | 22-bookworm ? | 22-bookworm | - |
| `opencode-PROJECT_NAME` | `default` | 3.7.3 ? | latest ✅ | - | - |
| `opencode-andreamosteller` | `default` | 3.7.3 ? | sha-4d4c614 ? | sha-4d4c614 | - |
| `paperless-ai` | `default` | 3.7.3 ? | latest ✅ | - | - |
| `paperless-gpt` | `default` | 3.7.3 ? | latest ✅ | - | - |
| `redis` | `default` | 3.7.3 ? | 7-alpine ? | 7-alpine | - |
| `reloader` | `default` | 1.3.0 ? | - | - | - |
| `spegel` | `default` | v0.0.30 ? | - | - | - |
| `teslamate` | `default` | 3.7.3 ? | 2.2.0 ✅ | 2.2.0 | - |
| `tube-archivist` | `default` | 3.7.3 ? | v0.5.9 ✅ | v0.5.9 | - |
| `vaultwarden` | `default` | 3.7.3 ? | 1.35.3 ✅ | 1.35.3 | - |
| `esphome` | `home-automation` | 3.7.3 ? | 2026.2.1 ✅ | 2026.2.1 | - |
| `frigate` | `home-automation` | 7.8.0 ✅ | 0.16.4 ✅ | 0.16.4 | - |
| `home-assistant` | `home-automation` | 3.7.3 ? | 2026.2.1 → 2026.2.3 | 2026.2.1 | 🟢 PATCH |
| `mosquitto` | `home-automation` | 3.7.3 ? | 2.0.22 ? | 2.0.22 | - |
| `mqttx-web` | `home-automation` | 3.7.3 ? | latest ✅ | - | - |
| `music-assistant-server` | `home-automation` | 3.7.3 ? | 2.7.6 → 2.7.8 | 2.7.6 | 🟢 PATCH |
| `n8n` | `home-automation` | 2.0.1 ? | 2.9.1 ✅ | 2.9.1 | - |
| `node-red` | `home-automation` | 3.7.3 ? | 4.1.5 ✅ | 4.1.5 | - |
| `scrypted` | `home-automation` | 3.7.3 ? | latest ✅ | - | - |
| `zigbee2mqtt` | `home-automation` | 3.7.3 ? | 2.8.0 ✅ | 2.8.0 | - |
| `authentik` | `kube-system` | 2025.12.4 ✅ | - | - | - |
| `csi-driver-smb` | `kube-system` | 1.20.0 ✅ | - | - | - |
| `jellyfin` | `media` | 2.7.0 ✅ | 10.11.6 ✅ | 10.11.6 | - |
| `makemkv` | `media` | 3.7.3 ? | latest ✅ | - | - |
| `plex` | `media` | 1.4.0 ✅ | 1.42.1.10060-4e8b05daf → latest | 1.42.1.10060-4e8b05daf | ⚪ UNKNOWN |
| `eck-operator` | `monitoring` | 3.3.0 ✅ | - | - | - |
| `headlamp` | `monitoring` | 0.40.0 ✅ | - | - | - |
| `unpoller` | `monitoring` | 2.1.0 ✅ | v2.34.0 → 2.34.0 | v2.34.0 | ⚪ UNKNOWN |
| `uptime-kuma` | `monitoring` | 4.0.0 ✅ | 2.1.1 → 2.1.3 | 2.1.1 | 🟢 PATCH |
| `absenty` | `my-software-development` | 3.7.3 ? | sha-ff3910e-dev ? | sha-ff3910e-dev | - |
| `andreamosteller` | `my-software-development` | 3.7.3 ? | sha-394fe9f ? | sha-394fe9f | - |
| `absenty` | `my-software-production` | 3.7.3 ? | sha-ffa072a ? | sha-ffa072a | - |
| `andreamosteller` | `my-software-production` | 3.7.3 ? | 5d88656-unprivileged-v2 ? | 5d88656-unprivileged-v2 | - |
| `adguard-home` | `network` | 0.24.0 ✅ | v0.107.72 ✅ | v0.107.72 | - |
| `paperless-ngx` | `office` | 0.24.1 ✅ | 2.20.7 → 2.20.8 | 2.20.7 | 🟢 PATCH |
| `penpot` | `office` | 0.35.0 ✅ | - | - | - |
| `longhorn` | `storage` | 1.10.1 → 1.11.0 | - | - | 🟡 MINOR |

---

## Namespace: `backup`

### icloud-docker-mu

- **File:** `kubernetes/apps/backup/icloud-docker-mu/app/helmrelease.yaml`

#### Chart
- **Name:** `app-template`
- **Repository:** `bjw-s`
- **Current Version:** `3.7.3`
- **Latest Version:** *Could not determine*

#### Container Images
- **Repository:** `mandarons/icloud-drive`
  - **Path:** `controllers.main.containers.app.image`
  - **Current Tag:** `latest`
  - **Latest Tag:** `1.24.0` ✅ (up-to-date)

---

## Namespace: `databases`

### influxdb

- **File:** `kubernetes/apps/databases/influxdb/app/helmrelease.yaml`

#### Chart
- **Name:** `influxdb2`
- **Repository:** `influxdata`
- **Current Version:** `2.1.2`
- **Latest Version:** `2.1.2` ✅ (up-to-date)

#### Container Images
- **Repository:** `docker.io/library/influxdb`
  - **Path:** `image`
  - **Current Tag:** `2.8.0-alpine`
  - **Latest Tag:** `2.8.0` ⚠️ **UPDATE AVAILABLE**
  - **Update Type:** ⚪ **UNKNOWN** (unknown complexity)
  - **Update Description:** Versions appear equal or downgrade detected
  - **Source:** https://github.com/docker.io/influxdb/releases/tag/2.8.0
  - **Release Notes:** *Could not fetch release notes (GitHub API rate limit or release not found). Check source link above.*

---

### mariadb

- **File:** `kubernetes/apps/databases/mariadb/app/helmrelease.yaml`

#### Chart
- **Name:** `mariadb`
- **Repository:** `bitnami`
- **Current Version:** `11.5.7`
- **Latest Version:** `25.0.0` ⚠️ **UPDATE AVAILABLE**
- **Update Type:** 🔴 **MAJOR** (high complexity)
- **Update Description:** Major version update: 11.x.x → 25.x.x
- **Source:** https://github.com/mariadb/mariadb/releases/tag/25.0.0
- **Release Notes:** *Could not fetch release notes (GitHub API rate limit or release not found). Check source link above.*
- **⚠️ Breaking Changes:** *Major version update - review release notes above for breaking changes*

#### Container Images
- **Repository:** `bitnamilegacy/mariadb`
  - **Path:** `image`
  - **Current Tag:** `latest`
  - **Latest Tag:** `12.0.2` ✅ (up-to-date)

---

### nocodb

- **File:** `kubernetes/apps/databases/nocodb/app/helmrelease.yaml`

#### Chart
- **Name:** `app-template`
- **Repository:** `bjw-s`
- **Current Version:** `3.7.3`
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
- **Current Version:** `3.7.3`
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
- **Current Version:** `3.7.3`
- **Latest Version:** *Could not determine*

#### Container Images
- **Repository:** `actualbudget/actual-server`
  - **Path:** `controllers.main.containers.main.image`
  - **Current Tag:** `latest`
  - **Latest Tag:** `sha-31a027f-alpine` ✅ (up-to-date)

---

### ai-sre

- **File:** `kubernetes/apps/ai/ai-sre/app/helmrelease.yaml`

#### Chart
- **Name:** `app-template`
- **Repository:** `bjw-s`
- **Current Version:** `3.7.3`
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
- **Current Version:** `v1.19.3`
- **Latest Version:** `v1.19.3` ✅ (up-to-date)

*No container images specified in values*

---

### cilium

- **File:** `kubernetes/apps/kube-system/cilium/app/helmrelease.yaml`

#### Chart
- **Name:** `cilium`
- **Repository:** `cilium`
- **Current Version:** `1.18.6`
- **Latest Version:** `1.19.1` ⚠️ **UPDATE AVAILABLE**
- **Update Type:** 🟡 **MINOR** (medium complexity)
- **Update Description:** Minor version update: 1.18.x → 1.19.x
- **Source:** https://github.com/cilium/cilium/releases/tag/1.19.1
- **Release Date:** 2026-02-17
- **Release Notes:**
  ```markdown
  Summary of Changes
------------------

**Bugfixes:**
* clustermesh: fix CRD update permission for MCS-API CRD install (Backport PR cilium/cilium#44280, Upstream PR cilium/cilium#44224, @Preisschild)
* Fix panic during datapath reinitialization if DirectRouting device is required but missing (Backport PR cilium/cilium#44280, Upstream PR cilium/cilium#44219, @fristonio)
* helm: Fixed RBAC errors with `operator.enabled=false` by aligning cilium-tlsinterception-secrets Role/RoleBinding conditionals (Backport PR cilium/cilium#44280, Upstream PR cilium/cilium#44159, @puwun)
* Reduces rtnl_mutex contention on SR-IOV nodes by not requesting VF information in netlink RTM_GETLINK operations (Backport PR cilium/cilium#44280, Upstream PR cilium/cilium#43517, @pasteley)

**CI Changes:**
* ci: e2e: add `kernel` to workflow job names (Backport PR cilium/cilium#44127, Upstream PR cilium/cilium#44291, @smagnani96)
* gh: ariane: don't run cloud workflows for LVH kernel updates (Backport PR cilium/cilium#44147, Upstream PR cilium/cilium#44109, @julianwiedmann)
* gh: ariane: skip more workflows for LVH kernel updates (Backport PR cilium/cilium#44147, Upstream PR cilium/cilium#44115, @julianwiedmann)

**Misc Changes:**
* chore(deps): update all github action dependencies (v1.19) (cilium/cilium#44248, @cilium-renovate[bot])
* chore(deps): update all github action dependencies (v1.19) (cilium/cilium#44368, @cilium-renovate[bot])
* chore(deps): update all-dependencies (v1.19) (cilium/cilium#44363, @cilium-renovate[bot])
* chore(deps): update base-images (v1.19) (cilium/cilium#44247, @cilium-renovate[bot])
* chore(deps): update cilium/cilium-cli action to v0.19.1 (v1.19) (cilium/cilium#44343, @cilium-renovate[bot])
* chore(deps): update dependency cilium/cilium-cli to v0.19.1 (v1.19) (cilium/cilium#44400, @cilium-renovate[bot])
* chore(deps): update docker.io/library/busybox:1.37.0 docker digest to b3255e7 (v1.19) (cilium/cilium#44242, @cilium-renovate[bot])
* chore(deps): update docker.io/library/golang:1.25.7 docker digest to 85c0ab0 (v1.19) (cilium/cilium#44364, @cilium-renovate[bot])
* chore(deps): update gcr.io/distroless/static:nonroot docker digest to f9f84bd (v1.19) (cilium/cilium#44243, @cilium-renovate[bot])
* chore(deps): update gcr.io/etcd-development/etcd docker tag to v3.6.8 (v1.19) (cilium/cilium#44365, @cilium-renovate[bot])
* chore(deps): update module sigs.k8s.io/kube-api-linter to v0.0.0-20260206102632-39e3d06a2850 (v1.19) (cilium/cilium#44244, @cilium-renovate[bot])
* chore(deps): update quay.io/cilium/cilium-envoy docker tag to v1.35.9-1770265024-9828c064a10df81f1939b692b01203d88bb439e4 (v1.19) (cilium/cilium#44245, @cilium-renovate[bot])
* chore(deps): update quay.io/cilium/cilium-envoy docker tag to v1.35.9-1770554954-8ce3bb4eca04188f4a0a1bfbd0a06a40f90883de (v1.19) (cilium/cilium#44262, @cilium-renovate[bot])
* chore(deps): update quay.io/cilium/cilium-envoy docker tag to v1.35.9-1770979049-232ed4a26881e4ab4f766f251f258
  ... (truncated, see source link above for full notes)
  ```
- **⚠️ Breaking Changes:** *Review release notes above for potential breaking changes*

*No container images specified in values*

---

### cloudflared

- **File:** `kubernetes/apps/network/external/cloudflared/helmrelease.yaml`

#### Chart
- **Name:** `app-template`
- **Repository:** `bjw-s`
- **Current Version:** `3.7.3`
- **Latest Version:** *Could not determine*

#### Container Images
- **Repository:** `docker.io/cloudflare/cloudflared`
  - **Path:** `controllers.cloudflared.containers.app.image`
  - **Current Tag:** `2026.2.0`
  - **Latest Tag:** `2026.2.0` ✅ (up-to-date)

---

### coredns

- **File:** `kubernetes/apps/kube-system/coredns/app/helmrelease.yaml`

#### Chart
- **Name:** `coredns`
- **Repository:** `coredns`
- **Current Version:** `1.45.2`
- **Latest Version:** *Could not determine*

*No container images specified in values*

---

### descheduler

- **File:** `kubernetes/apps/kube-system/descheduler/app/helmrelease.yaml`

#### Chart
- **Name:** `descheduler`
- **Repository:** `descheduler`
- **Current Version:** `0.35.0`
- **Latest Version:** `0.35.0` ✅ (up-to-date)

*No container images specified in values*

---

### echo-server

- **File:** `kubernetes/apps/default/echo-server/app/helmrelease.yaml`

#### Chart
- **Name:** `app-template`
- **Repository:** `bjw-s`
- **Current Version:** `3.7.3`
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
- **Current Version:** `4.14.3`
- **Latest Version:** `4.14.3` ✅ (up-to-date)

*No container images specified in values*

---

### fluent-bit

- **File:** `kubernetes/apps/monitoring/fluent-bit/app/helmrelease.yaml`

#### Chart
- **Name:** `fluent-bit`
- **Repository:** `fluent`
- **Current Version:** `0.55.0`
- **Latest Version:** `0.55.0` ✅ (up-to-date)

#### Container Images
- **Repository:** `cr.fluentbit.io/fluent/fluent-bit`
  - **Path:** `image`
  - **Current Tag:** `4.2.2`
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
- **Current Version:** `10.5.15`
- **Latest Version:** `10.5.15` ✅ (up-to-date)

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
  - **Current Tag:** `v1.10.1`
  - **Latest Tag:** `1.10.1` ⚠️ **UPDATE AVAILABLE**
  - **Update Type:** ⚪ **UNKNOWN** (unknown complexity)
  - **Update Description:** Versions appear equal or downgrade detected
  - **Source:** https://github.com/gethomepage/homepage/releases/tag/1.10.1
  - **Release Date:** 2026-02-05
  - **Release Notes:**
    ```markdown
    ## What's Changed
* Chore: move to Zensical docs by @shamoon in https://github.com/gethomepage/homepage/pull/6279
* Enhancement: better display of Arcane widget errors by @shamoon in https://github.com/gethomepage/homepage/pull/6281


**Full Changelog**: https://github.com/gethomepage/homepage/compare/v1.10.0...v1.10.1
    ```

---

### intel-device-plugin-gpu

- **File:** `kubernetes/apps/kube-system/intel-device-plugin/gpu/helmrelease.yaml`

#### Chart
- **Name:** `intel-device-plugins-gpu`
- **Repository:** `intel`
- **Current Version:** `0.35.0`
- **Latest Version:** `0.35.0` ✅ (up-to-date)

*No container images specified in values*

---

### intel-device-plugin-operator

- **File:** `kubernetes/apps/kube-system/intel-device-plugin/app/helmrelease.yaml`

#### Chart
- **Name:** `intel-device-plugins-operator`
- **Repository:** `intel`
- **Current Version:** `0.35.0`
- **Latest Version:** `0.35.0` ✅ (up-to-date)

*No container images specified in values*

---

### internal-ingress-nginx

- **File:** `kubernetes/apps/network/internal/ingress-nginx/helmrelease.yaml`

#### Chart
- **Name:** `ingress-nginx`
- **Repository:** `ingress-nginx`
- **Current Version:** `4.14.3`
- **Latest Version:** `4.14.3` ✅ (up-to-date)

*No container images specified in values*

---

### jdownloader

- **File:** `kubernetes/apps/download/jdownloader/app/helmrelease.yaml`

#### Chart
- **Name:** `app-template`
- **Repository:** `bjw-s`
- **Current Version:** `3.7.3`
- **Latest Version:** *Could not determine*

#### Container Images
- **Repository:** `jlesage/jdownloader-2`
  - **Path:** `controllers.main.containers.app.image`
  - **Current Tag:** `v26.02.2`
  - **Latest Tag:** `v26.02.2` ✅ (up-to-date)

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
- **Current Version:** `81.6.9`
- **Latest Version:** *Could not determine*

*No container images specified in values*

---

### mcpo

- **File:** `kubernetes/apps/ai/mcpo/app/helmrelease.yaml`

#### Chart
- **Name:** `app-template`
- **Repository:** `bjw-s`
- **Current Version:** `3.7.3`
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
- **Latest Version:** `8.9.1` ⚠️ **UPDATE AVAILABLE**
- **Update Type:** 🔴 **MAJOR** (high complexity)
- **Update Description:** Major version update: 6.x.x → 8.x.x
- **Source:** https://github.com/nextcloud/helm/releases/tag/8.9.1
- **Release Notes:** *Could not fetch release notes (GitHub API rate limit or release not found). Check source link above.*
- **⚠️ Breaking Changes:** *Major version update - review release notes above for breaking changes*

#### Container Images
- **Repository:** `nextcloud`
  - **Path:** `image`
  - **Current Tag:** `32.0.6`
  - **Latest Tag:** *Could not determine*

- **Repository:** `bitnamilegacy/mariadb`
  - **Path:** `mariadb.image`
  - **Current Tag:** `latest`
  - **Latest Tag:** `12.0.2` ✅ (up-to-date)

- **Repository:** `xperimental/nextcloud-exporter`
  - **Path:** `metrics.image`
  - **Current Tag:** `0.9.0`
  - **Latest Tag:** `0.9.0` ✅ (up-to-date)

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
- **Current Version:** `3.7.3`
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
- **Current Version:** `12.3.0`
- **Latest Version:** `12.3.0` ✅ (up-to-date)

#### Container Images
- **Repository:** `ghcr.io/open-webui/open-webui`
  - **Path:** `image`
  - **Current Tag:** `0.8.3`
  - **Latest Tag:** `0.8.3` ✅ (up-to-date)

---

### openclaw

- **File:** `kubernetes/apps/ai/openclaw/app/helmrelease.yaml`

#### Chart
- **Name:** `app-template`
- **Repository:** `bjw-s`
- **Current Version:** `3.7.3`
- **Latest Version:** *Could not determine*

#### Container Images
- **Repository:** `node`
  - **Path:** `controllers.openclaw.containers.app.image`
  - **Current Tag:** `22-bookworm`
  - **Latest Tag:** *Could not determine*

- **Repository:** `node`
  - **Path:** `controllers.openclaw.initContainers.install-openclaw.image`
  - **Current Tag:** `22-bookworm`
  - **Latest Tag:** *Could not determine*

---

### opencode-PROJECT_NAME

- **File:** `kubernetes/apps/my-software-development/_template/app/helmrelease.yaml`

#### Chart
- **Name:** `app-template`
- **Repository:** `bjw-s`
- **Current Version:** `3.7.3`
- **Latest Version:** *Could not determine*

#### Container Images
- **Repository:** `ghcr.io/nachtschatt3n/opencode-web-devcontainer`
  - **Path:** `controllers.opencode-PROJECT_NAME.containers.opencode.image`
  - **Current Tag:** `latest`
  - **Latest Tag:** *Could not determine*

- **Repository:** `ghcr.io/nachtschatt3n/opencode-web-devcontainer`
  - **Path:** `controllers.opencode-PROJECT_NAME.containers.preview.image`
  - **Current Tag:** `latest`
  - **Latest Tag:** *Could not determine*

- **Repository:** `ghcr.io/nachtschatt3n/opencode-web-devcontainer`
  - **Path:** `controllers.opencode-PROJECT_NAME.initContainers.init-clone.image`
  - **Current Tag:** `latest`
  - **Latest Tag:** *Could not determine*

---

### opencode-andreamosteller

- **File:** `kubernetes/apps/my-software-development/opencode-andreamosteller/app/helmrelease.yaml`

#### Chart
- **Name:** `app-template`
- **Repository:** `bjw-s`
- **Current Version:** `3.7.3`
- **Latest Version:** *Could not determine*

#### Container Images
- **Repository:** `ghcr.io/nachtschatt3n/opencode-web-devcontainer`
  - **Path:** `controllers.opencode-andreamosteller.containers.opencode.image`
  - **Current Tag:** `sha-4d4c614`
  - **Latest Tag:** *Could not determine*

- **Repository:** `ghcr.io/nachtschatt3n/opencode-web-devcontainer`
  - **Path:** `controllers.opencode-andreamosteller.containers.preview.image`
  - **Current Tag:** `sha-4d4c614`
  - **Latest Tag:** *Could not determine*

- **Repository:** `ghcr.io/nachtschatt3n/opencode-web-devcontainer`
  - **Path:** `controllers.opencode-andreamosteller.initContainers.init-clone.image`
  - **Current Tag:** `sha-4d4c614`
  - **Latest Tag:** *Could not determine*

---

### paperless-ai

- **File:** `kubernetes/apps/office/paperless-ai/app/helmrelease.yaml`

#### Chart
- **Name:** `app-template`
- **Repository:** `bjw-s`
- **Current Version:** `3.7.3`
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
- **Current Version:** `3.7.3`
- **Latest Version:** *Could not determine*

#### Container Images
- **Repository:** `icereed/paperless-gpt`
  - **Path:** `controllers.main.containers.main.image`
  - **Current Tag:** `latest`
  - **Latest Tag:** `v0.25.0` ✅ (up-to-date)

---

### redis

- **File:** `kubernetes/apps/databases/redis/app/helmrelease.yaml`

#### Chart
- **Name:** `app-template`
- **Repository:** `bjw-s`
- **Current Version:** `3.7.3`
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
- **Current Version:** `3.7.3`
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
- **Current Version:** `3.7.3`
- **Latest Version:** *Could not determine*

#### Container Images
- **Repository:** `bbilly1/tubearchivist`
  - **Path:** `controllers.main.containers.app.image`
  - **Current Tag:** `v0.5.9`
  - **Latest Tag:** `v0.5.9` ✅ (up-to-date)

---

### vaultwarden

- **File:** `kubernetes/apps/office/vaultwarden/app/helmrelease.yaml`

#### Chart
- **Name:** `app-template`
- **Repository:** `bjw-s`
- **Current Version:** `3.7.3`
- **Latest Version:** *Could not determine*

#### Container Images
- **Repository:** `vaultwarden/server`
  - **Path:** `controllers.main.containers.main.image`
  - **Current Tag:** `1.35.3`
  - **Latest Tag:** `1.35.3` ✅ (up-to-date)

---

## Namespace: `home-automation`

### esphome

- **File:** `kubernetes/apps/home-automation/esphome/app/helmrelease.yaml`

#### Chart
- **Name:** `app-template`
- **Repository:** `bjw-s`
- **Current Version:** `3.7.3`
- **Latest Version:** *Could not determine*

#### Container Images
- **Repository:** `ghcr.io/esphome/esphome`
  - **Path:** `controllers.esphome.containers.app.image`
  - **Current Tag:** `2026.2.1`
  - **Latest Tag:** `2026.2.1` ✅ (up-to-date)

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
  - **Current Tag:** `0.16.4`
  - **Latest Tag:** `0.16.4` ✅ (up-to-date)

---

### home-assistant

- **File:** `kubernetes/apps/home-automation/home-assistant/app/helmrelease.yaml`

#### Chart
- **Name:** `app-template`
- **Repository:** `bjw-s`
- **Current Version:** `3.7.3`
- **Latest Version:** *Could not determine*

#### Container Images
- **Repository:** `ghcr.io/home-assistant/home-assistant`
  - **Path:** `controllers.home-assistant.containers.app.image`
  - **Current Tag:** `2026.2.1`
  - **Latest Tag:** `2026.2.3` ⚠️ **UPDATE AVAILABLE**
  - **Update Type:** 🟢 **PATCH** (low complexity)
  - **Update Description:** Patch version update: 2026.2.1 → 2026.2.3
  - **Source:** https://github.com/home-assistant/home-assistant/releases/tag/2026.2.3
  - **Release Date:** 2026-02-20
  - **Release Notes:**
    ```markdown
    - Add the ability to select region for Roborock ([@Lash-L] - [#160898]) ([roborock docs])
- Fix dynamic entity creation in eheimdigital ([@autinerd] - [#161155]) ([eheimdigital docs])
- Fix HomematicIP entity recovery after access point cloud reconnect ([@lackas] - [#162575]) ([homematicip_cloud docs])
- Show progress indicator during backup stage of Core/App update ([@hbludworth] - [#162683]) ([hassio docs])
- Fix Z-Wave climate set preset ([@MartinHjelmare] - [#162728]) ([zwave_js docs])
- Block redirect to localhost ([@edenhaus] - [#162941])
- Bump pypck to 0.9.10 ([@alengwenus] - [#162333]) ([lcn docs]) (dependency)
- Bump pypck to 0.9.11 ([@alengwenus] - [#163043]) ([lcn docs]) (dependency)
- Fix blocking call in Xbox config flow ([@tr4nt0r] - [#163122]) ([xbox docs])
- Bump ical to 13.2.0 ([@allenporter] - [#163123]) ([google docs]) ([local_calendar docs]) ([local_todo docs]) ([remote_calendar docs]) (dependency)
- Add Lux to homee units ([@Taraman17] - [#163180]) ([homee docs])
- Fix remote calendar event handling of events within the same update period ([@allenporter] - [#163186]) ([remote_calendar docs])
- Fix Control4 HVAC action mapping for multi-stage and idle states ([@davidrecordon] - [#163222]) ([control4 docs])
- NRGkick: do not update vehicle connected timestamp when vehicle is not connected ([@andijakl] - [#163292]) ([nrgkick docs])
- Add Miele dishwasher program code ([@astrandb] - [#163308]) ([miele docs])
- Bump pyrainbird to 6.0.5 ([@allenporter] - [#163333]) ([rainbird docs]) (dependency)
- Fix touchline_sl zone availability when alarm state is set ([@molsmadsen] - [#163338]) ([touchline_sl docs])
- Bump pySmartThings to 3.5.3 ([@joostlek] - [#163375]) ([smartthings docs])
- Fix hassfest requirements check ([@cdce8p] - [#163681])
- Bump eheimdigital to 1.6.0 ([@autinerd] - [#161961]) ([eheimdigital docs]) (dependency)

[#160898]: https://github.com/home-assistant/core/pull/160898
[#161155]: https://github.com/home-assistant/core/pull/161155
[#161961]: https://github.com/home-assistant/core/pull/161961
[#162224]: https://github.com/home-assistant/core/pull/162224
[#162333]: https://github.com/home-assistant/core/pull/162333
[#162450]: https://github.com/home-assistant/core/pull/162450
[#162575]: https://github.com/home-assistant/core/pull/162575
[#162683]: https://github.com/home-assistant/core/pull/162683
[#162728]: https://github.com/home-assistant/core/pull/162728
[#162941]: https://github.com/home-assistant/core/pull/162941
[#162950]: https://github.com/home-assistant/core/pull/162950
[#163043]: https://github.com/home-assistant/core/pull/163043
[#163122]: https://github.com/home-assistant/core/pull/163122
[#163123]: https://github.com/home-assistant/core/pull/163123
[#163180]: https://github.com/home-assistant/core/pull/163180
[#163186]: https://github.com/home-assistant/core/pull/163186
[#163222]: https://github.com/home-assistant/core/pull/163222
[#163292]: https://github.com/home
    ... (truncated, see source link above for full notes)
    ```

---

### mosquitto

- **File:** `kubernetes/apps/home-automation/mosquitto/app/helmrelease.yaml`

#### Chart
- **Name:** `app-template`
- **Repository:** `bjw-s`
- **Current Version:** `3.7.3`
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

### mqttx-web

- **File:** `kubernetes/apps/home-automation/mqttx-web/app/helmrelease.yaml`

#### Chart
- **Name:** `app-template`
- **Repository:** `bjw-s`
- **Current Version:** `3.7.3`
- **Latest Version:** *Could not determine*

#### Container Images
- **Repository:** `emqx/mqttx-web`
  - **Path:** `controllers.mqttx-web.containers.app.image`
  - **Current Tag:** `latest`
  - **Latest Tag:** `v1.13.0` ✅ (up-to-date)

---

### music-assistant-server

- **File:** `kubernetes/apps/home-automation/music-assistant-server/app/helmrelease.yaml`

#### Chart
- **Name:** `app-template`
- **Repository:** `bjw-s`
- **Current Version:** `3.7.3`
- **Latest Version:** *Could not determine*

#### Container Images
- **Repository:** `ghcr.io/music-assistant/server`
  - **Path:** `controllers.music-assistant-server.containers.app.image`
  - **Current Tag:** `2.7.6`
  - **Latest Tag:** `2.7.8` ⚠️ **UPDATE AVAILABLE**
  - **Update Type:** 🟢 **PATCH** (low complexity)
  - **Update Description:** Patch version update: 2.7.6 → 2.7.8
  - **Source:** https://github.com/music-assistant/server/releases/tag/2.7.8
  - **Release Date:** 2026-02-16
  - **Release Notes:**
    ```markdown
    ## 📦 Stable Release

_Changes since [2.7.7](https://github.com/music-assistant/server/releases/tag/2.7.7)_

### 🐛 Bugfixes

- Fix AttributeError when provider is temporarily unavailable (by @teancom in #3157)
- Fix HTTP proxy URL parsing for wss:// WebSocket URLs (by @chrisuthe in #3168)
- Auto cleanup cache db when it grows >= 2GB (by @MarvinSchenkel in #3174)

## :bow: Thanks to our contributors

Special thanks to the following contributors who helped with this release:

@MarvinSchenkel, @chrisuthe, @teancom
    ```

- **Repository:** `ghcr.io/alams154/music-assistant-alexa-api`
  - **Path:** `controllers.music-assistant-server.containers.alexa-api.image`
  - **Current Tag:** `latest`
  - **Latest Tag:** *Could not determine*

- **Repository:** `ghcr.io/alams154/music-assistant-skill`
  - **Path:** `controllers.music-assistant-server.containers.alexa-skill.image`
  - **Current Tag:** `latest`
  - **Latest Tag:** *Could not determine*

---

### n8n

- **File:** `kubernetes/apps/home-automation/n8n/app/helmrelease.yaml`

#### Chart
- **Name:** `n8n`
- **Repository:** `n8n`
- **Current Version:** `2.0.1`
- **Latest Version:** *Could not determine*

#### Container Images
- **Repository:** `n8nio/n8n`
  - **Path:** `image`
  - **Current Tag:** `2.9.1`
  - **Latest Tag:** `2.9.1` ✅ (up-to-date)

---

### node-red

- **File:** `kubernetes/apps/home-automation/node-red/app/helmrelease.yaml`

#### Chart
- **Name:** `app-template`
- **Repository:** `bjw-s`
- **Current Version:** `3.7.3`
- **Latest Version:** *Could not determine*

#### Container Images
- **Repository:** `nodered/node-red`
  - **Path:** `controllers.node-red.containers.app.image`
  - **Current Tag:** `4.1.5`
  - **Latest Tag:** `4.1.5` ✅ (up-to-date)

---

### scrypted

- **File:** `kubernetes/apps/home-automation/scrypted-nvr/app/helmrelease.yaml`

#### Chart
- **Name:** `app-template`
- **Repository:** `bjw-s`
- **Current Version:** `3.7.3`
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
- **Current Version:** `3.7.3`
- **Latest Version:** *Could not determine*

#### Container Images
- **Repository:** `koenkk/zigbee2mqtt`
  - **Path:** `controllers.zigbee2mqtt.containers.app.image`
  - **Current Tag:** `2.8.0`
  - **Latest Tag:** `2.8.0` ✅ (up-to-date)

---

## Namespace: `kube-system`

### authentik

- **File:** `kubernetes/apps/kube-system/authentik/app/helmrelease.yaml`

#### Chart
- **Name:** `authentik`
- **Repository:** `authentik`
- **Current Version:** `2025.12.4`
- **Latest Version:** `2025.12.4` ✅ (up-to-date)

*No container images specified in values*

---

### csi-driver-smb

- **File:** `kubernetes/apps/kube-system/csi-driver-smb/app/helmrelease.yaml`

#### Chart
- **Name:** `csi-driver-smb`
- **Repository:** `csi-driver-smb`
- **Current Version:** `1.20.0`
- **Latest Version:** `1.20.0` ✅ (up-to-date)

*No container images specified in values*

---

## Namespace: `media`

### jellyfin

- **File:** `kubernetes/apps/media/jellyfin/app/helmrelease.yaml`

#### Chart
- **Name:** `jellyfin`
- **Repository:** `jellyfin`
- **Current Version:** `2.7.0`
- **Latest Version:** `2.7.0` ✅ (up-to-date)

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
- **Current Version:** `3.7.3`
- **Latest Version:** *Could not determine*

#### Container Images
- **Repository:** `jlesage/makemkv`
  - **Path:** `image`
  - **Current Tag:** `latest`
  - **Latest Tag:** `v26.02.2` ✅ (up-to-date)

- **Repository:** `jlesage/makemkv`
  - **Path:** `controllers.main.containers.main.image`
  - **Current Tag:** `latest`
  - **Latest Tag:** `v26.02.2` ✅ (up-to-date)

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
- **Current Version:** `3.3.0`
- **Latest Version:** `3.3.0` ✅ (up-to-date)

*No container images specified in values*

---

### headlamp

- **File:** `kubernetes/apps/monitoring/headlamp/app/helmrelease.yaml`

#### Chart
- **Name:** `headlamp`
- **Repository:** `headlamp`
- **Current Version:** `0.40.0`
- **Latest Version:** `0.40.0` ✅ (up-to-date)

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
  - **Current Tag:** `v2.34.0`
  - **Latest Tag:** `2.34.0` ⚠️ **UPDATE AVAILABLE**
  - **Update Type:** ⚪ **UNKNOWN** (unknown complexity)
  - **Update Description:** Versions appear equal or downgrade detected
  - **Source:** https://github.com/unpoller/unpoller/releases/tag/2.34.0
  - **Release Date:** 2026-02-18
  - **Release Notes:**
    ```markdown
    ## Changelog
* 4bf5c1e6b5c1ce3c4f1a8c61b77b7cceeb1e37c3 build(deps): bump the all group with 2 updates (#955)
* 40e2a7703fa5dc8bc06a2e974412a79d49d38626 Fix panic when remote discovery fails and no controllers configured (fixes #953) (#957)
* eae3741120560d9ee22a27d1ad3ed248970caaeb build(deps): bump the all group with 2 updates (#950)
    ```

---

### uptime-kuma

- **File:** `kubernetes/apps/monitoring/uptime-kuma/app/helmrelease.yaml`

#### Chart
- **Name:** `uptime-kuma`
- **Repository:** `dirsigler`
- **Current Version:** `4.0.0`
- **Latest Version:** `4.0.0` ✅ (up-to-date)

#### Container Images
- **Repository:** `louislam/uptime-kuma`
  - **Path:** `image`
  - **Current Tag:** `2.1.1`
  - **Latest Tag:** `2.1.3` ⚠️ **UPDATE AVAILABLE**
  - **Update Type:** 🟢 **PATCH** (low complexity)
  - **Update Description:** Patch version update: 2.1.1 → 2.1.3
  - **Source:** https://github.com/louislam/uptime-kuma/releases/tag/2.1.3
  - **Release Date:** 2026-02-19
  - **Release Notes:**
    ```markdown
    ### 🐞 Bug Fixes
- #6981 fix: rdap data is not actually cached
    ```

---

## Namespace: `my-software-development`

### absenty

- **File:** `kubernetes/apps/my-software-development/absenty/app/helmrelease.yaml`

#### Chart
- **Name:** `app-template`
- **Repository:** `bjw-s`
- **Current Version:** `3.7.3`
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
- **Current Version:** `3.7.3`
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
- **Current Version:** `3.7.3`
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
- **Current Version:** `3.7.3`
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
- **Current Version:** `0.24.0`
- **Latest Version:** `0.24.0` ✅ (up-to-date)

#### Container Images
- **Repository:** `adguard/adguardhome`
  - **Path:** `image`
  - **Current Tag:** `v0.107.72`
  - **Latest Tag:** `v0.107.72` ✅ (up-to-date)

---

## Namespace: `office`

### paperless-ngx

- **File:** `kubernetes/apps/office/paperless-ngx/app/helmrelease.yaml`

#### Chart
- **Name:** `paperless-ngx`
- **Repository:** `gabe565`
- **Current Version:** `0.24.1`
- **Latest Version:** `0.24.1` ✅ (up-to-date)

#### Container Images
- **Repository:** `ghcr.io/paperless-ngx/paperless-ngx`
  - **Path:** `image`
  - **Current Tag:** `2.20.7`
  - **Latest Tag:** `2.20.8` ⚠️ **UPDATE AVAILABLE**
  - **Update Type:** 🟢 **PATCH** (low complexity)
  - **Update Description:** Patch version update: 2.20.7 → 2.20.8
  - **Source:** https://github.com/paperless-ngx/paperless-ngx/releases/tag/2.20.8
  - **Release Date:** 2026-02-22
  - **Release Notes:**
    ```markdown
    > [!NOTE]
> This release addresses a security issue (GHSA-7qqc-wrcw-2fj9) and is recommended for all users. Our sincere thank you to the community members who reported this.

## paperless-ngx 2.20.8
    ```

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
- **Current Version:** `0.35.0`
- **Latest Version:** `0.35.0` ✅ (up-to-date)

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

> [!WARNING]
>
> ## Hotfix
>
> ### `longhorn-instance-manager` Image
>
> The `longhorn-instance-manager:v1.11.0` image is affected by a [regression issue](https://github.com/longhorn/longhorn/issues/12573) introduced by the new longhorn-instance-manager Proxy service APIs. The bug causes Proxy connection leaks in the longhorn-instance-manager pods, resulting in increased memory usage. To mitigate this issue, replace `longhornio/longhorn-instance-manager:v1.11.0` with the hotfixed image `longhornio/longhorn-instance-manager:v1.11.0-hotfix-1`.
>
> You can apply the update by following these steps:
>
> 1. **Update the `longhorn-instance-manager` image**
>
>    - Change the longhorn-instance-manager image tag from `v1.11.0` to `v1.11.0-hotfix-1` in the appropriate file:
>        - For Helm: Update `values.yaml`
>        - For manifests: Update the deployment manifest directly.
>
> 2. **Proceed with the installation or upgrade**
>
>    - Apply the changes using your standard Helm install/upgrade command or reapply the updated manifest.
>
> ### `longhorn-manager` Image
>
>
> The `longhorn-manager:v1.11.0` image is affected by a [regression issue](https://github.com/longhorn/longhorn/issues/12578) introduced by the new `Kubernetes Node` validator. The bug blocks setting Kubernetes node CNI labels because it waits for the Longhorn webhook server to be running, while the Longhorn webhook server waits for CNI network to be ready. To mitigate this issue, replace `longhornio/longhorn-manager:v1.11.0` with the hotfixed image `longhornio/longhorn-manager:v1.11.0-hotfix-1`.
>
> You can apply the update by following these steps:
> 
> 1. **Disable the upgrade version check**
>   - Helm users: Set `upgradeVersionCheck` to `false` in the `values.yaml` file.
>   - Manifest users: Remove the `--upgrade-version-check` flag from the deployment manifest.
>
> 2. **Update the `longhorn-manager` image**
>   - Change the `longhorn-manager` image tag from `v1.11.0` to `v1.11.0-hotfix-1` in the appropriate file:
>     - For Helm: Update `values.yaml`.
>     - For manifests: Update the deployment manifest directly.
>
>3. **Proceed with the installation or upgrade**
>   - Apply the changes using your standard Helm install/upgrade command or reapply the updated manifest.

## Deprecation

### V2 Backing Image Deprecation

The Backing Image feature for the V2 Data Engine is now deprecat
  ... (truncated, see source link above for full notes)
  ```
- **⚠️ Breaking Changes:**
  - Migration/Upgrade Guide:
  - > [!IMPORTANT]
  - **Ensure that your cluster is running Kubernetes v1.25 or later before upgrading from Longhorn v1.10.x to v1.11.0.**
  - Longhorn only allows upgrades from supported versions. For more information about upgrade paths and procedures, see [Upgrade](https://longhorn.io/docs/1.11.0/deploy/upgrade/) in the Longhorn documentation.

*No container images specified in values*

---
