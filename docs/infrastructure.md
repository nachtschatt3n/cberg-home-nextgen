# Infrastructure Reference

> Maintained manually. Update after hardware changes, version upgrades, or cluster topology changes.
> Run `python3 runbooks/doc-check.py` to validate this file against live cluster state.

---

## Overview

Home lab Kubernetes cluster running 75+ applications across 16 namespaces, managed via GitOps with
Flux on Talos Linux. Three-node hyper-converged architecture (all nodes serve as both control plane
and worker).

| Attribute | Value |
|-----------|-------|
| Kubernetes | v1.34.0 |
| Talos Linux | v1.11.0 |
| Flux | v2.8.0 |
| Nodes | 3 × Intel NUC14 Pro |
| CNI | Cilium v1.18.6 |
| Storage | Longhorn v1.10.1 |
| GitOps | Flux (Helm Operator) |
| Secrets | SOPS + age encryption |
| Auth | Authentik |

---

## Cluster Nodes

All nodes serve as both control plane and worker nodes (hyper-converged).

| Node | Model | CPU | Memory | Storage | Network | IP |
|------|-------|-----|---------|---------|---------|-----|
| k8s-nuc14-01 | Intel NUC14 Pro | 18 cores | ~64 GB | NVMe SSD | 2.5 GbE | 192.168.55.x |
| k8s-nuc14-02 | Intel NUC14 Pro | 18 cores | ~64 GB | NVMe SSD | 2.5 GbE | 192.168.55.x |
| k8s-nuc14-03 | Intel NUC14 Pro | 18 cores | ~64 GB | NVMe SSD | 2.5 GbE | 192.168.55.x |

Node IPs are assigned from the k8s-network VLAN (192.168.55.0/24, VLAN 55) via DHCP.
All three nodes connect to Basement-SW-24-PoE.

---

## Additional Infrastructure

| Device | IP | Role |
|--------|----|------|
| UNAS-CBERG (NAS) | 192.168.31.230 | Bulk storage, SMB/NFS shares, backups |
| Mac Mini M4 Pro | 192.168.30.111 | Ollama AI inference (Voice/Reason/Vision) |
| DMP-CBERG | 192.168.30.1 | Router/gateway, WireGuard VPN, IDS/IPS |
| PiKVM (per node) | — | KVM-over-IP for out-of-band node management |

**Mac Mini M4 Pro:**
- Three Ollama instances with Metal Performance Shaders (MPS) acceleration
- Voice: port 11434 (`qwen3:4b-instruct`)
- Reason: port 11435 (`gpt-oss:20b`)
- Vision: port 11436 (`qwen3-vl:8b-instruct`)
- Native Ollama API at `http://192.168.30.111:{PORT}/api`

**NAS (UNAS-CBERG):**
- 10 GbE SFP+ connection on Servers VLAN (192.168.31.0/24)
- Provides SMB/NFS shares for Kubernetes workloads via CSI Driver SMB
- Hosts Longhorn backup target

---

## Bootstrap Components

Bootstrap order (via `kubernetes/bootstrap/apps/helmfile.yaml`):

| Order | Component | Chart | Version | Namespace |
|-------|-----------|-------|---------|-----------|
| 1 | Cilium | `cilium/cilium` | 1.17.1 | kube-system |
| 2 | CoreDNS | `oci://ghcr.io/coredns/charts/coredns` | 1.45.2 | kube-system |
| 3 | cert-manager | `jetstack/cert-manager` | v1.19.3 | cert-manager |
| 4 | Flux Operator | `oci://ghcr.io/controlplaneio-fluxcd/charts/flux-operator` | 0.14.0 | flux-system |
| 5 | Flux Instance | `oci://ghcr.io/controlplaneio-fluxcd/charts/flux-instance` | 0.14.0 | flux-system |

These are bootstrapped via Helmfile (not Flux) on initial cluster setup. After bootstrap, Flux
manages all subsequent deployments including upgrades to these components.

---

## Kubernetes Cluster

