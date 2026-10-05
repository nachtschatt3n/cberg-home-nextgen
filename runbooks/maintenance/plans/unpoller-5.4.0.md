---
plan_id: unpoller-5.4.0
component: unpoller
pr: null                              # no Renovate PR. Reaches the PLAN lane through coverage.py's
                                      # no-PR direct-bump path: the `*unpoller*` deny rule carries
                                      # `max: patch` (narrowed 2026-09-22, F-84472f89), so this
                                      # image MINOR is blocked mechanically (§1.5).
kind: image
current: "v5.2.8"                     # live on deployment/unpoller, measured 2026-09-30: pod
                                      # unpoller-656d9dd8b8-6k66h, imageID sha256:ca82e584… (= the
                                      # v5.2.8 index digest), 0 restarts, started 2026-09-27T08:22:58Z.
target: "v5.5.0"                      # RETARGETED in place 2026-10-05 from v5.4.0 (plan_id/filename kept,
                                      # README rule). Released 2026-10-01T21:10:18Z, prerelease=false,
                                      # draft=false, newest release of any line (measured 2026-10-05; no
                                      # v5.5.1/v5.6.0). ghcr manifest HEAD 200, index sha256:0f45de09…
                                      # (== `latest`), amd64 child sha256:237f13ff…
update_type: minor
risk: low                             # 17 commits / 27 files over v5.2.8…v5.5.0 (§1.2). Every
                                      # exporter change is ADDITIVE and gated on hardware or a config
                                      # flag we do not have (§1.3); the two behaviour changes that DO
                                      # reach us are a controller-login body re-encoding that is
                                      # byte-equivalent in meaning for our credential (§1.4a) and a
                                      # sysinfo decode FIX that turns 16 all-zero series into real
                                      # values (§1.4b). v5.4.0->v5.5.0 is ONE additive exporter (UMBB /
                                      # U5G Max cellular, no such device here, §1.3) + unifi lib 6.3.0
                                      # (UMBB parse only). No metric rename, no config-key change, no
                                      # Dockerfile/base change, image User/Entrypoint unchanged.
                                      # Stateless exporter, git-revert is a true rollback.
est_duration_min: 20                  # commit+push 2, reconcile+rollout 3, >=5 min settle (60s
                                      # scrape, 2m cache, 5m lookback that retires rollout twins),
                                      # verification ~8, InfluxDB write interval 2
needs_reboot: false
touches:
  namespaces: [monitoring]
  resources:
    - helmrelease/unpoller
    - deployment/unpoller
    - "ghcr.io/unpoller/unpoller"
  shared: []                          # DELIBERATE. unpoller is a LEAF exporter: nothing in-cluster
                                      # reads from it for its own function, it restarts nothing
                                      # shared, and its InfluxDB schema does not change in this hop
                                      # (§1.3). The one real coupling is that §4 READS Prometheus and
                                      # InfluxDB; that is expressed in conflicts_with (the only field
                                      # the scheduler honours) -- incl. kube-prometheus-stack-91.9.0
                                      # (draft 2026-10-05). The off-cluster surface (the UniFi
                                      # controller API login) is named in §6.
depends_on: []
conflicts_with:                       # re-checked 2026-10-05 against maintenance-plan.py --open and
                                      # every sibling plan's frontmatter. window-scheduler.py honours
                                      # this field symmetrically, so these entries suffice unilaterally.
  - flux-oci-chart-sources            # its stage 8 (§3.5) is exactly unpoller's chart source: it
                                      # would move HelmRepository/unpoller to OCI and force a chart
                                      # change under this plan's feet (§1.1 chart leg).
  - helm-drift-detection              # adds spec.driftDetection to EVERY HelmRelease incl.
                                      # helmrelease/unpoller — same object, same night = an
                                      # unattributable Helm upgrade.
  - flux-fleet-0.60.0                 # restarts the Flux controllers that must reconcile this
                                      # commit; a stalled/replaying helm-controller reads as "bump
                                      # did not land" (§4.1) and muddles the revert path.
  - coredns-1.48.2                    # rolls CoreDNS; §4.6 writes/reads InfluxDB by service DNS
                                      # name (influxdb-influxdb2.databases.svc), so a DNS blip would
                                      # be misread as an unpoller write-path regression. Replaces
                                      # coredns-1.48.1 (superseded) and chart-patches-coredns-reloader-
                                      # blackbox (now blackbox-only since 2026-10-05; this plan reads no
                                      # blackbox probe, so that entry is dropped). Reciprocal present.
  - kube-prometheus-stack-91.9.0      # restarts Prometheus, the instrument §2.5/§4.3-§4.5/§4.7 read
                                      # (authoring rule 4). Reciprocal present (8921c1bd).
  - flux-distribution-2.9.6           # upgrades the Flux controllers that reconcile this commit (same
                                      # reason as flux-fleet-0.60.0). Reciprocal present in its list.
exclusive: false
security_ref: null                    # version-currency driver only. The two security findings on
                                      # this component (F-cafe8865/AR-114, F-2991c787/AR-115) are
                                      # already-accepted register entries, cited as premises in §1.4a,
                                      # not drivers.
capability_change: false              # FACT, not a hedge: no new route, permission, API, exposure or
                                      # config key; the rendered manifest delta is ONE image tag. The
                                      # two upstream "feat" commits add exporters that emit NOTHING
                                      # here (Protect air-quality needs save_protect, unset; U-LTE
                                      # needs an LTE device, none of our 10 devices is one — §1.3).
                                      # v5.5.0's UMBB exporter likewise needs a device of type `umbb`
                                      # (U5G Max); live types 2026-10-05: uap 4, udm 1, usw 5.
                                      # The sysinfo change is a bug fix: the same 16 existing
                                      # unpoller_controller_* series start carrying real values.
rollback_class: git-revert            # stateless exporter, no PVC, no migration, no schema change
finding_refs: [F-464c9d8b, F-8551ca27] # F-464c9d8b = the OPEN version-lane row (title re-read
                                      # 2026-10-05: "… v5.2.8 -> v5.5.0 (minor)"). Script-owned, ONE row
                                      # per component: it auto-closes when the pin moves off v5.2.8 —
                                      # never close it by hand. F-8551ca27 = the plan-section row
                                      # "re-target unpoller-5.4.0 to v5.5.0" — remedied by this refresh,
                                      # already RESOLVED (commit ced94db9); kept as the provenance ref.
                                      # (F-23119c27, the earlier v5.2.10-patch row, is resolved.)
