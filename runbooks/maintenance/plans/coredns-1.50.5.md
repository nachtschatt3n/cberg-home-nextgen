---
plan_id: coredns-1.50.5
component: coredns
pr: 481                               # Renovate #481 = HelmRelease 1.50.2 -> 1.50.7 (the LIVE change). #483 bumps the SAME
                                      # chart in kubernetes/bootstrap/apps/helmfile.yaml (bootstrap-only, no live object reads
                                      # it). Both OPEN + MERGEABLE + CI green 2026-11-15, both held by the `*coredns*` deny rule.
                                      # Both retargeted 1.50.5 -> 1.50.7 since the first draft (2026-11-13): this plan is
                                      # REFRESHED to the new target (plan_id kept at coredns-1.50.5 on purpose: seven other plans
                                      # name it in conflicts_with and cannot be edited from here; rename in a follow-up that fixes
                                      # all of them). Section 3 makes ONE commit whose HR + helmfile post-images have the same git
                                      # blob ids as the PR post-images (a0e0715ef / ab7767d92, measured 2026-11-15 from
                                      # `gh api .../pulls/{481,483}/files` AND on scratch copies), so Renovate closes both.
kind: chart
current: "chart 1.50.2 (appVersion 1.14.7), no image pin"
target: "1.50.7"                      # chart 1.50.7, appVersion 1.14.7 (UNCHANGED) - image does NOT move. 1.50.8 / 1.51.0 do not
                                      # exist (helm show chart: not found, 2026-11-15)
update_type: patch                    # chart patch x5 (1.50.3 .. 1.50.7); image coredns/coredns:1.14.7 unchanged
risk: low                             # MEASURED 2026-11-15: `helm template` 1.50.2 vs 1.50.7 with our exact values differs in 6x
                                      # helm.sh/chart labels + pod checksum/config + THREE pod-spec lines: livenessProbe.
                                      # initialDelaySeconds 60 -> 0, readinessProbe.initialDelaySeconds 30 -> 0 (1.50.5) and a NEW
                                      # container field terminationMessagePolicy: FallbackToLogsOnError (1.50.6; live is the API
                                      # default `File`). 1.50.7 is chart metadata only (sources URL). Corefile, image, Service,
                                      # ports identical. Effect = one rolling restart whose new pods join the Service when /ready
                                      # says so (~1-5 s) instead of 30 s later. Low because the change is two probe delays and a
                                      # diagnostics-only termination policy, fully reverted by git revert, and guarded by upstream
                                      # code (section 1). The impact class (cluster DNS; a DNS failure disables its own git
                                      # revert) is carried by the SD-11 floor + autonomy_override, not by this field.
est_duration_min: 40                  # section 2 (incl. 2.0 control-plane gate) 15 + section 3 5 + Flux pickup/roll ~3 + section 4 12 (incl. 5 min rate window) + slack 5
needs_reboot: false
exclusive: false
touches:
  namespaces: [kube-system]
  resources:
    - helmrelease/kube-system/coredns                   # chart 1.50.2 -> 1.50.7 (helm revision 14 -> 15)
    - deployment/kube-system/coredns                    # 2 replicas, RollingUpdate maxUnavailable 1 / maxSurge 25%; no PDB,
                                                        # no priorityClassName, no minReadySeconds (re-read live 2026-11-13).
                                                        # Pod template changes: 2 probe delays + terminationMessagePolicy + checksum -> both pods roll
    - configmap/kube-system/coredns                     # label only; Corefile must be byte-identical
    - service/kube-system/kube-dns                      # label only (clusterIP LOOKED UP in 2.1, never typed)
    - serviceaccount/kube-system/coredns                # label only
    - clusterrole/coredns                               # label only
    - clusterrolebinding/coredns                        # label only
    - kubernetes/apps/kube-system/coredns/app/helmrelease.yaml
    - kubernetes/bootstrap/apps/helmfile.yaml           # bootstrap-only pin (Renovate #483); no live object reads it
    - docs/infrastructure.md                            # CoreDNS bootstrap row (line 109) 1.50.2 -> 1.50.7
    - docs/applications.md                              # coredns row (line 186) "Chart 1.50.2" -> "Chart 1.50.7"
                                                        # helm-values.yaml is NOT edited -> no new coredns-helm-values-<hash>
  shared:
    - dns                             # SD-11 floor token: cluster DNS for every pod in the cluster
    - coredns                         # SD-11 floor token; the domain block forwards to k8s-gateway 192.168.55.101,
                                      # `.` forwards to Talos hostDNS 169.254.116.108
    - flux                            # source-controller resolves github.com THROUGH CoreDNS = this plan's revert path
    - monitoring                      # section 4 reads Prometheus + execs into blackbox (read-only; the instrument is shared)
depends_on: []
conflicts_with:
  # Every non-terminal plan whose execution or verification touches cluster DNS, the HR apply/revert path (Flux
  # controllers, sources, drift), kube-system pod placement / node state, or the Prometheus/blackbox instrument section 4
  # reads. Plan set re-read 2026-11-15: `maintenance-plan.py --open` + a frontmatter scan of the plan files.
  - talos-linux-1.14.5                # sun-attended:2026-11-22, exclusive node roll (3 reboots); reschedules both CoreDNS pods, lists `coredns`
  - longhorn-1.13.0                   # sun-attended:2026-11-15, exclusive; lists `flux` (its reconcile storm shares the revert path)
  - flux-oci-chart-sources            # sun-attended:2026-12-13; moves HelmRepository sources and re-applies kube-system HRs incl. this one
  - helm-drift-detection              # sat-attended:2026-11-28; adds driftDetection to every HR incl. this one
  - kube-prometheus-stack-93.3.0      # exclusive; rolls Prometheus = the instrument sections 2.3/4 read (replaces the retired
                                      # -92.22.0 entry: that plan file no longer exists). It already names coredns-1.50.5.
  - postgres-digest-refresh-2026-11   # sun-attended:2026-12-20; DB restarts, consumers re-resolve; its text names the retired coredns-1.50.2
  - redis-fleet-8.10.3                # sun-attended:2026-11-29; consumers re-resolve on reconnect
  - etcd-timeouts-5000-500            # control-plane service restarts; CoreDNS's kubernetes plugin watches the apiserver
  - flux-reconciler-impersonation     # exclusive; changes how helm-controller applies this HR
  - talos-power-tuning-ab             # exclusive; machineconfig change on the 3 control-plane nodes CoreDNS is pinned to
  - descheduler-0.37.0                # kube-system CronJob that can evict CoreDNS (no priorityClassName) mid-roll
  - envoy-gateway-1.10.0              # exclusive; lists `dns`, its gates resolve through CoreDNS and read probe_success
  - envoy-proxy-config-distroless-v1.40.0   # its verification resolves through CoreDNS and reads probe_success
  - envoy-proxy-config-distroless-v1.40.2   # same surface
  - nocodb-2026.10.1                  # reaches postgresql by DNS name (its conflicts_with names coredns-1.50.5: reciprocal)
  # NOT listed, checked 2026-11-15: no cilium, blackbox-exporter or flux-fleet plan is open (if one appears it MUST be
  # added). vaultwarden-1.37.5 (listed by the predecessor) no longer exists. Every other open plan only shares
  # `monitoring` as a READER: serialize by slot, do not stack in the same hour.
capability_change: false              # same image coredns/coredns:1.14.7, byte-identical Corefile, same Service spec. The two
                                      # probe delays change WHEN a starting pod is probed, and terminationMessagePolicy only what
                                      # kubectl shows after a crash; none changes what CoreDNS can do or serve