| Component | Details |
|-----------|---------|
| OS | Talos Linux v1.11.0 (immutable, minimal, Kubernetes-focused) |
| Container Runtime | Containerd 2.1.4 + Spegel (distributed image caching) |
| CNI | Cilium v1.18.6 (eBPF networking, load balancing, network policies) |
| DNS | CoreDNS (cluster-internal) + k8s-gateway (split-DNS for `*.domain`) |
| Ingress | ingress-nginx (internal) + ingress-nginx (external) |
| Storage | Longhorn v1.10.1 (distributed, replicated, with backup) |
| Certificate Management | cert-manager v1.19.3 + Let's Encrypt |
| Secrets | SOPS + age encryption |
| Identity Provider | Authentik (forward auth for all ingress) |
| Image Updates | Renovate (weekly) + Flux Image Automation |

---

## Storage

**Longhorn** provides distributed block storage with replication:

| Setting | Value |
|---------|-------|
| Storage class (dynamic) | `longhorn` |
| Storage class (static) | `longhorn-static` |
| Default replicas | 2 |
| Backup target | UNAS-CBERG NAS |
| Backup schedule | Daily CronJob at 3:00 AM (`storage/backup-of-all-volumes`) |
| Data engine | v1 |

**Usage guidelines:**
- Use `longhorn` (dynamic) for app databases, StatefulSets, and auto-provisioned volumes
- Use `longhorn-static` for config directories with fixed size and manual lifecycle management
- Dynamic PV names are auto-generated UUIDs (expected — do not confuse with static PVs)

---

## GitOps Workflow

```
Push to main → GitHub Actions (validate) → Flux detects changes
  → Reconcile HelmReleases + Kustomizations → Deploy/Update Applications
```

- **Flux** reconciles every 30m or on webhook push from GitHub
- **Renovate** scans for dependency updates every weekend, opens PRs automatically
- **All changes** go through Git — no direct kubectl apply to cluster
- **Secrets** are SOPS-encrypted before commit; Flux decrypts at apply time

---

## Namespaces

| Namespace | Purpose | App Count |
|-----------|---------|-----------|
| ai | AI/ML services | ~5 |
| home-automation | Smart home integrations | ~13 |
| databases | Database backends | ~8 |
| monitoring | Observability stack | ~10 |
| office | Productivity and document management | ~8 |
| media | Media servers | ~3 |
| download | Download managers | ~2 |
| kube-system | Core cluster infrastructure | ~10 |
| storage | Persistent storage (Longhorn) | 1 |
| cert-manager | TLS certificate management | 1 |
| network | Ingress controllers, DNS, networking | ~6 |
| default | Dashboard (Homepage) + utilities | ~2 |
| flux-system | Flux GitOps operator | 1 |
| backup | External backup integrations | 1 |
| my-software-development | Custom app development | ~4 |
| my-software-production | Custom app production | ~2 |

---

## Versions Quick Reference

| Tool | Version | Purpose |
|------|---------|---------|
| Kubernetes | v1.34.0 | Container orchestration |
| Talos Linux | v1.11.0 | Cluster OS |
| Flux | v2.8.0 | GitOps operator |
| Cilium | v1.18.6 | CNI / network |
| Longhorn | v1.10.1 | Distributed storage |
| cert-manager | v1.19.3 | TLS management |
| Helm | 3.20.0 | Package manager |
| kubectl | 1.34.0 | CLI |
| talosctl | 1.11.0 | Talos CLI (server); client v1.12.4 |
| talhelper | 3.1.3 | Talos config helper |
| sops | 3.12.1 | Secrets encryption |
| age | 1.3.1 | Encryption backend |

---

## Development Environment

Tools managed via [mise](https://mise.jdx.dev/) — all defined in `.mise.toml`.

```bash
mise trust && mise install   # Install all tools
mise ls                      # Verify versions
```

Environment variables auto-set by mise:
```bash
KUBECONFIG=$PWD/kubeconfig
KUBERNETES_DIR=$PWD/kubernetes
SOPS_AGE_KEY_FILE=$PWD/age.key
TALOSCONFIG=$PWD/kubernetes/bootstrap/talos/clusterconfig/talosconfig
VIRTUAL_ENV=$PWD/.venv
```

---

## Operational Commands

```bash
# Cluster health
kubectl get nodes
kubectl get pods -A | grep -v Running | grep -v Completed

# GitOps status
flux get kustomizations -A
flux get helmreleases -A

# Storage
kubectl get volumes -n storage
kubectl get pv,pvc -A

# Certificates
kubectl get certificates -A
kubectl get certificaterequests -A

# Bootstrap (initial setup only)
task bootstrap:apps
talhelper validate kubernetes/bootstrap/talos/clusterconfig/
```

*See `docs/sops/` for system-specific SOPs.*
