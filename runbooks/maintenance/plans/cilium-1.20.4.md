---
plan_id: cilium-1.20.4
component: cilium
pr: 372                               # Renovate "fix(helm): update cilium ( 1.20.2 → 1.20.4 )",
                                      # branch renovate/cilium-1.20.x, head ec2e495c. Verified
                                      # 2026-10-16: OPEN, mergeable CLEAN, all 4 checks pass
                                      # (Flate Render Gate, Flux Local Diff hr+ks, Labeler).
                                      # Diff = exactly the two pins this plan needs (§3.2).
kind: chart
current: "1.20.2"                     # LIVE, verified 2026-10-16: HR Ready, history[0]
                                      # chartVersion 1.20.2 (helm revision 14, deployed
                                      # 2026-09-21); ds/cilium + deploy/cilium-operator on
                                      # v1.20.2 digests; cilium-dbg version 1.20.2 e0dc92bd.
target: "1.20.4"                      # chart on helm.cilium.io (helm show chart: version +
                                      # appVersion 1.20.4); GitHub release v1.20.4 published
                                      # 2026-10-23T14:51:39Z, non-prerelease. RETARGETED 2026-10-24 from
                                      # 1.20.3 (v1.20.3 carries a Gateway API BackendTLSPolicy regression,
                                      # fixed only in 1.20.4); we skip 1.20.3 entirely.
update_type: patch                    # fourth patch (1.20.2 -> 1.20.4 skips 1.20.3) on the 1.20 line we have run since
                                      # 2026-08-03 (97989c9b). Not a minor traversal.
risk: medium                          # Rated on the MEASURED change: rendered delta against
                                      # OUR values is two image digests (§1.3), identical in
                                      # shape to cilium-1.20.1 and cilium-1.20.2, both rated
                                      # medium and both executed cleanly. Probability of
                                      # failure low; CONSEQUENCE total (the CNI). The
                                      # consequence is handled by autonomy_override +
                                      # exclusive + an attended slot, not by inflating this.
est_duration_min: 85                  # 2026-10-22: +25 for the gated one-node-at-a-time roll (3 x ~8 min incl. etcd gate before/after each node).
                                      # cilium-1.20.2 booked 55 and ran inside it. +5 for the
                                      # NEW FQDN/L7-DNS canary (§2n baseline + §4.9), which
                                      # did not exist then because no CiliumNetworkPolicy
                                      # existed then. Fits sat-attended's 70 usable minutes
                                      # SOLO (duration_min 90 - STEP0_RESERVE_MIN 20).
needs_reboot: false                   # HONEST: DaemonSet RollingUpdate + operator Deployment
                                      # roll only. No drain, no Talos change, zero files under
                                      # kubernetes/bootstrap/talos/. Do not claim the
                                      # reboot-capable Sunday slot with this.
touches:
  namespaces:
    - kube-system                     # helmrelease/cilium, ds/cilium, deploy/cilium-operator
    - "ALL (cluster-wide)"            # every pod rides this datapath; agent restart is per node
    - ci-runner                       # CNP ci-runner-lockdown (L7 DNS + toFQDNs) — §1.4
    - arc-system                      # CNP arc-system-lockdown (L7 DNS + toFQDNs) — §1.4
    - arc-build                       # CNP arc-build-egress (L7 DNS + toFQDNs) — §1.4
    - default                         # §4.8 CNI-ADD canaries (created + deleted)
  resources:
    - helmrelease/cilium              # kube-system — the only LIVE pin
    - daemonset/cilium                # rolls on all 3 nodes; rolled ONE node at a time via updateStrategy OnDelete (§3.4); chart default is maxUnavailable 2
    - deployment/cilium-operator      # 1 replica; brief operator gap
    - configmap/cilium-config         # NOT byte-identical at 1.20.4: key envoy-xds-mode (live "ads") is no longer rendered (§1.3); helm rewrites it
    - kubernetes/apps/kube-system/cilium/app/helmrelease.yaml
    - kubernetes/bootstrap/apps/helmfile.yaml   # bootstrap/DR-only pin, inert at runtime
    - "13 LoadBalancer Services (VLAN 55 VIPs) announced via CiliumL2AnnouncementPolicy l2-policy"
    - "13 cilium-l2announce leases in kube-system"
    - "4 CiliumNetworkPolicies (arc-build-egress, arc-system-lockdown, ci-runner-lockdown, the-ninth-banner-runners-egress)"
  shared:
    - cilium                          # the CNI itself
    - cni                             # pod networking, kube-proxy replacement, policy enforcement
    - gateway/envoy                   # Cilium LB-IPAM + L2 supplies 192.168.55.103 (envoy-internal)
                                      # and 192.168.55.104 (envoy-external)
    - public-edge                     # envoy-external is the internet-facing gateway
    - coredns                         # in-cluster DNS rides the pod datapath; the FQDN proxy
                                      # forwards to it
    - dns                             # AdGuard VIP .5 and k8s-gateway VIP .101 are Cilium LB IPs
    - monitoring                      # §4.2's contents gate reads Prometheus over this datapath
    - ci-runner                       # ARC listeners/runners sit behind toFQDNs policies (§1.4)
    - "LAN service access (VLAN 55)"  # HA .24, MA .29, Plex .30, mosquitto .15, ... by VIP
depends_on: []
conflicts_with:                       # Belt-and-braces: `exclusive: true` below already keeps
                                      # every plan out of this slot in BOTH directions. These are
                                      # the plans whose interaction with a CNI roll is specific
                                      # enough to name, re-read from each plan's frontmatter on
                                      # 2026-10-16. NONE of them lists cilium-1.20.4 yet (it did
                                      # not exist) — reciprocity is owed on their side (§6).
                                      # (No kube-prometheus-stack plan file exists as of 2026-10-23; both former refs were dead
                                      # and are removed. Re-add one if a KPS bump is planned: §4.2 reads Prometheus.)
  - talos-linux-1.14.4                # node-roll plan (3 reboots, exclusive, sun-attended:2026-11-01): same CNI-on-all-3-nodes worst pairing.
                                      # RECIPROCAL: talos-linux-1.14.4 now lists cilium-1.20.4 (2026-10-23). Cilium runs
                                      # sun-attended:2026-10-25 SOLO; the Talos roll must not share a night with it, and
                                      # its first reboot should follow a clean 10-25 run (agents restarted once already).
                                      # talos-linux-1.14.2 (superseded by 1.14.4) is no longer listed.
  - coredns-1.48.1                    # SUPERSEDED/dead plan kept only if the validator accepts it; coredns is LIVE 1.49.0 (verified 2026-10-22) so no coredns change is pending. Was: sat-attended:2026-10-17. DNS rides this datapath and the
                                      # §4.9 FQDN canary resolves through coredns — a same-night
                                      # coredns change makes a canary FAIL un-attributable.
  - etcd-timeouts-5000-500            # control plane; §5.3 break-glass needs a healthy apiserver.
  - flux-distribution-2.9.6           # Flux is the rollback machinery (§5).
  - flux-oci-chart-sources            # declares cni-adjacent; changes chart sourcing incl. Flux.
  - flux-reconciler-impersonation     # same family; exclusive on its own side.
  - otel-operator-0.25.1              # ships a NetworkPolicy + monitoring collector; precedent
                                      # 893ff81b declared edot/otel <-> cilium both ways.
  - edot-collector-0.163.2            # current edot plan (0.162.0 superseded).
  - edot-collector-0.162.0            # owns LB VIP edot-collector-talos-kmsg (.18), in §4.4's table.
  - envoy-proxy-config-distroless-v1.39.4  # §4.5 gates on the Envoy VIPs; an Envoy change the
                                      # same night makes a VIP failure un-attributable.
  - envoy-proxy-config-distroless-v1.40.0
  - otbr-0.4.0                        # host-netfilter on k8s-nuc14-03 (one of the rolled nodes).
  - longhorn-1.13.0                   # storage engine; exclusive on its own side.
  - talos-power-tuning-ab             # Talos machine-config on all nodes; exclusive.
  - ci-gate-primary-control-rework    # touches the CI-runner gate whose namespaces carry the
                                      # FQDN policies §4.9 exercises.
exclusive: true                       # "no other change may be in flight while this runs" —
                                      # the README names a CNI bump as the canonical case.
security_ref: null                    # Dispatch: security_evidence none. The image records are
                                      # carried in finding_refs (ownership), detail stays in DB.
capability_change: false              # FACT: no value, flag or user-visible behaviour changes;
                                      # rendered delta is two image digests (§1.3). The three
                                      # upstream behaviour changes that COULD apply were each
                                      # checked against live objects and are vacuous here (§1.4).
rollback_class: git-revert            # nothing forward-only: no schema/data migration, no
                                      # immutable handle; CRDs unchanged. Read §5 before trusting
                                      # the word "revert" — Flux runs on this datapath.
autonomy_override: human-gated        # LOAD-BEARING. Without it, capability_change:false +
                                      # git-revert + risk:medium derive AUTO-NIGHT (forbid_shared
                                      # is [storage, longhorn]). The deny rule requires an
                                      # attended slot + operator GO, and §4.10 is an operator
                                      # streaming check no cron can perform.
finding_refs: [F-f0816905, F-1c0f5b1d, F-c879161b, F-a571f10d, F-cb6c175f]
                                      # Re-queried 2026-10-24, same set, F-f0816905 already titled 1.20.2 -> 1.20.4 (`policy-cli.py finding list --grep cilium`, DSN up):
                                      #   F-f0816905  version  — "cilium: chart 1.20.2 -> 1.20.4 (patch)" (this change)
                                      #   F-c879161b  security — cilium agent v1.20.2 image, newer tag now exists (this plan's remedy)
                                      #   F-1c0f5b1d  security — operator-generic v1.20.2 image, newer tag now exists (same)
                                      # F-f835aded (health/monitor, SOP gap on ipBlock NetworkPolicy chart bumps) is context, NOT claimed.
                                      # Original two, kept (accepted under AR-029, lapse once 1.20.4 lands):
                                      #   F-a571f10d  security — quay.io/cilium/cilium:v1.20.2 image
                                      #   F-cb6c175f  security — operator-generic:v1.20.2 image
                                      # Both currently [AR-029] "already newest"; that premise lapses
                                      # now that v1.20.4 exists, and this plan moves both digests.
