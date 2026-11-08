---
plan_id: coredns-1.50.2
component: coredns
pr: 481                               # Renovate #481 = HelmRelease 1.50.1 -> 1.50.2 (the LIVE change). #483 bumps the SAME
                                      # chart in kubernetes/bootstrap/apps/helmfile.yaml (bootstrap-only, no live object reads
                                      # it). Both OPEN 2026-11-08 and both held by the `*coredns*` deny rule. Section 3 makes ONE
                                      # commit whose HR + helmfile hunks have the same git blob ids as the PR post-images
                                      # (2b1588e6f / 392fb5114, measured on scratch copies 2026-11-08), so Renovate closes both.
kind: chart
current: "chart 1.50.1 (appVersion 1.14.7), no image pin"
target: "1.50.2"                      # chart 1.50.2, appVersion 1.14.7 (UNCHANGED) - image does NOT move
update_type: patch                    # chart patch; image unchanged (coredns/coredns:1.14.7 -> 1.14.7)
risk: low                             # MEASURED 2026-11-08: 1.50.2 changes one template helper (default port when a server
                                      # block sets none). Both our server blocks set `port: 53`, so `helm template` 1.50.1 vs
                                      # 1.50.2 with our exact values differs ONLY in 6x helm.sh/chart labels + pod
                                      # checksum/config (Corefile identical). Net effect = one rolling restart, the same roll
                                      # 1.50.0 (2026-11-03) and 1.50.1 (2026-11-06) did green. Impact class (cluster DNS; a
                                      # DNS failure disables its own git revert) is carried by the SD-11 floor + autonomy_override.
est_duration_min: 35                  # section 2 10 + section 3 5 + Flux pickup/roll ~5 + section 4 10 (incl. 5 min rate window) + slack 5
needs_reboot: false
exclusive: false
touches:
  namespaces: [kube-system]
  resources:
    - helmrelease/kube-system/coredns                   # chart 1.50.1 -> 1.50.2 (helm revision 13 -> 14)
    - deployment/kube-system/coredns                    # 2 replicas, RollingUpdate maxUnavailable 1 / maxSurge 25%;
                                                        # no PDB, no priorityClassName (re-read live 2026-11-08)
    - configmap/kube-system/coredns                     # label only; Corefile must be byte-identical
    - service/kube-dns                                  # label only (clusterIP LOOKED UP in 2.1, never typed)
    - serviceaccount/kube-system/coredns                # label only
    - clusterrole/coredns                               # label only
    - clusterrolebinding/coredns                        # label only
    - kubernetes/apps/kube-system/coredns/app/helmrelease.yaml
    - kubernetes/bootstrap/apps/helmfile.yaml           # bootstrap-only pin (Renovate #483); no live object reads it
    - docs/infrastructure.md                            # CoreDNS bootstrap row 1.50.1 -> 1.50.2 (kept in step; line 109)
                                                        # helm-values.yaml is NOT edited -> no new coredns-helm-values-<hash>
  shared:
    - dns                             # SD-11 floor token: cluster DNS for every pod in the cluster
    - coredns                         # SD-11 floor token; ${SECRET_DOMAIN} block forwards to k8s-gateway 192.168.55.101,
                                      # `.` forwards to Talos hostDNS 169.254.116.108
    - flux                            # source-controller resolves github.com THROUGH CoreDNS = this plan's revert path
    - monitoring                      # section 4 reads Prometheus + execs into blackbox (read-only; the instrument is shared)
depends_on: []
conflicts_with:
  # Every open (non-terminal) plan whose execution or verification touches cluster DNS, the HR apply/revert path (Flux
  # controllers, sources, drift), kube-system pod placement/node rolls, or the Prometheus/blackbox instrument section 4 reads.
  # Plan set re-read 2026-11-08 via `maintenance-plan.py --open` + frontmatter scan of every plan mentioning cilium or
  # kube-prometheus-stack.
  - postgres-digest-refresh-2026-11   # reciprocal, added 2026-11-08 (DB-restart plan; sun-attended:2026-12-20)
  - talos-linux-1.14.5                # exclusive node roll (3 reboots); reschedules both CoreDNS pods (lists `coredns` in shared)
  - etcd-timeouts-5000-500            # control-plane service restarts; CoreDNS's kubernetes plugin watches the apiserver
  - flux-reconciler-impersonation     # exclusive; changes how helm-controller applies this HR
  - vaultwarden-1.37.5                # reciprocal: gates on the same http-vaultwarden probe; Recreate gap during a DNS roll would blame the wrong plan
  - flux-oci-chart-sources            # moves HelmRepository sources (incl. the coredns OCI source) and re-applies kube-system HRs
  - helm-drift-detection              # adds driftDetection to every HR incl. this one
  - longhorn-1.13.0                   # exclusive; lists `flux` in shared (its reconcile storm shares the revert path)
  - descheduler-0.37.0                # kube-system CronJob that can evict CoreDNS (no priorityClassName) mid-roll
  - envoy-gateway-1.10.0              # exclusive; restarts k8s-gateway (CoreDNS forwards the domain block to it) and lists `dns`
  - envoy-proxy-config-distroless-v1.40.0   # its verification resolves through CoreDNS and reads probe_success
  - envoy-proxy-config-distroless-v1.40.2   # same surface
  - redis-fleet-8.10.3                # consumers re-resolve on reconnect
  # NOT listed, checked 2026-11-08: no kube-prometheus-stack, blackbox, cilium or flux-fleet plan is open (if one appears
  # it MUST be added: section 4 reads Prometheus and execs into blackbox; a cilium roll breaks pod networking under CoreDNS).
  # Every other open plan only shares `monitoring` as a READER - serialize by slot, do not stack in the same hour.
