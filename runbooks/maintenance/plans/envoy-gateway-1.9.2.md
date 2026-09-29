---
plan_id: envoy-gateway-1.9.2
component: envoy-gateway
also_covers:
  - gateway-helm
  - gateway-crds-helm
pr: null                              # no Renovate PR (0 open); surfaced by coverage.py
kind: chart
current: "1.9.1"
target: "1.9.2"
update_type: patch
risk: medium                          # low-PROBABILITY (measured below: rendered chart diff = image
                                      # tag + 2 env vars; Gateway API CRDs byte-identical; EG CRD diff
                                      # additive-only; Envoy data-plane image UNCHANGED) but total
                                      # IMPACT: Envoy Gateway is the ONLY HTTP data plane since
                                      # 2026-09-07 and this bump ROLLS BOTH proxy Deployments
                                      # (shutdown-manager sidecar image follows the controller tag).
est_duration_min: 50                  # §2 12 + §3 5 + rollouts ~8 + DNS gate x2 ~8 + §4 sweeps/soak ~15
needs_reboot: false
exclusive: false
touches:
  namespaces: [network]
  resources:
    - helmrelease/network/envoy-gateway                          # chart 1.9.1 -> 1.9.2
    - deployment/network/envoy-gateway                           # controller image v1.9.1 -> v1.9.2, 3 pods, surge-first
    - configmap/network/envoy-gateway-config                     # shutdownManager + ratelimit image strings
    - job/network/envoy-gateway-gateway-helm-certgen             # helm pre-upgrade hook; exists only DURING the upgrade (hook-deleted), absent between
    - deployment/network/envoy-internal                          # ROLLS: shutdown-manager sidecar v1.9.1 -> v1.9.2
    - deployment/network/envoy-external                          # ROLLS: shutdown-manager sidecar v1.9.1 -> v1.9.2
    - crd/envoyproxies.gateway.envoyproxy.io                     # additive schema only (73 paths added, 0 removed)
    - deployment/network/k8s-gateway                             # DNS gate: rollout restart x2 (SOP-mandated)
    - kubernetes/apps/network/envoy-gateway/app/helmrelease.yaml
    - kubernetes/apps/network/envoy-gateway/crds/envoy-gateway.yaml
    - kubernetes/apps/network/envoy-gateway/crds/gateway-api-standard.yaml   # header lines only
  shared:
    - gateway/envoy                   # envoy-internal (.103) + envoy-external (.104) carry EVERY
                                      # HTTPRoute (110 routes, 83 internal / 29 external parent refs
                                      # Accepted, measured 2026-09-29)
    - public-edge                     # envoy-external is the internet-facing data plane
    - authentik                       # 12 SecurityPolicies (forward-auth) are enforced by Envoy
    - dns                             # k8s-gateway (.101) restarted twice by the SOP DNS gate
    - monitoring                      # §4 reads Prometheus + blackbox probes (the instrument)
depends_on: []
conflicts_with:
  - app-template-5.2.1                # shared gateway/envoy; rolls ~78 workloads whose routes §4.1's
                                      # hostname status-diff reads -- an app roll mid-window turns
                                      # a 200 into a 503 and fakes (or masks) a regression here
  - penpot-chart-1.10.0               # declares gateway/envoy-external; same §4.1 poisoning
  - helm-drift-detection              # adds spec.driftDetection to every HelmRelease INCLUDING this one
  - flux-fleet-0.60.0                 # upgrades helm-controller, which applies this HR and carries
                                      # the §5 revert path
  - flux-reconciler-impersonation     # exclusive; rewrites how helm/kustomize-controller apply this
  - flux-oci-chart-sources            # moves HelmRepository sources + declares dns-internal/network;
                                      # its DNS work must not overlap the k8s-gateway restart gate
  - chart-patches-coredns-reloader-blackbox   # rolls prometheus-blackbox-exporter = the probe_success
                                      # instrument §4 reads, and CoreDNS (forwards *.domain to .101)
                                      # No kube-prometheus-stack plan is open (91.4.1 executed). If one
                                      # appears it MUST be added here -- §4 reads Prometheus.
capability_change: false              # bug fixes + hardening only. The one "breaking change" (Lua
                                      # strict validation) is inert here: 0 EnvoyExtensionPolicy objects.
                                      # New EnvoyProxyPatch runtime flag defaults ENABLED (preserves
                                      # behaviour) and no EnvoyProxy here uses `patch`. No new route,
                                      # permission, API surface or exposure.