premises:                             # Every run: was checked against plan-premises.py's allowlist
                                      # (kubectl get / helm show|history / git show|status / flux get,
                                      # plus grep|wc|awk) and every expected value MEASURED 2026-10-16.
  - id: hr-ready
    why: "An unready HelmRelease cannot be cleanly upgraded; §4.1 asserts this field."
    run: kubectl get hr -n kube-system cilium -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: live-chart-is-1.20.2
    why: "`current:` claims 1.20.2. If the cluster already moved, this plan is stale."
    run: kubectl get hr -n kube-system cilium -o jsonpath='{.status.history[0].chartVersion}'
    expect_exact: "1.20.2"
  - id: live-agent-image-is-1.20.2
    why: "§4.1 diffs the digest, so the OLD digest must be what is live."
    run: kubectl get ds -n kube-system cilium -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_contains: "v1.20.2@sha256:2939231d"
  - id: live-operator-image-is-1.20.2
    why: "Second of the two digests §1.3 says this plan moves."
    run: kubectl get deploy -n kube-system cilium-operator -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_contains: "operator-generic:v1.20.2@sha256:64d87983"
  - id: agents-3-of-3-ready
    why: "Rolling a CNI already down a node turns a 2-of-3 maxUnavailable roll into a full outage."
    run: kubectl get ds -n kube-system cilium -o jsonpath='{.status.desiredNumberScheduled} {.status.numberReady}'
    expect_exact: "3 3"
  - id: etcd-leader-changes-24h-below-6
    why: "etcd base-rate rule (docs/sops/etcd.md: >=6 leader changes/24h = already unstable = NO-GO). Rolling the CNI on a control-plane node that also runs etcd while etcd is flapping risks quorum loss. `< bool 6` returns 1 when quiet and 0 when not, so the gate can fail (0) and an empty result (no scrape) fails the grep too. Measured 2026-10-22: 1 leader change/24h (10-20 had 21)."
    run: kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=max(increase(etcd_server_leader_changes_seen_total%5B24h%5D))%3Cbool%206' | grep -c -E '"value":\[[0-9.]+,"1"\]'
    expect_exact: "1"
  - id: updatestrategy-not-yet-ondelete
    why: "§3.4a flips the DaemonSet to OnDelete; if it already is OnDelete a previous attempt stopped mid-roll and the plan is stale."
    run: kubectl get ds -n kube-system cilium -o jsonpath='{.spec.updateStrategy.type}'
    expect_exact: "RollingUpdate"
  - id: maxunavailable-is-1-or-2
    why: "2 = chart default (measured today). 1 = the optional §3.4 override was taken. Anything else means something outside this plan edited the DaemonSet and §6's blast-radius arithmetic is wrong."
    run: kubectl get ds -n kube-system cilium -o jsonpath='{.spec.updateStrategy.rollingUpdate.maxUnavailable}'
    expect_matches: "^[12]$"
  - id: chart-1.20.4-is-published
    why: "Never bump to a version that is not there. A stale local repo cache fails this CLOSED; fix with `helm repo update cilium`, never by relaxing the premise."
    run: helm show chart cilium/cilium --version 1.20.4 | grep '^version'
    expect_exact: "version: 1.20.4"
  - id: rollback-revision-present
    why: "§5.3 rolls back by helm revision. The chart-1.20.2 revision must be in history (measured: revision 14)."
    run: helm history cilium -n kube-system | grep -c 'cilium-1.20.2'
    expect_matches: "^[1-9]"
  - id: lb-services-are-13
    why: "§4.4 diffs the LB table. 13 today — the retired 1.20.2 plan said 14; the count moves, so this is re-measured, never copied."
    run: kubectl get svc -A --no-headers | grep -c LoadBalancer
    expect_exact: "13"
  - id: l2announce-leases-are-13
    why: "A VIP with a Service IP but no lease is dark on the LAN. §4.4 counts these."
    run: kubectl get leases -n kube-system -o name | grep -c cilium-l2announce
    expect_exact: "13"
  - id: lbipam-pool-not-conflicted
    why: "A pool already in conflict re-allocates unpredictably on operator restart and §4.4 would misread it as a cilium regression."
    run: kubectl get ciliumloadbalancerippool pool -o jsonpath='{.status.conditions[?(@.type=="cilium.io/PoolConflict")].status}'
    expect_exact: "False"
  - id: cnp-count-is-4
    why: "§1.4's applicability analysis and the §4.9 FQDN canary are written against exactly these 4 CNPs. If one appeared or vanished, re-derive both before running."
    run: kubectl get cnp -A --no-headers | wc -l
    expect_matches: "^ *4$"
  - id: cnps-all-valid
    why: "BASELINE for §4.7b. The 1.20.3+ operator adds CNP validation (nodeSelector case); all 4 must read VALID=True before so a post-upgrade False is attributable."
    run: kubectl get cnp -A --no-headers | awk '$4!="True"' | wc -l
    expect_matches: "^ *0$"
  - id: k8s-netpol-count-is-5
    why: "Baseline for §4.7a — the enforcement count derives from 5 NetworkPolicies + 4 CNPs. Measured live 2026-10-23: 5 (mariadb, flux-operator-web, otel-operator-daemon-collector-networkpolicy, nextcloud-mariadb, nextcloud-redis). It read 6 on 2026-10-21/22 only while the ingress-only uzeit-de-ingress policy existed; that app was removed, so 6 now FAILS this premise by design (a changed count means a policy appeared or vanished since this plan was measured: re-baseline §4.7a)."
    run: kubectl get netpol -A --no-headers | wc -l
    expect_matches: "^ *5$"
  - id: no-clrp-or-cidrgroup
    why: "1.20.3+ changes behaviour for empty-toPorts CiliumLocalRedirectPolicies (now rejected) and 0.0.0.0/0 CiliumCIDRGroups (now select traffic). §1.4 calls both vacuous because zero objects exist."
    run: kubectl get ciliumlocalredirectpolicies,ciliumcidrgroups -A --no-headers | wc -l
    expect_matches: "^ *0$"
  - id: live-xds-mode-is-ads
    why: "§1.3: chart 1.20.4 stops rendering envoy-xds-mode (live ads). This premise is the baseline; §4.3b asserts the key is gone AFTER and the agents are healthy. If it is already absent, someone changed the chart/values and §1.3 is stale."
    run: kubectl get cm -n kube-system cilium-config -o jsonpath='xds=[{.data.envoy-xds-mode}]'
    expect_exact: "xds=[ads]"
  - id: no-cilium-envoyconfig-crds-or-objects
    why: "1.20.4 changes CiliumEnvoyConfig service scoping and xDS restoration. Vacuous only while no Cilium CEC CRD exists (measured 0 on 2026-10-24; the Envoy CRDs present are all gateway.envoyproxy.io = Envoy Gateway)."
    run: kubectl get crd -o name | awk '/envoyconfigs.cilium.io/' | wc -l
    expect_matches: "^ *0$"
  - id: cilium-gateway-api-off
    why: "Part of the 1.20.3/1.20.4 changelog is Cilium's own Gateway API / Envoy (incl. the 1.20.3 BackendTLSPolicy regression that 1.20.4 fixes). Irrelevant only while enable-gateway-api is ABSENT from cilium-config (measured)."
    run: kubectl get cm -n kube-system cilium-config -o jsonpath='gw=[{.data.enable-gateway-api}]'
    expect_exact: "gw=[]"             # literal wrapper: the runner refuses empty output. Negative
                                      # control: the same form on a PRESENT key prints gw=[false].
  - id: repo-pin-still-1.20.2
    why: "§3.2's fallback sed anchors on `version: 1.20.2`; if HEAD already says 1.20.4 the plan is executed or stale."
    run: git show HEAD:kubernetes/apps/kube-system/cilium/app/helmrelease.yaml | grep '^      version'
    expect_exact: "version: 1.20.2"
  - id: bootstrap-pin-still-1.20.2
    why: "§3.2's fallback regex anchors on it; exactly ONE occurrence (measured)."
    run: git show HEAD:kubernetes/bootstrap/apps/helmfile.yaml | grep -c 'version. 1.20.2'
    expect_exact: "1"
  - id: cilium-worktree-clean
    why: "Shared checkout: an uncommitted edit under the cilium app dir would ride into a path-scoped commit."
    run: git status --porcelain kubernetes/apps/kube-system/cilium kubernetes/bootstrap/apps/helmfile.yaml | wc -l
    expect_matches: "^ *0$"
  - id: no-kustomization-in-flight
    why: "Nothing else may be reconciling. Column 5 is READY (column 4 is SUSPENDED — `grep -c False` matches every row)."
    run: flux get kustomizations -A | tail -n +2 | awk '$5!="True"' | wc -l
    expect_matches: "^ *0$"
  - id: no-helmrelease-in-flight
    why: "helm-controller must be idle before it is asked to upgrade the CNI."
    run: flux get helmreleases -A | tail -n +2 | awk '$5!="True"' | wc -l
    expect_matches: "^ *0$"
  - id: nodes-on-expected-kubelet
    why: "Asserts no node operation is mid-flight. If a Talos/k8s roll moved this, re-measure, do not run."
    run: kubectl get nodes -o jsonpath='{.items[*].status.nodeInfo.kubeletVersion}'
    expect_exact: "v1.36.0 v1.36.0 v1.36.0"
  - id: canary-image-cached-on-all-3-nodes
    why: "§4.8/§4.9 canaries use busybox:1.38.0 because ds/security/falco-log-rotate runs it on all 3 nodes — a CNI failure can never be misread as a slow pull."
    run: kubectl get ds -n security falco-log-rotate -o jsonpath='{.status.numberReady} {.spec.template.spec.containers[0].image}'
    expect_exact: "3 busybox:1.38.0"
  - id: canary-target-service-exists
    why: "§4.8 dials svc/echo-server in ns default on 8080."
    run: kubectl get svc -n default echo-server -o jsonpath='{.spec.ports[0].port}'
    expect_exact: "8080"
  - id: canary-namespace-default-unpoliced
    why: "A default-deny in ns default would fail §4.8 for a reason unrelated to this upgrade."
    run: kubectl get netpol,cnp -n default --no-headers --ignore-not-found | wc -l
    expect_matches: "^ *0$"
  - id: fqdn-canary-namespace-policy
    why: "§4.9 relies on ci-runner-lockdown (endpointSelector {}) allowing DNS for github.com and denying anything else. Assert the allow-name is still in the policy."
    run: kubectl get cnp -n ci-runner ci-runner-lockdown -o jsonpath='{.spec.egress[0].toPorts[0].rules.dns[0].matchName}'
    expect_exact: "github.com"
