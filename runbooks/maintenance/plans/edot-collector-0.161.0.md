---
plan_id: edot-collector-0.161.0
component: edot-collector
pr: null                          # NO Renovate PR exists. Verified 2026-09-17:
                                  # `gh pr list` returns exactly two open PRs
                                  # (#217 esphome, #212 aqua:siderolabs/talos),
                                  # neither for this image; and
                                  # runbooks/version-check-current.md line 151
                                  # carries `?` in the PR column for this row.
                                  # So this lands via coverage.py's DIRECT-BUMP
                                  # path (a hand edit), not by merging a PR.
kind: image
current: "0.160.0"                # MEASURED live 2026-09-17, not copied:
                                  # deployment/edot-collector container image is
                                  # otel/opentelemetry-collector-contrib:0.160.0
target: "0.161.0"
update_type: minor                # 0.x line: the MINOR digit is the breaking axis
risk: medium                      # NOT from likelihood — the changelog is clean
                                  # (§1.2). From blast radius + failure MODE:
                                  # single-replica sole ingestion path for every
                                  # namespace, and it fails SILENTLY. See §1.4.
est_duration_min: 70              # RAISED from 40 on 2026-09-20 review. 8 pre-checks
                                  # (incl. the validate pod + baselines) + 3
                                  # edit/commit/push + 4 reconcile and Recreate roll
                                  # + 45 SETTLE + 10 verification.
                                  # THE SETTLE IS 45m, NOT 15m, AND THAT IS THE
                                  # MEASUREMENT, NOT PADDING. §4.4's per-node kmsg
                                  # gate must read a window that lies ENTIRELY after
                                  # the roll (a straddling window passes on pre-roll
                                  # lines from a node that has since gone silent),
                                  # and [45m] is the SHORTEST window with a real
                                  # floor. Measured 2026-09-20 over 7d, per node:
                                  #   [15m] min 0/0/0     zero 6.5%/10.7%/13.1%
                                  #   [30m] min 0/0/0     zero 0.9%/0.9%/1.5%
                                  #   [45m] min 3.0/3.0/3.0   zero 0%/0%/0%
                                  #   [1h]  min 6.0/6.0/6.1   zero 0%/0%/0%
                                  # FITS `nightly` (90m) BUT ONLY ALONE: the
                                  # scheduler's budget is duration_min - 
                                  # STEP0_RESERVE_MIN = 90 - 20 = 70, so this plan
                                  # consumes the whole nightly budget exactly and
                                  # cannot share the slot with any other plan (§6).
needs_reboot: false
touches:
  namespaces: [monitoring]
  resources:                      # every object below verified to EXIST live
                                  # 2026-09-17 via kubectl (authoring rule 1)
    - deployment/edot-collector               # the only object this plan EDITS
    - configmap/edot-collector-config         # READ + validated against the new
                                              # binary in §2.3; NOT edited (§1.5)
    - pvc/edot-collector-queue                # RWO longhorn-static, Bound; the
                                              # bbolt sending-queue. Detach/attach
                                              # on the Recreate roll. Not resized.
    - service/edot-collector                  # ClusterIP 4317/4318/8888/8889
    - service/edot-collector-talos-kmsg       # LoadBalancer 192.168.55.18 UDP 5171
    - servicemonitor/edot-collector           # the scrape that FEEDS §4's gates
    - httproute/edot-collector                # OTLP/HTTP on envoy-internal; backend
                                              # is briefly down during the roll (§6)
  shared: [monitoring]            # DELIBERATE, and a CORRECTION of the retired
                                  # 0.160.0 plan, which set `shared: []` and put
                                  # the blast radius in prose only — where the
                                  # scheduler cannot see it. This Deployment is
                                  # the single OTLP choke point for every
                                  # namespace's logs/metrics/traces into
                                  # Elasticsearch AND the Talos kmsg sink. A roll
                                  # blinds cluster-wide observability for the
                                  # duration, so it must present that surface to
                                  # interference detection. NOT gateway/envoy:
                                  # this plan does not change routing, it only
                                  # makes one HTTPRoute backend briefly
                                  # unavailable (§6).
depends_on: []
conflicts_with:                   # HARD slot exclusions. window-scheduler.py
                                  # honours ONLY this field — a prose rule in §6
                                  # schedules nothing. Every entry below names a
                                  # MECHANISM, not a courtesy.
                                  # NOT LISTED, 2026-09-17: `otel-operator-0.21.0`.
                                  # It was the obvious entry — its own §6 said
                                  # "Do not run in the same window as an
                                  # edot-collector change" — but it EXECUTED in
                                  # nightly:2026-09-17 and its file was retired in
                                  # commit 37f7c7a6 while this plan was being
                                  # written. A ref to it is now a DEAD ref, which
                                  # --validate rejects ("this guard is not
                                  # enforced"). The mechanism it guarded is not
                                  # lost: `prometheus-crd-ownership` below is the
                                  # same otel-operator helm upgrade and still open.
  # RESOLVED 2026-09-20: prometheus-crd-ownership EXECUTED (1a551276) and retired (9d87171b) — there is no longer a plan to collide with, so this guard protected nothing. Removed per the dead-ref convention (F-6acb231c).
                                  # rolls daemonset/otel-operator-daemon-collector
                                  # by the same label-propagation mechanism as
                                  # otel-operator-0.21.0 — same OTLP-producer
                                  # restart, same unattributable gap. It also
                                  # CreateReplaces the servicemonitors CRD that
                                  # servicemonitor/edot-collector depends on, i.e.
                                  # it perturbs the instrument §4 reads.
  - kube-prometheus-stack-91.4.1  # Authoring rule 4, and the mechanism is
                                  # explicit in that plan's own file: a chart bump
                                  # RESTARTS Prometheus. Every gate in §2.4 and §4
                                  # of this plan is a Prometheus range query, so a
                                  # scrape blind spot reads as "rate == 0" —
                                  # i.e. as THIS plan regressing — and would
                                  # trigger a needless revert of a healthy bump.
                                  # That plan already removed an identical guard
                                  # for unpoller for exactly this reason.
  - talos-1.14.0                  # A rolling node reboot EVICTS this very pod
                                  # (single replica) mid-verification and puts the
                                  # whole cluster in motion; no assertion in §4
                                  # means anything during it.
                                  # KEPT as a resolving ref only — see below.
  - talos-1.14.1                  # ADDED 2026-09-21, and this is the LIVE talos
                                  # plan. talos-1.14.0 was SUPERSEDED earlier the
                                  # same day (commit 9c19acc3) and will never run;
                                  # its window was cleared and talos-1.14.1 (draft,
                                  # high, 145 min, needs_reboot) INHERITED
                                  # sun-attended:2026-09-27. The ref above still
                                  # RESOLVES, so --validate stayed clean the whole
                                  # time while the guard pointed at a plan that
                                  # cannot execute — the node roll that actually
                                  # happens was unguarded against this plan. Same
                                  # eviction mechanism as above. Convention follows
                                  # n8n-2.39.8 and cilium-1.20.2: name the successor,
                                  # keep the predecessor so a revival cannot slip
                                  # past and so --validate keeps resolving.
  - otel-operator-0.23.0          # ADDED 2026-09-20. That plan's daemon collectors
                                  # export OTLP into edot-collector.monitoring.svc
                                  # :4317, and its own §4 proves itself through
                                  # documents landing in ES *via this collector*. If
                                  # both roll in one window neither plan's ES gate
                                  # can attribute a gap to its own change. It
                                  # ALREADY names `edot-collector-0.161.0` in its
                                  # conflicts_with (verified 2026-09-20), and
                                  # window-scheduler.py honours a declaration in
                                  # EITHER direction (`names_me`, line 264), so the
                                  # pair is already unschedulable together — this
                                  # entry makes the guard readable from this side
                                  # rather than creating it. The §6 claim that the
                                  # edot-vs-otel-operator collision was "spent"
                                  # when 0.21.0 executed is corrected below: the
                                  # mechanism is durable and 0.23.0 is its heir.
  # RESOLVED 2026-09-21: cilium-1.20.2 EXECUTED (80395710, chart 1.20.1 -> 1.20.2) and retired (c0797253) -- there is no longer a plan to collide with, so this guard protected nothing. Removed per the dead-ref convention: --validate treats an unresolvable ref as an ERROR, because a guard pointing at nothing enforces nothing.
