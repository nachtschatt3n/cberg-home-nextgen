---
plan_id: coredns-1.50.0
component: coredns
pr: 469                               # Renovate #469 = HelmRelease 1.49.0 -> 1.50.0. Its twin #470 bumps the SAME
                                      # chart in kubernetes/bootstrap/apps/helmfile.yaml. Both are held by the
                                      # `*coredns*` deny rule; CI green on both (Flate Render Gate + Flux Local Diff,
                                      # 2026-11-03). §3 makes ONE commit whose two hunks have the same git blob ids
                                      # as the PRs (404ba5c57 / bd4ac465c, measured on a scratch copy 2026-11-03),
                                      # so Renovate closes both as already applied.
kind: chart
current: "chart 1.49.0 (appVersion 1.14.7), no image pin"
target: "1.50.0"                      # chart 1.50.0, appVersion 1.14.7 (unchanged) - image does NOT move
update_type: minor                    # chart minor; image unchanged (coredns/coredns:1.14.7 -> 1.14.7)
risk: low                             # MEASURED 2026-11-03: `helm template` 1.49.0 vs 1.50.0 with our exact values
                                      # differs ONLY in 6x helm.sh/chart labels + pod checksum/config (Corefile
                                      # identical). The one functional chart change (optional service.ipFamilies) is
                                      # unset by us and renders nothing. Net effect = one rolling restart, the same
                                      # roll the 1.49.0 bump did green on 2026-10-21. Impact class (cluster DNS, and a
                                      # DNS failure disables its own git revert) is carried by the SD-11 `dns`/`coredns`
                                      # floor + autonomy_override, not by inflating risk.
est_duration_min: 35                  # §2 10 + §3 5 + Flux pickup/roll ~5 + §4 10 (incl. 5 min rate window) + slack 5
needs_reboot: false
exclusive: false
touches:
  namespaces: [kube-system]
  resources:
    - helmrelease/kube-system/coredns                   # chart 1.49.0 -> 1.50.0 (helm revision 11 -> 12)
    - deployment/kube-system/coredns                    # 2 replicas, RollingUpdate maxUnavailable 1 / maxSurge 25%,
                                                        # lameduck 5s, required anti-affinity on the 3 control-plane
                                                        # nodes; no PDB, no priorityClassName (measured 2026-11-03)
    - configmap/kube-system/coredns                     # label only; Corefile must be byte-identical
    - service/kube-system/kube-dns                      # label only; the template gained an ipFamilies block that
                                                        # renders nothing for us (clusterIP + SingleStack IPv4 unchanged;
                                                        # the address is LOOKED UP in §2.2, never typed)
    - serviceaccount/kube-system/coredns                # label only
    - clusterrole/coredns                               # label only
    - clusterrolebinding/coredns                        # label only
    - kubernetes/apps/kube-system/coredns/app/helmrelease.yaml
    - kubernetes/bootstrap/apps/helmfile.yaml           # bootstrap-only pin (Renovate #470); no live object reads it
                                                        # helm-values.yaml is NOT edited -> no new coredns-helm-values-<hash>
  shared:
    - dns                             # SD-11 floor token: cluster DNS for every pod in the cluster
    - coredns                         # SD-11 floor token; the ${SECRET_DOMAIN} block forwards to k8s-gateway
                                      # 192.168.55.101, `.` forwards to Talos hostDNS 169.254.116.108
    - flux                            # source-controller resolves github.com THROUGH CoreDNS = this plan's revert path
    - monitoring                      # §4 reads Prometheus + execs into blackbox (read-only; the instrument is shared)
