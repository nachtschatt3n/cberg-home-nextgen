---
plan_id: unpoller-v5.2.7
component: unpoller
pr: null                              # no open Renovate PR. Re-verified 2026-09-20 via the
                                      # version finding F-23119c27, whose action reads
                                      # "held by auto-update-policy (*unpoller*) — PLAN lane".
                                      # Like v5.2.5/v5.2.6 this reaches the PLAN lane through
                                      # coverage.py's no-PR direct-bump path, blocked by the
                                      # `*unpoller*` deny rule — see §1.5
kind: image
current: "v5.2.5"                     # STILL v5.2.5 — live on deployment/unpoller, re-verified
                                      # 2026-09-20 05:37Z. The v5.2.6 bump was planned but never
                                      # shipped, so this plan's hop WIDENS to v5.2.5 -> v5.2.7
                                      # and carries BOTH upstream deltas (§1.2). imageID on the
                                      # running pod is sha256:123a42e6… = the v5.2.5 index digest.
target: "v5.2.7"                      # released 2026-09-18T11:16:58Z, isPrerelease=false,
                                      # isDraft=false, newest v5 release (§2.4). ghcr manifest
                                      # HEAD 200, index digest sha256:99f452d3… (measured 2026-09-20)
update_type: patch
risk: low                             # Across the FULL v5.2.5 -> v5.2.7 hop: 6 commits, 4 files.
                                      # Two are a dependabot go.mod/go.sum group, one is a
                                      # distroless base bump (MEASURED, §1.3), and one is a
                                      # single Go function in pkg/otelunifi — a package that is
                                      # UNREACHABLE in this deployment because no [otel] config
                                      # block exists (§1.4, and asserted as a premise). No metric
                                      # rename, no InfluxDB schema change, no config-contract
                                      # change. This is the same risk tier the v5.2.6 draft
                                      # carried, re-derived against the wider hop rather than
                                      # inherited.
est_duration_min: 15                  # commit+push ~2, reconcile+rollout ~3, settle >=5 for
                                      # the contents assertions (60s scrape, 2m cache refresh,
                                      # and the 5m lookback that retires stale twins — §4.5)
needs_reboot: false
touches:
  namespaces: [monitoring]
  resources:
    - helmrelease/unpoller
    - deployment/unpoller
    - "ghcr.io/unpoller/unpoller"
  shared: []                          # DELIBERATE, and narrower than it looks. unpoller is a
                                      # LEAF exporter: nothing in the cluster reads from it,
                                      # it restarts nothing shared, and it keeps writing to
                                      # the shared influxdb2 in `databases` with an unchanged
                                      # schema (§1.2). Declaring shared:[monitoring] here
                                      # would manufacture an interference warning against
                                      # every monitoring plan for a workload that perturbs
                                      # none of them. The one real coupling is the OPPOSITE
                                      # direction — §4 READS Prometheus — and that is
                                      # expressed in conflicts_with, which is the only field
                                      # the scheduler honours. The off-cluster surface it does
                                      # touch (the UniFi controller API) is named in §6.
depends_on: []
conflicts_with:                       # HARD slot exclusions. window-scheduler.py keys on this
                                      # field and honours it SYMMETRICALLY (lines 253-266:
                                      # `conflicts & here` OR `names_me`), so an entry here is
                                      # sufficient on its own — the other plan does not need
                                      # to name this one back. That asymmetry is load-bearing
                                      # RIGHT NOW: cilium-1.20.2 and prometheus-crd-ownership
                                      # name no unpoller plan (each dropped its
                                      # `unpoller-v5.2.5` ref when that plan retired and no
                                      # successor was added). The ONE inbound ref that exists —
                                      # kube-prometheus-stack-91.4.1 -> `unpoller-v5.2.7` — was
                                      # REPOINTED by its own owner and now RESOLVES: re-measured
                                      # 2026-09-20 06:2xZ, `grep -rn 'unpoller-v5\.2\.[0-9]'`
                                      # over plans/ shows that entry naming v5.2.7 (its file,
                                      # line 100) and `maintenance-plan.py --validate` exits 0
                                      # with "all plan frontmatter invariants hold". The earlier
                                      # `unpoller-v5.2.6` dangle is GONE — do not re-report it.
                                      # Consequence for close-out: that ref is now LIVE, so
                                      # deleting this file orphans it (§3.5).
                                      # Re-checked against `maintenance-plan.py --open` and
                                      # every sibling plan's frontmatter on 2026-09-20.
  - kube-prometheus-stack-91.4.1      # MANDATORY. §4.5, §4.6 and §4.8 read THIS Prometheus over
                                      # a >=5-min settle; that plan restarts Prometheus AND
                                      # Alertmanager (2-5 min blind spot) and a replaying
                                      # Prometheus answers "no data", which reads as an unpoller
                                      # regression and would trigger a needless §5 revert. That
                                      # plan's own §6 says it outright: "Any future unpoller plan
                                      # must re-add the exclusion for the same reason".
                                      # REF RETARGETED 2026-09-20: this entry named
                                      # `kube-prometheus-stack-91.4.0` until that plan was itself
                                      # re-targeted to 91.4.1 in the same worktree, in parallel
                                      # with this one. 91.4.1 is a CHART-ONLY bump (same
                                      # appVersion v0.94.0), so the reason above is unchanged —
                                      # only the id moved. Status re-read 2026-09-20 AFTER its
                                      # retarget: draft, window null (it was `vetted` before) —
                                      # so the two CAN still be co-slotted without this line.
  # RESOLVED 2026-09-20: prometheus-crd-ownership EXECUTED (1a551276) and retired (9d87171b) — there is no longer a plan to collide with, so this guard protected nothing. Removed per the dead-ref convention (F-6acb231c).
                                      # servicemonitors.monitoring.coreos.com — the CRD that
                                      # defines the object carrying this plan's only scrape
                                      # path. Its §4.2 asserts generation/resourceVersion are
                                      # UNCHANGED, so the expected perturbation is zero; the
                                      # exclusion is for the failure case, where a momentary
                                      # CRD race stops the unpoller scrape and this plan's
                                      # verification misattributes it to the image bump.
                                      # CHANGED SINCE THE v5.2.6 DRAFT: it is no longer
                                      # window-null — re-read 2026-09-20 it is status
                                      # awaiting-go, window "sat-attended:2026-09-26". So this
                                      # exclusion now actively removes a real date from this
                                      # plan's candidate slots (§6).
  - cilium-1.20.2                     # A CNI roll restarts pod networking cluster-wide; every
                                      # assertion in §4 (scrape, cache refresh, InfluxDB write
                                      # path) rides that network. cilium-1.20.2 declares a SOLO
                                      # SLOT (12 exclusions — COUNTED 2026-09-20 from its own
                                      # conflicts_with block, not estimated) and explicitly
                                      # dropped its unpoller-v5.2.5 ref on 2026-09-16; this is
                                      # the successor it would re-add.
security_ref: null                    # version-currency driver only; no vulnerability content.
                                      # The TLS-posture reference in §1.3 is an ALREADY-ACCEPTED
                                      # risk (F-cafe8865 / AR-114), cited as a premise of the
                                      # base-image analysis, not a driver for this plan.
capability_change: false              # dependency refresh + base-image rebuild + a fix inside a
                                      # DISABLED output plugin. No new opt-in, no config key, no
                                      # user-visible behaviour change. The rendered manifest
                                      # delta is ONE image tag.
rollback_class: git-revert
finding_refs: [F-0e3c2de5, F-23119c27]
                                      # F-0e3c2de5 (section plan) OWNS this retarget: "unpoller
                                      # v5.2.6 published 2026-09-16 00:40Z, 3 h before the
                                      # nightly window: the vetted plan targets v5.2.5, so the
                                      # window executed v5.2.5 as reviewed and left v5.2.6 for
                                      # the next cycle". This plan is that next cycle — carried
                                      # one release further, because v5.2.7 landed before the
                                      # cycle ran. Its TEXT is now stale in two ways (§1.6);
                                      # this plan does not edit the finding.
                                      # F-23119c27 (section version) now names THIS EXACT HOP:
                                      # re-read 2026-09-20 its title is "unpoller: image
                                      # ghcr.io/unpoller/unpoller v5.2.5 → v5.2.7 (patch)",
                                      # status unchanged, last seen 2026-09-19. The v5.2.6 draft
                                      # said this row was "the v5.2.4 → v5.2.5 finding, already
                                      # satisfied, auto-closes next sweep" — it did NOT close;
                                      # it re-targeted itself to the live pin vs newest upstream
                                      # (§1.6). It is producer=script, so it DOES auto-close once
                                      # the pin moves; it is listed because it is the version-lane
                                      # row this plan answers, not because it needs manual closing.
