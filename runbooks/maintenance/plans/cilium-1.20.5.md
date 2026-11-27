---
plan_id: cilium-1.20.5
component: cilium
pr: null                              # NO Renovate PR exists (measured 2026-11-18: `gh pr list --search cilium`
                                      # shows only the merged #372; no remote branch renovate/cilium-*). The held
                                      # update comes from the version snapshot (version-check-current.md row
                                      # "cilium kube-system 1.20.4 -> 1.20.5 PATCH"). §2c handles a PR that
                                      # appears before the window; otherwise §3.2 is a direct GitOps edit.
kind: chart
current: "1.20.4"                     # LIVE, verified 2026-11-18: HR Ready, history[0] chartVersion 1.20.4,
                                      # helm revision 26 'deployed'; ds/cilium + deploy/cilium-operator on the
                                      # v1.20.4 digests (20fe92e4 / 7a7a3489); count by (version)(cilium_version)
                                      # = {1.20.4: 3}.
target: "1.20.5"                      # helm.cilium.io: version + appVersion 1.20.5 (helm show chart, 2026-11-18);
                                      # GitHub release v1.20.5 published 2026-11-17T09:53:42Z, non-prerelease.
update_type: patch                    # fifth patch on the 1.20 line (run since 2026-08-03, 97989c9b).
risk: medium                          # Measured delta is small (§1.3: two digests + one operator toleration),
                                      # BUT 1.20.5 renames every L2-announcement Lease (§1.4) — the first patch
                                      # on this line with a mixed-version behaviour on the LAN VIP surface.
                                      # Probability low; CONSEQUENCE total (the CNI). Consequence is handled by
                                      # exclusive + human-gated + an attended slot, not by inflating this.
est_duration_min: 90                  # cilium-1.20.4 booked 85 for the same gated one-node-at-a-time roll and
                                      # ran inside it (2026-10-25). +5 for the §4.4b lease-rename assertion and
                                      # its 2-min GC wait. Does NOT fit sat-attended (90 - 20 reserve = 70):
                                      # needs sun-attended (budget 180) or an on-demand NOW run (480).
needs_reboot: false                   # HONEST: DaemonSet + operator Deployment roll only. No drain, no Talos
                                      # change, zero files under kubernetes/bootstrap/talos/.
touches:
  namespaces:
    - kube-system                     # helmrelease/cilium, ds/cilium, deploy/cilium-operator, l2announce leases
    - "ALL (cluster-wide)"            # every pod rides this datapath; agent restart is per node
    - ci-runner                       # CNPs ci-runner-lockdown, the-ninth-banner-runners-egress (L7 DNS + toFQDNs)
    - arc-system                      # CNP arc-system-lockdown
    - arc-build                       # CNPs arc-build-egress, absenty-build-egress, rainbow-rescue-build-egress
    - default                         # §4.8 CNI-ADD canaries (created + deleted)
    - monitoring                      # CNP edot-collector-ingress (L3/L4 ingress, new 2026-11-25) + LB VIP .19 (§4.7c)
  resources:
    - helmrelease/cilium              # kube-system — the only LIVE pin
    - daemonset/cilium                # 3 nodes; rolled ONE node at a time via temporary updateStrategy OnDelete (§3.4)
    - deployment/cilium-operator      # 1 replica; brief operator gap; gains an etcd toleration (§1.3)
    - configmap/cilium-config         # renders IDENTICAL at 1.20.5 (diff of helm template: no change)
    - kubernetes/apps/kube-system/cilium/app/helmrelease.yaml      # version pin + temporary upgrade.disableWait
    - kubernetes/apps/kube-system/cilium/app/helm-values.yaml      # temporary updateStrategy OnDelete
    - kubernetes/bootstrap/apps/helmfile.yaml                      # bootstrap/DR-only pin, inert at runtime
    - "15 LoadBalancer Services (VLAN 55 VIPs) announced via CiliumL2AnnouncementPolicy l2-policy"
                                      # 15 since 2026-11-25: +monitoring/edot-collector-syslog .19 (e6b6c1dfe)
    - "15 cilium-l2announce-* Leases in kube-system — ALL RENAMED by 1.20.5 (<ns>-<svc> -> <ns>.<svc>, §1.4)"
    - "7 CiliumNetworkPolicies (6 egress L7 DNS + toFQDNs; 1 L3/L4 ingress: monitoring/edot-collector-ingress)"
  shared:
    - cilium                          # the CNI itself
    - cni                             # pod networking, kube-proxy replacement, policy enforcement
    - cni/cilium
    - gateway/envoy                   # Cilium LB-IPAM + L2 supplies 192.168.55.103 (envoy-internal) and .104 (envoy-external)
    - public-edge                     # envoy-external is the internet-facing gateway
    - coredns                         # in-cluster DNS rides the pod datapath; the FQDN proxy forwards to it
    - dns                             # AdGuard VIP .5 and k8s-gateway VIP .101 are Cilium L2 LB IPs
    - etcd                            # agent restarts on the 3 control-plane nodes; §2o/§3.4b gate on etcd
    - flux                            # all Flux controllers are pod-network: the rollback machinery is in the blast radius
    - monitoring                      # §4.2 reads Prometheus over this datapath
    - ci-runner                       # ARC listeners/runners sit behind toFQDNs policies
    - home-automation-pinned          # HA .24, MA .29, mosquitto .15, iobroker .25 reached by L2 VIP
    - "LAN service access (VLAN 55)"
depends_on: []
conflicts_with:                       # Belt-and-braces: `exclusive: true` already keeps every plan out of this
                                      # slot in BOTH directions. These name a specific interaction; each was
                                      # re-read from its frontmatter on 2026-11-18. Reciprocity owed (§6).
  - talos-linux-1.14.6                # node roll, exclusive, shared cni/cilium + etcd: same failure domain
  - talos-power-tuning-ab             # Talos machine-config on all nodes; exclusive
  - etcd-timeouts-5000-500            # control plane; §3.4b is etcd-gated and §5.3 needs a healthy apiserver
  - flux-oci-chart-sources            # cni-adjacent; changes chart sourcing incl. this HR (sun-attended:2026-12-13)
  - flux-reconciler-impersonation     # Flux is the rollback machinery (§5); exclusive on its own side
  - kube-prometheus-stack-93.3.0      # §4.2's instrument (README rule: same-night KPS bump must be listed)
  - otel-operator-0.27.2              # monitoring collectors; precedent declared otel <-> cilium both ways
  - envoy-gateway-1.10.0              # §4.5 gates on the Envoy VIPs; same-night Envoy change = un-attributable
  - envoy-proxy-config-distroless-v1.40.2
  - coredns-1.50.5                    # DNS rides this datapath; §4.9 FQDN canary resolves through coredns
  - otbr-0.4.0                        # host-netfilter on k8s-nuc14-03, one of the rolled nodes
  - longhorn-1.13.0                   # storage engine, exclusive (sun-attended:2026-11-22)
  - multus-macvlan-foundation         # its own frontmatter: "do NOT co-schedule with any Cilium/Talos plan"
exclusive: true                       # README names a CNI bump as the canonical "nothing else in flight" case
security_ref: F-7cd37e1f              # agent-image record, accepted under [AR-029] "already newest" on
                                      # v1.20.4; that premise lapses now v1.20.5 exists. Detail stays in DB.
capability_change: false              # FACT: no value, flag or user-visible behaviour changes. Rendered delta is
                                      # two image digests + an operator toleration matching no taint on our nodes
                                      # (§1.3). The Lease rename is an internal coordination-object name; the
                                      # toServices+toPorts policy fix cannot apply (no CNP uses toServices, §1.4).
rollback_class: git-revert            # nothing forward-only: no schema/data migration, CRDs unchanged, renamed
                                      # Leases are recreated under the old names by 1.20.4 agents. Read §5 first —
                                      # Flux runs on this datapath.
autonomy_override: human-gated        # LOAD-BEARING. Without it capability_change:false + git-revert + medium
                                      # could derive AUTO-NIGHT. The *cilium* deny rule requires an attended slot
                                      # + operator GO, and §4.10 is an operator check no cron can perform.
finding_refs: [F-7cd37e1f]            # `policy-cli.py finding list --grep cilium` (DSN up), 2026-11-18:
                                      #   F-7cd37e1f security — quay.io/cilium/cilium:v1.20.4 image, [AR-029]
                                      #              "already newest"; this plan moves the digest (remedy).
                                      # Context, NOT claimed: F-33873912 / F-6938f5a1 (etcd leader churn — gates
                                      # this plan, §2o), F-f835aded (SOP gap, ipBlock NetworkPolicy chart bumps).
                                      # No version-section finding for 1.20.5 existed yet; if the next sweep files
                                      # one, add its id here.