security_ref: F-2a0b50e5          # A security finding DOES exist on the exact image
                                  # this plan moves, and this plan is its remedy:
                                  # the finding's own remediation is "newer upstream
                                  # tag available, bump the image", which is
                                  # precisely 0.160.0 -> 0.161.0. Contextual tier is
                                  # MEDIUM (internal, not-in-KEV) — NOT a raw
                                  # scanner CRITICAL; quote the board's tier, per
                                  # CLAUDE.md. Bare F-id only: no CVE ids, no counts,
                                  # no exposure detail in this public repo
                                  # (docs/sops/vulnerability-disclosure.md).
                                  # CORRECTION of the pre-review text, which claimed
                                  # "no security driver for this image". The AR that
                                  # tags this row is AR-124 (needle
                                  # `opentelemetry-collector`), not AR-072 (needle
                                  # `opentelemetry-operator`); AR-072 scopes the
                                  # DAEMON image (F-ba45c963) and was never the
                                  # relevant rule here. The config-validation gate
                                  # in §2.3 still stands on the documented 2026-08
                                  # incident (§1.5), not on any rule's reason text.
capability_change: false          # image tag only; no config change, no new
                                  # receiver/exporter/processor, no user-visible
                                  # behaviour. Deliberately kept true by NOT
                                  # carrying the F-dc898b50 filter — see §1.6.
rollback_class: git-revert        # primary path is genuinely a one-commit revert
                                  # (image tag only, config untouched). The ONE
                                  # forward-only surface — the bbolt queue file
                                  # written by the newer binary — is handled as an
                                  # explicit contingency PROCEDURE in §5.2, not
                                  # waved away.
finding_refs: [F-cb9182ca]        # CORRECTED 2026-09-20. The pre-review file left
                                  # this EMPTY on two claims that are both FALSE,
                                  # now deleted: re-run live with SWEEP_PG_DSN up,
                                  # `finding list --grep 0.161` DOES return
                                  # F-cb9182ca, and it IS in `--section version`.
                                  # F-cb9182ca is this plan's own finding: section
                                  # `version`, action "0.x release-line move
                                  # (0.160 -> 0.161) — PLAN lane", first_seen
                                  # 2026-09-17, last_seen 2026-09-19, resolved_at
                                  # None. finding-triage.py's plan-or-page pass
                                  # joins PLAN-lane findings to plans on exactly
                                  # this field, so without it this plan's own target
                                  # reads as unplanned and pages the operator after
                                  # plan_sla_days.
                                  # NOTE on why it was easy to miss: the row is
                                  # currently marked `accepted` under AR-124, whose
                                  # needle is the bare substring
                                  # `opentelemetry-collector` and over-matches this
                                  # VERSION row. AR-124's own justification scopes
                                  # it to CVE rows and says the bump is window-work.
                                  # That over-match is itself filed as F-e430800e
                                  # (section `plan`), whose metadata.plans already
                                  # names THIS plan. Narrowing AR-124 is a policy-DB
                                  # edit, not a git change — see §6.
                                  # STILL DELIBERATELY NOT CLAIMED:
                                  # F-dc898b50 (the ES-storage/Envoy-cardinality
                                  #     finding whose fix lives in THIS directory)
                                  #     is deliberately NOT claimed here, because
                                  #     this plan does not fix it (§1.6). Claiming
                                  #     it would make finding-triage.py's
                                  #     plan-or-page pass read that finding as
                                  #     PLANNED and stop paging for it, while
                                  #     nothing in this plan remediates it. It
                                  #     SHOULD keep reading as unplanned until it
                                  #     gets its own plan or DECIDE routing.
status: vetted   # 2026-09-26 plan-reviewer needs-fix -> 15 edits applied (log floor 10k, kmsg gate via ES per-node count, state in fixed files, silence delete URL fixed); order: after elasticsearch-obs-recovery §4 + 10 min
window: null                      # the scheduler assigns. Shape: no reboot, no
                                  # capability change, git-revert, 70m. Derived
                                  # execution class is AUTO-NIGHT (read from
                                  # `maintenance-plan.py --json`, not re-derived),
                                  # i.e. UNATTENDED — which is why every gate in §4
                                  # that carries revert authority had to be proven
                                  # incapable of false-failing (§4.4, §4.5).
                                  # Fits `nightly` (90m) ONLY ALONE: budget is
                                  # 90 - STEP0_RESERVE_MIN(20) = 70m exactly.
