---
plan_id: edot-collector-0.164.0
component: edot-collector
pr: 324                           # Renovate "feat(container): update otel/opentelemetry-collector-contrib
                                  # ( 0.161.0 → 0.164.0 )", branch renovate/otel-opentelemetry-collector-contrib-0.x.
                                  # SAME PR the edot-collector-0.163.2 plan was written for: Renovate
                                  # RE-TARGETED it 0.163.2 -> 0.164.0 (last update 2026-10-27T02:45Z).
                                  # OPEN, MERGEABLE, all 4 checks SUCCESS incl. Flate Render Gate
                                  # (measured 2026-10-29). Diff = exactly one line in deployment.yaml.
kind: image
current: "0.161.0"                # MEASURED 2026-10-29: deployment/edot-collector image
                                  # otel/opentelemetry-collector-contrib:0.161.0, pod
                                  # edot-collector-7dbd97b8d8-vzdzj imageID ...@sha256:fd328de2...5ac1.
target: "0.164.0"                 # Multi-arch MANIFEST LIST on Docker Hub, 7 linux platforms incl.
                                  # amd64, digest
                                  # sha256:340c9ca6a36617084c6661bdc4f0fe92b7cda5a805d61673ec8db375fddc522b
                                  # (measured 2026-10-29). releases-repo v0.164.0 (2026-10-26T23:46Z) is
                                  # built from core v0.164.0 + contrib v0.164.1 (contrib 0.164.1 = a
                                  # go.mod dependency fix only, #52356). Tag 0.164.1 is HTTP 404 on
                                  # Docker Hub: there is no newer image to wait for.
update_type: minor                # 0.x line: the MINOR digit is the breaking axis (0.161 -> 0.164 = 3 minors)
risk: medium                      # NOT from likelihood: every breaking entry in 0.162/0.163/0.164 names
                                  # a component or feature gate this config does not use (§1.2), and
                                  # the live config validates on the 0.164.0 binary with 3 of 4
                                  # negative controls failing as they must (§1.3). From blast radius +
                                  # failure MODE: one replica, the sole OTLP path into ES for every
                                  # namespace plus the Talos kmsg sink; its characteristic failure is
                                  # SILENT (pod Ready, telemetry gone) — §4 gates contents.
est_duration_min: 52              # 14 pre-checks (tag gate, local + in-cluster validate, 15 s startup-gate
                                  # rehearsal §2.3(c), baselines) +
                                  # 3 merge + 5 reconcile/Recreate roll + 3 heartbeat-kick commit +
                                  # DaemonSet roll + 15 settle (every [15m] window in §4 must lie after
                                  # the roll) + 12 verification. Fits a nightly slot (90 - STEP0 20 = 70m).
needs_reboot: false
touches:
  namespaces: [monitoring]
  resources:                      # every object below verified to EXIST live 2026-10-29
    - deployment/edot-collector               # image tag (via PR #324) — the change; strategy Recreate (measured)
    - daemonset/kmsg-heartbeat                # pod-template annotation only (§3 step 5): restarts the 3
                                              # heartbeat pods so each node writes one kmsg line on demand
    - configmap/edot-collector-config         # READ + validated on 0.164.0 (§1.3, §2.3); NOT edited
    - pvc/edot-collector-queue                # RWO longhorn-static, Bound; bbolt sending queue; detach/attach
                                              # on the Recreate roll; the forward-only surface (§5.2)
    - service/edot-collector                  # ClusterIP 4317/4318/8888/8889 — every OTLP producer's target
    - service/edot-collector-talos-kmsg       # LoadBalancer 192.168.55.18 UDP 5171
    - servicemonitor/edot-collector           # the scrape feeding §4
    - httproute/edot-collector                # OTLP/HTTP on envoy-internal; backend briefly down during the roll
    - kustomization/edot-collector            # Flux Kustomization, namespace monitoring (Ready, measured)
  shared: [monitoring]            # the single OTLP choke point for every namespace's logs/metrics into
                                  # Elasticsearch + the Talos kmsg sink (TalosKernelLogsMissingFromNode).
                                  # A roll blinds cluster-wide ingestion for its duration. NOT
                                  # gateway/envoy: routing unchanged.
depends_on: []
conflicts_with:                   # HARD slot exclusions — the only field window-scheduler.py honours.
                                  # Built from every open plan's frontmatter on 2026-10-29.
  - edot-collector-0.163.2        # SAME deployment, SAME PR #324 (retargeted to 0.164.0). Now
                                  # `status: superseded` (2026-11-02, superseded_by this plan) — terminal, kept
                                  # in the list only until the orchestrator prunes the reciprocal refs.
  # REMOVED 2026-11-03 (plan retired cdf1cf53, chart live via 5aa609d5; dead ref) - otel-operator-0.26.1          # draft, HUMAN-GATED; supersedes otel-operator-0.25.1. Its daemon collectors
                                  # EXPORT into edot-collector.monitoring.svc:4317 and its §4.4 proves itself
                                  # via docs landing in ES THROUGH this collector. OPERATOR RULE 2026-10-23:
                                  # SEPARATE slot, otel-operator FIRST (suggested sat-attended:2026-11-07 SOLO).
  - otel-operator-0.27.0          # live plan for the same HelmRelease (vetted, window null); keep out of this night (reviewer 2026-11-06)
  - otel-operator-0.25.1          # the plan 0.26.1 supersedes (still vetted at sat-attended:2026-11-07 until the
                                  # orchestrator retires it) — keep until then; same reason.
  - talos-linux-1.14.5            # draft, EXCLUSIVE, supersedes talos-linux-1.14.4: node drains evict this
                                  # single replica (RWO queue PVC re-attaches) and silence each node's kmsg
                                  # feed for its reboot — §4.1/§4.3/§4.4 would misattribute.
  - talos-linux-1.14.4            # the plan 1.14.5 supersedes (still vetted at sun-attended:2026-11-01 until the
                                  # orchestrator retires it) — keep until then; same reason.
  - longhorn-1.13.0               # the bbolt queue is an RWO Longhorn volume; an engine/manager roll
                                  # during the Recreate detach/attach is the Multi-Attach surface.
  - grafana-14.1.0                # carried from 0.163.2 (reciprocal there): keep a failed monitoring-
                                  # namespace gate attributable to ONE change.
  - flux-oci-chart-sources        # re-sources every HelmRelease incl. kube-prometheus-stack (monitoring);
                                  # §4 reads Prometheus — authoring rule 4 (shared instrument).
exclusive: false
security_ref: F-dbefa2e5          # OPEN security row on the 0.161.0 image (first seen 2026-10-29, queried
                                  # 2026-11-02 with SWEEP_PG_DSN up; `finding list --all --grep
                                  # collector-contrib`). DETAIL stays in the DB. A newer upstream tag
                                  # exists, so a bump is the only remediation this household performs; this
                                  # plan does NOT assert the row closes — the next sweep's image scan of the
                                  # 0.164.0 pod decides. (Earlier drafts said "none open": stale since 10-29.)
capability_change: false          # image tag only + a no-op pod-template annotation on the heartbeat
                                  # DaemonSet. No config change, no new receiver/exporter/processor/route/
                                  # permission. Upstream changes reaching this config are bug fixes,
                                  # extra retries, a startup log line and a scope.name field on kmsg docs
                                  # (§1.2) — same observable contract.
rollback_class: git-revert        # one-commit revert of the PR squash commit. The one forward-only
                                  # surface — the bbolt queue written by the newer binary — has an
                                  # explicit PROCEDURE in §5.2.
finding_refs: [F-cb9182ca]        # version row "edot-collector: image otel/opentelemetry-collector-contrib
                                  # 0.161.0 → 0.164.0 (minor)", status unchanged, last seen 2026-11-02
                                  # (`finding list --all --grep 0.164`, SWEEP_PG_DSN up). Formerly also
                                  # claimed by edot-collector-0.163.2 (now superseded). F-76387378 (health,
                                  # monitor: edot ES dropped metric points, 360/h since 2026-10-31) is NOT
                                  # answered here — it is a pre-existing baseline this plan must not be
                                  # blamed for or credited with (§2.4, §6).
review: ready-for-go@2026-11-06                      # refreshed in place 2026-11-06 (operator asked to execute in the attended NOW
                                  # window); the 2026-11-02 ready-for-go stamp is removed - a plan-reviewer
                                  # re-review stamps it. Never hand-write ready-for-go.
