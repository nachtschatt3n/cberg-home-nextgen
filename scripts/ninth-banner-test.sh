#!/usr/bin/env bash
# Run The Ninth Banner's test suites as a sharded Kubernetes Job on the
# cluster (namespace ci-runner) and collect the results on this Mac.
#
#   scripts/ninth-banner-test.sh <ref> <unit|e2e|nightly|responsive|release|sims> [shards]
#   scripts/ninth-banner-test.sh --collect <job>
#
#   ref     commit sha (short ok), branch or tag of nachtschatt3n/the-ninth-banner
#   shards  default: e2e/nightly/responsive/release 3, sims 6, unit 1 (forced)
#   --collect <job>  re-attach the collector to a Job that was submitted from
#           this Mac and whose collector stopped: reads <results>/<job>/job.yaml,
#           creates nothing, never posts the release commit status
#
# release: when every shard has reported, posts the commit status
# "E2E (GPU, k8s)" on the game repo with gh (the pods hold no token).
#
# Env: RESULTS_DIR (default ~/ci-results), WORKERS (playwright workers per
# shard, default 2), COLLECT=0 (fire and forget: no wait, no artifact copy),
# GPU=1|0 (Chromium on the node's Intel iGPU via the device plugin; default 1
# for e2e/nightly/responsive, 0 for unit/sims), SPECS
# (space-separated spec files), PROJECT (e.g. chromium), CPU_REQ/CPU_LIM
# (per-shard CPU, default 2/4 browser lane, 1/1.5 cpu lane = sims/unit
# without GPU; never above 4, thermal cap), TNB_POD_DEADLINE (one shard's own
# time limit in seconds; default sims 12600, else 5400), DRY_RUN=1 (render the
# Job for every parallelism the admission may pick and print its deadlines;
# nothing is created).
# ---
# Admission (docs/sops/ci-runner.md): the Job is created only once all parallel
# shard pods first-fit, one at a time, into the schedulable nodes' free CPU
# AND memory, each node keeping TNB_HEADROOM_CPU (default 2) and TNB_HEADROOM_MEM
# (default 2Gi) free, and the ci-runner ResourceQuota still has room
# (scripts/ninth-banner-capacity.py decide); until then `queued: need X, free Y
# (reason)` every TNB_POLL s (60). Queue
# time never counts against activeDeadlineSeconds (the Job does not exist yet).
# TNB_QUEUE_TIMEOUT (default 14400 s) bounds the wait. sims: at most one
# non-terminal sims Job per SUBMITTER (default: the Ninth Banner branch containing <sha>, else sha8; never this repo's branch); parallelism
# 6 (all shards) when it fits, else 3, else 2. Unreadable kubectl data fails loud (exit 3).
# Deadlines: per POD (each shard's own budget, from its own start) and per
# JOB (outer bound for the whole run incl. shards waiting for a slot; for sims
# it follows the parallelism: rounds x (pod deadline + 300 s)).
# Results: <results>/<job>/summary.txt holds exactly one `CI-RESULT ...
# shard=i/N ...` line per shard, in shard order, written in one step when the
# collector ends (also when a signal stops it). `result=PASS` and
# `result=FAIL rc=<number>` come from the shard itself. A shard that could not
# report is `result=FAIL rc=? (lost: <kind>: <what happened, what to do>)`.
# Exit status: 0 if every shard passed, 1 otherwise, 2 on usage errors, 3 on
# admission failure (queue timeout / unreadable cluster data).
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

usage() { sed -n '2,/^# ---$/p' "$0" | sed -e '$d' -e 's/^# \{0,1\}//'; exit 2; }
# kubectl comes from the repo's pinned tools. TNB_KUBECTL (a command line, split
# on blanks) replaces it, as in scripts/ninth-banner-capacity.py: the tests in
# runbooks/tests/ put a fake there.
read -r -a KUBECTL <<<"${TNB_KUBECTL:-mise exec -- kubectl}"
k() { (cd "$REPO_ROOT" && "${KUBECTL[@]}" "$@"); }
poll_s="${TNB_COLLECT_POLL:-10}"   # seconds between two looks of the collector
[[ "$poll_s" =~ ^[0-9]+$ ]] || { echo "TNB_COLLECT_POLL must be whole seconds"; exit 2; }
attached=0
# Output that survives a closed stdout (the session that started the script is
# gone): from the moment the Job exists, the script goes on without output and
# still writes summary.txt. bash 3.2 keeps the text of a failed write in its
# buffer and flushes it into the next redirected file, so stdout goes to
# /dev/null for good first.
trap '' PIPE
say() {
    echo "$@" 2>/dev/null && return 0
    exec >/dev/null 2>&1
    echo
    return 0
}

# ---- submit: everything up to `kubectl create` (not used by --collect) ----
submit() {
ref_in="$1"; suite="$2"; shards="${3:-}"
case "$suite" in
    unit) shards=1 ;;
    e2e|nightly|responsive|release) shards="${shards:-3}" ;;
    sims) shards="${shards:-6}" ;;
    *) echo "unknown suite '$suite'"; usage ;;
