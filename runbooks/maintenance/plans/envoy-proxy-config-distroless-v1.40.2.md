---
plan_id: envoy-proxy-config-distroless-v1.40.2
component: envoy-proxy-config
also_covers:
  - docker.io/envoyproxy/envoy        # the Envoy DATA-PLANE image pinned in EnvoyProxy/network/envoy-proxy-config
supersedes: envoy-proxy-config-distroless-v1.40.0   # same blocked cross-minor move; that file's target (1.40.0) went stale.
                                      # Its file is NOT edited here (planner writes one file); bookkeeping owed, see §6.
pr: null                              # no Renovate PR for the pin: the `distroless-v` prefix is not docker-versionable
                                      # (gatewayclass.yaml comment). Surfaced by version-check-current.md row
                                      # "distroless-v1.39.1 -> distroless-v1.40.2 (minor)"; dispatched by sweep 8699f7d4 (rule 4d0).
                                      # The related chart PR #437 (gateway-helm 1.9.2 -> 1.9.3) is owned by
                                      # envoy-proxy-config-distroless-v1.39.4, NOT by this plan.
kind: image
current: "distroless-v1.39.1@sha256:eb2c01c13125d1629637cb4e4cce7207009fb7cc2c8027f9742758549d15b6f4"
target: "distroless-v1.40.2@sha256:09ca6f2140a61ad8df11779a4a30d52b48433d444466328494f9188c9c35eded"
update_type: minor
risk: high                            # cross-MINOR data plane under a controller (EG v1.9.x) that upstream has NOT tested
                                      # with Envoy 1.40; the documented failure mode is SILENT xDS rejection that surfaces
                                      # exactly on proxy restart, and this change restarts all 6 proxy pods of both gateways
                                      # (the only HTTP data plane: LAN .103 + public edge .104).
est_duration_min: 60                  # only meaningful once unblocked: §2 15 + §3 5 + rolls ~8 + §4 ~20 + soak 7 + slack 5
needs_reboot: false
exclusive: false
touches:
  namespaces: [network]
  resources:
    - envoyproxy/network/envoy-proxy-config                      # spec.provider.kubernetes.envoyDeployment.container.image
    - deployment/network/envoy-internal                          # ROLLS (3 pods, surge-first, PDB minAvailable 2)
    - deployment/network/envoy-external                          # ROLLS (3 pods, surge-first, PDB minAvailable 2)
    - kubernetes/apps/network/envoy-gateway/app/gatewayclass.yaml
  shared:
    - gateway/envoy                   # envoy-internal (.103) + envoy-external (.104) carry EVERY HTTPRoute
    - public-edge                     # envoy-external is the internet-facing data plane
    - authentik                       # SecurityPolicies (extAuth forward-auth) are enforced inside Envoy
    - monitoring                      # §4.2 reads Prometheus (listener + xDS-rejection metrics): the instrument
depends_on: []
  # The real prerequisite is an Envoy Gateway RELEASE that compiles Envoy 1.40.x (EG v1.10.x; none exists
  # 2026-10-29). No plan exists for it, so naming one would be a DEAD-REF. It is encoded instead as the
  # premise `controller-is-1.10-or-newer` (fails today, by design) and as the §1 UNBLOCK condition.
conflicts_with:                       # each re-checked 2026-10-29 as an existing, non-terminal plan file
  # 2026-11-03: removed dead ref envoy-proxy-config-distroless-v1.39.4 (no plan file; its change shipped as chart 1.9.3 + distroless-v1.39.5, reviewer finding)
  - envoy-proxy-config-distroless-v1.40.0   # SAME pin line (blocked; superseded by this file, retire in bookkeeping)
  - talos-linux-1.14.4                # node drain competes for the single PDB disruption per gateway
  - etcd-timeouts-5000-500            # apiserver restarts confound the roll + §4 gates
  - flux-oci-chart-sources            # moves Flux sources; same §3/§5 apply-and-revert path
  - flux-reconciler-impersonation     # rewrites how kustomize-controller applies this (blocked)
  # 2026-11-03: removed dead ref authentik-2026.8.5 (no plan file; Authentik forward-auth path is still exercised by §4.3)
  - authentik-web-max-requests        # same path
