---
plan_id: coredns-1.48.2
component: coredns
pr: 220                               # Renovate #220 = HelmRelease 1.47.0 -> 1.48.2. Its twin #221 bumps the
                                      # SAME chart in kubernetes/bootstrap/apps/helmfile.yaml. Both are
                                      # policy-held (`*coredns*` deny rule). They are NOT merged by this plan:
                                      # §3 makes one commit whose HelmRelease and helmfile hunks are
                                      # byte-identical to both PRs (same git blob ids, measured 2026-10-05) plus
                                      # the pin drop, so Renovate auto-closes both as already applied.
kind: chart
current: "chart 1.47.0 (appVersion 1.14.6) + helm-values image.tag pin 1.14.7"
target: "1.48.2"                      # chart 1.48.2, appVersion 1.14.7 -> pin DROPPED, chart owns the tag again
update_type: minor                    # chart minor (1.47 -> 1.48); image unchanged (1.14.7 -> 1.14.7)
risk: medium                          # LOW probability: rendered diff = labels + checksum + four explicit
                                      # securityContext fields that equal the pods' effective state today
                                      # (re-measured 2026-10-05, §1). Cluster-wide IMPACT if wrong, and a DNS
                                      # failure disables its own GitOps revert (source-controller resolves
                                      # github.com through CoreDNS) -> §5.3.
est_duration_min: 35                  # §2 10 + §3 5 + Flux pickup/roll ~5 + §4 10 (incl. 5 min rate window) + slack 5
needs_reboot: false
exclusive: false
touches:
  namespaces: [kube-system]
  resources:
    - helmrelease/kube-system/coredns                   # chart 1.47.0 -> 1.48.2
    - deployment/kube-system/coredns                    # 2 replicas, RollingUpdate maxUnavailable 1 / maxSurge 25%,
                                                        # lameduck 5s, required anti-affinity on control-plane nodes.
                                                        # No PDB exists or is rendered (chart 1.48.2's new PDB is for
                                                        # the autoscaler only, which we do not enable).
    - configmap/kube-system/coredns                     # label only; Corefile must be byte-identical
    - configmap/kube-system/coredns-helm-values-<hash>  # values edit => new generated name; old one ORPHANED
                                                        # (ks prune: false) - harmless, and a revert re-points to it
    - service/kube-system/kube-dns                      # label only (10.96.0.10 unchanged)
    - kubernetes/apps/kube-system/coredns/app/helmrelease.yaml
    - kubernetes/apps/kube-system/coredns/app/helm-values.yaml
    - kubernetes/bootstrap/apps/helmfile.yaml           # bootstrap-only pin (Renovate #221); no live object reads it
  shared:
    - dns/coredns                     # cluster DNS for every pod; the ${SECRET_DOMAIN} block forwards to
                                      # k8s-gateway 192.168.55.101, `.` forwards to Talos hostDNS 169.254.116.108
    - monitoring                      # §4 reads Prometheus + blackbox (read-only; the instrument is shared)
depends_on: []
conflicts_with:
  - flux-distribution-2.9.6           # 2026-10-05 review: exclusive, upgrades the Flux controllers = this plan's §5 revert path
  # Every open (non-terminal) plan whose execution or verification touches kube-system DNS, the
  # HR's apply/revert path, or the Prometheus/blackbox instrument §4 reads. Plan set re-read 2026-10-05.
  - chart-patches-coredns-reloader-blackbox   # now blackbox-only (coredns carved out 2026-10-05), but it rolls
                                              # prometheus-blackbox-exporter = the pod §2.1/§4 dnsmatrix execs
                                              # into and the probe_success instrument. Never the same window.
  - talos-linux-1.14.2                # exclusive node roll; reschedules both CoreDNS pods
  - flux-reconciler-impersonation     # exclusive; changes how helm-controller applies this HR
  - flux-fleet-0.60.0                 # upgrades source/helm-controller = the §5 revert path
  - flux-oci-chart-sources            # moves HelmRepository sources incl. coredns, declares dns-internal
  - helm-drift-detection              # adds driftDetection to every HR incl. this one
  - kube-prometheus-stack-91.9.0      # exclusive; restarts the Prometheus §4 reads (rule 4: same-night kps)
  - envoy-proxy-config-distroless-v1.39.2   # its §4 reads probe_success + resolves through CoreDNS; it lists coredns-1.48.1
  - external-dns-1.23.0               # DNS-plane change; its verification resolves names
  - app-template-5.2.1                # rolls ~78 workloads whose readiness resolves through CoreDNS
  - mariadb-28.1.1                    # tenants re-resolve the DB service on reconnect; lists coredns-1.48.1
  - penpot-chart-1.10.0               # its nginx resolver moves to cluster DNS; gate resolves via CoreDNS
  - redis-fleet-8.10.2                # consumers re-resolve on reconnect
  - nextcloud-fleet-35.0.1            # appstore downloads resolve through CoreDNS
  - edot-collector-0.162.0            # its ES exporters resolve through CoreDNS
  - unpoller-5.4.0                    # its §4.6 InfluxDB write/read resolves through CoreDNS
  # NOT listed, checked 2026-10-05: reloader-2.2.18 (kube-system, but no DNS surface; coredns carries no
  # reloader annotation), descheduler-0.37.0 (kube-system CronJob 04:00 - see §6), multus-macvlan-foundation
  # (status reference), oc8-install (superseded).
