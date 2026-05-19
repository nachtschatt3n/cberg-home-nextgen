#!/usr/bin/env bash
# sweep-run — entrypoint for the in-cluster sweep-collector container.
#
# Runs one or more audit scripts with a shared SWEEP_CYCLE_ID so all
# their findings land in the same sweep_cycles row.
#
# Usage (inside the container; not for direct operator use):
#   sweep-run all          run every supported audit script in order
#   sweep-run doc          run only doc-check
#   sweep-run version      run only check-all-versions
#   sweep-run security     run only security-check
#   sweep-run health       run only health-check (wraps health-check.sh)
#
# Required env:
#   SWEEP_PG_DSN          DSN for the sweep_writer role
# Optional env:
#   SWEEP_CYCLE_ID        UUID shared across scripts in this run.
#                         Auto-generated if unset.
#   SWEEP_TRIGGER         cron|manual  (default: cron — set by the CronJob)
#   GITHUB_TOKEN          for check-all-versions Renovate / release-notes
set -euo pipefail

cd /opt/sweep

if [ -z "${SWEEP_CYCLE_ID:-}" ]; then
    export SWEEP_CYCLE_ID=$(python3 -c 'import uuid; print(uuid.uuid4())')
fi
export SWEEP_TRIGGER="${SWEEP_TRIGGER:-cron}"

echo "==> sweep-collector starting"
echo "    cycle_id : ${SWEEP_CYCLE_ID}"
echo "    trigger  : ${SWEEP_TRIGGER}"
echo "    pg_dsn   : ${SWEEP_PG_DSN:+(set)}${SWEEP_PG_DSN:-(MISSING)}"
echo ""

run_doc()      { echo "==> doc-check.py";          python3 runbooks/doc-check.py; }
run_version()  { echo "==> check-all-versions.py"; python3 runbooks/check-all-versions.py; }
run_security() { echo "==> security-check.py";     python3 runbooks/security-check.py; }
run_health()   { echo "==> health-check.py";       python3 runbooks/health-check.py; }

# Each step's exit code is captured so one specialist's failure doesn't abort
# the whole sweep. We exit non-zero at the end if anything failed.
fail=0
case "${1:-all}" in
    doc)      run_doc      || fail=1 ;;
    version)  run_version  || fail=1 ;;
    security) run_security || fail=1 ;;
    health)   run_health   || fail=1 ;;
    all)
        # Fast and cheap first (so DB has *something* even if heavy ones hang).
        run_doc       || fail=1
        run_version   || fail=1
        run_security  || fail=1
        run_health    || fail=1
        ;;
    *)
        echo "unknown step: $1" >&2
        echo "valid: all | doc | version | security | health" >&2
        exit 2
        ;;
esac

echo ""
echo "==> sweep-collector done (cycle_id=${SWEEP_CYCLE_ID} fail=${fail})"
exit "${fail}"