review: ready-for-go@2026-10-05   # plan-reviewer 2026-10-05: needs-fix (B1 30d-vs-1w evidence, B2 absence greps) -> fixed -> delta ready-for-go
status: vetted
window: "nightly:2026-10-14"   # scheduled 2026-10-05: AUTO-NIGHT (image graduated); alone; clear of kps (10-08), flux-distribution, coredns-1.48.2 (sat 10-17)
premises:
  - id: live-image-still-v5.2.x
    why: >-
      `current:` is v5.2.8. The §1.2 review covers v5.2.8…v5.5.0, so a later
      v5.2.9–v5.2.11 patch landing first via Step 0's direct-bump lane
      (max: patch allows it) only SHRINKS the reviewed delta and is fine. Any
      other value (a v5.3/v5.4/v5.5 already live, or an older tag) means this plan
      is a no-op or mis-based: verify per §4 and retire, do not execute.
    run: kubectl get deploy -n monitoring unpoller -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_matches: '^ghcr\.io/unpoller/unpoller:v5\.2\.(8|9|10|11)$'
  - id: git-pin-still-v5.2.x
    why: >-
      Git side of the same premise; the §3.2 edit targets exactly one
      `tag: v5.2.x` line under image:. Zero or two matches = the file moved.
      (Any v5.2.x matches here; the live-image premise above pins the range.)
    run: "git show HEAD:kubernetes/apps/monitoring/unpoller/app/helmrelease.yaml | grep -c '^      tag: v5[.]2[.][0-9]*$'"   # no '|' in the regex: plan-premises splits stages on it
    expect_exact: "1"
  - id: chart-still-2.4.0
    why: >-
      §1.1's chart-leg decision (stay on 2.4.0, keep the override) is argued
      for chart 2.4.0 only. Per F-a2cd7a11 the chart leg moves in a separate
      lane and can change under this plan without touching the image.
    run: kubectl get helmrelease -n monitoring unpoller -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: "2.4.0"
  - id: http-chart-repo-newest-still-2.4.0
    why: >-
      The lockstep answer in §1.1 ("no chart to move to on our source, so the
      image.tag override must stay") rests on the HTTP repo's newest stable
      chart being 2.4.0 (appVersion v3.5.0). If upstream publishes a newer
      chart there, the chart half must be re-assessed (and may make the
      override droppable) before this plan runs.
    run: "helm show chart unpoller --repo https://unpoller.github.io/helm-chart | grep -E '^version:'"
    expect_exact: "version: 2.4.0"
  - id: helmrelease-ready
    why: "Do not stack a bump on an already-failing release."
    run: kubectl get helmrelease -n monitoring unpoller -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: chart-service-still-disabled
    why: >-
      Keeps chart 2.4.0's own Service (port named `tcp`) from displacing the
      hand-written one (port `http`, which the ServiceMonitor scrapes). If
      flipped, every unpoller_* series is already gone and §2 baselines lie.
    run: kubectl get helmrelease -n monitoring unpoller -o jsonpath='{.spec.values.service.enabled}'
    expect_exact: "false"
  - id: chart-podmonitor-still-disabled
    why: >-
      A second 30s scrape doubles UniFi controller API load (429 lockout
      path) and duplicates every series, corrupting §4.4's counts.
    run: kubectl get helmrelease -n monitoring unpoller -o jsonpath='{.spec.values.podMonitor.enabled}'
    expect_exact: "false"
  - id: handwritten-service-owns-port-http
    why: "The ServiceMonitor scrapes `port: http`; the Service's port must still carry that name."
    run: kubectl get svc -n monitoring unpoller -o jsonpath='{.spec.ports[0].name}'
    expect_exact: http
  - id: servicemonitor-scrapes-port-http
    why: "Other half of the same wiring."
    run: kubectl get servicemonitor -n monitoring unpoller -o jsonpath='{.spec.endpoints[0].port}'
    expect_exact: http
  - id: pod-running
    why: "A baseline can only be taken from a running exporter."
    run: kubectl get pods -n monitoring -l app.kubernetes.io/name=unpoller -o jsonpath='{.items[0].status.phase}'
    expect_exact: Running
  - id: no-env-on-workload
    why: >-
      v5.2.9 bumps golift.io/cnfg 0.4.0 -> 0.5.0, whose only functional change
      is ParseENV map handling (§1.4c). The workload carrying NO env at all is
      what makes that change unreachable here. If env ever appears, re-run
      §1.4c before executing.
    run: kubectl get deploy -n monitoring unpoller -o jsonpath='{.spec.template.spec.containers[0].env[*].name}' | wc -c | tr -d ' '
    expect_exact: "0"
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/unifi-controller-rate-limit.md
  - docs/sops/monitoring.md
  - docs/sops/auto-update.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-09-30"                # refreshed 2026-10-05: retarget v5.4.0 -> v5.5.0
---

# unpoller: image v5.2.8 → v5.5.0 (image minor; chart leg deliberately stays 2.4.0, override stays)

> **Refreshed 2026-10-05:** retargeted in place from v5.4.0 to v5.5.0 (plan_id and
> scratch paths keep `5.4.0`). The v5.4.0 → v5.5.0 delta is read in §1.2 (last row)
> and §1.3 (UMBB bullet); everything argued for v5.4.0 carries unchanged.

## 1) Summary & why held

### 1.1 What changes — and the chart half, decided explicitly

**Image leg: one line.** `image.tag: v5.2.8 → v5.5.0` in
`kubernetes/apps/monitoring/unpoller/app/helmrelease.yaml`, plus a lineage
comment. No `upConfig` (secret) edit, no policy edit.

**Chart leg: does NOT move, and the `image.tag` override can NOT be dropped.**
The dispatch asked for both halves in lockstep; the lockstep answer, measured
2026-09-30, is "the chart has nothing to lockstep to":

| Source | Chart versions | appVersion | Templates/values vs 2.4.0 |
|---|---|---|---|
| HTTP `https://unpoller.github.io/helm-chart` (our `HelmRepository/unpoller`) | newest stable **2.4.0** (`helm show chart` confirms; the `2.11.2-ChartN` entries are 2024 semver pre-releases for app v2.11.2, which helm and our tooling correctly ignore) | v3.5.0 | — |
| OCI `oci://ghcr.io/unpoller/helm-chart/unpoller` | 2.5.0, 2.6.0 (2026-08-19), 2.7.0, 2.8.0 (2026-09-03) | v5.3.0, v5.3.0, v5.2.2, **v5.2.3** — non-monotonic | **byte-identical** (`diff -r` of the pulled charts: only `Chart.yaml` + `README.md` differ) |

Consequences:

1. **No chart anywhere ships appVersion ≥ v5.5.0** (max is v5.3.0, on two
   August charts whose appVersion predates that app release). The chart
   templates `image: "{{ .Values.image.repository }}:{{ .Values.image.tag | default .Chart.AppVersion }}"`,
   so dropping the override would render **v3.5.0** on 2.4.0 and **v5.2.3** on
   2.8.0 — a silent downgrade in both cases. The override stays, and the
   `*unpoller*` deny rule's precondition for removal ("a chart ships an
   appVersion at or above the pinned tag") remains unmet.
2. **A chart move would buy nothing.** Rendered with our exact values
   (`helm template`, 2026-09-30), 2.4.0 vs 2.8.0 differs only in the
   `helm.sh/chart` and `app.kubernetes.io/version` labels (four places, one of
   them the pod template → one pod roll). Selector labels are unchanged.
3. **It would also require a source move** (2.5.0+ exist only in OCI), which is
   `flux-oci-chart-sources` stage 8's job (§3.5 there parks unpoller for exactly
   this reason). Hence `flux-oci-chart-sources` in `conflicts_with`, and the
   `http-chart-repo-newest-still-2.4.0` premise: if a newer chart lands on our
   source, this decision is re-taken, not assumed.

Live today: chart 2.4.0 + image v5.2.8. After this plan: chart 2.4.0 + image v5.5.0.
(Chart sources re-read 2026-10-05: HTTP newest still 2.4.0 / appVersion v3.5.0; OCI newest still 2.8.0.)

### 1.2 Upstream evidence — six releases in eight days, measured

`gh`/API `compare/v5.2.8...v5.5.0`, measured 2026-10-05: `status: ahead`,
**17 commits (10 non-merge), 27 files** (v5.2.8...v5.4.0 alone: 13 / 15). Per hop:

