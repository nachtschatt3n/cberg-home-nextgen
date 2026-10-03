#!/bin/bash
# Main container: install, run ONE shard of a suite, stage results in /results,
# then hold the pod (bounded) so the trigger script can `kubectl cp` them out.
# The git credential is NOT mounted here: npm install scripts and test code
# never see it.
set -uo pipefail
IDX=${JOB_COMPLETION_INDEX:-0}
N=${SHARD_TOTAL:-1}
SHARD=$((IDX + 1))
OUT=/results/shard-${SHARD}
mkdir -p "$OUT"
export CI=1 HOME=/work/home npm_config_cache=/work/npm-cache npm_config_update_notifier=false
log() { echo "[ci $(date -u +%H:%M:%S) ${SUITE} ${SHARD}/${N}] $*"; }

cd /work/src
log "commit $(git rev-parse HEAD) on node ${NODE_NAME:-?}, workers ${WORKERS}"
t0=$(date +%s)
rc=0
if ! npm ci --no-audit --no-fund --loglevel=error >"$OUT/npm-ci.log" 2>&1; then
    tail -n 60 "$OUT/npm-ci.log"
    rc=97
fi
log "npm ci done in $(( $(date +%s) - t0 ))s (rc=$rc)"

# GPU mode: every Chromium launch (incl. specs that set their own launchOptions
# via test.use) gets CHROMIUM_EXTRA_ARGS through a wrapper around the browser
# binaries: PLAYWRIGHT_BROWSERS_PATH points at a shadow tree whose chrome /
# chrome-headless-shell are scripts exec'ing the real binary + the flags.
if [ -n "${CHROMIUM_EXTRA_ARGS:-}" ]; then
    shadow=/work/pw-browsers
    mkdir -p "$shadow"
    for d in /ms-playwright/*; do
        name=$(basename "$d")
        case "$name" in
            chromium-*|chromium_headless_shell-*)
                mkdir -p "$shadow/$name"
                for e in "$d"/*; do
                    if [ -d "$e" ]; then
                        mkdir -p "$shadow/$name/$(basename "$e")"
                        for f in "$e"/*; do
                            bn=$(basename "$f")
                            if [ "$bn" = chrome ] || [ "$bn" = chrome-headless-shell ]; then
                                printf '#!/bin/sh\nexec %s "$@" %s\n' "$f" "$CHROMIUM_EXTRA_ARGS" >"$shadow/$name/$(basename "$e")/$bn"
                                chmod 755 "$shadow/$name/$(basename "$e")/$bn"
                            else
                                ln -s "$f" "$shadow/$name/$(basename "$e")/$bn"
                            fi
                        done
                    else
                        ln -s "$e" "$shadow/$name/"
                    fi
                done ;;
            *) ln -s "$d" "$shadow/$name" ;;
        esac
    done
    export PLAYWRIGHT_BROWSERS_PATH="$shadow"
fi
if [ "$rc" -eq 0 ] && [ -d node_modules/playwright ]; then
    renderer=$(timeout 60 node -e '
const { chromium } = require("playwright");
(async () => { const b = await chromium.launch(); const p = await b.newPage();
  const r = await p.evaluate(() => { const g = document.createElement("canvas").getContext("webgl2");
    const i = g && g.getExtension("WEBGL_debug_renderer_info");
    return g ? (i ? g.getParameter(i.UNMASKED_RENDERER_WEBGL) : g.getParameter(g.RENDERER)) : "no webgl2"; });
  console.log(r); await b.close(); })().catch((e) => console.log("probe failed: " + e.message.split("\n")[0]));' 2>&1 | tail -1)
    log "WebGL renderer: ${renderer}"
    if [ -n "${CHROMIUM_EXTRA_ARGS:-}" ] && ! grep -qi "intel" <<<"$renderer"; then
        log "GPU-FALLBACK: GPU mode requested but Chromium is not on the Intel GPU"
    fi
fi

pw_args=(--shard="${SHARD}/${N}" --workers="${WORKERS}" --reporter=list,junit,html,blob --output="$OUT/test-results")
[ -n "${PROJECT:-}" ] && pw_args+=(--project="$PROJECT")
read -r -a spec_filter <<<"${SPECS:-}"
export PLAYWRIGHT_JUNIT_OUTPUT_FILE="$OUT/junit.xml" \
       PLAYWRIGHT_HTML_OUTPUT_DIR="$OUT/playwright-report" \
       PLAYWRIGHT_HTML_OPEN=never \
       PLAYWRIGHT_BLOB_OUTPUT_DIR="$OUT/blob-report" \
       PLAYWRIGHT_BLOB_OUTPUT_NAME="report-${SHARD}.zip"

t1=$(date +%s)
if [ "$rc" -eq 0 ]; then
    case "$SUITE" in
        unit)
            # typecheck, lint, validate:data, vitest, build, security (= CI "Check & test")
            npm run check; rc=$?
            ;;
        e2e)
            # = the game's per-push CI (.github/workflows/ci.yml "End-to-end tests")
            npm run build && npx playwright test --grep-invert "@art|@nightly" "${pw_args[@]}" "${spec_filter[@]}"; rc=$?
            ;;
        nightly)
            # = the game's nightly e2e job: the slow/perf-sensitive specs
            npm run build && npx playwright test --grep "@nightly|@perf" "${pw_args[@]}" "${spec_filter[@]}"; rc=$?
            ;;
        responsive)
            if [ ! -f playwright.responsive.config.ts ]; then
                log "playwright.responsive.config.ts not present at this commit"; rc=2
            else
                npm run build && npx playwright test -c playwright.responsive.config.ts "${pw_args[@]}" "${spec_filter[@]}"; rc=$?
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
            log "unknown SUITE '${SUITE}' (unit|e2e|nightly|responsive|sims)"; rc=2
            ;;
    esac
fi
dur=$(( $(date +%s) - t1 ))
[ -d reports ] && cp -r reports "$OUT/" 2>/dev/null
[ -f junit.xml ] && cp junit.xml "$OUT/" 2>/dev/null
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
