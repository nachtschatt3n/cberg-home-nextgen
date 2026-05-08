#!/usr/bin/env bash
# Apply 14-day retention to ECK Elasticsearch metrics indices.
#
# Why this lives here, not in a CRD: the ECK operator does NOT manage ILM
# policies — they're an Elasticsearch runtime concept stored in the cluster
# state. The repo's GitOps surface (the Elasticsearch CR) doesn't have a
# field for ILM policies. So we apply via REST and keep this script as the
# repeatable source of truth.
#
# Re-run after:
#   - A fresh ECK re-bootstrap (deletes cluster state).
#   - Restoring from a snapshot that didn't include ILM.
#   - Switching to a different ECK ES instance.
#
# The default x-pack 'metrics' policy ships with only a hot phase
# (rollover at 30d / 50gb). For homelab event volume, ~9 daily rollover
# indices ≈ 50 GB build up before this policy. Adding a delete phase at
# 14 days bounds total disk to ~5 indices ≈ 30 GB.

set -euo pipefail

NS=monitoring
POD=elasticsearch-es-default-0
SECRET=elasticsearch-es-elastic-user

PASS=$(kubectl get secret -n "$NS" "$SECRET" -o jsonpath='{.data.elastic}' | base64 -d)

echo "Applying 14d delete phase to ECK 'metrics' ILM policy..."
kubectl exec -n "$NS" "$POD" -- bash -c "curl -sk -u 'elastic:$PASS' -X PUT 'https://localhost:9200/_ilm/policy/metrics' -H 'Content-Type: application/json' -d '{
  \"policy\": {
    \"phases\": {
      \"hot\": {
        \"min_age\": \"0ms\",
        \"actions\": {
          \"rollover\": {
            \"max_age\": \"30d\",
            \"max_primary_shard_size\": \"50gb\"
          }
        }
      },
      \"delete\": {
        \"min_age\": \"14d\",
        \"actions\": { \"delete\": {} }
      }
    },
    \"_meta\": {
      \"managed_by\": \"cberg-home-nextgen\",
      \"description\": \"x-pack metrics policy + 14d delete phase (homelab retention)\"
    }
  }
}'"

echo "Verifying..."
kubectl exec -n "$NS" "$POD" -- bash -c "curl -sk -u 'elastic:$PASS' 'https://localhost:9200/_ilm/policy/metrics?pretty' | grep -A 3 delete"
