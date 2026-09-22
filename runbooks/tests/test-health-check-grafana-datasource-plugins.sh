#!/usr/bin/env bash
# Regression tests for the Grafana datasource-plugin probe in
# runbooks/health-check.sh (F-f3bd72df item 1).
#
# On 2026-09-12 a Grafana restart let the plugin background installer kill
# the bundled postgres/influxdb/loki/jaeger/mssql backends on the read-only
# rootfs: 15/72 dashboards read "no data" while the pod was Ready and Section
# 30 counted "Grafana: 1 Running pod". The probe now asserts what the
# dashboards actually depend on: /api/plugins?type=datasource == 18 and every
# provisioned datasource /health == 200 (alertmanager skipped: its /health is
# plugin.unavailable by design). A probe that cannot run is unmeasured.
#
# Hermetic: grafana_score_datasources is driven with fixture TSV in the exact
# shape grafana_probe_collect emits (uids are the real provisioned ones; no
# credential is involved in scoring).
# Run directly:  bash runbooks/tests/test-health-check-grafana-datasource-plugins.sh
set -uo pipefail
HC="$(cd "$(dirname "$0")/.." && pwd)/health-check.sh"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT

python3 - "$HC" "$TMP/funcs.sh" <<'PY'
import sys, re
src, out = sys.argv[1], sys.argv[2]
s = open(src).read()
def grab(name):
    i = s.index(f"{name}() {{")
    j = s.index("\n}\n", i) + 3
    return s[i:j]
m = re.search(r'^GRAFANA_DS_PLUGINS_EXPECTED=.*$', s, re.M)
open(out, "w").write((m.group(0) if m else "") + "\n\n" + grab("grafana_score_datasources"))
PY

WARN=(); INFO=(); OK=(); MINOR=(); MAJOR=(); CRIT=(); UNMEASURED=()
log_warning() { WARN+=("$1"); }
log_info()    { INFO+=("$1"); }
log_success() { OK+=("$1"); }
add_minor_issue() { MINOR+=("$1"); }
add_major_issue() { MAJOR+=("$1"); }
add_critical_issue() { CRIT+=("$1"); }
_record_unmeasured() { UNMEASURED+=("$1: $2"); }
source "$TMP/funcs.sh"
reset() { WARN=(); INFO=(); OK=(); MINOR=(); MAJOR=(); CRIT=(); UNMEASURED=(); }

PASS=0; FAIL=0
check() { if [ "$2" -eq 0 ]; then echo "  PASS  $1"; PASS=$((PASS+1)); else echo "  FAIL  $1"; [ -n "${3:-}" ] && printf '        %s\n' "$3"; FAIL=$((FAIL+1)); fi; }
joined() { printf '%s\n' "$@"; }

HEALTHY=$'PLUGINS\t18\nDS\talertmanager\talertmanager\t500\tPlugin unavailable\nDS\telasticsearch\telasticsearch\t200\tElasticsearch data source is healthy.\nDS\tinfluxdb\tinfluxdb\t200\tdatasource is working. 1 buckets found\nDS\tpellets\tgrafana-postgresql-datasource\t200\tDatabase Connection OK\nDS\tprometheus\tprometheus\t200\tSuccessfully queried the Prometheus API.\nDS\tTeslaMate\tgrafana-postgresql-datasource\t200\tDatabase Connection OK\nDS\tunpoller-influxdb\tinfluxdb\t200\tdatasource is working. 1 buckets found'
# The 2026-09-12 shape: bundled backends gone (13 of 18), postgres datasources dead.
DEGRADED=$'PLUGINS\t13\nDS\talertmanager\talertmanager\t500\tPlugin unavailable\nDS\telasticsearch\telasticsearch\t200\tok\nDS\tinfluxdb\tinfluxdb\t500\tPlugin unavailable\nDS\tpellets\tgrafana-postgresql-datasource\t500\tPlugin unavailable\nDS\tprometheus\tprometheus\t200\tok\nDS\tTeslaMate\tgrafana-postgresql-datasource\t500\tPlugin unavailable\nDS\tunpoller-influxdb\tinfluxdb\t500\tPlugin unavailable'

echo "grafana datasource-plugin probe"

check "expected plugin count is 18 (measured 2026-09-22 on 13.2.2)" $([ "${GRAFANA_DS_PLUGINS_EXPECTED:-}" = "18" ] && echo 0 || echo 1) "GRAFANA_DS_PLUGINS_EXPECTED='${GRAFANA_DS_PLUGINS_EXPECTED:-}'"

