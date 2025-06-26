#!/usr/bin/env bash
#
#  unifi-temp-discover.sh
#  ----------------------------------------------------------
#  Discover every UniFi device via Controller API,
#  probe its SNMP agent for temperature sensors,
#  and emit a Kuma-ready table.
#
#  USAGE
#    ./unifi-temp-discover.sh -h unifi.uhl.cool -t <JWT>
#
#  If you prefer a fixed host list, skip -h/-t and pass IPs:
#    ./unifi-temp-discover.sh 192.168.30.1 192.168.30.220
#  ----------------------------------------------------------

set -euo pipefail

########## 1.  CLI args ##############################################
CTRL_HOST=""      # e.g. unifi.uhl.cool  (https on port 443)
TOKEN=""          # API token (Settings › System › API Access)
COMMUNITY="public"
USER="" AUTH="" PRIV=""   # for SNMPv3 (optional)
SNMPV="2c"        # change to 3 if you fill USER/AUTH/PRIV
HOSTS=()          # filled later

usage() {
cat <<EOF
Usage: $0 [-h controllerHost] [-t apiToken] [-c community] [-v 3 -u user -A auth -X priv] [ip1 ip2 …]
  -h  UniFi controller hostname (https)
  -t  Bearer token from UniFi OS (read-only)
  -c  SNMP community (default: public)
  -v  SNMP version (2c or 3); default 2c
  -u/A/X  SNMPv3 user / auth-pass / priv-pass
If ip list is omitted and -h/-t are given, the script auto-discovers
all device IPs from the controller.
EOF
exit 1
}

while getopts "h:t:c:v:u:A:X:" opt; do
  case $opt in
    h) CTRL_HOST=$OPTARG ;;
    t) TOKEN=$OPTARG ;;
    c) COMMUNITY=$OPTARG ;;
    v) SNMPV=$OPTARG ;;
    u) USER=$OPTARG ;;
    A) AUTH=$OPTARG ;;
    X) PRIV=$OPTARG ;;
    *) usage ;;
  esac
done
shift $((OPTIND-1))
HOSTS+=("$@")

[[ -z ${HOSTS[*]} && ( -z $CTRL_HOST || -z $TOKEN ) ]] && usage

########## 2.  Get IPs from controller (if needed) ###################
if [[ ${#HOSTS[@]} -eq 0 ]]; then
  HOSTS=($(curl -sSk \
    -H "Authorization: Bearer $TOKEN" \
    "https://${CTRL_HOST}/proxy/network/api/s/default/stat/device" \
    | jq -r '.data[].ip'))
fi

########## 3.  Candidate temp roots #################################
CANDIDATE_OIDS=(
  1.3.6.1.2.1.99.1.1.1.4                    # ENTITY-SENSOR
  1.3.6.1.4.1.2021.13.16.2.1.3              # UCD envTable  (UDM/UXG)
  1.3.6.1.4.1.4413.1.1.36.2.1.1.5           # Edge-Core Enterprise switch
  1.3.6.1.4.1.41112.1.6.1.1.12              # Gen-2/Pro switch
  1.3.6.1.4.1.41112.1.60.13.1.3             # Wi-Fi 6 AP
  1.3.6.1.4.1.10002.1.2.1.8                 # Lite/Flex switch
  1.3.6.1.4.1.10002.1.4.7.1.3               # AC-series AP
)

########## 4.  SNMP helpers ##########################################
snmp() {        # $1 host   $2 oid
  if [[ $SNMPV == 3 ]]; then
    snmpwalk -v3 -l authPriv -u "$USER" -A "$AUTH" -X "$PRIV" "$1" "$2" 2>/dev/null
  else
    snmpwalk -v"$SNMPV" -c "$COMMUNITY" "$1" "$2" 2>/dev/null
  fi
}

########## 5.  Output header #########################################
printf "\n%-15s  %-45s %-7s %-9s\n" "HOST" "OID" "DIV" "°C"
printf "%-15s  %-45s %-7s %-9s\n" "---------------" "---------------------------------------------" "----" "-------"

########## 6.  Main discover loop ###################################
for h in "${HOSTS[@]}"; do
  printed=0
  for root in "${CANDIDATE_OIDS[@]}"; do
    result=$(snmp "$h" "$root" | grep -E '(INTEGER|Gauge32): [1-9]' || true)
    [[ -z $result ]] && continue

    while IFS= read -r line; do
      oid=$(cut -d' ' -f1 <<< "$line")
      raw=$(grep -oE '[0-9]+$' <<< "$line")
      (( raw == 0 )) && continue        # skip zero sensors
      div=1 temp=$raw
      if (( raw > 1000 )); then
        div=1000
        temp=$(awk "BEGIN{printf \"%.1f\", $raw/1000}")
      fi
      printf "%-15s  %-45s %-7s %-9s\n" "$h" "$oid" "$div" "$temp"
      printed=1
      break   # stop after first live sensor from this root
    done <<< "$result"
    (( printed )) && break   # stop after first live root for this host
  done
  (( printed )) || printf "%-15s  (no temp sensor) \n" "$h"
done

cat <<'EOF'

────────  HOW TO USE IN UPTIME KUMA  ────────
For each line above …
  • Host          →  Host field
  • OID           →  OID field
  • DIV = 1000    →  put 1000 in "Divider" (Advanced)¹
  • DIV = 1       →  leave Divider empty
  • Set "Comparison >= ", Expected = 65 (or your own limit)
  • Expect monitor = DOWN
  • Heartbeat = 30–60 s
¹ Any sensor that showed 48 000 becomes 48.0 °C.

The script is idempotent: re-run after firmware upgrades and copy the
new OID if the index ever changes.
EOF