| Hop | Commits (non-merge) | Files | Effect on us |
|---|---|---|---|
| v5.2.8→v5.2.9 | `28b1044` docs(manual) links; `5675702` deps "all group, 2 updates" | `examples/MANUAL.md`, `go.mod`, `go.sum` | **config libs**: `golift.io/cnfg` 0.4.0→0.5.0, `golift.io/cnfgfile` →0.1.0, `BurntSushi/toml` 1.5.0→1.6.0 (indirect). §1.4c |
| v5.2.9→v5.2.10 | `3cfd05b` Homebrew cask branch | `.goreleaser.yaml` | none (packaging) |
| v5.2.10→v5.2.11 | `45d60f7` `unpoller/unifi/v6` 6.1.2→6.1.3 | `go.mod`, `go.sum` | **login body** now JSON-marshalled (§1.4a); `golang.org/x/net` 0.58→0.59 |
| v5.2.11→v5.3.0 | `912ea91` feat(protect): air quality; `c742df9` unifi 6.2.0 | `pkg/{prom,influx,datadog}unifi/protect.go` (+tests), `go.mod/sum` | Protect exporter — **inert, Protect polling off** (§1.3); unifi 6.2.0 also carries the **sysinfo envelope fix** (§1.4b) |
| v5.3.0→v5.4.0 | `2819753` feat: export live U-LTE failover status | `pkg/{prom,influx,datadog,otel}unifi/uap.go`, tests | new `unpoller_lte_*` / InfluxDB `uap_lte` — **inert, no LTE device** (§1.3) |
| v5.4.0→v5.5.0 | `00b6f33` feat: export UMBB (U5G Max) cellular modem metrics; `5ed9b00` `unpoller/unifi/v6` 6.2.0→6.3.0; `dd8a424` review fixes (PR #1102) | new `pkg/{prom,influx,datadog,otel}unifi/umbb.go`; 2-6 line `case *unifi.UMBB` additions in each output's `switchExport`/`Run`; `pkg/inputunifi/{collector,collectevents}.go` (+UMBB loops, debug-log format); `go.mod/sum` | new `unpoller_device_mbb_*` family (25 descriptors, no name shared with any existing family) + InfluxDB UMBB measurement — **inert, no `umbb` device** (§1.3). unifi 6.3.0 (`compare v6.2.0...v6.3.0`: 1 commit, 7 files) only adds the `umbb` case to `parseDevices` + the `UMBB` type; zero deletions outside a struct re-alignment. Only visible side effect: the INFO line `UniFi Measurements Exported. … USW: %d, UMBB: %d, DPI …` gains `UMBB: 0` — the prefix greps in `docs/sops/unifi-controller-rate-limit.md` still match. |

No release note marks anything breaking (v5.5.0's body is the four-line
goreleaser changelog above). **Untouched across the whole hop** (file list
re-read 2026-10-05): `Dockerfile` (still `FROM gcr.io/distroless/static-debian13`),
`examples/up.conf.example` (config contract) and `pkg/poller/`. `pkg/inputunifi/`
IS touched since v5.4.0, but only by additive `for _, d := range …UMBBs` loops
(empty slice here) and one extra `%d` in a debug log line.

**No metric our repo reads is renamed or removed.** The v5.4.0→v5.5.0 diff has
zero deleted lines in `pkg/promunifi/` outside the reformatted report log line,
and every `unpoller_*` name the repo selects (grep 2026-10-05 of
`kubernetes/apps/monitoring/unpoller/app/{prometheusrule,dashboards/*}.yaml` and
`kube-prometheus-stack/app/slo-burn-rate-alerts.yaml`: `device_info`,
`device_uptime_seconds`, `client_*`, `device_port_*`, `device_vap_*`,
`site_*`, `prometheus_cache_age_seconds`, `prometheus_refresh_failures_total`, …)
is emitted by unchanged code.

**Image config, amd64, pulled from ghcr 2026-09-30:**

| | v5.2.8 (live / rollback) | v5.4.0 (previous target) | **v5.5.0 (target)** |
|---|---|---|---|
| index digest | `sha256:ca82e584…` (= live pod `imageID`) | `sha256:12fe7418…` | **`sha256:0f45de09caec353b68f67524f864a6c68fc551600261c2002312750b52fe38a8`** (= `latest`) |
| amd64 child | `sha256:a5316d72…` | `sha256:d2cdb6fd…` | **`sha256:237f13ff02759d4531ea247ad703f43cf599eadab810dde3c9e15e6f3fd64f9b`** |
| `User` / `Entrypoint` | `'0'` / `/usr/bin/unpoller` | same | same |
| `SSL_CERT_FILE` | `/etc/ssl/certs/ca-certificates.crt` | same | same |
| layers / created | 15 / 2026-09-24T01:10:13Z | 15 / 2026-09-29T21:27:31Z | 15 / 2026-10-01T21:09:34Z |

(v5.5.0 column pulled from ghcr 2026-10-05.)

`User` unchanged matters because the HelmRelease deliberately does not set
`runAsUser` and does set `readOnlyRootFilesystem: true`.

### 1.3 The three "feat" commits are inert here — measured, not assumed

- **Protect air quality (v5.3.0).** Only reached from `exportProtectDevices`,
  which runs only when Protect data is collected (`save_protect`). Our decrypted
  config (key names only, values never printed; 2026-09-30) has
  `[unifi]`, `[[unifi.controller]]`, `[prometheus]`, `[influxdb]` and **no
  `save_protect` key** (default false). Live: `count({__name__=~"unpoller_(lte|sensor|protect).*"})`
  = **empty** (0 series). Note the refactor also re-routes the EXISTING
  temperature/humidity/light gauges through new helpers — also Protect-only, so
  also inert.
- **U-LTE failover (v5.4.0).** `exportLTE`/`batchLTE` return immediately unless
  `hasLTEStatus()` sees `lte_*` fields on a UAP. Live `count by (model,type)
  (unpoller_device_info)` 2026-09-30: `U7LR, UAPL6, UAP6MP, U7PRO` (uap),
  `UDMPRO` (udm), `USMINI×2, USM8P, US624P, US48PRO` (usw) — **no U-LTE /
  U-LTE-Pro**. So no `unpoller_lte_*` series and no `uap_lte` InfluxDB
  measurement will appear. (If one ever does, that is the positive-control that
  the code path is live — informational, §4.8.)
- **UMBB / U5G Max cellular (v5.5.0).** `exportUMBB` is reached only from the
  `case *unifi.UMBB` arm, and unifi 6.3.0 creates a `UMBB` only for a device
  whose `type` is `umbb`. Live `count by (type) (unpoller_device_info)`
  2026-10-05: `uap 4, udm 1, usw 5` — none. The 25 `unpoller_device_mbb_*`
  descriptors are registered (Describe) but emit no series;
  `count({__name__=~"unpoller_(lte|sensor|protect|device_mbb).*"})` = **empty**
  (2026-10-05). No `mbb` name collides with an existing family (grep of
  `pkg/promunifi/*.go` at v5.5.0: only `umbb.go` defines `mbb_*`), so the
  registry cannot reject the collector on start.

### 1.4 The three changes that DO reach us

**1.4a Login body re-encoding (unpoller/unifi #250, in v6.1.3; unchanged in 6.3.0).** Before:
`fmt.Sprintf('{"username":"%s","password":"%s"}', …)`; after:
`json.Marshal(map[string]string{…})`. For a credential with no JSON-special
characters the two bodies decode to the same object (key order changes;
`json.Marshal` also \u-escapes `<>&`, which any JSON parser decodes back). Our
credential (length/charset checked 2026-09-30, values never printed): user and
password contain **none** of `" \ < > &`. So the controller receives a
semantically identical login. This matters more than it looks because the live
pod **re-authenticates repeatedly** (`Re-authenticating to UniFi Controller …`
at 00:55 and 01:15 on 2026-09-30 — the known UDM 401/500 flakiness, §6), so the
new encoder runs on every re-auth, not only at startup; and the controller's
login endpoint is the rate-limited one (`docs/sops/unifi-controller-rate-limit.md`).
A broken login presents as **sustained** refresh failures and a growing cache
age — exactly §4.5's gate. (TLS verification stays disabled: AR-114 / F-cafe8865,
already accepted; §2.4 asserts `verify_ssl=false` is unchanged.)

**1.4b Sysinfo envelope fix (unpoller/unifi #248, in v6.2.0) — a visible, one-time
series change.** `GetSysinfoSite` used to decode the `{"data":[…]}` envelope
straight into the struct, leaving every field zero. It now reads `data[0]`, and
returns `ErrNoSysinfoData` if the array is empty (the collector logs that at
debug level and continues). Live 2026-09-30 confirms we have the bug today:
all 17 `unpoller_controller_*` families are present and **every value except
`controller_info` and `controller_up` reads 0** — `controller_uptime_seconds 0`,
`https_port 0`, `inform_port 0` — with `version=""`, `build=""`, and
`hostname="<site name> (default)"`, i.e. the site-name fallback that fires only
when both Hostname and Name are empty.

After v5.5.0, one of two things happens, and both are acceptable:
- **Expected:** real values arrive, and `hostname` changes to the controller's
  real hostname, so the 16 labelled `unpoller_controller_*` series change
  identity once (old ones fall out of the 5-min lookback). This is the
  **positive, unfakeable new-binary signal** §4.3 uses: no v5.2.8 code path can
  produce `unpoller_controller_uptime_seconds > 0`.
- **Tolerated:** the UDM returns an empty `data` array → sysinfo series go
  **absent**. That is a loss of 16 series that today carry only zeros. Not a
  revert trigger; record it (§4.3).

**Who reads these series:** `grep -rln unpoller_controller kubernetes/ runbooks/ docs/`
returns nothing outside `runbooks/maintenance/plans/` (re-run 2026-10-05) — no rule, dashboard or runbook. The
`UnifiControllerUnreachable` alert reads `up{job="unpoller"}`, not these.

**1.4c Config-library bumps (v5.2.9).** This is why the hop is not waved
through: the libraries that parse our `up.conf` moved.
- `golift.io/cnfg` 0.4.0→0.5.0: 10 commits; functional change confined to
  `mapparse.go` — `PeelMapKey` exported and **`ParseENV` overlays existing map
  values**. Env-only. Unreachable: the workload has **no env** (premise
  `no-env-on-workload`).
- `golift.io/cnfgfile` →0.1.0: `file.go` refactor (explicit close instead of
  `defer` in the loop, decode moved to `unmarshalOpenFile` — same TOML/JSON/YAML
  dispatch by suffix, same error wrapping), `filepath.go` lint-only.
- `BurntSushi/toml` 1.5.0→1.6.0 (indirect): the TOML decoder itself. Not
  provable from metadata — so the runtime gates are the startup lines that echo
  the parsed config back: `Prometheus scrape cache enabled, refresh interval: 2m0s`
  (our `interval = "2m"`; a mis-parse prints `disabled` or `1m0s`),
  `Poller->InfluxDB started, … interval: 2m0s, … bucket: default, org: influxdata`,
  and `=> URL: https://<controller> (verify SSL: false …)` (§4.2).

### 1.5 Why it was held — honest verdict

The `*unpoller*` rule in `runbooks/auto-update-policy.yaml` is `max: patch`, so
coverage.py blocks every minor. Its **reason** argues only about CHART bumps
outranking a pinned image, which an image-only minor on an unchanged chart
does not engage. But unlike the last three patches, this hop carries real
behaviour deltas (config-parser libs, login encoding, a sysinfo decode fix that
changes label values), so a human-readable review is warranted for a minor and
the hold is **not** a pure false positive. `risk: low`, because every delta is
either inert here, semantically identical, or strictly a fix, and the rollback
is a clean revert of a stateless exporter.

**Repo correction (applied 2026-10-01, text only):** the rule reason said
"Chart minors go through the PLAN lane" but `max: patch` also routes **image**
minors here. The reason now reads "Chart AND image minors go through the PLAN
lane (max: patch); chart minors stay there until …". No version field or
`max:` changed; executing this plan still does not edit policy.

### 1.6 Derived execution class

`capability_change: false`, `rollback_class: git-revert`, `needs_reboot: false`,
`autonomy_override` unset,
`shared: []`, `risk: low` → derives `auto-night` in `runbooks/autonomy-policy.yaml`;
with a `ready-for-go` review it becomes SD-10 eligible. The plan does not claim
a class; confirm with `.venv/bin/python3 runbooks/maintenance-plan.py --open`.

## 2) Pre-checks

All scratch state lives in `/private/tmp/claude-501/unpoller-5.4.0` — agent Bash
calls share no shell variables, so every later step reads files, not variables.

1. **Premises** (the gate refuses the plan otherwise):
   ```bash
   .venv/bin/python3 runbooks/plan-premises.py unpoller-5.4.0 --require-premises
   ```
2. **Baseline health:**
   ```bash
   flux get helmrelease unpoller -n monitoring
   kubectl -n monitoring get pods -l app.kubernetes.io/name=unpoller
   flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
   runbooks/update-marker.sh list        # a live marker for another monitoring component = wait
   ```
3. **Target + rollback tags published; re-resolve the target** (unpoller shipped
   six releases in eight days, and the plan was already retargeted once — expect it to move again):
   ```bash
   python3 - <<'EOF'
   import json,urllib.request
   tok=json.load(urllib.request.urlopen("https://ghcr.io/token?scope=repository:unpoller/unpoller:pull&service=ghcr.io"))['token']
   for t in ("v5.2.8","v5.5.0","latest"):
       r=urllib.request.Request("https://ghcr.io/v2/unpoller/unpoller/manifests/"+t,method="HEAD",
         headers={"Authorization":"Bearer "+tok,"Accept":"application/vnd.oci.image.index.v1+json"})
       h=urllib.request.urlopen(r); print(t,h.status,h.headers["docker-content-digest"])
   EOF
   curl -s "https://api.github.com/repos/unpoller/unpoller/releases?per_page=8" \
     | python3 -c "import sys,json;[print(r['tag_name'],r['published_at'][:16],'pre=%s'%r['prerelease'],'draft=%s'%r['draft']) for r in json.load(sys.stdin)]"
   ```
   Measured 2026-10-05: v5.2.8 `200 sha256:ca82e584…`, v5.5.0 `200 sha256:0f45de09…`,
   latest `200 sha256:0f45de09…`; newest release v5.5.0 (pre=False). **If a newer
   non-prerelease N exists**, run `compare/v5.5.0...N` and re-review before retargeting: anything in
   `pkg/promunifi/` beyond additive descriptors, `pkg/influxunifi/` beyond
   additive tags/measurements, `examples/up.conf.example`, `Dockerfile`, or a
   `golift.io/cnfg*`/`toml`/`unpoller/unifi` bump is a re-review, not a
   find-and-replace. Never take `pre=True`/`draft=True`.
4. **Config facts the §1 argument rests on** (counts only — never print the config):
   ```bash
   S=$(mktemp); sops -d kubernetes/apps/monitoring/unpoller/app/secret.sops.yaml > "$S"
   grep -cE 'interval[[:space:]]*=[[:space:]]*"2m"' "$S"      # expect 2
   grep -cE 'verify_ssl[[:space:]]*=[[:space:]]*false' "$S"   # expect 1  (§1.4a TLS posture unchanged)
   grep -ciE 'save_protect' "$S"                              # expect 0  (§1.3 Protect path off)
   grep -ciE 'otel|opentelemetry' "$S"                        # expect 0
   grep -cE '^[[:space:]]*pass[[:space:]]*=.*[<>&\\]' "$S"    # expect 0  (§1.4a: no JSON-special chars; a '"' inside the value would already break TOML)
   grep -cE '^[[:space:]]*user[[:space:]]*=.*[<>&\\]' "$S"    # expect 0  (§1.4a, same check for the username)
   # POSITIVE CONTROLS -- prove the file decrypted and the absence greps above read the real config:
   grep -cE '^[[:space:]]*pass[[:space:]]*=' "$S"             # expect 1
   grep -cE '^[[:space:]]*user[[:space:]]*=' "$S"             # expect 1
   grep -cF '[unifi]' "$S"                                     # expect >= 1
   rm -f "$S"
   ```
   Measured 2026-09-30: 2 / 1 / 0 / 0 / 0; positive controls and the `user`
   special-char line re-measured 2026-10-05: 0 / 1 / 1 / 1. **If any positive
   control reads 0, the decrypt or the file layout failed and every `expect 0`
   above is meaningless — STOP.** The patterns are `[[:space:]]`-based
   and unanchored at column 0 on purpose: the TOML is indented inside the
   Secret's `stringData`, and `\s` is not a BSD `grep -E` class.
   **If `save_protect` is now present/true, stop** — §1.3's inertness claim no
   longer holds and the Protect refactor must be reviewed.
5. **Prometheus baseline — MEASURE IN THIS SESSION; the numbers below are magnitude only:**
   ```bash
   D=/private/tmp/claude-501/unpoller-5.4.0; mkdir -p "$D"; : > "$D/baseline-prom.txt"
   kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!
   sleep 3
   q(){ r=$(curl -s --data-urlencode "query=$1" http://localhost:19090/api/v1/query \
        | python3 -c "import sys,json;print([r['value'][1] for r in json.load(sys.stdin)['data']['result']])"); echo "$1 => $r" | tee -a "$D/baseline-prom.txt"; }
   q 'up{job="unpoller"}'                                              # ['1']
   q 'count(unpoller_site_adopted)'                                    # ['3']
   q 'count(unpoller_device_uptime_seconds)'                           # ['10']
   q 'count({__name__=~"unpoller_.*"})'                                # ['8024'] 2026-09-30; ['6873'] 2026-10-05
   q 'unpoller_prometheus_cache_age_seconds'                           # ['38.79']
   q 'increase(unpoller_prometheus_refresh_failures_total[24h])'       # ['0']
   q 'unpoller_prometheus_refresh_failures_total'                      # raw counter; if > 0, evaluate §4.5 only at >= 10 min after Ready
   q 'max_over_time(increase(unpoller_prometheus_refresh_failures_total[10m])[7d:5m])'  # INFORMATIONAL: ['0'] 2026-10-05 (archived 2.22, see below)
   q 'max_over_time(unpoller_prometheus_cache_age_seconds[7d])'        # INFORMATIONAL: ['101.33'] 2026-10-05 (archived 329.9, see below)
   q 'unpoller_controller_uptime_seconds'                              # ['0']   <- the sysinfo bug (§1.4b)
   q 'count({__name__=~"unpoller_(lte|sensor|protect|device_mbb).*"})' # []      (0 series)
   q 'count by (type) (unpoller_device_info)'                          # uap 4, udm 1, usw 5 — a `umbb` type here voids §1.3's UMBB bullet
   kill $PF 2>/dev/null
   kubectl -n monitoring get pod -l app.kubernetes.io/name=unpoller \
     -o jsonpath='{.items[0].status.containerStatuses[0].imageID}{"\n"}' | tee "$D/baseline-imageid.txt"
   ```
   Authoring values 2026-09-30 in the comments. The total series count tracks
   associated wireless clients and drifts by the day; re-measured by the plan
   review (sweep b23be87b) its 6 h spread was `min 7684 / max 7920` (a 3.0%
   range, ±1.5% about the middle), wider than the 8011–8140 seen at authoring,
   and on 2026-10-05 it read **6873** — a further ~11% below that band.
   §4.4 therefore uses ±2% against a **same-session** baseline taken right
   before the bump (nightly window, few clients joining/leaving), widened to
   **±3%** if the window runs in daytime. Never compute the band from a printed
   number above.
   The two `max_over_time` lines relate to the **bad-case evidence** for §4.5.
   Prometheus retention is **1w** (live `storage.tsdb.retention.time`, 2026-10-05),
   so they use `[7d]`. The evidence itself is **ARCHIVED**: measured 2026-09-30
   (sweep b23be87b), the 10-min refresh-failure increase had reached **2.22**,
   the counter had moved (`changes(...)` = **2**) and cache age had peaked at
   **329.9 s** — both gates demonstrably read their failing side on this exact
   series, so they are not inert. Those samples have **aged out of the 1w
   retention**; on 2026-10-05 the `[7d]` lines read `0` / `0` / `101.33`.
   **A reading of 0 / < 150 at execution is expected and is NOT a STOP.**
   If the raw `unpoller_prometheus_refresh_failures_total` is already > 0 here
   that is fine (it is a counter since pod start); it only means §4.5 must be
   read at ≥ 10 min after Ready so the `[10m]` window excludes the v5.2.8 pod's
   history.
   **If `unpoller_controller_uptime_seconds` is already > 0 here**, something
   other than v5.2.8 is answering (or upstream's controller changed) — §4.3 would
   then prove nothing; stop and find out.
6. **InfluxDB write-path baseline** (token assigned to a 0600 file, never echoed):
   ```bash
   D=/private/tmp/claude-501/unpoller-5.4.0; mkdir -p "$D"
   (umask 077; sops -d kubernetes/apps/monitoring/unpoller/app/secret.sops.yaml \
     | python3 -c "
   import sys
   for line in sys.stdin:
       s=line.strip()
       if s.startswith('auth_token'):
           print(s.split('=',1)[1].strip().strip('\"')); break" > "$D/influx.tok")
   test -s "$D/influx.tok" || echo "NO TOKEN - STOP"
   kubectl port-forward -n databases svc/influxdb-influxdb2 18086:80 >/dev/null 2>&1 & PF=$!
   sleep 3
   curl -s 'http://localhost:18086/api/v2/query?org=influxdata' \
     -H "Authorization: Token $(cat "$D/influx.tok")" -H 'Content-Type: application/vnd.flux' -H 'Accept: application/csv' \
     -d 'from(bucket:"default") |> range(start:-2h) |> filter(fn:(r)=>r._measurement=="uap_radios") |> keep(columns:["_time"]) |> sort(columns:["_time"],desc:true) |> limit(n:1)' \
     | tee "$D/baseline-influx.csv"
   kill $PF 2>/dev/null
   ```
   Keep `range(start:-2h)`: with a narrower window a write path dead for longer
   than the window returns **no rows** (a bare `\r`, exit 0) instead of the
   frozen timestamp §4.6 is written to detect. Objects verified 2026-09-30:
   `svc/influxdb-influxdb2` (ns databases, port 80), org `influxdata`, bucket
   `default`.

## 3) Steps

1. **Update marker** (no Alertmanager silence needed: stateless 1-replica
   RollingUpdate, scrape gap ≤ one 60 s interval vs the 15 m `for:` on the
   `absent()` guards):
   ```bash
   runbooks/update-marker.sh add unpoller monitoring 1 "v5.2.8->v5.5.0 image minor (plan unpoller-5.4.0)"
   ```
2. **Edit the tag + lineage comment** in one scripted edit. **Dry-tested
   2026-10-05 on a scratch copy of the current file on macOS**; the resulting
   diff is exactly:
   ```
   57c57,65
   <       tag: v5.2.8
   ---
   >       # 2026-10-XX: v5.2.8 -> v5.5.0 image minor (plan unpoller-5.4.0). Deltas: go deps incl.
   >       # the config libs (golift cnfg 0.5.0 / cnfgfile 0.1.0 / BurntSushi toml 1.6.0), unifi lib
   >       # v6.3.0 (JSON-encoded login body; sysinfo envelope fix, so unpoller_controller_* stop
   >       # reading 0 and gain the real hostname label), and three additive exporters that are inert
   >       # here (Protect air-quality: save_protect unset; U-LTE and UMBB/U5G-Max cellular: no such
   >       # device). No metric rename or removal.
   >       # Chart STILL 2.4.0 and this override STAYS: no published chart (HTTP 2.4.0, OCI
   >       # 2.5.0-2.8.0, all template-identical) ships an appVersion >= v5.5.0.
   >       tag: v5.5.0
   ```
   ```bash
   python3 - kubernetes/apps/monitoring/unpoller/app/helmrelease.yaml <<'EOF'
   import sys
   p=sys.argv[1]; t=open(p).read()
   old="      # Chart still 2.4.0.\n      tag: v5.2.8\n"
   new=("      # Chart still 2.4.0.\n"
   "      # 2026-10-XX: v5.2.8 -> v5.5.0 image minor (plan unpoller-5.4.0). Deltas: go deps incl.\n"
   "      # the config libs (golift cnfg 0.5.0 / cnfgfile 0.1.0 / BurntSushi toml 1.6.0), unifi lib\n"
   "      # v6.3.0 (JSON-encoded login body; sysinfo envelope fix, so unpoller_controller_* stop\n"
   "      # reading 0 and gain the real hostname label), and three additive exporters that are inert\n"
   "      # here (Protect air-quality: save_protect unset; U-LTE and UMBB/U5G-Max cellular: no such\n"
   "      # device). No metric rename or removal.\n"
   "      # Chart STILL 2.4.0 and this override STAYS: no published chart (HTTP 2.4.0, OCI\n"
   "      # 2.5.0-2.8.0, all template-identical) ships an appVersion >= v5.5.0.\n"
   "      tag: v5.5.0\n")
   assert t.count(old)==1, "anchor not found exactly once: %d" % t.count(old)
   open(p,'w').write(t.replace(old,new)); print("edited")
   EOF
   grep -n '^      tag:' kubernetes/apps/monitoring/unpoller/app/helmrelease.yaml   # exactly one line: tag: v5.5.0
   git diff --stat kubernetes/apps/monitoring/unpoller/app/helmrelease.yaml         # 1 file, +9 -1
   ```
   Replace `XX` with the execution day before committing. **If a v5.2.9–v5.2.11
   patch landed first** (premise allows it), the anchor still reads
   `tag: v5.2.x`: change the `old` string's tag and the comment's "v5.2.8" to
   the live value — the `assert` refuses to write otherwise, which is the point.
   Do NOT touch `chart.spec.version`, `HelmRepository/unpoller`, or
   `runbooks/auto-update-policy.yaml` (§1.1, §1.5).
3. **Commit, shared-worktree safe:**
   ```bash
   git fetch origin main && git merge --ff-only origin/main
   git commit --only kubernetes/apps/monitoring/unpoller/app/helmrelease.yaml \
     -m "chore(unpoller): image v5.2.8 -> v5.5.0 on chart 2.4.0 (plan unpoller-5.4.0)"
   git show --stat HEAD          # exactly ONE file
   git log -1 --format=%s        # MUST be your subject; amend before push if not
   git push origin main
   ```
4. **Let Flux reconcile on the webhook** (no manual reconcile by default):
   ```bash
   kubectl -n monitoring rollout status deploy/unpoller --timeout=10m   # green is NOT proof; §4.1 checks the digest
   ```
   Only if nothing rolled after 10 min: `flux get kustomization unpoller -n monitoring`
   must show the pushed revision; if the source is stale,
   `flux reconcile kustomization unpoller -n monitoring --with-source`.
5. **Close-out after §4 passes:** `runbooks/update-marker.sh clear unpoller`;
   `rm -rf /private/tmp/claude-501/unpoller-5.4.0` (holds the InfluxDB token —
   also after a §5 rollback); delete this plan file in the close-out commit;
   record via `autonomy-record.py` per the window agent's contract. **Scrub
   inbound refs first** — as of 2026-09-30 no other plan names `unpoller-5.4.0`,
   but re-check, and run the validator before pushing:
   ```bash
   grep -rn 'unpoller-5\.4\.0' runbooks/maintenance/plans/ | grep -v 'plans/unpoller-5.4.0.md'
   .venv/bin/python3 runbooks/maintenance-plan.py --validate
   ```
   `F-464c9d8b` is script-owned (one row per target) and auto-closes on the next
   sweep once the pin has moved off v5.2.8 — never close it by hand.

## 4) Verification

`Ready=True` proves nothing for this component — a running unpoller that stopped
emitting looks identical to a healthy one. Wait **≥ 5 min after the new pod is
Ready** before §4.4 (see the box there).

### 4.0 Pin exactly one pod, persist its full log

The rollout is `RollingUpdate` on 1 replica (live 2026-09-30:
`.spec.strategy.type=RollingUpdate`), so during the roll the outgoing v5.2.8 pod
still matches the label selector and a Terminating pod keeps `phase: Running`.
`kubectl logs -l …` would concatenate the OLD pod's banner — which prints every
§4.2 line verbatim — and pass on failure.
```bash
D=/private/tmp/claude-501/unpoller-5.4.0; mkdir -p "$D"; rm -f "$D/pod" "$D/pod.log"
kubectl -n monitoring get pods -l app.kubernetes.io/name=unpoller \
  -o jsonpath='{range .items[*]}{.metadata.name}{"  phase="}{.status.phase}{"  deleting="}{.metadata.deletionTimestamp}{"\n"}{end}'
N=$(kubectl -n monitoring get pods -l app.kubernetes.io/name=unpoller --no-headers | wc -l | tr -d ' ')
POD=$(kubectl -n monitoring get pods -l app.kubernetes.io/name=unpoller -o jsonpath='{.items[0].metadata.name}')
if [ "$N" = 1 ] && [ -n "$POD" ] && [ -z "$(kubectl -n monitoring get pod "$POD" -o jsonpath='{.metadata.deletionTimestamp}')" ]; then
  echo "$POD" > "$D/pod" && kubectl -n monitoring logs "$POD" --tail=-1 > "$D/pod.log" \
    && echo "PINNED POD=$POD log_lines=$(wc -l < "$D/pod.log" | tr -d ' ')"
else
  echo "GATE 4.0 NOT MET (N=$N, POD='$POD') - wait and re-run; evaluate nothing below"
fi
```
N=0 is a rollout FAIL, not a flaky query. Identity (old vs new) is §4.1's job.

1. **New bytes are running.**
   ```bash
   POD=$(cat /private/tmp/claude-501/unpoller-5.4.0/pod) && test -n "$POD" && \
   kubectl -n monitoring get pod "$POD" -o jsonpath='{.spec.containers[0].image}{"  "}{.status.containerStatuses[0].imageID}{"\n"}'
   cat /private/tmp/claude-501/unpoller-5.4.0/baseline-imageid.txt
   ```
   PASS: image `ghcr.io/unpoller/unpoller:v5.5.0` AND imageID carries
   `sha256:0f45de09…` (index) or `sha256:237f13ff…` (amd64 child) AND differs
   from the baseline. FAIL signature: imageID still `sha256:ca82e584…` = the old
   bytes; everything below would be measuring v5.2.8. `sha256:12fe7418…` = v5.4.0
   committed by mistake (the pre-refresh target) — also a FAIL. No output = §4.0 not met = FAIL.
   Dry-run 2026-09-30 on the live pod printed `…:v5.2.8  …@sha256:ca82e584…` —
   the gate reports the pre-bump state, as it must.
2. **The rebuilt binary started and parsed our config identically** (§1.4c —
   this is the TOML-parser gate). Case-insensitive greps against the head of
   the pinned pod's full log (the banner is printed once; a `--tail=200` read
   late misses it — the live v5.2.8 log is already 6042 lines):
   ```bash
   L=/private/tmp/claude-501/unpoller-5.4.0/pod.log; test -s "$L" || echo "NO LOG - FAIL"
   head -40 "$L" | grep -iE 'starting up'        # MUST: [INFO] UniFi Poller v5.5.0 Starting Up! PID: 1
   head -40 "$L" | grep -iE 'scrape cache'       # MUST: Prometheus scrape cache enabled, refresh interval: 2m0s
   head -40 "$L" | grep -iE 'influxdb started'   # MUST contain: interval: 2m0s  and  bucket: default, org: influxdata
   head -40 "$L" | grep -iE 'verify ssl'         # MUST: => URL: https://<controller> (verify SSL: false, timeout: 1m0s)
   ```
   FAIL signatures: banner shows v5.2.8 (process not replaced); `scrape cache
   disabled` or `refresh interval: 1m0s` (the `"2m"` duration mis-parsed by the
   new toml/cnfg); InfluxDB line missing or a different interval/bucket/org;
   no controller URL line, or x509/`unmarshaling file` errors. Any line
   **absent** is a FAIL, not a pass. All four lines verified present with these
   exact texts on the live v5.2.8 pod 2026-09-30 (only the version differs).
3. **CONTENTS ASSERTION (new-binary proof via the sysinfo fix, §1.4b):**
   `unpoller_controller_uptime_seconds` > 0 — measured by the §4.4 `q` helper,
   compared to the §2.5 baseline of `['0']`. A v5.2.8 binary cannot produce a
   non-zero value (it decodes the envelope into a zeroed struct).
   - PASS: a single value > 0, and `unpoller_controller_info` now carries a
     non-empty `version` label (`q 'count(unpoller_controller_info{version!=""})'` → `['1']`).
   - `['0']` after the settle: the old decode is still running — cross-check §4.1;
     if §4.1 passed, the fix did not take on this controller → **record, not a revert trigger**.
   - `[]` (absent): the UDM answered with an empty `data` array (`ErrNoSysinfoData`,
     logged at debug only) → 16 all-zero series lost, nothing reads them (§1.4b) →
     **record, not a revert trigger**; file a finding so the dashboard gap is visible.
4. **CONTENTS ASSERTION (the scrape still delivers the same population)** —
   measured by the `q` helper, compared to the SAME-SESSION §2.5 baseline, ≥ 5 min after Ready:
   ```bash
   D=/private/tmp/claude-501/unpoller-5.4.0; cat "$D/baseline-prom.txt"   # missing = take §2.5 first
   kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!
   sleep 3
   q(){ echo -n "$1 => "; curl -s --data-urlencode "query=$1" http://localhost:19090/api/v1/query \
        | python3 -c "import sys,json;print([r['value'][1] for r in json.load(sys.stdin)['data']['result']])"; }
   q 'up{job="unpoller"}'                                        # == ['1']
   q 'count(unpoller_site_adopted)'                              # == baseline (3)
   q 'count(unpoller_device_uptime_seconds)'                     # == baseline (10)
   q 'count({__name__=~"unpoller_.*"})'                          # within ±2% of baseline (±3% daytime) AND >= 5000
   q 'count(count_over_time(unpoller_site_adopted[5m]))'         # > 0
   q 'unpoller_prometheus_cache_age_seconds'                     # >= 0 and < 150  (-1 = never refreshed = FAIL)
   q 'increase(unpoller_prometheus_refresh_failures_total[10m])' # == ['0']  (read >= 10 min after Ready)
   q 'unpoller_controller_uptime_seconds'                        # §4.3
   q 'count(unpoller_controller_info{version!=""})'              # §4.3
   q 'count({__name__=~"unpoller_(lte|sensor|protect|device_mbb).*"})'  # §4.8 (expected [])
   kill $PF 2>/dev/null
   ```
   An empty list `[]` on any of the first seven lines is a FAIL, never a zero.
   The `≥ 5000` floor is the part drift cannot argue away: a collapsed exporter
   (chart-Service trap, rename, login broken by §1.4a) returns 0 or single digits.
   (Lowered from 6000 on 2026-10-05: the live total read 6873 that day, so a
   6000 floor sat only ~13% under a normal reading; 5000 keeps the same
   collapse-detection power with honest headroom.)
   A count materially ABOVE the band after the settle is also a finding — §1.3
   predicts no new families here, so investigate rather than accept.
   > **Do not evaluate before the 5-minute mark.** The rollout overlaps two pods
   > for ~1 min; the ServiceMonitor's `metricRelabelings` (F-26b89cde) pin
   > `instance`/drop `pod` on `unpoller_*` so the twins merge, but the 16
   > `unpoller_controller_*` series additionally change their `hostname` label
   > (§1.4b) and both identities sit inside the 5-min lookback until it passes.
   > That is +16 at most (~0.2%), inside the band — but read after the settle anyway.
5. **CONTENTS ASSERTION (the cache poller runs at OUR interval and logins keep working):**
   `unpoller_prometheus_cache_age_seconds` exists and is `>= 0 and < 150` on two
   samples 3 min apart (re-run the §4.4 block), and
   `increase(unpoller_prometheus_refresh_failures_total[10m])` == `['0']`,
   read **≥ 10 min after Ready**. The failure signature for a broken config is
   `[]` (the gauge is only registered when the cache is enabled); `-1` means the
   cache has never completed a refresh and is a FAIL, not a small age; for a
   broken login (§1.4a) it is a growing age and a non-zero increase.
   **These gates can fail — measured, not argued** (ARCHIVED evidence, measured
   2026-09-30 in sweep b23be87b over the then-available history; aged out of the
   1w retention since): the 10-min refresh-failure increase peaked at **2.22**,
   `changes(unpoller_prometheus_refresh_failures_total)` = **2**, cache age
   peaked at **329.9** s. So both series have read their failing side on this
   exact exporter; an empty or always-zero instrument would have shown neither.
   Today's `[7d]` re-reads (`0` / `0` / `101.33` on 2026-10-05) are expected
   and NOT a STOP. Baseline 38.8 s at authoring; refresh failures are rare
   (twice in the archived window, zero in the last 7 d), so a non-zero 10-minute
   increase right after the roll is signal, not noise.
6. **CONTENTS ASSERTION (the InfluxDB write path still advances):** re-run the
   §2.6 query with the same `range(start:-2h)` ≥ 2 min after the new pod's
   `Poller->InfluxDB started` line; the newest `uap_radios` `_time` must be
   NEWER than the §2.6 baseline.
   ```bash
   D=/private/tmp/claude-501/unpoller-5.4.0
   kubectl port-forward -n databases svc/influxdb-influxdb2 18086:80 >/dev/null 2>&1 & PF=$!
   sleep 3
   curl -s 'http://localhost:18086/api/v2/query?org=influxdata' \
     -H "Authorization: Token $(cat "$D/influx.tok")" -H 'Content-Type: application/vnd.flux' -H 'Accept: application/csv' \
     -d 'from(bucket:"default") |> range(start:-2h) |> filter(fn:(r)=>r._measurement=="uap_radios") |> keep(columns:["_time"]) |> sort(columns:["_time"],desc:true) |> limit(n:1)' \
     > "$D/post-influx.csv"
   kill $PF 2>/dev/null
   echo "baseline: $(grep -o '20[0-9-]*T[0-9:.]*Z' "$D/baseline-influx.csv")"
   echo "post:     $(grep -o '20[0-9-]*T[0-9:.]*Z' "$D/post-influx.csv")"   # MUST be later; empty = FAIL
   ```
   **An empty result is a FAIL** (no `uap_radios` write for 2 h), not a tooling
   hiccup. This is the second, independent output of the same poll, so it
   separates "Prometheus scrape broke" from "the poller stopped polling".
7. **CONTROLS — the instruments the gates above read:**
   - CONTROL: metric up — `up{job="unpoller"}` must be exactly 1 (§4.4).
   - CONTROL: metric unpoller_site_adopted — count equals the same-session baseline (§4.4).
   - CONTROL: metric unpoller_device_uptime_seconds — count equals the same-session baseline (§4.4).
   - CONTROL: metric unpoller_prometheus_cache_age_seconds — present and >= 0 and < 150 on two samples; -1 = never refreshed = FAIL (§4.5).
   - CONTROL: metric unpoller_prometheus_refresh_failures_total — 10m increase exactly 0 (§4.5).
   - CONTROL: metric unpoller_controller_uptime_seconds — > 0 is the new-binary proof; 0/absent is recorded, not reverted (§4.3).
   - CONTROL: alertname UnifiMetricsAbsent — not firing 15 min after Ready (§4.8).
   - CONTROL: alertname UnifiClientMetricsAbsent — not firing 15 min after Ready (§4.8).
   - CONTROL: alertname UnifiControllerUnreachable — not firing 15 min after Ready (§4.8).
8. **INFORMATIONAL (absence checks; the positive gates are §4.1–§4.6):** the
   three alerts above are not firing 15 min after Ready; `count({__name__=~"unpoller_(lte|sensor|protect|device_mbb).*"})`
   is still `[]` (a non-empty result means §1.3's inertness premise was wrong
   about our hardware/config — not harmful, but re-assess `capability_change`
   and record it); the in-repo Grafana UniFi dashboards render data past the
   rollout time.

## 5) Rollback

Revert the §3.3 commit — it restores `image.tag: v5.2.8` (or whatever v5.2.x
the premise found) and removes the comment:
```bash
git revert --no-edit <sha>
git log -1 --format=%s          # confirm it is YOUR revert subject
git push origin main
kubectl -n monitoring rollout status deploy/unpoller --timeout=10m
```
Then re-run §4.0, and confirm §4.1 shows imageID `sha256:ca82e584…` (the exact
digest that ran with 0 restarts from 2026-09-27T08:22:58Z), §4.2 shows
`UniFi Poller v5.2.8 Starting Up!`, and §4.4–§4.6 pass again. §4.3 inverts:
`unpoller_controller_uptime_seconds` returns to `0` with the site-name
`hostname` — the expected rollback state, not a new failure.

**Nothing is forward-only**, so `git-revert` is honest: no PVC, no migration,
no InfluxDB schema change in this hop (the only new InfluxDB measurement,
`uap_lte`, is never written here — §1.3). The one thing a revert leaves behind
is ≤ the retention window of real-valued `unpoller_controller_*` samples under
the new `hostname` label; they are ordinary stale series that age out, nothing
reads them, nothing needs cleaning. If Helm is ever wedged `pending-upgrade`
(not expected for a tag-only change):
`helm rollback unpoller <last-deployed-rev> -n monitoring --wait=false`, then
`flux reconcile helmrelease unpoller -n monitoring --force`
(application-update.md §11). Clear the update marker and delete the scratch dir
(token) either way.

## 6) Interference notes

- **Blast radius if wrong:** UniFi observability only — `unpoller_*` series stop,
  the ten `unifi.*` rules go blind (the two `absent()` guards fire after 15 m,
  the intended loud failure), InfluxDB UniFi measurements freeze. No workload,
  gateway, storage or auth path depends on unpoller.
- **Expected, not a failure:** the 16 labelled `unpoller_controller_*` series
  change identity once (real `hostname`) and start reading real values (§1.4b).
  No rule or dashboard in the repo selects them.
- **Off-cluster surface: the UniFi controller login API** (rate-limited; see
  `docs/sops/unifi-controller-rate-limit.md`). The RollingUpdate briefly runs two
  pollers, i.e. one extra login at the 2 m cadence — far under the 429 threshold.
  The new JSON-marshalled login body (§1.4a) is semantically identical for our
  credential. **Do not "fix" the overlap by enabling the chart PodMonitor.**
- **Pre-existing noise, not this plan's scope:** periodic
  `Re-authenticating to UniFi Controller …` and occasional
  `failed to fetch clients for DHCP lease association … 500` lines from the
  UDM's flaky Network app (both present on the v5.2.8 pod 2026-09-30). Only a
  sustained poll failure (§4.5) is a regression.
- **Why each `conflicts_with` entry:**
  `flux-oci-chart-sources` (owns unpoller's chart-source move, §1.1);
  `helm-drift-detection` (edits `helmrelease/unpoller` itself);
  `flux-fleet-0.60.0` (restarts the reconcilers this rollout depends on);
  `coredns-1.48.2` (CoreDNS roll vs §4.6's DNS-named InfluxDB write path; it
  replaces the superseded `coredns-1.48.1` and the now blackbox-only
  `chart-patches-coredns-reloader-blackbox`, which this plan has no reason to
  serialize with — no §4 gate reads a blackbox probe);
  `kube-prometheus-stack-91.9.0` (restarts the Prometheus every §4 gate reads).
  `flux-reconciler-impersonation` is `exclusive: true` and excludes everything
  on its own. `flux-distribution-2.9.6` (upgrades the Flux controllers, same
  reason as flux-fleet). `otel-operator-0.23.0` (draft, unwindowed since its
  0.24.0 retarget; `shared: [monitoring]`)
  restarts neither Prometheus nor anything on unpoller's scrape path — sharing a
  window is acceptable, but do not interleave their verifications.
- **Chart-leg follow-up for whoever runs `flux-oci-chart-sources` stage 8:** the
  OCI charts are template-identical to 2.4.0 (§1.1), so moving to OCI 2.8.0 is a
  labels-only render delta (+1 pod roll) — BUT their appVersions (v5.2.3, and a
  non-monotonic v5.3.0 on 2.5.0/2.6.0) are all below the pinned tag, so the
  `image.tag` override must survive that move too. Dropping it in the same
  commit would silently downgrade the exporter.
- **Deny rule:** untouched. After this plan the pin is v5.5.0 and no chart ships
  an appVersion ≥ it, so the rule's removal precondition is still unmet (§1.5
  records the reason-text correction already applied).
