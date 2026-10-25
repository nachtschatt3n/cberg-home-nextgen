---
plan_id: envoy-proxy-config-distroless-v1.39.4
component: envoy-proxy-config
also_covers:
  - docker.io/envoyproxy/envoy        # the Envoy DATA-PLANE image pinned in EnvoyProxy/network/envoy-proxy-config
supersedes: envoy-proxy-config-distroless-v1.39.3   # chain: -v1.39.2 -> -v1.39.3 -> this plan (both earlier drafts retired/superseded)
refreshed: "2026-10-23"               # RETARGETED 1.39.4 -> 1.39.5 in place (upstream v1.39.5 published 2026-10-23T00:59Z).
                                      # The plan_id/file name KEEP "-v1.39.4" deliberately: other plans and the 1.40.0 plan
                                      # reference this id in conflicts_with; the TARGET in `target:` is authoritative.
pr: null                              # no Renovate PR: the `distroless-v` prefix is not docker-versionable
                                      # (gatewayclass.yaml comment). Surfaced by version-check-current.md row
                                      # "distroless-v1.39.1 -> distroless-v1.39.4" (now .5); dispatched by sweep cycle ee022565.
kind: image
current: "distroless-v1.39.1@sha256:eb2c01c13125d1629637cb4e4cce7207009fb7cc2c8027f9742758549d15b6f4"
target: "distroless-v1.39.5@sha256:9d84a586119a27b50437dbb01eccd4722832741539b1ed53c8e9d6da6067a6e0"
update_type: patch
risk: medium                          # low PROBABILITY (same Envoy minor as the compiled default; the 1.39.5
                                      # delta is a CA trust-store fix + dep bumps, no source/ change; the carried
                                      # 1.39.4 delta is seven thread-affinity race fixes) but total IMPACT: this image IS the only HTTP data
                                      # plane; the bump rolls all 6 proxy pods of envoy-internal + envoy-external.
est_duration_min: 55                  # §2 15 + §3 5 + rolls ~8 + §4 (10m metric wait + sweeps + filtmap) ~17 + soak 7 + slack 3
needs_reboot: false
exclusive: false
touches:
  namespaces: [network]
  resources:
    - envoyproxy/network/envoy-proxy-config                      # spec.provider.kubernetes.envoyDeployment.container.image
    - deployment/network/envoy-internal                          # ROLLS: envoy container 1.39.1 -> 1.39.5 (3 pods, surge-first)
    - deployment/network/envoy-external                          # ROLLS: envoy container 1.39.1 -> 1.39.5 (3 pods, surge-first)
    - kubernetes/apps/network/envoy-gateway/app/gatewayclass.yaml
  shared:
    - gateway/envoy                   # envoy-internal (.103) + envoy-external (.104) carry EVERY
                                      # HTTPRoute (95 routes / 80 host-VIP pairs, re-measured 2026-10-13)
    - public-edge                     # envoy-external is the internet-facing data plane
    - authentik                       # 12 SecurityPolicies (extAuth forward-auth) are enforced inside Envoy
    - monitoring                      # §2.7/§4.4 read Prometheus + blackbox probe_success (the instrument)
depends_on: []
  # The controller coupling is a premise (`controller-is-1.9.2`), not a plan dependency:
  # envoy-gateway-1.9.2 executed and was retired in 418faa1e; chart 1.9.2 re-measured live 2026-10-13.
conflicts_with:                       # every id re-checked as an existing, non-terminal plan file 2026-10-23;
  # 2026-10-25: pruned dead refs penpot-chart-1.10.0, external-dns-1.23.0 (executed/retired)
                                      # reasons in §6. DROPPED 2026-10-23 (no such plan file any more):
                                      # jellyfin-12.2.20261005, open-webui-17.0.0, coredns-1.48.2,
                                      # flux-fleet-0.60.0, kube-prometheus-stack-92.2.0.
  - authentik-2026.8.5                # reciprocal: names this plan; Authentik ext-auth path is exercised by §4
  - authentik-web-max-requests        # reciprocal: names this plan; same path
  - n8n-2.39.8                        # reciprocal: names this plan (status executed; kept for the reciprocity check)
  - envoy-proxy-config-distroless-v1.40.0   # SAME pin line (blocked); two plans moving one pin never share a window
  - talos-linux-1.14.2                # node drain competes for the single PDB disruption
  - talos-linux-1.14.4                # same
  - flux-reconciler-impersonation     # exclusive; rewrites how kustomize-controller applies this
  - flux-oci-chart-sources            # moves Flux sources; same §3/§5 apply-and-revert path
capability_change: false              # same-behaviour patch: no new route, permission, API surface or
                                      # exposure; the EnvoyProxy object only changes its image string.
rollback_class: git-revert            # the old image is digest-pinned, still published (re-resolved
                                      # 2026-10-13) and cached on all 3 nodes; no CRD, no state, no
                                      # migration. §5 is a one-line digest restore.
autonomy_override: human-gated        # shared `gateway` derives HUMAN-GATED via SHARED_INFRA_FLOOR anyway;
                                      # attended window only.
security_ref: F-61035b6e              # the 1.39.5 delta IS security-labelled upstream (release image CA trust-store update, in
                                      # addition to the 1.39.2/1.39.3 chain's items). Detail stays on the DB record.
finding_refs: [F-4a6327dd, F-61035b6e]  # version row for this pin (re-opens with the 1.39.5 title) + the planner-raised plan row.
                                      # F-df39740f (inert compression) is cited in §1/§2.3b but NOT owned here.
review: ready-for-go@2026-10-23
status: vetted
window: null                          # KEEP: sun-attended:2026-11-08 (operator 2026-10-23), first, before nocodb-2026.09.1
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/envoy-gateway-upgrade.md
  - docs/sops/gateway-api-httproute.md
  - docs/sops/vulnerability-disclosure.md
generated: "2026-10-13"
premises:
  - id: controller-is-1.9.2
    why: "The data plane moves only on top of the CURRENT controller (EG v1.9.2 compiles distroless-v1.39.1, same MINOR as the target). Any other chart version means the controller moved since this plan was written; re-check §1 compatibility before proceeding."
    run: kubectl get helmrelease envoy-gateway -n network -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: "1.9.2"
  - id: envoy-gateway-hr-ready
    why: "Do not move the data plane under a failing controller; it renders the proxy Deployments."
    run: kubectl get helmrelease envoy-gateway -n network -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: repo-pin-is-1.39.1
    why: "current: claims the 1.39.1 digest pin. If someone already moved it (e.g. an earlier draft of this chain ran), §3.1's sed matches nothing and §5's restore target is wrong."
    run: grep -o 'envoy:distroless-v[^ ]*' kubernetes/apps/network/envoy-gateway/app/gatewayclass.yaml
    expect_exact: "envoy:distroless-v1.39.1@sha256:eb2c01c13125d1629637cb4e4cce7207009fb7cc2c8027f9742758549d15b6f4"
  - id: live-envoyproxy-pin-is-1.39.1
    why: "Git and cluster must agree before the edit, or the roll is not caused by this change."
    run: kubectl get envoyproxy envoy-proxy-config -n network -o jsonpath='{.spec.provider.kubernetes.envoyDeployment.container.image}'
    expect_exact: "docker.io/envoyproxy/envoy:distroless-v1.39.1@sha256:eb2c01c13125d1629637cb4e4cce7207009fb7cc2c8027f9742758549d15b6f4"
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