premises:
  # Re-checked at EXECUTION time, not trusted from when this was written.
  # Both commands were RUN on 2026-09-17 while writing this plan; premise 2 was
  # additionally validated with a NEGATIVE CONTROL (see its `why`).
  - id: image-is-still-0.160.0
    why: >-
      `current:` claims 0.160.0. If the collector already moved, this plan is
      stale: its rollback target and every §2.4 baseline are wrong. Fails loudly
      by printing the actual image instead of the expected one.
    run: kubectl get deploy -n monitoring edot-collector -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "otel/opentelemetry-collector-contrib:0.160.0"
  - id: ingestion-is-healthy-before-we-touch-anything
    why: >-
      Never roll the cluster's sole telemetry path while it is ALREADY degraded —
      a pre-existing stall would be misattributed to this bump and would burn the
      window on a false rollback. Asserts the logs exporter actually persisted
      records over the last 15m (measured 39,927 on 2026-09-17, so the >1000 floor
      has ~40x headroom and is not a hair trigger). NEGATIVE CONTROL RUN, 2026-09-17,
      per docs/sops/verification-contents-not-shape.md §2b — the identical pipeline
      pointed at a nonexistent metric printed INGEST_LOW, proving this premise can
      fail rather than passing on an empty result. Uses the API-server service proxy
      so it needs no port-forward and leaks no background process.
      THREE AUTHORING TRAPS, all hit and all recorded here so the next author
      does not re-discover them (plan-premises.py sandboxes premises hard, and a
      refused premise does NOT run - it fails the plan):
      (a) it refuses any command containing `;`, `&&`, `||`, backticks, `$(`,
          `>`, `>>` or `&`, so a python one-liner separated by `;` is refused;
      (b) it allows only kubectl/flux/talosctl/helm/git plus bare
          grep/sed/awk/jq/head/tail/wc/cut/sort/uniq/tr/cat/echo/test -
          `python3` is on NEITHER list, which is why extraction is sed+awk and
          not this repo's usual python;
      (c) the ban on `>` is textual, not shell-aware, so an awk comparison
          written `($1+0>1000)` is refused too. Hence the comparison is INVERTED
          to use `<` and the ternary arms are swapped - same logic, legal string.
      Verified 2026-09-17 with three controls- INGEST_OK on the real query,
      INGEST_LOW on a nonexistent metric (empty `result` array), and INGEST_LOW
      on a real metric over a 1s window. The awk `$1+0` coercion is what makes
      the empty-result case fail closed rather than erroring.
    run: kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=sum(increase(otelcol_exporter_sent_log_records_total[15m]))' | sed -E 's/.*"value":\[[0-9.]+,"([0-9]+).*/\1/' | awk '{print ($1+0<1000)?"INGEST_LOW":"INGEST_OK"}'
    expect_exact: "INGEST_OK"
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/monitoring.md                          # "ES Rejected Documents" §301
                                                     # + "Metric-based rejection
                                                     # assertion" §365 — §4.2 uses
                                                     # the form given there
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/longhorn-rwo-multi-attach.md           # why strategy Recreate is
                                                     # load-bearing here
generated: "2026-09-17"
---

# edot-collector: image 0.160.0 → 0.161.0 (0.x release-line move)

## 1) Summary & why held

### 1.1 Why the auto-updater held it

Not a deny rule, and not a CVE. `runbooks/coverage.py` classifies this into the
PLAN lane on a component-agnostic rule, verbatim from `assign_lane()`:

> `"0.x release-line move (0.%d -> 0.%d) — at major 0 the minor IS the breaking
> axis; needs an assessed window plan"`

There is no `deny` entry matching `edot-collector` or
`opentelemetry-collector-contrib` in `runbooks/auto-update-policy.yaml`
(checked 2026-09-17), and neither the G5 release-age cooldown nor the G3
breaking-signal gate is what stopped it — the 0.x rule sits **above** both exits.
So the hold is structural: at major 0 there is no separate major digit, so
`0.160 → 0.161` is upstream's breaking-change hop and must be assessed, not
merged.

### 1.2 Upstream evidence for 0.161.0 — assessed, and clean for OUR config

Sources read directly from the upstream releases (authoring rule 8 — evidence
from upstream, never from a deny reason or a SOP):

- contrib `v1.0.0/v0.161.0`, published **2026-09-15T15:05:47Z**
- core `v0.161.0`, published **2026-09-14T22:49:14Z**
- image `otel/opentelemetry-collector-contrib:0.161.0` pushed
  **2026-09-16T03:01:45Z**, multi-arch (amd64 present)

The components this deployment's `otel.yml` actually instantiates are:
`otlp` receiver, `udplog/talos-kernel` (stanza `json_parser`/`move`/`add`),
`memory_limiter`, two `filter` processors, one `transform` processor,
`cumulativetodelta`, `batch`, three `elasticsearch` exporters, the `prometheus`
exporter, the `count` connector, the `file_storage` extension, `health_check`,
and the `service::telemetry` Prometheus reader.

**Not one breaking change in either release touches any of them.** The contrib
breaking list is: mezmo exporter removal, opampsupervisor `reports_remote_config`
deprecation, azure/google-cloud encoding extensions, coreinternal goldendataset,
faro, kafka configkafka, three `pkg/ottl` entries, `processor/k8s_attributes`,
`processor/signing`, `receiver/kubelet_stats`, `receiver/sqlserver`. The core
breaking list is four Go-API removals (`pkg/pprofile`, `pkg/scraperhelper`,
`pkg/service` ZapOptions, `pkg/xconfmap`) — build-time only.

Three of those deserve an explicit "checked, not ours", because each looks
alarming to a reviewer scanning the changelog:

- **`pkg/ottl`: Remove the deprecated `Base64Decode` converter (#50875)** — this
  config uses no `Base64Decode` (grepped: zero hits).
- **`pkg/ottl`: Promote `ottl.set.allowNil` to beta, enabling it by default
  (#49741)** — changes the behaviour of the `set` function. This config contains
  no `set(` at all (grepped: zero hits); its only OTTL mutation is
  `delete_key(...)` in `transform/strip-k8s-managedfields`, plus boolean
  `IsString`/`IsMap`/`IsMatch` conditions in the two filters. Unaffected.
- **`processor/k8s_attributes`: promote logs/metrics/traces to stable, with
  `EmitV1K8sConventions` + `DontEmitV0K8sConventions` beta (enabled by default)**
  — this is the genuinely disruptive entry in the release (it renames
  `k8s.pod.labels.*` → `k8s.pod.label.*`). **It does not apply to this plan.**
  `edot-collector`'s config has no `k8sattributes` processor; that processor runs
  in the *daemon* collector, which is a different image
  (`otel/opentelemetry-collector-k8s:0.154.0`), owned by a different HelmRelease
  (`otel-operator`), and is **not moved by this plan**. Confirmed live 2026-09-17.

Repo-wide, `otel/opentelemetry-collector-contrib:` appears in exactly **one**
file — `kubernetes/apps/monitoring/edot-collector/app/deployment.yaml:40` — so
there is no second collector to keep in lockstep.

### 1.3 The load-bearing thing 0.161.0 did NOT change

`service::telemetry` still honours `without_type_suffix`, `without_units` and
`without_scope_info`. Those three are pinned `false` in the configmap on purpose:
collector 0.152.0's `applyPrometheusDefaults()` forces them TRUE for explicitly
configured telemetry, which would silently rename
`otelcol_exporter_sent_{log_records,metric_points}_total` and leave
`EsMetricsIngestionStalled` / `EsLogIngestionStalled` matching an empty vector —
losing exactly the detectors that catch silent telemetry loss, with no error.
Neither the core nor the contrib 0.161.0 changelog touches that surface, and
§2.3's validate run re-proves the keys are still accepted by the new binary.

### 1.4 Why `risk: medium` despite a clean changelog

**UPDATE 2026-09-26 (review):** F-7c88001b is RESOLVED (aff58ede, 2026-09-20):
`Es{Metrics,Log,Traces}ExporterSeriesMissing` (absent(), for 15m) now page on the
disappearance mode. They are deliberately NOT in §3.1's silence; §4.6 must show
them not firing. §4 remains the primary detection.

Blast radius and failure *mode*, not likelihood. This single-replica Deployment is
the only OTLP path into Elasticsearch for every namespace's logs, metrics and
traces, plus the Talos kmsg sink on `192.168.55.18`. Its characteristic failure is
**silent**: the pod stays Ready, the health endpoint stays 200, and telemetry
simply stops being counted. That is why §4 is built on contents assertions with a
floor, and why "pod Ready" is explicitly not the gate.

**And the standing alerts cannot catch it either — which is what makes §4
load-bearing rather than belt-and-braces.** `F-7c88001b` (open, section `plan`)
records that `EsLogIngestionStalled` and `EsMetricsIngestionStalled` in
`kubernetes/apps/monitoring/kube-prometheus-stack/app/otel-collector-alerts.yaml`
are written as `rate(...) == 0`, which returns NO DATA — and therefore does not
fire — when the series disappears entirely, i.e. in exactly the disappearance
mode §1.3 describes. Do not treat "no alerts fired" as evidence this bump was
clean; §4.1's floor and §4.2's two-sided outcome gate are the detection.

### 1.5 The config-validation gate is mandatory (§2.3)

This deployment has already shipped a config the collector ACCEPTED and
Elasticsearch REJECTED — `document_parsing_exception` with an **empty**
`error.reason`, caused by Kubernetes Event `managedFields` carrying a `"."` key,
silently dropping ~0.5% of all log records. The fix was a transform stripping at
`log.body["object"]["metadata"]`; the trap that cost a wasted roll was writing it
at `body.structured`, which is the **ES-side otel-mode wrapper**, not the OTLP
record path — the wrong path is a silent no-op. Because of that history, §2.3
validates the live config against the **new binary** before anything rolls, and
§4.2 asserts on ES's per-document outcome afterwards.

### 1.6 F-dc898b50 — this plan deliberately does NOT carry the filter

**UPDATE 2026-09-26 (review): F-dc898b50 is RESOLVED (2026-09-22) by f470b8c8**, which
added `filter/drop-envoy-cluster-metrics` in its own commit; the live pod (started
2026-09-22T22:52Z) already runs it, and §2.3 validates it against 0.161.0. The
metric-point rate fell from ~3.2M to ~2.0M per 15m (24h range 1,969,997 - 1,999,117
on 2026-09-26); §2.4 re-baselines live, so §4.1's band is unaffected. The text
below is historical.

`F-dc898b50` is open and unremediated: Elasticsearch storage is growing
**+1.47 GiB/day** because a high-cardinality Envoy histogram family (labelled by
user agent) is being ingested, and the prescribed fix is a `filter`/
`metricstransform` processor **in this very directory**. `git log` over
`kubernetes/apps/monitoring/edot-collector/` confirms zero commits since
2026-09-13 (the 0.160.0 bump). **The next person touching this directory must know
this is still outstanding — which is why it is stated here in full.**

**Decision: keep this plan strictly a version bump.** Four reasons:

1. **It would destroy this plan's own verification.** §4's metrics-side gates
   compare post-roll ingestion rates against a pre-roll baseline. A processor
   whose entire purpose is to *reduce* the metric-point rate makes that
   comparison fail by design, and makes any real regression from the binary
   unattributable against the intended drop. This component's failure is silent;
   the last thing it needs is a gate that cannot distinguish the two causes.
2. **It is a state change requiring operator approval — the finding says so
   verbatim:** *"OPERATOR APPROVAL REQUIRED (state change)."* Dropping a metric
   family is a deliberate decision to stop being able to see something. It would
   flip `capability_change` to `true` and move this plan out of the reversible,
   pre-approved class into human-gated.
3. **The urgency does not require coupling.** The finding's own 2026-09-16
   re-measurement supersedes its original "~11d runway": with 14d retention, the
   five pre-step indices ageing out account for most of the remaining growth, and
   the projected plateau is ~64-66 GiB of 83 GiB usable (~78-80%) — *"tight, but
   not a wall, and NOT an 11-day emergency."* ES is green, 0 unassigned shards, no
   node reports DiskPressure, and no disk-watermark messages. Separately, the
   Longhorn alert that re-raised it is the snapshot-inflation detector defect
   F-d6efb5fa, not the growth itself — the two must not be conflated.
4. **It would contaminate the rollback.** Keeping the commit image-tag-only is
   what makes `rollback_class: git-revert` honest; a mixed commit means reverting
   a bad binary also reverts a cardinality fix.

**What is owed instead:** F-dc898b50 needs its own treatment, and it is arguably a
**DECIDE**, not a window action — the choice is between (a) permanently dropping a
metric family, (b) cutting retention on `metrics-generic.otel-default`, and
(c) spending disk. That is a judgement about what the household is willing to stop
seeing, and bundling it into an image bump would hide it from the person it
belongs to. This plan's `finding_refs` is therefore empty **on purpose**, so
F-dc898b50 keeps reading as unplanned and keeps paging.

Two sibling findings live in the same file and are likewise **not** addressed
here: `F-f8801413` (the `cumulativetodelta` include list is `match_type: strict`,
so each new Envoy histogram family silently drops until hand-added) and
`F-b780647b` (its current symptom). They matter to §4.5: the drop counter is
**already non-zero** today, so the gate is written against a baseline, not
against zero.

## 2) Pre-checks

Run in order. Any failure stops the plan — do not proceed to §3.

```bash
# 2.1 — premises (both re-run mechanically at execution time)
.venv/bin/python3 runbooks/plan-premises.py edot-collector-0.161.0

# 2.2 — target tag is published and multi-arch, AND capture the digest that §4's
# floor will compare against. Measured 2026-09-20: pushed 2026-09-16T03:01:45Z,
# amd64 present, manifest-list digest
#   sha256:fd328de2552466ad78385e1b1289c3f2402b1c45f265b252aab1955b42845ac1
curl -s "https://hub.docker.com/v2/repositories/otel/opentelemetry-collector-contrib/tags/0.161.0" \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['name'],d['tag_last_pushed'],d['digest'],[i['architecture'] for i in d['images']])"
# PASS: prints 0.161.0, a tag_last_pushed, a sha256: digest, with amd64 present.
# FAILS AS: a 404 body -> KeyError/'httpStatus' -> the tag does not exist.
#
# RECORD THE MANIFEST-LIST DIGEST — the top-level `digest`, NOT the per-arch one.
# This matters and is measured, not assumed: the live pod's imageID today reads
#   docker.io/otel/opentelemetry-collector-contrib@sha256:799dc6cf12c9...72ad6
# which is Docker Hub's MANIFEST-LIST digest for 0.160.0. The amd64 digest for
# 0.160.0 is sha256:5b66b0dc6921... and appears NOWHERE in imageID. Comparing
# §4's floor against the per-arch digest would therefore false-FAIL on a
# perfectly good roll.
TARGET_DIGEST=sha256:fd328de2552466ad78385e1b1289c3f2402b1c45f265b252aab1955b42845ac1

# 2.3 — HARD GATE: validate the LIVE config against the NEW binary.
# A config the new binary rejects crashloops the entire cluster-wide ingest path.
kubectl run edot-validate-0161 --rm -i --restart=Never \
  --image=otel/opentelemetry-collector-contrib:0.161.0 \
  --overrides='{"spec":{"containers":[{"name":"edot-validate-0161","image":"otel/opentelemetry-collector-contrib:0.161.0","command":["/otelcol-contrib","validate","--config=/config/otel.yml"],"env":[{"name":"ES_PASSWORD","value":"dummy-validate-only"}],"volumeMounts":[{"name":"cfg","mountPath":"/config"}]}],"volumes":[{"name":"cfg","configMap":{"name":"edot-collector-config"}}]}}'
echo "validate exit=$?"
# NEGATIVE CONTROL (same Bash call): a missing config MUST print a non-zero exit,
# proving the exit code above is the collector's and not kubectl's.
kubectl run edot-validate-0161-neg --rm -i --restart=Never \
  --image=otel/opentelemetry-collector-contrib:0.161.0 \
  --overrides='{"spec":{"containers":[{"name":"edot-validate-0161-neg","image":"otel/opentelemetry-collector-contrib:0.161.0","command":["/otelcol-contrib","validate","--config=/nonexistent/otel.yml"]}]}}'
echo "negative-control exit=$?   # MUST be non-zero; if 0, the gate above cannot fail"
# PASS: exit 0 AND no output containing (case-insensitively) "error" / "invalid
# configuration" / "cannot unmarshal". Read the OUTPUT, not only the code.
# FAILS AS: a line naming the rejected key, e.g. an unknown `without_type_suffix`
# under service::telemetry, or an unrecognised `sending_queue` key. If it fails,
# this plan is BLOCKED — the bump needs a config change first, which is a
# different plan.

# 2.4 — BASELINES for §4.
# EVERY BASELINE IS TAKEN OVER THE EXACT WINDOW ITS GATE USES. The pre-review
# file baselined docs.processed over [6h] but gated it at [15m], and baselined
# kmsg per-HOUR but gated it at [15m] — a baseline in different units than its
# gate is not a baseline, it is a number that looks like one.
# Measured 2026-09-20 for reference (yours will differ):
#   sent log records [15m]        37,161   (24h range 35,927 - 57,673)
#   sent metric points [15m]   3,218,414   (24h range 3,217,392 - 3,246,244)
#   docs.processed success [15m] 1,140,668   non-success: EMPTY (= 0, healthy)
#   cumulativetodelta dropped [1h]    2.0   <- bursty, see §4.5; NOT a band
#   kmsg per node [45m]  (see §4.4 — 7d min 3.0/3.0/3.0)
P=/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query
kubectl get --raw "${P}?query=sum(increase(otelcol_exporter_sent_log_records_total[15m]))"
kubectl get --raw "${P}?query=sum(increase(otelcol_exporter_sent_metric_points_total[15m]))"
kubectl get --raw "${P}?query=sum(increase(otelcol_cumulativetodelta_datapoints_dropped_total[1h]))"
kubectl get --raw "${P}?query=sum%20by%20(outcome)%20(increase(%7B__name__%3D%22otelcol.elasticsearch.docs.processed_total%22%7D%5B15m%5D))"
# kmsg baseline over the SAME [45m] window §4.4 gates on (pre-roll reference only;
# §4.4's authoritative read is post-roll):
kubectl get --raw "${P}?query=sum%20by%20(net_peer_ip)%20(increase(talos_kernel_kmsg_lines_total%5B45m%5D))"

# 2.5 — pre-state is clean (nothing already broken that we would be blamed for)
kubectl get pods -n monitoring -l app=edot-collector -o wide
kubectl get pvc -n monitoring edot-collector-queue
flux get kustomizations -n monitoring | awk 'NR==1 || $4 != "True"'
# PASS: 1/1 Running, PVC Bound, no kustomization off True.
```

## 3) Steps (GitOps)

**1. Silence expected rollout noise and mark the update active.** Alert names
below were read from
`kubernetes/apps/monitoring/kube-prometheus-stack/app/otel-collector-alerts.yaml`
(all nine exist):

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 >/dev/null 2>&1 & PF=$!
sleep 3
NOW=$(python3 -c "from datetime import *;print(datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
END=$(python3 -c "from datetime import *;print((datetime.now(timezone.utc)+timedelta(hours=4)).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
curl -s -X POST localhost:9093/api/v2/silences -H 'Content-Type: application/json' -d '{
  "matchers":[{"name":"namespace","value":"monitoring","isRegex":false,"isEqual":true},
              {"name":"alertname","value":"EdotCollectorDown|OtelDaemonCollectorDown|OtelCollectorExportFailed|OtelCollectorRecordsRefused|OtelCollectorQueueFull|EdotCollectorESAuthError|EsMetricsIngestionStalled|EsLogIngestionStalled|EsExportQueueStuckFull","isRegex":true,"isEqual":true}],
  "startsAt":"'"$NOW"'","endsAt":"'"$END"'","createdBy":"maintenance-window-agent",
  "comment":"edot-collector 0.160.0->0.161.0 — expected rollout noise. auto-expires 4h"}' \
  | tee /private/tmp/claude-501/edot-0161-silence.json; echo   # prints {"silenceID":"..."}; empty = NOT silenced
kill $PF 2>/dev/null
runbooks/update-marker.sh add edot-collector monitoring 4 "0.160.0->0.161.0 bump"
```

**2. Edit the image tag.** Two lines, one file — this is the whole change. The
`sed` below was DRY-TESTED on a scratch copy on macOS (BSD sed) while planning;
the resulting diff is pasted verbatim underneath (authoring rule 3):

The rollout-revision stamp is derived from the EXECUTION date, not hard-coded —
the pre-review file pinned it to `2026-09-17.1`, which is already stale and would
stamp a false date on whatever night this actually runs.

```bash
REV="$(date -u +%Y-%m-%d).1"
sed -i '' \
  -e 's|image: otel/opentelemetry-collector-contrib:0.160.0|image: otel/opentelemetry-collector-contrib:0.161.0|' \
  -e 's|cberg.dev/rollout-revision: ".*"|cberg.dev/rollout-revision: "'"$REV"'"|' \
  kubernetes/apps/monitoring/edot-collector/app/deployment.yaml
git diff --stat kubernetes/apps/monitoring/edot-collector/app/deployment.yaml
```

DRY-TESTED 2026-09-20 on a scratch copy of the real file on macOS (BSD sed);
`sed` exited 0 and `diff` returned exactly these two hunks, pasted verbatim
(authoring rule 3). Note the revision pattern is `".*"`, not a `\s`-class or a
literal old date: BSD sed has no `\s`, and a literal old date makes the command
a silent no-op the moment another plan stamps the line first.

```
26c26
<         cberg.dev/rollout-revision: "2026-09-13.1"
---
>         cberg.dev/rollout-revision: "2026-09-20.1"
40c40
<           image: otel/opentelemetry-collector-contrib:0.160.0
---
>           image: otel/opentelemetry-collector-contrib:0.161.0
```

**Both hunks must be present.** If only hunk 26 appears, the image line did not
match — STOP: premise 1 has been invalidated since §2.1. If only hunk 40
appears, the revision line moved; set it by hand (traceability only, not
functional).

**3. Commit and push** (shared worktree — `--only`, never `git add -A`):

```bash
git fetch origin main && git merge --ff-only origin/main
MSG=/private/tmp/claude-501/msg-edot-collector-0.161.0-$(date +%s).txt
printf '%s\n' "chore(monitoring): edot-collector 0.160.0 -> 0.161.0 (plan edot-collector-0.161.0)" > "$MSG"
git commit --only kubernetes/apps/monitoring/edot-collector/app/deployment.yaml -F "$MSG"
git show --stat HEAD   # exactly one file: deployment.yaml
git log -1 --format=%s     # MUST be your subject; amend before pushing if not
git push origin main
```

**4. Reconcile and watch the Recreate roll.** `strategy: Recreate` is load-bearing
here: the pod mounts an RWO Longhorn PVC at `replicas: 1`, so the old pod must
fully terminate and detach before the new one starts, or the replacement blocks
forever on `Multi-Attach` (`docs/sops/longhorn-rwo-multi-attach.md`). Do **not**
hand-delete pods mid-roll.

**THE NAMESPACE IS `monitoring`, NOT `flux-system`.** Measured 2026-09-20:
`kubectl get kustomization -n flux-system edot-collector` returns NotFound, while
`kubectl get kustomization -A` shows it in `monitoring` (and the Deployment
carries `kustomize.toolkit.fluxcd.io/namespace: monitoring`). The pre-review file
said `-n flux-system`, which does not merely error — it fails as a FALSE GREEN:
the reconcile errors, and the very next `kubectl rollout status` then reports
"successfully rolled out" instantly against the OLD, unchanged generation (this
repo's documented rollout-status-green-lights-the-old-generation trap), after
which every §4 gate measures a still-healthy 0.160.0 and passes. Under the
derived AUTO-NIGHT class that records an unattended SUCCESS on a bump that never
shipped. §2.5 already used `-n monitoring`, so this was an internal
inconsistency, not a belief.

```bash
GEN_BEFORE=$(kubectl get deployment edot-collector -n monitoring -o jsonpath='{.metadata.generation}')
flux reconcile kustomization edot-collector -n monitoring --with-source
# PROVE the new spec actually landed BEFORE trusting rollout status:
kubectl get deployment edot-collector -n monitoring \
  -o jsonpath='{.spec.template.spec.containers[0].image}'; echo
GEN_AFTER=$(kubectl get deployment edot-collector -n monitoring -o jsonpath='{.metadata.generation}')
echo "generation $GEN_BEFORE -> $GEN_AFTER"
kubectl rollout status deployment/edot-collector -n monitoring --timeout=180s
kubectl get pods -n monitoring -l app=edot-collector -o wide
# record the new pod's start time — §4.3 needs it as the range floor
kubectl get pods -n monitoring -l app=edot-collector \
  -o jsonpath='{.items[0].status.startTime}' > /private/tmp/claude-501/edot-0161-rollout-ts
cat /private/tmp/claude-501/edot-0161-rollout-ts; echo   # MUST be non-empty and AFTER the push time
```

**HARD GATE before proceeding:** the printed image must read `:0.161.0` AND
`GEN_AFTER` must be greater than `GEN_BEFORE`. If the image still reads
`:0.161.0` but the generation did NOT advance, the spec was already at the target
and nothing rolled. If the image still reads `:0.160.0`, the reconcile did not
apply — do NOT continue into §4, whose gates would all pass on the old binary.

**5. Wait 15 minutes** before §4 (2026-09-26 review: §4.4 is now an ES read over
[ROLLOUT_TS, now]; the 45-minute sizing below belonged to the retired counter gate
and is historical). Original text: This is the measurement, not padding: §4.4's
per-node kmsg gate must read a window lying ENTIRELY after the roll, and [45m] is
the shortest window with a measured non-zero floor on every node (frontmatter
`est_duration_min`). §4.1–4.3 could be read at T+15m, but §4.4 is the gate that
decides, so the settle is sized on it.

## 4) Verification

### Floor (shape — necessary, NOT sufficient)

```bash
kubectl get deployment edot-collector -n monitoring -o jsonpath='{.status.readyReplicas}'; echo
# MECHANICAL digest comparison — not "must name 0.161.0's digest" by eye
TARGET_DIGEST=sha256:fd328de2552466ad78385e1b1289c3f2402b1c45f265b252aab1955b42845ac1
LIVE_ID=$(kubectl get pods -n monitoring -l app=edot-collector \
  -o jsonpath='{.items[0].status.containerStatuses[0].imageID}')
echo "live: $LIVE_ID"
case "$LIVE_ID" in
  *"$TARGET_DIGEST") echo "DIGEST_OK" ;;
  *) echo "DIGEST_MISMATCH" ;;
esac
kubectl logs -n monitoring deploy/edot-collector | head -80 | grep -iE "error|invalid configuration|panic" || echo "no startup errors"
# can-fail shown 2026-09-26: the same grep on the 0.160.0 pod's tail matched 5 lines.
```

**PASS:** `readyReplicas` is 1, the digest check prints `DIGEST_OK`, and the grep
prints `no startup errors`.

The digest comparison is literal because the pre-review instruction — "`imageID`
must name 0.161.0's digest" — was not mechanically checkable: no digest was ever
captured, so the step could only ever be eyeballed, and an eyeball on a 64-char
hex string is not a gate. `$TARGET_DIGEST` is the MANIFEST-LIST digest recorded
in §2.2; measured 2026-09-20, `imageID` carries the manifest-list digest
(`...@sha256:799dc6cf...` for the running 0.160.0, which equals Docker Hub's
`digest` field for that tag), NOT the per-arch amd64 digest. Comparing against
the amd64 digest would print `DIGEST_MISMATCH` on a perfectly good roll.
The grep is case-insensitive deliberately — upstream logs mixed case.

### CONTENTS ASSERTION 4.1 — telemetry still FLOWS

CONTENTS ASSERTION: *the exporters are still persisting records and points* —
measured by `increase(...[15m])` over a window starting after the new pod is
Ready, compared to the §2.4 baselines.

```bash
P=/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query
kubectl get --raw "${P}?query=sum(increase(otelcol_exporter_sent_log_records_total[15m]))"
kubectl get --raw "${P}?query=sum(increase(otelcol_exporter_sent_metric_points_total[15m]))"
```

**PASS:**
- **log records — a FLOOR, not a band: `>= 10000`.** The pre-review ±40%
  two-sided band false-fails on a healthy cluster. Measured 2026-09-20, the
  24h range of `sum(increase(...[15m]))` is **35,927 – 57,673** — a 1.6x natural
  spread, so a baseline taken near the low end and a post-roll read near the high
  end is +60% and trips the band with nothing wrong. Under AUTO-NIGHT that
  auto-reverts a good bump. The plan's own stated intent ("a trickle is a
  failure") is a floor. RE-MEASURED 2026-09-26 (review): the 7d minimum of
  `sum(increase(...[15m]))` is **20,530** (24h range 21,673 - 89,933), so the
  earlier 20,000 floor had ~3% headroom and would false-fail a healthy roll in a
  quiet quarter-hour. The floor is **10,000**, about half the 7d minimum:
  reachable only by a real collapse, never by diurnal variation.
- **metric points — a band IS legitimate here: within ±20% of the §2.4
  baseline.** Measured 2026-09-20, the same 24h range is **3,217,392 –
  3,246,244**, a spread of under 1%. This series is genuinely flat, so a band
  costs nothing and catches a partial pipeline loss that a floor would miss.

**FAILS AS:** an empty `result` array (the metric stopped being exported — the
`without_type_suffix` rename mode from §1.3 looks exactly like this), or a value
near zero (the collector is Ready but shipping nothing). Total silence must never
score as success: an empty result is a FAIL, not a skip.

### CONTENTS ASSERTION 4.2 — Elasticsearch is not silently REJECTING

CONTENTS ASSERTION: *per-document outcome at the ES exporter is success-only* —
measured by the elasticsearchexporter's own outcome counter, which survives pod
restarts, compared to the §2.4 baseline.

> **Use the DOTTED metric name.** This is a correction of the retired
> `edot-collector-0.160.0` plan, which asserted on
> `otelcol_elasticsearch_docs_processed_total{outcome!~"success|retried"}`.
> That series **does not exist**: because the configmap pins
> `without_type_suffix`/`without_units`/`without_scope_info` to `false`, the
> exporter's own metrics keep dots and are exposed as
> `otelcol.elasticsearch.docs.processed_total`. RE-MEASURED 2026-09-20 over the
> same [15m] window this gate uses: the underscored form returns EMPTY, the
> dotted form returns `outcome="success"` = 1,140,668. The
> underscored gate therefore read EMPTY before and after — it could never fail,
> and it shipped in an executed plan. `docs/sops/monitoring.md` §365 has the
> correct escaped form; use it.

```bash
P=/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query
# (a) the FLOOR — success series must exist and be non-zero
kubectl get --raw "${P}?query=sum%20by%20(outcome)%20(increase(%7B__name__%3D%22otelcol.elasticsearch.docs.processed_total%22%7D%5B15m%5D))"
# (b) the CEILING — non-success outcomes must be absent/zero
kubectl get --raw "${P}?query=sum%20by%20(outcome)%20(increase(%7B__name__%3D%22otelcol.elasticsearch.docs.processed_total%22%2Coutcome!~%22success%7Cretried%22%7D%5B15m%5D))"
```

**PASS:** (a) returns an `outcome="success"` element with a non-zero value, AND
(b) returns an empty result (or zeros).
(b) CAN fail - demonstrated 2026-09-26: `max_over_time` of query (b) over 30d returns
`outcome="timeout"` 46,357 (ES-side burst 2026-09-24 ~20:28Z, open finding F-c5333426;
zero in every other hour of 7d). Attribution: `failed_client` is the binary/config
signal (revert); a non-zero `timeout`/`internal_server_error` is ES-side - check
`_cluster/health` and elasticsearch-obs-recovery's last Job before reverting.
**FAILS AS:** (b) returning `failed_client` — that is precisely the
`managedFields`-class signature from §1.5, i.e. the transform stopped matching
under the new binary while the pod looked perfectly healthy. Per
`docs/sops/monitoring.md`, a **missing `success` series in (a) is also a FAIL**
("rejection SLI blind"): empty non-success means zero only if the success series
proves the counter is alive. That is what makes this gate two-sided rather than a
shape check.

### CONTENTS ASSERTION 4.3 — documents actually LANDED in Elasticsearch

CONTENTS ASSERTION: *new documents exist in both data streams with a timestamp
after the roll* — measured in ES itself, not via the exporter's self-report.
This matters because the ES `_bulk` API returns HTTP 200 even when every item
inside is rejected, so "sent" is not "stored".

```bash
ES_PW=$(kubectl get secret -n monitoring elasticsearch-es-elastic-user -o jsonpath='{.data.elastic}' | base64 -d)
kubectl port-forward -n monitoring svc/elasticsearch-es-http 9200:9200 >/dev/null 2>&1 & PF=$!
sleep 4
ROLLOUT_TS=$(cat /private/tmp/claude-501/edot-0161-rollout-ts)   # written in §3.4
test -n "$ROLLOUT_TS" || echo "NO_ROLLOUT_TS -> FAIL"
for DS in logs-generic-default metrics-generic.otel-default; do
  echo -n "$DS "
  curl -k -s -u "elastic:$ES_PW" -H 'Content-Type: application/json' \
    -X POST "https://localhost:9200/$DS/_count" \
    -d '{"query":{"range":{"@timestamp":{"gte":"'"$ROLLOUT_TS"'"}}}}' \
    | python3 -c "import sys,json;print(json.load(sys.stdin).get('count'))"
done
curl -k -s -u "elastic:$ES_PW" "https://localhost:9200/_cluster/health" \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['status'],d['unassigned_shards'])"
kill $PF 2>/dev/null
```

**PASS:** both counts > 0 and rising on a re-run; cluster `green`/`yellow` with 0
unassigned.
**FAILS AS:** a count of 0 — the hard "are we blind" answer, and a hard stop
regardless of what the pod or the health endpoint say.
Baseline for scale (2026-09-17, 15m): logs ~38,100, metrics ~1,070,600.

### CONTENTS ASSERTION 4.4 — the Talos kmsg path re-established on ALL THREE nodes

CONTENTS ASSERTION: *every node is still shipping kernel logs* — measured
per-node, because this path has failed silently before.

**SUPERSEDED 2026-09-26 (review): the Prometheus-counter gate is RETIRED.** Re-measured
live: since 2026-09-23 ~00:00Z (Talos discovery-registry noise removed, 40d7dc78)
per-node kmsg volume fell ~15x. `sum by (net_peer_ip)(increase(talos_kernel_kmsg_lines_total[45m]))`
read **0 / 0 / 27** (.11/.12/.13) on the untouched, healthy 0.160.0 pod at 05:17Z; its
zero-fraction over the last 2d is **62% / 85% / 56%**, and `.12` had no current series
at all. The counter also undercounts ES by about two orders of magnitude (ES holds
~7,500 talos-kernel docs per 12h from .11). Read at T+45m it would fail a good roll
most of the time. The table and prose further down describe the retired gate and are
historical. The gate is now an ES read over the post-roll window, at T+15m:

```bash
ES_PW=$(kubectl get secret -n monitoring elasticsearch-es-elastic-user -o jsonpath='{.data.elastic}' | base64 -d)
ROLLOUT_TS=$(cat /private/tmp/claude-501/edot-0161-rollout-ts)
test -n "$ROLLOUT_TS" || echo "NO_ROLLOUT_TS -> FAIL"
kubectl port-forward -n monitoring svc/elasticsearch-es-http 19211:9200 >/dev/null 2>&1 & PF=$!
sleep 4
curl -k -s -u "elastic:$ES_PW" -H 'Content-Type: application/json' \
  "https://localhost:19211/logs-generic-default/_search" \
  -d '{"size":0,"query":{"bool":{"filter":[{"term":{"attributes.log_source":"talos-kernel"}},{"range":{"@timestamp":{"gte":"'"$ROLLOUT_TS"'"}}}]}},"aggs":{"ip":{"terms":{"field":"attributes.net.peer.ip","size":5}}}}' \
  | python3 -c "import sys,json;d=json.load(sys.stdin);b={x['key']:x['doc_count'] for x in d['aggregations']['ip']['buckets']};print(b);print('KMSG_OK' if b.get('192.168.55.11',0)>=20 else 'KMSG_FAIL')"
kill $PF 2>/dev/null
```

**PASS (revert authority):** `KMSG_OK` - node `.11` (steady ~9-10 lines/min; 7,500-8,000
per 12h, 2026-09-23..26) has >= 20 talos-kernel docs in ES after the roll, proving
LB 192.168.55.18 -> udplog receiver -> ES works on the new binary.
Both sides DEMONSTRATED 2026-09-26 with this exact command: gte 05:00Z printed
`{'192.168.55.11': 235, '192.168.55.13': 154, '192.168.55.12': 31}` / `KMSG_OK`; gte a
future timestamp printed `{}` / `KMSG_FAIL`. A KeyError on `aggregations` is a FAIL.
**.12 / .13 - INFORMATIONAL, no revert authority:** they are genuinely quiet (0-700
docs per 12h since 09-23; .12 had 1 doc in one 12h bucket), so no in-window read can
prove their sender resumed. Record their counts. Follow-up owed by the next sweep:
talos-kernel docs per node in ES over the 24h after ROLLOUT_TS must be >= 1 each,
else file a finding (UDP-sender wedge, docs/troubleshooting/node-reboot-observability.md).

**RETIRED PASS (historical):** three elements, one per node (`192.168.55.11/.12/.13`), each `>= 1`.
**FAILS AS:** two elements instead of three, or any element at 0 — a node's UDP
sender did not resume after the pod restart. Not hypothetical: nuc14-03 stopped
shipping kmsg on 2026-08-04 and nobody noticed for **4 days**, which is why the
`talos_kernel_kmsg_lines` counter exists at all. A cluster-wide aggregate would
hide exactly this, so the gate is deliberately per-node.

**Why `[45m]` and not `[15m]` — the pre-review gate FALSE-FAILED on a healthy
cluster.** It read `increase(...[15m])` and demanded all three nodes > 0. This is
a tiny, reset-heavy counter: the `count/hwerrors` connector feeds the
`prometheus/hwerrors` exporter on `0.0.0.0:8889` with `metric_expiration: 24h`
(configmap lines 310-318), at only a few lines per node per 15 minutes. Measured
2026-09-20 over 7 days, per node (`.11/.12/.13`):

| window | min increase | fraction of windows reading ZERO |
|---|---|---|
| `[15m]` | 0 / 0 / 0 | **6.5% / 10.7% / 13.1%** |
| `[30m]` | 0 / 0 / 0 | 0.9% / 0.9% / 1.5% |
| `[45m]` | **3.0 / 3.0 / 3.0** | **0% / 0% / 0%** |
| `[1h]` | 6.0 / 6.0 / 6.1 | 0% / 0% / 0% |

At `[15m]` the chance that at least one of the three nodes reads zero with
nothing wrong is `1 - (0.935 x 0.893 x 0.869)` = **~27%**: roughly one run in
four would auto-revert a healthy bump, unattended. `[45m]` is the shortest window
with a measured zero-fraction of 0 on all three nodes over 7 days, and its floor
of 3 lines gives the `>= 1` threshold 3x headroom.

**The window must not straddle the roll.** Widening to `[1h]` but reading it at
T+15m would be worse than the original: the range would include 45 minutes of
PRE-roll lines, so a node that went permanently silent at the restart still
reports a healthy non-zero — a gate that passes on exactly the failure it exists
to catch. That is why the settle in §3.5 is 45 minutes and this read happens
after it, not why the plan is slow.

**The pre-review baseline did not support the gate either:** it cited "19.2 /
15.1 / 22.2" measured over **1h** as the reference for a **15m** gate — a number
in the wrong units, roughly 4x the value the gate would actually see.

### CONTENTS ASSERTION 4.5 — no NEW metric-drop class

CONTENTS ASSERTION: *the ES metric-rejection rate did not worsen* — compared to
the §2.4 baseline, **not** to zero.

```bash
P=/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query
kubectl get --raw "${P}?query=sum(increase(otelcol_cumulativetodelta_datapoints_dropped_total[1h]))"
```

**THIS LIMB IS INFORMATIONAL AND CARRIES NO REVERT AUTHORITY.** Record the
pre-roll and post-roll values in the window log; a difference is a note for the
operator, not a rollback trigger.

**WARN (operator note only):** post-roll `[1h]` value **> 6,000**.
**PASS:** anything at or below that, including 0.

**The ±25% band from the pre-review file was unusable in BOTH directions, and its
baseline was off by roughly 1300x.** It cited "~2,624/h"; re-measured 2026-09-20,
the `[1h]` value is **2.0**. The counter is bursty across three orders of
magnitude — over 24h, `increase(...[1h])` ranges **0 to 601** and
`increase(...[6h])` ranges **2.0 to 6,014** (raw counter 27,092). A ±25% band on
a window whose healthy range spans 0..601 fails a good bump whenever a burst
lands post-roll and passes a real regression whenever one does not: a coin flip
with revert authority, under AUTO-NIGHT, on a healthy cluster. The 6,000 WARN
ceiling is 10x the measured 24h maximum of any single `[1h]` window, so it trips
only on a genuinely new drop class, not on burstiness.

**Do not assert zero here**: this counter is already non-zero because of the open
findings `F-f8801413` / `F-b780647b` (§1.6) — the `cumulativetodelta/es-histograms`
include list is `match_type: strict` (configmap line 105), so each new Envoy
histogram family silently drops until hand-added. A `== 0` gate would fail every
time for a pre-existing reason.

**The real ES-rejection signal is §4.2(b), which does carry revert authority.**
That gate reads the exporter's own per-document outcome counter and is two-sided;
this one is a coarse secondary indicator and is scored as such.

### 4.6 Alerts quiet

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 >/dev/null 2>&1 & PF=$!
sleep 3
curl -s http://localhost:9093/api/v2/alerts | python3 -c "
import sys,json
for a in json.load(sys.stdin):
    n=a['labels'].get('alertname')
    if n in ('Watchdog','InfoInhibitor'): continue
    if a['labels'].get('component')=='otel-collector': print(n, a['status']['state'])"
kill $PF 2>/dev/null
```

**PASS:** nothing firing that is not covered by the §3.1 silence. Baseline: zero
non-Watchdog alerts firing cluster-wide on 2026-09-17.

## 5) Rollback

### 5.1 Primary — revert the commit

Image-tag-only change, config untouched:

```bash
git fetch origin main && git merge --ff-only origin/main
git revert --no-edit <bump-commit-sha>
git push origin main
# NAMESPACE IS `monitoring` — see §3.4. With `-n flux-system` this reconcile
# errors, the rollout status below then returns "successfully rolled out"
# against the unchanged generation, and THE ROLLBACK REPORTS SUCCESS WITHOUT
# HAVING REVERTED ANYTHING — at the worst possible moment.
flux reconcile kustomization edot-collector -n monitoring --with-source
kubectl rollout status deployment/edot-collector -n monitoring --timeout=180s
kubectl get pods -n monitoring -l app=edot-collector \
  -o jsonpath='{.items[0].spec.containers[0].image}'; echo
# PROVE the revert actually took, mechanically:
ROLLBACK_DIGEST=sha256:799dc6cf12c96192af37b5bdba804da8c10b3bc563b43cb90c3f3c58d9572ad6
LIVE_ID=$(kubectl get pods -n monitoring -l app=edot-collector \
  -o jsonpath='{.items[0].status.containerStatuses[0].imageID}')
case "$LIVE_ID" in
  *"$ROLLBACK_DIGEST") echo "ROLLBACK_DIGEST_OK" ;;
  *) echo "ROLLBACK_DIGEST_MISMATCH: $LIVE_ID" ;;
esac
```

`$ROLLBACK_DIGEST` is 0.160.0's manifest-list digest, measured live 2026-09-20
from the currently-running pod's `imageID` (it equals Docker Hub's `digest` for
tag 0.160.0). The image-tag print alone is not proof — the tag string can be
correct while the pod still runs the old layer mid-roll.