premises:                             # Every run: checked against plan-premises.py's allowlist; expected values
                                      # MEASURED live 2026-11-18 unless the line says otherwise.
  - id: hr-ready
    why: "An unready HelmRelease cannot be cleanly upgraded; §4.1 asserts this field."
    run: kubectl get hr -n kube-system cilium -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: live-chart-is-1.20.4
    why: "`current:` claims 1.20.4. If the cluster already moved, this plan is stale."
    run: kubectl get hr -n kube-system cilium -o jsonpath='{.status.history[0].chartVersion}'
    expect_exact: "1.20.4"
  - id: live-agent-image-is-1.20.4
    why: "§3.4b/§4.1 diff the digest, so the OLD digest must be what is live."
    run: kubectl get ds -n kube-system cilium -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_contains: "v1.20.4@sha256:20fe92e4"
  - id: live-operator-image-is-1.20.4
    why: "Second of the two digests §1.3 says this plan moves."
    run: kubectl get deploy -n kube-system cilium-operator -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_contains: "operator-generic:v1.20.4@sha256:7a7a3489"
  - id: agents-3-of-3-ready
    why: "Rolling a CNI already down a node turns a one-node roll into a two-node outage."
    run: kubectl get ds -n kube-system cilium -o jsonpath='{.status.desiredNumberScheduled} {.status.numberReady}'
    expect_exact: "3 3"
  - id: etcd-leader-changes-24h-below-6
    why: "etcd base-rate rule (docs/sops/etcd.md: >=6 leader changes/24h = already unstable = NO-GO). Reads the RAW worst-member 24h increase and matches a value below 6 (0..5.999). Re-planned 2026-11-27: the old form (`< bool 6` piped to grep -c for value 1) printed '0' for BOTH 'churning' and 'not scraped', so the failure line said nothing. Now the got-value IS the measurement. FAILS on: >=6 (e.g. '6.0', '11.0038'), an empty result list (etcd not scraped: no value field), an API/proxy error. MEASURED 2026-11-27: 11.0 (per member 9.0/11.0/10.0) -> this premise FAILS TODAY, open findings F-33873912/F-6938f5a1. That is the gate working: not runnable until churn subsides. Never relax it."
    run: kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=max(increase(etcd_server_leader_changes_seen_total%5B24h%5D))'
    expect_matches: "\"value\":\\[[0-9.]+,\"[0-5](\\.[0-9]+)?\"\\]"
  - id: updatestrategy-is-rollingupdate
    why: "§3.4a flips the DaemonSet to OnDelete; if it already is OnDelete a previous attempt stopped mid-roll."
    run: kubectl get ds -n kube-system cilium -o jsonpath='{.spec.updateStrategy.type}'
    expect_exact: "RollingUpdate"
  - id: hr-wait-not-disabled
    why: "§3.4a adds upgrade.disableWait temporarily; present already = a previous attempt did not finish §3.4c."
    run: kubectl get hr -n kube-system cilium -o jsonpath='dw=[{.spec.upgrade.disableWait}]'
    expect_exact: "dw=[]"
  - id: chart-1.20.5-is-published
    why: "Never bump to a version that is not there. A stale local repo cache fails this CLOSED; fix with `helm repo update cilium`, never by relaxing the premise."
    run: helm show chart cilium/cilium --version 1.20.5 | grep '^version'
    expect_exact: "version: 1.20.5"
  - id: rollback-revision-present
    why: "§5.3 rolls back to the 1.20.4 revision recorded in §2q (measured: 26 deployed, 25 superseded)."
    run: helm history cilium -n kube-system | grep -c 'cilium-1.20.4'
    expect_matches: "^[1-9]"
  - id: lb-services-are-15
    why: "Staleness detector for the LB/VIP blast radius. 15 at re-plan 2026-11-27 (14 on 2026-11-18; +monitoring/edot-collector-syslog .19 created 2026-11-25). §3.4b/§4.4b derive their expected count from the §2e baseline FILE, so a future add only needs this pin re-measured, but a moved count still means re-read §1.4 for the new Service (eTP, policy) before running."
    run: kubectl get svc -A --no-headers | grep -c LoadBalancer
    expect_exact: "15"
  - id: l2-leases-old-format-15
    why: "Baseline for §4.4b: one old-format Lease (cilium-l2announce-<ns>-<svc>) per LB Service = 15. Must equal lb-services-are-15; a mismatch means a VIP has no announcer before we start."
    run: kubectl get leases -n kube-system -o custom-columns=N:.metadata.name --no-headers | grep -c '^cilium-l2announce-'
    expect_exact: "15"
  - id: l2-leases-new-format-0
    why: "Baseline for §4.4b: 0 Leases in the 1.20.5 format (<ns>.<svc>). If non-zero, a 1.20.5 agent already ran here."
    run: kubectl get leases -n kube-system -o custom-columns=N:.metadata.name --no-headers | grep -c 'cilium-l2announce-[a-z0-9-]*\.'
    expect_exact: "0"
  - id: all-lb-services-etp-cluster
    why: "§1.4's dual-announcer argument (mixed 1.20.4/1.20.5 window is functional) holds only while EVERY LB Service is externalTrafficPolicy Cluster. A Local service would black-hole on the non-backend announcer."
    run: kubectl get svc -A -o custom-columns=T:.spec.type,E:.spec.externalTrafficPolicy --no-headers | grep LoadBalancer | grep -c -v Cluster
    expect_exact: "0"
  - id: lbipam-pool-not-conflicted
    why: "A pool already in conflict re-allocates unpredictably on operator restart; §4.4 would misread it."
    run: kubectl get ciliumloadbalancerippool pool -o jsonpath='{.status.conditions[?(@.type=="cilium.io/PoolConflict")].status}'
    expect_exact: "False"
  - id: cnp-count-is-7
    why: "§1.4's applicability analysis is written against exactly these 7 CNPs: 6 egress L7-DNS/toFQDNs (ci-runner x2, arc-system, arc-build x3) + monitoring/edot-collector-ingress (L3/L4 ingress only, added 2026-11-25 by 52ec990dd). Was 6 on 2026-11-18, 4 at the 1.20.4 plan."
    run: kubectl get cnp -A --no-headers | wc -l
    expect_matches: "^ *7$"
  - id: cnps-all-valid
    why: "Baseline for §4.7b: all CNPs VALID=True before, so a post-upgrade False is attributable."
    run: kubectl get cnp -A --no-headers | awk '$4!="True"' | wc -l
    expect_matches: "^ *0$"
  - id: no-cnp-uses-toservices
    why: "1.20.5 tightens egress rules combining toServices with toPorts. Vacuous only while no CNP uses toServices (measured 0)."
    run: kubectl get cnp -A -o json | grep -c toServices
    expect_exact: "0"
  - id: k8s-netpol-count-is-6
    why: "Baseline for §4.7a (enforcement count derives from 6 NetworkPolicies + 7 CNPs). 6 since 2026-11-23: +ai/camofox-browser (ingress podSelector/namespaceSelector only, no ipBlock)."
    run: kubectl get netpol -A --no-headers | wc -l
    expect_matches: "^ *6$"
  - id: no-cilium-envoyconfig-crd
    why: "1.20.5 bumps the embedded Envoy to 1.39 and carries gateway-api fixes; irrelevant only while Cilium's Envoy-config feature is absent."
    run: kubectl get crd -o name | awk '/envoyconfigs.cilium.io/' | wc -l
    expect_matches: "^ *0$"
  - id: cilium-gateway-api-off
    why: "Cilium Gateway API fixes in 1.20.5 are irrelevant only while enable-gateway-api is ABSENT from cilium-config. Wrapper avoids empty output; a PRESENT key prints gw=[false|true]."
    run: kubectl get cm -n kube-system cilium-config -o jsonpath='gw=[{.data.enable-gateway-api}]'
    expect_exact: "gw=[]"
  - id: repo-pin-still-1.20.4
    why: "§3.2's sed anchors on `version: 1.20.4`; if HEAD already says 1.20.5 the plan is executed or stale."
    run: git show HEAD:kubernetes/apps/kube-system/cilium/app/helmrelease.yaml | grep '^      version'
    expect_exact: "version: 1.20.4"
  - id: bootstrap-pin-still-1.20.4
    why: "§3.2's regex anchors on it; exactly ONE occurrence (measured)."
    run: git show HEAD:kubernetes/bootstrap/apps/helmfile.yaml | grep -c 'version. 1.20.4'
    expect_exact: "1"
  - id: cilium-worktree-clean
    why: "Shared checkout: an uncommitted edit under the cilium dir would ride into a path-scoped commit."
    run: git status --porcelain kubernetes/apps/kube-system/cilium kubernetes/bootstrap/apps/helmfile.yaml | wc -l
    expect_matches: "^ *0$"
  - id: no-kustomization-in-flight
    why: "Nothing else may be reconciling. Column 5 is READY."
    run: flux get kustomizations -A | tail -n +2 | awk '$5!="True"' | wc -l
    expect_matches: "^ *0$"
  - id: no-helmrelease-in-flight
    why: "helm-controller must be idle before it is asked to upgrade the CNI."
    run: flux get helmreleases -A | tail -n +2 | awk '$5!="True"' | wc -l
    expect_matches: "^ *0$"
  - id: nodes-on-expected-kubelet
    why: "No node operation mid-flight. If a Talos/k8s roll moved this, re-measure, do not run."
    run: kubectl get nodes -o jsonpath='{.items[*].status.nodeInfo.kubeletVersion}'
    expect_exact: "v1.36.0 v1.36.0 v1.36.0"
  - id: canary-image-cached-on-all-3-nodes
    why: "§4.8/§4.9 canaries use busybox:1.38.0 because ds/security/falco-log-rotate runs it on all 3 nodes — a CNI failure is never misread as a slow pull."
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
    why: "§4.9 relies on ci-runner-lockdown allowing DNS for github.com and denying anything else."
    run: kubectl get cnp -n ci-runner ci-runner-lockdown -o jsonpath='{.spec.egress[0].toPorts[0].rules.dns[0].matchName}'
    expect_exact: "github.com"
