# Phase 3 Migration Guide - Major Version Updates

**Generated:** 2026-01-11

This document outlines the migration paths for Phase 3 major version updates. These updates require careful planning, testing, and potentially manual intervention.

## Overview

Phase 3 includes 6 major version updates:
1. **kubernetes-dashboard**: 6.0.8 → 7.14.0 (1 major version)
2. **eck-operator**: 2.14.0 → 3.2.0 (1 major version)
3. **plex**: 0.9.1 → 1.4.0 (1 major version)
4. **grafana**: 7.0.19 → 10.5.5 (3 major versions!)
5. **nextcloud**: 6.6.4 → 8.7.0 (2 major versions)
6. **open-webui**: 5.13.0 → 10.1.0 (5 major versions!)

---

## 1. Kubernetes Dashboard: 6.0.8 → 7.14.0

### Current State
- **Chart Version**: 6.0.8
- **Location**: `kubernetes/apps/monitoring/kubernetes-dashboard/app/helmrelease.yaml`
- **Namespace**: `monitoring`
- **Current Configuration**:
  - Ingress enabled with Authentik forward auth
  - Extra args: `--enable-insecure-login`, `--enable-skip-login`, `--disable-settings-authorizer`
  - Metrics scraper enabled

### Migration Path

#### Step 1: Review Breaking Changes
- Kubernetes Dashboard v7.x requires Kubernetes 1.25+ (verify cluster version)
- API changes in authentication and RBAC
- UI/UX changes in the dashboard interface

#### Step 2: Backup Current Configuration
```bash
# Export current HelmRelease
kubectl get helmrelease kubernetes-dashboard -n monitoring -o yaml > kubernetes-dashboard-backup.yaml

# Export current values
helm get values kubernetes-dashboard -n monitoring > kubernetes-dashboard-values-backup.yaml
```

#### Step 3: Update Process
1. **Update HelmRelease version**:
   ```yaml
   spec:
     chart:
       spec:
         version: 7.14.0
   ```

2. **Review and update values**:
   - **Ingress**: Verify `ingress.className: internal` still works
   - **Authentik annotations**: Should remain compatible, but verify
   - **Extra args**: Check if `--enable-insecure-login` and `--enable-skip-login` are still valid
   - **Metrics scraper**: Verify `metricsScraper.enabled: true` is still supported
   - **Homepage annotations**: Should remain compatible

#### Step 4: Testing
- Test dashboard access after upgrade
- Verify RBAC permissions still work
- Check metrics scraping functionality

### Risk Level: **Medium**
- Dashboard is typically read-only, lower risk
- May require RBAC adjustments

---

## 2. ECK Operator: 2.14.0 → 3.2.0

### Current State
- **Chart Version**: 2.14.0
- **Location**: `kubernetes/apps/monitoring/eck-operator/app/helmrelease.yaml`
- **Namespace**: `monitoring`
- **CRDs**: Installed via `installCRDs: true`
- **Current Configuration**:
  - `createClusterScopedResources: true`
  - Resource limits: 50m CPU, 128Mi-256Mi memory
  - No nodeSelector or tolerations

### Migration Path

#### Step 1: Critical Pre-Migration Checks
⚠️ **IMPORTANT**: ECK 3.x has significant breaking changes

1. **Backup all Elasticsearch clusters**:
   ```bash
   # List all Elasticsearch resources
   kubectl get elasticsearch -A
   
   # Backup each cluster's data (use snapshot repository)
   # Verify backups are restorable
   ```

2. **Check current Elasticsearch versions**:
   ```bash
   kubectl get elasticsearch -A -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.version}{"\n"}{end}'
   ```

#### Step 2: Review Breaking Changes (ECK 3.0)
Based on release notes and documentation:
- **Elastic Stack 9.0.0 Support**: ECK 3.0+ supports Elastic Stack 9.0.0 (requires operator 3.0+)
- **Enterprise Search Deprecation**: Standalone Enterprise Search deprecated (if you use it)
- **CRD API changes**: Some Elasticsearch CRD fields may have changed
- **Operator behavior**: New automatic PodDisruptionBudget features (Enterprise feature)
- **Password generation**: Default password length increased to 24 chars (configurable up to 72)
- **Certificate reloading**: New features for stack monitoring Beats
- **GOMEMLIMIT**: Automatically set based on cgroups memory limits

#### Step 3: Update Process

1. **Update CRDs first** (critical):
   ```bash
   # ECK 3.x may require CRD updates
   # The chart has `crds: CreateReplace` which should handle this
   # But verify CRD compatibility first
   ```

2. **Update HelmRelease**:
   ```yaml
   spec:
     chart:
       spec:
         version: 3.2.0
   ```

3. **Review values for changes**:
   - Check if any values are deprecated
   - Verify resource limits are appropriate
   - Review nodeSelector/tolerations if needed