esac
[[ "$shards" =~ ^[1-9][0-9]?$ ]] || { echo "shards must be 1..99"; exit 2; }
# Per-JOB parallelism: CPU/SwiftShader mode 2, GPU mode 3 (below). The
# cluster-wide limit is the namespace quota (the thermal gate was removed 2026-10-06).
# Best-effort CI, GitHub CI is the gate.
parallelism=$(( shards < 2 ? shards : 2 ))   # CPU/SwiftShader mode
workers="${WORKERS:-2}"   # 4 per 6-CPU shard starved Chromium (timing tests failed); see SOP
# Browser suites default to the iGPU (10x faster, ~10-20 C cooler, measured
# 2026-10-03); GPU=0 forces the CPU/SwiftShader fallback.
case "$suite" in e2e|nightly|responsive|release) gpu="${GPU:-1}" ;; *) gpu="${GPU:-0}" ;; esac
case "$suite" in e2e|responsive|release)
    [ "$gpu" = 1 ] || { echo "suite '$suite' is GPU-only: on 4 software-rendering CPUs it fails its timing budgets (docs/sops/ci-runner.md)"; exit 2; } ;;
esac
# Lanes (resource profile only, SOP §2b): sims/unit without a browser run in the cpu
# lane with small resources (single-threaded Node: ~1 core, <= 0.61Gi measured
# 2026-10-04) and their own per-node slots; everything else is the browser lane.
case "$suite" in unit|sims) [ "$gpu" = 0 ] && lane=cpu || lane=browser ;; *) lane=browser ;; esac
if [ "$lane" = cpu ]; then
    cpu_req="${CPU_REQ:-1}"; cpu_lim="${CPU_LIM:-1.5}"; mem_req=1Gi; mem_lim=3Gi; eph_req=2Gi; eph_lim=8Gi
else
    cpu_req="${CPU_REQ:-2}"; cpu_lim="${CPU_LIM:-4}"; mem_req=6Gi; mem_lim=10Gi; eph_req=8Gi; eph_lim=16Gi
fi
[[ "$cpu_lim" =~ ^([1-4]|[1-3]\.5)$ ]] || { echo "CPU_LIM must be 1..4 (halves allowed; thermal cap)"; exit 2; }
# These values are pasted into sed and YAML: allow-list them.
[[ "$cpu_req" =~ ^[1-4]$ ]] || { echo "CPU_REQ must be 1..4"; exit 2; }
[[ "$gpu" =~ ^[01]$ ]] || { echo "GPU must be 0 or 1"; exit 2; }
[[ "$workers" =~ ^[1-8]$ ]] || { echo "WORKERS must be 1..8"; exit 2; }
[[ "${SPECS:-}" =~ ^[A-Za-z0-9._/@\ -]*$ ]] || { echo "SPECS: spec paths only"; exit 2; }
[[ "${PROJECT:-}" =~ ^[A-Za-z0-9_-]*$ ]] || { echo "PROJECT: a project name only"; exit 2; }
[[ "${DRY_RUN:-0}" =~ ^[01]$ ]] || { echo "DRY_RUN must be 0 or 1"; exit 2; }
if [ "$gpu" = 1 ]; then
    gpu_res=', gpu.intel.com/i915: "1"'
    # verified 2026-10-03: ANGLE on GL/EGL renders on "Mesa Intel Arc Graphics
    # (MTL)"; the Vulkan path falls back to SwiftShader (no Vulkan ICD in the image)
    chromium_args="--use-gl=angle --use-angle=gl-egl --ignore-gpu-blocklist --enable-gpu-rasterization"
else
    gpu_res=""; chromium_args=""
fi
# GPU shards run cool (peak 66-89 C vs 100-102 C on SwiftShader): 3 in parallel
# per Job (owner decision 2026-10-03); node placement by the scheduler.
# CPU mode stays at 2 per Job.
if [ "$gpu" = 1 ]; then parallelism=$(( shards < 3 ? shards : 3 )); fi
collect="${COLLECT:-1}"
# Deadlines. pod_deadline is each shard pod's own limit and counts from that
# pod's start; deadline is the Job's and counts from the Job's start, so it
# must cover every round when parallelism < shards.
# sims: 12600 s per shard since 2026-11-11 (9000 s killed shards that needed up
# to 9,496 s). The Job deadline follows the parallelism the admission picks:
# rounds x (pod_deadline + 300 s), rounds = ceil(shards / parallelism). With
# every shard inside its pod deadline the last shard ends within that many
# rounds, so the Job deadline never cuts a shard that is still inside its own
# budget; the 300 s per round cover the time between one pod ending and the
# next one starting. 6 shards: 12900 s at parallelism 6, 25800 s at 3, 38700 s
# at 2 (the fixed 28800 s of 2026-11-09 did not cover three rounds of 12600 s;
# the Job-only 10800 s before that killed the third round, 2026-11-07/08).
# Other suites keep 5400 s for both.
case "$suite" in sims) pod_deadline=12600 ;; *) pod_deadline=5400 ;; esac
pod_deadline="${TNB_POD_DEADLINE:-$pod_deadline}"
[[ "$pod_deadline" =~ ^[1-9][0-9]{1,4}$ ]] || { echo "TNB_POD_DEADLINE must be whole seconds, 10..99999"; exit 2; }
set_job_deadline() {   # from $parallelism: call again once the admission has picked it
    rounds=$(( (shards + parallelism - 1) / parallelism ))
    if [ "$suite" = sims ]; then
        deadline=$(( rounds * (pod_deadline + 300) ))
    else
        deadline=5400
        [ "$pod_deadline" -le "$deadline" ] || deadline="$pod_deadline"
    fi
}
set_job_deadline

