# Version And Migration State

Generated: 2026-02-21 10:21:41 CET

## Data Sources

- Full version scan: `tools/check-all-versions.py`
- Generated report: `AI_version_check_current.md`
- Open PR data: `gh pr list`, `gh pr view`
- Renovate dashboard: `gh issue view 7`
- Runtime inventory: `kubectl get helmreleases -A`, `kubectl get pods -A`, `kubectl get nodes`

## Current State Snapshot

- Deployments parsed by version scanner: 68
- Chart updates available: 11
- Image updates available: 16
- Complexity mix: 5 major, 10 minor, 9 patch
- Potential breaking changes flagged: 8
- Open Renovate PRs: 10 (2 major, 5 minor, 3 patch)
- Pending approval entries in Renovate dashboard issue #7: 51 unchecked

## Coverage Gaps And Blockers

The scanner skipped 2 HelmRelease files because of duplicate YAML anchors:

- `kubernetes/apps/databases/mariadb/app/helmrelease.yaml:72`
- `kubernetes/apps/databases/influxdb/app/helmrelease.yaml:90`

Root cause: the `&host` anchor is declared twice in each file (`hostname` and `hosts[0]`), which is invalid YAML for strict parsers.

## Runtime Baseline (Cluster)

- HelmReleases in cluster: 73
- HelmRelease readiness: 72 ready, 1 not ready
- Not-ready release: `my-software-development/opencode-andreamosteller` (Helm install failed, context deadline exceeded)
- Pods: 205 across 16 namespaces
- Unique container images currently running: 139
- Node drift vs desired Talos config:
  - Running: Kubernetes `v1.34.0`, Talos `v1.11.0`
  - Desired in `kubernetes/bootstrap/talos/talconfig.yaml`: Kubernetes `v1.34.3`, Talos `v1.11.6`

## Open PR Migration Paths

### PR #77 - n8n patch (`1.123.20` -> `1.123.21`)

- File: `kubernetes/apps/home-automation/n8n/app/helmrelease.yaml`
- Complexity: patch, low risk
- Path:
  1. Merge PR #77 only if deferring n8n v2 migration.
  2. Reconcile Flux and wait for rollout.
  3. Validate editor UI, webhook execution, queue workers, and DB connectivity.
- Rollback: revert tag to `1.123.20`.

### PR #76 - sops CLI toolchain (`3.11.0` -> `3.12.0`)

- File: `.mise.toml`
- Complexity: minor, low production risk (developer tooling only)
- Path:
  1. Merge PR #76.
  2. Run `mise install` and `sops --version` locally/CI.
  3. Re-run secret edit/decrypt smoke test.
- Rollback: revert `.mise.toml`.

### PR #75 - jdownloader (`v26.01.1` -> `v26.02.2`)

- File: `kubernetes/apps/download/jdownloader/app/helmrelease.yaml`
- Complexity: minor
- Path:
  1. Merge PR #75 and reconcile.
  2. Confirm pod restart and reconnect to downloads storage.
  3. Validate active jobs and web UI.
- Rollback: revert image tag.

### PR #74 - esphome (`2026.1.4` -> `2026.2.1`)

- File: `kubernetes/apps/home-automation/esphome/app/helmrelease.yaml`
- Complexity: minor (monthly release train)
- Path:
  1. Merge PR #74 and reconcile.
  2. Verify compile/install of one known-good device.
  3. Confirm API connectivity from Home Assistant.
- Rollback: revert image tag.

### PR #73 - uptime-kuma chart (`2.24.0` -> `2.25.0`)

- File: `kubernetes/apps/monitoring/uptime-kuma/app/helmrelease.yaml`
- Complexity: minor
- Path:
  1. Merge PR #73.
  2. Confirm values schema compatibility (no dropped keys).
  3. Validate monitor list, notification channels, and historical data retention.
- Rollback: revert chart version.

### PR #72 - paperless-ngx (`2.20.6` -> `2.20.7`)

- File: `kubernetes/apps/office/paperless-ngx/app/helmrelease.yaml`
- Complexity: patch
- Path:
  1. Merge PR #72.
  2. Check web UI login and document ingest pipeline.
  3. Validate Redis and MariaDB sidecars stay healthy.
- Rollback: revert image tag.

### PR #71 - postgres image for Authentik cleanup job (`17.7` -> `17.8`)

- File: `kubernetes/apps/kube-system/authentik/app/cronjob-channels-cleanup.yaml`
- Complexity: minor
- Path:
  1. Merge PR #71.
  2. Trigger or wait for next CronJob run.
  3. Confirm job completes and does not fail on SQL compatibility.
- Rollback: revert image tag.

### PR #70 - Talos/Kubelet patch (`v1.34.3` -> `v1.34.4`)

