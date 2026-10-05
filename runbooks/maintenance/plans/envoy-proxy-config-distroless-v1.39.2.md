---
plan_id: envoy-proxy-config-distroless-v1.39.2
component: envoy-proxy-config
also_covers:
  - docker.io/envoyproxy/envoy        # the Envoy DATA-PLANE image pinned in EnvoyProxy/network/envoy-proxy-config
pr: null                              # no Renovate PR: the `distroless-v` prefix is not docker-versionable
                                      # (see gatewayclass.yaml comment); surfaced by coverage.py, sweep
                                      # cycle 5a150729-bc69-4faa-a62d-d99cf768d726
kind: image
current: "distroless-v1.39.1@sha256:eb2c01c13125d1629637cb4e4cce7207009fb7cc2c8027f9742758549d15b6f4"
target: "distroless-v1.39.2@sha256:dced08cf7c472e1a1d067f906878266078eeeb63c110b4961882c039a622853a"
update_type: patch
risk: medium                          # low PROBABILITY (v1.39.1...v1.39.2 = 8 commits, ZERO files under
                                      # source/; one BoringSSL dependency bump + packaging + base image
                                      # refresh) but total IMPACT: this image IS the only HTTP data plane;
                                      # the bump rolls all 6 proxy pods of envoy-internal + envoy-external.
est_duration_min: 45                  # §2 10 + §3 5 + rolls ~8 + §4 (10m metric wait + sweeps) ~15 + soak 7
needs_reboot: false
exclusive: false
touches:
  namespaces: [network]
  resources:
    - envoyproxy/network/envoy-proxy-config                      # spec.provider.kubernetes.envoyDeployment.container.image
    - deployment/network/envoy-internal                          # ROLLS: envoy container 1.39.1 -> 1.39.2 (3 pods, surge-first)
    - deployment/network/envoy-external                          # ROLLS: envoy container 1.39.1 -> 1.39.2 (3 pods, surge-first)
    - kubernetes/apps/network/envoy-gateway/app/gatewayclass.yaml
  shared:
    - gateway/envoy                   # envoy-internal (.103) + envoy-external (.104) carry EVERY
                                      # HTTPRoute (112 routes live 2026-10-03)
    - public-edge                     # envoy-external is the internet-facing data plane
    - authentik                       # 12 SecurityPolicies (forward-auth) are enforced inside Envoy
    - monitoring                      # §4 reads Prometheus + blackbox probe_success (the instrument)
depends_on:
  # - envoy-gateway-1.9.2 (RESOLVED 2026-10-04: executed + retired 418faa1e (now:2026-10-03); dead ref removed per the dead-ref convention)
    # (a) the *envoyproxy/envoy* deny rule couples this pin to the
                                      # controller: move the data plane only on top of the CURRENT
                                      # controller (v1.9.2 compiles 1.39.1, measured below), and
                                      # (b) that plan's premise `gatewayclass-pin-unchanged`
                                      # expect_exact's the 1.39.1 pin -- running this first would make
                                      # a vetted plan fail its own premise. See §6 for the fold option.
conflicts_with:
  - app-template-5.2.1                # declares gateway/envoy; rolls ~78 apps whose routes §4.3's
                                      # per-host status diff reads -- an app roll mid-window fakes
                                      # (or masks) a data-plane regression
  - penpot-chart-1.10.0               # declares gateway/envoy-external; same §4.3 poisoning
  - talos-linux-1.14.2                # node roll drains proxy pods; PDB minAvailable 2 has ONE
                                      # disruption to give -- a drain and this roll would compete for it
  - external-dns-1.23.0               # public-edge: reads Gateway envoy-external's target; a public
                                      # DNS change mid-roll makes §4.3 external rows unattributable
  - coredns-1.48.2                    # cluster DNS under the §4 Prometheus/blackbox instrument path
  - chart-patches-coredns-reloader-blackbox   # rolls prometheus-blackbox-exporter = the probe_success
                                      # instrument §4.4 reads, and CoreDNS
  - flux-fleet-0.60.0                 # upgrades kustomize-controller, which applies gatewayclass.yaml
                                      # and carries the §5 revert path
  - flux-reconciler-impersonation     # exclusive; rewrites how kustomize-controller applies this
                                      # No kube-prometheus-stack plan is open (checked 2026-10-03). If one
                                      # appears it MUST be added here -- §4 reads Prometheus.