capability_change: false              # same image coredns/coredns:1.14.7 (identical digest), byte-identical
                                      # Corefile; the new securityContext fields (runAsNonRoot, uid/gid 65532,
                                      # seccomp RuntimeDefault) equal what the pods already run as (image
                                      # User=65532:65532, kubelet seccompDefault=true) - measured, §1
rollback_class: git-revert
autonomy_override: human-gated        # `dns` is in SHARED_INFRA_FLOOR anyway; §5.3 break-glass needs a human
security_ref: null
finding_refs:
  - F-7c2b93bc                        # coredns: chart 1.47.0 -> 1.48.2 (version finding, PLAN lane)
  - F-d4a234b4                        # "coredns-1.48.1 targets a superseded chart; re-target to 1.48.2 and land
                                      # Renovate #220 + #221 together" - this plan is that re-target
                                      # (F-3893caaf, the old 1.47.1 row, is RESOLVED since 2026-10-01; not carried)
premises:
  # All read-only single commands. Values measured 2026-10-05.
  - id: coredns-image-pinned-1-14-7
    why: >-
      §4 asserts the image does NOT change when the pin is dropped (chart 1.48.2 appVersion = 1.14.7).
      If the live image is not 1.14.7, that gate is wrong. Prints a different string and fails.
    run: kubectl get deploy -n kube-system coredns -o jsonpath='{.spec.template.spec.containers[0].image} {.spec.replicas} {.status.readyReplicas}'
    expect_exact: coredns/coredns:1.14.7 2 2
  - id: coredns-hr-chart
    why: >-
      HelmRelease must be Ready on 1.47.0; a failed/in-flight release, or a Renovate PR merged behind the
      plan's back (1.48.2 already live), makes §3's anchor and the §5 rollback target wrong.
    run: kubectl get helmrelease -n kube-system coredns -o jsonpath='{.spec.chart.spec.version} {.status.lastAttemptedRevision} {.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: 1.47.0 1.47.0 True
  - id: dns-probes-exist
    why: >-
      §4 reads probe_success{probe_class="http"} from these Probe CRs; if renamed/removed the gate reads empty.
    run: kubectl get probe -n monitoring http-ingress-internal http-ingress-external http-vaultwarden -o name
    expect_matches: "(?s)http-ingress-internal.*http-ingress-external.*http-vaultwarden"
  - id: blackbox-exec-target
    why: >-
      §2.1/§4 dnsmatrix execs nslookup inside this Deployment; if it is absent or not 1/1 the harness
      cannot run and every DNS gate reads empty.
    run: kubectl get deploy -n monitoring prometheus-blackbox-exporter -o jsonpath='{.status.readyReplicas}/{.spec.replicas}'
    expect_exact: 1/1