capability_change: false              # same image coredns/coredns:1.14.7 (same digest), byte-identical Corefile, same
                                      # Service spec; the new helper only changes behaviour for a server block with NO port
rollback_class: git-revert
autonomy_override: human-gated        # `dns`/`coredns`/`flux` are in the SD-11 floor anyway; section 5.3 break-glass needs a human
security_ref: null                    # not security-driven. Image unchanged, so it does NOT answer F-7eb4c1dc.
finding_refs: []                      # `policy-cli.py finding list --grep {coredns,1.50.2,CoreDNS}` 2026-11-08: no finding names
                                      # chart 1.50.2 yet (the version-row finding is created by the next sweep; add its id then).
                                      # F-7eb4c1dc (image security) is NOT answered. F-d3e9f076 (doc, applications.md) already
                                      # reads 1.50.1 and self-resolves; applications.md line 186 also names the chart version
                                      # and is bumped in section 3.
premises:
  # All read-only single commands. Values measured live 2026-11-08.
  - id: coredns-live-image-and-replicas
    why: >-
      Section 4 asserts the image does NOT change (chart 1.50.2 appVersion = 1.14.7 = live). If the live image or replica
      count differs, the imageID and 8-line dnsmatrix gates are wrong. Prints a different string and fails.
    run: kubectl get deploy -n kube-system coredns -o jsonpath='{.spec.template.spec.containers[0].image} {.spec.replicas} {.status.readyReplicas}'
    expect_exact: "coredns/coredns:1.14.7 2 2"
  - id: coredns-hr-chart
    why: >-
      HelmRelease must be Ready on 1.50.1. A failed/in-flight release, or #481 merged behind the plan's back (1.50.2 already
      live), makes section 3's anchor and the section 5 rollback target wrong.
    run: kubectl get helmrelease -n kube-system coredns -o jsonpath='{.spec.chart.spec.version} {.status.lastAttemptedRevision} {.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "1.50.1 1.50.1 True"
  - id: coredns-deployed-chart-label
    why: >-
      The Deployment's helm.sh/chart label is what section 4 compares after the roll; it must read coredns-1.50.1 now or the
      "new release applied" gate cannot tell old from new.
    run: kubectl get deploy -n kube-system coredns -o jsonpath='{.metadata.labels.helm\.sh/chart}'
    expect_exact: "coredns-1.50.1"
  - id: kube-dns-service-spec
    why: >-
      Section 4 asserts the Service spec is unchanged; this records the shape it compares against. The clusterIP is NOT
      hardcoded here: 2.1 reads it into svc.pre and section 4 diffs against that file.
    run: kubectl get svc -n kube-system kube-dns -o jsonpath='{.spec.clusterIP} {.spec.ipFamilyPolicy} {.spec.ipFamilies[*]}'
    expect_matches: '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+ SingleStack IPv4$'
  - id: repo-hr-anchor
    why: >-
      Section 3's edit anchors on exactly one `version: 1.50.1` line in the committed HelmRelease. Prints 0 if main moved.
    run: "git show HEAD:kubernetes/apps/kube-system/coredns/app/helmrelease.yaml | grep -c 'version: 1.50.1'"
    expect_exact: "1"
  - id: repo-bootstrap-anchor
    why: >-
      Section 3's edit also anchors on exactly one `version: 1.50.1` line in the coredns release of the bootstrap helmfile
      (the only release at that version, measured 2026-11-08). Prints 0 if #483 was merged or main moved.
    run: "git show HEAD:kubernetes/bootstrap/apps/helmfile.yaml | grep -c 'version: 1.50.1'"
    expect_exact: "1"
  - id: dns-probes-exist
    why: >-
      Section 4 reads probe_success{probe_class="http"} from these Probe CRs; if renamed/removed the gate reads empty.
    run: kubectl get probe -n monitoring http-ingress-internal http-ingress-external http-vaultwarden -o name
    expect_matches: "(?s)http-ingress-internal.*http-ingress-external.*http-vaultwarden"
  - id: blackbox-exec-target
    why: >-
      Sections 2.1/4 dnsmatrix exec nslookup inside this Deployment; if it is absent or not 1/1 the harness cannot run and
      every DNS gate reads empty.
    run: kubectl get deploy -n monitoring prometheus-blackbox-exporter -o jsonpath='{.status.readyReplicas}/{.spec.replicas}'
    expect_exact: "1/1"
  - id: descheduler-schedule-utc
    why: >-
      Section 6's timing rule assumes the descheduler fires at 04:00 with NO timeZone (= UTC). A changed schedule or an
      added timeZone moves the no-run band; prints something else and fails.
    run: kubectl get cronjob descheduler -n kube-system -o jsonpath='{.spec.schedule} tz={.spec.timeZone}'
    expect_exact: "0 4 * * * tz="
