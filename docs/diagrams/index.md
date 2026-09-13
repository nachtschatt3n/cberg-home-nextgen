# Diagrams

Interactive architecture and process diagrams for this cluster. Each opens as a
standalone page with its own light/dark theme, pan/zoom, search, guided views,
and PNG/SVG export. Sources are the `.json` specs beside each HTML file
(rendered with [Archify](https://github.com/tt-a1i/archify); regenerate by
editing the spec and re-delivering — do not hand-edit the HTML).

## Network & ingress

- [Home Network Topology](home-network.html){ target=_blank } — fiber uplink, 10 GbE backbone, VLANs, WiFi, NAS, and the k8s nodes.
- [External Ingress Path](external-ingress.html){ target=_blank } — Cloudflare Tunnel → envoy-external, wildcard TLS, external-dns, Authentik.
- [Internal Ingress & DNS](internal-ingress.html){ target=_blank } — AdGuard → k8s-gateway split-horizon DNS, envoy-internal, forward-auth.

## Cluster & GitOps

- [Kubernetes Cluster](k8s-cluster.html){ target=_blank } — Talos/Cilium cluster, both gateways, GitOps loop, storage, monitoring.
- [Flux Reconcile Flow](flux-reconcile.html){ target=_blank } — push → webhook → SOPS decrypt → apply, with the flux-guardrails policy.

## Operations

- [Maintenance-Window Pipeline](maintenance-window.html){ target=_blank } — Step 0 safe updates, plan vetting, autonomy classes, auto-revert.
- [Operation Sweep](operation-sweep.html){ target=_blank } — the 48h cron, six specialists, one shared cycle, deterministic board.
- [Update Decision Lifecycle](update-lifecycle.html){ target=_blank } — the six gates and the safe / held / reverted state machine.
- [Longhorn Backup & Restore](longhorn-backup.html){ target=_blank } — nightly snapshots → Backup CRs → NAS, and the restore contract.

## Applications

- [Paperless Document Ingestion](paperless-ingestion.html){ target=_blank } — scanner + email intake, validation, OCR, native AI, storage.
- [Media Intake Workflow](media-intake.html){ target=_blank } — ffprobe evidence, operator gate, atomic moves, targeted rescans.
- [Home Automation Stack](home-automation.html){ target=_blank } — Zigbee mesh → Z2M → MQTT → Home Assistant, Matter/Thread, NVR.
