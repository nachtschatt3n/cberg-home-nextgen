#!/usr/bin/env bash
# Stand up the Claude push-alert watcher's shell side: start the bridge (Mac) and
# apply the ephemeral Alertmanager webhook receiver. After running this, the
# ASSISTANT must start the Monitor ws source:  ws = { url: "ws://127.0.0.1:8787/" }.
# Tear down with alert-watch-down.sh when the watch session ends.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
WS_PORT="${WS_PORT:-8787}"
HTTP_PORT="${HTTP_PORT:-8788}"
PYBIN="$([ -x "$REPO/.venv/bin/python3" ] && echo "$REPO/.venv/bin/python3" || echo python3)"

# already up?
if curl -sf "http://127.0.0.1:${HTTP_PORT}/" >/dev/null 2>&1; then
  echo "bridge already running on :${HTTP_PORT}"
else
  echo "starting alert-bridge (ws :${WS_PORT}, webhook :${HTTP_PORT})..."
  WS_PORT="$WS_PORT" HTTP_PORT="$HTTP_PORT" nohup "$PYBIN" "$HERE/alert-bridge.py" \
    >/tmp/alert-bridge.log 2>&1 &
  echo $! > /tmp/alert-bridge.pid
  sleep 2
  grep 'up:' /tmp/alert-bridge.log || { echo "bridge failed to start; see /tmp/alert-bridge.log"; exit 1; }
fi

echo "applying ephemeral Alertmanager webhook receiver..."
kubectl apply -f "$HERE/claude-watch-webhook.yaml"

# verify cluster -> Mac reachability (webhook path)
echo "checking cluster -> Mac bridge reachability..."
kubectl run alert-watch-reach --rm -i --restart=Never --image=curlimages/curl:8.21.0 --timeout=60s -- \
  curl -s -m 8 -o /dev/null -w 'reach: HTTP %{http_code}\n' "http://192.168.30.111:${HTTP_PORT}/" 2>&1 | grep -E 'HTTP|refused|timed' || true

echo "UP. Now have the assistant start:  Monitor ws url=ws://127.0.0.1:${WS_PORT}/"
echo "Tear down with: $HERE/alert-watch-down.sh"
