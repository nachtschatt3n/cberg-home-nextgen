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
est_duration_min: 55                  # 13 pre-checks + premise runner ~12 · edit+commit+push
                                      # ~5 · reconcile + full DS roll ~8 · verification §4
                                      # ~15 · mandatory 15-min settle. RAISED from 50 on
                                      # 2026-09-21: §4.8 (fresh-pod CNI ADD canary) and §2m
                                      # (enforcement baseline) are new work, ~4 min together.
                                      # UNCHANGED by the 2026-09-21 repair: §4.8 went from one
                                      # canary to one PER NODE (+~40s, they run back-to-back)
                                      # and §3.4's optional override was measured to cost a
                                      # helm upgrade and ZERO node-steps (§3.4), not the +8 min
                                      # it used to claim. Both fit inside the 55 already booked.
                                      # Still fits a 70-min schedulable sat-attended budget
                                      # SOLO — see §6, which does that arithmetic against
                                      # duration_min - STEP0_RESERVE_MIN, not duration_min.
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
  - talos-1.14.1                      # ADDED 2026-09-21. THE LIVE Talos plan (talos-1.14.0 was
                                      # superseded 2026-09-21 and its window cleared). Holds
                                      # sun-attended:2026-09-27 at 145 min and names
                                      # cilium-1.20.2 back. Worst pairing in the queue: both
                                      # roll the CNI on all three nodes.
  - talos-1.14.0                      # KEPT although superseded — the file still exists and
                                      # --validate checks that refs resolve. Rolls all 3 nodes.
                                      # Compounding: agents restarting while a node drains.
  - otel-operator-0.23.0              # ADDED 2026-09-21 (RECIPROCITY — it was MISSING). That
                                      # plan already lists cilium-1.20.2, because its whole
                                      # §1.4 NetworkPolicy risk assessment is read against
                                      # this CNI. A one-sided exclusion schedules nothing:
                                      # window-scheduler.py skips a plan if EITHER side names
                                      # the other, but only for plans it is actively placing.
  - unpoller-v5.2.7                   # ADDED 2026-09-21 (RECIPROCITY — it was MISSING). That
                                      # plan lists cilium-1.20.2: a CNI roll restarts pod
                                      # networking cluster-wide and its §4 reads Prometheus.
  - multus-macvlan-foundation         # CNI-adjacent (Talos machine-config VLAN work)
  - flux-oci-chart-sources            # already declares conflicts_with: [talos-1.14.0] for
                                      # the same reason; a CNI roll restarts what it verifies
  - kube-prometheus-stack-91.4.1      # MANDATORY: §4's CONTENTS ASSERTION reads Prometheus.
                                      # The window's instrument is shared infra (README §4).
  # RESOLVED 2026-09-20: prometheus-crd-ownership EXECUTED (1a551276) and retired (9d87171b) — there is no longer a plan to collide with, so this guard protected nothing. Removed per the dead-ref convention (F-6acb231c).
                                      # 2026-09-16: unpoller-v5.2.5 ref REMOVED — executed
                                      # (b0ffb944) and retired (f3869634) that same night.
                                      # 2026-09-17: otel-operator-0.21.0 ref REMOVED for the
                                      # same reason — executed (9a35168f) and retired
                                      # (37f7c7a6) in the nightly window. It was a monitoring
                                      # collector conflict; any FUTURE otel-operator plan must
                                      # re-add the exclusion.
  # Window annotations below RE-READ from each plan's own frontmatter 2026-09-21.
  # Four were stale; a stale annotation is how a planner talks itself into a slot
  # that is already full.
  - media-audit-durable-output        # sat-attended:2026-10-10 (was annotated 09-19 — that
                                      # window ran without it; rescoped TWICE since, off
                                      # 09-26 and 10-03 on capacity)
  - wazuh-2xx-edge-coverage           # sat-attended:2026-09-26 — touches the external
                                      # request path this plan can blackhole. 45 min.
  - external-dns-unowned-cnames       # sat-attended:2026-10-03 — DNS/edge records. 40 min.
  - nextcloud-mcp-0.187.1             # sat-attended:2026-10-03. 30 min. (Its recorded GO is
                                      # itself stale — F-bb713800 — but the slot is claimed.)
  - absenty-drop-npm-runtime          # window: null, status: blocked (was annotated
                                      # sun-attended:2026-09-20). UNSCHEDULED 2026-09-20 —
                                      # it claims no slot at all right now.
  - nextcloud-34.0.4                  # sun-attended:2026-10-04 (was annotated 09-20), status
                                      # vetted with a RECORDED GO. 75 min.
  - jellyfin-12.1                     # sun-attended:2026-10-11
