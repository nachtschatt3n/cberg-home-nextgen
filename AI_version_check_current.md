# Kubernetes Deployment Version Status

**Generated:** 2026-01-11 12:41:21

> **Note:** Release notes are fetched from GitHub API. If rate limited, some release notes may not be available. Check source links for full details.

## Summary

- **Total Deployments:** 65
- **Chart Updates Available:** 25
- **Image Updates Available:** 16
- **Update Breakdown:** 🔴 6 major | 🟡 16 minor | 🟢 7 patch
- **⚠️ Breaking Changes Detected:** 6 updates with potential breaking changes

---

## Quick Overview Table

| Deployment | Namespace | Chart | Image | App | Complexity |
|------------|-----------|-------|-------|-----|------------|
| `icloud-docker-mu` | `backup` | 3.7.1 ? | latest ✅ | - | - |
| `absenty-development` | `custom-code-production` | 3.7.1 ? | sha-ff3910e-dev ? | sha-ff3910e-dev | - |
| `absenty-production` | `custom-code-production` | 3.7.1 ? | sha-ffa072a ? | sha-ffa072a | - |
| `nocodb` | `databases` | 3.7.1 ? | latest ✅ | - | - |
| `phpmyadmin` | `databases` | 3.7.1 ? | latest ✅ | - | - |
| `actual-budget` | `default` | 3.7.1 ? | latest ✅ | - | - |
| `ai-sre` | `default` | 3.7.1 ? | 2.1.0 ? | 2.1.0 | - |
| `bytebot` | `default` | 3.7.1 ? | 16-alpine ? | 16-alpine | - |
| `cert-manager` | `default` | v1.19.1 → v1.19.2 | - | - | 🟢 PATCH |
| `cilium` | `default` | 1.17.1 → 1.18.5 | - | - | 🟡 MINOR |
| `clawd-bot` | `default` | 3.7.1 ? | 22-alpine ? | 22-alpine | - |
| `cloudflared` | `default` | 3.7.1 ? | 2025.11.1 → 414-772ccc9 | 2025.11.1 | ⚪ UNKNOWN |
| `coredns` | `default` | 1.39.0 ? | - | - | - |
| `descheduler` | `default` | 0.33.0 → 0.34.0 | - | - | 🟡 MINOR |
| `echo-server` | `default` | 3.7.1 ? | 35 ? | 35 | - |
| `external-dns` | `default` | 1.15.2 → 1.20.0 | - | - | 🟡 MINOR |
| `external-ingress-nginx` | `default` | 4.12.0 → 4.14.1 | - | - | 🟡 MINOR |
| `fluent-bit` | `default` | 0.47.10 → 0.54.1 | 3.1.9 ? | 3.1.9 | 🟡 MINOR |
| `flux-instance` | `default` | 0.14.0 ? | - | - | - |
| `flux-operator` | `default` | 0.14.0 ? | - | - | - |
| `grafana` | `default` | 7.0.19 → 10.5.5 | - | - | 🔴 MAJOR |
| `homepage` | `default` | 2.0.2 → 2.1.0 | v1.6.1 ? | v1.6.1 | 🟡 MINOR |
| `intel-device-plugin-gpu` | `default` | 0.34.0 → 0.34.1 | - | - | 🟢 PATCH |
| `intel-device-plugin-operator` | `default` | 0.34.0 → 0.34.1 | - | - | 🟢 PATCH |
| `internal-ingress-nginx` | `default` | 4.12.0 → 4.14.1 | - | - | 🟡 MINOR |
| `jdownloader` | `default` | 3.7.1 ? | v25.02.1 → v1.0.0 | v25.02.1 | ⚪ UNKNOWN |
| `k8s-gateway` | `default` | 2.4.0 ✅ | - | - | - |
| `kube-prometheus-stack` | `default` | 68.4.4 ? | - | - | - |
| `kubernetes-dashboard` | `default` | 6.0.8 → 7.14.0 | - | - | 🔴 MAJOR |
| `mcpo` | `default` | 3.7.1 ? | git-44ce6d0 ? | git-44ce6d0 | - |
| `metricbeat` | `default` | 3.6.0 ? | 8.15.3 ? | 8.15.3 | - |
| `metrics-server` | `default` | 3.13.0 ✅ | - | - | - |
| `nextcloud` | `default` | 6.6.4 → 8.7.0 | 32.0.2 ? | 32.0.2 | 🔴 MAJOR |
| `node-feature-discovery` | `default` | 0.17.1 → 0.18.3 | - | - | 🟡 MINOR |
| `omni-tools` | `default` | 3.7.1 ? | 0.6.0 → 0.1.0 | 0.6.0 | ⚪ UNKNOWN |
| `open-webui` | `default` | 5.13.0 → 10.1.0 | v0.6.43 ? | v0.6.43 | 🔴 MAJOR |
| `paperless-ai` | `default` | 3.7.1 ? | latest ✅ | - | - |
| `paperless-gpt` | `default` | 3.7.1 ? | latest ✅ | - | - |
| `reloader` | `default` | 1.2.1 ? | - | - | - |
| `spegel` | `default` | v0.0.30 ? | - | - | - |
| `teslamate` | `default` | 3.7.1 ? | 2.2.0 → 1.16.0 | 2.2.0 | 🟡 MINOR |
| `tube-archivist` | `default` | 3.7.1 ? | v0.5.8 → v0.3.6 | v0.5.8 | ⚪ UNKNOWN |
| `vaultwarden` | `default` | 3.7.1 ? | 1.32.7 → 1.21.0-alpine | 1.32.7 | ⚪ UNKNOWN |
| `esphome` | `home-automation` | 3.7.1 ? | 2025.10.5 ? | 2025.10.5 | - |
| `frigate` | `home-automation` | 7.8.0 ✅ | 0.16.2 ? | 0.16.2 | - |
| `home-assistant` | `home-automation` | 3.7.1 ? | 2026.1.0 ✅ | 2026.1.0 | - |
| `mosquitto` | `home-automation` | 3.7.1 ? | 2.0.20@sha256:8b396cec28cd5e8e1a3aba1d9a... | 2.0.20@sha256:8b396cec28cd5e8e... | - |
| `music-assistant-server` | `home-automation` | 3.7.1 ? | 2.7.2 → 2.7.3 | 2.7.2 | 🟢 PATCH |
| `n8n` | `home-automation` | 1.0.6 ? | 1.110.2 → 0.1.2 | 1.110.2 | ⚪ UNKNOWN |
| `node-red` | `home-automation` | 3.7.1 ? | 4.0.9 → 1.0.0-10-minimal-amd64 | 4.0.9 | ⚪ UNKNOWN |
| `scrypted` | `home-automation` | 3.7.1 ? | latest ✅ | - | - |
| `zigbee2mqtt` | `home-automation` | 3.7.1 ? | 2.6.1 → 0.1.0 | 2.6.1 | ⚪ UNKNOWN |
| `authentik` | `kube-system` | 2025.10.2 → 2025.10.3 | - | - | 🟢 PATCH |
| `csi-driver-smb` | `kube-system` | v1.17.0 → 1.19.1 | - | - | 🟡 MINOR |
| `jellyfin` | `media` | 2.1.0 → 2.7.0 | 10.11.3 → 10.0.0-arm | 10.11.3 | 🟡 MINOR |
| `makemkv` | `media` | 3.7.1 ? | latest ✅ | - | - |
| `plex` | `media` | 0.9.1 → 1.4.0 | 1.42.1.10060-4e8b05daf → 1.3.2.3112-1751... | 1.42.1.10060-4e8b05daf | 🔴 MAJOR |
| `eck-operator` | `monitoring` | 2.14.0 → 3.2.0 | - | - | 🔴 MAJOR |
| `opentelemetry-operator` | `monitoring` | 0.66.0 → 0.102.0 | - | - | 🟡 MINOR |
| `otel-collector` | `monitoring` | 0.92.0 → 0.143.0 |  → 0.2.10 | - | 🟡 MINOR |
| `uptime-kuma` | `monitoring` | 2.18.0 → 2.24.0 | 2.0.0-beta.2 → 1.0.1 | 2.0.0-beta.2 | 🟡 MINOR |
| `adguard-home` | `network` | 0.19.0 → 0.24.0 | v0.107.65 → v0.93 | v0.107.65 | 🟡 MINOR |
| `paperless-ngx` | `office` | 0.19.1 → 0.24.1 | 2.20.3 ✅ | 2.20.3 | 🟡 MINOR |
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
  - **Latest Tag:** `1.0.0` ✅ (up-to-date)