Then **re-run §4.1 through §4.4** to confirm ingestion actually resumed on
0.160.0. A revert that restores the manifest but not the telemetry is not a
rollback.

### 5.2 Contingency — the one forward-only surface

The bbolt sending-queue on `pvc/edot-collector-queue` is written by whichever
binary is running. Nothing in core or contrib 0.161.0 changes the persistent-queue
format, so the expected case is that 0.160.0 reads it back fine. **If instead the
reverted pod crashloops on the queue file**, do not keep retrying:

```bash
kubectl logs -n monitoring deploy/edot-collector --tail=50 | grep -iE "bolt|storage|queue|corrupt"
```

If the failure names the queue store, the recovery is to discard the buffer — it
holds only in-flight telemetry already accepted by ES or replayable by the
producers, never durable state:

1. `kubectl scale deploy/edot-collector -n monitoring --replicas=0` (releases the
   RWO volume).
2. Mount `pvc/edot-collector-queue` in a throwaway pod and delete the contents of
   `/var/lib/otelcol/sending-queue`.
3. `kubectl scale deploy/edot-collector -n monitoring --replicas=1`, then re-run
   §4.1–§4.3.

Cost is bounded: the buffered records only. `file_storage/queue` has
`create_directory: true`, so an empty directory is a clean start, not a crash.
**This step is operator-visible** — record it, because it is the only part of this
plan that loses data.