capability_change: false              # same-behaviour patch: 0 source/ changes upstream, no new route,
                                      # permission, API surface or exposure; the EnvoyProxy object only
                                      # changes its image string.
rollback_class: git-revert            # the old image is digest-pinned, still published, and cached on all
                                      # 3 nodes (imagePullPolicy IfNotPresent); no CRD, no state, no
                                      # migration. §5 is a one-line digest restore.
autonomy_override: human-gated        # shared `gateway` derives HUMAN-GATED via SHARED_INFRA_FLOOR anyway;
                                      # attended window only.
security_ref: F-61035b6e              # security driver; detail on the DB record only (review 2026-10-05)
finding_refs: [F-4a6327dd, F-61035b6e]  # version row for this target + the planner-raised plan-section row
review: null
status: draft
window: null
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/envoy-gateway-upgrade.md
  - docs/sops/gateway-api-httproute.md
generated: "2026-10-03"
premises:
  - id: controller-is-1.9.2
    why: "depends_on envoy-gateway-1.9.2. If the controller is still 1.9.1 that plan has not run, and running this one first fails its premise gatewayclass-pin-unchanged."
    run: kubectl get helmrelease envoy-gateway -n network -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: "1.9.2"
  - id: envoy-gateway-hr-ready
    why: "Do not move the data plane under a failing controller; it renders the proxy Deployments."
    run: kubectl get helmrelease envoy-gateway -n network -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: repo-pin-is-1.39.1
    why: "current: claims the 1.39.1 digest pin. If someone already moved it, §3.1's sed matches nothing and §5's restore target is wrong."
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

# envoy-proxy-config: Envoy data plane distroless-v1.39.1 -> distroless-v1.39.2

## 1. Summary & why held

**What changes.** One line in `kubernetes/apps/network/envoy-gateway/app/gatewayclass.yaml`:
the `EnvoyProxy/network/envoy-proxy-config` container image, digest-pinned, moves from
`docker.io/envoyproxy/envoy:distroless-v1.39.1@sha256:eb2c01c1…` to
`docker.io/envoyproxy/envoy:distroless-v1.39.2@sha256:dced08cf7c472e1a1d067f906878266078eeeb63c110b4961882c039a622853a`.
The Envoy Gateway controller re-renders both proxy Deployments (`envoy-internal`,
`envoy-external`) and they roll, 3 pods each. Nothing else moves: no chart, no CRD,
no shutdown-manager sidecar, no k8s-gateway restart.

**Why held.** `runbooks/auto-update-policy.yaml` rule `*envoyproxy/envoy*`: the Envoy
data-plane image is coupled to the controller and is the only HTTP data plane in the
cluster.

**Upstream evidence (Envoy v1.39.2, released 2026-10-01).**
- `changelogs/1.39.2.yaml` at tag v1.39.2 has exactly two entries: one `bug_fixes` entry
  for `area: tls` (a BoringSSL update), and one `removed_config_or_runtime` entry: "Removed
  Debian bullseye (11) packaging". The GitHub release adds "Refreshed the Ubuntu build and
  distroless Docker base images."
- `compare/v1.39.1...v1.39.2`: 8 commits, 66 files, **0 files under `source/`**. The
  only build-affecting change is the BoringSSL pin in `bazel/repository_locations.bzl`.
  No Envoy behaviour, xDS API or config semantics change.
- Upstream labels this a security release (4 Envoy lines patched the same day). Per
  `docs/sops/vulnerability-disclosure.md` the advisory detail does not belong in this
  file; it is recorded on F-61035b6e (`security_ref`, see the frontmatter).

**Registry facts (measured 2026-10-03, Docker Hub v2 API).**
- `distroless-v1.39.2` is an OCI index, `sha256:dced08cf7c472e1a1d067f906878266078eeeb63c110b4961882c039a622853a`.
  It covers linux/amd64 (`sha256:bb26a0a1…`) and linux/arm64.