rollback_class: git-revert            # valid HERE (unlike a channel bump): Gateway API CRD content is
                                      # byte-identical at v1.6.1, so the safe-upgrades VAP floor does
                                      # not move; the EG CRD change is additive with 0 stored objects
                                      # using the new fields. See §5.
autonomy_override: human-gated        # belt and braces: shared `gateway`/`dns` already derive
                                      # HUMAN-GATED via SHARED_INFRA_FLOOR. Attended window only.
security_ref: null
finding_refs: []                      # checked 2026-09-29: `finding list --grep` for envoy / envoyproxy /
                                      # gateway / 1.9.2 returns no row for this component+target
review: null
status: draft
window: null
sops_refs:
  - docs/sops/envoy-gateway-upgrade.md
  - docs/sops/k8s-gateway-dns.md
  - docs/sops/application-update.md
  - docs/sops/gateway-api-httproute.md
generated: "2026-09-29"
premises:
  - id: live-chart-is-1.9.1
    why: "current: claims 1.9.1. If a hand bump already moved it, §3's sed matches nothing and the rollback target is wrong."
    run: kubectl get helmrelease envoy-gateway -n network -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: "1.9.1"
  - id: envoy-gateway-hr-ready
    why: "Do not stack a chart bump on a failing release; remediation retries would mask every §4 result."
    run: kubectl get helmrelease envoy-gateway -n network -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: both-gateways-programmed
    why: "The bump must start from a serving data plane; a pre-existing Programmed=False would be blamed on the upgrade."
    run: >-
      kubectl get gateway -n network -o jsonpath='{range .items[*]}{.metadata.name}={.status.conditions[?(@.type=="Programmed")].status} {end}'
    expect_matches: '^envoy-external=True envoy-internal=True\s*$'
  - id: gateway-api-bundle-still-v1.6.1
    why: "§1 and §5 rely on the Gateway API channel NOT moving (the vendored 1.9.2 standard bundle is content-identical at v1.6.1). If the live bundle is anything else, the rollback analysis is void."
    run: >-
      kubectl get crd -o jsonpath='{range .items[*]}{.metadata.annotations.gateway\.networking\.k8s\.io/bundle-version}{"\n"}{end}' | sort -u | grep .
    expect_exact: "v1.6.1"
  - id: no-lua-extension-policies
    why: "The ONLY breaking change in 1.9.2 is strict Lua validation of EnvoyExtensionPolicy scripts. It is inert only while no such policy exists."
    run: kubectl get envoyextensionpolicy -A -o name | wc -l | tr -d ' '
    expect_exact: "0"
  - id: envoyproxy-uses-no-patch-or-lua
    why: "1.9.2 adds the EnvoyProxyPatch runtime flag and Lua sandbox hardening; confirm no EnvoyProxy uses either, so capability_change: false holds."
    run: >-
      kubectl get envoyproxy -A -o json | awk 'tolower($0) ~ /"patch"/ {n++} tolower($0) ~ /lua/ {n++} END {print n+0}'
    expect_exact: "0"
  - id: gatewayclass-pin-unchanged
    why: "gatewayclass.yaml pins the Envoy image and MUST equal the new release's DefaultEnvoyProxyImage (auto-update-policy *envoyproxy/envoy* rule). Measured 2026-09-29: upstream v1.9.2 api/v1alpha1/shared_types.go compiles in exactly this tag+digest (same as v1.9.1), so §3 needs no data-plane image edit. The upstream half cannot be a premise (curl is not an allowed premise command) -- it is §2.6."
    run: grep -o 'distroless-v[^ ]*' kubernetes/apps/network/envoy-gateway/app/gatewayclass.yaml
    expect_exact: "distroless-v1.39.1@sha256:eb2c01c13125d1629637cb4e4cce7207009fb7cc2c8027f9742758549d15b6f4"
  - id: k8s-gateway-no-sync-errors
    why: "The DNS gate in §4.3 counts sync errors after restart; a non-zero baseline would make it unreadable."
    run: >-
      kubectl logs deploy/k8s-gateway -n network --tail=80 | awk 'tolower($0) ~ /could not sync/ {n++} tolower($0) ~ /failed to list/ {n++} END {print n+0}'
    expect_exact: "0"
---

# envoy-gateway 1.9.1 -> 1.9.2 (gateway-helm chart + vendored CRDs)

## 1. Summary & why held

**What changes.** `gateway-helm` 1.9.1 -> 1.9.2 (appVersion v1.9.2, released
2026-09-28) and a re-vendor of the CRDs from `gateway-crds-helm:1.9.2`.