review: ready-for-go@2026-11-08   # plan-reviewer 2026-11-08: ready-for-go, no blocking issues; premises 9/9 live; recommended slot sat-attended 2026-11-14 or 2026-11-21 (alone/last)
status: awaiting-go   # HUMAN-GATED (cluster DNS): GO at the window; never nightly; scheduled by operator 2026-11-08
window: sat-attended:2026-11-21   # reviewer: alone or last in its slot; 11-14 carries open-webui + python-fleet-alpine
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/auto-update.md
  - docs/sops/k8s-gateway-dns.md
  - docs/sops/monitoring.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-11-08"
---

# coredns chart 1.50.1 -> 1.50.2 (image unchanged at 1.14.7)

## 1. Summary & why held

**What changes:** the CoreDNS HelmRelease moves from chart 1.50.1 to 1.50.2. The bootstrap helmfile's coredns pin and
the CoreDNS row in `docs/infrastructure.md` move the same way, in one commit equal to Renovate #481 + #483 plus the
doc row. CoreDNS keeps running **coredns/coredns:1.14.7** (same digest). `helm-values.yaml` is not touched.

**Why held:** the `*coredns*` deny rule in `runbooks/auto-update-policy.yaml` holds every coredns bump in the PLAN lane
on purpose: a coredns patch number is not a patch release (1.14.7 proved it), and a DNS failure disables its own GitOps
revert because source-controller resolves github.com through CoreDNS. The hold is **intentional, not a gate
false-positive**; the diff is trivial, the hold is about blast radius.

**Upstream evidence (primary sources, read 2026-11-08):**
- `helm pull oci://ghcr.io/coredns/charts/coredns` 1.50.1 (`sha256:8d4d6102...`) and 1.50.2 (`sha256:1037b6e9...`): both
  `appVersion: 1.14.7`. **appVersion does NOT change.** Flux's `HelmRepository/coredns` is `oci://ghcr.io/coredns/charts`
  (live), so that is the artifact Flux pulls.
- Chart changelog annotation for 1.50.2, verbatim: `kind: fixed - "Default the Service and container ports when a server
  block has no port set, instead of rendering null ports"`.