- `distroless-v1.39.1` still resolves to `sha256:eb2c01c1…`. That is byte-equal to the
  `imageID` of the `envoy` container in all 6 live proxy pods, so the rollback target
  is published and node-cached.

**Compatibility with the controller: COMPATIBLE.**
- Every EG tag compiles in `DefaultEnvoyProxyImage` (`api/v1alpha1/shared_types.go`).
  At v1.9.1, at v1.9.2 and at the `release/v1.9` branch head on 2026-10-03, it is
  `distroless-v1.39.1@sha256:eb2c01c1…`. No EG release ships 1.39.2 yet, and there is
  no v1.9.3.
- The EG compatibility matrix (gateway.envoyproxy.io/news/releases/matrix) lists
  v1.9 ↔ `distroless-v1.39.x`. It states: "The Envoy Proxy column shows the supported
  minor version. The exact image that a given Envoy Gateway patch release ships may be
  a newer patch within that same minor version."
- So 1.39.2 under EG 1.9.x is inside the supported matrix. The thing that would be
  untested is a different Envoy MINOR (1.40), and that is not what this plan does.

**Repo correction (reported, not planned around).** The deny rule's reason says this pin
moves "only in the SAME change as the gateway-helm chart bump … never on its own". That
is stricter than upstream's stated contract. Read literally, a security-only Envoy patch
inside the supported minor could never land until EG cuts a release. This plan follows
upstream's matrix, and it keeps the rule's real intent through `depends_on` (the
controller is current first) and the attended window. The rule text should say
"MINOR moves only with the chart; same-minor patches may lead the compiled default".

**Verdict.** This is a genuinely small patch, but it rolls every HTTP-serving pod, so
it runs in an attended window and is human-gated. No reboot.

## 2. Pre-checks (read-only, ~10 min)

Run these AFTER Step 0 of the window has settled, and AFTER `envoy-gateway-1.9.2` has
finished its §4.6 soak if that plan ran earlier in the same window.

2.1 Premises: `.venv/bin/python3 runbooks/plan-premises.py envoy-proxy-config-distroless-v1.39.2`.
Every premise must PASS.

2.2 Flux, workloads and PDBs:
```bash
flux get kustomizations -n network | grep -E 'envoy-gateway'          # both Ready True
kubectl -n network get deploy envoy-gateway envoy-internal envoy-external   # all 3/3
kubectl -n network get pdb envoy-internal envoy-external                    # ALLOWED DISRUPTIONS 1 each
kubectl -n network get pods -l app.kubernetes.io/component=proxy -o wide    # 3 per gateway, one per node
```

2.3 Upstream target is still what this plan pins. This is a network read, not a premise.
```bash
T=$(curl -fsSL "https://auth.docker.io/token?service=registry.docker.io&scope=repository:envoyproxy/envoy:pull" | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
for t in distroless-v1.39.2 distroless-v1.39.1; do echo "$t $(curl -fsSI -H "Authorization: Bearer $T" -H 'Accept: application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json' https://registry-1.docker.io/v2/envoyproxy/envoy/manifests/$t | grep -i docker-content-digest)"; done
# must print (measured 2026-10-03):
#   distroless-v1.39.2 docker-content-digest: sha256:dced08cf7c472e1a1d067f906878266078eeeb63c110b4961882c039a622853a
#   distroless-v1.39.1 docker-content-digest: sha256:eb2c01c13125d1629637cb4e4cce7207009fb7cc2c8027f9742758549d15b6f4
curl -fsSL https://raw.githubusercontent.com/envoyproxy/gateway/v1.9.2/api/v1alpha1/shared_types.go | grep -o 'DefaultEnvoyProxyImage = "[^"]*"'
# must name distroless-v1.39.1 (same Envoy MINOR 1.39). If a NEWER EG patch exists and compiles
# 1.39.2+, prefer that chart bump and supersede this plan. If it names any 1.40.x, STOP: re-plan.
```
- FAIL shape: a different digest for 1.39.2 (the tag was re-pushed), or an empty line
  (tag gone or registry unreachable). Either is a STOP.

