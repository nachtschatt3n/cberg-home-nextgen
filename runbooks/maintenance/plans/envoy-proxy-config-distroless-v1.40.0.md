---
plan_id: envoy-proxy-config-distroless-v1.40.0
component: envoy-proxy-config
also_covers:
  - docker.io/envoyproxy/envoy        # the Envoy DATA-PLANE image pinned in EnvoyProxy/network/envoy-proxy-config
pr: null                              # no Renovate PR: the `distroless-v` prefix is not docker-versionable
                                      # (gatewayclass.yaml comment). Surfaced by version-check-current.md row
                                      # "distroless-v1.39.1 -> distroless-v1.40.0"; dispatched by sweep cycle aba6b526.
kind: image
current: "distroless-v1.39.1@sha256:eb2c01c13125d1629637cb4e4cce7207009fb7cc2c8027f9742758549d15b6f4"
target: "distroless-v1.40.0@sha256:23b72ac1fa94908b2ca7ebf194cc6083cd0d4913210c7d7453e4b2008ca26c84"
update_type: minor
risk: high                            # cross-MINOR under a controller (EG v1.9.2) that upstream has NOT tested
                                      # with Envoy 1.40; failure mode is SILENT config rejection that surfaces
                                      # exactly on restart, and this change restarts all 6 proxy pods of both
                                      # gateways (the only HTTP data plane, LAN + public edge).
est_duration_min: 60                  # only meaningful once unblocked: §2 15 + §3 5 + rolls ~8 + §4 ~20 + soak 7 + slack 5
needs_reboot: false
exclusive: false
touches:
  namespaces: [network]
  resources:
    - envoyproxy/network/envoy-proxy-config                      # spec.provider.kubernetes.envoyDeployment.container.image
    - deployment/network/envoy-internal                          # ROLLS (3 pods)
    - deployment/network/envoy-external                          # ROLLS (3 pods)
    - kubernetes/apps/network/envoy-gateway/app/gatewayclass.yaml
  shared:
    - gateway/envoy                   # envoy-internal (.103) + envoy-external (.104) carry EVERY HTTPRoute
    - public-edge                     # envoy-external is the internet-facing data plane
    - authentik                       # SecurityPolicies (ext_authz forward-auth) are enforced inside Envoy
    - monitoring                      # §4 reads Prometheus (xDS-rejection + listener metrics) — the instrument
depends_on: []
  # The real prerequisite is an Envoy Gateway RELEASE that compiles Envoy 1.40.x (EG v1.10.x, unreleased
  # 2026-10-15). No plan exists for it yet, so it cannot be named here without a DEAD-REF; it is carried as
  # the §1 UNBLOCK condition instead (the former premise `eg-release-compiles-1.40` was dropped 2026-10-25:
  # plan-premises.py allows no network read command, so it could not run).
conflicts_with:                       # pruned 2026-10-25: only plans that still exist and are not executed/superseded
  - envoy-proxy-config-distroless-v1.39.4   # SAME pin line (file name kept; it now targets distroless-v1.39.5)
  - talos-linux-1.14.4                # node drain competes for the single PDB disruption
  - flux-reconciler-impersonation     # rewrites how kustomize-controller applies this
  - flux-oci-chart-sources            # moves Flux sources; same §3/§5 apply-and-revert path
capability_change: true               # A new Envoy MINOR changes behaviour, not just the binary: post-quantum
                                      # X25519MLKEM768 joins the DEFAULT ECDH curves on every downstream and
                                      # upstream TLS handshake, container-aware CPU detection changes worker
                                      # count semantics, drain becomes event-driven, and 28 runtime guards /
                                      # legacy paths are removed (http2 safe defaults, websocket 4xx/5xx
                                      # passthrough, validate_upstream_headers, …). Not a same-behaviour bump.
rollback_class: git-revert            # no CRD, no state, no migration; the 1.39.1 image is digest-pinned,
                                      # still published (re-resolved 2026-10-15) and cached on all 3 nodes.
autonomy_override: human-gated        # shared gateway/envoy derives HUMAN-GATED anyway; attended window only.
security_ref: F-61035b6e              # the security content upstream lists for 1.40.0 is "carried forward
                                      # from 1.39.x" — i.e. ALREADY delivered inside the supported minor by
                                      # plan envoy-proxy-config-distroless-v1.39.4 (file name kept; it now targets distroless-v1.39.5). Detail stays on the DB record.