capability_change: true               # A new Envoy MINOR changes behaviour, not just the binary: X25519MLKEM768 joins
                                      # the DEFAULT ECDH curves on every downstream/upstream TLS handshake, container-aware
                                      # CPU detection changes worker-count semantics, drain becomes event-driven, and 28
                                      # runtime guards / legacy paths are removed (1.40.0 changelog). Not a same-behaviour bump.
rollback_class: git-revert            # no CRD, no state, no migration; the 1.39.x image is digest-pinned, still published
                                      # (re-resolved 2026-10-29) and cached on all 3 nodes.
autonomy_override: human-gated        # shared gateway/envoy derives HUMAN-GATED anyway; attended window only.
security_ref: F-61035b6e              # 1.40.1/1.40.2 security content is ALSO shipped on the supported 1.39 line
                                      # (distroless-v1.39.6), so there is no security reason to leave the tested minor.
                                      # Detail stays on the DB record.
finding_refs: [F-10b4fee2]            # version row "distroless-v1.39.1 -> distroless-v1.40.2 (minor)", cycle 8699f7d4.
                                      # Also carried by -v1.40.0 (blocked) and -v1.39.4 until the bookkeeping in §6.
review: null
status: blocked   # BLOCKED 2026-10-29 (planner, sweep 8699f7d4): no Envoy Gateway release compiles or supports Envoy 1.40. EG releases: v1.9.3 (Latest, 2026-10-26) compiles distroless-v1.39.5; release/v1.9 head = distroless-v1.39.5; main = distroless-dev; no release/v1.10 branch. EG matrix: "Each Envoy Gateway release ships with, and is tested against, a single Envoy Proxy minor version" (v1.9 <-> distroless-v1.39.x). Deny rule *envoyproxy/envoy* forbids moving this pin outside the gateway-helm chart bump. UNBLOCK = an EG v1.10.x release whose DefaultEnvoyProxyImage is distroless-v1.40.x; then this becomes the data-plane half of an envoy-gateway-<v1.10.x> chart plan (§1, §6).
window: null
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/envoy-gateway-upgrade.md
  - docs/sops/gateway-api-httproute.md
  - docs/sops/vulnerability-disclosure.md
generated: "2026-10-29"
premises:
  - id: controller-is-1.10-or-newer
    why: "THE BLOCK, machine-checked. Envoy 1.40 is only supported under an EG release that compiles it (v1.10.x). Live chart is 1.9.2 (2026-10-29), so this premise FAILS today by design. When it passes, also confirm by hand that the release's DefaultEnvoyProxyImage is distroless-v1.40.x and retarget to that digest (§2.1)."
    run: kubectl get helmrelease envoy-gateway -n network -o jsonpath='{.spec.chart.spec.version}'
    expect_matches: '^1\.1[0-9]\.\d+$'
  - id: repo-pin-is-1.39.x
    why: "§3's sed is anchored on any 1.39.x digest pin (1.39.1 today, 1.39.5/1.39.6 after the -v1.39.4 plan). Any other value means the pin moved by another path; re-plan."
    run: grep -o 'envoy:distroless-v[^@]*' kubernetes/apps/network/envoy-gateway/app/gatewayclass.yaml
    expect_matches: '^envoy:distroless-v1\.39\.\d+$'
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

# envoy-proxy-config: Envoy data plane distroless-v1.39.1 -> distroless-v1.40.2 (BLOCKED)

## 1. Summary & why held

**Verdict: correctly held, NOT executable today. `status: blocked`.** The hold is not a
false positive. This file owns the held 1.40.2 target (it supersedes the stale
`-v1.40.0` file, whose target 1.40.0 is now two patches behind) and records the unblock
condition and the gates a cross-minor move needs.

**Does the deployed Envoy Gateway support 1.40.x? No. Must the two move in lockstep? Yes.**
Measured 2026-10-29:
- Live: HelmRelease `network/envoy-gateway` chart `1.9.2`, Ready=True; `deploy/envoy-gateway`
  3/3; EnvoyProxy pin `distroless-v1.39.1@sha256:eb2c01c1…`; all 6 `envoy` containers on
  imageID `sha256:eb2c01c1…`, 0 restarts; both Gateways Programmed=True.
