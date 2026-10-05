---
plan_id: chart-patches-coredns-reloader-blackbox   # id KEPT on purpose (other plans + home-operation key on it);
                                                   # since 2026-10-05 this is a blackbox-only plan
component: prometheus-blackbox-exporter
also_covers: []                       # coredns CARVED OUT 2026-10-05 -> plan coredns-1.48.2 (chart 1.48.2, pin dropped)
                                      # reloader CARVED OUT 2026-10-03 -> plan reloader-2.2.18
pr: null                              # no Renovate PR for the blackbox chart (gh pr list --search blackbox: none, 2026-10-05)
kind: chart
current: "prometheus-blackbox-exporter 11.18.0"
target: "11.19.1"                     # newest published (prometheus-community index, re-read 2026-10-05:
                                      # 11.19.1 created 2026-09-24, nothing newer)
update_type: minor                    # chart minor 11.18 -> 11.19; app/image v0.28.0 unchanged
risk: low                             # rendered diff with our values = 6 helm.sh/chart labels only (re-diffed
                                      # 2026-10-05). One surge-first pod roll of the probe exporter; no DNS,
                                      # no storage, no gateway. The coredns item that made this `medium` is gone.
est_duration_min: 25                  # §2 5 + §3 5 + Flux pickup/roll ~5 + §4 5 (2 min probe window) + slack 5
needs_reboot: false
exclusive: false
touches:
  namespaces: [monitoring]
  resources:
    - helmrelease/monitoring/prometheus-blackbox-exporter   # chart 11.18.0 -> 11.19.1
    - deployment/monitoring/prometheus-blackbox-exporter    # 1 replica, maxSurge 1 / maxUnavailable 0 (label change rolls it)
    - configmap/monitoring/prometheus-blackbox-exporter     # label only; modules must be unchanged
    - service/monitoring/prometheus-blackbox-exporter       # label only
    - servicemonitor/monitoring/prometheus-blackbox-exporter   # label only (selfMonitor)
    - kubernetes/apps/monitoring/prometheus-blackbox-exporter/app/helmrelease.yaml
  shared:
    - monitoring                      # blackbox IS the ingress/DNS probe instrument (5 Probe CRs ->
                                      # probe_success, IngressProbe*/InternalDns*/Blackbox* alerts). Other
                                      # plans' §4 read it, hence the conflicts below.
                                      # `dns/coredns` REMOVED 2026-10-05 with the coredns carve-out.
depends_on: []
conflicts_with:
  - coredns-1.48.2                    # the carved-out coredns item; its §2.1/§4 dnsmatrix execs INTO this pod
                                      # and its gates read probe_success. Never the same window (or this plan
                                      # strictly first, §4 green, before coredns-1.48.2 §2 starts).
  - reloader-2.2.18                   # former item B; reciprocal (it lists this plan). No shared object any more
                                      # (blackbox carries no reloader annotation); kept until its own file drops it.
  - envoy-proxy-config-distroless-v1.39.2   # its §4 gates on probe_success / IngressProbeFailing = this exporter
  - flux-oci-chart-sources            # moves the prometheus-community HelmRepository source; same HR
  - helm-drift-detection              # adds spec.driftDetection to every HelmRelease incl. this one
  - flux-reconciler-impersonation     # exclusive; rewrites how helm-controller applies this release
  - flux-fleet-0.60.0                 # upgrades helm-/source-controller = this plan's apply AND revert path
  - kube-prometheus-stack-91.9.0      # exclusive; restarts the Prometheus that §4 reads (rule 4)
  - talos-linux-1.14.2                # exclusive node roll; belt and braces
  # REMOVED 2026-10-05 with the coredns carve-out (they were listed only because item C rolled CoreDNS;
  # none reads probe_success): app-template-5.2.1, mariadb-28.1.1, penpot-chart-1.10.0,
  # redis-fleet-8.10.2, oc8-install (superseded). Their reciprocal refs to this plan are now
  # over-constraining and should be re-pointed to coredns-1.48.2 (repo correction, not done here).
capability_change: false              # same image v0.28.0, same modules, labels only
rollback_class: git-revert
# autonomy_override REMOVED 2026-10-05: it existed only for the coredns item (§5.3 break-glass).
# Blackbox alone derives AUTO-NIGHT on mechanics (risk low, git-revert, no reboot, shared: monitoring).
security_ref: null                    # was F-0cf695f9 (reloader image) - moved to reloader-2.2.18 with that carve-out
finding_refs:
  - F-b7b896a4                        # prometheus-blackbox-exporter chart 11.18.0 -> 11.19.1
                                      # (F-3893caaf coredns 1.47.1 RESOLVED 2026-10-01; coredns now owned by coredns-1.48.2)
