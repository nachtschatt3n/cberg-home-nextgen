---
plan_id: cilium-1.20.2
component: cilium
pr: null                              # NO Renovate PR. The only open PR in the repo
                                      # is #212 (aqua:siderolabs/talos CLI pin) — verified
                                      # 2026-09-16 via `gh pr list` (1 open PR total).
                                      # cilium is held by the `*cilium*` deny rule in
                                      # runbooks/auto-update-policy.yaml, so no PR is opened.
kind: chart
current: "1.20.1"                     # LIVE on all 3 nodes, verified 2026-09-16:
                                      # helm release cilium.v13, ds/cilium image v1.20.1
target: "1.20.2"                      # chart published 2026-09-16T00:55:18Z (helm.cilium.io
                                      # index.yaml); image tag pushed 2026-09-15 20:28 UTC
update_type: patch                    # PATCH within the 1.20 line — see §1 "What the
                                      # dispatch got wrong". This is NOT the 1.19->1.20
                                      # traversal; that happened on 2026-08-03 (97989c9b).
risk: medium                          # Rated on the MEASURED change, not the component's
                                      # name. The rendered diff against OUR values is TWO
                                      # image digests and nothing else (§1.4) — byte-identical
                                      # ConfigMap, byte-identical DaemonSet spec otherwise.
                                      # Probability of failure: low. CONSEQUENCE of failure:
                                      # total (§6). That asymmetry is handled by
                                      # autonomy_override + the attended-slot requirement
                                      # below, NOT by inflating this number — precedent:
                                      # cilium-1.20.1 (executed 2026-08-19, addfd9aa) was
                                      # also rated medium for the identical change shape.
                                      # A reviewer who disagrees should change this ONE line.
est_duration_min: 50                  # 12 pre-checks ~10 · edit+commit+push ~5 · reconcile
                                      # + full DS roll ~8 · verification §4 ~12 · mandatory
                                      # 15-min settle. (Predecessor plan used 45; +5 for the
                                      # two gateway probes and the Prometheus contents gate.)
needs_reboot: false                   # HONEST: no node reboot, no drain, no Talos change.
                                      # Upstream's upgrade guide requires neither; the roll is
                                      # a DaemonSet RollingUpdate only. Verified: this plan
                                      # touches zero files under kubernetes/bootstrap/talos/.
                                      # Do NOT let the blast radius tempt you into `true` —
                                      # that would wrongly claim the reboot-capable Sunday
                                      # slot that talos-1.14.0 needs in full.
touches:
  namespaces:
    - kube-system                     # helmrelease/cilium, ds/cilium, deploy/cilium-operator
    - "ALL (cluster-wide)"            # every pod in the cluster rides this datapath; the
                                      # agent restart is per-node, not per-namespace
  resources:
    - helmrelease/cilium              # kube-system — the ONLY live pin (§1.3)
    - daemonset/cilium                # rolls on all 3 nodes; maxUnavailable 2 (§1.5)
    - deployment/cilium-operator      # 1 replica, strategy maxUnavailable 100% => brief gap
    - configmap/cilium-config         # rendered byte-identical at 1.20.2 (§1.4) but the
                                      # helm upgrade still rewrites it
    - kubernetes/apps/kube-system/cilium/app/helmrelease.yaml
    - kubernetes/bootstrap/apps/helmfile.yaml   # bootstrap/DR-only pin, inert at runtime
    - "14 LoadBalancer Services (VLAN 55 VIPs) — announced via CiliumL2AnnouncementPolicy"
    - "14 cilium-l2announce leases in kube-system"
  shared:
    - cni/cilium                      # the CNI itself: pod networking, kube-proxy
                                      # replacement, NetworkPolicy enforcement
    - gateway/envoy                   # Cilium supplies the LB IPs for svc/envoy-internal
                                      # (192.168.55.103) and svc/envoy-external
                                      # (192.168.55.104) via LB-IPAM + L2 announcement.
                                      # 108 HTTPRoutes (82 internal / 26 external) ride them.
    - coredns                         # in-cluster DNS resolution rides the pod datapath
    - monitoring                      # §4's contents gate reads Prometheus; the scrape
                                      # itself crosses the datapath being changed
    - "public edge"                   # envoy-external is the internet-facing gateway
    - "LAN service access (VLAN 55)"  # AdGuard DNS .5, Home Assistant .24, Music Assistant
                                      # .29, Plex .30, mosquitto .15 are reached by VIP
