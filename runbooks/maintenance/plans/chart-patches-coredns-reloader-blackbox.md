---
plan_id: chart-patches-coredns-reloader-blackbox
component: chart-patches
also_covers:                          # coverage.py matches held items by name/also_covers;
  - coredns                           # maintenance-plan.py by BOTH version tokens below.
  - reloader
  - prometheus-blackbox-exporter
pr: null                              # no Renovate PR exists for any of the three (sweep cycle 58d45ed0)
kind: chart
current: "coredns 1.47.0, reloader 2.2.16 (image v1.4.21), prometheus-blackbox-exporter 11.18.0"
target: "coredns 1.47.1, reloader 2.2.17 (image v1.4.22), prometheus-blackbox-exporter 11.19.1"
update_type: minor                    # two chart patches + one chart minor (11.18 -> 11.19)
risk: medium                          # blackbox + reloader alone are low. coredns is low-PROBABILITY
                                      # (rendered diff = labels + checksum only, image pin unchanged)
                                      # but cluster-wide IMPACT, and a DNS failure disables its own
                                      # GitOps rollback path (source-controller cannot resolve
                                      # github.com) — see §5.3. Weighted medium for that reason.
est_duration_min: 60                  # §2 10 + A 10 + B 8 + C 15 + wait for B's 30m events floor
                                      # (runs concurrently with C; ~15 min left after C) + slack 2
needs_reboot: false
exclusive: false
touches:
  namespaces: [kube-system, monitoring]
  resources:
    - helmrelease/monitoring/prometheus-blackbox-exporter   # chart 11.18.0 -> 11.19.1
    - deployment/monitoring/prometheus-blackbox-exporter    # 1 replica, surge-first roll (label change)
    - configmap/monitoring/prometheus-blackbox-exporter     # label only; modules must be unchanged
    - helmrelease/kube-system/reloader                      # chart 2.2.16 -> 2.2.17
    - deployment/kube-system/reloader                       # image v1.4.21 -> v1.4.22, surge-first roll
    - helmrelease/kube-system/coredns                       # chart 1.47.0 -> 1.47.1
    - deployment/kube-system/coredns                        # 2 replicas, maxUnavailable 1 roll (checksum/config)
    - configmap/kube-system/coredns                         # label only; Corefile must be byte-identical
    - configmap/kube-system/coredns-helm-values-<hash>      # comment edit => new generated name; old one
                                                            # is ORPHANED (ks prune: false), harmless
    - kubernetes/apps/monitoring/prometheus-blackbox-exporter/app/helmrelease.yaml
    - kubernetes/apps/kube-system/reloader/app/helmrelease.yaml
    - kubernetes/apps/kube-system/coredns/app/helmrelease.yaml
    - kubernetes/apps/kube-system/coredns/app/helm-values.yaml
  shared:
    - dns/coredns                     # cluster DNS (Service kube-dns 10.96.0.10) — every pod resolves
                                      # through it; the *.<domain> zone forwards to k8s-gateway .101
    - monitoring                      # blackbox IS the DNS/ingress instrument (5 Probe CRs +
                                      # InternalDns*/IngressProbe* alerts); §4 reads Prometheus
    - reloader                        # 24 auto + 19 named reload annotations cluster-wide depend on it