rollback_class: git-revert
autonomy_override: human-gated        # `dns`/`coredns`/`flux` are in the SD-11 floor anyway; section 5.3 break-glass needs a human
security_ref: null                    # not security-driven. Image unchanged, so it does NOT answer F-7eb4c1dc.
finding_refs: [F-3893caaf]            # version-row finding for this component (`policy-cli.py finding list --grep coredns`,
                                      # 2026-11-15; current title "coredns: chart 1.50.2 -> 1.50.6 (patch)" - it lags the PRs'
                                      # 1.50.7 by one sweep, the sweep retitles it; the ref is by id). F-7eb4c1dc (image
                                      # security) is NOT answered by this plan.
premises:
  # All read-only single commands. Values measured live 2026-11-15.
  - id: coredns-live-image-and-replicas
    why: >-
      Section 4 asserts the image does NOT change (chart 1.50.7 appVersion = 1.14.7 = live). If the live image or replica
      count differs, the imageID and 8-line dnsmatrix gates are wrong. Prints a different string and fails.
    run: kubectl get deploy -n kube-system coredns -o jsonpath='{.spec.template.spec.containers[0].image} {.spec.replicas} {.status.readyReplicas}'
    expect_exact: "coredns/coredns:1.14.7 2 2"
  - id: coredns-hr-chart
    why: >-
      HelmRelease must be Ready on 1.50.2. A failed/in-flight release, or #481 merged behind the plan's back (1.50.7 already
      live), makes section 3's anchor and the section 5 rollback target wrong.
    run: kubectl get helmrelease -n kube-system coredns -o jsonpath='{.spec.chart.spec.version} {.status.lastAttemptedRevision} {.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "1.50.2 1.50.2 True"
  - id: coredns-deployed-chart-label
    why: >-
      The Deployment's helm.sh/chart label is what section 4 compares after the roll; it must read coredns-1.50.2 now or the
      "new release applied" gate cannot tell old from new.
    run: kubectl get deploy -n kube-system coredns -o jsonpath='{.metadata.labels.helm\.sh/chart}'
    expect_exact: "coredns-1.50.2"
  - id: coredns-live-probe-delays
    why: >-
      The one functional change of 1.50.5 (carried by 1.50.7) is liveness/readiness initialDelaySeconds 60/30 -> 0/0. Section 4 asserts "0 0"
      and a ready gap under 20 s; that only proves anything if the live values are still 60/30 (a values override or an
      earlier roll would make the gate pass without this plan having changed anything).
    run: kubectl get deploy -n kube-system coredns -o jsonpath='{.spec.template.spec.containers[0].livenessProbe.initialDelaySeconds} {.spec.template.spec.containers[0].readinessProbe.initialDelaySeconds}'
    expect_exact: "60 30"
  - id: kube-dns-service-spec
    why: >-
      Section 4 asserts the Service spec is unchanged; this records the shape it compares against. The clusterIP is NOT
      hardcoded here: 2.2 reads it into svc.pre and section 4 diffs against that file.
    run: kubectl get svc -n kube-system kube-dns -o jsonpath='{.spec.clusterIP} {.spec.ipFamilyPolicy} {.spec.ipFamilies[*]}'
    expect_matches: '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+ SingleStack IPv4$'
  - id: repo-hr-anchor
    why: >-
      Section 3's edit anchors on exactly one `version: 1.50.2` line in the committed HelmRelease. Prints 0 if main moved.
    run: "git show HEAD:kubernetes/apps/kube-system/coredns/app/helmrelease.yaml | grep -c 'version: 1.50.2'"
    expect_exact: "1"
  - id: repo-bootstrap-anchor
    why: >-
      Section 3's edit also anchors on exactly one `version: 1.50.2` line in the bootstrap helmfile (the coredns release is
      the only one at that version, measured 2026-11-13). Prints 0 if #483 was merged or main moved.
    run: "git show HEAD:kubernetes/bootstrap/apps/helmfile.yaml | grep -c 'version: 1.50.2'"
    expect_exact: "1"
  - id: coredns-live-termination-policy
    why: >-
      1.50.6 adds terminationMessagePolicy: FallbackToLogsOnError. Section 4 asserts the live field flips to it; that proves
      the new release applied only if the live value is the API default `File` now (a values override or an earlier roll
      would make the assertion pass without this plan having changed anything). Prints another string and fails.
    run: kubectl get deploy -n kube-system coredns -o jsonpath='{.spec.template.spec.containers[0].terminationMessagePolicy}'
    expect_exact: "File"
  - id: renovate-481-post-image
    why: >-
      DRIFT GUARD. The first draft targeted 1.50.5 and went stale in two days while Renovate moved PRs 481/483 to 1.50.7.
      `gh` and `helm show` of a missing chart are refused/fail in the premise runner, so this reads the git blob id of the
      HelmRelease on Renovate's own branch (the PR #481 post-image). It equals a0e0715ef... only while the PR still bumps
      to exactly 1.50.7; a retarget (1.50.8) changes the blob and prints another id. Needs `git fetch origin` first
      (section 2 does it); a stale ref reads the old blob, which is why section 2 also reads the live PR titles.
    run: git rev-parse origin/renovate/coredns-1.50.x:kubernetes/apps/kube-system/coredns/app/helmrelease.yaml
    expect_exact: "a0e0715efbfcc554ce1c59f62d745bb436ec16cc"
  - id: renovate-483-post-image
    why: >-
      Same drift guard for the bootstrap-helmfile PR #483 whose post-image blob (ab7767d92...) section 3 must reproduce.
      A different id means #483 moved or the helmfile on main changed: re-plan.
    run: git rev-parse origin/renovate/ghcr.io-coredns-charts-coredns-1.50.x:kubernetes/bootstrap/apps/helmfile.yaml
    expect_exact: "ab7767d92e9c0ae60f72bc94901beaf15c9d4c3a"
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
review: ready-for-go@2026-11-15      # plan-reviewer 2nd pass 2026-11-15: ready-for-go, 0 blocking (1st pass needs-fix: target drift to 1.50.7 + SERVFAIL gate control, both fixed + verified live). Section 2.0 etcd gate FAILS today (11 leader changes in 2 h): do not run until quiet.
status: vetted
window: null
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/auto-update.md
  - docs/sops/k8s-gateway-dns.md
  - docs/sops/monitoring.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-11-13"
refreshed: "2026-11-15"             # retargeted 1.50.5 -> 1.50.7 after Renovate moved PRs 481/483; see section 1
---

# coredns chart 1.50.2 -> 1.50.7 (image unchanged at 1.14.7; probe initial delays 60/30 -> 0/0; terminationMessagePolicy -> FallbackToLogsOnError)

## 1. Summary & why held

**REFRESHED 2026-11-15.** The first draft (2026-11-13) targeted 1.50.5. Renovate #481/#483 have since moved to 1.50.7
(titles read "1.50.2 -> 1.50.7"), finding F-3893caaf reads "coredns: chart 1.50.2 -> 1.50.6 (patch)", and chart 1.50.6
adds a pod-spec line the old plan's "exactly nine changed lines" render gate did not allow. Everything below is
re-measured against 1.50.7 (pulled digest `sha256:7688172c...`). The `plan_id`/file name stay `coredns-1.50.5` because seven
other plans reference that id.