- EG releases (`gh release list -R envoyproxy/gateway`): `v1.9.3` (Latest, 2026-10-26),
  `v1.8.6`, `v1.9.2`, … No v1.10.x, no rc, no `release/v1.10` branch.
- Compiled defaults (`api/v1alpha1/shared_types.go`, `DefaultEnvoyProxyImage`):
  `v1.9.2` = `distroless-v1.39.1@sha256:eb2c01c1…` (= our pin);
  `v1.9.3` = `distroless-v1.39.5@sha256:9d84a586…`; `release/v1.9` head = the same 1.39.5;
  `main` = `distroless-dev`. No EG ref pins 1.40.
- EG compatibility matrix (`site/content/en/news/releases/matrix.md`, main), verbatim:
  "Each Envoy Gateway release ships with, and is tested against, a single Envoy Proxy minor
  version. … Compatibility with older or newer Envoy Proxy minor versions has not been
  tested and is unknown." Row `v1.9 | distroless-v1.39.x`. And: "If the pinned image is a
  different Envoy Proxy minor version than the one listed above, the combination is
  untested, and Envoy Gateway may generate configuration that the proxy rejects."
- Policy: deny rule `*envoyproxy/envoy*` (`runbooks/auto-update-policy.yaml`): the pin
  "moves only in the SAME change as the gateway-helm chart bump, to that release's
  DefaultEnvoyProxyImage — never on its own". Upstream's matrix makes that rule mandatory
  for a MINOR.

