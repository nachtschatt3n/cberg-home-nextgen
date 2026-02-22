# Troubleshooting Notes & Learnings

## 2026-02-22

### 1. Fluent Bit Retry Backlog
**Issue:** `FluentBitRetryBacklogCritical` alerts. Fluent Bit unable to flush chunks to Elasticsearch.
**Root Cause:** Mapping conflict in Elasticsearch. Logs contained `app` field as both a concrete string and a nested object (e.g., `app.kubernetes.io/name`), causing `document_parsing_exception`.
**Resolution:**
- Enabled `Replace_Dots On` in Fluent Bit `[OUTPUT]` configuration to flatten labels.
- Deleted the corrupted daily index `fluent-bit-2026.02.22` to reset mappings.
- Restarted Fluent Bit pods.
- Persisted `Replace_Dots On` in `kubernetes/apps/monitoring/fluent-bit/app/helmrelease.yaml`.

### 2. Node DNS Timeouts (False Positive)
**Issue:** Health check reported "High hardware errors" on node `192.168.55.12`.
**Analysis:** `talosctl dmesg` showed `[talos] error serving dns request ... context deadline exceeded`.
**Context:** The timestamps on these errors were from `2026-02-19`, indicating a transient network/DNS issue that occurred days prior.
**Resolution:** Verified current logs are clean of these errors. No action required. Future health checks should filter by timestamp if possible to avoid alerting on stale logs.

### 3. Flux ImagePolicy API Deprecation
**Issue:** Kustomizations for `absenty` failing with `no matches for kind "ImagePolicy" in version "image.toolkit.fluxcd.io/v1"`.
**Root Cause:** The manifests were using `v1` but the cluster CRD only supports `v1beta1` and `v1beta2`.
**Resolution:** Downgraded manifests to `v1beta2` in:
- `kubernetes/apps/my-software-development/absenty/app/image-automation.yaml`
- `kubernetes/apps/my-software-production/absenty/app/image-automation.yaml`
