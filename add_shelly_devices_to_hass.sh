#!/bin/bash

# CONFIGURATION
HA_URL="https://hass.example.com"
HA_TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJiYzBlMWJmNjI5Yzg0ZWUyODhlYjBhMWNmM2ViNjYwOSIsImlhdCI6MTc0NDgzMTE4MSwiZXhwIjoyMDYwMTkxMTgxfQ.V2IhsGys2BrEx9gNaTqzTZR_R55Oiw8qRf-_orji0Rc"
DEVICE_FILE="shelly_devices.yaml"

# Check for yq dependency
command -v yq >/dev/null 2>&1 || {
  echo >&2 "Please install 'yq' to parse YAML. Aborting."
  exit 1
}

device_count=$(yq eval '.devices | length' "$DEVICE_FILE")

for i in $(seq 0 $((device_count - 1))); do
  name=$(yq eval ".devices[$i].name" "$DEVICE_FILE")
  ip=$(yq eval ".devices[$i].ip" "$DEVICE_FILE")
  type=$(yq eval ".devices[$i].type" "$DEVICE_FILE")

  echo "Adding device: $name (IP: $ip, Type: $type)"

  curl -s -X POST "$HA_URL/api/config/device_registry/device" \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\n      \"config_entries\": [],\n      \"connections\": [[\"mac\", \"${ip//./-}\" ]],\n      \"identifiers\": [[\"shelly\", \"$ip\"]],\n      \"manufacturer\": \"Shelly\",\n      \"model\": \"$type\",\n      \"name\": \"$name\"\n    }"

  echo -e "\n→ Device \"$name\" added.\n"
done
