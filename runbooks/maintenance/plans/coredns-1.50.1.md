---
plan_id: coredns-1.50.1
component: coredns
pr: 481                               # Renovate #481 = HelmRelease 1.50.0 -> 1.50.1 (the LIVE change; CI: Flate Render
                                      # Gate + Flux Local Diff green). #483 is NOT a duplicate: it bumps the SAME chart
                                      # in kubernetes/bootstrap/apps/helmfile.yaml (bootstrap-only, no live object reads
                                      # it; only the Labeler check runs on it). Both are held by the `*coredns*` deny
                                      # rule. §3 makes ONE commit whose HR + helmfile hunks have the same git blob ids
                                      # as the PR post-images (89729e391 / a10bad109, measured on scratch copies
                                      # 2026-11-06), so Renovate closes BOTH as already applied. Do not close #483
                                      # unapplied: that leaves the bootstrap pin drifting behind the live chart.
kind: chart
current: "chart 1.50.0 (appVersion 1.14.7), no image pin"
target: "1.50.1"                      # chart 1.50.1, appVersion 1.14.7 (UNCHANGED) - image does NOT move
update_type: patch                    # chart patch; image unchanged (coredns/coredns:1.14.7 -> 1.14.7)
risk: low                             # MEASURED 2026-11-06: upstream 1.50.0...1.50.1 = 2 commits, docs only
                                      # (Chart.yaml changelog annotation, README, a values.yaml COMMENT). `helm template`
                                      # 1.50.0 vs 1.50.1 with our exact values differs ONLY in 6x helm.sh/chart labels +
                                      # pod checksum/config (Corefile identical). Net effect = one rolling restart, the
                                      # same roll 1.50.0 did green on 2026-11-03 (391cf1a8). Impact class (cluster DNS;
                                      # a DNS failure disables its own git revert) is carried by the SD-11
                                      # `dns`/`coredns`/`flux` floor + autonomy_override, not by inflating risk.
est_duration_min: 35                  # §2 10 + §3 5 + Flux pickup/roll ~5 + §4 10 (incl. 5 min rate window) + slack 5
needs_reboot: false
exclusive: false
touches:
  namespaces: [kube-system]
  resources:
    - helmrelease/kube-system/coredns                   # chart 1.50.0 -> 1.50.1 (helm revision 12 -> 13)
    - deployment/kube-system/coredns                    # 2 replicas, RollingUpdate maxUnavailable 1 / maxSurge 25%;
                                                        # no PDB, no priorityClassName (re-read 2026-11-06)
    - configmap/kube-system/coredns                     # label only; Corefile must be byte-identical
    - service/kube-system/kube-dns                      # label only (clusterIP LOOKED UP in §2.2, never typed)
    - serviceaccount/kube-system/coredns                # label only
    - clusterrole/coredns                               # label only
    - clusterrolebinding/coredns                        # label only
    - kubernetes/apps/kube-system/coredns/app/helmrelease.yaml
    - kubernetes/bootstrap/apps/helmfile.yaml           # bootstrap-only pin (Renovate #483); no live object reads it
    - docs/infrastructure.md                            # CoreDNS bootstrap row still says 1.49.0 -> 1.50.1 (F-d6750a2d)
                                                        # helm-values.yaml is NOT edited -> no new coredns-helm-values-<hash>
  shared:
    - dns                             # SD-11 floor token: cluster DNS for every pod in the cluster
    - coredns                         # SD-11 floor token; ${SECRET_DOMAIN} block forwards to k8s-gateway 192.168.55.101,
                                      # `.` forwards to Talos hostDNS 169.254.116.108
    - flux                            # source-controller resolves github.com THROUGH CoreDNS = this plan's revert path
    - monitoring                      # §4 reads Prometheus + execs into blackbox (read-only; the instrument is shared)
