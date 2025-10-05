# WARP.md

This file provides guidance to WARP agents when working with code in this repository.

## Project Overview

This is a production home operations repository managing a Kubernetes homelab cluster. The infrastructure runs on 3x Intel NUC14 Pro systems with **Talos Linux v1.9.4**, **Kubernetes v1.32.2**, and **Flux v2.4.0** for GitOps automation. Originally based on onedr0p's cluster-template, it has been personalized and evolved into a comprehensive homelab platform.

**Infrastructure Highlights:**
- **Hardware**: 3x Intel NUC14 Pro nodes (18 cores, ~64GB RAM, NVMe SSD, 2.5GbE each)
- **Network**: UniFi infrastructure with 10GbE backbone and AdGuard Home DNS filtering
- **Storage**: Longhorn distributed storage + UNAS-CBERG NAS for bulk data
- **Applications**: 50+ containerized applications across multiple categories

## Architecture

### Infrastructure Stack
- **Operating System**: Talos Linux v1.9.4 - Immutable, API-managed Kubernetes OS
- **Container Runtime**: Containerd 2.0.2 with Spegel for distributed image caching
- **GitOps**: Flux v2.4.0 continuously reconciles this Git repository to cluster state
- **Secrets**: SOPS with age encryption for secure secret storage in Git

### Core Platform Services
- **Networking**: Cilium eBPF-based CNI with load balancing and network security
- **DNS & Security**: AdGuard Home at 192.168.55.5 provides network-wide ad blocking
  - DNS-over-TLS (853), DNS-over-HTTPS, split-DNS for internal domains
- **Storage**: Longhorn distributed storage for critical data, UNAS-CBERG NAS for bulk storage
- **TLS**: cert-manager with Let's Encrypt for automated certificate management
- **Ingress**: Internal/external ingress classes with Cloudflare Tunnel for external access

### Application Categories
Applications are organized into functional namespaces:

**🏠 Home Automation**
- Home Assistant, ESPHome, Node-RED, Frigate NVR, Scrypted NVR
- Zigbee2MQTT, Mosquitto MQTT broker, Music Assistant

**🎬 Media & Entertainment**
- Plex, Jellyfin (media servers), TubeArchivist, MakeMKV

**🤖 AI & Machine Learning**
- Ollama (local LLM inference), Open WebUI, Langfuse (LLM analytics)

**📊 Monitoring & Observability**
- Grafana, Prometheus Stack, Uptime Kuma, Kubernetes Dashboard

**🌐 Network Services**
- AdGuard Home, Ingress NGINX, Cloudflared, External DNS, k8s-gateway

**🗄️ Data & Storage**
- MariaDB, InfluxDB, phpMyAdmin, Longhorn, Kopia backups

**📄 Office & Productivity**
- Nextcloud, Paperless-ngx

**🛠️ Custom Applications**
- Absenty (development/production deployments)

## Development Environment Setup

Use **mise** for development environment management:

```bash
# Install mise following instructions at https://mise.jdx.dev/
# Then trust this repository and install tools
mise trust
mise install
```

This installs all required tools including:
- **Kubernetes tools**: kubectl, helm, flux, kustomize
- **Talos tools**: talosctl, talhelper
- **Security tools**: sops, age
- **Utilities**: task, jq, yq

## Common Commands

### Cluster Access and Monitoring
```bash
# Set up cluster access
export KUBECONFIG=$PWD/kubeconfig

# Monitor Flux GitOps status
flux get kustomizations -A
flux get helmreleases -A

# Check cluster health
kubectl get nodes
kubectl get pods -A

# Debug specific application
kubectl logs -n <namespace> <pod-name>
```

### GitOps and Flux Management
```bash
# Force Flux to reconcile with repository
flux -n flux-system reconcile ks flux-system --with-source

# Check Git repository sync status
flux get sources git -A

# Monitor application deployments
watch kubectl get helmreleases -A

# Debug failed deployments
flux logs -n flux-system
```

### Talos Operations
```bash
# Generate new Talos configuration
task talos:generate-config

# Apply config to specific node
task talos:apply-node IP=10.10.10.10 MODE=auto

# Upgrade Talos on node
task talos:upgrade-node IP=10.10.10.10

# Upgrade Kubernetes version
task talos:upgrade-k8s

# Reset cluster (destructive)
task talos:reset
```

### Development and Debugging
```bash
# Validate configurations
task template:validate-kubernetes-config
task template:validate-talos-config

# Debug cluster resources
task template:debug
# Gets: nodes, gitrepositories, kustomizations, helmreleases, certificates, ingresses, pods

# Clean up template files after setup
task template:tidy
```

### Flux Debugging
```bash
# Check Git repository sync status
flux get sources git -A

# Check kustomizations
flux get ks -A

# Check Helm releases
flux get hr -A

# Manual reconciliation
flux -n flux-system reconcile ks flux-system --with-source
```
### Application Management