- File: `kubernetes/bootstrap/talos/talconfig.yaml`
- Complexity: patch, operationally sensitive
- Path:
  1. Merge PR #70.
  2. Upgrade Talos nodes one at a time (control-plane safe order).
  3. Validate each node returns `Ready` before moving to the next.
  4. Re-check workloads and CNI after full rollout.
- Rollback: pin back to previous Talos/Kubernetes versions and roll nodes back in reverse order.

### PR #67 - kube-prometheus-stack chart (`81.5.0` -> `81.6.9`)

- File: `kubernetes/apps/monitoring/kube-prometheus-stack/app/helmrelease.yaml`
- Complexity: labeled major, treat as high-risk monitoring stack change
- Path:
  1. Merge PR #67 in isolation (no concurrent monitoring stack changes).
  2. Ensure CRD/Helm hook upgrade completes.
  3. Validate Prometheus targets, Alertmanager routing, and key Grafana dashboards.
  4. Check alert noise deltas for 24h after rollout.
- Rollback: revert chart version and reconcile.

### PR #40 - n8n major (`1.123.20` -> `2.9.1`)

- File: `kubernetes/apps/home-automation/n8n/app/helmrelease.yaml`
- Complexity: major, high risk
- Path:
  1. Snapshot n8n DB and current PVC before merge.
  2. Review n8n v2 breaking changes and credentials/workflow compatibility.
  3. Run upgrade during maintenance window.
  4. Validate workflow executions, triggers, webhook endpoints, queue mode, and credentials decryption.
- Rollback: restore DB/PVC snapshot and revert image tag to `1.123.20`.

Conflict note: PR #77 and PR #40 target the same file. Choose one sequence:

- Short-term stability: merge #77 now, defer #40.
- Fast major migration: close #77 and execute #40 directly.

## Staged Major Migrations Not Yet In Open PRs

### Nextcloud chart `6.6.10` -> `8.9.1`

- File: `kubernetes/apps/office/nextcloud/app/helmrelease.yaml`
- Source: `https://github.com/nextcloud/helm/releases/tag/8.9.1`
- Path:
  1. Take DB backup and volume snapshot.
  2. Diff chart values against new chart defaults (major schema drift expected).
  3. Upgrade chart in maintenance window.
  4. Run Nextcloud post-upgrade checks (`occ status`, app compatibility, cron jobs).
- Rollback: restore DB and data volume snapshot, revert chart version.

### Open WebUI chart `10.2.1` -> `12.3.0` and image `0.7.2` -> `0.8.3`

- File: `kubernetes/apps/ai/open-webui/app/helmrelease.yaml`
- Sources:
  - `https://github.com/open-webui/open-webui/releases/tag/12.3.0`
  - `https://github.com/open-webui/open-webui/releases/tag/0.8.3`
- Path:
  1. Export/backup Open WebUI config and state volume.
  2. Apply chart major first with existing image pin if possible.
  3. Then upgrade image to `0.8.3`.
  4. Validate model providers, auth settings, tool integrations, and file upload/vision flows.
- Rollback: revert chart/image and restore state volume snapshot.

### ECK operator chart `2.14.0` -> `3.3.0`

- File: `kubernetes/apps/monitoring/eck-operator/app/helmrelease.yaml`
- Source: `https://github.com/elastic/cloud-on-k8s/releases/tag/3.3.0`
- Path:
  1. Review CRD changes before rollout.
  2. Upgrade operator first, then watch Elasticsearch/Kibana custom resources.
  3. Confirm reconciliation health and StatefulSet stability for Elastic workloads.
  4. Verify snapshots, ILM, and ingest pipelines remain functional.
- Rollback: operator rollback only after confirming CRD compatibility constraints.

### Uptime Kuma chart `2.24.0` -> `4.0.0`

- File: `kubernetes/apps/monitoring/uptime-kuma/app/helmrelease.yaml`
- Source: `https://github.com/louislam/uptime-kuma/releases/tag/4.0.0`
- Path:
  1. Back up monitor DB/PVC.
  2. Validate chart values compatibility against v4.
  3. Upgrade chart and then validate monitor definitions and notifications.
  4. Keep image patch (`2.1.3`) independent from chart-major step when possible.
- Rollback: restore PVC and revert chart.

## Recommended Execution Order

1. Resolve baseline readiness issue for `opencode-andreamosteller`.
2. Fix YAML anchor errors in MariaDB/Influxdb HelmReleases so they are included in future scans.
3. Merge patch PRs (#70, #72, #77 or #40 decision) with post-merge verification.
4. Merge low-risk minor PRs (#71, #73, #74, #75, #76).
5. Execute major upgrades one-by-one with snapshots and explicit rollback points.