#### Step 4: Post-Upgrade Verification
```bash
# Check operator is running
kubectl get pods -n monitoring -l control-plane=elastic-operator

# Verify Elasticsearch clusters are healthy
kubectl get elasticsearch -A

# Check for any error events
kubectl get events -n monitoring --sort-by='.lastTimestamp' | grep -i elastic
```

### Risk Level: **High**
- ECK manages critical Elasticsearch clusters
- CRD changes may affect existing resources
- **Recommendation**: Test in non-production first, have backups ready

---

## 3. Plex Media Server: 0.9.1 → 1.4.0

### Current State
- **Chart Version**: 0.9.1
- **Location**: `kubernetes/apps/media/plex/app/helmrelease.yaml`
- **Namespace**: `media`
- **Image**: `plexinc/pms-docker:1.42.1.10060-4e8b05daf`
- **Storage**: Uses PVC `plex-config` and `plex-media-smb`

### Migration Path

#### Step 1: Backup
- **Plex database/config**: Already in PVC `plex-config` (should persist)
- **Media files**: In PVC `plex-media-smb` (should persist)
- **Optional**: Export Plex library metadata

#### Step 2: Review Chart Changes
- Chart v1.x may have different value structure
- Check for changes in:
  - Service configuration
  - Ingress settings
  - Resource requirements
  - GPU/transcoding settings

#### Step 3: Update Process

1. **Update HelmRelease**:
   ```yaml
   spec:
     chart:
       spec:
         version: 1.4.0
   ```

2. **Review current values**:
   - GPU configuration (`gpu.intel.com/i915`)
   - Volume mounts (config and media)
   - Environment variables
   - Probes configuration

3. **Update image tag** (if needed):
   ```yaml
   values:
     image:
       tag: 1.3.2.3112-1751929  # Latest available
   ```

#### Step 4: Post-Upgrade
- Verify Plex is accessible
- Check transcoding still works
- Verify library/media access

### Risk Level: **Low-Medium**
- Media server, less critical than infrastructure
- Data in PVCs should persist
- May need to re-scan library

---

## 4. Grafana: 7.0.19 → 10.5.5

### Current State
- **Chart Version**: 7.0.19
- **Location**: `kubernetes/apps/monitoring/grafana/app/helmrelease.yaml`
- **Namespace**: `monitoring`
- **Storage**: Uses PVC `grafana-config` (existingClaim)
- **Complex Configuration**:
  - Multiple dashboard providers (default, flux, kubernetes, nginx, teslamate)
  - Multiple datasources (Prometheus, TeslaMate PostgreSQL)
  - Custom `grafana.ini` configuration
  - Ingress with internal class
  - Admin secret from existing secret
  - Sidecar for dashboards and datasources
  - ServiceMonitor enabled

### Migration Path

⚠️ **CRITICAL**: This is a **3 major version jump** (7 → 8 → 9 → 10)

#### Step 1: Comprehensive Backup
```bash
# Backup Grafana configuration PVC
kubectl get pvc grafana-config -n monitoring

# Export all dashboards via API (if possible)
# Or ensure PVC backup is recent

# Export datasource configuration
kubectl get configmap -n monitoring | grep grafana
```

#### Step 2: Review Major Breaking Changes

**Grafana 8.x Breaking Changes:**
- Plugin system changes
- Dashboard JSON format updates
- Datasource API changes
- Authentication changes
- **Values.yaml changes**: Some value paths may have changed

**Grafana 9.x Breaking Changes:**
- New unified alerting system (replaces legacy alerts)
- Dashboard permissions model changes
- Plugin compatibility updates
- **Values.yaml changes**: Further structural changes

**Grafana 10.x Breaking Changes:**
- Further plugin system updates
- UI/UX changes
- API changes
- **Values.yaml changes**: Additional value structure updates

**Important**: For major version upgrades, Helm requires `--force` flag due to label changes.

#### Step 3: Staged Migration Approach

**Option A: Direct Jump (Risky)**
- Update directly to 10.5.5
- Requires thorough testing
- May miss intermediate migration steps

**Option B: Staged Migration (Recommended)**
1. **First**: Update to 8.x (test thoroughly)
2. **Second**: Update to 9.x (test thoroughly)
3. **Third**: Update to 10.x (test thoroughly)

#### Step 4: Update Process

1. **Compare values** (critical step):
   ```bash
   # Get current values
   helm get values grafana -n monitoring > grafana-current-values.yaml
   
   # Get new default values
   helm show values grafana/grafana --version 10.5.5 > grafana-new-defaults.yaml
   
   # Compare
   diff grafana-current-values.yaml grafana-new-defaults.yaml
   ```