status: draft
window: null
premises:
  - id: live-image-still-v5.2.5
    why: >-
      `current:` claims v5.2.5 (shipped 2026-09-16 by plan unpoller-v5.2.5,
      commit b0ffb944) and the v5.2.6 bump never shipped. If the cluster has
      since moved — e.g. the operator narrowed the `*unpoller*` deny rule to
      `max: patch` (§1.5) and Step 0's direct-bump lane landed a newer tag on
      its own — this plan is a no-op: verify per §4 and retire it, do not
      execute.
    run: kubectl get deploy -n monitoring unpoller -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: ghcr.io/unpoller/unpoller:v5.2.5
  - id: git-pin-still-v5.2.5
    why: >-
      Same premise, git side. The rollout is one line in helmrelease.yaml; if
      main already carries a newer tag the §3.2 edit produces an empty diff and
      the §5 revert target is wrong.
    run: "git show HEAD:kubernetes/apps/monitoring/unpoller/app/helmrelease.yaml | grep -c 'tag: v5.2.5'"
    expect_exact: "1"
  - id: chart-still-2.4.0
    why: >-
      The entire "image-only is safe" argument (§1.1) is that chart 2.4.0 is a
      version-agnostic wrapper already vetted three times. A different chart
      version means different templates and this plan's analysis is void — and
      per F-a2cd7a11 the chart leg moves in a SEPARATE lane, so it can change
      under this plan without touching the image.
    run: kubectl get helmrelease -n monitoring unpoller -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: "2.4.0"
  - id: helmrelease-ready
    why: "Do not stack a bump on top of an already-failing release."
    run: kubectl get helmrelease -n monitoring unpoller -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: chart-service-still-disabled
    why: >-
      `service.enabled: false` is what keeps chart 2.4.0's own Service (port
      named `tcp`) from displacing our hand-written one (port named `http`,
      which the ServiceMonitor selects). Both render as `unpoller` in
      `monitoring`. If someone flipped it, every unpoller_* series would
      ALREADY be gone under a green HelmRelease and §2.6's baselines would be
      meaningless. See docs/sops/unifi-controller-rate-limit.md §1.
    run: kubectl get helmrelease -n monitoring unpoller -o jsonpath='{.spec.values.service.enabled}'
    expect_exact: "false"
  - id: chart-podmonitor-still-disabled
    why: >-
      A second scrape (the chart's PodMonitor at 30s) would double UniFi
      controller API load — re-triggering the 429 storm the 2m interval exists
      to prevent — and duplicate every series, corrupting the count-based
      contents assertions in §4.4.
    run: kubectl get helmrelease -n monitoring unpoller -o jsonpath='{.spec.values.podMonitor.enabled}'
    expect_exact: "false"
  - id: handwritten-service-owns-port-http
    why: >-
      The ServiceMonitor scrapes `port: http`. If the Service's first port is
      no longer named `http`, the scrape is already broken and §4 cannot
      attribute anything to this bump.
    run: kubectl get svc -n monitoring unpoller -o jsonpath='{.spec.ports[0].name}'
    expect_exact: http
  - id: servicemonitor-scrapes-port-http
    why: "The other half of the same wiring: the ServiceMonitor must still select the `http` port."
    run: kubectl get servicemonitor -n monitoring unpoller -o jsonpath='{.spec.endpoints[0].port}'
    expect_exact: http
  - id: pod-running
    why: "A baseline can only be taken from a running exporter."
    run: kubectl get pods -n monitoring -l app.kubernetes.io/name=unpoller -o jsonpath='{.items[0].status.phase}'
    expect_exact: Running
  - id: no-otel-env-on-workload
    why: >-
      NEW FOR THIS TARGET, and it guards the whole risk argument. v5.2.7's only
      code change is one function in pkg/otelunifi (§1.4). Upstream gates that
      package behind Enabled(), which is false when no [otel] block is
      configured — so the changed code is unreachable here. unpoller's config
      library also accepts env overrides, so "no [otel] in the file" is only
      half the proof; this asserts the workload carries NO env at all, closing
      the second path. If env ever appears, re-run §1.4 before executing.
    run: kubectl get deploy -n monitoring unpoller -o jsonpath='{.spec.template.spec.containers[0].env[*].name}' | wc -c | tr -d ' '
    expect_exact: "0"
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/unifi-controller-rate-limit.md
  - docs/sops/monitoring.md
  - docs/sops/auto-update.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-09-20"
---

# unpoller: image v5.2.5 → v5.2.7 (image-only patch, chart stays 2.4.0)

> **Retargeted 2026-09-20** from the `unpoller-v5.2.6` draft (generated
> 2026-09-17, never executed). v5.2.7 shipped 2026-09-18 while that draft sat in
> the queue, so the hop widens to **v5.2.5 → v5.2.7** and now carries TWO
> upstream deltas. Every live measurement in this file was **re-taken on
> 2026-09-20**; where an older datapoint is still worth showing it is labelled
> with its own date and kept as the older reading rather than rewritten.

## 1) Summary & why held

### 1.1 What changes

**One line**: `image.tag: v5.2.5 → v5.2.7` in
`kubernetes/apps/monitoring/unpoller/app/helmrelease.yaml`.

**Which leg moves — state it explicitly (F-a2cd7a11).** unpoller's chart and
image move in two independent lanes, so a chart bump can land days apart from an
image bump and split the pair. **This plan moves the IMAGE leg ONLY.** The chart
stays `2.4.0`, the `HelmRepository` stays on HTTP, and no chart value changes.
Live today and after this plan: chart `2.4.0` + image `v5.2.7`. The chart leg is
deliberately parked — `flux-oci-chart-sources` §3.5 blocks unpoller's OCI
migration precisely because it would force a chart upgrade in the same commit.
No `upConfig` (secret) edit. No policy edit.

**The current version did NOT move while this plan was re-targeted.**
`deployment/unpoller` still runs `ghcr.io/unpoller/unpoller:v5.2.5`, re-verified
2026-09-20 05:37Z, with `imageID sha256:123a42e6…` — the exact v5.2.5 index
digest — 0 restarts, and a start time of 2026-09-16T01:48:49Z. So `current:`
stays `v5.2.5`; this is a **wider hop, not a later one**.

### 1.2 Upstream evidence — TWO deltas, both measured

`gh api repos/unpoller/unpoller/compare/v5.2.5...v5.2.7`, measured **2026-09-20**:
`status: ahead`, **6 commits, 4 files**.

| File | Delta (v5.2.5…v5.2.7) | Which hop | Effect on us |
|---|---|---|---|
| `Dockerfile` | `+1/-1` | v5.2.5→v5.2.6 | distroless base `static-debian11` → `static-debian13`. Assessed in §1.3. |
| `go.mod` | `+6/-6` | v5.2.5→v5.2.6 | dependabot "all" group, 4 updates; no functional surface. |
| `go.sum` | `+12/-12` | v5.2.5→v5.2.6 | checksums for the above. |
| `pkg/otelunifi/report.go` | `+3/-14` | v5.2.6→v5.2.7 | **the only Go source change in the whole hop.** Assessed in §1.4. |

**The second hop in isolation** (`compare/v5.2.6...v5.2.7`, measured 2026-09-20):
`status: ahead`, **2 commits, 1 file** — exactly the two the orchestrator
reported: `160b46d` *"fix(otelunifi): callback memory leak"* and `4123a13`, the
merge of PR #1092. Nothing else moved.

**NONE of the review-sensitive paths changed**, re-verified against the file list
of the combined compare: `pkg/influxunifi/` (InfluxDB tag/field schema),
`pkg/promunifi/` (Prometheus metric names, the scrape-cache config contract) and
`examples/up.conf.example` (the config contract).

Consequences, each of which the v5.2.5 review established and neither delta can
have moved:

- **No metric rename.** The in-repo `prometheusrule.yaml` keeps matching.
  Re-measured 2026-09-20 (reproduce with
  `grep -c '^[[:space:]]*- alert:' …/prometheusrule.yaml` and
  `grep -o 'unpoller_[a-z_]*' …/prometheusrule.yaml | sort -u`): **10 alert
  rules over 7 distinct `unpoller_*` series names**, two of them `absent()`
  guards (`absent(unpoller_device_uptime_seconds)` line 30 and
  `absent(unpoller_client_satisfaction_ratio)` line 52). *(An earlier draft of
  this bullet also quoted "14 selector occurrences"; that figure was not
  reproducible — the same file counts 19 raw token hits, 18 matching lines, or
  13 on non-comment lines depending on how you count, and several hits are
  prose inside comments. The number was load-bearing for nothing, so it is
  dropped rather than restated.)* All five in-repo dashboards are
  Prometheus-datasource — re-measured 2026-09-20: **118 `"type": "prometheus"`,
  zero `"influxdb"`** across `app/dashboards/*.yaml` (identical to the
  2026-09-17 reading).
- **No InfluxDB schema change.** Re-measured 2026-09-20, bucket `default` holds
  **20 measurements** (`uap`, `uap_radios`, `uap_vaps`, `usw`, `usw_ports`,
  `usg`, `usg_networks`, `usg_wan_ports`, `clients`, `clientdpi`, `wan`,
  `wan_status`, `speedtest`, `subsystems`, `firewall_policy`, `topology_edge`,
  `topology_summary`, `vpn_mesh`, `vpn_mesh_connection`, `vpn_mesh_status`).
  Their tag/field names are untouched by both deltas, so the Grafana
  `unpoller-influxdb` datasource and any operator-built InfluxDB panels need no
  repointing. *(Older datapoint, kept: the 2026-09-17 authoring note recorded
  **21** measurements. The current re-measured figure is 20. Nothing in this
  plan depends on the exact count — it is cited only as "the schema did not
  move" — and §4.6 asserts the write path by timestamp, not by cardinality.)*
- **No config-contract change.** The one key whose type changed in v5.2.5
  (`[prometheus] interval`, where an explicit `0` now disables the scrape cache)
  is untouched by both deltas, and our config sets `"2m"` explicitly — asserted
  in §2.5 and re-verified 2026-09-20 (2 occurrences of `interval = "2m"`, zero
  of `interval = 0`).

### 1.3 The distroless base change — carried over from the first hop, MEASURED

The base move is **still in scope**: it belongs to v5.2.5→v5.2.6, and since the
live image never left v5.2.5, executing this plan crosses it. `Dockerfile` is
**unchanged** between v5.2.6 and v5.2.7 (the compare above lists one file, and it
is not the Dockerfile), re-confirmed 2026-09-20 by reading the file at both tags
directly:

```
v5.2.5:  FROM gcr.io/distroless/static-debian11
v5.2.7:  FROM gcr.io/distroless/static-debian13
```

So the jump is **two Debian majors**, upstream's stated reason being that Debian
11 (bullseye) reached end of life and no longer receives security updates.

**Why a distroless major matters at all:** `gcr.io/distroless/static-*` ships the
CA trust store, and a base swap replaces the `ca-certificates` package — newer
bundles *remove* distrusted and expired roots. On a component that talks TLS to
the UniFi controller, a silently-emptied or silently-changed trust store is a
real failure mode, and it would present as "green pod, no metrics".

**Measurement 1 (2026-09-17, older datapoint, still valid — the two bases have
not changed since):** listing the tar entries of every layer of
`gcr.io/distroless/static-debian11` and `static-debian13` (linux/amd64) returns
`etc/ssl/certs/ca-certificates.crt` in **each**. The bundle is not lost by the
move; only its contents are newer.

**Measurement 2 (re-verified 2026-09-20): no code path in our deployment
consults that trust store.** The config has exactly three sections — `[unifi]`,
`[prometheus]`, `[influxdb]` (counted 2026-09-20) — and exactly one `https://`
URL: the controller. InfluxDB is plaintext `http` to an in-cluster Service
(`influxdb-influxdb2.databases`, port 80). The controller client runs with TLS
verification **disabled** — a long-standing operator-accepted posture recorded on
**F-cafe8865 (AR-114)** and already published in
`docs/sops/unifi-controller-rate-limit.md` §3 — which the live v5.2.5 pod prints
at startup: `=> URL: https://<controller> (verify SSL: false, timeout: 1m0s)`.
A client that does not validate never reads the bundle; a plaintext client never
opens TLS. **Both TLS-relevant paths are therefore insensitive to the CA-bundle
contents by construction**, which is what makes this base major low-risk HERE and
would NOT make it low-risk on a component that verifies.

**Measurement 3 — RE-TAKEN 2026-09-20 against the NEW target.** The old draft
compared v5.2.5 against v5.2.6; this table compares the amd64 image configs
pulled from ghcr for **v5.2.5 and v5.2.7**:

| | v5.2.5 | v5.2.7 |
|---|---|---|
| `User` | `'0'` | `'0'` |
| `Entrypoint` | `/usr/bin/unpoller` | `/usr/bin/unpoller` |
| `SSL_CERT_FILE` | `/etc/ssl/certs/ca-certificates.crt` | `/etc/ssl/certs/ca-certificates.crt` |
| `Cmd` / `ExposedPorts` | none / none | none / none |
| layers | 13 | 15 |
| created | 2026-09-12T22:55:31Z | 2026-09-18T11:16:17Z |
| amd64 child digest | `sha256:b48f300f…` | `sha256:8aebeff1…` |

The `User` row is the one that could have bitten: our HelmRelease deliberately
does NOT set `runAsNonRoot`/`runAsUser` (the comment in `helmrelease.yaml`
explains why — the declared USER could not be read at hardening time), and it
DOES set `readOnlyRootFilesystem: true`. A base that changed the declared uid
could have produced `CreateContainerConfigError` or a container unable to read
its own config. It did not change. *(Older datapoint, kept: the same table taken
2026-09-17 against v5.2.6 read 15 layers, created 2026-09-16T00:40:12Z, same
User/Entrypoint/SSL_CERT_FILE. v5.2.7 matches it on every row but `created` —
consistent with a rebuild of the same base.)*

**Residual risk after those three:** the recompiled binary carries new
dependency versions, and the base carries a new libc-free layer set. Neither is
provable from metadata — which is exactly what §4 measures at runtime, on the
running pod, rather than asserting here.

### 1.4 The OTel callback fix — the one element the v5.2.6 draft never saw

This is the **only novel risk surface** introduced by moving the target from
v5.2.6 to v5.2.7, and it is the first Go source change in either hop, so it gets
the same treatment §1.3 gave the base bump: measured, not waved through.

The upstream diff (`pkg/otelunifi/report.go`, `+3/-14`) replaces an
observable-gauge-plus-callback registration with a direct synchronous record:

```go
-	g, err := meter.Float64ObservableGauge(name, metric.WithDescription(description))
+	g, err := meter.Float64Gauge(name, metric.WithDescription(description))
...
-	_, err = meter.RegisterCallback(func(_ context.Context, o metric.Observer) error {
-		o.ObserveFloat64(g, value, metric.WithAttributeSet(attrs))
-		return nil
-	}, g)
-	if err != nil { ... }
+	g.Record(ctx, value, metric.WithAttributeSet(attrs))
```

That is a real fix for a real leak: the old code registered a **new callback per
gauge per report cycle** and never unregistered, so callbacks accumulated for the
life of the process.

**It is unreachable in this deployment, and that is the whole argument.**
Upstream gates the entire plugin, read from `pkg/otelunifi/otelunifi.go` at tag
v5.2.7:

```go
func (u *OtelOutput) Enabled() bool {
	if u == nil { return false }
	if u.Config == nil { return false }
	return u.Enable
}

func (u *OtelOutput) Run(c poller.Collect) error {
	u.Collector = c
	if !u.Enabled() {
		u.LogDebugf("OTel output not enabled, skipping.")
		return nil
	}
	u.Logf("OpenTelemetry (OTel) output plugin enabled")
	...
}
```

`recordGauge` — the changed function — is only ever reached from the report path
that `Run()` starts. `Run()` returns before that when `Enabled()` is false, and
`Enabled()` is false when the `[otel]` config block is absent (`u.Config == nil`)
or `enable` is unset.

**Two independent measurements, both taken 2026-09-20, that close it:**

1. **No `[otel]` block in the config.** The decrypted secret contains exactly
   three section headers — `[unifi]`, `[prometheus]`, `[influxdb]` — and
   **zero** case-insensitive occurrences of `otel` or `opentelemetry`.
   (Counts only; the config itself is never printed — §2.5.)
2. **No env override path.** unpoller's config library also accepts env
   overrides, so the file alone is only half the proof. The rendered
   `deployment/unpoller` carries **no `env` entries at all** (zero names), so
   nothing can switch the plugin on out-of-band. This is asserted mechanically
   as the premise `no-otel-env-on-workload`.

**Verdict:** for us the v5.2.6→v5.2.7 delta changes bytes in the binary and
nothing in behaviour. §4.4 asserts the plugin is still silent on the new pod, so
the claim is checked at runtime rather than trusted. **If an `[otel]` block is
ever added to the config, this section must be re-run before executing** — the
premise fails loudly in that case rather than letting the plan proceed on a
stale argument.

### 1.5 Why it was held — and the honest verdict

The `*unpoller*` deny rule in `runbooks/auto-update-policy.yaml` carries **no
`max:` key** (re-read 2026-09-20, still unchanged), and `coverage.py::deny_rule_for`
blocks EVERY update_type for a rule without one (`mx is None → block`). So the
patch was blocked mechanically.

But the rule's *reason* is entirely about **chart** bumps: the pinned `image.tag`
outranks `appVersion`, so a chart bump would score as a safe minor and land
unattended while templating for v3. **An image-only patch under the same chart
2.4.0 does not engage that reason at all** — the chart is untouched, the pin
still outranks appVersion exactly as before, and the three overrides that make
image-only safe (`service.enabled: false`, `podMonitor.enabled: false`,
`dashboards.create: false`) are unchanged and are asserted as premises above.

**This hold is a false positive of a glob wider than its own justification** —
the same verdict the reviewed v5.2.5 plan reached, and the v5.2.6 draft after it.
`risk: low`. The plan is written anyway because the human / window agent decides,
not the planner.

**Deny-rule note for the operator (NOT edited by this plan).** The narrowing
recommendation is no longer just a note in a dispatch report — it is a filed,
open finding: **F-84472f89**, *"The \*unpoller\* deny rule blocks image patches on
a reason that argues only about CHART risk, and its premise names v5.2.4 while
the live pin is v5.2.5 — two releases stale, no max: key, so two consecutive
patches each needed a full window plan"*. Its action text already carries the
concrete remedy (add `max: patch`, then rewrite the reason so it stops naming a
specific pinned tag). Re-read 2026-09-20 the rule is still byte-identical and
still names `v5.2.4` — now **three** releases stale, and this plan is the *third*
consecutive patch to need a window. Nothing here edits the policy; that is the
operator's separate, code-reviewed decision.

**If the rule is narrowed before this plan runs**, Step 0's direct-bump lane will
ship v5.2.7 on its own, premises `live-image-still-v5.2.5` / `git-pin-still-v5.2.5`
will FAIL, and the right action is to run §4 against the already-landed bump and
retire this file — not to execute it.

### 1.6 Two stale finding texts — reported, not edited

Recorded here because the next reader will otherwise trust them:

1. **F-0e3c2de5** (this plan's owning finding) says *"the vetted plan targets
   v5.2.5"* and frames the work as *"treat v5.2.5 → v5.2.6 as a normal
   follow-up"*. Both were true on 2026-09-16 and neither is true now: the plan
   targets **v5.2.7**, and v5.2.6 has been superseded upstream without ever being
   deployed. Its `security_detail` also carries a correction appended 2026-09-17
   fixing its own base-image claim from `debian12 → debian13` to
   `debian11 → debian13` (which this plan re-verified independently, §1.3).
2. **F-23119c27** was described by the v5.2.6 draft as the v5.2.4→v5.2.5 version
   finding, *"already satisfied by b0ffb944 … auto-closes on the next sweep"*.
   It did not close. It is a script-produced row keyed on *live pin vs newest
   upstream*, so it re-targeted itself: as of 2026-09-19 its title reads
   **"unpoller: image ghcr.io/unpoller/unpoller v5.2.5 → v5.2.7 (patch)"**,
   status `unchanged`. It is now the version-lane row for exactly this hop, which
   is why `finding_refs` lists it.

Per the planner contract neither finding is edited by this plan.

### 1.7 Derived execution class

`capability_change: false`, `rollback_class: git-revert`, `needs_reboot: false`,
`shared: []`, `risk: low` → satisfies `auto-night` in
`runbooks/autonomy-policy.yaml` (`require` all three, `forbid_shared:
[storage, longhorn]`, `forbid_risk: [high]`). Confirm with
`.venv/bin/python3 runbooks/maintenance-plan.py --open`; the plan does not claim
a class.

## 2) Pre-checks

1. **Premises pass mechanically** (the gate refuses the plan otherwise):
   ```bash
   .venv/bin/python3 runbooks/plan-premises.py unpoller-v5.2.7 --require-premises
   ```
2. Baseline health — HR Ready, pod Running with 0 restarts, no failing
   kustomizations anywhere:
   ```bash
   flux get helmrelease unpoller -n monitoring
   kubectl -n monitoring get pods -l app.kubernetes.io/name=unpoller
   flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
   ```
3. **Target and rollback tags both published** (application-update.md Step 0).
   Record the digests — §4.1 compares against them:
   ```bash
   TOKEN=$(curl -s "https://ghcr.io/token?scope=repository:unpoller/unpoller:pull&service=ghcr.io" | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
   for t in v5.2.5 v5.2.7; do echo "== $t"; curl -sI -H "Authorization: Bearer $TOKEN" \
     -H "Accept: application/vnd.oci.image.index.v1+json" \
     "https://ghcr.io/v2/unpoller/unpoller/manifests/$t" | grep -iE '^HTTP|docker-content-digest'; done
   ```
   **Measured 2026-09-20 (re-taken for the new target, not carried over):**
   | tag | HTTP | index digest | amd64 child |
   |---|---|---|---|
   | `v5.2.5` (rollback) | 200 | `sha256:123a42e6…` | `sha256:b48f300f…` |
   | `v5.2.7` (target) | 200 | `sha256:99f452d3…` | `sha256:8aebeff1…` |

   The v5.2.5 index digest matches the `imageID` on the LIVE pod — so the
   rollback target in §5 is the exact artifact that has been serving since
   2026-09-16T01:48:49Z.
   *(Older datapoint, kept for lineage: on 2026-09-17 the then-target v5.2.6
   resolved 200 at index digest `sha256:b6912acc…`. v5.2.6 is **not** this
   plan's target and that digest is not used by any step below.)*
4. **Re-resolve the target** — a plan is a snapshot and unpoller ships fast
   (v5.2.0 → v5.2.7 in 18 days; this plan exists *because* the previous draft was
   overtaken twice). Measured 2026-09-20, the newest v5 release is **v5.2.7**
   (`isPrerelease=false`, `isDraft=false`, published 2026-09-18T11:16:58Z) with
   nothing above it. Re-run at execution:
   ```bash
   curl -s "https://api.github.com/repos/unpoller/unpoller/releases?per_page=10" \
     | python3 -c "import sys,json;[print(r['tag_name'],r['published_at'][:10],'pre=%s'%r['prerelease'],'draft=%s'%r['draft']) for r in json.load(sys.stdin) if r['tag_name'].startswith('v5.')]"
   # for any newer NON-prerelease, non-draft tag N:
   curl -s "https://api.github.com/repos/unpoller/unpoller/compare/v5.2.7...N" \
     | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['status'],d['total_commits']);[print(f['status'],f['filename']) for f in d['files']]"
   ```
   **Do not take a tag marked `pre=True` or `draft=True`.**
   `identical` / 0 commits → a re-tagged rebuild; take N and this analysis
   carries over. Real commits → re-run the §1.2 review for the delta before
   bumping, paying attention to `pkg/influxunifi/` (schema), `pkg/promunifi/`
   (metric names, config keys) and `examples/up.conf.example` (config contract).
   **Anything touching those beyond a one-liner is a new plan, not a retarget.**
   A `Dockerfile` base change alone is a retarget, but re-run §1.3's three
   measurements against the new base before taking it; a change confined to
   `pkg/otelunifi/` is a retarget **only while §1.4's two measurements still
   hold** (no `[otel]` block, no env).
5. **The ONE config key whose contract changed in v5.2.5 is still explicit and
   positive**, the TLS posture §1.3 depends on is unchanged, and the OTel plugin
   §1.4 depends on is still unconfigured. Print counts only — never the config
   itself:
   ```bash
   S=$(mktemp); sops -d kubernetes/apps/monitoring/unpoller/app/secret.sops.yaml > "$S"
   grep -cE 'interval[[:space:]]*=[[:space:]]*"2m"' "$S"   # expect 2 (prometheus + influxdb)
   grep -cE 'interval[[:space:]]*=[[:space:]]*"?0'   "$S"  # expect 0 — nobody disabled the cache
   grep -cE 'verify_ssl[[:space:]]*=[[:space:]]*false' "$S" # expect 1 — §1.3 measurement 2 holds
   grep -c 'https://' "$S"                                  # expect 1 — the controller, and only it
   grep -ciE 'otel|opentelemetry' "$S"                      # expect 0 — §1.4 measurement 1 holds
   grep -oE '^[[:space:]]*\[[a-z_.]+\]' "$S" | tr -d ' ' | sort -u  # expect exactly [influxdb] [prometheus] [unifi]
   rm -f "$S"
   ```
   All six re-measured 2026-09-20 and matching the expectations above.
   **Note the anchors:** these patterns are deliberately `[[:space:]]`-tolerant
   and NOT anchored at column 0 — the TOML lives indented inside the Secret's
   `stringData`, and a `^\[` anchor returns a false **zero** here rather than an
   error (measured: it reported 0 sections for a config that has 3).
   If `verify_ssl` has become `true` since this plan was written, **stop**:
   §1.3's argument that the CA bundle is off the live path no longer holds, and
   the base-major bump needs a fresh assessment (a trust-store regression would
   then present as a total loss of UniFi metrics).
6. **Baselines for §4 — MEASURE THEM NOW, in this session. Do not reuse the
   numbers below.** They are this plan's authoring measurements
   (**2026-09-20 05:38Z**) and are recorded only to show the expected magnitude
   and to justify the §4.4 band:
   ```bash
   kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 >/dev/null 2>&1 & PF=$!
   sleep 3
   q(){ echo -n "$1 => "; curl -s --data-urlencode "query=$1" http://localhost:9090/api/v1/query \
        | python3 -c "import sys,json;print([r['value'][1] for r in json.load(sys.stdin)['data']['result']])"; }
   q 'up{job="unpoller"}'                                   # [1]
   q 'count(unpoller_site_adopted)'                         # [3]
   q 'count(unpoller_device_uptime_seconds)'                # [10]
   q 'count({__name__=~"unpoller_.*"})'                     # [7984]
   q 'unpoller_prometheus_cache_age_seconds'                # [29.79]
   q 'unpoller_prometheus_refresh_failures_total'           # [1]  (cumulative — see below)
   q 'increase(unpoller_prometheus_refresh_failures_total[24h])'  # [0]
   kill $PF 2>/dev/null
   kubectl -n monitoring get pod -l app.kubernetes.io/name=unpoller \
     -o jsonpath='{.items[0].status.containerStatuses[0].imageID}{"\n"}'   # §4.1 must DIFFER
   ```
   **The refresh-failure counter moved since the last draft, and it is benign —
   check it the same way rather than trusting this sentence.** It read `0` on
   2026-09-17 and reads **`1`** on 2026-09-20. It is a **cumulative counter**, so
   the number that matters is the rate: measured 2026-09-20,
   `increase(...[10m])`, `increase(...[6h])` and `increase(...[24h])` are all
   **0**, and `changes(...[3d])` is **1** — i.e. exactly one failure somewhere in
   the last three days and none in the last day. That is the known re-auth noise
   described in §6, not a regression. §4.5 therefore asserts the *rate*, never
   the absolute value.

   **Why re-measuring the series count is mandatory, with the evidence:** the
   v5.2.5 plan recorded `count({__name__=~"unpoller_.*"}) = 7953` on 2026-09-15;
   the v5.2.6 draft measured **7607** on 2026-09-17 (a 4.4% drift in two days);
   today it is **7984**. Any of those would blow a ±2% band taken against
   another day's number and fail a perfectly healthy exporter. The series
   population tracks how many wireless clients are associated, so it moves with
   the household, not with the software. Over a SHORT horizon it is tight:
   measured 2026-09-20 over the last 6 h, `min_over_time` **7883** /
   `max_over_time` **8008** (±0.8% around ~7945). That is what makes a ±2% band
   against a SAME-SESSION baseline both meaningful and passable.

   > **THE PRINTED FIGURES ARE MAGNITUDE-ONLY. NEVER USE THEM AS THE BAND.**
   > They are already stale, and demonstrably so *within the same day they were
   > written*: re-measured 2026-09-20 06:2xZ — hours after the 05:38Z authoring
   > run above — the instant count read **7883** (not 7984) and the 6 h window
   > read `min_over_time` **7883** / `max_over_time` **8019** (not 7883/8008),
   > i.e. a ±0.9% spread around ~7951. Nothing is wrong: this is the household
   > drift the bullet above describes, and it is exactly why §2.6 mandates a
   > same-session baseline and §4.5 compares only against THAT. If you find
   > yourself computing ±2% of 7984, you are using the wrong number — take your
   > own baseline first. The only figure in §4.5 that is NOT session-relative is
   > the `≥ 6000` absolute floor, which exists precisely because it cannot be
   > argued away by drift.
7. **InfluxDB write-path baseline** (cheap, and §4.6 compares against it). The
   token comes from the decrypted secret — assign it, never echo it:
   ```bash
   TOK=$(sops -d kubernetes/apps/monitoring/unpoller/app/secret.sops.yaml \
     | python3 -c "
import sys
for line in sys.stdin:
    s=line.strip()
    if s.startswith('auth_token'):
        print(s.split('=',1)[1].strip().strip('\"')); break")
   kubectl port-forward -n databases svc/influxdb-influxdb2 8086:80 >/dev/null 2>&1 & PF=$!
   sleep 3
   curl -s 'http://localhost:8086/api/v2/query?org=influxdata' \
     -H "Authorization: Token $TOK" -H 'Content-Type: application/vnd.flux' -H 'Accept: application/csv' \
     -d 'from(bucket:"default") |> range(start:-2h) |> filter(fn:(r)=>r._measurement=="uap_radios") |> keep(columns:["_time"]) |> sort(columns:["_time"],desc:true) |> limit(n:1)'
   kill $PF 2>/dev/null
   ```
   **The range is `-2h`, deliberately — do not narrow it back to `-30m`.** §4.7
   re-runs this identical query as a gate, and with a 30 min window a write path
   that has been dead for longer than 30 min returns **no rows at all** instead
   of the frozen timestamp the gate is written to detect. Dry-run 2026-09-20 on
   the live instance: a query that matches nothing returns a bare `\r` and
   nothing else — no error, no non-zero exit — which reads like a tooling
   hiccup, not a failure. `-2h` keeps a stalled write path legible as an OLD
   timestamp. Both invocations must use the SAME range or the comparison in
   §4.7 is not like-for-like.
   **Measured 2026-09-20 05:40Z: newest `uap_radios` `_time` =
   `2026-09-20T05:40:53Z`** — i.e. the write path was current to the second at
   baseline time. (org `influxdata`, bucket `default`, measurement `uap_radios`
   — all three re-verified to exist today, alongside 19 sibling measurements.)
   *(Older datapoint, kept: the 2026-09-17 authoring baseline was
   `2026-09-17T02:00:53Z`.)*
8. **No in-flight reconcile on `monitoring`, and no other plan mid-execution in
   the namespace** (§6). Check the active-update markers too — a live marker for
   another component means its window is still open:
   ```bash
   runbooks/update-marker.sh list
   ```

## 3) Steps

1. **Update marker** (cheap, recommended; no Alertmanager silence is needed at
   this tier per application-update.md Example A — the rollout is a
   RollingUpdate of a stateless 1-replica Deployment, so the scrape gap is at
   most one 60s interval while `UnifiMetricsAbsent` needs 15m to fire):
   ```bash
   runbooks/update-marker.sh add unpoller monitoring 1 "v5.2.5->v5.2.7 image patch (plan unpoller-v5.2.7)"
   ```
2. **Bump the tag** — one line in
   `kubernetes/apps/monitoring/unpoller/app/helmrelease.yaml`. **Dry-tested
   2026-09-20 on a scratch copy of the CURRENT file on macOS (BSD sed)**; the
   resulting diff is exactly:
   ```
   50c50
   <       tag: v5.2.5
   ---
   >       tag: v5.2.7
   ```
   ```bash
   sed -i '' 's/^      tag: v5\.2\.5$/      tag: v5.2.7/' kubernetes/apps/monitoring/unpoller/app/helmrelease.yaml
   grep -n 'tag: v5\.2\.' kubernetes/apps/monitoring/unpoller/app/helmrelease.yaml   # exactly one line, v5.2.7
   grep -c 'tag: v5.2.7' kubernetes/apps/monitoring/unpoller/app/helmrelease.yaml    # exactly 1
   ```
   Then add the lines below to the comment block directly above the tag, after
   the existing "2026-09-16: v5.2.4 -> v5.2.5 …" paragraph, so the next reader
   sees the lineage without git archaeology (replace `XX` with the execution day
   — the stub is a placeholder, not a value):
   ```
         # 2026-09-XX: v5.2.5 -> v5.2.7 image patch (plan unpoller-v5.2.7), skipping v5.2.6
         # which was planned but never shipped. Two deltas: dependabot go.mod/go.sum group +
         # distroless base static-debian11 -> static-debian13 (bullseye EOL) from v5.2.6, and
         # an otelunifi callback-leak fix from v5.2.7 that is inert here (no [otel] block, no
         # env, so the plugin never starts). No metric rename, no InfluxDB schema change, no
         # config-contract change. Chart still 2.4.0.
   ```
   Do NOT touch `runbooks/auto-update-policy.yaml` in this plan — the rule
   narrowing is the operator's separate, code-reviewed decision (§1.5, F-84472f89).
3. **Commit, shared-worktree safe** (`git commit --only`, never `git add -A` —
   other sessions commit into this same index, and `runbooks/state/active-updates.json`
   is routinely dirty from step 1 and from other agents' markers):
   ```bash
   git fetch origin main && git merge --ff-only origin/main
   git commit --only kubernetes/apps/monitoring/unpoller/app/helmrelease.yaml \
     -m "chore(unpoller): image v5.2.5 -> v5.2.7 on chart 2.4.0 (plan unpoller-v5.2.7)"
   git show --stat HEAD                 # exactly ONE file — reject anything else
   git log -1 --format=%s               # MUST be your subject; if not, git commit --amend
   git push origin main
   ```
4. **Let Flux reconcile on the webhook** — no manual `flux reconcile` by
   default. Watch the rollout:
   ```bash
   kubectl -n monitoring get pods -l app.kubernetes.io/name=unpoller -w
   ```
   Only if nothing has rolled after 10 min: check
   `flux get kustomization unpoller -n monitoring` shows the pushed revision; if
   the source is stale,
   `flux reconcile kustomization unpoller -n monitoring --with-source`.
5. **Close-out** after §4 passes: clear the marker
   (`runbooks/update-marker.sh clear unpoller`), delete this plan file in the
   close-out commit (`plans/README.md`: executed plans are deleted, git has the
   history), and record the execution via `autonomy-record.py` as the window
   agent's contract requires.

   **Before deleting this file, scrub inbound refs — this has broken the repo-wide
   validator on two consecutive nights (F-6acb231c).** Retiring
   `unpoller-v5.2.5` left 2 dangling `conflicts_with` refs; retiring
   `otel-operator-0.21.0` left 3. **As of 2026-09-20 there is exactly one
   inbound ref and it RESOLVES**: `kube-prometheus-stack-91.4.1` line 100 names
   `unpoller-v5.2.7` (its owner repointed it from the `unpoller-v5.2.6` id in
   their own commit — measured, see §6). That is precisely why deleting this
   file will orphan it: a live ref becomes a dead ref the moment this plan is
   retired. Remove or repoint it in the SAME commit.

   **Know your baseline before you start:** `maintenance-plan.py --validate`
   exits **0** right now — measured 2026-09-20 06:2xZ, output *"all plan
   frontmatter invariants hold"*, across all 41 plan files. There are **no**
   pre-existing dead refs to excuse a red result. So if the validator goes red
   after your close-out commit, **your close-out caused it** — fix it before
   pushing rather than dismissing it as someone else's breakage. Re-measure
   rather than trusting this paragraph; it is a snapshot, and other sessions
   retire plans in this same worktree.
   ```bash
   grep -rn 'unpoller-v5\.2\.7' runbooks/maintenance/plans/ | grep -v 'plans/unpoller-v5.2.7.md'
   .venv/bin/python3 runbooks/maintenance-plan.py --validate   # run BEFORE pushing the close-out
   ```

   **Findings:** `F-0e3c2de5` is `authored_by: policy-cli`, **not** a script
   producer — it will NOT auto-close. Close it by hand in the same turn, citing
   the bump commit. `F-23119c27` is `producer: script` and closes itself on the
   next sweep once the pin moves — do not close it by hand.
   ```bash
   runbooks/policy-cli.py finding close F-0e3c2de5 --commit <sha>
   ```

## 4) Verification

`Ready=True` proves nothing here — a running unpoller that stopped emitting
looks identical to a healthy one, and that is the documented failure mode of
this exact component (the chart-Service trap, §1 premises). Wait **≥ 5 min**
after the new pod is Ready, then work through the list. **The 5-minute wait is
now doubly load-bearing — see the box under §4.5; evaluating early produces a
~2x series count and can trigger a needless revert.**

### 4.0 Pin the pod FIRST — §4.1–§4.4 read `$POD`, never a label selector

**Do not skip this, and do not put `-l app.kubernetes.io/name=unpoller` back
into the four commands below.** The rollout is a `RollingUpdate` on 1 replica
(verified live 2026-09-20: `.spec.strategy.type=RollingUpdate`, exactly 1 pod),
so while the roll is in flight the OUTGOING v5.2.5 pod still matches that
selector — and a Terminating pod keeps `status.phase: Running`, so
`--field-selector status.phase=Running` does **not** exclude it either. Two
consequences, both confirmed against the live pod on 2026-09-20:

- `kubectl logs -l …` **concatenates every matching pod**, so §4.2/§4.3 would
  read the OLD pod's log. This is the **pass-on-failure** case: the v5.2.5 pod
  prints `UniFi Poller v5.2.5 Starting Up!`, `Prometheus scrape cache enabled,
  refresh interval: 2m0s` and `=> URL: https://<controller> (verify SSL: false,
  timeout: 1m0s)` **verbatim** — measured on it today — so a new pod that never
  printed those lines could still be reported PASS.
- `{.items[0]…}` in §4.1 selects by list order, not by age, so it can equally
  read the OLD pod and produce a false FAIL on a healthy rollout.

Resolve the pod ONCE and refuse to continue unless exactly one matches:

```bash
kubectl -n monitoring get pods -l app.kubernetes.io/name=unpoller \
  -o jsonpath='{range .items[*]}{.metadata.name}{"  phase="}{.status.phase}{"  deleting="}{.metadata.deletionTimestamp}{"\n"}{end}'
N=$(kubectl -n monitoring get pods -l app.kubernetes.io/name=unpoller --no-headers | wc -l | tr -d ' ')
echo "matching pods: $N"
# HARD GATE — N must be exactly 1 and that pod must print an EMPTY deleting= field.
#   N=2 → the old pod is still Terminating: WAIT. Evaluate nothing below.
#   N=1 but deleting= non-empty → that IS the dying pod: WAIT.
#   N=0 → no pod at all: that is a FAIL of the rollout, not a flaky query.
POD=$(kubectl -n monitoring get pods -l app.kubernetes.io/name=unpoller -o jsonpath='{.items[0].metadata.name}')
echo "POD=$POD"
```

**Why this is safe even though it cannot tell the old pod from the new one:** it
deliberately does not try. If the single surviving pod is the OLD one (the
rollout never happened), **§4.1 catches it** — the `imageID` will be unchanged.
Deciding identity is §4.1's job; §4.0's only job is to remove the ambiguity that
let the gates read two pods at once. Dry-run 2026-09-20 on the live cluster:
`N=1`, `POD=unpoller-9d8c6bdd7-r9kgx`, `deleting=` empty, and all four pinned
commands below returned their expected output.

1. **New bytes are running.** Tag is `ghcr.io/unpoller/unpoller:v5.2.7` AND the
   pod's `imageID` DIFFERS from the §2.6 baseline (it should carry the v5.2.7
   index digest `sha256:99f452d3…` from §2.3, or its amd64 child
   `sha256:8aebeff1…` — all three nodes are amd64):
   ```bash
   kubectl -n monitoring get pod "$POD" \
     -o jsonpath='{.spec.containers[0].image}{"  "}{.status.containerStatuses[0].imageID}{"\n"}'
   ```
   Dry-run 2026-09-20 on the live (pre-bump) pod returned
   `ghcr.io/unpoller/unpoller:v5.2.5  ghcr.io/unpoller/unpoller@sha256:123a42e6…`
   — i.e. the gate is wired correctly and currently reports the PRE-bump state,
   which is what it must do before the bump lands.
   **FAIL signature:** an unchanged `imageID` (still `sha256:123a42e6…`) means
   `IfNotPresent` served a cached layer set under a moved tag, and everything
   below would be measuring v5.2.5.
2. **The rebuilt binary identifies itself as v5.2.7, on the FRESH pod.** This is
   the assertion that separates "the tag moved" from "the new binary runs".
   ```bash
   kubectl -n monitoring logs "$POD" --tail=-1 | head -40 | grep -iE 'starting up'
   # MUST show:  [INFO] UniFi Poller v5.2.7 Starting Up! PID: 1
   # FAIL if it shows v5.2.5 — the rollout did not replace the process.
   ```
   **`"$POD"`, not `-l` (§4.0):** with a selector this line reads the old pod's
   banner too and cannot distinguish "v5.2.7 started" from "v5.2.5 is still
   here and v5.2.7 never printed anything".
   **Use `--tail=-1 | head -40`, NOT `--tail=200`.** The startup banner is
   printed once, at the head of the log, and this exporter emits ~1 line/minute
   forever after, so a 200-line tail only reaches back ~3 h. Measured 2026-09-20
   on the live pod: the retained log is **9179 lines** and `--tail=200 | grep -i
   'starting up'` returns **0 hits** while the full log returns exactly 1. On a
   pod minutes old either form works; the failure mode is a verification run late
   (or re-run next morning) that reports a *false* FAIL on a healthy rollout.
   Greps here are `-i` because the upstream lines are mixed-case.
3. **The config contract survived the rebuild** — same head-of-log window. The
   live v5.2.5 pod printed these exact lines at 2026-09-16T01:48:5xZ (verified
   2026-09-20), and `pkg/promunifi/` is untouched by both deltas (§1.2), so the
   text must be identical apart from the version:
   **These two are the gates §4.0 exists for** — the outgoing v5.2.5 pod prints
   both lines verbatim, so run them against `"$POD"` only. With `-l` they PASS
   on a new pod that printed nothing.
   ```bash
   kubectl -n monitoring logs "$POD" --tail=-1 | head -40 | grep -iE 'scrape cache'
   # MUST show:  Prometheus scrape cache enabled, refresh interval: 2m0s
   # FAIL if:    Prometheus scrape cache disabled; /metrics fetches live   (our "2m" parsed as 0)
   # FAIL if:    ... refresh interval: 1m0s                                 (parsed as nil → default)
   # FAIL if:    nothing at all — a silent start is not a pass.

   kubectl -n monitoring logs "$POD" --tail=-1 | head -40 | grep -iE 'verify ssl'
   # MUST show:  => URL: https://<controller> (verify SSL: false, timeout: 1m0s)
   # FAIL if the controller block is absent or followed by x509/certificate errors
   #      — that is the CA-bundle regression the base bump could theoretically cause.
   ```
   Both also confirm the InfluxDB output is still enabled: the line
   `Poller->InfluxDB started, version: 2, interval: 2m0s, …, bucket: default,
   org: influxdata` appears in the same block on the live pod.
4. **NEW — the OTel plugin is still OFF on the new binary (§1.4).** This is the
   assertion that makes the v5.2.7 delta's irrelevance a *measurement* instead of
   a claim. Upstream logs a specific line via `u.Logf` **only** when the plugin
   starts:
   ```bash
   kubectl -n monitoring logs "$POD" --tail=-1 | grep -icE 'OpenTelemetry \(OTel\) output plugin enabled'
   # MUST print 0.
   ```
   **Pinned to `"$POD"` for the opposite reason to §4.2/§4.3:** with `-l` a
   concatenated OLD pod log would dilute nothing here (0 + 0 = 0), but it would
   also let a NEW pod that *did* enable the plugin hide behind a quiet old one
   if the counts were ever read per-pod. Dry-run 2026-09-20 on the live pod:
   prints `0`.
   **FAIL signature:** any non-zero count means an `[otel]` block or env reached
   the pod, the changed `recordGauge` path is live, and §1.4's entire argument is
   void — stop and re-assess rather than continuing down this list.
   *(`grep -c` prints 0 and exits 1 when there is no match; read the number, not
   the exit status.)*
5. **CONTENTS ASSERTION (the scrape still delivers the same population)** —
   measured by the §2.6 `q` helper, compared to the SAME-SESSION baseline, all
   evaluated ≥ 5 min after Ready so the window starts after the change:
   - `up{job="unpoller"}` == `1`
   - `count(unpoller_site_adopted)` == baseline (3 at authoring)
   - `count(unpoller_device_uptime_seconds)` == baseline (10 at authoring — the
     `UnifiDeviceOffline` rule's comment independently records 10 devices)
   - `count({__name__=~"unpoller_.*"})` within **±2% of the §2.6 baseline** AND
     **≥ 6000 absolute**. The band is justified in §2.6 (6 h spread ±0.8% around
     ~7945, measured 2026-09-20); the absolute floor is the part that cannot be
     argued away by drift and catches the "green and empty" failure — a collapsed
     exporter returns 0 or single digits, not 6000.
   - `count(count_over_time(unpoller_site_adopted[5m]))` > 0 at that point
     (measured 3 at baseline), so the assertion is reading post-change samples
     rather than stale ones.

   > **DO NOT evaluate this gate before the 5-minute mark — you will see roughly
   > DOUBLE and revert a healthy bump.** Per **F-26b89cde** (measured 2026-09-19):
   > unpoller device metrics carry `instance`/`pod` in their series identity, so
   > when the pod is rescheduled its IP changes and every physical device
   > acquires a SECOND series with the same `mac` but a different `instance`.
   > Measured there: **18 series over 7d against 9 live** — every live radio had
   > a stale twin. Instantaneous queries are *correct* because a stale series
   > stops receiving samples and falls out of the 5-minute lookback — but for the
   > first ~5 minutes after the roll BOTH the old and the new series are inside
   > that lookback and `count()` counts both. That is a transient artefact of the
   > rollout, not a regression, and waiting it out is the whole fix. The same
   > finding is why you must NOT re-baseline this gate over a multi-day window:
   > any query spanning a reschedule silently mixes a live and a dead exporter.

   **This is the check that fails if the exporter came up green and empty** —
   the chart-Service trap, a metric rename, or a scrape-path break all land
   here. A count materially ABOVE baseline *after* the settle is also a finding
   (in v5.2.5 the benign cause was locate-mode devices newly exported; neither
   delta here has such a mechanism, so investigate rather than accept).
6. **CONTENTS ASSERTION (the background cache poller runs at OUR interval):**
   `unpoller_prometheus_cache_age_seconds` EXISTS and is `< 150` on two samples
   3 min apart. Measured over the last 6 h on 2026-09-20 this gauge peaks at
   **90.25 s** against a 2m refresh, so 150 leaves real headroom and still trips
   on a stalled poller. **The failure signature is `absent(...)`, not a large
   number**: `cacheAgeGauge()` is only registered inside
   `if u.scrapeCacheEnabled()`, so a cache taken as disabled makes the series
   vanish entirely rather than grow. Also
   `increase(unpoller_prometheus_refresh_failures_total[10m])` == 0 — **the
   rate, not the absolute counter**, which stands at 1 cumulative as of
   2026-09-20 with zero increase over 24 h (§2.6).
7. **CONTENTS ASSERTION (the InfluxDB write path still advances):** re-run the
   §2.7 Flux query **with the same `range(start:-2h)`** — the newest
   `uap_radios` `_time` must be **NEWER** than the §2.7 baseline timestamp taken
   in this session.

   > **AN EMPTY RESULT IS A FAIL, NOT A TOOLING PROBLEM.** Measured 2026-09-20
   > against the live instance: a Flux query matching nothing returns a bare
   > `\r` — no rows, no error message, exit status 0. So "the command printed
   > almost nothing" is indistinguishable at a glance from "I mistyped the
   > measurement", and the tempting reading (*"the query is broken, skip it"*)
   > is exactly wrong: with `-2h` a write path that is merely stalled still
   > returns its OLD timestamp, so **empty means the measurement has not been
   > written for two hours** — a harder failure than a frozen one, not a softer
   > one. If you get an empty result, treat §4.7 as FAILED and go to §5. (This
   > is also why §2.7 must not be narrowed back to `-30m`, where a >30 min
   > outage produces the same silent empty output.)

   Tag/field names are unchanged
   by both deltas (§1.2), so nothing needs repointing; a frozen timestamp would
   mean the write path broke, which §1 says cannot happen from these deltas —
   **which is exactly why it is checked.** This is the second independent output
   of the same process, so it distinguishes "Prometheus scrape broke" from "the
   poller stopped polling".
8. `UnifiMetricsAbsent` (`absent(unpoller_device_uptime_seconds)`, `for: 15m`),
   `UnifiClientMetricsAbsent` (`absent(unpoller_client_satisfaction_ratio)`) and
   `UnifiControllerUnreachable` are NOT firing 15 min after Ready; the in-repo
   Grafana UniFi dashboards render data past the rollout time, not a flat line
   ending at it.

## 5) Rollback

One `git revert` of the §3.3 commit restores `image.tag: v5.2.5`:

```bash
git revert <sha>
git push origin main
```

The rollback target is unusually well-proven here: v5.2.5 is published
(§2.3 re-confirmed HTTP 200 on 2026-09-20, index digest `sha256:123a42e6…`), and
that exact digest is the `imageID` the live pod has been running since
2026-09-16T01:48:49Z with **0 restarts** (re-verified 2026-09-20) — this is a
return to a state observed healthy for four days, not to a theoretical one.
**Note it is v5.2.5, not v5.2.6:** v5.2.6 has never run in this cluster, so it is
not a rollback target and must not be used as one.

Then let Flux roll the Deployment back and confirm §4.1 shows `v5.2.5`, §4.2
shows `UniFi Poller v5.2.5 Starting Up!`, and §4.5–4.7 pass again.

**Nothing is forward-only**, so `rollback_class: git-revert` is honest rather
than optimistic: unpoller is a stateless scraper with no PVC, no schema and no
migration; the InfluxDB measurements are identical on both sides of this patch,
so there is no mixed-key window to clean up and no dump to take first. If Helm is
ever wedged `pending-upgrade` (not expected for a tag-only change):
`helm rollback unpoller <last-deployed-rev> -n monitoring --wait=false` then
`flux reconcile helmrelease unpoller -n monitoring --force`, per
application-update.md §11. Clear the update marker either way.

## 6) Interference notes

- **Blast radius if wrong:** UniFi observability only. `unpoller_*` series stop,
  the ten `unifi.*` alert rules go blind (the two `absent()` guards fire after
  15m, which is the intended loud failure), and the 20 InfluxDB UniFi
  measurements freeze. **No workload, gateway, storage or auth path depends on
  unpoller, and nothing depends on it for recovery** — it is a leaf exporter.
- **Shared infra: none perturbed**, hence `shared: []` (justified in the
  frontmatter). unpoller continues writing to the shared influxdb2 (`databases`
  ns, bucket `default`) with an unchanged schema and restarts nothing shared.
  §4.7 checks that write path anyway because it is cheap, and because the v5.1.0
  plan taught that "the schema did not change" is a claim, not a check.
- **The off-cluster surface it DOES touch: the UniFi controller API.** The
  rollout is chart-default `RollingUpdate` on 1 replica with no PVC, so for a few
  seconds two pollers authenticate against the gateway concurrently. At a 2m poll
  cadence that is a single extra login round, far under the threshold that caused
  the 429 lockout (`docs/sops/unifi-controller-rate-limit.md`: ~1 login/min at
  2m vs ~4/min at 30s). Acceptable; no `Recreate` needed (no RWO volume). **Do
  not "fix" this by enabling the chart's PodMonitor** — that is the duplicate-
  scrape path the premises forbid.
- **The rollout leaves stale duplicate series behind, by design of the metric
  identity (F-26b89cde).** Every pod reschedule does this; it is not caused by
  this bump and is not this plan's to fix. Two consequences for whoever runs the
  window: (a) §4.5 must be read **after** the 5-minute settle, or it reports ~2x;
  (b) do not answer "did the bump change anything?" with a multi-day PromQL
  window — that window spans the reschedule and mixes a live exporter with a dead
  one (measured there as a 5x spread on one radio). Compare same-session instant
  values, which is what §4 already does.
- **Same-namespace / same-instrument plans (re-checked against
  `maintenance-plan.py --open`, 2026-09-20):**
  - `kube-prometheus-stack-91.4.1` (**draft, window null**) — **hard conflict,
    in `conflicts_with`**, and its own §6 asks any successor unpoller plan to
    re-add it. Never the same window. If an operator overrides that, run unpoller
    **fully before** kps (complete §4 including the ≥5-min settle) or **fully
    after** kps's own verification has passed — never interleaved.
    **This ref was repointed on 2026-09-20**: that plan was re-targeted from
    `91.4.0` to `91.4.1` in this same worktree while this plan was being
    re-targeted. 91.4.1 is chart-only (same operator appVersion `v0.94.0`), so
    the conflict *reason* is untouched — it still restarts Prometheus and
    Alertmanager, which is the whole basis for the exclusion.
  - `prometheus-crd-ownership` — **in `conflicts_with`**; it touches the CRD
    behind this plan's only scrape path. **CHANGED since the v5.2.6 draft:** it
    is now `status: awaiting-go`, `window: "sat-attended:2026-09-26"` (it was
    vetted/window-null on 2026-09-17), so this exclusion now removes a real date
    rather than a hypothetical one — **this plan must not be slotted into
    sat-attended:2026-09-26.** Expected perturbation is still zero (its §4.2
    asserts the CRDs are unchanged); the exclusion exists so that if it is ever
    non-zero, the damage does not get misattributed to this image bump and revert
    it needlessly.
  - `cilium-1.20.2` (draft, window null) — **in `conflicts_with`**; a CNI roll
    restarts the network every §4 assertion rides on. It declares a solo slot
    (**12** exclusions — counted 2026-09-20 from its own `conflicts_with`
    block), so in practice it excludes everything.
  - **Inbound refs: exactly one exists, and it now RESOLVES — no action
    outstanding.** `kube-prometheus-stack-91.4.1` added
    `- unpoller-v5.2.6  # ADDED 2026-09-20 (RECIPROCITY)` to its
    `conflicts_with` earlier today, pointing at this plan's pre-rename id; **its
    owner has since repointed it to `unpoller-v5.2.7`.** Re-measured 2026-09-20
    06:2xZ: `grep -rn 'unpoller-v5\.2\.[0-9]' runbooks/maintenance/plans/` shows
    that entry at line 100 of its file reading `unpoller-v5.2.7`, and
    `maintenance-plan.py --validate` exits **0** with *"all plan frontmatter
    invariants hold"* — the dangle reported in the earlier draft of this bullet
    is GONE, and the repo-wide validator is clean. **Do not re-report it as
    broken**, and note the consequence in the other direction: because the ref
    is live, retiring this file WILL orphan it (§3.5 handles that). The
    exclusion is now declared on BOTH sides, which is belt-and-braces rather
    than required — `window-scheduler.py` honours `conflicts_with`
    symmetrically (`conflicts & here` OR `names_me`), so either side alone
    suffices.
    `cilium-1.20.2` and `prometheus-crd-ownership` name no unpoller plan at all;
    each dropped its `unpoller-v5.2.5` ref when that plan retired on 2026-09-16
    and no successor ref was added. That is tolerable **only** because
    `window-scheduler.py` honours `conflicts_with` symmetrically (`conflicts &
    here` OR `names_me`), so the three entries in this plan's frontmatter are
    sufficient unilaterally. Do not "tidy" them away on the grounds that the
    other side is silent.
  - `edot-collector-0.161.0` (draft, window null, `shared: [monitoring]`) —
    **not a conflict.** Re-read 2026-09-20: it rolls `deployment/edot-collector`
    and its own §4 reads `otelcol_*` from this same Prometheus, but it restarts
    neither Prometheus nor anything on unpoller's scrape path, and its
    `conflicts_with` (prometheus-crd-ownership, kube-prometheus-stack-91.4.0,
    talos-1.14.0) does not name unpoller. The two `touches.shared` sets do not
    even intersect (this plan declares `[]`). Sharing a window is acceptable, in
    either order. **Note the name collision trap:** `edot-collector` is an
    OpenTelemetry collector and this plan's §1.4/§4.4 are about unpoller's own
    `pkg/otelunifi` output plugin — they are unrelated, and unpoller emits no
    `otelcol_*` series (measured 2026-09-20: zero).
  - **A collector roll of either kind causes a ~10-30 s per-node pod-log gap in
    Elasticsearch.** Never read ES log continuity as an unpoller signal on a
    night one runs — every assertion in §4 reads Prometheus, InfluxDB or the
    pod's own log, which a collector restart does not perturb.
  - `flux-oci-chart-sources` §3.5 explicitly parks unpoller (migrating it to OCI
    would force a chart upgrade in the same commit, because 2.4.0 is absent from
    the OCI repo). This plan does not move `HelmRepository/unpoller`, so there is
    no ordering relation — but it is the reason the chart leg stays put.
- **Pre-existing noise, NOT this plan's scope — do not "fix" it mid-window:** the
  live log carries periodic `[INFO] Re-authenticating to UniFi Controller …`
  lines driven by intermittent `401`/`500` responses from the UDM-Pro's Network
  app (the same flaky control plane as the JVM-GC pattern). The scrape cache
  preserves the last snapshot across them, and
  `unpoller_prometheus_refresh_failures_total` has incremented exactly **once in
  three days** with zero increase in the last 24 h (§2.6). A re-auth line after
  the rollout is **not** a regression; only a sustained failure to poll (cache
  age growing past 150 s, §4.6) is.
- **Deny rule:** untouched by this plan (§1.5 gives the operator the facts and
  cites F-84472f89, which already carries the remedy). If it is narrowed first
  and Step 0 lands the bump, the premises fail on purpose — run §4 against the
  landed bump and retire this plan, do not re-run it.
