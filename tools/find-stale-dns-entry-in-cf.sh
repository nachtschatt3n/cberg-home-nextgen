# get your zone ID first
ZONE_ID=$(curl -s -X GET "https://api.cloudflare.com/client/v4/zones?name=example.com" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  | jq -r '.result[0].id')

# list all TXT heritage records
curl -s -X GET "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/dns_records?type=TXT&per_page=100" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
| jq -r '.result[] | "\(.name) \(.content)"' \
| while read NAME CONTENT; do

    # pull out kind/namespace/name
    RESOURCE=$(echo "$CONTENT" | sed -n 's/.*external-dns\/resource=\([^,]*\).*/\1/p')
    KIND=${RESOURCE%%/*}                             # e.g. "cname" or "service"
    NS=$(echo "$RESOURCE" | cut -d/ -f2)             # e.g. "network"
    OBJECT=$(echo "$RESOURCE" | cut -d/ -f3)         # e.g. "echo-server"

    # map our "cname" pseudo‐kind back to ingress
    if [ "$KIND" = "cname" ]; then
      KIND=ingress
    fi

    # test for its existence
    if ! kubectl get $KIND "$OBJECT" -n "$NS" &>/dev/null; then
      echo "⚠️ STALE: $NAME (was $KIND/$NS/$OBJECT)"
    fi
  done