status: vetted
window: "now:2026-11-06"   # ON-DEMAND NOW run 2026-11-06 (run-now.py stamp; was None)
premises:
  # Re-checked at EXECUTION time. All four RUN on 2026-10-29 while writing this plan.
  - id: image-is-still-0.161.0
    why: >-
      `current:` claims 0.161.0. If Step 0 auto-merged PR #324 (it merged the 0.162.0 PR #264 on
      2026-10-08) or anyone else moved the collector, §3 is moot and the §5.1 rollback digest is
      wrong. Prints the actual image when it fails. If it fails because the image already reads
      0.164.0, do NOT re-run §3 — run §4 as post-hoc verification (see §6).
    run: kubectl get deploy -n monitoring edot-collector -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "otel/opentelemetry-collector-contrib:0.161.0"
  - id: ingestion-is-healthy-before-we-touch-anything
    why: >-
      Never roll the sole telemetry path while it is ALREADY degraded — a pre-existing stall would
      be misattributed to this bump. Asserts the logs exporter persisted more than 1000 records over
      the last 15m (measured 23,720 on 2026-10-29; 7d min of the same expression 15,722). The awk
      `$1+0` coercion makes an empty result fail closed (INGEST_LOW). Written with `<` because the
      premise sandbox refuses the greater-than character.
    run: kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=sum(increase(otelcol_exporter_sent_log_records_total[15m]))' | sed -E 's/.*"value":\[[0-9.]+,"([0-9]+).*/\1/' | awk '{print ($1+0<1000)?"INGEST_LOW":"INGEST_OK"}'
    expect_exact: "INGEST_OK"
  - id: config-is-the-one-validated-on-0.164.0
    why: >-
      §1.3's evidence (the live otel.yml validates on the 0.164.0 binary) holds only for the config
      committed in 429791200b7e (2026-09-28, the last commit touching configmap.yaml). If the configmap
      moved, that evidence is stale; §2.3 still runs either way. Prints the newer short sha if it moved.
      CORRECTED 2026-11-06: the old expect_exact "42979120" (8 chars) failed because git now abbreviates
      %h to 9 chars (`429791200`); same commit, abbreviation-length drift (`git rev-parse 429791200` =
      429791200b7eabd0bf94586a60e41aa7de8eb347), NOT a config change. The regex is a prefix match so
      further abbreviation growth cannot flip it, while a different sha still fails.
    run: git log -1 --format=%h -- kubernetes/apps/monitoring/edot-collector/app/configmap.yaml
    expect_matches: "^42979120"
  - id: kmsg-heartbeat-daemonset-ready-on-all-nodes
    why: >-
      §4.4's per-node gate depends on one heartbeat pod per node writing a kmsg line when it starts.
      With fewer than 3 ready the gate would read a missing heartbeat POD as a stalled kmsg SENDER.
      Measured 3 on 2026-10-29.
    run: kubectl get ds -n monitoring kmsg-heartbeat -o jsonpath='{.status.numberReady}'
    expect_exact: "3"
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/monitoring.md                          # "ES Rejected Documents" — §4.2 uses the dotted outcome metric
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/longhorn-rwo-multi-attach.md           # why strategy Recreate is load-bearing
  - docs/troubleshooting/node-reboot-observability.md  # kmsg-sender stall + the url-toggle recovery in §5.3
generated: "2026-11-06"            # refreshed in place 2026-11-06 (premise 3 corrected + re-measured); amended 2026-11-02 after plan-reviewer needs-fix; original 2026-10-29
---

# edot-collector: image 0.161.0 → 0.164.0 (0.x release-line move, three minors)

## 1) Summary & why held

### 1.1 Why it was held

`runbooks/coverage.py` (sweep 8699f7d4, rule 4d0) routed this to the PLAN lane on its
component-agnostic rule: *"0.x release-line move (0.161 -> 0.164) — at major 0 the minor IS the
breaking axis"*. No deny rule, no security driver (`security_evidence: none`).

The change is one line, delivered by Renovate PR **#324**
(`image: otel/opentelemetry-collector-contrib:0.161.0` → `:0.164.0`). It is green, Flate Render
Gate included. This is the **same PR** that `edot-collector-0.163.2` (vetted,
`nightly:2026-11-10`) was written for: Renovate re-targeted it to 0.164.0 on 2026-10-27, so that
plan's §2.2 hard gate (title must read `→ 0.163.2`) now STOPs it. This plan replaces it; see §1.5.

**History.** The 0.162.0 bump (PR #264) was merged by nightly Step 0 on 2026-10-08 and
auto-reverted (`0b958c7d`) as **collateral** of a pgvector culprit, not for its own behaviour.
There is no evidence either way about 0.162.0 itself; the revert still counts against this
image's earned autonomy.

### 1.2 Upstream evidence — assessed against OUR config

Read directly (authoring rule 8): contrib `v0.164.0` (2026-10-26) and `v0.164.1`, core
`v1.70.0/v0.164.0`, releases-repo `v0.164.0`. For 0.162.0 and 0.163.x this plan relies on
`edot-collector-0.162.0` §1.2 and `edot-collector-0.163.2` §1.2 (same config, unchanged since
`42979120`; reviewer verdict ready-for-go 2026-10-23); §1.3 re-validates the config on a binary
containing all three minors.

Components `otel.yml` instantiates (LIVE configmap, 2026-10-29): receivers `otlp`,
`udp_log/talos-kernel` (stanza `json_parser`/`move`/`add`); processors `memory_limiter`, three
`filter` (all with explicit `error_mode: ignore`), one `transform` (OTTL `delete_key` + `IsMap`,
no `set`), `cumulative_to_delta`, `batch`; exporters three `elasticsearch` (otel mapping, static
`*_index`, `sending_queue` on `file_storage/queue`, `block_on_overflow: true`, own `retry` block),
`prometheus/hwerrors`; connector `count/hwerrors`; extensions `file_storage/queue`, `health_check`;
the `service::telemetry` Prometheus reader with three `without_*: false` pins. No `--feature-gates`.

**releases-repo v0.164.0** — adds the partitioning processor to the contrib distribution (unused
here); "Build release binaries with Go 1.26.10 and require Alpine `ca-certificates` 20261020-r0
... The updated CA bundle removes the distrusted eMudhra emSign roots" (#1722). Our ES exporters
use `tls.insecure_skip_verify: true` against the in-cluster ECK endpoint, so a CA-bundle change
cannot break them; §4 covers the Go-toolchain residual on live traffic.

**core v0.164.0** — no breaking section. Only `exporter/otlp_http` error text, `pkg/otelcol`
OpAMP raw-config redaction and `mdatagen` — none instantiated here.

**contrib v0.164.0 "Breaking changes" — each against our config:**

| entry | ours? | why not |
|---|---|---|
| `connector/service_graph`, `pkg/azurelogs`, `pkg/coreinternal` goldendataset, `pkg/translator/pprof`, `pkg/zipkin`, `processor/drain`, `receiver/file_log`, `receiver/kubelet_stats`, `receiver/mongodb`, `receiver/prometheus` | no | components not in `otel.yml` (`kubelet_stats`/`k8s_objects` run in the otel-operator daemon collectors, image `opentelemetry-collector-k8s`, not moved here) |
| `exporter/prometheus`: "Always preserve leading and consecutive underscores in label names. Remove `-pkg.translator.prometheus.PermissiveLabelSanitization` from `--feature-gates`; disabling this gate now causes a startup error." | exporter yes, effect no | we pass no `--feature-gates`; `prometheus/hwerrors` labels come only from `net.peer.ip` → `net_peer_ip` (no leading/consecutive underscores). The alert rules' label set is unchanged. §4.5 proves the `talos_kernel_kmsg_lines_total` series still exists. |
| `processor/filter`: "remove stable processor.filter.defaultErrorModeIgnore gate" | processor yes, effect no | every one of our three filters sets `error_mode: ignore` explicitly, and the gate was already stable (on) in 0.161 |
| `pkg/ottl`: "Remove the stable `ottl.set.allowNil` feature gate" | no | no `set` statement in our config |

**Changes that DO reach components we run, each checked:**

- **`exporter/elasticsearch`: explicit-bounds histograms converted to native exponential histograms
  "when connected to Elasticsearch 9.4.0 or later" (#52113), and the exponential threshold moved
  from 9.3.0 to 9.4.0 (#52222).** Code at `v0.164.0`: `es_version.go`
  `minExponentialHistogramVersion = semver.New(9, 4, 0)`; `exporter.go`
  `resolveDefaultHistogramMapping` returns exponential only if `VersionDetection.Enabled &&
  supportsExponentialHistograms(v)`. Our ES is **8.19.20** (`kubectl get elasticsearch -n
  monitoring`, 2026-10-29) → stays on **TDigest, the existing mapping**. No change today.
  **Correction (plan-reviewer 2026-11-02, reproduced 2026-11-02 — see §1.3b):** the version probe
  itself does NOT work against our ES. `getElasticsearchVersions` builds its `elastictransport`
  with only `URLs`/`Transport`/retry fields — no username/password — so the unauthenticated
  `GET /` gets **401** from our ECK-secured ES, the exporter logs `failed to fetch Elasticsearch
  info ... "es info returned status 401"` (once per ES exporter, so three lines), returns `nil`, and
  `supportsExponentialHistograms(nil)` is `false`. So the mapping is TDigest **regardless of the ES
  version** until upstream sends credentials on that probe or `version_detection` is set explicitly
  (§6). Do NOT read "ES stays 8.19" as the only thing holding TDigest: the detection is blind.
- **`exporter/elasticsearch`: "Additionally retry context deadlines that expire before the connection
  is ready, including DNS, TCP handshake, and TLS handshake timeouts" (#52102).** More retries, not
  fewer; with `max_retries: 0` (infinite) and a disk queue this can only reduce loss. It may raise
  the `retried` outcome count, which §4.2(b) already excludes.
- **`exporter/elasticsearch`: opt-in `telemetry::include_destination_index` (#52108)** — not set; the
  `otelcol.elasticsearch.docs.processed` series keep today's labels (§4.2 reads them).
- **`exporter/elasticsearch` version detection (from 0.163.0, default `enabled: true`)** — file
  renamed `version.go` → `es_version.go` at v0.164.0; success logs `Info("Connected to
  Elasticsearch", ...)`, failure is Warn-only (`failed to fetch Elasticsearch info`), 5s timeout.
  **On our cluster it can only ever take the failure path (401, above)**, so a healthy 0.164.0
  NEVER logs "Connected to Elasticsearch" and logs three 401 warnings instead. The earlier draft's
  §4.0 gate (`Connected to Elasticsearch` >= 3) therefore could not pass on a healthy pod and would
  have auto-reverted it; §4.0 now gates on the service's own `Everything is ready` line (§1.3b).
  (Only the histogram-mapping consumer of the probe result was read at v0.164.0
  `exporter.go:94-96`; no other consumer was verified.)
- **`processor/cumulative_to_delta`: "Include the scope attributes in the identity of a stream"
  (#52162), NaN-sum exponential fix (#51965).** Our metrics arrive via OTLP from the daemon
  collectors' Prometheus scrapes; streams differing only in scope attributes were previously
  merged (wrong deltas), now separated. Effect at most a correctness fix on delta values; point
  COUNT is unchanged and every stream resets on the restart anyway. §4.1's ±20% metric band
  would catch a gross change.
- **`pkg/ottl`: "Promote traces, metrics, and logs signals from beta to stable" (#51068), context
  inference fix for all-uppercase converter names (#52192).** Our statements parse (§1.3) and
  OTTL parse errors are fatal at validate (negative control below).
- **`processor/transform`: `flatten_data` deprecated** — not used.
- **From 0.163.0 (carried, see 0.163.2 §1.2):** `pkg/stanza` default scope name (kmsg docs gain
  `scope.name`, routing unaffected because `logs_index` is static — §4.3 uses it as positive proof),
  and core `exporterhelper` fix for sending-queue deadlocks with `block_on_overflow` (#15700), which
  we are exposed to and which this bump fixes.

**The two invariants the brief named are not touched:** the managedFields `"."`-key strip
(`transform/strip-k8s-managedfields`, `delete_key` + `IsMap`) parses unchanged on 0.164.0 and the
IsMapp negative control proves the transform is actually parsed; the ES TSDB OTel metrics stream
(`metrics-generic.otel-default`) keeps its TDigest histogram mapping on ES 8.19 (above), and
§4.2/§4.3 gate that docs still land there without rejections.

### 1.3 The live config validates on the 0.164.0 binary — and what that gate cannot see

Run 2026-10-29 on the Mac with the official `otelcol-contrib_0.164.0_darwin_arm64.tar.gz` from
releases-repo `v0.164.0` (reports `otelcol-contrib version 0.164.0`), against the LIVE `otel.yml`
pulled from `configmap/edot-collector-config`:

| input | 0.164.0 exit | meaning |
|---|---|---|
| live `otel.yml` | **0**, empty output | accepted |
| `num_consumers: 4` → `notanint` (first ES exporter) | 1 (`failed to get config: cannot unmarshal`) | type errors caught |
| `IsMap(log.body)` → `IsMapp(log.body)` in the managedFields transform | 1 (`processors::transform/strip-k8s-managedfields: unable to parse OTTL statement`) | OTTL errors caught |
| `bogus_key: 1` under `service::telemetry…prometheus` | 1 (`has invalid keys: bogus_key`) | telemetry-reader unknown keys caught |
| `totally_unknown_field: 1` in `elasticsearch/logs` | **0** | **ES exporter unknown keys NOT caught** |

The ES-exporter blind spot (same as on 0.163.2) is why §4.1 and §4.2 gate on contents and treat
an empty result as FAIL.

### 1.3b The startup-log gate, measured on a real 0.164.0 start (not just `validate`)

`validate` never starts the pipeline, so it cannot show what a healthy 0.164.0 prints. On
2026-11-02 the official `otelcol-contrib_0.164.0_darwin_arm64.tar.gz` (sha256 `af6a0c56…cf73a`,
equal to the release asset's published digest; banner `otelcol-contrib version 0.164.0`) was
STARTED for 15 s against the LIVE Elasticsearch through a read-only `kubectl port-forward`, with the
live `otel.yml` (byte-identical to the 10-29 copy) rewritten only for endpoint, loopback ports and a
scratch queue directory, and a dummy `ES_PASSWORD` (no producer pointed at it, so nothing was sent).
Same gate function as §2.3(c)/§3 step 4/§4.0:

| run | process | `Everything is ready…` lines | fatal lines | `es info returned status 401` | verdict |
|---|---|---|---|---|---|
| live config, ES reachable | ran until SIGTERM | **1** | 0 | **3** (one each: `elasticsearch/logs`, `/metrics`, `/traces`; level `warn`, from `es_version.go:90`) | `STARTUP_OK` |
| `num_consumers: notanint` | exit 1 | 0 | 1 (`Error: failed to get config: cannot unmarshal the configuration…`) | 0 | `STARTUP_FAIL` |
| ES unreachable (no port-forward) | ran | 1 | 0 | 0 (3 × `fetching es info: context deadline exceeded`) | `STARTUP_OK` + `ES_INFO_OTHER` note |
| empty log / log holding two starts / a lone `panic:` line | — | 0 / 2 / 0 | 0 / 0 / 1 | — | `STARTUP_FAIL` ×3 |

Reading it: (1) the healthy start logs **zero** `Connected to Elasticsearch` and three 401 warnings,
exactly as the reviewer found — the 401 is EXPECTED and informational; (2) a broken config prints
`Error: failed to get config`, NOT `invalid configuration` or `panic`, so the fatal regex carries
that text too, and the `ready == 1` count is the load-bearing half; (3) an unreachable ES does not
stop the service from reporting ready, so this gate does NOT vouch for ES reachability — §4.2/§4.3 do.
The live 0.161.0 pod's log (14,188 lines, 25 days old) holds 0 `Everything is ready` lines — rotated —
which is why the baseline above comes from a fresh start and why the new pod's log must be captured
immediately after the roll (§3 step 4). Not rehearsed in-cluster: a planner creates no cluster object.

### 1.3c Re-measured 2026-11-06 (refresh in place, operator asked to execute in the attended NOW window)

- **Premise 3 failure root cause: abbreviation drift, not a config change.** The premise printed
  `429791200` (9 chars) against an expected 8-char `42979120`. `git rev-parse 429791200` =
  `429791200b7eabd0bf94586a60e41aa7de8eb347` (2026-09-28, "clear 0.161.0 config deprecations"), the
  same commit as before, and it predates the 10-29/11-02 validations. Premise now `expect_matches ^42979120`.
- **Live config == git config.** `configmap/edot-collector-config` `otel.yml` (19,505 bytes, sha256
  `063d47a846f28ea7f3ba87d868961555bf7059038721888eb71c488676b96a5d`) differs from the git
  `configmap.yaml` value in exactly three lines (217/253/289): `$${env:ES_PASSWORD}` in git vs
  `${env:ES_PASSWORD}` live, the Flux postBuild `$$` unescape. Nothing else.
- **Validation on the real 0.164.0 binary** (official darwin_arm64 release, `otelcol-contrib version
  0.164.0`) of that live file: positive `validate exit=0`, empty output; `num_consumers: notanint`
  exit 1 (`failed to get config: cannot unmarshal`); `IsMapp` exit 1 (`processors::transform/strip-k8s-
  managedfields: unable to parse OTTL statement ... undefined function "IsMapp"`). Startup rehearsal
  against live ES (port-forward, dummy password): `ready_lines=1 fatal_lines=0 es_info_401=3
  es_info_connected=0 es_info_other=0` STARTUP_OK; notanint start exit 1 STARTUP_FAIL; empty log
  STARTUP_FAIL. Identical to 11-02. The in-cluster dry pod (§2.3(b)) was NOT run (a planner creates no
  cluster object); the window agent runs it.
- **Target:** Docker Hub `0.164.0` list digest still
  `sha256:340c9ca6a36617084c6661bdc4f0fe92b7cda5a805d61673ec8db375fddc522b`; tags `0.164.1`, `0.164.2`,
  `0.165.0` all HTTP 404; releases-repo latest is still `v0.164.0` (2026-10-26). No newer image exists.
- **PR #324:** OPEN, MERGEABLE, title `... ( 0.161.0 → 0.164.0 )`, all 4 checks SUCCESS (last run
  2026-10-27), branch `renovate/otel-opentelemetry-collector-contrib-0.x`.
- **Live:** deployment image `:0.161.0`, pod `edot-collector-7dbd97b8d8-vzdzj` (start 2026-10-08),
  imageID `...@sha256:fd328de2552466ad78385e1b1289c3f2402b1c45f265b252aab1955b42845ac1` (= §5.1
  rollback digest, unchanged). ES `8.19.20 green`, kmsg-heartbeat 3/3, PVC `edot-collector-queue` Bound.
  No commits in 3 days touching kube-prometheus-stack / otel-operator / elasticsearch / eck-operator /
  edot-collector.
- **Baselines now (15m):** log records 24,395; metric points 1,908,104 (MP_BASE for §4.1);
  `docs.processed` success 829,360, no non-success outcome; `dropping cumulative temporality` 360/1h
  (DROP_BASE unchanged, F-76387378 pre-existing).
- **Release notes 0.161 -> 0.164 vs this config:** no new releases since the §1.2 reading (0.164.0 is
  still the newest); §1.2 conclusions stand unchanged.

### 1.4 Why `risk: medium` despite a clean changelog

Blast radius and failure mode: **one replica**, the only OTLP path into Elasticsearch for every
namespace (measured 15m on 2026-10-29: 23,720 log records, 1,865,345 metric points, 813,716
per-doc `success` outcomes, no non-success outcome); also the Talos kmsg sink on `192.168.55.18`,
where **a collector restart is the documented trigger for a per-node kmsg-sender stall**
(docs/troubleshooting/node-reboot-observability.md). Its failure is silent: pod Ready, health 200,
telemetry gone.

### 1.5 Supersession of edot-collector-0.163.2 (done 2026-11-02)

This plan **supersedes `edot-collector-0.163.2`**, which could not execute as written: PR #324's
title reads `→ 0.164.0`, so its §2.2 gate STOPs, its §2.2 digest / §2.3 binary / §3 grep are pinned
to 0.163.2, and it carried the same unpassable `Connected to Elasticsearch` gate (§1.3b).
`maintenance-plan.py` had reported `ambiguous_matches: pr324 -> edot-collector-0.163.2, also
edot-collector-0.164.0`. Applied in the amendment that produced this text:
- `edot-collector-0.163.2`: `status: superseded`, `superseded_by: edot-collector-0.164.0`,
  `window: null`, `review: null` (the README convention used by `coredns-1.48.1`,
  `redis-fleet-8.10.2`); its `nightly:2026-11-10` slot is carried here as the SUGGESTED `window:`
  comment, not stamped (this plan is `draft`, review null);
- the dead refs 0.163.2 carried (`coredns-1.48.1`, `talos-linux-1.14.2`, `home-assistant-2026.10.2`,
  all superseded/executed) are deliberately NOT carried here.

Still owed by the orchestrator (planner touches two files only): the home-operation go/no-go issue
keyed on `edot-collector-0.163.2` moves to this plan_id, and the reciprocal refs naming
`edot-collector-0.163.2` in `otel-operator-0.25.1`, `otel-operator-0.26.1`, `talos-linux-1.14.4`,
`talos-linux-1.14.5` and `grafana-14.1.0` become `edot-collector-0.164.0`.

**Repo-process note.** `runbooks/maintenance/plans/README.md` §"When the held target MOVES" says a
DRIFTED target is refreshed **in place** under the old `plan_id`. This file was written under a new id
because the dispatch named `edot-collector-0.164.0` explicitly, which orphans a vetted slot every time.

## 2) Pre-checks

Run in order. Any failure stops the plan; do not go on to §3.

```bash
cd /Users/mu/code/cberg-home-nextgen
# 2.1 — premises (re-run mechanically)
.venv/bin/python3 runbooks/plan-premises.py edot-collector-0.164.0
# PASS: all four premises PASS (premise 3 is a prefix regex since 2026-11-06 - see 1.3c).
# If ONLY image-is-still-0.161.0 fails and prints ...:0.164.0 -> Step 0 already merged #324:
# skip §3 steps 2-4, do §3 step 5 + all of §4 as post-hoc verification.

# 2.1b — tonight's Step 0 batch must not have moved the instrument or the producers.
git fetch origin main
git log --since='6 hours ago' --format='%h %s' origin/main -- \
  kubernetes/apps/monitoring/kube-prometheus-stack kubernetes/apps/monitoring/otel-operator \
  kubernetes/apps/monitoring/elasticsearch kubernetes/apps/monitoring/eck-operator
# PASS: prints NOTHING (path-scoped on purpose: a subject grep for "eck" matched every "pre-check"
#   commit when dry-tested 2026-10-29).
# FAILS AS: any commit line, e.g. a kube-prometheus-stack bump (open PR #428 92.11.1 -> 92.14.1 has no
#   plan and could land via Step 0), an opentelemetry-kube-stack bump (#351/#356) or an ES/ECK change
#   -> STOP, reslot: §4 reads Prometheus and ES through those exact components. Can-fail shown
#   2026-10-29 with --since='40 days ago': prints `d997b0fa fix(container): update kube-prometheus-stack
#   ( 92.11.0 → 92.11.1 ) (#427)` among others.

# 2.2 — HARD GATE: PR #324 still targets 0.164.0 and is mergeable, AND the multi-arch tag 0.164.0
# exists as a manifest list containing linux/amd64 with the digest measured at planning time.
gh pr view 324 --json state,mergeable,title -q '.state+" "+.mergeable+" "+.title'
# PASS: "OPEN MERGEABLE feat(container): update otel/opentelemetry-collector-contrib ( 0.161.0 → 0.164.0 )"
# FAILS AS: MERGED/CLOSED, CONFLICTING, or a different target in the title -> STOP
#   (retarget = refresh this plan in place; README "When the held target MOVES").
T=$(curl -s "https://auth.docker.io/token?service=registry.docker.io&scope=repository:otel/opentelemetry-collector-contrib:pull" | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
curl -s -D /private/tmp/claude-501/edot-0164-hdr.txt -o /private/tmp/claude-501/edot-0164-manifest.json \
  -H "Authorization: Bearer $T" \
  -H "Accept: application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.list.v2+json" \
  https://registry-1.docker.io/v2/otel/opentelemetry-collector-contrib/manifests/0.164.0
python3 - <<'EOF'
import json,re
h=open('/private/tmp/claude-501/edot-0164-hdr.txt').read()
st=re.search(r'^HTTP/\S+ (\d+)',h,re.M).group(1)
dg=(re.search(r'(?im)^docker-content-digest:\s*(\S+)',h) or [None,None])[1]
if st!='200': print('TAG_MISSING http',st,'-> BLOCKED'); raise SystemExit
m=json.load(open('/private/tmp/claude-501/edot-0164-manifest.json'))
plats=[(x['platform']['os'],x['platform']['architecture']) for x in m.get('manifests',[])]
ok=('linux','amd64') in plats
print('TAG_OK' if ok else 'NO_AMD64', dg, plats)
if ok: open('/private/tmp/claude-501/edot-0164-target-digest','w').write(dg)
EOF
cat /private/tmp/claude-501/edot-0164-target-digest; echo
# PASS: `TAG_OK sha256:340c9ca6a36617084c6661bdc4f0fe92b7cda5a805d61673ec8db375fddc522b [... ('linux','amd64') ...]`
#   (exactly this digest, 7 linux platforms, measured 2026-10-29; a DIFFERENT digest = upstream re-pushed
#   the tag -> STOP and re-read the release before proceeding).
# CAN FAIL — demonstrated 2026-10-29 with the same request + parse on tag 0.164.1: `TAG_MISSING http 404`.
#   Also NO_AMD64 / empty digest file -> STOP.

# 2.3 — GATE: validate the LIVE config against the NEW binary, two ways.
# (a) locally, upstream release binary (no cluster object created):
mkdir -p /private/tmp/claude-501/otel1640 && cd /private/tmp/claude-501/otel1640
gh release download v0.164.0 -R open-telemetry/opentelemetry-collector-releases \
  -p 'otelcol-contrib_0.164.0_darwin_arm64.tar.gz' --clobber
tar xzf otelcol-contrib_0.164.0_darwin_arm64.tar.gz otelcol-contrib
./otelcol-contrib --version                        # MUST print: otelcol-contrib version 0.164.0
kubectl get cm -n monitoring edot-collector-config -o jsonpath='{.data.otel\.yml}' > live-otel.yml
ES_PASSWORD=dummy ./otelcol-contrib validate --config=live-otel.yml > pos.out 2>&1; echo "validate exit=$?"
cat pos.out
# NEGATIVE CONTROLS — each must exit NON-zero, proving this gate can fail:
python3 -c "t=open('live-otel.yml').read();open('neg.yml','w').write(t.replace('num_consumers: 4','num_consumers: notanint',1))"
ES_PASSWORD=dummy ./otelcol-contrib validate --config=neg.yml > neg.out 2>&1; echo "negative-control exit=$?"
head -1 neg.out
python3 -c "t=open('live-otel.yml').read();assert 'IsMap(log.body)' in t;open('neg2.yml','w').write(t.replace('IsMap(log.body)','IsMapp(log.body)',1))"
ES_PASSWORD=dummy ./otelcol-contrib validate --config=neg2.yml > neg2.out 2>&1; echo "ottl-control exit=$?"
head -1 neg2.out
cd /Users/mu/code/cberg-home-nextgen
# PASS: `validate exit=0` with EMPTY pos.out AND `negative-control exit=1` with neg.out starting
#   "Error: failed to get config: cannot unmarshal" AND `ottl-control exit=1` with neg2.out naming
#   "transform/strip-k8s-managedfields: unable to parse OTTL statement" (all three measured exactly so
#   on 2026-10-29). The ottl-control is the proof that the managedFields strip is parsed by 0.164.0.
# FAILS AS: non-zero exit naming a rejected key/type/OTTL statement -> BLOCKED (the fix is a config
#   change = a different plan). Remember §1.3: blind to unknown ES-exporter keys.
#
# (b) in-cluster with the linux image that will actually run (only after 2.2 passed).
# EVERY command carries `-n monitoring` (kube context namespace is `default`, where the configmap does
# not exist). Detached run + read the container's own exitCode — NOT `-i --rm`. monitoring is PSA
# `privileged`.
edot_validate() {  # $1 = pod name, $2 = --config path, $3 = mount cm? (yes|no)
  local OV IMG=otel/opentelemetry-collector-contrib:0.164.0
  if [ "$3" = yes ]; then
    OV='{"spec":{"securityContext":{"runAsNonRoot":true,"runAsUser":10001,"runAsGroup":10001},"containers":[{"name":"'"$1"'","image":"'"$IMG"'","command":["/otelcol-contrib","validate","--config='"$2"'"],"env":[{"name":"ES_PASSWORD","value":"dummy-validate-only"}],"volumeMounts":[{"name":"cfg","mountPath":"/config","readOnly":true}]}],"volumes":[{"name":"cfg","configMap":{"name":"edot-collector-config"}}]}}'
  else
    OV='{"spec":{"securityContext":{"runAsNonRoot":true,"runAsUser":10001,"runAsGroup":10001},"containers":[{"name":"'"$1"'","image":"'"$IMG"'","command":["/otelcol-contrib","validate","--config='"$2"'"]}]}}'
  fi
  kubectl delete pod -n monitoring "$1" --ignore-not-found >/dev/null
  kubectl run "$1" -n monitoring --restart=Never --image="$IMG" --overrides="$OV" >/dev/null
  local PH=""
  for i in $(seq 1 60); do
    PH=$(kubectl get pod -n monitoring "$1" -o jsonpath='{.status.phase}')
    case "$PH" in Succeeded|Failed) break ;; esac
    sleep 3
  done
  case "$PH" in Succeeded|Failed) ;; *)
    echo "NOT_TERMINAL phase=$PH -> STOP; pod $1 left for: kubectl describe pod -n monitoring $1"
    return 1 ;; esac
  echo "phase=$PH exitCode=$(kubectl get pod -n monitoring "$1" -o jsonpath='{.status.containerStatuses[0].state.terminated.exitCode}')"
  kubectl logs -n monitoring "$1" > "/private/tmp/claude-501/$1.out" 2>&1
  cat "/private/tmp/claude-501/$1.out"
  kubectl delete pod -n monitoring "$1" --ignore-not-found >/dev/null
}
edot_validate edot-validate-01640     /config/otel.yml      yes
edot_validate edot-validate-01640-neg /nonexistent/otel.yml no
grep -ic 'nonexistent/otel.yml' /private/tmp/claude-501/edot-validate-01640-neg.out
# PASS (positive): `phase=Succeeded exitCode=0` and the log matches nothing for (case-insensitive)
#   error|invalid|cannot unmarshal.
# PASS (negative control): `phase=Failed`, NON-zero exitCode AND the grep prints >= 1. A non-zero exit
#   WITHOUT that path means the pod failed for another reason (pull, admission, arch) — investigate.
# FAILS AS: positive pod Failed / error text -> BLOCKED. NOT_TERMINAL after 180s = pull or volume
#   problem -> STOP, describe, delete the pod by hand. "exec format error" = wrong arch -> STOP.
# (This in-cluster shape is the predecessor's, vetted 2026-10-23; it was NOT re-run at planning time —
#  no cluster object is created by a planner.)

# (c) STARTUP-LOG GATE rehearsal on the REAL 0.164.0 binary against the LIVE Elasticsearch (read-only
# port-forward, dummy password, scratch queue dir; no producer points at it, so nothing is sent).
cat > /private/tmp/claude-501/edot-startup-gate.sh <<'EOF'
edot_startup_gate() {  # $1 = captured log of the NEW container's startup
  local N BAD
  N=$(grep -c 'Everything is ready. Begin running and processing data.' "$1")
  BAD=$(grep -ciE '^Error:|failed to get config|panic|invalid configuration|exec format' "$1")
  echo "ready_lines=$N fatal_lines=$BAD es_info_401=$(grep -c 'es info returned status 401' "$1") es_info_connected=$(grep -ci 'Connected to Elasticsearch' "$1") es_info_other=$(grep 'failed to fetch Elasticsearch info' "$1" | grep -vc 'es info returned status 401')"
  if [ "$N" = 1 ] && [ "$BAD" = 0 ]; then echo STARTUP_OK; else echo STARTUP_FAIL; fi
}
EOF
. /private/tmp/claude-501/edot-startup-gate.sh
D=/private/tmp/claude-501/otel1640   # the directory (a) filled
cd "$D"
python3 - <<'EOF'
import os
t=open('live-otel.yml').read()
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
rm -rf queue
kubectl port-forward -n monitoring svc/elasticsearch-es-http 19211:9200 >/dev/null 2>&1 & PF=$!
sleep 4
ES_PASSWORD=dummy ./otelcol-contrib --config=scratch.yml > start-pos.log 2>&1 & CP=$!
sleep 15; kill -TERM $CP; wait $CP 2>/dev/null
ES_PASSWORD=dummy ./otelcol-contrib --config=scratch-neg.yml > start-neg.log 2>&1; echo "neg exit=$?"
kill $PF 2>/dev/null
echo "--- POSITIVE (live config):";  edot_startup_gate start-pos.log
echo "--- NEGATIVE (num_consumers: notanint):"; edot_startup_gate start-neg.log
: > start-empty.log; echo "--- NEGATIVE (empty log):"; edot_startup_gate start-empty.log
cd /Users/mu/code/cberg-home-nextgen
# PASS: positive = `ready_lines=1 fatal_lines=0 es_info_401=3 ...` + STARTUP_OK; BOTH negatives = STARTUP_FAIL.
#   `es_info_401=3` with `es_info_connected=0` is the EXPECTED healthy shape on 0.164.0 (§1.3b). If the
#   negatives print STARTUP_OK the gate cannot fail: STOP.
# FAILS AS: positive STARTUP_FAIL (config rejected at start, or the binary does not run) -> BLOCKED.
#   DRY-RUN 2026-11-02 (bash AND zsh, real binary, live ES): positive `ready_lines=1 fatal_lines=0
#   es_info_401=3 es_info_connected=0 es_info_other=0` STARTUP_OK; num_consumers control `ready_lines=0
#   fatal_lines=1` STARTUP_FAIL (exit 1); empty log STARTUP_FAIL. Local port 19211 must be free.


# 2.4 — BASELINES for §4, each over the SAME window its gate uses.
# Measured 2026-10-29 for reference (yours will differ):
#   sent log records [15m]          23,720   (7d min of the same expression 15,722)
#   sent metric points [15m]     1,865,345
#   docs.processed success [15m]   813,716   non-success [15m]: EMPTY
# PRE-EXISTING baseline, NOT this plan's (sweep finding F-76387378, health/monitor, open since 2026-10-31):
# the 0.161.0 pod already logs "dropping cumulative temporality" metric points. Record it NOW so a
# post-roll health-check warning is not attributed to 0.164.0 (same pipeline the health check runs):
kubectl logs -n monitoring deploy/edot-collector --since=1h | grep -oE "dropping [a-z]+ [a-z]+|invalid number data point" | sort | uniq -c
kubectl logs -n monitoring deploy/edot-collector --since=1h | grep -oE 'histogram \\"[a-zA-Z0-9_]+' | sort -u | head -8
# Measured 2026-11-02 on the 0.161.0 pod: `360 dropping cumulative temporality`, and the second command
# prints the single family tag `histogram \"otelcol`. Record DROP_BASE=360 and the tag.
P=/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query
kubectl get --raw "${P}?query=sum(increase(otelcol_exporter_sent_log_records_total[15m]))"; echo
kubectl get --raw "${P}?query=sum(increase(otelcol_exporter_sent_metric_points_total[15m]))"; echo
kubectl get --raw "${P}?query=sum%20by%20(outcome)%20(increase(%7B__name__%3D%22otelcol.elasticsearch.docs.processed_total%22%7D%5B15m%5D))"; echo
# Record the metric-points value as MP_BASE for §4.1.

# 2.4b — PRE-ROLL ES CONTROL (content-based, run BEFORE §3; the pipeline fails silently).
# Proves, in Elasticsearch itself, that documents are landing NOW through the 0.161.0 pod, so §4.3's
# post-roll counts have a measured "before". `_count` over the last 10 minutes on both data streams plus
# the per-node kmsg sources.
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
kill $PF 2>/dev/null
# PASS: both streams PRE_OK (count > 0) and PRE_KMSG_OK and the control prints 0. Record the counts.
# FAILS AS: PRE_FAIL / count 0 / KeyError / 401 (ES unreachable or ingestion ALREADY dead) -> STOP, do not
#   roll: a post-roll failure would be misattributed. The future-window control proves the range query
#   discriminates (0 vs the positive counts). This is the "before" half; §4.3 is the "after" half and
#   additionally requires docs newer than the new pod's Ready timestamp.

# 2.5 — pre-state is clean
kubectl get pods -n monitoring -l app=edot-collector -o wide
kubectl get pvc -n monitoring edot-collector-queue
kubectl get ds -n monitoring kmsg-heartbeat
kubectl get elasticsearch -n monitoring -o jsonpath='{range .items[*]}{.metadata.name} {.spec.version} {.status.health}{"\n"}{end}'
flux get kustomizations -n monitoring | awk 'NR==1 || $4 != "True"'
# PASS: collector 1/1 Running, PVC Bound, DaemonSet 3/3, ES `elasticsearch 8.19.20 green` (a 9.4+
#   version here changes §1.2's histogram verdict -> STOP and re-assess), no kustomization off True.
```

## 3) Steps (GitOps)

**1. Silence expected rollout noise and mark the update active.** Every alertname below exists in
`kubernetes/apps/monitoring/kube-prometheus-stack/app/otel-collector-alerts.yaml`. Deliberately NOT
silenced: the three `Es*ExporterSeriesMissing` absent() guards, `TalosKmsgPipelineDown`,
`TalosKernelLogsMissingFromNode` — a real disappearance or a stalled kmsg sender must still page.

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 >/dev/null 2>&1 & PF=$!
sleep 3
NOW=$(python3 -c "from datetime import *;print(datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
END=$(python3 -c "from datetime import *;print((datetime.now(timezone.utc)+timedelta(hours=3)).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
curl -s -X POST localhost:9093/api/v2/silences -H 'Content-Type: application/json' -d '{
  "matchers":[{"name":"namespace","value":"monitoring","isRegex":false,"isEqual":true},
              {"name":"alertname","value":"EdotCollectorDown|OtelCollectorExportFailed|OtelCollectorRecordsRefused|OtelCollectorQueueFull|EdotCollectorESAuthError|EsMetricsIngestionStalled|EsLogIngestionStalled|EsExportQueueStuckFull","isRegex":true,"isEqual":true}],
  "startsAt":"'"$NOW"'","endsAt":"'"$END"'","createdBy":"maintenance-window-agent",
  "comment":"edot-collector 0.161.0->0.164.0 - expected rollout noise. auto-expires 3h"}' \
  | tee /private/tmp/claude-501/edot-01640-silence.json; echo   # prints {"silenceID":"..."}; empty = NOT silenced
kill $PF 2>/dev/null
runbooks/update-marker.sh add edot-collector monitoring 3 "0.161.0->0.164.0 bump"
```

**2. Merge the Renovate PR** (squash, the repo's convention for Renovate PRs).

```bash
GEN_BEFORE=$(kubectl get deployment edot-collector -n monitoring -o jsonpath='{.metadata.generation}')
gh pr merge 324 --squash --delete-branch
git fetch origin main && git merge --ff-only origin/main
BUMP_SHA=$(git log -1 --format=%H -- kubernetes/apps/monitoring/edot-collector/app/deployment.yaml)
git show --stat "$BUMP_SHA" | head -8      # exactly one file: .../edot-collector/app/deployment.yaml
grep -n 'image: otel/opentelemetry-collector-contrib' kubernetes/apps/monitoring/edot-collector/app/deployment.yaml
echo "$BUMP_SHA" > /private/tmp/claude-501/edot-01640-bump-sha
# PASS: the grep prints `image: otel/opentelemetry-collector-contrib:0.164.0`.
```

**3. Reconcile and watch the Recreate roll.** The Flux Kustomization lives in namespace
**`monitoring`**; with `-n flux-system` the command errors and `rollout status` then green-lights
the OLD generation. `strategy: Recreate` (measured) is load-bearing (RWO Longhorn PVC at
`replicas: 1`). Do not hand-delete pods mid-roll.

```bash
flux reconcile kustomization edot-collector -n monitoring --with-source
kubectl get deployment edot-collector -n monitoring -o jsonpath='{.spec.template.spec.containers[0].image}'; echo
GEN_AFTER=$(kubectl get deployment edot-collector -n monitoring -o jsonpath='{.metadata.generation}')
echo "generation $GEN_BEFORE -> $GEN_AFTER"
kubectl rollout status deployment/edot-collector -n monitoring --timeout=180s
kubectl get pods -n monitoring -l app=edot-collector -o wide
kubectl get pods -n monitoring -l app=edot-collector \
  -o jsonpath='{.items[0].status.conditions[?(@.type=="Ready")].lastTransitionTime}' \
  > /private/tmp/claude-501/edot-01640-ready-ts
cat /private/tmp/claude-501/edot-01640-ready-ts; echo   # MUST be non-empty and AFTER the merge
```

**HARD GATE:** the printed image reads `:0.164.0` AND `GEN_AFTER > GEN_BEFORE` AND exactly one pod
is listed, `1/1 Running`. If not, nothing rolled — do not continue into §4, whose gates would all
pass on the old binary.

**4. Read the startup log NOW** (§4.0's startup gate; startup lines rotate out within days — the
25-day-old 0.161.0 pod no longer holds its own).

```bash
kubectl logs -n monitoring deploy/edot-collector > /private/tmp/claude-501/edot-01640-startup.log
. /private/tmp/claude-501/edot-startup-gate.sh   # written by §2.3(c); re-create it from there on a new shell/host
edot_startup_gate /private/tmp/claude-501/edot-01640-startup.log
kubectl get pods -n monitoring -l app=edot-collector -o jsonpath='{.items[0].status.containerStatuses[0].restartCount}'; echo
```

**HARD GATE:** `STARTUP_OK` (exactly one `Everything is ready. Begin running and processing data.`, no
`Error:`/`failed to get config`/`panic`/`invalid configuration`/`exec format` line) AND `restartCount`
`0`. `kubectl logs` shows only the CURRENT container, so a crash-looping pod can still print a single
ready line — the restart count is the other half. **EXPECTED, informational, NOT a failure:** three
`warn` lines `failed to fetch Elasticsearch info ... "es info returned status 401"` (one per ES
exporter) and `es_info_connected=0` — the version probe sends no credentials (§1.2, §1.3b). Any
`es_info_other>0` (a non-401 probe error such as `context deadline exceeded`) is recorded in the
report but decides nothing by itself: ES reachability is gated by §4.2/§4.3.

**5. Kick the kmsg heartbeat (second commit, ONLY after step 3's hard gate).** `kmsg-heartbeat`
writes one `cberg-kmsg-heartbeat node=<node>` line into each node's kernel ring buffer when its pod
starts, then hourly. Restarting the pods via a pod-template annotation makes every node emit a line
within about a minute while the new collector is listening.

DRY-TESTED 2026-10-29 with macOS BSD sed on a scratch copy of the real file (exit 0), and the result
was accepted by `kubectl apply --dry-run=server -n monitoring` (`daemonset.apps/kmsg-heartbeat
configured (server dry run)`). The anchor is the 8-space-indented template label (unique; the
top-level label has 4 spaces).

```bash
REV="$(date -u +%Y-%m-%dT%H%M)"
sed -i '' -e '/^        app.kubernetes.io\/part-of: edot-collector$/a\
      annotations:\
        cberg.dev/kmsg-heartbeat-kick: "'"$REV"'"
' kubernetes/apps/monitoring/edot-collector/app/kmsg-heartbeat-daemonset.yaml
git diff kubernetes/apps/monitoring/edot-collector/app/kmsg-heartbeat-daemonset.yaml
```

The dry-test (`diff original scratch`, REV=2026-10-29.1) showed exactly this ONE hunk:

```
51a52,53
>       annotations:
>         cberg.dev/kmsg-heartbeat-kick: "2026-10-29.1"
```

Hunk missing → the anchor did not match: STOP and edit by hand. Two hunks → someone already added a
template `annotations:` key: `git checkout -- <file>`, then add only the annotation line under it.

```bash
git fetch origin main && git merge --ff-only origin/main
MSG=/private/tmp/claude-501/msg-edot-01640-kick-$(date +%s).txt
printf '%s\n' "chore(monitoring): kick kmsg-heartbeat after edot-collector 0.164.0 roll (plan edot-collector-0.164.0)" > "$MSG"
git commit --only kubernetes/apps/monitoring/edot-collector/app/kmsg-heartbeat-daemonset.yaml -F "$MSG"
git show --stat HEAD       # exactly one file: kmsg-heartbeat-daemonset.yaml
git log -1 --format=%s     # MUST be your subject; amend before pushing if not
git push origin main
flux reconcile kustomization edot-collector -n monitoring --with-source
kubectl rollout status ds/kmsg-heartbeat -n monitoring --timeout=180s
kubectl get pods -n monitoring -l app.kubernetes.io/name=kmsg-heartbeat -o wide
# PASS: 3 pods, all with a fresh AGE, one per node.
```

**6. Wait 15 minutes** after the Ready timestamp from step 3, so every `[15m]` window in §4 lies
entirely after the new pod's start. A straddling window passes on pre-roll data.

## 4) Verification

### 4.0 Floor + the new binary is really serving

CONTROL: metric target_info — `count(target_info{job="edot-collector","service.version"="0.164.0"})` must be 1

```bash
kubectl get deployment edot-collector -n monitoring -o jsonpath='{.status.readyReplicas}'; echo
TARGET_DIGEST=$(cat /private/tmp/claude-501/edot-0164-target-digest)
test -n "$TARGET_DIGEST" || echo "NO_TARGET_DIGEST -> FAIL"
LIVE_ID=$(kubectl get pods -n monitoring -l app=edot-collector -o jsonpath='{.items[0].status.containerStatuses[0].imageID}')
echo "live: $LIVE_ID"
case "$LIVE_ID" in *"$TARGET_DIGEST") echo "DIGEST_OK" ;; *) echo "DIGEST_MISMATCH" ;; esac
P=/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query
for v in 0.164.0 0.161.0; do
  Q='count(target_info{job="edot-collector","service.version"="'$v'"})'
  E=$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))" "$Q")
  echo -n "service.version=$v: "
  kubectl get --raw "${P}?query=${E}" | python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];print(r[0]['value'][1] if r else 'EMPTY')"
done
# Startup gate (re-evaluated here from the log §3 step 4 captured; do NOT grep "Connected to Elasticsearch" - see §1.3b)
. /private/tmp/claude-501/edot-startup-gate.sh
edot_startup_gate /private/tmp/claude-501/edot-01640-startup.log
kubectl get pods -n monitoring -l app=edot-collector -o jsonpath='restartCount={.items[0].status.containerStatuses[0].restartCount}'; echo
```

**PASS (all gating):** `readyReplicas` 1 and `DIGEST_OK` (imageID carries the manifest-list
digest — today's 0.161.0 pod shows `…@sha256:fd328de2…5ac1`, the tag's list digest);
`service.version=0.164.0: 1` (the `0.161.0` line may read 1 inside the 5-min staleness window, must
read `EMPTY` by T+15m); `STARTUP_OK` and `restartCount=0` (one `Everything is ready…` line, no fatal
line). The three `es info returned status 401` warnings are EXPECTED (§1.3b) and never a FAIL.

**Both sides demonstrated.** Metric side 2026-10-29: the identical loop printed `0.161.0: 1` and
`0.164.0: EMPTY`. Startup-gate side 2026-11-02 on a real 0.164.0 start (§1.3b, §2.3(c)): healthy
config -> `ready_lines=1 fatal_lines=0 es_info_401=3` `STARTUP_OK`; `num_consumers: notanint` ->
`ready_lines=0 fatal_lines=1` `STARTUP_FAIL`; empty log -> `STARTUP_FAIL`; two starts in one log
(`ready_lines=2`) -> `STARTUP_FAIL`. (The superseded gate `Connected to Elasticsearch >= 3` printed 0 on
that same healthy start - it could not pass.)

**FAILS AS:** `DIGEST_MISMATCH` (not the §2.2 list); 0.164.0 EMPTY (scrape broke or other binary);
`STARTUP_FAIL` (no/duplicate ready line, or `Error: failed to get config` / `panic` / `invalid
configuration` / `exec format`); `restartCount` > 0 (the container restarted after start - read
`kubectl logs --previous` before deciding; revert per §5.1). ES reach/auth problems are NOT caught here
(the probe is unauthenticated and always warns): they show as non-success outcomes in §4.2 or missing
documents in §4.3.

### 4.1 Telemetry still FLOWS

CONTROL: metric otelcol_exporter_sent_log_records_total — `sum(increase([15m]))` must be >= 7,500 (floor)
CONTROL: metric otelcol_exporter_sent_metric_points_total — `sum(increase([15m]))` within ±20% of MP_BASE (band)

```bash
P=/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query
kubectl get --raw "${P}?query=sum(increase(otelcol_exporter_sent_log_records_total[15m]))"; echo
kubectl get --raw "${P}?query=sum(increase(otelcol_exporter_sent_metric_points_total[15m]))"; echo
```

**PASS:** log records **>= 7,500** — a floor at about half the 7d minimum of this exact expression
(15,722, measured 2026-10-29); log volume spreads too widely for a band. Metric points **within ±20%
of MP_BASE** (this series is flat to ~1%), which catches a partial pipeline loss a floor would miss.

**FAILS AS:** an **empty `result` array** (metric stopped being exported under that name — the §1.3
ES-key blind spot; empty is FAIL, never skip); a value under the floor or outside the band.

**The ±20% band is tight right after a Recreate — first suspect it, not the binary, if the metric
points miss NARROWLY.** The swap restarts `cumulative_to_delta` (the first sample of every cumulative
stream becomes its baseline and emits nothing) and the OTLP producers reconnect during the first
minutes; both fall inside the first `[15m]` window (an estimate of a few percent, NOT measured — the
band was set from a 1%-flat series that had never been read across a restart). Rule: a first read
inside ±20% passes; a first read between ±20% and ±30% is NOT yet a FAIL — re-read once at T+30m after
Ready (window wholly past the settle) and it must then sit inside ±20%; beyond ±30% at the first read,
or still outside ±20% at T+30m, is a FAIL (§5.1). The log-records floor and §4.2 do not have this
slack and are never re-read for it.

### 4.2 Elasticsearch is not silently REJECTING

CONTROL: metric otelcol.elasticsearch.docs.processed_total — (a) `outcome="success"` present and non-zero; (b) `outcome!~"success|retried"` empty or zero

Use the DOTTED name (the telemetry pins keep dots; the underscored form reads empty on both sides
and can never fail — docs/sops/monitoring.md).

```bash
P=/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query
kubectl get --raw "${P}?query=sum%20by%20(outcome)%20(increase(%7B__name__%3D%22otelcol.elasticsearch.docs.processed_total%22%7D%5B15m%5D))"; echo
kubectl get --raw "${P}?query=sum%20by%20(outcome)%20(increase(%7B__name__%3D%22otelcol.elasticsearch.docs.processed_total%22%2Coutcome!~%22success%7Cretried%22%7D%5B15m%5D))"; echo
```

**PASS:** (a) returns `outcome="success"`, non-zero (baseline 813,716 per 15m, measured 2026-10-29),
AND (b) empty or zeros.

**Can fail:** the predecessor measured `max_over_time` of (b) over 7d returning
`internal_server_error` and `timeout` outcomes in the tens of thousands, so the query reads real
non-success outcomes when they exist; a missing `success` series in (a) is itself a FAIL. 0.164.0's
extra pre-connection retries (#52102) land under `retried`, which (b) excludes by design.

**Not this plan's (F-76387378):** the health-check warning `edot ES dropped metric points ... /h` and
the `dropping cumulative temporality` log lines predate the roll (360/h on the 0.161.0 pod, §2.4,
open since 2026-10-31). They are NOT `docs.processed` non-success outcomes and are not a revert
trigger here. Compare against DROP_BASE: the SAME reason string at about the same rate = unchanged
baseline (note it, do nothing). A NEW reason string (`invalid number data point`, other `dropping …`
text) or a rate several times DROP_BASE after the T+15m window is a change this bump may have
caused -> report it as a regression candidate (`cumulative_to_delta` scope-identity change, §1.2),
but the revert decision stays with the §4.1/§4.2/§4.3 contents gates.

**Attribution:** `failed_client` → binary/config: revert. `timeout`/`internal_server_error` → ES side:
check `_cluster/health` (§4.3) before reverting.

### 4.3 Documents actually LANDED in Elasticsearch, kmsg through the new stanza path

CONTENTS ASSERTION: new documents in both data streams with `@timestamp` after the new pod went
Ready; node `.11`'s kernel lines arrive through `udp_log` and now carry the `scope.name` that only the
0.163+ stanza adapter writes. Measured in ES itself (`_bulk` returns 200 even when items are rejected).

```bash
ES_PW=$(kubectl get secret -n monitoring elasticsearch-es-elastic-user -o jsonpath='{.data.elastic}' | base64 -d)
kubectl port-forward -n monitoring svc/elasticsearch-es-http 19211:9200 >/dev/null 2>&1 & PF=$!
sleep 4
READY_TS=$(cat /private/tmp/claude-501/edot-01640-ready-ts)
test -n "$READY_TS" || echo "NO_READY_TS -> FAIL"
for DS in logs-generic-default metrics-generic.otel-default; do
  echo -n "$DS "
  curl -k -s -u "elastic:$ES_PW" -H 'Content-Type: application/json' \
    -X POST "https://localhost:19211/$DS/_count" \
    -d '{"query":{"range":{"@timestamp":{"gte":"'"$READY_TS"'"}}}}' \
    | python3 -c "import sys,json;print(json.load(sys.stdin).get('count'))"
done
curl -k -s -u "elastic:$ES_PW" -H 'Content-Type: application/json' \
  "https://localhost:19211/logs-generic-default/_search" \
  -d '{"size":0,"query":{"bool":{"filter":[{"term":{"attributes.log_source":"talos-kernel"}},{"range":{"@timestamp":{"gte":"'"$READY_TS"'"}}}]}},"aggs":{"ip":{"terms":{"field":"attributes.net.peer.ip","size":5}},"scoped":{"filter":{"exists":{"field":"scope.name"}}}}}' \
  | python3 -c "import sys,json;d=json.load(sys.stdin);a=d['aggregations'];b={x['key']:x['doc_count'] for x in a['ip']['buckets']};print(b);print('KMSG_OK' if b.get('192.168.55.11',0)>=20 else 'KMSG_FAIL');s=a['scoped']['doc_count'];print('scope.name docs',s,'STANZA_NEW_OK' if s>0 else 'STANZA_NEW_MISSING')"
curl -k -s -u "elastic:$ES_PW" "https://localhost:19211/_cluster/health" \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['status'],d['unassigned_shards'])"
kill $PF 2>/dev/null
```

**PASS:** both datastream counts > 0; `KMSG_OK` (if .11 lands 5–19, re-check once at T+25m before
failing); `STANZA_NEW_OK`; cluster `green`/`yellow` with 0 unassigned.

**Both sides of the scope gate measured 2026-10-29:** talos-kernel docs over the last 7d (>=10,000)
carry **0** with `scope.name` (0.161.0 writes `scope: {}`). Zero after the roll means the stanza path
is NOT the new binary's, or kmsg is not arriving — cross-check with KMSG. A KeyError on
`aggregations` is a FAIL. `traces-generic-default` is not gated (no trace producers; it could only
read empty).

### 4.4 Every node's kmsg SENDER survived the restart (per-node heartbeat gate)

CONTENTS ASSERTION: each of 192.168.55.11/.12/.13 delivered at least one `cberg-kmsg-heartbeat` line
into ES with `@timestamp` after the new collector went Ready — the node's Talos UDP sender is not
stalled on the dead pod IP.

```bash
ES_PW=$(kubectl get secret -n monitoring elasticsearch-es-elastic-user -o jsonpath='{.data.elastic}' | base64 -d)
kubectl port-forward -n monitoring svc/elasticsearch-es-http 19211:9200 >/dev/null 2>&1 & PF=$!
sleep 4
READY_TS=$(cat /private/tmp/claude-501/edot-01640-ready-ts)
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
kill $PF 2>/dev/null
```

**PASS:** the gate prints `HB_OK` with all three IPs, AND the control prints
`HB_FAIL missing=192.168.55.11,192.168.55.12,192.168.55.13`. Positive side measured 2026-10-29: over
7d, 168 heartbeat docs from each of .11/.12/.13 with this wildcard + field shape. If the control does
not print HB_FAIL, the harness is broken and HB_OK means nothing — FAIL.

**Timing:** evaluate at T+5m after §3 step 5's DaemonSet roll; re-evaluate once at T+15m before
declaring a node missing.

**FAILS AS:** `HB_FAIL missing=<ip>` at T+15m while that node's heartbeat pod is Running with a fresh
start = the known **kmsg-sender stall**. **NOT a revert trigger** (reverting restarts the collector
again — the stall trigger itself). Go to §5.3. A missing heartbeat POD (not Running) is a DaemonSet
problem: `kubectl describe pod -n monitoring <pod>`; do not toggle the node.

### 4.5 The exporter series EXIST — direct absent() evaluation

The `Es*ExporterSeriesMissing` and `TalosKmsgPipelineDown` rules carry `for: 15m`, so at T+15m they
are at most `pending`; evaluate their expressions directly instead. Line 3 also proves the
`prometheus/hwerrors` exporter survived 0.164.0's label-sanitization change (§1.2).

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

**PASS:** the first three print `PRESENT`; the fourth (positive control) prints `ABSENT`. If the
control does not print `ABSENT`, the harness is broken: FAIL.

**FAILS AS:** `ABSENT` on line 1 or 2 → exporter series gone under that name → §5. `ABSENT` on line
3 is a FAIL only if §4.3 also printed KMSG_FAIL (the exporter re-registers on the first line, and
§3 step 5 guarantees lines).

## 5) Rollback

### 5.1 Primary — revert the bump commit

The heartbeat-kick commit is a harmless pod-template annotation; leave it (reverting only restarts
the heartbeat pods again).

```bash
BUMP_SHA=$(cat /private/tmp/claude-501/edot-01640-bump-sha)
git fetch origin main && git merge --ff-only origin/main
git revert --no-edit "$BUMP_SHA"
git show --stat HEAD       # exactly deployment.yaml; image back to :0.161.0
git log -1 --format=%s     # MUST read: Revert "feat(container): update otel/opentelemetry-collector-contrib ( 0.161.0 → 0.164.0 ) (#324)"
git push origin main
flux reconcile kustomization edot-collector -n monitoring --with-source   # namespace monitoring
kubectl rollout status deployment/edot-collector -n monitoring --timeout=180s
ROLLBACK_DIGEST=sha256:fd328de2552466ad78385e1b1289c3f2402b1c45f265b252aab1955b42845ac1
LIVE_ID=$(kubectl get pods -n monitoring -l app=edot-collector -o jsonpath='{.items[0].status.containerStatuses[0].imageID}')
case "$LIVE_ID" in *"$ROLLBACK_DIGEST") echo "ROLLBACK_DIGEST_OK" ;; *) echo "ROLLBACK_DIGEST_MISMATCH: $LIVE_ID" ;; esac
```

`$ROLLBACK_DIGEST` is 0.161.0's manifest-list digest, re-measured 2026-10-29 from the running pod's
`imageID`. After the revert: re-capture the Ready timestamp into
`/private/tmp/claude-501/edot-01640-ready-ts` (same command as §3 step 3), re-run §3 step 5 with a
new REV, then §4.1–§4.4 (the revert restarts the collector too, so §4.4 can catch a stall here as
well). A revert that restores the manifest but not the telemetry is not a rollback. Renovate will
re-open the PR; add a deny rule only if the failure was version-caused.

### 5.2 Contingency — the forward-only surface (bbolt queue)

`pvc/edot-collector-queue` holds the persistent sending queue, written by whichever binary runs. No
changelog entry 0.162–0.164 touches the persistent-queue storage format (0.163's queue change is a
deadlock fix in the blocking-offer path; 0.164's `exporterhelper` change only exposes
`PartitionConfig` in the Go API), so 0.161.0 is expected to read it back. **If the reverted pod
crashloops on the queue file:**

```bash
kubectl logs -n monitoring deploy/edot-collector --tail=50 | grep -iE "bolt|storage|queue|corrupt"
```

1. `kubectl scale deploy/edot-collector -n monitoring --replicas=0` to release the RWO volume (Flux
   scales it back on its next reconcile, interval 30m — do steps 2–3 promptly).
2. Wait until `kubectl get pods -n monitoring -l app=edot-collector` prints nothing, then empty the
   queue from a throwaway pod with uid/gid/fsGroup 10001, using the busybox digest already pinned
   and cached for `kmsg-heartbeat`:

   ```bash
   kubectl run edot-queue-wipe -n monitoring --restart=Never \
     --image=busybox:1.38.0@sha256:dc2d74b28e4cf8984fa52af1f39bc7c3d9c73760b41a74d629f5d11b1ab28616 \
     --overrides='{"spec":{"securityContext":{"runAsUser":10001,"runAsGroup":10001,"fsGroup":10001},"containers":[{"name":"edot-queue-wipe","image":"busybox:1.38.0@sha256:dc2d74b28e4cf8984fa52af1f39bc7c3d9c73760b41a74d629f5d11b1ab28616","command":["sh","-c","ls -la /q; find /q -mindepth 1 -delete; echo REMAINING=$(find /q -mindepth 1 | wc -l)"],"volumeMounts":[{"name":"q","mountPath":"/q"}]}],"volumes":[{"name":"q","persistentVolumeClaim":{"claimName":"edot-collector-queue"}}]}}'
   kubectl wait pod/edot-queue-wipe -n monitoring --for=jsonpath='{.status.phase}'=Succeeded --timeout=180s
   kubectl logs -n monitoring edot-queue-wipe      # MUST end with REMAINING=0
   kubectl delete pod -n monitoring edot-queue-wipe
   ```

   A timeout with the pod in `ContainerCreating` = volume still attached elsewhere (Multi-Attach).
   Wait; do not force-detach.
3. `kubectl scale deploy/edot-collector -n monitoring --replicas=1`, then re-run §4.1–§4.4.

Cost: only the buffered in-flight telemetry (`create_directory: true` makes an empty directory a
clean start). **Operator-visible; record it.** It is the only step that loses data.

### 5.3 kmsg-sender stall on a node (from §4.4) — recovery, not rollback

Documented recipe in `docs/troubleshooting/node-reboot-observability.md` §"kmsg-sender stall on
collector restart": toggle the node's `KmsgLogConfig` url to port 5172 and back to 5171 (re-opens the
UDP socket without a reboot; a same-value `apply-config` does NOT kick it).

```bash
NODE=<192.168.55.1x of the missing node>
talosctl -n "$NODE" patch mc --patch '{apiVersion: v1alpha1, kind: KmsgLogConfig, name: ship-kmsg-to-otel, url: udp://192.168.55.18:5172/}'
talosctl -n "$NODE" patch mc --patch '{apiVersion: v1alpha1, kind: KmsgLogConfig, name: ship-kmsg-to-otel, url: udp://192.168.55.18:5171/}'
```

A direct Talos machine-config mutation outside Flux (ends at the same value), so:
- **Attended slot:** operator GO, then delegate to cberg-agent, re-run §3 step 5 with a new REV and §4.4.
- **Nightly (unattended):** do NOT toggle. Leave the bump in place, record a finding naming the node,
  put the toggle in the morning report. `TalosKernelLogsMissingFromNode` pages at 3h+15m if the node
  stays silent. The only loss is that node's kernel-log diagnostic feed, not user data.

### 5.4 Restore alert state (either outcome)

```bash
runbooks/update-marker.sh clear edot-collector
kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 >/dev/null 2>&1 & PF=$!
sleep 3
SID=$(python3 -c "import json;print(json.load(open('/private/tmp/claude-501/edot-01640-silence.json'))['silenceID'])")
curl -s -o /dev/null -w 'delete silence %{http_code}\n' -X DELETE "localhost:9093/api/v2/silence/$SID"
kill $PF 2>/dev/null
```

## 6) Interference notes

- **Supersedes edot-collector-0.163.2 (§1.5, done 2026-11-02).** 0.163.2 is `status: superseded`
  (`superseded_by` this plan, window null); its `nightly:2026-11-10` slot is carried here only as a
  SUGGESTED `window:` comment. This plan stays `draft`/`review: null` and must pass a re-review before
  anyone stamps the slot. The go/no-go issue and the reciprocal refs still need moving (§1.5).
- **Step 0 may pre-empt this plan.** The nightly auto-update merged the 0.162.0 PR #264 on 2026-10-08
  as a "safe" minor. If Step 0 merges #324 first, premise 1 fails printing `:0.164.0`: do not re-run
  §3 steps 2–4; run §3 step 5 and all of §4 as post-hoc verification with the running pod's Ready
  timestamp; mark executed only if §4 passes.
- **SEPARATE SLOT from otel-operator, otel-operator FIRST (operator rule 2026-10-23).**
  `otel-operator-0.26.1` (draft, human-gated; supersedes `otel-operator-0.25.1`, which still reads
  vetted at `sat-attended:2026-11-07` until the orchestrator retires it) runs first, SOLO; this plan
  in a later slot (suggested `nightly:2026-11-10`). Both names are in `conflicts_with`; 0.26.1 already
  lists `edot-collector-0.164.0` back. No technical ordering dependency in either direction (OTLP
  4317/4318 contract unchanged; `depends_on: []`); the ordering is attribution only.
- **Node roll: `talos-linux-1.14.5`** (draft, `exclusive: true`, `needs_reboot: true`, supersedes
  `talos-linux-1.14.4`, which still reads vetted at `sun-attended:2026-11-01` until retired) drains
  the node this single replica runs on and silences each node's kmsg feed for its reboot. Never the
  same night as this plan, before or after within the same window; it lists this plan back.
- **Same-night shared-instrument changes.** §4 reads Prometheus and ES. `kube-prometheus-stack`
  92.11.1 → 92.14.1 (PR #428) is open with no plan and could land via Step 0; §2.1b STOPs on it (and
  on opentelemetry-kube-stack or ES/ECK changes) the same night.
- **Future ES 9.4+ upgrade — corrected 2026-11-02.** The earlier note said an ES >= 9.4.0 upgrade would
  flip explicit-bounds histograms in `metrics-generic.otel-default` to exponential through version
  detection. That is NOT what happens today: the probe is unauthenticated, gets 401 from our ECK ES
  and returns `nil` (§1.2, §1.3b), so TDigest stays regardless of the ES version. The mapping can
  flip only if (a) a later collector release sends credentials on the probe, or (b) the exporter is
  configured to use exponential histograms explicitly. Any ES major plan must therefore re-check, on
  the then-current collector, whether the startup log shows `Connected to Elasticsearch` (probe now
  authenticated) — if it does, the histogram mapping on the TSDB OTel metrics stream changes with ES
  9.4; if it still shows the 401 warning, it does not. Inert at 8.19.20 either way.
- **`conflicts_with` mechanisms:** same deployment/PR (edot-collector-0.163.2, superseded), producer
  roll into this sink (otel-operator-0.26.1, and 0.25.1 until retired), node drains
  (talos-linux-1.14.5, and 1.14.4 until retired), the RWO queue volume (longhorn-1.13.0),
  monitoring-namespace attribution (grafana-14.1.0 — its target is now **14.2.0**, the id was kept on
  purpose; a soft attribution conflict only, neither plan reads the other's signals), HelmRelease
  re-sourcing of kube-prometheus-stack (flux-oci-chart-sources). Checked against every open plan's
  frontmatter on 2026-10-29 and re-checked 2026-11-02 (new drafts: otel-operator-0.26.1,
  talos-linux-1.14.5, flux-fleet-0.62.0/.1). Not carried from 0.163.2: `coredns-1.48.1`
  (superseded), `talos-linux-1.14.2` (superseded), `home-assistant-2026.10.2` (executed).
- **Low-risk monitoring/reconcile-surface neighbours (not in `conflicts_with`; none is a technical
  blocker, each can blur a §3/§4 failure if it lands the same night, so keep them off this night where
  the calendar allows).** `helm-drift-detection` (`sat-attended:2026-11-07`; fleet-wide HelmRelease
  drift settings — its own plan says `monitoring/edot-collector` is NOT HelmRelease-owned and outside
  drift detection, so only the Flux reconcile load is shared), `etcd-timeouts-5000-500`
  (`sun-attended:2026-11-08`; restarts etcd on all three control-plane nodes, a control-plane
  disturbance that can fail `kubectl`-driven gates), `flux-fleet-0.62.0` / `flux-fleet-0.62.1` (drafts; roll
  `deployment/flux-operator` in `flux-system`, the reconcile engine behind §3 step 3 and the exporter
  of the `flux_*` series), `talos-power-tuning-ab` (vetted, unscheduled; per-node power/performance
  A/B, attended NOW evenings, no reboot).
- **Pre-existing alert noise not to attribute here:** health finding **F-76387378** (edot ES dropped
  metric points, 360/h since 2026-10-31, baseline recorded in §2.4). A post-roll health-check warning
  with the same reason string is the baseline, not a 0.164.0 regression (§4.2).
- **Slot preference: nightly is fine, attended preferred.** 52 of 70 nightly minutes (the one-off §4.1 T+30m re-read adds about 3 more). The only step
  wanting an operator is the §5.3 kmsg toggle, and only on a stall.
- **Ingestion gap of tens of seconds** during the Recreate swap. OTLP producers (otel-operator daemon
  collectors) buffer only in memory, so a few seconds may be lost; the ES exporters here back-pressure
  via `block_on_overflow` + disk queue (visible as `otelcol_receiver_refused_*`). Any kmsg line sent
  during the swap is lost (UDP, no listener), which is why §3 step 5 runs only after Ready.
- **The image is minimal** (no `cat`/`curl`/`wget`): every check uses `kubectl get --raw` or
  port-forward + local curl, never `kubectl exec`.
- **The daemon collectors are NOT moved** — they run `otel/opentelemetry-collector-k8s`, owned by
  HelmRelease `otel-operator`. Repo-wide, `otel/opentelemetry-collector-contrib:` appears only in
  `edot-collector/app/deployment.yaml` (grepped 2026-10-29).
- **The kmsg heartbeat phase shifts** to the kick minute after §3 step 5 — harmless,
  `TalosKernelLogsMissingFromNode` keys on "nothing for 3h".
- **Repo correction owed:** `runbooks/maintenance/plans/README.md` prescribes refresh-in-place for a
  drifted target, but the rule-4d0 dispatch named a new plan_id (as it did for 0.162.0 → 0.163.2).
  Either the dispatcher should pass the existing plan_id on a DRIFTED target, or the README should
  document the supersede path; today the two disagree and every edot retarget orphans a vetted slot.
