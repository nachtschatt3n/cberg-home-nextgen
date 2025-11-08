- we only use the main branch and no PRs

## Cluster Organization

### Namespace Layout
The cluster uses namespace-based organization for different service categories:

- **monitoring**: Prometheus, Grafana, Alertmanager, fluent-bit, Elasticsearch, Kibana, APM server, Metricbeat, OpenTelemetry
- **storage**: Longhorn volumes and storage management
- **ai**: AI/ML workloads (langfuse, open-webui, bytebot, ai-sre, mcpo)
- **network**: Ingress controllers (internal/external), external-dns, adguard-home, cloudflared
- **kube-system**: Core cluster services (authentik, cilium, coredns, descheduler, spegel, node-feature-discovery)
- **home-automation**: Home Assistant, ESPHome, Frigate, iobroker, mosquitto, music-assistant-server, n8n, mdns-repeater
- **databases**: MariaDB, InfluxDB, phpMyAdmin
- **media**: Jellyfin, Plex, MakeMKV
- **office**: Nextcloud, Paperless-NGX, Omni-Tools
- **download**: JDownloader, Tube-Archivist
- **custom-code-production**: Custom applications (absenty-production, absenty-development)
- **flux-system**: Flux GitOps controllers and sources
- **cert-manager**: Certificate management
- **backup**: Backup-related resources (currently empty)
- **cilium-secrets**: Cilium secret storage
- **default**: Homepage, echo-server

### Key Service Locations
- Prometheus: `monitoring/prometheus-kube-prometheus-stack-0`
- Alertmanager: `monitoring/alertmanager-kube-prometheus-stack-0`
- fluent-bit: DaemonSet in `monitoring` namespace
- Elasticsearch: `monitoring/elasticsearch-es-*` pods
- Longhorn Manager: DaemonSet in `storage` namespace
- Flux controllers: `flux-system` namespace

## Longhorn Storage Standards

### Storage Class Usage
- **longhorn** (dynamic provisioning): Use for application data, databases, and growing volumes
  - PVC names: Clean and descriptive (e.g., `postgres-data`, `redis-cache`)
  - PV names: Auto-generated UUIDs (e.g., `pvc-df1999c2-...`) - THIS IS NORMAL AND EXPECTED
  - Best for: StatefulSet volumes, application databases, data that grows over time

- **longhorn-static**: Use ONLY for configuration directories and manually managed volumes
  - PVC names: Match application (e.g., `home-assistant-config`)
  - PV names: Clean names matching PVC
  - Requires pre-existing Longhorn volume
  - Best for: Fixed-size config directories, volumes needing manual control

### Important: UUID PV Names Are Normal
- When using `longhorn` storage class, PV names will be UUIDs like `pvc-4b56f40c-...`
- This is **standard Kubernetes behavior**, not a misconfiguration
- Do NOT attempt to migrate these to clean names - it's costly, risky, and unnecessary
- PVC names are what users interact with - those should be clean
- See `/docs/migration/pv-pvc-migration-lessons-learned.md` for detailed explanation

### PV/PVC Migration Warning
- **DO NOT** attempt to migrate existing dynamically provisioned volumes to longhorn-static
- Migration requires:
  - Application downtime (30-45 min per volume)
  - Complex Longhorn volume pre-creation
  - Data migration with risk of data loss
  - Manual cleanup
- Cost-benefit analysis: Purely cosmetic, not worth the effort/risk
- Only migrate if volume is truly static config data

### Storage Naming Convention
For new deployments:
- PVC naming: `{app-name}-{purpose}` (e.g., `langfuse-postgresql-data`, `bytebot-cache`)
- Storage class selection:
  - Application data → `longhorn` (accept UUID PVs)
  - Config directories → `longhorn-static` (clean PVs)
- Never mix concerns: one PVC per purpose (data, config, cache, logs separately)

## Flux GitOps Workflow

### Making Changes
All cluster changes must go through Git:
1. Modify YAML files in `kubernetes/apps/{namespace}/{app}/`
2. Commit changes to main branch (no PRs)
3. Push to GitHub - triggers webhook to Flux
4. Monitor reconciliation: `flux get kustomizations -A`

### Force Reconciliation
When changes don't auto-apply:
```bash
# Reconcile Git source
flux reconcile source git flux-system

# Reconcile specific kustomization
flux reconcile kustomization {name} -n {namespace}

# Reconcile HelmRepository
flux reconcile source helm {name} -n flux-system

# Reconcile HelmRelease
flux reconcile helmrelease {name} -n {namespace}
```

### Manual Apply (Emergency Only)
Only use when Flux is stuck or for immediate testing:
```bash
kubectl apply -f kubernetes/apps/{namespace}/{app}/app/*.yaml
```

### Repository Structure
- `kubernetes/flux/meta/repositories/helm/` - HelmRepository definitions
- `kubernetes/apps/{namespace}/{app}/` - Application manifests
  - `ks.yaml` - Kustomization definition
  - `app/helmrelease.yaml` - Helm chart config
  - `app/kustomization.yaml` - Kustomization resources
  - `app/*.sops.yaml` - Encrypted secrets