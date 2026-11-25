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
# shard-<suite>-<i>.json here: the layout the trigger collects. A combined
# suite (release-all) writes one subfolder per part ($OUT/release/, $OUT/responsive/).
# E2E_RUNNER=k8s selects the game's k8s speed factors when it plans the shards.
export E2E_OUT="$OUT" E2E_RUNNER=k8s
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
if [ "$rc" -eq 0 ] && [ "$SUITE" != unit ] && [ "$SUITE" != sims ] && [ "$SUITE" != clipgate ] && [ -d node_modules/playwright ]; then
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

# Review pictures (PICS_ENV, from the trigger): every name is an env variable the
# game's specs read as their picture folder (POC3D_HEROES_SHOTS, REVIEW_DIR, ...);
# each points at its own folder here, collected into $OUT/pics after the run.
pics_src=/work/pics-src
read -r -a pics_env <<<"${PICS_ENV:-}"
for v in "${pics_env[@]}"; do
    if [[ "$v" =~ ^[A-Z][A-Z0-9_]*(_DIR|_SHOTS)$ ]]; then
        mkdir -p "$pics_src/$v"; export "$v=$pics_src/$v"
    else
        log "PICS_ENV: '$v' is not a picture-folder variable (*_DIR, *_SHOTS); ignored"
    fi
done

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
                export PW_GPU_EXPECTED=1 E2E_RUNNER=k8s
                if has_script test:release-all:shard; then
                    # release + the responsive matrix planned as one pool over every shard
                    # (outputs in $OUT/release/ and $OUT/responsive/)
                    npm run test:release-all:shard -- "$SHARD" "$N" "${extra[@]}" --retries=1; rc=$?
                else
                    # refs before release-all: release split, responsive whole on shard 1
                    npm run test:release:shard -- "$SHARD" "$N" "${extra[@]}" --retries=1; rc=$?
                    if [ "$SHARD" = 1 ]; then
                        E2E_OUT="$OUT/responsive" npm run test:responsive:shard -- 1 1 --no-build --workers="${WORKERS}" --retries=1 || rc=1
                    fi
                fi
            fi
            ;;
        sims)
            # the game's planner (tools/sims-shard.ts, decision 410): one shard of N
            mkdir -p reports
            if has_script sims:shard; then
                npm run sims:shard -- "$SHARD" "$N"; rc=$?
            else
                log "this ref predates the sims planner (sims:shard script); not supported by the runner"; rc=2
            fi
            ;;
        clipgate)
            # the PoC 3D clipping gate, one share of the figures (CLIP_ARGS)
            OUT="$OUT" SHARD="$SHARD" N="$N" bash /opt/ci/clipgate.sh; rc=$?
            ;;
        *)
            log "unknown SUITE '${SUITE}' (unit|e2e|nightly|responsive|release|sims|clipgate)"; rc=2
            ;;
    esac
fi
dur=$(( $(date +%s) - t1 ))

# NO-TESTS GUARD: a browser suite that executed nothing is a FAIL, never a
# green. Playwright exits 0 when a --test-list matches no test (2026-10-03: a
# describe title containing " › " made the game's shard list match nothing,
# 22 planned, 0 run, PASS). Planned = the game's shard-*.json "tests";
# executed = <testcase> entries in the junit.xml files.
count_info=""
case "$SUITE" in e2e|nightly|responsive|release)
    read -r plans planned executed <<<"$(node -e '
const fs = require("fs"), path = require("path");
let plans = 0, planned = 0, executed = 0;
const walk = (d) => { for (const n of fs.readdirSync(d, { withFileTypes: true })) {
  const f = path.join(d, n.name);
  if (n.isDirectory()) { if (n.name !== "test-results" && n.name !== "blob-report") walk(f); }
  else if (n.name === "junit.xml") executed += (fs.readFileSync(f, "utf8").match(/<testcase\b/g) || []).length;
  else if (/^shard-.*\.json$/.test(n.name)) { plans++; planned += Number(JSON.parse(fs.readFileSync(f, "utf8")).tests) || 0; }
} };
walk(process.argv[1]); console.log(plans, planned, executed);' "$OUT" 2>/dev/null || echo "? ? ?")"
    count_info=" planned=${planned} executed=${executed}"
    if [ "$rc" -eq 0 ]; then
        if ! [[ "$executed" =~ ^[0-9]+$ ]]; then
            log "NO-TESTS: cannot count the executed tests (junit.xml unreadable)"; rc=3
        elif [ "$plans" = 0 ]; then
            log "NO-TESTS: the game's shard tool wrote no plan (shard-*.json); nothing provably ran"; rc=3
        elif [ "$executed" -eq 0 ] && { [ "$planned" -gt 0 ] || [ "$N" -eq 1 ]; }; then
            log "NO-TESTS: ${planned} tests planned, 0 executed (SPECS='${SPECS:-}' PROJECT='${PROJECT:-}'); a run that tests nothing fails"; rc=3
        elif [ "$executed" -eq 0 ]; then
            log "note: this shard got no tests from the plan (more shards than tests); the trigger fails the run if ALL shards are empty"
        elif [ "$executed" -lt "$planned" ]; then
            log "TEST-COUNT-MISMATCH: ${planned} planned, only ${executed} executed; some tests were silently dropped (see docs/sops/ci-runner.md)"
        fi
    fi
    ;;
