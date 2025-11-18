# Kubernetes Cluster Update TODO

**Last Updated**: 2025-11-18
**Cluster**: cberg-home-nextgen

---

## Update Tracking

### 🔴 Critical Updates

#### 1. Cilium - CNI & Network Policy
- **Current**: v1.17.1
- **Latest**: v1.18.4
- **Status**: ⏸️ Pending
- **Check URL**: https://github.com/cilium/cilium/releases
- **Helm Chart**: https://github.com/cilium/charts
- **Docs**: https://docs.cilium.io/en/stable/operations/upgrade/
- **Risk**: Medium (core networking)
- **Action**: Test in staging first, review upgrade notes
- **Breaking Changes**: Check v1.18 release notes for CRD updates

#### 2. cert-manager - Certificate Management
- **Current**: v1.17.1
- **Latest**: v1.19.1
- **Status**: ✅ Safe to update
- **Check URL**: https://github.com/cert-manager/cert-manager/releases
- **Helm Chart**: https://cert-manager.io/docs/installation/helm/
- **Docs**: https://cert-manager.io/docs/installation/upgrading/
- **Risk**: Low
- **Action**: Update chart version in helmrelease.yaml

#### 3. kube-prometheus-stack - Monitoring
- **Current**: 68.4.4
- **Latest**: 79.5.0
- **Status**: ⚠️ Review needed
- **Check URL**: https://github.com/prometheus-community/helm-charts/releases
- **Helm Chart**: https://github.com/prometheus-community/helm-charts/tree/main/charts/kube-prometheus-stack
- **Docs**: https://github.com/prometheus-community/helm-charts/tree/main/charts/kube-prometheus-stack#upgrading-chart
- **Risk**: Medium (11 versions behind)
- **Action**: Review changelogs from v68 to v79, check CRD updates
- **Notes**: Includes Prometheus Operator updates, may require CRD updates

#### 4. Authentik - Authentication
- **Current**: 2025.10.1 ✅ **UPDATED 2025-11-18**
- **Latest**: 2025.10.1
- **Status**: ✅ Updated and running
- **Check URL**: https://github.com/goauthentik/authentik/releases
- **Helm Chart**: https://charts.goauthentik.io
- **Docs**: https://docs.goauthentik.io/docs/installation/kubernetes
- **Risk**: Low-Medium
- **Action**: ✅ Completed
- **Update Details**:
  - Upgraded from 2025.8.4 → 2025.10.1
  - **Breaking Change**: Redis completely removed, migrated to PostgreSQL for caching/WebSockets/scheduling
  - Disabled Redis in helmrelease.yaml (`enabled: false`)
  - **Worker Probe Workaround**: Set worker probes to `null` due to bug in 2025.10.1
    - Issue: Workers try to connect to port 9000 (server port) instead of checking heartbeat file
    - Official fix in PR #18090 scheduled for 2025.10.2 (not yet released)
    - Our Helm override pre-implements the official fix
  - Increased upgrade timeout to 30m for migration
  - All 3 server pods + 3 worker pods running healthy
- **Next Action**: Update to 2025.10.2 when released, may be able to remove worker probe workaround

#### 5. Nextcloud Helm Chart
- **Current**: 6.6.4
- **Latest**: 8.5.2
- **Status**: ⚠️ Major version - backup first
- **Check URL**: https://github.com/nextcloud/helm/releases
- **Helm Chart**: https://github.com/nextcloud/helm
- **Docs**: https://github.com/nextcloud/helm/blob/main/charts/nextcloud/README.md
- **Risk**: High (major chart version)
- **Action**: Backup database, review chart values changes, test upgrade path
- **Breaking Changes**: Review 7.x and 8.x changelog for values structure changes

---

### 🟡 Recommended Updates

#### 6. Open WebUI
- **Current**: v0.6.34
- **Latest**: v0.6.36
- **Status**: ✅ Safe to update
- **Check URL**: https://github.com/open-webui/open-webui/releases
- **Container**: ghcr.io/open-webui/open-webui
- **Action**: Update image tag in helmrelease.yaml

#### 7. Grafana
- **Current**: 10.2.2
- **Latest**: v12.2.1
- **Status**: ⚠️ Major version (v10 → v12)
- **Check URL**: https://github.com/grafana/grafana/releases
- **Docs**:
  - https://grafana.com/docs/grafana/latest/whatsnew/whats-new-in-v11-0/
  - https://grafana.com/docs/grafana/latest/whatsnew/whats-new-in-v12-0/
- **Risk**: Medium (test dashboards)
- **Action**: Test dashboard compatibility, review plugin support