### 5.3 Restore alert state (either outcome)

```bash
runbooks/update-marker.sh clear edot-collector
# delete the §3.1 silence (id persisted in §3.1), one Bash call:
kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 >/dev/null 2>&1 & PF=$!
sleep 3
SID=$(python3 -c "import json;print(json.load(open('/private/tmp/claude-501/edot-0161-silence.json'))['silenceID'])")
curl -s -o /dev/null -w 'delete silence %{http_code}\n' -X DELETE "localhost:9093/api/v2/silence/$SID"
kill $PF 2>/dev/null
```

## 6) Interference notes

- **2026-09-26 NOW run ordering (review).** kube-prometheus-stack-91.4.1 EXECUTED
  (598bbce7; Prometheus restarted ~04:57Z; TSDB retained) - spent. Run
  `elasticsearch-obs-recovery-3.14.7` FIRST and start this plan only after its §4
  (two post-push */10 runs + §4.5) is recorded: its job acts on ES/ingestion state and
  its §4.5 reads the ES stall ALERTS this roll can perturb (it declares this plan in
  conflicts_with). Settle >= 10 min after it closes (one clean */10 run). No mechanism
  links this plan to prometheus-pushgateway-3.9.0 (monitoring), paperclip (ai) or
  crash-ghost-reaper (kube-system); parallel is acceptable.