status: vetted
window: "now:2026-10-25"   # ON-DEMAND NOW run 2026-10-25 (run-now.py stamp; was 'sun-attended:2026-10-25')
                                      # Recommended: an on-demand NOW run, as cilium-1.20.2 did.
review: ready-for-go@2026-10-24   # plan-reviewer 2026-10-24: 0 blocking; digests, xDS removal and Envoy-unused claims verified
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/auto-update.md
  - docs/sops/maintenance-windows.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-10-24"                # RETARGETED 1.20.3 -> 1.20.4 on 2026-10-24 (v1.20.4 published 2026-10-23); status reset to draft, review null (needs a fresh review). Earlier: refreshed 2026-10-22 (operator request): live re-verified 1.20.2, v1.20.4 still newest stable 1.20.x, PR #372 head now 3000e749 (4/4 checks pass); added the etcd gate + one-node-at-a-time OnDelete gated roll (§3.4); netpol baseline corrected 6->5 on 2026-10-23 (uzeit-de-ingress removed; measured live)
---

# cilium chart 1.20.2 → 1.20.4 (CNI datapath — plan lane by standing rule)

## 1) Summary & why held

### 1.1 What this is

Fourth bugfix patch on the Cilium 1.20 line (1.20.3 is skipped), which this cluster has run since
2026-08-03 (`97989c9b`). The two previous patches went through this same shape
of plan: `cilium-1.20.1` (`addfd9aa`, 2026-08-19) and `cilium-1.20.2`
(`80395710`, executed 2026-09-21 in an attended on-demand NOW run; every §4 gate
passed, see retire commit `c0797253`). This plan is derived from the vetted
1.20.2 plan (`git show 49009421:runbooks/maintenance/plans/cilium-1.20.2.md`), with
every number **re-measured live on 2026-10-16**. Several had moved — see §1.5.

### 1.2 Why held — the hold is about consequence, and it is correct

`runbooks/auto-update-policy.yaml` rule `*cilium*` (current text, corrected
2026-09-20 in `b9d64b70`):

> "CNI datapath — never an unattended bump. The hold is about CONSEQUENCE, not a
> specific release: a bad cilium roll takes the cluster network with it, and every
> Flux controller that would revert it sits inside the failure domain. [...]
> Requires an attended slot, a plan that exercises a FRESH CNI ADD [...], and an
> operator GO."

Nothing in 1.20.4 is breaking; the hold is the standing rule. The rule's three
requirements map to: attended slot + GO → `autonomy_override: human-gated` and
§4.10; fresh CNI ADD → §4.8 (one canary pinned per node). I checked the rule's
reason against the live cluster per authoring rule 8 and it is accurate: all
seven Flux controllers run on the pod network (`hostNetwork` unset, measured).

### 1.3 What actually changes — measured, not assumed

Rendered both charts against **our** `app/helm-values.yaml` (1734 lines each):

```
$ helm template cilium cilium/cilium --version 1.20.{2,4} -n kube-system \
    -f kubernetes/apps/kube-system/cilium/app/helm-values.yaml
# 67 changed lines (re-measured 2026-10-24). Non-label delta, in full (the agent image repeats across the
# DaemonSet's init containers, so it appears 7 times — same digest each time):
-  image: "quay.io/cilium/cilium:v1.20.2@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01"
+  image: "quay.io/cilium/cilium:v1.20.4@sha256:20fe92e4c86641233a450098c158d2d29085f3419931ab6bf681d2485dedf16e"
-  image: "quay.io/cilium/operator-generic:v1.20.2@sha256:64d8798350e8569b8e7622563fed6e44dce2625f311e4651b774816516c744fc"
+  image: "quay.io/cilium/operator-generic:v1.20.4@sha256:7a7a3489dc66ad67e420d285c8a8d2e169b0957ad15e120f593d27081bf38d82"
```

plus the cilium-config checksum annotation (2 lines, a consequence of the next item),
the `helm.sh/chart` label, and ONE CONFIGMAP KEY REMOVED (new vs the retired 1.20.3
plan, which rendered byte-identical):

```
-  envoy-xds-mode: "ads"          # cm/cilium-config; live value is "ads"
```

**Why (read from the charts, `helm pull` 1.20.2 vs 1.20.4, `values.yaml`/README):** 1.20.2's
README says `envoy.xdsMode` is "`ads` for new 1.20+ installations; none when
`upgradeCompatibility` is set below 1.20"; 1.20.4's says "none" and "Cilium Agent
defaults missing option to `split` to keep upgrades in the legacy mode". So after this
upgrade the agents run xDS in `split` mode instead of `ads`. Blast radius on THIS cluster
is nil: `envoy.enabled: false` (no cilium-envoy DaemonSet), `enable-envoy-config` is
absent from cilium-config (off), no `*envoyconfigs.cilium.io` CRD exists, and the `proxy_type="envoy"` L7 counters
read 0. xDS only configures Cilium's own Envoy listeners for CEC/Gateway API, which we do not use (the
embedded Envoy only serves the DNS-proxy L7 redirects, which do not use xDS; Envoy Gateway is a
separate product). Decision: take the upstream default, do NOT pin
`envoy.xdsMode: ads` in our values (a pin would be a permanent local override of a
deliberate upstream rollback of the default). §2/§4.3b assert both sides. The chart has no
`crds/` dir (the operator manages CRDs at startup); no CRD schema change is listed.

Renovate PR #372 carries exactly the two pins needed (HelmRelease + bootstrap
helmfile), one line each, and its CI is green.

### 1.4 Upstream content, read against THIS cluster

Primary sources: GitHub release `v1.20.4` (published 2026-10-23T14:51:39Z, out-of-band
security patch release on Go 1.26.10, all dependencies at latest patch) AND the v1.20.3
changelog (1.20.2 -> 1.20.4 includes both). No breaking changes, no action-required notes.

**Why 1.20.4 and not 1.20.3 (retarget, 2026-10-24):** 1.20.4's bugfix list contains
*"Fix regression in Cilium 1.20.3 where the Gateway API implementation would incorrectly
handle BackendTLSPolicy configurations, leading to high Cilium CPU usage and inability
to forward traffic."* **Not applicable to us, verified live:** `enable-gateway-api` is absent
from `cilium-config`; the only GatewayClass is `envoy` (`gateway.envoyproxy.io`); the one
`BackendTLSPolicy` (`monitoring/kibana-backend-tls`) is served by Envoy Gateway, not
Cilium; no Cilium CiliumEnvoyConfig CRD or object exists. So the regression could not
have hit us either way; 1.20.4 is chosen because it is the newest patch, it is what Renovate
PR #372 now carries, and it adds the fixes below.

Also new in 1.20.4 and relevant to our configuration: *LB-IPAM sharing index not updated
on service upsert when allocations are unchanged* (we run LB-IPAM with 13 pinned VIPs;
the §4.4 table is the gate); *transient DNS SERVFAIL/REFUSED for pods querying
immediately at startup* (Standalone DNS Proxy policy snapshots; we do not run the
standalone DNS proxy, informational); *terminating backends evicted from BPF maps when
trafficDistribution is enabled*; *Envoy xDS listener restoration/rejected-update fixes*
(vacuous, Envoy not in use); and the unused `pebble` binary was removed from the agent image
(clears scanner findings, see `security_ref`/finding records, detail not committed here). What lands on our configuration
(`kubeProxyReplacement`, DSR + maglev, native routing, `bpf.masquerade`,
`l2announcements`, `enable-l7-proxy: true`, `dnsproxy-enable-transparent-mode: true`):

- *"Fix conntrack garbage collection deleting CT entries that the datapath
  reopened between the GC batch read and the delete, which could cascade into NAT
  mapping deletion and SNAT source-port reallocation for live connections."* — we
  run BPF masquerade; this is the substantive reason to take the patch (shipped in 1.20.3, included in 1.20.4).
- *"Fix restoration of terminating backends"*, *"Sockets are no longer destroyed
  when a Service backend is terminated unless they are still connected to that
  backend"*, *"Fix incorrect deletion of new endpoint during GC iteration"*,
  *"Fix rare data race in selector cache that could lead to agent panic"*.
- **New since the 1.20.2 plan, and the reason this plan has a §4.9:**
  *"daemon: fix a bug where L7 DNS policies could remain loaded in the datapath
  during agent shutdown, causing pods under a wildcard toFQDNs policy to lose DNS
  resolution for the duration of the restart."* On 2026-09-21 the cluster had
  **zero** CiliumNetworkPolicies. It now has **four** (ARC CI-runner lockdowns,
  ~9–12 days old), and all four carry L7 `rules.dns` with a wildcard
  `matchPattern: '**.cluster.local'` plus `toFQDNs`. The FQDN proxy is busy:
  `cilium_policy_l7_total{proxy_type="fqdn"}` read ~800k forwarded / ~26k denied
  (measured). **Read the direction carefully: the fix is in the SHUTDOWN path of
  the agent being replaced — and the agent being replaced during THIS roll is
  1.20.2.** So this upgrade may itself show the bug once: pods in `ci-runner`,
  `arc-system`, `arc-build` may lose DNS for the seconds their node's agent
  restarts. Subsequent restarts (on 1.20.4) are fixed. (This fix shipped in 1.20.3 and is included in 1.20.4.) Impact: an in-flight CI job
  can fail and an ARC listener reconnects — interruption, not data loss.

Upstream behaviour changes that **could** have mattered, each checked live and
**vacuous here** (each is also a premise):

| 1.20.4 change | Live state | Verdict |
|---|---|---|
| Operator now rejects CNPs with a `nodeSelector` that would enforce nothing | none of the 4 CNPs uses `nodeSelector` | vacuous; §4.7b still asserts all 4 stay VALID |
| CLRP with empty `redirectBackend.toPorts` now rejected | 0 CiliumLocalRedirectPolicies | vacuous |
| CiliumCIDRGroup `0.0.0.0/0` now selects traffic (previously nothing) | 0 CiliumCIDRGroups; no CNP/netpol uses `0.0.0.0/0` | vacuous |
| Gateway API / ExternalAuth / Envoy listener fixes; BackendTLSPolicy regression fix; "update gateway api to v1.6.3" | `enable-gateway-api` ABSENT in `cilium-config`; the only GatewayClass is Envoy Gateway's; `proxy_type="envoy"` L7 counters all 0 | Cilium's Gateway API and L7 HTTP proxying are not in use; not a reason to take, not a risk |
| CiliumEnvoyConfig now only redirects Services in its own namespace (1.20.4) | no CiliumEnvoyConfig CRD or object (premise `no-cilium-envoyconfig-crds-or-objects`) | vacuous |
| `envoy-xds-mode` no longer rendered; agent defaults to split | `envoy.enabled: false`, `enable-envoy-config` absent from cilium-config (feature off; embedded Envoy only serves the DNS-proxy L7 redirects); live key was `ads` | accepted, see §1.3; asserted in §4.3b |
| Hubble cert-manager key fix | `hubble.enabled: false` | vacuous |
| Azure / AlibabaCloud / dual-stack ENI fixes | bare-metal Talos, IPv4 native routing | vacuous |

