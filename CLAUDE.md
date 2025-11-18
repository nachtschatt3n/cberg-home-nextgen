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

### Important: do not use UUID PV Names Are Normal
- you should not use  `longhorn` storage class, PV names will be UUIDs like `pvc-4b56f40c-...`

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

## Authentik Authentication Integration

### Overview
Authentik is the default authentication provider for applications in this cluster. All new applications requiring web authentication should use Authentik blueprints for configuration, not the UI.

### Blueprint-Based Configuration (Default)
Authentik resources are managed through YAML blueprints stored in ConfigMaps, not through the UI. This ensures:
- Version-controlled configuration
- GitOps-compatible deployment
- Reproducible authentication setup
- No manual UI configuration required

### Blueprint Storage
**Important**: All blueprints are stored in a **SOPS-encrypted ConfigMap** (`configmap.sops.yaml`), which is the **source of truth** that Authentik loads.

- **Source of Truth**: `kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml` (SOPS-encrypted, contains all blueprints)
- **Deployment**: Flux decrypts and applies the ConfigMap, init containers copy blueprints to `/blueprints` for Authentik to load
- **Mount path in pods**: `/blueprints` (automatically loaded by Authentik)

**Benefits:**
- **Security**: Actual domains (not placeholders) can be stored safely in public repository via SOPS encryption
- **Simplicity**: Single source of truth, no duplicate files to maintain
- **GitOps friendly**: All changes tracked in Git, no UI drift

**Workflow:**
1. Decrypt ConfigMap: `sops -d kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml > /tmp/configmap.yaml`
2. Add/update blueprint entry in `/tmp/configmap.yaml`
3. Re-encrypt: `sops -e /tmp/configmap.yaml > kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml`
4. Update `helmrelease.yaml` init containers to copy the new blueprint (if adding a new app)
5. Commit and push - Flux reconciles, Authentik loads blueprints automatically

### Blueprint Structure
Each blueprint file contains:
- `version: 1` - Blueprint API version
- `entries:` - List of Authentik resources to create/update
  - Each entry has `id`, `model`, `state`, `identifiers`, and `attrs`

### Key Concepts

#### Flow References
- **MUST use UUIDs**, not slugs for flow references
- Default flows UUIDs (pre-installed):
  - Authorization: `0cdf1b8c-88f9-4b90-a063-a14e18192f74` (default-provider-authorization-implicit-consent)
  - Invalidation: `b8a97e00-f02f-48d9-b854-b26bf837779c` (default-provider-invalidation-flow)
- These UUIDs are stable and don't change between deployments

#### Provider References
- Use `!KeyOf {entry-id}` to reference other blueprint entries
- Example: `provider: !KeyOf frigate-forward-auth-provider`
- This resolves to the UUID of the referenced entry at runtime

#### Service Connections
- Kubernetes outposts **require** a service connection UUID
- Default service connection: `162f6c4f-053d-4a1a-9aa6-d8e590c49d70` (Local Kubernetes Cluster)
- Without this, outposts won't create Kubernetes resources

#### Domain Configuration
- **Flux substitution (`${SECRET_DOMAIN}`) does NOT work** inside ConfigMap `data` fields
- **Blueprints are SOPS-encrypted** to securely store the actual domain in a public repository
- The encrypted ConfigMap (`configmap.sops.yaml`) contains all blueprints with the real domain
- Flux automatically decrypts the ConfigMap on deployment
- To update blueprints: decrypt, edit, re-encrypt (see kustomization.yaml for instructions)

### Typical Application Integration Pattern

For a new application requiring Authentik authentication:

1. **Create Blueprint File** - Create `authentik-blueprint.yaml` in your app's `app/` directory
   ```yaml
   - id: {app}-forward-auth-provider
     model: authentik_providers_proxy.proxyprovider
     state: present
     identifiers:
       name: {app}-forward-auth
     attrs:
       name: {app}-forward-auth
       mode: forward_single
       external_host: "https://{app}.{domain}"
       internal_host: "http://{app}.{namespace}.svc.cluster.local:{port}"
       authorization_flow: "0cdf1b8c-88f9-4b90-a063-a14e18192f74"
       invalidation_flow: "b8a97e00-f02f-48d9-b854-b26bf837779c"
   ```

2. **Create Application** - Registers the app in Authentik
   ```yaml
   - id: {app}-application
     model: authentik_core.application
     state: present
     identifiers:
       slug: {app}
     attrs:
       name: {App Name}
       slug: {app}
       provider: !KeyOf {app}-forward-auth-provider
       meta_launch_url: "https://{app}.{domain}"
   ```

