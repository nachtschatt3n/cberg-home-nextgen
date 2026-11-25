#!/bin/bash
# SUITE=clipgate, called by run.sh after the game's `npm ci`: ONE shard of the
# game's PoC 3D clipping gate (tools/poc3d-clipgate.mjs: pure Node, one core,
# no WebGL). The figures of `--rigs` are dealt round-robin over the shards
# (rig i goes to shard i mod N + 1); this shard gates its share with
# `--pics 0` once per hand state of `--hands` (a comma list, e.g. fist,open;
# none = the figures' built hands) into $OUT/gate-<hands>/ and
# $OUT/gate-<hands>.log. The Mac merges the shards' tables
# (coord/tools/farm-clipgate.sh in the game's coordinator folder).
# Exit: 0 every pair passes, 1 a pair fails (the gate's own red), 2 bad
# CLIP_ARGS or no figure for this shard, 4 the gate did not finish (crash,
# missing table), 96 the 3D tool packages did not install.
set -uo pipefail
: "${OUT:?}" "${SHARD:?}" "${N:?}"
log() { echo "[ci $(date -u +%H:%M:%S) clipgate ${SHARD}/${N}] $*"; }

# Same allow-list as the trigger (scripts/ninth-banner-test.sh): flags that
# only choose WHAT is gated. Never a path, never --out/--pics/--fit-solve
# (it writes fit files) or anything that reads a file named by the caller.
read -r -a words <<<"${CLIP_ARGS:-}"
rigs=""; hands=""; pass=()
i=0
while [ "$i" -lt "${#words[@]}" ]; do
    w="${words[$i]}"; v="${words[$((i + 1))]:-}"
    case "$w" in
        --items|--kit|--no-skirt|--raw-aim|--aim) pass+=("$w"); i=$((i + 1)); continue ;;
        --rigs|--only|--hands|--level|--item-level|--step|--pair|--knee|--whole-alt) ;;
        *) log "CLIP_ARGS: '$w' is not an allowed flag"; exit 2 ;;
    esac
    [[ "$v" =~ ^[A-Za-z0-9_@,.-]+$ && "$v" != -* ]] || { log "CLIP_ARGS: $w needs a value of letters, digits and _@,.-"; exit 2; }
    case "$w" in
        --rigs) rigs="$v" ;;
        --hands) hands="$v" ;;
        *) pass+=("$w" "$v") ;;
    esac
    i=$((i + 2))
done
[ -n "$rigs" ] || { log "CLIP_ARGS: --rigs <figure,...> is required"; exit 2; }
IFS=, read -r -a all <<<"$rigs"
mine=""
for ((i = 0; i < ${#all[@]}; i++)); do
    [ $(( i % N + 1 )) -eq "$SHARD" ] && mine="${mine:+$mine,}${all[$i]}"
done
[ -n "$mine" ] || { log "no figure for this shard (${#all[@]} figures, $N shards): the trigger caps the shards at the figure count"; exit 2; }
echo "$mine" >"$OUT/rigs"
IFS=, read -r -a hand_list <<<"${hands:-built}"
for h in "${hand_list[@]}"; do
    [[ "$h" =~ ^(built|fist|open)$ ]] || { log "CLIP_ARGS: --hands takes fist, open or both (fist,open)"; exit 2; }
done

# The 3D tool packages (gltf-transform, meshoptimizer, sharp, ...), pinned by
# the lock file copied from the game's poc3d-tools folder (configMap keys
# poc3d-tools-package*.json), installed outside the game's tree.
tools=/work/poc3d-tools
mkdir -p "$tools"
cp /opt/ci/poc3d-tools-package.json "$tools/package.json"
cp /opt/ci/poc3d-tools-package-lock.json "$tools/package-lock.json"
t0=$(date +%s)
if ! npm ci --prefix "$tools" --no-audit --no-fund --loglevel=error >"$OUT/poc3d-tools-npm-ci.log" 2>&1; then
    tail -n 40 "$OUT/poc3d-tools-npm-ci.log"; exit 96
fi
export POC3D_TOOLS="$tools"
# the gate imports the game's .ts modules as they are: Node's type stripping
strip=()
node -e 'process.exit(process.features.typescript ? 0 : 1)' 2>/dev/null || strip=(--experimental-strip-types)
log "node $(node --version)${strip:+ ${strip[*]}}, 3D tools installed in $(( $(date +%s) - t0 ))s; figures: $mine; hands: ${hand_list[*]}; flags: ${pass[*]:-none}"

rc=0
nfig=$(tr ',' '\n' <<<"$mine" | grep -c .)
for h in "${hand_list[@]}"; do
    hflag=(); [ "$h" = built ] || hflag=(--hands "$h")
    t1=$(date +%s)
    node "${strip[@]}" tools/poc3d-clipgate.mjs --rigs "$mine" "${pass[@]}" "${hflag[@]}" --pics 0 --out "$OUT/gate-$h" >"$OUT/gate-$h.log" 2>&1
    grc=$?
    # the table also goes to the pod log, so shard-N.log holds it if the copy fails
    sed "s/^/[gate-$h] /" "$OUT/gate-$h.log"
    tables=$(grep -c $'^clip\tpair\tworstKey\tdepthCm\tareaCm2\tfailing\tresult$' "$OUT/gate-$h.log")
    if grep -q '^clipping gate passed$' "$OUT/gate-$h.log" && [ "$grc" -eq 0 ] && [ "$tables" -eq "$nfig" ]; then
        log "gate $h: pass, $tables figure(s) in $(( $(date +%s) - t1 ))s"
    elif grep -q '^FAILED: [0-9]* figure-clip pairs over the limits$' "$OUT/gate-$h.log" && [ "$grc" -eq 1 ] && [ "$tables" -eq "$nfig" ]; then
        log "gate $h: pairs over the limits, $tables figure(s) in $(( $(date +%s) - t1 ))s"
        [ "$rc" -ne 0 ] || rc=1
    else
        log "gate $h: did not finish (exit $grc, $tables of $nfig figure tables): see gate-$h.log"
        rc=4
    fi
done
exit "$rc"
