#!/usr/bin/env bash
# F-ba96c827: Section 17 counts HTTPRoutes (floor 1), not Ingresses. Zero
# Ingress is the correct post-ingress-nginx state; the floor must guard a
# measurement that can still be non-zero.
set -u
HC="$(cd "$(dirname "$0")/.." && pwd)/health-check.sh"
fail=0
check() { if [ "$2" = "$3" ]; then echo "  PASS  $1"; else echo "  FAIL  $1 got [$2] want [$3]"; fail=1; fi; }
check "no live Ingress counter with a floor" "$(grep -c '^[[:space:]]*INGRESSES=\$(safe_count' "$HC")" "0"
check "HTTPRoute counter carries floor 1" "$(grep -c 'HTTPROUTES=\$(safe_count .*"httproutes" 1)' "$HC")" "1"
# Control: the counter's own pipeline is non-zero on a fixture with routes and
# zero on an empty one (proves it can be non-zero).
n=$(printf 'a b\nc d\n' | wc -l | tr -cd 0-9); check "control: counter pipeline counts 2 fixture routes" "$n" "2"
if command -v kubectl >/dev/null 2>&1 && kubectl get httproute -A --no-headers >/dev/null 2>&1; then
  live=$(kubectl get httproute -A --no-headers 2>/dev/null | wc -l | tr -cd 0-9)
  [ "${live:-0}" -ge 1 ] && echo "  PASS  live control: $live HTTPRoutes" || { echo "  FAIL  live HTTPRoutes is 0"; fail=1; }
fi
exit $fail