depends_on: []
conflicts_with:
  - flux-oci-chart-sources            # moves HelmRepository sources incl. coredns/stakater/
                                      # prometheus-community and declares dns-internal; same HRs
  - helm-drift-detection              # adds spec.driftDetection to every HelmRelease incl. these three
  - flux-reconciler-impersonation     # exclusive; rewrites how helm-controller applies these releases
  - uptime-kuma-2.5.5-slim-rootless   # its §4 reads Kuma monitors that resolve via CoreDNS and
                                      # Prometheus; a CoreDNS roll mid-verification poisons its gate
  - oc8-install                       # declares shared k8s-gateway DNS; its DNS verification must not
                                      # overlap a CoreDNS roll (blocked today; listed for when it unblocks)
  - traccar-6.16.0                    # reciprocal: that draft (written concurrently, 2026-09-27) already
                                      # lists this plan in its own conflicts_with
  - mariadb-chart-27.3.0              # tenants re-resolve the DB service on reconnect after mariadb-0 rolls;
                                      # a CoreDNS roll in the same night muddies its reconnect gate
  - penpot-chart-1.10.0               # its frontend nginx resolver moves to cluster DNS; its gate resolves
                                      # through CoreDNS
  # PARKED 2026-09-27: app-template-5.2.1 is an uncommitted draft from another session (DEAD-REF on main); re-add to conflicts_with once it lands.
  # - app-template-5.2.1                # rolls ~78 workloads (incl. monitoring) whose readiness/verification
                                      # resolves through CoreDNS; must not overlap item C's roll.
                                      # Concurrent draft — it should list this plan back.
                                      # No kube-prometheus-stack plan is open (91.4.1 executed). If one
                                      # appears it MUST be added here — §4 reads Prometheus.
capability_change: false              # coredns: same image 1.14.7, byte-identical Corefile; blackbox: same
                                      # image v0.28.0, labels only; reloader v1.4.22: new OPTIONAL
                                      # leader-election flags (unused, enableHA false), rejects non-positive
                                      # pause-period (0 pause-period annotations live, measured 2026-09-27)
rollback_class: git-revert
autonomy_override: human-gated        # belt and braces: shared `dns` already derives HUMAN-GATED via
                                      # SHARED_INFRA_FLOOR. Recommended window class: sat-attended (§6).
security_ref: F-0cf695f9              # reloader image finding (detail in DB only); v1.4.22 is the bump
finding_refs:
  - F-3893caaf                        # coredns chart 1.47.0 -> 1.47.1
  - F-74a00f0b                        # reloader chart 2.2.16 -> 2.2.17
  - F-b7b896a4                        # prometheus-blackbox-exporter chart 11.18.0 -> 11.19.1
premises:
  # All read-only single commands. Values measured 2026-09-27.
  - id: blackbox-is-current
    why: >-
      Item A edits `version: 11.18.0`; if the chart or image already moved, §3.A's anchor and
      §4.A's "image unchanged" assertion are wrong. Prints a different string and fails.
    run: kubectl get helmrelease -n monitoring prometheus-blackbox-exporter -o jsonpath='{.spec.chart.spec.version} {.status.lastAttemptedRevision}'
    expect_exact: 11.18.0 11.18.0
  - id: blackbox-image
    why: >-
      11.19.1 keeps appVersion v0.28.0; §4.A asserts the image did NOT change. Baseline must be v0.28.0.
    run: kubectl get deploy -n monitoring prometheus-blackbox-exporter -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: quay.io/prometheus/blackbox-exporter:v0.28.0
  - id: reloader-is-current
    why: >-
      Item B edits `version: 2.2.16` and expects the image to move v1.4.21 -> v1.4.22.
    run: kubectl get deploy -n kube-system reloader -o jsonpath='{.spec.template.spec.containers[0].image} {.spec.replicas}'
    expect_exact: ghcr.io/stakater/reloader:v1.4.21 1
  - id: coredns-is-current-and-pinned
    why: >-
      Item C edits `version: 1.47.0` and relies on the helm-values image.tag pin (1.14.7) staying
      in force, because chart 1.47.1 still ships appVersion 1.14.6. If the pin was dropped or the
      image moved, the "image unchanged" gate in §4.C is wrong. Prints a different string and fails.
    run: kubectl get deploy -n kube-system coredns -o jsonpath='{.spec.template.spec.containers[0].image} {.spec.replicas} {.status.readyReplicas}'
    expect_exact: coredns/coredns:1.14.7 2 2
  - id: coredns-hr-chart
    why: >-
      HelmRelease must be on 1.47.0 and Ready; a failed/in-flight release makes §5 rollback targets wrong.
    run: kubectl get helmrelease -n kube-system coredns -o jsonpath='{.spec.chart.spec.version} {.status.lastAttemptedRevision} {.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: 1.47.0 1.47.0 True
  - id: dns-probes-exist
    why: >-
      §4 reads probe_success from these Probe CRs; if they were renamed/removed the gate reads empty.
    run: kubectl get probe -n monitoring dns-k8s-gateway-primary dns-k8s-gateway-secondary http-ingress-internal http-ingress-external -o name
    expect_matches: "(?s)dns-k8s-gateway-primary.*dns-k8s-gateway-secondary.*http-ingress-internal.*http-ingress-external"