esac
[ -d reports ] && cp -r reports "$OUT/" 2>/dev/null

# Picture collection (PICS=1 or PICS_ENV set): the images of the spec's own
# picture folders and of Playwright's test-results, copied into $OUT/pics/ in
# name order until this shard's share of the job's cap (PICS_CAP_MB / shards)
# is used; the rest is counted, not copied. The collector moves them to
# <results>/<job>/pics/shard-N/.
if [ "${PICS:-0}" = 1 ] || [ "${#pics_env[@]}" -gt 0 ]; then
    cap=$(( ${PICS_CAP_MB:-200} * 1024 * 1024 / N ))
    node -e '
const fs = require("fs"), path = require("path");
const [out, cap, ...srcs] = process.argv.slice(1);
const img = /\.(png|jpe?g|webp)$/i, list = [];
const walk = (root, d) => { if (!fs.existsSync(d)) return; for (const n of fs.readdirSync(d, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
  const f = path.join(d, n.name); if (n.isDirectory()) walk(root, f); else if (img.test(n.name)) list.push([root, f]); } };
for (const s of srcs) { const [name, dir] = s.split("="); walk(name, dir); }
let used = 0, copied = 0, skipped = 0, skippedBytes = 0; const index = [];
for (const [name, f] of list) {
  const size = fs.statSync(f).size, root = srcs.find((s) => s.startsWith(name + "=")).slice(name.length + 1);
  const rel = path.join(name, path.relative(root, f));
  if (used + size > +cap) { skipped++; skippedBytes += size; index.push(`skipped ${size} ${rel}`); continue; }
  fs.mkdirSync(path.dirname(path.join(out, rel)), { recursive: true }); fs.copyFileSync(f, path.join(out, rel));
  used += size; copied++; index.push(`copied ${size} ${rel}`);
}
fs.mkdirSync(out, { recursive: true }); fs.writeFileSync(path.join(out, "INDEX.txt"), index.join("\n") + "\n");
console.log(`${copied} copied (${(used / 1048576).toFixed(1)} MiB), ${skipped} over the cap of ${(cap / 1048576).toFixed(1)} MiB not copied (${(skippedBytes / 1048576).toFixed(1)} MiB)`);
' "$OUT/pics" "$cap" "test-results=$OUT/test-results" $(for v in "${pics_env[@]}"; do [ -d "$pics_src/$v" ] && echo "$v=$pics_src/$v"; done) 2>&1 | sed 's/^/[pics] /'
fi
git rev-parse HEAD >"$OUT/commit"
echo "$rc" >"$OUT/exit-code"

# Size of what the trigger will copy (results emptyDir cap: 6Gi, see job-template.yaml.tpl)
log "results size: $(du -sh "$OUT" 2>/dev/null | cut -f1) in $OUT; 10 largest entries:"
du -ah "$OUT" 2>/dev/null | sort -h | tail -10 | sed 's/^/  du: /'

if [ "$rc" -eq 0 ]; then verdict=PASS; else verdict=FAIL; fi
echo "CI-RESULT suite=${SUITE} shard=${SHARD}/${N} result=${verdict} rc=${rc}${count_info} test_seconds=${dur} total_seconds=$(( $(date +%s) - t0 ))"
echo "CI-RESULTS-READY"
# Hold for the collector (bounded). The trigger script copies /results and then
# touches /results/.collected; COLLECT_WAIT_SECONDS=0 skips the wait.
waited=0
while [ "$waited" -lt "${COLLECT_WAIT_SECONDS:-900}" ] && [ ! -f /results/.collected ]; do
    sleep 5; waited=$((waited + 5))
done
exit "$rc"
