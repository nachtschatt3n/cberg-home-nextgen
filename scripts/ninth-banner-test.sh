#!/usr/bin/env bash
# Run The Ninth Banner's test suites as a sharded Kubernetes Job on the
# cluster (namespace ci-runner) and collect the results on this Mac.
#
#   scripts/ninth-banner-test.sh <ref> <unit|e2e|nightly|responsive|release|sims> [shards]
#
#   ref     commit sha (short ok), branch or tag of nachtschatt3n/the-ninth-banner
#   shards  default: e2e/nightly/responsive/release 3, sims 4, unit 1 (forced)
#
# release: when every shard has reported, posts the commit status
# "E2E (GPU, k8s)" on the game repo with gh (the pods hold no token).
#
# Env: RESULTS_DIR (default ~/ci-results), WORKERS (playwright workers per
# shard, default 2), COLLECT=0 (fire and forget: no wait, no artifact copy),
# GPU=1|0 (Chromium on the node's Intel iGPU via the device plugin; default 1
# for e2e/nightly/responsive, 0 for unit/sims), SPECS
# (space-separated spec files), PROJECT (e.g. chromium), CPU_REQ/CPU_LIM
# (per-shard CPU, default 2/4; never above 4, thermal cap).
# Exit status: 0 if every shard passed, 1 otherwise, 2 on usage errors.
# Full procedure, security model and troubleshooting: docs/sops/ci-runner.md
set -euo pipefail

# The whole body is a function that is called on the LAST line, so bash has
# parsed the complete file before anything runs. bash otherwise reads a script
# incrementally, and an edit to this file mid-run (shared worktree: other
# sessions edit it) corrupts the running instance.
main() {
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TEMPLATE="$REPO_ROOT/kubernetes/apps/ci-runner/the-ninth-banner-tests/job-template.yaml.tpl"
GH_REPO="nachtschatt3n/the-ninth-banner"
NS="ci-runner"

usage() { sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }
k() { (cd "$REPO_ROOT" && mise exec -- kubectl "$@"); }

[ $# -ge 2 ] || usage
ref_in="$1"; suite="$2"; shards="${3:-}"
case "$suite" in
    unit) shards=1 ;;
    e2e|nightly|responsive|release) shards="${shards:-3}" ;;
    sims) shards="${shards:-4}" ;;
    *) echo "unknown suite '$suite'"; usage ;;
esac
[[ "$shards" =~ ^[1-9][0-9]?$ ]] || { echo "shards must be 1..99"; exit 2; }
# THERMAL: at most 2 shards run at once (3 at 4-6 CPU drove the NUC14s to
# 100-102 C); extra shards queue. Best-effort CI, GitHub CI is the gate.
parallelism=$(( shards < 2 ? shards : 2 ))   # CPU/SwiftShader mode
workers="${WORKERS:-2}"   # 4 per 6-CPU shard starved Chromium (timing tests failed); see SOP
# Browser suites default to the iGPU (10x faster, ~10-20 C cooler, measured
# 2026-10-03); GPU=0 forces the CPU/SwiftShader fallback.
case "$suite" in e2e|nightly|responsive|release) gpu="${GPU:-1}" ;; *) gpu="${GPU:-0}" ;; esac
case "$suite" in e2e|responsive|release)
    [ "$gpu" = 1 ] || { echo "suite '$suite' is GPU-only: on 4 software-rendering CPUs it fails its timing budgets (docs/sops/ci-runner.md)"; exit 2; } ;;
