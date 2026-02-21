# Pending Updates Todo List

**Generated:** 2026-02-21
**Source:** `AI_version_check_current.md` + Renovate Dashboard issue #7

---

## Status Legend

- `[ ]` Not started
- `[~]` In progress / needs investigation
- `[x]` Done
- `[!]` Blocked

---

## 🟢 Patch Updates (Safe to Apply)

These are low-risk, no PRs open — approve in Renovate dashboard or apply manually.

- [ ] **authentik** `kube-system` — chart `2025.12.3` → `2025.12.4`
  - Approve in Renovate dashboard to generate PR
- [ ] **vaultwarden** `default` — image `1.35.2` → `1.35.3`
  - Approve in Renovate dashboard to generate PR
- [ ] **adguard-home** `network` — image `v0.107.71` → `v0.107.72`
  - Approve in Renovate dashboard to generate PR
- [ ] **node-red** `home-automation` — image `4.1.4` → `4.1.5`
  - Approve in Renovate dashboard to generate PR

---

## 🟡 Minor Updates (Generally Safe)

- [ ] **longhorn** `storage` — chart `1.10.1` → `1.11.0`
  - Review release notes before applying
  - Approve in Renovate dashboard to generate PR
- [ ] **cilium** `default` — chart `1.18.6` → `1.19.1` ⚠️ **APPLY LAST**
  - Network component — apply in low-traffic window
  - Approve in Renovate dashboard to generate PR
  - **⚠️ Home Assistant had issues after a previous cilium upgrade — run full post-update checklist:**
    - [ ] **mDNS cross-VLAN** — HA can still discover IoT devices (192.168.32.0/23) from k8s-network; test `.local` hostname resolution from HA pod
    - [ ] **UPnP/SSDP** — HA UPnP integration still shows devices (media players, routers)
    - [ ] **MQTT** — mosquitto reachable, HA MQTT integration shows connected (`kubectl logs -n home-automation -l app.kubernetes.io/name=home-assistant | grep -i mqtt`)
    - [ ] **Network auto-discovery** — Sonos, Chromecast, other network-discovered devices still appear in HA integrations (no "unavailable")
    - [ ] **ESPHome** — devices still connecting (`kubectl logs -n home-automation -l app.kubernetes.io/name=esphome | grep -i connect`)
    - [ ] **CiliumNetworkPolicy audit** — check if new policies block multicast/broadcast traffic
- [ ] **descheduler** `default` — chart `0.34.0` → `0.35.0`
  - Approve in Renovate dashboard to generate PR
- [ ] **intel-device-plugin-gpu** `default` — chart `0.34.1` → `0.35.0`
  - Approve in Renovate dashboard to generate PR
- [ ] **intel-device-plugin-operator** `default` — chart `0.34.1` → `0.35.0`
  - Approve in Renovate dashboard to generate PR (apply together with gpu plugin)
- [ ] **unpoller** `monitoring` — image `v2.33.0` → `2.34.0`
  - Approve in Renovate dashboard to generate PR
- [ ] **penpot** `office` — chart `0.33.0` → `0.35.0`
  - Approve in Renovate dashboard to generate PR

---

## 🔴 Major Updates (Breaking Changes — Research Required)

### mariadb `databases` — chart `11.5.7` → `25.0.0`

- [!] **BLOCKED** — PR was previously open and closed. The chart jump from 11.x to 25.x is a complete
  Bitnami re-versioning, not a MariaDB engine major version bump.
- Known issues:
  - Legacy image format no longer accepted (no explicit tag)
  - Password injection breaking change in Bitnami chart
- TODO:
  - [ ] Read Bitnami MariaDB chart 24.x/25.x migration guide
  - [ ] Check current chart values for any deprecated fields
  - [ ] Test migration procedure (dump/restore may be required)
  - [ ] Approve in Renovate dashboard once migration plan is ready

### nextcloud `default` — chart `6.6.10` → `8.9.1`