# --- submitter label (one sims Job in flight per agent) is resolved after the sha is known ---

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

read -r submitter submitter_src <<<"$(python3 "$REPO_ROOT/scripts/ninth-banner-capacity.py" submitter "$sha")" \
    && [ -n "$submitter" ] || { echo "admission: cannot resolve the submitter"; exit 3; }
# --- admission by per-node CPU+memory fit and quota (+ one sims Job per submitter), BEFORE creating the Job ---
admit="$REPO_ROOT/scripts/ninth-banner-capacity.py"
headroom="${TNB_HEADROOM_CPU:-2}"; poll="${TNB_POLL:-60}"; qtimeout="${TNB_QUEUE_TIMEOUT:-14400}"
[[ "$headroom" =~ ^[0-9]+(\.[0-9]+)?$ ]] || { echo "TNB_HEADROOM_CPU must be a number of CPUs"; exit 2; }
[[ "$poll" =~ ^[1-9][0-9]*$ && "$qtimeout" =~ ^[0-9]+$ ]] || { echo "TNB_POLL / TNB_QUEUE_TIMEOUT must be whole seconds"; exit 2; }
probe="$(mktemp)"
sed -e "s|__JOB_NAME__|tnb-probe|g" -e "s|__REF__|$sha|g" -e "s|__SUITE__|$suite|g" -e "s|__SUBMITTER__|$submitter|g" \
    -e "s|__SHARDS__|$shards|g" -e "s|__PARALLELISM__|$parallelism|g" -e "s|__DEADLINE__|$deadline|g" -e "s|__POD_DEADLINE__|$pod_deadline|g" \
    -e "s|__WORKERS__|$workers|g" -e "s|__COLLECT_WAIT__|0|g" \
    -e "s|__CPU_REQ__|$cpu_req|g" -e "s|__CPU_LIM__|$cpu_lim|g" -e "s|__GPU_RES__|$gpu_res|g" \
    -e "s|__LANE__|$lane|g" -e "s|__MEM_REQ__|$mem_req|g" -e "s|__MEM_LIM__|$mem_lim|g" \
    -e "s|__EPH_REQ__|$eph_req|g" -e "s|__EPH_LIM__|$eph_lim|g" \
    -e "s|__CHROMIUM_ARGS__||g" -e "s|__SPECS__||g" -e "s|__PROJECT__||g" "$TEMPLATE" > "$probe"
# the pod's CPU request comes from the rendered pod spec, never hardcoded
req_m="$(python3 "$admit" podreq "$probe")" || { rm -f "$probe"; echo "admission: cannot read the pod CPU request from the rendered template"; exit 3; }
rm -f "$probe"
# sims: all shards at once (max 6) if it fits, else 2; others keep today's parallelism
if [ "$suite" = sims ]; then
    # 6 / 3 / 2: 3 still runs 6 shards in two rounds, for half the CPU of 6
    full=$(( shards < 6 ? shards : 6 )); mid=$(( full / 2 )); half=$(( shards < 2 ? shards : 2 ))
    par_list="$full"
    [ "$mid" -gt "$half" ] && [ "$mid" -lt "$full" ] && par_list="$par_list $mid"
    [ "$half" -lt "$full" ] && par_list="$par_list $half"
else
    par_list="$parallelism"
fi
# The Job exactly as it is (or, DRY_RUN, would be) created: <job name> <out file>
render() {
    sed -e "s|__JOB_NAME__|$1|g" -e "s|__REF__|$sha|g" -e "s|__SUITE__|$suite|g" -e "s|__SUBMITTER__|$submitter|g" \
        -e "s|__SHARDS__|$shards|g" -e "s|__PARALLELISM__|$parallelism|g" -e "s|__DEADLINE__|$deadline|g" -e "s|__POD_DEADLINE__|$pod_deadline|g" \
        -e "s|__WORKERS__|$workers|g" -e "s|__COLLECT_WAIT__|$([ "$collect" = 1 ] && echo 900 || echo 0)|g" \
        -e "s|__CPU_REQ__|$cpu_req|g" -e "s|__CPU_LIM__|$cpu_lim|g" -e "s|__GPU_RES__|$gpu_res|g" \
        -e "s|__LANE__|$lane|g" -e "s|__MEM_REQ__|$mem_req|g" -e "s|__MEM_LIM__|$mem_lim|g" \
        -e "s|__EPH_REQ__|$eph_req|g" -e "s|__EPH_LIM__|$eph_lim|g" \
        -e "s|__CHROMIUM_ARGS__|$chromium_args|g" -e "s|__SPECS__|${SPECS:-}|g" -e "s|__PROJECT__|${PROJECT:-}|g" \
        "$TEMPLATE" > "$2"
}
if [ "${DRY_RUN:-0}" = 1 ]; then
    # No cluster call up to here, and none below: the Job is only rendered.
    dry="$(mktemp -d)"
    for parallelism in $par_list; do
        set_job_deadline
        out="$dry/job-parallel-$parallelism.yaml"
        render "tnb-${suite}$([ "$gpu" = 1 ] && echo -gpu)-${sha:0:7}-dryrun" "$out"
        echo "dry render: suite $suite  shards $shards  parallel $parallelism = $rounds round(s)  deadline=${deadline}s pod_deadline=${pod_deadline}s  -> $out"
        grep -n '^ *activeDeadlineSeconds: ' "$out" | sed 's/^/    line /'
    done
    echo "DRY_RUN=1: no Job was created"
    exit 0