security_ref: F-7620060c              # quay.io/cilium/cilium image record. Detail stays on
                                      # the finding; see §1.6. Companion: F-9b0a4b0d
                                      # (operator-generic image).
                                      # REPOINTED 2026-09-21: the previous refs F-d3d1472f
                                      # and F-0075055f are both RESOLVED/ACCEPTED records —
                                      # a plan citing a closed finding answers nothing and
                                      # leaves the LIVE ones reading as unplanned.
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
finding_refs: [F-7620060c, F-9b0a4b0d, F-f0816905]
                                      # REPOINTED 2026-09-21 to the LIVE open records
                                      # (`policy-cli.py finding show`, re-read that day):
                                      #   F-7620060c  security/warning — cilium agent image,
                                      #               newer upstream tag available
                                      #   F-9b0a4b0d  security/warning — operator-generic
                                      #               image, same
                                      #   F-f0816905  version/monitor — "cilium: chart
                                      #               1.20.1 → 1.20.2 (patch)", action
                                      #               "held by auto-update-policy (*cilium*)
                                      #               — PLAN lane". THIS is the finding the
                                      #               plan-or-page pass joins on; without it
                                      #               the PLAN-lane row pages the operator
                                      #               after plan_sla_days.
                                      # F-19e12a92 deliberately NOT added — CLOSED 2026-09-20
                                      # (it was the deny-rule reason correction, b9d64b70).
premises:                             # MACHINE-CHECKED preconditions, re-run at execution
                                      # time. ADDED 2026-09-21. Before this, §2 carried
                                      # twelve `# PREMISE` prose comments and NO `premises:`
                                      # block, so `plan-premises.py cilium-1.20.2
                                      # --require-premises` exited non-zero ("declares no
                                      # premises") and the vetting gate reported UNVERIFIED
                                      # while checking nothing. Prose is the claim under
                                      # test, not evidence for it.
                                      # Every `run:` below was dry-tested against
                                      # plan-premises.py's own command_is_readonly(), and
                                      # every expected value was MEASURED live 2026-09-21.
                                      # THREE §2 gates are deliberately NOT premises — the
                                      # §2e LB snapshot, the §2h LAN probes and the §2m
                                      # enforcement baseline use `$( )`, `>` or `&&`, which
                                      # command_is_readonly refuses ("premises must be a
                                      # simple pipeline"). They stay executor gates in §2.
  - id: hr-ready
    why: "An unready HelmRelease cannot be cleanly upgraded, and §4.1 asserts against this same field."
    run: kubectl get hr -n kube-system cilium -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: live-chart-is-1.20.1
    why: "`current:` claims 1.20.1. If the cluster already moved, this plan is stale and §4.1's baseline is wrong."
    run: kubectl get hr -n kube-system cilium -o jsonpath='{.status.history[0].chartVersion}'
    expect_exact: "1.20.1"
  - id: live-agent-image-is-1.20.1
    why: "The HR can read 1.20.1 while the DaemonSet runs something else. §4.1 diffs the digest, so the OLD digest must be what is live."
    run: kubectl get ds -n kube-system cilium -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_contains: "v1.20.1@sha256:ae9ea21f"
  - id: live-operator-image-is-1.20.1
    why: "Second of the two digests §1.4 says this plan moves."
    run: kubectl get deploy -n kube-system cilium-operator -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_contains: "operator-generic:v1.20.1"
  - id: agents-3-of-3-ready
    why: "Rolling a CNI that is already down a node is how a 2-of-3 maxUnavailable roll becomes a full outage."
    run: kubectl get ds -n kube-system cilium -o jsonpath='{.status.desiredNumberScheduled} {.status.numberReady}'
    expect_exact: "3 3"
  - id: maxunavailable-is-1-or-2
    why: "BOTH values are legal here, which is why this is a regex and not expect_exact. 2 = the chart default, the state §1.5 describes and §3.4 offers to change. 1 = §3.4 already taken (earlier in THIS window, or in an earlier one) — then skip §3.4 and read §1.5's '2 of 3' as history, not as current state. Anything else (0, 3, empty) means something outside this plan edited the DaemonSet, and §1.5's blast-radius arithmetic no longer describes the roll. RELAXED 2026-09-21, and this is the B4 fix: as expect_exact '2' the premise was MUTUALLY EXCLUSIVE with §3.4's own instruction to commit the override first and separately. The window agent re-runs premises at execution time, so an operator who took §3.4 as written made the very next premise run FAIL with \"got '1', want exactly '2'\" — stopping a plan that was proceeding exactly as written. Relaxing is the right limb rather than an ordering constraint, because ordering is prose the runner cannot see, and the premise must stay meaningful in both legal states instead of being evaluated once at a moment chosen to make it true."
    run: kubectl get ds -n kube-system cilium -o jsonpath='{.spec.updateStrategy.rollingUpdate.maxUnavailable}'
    expect_matches: "^[12]$"
  - id: chart-1.20.2-is-published
    why: "Never bump to a version that is not there. Uses `helm show chart` — curl is NOT in the premise runner's allowlist. A stale local repo cache fails this CLOSED; the fix is `helm repo update`, not relaxing the premise."
    run: helm show chart cilium/cilium --version 1.20.2 | grep '^version'
    expect_exact: "version: 1.20.2"
  - id: lb-services-are-14
    why: "§4.4 diffs the LB table against 14 rows. The retired 1.20.1 plan said 16 and was wrong."
    run: kubectl get svc -A --no-headers | grep -c LoadBalancer
    expect_exact: "14"
  - id: l2announce-leases-are-14
    why: "A VIP with a Service IP but no lease is dark on the LAN. §4.4's second half counts these."
    run: kubectl get leases -n kube-system -o name | grep -c cilium-l2announce
    expect_exact: "14"
  - id: lbipam-pool-not-conflicted
    why: "A pool already in conflict re-allocates unpredictably when the operator restarts, and §4.4 would read that as a cilium regression."
    run: kubectl get ciliumloadbalancerippool pool -o jsonpath='{.status.conditions[?(@.type=="cilium.io/PoolConflict")].status}'
    expect_exact: "False"
  - id: k8s-netpol-count-is-6
    why: "BASELINE for §4.7, not a gate. §4.7 asserts 6 ENFORCING endpoints in the datapath; that number is only meaningful against the 6 policy objects it derives from. If this moved, re-derive §4.7's expected total before trusting it."
    run: kubectl get netpol -A --no-headers | wc -l
    expect_exact: "6"
  - id: no-ciliumnetworkpolicies-exist
    why: "§1.2 calls the deprecated-L7-rule upgrade note vacuous on the strength of there being zero CNPs. If one appeared, that reasoning no longer holds."
    run: kubectl get cnp -A --no-headers | wc -l
    expect_exact: "0"
  - id: repo-pin-still-1.20.1
    why: "§3.2's sed anchors on `version: 1.20.1`. If HEAD already says 1.20.2 the edit silently no-ops and the window ships nothing."
    run: git show HEAD:kubernetes/apps/kube-system/cilium/app/helmrelease.yaml | grep '^      version'
    expect_exact: "version: 1.20.1"
  - id: bootstrap-pin-still-1.20.1
    why: "§3.3's regex anchors on it. Exactly ONE occurrence in the file (measured) — a second would mean the naive-sed trap §3.3 warns about became real."
    run: git show HEAD:kubernetes/bootstrap/apps/helmfile.yaml | grep -c 'version. 1.20.1'
    expect_exact: "1"
  - id: cilium-worktree-clean
    why: "Shared checkout. An uncommitted edit under the cilium app dir would ride into §3.5's path-scoped commit."
    run: git status --porcelain kubernetes/apps/kube-system/cilium | wc -l
    expect_exact: "0"
  - id: no-kustomization-in-flight
    why: "Nothing else may be reconciling. NOTE the form: `grep -c False` is WRONG here — False is the SUSPENDED column and matches all 140 rows. Column 5 is READY."
    run: flux get kustomizations -A | tail -n +2 | awk '$5!="True"' | wc -l
    expect_exact: "0"
  - id: no-helmrelease-in-flight
    why: "Same, for HelmReleases — helm-controller must be idle before it is asked to upgrade the CNI."
    run: flux get helmreleases -A | tail -n +2 | awk '$5!="True"' | wc -l
    expect_exact: "0"
  - id: nodes-on-expected-kubelet
    why: "Asserts no Talos/node operation is mid-flight. talos-1.14.1 moves this; if it reads anything else, that roll is in progress and this plan must not run."
    run: kubectl get nodes -o jsonpath='{.items[*].status.nodeInfo.kubeletVersion}'
    expect_exact: "v1.36.0 v1.36.0 v1.36.0"
  - id: canary-image-cached-on-all-3-nodes
    why: "§4.8's canary uses busybox:1.38.0 precisely because ds/security/falco-log-rotate already runs it on all three nodes — so a CNI-ADD failure cannot be misread as a slow image pull."
    run: kubectl get ds -n security falco-log-rotate -o jsonpath='{.status.numberReady}'
    expect_exact: "3"
  - id: canary-target-service-exists
    why: "§4.8 dials svc/echo-server in ns default on 8080. A gate naming an object that does not exist fails at the worst moment."
    run: kubectl get svc -n default echo-server -o jsonpath='{.spec.ports[0].port}'
    expect_exact: "8080"
  - id: canary-namespace-has-no-networkpolicy
    why: "If ns default gained a default-deny, §4.8's canary would fail for a reason that has nothing to do with this upgrade — a false rollback trigger."
    run: kubectl get netpol -n default --no-headers | wc -l
    expect_exact: "0"
