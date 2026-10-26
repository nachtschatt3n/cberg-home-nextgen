---
plan_id: edot-collector-0.163.2
component: edot-collector
pr: 324                           # Renovate "update otel/opentelemetry-collector-contrib
                                  # ( 0.161.0 → 0.163.2 )", branch
                                  # renovate/otel-opentelemetry-collector-contrib-0.x.
                                  # OPEN, MERGEABLE/CLEAN, all 4 checks SUCCESS incl.
                                  # Flate Render Gate (re-checked 2026-10-23). Diff = exactly one
                                  # line in deployment.yaml (the image tag).
kind: image
current: "0.161.0"                # MEASURED 2026-10-19: deployment/edot-collector image
                                  # otel/opentelemetry-collector-contrib:0.161.0, pod
                                  # edot-collector-7dbd97b8d8-vzdzj imageID
                                  # ...@sha256:fd328de2...5ac1 (= Docker Hub manifest-list
                                  # digest for tag 0.161.0, re-measured today).
target: "0.163.2"                 # Multi-arch MANIFEST LIST on Docker Hub, 7 linux
                                  # platforms incl. amd64 (also 200 on ghcr), digest
                                  # sha256:7f22d2a6748110ffb6a59bc0df448bccbf501cdb667d610ede4c61d3863d5849
                                  # (measured 2026-10-23). PR #324 was RE-TARGETED by Renovate
                                  # 0.163.1 -> 0.163.2 on 2026-10-21/22. 0.163.2 is a release-
                                  # PIPELINE patch (releases-repo v0.163.2, 2026-10-21: "updates
                                  # the binaries' Go version and CA bundle", fixes #1722); it
                                  # carries contrib/core v0.163.0 components, same as 0.163.0/
                                  # 0.163.1. Tag 0.163.0 itself is HTTP 404 on Docker Hub.
                                  # The binary reports "otelcol-contrib version 0.163.2".
update_type: minor                # 0.x line: the MINOR digit is the breaking axis
risk: medium                      # NOT from likelihood — the changelogs are clean for
                                  # every component this config instantiates (§1.2) and
                                  # the live config validates on the 0.163.2 binary
                                  # (§1.3). From blast radius + failure MODE: one replica,
                                  # the sole OTLP path into ES for every namespace plus
                                  # the Talos kmsg sink, and its characteristic failure is
                                  # SILENT (pod Ready, telemetry gone) — §4 gates contents.
est_duration_min: 50              # 12 pre-checks (tag gate, local + in-cluster validate,
                                  # baselines) + 3 merge + 5 reconcile/Recreate roll +
                                  # 3 heartbeat-kick commit + DaemonSet roll + 15 settle
                                  # (every [15m] window in §4 must lie after the roll) +
                                  # 12 verification. The §4.4 per-node heartbeat gate
                                  # runs INSIDE the settle (it no longer waits for the
                                  # hourly :45 heartbeat — §3 step 5 triggers one).
                                  # Fits a nightly slot (90 - STEP0_RESERVE 20 = 70m).
needs_reboot: false
touches:
  namespaces: [monitoring]
  resources:                      # every object below verified to EXIST live 2026-10-19
    - deployment/edot-collector               # image tag (via PR #324) — the change
    - daemonset/kmsg-heartbeat                # pod-template annotation only (§3 step 5):
                                              # restarts the 3 heartbeat pods so each node
                                              # writes one kmsg line on demand; makes §4.4
                                              # deterministic. No behaviour change.
    - configmap/edot-collector-config         # READ + validated on 0.163.2 (§1.3, §2.3);
                                              # NOT edited
    - pvc/edot-collector-queue                # RWO longhorn-static, Bound, 10Gi; bbolt
                                              # sending queue; detach/attach on the
                                              # Recreate roll; the forward-only surface (§5.2)
    - service/edot-collector                  # ClusterIP 4317/4318/8888/8889 — every OTLP
                                              # producer's target
    - service/edot-collector-talos-kmsg       # LoadBalancer 192.168.55.18 UDP 5171
    - servicemonitor/edot-collector           # the scrape feeding §4 (up==1 on both
                                              # endpoints, measured)
    - httproute/edot-collector                # OTLP/HTTP on envoy-internal; backend briefly
                                              # down during the roll
    - kustomization/edot-collector            # Flux Kustomization, namespace monitoring
  shared: [monitoring]            # the single OTLP choke point for every namespace's
                                  # logs/metrics into Elasticsearch + the Talos kmsg sink
                                  # (and with it TalosKernelLogsMissingFromNode). A roll
                                  # blinds cluster-wide ingestion for its duration.
                                  # NOT gateway/envoy: routing unchanged.
depends_on: []
conflicts_with:                   # HARD slot exclusions — the only field
  - grafana-14.1.0   # reciprocal, added 2026-10-26 (sweep a1721200 plan review)
  # 2026-10-25: pruned dead refs cilium-1.20.4 (executed/retired)
                                  # window-scheduler.py honours (symmetric either way).
                                  # Re-pruned 2026-10-23: refs to plans that no longer exist
                                  # (otel-operator-0.24.4, kube-prometheus-stack-92.2.0,
                                  # coredns-1.48.2, spegel-0.8.0) and to the superseded
                                  # edot-collector-0.162.0 / home-assistant-2026.10.1 dropped.
  - otel-operator-0.25.1          # its daemon collectors EXPORT into
                                  # edot-collector.monitoring.svc:4317 and its §4.4 proves
                                  # itself via docs landing in ES THROUGH this collector;
                                  # a same-night pair makes every ingestion gap
                                  # unattributable. OPERATOR RULE 2026-10-23: SEPARATE slot,
                                  # otel-operator FIRST, this plan in a later slot.
  - coredns-1.48.1                # all three ES exporters resolve
                                  # elasticsearch-es-http.monitoring.svc through CoreDNS;
                                  # a DNS blip during §4 shows up as non-success outcomes
                                  # in §4.2(b), which carries revert authority.
  - talos-linux-1.14.2            # node drains evict this single replica (RWO queue PVC
  - talos-linux-1.14.4            # re-attaches elsewhere) and silence each node's kmsg feed
                                  # for its reboot — §4.1/§4.3/§4.4 would read the roll as
                                  # this plan's regression.
  - longhorn-1.13.0               # the bbolt queue is an RWO Longhorn volume; a Longhorn
                                  # engine/manager roll during the Recreate detach/attach
                                  # is exactly the Multi-Attach / attach-stall surface.
  - home-assistant-2026.10.2      # pod logs in ES drop while the collector rolls; its
                                  # gates read the same log path.
exclusive: false
security_ref: null                # no open security finding on the 0.161.0 image
                                  # (`finding list --all --grep collector-contrib`,
                                  # 2026-10-19: every security row resolved).
capability_change: false          # image tag only + a no-op pod-template annotation on the
                                  # heartbeat DaemonSet. No config change, no new receiver/
                                  # exporter/processor/route/permission. The upstream
                                  # behaviour changes that reach this config are bug fixes,
                                  # an extra startup log line, and a scope.name field on
                                  # kmsg docs (§1.2) — same observable contract.
rollback_class: git-revert        # one-commit revert of the PR squash commit. The one
                                  # forward-only surface — the bbolt queue written by the
                                  # newer binary — has an explicit PROCEDURE in §5.2.