fi
queue_start=$(date +%s)
while :; do
    msg=""
    if [ "$suite" = sims ]; then
        other="$(python3 "$admit" inflight "$submitter")" || { echo "admission: cannot read the Job list (fail loud, not admitting)"; exit 3; }
        [ -z "$other" ] || msg="queued: submitter $submitter already has sims job $other in flight"
    fi
    if [ -z "$msg" ]; then
        rc=0; verdict="$(python3 "$admit" decide --req "$req_m" --par "$par_list" --headroom "$headroom")" || rc=$?
        if [ "$rc" -eq 0 ]; then
            read -r _ chosen _ _ <<<"$verdict"
            # Race-safety is BEST-EFFORT: two invocations in the same instant can
            # both pass; re-checking the submitter right before create narrows
            # the window to the kubectl round-trip.
            if [ "$suite" = sims ]; then
                other="$(python3 "$admit" inflight "$submitter")" || { echo "admission: cannot read the Job list (fail loud)"; exit 3; }
                [ -z "$other" ] || msg="queued: submitter $submitter already has sims job $other in flight"
            fi
            if [ -z "$msg" ]; then parallelism="$chosen"; break; fi
        elif [ "$rc" -eq 10 ]; then
            read -r _ need_cpu free_cpu <<<"$verdict"; msg="queued: need $need_cpu, free $free_cpu"
        else
            echo "admission: cannot compute node capacity / quota (rc=$rc); refusing to start (fail loud, never 'plenty of room')"; exit 3
        fi
    fi
    waited=$(( $(date +%s) - queue_start ))
    if [ "$waited" -ge "$qtimeout" ]; then
        echo "$msg"; echo "QUEUE TIMEOUT after ${waited}s (TNB_QUEUE_TIMEOUT=${qtimeout}); no Job was created"; exit 3
    fi
    echo "$msg  (waited ${waited}s)"
    sleep "$poll"
done
queue_wait=$(( $(date +%s) - queue_start ))
set_job_deadline   # the Job's deadline for the parallelism the admission picked

job="tnb-${suite}$([ "$gpu" = 1 ] && echo -gpu)-${sha:0:7}-$(date +%m%d%H%M%S)"
dest="${RESULTS_DIR:-$HOME/ci-results}/$job"
mkdir -p "$dest"

render "$job" "$dest/job.yaml"
k create -f "$dest/job.yaml" >/dev/null
start=$(date +%s)
say "job $NS/$job  commit ${sha:0:12}  suite $suite  shards $shards (parallel $parallelism = $rounds round(s))  lane=$lane gpu=$gpu cpu=$cpu_req/$cpu_lim mem=$mem_req/$mem_lim  deadline=${deadline}s pod_deadline=${pod_deadline}s  queued=${queue_wait}s parallelism=$parallelism submitter=$submitter($submitter_src)"
if [ "$collect" != 1 ]; then
    # Fire and forget: return once the Job controller has created every shard pod.
    echo "COLLECT=0: waiting only until all $shards shard pod(s) exist"
    while :; do
        created="$(k get pods -n "$NS" -l "batch.kubernetes.io/job-name=$job" --no-headers 2>/dev/null | wc -l | tr -d ' ')"
        [ "${created:-0}" -ge "$shards" ] && break
        sleep 10
    done
    echo "all shards created. Logs: kubectl logs -n $NS -l batch.kubernetes.io/job-name=$job -c runner --prefix"
    exit 0
fi
}

# ---- --collect <job>: everything the collector needs is in the rendered Job ----
attach() {
job="$1"
[[ "$job" =~ ^tnb-[a-z0-9-]+$ ]] || { echo "--collect: '$job' is not a job name (tnb-...)"; exit 2; }
dest="${RESULTS_DIR:-$HOME/ci-results}/$job"
[ -s "$dest/job.yaml" ] || { echo "--collect: no $dest/job.yaml (was the Job submitted from this Mac?)"; exit 2; }
suite="$(awk '/^    ci\.cberg\.home\/suite: /{print $2; exit}' "$dest/job.yaml")"
sha="$(awk -F'"' '/^    ci\.cberg\.home\/ref: /{print $2; exit}' "$dest/job.yaml")"
shards="$(awk '/^  completions: /{print $2; exit}' "$dest/job.yaml")"
parallelism="$(awk '/^  parallelism: /{print $2; exit}' "$dest/job.yaml")"
deadline="$(awk '/^  activeDeadlineSeconds: /{print $2; exit}' "$dest/job.yaml")"
pod_deadline="$(awk '/^      activeDeadlineSeconds: /{print $2; exit}' "$dest/job.yaml")"
pod_deadline="${pod_deadline:-$deadline}"   # Jobs from before 2026-11-09 have no pod deadline
[[ "$suite" =~ ^(unit|e2e|nightly|responsive|release|sims)$ && "$shards" =~ ^[1-9][0-9]?$ \
    && "$deadline" =~ ^[1-9][0-9]*$ && "$pod_deadline" =~ ^[1-9][0-9]*$ ]] \
    || { echo "--collect: cannot read suite, shards and deadlines from $dest/job.yaml"; exit 2; }
# the Job's start, to within seconds: job.yaml is written right before `kubectl create`
start="$(python3 -c 'import os, sys; print(int(os.path.getmtime(sys.argv[1])))' "$dest/job.yaml")"
attached=1
say "collect $NS/$job  commit ${sha:0:12}  suite $suite  shards $shards (parallel ${parallelism:-?})  deadline=${deadline}s pod_deadline=${pod_deadline}s  submitted $(( $(date +%s) - start ))s ago"
}