**Why held.** `runbooks/auto-update-policy.yaml` rule `*envoy-gateway*`
("Catch-all for Envoy Gateway artifacts (image/chart aliases) — same hold as
gateway-helm"). The hold is right: Envoy Gateway is the only HTTP data plane in
the cluster. The patch itself is low-probability, as measured below.

**Upstream evidence** (`release-notes/v1.9.2.yaml` at tag v1.9.2, 12 commits
v1.9.1...v1.9.2, including Go 1.26.8, gomod bumps, a distroless base bump and a
ratelimit bump):
- *Breaking:* "Lua scripts that use the `getfenv`, `setfenv`, `newproxy`, or
  `module` globals now fail `Strict` Lua validation, which is the default mode."
  **Inert here.** There are 0 EnvoyExtensionPolicy objects (premise
  `no-lua-extension-policies`).
- *Security hardening:* this covers the Lua sandbox, ControllerNamespace-mode
  resource-collision rejection (we run `deploy.type: GatewayNamespace`), and a
  new `EnvoyProxyPatch` runtime flag that is "enabled by default to preserve
  pre-existing behavior". We use no `patch` in our EnvoyProxy (premise). It
  also fixes an xDS JWT-auth control-plane panic.
- *Bug fixes that matter here:*
  - Deterministic typed_config marshaling. This stops "repeated no-op xDS
    pushes".
  - Duplicate filter-chain / same-SNI listener rejection fixes.
  - Shutdown-manager UDP drain fix.
  - A shutdown panic fix.
- No deprecations. No new features.

**Measured diffs (2026-09-29, scratch copies under /tmp, nothing committed):**
- `helm template` 1.9.1 vs 1.9.2 with the live HR values changes three things:
  - the controller image, `v1.9.1` -> `v1.9.2`;
  - `shutdownManager.image` in `envoy-gateway-config`, `v1.9.1` -> `v1.9.2`;
  - `rateLimitDeployment` image `8fe6ea42` -> `0482748e` (no ratelimit
    Deployment exists here, so this is inert).

  It also adds two env vars to the controller (`ENVOY_GATEWAY_SERVICE_ACCOUNT`,
  `ENVOY_GATEWAY_FULLNAME`), and the labels change. Nothing else.
- **The data plane WILL roll.** Both `envoy-internal` and `envoy-external` run a
  `shutdown-manager` sidecar whose image is `docker.io/envoyproxy/gateway:v1.9.1`
  (live). The controller re-renders it to v1.9.2, which triggers a surge-first
  rolling update of 3+3 proxy pods (strategy 25%/25% gives maxSurge 1 and
  maxUnavailable 0; PDB minAvailable 2). The shutdown-manager drains each old pod.
- **Envoy image: NO change.** `DefaultEnvoyProxyImage` at v1.9.2 is
  `distroless-v1.39.1@sha256:eb2c01c1…`, identical to v1.9.1 and to our pin in
  `gatewayclass.yaml`. So the coupled-pin rule needs no edit (§2.6 + premise
  `gatewayclass-pin-unchanged`).
- **Gateway API CRDs: content byte-identical.** `revendor.sh 1.9.2` on a
  scratch copy gave a 0-line content diff past the 3-line header, and the
  bundle-version is still `v1.6.1` on all 12 docs. So the k8s-gateway
  channel-move risk that justifies the hold does not apply to this bump.
- **EG CRDs:** only `envoyproxies.gateway.envoyproxy.io` changes. The walk over
  schema paths found **0 removed and 73 added**: `bindMountOptions`,
  `defaultUser`/`user` on volume projections, `emptyDir.mode`, and probe
  `grpc.mode`/`httpGet.protocol` from the k8s.io/api bump. Versions are
  unchanged (`v1alpha1` served+storage). A server-side dry-run apply of both
  new files was accepted, including the `safe-upgrades` VAP.
- The image tag exists: `docker.io/envoyproxy/gateway:v1.9.2`, index digest
  `sha256:9d67017c…`, pushed 2026-09-28.

**Verdict.** This is a genuinely small patch. It stays held and HUMAN-GATED
for one reason: it rolls every HTTP-serving pod in the cluster. Run it in an
attended window. No reboot.

## 2. Pre-checks (read-only, ~12 min)

Run these AFTER Step 0 (safe-update apply) of the window has settled. Step 0 can
roll apps, and §2.4's baseline must not include their transients.

2.1 Premises: `.venv/bin/python3 runbooks/plan-premises.py envoy-gateway-1.9.2`. Every premise must PASS.

2.2 Flux and workloads:
```bash
flux get kustomizations -n network | grep -E 'envoy-gateway'          # both Ready True
kubectl -n network get deploy envoy-gateway envoy-internal envoy-external k8s-gateway   # all 3/3
kubectl -n network get pdb envoy-gateway envoy-internal envoy-external k8s-gateway      # ALLOWED DISRUPTIONS 1 each
```

2.3 Baseline route and policy acceptance. Write this to a file; §4.2 diffs
against it.
```bash
mkdir -p /tmp/eg192-win && cd /tmp/eg192-win
kubectl get httproute -A -o json | python3 -c '
import sys,json;from collections import Counter;c=Counter()
for r in json.load(sys.stdin)["items"]:
  for p in r.get("status",{}).get("parents",[]):
    s={x["type"]:x["status"] for x in p.get("conditions",[])}
    c[(p["parentRef"]["name"],"Accepted="+s.get("Accepted","?"),"ResolvedRefs="+s.get("ResolvedRefs","?"))]+=1
for k,v in sorted(c.items()): print(k,v)' > routes.before
kubectl get securitypolicy,clienttrafficpolicy,backendtrafficpolicy,backend -A -o json | python3 -c '
import sys,json;from collections import Counter;c=Counter()
for o in json.load(sys.stdin)["items"]:
  st=o.get("status",{}); a=st.get("ancestors") or []
  v=[x["status"] for y in a for x in y.get("conditions",[]) if x["type"]=="Accepted"] or [x["status"] for x in st.get("conditions",[]) if x["type"]=="Accepted"]
  c[(o["kind"],tuple(sorted(set(v))))]+=1
print(sorted(c.items()))' > policies.before
cat routes.before policies.before
```
The measurement on 2026-09-29 read as follows:
- `('envoy-external','Accepted=True','ResolvedRefs=True') 29`
- `('envoy-internal','Accepted=True','ResolvedRefs=True') 83`
- policies: SecurityPolicy 12, ClientTrafficPolicy 2, BackendTrafficPolicy 1
  and Backend 1, all `('True',)`.

Any non-True already in the baseline must be noted and not blamed on the bump.

2.4 Baseline per-hostname HTTP status through each VIP. This is the CONTENTS
baseline. Hostnames are pulled live, into /tmp only, and never committed.
```bash
cd /tmp/eg192-win
kubectl get httproute -A -o json | python3 -c '
import sys,json
vip={"envoy-internal":"192.168.55.103","envoy-external":"192.168.55.104"};seen=set()
for r in json.load(sys.stdin)["items"]:
  for p in r["spec"].get("parentRefs",[]):
    if p.get("sectionName")=="http" or p["name"] not in vip: continue
    for h in r["spec"].get("hostnames") or []:
      if (h,vip[p["name"]]) not in seen: seen.add((h,vip[p["name"]])); print(h,vip[p["name"]])' > hosts.txt
sweep() { while read -r h v; do printf '%s %s %s\n' "$v" "$(curl -sk -o /dev/null -w '%{http_code}' --max-time 8 --resolve "$h:443:$v" "https://$h/")" "$h"; done < hosts.txt; }
sweep > status.before; wc -l < hosts.txt; awk '{print $1,$2}' status.before | sort | uniq -c
# negative control -- proves the sweep can SEE a missing route (Envoy answers 404 for an unrouted host):
for v in 192.168.55.103 192.168.55.104; do curl -sk -o /dev/null -w "$v %{http_code}\n" --max-time 8 --resolve "nohost-negative-control.invalid:443:$v" https://nohost-negative-control.invalid/; done   # must print 404 twice
```
The measurement on 2026-09-29 read as follows:
- 96 host/VIP pairs; the sweep took 45 s.
- Internal (.103): 200×34, 302×28, 307×1, 401×2, 404×4, 503×1.
- External (.104): 200×15, 302×8, 404×2, 405×1.
- The negative control returned 404 on both VIPs.

2.5 Alerts and xDS baseline (Prometheus):
```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
q(){ curl -s --get http://localhost:19090/api/v1/query --data-urlencode "query=$1" | python3 -c 'import sys,json;r=json.load(sys.stdin)["data"]["result"];print(r[0]["value"][1] if r else "EMPTY")'; }
q 'sum(envoy_listener_manager_lds_update_rejected{namespace="network"})'   # baseline (2026-09-29: 0)
q 'sum(envoy_cluster_manager_cds_update_rejected{namespace="network"})'    # baseline (2026-09-29: 0)
q 'count(up{namespace="network",job="network/envoy-gateway"}==1)'          # must be 6
q 'min(probe_success{probe_class=~"http|dns"})'                            # must be 1
curl -s http://localhost:19090/api/v1/alerts | python3 -c 'import sys,json;print(sorted({a["labels"]["alertname"] for a in json.load(sys.stdin)["data"]["alerts"] if a["state"]=="firing" and a["labels"]["alertname"].startswith(("EnvoyGateway","InternalDns","IngressProbe"))}))'   # must be []
kill $PF 2>/dev/null
```
2.6 Upstream data-plane default still equals our pin (network read, not a premise):
```bash
curl -fsSL https://raw.githubusercontent.com/envoyproxy/gateway/v1.9.2/api/v1alpha1/shared_types.go | grep -o 'DefaultEnvoyProxyImage = "[^"]*"'
grep -o 'distroless-v[^ ]*' kubernetes/apps/network/envoy-gateway/app/gatewayclass.yaml
# both must name distroless-v1.39.1@sha256:eb2c01c13125d1629637cb4e4cce7207009fb7cc2c8027f9742758549d15b6f4
# (measured 2026-09-29). If they differ, STOP: §3 must also move the pin in the same commit.
```

**STOP** if any of these fails:
- a premise fails;
- a Deployment is below 3/3;
- a PDB allows 0 disruptions;
- the negative control does not print 404;
- an `EnvoyGateway*` alert is firing.

## 3. Steps (GitOps)

3.1 Bump the chart. This sed was dry-tested on a scratch copy on macOS (BSD
sed) and changes exactly one line: `-      version: 1.9.1` / `+      version: 1.9.2`.
```bash
cd /Users/mu/code/cberg-home-nextgen
sed -i '' 's/^\([[:space:]]*version:[[:space:]]*\)1\.9\.1$/\11.9.2/' kubernetes/apps/network/envoy-gateway/app/helmrelease.yaml
git diff --stat kubernetes/apps/network/envoy-gateway/app/helmrelease.yaml   # 1 file, 1 insertion, 1 deletion
```

3.2 Re-vendor the CRDs with the script. The SOP says never edit these by hand.
```bash
mise exec -- bash kubernetes/apps/network/envoy-gateway/crds/revendor.sh 1.9.2
```
The script's channel check must print both of these:
- `gateway-api-standard.yaml: content UNCHANGED (header-only diff)`
- a changed `envoy-gateway.yaml`

`git diff --stat` for this step, measured on a scratch copy:
- `gateway-api-standard.yaml`: 2 lines, header only.
- `envoy-gateway.yaml`: about 309 lines added and 32 removed; the removals are
  descriptions and the header.

**STOP and re-plan** if `gateway-api-standard.yaml` shows a CONTENT change. That
would mean the Gateway API channel moved and §5 no longer holds.

3.3 Leave `gatewayclass.yaml` unchanged. The Envoy pin already equals v1.9.2's
`DefaultEnvoyProxyImage` (§2.6 + premise `gatewayclass-pin-unchanged`).

3.4 Commit with `--only` (shared worktree), verify, then push:
```bash
cat > /tmp/eg192-msg.txt <<'EOF'
feat(envoy-gateway): chart 1.9.1 -> 1.9.2 + re-vendor CRDs

Gateway API bundle content unchanged (v1.6.1); envoyproxies CRD additive only.
Envoy data-plane image unchanged (v1.9.2 DefaultEnvoyProxyImage == pin).
Rolls envoy-internal/-external via shutdown-manager sidecar tag.
Plan: runbooks/maintenance/plans/envoy-gateway-1.9.2.md

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
git commit --only kubernetes/apps/network/envoy-gateway/app/helmrelease.yaml \
  kubernetes/apps/network/envoy-gateway/crds/envoy-gateway.yaml \
  kubernetes/apps/network/envoy-gateway/crds/gateway-api-standard.yaml -F /tmp/eg192-msg.txt
git log -1 --format=%s    # must be "feat(envoy-gateway): chart 1.9.1 -> 1.9.2 + re-vendor CRDs"; amend if not
git show --stat HEAD      # exactly the 3 files above
git push
```

3.5 Reconcile **Kustomization, then HelmRelease**, in that order. The SOP
(`envoy-gateway-upgrade.md` step 5) requires the CRDs to land before the
controller that reads them.
```bash
flux reconcile source git flux-system -n flux-system
flux reconcile kustomization envoy-gateway-crds -n network --with-source
flux reconcile kustomization envoy-gateway -n network
flux reconcile helmrelease envoy-gateway -n network
```

3.6 Watch the controller roll, then the data-plane rolls it triggers:
```bash
kubectl -n network rollout status deploy/envoy-gateway --timeout=300s
kubectl -n network rollout status deploy/envoy-internal --timeout=600s
kubectl -n network rollout status deploy/envoy-external --timeout=600s
```
`rollout status` can go green on the OLD generation (`feedback_rollout_status_old_generation`),
so §4.1 checks the live pod images directly.

## 4. Verification

4.1 Versions are actually live, not just declared:
```bash
kubectl -n network get hr envoy-gateway -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.lastAttemptedRevision}{"\n"}'   # True 1.9.2
kubectl -n network get pods -l control-plane=envoy-gateway -o jsonpath='{range .items[*]}{.spec.containers[0].image}{"\n"}{end}' | sort | uniq -c        # 3 x ...gateway:v1.9.2
kubectl -n network get pods -l app.kubernetes.io/component=proxy -o jsonpath='{range .items[*]}{range .spec.containers[*]}{.name}={.image}{"\n"}{end}{end}' | sort | uniq -c
#   expect: 6 x envoy=...envoy:distroless-v1.39.1@sha256:eb2c01c1...   (UNCHANGED)
#           6 x shutdown-manager=docker.io/envoyproxy/gateway:v1.9.2    (a v1.9.1 here = data plane not re-rendered)
kubectl -n network get pods -l app.kubernetes.io/component=proxy -o wide   # 3 per gateway, one per node (spread held)
```
- FAIL shape: any `v1.9.1` remaining, fewer than 6 proxy pods Ready, or two
  pods of one gateway on the same node.
- Guards against: a half-rolled data plane, or topology-spread collapse (seen
  2026-09-07, before `pod-template-hash` was added).

4.2 Route and policy acceptance must not regress. This is diffed against §2.3.
```bash
cd /tmp/eg192-win
# re-run the two §2.3 python blocks with > routes.after / > policies.after
diff routes.before routes.after && diff policies.before policies.after && echo ACCEPTANCE_UNCHANGED
```
- FAIL shape: any line moves to `Accepted=False` or `ResolvedRefs=False`, a
  count drops, or a policy kind gains a `False`.
- Guards against: the new controller translating the same objects differently.
  The listener-merge and SNI fixes change translation code paths.

4.3 **DNS gate, run TWICE** (`docs/sops/envoy-gateway-upgrade.md`, `k8s-gateway-dns.md`).
The CRD channel did not move, so this is low-stakes. The SOP makes it
mandatory for every EG bump, and it takes about 4 minutes per run.
```bash
for i in 1 2; do
  kubectl -n network rollout restart deploy/k8s-gateway
  kubectl -n network rollout status deploy/k8s-gateway --timeout=180s
  sleep 20
  for p in $(kubectl -n network get pods -l app.kubernetes.io/name=k8s-gateway -o name); do kubectl -n network logs $p --tail=80; done | grep -icE 'could not sync|failed to list'   # must print 0 (all 3 pods, not deploy/ = 1 pod)
  # Demonstrated able to match: the archived failure lines in docs/sops/k8s-gateway-dns.md:238-240 give 2 through this regex.
  awk '{print $2, $1}' /tmp/eg192-win/hosts.txt | head -20 | while read -r v h; do a=$(dig +short @192.168.55.101 "$h" | tail -1); [ "$a" = "$v" ] || echo "DNS MISMATCH $h -> '$a' (want $v)"; done; echo "dns pass $i done"
done
```
- FAIL shape: a non-zero sync-error count, or any `DNS MISMATCH` line. An empty
  answer (SERVFAIL) prints `''`, and the wrong VIP prints that VIP.
- Guards against: the latent k8s_gateway informer failure. Blackbox
  `probe_class="dns"` accepts ANY `192.168.x.x` answer, so this per-VIP check
  is the one that can see a wrong-VIP answer.

4.4 **CONTENTS**: every hostname still serves the same answer through its
Gateway.
```bash
cd /tmp/eg192-win && sweep > status.after   # (re-define sweep() from §2.4 if in a new shell)
join -j 3 <(sort -k3 status.before) <(sort -k3 status.after) | awk '$3!=$5 {print "CHANGED", $1, $2, $3, "->", $5}'
```
CONTENTS ASSERTION: the per-host HTTP status through its VIP is unchanged for all
96 host/VIP pairs. It is measured by the §2.4 `sweep` and compared to
`status.before`.
- Each `CHANGED` line gets re-probed once after 60 s, because an app pod can
  legitimately be mid-restart.
- PASS: every `CHANGED` line reverts to its baseline status on the re-probe.
- FAIL: any pair that stays at `404` (route gone; the negative control proved
  Envoy says 404 for an unrouted host) or `000` (listener or TLS rejected).
- FAIL: any `2xx/3xx/401` that stays at `5xx`.
- This check goes red on exactly the failure a Programmed=True Gateway hides: a
  listener or route that Envoy silently dropped from its xDS config.

4.5 Prometheus gates. Wait 10 minutes after §3.6 so the 5m windows cover only
new pods. Reuse `q()` from §2.5.
```bash
q 'count(up{namespace="network",job="network/envoy-gateway"}==1)'                               # 6
q 'sum(envoy_listener_manager_lds_update_rejected{namespace="network"})'   # 0 (all 6 pods are new after §3.6)
q 'sum(envoy_cluster_manager_cds_update_rejected{namespace="network"})'    # 0
q 'count(envoy_listener_manager_lds_update_rejected{namespace="network"})' # 6 (non-vacuous guard: an empty result cannot pass)
q 'sum(rate(envoy_http_downstream_rq_xx{namespace="network",envoy_response_code_class="2"}[5m]))' # > 0 (2026-09-29: ~1.03 rps)
q 'sum(rate(envoy_http_downstream_rq_xx{namespace="network",envoy_response_code_class="5"}[5m])) / sum(rate(envoy_http_downstream_rq_xx{namespace="network"}[5m]))'   # < 0.02 (baseline ~0.005)
q 'min(probe_success{probe_class=~"http|dns"})'                                                   # 1
```
- CONTROL: metric `envoy_http_downstream_rq_xx`. The 2xx rate must be `> 0`;
  that is the floor, and it guards against a data plane that is up but serves
  nothing. The 5xx ratio must be `< 0.02`. Scraped from all 6 proxy pods,
  measured 2026-09-29.
- CONTROL: metric `envoy_listener_manager_lds_update_rejected`. The raw
  counter summed over the 6 new pods must be `0` (increase() would miss a
  rejection of the initial xDS config before the first scrape, because it
  ignores a new series' first sample), with a series count of `6`. This is the direct signal for the listener-rejection
  bugs 1.9.2 fixes, and for any new translation Envoy refuses. The baseline was
  0 while the success counter read 1343, so the series is live and this gate
  can move.
- CONTROL: metric `envoy_cluster_manager_cds_update_rejected`. The raw
  counter summed over the 6 new pods must be `0` (same reason as LDS).
- CONTROL: metric `probe_success`. The minimum over the 5 http/dns blackbox
  probes must be `1`.
- CONTROL: alertname `EnvoyGatewayMetricsAbsent`. It must NOT be firing. It is
  the guard that makes the metric gates above non-vacuous: an empty `q` result
  prints `EMPTY`, and that is a FAIL, never a pass.
- CONTROL: alertname `EnvoyGateway5xxSustained`. It must NOT be firing.
- CONTROL: alertname `EnvoyGatewayPodCrashLooping`. It must NOT be firing.

4.6 Soak: re-run 4.4 and 4.5 once more 15 minutes later before closing the
window. After that, retire this plan file in the same commit series, per
`README.md`.

## 5. Rollback

A git revert is a real rollback **for this bump**. The general SOP warning
("assume `git revert` will NOT work") is about the Gateway API channel moving
under the `safe-upgrades` VAP. Here that channel is content-identical at
v1.6.1, so the VAP floor does not move and reverting re-applies the SAME
Gateway API CRDs. The only CRD delta reverts as follows:
- the reverted `envoyproxies` schema drops 73 optional fields;
- no stored EnvoyProxy uses them (1 object, which we author);
- the server-side apply of the 1.9.1 bundle is therefore accepted.

Confirm that before relying on it (step 5.1).

5.1 Pre-flight (read-only, ~30 s). This proves the revert bundle applies:
```bash
git show <sha-of-3.4>~1:kubernetes/apps/network/envoy-gateway/crds/envoy-gateway.yaml > /tmp/eg191-crds.yaml
git show <sha-of-3.4>~1:kubernetes/apps/network/envoy-gateway/crds/gateway-api-standard.yaml > /tmp/eg191-gwapi.yaml
kubectl apply --server-side --dry-run=server --field-manager=kustomize-controller -f /tmp/eg191-crds.yaml -f /tmp/eg191-gwapi.yaml 2>&1 | tee /tmp/eg191-dry.txt | grep -vc 'serverside-applied'   # must be 0 (2>&1: a rejection goes to stderr)
grep -c 'serverside-applied' /tmp/eg191-dry.txt   # must equal the `kind: CustomResourceDefinition` count in both files (positive count; a failed apply prints 0 here)
```

5.2 Revert and push:
```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <sha-of-3.4>
git log -1 --format=%s    # must be 'Revert "feat(envoy-gateway): chart 1.9.1 -> 1.9.2 + re-vendor CRDs"'
git show --stat HEAD      # the same 3 files
git push
flux reconcile source git flux-system -n flux-system
flux reconcile kustomization envoy-gateway-crds -n network --with-source
flux reconcile kustomization envoy-gateway -n network
flux reconcile helmrelease envoy-gateway -n network
```
If the HR is wedged `pending-upgrade`, follow `docs/sops/application-update.md`
§11 (clear the Helm lock) before reconciling.

5.3 Confirm it is back:
- Re-run 4.1 expecting `v1.9.1` on all 3 controller pods and all 6
  `shutdown-manager` containers. The data plane rolls back the same way, via
  the sidecar tag.
- Re-run 4.2, 4.3 (DNS gate twice), 4.4 and 4.5 against the SAME
  `/tmp/eg192-win/*.before` baselines. They must pass.

5.4 **Break-glass if the data plane is dark and git is unreachable.** Flux
fetches from GitHub over the same cluster DNS and egress, not through Envoy, so
a dark Envoy does not block the revert path. If the CONTROLLER is down, the
proxies keep serving their last good xDS config. A dead controller alone is
therefore not an outage; do not panic-delete proxy pods. If proxies are
crash-looping on the new sidecar, first try a
`kubectl -n network rollout undo deploy/envoy-internal` (and `envoy-external`)
as a stopgap. It will be re-rendered by the controller, so follow it
immediately with 5.2.

## 6. Interference notes

- **Attended window only (sat/sun), never nightly.** `touches.shared` carries
  `gateway` and `dns`, which are in `SHARED_INFRA_FLOOR`, so the plan derives
  HUMAN-GATED; `autonomy_override: human-gated` says so explicitly. It needs no
  reboot and no `exclusive`, but it should be the ONLY routing-perturbing plan
  in its window. See `conflicts_with`.
- **Run it FIRST among the plans, right after Step 0 settles.** §4.4 diffs 96
  hostnames. Any other plan that restarts an app with an HTTPRoute, in the same
  window, turns into a `CHANGED` line here. `conflicts_with` covers the known
  ones (`app-template-5.2.1`, `penpot-chart-1.10.0`). For any other same-window
  plan, run this one before it, or re-take the §2.4 baseline.
- The `conflicts_with` entries were added from this side only. The other plans
  do not list this one yet; `--validate` does not check reciprocity. Here is
  why each needs the reciprocal entry:
  - `app-template-5.2.1` (nightly 2026-10-02) and `penpot-chart-1.10.0`
    (sat-attended 2026-10-31) both declare `gateway/envoy`.
  - `helm-drift-detection`, `flux-fleet-0.60.0` and
    `flux-reconciler-impersonation` change how THIS HelmRelease is applied.
  - `flux-oci-chart-sources` declares `dns-internal`.
  - `chart-patches-coredns-reloader-blackbox` rolls the blackbox exporter that
    §4.5 reads.
- **What the rollout does to traffic:** both proxy Deployments roll surge-first,
  1 pod at a time: maxSurge 1, maxUnavailable 0, PDB minAvailable 2. Each old
  pod drains via its shutdown-manager, so in-flight requests complete.
  Long-lived connections (websockets, SSE, HA frontend, streaming media) will be
  cut once per pod roll and must reconnect. That is interruption, not data loss.
- **k8s-gateway is restarted twice** (DNS gate). It runs 3 replicas behind PDB
  minAvailable 2, so internal name resolution should not gap. The external-dns
  / public DNS path is not touched.
- **Authentik forward-auth** (12 SecurityPolicies) is enforced by Envoy.
  §4.2 asserts all of them stay `Accepted`, and §4.4 sees a broken auth
  redirect as a 302 turning into a 5xx or 404. The v1.7.0 ext-auth regression
  cited in the HR comment is not in the 1.9.1...1.9.2 range.
- **Next time the data-plane image moves:** this bump did not require editing
  the `gatewayclass.yaml` Envoy pin, because upstream kept the same Envoy.
  §2.6 is the reusable check. Copy it into the next EG plan.