status: draft
window: null
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/auto-update.md
  - docs/sops/k8s-gateway-dns.md
  - docs/sops/monitoring.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-09-27"
---

# Low-risk chart patches: blackbox-exporter, reloader, coredns

## 1. Summary & why held

Three chart bumps with no Renovate PR, bundled into one plan. Each item is its own commit, so each
one can be reverted on its own. Order: **A blackbox, then B reloader, then C coredns.** Blackbox goes
first because §4.C reads it. Reloader goes before coredns so the one item with a real blast radius
runs last, with nothing else in flight.

| Item | Chart | App/image | Rendered diff with OUR values (`helm template` old vs new, diffed 2026-09-27) | Why held |
|---|---|---|---|---|
| A | prometheus-blackbox-exporter 11.18.0 → 11.19.1 | v0.28.0 → v0.28.0 (unchanged) | only `helm.sh/chart` labels (incl. pod template → one surge-first pod roll). Chart source diff: `Chart.yaml` version + default `configReloader.image.tag` v0.93.1→v0.94.1. That sidecar is disabled here (it does not render). | G3 could not read release notes (coverage "unverified"). This is a false positive in substance: nothing functional changes. |
| B | reloader 2.2.16 → 2.2.17 | v1.4.21 → **v1.4.22** (tag verified on ghcr, HTTP 200) | labels + image tag only. Args, RBAC and strategy are unchanged. | G3 could not read release notes. Upstream v1.4.22 notes (github stakater/Reloader release v1.4.22): "reject non-positive pause-period durations", "expose client-go leader election timings as flags and Helm values", "Move leases RBAC to *-metadata-reader role when HA is enabled", Go 1.26.8, ubi9 base bump. Also in the v1.4.21..v1.4.22 range: "prevent panic on invalid regex in reload annotation". None of this reaches our config: `enableHA` is off, and 0 pause-period annotations exist live. The 24 `auto` and 19 named `…/reload` annotations are valid patterns. Security driver: `security_ref: F-0cf695f9` (detail on the DB record only). |
| C | coredns 1.47.0 → 1.47.1 | **1.14.7 stays** (pinned in helm-values; chart appVersion is still 1.14.6) | `helm.sh/chart` labels + pod `checksum/config`. **The Corefile render is identical.** The checksum changes only because the hashed ConfigMap carries the chart label. Chart source diff is autoscaler-only ("Allow separate labels and selector for the cluster-proportional-autoscaler Deployment"). We do not enable the autoscaler. | Deny rule `*coredns*` in `runbooks/auto-update-policy.yaml`: cluster DNS, and the image is pinned ahead of the chart. |

**Pin decision (item C):** `helm show chart oci://ghcr.io/coredns/charts/coredns --version 1.47.1`
gives `appVersion: 1.14.6`. That is still below the pinned `1.14.7`, so the pin STAYS. Only the
helm-values comment's "1.47.0 is the newest" text is refreshed. Dropping the pin would downgrade
CoreDNS to 1.14.6 and bring back the forward `max_connect_attempts` default that the 1.14.7 bump
had to pin.