review: ready-for-go@2026-10-05   # plan-reviewer 2026-10-05: ready-for-go, 0 blocking; nonblocking fixes (test -s guard, 2-Running-pods precondition, flux-distribution-2.9.6 conflict) applied by coordinator
status: vetted
window: "sat-attended:2026-10-17"   # scheduled 2026-10-05 (operator "plan all and time them"): HUMAN-GATED -> operator GO; alone in the slot; after blackbox (nightly 10-10)
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/auto-update.md
  - docs/sops/k8s-gateway-dns.md
  - docs/sops/monitoring.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-10-05"
---

# coredns chart 1.47.0 -> 1.48.2, drop the image.tag pin (supersedes coredns-1.48.1)

## 1. Summary & why held

**What changes:** the CoreDNS HelmRelease moves from chart 1.47.0 to 1.48.2. The
`image.tag: "1.14.7"` override in `helm-values.yaml` is removed. The bootstrap helmfile's
coredns pin moves 1.47.0 -> 1.48.2 in the same commit. CoreDNS keeps running
**coredns/coredns:1.14.7**. After this change the chart sets that tag, not our override.

**Supersedes `coredns-1.48.1`** (draft, never reviewed or executed). Upstream published 1.48.2
on 2026-10-01; Renovate opened #220 (HelmRelease) and #221 (bootstrap helmfile), both held by
the `*coredns*` deny rule. Finding `F-d4a234b4` asked for this re-target.

**Why held:** the `*coredns*` deny rule in `runbooks/auto-update-policy.yaml` says "CLUSTER DNS,
and currently image-tag-pinned AHEAD of the chart". On 2026-08-19 the image was pinned to 1.14.7
because chart 1.47.0 shipped appVersion 1.14.6. The chart template reads
`.Values.image.tag | default .Chart.AppVersion`, so the pin would win over every later chart.

**Upstream evidence (primary sources, re-read 2026-10-05):**
- `helm show chart oci://ghcr.io/coredns/charts/coredns --version 1.48.2` → `version: 1.48.2`,
  `appVersion: 1.14.7` (1.47.0 → 1.14.6, 1.48.1 → 1.14.7). Flux's `HelmRepository/coredns` is
  `type: oci`, `oci://ghcr.io/coredns/charts`, so that is the artifact Flux pulls.