### 1.5 Numbers that moved since the 1.20.2 plan (do not copy from it)

| Fact | 1.20.2 plan (2026-09-21) | Live 2026-10-16 |
|---|---|---|
| LoadBalancer Services / L2 leases | 14 / 14 | **13 / 13** |
| k8s NetworkPolicies | 6 | **5** |
| CiliumNetworkPolicies | 0 | **4** (L7 DNS + toFQDNs) |
| Endpoints with enforcement Enabled (sum over agents) | 6 | **14** (2 + 6 + 6) |
| helm revision holding the current chart | 13 (1.20.1) | **14 (1.20.2)** |
| Talos | 1.14.0 | 1.14.1 (agents restarted 2026-09-27 by that roll) |
| ds/cilium updateStrategy | maxUnavailable 2, maxSurge 0 | temporarily OnDelete (3.4), restored to the same after |

### 1.6 Security

The two image records are `F-a571f10d` (agent) and `F-cb6c175f`
(operator-generic), both currently accepted under `[AR-029]` "already newest".
With 1.20.4 published that premise no longer holds, and this plan moves both
digests. Detail stays on the finding records.

---

## 2) Pre-checks

Run from `/Users/mu/code/cberg-home-nextgen`, **after Step 0 of the window has
settled** (baselines taken before Step 0 make §4 diff against stale state).

```bash
cd /Users/mu/code/cberg-home-nextgen
helm repo update cilium >/dev/null   # premise chart-1.20.4-is-published reads the LOCAL cache
.venv/bin/python3 runbooks/plan-premises.py cilium-1.20.4 --require-premises
#   PASS: every premise PASS, exit 0.
#   A first FAIL naming only no-kustomization-in-flight / no-helmrelease-in-flight
#   is Step 0 still settling: wait ~60s and re-run ONCE. Any other FAIL, or a
#   second FAIL, is a stop.
```

The gates below use `$( )`, `>`, loops or `gh`, which the premise runner refuses.
Run them by hand; each states its PASS and FAIL.

```bash
# a) Agent health on EVERY node (not `exec ds/cilium`, which picks one pod).
for p in $(kubectl get pods -n kube-system -l k8s-app=cilium -o name); do
  echo -n "$p: "; kubectl -n kube-system exec "$p" -c cilium-agent -- cilium-dbg status --brief
done
#   PASS: 3x OK.   FAIL: any non-OK line — STOP.

# b) Module health baseline — the gate is Stopped(0) Degraded(0) on all three.
for p in $(kubectl get pods -n kube-system -l k8s-app=cilium -o name); do
  echo -n "$p "; kubectl -n kube-system exec "$p" -c cilium-agent -- cilium-dbg status | grep -E 'Modules Health'
done
#   Measured 2026-10-16: Stopped(0) Degraded(0) OK(343/372/313). The OK count drifts
#   with pod placement — colour, never a gate.

# c) PR #372 is still exactly what §3.2 expects.
gh pr view 372 --json state,mergeStateStatus --jq '.state + " " + .mergeStateStatus'   # PASS: OPEN CLEAN
gh pr checks 372                                       # PASS: every line "pass"
gh pr diff 372 --name-only                             # PASS: exactly the two files in §3.2
gh pr diff 372 | grep -E '^[+-][^+-]'                  # PASS: exactly these 4 lines:
#   -      version: 1.20.2
#   +      version: 1.20.4
#   -    version: 1.20.2
#   +    version: 1.20.4
#   FAIL: any other line (Renovate rebased new content in) — STOP and re-review.

# e) LB table baseline (domain-free, VIPs only).
kubectl get svc -A -o json | .venv/bin/python3 -c "
import sys, json
d = json.load(sys.stdin)
rows = sorted((i['metadata']['namespace'] + '/' + i['metadata']['name'],
               (i['status'].get('loadBalancer', {}).get('ingress') or [{}])[0].get('ip'))
              for i in d['items'] if i['spec']['type'] == 'LoadBalancer')
[print(n, ip) for n, ip in rows]
" > /tmp/cilium-lb-before.txt
wc -l < /tmp/cilium-lb-before.txt                      # PASS: 13

# h) LAN reachability baseline through both gateway VIPs + DNS VIP.
HINT=$(kubectl get httproute -n default echo-server -o jsonpath='{.spec.hostnames[0]}')
HEXT=$(kubectl get httproute -n office mealie -o jsonpath='{.spec.hostnames[0]}')
curl -sk --resolve "$HINT:443:192.168.55.103" -o /dev/null -w 'envoy-internal .103 -> %{http_code}\n' --max-time 10 "https://$HINT/"
curl -sk --resolve "$HEXT:443:192.168.55.104" -o /dev/null -w 'envoy-external .104 -> %{http_code}\n' --max-time 10 "https://$HEXT/"
#   PASS: 200 and 200. FAIL: anything else — the edge is already broken; do not start.

# l) OPERATOR — no active Music Assistant stream / Plex playback, and no CI job
#    the operator cares about is mid-run (§1.4: CI pods may lose DNS for seconds).

# m) Policy-enforcement baseline FROM THE DATAPATH (each agent's BPF endpoint table).
for p in $(kubectl get pods -n kube-system -l k8s-app=cilium -o name); do
  kubectl -n kube-system exec "$p" -c cilium-agent -- cilium-dbg endpoint list
done | grep -c 'Enabled' | tee /tmp/cilium-enf-before.txt
for n in ci-runner arc-system arc-build; do kubectl get pods -n $n --no-headers; done | wc -l | tee /tmp/cilium-ci-pods-before.txt
#   Measured 2026-10-16: 14 enabled; 7 pods across the three CI namespaces.
#   The CI pods are ARC runners that scale with jobs, so this count is a WINDOW
#   baseline, never a constant. `grep -c 'Enabled'` does not match "Disabled".

# n) FQDN canary BASELINE — proves §4.9 measures what it claims BEFORE anything changes.
#    Run the §4.9 block now, unchanged. PASS: FQDN_ALLOW_OK and FQDN_DENY_OK on all
#    three nodes. If the baseline itself does not read that (e.g. coredns cannot
#    resolve external names tonight), §4.9 is not a valid gate for this window:
#    record why and treat §4.9 as INFORMATIONAL — do not let a pre-existing state
#    trigger a CNI rollback.
# o) etcd gate (added 2026-10-22: 21 leader changes on 10-20; 1 in the 24h to 10-22).
#    The cilium agent restart on a control-plane node perturbs the node's pod
#    network, and etcd runs on these same 3 nodes. This gate talks to Talos on the
#    node IPs (NOT the pod network), so it still answers when the CNI is sick.
cat > /tmp/cilium-etcd-gate.sh <<'GATE'
#!/bin/bash
# cilium-etcd-gate: exit 0 = etcd healthy; exit 1 = STOP. Reads Talos (not the pod network).
N=192.168.55.11,192.168.55.12,192.168.55.13
OUT=$(talosctl -n "$N" etcd status 2>&1) || { echo "GATE-FAIL talosctl: $OUT"; exit 1; }
echo "$OUT" | .venv/bin/python3 -c "
import sys, re
rows = [l for l in sys.stdin if re.match(r'^192\.168\.55\.1[123]\s', l)]
ok = len(rows) == 3
leaders, members, errs = set(), set(), []
for l in rows:
    h = re.findall(r'\b[0-9a-f]{16}\b', l)
    if len(h) < 2: ok = False; continue
    members.add(h[0]); leaders.add(h[1])
    if not re.search(r'\s3\.\d+\.\d+\s*$', l): errs.append(l.strip())  # ERRORS column non-empty
if not ok or len(leaders) != 1 or not leaders <= members or errs:
    print('GATE-FAIL rows=%d leaders=%s errs=%s' % (len(rows), leaders, errs)); sys.exit(1)
lead = [l.split()[0] for l in rows if re.findall(r'\b[0-9a-f]{16}\b', l)[0] in leaders][0]
print('GATE-OK 3 members, 1 leader, LEADER_IP=' + lead)
"
GATE
chmod +x /tmp/cilium-etcd-gate.sh
bash /tmp/cilium-etcd-gate.sh
#   PASS: "GATE-OK 3 members, 1 leader, LEADER_IP=192.168.55.1x" (verified 2026-10-22,
#         LEADER_IP=.11). FAIL (exit 1, "GATE-FAIL ..."): fewer than 3 rows, 2+ distinct
#         leaders (split view), a non-empty ERRORS column, or talosctl unreachable.
#         Negative control run 2026-10-22: pointing N at one IP printed "GATE-FAIL rows=1".
#   Also PASS premise etcd-leader-changes-24h-below-6. Record the counter baseline:
kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=max(etcd_server_leader_changes_seen_total)' \
  | .venv/bin/python3 -c "import sys,json;print(json.load(sys.stdin)['data']['result'][0]['value'][1])" | tee /tmp/cilium-etcd-lc-before.txt
#   PASS: a number. FAIL: IndexError/empty (Prometheus not scraping etcd) - STOP; this plan
#   needs that counter to tell "the roll hurt etcd" from "etcd was already sick".

# p) Pre-pull the new images at NODE level (containerd, host network - independent of the
#    CNI), so a pod restart never waits on a registry pull while its node has no datapath.
for ip in 192.168.55.11 192.168.55.12 192.168.55.13; do
  talosctl -n $ip image pull quay.io/cilium/cilium:v1.20.4@sha256:20fe92e4c86641233a450098c158d2d29085f3419931ab6bf681d2485dedf16e
  talosctl -n $ip image pull quay.io/cilium/operator-generic:v1.20.4@sha256:7a7a3489dc66ad67e420d285c8a8d2e169b0957ad15e120f593d27081bf38d82
done
for ip in 192.168.55.11 192.168.55.12 192.168.55.13; do
  talosctl -n $ip image list | grep -c -E 'sha256:(20fe92e4c8664123|7a7a3489dc66ad67)'
done
#   PASS: 3 lines, each >= 2 (agent + operator digests present on that node).
#   FAIL: any 0/1 - STOP, the pull failed (registry/egress); do not start a CNI roll that must pull.
#   (digests = the rendered 1.20.4 values from `helm template`, see 1.3; re-derive if #372's head changed.)
```

