---
plan_id: coredns-1.48.1
component: coredns
pr: null                              # no Renovate PR (chart bump held by the `*coredns*` deny rule; coverage lane)
kind: chart
current: "chart 1.47.0 (appVersion 1.14.6) + helm-values image.tag pin 1.14.7"
target: "1.48.1"                      # chart 1.48.1, appVersion 1.14.7 -> pin DROPPED, chart owns the tag again
update_type: minor                    # chart minor (1.47 -> 1.48); image unchanged (1.14.7 -> 1.14.7)
risk: medium                          # LOW probability: rendered diff = labels + checksum + four explicit
                                      # securityContext fields that equal the pods' effective state today
                                      # (measured, §1). Cluster-wide IMPACT if wrong, and a DNS failure
                                      # disables its own GitOps revert (source-controller resolves
                                      # github.com through CoreDNS) -> §5.3. Same weighting as the sibling
                                      # chart-patches plan.
est_duration_min: 35                  # §2 10 + §3 5 + Flux pickup/roll ~5 + §4 10 (incl. 5 min rate window) + slack 5
needs_reboot: false
exclusive: false
touches:
  namespaces: [kube-system]
  resources:
    - helmrelease/kube-system/coredns                   # chart 1.47.0 -> 1.48.1
    - deployment/kube-system/coredns                    # 2 replicas, RollingUpdate maxUnavailable 1, lameduck 5s
    - configmap/kube-system/coredns                     # label only; Corefile must be byte-identical
    - configmap/kube-system/coredns-helm-values-<hash>  # values edit => new generated name; old one ORPHANED
                                                        # (ks prune: false) - harmless, and a revert re-points to it
    - service/kube-system/kube-dns                      # label only (10.96.0.10 unchanged)
    - kubernetes/apps/kube-system/coredns/app/helmrelease.yaml
    - kubernetes/apps/kube-system/coredns/app/helm-values.yaml
  shared:
    - dns/coredns                     # cluster DNS for every pod; the ${SECRET_DOMAIN} block forwards to
                                      # k8s-gateway 192.168.55.101, `.` forwards to Talos hostDNS 169.254.116.108
    - monitoring                      # §4 reads Prometheus + blackbox (read-only; the instrument is shared)
depends_on: []
conflicts_with:
  - chart-patches-coredns-reloader-blackbox   # its item C bumps THE SAME HelmRelease to 1.47.1 (pin kept);
                                              # this plan supersedes that item. Never the same window.
                                              # §3 tolerates either order (anchor accepts 1.47.0 or 1.47.1).
  - talos-linux-1.14.2                # exclusive node roll; reschedules both CoreDNS pods and touches coredns
  - talconfig-multidoc-migration      # exclusive; rewrites node-resolver/hostDNS = CoreDNS's `.` upstream
  - flux-reconciler-impersonation     # exclusive; changes how helm-controller applies this HR
  - flux-fleet-0.60.0                 # upgrades source/helm-controller = the §5 revert path
  - flux-oci-chart-sources            # moves HelmRepository sources incl. coredns, declares dns-internal
  - helm-drift-detection              # adds driftDetection to every HR incl. this one
  # - envoy-gateway-1.9.2 (RESOLVED 2026-10-04: executed + retired 418faa1e (now:2026-10-03); dead ref removed per the dead-ref convention)
    # declares shared dns; its gates resolve through CoreDNS
  - external-dns-1.23.0               # DNS-plane change; its verification resolves names
  - app-template-5.2.1                # rolls ~78 workloads whose readiness resolves through CoreDNS
  # - uptime-kuma-2.5.5-slim-rootless (RESOLVED 2026-10-04: executed sat-attended:2026-10-03 + retired d60d14f7; dead ref removed per the dead-ref convention)
    # its §4 reads Kuma monitors that resolve via CoreDNS
  # - mariadb-chart-27.3.0 (RESOLVED 2026-10-04: executed + retired 418faa1e (now:2026-10-03); dead ref removed per the dead-ref convention)
  - mariadb-28.1.1  # ADDED 2026-10-04: successor plan (same databases/mariadb HR + mariadb-0 roll); reciprocal -- it already lists this plan
    # tenants re-resolve the DB service on reconnect
  - penpot-chart-1.10.0               # its nginx resolver moves to cluster DNS; gate resolves via CoreDNS
  - redis-fleet-8.10.2                # consumers re-resolve on reconnect
  - nextcloud-fleet-35.0.1            # lists the sibling coredns plan for the same reason
  - edot-collector-0.162.0            # lists the sibling coredns plan (monitoring/DNS gates)
  - unpoller-5.4.0                    # lists the sibling coredns plan
                                      # No kube-prometheus-stack plan is open (91.4.1 executed). If one
                                      # appears it MUST be added here: §4 reads Prometheus.