- **`conflicts_with` is FOUR entries and every one names a mechanism** — see the
  frontmatter. The ones the window agent must not relax: `prometheus-crd-ownership`
  (an otel-operator helm upgrade, which rolls the daemon collectors that export
  into this collector), `kube-prometheus-stack-91.4.1` (a Prometheus restart
  blinds every gate in §4 and would read as this plan regressing), and
  `otel-operator-0.23.0` (below).
- **CAPACITY: this plan fills the nightly budget exactly and cannot share it.**
  `est_duration_min: 70`; `window-scheduler.py` computes the slot budget as
  `duration_min - STEP0_RESERVE_MIN` = `90 - 20` = **70m** for `nightly`, and
  places a plan only while `rmins + dur <= budget`. So it fits an unattended
  nightly slot **only as the sole plan in it**. Any other plan already holding
  that night pushes this one out — which is correct, not a defect: Step 0's
  safe-update apply runs first in EVERY window regardless.
- **`otel-operator-0.23.0` is now DECLARED (frontmatter), and the earlier "the
  collision is spent" argument is WITHDRAWN.** `otel-operator-0.21.0` did execute
  in `nightly:2026-09-17` with its file retired in `37f7c7a6`, but the mechanism
  it described is durable and `otel-operator-0.23.0` (draft, window null, risk
  high, human-gated) is its heir. That plan already lists
  `edot-collector-0.161.0` in its own `conflicts_with` (verified 2026-09-20).