finding_refs: [F-10b4fee2]            # version row "distroless-v1.39.1 -> distroless-v1.40.0 (minor)", cycle aba6b526
review: null
status: blocked   # BLOCKED 2026-10-15 (planner, sweep aba6b526): no Envoy Gateway release compiles or supports Envoy 1.40 (EG matrix: v1.9 <-> distroless-v1.39.x only; "Compatibility with … newer Envoy Proxy minor versions has not been tested and is unknown"; EG main = distroless-dev). Deny rule *envoyproxy/envoy* forbids a MINOR pin move outside the gateway-helm chart bump. UNBLOCK = an EG v1.10.x release whose api/v1alpha1/shared_types.go DefaultEnvoyProxyImage is distroless-v1.40.x -> then this plan is SUPERSEDED by an envoy-gateway-<v1.10.x> chart plan that moves this pin in the same commit (§6).
window: null
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/envoy-gateway-upgrade.md
  - docs/sops/gateway-api-httproute.md
  - docs/sops/vulnerability-disclosure.md
generated: "2026-10-15"
premises:
  - id: controller-is-1.9.2
    why: "current: and the §5 restore target assume the controller this plan was written against. If the chart moved, re-plan as that chart's lockstep plan."
    run: kubectl get helmrelease envoy-gateway -n network -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: "1.9.2"
  - id: repo-pin-is-1.39.1
    why: "§3.1's sed is anchored on the 1.39.1 digest. If the -v1.39.4 plan (target now distroless-v1.39.5) ran first, the sed matches nothing and §5 restores the wrong image."
    run: grep -o 'envoy:distroless-v[^ ]*' kubernetes/apps/network/envoy-gateway/app/gatewayclass.yaml
    expect_exact: "envoy:distroless-v1.39.1@sha256:eb2c01c13125d1629637cb4e4cce7207009fb7cc2c8027f9742758549d15b6f4"
  - id: both-gateways-programmed
    why: "Start from a serving data plane; a pre-existing Programmed=False would be blamed on the bump."
    run: >-
      kubectl get gateway -n network -o jsonpath='{range .items[*]}{.metadata.name}={.status.conditions[?(@.type=="Programmed")].status} {end}'
    expect_matches: '^envoy-external=True envoy-internal=True\s*$'
  - id: six-proxy-pods-ready
    why: "The surge-first roll and PDB minAvailable 2 assume 3/3 per gateway at the start."
    run: >-
      kubectl get deploy envoy-internal envoy-external -n network -o jsonpath='{range .items[*]}{.metadata.name}={.status.readyReplicas} {end}'
    expect_matches: '^envoy-internal=3 envoy-external=3\s*$'
---

# envoy-proxy-config: Envoy data plane distroless-v1.39.1 -> distroless-v1.40.0 (BLOCKED)

## 1. Summary & why held

**Verdict: correctly held, and NOT executable today. `status: blocked`.** The hold is
not a false positive. This file exists so the held update is owned (the sweep stops
re-dispatching a planner for it, and `F-10b4fee2` is not unplanned), and so the unblock
condition and the gates a cross-minor move needs are written down once.

**What would change.** One line in `kubernetes/apps/network/envoy-gateway/app/gatewayclass.yaml`
(line 85, live 2026-10-15): the `EnvoyProxy/network/envoy-proxy-config` container image
moves from `distroless-v1.39.1@sha256:eb2c01c1…` to
`distroless-v1.40.0@sha256:23b72ac1fa94908b2ca7ebf194cc6083cd0d4913210c7d7453e4b2008ca26c84`.
EG re-renders `deploy/envoy-internal` and `deploy/envoy-external`; all 6 proxy pods roll.

**Why it cannot run under the live controller (measured 2026-10-15).**
- Live: HelmRelease `network/envoy-gateway` chart `1.9.2`, Ready=True; controller image
  `docker.io/envoyproxy/gateway:v1.9.2`; all 6 `envoy` containers on imageID
  `sha256:eb2c01c1…` (1.39.1), 0 restarts.
- Newest EG releases: `v1.9.2` (Latest) / `v1.8.5`, both 2026-09-28. No v1.10.x, no rc.
- Compiled defaults (`api/v1alpha1/shared_types.go DefaultEnvoyProxyImage`):
  `v1.9.2` = `distroless-v1.39.1@sha256:eb2c01c1…`; `release/v1.9` head =
  `distroless-v1.39.3@sha256:7369b033…` (a v1.9.3 is being prepared, still 1.39);
  `main` = `distroless-dev`. No EG ref anywhere pins 1.40.