---

## Namespace: `custom-code-production`

### absenty-development

- **File:** `kubernetes/apps/custom-code-production/absenty-development/app/helmrelease.yaml`

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

### absenty-production

- **File:** `kubernetes/apps/custom-code-production/absenty-production/app/helmrelease.yaml`

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
  - **Latest Tag:** `0.5.0` ✅ (up-to-date)

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
  - **Latest Tag:** `sha-c3d89b6-alpine` ✅ (up-to-date)

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

### bytebot

- **File:** `kubernetes/apps/ai/bytebot/app/helmrelease.yaml`

#### Chart
- **Name:** `app-template`
- **Repository:** `bjw-s`
- **Current Version:** `3.7.1`
- **Latest Version:** *Could not determine*

#### Container Images
- **Repository:** `postgres`
  - **Path:** `controllers.postgres.containers.postgres.image`
  - **Current Tag:** `16-alpine`
  - **Latest Tag:** *Could not determine*

- **Repository:** `ghcr.io/bytebot-ai/bytebot-desktop`
  - **Path:** `controllers.desktop.containers.desktop.image`
  - **Current Tag:** `edge`
  - **Latest Tag:** *Could not determine*

- **Repository:** `busybox`
  - **Path:** `controllers.desktop.initContainers.fix-permissions.image`
  - **Current Tag:** `latest`
  - **Latest Tag:** *Could not determine*

- **Repository:** `ghcr.io/bytebot-ai/bytebot-agent`
  - **Path:** `controllers.agent.containers.agent.image`
  - **Current Tag:** `edge`
  - **Latest Tag:** *Could not determine*

- **Repository:** `ghcr.io/bytebot-ai/bytebot-ui`
  - **Path:** `controllers.ui.containers.ui.image`
  - **Current Tag:** `edge`
  - **Latest Tag:** *Could not determine*

---

### cert-manager

- **File:** `kubernetes/apps/cert-manager/cert-manager/app/helmrelease.yaml`

#### Chart
- **Name:** `cert-manager`
- **Repository:** `jetstack`
- **Current Version:** `v1.19.1`
- **Latest Version:** `v1.19.2` ⚠️ **UPDATE AVAILABLE**
- **Update Type:** 🟢 **PATCH** (low complexity)
- **Update Description:** Patch version update: 1.19.1 → 1.19.2
- **Source:** https://github.com/cert-manager/cert-manager/releases/tag/v1.19.2
- **Release Date:** 2025-12-09
- **Release Notes:**
  ```markdown
  cert-manager is the easiest way to automatically manage certificates in Kubernetes and OpenShift clusters.

We updated Go to fix some vulnerabilities in the standard library.

> 📖 Read the [full 1.19 release notes](https://cert-manager.io/docs/releases/release-notes/release-notes-1.19) on the cert-manager.io website before upgrading.


## Changes since `v1.19.1`

### Bug or Regression

- Address false positive vulnerabilities `CVE-2025-47914` and `CVE-2025-58181` which were reported by Trivy. (#8283, @SgtCoDFish)
- Update Go to `v1.25.5` to fix `CVE-2025-61727` and `CVE-2025-61729` (#8294, @wallrj-cyberark)
- Update `global.nodeSelector` to helm chart to perform a `merge` and allow for a single `nodeSelector` to be set across all services. (#8233, @cert-manager-bot)

### Other (Cleanup or Flake)

- Update cert-manager's ACME client, forked from `golang/x/crypto` (#8270, @SgtCoDFish)
- Updated Debian 12 distroless base images (#8326, @wallrj-cyberark)
  ```
- **⚠️ Breaking Changes:** *Patch updates typically don't have breaking changes - see release notes above*

*No container images specified in values*

---

### cilium

- **File:** `kubernetes/apps/kube-system/cilium/app/helmrelease.yaml`