depends_on: []
conflicts_with:
  # Every open (non-terminal) plan whose execution or verification touches cluster DNS, the HR apply/revert path
  # (Flux controllers, sources, drift), kube-system pod placement, or the Prometheus/blackbox instrument §4 reads.
  # Plan set re-read 2026-11-06 via `maintenance-plan.py --open` + frontmatter scan of every non-terminal plan.
  - talos-linux-1.14.5                # exclusive node roll; reschedules both CoreDNS pods (lists `coredns` in shared)
  - etcd-timeouts-5000-500            # control-plane service restarts; CoreDNS's kubernetes plugin watches the apiserver
  - flux-reconciler-impersonation     # exclusive; changes how helm-controller applies this HR
  - flux-oci-chart-sources            # moves HelmRepository sources and re-applies kube-system HRs
  - helm-drift-detection              # adds driftDetection to every HR incl. this one (flux-system + kube-system)
  - longhorn-1.13.0                   # exclusive; lists `flux` in shared (its reconcile storm shares the revert path)
  - descheduler-0.37.0                # kube-system CronJob that can evict CoreDNS (no priorityClassName) mid-roll
  - edot-collector-0.164.0            # its ES exporters resolve through CoreDNS; reads the same monitoring surface
  - envoy-proxy-config-distroless-v1.40.0   # its §4 reads probe_success + resolves through CoreDNS
  - envoy-proxy-config-distroless-v1.40.2   # same surface
  - redis-fleet-8.10.3                # consumers re-resolve on reconnect
  # NOT listed, checked 2026-11-06: no kube-prometheus-stack / blackbox / cilium / flux-fleet plan is open (if one
  # appears it MUST be added: §4 reads Prometheus and execs into blackbox; flux-fleet rolls the revert path).
  # authentik-2026.8.5, envoy v1.39.4 and flux-fleet-0.62.1 (in the 1.50.0 plan's list) are no longer open.
  # Every other open plan only shares `monitoring` as a READER (gha-fleet, python-fleet*, nextcloud-mcp*, open-webui,
  # otbr*, frigate, vaultwarden, tube-archivist*, icloud-drive-fleet, talos-power-tuning-ab) - serialize by slot.
capability_change: false              # same image coredns/coredns:1.14.7 (same digest), byte-identical Corefile, same
                                      # Service spec; 1.50.1 adds no value and no template - measured, §1
rollback_class: git-revert
autonomy_override: human-gated        # `dns`/`coredns`/`flux` are in the SD-11 floor anyway; §5.3 break-glass needs a human
security_ref: null                    # not security-driven. Image unchanged, so it does NOT answer F-7eb4c1dc (§1).
finding_refs: [F-3893caaf, F-d6750a2d]   # `policy-cli.py finding list --grep {coredns,1.50.1,CoreDNS}` 2026-11-06:
                                      # F-3893caaf = version row "coredns: chart 1.50.0 -> 1.50.1 (patch)";
                                      # F-d6750a2d = doc row "Bootstrap chart coredns version not in docs/infrastructure.md"
                                      # (§3 fixes the doc row in the same commit). F-7eb4c1dc (image security),
                                      # F-be7c319e / F-44a4e9fd (health) are NOT answered by this plan.
premises:
  # All read-only single commands. Values measured live 2026-11-06.
  - id: coredns-live-image-and-replicas
    why: >-
      §4 asserts the image does NOT change (chart 1.50.1 appVersion = 1.14.7 = live). If the live image or replica
      count differs, the imageID and 8-line dnsmatrix gates are wrong. Prints a different string and fails.
    run: kubectl get deploy -n kube-system coredns -o jsonpath='{.spec.template.spec.containers[0].image} {.spec.replicas} {.status.readyReplicas}'
    expect_exact: "coredns/coredns:1.14.7 2 2"
  - id: coredns-hr-chart
    why: >-
      HelmRelease must be Ready on 1.50.0. A failed/in-flight release, or #481 merged behind the plan's back
      (1.50.1 already live), makes §3's anchor and the §5 rollback target wrong.
    run: kubectl get helmrelease -n kube-system coredns -o jsonpath='{.spec.chart.spec.version} {.status.lastAttemptedRevision} {.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "1.50.0 1.50.0 True"
  - id: kube-dns-service-spec
    why: >-
      §4 asserts the Service spec is unchanged; this records the shape it compares against. The clusterIP is NOT
      hardcoded (cluster-assigned): §2.2 reads it into svc.pre and §4 diffs against that file.
    run: kubectl get svc -n kube-system kube-dns -o jsonpath='{.spec.clusterIP} {.spec.ipFamilyPolicy} {.spec.ipFamilies[*]}'
    expect_matches: '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+ SingleStack IPv4$'
  - id: repo-hr-anchor
    why: >-
      §3's edit anchors on exactly one `version: 1.50.0` line in the committed HelmRelease. Prints 0 if main moved.
    run: "git show HEAD:kubernetes/apps/kube-system/coredns/app/helmrelease.yaml | grep -c 'version: 1.50.0'"
    expect_exact: "1"
  - id: repo-bootstrap-anchor
    why: >-
      §3's edit also anchors on exactly one `version: 1.50.0` line in the bootstrap helmfile (the coredns release is
      the only one at that version, measured 2026-11-06). Prints 0 if #483 was merged or main moved.
    run: "git show HEAD:kubernetes/bootstrap/apps/helmfile.yaml | grep -c 'version: 1.50.0'"
    expect_exact: "1"
  - id: dns-probes-exist
    why: >-
      §4 reads probe_success{probe_class="http"} from these Probe CRs; if renamed/removed the gate reads empty.
    run: kubectl get probe -n monitoring http-ingress-internal http-ingress-external http-vaultwarden -o name
    expect_matches: "(?s)http-ingress-internal.*http-ingress-external.*http-vaultwarden"
  - id: blackbox-exec-target
    why: >-
      §2.1/§4 dnsmatrix execs nslookup inside this Deployment; if it is absent or not 1/1 the harness cannot run and
      every DNS gate reads empty.
    run: kubectl get deploy -n monitoring prometheus-blackbox-exporter -o jsonpath='{.status.readyReplicas}/{.spec.replicas}'
    expect_exact: "1/1"
  - id: descheduler-schedule-utc
    why: >-
      §6's timing rule assumes the descheduler fires at 04:00 with NO timeZone (= UTC). A changed schedule or an
      added timeZone moves the no-run band; prints something else and fails.
    run: kubectl get cronjob descheduler -n kube-system -o jsonpath='{.spec.schedule} tz={.spec.timeZone}'
    expect_exact: "0 4 * * * tz="