capability_change: false              # same image coredns/coredns:1.14.7 (identical digest), byte-identical
                                      # Corefile; the new securityContext fields (runAsNonRoot, uid/gid 65532,
                                      # seccomp RuntimeDefault) equal what the pods already run as (image
                                      # User=65532:65532, kubelet seccompDefault=true) - measured, §1
rollback_class: git-revert
autonomy_override: human-gated        # `dns` is in SHARED_INFRA_FLOOR anyway; §5.3 break-glass needs a human
security_ref: null
finding_refs:
  - F-3893caaf                        # coredns chart version finding (filed as 1.47.0 -> 1.47.1; the chart
                                      # has since moved to 1.48.1 - this plan answers the chart update and
                                      # supersedes the sibling plan's item C). No 1.48.1-titled row existed
                                      # at authoring (`finding list --grep 1.48` -> no rows, 2026-10-01).
premises:
  # All read-only single commands. Values measured 2026-10-01.
  - id: coredns-image-pinned-1-14-7
    why: >-
      §4 asserts the image does NOT change when the pin is dropped (chart 1.48.1 appVersion = 1.14.7).
      If the live image is not 1.14.7, that gate is wrong. Prints a different string and fails.
    run: kubectl get deploy -n kube-system coredns -o jsonpath='{.spec.template.spec.containers[0].image} {.spec.replicas} {.status.readyReplicas}'
    expect_exact: coredns/coredns:1.14.7 2 2
  - id: coredns-hr-chart
    why: >-
      HelmRelease must be Ready on 1.47.0 (or 1.47.1 if the sibling plan's item C ran first); a
      failed/in-flight release makes the §5 rollback target wrong.
    run: kubectl get helmrelease -n kube-system coredns -o jsonpath='{.spec.chart.spec.version} {.status.conditions[?(@.type=="Ready")].status}'
    expect_matches: "^1\\.47\\.[01] True$"
  - id: dns-probes-exist
    why: >-
      §4 reads probe_success{probe_class="http"} from these Probe CRs; if renamed/removed the gate reads empty.
    run: kubectl get probe -n monitoring http-ingress-internal http-ingress-external http-vaultwarden -o name
    expect_matches: "(?s)http-ingress-internal.*http-ingress-external.*http-vaultwarden"
status: draft
window: null
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/auto-update.md
  - docs/sops/k8s-gateway-dns.md
  - docs/sops/monitoring.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-10-01"
---

# coredns chart 1.47.0 -> 1.48.1, drop the image.tag pin

## 1. Summary & why held

**What changes:** the CoreDNS HelmRelease moves from chart 1.47.0 to 1.48.1. The
`image.tag: "1.14.7"` override in `helm-values.yaml` is removed. CoreDNS keeps running
**coredns/coredns:1.14.7**. After this change the chart sets that tag, not our override.

**Why held:** the `*coredns*` deny rule in `runbooks/auto-update-policy.yaml` says "CLUSTER DNS,
and currently image-tag-pinned AHEAD of the chart". On 2026-08-19 the image was pinned to 1.14.7
because chart 1.47.0 shipped appVersion 1.14.6. The chart template reads
`.Values.image.tag | default .Chart.AppVersion`, so the pin would win over every later chart.

**Upstream evidence (primary sources, read 2026-10-01):**
- The chart index (`https://coredns.github.io/helm/index.yaml`) and the `coredns/helm` repo tag
  `coredns-1.48.1` both show `version: 1.48.1`, `appVersion: 1.14.7`, published
  2026-09-29T11:15Z. The artifacthub change note reads "Bump to CoreDNS 1.14.7". Flux pulls the
  chart from `oci://ghcr.io/coredns/charts`, and `helm template … --version 1.48.1` against that
  OCI repo resolves the same chart.
- **The pin can be dropped.** 1.48.1's appVersion 1.14.7 equals the pinned tag. `helm template`
  of 1.47.0 with the pin and 1.48.1 without it both render `image: "coredns/coredns:1.14.7"`.
- The `coredns-1.47.0..coredns-1.48.1` range contains 5 chart commits. Three of them only affect
  the cluster-proportional-autoscaler (`inheritCustomLabels`, a separate selector and labels). We
  do not enable the autoscaler, so they render nothing here. The other two:
  - `ce952df` "Bump to CoreDNS 1.14.7" changes only the appVersion.
  - `eb4ce1a` "Run CoreDNS as the image's non-root user by default" (chart 1.48.0) adds these
    defaults to the container securityContext: `runAsNonRoot: true`, `runAsUser: 65532`,
    `runAsGroup: 65532`, `seccompProfile: RuntimeDefault`. Upstream's reason: the image "has run as
    the distroless nonroot user, uid and gid 65532, since 1.11.0, with cap_net_bind_service on the
    binary so it binds port 53 … the image pins the numeric ids since coredns/coredns#8316, released
    in 1.14.7". This is the only change in the range that affects how the pod runs.

**Rendered diff with OUR values** (`helm template` 1.47.0+pin vs 1.48.1 without pin, 2026-10-01).
Only three kinds of change appear:
- 6× `helm.sh/chart` labels.
- The pod `checksum/config`. It changes because the hashed ConfigMap carries the chart label;
  the Corefile is identical.
- The four securityContext lines above.

**Why those four lines change nothing at runtime** (measured 2026-10-01):
- The coredns:1.14.7 image config (docker.io, amd64) has `User=65532:65532`, so the process
  already runs as 65532.
- The kubelet on the nodes has `seccompDefault: true` (`/configz` on k8s-nuc14-02), so the pods
  already run under RuntimeDefault.
- `kube-system` enforces PSA `privileged`, so admission has no new failure mode.
- `NET_BIND_SERVICE` add and `drop: ALL` are unchanged.

**Net effect:** one rolling restart of CoreDNS (2 replicas, `maxUnavailable: 1`, `lameduck 5s`).
Image, Corefile and effective uid/seccomp all stay the same.

**Verdict:** the hold is close to a false positive in substance. It is weighted `medium` only
because of blast radius. A CoreDNS that is Ready but answering wrongly is invisible to Flux, and
it breaks the GitOps revert (§5.3).

**Relationship to `chart-patches-coredns-reloader-blackbox`:** that vetted plan (window
`sun-attended:2026-11-01`) has an item C that bumps the same HelmRelease to 1.47.1 and keeps the
pin. **This plan supersedes item C.** 1.48.1 contains all of 1.47.1. The two plans are in each
other's `conflicts_with` (this side declared here). The sibling should drop item C and carry only
A+B. That is a repo correction for the sibling's owner and is not done here. If item C still runs
first, §3's anchor accepts `1.47.1` and either form of the comment, so this plan still applies
cleanly.

**Deny rule:** do NOT edit `runbooks/auto-update-policy.yaml` in this window. The rule's own
removal condition is "a chart ships appVersion >= the pinned tag AND the image.tag override is
dropped". This plan meets that condition. But the same rule also says coredns "should never bump
unattended regardless of the pin". Whether to keep, narrow or remove the rule is an operator
decision and is flagged in the planner report. The rule's reason text ("chart 1.47.0 is the
newest published") is stale after this plan either way.

## 2. Pre-checks (all read-only; abort on any failure)

```bash
cd /Users/mu/code/cberg-home-nextgen
.venv/bin/python3 runbooks/plan-premises.py coredns-1.48.1                 # all PASS
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'                    # header only
flux get helmreleases -A   | awk 'NR==1 || $5 != "True"'                    # header only
git status --short -- kubernetes/apps/kube-system/coredns                   # empty (no foreign edits)
flux get sources git -n flux-system flux-system ; git rev-parse --short origin/main   # same revision (Step 0 settled)
helm history coredns -n kube-system --max 3                                 # note the DEPLOYED revision number (10 on 2026-10-01) for §5.3
mkdir -p /private/tmp/coredns-1.48.1
```

**2.1 DNS baseline (record it; §4 compares against it).** Lookups run from inside the blackbox
pod. Pod IPs are not routable from the Mac. busybox `nslookup` exits 1 on NXDOMAIN, so the
fourth name is the negative control.
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
dnsmatrix | tee /private/tmp/coredns-1.48.1/dnsmatrix.pre
```
Expected (measured live 2026-10-01: 2 pod IPs × 4 names, 8 lines):
- `kubernetes.default.svc.cluster.local` → `rc=0 ans=10.96.0.1`
- `sweep` → `rc=0 ans=192.168.55.103` (`${SECRET_DOMAIN}` block → forward to k8s-gateway .101)
- `github.com` → `rc=0` with a public IP (`.` block → Talos hostDNS)
- `does-not-exist-zz9…` → `rc=1 ans=NONE`

**Negative control:** if the last line ever reads `rc=0`, the harness cannot detect a failure.
STOP. Do not hold the IP list in a scalar: `for ip in $(…)` word-splits correctly under zsh, and
a scalar does not.

**2.2 Corefile + image-digest baseline:**
```bash
kubectl -n kube-system get cm coredns -o jsonpath='{.data.Corefile}' > /private/tmp/coredns-1.48.1/corefile.txt
test -s /private/tmp/coredns-1.48.1/corefile.txt || echo 'ABORT: empty Corefile read'
shasum -a 256 < /private/tmp/coredns-1.48.1/corefile.txt | tee /private/tmp/coredns-1.48.1/corefile.pre
kubectl -n kube-system get pods -l k8s-app=kube-dns -o jsonpath='{range .items[*]}{.status.containerStatuses[0].imageID}{"\n"}{end}' | sort -u | tee /private/tmp/coredns-1.48.1/imageid.pre
# 1 line: docker.io/coredns/coredns@sha256:7efd3c635b03efd68c4e8398fc45f0d993d0e9ab016f72c1cefb0fd6d01aa286 (2026-10-01)
```

**2.3 Prometheus baseline.** The port-forward stays up for §4.
```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
q(){ curl -s --get http://localhost:19090/api/v1/query --data-urlencode "query=$1" \
  | python3 -c "import sys,json; r=json.load(sys.stdin)['data']['result']; print(len(r)); [print(' ',{k:v for k,v in x['metric'].items() if k in ('pod','version','rcode','to','instance')},x['value'][1]) for x in r]"; }
q 'coredns_build_info'                                                  # 2 series, version="1.14.7"
q 'sum by (rcode)(rate(coredns_dns_responses_total[10m]))'              # NOERROR + NXDOMAIN > 0; record SERVFAIL (absent on 2026-10-01)
q 'sum by (to,rcode)(rate(coredns_proxy_request_duration_seconds_count[10m]))'   # to=192.168.55.101:53 and to=169.254.116.108:53 both NOERROR > 0
q 'ALERTS{alertstate="firing",alertname=~"InternalDns.*|IngressProbe.*|Blackbox.*"}'   # 0
```

## 3. Steps (one commit)

The edit was dry-tested on scratch copies of both files with macOS python3 on 2026-10-01.
- On today's files it produces exactly the diff below.
- On a copy where the sibling plan's item C had already run (1.47.1 plus its rewritten comment)
  it produces the identical result.
- A second run aborts, because the anchor is gone.

```bash
cd /Users/mu/code/cberg-home-nextgen
F=kubernetes/apps/kube-system/coredns/app/helmrelease.yaml
V=kubernetes/apps/kube-system/coredns/app/helm-values.yaml
python3 - "$F" "$V" <<'EOF'
import re, sys
hr, vals = sys.argv[1], sys.argv[2]
s = open(hr).read()
pat = re.compile(r'^      version: 1\.47\.[01]$', re.M)
if len(pat.findall(s)) != 1: sys.exit("ABORT: helmrelease anchor not found exactly once")
open(hr, 'w').write(pat.sub('      version: 1.48.1', s))
v = open(vals).read()
blk = re.compile(r'^# Chart 1\.47\.[01] .*\n(?:#.*\n)*?image:\n  tag: "1\.14\.7"\n', re.M)
if len(blk.findall(v)) != 1: sys.exit("ABORT: pin block not found exactly once")
v2 = blk.sub('', v)
if 'image:' in v2 or '1.14.7"' in v2: sys.exit("ABORT: a pin survived")
open(vals, 'w').write(v2)
print("OK")
EOF
git diff -- "$F" "$V"
```
Expected diff (verbatim from the dry run):
```
-      version: 1.47.0
+      version: 1.48.1
...
-# Chart 1.47.0 is the newest published chart and still ships appVersion 1.14.6,
-# so the image is pinned ahead of the chart's tested appVersion. Re-check on
-# every chart bump: once a chart ships >= this appVersion, drop this block and
-# let the chart own the tag again.
-image:
-  tag: "1.14.7"
```
If the script prints `ABORT…`, stop. Do not improvise an edit. Check the files first: `git checkout -- "$F" "$V"` and investigate.

Before committing, confirm the render (helm 3 is on PATH via mise). The output must be exactly
one line, `coredns/coredns:1.14.7`. Any other tag means the chart is not doing what §1 says.
STOP and `git checkout -- "$F" "$V"`.
```bash
sed 's/\${SECRET_DOMAIN}/example.test/' "$V" > /private/tmp/coredns-1.48.1/vals.yaml
helm template coredns oci://ghcr.io/coredns/charts/coredns --version 1.48.1 -n kube-system \
  -f /private/tmp/coredns-1.48.1/vals.yaml 2>/dev/null | grep -E '^[[:space:]]*image:' | tr -d ' "' | sed 's/^image://'
```

Commit (shared worktree: `--only`, then verify subject and file list BEFORE push):
```bash
git commit --only "$F" "$V" -m "feat(kube-system): coredns chart 1.47.0 -> 1.48.1, drop image pin (chart appVersion now 1.14.7)" \
  -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
git log -1 --format=%s          # must be the subject above, else amend before push
git show --stat HEAD            # exactly the two coredns files
git push
```
Flux picks the change up through the push webhook. No manual reconcile. Then watch the roll:
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
  → `1.48.1 1.48.1 True`. `helm history coredns -n kube-system --max 2` shows the new revision
  `deployed` on `coredns-1.48.1` with APP VERSION 1.14.7. If any revision after it reads
  `rolled back`, helm's own remediation fired. FAIL.
- **Pods and image:** run this.
  ```bash
  kubectl -n kube-system get pods -l k8s-app=kube-dns -o 'custom-columns=N:.metadata.name,NODE:.spec.nodeName,IMG:.spec.containers[0].image,READY:.status.containerStatuses[0].ready,RS:.status.containerStatuses[0].restartCount,UID:.spec.containers[0].securityContext.runAsUser,SECCOMP:.spec.containers[0].securityContext.seccompProfile.type'
  ```
  → 2 pods with new names, on 2 distinct nodes, `coredns/coredns:1.14.7`, READY true, RS 0,
  UID 65532, SECCOMP RuntimeDefault.
  - A `1.14.6` image means the chart default won without the pin, which contradicts §1. FAIL.
  - `<none>` in UID means 1.48.x was not rendered. FAIL.
- CONTENTS ASSERTION: the running image is byte-identical to the pre-change one. Measured by re-running the §2.2 `imageID` command and `diff`-ing it against `/private/tmp/coredns-1.48.1/imageid.pre` (silent = pass). A different digest means a different image even under the same tag. FAIL.
- CONTENTS ASSERTION: the served Corefile is byte-identical. Measured by `kubectl -n kube-system get cm coredns -o jsonpath='{.data.Corefile}' | shasum -a 256 | diff - /private/tmp/coredns-1.48.1/corefile.pre` (silent = pass). The render diff says the Corefile does not change, so any difference means the chart altered DNS config (for example `max_connect_attempts 6` was lost). FAIL.
- CONTENTS ASSERTION: every NEW replica answers all three name classes correctly and still fails the negative control. Measured by `dnsmatrix | tee /private/tmp/coredns-1.48.1/dnsmatrix.post` (§2.1 function, against the NEW pod IPs). Required: exactly 8 lines. Per IP: cluster name `rc=0 ans=10.96.0.1`, `sweep` `rc=0 ans=192.168.55.103`, `github.com` `rc=0` with an IP, negative control `rc=1 ans=NONE`. Any `rc≠0` on the first three, `rc=0` on the fourth, or fewer than 8 lines is a FAIL. The pod IPs differ from the baseline, so compare the `ans=` and `rc=` columns, not the whole line.
- CONTROL: metric coredns_build_info — exactly 2 series, both `version="1.14.7"`, with the NEW pod names as `pod` labels. 0 series means the scrape broke, so nothing else in this list can be trusted. FAIL.
- CONTROL: metric coredns_dns_responses_total — `sum by (rcode)(rate(coredns_dns_responses_total[5m]))`, read 5 min after the roll. NOERROR must be > 0: this is a floor that proves traffic is served (19.8/s on 2026-10-01). SERVFAIL must not be above the §2.3 baseline (absent on 2026-10-01). A seccomp or uid denial on bind or upstream sockets shows up here as SERVFAIL or as no NOERROR.
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
git show --stat "$SHA"          # confirm it is the coredns 1.48.1 commit
git revert --no-edit "$SHA" && git log -1 --format=%s && git show --stat HEAD && git push
```
What happens:
- The HR returns to the pre-plan chart (1.47.0, or 1.47.1 if the sibling's item C had run), and
  the pin comes back.
- The old generated values ConfigMap still exists (`prune: false`).
- The pods roll again.

**5.2 Confirm the cluster is back:** re-run §4 against the pre-plan state:
- HR `1.47.x … True`.
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
helm history coredns -n kube-system --max 5     # find the last coredns-1.47.x revision (10 on 2026-10-01 if nothing else ran)
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
  the exclusive plans (talos-linux-1.14.2, talconfig-multidoc-migration,
  flux-reconciler-impersonation) the entry is belt and braces.
- **Sibling plan overlap:** `chart-patches-coredns-reloader-blackbox` item C is superseded by this
  plan. Recommend that its owner drop item C (and its `F-3893caaf` ref) so it carries reloader and
  blackbox only. Those two derive AUTO-NIGHT once the DNS item is gone. Until then the two plans
  conflict and must not share a window. In either order, the second one's anchor check keeps it
  safe: this plan accepts 1.47.1, and the sibling's item C aborts on a 1.48.1 file.
- **Renovate:** after the pin is dropped, CoreDNS image updates arrive only through chart bumps.
  The `*coredns*` deny rule keeps sending those to the PLAN lane, which is intended. Do not change
  the rule in this window (§1).
- Retire this file in the commit that records execution. Close the version finding with
  `runbooks/policy-cli.py finding close F-3893caaf --commit <sha>` (and any 1.48.1-titled successor
  the next sweep files).