2.4 Baseline Envoy build version on all 6 pods. This is the input to the §4.1 CONTENTS
assertion.
```bash
mkdir -p /tmp/envoy1392-win && cd /tmp/envoy1392-win
envver() { i=0; for p in $(kubectl -n network get pods -l app.kubernetes.io/component=proxy -o name); do
  port=$((19100+i)); i=$((i+1))
  kubectl -n network port-forward "$p" "$port":19000 >/dev/null 2>&1 & pf=$!; sleep 2
  v=$(curl -s --max-time 5 "http://localhost:$port/server_info" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['version'].split('/')[1], d['state'])" 2>/dev/null)
  kill $pf 2>/dev/null; echo "${p#pod/} ${v:-UNREADABLE}"; done; }
envver | tee ver.before
# 2026-10-03 (one pod sampled live): "1.39.1 LIVE". Expect 6 lines "<pod> 1.39.1 LIVE".
```
The instrument was measured live on 2026-10-03. The Envoy admin endpoint is bound to the
pod's localhost:19000, and port-forward reaches it. `server_info.version` reads
`b579d07d…/1.39.1/Clean/RELEASE/BoringSSL`.

2.5 Baseline route and policy acceptance. Write it to files; §4.2 diffs against them.
```bash
cd /tmp/envoy1392-win
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
routes > routes.before; policies > policies.before; cat routes.before policies.before
```
Any non-True line already in the baseline must be noted and not blamed on this change.

2.6 **Behavioural baseline of BOTH gateways.** Record the per-hostname HTTP status
through each VIP. Hostnames are pulled live into /tmp only and never committed.
```bash
cd /tmp/envoy1392-win
kubectl get httproute -A -o json | python3 -c '
import sys,json
vip={"envoy-internal":"192.168.55.103","envoy-external":"192.168.55.104"};seen=set()
for r in json.load(sys.stdin)["items"]:
  for p in r["spec"].get("parentRefs",[]):
    if p.get("sectionName")=="http" or p["name"] not in vip: continue
    for h in r["spec"].get("hostnames") or []:
      if (h,vip[p["name"]]) not in seen: seen.add((h,vip[p["name"]])); print(h,vip[p["name"]])' > hosts.txt
sweep() { while read -r h v; do printf '%s %s %s\n' "$v" "$(curl -sk -o /dev/null -w '%{http_code}' --max-time 8 --resolve "$h:443:$v" "https://$h/")" "$h"; done < /tmp/envoy1392-win/hosts.txt; }
sweep > status.before; wc -l < hosts.txt; awk '{print $1,$2}' status.before | sort | uniq -c
awk '{print $2}' hosts.txt | sort | uniq -c        # BOTH 192.168.55.103 and 192.168.55.104 must appear
# negative control -- proves the sweep can SEE a missing route (Envoy answers 404 for an unrouted host):
for v in 192.168.55.103 192.168.55.104; do curl -sk -o /dev/null -w "$v %{http_code}\n" --max-time 8 --resolve "nohost-negative-control.invalid:443:$v" https://nohost-negative-control.invalid/; done   # must print 404 twice
```
On 2026-09-29 the same sweep covered 96 host/VIP pairs on both VIPs in about 45 s, and
the negative control returned 404 on both.

2.7 Prometheus and alert baseline:
```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
q(){ curl -s --get http://localhost:19090/api/v1/query --data-urlencode "query=$1" | python3 -c 'import sys,json;r=json.load(sys.stdin)["data"]["result"];print(r[0]["value"][1] if r else "EMPTY")'; }
q 'count(up{namespace="network",job="network/envoy-gateway"}==1)'          # 6   (2026-10-03: 6)
q 'sum(envoy_listener_manager_lds_update_rejected{namespace="network"})'   # 0   (2026-10-03: 0)
q 'sum(envoy_cluster_manager_cds_update_rejected{namespace="network"})'    # 0   (2026-10-03: 0)
q 'sum(rate(envoy_http_downstream_rq_xx{namespace="network",envoy_response_code_class="2"}[5m]))'  # >0 (2026-10-03: ~1.03)
q 'min(probe_success{probe_class=~"http|dns"})'                            # 1   (2026-10-03: 1, over 5 probes)
curl -s http://localhost:19090/api/v1/alerts | python3 -c 'import sys,json;print(sorted({a["labels"]["alertname"] for a in json.load(sys.stdin)["data"]["alerts"] if a["state"]=="firing" and a["labels"]["alertname"].startswith(("EnvoyGateway","IngressProbe"))}))'   # must be []
```

