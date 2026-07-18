#!/usr/bin/env bash
# Tear down the Claude push-alert watcher's shell side: delete the ephemeral
# Alertmanager webhook receiver (so Alertmanager stops POSTing to a dead bridge)
# and stop the bridge process. The assistant should also TaskStop the Monitor ws.
set -uo pipefail
HTTP_PORT="${HTTP_PORT:-8788}"

echo "deleting ephemeral Alertmanager webhook receiver..."
kubectl delete alertmanagerconfig -n monitoring claude-watch-webhook --ignore-not-found=true

echo "stopping alert-bridge..."
if [ -f /tmp/alert-bridge.pid ]; then
  kill "$(cat /tmp/alert-bridge.pid)" 2>/dev/null || true
  rm -f /tmp/alert-bridge.pid
fi
# belt-and-suspenders: kill anything still bound to the webhook port
pkill -f alert-bridge.py 2>/dev/null || true

echo "DOWN. (Assistant: TaskStop the Monitor ws watch too.)"
