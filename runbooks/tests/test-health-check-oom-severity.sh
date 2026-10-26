#!/usr/bin/env bash
# F-e8348288 (2026-10-26): an OOMKilled lastState survives for the pod's whole
# life, so the health check kept Section 1 CRITICAL for 31+ hours after a
# single OOM on a pod that was stable (482Mi of a 1Gi limit). oom_severity_class
# now rates: fresh (event within ~1h, or lastState finished within 24h) =
# critical; only an OLDER lastState = minor (reported, never dropped); and an
# unreadable 24h window fails CLOSED to critical. This test runs the SHIPPED
# function (extracted from health-check.sh), and checks the caller wires the
# 24h control into it and records an unreadable window as UNMEASURED.
# BSD-safe. Bash script; callers may be zsh.
set -u
HC="$(cd "$(dirname "$0")/.." && pwd)/health-check.sh"
fail=0
check() { if [ "$2" = "$3" ]; then echo "  PASS  $1"; else echo "  FAIL  $1 got [$2] want [$3]"; fail=1; fi; }

fn=$(awk '/^oom_severity_class\(\) \{/{p=1} p{print} p&&/^}/{exit}' "$HC")
[ -n "$fn" ] || { echo "  FAIL  oom_severity_class not found in health-check.sh"; exit 1; }
eval "$fn"

#                         events lastState last24h unmeasured
check "clean cluster"                  "$(oom_severity_class 0 0 0 0)" "clean"
check "fresh event"                    "$(oom_severity_class 2 0 0 0)" "critical"
check "lastState within 24h"           "$(oom_severity_class 0 1 1 0)" "critical"
check "OLD lastState only (trmnl-ha)"  "$(oom_severity_class 0 1 0 0)" "minor"
check "several old lastStates"         "$(oom_severity_class 0 4 0 0)" "minor"
check "old lastState, 24h unreadable"  "$(oom_severity_class 0 1 0 1)" "critical"
check "nothing seen, 24h unreadable"   "$(oom_severity_class 0 0 0 1)" "clean"
check "event beats old lastState"      "$(oom_severity_class 1 1 0 0)" "critical"

# Caller wiring: the severity must come from the function (a revert to the
# unbounded `$OOM_LASTSTATE -gt 0` critical would pass the function tests).
check "caller uses oom_severity_class" \
    "$(grep -c 'oom_severity_class "\$OOM_COUNT" "\$OOM_LASTSTATE" "\$OOM_LASTSTATE_24H" "\$OOM_24H_UNMEASURED"' "$HC")" "1"
check "no unbounded lastState critical left" \
    "$(grep -c 'if \[ "\$OOM_COUNT" -gt 0 \] || \[ "\$OOM_LASTSTATE" -gt 0 \]' "$HC")" "0"
check "unreadable 24h window is recorded UNMEASURED" \
    "$(grep -c '_record_unmeasured "oom-laststate-24h"' "$HC")" "1"
check "24h control no longer swallows errors as 0" \
    "$(grep -c "n = 'ERR'" "$HC")" "1"

[ "$fail" -eq 0 ] && echo "ALL PASS" || { echo "FAILURES"; exit 1; }
