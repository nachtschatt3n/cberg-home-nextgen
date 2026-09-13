# Homelab Handbook

Rendered documentation for the [cberg-home-nextgen](https://github.com/nachtschatt3n/cberg-home-nextgen)
cluster — Talos + Flux GitOps on 3× NUC14, rebuilt nightly from `main`.

## Start here

- [Infrastructure reference](docs/infrastructure.md) — topology, nodes, platform services
- [Application inventory](docs/applications.md) — every deployed app and where it lives
- [Network reference](docs/network.md) — VLANs, WiFi, routing
- [Security reference](docs/security.md)
- [Interactive diagrams](docs/diagrams/index.md) — network, ingress, GitOps, operations

## Operating the cluster

- [New deployment blueprint](docs/sops/new-deployment-blueprint.md) — the SOP for rolling out anything new
- [Maintenance windows](docs/sops/maintenance-windows.md) and [auto-update](docs/sops/auto-update.md)
- [Storage safety](docs/sops/storage-safety.md) — read before touching any PVC
- [Health check runbook](runbooks/health-check.md) · [Security check runbook](runbooks/security-check.md)

Everything under **Docs → Sops** is a standing operating procedure; **Runbooks**
hold recurring procedures and their scripts (only the markdown is rendered
here). Generated `*-current.md` reports are deliberately absent — they live on
the operator machine and in sweep-history Postgres, not in git.