if [ "${1:-}" = "--collect" ]; then
    [ $# -eq 2 ] || usage
    attach "$2"
else
    [ $# -ge 2 ] || usage
    submit "$@"
fi

# ---- collector ----
# ISO UTC timestamp for an epoch (BSD date on macOS, GNU date fallback)
iso() { date -u -r "$1" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d "@$1" +%Y-%m-%dT%H:%M:%SZ; }
ttl=3600     # ttlSecondsAfterFinished in the job template
margin=300   # 5 min either side of the lookup window
# Per shard, index = shard - 1 (indexed arrays: bash 3.2 on macOS has no associative ones)
pod_names=(); pod_seen=()                   # pod name, epoch first seen
last_phase=(); last_node=(); last_wait=()   # what the last look saw of that pod
gone_rounds=(); term_rounds=()              # looks without the pod / at a dead pod without results
done_idx=(); lines=(); ndone=0; fails=0; lostn=0
summary_written=0

# One collector per Job: two would copy and count the same shards.
if [ -f "$dest/collector.pid" ]; then
    other_pid="$(cat "$dest/collector.pid" 2>/dev/null || true)"
    other_cmd=""
    if [[ "$other_pid" =~ ^[0-9]+$ ]]; then other_cmd="$(ps -p "$other_pid" -o command= 2>/dev/null || true)"; fi
    case "$other_cmd" in *ninth-banner-test*)
        say "a collector for $job is still running (pid $other_pid): not starting a second one"; exit 2 ;;
    esac
fi
echo $$ > "$dest/collector.pid"

# Exactly one line per shard: the first one recorded stays.
record() {   # <index> <line>
    [ -z "${done_idx[$1]:-}" ] || return 0
    done_idx[$1]=1; lines[$1]="$2"; ndone=$((ndone + 1))
    grep -q 'result=PASS' <<<"$2" || fails=$((fails + 1))
    say "  $2"
}
# A shard that could not report. `rc=?` is the contract with the caller: its
# wait tool counts result=PASS, takes result=FAIL rc=<number> as a real red and
# everything else as lost. The line also ends the shard's own log on this Mac.
lost() {   # <index> <kind> <what happened and what to do>
    [ -z "${done_idx[$1]:-}" ] || return 0
    local n=$(( $1 + 1 )) detail="$3" f line
    detail="${detail//rc=/rc }"; detail="${detail//result=/result }"   # free text never reads as a verdict
    line="CI-RESULT suite=$suite shard=$n/$shards result=FAIL rc=? (lost: $2: $detail; partial log, if any, in shard-$n.log)"
    f="$dest/shard-$n.log"
    if [ -f "$f" ]; then   # a re-attached collector replaces the earlier lost line
        grep -v '^CI-RESULT .* rc=? (lost: ' "$f" > "$f.tmp" || true
        mv -f "$f.tmp" "$f"
    fi
    printf '%s\n' "$line" >> "$f"
    lostn=$((lostn + 1))
    record "$1" "$line"
}
# In one step (tmp + mv): the caller's wait tool reads summary.txt as soon as it is not empty.
write_summary() {
    local i
    for ((i = 0; i < shards; i++)); do
        [ -n "${lines[$i]:-}" ] || lost "$i" "collector error" "no result was recorded for this shard: rerun it"
    done
    for ((i = 0; i < shards; i++)); do printf '%s\n' "${lines[$i]}"; done > "$dest/summary.txt.tmp"
    mv -f "$dest/summary.txt.tmp" "$dest/summary.txt"
    summary_written=1
}
# The collector ends early (signal, error): every shard still gets its line.
# No kubectl in here; `--collect` reads the cluster again.
on_exit() {
    local rc="$1" i
    trap - EXIT
    set +e
    rm -f "$dest/collector.pid" "$dest/collector.err"
    [ "$summary_written" = 1 ] && exit "$rc"
    for ((i = 0; i < shards; i++)); do
        lost "$i" "collector stopped" "the collector on this Mac ended (exit code $rc) before this shard reported; the Job may still be running: scripts/ninth-banner-test.sh --collect $job"
    done
    write_summary
    say "collector stopped (exit code $rc): $dest/summary.txt has a line for every shard; re-attach with scripts/ninth-banner-test.sh --collect $job"
    exit "$rc"
}
trap 'on_exit $?' EXIT
trap 'exit 143' TERM
trap 'exit 130' INT
trap 'exit 129' HUP

# Job state: active | unreadable | Vanished (deleted by hand or by its TTL) |
# Complete[:reason] | Failed:<reason>. FailureTarget (set first, while the Job
# controller still removes the pods) counts as Failed. A Job that ends by
# DeadlineExceeded deletes its running pods and never starts the pending
# indexes, so those shards can never report: without this the loop waited
# forever (2026-10-20, tnb-sims-43224f7).
re_failed=' (Failed|FailureTarget):([A-Za-z]*)'
re_complete=' Complete:([A-Za-z]*)'
job_state() {
    local out
    # stderr apart: a warning of the tool wrapper must not read as a condition
    if ! out="$(k get job -n "$NS" "$job" -o jsonpath='{range .status.conditions[?(@.status=="True")]}{.type}:{.reason} {end}' 2>"$dest/collector.err")"; then
        if grep -q 'NotFound' "$dest/collector.err" 2>/dev/null; then echo Vanished; else echo unreadable; fi
        return 0
    fi
    if [[ " $out" =~ $re_failed ]]; then echo "Failed:${BASH_REMATCH[2]}"
    elif [[ " $out" =~ $re_complete ]]; then echo "Complete${BASH_REMATCH[1]:+:${BASH_REMATCH[1]}}"
    else echo active; fi
}
# All pods of the Job in one read, one line per pod. A read that fails means
# "not readable in this look" (pods_ok=0), never "no pod".
pod_fields='{range .items[*]}{.metadata.labels.batch\.kubernetes\.io/job-completion-index}{"|"}{.metadata.name}{"|"}{.status.phase}{"|"}{.status.reason}{"|"}{.spec.nodeName}{"|"}{.status.conditions[?(@.type=="PodScheduled")].reason}{"|"}{.status.initContainerStatuses[0].state.waiting.reason}{"|"}{.status.initContainerStatuses[0].state.terminated.exitCode}{"|"}{.status.containerStatuses[0].state.waiting.reason}{"|"}{.status.containerStatuses[0].state.terminated.reason}{"|"}{.status.containerStatuses[0].state.terminated.exitCode}{"|"}{.status.message}{"\n"}{end}'
read_pods() {
    local out idx name phase reason node sched iwait iexit cwait cterm cexit message
    p_name=(); p_phase=(); p_reason=(); p_node=(); p_wait=(); p_iexit=(); p_cterm=(); p_cexit=(); p_message=()
    pods_ok=0
    out="$(k get pods -n "$NS" -l "batch.kubernetes.io/job-name=$job" -o jsonpath="$pod_fields" 2>/dev/null)" || return 0
    pods_ok=1
    while IFS='|' read -r idx name phase reason node sched iwait iexit cwait cterm cexit message; do
        [[ "$idx" =~ ^[0-9]+$ ]] && [ "$idx" -lt "$shards" ] || continue
        p_name[$idx]="$name"; p_phase[$idx]="$phase"; p_reason[$idx]="$reason"; p_node[$idx]="$node"
        p_iexit[$idx]="$iexit"; p_cterm[$idx]="$cterm"; p_cexit[$idx]="$cexit"; p_message[$idx]="$message"
        # what a pod that is not running waits for: a node, or its image / clone step
        if [ -z "$node" ]; then p_wait[$idx]="${sched:-not scheduled}"; else p_wait[$idx]="${iwait:-$cwait}"; fi
    done <<<"$out"
}
# No pod for this shard in a pod list that was read.
no_pod() {   # <index>
    local i="$1" seen="${pod_names[$1]:-}" was=""
    if [ -n "$seen" ]; then
        was="pod $seen (last seen ${last_phase[$i]:-?}${last_node[$i]:+ on ${last_node[$i]}}${last_wait[$i]:+, ${last_wait[$i]}})"
    fi
    case "$jstate" in
        unreadable) ;;   # the Job could not be read in this look: decide nothing
        Vanished)
            lost "$i" "job gone" "the Job no longer exists (deleted by hand, or by its 60 min TTL after it ended) before this shard reported; ${was:-no pod of this shard was seen}: rerun" ;;
        Failed:DeadlineExceeded)
            if [ -z "$seen" ]; then
                lost "$i" "never started" "the Job hit its deadline of ${deadline}s before a slot was free for this shard (parallel ${parallelism:-?}), no pod was created: rerun"
            elif [ "${last_phase[$i]:-}" = Pending ] && [ -z "${last_node[$i]:-}" ]; then
                lost "$i" "never scheduled" "$was found no node until the Job hit its deadline of ${deadline}s: check free CPU and memory on the nodes and the ci-runner quota, then rerun"
            elif [ "${last_phase[$i]:-}" = Pending ]; then
                lost "$i" "never started" "$was was still starting when the Job hit its deadline of ${deadline}s: rerun"
            else
                lost "$i" "job deadline" "the Job hit its deadline of ${deadline}s and removed $was; the shard started too late in the Job to finish: rerun"
            fi ;;
        *)
            # active, Complete, or Failed for another reason (FailedIndexes: a
            # shard failed, the others go on). No pod yet: the shard waits for a
            # slot. A pod that was there and is gone was deleted; three looks,
            # so a pod list that is behind for a moment loses nothing.
            if [ -n "$seen" ]; then
                gone_rounds[$i]=$(( ${gone_rounds[$i]:-0} + 1 ))
                [ "${gone_rounds[$i]}" -ge 3 ] || return 0
                lost "$i" "pod gone" "$was was deleted before its result was read (node drain, eviction or a delete by hand; Job: $jstate): rerun"
            elif [ "$jstate" != active ]; then
                lost "$i" "pod gone" "the Job ended ($jstate) and no pod of this shard exists (deleted before this collector saw it): rerun"
            fi ;;
    esac
}
# The pod is Failed or Succeeded and staged no results.
dead_pod() {   # <index>
    local i="$1" n=$(( $1 + 1 )) where
    local phase="${p_phase[$1]:-}" reason="${p_reason[$1]:-}" iexit="${p_iexit[$1]:-}" cterm="${p_cterm[$1]:-}" cexit="${p_cexit[$1]:-}" message="${p_message[$1]:-}"
    where="pod ${p_name[$i]}${p_node[$i]:+ on ${p_node[$i]}}"
    if [ "$reason" = DeadlineExceeded ] && [ "$iexit" = 0 ] && [ -z "${p_wait[$i]:-}" ]; then
        # the clone step ended well and the runner waits for nothing: the tests ran
        lost "$i" "pod deadline" "$where ran past pod_deadline=${pod_deadline}s and was killed: the shard needs a longer pod deadline (TNB_POD_DEADLINE) or less work"
    elif [ "$reason" = DeadlineExceeded ]; then
        lost "$i" "pod deadline" "$where was killed at pod_deadline=${pod_deadline}s before its tests started (${p_wait[$i]:-clone step}): see the clone output in shard-$n.log"
    elif [ -n "$iexit" ] && [ "$iexit" != 0 ]; then
        lost "$i" "clone failed" "the clone step of $where ended with exit code $iexit (git fetch or npm ci): its output is at the top of shard-$n.log"
    elif [ "$cterm" = OOMKilled ]; then
        lost "$i" "out of memory" "the runner of $where was OOMKilled at its memory limit: fewer WORKERS, or a higher limit in the job template"
    elif [ "$reason" = Evicted ]; then
        lost "$i" "evicted" "$where was evicted by its node (${message:0:160}): rerun"
    else
        lost "$i" "pod died" "$where ended $phase${reason:+, $reason}${cterm:+, runner $cterm}${cexit:+ with exit code $cexit} without a result line: see shard-$n.log"
    fi
}

