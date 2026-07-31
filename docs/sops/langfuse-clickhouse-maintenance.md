# SOP: langfuse ClickHouse maintenance — system-log bloat + TTL traps

> Version: `2026.07.31`
> Last Updated: `2026-07-31`

## 1) Description

langfuse (v3) stores traces/observations/scores in ClickHouse. On 2026-07-31
the Longhorn PVC `langfuse-clickhouse-data-new` (namespace `ai`) tripped
`LonghornVolumeUsageWarning` at ~81% — but **the bloat was NOT langfuse data.**
It was **ClickHouse's own diagnostic system logs**, which ship with **no TTL**
and grow unbounded, while langfuse never reads them:

| Table | Size | Rows |
|---|---|---|
| `system.asynchronous_metric_log` | **10.5 GiB** | 20.6 billion |
| `system.metric_log` | 1.96 GiB | — |
| `system.trace_log` | 453 MiB | — |
| **actual langfuse data** (`default.observations/traces/scores`) | **~2 MiB** | 88 |

So a TTL on langfuse's trace tables reclaims ~nothing; the fix is on the
**system-log** side. This SOP captures the reclaim + the durable TTL config and
the non-obvious crash trap hit while applying it.

Related: `docs/sops/monitoring.md`, `docs/sops/longhorn.md`,
`docs/sops/storage-safety.md`. Commits: `a288187b`, `852eb8ff`.

## 2) Overview

- **Symptom:** `LonghornVolumeUsageWarning` on `langfuse-clickhouse-data-new`
  (ai), flapping around ~80% as ClickHouse ingests system metrics then merges.
- **Root cause:** ClickHouse system-log tables (`asynchronous_metric_log`,
  `metric_log`, `trace_log`, `query_log`, …) have no default TTL and
  `asynchronous_metrics_update_period_s` defaults to 1s → ~20B rows accumulate.
- **Durable fix (git):** `kubernetes/apps/ai/langfuse/app/clickhouse.yaml` mounts
  a `config.d/system-log-ttl.xml` that sets a **3-day TTL** on the system-log
  tables and raises the async-metrics period 1s→60s (~60× less write volume).