esac
cpu_req="${CPU_REQ:-2}"; cpu_lim="${CPU_LIM:-4}"
[[ "$cpu_lim" =~ ^[1-4]$ ]] || { echo "CPU_LIM must be 1..4 (thermal cap)"; exit 2; }
# These values are pasted into sed and YAML: allow-list them.
[[ "$cpu_req" =~ ^[1-4]$ ]] || { echo "CPU_REQ must be 1..4"; exit 2; }
[[ "$gpu" =~ ^[01]$ ]] || { echo "GPU must be 0 or 1"; exit 2; }
[[ "$workers" =~ ^[1-8]$ ]] || { echo "WORKERS must be 1..8"; exit 2; }
[[ "${SPECS:-}" =~ ^[A-Za-z0-9._/@\ -]*$ ]] || { echo "SPECS: spec paths only"; exit 2; }
[[ "${PROJECT:-}" =~ ^[A-Za-z0-9_-]*$ ]] || { echo "PROJECT: a project name only"; exit 2; }
if [ "$gpu" = 1 ]; then
    gpu_res=', gpu.intel.com/i915: "1"'
    # verified 2026-10-03: ANGLE on GL/EGL renders on "Mesa Intel Arc Graphics
    # (MTL)"; the Vulkan path falls back to SwiftShader (no Vulkan ICD in the image)
    chromium_args="--use-gl=angle --use-angle=gl-egl --ignore-gpu-blocklist --enable-gpu-rasterization"
else
    gpu_res=""; chromium_args=""
fi
# GPU shards run cool (peak 66-89 C vs 100-102 C on SwiftShader): one per node,
# 3 in parallel (owner decision 2026-10-03). CPU mode stays capped at 2.
if [ "$gpu" = 1 ]; then parallelism=$(( shards < 3 ? shards : 3 )); fi
collect="${COLLECT:-1}"

sha="$(gh api "repos/$GH_REPO/commits/$ref_in" --jq .sha)" || { echo "cannot resolve ref '$ref_in'"; exit 2; }

# Image lockstep: the game pins the runner image (tests/e2e/runner.json, its
# tag = @playwright/test). Refuse a mismatch; older refs have no runner.json.
tpl_image="$(sed -n 's|^ *image: &image ||p' "$TEMPLATE")"
want_image="$(gh api "repos/$GH_REPO/contents/tests/e2e/runner.json?ref=$sha" --jq .content 2>/dev/null | base64 -d 2>/dev/null \
    | python3 -c 'import sys,json; print(json.load(sys.stdin)["playwrightImage"])' 2>/dev/null || true)"
if [ -z "$want_image" ]; then
    echo "note: no tests/e2e/runner.json at ${sha:0:12}; image lockstep not checked"
elif [ "$want_image" != "$tpl_image" ]; then
    echo "IMAGE MISMATCH: the game at ${sha:0:12} wants $want_image"
    echo "                the runner template has  $tpl_image"
    echo "bump job-template.yaml.tpl first (docs/sops/ci-runner.md §4 step 5)"; exit 2
fi
job="tnb-${suite}$([ "$gpu" = 1 ] && echo -gpu)-${sha:0:7}-$(date +%m%d%H%M%S)"
dest="${RESULTS_DIR:-$HOME/ci-results}/$job"
mkdir -p "$dest"

sed -e "s|__JOB_NAME__|$job|g" -e "s|__REF__|$sha|g" -e "s|__SUITE__|$suite|g" \
    -e "s|__SHARDS__|$shards|g" -e "s|__PARALLELISM__|$parallelism|g" \
    -e "s|__WORKERS__|$workers|g" -e "s|__COLLECT_WAIT__|$([ "$collect" = 1 ] && echo 900 || echo 0)|g" \
    -e "s|__CPU_REQ__|$cpu_req|g" -e "s|__CPU_LIM__|$cpu_lim|g" -e "s|__GPU_RES__|$gpu_res|g" \
    -e "s|__CHROMIUM_ARGS__|$chromium_args|g" -e "s|__SPECS__|${SPECS:-}|g" -e "s|__PROJECT__|${PROJECT:-}|g" \
    "$TEMPLATE" > "$dest/job.yaml"