status: vetted                        # VETTED 2026-09-21. Second independent plan-reviewer
                                      # returned ready-for-go after the B1-B4 repair, having
                                      # EXERCISED all four rather than read them: kubectl
                                      # --dry-run confirmed nodeName lands in the spec without
                                      # clobbering the container; every Gate 2/3 branch was run
                                      # in both zsh and bash; the chart was re-rendered twice
                                      # and md5 of line 1011..EOF is IDENTICAL in both, proving
                                      # spec.template is byte-identical; and the relaxed
                                      # premise was measured through plan-premises.py evaluate().
                                      # blocking_issues: none. --validate clean, premises 21/21.
                                      # KNOWN, CARRIED TO THE EXECUTION BRIEF rather than
                                      # patched post-review: §4.8's per-node loop returns the
                                      # LAST iteration's status, so a failure on node 01 with
                                      # 02/03 passing leaves the loop exit code 0. The failure
                                      # still PRINTS under its node header. Read §4.8's output,
                                      # never its exit code. Also: nodeName bypasses the
                                      # scheduler, so check `describe pod` for OutOfcpu/
                                      # OutOfmemory before attributing a canary failure to the
                                      # CNI — that path fails safe (false STOP, never false
                                      # green).
                                      # §3.4 maxUnavailable 2->1 DECLINED by the operator
                                      # 2026-09-21: run at 2. The premise accepts ^[12]$, so
                                      # leaving it at 2 passes unchanged.