---

## 3) Steps

### 3.1 Active-update marker (application-update.md §Step 1b)

```bash
cd /Users/mu/code/cberg-home-nextgen
runbooks/update-marker.sh add cilium kube-system 2 "chart 1.20.2 -> 1.20.4 CNI patch"
```

### 3.2 Land the pins by merging Renovate PR #372

Same merge mode as `auto-update.py`. §2c already proved the diff.

```bash
gh pr merge 372 --squash --delete-branch
git fetch origin main && git merge --ff-only origin/main
grep -n '^      version: 1.20.4$' kubernetes/apps/kube-system/cilium/app/helmrelease.yaml   # PASS: 1 line
grep -c 'version: 1.20.4' kubernetes/bootstrap/apps/helmfile.yaml                           # PASS: 1
SHA=$(git log -1 --format=%H -- kubernetes/apps/kube-system/cilium/app/helmrelease.yaml)
echo "$SHA" > /tmp/cilium-bump-sha.txt
git show --stat "$SHA"     # PASS: exactly the two files, 1 insertion + 1 deletion each
# GATE before 3.4b: the DaemonSet TEMPLATE must name the 1.20.4 agent digest (and still be OnDelete, so no pod moved)
flux reconcile source git flux-system && flux reconcile hr cilium -n kube-system
kubectl wait hr/cilium -n kube-system --for=condition=Ready --timeout=10m
kubectl get hr -n kube-system cilium -o jsonpath='{.status.history[0].chartVersion}{"\n"}'   # PASS: 1.20.4 (FAIL: 1.20.2 - Flux has not applied the bump; do NOT start 3.4b)
kubectl get ds -n kube-system cilium -o jsonpath='{.spec.template.spec.containers[?(@.name=="cilium-agent")].image}{"\n"}' | grep -c '20fe92e4'   # PASS: 1 (0 = template still on 1.20.2: 3.4b'"'"'s image check would then be vacuous - STOP)
kubectl get ds -n kube-system cilium -o jsonpath='{.spec.updateStrategy.type}{"\n"}'          # PASS: OnDelete
kubectl get pods -n kube-system -l k8s-app=cilium --no-headers -o custom-columns=N:.metadata.name,S:.status.startTime | diff - /tmp/cilium-pod-start-before.txt && echo AGENTS-UNTOUCHED   # PASS: AGENTS-UNTOUCHED
```

*Fallback, only if #372 was closed unmerged and HEAD still pins 1.20.2.* Both
edits were dry-tested on scratch copies with BSD sed / python on 2026-10-16 and
each changed exactly one line (`12c12 version: 1.20.2 → 1.20.4` and
`21c21 version: 1.20.2 → 1.20.4`):

```bash
sed -i '' 's/^      version: 1\.20\.2$/      version: 1.20.4/' \
  kubernetes/apps/kube-system/cilium/app/helmrelease.yaml
.venv/bin/python3 - <<'PY'
import re
p = 'kubernetes/bootstrap/apps/helmfile.yaml'
s = open(p).read()
new = re.sub(r'(- name: cilium\n    namespace: kube-system\n    chart: cilium/cilium\n    version: )1\.20\.2',
             r'\g<1>1.20.4', s)
assert s != new, 'anchor did not match — STOP and inspect the file'
open(p, 'w').write(new)
PY
cat > /tmp/cilium-msg.txt <<'EOF'
feat(cilium): chart 1.20.2 -> 1.20.4 (CNI patch; plan cilium-1.20.4)

Bugfix/security patch on the 1.20 line (skips 1.20.3). Rendered delta against
our values is two image digests (agent + operator-generic) plus the
envoy-xds-mode key dropping out of cilium-config (Envoy is not enabled
here). Carries the conntrack-GC / SNAT fix, the L7-DNS shutdown fix for
toFQDNs policies and the LB-IPAM sharing-index fix.
EOF
git commit --only kubernetes/apps/kube-system/cilium/app/helmrelease.yaml \
  kubernetes/bootstrap/apps/helmfile.yaml -F /tmp/cilium-msg.txt
git log -1 --format=%s     # MUST be the subject above; else git commit --amend -F /tmp/cilium-msg.txt
git show --stat HEAD       # MUST list exactly the two files
git push origin main
git rev-parse HEAD > /tmp/cilium-bump-sha.txt
```

### 3.3 (none — the config Kustomization is out of scope)

`kubernetes/apps/kube-system/cilium/config/` (LB pool, L2 policy) is a separate
Kustomization that `dependsOn` cilium. Never bundle a pool edit into a version
bump — a bad pool and a bad agent look identical from the LAN.

### 3.4 REQUIRED (changed 2026-10-22) - ONE NODE AT A TIME, etcd-gated, via `updateStrategy: OnDelete`

The operator rule is "never two nodes at once". The chart default is
`maxUnavailable: 2` (live: `{"maxSurge":0,"maxUnavailable":2}`), and a RollingUpdate
cannot be gated BETWEEN nodes by anything outside the cluster. `OnDelete` can: the
DaemonSet never restarts a pod by itself, so the template change in #372 lands with
zero agent restarts, and this runbook restarts one agent at a time with the etcd gate
(2o) before and after each. Rendered with our values (`helm template ... -f
helm-values.yaml`, 2026-10-22) the OnDelete flag changes exactly ONE line vs the plain
1.20.4 render: `1010c1010  <     type: RollingUpdate  /  >     type: OnDelete`; and
1.20.2 -> 1.20.4 changes only the chart label, the agent digest
(`2939231d` -> `20fe92e4`) and the operator digest (`64d87983` -> `7a7a3489`);
configmap/cilium-config renders identical.

**Mandatory order: 3.1 -> 3.4a -> 3.2 -> 3.4b -> 3.4c -> 3.6.** (3.2 is above in the file.)

**3.4a - commit OnDelete FIRST, separately** (pods must NOT restart):

```bash
(   # subshell + set -e: any failing line (or a STOP) ends THIS block, never your terminal
set -e
cd /Users/mu/code/cberg-home-nextgen
kubectl get pods -n kube-system -l k8s-app=cilium --no-headers -o custom-columns=N:.metadata.name,S:.status.startTime > /tmp/cilium-pod-start-before.txt
V=kubernetes/apps/kube-system/cilium/app/helm-values.yaml
test "$(grep -c '^updateStrategy:' $V)" = 0 || { echo "STOP: updateStrategy already in $V (a duplicate top-level key is a YAML error or a silent override)"; exit 1; }
printf 'updateStrategy:\n  type: OnDelete\n' >> $V
tail -3 $V   # PASS: socketLB tail then the 2 new lines
# PRE-PUSH GATE (can FAIL; do not commit before it passes): render the REAL values file + appended key against chart 1.20.4
helm repo add cilium https://helm.cilium.io >/dev/null 2>&1; helm repo update cilium >/dev/null 2>&1
helm template cilium cilium/cilium --version 1.20.4 -n kube-system -f $V > /tmp/cilium-od-render.yaml; echo "helm rc=$?"      # PASS: rc=0 (FAIL: YAML/schema error from the append)
test "$(grep -c 'type: OnDelete' /tmp/cilium-od-render.yaml)" = 1 || { echo 'STOP: OnDelete count != 1'; exit 1; }   # PASS: exactly 1 (0 = key not honoured; 2+ = duplicated)
python3 - <<'PY'
import yaml
d=[x for x in yaml.safe_load_all(open('/tmp/cilium-od-render.yaml')) if x and x.get('kind')=='DaemonSet' and x['metadata']['name']=='cilium']
assert len(d)==1, len(d)
yaml.safe_dump(d[0],open('/tmp/cilium-od-ds.yaml','w')); print('DS strategy:',d[0]['spec']['updateStrategy'])
PY
kubectl apply --dry-run=server -f /tmp/cilium-od-ds.yaml                            # PASS: "configured (server dry run)"; FAIL: any validation Error. (The last-applied-configuration warning is expected noise.)
kubeconform -summary -ignore-missing-schemas /tmp/cilium-od-ds.yaml                 # PASS: Invalid: 0, Errors: 0
printf 'chore(cilium): updateStrategy OnDelete for a gated one-node-at-a-time roll (plan cilium-1.20.4)\n' > /tmp/cilium-od-msg.txt
git commit --only kubernetes/apps/kube-system/cilium/app/helm-values.yaml -F /tmp/cilium-od-msg.txt
git log -1 --format=%s ; git show --stat HEAD     # subject must be YOURS; exactly this one file
git push origin main
echo "$(git rev-parse HEAD)" > /tmp/cilium-od-sha.txt
flux reconcile source git flux-system && flux reconcile hr cilium -n kube-system   # do not wait on the webhook
kubectl wait hr/cilium -n kube-system --for=condition=Ready --timeout=10m
kubectl get ds -n kube-system cilium -o jsonpath='{.spec.updateStrategy.type}{"\n"}'   # PASS: OnDelete (FAIL: RollingUpdate - Flux has not applied; wait/inspect)
kubectl get pods -n kube-system -l k8s-app=cilium --no-headers -o custom-columns=N:.metadata.name,S:.status.startTime | diff - /tmp/cilium-pod-start-before.txt && echo PODS-UNTOUCHED
#   PASS: PODS-UNTOUCHED (diff exit 0). FAIL: any pod restarted -> OnDelete did not hold; STOP, go to 5.
)
```

**What the appended key does (measured 2026-10-23, helm 3 against chart 1.20.4 with the real
values file):** Helm DEEP-MERGES values maps, so the append does not replace the chart default
block `{type: RollingUpdate, rollingUpdate: {maxUnavailable: 2}}` - it overrides only `type`.
The rendered DaemonSet carries `type: OnDelete` with the leftover `rollingUpdate.maxUnavailable: 2`
(inert under OnDelete, accepted by the API: `kubectl apply --dry-run=server` configured; live
object shows `{"rollingUpdate":{"maxSurge":0,"maxUnavailable":2},"type":"OnDelete"}`, maxSurge being
the API default). The chart default IS overridden for `type`; maxSurge/maxUnavailable no longer
govern anything while OnDelete is on, which is intended and harmless (3.4c restores them with the
revert). The gate above guards against a duplicate top-level key and a render/validation failure.