**STOP** if any of these fails:
- a premise fails;
- §2.3 shows a different digest;
- a proxy Deployment is below 3/3;
- a PDB allows 0 disruptions;
- `ver.before` has an `UNREADABLE` line (the §4.1 instrument is then blind);
- the negative control does not print 404 twice;
- an `EnvoyGateway*` or `IngressProbe*` alert is firing.

## 3. Steps (GitOps)

3.1 Move the pin and annotate it. Both edits were dry-tested on a scratch copy on
macOS (BSD sed + python3). The resulting diff is the image line
`-          image: docker.io/envoyproxy/envoy:distroless-v1.39.1@sha256:eb2c01c1…`
replaced by
`+          image: docker.io/envoyproxy/envoy:distroless-v1.39.2@sha256:dced08cf…`,
plus 5 comment lines above it. The file still parses as YAML.
```bash
cd /Users/mu/code/cberg-home-nextgen
F=kubernetes/apps/network/envoy-gateway/app/gatewayclass.yaml
sed -i '' 's|envoyproxy/envoy:distroless-v1\.39\.1@sha256:eb2c01c13125d1629637cb4e4cce7207009fb7cc2c8027f9742758549d15b6f4$|envoyproxy/envoy:distroless-v1.39.2@sha256:dced08cf7c472e1a1d067f906878266078eeeb63c110b4961882c039a622853a|' "$F"
python3 - "$F" <<'EOF'
import sys
p=sys.argv[1]; s=open(p).read()
anchor="          image: docker.io/envoyproxy/envoy:distroless-v1.39.2@"
assert s.count(anchor)==1, "anchor not unique -- sed did not apply; STOP"
note=("          # 2026-10 (plan envoy-proxy-config-distroless-v1.39.2): moved AHEAD of the\n"
      "          # compiled default (EG v1.9.x compiles v1.39.1) to upstream's v1.39.2\n"
      "          # patch. Same Envoy MINOR, which the EG compatibility matrix declares\n"
      "          # supported (\"may be a newer patch within that same minor\").\n"
      "          # A MINOR move still travels only with the gateway-helm chart bump.\n")
open(p,"w").write(s.replace(anchor, note+anchor))
EOF
git diff --stat "$F"                       # 1 file, 6 insertions(+), 1 deletion(-)
grep -c 'distroless-v1.39.2@sha256:dced08cf7c472e1a1d067f906878266078eeeb63c110b4961882c039a622853a' "$F"   # 1
python3 -c "import yaml,sys;list(yaml.safe_load_all(open('$F')));print('YAML_OK')"
```

3.2 Commit with `--only` (shared worktree), verify, then push:
```bash
cat > /tmp/envoy1392-msg.txt <<'EOF'
feat(envoy-gateway): Envoy data plane distroless-v1.39.1 -> v1.39.2

Digest-pinned. Same Envoy minor as EG 1.9.x's compiled default (matrix:
v1.9 <-> 1.39.x). Upstream diff: 0 source/ files, BoringSSL + packaging only.
Rolls envoy-internal/-external (3+3 pods, surge-first).
Plan: runbooks/maintenance/plans/envoy-proxy-config-distroless-v1.39.2.md

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
git commit --only kubernetes/apps/network/envoy-gateway/app/gatewayclass.yaml -F /tmp/envoy1392-msg.txt
git log -1 --format=%s    # must be "feat(envoy-gateway): Envoy data plane distroless-v1.39.1 -> v1.39.2"; amend if not
git show --stat HEAD      # exactly gatewayclass.yaml
git push
```

