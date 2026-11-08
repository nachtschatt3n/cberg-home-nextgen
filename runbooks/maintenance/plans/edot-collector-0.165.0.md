---
plan_id: edot-collector-0.165.0
component: edot-collector
pr: 500                           # Renovate "feat(container): update otel/opentelemetry-collector-contrib
                                  # ( 0.164.0 → 0.165.0 )", branch renovate/otel-opentelemetry-collector-contrib-0.x.
                                  # OPEN, mergeable UNKNOWN (just rebased), 4 checks SUCCESS incl. Flate Render
                                  # Gate (measured 2026-11-08). THE PR IS NOT SAFE TO MERGE ALONE: its one-line diff
                                  # alone crash-loops the collector (section 1.2). This plan lands the image bump
                                  # and the required config edit in ONE commit and then closes the PR.
kind: image
current: "0.164.0"                # MEASURED 2026-11-08: deployment/edot-collector image
                                  # otel/opentelemetry-collector-contrib:0.164.0, pod edot-collector-857f67ff59-2hlh8
                                  # (start 2026-11-06T12:32Z, 0 restarts), imageID
                                  # ...@sha256:340c9ca6a36617084c6661bdc4f0fe92b7cda5a805d61673ec8db375fddc522b
target: "0.165.0"                 # Docker Hub multi-arch MANIFEST LIST, digest
                                  # sha256:e40d61f10c9a617cca1ffd1be4d7e2b3a4b0f0001798ff07e58cabe82e618cea,
                                  # 7 linux platforms incl. amd64 (measured 2026-11-08). releases-repo v0.165.0
                                  # 2026-11-07T05:02Z = core v0.165.0 + contrib v0.165.0. Tags 0.165.1 and 0.166.0
                                  # are HTTP 404: there is no newer image to wait for.
update_type: minor                # 0.x line: the MINOR digit is the breaking axis
risk: medium                      # NOT from the changelog (which is silent on the break that matters) but from
                                  # blast radius + failure MODE: one replica, the sole OTLP path into
                                  # Elasticsearch for every namespace plus the Talos kmsg sink, and a Recreate roll
                                  # on an RWO queue volume. With the config edit the live config validates on the
                                  # 0.165.0 binary (section 1.3); WITHOUT it the pod cannot start.
est_duration_min: 60              # 17 pre-checks (tag gate, local + in-cluster validate with controls, startup
                                  # rehearsal, baselines) + 3 silence/marker + 4 commit/push/close PR + 8 settle
                                  # (Reloader may roll a second time) + 2 startup gate + 4 heartbeat kick +
                                  # 15 settle (every [15m] window in section 4 must lie after the roll) + 12
                                  # verification. Over the 52 min of the 0.164.0 plan because of the
                                  # config leg; fits a nightly slot (90 - STEP0 20 = 70) but attended is preferred.
needs_reboot: false
touches:
  namespaces: [monitoring]
  resources:                      # every object below verified to EXIST live 2026-11-08
    - deployment/edot-collector               # image tag AND (via configmap + Reloader) a pod roll; strategy Recreate (measured)
    - configmap/edot-collector-config         # EDITED: the three `mapping: mode: otel` blocks are removed (section 3 step 2)
    - daemonset/kmsg-heartbeat                # pod-template annotation only (section 3 step 5): restarts the 3 heartbeat pods
    - pvc/edot-collector-queue                # RWO longhorn-static, Bound, 10Gi; bbolt sending queue; detach/attach on the
                                              # Recreate roll; the forward-only surface (section 5.2)
    - service/edot-collector                  # ClusterIP 4317/4318/8888/8889 — every OTLP producer's target
    - service/edot-collector-talos-kmsg       # LoadBalancer 192.168.55.18 UDP 5171
    - servicemonitor/edot-collector           # the scrape feeding section 4
    - httproute/edot-collector                # OTLP/HTTP on envoy-internal; backend briefly down during the roll
    - kustomization/edot-collector            # Flux Kustomization, namespace monitoring (Ready, measured)
    - deployment/reloader                     # kube-system; READ-ONLY dependency: it turns a configmap change into a
                                              # second rollout (section 3 step 3). Not modified.
  shared: [monitoring]            # the single OTLP choke point for every namespace's logs/metrics into
                                  # Elasticsearch + the Talos kmsg sink (TalosKernelLogsMissingFromNode). A roll
                                  # blinds cluster-wide ingestion for its duration. NOT gateway/envoy: routing unchanged.
depends_on: []
conflicts_with:                   # HARD slot exclusions — the only field window-scheduler.py honours. Built from
                                  # every plan file's frontmatter on 2026-11-08. There is NO open otel-operator or
                                  # kube-prometheus-stack plan today (otel-operator 0.27.0 landed 2026-11-07 via
                                  # eee6e16c5; kube-prometheus-stack PRs #501 major and #428 are unplanned and are
                                  # held by the time-boxed deny rule), so those two are kept out of this night by the
                                  # section 2.1b path gate and the section 6 PR list, not by a plan ref.
  - talos-linux-1.14.5            # EXCLUSIVE reboot plan: node drains evict this single replica (RWO queue re-attaches)
                                  # and silence each node's kmsg feed for its reboot — section 4.3/4.4 would misattribute.
  - longhorn-1.13.0               # EXCLUSIVE: the bbolt queue is an RWO Longhorn volume; an engine/manager roll during
                                  # the Recreate detach/attach is the Multi-Attach surface.
  - grafana-14.1.0                # monitoring-namespace attribution: keep a failed gate attributable to ONE change.
  - flux-oci-chart-sources        # re-sources every HelmRelease incl. kube-prometheus-stack and otel-operator
                                  # (monitoring); section 4 reads Prometheus — authoring rule 4 (shared instrument).
  - flux-reconciler-impersonation # EXCLUSIVE: changes the service account every Flux controller reconciles as, in
                                  # monitoring too; would blur a failed reconcile in section 3.
  - envoy-gateway-1.10.0          # EXCLUSIVE, shared monitoring: the gateway pods are scraped by the daemon collectors
                                  # whose histograms transit this collector (cumulative_to_delta include list).
  - etcd-timeouts-5000-500        # EXCLUSIVE-class control-plane disturbance (restarts etcd on all three nodes): can
                                  # fail kubectl-driven gates and the RWO re-attach.
  - helm-drift-detection          # fleet-wide HelmRelease reconcile load; touches monitoring.
  - talos-power-tuning-ab         # EXCLUSIVE, shared monitoring: per-node power A/B; node-level perturbation of the
                                  # sole replica's host.
  - descheduler-0.37.0            # may evict the single replica mid-roll (pod-placement, shared monitoring).
exclusive: false
security_ref: null                # F-dbefa2e5 (security, OPEN, last seen 2026-11-06) is filed against the 0.161.0 IMAGE,
                                  # which no longer runs; its title predates the 0.164.0 roll. It is NOT this plan's
                                  # driver and this plan does not assert it closes — the next sweep's image scan of the
                                  # running pod decides. Detail stays in the DB.
capability_change: false          # image tag + removal of a config key upstream documents as "ignored since v0.145.0"
                                  # (section 1.2). No new receiver/exporter/processor/route/permission; the one
                                  # observable difference is an extra `temporality` field in the _source of histogram
                                  # documents (not indexed, section 1.2) and log-line changes. Same contract.
rollback_class: git-revert        # one-commit revert restores image 0.164.0 AND `mode: otel` (that pair validates
                                  # exit 0 on the 0.164.0 binary, section 1.3). The one forward-only surface — the bbolt
                                  # queue written by the newer binary — has an explicit PROCEDURE in section 5.2.
finding_refs: [F-cb9182ca]        # the stable version row "edot-collector: image otel/opentelemetry-collector-contrib
                                  # X -> Y (minor)". A row exists for exactly THIS bump: F-cb9182ca, last seen
                                  # 2026-11-08, 0.164.0 -> 0.165.0 (coordinator/reviewer check; my 2026-11-08 `--grep 0.165`
                                  # query ran before the sweep wrote it). F-76387378 (health, monitor, open: edot ES
                                  # dropped metric points 360/h) is NOT answered here — it is a pre-existing baseline
                                  # this plan must not be blamed for or credited with (section 2.4, 4.2).
review: ready-for-go@2026-11-08   # plan-reviewer 2026-11-08: needs-fix (section 4.2(b) gate had an unreproducible known-bad claim), fixed with a same-selector positive control, delta re-review ready-for-go; HUMAN-GATED for GO at the window
status: vetted
window: "sat-attended:2026-12-05"   # attended, operator on hand for the section 5.3 kmsg toggle; first Saturday slot with no other plan (11-14 python-fleet+open-webui, 11-21 coredns, 11-28 helm-drift-detection); status stays draft until re-reviewed
premises:
  # Re-checked at EXECUTION time. All RUN on 2026-11-08 while writing this plan.
  - id: image-is-still-0.164.0
    why: >-
      `current:` claims 0.164.0. If PR #500 was merged by hand or by anything else, the collector is ALREADY
      crash-looping on the invalid `mapping::mode` key (section 1.2) and this plan's section 3 is the wrong tool:
      go to section 6 "PR #500 merged alone". Prints the actual image when it fails.
    run: kubectl get deploy -n monitoring edot-collector -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "otel/opentelemetry-collector-contrib:0.164.0"
  - id: ingestion-is-healthy-before-we-touch-anything
    why: >-
      Never roll the sole telemetry path while it is ALREADY degraded — a pre-existing stall would be misattributed
      to this bump. Asserts the logs exporter persisted more than 1000 records over the last 15m (measured 24,016 on
      2026-11-08; 7d min of the same expression 16,555). The awk `$1+0` coercion makes an empty result fail closed
      (INGEST_LOW). Written with `<` because the premise sandbox refuses the greater-than character.
    run: kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=sum(increase(otelcol_exporter_sent_log_records_total[15m]))' | sed -E 's/.*"value":\[[0-9.]+,"([0-9]+).*/\1/' | awk '{print ($1+0<1000)?"INGEST_LOW":"INGEST_OK"}'
    expect_exact: "INGEST_OK"
  - id: config-still-carries-the-three-mapping-mode-keys
    why: >-
      The edit in section 3 step 2 removes exactly three `mapping: mode: otel` blocks and asserts the count is 3.
      This counts them in the LIVE ConfigMap. If it is no longer 3 somebody already edited the config (or added a
      fourth exporter): re-read section 1.2 before running the edit. Measured 3 on 2026-11-08.
    run: "kubectl get cm -n monitoring edot-collector-config -o jsonpath='{.data.otel\\.yml}' | grep -c 'mode: otel'"
    expect_exact: "3"
  - id: config-is-the-one-validated-on-0.165.0
    why: >-
      Section 1.3's evidence holds only for the config committed in 429791200 (2026-09-28, the last commit touching
      configmap.yaml; live otel.yml sha256 063d47a8..96a5d, 19,505 bytes, identical to the 2026-11-06 copy). If the
      configmap moved the evidence is stale (section 2.3 still re-runs either way). PREFIX match on purpose: git
      abbreviates %h to 9 characters today and may grow; an exact 8- or 9-char expected value failed this premise once.
    run: git log -1 --format=%h -- kubernetes/apps/monitoring/edot-collector/app/configmap.yaml
    expect_matches: "^42979120"
  - id: elasticsearch-is-8.19-green
    why: >-
      Section 1.2's histogram verdict (TDigest mapping kept, cumulative histograms still dropped) holds only below
      Elasticsearch 9.4.0 / 9.5.0. 0.165.0's version probe is now AUTHENTICATED and therefore works, so an ES at 9.4+
      would switch histogram documents to the exponential mapping at the same time as this bump. Measured
      `8.19.20 green` 2026-11-08.
    run: kubectl get elasticsearch -n monitoring elasticsearch -o jsonpath='{.spec.version} {.status.health}'
    expect_matches: '^8\.19\.\d+ green$'
  - id: kmsg-heartbeat-daemonset-ready-on-all-nodes
    why: >-
      Section 4.4's per-node gate depends on one heartbeat pod per node writing a kmsg line when it starts. With
      fewer than 3 ready the gate would read a missing heartbeat POD as a stalled kmsg SENDER. Measured 3 on 2026-11-08.
    run: kubectl get ds -n monitoring kmsg-heartbeat -o jsonpath='{.status.numberReady}'
    expect_exact: "3"
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/monitoring.md                          # "ES Rejected Documents" — section 4.2 uses the dotted outcome metric
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/longhorn-rwo-multi-attach.md           # why strategy Recreate is load-bearing
  - docs/troubleshooting/node-reboot-observability.md  # kmsg-sender stall + the url-toggle recovery in section 5.3