review: ready-for-go@2026-11-06   # sweep 471de4f9 plan-reviewer: 0 blocking; nonblocking runnability polish for the window agent: q() lives only in §2.3 (define it in §4 fresh shell), replace `get pods -w` with a bounded poll, make §2.2 ABORT stop (`|| { echo ABORT; false; }`) + assert 2 lines in pods.pre, scope §4 rate controls to new pods
status: vetted   # HUMAN-GATED (cluster DNS): operator GO required; never nightly
window: "now:2026-11-06"   # ON-DEMAND NOW run 2026-11-06 (run-now.py stamp; was None)
                                      # or an on-demand NOW run with operator GO as 1.50.0 was. NOT nightly: human-gated
                                      # (SD-11 floor dns/coredns/flux + §5.3 needs a human). NOT stamped.
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/auto-update.md
  - docs/sops/k8s-gateway-dns.md
  - docs/sops/monitoring.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-11-06"
---

# coredns chart 1.50.0 -> 1.50.1 (image unchanged at 1.14.7)

## 1. Summary & why held

**What changes:** the CoreDNS HelmRelease moves from chart 1.50.0 to 1.50.1. The bootstrap
helmfile's coredns pin moves the same way, and the stale CoreDNS row in `docs/infrastructure.md`
(still `1.49.0`) is corrected to `1.50.1`, all in one commit. That commit equals Renovate #481 +
#483 plus the doc fix. CoreDNS keeps running **coredns/coredns:1.14.7** (same digest).
`helm-values.yaml` is not touched.