**The two halves (what the sweep asked for):**
1. **Today's lockstep pair is chart `gateway-helm` 1.9.3 (PR #437) + pin
   `distroless-v1.39.5`.** That is not this plan: it is already owned by the vetted plan
   `envoy-proxy-config-distroless-v1.39.4` (target "chart gateway-helm 1.9.3 + data plane
   distroless-v1.39.5", one commit, HUMAN-GATED, window pending operator choice). PR #437
   must NOT be merged on its own: the pin outranks the chart's compiled default, so a
   chart-only merge moves the controller and shutdown-manager sidecar but leaves the data
   plane on 1.39.1, and still rolls all proxies once (sidecar image). Leave #437 to that plan.
2. **The 1.40 move is the data-plane half of a FUTURE `envoy-gateway-<v1.10.x>` chart
   plan** — chart + CRDs + this pin moved to v1.10.x's `DefaultEnvoyProxyImage`, one
   commit, per `docs/sops/envoy-gateway-upgrade.md`. §2–§5 below are that half's gates.

**Upstream evidence for the target.**
- `v1.40.0` (2026-10-13): 11 behavior_changes, 54 minor_behavior_changes, 28
  removed_config_or_runtime. What reaches our runtime: post-quantum `X25519MLKEM768`
  added to the DEFAULT ECDH curves (downstream and upstream TLS; every client handshake on
  .103/.104 changes — IoT/TV clients and the Cloudflare edge in front of .104 are the
  risk); container-aware CPU detection when `--concurrency` is unset (EG passes
  `--cpuset-threads`, no `--concurrency`); event-driven drain vs EG's
  `--drain-strategy immediate` + shutdown-manager; removed guards incl. HTTP/2 safe
  options, websocket 4xx/5xx passthrough, `validate_upstream_headers`,
  `ext_authz_http_client_retries_respect_user_retry_on` (we run extAuth on the Authentik
  SecurityPolicies).
- `v1.40.1` (2026-10-23): "Upstream security fixes" — release images no longer trust the
  compromised eMudhra intermediate CAs; one contrib/istio behaviour change (unused here).
- `v1.40.2` (2026-10-27), verbatim: "updated the `distroless` docker image base to pick up
  the patched `ca-certificates` package (`20250419+deb13u1`) … The distroless image
  released in 1.40.1 still shipped the unpatched bundle."
- The SAME fix shipped on the supported minor as `v1.39.6` (2026-10-27), verbatim: "The
  distroless image released in 1.39.5 still shipped the unpatched bundle." So the
  security content of 1.40.2 is available without leaving 1.39 — no reason to lead the
  controller onto an untested minor. Detail on `F-61035b6e`.

**Registry facts (Docker Hub v2 HEAD, 2026-10-29).** `distroless-v1.40.2` =
`sha256:09ca6f2140a61ad8df11779a4a30d52b48433d444466328494f9188c9c35eded`;
`distroless-v1.40.1` = `sha256:6cf31425…`; `distroless-v1.39.6` = `sha256:1cac8b3a…`;
`distroless-v1.39.5` = `sha256:9d84a586…` (= EG v1.9.3 default);
`distroless-v1.39.1` = `sha256:eb2c01c1…` (rollback target, still published).

**UNBLOCK path.** When `gh release list -R envoyproxy/gateway` shows a v1.10.x whose
compiled default is `distroless-v1.40.x`:
1. Write `envoy-gateway-<v1.10.x>` (chart in `helmrelease.yaml`, CRD re-vendor, and this
   pin moved to THAT release's `DefaultEnvoyProxyImage` digest — which may be 1.40.3+,
   not 1.40.2; pin what EG compiles). Use §2–§5 here as its data-plane gates.
2. Mark this file `status: superseded`, `superseded_by: envoy-gateway-<v1.10.x>`, and move
   `finding_refs: [F-10b4fee2]` to the chart plan in the same bookkeeping commit.
Expected timing (estimate): EG minors ship ~quarterly (v1.9.0 2026-08-15), so v1.10.0 is
plausibly mid/late November 2026. Matrix lists v1.9 EOL 2027/02/14.

## 2. Pre-checks (read-only, ~15 min) — only once §1 UNBLOCK holds

2.1 Premises: `.venv/bin/python3 runbooks/plan-premises.py envoy-proxy-config-distroless-v1.40.2`.
All must PASS — `controller-is-1.10-or-newer` fails today and IS the block; do not work
around it. By hand: the live EG release's `api/v1alpha1/shared_types.go` must read
`distroless-v1.40.x`:
```bash
V=$(kubectl get helmrelease envoy-gateway -n network -o jsonpath='{.spec.chart.spec.version}')
gh api "repos/envoyproxy/gateway/contents/api/v1alpha1/shared_types.go?ref=v$V" --jq .content | base64 -d | grep -n 'DefaultEnvoyProxyImage[[:space:]]*='
# measured 2026-10-29 for v1.9.2: distroless-v1.39.1@sha256:eb2c01c1...  -> STOP (not 1.40)
```
If the compiled digest is not `09ca6f21…`, retarget §3 to the compiled tag+digest.

2.2 Flux, workloads, PDBs (all objects verified to exist 2026-10-29):
```bash
flux get kustomizations -n network | grep envoy-gateway                      # Ready True
kubectl get deploy envoy-gateway envoy-internal envoy-external -n network    # all 3/3 (live 2026-10-29)
kubectl get pdb envoy-internal envoy-external envoy-gateway -n network       # ALLOWED DISRUPTIONS 1 each (live)
kubectl get gateway -n network                                               # both PROGRAMMED True
```

2.3 Target digest unchanged:
```bash
T=$(curl -fsSL "https://auth.docker.io/token?service=registry.docker.io&scope=repository:envoyproxy/envoy:pull" | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
for t in distroless-v1.40.2 distroless-v1.39.1; do echo "$t $(curl -fsSI -H "Authorization: Bearer $T" -H 'Accept: application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json' https://registry-1.docker.io/v2/envoyproxy/envoy/manifests/$t | grep -i docker-content-digest | tr -d '\r')"; done
# measured 2026-10-29:
#   distroless-v1.40.2 docker-content-digest: sha256:09ca6f2140a61ad8df11779a4a30d52b48433d444466328494f9188c9c35eded
#   distroless-v1.39.1 docker-content-digest: sha256:eb2c01c13125d1629637cb4e4cce7207009fb7cc2c8027f9742758549d15b6f4
```
FAIL/STOP: different digest, empty line, or a digest differing from the EG compiled default.

2.4 Helpers + baselines (write once, source at the top of every later block; every
after-file is `test -s`-guarded so an unsourced helper cannot pass vacuously):
```bash
mkdir -p /tmp/envoy1402-win
cat > /tmp/envoy1402-win/fns.sh <<'FNS'
W=/tmp/envoy1402-win; cd "$W" || return 1
envver() { i=0; for p in $(kubectl get pods -n network -l app.kubernetes.io/component=proxy -o name); do
  port=$((19100+i)); i=$((i+1))
  kubectl port-forward -n network "$p" "$port":19000 >/dev/null 2>&1 & pf=$!; sleep 2
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
. /tmp/envoy1402-win/fns.sh
envver | tee ver.before
test -s ver.before && grep -c ' 1\.39\.[0-9]* LIVE$' ver.before      # must print 6
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
q 'envoy_listener_manager_total_listeners_active{namespace="network"}'   # "4 4 4 4 4 4" (live 2026-10-29)
q 'sum(envoy_listener_manager_lds_update_rejected{namespace="network"})' # 0 (live 2026-10-29)
q 'sum(envoy_cluster_manager_cds_update_rejected{namespace="network"})'  # 0 (live 2026-10-29)
pfstop
```
Hostnames stay in `/tmp`, never committed. STOP on: any premise FAIL, `UNREADABLE`,
missing `BASELINE_ROWS_OK`, negative control not 404 twice, any `PF_FAILED`/`QUERY_FAILED`/`EMPTY`.

## 3. Steps (GitOps) — DO NOT EXECUTE while `status: blocked`

When unblocked, this edit goes INSIDE the `envoy-gateway-<v1.10.x>` chart commit (deny
rule), never alone. Pin edit, dry-tested 2026-10-29 with BSD sed on a scratch copy of the
live file: exactly one line changes, YAML still parses as `[GatewayClass, EnvoyProxy]`,
the anchor also matches a 1.39.5 pre-state, and the §5 restore sed round-trips the file
byte-identical. Resulting diff (from today's pre-state):
```
-          image: docker.io/envoyproxy/envoy:distroless-v1.39.1@sha256:eb2c01c13125d1629637cb4e4cce7207009fb7cc2c8027f9742758549d15b6f4
+          image: docker.io/envoyproxy/envoy:distroless-v1.40.2@sha256:09ca6f2140a61ad8df11779a4a30d52b48433d444466328494f9188c9c35eded
```
```bash
cd /Users/mu/code/cberg-home-nextgen
F=kubernetes/apps/network/envoy-gateway/app/gatewayclass.yaml
grep -o 'envoy:distroless-v[^ ]*' "$F" | tee /tmp/envoy1402-win/pin.before   # record the exact pre-state for §5
sed -i '' 's|envoyproxy/envoy:distroless-v1\.39\.[0-9]*@sha256:[0-9a-f]\{64\}$|envoyproxy/envoy:distroless-v1.40.2@sha256:09ca6f2140a61ad8df11779a4a30d52b48433d444466328494f9188c9c35eded|' "$F"
grep -c 'distroless-v1.40.2@sha256:09ca6f21' "$F"     # must print 1 (0 = anchor moved, STOP)
# Substitute the EG release's compiled 1.40.x tag+digest if it is not 1.40.2.
```
Also update the `COUPLED TO THE CONTROLLER` comment block above the pin only if the chart
plan changes its meaning (it should not). Commit with
`git commit --only <chart files> "$F" -F <msg>`, then `git log -1 --format=%s` (must be
yours) and `git show --stat HEAD`, push. Per `docs/sops/envoy-gateway-upgrade.md` step 5
("reconcile **Kustomization then HelmRelease**"):
`flux reconcile kustomization envoy-gateway -n network --with-source` (applies the EnvoyProxy
CR), then `flux reconcile helmrelease envoy-gateway -n network` (the chart half). Watch
`kubectl rollout status deploy/envoy-internal -n network --timeout=600s` and the same for
`deploy/envoy-external`; rollout status can go green on the OLD generation, so §4.1
checks the pods themselves.

## 4. Verification

4.1 **CONTENTS ASSERTION: every proxy runs 1.40 and is LIVE.**
```bash
. /tmp/envoy1402-win/fns.sh
kubectl get pods -n network -l app.kubernetes.io/component=proxy -o jsonpath='{range .items[*]}{range .status.containerStatuses[?(@.name=="envoy")]}{.imageID}{"\n"}{end}{end}' | sort | uniq -c   # 6 x ...@sha256:09ca6f21...
envver | tee ver.after
test -s ver.after && [ "$(wc -l < ver.after)" -eq 6 ] && grep -c ' 1\.40\.[0-9]* LIVE$' ver.after   # must print 6
```
Can fail: against today's pods the grep prints 0 (all six report `1.39.1 LIVE`). FAIL
shape: a `1.39.x` line, `UNREADABLE`, or state `PRE_INITIALIZING` (stuck before first config).

4.2 **CONTENTS ASSERTION: no listener silently missing, no xDS rejection** — the exact
failure mode the EG matrix names for a cross-minor pin (readiness passes while a listener
is gone). Wait 2 min after §3 so the new pods are scraped.
```bash
. /tmp/envoy1402-win/fns.sh
q 'count(up{namespace="network",job="network/envoy-gateway"}==1)'          # 6
q 'envoy_listener_manager_total_listeners_active{namespace="network"}'     # "4 4 4 4 4 4"
q 'sum(envoy_listener_manager_lds_update_rejected{namespace="network"})'   # 0
q 'count(envoy_listener_manager_lds_update_rejected{namespace="network"})' # 6 (non-vacuous)
q 'sum(envoy_cluster_manager_cds_update_rejected{namespace="network"})'    # 0
pfstop
```
- CONTROL: metric envoy_listener_manager_total_listeners_active — 4 per pod on all 6, live 2026-10-29. A rejected LDS resource on a fresh pod leaves 3 or fewer; per-pod values, so one bad pod shows.
- CONTROL: metric envoy_listener_manager_lds_update_rejected — raw sum 0 over 6 series (count 6 live 2026-10-29); raw counter, not `increase()`, which drops a new series' first sample and would miss rejection of the initial config.
- CONTROL: metric envoy_cluster_manager_cds_update_rejected — raw sum 0.
- CONTROL: metric up — 6 (live 2026-10-29).
`PF_FAILED`, `QUERY_FAILED` or `EMPTY` is a FAIL, never a pass.

4.3 **CONTENTS ASSERTION: behavioural probe of BOTH gateways** — real HTTPS through every
routed hostname on .103 and .104, compared row-by-row with the §2.4 baseline.
```bash
. /tmp/envoy1402-win/fns.sh
sweep > status.after; test -s status.after && echo AFTER_NONEMPTY
sed '1s/^\([^ ]*\) [0-9]*/\1 000/' status.after > status.knownbad
changed status.before status.knownbad; echo "control rc=$?"   # must print one CHANGED ... -> 000 and "control rc=1"
changed status.before status.after;    echo "rc=$?"           # 0 clean; 1 = CHANGED rows; 2 = GUARD = FAIL
for v in 192.168.55.103 192.168.55.104; do echo | openssl s_client -connect $v:443 -servername nohost-negative-control.invalid 2>/dev/null | grep -i -e '^Protocol' -e 'Negotiated TLS1.3 group' -e 'Server Temp Key'; done
```
PASS: `AFTER_NONEMPTY`, `control rc=1`, real rc 0 (or every CHANGED row back to baseline
on one re-probe after 60 s). FAIL: a pair stuck at `000` (TLS/listener), `404` (route
dropped — the negative control proves Envoy answers 404 for an unrouted host), `302`
turned `5xx` (Authentik forward-auth broken). The `openssl` line records the negotiated
group (a PQ hybrid group is expected for clients that offer it) — evidence, not a gate.

4.4 Soak 15 min, then: proxy `restartCount` all 0
(`kubectl get pods -n network -l app.kubernetes.io/component=proxy -o jsonpath='{range .items[*]}{.metadata.name} {range .status.containerStatuses[?(@.name=="envoy")]}{.restartCount}{end}{"\n"}{end}'`),
re-run 4.2 and 4.3, and confirm no `EnvoyGateway*` / `IngressProbeFailing` alert firing.
Operator opens one LAN app and one public app from a phone (old-client TLS check).

## 5. Rollback

No forward-only step. 5.1: `git revert --no-edit <sha>` of the §3 commit (if that commit
also moved the chart, the revert moves both back — correct, they are coupled);
`git log -1 --format=%s` must be the Revert subject; push; reconcile as in §3; watch both
rollouts. Manual restore if the revert conflicts (dry-tested 2026-10-29 for a 1.39.1
pre-state, round-trip byte-identical; substitute the line in `/tmp/envoy1402-win/pin.before`
if the pre-state was another 1.39.x):
```bash
F=kubernetes/apps/network/envoy-gateway/app/gatewayclass.yaml
sed -i '' 's|envoyproxy/envoy:distroless-v1\.40\.2@sha256:09ca6f2140a61ad8df11779a4a30d52b48433d444466328494f9188c9c35eded$|envoyproxy/envoy:distroless-v1.39.1@sha256:eb2c01c13125d1629637cb4e4cce7207009fb7cc2c8027f9742758549d15b6f4|' "$F"
grep -o 'envoy:distroless-v[^ ]*' "$F"   # must equal /tmp/envoy1402-win/pin.before
```
5.2 Confirm: 4.1 with `1\.39\.[0-9]*` (6 rows), 4.2 and 4.3 against the SAME `*.before` files.
5.3 Break-glass: Flux fetches from GitHub over cluster egress, not through Envoy, so a dark
data plane does not block 5.1. `kubectl rollout undo` on the proxy Deployments is NOT a fix
(the controller re-renders from the EnvoyProxy CR); use 5.1.

## 6. Interference notes

- **Blocked; window null.** Do not schedule. The window agent skips it; `F-10b4fee2` is owned.
- **Do not merge PR #437 standalone.** It belongs to `envoy-proxy-config-distroless-v1.39.4`
  (chart 1.9.3 + pin 1.39.5 in one commit). A standalone merge rolls every proxy (new
  shutdown-manager sidecar) while leaving the data plane on 1.39.1, and makes that plan's
  `controller-is-1.9.2` premise fail.
- **Correction owed to `-v1.39.4` (not edited here):** its target `distroless-v1.39.5` is
  the EG v1.9.3 compiled default, but upstream `v1.39.6` notes say "The distroless image
  released in 1.39.5 still shipped the unpatched bundle" — the CA trust-store fix that plan
  cites as the 1.39.5 security delta only reaches the distroless image in 1.39.6. The
  plan's owner/operator should decide: keep 1.39.5 (strict "compiled default" reading of
  the deny rule) or pin 1.39.6 (same minor, matrix-permitted patch above the default).
- **Bookkeeping owed (one commit, not done by this planner):** mark
  `envoy-proxy-config-distroless-v1.40.0` `status: superseded`,
  `superseded_by: envoy-proxy-config-distroless-v1.40.2`; replace that id with this one in
  the `conflicts_with` of `envoy-proxy-config-distroless-v1.39.4`, `authentik-2026.8.5`,
  `n8n-2.39.8`, `redis-fleet-8.10.2`, `redis-fleet-8.10.3` (or keep both ids until the old
  file is retired); add this id to the `conflicts_with` of every plan listed in this
  file's `conflicts_with` (reciprocity; `--validate` does not check it). Per the plans
  README, refreshing `-v1.40.0` in place would have avoided this churn — the dispatch named
  a new file id.
- **When unblocked it becomes the chart plan's data-plane half.** Attended window only
  (shared `gateway/envoy`, public edge, Authentik extAuth), the only routing-perturbing plan
  in its slot, run first after Step 0, never same-night as a kube-prometheus-stack bump
  (the §4.2 instrument), a Talos node roll (single PDB disruption) or etcd restarts.
- **Traffic during the roll:** surge-first, PDB minAvailable 2, shutdown-manager drain:
  long-lived connections reconnect once per pod. Interruption, not data loss.
- **Not touched:** k8s-gateway, external-dns, cert-manager, the controller Deployment (the
  chart plan touches the controller).