3.3 Reconcile. The SOP sequence for this Kustomization is: source, then the app
Kustomization. No HelmRelease reconcile is needed, because the EnvoyProxy CR is
applied by Kustomization `network/envoy-gateway` and not by the chart.
```bash
flux reconcile source git flux-system -n flux-system
flux reconcile kustomization envoy-gateway -n network
kubectl -n network get envoyproxy envoy-proxy-config -o jsonpath='{.spec.provider.kubernetes.envoyDeployment.container.image}{"\n"}'   # ...distroless-v1.39.2@sha256:dced08cf...
```

3.4 Watch both data-plane rolls:
```bash
kubectl -n network rollout status deploy/envoy-internal --timeout=600s
kubectl -n network rollout status deploy/envoy-external --timeout=600s
```
`rollout status` can go green on the OLD generation
(`feedback_rollout_status_old_generation`), so §4.1 checks the live pods directly.

## 4. Verification

4.1 **CONTENTS ASSERTION: every proxy pod runs the 1.39.2 binary and is LIVE.**
```bash
kubectl -n network get pods -l app.kubernetes.io/component=proxy -o jsonpath='{range .items[*]}{range .status.containerStatuses[?(@.name=="envoy")]}{.imageID}{"\n"}{end}{end}' | sort | uniq -c
#   expect: 6 x docker.io/envoyproxy/envoy@sha256:dced08cf7c472e1a1d067f906878266078eeeb63c110b4961882c039a622853a
cd /tmp/envoy1392-win && envver | tee ver.after       # envver() from §2.4
grep -c ' 1\.39\.2 LIVE$' ver.after                   # must print 6
grep -vc ' 1\.39\.2 LIVE$' ver.after                  # must print 0
kubectl -n network get pods -l app.kubernetes.io/component=proxy -o wide   # 3 per gateway, one per node
```
- PASS: 6 lines `<pod> 1.39.2 LIVE`, 6 × the `dced08cf…` imageID, and each gateway
  spread one pod per node.
- FAIL shape: a `1.39.1` line means a pod was not re-rendered, or the roll is
  half-done. `UNREADABLE` means the admin endpoint is not answering. A state other than
  `LIVE` (`PRE_INITIALIZING`, `DRAINING`) means the pod has not reached config. Two
  pods of one gateway on the same node means the spread collapsed (seen 2026-09-07).
- The gate can fail: `ver.before` reads `1.39.1` on these same pods (measured
  2026-10-03), so the `1\.39\.2` grep returns 0 against the pre-state.

4.2 Route and policy acceptance must not regress. Diff against §2.5:
```bash
cd /tmp/envoy1392-win && routes > routes.after && policies > policies.after
diff routes.before routes.after && diff policies.before policies.after && echo ACCEPTANCE_UNCHANGED
```
- FAIL shape: a line moves to `Accepted=False` or `ResolvedRefs=False`, a count drops,
  or a policy kind gains a `False`.
- The controller did not change, so this is the floor check, not the main signal.

4.3 **CONTENTS ASSERTION, behavioural probe of BOTH gateways.** Every hostname must
still serve the same answer through its own VIP.
```bash
cd /tmp/envoy1392-win && sweep > status.after   # sweep() from §2.6
awk '{print $1}' status.after | sort | uniq -c   # both .103 and .104 rows present, same counts as status.before
join -j 3 <(sort -k3 status.before) <(sort -k3 status.after) | awk '$3!=$5 {print "CHANGED", $1, $2, $3, "->", $5}'
```
- Re-probe each `CHANGED` line once after 60 s, because an app pod can legitimately be
  mid-restart.
- PASS: every `CHANGED` line returns to its baseline status on the re-probe, and both
  VIPs are present with unchanged row counts.
- FAIL: any pair that stays at `000`. That is a TLS or listener failure, the exact
  shape a TLS-library swap would produce. The §2.6 baseline has no `000` for a
  reachable host.
- FAIL: any pair that stays at `404` (the route was dropped; the negative control
  proved Envoy says 404 for an unrouted host).