finding_refs: [F-cb9182ca]        # version row "edot-collector: image
                                  # otel/opentelemetry-collector-contrib 0.161.0 → 0.163.2
                                  # (minor)", open/unchanged 2026-10-19
                                  # (`finding list --all --grep 0.163`). F-76387378 (ES
                                  # dropped metric points, monitor) is NOT answered here.
review: ready-for-go@2026-10-23
status: vetted
window: "nightly:2026-11-10"       # after otel-operator-0.25.1 (sat-attended:2026-11-07), separate slot
premises:
  # Re-checked at EXECUTION time. All four RUN on 2026-10-19 while writing this plan.
  - id: image-is-still-0.161.0
    why: >-
      `current:` claims 0.161.0. If Step 0 auto-merged PR #324 (it merged the 0.162.0
      PR #264 on 2026-10-08) or anyone else moved the collector, §3 is moot and the
      §5.1 rollback digest is wrong. Prints the actual image when it fails. If it
      fails because the image already reads 0.163.2, do NOT re-run §3 — run §4 as a
      post-hoc verification (see §6).
    run: kubectl get deploy -n monitoring edot-collector -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "otel/opentelemetry-collector-contrib:0.161.0"
  - id: ingestion-is-healthy-before-we-touch-anything
    why: >-
      Never roll the sole telemetry path while it is ALREADY degraded — a pre-existing
      stall would be misattributed to this bump. Asserts the logs exporter persisted
      more than 1000 records over the last 15m (measured 20,089 on 2026-10-19; 7d
      minimum of the same expression 15,510). The awk `$1+0` coercion makes an empty
      result fail closed (INGEST_LOW) — negative control demonstrated by the
      predecessor plan against a nonexistent metric. Written with `<` because the
      premise sandbox refuses the greater-than character.
    run: kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=sum(increase(otelcol_exporter_sent_log_records_total[15m]))' | sed -E 's/.*"value":\[[0-9.]+,"([0-9]+).*/\1/' | awk '{print ($1+0<1000)?"INGEST_LOW":"INGEST_OK"}'
    expect_exact: "INGEST_OK"
  - id: config-is-the-one-validated-on-0.163.2
    why: >-
      §1.3's evidence (the live otel.yml validates on the 0.163.2 binary) holds only
      for the config committed in 42979120. If the configmap moved, that evidence is
      stale; §2.3 still runs either way. Prints the newer short sha if it moved.
    run: git log -1 --format=%h -- kubernetes/apps/monitoring/edot-collector/app/configmap.yaml
    expect_exact: "42979120"
  - id: kmsg-heartbeat-daemonset-ready-on-all-nodes
    why: >-
      §4.4's per-node gate depends on one heartbeat pod per node writing a kmsg
      line when it starts. With fewer than 3 ready the gate would read a missing
      heartbeat POD as a stalled kmsg SENDER. Measured 3 on 2026-10-19.
    run: kubectl get ds -n monitoring kmsg-heartbeat -o jsonpath='{.status.numberReady}'
    expect_exact: "3"
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/monitoring.md                          # "ES Rejected Documents" — §4.2 uses
                                                     # the dotted outcome metric
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/longhorn-rwo-multi-attach.md           # why strategy Recreate is load-bearing
  - docs/troubleshooting/node-reboot-observability.md  # kmsg-sender stall + the url-toggle
                                                     # recovery recipe used in §5.3
generated: "2026-10-19"
---

# edot-collector: image 0.161.0 → 0.163.2 (0.x release-line move, two minors)

## 1) Summary & why held

### 1.1 Why it was held

`runbooks/coverage.py` (sweep 70815a65, rule 4d0 coverage group) put this in the
PLAN lane on its component-agnostic rule: *"0.x release-line move (0.161 ->
0.163) — at major 0 the minor IS the breaking axis; needs an assessed window
plan"*. No deny rule, no security driver (`security_evidence: none`).

The change is one line, delivered by Renovate PR **#324**
(`image: otel/opentelemetry-collector-contrib:0.161.0` → `:0.163.2`). PR checks
are green, Flate Render Gate included. **Re-target 2026-10-23:** the plan was
written for 0.163.1; Renovate moved the same PR to 0.163.2 (digest, release notes,
local validate and manifest-list gate all re-run below). The 0.163.1 evidence is
kept only where it still describes the same components.

**History you need.** The 0.162.0 bump (PR #264) was MERGED by the nightly
Step 0 on 2026-10-08 at 01:34Z and auto-reverted at 03:49 CEST (`0b958c7d`) as
**collateral**. `window_runs` for nightly 2026-10-08 says: *"11 PRs merged then
ALL auto-reverted by health gate (culprit #238 pgvector 0.8.7: immutable
init-Job template ...; 10 collateral)"*. The `component_autonomy` row for this
image says the same: *"batch auto-reverted ... culprit PR #238 pgvector"*. So
there is **no evidence that 0.162.0 itself misbehaved**. There is no evidence
that it behaved either: Prometheus retention starts 2026-10-12, so that ~15-min
run cannot be measured now. The revert still counts against the image's earned
autonomy, which is one more reason this goes through a plan.

### 1.2 Upstream evidence — assessed against OUR config

Sources were read directly (authoring rule 8):
- contrib release `v1.2.0/v0.163.0` (2026-10-14T06:53Z);
- core `v1.69.0/v0.163.0` (2026-10-14T02:03Z);
- releases repo `v0.163.0`, `v0.163.1` (2026-10-16) and `v0.163.2` (2026-10-21).
  Their bodies are only a component-update commit plus pipeline fixes. v0.163.2
  reads: "This release updates the binaries' Go version and CA bundle. It fixes
  #1722" (commits: prepare release, ensure latest Go + CA bundles, golang:1.27-alpine
  digest bump, github-actions deps). No component change: 0.163.2 = 0.163.0 components.
  Residual risk is a Go-toolchain/CA-bundle change: covered by the live-traffic
  gates in §4 (ES exporters over TLS to the in-cluster Elasticsearch).
- For 0.162.0 this plan relies on edot-collector-0.162.0 §1.2. That assessment
  was against the same config (unchanged since `42979120`). §1.3 re-validates the
  config on a binary that contains both minors.

