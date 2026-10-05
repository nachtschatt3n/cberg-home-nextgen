---
plan_id: edot-collector-0.162.0
component: edot-collector
pr: null                          # NO Renovate PR. Lands via coverage.py's PLAN lane
                                  # (a hand edit of one image line), same path as the
                                  # executed edot-collector-0.161.0 (retired 4411b0f1).
kind: image
current: "0.161.0"                # MEASURED live 2026-09-30: deployment/edot-collector
                                  # runs otel/opentelemetry-collector-contrib:0.161.0,
                                  # pod imageID digest sha256:fd328de2...5ac1 (= Docker
                                  # Hub manifest-list digest for tag 0.161.0).
target: "0.162.0"                 # CORRECTED from the coverage target "0.162.0-386".
                                  # `0.162.0-386` is upstream's single-arch linux/386
                                  # (32-bit x86) build tag, NOT a build number: the
                                  # version picker's hex build-suffix pattern
                                  # `(-[0-9a-f]+)?` accepts "386" because it is made
                                  # only of digits. It was offered ONLY because the
                                  # multi-arch manifest-list tag `0.162.0` did not
                                  # exist yet (HTTP 404 on registry-1.docker.io AND
                                  # ghcr.io, measured 2026-09-30); once `0.162.0` is
                                  # published, the picker's clean-tag tiebreaker ranks
                                  # it above `-386`. Pin the plain tag. NEVER pin
                                  # `-386`. See §1.1 and §2.2 (the gate that BLOCKS
                                  # this plan until `0.162.0` exists).
update_type: minor                # 0.x line: the MINOR digit is the breaking axis
risk: medium                      # NOT from likelihood: the changelog is clean for
                                  # every component this config instantiates (§1.2),
                                  # and the live config validates on the 0.162.0
                                  # binary (§1.3). From blast radius + failure MODE:
                                  # single-replica, sole OTLP ingestion path into ES
                                  # for every namespace + the Talos kmsg sink, and its
                                  # characteristic failure is SILENT (§1.4).
est_duration_min: 45              # 10 pre-checks (tag gate, local + in-cluster
                                  # validate, baselines) + 3 edit/commit/push +
                                  # 5 reconcile + Recreate roll + 15 settle +
                                  # 12 verification. The 15m settle is sized on the
                                  # [15m] Prometheus windows of §4.1/§4.2: a window
                                  # that straddles the roll passes on pre-roll data.
                                  # (The 45m settle of 0.161.0's first draft belonged
                                  # to a retired counter gate — 0.161.0 §4.4.)
                                  # Nightly budget is 90 - STEP0_RESERVE(20) = 70m,
                                  # so this fits a nightly slot beside at most ~25m
                                  # of other work.
needs_reboot: false
touches:
  namespaces: [monitoring]
  resources:                      # every object below verified to EXIST live 2026-09-30
    - deployment/edot-collector               # the ONLY object this plan EDITS (image tag
                                              # + rollout-revision annotation)
    - configmap/edot-collector-config         # READ + validated against the 0.162.0
                                              # binary (§1.3, §2.3); NOT edited
    - pvc/edot-collector-queue                # RWO longhorn-static, Bound, 10Gi; bbolt
                                              # sending-queue; detach/attach on the
                                              # Recreate roll; the one forward-only
                                              # surface (§5.2)
    - service/edot-collector                  # ClusterIP 4317/4318/8888/8889 — every
                                              # OTLP producer's target
    - service/edot-collector-talos-kmsg       # LoadBalancer 192.168.55.18 UDP 5171
    - servicemonitor/edot-collector           # the scrape that feeds §4's gates (up==1
                                              # on both endpoints, measured)
    - httproute/edot-collector                # OTLP/HTTP on envoy-internal; backend
                                              # briefly down during the roll (§6)
  shared: [monitoring]            # this Deployment is the single OTLP choke point for
                                  # every namespace's logs/metrics into Elasticsearch
                                  # and the Talos kmsg sink; a roll blinds cluster-wide
                                  # log/metric ingestion for its duration. NOT
                                  # gateway/envoy: routing is unchanged, one HTTPRoute
                                  # backend is briefly unavailable.
depends_on: []
conflicts_with:                   # HARD slot exclusions (the only field
                                  # window-scheduler.py honours; it treats a
                                  # declaration in EITHER direction as symmetric).
  - otel-operator-0.23.0          # scheduled nightly:2026-10-03. It rolls
                                  # daemonset/otel-operator-daemon-collector, whose
                                  # pods EXPORT into edot-collector.monitoring.svc:4317
                                  # (its premise `otlp-sink-is-edot-collector`), and
                                  # its §4.4 proves itself through documents landing
                                  # in ES VIA THIS COLLECTOR. Both rolling in one
                                  # night makes any ingestion gap unattributable and
                                  # each plan's ES gate reads the other's roll as its
                                  # own regression. Its frontmatter carried the
                                  # reciprocal ref for 0.161.0 (removed on that plan's
                                  # retirement) — see §6 for the readability follow-up.
  - app-template-5.2.1            # scheduled nightly:2026-10-02. Rolls ~78 workloads
                                  # (incl. `monitoring`) in one reconcile: a mass pod
                                  # roll perturbs exactly the log-record and
                                  # metric-point volumes §4.1 gates on (the metric
                                  # band is ±20% on a series that is flat to <1% only
                                  # when nothing is churning), so a same-night run
                                  # can false-fail this plan into a needless revert.
  - chart-patches-coredns-reloader-blackbox  # rolls CoreDNS. All three ES exporters
                                  # resolve elasticsearch-es-http.monitoring.svc
                                  # through it; a DNS blip during §4 surfaces as
                                  # non-success outcomes in §4.2(b), which carries
                                  # revert authority. That plan already declares the
                                  # same mechanism against uptime-kuma/mariadb/redis.
  - talos-linux-1.14.2            # ADDED 2026-10-01 (review b23be87b). A node roll
                                  # drains/reboots each node in turn: it evicts this
                                  # single replica (RWO queue PVC re-attaches on the
                                  # new node) and silences each node's kmsg UDP feed
                                  # for its reboot, so §4.1/§4.3 (incl. the .11 kmsg
                                  # gate) would read the roll as this plan's
                                  # regression. Its sun-attended slot is exclusive
                                  # anyway; declared so the pair is explicit.
exclusive: false
security_ref: null                # no open security finding on the 0.161.0 image
                                  # (`finding list --grep collector-contrib`, 2026-09-30:
                                  # every row resolved). Not security-driven.
capability_change: false          # image tag only. No config change, no new receiver/
                                  # exporter/processor, no new route or permission.
                                  # The upstream behaviour changes that DO reach this
                                  # config are bug fixes or keepalive defaults with
                                  # the same observable contract (§1.2).