status: draft
window: null                          # window agent assigns. Needs sun-attended (180 budget) or an on-demand
                                      # NOW run — NOT sat-attended (70 budget < 90). Free Sunday at authoring:
                                      # 2026-12-06 (11-22 longhorn, 11-29 redis-fleet, 12-13 flux-oci, 12-20
                                      # postgres-digest). Never nightly.
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/auto-update.md
  - docs/sops/maintenance-windows.md
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/etcd.md
generated: "2026-11-18"               # derived from the executed+retired cilium-1.20.4 plan
                                      # (`git show 3505ff896^:runbooks/maintenance/plans/cilium-1.20.4.md`), with
                                      # its retire-commit correction (disableWait) baked in and every number
                                      # re-measured live. No older open cilium plan existed to supersede.
replanned: "2026-11-27"                # in place after plan-refine premise-fail (lb 14->15, leases 14->15,
                                      # etcd premise re-expressed). Also found and fixed: cnp 6->7, netpol 5->6.
                                      # Upstream re-checked 2026-11-27: v1.20.5 is still the newest 1.20.x
                                      # (gh release list + helm search); no retarget.
---

# cilium chart 1.20.4 → 1.20.5 (CNI datapath — plan lane by standing rule)

## 1) Summary & why held

### 1.1 What this is

Fifth bugfix patch on the Cilium 1.20 line. The previous three patches each went
through this plan shape and executed cleanly: `cilium-1.20.1` (`addfd9aa`),
`cilium-1.20.2` (`80395710`, 2026-09-21), `cilium-1.20.4` (`187448df`, attended NOW
run 2026-10-25, gated roll `.11, .13, .12`, every §4 gate passed; retire commit
`3505ff89`). This plan is derived from the executed 1.20.4 plan. It differs in three
ways: it carries that run's correction (`upgrade.disableWait`, §3.4a), it handles the
**L2 Lease rename** that 1.20.5 introduces (§1.4, §4.4b), and its rollback pins an
explicit helm revision rather than "the last 1.20.4 one" (§2q, §5.3).

### 1.2 Why held — consequence, and the hold is correct

`runbooks/auto-update-policy.yaml` rule `*cilium*`:

> "CNI datapath — never an unattended bump. The hold is about CONSEQUENCE, not a
> specific release: a bad cilium roll takes the cluster network with it, and every
> Flux controller that would revert it sits inside the failure domain. [...]
> Requires an attended slot, a plan that exercises a FRESH CNI ADD [...], and an
> operator GO."

Checked against the cluster (authoring rule 8): still accurate. Nothing in 1.20.5 is
marked breaking or action-required. Mapping: attended slot + GO →
`autonomy_override: human-gated` + §4.10; fresh CNI ADD → §4.8 (one canary per node).

### 1.3 What actually changes — measured, not assumed

Rendered both charts against **our** `app/helm-values.yaml` on 2026-11-18
(1733 → 1735 lines):

```
$ helm template cilium cilium/cilium --version 1.20.{4,5} -n kube-system \
    -f kubernetes/apps/kube-system/cilium/app/helm-values.yaml
# Non-label delta, in full (agent image repeats across the DaemonSet's init containers: 7x, same digest):
-  image: "quay.io/cilium/cilium:v1.20.4@sha256:20fe92e4c86641233a450098c158d2d29085f3419931ab6bf681d2485dedf16e"
+  image: "quay.io/cilium/cilium:v1.20.5@sha256:aa72499f075ad729947ea91b026218aceba24f1a8e4534bf36b8368c7c561526"
-  image: "quay.io/cilium/operator-generic:v1.20.4@sha256:7a7a3489dc66ad67e420d285c8a8d2e169b0957ad15e120f593d27081bf38d82"
+  image: "quay.io/cilium/operator-generic:v1.20.5@sha256:c6e7de6665aa9701db86c4fe46828a75a0d167afe084a9ffb5bce34b2c4fa8c4"
+  - key: node-role.kubernetes.io/etcd        # cilium-operator tolerations
+    operator: Exists
```

plus the `helm.sh/chart` label and the config checksum annotation. `cm/cilium-config`
renders **identical**. The digests match the v1.20.5 release's "Docker Manifests"
section. The new operator toleration is upstream "helm: Add
node-role.kubernetes.io/etcd to default cilium-operator tolerations" (#49371); our
three nodes carry **no taints at all** (measured), so it changes nothing about
scheduling. The chart has no `crds/` dir (the operator manages CRDs).

### 1.4 Upstream content, read against THIS cluster

Primary source: GitHub release `v1.20.5` (`gh release view v1.20.5 -R cilium/cilium`).
One "Minor change" (new LB ID-allocator metrics), ~45 bugfixes, dependency security
bumps. No breaking or upgrade notes.

**The one change that behaves differently during a rolling upgrade — the L2 Lease
rename.** Release note: *"l2announcer: use unambiguous separator in Lease name to
avoid collision"* (upstream #48138). Read in the source (`pkg/l2announcer/l2announcer.go`,
`v1.20.4` vs `v1.20.5`, fetched via `gh api`):

```
-  Name: fmt.Sprintf("%s-%s-%s", leasePrefix, svc.Name.Namespace(), svc.Name.Name()),
+  Name: fmt.Sprintf("%s-%s.%s", leasePrefix, svc.Name.Namespace(), svc.Name.Name()),
```

So every per-Service leader-election Lease changes name, e.g.
`cilium-l2announce-network-envoy-internal` → `cilium-l2announce-network.envoy-internal`.
Consequences, derived from the same file:

- **Mixed-version window = two announcers per VIP.** 1.20.4 agents contend for the
  old-named Lease, 1.20.5 agents for the new one. They cannot see each other, so while
  the roll is part-way, each VIP is answered by one 1.20.4 node AND one 1.20.5 node
  (after the first node rolls, that node holds all 15 new Leases). The LAN learns
  whichever ARP reply it saw last. **This works here** because all 15 LB Services are
  `externalTrafficPolicy: Cluster` (premise `all-lb-services-etp-cluster`), KPR runs on
  every node and Maglev gives every node the same backend choice, so either announcer
  forwards correctly. Expect: possible one-off connection resets on long-lived TCP
  flows (mosquitto, HA websockets) when a client's ARP entry flips, and possibly a
  UniFi duplicate-IP event. Interruption, not data loss. It also argues for not
  stretching the mixed window: §3.4b's per-node gates take ~8 min/node (~25 min total),
  and that is accepted. Do not pause mid-roll for unrelated work.