The components `otel.yml` instantiates (read from the LIVE configmap on
2026-10-19, identical to git apart from Flux's `$$` escaping):
- receivers: `otlp`; `udp_log/talos-kernel` (stanza `json_parser`/`move`/`add`);
- processors: `memory_limiter`, three `filter` processors, one `transform`
  (OTTL `delete_key`, `IsMap`), `cumulative_to_delta`, `batch`;
- exporters: three `elasticsearch` exporters (otel mapping mode, static
  `*_index`, `sending_queue` on `file_storage/queue` with `block_on_overflow:
  true`), `prometheus/hwerrors`;
- connector and extensions: the `count/hwerrors` connector, plus the
  `file_storage/queue` and `health_check` extensions;
- the `service::telemetry` Prometheus reader with its three `without_*: false`
  pins.

The collector runs with no `--feature-gates` (args: `--config=/config/otel.yml`
only).

**0.163.0 contrib "Breaking changes".** All ten entries name components we do
not run:
- opampsupervisor, `connector/failover`, `exporter/signalfx`;
- google_cloud_logentry_encoding, `processor/redaction`, `receiver/postgresql`;
- `receiver/prometheus_simple`, `receiver/sql_server`;
- two API-only `pkg/ottl` Go struct/module moves.

**0.163.0 core.** It has no breaking section.

**Changes that DO reach components we run, each checked:**

- **`pkg/stanza`: default scope name and version for entries without one
  (`pkg.stanza.addDefaultScopeName`, beta, so ON by default; new in 0.163.0, not
  present in 0.162.0's `pkg/stanza/metadata.yaml`).** For `udp_log`,
  `adapter/receiver.go` passes the receiver's `metadata.ScopeName`
  (`.../receiver/udplogreceiver`) and the build version. Talos kmsg docs today
  carry `scope: {}`; measured on 2026-10-19, zero talos-kernel docs had
  `scope.name` over 7d. Could that scope name re-route them (the ES exporter has
  `/receiver/(\w+receiver)` scope routing)? No. `newDocumentRouter` builds a
  `staticDocumentRouter` whenever `logs_index` is set (ours is
  `logs-generic-default`), and `staticDocumentRouter.route` ignores the scope.
  The live data agrees: in the last hour `logs-generic-default` already held
  1,637 docs with `scope.name = .../receiver/k8sobjectsreceiver` routed through
  the same exporter. **Effect: kmsg docs gain a `scope.name`/`scope.version`
  field. Nothing else changes.** §4.3 uses this as positive proof that the new
  binary's stanza path is live.
- **`exporter/elasticsearch`: version detection plus "Connected to
  Elasticsearch" startup log (#51541), and native exponential histograms on ES
  >= 9.3.0 (#51429).** `version.go` (new in 0.163.0; 404 at `v0.162.0`) does a
  `GET /` per endpoint in `Start()`. It has a 5s timeout and is **warn-only** on
  failure. `resolveDefaultHistogramMapping` picks Exponential only if the version
  is >= 9.3.0. Our ES is **8.19.20** (measured), so we stay on TDigest, the
  existing mapping. Effect: one extra GET plus an info line per exporter at
  start. §4.0 gates on that line (it proves ES reachability and auth from the new
  binary at startup).
- **core `pkg/exporterhelper`: "Fix sending queue deadlocks when blocked offers
  are cancelled with block_on_overflow enabled" (#15700).** All three of our ES
  queues set `block_on_overflow: true`, so this fixes a hang we are exposed to.
  The same release also brings oversized-span/profile split drops in line with
  0.162.0's logs fix.
- **`pkg/ottl`: the new `pkg.ottl.functions.enableExperimental` gate (#51564),
  and slice-argument literals rejected at parse time (#51833).** Our statements
  use only `IsString`, `IsMatch`, `IsMap`, `delete_key`, `name`, `type`, `flags`.
  The live config **parses on 0.163.2** (§1.3). I also proved that OTTL parse
  errors ARE fatal at validate: a misspelled `IsMapp` exits 1 naming the
  statement. So a function newly gated behind "experimental" could not pass
  §2.3 silently.
- **`processor/cumulative_to_delta`: ExponentialBuckets reset fix (#51303).** It
  touches exponential histograms only. Our include list is Prometheus-sourced
  explicit histograms, so this is not ours in practice. §4.1's ±20% metric band
  could not be tripped by it.

### 1.3 The live config validates on the 0.163.2 binary — and what that gate cannot see

**Re-run 2026-10-23 on 0.163.2** (live config still commit `42979120`): `validate` exit 0 with empty output; `num_consumers: notanint` exit 1 (`cannot unmarshal`); `IsMapp(` exit 1 (`undefined function "IsMapp"`). The table below was first measured 2026-10-19 on 0.163.1. Run on the Mac with the official
`otelcol-contrib_0.163.2_darwin_arm64` release binary (it reports
`otelcol-contrib version 0.163.2`), against the LIVE `otel.yml` pulled from
`configmap/edot-collector-config`:

| input | 0.163.2 exit | meaning |
|---|---|---|
| live `otel.yml` | **0**, no output | accepted |
| `num_consumers: notanint` in `elasticsearch/logs` | 1 (`cannot unmarshal`) | type errors caught |
| `IsMap(` → `IsMapp(` in the transform statement | 1 (`unable to parse OTTL statement`) | OTTL errors caught |
| `bogus_key` under `service::telemetry…prometheus` | **1** (`has invalid keys: bogus_key`) | telemetry-reader unknown keys ARE caught |
| `totally_unknown_field` in an ES exporter | **0** | **ES exporter unknown keys NOT caught** |

**Correction to the predecessor.** edot-collector-0.162.0 §1.3 recorded that the
telemetry-reader `bogus_key` case exits 0 "on 0.162.0". Re-measured today on the
0.162.0 darwin binary, it exits **1**. So the `without_type_suffix`-rename
concern is now covered by `validate` too. The ES-exporter blind spot is real and
remains. A silently ignored ES key would show up only as a contents change, which
is why §4.1 and §4.2 gate on contents and treat an empty result as FAIL.

### 1.4 Why `risk: medium` despite a clean changelog

The reasons are blast radius and failure mode:
- **One replica**, and it is the only OTLP path into Elasticsearch for every
  namespace. Measured over 15m on 2026-10-19: 20,089 log records and 1,881,222
  metric points sent, 813,786 per-doc `success` outcomes.
- It is also the Talos kmsg sink on `192.168.55.18`. **A collector restart is the
  documented trigger for a per-node kmsg-sender stall**
  (docs/troubleshooting/node-reboot-observability.md).
- Its characteristic failure is silent: the pod is Ready, the health endpoint
  returns 200, and telemetry simply stops being counted.

### 1.5 Supersession verdict on edot-collector-0.162.0

**This plan supersedes edot-collector-0.162.0.** Its blocker no longer applies:
- **The stated blocker is resolved.** The 0.162.0 plan was blocked on 2026-10-05
  because Docker Hub/ghcr had no multi-arch `0.162.0` manifest list. Re-measured
  2026-10-19: `0.162.0` is now a manifest list (`sha256:39923a8e…74be6`, 7 linux
  platforms). The target here, `0.163.2`, is a manifest list too
  (`sha256:7f22d2a6…5849`). The `-386` picker defect it reported was fixed in
  `69d4eb6e`. §2.2 keeps the manifest-list gate anyway, so the condition is
  checked, not assumed.
- **The reviewer's other unblock conditions are carried here:**
  - a target-manifest-list check (§2.2);
  - a per-node kmsg heartbeat gate for .11/.12/.13 (§4.4, made deterministic by
    §3 step 5 rather than waiting up to 60 min for the hourly heartbeat).
- **There is no reason to stop at 0.162.0.** Renovate retargeted the same branch
  to 0.163.2 (PR #324). Running 0.162.0 first would mean two collector restarts,
  and so two sender-stall chances, for no gain.

Housekeeping owed (not done by this planner, which writes only this file):
- Set `edot-collector-0.162.0` to `status: superseded` (it is `blocked`). This
  plan no longer lists it in `conflicts_with`.
- Plans that still name dead edot/otel ids (cilium-1.20.4 and talos-linux-1.14.4
  name `otel-operator-0.25.0`; those should read `otel-operator-0.25.1` and
  `edot-collector-0.163.2`) are owed a reciprocal fix by their owners.

## 2) Pre-checks

Run them in order. Any failure stops the plan; do not go on to §3.

```bash
cd /Users/mu/code/cberg-home-nextgen
# 2.1 — premises (re-run mechanically)
.venv/bin/python3 runbooks/plan-premises.py edot-collector-0.163.2
# PASS: all four premises PASS.
# If ONLY image-is-still-0.161.0 fails and prints ...:0.163.2 -> Step 0 already
# merged #324: skip §3 steps 2-4, do §3 step 5 + all of §4 as post-hoc verification.

# 2.2 — HARD GATE: PR #324 still targets 0.163.2 and is mergeable, AND the
# multi-arch tag 0.163.2 exists as a manifest list containing linux/amd64.
gh pr view 324 --json state,mergeable,title -q '.state+" "+.mergeable+" "+.title'
# PASS: "OPEN MERGEABLE feat(container): update otel/opentelemetry-collector-contrib ( 0.161.0 → 0.163.2 )"
# FAILS AS: MERGED/CLOSED, CONFLICTING, or a different target in the title -> STOP
#       (retarget = re-plan; README "When the held target MOVES").
T=$(curl -s "https://auth.docker.io/token?service=registry.docker.io&scope=repository:otel/opentelemetry-collector-contrib:pull" | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
curl -s -D /private/tmp/claude-501/edot-0163-hdr.txt -o /private/tmp/claude-501/edot-0163-manifest.json \
  -H "Authorization: Bearer $T" \
  -H "Accept: application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.list.v2+json" \
  https://registry-1.docker.io/v2/otel/opentelemetry-collector-contrib/manifests/0.163.2
python3 - <<'EOF'
import json,re
h=open('/private/tmp/claude-501/edot-0163-hdr.txt').read()
st=re.search(r'^HTTP/\S+ (\d+)',h,re.M).group(1)
dg=(re.search(r'(?im)^docker-content-digest:\s*(\S+)',h) or [None,None])[1]
if st!='200': print('TAG_MISSING http',st,'-> BLOCKED'); raise SystemExit
m=json.load(open('/private/tmp/claude-501/edot-0163-manifest.json'))
plats=[(x['platform']['os'],x['platform']['architecture']) for x in m.get('manifests',[])]
ok=('linux','amd64') in plats
print('TAG_OK' if ok else 'NO_AMD64', dg, plats)
if ok: open('/private/tmp/claude-501/edot-0163-target-digest','w').write(dg)
EOF
cat /private/tmp/claude-501/edot-0163-target-digest; echo
# PASS: `TAG_OK sha256:7f22d2a6748110ffb6a59bc0df448bccbf501cdb667d610ede4c61d3863d5849 [...('linux','amd64')...]`
#       (exactly this digest measured 2026-10-23; a DIFFERENT digest = upstream re-pushed
#       the tag -> STOP and re-read the release before proceeding).
# CAN FAIL — demonstrated 2026-10-19 with the same request + parse on tag 0.163.0:
#       `TAG_MISSING http 404 -> BLOCKED`. Also NO_AMD64 / empty digest file -> STOP.

# 2.3 — GATE: validate the LIVE config against the NEW binary, two ways.
# (a) locally, upstream release binary (no cluster object created):
mkdir -p /private/tmp/claude-501/otel1632 && cd /private/tmp/claude-501/otel1632
gh release download v0.163.2 -R open-telemetry/opentelemetry-collector-releases \
  -p 'otelcol-contrib_0.163.2_darwin_arm64.tar.gz' --clobber
tar xzf otelcol-contrib_0.163.2_darwin_arm64.tar.gz otelcol-contrib
./otelcol-contrib --version                        # MUST print: otelcol-contrib version 0.163.2
kubectl get cm -n monitoring edot-collector-config -o jsonpath='{.data.otel\.yml}' > live-otel.yml
ES_PASSWORD=dummy ./otelcol-contrib validate --config=live-otel.yml > pos.out 2>&1; echo "validate exit=$?"
cat pos.out
# NEGATIVE CONTROL — must exit NON-zero, proving this gate can fail:
python3 -c "t=open('live-otel.yml').read();open('neg.yml','w').write(t.replace('num_consumers: 4','num_consumers: notanint',1))"
ES_PASSWORD=dummy ./otelcol-contrib validate --config=neg.yml > neg.out 2>&1; echo "negative-control exit=$?"
head -1 neg.out
cd /Users/mu/code/cberg-home-nextgen
# PASS: `validate exit=0` with EMPTY pos.out AND `negative-control exit=1` with neg.out
#       starting "Error: failed to get config: cannot unmarshal" (both measured exactly
#       so on 2026-10-19).
# FAILS AS: non-zero exit naming a rejected key/type/OTTL statement -> BLOCKED (the fix is
#       a config change = a different plan). Remember §1.3: blind to unknown ES-exporter keys.
#
# (b) in-cluster with the linux image that will actually run (only after 2.2 passed).
# EVERY command carries `-n monitoring` (the kube context's namespace is `default`,
# where the configmap does not exist). Detached run + read the container's own
# exitCode — NOT `-i --rm` (the merge-patch --overrides drops stdin; the attach then
# reports kubectl's status, not the container's). monitoring is PSA `privileged`.
edot_validate() {  # $1 = pod name, $2 = --config path, $3 = mount cm? (yes|no)
  local OV IMG=otel/opentelemetry-collector-contrib:0.163.2
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
edot_validate edot-validate-01632     /config/otel.yml      yes
edot_validate edot-validate-01632-neg /nonexistent/otel.yml no
grep -ic 'nonexistent/otel.yml' /private/tmp/claude-501/edot-validate-01632-neg.out
# PASS (positive): `phase=Succeeded exitCode=0` and the log matches nothing for
#       (case-insensitive) error|invalid|cannot unmarshal.
# PASS (negative control): `phase=Failed`, NON-zero exitCode AND the grep prints >= 1
#       (output names /nonexistent/otel.yml). A non-zero exit WITHOUT that path means the
#       pod failed for another reason (pull, admission, arch) — investigate, not a pass.
# FAILS AS: positive pod Failed / error text -> BLOCKED. NOT_TERMINAL after 180s = pull or
#       volume problem -> STOP, describe, delete the pod by hand. "exec format error" =
#       wrong-architecture image -> STOP.

# 2.4 — BASELINES for §4, each over the SAME window its gate uses.
# Measured 2026-10-19 for reference (yours will differ):
#   sent log records [15m]          20,089   (7d min 15,510)
#   sent metric points [15m]     1,881,222   (24h range 1,873,362 - 1,892,640, ~1% spread)
#   docs.processed success [15m]   813,786   non-success [15m]: EMPTY
P=/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query
kubectl get --raw "${P}?query=sum(increase(otelcol_exporter_sent_log_records_total[15m]))"; echo
kubectl get --raw "${P}?query=sum(increase(otelcol_exporter_sent_metric_points_total[15m]))"; echo
kubectl get --raw "${P}?query=sum%20by%20(outcome)%20(increase(%7B__name__%3D%22otelcol.elasticsearch.docs.processed_total%22%7D%5B15m%5D))"; echo
# Record the metric-points value as MP_BASE for §4.1.

# 2.5 — pre-state is clean
kubectl get pods -n monitoring -l app=edot-collector -o wide
kubectl get pvc -n monitoring edot-collector-queue
kubectl get ds -n monitoring kmsg-heartbeat
flux get kustomizations -n monitoring | awk 'NR==1 || $4 != "True"'
# PASS: collector 1/1 Running, PVC Bound, DaemonSet 3/3, no kustomization off True.
```

## 3) Steps (GitOps)

**1. Silence expected rollout noise and mark the update active.** Every
alertname below exists in
`kubernetes/apps/monitoring/kube-prometheus-stack/app/otel-collector-alerts.yaml`
(grepped 2026-10-19). These are deliberately NOT silenced:
- the three `Es*ExporterSeriesMissing` absent() guards;
- `TalosKmsgPipelineDown`;
- `TalosKernelLogsMissingFromNode` (3h window, `for: 15m`).

A real disappearance, or a stalled kmsg sender, must still page after the
window.

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 >/dev/null 2>&1 & PF=$!
sleep 3
NOW=$(python3 -c "from datetime import *;print(datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
END=$(python3 -c "from datetime import *;print((datetime.now(timezone.utc)+timedelta(hours=3)).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
curl -s -X POST localhost:9093/api/v2/silences -H 'Content-Type: application/json' -d '{
  "matchers":[{"name":"namespace","value":"monitoring","isRegex":false,"isEqual":true},
              {"name":"alertname","value":"EdotCollectorDown|OtelCollectorExportFailed|OtelCollectorRecordsRefused|OtelCollectorQueueFull|EdotCollectorESAuthError|EsMetricsIngestionStalled|EsLogIngestionStalled|EsExportQueueStuckFull","isRegex":true,"isEqual":true}],
  "startsAt":"'"$NOW"'","endsAt":"'"$END"'","createdBy":"maintenance-window-agent",
  "comment":"edot-collector 0.161.0->0.163.2 - expected rollout noise. auto-expires 3h"}' \
  | tee /private/tmp/claude-501/edot-01632-silence.json; echo   # prints {"silenceID":"..."}; empty = NOT silenced
kill $PF 2>/dev/null
runbooks/update-marker.sh add edot-collector monitoring 3 "0.161.0->0.163.2 bump"
```

**2. Merge the Renovate PR** (squash, the repo's convention for Renovate PRs).

```bash
GEN_BEFORE=$(kubectl get deployment edot-collector -n monitoring -o jsonpath='{.metadata.generation}')
gh pr merge 324 --squash --delete-branch
git fetch origin main && git merge --ff-only origin/main
BUMP_SHA=$(git log -1 --format=%H -- kubernetes/apps/monitoring/edot-collector/app/deployment.yaml)
git show --stat "$BUMP_SHA" | head -8      # exactly one file: .../edot-collector/app/deployment.yaml
grep -n 'image: otel/opentelemetry-collector-contrib' kubernetes/apps/monitoring/edot-collector/app/deployment.yaml
echo "$BUMP_SHA" > /private/tmp/claude-501/edot-01632-bump-sha
# PASS: the grep prints `image: otel/opentelemetry-collector-contrib:0.163.2`.
```

**3. Reconcile and watch the Recreate roll.** The Flux Kustomization lives in
namespace **`monitoring`** (`kustomization/edot-collector`, Ready, measured
2026-10-19). With `-n flux-system` the command errors, and `rollout status`
then green-lights the OLD generation, a false success. `strategy: Recreate` is
load-bearing (RWO Longhorn PVC at `replicas: 1`). Do not hand-delete pods
mid-roll.

```bash
flux reconcile kustomization edot-collector -n monitoring --with-source
kubectl get deployment edot-collector -n monitoring -o jsonpath='{.spec.template.spec.containers[0].image}'; echo
GEN_AFTER=$(kubectl get deployment edot-collector -n monitoring -o jsonpath='{.metadata.generation}')
echo "generation $GEN_BEFORE -> $GEN_AFTER"
kubectl rollout status deployment/edot-collector -n monitoring --timeout=180s
kubectl get pods -n monitoring -l app=edot-collector -o wide
kubectl get pods -n monitoring -l app=edot-collector \
  -o jsonpath='{.items[0].status.conditions[?(@.type=="Ready")].lastTransitionTime}' \
  > /private/tmp/claude-501/edot-01632-ready-ts
cat /private/tmp/claude-501/edot-01632-ready-ts; echo   # MUST be non-empty and AFTER the merge
```

**HARD GATE:** the printed image reads `:0.163.2` AND `GEN_AFTER > GEN_BEFORE`
AND exactly one pod is listed, `1/1 Running`. If not, nothing rolled. Do not
continue into §4, whose gates would all pass on the old binary.

**4. Read the startup log NOW** (§4.0's ES-connect gate). The collector's
startup lines are rotated out within days; today's 0.161.0 pod no longer has
its own.

```bash
kubectl logs -n monitoring deploy/edot-collector | head -400 > /private/tmp/claude-501/edot-01632-startup.log
grep -ci "Connected to Elasticsearch" /private/tmp/claude-501/edot-01632-startup.log
grep -iE "failed to fetch Elasticsearch info|version detection|invalid configuration|panic|exec format" \
  /private/tmp/claude-501/edot-01632-startup.log || echo "no startup errors"
```

**5. Kick the kmsg heartbeat (second commit, ONLY after step 3's hard gate).**
`kmsg-heartbeat` writes one `cberg-kmsg-heartbeat node=<node>` line into each
node's kernel ring buffer **when its pod starts**, and then hourly. All three
currently fire at about :45 UTC (measured 01:44:58–01:45:10Z on 2026-10-19). A
post-roll heartbeat could otherwise be up to 60 min away, which is longer than
the nightly budget. Restarting the pods via a pod-template annotation makes
every node emit a line within about a minute, while the new collector is
already listening. The DaemonSet rolls `maxUnavailable: 1, maxSurge: 0`
(measured).

The edit was DRY-TESTED 2026-10-19 with macOS BSD sed on a scratch copy of the
real file (exit 0). The result was server-side dry-run-applied (`kubectl apply
--dry-run=server`, accepted, rendered annotation shown). The anchor is the
8-space-indented template label, which is unique: the top-level label at line 42
has 4 spaces.

```bash
REV="$(date -u +%Y-%m-%dT%H%M)"
sed -i '' -e '/^        app.kubernetes.io\/part-of: edot-collector$/a\
      annotations:\
        cberg.dev/kmsg-heartbeat-kick: "'"$REV"'"
' kubernetes/apps/monitoring/edot-collector/app/kmsg-heartbeat-daemonset.yaml
git diff kubernetes/apps/monitoring/edot-collector/app/kmsg-heartbeat-daemonset.yaml
```

The dry-test output (`diff original scratch`, REV=2026-10-19.1) must show
exactly this ONE hunk:

```
51a52,53
>       annotations:
>         cberg.dev/kmsg-heartbeat-kick: "2026-10-19.1"
```

If the hunk is missing, the anchor did not match: STOP and edit by hand. If
there are two hunks, someone already added a template `annotations:` key: undo
with `git checkout -- <file>`, then add only the annotation line under the
existing key.

```bash
git fetch origin main && git merge --ff-only origin/main
MSG=/private/tmp/claude-501/msg-edot-01632-kick-$(date +%s).txt
printf '%s\n' "chore(monitoring): kick kmsg-heartbeat after edot-collector 0.163.2 roll (plan edot-collector-0.163.2)" > "$MSG"
git commit --only kubernetes/apps/monitoring/edot-collector/app/kmsg-heartbeat-daemonset.yaml -F "$MSG"
git show --stat HEAD       # exactly one file: kmsg-heartbeat-daemonset.yaml
git log -1 --format=%s     # MUST be your subject; amend before pushing if not
git push origin main
flux reconcile kustomization edot-collector -n monitoring --with-source
kubectl rollout status ds/kmsg-heartbeat -n monitoring --timeout=180s
kubectl get pods -n monitoring -l app.kubernetes.io/name=kmsg-heartbeat -o wide
# PASS: 3 pods, all with a fresh AGE (seconds/minutes), one per node.
```

**6. Wait 15 minutes** after the Ready timestamp from step 3, so every `[15m]`
window in §4 lies entirely after the new pod's start. A straddling window passes
on pre-roll data.

## 4) Verification

### 4.0 Floor + the new binary is really serving (shape → contents)

CONTROL: metric target_info — `count(target_info{job="edot-collector","service.version"="0.163.2"})` must be 1

```bash
kubectl get deployment edot-collector -n monitoring -o jsonpath='{.status.readyReplicas}'; echo
TARGET_DIGEST=$(cat /private/tmp/claude-501/edot-0163-target-digest)
test -n "$TARGET_DIGEST" || echo "NO_TARGET_DIGEST -> FAIL"
LIVE_ID=$(kubectl get pods -n monitoring -l app=edot-collector -o jsonpath='{.items[0].status.containerStatuses[0].imageID}')
echo "live: $LIVE_ID"
case "$LIVE_ID" in *"$TARGET_DIGEST") echo "DIGEST_OK" ;; *) echo "DIGEST_MISMATCH" ;; esac
P=/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query
for v in 0.163.2 0.161.0; do
  Q='count(target_info{job="edot-collector","service.version"="'$v'"})'
  E=$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))" "$Q")
  echo -n "service.version=$v: "
  kubectl get --raw "${P}?query=${E}" | python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];print(r[0]['value'][1] if r else 'EMPTY')"
done
grep -ci "Connected to Elasticsearch" /private/tmp/claude-501/edot-01632-startup.log
```

**PASS (all gating):**
- `readyReplicas` is 1, and `DIGEST_OK`. `imageID` carries the MANIFEST-LIST
  digest; precedent: today's 0.161.0 pod shows `…@sha256:fd328de2…5ac1`, equal to
  the tag's list digest.
- `service.version=0.163.2: 1`. The `0.161.0` line may still read 1 inside
  Prometheus' 5-min staleness window; it must read `EMPTY` by T+15m.
- The "Connected to Elasticsearch" count is **>= 3**, one per ES exporter
  (logs/metrics/traces, one endpoint each).

**Both sides demonstrated 2026-10-19.**
- The identical target_info loop printed `0.161.0: 1` and `0.163.2: EMPTY`, so
  the version gate reads both states.
- The "Connected to Elasticsearch" message exists only in 0.163.0+ `version.go`
  (the file is 404 at `v0.162.0`). The same grep against today's 0.161.0 pod log
  prints `0`.

**FAILS AS:**
- `DIGEST_MISMATCH` means something other than the §2.2 list is running.
- The version reads EMPTY for 0.163.2: the scrape broke, or a different binary
  is running.
- A Connected count of 0, with `failed to fetch Elasticsearch info` in the
  startup log: the new binary cannot reach or authenticate to ES. Check
  `_cluster/health` (§4.3), then §5.
- Any `panic` or `invalid configuration` line is a FAIL.

### 4.1 Telemetry still FLOWS

CONTENTS ASSERTION: the exporters are still persisting log records and metric
points. This is measured by `increase(...[15m])` read at T+15m and compared to
the §2.4 baselines.

CONTROL: metric otelcol_exporter_sent_log_records_total — `sum(increase([15m]))` must be >= 7,500 (floor)
CONTROL: metric otelcol_exporter_sent_metric_points_total — `sum(increase([15m]))` within ±20% of MP_BASE (band)

```bash
P=/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query
kubectl get --raw "${P}?query=sum(increase(otelcol_exporter_sent_log_records_total[15m]))"; echo
kubectl get --raw "${P}?query=sum(increase(otelcol_exporter_sent_metric_points_total[15m]))"; echo
```

**PASS:**
- Log records **>= 7,500**. This is a FLOOR at half the 7d minimum of this exact
  expression (15,510, measured 2026-10-19). Log volume has a natural spread of
  more than 20x, so no band would survive it. The predecessor's 10,000 floor was
  sized on a 20,860 minimum and now sits too close.
- Metric points **within ±20% of MP_BASE**. This series is flat (24h range
  1,873,362 – 1,892,640, about 1%), so a band is safe and catches a partial
  pipeline loss that a floor would miss.

**FAILS AS:**
- An **empty `result` array**: the metric stopped being exported under that
  name. That is the ES-key blind spot of §1.3, so empty is a FAIL, never a skip.
- A value under the floor or outside the band. The query form returns an empty
  result against a nonexistent metric (demonstrated by the predecessor). The
  floor can trip because 7,500 is below the healthy minimum but above a
  collapsed pipeline's ~0.

### 4.2 Elasticsearch is not silently REJECTING

CONTENTS ASSERTION: per-document outcome at the ES exporter is success-only,
read from the exporter's own outcome counter over `[15m]` after the roll.

CONTROL: metric otelcol.elasticsearch.docs.processed_total — (a) `outcome="success"` present and non-zero; (b) `outcome!~"success|retried"` empty or zero

Use the DOTTED name. The telemetry pins keep dots, and the underscored form reads
empty on both sides, so it can never fail (docs/sops/monitoring.md).

```bash
P=/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query
kubectl get --raw "${P}?query=sum%20by%20(outcome)%20(increase(%7B__name__%3D%22otelcol.elasticsearch.docs.processed_total%22%7D%5B15m%5D))"; echo
kubectl get --raw "${P}?query=sum%20by%20(outcome)%20(increase(%7B__name__%3D%22otelcol.elasticsearch.docs.processed_total%22%2Coutcome!~%22success%7Cretried%22%7D%5B15m%5D))"; echo
```

**PASS:** (a) returns `outcome="success"`, non-zero (baseline 813,786 per 15m),
AND (b) returns an empty result or zeros.

**Can fail:**
- The predecessor measured `max_over_time` of (b) over 7d returning
  `internal_server_error` and `timeout` outcomes in the tens of thousands, so the
  query reads real non-success outcomes when they exist.
- A missing `success` series in (a) is itself a FAIL (the rejection SLI is
  blind).

**Attribution:**
- `failed_client` points at the binary or config: revert.
- `timeout` or `internal_server_error` is ES-side: check `_cluster/health`
  (§4.3) before reverting. Do not revert a good binary for an ES hiccup.

### 4.3 Documents actually LANDED in Elasticsearch, kmsg through the new stanza path

CONTENTS ASSERTION: new documents exist in both data streams with `@timestamp`
after the new pod went Ready. Node `.11`'s kernel lines arrive through
`udp_log`, and those kmsg docs now carry the `scope.name` that only the
0.163.x stanza adapter writes. All of this is measured in ES itself; `_bulk`
returns 200 even when every item is rejected.

```bash
ES_PW=$(kubectl get secret -n monitoring elasticsearch-es-elastic-user -o jsonpath='{.data.elastic}' | base64 -d)
kubectl port-forward -n monitoring svc/elasticsearch-es-http 19211:9200 >/dev/null 2>&1 & PF=$!
sleep 4
READY_TS=$(cat /private/tmp/claude-501/edot-01632-ready-ts)
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

**PASS:**
- Both datastream counts are > 0.
- `KMSG_OK`: node .11 ships about 7 kernel lines/hour plus §3's heartbeat, and
  each heartbeat kick adds lines. 20 in 15m is the predecessor's measured floor.
  If .11 lands between 5 and 19, re-check once at T+25m before failing.
- `STANZA_NEW_OK`, and the cluster is `green`/`yellow` with 0 unassigned.

**Both sides of the scope gate demonstrated 2026-10-19:** zero talos-kernel docs
had `scope.name` over the last 7d (0.161.0 writes `scope: {}`). Zero after the
roll means the stanza path is NOT the new binary's, or kmsg is not arriving.
Cross-check with KMSG.

A KeyError on `aggregations` is a FAIL. `traces-generic-default` is not gated
because it has no trace producers, so a gate on it could only ever read empty.

### 4.4 Every node's kmsg SENDER survived the restart (per-node heartbeat gate)

CONTENTS ASSERTION: each of 192.168.55.11/.12/.13 delivered at least one
`cberg-kmsg-heartbeat` line into ES with `@timestamp` after the new collector
went Ready. That proves the node's Talos UDP sender is not stalled on the dead
pod IP. This is the condition the 0.162.0 reviewer required. It is measured in
ES, because the Prometheus `talos_kernel_kmsg_lines_total` series is sparse by
design (samples only when lines arrive, `send_timestamps: true`) and cannot
answer "after time T" per node.

```bash
ES_PW=$(kubectl get secret -n monitoring elasticsearch-es-elastic-user -o jsonpath='{.data.elastic}' | base64 -d)
kubectl port-forward -n monitoring svc/elasticsearch-es-http 19211:9200 >/dev/null 2>&1 & PF=$!
sleep 4
READY_TS=$(cat /private/tmp/claude-501/edot-01632-ready-ts)
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
`HB_FAIL missing=192.168.55.11,192.168.55.12,192.168.55.13`.

**Both sides demonstrated 2026-10-19** with this query shape:
- `gte now-3h` returned 3 heartbeats from each of .11, .12 and .13 (01:44:58Z,
  01:45:04Z and 01:45:10Z were the latest);
- a future lower bound returns no buckets.

If the control does not print HB_FAIL, the harness is broken (wrong index or a
mangled query) and an HB_OK means nothing, so treat it as a FAIL.

**Timing:** evaluate the gate at T+5m after §3 step 5's DaemonSet roll
completes. Re-evaluate once at T+15m (the §3 step 6 settle) before declaring a
node missing.

**FAILS AS:** `HB_FAIL missing=<ip>` at T+15m while the heartbeat pod on that
node is Running with a fresh start. That is the known **kmsg-sender stall**. It
is **NOT a revert trigger**: the stall is caused by the restart, not by the
version, and reverting restarts the collector again, which is the stall trigger
itself. Go to §5.3. A missing heartbeat POD instead (not Running) is a
DaemonSet problem: `kubectl describe pod -n monitoring <pod>`, and do not
toggle the node.

### 4.5 The exporter series EXIST — direct absent() evaluation

The `Es*ExporterSeriesMissing` and `TalosKmsgPipelineDown` rules carry
`for: 15m`, so at T+15m they are at most `pending`. An Alertmanager read here
could not fail. Evaluate their expressions directly instead.

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

**PASS:** the first three print `PRESENT`. The fourth, the positive control,
prints `ABSENT`. The predecessor demonstrated both sides on 2026-10-01 with these
exact expressions. If the control does not print `ABSENT`, the harness is
broken: FAIL.

**FAILS AS:**
- `ABSENT` on line 1 or 2: the exporter series is gone under that name. Go to
  §5.
- `ABSENT` on line 3 is a FAIL only if §4.3 also printed KMSG_FAIL. The
  in-memory exporter re-registers on the first line, and §3 step 5 guarantees
  lines.

## 5) Rollback

### 5.1 Primary — revert the bump commit

The heartbeat-kick commit is a harmless pod-template annotation. Leave it in
place; reverting it only restarts the heartbeat pods again.

```bash
BUMP_SHA=$(cat /private/tmp/claude-501/edot-01632-bump-sha)
git fetch origin main && git merge --ff-only origin/main
git revert --no-edit "$BUMP_SHA"
git show --stat HEAD       # exactly deployment.yaml; image back to :0.161.0
git log -1 --format=%s     # MUST read: Revert "feat(container): update otel/opentelemetry-collector-contrib ( 0.161.0 → 0.163.2 ) (#324)"
git push origin main
flux reconcile kustomization edot-collector -n monitoring --with-source   # namespace monitoring
kubectl rollout status deployment/edot-collector -n monitoring --timeout=180s
ROLLBACK_DIGEST=sha256:fd328de2552466ad78385e1b1289c3f2402b1c45f265b252aab1955b42845ac1
LIVE_ID=$(kubectl get pods -n monitoring -l app=edot-collector -o jsonpath='{.items[0].status.containerStatuses[0].imageID}')
case "$LIVE_ID" in *"$ROLLBACK_DIGEST") echo "ROLLBACK_DIGEST_OK" ;; *) echo "ROLLBACK_DIGEST_MISMATCH: $LIVE_ID" ;; esac
```

`$ROLLBACK_DIGEST` is 0.161.0's manifest-list digest. It was re-measured
2026-10-19, both from the running pod's `imageID` and from Docker Hub for tag
`0.161.0`. After the revert:
- Re-capture the Ready timestamp into `/private/tmp/claude-501/edot-01632-ready-ts`
  (same command as §3 step 3).
- Re-run §4.1–§4.4. The revert restarts the collector too, so §4.4 can catch a
  stall here as well. Re-run §3 step 5 first with a new REV to get fresh
  heartbeats.

A revert that restores the manifest but not the telemetry is not a rollback.
Renovate will re-open a PR for 0.163.2; that is expected. Add a deny rule only
if the failure was version-caused.

### 5.2 Contingency — the forward-only surface (bbolt queue)

`pvc/edot-collector-queue` holds the persistent sending queue, written by
whichever binary runs. Neither the 0.162 nor the 0.163 changelog touches the
persistent-queue storage format (the 0.163 queue change is a deadlock fix in the
blocking-offer path), so 0.161.0 is expected to read it back. **If the reverted
pod crashloops on the queue file**, this prints the store's name:

```bash
kubectl logs -n monitoring deploy/edot-collector --tail=50 | grep -iE "bolt|storage|queue|corrupt"
```

1. Run `kubectl scale deploy/edot-collector -n monitoring --replicas=0` to
   release the RWO volume. Flux scales it back on its next reconcile (interval
   30m), so do steps 2–3 promptly.
2. Wait until `kubectl get pods -n monitoring -l app=edot-collector` prints
   nothing, so the volume is detached. Then empty the queue from a throwaway pod
   with the Deployment's uid/gid/fsGroup 10001. The image is the busybox digest
   already pinned and cached for `kmsg-heartbeat`:

   ```bash
   kubectl run edot-queue-wipe -n monitoring --restart=Never \
     --image=busybox:1.38.0@sha256:dc2d74b28e4cf8984fa52af1f39bc7c3d9c73760b41a74d629f5d11b1ab28616 \
     --overrides='{"spec":{"securityContext":{"runAsUser":10001,"runAsGroup":10001,"fsGroup":10001},"containers":[{"name":"edot-queue-wipe","image":"busybox:1.38.0@sha256:dc2d74b28e4cf8984fa52af1f39bc7c3d9c73760b41a74d629f5d11b1ab28616","command":["sh","-c","ls -la /q; find /q -mindepth 1 -delete; echo REMAINING=$(find /q -mindepth 1 | wc -l)"],"volumeMounts":[{"name":"q","mountPath":"/q"}]}],"volumes":[{"name":"q","persistentVolumeClaim":{"claimName":"edot-collector-queue"}}]}}'
   kubectl wait pod/edot-queue-wipe -n monitoring --for=jsonpath='{.status.phase}'=Succeeded --timeout=180s
   kubectl logs -n monitoring edot-queue-wipe      # MUST end with REMAINING=0
   kubectl delete pod -n monitoring edot-queue-wipe
   ```

   A timeout with the pod in `ContainerCreating` means the volume is still
   attached elsewhere (Multi-Attach). Wait; do not force-detach.
3. Run `kubectl scale deploy/edot-collector -n monitoring --replicas=1`, then
   re-run §4.1–§4.4.

Cost: only the buffered in-flight telemetry (`create_directory: true` makes an
empty directory a clean start). **This is operator-visible; record it.** It is
the only step that loses data.

### 5.3 kmsg-sender stall on a node (from §4.4) — recovery, not rollback

This is the documented recipe in
`docs/troubleshooting/node-reboot-observability.md` §"kmsg-sender stall on
collector restart". It toggles the node's `KmsgLogConfig` url to port 5172 and
back to 5171, which re-opens the UDP socket without a reboot. A same-value
`apply-config` does NOT kick it (measured there).

```bash
NODE=<192.168.55.1x of the missing node>
talosctl -n "$NODE" patch mc --patch '{apiVersion: v1alpha1, kind: KmsgLogConfig, name: ship-kmsg-to-otel, url: udp://192.168.55.18:5172/}'
talosctl -n "$NODE" patch mc --patch '{apiVersion: v1alpha1, kind: KmsgLogConfig, name: ship-kmsg-to-otel, url: udp://192.168.55.18:5171/}'
```

This is a direct Talos machine-config mutation outside Flux, though it ends at
the same value. So:
- **Attended slot:** operator GO, then the window agent delegates it to
  cberg-agent, re-runs §3 step 5 with a new REV, and re-runs §4.4.
- **Nightly (unattended):** do NOT toggle. Leave the bump in place. Record a
  finding naming the node, and put the toggle in the morning report for the
  operator. `TalosKernelLogsMissingFromNode` pages at 3h+15m if the node stays
  silent. The only loss is the kernel-log diagnostic feed of that node, not user
  data.

### 5.4 Restore alert state (either outcome)

```bash
runbooks/update-marker.sh clear edot-collector
kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 >/dev/null 2>&1 & PF=$!
sleep 3
SID=$(python3 -c "import json;print(json.load(open('/private/tmp/claude-501/edot-01632-silence.json'))['silenceID'])")
curl -s -o /dev/null -w 'delete silence %{http_code}\n' -X DELETE "localhost:9093/api/v2/silence/$SID"
kill $PF 2>/dev/null
```

## 6) Interference notes

- **Step 0 may pre-empt this plan.** The nightly auto-update merged the 0.162.0
  PR #264 on 2026-10-08 as a "safe" minor. If Step 0 merges #324 before this
  plan runs, premise 1 fails, printing `:0.163.2`. Then:
  - do not re-run §3 steps 2–4;
  - run §3 step 5 and all of §4 as post-hoc verification, with the Ready
    timestamp of the pod that is running;
  - mark this plan executed only if §4 passes.
- **SEPARATE SLOT from otel-operator-0.25.1 (operator rule 2026-10-23):**
  otel-operator-0.25.1 runs FIRST, this plan in a later slot. Both gate on ES
  ingestion through this hop; a shared night makes every gap unattributable.
- **`conflicts_with` covers these mechanisms** (see frontmatter): producer roll into
  this sink (otel-operator-0.25.1), ES endpoint resolution (coredns), the kmsg LB
  VIP and pod network (cilium), node drains (talos x2), the RWO queue volume
  (longhorn), and a carried-over HA ref. No `kube-prometheus-stack` or `spegel`
  plan is open on 2026-10-23; if one appears for the same night (§4 reads Prometheus;
  spegel is the image-pull path for the new tag), serialize it in a separate slot.
  Re-checked against every open plan's frontmatter on 2026-10-23.
- **Slot preference: attended (sat/sun 09:00) over nightly, not required.** The
  plan fits a nightly slot (50 of 70 min). The only step that wants an operator
  is the §5.3 kmsg toggle, and that only on a stall.
- **The ingestion gap lasts tens of seconds** during the Recreate swap. The OTLP
  producers (otel-operator daemon collectors) buffer only in memory, so a few
  seconds of their data may be lost. The ES exporters here have
  `block_on_overflow: true` and a disk queue, so backpressure shows up as
  `otelcol_receiver_refused_*`, not as silent loss. Any heartbeat or kmsg line
  sent DURING the swap is lost (UDP, no listener), which is why §3 step 5 runs
  only after Ready.
- **The image is minimal** (no `cat`/`curl`/`wget`). Every check uses
  `kubectl get --raw` or port-forward plus local curl, never `kubectl exec`.
- **The daemon collectors are NOT moved.** They run
  `otel/opentelemetry-collector-k8s`, owned by HelmRelease `otel-operator`.
  Repo-wide, `otel/opentelemetry-collector-contrib:` appears only in
  `edot-collector/app/deployment.yaml`.
- **The kmsg heartbeat phase shifts.** After §3 step 5 the hourly heartbeat
  fires at the kick minute, not at :45 UTC. That is harmless:
  `TalosKernelLogsMissingFromNode` keys on "nothing for 3h".
- **Repo corrections owed (not fixed by this plan):**
  1. edot-collector-0.162.0 §1.3 says a `bogus_key` under the telemetry
     Prometheus reader validates with exit 0. Measured 2026-10-19 on both the
     0.162.0 and 0.163.2 darwin binaries, it exits 1 (`has invalid keys`). Only
     the ES-exporter unknown-key blind spot is real.
  2. The predecessor's §4.1 log floor (10,000) no longer has 2x headroom over
     the measured 7d minimum (15,510). This plan uses 7,500, and future edot
     plans should re-derive the floor from a fresh 7d minimum.