if [ "$attached" = 1 ]; then
    # results an earlier collector already brought home
    for ((i = 0; i < shards; i++)); do
        f="$dest/shard-$((i + 1)).log"
        if [ -f "$f" ] && grep -q '^CI-RESULTS-READY' "$f"; then
            line="$(grep '^CI-RESULT ' "$f" | grep -v ' rc=? (' | tail -1 || true)"
            if [ -n "$line" ]; then record "$i" "$line"; fi
        fi
    done
fi
while [ "$ndone" -lt "$shards" ]; do
    jstate="$(job_state)"
    read_pods
    for ((i = 0; i < shards; i++)); do
        [ -z "${done_idx[$i]:-}" ] || continue
        [ "$pods_ok" = 1 ] || continue   # the pod list could not be read: decide nothing in this look
        n=$((i + 1)); pod="${p_name[$i]:-}"
        if [ -z "$pod" ]; then
            no_pod "$i"
            continue
        fi
        gone_rounds[$i]=0
        if [ "${pod_names[$i]:-}" != "$pod" ]; then
            # first sight of this shard's pod (or a replacement): print the
            # recovery command now, with the latest possible end as the window
            # end, so a pod removed by the TTL can still be read from Elastic
            pod_names[$i]="$pod"; pod_seen[$i]=$(date +%s)
            # re-attached: the pod may be as old as the Job
            [ "$attached" != 1 ] || pod_seen[$i]=$start
            say "  shard $n/$shards logs: scripts/ninth-banner-logs.sh $pod $(iso $(( ${pod_seen[$i]} - margin ))) $(iso $(( start + deadline + margin )))"
        fi
        phase="${p_phase[$i]:-}"
        last_phase[$i]="$phase"; last_node[$i]="${p_node[$i]:-}"; last_wait[$i]="${p_wait[$i]:-}"
        # Pending: waits for a node (no pod deadline runs yet) or for its image
        # and clone step (the pod deadline runs)
        [ "$phase" != Pending ] || continue
        logs_rc=0; logs="$(k logs -n "$NS" "$pod" -c runner 2>/dev/null)" || logs_rc=$?
        # keep the newest partial log, so a pod deleted mid-run (deadline,
        # eviction, preemption) still leaves its output on this Mac
        if [ -n "$logs" ]; then printf '%s\n' "$logs" > "$dest/shard-$n.log"; fi
        if grep -q '^CI-RESULTS-READY' <<<"$logs"; then
            k cp -c runner "$NS/$pod:/results" "$dest" >/dev/null 2>&1 || say "  (copy of shard $n artifacts failed)"
            k exec -n "$NS" "$pod" -c runner -- touch /results/.collected >/dev/null 2>&1 || true
            line="$(grep '^CI-RESULT ' <<<"$logs" | tail -1 || true)"
            if [ -n "$line" ]; then
                record "$i" "$line"
            else
                lost "$i" "no result line" "pod $pod staged its results without a CI-RESULT line: see shard-$n.log and shard-$n/exit-code"
            fi
            continue
        fi
        case "$phase" in Failed|Succeeded) ;; *) continue ;; esac
        # dead before staging results (clone failure, OOM, pod deadline, eviction).
        # A log read that failed is not "no results": look again, twice, first.
        term_rounds[$i]=$(( ${term_rounds[$i]:-0} + 1 ))
        if [ "$logs_rc" -ne 0 ] && [ "${term_rounds[$i]}" -lt 3 ]; then continue; fi
        if [ -z "$logs" ] && [ -f "$dest/shard-$n.log" ]; then logs="$(cat "$dest/shard-$n.log")"; fi
        { k logs -n "$NS" "$pod" -c clone 2>&1 || true; printf '%s\n' "$logs"; } > "$dest/shard-$n.log"
        dead_pod "$i"
    done
    [ "$ndone" -lt "$shards" ] || break
    if [ "$(date +%s)" -gt $(( start + deadline + ttl + 900 )) ]; then
        # Past the Job's latest end plus its TTL nothing is left that could report.
        for ((i = 0; i < shards; i++)); do
            if [ "$pods_ok" != 1 ] || [ "$jstate" = unreadable ]; then
                lost "$i" "cluster unreadable" "kubectl could not read the Job or its pods, and the Job's latest end (deadline ${deadline}s) plus its 60 min TTL have passed: the pod's output is in Elastic (scripts/ninth-banner-logs.sh), rerun"
            else
                lost "$i" "no end state" "the Job's latest end (deadline ${deadline}s) plus its 60 min TTL have passed and the shard's pod (${pod_names[$i]:-none seen}) neither reported nor ended: look at the Job by hand, rerun"
            fi
        done
        break
    fi
    sleep "$poll_s"