**Net effect:** three pod rolls. Two are no-op (identical image and config), and one is an image
patch on reloader. The real risk is the CoreDNS pod roll itself (2 replicas, `maxUnavailable: 1`,
`lameduck 5s`) and what happens if DNS breaks (§5.3).

## 2. Pre-checks (all read-only; abort the whole plan on any failure)

```bash
cd /Users/mu/code/cberg-home-nextgen
.venv/bin/python3 runbooks/plan-premises.py chart-patches-coredns-reloader-blackbox   # all PASS
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'     # header only
flux get helmreleases -A   | awk 'NR==1 || $5 != "True"'     # header only
git status --short -- kubernetes/apps/kube-system/coredns kubernetes/apps/kube-system/reloader \
  kubernetes/apps/monitoring/prometheus-blackbox-exporter     # empty (no foreign edits)
```

**2.1 Step 0 has settled.** The window's safe-update batch must be fully reconciled before item B.
Reloader rolls surge-first, so there is no watch gap, but do not stack changes. Check that the
`flux-system` GitRepository revision equals `git rev-parse origin/main`:
```bash
flux get sources git -n flux-system flux-system ; git rev-parse --short origin/main
```

**2.2 DNS baseline (record the output; §4.C compares against it).** Resolution runs from inside the
blackbox pod. Its busybox `nslookup` exits 1 on NXDOMAIN (the negative control below proves the gate
can fail). Pod IPs are not routable from the Mac, so do not use `dig` from the Mac.
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
dnsmatrix
```
Expected (measured 2026-09-27, 2 replicas × 4 names):
`kubernetes.default…` → `rc=0 ans=10.96.0.1`; `sweep.<domain>` → `rc=0 ans=192.168.55.103`
(this goes through the `${SECRET_DOMAIN}` server block → forward to 192.168.55.101); `github.com` →
`rc=0` with a public IP; `does-not-exist-zz9…` → `rc=1 ans=NONE`. **Negative control:** if that
last line reads `rc=0`, the harness cannot detect failure. STOP.
(`for ip in $(…)` word-splits correctly under zsh. Holding the IP list in a scalar does not; that
bug was hit while authoring this plan.)

```bash
kubectl -n kube-system get cm coredns -o jsonpath='{.data.Corefile}' | shasum -a 256 | tee /private/tmp/claude-501/chart-patches-corefile.pre
kubectl -n monitoring get cm prometheus-blackbox-exporter -o jsonpath='{.data.blackbox\.yaml}' \
  | python3 -c "import sys,yaml; print(sorted(yaml.safe_load(sys.stdin)['modules']))"
# expect: ['dns_k8s_gateway_primary', 'dns_k8s_gateway_secondary', 'http_2xx_ingress']
```

**2.3 Prometheus baseline** (the port-forward stays up for §4):
```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
q(){ curl -s --get http://localhost:19090/api/v1/query --data-urlencode "query=$1" \
  | python3 -c "import sys,json; r=json.load(sys.stdin)['data']['result']; print(len(r)); [print(' ',{k:v for k,v in x['metric'].items() if k in ('probe_component','instance','rcode','to','version','pod','event_type')},x['value'][1]) for x in r]"; }