- `diff -ru` of the two pulled charts: `templates/_helpers.tpl` gains a `coredns.serverPort` helper (port, else 853 for
  tls:// and quic://, 443 for grpc:// and https://, else 53) used by `coredns.servicePorts` and the container-port list;
  plus two unit tests, a `values.yaml` comment, Chart.yaml. **This IS a template change**, but it only differs from 1.50.1
  for a server block with no `port:`. Both of our blocks set `port: 53` explicitly (`helm-values.yaml`), so the helper
  takes the `if .port` branch and returns the same value. One nuance: `$serviceport` is now `default ($port | int)
  .servicePort` instead of `default .port .servicePort`; with `port: 53` both give 53.
- **Rendered diff with OUR values** (`helm template` 1.50.1 vs 1.50.2, `${SECRET_DOMAIN}` substituted, helm 3.22.1,
  2026-11-08): exactly seven changed lines. 6x `helm.sh/chart: "coredns-1.50.1"` -> `"coredns-1.50.2"`, and the pod
  `checksum/config` (`7553ea3e...` -> `1626f59f...`; it changes because the hashed ConfigMap carries the chart label, the
  Corefile is identical). That checksum triggers the one rolling restart. Rendered image `coredns/coredns:1.14.7`;
  `ipFamilies` occurrences 0.

**Live state (2026-11-08):**
- HR `1.50.1 1.50.1 True`; `helm history` revision 13 `deployed` on coredns-1.50.1 (rev 12 = 1.50.0, rev 11 = 1.49.0).
- 2/2 pods (k8s-nuc14-02 and k8s-nuc14-03, age 43h, 0 restarts); all 3 nodes Ready; no PDB in kube-system; Deployment
  `RollingUpdate` maxUnavailable 1 / maxSurge 25%, no `priorityClassName`, `revisionHistoryLimit` 10.
- imageID `docker.io/coredns/coredns@sha256:7efd3c63...`; Corefile sha256 `cf7ccdad...` (unchanged since 2026-11-03);
  kube-dns `10.96.0.10`, SingleStack IPv4.
- dnsmatrix measured from the blackbox pod against both pod IPs: cluster name -> `10.96.0.1` rc=0, `sweep.<domain>` ->
  `192.168.55.103` rc=0, `github.com` -> public IP rc=0, `does-not-exist-zz9...` rc=1 (negative control).
- kubeconfig server is an IP literal (`https://192.168.55.10:6443`) so `helm`/`kubectl` from the Mac work with cluster DNS down.
- GitRepository `flux-system` points at `https://github.com/...` (resolved through CoreDNS by source-controller), Ready True.

**Pod-disruption behaviour:** there is no PDB. The Deployment rolls with `maxSurge 25%` (rounds up to 1 at 2 replicas) and
`maxUnavailable 1`. Required pod anti-affinity over the three control-plane nodes puts the surge pod on the one node
without a CoreDNS pod (k8s-nuc14-01 today); then the old pods terminate one at a time. At least one replica serves at
all times; each terminating pod has `lameduck 5s` on the `.` block, so in-flight queries drain. Expected visible effect:
none, or a few retried lookups for ~5 s. This is the same mechanic as the 1.49.0 / 1.50.0 / 1.50.1 rolls, all green.

**Out of scope, flagged for the operator (not done here):**
- **The image finding stays open.** `F-7eb4c1dc` (image-level security finding on `coredns/coredns:1.14.7`; detail on the
  DB record) is not answered: chart 1.50.2 still says 1.14.7.
- **Deny rule:** do NOT edit `runbooks/auto-update-policy.yaml` in this window. Keep / narrow / remove stays an operator
  decision. (Repo observation, not acted on: the rule's reason text is still accurate for this component, but note the
  last three consecutive chart patches were label-only rolls.)

## 2. Pre-checks (all read-only; abort on any failure)

```bash
cd /Users/mu/code/cberg-home-nextgen
.venv/bin/python3 runbooks/plan-premises.py coredns-1.50.2 --require-premises   # all PASS, no REFUSED line
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'                    # header only
flux get helmreleases -A   | awk 'NR==1 || $5 != "True"'                    # header only
git status --short -- kubernetes/apps/kube-system/coredns kubernetes/bootstrap/apps/helmfile.yaml docs/infrastructure.md   # empty
flux get sources git -n flux-system flux-system ; git rev-parse --short origin/main   # same revision (Step 0 settled)
gh pr view 481 --json state -q .state ; gh pr view 483 --json state -q .state         # OPEN OPEN (MERGED -> STOP, re-plan)
helm history coredns -n kube-system --max 3                                 # DEPLOYED revision = 13 (coredns-1.50.1); note it for 5.3
helm show chart oci://ghcr.io/coredns/charts/coredns --version 1.50.2 | grep -E '^(version|appVersion)'   # 1.50.2 / 1.14.7
helm show chart oci://ghcr.io/coredns/charts/coredns --version 1.50.3 2>&1 | head -1   # expect "not found" (a newer patch means re-check the diff)
kubectl get nodes                                                           # prefer 3 Ready (section 6 surge note)
date -u +%H:%M                                                              # NOT within 03:50-04:10 UTC (descheduler `0 4 * * *`, no timeZone = UTC)
mkdir -p /private/tmp/coredns-1.50.2
```

**2.1 DNS baseline (record it; section 4 compares against it).** The lookups run from inside the blackbox pod, because pod
IPs are not routable from the Mac. busybox `nslookup` exits 1 on NXDOMAIN, so the fourth name is the negative control
(measured rc=1 on 2026-11-08). Expected in-cluster answers are LOOKED UP from live Services, never typed:
```bash
cat > /private/tmp/coredns-1.50.2/fns.sh <<'FNS'
D=$(kubectl -n flux-system get secret cluster-secrets -o jsonpath='{.data.SECRET_DOMAIN}' | base64 -d)
KSVC=$(kubectl -n default get svc kubernetes -o jsonpath='{.spec.clusterIP}')        # what kubernetes.default must resolve to
KDNS=$(kubectl -n kube-system get svc kube-dns -o jsonpath='{.spec.clusterIP}')      # the address every pod's resolv.conf points at
test -n "$D" -a -n "$KSVC" -a -n "$KDNS" || { echo "GUARD: lookup returned empty (D/KSVC/KDNS)"; false; }
dnsmatrix() {
  for ip in $(kubectl -n kube-system get pods -l k8s-app=kube-dns -o jsonpath='{.items[*].status.podIP}'); do
    for n in kubernetes.default.svc.cluster.local "sweep.$D" github.com does-not-exist-zz9.svc.cluster.local; do
      out=$(kubectl -n monitoring exec deploy/prometheus-blackbox-exporter -- nslookup -type=A "$n" "$ip" 2>&1); rc=$?
      a=$(printf '%s\n' "$out" | awk '/^Name:/{f=1} f&&/^Address/{print $2}' | head -1)
      echo "$ip rc=$rc ans=${a:-NONE} name=${n%%.$D}"
    done
  done
}
q(){ curl -s --get http://localhost:19090/api/v1/query --data-urlencode "query=$1" \
  | python3 -c "import sys,json; r=json.load(sys.stdin)['data']['result']; print(len(r)); [print(' ',{k:v for k,v in x['metric'].items() if k in ('pod','version','rcode','to','instance','alertname')},x['value'][1]) for x in r]"; }
FNS
. /private/tmp/coredns-1.50.2/fns.sh && echo "FNS_OK ksvc=$KSVC kdns=$KDNS"
dnsmatrix | tee /private/tmp/coredns-1.50.2/dnsmatrix.pre
kubectl -n monitoring exec deploy/prometheus-blackbox-exporter -- nslookup -type=A kubernetes.default.svc.cluster.local "$KDNS" | awk '/^Name:/{f=1} f&&/^Address/{print "via-kube-dns-vip", $2}' | head -1 | tee /private/tmp/coredns-1.50.2/vip.pre
```
`FNS_OK` must print two non-empty addresses; `vip.pre` must name `$KSVC`. Expected 8 lines (2 pod IPs x 4 names):
cluster name `rc=0 ans=$KSVC` (10.96.0.1 on 2026-11-08); `sweep` `rc=0 ans=192.168.55.103`; `github.com` `rc=0` with a
public IP; `does-not-exist-zz9...` `rc=1 ans=NONE`. **Negative control:** if the last name ever reads `rc=0`, the harness
cannot detect a failure. STOP. Do not hold the IP list in a zsh scalar; `for ip in $(...)` word-splits correctly.

**2.2 Corefile, image-digest and Service baseline:**
```bash
kubectl -n kube-system get cm coredns -o jsonpath='{.data.Corefile}' > /private/tmp/coredns-1.50.2/corefile.txt
test -s /private/tmp/coredns-1.50.2/corefile.txt || { echo 'ABORT: empty Corefile read'; false; }
shasum -a 256 < /private/tmp/coredns-1.50.2/corefile.txt | tee /private/tmp/coredns-1.50.2/corefile.pre
# 2026-11-08: cf7ccdad3e5799e63d642753797489197dbf50db294083622bb9578fde54063d
kubectl -n kube-system get pods -l k8s-app=kube-dns -o jsonpath='{range .items[*]}{.status.containerStatuses[0].imageID}{"\n"}{end}' | sort -u | tee /private/tmp/coredns-1.50.2/imageid.pre
# 1 line: docker.io/coredns/coredns@sha256:7efd3c635b03efd68c4e8398fc45f0d993d0e9ab016f72c1cefb0fd6d01aa286 (2026-11-08)
kubectl -n kube-system get svc kube-dns -o jsonpath='{.spec.clusterIP} {.spec.ipFamilyPolicy} {.spec.ipFamilies[*]} {.spec.ports[*].port}' | tee /private/tmp/coredns-1.50.2/svc.pre
kubectl -n kube-system get pods -l k8s-app=kube-dns -o name | sort | tee /private/tmp/coredns-1.50.2/pods.pre
test "$(wc -l < /private/tmp/coredns-1.50.2/pods.pre | tr -d ' ')" = 2 || echo 'ABORT: expected 2 pods in pods.pre'
```

**2.3 Prometheus baseline.** The port-forward stays up for section 4.
```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; echo $PF > /private/tmp/coredns-1.50.2/pf.pid; sleep 3
. /private/tmp/coredns-1.50.2/fns.sh
q 'coredns_build_info'                                                  # 2 series, version="1.14.7"
q 'sum by (rcode)(rate(coredns_dns_responses_total[10m]))'              # NOERROR > 0 and NXDOMAIN > 0; SERVFAIL absent
q 'sum by (to,rcode)(rate(coredns_proxy_request_duration_seconds_count[10m]))'   # to=192.168.55.101:53 and to=169.254.116.108:53 both NOERROR > 0
q 'min_over_time(probe_success{probe_class="http"}[5m])'               # 3 series, all 1
q 'ALERTS{alertstate="firing",alertname=~"InternalDns.*|IngressProbe.*|Blackbox.*|CoreDNS.*"}'   # 0
```
Record the SERVFAIL value (absent = 0). If `coredns_build_info` returns 0 series the scrape is broken and the metric gates
below are blind: fix or drop to the dnsmatrix gates, do not proceed on empty reads.

**2.4 Fallback source of the revert (read before pushing).** The only DNS-independent restore is `helm rollback` from the
Mac (apiserver by IP; check `kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}'` prints `https://<ip>:6443`, a hostname FAILS this pre-check) and the retained ReplicaSet (`revisionHistoryLimit 10`, 11 old ReplicaSets
live 2026-11-08). Confirm the Mac itself resolves github.com (`git push` runs from the Mac, not through cluster DNS):
`git ls-remote origin HEAD | head -1` prints a sha. Also run the apiserver-by-IP check above now.

## 3. Steps (one commit, three files)

The edit was dry-tested with macOS `python3 -I` on scratch copies of all three files from `HEAD` on 2026-11-08:
- It checks ALL three anchors before writing ANY file.
- The HelmRelease and helmfile post-image blobs are `2b1588e6f...` and `392fb5114...`, identical to the blob ids GitHub
  reports for Renovate #481 and #483 (`gh api repos/.../pulls/481/files`).
- A second run aborts with `ABORT: helmrelease anchor not found exactly once`.

```bash
cd /Users/mu/code/cberg-home-nextgen
F=kubernetes/apps/kube-system/coredns/app/helmrelease.yaml
B=kubernetes/bootstrap/apps/helmfile.yaml
DOC=docs/infrastructure.md
python3 -I - "$F" "$B" "$DOC" <<'EOF'
import re, sys
hr, boot, doc = sys.argv[1:4]
s = open(hr).read()
pat = re.compile(r'^      version: 1\.50\.1$', re.M)
if len(pat.findall(s)) != 1: sys.exit("ABORT: helmrelease anchor not found exactly once")
b = open(boot).read()
bpat = re.compile(r'^(    chart: oci://ghcr\.io/coredns/charts/coredns\n    version: )1\.50\.1$', re.M)
if len(bpat.findall(b)) != 1: sys.exit("ABORT: bootstrap helmfile coredns anchor not found exactly once")
t = open(doc).read()
dpat = re.compile(r'^(\| 2 \| CoreDNS \| `oci://ghcr\.io/coredns/charts/coredns` \| )1\.50\.1( \|)', re.M)
if len(dpat.findall(t)) != 1: sys.exit("ABORT: docs/infrastructure.md CoreDNS row anchor not found exactly once")
open(hr, 'w').write(pat.sub('      version: 1.50.2', s))
open(boot, 'w').write(bpat.sub(r'\g<1>1.50.2', b))
open(doc, 'w').write(dpat.sub(r'\g<1>1.50.2\g<2>', t))
print("OK")
EOF
git diff -- "$F" "$B" "$DOC"
git hash-object "$F" "$B"       # 2b1588e6fbcc... and 392fb5114c78... (= #481 / #483 post-images)
```
Expected diff (verbatim from the dry run):
```
helmrelease.yaml:  -      version: 1.50.1   /   +      version: 1.50.2
helmfile.yaml (coredns release):  -    version: 1.50.1   /   +    version: 1.50.2
docs/infrastructure.md (line 109): the CoreDNS row's version cell 1.50.1 -> 1.50.2
```
If the script prints `ABORT...`, stop. Do not improvise. Run `git checkout -- "$F" "$B" "$DOC"` and investigate (a merged
#481/#483 or a doc edit by another session is the likely cause). If ONLY the doc anchor fails, dropping `$DOC` from the
script and the commit is acceptable; the two chart hunks are the change. `docs/applications.md` line 186 also carries the
chart number ("Chart 1.50.1 / image 1.14.7"): edit it with the Edit tool to 1.50.2 and add it to the commit if it is still 1.50.1.

Before committing, confirm the render with the NEW chart and our values (helm 3 via mise). The image line must be exactly
`coredns/coredns:1.14.7` and `ipFamilies` count `0`; the diff against the 1.50.1 render must be only chart labels and the
checksum. Anything else means the chart is not doing what section 1 says: STOP and `git checkout -- "$F" "$B" "$DOC"`.
```bash
V=kubernetes/apps/kube-system/coredns/app/helm-values.yaml
sed 's/\${SECRET_DOMAIN}/example.test/' "$V" > /private/tmp/coredns-1.50.2/vals.yaml
for v in 1.50.1 1.50.2; do helm template coredns oci://ghcr.io/coredns/charts/coredns --version $v -n kube-system -f /private/tmp/coredns-1.50.2/vals.yaml > /private/tmp/coredns-1.50.2/render-$v.yaml; done
grep -E '^[[:space:]]*image:' /private/tmp/coredns-1.50.2/render-1.50.2.yaml | tr -d ' "' | sed 's/^image://'   # coredns/coredns:1.14.7
grep -c -i 'ipFamilies' /private/tmp/coredns-1.50.2/render-1.50.2.yaml                                          # 0
diff /private/tmp/coredns-1.50.2/render-1.50.1.yaml /private/tmp/coredns-1.50.2/render-1.50.2.yaml | grep -E '^[<>]' | grep -vcE 'helm.sh/chart: "coredns-1.50.[12]"|checksum/config'   # 0
```

Commit. Shared worktree: use `--only`, then verify subject and file list BEFORE pushing:
```bash
git commit --only "$F" "$B" "$DOC" -m "fix(kube-system): coredns chart 1.50.1 -> 1.50.2 (appVersion 1.14.7 unchanged; default-port helper, no-op for our explicit port: 53); supersedes Renovate #481 #483" \
  -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
git log -1 --format=%s          # must be the subject above, else amend before push
git show --stat HEAD            # exactly the files you edited
git push
```
Flux picks the change up through the push webhook. No manual reconcile. Do NOT merge or close #481/#483 by hand. Watch
the roll with a bounded poll (no `-w`):
```bash
for i in $(seq 1 40); do kubectl -n kube-system get pods -l k8s-app=kube-dns --no-headers; echo ---; sleep 15; done | tail -12
```
Proceed once exactly 2 NEW pods are Running 1/1 on 2 distinct nodes and none is Terminating (<= 10 min). If the HR does not
move within 10 min, check the webhook and `flux get sources git` before anything else.

## 4. Verification (any FAIL -> section 5)

Wait until exactly 2 kube-dns pods are Running and none is Terminating (lameduck 5 s); that also fixes the dnsmatrix line
count. Each block runs in a fresh shell: start with `. /private/tmp/coredns-1.50.2/fns.sh` (it defines `q`), and re-open
the 2.3 port-forward if `pf.pid` is dead.

- **Release:**
  ```bash
  kubectl get hr -n kube-system coredns -o jsonpath='{.spec.chart.spec.version} {.status.lastAttemptedRevision} {.status.conditions[?(@.type=="Ready")].status}'
  ```
  Expected `1.50.2 1.50.2 True`. `helm history coredns -n kube-system --max 2` shows revision 14 `deployed` on
  `coredns-1.50.2`, APP VERSION 1.14.7. A later revision reading `rolled back` means helm's own remediation fired. FAIL.
- **Pods rolled and run the new render:**
  ```bash
  kubectl -n kube-system get pods -l k8s-app=kube-dns -o name | sort | comm -12 - /private/tmp/coredns-1.50.2/pods.pre   # EMPTY = both replaced
  kubectl -n kube-system get pods -l k8s-app=kube-dns -o 'custom-columns=N:.metadata.name,NODE:.spec.nodeName,IMG:.spec.containers[0].image,READY:.status.containerStatuses[0].ready,RS:.status.containerStatuses[0].restartCount'
  kubectl get deploy -n kube-system coredns -o jsonpath='{.metadata.labels.helm\.sh/chart}'
  ```
  `comm` output must be empty (a surviving old name means the roll did not happen and every later gate would measure the
  old pods). 2 pods on 2 distinct nodes, `coredns/coredns:1.14.7`, READY true, RS 0. The Deployment label must print
  `coredns-1.50.2`; `coredns-1.50.1` means the new release did not apply. FAIL.
- CONTENTS ASSERTION: the running image is byte-identical. First `test -s /private/tmp/coredns-1.50.2/imageid.pre` (empty
  baseline = FAIL, never a silent pass). Re-run the 2.2 imageID command and `diff` it against `imageid.pre` (silent =
  pass). A different digest under the same tag is a different image. FAIL.
- CONTENTS ASSERTION: the served Corefile is byte-identical:
  `kubectl -n kube-system get cm coredns -o jsonpath='{.data.Corefile}' | shasum -a 256 | diff - /private/tmp/coredns-1.50.2/corefile.pre`
  (silent = pass). Any difference means the chart altered DNS config (for example a lost `max_connect_attempts 6`). FAIL.
- CONTENTS ASSERTION: the kube-dns Service spec is unchanged (this is the one thing the 1.50.2 port helper could touch):
  re-run the 2.2 Service jsonpath and `diff` against `svc.pre` (silent = pass), and the live clusterIP must equal `$KDNS`.
  A changed port list or clusterIP breaks every pod's `/etc/resolv.conf` target. Also
  `kubectl -n kube-system get deploy coredns -o jsonpath='{.spec.template.spec.containers[0].ports[*].containerPort}'`
  must print `53 53 9153` (two DNS ports + metrics; compare to the pre-roll value, they must be equal). FAIL otherwise.
- CONTENTS ASSERTION: every NEW replica answers all three name classes and still fails the negative control.
  `dnsmatrix | tee /private/tmp/coredns-1.50.2/dnsmatrix.post`: exactly 8 lines; per IP cluster name `rc=0 ans=$KSVC`,
  `sweep` `rc=0 ans=192.168.55.103`, `github.com` `rc=0` with an IP, negative control `rc=1 ans=NONE`; re-run the
  `vip.pre` command and its output must equal `vip.pre`. FAIL on any `rc!=0` for the first three names, `rc=0` on the
  fourth, or < 8 lines. Pod IPs differ from the baseline, so compare the `rc=`/`ans=` columns, not whole lines.
- CONTROL: metric coredns_build_info - exactly 2 series, both `version="1.14.7"`, with the NEW pod names. 0 series means the
  scrape broke and nothing else here can be trusted. FAIL.
- CONTROL: metric coredns_dns_responses_total - `sum by (rcode)(rate(coredns_dns_responses_total[5m]))` 5 min after the
  roll: NOERROR > 0 (proves traffic is served); SERVFAIL not above the 2.3 baseline (absent).
- CONTROL: metric coredns_proxy_request_duration_seconds_count - `sum by (to,rcode)(rate(...[5m]))`: both
  `to="192.168.55.101:53"` and `to="169.254.116.108:53"` NOERROR > 0 (both forward blocks reach their upstreams). Scope to the
  new pods (`pod=~` the two new names) so the old pods' series do not mask a dead new one.
- CONTROL: metric probe_success - `min_over_time(probe_success{probe_class="http"}[5m])` = 1 for all 3 http probes. These
  resolve hostnames through CoreDNS inside the blackbox pod (end to end). The `dns_*` probes target k8s-gateway .101
  directly and stay green with CoreDNS dead, so they are NOT a CoreDNS gate.
- CONTROL: alertname IngressProbeFailing - not firing. alertname InternalDnsResolutionFailing - not firing (covers
  k8s-gateway, not CoreDNS; listed so a coincident k8s-gateway failure is not misread as this plan's fault).
- **Rollback-path health (a gate that can fail).** Wait >= 2 min after the roll. A bare `flux get sources git` shows a fetch
  made BEFORE the roll and cannot fail. Force a fetch that must resolve github.com through the new pods and read back that
  THIS request was handled:
  ```bash
  TOK=$(date +%s)
  kubectl -n flux-system annotate gitrepository flux-system reconcile.fluxcd.io/requestedAt="$TOK" --overwrite
  for i in $(seq 1 24); do
    H=$(kubectl -n flux-system get gitrepository flux-system -o jsonpath='{.status.lastHandledReconcileAt}')
    [ "$H" = "$TOK" ] && { echo "HANDLED token=$H"; break; }; sleep 5
  done; [ "$H" = "$TOK" ] || echo "NOT_HANDLED_IN_2MIN"
  kubectl -n flux-system get gitrepository flux-system -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.artifact.revision}{"\n"}'
  git fetch origin && git rev-parse origin/main
  ```
  `lastHandledReconcileAt` is set even when the fetch FAILS, so `HANDLED` only proves an attempt. PASS = `HANDLED` AND Ready
  `True` AND artifact revision equal to the freshly fetched `origin/main` (compare, do not remember: other sessions push).
  FAIL = `NOT_HANDLED_IN_2MIN`, or HANDLED with `False` (print the Ready message; a DNS failure lands here), or a stale
  revision. This is the plan's one cluster write: the Flux-documented request annotation (what `flux reconcile source git`
  does), attended, changing no workload.

Finally: `kill $(cat /private/tmp/coredns-1.50.2/pf.pid)`.

## 5. Rollback

**5.1 GitOps revert (default; needs source-controller to resolve github.com, so it works only while DNS works):**
```bash
cd /Users/mu/code/cberg-home-nextgen
SHA=$(git log -1 --format=%h -- kubernetes/apps/kube-system/coredns/app/helmrelease.yaml)
git show --stat "$SHA"          # confirm it is the coredns 1.50.2 commit
git revert --no-edit "$SHA" && git log -1 --format=%s && git show --stat HEAD && git push
```
The HR and helmfile return to 1.50.1 (the doc rows with them). No values change, so no ConfigMap is orphaned. Pods roll
again. Renovate re-opens its 1.50.2 PRs later; expected. Nothing forward-only happens (no CRD, PVC, migration; same
image; same Corefile), so a revert is the complete restore.

**5.2 Confirm the cluster is back.** Re-run section 4 against the pre-plan state: HR `1.50.1 1.50.1 True`; Deployment
label `coredns-1.50.1`; imageID = `imageid.pre`, Corefile hash = `corefile.pre`, Service = `svc.pre`; `dnsmatrix` matches
the baseline; rollback-path gate PASS.

**5.3 Break-glass that does NOT use cluster DNS** (CoreDNS serving failures AND the 5.1 revert cannot land: no fetch of the
revert revision by source-controller within 5 min of the push). Operator-present only, never unattended. Every command runs
from the Mac against the apiserver IP (`https://192.168.55.10:6443`, checked in 2.4); none needs a name resolved
by CoreDNS, and `git push` uses the Mac's own resolver:
```bash
helm history coredns -n kube-system --max 5     # 13 = last coredns-1.50.1 revision unless something else ran; use what helm shows
flux suspend helmrelease coredns -n kube-system # stops helm-controller re-applying 1.50.2 over the rollback
helm rollback coredns 13 -n kube-system --wait --timeout 5m
```
`helm rollback` re-renders revision 13's stored manifest (it needs only the apiserver, not the OCI registry or github.com).
Faster still, if even that is slow, the previous ReplicaSet is retained (`revisionHistoryLimit 10`):
`kubectl -n kube-system rollout undo deploy/coredns` returns to the previous pod template, then still do the `helm rollback`
so Helm's record matches. Confirm with the section 4 dnsmatrix and the `lastHandledReconcileAt` gate. Then push the 5.1
revert; once `flux get sources git` shows the revert revision, `flux resume helmrelease coredns -n kube-system`.
Helm's `upgrade.remediation.strategy: rollback` (retries 3) only covers an upgrade that FAILS to become Ready, not a Ready
upgrade that answers wrongly, which is why this path exists. If the Mac cannot reach the apiserver either, the problem is
not this plan: stop and use `docs/sops/k8s-gateway-dns.md` and the Talos break-glass.