premises:
  # All read-only single commands. Values measured 2026-10-05.
  - id: blackbox-is-current
    why: >-
      §3 edits `version: 11.18.0`; if the chart already moved, the anchor and §4's "image unchanged"
      assertion are wrong. Prints a different string and fails.
    run: kubectl get helmrelease -n monitoring prometheus-blackbox-exporter -o jsonpath='{.spec.chart.spec.version} {.status.lastAttemptedRevision} {.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: 11.18.0 11.18.0 True
  - id: blackbox-image
    why: >-
      11.19.1 keeps appVersion v0.28.0; §4 asserts the image did NOT change. Baseline must be v0.28.0.
    run: kubectl get deploy -n monitoring prometheus-blackbox-exporter -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: quay.io/prometheus/blackbox-exporter:v0.28.0
  - id: probes-exist
    why: >-
      §4 reads probe_success from these 5 Probe CRs; if they were renamed/removed the gate reads empty.
    run: kubectl get probe -n monitoring dns-k8s-gateway-primary dns-k8s-gateway-secondary http-ingress-internal http-ingress-external http-vaultwarden -o name
    expect_matches: "(?s)dns-k8s-gateway-primary.*dns-k8s-gateway-secondary.*http-ingress-internal.*http-ingress-external.*http-vaultwarden"
review: ready-for-go@2026-10-05   # plan-reviewer 2026-10-05 delta (blackbox-only): ready-for-go, 0 blocking; nonblocking .venv python fix applied by coordinator
status: vetted
# AMENDED 2026-10-03: item B (reloader) carved out to reloader-2.2.18.
# AMENDED 2026-10-05 (upgrade-planner refresh): item C (coredns 1.47.0 -> 1.47.1, pin kept) carved out;
# superseded by coredns-1.48.2. Window `sun-attended:2026-11-01` REMOVED (it was attended only for coredns);
# the coordinator re-schedules. Blackbox target re-verified as newest (11.19.1).
window: null
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/auto-update.md
  - docs/sops/monitoring.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-10-05"
---

# prometheus-blackbox-exporter chart 11.18.0 -> 11.19.1 (former chart-patches bundle; coredns + reloader carved out)

## 1. Summary & why held

**Scope history.** This file started (2026-09-27) as a three-chart bundle: A blackbox, B reloader,
C coredns. B moved to `reloader-2.2.18` on 2026-10-03. C moved on 2026-10-05: chart 1.48.2 was
published with appVersion 1.14.7, so the coredns image pin can finally be dropped, and that is now
plan `coredns-1.48.2` (which supersedes the 1.47.1 bump this file used to carry). What is left is
item A only. The plan_id is kept so the cross-references and the go/no-go key stay valid; the item
letter is dropped below.

**What changes:** the `monitoring/prometheus-blackbox-exporter` HelmRelease moves from chart
11.18.0 to 11.19.1. The exporter image stays `quay.io/prometheus/blackbox-exporter:v0.28.0`.

**Upstream evidence (primary sources, re-read 2026-10-05):**
- prometheus-community chart index: 11.19.1 (appVersion v0.28.0, created 2026-09-24) is the
  newest; 11.18.0 (2026-08-31) is what runs. No newer chart exists, so the target stays 11.19.1.
- Chart source diff (`helm pull` of both from `oci://ghcr.io/prometheus-community/charts`, the
  `type: oci` source Flux uses, `diff -r`): exactly two lines — `Chart.yaml` `version`, and the
  default `configReloader.image.tag` v0.93.1 → v0.94.1. That sidecar is disabled here and does not
  render.
- Rendered diff with OUR values (`helm template` 11.18.0 vs 11.19.1, values extracted from the
  HelmRelease with `${SECRET_DOMAIN}` substituted, helm v3.22.0): **6 `helm.sh/chart` label lines,
  nothing else**. Same kinds in both (ConfigMap, Deployment, Service, ServiceAccount,
  ServiceMonitor). The pod-template label change rolls the one pod, surge-first
  (`maxSurge: 1, maxUnavailable: 0`).