- **Reclaim (one-time, operator-approved data drop):** `TRUNCATE` the system
  diagnostic tables (they're pure telemetry — safe to drop), then let Longhorn
  reclaim the freed blocks via the scheduled `filesystem-trim` RecurringJob.
- **langfuse data is never touched** — `default.*` tables are
  `ReplicatedReplacingMergeTree`, langfuse-migration-managed; leave them alone.

## 3) Blueprints

N/A. Plain ClickHouse `config.d` override (ConfigMap + volumeMount in the
langfuse clickhouse manifest) + a one-time SQL reclaim. No Authentik/Homepage.

## 4) Operational Instructions

### Durable config (already in git — this is the reference)
`config.d/system-log-ttl.xml` sets, per system-log table:
`TTL event_date + toIntervalDay(3)` and `asynchronous_metrics_update_period_s=60`.
Applied both as startup config (durable across restarts) AND live via
`ALTER TABLE system.<t> MODIFY TTL event_date + INTERVAL 3 DAY` so existing
tables self-cap immediately. Edit the XML, commit, push (Flux rolls the pod).

### ⚠️ The `opentelemetry_span_log` trap (this WILL crash ClickHouse)
Do **NOT** add a `<ttl>` to `opentelemetry_span_log` (or any system-log table
whose base config already defines an explicit `<engine>`). ClickHouse rejects a
separate `<ttl>` alongside an explicit `<engine>` with
`Code 36 BAD_ARGUMENTS` → the gateway aborts on startup → **CrashLoopBackOff**
(hit 2026-07-31, fixed in `852eb8ff` by dropping that one line). That table is
<1 MiB — leave it at default. Only TTL the tables that use the implicit engine.

### One-time reclaim (operator-approved — drops telemetry only)
```bash
POD=$(kubectl get pod -n ai -l app.kubernetes.io/component=clickhouse -o name | head -1)
# Safe: these are ClickHouse's own diagnostics, not langfuse data.
for t in asynchronous_metric_log metric_log trace_log query_log query_views_log part_log; do
  kubectl exec -n ai "${POD#pod/}" -- clickhouse-client -q "TRUNCATE TABLE IF EXISTS system.$t"
done
# NEVER truncate default.* (langfuse traces/observations/scores).
```
Longhorn block reclaim then happens at the scheduled `langfuse-clickhouse-
filesystem-trim` RecurringJob (02:00). To reclaim now: an on-demand Longhorn
`trimFilesystem` on the volume (a shared-storage op — see storage-safety.md).

## 5) Examples

```
before:  /var/lib/clickhouse  13.2 GiB / 68%   (asynchronous_metric_log 10.5 GiB)
after :  /var/lib/clickhouse  12.9 MiB / 0%    (system logs truncated + 3d TTL)
langfuse data: unchanged, ~2 MiB, /api/public/health = 200
```

## 6) Verification Tests

```bash
POD=$(kubectl get pod -n ai -l app.kubernetes.io/component=clickhouse -o name | head -1)
# 1) TTLs are set on the system-log tables (expect 3-day intervals)
kubectl exec -n ai "${POD#pod/}" -- clickhouse-client -q \
  "SELECT name, engine_full FROM system.tables WHERE database='system' AND name IN ('asynchronous_metric_log','metric_log','trace_log') FORMAT Vertical" | grep -i ttl
# 2) langfuse data intact + healthy
kubectl exec -n ai "${POD#pod/}" -- clickhouse-client -q \
  "SELECT count() FROM default.observations"          # non-negative, unchanged
kubectl exec -n ai deploy/langfuse-web -- wget -qO- localhost:3000/api/public/health   # 200/ok
# 3) filesystem actually reclaimed
kubectl exec -n ai "${POD#pod/}" -- df -h /var/lib/clickhouse
```

## 7) Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| ClickHouse CrashLoop after a config edit, `Code 36 BAD_ARGUMENTS` | added `<ttl>` to a system-log table with an explicit `<engine>` (e.g. `opentelemetry_span_log`) | remove that TTL line; only TTL implicit-engine tables |
| PVC usage warning still firing after truncate | Longhorn block-level `actualSize` not yet TRIM'd | wait for the 02:00 `filesystem-trim` job, or run an on-demand `trimFilesystem` |
| Volume re-fills over days | system-log TTL not applied / async period back to 1s | re-verify `config.d/system-log-ttl.xml` mounted; check the pod picked it up |
| langfuse data missing | someone truncated `default.*` | restore from Longhorn backup — NEVER truncate `default.*` |

## 8) Diagnose Examples

```bash
POD=$(kubectl get pod -n ai -l app.kubernetes.io/component=clickhouse -o name | head -1)
# What's actually eating the disk? (system logs vs langfuse data)
kubectl exec -n ai "${POD#pod/}" -- clickhouse-client -q \
  "SELECT database, table, formatReadableSize(sum(bytes_on_disk)) sz, sum(rows) FROM system.parts WHERE active GROUP BY database, table ORDER BY sum(bytes_on_disk) DESC LIMIT 10"
```

## 9) Health Check

```bash
kubectl get pods -n ai -l app.kubernetes.io/component=clickhouse   # 1/1 Running, stable restarts
kubectl exec -n ai deploy/langfuse-web -- wget -qO- localhost:3000/api/public/health
kubectl exec -n ai "$(kubectl get pod -n ai -l app.kubernetes.io/component=clickhouse -o name|head -1|sed s@pod/@@)" -- clickhouse-client -q "SELECT 1"
```

## 10) Security Check

- Only ClickHouse **telemetry** is dropped; no langfuse user/trace data, no
  secrets, no SOPS content touched. `default.*` is off-limits.
- The `config.d` override is a plain ConfigMap (no secrets). Confirm no
  credentials leaked into the XML.

## 11) Rollback Plan

```bash
# Config: revert the langfuse clickhouse commits — ClickHouse reverts to
# un-capped system logs (the bloat will slowly return).
git revert 852eb8ff a288187b && git push
# Data: the TRUNCATE'd system diagnostics are gone (operator-approved,
# non-recoverable) — they regenerate. langfuse data was never touched, so
# nothing to restore there. If langfuse data was ever lost, restore PVC
# langfuse-clickhouse-data-new from its Longhorn backup (docs/sops/backup.md).
```

## 12) References

- Config: `kubernetes/apps/ai/langfuse/app/clickhouse.yaml` (`config.d/system-log-ttl.xml`)
- Incident + fix commits: `a288187b`, `852eb8ff`
- Storage reclaim: `docs/sops/longhorn.md`, `docs/sops/storage-safety.md`

## Version History

| Version | Date | Change |
|---|---|---|
| 2026.07.31 | 2026-07-31 | Initial SOP after the system-log bloat incident: 3-day TTL on ClickHouse system logs + async-period 60s, one-time truncate reclaim (68%→0%), and the `opentelemetry_span_log` TTL/base-engine CrashLoop trap. |