- EG compatibility matrix (`site/content/en/news/releases/matrix.md`, main), verbatim:
  "Each Envoy Gateway release ships with, and is tested against, a single Envoy Proxy
  minor version. … Compatibility with older or newer Envoy Proxy minor versions has not
  been tested and is unknown." Row: `v1.9 | distroless-v1.39.x`. And the override warning:
  "If the pinned image is a different Envoy Proxy minor version … the combination is
  untested, and Envoy Gateway may generate configuration that the proxy rejects. A
  rejected configuration is silent while the proxies keep running … The failure surfaces
  when a proxy restarts … and pod readiness can still pass while a listener is missing."
  This change IS a restart of every proxy, so it lands exactly on that failure mode.
- Policy: deny rule `*envoyproxy/envoy*` in `runbooks/auto-update-policy.yaml`: the pin
  "moves only in the SAME change as the gateway-helm chart bump, to that release's
  DefaultEnvoyProxyImage — never on its own". For a MINOR this is upstream's own rule,
  not just ours (contrast the -v1.39.4 plan, a same-minor patch the matrix allows).

**Upstream evidence (Envoy `v1.40.0`, 2026-10-13, `changelogs/1.40.0.yaml` + release
notes).** 11 behavior_changes, 54 minor_behavior_changes, 28 removed_config_or_runtime,
6 deprecated, 139 new features, 156 bug fixes. "Breaking changes" in the release notes
are build-system (bzlmod, Clang 22, Wasm engine flag), AWS-LC removal, `mcp_router`
header forwarding and the Rust dynamic-module SDK — none of which EG v1.9.2 renders for
us. What does reach our runtime:
- `X25519MLKEM768` hybrid key exchange added to the DEFAULT ECDH curves for downstream
  and upstream TLS (revertible via `envoy.reloadable_features.pqc_default_ecdh_curves`).
  Every client handshake on .103/.104 changes ClientHello/ServerHello size; old or
  middlebox-y clients (IoT, TV apps, the Cloudflare edge in front of .104) are the risk.
- Container-aware CPU detection now on whenever `--concurrency` is unset. EG v1.9.2
  passes `--cpuset-threads` and no `--concurrency` (live args 2026-10-15), so worker
  count may change.
- Drain is event-driven. EG passes `--drain-strategy immediate --drain-time-s 60` and
  relies on its shutdown-manager; the interplay is untested upstream.
- Removed runtime guards incl. `http2 safe_http2_options` (HTTP/2 now always uses safe
  defaults), `websocket_allow_4xx_5xx_through_filter_chain`, `validate_upstream_headers`,
  `ext_authz_http_client_retries_respect_user_retry_on` (we run ext_authz on 12
  SecurityPolicies).
- `local_ratelimit` behavior change (shadow-mode descriptor short-circuit fixed): we run
  one local rate limit on envoy-external (BackendTrafficPolicy
  `my-software-production/the-ninth-banner-ai-generate`), non-shadow per the -v1.39.4 plan's
  measurement, so likely neutral — unverified here.
- EG v1.9.2's bootstrap static runtime layer sets `envoy.reloadable_features.oauth2_*`
  keys (live args); harmless as unknown runtime keys, but it shows the bootstrap is
  written for 1.39.

**Security.** Upstream lists 1.40.0's security content as "carries forward the 1.39.x
security fixes" — i.e. the fixes are already available inside the supported minor and
are delivered by the executable plan `envoy-proxy-config-distroless-v1.39.4`. There is
no security reason to lead the controller onto an untested minor. Detail: `F-61035b6e`.

**Registry facts (Docker Hub v2, 2026-10-15).** `distroless-v1.40.0` = index
`sha256:23b72ac1fa94908b2ca7ebf194cc6083cd0d4913210c7d7453e4b2008ca26c84`;
`distroless-v1.39.1` still `sha256:eb2c01c1…` (rollback target published and cached);
`distroless-v1.39.4` = `sha256:ccb37e93…`; `distroless-v1.39.5` was 404 on 2026-10-15 and has since been published (it is the current target of the `-v1.39.4` plan).