## 6. Interference notes

- **Execution class: HUMAN-GATED, expected and correct, NOT AUTO-NIGHT.** `touches.shared` carries `dns`, `coredns` and
  `flux`, all in the in-code SD-11 floor, and `autonomy_override: human-gated` states it. `risk: low` does not change that:
  the gate is the self-revert hazard (5.3 needs a human with `helm` if DNS breaks at 03:30), not the diff. Do not make it
  eligible by editing fields. 35 min fits a `sat-attended` slot (70 usable min); an on-demand NOW run with an operator GO
  (as 1.50.0 and 1.50.1 ran) is equally fine. Unscheduled: `window: null`; the window agent assigns it.
- **Run it alone, or last in its window.** No other plan may verify through DNS or Prometheus during the ~2-min roll, hence
  every DNS-, Flux-, k8s-gateway- and monitoring-verifying open plan is in `conflicts_with`. In particular do NOT put it in
  the same slot as `talos-linux-1.14.5` (sun-attended:2026-11-22), `longhorn-1.13.0` (sun-attended:2026-11-15), `helm-drift-detection`
  (sat-attended:2026-11-28), `redis-fleet-8.10.3` (sun-attended:2026-11-29) or `flux-oci-chart-sources` (sun-attended:2026-12-13).
  Free Saturdays today: 2026-11-14, 2026-11-21.