#### Chart
- **Name:** `cilium`
- **Repository:** `cilium`
- **Current Version:** `1.17.1`
- **Latest Version:** `1.18.5` ⚠️ **UPDATE AVAILABLE**
- **Update Type:** 🟡 **MINOR** (medium complexity)
- **Update Description:** Minor version update: 1.17.x → 1.18.x
- **Source:** https://github.com/cilium/cilium/releases/tag/1.18.5
- **Release Date:** 2025-12-18
- **Release Notes:**
  ```markdown
  Summary of Changes
------------------

**Minor Changes:**
* [v1.18] proxy: Bump envoy version to v1.34.11 (cilium/cilium#43143, @sayboras)
* Change the sidecar etcd instance of the Cluster Mesh API Server listen on all IP addresses (Backport PR cilium/cilium#42948, Upstream PR cilium/cilium#42818, @giorio94)

**Bugfixes:**
* allow missing verbs for cilium-agent cluster role when readSecretsOnlyFromSecretsNamespace is false (Backport PR cilium/cilium#42948, Upstream PR cilium/cilium#42790, @kraashen)
* AWS EC2: Fix ENI attachment on multi-network card instances with high-performance networking (EFA) setups (Backport PR cilium/cilium#42745, Upstream PR cilium/cilium#42512, @41ks)
* CiliumEnvoyConfig proxy ports are now restored on agent restarts. (Backport PR cilium/cilium#43117, Upstream PR cilium/cilium#43108, @jrajahalme)
* Cleanup FQDNs that have leaked into the global FQDN cache (Backport PR cilium/cilium#42864, Upstream PR cilium/cilium#42485, @sjohnsonpal)
* Do not opt-out Endpoint ID 1 from dnsproxy transparent mode. (Backport PR cilium/cilium#42948, Upstream PR cilium/cilium#42887, @jrajahalme)
* ENI: Fix panic on nil subnet (Backport PR cilium/cilium#43117, Upstream PR cilium/cilium#43023, @HadrienPatte)
* Ensure cilium-agent gracefully does fallbacks when etcd is in a bad state. (Backport PR cilium/cilium#43059, Upstream PR cilium/cilium#42977, @odinuge)
* Fix a bug that would cause Cilium to not report L4 checksum update errors when the length attribute is missing in ICMP Error messages with TCP inner packets. (Backport PR cilium/cilium#42828, Upstream PR cilium/cilium#42426, @yushoyamaguchi)
* Fix a bug that would cause IPsec logs to incorrectly report the XFRM rules being processed as "Ingress" rules. (Backport PR cilium/cilium#42828, Upstream PR cilium/cilium#42640, @sjohnsonpal)
* Fix agent local identity leak (Backport PR cilium/cilium#43117, Upstream PR cilium/cilium#42662, @odinuge)
* Fix bug that could cause the agent to fail to add XFRM states when IPsec is enabled, thus preventing a proper startup. (Backport PR cilium/cilium#42948, Upstream PR cilium/cilium#42666, @pchaigno)
* Fix GC of per-cluster ctmap entries (Backport PR cilium/cilium#43294, Upstream PR cilium/cilium#43160, @giorio94)
* Fix ipcache issues causing severe issues with the fqdn subsystem (Backport PR cilium/cilium#42864, Upstream PR cilium/cilium#42815, @odinuge)
* Fix issue where endpoints got stuck in "waiting-to-regenerate" (Backport PR cilium/cilium#42948, Upstream PR cilium/cilium#42856, @odinuge)
* Fix leak in the policy subsystem (Backport PR cilium/cilium#43117, Upstream PR cilium/cilium#42661, @odinuge)
* Fix rare kvstore issue where cilium continues to use an expired lease causing kvstore operations to fail consistently (Backport PR cilium/cilium#42745, Upstream PR cilium/cilium#42709, @odinuge)
* fqdn: Fix fqdn subsystem correctness issues causing packet drops and inconsistent ipcache (Backport PR cilium/cilium#43117, Upstrea
  ... (truncated, see source link above for full notes)
  ```
- **⚠️ Breaking Changes:** *Review release notes above for potential breaking changes*

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
  - **Current Tag:** `22-alpine`
  - **Latest Tag:** *Could not determine*

- **Repository:** `node`
  - **Path:** `controllers.clawd-bot.initContainers.install-clawdbot.image`
  - **Current Tag:** `22-alpine`
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
  - **Latest Tag:** `414-772ccc9` ⚠️ **UPDATE AVAILABLE**
  - **Update Type:** ⚪ **UNKNOWN** (unknown complexity)
  - **Update Description:** Versions appear equal or downgrade detected
  - **Source:** https://github.com/docker.io/cloudflared/releases/tag/414-772ccc9
  - **Release Notes:** *Could not fetch release notes (GitHub API rate limit or release not found). Check source link above.*

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
- **Current Version:** `0.33.0`
- **Latest Version:** `0.34.0` ⚠️ **UPDATE AVAILABLE**
- **Update Type:** 🟡 **MINOR** (medium complexity)
- **Update Description:** Minor version update: 0.33.x → 0.34.x
- **Source:** https://github.com/kubernetes-sigs/descheduler/releases/tag/0.34.0
- **Release Date:** 2025-10-30
- **Release Notes:**
  ```markdown
  ## What's Changed
* Remove reference to obsolete deschedulerPolicy fields in chart values by @meroupatate in https://github.com/kubernetes-sigs/descheduler/pull/1674
* v0.33.0: bump helm chart by @a7i in https://github.com/kubernetes-sigs/descheduler/pull/1680
* optimize: NodeFit function by reordering checks for performance by @googs1025 in https://github.com/kubernetes-sigs/descheduler/pull/1681
* feature: sort pods by restarts count in RemovePodsHavingTooManyRestarts plugin by @googs1025 in https://github.com/kubernetes-sigs/descheduler/pull/1686
* chore: move namespaces filtering logic to New() by @googs1025 in https://github.com/kubernetes-sigs/descheduler/pull/1684
* RemovePodsViolatingNodeTaints: list only pods that are not failed/suceeded by @ingvagabund in https://github.com/kubernetes-sigs/descheduler/pull/1688
* fix(example): list only active pod by @googs1025 in https://github.com/kubernetes-sigs/descheduler/pull/1691
* refactor: separate eviction constraints to constraints.go by @googs1025 in https://github.com/kubernetes-sigs/descheduler/pull/1693
* Extend plugin's New with a context.Context by @ingvagabund in https://github.com/kubernetes-sigs/descheduler/pull/1694
* *1677 Allow Succeeded and Failed states in PodLifeTime by @doctapp in https://github.com/kubernetes-sigs/descheduler/pull/1696
* metrics name refact by @lowang-bh in https://github.com/kubernetes-sigs/descheduler/pull/1232
* feat(prometheus): allow different url schemes by @ricardomaraschini in https://github.com/kubernetes-sigs/descheduler/pull/1705
* feature: use contextal logging for plugins by @googs1025 in https://github.com/kubernetes-sigs/descheduler/pull/1655
* logger: Align with the previous logger verbosity by @ingvagabund in https://github.com/kubernetes-sigs/descheduler/pull/1708
* add activeDeadlineSeconds field for cronjob by @googs1025 in https://github.com/kubernetes-sigs/descheduler/pull/1709
* chore: stop with no-op default evictor settings by @ricardomaraschini in https://github.com/kubernetes-sigs/descheduler/pull/1717
* fix: removepodsviolatingtopologyspreadconstraint to favor evictable pods when balancing domains by @a7i in https://github.com/kubernetes-sigs/descheduler/pull/1719
* fix: Fix panic in descheduler when using `--secure-port=0` by @dongjiang1989 in https://github.com/kubernetes-sigs/descheduler/pull/1647
* feat(helm): run descedulerPolicy thru tpl func for more chart control by @schahal in https://github.com/kubernetes-sigs/descheduler/pull/1660
* Test code refactorings by @ingvagabund in https://github.com/kubernetes-sigs/descheduler/pull/1722
* Default evictor no eviction policy by @ingvagabund in https://github.com/kubernetes-sigs/descheduler/pull/1723
* add PodProtections for DefaultEvictorArgs by @googs1025 in https://github.com/kubernetes-sigs/descheduler/pull/1665
* add ValidateHighNodeUtilizationPluginConfig unit test by @googs1025 in https://github.com/kubernetes-sigs/descheduler/pull/1733
* feature: ad
  ... (truncated, see source link above for full notes)
  ```