#### 8. ESPHome
- **Current**: 2025.8.3
- **Latest**: 2025.10.5
- **Status**: ✅ Safe to update
- **Check URL**: https://github.com/esphome/esphome/releases
- **Container**: ghcr.io/esphome/esphome
- **Action**: Update image tag

#### 9. Jellyfin
- **Current**: 10.11.0-rc2 (Release Candidate)
- **Latest**: v10.11.3 (Stable)
- **Status**: ✅ Update to stable
- **Check URL**: https://github.com/jellyfin/jellyfin/releases
- **Container**: docker.io/jellyfin/jellyfin
- **Action**: Update from RC to stable release

#### 10. metrics-server
- **Current**: v0.7.2
- **Latest**: v0.8.0
- **Status**: ✅ Safe to update
- **Check URL**: https://github.com/kubernetes-sigs/metrics-server/releases
- **Helm Chart**: https://github.com/kubernetes-sigs/metrics-server
- **Action**: Update chart version

---

### 🟢 Maintenance Tasks

#### 11. Pin `:latest` Container Tags
**Status**: ⏳ In Progress

Images to pin:
- [ ] dpage/pgadmin4:latest → Find specific version
- [ ] iib0011/omni-tools:latest → Find specific version
- [ ] ghcr.io/alams154/music-assistant-alexa-api:latest → Find specific version
- [ ] ghcr.io/open-webui/pipelines:main → Use version tags
- [ ] bbilly1/tubearchivist:latest → Find specific version
- [ ] bbilly1/tubearchivist-es:latest → Find specific version

**Check Commands**:
```bash
# Check pgadmin versions
curl -s https://registry.hub.docker.com/v2/repositories/dpage/pgadmin4/tags?page_size=10 | jq -r '.results[].name'

# Check omni-tools versions
curl -s https://registry.hub.docker.com/v2/repositories/iib0011/omni-tools/tags?page_size=10 | jq -r '.results[].name'

# Check tubearchivist versions
curl -s https://registry.hub.docker.com/v2/repositories/bbilly1/tubearchivist/tags?page_size=10 | jq -r '.results[].name'
```

#### 12. Standardize app-template Versions
**Status**: ⏳ In Progress

Current distribution:
- 3.7.1: 12 apps ✅ (target version)
- 3.6.1: 1 app (makemkv)
- 3.6.0: 6 apps (ai-sre, bytebot, mcpo, mosquitto, scrypted, omni-tools)
- 2.4.0: 1 app (iobroker) ⚠️ **Staying on 2.4.0** (see notes)

**Action Items**:
- [x] ~~Update iobroker: 2.4.0 → 3.7.1~~ **NOT COMPATIBLE** - Keeping on 2.4.0
  - **Reason**: Ingress schema incompatible between versions, 3.7.1 requires different service reference format
  - **Fixed on 2.4.0**: Updated probe configuration to use port 8081, added 20m timeout
  - **Status**: Running stable on 2.4.0, no issues
- [ ] Update makemkv: 3.6.1 → 3.7.1
- [ ] Update ai-sre, bytebot, mcpo: 3.6.0 → 3.7.1
- [ ] Update mosquitto: 3.6.0 → 3.7.1
- [ ] Update scrypted: 3.6.0 → 3.7.1
- [ ] Update omni-tools: 3.6.0 → 3.7.1

**Check URL**: https://github.com/bjw-s/helm-charts
**Chart Location**: oci://ghcr.io/bjw-s/helm/app-template

---

## Update Execution Log

### 2025-11-18 - Authentik 2025.10.1 Upgrade & iobroker Fixes
**Completed Updates:**
- [x] **Authentik**: 2025.8.4 → 2025.10.1
  - Disabled Redis (removed in 2025.10.x)
  - Migrated to PostgreSQL for all caching/scheduling
  - Applied worker probe workaround for 2025.10.1 bug (pre-implements 2025.10.2 fix)
  - All 3 server + 3 worker pods healthy
  - Files: `kubernetes/apps/kube-system/authentik/app/helmrelease.yaml`
  - Commits: `1ca9015`, `15db185`

**Completed Fixes:**
- [x] **iobroker**: Health check and timeout issues
  - Fixed probes to use port 8081 (admin UI) instead of localhost-only ports
  - Added 20m timeout for slow StatefulSet startup
  - Stays on app-template 2.4.0 due to 3.7.1 incompatibility
  - Pod: 1/1 Running (Ready)
  - File: `kubernetes/apps/home-automation/iobroker/app/helm-release.yaml`
  - Commit: `57e417f`