depends_on: []
conflicts_with:                       # SOLO SLOT. This is not a courtesy list: §6 states
                                      # the plan must share its window with nothing, and
                                      # window-scheduler.py honours ONLY this field —
                                      # a prose "run it alone" schedules nothing. Every
                                      # currently-open EXECUTABLE plan is listed, because
                                      # every one of them verifies over the network this
                                      # plan perturbs. Checked against
                                      # `maintenance-plan.py --open` on 2026-09-16.
  - talos-1.14.0                      # rolls all 3 nodes; needs the whole Sunday slot.
                                      # Compounding: agents restarting while a node drains.
  - multus-macvlan-foundation         # CNI-adjacent (Talos machine-config VLAN work)
  - flux-oci-chart-sources            # already declares conflicts_with: [talos-1.14.0] for
                                      # the same reason; a CNI roll restarts what it verifies
  - kube-prometheus-stack-91.4.0      # MANDATORY: §4's CONTENTS ASSERTION reads Prometheus.
                                      # The window's instrument is shared infra (README §4).
  - prometheus-crd-ownership          # same instrument, same night risk
  - otel-operator-0.21.0              # monitoring collector; currently nightly:2026-09-17
  - unpoller-v5.2.5                   # monitoring; currently nightly:2026-09-16
  - media-audit-durable-output        # sat-attended:2026-09-19
  - wazuh-2xx-edge-coverage           # sat-attended:2026-09-26 — touches the external
                                      # request path this plan can blackhole
  - external-dns-unowned-cnames       # sat-attended:2026-10-03 — DNS/edge records
  - nextcloud-mcp-0.187.1             # sat-attended:2026-10-03
  - absenty-drop-npm-runtime          # sun-attended:2026-09-20
  - nextcloud-34.0.4                  # sun-attended:2026-09-20
  - jellyfin-12.1                     # sun-attended:2026-10-11
security_ref: F-d3d1472f              # quay.io/cilium/cilium image record. Detail stays on
                                      # the finding; see §1.6. Companion: F-0075055f
                                      # (operator-generic image).
capability_change: false              # FACT, not a claim of safety: no feature flag, no
                                      # value, no user-visible behaviour changes. The
                                      # rendered manifest delta is two image digests (§1.4).
rollback_class: git-revert            # CLASS is honest — nothing here is forward-only: no
                                      # schema migration, no data conversion, no immutable
                                      # handle. But read §5 BEFORE trusting the word
                                      # "revert": the machinery that EXECUTES a git revert
                                      # runs on the datapath this plan changes.
autonomy_override: human-gated        # DELIBERATE AND LOAD-BEARING. Without this line the
                                      # facts above (capability_change:false +
                                      # rollback_class:git-revert + needs_reboot:false +
                                      # risk:medium) derive AUTO-NIGHT under
                                      # runbooks/autonomy-policy.yaml — its `forbid_shared`
                                      # lists only [storage, longhorn], so `cni/cilium` does
                                      # NOT block autonomy. This cluster's only data plane
                                      # must not roll unattended, and §4's last gate is an
                                      # operator-performed streaming check that no cron can
                                      # do. `human-gated` is the one legal value and it only
                                      # RESTRICTS (maintenance-plan.py:704).
finding_refs: [F-d3d1472f, F-0075055f]
status: draft
window: null                          # the scheduler assigns. §6 states the constraint:
                                      # an ATTENDED slot, alone.
sops_refs:
  - docs/sops/application-update.md
generated: "2026-09-16"
---

# cilium chart 1.20.1 → 1.20.2 (CNI datapath — plan lane by standing rule)

## 1) Summary & why held

### 1.1 What the dispatch got wrong (read this first)

The sweep dispatched this as *"1.20.0 carries Gateway-API / mutual-auth caveats"*,
implying a **1.19 → 1.20 traversal**. That is not what is in front of us.

**The cluster is already on 1.20.1.** Verified live 2026-09-16:

```
helm release  : cilium.v13, chart cilium-1.20.1, deployed 2026-08-19
ds/cilium     : quay.io/cilium/cilium:v1.20.1@sha256:ae9ea21f…
cilium-dbg    : Cilium: Ok  1.20.1 (v1.20.1-7d68cfb3)  ×3 nodes
```

The 1.19.6 → 1.20.0 minor happened on **2026-08-03** (`97989c9b`), with its
`CiliumLoadBalancerIPPool` v2alpha1 → v2 prerequisite landed separately first
(`95098c6c`). 1.20.0 → 1.20.1 followed on 2026-08-19 (`addfd9aa`, plan
`cilium-1.20.1`, since retired). **This plan is the second patch on a line we
have been running for six weeks.** Every 1.20 upgrade-note action item is
therefore already behind us — and, as §1.2 shows, three of the four never
applied to this cluster at all.

### 1.2 The deny-rule reason is stale — the hold is still right, the reason is wrong

`runbooks/auto-update-policy.yaml` holds `*cilium*` with:

> "CNI datapath — 1.20.0 carries Gateway-API/mutual-auth caveats that can affect
> streaming protocols (Music Assistant / Home Assistant). Plan + verify MA/HA
> streaming before upgrading; never an unattended bump."

**The "never an unattended bump" half is correct and this plan honours it.** The
stated *caveats*, however, are structurally inapplicable here — checked against
the live `cilium-config`, not against the rule text (authoring rule 8: a remedy
or a risk claim must come from upstream or the cluster, never from a deny-rule
reason written by the last agent):