- **⚠️ Breaking Changes:** *Review release notes above for potential breaking changes*

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
- **Current Version:** `1.15.2`
- **Latest Version:** `1.20.0` ⚠️ **UPDATE AVAILABLE**
- **Update Type:** 🟡 **MINOR** (medium complexity)
- **Update Description:** Minor version update: 1.15.x → 1.20.x
- **Source:** https://github.com/kubernetes-sigs/external-dns/releases/tag/1.20.0
- **Release Notes:** *Could not fetch release notes (GitHub API rate limit or release not found). Check source link above.*
- **⚠️ Breaking Changes:** *Review release notes above for potential breaking changes*

*No container images specified in values*

---

### external-ingress-nginx

- **File:** `kubernetes/apps/network/external/ingress-nginx/helmrelease.yaml`

#### Chart
- **Name:** `ingress-nginx`
- **Repository:** `ingress-nginx`
- **Current Version:** `4.12.0`
- **Latest Version:** `4.14.1` ⚠️ **UPDATE AVAILABLE**
- **Update Type:** 🟡 **MINOR** (medium complexity)
- **Update Description:** Minor version update: 4.12.x → 4.14.x
- **Source:** https://github.com/kubernetes/ingress-nginx/releases/tag/4.14.1
- **Release Notes:** *Could not fetch release notes (GitHub API rate limit or release not found). Check source link above.*
- **⚠️ Breaking Changes:** *Review release notes above for potential breaking changes*

*No container images specified in values*

---

### fluent-bit

- **File:** `kubernetes/apps/monitoring/fluent-bit/app/helmrelease.yaml`

#### Chart
- **Name:** `fluent-bit`
- **Repository:** `fluent`
- **Current Version:** `0.47.10`
- **Latest Version:** `0.54.1` ⚠️ **UPDATE AVAILABLE**
- **Update Type:** 🟡 **MINOR** (medium complexity)
- **Update Description:** Minor version update: 0.47.x → 0.54.x
- **Source:** https://github.com/fluent/helm-charts/releases/tag/0.54.1
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
- **Current Version:** `7.0.19`
- **Latest Version:** `10.5.5` ⚠️ **UPDATE AVAILABLE**
- **Update Type:** 🔴 **MAJOR** (high complexity)
- **Update Description:** Major version update: 7.x.x → 10.x.x
- **Source:** https://github.com/grafana/helm-charts/releases/tag/10.5.5
- **Release Notes:** *Could not fetch release notes (GitHub API rate limit or release not found). Check source link above.*
- **⚠️ Breaking Changes:** *Major version update - review release notes above for breaking changes*

*No container images specified in values*

---

### homepage

- **File:** `kubernetes/apps/default/homepage/app/helmrelease.yaml`

#### Chart
- **Name:** `homepage`
- **Repository:** `jameswynn`
- **Current Version:** `2.0.2`
- **Latest Version:** `2.1.0` ⚠️ **UPDATE AVAILABLE**
- **Update Type:** 🟡 **MINOR** (medium complexity)
- **Update Description:** Minor version update: 2.0.x → 2.1.x
- **Source:** https://github.com/gethomepage/homepage/releases/tag/2.1.0
- **Release Notes:** *Could not fetch release notes (GitHub API rate limit or release not found). Check source link above.*
- **⚠️ Breaking Changes:** *Review release notes above for potential breaking changes*

#### Container Images
- **Repository:** `ghcr.io/gethomepage/homepage`
  - **Path:** `image`
  - **Current Tag:** `v1.6.1`
  - **Latest Tag:** *Could not determine*

---

### intel-device-plugin-gpu

- **File:** `kubernetes/apps/kube-system/intel-device-plugin/gpu/helmrelease.yaml`

#### Chart
- **Name:** `intel-device-plugins-gpu`
- **Repository:** `intel`
- **Current Version:** `0.34.0`
- **Latest Version:** `0.34.1` ⚠️ **UPDATE AVAILABLE**
- **Update Type:** 🟢 **PATCH** (low complexity)
- **Update Description:** Patch version update: 0.34.0 → 0.34.1
- **Source:** https://github.com/intel-device-plugins-gpu/intel-device-plugins-gpu/releases/tag/0.34.1
- **Release Notes:** *Could not fetch release notes (GitHub API rate limit or release not found). Check source link above.*
- **⚠️ Breaking Changes:** *Patch updates typically don't have breaking changes - see release notes above*

