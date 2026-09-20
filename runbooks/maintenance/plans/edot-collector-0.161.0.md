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
est_duration_min: 40              # 8 pre-checks (incl. the validate pod + four
                                  # baselines) + 3 edit/commit/push + 4 reconcile
                                  # and Recreate roll + 15 SETTLE (the rate gates
                                  # in §4 need a 15m window that STARTS after the
                                  # new pod is Ready — this is not padding, it is
                                  # the measurement) + 10 verification.
                                  # Prior comparable plan (0.158->0.160) was 25m
                                  # and did not budget the settle honestly.
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
  - prometheus-crd-ownership      # It is an otel-operator HELM UPGRADE, so it
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
security_ref: null                # No security driver for this image. AR-072 was
                                  # NARROWED on 2026-09-15 to the description
                                  # `opentelemetry-operator` and scopes the
                                  # collector-k8s image (the DAEMON, finding
                                  # F-ba45c963) — not
                                  # otel/opentelemetry-collector-contrib, which
                                  # this plan moves. The config-validation gate in
                                  # §2.3 therefore stands on the documented 2026-08
                                  # incident (§1.5), NOT on a rule's reason text.
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
finding_refs: []                  # DELIBERATELY EMPTY, and argued — not an
                                  # oversight. Two separate checks, both run
                                  # 2026-09-17 with SWEEP_PG_DSN up:
                                  # (1) There is NO sweep finding for this
                                  #     component/target to name. `finding list
                                  #     --section version --limit 60` returns 24
                                  #     rows with no edot-collector row, and
                                  #     `finding list --grep 0.161` returns none.
                                  # (2) F-dc898b50 (the ES-storage/Envoy-cardinality
                                  #     finding whose fix lives in THIS directory)
                                  #     is deliberately NOT claimed here, because
                                  #     this plan does not fix it (§1.6). Claiming
                                  #     it would make finding-triage.py's
                                  #     plan-or-page pass read that finding as
                                  #     PLANNED and stop paging for it, while
                                  #     nothing in this plan remediates it. It
                                  #     SHOULD keep reading as unplanned until it
                                  #     gets its own plan or DECIDE routing.
status: draft
window: null                      # the scheduler assigns. Shape: no reboot, no
                                  # capability change, git-revert, 40m — fits
                                  # `nightly` (90m). But NOT nightly:2026-09-17,
                                  # which otel-operator-0.21.0 already holds and
                                  # which conflicts_with excludes.
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

Blast radius and failure *mode*, not likelihood. This single-replica Deployment is
the only OTLP path into Elasticsearch for every namespace's logs, metrics and
traces, plus the Talos kmsg sink on `192.168.55.18`. Its characteristic failure is
**silent**: the pod stays Ready, the health endpoint stays 200, and telemetry
simply stops being counted. That is why §4 is built on contents assertions with a
floor, and why "pod Ready" is explicitly not the gate.

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

# 2.2 — target tag is published and multi-arch (measured while planning:
# pushed 2026-09-16T03:01:45Z, amd64 present)
curl -s "https://hub.docker.com/v2/repositories/otel/opentelemetry-collector-contrib/tags/0.161.0" \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['name'],d['tag_last_pushed'],[i['architecture'] for i in d['images']])"
# PASS: prints 0.161.0 with linux/amd64 present.
# FAILS AS: a 404 body -> KeyError/'httpStatus' -> the tag does not exist.

# 2.3 — HARD GATE: validate the LIVE config against the NEW binary.
# A config the new binary rejects crashloops the entire cluster-wide ingest path.
kubectl run edot-validate-0161 --rm -i --restart=Never \
  --image=otel/opentelemetry-collector-contrib:0.161.0 \
  --overrides='{"spec":{"containers":[{"name":"edot-validate-0161","image":"otel/opentelemetry-collector-contrib:0.161.0","command":["/otelcol-contrib","validate","--config=/config/otel.yml"],"env":[{"name":"ES_PASSWORD","value":"dummy-validate-only"}],"volumeMounts":[{"name":"cfg","mountPath":"/config"}]}],"volumes":[{"name":"cfg","configMap":{"name":"edot-collector-config"}}]}}'
echo "validate exit=$?"
# PASS: exit 0 AND no output containing (case-insensitively) "error" / "invalid
# configuration" / "cannot unmarshal". Read the OUTPUT, not only the code.
# FAILS AS: a line naming the rejected key, e.g. an unknown `without_type_suffix`
# under service::telemetry, or an unrecognised `sending_queue` key. If it fails,
# this plan is BLOCKED — the bump needs a config change first, which is a
# different plan.