| Claimed caveat | Live state | Verdict |
|---|---|---|
| Gateway-API | `enable-gateway-api` is **ABSENT** from `cm/cilium-config`. The only `GatewayClass` is `envoy`, controller `gateway.envoyproxy.io/gatewayclass-controller` (Envoy Gateway, chart `gateway-helm` 1.9.1 — a *separate product*). | Cilium's Gateway API controller is **not running**. Upstream's 1.20 note "Cilium's Gateway API support now requires Gateway API v1.6.1" cannot bite us; the installed CRD bundle is v1.6.1 anyway. |
| Mutual auth | `mesh-auth-enabled: false` | Not enabled. Upstream deprecated it in 1.20; we never used it. |
| Deprecated L7 policy rules (`kafka`/`l7`/`l7proto`) must be removed before 1.20 | **0 CiliumNetworkPolicies exist** cluster-wide (6 plain k8s NetworkPolicies, which this note does not cover). | Vacuous. |
| `CiliumNodeConfig` v2alpha1 → v2 | 0 objects; CRD serves v2 only. | Vacuous. |

**Repo correction owed** (do not silently plan around it): the deny rule's
*reason* string should be rewritten to the real one — *"the CNI is the cluster's
only data plane; every bump restarts it under every pod, so it is never
unattended"* — and its version-specific clause dropped. That is a policy edit,
code-reviewed, and out of scope for this plan file.

### 1.3 How cilium is delivered here — Flux, not bootstrap

This matters because it changes every step, and the two pins look identical in a
grep:

- **LIVE pin — what this plan edits.** A Flux `HelmRelease`
  `kube-system/cilium` (`kubernetes/apps/kube-system/cilium/app/helmrelease.yaml`),
  `version: 1.20.1`, values from the kustomize-generated ConfigMap
  `cilium-helm-values-*` (source: `app/helm-values.yaml`). helm-controller owns
  the release — its status reads *"Helm upgrade succeeded for release
  kube-system/cilium.v13"*, matching `helm history` revision 13. The
  Kustomization is `prune: false`, `wait: true`, interval 30m.
- **BOOTSTRAP-ONLY pin — inert at runtime.**
  `kubernetes/bootstrap/apps/helmfile.yaml` also says `version: 1.20.1`. It runs
  only at cluster re-bootstrap / DR. Bring it along in the same commit for DR
  parity; it has **zero** effect on the running cluster. (Leaving it behind has
  bitten before: `0737bd62` was a commit whose whole purpose was re-aligning this
  file after it drifted.)
- **The config leg is NOT touched.** `kubernetes/apps/kube-system/cilium/config/`
  (the LB-IPAM `pool` and the `l2-policy`) is a separate Kustomization that
  `dependsOn` cilium. This plan changes nothing in it. Any pool edit is its own
  change and must never ride along.

### 1.4 What actually changes — measured, not assumed

Rendered both chart versions locally against **our** `helm-values.yaml` and
diffed (1734 lines each side):

```
$ helm template cilium cilium/cilium --version 1.20.{1,2} -n kube-system -f app/helm-values.yaml
# non-label delta, in full:
-  image: "quay.io/cilium/cilium:v1.20.1@sha256:ae9ea21f7427fe24bc6ea7247eb552157a1b0a431744045d3f641545ca71d11b"
+  image: "quay.io/cilium/cilium:v1.20.2@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01"
-  image: "quay.io/cilium/operator-generic:v1.20.1@sha256:6c3885fc7b629099fdbe2a5c87869c86feb825fa18fae299eac0f61918d16ecf"
+  image: "quay.io/cilium/operator-generic:v1.20.2@sha256:64d8798350e8569b8e7622563fed6e44dce2625f311e4651b774816516c744fc"
```

Everything else in the 64 changed lines is the `helm.sh/chart: cilium-1.20.x`
label (46 lines). **`cm/cilium-config` renders byte-identical.** No value we set
gained or lost meaning; no DaemonSet field other than the image moved.

**CRDs:** the chart ships **no `crds/` directory** — Cilium's CRDs are
created/updated by the *operator* at startup, not by Helm. So there is no
`helm upgrade` CRD race to plan around; the CRD schema moves when the new
operator pod starts. Between 1.20.1 and 1.20.2 upstream changed no CRD schema
(the compare touches `operator/identitygc/crd_gc.go` — garbage-collection logic,
not schema).

**Upstream content** (primary: the `v1.20.1...v1.20.2` compare — 204 commits,
300 files, of which 166 are `bpf/` — plus `CHANGELOG.md` at tag `v1.20.2`).
A bugfix patch, no breaking changes, no action-required items. Fixes that land
directly on **our** configuration (`kubeProxyReplacement: true`,
`loadBalancer.mode: dsr`, `algorithm: maglev`, `routingMode: native`,
`bpf.masquerade: true`):

- *"Improve reliability for fast recovery of disrupted TCP connections that
  access a DSR-enabled Service"* — we run DSR.
- *"lb (fix): require active state for backend when using topology hints"*.
- *"Fix nodeport egress tuple reuse for closed connections"*.
- BPF NAT engine now drops ICMP error packets containing a fragmented
  TCP/UDP/SCTP packet.

The Gateway-API entries in the changelog (`fail closed on invalid ExternalAuth`,
listener status fixes) belong to **Cilium's own** Gateway API implementation —
not running here (§1.2). They are not a reason to take this patch, and not a
risk from it.

### 1.5 The one genuine surprise: the roll takes 2 of 3 nodes at once

```
$ kubectl get ds -n kube-system cilium -o jsonpath='{.spec.updateStrategy}'
{"rollingUpdate":{"maxSurge":0,"maxUnavailable":2},"type":"RollingUpdate"}
```