# 1. Healthy: no issue, one success, alertmanager skipped rather than scored.
reset; grafana_score_datasources "$HEALTHY" > "$TMP/out"; out=$(cat "$TMP/out")
check "healthy probe -> no issues" $([ ${#MAJOR[@]} -eq 0 ] && [ ${#MINOR[@]} -eq 0 ] && [ ${#UNMEASURED[@]} -eq 0 ] && echo 0 || echo 1) "$(joined "${MAJOR[@]:-}" "${MINOR[@]:-}" "${UNMEASURED[@]:-}")"
check "healthy probe -> success line counts 6/6 non-alertmanager datasources" $(joined "${OK[@]:-}" | grep -q '6/6 200' && echo 0 || echo 1) "$(joined "${OK[@]:-none}")"
check "alertmanager 500 is printed as skipped, not scored" $(printf '%s' "$out" | grep -q 'alertmanager (alertmanager): HTTP 500 -- skipped' && echo 0 || echo 1) "$out"

# 2. Degraded: plugin loss AND datasource failures are each a MAJOR naming the victims.
reset; grafana_score_datasources "$DEGRADED" > "$TMP/out"; out=$(cat "$TMP/out")
check "13 of 18 plugins -> MAJOR naming the count" $(joined "${MAJOR[@]:-}" | grep -q 'Grafana datasource plugins: 13 of 18' && echo 0 || echo 1) "$(joined "${MAJOR[@]:-none}")"
check "unhealthy datasources -> MAJOR naming uid, type and HTTP code" $(joined "${MAJOR[@]:-}" | grep -q 'TeslaMate (grafana-postgresql-datasource) HTTP 500' && joined "${MAJOR[@]:-}" | grep -q 'unpoller-influxdb (influxdb) HTTP 500' && echo 0 || echo 1) "$(joined "${MAJOR[@]:-none}")"
check "exactly two MAJORs (plugins, datasources) and no success" $([ ${#MAJOR[@]} -eq 2 ] && [ ${#OK[@]} -eq 0 ] && echo 0 || echo 1) "$(joined "${MAJOR[@]:-none}")"
check "alertmanager is NOT among the unhealthy names" $(! joined "${MAJOR[@]:-}" | grep -q 'alertmanager (alertmanager)' && echo 0 || echo 1)

# 3. Probe could not run: unmeasured, never a quiet pass.
reset; grafana_score_datasources $'ERR\tgrafana port-forward on 3097 never answered /api/health' > /dev/null
check "ERR line -> unmeasured recorded, no issue, no success" $([ ${#UNMEASURED[@]} -eq 1 ] && [ ${#MAJOR[@]} -eq 0 ] && [ ${#OK[@]} -eq 0 ] && joined "${UNMEASURED[@]}" | grep -q 'grafana-datasource-plugins' && echo 0 || echo 1) "$(joined "${UNMEASURED[@]:-none}")"
reset; grafana_score_datasources "" > /dev/null
check "empty probe output -> unmeasured" $([ ${#UNMEASURED[@]} -ge 1 ] && [ ${#OK[@]} -eq 0 ] && echo 0 || echo 1)
reset; grafana_score_datasources $'PLUGINS\t18' > /dev/null
check "plugins listed but 0 datasources -> unmeasured (there ARE 7)" $(joined "${UNMEASURED[@]:-}" | grep -q 'grafana-datasource-health' && [ ${#OK[@]} -eq 0 ] && echo 0 || echo 1) "$(joined "${UNMEASURED[@]:-none}")"

# 4. More plugins than expected is drift to note, not a failure.
reset; grafana_score_datasources "$(printf '%s' "$HEALTHY" | sed 's/^PLUGINS\t18/PLUGINS\t19/')" > /dev/null
check "19 plugins -> info, no issue" $([ ${#MAJOR[@]} -eq 0 ] && joined "${INFO[@]:-}" | grep -q 'more than the expected' && echo 0 || echo 1) "$(joined "${INFO[@]:-none}")"

# 5. Script text: credentials never on argv, port-forward torn down, section before report_unmeasured.
check "admin password reaches curl via -K config file, not argv" $(grep -q 'curl -s -m 15 -K "\$cfg"' "$HC" && ! grep -q 'curl.*-u "\$user:\$pass"' "$HC" && echo 0 || echo 1)
check "Grafana section sits before report_unmeasured" $([ "$(grep -n '^log_section "Grafana Datasource Plugins"' "$HC" | cut -d: -f1)" -lt "$(grep -n '^report_unmeasured$' "$HC" | cut -d: -f1)" ] && echo 0 || echo 1)

# --- COMMISSIONING STRAW ------------------------------------------------------
# Pre-fix logic, transcribed from Section 30: Grafana health was "has at least
# one Running pod". On the 2026-09-12 shape (pod Ready, 13/18 plugins, four
# datasources dead) it must raise NOTHING -- proving case 2 would fail
# against the old code.
echo "commissioning straw (pre-fix pod-count logic must FAIL case 2)"
straw_section30() {
    local running_pods="$1"
    if [ "${running_pods:-0}" -eq 0 ] 2>/dev/null; then
        add_critical_issue "Grafana has no Running pods"
    fi
}
reset
straw_section30 1
check "STRAW: one Running pod satisfies the old check while 4 datasources are dead (test would fail -> witness is real)" \
    $([ ${#CRIT[@]} -eq 0 ] && [ ${#MAJOR[@]} -eq 0 ] && echo 0 || echo 1) "$(joined "${CRIT[@]:-none}")"

echo ""
echo "  $PASS passed, $FAIL failed"
[ $FAIL -eq 0 ]