k create -f "$dest/job.yaml" >/dev/null
start=$(date +%s)
echo "job $NS/$job  commit ${sha:0:12}  suite $suite  shards $shards (parallel $parallelism)  gpu=$gpu cpu=$cpu_req/$cpu_lim"
# THERMAL GATE: shard pods are created gated; every running trigger admits the
# oldest gated CI pods (any run) onto cool nodes with a free CI slot, one tick
# per poll. docs/sops/ci-runner.md "Thermal gate".
admit() { python3 "$REPO_ROOT/scripts/ninth-banner-admit.py" || true; }
if [ "$collect" != 1 ]; then
    # Fire and forget still has to stay until every shard is ADMITTED: a gated
    # pod with no running trigger waits until another run's trigger admits it.
    echo "COLLECT=0: waiting only until all $shards shard(s) are admitted by the thermal gate"
    while :; do
        admit
        ungated="$(k get pods -n "$NS" -l "batch.kubernetes.io/job-name=$job" \
            -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.spec.schedulingGates}{"\n"}{end}' 2>/dev/null \
            | grep -vc 'ci.cberg.home/thermal' || true)"
        [ "${ungated:-0}" -ge "$shards" ] && break
        sleep 10
    done
    echo "all shards admitted. Logs: kubectl logs -n $NS -l batch.kubernetes.io/job-name=$job -c runner --prefix"
    exit 0
fi

pod_of() { k get pods -n "$NS" -l "batch.kubernetes.io/job-name=$job,batch.kubernetes.io/job-completion-index=$1" \
               -o jsonpath='{.items[-1:].metadata.name}' 2>/dev/null || true; }
done_idx=()   # indexed array: bash 3.2 (macOS) has no associative arrays
summary=()
fails=0
while [ "${#done_idx[@]}" -lt "$shards" ]; do
    admit
    for ((i = 0; i < shards; i++)); do
        [ -n "${done_idx[$i]:-}" ] && continue
        pod="$(pod_of "$i")"; [ -n "$pod" ] || continue
        phase="$(k get pod -n "$NS" "$pod" -o jsonpath='{.status.phase}' 2>/dev/null || echo Unknown)"
        logs="$(k logs -n "$NS" "$pod" -c runner 2>/dev/null || true)"
        if grep -q '^CI-RESULTS-READY' <<<"$logs"; then
            printf '%s\n' "$logs" > "$dest/shard-$((i + 1)).log"
            k cp -c runner "$NS/$pod:/results" "$dest" >/dev/null 2>&1 || echo "  (copy of shard $((i + 1)) artifacts failed)"
            k exec -n "$NS" "$pod" -c runner -- touch /results/.collected >/dev/null 2>&1 || true
            line="$(grep '^CI-RESULT ' <<<"$logs" | tail -1)"
        elif [ "$phase" = Failed ] || [ "$phase" = Succeeded ]; then
            # died before staging results (clone/init failure, OOM, deadline)
            { k logs -n "$NS" "$pod" -c clone 2>&1; printf '%s\n' "$logs"; } > "$dest/shard-$((i + 1)).log"
            reason="$(k get pod -n "$NS" "$pod" -o jsonpath='{.status.initContainerStatuses[0].state.terminated.reason} {.status.containerStatuses[0].state.terminated.reason}' 2>/dev/null)"
            line="CI-RESULT suite=$suite shard=$((i + 1))/$shards result=FAIL rc=? (pod $phase before results: ${reason:-unknown}; see shard-$((i + 1)).log)"
        else
            continue
        fi
        done_idx[$i]=1
        summary+=("$line")
        grep -q 'result=PASS' <<<"$line" || fails=$((fails + 1))
        echo "  $line"
    done
    [ "${#done_idx[@]}" -lt "$shards" ] && sleep 10
done

elapsed=$(( $(date +%s) - start ))
printf '%s\n' "${summary[@]}" > "$dest/summary.txt"