done

elapsed=$(( $(date +%s) - start ))
write_summary

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
say "----"
end_ts=$(date +%s)
for ((i = 0; i < shards; i++)); do
    [ -n "${pod_names[$i]:-}" ] || continue
    say "logs shard $((i + 1))/$shards: scripts/ninth-banner-logs.sh ${pod_names[$i]} $(iso $(( ${pod_seen[$i]} - margin ))) $(iso $(( end_ts + margin )))"
done
if [ "$no_tests" = 1 ]; then
    say "FAIL  $suite @ ${sha:0:12}: 0 tests executed (planned ${planned}; SPECS='${SPECS:-}' PROJECT='${PROJECT:-}'). A run that tests nothing is a failure: check the spec paths, or the shard logs for 'NO-TESTS'."
elif [ "$fails" -eq 0 ]; then
    say "PASS  $suite @ ${sha:0:12}: $shards/$shards shards passed in ${elapsed}s"
else
    say "FAIL  $suite @ ${sha:0:12}: $fails/$shards shards failed, $lostn of them lost (rc=?: no verdict on the code) (${elapsed}s)"
fi
say "tests: $counts (executed $executed of $planned planned)"
if [[ "$executed" =~ ^[0-9]+$ ]] && [[ "$planned" =~ ^[0-9]+$ ]] && [ "$executed" -lt "$planned" ]; then
    say "WARNING: TEST-COUNT-MISMATCH: $((planned - executed)) planned tests never ran (dropped from the --test-list match; docs/sops/ci-runner.md)"
