# Repository Guidelines

## Project Overview
This is a personalized home operations repository for managing a production Kubernetes homelab cluster. The infrastructure runs on 3x Intel NUC14 Pro systems with Talos Linux v1.9.4, Kubernetes v1.32.2, and Flux v2.4.0 for GitOps automation.

**Key Infrastructure:**
- **Hardware**: 3x Intel NUC14 Pro (18 cores, ~64GB RAM, NVMe SSD, 2.5GbE networking)
- **OS**: Talos Linux v1.9.4 (immutable, secure-by-default)
- **Network**: UniFi infrastructure with 10GbE backbone, AdGuard Home DNS at 192.168.55.5
- **Storage**: Longhorn distributed storage + UNAS-CBERG NAS at 192.168.31.230
- **Applications**: 50+ applications across home automation, media, AI/ML, monitoring, and productivity

## Project Structure & Module Organization
- `kubernetes/apps/` - Applications organized by category (home-automation, media, ai, monitoring, etc.)
- `kubernetes/bootstrap/` - Talos cluster bootstrap configuration and initial applications
- `kubernetes/components/` - Reusable Kustomize components shared across applications
- `kubernetes/flux/` - Flux system configuration for GitOps automation
- `tools/` - Utility scripts including SNMP temperature monitoring for UniFi devices
- `docs/` - Documentation and network topology diagrams

## Build, Test, and Development Commands
Install development environment using Mise:
```sh
mise trust
mise install
```

Access and monitor the cluster:
```sh
# Set up cluster access
export KUBECONFIG=$PWD/kubeconfig

# Monitor Flux GitOps status
flux get kustomizations -A
flux get helmreleases -A

# Debug applications
kubectl get pods -A
kubectl logs -n <namespace> <pod-name>

# Force Flux reconciliation
flux -n flux-system reconcile ks flux-system --with-source
```

Bootstrap cluster (if rebuilding):
```sh
task bootstrap:talos
task bootstrap:apps
```

## Coding Style & Naming Conventions
- `.editorconfig` enforces LF endings, final newlines, and 2-space indentation (Python/Shell stay at 4).
- Name manifests with scope prefixes (e.g. `cluster/`, `network/`) and keep secrets in `*.sops.*` files.
- Prefer Taskfile targets; mirror `templates/scripts` when introducing scripts.

## Testing Guidelines
- `task template:configure` must pass; it runs `makejinja`, encrypts secrets, then validates YAML with `kubeconform` and Talos config with `talhelper validate`.
- When touching rendered resources, run `task template:configure -- --strict` if you add extra options, and spot-check `kubernetes/` diffs before committing.
- For live clusters, run `task template:debug` to capture kubectl snapshots when verifying fixes.

## Commit & Pull Request Guidelines
- Use concise, imperative subjects; prefix with the touched area when helpful (`langfuse:`, `talos:`), matching existing history.
- Squash noisy rendered output and commit only meaningful diffs; never commit unencrypted secrets or new kubeconfig files.
- PRs should outline the change, list the Task targets run, reference related issues, and attach screenshots or logs for cluster-impacting updates.

## Storage & Persistence Policies
- **Distributed Storage**: Longhorn provides replicated storage across the 3-node cluster for critical data
- **Bulk Storage**: UNAS-CBERG NAS (192.168.31.230) provides CIFS/SMB shares for media and backups
- **Database Storage**: MariaDB, InfluxDB, and application state use Longhorn persistent volumes
- **Media Storage**: Plex, Jellyfin, and media applications connect to NAS via CIFS for large file storage
- **Backup Strategy**: Kopia handles automated backups, iCloud Drive Sync for selective cloud backup

## Network & Security Configuration
- **DNS**: AdGuard Home (192.168.55.5) provides network-wide ad blocking and recursive DNS
  - Supports DNS-over-TLS (port 853) and DNS-over-HTTPS via internal ingress
  - Split-DNS: internal domains (*.example.com) → 192.168.55.101, external → Cloudflare/Quad9
- **TLS Certificates**: cert-manager with Let's Encrypt for automated certificate management
- **Ingress**: Internal ingress class for LAN access, external for internet-facing services via Cloudflare Tunnel
- **Secrets Management**: SOPS with age encryption for storing secrets in Git
  - Critical files: `age.key`, `.sops.yaml`, encrypted secrets in `*.sops.yaml` files
- **UniFi Network**: DMP-CBERG gateway, SW-48-PoE core switch, SW-24-PoE distribution