q 'probe_success'                                              # 5 series, all 1
q 'sum by (rcode)(rate(coredns_dns_responses_total[10m]))'     # note SERVFAIL (absent/0 on 2026-09-27)
q 'ALERTS{alertstate="firing",alertname=~"InternalDns.*|IngressProbe.*|Blackbox.*"}'   # 0
```

**2.4 Reloader log baseline** (§4.B requires the same count after the change):
```bash
kubectl -n kube-system logs deploy/reloader | grep -ciE 'level=(warning|error|fatal)|panic'
# 1 on 2026-09-27 — the startup `KUBERNETES_NAMESPACE is unset…` warning; record the number
```

## 3. Steps: one commit per item, verify each (§4) before the next

Shared-worktree rule: use `git commit --only <paths>`, then check with `git log -1 --format=%s` that
the subject is yours, and `git show --stat HEAD` that every file is yours, BEFORE `git push`.
Each sed was dry-tested on a scratch copy with macOS BSD sed. The resulting diff line is quoted below.
Each anchor matches exactly once (`grep -c` = 1, measured).

### 3.A prometheus-blackbox-exporter 11.18.0 → 11.19.1
```bash
F=kubernetes/apps/monitoring/prometheus-blackbox-exporter/app/helmrelease.yaml
test "$(grep -c '^      version: 11\.18\.0$' $F)" = 1 || { echo ABORT; return 1 2>/dev/null || exit 1; }
sed -i '' 's/^      version: 11\.18\.0$/      version: 11.19.1/' $F
git diff -- $F     # exactly: -      version: 11.18.0  /  +      version: 11.19.1
git commit --only $F -m "feat(monitoring): prometheus-blackbox-exporter chart 11.18.0 -> 11.19.1 (F-b7b896a4)"
git log -1 --format=%s && git show --stat HEAD && git push
```
Flux picks it up via the push webhook. No manual reconcile. Wait for
`kubectl get hr -n monitoring prometheus-blackbox-exporter` Ready, message `…11.19.1`
(≤10 min; if nothing happens after 10 min, check the webhook before anything else). Then run §4.A.

### 3.B reloader 2.2.16 → 2.2.17
```bash
F=kubernetes/apps/kube-system/reloader/app/helmrelease.yaml
test "$(grep -c '^      version: 2\.2\.16$' $F)" = 1 || { echo ABORT; return 1 2>/dev/null || exit 1; }
sed -i '' 's/^      version: 2\.2\.16$/      version: 2.2.17/' $F
git diff -- $F     # exactly: -      version: 2.2.16  /  +      version: 2.2.17
git commit --only $F -m "feat(kube-system): reloader chart 2.2.16 -> 2.2.17 (image v1.4.22) (F-74a00f0b)"
git log -1 --format=%s && git show --stat HEAD && git push
```
Wait for the HR to be Ready at 2.2.17, then run §4.B.

### 3.C coredns 1.47.0 → 1.47.1 (image pin KEPT)
```bash
F=kubernetes/apps/kube-system/coredns/app/helmrelease.yaml
V=kubernetes/apps/kube-system/coredns/app/helm-values.yaml
test "$(grep -c '^      version: 1\.47\.0$' $F)" = 1 || { echo ABORT; return 1 2>/dev/null || exit 1; }
test "$(grep -c '^# Chart 1\.47\.0 is the newest published chart and still ships appVersion 1\.14\.6,$' $V)" = 1 || { echo ABORT; return 1 2>/dev/null || exit 1; }
sed -i '' 's/^      version: 1\.47\.0$/      version: 1.47.1/' $F
sed -i '' 's/^# Chart 1\.47\.0 is the newest published chart and still ships appVersion 1\.14\.6,$/# Chart 1.47.1 (newest published, re-checked 2026-09-27) still ships appVersion 1.14.6,/' $V
git diff -- $F $V
#   -      version: 1.47.0
#   +      version: 1.47.1
#   -# Chart 1.47.0 is the newest published chart and still ships appVersion 1.14.6,
#   +# Chart 1.47.1 (newest published, re-checked 2026-09-27) still ships appVersion 1.14.6,
grep -n 'tag: "1.14.7"' $V     # MUST still print the pin line
git commit --only $F $V -m "feat(kube-system): coredns chart 1.47.0 -> 1.47.1, keep image pin 1.14.7 (F-3893caaf)"
git log -1 --format=%s && git show --stat HEAD && git push
```
The comment edit changes the generated `coredns-helm-values-<hash>` ConfigMap name. Because
`ks prune: false`, the old one stays as an orphan. That is harmless, and it makes a revert re-point
to an object that already exists. Watch the roll:
`kubectl -n kube-system get pods -l k8s-app=kube-dns -o wide -w` (Ctrl-C once 2/2 new pods are Ready,
on 2 distinct nodes). Then run §4.C.

**Do NOT touch** the `*coredns*` deny rule in `runbooks/auto-update-policy.yaml`. Its removal
condition ("a chart ships appVersion >= the pinned tag AND the image.tag override is dropped") is
still unmet.

## 4. Verification

A failed gate means that item's §5 rollback. Earlier items stay applied, because each gate is
independent.

### 4.A blackbox
- HR Ready at 11.19.1. **Image unchanged**:
  `kubectl get deploy -n monitoring prometheus-blackbox-exporter -o jsonpath='{.spec.template.spec.containers[0].image}'`
  → `quay.io/prometheus/blackbox-exporter:v0.28.0`. If a different tag prints, the chart moved the
  image contrary to the render. FAIL.
- CONTENTS ASSERTION: the live module set is still exactly our three and the chart-default `http_2xx` is still nulled. Measured by the §2.2 `python3 … sorted(modules)` command, compared to the baseline `['dns_k8s_gateway_primary', 'dns_k8s_gateway_secondary', 'http_2xx_ingress']`. If the Helm map-merge regressed, `http_2xx` appears in the list. FAIL.
- Negative control through the live exporter (proves the module is really gone, not just absent from
  a list we parsed):
  ```bash
  kubectl -n monitoring port-forward svc/prometheus-blackbox-exporter 19115:9115 >/dev/null 2>&1 & BF=$!; sleep 2
  curl -s 'http://localhost:19115/probe?module=dns_k8s_gateway_primary&target=192.168.55.101' | grep -E '^probe_success '   # probe_success 1
  curl -s -o /dev/null -w '%{http_code}\n' 'http://localhost:19115/probe?module=http_2xx&target=192.168.55.101'           # 400 (unknown module)
  kill $BF
  ```
  A `200` on the second curl means the permissive default module is back. FAIL.
- CONTROL: metric probe_success — all 5 series = 1, over a window after the new pod's start (wait 2 min; `q 'min_over_time(probe_success[2m])'` → 5 series, all 1). 0 series means the scrape broke. FAIL.
- CONTROL: metric blackbox_exporter_config_last_reload_successful — `= 1` on the new pod (the `pod` label must be the new pod name).
- CONTROL: metric blackbox_exporter_build_info — `version="0.28.0"`, exactly 1 series from the new pod.
- CONTROL: alertname BlackboxProbesAbsent — not firing.
- CONTROL: alertname BlackboxExporterPodNotReady — not firing.

### 4.B reloader
- `kubectl get deploy -n kube-system reloader -o jsonpath='{.spec.template.spec.containers[0].image} {.status.readyReplicas}'`
  → `ghcr.io/stakater/reloader:v1.4.22 1`. Restarts 0 after 5 min.
- Startup log lines (case-insensitive; upstream mixes case):
  `kubectl -n kube-system logs deploy/reloader | grep -ciE 'starting controller to watch resource type: (configmaps|secrets)'` → `2`.
  `kubectl -n kube-system logs deploy/reloader | grep -ciE 'level=(warning|error|fatal)|panic'` → must EQUAL the
  §2.4 baseline (1 on 2026-09-27: the startup `KUBERNETES_NAMESPACE is unset, will detect changes in all
  namespaces` warning). That baseline line proves the grep matches this log format. Any extra
  warning, error or panic raises the count. FAIL. A count of 0 means the startup warning disappeared,
  so the log format or config changed: investigate before continuing.
- CONTENTS ASSERTION: the new pod's informers actually receive update events. Measured by
  `q 'sum(increase(reloader_events_received_total{event_type="update",pod="<NEW pod>"}[30m]))'`
  (configmaps + secrets summed), read 30 min after the new pod started. The floor is `> 0`. Measured
  over 24h on 2026-09-27: the 10m form read 0 in 38 of 144 windows, which would false-FAIL, so it is
  not used. The summed 30m form read 0 in 0 of 144 windows, with a minimum of 7.1. A watch/RBAC
  regression leaves it at 0 while the pod is Ready. FAIL. This read does not block item C: C proceeds
  once B's image, Ready and log gates pass, and this floor is read at the end of the window.
- CONTROL: metric reloader_events_received_total — floor above, new pod only (the old pod's stale series also exist until they age out; filter by `pod`).
- CONTROL: metric reloader_reload_executed_total — soak, not a window gate: `{success="true"}` on the new pod `> 0` within 48 h (the live rate was 34 in 7 d), and `{success="false"}` stays 0. The window agent records this as a follow-up check for the next sweep.

### 4.C coredns
- Pods: 2/2 Ready on 2 distinct nodes, both with image `coredns/coredns:1.14.7` (the **pin survived**;
  `1.14.6` = the pin was lost = FAIL):
  `kubectl -n kube-system get pods -l k8s-app=kube-dns -o 'custom-columns=N:.metadata.name,NODE:.spec.nodeName,IMG:.spec.containers[0].image,READY:.status.containerStatuses[0].ready,RS:.status.containerStatuses[0].restartCount'`
- CONTENTS ASSERTION: the served Corefile is byte-identical to the pre-change one. Measured by `kubectl -n kube-system get cm coredns -o jsonpath='{.data.Corefile}' | shasum -a 256 | diff - /private/tmp/claude-501/chart-patches-corefile.pre` (silent = pass). The render diff says only labels change; any Corefile change means the chart altered DNS config. FAIL and roll back.
- CONTENTS ASSERTION: every replica resolves all three name classes correctly. Measured by re-running `dnsmatrix` from §2.2 against the NEW pod IPs, compared to the §2.2 baseline. Required: 2 IPs × (cluster name → 10.96.0.1, `sweep.<domain>` → 192.168.55.103, github.com → rc=0 public IP, negative control → rc=1 NONE). Any `rc≠0` on the first three, or `rc=0` on the fourth, is a FAIL.
- CONTROL: metric coredns_build_info — exactly 2 series, both `version="1.14.7"`, with the NEW pod names.
- CONTROL: metric coredns_dns_responses_total — `sum by (rcode)(rate(coredns_dns_responses_total[5m]))` 5 min after roll: NOERROR > 0 (a floor: traffic is served), SERVFAIL not above the §2.3 baseline.
- CONTROL: metric coredns_proxy_request_duration_seconds_count — `sum by (to,rcode)(rate(coredns_proxy_request_duration_seconds_count[5m]))` shows `to="192.168.55.101:53"` NOERROR > 0, so the `${SECRET_DOMAIN}` block still forwards to k8s-gateway.
- CONTROL: metric probe_success — the three `probe_class="http"` probes (ingress-internal, ingress-external, vaultwarden) resolve their hostnames through CoreDNS inside the blackbox pod, so they are the Prometheus-side end-to-end check: `min_over_time(probe_success{probe_class="http"}[5m])` = 1. **Note:** the two `dns_*` probes target k8s-gateway (192.168.55.101) DIRECTLY and do **not** exercise CoreDNS. They stay green even if CoreDNS is dead. They are not a CoreDNS gate; `dnsmatrix` is.
- CONTROL: alertname InternalDnsResolutionFailing — not firing.
- CONTROL: alertname InternalDnsResolverDown — not firing.
- CONTROL: alertname IngressProbeFailing — not firing.
- Rollback-path health: wait >= 2 min after the roll completes, then `flux get sources git -n flux-system flux-system`
  must show READY `True` (the real gate; a post-roll fetch is not observable without a new commit)
  (needs github.com resolution via CoreDNS). This proves §5 is still usable.

Finally: `kill $PF`.

## 5. Rollback (per item; each is one revert commit)

Find the item's commit with `git log --oneline -3 -- <file>`, then
`git revert --no-edit <sha> && git log -1 --format=%s && git push`.

- **5.A blackbox:** revert → HR back at 11.18.0 (`helm history prometheus-blackbox-exporter -n monitoring` shows a new revision with chart 11.18.0). Re-run §4.A. Expected module set and image unchanged.
- **5.B reloader:** revert → image `ghcr.io/stakater/reloader:v1.4.21`, HR 2.2.16. Re-run §4.B with v1.4.21.
  Any workload whose ConfigMap/Secret changed while reloader was broken missed its reload. List what
  changed (`git log --since=<item B push> --name-only -- kubernetes/`) and restart only those
  workloads through their own GitOps path.
- **5.C coredns:** revert (both files) → HR 1.47.0. The old generated values ConfigMap still exists
  (prune: false). Pods roll again. Re-run §4.C: Corefile hash = `/private/tmp/claude-501/chart-patches-corefile.pre`, dnsmatrix = baseline.
- **5.3 Break-glass, only if CoreDNS is serving failures:** the GitOps revert needs source-controller
  to resolve github.com THROUGH CoreDNS, so a DNS-breaking upgrade can block its own revert. Helm's own
  `upgrade.remediation.strategy: rollback` covers a failed upgrade, but not an upgrade that is Ready
  and serving wrong answers. If §4.C fails AND `flux get sources git` shows no fetch after the revert
  push, an operator (not unattended) runs:
  `flux suspend helmrelease coredns -n kube-system && helm rollback coredns 10 -n kube-system --wait`
  Revision 10 is `coredns-1.47.0`, deployed 2026-08-19; confirm with `helm history coredns -n kube-system`
  first, because it will be 10 only if nothing else upgraded it. Then push the revert, and
  `flux resume helmrelease coredns -n kube-system` once the source shows the revert revision. This is
  the one direct cluster mutation in the plan. It is why this plan is attended.

## 6. Interference notes

- **Not nightly-unattended, by design and by derivation.** `touches.shared` carries `dns/coredns`.
  `dns` is in `SHARED_INFRA_FLOOR`, so `maintenance-plan.py` derives HUMAN-GATED, and
  `autonomy_override: human-gated` states it explicitly. The reason is not the diff, which is
  trivial. It is §5.3: a CoreDNS failure at 03:30 disables the GitOps revert and needs a human with
  `helm`. The `*coredns*` deny rule also says coredns "should never bump unattended regardless of
  the pin". **Recommended window: `sat-attended`** (60 min fits the 70 min budget). The plan reviewer
  (2026-09-27) named the next free slot as `sat-attended:2026-10-17`. That is recorded here as prose only:
  `window:` stays null for the scheduler.
  If the operator wants A+B in `nightly`: split item C into its own plan. A and B alone derive
  AUTO-NIGHT (low risk, git-revert, no DNS/storage/gateway shared surface).
- **Serialize A → B → C, gate between each.** C last, with nothing else in flight. The window's other
  plans must not verify through DNS or Prometheus during C's roll (~2 min). That is why
  `uptime-kuma-2.5.5-slim-rootless` and `oc8-install` are in `conflicts_with`.
- **Blackbox is the window's own instrument.** During A's surge roll there is at most a ~30 s gap in
  `probe_success`. `BlackboxProbesAbsent` needs 10 m and `InternalDns*` need 2 m, so neither should
  fire. A firing one is a real signal.
- `flux-oci-chart-sources`, `helm-drift-detection` and `flux-reconciler-impersonation` rewrite
  these same three HelmReleases or their sources. Never in the same window. Those plans should list
  this one in their own `conflicts_with` (reciprocity is not validated).
- Retire this file (delete it) in the commit that records execution, and close the three findings with
  `runbooks/policy-cli.py finding close <id> --commit <sha>` (F-3893caaf, F-74a00f0b, F-b7b896a4).
  Re-measure F-0cf695f9 on the next security sweep rather than closing it by hand.
