#!/bin/bash
# Main container: install, run ONE shard of a suite, stage results in /results,
# then hold the pod (bounded) so the trigger script can `kubectl cp` them out.
# The git credential is NOT mounted here: npm install scripts and test code
# never see it.
#
# Suite selection, sharding (duration-balanced), reporters and the GPU check
# are the GAME's (tools/e2e-shard.ts, npm test:*:shard scripts); this runner
# only picks suite / shard / workers and sets E2E_OUT. Contract:
# the-ninth-banner docs/testing/test-execution-strategy.md "Hand-off to cberg-agent".
set -uo pipefail
IDX=${JOB_COMPLETION_INDEX:-0}
N=${SHARD_TOTAL:-1}
SHARD=$((IDX + 1))
OUT=/results/shard-${SHARD}
mkdir -p "$OUT"
export CI=1 HOME=/work/home npm_config_cache=/work/npm-cache npm_config_update_notifier=false
# the game's shard scripts write blob-report/, junit.xml, test-results/ and
# shard-<suite>-<i>.json here: the layout the trigger collects
export E2E_OUT="$OUT"
log() { echo "[ci $(date -u +%H:%M:%S) ${SUITE} ${SHARD}/${N}] $*"; }

cd /work/src
log "commit $(git rev-parse HEAD) on node ${NODE_NAME:-?}, workers ${WORKERS}, gpu flags: ${CHROMIUM_EXTRA_ARGS:-none}"
t0=$(date +%s)
rc=0
if ! npm ci --no-audit --no-fund --loglevel=error >"$OUT/npm-ci.log" 2>&1; then
    tail -n 60 "$OUT/npm-ci.log"
    rc=97
fi
log "npm ci done in $(( $(date +%s) - t0 ))s (rc=$rc)"

has_script() { node -e 'process.exit(require("./package.json").scripts?.[process.argv[1]] ? 0 : 1)' "$1"; }
gpu=0; [ -n "${CHROMIUM_EXTRA_ARGS:-}" ] && gpu=1
if [ "$gpu" = 1 ]; then
    # the game reads PW_CHROMIUM_ARGS in playwright.config.ts AND in specs
    # with their own launchOptions (perf.spec), so no browser wrapper is needed
    export PW_CHROMIUM_ARGS="$CHROMIUM_EXTRA_ARGS"
fi

# proof of the renderer, logged for every browser suite
if [ "$rc" -eq 0 ] && [ "$SUITE" != unit ] && [ "$SUITE" != sims ] && [ -d node_modules/playwright ]; then
    renderer=$(timeout 60 node -e '
const { chromium } = require("playwright");
(async () => { const b = await chromium.launch({ args: (process.env.PW_CHROMIUM_ARGS || "").split(/\s+/).filter(Boolean) });
  const p = await b.newPage();
  const r = await p.evaluate(() => { const g = document.createElement("canvas").getContext("webgl2");
    const i = g && g.getExtension("WEBGL_debug_renderer_info");
    return g ? (i ? g.getParameter(i.UNMASKED_RENDERER_WEBGL) : g.getParameter(g.RENDERER)) : "no webgl2"; });
  console.log(r); await b.close(); })().catch((e) => console.log("probe failed: " + e.message.split("\n")[0]));' 2>&1 | tail -1)
    log "WebGL renderer: ${renderer}"
    if [ "$gpu" = 1 ] && ! grep -qi "intel" <<<"$renderer"; then
        log "GPU-FALLBACK: GPU mode requested but Chromium is not on the Intel GPU"
    fi
fi

# extra Playwright args passed through the game's shard script
extra=(--workers="${WORKERS}")
[ -n "${PROJECT:-}" ] && extra+=(--project="$PROJECT")
read -r -a spec_filter <<<"${SPECS:-}"
extra+=("${spec_filter[@]}")
need_split() {   # the browser suites need the game's shard tooling (77764e6+)
    if ! has_script test:e2e:shard; then
        log "this ref predates tools/e2e-shard.ts (test:*:shard scripts); not supported by the runner"; rc=2; return 1
    fi
}
need_gpu() {     # rendering suites fail their timing assertions on 4 software CPUs
    if [ "$gpu" != 1 ]; then
        log "suite '${SUITE}' runs on GPU only (CPU/SwiftShader fails its timing budgets, docs/sops/ci-runner.md)"; rc=2; return 1
    fi
}

t1=$(date +%s)
if [ "$rc" -eq 0 ]; then
    case "$SUITE" in
        unit)
            # GitHub "Check & test" minus the Docker build (the image has the browsers)
            npm run check && npx tsx tools/story-check.ts && \
                { if has_script test:ci; then npm run test:ci -- --no-build; fi; }
            rc=$?
            ;;
        e2e)
            need_gpu && need_split && { npm run test:e2e:shard -- "$SHARD" "$N" "${extra[@]}"; rc=$?; }
            ;;
        nightly)
            need_split && { npm run test:nightly:shard -- "$SHARD" "$N" "${extra[@]}"; rc=$?; }
            ;;
        responsive)
            need_gpu && need_split && { npm run test:responsive:shard -- "$SHARD" "$N" "${extra[@]}"; rc=$?; }
            ;;
        release)
            # THE release suite on hardware WebGL: no CI relaxations, and the
            # game's gpu-check fails the shard in seconds on a software renderer
            if need_gpu && need_split; then
                unset CI
                export PW_GPU_EXPECTED=1
                npm run test:release:shard -- "$SHARD" "$N" "${extra[@]}" --retries=1; rc=$?
                if [ "$SHARD" = 1 ]; then
                    # shard 1 also runs the responsive matrix (one shard, already built)
                    E2E_OUT="$OUT/responsive" npm run test:responsive:shard -- 1 1 --no-build --workers="${WORKERS}" --retries=1 || rc=1
                fi
            fi
            ;;
        sims)
            # the CI nightly sweeps, distributed round-robin over the shards
            cmds=("npx tsx tools/sim.ts --n 30 --check"
                  "npx tsx tools/gen-sweep.ts --n 2000"
                  "npx tsx tools/autoplay.ts --n 10 --check"
                  "npx tsx tools/ending-hunt.ts --n 4")
            mkdir -p reports
            for i in "${!cmds[@]}"; do
                [ $(( i % N )) -eq "$IDX" ] || continue
                log "run: ${cmds[$i]}"
                bash -c "${cmds[$i]}" || rc=1
            done
            ;;
        *)
            log "unknown SUITE '${SUITE}' (unit|e2e|nightly|responsive|release|sims)"; rc=2
            ;;
    esac
fi
dur=$(( $(date +%s) - t1 ))
[ -d reports ] && cp -r reports "$OUT/" 2>/dev/null
git rev-parse HEAD >"$OUT/commit"
echo "$rc" >"$OUT/exit-code"

if [ "$rc" -eq 0 ]; then verdict=PASS; else verdict=FAIL; fi
echo "CI-RESULT suite=${SUITE} shard=${SHARD}/${N} result=${verdict} rc=${rc} test_seconds=${dur} total_seconds=$(( $(date +%s) - t0 ))"
echo "CI-RESULTS-READY"
# Hold for the collector (bounded). The trigger script copies /results and then
# touches /results/.collected; COLLECT_WAIT_SECONDS=0 skips the wait.
waited=0
while [ "$waited" -lt "${COLLECT_WAIT_SECONDS:-900}" ] && [ ! -f /results/.collected ]; do
    sleep 5; waited=$((waited + 5))
done
exit "$rc"