*No container images specified in values*

---

### intel-device-plugin-operator

- **File:** `kubernetes/apps/kube-system/intel-device-plugin/app/helmrelease.yaml`

#### Chart
- **Name:** `intel-device-plugins-operator`
- **Repository:** `intel`
- **Current Version:** `0.34.0`
- **Latest Version:** `0.34.1` ⚠️ **UPDATE AVAILABLE**
- **Update Type:** 🟢 **PATCH** (low complexity)
- **Update Description:** Patch version update: 0.34.0 → 0.34.1
- **Source:** https://github.com/intel-device-plugins-operator/intel-device-plugins-operator/releases/tag/0.34.1
- **Release Notes:** *Could not fetch release notes (GitHub API rate limit or release not found). Check source link above.*
- **⚠️ Breaking Changes:** *Patch updates typically don't have breaking changes - see release notes above*

*No container images specified in values*

---

### internal-ingress-nginx

- **File:** `kubernetes/apps/network/internal/ingress-nginx/helmrelease.yaml`

#### Chart
- **Name:** `ingress-nginx`
- **Repository:** `ingress-nginx`
- **Current Version:** `4.12.0`
- **Latest Version:** `4.14.1` ⚠️ **UPDATE AVAILABLE**
- **Update Type:** 🟡 **MINOR** (medium complexity)
- **Update Description:** Minor version update: 4.12.x → 4.14.x
- **Source:** https://github.com/kubernetes/ingress-nginx/releases/tag/4.14.1
- **Release Notes:** *Could not fetch release notes (GitHub API rate limit or release not found). Check source link above.*
- **⚠️ Breaking Changes:** *Review release notes above for potential breaking changes*

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
  - **Latest Tag:** `v1.0.0` ⚠️ **UPDATE AVAILABLE**
  - **Update Type:** ⚪ **UNKNOWN** (unknown complexity)
  - **Update Description:** Versions appear equal or downgrade detected
  - **Source:** https://github.com/jlesage/jdownloader-2/releases/tag/v1.0.0
  - **Release Notes:** *Could not fetch release notes (GitHub API rate limit or release not found). Check source link above.*

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

### kubernetes-dashboard

- **File:** `kubernetes/apps/monitoring/kubernetes-dashboard/app/helmrelease.yaml`

#### Chart
- **Name:** `kubernetes-dashboard`
- **Repository:** `kubernetes-dashboard`
- **Current Version:** `6.0.8`
- **Latest Version:** `7.14.0` ⚠️ **UPDATE AVAILABLE**
- **Update Type:** 🔴 **MAJOR** (high complexity)
- **Update Description:** Major version update: 6.x.x → 7.x.x
- **Source:** https://github.com/kubernetes-dashboard/kubernetes-dashboard/releases/tag/7.14.0
- **Release Notes:** *Could not fetch release notes (GitHub API rate limit or release not found). Check source link above.*
- **⚠️ Breaking Changes:** *Major version update - review release notes above for breaking changes*

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

### metricbeat

- **File:** `kubernetes/apps/monitoring/metricbeat/app/helmrelease.yaml`

#### Chart
- **Name:** `app-template`
- **Repository:** `bjw-s`
- **Current Version:** `3.6.0`
- **Latest Version:** *Could not determine*

#### Container Images
- **Repository:** `docker.elastic.co/beats/metricbeat`
  - **Path:** `controllers.metricbeat.containers.app.image`
  - **Current Tag:** `8.15.3`
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
- **Latest Version:** `8.7.0` ⚠️ **UPDATE AVAILABLE**
- **Update Type:** 🔴 **MAJOR** (high complexity)
- **Update Description:** Major version update: 6.x.x → 8.x.x
- **Source:** https://github.com/nextcloud/helm/releases/tag/8.7.0
- **Release Notes:** *Could not fetch release notes (GitHub API rate limit or release not found). Check source link above.*
- **⚠️ Breaking Changes:** *Major version update - review release notes above for breaking changes*

#### Container Images
- **Repository:** `nextcloud`
  - **Path:** `image`
  - **Current Tag:** `32.0.2`
  - **Latest Tag:** *Could not determine*

- **Repository:** `bitnamilegacy/mariadb`
  - **Path:** `mariadb.image`
  - **Current Tag:** `latest`
  - **Latest Tag:** `0.0.1` ✅ (up-to-date)

- **Repository:** `xperimental/nextcloud-exporter`
  - **Path:** `metrics.image`
  - **Current Tag:** `0.6.2`
  - **Latest Tag:** `v0.1.0` ⚠️ **UPDATE AVAILABLE**
  - **Update Type:** ⚪ **UNKNOWN** (unknown complexity)
  - **Update Description:** Versions appear equal or downgrade detected
  - **Source:** https://github.com/xperimental/nextcloud-exporter/releases/tag/v0.1.0
  - **Release Notes:** *Could not fetch release notes (GitHub API rate limit or release not found). Check source link above.*

- **Repository:** `bitnamilegacy/redis`
  - **Path:** `redis.image`
  - **Current Tag:** `latest`
  - **Latest Tag:** `3.2.0-r1` ✅ (up-to-date)

---

### node-feature-discovery

- **File:** `kubernetes/apps/kube-system/node-feature-discovery/app/helmrelease.yaml`

#### Chart
- **Name:** `node-feature-discovery`
- **Repository:** `node-feature-discovery`
- **Current Version:** `0.17.1`
- **Latest Version:** `0.18.3` ⚠️ **UPDATE AVAILABLE**
- **Update Type:** 🟡 **MINOR** (medium complexity)
- **Update Description:** Minor version update: 0.17.x → 0.18.x
- **Source:** https://github.com/kubernetes-sigs/node-feature-discovery/releases/tag/0.18.3
- **Release Date:** 2025-11-05
- **Release Notes:**
  ```markdown
  ## What's Changed

This patch release adds support for ppc64le and s390x architectures by providing official NFD container images for them. It also fixes the "test" subcommand of kubectl-nfd plugin.

**Full Changelog**: https://github.com/kubernetes-sigs/node-feature-discovery/compare/v0.18.2...v0.18.3
  ```