# Counts from every shard's junit.xml (a test-list split never runs a test twice)
# and the plan from the game's shard-*.json. Line 1: "<executed> <planned>".
counts_out="$(python3 - "$dest" <<'PY' || printf '? ?\ncounting failed (unreadable junit.xml)'
import sys, glob, json, xml.etree.ElementTree as ET
t = f = s = 0
for p in glob.glob(sys.argv[1] + "/shard-*/**/junit.xml", recursive=True):
    if "/test-results/" in p or "/blob-report/" in p: continue
    r = ET.parse(p).getroot()
    for c in r.iter("testcase"):
        t += 1
        if c.find("failure") is not None or c.find("error") is not None: f += 1
        elif c.find("skipped") is not None: s += 1
planned = 0
for p in glob.glob(sys.argv[1] + "/shard-*/**/shard-*.json", recursive=True):
    if "/test-results/" in p or "/blob-report/" in p: continue
    try: planned += int(json.load(open(p)).get("tests", 0))
    except Exception: pass
print(t, planned)
print(f"{t - f - s} passed, {f} failed, {s} skipped")
PY
)"
read -r executed planned <<<"$(head -1 <<<"$counts_out")"
counts="$(sed -n 2p <<<"$counts_out")"
# NO-TESTS GUARD: a browser suite that executed nothing never passes (a
# --test-list that matches nothing makes Playwright exit 0; 2026-10-03).
no_tests=0
case "$suite" in e2e|nightly|responsive|release)
    if ! [[ "$executed" =~ ^[0-9]+$ ]] || [ "$executed" -eq 0 ]; then
        no_tests=1; fails=$((fails + 1))
    fi ;;
esac
echo "----"
if [ "$no_tests" = 1 ]; then
    echo "FAIL  $suite @ ${sha:0:12}: 0 tests executed (planned ${planned}; SPECS='${SPECS:-}' PROJECT='${PROJECT:-}'). A run that tests nothing is a failure: check the spec paths, or the shard logs for 'NO-TESTS'."
elif [ "$fails" -eq 0 ]; then
    echo "PASS  $suite @ ${sha:0:12}: $shards/$shards shards passed in ${elapsed}s"
else
    echo "FAIL  $suite @ ${sha:0:12}: $fails/$shards shards failed (${elapsed}s)"
fi
echo "tests: $counts (executed $executed of $planned planned)"
if [[ "$executed" =~ ^[0-9]+$ ]] && [[ "$planned" =~ ^[0-9]+$ ]] && [ "$executed" -lt "$planned" ]; then
    echo "WARNING: TEST-COUNT-MISMATCH: $((planned - executed)) planned tests never ran (dropped from the --test-list match; docs/sops/ci-runner.md)"
fi
echo "artifacts: $dest  (shard-N/: junit.xml, playwright-report/, test-results/ traces, blob-report/; release: per part in shard-N/{release,responsive}/)"
if ls "$dest"/shard-*/blob-report/*.zip "$dest"/shard-*/*/blob-report/*.zip >/dev/null 2>&1; then
    echo "merged report (from a checkout of the game at ${sha:0:12}): npm run test:merge-reports -- \"$dest\" --out \"$dest/report\""
fi


if [ "$suite" = release ]; then
    # Only for a complete run: every shard reported above, or we never got here.
    if [ "$fails" -eq 0 ]; then state=success; else state=failure; fi
    desc="$counts; $shards GPU shards in ${elapsed}s"
    if gh api "repos/$GH_REPO/statuses/$sha" -f state="$state" -f context="E2E (GPU, k8s)" -f description="${desc:0:140}" >/dev/null; then
        echo "posted commit status 'E2E (GPU, k8s)' = $state on ${sha:0:12}: $desc"
    else
        echo "WARNING: could not post the commit status (gh api failed)"
    fi
fi
echo "the Job and its pods self-delete 1h after finishing (ttlSecondsAfterFinished=3600)"
[ "$fails" -eq 0 ]
}

main "$@"