depends_on: []
conflicts_with:
  # Every open (non-terminal) plan whose execution or verification touches cluster DNS, the HR apply/revert path
  # (Flux controllers, sources, drift), kube-system pod placement, or the Prometheus/blackbox instrument §4 reads.
  # Plan set re-read 2026-11-03 via `maintenance-plan.py --open` + frontmatter scan.
  - talos-linux-1.14.5                # exclusive node roll; reschedules both CoreDNS pods (lists `coredns` in shared)
  - etcd-timeouts-5000-500            # control-plane service restarts; CoreDNS's kubernetes plugin watches the apiserver
  - flux-fleet-0.62.1                 # operator/instance charts; this plan's revert path (git push -> source-controller -> DNS) must not share a night with a Flux control-plane roll
                                      # (flux-fleet-0.62.0 dropped 2026-11-03: superseded by 0.62.1)
  - flux-reconciler-impersonation     # exclusive; changes how helm-controller applies this HR
  - flux-oci-chart-sources            # moves HelmRepository sources and re-applies kube-system HRs (stage 3)
  - helm-drift-detection              # adds driftDetection to every HR incl. this one
  - descheduler-0.37.0                # kube-system CronJob that can evict CoreDNS (no priorityClassName) mid-roll
  - authentik-2026.8.5                # same namespace (kube-system); its gates resolve through CoreDNS
  - envoy-proxy-config-distroless-v1.39.4   # its §4 reads probe_success + resolves through CoreDNS
  - envoy-proxy-config-distroless-v1.40.0   # same surface
  - envoy-proxy-config-distroless-v1.40.2   # same surface
  - edot-collector-0.164.0            # its ES exporters resolve through CoreDNS; reads the same monitoring surface
  - redis-fleet-8.10.3                # consumers re-resolve on reconnect
  # NOT listed, checked 2026-11-03: no kube-prometheus-stack / blackbox / cilium plan is open (if one appears it MUST
  # be added: §4 reads Prometheus and execs into blackbox). talos-power-tuning-ab and longhorn-1.13.0 are
  # exclusive (serialized by slot anyway) and have no DNS surface. Superseded coredns-1.48.1 is terminal.
capability_change: false              # same image coredns/coredns:1.14.7 (same digest), byte-identical Corefile,
                                      # same Service spec; the only new chart capability (service.ipFamilies) is
                                      # unset by our values and renders nothing - measured, §1
rollback_class: git-revert
autonomy_override: human-gated        # `dns`/`coredns` are in the SD-11 floor anyway; §5.3 break-glass needs a human
security_ref: null                    # not security-driven. NB: this bump does NOT change the image, so it does not
                                      # answer the open image finding F-7eb4c1dc (see §1 "Out of scope").
finding_refs: []                      # `policy-cli.py finding list --grep {coredns,1.50.0,charts/coredns,CoreDNS}`
                                      # 2026-11-03: no chart-version row for 1.49.0 -> 1.50.0 exists. The only open
                                      # coredns rows are image/security (F-7eb4c1dc, F-abfa63ba) and health
                                      # (F-be7c319e, F-44a4e9fd), none of which this plan answers. Add the version
                                      # finding's id here if the next sweep files one.
premises:
  # All read-only single commands. Values measured live 2026-11-03.
  - id: coredns-live-image-and-replicas
    why: >-
      §4 asserts the image does NOT change (chart 1.50.0 appVersion = 1.14.7 = live). If the live image or replica
      count differs, the imageID and 8-line dnsmatrix gates are wrong. Prints a different string and fails.
    run: kubectl get deploy -n kube-system coredns -o jsonpath='{.spec.template.spec.containers[0].image} {.spec.replicas} {.status.readyReplicas}'
    expect_exact: "coredns/coredns:1.14.7 2 2"
  - id: coredns-hr-chart
    why: >-
      HelmRelease must be Ready on 1.49.0. A failed/in-flight release, or #469 merged behind the plan's back
      (1.50.0 already live), makes §3's anchor and the §5 rollback target wrong.
    run: kubectl get helmrelease -n kube-system coredns -o jsonpath='{.spec.chart.spec.version} {.status.lastAttemptedRevision} {.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "1.49.0 1.49.0 True"
  - id: kube-dns-service-spec
    why: >-
      The only functional template change in 1.50.0 is an optional ipFamilies block on this Service. §4 asserts the
      Service spec is unchanged; this records the pre-state it compares against. The clusterIP is NOT hardcoded
      here (a Service address is cluster-assigned): §2.2 reads it into svc.pre and §4 diffs against that file.
    run: kubectl get svc -n kube-system kube-dns -o jsonpath='{.spec.clusterIP} {.spec.ipFamilyPolicy} {.spec.ipFamilies[*]}'
    expect_matches: '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+ SingleStack IPv4$'
  - id: repo-hr-anchor
    why: >-
      §3's edit anchors on exactly one `version: 1.49.0` line in the committed HelmRelease. Prints 0 if main moved.
    run: "git show HEAD:kubernetes/apps/kube-system/coredns/app/helmrelease.yaml | grep -c 'version: 1.49.0'"
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
review: ready-for-go@2026-11-03   # plan-reviewer 2026-11-03: ready-for-go; operator GO recorded for a NOW run 2026-11-03
status: vetted
window: null                          # RECOMMENDED sat-attended:2026-11-07 (09:00 Berlin, 35 of 70 usable min): human-gated and its section 4/5.3 need an operator, so NOT the
                                      # unattended nightly; flux-fleet-0.62.1 takes nightly:2026-11-07. NOT stamped.
                                      # (earlier draft said nightly:2026-11-07, which collided: flux-fleet-0.62.1 is a declared conflicts_with
                                      # here and 70 of 70 min). Operator confirms the slot; check the scheduler does not already hold sat-attended:2026-11-07.)
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/auto-update.md
  - docs/sops/k8s-gateway-dns.md
  - docs/sops/monitoring.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-11-03"