**Adding New Applications:**
1. Create application directory under `kubernetes/apps/<category>/`
2. Add `ks.yaml` (Kustomization) and `app/` subdirectory with `helmrelease.yaml`
3. Include in parent category's `kustomization.yaml`
4. Follow existing patterns in similar applications

**Configuration Patterns:**
- **HelmReleases**: Primary method for deploying applications via Flux
- **Secrets**: SOPS-encrypted `secret.sops.yaml` files in app directories
- **Persistent Storage**: Use Longhorn for critical data, NAS mounts for media
- **Homepage Integration**: Add `gethomepage.dev/*` annotations for dashboard

**Network Access Options:**
- **Internal Ingress**: `internal` class for LAN-only access with AdGuard DNS
- **External Ingress**: `external` class for internet access via Cloudflare Tunnel
- **LoadBalancer**: Services get cluster IPs from Cilium's pool (e.g., AdGuard at 192.168.55.5)

## Repository Structure

```sh
📁 kubernetes/
├── 📁 apps/                     # Applications organized by category
│   ├── 📁 home-automation/      # Home Assistant, Frigate, Node-RED, etc.
│   ├── 📁 media/                # Plex, Jellyfin, TubeArchivist
│   ├── 📁 ai/                   # Ollama, Open WebUI, Langfuse
│   ├── 📁 monitoring/           # Grafana, Prometheus, Uptime Kuma
│   ├── 📁 network/              # AdGuard, Ingress, DNS services
│   ├── 📁 databases/            # MariaDB, InfluxDB, phpMyAdmin
│   ├── 📁 office/               # Nextcloud, Paperless-ngx
│   ├── 📁 storage/              # Longhorn, backup solutions
│   ├── 📁 custom-code-production/ # Custom applications
│   └── 📁 default/              # Default namespace apps
├── 📁 bootstrap/                # Talos cluster configuration
│   └── 📁 talos/                # Talos config and patches
├── 📁 components/               # Reusable Kustomize components
└── 📁 flux/                     # Flux system configuration
📁 tools/                        # Utility scripts
├── snmp-temp-scan.sh           # UniFi temperature monitoring
└── find-stale-dns-entry-in-cf.sh # DNS cleanup utility
📁 docs/                         # Documentation and diagrams
```

## Security & Network Configuration

**DNS & Ad Blocking:**
- AdGuard Home (192.168.55.5) provides network-wide ad blocking and DNS resolution
- DNS-over-TLS (port 853) and DNS-over-HTTPS support for encrypted queries
- Split-DNS: Internal domains route to internal resolver, external to Cloudflare/Quad9

**Network Architecture:**
- UniFi Dream Machine Pro (DMP-CBERG) - Gateway with IDS/IPS
- 10GbE core switch (SW-48-PoE) with SFP+ uplinks
- 2.5GbE distribution to compute nodes via SW-24-PoE
- Strategic AP placement for full wireless coverage

**Secret Management:**
- SOPS with age encryption for all secrets stored in Git
- Critical files: `age.key`, `.sops.yaml` (keep secure, not in repo)
- All secrets in `*.sops.yaml` files throughout the repository

## Key Infrastructure Details

**Hardware Platform:**
- 3x Intel NUC14 Pro (18 cores, ~64GB RAM, NVMe SSD per node)
- All nodes serve as both control plane and worker (hyper-converged)
- 2.5GbE networking via UniFi infrastructure

**Software Stack:**
- **OS**: Talos Linux v1.9.4 (immutable, API-managed)
- **Kubernetes**: v1.32.2 with containerd 2.0.2
- **GitOps**: Flux v2.4.0 for continuous deployment
- **Storage**: Longhorn for distributed storage, UNAS-CBERG NAS for bulk data

**Development Environment:**
- **Platform**: macOS with zsh shell
- **Tooling**: mise for development environment management
- **Access**: kubectl, talosctl, flux CLI tools

## Important Files & Utilities

**Critical Configuration:**
- `kubeconfig`: Kubernetes cluster access credentials
- `age.key`: SOPS encryption key (keep secure, never commit)
- `.sops.yaml`: SOPS encryption rules for secret management
- `Taskfile.yaml`: Task automation definitions

**Utilities:**
- `tools/snmp-temp-scan.sh`: Discovers UniFi device temperature sensors for Uptime Kuma
- `tools/find-stale-dns-entry-in-cf.sh`: Cloudflare DNS cleanup utility
- `mise.toml`: Development environment tool configuration

**Documentation:**
- `README.md`: Main project documentation with architecture and applications
- `AGENTS.md`: Repository guidelines and development practices
- This file (`WARP.md`): Warp agent guidance for working with the codebase