- **Nodes / Cilium:** nothing in this plan reboots a node or touches Cilium. If a node roll or Cilium upgrade lands in the
  same night, CoreDNS pods reschedule and section 2 baselines are invalid: abort and re-run after it settles.
- **Descheduler:** `kube-system/descheduler` CronJob is `0 4 * * *` with no `timeZone` (premise `descheduler-schedule-utc`) =
  04:00 **UTC**. CoreDNS has no `priorityClassName` and no PDB, so its pods are evictable. Do not run section 3 within ~10 min
  of 04:00 UTC (`date -u`).
- **Surge scheduling:** maxSurge 25% rounds up to 1 at `replicas: 2`; required anti-affinity over the 3 control-plane nodes
  puts the surge pod on the free node. With a node cordoned/NotReady the roll proceeds via `maxUnavailable: 1` with one
  replica serving for a few seconds; prefer all 3 Ready at section 2.
- **Renovate:** do not merge #481/#483 separately; section 3's single commit is byte-identical to both for the two chart files.
- **Findings:** after execution, close any version-row finding the next sweep opened for "coredns: chart 1.50.1 -> 1.50.2" with
  `runbooks/policy-cli.py finding close <id> --commit <sha>`. Do NOT close `F-7eb4c1dc`; this plan does not move the image.
- Retire this file in the commit that records execution.