- **Reciprocity is HONOURED BY THE SCHEDULER — verified in code, 2026-09-20.**
  The pre-review text warned that a one-sided guard protects only one direction.
  That is no longer true: `window-scheduler.py` (lines 254-266) builds
  `names_me = {p for p in here_plans if pid in p.conflicts_with}` and skips the
  slot on `(conflicts & here) or names_me`, with the comment that the relation
  "is symmetric by meaning ... so it is symmetric here". Measured rationale in
  that comment: 21 of 21 declarations across the plan set were one-sided.
  So the missing reciprocal entries in `prometheus-crd-ownership` and
  `kube-prometheus-stack-91.4.1` are a **readability** gap, not a scheduling
  hole — worth adding, not blocking. `--validate` still checks only that refs
  *resolve*.
- **The earlier "three dead refs" claim was FALSE and is removed.** Re-checked
  2026-09-20: `maintenance-plan.py --validate` exits 0 with "all plan frontmatter
  invariants hold", and `grep -rn '^  - otel-operator-0.21.0' plans/*.md` returns
  nothing. Every surviving mention of that retired plan sits inside a comment or
  prose, not a list entry — `cilium-1.20.2`, `kube-prometheus-stack-91.4.1` and
  `prometheus-crd-ownership` each already removed the ref with a dated comment.
  No repo sweep is owed; the pre-review bullet sent the window agent after work
  that does not exist.
