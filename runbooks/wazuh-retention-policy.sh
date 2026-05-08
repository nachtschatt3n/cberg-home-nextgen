#!/usr/bin/env bash
# Apply 14-day ISM retention policy to Wazuh indexer for wazuh-alerts-*
# and wazuh-archives-* index patterns.
#
# Why this lives here, not in a CRD: the Wazuh indexer (OpenSearch) ISM
# policies are runtime cluster state, not exposed via the StatefulSet CR.
# Running securityadmin.sh handles internal_users / roles / config, but
# NOT ISM policies — those have to be applied via the OpenSearch REST API.
#
# Re-run after:
#   - A fresh Wazuh-indexer re-bootstrap (deletes cluster state).
#   - Restoring from a snapshot that didn't include ISM.
#   - Tuning retention thresholds.
#
# Settings:
#   hot phase    rollover at 10 GB or 30 days
#   delete phase 14 days after index creation
#
# Indexes that match (via ism_template):
#   wazuh-alerts-*    (security events)
#   wazuh-archives-*  (every received event when <logall>yes — debug only)
#
# wazuh-states-inventory-* are NOT covered — they're refreshed on cycle,
# small (KB-MB scale), and not time-series. No retention needed.

set -euo pipefail

NS=security
POD=wazuh-indexer-0
USER=admin
PASS=admin   # see AR-024 for why these are the demo defaults

echo "Applying wazuh-retention-14d ISM policy..."
kubectl exec -n "$NS" "$POD" -- curl -sk -u "${USER}:${PASS}" -X PUT \
  'https://localhost:9200/_plugins/_ism/policies/wazuh-retention-14d' \
  -H 'Content-Type: application/json' \
  -d '{
    "policy": {
      "description": "Homelab retention: rollover wazuh-alerts/archives at 30d/10gb, delete after 14d",
      "default_state": "hot",
      "states": [
        {
          "name": "hot",
          "actions": [{"rollover": {"min_size": "10gb", "min_index_age": "30d"}}],
          "transitions": [{"state_name": "delete", "conditions": {"min_index_age": "14d"}}]
        },
        {
          "name": "delete",
          "actions": [{"delete": {}}],
          "transitions": []
        }
      ],
      "ism_template": [
        {"index_patterns": ["wazuh-alerts-*"], "priority": 1},
        {"index_patterns": ["wazuh-archives-*"], "priority": 1}
      ]
    }
  }'
echo

echo "Verifying..."
kubectl exec -n "$NS" "$POD" -- curl -sk -u "${USER}:${PASS}" \
  'https://localhost:9200/_plugins/_ism/policies/wazuh-retention-14d?pretty' \
  | head -c 400
echo