- **⚠️ Breaking Changes:** *Review release notes above for potential breaking changes*

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
  - **Latest Tag:** `0.1.0` ⚠️ **UPDATE AVAILABLE**
  - **Update Type:** ⚪ **UNKNOWN** (unknown complexity)
  - **Update Description:** Versions appear equal or downgrade detected
  - **Source:** https://github.com/iib0011/omni-tools/releases/tag/0.1.0
  - **Release Date:** 2025-02-27
  - **Release Notes:**
    ```markdown
    ## Docker images
- `iib0011/omni-tools:latest`
- `iib0011/omni-tools:0.1.0`
## What's new
### PNG Tools:
- **Compress PNG**: Reduce the file size of PNG images without losing quality.
- **Convert JPG to PNG**: Easily convert JPG images to PNG format.
- **Create Transparent PNG**: Make parts of an image transparent.
- **Change Colors in PNG**: Replace specific colors in a PNG image.

### Text Tools:
- **Text Splitter**: Split text into multiple lines or segments.
- **Text Joiner**: Combine multiple lines of text into one.
- **String to Morse**: Convert text into Morse code.

### JSON Tools:
- **Prettify JSON**: Format JSON data for better readability.

### List Tools:
- **Sort**: Arrange list items in ascending or descending order.
- **Unwrap**: Remove wrapping characters (like quotes) from list items.
- **Reverse**: Reverse the order of items in a list.
- **Find Unique**: Identify and keep only unique items from a list.
- **Find Most Popular**: Find the most frequently occurring items.
- **Group**: Group list items based on a common attribute.
- **Rotate**: Shift list items by a certain number of positions.
- **Shuffle**: Randomly rearrange list items.

### GIF Tools:
- **Change Speed**: Adjust the playback speed of GIFs.

### Number Tools:
- **Sum Calculator**: Calculate the sum of a list of numbers.
- **Generate Numbers**: Create a sequence of numbers.

## New Contributors
* @Made4Uo made their first contribution in https://github.com/iib0011/omni-tools/pull/8
* @Chesterkxng made their first contribution in https://github.com/iib0011/omni-tools/pull/15
* @hhourani27 made their first contribution in https://github.com/iib0011/omni-tools/pull/17

**Full Changelog**: https://github.com/iib0011/omni-tools/commits/v0.1.0
    ```

---

### open-webui

- **File:** `kubernetes/apps/ai/open-webui/app/helmrelease.yaml`

#### Chart
- **Name:** `open-webui`
- **Repository:** `open-webui`
- **Current Version:** `5.13.0`
- **Latest Version:** `10.1.0` ⚠️ **UPDATE AVAILABLE**
- **Update Type:** 🔴 **MAJOR** (high complexity)
- **Update Description:** Major version update: 5.x.x → 10.x.x
- **Source:** https://github.com/open-webui/open-webui/releases/tag/10.1.0
- **Release Notes:** *Could not fetch release notes (GitHub API rate limit or release not found). Check source link above.*
- **⚠️ Breaking Changes:** *Major version update - review release notes above for breaking changes*