2. **Review values for deprecated options**:
   - **grafana.ini**: Structure may have changed - verify all sections
   - **dashboardProviders**: Format may have changed
   - **datasources**: API version and structure changes
   - **sidecar**: Configuration may have changed
   - **persistence**: Verify `existingClaim` still works
   - **ingress**: Check `ingressClassName` vs `className`

3. **Update HelmRelease**:
   ```yaml
   spec:
     chart:
       spec:
         version: 10.5.5
   ```
   
   **Note**: Flux may need to use `--force` for major upgrades. Check if Flux handles this automatically.

4. **Verify persistence**:
   - Ensure `grafana-config` PVC is properly mounted
   - Check that `persistence.enabled: true` and `persistence.existingClaim: grafana-config` are set

#### Step 5: Post-Upgrade Checklist
- [ ] Grafana UI accessible
- [ ] All dashboards load correctly
- [ ] Datasources connect (Prometheus, TeslaMate PostgreSQL)
- [ ] Alerts/notifications working
- [ ] Custom dashboards render properly
- [ ] User authentication works
- [ ] Plugins (if any) are compatible

### Risk Level: **High**
- 3 major versions = many breaking changes
- Complex configuration with many dashboards
- **Recommendation**: 
  - Consider staged migration (8 → 9 → 10)
  - Test in staging first
  - Have full backup of PVC
  - Plan for dashboard/datasource fixes

---

## 5. Nextcloud: 6.6.4 → 8.7.0

### Current State
- **Chart Version**: 6.6.4
- **Location**: `kubernetes/apps/office/nextcloud/app/helmrelease.yaml`
- **Image**: `nextcloud:32.0.2`
- **Database**: MariaDB (bitnamilegacy/mariadb:latest)
- **Storage**: 
  - PVC `nextcloud-config` (main config)
  - PVC `nextcloud-data` (user data)
  - PVC `nextcloud-mariadb` (database)
- **Complex Configuration**:
  - Custom PHP configs (memory limits, opcache)
  - Custom Nextcloud config (custom.config.php)
  - Redis enabled
  - Worker sidecar container
  - Cronjob enabled
  - Metrics exporter
  - Ingress with extensive annotations

### Migration Path

⚠️ **CRITICAL**: This is a **2 major version jump** (6 → 7 → 8)

#### Step 1: Critical Backup
```bash
# 1. Backup MariaDB database
kubectl get pods -n office -l app.kubernetes.io/name=mariadb
kubectl exec -n office <mariadb-pod> -- mysqldump -u nextcloud -p nextcloud > nextcloud-db-backup-$(date +%Y%m%d).sql

# 2. Backup PVCs (via Longhorn snapshots or manual backup)
kubectl get pvc -n office | grep nextcloud
# - nextcloud-config (configuration)
# - nextcloud-data (user files)
# - nextcloud-mariadb (database)

# 3. Export current Helm values
helm get values nextcloud -n office > nextcloud-current-values.yaml

# 4. Optional: Export Nextcloud config via occ command
kubectl exec -n office <nextcloud-pod> -- php occ config:export > nextcloud-config-export.json
```

#### Step 2: Review Breaking Changes

**Nextcloud Chart 7.x:**
- Value structure changes
- Database migration requirements
- PHP version requirements

**Nextcloud Chart 8.x:**
- Further value changes
- Nextcloud app version compatibility
- Database schema updates

#### Step 3: Database Migration
Nextcloud requires database migrations between major versions:
- **6.x → 7.x**: Database schema changes
- **7.x → 8.x**: Additional schema changes

**Process:**
1. Nextcloud will auto-migrate on first startup
2. Ensure database is accessible
3. Monitor migration logs
4. May take time depending on data size

#### Step 4: Update Process

1. **Compare values structure**:
   ```bash
   # Get new chart values
   helm show values nextcloud/nextcloud --version 8.7.0 > nextcloud-new-values.yaml
   
   # Compare with current
   diff nextcloud-current-values.yaml nextcloud-new-values.yaml
   ```

2. **Update HelmRelease**:
   ```yaml
   spec:
     chart:
       spec:
         version: 8.7.0
   ```

3. **Review values for changes**:
   - **Image**: May need to update to compatible Nextcloud version
   - **Ingress**: Check if structure changed (your config uses complex ingress with paths)
   - **nextcloud.configs**: Verify custom.config.php structure still works
   - **nextcloud.phpConfigs**: Check if format changed
   - **extraSidecarContainers**: Verify worker container config still works
   - **mariadb**: Check if bitnamilegacy registry still supported
   - **redis**: Verify configuration
   - **persistence**: Ensure existingClaim references still work
   - **cronjob**: Verify schedule and configuration

4. **Critical**: Nextcloud will auto-migrate database on first startup
   - Monitor logs during upgrade
   - May take time depending on data size
   - Ensure database is accessible and has enough space