**Why held:** G3 could not read release notes (coverage "unverified"). This is a false positive in
substance: nothing functional changes. Risk `low`.

**Execution class:** with coredns gone, nothing in `touches.shared` hits SHARED_INFRA_FLOOR
(`monitoring` only), `capability_change: false`, `rollback_class: git-revert`, no reboot — it
derives AUTO-NIGHT. `autonomy_override: human-gated` was removed because its only reason was the
coredns break-glass.

## 2. Pre-checks (all read-only; abort on any failure)

```bash
cd /Users/mu/code/cberg-home-nextgen
.venv/bin/python3 runbooks/plan-premises.py chart-patches-coredns-reloader-blackbox   # all PASS
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'     # header only
flux get helmreleases -A   | awk 'NR==1 || $5 != "True"'     # header only
git status --short -- kubernetes/apps/monitoring/prometheus-blackbox-exporter   # empty (no foreign edits)
flux get sources git -n flux-system flux-system ; git rev-parse --short origin/main   # same revision (Step 0 settled)
```

**2.1 Module-set baseline (§4 compares against it):**
```bash
kubectl -n monitoring get cm prometheus-blackbox-exporter -o jsonpath='{.data.blackbox\.yaml}' \
  | .venv/bin/python3 -c "import sys,yaml; print(sorted(yaml.safe_load(sys.stdin)['modules']))"
# expect (2026-10-05): ['dns_k8s_gateway_primary', 'dns_k8s_gateway_secondary', 'http_2xx_ingress']
```

**2.2 Prometheus baseline** (the port-forward stays up for §4):
```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
q(){ curl -s --get http://localhost:19090/api/v1/query --data-urlencode "query=$1" \
  | python3 -c "import sys,json; r=json.load(sys.stdin)['data']['result']; print(len(r)); [print(' ',{k:v for k,v in x['metric'].items() if k in ('probe_component','instance','version','pod')},x['value'][1]) for x in r]"; }
q 'probe_success'                                              # 5 series, all 1
q 'blackbox_exporter_build_info'                               # 1 series, version="0.28.0"; note the pod name
q 'ALERTS{alertstate="firing",alertname=~"InternalDns.*|IngressProbe.*|Blackbox.*"}'   # 0
```

## 3. Steps (one commit)

Shared-worktree rule: `git commit --only <path>`, then check with `git log -1 --format=%s` that the
subject is yours and `git show --stat HEAD` that the file is yours, BEFORE `git push`. The sed was
dry-tested on a scratch copy with macOS BSD sed; the anchor matches exactly once (`grep -c` = 1,
re-measured 2026-10-05).

```bash
cd /Users/mu/code/cberg-home-nextgen
F=kubernetes/apps/monitoring/prometheus-blackbox-exporter/app/helmrelease.yaml
test "$(grep -c '^      version: 11\.18\.0$' $F)" = 1 || { echo ABORT; return 1 2>/dev/null || exit 1; }
sed -i '' 's/^      version: 11\.18\.0$/      version: 11.19.1/' $F
git diff -- $F     # exactly: -      version: 11.18.0  /  +      version: 11.19.1
git commit --only $F -m "feat(monitoring): prometheus-blackbox-exporter chart 11.18.0 -> 11.19.1 (F-b7b896a4)" \
  -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
git log -1 --format=%s && git show --stat HEAD && git push
```
Flux picks it up via the push webhook. No manual reconcile. Wait for
`kubectl get hr -n monitoring prometheus-blackbox-exporter` Ready, message `…11.19.1`
(≤10 min; if nothing happens after 10 min, check the webhook before anything else). Then §4.

**Do NOT touch** coredns here; that is `coredns-1.48.2`.

## 4. Verification (any FAIL → §5)

- HR Ready at 11.19.1:
  `kubectl get hr -n monitoring prometheus-blackbox-exporter -o jsonpath='{.spec.chart.spec.version} {.status.lastAttemptedRevision} {.status.conditions[?(@.type=="Ready")].status}'`
  → `11.19.1 11.19.1 True`.
- **Image unchanged**:
  `kubectl get deploy -n monitoring prometheus-blackbox-exporter -o jsonpath='{.spec.template.spec.containers[0].image}'`
  → `quay.io/prometheus/blackbox-exporter:v0.28.0`. A different tag means the chart moved the image
  contrary to the render. FAIL.
