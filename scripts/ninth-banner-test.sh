#!/usr/bin/env bash
# Run The Ninth Banner's test suites as a sharded Kubernetes Job on the
# cluster (namespace ci-runner) and collect the results on this Mac.
#
#   scripts/ninth-banner-test.sh <ref> <unit|e2e|nightly|responsive|sims> [shards]
#
#   ref     commit sha (short ok), branch or tag of nachtschatt3n/the-ninth-banner
#   shards  default: e2e/nightly/responsive 3, sims 4 (one sweep each), unit 1 (forced)
#
# Env: RESULTS_DIR (default ~/ci-results), WORKERS (playwright workers per
# shard, default 2), COLLECT=0 (fire and forget: no wait, no artifact copy).
# Exit status: 0 if every shard passed, 1 otherwise, 2 on usage errors.
# Full procedure, security model and troubleshooting: docs/sops/ci-runner.md
set -euo pipefail

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
    e2e|nightly|responsive) shards="${shards:-3}" ;;
    sims) shards="${shards:-4}" ;;
    *) echo "unknown suite '$suite'"; usage ;;
esac
[[ "$shards" =~ ^[1-9][0-9]?$ ]] || { echo "shards must be 1..99"; exit 2; }
parallelism=$(( shards < 3 ? shards : 3 ))
workers="${WORKERS:-2}"   # 4 per 6-CPU shard starved Chromium (timing tests failed); see SOP
collect="${COLLECT:-1}"

sha="$(gh api "repos/$GH_REPO/commits/$ref_in" --jq .sha)" || { echo "cannot resolve ref '$ref_in'"; exit 2; }
job="tnb-${suite}-${sha:0:7}-$(date +%m%d%H%M%S)"
dest="${RESULTS_DIR:-$HOME/ci-results}/$job"
mkdir -p "$dest"

sed -e "s|__JOB_NAME__|$job|g" -e "s|__REF__|$sha|g" -e "s|__SUITE__|$suite|g" \
    -e "s|__SHARDS__|$shards|g" -e "s|__PARALLELISM__|$parallelism|g" \
    -e "s|__WORKERS__|$workers|g" -e "s|__COLLECT_WAIT__|$([ "$collect" = 1 ] && echo 900 || echo 0)|g" \
    "$TEMPLATE" > "$dest/job.yaml"
k create -f "$dest/job.yaml" >/dev/null
start=$(date +%s)
echo "job $NS/$job  commit ${sha:0:12}  suite $suite  shards $shards (parallel $parallelism)"
if [ "$collect" != 1 ]; then
    echo "COLLECT=0: not waiting. Logs: kubectl logs -n $NS -l batch.kubernetes.io/job-name=$job -c runner --prefix"
    exit 0
fi

pod_of() { k get pods -n "$NS" -l "batch.kubernetes.io/job-name=$job,batch.kubernetes.io/job-completion-index=$1" \
               -o jsonpath='{.items[-1:].metadata.name}' 2>/dev/null || true; }
done_idx=()   # indexed array: bash 3.2 (macOS) has no associative arrays
summary=()
fails=0
while [ "${#done_idx[@]}" -lt "$shards" ]; do
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
echo "----"
if [ "$fails" -eq 0 ]; then
    echo "PASS  $suite @ ${sha:0:12}: $shards/$shards shards passed in ${elapsed}s"
else
    echo "FAIL  $suite @ ${sha:0:12}: $fails/$shards shards failed (${elapsed}s)"
fi
echo "artifacts: $dest  (shard-N/: junit.xml, playwright-report/, test-results/ traces, blob-report/)"
if ls "$dest"/shard-*/blob-report/*.zip >/dev/null 2>&1; then
    echo "merged HTML report: mkdir -p $dest/blobs && cp $dest/shard-*/blob-report/*.zip $dest/blobs/ && (cd ~/code/the-ninth-banner && npx playwright merge-reports --reporter html $dest/blobs && npx playwright show-report)"
fi
echo "the Job and its pods self-delete 1h after finishing (ttlSecondsAfterFinished=3600)"
[ "$fails" -eq 0 ]