- FAIL: any `2xx/3xx/401` that stays at `5xx`. A `302` that turns into a `5xx` is a
  broken Authentik forward-auth path.
- What it guards against: a Programmed=True Gateway with a data plane that
  handshakes or routes wrongly. Neither Flux nor the Gateway status can see that.

4.4 Prometheus gates. Wait 10 minutes after §3.4 so the 5m windows cover only the new
pods. Reuse `q()` from §2.7.
```bash
q 'count(up{namespace="network",job="network/envoy-gateway"}==1)'                               # 6
q 'sum(envoy_listener_manager_lds_update_rejected{namespace="network"})'   # 0
q 'count(envoy_listener_manager_lds_update_rejected{namespace="network"})' # 6 (non-vacuous: EMPTY cannot pass)
q 'sum(envoy_cluster_manager_cds_update_rejected{namespace="network"})'    # 0
q 'sum(rate(envoy_http_downstream_rq_xx{namespace="network",envoy_response_code_class="2"}[5m]))' # > 0
q 'sum(rate(envoy_http_downstream_rq_xx{namespace="network",envoy_response_code_class="5"}[5m])) / sum(rate(envoy_http_downstream_rq_xx{namespace="network"}[5m]))'   # < 0.02
q 'min(probe_success{probe_class=~"http|dns"})'                                                   # 1
```
- CONTROL: metric `envoy_http_downstream_rq_xx`. The 2xx rate must be `> 0`; that is
  the floor against a data plane that is up but serves nothing (2026-10-03 baseline
  ~1.03 rps). The 5xx ratio must be `< 0.02`.
- CONTROL: metric `envoy_listener_manager_lds_update_rejected`. The raw sum over the 6
  new pods must be `0`, with a series count of `6`. The raw counter is used, not
  `increase()`, because `increase()` drops a new series' first sample and would miss a
  rejection of the initial config. All 6 series are new after §3.4.
- CONTROL: metric `envoy_cluster_manager_cds_update_rejected`. The raw sum must be `0`.
- CONTROL: metric `probe_success`. The minimum over the 5 http/dns blackbox probes
  must be `1`.
- CONTROL: alertname `EnvoyGatewayMetricsAbsent`. It must NOT be firing. It is the
  guard that keeps the metric gates non-vacuous. An `EMPTY` from `q` is a FAIL, never
  a pass.
- CONTROL: alertname `EnvoyGateway5xxSustained`. It must NOT be firing.
- CONTROL: alertname `EnvoyGatewayPodCrashLooping`. It must NOT be firing.
- CONTROL: alertname `EnvoyGatewayPodNotReady`. It must NOT be firing.
- CONTROL: alertname `IngressProbeFailing`. It must NOT be firing.

All 5 alert rules were verified to exist live on 2026-10-03, in PrometheusRules
`envoy-gateway-alerts`, `gateway-availability-alerts` and `blackbox-exporter-alerts`.

4.5 Soak: re-run 4.3 and 4.4 once more, 7 minutes later. Then retire this plan file
in the same commit series, per `README.md`.

## 5. Rollback

There is no forward-only step. There is no CRD, no state, no migration and no
controller change. The old image is digest-pinned, still published (§2.3) and cached on
every node (`imagePullPolicy: IfNotPresent`, 6 pods currently run it).

5.1 Revert and push (≈2 min plus the roll):
```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <sha-of-3.2>
git log -1 --format=%s    # must be 'Revert "feat(envoy-gateway): Envoy data plane distroless-v1.39.1 -> v1.39.2"'
git show --stat HEAD      # exactly gatewayclass.yaml
grep -o 'envoy:distroless-v[^ ]*' kubernetes/apps/network/envoy-gateway/app/gatewayclass.yaml
#   must print envoy:distroless-v1.39.1@sha256:eb2c01c13125d1629637cb4e4cce7207009fb7cc2c8027f9742758549d15b6f4
git push
flux reconcile source git flux-system -n flux-system
flux reconcile kustomization envoy-gateway -n network
kubectl -n network rollout status deploy/envoy-internal --timeout=600s
kubectl -n network rollout status deploy/envoy-external --timeout=600s
```
If the revert conflicts because another commit touched the same lines, restore the pin
with the reverse sed instead. It was dry-tested: forward then reverse gives a
byte-identical file.
```bash
sed -i '' 's|envoyproxy/envoy:distroless-v1\.39\.2@sha256:dced08cf7c472e1a1d067f906878266078eeeb63c110b4961882c039a622853a$|envoyproxy/envoy:distroless-v1.39.1@sha256:eb2c01c13125d1629637cb4e4cce7207009fb7cc2c8027f9742758549d15b6f4|' kubernetes/apps/network/envoy-gateway/app/gatewayclass.yaml
```
Then commit it with `--only` as in §3.2.