- CONTENTS ASSERTION: the live module set is still exactly our three and the chart-default `http_2xx` is still nulled. Measured by the §2.1 `python3 … sorted(modules)` command, compared to the baseline `['dns_k8s_gateway_primary', 'dns_k8s_gateway_secondary', 'http_2xx_ingress']`. If the Helm map-merge regressed, `http_2xx` appears in the list. FAIL.
- Negative control through the live exporter (proves the module is really gone, not just absent from
  a list we parsed):
  ```bash
  kubectl -n monitoring port-forward svc/prometheus-blackbox-exporter 19115:9115 >/dev/null 2>&1 & BF=$!; sleep 2
  curl -s 'http://localhost:19115/probe?module=dns_k8s_gateway_primary&target=192.168.55.101' | grep -E '^probe_success '   # probe_success 1
  curl -s -o /dev/null -w '%{http_code}\n' 'http://localhost:19115/probe?module=http_2xx&target=192.168.55.101'           # 400 (unknown module)
  kill $BF
  ```
  A `200` on the second curl means the permissive default module is back. FAIL. A `probe_success 0`
  on the first means the DNS module broke. FAIL.
- CONTROL: metric probe_success — all 5 series = 1 over a window after the new pod's start (wait 2 min; `q 'min_over_time(probe_success[2m])'` → 5 series, all 1). 0 series means the scrape broke. FAIL.
- CONTROL: metric blackbox_exporter_config_last_reload_successful — `= 1` on the new pod (the `pod` label must be the new pod name, not the §2.2 one).
- CONTROL: metric blackbox_exporter_build_info — `version="0.28.0"`, exactly 1 series, from the new pod.
- CONTROL: alertname BlackboxProbesAbsent — not firing.
- CONTROL: alertname BlackboxExporterPodNotReady — not firing.

Finally: `kill $PF`.

## 5. Rollback

```bash
cd /Users/mu/code/cberg-home-nextgen
SHA=$(git log -1 --format=%h -- kubernetes/apps/monitoring/prometheus-blackbox-exporter/app/helmrelease.yaml)
git show --stat "$SHA"     # confirm it is the 11.19.1 commit (1 file)
git revert --no-edit "$SHA" && git log -1 --format=%s && git show --stat HEAD && git push
```
Confirm: HR back at `11.18.0 11.18.0 True`; `helm history prometheus-blackbox-exporter -n monitoring --max 2`
shows a new revision on chart 11.18.0; re-run §4 — image v0.28.0, module set = §2.1 baseline,
`probe_success` 5 series all 1. Nothing forward-only happens in this plan (no CRD, no PVC, no
migration), so the revert is complete.

## 6. Interference notes

- **Nightly-eligible.** Derives AUTO-NIGHT (see §1); with a `ready-for-go` review and `risk: low` it
  meets SD-10. The previous `sun-attended:2026-11-01` slot was chosen only for coredns and is removed.
- **This pod is the window's instrument.** During the surge roll there is at most a ~30 s gap in
  `probe_success`. `BlackboxProbesAbsent` needs 10 m and `InternalDns*` need 2 m, so neither should
  fire; a firing one is a real signal. No other plan in the same window should be inside its own
  §4 probe/alert gates during this roll — hence `envoy-proxy-config-distroless-v1.39.2` and
  `coredns-1.48.2` in `conflicts_with`.
- **coredns-1.48.2:** its DNS harness execs `nslookup` inside this Deployment. If the operator puts
  both in one window anyway, run this plan first and let §4 go green before coredns §2 starts.
- `flux-oci-chart-sources`, `helm-drift-detection`, `flux-reconciler-impersonation` and
  `flux-fleet-0.60.0` rewrite this HelmRelease, its source, or the controller that applies/reverts it.
  Never in the same window.
- **Repo corrections (not done here):** `app-template-5.2.1`, `mariadb-28.1.1`, `penpot-chart-1.10.0`,
  `redis-fleet-8.10.2`, `nextcloud-fleet-35.0.1`, `edot-collector-0.162.0`, `external-dns-1.23.0` and
  `unpoller-5.4.0` list this plan in `conflicts_with` because it used to roll CoreDNS. That reason now
  belongs to `coredns-1.48.2`; they should re-point (and may drop this plan).
- Retire this file (delete it) in the commit that records execution, and close
  `runbooks/policy-cli.py finding close F-b7b896a4 --commit <sha>`.