generated: "2026-11-08"
---

# edot-collector: image 0.164.0 → 0.165.0 (0.x release-line move) — needs a config edit or the pod cannot start

## 1) Summary & why held

### 1.1 Why it was held

`runbooks/coverage.py` routes this to the PLAN lane on its component-agnostic rule (`coverage.py` line 2538:
*"0.x release-line move (0.164 -> 0.165) — at major 0 the minor IS the breaking axis"*). That hold is structural, not
release-notes-dependent, so tonight's Step 0 will NOT auto-merge PR #500 (confirmed by reading the rule; the policy
YAML has no edot rule and needs none). Renovate itself only automerges github-actions. The PR is the one-line
diff `image: otel/opentelemetry-collector-contrib:0.164.0` → `:0.165.0` in
`kubernetes/apps/monitoring/edot-collector/app/deployment.yaml`, all four checks green.

**Those green checks are exactly why this plan exists.** `Flate Render Gate` renders manifests; it does not start the
binary. Merging #500 on its own produces a Deployment whose new pod exits at startup (section 1.2), and because
the strategy is `Recreate` the old pod is already gone: every namespace's telemetry and the Talos kmsg feed are dark until a
revert lands.

### 1.2 Upstream evidence — assessed against OUR config

Read directly from upstream code at the tags (authoring rule 8), not from a SOP or deny reason: contrib `v0.165.0`
(2026-11-07), core `v0.165.0`, releases-repo `v0.165.0`, and `exporter/elasticsearchexporter` source at `v0.164.1`
(the exporter version inside 0.164.0) and `v0.165.0`.

**THE BREAK (not in any release note).** Commit `e38696a4d6` "[chore][exporter/elasticsearch] Remove deprecated
configs (#52027)", merged 2026-11-05, is a `[chore]`, so it has **no changelog entry**: a grep of the whole v0.165.0
contrib changelog for "mapping" finds only an unrelated opensearch line. It deletes `MappingsSettings.Mode`. At
`v0.164.1` `config.go` reads *"Deprecated: [v0.145.0] Mode is ignored. The default mapping mode is "otel"."*; at
`v0.165.0` the field is gone and `mapping` accepts only `allowed_modes`. Our ConfigMap sets `mapping: mode: otel` on all
three exporters (`elasticsearch/logs`, `/metrics`, `/traces`), so the real 0.165.0 binary prints
`'mapping' has invalid keys: mode` and exits 1 (section 1.3). The same commit also removed `logs_dynamic_index`,
`metrics_dynamic_index`, `traces_dynamic_index` and `retry::max_requests`; the live config sets none of them.
Auto-update's "no breaking-change signal in the release notes" test cannot see this class of break.

**THE FIX (from upstream code).** `v0.165.0` `exporter.go` lines 61-66: `defaultMappingMode := MappingOTel`, and it
changes only when `allowed_modes` is non-empty and omits `otel`. `README.md` at the tag: *"`allowed_modes` (defaults to all
mapping modes) ... If `otel` is included in the list, it is used as the default mapping mode."* Because `mode` was already
ignored, **deleting the three `mapping:` blocks is a behavioural no-op** — the default mode today and tomorrow is `otel`.
I deliberately did NOT use `allowed_modes: [otel]`: today every mode is allowed (nothing requests another), and restricting
it would be a new behaviour. Candidate "A" (delete) validates exit 0 on both the 0.164.0 and the 0.165.0 binary, which is
what lets rollback be a plain revert.

**Everything else in 0.165.0 against our components** (receivers `otlp`, `udp_log/talos-kernel` with stanza
`json_parser`/`move`/`add`; processors `memory_limiter`, three `filter`, one `transform` (OTTL `delete_key` + `IsMap`),
`cumulative_to_delta`, `batch`; exporters three `elasticsearch`, `prometheus/hwerrors`; connector `count/hwerrors`;
extensions `file_storage/queue`, `health_check`; the `service::telemetry` Prometheus reader with three `without_*: false`
pins; no `--feature-gates`):