window: "now:2026-09-21"   # ON-DEMAND NOW run 2026-09-21 (run-now.py stamp; was None)
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

### 1.2 The deny rule — reason ALREADY CORRECTED upstream of this plan; the hold stays

**Status 2026-09-21: the correction this section used to ask for has landed.**
`runbooks/auto-update-policy.yaml` was fixed on 2026-09-20 (commit `b9d64b70`,
finding `F-19e12a92`, now closed). The rule text this plan is written against is
the CURRENT one — do not re-litigate the old Gateway-API/mutual-auth rationale,
which is gone from the file:

> "CNI datapath — never an unattended bump. The hold is about CONSEQUENCE, not a
> specific release: a bad cilium roll takes the cluster network with it, and
> every Flux controller that would revert it sits inside the failure domain.
> […] Requires an attended slot, a plan that exercises a FRESH CNI ADD (existing
> pods keep networking from in-kernel BPF state, so every ordinary gate can pass
> while new-pod networking is broken), and an operator GO."

**The hold is correct and stays.** Note what the corrected reason now demands of
this file, in as many words: *a plan that exercises a FRESH CNI ADD*. That is
**§4.8**, which did not exist before 2026-09-21 — the plan asserted the in-kernel
BPF persistence argument in §5.1 and then never tested the one path that
argument leaves unprotected. The attended-slot and operator-GO requirements are
met by `autonomy_override: human-gated` and §4.9.

The table below is retained as the measured record of why the OLD reason's
version-specific caveats never applied here — checked against the live
`cilium-config`, not against rule text (authoring rule 8: a risk claim must come
from upstream or the cluster, never from a deny-rule reason written by the last
agent):

| Claimed caveat | Live state | Verdict |
|---|---|---|
| Gateway-API | `enable-gateway-api` is **ABSENT** from `cm/cilium-config`. The only `GatewayClass` is `envoy`, controller `gateway.envoyproxy.io/gatewayclass-controller` (Envoy Gateway, chart `gateway-helm` 1.9.1 — a *separate product*). | Cilium's Gateway API controller is **not running**. Upstream's 1.20 note "Cilium's Gateway API support now requires Gateway API v1.6.1" cannot bite us; the installed CRD bundle is v1.6.1 anyway. |
| Mutual auth | `mesh-auth-enabled: false` | Not enabled. Upstream deprecated it in 1.20; we never used it. |
| Deprecated L7 policy rules (`kafka`/`l7`/`l7proto`) must be removed before 1.20 | **0 CiliumNetworkPolicies exist** cluster-wide (6 plain k8s NetworkPolicies, which this note does not cover). | Vacuous. |
| `CiliumNodeConfig` v2alpha1 → v2 | 0 objects; CRD serves v2 only. | Vacuous. |

**Repo correction: DONE, nothing owed.** This section previously ended with an
owed correction to the deny rule's *reason* string. It was made on 2026-09-20 in
`b9d64b70` — the version-specific clause was dropped and replaced with the
consequence-based rationale quoted above. No further policy edit is required by
this plan, and the window agent should not open one.

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

Everything else in the **62** changed lines is the `helm.sh/chart: cilium-1.20.x`
label (re-measured 2026-09-21; the earlier "64" was wrong). **`cm/cilium-config` renders byte-identical.** No value we set
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
2×. Corrected here; **§3.4** offers the optional fix — at a cost §3.4 now states
correctly (one helm upgrade, zero node-steps; the old "+8 min, a full agent roll"
was measured to be false).

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
object verified to exist on 2026-09-21.** Do not proceed if any premise fails.

**Run the machine-checked premises FIRST** — the 21 `premises:` entries in the
frontmatter cover (a), (c), (d), (f), (g), (i), (j), (k) below and several
things the prose never checked. Verified 2026-09-21: `PASS cilium-1.20.2
(21 premise(s))`, exit 0.

```bash
.venv/bin/python3 runbooks/plan-premises.py cilium-1.20.2 --require-premises
#   PASS: every premise PASS, exit 0.
#   FAIL MODE: any premise FAIL, or exit non-zero — including "declares no
#   premises", which is what this plan did before 2026-09-21.
#
#   A FIRST FAIL OF ONE SPECIFIC SHAPE IS A RE-RUN, NOT A STOP. The premises
#   `no-kustomization-in-flight` / `no-helmrelease-in-flight` assert that NOTHING
#   is reconciling, and Step 0 (the window's safe-update batch) or a `run-now`
#   preflight always runs immediately before this plan — so a Flux object is
#   often still settling when the runner first fires. An independent review run
#   on 2026-09-21 FAILed on `ai/mcpo` "Reconciliation in progress" and PASSed
#   60s later with nothing changed. So: on a FAIL naming an in-flight or
#   reconciling object, wait ~60s and re-run ONCE. Escalate only if it fails
#   twice, or if the FAIL names anything else — every other premise here asserts
#   a steady-state fact that time alone will not fix, and a re-run that keeps
#   failing is a real stop.
```

The gates below that the premise runner **cannot** express — `$( )`, `>` and
`&&` are refused as not-a-simple-pipeline — are (b), (e), (h), (l) and (m).
Run those by hand.

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) PREMISE — cilium is fully healthy on all three nodes BEFORE we touch it.
kubectl -n kube-system get ds cilium \
  -o jsonpath='{.status.desiredNumberScheduled} {.status.numberReady}{"\n"}'   # expect: 3 3