#### Step 5: Post-Upgrade Verification
- [ ] Nextcloud UI accessible
- [ ] Database migration completed (check logs)
- [ ] User files accessible
- [ ] Apps/plugins working
- [ ] External storage mounts working
- [ ] Cron jobs running

### Risk Level: **High**
- 2 major versions = significant changes
- Database migration required
- User data at risk if migration fails
- **Recommendation**:
  - Full backup before upgrade
  - Test database migration in staging
  - Monitor upgrade process closely
  - Have rollback plan ready

---

## 6. Open WebUI: 5.13.0 → 10.1.0

### Current State
- **Chart Version**: 5.13.0
- **Location**: `kubernetes/apps/ai/open-webui/app/helmrelease.yaml`
- **Image**: `ghcr.io/open-webui/open-webui:v0.6.43`
- **Storage**: PVC `open-webui-20g`
- **Configuration**:
  - Pipelines enabled with PVC `open-webui-pipelines-new`
  - Ollama URL: `http://ollama-ipex.ai.svc.cluster.local:11434`
  - Ingress with external class
  - LoadBalancer service
  - WebSocket support configured

### Migration Path

⚠️ **CRITICAL**: This is a **5 major version jump** (5 → 6 → 7 → 8 → 9 → 10)

#### Step 1: Assessment
This is an **extremely large jump**. Consider:
- **Option A**: Direct upgrade (risky, may fail)
- **Option B**: Fresh deployment (safer, may lose some config)
- **Option C**: Staged migration (if intermediate versions available)

#### Step 2: Backup
- Export user data/conversations (if possible via API)
- Backup configuration
- Document current settings

#### Step 3: Review Breaking Changes
With 5 major versions, expect:
- Complete value structure changes
- API changes
- Database/storage format changes
- Authentication changes
- Feature deprecations

#### Step 4: Update Process

**Recommended Approach: Fresh Deployment**

1. **Document current configuration**:
   ```bash
   helm get values open-webui -n ai > open-webui-current-values.yaml
   ```

2. **Review new chart values**:
   ```bash
   helm show values open-webui/open-webui --version 10.1.0 > open-webui-new-values.yaml
   ```

3. **Map old values to new structure**:
   - **pipelines**: Check if configuration structure changed
   - **ollamaUrls**: Verify format still supported
   - **ingress**: Check class vs className
   - **persistence**: Verify existingClaim still works
   - **extraEnvVars**: Check if any env vars deprecated
   - **service**: Verify LoadBalancer configuration

4. **Update HelmRelease**:
   ```yaml
   spec:
     chart:
       spec:
         version: 10.1.0
   ```

5. **Update values** to match new structure:
   - Map all current values to new structure
   - Test in staging if possible
   - Consider exporting user data/conversations before upgrade

#### Step 5: Alternative - Fresh Install
If migration is too complex:
1. Deploy new version in parallel namespace
2. Migrate data manually
3. Switch traffic
4. Remove old deployment

### Risk Level: **Very High**
- 5 major versions = massive changes
- High likelihood of breaking changes
- **Recommendation**:
  - Consider fresh deployment approach
  - Export/import data manually
  - Test thoroughly before production
  - May be easier to redeploy than migrate

---

## Migration Priority & Timeline

### Recommended Order

1. **Low Risk First**:
   - Plex (low-medium risk, media server)
   - Kubernetes Dashboard (medium risk, read-only)

2. **Medium Risk**:
   - ECK Operator (high risk, but critical - do with caution)

3. **High Risk** (plan carefully):
   - Grafana (3 versions, complex config)
   - Nextcloud (2 versions, database migration)

4. **Very High Risk** (consider alternatives):
   - Open WebUI (5 versions - consider fresh deployment)

### Timeline Suggestion

- **Week 1**: Plex + Kubernetes Dashboard
- **Week 2**: ECK Operator (with full backups)
- **Week 3**: Grafana (staged: 8 → 9 → 10)
- **Week 4**: Nextcloud (with database backup)
- **Week 5**: Open WebUI (or fresh deployment)

---

## General Migration Best Practices

1. **Always Backup First**:
   - PVC data
   - Databases
   - Configuration files
   - Helm values

2. **Test in Staging**:
   - If possible, test upgrades in non-production first

3. **Monitor Closely**:
   - Watch pod logs during upgrade
   - Check for error events
   - Verify functionality after upgrade

4. **Have Rollback Plan**:
   - Keep old HelmRelease version
   - Know how to restore from backup
   - Document rollback procedure

5. **Staged Approach for Large Jumps**:
   - Don't jump 3+ major versions at once
   - Upgrade incrementally if possible

6. **Document Changes**:
   - Note any manual interventions
   - Document configuration changes
   - Update runbooks

---

## Next Steps

1. Review this guide for each component
2. Check official migration guides for each project
3. Create backup procedures
4. Plan testing approach
5. Schedule migration windows
6. Execute one at a time, monitoring closely