fi
say "artifacts: $dest  (shard-N/: junit.xml, playwright-report/, test-results/ traces, blob-report/; release: per part in shard-N/{release,responsive}/)"
if ls "$dest"/shard-*/blob-report/*.zip "$dest"/shard-*/*/blob-report/*.zip >/dev/null 2>&1; then
    say "merged report (from a checkout of the game at ${sha:0:12}): npm run test:merge-reports -- \"$dest\" --out \"$dest/report\""
fi


if [ "$suite" = release ] && [ "$attached" = 1 ]; then
    say "commit status 'E2E (GPU, k8s)' NOT posted: a re-attached collector never posts it (run the release suite again for the gate)"
elif [ "$suite" = release ]; then
    # Only for a complete run: every shard reported above, or we never got here.
    if [ "$fails" -eq 0 ]; then state=success; else state=failure; fi
    desc="$counts; $shards GPU shards in ${elapsed}s"
    if gh api "repos/$GH_REPO/statuses/$sha" -f state="$state" -f context="E2E (GPU, k8s)" -f description="${desc:0:140}" >/dev/null; then
        say "posted commit status 'E2E (GPU, k8s)' = $state on ${sha:0:12}: $desc"
    else
        say "WARNING: could not post the commit status (gh api failed)"
    fi
fi
say "the Job and its pods self-delete 60 min after the whole Job finishes (ttlSecondsAfterFinished=3600; logs stay in Elastic via the scripts/ninth-banner-logs.sh lines above)"
[ "$fails" -eq 0 ]
}

main "$@"