**Relation to the other envoy-proxy-config plans.** This plan does **NOT** supersede
`-v1.39.4` (file name kept; it now targets `distroless-v1.39.5`; the older `-v1.39.3` draft is gone). They are different lanes: `-v1.39.4` is the
executable same-minor patch that upstream's matrix permits and that carries the security
content; this one is a cross-minor move that cannot run until the controller moves. All
three edit the same pin line, so they are mutual `conflicts_with`. Recommended order:
run `-v1.39.4` (attended, operator decides its deny-rule departure as that plan says);
this plan waits for EG v1.10.x and is then superseded by the chart plan.

**UNBLOCK path (what turns this into work).** When `gh release list -R envoyproxy/gateway`
shows a v1.10.x whose compiled default is `distroless-v1.40.x`:
1. Write `envoy-gateway-<v1.10.x>` (chart `gateway-helm` in `helmrelease.yaml` line 23 +
   CRDs + this pin moved to THAT release's `DefaultEnvoyProxyImage` digest, one commit),
   following `docs/sops/envoy-gateway-upgrade.md`. Use §2–§5 below as its data-plane
   gates; note the compiled patch may be 1.40.1+, not 1.40.0 — pin what EG compiles.
2. Mark this file `status: superseded`, `superseded_by: envoy-gateway-<v1.10.x>`, and
   move `finding_refs: [F-10b4fee2]` to the chart plan in the same bookkeeping commit.
Expected timing (estimate, not a commitment): EG minors have shipped ~quarterly
(v1.9.0 2026-08-15), so v1.10.0 is plausibly mid/late November 2026.

## 2. Pre-checks (read-only, ~15 min) — only once §1 UNBLOCK holds

2.1 Premises: `.venv/bin/python3 runbooks/plan-premises.py envoy-proxy-config-distroless-v1.40.0`.
All must PASS. The block itself is the §1 UNBLOCK condition (no EG release compiles Envoy 1.40; check
by hand: `release/v1.10` of envoyproxy/gateway must exist and its `api/v1alpha1/shared_types.go`
`DefaultEnvoyProxyImage` must read `distroless-v1.40.x`); do not work around it.

2.2 Flux, workloads, PDBs (objects verified to exist 2026-10-15):
```bash
flux get kustomizations -n network | grep -E 'envoy-gateway'                 # Ready True
kubectl -n network get deploy envoy-gateway envoy-internal envoy-external    # all 3/3
kubectl -n network get pdb envoy-internal envoy-external                     # ALLOWED DISRUPTIONS 1 each
kubectl -n network get gateway                                               # both PROGRAMMED True, .103/.104
```

2.3 Target digest still what this plan pins:
```bash
T=$(curl -fsSL "https://auth.docker.io/token?service=registry.docker.io&scope=repository:envoyproxy/envoy:pull" | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
for t in distroless-v1.40.0 distroless-v1.39.1; do echo "$t $(curl -fsSI -H "Authorization: Bearer $T" -H 'Accept: application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json' https://registry-1.docker.io/v2/envoyproxy/envoy/manifests/$t | grep -i docker-content-digest | tr -d '\r')"; done
# measured 2026-10-15:
#   distroless-v1.40.0 docker-content-digest: sha256:23b72ac1fa94908b2ca7ebf194cc6083cd0d4913210c7d7453e4b2008ca26c84
#   distroless-v1.39.1 docker-content-digest: sha256:eb2c01c13125d1629637cb4e4cce7207009fb7cc2c8027f9742758549d15b6f4
```
FAIL/STOP: a different digest, an empty line, or a digest that differs from the EG
release's compiled default (then retarget to the compiled one).

2.4 Helpers + baselines. Shell state does not survive between agent Bash calls, so write
the helpers once and source them at the top of every later block. Each after-file is
`test -s`-guarded: an unsourced helper writes 0 lines and an unguarded diff passes vacuously.
```bash
mkdir -p /tmp/envoy140-win
cat > /tmp/envoy140-win/fns.sh <<'FNS'
W=/tmp/envoy140-win; cd "$W" || return 1
envver() { i=0; for p in $(kubectl -n network get pods -l app.kubernetes.io/component=proxy -o name); do
  port=$((19100+i)); i=$((i+1))
  kubectl -n network port-forward "$p" "$port":19000 >/dev/null 2>&1 & pf=$!; sleep 2
  v=$(curl -s --max-time 5 "http://localhost:$port/server_info" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['version'].split('/')[1], d['state'])" 2>/dev/null)
  kill $pf 2>/dev/null; echo "${p#pod/} ${v:-UNREADABLE}"; done; }
sweep() { test -s "$W/hosts.txt" || { echo "GUARD: hosts.txt missing" >&2; return 2; }
  while read -r h v; do printf '%s %s %s\n' "$v" "$(curl -sk -o /dev/null -w '%{http_code}' --max-time 8 --resolve "$h:443:$v" "https://$h/" </dev/null)" "$h"; done < "$W/hosts.txt"; }
changed() { b=$1; a=$2
  test -s "$b" && test -s "$a" || { echo "GUARD: empty input"; return 2; }
  [ "$(wc -l < "$b")" -eq "$(wc -l < "$a")" ] || { echo "GUARD: row count differs"; return 2; }
  awk '{print $3"|"$1, $2}' "$b" | sort > .kb; awk '{print $3"|"$1, $2}' "$a" | sort > .ka
  [ "$(join .kb .ka | wc -l)" -eq "$(wc -l < "$b")" ] || { echo "GUARD: join mismatch"; return 2; }
  join .kb .ka | awk '$2!=$3 {print "CHANGED", $1, $2, "->", $3; n++} END {print "CHECKED " NR " rows, CHANGED " n+0; exit (n>0)}'; }
pfprom() { curl -sf --max-time 3 http://localhost:19090/-/ready >/dev/null 2>&1 && return 0
  kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & echo $! > pf.pid
  for _ in 1 2 3 4 5 6 7 8 9 10; do sleep 1; curl -sf --max-time 3 http://localhost:19090/-/ready >/dev/null 2>&1 && return 0; done; return 2; }
pfstop() { [ -f pf.pid ] && kill "$(cat pf.pid)" 2>/dev/null; rm -f pf.pid; }
q() { pfprom || { echo PF_FAILED; return 2; }
  curl -s --get http://localhost:19090/api/v1/query --data-urlencode "query=$1" | python3 -c 'import sys,json;r=json.load(sys.stdin)["data"]["result"];print(" ".join(sorted(x["value"][1] for x in r)) if r else "EMPTY")' 2>/dev/null || echo QUERY_FAILED; }
FNS
. /tmp/envoy140-win/fns.sh
envver | tee ver.before
test -s ver.before && grep -c ' 1\.39\.1 LIVE$' ver.before          # must print 6 (live 2026-10-15: 6)
kubectl get httproute -A -o json | python3 -c '
import sys,json
vip={"envoy-internal":"192.168.55.103","envoy-external":"192.168.55.104"};seen=set()
for r in json.load(sys.stdin)["items"]:
  for p in r["spec"].get("parentRefs",[]):
    if p.get("sectionName")=="http" or p["name"] not in vip: continue
    for h in r["spec"].get("hostnames") or []:
      if (h,vip[p["name"]]) not in seen: seen.add((h,vip[p["name"]])); print(h,vip[p["name"]])' > hosts.txt
test -s hosts.txt && awk '{print $2}' hosts.txt | sort | uniq -c     # BOTH .103 and .104 must appear
sweep > status.before
test -s status.before && [ "$(wc -l < status.before)" -eq "$(wc -l < hosts.txt)" ] && echo BASELINE_ROWS_OK
for v in 192.168.55.103 192.168.55.104; do curl -sk -o /dev/null -w "$v %{http_code}\n" --max-time 8 --resolve "nohost-negative-control.invalid:443:$v" https://nohost-negative-control.invalid/; done   # must print 404 twice
q 'envoy_listener_manager_total_listeners_active{namespace="network"}'  # "4 4 4 4 4 4" (live 2026-10-15)
q 'sum(envoy_listener_manager_lds_update_rejected{namespace="network"})' # 0
q 'sum(envoy_cluster_manager_cds_update_rejected{namespace="network"})'  # 0
pfstop
```
Hostnames stay in `/tmp`, never committed. STOP on: any premise FAIL, `UNREADABLE`, missing
`BASELINE_ROWS_OK`, negative control not 404 twice, any `PF_FAILED`/`QUERY_FAILED`/`EMPTY`.

## 3. Steps (GitOps) — DO NOT EXECUTE while `status: blocked`

When unblocked, this edit belongs INSIDE the `envoy-gateway-<v1.10.x>` chart commit
(deny rule), not on its own. The pin edit, dry-tested 2026-10-15 on a scratch copy with
BSD sed (round-trip with the §5 sed returned the file byte-identical; YAML still parses
as `[GatewayClass, EnvoyProxy]`). Resulting diff:
```
-          image: docker.io/envoyproxy/envoy:distroless-v1.39.1@sha256:eb2c01c13125d1629637cb4e4cce7207009fb7cc2c8027f9742758549d15b6f4
+          image: docker.io/envoyproxy/envoy:distroless-v1.40.0@sha256:23b72ac1fa94908b2ca7ebf194cc6083cd0d4913210c7d7453e4b2008ca26c84
```
```bash
cd /Users/mu/code/cberg-home-nextgen
F=kubernetes/apps/network/envoy-gateway/app/gatewayclass.yaml
sed -i '' 's|envoyproxy/envoy:distroless-v1\.39\.1@sha256:eb2c01c13125d1629637cb4e4cce7207009fb7cc2c8027f9742758549d15b6f4$|envoyproxy/envoy:distroless-v1.40.0@sha256:23b72ac1fa94908b2ca7ebf194cc6083cd0d4913210c7d7453e4b2008ca26c84|' "$F"
grep -c 'distroless-v1.40.0@sha256:23b72ac1' "$F"     # must print 1 (0 = anchor moved, STOP)
# Substitute the EG release's compiled 1.40.x digest if it is not 1.40.0.
```
Commit with `git commit --only <chart files> "$F" -F <msg>`, then `git log -1 --format=%s`
(must be yours) and `git show --stat HEAD`, push, then
`flux reconcile source git flux-system -n flux-system` and
`flux reconcile kustomization envoy-gateway -n network` (the EnvoyProxy CR is applied by
that Kustomization). Watch `kubectl -n network rollout status deploy/envoy-internal` and
`deploy/envoy-external` (`--timeout=600s`); rollout status can go green on the OLD
generation, so §4.1 checks the pods themselves.

## 4. Verification

4.1 **CONTENTS ASSERTION: every proxy runs 1.40 and is LIVE.**
```bash
. /tmp/envoy140-win/fns.sh
kubectl -n network get pods -l app.kubernetes.io/component=proxy -o jsonpath='{range .items[*]}{range .status.containerStatuses[?(@.name=="envoy")]}{.imageID}{"\n"}{end}{end}' | sort | uniq -c   # 6 x ...@sha256:23b72ac1...
envver | tee ver.after
test -s ver.after && [ "$(wc -l < ver.after)" -eq 6 ] && grep -c ' 1\.40\.[0-9]* LIVE$' ver.after   # must print 6
```
Can fail: against today's pods the grep prints 0 (`ver.before` = 6 × `1.39.1 LIVE`).
FAIL shape: a `1.39.1` line, `UNREADABLE`, or state `PRE_INITIALIZING` (stuck before first config).

4.2 **CONTENTS ASSERTION: no listener silently missing, no xDS rejection** — the exact
failure mode the EG matrix warns about for a cross-minor pin (readiness passes while a
listener is gone). Wait 2 min after §3 so the new pods are scraped.
```bash
. /tmp/envoy140-win/fns.sh
q 'count(up{namespace="network",job="network/envoy-gateway"}==1)'        # 6
q 'envoy_listener_manager_total_listeners_active{namespace="network"}'   # "4 4 4 4 4 4"
q 'sum(envoy_listener_manager_lds_update_rejected{namespace="network"})' # 0
q 'count(envoy_listener_manager_lds_update_rejected{namespace="network"})' # 6 (non-vacuous)
q 'sum(envoy_cluster_manager_cds_update_rejected{namespace="network"})'  # 0
pfstop
```
- CONTROL: metric envoy_listener_manager_total_listeners_active — 4 per pod, live 2026-10-15 on all 6. A rejected LDS resource on a fresh pod leaves 3 (or fewer); the value is per-pod so one bad pod shows.
- CONTROL: metric envoy_listener_manager_lds_update_rejected — raw sum 0 over 6 series; raw counter, not `increase()`, which drops a new series' first sample and would miss rejection of the initial config.
- CONTROL: metric envoy_cluster_manager_cds_update_rejected — raw sum 0.
- CONTROL: metric up — 6.
`PF_FAILED`, `QUERY_FAILED` or `EMPTY` is a FAIL, never a pass.

4.3 **CONTENTS ASSERTION: behavioural probe of BOTH gateways** — real HTTPS through .103 and .104.
```bash
. /tmp/envoy140-win/fns.sh
sweep > status.after; test -s status.after && echo AFTER_NONEMPTY
sed '1s/^\([^ ]*\) [0-9]*/\1 000/' status.after > status.knownbad
changed status.before status.knownbad; echo "control rc=$?"   # must print one CHANGED ... -> 000 and "control rc=1"
changed status.before status.after;    echo "rc=$?"           # 0 clean; 1 = CHANGED rows; 2 = GUARD = FAIL
for v in 192.168.55.103 192.168.55.104; do echo | openssl s_client -connect $v:443 -servername nohost-negative-control.invalid 2>/dev/null | grep -iE '^(Protocol|Negotiated TLS1.3 group|Server Temp Key)'; done
```
PASS: `AFTER_NONEMPTY`, `control rc=1`, real rc 0 (or every CHANGED row back to baseline
on one re-probe after 60 s). FAIL: a pair stuck at `000` (TLS/listener), `404` (route
dropped; negative control proved Envoy 404s an unrouted host), `302 -> 5xx` (Authentik
forward-auth broken). The `openssl` line records the negotiated group (expect a change
toward the PQ hybrid on clients that offer it) — evidence, not a gate.

4.4 Soak 15 min, then: proxies `restartCount` all 0
(`kubectl -n network get pods -l app.kubernetes.io/component=proxy -o jsonpath='{range .items[*]}{.metadata.name} {range .status.containerStatuses[?(@.name=="envoy")]}{.restartCount}{end}{"\n"}{end}'`),
re-run 4.2 and 4.3, and confirm no `EnvoyGateway*`/`IngressProbeFailing` alert firing.
Ask the operator to open one LAN app and one public app from a phone (old-client TLS check).

## 5. Rollback

No forward-only step. 5.1: `git revert --no-edit <sha>` of the §3 commit (if that commit
also moved the chart, the revert moves both back — that is correct, they are coupled),
`git log -1 --format=%s` must be the Revert subject, push, reconcile as in §3, watch both
rollouts. Manual restore if the revert conflicts (dry-tested, round-trip byte-identical):
```bash
F=kubernetes/apps/network/envoy-gateway/app/gatewayclass.yaml
sed -i '' 's|envoyproxy/envoy:distroless-v1\.40\.0@sha256:23b72ac1fa94908b2ca7ebf194cc6083cd0d4913210c7d7453e4b2008ca26c84$|envoyproxy/envoy:distroless-v1.39.1@sha256:eb2c01c13125d1629637cb4e4cce7207009fb7cc2c8027f9742758549d15b6f4|' "$F"
grep -o 'envoy:distroless-v[^ ]*' "$F"   # envoy:distroless-v1.39.1@sha256:eb2c01c1...
```
5.2 Confirm: 4.1 with `1\.39\.1` (6 rows), 4.2 and 4.3 against the SAME `*.before` files.
5.3 Break-glass: Flux fetches from GitHub over cluster egress, not through Envoy, so a dark
data plane does not block 5.1. `kubectl -n network rollout undo deploy/envoy-*` is a
stopgap only (the controller re-renders from the EnvoyProxy CR); follow with 5.1 at once.

## 6. Interference notes

- **Blocked; window null.** Do not schedule. The window agent should skip it and the
  sweep should treat `F-10b4fee2` as owned (this file carries it).
- **Same-pin plans:** `-v1.39.4` (executable, recommended now; file name unchanged but it now targets
  `distroless-v1.39.5`) is in `conflicts_with`; the former `-v1.39.3` draft no longer exists. Reciprocity owed in the
  plan-bookkeeping commit: add `envoy-proxy-config-distroless-v1.40.0` to `-v1.39.4`'s
  `conflicts_with`. If `-v1.39.4` executes first, premise `repo-pin-is-1.39.1` fails here
  — expected; this plan will be superseded by the chart plan anyway.
- **When unblocked it becomes the chart plan's data-plane half.** Attended window only
  (shared `gateway/envoy`, public edge, Authentik ext_authz), the only routing-perturbing
  plan in its slot, run first after Step 0, never same-night as a kube-prometheus-stack
  bump (the §4.2 instrument) or a Talos node roll (single PDB disruption).
- **Traffic during the roll:** surge-first, PDB minAvailable 2, shutdown-manager drain
  (terminationGracePeriod 360 s): long-lived connections reconnect once per pod. Interruption, not data loss.
- **Not touched:** k8s-gateway, external-dns, cert-manager, the controller Deployment
  (in this plan; the chart plan will touch the controller).