#### Container Images
- **Repository:** `ghcr.io/open-webui/open-webui`
  - **Path:** `image`
  - **Current Tag:** `v0.6.43`
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
  - **Latest Tag:** `1.1.5` ✅ (up-to-date)

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
  - **Latest Tag:** `ollama-bearer` ✅ (up-to-date)

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
  - **Latest Tag:** `1.16.0` ⚠️ **UPDATE AVAILABLE**
  - **Update Type:** 🟡 **MINOR** (medium complexity)
  - **Update Description:** Minor version update: 2.2.x → 2.16.x
  - **Source:** https://github.com/teslamate/teslamate/releases/tag/1.16.0
  - **Release Notes:** *Could not fetch release notes (GitHub API rate limit or release not found). Check source link above.*

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
  - **Latest Tag:** `v0.3.6` ⚠️ **UPDATE AVAILABLE**
  - **Update Type:** ⚪ **UNKNOWN** (unknown complexity)
  - **Update Description:** Versions appear equal or downgrade detected
  - **Source:** https://github.com/bbilly1/tubearchivist/releases/tag/v0.3.6
  - **Release Date:** 2023-05-13
  - **Release Notes:**
    ```markdown
    ## Project Updates
- This update will automatically change and rebuild the video, channel and download queue indexes.
- Tube Archivist Companion browser extension also got an update to control auto start behavior: [Release Notes](https://github.com/tubearchivist/browser-extension/releases/tag/v0.1.4)
- If you are a sponsor, the real time monitor client also got an update to control auto start behavior: [Release Notes](https://github.com/tubearchivist/members/releases/tag/v0.0.2)
- It is recommend to run [Rescan Filesystem](https://docs.tubearchivist.com/settings/#rescan-filesystem) to validate all media file paths before updating, monitor the logs to make sure, this does nothing unexpected.
- At first start, there is a migration command running to index additional metadata from your media files. That includes file size, codec, bitrate, resolution. 
  - That process can take some time, depending on various factors, expect this to take around 1 minute per 1000 videos.
  - Log output will show progress and any error messages.
  - The interface will become available again, after that completes.
  - Be patient and grab some popcorn to watch the logs fly by.

## Added
- Added video stream metadata indexing like codecs, bitrate, filesize
- Added channel metadata aggregation like total file size, total videos, total playback.
- Added start now for adding to download queue, [docs](https://docs.tubearchivist.com/downloads/#add-to-download-queue)
- Added auto start for subscriptions, [docs](https://docs.tubearchivist.com/settings/#subscriptions)
- Added extractor language configuration, [docs](https://docs.tubearchivist.com/settings/#download-format)
- Added `--format-sort` configuration, [docs](https://docs.tubearchivist.com/settings/#download-format), by @dsander
- Added channel tags indexing for better search results
- [API] Added endpoints to control auto start behavior

## Changed
- Changed channel metadata extraction to use `yt-dlp` instead of custom scraper for better reliability.
- Removed the `limit_count` config field, use queue control instead

## Fixed
- Fixed backup run issue when not initiated with task
- Fixed playlist ID parser for members only playlists, by @mglinski

## Hotfix
- I've pushed a quick hotfix dealing with #476, if you encounter that, please pull again.
    ```

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
  - **Current Tag:** `1.32.7`
  - **Latest Tag:** `1.21.0-alpine` ⚠️ **UPDATE AVAILABLE**
  - **Update Type:** ⚪ **UNKNOWN** (unknown complexity)
  - **Update Description:** Versions appear equal or downgrade detected
  - **Source:** https://github.com/vaultwarden/server/releases/tag/1.21.0-alpine
  - **Release Notes:** *Could not fetch release notes (GitHub API rate limit or release not found). Check source link above.*

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
  - **Current Tag:** `2025.10.5`
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
  - **Current Tag:** `0.16.2`
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
  - **Current Tag:** `2026.1.0`
  - **Latest Tag:** `2026.1.0` ✅ (up-to-date)

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
  - **Current Tag:** `2.7.2`
  - **Latest Tag:** `2.7.3` ⚠️ **UPDATE AVAILABLE**
  - **Update Type:** 🟢 **PATCH** (low complexity)
  - **Update Description:** Patch version update: 2.7.2 → 2.7.3
  - **Source:** https://github.com/music-assistant/server/releases/tag/2.7.3
  - **Release Date:** 2026-01-02
  - **Release Notes:**
    ```markdown
    ## 📦 Stable Release

_Changes since [2.7.2](https://github.com/music-assistant/server/releases/tag/2.7.2)_

### 🐛 Bugfixes

- Fix link in Roku manifest (by @OzGav in #2866)
- Fix items not showing up in the library (filtering still not right) (by @arturpragacz in #2873)
- Fix Sonos S1 not reconnecting after having gone offline. (by @MarvinSchenkel in #2874)
- Audible: Fix authentication for new API token format (by @ztripez in #2875)
- Plex Connect: Fix Plex Connect timeline reporting (by @anatosun in #2876)
- Fix issue with remote_progress if user not logged in (by @jfeil in #2882)
- Add 2 guards for queue missing after client disconnect (by @balloob in #2884)
- Fix spotify podcast thumb image quality (by @OzGav in #2885)
- Prevent cache with media_item=None (by @balloob in #2886)
- Disconnect sendspin clients to allow clean shutdown (by @balloob in #2887)
- Fix OpenSubsonic ReplayGain loudness calculation (by @OzGav in #2893)
- Improve single artist detection when splitting (by @OzGav in #2899)
- Fix base queries to work with provider mapping filters (by @MarvinSchenkel in #2900)
- Fix track name stripping too agressive (by @OzGav in #2901)
- Fix multiple spotify connect instances reporting to the latest registered webservice callback (by @kneirinck in #2905)
- fix: MusicCast Pause (by @fmunkes in #2907)

### 🧰 Maintenance and dependency bumps

- Bump aioslimproto to 3.1.3 (by @MarvinSchenkel in #2906)
- Bump aioslimproto to 3.1.4 (by @MarvinSchenkel in #2909)

## :bow: Thanks to our contributors

Special thanks to the following contributors who helped with this release:

@MarvinSchenkel, @OzGav, @anatosun, @arturpragacz, @balloob, @fmunkes, @jfeil, @kneirinck, @ztripez
    ```

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
  - **Current Tag:** `1.110.2`
  - **Latest Tag:** `0.1.2` ⚠️ **UPDATE AVAILABLE**
  - **Update Type:** ⚪ **UNKNOWN** (unknown complexity)
  - **Update Description:** Versions appear equal or downgrade detected
  - **Source:** https://github.com/n8nio/n8n/releases/tag/0.1.2
  - **Release Notes:** *Could not fetch release notes (GitHub API rate limit or release not found). Check source link above.*

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
  - **Current Tag:** `4.0.9`
  - **Latest Tag:** `1.0.0-10-minimal-amd64` ⚠️ **UPDATE AVAILABLE**
  - **Update Type:** ⚪ **UNKNOWN** (unknown complexity)
  - **Update Description:** Versions appear equal or downgrade detected
  - **Source:** https://github.com/nodered/node-red/releases/tag/1.0.0-10-minimal-amd64
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
  - **Latest Tag:** `nightly-2022-03-08` ✅ (up-to-date)

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
  - **Current Tag:** `2.6.1`
  - **Latest Tag:** `0.1.0` ⚠️ **UPDATE AVAILABLE**
  - **Update Type:** ⚪ **UNKNOWN** (unknown complexity)
  - **Update Description:** Versions appear equal or downgrade detected
  - **Source:** https://github.com/koenkk/zigbee2mqtt/releases/tag/0.1.0
  - **Release Date:** 2018-07-03

---

## Namespace: `kube-system`

### authentik

- **File:** `kubernetes/apps/kube-system/authentik/app/helmrelease.yaml`

#### Chart
- **Name:** `authentik`
- **Repository:** `authentik`
- **Current Version:** `2025.10.2`
- **Latest Version:** `2025.10.3` ⚠️ **UPDATE AVAILABLE**
- **Update Type:** 🟢 **PATCH** (low complexity)
- **Update Description:** Patch version update: 2025.10.2 → 2025.10.3
- **Source:** https://github.com/goauthentik/authentik/releases/tag/2025.10.3
- **Release Notes:** *Could not fetch release notes (GitHub API rate limit or release not found). Check source link above.*
- **⚠️ Breaking Changes:** *Patch updates typically don't have breaking changes - see release notes above*

*No container images specified in values*

---

### csi-driver-smb

- **File:** `kubernetes/apps/kube-system/csi-driver-smb/app/helmrelease.yaml`

#### Chart
- **Name:** `csi-driver-smb`
- **Repository:** `csi-driver-smb`
- **Current Version:** `v1.17.0`
- **Latest Version:** `1.19.1` ⚠️ **UPDATE AVAILABLE**
- **Update Type:** 🟡 **MINOR** (medium complexity)
- **Update Description:** Minor version update: 1.17.x → 1.19.x
- **Source:** https://github.com/kubernetes-csi/csi-driver-smb/releases/tag/1.19.1
- **Release Date:** 2025-10-13
- **Release Notes:**
  ```markdown
  ## What's Changed
* [release-1.19] chore: Update csi release tools by @andyzhangx in https://github.com/kubernetes-csi/csi-driver-smb/pull/983
* doc: cut v1.19.1 release by @andyzhangx in https://github.com/kubernetes-csi/csi-driver-smb/pull/984


**Full Changelog**: https://github.com/kubernetes-csi/csi-driver-smb/compare/v1.19.0...v1.19.1
  ```