`maxUnavailable: 2` is the **cilium chart default** (confirmed in the 1.20.2
`values.yaml`), and `minReadySeconds` is 0. On a 3-node cluster that means **two
thirds of the datapath agents restart simultaneously**, and a slow image pull
holds both down together.

**The retired `cilium-1.20.1` plan asserted "DaemonSet RollingUpdate,
maxUnavailable 1" and "16 VIPs / 16 leases".** Both were wrong — it is 2, and
there are **14** LoadBalancer services and **14** `cilium-l2announce` leases
today. That plan's text would have understated the simultaneous blast radius by
2×. Corrected here; §3.3 offers the optional fix.

### 1.6 Security driver

A newer upstream tag now exists for both images, so the `[AR-029]`
*"already on the newest upstream tag"* premise that made `F-d3d1472f` and
`F-0075055f` **accepted** no longer holds — and per CLAUDE.md the only
remediation this household performs for a third-party image is *bump to a newer
tag*, which is exactly this plan. Both digests move (§1.4), so both findings are
answered. Detail stays on the finding records; nothing quantitative here.

---

## 2) Pre-checks

Run from `/Users/mu/code/cberg-home-nextgen`. **Every command below names an
object verified to exist on 2026-09-16.** Do not proceed if any premise fails.

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) PREMISE — cilium is fully healthy on all three nodes BEFORE we touch it.
kubectl -n kube-system get ds cilium \
  -o jsonpath='{.status.desiredNumberScheduled} {.status.numberReady}{"\n"}'   # expect: 3 3
for p in $(kubectl get pods -n kube-system -l k8s-app=cilium -o name); do
  echo -n "$p: "; kubectl -n kube-system exec "$p" -c cilium-agent -- cilium-dbg status --brief
done                                                                          # expect: 3× OK

# b) PREMISE — no module is already degraded (this is the baseline §4 compares to).
kubectl -n kube-system exec ds/cilium -c cilium-agent -- cilium-dbg status \
  | grep -E 'Modules Health'
#   baseline 2026-09-16: "Stopped(0) Degraded(0) OK(307)"

# c) PREMISE — the HelmRelease is Ready and actually on 1.20.1.
kubectl get hr -n kube-system cilium \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion}{"\n"}'
#   expect: True 1.20.1

# d) PREMISE — chart 1.20.2 is published (never bump to a version that isn't there).
curl -s https://helm.cilium.io/index.yaml | grep -c 'version: 1.20.2'          # expect: >= 1

# e) BASELINE — the LB table. §4 diffs against this file; take it AFTER Step 0
#    of the window (safe-update batch) has settled, immediately before §3.
kubectl get svc -A -o json | .venv/bin/python3 -c "
import sys, json
d = json.load(sys.stdin)
rows = sorted((i['metadata']['namespace'] + '/' + i['metadata']['name'],
               (i['status'].get('loadBalancer', {}).get('ingress') or [{}])[0].get('ip'))
              for i in d['items'] if i['spec']['type'] == 'LoadBalancer')
[print(n, ip) for n, ip in rows]
" > /tmp/cilium-lb-before.txt
wc -l < /tmp/cilium-lb-before.txt                                              # expect: 14

# f) BASELINE — L2 announcement leases.
kubectl get leases -n kube-system -o name | grep -c cilium-l2announce          # expect: 14

# g) PREMISE — LB-IPAM pool is not in conflict.
kubectl get ciliumloadbalancerippool pool \
  -o jsonpath='{.status.conditions[?(@.type=="cilium.io/PoolConflict")].status}{"\n"}'
#   expect: False

# h) BASELINE + PREMISE — the datapath is reachable from the LAN right now.
#    Domain-free: the hostname is read from the live HTTPRoute, never written here.
HINT=$(kubectl get httproute -n default echo-server -o jsonpath='{.spec.hostnames[0]}')
HEXT=$(kubectl get httproute -n office mealie   -o jsonpath='{.spec.hostnames[0]}')
curl -sk --resolve "$HINT:443:192.168.55.103" -o /dev/null \
  -w 'envoy-internal .103 -> %{http_code}\n' --max-time 10 "https://$HINT/"     # expect: 200
curl -sk --resolve "$HEXT:443:192.168.55.104" -o /dev/null \
  -w 'envoy-external .104 -> %{http_code}\n' --max-time 10 "https://$HEXT/"     # expect: 200
dig +short +time=2 @192.168.55.5 kubernetes.io > /dev/null && echo 'DNS VIP .5 OK'

# i) PREMISE — nothing else is in flight.
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
flux get helmreleases -A   | awk 'NR==1 || $5 != "True"'
#   expect: header only

# j) PREMISE — NO Talos operation of any kind is running, and talos-1.14.0 is not
#    executing tonight. Both roll the same nodes.
kubectl get nodes -o custom-columns='NAME:.metadata.name,STATUS:.status.conditions[-1].type,VERSION:.status.nodeInfo.kubeletVersion'
#   expect: 3× Ready, v1.36.0

# k) PREMISE — the git worktree is clean and synced (shared checkout).
git fetch origin main && git status --porcelain && git log --oneline -1 origin/main