**What changes:** the CoreDNS HelmRelease moves from chart 1.50.2 to 1.50.7. The bootstrap helmfile's coredns pin and the
CoreDNS rows in `docs/infrastructure.md` / `docs/applications.md` move the same way, in one commit equal to Renovate
#481 + #483 plus the two doc rows (it supersedes BOTH PRs; Renovate closes them once main carries identical blobs). CoreDNS keeps running **coredns/coredns:1.14.7** (same digest). `helm-values.yaml`
is not touched.

**Why held:** the `*coredns*` deny rule in `runbooks/auto-update-policy.yaml` holds every coredns bump in the PLAN lane
on purpose: a coredns patch number is not a patch release, and a DNS failure disables its own GitOps revert because
source-controller resolves github.com through CoreDNS. The hold is **intentional, not a gate false-positive**. Unlike
the three previous chart patches (1.50.0, 1.50.1, 1.50.2: label-only rolls), this one changes the pod spec (two probe delays, one termination policy), which
is the case the rule exists for.

**Upstream evidence (primary sources, re-read 2026-11-15):**
- `helm pull oci://ghcr.io/coredns/charts/coredns` for 1.50.2 (`sha256:43a04aa7...`), 1.50.5 (`sha256:53d32062...`),
  1.50.6 (`sha256:779cb2c7...`), 1.50.7 (`sha256:7688172c...`): all `appVersion: 1.14.7`. **appVersion does NOT
  change.** 1.50.8 and 1.51.0 do not exist (`helm show chart ... --version`: "not found"). Flux's `HelmRepository/coredns`
  is `oci://ghcr.io/coredns/charts` (live), so these are the artifacts Flux pulls.
- Chart changelog annotations (`artifacthub.io/changes`), verbatim:
  - 1.50.3 `fixed`: "Document values missing from the README and drop the stale top-level dnsConfig row" (README only).
  - 1.50.4 `fixed`: "Do not render service.trafficDistribution on its own when deployment.enabled is false"
    (`templates/service.yaml`: an `{{- end }}` moved below the `trafficDistribution` block; we set neither value).
  - 1.50.5 `changed`: "The readiness probe starts without an initial delay (readinessProbe.initialDelaySeconds 0), so a
    pod receives queries once the ready plugin reports it ready, not 30 s later" and "The liveness probe starts without
    an initial delay (livenessProbe.initialDelaySeconds 0); failureThreshold 5 and periodSeconds 10 still give a starting
    pod 50 s before a restart" (`values.yaml` defaults + 4 unit tests).
  - 1.50.6 `added`: "terminationMessagePolicy, FallbackToLogsOnError by default, so a CoreDNS container that exits with
    an error shows the reason in its status" (`templates/deployment.yaml`: a `{{- with .Values.terminationMessagePolicy }}`
    block; `values.yaml` default `FallbackToLogsOnError`).
  - 1.50.7 `added`: "The chart repository (https://github.com/coredns/helm) in sources, so tools such as Renovate find
    the chart's release notes" - `Chart.yaml` only (`diff -ru` 1.50.6 vs 1.50.7 shows nothing else).
- `diff -ru` of the pulled 1.50.2 and 1.50.7 charts: Chart.yaml, README.md, `templates/deployment.yaml` (the 1.50.6
  `terminationMessagePolicy` block), `templates/service.yaml` (the 1.50.4 `{{- end }}` move), three test files, and
  `values.yaml` (two `initialDelaySeconds` defaults + the new `terminationMessagePolicy`). No other template changed.