---

# coredns chart 1.49.0 -> 1.50.0 (image unchanged at 1.14.7)

## 1. Summary & why held

**What changes:** the CoreDNS HelmRelease moves from chart 1.49.0 to 1.50.0. The bootstrap
helmfile's coredns pin moves the same way in the same commit, which is exactly Renovate #469 plus
#470. CoreDNS keeps running **coredns/coredns:1.14.7** (same digest). `helm-values.yaml` is not
touched.

**Why held:** the `*coredns*` deny rule in `runbooks/auto-update-policy.yaml` holds every coredns
bump in the PLAN lane on purpose. Its reason (rewritten 2026-10-21 when 1.49.0 landed and the
image pin was dropped) says the pin hazard is gone. The rule stays because a DNS failure disables
its own GitOps revert (source-controller resolves github.com through CoreDNS), "so this component
should never bump unattended". The hold is therefore **intentional, not a gate false-positive**.
The CHANGE itself is trivial: the hold is about blast radius, not about the diff.

**Upstream evidence (primary sources, read 2026-11-03):**
- `helm pull oci://ghcr.io/coredns/charts/coredns` 1.49.0 and 1.50.0 (digests `ad5d2d95…` and
  `f606e1c8…`): both `appVersion: 1.14.7`. Flux's `HelmRepository/coredns` is `type: oci`,
  `oci://ghcr.io/coredns/charts`, so that is the artifact Flux pulls. The HTTP index
  (`coredns.github.io/helm/index.yaml`) agrees: 1.50.0 / 1.14.7, created 2026-11-02.