3. **Create Outpost** - Deploys the authentication proxy
   ```yaml
   - id: {app}-outpost
     model: authentik_outposts.outpost
     state: present
     identifiers:
       name: {app}-forward-auth
     attrs:
       name: {app}-forward-auth
       type: proxy
       providers:
         - !KeyOf {app}-forward-auth-provider
       service_connection: "162f6c4f-053d-4a1a-9aa6-d8e590c49d70"
       config:
         authentik_host: "https://auth.{domain}"
         kubernetes_namespace: kube-system
         kubernetes_replicas: 1
         kubernetes_service_type: "ClusterIP"
   ```

4. **Update Encrypted ConfigMap** - Add your blueprint to the SOPS-encrypted ConfigMap:
   ```bash
   # Decrypt the ConfigMap
   sops -d kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml > /tmp/configmap.yaml

   # Edit the ConfigMap and add your blueprint as a new data entry
   # data:
   #   {app-name}-blueprint.yaml: |
   #     <your blueprint content here>

   # Re-encrypt and save
   sops -e /tmp/configmap.yaml > kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml
   ```

5. **Commit and Push** - The encrypted ConfigMap is safe to commit to the public repository

6. **Configure Ingress** - Add Authentik forward auth annotations (for forward auth mode)
   ```yaml
   annotations:
     nginx.ingress.kubernetes.io/auth-url: "http://ak-outpost-{app}-forward-auth.kube-system.svc.cluster.local:9000/outpost.goauthentik.io/auth/nginx"
     nginx.ingress.kubernetes.io/auth-signin: "https://{app}.{domain}/outpost.goauthentik.io/start?rd=$escaped_request_uri"
     nginx.ingress.kubernetes.io/auth-response-headers: "Set-Cookie,X-authentik-username,X-authentik-groups,X-authentik-email,X-authentik-name,X-authentik-uid"
     nginx.ingress.kubernetes.io/auth-snippet: |
       proxy_set_header X-Forwarded-Host $http_host;
       proxy_set_header X-Proxy-Secret {auth-secret};
   ```

7. **Create Outpost Ingress** - Exposes outpost endpoints (for forward auth mode)
   ```yaml
   # Service (ExternalName to outpost service)
   apiVersion: v1
   kind: Service
   metadata:
     name: {app}-authentik-outpost
     namespace: {app-namespace}
   spec:
     type: ExternalName
     externalName: ak-outpost-{app}-forward-auth.kube-system.svc.cluster.local
     ports:
       - port: 9000
         targetPort: 9000
   
   # Ingress for outpost paths
   apiVersion: networking.k8s.io/v1
   kind: Ingress
   metadata:
     name: {app}-authentik-outpost
     namespace: {app-namespace}
   spec:
     ingressClassName: {ingress-class}
     rules:
       - host: "{app}.{domain}"
         http:
           paths:
             - path: /outpost.goauthentik.io
               pathType: Prefix
               backend:
                 service:
                   name: {app}-authentik-outpost
                   port:
                     number: 9000
   ```

### Blueprint Loading Process

1. Blueprint files in `kubernetes/apps/kube-system/authentik/app/` are combined by Kustomize into a single ConfigMap
2. ConfigMap `authentik-blueprints` is created/updated in `kube-system` namespace
3. Authentik server/worker pods automatically load blueprints from `/blueprints` on startup
4. Blueprint entries are applied by Authentik's blueprint loader
5. Kubernetes resources (outposts) are created by the outpost controller

### Removing an Application

When removing an app with Authentik integration:
1. Remove the blueprint file from the app directory: `{app}/app/authentik-blueprint.yaml`
2. Remove the copy from the authentik directory: `kube-system/authentik/app/{app-name}-blueprint.yaml`
3. Remove the reference from `kube-system/authentik/app/kustomization.yaml` `configMapGenerator.files` list
4. Commit and push - The blueprint will be automatically removed from the ConfigMap and Authentik will remove the resources

### Monitoring Blueprint Application

```bash
# Check blueprint application status (in Authentik pod)
kubectl exec -n kube-system deployment/authentik-server -- python3 manage.py show_blueprints

# Check outpost deployment
kubectl get deployment -n kube-system | grep outpost

# Check outpost service
kubectl get svc -n kube-system | grep outpost

# Check outpost controller logs
kubectl logs -n kube-system -l app.kubernetes.io/name=authentik --tail=100 | grep -i blueprint
```

### Common Issues and Solutions

1. **Blueprint not loading**: Check ConfigMap mount in Authentik pods, verify blueprint YAML syntax, ensure SOPS-encrypted ConfigMap is properly decrypted by Flux
2. **Outpost not created**: Verify `service_connection` UUID is correct, check outpost controller logs
3. **Flow reference errors**: Ensure flow UUIDs are correct, use hardcoded UUIDs for default flows
4. **Provider reference errors**: Use `!KeyOf` syntax, verify entry `id` matches exactly
5. **ConfigMap decryption failed**: Verify SOPS encryption keys are correctly configured in `.sops.yaml` and Flux has access to the age key
6. **Blueprint update not applied**: After editing the encrypted ConfigMap, ensure you re-encrypted it properly and committed the changes