**The two PRs (#481 / #483) are complementary, not duplicates.** #481 edits only the live
HelmRelease. #483 edits only `kubernetes/bootstrap/apps/helmfile.yaml`, which nothing in the
running cluster reads. Recommendation: land NEITHER by merge. §3's single commit reproduces both
post-images byte-for-byte (blob `89729e391` = #481, `a10bad109` = #483), so Renovate closes both on
its next run, as it did for #469/#470. If the operator insists on a GitHub merge, merge **#481**
(it is the live change and the one with the full CI: Flate Render Gate + Flux Local Diff) and
then #483. Closing #483 unapplied would leave the bootstrap pin behind the live chart, which the
doc-check already flags (F-d6750a2d).

**Why held:** the `*coredns*` deny rule in `runbooks/auto-update-policy.yaml` holds every coredns
bump in the PLAN lane on purpose. The rule exists because a DNS failure disables its own GitOps
revert (source-controller resolves github.com through CoreDNS), and the rule says this component
"should never bump unattended". The hold is **intentional, not a gate false-positive**. The diff
itself is trivial: the hold is about blast radius, not about the change.

**Upstream evidence (primary sources, read 2026-11-06):**
- `helm pull oci://ghcr.io/coredns/charts/coredns` 1.50.0 (`sha256:f606e1c8…`) and 1.50.1
  (`sha256:8d4d6102…`): both `appVersion: 1.14.7`. **appVersion does NOT change.** Flux's
  `HelmRepository/coredns` is OCI (`oci://ghcr.io/coredns/charts`), so that is the artifact Flux
  pulls. The HTTP index agrees: 1.50.1 / 1.14.7, created 2026-11-04.
- Chart changelog annotation for 1.50.1, verbatim: `kind: fixed — "Document that
  prometheus.monitor.enabled needs prometheus.service.enabled unless prometheus.monitor.selector
  is set"`.
- `coredns/helm` compare `coredns-1.50.0...coredns-1.50.1`: 2 commits, `89c413f` "docs: note that
  the ServiceMonitor needs the metrics Service" and its merge (PR #288). Files: `Chart.yaml`,
  `README.md`, `values.yaml`.
- `diff -r` of the two pulled charts: README table text, two COMMENT lines in `values.yaml`, the
  Chart.yaml annotation and version. **No template changed, no value default changed.**

**Rendered diff with OUR values** (`helm template` 1.50.0 vs 1.50.1, `${SECRET_DOMAIN}`
substituted, helm v3.22, 2026-11-06). Only two kinds of change appear:
- 6x `helm.sh/chart: "coredns-1.50.0"` -> `"coredns-1.50.1"`.
- The pod `checksum/config` (`fbe351e5…` -> `7553ea3e…`). It changes because the hashed ConfigMap
  carries the chart label; the Corefile is identical. This triggers the one rolling restart.

Rendered image: `coredns/coredns:1.14.7`. `ipFamilies` occurrences in the render: 0.

**Live state (2026-11-06):**
- HR `1.50.0 1.50.0 True`, helm revision 12 deployed (rev 11 = coredns-1.49.0).
- 2/2 pods, on k8s-nuc14-01 and k8s-nuc14-03; all 3 nodes Ready; no PDB in kube-system.
- imageID `docker.io/coredns/coredns@sha256:7efd3c63…`.
- Corefile sha256 `cf7ccdad…` (unchanged since 2026-11-03).
- kube-dns Service `SingleStack IPv4`.
- Prometheus: `coredns_build_info` 2 series v1.14.7; NOERROR ~18/s, NXDOMAIN ~13/s, no SERVFAIL;
  forwards to `192.168.55.101:53` and `169.254.116.108:53` both NOERROR > 0; 3 http probes = 1;
  0 matching alerts firing. Negative control `does-not-exist-zz9.svc.cluster.local` via the
  kube-dns address exits rc=1.

**Net effect:** one rolling restart of CoreDNS, same mechanics as the 1.49.0 (2026-10-21) and
1.50.0 (2026-11-03) rolls, both green.

**Out of scope, flagged for the operator (not done here):**
- **The image finding stays open.** `F-7eb4c1dc` (image-level security finding on
  `coredns/coredns:1.14.7`; detail on the DB record) is not answered: no chart ships a newer
  CoreDNS yet (1.50.1 still says 1.14.7). Re-pinning `image.tag` ahead of the chart is a separate
  decision, not a window action.
- **Deny rule:** do NOT edit `runbooks/auto-update-policy.yaml` in this window. Keep / narrow /
  remove stays an operator decision.

## 2. Pre-checks (all read-only; abort on any failure)

```bash
cd /Users/mu/code/cberg-home-nextgen
.venv/bin/python3 runbooks/plan-premises.py coredns-1.50.1                  # all PASS
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'                    # header only
flux get helmreleases -A   | awk 'NR==1 || $5 != "True"'                    # header only
git status --short -- kubernetes/apps/kube-system/coredns kubernetes/bootstrap/apps/helmfile.yaml docs/infrastructure.md   # empty
flux get sources git -n flux-system flux-system ; git rev-parse --short origin/main   # same revision (Step 0 settled)
gh pr view 481 --json state -q .state ; gh pr view 483 --json state -q .state         # OPEN OPEN (MERGED -> STOP, re-plan)
helm history coredns -n kube-system --max 3                                 # DEPLOYED revision = 12 (coredns-1.50.0) on 2026-11-06; note it for §5.3
helm show chart oci://ghcr.io/coredns/charts/coredns --version 1.50.1 | grep -E '^(version|appVersion)'   # 1.50.1 / 1.14.7
kubectl get nodes                                                           # prefer 3 Ready (§6 surge note)
date -u +%H:%M                                                              # NOT within 03:50-04:10 UTC (descheduler `0 4 * * *`, no timeZone = UTC = 05:00 CET)
mkdir -p /private/tmp/coredns-1.50.1
```

**2.1 DNS baseline (record it; §4 compares against it).** The lookups run from inside the
blackbox pod, because pod IPs are not routable from the Mac. busybox `nslookup` exits 1 on
NXDOMAIN, so the fourth name is the negative control (measured rc=1 on 2026-11-06). Nothing
survives between shells, so the helpers live in a file every later block sources. The expected
in-cluster answers are LOOKED UP from the live Services, never typed:
```bash
cat > /private/tmp/coredns-1.50.1/fns.sh <<'FNS'
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
FNS
. /private/tmp/coredns-1.50.1/fns.sh && echo "FNS_OK ksvc=$KSVC kdns=$KDNS"
dnsmatrix | tee /private/tmp/coredns-1.50.1/dnsmatrix.pre
kubectl -n monitoring exec deploy/prometheus-blackbox-exporter -- nslookup -type=A kubernetes.default.svc.cluster.local "$KDNS" | awk '/^Name:/{f=1} f&&/^Address/{print "via-kube-dns-vip", $2}' | head -1 | tee /private/tmp/coredns-1.50.1/vip.pre
```
`FNS_OK` must print two non-empty addresses. `vip.pre` must name `$KSVC`.
Expected: 8 lines (2 pod IPs x 4 names):
- `kubernetes.default.svc.cluster.local` -> `rc=0 ans=$KSVC` (measured 2026-11-06: `10.96.0.1`; compare to the looked-up value)
- `sweep` -> `rc=0 ans=192.168.55.103` (the `${SECRET_DOMAIN}` block forwards to k8s-gateway .101)
- `github.com` -> `rc=0` with a public IP (the `.` block forwards to Talos hostDNS)
- `does-not-exist-zz9…` -> `rc=1 ans=NONE`

**Negative control:** if the last line ever reads `rc=0`, the harness cannot detect a failure.
STOP. Do not hold the IP list in a zsh scalar; `for ip in $(…)` word-splits correctly.

**2.2 Corefile, image-digest and Service baseline:**
```bash
kubectl -n kube-system get cm coredns -o jsonpath='{.data.Corefile}' > /private/tmp/coredns-1.50.1/corefile.txt
test -s /private/tmp/coredns-1.50.1/corefile.txt || echo 'ABORT: empty Corefile read'
shasum -a 256 < /private/tmp/coredns-1.50.1/corefile.txt | tee /private/tmp/coredns-1.50.1/corefile.pre
# 2026-11-06: cf7ccdad3e5799e63d642753797489197dbf50db294083622bb9578fde54063d
kubectl -n kube-system get pods -l k8s-app=kube-dns -o jsonpath='{range .items[*]}{.status.containerStatuses[0].imageID}{"\n"}{end}' | sort -u | tee /private/tmp/coredns-1.50.1/imageid.pre
# 1 line: docker.io/coredns/coredns@sha256:7efd3c635b03efd68c4e8398fc45f0d993d0e9ab016f72c1cefb0fd6d01aa286 (2026-11-06)
kubectl -n kube-system get svc kube-dns -o jsonpath='{.spec.clusterIP} {.spec.ipFamilyPolicy} {.spec.ipFamilies[*]} {.spec.ports[*].port}' | tee /private/tmp/coredns-1.50.1/svc.pre
kubectl -n kube-system get pods -l k8s-app=kube-dns -o name | sort | tee /private/tmp/coredns-1.50.1/pods.pre   # 2 names
```

**2.3 Prometheus baseline.** The port-forward stays up for §4.
```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; echo $PF > /private/tmp/coredns-1.50.1/pf.pid; sleep 3
q(){ curl -s --get http://localhost:19090/api/v1/query --data-urlencode "query=$1" \
  | python3 -c "import sys,json; r=json.load(sys.stdin)['data']['result']; print(len(r)); [print(' ',{k:v for k,v in x['metric'].items() if k in ('pod','version','rcode','to','instance','alertname')},x['value'][1]) for x in r]"; }
q 'coredns_build_info'                                                  # 2 series, version="1.14.7"
q 'sum by (rcode)(rate(coredns_dns_responses_total[10m]))'              # NOERROR ~18/s + NXDOMAIN ~13/s (2026-11-06); SERVFAIL absent
q 'sum by (to,rcode)(rate(coredns_proxy_request_duration_seconds_count[10m]))'   # to=192.168.55.101:53 and to=169.254.116.108:53 both NOERROR > 0
q 'min_over_time(probe_success{probe_class="http"}[5m])'               # 3 series, all 1
q 'ALERTS{alertstate="firing",alertname=~"InternalDns.*|IngressProbe.*|Blackbox.*|CoreDNS.*"}'   # 0
```

## 3. Steps (one commit, three files)

The edit was dry-tested with macOS `python3 -I` on scratch copies of all three files from `HEAD`
on 2026-11-06:
- It checks ALL three anchors before writing ANY file.
- It produced exactly the diff below. The resulting blobs are `89729e391` (HelmRelease) and
  `a10bad109` (helmfile), identical to the post-image blob ids of Renovate #481 and #483.
- A second run aborts with `ABORT: helmrelease anchor not found exactly once`.

```bash
cd /Users/mu/code/cberg-home-nextgen
F=kubernetes/apps/kube-system/coredns/app/helmrelease.yaml
B=kubernetes/bootstrap/apps/helmfile.yaml
DOC=docs/infrastructure.md
python3 - "$F" "$B" "$DOC" <<'EOF'
import re, sys
hr, boot, doc = sys.argv[1:4]
s = open(hr).read()
pat = re.compile(r'^      version: 1\.50\.0$', re.M)
if len(pat.findall(s)) != 1: sys.exit("ABORT: helmrelease anchor not found exactly once")
b = open(boot).read()
bpat = re.compile(r'^(    chart: oci://ghcr\.io/coredns/charts/coredns\n    version: )1\.50\.0$', re.M)
if len(bpat.findall(b)) != 1: sys.exit("ABORT: bootstrap helmfile coredns anchor not found exactly once")
t = open(doc).read()
dpat = re.compile(r'^(\| 2 \| CoreDNS \| `oci://ghcr\.io/coredns/charts/coredns` \| )1\.49\.0( \|)', re.M)
if len(dpat.findall(t)) != 1: sys.exit("ABORT: docs/infrastructure.md CoreDNS row anchor not found exactly once")
open(hr, 'w').write(pat.sub('      version: 1.50.1', s))
open(boot, 'w').write(bpat.sub(r'\g<1>1.50.1', b))
open(doc, 'w').write(dpat.sub(r'\g<1>1.50.1\g<2>', t))
print("OK")
EOF
git diff -- "$F" "$B" "$DOC"
git hash-object "$F" "$B"       # 89729e3913c6... and a10bad109f87... (= #481 / #483 post-images)
```
Expected diff (verbatim from the dry run):
```
helmrelease.yaml:
-      version: 1.50.0
+      version: 1.50.1
helmfile.yaml (coredns release):
-    version: 1.50.0
+    version: 1.50.1
docs/infrastructure.md (line 109):
-| 2 | CoreDNS | `oci://ghcr.io/coredns/charts/coredns` | 1.49.0 | kube-system | (chart appVersion 1.14.7 owns ...
+| 2 | CoreDNS | `oci://ghcr.io/coredns/charts/coredns` | 1.50.1 | kube-system | (chart appVersion 1.14.7 owns ...
```
If the script prints `ABORT…`, stop. Do not improvise an edit. Run
`git checkout -- "$F" "$B" "$DOC"` and investigate; a merged #481/#483 or a doc edit by another
session is the likely cause. (If ONLY the doc anchor fails because someone already fixed the
row, it is acceptable to drop `$DOC` from the script and the commit; the two chart hunks are
the change.)

Before committing, confirm the render (helm 3 via mise). The image line must be exactly
`coredns/coredns:1.14.7` and the `ipFamilies` count must be `0`; anything else means the chart
is not doing what §1 says: STOP and `git checkout -- "$F" "$B" "$DOC"`.
```bash
V=kubernetes/apps/kube-system/coredns/app/helm-values.yaml
sed 's/\${SECRET_DOMAIN}/example.test/' "$V" > /private/tmp/coredns-1.50.1/vals.yaml
helm template coredns oci://ghcr.io/coredns/charts/coredns --version 1.50.1 -n kube-system \
  -f /private/tmp/coredns-1.50.1/vals.yaml > /private/tmp/coredns-1.50.1/render.yaml
grep -E '^[[:space:]]*image:' /private/tmp/coredns-1.50.1/render.yaml | tr -d ' "' | sed 's/^image://'   # coredns/coredns:1.14.7
grep -c -i 'ipFamilies' /private/tmp/coredns-1.50.1/render.yaml                                          # 0
```

Commit. Shared worktree: use `--only`, then verify subject and file list BEFORE pushing:
```bash
git commit --only "$F" "$B" "$DOC" -m "fix(kube-system): coredns chart 1.50.0 -> 1.50.1 (appVersion 1.14.7 unchanged, docs-only chart patch); supersedes Renovate #481 #483" \
  -m "Also corrects the stale CoreDNS row in docs/infrastructure.md (F-d6750a2d)." \
  -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git log -1 --format=%s          # must be the subject above, else amend before push
git show --stat HEAD            # exactly the three files
git push
```
Flux picks the change up through the push webhook. No manual reconcile. Do NOT merge or close
#481/#483 by hand: once main carries 1.50.1, Renovate closes them. Watch the roll:
```bash
kubectl -n kube-system get pods -l k8s-app=kube-dns -o wide -w
```
Ctrl-C once 2/2 NEW pods are Ready on 2 distinct nodes (<= 10 min). If the HR does not move
within 10 min, check the webhook and `flux get sources git` before anything else.

## 4. Verification (any FAIL -> §5)

Wait until exactly 2 kube-dns pods are Running and none is Terminating (lameduck 5 s). That gate
also fixes the dnsmatrix line count. Each block runs in a fresh shell: start it with
`. /private/tmp/coredns-1.50.1/fns.sh`, and re-open the §2.3 port-forward if `pf.pid` is dead.

- **Release:**
  ```bash
  kubectl get hr -n kube-system coredns -o jsonpath='{.spec.chart.spec.version} {.status.lastAttemptedRevision} {.status.conditions[?(@.type=="Ready")].status}'
  ```
  - Expected `1.50.1 1.50.1 True`.
  - `helm history coredns -n kube-system --max 2` shows revision 13 `deployed` on
    `coredns-1.50.1`, APP VERSION 1.14.7.
  - A later revision reading `rolled back` means helm's own remediation fired. FAIL.
- **Pods rolled and run the new render:**
  ```bash
  kubectl -n kube-system get pods -l k8s-app=kube-dns -o name | sort | comm -12 - /private/tmp/coredns-1.50.1/pods.pre   # EMPTY = both replaced
  kubectl -n kube-system get pods -l k8s-app=kube-dns -o 'custom-columns=N:.metadata.name,NODE:.spec.nodeName,IMG:.spec.containers[0].image,READY:.status.containerStatuses[0].ready,RS:.status.containerStatuses[0].restartCount'
  kubectl get deploy -n kube-system coredns -o jsonpath='{.metadata.labels.helm\.sh/chart}'
  ```
  - `comm` output must be empty. A surviving old name means the roll did not happen and every
    later gate would measure the old pods. FAIL.
  - 2 pods on 2 distinct nodes, `coredns/coredns:1.14.7`, READY true, RS 0.
  - The Deployment label must print `coredns-1.50.1` (pods carry no chart label).
    `coredns-1.50.0` means the new release did not apply. FAIL.
- CONTENTS ASSERTION: the running image is byte-identical.
  - First `test -s /private/tmp/coredns-1.50.1/imageid.pre` (empty baseline = FAIL, never a
    silent pass).
  - Re-run the §2.2 imageID command and `diff` it against `imageid.pre` (silent = pass). A
    different digest under the same tag is a different image. FAIL.
- CONTENTS ASSERTION: the served Corefile is byte-identical:
  `kubectl -n kube-system get cm coredns -o jsonpath='{.data.Corefile}' | shasum -a 256 | diff - /private/tmp/coredns-1.50.1/corefile.pre`
  (silent = pass). Any difference means the chart altered DNS config (e.g. lost
  `max_connect_attempts 6`). FAIL.
- CONTENTS ASSERTION: the kube-dns Service spec is unchanged: re-run the §2.2 Service jsonpath
  and `diff` against `svc.pre` (silent = pass), and the live clusterIP must equal `$KDNS`. A
  changed clusterIP or family policy breaks every pod's `/etc/resolv.conf` target. FAIL.
- CONTENTS ASSERTION: every NEW replica answers all three name classes and still fails the
  negative control. `dnsmatrix | tee /private/tmp/coredns-1.50.1/dnsmatrix.post`:
  - exactly 8 lines;
  - per IP: cluster name `rc=0 ans=$KSVC`; `sweep` `rc=0 ans=192.168.55.103`; `github.com` `rc=0`
    with an IP; negative control `rc=1 ans=NONE`;
  - re-run the `vip.pre` command; output must equal `vip.pre`;
  - FAIL on any `rc!=0` for the first three names, `rc=0` on the fourth, or < 8 lines. Pod IPs
    differ from the baseline, so compare the `rc=`/`ans=` columns, not whole lines.
- CONTROL: metric coredns_build_info — exactly 2 series, both `version="1.14.7"`, with the NEW
  pod names as `pod`. 0 series means the scrape broke and nothing else here can be trusted. FAIL.
- CONTROL: metric coredns_dns_responses_total — `sum by (rcode)(rate(coredns_dns_responses_total[5m]))`
  5 min after the roll: NOERROR > 0 (floor proving traffic is served, ~18/s on 2026-11-06);
  SERVFAIL not above the §2.3 baseline (absent).
- CONTROL: metric coredns_proxy_request_duration_seconds_count —
  `sum by (to,rcode)(rate(coredns_proxy_request_duration_seconds_count[5m]))`: both
  `to="192.168.55.101:53"` and `to="169.254.116.108:53"` NOERROR > 0 (both forward blocks reach
  their upstreams).
- CONTROL: metric probe_success — `min_over_time(probe_success{probe_class="http"}[5m])` = 1 for
  all 3 http probes. These resolve hostnames through CoreDNS inside the blackbox pod (end-to-end).
  The `dns_*` probes target k8s-gateway .101 directly and stay green with CoreDNS dead, so they
  are NOT a CoreDNS gate.
- CONTROL: alertname IngressProbeFailing — not firing.
- CONTROL: alertname InternalDnsResolutionFailing — not firing (covers k8s-gateway, not CoreDNS;
  listed so a coincident k8s-gateway failure is not misread as this plan's fault).
- **Rollback-path health (a gate that can fail).** Wait >= 2 min after the roll. A bare
  `flux get sources git` shows a fetch made BEFORE the roll and cannot fail. Force a fetch that
  must resolve github.com through the new pods and read back that THIS request was handled:
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
  `lastHandledReconcileAt` is set even when the fetch FAILS, so `HANDLED` only proves an attempt.
  PASS = `HANDLED` AND Ready `True` AND artifact revision equal to the freshly fetched
  `origin/main` (compare, do not remember: other sessions push). FAIL = `NOT_HANDLED_IN_2MIN`, or
  HANDLED with `False` (print the Ready message; a DNS failure lands here), or a stale revision.
  This is the plan's one cluster write: the Flux-documented request annotation (what
  `flux reconcile source git` does), attended, changing no workload.

Finally: `kill $(cat /private/tmp/coredns-1.50.1/pf.pid)`.

## 5. Rollback

**5.1 GitOps revert (default):**
```bash
cd /Users/mu/code/cberg-home-nextgen
SHA=$(git log -1 --format=%h -- kubernetes/apps/kube-system/coredns/app/helmrelease.yaml)
git show --stat "$SHA"          # confirm it is the coredns 1.50.1 commit (3 files)
git revert --no-edit "$SHA" && git log -1 --format=%s && git show --stat HEAD && git push
```
The HR and helmfile return to 1.50.0 (the doc row returns to the stale 1.49.0; fix it to 1.50.0
in a follow-up, not mid-incident). No values change, so no ConfigMap is orphaned. Pods roll
again. Renovate re-opens its 1.50.1 PRs later; expected. Nothing forward-only happens (no CRD,
PVC, migration; same image; same Corefile), so a revert is the complete restore.

**5.2 Confirm the cluster is back.** Re-run §4 against the pre-plan state: HR `1.50.0 1.50.0 True`;
Deployment label `coredns-1.50.0`; imageID = `imageid.pre`, Corefile hash = `corefile.pre`,
Service = `svc.pre`; `dnsmatrix` matches the baseline; rollback-path gate PASS.

**5.3 Break-glass, only if CoreDNS is serving failures and the revert cannot land.** The revert
needs source-controller to resolve github.com THROUGH CoreDNS. Helm's
`upgrade.remediation.strategy: rollback` covers a failed upgrade, not a Ready upgrade that answers
wrongly. If §4 fails AND `flux get sources git` shows no fetch of the revert revision within 5 min
of the push, an operator (never unattended) runs:
```bash
helm history coredns -n kube-system --max 5     # last coredns-1.50.0 revision = 12 (2026-11-06) unless something else ran
flux suspend helmrelease coredns -n kube-system
helm rollback coredns 12 -n kube-system --wait  # use the revision helm history shows for coredns-1.50.0
```
Then push the §5.1 revert. Once `flux get sources git` shows the revert revision, run
`flux resume helmrelease coredns -n kube-system`. This is the plan's only direct cluster mutation
and the reason it is attended.

## 6. Interference notes

- **Execution class: HUMAN-GATED, expected and correct, NOT AUTO-NIGHT.** `touches.shared`
  carries `dns`, `coredns` and `flux`, all in the in-code SD-11 floor (`maintenance-plan.py`
  `SD11_FLOOR`; `dns` is also in `SHARED_INFRA_FLOOR` for SD-10), and `autonomy_override:
  human-gated` states it. `risk: low` does not change that: the gate is the self-revert hazard
  (§5.3 needs a human with `helm` if DNS breaks at 03:30), not the diff. Do not make it eligible
  by editing fields. 35 min fits a `sat-attended` slot (70 usable min); sat-attended:2026-11-07
  had no plan scheduled at authoring time. An on-demand NOW run with an operator GO (as 1.50.0
  ran on 2026-11-03) is equally fine.
- **Run it alone, or last in its window.** No other plan may verify through DNS or Prometheus
  during the ~2-min roll; hence every DNS-, Flux- and monitoring-verifying open plan is in
  `conflicts_with`.
- **Descheduler:** `kube-system/descheduler` CronJob is `0 4 * * *` with no `timeZone` (premise
  `descheduler-schedule-utc`) = 04:00 **UTC** = 05:00 Berlin now (CET). CoreDNS has no
  `priorityClassName` and no PDB, so its pods are evictable. Do not run §3 within ~10 min of
  04:00 UTC (`date -u`). A sat 09:00 Berlin slot (08:00Z) is well clear.
- **Surge scheduling:** maxSurge 25% rounds up to 1 at `replicas: 2`; required anti-affinity over
  the 3 control-plane nodes puts the surge pod on the free node (k8s-nuc14-02 today). With a node
  cordoned/NotReady the roll proceeds via `maxUnavailable: 1` with one replica serving for a few
  seconds; prefer all 3 Ready at §2.
- **Renovate:** do not merge #481/#483 separately; §3's single commit is byte-identical to both
  and adds the doc fix.
- **Findings:** after execution, close the agent-visible rows in the same turn:
  `runbooks/policy-cli.py finding close F-3893caaf --commit <sha>` and
  `runbooks/policy-cli.py finding close F-d6750a2d --commit <sha>` (the latter is script-produced
  and may also self-resolve on the next doc-check). Do NOT close `F-7eb4c1dc`; this plan does not
  move the image.
- Retire this file in the commit that records execution.