- **1.48.1 → 1.48.2** (`coredns/helm` compare `coredns-1.48.1...coredns-1.48.2`, PR #276): 3 commits,
  "feat: add optional autoscaler replicas and disruption budget". Files touched:
  `templates/deployment-autoscaler.yaml`, a NEW `templates/poddisruptionbudget-autoscaler.yaml`,
  `values.yaml` (+8, new opt-in keys), README, tests. The artifacthub change note reads "Add
  optional replica count and PodDisruptionBudget for the cluster-proportional-autoscaler". We do
  not enable the autoscaler, so nothing new renders (confirmed by the render diff below: no
  `PodDisruptionBudget` kind appears).
- **1.47.0 → 1.48.1** (carried over from the 1.48.1 plan, still true): `ce952df` "Bump to CoreDNS
  1.14.7" (appVersion only); `eb4ce1a` "Run CoreDNS as the image's non-root user by default"
  (chart 1.48.0) adds container securityContext defaults `runAsNonRoot: true`,
  `runAsUser: 65532`, `runAsGroup: 65532`, `seccompProfile: RuntimeDefault`. Upstream's reason:
  the image "has run as the distroless nonroot user, uid and gid 65532, since 1.11.0, with
  cap_net_bind_service on the binary so it binds port 53 … the image pins the numeric ids since
  coredns/coredns#8316, released in 1.14.7". Three further commits are autoscaler-only.
- **The pin can be dropped.** 1.48.2's appVersion 1.14.7 equals the pinned tag.

**Rendered diff with OUR values** (`helm template` of 1.47.0+pin vs 1.48.2 without pin,
`${SECRET_DOMAIN}` substituted, helm v3.22.0, 2026-10-05). Rendered kinds are identical in both
(ClusterRole, ClusterRoleBinding, ConfigMap, Deployment, Service, ServiceAccount — no PDB).
Only three kinds of change appear:
- 6× `helm.sh/chart` labels (`coredns-1.47.0` → `coredns-1.48.2`).
- The pod `checksum/config`. It changes because the hashed ConfigMap carries the chart label;
  the Corefile is identical (sha256 of the rendered Corefile is the same in both renders).
- The four securityContext lines above.
Further: 1.48.2 with the pin and 1.48.2 without it render **byte-identically** (empty diff), and
1.48.1 → 1.48.2 differs only in labels + checksum. Image line in the 1.48.2 render:
`coredns/coredns:1.14.7`.

**Why those four lines change nothing at runtime** (measured 2026-10-01, re-confirmed 2026-10-05:
live pods show `runAsUser <none>` today and imageID unchanged):
- The coredns:1.14.7 image config has `User=65532:65532`, so the process already runs as 65532.
- The kubelet has `seccompDefault: true`, so the pods already run under RuntimeDefault.
- `kube-system` enforces PSA `privileged`, so admission has no new failure mode.
- `NET_BIND_SERVICE` add and `drop: ALL` are unchanged.

**Bootstrap helmfile (new vs the 1.48.1 plan):** `kubernetes/bootstrap/apps/helmfile.yaml`
installs coredns from the SAME `helm-values.yaml`. If the pin is dropped while the helmfile stays
on 1.47.0, a cluster re-bootstrap would render appVersion **1.14.6** — silently undoing the
1.14.7 bump and its `max_connect_attempts` semantics. So the helmfile moves to 1.48.2 in the same
commit (that is exactly Renovate #221's hunk). It has no live effect.

**Net effect:** one rolling restart of CoreDNS (2 replicas, `maxUnavailable: 1`, `lameduck 5s`,
one per control-plane node by required anti-affinity). Image, Corefile and effective
uid/seccomp all stay the same.

**Verdict:** the hold is close to a false positive in substance. It is weighted `medium` only
because of blast radius: a CoreDNS that is Ready but answering wrongly is invisible to Flux, and
it breaks the GitOps revert (§5.3).

**Deny rule:** do NOT edit `runbooks/auto-update-policy.yaml` in this window. The rule's removal
condition ("a chart ships appVersion >= the pinned tag AND the image.tag override is dropped") is
met by this plan, but the same rule also says coredns "should never bump unattended regardless of
the pin". Keep / narrow / remove is an operator decision (flagged in the planner report). Its
reason text ("chart 1.47.0 is the newest published") is stale after this plan either way.

## 2. Pre-checks (all read-only; abort on any failure)

```bash
cd /Users/mu/code/cberg-home-nextgen
.venv/bin/python3 runbooks/plan-premises.py coredns-1.48.2                 # all PASS
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'                    # header only
flux get helmreleases -A   | awk 'NR==1 || $5 != "True"'                    # header only
git status --short -- kubernetes/apps/kube-system/coredns kubernetes/bootstrap/apps/helmfile.yaml   # empty
flux get sources git -n flux-system flux-system ; git rev-parse --short origin/main   # same revision (Step 0 settled)
gh pr view 220 --json state -q .state ; gh pr view 221 --json state -q .state         # OPEN OPEN (if MERGED: STOP, re-plan)
helm history coredns -n kube-system --max 3                                 # note the DEPLOYED revision (10 on 2026-10-05) for §5.3
mkdir -p /private/tmp/coredns-1.48.2
```

**2.1 DNS baseline (record it; §4 compares against it).** Lookups run from inside the blackbox
pod. Pod IPs are not routable from the Mac. busybox `nslookup` exits 1 on NXDOMAIN, so the
fourth name is the negative control (re-confirmed 2026-10-05: cluster name `rc=0 ans=10.96.0.1`,
negative control `rc=1 ans=NONE`).
```bash
D=$(kubectl -n flux-system get secret cluster-secrets -o jsonpath='{.data.SECRET_DOMAIN}' | base64 -d)
dnsmatrix() {
  for ip in $(kubectl -n kube-system get pods -l k8s-app=kube-dns -o jsonpath='{.items[*].status.podIP}'); do
    for n in kubernetes.default.svc.cluster.local "sweep.$D" github.com does-not-exist-zz9.svc.cluster.local; do
      out=$(kubectl -n monitoring exec deploy/prometheus-blackbox-exporter -- nslookup -type=A "$n" "$ip" 2>&1); rc=$?
      a=$(printf '%s\n' "$out" | awk '/^Name:/{f=1} f&&/^Address/{print $2}' | head -1)
      echo "$ip rc=$rc ans=${a:-NONE} name=${n%%.$D}"
    done
  done
}
dnsmatrix | tee /private/tmp/coredns-1.48.2/dnsmatrix.pre
```
Expected (2 pod IPs × 4 names, 8 lines):
- `kubernetes.default.svc.cluster.local` → `rc=0 ans=10.96.0.1`
- `sweep` → `rc=0 ans=192.168.55.103` (`${SECRET_DOMAIN}` block → forward to k8s-gateway .101)
- `github.com` → `rc=0` with a public IP (`.` block → Talos hostDNS)
- `does-not-exist-zz9…` → `rc=1 ans=NONE`

**Negative control:** if the last line ever reads `rc=0`, the harness cannot detect a failure.
STOP. Do not hold the IP list in a scalar: `for ip in $(…)` word-splits correctly under zsh, and
a scalar does not.

**2.2 Corefile + image-digest baseline:**
```bash
kubectl -n kube-system get cm coredns -o jsonpath='{.data.Corefile}' > /private/tmp/coredns-1.48.2/corefile.txt
test -s /private/tmp/coredns-1.48.2/corefile.txt || echo 'ABORT: empty Corefile read'
shasum -a 256 < /private/tmp/coredns-1.48.2/corefile.txt | tee /private/tmp/coredns-1.48.2/corefile.pre
# 2026-10-05: cf7ccdad3e5799e63d642753797489197dbf50db294083622bb9578fde54063d
kubectl -n kube-system get pods -l k8s-app=kube-dns -o jsonpath='{range .items[*]}{.status.containerStatuses[0].imageID}{"\n"}{end}' | sort -u | tee /private/tmp/coredns-1.48.2/imageid.pre
# 1 line: docker.io/coredns/coredns@sha256:7efd3c635b03efd68c4e8398fc45f0d993d0e9ab016f72c1cefb0fd6d01aa286 (2026-10-05)
```

**2.3 Prometheus baseline.** The port-forward stays up for §4.
```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
q(){ curl -s --get http://localhost:19090/api/v1/query --data-urlencode "query=$1" \
  | python3 -c "import sys,json; r=json.load(sys.stdin)['data']['result']; print(len(r)); [print(' ',{k:v for k,v in x['metric'].items() if k in ('pod','version','rcode','to','instance')},x['value'][1]) for x in r]"; }
q 'coredns_build_info'                                                  # 2 series, version="1.14.7"
q 'sum by (rcode)(rate(coredns_dns_responses_total[10m]))'              # NOERROR + NXDOMAIN > 0; record SERVFAIL
q 'sum by (to,rcode)(rate(coredns_proxy_request_duration_seconds_count[10m]))'   # to=192.168.55.101:53 and to=169.254.116.108:53 both NOERROR > 0
q 'ALERTS{alertstate="firing",alertname=~"InternalDns.*|IngressProbe.*|Blackbox.*"}'   # 0
```

## 3. Steps (one commit, three files)

The edit was dry-tested on scratch copies of all three files with macOS python3 on 2026-10-05.
- It checks ALL three anchors before writing ANY file (the 1.48.1 plan's script wrote the
  HelmRelease before checking the values anchor; fixed here).
- It produced exactly the diff below; the HelmRelease and helmfile hunks have the same git blob
  ids as Renovate #220 (`9f83cc88f..186653e24`) and #221 (`3753f8c48..40568a6ce`).
- A second run aborts with `ABORT: helmrelease anchor not found exactly once`.

```bash
cd /Users/mu/code/cberg-home-nextgen
F=kubernetes/apps/kube-system/coredns/app/helmrelease.yaml
V=kubernetes/apps/kube-system/coredns/app/helm-values.yaml
B=kubernetes/bootstrap/apps/helmfile.yaml
python3 - "$F" "$V" "$B" <<'EOF'
import re, sys
hr, vals, boot = sys.argv[1:4]
s = open(hr).read()
pat = re.compile(r'^      version: 1\.47\.[01]$', re.M)
if len(pat.findall(s)) != 1: sys.exit("ABORT: helmrelease anchor not found exactly once")
b = open(boot).read()
bpat = re.compile(r'^(    chart: oci://ghcr\.io/coredns/charts/coredns\n    version: )1\.47\.[01]$', re.M)
if len(bpat.findall(b)) != 1: sys.exit("ABORT: bootstrap helmfile coredns anchor not found exactly once")
v = open(vals).read()
blk = re.compile(r'^# Chart 1\.47\.[01] .*\n(?:#.*\n)*?image:\n  tag: "1\.14\.7"\n', re.M)
if len(blk.findall(v)) != 1: sys.exit("ABORT: pin block not found exactly once")
v2 = blk.sub('', v)
if re.search(r'^image:', v2, re.M) or '1.14.7"' in v2: sys.exit("ABORT: a pin survived")
open(hr, 'w').write(pat.sub('      version: 1.48.2', s))
open(boot, 'w').write(bpat.sub(r'\g<1>1.48.2', b))
open(vals, 'w').write(v2)
print("OK")
EOF
git diff -- "$F" "$V" "$B"
```
Expected diff (verbatim from the dry run):
```
helm-values.yaml:
-# Chart 1.47.0 is the newest published chart and still ships appVersion 1.14.6,
-# so the image is pinned ahead of the chart's tested appVersion. Re-check on
-# every chart bump: once a chart ships >= this appVersion, drop this block and
-# let the chart own the tag again.
-image:
-  tag: "1.14.7"
helmrelease.yaml:
-      version: 1.47.0
+      version: 1.48.2
helmfile.yaml (coredns release):
-    version: 1.47.0
+    version: 1.48.2
```
If the script prints `ABORT…`, stop. Do not improvise an edit: `git checkout -- "$F" "$V" "$B"`
and investigate (a merged #220/#221 is the likely cause).

Before committing, confirm the render (helm 3 is on PATH via mise). The output must be exactly
one line, `coredns/coredns:1.14.7` (dry-run output 2026-10-05). Any other tag means the chart is
not doing what §1 says. STOP and `git checkout -- "$F" "$V" "$B"`.
```bash
sed 's/\${SECRET_DOMAIN}/example.test/' "$V" > /private/tmp/coredns-1.48.2/vals.yaml
helm template coredns oci://ghcr.io/coredns/charts/coredns --version 1.48.2 -n kube-system \
  -f /private/tmp/coredns-1.48.2/vals.yaml 2>/dev/null | grep -E '^[[:space:]]*image:' | tr -d ' "' | sed 's/^image://'
```

Commit (shared worktree: `--only`, then verify subject and file list BEFORE push):
```bash
git commit --only "$F" "$V" "$B" -m "feat(kube-system): coredns chart 1.47.0 -> 1.48.2, drop image pin (chart appVersion now 1.14.7); supersedes Renovate #220 #221" \
  -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
git log -1 --format=%s          # must be the subject above, else amend before push
git show --stat HEAD            # exactly the three files
git push
```
Flux picks the change up through the push webhook. No manual reconcile. Do NOT merge or close
#220/#221 by hand: once main carries 1.48.2, Renovate closes them on its next run. Watch the roll:
```bash
kubectl -n kube-system get pods -l k8s-app=kube-dns -o wide -w
```
Press Ctrl-C once 2/2 NEW pods are Ready on 2 distinct nodes (≤10 min). If the HR does not move
within 10 min, check the webhook and `flux get sources git` before anything else.

## 4. Verification (any FAIL → §5)

- **Release:**
  ```bash
  kubectl get hr -n kube-system coredns -o jsonpath='{.spec.chart.spec.version} {.status.lastAttemptedRevision} {.status.conditions[?(@.type=="Ready")].status}'
  ```
  → `1.48.2 1.48.2 True`. `helm history coredns -n kube-system --max 2` shows the new revision
  `deployed` on `coredns-1.48.2` with APP VERSION 1.14.7. If any revision after it reads
  `rolled back`, helm's own remediation fired. FAIL.
- **Pods and image:**
  ```bash
  kubectl -n kube-system get pods -l k8s-app=kube-dns -o 'custom-columns=N:.metadata.name,NODE:.spec.nodeName,IMG:.spec.containers[0].image,READY:.status.containerStatuses[0].ready,RS:.status.containerStatuses[0].restartCount,UID:.spec.containers[0].securityContext.runAsUser,SECCOMP:.spec.containers[0].securityContext.seccompProfile.type'
  ```
  → 2 pods with new names, on 2 distinct nodes, `coredns/coredns:1.14.7`, READY true, RS 0,
  UID 65532, SECCOMP RuntimeDefault.
  - A `1.14.6` image means the chart default won without the pin, which contradicts §1. FAIL.
  - `<none>` in UID (today's value) means 1.48.x was not rendered. FAIL.
- CONTENTS ASSERTION: the running image is byte-identical to the pre-change one. Measured — only after the roll shows exactly 2 Running kube-dns pods (no Terminating pod left; lameduck 5 s), which also gates the 8-line dnsmatrix count — by first asserting `test -s /private/tmp/coredns-1.48.2/imageid.pre` (an empty baseline is a FAIL, never a silent pass), then re-running the §2.2 `imageID` command and `diff`-ing it against `/private/tmp/coredns-1.48.2/imageid.pre` (silent = pass). A different digest means a different image even under the same tag. FAIL.
- CONTENTS ASSERTION: the served Corefile is byte-identical. Measured by `kubectl -n kube-system get cm coredns -o jsonpath='{.data.Corefile}' | shasum -a 256 | diff - /private/tmp/coredns-1.48.2/corefile.pre` (silent = pass). The render diff says the Corefile does not change, so any difference means the chart altered DNS config (for example `max_connect_attempts 6` was lost). FAIL.
- CONTENTS ASSERTION: every NEW replica answers all three name classes correctly and still fails the negative control. Measured by `dnsmatrix | tee /private/tmp/coredns-1.48.2/dnsmatrix.post` (§2.1 function, against the NEW pod IPs). Required: exactly 8 lines. Per IP: cluster name `rc=0 ans=10.96.0.1`, `sweep` `rc=0 ans=192.168.55.103`, `github.com` `rc=0` with an IP, negative control `rc=1 ans=NONE`. Any `rc≠0` on the first three, `rc=0` on the fourth, or fewer than 8 lines is a FAIL. The pod IPs differ from the baseline, so compare the `ans=` and `rc=` columns, not the whole line.
- CONTROL: metric coredns_build_info — exactly 2 series, both `version="1.14.7"`, with the NEW pod names as `pod` labels. 0 series means the scrape broke, so nothing else in this list can be trusted. FAIL.
- CONTROL: metric coredns_dns_responses_total — `sum by (rcode)(rate(coredns_dns_responses_total[5m]))`, read 5 min after the roll. NOERROR must be > 0 (a floor that proves traffic is served). SERVFAIL must not be above the §2.3 baseline. A seccomp or uid denial on bind or upstream sockets shows up here as SERVFAIL or as no NOERROR.
- CONTROL: metric coredns_proxy_request_duration_seconds_count — `sum by (to,rcode)(rate(coredns_proxy_request_duration_seconds_count[5m]))`. Both `to="192.168.55.101:53"` and `to="169.254.116.108:53"` must show NOERROR > 0, which proves both forward blocks still reach their upstreams.
- CONTROL: metric probe_success — `min_over_time(probe_success{probe_class="http"}[5m])` = 1 for the 3 http probes (ingress-internal, ingress-external, vaultwarden). They resolve their hostnames through CoreDNS inside the blackbox pod, so they are the Prometheus-side end-to-end check. The two `dns_*` probes target k8s-gateway .101 DIRECTLY and stay green even if CoreDNS is dead, so they are NOT a CoreDNS gate.
- CONTROL: alertname IngressProbeFailing — not firing.
- CONTROL: alertname InternalDnsResolutionFailing — not firing. This alert covers k8s-gateway, not CoreDNS. It is listed so a coincident k8s-gateway failure is not misread as caused by this plan.
- **Rollback-path health:** wait ≥ 2 min after the roll completes. Then
  `flux get sources git -n flux-system flux-system` must show READY `True`. source-controller
  resolves github.com through CoreDNS, so this proves the §5 revert path still works.

Finally: `kill $PF`.

## 5. Rollback

**5.1 GitOps revert (default):**
```bash
cd /Users/mu/code/cberg-home-nextgen
SHA=$(git log -1 --format=%h -- kubernetes/apps/kube-system/coredns/app/helmrelease.yaml)
git show --stat "$SHA"          # confirm it is the coredns 1.48.2 commit (3 files)
git revert --no-edit "$SHA" && git log -1 --format=%s && git show --stat HEAD && git push
```
What happens:
- The HR returns to chart 1.47.0, the pin comes back, the helmfile returns to 1.47.0.
- The old generated values ConfigMap still exists (`prune: false`).
- The pods roll again.
- Renovate will re-open its 1.48.2 PRs later; that is expected.

**5.2 Confirm the cluster is back:** re-run §4 against the pre-plan state:
- HR `1.47.0 1.47.0 True`.
- Pods `coredns/coredns:1.14.7` with UID `<none>`. The 1.47 chart sets no `runAsUser`, so
  `<none>` proves the old render is back.
- imageID = `imageid.pre`, Corefile hash = `corefile.pre`.
- `dnsmatrix` = baseline.

**5.3 Break-glass, only if CoreDNS is serving failures and the revert cannot land.** The GitOps
revert needs source-controller to resolve github.com THROUGH CoreDNS. Helm's own
`upgrade.remediation.strategy: rollback` covers a failed upgrade. It does not cover an upgrade
that is Ready but answers wrongly. If §4 fails AND `flux get sources git` shows no fetch of the
revert revision within 5 min of the push, an operator (never unattended) runs:
```bash
helm history coredns -n kube-system --max 5     # find the last coredns-1.47.0 revision (10 on 2026-10-05 if nothing else ran)
flux suspend helmrelease coredns -n kube-system
helm rollback coredns <REV> -n kube-system --wait
```
Then push the §5.1 revert. Once `flux get sources git` shows the revert revision, run
`flux resume helmrelease coredns -n kube-system`. This is the plan's only direct cluster mutation,
and it is why the plan is attended.

## 6. Interference notes

- **Not nightly-unattended.** `touches.shared` carries `dns/coredns`, which derives HUMAN-GATED
  through SHARED_INFRA_FLOOR, and `autonomy_override: human-gated` states it explicitly. The
  reason is not the diff. It is §5.3: a DNS failure at 03:30 disables the GitOps revert and needs
  a human with `helm`. 35 min fits a `sat-attended` slot.
- **Run it alone, or last in its window.** No other plan may verify through DNS or Prometheus
  during the ~2-min roll. That is why every DNS-verifying open plan is in `conflicts_with`. For
  the exclusive plans (talos-linux-1.14.2, flux-reconciler-impersonation,
  kube-prometheus-stack-91.9.0) the entry is belt and braces.
- **Blackbox plan:** `chart-patches-coredns-reloader-blackbox` no longer carries coredns (carved out
  2026-10-05 in favour of this plan). It still rolls the blackbox pod that §2.1/§4 exec into and
  that produces `probe_success`, so the two stay in different windows (or blackbox strictly first
  with its §4 green before §2 here starts).
- **Descheduler:** `kube-system/descheduler` CronJob runs at 04:00 and CoreDNS has no
  `priorityClassName`, so its pods are evictable by LowNodeUtilization. Do not run §3 within
  ~10 min of 04:00 (a descheduler eviction mid-roll would read as a plan failure).
- **Superseded plan refs (repo correction, not done here):** `envoy-proxy-config-distroless-v1.39.2`,
  `external-dns-1.23.0`, `flux-fleet-0.60.0`, `mariadb-28.1.1`, `penpot-chart-1.10.0` and
  `unpoller-5.4.0` list `coredns-1.48.1` in `conflicts_with`; that plan is now `superseded` and drops
  out of scheduling, so those guards no longer bind. They should be re-pointed to `coredns-1.48.2`.
- **Renovate:** after the pin is dropped, CoreDNS image updates arrive only through chart bumps.
  The `*coredns*` deny rule keeps sending those to the PLAN lane, which is intended. Do not change
  the rule in this window (§1).
- Retire this file in the commit that records execution. Close the findings with
  `runbooks/policy-cli.py finding close F-7c2b93bc --commit <sha>` and
  `runbooks/policy-cli.py finding close F-d4a234b4 --commit <sha>`.
