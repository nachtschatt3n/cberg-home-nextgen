#!/bin/bash

# This script updates the Langfuse configuration in Home Assistant with the new working API keys

NAMESPACE="home-automation"
DEPLOYMENT="home-assistant"

# New working keys from Langfuse UI
NEW_PUBLIC_KEY="pk-lf-90a391b7-9857-449b-952e-ab37a96fdf72"
NEW_SECRET_KEY="sk-lf-16ca1277-9e07-436f-a323-d64d8122e716" 
NEW_HOST="https://langfuse.example.com"

echo "Updating Home Assistant Langfuse configuration..."

# Copy the current config to a backup
kubectl exec -n $NAMESPACE deployment/$DEPLOYMENT -- cp /config/.storage/core.config_entries /config/.storage/core.config_entries.backup

# Update the configuration
kubectl exec -n $NAMESPACE deployment/$DEPLOYMENT -- sh -c "
cat /config/.storage/core.config_entries | jq '
(.data.entries[] | select(.domain == \"custom_conversation\") | .options.langfuse.langfuse_public_key) |= \"$NEW_PUBLIC_KEY\" |
(.data.entries[] | select(.domain == \"custom_conversation\") | .options.langfuse.langfuse_secret_key) |= \"$NEW_SECRET_KEY\" |
(.data.entries[] | select(.domain == \"custom_conversation\") | .options.langfuse.langfuse_host) |= \"$NEW_HOST\"
' > /tmp/updated_config.json && mv /tmp/updated_config.json /config/.storage/core.config_entries
"

echo "Configuration updated. Restarting Home Assistant to apply changes..."

# Restart Home Assistant to apply the configuration changes
kubectl rollout restart -n $NAMESPACE deployment/$DEPLOYMENT

echo "Home Assistant is restarting. Monitor with: kubectl logs -n $NAMESPACE -f deployment/$DEPLOYMENT"
echo "Done!"