**3.2** (above) merges #372 now. Expect: `cilium-operator` restarts (1 replica, brief
operator gap: no new LB-IPAM allocations/identity GC for ~1 min, no datapath effect); the three
agents DO NOT restart; `ds/cilium` template now names the 1.20.4 digest.

**3.4b - per-node roll, followers first, etcd leader's node last:**

```bash
cat > /tmp/cilium-roll.sh <<'ROLL_EOF'
#!/usr/bin/env bash
# Written to a FILE and run as a child, so the `exit 1` STOPs end this script, never your terminal.
set -u
cd /Users/mu/code/cberg-home-nextgen
HINT=$(kubectl get httproute -n default echo-server -o jsonpath='{.spec.hostnames[0]}')   # same as pre-check 2h
HEXT=$(kubectl get httproute -n office mealie -o jsonpath='{.spec.hostnames[0]}')
test -n "$HINT" && test -n "$HEXT" || { echo 'STOP: empty HINT/HEXT'; exit 1; }
bash /tmp/cilium-etcd-gate.sh > /tmp/cilium-gate-out.txt 2>&1; GRC=$?    # NOT `| tee ||`: that tests tee's status, not the gate's
cat /tmp/cilium-gate-out.txt
[ $GRC -eq 0 ] || { echo "STOP: etcd gate rc=$GRC"; exit 1; }
LEADER=$(grep -o 'LEADER_IP=[0-9.]*' /tmp/cilium-gate-out.txt | cut -d= -f2)
# node name for each control-plane IP (k8s-nuc14-01=.11, -02=.12, -03=.13; verified 2026-10-22)
ORDER=""
for ip in 192.168.55.11 192.168.55.12 192.168.55.13; do [ "$ip" != "$LEADER" ] && ORDER="$ORDER $ip"; done
ORDER="$ORDER $LEADER"
echo "roll order: $ORDER"
for ip in $ORDER; do
  NODE=$(kubectl get nodes -o wide --no-headers | awk -v ip=$ip '$6==ip{print $1}')
  echo "=== $NODE ($ip) ==="
  bash /tmp/cilium-etcd-gate.sh || { echo "STOP before $NODE: etcd gate"; exit 1; }
  kubectl -n kube-system delete pod -l k8s-app=cilium --field-selector spec.nodeName=$NODE --wait=true
  n=0
  until kubectl -n kube-system get pods -l k8s-app=cilium --field-selector spec.nodeName=$NODE \
        -o jsonpath='{.items[0].status.containerStatuses[0].imageID} {.items[0].status.containerStatuses[0].ready}' | grep -q '20fe92e4c8664123.* true'; do
    n=$((n+1)); [ $n -gt 60 ] && { echo "STOP: $NODE agent not Ready on 1.20.4 after 5 min"; exit 1; }; sleep 5
  done
  P=$(kubectl -n kube-system get pods -l k8s-app=cilium --field-selector spec.nodeName=$NODE -o name)
  kubectl -n kube-system exec $P -c cilium-agent -- cilium-dbg status --brief | grep -qx OK || { echo "STOP: $NODE cilium-dbg not OK"; exit 1; }
  kubectl get node $NODE --no-headers | grep -q ' Ready' || { echo "STOP: $NODE NotReady"; exit 1; }
  sleep 60                                   # let etcd/apiserver surface any perturbation
  bash /tmp/cilium-etcd-gate.sh || { echo "STOP after $NODE: etcd gate"; exit 1; }
  LC=$(kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=max(etcd_server_leader_changes_seen_total)' | .venv/bin/python3 -c "import sys,json;print(int(float(json.load(sys.stdin)['data']['result'][0]['value'][1])))")
  B=$(cat /tmp/cilium-etcd-lc-before.txt | cut -d. -f1)
  [ $((LC-B)) -le 1 ] || { echo "STOP: etcd leader changes +$((LC-B)) since baseline"; exit 1; }
  curl -sk -o /dev/null -w "envoy-internal .103 -> %{http_code}\n" --max-time 10 --resolve "$HINT:443:192.168.55.103" "https://$HINT/" | grep -q ' 200' || { echo "STOP: .103 not 200"; exit 1; }
  curl -sk -o /dev/null -w "envoy-external .104 -> %{http_code}\n" --max-time 10 --resolve "$HEXT:443:192.168.55.104" "https://$HEXT/" | grep -q ' 200' || { echo "STOP: .104 not 200"; exit 1; }
done
ROLL_EOF
bash /tmp/cilium-roll.sh; echo "roll rc=$?"      # PASS: rc=0 and 3 nodes rolled. rc!=0: a STOP line printed above.
```

The script derives `$HINT`/`$HEXT` itself (same two lookups as pre-check 2h) and needs `/tmp/cilium-etcd-gate.sh` and `/tmp/cilium-etcd-lc-before.txt` from §2o. A STOP leaves the cluster
**mixed 1.20.2/1.20.4 and stable** (patch-level agent skew, same chart, OnDelete keeps
the rest untouched): do NOT continue and do NOT auto-rollback; hand to an operator
(Rollback 5.2/5.3, and a stuck node: `kubectl -n kube-system delete pod` of the
new agent once, then re-run the gate). The gates can FAIL: etcd gate prints GATE-FAIL
(negative control in 2o); the image check fails if the pod came back on `2939231d`; `+N`
leader changes uses the live counter baseline from 2o (a counter that does not move
reads 0 - so a Prometheus scrape gap would hide a change; the etcd gate itself reads
Talos, not Prometheus, and is the primary control).

**3.4c - restore RollingUpdate (zero pod restarts):**

```bash
kubectl get pods -n kube-system -l k8s-app=cilium --no-headers -o custom-columns=N:.metadata.name,S:.status.startTime > /tmp/cilium-pod-start-after-roll.txt
git revert --no-edit "$(cat /tmp/cilium-od-sha.txt)"
git log -1 --format=%s; git show --stat HEAD; git push origin main
flux reconcile source git flux-system && flux reconcile hr cilium -n kube-system   # do not wait on the webhook
kubectl wait hr/cilium -n kube-system --for=condition=Ready --timeout=10m
kubectl get ds -n kube-system cilium -o jsonpath='{.spec.updateStrategy.type} {.status.numberReady}/{.status.desiredNumberScheduled} {.status.updatedNumberScheduled}{"\n"}'
kubectl get pods -n kube-system -l k8s-app=cilium --no-headers -o custom-columns=N:.metadata.name,S:.status.startTime | diff - /tmp/cilium-pod-start-after-roll.txt && echo ROLL-DID-NOT-RESTART-AGENTS
#   PASS: RollingUpdate 3/3 3.  FAIL: updatedNumberScheduled < 3 (a pod would roll
#   unattended) - STOP. Pod start times must equal /tmp/cilium-pod-start-after-roll.txt (recorded just before this revert).
```

### 3.5 Watch the roll

3.4b IS the watch (it blocks and gates). `rollout status ds/cilium` is meaningless under
OnDelete; the per-node image check + §4.1 are the proof. `rollout status deploy/cilium-operator
--timeout=5m` still applies after 3.2.

### 3.6 On success

```bash
runbooks/update-marker.sh clear cilium
```

---

## 4) Verification

Every gate states its failure. A gate that cannot fail is not in this section.

**4.1 — The version moved, on every node.**

```bash
kubectl get hr -n kube-system cilium \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion}{"\n"}'
#   PASS: True 1.20.4     FAIL: UpgradeFailed / still 1.20.2
kubectl -n kube-system get pods -l k8s-app=cilium \
  -o jsonpath='{range .items[*]}{.spec.nodeName} {.status.containerStatuses[0].imageID}{"\n"}{end}'
#   PASS: 3 lines, each imageID ends sha256:20fe92e4c8664123...
#   FAIL: any line on 2939231d... (an agent never rolled)
kubectl -n kube-system get pods -l name=cilium-operator \
  -o jsonpath='{.items[*].status.containerStatuses[0].imageID}{"\n"}'
#   PASS: contains sha256:7a7a3489dc66ad67...
```

**4.2 — CONTENTS: every agent is scraped and reports 1.20.4; the FQDN proxy is
forwarding again.**

```
CONTENTS ASSERTION: all 3 agents report version 1.20.4 and none 1.20.2 — measured
by count(cilium_version{version=...}), compared to the measured baseline of exactly
3 series at version="1.20.2" (2026-10-16).
CONTENTS ASSERTION: the DNS proxy is forwarding real queries after the roll —
measured by the increase of cilium_policy_l7_total{proxy_type="fqdn",rule="forwarded"}
over 10 minutes that start AFTER the roll completes, compared to a floor of > 0
(baseline: ~800k cumulative; CI pods query continuously).
CONTROL: metric cilium_version — count by version; gate: ==3 at 1.20.4, empty at 1.20.2
CONTROL: metric up — job="cilium-agent"; gate: count(up==1) == 3
CONTROL: metric cilium_policy_l7_total — proxy_type="fqdn", rule="forwarded"; gate: increase > 0
CONTROL: metric cilium_endpoint_state — gate: waiting-for-identity + regenerating + restoring == 0, ready > 0
```

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 >/dev/null 2>&1 & PF=$!
sleep 3
q() { curl -s --get http://localhost:9090/api/v1/query --data-urlencode "query=$1" \
  | .venv/bin/python3 -c "import sys,json; r=json.load(sys.stdin)['data']['result']; print([x['value'][1] for x in r] or 'EMPTY')"; }
q 'count(cilium_version{version="1.20.4"})'        # PASS: ['3']
q 'count(cilium_version{version="1.20.2"})'        # PASS: EMPTY
q 'count(up{job="cilium-agent"} == 1)'             # PASS: ['3']
# wait until >=10 min after §3.5 completed, then:
q 'sum(increase(cilium_policy_l7_total{proxy_type="fqdn",rule="forwarded"}[10m]))'   # PASS: > 0
q 'sum(cilium_endpoint_state{endpoint_state=~"waiting-for-identity|regenerating|restoring"})'  # PASS: ['0']
q 'sum(cilium_endpoint_state{endpoint_state="ready"})'                                # PASS: > 0 (baseline 252)
kill $PF 2>/dev/null
```

*Why these can fail:* `up` alone passes with agents stuck on the old image;
`cilium_version` alone goes EMPTY (not red) if scraping broke — the three
together fail on wrong version, missing node, and dead scrape. The `q` helper
prints `EMPTY` rather than nothing, so an empty result is visible. The
`increase()` gate handles the counter reset on agent restart; it reads 0 if the
proxy stopped forwarding, which is exactly the toFQDNs failure §1.4 describes.

**4.3 — Agent + module health on every node.**

```bash
for p in $(kubectl get pods -n kube-system -l k8s-app=cilium -o name); do
  echo -n "$p: "; kubectl -n kube-system exec "$p" -c cilium-agent -- cilium-dbg status --brief
  kubectl -n kube-system exec "$p" -c cilium-agent -- cilium-dbg status | grep -E 'Modules Health'