- [ ] Review nextcloud chart changelog for 7.x and 8.x breaking changes
- [ ] Check current values for deprecated fields
- [ ] Ensure `notify_push` binary path fix (PR #0ddd363) is compatible with new chart
- [ ] Approve in Renovate dashboard once validated

### open-webui `default` — chart `10.2.1` → `12.3.0`

- [ ] Review chart changelog for breaking changes in 11.x and 12.x
- [ ] Check if image tag pinning is needed (currently `0.7.2`)
- [ ] Approve in Renovate dashboard once validated

### n8n `home-automation` — image `1.123.21` → `2.9.1` (PR #40 open)

- [!] **BLOCKED** — PR #40 is open but not mergeable as-is
- Known blockers:
  - Chart `1.1.0` does not support n8n v2
  - Task runner architecture changed in v2 (external runner required)
  - Migration tool needed for workflow data
- TODO:
  - [ ] Check if n8n chart `2.x` is available (`helm search repo n8n`)
  - [ ] Review n8n v2 migration documentation
  - [ ] Update helmrelease to use chart `2.x` with correct values
  - [ ] Plan data migration if required
  - [ ] Close or update PR #40 once chart is ready

### eck-operator `monitoring` — chart `2.14.0` → `3.3.0`

- [ ] Review ECK operator 3.x migration guide (major API changes likely)
- [ ] Check if Elasticsearch/Kibana CRD versions need updating
- [ ] Approve in Renovate dashboard once validated

### uptime-kuma `monitoring` — chart `2.25.0` → `4.0.0`, image `2.1.0` → `2.1.3`

- [ ] Review uptime-kuma chart 3.x and 4.x changelogs
- [ ] Check for data migration requirements
- [ ] Note: image patch `2.1.0` → `2.1.3` can be applied independently if chart update is deferred

---

## 🔧 Infrastructure / Tooling Updates (Pending Approval in Renovate)

These need to be approved in the Renovate dashboard before PRs are created.

- [ ] **Flux CRD API bumps** — `HelmRelease` → `helm.toolkit.fluxcd.io/v2`, `HelmRepository` → `source.toolkit.fluxcd.io/v1`, `ImagePolicy/Repository/UpdateAutomation` → `v1`
  - Low risk but broad change (touches many files)
  - Renovate can handle this automatically once approved
- [ ] **app-template** `3.7.1` → `3.7.3` (patch)
- [ ] **Flux operator group** `0.14.0` → `0.40.0` (minor) — flux-instance + flux-operator + charts
- [ ] **Talos upgrade** `v1.11.0` → `v1.12.2` (node drain + upgrade procedure required)
- [ ] **Kubernetes upgrade** `v1.34.0` → `v1.35.0` (node drain + upgrade procedure required)
  - Note: cluster is currently running `v1.34.0` but desired state in talconfig is `v1.34.3` — reconcile that first
- [ ] **aqua tooling** — talhelper, yq, task, helm, helmfile minor/major bumps
  - Approve batch in Renovate dashboard

---

## ⚠️ Renovate Lookup Failures (Need Manual Fix)

Renovate cannot look up these packages — they may need configuration fixes:

- [ ] `ghcr.io/nachtschatt3n/andreamosteller.com` — package not found
  - File: `kubernetes/apps/my-software-production/andreamosteller/app/helmrelease.yaml`
  - Check if image exists in GHCR and if the reference is correct
- [ ] `nachtschatt3n/k8s-self-ai-ops` — github-tags lookup failed
  - File: `kubernetes/flux/meta/repositories/git/k8s-self-ai-ops.yaml`
  - Check if the repo is public and the reference format is correct

---

## Recommended Order

1. **Now (safe):** Approve all 🟢 patch items in Renovate dashboard
2. **Soon:** Approve 🟡 minor items (longhorn, cilium last — network-sensitive)
3. **Research first:** Work through 🔴 major items one at a time, starting with the simpler ones (eck-operator, uptime-kuma)
4. **Complex migration:** mariadb and n8n require dedicated migration planning sessions
5. **Infrastructure:** Talos/Kubernetes upgrades last — requires cluster maintenance window