# envoy-proxy-config: Envoy data plane distroless-v1.39.1 -> distroless-v1.39.5

## 1. Summary & why held

**Refresh 2026-10-23: target moved 1.39.4 -> 1.39.5.** Upstream published v1.39.5 at
2026-10-23T00:59Z, 10 days after this plan's 1.39.4 draft. Executing 1.39.4 would put all
6 proxy pods on a patch that is already one release behind, and cost a second full roll.
Same image, same Envoy MINOR, same controller (EG 1.9.2, still the newest 1.9.x), same
procedure; what changed is the digest and the upstream delta (below). Operator
2026-10-23: keep the window `sun-attended:2026-11-08`; the deny-rule departure stays an
explicit operator decision at the GO (§6). The chain `-v1.39.2 -> -v1.39.3 -> this plan`
is bookkeeping-complete: the earlier drafts no longer exist or are `superseded`.

**What changes.** One line in `kubernetes/apps/network/envoy-gateway/app/gatewayclass.yaml`:
the `EnvoyProxy/network/envoy-proxy-config` container image, digest-pinned, moves from
`docker.io/envoyproxy/envoy:distroless-v1.39.1@sha256:eb2c01c1…` to
`docker.io/envoyproxy/envoy:distroless-v1.39.5@sha256:9d84a586119a27b50437dbb01eccd4722832741539b1ed53c8e9d6da6067a6e0`.
The Envoy Gateway controller re-renders both proxy Deployments (`envoy-internal`,
`envoy-external`) and they roll, 3 pods each. Nothing else moves: no chart, no CRD, no
controller, no shutdown-manager sidecar, no k8s-gateway restart.

**Why held.** `runbooks/auto-update-policy.yaml` rule `*envoyproxy/envoy*`: the Envoy
data-plane image is coupled to the controller and is the only HTTP data plane in the
cluster.

**Compatibility with the live controller: COMPATIBLE (same minor), measured 2026-10-13.**
- Live: HelmRelease `network/envoy-gateway` chart `1.9.2`, Ready=True; controller image
  `docker.io/envoyproxy/gateway:v1.9.2`; all 6 `envoy` containers run imageID
  `sha256:eb2c01c1…`, admin `server_info` = `b579d07d…/1.39.1/Clean/RELEASE/BoringSSL`, LIVE.
- EG `v1.9.2` and the `release/v1.9` branch head both compile
  `DefaultEnvoyProxyImage = distroless-v1.39.1@sha256:eb2c01c1…`. Newest EG releases are
  still v1.9.2 / v1.8.5 (2026-09-28); there is no v1.9.3, and no EG release (re-checked 2026-10-23) ships 1.39.5.
  So no chart bump exists that would move this pin in lockstep.
- EG compatibility matrix (`site/content/en/news/releases/matrix.md`, main, last changed
  7ee8b982 2026-09-11): v1.9 <-> **`distroless-v1.39.x`**; "Each Envoy Gateway release
  ships with, and is tested against, a single Envoy Proxy minor version" and "The Envoy
  Proxy column shows the supported minor version. The exact image that a given Envoy
  Gateway patch release ships may be a newer patch within that same minor version."
  Honest reading: 1.39.5 is inside the supported MINOR; upstream has not shipped an EG
  release that pairs v1.9 with 1.39.5 specifically. No xDS/API surface changed in the
  1.39.5 delta (it touches NO `source/` file; see below) nor in 1.39.4 (destructor/thread-affinity fixes).

**Upstream evidence.** Read from the GitHub release body for `v1.39.5` and the
`compare/v1.39.4...v1.39.5` file list (2026-10-23), and `changelogs/1.39.4.yaml` at tag
`v1.39.4`.

*v1.39.5 (2026-10-23; 9 commits, 61 files, ZERO files under `source/`).* Release body
summary: one upstream **security fix** and one behaviour change.
- Security-labelled upstream: CA trust-store update in the release image (and the
  Rust DNS-resolver crates / Envoy Mobile roots, neither in our distroless binary
  path). It is the reason to prefer 1.39.5 over 1.39.4 and gives this plan a security
  driver. Detail stays on `security_ref` (docs/sops/vulnerability-disclosure.md).
- Behaviour change: `contrib/istio` peer-metadata label precedence (6 files under
  `contrib/istio`). Not compiled into the distroless image we run; no Istio.
- Commits: build-image bump, the CA trust-store update, CVE-ignore list for unaffected CVEs,
  the istio fix backport, OpenSSL 3.5.9 bump (build/contrib tooling; the proxy binary is
  BoringSSL), renewed OCSP test certs, changelog summary, release prep.

*v1.39.4 (2026-10-12; carried, unchanged).* Seven `bug_fixes`, no `breaking_changes`:
- `aws`, `composite`, `dynamic_modules`, `filter_chain`: route-level configuration could
  be destroyed on a worker thread when an RDS update replaced the route configuration.
- `local_ratelimit`: the share provider manager owned by a route-level local rate limit
  configuration could be destroyed on a worker thread on an RDS update. It is now handed
  to the main dispatcher.
- `sds`: a generic secret provider shared with worker threads could be destroyed on a
  worker thread.
- `stats`: exported Prometheus native histogram bucket indices one bucket too low
  (protobuf exposition only).
- `compare/v1.39.3...v1.39.4`: 16 commits, 85 files (fixes above, `thrift`/`fips_go`
  build-time bumps, Docker build base digest).
- Cumulative from live 1.39.1: also the 1.39.2 (BoringSSL bump, packaging) and 1.39.3
  (`api_key_auth`/`oauth2` missing-`:path` crash fixes, brotli bump) deltas.

**Which of those code paths we actually run (re-measured 2026-10-23 on the live 1.39.1
pods with the §2.3b parser: 5 of 6 pods read, identical to 2026-10-13 — the sixth
port-forward returned nothing, the `UNREADABLE` guard exists for exactly that):**
- `envoy.filters.http.local_ratelimit`: **ON our path** — 1 HTTP filter + 1 per-route
  config on each of the 3 envoy-external pods (BackendTrafficPolicy
  `my-software-production/the-ninth-banner-ai-generate`, reworked to per-client +
  global buckets on 2026-10-12 in bf045b58). The (carried) 1.39.4 fix is a destruction race on
  exactly that route-level config during RDS updates, i.e. it HARDENS a path we use;
  it is also the one changed path whose rendering §4.1b must prove survives.