- **End state cleans itself up.** The agent's leader election uses `ReleaseOnCancel:
  true`, so when the last 1.20.4 agent stops, it empties `holderIdentity` on the
  old-named Leases, and `leaseGC` (a 1-minute timer in every 1.20.5 agent) deletes
  every `cilium-l2announce*` Lease with an empty holder. Expected end state: 15 new-format
  Leases, 0 old-format. §4.4b asserts this. If an old Lease survives with a holder
  still set (an agent killed without a clean shutdown), it is inert. Nothing reads it.
  Delete it by hand only after the full roll (§4.4b).
- **Nothing in this repo reads Lease names** (`grep -rn l2announce kubernetes/ runbooks/*.py
  runbooks/*.sh runbooks/lib` matches only the values key and the policy schema
  comment). The retired 1.20.4 plan's `grep -c cilium-l2announce` count still works
  after the rename (the prefix is unchanged), but it would count BOTH formats during
  the mixed window, which is why §4.4b checks each format separately.

Fixes that land on our configuration (`kubeProxyReplacement`, DSR + Maglev, native
routing, `bpf.masquerade`, `l2announcements`, L7 DNS proxy for 6 toFQDNs CNPs):

- *"Fixed an issue where DNS egress policy could deny requests after a destination's
  security identity changed. DNS proxy rules now refresh alongside incremental policy
  updates."* and *"Fix agent bootstrap to order endpoint regeneration after DNS proxy
  initialization to prevent proxy port race."* These are the FQDN path the CI
  namespaces use. §4.9 exercises it.
- *"Fix restored endpoints getting only policy rules that select all endpoints."*
  This hits the restart path this roll exercises. §4.7 counts enforcement after.
  Since 2026-11-25 it has a concrete target: `monitoring/edot-collector-ingress` is the
  first INGRESS CNP here, selecting exactly one endpoint (the edot-collector pod). A restored
  endpoint that came back with only select-all rules would lose that ingress allow-list;
  §4.7c asserts the pod's endpoint still shows ingress enforcement `Enabled`.
- *"l2announcer: Fix L2 announcements of new IPs stopping until the agent restarts
  after many selected services are removed at once"*; *"Fix nodes sending out ARP
  probes for their own IPs when L2 neighbor discovery is enabled"*.
- *"Fix unintended socket termination when a backend is removed from one service but
  remains alive and in use by another"*; *"Fix connections to a pod timing out when the
  client reuses the source port of a closed NodePort or HostPort connection"*;
  *"Fix incorrect checksums in ICMP error replies"*; *"fix incorrect CiliumEndpoint
  deletion during endpoint replacement"*; operator now exits when its controller-runtime
  manager fails (instead of running with controllers stopped).

Behaviour changes that **could** have mattered, each checked live, all **vacuous here**
(each is also a premise):

| 1.20.5 change | Live state | Verdict |
|---|---|---|
| Egress rules combining `toServices` + `toPorts` no longer allow any destination when the Service is missing/selector-less | 0 CNPs use `toServices` (premise `no-cnp-uses-toservices`) | vacuous |
| L2 Lease rename (above) | 15 Leases, all old format; all LB svcs eTP=Cluster (incl. new edot-collector-syslog .19) | handled: §3.4b, §4.4b |
| Gateway API route-ordering / GRPCRoute fixes; embedded Envoy bumped to 1.39.x | `enable-gateway-api` absent; no `envoyconfigs.cilium.io` CRD; `envoy.enabled: false` | vacuous |
| IPAM: operator waits 30 min (was 3) before releasing IPs; multi-pool / ENI fixes | `ipam.mode: kubernetes` (node podCIDRs from k8s, not operator pools) | vacuous |
| Operator default toleration `node-role.kubernetes.io/etcd` | nodes carry no taints | vacuous (rendered, harmless) |
| IPsec / WireGuard / strict-egress-encryption / Hubble / clustermesh fixes | none enabled (`hubble.enabled: false`, no encryption, no clustermesh) | vacuous |
| Bandwidth-manager drop fix | bandwidthManager not enabled | vacuous |

### 1.5 Numbers that moved since the 1.20.4 plan (do not copy from it)

| Fact | 1.20.4 plan (2026-10-24) | Live 2026-11-18 | Live 2026-11-27 (re-plan) |
|---|---|---|---|
| LoadBalancer Services / L2 Leases | 13 / 13 | 14 / 14 (added: home-automation/dashcast .32) | **15 / 15** (added: monitoring/edot-collector-syslog .19, UDP 5173-5175, eTP=Cluster, created 2026-11-25) |
| CiliumNetworkPolicies | 4 | 6 (+absenty-build-egress, +rainbow-rescue-build-egress in arc-build) | **7** (+monitoring/edot-collector-ingress, L3/L4 ingress, `fromEntities` + two `fromCIDR` /32s) |
| k8s NetworkPolicies | 5 | 5 | **6** (+ai/camofox-browser, ingress podSelector only) |
| helm revision holding the current chart | 14 (1.20.2) | **26 (1.20.4, deployed)**; 25 is also chart 1.20.4 but carries OnDelete — see §2q | unchanged (premise `rollback-revision-present` passes) |
| `envoy-xds-mode` in cilium-config | `ads` | absent (removed by the 1.20.4 chart, as planned) | absent |
| etcd leader changes / 24h (worst member) | 1 | 6.0 — premise FAILS | **11.0 (9/11/10 per member) — premise FAILS** |

What the new LB Service changes: one more VIP rides the dual-announcer window (UDP syslog
from node Talos, the UDM and the UNAS — fire-and-forget, so a mid-roll ARP flip loses at
most a few log lines, no data store is touched) and one more Lease is renamed. It is
eTP=Cluster like the rest, so §1.4's dual-announcer argument holds unchanged. Blast radius
grows by one log-ingest path, not by a new class of failure. The new ingress CNP is the
more interesting addition (see §1.4 "restored endpoints" and §4.7c).

### 1.6 Security

The agent-image record `F-7cd37e1f` is accepted under `[AR-029]` "already newest" on
v1.20.4. With v1.20.5 published that premise no longer holds, and this plan moves the
digest. The 1.20.5 notes list several `[security]` Go-module bumps. Which of them clear
which scanner rows is assessed on the finding record, not here.

---

## 2) Pre-checks

Run from `/Users/mu/code/cberg-home-nextgen`, **after Step 0 of the window has
settled**. Baselines taken before Step 0 make §4 diff against stale state.

```bash
cd /Users/mu/code/cberg-home-nextgen
helm repo update cilium >/dev/null   # premise chart-1.20.5-is-published reads the LOCAL cache
.venv/bin/python3 runbooks/plan-premises.py cilium-1.20.5 --require-premises
#   PASS: every premise PASS, exit 0.
#   A first FAIL naming only no-kustomization-in-flight / no-helmrelease-in-flight is Step 0
#   still settling: wait ~60s and re-run ONCE. Any other FAIL, or a second FAIL, is a stop.
#   KNOWN 2026-11-27: etcd-leader-changes-24h-below-6 FAILS (got the raw value 11.0/24h). Do NOT relax it.
#   Wait for the churn findings (F-33873912) to clear, or get an explicit operator override
#   recorded in the window close-out.
```

The gates below use `$( )`, `>`, loops or `gh`, which the premise runner refuses. Run
them by hand. Each one states its PASS and FAIL.

```bash
# a) Agent health on EVERY node.
for p in $(kubectl get pods -n kube-system -l k8s-app=cilium -o name); do
  echo -n "$p: "; kubectl -n kube-system exec "$p" -c cilium-agent -- cilium-dbg status --brief
done
#   PASS: 3x OK (measured 2026-11-18).   FAIL: any non-OK line — STOP.

# b) Module health baseline — gate is Stopped(0) Degraded(0) on all three.
for p in $(kubectl get pods -n kube-system -l k8s-app=cilium -o name); do
  echo -n "$p "; kubectl -n kube-system exec "$p" -c cilium-agent -- cilium-dbg status | grep -E 'Modules Health'
done

# c) Did Renovate open a PR since authoring? (pr: null at authoring)
gh pr list --state open --search "cilium in:title" --json number,title,headRefName
#   EMPTY [] -> use the direct edit in §3.2 (the default path).
#   A PR exists -> its diff must be EXACTLY the two version lines below, CI green, or STOP:
#     gh pr diff <N> | grep -E '^[+-][^+-]'
#       -      version: 1.20.4 / +      version: 1.20.5 / -    version: 1.20.4 / +    version: 1.20.5
#     gh pr checks <N>     # every line pass
#   Then merge it in §3.2 instead of the direct edit, and record its number in the close-out.

# e) LB table baseline (domain-free, VIPs only).
kubectl get svc -A -o json | .venv/bin/python3 -c "
import sys, json
d = json.load(sys.stdin)
rows = sorted((i['metadata']['namespace'] + '/' + i['metadata']['name'],
               (i['status'].get('loadBalancer', {}).get('ingress') or [{}])[0].get('ip'))
              for i in d['items'] if i['spec']['type'] == 'LoadBalancer')
[print(n, ip) for n, ip in rows]
" > /tmp/cilium-lb-before.txt
wc -l < /tmp/cilium-lb-before.txt                      # PASS: 15 (= premise lb-services-are-15; §3.4b/§4.4b read this file)
grep -c -E ' 192\.168\.55\.(103|104|5)$' /tmp/cilium-lb-before.txt   # PASS: 3 (envoy-internal, envoy-external, adguard)

# h) LAN reachability baseline through both gateway VIPs + DNS VIP (measured 200/200/answers 2026-11-18).
HINT=$(kubectl get httproute -n default echo-server -o jsonpath='{.spec.hostnames[0]}')
HEXT=$(kubectl get httproute -n office mealie -o jsonpath='{.spec.hostnames[0]}')
curl -sk --resolve "$HINT:443:192.168.55.103" -o /dev/null -w 'envoy-internal .103 -> %{http_code}\n' --max-time 10 "https://$HINT/"
curl -sk --resolve "$HEXT:443:192.168.55.104" -o /dev/null -w 'envoy-external .104 -> %{http_code}\n' --max-time 10 "https://$HEXT/"
if dig +short +time=2 +tries=1 @192.168.55.5 kubernetes.io | grep -q '[0-9]'; then echo 'DNS VIP .5 OK'; else echo 'DNS VIP .5 FAIL'; fi
#   PASS: 200, 200, 'DNS VIP .5 OK'. FAIL: anything else — the edge is already broken; do not start.

# l) OPERATOR — no active Music Assistant stream / Plex playback, no CI job the operator
#    cares about mid-run (CI pods' DNS proxy restarts with their node's agent).

# m) Policy-enforcement baseline FROM THE DATAPATH.
for p in $(kubectl get pods -n kube-system -l k8s-app=cilium -o name); do
  kubectl -n kube-system exec "$p" -c cilium-agent -- cilium-dbg endpoint list
done | grep -c 'Enabled' | tee /tmp/cilium-enf-before.txt
for n in ci-runner arc-system arc-build; do kubectl get pods -n $n --no-headers; done | wc -l | tee /tmp/cilium-ci-pods-before.txt
#   A WINDOW baseline (ARC runners scale with jobs), never a constant. `grep -c 'Enabled'`
#   does not match "Disabled".
#   Then run the §4.7c block (edot-collector ingress enforcement) once as a baseline.
#   PASS: "edot ingress=Enabled". A baseline FAIL makes §4.7c informational; record why.

# n) FQDN canary BASELINE — run the §4.9 block now, unchanged. PASS: ALLOW PASS and DENY PASS
#    on all three nodes. If the baseline itself fails, §4.9 is INFORMATIONAL for this window:
#    record why; never let a pre-existing state trigger a CNI rollback.

# o) etcd gate — talks to Talos on the node IPs (NOT the pod network), so it still answers
#    when the CNI is sick.
cat > /tmp/cilium-etcd-gate.sh <<'GATE'
#!/bin/bash
# cilium-etcd-gate: exit 0 = etcd healthy; exit 1 = STOP. Reads Talos (not the pod network).
cd /Users/mu/code/cberg-home-nextgen
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
#   PASS: "GATE-OK 3 members, 1 leader, LEADER_IP=192.168.55.1x". Talos output read 2026-11-18:
#         3 rows, one leader 73a201c6b4bf6faf (= .13), rows end in the STORAGE column "3.7.0"
#         with ERRORS empty, which is the shape the regex expects. FAIL (exit 1): <3 rows, split
#         leader view, non-empty ERRORS, talosctl unreachable. Negative control (from the 1.20.4 run):
#         N set to one IP prints "GATE-FAIL rows=1".
kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=max(etcd_server_leader_changes_seen_total)' \
  | .venv/bin/python3 -c "import sys,json;print(json.load(sys.stdin)['data']['result'][0]['value'][1])" | tee /tmp/cilium-etcd-lc-before.txt
#   PASS: a number. FAIL: IndexError/empty (etcd not scraped) - STOP.

# p) Pre-pull the 1.20.5 images at NODE level (containerd, host network - CNI-independent).
for ip in 192.168.55.11 192.168.55.12 192.168.55.13; do
  talosctl -n $ip image pull quay.io/cilium/cilium:v1.20.5@sha256:aa72499f075ad729947ea91b026218aceba24f1a8e4534bf36b8368c7c561526
  talosctl -n $ip image pull quay.io/cilium/operator-generic:v1.20.5@sha256:c6e7de6665aa9701db86c4fe46828a75a0d167afe084a9ffb5bce34b2c4fa8c4
done
for ip in 192.168.55.11 192.168.55.12 192.168.55.13; do
  talosctl -n $ip image list | grep -c -E 'sha256:(aa72499f075ad729|c6e7de6665aa9701)'
done
#   PASS: 3 lines, each >= 2.  FAIL: any 0/1 — STOP, do not start a CNI roll that must pull.

# q) Pin the ROLLBACK revision NOW, before §3.4a adds more 1.20.4-chart revisions.
#    Revision 25 is ALSO chart cilium-1.20.4 but was rendered with OnDelete (the 10-25 gated
#    roll), and §3.4a will add another (OnDelete + 1.20.4). "Latest 1.20.4 revision" is therefore
#    the WRONG rollback target after §3.4a. Record the currently DEPLOYED one:
helm history cilium -n kube-system -o json | .venv/bin/python3 -c "
import sys, json
d = [x for x in json.load(sys.stdin) if x['status'] == 'deployed']
assert len(d) == 1 and d[0]['chart'] == 'cilium-1.20.4', d
print(d[0]['revision'])" | tee /tmp/cilium-rollback-rev.txt
helm get manifest cilium -n kube-system --revision "$(cat /tmp/cilium-rollback-rev.txt)" | grep -c 'type: OnDelete'
#   PASS: revision printed (26 at authoring) AND OnDelete count 0 (measured 0 for rev 26).
#   FAIL: AssertionError, or count != 0 — STOP; the rollback target is not a clean RollingUpdate 1.20.4.
```

---

## 3) Steps

**Mandatory order: 3.1 → 3.4a → 3.2 → 3.4b → 3.4c → 3.6.**

### 3.1 Active-update marker (application-update.md §Step 1b)

```bash
cd /Users/mu/code/cberg-home-nextgen
runbooks/update-marker.sh add cilium kube-system 2 "chart 1.20.4 -> 1.20.5 CNI patch"
```

### 3.4a Commit OnDelete + disableWait FIRST, separately (no pod may restart)

**Correction carried from the 1.20.4 run (retire commit `3505ff89`):** with the DaemonSet
on `OnDelete`, helm's wait never completes after the template changes (0 of 3 updated
reads InProgress), so the HelmRelease upgrade times out after 5 min, remediation rolls
it back, and §3.2 cannot pass. That run fixed it with an in-window amendment
(`38cfffc0`). This plan sets `upgrade.disableWait: true` in the same commit as OnDelete
and reverts both together in §3.4c. The strategy change alone does not touch the pod
template, so this commit's own helm wait still completes.

Both edits were dry-tested on scratch copies with BSD sed / helm on 2026-11-18:
helm-values append → render diff exactly `1009c1009 < type: RollingUpdate / > type: OnDelete`.
helmrelease sed → diff exactly `21a22 > disableWait: true`. The anchor
`^    cleanupOnFail: true$` occurs exactly once (measured).

```bash
(   # subshell + set -e: a failing line ends THIS block, never your terminal
set -e
cd /Users/mu/code/cberg-home-nextgen
kubectl get pods -n kube-system -l k8s-app=cilium --no-headers -o custom-columns=N:.metadata.name,S:.status.startTime > /tmp/cilium-pod-start-before.txt
V=kubernetes/apps/kube-system/cilium/app/helm-values.yaml
H=kubernetes/apps/kube-system/cilium/app/helmrelease.yaml
test "$(grep -c '^updateStrategy:' $V)" = 0 || { echo "STOP: updateStrategy already in $V"; exit 1; }
test "$(grep -c 'disableWait' $H)" = 0 || { echo "STOP: disableWait already in $H"; exit 1; }
printf 'updateStrategy:\n  type: OnDelete\n' >> $V
sed -i '' 's/^    cleanupOnFail: true$/    cleanupOnFail: true\
    disableWait: true/' $H
git diff --stat -- $V $H        # PASS: 2 files, 2 + 1 insertions, 0 deletions
# PRE-PUSH GATE: render the real values + appended key against the CURRENT chart 1.20.4
helm template cilium cilium/cilium --version 1.20.4 -n kube-system -f $V > /tmp/cilium-od-render.yaml
test "$(grep -c 'type: OnDelete' /tmp/cilium-od-render.yaml)" = 1 || { echo 'STOP: OnDelete count != 1'; exit 1; }
.venv/bin/python3 -c "import yaml; d=yaml.safe_load(open('$H')); assert d['spec']['upgrade']['disableWait'] is True; print('HR disableWait OK')"
printf 'chore(cilium): temporary OnDelete + upgrade.disableWait for a gated one-node-at-a-time roll (plan cilium-1.20.5)\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\n' > /tmp/cilium-od-msg.txt
git commit --only $V $H -F /tmp/cilium-od-msg.txt
git log -1 --format=%s ; git show --stat HEAD     # subject must be YOURS; exactly these 2 files
git push origin main
git rev-parse HEAD > /tmp/cilium-od-sha.txt
flux reconcile source git flux-system && flux reconcile ks cilium -n kube-system && flux reconcile hr cilium -n kube-system
kubectl wait hr/cilium -n kube-system --for=condition=Ready --timeout=10m
kubectl get ds -n kube-system cilium -o jsonpath='{.spec.updateStrategy.type}{"\n"}'   # PASS: OnDelete
kubectl get hr -n kube-system cilium -o jsonpath='{.spec.upgrade.disableWait}{"\n"}'     # PASS: true
kubectl get pods -n kube-system -l k8s-app=cilium --no-headers -o custom-columns=N:.metadata.name,S:.status.startTime | diff - /tmp/cilium-pod-start-before.txt && echo PODS-UNTOUCHED
#   PASS: PODS-UNTOUCHED. FAIL: any pod restarted -> OnDelete did not hold; STOP, go to §5.
)
```

(The cilium Kustomization lives in `kube-system`, not `flux-system`. The 1.20.4 run hit that.)

### 3.2 Land the version pins (direct edit; or merge the PR found in §2c)

Dry-tested on scratch copies 2026-11-18: each edit changed exactly one line
(`12c12 version: 1.20.4 → 1.20.5` in the HelmRelease, `21c21` in the helmfile).

```bash
(
set -e
cd /Users/mu/code/cberg-home-nextgen
sed -i '' 's/^      version: 1\.20\.4$/      version: 1.20.5/' kubernetes/apps/kube-system/cilium/app/helmrelease.yaml
.venv/bin/python3 - <<'PY'
import re
p = 'kubernetes/bootstrap/apps/helmfile.yaml'
s = open(p).read()
new = re.sub(r'(- name: cilium\n    namespace: kube-system\n    chart: cilium/cilium\n    version: )1\.20\.4',
             r'\g<1>1.20.5', s)
assert s != new, 'anchor did not match — STOP and inspect the file'
open(p, 'w').write(new)
PY
git diff -- kubernetes/apps/kube-system/cilium/app/helmrelease.yaml kubernetes/bootstrap/apps/helmfile.yaml | grep -E '^[+-][^+-]'
#   PASS: exactly 4 lines: -/+ "      version: 1.20.4/5" and -/+ "    version: 1.20.4/5"
cat > /tmp/cilium-msg.txt <<'EOF'
feat(cilium): chart 1.20.4 -> 1.20.5 (CNI patch; plan cilium-1.20.5)

Bugfix patch on the 1.20 line. Rendered delta against our values: agent +
operator-generic image digests and a default operator toleration for
node-role.kubernetes.io/etcd; cilium-config unchanged. Carries the DNS-proxy
identity-refresh and bootstrap-ordering fixes, restored-endpoint policy fix,
and L2 announcer fixes (Lease names change to <ns>.<svc>).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
git commit --only kubernetes/apps/kube-system/cilium/app/helmrelease.yaml kubernetes/bootstrap/apps/helmfile.yaml -F /tmp/cilium-msg.txt
git log -1 --format=%s     # MUST be the subject above; else git commit --amend -F /tmp/cilium-msg.txt (before push)
git show --stat HEAD       # MUST list exactly the two files, 1+/1- each
git push origin main
git rev-parse HEAD > /tmp/cilium-bump-sha.txt
flux reconcile source git flux-system && flux reconcile ks cilium -n kube-system && flux reconcile hr cilium -n kube-system
kubectl wait hr/cilium -n kube-system --for=condition=Ready --timeout=10m
kubectl get hr -n kube-system cilium -o jsonpath='{.status.history[0].chartVersion}{"\n"}'   # PASS: 1.20.5
kubectl get ds -n kube-system cilium -o jsonpath='{.spec.template.spec.containers[?(@.name=="cilium-agent")].image}{"\n"}' | grep -c 'aa72499f'   # PASS: 1
kubectl get ds -n kube-system cilium -o jsonpath='{.spec.updateStrategy.type}{"\n"}'          # PASS: OnDelete
kubectl get pods -n kube-system -l k8s-app=cilium --no-headers -o custom-columns=N:.metadata.name,S:.status.startTime | diff - /tmp/cilium-pod-start-before.txt && echo AGENTS-UNTOUCHED
#   PASS: AGENTS-UNTOUCHED. Expected side effect: cilium-operator restarts (1 replica; ~1 min with no
#   new LB-IPAM allocations / identity GC; no datapath effect).
kubectl -n kube-system rollout status deploy/cilium-operator --timeout=5m
)
```

*If §2c found a Renovate PR:* `gh pr merge <N> --squash --delete-branch && git fetch origin main && git merge --ff-only origin/main`,
then `git log -1 --format=%H -- kubernetes/apps/kube-system/cilium/app/helmrelease.yaml > /tmp/cilium-bump-sha.txt`
and continue from the `flux reconcile` line above.

### 3.3 (none — the config Kustomization is out of scope)

`kubernetes/apps/kube-system/cilium/config/` (LB pool, L2 policy) is a separate
Kustomization. Never bundle a pool edit into a version bump. A bad pool and a bad agent
look identical from the LAN.

### 3.4b Per-node roll — followers first, etcd leader's node last

```bash
cat > /tmp/cilium-roll.sh <<'ROLL_EOF'
#!/usr/bin/env bash
# Run as a child so `exit 1` STOPs end this script, never your terminal.
set -u
cd /Users/mu/code/cberg-home-nextgen
NEW=aa72499f075ad729
HINT=$(kubectl get httproute -n default echo-server -o jsonpath='{.spec.hostnames[0]}')
HEXT=$(kubectl get httproute -n office mealie -o jsonpath='{.spec.hostnames[0]}')
test -n "$HINT" && test -n "$HEXT" || { echo 'STOP: empty HINT/HEXT'; exit 1; }
bash /tmp/cilium-etcd-gate.sh > /tmp/cilium-gate-out.txt 2>&1; GRC=$?
cat /tmp/cilium-gate-out.txt
[ $GRC -eq 0 ] || { echo "STOP: etcd gate rc=$GRC"; exit 1; }
LEADER=$(grep -o 'LEADER_IP=[0-9.]*' /tmp/cilium-gate-out.txt | cut -d= -f2)
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
        -o jsonpath='{.items[0].status.containerStatuses[0].imageID} {.items[0].status.containerStatuses[0].ready}' | grep -q "$NEW.* true"; do
    n=$((n+1)); [ $n -gt 60 ] && { echo "STOP: $NODE agent not Ready on 1.20.5 after 5 min"; exit 1; }; sleep 5
  done
  P=$(kubectl -n kube-system get pods -l k8s-app=cilium --field-selector spec.nodeName=$NODE -o name)
  kubectl -n kube-system exec $P -c cilium-agent -- cilium-dbg status --brief | grep -qx OK || { echo "STOP: $NODE cilium-dbg not OK"; exit 1; }
  kubectl get node $NODE --no-headers | grep -q ' Ready' || { echo "STOP: $NODE NotReady"; exit 1; }
  sleep 60
  bash /tmp/cilium-etcd-gate.sh || { echo "STOP after $NODE: etcd gate"; exit 1; }
  LC=$(kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=max(etcd_server_leader_changes_seen_total)' | .venv/bin/python3 -c "import sys,json;print(int(float(json.load(sys.stdin)['data']['result'][0]['value'][1])))")
  B=$(cut -d. -f1 /tmp/cilium-etcd-lc-before.txt)
  [ $((LC-B)) -le 1 ] || { echo "STOP: etcd leader changes +$((LC-B)) since baseline"; exit 1; }
  curl -sk -o /dev/null -w "envoy-internal .103 -> %{http_code}\n" --max-time 10 --resolve "$HINT:443:192.168.55.103" "https://$HINT/" | grep -q ' 200' || { echo "STOP: .103 not 200"; exit 1; }
  curl -sk -o /dev/null -w "envoy-external .104 -> %{http_code}\n" --max-time 10 --resolve "$HEXT:443:192.168.55.104" "https://$HEXT/" | grep -q ' 200' || { echo "STOP: .104 not 200"; exit 1; }
  dig +short +time=2 +tries=1 @192.168.55.5 kubernetes.io | grep -q '[0-9]' || { echo "STOP: AdGuard VIP .5 not answering"; exit 1; }
  NEWL=$(kubectl get leases -n kube-system -o custom-columns=N:.metadata.name --no-headers | grep -c 'cilium-l2announce-[a-z0-9-]*\.')
  WANT=$(wc -l < /tmp/cilium-lb-before.txt | tr -d ' ')
  echo "new-format L2 leases: $NEWL (expect $WANT = LB services in §2e baseline, 15 at re-plan)"
  [ "$WANT" -ge 1 ] && [ "$NEWL" -eq "$WANT" ] || { echo "STOP: $NEWL/$WANT new-format leases — a VIP has no 1.20.5 announcer (or §2e baseline missing)"; exit 1; }
done
ROLL_EOF
bash /tmp/cilium-roll.sh; echo "roll rc=$?"      # PASS: rc=0 and 3 nodes rolled.
```

Why the per-node lease check is valid: after the first node rolls, that node is the
only contender for the 15 new-format Leases and takes all of them within one
lease-acquire cycle (seconds). A count below 15 after the 60 s settle means a Service
is not being elected on the new side, so that VIP goes dark once its last 1.20.4
announcer rolls. The check can FAIL. It reads 0 if the agent did not start the L2
announcer at all.

A STOP leaves the cluster **mixed 1.20.4/1.20.5 and stable** (patch skew, OnDelete holds
the rest). Mixed means two announcers per VIP (§1.4), which is functional on eTP=Cluster.
Do NOT continue, and do NOT auto-rollback. Hand it to the operator (§5.2/§5.3b).

### 3.4c Restore RollingUpdate + helm wait (zero pod restarts)

```bash
cd /Users/mu/code/cberg-home-nextgen
kubectl get pods -n kube-system -l k8s-app=cilium --no-headers -o custom-columns=N:.metadata.name,S:.status.startTime > /tmp/cilium-pod-start-after-roll.txt
git revert --no-edit "$(cat /tmp/cilium-od-sha.txt)"     # removes BOTH OnDelete and disableWait
git log -1 --format=%s; git show --stat HEAD              # your revert; exactly helm-values.yaml + helmrelease.yaml
git push origin main
flux reconcile source git flux-system && flux reconcile ks cilium -n kube-system && flux reconcile hr cilium -n kube-system
kubectl wait hr/cilium -n kube-system --for=condition=Ready --timeout=10m
kubectl get ds -n kube-system cilium -o jsonpath='{.spec.updateStrategy.type} {.status.numberReady}/{.status.desiredNumberScheduled} {.status.updatedNumberScheduled}{"\n"}'
kubectl get hr -n kube-system cilium -o jsonpath='dw=[{.spec.upgrade.disableWait}]{"\n"}'
kubectl get pods -n kube-system -l k8s-app=cilium --no-headers -o custom-columns=N:.metadata.name,S:.status.startTime | diff - /tmp/cilium-pod-start-after-roll.txt && echo REVERT-DID-NOT-RESTART-AGENTS
#   PASS: "RollingUpdate 3/3 3", "dw=[]", REVERT-DID-NOT-RESTART-AGENTS.
#   FAIL: updatedNumberScheduled < 3 (an agent would roll unattended at maxUnavailable 2) — STOP.
```

### 3.5 Watch the roll

§3.4b IS the watch: it blocks and gates. `rollout status ds/cilium` is meaningless
under OnDelete.

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
#   PASS: True 1.20.5     FAIL: UpgradeFailed / still 1.20.4
kubectl -n kube-system get pods -l k8s-app=cilium \
  -o jsonpath='{range .items[*]}{.spec.nodeName} {.status.containerStatuses[0].imageID}{"\n"}{end}'
#   PASS: 3 lines, each ending sha256:aa72499f075ad729...   FAIL: any line on 20fe92e4... (never rolled)
kubectl -n kube-system get pods -l name=cilium-operator \
  -o jsonpath='{.items[*].status.containerStatuses[0].imageID}{"\n"}'
#   PASS: contains sha256:c6e7de6665aa9701...   (measured before: 7a7a3489dc66ad67)
```

**4.2 — CONTENTS: every agent is scraped and reports 1.20.5; the FQDN proxy is forwarding.**

```
CONTENTS ASSERTION: all 3 agents report version 1.20.5 and none 1.20.4 — measured by
count by (version)(cilium_version), compared to the 2026-11-18 baseline {1.20.4: 3}.
CONTENTS ASSERTION: the DNS proxy forwards real queries after the roll — increase of
cilium_policy_l7_total{proxy_type="fqdn",rule="forwarded"} over 10 min starting AFTER the
roll, floor > 0 (cumulative read 527955 on 2026-11-18; CI pods query continuously).
CONTROL: metric cilium_version — count by version; gate: ==3 at 1.20.5, EMPTY at 1.20.4
CONTROL: metric up — job="cilium-agent"; gate: count(up==1) == 3
CONTROL: metric cilium_policy_l7_total — proxy_type="fqdn", rule="forwarded"; gate: increase > 0
CONTROL: metric cilium_endpoint_state — gate: waiting-for-identity + regenerating + restoring == 0, ready > 0
```

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 >/dev/null 2>&1 & PF=$!
sleep 3
q() { curl -s --get http://localhost:9090/api/v1/query --data-urlencode "query=$1" \
  | .venv/bin/python3 -c "import sys,json; r=json.load(sys.stdin)['data']['result']; print([x['value'][1] for x in r] or 'EMPTY')"; }
q 'count(cilium_version{version="1.20.5"})'        # PASS: ['3']
q 'count(cilium_version{version="1.20.4"})'        # PASS: EMPTY
q 'count(up{job="cilium-agent"} == 1)'             # PASS: ['3']
# wait until >= 10 min after §3.4b completed, then:
q 'sum(increase(cilium_policy_l7_total{proxy_type="fqdn",rule="forwarded"}[10m]))'   # PASS: > 0
q 'sum(cilium_endpoint_state{endpoint_state=~"waiting-for-identity|regenerating|restoring"})'  # PASS: ['0']
q 'sum(cilium_endpoint_state{endpoint_state="ready"})'                                # PASS: > 0
kill $PF 2>/dev/null
```

*Why these can fail:* `up` alone passes with agents stuck on the old image.
`cilium_version` alone goes EMPTY (not red) if scraping broke. Together the three fail on
wrong version, missing node and dead scrape. `q` prints `EMPTY` instead of nothing. The
`increase()` gate handles the counter reset on restart and reads 0 if the proxy stopped
forwarding.

**4.3 — Agent + module health on every node.** Re-run §2a and §2b.
PASS: 3x OK and `Stopped(0) Degraded(0)` on all three. FAIL: any non-OK, or Degraded(n>0).
The brief line can read OK while a module is degraded, which is why both are read.

**4.4 — LB table byte-identical.**

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
#   PASS: LB TABLE UNCHANGED (15 rows).   FAIL: an IP empty or changed (LB-IPAM lost a pin).
```

**4.4b — CONTENTS: the L2 Lease rename completed (the 1.20.5-specific gate).**

```
CONTENTS ASSERTION: every LB Service is elected under the NEW Lease name and no old-format
Lease is still held — measured by the two lease-name counts below, compared to the
premise baselines old=15 / new=0 (expected count read from the §2e baseline file).
```

```bash
sleep 120   # leaseGC runs every 60 s in each 1.20.5 agent; give it two cycles after the last node rolled
kubectl get leases -n kube-system -o custom-columns=N:.metadata.name,H:.spec.holderIdentity --no-headers \
  | .venv/bin/python3 -c "
import sys
want = sum(1 for _ in open('/tmp/cilium-lb-before.txt'))
assert want >= 1, 'no §2e baseline'
rows = [l.split() for l in sys.stdin if l.startswith('cilium-l2announce-')]
new = [r for r in rows if '.' in r[0]]
old = [r for r in rows if '.' not in r[0]]
held_new = [r for r in new if len(r) > 1 and r[1] not in ('', '<none>')]
held_old = [r for r in old if len(r) > 1 and r[1] not in ('', '<none>')]
print('new=%d held_new=%d old=%d held_old=%d' % (len(new), len(held_new), len(old), len(held_old)))
print('want=%d' % want)
print('L2-LEASES OK' if len(new) == want and len(held_new) == want and len(held_old) == 0 else 'L2-LEASES FAIL')
for r in old: print('  leftover old lease:', r)
"
#   PASS: "new=15 held_new=15 old=0 held_old=0", "want=15" + L2-LEASES OK.
#   FAIL: new < want or held_new < want -> a Service has no announcer (its VIP is dark on the LAN even though
#         its Service still shows an IP: §4.4 cannot see this). held_old > 0 -> an agent is still 1.20.4
#         (re-read §4.1).
#   old > 0 with held_old == 0 just means GC has not run yet: wait 60 s and re-run. Persisting empty-holder
#   old Leases after 5 min are inert; delete by name only AFTER §4.1 passes:
#     kubectl delete lease -n kube-system <exact old name>
```

The 15 holder names should also be spread across nodes. Print them with the same command
and compare against the old distribution (e.g. envoy-internal on 03, envoy-external on 02
at authoring). Informational only: the election is free to move holders.

**4.5 — Both gateway VIPs and the DNS VIP still serve.** Re-run §2h verbatim.
PASS: 200, 200, 'DNS VIP .5 OK'. `--resolve` pins the connection to the VIP; against an
unused VLAN-55 address the same probe returns `000`/exit 28 (measured on the 1.20.2 run),
so a dark VIP is a hard failure.

**4.6 — LAN VIP surface beyond the gateways.**

```bash
curl -sk -o /dev/null -w 'HA .24:8123 -> %{http_code}\n' --max-time 8 http://192.168.55.24:8123
curl -sk -o /dev/null -w 'MA .29:8095 -> %{http_code}\n' --max-time 8 http://192.168.55.29:8095
#   PASS: 200, 200 (measured 2026-11-18).   FAIL: 000 or anything else.
```

**4.7 — Policy enforcement survived (datapath, not API server).**

```bash
# a) enforcement count
for p in $(kubectl get pods -n kube-system -l k8s-app=cilium -o name); do
  kubectl -n kube-system exec "$p" -c cilium-agent -- cilium-dbg endpoint list
done | grep -c 'Enabled'
for n in ci-runner arc-system arc-build; do kubectl get pods -n $n --no-headers; done | wc -l
#   PASS: enforcement count == /tmp/cilium-enf-before.txt. If it differs, compare the CI-pod count
#   against /tmp/cilium-ci-pods-before.txt: runner scaling moves it legitimately. Since 2026-11-25 the
#   count also includes the edot-collector pod (ingress Enabled) and since 2026-11-23 camofox-browser;
#   neither scales, so they do not move it. A DROP with an
#   UNCHANGED CI-pod count is a FAIL (agents came up without policy print "Disabled").
# b) CNP validity
kubectl get cnp -A --no-headers | awk '$4!="True"{print "INVALID: "$0}' ; kubectl get cnp -A --no-headers | wc -l
#   PASS: no INVALID line, count 7.   FAIL: any INVALID line.

# c) The one ingress CNP still enforces on its endpoint (1.20.5 "restored endpoints" fix, §1.4).
EPOD=$(kubectl get pods -n monitoring -l app=edot-collector -o jsonpath='{.items[0].metadata.name}')
EIP=$(kubectl get pod -n monitoring "$EPOD" -o jsonpath='{.status.podIP}')
ENODE=$(kubectl get pod -n monitoring "$EPOD" -o jsonpath='{.spec.nodeName}')
AG=$(kubectl get pods -n kube-system -l k8s-app=cilium --field-selector spec.nodeName="$ENODE" -o name)
echo "edot pod=$EPOD ip=$EIP node=$ENODE agent=$AG"
kubectl -n kube-system exec "$AG" -c cilium-agent -- cilium-dbg endpoint list \
  | awk -v ip="$EIP" 'index($0, " " ip " ") {print "edot ingress=" $2; f=1} END {if (!f) print "edot ingress=NOT-FOUND"}'
#   PASS: "edot ingress=Enabled" (measured 2026-11-27 on k8s-nuc14-03, endpoint 1928, pre-upgrade).
#   FAIL: "edot ingress=Disabled" -> the restored endpoint lost its ingress policy (policy not applied,
#         the edot syslog ports are open to anything); "NOT-FOUND" -> empty pod/IP/agent variable or the
#         endpoint is not managed on that node. Either is a §5 trigger if the pre-upgrade run PASSed.
#   Run it ALSO in §2 (after §2m) as the baseline; a baseline FAIL makes this gate informational.
```

**4.8 — A FRESH POD GETS NETWORKING, on every node.** This is the deny rule's
requirement. Existing pods keep networking from in-kernel BPF state, so every gate above
can pass while `CNI ADD` is broken.

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
#   PASS: per node "condition met", GATE2 PASS, GATE3 PASS.
#   FAIL: any line containing FAIL. READ THE OUTPUT, NOT THE EXIT CODE (a loop's status is the last
#   iteration's). Gate-1 failure signature: FailedCreatePodSandBox naming cilium-cni; rule out
#   OutOfcpu/OutOfmemory in describe first (nodeName bypasses the scheduler).
```

Objects verified live 2026-11-18: nodes `k8s-nuc14-01/02/03`; `svc/echo-server` :8080 in
`default`; 0 netpol / 0 CNP in `default`; `busybox:1.38.0` cached on all 3 nodes via
`ds/security/falco-log-rotate`.

**4.9 — The L7 DNS / toFQDNs path works and still ENFORCES, on every node.** Three of the
1.20.5 fixes are on this path (§1.4), and no other gate exercises it. Canary runs in
`ci-runner`, where CNP `ci-runner-lockdown` allows DNS only for `github.com`,
`registry.npmjs.org` and `**.cluster.local`.

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
#   PASS (per node): ALLOW PASS and DENY PASS, and the §2n baseline read the same.
#   FAIL: ALLOW FAIL => DNS proxy not forwarding allowed names on that node.
#         DENY FAIL  => L7 DNS policy NOT ENFORCED on that node (silent security regression).
```

This block ran unchanged in the 1.20.4 window (2026-10-25: baseline and post both
PASS/PASS on 3 nodes), against the same `ci-runner` PSA `restricted` enforcement,
ResourceQuota and LimitRange. Both markers use `grep -qx`, so empty output fails both.

**4.10 — OPERATOR GATE.** Play a stream through Music Assistant and open the Home
Assistant dashboard. Both must work. No cron can perform this check, which is why the plan
is `autonomy_override: human-gated`. Do not close the window without it.

**4.11 — Settle.** Wait 15 minutes. Confirm no new firing alerts compared with the
pre-window set (port-forward Prometheus per CLAUDE.md, filter `Watchdog|InfoInhibitor`).
Re-read §4.2's `increase()` gate and §4.4b at the end. No `CONTROL: alertname` is named:
the repo's PrometheusRules define no Cilium alert (`grep -rhoE 'alert: *[A-Za-z]*Cilium'
kubernetes/` is empty, 2026-11-18). The §4.2 metric CONTROLs are the binding gates, and 4.11
is a firing-set diff.

---

## 5) Rollback

### 5.1 The honest verdict

`rollback_class: git-revert` is honest, since nothing here is forward-only. 1.20.4 agents
simply re-create the old-named Leases, and leaseGC in either version deletes the other
format's Leases once their holder empties. But the machinery that executes a git revert
runs **on the datapath this plan changes**: all Flux controllers are pod-network. Two
things survive a broken CNI. `kube-apiserver` is hostNetwork on .11/.12/.13 behind the
Talos VIP, so `kubectl`/`helm` from the Mac keep working. Existing pods keep flowing on
in-kernel BPF state, which buys minutes. **When in doubt use §5.3 first and reconcile git
after.**

### 5.2 Limb A — regression, Flux healthy, roll NOT started or finished cleanly

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit "$(cat /tmp/cilium-bump-sha.txt)"   # the version bump only
git log -1 --format=%s; git show --stat HEAD              # your revert; exactly helmrelease.yaml + helmfile.yaml
git push origin main
flux reconcile source git flux-system && flux reconcile ks cilium -n kube-system && flux reconcile hr cilium -n kube-system
```

- **If OnDelete is still on** (§3.4c not yet run): the template goes back to 1.20.4 and
  nothing restarts. Use §5.3b's per-node loop with the image check pointed at
  `20fe92e4c8664123`, then run §3.4c.
- **If §3.4c already ran** (RollingUpdate back): the revert rolls agents up to **two at a
  time** (`maxUnavailable: 2`). To keep one-at-a-time, first re-apply §3.4a (new OnDelete +
  disableWait commit), then revert the bump, loop per node, then §3.4c again.

Confirm with §4.1 (expect chart 1.20.4, agent `sha256:20fe92e4…`, operator
`sha256:7a7a3489…`), §4.3, §4.4, §4.4b with the formats reversed (expect old=15 held, new
Leases GC'd), §4.5, §4.9.

### 5.3 Limb B — break-glass: datapath broken, Flux cannot act (works without Flux)

```bash
cd /Users/mu/code/cberg-home-nextgen        # REQUIRED: helm/flux are mise shims pinned here
flux suspend helmrelease cilium -n kube-system     # else helm-controller re-applies 1.20.5 when it recovers
REV=$(cat /tmp/cilium-rollback-rev.txt)            # recorded in §2q: the DEPLOYED clean 1.20.4 revision (26)
helm history cilium -n kube-system | awk -v r="$REV" '$1==r'
#   MUST show chart cilium-1.20.4. Do NOT pick "the latest cilium-1.20.4 revision": §3.4a creates one
#   rendered with OnDelete (and rev 25 already is), and rolling back to it restarts nothing.
helm rollback cilium "$REV" -n kube-system --wait --timeout 10m
kubectl -n kube-system rollout status ds/cilium --timeout=10m
#   rev 26 is RollingUpdate maxUnavailable 2: agents restart up to two at a time. That is acceptable
#   ONLY because this limb is for an already-broken datapath (nothing left to protect).
# prove the datapath is back: §4.3, §4.4 (diff vs /tmp/cilium-lb-before.txt), §4.5, §4.8
git revert --no-edit "$(cat /tmp/cilium-bump-sha.txt)"
test -f /tmp/cilium-od-sha.txt && git revert --no-edit "$(cat /tmp/cilium-od-sha.txt)"   # drop OnDelete+disableWait too
git log -2 --format=%s; git push origin main
flux resume helmrelease cilium -n kube-system     # own line: resume even if the push failed
```

If `/tmp/cilium-rollback-rev.txt` is lost: `helm get manifest cilium -n kube-system --revision <N> | grep -c 'type: OnDelete'`
must print 0 for the revision you choose, and `helm history` must show it as chart
cilium-1.20.4.

A HelmRelease left suspended is itself an incident, because an unreconciled CNI drifts
silently. If you must stop before `flux resume`, record that in the window close-out.

### 5.3b Rollback DURING the gated roll (OnDelete still on)

A `git revert` of the bump changes the template but restarts nothing. Revert the bump
commit (leave the OnDelete commit), push, and wait for HR Ready. Then delete the agent pod
one node at a time, only on nodes already on 1.20.5, with `/tmp/cilium-etcd-gate.sh`
before and after each. Use the same loop as §3.4b with `NEW=20fe92e4c8664123`, the lease
check inverted to old-format, and the per-node STOP left as is. Then run §3.4c. Nodes not
yet rolled need nothing. Mixed state during this is the same dual-announcer state as
§1.4, which is functional.

### 5.3c What still works when the pod network is degraded

- `kubectl`/`helm` from the Mac (Talos VIP → hostNetwork apiserver; no CoreDNS involved).
- `talosctl` (etcd status, image pull, service restart, reboot as a last resort) against
  node IPs. The etcd gate and image pre-pull never depend on the CNI.
- NOT working: Flux controllers (a pushed revert is not applied, so use §5.3), CoreDNS,
  the FQDN proxy for ci-runner/arc namespaces, Prometheus (§4.2 reads empty, so judge by
  `cilium-dbg`), the AdGuard / k8s-gateway VIPs.
- The 1.20.4 images are still in each node's containerd cache (they are running now), so
  a rollback does not wait on the registry.

### 5.4 Cost

Rollback is another full agent roll with the same per-node blips, and the same
dual-announcer window in reverse. Pull it for a real regression: a crash-loop, a dark VIP,
§4.4b new<15 after GC, or a failed §4 gate whose baseline passed. Never pull it for a
transient blip during the roll.

---

## 6) Interference notes

- **CURRENTLY NOT RUNNABLE: etcd gate.** Premise `etcd-leader-changes-24h-below-6` read
  6.0 on 2026-11-18 and **11.0 on 2026-11-27** (worst member; findings F-33873912/F-6938f5a1:
  leader churn, getting worse, not better). The plan is correct to refuse. Rolling the CNI on the three etcd nodes while etcd flaps risks quorum loss.
  Schedule it, but expect the premise to decide GO on the day. Do not override it without
  an explicit operator decision recorded in the close-out.
- **Attended + solo, both hard.** `exclusive: true` keeps every other plan out of the slot
  in both directions, and `autonomy_override: human-gated` keeps it out of `nightly`. Slot:
  **sun-attended** (180 budget) or an operator-triggered **on-demand NOW run**, which is
  how 1.20.2 and 1.20.4 ran. **Not sat-attended**: 90 > 70 usable. Taken Sundays at
  authoring: 11-22 `longhorn-1.13.0` (exclusive; listed), 11-29 `redis-fleet-8.10.3`,
  12-13 `flux-oci-chart-sources` (listed), 12-20 `postgres-digest-refresh-2026-11`. First
  free Sunday: **2026-12-06**. `talos-linux-1.14.6` (unwindowed, depends on longhorn) must
  not share a night with this, and should follow a clean cilium run rather than precede
  it.
- **Reciprocity owed.** None of the `conflicts_with` plans lists `cilium-1.20.5` (it did
  not exist; their 1.20.4 refs were pruned 2026-10-25). `exclusive` makes that
  non-blocking for scheduling. Owners of `talos-linux-1.14.6`,
  `kube-prometheus-stack-93.3.0`, `envoy-gateway-1.10.0` and `coredns-1.50.5` should add
  the back-reference.
- **The 1.20.5-specific blip: dual L2 announcers mid-roll** (§1.4). While the roll is in
  progress, every VIP is answered by one 1.20.4 and one 1.20.5 node. It is functional on
  eTP=Cluster + Maglev, but long-lived TCP to VIPs (mosquitto .15, HA .24 websockets, MA
  .29 streams, Plex .30) may reset once when a client's ARP entry flips. UniFi may log a
  duplicate-IP event for VLAN 55 VIPs during the window. It is expected; do not
  investigate it unless it persists after §4.4b passes. The window is about 25 min;
  do not stretch it.
- **Blip profile otherwise** is the same as 1.20.4. Established flows survive, and new-flow
  setup and policy updates pause for seconds per node. CI pods under the 6 toFQDNs CNPs may
  lose DNS for the restart duration on their node (on 1.20.4 the shutdown-path DNS fix is
  already in the outgoing agent, so this is shorter than on the 1.20.2 → 1.20.4 roll).
- **Step 0 ordering.** Take every §2 baseline after Step 0 settles.
- **Monitoring is the instrument.** §4.2 reads Prometheus over the datapath being changed,
  which is why `kube-prometheus-stack-93.3.0` and `otel-operator-0.27.2` are in
  `conflicts_with`.
- **Upstream pre-flight DaemonSet deliberately not used**: it would be a second Helm release
  outside Flux. The node-level pre-pull (§2p) covers its value.
- **Repo correction noted (not planned around):** the retired 1.20.4 plan's §3.2/§3.4a
  assumed `kubectl wait hr` works under OnDelete. It does not (retire commit `3505ff89`).
  This plan fixes it with `disableWait` in §3.4a. Any future CNI plan derived from the
  1.20.4 text must take the fix from here, not from git history.