done
#   PASS: 3x OK and Stopped(0) Degraded(0) on all three.
#   FAIL: any non-OK, or Degraded(n>0) — the brief line can read OK while a module
#   is degraded, which is why both are read.
```

**4.3b — The xDS-mode change landed as §1.3 says, and nothing depends on it.**

```bash
kubectl get cm -n kube-system cilium-config -o jsonpath='xds=[{.data.envoy-xds-mode}]{"\n"}'
kubectl get ds -n kube-system -o name | grep -c -i envoy
#   PASS: xds=[]  (key gone, == 1.20.4 chart behaviour) and 0 envoy DaemonSets.
#   FAIL: xds=[ads] after the HR is on 1.20.4 (HR did not apply the new chart: re-read 4.1),
#         or a cilium-envoy DaemonSet exists (someone enabled envoy: §1.3's blast-radius
#         argument is void; STOP and re-review). Premise live-xds-mode-is-ads is the 'before'.
```

**4.4 — LB table byte-identical; leases re-formed.**

```bash
kubectl get svc -A -o json | .venv/bin/python3 -c "
import sys, json
d = json.load(sys.stdin)
rows = sorted((i['metadata']['namespace'] + '/' + i['metadata']['name'],
               (i['status'].get('loadBalancer', {}).get('ingress') or [{}])[0].get('ip'))
              for i in d['items'] if i['spec']['type'] == 'LoadBalancer')
[print(n, ip) for n, ip in rows]
" > /tmp/cilium-lb-after.txt
if diff /tmp/cilium-lb-before.txt /tmp/cilium-lb-after.txt; then echo 'LB TABLE UNCHANGED'; else echo 'LB TABLE CHANGED — FAIL'; fi
kubectl get leases -n kube-system -o name | grep -c cilium-l2announce
#   PASS: 'LB TABLE UNCHANGED' and 13.
#   FAIL: an IP empty or changed (LB-IPAM lost a pin), or fewer leases (a VIP is
#   dark on the LAN while its Service still shows an IP).
```

**4.5 — Both gateway VIPs still serve.** Re-run §2h verbatim.
PASS: 200 and 200. The probe pins the connection to the VIP with `--resolve`; the
same probe against an unused VLAN-55 address returns `000`/exit 28 (measured on
the 1.20.2 run), so a dark VIP is a hard failure.

**4.6 — LAN VIP surface beyond the gateways.**

```bash
if dig +short +time=2 +tries=1 @192.168.55.5 kubernetes.io | grep -q '[0-9]'; then
  echo 'DNS VIP .5 OK'; else echo 'DNS VIP .5 FAIL'; fi
curl -sk -o /dev/null -w 'HA .24:8123 -> %{http_code}\n' --max-time 8 http://192.168.55.24:8123
curl -sk -o /dev/null -w 'MA .29:8095 -> %{http_code}\n' --max-time 8 http://192.168.55.29:8095
#   PASS: 'DNS VIP .5 OK', 200, 200.   FAIL: the FAIL line, or 000.
```

**4.7 — Policy enforcement survived (datapath, not API server).**

```bash
# a) enforcement count
for p in $(kubectl get pods -n kube-system -l k8s-app=cilium -o name); do
  kubectl -n kube-system exec "$p" -c cilium-agent -- cilium-dbg endpoint list
done | grep -c 'Enabled'
for n in ci-runner arc-system arc-build; do kubectl get pods -n $n --no-headers; done | wc -l
#   PASS: enforcement count == /tmp/cilium-enf-before.txt (14 at authoring).
#   If it differs, compare the CI-pod count against /tmp/cilium-ci-pods-before.txt:
#   an ARC runner scaling up/down moves the count legitimately (every pod in those
#   namespaces is policy-selected). A DROP with an UNCHANGED CI-pod count is a FAIL —
#   agents that came up without policy print "Disabled" instead.
# b) CNP validity under the 1.20.4 operator's new validation
kubectl get cnp -A --no-headers | awk '$4!="True"{print "INVALID: "$0}' ; kubectl get cnp -A --no-headers | wc -l
#   PASS: no INVALID line, count 4.   FAIL: any INVALID line (the new operator
#   rejected one of our policies — its pods are now unprotected or blocked).
```

**4.8 — A FRESH POD GETS NETWORKING, on every node.** (The deny rule's
requirement: existing pods keep networking from in-kernel BPF state, so every
gate above can pass while `CNI ADD` is broken for new pods.)

```bash
for N in k8s-nuc14-01 k8s-nuc14-02 k8s-nuc14-03; do
  kubectl -n default delete pod "cni-canary-$N" --ignore-not-found
  kubectl -n default run "cni-canary-$N" --restart=Never --image=busybox:1.38.0 \
    --overrides="{\"spec\":{\"nodeName\":\"$N\"}}" --command -- sh -c \
    'wget -q -T 5 -O- http://echo-server.default.svc.cluster.local:8080/ >/dev/null && echo CNI_CANARY_OK || echo CNI_CANARY_FAIL'
done
for N in k8s-nuc14-01 k8s-nuc14-02 k8s-nuc14-03; do
  POD="cni-canary-$N"; echo "===== $N ====="
  kubectl -n default wait --for=jsonpath='{.status.phase}'=Succeeded "pod/$POD" --timeout=120s \
    || { echo "GATE1 FAIL $N"; kubectl -n default describe pod "$POD" | tail -20; }
  IP=$(kubectl -n default get pod "$POD" -o jsonpath='{.status.podIP}')
  case "$IP" in 10.69.*) echo "GATE2 PASS podIP=$IP";; *) echo "GATE2 FAIL podIP='$IP'";; esac
  kubectl -n default logs "$POD" | grep -qx CNI_CANARY_OK && echo "GATE3 PASS" \
    || { echo "GATE3 FAIL"; kubectl -n default logs "$POD"; }
done
for N in k8s-nuc14-01 k8s-nuc14-02 k8s-nuc14-03; do kubectl -n default delete pod "cni-canary-$N" --ignore-not-found; done
#   PASS: per node, "condition met", GATE2 PASS, GATE3 PASS.
#   FAIL: any line containing FAIL. READ THE OUTPUT, NOT THE EXIT CODE — the loop's
#   status is the last iteration's. Gate 1 failure signature: FailedCreatePodSandBox
#   naming cilium-cni. nodeName bypasses the scheduler, so rule out OutOfcpu/
#   OutOfmemory in `describe` before blaming the CNI (that path fails safe).
```

Objects verified live 2026-10-16: nodes `k8s-nuc14-01/02/03`; `svc/echo-server`
:8080 in `default` (pod on 10.69.2.125); 0 netpol and 0 CNP in `default`;
`busybox:1.38.0` on all 3 nodes via `ds/security/falco-log-rotate`; all 246
running non-hostNetwork pods are on `10.69.*`; no `cni-canary-*` pod exists.

**4.9 — The L7 DNS / toFQDNs path works and still ENFORCES, on every node.**

This is the path §1.4's upstream fix is about and the one path no other gate
exercises (§4.8 runs in an unpoliced namespace). The canary runs in `ci-runner`,
where CNP `ci-runner-lockdown` (`endpointSelector: {}`) allows DNS only for
`github.com`, `registry.npmjs.org` and `**.cluster.local`. One positive and one
negative control per node:

```bash
for N in k8s-nuc14-01 k8s-nuc14-02 k8s-nuc14-03; do
  kubectl -n ci-runner delete pod "fqdn-canary-$N" --ignore-not-found
  kubectl -n ci-runner run "fqdn-canary-$N" --restart=Never --image=busybox:1.38.0 \
    --overrides="{\"spec\":{\"nodeName\":\"$N\",\"securityContext\":{\"runAsNonRoot\":true,\"runAsUser\":65534,\"runAsGroup\":65534,\"seccompProfile\":{\"type\":\"RuntimeDefault\"}},\"containers\":[{\"name\":\"fqdn-canary-$N\",\"image\":\"busybox:1.38.0\",\"command\":[\"sh\",\"-c\",\"if nslookup github.com >/dev/null 2>&1; then echo FQDN_ALLOW_OK; else echo FQDN_ALLOW_FAIL; fi; if nslookup example.org >/dev/null 2>&1; then echo FQDN_DENY_FAIL; else echo FQDN_DENY_OK; fi\"],\"securityContext\":{\"allowPrivilegeEscalation\":false,\"capabilities\":{\"drop\":[\"ALL\"]}},\"resources\":{\"requests\":{\"cpu\":\"10m\",\"memory\":\"16Mi\",\"ephemeral-storage\":\"16Mi\"},\"limits\":{\"cpu\":\"100m\",\"memory\":\"32Mi\",\"ephemeral-storage\":\"32Mi\"}}}]}}"
done
for N in k8s-nuc14-01 k8s-nuc14-02 k8s-nuc14-03; do
  POD="fqdn-canary-$N"; echo "===== $N ====="
  kubectl -n ci-runner wait --for=jsonpath='{.status.phase}'=Succeeded "pod/$POD" --timeout=120s || echo "FQDN GATE0 FAIL $N"
  L=$(kubectl -n ci-runner logs "$POD")
  echo "$L" | grep -qx FQDN_ALLOW_OK && echo "ALLOW PASS" || echo "ALLOW FAIL: $L"
  echo "$L" | grep -qx FQDN_DENY_OK  && echo "DENY PASS"  || echo "DENY FAIL: $L"