- `sds` generic secret: **ON our path** — one `generic_secret` (`jwt-sa-bearer`, the
  proxy's xDS SA-token) on every pod. Fix is destructor-thread only.
- `aws_*`, `composite`, `filter_chain`, `dynamic_modules`, `oauth2`, `api_key_auth`,
  `compressor`: 0 instances on every pod (positive control: `ext_authz` 11/11 internal,
  1/1 external = the 12 SecurityPolicies).
- Native histograms: Prometheus `kube-prometheus-stack` has no `enableFeatures` /
  `scrapeNativeHistograms`; the PodMonitor scrapes text `/stats/prometheus`. The `stats`
  fix does not touch our instrument.

**Registry facts (Docker Hub v2 API, 2026-10-23).**
- `distroless-v1.39.5` = OCI index `sha256:9d84a586119a27b50437dbb01eccd4722832741539b1ed53c8e9d6da6067a6e0`
  (linux/amd64 `sha256:00c38048…`, linux/arm64 `sha256:3a84aef7…`), HTTP 200.
- `distroless-v1.39.4` = `sha256:ccb37e93…` (still published, no longer the target).
- `distroless-v1.39.1` still resolves to `sha256:eb2c01c1…` = the live imageID on all 6
  pods: rollback target published and node-cached. `distroless-v1.40.0` is now 200
  (`sha256:23b72ac1…`, a MINOR move — separate blocked plan, never this one).
- Live state re-measured 2026-10-23: HR `envoy-gateway` 1.9.2 Ready, EnvoyProxy image =
  the 1.39.1 pin, both Gateways Programmed=True, 3/3 + 3/3 proxy pods, all `1.39.1 LIVE`.
- SDS: one `generic_secret` (`jwt-sa-bearer`) on the pod checked (2026-10-23 structural walk).

**Repo correction (carried, still open).** The deny rule's reason says this pin moves
"only in the SAME change as the gateway-helm chart bump … never on its own". That is
stricter than upstream's matrix; executing this plan departs from its literal wording
(§6 makes it an explicit operator decision at the GO). Proposed wording: "MINOR moves
only with the chart; same-minor patches may lead the compiled default, attended."

**Latent finding (not planned around, F-df39740f).** `BackendTrafficPolicy
network/envoy-compression` is Accepted=True yet every pod still renders **0**
compressor filters (re-measured 2026-10-13). If that is fixed before this window, the
1.39.3-delta brotli bump (carried in this target) lands on a live path, hence the §2.3b STOP-and-amend.

**Verdict.** A small same-minor patch whose only code touching our request path is a
race fix on a filter we use; but it rolls every HTTP-serving pod, so it runs in an
attended window, human-gated. No reboot.

## 2. Pre-checks (read-only, ~15 min)

Run these AFTER Step 0 of the window has settled.

**Shell state does not survive between agent Bash calls.** §2.4 writes every helper
(`envver`, `filtmap`, `routes`, `policies`, `sweep`, `changed`, `q`, `alerts`, `pfprom`,
`pfstop`) to `/tmp/envoy1395-win/fns.sh`. EVERY later block in §2.4–§5 starts with
`. /tmp/envoy1395-win/fns.sh`, which also `cd`s into `/tmp/envoy1395-win`. `q()` and
`alerts()` own their Prometheus port-forward on :19090. Every after-file is checked
with `test -s` before it is read: an unsourced helper writes 0 lines and an unguarded
diff then reports a vacuous PASS (measured 2026-10-05 on the 1.39.2 draft).

2.1 Premises: `.venv/bin/python3 runbooks/plan-premises.py envoy-proxy-config-distroless-v1.39.4`.
Every premise must PASS.

2.2 Flux, workloads and PDBs (all objects verified to exist 2026-10-13):
```bash
flux get kustomizations -n network | grep -E 'envoy-gateway'          # envoy-gateway + envoy-gateway-crds, Ready True
kubectl -n network get deploy envoy-gateway envoy-internal envoy-external   # all 3/3
kubectl -n network get pdb envoy-internal envoy-external                    # ALLOWED DISRUPTIONS 1 each
kubectl -n network get pods -l app.kubernetes.io/component=proxy -o wide    # 3 per gateway, one per node
```

2.3 Upstream target is still what this plan pins (network read, not a premise):
```bash
T=$(curl -fsSL "https://auth.docker.io/token?service=registry.docker.io&scope=repository:envoyproxy/envoy:pull" | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
for t in distroless-v1.39.5 distroless-v1.39.1; do echo "$t $(curl -fsSI -H "Authorization: Bearer $T" -H 'Accept: application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json' https://registry-1.docker.io/v2/envoyproxy/envoy/manifests/$t | grep -i docker-content-digest | tr -d '\r')"; done
# must print (measured 2026-10-13):
#   distroless-v1.39.5 docker-content-digest: sha256:9d84a586119a27b50437dbb01eccd4722832741539b1ed53c8e9d6da6067a6e0
#   distroless-v1.39.1 docker-content-digest: sha256:eb2c01c13125d1629637cb4e4cce7207009fb7cc2c8027f9742758549d15b6f4
gh release list -R envoyproxy/gateway -L 3          # newest must still be v1.9.2 / v1.8.5
gh release list -R envoyproxy/envoy -L 3            # newest 1.39.x must still be v1.39.5 (v1.40.x may also be listed: ignore, minor move)
```
- FAIL shape / STOP: a different digest (tag re-pushed) or an empty line (tag gone or
  registry unreachable). If an EG v1.9.3+ exists, prefer that chart bump (moves the pin
  in lockstep per the deny rule) and supersede this plan. If a v1.39.6 exists, this
  plan is stale: re-plan rather than ship a known-superseded patch.

2.3b **Exposure re-check: which changed code paths are live?** Uses `filtmap` from §2.4
(write §2.4 first, then run this). It parses each pod's `/config_dump` STRUCTURALLY
(listener `http_filters` + route `typed_per_filter_config`), not by substring: a raw
substring count over the full dump hits the compiled-extension list and reported 1–2
"instances" of every filter on 2026-10-13, which is a false exposure reading.
```bash
. /tmp/envoy1395-win/fns.sh
filtmap | sort | tee filt.before
test -s filt.before && [ "$(wc -l < filt.before)" -eq 6 ] && echo FILT_ROWS_OK
grep -c UNREADABLE filt.before                                  # must print 0 (or 1 under the baseline tolerance rule)
# measured 2026-10-13 04:1x (format filter=<http_filters>/<per-route configs>):
#   envoy-external-… ext_authz=1/1  local_ratelimit=1/1 compressor=0/0 router=4   (x3)
#   envoy-internal-… ext_authz=11/11 local_ratelimit=0/0 compressor=0/0 router=4  (x3)
```
- BASELINE TOLERANCE RULE (pre-roll only): the helpers now wait up to 10 s for the
  port-forward. If exactly ONE pod still prints `UNREADABLE`, re-run `filtmap` once; if it
  stays unreadable and the other two pods of its gateway read identically, record it and
  continue (5-of-6 baseline). Two or more `UNREADABLE`, or a whole gateway unreadable,
  is a STOP. After the roll (§4) the requirement is strict: 0 `UNREADABLE`.
- PASS: `FILT_ROWS_OK`, 0 `UNREADABLE` (or the tolerance rule above), `ext_authz` non-zero on all 6 (control: proves the
  parser sees filters), `compressor=0/0` on all 6.
- STOP-and-amend: a non-zero `compressor` means F-df39740f was fixed since 2026-10-13;
  the brotli dependency bump is then on every compressible response and §4 has no
  decode gate. A different `local_ratelimit` count is fine (record it); §4.1b diffs
  against THIS file, not the 2026-10-13 numbers.

2.4 Write the helper file once, then take the baseline Envoy build version on all 6
pods (the input to the §4.1 CONTENTS assertion). Paste exactly as written. `envver`,
`routes`, `policies`, `sweep`, `changed`, `q`, `alerts` are the 1.39.2-draft helpers
dry-run 2026-10-05 under zsh and bash (`changed()` rc 0/1/2/2/2 on identical /
one-row-000 / empty / short / key-mismatch); `filtmap` is new and was dry-run
2026-10-13 under zsh 5.9 and bash against all 6 live pods (output above).
```bash
mkdir -p /tmp/envoy1395-win
cat > /tmp/envoy1395-win/fns.sh <<'FNS'
# envoy1395 window helpers. SOURCE at the top of EVERY later block:  . /tmp/envoy1395-win/fns.sh
W="${W:-/tmp/envoy1395-win}"; cd "$W" || return 1
envver() { i=0; for p in $(kubectl -n network get pods -l app.kubernetes.io/component=proxy -o name); do
  port=$((19100+i)); i=$((i+1))
  kubectl -n network port-forward "$p" "$port":19000 >/dev/null 2>&1 & pf=$!; for _ in 1 2 3 4 5 6 7 8 9 10; do curl -s --max-time 2 -o /dev/null "http://localhost:$port/ready" && break; sleep 1; done
  v=$(curl -s --max-time 5 "http://localhost:$port/server_info" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['version'].split('/')[1], d['state'])" 2>/dev/null)
  kill $pf 2>/dev/null; echo "${p#pod/} ${v:-UNREADABLE}"; done; }
filtmap() { i=0; for p in $(kubectl -n network get pods -l app.kubernetes.io/component=proxy -o name); do
  port=$((19120+i)); i=$((i+1))
  kubectl -n network port-forward "$p" "$port":19000 >/dev/null 2>&1 & pf=$!; for _ in 1 2 3 4 5 6 7 8 9 10; do curl -s --max-time 2 -o /dev/null "http://localhost:$port/ready" && break; sleep 1; done
  curl -s --max-time 20 "http://localhost:$port/config_dump" > "$W/.cd" 2>/dev/null
  kill $pf 2>/dev/null; wait $pf 2>/dev/null
  python3 - "${p#pod/}" "$W/.cd" <<'PY'
import sys,json
from collections import Counter
pod,f=sys.argv[1],sys.argv[2]
try: d=json.load(open(f))
except Exception: print(pod,"UNREADABLE"); sys.exit(0)
hf=Counter(); pr=Counter()
def walk(o):
    if isinstance(o,dict):
        for x in o.get("http_filters",[]) or []: hf[x.get("name","").split("/")[0]]+=1
        for k in (o.get("typed_per_filter_config") or {}): pr[k.split("/")[0]]+=1
        for v in o.values(): walk(v)
    elif isinstance(o,list):
        for v in o: walk(v)
for c in d.get("configs",[]):
    if c.get("@type","").split(".")[-1] in ("ListenersConfigDump","RoutesConfigDump"): walk(c)
n=lambda k:"%d/%d"%(hf["envoy.filters.http."+k],pr["envoy.filters.http."+k])
print(pod,"ext_authz="+n("ext_authz"),"local_ratelimit="+n("local_ratelimit"),"compressor="+n("compressor"),"router="+str(hf["envoy.filters.http.router"]))
PY
done; }
routes() { kubectl get httproute -A -o json | python3 -c '
import sys,json;from collections import Counter;c=Counter()
for r in json.load(sys.stdin)["items"]:
  for p in r.get("status",{}).get("parents",[]):
    s={x["type"]:x["status"] for x in p.get("conditions",[])}
    c[(p["parentRef"]["name"],"Accepted="+s.get("Accepted","?"),"ResolvedRefs="+s.get("ResolvedRefs","?"))]+=1
for k,v in sorted(c.items()): print(k,v)'; }
policies() { kubectl get securitypolicy,clienttrafficpolicy,backendtrafficpolicy,backend -A -o json | python3 -c '
import sys,json;from collections import Counter;c=Counter()
for o in json.load(sys.stdin)["items"]:
  st=o.get("status",{}); a=st.get("ancestors") or []
  v=[x["status"] for y in a for x in y.get("conditions",[]) if x["type"]=="Accepted"] or [x["status"] for x in st.get("conditions",[]) if x["type"]=="Accepted"]
  c[(o["kind"],tuple(sorted(set(v))))]+=1
print(sorted(c.items()))'; }
sweep() { test -s "$W/hosts.txt" || { echo "GUARD: $W/hosts.txt missing or empty" >&2; return 2; }
  while read -r h v; do printf '%s %s %s\n' "$v" "$(curl -sk -o /dev/null -w '%{http_code}' --max-time 8 --resolve "$h:443:$v" "https://$h/" </dev/null)" "$h"; done < "$W/hosts.txt"; }
# changed BEFORE AFTER -- rows "<vip> <code> <host>", joined on key host|vip.
# rc 0 = no change, rc 1 = CHANGED lines printed, rc 2 = GUARD (empty input / row-count / join mismatch)
changed() { b=$1; a=$2
  test -s "$b" && test -s "$a" || { echo "GUARD: empty input ($b / $a)"; return 2; }
  nb=$(wc -l < "$b" | tr -d ' '); na=$(wc -l < "$a" | tr -d ' ')
  [ "$nb" = "$na" ] || { echo "GUARD: row count $nb (before) != $na (after)"; return 2; }
  awk '{print $3"|"$1, $2}' "$b" | sort > "$W/.kb"; awk '{print $3"|"$1, $2}' "$a" | sort > "$W/.ka"
  nj=$(join "$W/.kb" "$W/.ka" | wc -l | tr -d ' ')
  [ "$nj" = "$nb" ] || { echo "GUARD: join matched $nj of $nb rows"; return 2; }
  join "$W/.kb" "$W/.ka" | awk '$2!=$3 {print "CHANGED", $1, $2, "->", $3; n++} END {print "CHECKED " NR " rows, CHANGED " n+0; exit (n>0)}'; }
pfprom() { curl -sf --max-time 3 http://localhost:19090/-/ready >/dev/null 2>&1 && return 0
  kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & echo $! > "$W/pf.pid"
  for _ in 1 2 3 4 5 6 7 8 9 10; do sleep 1; curl -sf --max-time 3 http://localhost:19090/-/ready >/dev/null 2>&1 && return 0; done
  echo "GUARD: prometheus port-forward not ready" >&2; return 2; }
pfstop() { [ -f "$W/pf.pid" ] && kill "$(cat "$W/pf.pid")" 2>/dev/null; rm -f "$W/pf.pid"; }
q() { pfprom || { echo PF_FAILED; return 2; }
  curl -s --get http://localhost:19090/api/v1/query --data-urlencode "query=$1" | python3 -c 'import sys,json;r=json.load(sys.stdin)["data"]["result"];print(r[0]["value"][1] if r else "EMPTY")' 2>/dev/null || echo QUERY_FAILED; }
alerts() { pfprom || { echo PF_FAILED; return 2; }
  curl -s http://localhost:19090/api/v1/alerts | python3 -c 'import sys,json;print(sorted({a["labels"]["alertname"] for a in json.load(sys.stdin)["data"]["alerts"] if a["state"]=="firing" and a["labels"]["alertname"].startswith(("EnvoyGateway","IngressProbe"))}))'; }
FNS
echo "FNS_WRITTEN $(grep -c '() {' /tmp/envoy1395-win/fns.sh) functions"     # must print 10
. /tmp/envoy1395-win/fns.sh
envver | tee ver.before
test -s ver.before && grep -c ' 1\.39\.1 LIVE$' ver.before    # must print 6 (2026-10-13 live: 6)
```
Then run §2.3b.

2.5 Baseline route and policy acceptance (§4.2 diffs against them):
```bash
. /tmp/envoy1395-win/fns.sh
routes > routes.before; policies > policies.before
test -s routes.before && test -s policies.before && cat routes.before policies.before   # empty = STOP
```
Any non-True line already in the baseline must be noted and not blamed on this change.

2.6 **Behavioural baseline of BOTH gateways.** Per-hostname HTTP status through each VIP.
Hostnames are pulled live into /tmp only and never committed. Row key is host+VIP.
Re-measured 2026-10-13: 95 HTTPRoutes, 80 pairs (54 on .103, 26 on .104).
```bash
. /tmp/envoy1395-win/fns.sh
kubectl get httproute -A -o json | python3 -c '
import sys,json
vip={"envoy-internal":"192.168.55.103","envoy-external":"192.168.55.104"};seen=set()
for r in json.load(sys.stdin)["items"]:
  for p in r["spec"].get("parentRefs",[]):
    if p.get("sectionName")=="http" or p["name"] not in vip: continue
    for h in r["spec"].get("hostnames") or []:
      if (h,vip[p["name"]]) not in seen: seen.add((h,vip[p["name"]])); print(h,vip[p["name"]])' > hosts.txt
test -s hosts.txt && wc -l < hosts.txt                       # ~80; empty = STOP
sweep > status.before
test -s status.before && [ "$(wc -l < status.before)" -eq "$(wc -l < hosts.txt)" ] && echo BASELINE_ROWS_OK
awk '{print $1,$2}' status.before | sort | uniq -c
awk '{print $2}' hosts.txt | sort | uniq -c        # BOTH 192.168.55.103 and 192.168.55.104 must appear
# negative control -- proves the sweep can SEE a missing route (Envoy answers 404 for an unrouted host):
for v in 192.168.55.103 192.168.55.104; do curl -sk -o /dev/null -w "$v %{http_code}\n" --max-time 8 --resolve "nohost-negative-control.invalid:443:$v" https://nohost-negative-control.invalid/; done   # must print 404 twice
```
Pre-existing `404`/`405`/`503` rows (unrouted `/`, backend down) are expected; §4.3
judges only rows that CHANGE.

2.7 Prometheus and alert baseline:
```bash
. /tmp/envoy1395-win/fns.sh
q 'count(up{namespace="network",job="network/envoy-gateway"}==1)'          # 6   (2026-10-13: 6)
q 'sum(envoy_listener_manager_lds_update_rejected{namespace="network"})'   # 0   (2026-10-13: 0, over 6 series)
q 'sum(envoy_cluster_manager_cds_update_rejected{namespace="network"})'    # 0   (2026-10-13: 0)
q 'sum(rate(envoy_http_downstream_rq_xx{namespace="network",envoy_response_code_class="2"}[5m]))'  # >0 (2026-10-13: ~1.05)
q 'min(probe_success{probe_class=~"http|dns"})'                            # 1   (2026-10-13: 1, over 5 probes)
alerts                                                                     # must be [] (2026-10-13: [])
pfstop
```
`alerts` filters to `EnvoyGateway*`/`IngressProbe*` on purpose: on 2026-10-13 unrelated
`TargetDown`, `AragScrape*` and `MaintenanceWindow*` alerts were firing; record them, do
not STOP on them, and do not blame them on this change. `PF_FAILED`, `QUERY_FAILED` or
`EMPTY` from any `q` line is a STOP, never a pass.

**STOP** if any of these fails:
- a premise fails;
- §2.3 shows a different digest, an EG v1.9.3+, or an Envoy v1.39.6+;
- a proxy Deployment is below 3/3, or a PDB allows 0 disruptions;
- `ver.before` or `filt.before` has an `UNREADABLE` line that the baseline tolerance rule (§2.3b) does not cover, or `FILT_ROWS_OK` is missing;
- §2.3b shows a non-zero `compressor`;
- the negative control does not print 404 twice;
- an `EnvoyGateway*` or `IngressProbe*` alert is firing;
- any `test -s` guard prints nothing, or `BASELINE_ROWS_OK` is missing;
- any `q` prints `PF_FAILED`, `QUERY_FAILED` or `EMPTY`.

## 3. Steps (GitOps)

3.1 Move the pin and annotate it. Dry-tested 2026-10-13 and RE-TESTED 2026-10-23 with the 1.39.5 digest on a scratch copy of gatewayclass.yaml on macOS (forward diff 1 changed + 5 inserted lines; rollback seds return the file byte-identical) (BSD
sed + `.venv/bin/python3`). Resulting diff (verbatim from the dry run):
```
-          image: docker.io/envoyproxy/envoy:distroless-v1.39.1@sha256:eb2c01c13125d1629637cb4e4cce7207009fb7cc2c8027f9742758549d15b6f4
+          # 2026-10 (plan envoy-proxy-config-distroless-v1.39.4, target 1.39.5): moved AHEAD of the
+          # compiled default (EG v1.9.2 compiles v1.39.1) to upstream's v1.39.5
+          # patch. Same Envoy MINOR, which the EG compatibility matrix lists as the
+          # supported minor for v1.9 ("may be a newer patch within that same minor").
+          # A MINOR move still travels only with the gateway-helm chart bump.
+          image: docker.io/envoyproxy/envoy:distroless-v1.39.5@sha256:9d84a586119a27b50437dbb01eccd4722832741539b1ed53c8e9d6da6067a6e0
```
```bash
cd /Users/mu/code/cberg-home-nextgen
F=kubernetes/apps/network/envoy-gateway/app/gatewayclass.yaml
sed -i '' 's|envoyproxy/envoy:distroless-v1\.39\.1@sha256:eb2c01c13125d1629637cb4e4cce7207009fb7cc2c8027f9742758549d15b6f4$|envoyproxy/envoy:distroless-v1.39.5@sha256:9d84a586119a27b50437dbb01eccd4722832741539b1ed53c8e9d6da6067a6e0|' "$F"
.venv/bin/python3 - "$F" <<'EOF'
import sys
p=sys.argv[1]; s=open(p).read()
anchor="          image: docker.io/envoyproxy/envoy:distroless-v1.39.5@"
assert s.count(anchor)==1, "anchor not unique -- sed did not apply; STOP"
note=("          # 2026-10 (plan envoy-proxy-config-distroless-v1.39.4, target 1.39.5): moved AHEAD of the\n"
      "          # compiled default (EG v1.9.2 compiles v1.39.1) to upstream's v1.39.5\n"
      "          # patch. Same Envoy MINOR, which the EG compatibility matrix lists as the\n"
      "          # supported minor for v1.9 (\"may be a newer patch within that same minor\").\n"
      "          # A MINOR move still travels only with the gateway-helm chart bump.\n")
open(p,"w").write(s.replace(anchor, note+anchor))
EOF
git diff --stat "$F"                       # 1 file, 6 insertions(+), 1 deletion(-)
grep -c 'distroless-v1.39.5@sha256:9d84a586119a27b50437dbb01eccd4722832741539b1ed53c8e9d6da6067a6e0' "$F"   # 1
.venv/bin/python3 -c "import yaml;d=list(yaml.safe_load_all(open('$F')));print('YAML_OK',d[1]['spec']['provider']['kubernetes']['envoyDeployment']['container']['image'])"
#   YAML_OK docker.io/envoyproxy/envoy:distroless-v1.39.5@sha256:9d84a586...   (bare python3 may lack PyYAML)
```

3.2 Commit with `--only` (shared worktree), verify, then push. Land the §6 plan-file
bookkeeping (1.39.3 draft -> superseded, reciprocal refs) in a SEPARATE commit, never
inside this manifest commit.
```bash
cat > /tmp/envoy1395-msg.txt <<'EOF'
feat(envoy-gateway): Envoy data plane distroless-v1.39.1 -> v1.39.5

Digest-pinned. Same Envoy minor as EG 1.9.2's compiled default (matrix:
v1.9 <-> distroless-v1.39.x). 1.39.5 delta: image CA trust-store update
(CA trust-store update, see security_ref) + OpenSSL/build deps; carries the 1.39.4 worker-thread
destruction-race fixes (local_ratelimit route config, used on envoy-external). Rolls envoy-internal/-external (3+3 pods, surge-first).
Plan: runbooks/maintenance/plans/envoy-proxy-config-distroless-v1.39.4.md

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
git commit --only kubernetes/apps/network/envoy-gateway/app/gatewayclass.yaml -F /tmp/envoy1395-msg.txt
git log -1 --format=%s    # must be "feat(envoy-gateway): Envoy data plane distroless-v1.39.1 -> v1.39.5"; amend if not
git show --stat HEAD      # exactly gatewayclass.yaml
git push
```

3.3 Reconcile. The EnvoyProxy CR is applied by Kustomization `network/envoy-gateway`
(not by the chart), so no HelmRelease reconcile is needed:
```bash
flux reconcile source git flux-system -n flux-system
flux reconcile kustomization envoy-gateway -n network
kubectl -n network get envoyproxy envoy-proxy-config -o jsonpath='{.spec.provider.kubernetes.envoyDeployment.container.image}{"\n"}'   # ...distroless-v1.39.5@sha256:9d84a586...
```

3.4 Watch both data-plane rolls:
```bash
kubectl -n network rollout status deploy/envoy-internal --timeout=600s
kubectl -n network rollout status deploy/envoy-external --timeout=600s
```
`rollout status` can go green on the OLD generation
(`feedback_rollout_status_old_generation`), so §4.1 checks the live pods directly.

## 4. Verification

4.1 **CONTENTS ASSERTION: every proxy pod runs the 1.39.5 binary and is LIVE** —
measured by imageID + admin `server_info`, compared to `ver.before` (6 × `1.39.1 LIVE`).
```bash
kubectl -n network get pods -l app.kubernetes.io/component=proxy -o jsonpath='{range .items[*]}{range .status.containerStatuses[?(@.name=="envoy")]}{.imageID}{"\n"}{end}{end}' | sort | uniq -c
#   expect: 6 x docker.io/envoyproxy/envoy@sha256:9d84a586119a27b50437dbb01eccd4722832741539b1ed53c8e9d6da6067a6e0
. /tmp/envoy1395-win/fns.sh
envver | tee ver.after
test -s ver.after || echo 'FAIL: ver.after empty -- instrument did not run'
[ "$(wc -l < ver.after)" -eq 6 ] || echo 'FAIL: ver.after does not have 6 rows'
grep -c ' 1\.39\.5 LIVE$' ver.after                   # must print 6
grep -vc ' 1\.39\.5 LIVE$' ver.after                  # must print 0
kubectl -n network get pods -l app.kubernetes.io/component=proxy -o wide   # 3 per gateway, one per node
```
- PASS: 6 lines `<pod> 1.39.5 LIVE`, 6 × the `9d84a586…` imageID, each gateway one pod per node.
- FAIL shape: a `1.39.1` line (pod not re-rendered / roll half-done); `UNREADABLE`
  (admin not answering); state `PRE_INITIALIZING`/`DRAINING` (not at config); two pods
  of one gateway on one node (spread collapsed, seen 2026-09-07).
- The gate can fail: `ver.before` reads `1.39.1` on these pods (live 2026-10-13), so the
  `1\.39\.5` grep returns 0 against the pre-state. Note the imageID is the INDEX digest
  `9d84a586…` on these nodes (live pods show the index digest `eb2c01c1…` for 1.39.1,
  not a per-arch digest).

4.1b **CONTENTS ASSERTION: the rendered filter map is unchanged, including the
local rate limit on envoy-external** — the one changed code path we run (§1). Measured
by `filtmap` (structural `/config_dump` parse), compared to `filt.before` with pod names
stripped (pods are new after the roll).
```bash
. /tmp/envoy1395-win/fns.sh
filtmap | sort | tee filt.after
test -s filt.after && [ "$(wc -l < filt.after)" -eq 6 ] && echo FILT_AFTER_ROWS_OK
strip() { sed -E 's/^(envoy-(internal|external))-[^ ]+ /\1 /' "$1" | sort; }
strip filt.before > filt.before.k; strip filt.after > filt.after.k
grep -c UNREADABLE filt.after.k                                    # must print 0
diff filt.before.k filt.after.k && echo FILTMAP_UNCHANGED
grep -c '^envoy-external .*local_ratelimit=1/1' filt.after.k       # must print 3 (if §2.3b baseline was 1/1)
# negative control: the same grep against the internal rows must print 0 -- the counter discriminates
grep -c '^envoy-internal .*local_ratelimit=1/1' filt.after.k       # must print 0
```
- PASS: `FILT_AFTER_ROWS_OK`, `FILTMAP_UNCHANGED`, 0 `UNREADABLE`, external count 3, internal 0.
- FAIL shape: `local_ratelimit=0/0` on an external pod (the BackendTrafficPolicy no longer
  renders, i.e. the AI-generate endpoint lost its abuse guard while every route stays
  200); `ext_authz` lower than baseline (a SecurityPolicy dropped — forward-auth silently
  bypassed or the route 5xx's); any `UNREADABLE`.
- Why config, not a 429 probe: provoking the limit means POSTing to an AI generation
  endpoint (cost + real user buckets); the per-route config is the contents of what this
  change could drop. The `envoy_http_local_rate_limit_*` metrics are not used: they are
  per-pod counters that reset on the roll and only materialise once traffic hits the
  filter, so an empty result would be ambiguous.

4.2 Route and policy acceptance must not regress (diff against §2.5):
```bash
. /tmp/envoy1395-win/fns.sh
routes > routes.after; policies > policies.after
test -s routes.after && test -s policies.after && test -s routes.before && test -s policies.before \
  && diff routes.before routes.after && diff policies.before policies.after && echo ACCEPTANCE_UNCHANGED
```
- PASS only if `ACCEPTANCE_UNCHANGED` prints (two empty files would diff equal; the
  `test -s` guards make that a FAIL).
- FAIL shape: a line moves to `Accepted=False`/`ResolvedRefs=False`, a count drops, or a
  policy kind gains a `False`. The controller did not change, so this is the floor check.

4.3 **CONTENTS ASSERTION, behavioural probe of BOTH gateways** — every host+VIP pair
serves the same status as `status.before`.
```bash
. /tmp/envoy1395-win/fns.sh
sweep > status.after
test -s status.after && echo AFTER_NONEMPTY                                   # absent = FAIL
wc -l < status.before; wc -l < status.after                                   # must be EQUAL (~80)
awk '{print $1}' status.after | sort | uniq -c   # both .103 and .104 present, same counts as status.before
# prove the comparator can FAIL: one row forced to 000 must give rc 1 and exactly one CHANGED line
sed '1s/^\([^ ]*\) [0-9]*/\1 000/' status.after > status.knownbad
changed status.before status.knownbad; echo "control rc=$?"                    # must print CHANGED ... -> 000 and "control rc=1"
changed status.before status.after; echo "rc=$?"                              # rc 0 clean, rc 1 CHANGED rows, rc 2 GUARD = FAIL
```
- If `control rc=1` does not print, the comparator is blind: FAIL the gate.
- Any `GUARD:` line or `rc=2` is an instrument FAIL, never "0 CHANGED".
- Re-probe each `CHANGED` line once after 60 s (an app pod can be mid-restart).
- PASS: `AFTER_NONEMPTY`, equal row counts, `control rc=1`, real run rc 0 (or rc 1 where
  every CHANGED row returns to baseline on re-probe); both VIPs present.
- FAIL: a pair stuck at `000` (TLS/listener failure); stuck at `404` (route dropped; the
  negative control proved Envoy says 404 for an unrouted host); a `2xx/3xx/401` stuck at
  `5xx` (`302 -> 5xx` = broken Authentik forward-auth).

4.4 Prometheus gates. Wait 10 minutes after §3.4 so the 5m windows cover only new pods.
```bash
. /tmp/envoy1395-win/fns.sh
q 'count(up{namespace="network",job="network/envoy-gateway"}==1)'                               # 6
q 'sum(envoy_listener_manager_lds_update_rejected{namespace="network"})'   # 0
q 'count(envoy_listener_manager_lds_update_rejected{namespace="network"})' # 6 (non-vacuous: EMPTY cannot pass)
q 'sum(envoy_cluster_manager_cds_update_rejected{namespace="network"})'    # 0
q 'sum(rate(envoy_http_downstream_rq_xx{namespace="network",envoy_response_code_class="2"}[5m]))' # > 0
q 'sum(rate(envoy_http_downstream_rq_xx{namespace="network",envoy_response_code_class="5"}[5m])) / sum(rate(envoy_http_downstream_rq_xx{namespace="network"}[5m]))'   # < 0.02
q 'min(probe_success{probe_class=~"http|dns"})'                                                   # 1
alerts                                                                                            # must be []
pfstop
```
`PF_FAILED`, `QUERY_FAILED` or `EMPTY` on any line is a FAIL, never a pass. All metric
names below returned non-empty results live on 2026-10-13.
- CONTROL: metric envoy_http_downstream_rq_xx — 2xx rate `> 0` (floor against a data plane that is up but serves nothing; baseline ~1.05 rps 2026-10-13); 5xx ratio `< 0.02`.
- CONTROL: metric envoy_listener_manager_lds_update_rejected — raw sum over the 6 new pods `0`, series count `6`. Raw counter, not `increase()`, because `increase()` drops a new series' first sample and would miss a rejection of the initial config.
- CONTROL: metric envoy_cluster_manager_cds_update_rejected — raw sum `0`.
- CONTROL: metric probe_success — min over the 5 http/dns blackbox probes `1`.
- CONTROL: metric up — `count(up{job="network/envoy-gateway"}==1)` = `6` (all new pods scraped).
- CONTROL: alertname EnvoyGatewayMetricsAbsent — must NOT be firing (keeps the metric gates non-vacuous).
- CONTROL: alertname EnvoyGateway5xxSustained — must NOT be firing.
- CONTROL: alertname EnvoyGatewayPodCrashLooping — must NOT be firing.
- CONTROL: alertname EnvoyGatewayPodNotReady — must NOT be firing.
- CONTROL: alertname IngressProbeFailing — must NOT be firing.

Alert rules verified present in git 2026-10-13: `gateway-availability-alerts.yaml`
(MetricsAbsent, 5xxSustained), `envoy-gateway-alerts.yaml` (PodCrashLooping,
PodNotReady), `blackbox-exporter-alerts.yaml` (IngressProbeFailing), all under
`kubernetes/apps/monitoring/kube-prometheus-stack/app/`.

4.5 Soak: re-run 4.1b, 4.3 and 4.4 once more, 7 minutes later (each block sources
`fns.sh`; after-files are overwritten and re-guarded). An RDS update happens on any
route change; the carried 1.39.4 fixes are in that path, so a crash would show as a restart:
```bash
kubectl -n network get pods -l app.kubernetes.io/component=proxy -o jsonpath='{range .items[*]}{.metadata.name} {range .status.containerStatuses[?(@.name=="envoy")]}{.restartCount}{end}{"\n"}{end}'   # all 0
```
Then retire this plan file per `README.md` (separate commit).

## 5. Rollback

No forward-only step: no CRD, no state, no migration, no controller change. The old
image is digest-pinned, still published (§2.3) and cached on every node.

5.1 Revert and push (~2 min plus the roll):
```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <sha-of-3.2>
git log -1 --format=%s    # must be 'Revert "feat(envoy-gateway): Envoy data plane distroless-v1.39.1 -> v1.39.5"'
git show --stat HEAD      # exactly gatewayclass.yaml
grep -o 'envoy:distroless-v[^ ]*' kubernetes/apps/network/envoy-gateway/app/gatewayclass.yaml
#   must print envoy:distroless-v1.39.1@sha256:eb2c01c13125d1629637cb4e4cce7207009fb7cc2c8027f9742758549d15b6f4
git push
flux reconcile source git flux-system -n flux-system
flux reconcile kustomization envoy-gateway -n network
kubectl -n network rollout status deploy/envoy-internal --timeout=600s
kubectl -n network rollout status deploy/envoy-external --timeout=600s
```
If the revert conflicts (another commit touched the same lines), restore by hand. Both
lines were dry-tested 2026-10-13 on the scratch copy produced by §3.1 and returned the
file byte-identical to the original (`diff` empty):
```bash
F=kubernetes/apps/network/envoy-gateway/app/gatewayclass.yaml
sed -i '' 's|envoyproxy/envoy:distroless-v1\.39\.5@sha256:9d84a586119a27b50437dbb01eccd4722832741539b1ed53c8e9d6da6067a6e0$|envoyproxy/envoy:distroless-v1.39.1@sha256:eb2c01c13125d1629637cb4e4cce7207009fb7cc2c8027f9742758549d15b6f4|' "$F"
sed -i '' '/plan envoy-proxy-config-distroless-v1.39.4, target 1.39.5): moved AHEAD/,+4d' "$F"      # removes the 5 comment lines §3.1 added
```
Then commit it with `--only` as in §3.2 and verify the subject.

5.2 Confirm the cluster is back:
- Re-run 4.1 with `1\.39\.1` in place of `1\.39\.5` (6 × imageID `sha256:eb2c01c1…`,
  `grep -c ' 1\.39\.1 LIVE$' ver.after` = 6), keeping the `test -s` and 6-row guards.
- Re-run 4.1b, 4.2, 4.3 (including the `status.knownbad` control) and 4.4 against the
  SAME `/tmp/envoy1395-win/*.before` baselines. They must pass.

5.3 **Break-glass, data plane dark and the revert cannot land.** Flux fetches from GitHub
over cluster DNS/egress, not through Envoy, so a dark Envoy does not block 5.1. If new
pods crash-loop, `kubectl -n network rollout undo deploy/envoy-internal` (and
`envoy-external`) is a stopgap only — the controller re-renders these Deployments from
the EnvoyProxy CR and overwrites the undo at the next reconcile. Follow with 5.1 at once.

## 6. Interference notes

- **Attended window only (sat/sun), never nightly.** `touches.shared` carries
  `gateway/envoy` (in `SHARED_INFRA_FLOOR`); `autonomy_override: human-gated` says so
  explicitly. No reboot, not `exclusive`, but it should be the only routing-perturbing
  plan in its window.
- **Deny-rule departure: the operator decides it at the GO.** Rule `*envoyproxy/envoy*`
  says this pin moves "only in the SAME change as the gateway-helm chart bump … never on
  its own". This plan is exactly that on-its-own move. §1 argues it is inside upstream's
  supported minor, but a plan cannot waive a policy rule: at the GO the operator either
  accepts the departure for this one change, or first approves the rule reword (§1 repo
  correction). Without one of those it is a NO-GO. Alternative the operator may prefer:
  WAIT for EG v1.9.3, which will move the pin in lockstep with the chart.
- **Chain bookkeeping is complete:** the -v1.39.2 file is `superseded`; the -v1.39.3 draft no
  longer exists. Reciprocal refs to this plan id (not edited here, this planner writes only
  this file): `envoy-proxy-config-distroless-v1.40.0` already names it; `authentik-2026.8.5`,
  `talos-linux-1.14.4`, `cilium-1.20.4`, `authentik-web-max-requests`, `n8n-2.39.8` reference it too
  (now also listed in this plan's `conflicts_with`).
  Two plans moving the same pin must never both be open: the 1.40.0 plan is `blocked`.
- **Controller prerequisite is met** (chart 1.9.2 live 2026-10-23). The premise
  `controller-is-1.9.2` keeps the coupling checked; if the chart moves first, this plan
  is invalid (re-plan to that release's `DefaultEnvoyProxyImage`).
- **Slot:** `window: null`; the window agent assigns it. The natural slot is
  `sun-attended:2026-11-08`, FIRST, before `nocodb-2026.09.1` (55 + 45 = 100 of 180 min).
  Earlier attended slots are held by plans declared in `conflicts_with`; 11-01 is the
  exclusive Talos roll. Operator 2026-10-23: window stays sun-attended:2026-11-08.
- **nocodb-2026.09.1 in the same slot:** read/read overlap on `monitoring` only. nocodb
  restarts an app with an HTTPRoute, which would show as a `CHANGED` row in §4.3, so
  serialize: this plan runs first and finishes its §4.5 soak before nocodb starts. Not in
  `conflicts_with`, because that would forbid a shared slot that is fine when serialized.
- **Run it FIRST among the remaining plans**, right after Step 0 settles: any app with an
  HTTPRoute that another same-window plan restarts becomes a `CHANGED` line in §4.3.
- **Reciprocity.** `--validate` does not check it. Partners and reasons:
  `penpot-chart-1.10.0` (app restarts poison §4.3; any plan restarting an app with an
  HTTPRoute in the same window does likewise); `talos-linux-1.14.2`, `talos-linux-1.14.4` (node drain vs the single PDB disruption);
  `external-dns-1.23.0` (public edge, Gateway target); No coredns or `kube-prometheus-stack` plan is open on 2026-10-23: if one is added for this
  window (§2.7/§4.4 read Prometheus/blackbox; cluster DNS is on the instrument path), serialize it.
  `flux-reconciler-impersonation`, `flux-distribution-2.9.6`,
  `flux-oci-chart-sources` (the apply and revert path).
- **Traffic during the roll.** Surge-first, one pod at a time (25%/25% -> maxSurge 1,
  maxUnavailable 0; PDB minAvailable 2). The shutdown-manager drains each old pod
  (terminationGracePeriod 360 s). Long-lived connections (websockets, SSE, HA frontend,
  media streams) are cut once per pod and reconnect: interruption, not data loss.
- **Not touched:** k8s-gateway (no CRD change, no DNS gate needed), external-dns and
  public DNS, cert-manager certificates, the controller Deployment.