5.2 Confirm the cluster is back:
- Re-run 4.1, expecting 6 × imageID `sha256:eb2c01c1…` and 6 × `1.39.1 LIVE`.
- Re-run 4.2, 4.3 and 4.4 against the SAME `/tmp/envoy1392-win/*.before` baselines.
  They must pass.

5.3 **Break-glass, if the data plane is dark and the revert cannot reach the cluster.**
Flux fetches from GitHub over cluster DNS and egress, not through Envoy, so a dark
Envoy does not block 5.1. If the new pods crash-loop, run
`kubectl -n network rollout undo deploy/envoy-internal` (and `envoy-external`) as a
stopgap. The controller re-renders these Deployments from the EnvoyProxy CR, so the
undo is overwritten at the next reconcile. Follow it with 5.1 immediately.

## 6. Interference notes

- **Attended window only (sat/sun), never nightly.** `touches.shared` carries
  `gateway/envoy` and is in `SHARED_INFRA_FLOOR`; `autonomy_override: human-gated`
  says so explicitly. No reboot and no `exclusive`, but this should be the only
  routing-perturbing plan in its window.
- **`depends_on: envoy-gateway-1.9.2`.** That plan is `vetted` and unwindowed. Its
  premise `gatewayclass-pin-unchanged` expect_exact's the 1.39.1 pin, and its §2.6
  STOPs if the pin differs. Running THIS plan first would invalidate a vetted plan.
  Same-window execution is fine if it is sequential: EG 1.9.2 runs through its §4.6
  soak, then this plan's §2 takes fresh baselines.
- **Faster alternative, operator's call.** Fold §3.1 into `envoy-gateway-1.9.2` §3.3
  as one commit. That gives one data-plane roll instead of two (EG 1.9.2 already rolls
  every proxy pod via the shutdown-manager tag). It requires amending that plan
  (its premise + §2.6 + §4.1 expectations) and re-reviewing it. This plan would then
  become `superseded`.
- **Run it FIRST among the remaining plans**, right after Step 0 (and EG 1.9.2 if
  present) settles. §4.3 diffs every hostname, so any app with an HTTPRoute restarted
  by another same-window plan becomes a `CHANGED` line here. `conflicts_with` covers
  the known ones.
- **Reciprocity.** The `conflicts_with` entries were added from this side only.
  `--validate` does not check reciprocity. The partners are:
  - `app-template-5.2.1` and `penpot-chart-1.10.0`: gateway/envoy;
  - `talos-linux-1.14.2`: a node drain competes for the single PDB disruption;
  - `external-dns-1.23.0`: public-edge;
  - `coredns-1.48.1` and `chart-patches-coredns-reloader-blackbox`: the instrument path;
  - `flux-fleet-0.60.0` and `flux-reconciler-impersonation`: the apply and revert path.
- **Traffic during the roll.** Both proxy Deployments roll surge-first, one pod at a
  time: strategy 25%/25% gives maxSurge 1 and maxUnavailable 0, and the PDB is
  minAvailable 2. The shutdown-manager drains each old pod (terminationGracePeriod
  360 s), so in-flight requests complete. Long-lived connections (websockets, SSE, the
  HA frontend, media streams) are cut once per pod and must reconnect. That is
  interruption, not data loss.
- **Not touched:** k8s-gateway (no CRD change, so no DNS gate is needed), external-dns
  and public DNS, cert-manager certificates, and the controller Deployment.
