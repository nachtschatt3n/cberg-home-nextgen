# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Project Overview

This is a home automation Kubernetes cluster template built on **Talos Linux** with **Flux** for GitOps. It's based on onedr0p's cluster-template and uses **makejinja** for templating configuration files. The cluster runs containerized home automation services including Home Assistant, Frigate NVR, media servers, monitoring, and AI applications.

## Architecture

### Template System
- **makejinja**: Template engine that reads `config.yaml` and renders Jinja2 templates (`.j2` files) from `templates/` directory
- **SOPS + Age**: Secret encryption using Age keys for secure storage of sensitive configuration
- **Configuration Flow**: `config.sample.yaml` → `config.yaml` (user-customized) → makejinja rendering → final manifests

### Cluster Components
- **Talos Linux**: Immutable Kubernetes OS with declarative configuration
- **Flux**: GitOps controller for continuous delivery from this Git repository
- **Cilium**: CNI for networking with load balancer capabilities
- **Longhorn**: Distributed block storage for persistent volumes
- **cert-manager**: Automatic SSL certificate management

### Application Architecture
The cluster runs applications across multiple namespaces:
- **home-automation**: Core home automation (Home Assistant, Frigate, Node-RED, Zigbee2MQTT, etc.)
- **media**: Media servers (Plex, Jellyfin, makeMKV)
- **ai**: AI services (Ollama, Open WebUI, MCPO)
- **monitoring**: Observability stack (Grafana, Prometheus, Uptime Kuma)
- **databases**: Data persistence (MariaDB, InfluxDB)
- **office**: Productivity apps (Nextcloud, Paperless-ngx)

## Development Environment Setup

Use **mise** for development environment management:

```bash
# Install and activate mise first (see README.md)
mise trust
mise install
mise run deps
```

This installs all required tools including:
- Python 3.13 + uv for template dependencies
- Kubernetes tools: kubectl, helm, kustomize, flux
- Talos tools: talosctl, talhelper
- Security tools: sops, age
- Utilities: task, jq, yq, gum

## Common Commands

### Initial Setup
```bash
# Generate config.yaml from sample and initialize keys
task init

# Configure cluster (render templates, encrypt secrets)
task configure
```

### Cluster Management
```bash
# Bootstrap Talos cluster
task bootstrap:talos

# Deploy applications to cluster
task bootstrap:apps

# Force Flux to reconcile with repository
task reconcile
# Full command: flux --namespace flux-system reconcile kustomization flux-system --with-source
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

## Working with Applications

### Adding New Applications
1. Create namespace directory under `kubernetes/apps/`
2. Add Kustomization files following the existing pattern
3. Include in parent namespace's `kustomization.yaml`
4. Applications use Flux's `Kustomization` and `HelmRelease` resources

### Configuration Management
- **Secrets**: Use SOPS-encrypted `.sops.yaml` files in the appropriate namespace
- **ConfigMaps**: Store configuration in regular YAML files
- **External Secrets**: Managed through the secret management workflow with Age encryption

### Network Access
- **Internal ingress**: Use `internal` ingress class for LAN-only access
- **External ingress**: Use `external` ingress class for internet-facing services (via Cloudflare Tunnel)
- **LoadBalancer**: Services get IPs from Cilium's IP pool

## Repository Structure

```
├── kubernetes/
│   ├── apps/                    # Application manifests organized by category
│   │   ├── home-automation/     # Home Assistant, Frigate, Node-RED, etc.
│   │   ├── media/               # Plex, Jellyfin
│   │   ├── ai/                  # Ollama, Open WebUI
│   │   ├── monitoring/          # Grafana, Prometheus
│   │   └── ...
│   ├── bootstrap/               # Initial cluster setup
│   │   ├── apps/                # Bootstrap applications
│   │   └── talos/               # Talos configuration
│   └── flux/                    # Flux system configuration
├── templates/                   # Jinja2 templates for configuration
├── .taskfiles/                  # Task definitions for automation
├── config.yaml                  # Main configuration (user-customized)
├── config.sample.yaml           # Template configuration file
└── Taskfile.yaml               # Main task runner configuration
```

## Security Considerations

- **Age Encryption**: All secrets must be encrypted with SOPS before committing
- **Key Management**: Age keys stored in `age.key` (not committed to repo)
- **Deploy Keys**: SSH deploy keys for private repository access
- **Network Security**: Internal/external ingress separation with Cloudflare protection

## Environment Notes

- **Platform**: macOS with zsh shell
- **Container Runtime**: Talos Linux with containerd
- **GitOps**: Flux monitors this repository for changes
- **DNS**: Split-horizon DNS setup with Cloudflare for external, k8s_gateway for internal
- **Storage**: Longhorn for persistent storage, local-path for temporary storage

## Important Files

- `config.yaml`: Main configuration file (customize from config.sample.yaml)
- `age.key`: SOPS encryption key (keep secure, not in repo)
- `kubeconfig`: Kubernetes cluster access (generated after bootstrap)
- `.sops.yaml`: SOPS encryption rules
- `Taskfile.yaml`: Task automation definitions