for p in $(kubectl get pods -n kube-system -l k8s-app=cilium -o name); do
  echo -n "$p: "; kubectl -n kube-system exec "$p" -c cilium-agent -- cilium-dbg status --brief
done                                                                          # expect: 3× OK

# b) BASELINE — no module is already degraded (this is what §4.3 compares to).
for p in $(kubectl get pods -n kube-system -l k8s-app=cilium -o name); do
  echo -n "$p "
  kubectl -n kube-system exec "$p" -c cilium-agent -- cilium-dbg status | grep -E 'Modules Health'
done
#   THE GATE IS `Stopped(0) Degraded(0)` ON ALL THREE — measured 2026-09-21.
#   DO NOT write the OK counts down here. They drift within a single day: the
#   reading taken when this section was last edited (311/365/371) had become
#   374/308/365 hours later, with no cilium change in between. That is why §4.3
#   compares Degraded/Stopped and treats the OK count as colour. Take THIS
#   window's reading as the baseline §4.3 compares to, rather than trusting any
#   number committed to this file. Note this form also replaces the old
#   `exec ds/cilium`, which silently reads ONE arbitrary pod.

# c) PREMISE — the HelmRelease is Ready and actually on 1.20.1.
kubectl get hr -n kube-system cilium \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion}{"\n"}'
#   expect: True 1.20.1

# d) PREMISE — chart 1.20.2 is published (never bump to a version that isn't there).
#    `curl` is NOT in plan-premises.py's allowlist, so the premise form uses helm.
helm show chart cilium/cilium --version 1.20.2 | grep '^version'   # expect: version: 1.20.2
#    If this errors "chart not found", the LOCAL repo cache is stale — run
#    `helm repo update cilium` and re-run. Do NOT work around it by editing the pin.

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

# m) BASELINE — POLICY ENFORCEMENT IN THE DATAPATH. This is the number §4.7
#    compares to; take it AFTER Step 0 settles, immediately before §3.
#    It reads each agent's own endpoint table (BPF state), NOT the API server.
for p in $(kubectl get pods -n kube-system -l k8s-app=cilium -o name); do
  kubectl -n kube-system exec "$p" -c cilium-agent -- cilium-dbg endpoint list
done | grep -c 'Enabled'
#   Measured 2026-09-21: 6  (per node: 1 + 2 + 3, matching the 6 k8s NetworkPolicies)
#   NOTE the case: `grep -c 'Enabled'` does NOT match "Disabled" (D-i-s-a-b-l-e-d
#   contains no "enabled"), so this counts only endpoints with enforcement ON.
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

**COST — CORRECTED 2026-09-21, AND THE CORRECTION CHANGES THE DECISION.** This
section used to claim the override "is itself a full agent roll; budget +8 min",
and then used that invented cost as the stated reason to skip the mitigation.
**It is false.** Re-measured here by rendering chart 1.20.1 against the REAL
`app/helm-values.yaml` twice — once with the four lines above appended to a
scratch copy:

```
$ helm template cilium cilium/cilium --version 1.20.1 -n kube-system \
    -f kubernetes/apps/kube-system/cilium/app/helm-values.yaml   # 1734 lines
$ helm template cilium cilium/cilium --version 1.20.1 -n kube-system \
    -f /tmp/values-with-override.yaml    # scratch copy + the 4 lines, 1734 lines
$ diff render-base.yaml render-with.yaml
1009c1009
<       maxUnavailable: 2
---
>       maxUnavailable: 1
```

**That is the entire diff — one line out of 1734.** Line 1009 sits in
`spec.updateStrategy.rollingUpdate` of `ds/cilium`: the DaemonSet document
begins at line 994, and `spec.template:` begins at line **1011 in both
renders**. So `spec.template` is byte-identical, the DaemonSet's pod-template
hash does not change, and **the kubelet recreates no pod**. The true cost is one
helm upgrade and **zero node-steps**.

**So the operator decision is not "is this mitigation worth 8 extra minutes of
rolling?" — the mitigation is very nearly free.** What it actually costs:

- **Take it** and only one third of the datapath is ever down during THIS
  upgrade, and a stuck image pull cannot strand two nodes at once — which is the
  whole reason §1.5 exists. The upgrade's own roll becomes 3 node-steps instead
  of 2, so the roll in §3.6 runs somewhat longer; applying the override itself
  costs nothing.
- **Skip it** and the behaviour is exactly what the last two cilium bumps did.
- It changes *future* cilium rolls too, which is why it gets **its own commit**
  and its own revert line in §5.

If taken, commit it **first and separately** and let Flux settle. Then verify —
**both halves**, because the claim under test is that this lands WITHOUT a roll:

```bash
kubectl get ds -n kube-system cilium \
  -o jsonpath='{.spec.updateStrategy.rollingUpdate.maxUnavailable}{"\n"}'
#   PASS: 1.  FAIL MODE: still 2 => the generated values ConfigMap has not
#   re-rendered or helm-controller has not upgraded yet. Wait for the HR to go
#   Ready and re-read; do NOT proceed to §3.5 on an unverified override.
kubectl get pods -n kube-system -l k8s-app=cilium
#   PASS: three pods, AGES UNCHANGED across the commit. This is the gate that
#   proves no roll happened — measured 2026-09-21 pre-change, all three were
#   ~15d old (created 2026-09-06T07:13:52Z / 07:23:33Z / 07:36:50Z).
#   FAIL MODE: ages reset to seconds => something DID recreate the pods, the
#   render analysis above does not describe what actually landed, and you should
#   stop and find out what else moved before starting §3.5.
```