# 2.4 — BASELINES for §4. Record all five numbers; §4 compares against them.
# Measured 2026-09-17 while planning, for reference (yours will differ):
#   sent log records 15m      ~39,900
#   sent metric points 15m    ~3,151,700
#   docs.processed success 6h ~26,850,000   non-success: EMPTY (= 0, healthy)
#   cumulativetodelta dropped 1h ~2,624     <- ALREADY NON-ZERO (F-f8801413)
#   ES logs-generic-default 15m ~38,100 docs; metrics 15m ~1,070,600 docs
P=/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query
kubectl get --raw "${P}?query=sum(increase(otelcol_exporter_sent_log_records_total[15m]))"
kubectl get --raw "${P}?query=sum(increase(otelcol_exporter_sent_metric_points_total[15m]))"
kubectl get --raw "${P}?query=sum(increase(otelcol_cumulativetodelta_datapoints_dropped_total[1h]))"
kubectl get --raw "${P}?query=sum%20by%20(outcome)%20(increase(%7B__name__%3D%22otelcol.elasticsearch.docs.processed_total%22%7D%5B6h%5D))"

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
  "comment":"edot-collector 0.160.0->0.161.0 — expected rollout noise. auto-expires 4h"}'
kill $PF 2>/dev/null
runbooks/update-marker.sh add edot-collector monitoring 4 "0.160.0->0.161.0 bump"
```

**2. Edit the image tag.** Two lines, one file — this is the whole change. The
`sed` below was DRY-TESTED on a scratch copy on macOS (BSD sed) while planning;
the resulting diff is pasted verbatim underneath (authoring rule 3):

```bash
sed -i '' \
  -e 's|image: otel/opentelemetry-collector-contrib:0.160.0|image: otel/opentelemetry-collector-contrib:0.161.0|' \
  -e 's|cberg.dev/rollout-revision: "2026-09-13.1"|cberg.dev/rollout-revision: "2026-09-17.1"|' \
  kubernetes/apps/monitoring/edot-collector/app/deployment.yaml
git diff --stat kubernetes/apps/monitoring/edot-collector/app/deployment.yaml
```

Expected diff (measured, not predicted):

```
26c26
<         cberg.dev/rollout-revision: "2026-09-13.1"
---
>         cberg.dev/rollout-revision: "2026-09-17.1"
40c40
<           image: otel/opentelemetry-collector-contrib:0.160.0
---
>           image: otel/opentelemetry-collector-contrib:0.161.0
```

If the rollout-revision line does not match (another plan touched it first), set
it by hand — it is traceability only, not functional. If the **image** line does
not match, STOP: premise 1 has been invalidated since §2.1.

**3. Commit and push** (shared worktree — `--only`, never `git add -A`):

```bash
git fetch origin main && git merge --ff-only origin/main
git commit --only kubernetes/apps/monitoring/edot-collector/app/deployment.yaml \
  -m "chore(monitoring): edot-collector 0.160.0 -> 0.161.0 (plan edot-collector-0.161.0)"
git log -1 --format=%s     # MUST be your subject; amend before pushing if not
git push origin main
```

**4. Reconcile and watch the Recreate roll.** `strategy: Recreate` is load-bearing
here: the pod mounts an RWO Longhorn PVC at `replicas: 1`, so the old pod must
fully terminate and detach before the new one starts, or the replacement blocks
forever on `Multi-Attach` (`docs/sops/longhorn-rwo-multi-attach.md`). Do **not**
hand-delete pods mid-roll.

```bash
flux reconcile kustomization edot-collector -n flux-system --with-source
kubectl rollout status deployment/edot-collector -n monitoring --timeout=180s
kubectl get pods -n monitoring -l app=edot-collector -o wide
# record the new pod's start time — §4.3 needs it as the range floor
kubectl get pods -n monitoring -l app=edot-collector \
  -o jsonpath='{.items[0].status.startTime}'; echo