- artifacthub change note for 1.50.0, verbatim: `kind: added — "Expose service.ipFamilies in values"`.
- `coredns/helm` compare `coredns-1.49.0...coredns-1.50.0`: 7 commits. Four are dependabot CI
  bumps (docker/login-action, chart-releaser-action) and their merges. One is the version bump.
  The only chart change is `4daa49f` "feat: Expose service.ipFamilies in values" (PR #286).
- Full file diff of the two pulled charts: `templates/service.yaml` gains
  `{{- if .Values.service.ipFamilies }} ipFamilies: … {{- end }}`. `values.yaml` gains only a
  COMMENTED `# ipFamilies: []`. There are also README and unit-test lines. No other template
  changed.

**Rendered diff with OUR values** (`helm template` 1.49.0 vs 1.50.0, `${SECRET_DOMAIN}`
substituted, helm v3.22.1, 2026-11-03). Only two kinds of change appear:
- 6× `helm.sh/chart: "coredns-1.49.0"` → `"coredns-1.50.0"`.
- The pod `checksum/config` (`1fa7cd8d…` → `fbe351e5…`). It changes because the hashed
  ConfigMap carries the chart label; the Corefile is identical. This is what triggers the one
  rolling restart.

The Service renders NO `ipFamilies` field (we do not set `service.ipFamilies`), so the live
`SingleStack` / `IPv4` / clusterIP (the value recorded in `svc.pre`, §2.2) is untouched. Rendered image: `coredns/coredns:1.14.7`.

**Live state (2026-11-03):**
- HR `1.49.0 1.49.0 True`, helm revision 11 deployed.
- 2/2 pods, on nuc14-01 and nuc14-02.
- Both pods already run with `runAsUser 65532`, SA `coredns`, imageID
  `sha256:7efd3c63…`.
- Corefile sha256 `cf7ccdad…`.
- dnsmatrix 8/8 as expected, including the negative control.

**Net effect:** one rolling restart of CoreDNS. It is the same mechanics the 1.49.0 bump ran green
on 2026-10-21 (3f34eb84).

**Out of scope, flagged for the operator (not done here):**
- **The image finding stays open.** `F-7eb4c1dc` (image-level security finding on
  `coredns/coredns:1.14.7`; detail on the DB record) says a newer upstream tag exists. CoreDNS
  **v1.15.0** was released 2026-10-21, but no chart ships it yet (1.50.0 still says 1.14.7). This
  plan does not move the image, so it does not answer that finding.
- **Getting 1.15.0 before the chart ships it** would mean re-adding an `image.tag` pin. That
  re-creates exactly the pin-ahead-of-chart hazard 1.49.0 removed, and 1.14.x→1.15.0 is a
  minor with its own plugin changes. That is a separate plan/decision, not a window action here.
- **Deny rule:** do NOT edit `runbooks/auto-update-policy.yaml` in this window. Keep, narrow or
  remove stays an operator decision. The rule text itself says so.

## 2. Pre-checks (all read-only; abort on any failure)

```bash
cd /Users/mu/code/cberg-home-nextgen
.venv/bin/python3 runbooks/plan-premises.py coredns-1.50.0                  # all PASS
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'                    # header only
flux get helmreleases -A   | awk 'NR==1 || $5 != "True"'                    # header only
git status --short -- kubernetes/apps/kube-system/coredns kubernetes/bootstrap/apps/helmfile.yaml   # empty
flux get sources git -n flux-system flux-system ; git rev-parse --short origin/main   # same revision (Step 0 settled)
gh pr view 469 --json state -q .state ; gh pr view 470 --json state -q .state         # OPEN OPEN (MERGED -> STOP, re-plan)
helm history coredns -n kube-system --max 3                                 # DEPLOYED revision = 11 on 2026-11-03; note it for §5.3
helm show chart oci://ghcr.io/coredns/charts/coredns --version 1.50.0 | grep -E '^(version|appVersion)'   # 1.50.0 / 1.14.7
date -u +%H:%M                                                              # NOT within 03:50-04:10 UTC (descheduler CronJob `0 4 * * *`, NO timeZone => the controller-manager clock = UTC; 05:00 CET / 06:00 CEST)
mkdir -p /private/tmp/coredns-1.50.0
```

**2.1 DNS baseline (record it; §4 compares against it).** The lookups run from inside the
blackbox pod, because pod IPs are not routable from the Mac. busybox `nslookup` exits 1 on
NXDOMAIN, so the fourth name is the negative control.
Nothing survives between shells, so the helpers live in a file that every later block
sources (`. /private/tmp/coredns-1.50.0/fns.sh`). The expected in-cluster answers are LOOKED UP
from the live Services (`kubernetes` in `default`, `kube-dns` in `kube-system`), never typed:
```bash
cat > /private/tmp/coredns-1.50.0/fns.sh <<'FNS'
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
. /private/tmp/coredns-1.50.0/fns.sh && echo "FNS_OK ksvc=$KSVC kdns=$KDNS"
dnsmatrix | tee /private/tmp/coredns-1.50.0/dnsmatrix.pre
# The Service address itself (what pods really use) must answer too:
kubectl -n monitoring exec deploy/prometheus-blackbox-exporter -- nslookup -type=A kubernetes.default.svc.cluster.local "$KDNS" | awk '/^Name:/{f=1} f&&/^Address/{print "via-kube-dns-vip", $2}' | head -1 | tee /private/tmp/coredns-1.50.0/vip.pre
```
`FNS_OK` must print with two non-empty addresses (an empty lookup aborts the file, so
nothing downstream can pass on a blank expectation). `vip.pre` must equal `$KSVC`.
Expected: 8 lines (2 pod IPs × 4 names), measured live 2026-11-03:
- `kubernetes.default.svc.cluster.local` → `rc=0 ans=$KSVC` (measured 2026-11-03: `10.96.0.1`; compare to the looked-up value, not to this number)
- `sweep` → `rc=0 ans=192.168.55.103` (the `${SECRET_DOMAIN}` block forwards to k8s-gateway .101)
- `github.com` → `rc=0` with a public IP (the `.` block forwards to Talos hostDNS)
- `does-not-exist-zz9…` → `rc=1 ans=NONE`

**Negative control:** if the last line ever reads `rc=0`, the harness cannot detect a failure.
STOP. Do not hold the IP list in a scalar. `for ip in $(…)` word-splits correctly under zsh; a
scalar does not.

**2.2 Corefile, image-digest and Service baseline:**
```bash
kubectl -n kube-system get cm coredns -o jsonpath='{.data.Corefile}' > /private/tmp/coredns-1.50.0/corefile.txt
test -s /private/tmp/coredns-1.50.0/corefile.txt || echo 'ABORT: empty Corefile read'
shasum -a 256 < /private/tmp/coredns-1.50.0/corefile.txt | tee /private/tmp/coredns-1.50.0/corefile.pre
# 2026-11-03: cf7ccdad3e5799e63d642753797489197dbf50db294083622bb9578fde54063d
kubectl -n kube-system get pods -l k8s-app=kube-dns -o jsonpath='{range .items[*]}{.status.containerStatuses[0].imageID}{"\n"}{end}' | sort -u | tee /private/tmp/coredns-1.50.0/imageid.pre
# 1 line: docker.io/coredns/coredns@sha256:7efd3c635b03efd68c4e8398fc45f0d993d0e9ab016f72c1cefb0fd6d01aa286 (2026-11-03)
kubectl -n kube-system get svc kube-dns -o jsonpath='{.spec.clusterIP} {.spec.ipFamilyPolicy} {.spec.ipFamilies[*]} {.spec.ports[*].port}' | tee /private/tmp/coredns-1.50.0/svc.pre
test "$(cut -d' ' -f1 /private/tmp/coredns-1.50.0/svc.pre)" = "$(kubectl -n kube-system get svc kube-dns -o jsonpath='{.spec.clusterIP}')" && echo SVC_PRE_OK   # looked up, then re-read: the address recorded is the live one
kubectl -n kube-system get pods -l k8s-app=kube-dns -o name | sort | tee /private/tmp/coredns-1.50.0/pods.pre   # 2 names
```

**2.3 Prometheus baseline.** The port-forward stays up for §4.
```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; echo $PF > /private/tmp/coredns-1.50.0/pf.pid; sleep 3
q(){ curl -s --get http://localhost:19090/api/v1/query --data-urlencode "query=$1" \
  | python3 -c "import sys,json; r=json.load(sys.stdin)['data']['result']; print(len(r)); [print(' ',{k:v for k,v in x['metric'].items() if k in ('pod','version','rcode','to','instance','alertname')},x['value'][1]) for x in r]"; }
q 'coredns_build_info'                                                  # 2 series, version="1.14.7"
q 'sum by (rcode)(rate(coredns_dns_responses_total[10m]))'              # NOERROR ~18/s + NXDOMAIN ~12/s (2026-11-03); record SERVFAIL (absent)
q 'sum by (to,rcode)(rate(coredns_proxy_request_duration_seconds_count[10m]))'   # to=192.168.55.101:53 and to=169.254.116.108:53 both NOERROR > 0
q 'min_over_time(probe_success{probe_class="http"}[5m])'               # 3 series, all 1
q 'ALERTS{alertstate="firing",alertname=~"InternalDns.*|IngressProbe.*|Blackbox.*|CoreDNS.*"}'   # 0
```

## 3. Steps (one commit, two files)

The edit was dry-tested with macOS `python3 -I` on scratch copies of both files on 2026-11-03:
- It checks BOTH anchors before writing EITHER file.
- It produced exactly the diff below. The resulting blobs are `404ba5c57` (HelmRelease) and
  `bd4ac465c` (helmfile), identical to the post-image blob ids of Renovate #469 and #470.
- A second run aborts with `ABORT: helmrelease anchor not found exactly once`.

```bash
cd /Users/mu/code/cberg-home-nextgen
F=kubernetes/apps/kube-system/coredns/app/helmrelease.yaml
B=kubernetes/bootstrap/apps/helmfile.yaml
python3 - "$F" "$B" <<'EOF'
import re, sys
hr, boot = sys.argv[1:3]
s = open(hr).read()
pat = re.compile(r'^      version: 1\.49\.0$', re.M)
if len(pat.findall(s)) != 1: sys.exit("ABORT: helmrelease anchor not found exactly once")
b = open(boot).read()
bpat = re.compile(r'^(    chart: oci://ghcr\.io/coredns/charts/coredns\n    version: )1\.49\.0$', re.M)
if len(bpat.findall(b)) != 1: sys.exit("ABORT: bootstrap helmfile coredns anchor not found exactly once")
open(hr, 'w').write(pat.sub('      version: 1.50.0', s))
open(boot, 'w').write(bpat.sub(r'\g<1>1.50.0', b))
print("OK")
EOF
git diff -- "$F" "$B"
git hash-object "$F" "$B"       # 404ba5c578a7... and bd4ac465c47f... (= #469 / #470 post-images)
```
Expected diff (verbatim from the dry run):
```
helmrelease.yaml:
-      version: 1.49.0
+      version: 1.50.0
helmfile.yaml (coredns release):
-    version: 1.49.0
+    version: 1.50.0
```
If the script prints `ABORT…`, stop. Do not improvise an edit. Run `git checkout -- "$F" "$B"`
and investigate; a merged #469/#470 is the likely cause.

Before committing, confirm the render (helm 3 via mise). Two checks:
- The image line must be exactly one line, `coredns/coredns:1.14.7`.
- The `ipFamilies` count must be `0`.

Any other result means the chart is not doing what §1 says. STOP and run
`git checkout -- "$F" "$B"`.
```bash
V=kubernetes/apps/kube-system/coredns/app/helm-values.yaml
sed 's/\${SECRET_DOMAIN}/example.test/' "$V" > /private/tmp/coredns-1.50.0/vals.yaml
helm template coredns oci://ghcr.io/coredns/charts/coredns --version 1.50.0 -n kube-system \
  -f /private/tmp/coredns-1.50.0/vals.yaml > /private/tmp/coredns-1.50.0/render.yaml
grep -E '^[[:space:]]*image:' /private/tmp/coredns-1.50.0/render.yaml | tr -d ' "' | sed 's/^image://'   # coredns/coredns:1.14.7
grep -c -i 'ipFamilies' /private/tmp/coredns-1.50.0/render.yaml                                          # 0
```

Commit. This is a shared worktree, so use `--only`, then verify the subject and file list BEFORE
pushing:
```bash
git commit --only "$F" "$B" -m "feat(kube-system): coredns chart 1.49.0 -> 1.50.0 (appVersion 1.14.7 unchanged); supersedes Renovate #469 #470" \
  -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git log -1 --format=%s          # must be the subject above, else amend before push
git show --stat HEAD            # exactly the two files
git push
```
Flux picks the change up through the push webhook. No manual reconcile. Do NOT merge or close
#469/#470 by hand: once main carries 1.50.0, Renovate closes them on its next run. Watch the roll:
```bash
kubectl -n kube-system get pods -l k8s-app=kube-dns -o wide -w
```
Press Ctrl-C once 2/2 NEW pods are Ready on 2 distinct nodes (≤10 min). If the HR does not move
within 10 min, check the webhook and `flux get sources git` before anything else.

## 4. Verification (any FAIL → §5)

Wait until exactly 2 kube-dns pods are Running and none is Terminating (lameduck 5 s) before
starting. That gate also fixes the dnsmatrix line count. Each block runs in a fresh shell:
start it with `. /private/tmp/coredns-1.50.0/fns.sh` (defines `D`, `KSVC`, `KDNS`, `dnsmatrix`),
and for the Prometheus reads re-open the port-forward from §2.3 if `pf.pid` is no longer alive.

- **Release:**
  ```bash
  kubectl get hr -n kube-system coredns -o jsonpath='{.spec.chart.spec.version} {.status.lastAttemptedRevision} {.status.conditions[?(@.type=="Ready")].status}'
  ```
  - Expected output: `1.50.0 1.50.0 True`.
  - `helm history coredns -n kube-system --max 2` shows revision 12 `deployed` on
    `coredns-1.50.0`, APP VERSION 1.14.7.
  - Any later revision reading `rolled back` means helm's own remediation fired. FAIL.
- **Pods rolled and run the new render:**
  ```bash
  kubectl -n kube-system get pods -l k8s-app=kube-dns -o name | sort | comm -12 - /private/tmp/coredns-1.50.0/pods.pre   # EMPTY = both replaced
  kubectl -n kube-system get pods -l k8s-app=kube-dns -o 'custom-columns=N:.metadata.name,NODE:.spec.nodeName,IMG:.spec.containers[0].image,READY:.status.containerStatuses[0].ready,RS:.status.containerStatuses[0].restartCount,CHART:.metadata.labels.helm\.sh/chart'
  ```
  - The `comm` output must be empty. A surviving old name means the roll did not happen, so every
    later gate would be measuring the old pods. FAIL.
  - Expected: 2 pods on 2 distinct nodes, `coredns/coredns:1.14.7`, READY true, RS 0.
  - Pods carry no chart label, so CHART reads `<none>`. That is expected. Read the chart label
    from the Deployment instead:
    `kubectl get deploy -n kube-system coredns -o jsonpath='{.metadata.labels.helm\.sh/chart}'`
    must print `coredns-1.50.0`. Printing `coredns-1.49.0` means the new release did not apply.
    FAIL.
- CONTENTS ASSERTION: the running image is byte-identical to the pre-change one.
  - First assert `test -s /private/tmp/coredns-1.50.0/imageid.pre`. An empty baseline is a FAIL,
    never a silent pass.
  - Then re-run the §2.2 `imageID` command and `diff` it against
    `/private/tmp/coredns-1.50.0/imageid.pre` (silent = pass).
  - A different digest means a different image even under the same tag. FAIL.
- CONTENTS ASSERTION: the served Corefile is byte-identical.
  - Measured by
    `kubectl -n kube-system get cm coredns -o jsonpath='{.data.Corefile}' | shasum -a 256 | diff - /private/tmp/coredns-1.50.0/corefile.pre`
    (silent = pass).
  - The render diff says the Corefile does not change, so any difference means the chart altered
    the DNS config, for example `max_connect_attempts 6` was lost. FAIL.
- CONTENTS ASSERTION: the kube-dns Service spec is unchanged. This is the one template 1.50.0
  modified.
  - Measured by re-running the §2.2 Service jsonpath and `diff`-ing it against
    `/private/tmp/coredns-1.50.0/svc.pre` (silent = pass; `<clusterIP> SingleStack IPv4 53 53 …`
    with the SAME clusterIP that §2.2 looked up, also re-read live: `kubectl -n kube-system get svc kube-dns -o jsonpath='{.spec.clusterIP}'`
    must equal `$KDNS`).
  - A changed clusterIP or family policy here would break every pod's `/etc/resolv.conf`
    target. FAIL.
- CONTENTS ASSERTION: every NEW replica answers all three name classes correctly and still fails
  the negative control.
  - Measured by `dnsmatrix | tee /private/tmp/coredns-1.50.0/dnsmatrix.post` (the §2.1 function,
    run against the NEW pod IPs).
  - Required: exactly 8 lines.
  - Required per IP:
    - cluster name: `rc=0 ans=$KSVC` (the looked-up `kubernetes` Service address)
    - the Service address answers too: re-run the `vip.pre` command; the result must equal `vip.pre`
    - `sweep`: `rc=0 ans=192.168.55.103`
    - `github.com`: `rc=0` with an IP
    - negative control: `rc=1 ans=NONE`
  - FAIL on any `rc≠0` for the first three names, `rc=0` on the fourth, or fewer than 8 lines.
  - The pod IPs differ from the baseline, so compare the `ans=` and `rc=` columns, not whole
    lines.
- CONTROL: metric coredns_build_info — exactly 2 series, both `version="1.14.7"`, with the NEW
  pod names as `pod` labels. 0 series means the scrape broke, and then nothing else in this list
  can be trusted. FAIL.
- CONTROL: metric coredns_dns_responses_total — read
  `sum by (rcode)(rate(coredns_dns_responses_total[5m]))` 5 min after the roll.
  - NOERROR must be > 0. This is a floor that proves traffic is being served (~18/s on
    2026-11-03).
  - SERVFAIL must not be above the §2.3 baseline (absent on 2026-11-03).
- CONTROL: metric coredns_proxy_request_duration_seconds_count — read
  `sum by (to,rcode)(rate(coredns_proxy_request_duration_seconds_count[5m]))`. Both
  `to="192.168.55.101:53"` and `to="169.254.116.108:53"` must show NOERROR > 0. This proves both
  forward blocks still reach their upstreams.
- CONTROL: metric probe_success — `min_over_time(probe_success{probe_class="http"}[5m])` must be
  1 for all 3 http probes.
  - These probes resolve their hostnames through CoreDNS inside the blackbox pod, so they are the
    Prometheus-side end-to-end check.
  - The two `dns_*` probes are NOT a CoreDNS gate. They target k8s-gateway .101 directly and stay
    green even if CoreDNS is dead.
- CONTROL: alertname IngressProbeFailing — not firing.
- CONTROL: alertname InternalDnsResolutionFailing — not firing. This alert covers k8s-gateway,
  not CoreDNS. It is listed so that a coincident k8s-gateway failure is not misread as this plan's
  fault.
- **Rollback-path health (a gate that can fail).** Wait ≥ 2 min after the roll completes. A bare
  `flux get sources git` only shows the LAST result and prints READY `True` from a fetch made
  BEFORE the roll, so it cannot fail. Force a fetch that must resolve github.com through the new
  CoreDNS pods and read back that source-controller handled THIS request:
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
  `lastHandledReconcileAt` is set by source-controller even when the fetch FAILS, so `HANDLED`
  only proves a reconcile was attempted after the roll. The DNS proof is the clause read AFTER
  `HANDLED`: `Ready=True` plus an artifact revision equal to a freshly fetched `origin/main`
  (`git fetch origin` first, then `git rev-parse origin/main`; another session's push moves both,
  so compare, do not remember). PASS = `HANDLED` AND `True` AND equal revisions. FAIL =
  `NOT_HANDLED_IN_2MIN` (source-controller not reconciling), or HANDLED with `False` (print the
  Ready message: a DNS failure lands here), or a stale revision. Read the Ready status only after HANDLED. This is the one place the plan writes to the cluster: a
  Flux-documented request annotation on a Flux source (what `flux reconcile source git` does), in an
  attended window, to prove the revert path; it changes no workload. It can fail: before the
  request the field holds an older token, so a missing handle prints `NOT_HANDLED_IN_2MIN`.

Finally: `kill $(cat /private/tmp/coredns-1.50.0/pf.pid)`.

## 5. Rollback

**5.1 GitOps revert (default):**
```bash
cd /Users/mu/code/cberg-home-nextgen
SHA=$(git log -1 --format=%h -- kubernetes/apps/kube-system/coredns/app/helmrelease.yaml)
git show --stat "$SHA"          # confirm it is the coredns 1.50.0 commit (2 files)
git revert --no-edit "$SHA" && git log -1 --format=%s && git show --stat HEAD && git push
```
What happens:
- The HR and the helmfile return to chart 1.49.0. There is no values change, so no ConfigMap is
  orphaned or re-pointed.
- The pods roll again.
- Renovate will re-open its 1.50.0 PRs later. That is expected.

Nothing forward-only happens in this plan: no CRD, no PVC, no migration, the same image, and the
same Corefile. A revert is therefore the complete restore.

**5.2 Confirm the cluster is back.** Re-run §4 against the pre-plan state:
- HR reads `1.49.0 1.49.0 True`.
- The Deployment label reads `helm.sh/chart=coredns-1.49.0`.
- imageID equals `imageid.pre`, the Corefile hash equals `corefile.pre`, and the Service spec
  equals `svc.pre`.
- `dnsmatrix` matches the baseline.

**5.3 Break-glass, only if CoreDNS is serving failures and the revert cannot land.** The GitOps
revert needs source-controller to resolve github.com THROUGH CoreDNS. Helm's own
`upgrade.remediation.strategy: rollback` covers a failed upgrade. It does not cover an upgrade
that is Ready but answers wrongly. If §4 fails AND `flux get sources git` shows no fetch of the
revert revision within 5 min of the push, an operator (never unattended) runs:
```bash
helm history coredns -n kube-system --max 5     # last coredns-1.49.0 revision = 11 (2026-11-03) unless something else ran
flux suspend helmrelease coredns -n kube-system
helm rollback coredns 11 -n kube-system --wait  # use the revision helm history shows for coredns-1.49.0
```
Then push the §5.1 revert. Once `flux get sources git` shows the revert revision, run
`flux resume helmrelease coredns -n kube-system`. This is the plan's only direct cluster mutation,
and it is why the plan is attended.

## 6. Interference notes

- **Execution class: HUMAN-GATED, expected and correct.** `touches.shared` carries `dns`,
  `coredns` and `flux`, all of which are in the in-code SD-11 floor (`maintenance-plan.py`
  `sd11_eligibility()`). `autonomy_override: human-gated` states it explicitly. The reason is not
  the diff, which is labels-only. The reason is §5.3: a DNS failure at 03:30 disables the GitOps
  revert and needs a human with `helm`. This plan is not eligible for SD-10/SD-11 nightly
  pre-approval, and must not be made so by editing fields. 35 min fits a `sat-attended` slot.
- **Run it alone, or last in its window.** No other plan may verify through DNS or Prometheus
  during the ~2-min roll. That is why every DNS-, Flux- and monitoring-verifying open plan is in
  `conflicts_with`. For the exclusive plans (talos-linux-1.14.5, flux-reconciler-impersonation)
  the entry is belt and braces.
- **Descheduler:** the `kube-system/descheduler` CronJob (`0 4 * * *`, no `timeZone`, live
  re-read 2026-11-03) runs at 04:00 **UTC** = 05:00 Berlin in winter (CET), 06:00 in summer
  (CEST). An earlier draft read it as 04:00 local. CoreDNS has no
  `priorityClassName` and no PDB, so its pods are evictable. Do not run §3 within ~10 min of 04:00 UTC
  (check with `date -u`). A nightly 03:30 Berlin start (= 02:30Z) ends ~03:05Z, 55 min clear; an
  attended sat 09:00 Berlin slot (= 08:00Z) is past it:
  an eviction mid-roll would read as a plan failure. The `descheduler-0.37.0` plan is in
  `conflicts_with` for the same reason.
- **Surge scheduling:** maxSurge 25% rounds up to 1 at `replicas: 2`, and required anti-affinity
  over the 3 control-plane nodes puts the surge pod on the free node (nuc14-03 today). If a node is
  cordoned or NotReady at §2, the roll still proceeds one pod at a time via `maxUnavailable: 1`,
  but with one replica serving for a few seconds. Check `kubectl get nodes` in §2 and prefer all 3
  Ready.
- **Renovate:** do not merge #469/#470 separately. Two merges would mean two reconciles, and #470
  alone has no live effect. §3's single commit is byte-identical to both.
- **Not a security remediation.** `F-7eb4c1dc` (image finding) stays open after this plan. Do not
  close it here, and do not claim it in a report.
- Retire this file in the commit that records execution. If a sweep files a 1.50.0
  chart-version finding before execution, add it to `finding_refs` and close it with
  `runbooks/policy-cli.py finding close <id> --commit <sha>`.