| 0.165.0 entry | reaches us? | assessment |
|---|---|---|
| core breaking: `pkg/confighttp` removes `IdleConnTimeout`, `MaxIdleConns`, `MaxIdleConnsPerHost`, `DisableKeepAlives` | no | none set on any client; ES exporter keys are `endpoints`/`user`/`password`/`tls`. Validates. |
| contrib breaking (SignalFx receiver, service_graph gates, goldendataset/jaeger/zipkin conventions, resource_detection, `transform` `flatten_data`, file_log/kafka_metrics gates, prometheus receiver labels) | no | none instantiated. `transform/strip-k8s-managedfields` uses `log_statements` only; `flatten_data` is not set. |
| **`exporter/elasticsearch`: "Add authentication credential support to the Elasticsearch Exporter version check" (#52437)** | **yes** | `es_version.go` v0.165.0 lines 77-97 now pass `cfg.Authentication.User/Password` to the probe. At 0.164.0 the probe was unauthenticated and logged three `es info returned status 401` warnings (live pod log, 2026-11-08). At 0.165.0 it SUCCEEDS: measured on the real binary, **3 × `Connected to Elasticsearch ... version 8.19.20`, 0 × 401**. This FLIPS the startup gate of the 0.164.0 plan (section 2.3(c), 3 step 4, 4.0 below). |
| **`exporter/elasticsearch`: cumulative-temporality histograms + a `temporality` field on histogram documents (#52547)** | **yes** | `exporter.go` lines 320-326: a cumulative histogram is accepted only when `supportsCumulativeHistograms(esVersion)`, i.e. ES >= 9.5.0; otherwise it is dropped with the NEW text `dropping cumulative temporality histogram "<name>": requires Elasticsearch >= 9.5.0`. Ours is 8.19.20, so **the same ~60 drops per 15 min continue** (the existing baseline, F-76387378); the grep `dropping cumulative temporality` still matches. Histograms we convert to delta (`cumulative_to_delta/es-histograms`) are serialised with a new top-level `"temporality":"delta"` (`otelserializer/metrics.go` line 33; `Number.Temporality()` and `Summary.Temporality()` return "", so gauges/sums are unchanged). **Does ES reject the new field?** No: simulated index `metrics-generic.otel-default` resolves `mappings.dynamic = false` (component template `otel@mappings`), `temporality` is mapped in no backing index, so it stays in `_source` only — not indexed, not a TSDB dimension. Section 4.3 uses it as positive proof of the new binary, and section 2.4b shows today's documents carry none. |
| `exporter/elasticsearch`: failed-document log fields no longer accumulate (#52714) | log text only | none. |
| **core `pkg/service`: "Warn at startup when a pipeline combines the batch processor with exporterhelper batching" (#15965)** | **yes (log only)** | Measured on the real binary: **4 × `Pipeline has both a batch processor and an exporter with batching enabled; this will cause double batching`** (pipelines `logs`, `logs/talos-kernel`, `metrics`, `traces`). The 0.164.0 pipeline has always double-batched; only the warning is new. EXPECTED, informational, not a failure; deciding whether to drop the `batch` processor is a separate change. |
| core `processor/memory_limiter`: new `garbage_collector.enabled` | opt-in | not set; default behaviour unchanged. |
| core `pkg/exporterhelper`: fix "Cannot unref freed data" panic when a persistent queue forwards into another pipeline (#15256) | bug fix | we use a persistent queue; strictly a fix. |
| contrib `receiver/udp_log`: `resolve_names` option (#52603) | opt-in | `v0.165.0` `pkg/stanza/operator/input/udp/config.go` lines 109-114: default `resolveNames := true` — unchanged. The stable-network-attributes gate `stanza.udp.useStableNetworkAttributes` is still **StageAlpha** (disabled) at v0.165.0, so `net.peer.ip` — the attribute every kmsg gate and the `count/hwerrors` connector key on — keeps its name. |
| contrib `processor/cumulative_to_delta`: invalid regexp now an error instead of a panic (#51963) | bug fix | our `include` regexes compile (validate passes). |
| contrib `exporter/prometheus`: new opt-in gate `KeepIdentifyingResourceAttributes` | opt-in | not enabled; `prometheus/hwerrors` labels unchanged. |
| contrib `pkg/ottl` substring-matching optimisation for literal `IsMatch` patterns (#52593) | perf | "without changing regex semantics". Our filter regexes are not literal-only; OTTL parse errors are fatal at validate (negative control below). |

No change reaches `file_storage`, `health_check`, `connector/count`, `batch` or `filter` (grep of both changelogs). The
two invariants the brief of earlier plans named are untouched: the managedFields `"."`-key strip parses on 0.165.0
(the `IsMapp` control fails as it must) and the ES TSDB OTel metrics stream keeps its TDigest histogram mapping
(`resolveDefaultHistogramMapping` returns exponential only for ES >= 9.4.0, ours is 8.19.20).

### 1.3 The live config on the 0.165.0 binary — before and after the edit

Run 2026-11-08 on the Mac with the official `otelcol-contrib_0.165.0_darwin_arm64.tar.gz` (sha256
`f9a0ed310e9beeb0fabca9d9c24bd0d3467f6339e3207710dbd66a6adf1298f6`, equal to the release asset's published digest; banner
`otelcol-contrib version 0.165.0`) and the 0.164.0 binary, against the LIVE `otel.yml` pulled from
`configmap/edot-collector-config` (sha256 `063d47a846f28ea7f3ba87d868961555bf7059038721888eb71c488676b96a5d`):

| input | 0.164.0 exit | 0.165.0 exit | meaning |
|---|---|---|---|
| live `otel.yml` unedited | **0** | **1** `'mapping' has invalid keys: mode` | THE BREAK |
| live with the 3 `mapping:` blocks deleted (candidate A) | 0 | **0**, empty output | the fix, valid on both binaries |
| candidate A rendered from the git `configmap.yaml` after the section 3 step 2 edit (`$$`→`$`) | 0 | 0 | byte-equal to candidate A, so what we commit is what was validated |
| candidate B (`allowed_modes: [otel]`) | 0 | 0 | works, but changes behaviour; not chosen |
| A with `num_consumers: notanint` | — | 1 `failed to get config: cannot unmarshal` | type errors caught |
| A with `IsMap(log.body)`→`IsMapp(log.body)` | — | 1 `unable to parse OTTL statement` | OTTL errors caught |
| A with `bogus_key: 1` in the telemetry reader | — | 1 `failed to get config` | telemetry-key errors caught |
| A with `exporters: [elasticsearch/bogus]` | — | 1 `failed to get config` | unknown component caught |

**Blind spot, stated:** the 0.164.0 plan measured that unknown keys under an ES exporter were NOT caught. 0.165.0
evidently does catch them (it rejected `mapping.mode`), so the earlier "ES exporter unknown keys NOT caught" caveat does not
apply to this binary; section 4.1/4.2 still gate on contents, not on validate.

### 1.3b Startup rehearsal on the real 0.165.0 binary (not just `validate`)

`validate` does not start the pipeline. 2026-11-08: the same release binary was STARTED for 15 s with candidate A (endpoint
pointed through a read-only `kubectl port-forward` at the LIVE Elasticsearch, loopback ports, a scratch queue directory; no
producer pointed at it, so nothing was sent). New gate function (section 2.3(c)):

| run | `Everything is ready` | fatal | `Connected to Elasticsearch` | 401/403 | verdict |
|---|---|---|---|---|---|
| candidate A, real `ES_PASSWORD` | 1 | 0 | **3** (`version 8.19.20`) | **0** | `STARTUP_OK` (+ 4 double-batching warns) |
| candidate A, dummy password | 1 | 0 | 0 | 3 | `STARTUP_FAIL` (negative control: the auth probe really is authenticated) |
| `num_consumers: notanint` | 0 | 1 | 0 | 0 | `STARTUP_FAIL`, exit 1 |
| empty log | 0 | 0 | 0 | 0 | `STARTUP_FAIL` |

The gate therefore requires `Connected to Elasticsearch` = 3 and 401/403 = 0 — the exact inverse of the 0.164.0 gate, which
would have auto-reverted a healthy 0.165.0.

### 1.4 Measured baselines (2026-11-08, window agent re-measures in section 2.4)

Log records sent [15m] 24,016 (7d min of the same expression 16,555); metric points [15m] 1,881,004; `docs.processed`
success [15m] 816,242, no non-success outcome; `dropping cumulative temporality` 60 per 15 min, 246 in the last hour
(F-76387378, pre-existing, the reason string carries the new suffix after the roll); ES `8.19.20 green`;
`target_info` `service.version=0.164.0` count 1; ES `_count` last 10 min: logs 17,106, metrics 527,805; kmsg
over 1 h: `.11` 668 / `.12` 28 / `.13` 25 (`.11` is the chatty node), `scope.name` present on 721 of them; histogram documents
of `workqueue_queue_duration_seconds` in the last 30 min: 540, **none** with `temporality`.

### 1.5 Why `risk: medium`

One replica is the only OTLP path into Elasticsearch for every namespace and the Talos kmsg sink on `192.168.55.18`, where
**a collector restart is the documented trigger for a per-node kmsg-sender stall**
(docs/troubleshooting/node-reboot-observability.md). Its failure is silent: pod Ready, health 200, telemetry gone. The
changelog-invisible config break is the kind of surprise this plan exists to remove, and it is removed only if the edit lands
in the SAME commit as the image.

## 2) Pre-checks

Run in order. Any failure stops the plan; do not go on to section 3. All temp files live in
`/private/tmp/claude-501/edot-0165/` (created by the first block).

```bash
cd /Users/mu/code/cberg-home-nextgen
mkdir -p /private/tmp/claude-501/edot-0165
# 2.1 — premises (re-run mechanically)
.venv/bin/python3 runbooks/plan-premises.py edot-collector-0.165.0 --require-premises
# PASS: all six premises PASS, no REFUSED line.
# If ONLY image-is-still-0.164.0 fails and prints ...:0.165.0 -> PR #500 was merged alone: STOP, section 6 "PR #500 merged alone".

# 2.1b — the instrument and the producers must not have moved in the last 6 hours (tonight's Step 0 batch).
git fetch origin main
git log --since='6 hours ago' --format='%h %s' origin/main -- \
  kubernetes/apps/monitoring/kube-prometheus-stack kubernetes/apps/monitoring/otel-operator \
  kubernetes/apps/monitoring/elasticsearch kubernetes/apps/monitoring/eck-operator
gh pr list --state open --json number,title -q '.[]|"\(.number) \(.title)"' | grep -iE 'prometheus-stack|opentelemetry-kube-stack|otel-operator|flux'
# PASS (first command): prints NOTHING (path-scoped on purpose: a subject grep for "eck" matches every "pre-check" commit).
# FAILS AS: any commit line, e.g. a kube-prometheus-stack bump (#501 major 92.11.1 -> 93.1.0 and #428 92.11.1 -> 92.22.0
#   are open, unplanned and held by a time-boxed deny rule), or an opentelemetry-kube-stack bump (0.27.0 landed 2026-11-07,
#   eee6e16c5; its daemon collectors are 23 h old and healthy) -> STOP, reslot.
# SECOND command is informational: it lists the open PRs that must not merge tonight (measured 2026-11-08: #501, #471 flux2 CLI pin, #428). A listed PR that Step 0 merged since the first command ran shows up in the first command.

# 2.2 — HARD GATE: PR #500 still targets 0.165.0, and the multi-arch tag exists with the digest measured at planning time.
gh pr view 500 --json state,title -q '.state+" "+.title'
# PASS: "OPEN feat(container): update otel/opentelemetry-collector-contrib ( 0.164.0 → 0.165.0 )"
# FAILS AS: MERGED/CLOSED or a different target in the title -> STOP (retarget = refresh this plan in place, README
#   "When the held target MOVES"). mergeable may read UNKNOWN or MERGEABLE; it is irrelevant because section 3 does NOT merge it.
T=$(curl -s "https://auth.docker.io/token?service=registry.docker.io&scope=repository:otel/opentelemetry-collector-contrib:pull" | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
curl -s -D /private/tmp/claude-501/edot-0165/hdr.txt -o /private/tmp/claude-501/edot-0165/manifest.json \
  -H "Authorization: Bearer $T" \
  -H "Accept: application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.list.v2+json" \
  https://registry-1.docker.io/v2/otel/opentelemetry-collector-contrib/manifests/0.165.0
python3 - <<'EOF'
import json,re
d='/private/tmp/claude-501/edot-0165/'
h=open(d+'hdr.txt').read()
st=re.search(r'^HTTP/\S+ (\d+)',h,re.M).group(1)
dg=(re.search(r'(?im)^docker-content-digest:\s*(\S+)',h) or [None,None])[1]
if st!='200': print('TAG_MISSING http',st,'-> BLOCKED'); raise SystemExit
m=json.load(open(d+'manifest.json'))
plats=[(x['platform']['os'],x['platform']['architecture']) for x in m.get('manifests',[])]
ok=('linux','amd64') in plats
print('TAG_OK' if ok else 'NO_AMD64', dg, plats)
if ok: open(d+'target-digest','w').write(dg)
EOF
cat /private/tmp/claude-501/edot-0165/target-digest; echo
# PASS: `TAG_OK sha256:e40d61f10c9a617cca1ffd1be4d7e2b3a4b0f0001798ff07e58cabe82e618cea [... ('linux','amd64') ...]` — exactly this
#   digest (measured 2026-11-08). A DIFFERENT digest = upstream re-pushed the tag -> STOP and re-read the release.
# CAN FAIL — demonstrated 2026-11-08 with the same request on tags 0.165.1 and 0.166.0: HTTP 404 -> `TAG_MISSING http 404`.

# 2.3 — GATE: validate the CANDIDATE config (live config with the three mapping blocks removed) against the NEW binary,
# and prove the UNEDITED live config FAILS on it (that failure is the reason for this plan).
D=/private/tmp/claude-501/edot-0165; cd $D
gh release download v0.165.0 -R open-telemetry/opentelemetry-collector-releases -p 'otelcol-contrib_0.165.0_darwin_arm64.tar.gz' --clobber
shasum -a 256 otelcol-contrib_0.165.0_darwin_arm64.tar.gz
tar xzf otelcol-contrib_0.165.0_darwin_arm64.tar.gz otelcol-contrib
./otelcol-contrib --version                        # MUST print: otelcol-contrib version 0.165.0
kubectl get cm -n monitoring edot-collector-config -o jsonpath='{.data.otel\.yml}' > live-otel.yml
# candidate = what section 3 step 2 will commit, rendered the way Flux renders it ($$ -> $), taken from a SCRATCH COPY of the repo file:
cp /Users/mu/code/cberg-home-nextgen/kubernetes/apps/monitoring/edot-collector/app/configmap.yaml scratch-configmap.yaml
python3 - <<'EOF'
import yaml
t=open('scratch-configmap.yaml').read()
old="        mapping:\n          mode: otel\n"
assert t.count(old)==3, t.count(old)
open('scratch-configmap.yaml','w').write(t.replace(old,""))
open('candidate.yml','w').write(yaml.safe_load(open('scratch-configmap.yaml'))['data']['otel.yml'].replace('$${','${'))
print('candidate rendered')
EOF
ES_PASSWORD=dummy ./otelcol-contrib validate --config=live-otel.yml  > before.out 2>&1; echo "UNEDITED live config exit=$?"; grep -c "'mapping' has invalid keys: mode" before.out
ES_PASSWORD=dummy ./otelcol-contrib validate --config=candidate.yml  > pos.out 2>&1;    echo "candidate exit=$?"; cat pos.out
# NEGATIVE CONTROLS on the candidate — each must exit NON-zero:
python3 -c "t=open('candidate.yml').read();assert 'num_consumers: 4' in t;open('neg1.yml','w').write(t.replace('num_consumers: 4','num_consumers: notanint',1))"
python3 -c "t=open('candidate.yml').read();assert 'IsMap(log.body)' in t;open('neg2.yml','w').write(t.replace('IsMap(log.body)','IsMapp(log.body)',1))"
python3 -c "t=open('candidate.yml').read();assert 'without_scope_info: false' in t;open('neg3.yml','w').write(t.replace('without_scope_info: false','without_scope_info: false\n                bogus_key: 1',1))"
for n in neg1 neg2 neg3; do ES_PASSWORD=dummy ./otelcol-contrib validate --config=$n.yml > $n.out 2>&1; echo "$n exit=$? $(grep -m1 -oE 'cannot unmarshal|unable to parse OTTL statement|bogus_key|failed to get config' $n.out)"; done
cd /Users/mu/code/cberg-home-nextgen
# PASS: `UNEDITED live config exit=1` and the grep prints 1; `candidate exit=0` with EMPTY output; neg1/neg2/neg3 all `exit=1`
#   (measured 2026-11-08: neg1 `cannot unmarshal`, neg2 `unable to parse OTTL statement`, neg3 `failed to get config`).
# FAILS AS: unedited exit 0 -> the break is gone (upstream or config changed): STOP and re-read section 1.2 before doing anything;
#   candidate non-zero -> BLOCKED (a different config problem = a different plan); a negative control that exits 0 -> the
#   gate cannot fail, STOP.

# (b) in-cluster with the linux image that will actually run (only after 2.2 passed). Creates two short-lived objects in
# monitoring (a ConfigMap holding the candidate, and a pod); both are deleted by the function. monitoring is PSA privileged.
edot_validate() {  # $1 = pod name, $2 = ConfigMap to mount at /config
  local IMG=otel/opentelemetry-collector-contrib:0.165.0 OV PH
  OV='{"spec":{"securityContext":{"runAsNonRoot":true,"runAsUser":10001,"runAsGroup":10001},"containers":[{"name":"'"$1"'","image":"'"$IMG"'","command":["/otelcol-contrib","validate","--config=/config/otel.yml"],"env":[{"name":"ES_PASSWORD","value":"dummy-validate-only"}],"volumeMounts":[{"name":"cfg","mountPath":"/config","readOnly":true}]}],"volumes":[{"name":"cfg","configMap":{"name":"'"$2"'"}}]}}'
  kubectl delete pod -n monitoring "$1" --ignore-not-found >/dev/null
  kubectl run "$1" -n monitoring --restart=Never --image="$IMG" --overrides="$OV" >/dev/null
  for i in $(seq 1 60); do
    PH=$(kubectl get pod -n monitoring "$1" -o jsonpath='{.status.phase}')
    case "$PH" in Succeeded|Failed) break ;; esac
    sleep 3
  done
  case "$PH" in Succeeded|Failed) ;; *) echo "NOT_TERMINAL phase=$PH -> STOP; pod $1 left for: kubectl describe pod -n monitoring $1"; return 1 ;; esac
  echo "phase=$PH exitCode=$(kubectl get pod -n monitoring "$1" -o jsonpath='{.status.containerStatuses[0].state.terminated.exitCode}')"
  kubectl logs -n monitoring "$1" > "/private/tmp/claude-501/edot-0165/$1.out" 2>&1
  cat "/private/tmp/claude-501/edot-0165/$1.out"
  kubectl delete pod -n monitoring "$1" --ignore-not-found >/dev/null
}
kubectl create configmap edot-validate-cfg-01650 -n monitoring --from-file=otel.yml=/private/tmp/claude-501/edot-0165/candidate.yml
edot_validate edot-validate-01650     edot-validate-cfg-01650     # candidate: must pass
edot_validate edot-validate-01650-neg edot-collector-config       # the LIVE unedited config: must FAIL with the real reason
grep -ic "'mapping' has invalid keys: mode" /private/tmp/claude-501/edot-0165/edot-validate-01650-neg.out
kubectl delete configmap edot-validate-cfg-01650 -n monitoring --ignore-not-found
# PASS (positive): `phase=Succeeded exitCode=0` and the log is EMPTY. PASS (negative control): `phase=Failed`, exitCode 1 AND the
#   grep prints >= 1 (the exact mapping::mode error from the linux image). A non-zero exit WITHOUT that text means the pod failed for
#   another reason (pull, admission, arch) — investigate.
# FAILS AS: positive pod Failed / error text -> BLOCKED. NOT_TERMINAL after 180 s = pull or volume problem -> STOP, describe,
#   delete the pod and the ConfigMap by hand. "exec format error" = wrong arch -> STOP.
# (NOT run by the planner: a planner creates no cluster object. The local result in 1.3 is the planning-time evidence.)

# (c) STARTUP-LOG GATE rehearsal on the REAL 0.165.0 binary against the LIVE Elasticsearch (read-only port-forward, scratch queue
# dir, no producer points at it so nothing is sent). The REAL password is used on purpose: the new auth probe needs it.
cat > /private/tmp/claude-501/edot-0165/startup-gate.sh <<'EOF'
edot_startup_gate() {  # $1 = captured log of the NEW container's startup
  local N BAD C U
  N=$(grep -c 'Everything is ready. Begin running and processing data.' "$1")
  BAD=$(grep -ciE '^Error:|failed to get config|panic|invalid configuration|exec format|invalid keys' "$1")
  C=$(grep -c 'Connected to Elasticsearch' "$1")
  U=$(grep -c 'es info returned status 40[13]' "$1")
  echo "ready_lines=$N fatal_lines=$BAD es_connected=$C es_info_401_403=$U es_info_other=$(grep 'failed to fetch Elasticsearch info' "$1" | grep -vc 'status 40[13]') double_batching_warn=$(grep -c 'double batching' "$1")"
  if [ "$N" = 1 ] && [ "$BAD" = 0 ] && [ "$C" = 3 ] && [ "$U" = 0 ]; then echo STARTUP_OK; else echo STARTUP_FAIL; fi
}
EOF
. /private/tmp/claude-501/edot-0165/startup-gate.sh
cd /private/tmp/claude-501/edot-0165
python3 - <<'EOF'
import os
t=open('candidate.yml').read()
for a,b in [('https://elasticsearch-es-http.monitoring.svc:9200','https://localhost:19211'),
            ('/var/lib/otelcol/sending-queue',os.getcwd()+'/queue'),
            ('0.0.0.0:13133','127.0.0.1:23133'),('0.0.0.0:4317','127.0.0.1:24317'),
            ('0.0.0.0:4318','127.0.0.1:24318'),('0.0.0.0:5171','127.0.0.1:25171'),
            ('0.0.0.0:8889','127.0.0.1:28889'),
            ('host: 0.0.0.0\n                port: 8888','host: 127.0.0.1\n                port: 28888')]:
    assert a in t, 'config moved: '+a
    t=t.replace(a,b)
open('scratch.yml','w').write(t)
n=t.replace('num_consumers: 4','num_consumers: notanint',1); assert n!=t
open('scratch-neg.yml','w').write(n)
EOF
ES_PW=$(kubectl get secret -n monitoring elasticsearch-es-elastic-user -o jsonpath='{.data.elastic}' | base64 -d)
rm -rf queue
kubectl port-forward -n monitoring svc/elasticsearch-es-http 19211:9200 >/dev/null 2>&1 & PF=$!
sleep 4
ES_PASSWORD="$ES_PW" ./otelcol-contrib --config=scratch.yml > start-real.log 2>&1 & CP=$!
sleep 15; kill -TERM $CP; wait $CP 2>/dev/null
rm -rf queue
ES_PASSWORD=dummy ./otelcol-contrib --config=scratch.yml > start-dummy.log 2>&1 & CP=$!
sleep 15; kill -TERM $CP; wait $CP 2>/dev/null
ES_PASSWORD=dummy ./otelcol-contrib --config=scratch-neg.yml > start-neg.log 2>&1; echo "neg exit=$?"
kill $PF 2>/dev/null
echo "--- real password";  edot_startup_gate start-real.log
echo "--- dummy password (must FAIL)"; edot_startup_gate start-dummy.log
echo "--- num_consumers notanint (must FAIL)"; edot_startup_gate start-neg.log
: > start-empty.log; echo "--- empty log (must FAIL)"; edot_startup_gate start-empty.log
unset ES_PW; rm -rf queue
cd /Users/mu/code/cberg-home-nextgen
# PASS: real = `ready_lines=1 fatal_lines=0 es_connected=3 es_info_401_403=0 ... double_batching_warn=4` STARTUP_OK; the other three STARTUP_FAIL.
#   If a negative prints STARTUP_OK the gate cannot fail: STOP. Local port 19211 must be free (this is the same port section 4.3 uses).
# FAILS AS: real STARTUP_FAIL (config rejected at start, ES unreachable, or the probe is still unauthenticated) -> BLOCKED.
#   MEASURED 2026-11-08 (zsh, real binary, live ES): real `ready_lines=1 fatal_lines=0 es_connected=3 es_info_401_403=0 es_info_other=0
#   double_batching_warn=4` STARTUP_OK; dummy `es_connected=0 es_info_401_403=3` STARTUP_FAIL; notanint `ready_lines=0 fatal_lines=1`
#   STARTUP_FAIL; empty STARTUP_FAIL.

# 2.4 — BASELINES for section 4, each over the SAME window its gate uses. Reference values (yours will differ):
#   sent log records [15m] 24,016 (7d min 16,555) | sent metric points [15m] 1,881,004 | docs.processed success [15m] 816,242,
#   non-success [15m] EMPTY | `dropping cumulative temporality` 60 per 15 min.
P=/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query
kubectl get --raw "${P}?query=sum(increase(otelcol_exporter_sent_log_records_total[15m]))"; echo
kubectl get --raw "${P}?query=sum(increase(otelcol_exporter_sent_metric_points_total[15m]))"; echo      # record as MP_BASE
kubectl get --raw "${P}?query=sum%20by%20(outcome)%20(increase(%7B__name__%3D%22otelcol.elasticsearch.docs.processed_total%22%7D%5B15m%5D))"; echo
kubectl logs -n monitoring deploy/edot-collector --since=15m | grep -c 'dropping cumulative temporality'      # record as DROP_BASE (per 15 min)
kubectl logs -n monitoring deploy/edot-collector --since=1h | grep -oE "dropping [a-z]+ [a-z]+|invalid number data point" | sort | uniq -c
# PRE-EXISTING baseline, NOT this plan's (F-76387378): the same reason string only. A NEW reason string after the roll is a regression candidate.

# 2.4b — PRE-ROLL ES CONTROL (content-based, BEFORE section 3; the pipeline fails silently).
ES_PW=$(kubectl get secret -n monitoring elasticsearch-es-elastic-user -o jsonpath='{.data.elastic}' | base64 -d)
kubectl port-forward -n monitoring svc/elasticsearch-es-http 19211:9200 >/dev/null 2>&1 & PF=$!
sleep 4
for DS in logs-generic-default metrics-generic.otel-default; do
  echo -n "PRE $DS last10m="
  curl -k -s -u "elastic:$ES_PW" -H 'Content-Type: application/json' -X POST "https://localhost:19211/$DS/_count" \
    -d '{"query":{"range":{"@timestamp":{"gte":"now-10m"}}}}' \
    | python3 -c "import sys,json;c=json.load(sys.stdin).get('count');print(c,'PRE_OK' if isinstance(c,int) and c>0 else 'PRE_FAIL')"
done
curl -k -s -u "elastic:$ES_PW" -H 'Content-Type: application/json' "https://localhost:19211/logs-generic-default/_search" \
  -d '{"size":0,"query":{"bool":{"filter":[{"term":{"attributes.log_source":"talos-kernel"}},{"range":{"@timestamp":{"gte":"now-1h"}}}]}},"aggs":{"ip":{"terms":{"field":"attributes.net.peer.ip","size":5}}}}' \
  | python3 -c "import sys,json;b={x['key']:x['doc_count'] for x in json.load(sys.stdin)['aggregations']['ip']['buckets']};print('PRE kmsg 1h',b,'PRE_KMSG_OK' if all(b.get(n,0)>0 for n in ('192.168.55.11','192.168.55.12','192.168.55.13')) else 'PRE_KMSG_FAIL')"
echo -n "PRE negative control (future window, MUST be 0): "
curl -k -s -u "elastic:$ES_PW" -H 'Content-Type: application/json' -X POST "https://localhost:19211/logs-generic-default/_count" \
  -d '{"query":{"range":{"@timestamp":{"gte":"now+1h"}}}}' | python3 -c "import sys,json;print(json.load(sys.stdin).get('count'))"
# the temporality helper (also used by section 4.3). Pre-roll it MUST print TEMPORALITY_MISSING + PRE_ROLL_CONTROL_OK:
cat > /private/tmp/claude-501/edot-0165/temporality.sh <<'EOF'
edot_temporality() {  # $1 = READY_TS (ISO). Needs ES_PW and a port-forward on 19211.
  local Q='{"size":50,"sort":[{"@timestamp":"desc"}],"_source":["@timestamp","temporality"],"query":{"bool":{"filter":[{"exists":{"field":"metrics.workqueue_queue_duration_seconds"}},{"range":{"@timestamp":RANGE}}]}}}'
  local W B
  W=$(curl -k -s -u "elastic:$ES_PW" -H 'Content-Type: application/json' "https://localhost:19211/metrics-generic.otel-default/_search" -d "${Q/RANGE/{\"gte\":\"$1\"\}}")
  B=$(curl -k -s -u "elastic:$ES_PW" -H 'Content-Type: application/json' "https://localhost:19211/metrics-generic.otel-default/_search" -d "${Q/RANGE/{\"gte\":\"$1||-22m\",\"lt\":\"$1||-2m\"\}}")
  python3 -c "
import sys,json
w=json.loads(sys.argv[1])['hits']['hits']; b=json.loads(sys.argv[2])['hits']['hits']
tw=[h['_source'].get('temporality') for h in w]; tb=[h['_source'].get('temporality') for h in b]
print('after-ready docs',len(w),'temporality values',sorted(set(map(str,tw))),'| before-ready docs',len(b),'temporality values',sorted(set(map(str,tb))))
ok = len(w)>0 and all(x=='delta' for x in tw)
ctl = len(b)>0 and all(x is None for x in tb)
print('TEMPORALITY_OK' if ok else 'TEMPORALITY_MISSING', 'PRE_ROLL_CONTROL_OK' if ctl else 'PRE_ROLL_CONTROL_BAD')" "$W" "$B"
}
EOF
. /private/tmp/claude-501/edot-0165/temporality.sh
edot_temporality "$(python3 -c "from datetime import *;print((datetime.now(timezone.utc)-timedelta(minutes=5)).strftime('%Y-%m-%dT%H:%M:%SZ'))")"
kill $PF 2>/dev/null; unset ES_PW
# PASS: both streams PRE_OK (count > 0), PRE_KMSG_OK, the future-window control prints 0, and edot_temporality prints
#   `TEMPORALITY_MISSING PRE_ROLL_CONTROL_OK` (every document of the 0.164.0 pod lacks the field — measured 2026-11-08: 50 and 50 docs,
#   values ['None']).
# FAILS AS: PRE_FAIL / count 0 / 401 (ES unreachable or ingestion ALREADY dead) -> STOP, do not roll. `TEMPORALITY_OK` here means
#   something other than 0.164.0 is already sending -> STOP. PRE_ROLL_CONTROL_BAD = the before-window is empty or already has the
#   field, so the section 4.3 control cannot discriminate -> STOP.

# 2.5 — pre-state is clean
kubectl get pods -n monitoring -l app=edot-collector -o wide
kubectl get pvc -n monitoring edot-collector-queue
kubectl get ds -n monitoring kmsg-heartbeat
kubectl get deploy -n kube-system reloader
flux get kustomizations -n monitoring | awk 'NR==1 || $4 != "True"'
# PASS: collector 1/1 Running, PVC Bound, DaemonSet 3/3, reloader 1/1 (it is what turns the configmap edit into a roll), no
#   kustomization off True.
```

## 3) Steps (GitOps)

**1. Silence expected rollout noise and mark the update active.** Every alertname below exists in
`kubernetes/apps/monitoring/kube-prometheus-stack/app/otel-collector-alerts.yaml` (they are the ones the 0.164.0 plan used;
re-check with `grep -c <name> <file>` if the file moved). Deliberately NOT silenced: the three `Es*ExporterSeriesMissing`
absent() guards, `TalosKmsgPipelineDown`, `TalosKernelLogsMissingFromNode` — a real disappearance or a stalled kmsg sender must
still page.

```bash
for A in EdotCollectorDown OtelCollectorExportFailed OtelCollectorRecordsRefused OtelCollectorQueueFull EdotCollectorESAuthError EsMetricsIngestionStalled EsLogIngestionStalled EsExportQueueStuckFull; do
  echo -n "$A "; grep -c "alert: $A" kubernetes/apps/monitoring/kube-prometheus-stack/app/otel-collector-alerts.yaml
done      # every line must end in 1 (all eight measured 1 on 2026-11-08; a nonexistent name prints 0, so the loop can fail); a 0 = the name moved, fix the silence regex
kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 >/dev/null 2>&1 & PF=$!
sleep 3
NOW=$(python3 -c "from datetime import *;print(datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
END=$(python3 -c "from datetime import *;print((datetime.now(timezone.utc)+timedelta(hours=3)).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
curl -s -X POST localhost:9093/api/v2/silences -H 'Content-Type: application/json' -d '{
  "matchers":[{"name":"namespace","value":"monitoring","isRegex":false,"isEqual":true},
              {"name":"alertname","value":"EdotCollectorDown|OtelCollectorExportFailed|OtelCollectorRecordsRefused|OtelCollectorQueueFull|EdotCollectorESAuthError|EsMetricsIngestionStalled|EsLogIngestionStalled|EsExportQueueStuckFull","isRegex":true,"isEqual":true}],
  "startsAt":"'"$NOW"'","endsAt":"'"$END"'","createdBy":"maintenance-window-agent",
  "comment":"edot-collector 0.164.0->0.165.0 - expected rollout noise. auto-expires 3h"}' \
  | tee /private/tmp/claude-501/edot-0165/silence.json; echo   # prints {"silenceID":"..."}; empty = NOT silenced
kill $PF 2>/dev/null
runbooks/update-marker.sh add edot-collector monitoring 3 "0.164.0->0.165.0 bump"
```

**2. ONE commit: the image bump AND the config edit.** Do NOT `gh pr merge 500` (section 1.2). The python edit asserts the
anchor counts so a moved file STOPs instead of silently half-applying. DRY-TESTED 2026-11-08 on scratch copies of the real files
(macOS, python3; no sed involved), producing exactly these diff lines:

```
# configmap.yaml (3 hunks)
255,256d254   <         mapping:
              <           mode: otel
291,292d288   <         mapping:
              <           mode: otel
327,328d322   <         mapping:
              <           mode: otel
# deployment.yaml (1 hunk)
40c40  <           image: otel/opentelemetry-collector-contrib:0.164.0
       >           image: otel/opentelemetry-collector-contrib:0.165.0
```

```bash
cd /Users/mu/code/cberg-home-nextgen
git fetch origin main && git merge --ff-only origin/main
CM=kubernetes/apps/monitoring/edot-collector/app/configmap.yaml
DP=kubernetes/apps/monitoring/edot-collector/app/deployment.yaml
python3 - "$CM" "$DP" <<'EOF'
import sys
cm,dp=sys.argv[1],sys.argv[2]
t=open(cm).read()
old="        mapping:\n          mode: otel\n"
assert t.count(old)==3, "mapping-mode blocks != 3: %d -> STOP" % t.count(old)
open(cm,'w').write(t.replace(old,""))
t=open(dp).read()
o="image: otel/opentelemetry-collector-contrib:0.164.0\n"
assert t.count(o)==1, "image anchor != 1 -> STOP"
open(dp,'w').write(t.replace(o,"image: otel/opentelemetry-collector-contrib:0.165.0\n"))
print("edited")
EOF
git diff --stat -- "$CM" "$DP"       # MUST be exactly 2 files: 6 deletions in configmap.yaml, 1 line changed in deployment.yaml
# byte-check: the file we are about to commit renders to the candidate that section 2.3 validated
python3 - <<'EOF'
import yaml
t=yaml.safe_load(open('kubernetes/apps/monitoring/edot-collector/app/configmap.yaml'))['data']['otel.yml'].replace('$${','${')
c=open('/private/tmp/claude-501/edot-0165/candidate.yml').read()
print('RENDER_MATCHES_VALIDATED_CANDIDATE' if t==c else 'RENDER_DIFFERS -> STOP')
EOF
MSG=/private/tmp/claude-501/edot-0165/msg-$(date +%s).txt
printf '%s\n' "feat(container): update otel/opentelemetry-collector-contrib ( 0.164.0 → 0.165.0 ) + drop removed mapping::mode (plan edot-collector-0.165.0)" "" "0.165.0 removed exporter/elasticsearch mapping::mode (ignored since 0.145.0, default is otel); the unedited config fails validate on the new binary. Supersedes PR #500." > "$MSG"
git commit --only "$CM" "$DP" -F "$MSG"
git show --stat HEAD       # exactly the two files above
git log -1 --format=%s     # MUST be your subject; amend before pushing if not (concurrent sessions swap messages)
git rev-parse HEAD > /private/tmp/claude-501/edot-0165/bump-sha
git push origin main
gh pr close 500 --comment "Superseded: image bump landed with the required config edit in $(git rev-parse --short HEAD) (plan edot-collector-0.165.0). Merging this PR alone would crash-loop the collector (mapping::mode removed upstream)."
```

**3. Reconcile and WAIT UNTIL SETTLED.** The Flux Kustomization lives in namespace **`monitoring`**; `-n flux-system` errors and
`rollout status` then green-lights the OLD generation. The Deployment carries `reloader.stakater.com/auto: "true"` and the commit
changes a mounted ConfigMap AND the image, so Flux rolls the pod once and Reloader may patch the template and roll it AGAIN
within a minute: do not take the first Ready as final. `strategy: Recreate` is load-bearing (RWO Longhorn PVC at `replicas: 1`);
do not hand-delete pods mid-roll.

```bash
flux reconcile kustomization edot-collector -n monitoring --with-source
cat > /private/tmp/claude-501/edot-0165/settle.sh <<'EOF'
edot_settle() {  # waits until no generation is pending, ONE Ready pod exists and it has been the same pod for 90 s
  local last="" same=0 i G O R P
  for i in $(seq 1 90); do
    G=$(kubectl get deploy edot-collector -n monitoring -o jsonpath='{.metadata.generation}')
    O=$(kubectl get deploy edot-collector -n monitoring -o jsonpath='{.status.observedGeneration}')
    R=$(kubectl get deploy edot-collector -n monitoring -o jsonpath='{.status.readyReplicas}')
    P=$(kubectl get pods -n monitoring -l app=edot-collector -o name | tr '\n' ' ')
    if [ "$G" = "$O" ] && [ "$R" = 1 ] && [ "$(echo "$P" | wc -w | tr -d ' ')" = 1 ] && [ "$P" = "$last" ]; then same=$((same+1)); else same=0; fi
    last="$P"
    if [ "$same" -ge 9 ]; then echo "SETTLED gen=$G pod=$P"; return 0; fi
    sleep 10
  done
  echo "NOT_SETTLED gen=$G observed=$O ready=$R pods=$P"; return 1
}
EOF
. /private/tmp/claude-501/edot-0165/settle.sh
kubectl get deployment edot-collector -n monitoring -o jsonpath='{.spec.template.spec.containers[0].image}'; echo
edot_settle
kubectl get pods -n monitoring -l app=edot-collector -o wide
kubectl get pods -n monitoring -l app=edot-collector \
  -o jsonpath='{.items[0].status.conditions[?(@.type=="Ready")].lastTransitionTime}' \
  > /private/tmp/claude-501/edot-0165/ready-ts
cat /private/tmp/claude-501/edot-0165/ready-ts; echo   # MUST be non-empty and AFTER the push
```

**HARD GATE:** the printed image reads `:0.165.0`, `edot_settle` prints `SETTLED` (it ran live against the current 0.164.0
pod on 2026-11-08 and printed `SETTLED gen=59 pod=pod/edot-collector-857f67ff59-2hlh8`; with the pod selector pointed at a label
that matches nothing it printed `NOT_SETTLED ... pods=`, so it can fail), and exactly one pod is `1/1 Running`. If it prints
`NOT_SETTLED`, or the pod is `CrashLoopBackOff` / `Error`, go to section 5.1 NOW (read `kubectl logs --previous` first; an
`invalid keys` line means the edit did not reach the pod). Do not continue into section 4, whose gates would all pass on the old
binary.

**4. Read the startup log NOW** (startup lines rotate out; this is section 4.0's gate input).

```bash
kubectl logs -n monitoring deploy/edot-collector > /private/tmp/claude-501/edot-0165/startup.log
. /private/tmp/claude-501/edot-0165/startup-gate.sh   # written by section 2.3(c); re-create it from there on a new shell/host
edot_startup_gate /private/tmp/claude-501/edot-0165/startup.log
kubectl get pods -n monitoring -l app=edot-collector -o jsonpath='{.items[0].status.containerStatuses[0].restartCount}'; echo
```

**HARD GATE:** `STARTUP_OK` (exactly one `Everything is ready. Begin running and processing data.`, no
`Error:`/`failed to get config`/`panic`/`invalid configuration`/`invalid keys`/`exec format` line, THREE `Connected to
Elasticsearch ... version 8.19.20`, ZERO `es info returned status 401/403`) AND `restartCount` `0`. **EXPECTED, informational,
NOT a failure:** four `warn` lines `Pipeline has both a batch processor and an exporter with batching enabled` (section 1.2). A
`status 401` here would mean the new binary's probe is unauthenticated again (not what v0.165.0 does) or the ES password drifted:
section 4.2/4.3 then decide. `kubectl logs` shows only the CURRENT container, so a crash-looping pod can still print one ready
line — the restart count is the other half.

**5. Kick the kmsg heartbeat (second commit, ONLY after step 3's hard gate).** `kmsg-heartbeat` writes one
`cberg-kmsg-heartbeat node=<node>` line into each node's kernel ring buffer when its pod starts, then hourly. The CURRENT
annotation is `cberg.dev/kmsg-heartbeat-kick: "2026-11-06T1233"` (measured), so the anchor line below is the existing annotation, NOT
the label as in the 0.164.0 plan. DRY-TESTED 2026-11-08 with macOS BSD tooling on a scratch copy of the real file:

```bash
REV="$(date -u +%Y-%m-%dT%H%M)"
python3 - "$REV" <<'EOF'
import sys,re
p='kubernetes/apps/monitoring/edot-collector/app/kmsg-heartbeat-daemonset.yaml'
t=open(p).read()
pat=re.compile(r'(        cberg\.dev/kmsg-heartbeat-kick: )"[^"]*"\n')
assert len(pat.findall(t))==1, "kick annotation anchor != 1 -> STOP"
open(p,'w').write(pat.sub(lambda m: m.group(1)+'"'+sys.argv[1]+'"\n', t))
EOF
git diff kubernetes/apps/monitoring/edot-collector/app/kmsg-heartbeat-daemonset.yaml
```

The diff MUST be exactly one changed line (`-        cberg.dev/kmsg-heartbeat-kick: "2026-11-06T1233"` /
`+        cberg.dev/kmsg-heartbeat-kick: "<REV>"`). Zero hunks or two: STOP and edit by hand.

```bash
git fetch origin main && git merge --ff-only origin/main
MSG=/private/tmp/claude-501/edot-0165/msg-kick-$(date +%s).txt
printf '%s\n' "chore(monitoring): kick kmsg-heartbeat after edot-collector 0.165.0 roll (plan edot-collector-0.165.0)" > "$MSG"
git commit --only kubernetes/apps/monitoring/edot-collector/app/kmsg-heartbeat-daemonset.yaml -F "$MSG"
git show --stat HEAD       # exactly one file: kmsg-heartbeat-daemonset.yaml
git log -1 --format=%s     # MUST be your subject; amend before pushing if not
git push origin main
flux reconcile kustomization edot-collector -n monitoring --with-source
kubectl rollout status ds/kmsg-heartbeat -n monitoring --timeout=180s
kubectl get pods -n monitoring -l app.kubernetes.io/name=kmsg-heartbeat -o wide
# PASS: 3 pods, all with a fresh AGE, one per node.
```

**6. Wait 15 minutes** after the Ready timestamp from step 3 (the file holds the LAST pod's), so every `[15m]` window in
section 4 lies entirely after the new pod's start. A straddling window passes on pre-roll data.

## 4) Verification

### 4.0 Floor + the new binary is really serving

CONTROL: metric target_info — `count(target_info{job="edot-collector","service.version"="0.165.0"})` must be 1

```bash
kubectl get deployment edot-collector -n monitoring -o jsonpath='{.status.readyReplicas}'; echo
TARGET_DIGEST=$(cat /private/tmp/claude-501/edot-0165/target-digest)
test -n "$TARGET_DIGEST" || echo "NO_TARGET_DIGEST -> FAIL"
LIVE_ID=$(kubectl get pods -n monitoring -l app=edot-collector -o jsonpath='{.items[0].status.containerStatuses[0].imageID}')
echo "live: $LIVE_ID"
case "$LIVE_ID" in *"$TARGET_DIGEST") echo "DIGEST_OK" ;; *) echo "DIGEST_MISMATCH" ;; esac
P=/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query
for v in 0.165.0 0.164.0; do
  Q='count(target_info{job="edot-collector","service.version"="'$v'"})'
  E=$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))" "$Q")
  echo -n "service.version=$v: "
  kubectl get --raw "${P}?query=${E}" | python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];print(r[0]['value'][1] if r else 'EMPTY')"
done
. /private/tmp/claude-501/edot-0165/startup-gate.sh
edot_startup_gate /private/tmp/claude-501/edot-0165/startup.log
kubectl get pods -n monitoring -l app=edot-collector -o jsonpath='restartCount={.items[0].status.containerStatuses[0].restartCount}'; echo
```

**PASS (all gating):** `readyReplicas` 1 and `DIGEST_OK` (imageID carries the manifest-list digest; today's 0.164.0 pod shows
`...@sha256:340c9ca6...522b`); `service.version=0.165.0: 1` (the `0.164.0` line may read 1 inside the 5-min staleness window, must
read `EMPTY` by T+15m); `STARTUP_OK` and `restartCount=0`.

**Both sides demonstrated.** Metric side 2026-11-08: the identical query printed `0.164.0: 1` for the live pod (and `0.165.0` is
absent until the roll). Startup-gate side: section 1.3b table — healthy `STARTUP_OK`, dummy password / bad config / empty log
`STARTUP_FAIL`.

**FAILS AS:** `DIGEST_MISMATCH` (not the section 2.2 list); 0.165.0 EMPTY (scrape broke or other binary); `STARTUP_FAIL` (no/duplicate
ready line, fatal text, `es_connected` != 3, or any 401/403); `restartCount` > 0 (read `kubectl logs --previous` before deciding;
revert per section 5.1).

### 4.1 Telemetry still FLOWS

CONTROL: metric otelcol_exporter_sent_log_records_total — `sum(increase([15m]))` must be >= 8,000 (floor)
CONTROL: metric otelcol_exporter_sent_metric_points_total — `sum(increase([15m]))` within ±20% of MP_BASE (band)

```bash
P=/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query
kubectl get --raw "${P}?query=sum(increase(otelcol_exporter_sent_log_records_total[15m]))"; echo
kubectl get --raw "${P}?query=sum(increase(otelcol_exporter_sent_metric_points_total[15m]))"; echo
```

**PASS:** log records **>= 8,000** — a floor at about half the 7d minimum of this exact expression (16,555, measured 2026-11-08);
log volume spreads too widely for a band. Metric points **within ±20% of MP_BASE** (flat to ~1%), which catches a partial pipeline
loss a floor would miss.

**FAILS AS:** an **empty `result` array** (metric stopped being exported under that name; empty is FAIL, never skip); a value under
the floor or outside the band.

**The ±20% band is tight right after a Recreate — first suspect it, not the binary, if metric points miss NARROWLY.** The swap
restarts `cumulative_to_delta` (the first sample of every cumulative stream is only a baseline) and the OTLP producers reconnect
during the first minutes. Rule: a first read inside ±20% passes; between ±20% and ±30% is NOT yet a FAIL — re-read once at T+30m
after Ready and it must then sit inside ±20%; beyond ±30% at the first read, or still outside ±20% at T+30m, is a FAIL (section 5.1).
If Reloader rolled the pod a second time (section 3 step 3) the clock restarts from the LAST Ready, which is what `ready-ts` holds.

### 4.2 Elasticsearch is not silently REJECTING

CONTROL: metric otelcol.elasticsearch.docs.processed_total — (a) `outcome="success"` present and non-zero; (b) `outcome!~"success|retried"` empty or zero

Use the DOTTED name (the telemetry pins keep dots; the underscored form reads empty on both sides and can never fail —
docs/sops/monitoring.md).

```bash
P=/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query
M='%7B__name__%3D%22otelcol.elasticsearch.docs.processed_total%22'
kubectl get --raw "${P}?query=sum%20by%20(outcome)%20(increase(${M}%5B15m%5D))"; echo
# (b) the absence gate, and its same-selector POSITIVE CONTROL (exclusion changed so it MUST return the success series):
B=$(kubectl get --raw "${P}?query=sum%20by%20(outcome)%20(increase(${M}%2Coutcome!~%22success%7Cretried%22%7D%5B15m%5D))" | python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];print(sum(float(x['value'][1]) for x in r) if r else 0)")
C=$(kubectl get --raw "${P}?query=sum%20by%20(outcome)%20(increase(${M}%2Coutcome!~%22retried%7Cnomatch%22%7D%5B15m%5D))" | python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];print(len(r) and sum(float(x['value'][1]) for x in r) or 0)")
echo "nonsuccess=$B control(success series via same selector)=$C"
python3 -c "import sys;b,c=float(sys.argv[1]),float(sys.argv[2]);print('REJECT_GATE_OK' if c>0 and b==0 else ('REJECT_GATE_CONTROL_EMPTY_SELECTOR_BLIND' if c<=0 else 'REJECT_GATE_FAIL non-success outcomes present'))" "$B" "$C"
kubectl logs -n monitoring deploy/edot-collector --since=15m | grep -c 'dropping cumulative temporality'
kubectl logs -n monitoring deploy/edot-collector --since=15m | grep -oE "dropping [a-z]+ [a-z]+|invalid number data point" | sort | uniq -c
kubectl logs -n monitoring deploy/edot-collector --since=15m | grep -c 'requires Elasticsearch >= 9.5.0'
```

**PASS:** (a) returns `outcome="success"`, non-zero (baseline 816,242 per 15m, 2026-11-08), AND `REJECT_GATE_OK`: the (b) selector is empty/zero
AND the control — the SAME selector with only the exclusion changed to `outcome!~"retried|nomatch"` — returns the success series (~828k
measured 2026-11-08). (b) therefore cannot pass on a blind selector: if the control is empty the verdict is
`REJECT_GATE_CONTROL_EMPTY_SELECTOR_BLIND` and the gate FAILS.

**What this gate has NOT been shown to catch:** live Prometheus holds exactly ONE series for `otelcol.elasticsearch.docs.processed_total`
over the last 14 days, `outcome="success"`; the 7d `max_over_time` and `increase` of the (b) filter are both empty. The earlier plan's
claim of "tens of thousands of `internal_server_error`/`timeout` outcomes" cannot be replayed and is deleted. **There is no replayable
archive of a real failure outcome**, so (b) is proven to read the right metric (control) but not proven to fire on a real rejection;
the contents gate in 4.3 (documents actually in Elasticsearch) is the independent check.

**Drop baseline (F-76387378, not this plan's):** the `dropping cumulative temporality` count stays near DROP_BASE (60 per 15 min
2026-11-08) and the LAST command (the new suffix `requires Elasticsearch >= 9.5.0`) prints a number close to it — proof the new binary
is the one dropping, with ES < 9.5.0 as the stated reason. A NEW reason string (`invalid number data point`, other `dropping ...`
text), or a rate several times DROP_BASE after T+15m, is a regression candidate: report it; the revert decision stays with the
4.1/4.2(a,b)/4.3 contents gates. A count of ZERO with `success` unchanged is also worth a note (it would mean cumulative histograms
started landing, which needs ES >= 9.5.0).

**Attribution:** the `outcome` label enum from upstream `metadata.yaml` is `success`, `failed_client`, `failed_server`, `timeout`, `too_many`,
`failure_store`, `internal_server_error` (plus `retried`, excluded above). `failed_client` → binary/config: revert. `timeout`,
`internal_server_error`, `failed_server`, `too_many`, `failure_store` → ES side: check `_cluster/health` (4.3) before reverting.

### 4.3 Documents actually LANDED in Elasticsearch, through the NEW code paths

CONTENTS ASSERTION: new documents in both data streams with `@timestamp` after the new pod went Ready; node `.11`'s kernel lines
arrive through `udp_log` with `scope.name`; and histogram documents carry the `temporality` field that ONLY the 0.165 serializer
writes (all `delta`, because our histograms pass through `cumulative_to_delta`). Measured in ES itself (`_bulk` returns 200 even
when items are rejected).

```bash
ES_PW=$(kubectl get secret -n monitoring elasticsearch-es-elastic-user -o jsonpath='{.data.elastic}' | base64 -d)
kubectl port-forward -n monitoring svc/elasticsearch-es-http 19211:9200 >/dev/null 2>&1 & PF=$!
sleep 4
READY_TS=$(cat /private/tmp/claude-501/edot-0165/ready-ts)
test -n "$READY_TS" || echo "NO_READY_TS -> FAIL"
for DS in logs-generic-default metrics-generic.otel-default; do
  echo -n "$DS "
  curl -k -s -u "elastic:$ES_PW" -H 'Content-Type: application/json' -X POST "https://localhost:19211/$DS/_count" \
    -d '{"query":{"range":{"@timestamp":{"gte":"'"$READY_TS"'"}}}}' \
    | python3 -c "import sys,json;print(json.load(sys.stdin).get('count'))"
done
curl -k -s -u "elastic:$ES_PW" -H 'Content-Type: application/json' \
  "https://localhost:19211/logs-generic-default/_search" \
  -d '{"size":0,"query":{"bool":{"filter":[{"term":{"attributes.log_source":"talos-kernel"}},{"range":{"@timestamp":{"gte":"'"$READY_TS"'"}}}]}},"aggs":{"ip":{"terms":{"field":"attributes.net.peer.ip","size":5}},"scoped":{"filter":{"exists":{"field":"scope.name"}}}}}' \
  | python3 -c "import sys,json;d=json.load(sys.stdin);a=d['aggregations'];b={x['key']:x['doc_count'] for x in a['ip']['buckets']};print(b);print('KMSG_OK' if b.get('192.168.55.11',0)>=20 else 'KMSG_FAIL');s=a['scoped']['doc_count'];print('scope.name docs',s,'STANZA_NEW_OK' if s>0 else 'STANZA_NEW_MISSING')"
. /private/tmp/claude-501/edot-0165/temporality.sh      # written by section 2.4b
edot_temporality "$READY_TS"
curl -k -s -u "elastic:$ES_PW" "https://localhost:19211/_cluster/health" \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['status'],d['unassigned_shards'])"
kill $PF 2>/dev/null; unset ES_PW
```

**PASS:** both datastream counts > 0; `KMSG_OK` (if `.11` lands 5–19, re-check once at T+25m before failing); `STANZA_NEW_OK` (a CONTINUITY check only: `scope.name` has been written since 0.163, so it also passes on the old binary; `TEMPORALITY_OK` and the 4.0 digest are the discriminators);
**`TEMPORALITY_OK PRE_ROLL_CONTROL_OK`** (every sampled post-Ready histogram document has `temporality: delta`, AND the documents from
the 20 minutes before the roll have none — the control proves the check discriminates); cluster `green`/`yellow` with 0 unassigned.

**Both sides measured 2026-11-08 against the live 0.164.0 pod:** `edot_temporality` printed `after-ready docs 50 temporality values
['None'] | before-ready docs 50 temporality values ['None']` → `TEMPORALITY_MISSING PRE_ROLL_CONTROL_OK`, i.e. it fails on the old
binary exactly as it must, and the field cannot be a leftover (it has never been written). `TEMPORALITY_MISSING` after the roll while
4.0 says 0.165.0 = the new serializer is not the one writing, OR the histogram metric stopped arriving (`docs.processed` and a manual
`exists` query on `metrics.workqueue_queue_duration_seconds` tell which). A `temporality` value other than `delta` (e.g. `cumulative`)
would mean cumulative histograms are being ACCEPTED, i.e. ES is no longer 8.19 — STOP and re-read section 1.2. A KeyError on
`aggregations` is a FAIL. `traces-generic-default` is not gated (no trace producers; it could only read empty).

### 4.4 Every node's kmsg SENDER survived the restart (per-node heartbeat gate)

CONTENTS ASSERTION: each of 192.168.55.11/.12/.13 delivered at least one `cberg-kmsg-heartbeat` line into ES with `@timestamp` after
the new collector went Ready — the node's Talos UDP sender is not stalled on the dead pod IP.

```bash
ES_PW=$(kubectl get secret -n monitoring elasticsearch-es-elastic-user -o jsonpath='{.data.elastic}' | base64 -d)
kubectl port-forward -n monitoring svc/elasticsearch-es-http 19211:9200 >/dev/null 2>&1 & PF=$!
sleep 4
READY_TS=$(cat /private/tmp/claude-501/edot-0165/ready-ts)
hb() {  # $1 = lower bound for @timestamp (ISO or ES date-math)
  curl -k -s -u "elastic:$ES_PW" -H 'Content-Type: application/json' \
    "https://localhost:19211/logs-generic-default/_search" \
    -d '{"size":0,"query":{"bool":{"filter":[{"term":{"attributes.log_source":"talos-kernel"}},{"wildcard":{"body.text":"*cberg-kmsg-heartbeat*"}},{"range":{"@timestamp":{"gte":"'"$1"'"}}}]}},"aggs":{"ip":{"terms":{"field":"attributes.net.peer.ip","size":5}}}}' \
  | python3 -c "
import sys,json
d=json.load(sys.stdin); b={x['key']:x['doc_count'] for x in d['aggregations']['ip']['buckets']}
miss=[n for n in ('192.168.55.11','192.168.55.12','192.168.55.13') if b.get(n,0)<1]
print(b); print('HB_OK' if not miss else 'HB_FAIL missing='+','.join(miss))"
}
hb "$READY_TS"      # THE GATE
hb "now+1h"         # negative control: MUST print HB_FAIL missing=.11,.12,.13
kill $PF 2>/dev/null; unset ES_PW
```

**PASS:** the gate prints `HB_OK` with all three IPs, AND the control prints
`HB_FAIL missing=192.168.55.11,192.168.55.12,192.168.55.13`. If the control does not print HB_FAIL, the harness is broken and
HB_OK means nothing — FAIL. (Positive side measured on the 0.164.0 plan, 168 heartbeat docs per node over 7 d with this wildcard
+ field shape.)

**Timing:** evaluate at T+5m after section 3 step 5's DaemonSet roll; re-evaluate once at T+15m before declaring a node missing.

**FAILS AS:** `HB_FAIL missing=<ip>` at T+15m while that node's heartbeat pod is Running with a fresh start = the known **kmsg-sender
stall**. **NOT a revert trigger** (reverting restarts the collector again — the stall trigger itself). Go to section 5.3. A missing
heartbeat POD (not Running) is a DaemonSet problem: `kubectl describe pod -n monitoring <pod>`; do not toggle the node. NOTE: if
Reloader rolled the collector a second time AFTER the heartbeat kick, the kick no longer follows the last roll — re-run step 5 with a
new REV (and re-capture `ready-ts`) before judging this gate.

### 4.5 The exporter series EXIST — direct absent() evaluation

The `Es*ExporterSeriesMissing` and `TalosKmsgPipelineDown` rules carry `for: 15m`, so at T+15m they are at most `pending`; evaluate
their expressions directly instead.

CONTROL: metric otelcol_exporter_sent_log_records_total — `absent(...{exporter="elasticsearch/logs"})` must be EMPTY
CONTROL: metric otelcol_exporter_sent_metric_points_total — `absent(...{exporter="elasticsearch/metrics"})` must be EMPTY
CONTROL: metric talos_kernel_kmsg_lines_total — `absent(talos_kernel_kmsg_lines_total)` must be EMPTY

```bash
P=/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query
for Q in \
  'absent(otelcol_exporter_sent_log_records_total{exporter="elasticsearch/logs"})' \
  'absent(otelcol_exporter_sent_metric_points_total{exporter="elasticsearch/metrics"})' \
  'absent(talos_kernel_kmsg_lines_total)' \
  'absent(otelcol_exporter_sent_log_records_total{exporter="elasticsearch/bogus"})'; do
  E=$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))" "$Q")
  kubectl get --raw "${P}?query=${E}" | python3 -c "
import sys,json
d=json.load(sys.stdin); r=d['data']['result']
print('ABSENT' if r else 'PRESENT', sys.argv[1])" "$Q"
done
```

**PASS:** the first three print `PRESENT`; the fourth (positive control) prints `ABSENT`. If the control does not print `ABSENT`,
the harness is broken: FAIL.

**FAILS AS:** `ABSENT` on line 1 or 2 → exporter series gone under that name → section 5. `ABSENT` on line 3 is a FAIL only if 4.3
also printed KMSG_FAIL (the exporter re-registers on the first line, and step 5 guarantees lines).

## 5) Rollback

### 5.1 Primary — revert the combined commit

The heartbeat-kick commit is a harmless pod-template annotation; leave it (reverting only restarts the heartbeat pods again).

```bash
BUMP_SHA=$(cat /private/tmp/claude-501/edot-0165/bump-sha)
git fetch origin main && git merge --ff-only origin/main
git revert --no-edit "$BUMP_SHA"
git show --stat HEAD       # exactly configmap.yaml + deployment.yaml; image back to :0.164.0 AND the three `mapping: mode: otel` blocks back
git log -1 --format=%s     # MUST read: Revert "feat(container): update otel/opentelemetry-collector-contrib ( 0.164.0 → 0.165.0 ) + drop removed mapping::mode ..."
git push origin main
flux reconcile kustomization edot-collector -n monitoring --with-source   # namespace monitoring
. /private/tmp/claude-501/edot-0165/settle.sh && edot_settle
ROLLBACK_DIGEST=sha256:340c9ca6a36617084c6661bdc4f0fe92b7cda5a805d61673ec8db375fddc522b
LIVE_ID=$(kubectl get pods -n monitoring -l app=edot-collector -o jsonpath='{.items[0].status.containerStatuses[0].imageID}')
case "$LIVE_ID" in *"$ROLLBACK_DIGEST") echo "ROLLBACK_DIGEST_OK" ;; *) echo "ROLLBACK_DIGEST_MISMATCH: $LIVE_ID" ;; esac
```

`$ROLLBACK_DIGEST` is 0.164.0's manifest-list digest, read from the running pod's `imageID` on 2026-11-08. The restored pair (0.164.0
+ `mode: otel`) is the exact state that has been serving since 2026-11-06 and validates exit 0 on the 0.164.0 binary (section 1.3).
After the revert: re-capture the Ready timestamp into `/private/tmp/claude-501/edot-0165/ready-ts` (same command as section 3 step 3),
re-run section 3 step 5 with a new REV, then 4.1–4.4 adapted to the 0.164.0 expectations (the startup gate for 0.164.0 is the INVERSE:
`es_connected=0`, three `status 401` warns — do not reuse the 0.165.0 gate on a 0.164.0 pod; judge by `ready_lines=1 fatal_lines=0`
and `restartCount=0`, and drop the TEMPORALITY check). A revert that restores the manifest but not the telemetry is not a rollback.
Renovate will re-open the PR for 0.165.0 on its own; do not merge it — the plan is `status: draft` again and needs this config leg.

### 5.2 Contingency — the forward-only surface (bbolt queue)

`pvc/edot-collector-queue` holds the persistent sending queue, written by whichever binary runs. The only queue-related change in
0.165.0 is the `Cannot unref freed data` panic fix (#15256) for queues forwarding into another pipeline; no entry touches the
on-disk bbolt format, so 0.164.0 is expected to read it back. **If the reverted pod crash-loops on the queue file:**

```bash
kubectl logs -n monitoring deploy/edot-collector --tail=50 | grep -iE "bolt|storage|queue|corrupt"
```

1. `kubectl scale deploy/edot-collector -n monitoring --replicas=0` to release the RWO volume (Flux scales it back on its next
   reconcile, interval 30m — do steps 2–3 promptly).
2. Wait until `kubectl get pods -n monitoring -l app=edot-collector` prints nothing, then empty the queue from a throwaway pod with
   uid/gid/fsGroup 10001, using the busybox digest already pinned and cached for `kmsg-heartbeat`:

   ```bash
   kubectl run edot-queue-wipe -n monitoring --restart=Never \
     --image=busybox:1.38.0@sha256:dc2d74b28e4cf8984fa52af1f39bc7c3d9c73760b41a74d629f5d11b1ab28616 \
     --overrides='{"spec":{"securityContext":{"runAsUser":10001,"runAsGroup":10001,"fsGroup":10001},"containers":[{"name":"edot-queue-wipe","image":"busybox:1.38.0@sha256:dc2d74b28e4cf8984fa52af1f39bc7c3d9c73760b41a74d629f5d11b1ab28616","command":["sh","-c","ls -la /q; find /q -mindepth 1 -delete; echo REMAINING=$(find /q -mindepth 1 | wc -l)"],"volumeMounts":[{"name":"q","mountPath":"/q"}]}],"volumes":[{"name":"q","persistentVolumeClaim":{"claimName":"edot-collector-queue"}}]}}'
   kubectl wait pod/edot-queue-wipe -n monitoring --for=jsonpath='{.status.phase}'=Succeeded --timeout=180s
   kubectl logs -n monitoring edot-queue-wipe      # MUST end with REMAINING=0
   kubectl delete pod -n monitoring edot-queue-wipe
   ```

   A timeout with the pod in `ContainerCreating` = volume still attached elsewhere (Multi-Attach). Wait; do not force-detach.
3. `kubectl scale deploy/edot-collector -n monitoring --replicas=1`, then re-run the 4.1–4.4 equivalents.

Cost: only the buffered in-flight telemetry (`create_directory: true` makes an empty directory a clean start). **Operator-visible;
record it.** It is the only step that loses data.

### 5.3 kmsg-sender stall on a node (from 4.4) — recovery, not rollback

Documented recipe in `docs/troubleshooting/node-reboot-observability.md` §"kmsg-sender stall on collector restart": toggle the
node's `KmsgLogConfig` url to port 5172 and back to 5171 (re-opens the UDP socket without a reboot; a same-value `apply-config` does
NOT kick it).

```bash
NODE=<192.168.55.1x of the missing node>
talosctl -n "$NODE" patch mc --patch '{apiVersion: v1alpha1, kind: KmsgLogConfig, name: ship-kmsg-to-otel, url: udp://192.168.55.18:5172/}'
talosctl -n "$NODE" patch mc --patch '{apiVersion: v1alpha1, kind: KmsgLogConfig, name: ship-kmsg-to-otel, url: udp://192.168.55.18:5171/}'
```

A direct Talos machine-config mutation outside Flux (ends at the same value), so:
- **Attended slot:** operator GO, then delegate to cberg-agent, re-run section 3 step 5 with a new REV and 4.4.
- **Nightly (unattended):** do NOT toggle. Leave the bump in place, record a finding naming the node, put the toggle in the morning
  report. `TalosKernelLogsMissingFromNode` pages at 3h+15m if the node stays silent. The only loss is that node's kernel-log
  diagnostic feed, not user data.

### 5.4 Restore alert state (either outcome)

```bash
runbooks/update-marker.sh clear edot-collector
kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 >/dev/null 2>&1 & PF=$!
sleep 3
SID=$(python3 -c "import json;print(json.load(open('/private/tmp/claude-501/edot-0165/silence.json'))['silenceID'])")
curl -s -o /dev/null -w 'delete silence %{http_code}\n' -X DELETE "localhost:9093/api/v2/silence/$SID"
kill $PF 2>/dev/null
```

## 6) Interference notes

- **PR #500 merged alone = outage (the central gotcha).** Merging the Renovate PR without the config edit rolls a pod that exits at
  startup; with `Recreate` there is no old pod to fall back to. Step 0 will not do it (the 0.x rule in `coverage.py` holds the item
  and the hold does not depend on release notes), Renovate does not automerge it, but a human "merge all green PRs" would. **If it
  happens** (premise 1 prints `:0.165.0`, collector `CrashLoopBackOff`, `kubectl logs --previous` shows `'mapping' has invalid keys:
  mode`): do NOT debug further — run section 3 step 2's python edit for `configmap.yaml` ONLY (the image line is already 0.165.0), commit,
  push, then `edot_settle` and section 4; or, if time-critical, `git revert` the merge commit (section 5.1 shape). Either restores
  ingestion within one Recreate roll; the queue on the PVC keeps whatever was buffered.
- **Single commit on purpose.** One commit means one revert and no state in which the image and the config disagree. The cost is that
  Reloader (kube-system) sees the ConfigMap change and may roll the Deployment a second time after Flux's own roll — hence
  `edot_settle` and the "last Ready" `ready-ts`. A two-phase variant (config first on 0.164.0, then the bump) was rejected: two
  Recreate rolls, two kmsg-stall exposures, and about 25 extra minutes that do not fit a nightly slot.
- **Keep OFF this night (declared in `conflicts_with` where a plan exists; otherwise gated by section 2.1b):** any otel-operator /
  opentelemetry-kube-stack change (the daemon collectors EXPORT into `edot-collector.monitoring.svc:4317`; 0.27.0 landed 2026-11-07
  and its pods are 23 h old and healthy, so there is no residual dependency tonight), any kube-prometheus-stack bump (section 4
  reads Prometheus; PRs #501 major and #428 are open with no plan and held by the time-boxed deny rule, revisit by 2026-11-30), any
  Flux change (#471 is the flux2 CLI pin; `flux-oci-chart-sources` and `flux-reconciler-impersonation` are in `conflicts_with`), and
  the Talos roll `talos-linux-1.14.5` (drains the node this replica runs on and silences each node's kmsg feed during its reboot;
  never the same window). `longhorn-1.13.0` is excluded for the RWO queue volume.
- **Slot preference: attended preferred, nightly acceptable.** 60 of 70 nightly minutes. The only step that wants an operator is the
  section 5.3 kmsg toggle, and only on a stall; the section 6 PR #500 contingency is the other reason to prefer attended.
- **Ingestion gap of tens of seconds to a couple of minutes** during the Recreate swap (longer if Reloader adds a second roll).
  OTLP producers (the otel-operator daemon collectors) buffer only in memory, so a few seconds may be lost; the ES exporters
  back-pressure via `block_on_overflow` + disk queue (visible as `otelcol_receiver_refused_*`). Any kmsg line sent during the swap is
  lost (UDP, no listener), which is why step 5 runs only after Ready.
- **The image is minimal** (no `cat`/`curl`/`wget`): every check uses `kubectl get --raw` or port-forward + local curl, never
  `kubectl exec`.
- **The daemon collectors are NOT moved** — they run `otel/opentelemetry-collector-k8s`, owned by HelmRelease `otel-operator`.
  Repo-wide, `otel/opentelemetry-collector-contrib:` appears only in `edot-collector/app/deployment.yaml`.
- **Future ES upgrade — now REAL, correcting the 0.164.0 plan.** That plan said the version probe was blind (401) so the histogram
  mapping could not change with the ES version. From 0.165.0 the probe is authenticated and works (`Connected to Elasticsearch`
  x3). Therefore the next monitoring-ES upgrade changes behaviour: ES >= 9.4.0 switches explicit-bounds histograms in
  `metrics-generic.otel-default` to native exponential histograms (`resolveDefaultHistogramMapping`), and ES >= 9.5.0 additionally
  accepts cumulative histograms (they stop being dropped, so F-76387378's 360/h drops disappear and `temporality: cumulative` appears).
  Any plan that bumps the `elasticsearch` Elasticsearch CR (8.19.20 today; premise 5 guards it) must re-validate the TSDB OTel stream
  mapping for histograms before the bump. The `tube-archivist-elasticsearch-9.5.5` plan concerns a different cluster.
- **`python-fleet-3.15.2-alpine`** (awaiting-go, slotted `sat-attended:2026-11-14` with `open-webui-0.13.0`) touches `monitoring` through the
  `elasticsearch-obs-recovery` CronJob, a reader/writer of the same Elasticsearch this plan's 4.3 gate reads. Not in `conflicts_with` (it
  does not restart the collector or Prometheus); do not share a slot with it.
- **`--controls` needs an oracle:** `plan-premises.py --controls edot-collector-0.165.0` reads every metric UNVERIFIED and FAILS unless given
  `--prom-url http://localhost:<port>` (a port-forwarded `svc/kube-prometheus-stack-prometheus`) or `SLO_PROM_URL`. Measured PASS with it
  (7 CONTROL lines, 13 instruments).
- **Pre-existing noise not to attribute here:** health finding **F-76387378** (edot ES dropped metric points, ~360/h, baseline
  recorded in section 2.4). The same reason string at about the same rate is the baseline, not a 0.165.0 regression (section 4.2).
- **Repo corrections owed (found while writing this plan, none applied):** (1) upstream's `[chore]` commits carry no changelog entry,
  so `auto-update.py`'s "no breaking-change signal in release notes" test is blind to removed config keys; the only reliable gate for
  a `otel/opentelemetry-collector-contrib` bump is `otelcol-contrib validate` of the live config on the new binary, which this plan
  runs and the sweep does not. (2) The retired 0.164.0 plan's section 1.2/1.3b statement that the ES version probe is
  unauthenticated and "can only ever fail" is true for 0.164.x only and is inverted from 0.165.0 (above). (3) `docs/sops/monitoring.md`
  and `docs/troubleshooting/node-reboot-observability.md` contain no reference to either, so nothing there needs editing.