```

**5. Wait 15 minutes** before §4. The rate gates need a window that STARTS after
the new pod is Ready; running them early reads the gap as a regression.

## 4) Verification

### Floor (shape — necessary, NOT sufficient)

```bash
kubectl get deployment edot-collector -n monitoring -o jsonpath='{.status.readyReplicas}'; echo
kubectl get pods -n monitoring -l app=edot-collector -o jsonpath='{.items[0].status.containerStatuses[0].imageID}'; echo
kubectl logs -n monitoring deploy/edot-collector --tail=40 | grep -iE "error|invalid configuration|panic" || echo "no startup errors"
```

`imageID` (not the tag string) must name 0.161.0's digest. The grep is
case-insensitive deliberately — upstream logs mixed case.

### CONTENTS ASSERTION 4.1 — telemetry still FLOWS

CONTENTS ASSERTION: *the exporters are still persisting records and points* —
measured by `increase(...[15m])` over a window starting after the new pod is
Ready, compared to the §2.4 baselines.

```bash
P=/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query
kubectl get --raw "${P}?query=sum(increase(otelcol_exporter_sent_log_records_total[15m]))"
kubectl get --raw "${P}?query=sum(increase(otelcol_exporter_sent_metric_points_total[15m]))"
```

**PASS:** both non-empty and within roughly ±40% of the §2.4 baselines.
**FAILS AS:** an empty `result` array (the metric stopped being exported — the
`without_type_suffix` rename mode from §1.3 looks exactly like this), or a value
near zero (the collector is Ready but shipping nothing). A trickle is a failure,
not a pass — this is the floor half of the rule, and total silence must never
score as success.

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
> `otelcol.elasticsearch.docs.processed_total`. Measured 2026-09-17: the
> underscored form returns EMPTY, the dotted form returns 26.8M success/6h. The
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
ROLLOUT_TS="<the startTime captured in §3.4>"
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

```bash
P=/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query
kubectl get --raw "${P}?query=sum%20by%20(net_peer_ip)%20(increase(talos_kernel_kmsg_lines_total%5B15m%5D))"
```

**PASS:** three elements, one per node (`192.168.55.11/.12/.13`), each > 0.
Measured 2026-09-17 over 1h: 19.2 / 15.1 / 22.2.
**FAILS AS:** two elements instead of three — a node's UDP sender did not resume
after the pod restart. This is not hypothetical: nuc14-03 stopped shipping kmsg on
2026-08-04 and nobody noticed for **4 days**, which is why the
`talos_kernel_kmsg_lines` counter exists at all. A cluster-wide aggregate would
hide exactly this, so the gate is deliberately per-node.

### CONTENTS ASSERTION 4.5 — no NEW metric-drop class

CONTENTS ASSERTION: *the ES metric-rejection rate did not worsen* — compared to
the §2.4 baseline, **not** to zero.

```bash
P=/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query
kubectl get --raw "${P}?query=sum(increase(otelcol_cumulativetodelta_datapoints_dropped_total[1h]))"
```

**PASS:** within roughly ±25% of the §2.4 baseline (~2,624/h on 2026-09-17).
**FAILS AS:** a materially higher value — a new histogram family started being
rejected under 0.161.0. **Do not assert zero here**: this counter is already
non-zero because of the open findings `F-f8801413` / `F-b780647b` (§1.6), and a
`== 0` gate would fail every time for a pre-existing reason and train the operator
to ignore it.

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
flux reconcile kustomization edot-collector -n flux-system --with-source
kubectl rollout status deployment/edot-collector -n monitoring --timeout=180s
kubectl get pods -n monitoring -l app=edot-collector \
  -o jsonpath='{.items[0].spec.containers[0].image}'; echo
```

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
# delete the §3.1 silence by id: curl -s -X DELETE localhost:9093/api/v2/silences/<id>
```

## 6) Interference notes

- **`conflicts_with` is three entries and every one names a mechanism** — see the
  frontmatter. The two the window agent must not relax: `prometheus-crd-ownership`
  (an otel-operator helm upgrade, which rolls the daemon collectors that export
  into this collector) and `kube-prometheus-stack-91.4.0` (a Prometheus restart
  blinds every gate in §4 and would read as this plan regressing).
- **`otel-operator-0.21.0` is deliberately absent, and this is the interesting
  one.** That plan carried the canonical statement of the edot-vs-daemon
  interference, and it **executed in `nightly:2026-09-17`**, its file retired in
  commit `37f7c7a6`. So the collision it described is spent for that bump. Its
  reasoning is preserved verbatim in the frontmatter comment and in the bullet
  below, because the *mechanism* recurs on every future otel-operator upgrade —
  the next such plan must carry this conflict from the start.
- **RECIPROCAL EDIT OWED — the window agent must not assume symmetry.**
  `maintenance-plan.py --validate` checks that conflict refs *resolve*, not that
  they are *reciprocal*, so a one-sided guard passes validation while protecting
  only one direction. Neither `prometheus-crd-ownership` nor
  `kube-prometheus-stack-91.4.0` lists `edot-collector-0.161.0` in its
  `conflicts_with`, because this plan did not exist when they were written.
  **Add it to both before any of the three is scheduled.**
- **Pre-existing repo defect, surfaced by this plan's validation (not caused by
  it):** `cilium-1.20.2`, `kube-prometheus-stack-91.4.0` and
  `prometheus-crd-ownership` all still name the now-retired
  `otel-operator-0.21.0` in `conflicts_with`, so
  `maintenance-plan.py --validate` currently reports three dead refs. The
  close-out commit retired the plan file without sweeping the refs that pointed
  at it. Those three need the same dated-comment resolution applied here.
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