- **POLICY-DB item, NOT a git change:** AR-124's needle is the bare substring
  `opentelemetry-collector`, which over-matches this plan's own VERSION row
  (`F-cb9182ca`) and marks it `accepted`, even though AR-124's justification
  scopes it to CVE rows and calls the bump window-work. `F-e430800e` already
  prescribes narrowing it and names this plan. Until that lands, this plan's
  target reads as an accepted risk rather than queued work. Fix with
  `runbooks/policy-cli.py risk`, not by editing any file here.
- **Ordering against ANY otel-operator plan (the durable rule).** An
  otel-operator helm upgrade rolls `daemonset/otel-operator-daemon-collector`,
  and those daemon pods export into this collector at
  `edot-collector.monitoring.svc:4317` over OTLP using the **default in-memory**
  sending queue. A simultaneous edot restart is therefore buffered for only
  seconds and lost past that — and, worse, it makes any resulting telemetry gap
  unattributable between the two changes. They must not share a window; if an
  operator overrides that, run **edot first and let its §4 fully pass** before the
  operator plan starts.
- **Expect a genuine ingestion gap of tens of seconds** during the `Recreate`
  swap. That is by design and is what the on-disk bbolt queue absorbs on the
  producer side: every ES exporter sets `block_on_overflow: true`, so producers
  see backpressure (`otelcol_receiver_refused_*`, which is alerted) rather than a
  silent drop. Do not read that gap as a fault.
- **A separate, unrelated ES pod-log gap may be visible from the otel-operator
  daemon roll**: those DaemonSet pods use `file_log` with `start_at: end` and no
  checkpoints, so each node's pod logs have a ~10-30 s hole during its own
  restart. That is a pre-existing property of that deployment, **not** an edot
  fault — another reason the two must not share a window, since it makes any gap
  unattributable.
- **The edot image is minimal — no `cat`, `curl` or `wget`.** Every check above
  uses `kubectl get --raw` (API-server service proxy) or `port-forward` + local
  `curl`, never `kubectl exec`. Port-forwards are captured with `$!` and killed by
  PID, never `kill %1` (no job control in a non-interactive shell).
- **The HTTPRoute backend is briefly down.** `httproute/edot-collector` fronts
  OTLP/HTTP 4318 on `envoy-internal`. This plan does not change routing, so
  `touches.shared` deliberately does **not** claim `gateway/envoy`; only the
  backend is unavailable for the roll.
- **What this plan does NOT do, on purpose:** it does not touch
  `configmap/edot-collector-config` (§1.6 — the F-dc898b50 cardinality filter and
  the F-f8801413 `match_type` fix both belong to their own change), it does not
  move the daemon collector (`otel/opentelemetry-collector-k8s:0.154.0`, a
  different HelmRelease), and it does not resize or migrate the queue PVC.