- **Rendered diff with OUR values** (`helm template` 1.50.2 vs 1.50.7, `${SECRET_DOMAIN}` substituted, helm 3.22.1,
  2026-11-15): 19 changed `<`/`>` lines = 10 changes. 6x `helm.sh/chart: "coredns-1.50.2"` -> `"coredns-1.50.7"`; the pod
  `checksum/config` (`1626f59f...` -> `83878357...`; the hashed ConfigMap carries the chart label, the Corefile is
  identical); `+ terminationMessagePolicy: FallbackToLogsOnError` (an ADDED line, render line 222, live value is the API
  default `File`); `livenessProbe.initialDelaySeconds: 60` -> `0`; `readinessProbe.initialDelaySeconds: 30` -> `0`.
  Rendered image `coredns/coredns:1.14.7`; `ipFamilies` 0 occurrences, `trafficDistribution` 0 occurrences.
  (The old draft's `checksum 1626f59f -> ff312cda` and "nine changed lines" belong to 1.50.5 and are obsolete.)
- **Why delay 0 is safe, from CoreDNS v1.14.7 source** (not from the chart's claim):
  `plugin/ready/ready.go` answers 503 until `plugins.Ready()` is true and 200 after; `plugin/kubernetes/ready.go` is
  `func (k *Kubernetes) Ready() bool { return k.APIConn.HasSynced() }`. So a pod is added to the kube-dns endpoints only
  after its kubernetes informers synced; the 30 s delay was dead time, not protection. `plugin/health/health.go`
  answers 200 as soon as the listener is up, so liveness at delay 0 passes on the first probe; a pod that never serves
  `/health` is restarted after 5 x 10 s exactly as before. Both plugins are in our `.` server block (`health` with
  `lameduck 5s`, `ready`), read from `helm-values.yaml`.

**Live state (re-read 2026-11-15; unchanged vs 11-13 unless stated):**
- HR `1.50.2 1.50.2 True`; `helm history` revision 14 `deployed` on coredns-1.50.2 (13 = 1.50.1, 12 = 1.50.0).
- 2/2 pods on k8s-nuc14-01 and k8s-nuc14-02; all 3 nodes Ready; no PDB in kube-system; Deployment `RollingUpdate`
  maxUnavailable 1 / maxSurge 25%, no `priorityClassName`, no `minReadySeconds`, `revisionHistoryLimit` 10 (11
  ReplicaSets retained), `progressDeadlineSeconds` 600. Live probes: liveness delay 60, readiness delay 30.
- Both containers started 2026-11-12T13:32:40Z/41Z and went Ready at 13:33:11Z: **ready gap 31 s / 30 s** (the old
  delay, measured). One pod shows restartCount 1 (previous container exit 255 `Unknown` at 13:30:50Z, the other pod was
  recreated in the same minute: a node-level event on 11-12, not a CoreDNS crash loop; not investigated further here).
- imageID `docker.io/coredns/coredns@sha256:7efd3c63...aa286`; Corefile sha256 `cf7ccdad...4063d` (unchanged since
  2026-11-03); kube-dns `10.96.0.10`, SingleStack IPv4, ports `53 53`; container ports `53 53 9153`.
- dnsmatrix from the blackbox pod against both pod IPs: cluster name -> `10.96.0.1` rc=0, `sweep.<domain>` ->
  `192.168.55.103` rc=0, `github.com` -> public IP rc=0, `does-not-exist-zz9...` rc=1 (negative control).
- Prometheus (re-read 2026-11-15): `coredns_build_info` 2 series `version="1.14.7"`; responses NOERROR 17.2/s, NXDOMAIN
  10.6/s, SERVFAIL absent; `sum by (pod,rcode)(increase(...{rcode="NXDOMAIN"}[10m]))` = 2 series, one per pod
  (3047 and 3337), SERVFAIL = 0 series (the demonstration section 2.3 now requires); proxy `to=169.254.116.108:53` and `to=192.168.55.101:53` both NOERROR > 0; 3 http probes = 1; no DNS/ingress
  probe alert firing.
- kubeconfig server is an IP literal (`https://192.168.55.10:6443`), so `helm`/`kubectl` from the Mac work with cluster
  DNS down. GitRepository `flux-system` is an `https://github.com/...` URL, Ready True.
- 2026-11-15: all HelmReleases Ready (`flux get hr -A` header only). **etcd is flapping today**:
  `increase(etcd_server_leader_changes_seen_total[1h])` reads 4.0 / 3.0 / 3.0 on the three members. CoreDNS's
  `kubernetes` plugin watches the apiserver and Flux retries against it, so a roll during a leader-election storm would
  confuse every gate below. Section 2.0 therefore requires a clean control plane before section 3 (it must FAIL today).

**Roll behaviour, and what is different this time:** no PDB. `maxSurge 25%` rounds up to 1 at 2 replicas; required pod
anti-affinity over the three control-plane nodes puts the surge pod on the one node without a CoreDNS pod
(k8s-nuc14-03 today). Then the old pods terminate one at a time; `lameduck 5s` drains in-flight queries. At least one
replica serves at all times. With readiness delay 0 the roll finishes in roughly 20-30 s instead of ~70-90 s, because
each new pod is Ready seconds after start. Expected visible effect: none, or a few retried lookups.

**Out of scope, flagged for the operator (not done here):**
- **The image finding stays open.** `F-7eb4c1dc` (image-level security finding on `coredns/coredns:1.14.7`; detail on
  the DB record) is not answered: chart 1.50.7 still ships 1.14.7.
- **Retire `coredns-1.48.1.md`.** That older plan (chart 1.48.1, `pr: null`) targets a version long since passed and is
  superseded by this one; retire it in the same commit that records this plan's execution (not touched here).
- **Deny rule:** do NOT edit `runbooks/auto-update-policy.yaml` in this window. Its reason text is still accurate.

## 2. Pre-checks (all read-only; abort on any failure)

```bash
cd /Users/mu/code/cberg-home-nextgen
git fetch -q origin 'refs/heads/renovate/*:refs/remotes/origin/renovate/*'     # refresh the refs premises renovate-48x-post-image read
.venv/bin/python3 runbooks/plan-premises.py coredns-1.50.5 --require-premises   # all PASS, no REFUSED line
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'                    # header only
flux get helmreleases -A   | awk 'NR==1 || $5 != "True"'                    # header only
git status --short -- kubernetes/apps/kube-system/coredns kubernetes/bootstrap/apps/helmfile.yaml docs/infrastructure.md docs/applications.md   # empty
flux get sources git -n flux-system flux-system ; git rev-parse --short origin/main   # same revision (Step 0 settled)
gh pr view 481 --json state,title -q '.state+" "+.title' ; gh pr view 483 --json state,title -q '.state+" "+.title'
#   OPEN, and BOTH titles must end "1.50.2 → 1.50.7 )" (an arrow glyph between the versions). This is the check that
#   caught the 1.50.5 -> 1.50.7 drift: MERGED, or ANY other target -> STOP and REFRESH (re-run the section 1 chart diff
#   -ru + helm template diff for the new target; see README "target MOVES"), do not just change the number
helm history coredns -n kube-system --max 3                                 # DEPLOYED revision = 14 (coredns-1.50.2); note it for 5.3
helm show chart oci://ghcr.io/coredns/charts/coredns --version 1.50.7 | grep -E '^(version|appVersion)'   # 1.50.7 / 1.14.7
helm show chart oci://ghcr.io/coredns/charts/coredns --version 1.50.8 2>&1 | head -1   # expect "not found" (a newer patch = DRIFTED: refresh the diff, do not proceed)
kubectl get nodes                                                           # 3 Ready (section 6 surge note)
date -u +%H:%M                                                              # NOT within 03:50-04:10 UTC (descheduler `0 4 * * *`, no timeZone = UTC)
mkdir -p /private/tmp/coredns-1.50.5
```

**2.0 Clean control plane (required before section 3; read-only).** etcd is flapping on 2026-11-15, and a roll during
leader churn makes every later gate ambiguous (CoreDNS's `kubernetes` plugin and Flux both depend on the apiserver). The
helpers file of 2.1 and the Prometheus port-forward of 2.3 are needed, so run this block AFTER 2.3 (the numbering is by
topic, not order) and abort the plan (do not "wait and see") if it fails:
```bash
. /private/tmp/coredns-1.50.5/fns.sh
q 'max(increase(etcd_server_leader_changes_seen_total[2h]))'     # must print 1 series with value 0: no leader change in 2 h
q 'min(etcd_server_has_leader)'                                  # 1
flux get hr -A | awk 'NR==1 || $5 != "True"'                    # header only
flux get ks -A | awk 'NR==1 || $5 != "True"'                    # header only
kubectl get hr -A -o jsonpath='{range .items[*]}{.metadata.namespace}/{.metadata.name} {.status.conditions[?(@.type=="Ready")].message}{"\n"}{end}' | grep -i -e retries -e 'not ready' -e 'in progress'   # EMPTY: nothing is retrying
```
Gate can fail: measured 2026-11-15 the first query prints 4 (max across members) and this section therefore STOPS today.
It passes only after the control plane has been quiet for 2 h. A leader-change count of 0 is also what an unscraped
metric would give as an EMPTY result, so require exactly one series: 0 series = blind = STOP.

**2.1 DNS baseline and helpers (record; section 4 compares against it).** Lookups run from inside the blackbox pod,
because pod IPs are not routable from the Mac. busybox `nslookup` exits 1 on NXDOMAIN, so the fourth name is the
negative control (measured rc=1 on 2026-11-13). Expected in-cluster answers are LOOKED UP from live Services, never
typed. The whole file was run under zsh against the live cluster on 2026-11-13.
```bash
cat > /private/tmp/coredns-1.50.5/fns.sh <<'FNS'
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
readygap() {
  kubectl -n kube-system get pods -l k8s-app=kube-dns -o jsonpath='{range .items[*]}{.metadata.name} {.status.containerStatuses[0].state.running.startedAt} {.status.conditions[?(@.type=="Ready")].lastTransitionTime} {.status.containerStatuses[0].restartCount}{"\n"}{end}' \
  | python3 -I -c "
import sys, datetime as d
p=lambda s: d.datetime.strptime(s,'%Y-%m-%dT%H:%M:%SZ')
rows=[l.split() for l in sys.stdin if l.strip()]
if len(rows)!=2: sys.exit('READYGAP_FAIL expected 2 pods, got %d' % len(rows))
bad=0
for n,st,rd,rs in rows:
    g=(p(rd)-p(st)).total_seconds()
    v='FAST' if 0<=g<=20 and rs=='0' else 'SLOW_OR_RESTARTED'
    bad+= v!='FAST'
    print(n,'gap_s=%d'%g,'restarts='+rs,v)
print('READYGAP_PASS' if not bad else 'READYGAP_FAIL')
"
}
q(){ curl -s --get http://localhost:19090/api/v1/query --data-urlencode "query=$1" \
  | python3 -c "import sys,json; r=json.load(sys.stdin)['data']['result']; print(len(r)); [print(' ',{k:v for k,v in x['metric'].items() if k in ('pod','version','rcode','to','instance','alertname')},x['value'][1]) for x in r]"; }
FNS
. /private/tmp/coredns-1.50.5/fns.sh && echo "FNS_OK ksvc=$KSVC kdns=$KDNS"
dnsmatrix | tee /private/tmp/coredns-1.50.5/dnsmatrix.pre
kubectl -n monitoring exec deploy/prometheus-blackbox-exporter -- nslookup -type=A kubernetes.default.svc.cluster.local "$KDNS" | awk '/^Name:/{f=1} f&&/^Address/{print "via-kube-dns-vip", $2}' | head -1 | tee /private/tmp/coredns-1.50.5/vip.pre
readygap | tee /private/tmp/coredns-1.50.5/readygap.pre
```
- `FNS_OK` must print two non-empty addresses; `vip.pre` must name `$KSVC`.
- `dnsmatrix`: 8 lines (2 pod IPs x 4 names): cluster name `rc=0 ans=$KSVC` (10.96.0.1 on 2026-11-13); `sweep`
  `rc=0 ans=192.168.55.103`; `github.com` `rc=0` with a public IP; `does-not-exist-zz9...` `rc=1 ans=NONE`.
  **Negative control:** if the last name ever reads `rc=0`, the harness cannot detect a failure. STOP.
- `readygap` **must print `READYGAP_FAIL` now** (measured 2026-11-13, pods unchanged on 11-15: `gap_s=31 restarts=1` and `gap_s=30 restarts=0`,
  both `SLOW_OR_RESTARTED`). This is the negative control of the section 4 probe gate: the pre-change pods carry the
  30 s delay. If it prints `READYGAP_PASS` before the change, the gate cannot distinguish old from new. STOP.
- Do not hold the IP list in a zsh scalar; `for ip in $(...)` word-splits correctly.

**2.2 Corefile, image-digest, Service, probe and pod baseline:**
```bash
kubectl -n kube-system get cm coredns -o jsonpath='{.data.Corefile}' > /private/tmp/coredns-1.50.5/corefile.txt
test -s /private/tmp/coredns-1.50.5/corefile.txt || { echo 'ABORT: empty Corefile read'; false; }
shasum -a 256 < /private/tmp/coredns-1.50.5/corefile.txt | tee /private/tmp/coredns-1.50.5/corefile.pre
# 2026-11-13: cf7ccdad3e5799e63d642753797489197dbf50db294083622bb9578fde54063d
kubectl -n kube-system get pods -l k8s-app=kube-dns -o jsonpath='{range .items[*]}{.status.containerStatuses[0].imageID}{"\n"}{end}' | sort -u | tee /private/tmp/coredns-1.50.5/imageid.pre
# 1 line: docker.io/coredns/coredns@sha256:7efd3c635b03efd68c4e8398fc45f0d993d0e9ab016f72c1cefb0fd6d01aa286 (2026-11-13)
kubectl -n kube-system get svc kube-dns -o jsonpath='{.spec.clusterIP} {.spec.ipFamilyPolicy} {.spec.ipFamilies[*]} {.spec.ports[*].port}' | tee /private/tmp/coredns-1.50.5/svc.pre
# 10.96.0.10 SingleStack IPv4 53 53
kubectl -n kube-system get deploy coredns -o jsonpath='{.spec.template.spec.containers[0].ports[*].containerPort}' | tee /private/tmp/coredns-1.50.5/ports.pre
# 53 53 9153
kubectl -n kube-system get pods -l k8s-app=kube-dns -o name | sort | tee /private/tmp/coredns-1.50.5/pods.pre
test "$(wc -l < /private/tmp/coredns-1.50.5/pods.pre | tr -d ' ')" = 2 || echo 'ABORT: expected 2 pods in pods.pre'
```

**2.3 Prometheus baseline.** The port-forward stays up for section 4.
```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; echo $PF > /private/tmp/coredns-1.50.5/pf.pid; sleep 3
. /private/tmp/coredns-1.50.5/fns.sh
q 'coredns_build_info'                                                  # 2 series, version="1.14.7"
q 'sum by (rcode)(rate(coredns_dns_responses_total[10m]))'              # NOERROR > 0 and NXDOMAIN > 0; SERVFAIL absent
q 'sum by (to,rcode)(rate(coredns_proxy_request_duration_seconds_count[10m]))'   # to=192.168.55.101:53 and to=169.254.116.108:53 both NOERROR > 0
q 'min_over_time(probe_success{probe_class="http"}[5m])'               # 3 series, all 1
q 'ALERTS{alertstate="firing",alertname=~"InternalDns.*|IngressProbe.*|Blackbox.*"}'   # 0
# DEMONSTRATION that the section 4 SERVFAIL gate can see a failure: the IDENTICAL query shape with a different rcode that
# really occurs here. If it cannot return pod-labelled series for NXDOMAIN it cannot for SERVFAIL, and "0 series" is blind.
q 'sum by (pod,rcode)(increase(coredns_dns_responses_total{rcode="NXDOMAIN"}[10m]))'   # MUST be 2 series, one per CURRENT pod, each > 0
q 'sum by (pod,rcode)(increase(coredns_dns_responses_total{rcode="SERVFAIL"}[10m]))'   # 0 series today
```
**SERVFAIL gate demonstration (blocking).** The NXDOMAIN line must print exactly 2 series, `pod` labels equal to the two
names in `pods.pre`, both values > 0 (measured 2026-11-15: ~3047 and ~3337 per 10 min; cluster-wide NXDOMAIN rate ~10.6/s). Fewer than 2 series, a missing `pod` label, or a
zero value: STOP, because the section 4 SERVFAIL query is then provably blind (an absent series would read as "no
failures"). The SERVFAIL line printing 0 series is only meaningful after this passes. The window agent must not skip it
on the grounds that SERVFAIL "is absent anyway".

Record the SERVFAIL value (absent = 0). If `coredns_build_info` returns 0 series the scrape is broken and the metric
gates below are blind: fix or drop to the dnsmatrix gates, do not proceed on empty reads.

**2.4 Fallback source of the revert (read before pushing).** The only DNS-independent restore is `helm rollback` from
the Mac plus the retained ReplicaSet. Both checks must pass:
```bash
kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}'   # https://<ip>:6443 ; a hostname FAILS this pre-check
git ls-remote origin HEAD | head -1                                        # prints a sha (the Mac resolves github.com by itself)
```

## 3. Steps (one commit, four files)

**Precondition: section 2.0 passed** (no etcd leader change in 2 h, Flux not retrying). Do not start section 3 otherwise.

The edit was dry-tested with macOS `python3 -I` on scratch copies of all four files from `HEAD` on 2026-11-15 (re-run for 1.50.7):
- It checks ALL four anchors before writing ANY file.
- The HelmRelease and helmfile post-image blobs are `a0e0715efbfc...` and `ab7767d92e9c...`, identical to the blob ids
  GitHub reports for Renovate #481 and #483 (`gh api repos/{owner}/{repo}/pulls/{481,483}/files`, 2026-11-15) and to
  `git rev-parse` of the two Renovate branches (premises `renovate-481-post-image` / `renovate-483-post-image`).
- A second run aborts with `ABORT: helmrelease anchor not found exactly once`.

```bash
cd /Users/mu/code/cberg-home-nextgen
F=kubernetes/apps/kube-system/coredns/app/helmrelease.yaml
B=kubernetes/bootstrap/apps/helmfile.yaml
DOC=docs/infrastructure.md
APP=docs/applications.md
python3 -I - "$F" "$B" "$DOC" "$APP" <<'EOF'
import re, sys
hr, boot, doc, app = sys.argv[1:5]
s = open(hr).read()
pat = re.compile(r'^      version: 1\.50\.2$', re.M)
if len(pat.findall(s)) != 1: sys.exit("ABORT: helmrelease anchor not found exactly once")
b = open(boot).read()
bpat = re.compile(r'^(    chart: oci://ghcr\.io/coredns/charts/coredns\n    version: )1\.50\.2$', re.M)
if len(bpat.findall(b)) != 1: sys.exit("ABORT: bootstrap helmfile coredns anchor not found exactly once")
t = open(doc).read()
dpat = re.compile(r'^(\| 2 \| CoreDNS \| `oci://ghcr\.io/coredns/charts/coredns` \| )1\.50\.2( \|)', re.M)
if len(dpat.findall(t)) != 1: sys.exit("ABORT: docs/infrastructure.md CoreDNS row anchor not found exactly once")
a = open(app).read()
apat = re.compile(r'^(\| coredns \| Cluster-internal DNS resolution\. Chart )1\.50\.2( / image )', re.M)
if len(apat.findall(a)) != 1: sys.exit("ABORT: docs/applications.md coredns row anchor not found exactly once")
open(hr, 'w').write(pat.sub('      version: 1.50.7', s))
open(boot, 'w').write(bpat.sub(r'\g<1>1.50.7', b))
open(doc, 'w').write(dpat.sub(r'\g<1>1.50.7\g<2>', t))
open(app, 'w').write(apat.sub(r'\g<1>1.50.7\g<2>', a))
print("OK")
EOF
git diff --stat -- "$F" "$B" "$DOC" "$APP"     # 4 files, 4 insertions, 4 deletions
git diff -- "$F" "$B"
git hash-object "$F" "$B"       # a0e0715efbfcc554ce1c59f62d745bb436ec16cc and ab7767d92e9c0ae60f72bc94901beaf15c9d4c3a (MUST equal; else STOP)
```
Expected diff (verbatim from the dry run):
```
helmrelease.yaml (line 12):        -      version: 1.50.2   /   +      version: 1.50.7
helmfile.yaml (line 27, coredns):  -    version: 1.50.2     /   +    version: 1.50.7
docs/infrastructure.md (line 109): the CoreDNS row's version cell 1.50.2 -> 1.50.7
docs/applications.md (line 186):   "Chart 1.50.2 / image" -> "Chart 1.50.7 / image"
```
If the script prints `ABORT...`, nothing was written. Stop and investigate (a merged #481/#483 or a doc edit by another
session is the likely cause). If ONLY a doc anchor fails, the two chart hunks are the change: remove that doc's
anchor check, write and argument from a copy of the script and drop the file from the commit; do not hand-edit the
chart files.

Before committing, confirm the render with the NEW chart and our values (helm 3 via mise). STOP and
`git checkout -- "$F" "$B" "$DOC" "$APP"` on any deviation:
```bash
V=kubernetes/apps/kube-system/coredns/app/helm-values.yaml
sed 's/\${SECRET_DOMAIN}/example.test/' "$V" > /private/tmp/coredns-1.50.5/vals.yaml
for v in 1.50.2 1.50.7; do helm template coredns oci://ghcr.io/coredns/charts/coredns --version $v -n kube-system -f /private/tmp/coredns-1.50.5/vals.yaml > /private/tmp/coredns-1.50.5/render-$v.yaml; done
R=/private/tmp/coredns-1.50.5
grep -E '^[[:space:]]*image:' $R/render-1.50.7.yaml | tr -d ' "' | sed 's/^image://'   # coredns/coredns:1.14.7
grep -c -i 'ipFamilies' $R/render-1.50.7.yaml                                          # 0
diff $R/render-1.50.2.yaml $R/render-1.50.7.yaml | grep -E '^[<>]' | grep -vcE 'helm.sh/chart: "coredns-1.50.[27]"|checksum/config|initialDelaySeconds: (60|30|0)$|terminationMessagePolicy: FallbackToLogsOnError$'   # 0
diff $R/render-1.50.2.yaml $R/render-1.50.7.yaml | grep -cE '^[<>].*initialDelaySeconds'   # 4 (60->0 and 30->0)
diff $R/render-1.50.2.yaml $R/render-1.50.7.yaml | grep -cE '^>.*terminationMessagePolicy: FallbackToLogsOnError$'   # 1 (an ADDED line, no '<' counterpart)
diff $R/render-1.50.2.yaml $R/render-1.50.7.yaml | grep -cE '^<.*terminationMessagePolicy'   # 0
diff $R/render-1.50.2.yaml $R/render-1.50.7.yaml | grep -cE '^[<>]'   # 19 (6 label pairs = 12, checksum pair = 2, 4 delay lines, 1 added policy)
```
The whitelist `grep -vcE` MUST print `0`; anything else means the chart changed something section 1 did not account for.
The whitelist can fail: it counts every changed line outside the four allowed shapes (the old draft's whitelist lacked
`terminationMessagePolicy` and its labels were `1.50.[25]`; run against the 1.50.7 render it prints `7`, which is exactly the drift this refresh caught). The other
counts pin each allowed shape to its measured multiplicity, so a line that matches the whitelist but appears twice, or a
policy value other than `FallbackToLogsOnError`, still stops you. Measured 2026-11-15: `0`, `4`, `1`, `0`, `19`.

Commit. Shared worktree: use `--only`, then verify subject and file list BEFORE pushing. Append the executing
session's own attribution trailer as the last `-m`:
```bash
git commit --only "$F" "$B" "$DOC" "$APP" -m "fix(kube-system): coredns chart 1.50.2 -> 1.50.7 (appVersion 1.14.7 unchanged; probe initialDelaySeconds 60/30 -> 0/0, terminationMessagePolicy FallbackToLogsOnError); supersedes Renovate #481 #483"
git log -1 --format=%s          # must be the subject above, else amend before push
git show --stat HEAD            # exactly the four files
git push
```
Flux picks the change up through the push webhook. No manual reconcile. Do NOT merge or close #481/#483 by hand. Watch
the roll with a bounded poll (no `-w`):
```bash
for i in $(seq 1 40); do kubectl -n kube-system get pods -l k8s-app=kube-dns --no-headers; echo ---; sleep 15; done | tail -12
```
Proceed once exactly 2 NEW pods are Running 1/1 on 2 distinct nodes and none is Terminating (<= 10 min). If the HR does
not move within 10 min, check the webhook and `flux get sources git` before anything else.

## 4. Verification (any FAIL -> section 5)

Wait until exactly 2 kube-dns pods are Running and none is Terminating (lameduck 5 s); that also fixes the dnsmatrix
line count. Each block runs in a fresh shell: start with `. /private/tmp/coredns-1.50.5/fns.sh`, and re-open the 2.3
port-forward if `pf.pid` is dead.

- **Release:**
  ```bash
  kubectl get hr -n kube-system coredns -o jsonpath='{.spec.chart.spec.version} {.status.lastAttemptedRevision} {.status.conditions[?(@.type=="Ready")].status}'
  ```
  Expected `1.50.7 1.50.7 True`. `helm history coredns -n kube-system --max 2` shows revision 15 `deployed` on
  `coredns-1.50.7`, APP VERSION 1.14.7. A later revision reading `rolled back` (or 14 `deployed` again) means helm's own
  remediation fired. FAIL.
- **Pods rolled and run the new render:**
  ```bash
  kubectl -n kube-system get pods -l k8s-app=kube-dns -o name | sort | comm -12 - /private/tmp/coredns-1.50.5/pods.pre   # EMPTY = both replaced
  kubectl -n kube-system get pods -l k8s-app=kube-dns -o 'custom-columns=N:.metadata.name,NODE:.spec.nodeName,IMG:.spec.containers[0].image,READY:.status.containerStatuses[0].ready,RS:.status.containerStatuses[0].restartCount'
  kubectl get deploy -n kube-system coredns -o jsonpath='{.metadata.labels.helm\.sh/chart}'
  ```
  `comm` output must be empty (a surviving old name means the roll did not happen and every later gate would measure
  the old pods). 2 pods on 2 distinct nodes, `coredns/coredns:1.14.7`, READY true, RS 0. The Deployment label must
  print `coredns-1.50.7`; `coredns-1.50.2` means the new release did not apply. FAIL.
- CONTENTS ASSERTION: the pod-spec changes this chart ships are live and behave as upstream says.
  ```bash
  kubectl get deploy -n kube-system coredns -o jsonpath='{.spec.template.spec.containers[0].livenessProbe.initialDelaySeconds} {.spec.template.spec.containers[0].readinessProbe.initialDelaySeconds}'
  kubectl get deploy -n kube-system coredns -o jsonpath='{.spec.template.spec.containers[0].terminationMessagePolicy}'
  kubectl get pods -n kube-system -l k8s-app=kube-dns -o jsonpath='{range .items[*]}{.spec.containers[0].terminationMessagePolicy}{"\n"}{end}'
  readygap
  ```
  The `terminationMessagePolicy` lines must print `FallbackToLogsOnError` (Deployment, then one line per pod = 2 lines).
  `File` is the pre-change state (premise `coredns-live-termination-policy` read `File` before), so it means the new
  release did not apply to the template or the pods did not roll. FAIL. This is a diagnostics-only field: it cannot
  change DNS answers, so a failure here is a plan/render mismatch, not a DNS outage.
  First line must print `0 0`; kubectl may omit a zero-valued field, so an output of a single space (both empty) is
  also the new state, while `60 30` is the old one (premise `coredns-live-probe-delays` proves it read `60 30`
  before). `readygap` must print `READYGAP_PASS`: both pods `FAST` (container start to Ready within 20 s, restartCount
  0). `READYGAP_FAIL` with `gap_s` near 30 means the old delay is still in effect (the baseline in `readygap.pre`
  printed exactly that); a non-zero restart count means the liveness probe at delay 0 killed a starting pod, which is
  the one new failure mode of this change. FAIL either way. **`readygap` (restart count 0 on BOTH new pods, gap <= 20 s)
  is the PRIMARY guard against the "Ready/started before it could answer" failure**: it reads kubelet state, which does
  not depend on any scraped metric, and it demonstrably fails on the old pods (2.1 baseline prints `READYGAP_FAIL`). The
  SERVFAIL metric below is a secondary, corroborating guard.
- CONTENTS ASSERTION: the running image is byte-identical. First `test -s /private/tmp/coredns-1.50.5/imageid.pre`
  (empty baseline = FAIL, never a silent pass). Re-run the 2.2 imageID command and `diff` it against `imageid.pre`
  (silent = pass). A different digest under the same tag is a different image. FAIL.
- CONTENTS ASSERTION: the served Corefile is byte-identical:
  `kubectl -n kube-system get cm coredns -o jsonpath='{.data.Corefile}' | shasum -a 256 | diff - /private/tmp/coredns-1.50.5/corefile.pre`
  (silent = pass). Any difference means the chart altered DNS config (for example a lost `max_connect_attempts 6`). FAIL.
- CONTENTS ASSERTION: the kube-dns Service and container ports are unchanged (`templates/service.yaml` was edited in
  1.50.4): re-run the 2.2 Service and containerPort jsonpaths and `diff` against `svc.pre` / `ports.pre` (silent =
  pass), and the live clusterIP must equal `$KDNS`. A changed port list or clusterIP breaks every pod's
  `/etc/resolv.conf` target. FAIL otherwise.
- CONTENTS ASSERTION: every NEW replica answers all three name classes and still fails the negative control.
  `dnsmatrix | tee /private/tmp/coredns-1.50.5/dnsmatrix.post`: exactly 8 lines; per IP cluster name `rc=0 ans=$KSVC`,
  `sweep` `rc=0 ans=192.168.55.103`, `github.com` `rc=0` with an IP, negative control `rc=1 ans=NONE`; re-run the
  `vip.pre` command and its output must equal `vip.pre`. FAIL on any `rc!=0` for the first three names, `rc=0` on the
  fourth, or fewer than 8 lines. Pod IPs differ from the baseline, so compare the `rc=`/`ans=` columns, not whole lines.
- CONTROL: metric coredns_build_info - exactly 2 series, both `version="1.14.7"`, with the NEW pod names. 0 series means
  the scrape broke and nothing else here can be trusted. FAIL.
- CONTROL: metric coredns_dns_responses_total - `sum by (rcode)(rate(coredns_dns_responses_total[5m]))` 5 min after the
  roll: NOERROR > 0 (proves traffic is served); SERVFAIL not above the 2.3 baseline (absent on 2026-11-15). SECONDARY
  guard, in two steps, in this order (the order is the point):
  1. **Visibility proof (same query shape, rcode that really occurs):**
     `sum by (pod,rcode)(increase(coredns_dns_responses_total{rcode="NXDOMAIN"}[5m]))` must return exactly 2 series whose
     `pod` labels are the two NEW pod names (compare with `pods.pre`: no overlap) and both values > 0. Old names,
     fewer than 2 series, or 0 = the new pods are not being scraped or took no traffic, so step 2 would read "0 series"
     for the wrong reason. Wait and retry for up to 5 min; still failing = FAIL. (Demonstrated live in 2.3 on the old
     pods; counters of a new pod start at 0, so the first seconds of traffic are under-counted by `increase`, which is
     why this is a secondary guard and `readygap` is the primary one.)
  2. `sum by (pod,rcode)(increase(coredns_dns_responses_total{rcode="SERVFAIL"}[5m]))`: 0 series, or 0 for both new pods.
     Any SERVFAIL on a new pod = the "Ready before it could answer" failure. FAIL.
- CONTROL: metric coredns_proxy_request_duration_seconds_count - `sum by (to,rcode)(rate(...[5m]))`: both
  `to="192.168.55.101:53"` and `to="169.254.116.108:53"` NOERROR > 0 (both forward blocks reach their upstreams). Scope
  to the new pods (`pod=~` the two new names) so the old pods' series do not mask a dead new one.
- CONTROL: metric probe_success - `min_over_time(probe_success{probe_class="http"}[5m])` = 1 for all 3 http probes.
  These resolve hostnames through CoreDNS inside the blackbox pod (end to end). The `dns_*` probes target k8s-gateway
  .101 directly and stay green with CoreDNS dead, so they are NOT a CoreDNS gate.
- CONTROL: alertname IngressProbeFailing - not firing. CONTROL: alertname InternalDnsResolutionFailing - not firing
  (covers k8s-gateway, not CoreDNS; listed so a coincident k8s-gateway failure is not misread as this plan's fault).
- **Rollback-path health (a gate that can fail).** Wait >= 2 min after the roll. A bare `flux get sources git` shows a
  fetch made BEFORE the roll and cannot fail. Force a fetch that must resolve github.com through the new pods and read
  back that THIS request was handled:
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
  `lastHandledReconcileAt` is set even when the fetch FAILS, so `HANDLED` only proves an attempt. PASS = `HANDLED` AND
  Ready `True` AND artifact revision equal to the freshly fetched `origin/main` (compare, do not remember: other
  sessions push). FAIL = `NOT_HANDLED_IN_2MIN`, or HANDLED with `False` (print the Ready message; a DNS failure lands
  here), or a stale revision. This is the plan's one cluster write: the Flux-documented request annotation (what
  `flux reconcile source git` does), attended, changing no workload.

Finally: `kill $(cat /private/tmp/coredns-1.50.5/pf.pid)`.

## 5. Rollback

**5.1 GitOps revert (default; needs source-controller to resolve github.com, so it works only while DNS works):**
```bash
cd /Users/mu/code/cberg-home-nextgen
SHA=$(git log -1 --format=%h -- kubernetes/apps/kube-system/coredns/app/helmrelease.yaml)
git show --stat "$SHA"          # confirm it is the coredns 1.50.7 commit
git revert --no-edit "$SHA" && git log -1 --format=%s && git show --stat HEAD && git push
```
The HR and helmfile return to 1.50.2 (the doc rows with them). No values change, so no ConfigMap is orphaned. Pods
roll again, this time with the 60/30 delays back (each new pod Ready ~30 s after start, roll ~70-90 s). Renovate
re-opens its 1.50.7 PRs later; expected. Nothing forward-only happens (no CRD, PVC, migration; same image; same
Corefile), so a revert is the complete restore.

**5.2 Confirm the cluster is back.** HR `1.50.2 1.50.2 True`; Deployment label `coredns-1.50.2`; probe delays `60 30`; `terminationMessagePolicy` back to `File`;
imageID = `imageid.pre`, Corefile hash = `corefile.pre`, Service = `svc.pre`, ports = `ports.pre`; `dnsmatrix` matches
the baseline `rc=`/`ans=` columns; rollback-path gate PASS. (`readygap` prints `READYGAP_FAIL` with gaps near 30 again:
that is the restored state, not a failure.)

**5.3 Break-glass that does NOT use cluster DNS** (CoreDNS serving failures AND the 5.1 revert cannot land: no fetch of
the revert revision by source-controller within 5 min of the push). Operator-present only, never unattended. Every
command runs from the Mac against the apiserver IP (checked in 2.4); none needs a name resolved by CoreDNS, and
`git push` uses the Mac's own resolver:
```bash
helm history coredns -n kube-system --max 5     # 14 = last coredns-1.50.2 revision unless something else ran; use what helm shows
flux suspend helmrelease coredns -n kube-system # stops helm-controller re-applying 1.50.7 over the rollback
helm rollback coredns 14 -n kube-system --wait --timeout 5m
```
`helm rollback` re-applies revision 14's stored manifest (it needs only the apiserver, not the OCI registry or
github.com). Faster still, the previous ReplicaSet is retained (`revisionHistoryLimit 10`):
`kubectl -n kube-system rollout undo deploy/coredns` returns to the previous pod template, then still do the
`helm rollback` so Helm's record matches. Confirm with the section 4 dnsmatrix and the `lastHandledReconcileAt` gate.
Then push the 5.1 revert; once `flux get sources git` shows the revert revision,
`flux resume helmrelease coredns -n kube-system`. Helm's `upgrade.remediation.strategy: rollback` (retries 3) only
covers an upgrade that FAILS to become Ready, not a Ready upgrade that answers wrongly, which is why this path exists.
If the Mac cannot reach the apiserver either, the problem is not this plan: stop and use
`docs/sops/k8s-gateway-dns.md` and the Talos break-glass.

## 6. Interference notes

- **Execution class: HUMAN-GATED, expected and correct, NOT AUTO-NIGHT.** `touches.shared` carries `dns`, `coredns` and
  `flux`, all in the in-code SD-11 floor, and `autonomy_override: human-gated` states it. `risk: low` does not change
  that: the gate is the self-revert hazard (5.3 needs a human with `helm` if DNS breaks at 03:30), not the diff. Do not
  make it eligible by editing fields. 35 min fits a `sat-attended` slot (70 usable min); an on-demand NOW run with an
  operator GO (as 1.50.0, 1.50.1 and 1.50.2 ran) is equally fine.
- **Blast radius:** every pod in the cluster resolves through these two replicas (Service names, the internal domain
  via k8s-gateway, external names via Talos hostDNS), including Flux source-controller (github.com, OCI registries),
  Authentik outposts, the Envoy gateways' upstream lookups, external-dns and the blackbox probes. LAN clients are NOT
  affected: they use AdGuard and k8s-gateway directly.
- **Run it alone, or last in its window.** No other plan may verify through DNS or Prometheus during the roll, hence
  every DNS-, Flux-, node- and instrument-touching open plan is in `conflicts_with`. In particular never in the same
  slot as `longhorn-1.13.0` (sun-attended:2026-11-15), `talos-linux-1.14.5` (sun-attended:2026-11-22),
  `helm-drift-detection` (sat-attended:2026-11-28), `redis-fleet-8.10.3` (sun-attended:2026-11-29),
  `kube-prometheus-stack-93.3.0` (Prometheus is the instrument of 2.3/4), `flux-oci-chart-sources` (sun-attended:2026-12-13) or
  `postgres-digest-refresh-2026-11` (sun-attended:2026-12-20). Free Saturdays re-derive with `maintenance-plan.py --open` at scheduling time (the 2026-11-13 list is stale).
- **Control plane (etcd flapping 2026-11-15):** section 2.0 is a hard precondition; `etcd-timeouts-5000-500` and `talos-power-tuning-ab` are in `conflicts_with` for this reason as well. Do not run this plan inside a leader-churn episode.
- **Order against `talos-linux-1.14.5`:** independent, either order works. If the node roll runs first, re-run section
  2 afterwards (pod names, ages and the ready-gap baseline all change). If this plan runs first, the node roll's
  CoreDNS pods simply come back faster after each reboot (readiness delay 0).
- **Order against `flux-oci-chart-sources` / `helm-drift-detection`:** both edit this same `helmrelease.yaml`
  (sourceRef / driftDetection). Whichever lands second must re-anchor on the then-current file; this plan's section 3
  anchor is the `version:` line only and its premise `repo-hr-anchor` fails closed if that line moved.
- **Nodes / Cilium:** nothing here reboots a node or touches Cilium. If a node roll or Cilium upgrade lands in the
  same night, CoreDNS pods reschedule and section 2 baselines are invalid: abort and re-run after it settles.
- **Step 0 of the same window:** if Step 0 lands a kube-prometheus-stack, blackbox-exporter, cilium or flux bump,
  let it settle and re-take 2.3 before section 3 (the instrument and the revert path are shared).
- **Descheduler:** `kube-system/descheduler` CronJob is `0 4 * * *` with no `timeZone` (premise
  `descheduler-schedule-utc`) = 04:00 **UTC** (05:00 CET). CoreDNS has no `priorityClassName` and no PDB, so its pods
  are evictable. Do not run section 3 within ~10 min of 04:00 UTC (`date -u`).
- **Surge scheduling:** maxSurge 25% rounds up to 1 at `replicas: 2`; required anti-affinity over the 3 control-plane
  nodes puts the surge pod on the free node. With a node cordoned/NotReady the roll proceeds via `maxUnavailable: 1`
  with one replica serving for a few seconds; require all 3 Ready at section 2.
- **Renovate:** do not merge #481/#483 separately; section 3's single commit is byte-identical to both for the two
  chart files. If Renovate retargets the PRs again (a 1.50.8 appears) before the window, this plan is DRIFTED (it already was once, 1.50.5 -> 1.50.7,
  which is why premises `renovate-481-post-image` / `renovate-483-post-image` pin the PR blobs): refresh it in
  place (re-run the section 1 chart diff and render for the new target), do not just change the number.
- **Findings:** after execution, close `F-3893caaf` with `runbooks/policy-cli.py finding close F-3893caaf --commit <sha>`
  (confirm with `finding show` that it is still the coredns chart version row). Do NOT close `F-7eb4c1dc`; this plan
  does not move the image.
- Retire this file in the commit that records execution.
