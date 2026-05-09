# Wazuh Dashboards (saved-objects NDJSON)

Saved-object exports for Wazuh / OpenSearch Dashboards visualisations and dashboards
specific to this cluster's data flows. Re-import these after a Wazuh dashboard rebuild
or pod re-init to restore the cluster-specific UI surface that the stock Wazuh app
doesn't ship.

## Contents

| File | What it ships |
|---|---|
| `unifi-dashboard.ndjson` | "UniFi — Security Events" dashboard (7 visualisations, all auto-filtered to `decoder.name:"unifi"`) |
| `build-unifi-dashboard.py` | Generator script — re-run after edits, then re-import |

## Manual re-import

Run from this machine (kubectl + cluster access):

```bash
ADMIN=$(mise exec -- kubectl get secret wazuh-secret -n security -o jsonpath='{.data.INDEXER_PASSWORD}' | base64 -d)
POD=$(mise exec -- kubectl get pod -n security -l app=wazuh-dashboard -o jsonpath='{.items[0].metadata.name}')

# Stream the NDJSON into the pod (image has no `tar`, so kubectl cp doesn't work)
B64=$(base64 < unifi-dashboard.ndjson | tr -d '\n')
mise exec -- kubectl exec -n security $POD -- bash -c "echo '$B64' | base64 -d > /tmp/unifi-dashboard.ndjson"

# Import (overwrite=true makes this idempotent)
mise exec -- kubectl exec -n security $POD -- bash -c "
  curl -sk -u 'admin:$ADMIN' -H 'osd-xsrf: true' \
    -X POST 'https://localhost:5601/api/saved_objects/_import?overwrite=true' \
    --form file=@/tmp/unifi-dashboard.ndjson
"
```

Expected response: `{"successCount":8,"success":true,...}`.

## Updating the UniFi dashboard

1. Edit `build-unifi-dashboard.py`
2. Re-generate: `python3 build-unifi-dashboard.py > unifi-dashboard.ndjson`
3. Re-import (commands above) — `overwrite=true` replaces in place
4. Commit both files in the same PR

## Why not auto-import via init-container

The Wazuh dashboard image doesn't expose a hook for first-boot saved-object loading,
and bolt-on init containers would need the same admin password the dashboard itself
uses (creating a circular secret reference). The manual flow is two minutes after a
rebuild — acceptable cadence for a homelab.

If/when this becomes painful, options:
- Sidecar that polls for dashboard readiness and POSTs the NDJSON
- ConfigMap-mounted JSON + a CronJob that imports on schedule
- Migrate to Wazuh app plugin's native dashboard contribution model