- **⚠️ Breaking Changes:** *Review release notes above for potential breaking changes*

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
  - **Current Tag:** `10.11.3`
  - **Latest Tag:** `10.0.0-arm` ⚠️ **UPDATE AVAILABLE**
  - **Update Type:** ⚪ **UNKNOWN** (unknown complexity)
  - **Update Description:** Versions appear equal or downgrade detected
  - **Source:** https://github.com/docker.io/jellyfin/releases/tag/10.0.0-arm
  - **Release Notes:** *Could not fetch release notes (GitHub API rate limit or release not found). Check source link above.*

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
  - **Latest Tag:** `v0.1.0-beta` ✅ (up-to-date)

- **Repository:** `jlesage/makemkv`
  - **Path:** `controllers.main.containers.main.image`
  - **Current Tag:** `latest`
  - **Latest Tag:** `v0.1.0-beta` ✅ (up-to-date)

---

### plex

- **File:** `kubernetes/apps/media/plex/app/helmrelease.yaml`

#### Chart
- **Name:** `plex-media-server`
- **Repository:** `plex`
- **Current Version:** `0.9.1`
- **Latest Version:** `1.4.0` ⚠️ **UPDATE AVAILABLE**
- **Update Type:** 🔴 **MAJOR** (high complexity)
- **Update Description:** Major version update: 0.x.x → 1.x.x
- **Source:** https://github.com/plexinc/pms-docker/releases/tag/1.4.0
- **Release Notes:** *Could not fetch release notes (GitHub API rate limit or release not found). Check source link above.*
- **⚠️ Breaking Changes:** *Major version update - review release notes above for breaking changes*

#### Container Images
- **Repository:** `plexinc/pms-docker`
  - **Path:** `image`
  - **Current Tag:** `1.42.1.10060-4e8b05daf`
  - **Latest Tag:** `1.3.2.3112-1751929` ⚠️ **UPDATE AVAILABLE**
  - **Update Type:** 🟢 **PATCH** (low complexity)
  - **Update Description:** Patch version update: 1.42.1 → 1.42.2
  - **Source:** https://github.com/plexinc/pms-docker/releases/tag/1.3.2.3112-1751929
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

### opentelemetry-operator

- **File:** `kubernetes/apps/monitoring/opentelemetry-operator/app/helmrelease.yaml`

#### Chart
- **Name:** `opentelemetry-operator`
- **Repository:** `opentelemetry`
- **Current Version:** `0.66.0`
- **Latest Version:** `0.102.0` ⚠️ **UPDATE AVAILABLE**
- **Update Type:** 🟡 **MINOR** (medium complexity)
- **Update Description:** Minor version update: 0.66.x → 0.102.x
- **Source:** https://github.com/open-telemetry/opentelemetry-helm-charts/releases/tag/0.102.0
- **Release Notes:** *Could not fetch release notes (GitHub API rate limit or release not found). Check source link above.*
- **⚠️ Breaking Changes:** *Review release notes above for potential breaking changes*

*No container images specified in values*

---

### otel-collector

- **File:** `kubernetes/apps/monitoring/otel-collector/app/helmrelease.yaml`

#### Chart
- **Name:** `opentelemetry-collector`
- **Repository:** `opentelemetry`
- **Current Version:** `0.92.0`
- **Latest Version:** `0.143.0` ⚠️ **UPDATE AVAILABLE**
- **Update Type:** 🟡 **MINOR** (medium complexity)
- **Update Description:** Minor version update: 0.92.x → 0.143.x
- **Source:** https://github.com/opentelemetry-collector/opentelemetry-collector/releases/tag/0.143.0
- **Release Notes:** *Could not fetch release notes (GitHub API rate limit or release not found). Check source link above.*
- **⚠️ Breaking Changes:** *Review release notes above for potential breaking changes*

#### Container Images
- **Repository:** `otel/opentelemetry-collector-contrib`
  - **Path:** `image`
  - **Current Tag:** ``
  - **Latest Tag:** `0.2.10` ⚠️ **UPDATE AVAILABLE**
  - **Update Type:** ⚪ **UNKNOWN** (unknown complexity)
  - **Update Description:** Version format not recognized
  - **Source:** https://github.com/otel/opentelemetry-collector-contrib/releases/tag/0.2.10
  - **Release Notes:** *Could not fetch release notes (GitHub API rate limit or release not found). Check source link above.*

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
  - **Current Tag:** `2.0.0-beta.2`
  - **Latest Tag:** `1.0.1` ⚠️ **UPDATE AVAILABLE**
  - **Update Type:** 🟢 **PATCH** (low complexity)
  - **Update Description:** Patch version update: 2.0.0 → 2.0.1
  - **Source:** https://github.com/louislam/uptime-kuma/releases/tag/1.0.1
  - **Release Date:** 2021-07-12
  - **Release Notes:**
    ```markdown
    - Fix some bugs reported by the community. #5 #10 
- Ability to change the listening port and hostname for someone who directly run the server without Docker.
    ```

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
  - **Current Tag:** `v0.107.65`
  - **Latest Tag:** `v0.93` ⚠️ **UPDATE AVAILABLE**
  - **Update Type:** ⚪ **UNKNOWN** (unknown complexity)
  - **Update Description:** Versions appear equal or downgrade detected
  - **Source:** https://github.com/adguard/adguardhome/releases/tag/v0.93
  - **Release Notes:** *Could not fetch release notes (GitHub API rate limit or release not found). Check source link above.*

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
  - **Current Tag:** `2.20.3`
  - **Latest Tag:** `2.20.3` ✅ (up-to-date)

- **Repository:** `bitnamilegacy/mariadb`
  - **Path:** `mariadb.image`
  - **Current Tag:** `latest`
  - **Latest Tag:** `0.0.1` ✅ (up-to-date)

- **Repository:** `bitnamilegacy/redis`
  - **Path:** `redis.image`
  - **Current Tag:** `latest`
  - **Latest Tag:** `3.2.0-r1` ✅ (up-to-date)

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