rollback_class: git-revert        # one-commit revert (image tag only, config
                                  # untouched). The one forward-only surface — the
                                  # bbolt queue written by the newer binary — has an
                                  # explicit contingency PROCEDURE in §5.2.
finding_refs: []                  # CHECKED 2026-09-30 with SWEEP_PG_DSN up:
                                  # `finding list --all --grep edot`, `--grep
                                  # collector-contrib`, `--grep 0.162`, `--grep 386`
                                  # and `--section version` return NO row for this
                                  # 0.161 -> 0.162 move (the previous row F-cb9182ca
                                  # is resolved; the only open version row in the
                                  # otel family is F-60ebcdb5, owned by
                                  # otel-operator-0.23.0). If the next sweep files one,
                                  # add its id here — the plan-or-page pass joins on it.
review: null
status: blocked   # BLOCKED 2026-10-05 (plan-reviewer, sweep 481b9c1f): target tag 0.162.0 is 404 on Docker Hub AND ghcr (only -amd64 per-arch tags exist); upstream re-push tracked in open-telemetry/community#3738. UNBLOCK = manifest list published (or retarget to 0.163.0) + add a target-manifest-list-published premise + per-node kmsg-heartbeat gate for .11/.12/.13 (kmsg-sender stall on collector restart), then re-review.
window: null
premises:
  # Re-checked at EXECUTION time. All three RUN on 2026-09-30 while writing this plan.
  - id: image-is-still-0.161.0
    why: >-
      `current:` claims 0.161.0. If the collector already moved, the rollback
      target and the §5.1 rollback digest are wrong. Fails loudly by printing the
      actual image.
    run: kubectl get deploy -n monitoring edot-collector -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "otel/opentelemetry-collector-contrib:0.161.0"
  - id: ingestion-is-healthy-before-we-touch-anything
    why: >-
      Never roll the sole telemetry path while it is ALREADY degraded — a
      pre-existing stall would be misattributed to this bump and burn the window
      on a false rollback. Asserts the logs exporter persisted >1000 records over
      the last 15m (measured 35,928 on 2026-09-30; 7d minimum of the same
      expression 20,860, so ~20x headroom). NEGATIVE CONTROL RUN 2026-09-30: the
      identical pipeline pointed at a nonexistent metric printed INGEST_LOW (the
      awk `$1+0` coercion makes an empty result fail closed). The comparison is
      written with `<` because the premise sandbox refuses any `>` character.
    run: kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=sum(increase(otelcol_exporter_sent_log_records_total[15m]))' | sed -E 's/.*"value":\[[0-9.]+,"([0-9]+).*/\1/' | awk '{print ($1+0<1000)?"INGEST_LOW":"INGEST_OK"}'
    expect_exact: "INGEST_OK"
  - id: config-is-the-one-validated-on-0.162.0
    why: >-
      §1.3's evidence (the live otel.yml validates on the 0.162.0 binary) holds
      only for the config committed in 42979120. If anyone touched the configmap
      since, that evidence is stale and §2.3 must be re-read with fresh eyes
      (it still runs either way). Prints the newer short sha if it moved.
    run: git log -1 --format=%h -- kubernetes/apps/monitoring/edot-collector/app/configmap.yaml
    expect_exact: "42979120"
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/monitoring.md                          # "ES Rejected Documents" — §4.2
                                                     # uses the dotted outcome metric
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/longhorn-rwo-multi-attach.md           # why strategy Recreate is
                                                     # load-bearing here
generated: "2026-09-30"
---

# edot-collector: image 0.161.0 → 0.162.0 (0.x release-line move)

## 1) Summary & why held

### 1.1 Why it was held — and what "0.162.0-386" actually is

`runbooks/coverage.py` put this in the PLAN lane on its component-agnostic rule:
*"0.x release-line move (0.161 -> 0.162) — at major 0 the minor IS the breaking
axis; needs an assessed window plan"*. No deny rule, no CVE driver.

**The coverage target `0.162.0-386` must NOT be pinned.** Measured on Docker Hub
2026-09-30, upstream's release pipeline pushed nine single-architecture tags for
this release on 2026-09-29 12:41–12:47Z — `0.162.0-amd64`, `-arm64`, `-armv7`,
`-386`, `-ppc64le`, `-s390x`, `-riscv64`, `-windows-2019-amd64`,
`-windows-2022-amd64` — and each carries exactly ONE image of that architecture
(`0.162.0-386` → `[('386', None)]`). `-386` is the 32-bit x86 build. The
multi-arch manifest-list tag `0.162.0` — the form this deployment has always
pinned (`0.161.0` is a manifest list: `application/vnd.docker.distribution.manifest.list.v2+json`,
7 architectures) — **did not exist** at planning time:

| registry | `0.162.0` | `0.162.0-amd64` | `0.161.0` |
|---|---|---|---|
| registry-1.docker.io | **404** | 200 (single manifest) | 200 (manifest list, `sha256:fd328de2…5ac1`) |
| ghcr.io/open-telemetry/opentelemetry-collector-releases | **404** | — | — |

The sibling distributions DID get their manifest lists in the same release
(`otel/opentelemetry-collector-k8s:0.162.0` 12:42Z, `-otlp` 12:45Z, core
13:24Z), and the upstream "Release Contrib v0.162.0" workflow run (36568582369)
reports success on every job, so the contrib manifest-list step is late or was
lost upstream; no upstream issue exists for it yet.

Why the picker chose `-386`: `check-all-versions.py`'s `_SEMVER_TAG_RE` treats
`(-[0-9a-f]+)?` as a build/sha suffix. `386` is all digits, therefore valid hex,
so `0.162.0-386` parses as "0.162.0 plus a build suffix" and is the only
0.162.0-shaped candidate while the plain tag is missing (`-amd64`/`-arm64` are
rejected because `m`/`r` are not hex). `_semver_tag_key`'s clean-tag tiebreaker
ranks a plain `0.162.0` above it as soon as the plain tag exists, so the snapshot
self-corrects — this is why `target:` is `0.162.0`. The picker defect itself is a
repo correction (see §6), not something this plan works around.

**Consequence for execution:** §2.2 is a HARD GATE that the manifest-list tag
`0.162.0` exists and includes `linux/amd64`. Until it does, this plan is
**blocked**, not "run with an arch tag". Pinning `0.162.0-amd64` would run, but
it is an operator decision (it abandons the manifest-list convention the digest
checks in §4/§5 rely on), not something this plan authorises.

### 1.2 Upstream evidence for 0.162.0 — assessed against OUR config

Sources read directly (authoring rule 8): contrib release `v1.1.0/v0.162.0`
(published 2026-09-29T10:11:33Z), core `v1.68.0/v0.162.0`
(2026-09-28T14:09:31Z), releases repo `v0.162.0` (2026-09-29T12:34:07Z).

The components `otel.yml` instantiates: `otlp` receiver, `udp_log/talos-kernel`
(stanza `json_parser`/`move`/`add`), `memory_limiter`, three `filter`
processors, one `transform` processor, `cumulative_to_delta`, `batch`, three
`elasticsearch` exporters, the `prometheus/hwerrors` exporter, the `count`
connector, `file_storage/queue`, `health_check`, and the `service::telemetry`
Prometheus reader.

**Contrib breaking changes that name a component we run — each checked:**

- **`exporter/elasticsearch`: Remove the deprecated `flush` and `num_workers`
  configuration settings (#42718).** This config uses neither (grepped: 0 hits
  for `flush` and `num_workers`; all three exporters use
  `sending_queue::num_consumers`). **Not ours — and note §1.3: the validator
  would NOT have caught it if it were.**
- **`exporter/elasticsearch`: OTel profiles go to OTel-native datastreams
  requiring Elasticsearch 9.6.0 (#50589).** Our ES is **8.19.20** (measured), but
  this config has no `profiles` pipeline (only logs, logs/talos-kernel,
  metrics/hwerrors, metrics, traces). Not ours.
- **`pkg/prometheus`: `PermissiveLabelSanitization` promoted to beta (on by
  default, #50429)** — labels beginning with a single `_` stop being prefixed
  with `key_`. Reaches `prometheus/hwerrors`, whose only label is `net.peer.ip`
  → `net_peer_ip` (no leading underscore). Not changed.
- **`processor/transform`: remove the stable `defaultErrorModeIgnore` gate
  (#51242)** and **`pkg/ottl`: remove two stable gates (#44630, #46437)** — only
  matter to a collector started with `--feature-gates`; ours has none (args are
  `--config=/config/otel.yml` only), and every filter/transform here sets
  `error_mode: ignore` explicitly.

The rest of the contrib breaking list (wavefront removal,
`signal_to_metrics`, `adaptive_tail_sampling`, `cardinality_guardian`,
`signing`, `kafka`/`kafka_metrics`, `receiver/prometheus`) names nothing we run.
The core breaking list (`cmd/mdatagen` test assertion, `queuebatch` →
`queue_batch` rename) names nothing we run.

**Behaviour changes in components we run (not breaking, recorded so a reviewer
does not have to rediscover them):**

- `processor/cumulative_to_delta`: histogram reset recovery fixed (#50828).
  May shift the metric-point count marginally after a producer restart; §4.1's
  band is ±20% on a series whose 24h spread is <1%, so this cannot trip it.
- `exporter/prometheus`: removes every series ended by a staleness marker
  (#51289) — `prometheus/hwerrors` only.
- `extension/health_check`: keepalive on by default (#51175); `pkg/confighttp`:
  keepalive config enabled by default behind the new `PrioritizeNewKeepalive`
  gate (#16026). HTTP connection reuse only; the readiness/liveness probes hit
  `:13133/` and are unaffected in contract.
- `pkg/exporterhelper`: when splitting a batch, drop only the oversized item
  instead of everything queued behind it (logs only, #15936) — strictly fewer
  drops.
- `pkg/ottl`: reject lambda expressions outside lambda-accepting arguments at
  parse time (#51560). This config has no lambdas; it parses (§1.3).

### 1.3 The live config validates on the 0.162.0 binary — and what that gate CANNOT see

Run 2026-09-30 on the Mac with the official
`otelcol-contrib_0.162.0_darwin_arm64` release binary (reports
`otelcol-contrib version 0.162.0`) against the LIVE `otel.yml` pulled from
`configmap/edot-collector-config` (identical to git apart from a trailing newline):

| input | 0.162.0 exit | meaning |
|---|---|---|
| live `otel.yml` | **0**, no output | accepted |
| `--config=/nonexistent.yml` | 1 | exit code propagates |
| pipeline references an undefined exporter | 1 | graph errors are caught |
| `num_consumers: notanint` inside an ES exporter | 1 | type errors are caught |
| unknown key in `otlp` receiver / `debug` exporter (minimal config) | 1 (`has invalid keys`) | strict for those components |
| **`num_workers: 2` added to `elasticsearch/logs`** | **0** | **ES exporter unknown keys NOT caught** |
| **`totally_unknown_field` added to an ES exporter** | **0** | same |
| **`bogus_key` added under `service::telemetry…prometheus`** | **0** | **telemetry-reader unknown keys NOT caught** |

The same three lenient cases also exit 0 on the 0.161.0 binary, so this is not
new in 0.162.0 — but it means **the validate gate cannot fail on a removed or
renamed key in exactly the two blocks that matter most here**: the ES exporters
and the `without_type_suffix`/`without_units`/`without_scope_info` pins. A
silently ignored `without_type_suffix` would rename
`otelcol_exporter_sent_*_total` and blind `EsLogIngestionStalled` /
`EsMetricsIngestionStalled`. §2.3 therefore stays as a gate for the failures it
CAN see, and the rename mode is caught by §4.1 (empty result = FAIL), pinned to
the named exporter by §4.5's direct `absent()` evaluation (the
`Es*ExporterSeriesMissing` alerts themselves carry `for: 15m` and cannot have
fired by T+15m, so they are not read as a gate). The 0.161.0 plan's claim that
validate would reject "an unknown `without_type_suffix`" was never tested and is
false; it is corrected here.

### 1.4 Why `risk: medium` despite a clean changelog

Blast radius and failure mode. One replica, the only OTLP path into
Elasticsearch for every namespace (measured live 15m: 29,411 log docs, 888,451
metric docs), plus the Talos kmsg sink on `192.168.55.18`. Its characteristic
failure is **silent** — pod Ready, health endpoint 200, telemetry simply not
counted. Hence §4 gates on contents with floors, and "pod Ready" is not the gate.

The 0.161.0 bump (executed 2026-09-26) went green with the same structure; this
plan reuses its measured gates, re-measured today.

## 2) Pre-checks

Run in order. Any failure stops the plan — do not proceed to §3.

```bash
cd /Users/mu/code/cberg-home-nextgen
# 2.1 — premises (re-run mechanically)
.venv/bin/python3 runbooks/plan-premises.py edot-collector-0.162.0
# PASS: all three premises PASS.

# 2.2 — HARD GATE: the MULTI-ARCH tag 0.162.0 exists, is a manifest list, and
# contains linux/amd64. Capture its manifest-list digest for §4/§5.
# At planning time (2026-09-30) this printed HTTP 404 -> plan BLOCKED.
T=$(curl -s "https://auth.docker.io/token?service=registry.docker.io&scope=repository:otel/opentelemetry-collector-contrib:pull" | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
curl -s -D /private/tmp/claude-501/edot-0162-hdr.txt -o /private/tmp/claude-501/edot-0162-manifest.json \
  -H "Authorization: Bearer $T" \
  -H "Accept: application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.list.v2+json" \
  https://registry-1.docker.io/v2/otel/opentelemetry-collector-contrib/manifests/0.162.0
python3 - <<'EOF'
import json,re
h=open('/private/tmp/claude-501/edot-0162-hdr.txt').read()
st=re.search(r'^HTTP/\S+ (\d+)',h,re.M).group(1)
dg=(re.search(r'(?im)^docker-content-digest:\s*(\S+)',h) or [None,None])[1]
if st!='200': print('TAG_MISSING http',st,'-> BLOCKED'); raise SystemExit
m=json.load(open('/private/tmp/claude-501/edot-0162-manifest.json'))
plats=[(x['platform']['os'],x['platform']['architecture']) for x in m.get('manifests',[])]
ok=('linux','amd64') in plats
print('TAG_OK' if ok else 'NO_AMD64', dg, plats)
if ok: open('/private/tmp/claude-501/edot-0162-target-digest','w').write(dg)
EOF
cat /private/tmp/claude-501/edot-0162-target-digest; echo
# PASS: prints TAG_OK sha256:<64 hex> with ('linux','amd64') in the list, and the
#       digest file is non-empty.
# FAILS AS: `TAG_MISSING http 404 -> BLOCKED` (measured 2026-09-30 — this line CAN
#       and DID fail), or NO_AMD64 (a single-arch manifest was pushed under the
#       plain tag), or an empty digest file. On any of these: STOP, set status
#       blocked, report. Do NOT substitute `0.162.0-386` or any arch tag.

# 2.3 — GATE: validate the LIVE config against the NEW binary, two ways.
# (a) locally with the upstream release binary (no cluster object created):
mkdir -p /private/tmp/claude-501/otel162 && cd /private/tmp/claude-501/otel162
gh release download v0.162.0 -R open-telemetry/opentelemetry-collector-releases \
  -p 'otelcol-contrib_0.162.0_darwin_arm64.tar.gz' --clobber
tar xzf otelcol-contrib_0.162.0_darwin_arm64.tar.gz otelcol-contrib
./otelcol-contrib --version                        # MUST print 0.162.0
kubectl get cm -n monitoring edot-collector-config -o jsonpath='{.data.otel\.yml}' > live-otel.yml
ES_PASSWORD=dummy ./otelcol-contrib validate --config=live-otel.yml > pos.out 2>&1; echo "validate exit=$?"
cat pos.out
# NEGATIVE CONTROL — must exit NON-zero, proving this gate can fail:
python3 -c "t=open('live-otel.yml').read();open('neg.yml','w').write(t.replace('num_consumers: 4','num_consumers: notanint',1))"
ES_PASSWORD=dummy ./otelcol-contrib validate --config=neg.yml > neg.out 2>&1; echo "negative-control exit=$?"
head -3 neg.out    # kept: §4.0 demonstrates its startup-error grep against this file
cd /Users/mu/code/cberg-home-nextgen
# PASS: validate exit=0 with EMPTY pos.out, AND negative-control exit=1 with
#       neg.out starting "Error: failed to get config: cannot unmarshal" (measured
#       exactly so on 2026-09-30 and again 2026-10-01).
# FAILS AS: non-zero exit naming the rejected key/type (e.g. "'num_consumers'
#       expected type 'int'"), or a pipeline "references exporter ... which is not
#       configured". If it fails -> BLOCKED; the fix is a config change = a
#       different plan. REMEMBER §1.3: this gate is BLIND to unknown keys in the ES
#       exporters and the telemetry reader; §4.1 covers that mode.
#
# (b) in-cluster with the linux image that will actually run (only after 2.2 passed).
# EVERY command carries `-n monitoring`: the kube context's namespace is `default`
# (measured 2026-10-01), where configmap/edot-collector-config does not exist — the
# pod would sit in ContainerCreating and read as a false STOP.
# NO `-i --rm`: `--overrides` defaults to `--override-type=merge` (JSON merge
# patch), which REPLACES the generated containers list and so drops the
# stdin/stdinOnce that `-i` sets — the attach then hangs or returns kubectl's exit
# code, not the container's. Instead: run detached, wait for a terminal phase, read
# the container's own exitCode + logs, delete. Rendered spec checked 2026-10-01 with
# `--dry-run=client -o yaml` (namespace monitoring, configMap volume present,
# runAsUser 10001). monitoring is PSA `privileged`, so nothing is rejected at admission.
edot_validate() {  # $1 = pod name, $2 = --config path, $3 = mount cm? (yes|no)
  local OV
  if [ "$3" = yes ]; then
    OV='{"spec":{"securityContext":{"runAsNonRoot":true,"runAsUser":10001,"runAsGroup":10001},"containers":[{"name":"'"$1"'","image":"otel/opentelemetry-collector-contrib:0.162.0","command":["/otelcol-contrib","validate","--config='"$2"'"],"env":[{"name":"ES_PASSWORD","value":"dummy-validate-only"}],"volumeMounts":[{"name":"cfg","mountPath":"/config","readOnly":true}]}],"volumes":[{"name":"cfg","configMap":{"name":"edot-collector-config"}}]}}'
  else
    OV='{"spec":{"securityContext":{"runAsNonRoot":true,"runAsUser":10001,"runAsGroup":10001},"containers":[{"name":"'"$1"'","image":"otel/opentelemetry-collector-contrib:0.162.0","command":["/otelcol-contrib","validate","--config='"$2"'"]}]}}'
  fi
  kubectl delete pod -n monitoring "$1" --ignore-not-found >/dev/null
  kubectl run "$1" -n monitoring --restart=Never \
    --image=otel/opentelemetry-collector-contrib:0.162.0 --overrides="$OV" >/dev/null
  local PH=""
  for i in $(seq 1 60); do
    PH=$(kubectl get pod -n monitoring "$1" -o jsonpath='{.status.phase}')
    case "$PH" in Succeeded|Failed) break ;; esac
    sleep 3
  done
  case "$PH" in Succeeded|Failed) ;; *)
    echo "NOT_TERMINAL phase=$PH -> STOP; pod $1 left in place for: kubectl describe pod -n monitoring $1"
    return 1 ;; esac
  echo "phase=$PH exitCode=$(kubectl get pod -n monitoring "$1" -o jsonpath='{.status.containerStatuses[0].state.terminated.exitCode}')"
  kubectl logs -n monitoring "$1" > "/private/tmp/claude-501/$1.out" 2>&1
  cat "/private/tmp/claude-501/$1.out"
  kubectl delete pod -n monitoring "$1" --ignore-not-found >/dev/null
}
edot_validate edot-validate-0162     /config/otel.yml    yes
edot_validate edot-validate-0162-neg /nonexistent/otel.yml no
grep -ic 'nonexistent/otel.yml' /private/tmp/claude-501/edot-validate-0162-neg.out
# PASS (positive): `phase=Succeeded exitCode=0` and the log file contains nothing
#       matching (case-insensitive) error|invalid|cannot unmarshal.
# PASS (negative control — proves the harness can fail): `phase=Failed` with a
#       NON-zero exitCode AND the final grep prints >= 1, i.e. the output names
#       /nonexistent/otel.yml. A non-zero exit WITHOUT that path in the output means
#       the pod failed for some other reason (pull error, admission, wrong arch) and
#       proves nothing about the harness — investigate, do not count it as a pass.
# FAILS AS: positive pod Failed / non-zero / error text -> BLOCKED (config change =
#       different plan). `NOT_TERMINAL` after the 180s loop = image pull or volume
#       problem -> STOP, read `kubectl describe pod`, then delete the pod by hand
#       (`kubectl delete pod -n monitoring <name>`). An "exec format error" means the pulled image is the
#       wrong architecture -> STOP (that is the -386 trap).

# 2.4 — BASELINES for §4, each over the SAME window its gate uses.
# Measured 2026-09-30 for reference (yours will differ):
#   sent log records [15m]        35,929   (7d min 20,860, 7d max 505,689)
#   sent metric points [15m]   2,009,988   (24h range 2,006,087 - 2,020,343)
#   docs.processed success [15m]  925,224   non-success [15m]: EMPTY
P=/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query
kubectl get --raw "${P}?query=sum(increase(otelcol_exporter_sent_log_records_total[15m]))"; echo
kubectl get --raw "${P}?query=sum(increase(otelcol_exporter_sent_metric_points_total[15m]))"; echo
kubectl get --raw "${P}?query=sum%20by%20(outcome)%20(increase(%7B__name__%3D%22otelcol.elasticsearch.docs.processed_total%22%7D%5B15m%5D))"; echo
# Record the metric-points value as MP_BASE for §4.1.

# 2.5 — pre-state is clean
kubectl get pods -n monitoring -l app=edot-collector -o wide
kubectl get pvc -n monitoring edot-collector-queue
flux get kustomizations -n monitoring | awk 'NR==1 || $4 != "True"'
# PASS: 1/1 Running, PVC Bound, no kustomization off True.
```

## 3) Steps (GitOps)

**1. Silence expected rollout noise and mark the update active.** Every alert
name below exists in
`kubernetes/apps/monitoring/kube-prometheus-stack/app/otel-collector-alerts.yaml`
(checked 2026-09-30). The three `Es*ExporterSeriesMissing` absent() guards are
deliberately NOT silenced, so a real disappearance still pages after the
window; §4.5 evaluates their expressions directly (their `for: 15m` hides them
at T+15m).

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 >/dev/null 2>&1 & PF=$!
sleep 3
NOW=$(python3 -c "from datetime import *;print(datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
END=$(python3 -c "from datetime import *;print((datetime.now(timezone.utc)+timedelta(hours=3)).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
curl -s -X POST localhost:9093/api/v2/silences -H 'Content-Type: application/json' -d '{
  "matchers":[{"name":"namespace","value":"monitoring","isRegex":false,"isEqual":true},
              {"name":"alertname","value":"EdotCollectorDown|OtelCollectorExportFailed|OtelCollectorRecordsRefused|OtelCollectorQueueFull|EdotCollectorESAuthError|EsMetricsIngestionStalled|EsLogIngestionStalled|EsExportQueueStuckFull","isRegex":true,"isEqual":true}],
  "startsAt":"'"$NOW"'","endsAt":"'"$END"'","createdBy":"maintenance-window-agent",
  "comment":"edot-collector 0.161.0->0.162.0 - expected rollout noise. auto-expires 3h"}' \
  | tee /private/tmp/claude-501/edot-0162-silence.json; echo   # prints {"silenceID":"..."}; empty = NOT silenced
kill $PF 2>/dev/null
runbooks/update-marker.sh add edot-collector monitoring 3 "0.161.0->0.162.0 bump"
```

**2. Edit the image tag.** DRY-TESTED 2026-09-30 on a scratch copy of the real
file with macOS BSD sed (exit 0); the diff it produced is pasted verbatim below.
The image pattern is anchored with `$` so it can never match a `-386`/arch tag,
and the revision pattern is `".*"` so it cannot silently no-op if another plan
stamped the line first.

```bash
REV="$(date -u +%Y-%m-%d).1"
sed -i '' \
  -e 's|image: otel/opentelemetry-collector-contrib:0.161.0$|image: otel/opentelemetry-collector-contrib:0.162.0|' \
  -e 's|cberg.dev/rollout-revision: ".*"|cberg.dev/rollout-revision: "'"$REV"'"|' \
  kubernetes/apps/monitoring/edot-collector/app/deployment.yaml
git diff kubernetes/apps/monitoring/edot-collector/app/deployment.yaml
```

Dry-test output (`diff original scratch`, REV=2026-09-30.1):

```
26c26
<         cberg.dev/rollout-revision: "2026-09-26.1"
---
>         cberg.dev/rollout-revision: "2026-09-30.1"
40c40
<           image: otel/opentelemetry-collector-contrib:0.161.0
---
>           image: otel/opentelemetry-collector-contrib:0.162.0
```

**Both hunks must be present.** Only the revision hunk → the image line did not
match: STOP (premise 1 has been invalidated). Only the image hunk → set the
revision by hand (traceability only).

**3. Commit and push** (shared worktree — `--only`, never `git add -A`):

```bash
git fetch origin main && git merge --ff-only origin/main
MSG=/private/tmp/claude-501/msg-edot-collector-0.162.0-$(date +%s).txt
printf '%s\n' "chore(monitoring): edot-collector 0.161.0 -> 0.162.0 (plan edot-collector-0.162.0)" > "$MSG"
git commit --only kubernetes/apps/monitoring/edot-collector/app/deployment.yaml -F "$MSG"
git show --stat HEAD       # exactly one file: deployment.yaml
git log -1 --format=%s     # MUST be your subject; amend before pushing if not
git push origin main
```

**4. Reconcile and watch the Recreate roll.** The Flux Kustomization lives in
namespace **`monitoring`** (`kubectl get kustomization -n monitoring
edot-collector` → Ready, measured 2026-09-30). `-n flux-system` errors, after
which `rollout status` green-lights the OLD generation — a false success.
`strategy: Recreate` is load-bearing (RWO Longhorn PVC at `replicas: 1`); do not
hand-delete pods mid-roll.

```bash
GEN_BEFORE=$(kubectl get deployment edot-collector -n monitoring -o jsonpath='{.metadata.generation}')
flux reconcile kustomization edot-collector -n monitoring --with-source
kubectl get deployment edot-collector -n monitoring -o jsonpath='{.spec.template.spec.containers[0].image}'; echo
GEN_AFTER=$(kubectl get deployment edot-collector -n monitoring -o jsonpath='{.metadata.generation}')
echo "generation $GEN_BEFORE -> $GEN_AFTER"
kubectl rollout status deployment/edot-collector -n monitoring --timeout=180s
kubectl get pods -n monitoring -l app=edot-collector -o wide
kubectl get pods -n monitoring -l app=edot-collector \
  -o jsonpath='{.items[0].status.startTime}' > /private/tmp/claude-501/edot-0162-rollout-ts
cat /private/tmp/claude-501/edot-0162-rollout-ts; echo   # MUST be non-empty and AFTER the push
```

**HARD GATE:** the printed image reads `:0.162.0` AND `GEN_AFTER > GEN_BEFORE`.
Otherwise nothing rolled — do not continue into §4, whose gates would all pass
on the old binary.

**5. Wait 15 minutes** so every `[15m]` window in §4 lies entirely after the new
pod's start (a straddling window passes on pre-roll data).

## 4) Verification

### 4.0 Floor (shape — necessary, NOT sufficient)

```bash
kubectl get deployment edot-collector -n monitoring -o jsonpath='{.status.readyReplicas}'; echo
TARGET_DIGEST=$(cat /private/tmp/claude-501/edot-0162-target-digest)
test -n "$TARGET_DIGEST" || echo "NO_TARGET_DIGEST -> FAIL"
LIVE_ID=$(kubectl get pods -n monitoring -l app=edot-collector \
  -o jsonpath='{.items[0].status.containerStatuses[0].imageID}')
echo "live: $LIVE_ID"
case "$LIVE_ID" in
  *"$TARGET_DIGEST") echo "DIGEST_OK" ;;
  *) echo "DIGEST_MISMATCH" ;;
esac
kubectl logs -n monitoring deploy/edot-collector | head -80 | grep -iE "error|invalid configuration|panic|exec format" || echo "no startup errors"
# Positive demonstration of the SAME grep against the collector's own error format
# (the §2.3(a) negative-control output — capture it there with
#  `ES_PASSWORD=dummy ./otelcol-contrib validate --config=neg.yml > neg.out 2>&1`):
grep -ciE "error|invalid configuration|panic|exec format" /private/tmp/claude-501/otel162/neg.out
# MUST print >= 1 (measured 2026-10-01 on the 0.162.0 binary: exit 1, 6 matching
# lines, first line "Error: failed to get config: cannot unmarshal the configuration").
# The live pos.out under the same grep: 0 lines.
```

**PASS (gating):** `readyReplicas` 1 and `DIGEST_OK`.
**Startup-error grep:** a hit is a FAIL (read the lines, then §5). Zero hits is
supporting evidence only, not proof: the pattern is shown to match the
collector's error output (the demonstration above), but a config the binary
rejects outright crashloops and is already caught by `readyReplicas`, and the
mode this grep exists for — a runtime error after a clean start — is gated on
contents in §4.1/§4.2, not here.
**FAILS AS:** `DIGEST_MISMATCH` — the pod runs something other than the
manifest list captured in §2.2 (measured precedent: `imageID` carries the
MANIFEST-LIST digest, e.g. today's `…@sha256:fd328de2…5ac1` for 0.161.0, so a
per-arch digest here means a single-arch tag was pinned). `exec format error`
means a wrong-architecture image.

### 4.1 Telemetry still FLOWS

CONTENTS ASSERTION: the exporters are still persisting log records and metric
points — measured by `increase(...[15m])` read at T+15m, compared to the §2.4
baselines.

CONTROL: metric otelcol_exporter_sent_log_records_total — `sum(increase([15m]))` must be >= 10,000 (floor)
CONTROL: metric otelcol_exporter_sent_metric_points_total — `sum(increase([15m]))` within ±20% of MP_BASE (band)

```bash
P=/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query
kubectl get --raw "${P}?query=sum(increase(otelcol_exporter_sent_log_records_total[15m]))"; echo
kubectl get --raw "${P}?query=sum(increase(otelcol_exporter_sent_metric_points_total[15m]))"; echo
```

**PASS:**
- log records **>= 10,000** — a FLOOR, not a band: the 7d range of this exact
  expression is 20,860 – 505,689 (measured 2026-09-30), a 24x natural spread
  that no band survives; 10,000 is half the 7d minimum, reachable only by a real
  collapse.
- metric points **within ±20% of MP_BASE** — this series is genuinely flat
  (24h range 2,006,087 – 2,020,343, <1% spread), so a band is safe and catches a
  partial pipeline loss a floor would miss.

**FAILS AS:** an **empty `result` array** — the metric stopped being exported
under that name. This is precisely the §1.3 blind spot (a silently ignored
`without_type_suffix` renames `…_total`), so empty is a FAIL, never a skip.
Or a value under the floor / outside the band. Can-fail shown 2026-09-30: the
same query form against a nonexistent metric returns an empty result.

### 4.2 Elasticsearch is not silently REJECTING

CONTENTS ASSERTION: per-document outcome at the ES exporter is success-only —
the exporter's own outcome counter over `[15m]` after the roll.

CONTROL: metric otelcol.elasticsearch.docs.processed_total — (a) `outcome="success"` present and non-zero; (b) `outcome!~"success|retried"` empty or zero

Use the DOTTED name (the telemetry pins keep dots; the underscored form reads
empty on both sides and can never fail — docs/sops/monitoring.md).

```bash
P=/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query
# (a) FLOOR — success series must exist and be non-zero
kubectl get --raw "${P}?query=sum%20by%20(outcome)%20(increase(%7B__name__%3D%22otelcol.elasticsearch.docs.processed_total%22%7D%5B15m%5D))"; echo
# (b) CEILING — non-success outcomes must be absent/zero
kubectl get --raw "${P}?query=sum%20by%20(outcome)%20(increase(%7B__name__%3D%22otelcol.elasticsearch.docs.processed_total%22%2Coutcome!~%22success%7Cretried%22%7D%5B15m%5D))"; echo
```

**PASS:** (a) returns `outcome="success"` non-zero (baseline 925,224 / 15m) AND
(b) returns an empty result or zeros.
**Can-fail shown 2026-09-30:** `max_over_time` of (b) over 7d returns
`internal_server_error` 10,151 and `timeout` 46,357 — the gate reads real
non-success outcomes when they happen.
**Attribution:** `failed_client` = binary/config signal → revert. A non-zero
`timeout`/`internal_server_error` is ES-side → check `_cluster/health` (4.3)
before reverting; do not revert a good binary for an ES hiccup.
A missing `success` series in (a) is itself a FAIL (rejection SLI blind).

### 4.3 Documents actually LANDED in Elasticsearch, incl. Talos kmsg

CONTENTS ASSERTION: new documents exist in both data streams with `@timestamp`
after the roll, and node `.11`'s kernel log lines arrive through the udp_log
receiver on the new binary — measured in ES itself (the `_bulk` API returns 200
even when every item is rejected, so "sent" is not "stored").

```bash
ES_PW=$(kubectl get secret -n monitoring elasticsearch-es-elastic-user -o jsonpath='{.data.elastic}' | base64 -d)
kubectl port-forward -n monitoring svc/elasticsearch-es-http 19211:9200 >/dev/null 2>&1 & PF=$!
sleep 4
ROLLOUT_TS=$(cat /private/tmp/claude-501/edot-0162-rollout-ts)
test -n "$ROLLOUT_TS" || echo "NO_ROLLOUT_TS -> FAIL"
for DS in logs-generic-default metrics-generic.otel-default; do
  echo -n "$DS "
  curl -k -s -u "elastic:$ES_PW" -H 'Content-Type: application/json' \
    -X POST "https://localhost:19211/$DS/_count" \
    -d '{"query":{"range":{"@timestamp":{"gte":"'"$ROLLOUT_TS"'"}}}}' \
    | python3 -c "import sys,json;print(json.load(sys.stdin).get('count'))"
done
curl -k -s -u "elastic:$ES_PW" -H 'Content-Type: application/json' \
  "https://localhost:19211/logs-generic-default/_search" \
  -d '{"size":0,"query":{"bool":{"filter":[{"term":{"attributes.log_source":"talos-kernel"}},{"range":{"@timestamp":{"gte":"'"$ROLLOUT_TS"'"}}}]}},"aggs":{"ip":{"terms":{"field":"attributes.net.peer.ip","size":5}}}}' \
  | python3 -c "import sys,json;d=json.load(sys.stdin);b={x['key']:x['doc_count'] for x in d['aggregations']['ip']['buckets']};print(b);print('KMSG_OK' if b.get('192.168.55.11',0)>=20 else 'KMSG_FAIL')"
curl -k -s -u "elastic:$ES_PW" "https://localhost:19211/_cluster/health" \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['status'],d['unassigned_shards'])"
kill $PF 2>/dev/null
```

**PASS:** both datastream counts > 0 (baseline per 15m on 2026-09-30: logs
29,411, metrics 888,451); `KMSG_OK`; cluster `green`/`yellow` with 0 unassigned.
**Both sides of the kmsg gate DEMONSTRATED 2026-09-30** with this exact query:
`gte now-15m` → `{'192.168.55.11': 176}` / `KMSG_OK`; `gte now+1h` → `{}` /
`KMSG_FAIL`. A KeyError on `aggregations` is a FAIL.
`.12`/`.13` are informational only (1–2 docs/hour measured) — record their
counts; the next sweep owes a ">= 1 per node over 24h after ROLLOUT_TS" check.
`traces-generic-default` is deliberately NOT gated: it returned no count on
2026-09-30 (no trace producers), so a gate on it could only ever read empty.

### 4.4 Talos kmsg counter re-registered

CONTROL: metric talos_kernel_kmsg_lines_total — `absent(talos_kernel_kmsg_lines_total)` must return an EMPTY result at T+15m (direct eval, see §4.5)

The `prometheus/hwerrors` exporter is in-memory, so the restart wipes its
series; they reappear with the first kmsg line from any node (`.11` ships
~10 lines/min). `TalosKmsgPipelineDown` wraps this expression with `for: 15m`,
so at T+15m the alert can at most be pending — reading the alert is useless
here; the expression is evaluated directly in §4.5.

### 4.5 The exporter series EXIST — direct absent() evaluation

The `Es*ExporterSeriesMissing` / `TalosKmsgPipelineDown` rules all carry
`for: 15m` (`otel-collector-alerts.yaml`, `node-hardware-alerts.yaml`), so a
series that vanished at the roll is at most `pending` at T+15m and never shows
in Alertmanager — an Alertmanager read here could not fail. Evaluate the rules'
own expressions in Prometheus instead; an `absent()` that returns a sample IS
the failure, with no `for:` delay.

CONTROL: metric otelcol_exporter_sent_log_records_total — `absent(...{exporter="elasticsearch/logs"})` must be EMPTY
CONTROL: metric otelcol_exporter_sent_metric_points_total — `absent(...{exporter="elasticsearch/metrics"})` must be EMPTY

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

**PASS:** the first three print `PRESENT`; the fourth (the positive control)
prints `ABSENT`.
**Both sides DEMONSTRATED live 2026-10-01** with these exact expressions: the
logs, metrics and kmsg `absent()` each returned `"result":[]`; the
`exporter="elasticsearch/bogus"` control returned
`[{"metric":{"exporter":"elasticsearch/bogus"},"value":[…,"1"]}]`. If the
control does NOT print `ABSENT`, the harness is broken (query mangled, wrong
endpoint) and the three PRESENT lines mean nothing — FAIL.
**FAILS AS:** `ABSENT` on line 1 or 2 — the exporter series is gone under that
name (the §1.3 rename mode) → §5. `ABSENT` on line 3 at T+15m is a FAIL only if
§4.3 also printed `KMSG_FAIL`; with `KMSG_OK` (lines landed in ES) re-check once
after 5 more minutes before reverting.
**Scope:** this is a corroborating check. The primary detector for the
disappearance mode §1.3 says the validator cannot see is §4.1's empty-result
FAIL — §4.1 already fails if either `…_total` series is gone; §4.5 pins it to
the named exporter. `EsTracesExporterSeriesMissing` is not gated (no trace
producers).

## 5) Rollback

### 5.1 Primary — revert the commit

```bash
git fetch origin main && git merge --ff-only origin/main
git revert --no-edit <bump-commit-sha>
git push origin main
flux reconcile kustomization edot-collector -n monitoring --with-source   # namespace monitoring, NOT flux-system
kubectl rollout status deployment/edot-collector -n monitoring --timeout=180s
ROLLBACK_DIGEST=sha256:fd328de2552466ad78385e1b1289c3f2402b1c45f265b252aab1955b42845ac1
LIVE_ID=$(kubectl get pods -n monitoring -l app=edot-collector \
  -o jsonpath='{.items[0].status.containerStatuses[0].imageID}')
case "$LIVE_ID" in
  *"$ROLLBACK_DIGEST") echo "ROLLBACK_DIGEST_OK" ;;
  *) echo "ROLLBACK_DIGEST_MISMATCH: $LIVE_ID" ;;
esac
```

`$ROLLBACK_DIGEST` is 0.161.0's manifest-list digest, measured 2026-09-30 from
the running pod's `imageID` and equal to Docker Hub's digest for tag `0.161.0`.
Then **re-run §4.1–§4.3** — a revert that restores the manifest but not the
telemetry is not a rollback.

### 5.2 Contingency — the one forward-only surface (bbolt queue)

`pvc/edot-collector-queue` holds the persistent sending queue written by
whichever binary runs. Neither changelog touches the persistent-queue format,
so 0.161.0 is expected to read it back. **If the reverted pod crashloops on the
queue file** (`kubectl logs -n monitoring deploy/edot-collector --tail=50 | grep
-iE "bolt|storage|queue|corrupt"` names the store):

1. `kubectl scale deploy/edot-collector -n monitoring --replicas=0` (releases
   the RWO volume). Note Flux will scale it back on its next reconcile
   (interval 30m) — do steps 2–3 promptly.
2. Wait until the collector pod is gone (`kubectl get pods -n monitoring -l
   app=edot-collector` prints nothing — the RWO volume must be detached), then
   mount `pvc/edot-collector-queue` in a throwaway pod with the Deployment's
   uid/gid/fsGroup 10001 and empty it (the Deployment mounts it at
   `/var/lib/otelcol/sending-queue`; here it is `/q`). Spec checked 2026-10-01
   with `--dry-run=client` (namespace monitoring, claimName edot-collector-queue):

   ```bash
   kubectl run edot-queue-wipe -n monitoring --restart=Never --image=busybox:1.37 \
     --overrides='{"spec":{"securityContext":{"runAsUser":10001,"runAsGroup":10001,"fsGroup":10001},"containers":[{"name":"edot-queue-wipe","image":"busybox:1.37","command":["sh","-c","ls -la /q; find /q -mindepth 1 -delete; echo REMAINING=$(find /q -mindepth 1 | wc -l)"],"volumeMounts":[{"name":"q","mountPath":"/q"}]}],"volumes":[{"name":"q","persistentVolumeClaim":{"claimName":"edot-collector-queue"}}]}}'
   kubectl wait pod/edot-queue-wipe -n monitoring --for=jsonpath='{.status.phase}'=Succeeded --timeout=180s
   kubectl logs -n monitoring edot-queue-wipe      # MUST end with REMAINING=0
   kubectl delete pod -n monitoring edot-queue-wipe
   ```

   A timeout with the pod `ContainerCreating` = the volume is still attached
   elsewhere (Multi-Attach) — the collector pod has not fully terminated; wait,
   do not force-detach.
3. `kubectl scale deploy/edot-collector -n monitoring --replicas=1`, re-run
   §4.1–§4.3.

Cost: the buffered in-flight telemetry only (`create_directory: true` makes an
empty directory a clean start). **Operator-visible** — record it; it is the only
step that loses data.

### 5.3 Restore alert state (either outcome)

```bash
runbooks/update-marker.sh clear edot-collector
kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 >/dev/null 2>&1 & PF=$!
sleep 3
SID=$(python3 -c "import json;print(json.load(open('/private/tmp/claude-501/edot-0162-silence.json'))['silenceID'])")
curl -s -o /dev/null -w 'delete silence %{http_code}\n' -X DELETE "localhost:9093/api/v2/silence/$SID"
kill $PF 2>/dev/null
```

## 6) Interference notes

- **BLOCKED until upstream publishes the manifest list** (§2.2). Scheduling is
  fine; executing is not until `TAG_OK`. If the window arrives and §2.2 still
  prints `TAG_MISSING`, skip the plan (no change made) and leave it scheduled
  for the next slot.
- **`conflicts_with` carries four mechanisms** (frontmatter): otel-operator
  (producer roll into this sink), app-template (mass roll perturbs the §4.1
  volumes), CoreDNS (ES endpoint resolution under §4.2(b)), talos-linux-1.14.2
  (node drains evict this replica and pause each node's kmsg feed — §4.1/§4.3).
  `kube-prometheus-stack-91.4.1` is executed and no other kube-prometheus-stack
  plan is open (re-checked 2026-10-01); if one appears it MUST be added here —
  every §4.1/§4.2/§4.5 gate reads Prometheus.
- **flux-reconciler-impersonation** (draft, `exclusive: true`) rewires the
  identity every Kustomization — including `kustomization/edot-collector` in
  `monitoring` — is applied under. Its exclusivity already keeps it out of
  this slot, so it is not in `conflicts_with`. If it has executed before this
  plan runs, `monitoring` is one of its cluster-admin-tier namespaces, so §3.4's
  reconcile is expected to apply unchanged; but if §3.4 reports a Forbidden /
  impersonation error, that is the impersonation change, not this bump — STOP
  and report rather than retrying or reverting.
- **Reciprocal refs (readability, not a scheduling hole):** the scheduler
  honours a declaration in either direction, but `otel-operator-0.23.0`'s
  frontmatter now names `edot-collector-0.162.0` back (added 2026-10-01 in the
  same commit as this amendment). `app-template-5.2.1`,
  `chart-patches-coredns-reloader-blackbox` and `talos-linux-1.14.2` do not yet
  name it back — left for those plans' owners.
- **flux-fleet-0.60.0** (nightly 2026-10-06) upgrades the Flux controllers this
  plan's §3.4 reconcile depends on. No telemetry mechanism links them, so it is
  not a conflict; if both land in one window, run this plan only after
  flux-fleet's own verification has passed.
- **Expect an ingestion gap of tens of seconds** during the Recreate swap. OTLP
  producers (the otel-operator daemon collectors) buffer only in memory, so a
  few seconds of their data may be lost; the ES exporters here have
  `block_on_overflow: true` and a disk queue, so backpressure shows up as
  `otelcol_receiver_refused_*`, not as silent loss.
- **The image is minimal** (no `cat`/`curl`/`wget`): every check uses
  `kubectl get --raw` or `port-forward` + local curl, never `kubectl exec`.
  Port-forwards are killed by `$!` PID.
- **The daemon collectors are NOT moved** — they run
  `otel/opentelemetry-collector-k8s`, owned by HelmRelease `otel-operator` and
  by `otel-operator-0.23.0`. Repo-wide, `otel/opentelemetry-collector-contrib:`
  appears only in `kubernetes/apps/monitoring/edot-collector/app/deployment.yaml`.
- **Repo corrections owed (not fixed by this plan):**
  1. `runbooks/check-all-versions.py` `_SEMVER_TAG_RE`/`_semver_tag_key`: the
     `-[0-9a-f]+` build-suffix pattern accepts the architecture tag `-386`, so
     any upstream that publishes per-arch tags before its manifest list gets a
     32-bit-x86 tag proposed as the upgrade target. On a PATCH release this row
     would be `update_type: patch` and eligible for the unattended Step-0
     auto-apply lane. Architecture suffixes (`386`, and for safety
     `amd64|arm64|armv7|ppc64le|s390x|riscv64|windows-*`) should be excluded
     explicitly.
  2. The retired 0.161.0 plan asserted `validate` would reject an unknown
     `without_type_suffix`; measured false on both 0.161.0 and 0.162.0 (§1.3).
     Any future edot plan must not lean on `validate` for key renames in the
     ES exporter or telemetry-reader blocks.