# l) OPERATOR — no active Music Assistant stream / Plex playback. The per-node blip
#    is seconds, but do not roll the CNI mid-movie. This is a human judgement, and
#    it is the reason this plan is attended.
```

---

## 3) Steps

### 3.1 Drop an active-update marker

Suppresses the expected cluster-wide rollout noise so the `alert-triage-agent`
treats it as EXPECTED instead of paging (`docs/sops/application-update.md` §Step 1b):

```bash
cd /Users/mu/code/cberg-home-nextgen
runbooks/update-marker.sh add cilium kube-system 2 "chart 1.20.1 -> 1.20.2 CNI patch"
```

### 3.2 Bump the live pin

`kubernetes/apps/kube-system/cilium/app/helmrelease.yaml` — change the one line
under `spec.chart.spec`:

```yaml
      chart: cilium
      version: 1.20.2        # was 1.20.1
```

**Dry-tested on a scratch copy on macOS (BSD sed) — produces exactly one hunk:**

```bash
sed -i '' 's/^      version: 1\.20\.1$/      version: 1.20.2/' \
  kubernetes/apps/kube-system/cilium/app/helmrelease.yaml
```
```diff
-      version: 1.20.1
+      version: 1.20.2
```

### 3.3 Bump the bootstrap pin (DR parity, inert at runtime)

`kubernetes/bootstrap/apps/helmfile.yaml` holds pins for cilium **and** coredns
**and** cert-manager. A naive `s/1.20.1/1.20.2/` is safe today only by luck —
use the anchored form, **dry-tested on a scratch copy, changed exactly 1 line**
(`diff | grep -cE '^[<>]'` returned 2, i.e. one `-`/`+` pair):

```bash
.venv/bin/python3 - <<'PY'
import re
p = 'kubernetes/bootstrap/apps/helmfile.yaml'
s = open(p).read()
new = re.sub(r'(- name: cilium\n    namespace: kube-system\n    chart: cilium/cilium\n    version: )1\.20\.1',
             r'\g<1>1.20.2', s)
assert s != new, 'anchor did not match — STOP and inspect the file'
open(p, 'w').write(new)
PY
git diff --stat kubernetes/bootstrap/apps/helmfile.yaml   # expect: 1 file, 1 insertion, 1 deletion
```

### 3.4 OPTIONAL (recommended, separate commit) — halve the simultaneous blast radius

**This is an operator decision, deliberately not bundled into the upgrade
commit.** §1.5: the chart default rolls **2 of 3** agents at once. Adding four
lines to `kubernetes/apps/kube-system/cilium/app/helm-values.yaml` makes it one
at a time:

```yaml
updateStrategy:
  type: RollingUpdate
  rollingUpdate:
    maxUnavailable: 1
```

Supported by the chart's own `values.schema.json` (top-level `updateStrategy`
with `rollingUpdate.maxUnavailable`, verified against chart 1.20.2).

- **Take it** and the roll is slower (~3 node-steps instead of 2) but only one
  third of the datapath is ever down, and a stuck image pull cannot strand two
  nodes at once.
- **Skip it** and the behaviour is exactly what the last two cilium bumps did.
- It changes *future* cilium rolls too, which is why it gets **its own commit**
  and its own revert line in §5.

If taken, commit it **first and separately**, let Flux settle (the DS spec change
alone triggers a roll — so this is itself a full agent roll; budget +8 min), and
only then do §3.5. If that is more change than the window has appetite for,
skip §3.4 entirely — the upgrade does not depend on it.

### 3.5 Commit + push (SHARED worktree — path-scoped, never `git add -A`)

```bash
cd /Users/mu/code/cberg-home-nextgen
git fetch origin main && git merge --ff-only origin/main

cat > /tmp/cilium-msg.txt <<'EOF'
feat(cilium): chart 1.20.1 -> 1.20.2 (CNI patch; plan cilium-1.20.2)

Bugfix patch on the 1.20 line we have run since 2026-08-03. Rendered
delta against our values is two image digests (agent + operator-generic);
cilium-config renders byte-identical. Carries upstream DSR TCP-recovery
and nodeport tuple-reuse fixes that land on our kube-proxy-replacement +
DSR + maglev configuration.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_012bXdxrZGGHNy5e4RnF6seD
EOF

git commit --only \
  kubernetes/apps/kube-system/cilium/app/helmrelease.yaml \
  kubernetes/bootstrap/apps/helmfile.yaml \
  -F /tmp/cilium-msg.txt