Taking §3.4 does **not** break the next premise run: the
`maxunavailable-is-1-or-2` premise accepts `^[12]$` precisely so that this
section and the machine-checked preconditions are not mutually exclusive (see
that premise's `why`). Only then do §3.5. §3.4 remains optional — the upgrade
does not depend on it — but **"it costs a full agent roll" is no longer a reason
to skip it, because it does not.**

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
#   PASS: Degraded(0) AND Stopped(0) on all three.
#   FAIL MODE: Degraded(n>0) — the brief summary can still read OK while a
#   subsystem is degraded, which is exactly why both lines are checked.
#
#   THE OK COUNT IS NOT A GATE, AND NO BASELINE NUMBER IS QUOTED HERE ANY MORE.
#   Successive texts quoted "307", then "311/365/371", and both were stale
#   within days. Proof that a number here is unmaintainable: the 311/365/371
#   triple was written on 2026-09-21 and a re-measurement THE SAME DAY read
#   374/308/365 — the multiset itself changed, with no cilium change between
#   the two readings. The count is per-node and tracks how many endpoints and
#   subsystems that agent happens to own, so it moves with ordinary pod
#   placement and a threshold on it either never fires or fires for the wrong
#   reason. Compare `Degraded`/`Stopped` against the §2b baseline taken in THIS
#   window; read the OK count as colour, never as a gate.
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
if dig +short +time=2 +tries=1 @192.168.55.5 kubernetes.io | grep -q '[0-9]'; then
  echo 'DNS VIP .5 OK'
else
  echo 'DNS VIP .5 FAIL — AdGuard VIP dark or returning no answer'
fi
curl -sk -o /dev/null -w 'HA .24:8123 -> %{http_code}\n' --max-time 8 http://192.168.55.24:8123
curl -sk -o /dev/null -w 'MA .29:8095 -> %{http_code}\n' --max-time 8 http://192.168.55.29:8095
#   PASS: 'DNS VIP .5 OK', 200, 200 (measured 2026-09-16 pre-change).
#   FIXED 2026-09-21: the old form was `dig ... > /dev/null && echo OK`, which
#   PRINTS NOTHING on failure — a silent gate reads as a skipped gate in a
#   window log, and `dig` exits 0 even when it returns an empty answer set, so
#   the old `&&` would have printed OK for a VIP that answered nothing at all.
#   The `grep -q '[0-9]'` asserts an actual A record came back, and the else
#   branch makes the failure loud. Positive control: the same command aimed at
#   an address with no resolver on it prints the FAIL line.
```

**4.7 — Policy enforcement survived the restart (read from the DATAPATH).**

```bash
for p in $(kubectl get pods -n kube-system -l k8s-app=cilium -o name); do
  kubectl -n kube-system exec "$p" -c cilium-agent -- cilium-dbg endpoint list
done | grep -c 'Enabled'
#   PASS: 6 — identical to the §2m baseline.
#   FAIL MODE: a lower number. Agents that came up without loading policy
#   regenerate their endpoints with enforcement OFF, and every one of those
#   prints "Disabled" in this column instead.
```

*This replaced a gate that could not fail.* The old §4.7 was
`kubectl get netpol -A --no-headers | wc -l  # PASS: 6`, which asks the **API
server** how many NetworkPolicy OBJECTS exist. This plan creates and deletes no
NetworkPolicy, so that command returns 6 whether cilium is enforcing all six
policies or none of them — it was a constant dressed as a gate. The form above
asks each **agent** what its own BPF endpoint table says, which is the property
the restart could actually destroy.

*Proof this gate can fail — measured 2026-09-21, not inferred:* in the same
`cilium-dbg endpoint list` output, endpoint 3 (`k8s-gateway`, selected by none
of the six policies) prints `Disabled` in both enforcement columns. The column
therefore takes both values in the live cluster, and the count is a real
measurement of how many endpoints have enforcement on. Per-node it reads 1 / 2
/ 3; the **sum** is the gate, because a policy-selected pod rescheduling moves
the count between nodes without changing the total. If §2m's baseline was not 6,
use that number, not this one.

**4.8 — A FRESH POD GETS NETWORKING (the gate this section was missing).**

**Why this exists, and why nothing else in §4 substitutes for it.** §5.1 states
the plan's own load-bearing assumption: existing pods keep networking across an
agent restart because their BPF programs stay loaded in-kernel. That is exactly
why **every other gate in §4 can go green while `CNI ADD` is broken for new
pods** — agents Ready, VIPs serving, HA/MA answering, Prometheus scraped, policy
enforced, all of it runs on endpoints that already exist. A broken CNI ADD is
invisible until the next unrelated deploy schedules a pod, which is hours or
days after the window closed and nobody connects it to cilium. Nothing else here
creates a pod, so nothing else tests the path.

```bash
# ONE CANARY PER NODE — this is the point of the section, not a refinement.
# `maxUnavailable: 2` (§1.5) means two agents restart together, so the
# regression this gate exists to catch is "one agent came back unable to serve
# CNI ADD on ITS node". An unpinned `kubectl run` lets the scheduler place a
# single canary anywhere across the three nodes, so it can land on a healthy
# node and report PASS while another node's CNI ADD is dead — which is exactly
# the failure the deny rule demands this plan exercise. Pin with nodeName.
# Verified 2026-09-21 that kubectl v1.36.0 (client and server) accepts this
# --overrides JSON and puts nodeName into the pod spec. Adds ~40s.
for N in k8s-nuc14-01 k8s-nuc14-02 k8s-nuc14-03; do
  kubectl -n default delete pod "cni-canary-$N" --ignore-not-found
  kubectl -n default run "cni-canary-$N" --restart=Never --image=busybox:1.38.0 \
    --overrides="{\"spec\":{\"nodeName\":\"$N\"}}" --command -- sh -c \
    'wget -q -T 5 -O- http://echo-server.default.svc.cluster.local:8080/ >/dev/null && echo CNI_CANARY_OK || echo CNI_CANARY_FAIL'
done

# ALL THREE GATES, AGAINST EACH CANARY. Every gate exits non-zero on failure,
# and the loop echoes the node first, so the output names the node that failed.
for N in k8s-nuc14-01 k8s-nuc14-02 k8s-nuc14-03; do
  POD="cni-canary-$N"
  echo "===== $N ====="

  # GATE 1 — CNI ADD succeeded ON THIS NODE. A pod cannot reach Succeeded
  # without an IP.
  kubectl -n default wait --for=jsonpath='{.status.phase}'=Succeeded \
    "pod/$POD" --timeout=120s
  #   PASS: exit 0, "pod/cni-canary-<node> condition met".
  #   FAIL MODE: `wait` exits 1 on timeout while the pod sits in
  #   ContainerCreating. Diagnose SCOPED to the node that failed (not a
  #   cluster-wide tail, which crowds out the one line that matters):
  #     kubectl -n default describe pod "$POD" | tail -20
  #     kubectl -n default get events --field-selector involvedObject.name="$POD"
  #   The signature is FailedCreatePodSandBox naming plugin type "cilium-cni".

  # GATE 2 — the pod got a routable pod-network IP. ASSERTED, not printed.
  IP=$(kubectl -n default get pod "$POD" -o jsonpath='{.status.podIP}')
  case "$IP" in 10.69.*) echo "GATE2 PASS podIP=$IP";; *) echo "GATE2 FAIL podIP='$IP'"; false;; esac

  # GATE 3 — east-west: DNS resolved AND the Service was reachable. ASSERTED.
  kubectl -n default logs "$POD" | grep -qx CNI_CANARY_OK \
    && echo "GATE3 PASS" || { echo "GATE3 FAIL"; kubectl -n default logs "$POD"; false; }
done

# Clean up ALL THREE canaries.
for N in k8s-nuc14-01 k8s-nuc14-02 k8s-nuc14-03; do
  kubectl -n default delete pod "cni-canary-$N" --ignore-not-found
done
```

*Every object named here was verified live 2026-09-21:* the three node names are
`k8s-nuc14-01/02/03` (`kubectl get nodes`); `svc/echo-server` exists in ns
`default` on port 8080; ns `default` has **zero** NetworkPolicies and zero
CiliumNetworkPolicies, so a default-deny cannot fail the canary for an unrelated
reason; and `busybox:1.38.0` is already resident on **all three** nodes via
`ds/security/falco-log-rotate` (3/3 ready), so a CNI-ADD failure can never be
misread as a slow image pull. All of these are also frontmatter premises. No
`cni-canary-*` pod exists in ns `default` today, so the names are free.

*Proof each gate can fail — DRY-TESTED 2026-09-21, not inferred.*

- **Gate 1** exits non-zero on timeout: the failure is an exit code, not absent
  output.
- **Gate 2 was rewritten because the old form could not fail.** It used to be
  `get pod -o jsonpath='{.status.podIP}'`, which on failure prints an empty line
  and **exits 0** — indistinguishable in a window log from a gate that was
  skipped, the exact defect §4.6 was repaired for. The `case` form asserts the
  pod CIDR and returns non-zero otherwise. Dry-tested: `IP=10.69.1.42` prints
  `GATE2 PASS podIP=10.69.1.42` rc=0; `IP=""` prints `GATE2 FAIL podIP=''` rc=1.
  The prefix is right — all 306 pod-network IPs in the cluster are `10.69.*`
  (the remaining 25 are `hostNetwork` pods on `192.168.*`, which a canary is
  not), so a hostNetwork fallback would also fail this gate rather than pass it.
- **Gate 3 was rewritten because it had no assertion at all** — a bare
  `kubectl logs` is an eyeball, and an eyeball in a 03:30 window log is not a
  gate. `grep -qx` anchors the WHOLE line. Dry-tested: `CNI_CANARY_OK` → rc=0;
  `CNI_CANARY_FAIL` → rc=1 (and `-x` means a hypothetical `CNI_CANARY_OK_LATER`
  would not match either); empty log → rc=1, so a pod that produced no output at
  all fails rather than passing quietly. The failure branch re-prints the log so
  the window operator sees why.

Note the deliberate split, which the per-node loop preserves: the container's
command exits 0 either way, so Gate 1 tests **only** pod admission (CNI ADD)
while Gate 3 tests **only** reachability. Two distinct failure modes, two
distinct gates; collapsing them would let a DNS failure masquerade as a CNI
failure and trigger the wrong rollback limb.

**4.9 — OPERATOR GATE (the deny rule's actual requirement).** Play a stream
through Music Assistant and open the Home Assistant dashboard. Both must work.
This is the check no cron can perform and the reason `autonomy_override:
human-gated` is set. **Do not close the window without it.**

**4.10 — Settle.** Wait 15 minutes, then confirm no new firing alerts
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

# 2. Roll the release back directly — DERIVE the revision, never hardcode it.
#    A hardcoded number is correct only until the next cilium release changes
#    it, and this limb runs when the datapath is already broken.
helm history cilium -n kube-system          # eyeball it first
REV=$(helm history cilium -n kube-system -o json | .venv/bin/python3 -c "
import sys, json
h = json.load(sys.stdin)
r = [x for x in h if x['chart'] == 'cilium-1.20.1']
print(r[-1]['revision'] if r else 'NONE')
")
echo "rollback target revision: $REV"      # measured 2026-09-21: 13
test "$REV" != NONE || { echo 'STOP — no cilium-1.20.1 revision in helm history'; exit 1; }
#   The `{ …; exit 1; }` form is load-bearing. As a bare `|| echo` this only
#   PRINTED the warning and then fell straight through into
#   `helm rollback cilium "NONE"` — during a datapath outage, with a nonsense
#   revision. Dry-tested 2026-09-21: REV=NONE prints STOP and returns rc=1
#   without reaching the rollback; REV=13 proceeds normally.
helm rollback cilium "$REV" -n kube-system --wait --timeout 10m

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
git revert --no-edit <bump-commit-sha>
git push origin main
#   `flux resume` is on its OWN line deliberately. Chained as
#   `git revert … && git push …` followed by the resume, a push failure (rejected
#   non-fast-forward in this shared checkout, or GitHub unreachable — plausible
#   while the datapath is broken) short-circuits the chain and leaves the
#   HelmRelease SUSPENDED, which the paragraph below calls an incident in its own
#   right. Resume regardless, then fix the push.
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
  §4.9 is an operator-performed streaming check, and `autonomy_override:
  human-gated` enforces that no derivation can route this to an unattended night.
- **Reciprocity — VERIFIED 2026-09-21, no longer owed.** `--validate` checks that
  refs resolve, not that they are mutual, so each counterpart was read directly:
  `kube-prometheus-stack-91.4.1`, `otel-operator-0.23.0`, `unpoller-v5.2.7` and
  `talos-1.14.1` **all name `cilium-1.20.2` in their own `conflicts_with`**. The
  two that were missing on THIS side (`otel-operator-0.23.0`, `unpoller-v5.2.7`)
  have been added. The older refs named here before — `kube-prometheus-stack-91.4.0`,
  `prometheus-crd-ownership`, `otel-operator-0.21.0` — are gone: the first two
  executed and retired, the third was superseded by 0.23.0.
- **SLOT: a solo attended slot. None of the three standing ones is free for it.**
  Arithmetic against the SCHEDULABLE budget (`duration_min - STEP0_RESERVE_MIN`,
  `STEP0_RESERVE_MIN = 20`, window-scheduler.py:92/:270 — now also documented at
  the top of `maintenance-windows.yaml`, because four artifacts have costed a
  slot against the raw `duration_min` and got it wrong):
  - `sat-attended` 90 → **70 usable**. `2026-09-26` holds `wazuh-2xx-edge-coverage`
    (45 min) — which is in this plan's `conflicts_with`, and 45 + 55 = 100 > 70
    regardless. `2026-10-03` already holds 70 min (external-dns 40 +
    nextcloud-mcp 30) — full. `2026-10-10` holds `media-audit-durable-output`
    (45 min), also a listed conflict.
  - `sun-attended` 200 → **180 usable**. `2026-09-27` is `talos-1.14.1`'s at
    145 min, and it must keep the whole slot. **Do not put this plan there.**
    cilium + Talos is the single worst pairing in the queue: both roll the CNI
    on all three nodes, and the Talos plan already lists `cni/cilium` in its own
    `touches.shared`. `needs_reboot: false` here is truthful and must not be
    used to justify claiming a reboot-capable slot.
  - `nightly` is unattended — excluded by `autonomy_override: human-gated`.

  **What would have to move.** The cheapest displacement is
  `wazuh-2xx-edge-coverage` off `sat-attended:2026-09-26`: it is `status: draft`
  and explicitly "PROPOSED, not approved", it carries `conflicts_with: []`, and
  it is the only occupant of that slot — moving it frees all 70 usable minutes
  for a 55-minute solo run. The alternative, and probably the better one, is an
  operator-triggered **on-demand NOW run** (`on_demand:` slot `now`,
  480-min ceiling, `allow_reboot: false`, attended by construction): it gives
  this plan a genuinely solo attended slot without evicting anyone. Per
  `plans/README.md` only `run-now.py stamp` may write that `window:` value —
  hence `window: null` here. **Recommendation: NOW run, or 09-26 with wazuh
  displaced. Not 09-27.**
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
