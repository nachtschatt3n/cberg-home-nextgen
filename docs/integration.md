# Service Integration Reference

> Maintained manually. Update after endpoint changes, new integrations, or config restructuring.
> See `docs/sops/` for step-by-step procedures for each integration.

---

## Ollama AI Endpoints

Ollama runs on Mac Mini M4 Pro (`192.168.30.111`) with three dedicated instances using
Metal Performance Shaders (MPS) for GPU acceleration.

### Instances

| Instance | Port | Model | Purpose |
|---------|------|-------|---------|
| Voice | 11434 | `qwen3:4b-instruct` | Voice/audio processing |
| Reason | 11435 | `gpt-oss:20b` | General reasoning and text processing |
| Vision | 11436 | `qwen3-vl:8b-instruct` | Vision/image processing |

### API Formats

**Native Ollama API (preferred):**
```
Base URL: http://192.168.30.111:{PORT}/api
Endpoints: /api/chat, /api/generate
API Key: Not required
Model format: gpt-oss:20b (colon, not slash)
```

**OpenAI-compatible (for apps that require it):**
```
Base URL: http://192.168.30.111:{PORT}/v1
Endpoints: /v1/chat/completions
```

### Model Naming Convention

- ✅ Correct: `gpt-oss:20b`, `qwen3:4b-instruct`, `qwen3-vl:8b-instruct`
- ❌ Wrong: `openai/gpt-oss-20b`, `qwen/qwen3-4b-2507`

### Application Configuration

| App | Instance | Endpoint | Model | Provider Config |
|-----|---------|---------|-------|-----------------|
| paperless-ai | Reason | `http://192.168.30.111:11435/api` | `qwen3:4b-instruct` | `AI_PROVIDER: "custom"`, `CUSTOM_BASE_URL` |
| paperless-gpt | Reason | `http://192.168.30.111:11435/api` | `gpt-oss:20b` | `LLM_PROVIDER: "openai"`, `OPENAI_BASE_URL` |
| frigate-nvr | Vision | `http://192.168.30.111:11436/api` | `qwen3-vl:8b-instruct` | `OPENAI_BASE_URL` |
| openclaw | Reason | `http://192.168.30.111:11435/api` | `gpt-oss:20b` | App-specific |
| open-webui | In-cluster | `http://ollama-ipex.ai.svc.cluster.local:11434` | Various | In-cluster IPEX instance |

### Testing Endpoints

```bash
# Test Reason endpoint
curl -X POST http://192.168.30.111:11435/api/chat \
  -H "Content-Type: application/json" \
  -d '{"model": "gpt-oss:20b", "messages": [{"role": "user", "content": "Hello"}], "stream": false}'

# Test Vision endpoint
curl -X POST http://192.168.30.111:11436/api/chat \
  -H "Content-Type: application/json" \
  -d '{"model": "qwen3-vl:8b-instruct", "messages": [{"role": "user", "content": "Hello"}], "stream": false}'

# List available models (Voice instance)
curl http://192.168.30.111:11434/api/tags
```

---

## Homepage Dashboard

Homepage provides an auto-discovering dashboard via Kubernetes integration (RBAC-enabled).

**Deployment:** `kubernetes/apps/default/homepage/`

### Service Discovery

Homepage auto-discovers services via ingress annotations. Both annotations AND labels are required.

**Required annotations:**
```yaml
annotations:
  gethomepage.dev/enabled: "true"
  gethomepage.dev/name: "My App Name"
  gethomepage.dev/group: "Group Name"
  gethomepage.dev/icon: "app-icon.png"
  gethomepage.dev/description: "Brief description"
labels:
  gethomepage.dev/enabled: "true"   # REQUIRED for discovery
```

### Homepage Groups

| Group | Used For |
|-------|---------|
| AI | AI/ML applications and services |
| Databases | Database management UIs |
| System | System administration tools |
| Network Services | Network infrastructure UIs |
| Home Automation | Smart home and IoT services |
| Monitoring | Observability and monitoring tools |
| Infrastructure | Core infrastructure services |
| Office | Productivity and office applications |
| Media | Media servers and streaming services |
| Download | Download managers and archivers |
| Software Development | Custom development applications |
| Storage | Storage management UIs |

### Icon Selection

- **Dashboard Icons**: https://github.com/walkxcode/dashboard-icons
- **Material Design Icons**: `mdi-icon-name`
- **Simple Icons**: `si-brand-name`

### Troubleshooting

```bash
# Check Homepage logs
kubectl logs -n default -l app.kubernetes.io/name=homepage

# Verify ingress has both annotations AND labels
kubectl get ingress {name} -n {ns} -o yaml | grep -A5 "annotations:"
kubectl get ingress {name} -n {ns} -o yaml | grep -A5 "labels:"
```

*See `docs/sops/homepage-integration.md` for step-by-step procedures.*

---

## Flux GitOps

**Deployment:** `kubernetes/flux/` and `kubernetes/apps/flux-system/`

### Reconciliation Flow

```
Push to main → GitHub webhook → Flux source-controller detects change
  → kustomize-controller reconciles Kustomizations
  → helm-controller reconciles HelmReleases
  → Cluster state updated
```

### Key Concepts