**Research Findings:**
- Worker probes were intentionally added in PR #255 (April 2024)
- 2025.10.1 has confirmed bug (Issue #17923) where worker healthcheck tries port 9000
- Official fix in PR #18090 removes worker HTTP healthcheck (scheduled for 2025.10.2)
- Our solution pre-implements the official fix via Helm value override

### 2025-11-18 - Initial Assessment
- [x] Completed version audit
- [x] Identified 15+ components with updates available
- [x] Prioritized updates by risk and impact
- [x] Created update plan

### Safe Updates (Week 1)
- [ ] cert-manager: v1.17.1 → v1.19.1
- [x] **Authentik: 2025.8.4 → 2025.10.1** ✅ **COMPLETED 2025-11-18**
- [ ] Jellyfin: 10.11.0-rc2 → 10.11.3 (stable)
- [ ] metrics-server: v0.7.2 → v0.8.0
- [ ] Open WebUI: v0.6.34 → v0.6.36
- [ ] ESPHome: 2025.8.3 → 2025.10.5
- [ ] Pin all `:latest` tags
- [x] ~~Standardize app-template to 3.7.1~~ (Partial - iobroker incompatible)

### Medium-Risk Updates (Week 2-3)
- [ ] Cilium: v1.17.1 → v1.18.4 (TEST FIRST)
- [ ] kube-prometheus-stack: 68.4.4 → 79.x (review changes)

### Major Updates (Week 4+)
- [ ] Nextcloud: 6.6.4 → 8.5.2 (backup + test)
- [ ] Grafana: 10.2.2 → 12.2.1 (test dashboards)

---

## Version Check URLs

### Helm Repositories
```bash
# Check Helm repo indices
helm repo add bitnami oci://registry-1.docker.io/bitnamicharts
helm search repo bitnami/mariadb --versions | head -5

helm repo add prometheus-community oci://ghcr.io/prometheus-community/charts
helm search repo prometheus-community/kube-prometheus-stack --versions | head -5
```

### GitHub Release APIs
```bash
# Cilium
curl -s https://api.github.com/repos/cilium/cilium/releases/latest | jq -r '.tag_name'

# cert-manager
curl -s https://api.github.com/repos/cert-manager/cert-manager/releases/latest | jq -r '.tag_name'

# Authentik
curl -s https://api.github.com/repos/goauthentik/authentik/releases/latest | jq -r '.tag_name'

# Home Assistant
curl -s https://api.github.com/repos/home-assistant/core/releases/latest | jq -r '.tag_name'

# Jellyfin
curl -s https://api.github.com/repos/jellyfin/jellyfin/releases/latest | jq -r '.tag_name'

# Grafana
curl -s https://api.github.com/repos/grafana/grafana/releases/latest | jq -r '.tag_name'

# Open WebUI
curl -s https://api.github.com/repos/open-webui/open-webui/releases/latest | jq -r '.tag_name'

# Frigate
curl -s https://api.github.com/repos/blakeblackshear/frigate/releases/latest | jq -r '.tag_name'

# ESPHome
curl -s https://api.github.com/repos/esphome/esphome/releases/latest | jq -r '.tag_name'

# Longhorn
curl -s https://api.github.com/repos/longhorn/longhorn/releases/latest | jq -r '.tag_name'
```

### Container Registries
```bash
# Docker Hub
curl -s "https://registry.hub.docker.com/v2/repositories/{user}/{image}/tags?page_size=10" | jq -r '.results[].name'

# GitHub Container Registry
# Use GitHub releases API or browse at https://github.com/{user}/{repo}/pkgs/container/{image}
```

---

## Pre-Update Checklist

Before any update:
- [ ] Review release notes and changelog
- [ ] Check for breaking changes
- [ ] Verify Longhorn backups are current
- [ ] Check Flux reconciliation status: `flux get kustomizations -A`
- [ ] Note current pod status: `kubectl get pods -A`
- [ ] Plan rollback strategy
- [ ] Test in development if available

---

## Rollback Procedures

### Helm Chart Rollback
```bash
# Check history
helm history {release} -n {namespace}

# Rollback to previous version
helm rollback {release} -n {namespace}

# Or via Flux
flux suspend helmrelease {name} -n {namespace}
# Edit helmrelease.yaml back to previous version
flux resume helmrelease {name} -n {namespace}
```

### Container Image Rollback
```bash
# Edit deployment/helmrelease
# Change image tag back to previous version
# Commit and push
git add . && git commit -m "rollback: revert {app} to {version}" && git push
flux reconcile kustomization {app} -n {namespace}
```

---

## Notes

- Always update Flux first before updating cluster components
- CRD updates may require manual application before Helm chart updates
- Test network-related updates (Cilium, Ingress) during low-traffic periods
- Monitor Longhorn storage health after updates
- Check Authentik authentication flow after auth-related updates

---

**Last Review**: 2025-11-18
**Next Review**: 2025-11-25