# MANDATORY (concurrent sessions have swapped commit messages in this repo):
git log -1 --format=%s        # must be YOUR subject; if not: git commit --amend -F /tmp/cilium-msg.txt
git show --stat HEAD          # must list EXACTLY the two files above
git push origin main
```

### 3.6 Watch the roll — do not walk away

Flux's git interval picks the change up on its own; no manual reconcile is
required by the SOP. Agents restart **two at a time** (§1.5) unless §3.4 was
taken.

```bash
kubectl -n kube-system rollout status ds/cilium --timeout=10m
kubectl -n kube-system rollout status deploy/cilium-operator --timeout=5m
kubectl get pods -n kube-system -l k8s-app=cilium -o wide
```

### 3.7 On success

```bash
runbooks/update-marker.sh clear cilium
```

---

## 4) Verification

Every gate below states what its failure looks like. A gate that cannot fail is
not in this section.

**4.1 — The version actually moved, on every node.**

```bash
kubectl get hr -n kube-system cilium \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion}{"\n"}'
#   PASS: True 1.20.2      FAIL MODE: helm-controller reports UpgradeFailed / stays 1.20.1
kubectl -n kube-system get ds cilium -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
#   PASS: contains v1.20.2@sha256:2939231d0d3e3ebddc…
kubectl -n kube-system get deploy cilium-operator -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
#   PASS: contains operator-generic:v1.20.2@sha256:64d8798350e8569b…
```

**4.2 — CONTENTS ASSERTION (required by README §"Verification must assert
CONTENTS, not SHAPE").**

```
CONTENTS ASSERTION: every cilium agent is scraped AND reporting the new version —
measured by the Prometheus `cilium_version` series, compared to the pre-change
baseline of exactly 3 series labelled version="1.20.1".
```

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 >/dev/null 2>&1 & PF=$!
sleep 3
curl -s --get http://localhost:9090/api/v1/query \
  --data-urlencode 'query=count(cilium_version{version="1.20.2"})'
#   PASS: data.result[0].value[1] == "3"
curl -s --get http://localhost:9090/api/v1/query \
  --data-urlencode 'query=count(cilium_version{version="1.20.1"})'
#   PASS: data.result == []   (no agent left on the old version)
curl -s --get http://localhost:9090/api/v1/query \
  --data-urlencode 'query=count(up{job="cilium-agent"} == 1)'
#   PASS: "3"
kill $PF 2>/dev/null
```

*Why this can fail, and why the proxy would not:* `up == 1` alone would go green
with the agents scraped but stuck on the old image; `cilium_version` alone would
go **empty** — not red — if the ServiceMonitor broke and nothing were scraped.
Asserting `count(…{version="1.20.2"}) == 3` **and** `count(…{version="1.20.1"})`
empty **and** `count(up == 1) == 3` fails in all three directions: wrong version,
missing node, dead scrape. Measured baseline 2026-09-16: 3 series at 1.20.1,
`up{job="cilium-agent"}` = 1 on .11/.12/.13, ServiceMonitors `cilium-agent` and
`cilium-operator` present in `kube-system`.

**4.3 — Agent health on every node, not just the one `ds/cilium` happens to pick.**

```bash
for p in $(kubectl get pods -n kube-system -l k8s-app=cilium -o name); do
  echo -n "$p: "; kubectl -n kube-system exec "$p" -c cilium-agent -- cilium-dbg status --brief
done
#   PASS: 3× OK.  FAIL MODE: a degraded agent prints a non-OK summary.
for p in $(kubectl get pods -n kube-system -l k8s-app=cilium -o name); do
  kubectl -n kube-system exec "$p" -c cilium-agent -- cilium-dbg status | grep -E 'Modules Health'
done
#   PASS: Degraded(0) on all three, OK count >= 300 (baseline 307).
#   FAIL MODE: Degraded(n>0) — the brief summary can still read OK while a
#   subsystem is degraded, which is exactly why both lines are checked.
```

*Binary note:* both `cilium` and `cilium-dbg` exist in the agent container on
1.20.1 (verified). `cilium-dbg` is the current name; prefer it.

**4.4 — The LB table is byte-identical and the leases re-formed.**

```bash
kubectl get svc -A -o json | .venv/bin/python3 -c "
import sys, json
d = json.load(sys.stdin)
rows = sorted((i['metadata']['namespace'] + '/' + i['metadata']['name'],
               (i['status'].get('loadBalancer', {}).get('ingress') or [{}])[0].get('ip'))
              for i in d['items'] if i['spec']['type'] == 'LoadBalancer')
[print(n, ip) for n, ip in rows]
" > /tmp/cilium-lb-after.txt
diff /tmp/cilium-lb-before.txt /tmp/cilium-lb-after.txt && echo 'LB TABLE UNCHANGED'
#   PASS: no diff, 14 lines.  FAIL MODE: an IP goes empty (LB-IPAM failed to
#   re-allocate) or changes (a pin was lost) — both are user-visible outages.
kubectl get leases -n kube-system -o name | grep -c cilium-l2announce
#   PASS: 14.  FAIL MODE: fewer => some VIP is no longer being ARP-announced and
#   is dark on the LAN even though its Service still shows an IP.
```

**4.5 — BOTH gateway IPs still SERVE (the gate this plan exists for).**

Pods being Ready proves nothing here: the Envoy pods are not what this change
touches — the **LB IP and its L2 announcement** are. These probes pin the
connection to the specific VIP with `--resolve`, so they fail if that IP is dark
even while DNS and the pods are perfectly healthy. Hostnames are read from the
live HTTPRoutes, so no domain is written into this repo.

```bash
HINT=$(kubectl get httproute -n default echo-server -o jsonpath='{.spec.hostnames[0]}')
HEXT=$(kubectl get httproute -n office  mealie      -o jsonpath='{.spec.hostnames[0]}')
curl -sk --resolve "$HINT:443:192.168.55.103" -o /dev/null \
  -w 'envoy-internal .103 -> %{http_code}\n' --max-time 10 "https://$HINT/"
curl -sk --resolve "$HEXT:443:192.168.55.104" -o /dev/null \
  -w 'envoy-external .104 -> %{http_code}\n' --max-time 10 "https://$HEXT/"
#   PASS: 200 and 200 (both measured 2026-09-16 pre-change).
```