done
for N in k8s-nuc14-01 k8s-nuc14-02 k8s-nuc14-03; do kubectl -n ci-runner delete pod "fqdn-canary-$N" --ignore-not-found; done
#   PASS (per node): ALLOW PASS and DENY PASS — and the §2n baseline read the same.
#   FAIL: ALLOW FAIL => the DNS proxy is not forwarding allowed names on that node.
#         DENY FAIL  => L7 DNS policy is NOT ENFORCED on that node (a silent
#                       security regression every other gate would miss).
```

*Authoring evidence:* the pod spec passed `kubectl run --dry-run=server` on
2026-10-16 against `ci-runner`'s PSA `restricted` enforcement, its
`ci-runner-quota` ResourceQuota and `ci-runner-defaults` LimitRange. The
behavioural readings (ALLOW_OK/DENY_OK) were **not** measured at authoring time —
creating a pod is a cluster mutation a planner may not make — which is exactly
why §2n runs the identical block as a baseline before the change: the gate is
only trusted in a window where its baseline read PASS/PASS. Both markers are
matched with `grep -qx`, so empty output fails both.

**4.10 — OPERATOR GATE.** Play a stream through Music Assistant and open the Home
Assistant dashboard. Both must work. The check no cron can perform; reason for
`autonomy_override: human-gated`. Do not close the window without it.

**4.11 — Settle.** Wait 15 minutes; confirm no new firing alerts versus the
pre-window set (port-forward Prometheus per CLAUDE.md, filtering
`Watchdog|InfoInhibitor`), and re-read §4.2's `increase()` gate at the end of it.

---

## 5) Rollback

### 5.1 The honest verdict

`rollback_class: git-revert` is honest — nothing here is forward-only — but the
machinery that executes a git revert runs **on the datapath this plan changes**:
all seven Flux controllers are pod-network (`hostNetwork` unset, measured
2026-10-16). What survives a broken CNI: `kube-apiserver` is `hostNetwork` on
192.168.55.11/12/13 and the kubeconfig targets the Talos VIP, so `kubectl` and
`helm` from the Mac keep working; and existing pods keep flowing on in-kernel BPF
state, which buys minutes. **When in doubt use 5.3 first and reconcile git
after.**

### 5.2 Limb A — regression, Flux healthy

```bash
cd /Users/mu/code/cberg-home-nextgen
SHA=$(cat /tmp/cilium-bump-sha.txt)
git revert --no-edit "$SHA"                 # the #372 merge only; the §3.4a OnDelete commit stays until §5.3b ends
git log -1 --format=%s                      # must be YOUR revert subject
git show --stat HEAD                        # exactly helmrelease.yaml + helmfile.yaml
git push origin main
flux reconcile source git flux-system
flux reconcile helmrelease cilium -n kube-system
```
3.4 is REQUIRED, so the DaemonSet is `OnDelete` here and `kubectl rollout status ds/cilium`
would wait forever (nothing restarts a pod by itself). **Primary rollback is §5.3b** (per-node
delete loop with the etcd gate, image check pointed at `2939231d`, then revert the OnDelete
commit per 3.4c). Only if the OnDelete commit has already been reverted (RollingUpdate back) may
`kubectl -n kube-system rollout status ds/cilium --timeout=10m` be used - and then it rolls up to
two nodes at once, so prefer §5.3b regardless.

Confirm with §4.1 (expect 1.20.2 / `sha256:2939231d…` agent,
`sha256:64d87983…` operator), §4.3, §4.4, §4.5, §4.9.

### 5.3 Limb B — break-glass: datapath broken, Flux cannot act

```bash
cd /Users/mu/code/cberg-home-nextgen        # REQUIRED: helm is a mise shim pinned here
flux suspend helmrelease cilium -n kube-system     # else helm-controller re-applies 1.20.4
helm history cilium -n kube-system
REV=$(helm history cilium -n kube-system -o json | .venv/bin/python3 -c "
import sys, json
h = json.load(sys.stdin)
r = [x for x in h if x['chart'] == 'cilium-1.20.2']
print(r[-1]['revision'] if r else 'NONE')
")
echo "rollback target revision: $REV"       # measured 2026-10-16: 14
test "$REV" != NONE || { echo 'STOP — no cilium-1.20.2 revision in helm history'; exit 1; }
helm rollback cilium "$REV" -n kube-system --wait --timeout 10m
kubectl -n kube-system rollout status ds/cilium --timeout=10m
# prove the datapath is back: §4.3, §4.4 (diff against /tmp/cilium-lb-before.txt), §4.5
git revert --no-edit "$(cat /tmp/cilium-bump-sha.txt)"
git push origin main
flux resume helmrelease cilium -n kube-system     # own line: resume even if the push failed
```

Leaving the HelmRelease suspended is itself an incident — an unreconciled CNI
drifts silently. If you must stop before `flux resume`, record it in the window
close-out.

### 5.3b Rollback DURING the gated roll (OnDelete still on)

OnDelete means a `helm rollback`/revert changes the template but restarts nothing:
the already-upgraded nodes stay on 1.20.4 until you delete their agent pod, one node at
a time, with `/tmp/cilium-etcd-gate.sh` before and after each (same loop as 3.4b with the
image check pointed at `2939231d`). Un-upgraded nodes need nothing. Order: revert the
#372 merge commit (and leave the OnDelete commit until the end), push, wait HR Ready,
loop, then revert the OnDelete commit (3.4c). **Limb B caveat:** `helm rollback` to
revision 14 also restores `RollingUpdate maxUnavailable: 2` (rev 14 never had OnDelete),
so it restarts every 1.20.4 agent up to two at a time. Use it only for a datapath that is
already broken (nothing left to protect); for a mere regression use the git + node-by-node
path above.

### 5.3c What still works when the pod network is degraded (verified 2026-10-22)

- `kubectl`/`helm` from the Mac: kubeconfig targets the Talos VIP and kube-apiserver is
  hostNetwork on .11/.12/.13 - no pod network or CoreDNS involved.
- `talosctl` (etcd status, `image pull`, service restart, reboot as a last resort) talks to
  the node IPs directly - the etcd gate and the image pre-pull never depend on the CNI.
- Pod-network pieces that do NOT work: all 7 Flux controllers (so a pushed git revert
  is NOT applied until the datapath is back - use `helm rollback`, 5.3), CoreDNS (pods
  lose cluster DNS, and the FQDN L7-DNS proxy for ci-runner/arc namespaces), Prometheus
  (so 4.2 reads empty - judge by `cilium-dbg`, not Grafana), the AdGuard/k8s-gateway VIPs.
- The 1.20.4 images are pre-pulled to the nodes (2p), so a rollback/restart does not wait on
  the registry; the 1.20.2 images are still in each node's containerd cache (listed
  2026-10-22 on .11).

### 5.4 Cost

Rollback is another full agent roll with the same per-node blips (and, rolling
from 1.20.4 back to 1.20.2, the old shutdown-path DNS bug cannot fire because the
agent shutting down is 1.20.4). Pull it for a real regression — crash-loop, a dark
VIP, a failed §4 gate whose baseline passed — never for a transient blip seen
during the roll.

---

## 6) Interference notes

- **EXECUTION JUDGMENT (2026-10-22): NEEDS-OPERATOR (attended), not unattended.**
  The gated roll is stop-safe (any failed gate halts with the cluster mixed
  1.20.2/1.20.4 and stable; OnDelete guarantees nothing else restarts), and the etcd gate
  + pre-pull + `talosctl` access are CNI-independent. It is still not safe to run with
  the operator away because (a) no watchdog can *undo* a degraded datapath without
  judgment: the revert machinery (Flux) is itself on the pod network, so recovery is a
  manual `helm rollback` (5.3) from the Mac; (b) a failure mode that wedges the Mac->VIP
  path would remove the only control channel; (c) the sibling Cilium policy
  (`runbooks/auto-update-policy.yaml` `*cilium*`) requires an attended slot + GO.
  `autonomy_override: human-gated` stays. Recommended: on-demand NOW run or an empty
  sat/sun-attended slot, operator reachable; never `nightly`.

- **SOLO + ATTENDED, both hard.** `exclusive: true` keeps every other plan out of
  the slot in both directions; `autonomy_override: human-gated` keeps it out of
  `nightly`. `conflicts_with` names the plans with a specific interaction (§
  frontmatter). **Reciprocity owed:** none of those plans lists `cilium-1.20.4`
  (it did not exist). `exclusive` makes that non-blocking for scheduling, but the
  `talos-linux-1.14.4` owner should add the back-reference for the README §4
  convention (done 2026-10-23); no kube-prometheus-stack plan exists to owe one.
- **Slot.** Recommendation: an operator-triggered **on-demand NOW run** (attended
  by construction, 480-min ceiling, no reboot) — exactly how cilium-1.20.2 ran.
  A `sat-attended` slot also fits (60 ≤ 70 usable) but only an EMPTY one:
  `sat-attended:2026-10-17` holds `coredns-1.48.2` (a listed conflict),
  `2026-10-24` holds `paperless-db-13.0.2`, `2026-10-31` holds
  `penpot-chart-1.10.0`. Do **not** take `sun-attended:2026-11-01`
  (`talos-linux-1.14.4`, exclusive, rolls the same CNI). Scheduled slot:
  `sun-attended:2026-10-25`, solo and exclusive.
- **Blip profile.** Established flows survive; new-flow setup, policy updates and
  L2 lease renewals pause for seconds per node — **two nodes at once** at
  `maxUnavailable: 2` unless §3.4 is taken (it is REQUIRED as of 2026-10-22: strictly one node at a time). VIPs keep their addresses (pinned via
  `lbipam.cilium.io/ips`) but may move announcing node once (one gratuitous-ARP
  re-learn). New this time: CI pods under the four toFQDNs CNPs may lose DNS for
  the restart duration on their node (§1.4) — an in-flight CI job may fail.
- **Retarget note (2026-10-24).** This plan was retargeted from 1.20.3 to 1.20.4 the day
  before its slot. All reviewed fixes are kept (3.4a pre-push gate, 3.4b script, 3.2 digest
  gate, 5.3b). `review` was reset to null: the new reviewer must re-check §1.3's xDS-mode
  claim and the digests, not just the version strings. Other plans' `conflicts_with` entries
  were renamed `cilium-1.20.3` -> `cilium-1.20.4` in the same commit.
- **Step 0 ordering.** Take every §2 baseline after Step 0 settles.
- **Monitoring is the instrument.** §4.2 reads Prometheus over the datapath being
  changed; a same-night kube-prometheus-stack / otel / edot change would make a
  §4.2 failure un-attributable — hence those entries in `conflicts_with`.
- **Upstream pre-flight DaemonSet deliberately not used** (as in 1.20.2): it would
  be a second Helm release outside Flux. Its value — pre-pulling the image — is
  the `maxUnavailable: 2` pull-stall risk, which §3.4 mitigates GitOps-natively.