| Concept | Description |
|---------|-------------|
| HelmRelease | Declares a Helm chart deployment with values |
| HelmRepository | Defines a Helm chart source (OCI or HTTP) |
| Kustomization | Applies a directory of manifests with patches |
| Receiver | Webhook endpoint that triggers reconciliation |

### Key Commands

```bash
# Status overview
flux get kustomizations -A
flux get helmreleases -A
flux get sources helm -A

# Force reconciliation
flux reconcile kustomization {name} -n flux-system --with-source
flux reconcile helmrelease {name} -n {namespace}

# Check logs
kubectl logs -n flux-system deployment/helm-controller --tail=50
kubectl logs -n flux-system deployment/source-controller --tail=50
kubectl logs -n flux-system deployment/kustomize-controller --tail=50

# Suspend/resume
flux suspend helmrelease {name} -n {ns}
flux resume helmrelease {name} -n {ns}
```

### Webhook

Flux Webhook Receiver listens for GitHub push events to trigger immediate reconciliation
instead of waiting for the 30m polling interval.

---

## Renovate Dependency Updates

Renovate automatically creates PRs for dependency updates.

**Configuration:** `.github/renovate.json5`

| Setting | Value |
|---------|-------|
| Schedule | Every weekend |
| Auto-merge | GitHub Actions minor/patch only |
| Semantic commits | Enabled |
| Managers | Flux, Helm, Kubernetes, Kustomize, Helmfile |

### PR Conventions

| Type | Commit Prefix | Auto-merge |
|------|--------------|-----------|
| Major | `feat!:` | No — review required |
| Minor | `feat:` | Yes (GitHub Actions) |
| Patch | `fix:` | Yes (GitHub Actions) |
| Digest | `chore:` | Yes |

### Renovate Dashboard

Open PRs are tracked in `runbooks/version-check-current.md` (generated by `check-all-versions.py`).

```bash
# Check open Renovate PRs
gh pr list --label "renovate"

# View version check report
python3 runbooks/check-all-versions.py
```

---

## UniFi Network Management

**Tool:** `unifictl` — CLI for UniFi Network Controller

**Controller URL:** `https://192.168.30.1:8443`

### Configuration

```bash
# One-time setup
unifictl local configure \
  --url https://192.168.30.1:8443 \
  --username admin \
  --password '<PASSWORD>' \
  --site default \
  --scope local \
  --verify-tls false
```

### Key Commands

```bash
unifictl local health               # Network health summary
unifictl local devices              # All devices (switches, APs, gateway)
unifictl local clients              # Connected clients
unifictl local networks -o json     # VLAN/network config
unifictl local wlans                # WiFi networks
unifictl local events               # Recent events
unifictl local top-clients --limit 10  # Top bandwidth consumers
```

*See `docs/network.md` for full UniFi command reference.*

---

## External DNS

external-dns automatically manages DNS records in Cloudflare.

**Deployment:** `kubernetes/apps/network/external/external-dns/`

### Behavior

- Watches ingress resources with `ingressClassName: external`
- Creates CNAME records in Cloudflare: `service.domain → external.domain`
- Uses Cloudflare API token (stored in `secret.sops.yaml`)
- TXT ownership records prefixed with `k8s.`

### Adding External DNS for an App

Add annotation to ingress:
```yaml
annotations:
  external-dns.alpha.kubernetes.io/target: "external.${SECRET_DOMAIN}"
```

The ingress must also use `ingressClassName: external`.

---

## Longhorn Storage

**Deployment:** `kubernetes/apps/storage/longhorn/`

See `docs/sops/longhorn.md` for detailed operational procedures.

### Storage Class Selection

| Class | Use For |
|-------|---------|
| `longhorn` | App databases, StatefulSets, auto-provisioned volumes |
| `longhorn-static` | Config directories, manually managed volumes |

### Key Facts

- Default replicas: 2
- Backup target: UNAS-CBERG NAS
- Backup schedule: Daily CronJob at 3:00 AM
- Dynamic PV names: auto-generated UUIDs (expected for `longhorn` class)
- Static PV names: human-readable (required for `longhorn-static` class)

```bash
# Check volumes
kubectl get volumes -n storage
kubectl get pv,pvc -A | grep {app}

# UI access
kubectl port-forward -n storage svc/longhorn-frontend 8080:80
# Then open http://localhost:8080
```

---

## AdGuard Home DNS

**Deployment:** `kubernetes/apps/network/internal/adguard-home/`

| Setting | Value |
|---------|-------|
| Service IP | 192.168.55.5 (LoadBalancer) |
| DNS port | 53 |
| DNS-over-TLS | 853 |
| Upstream | Cloudflare 1.1.1.1 (DoH), Quad9 9.9.9.9 (DoH) |
| Internal domains | `*.domain` → k8s-gateway 192.168.55.101 |

All LAN clients use 192.168.55.5 as primary DNS (pushed via UniFi DHCP).

---

## CSI Driver SMB (NAS Integration)

**Deployment:** `kubernetes/apps/kube-system/csi-driver-smb/`

Provides SMB/CIFS volume mounts from UNAS-CBERG NAS (192.168.31.230) to Kubernetes pods.

Used by:
- Applications needing large file storage (Jellyfin media library, etc.)
- Backup targets

```bash
# Check SMB CSI driver pods
kubectl get pods -n kube-system -l app=csi-smb-node
kubectl get pods -n kube-system -l app=csi-smb-controller
```