*Proof the gate can fail:* the identical probe aimed at an unused VLAN-55 address
returns `code=000` with `curl` exit 28 (measured). A dark VIP therefore reads as
a hard failure, not as a quiet 200 from somewhere else.

**4.6 — LAN VIP surface beyond the gateways.**

```bash
dig +short +time=2 @192.168.55.5 kubernetes.io > /dev/null && echo 'DNS VIP .5 OK'
curl -sk -o /dev/null -w 'HA .24:8123 -> %{http_code}\n' --max-time 8 http://192.168.55.24:8123
curl -sk -o /dev/null -w 'MA .29:8095 -> %{http_code}\n' --max-time 8 http://192.168.55.29:8095
#   PASS: DNS line prints, 200, 200 (all measured 2026-09-16 pre-change).
```

**4.7 — Policy enforcement and east-west traffic survived the restart.**

```bash
kubectl get netpol -A --no-headers | wc -l        # PASS: 6 (unchanged)
kubectl get events -A --field-selector type=Warning --sort-by='.lastTimestamp' | tail -20
#   PASS: no FailedCreatePodSandBox / CNI / NetworkNotReady entries after the roll.
```

**4.8 — OPERATOR GATE (the deny rule's actual requirement).** Play a stream
through Music Assistant and open the Home Assistant dashboard. Both must work.
This is the check no cron can perform and the reason `autonomy_override:
human-gated` is set. **Do not close the window without it.**

**4.9 — Settle.** Wait 15 minutes, then confirm no new firing alerts
(port-forward Prometheus per CLAUDE.md, filtering `Watchdog|InfoInhibitor`).

---

## 5) Rollback

### 5.1 The honest verdict

**A `git revert` genuinely does restore the datapath — but only if the machinery
that executes it is still on the network.** That is the real risk, and it is not
theoretical:

```
$ kubectl get pods -n flux-system -o custom-columns='NAME:…,HOSTNET:.spec.hostNetwork,IP:.status.podIP'
helm-controller-…        <none>   10.69.1.128
source-controller-…      <none>   10.69.2.132
kustomize-controller-…   <none>   10.69.1.200
```

**Every Flux controller runs on the pod network — the very datapath this plan
changes.** If the 1.20.2 agents come up broken, the GitOps rollback path is
*inside* the failure domain: source-controller may not reach GitHub, and
helm-controller may not reach the API server. Pushing a revert commit and waiting
is then a rollback that cannot execute, and the 30-minute reconcile interval
means you would wait half an hour to learn that.

What **does** survive, and is therefore the real recovery path:

- `kube-apiserver` runs `hostNetwork: true` on 192.168.55.11/12/13, and the
  kubeconfig points at the Talos VIP `https://192.168.55.10:6443`. **`kubectl`
  and `helm` from the Mac keep working with pod networking fully down.**
- `helm history cilium -n kube-system` retains revision **13 = cilium-1.20.1**
  (the currently deployed one), so a direct rollback target exists.
- Existing pods keep networking across an agent restart (BPF programs stay loaded
  in-kernel), so a broken agent degrades to "no new flows, no policy updates, no
  L2 announcements" rather than instant total loss — which is what buys you the
  minutes to run 5.3.

Nothing here is forward-only: no schema migration, no data conversion, no
immutable handle. Hence `rollback_class: git-revert`. But run the limb that
matches the failure, and **when in doubt use 5.3 first and reconcile git after** —
the cluster being right matters more than the cluster being tidy.

### 5.2 Limb A — normal regression, Flux healthy (the common case)

Use when cilium is unhappy but the cluster still reconciles (agents Ready,
`flux get hr` responds).

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <bump-commit-sha>     # add the §3.4 commit too, if taken
git log -1 --format=%s                     # confirm it is YOURS before pushing
git push origin main
flux reconcile source git flux-system
flux reconcile helmrelease cilium -n kube-system
kubectl -n kube-system rollout status ds/cilium --timeout=10m
```

Confirm restoration with §4.1 (expect `1.20.1` / `v1.20.1@sha256:ae9ea21f…`),
§4.3, §4.4 and §4.5.

### 5.3 Limb B — BREAK-GLASS: the datapath is broken, Flux cannot act

Use when agents crash-loop, VIPs are dark, or `flux` commands hang.

```bash
cd /Users/mu/code/cberg-home-nextgen      # REQUIRED: `helm` is a mise shim pinned in
                                          # this repo's .mise.toml (aqua:helm/helm 3.22.0).
                                          # Outside the repo it errors "No version is set
                                          # for shim: helm" — verified. Do not run these
                                          # from /tmp.

# 1. Stop Flux fighting you. Without this, helm-controller re-applies 1.20.2
#    within its 30m interval and undoes the rollback.
flux suspend helmrelease cilium -n kube-system

# 2. Roll the release back directly. Revision 13 == chart cilium-1.20.1.
helm history cilium -n kube-system          # confirm 13 is cilium-1.20.1 before using it
helm rollback cilium 13 -n kube-system --wait --timeout 10m

# 3. Prove the datapath is back (§4.3, §4.4, §4.5).
kubectl -n kube-system rollout status ds/cilium --timeout=10m
for p in $(kubectl get pods -n kube-system -l k8s-app=cilium -o name); do
  echo -n "$p: "; kubectl -n kube-system exec "$p" -c cilium-agent -- cilium-dbg status --brief
done
diff /tmp/cilium-lb-before.txt <(kubectl get svc -A -o json | .venv/bin/python3 -c "
import sys, json
d = json.load(sys.stdin)
rows = sorted((i['metadata']['namespace'] + '/' + i['metadata']['name'],
               (i['status'].get('loadBalancer', {}).get('ingress') or [{}])[0].get('ip'))
              for i in d['items'] if i['spec']['type'] == 'LoadBalancer')
[print(n, ip) for n, ip in rows]
")

# 4. ONLY NOW reconcile git with reality, then hand control back to Flux.
git revert --no-edit <bump-commit-sha> && git push origin main
flux resume helmrelease cilium -n kube-system
```

**Leaving the HelmRelease suspended is itself an incident** — an unreconciled
CNI drifts silently. Step 4 is not optional; if you must stop before it, record
the suspension in the window close-out.

### 5.4 What rollback costs

The rollback is **another full agent roll**, with the same per-node blips as the
upgrade. Pull it for a real regression (agent crash-loop, policy drops, a dark
VIP, a failed §4 gate) — never for a transient blip observed *during* the roll.

---

## 6) Interference notes

- **SOLO SLOT, ATTENDED — both halves are hard requirements.** This plan restarts
  the dataplane under every pod in the cluster, so every other plan's
  verification becomes unreliable while it runs. `conflicts_with` lists every
  currently-open executable plan deliberately (README §4: prose schedules
  nothing; only that field is honoured). **`window: null` — the scheduler
  assigns, but it must be an ATTENDED slot** (`sat-attended` or `sun-attended`):
  §4.8 is an operator-performed streaming check, and `autonomy_override:
  human-gated` enforces that no derivation can route this to an unattended night.
- **Reciprocity is owed on the other side.** `--validate` checks that refs
  resolve, not that they are mutual. The counterpart entries — at minimum
  `kube-prometheus-stack-91.4.0`, `prometheus-crd-ownership`, `otel-operator-0.21.0`
  and `talos-1.14.0` naming `cilium-1.20.2` back — must be added by whoever vets
  this plan. This plan file cannot edit other plans.
- **Not the Sunday reboot slot.** `needs_reboot: false` is truthful, so this plan
  must **not** consume `sun-attended:2026-09-27`, which `talos-1.14.0` needs in
  full (140 min in-window against a 200-min slot). A `sat-attended` slot fits 50
  min comfortably. If it ever shares a Sunday with the Talos roll, that is the
  single worst pairing in the queue: both restart the CNI on all three nodes,
  and the Talos roll already lists `cni/cilium` in its own `touches.shared`.
- **Blip profile.** Established flows survive (in-kernel BPF persists across an
  agent restart). New-flow setup, policy updates and L2 lease renewals pause for
  seconds per node — and with `maxUnavailable: 2` that is **two nodes at once**
  unless §3.4 is taken. The 14 VLAN-55 VIPs keep their addresses (every LB
  service is pinned via `lbipam.cilium.io/ips`, and the pool blocks in
  `config/pool.yaml` are untouched), but each may shuffle its announcing node
  once, costing one gratuitous-ARP re-learn per VIP. That is precisely the
  "MA/HA streaming" caveat the deny rule was reaching for.
- **Upstream's pre-flight check is deliberately not used here.** The upgrade
  guide calls it required; its two jobs are (a) validating network policies —
  vacuous for us, there are **0** CiliumNetworkPolicies — and (b) pre-pulling the
  image to avoid `ErrImagePull` mid-roll. Installing it means a second Helm
  release outside Flux, i.e. a direct cluster mutation this plan is not permitted
  to make. The residual risk it would have covered is exactly the `maxUnavailable:
  2` pull-stall in §1.5, which is why §3.4 exists as the GitOps-native mitigation.
  If the window agent wants the upstream mitigation instead, that is an operator
  call to make before the window, not a step to improvise inside it.
- **Step 0 ordering.** The window's safe-update batch runs first, every window.
  The §2e LB snapshot and §2f lease count must be taken **after** Step 0 settles
  and immediately before §3 — otherwise §4.4 diffs against a stale baseline and
  reports a Step-0 change as a cilium regression.
- **The config Kustomization is out of scope.** `cilium/config/` (LB pool, L2
  policy) `dependsOn` cilium and is not touched. Never bundle a pool edit into a
  version bump: a bad pool edit and a bad agent look identical from the LAN.
- **Monitoring is the instrument, not a bystander.** §4.2 reads Prometheus over
  the datapath being changed. A same-night `kube-prometheus-stack`,
  `prometheus-crd-ownership` or `otel-operator` change would leave this plan
  unable to tell "cilium is fine" from "the instrument moved" — hence their
  presence in `conflicts_with`.
