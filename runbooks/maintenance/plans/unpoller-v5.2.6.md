---
plan_id: unpoller-v5.2.6
component: unpoller
pr: null                              # no open Renovate PR (`gh pr list --state open`
                                      # 2026-09-17 shows only #217 esphome and #212 talos
                                      # CLI). Like v5.2.5, this reaches the PLAN lane via
                                      # coverage.py's no-PR direct-bump path, blocked by the
                                      # `*unpoller*` deny rule — see §1.4
kind: image
current: "v5.2.5"                     # live on deployment/unpoller, verified 2026-09-17 01:58Z
target: "v5.2.6"                      # released 2026-09-16 00:40Z; ghcr manifest HEAD 200
update_type: patch
risk: low                             # 3 files changed upstream, ZERO of them Go source in
                                      # our review-sensitive paths: a dependabot go.mod/go.sum
                                      # group and a distroless base bump. The base change is
                                      # the one novel element vs v5.2.5 and it was MEASURED,
                                      # not assumed — §1.3. No metric rename, no InfluxDB
                                      # schema change, no config-contract change.
est_duration_min: 15                  # commit+push ~2, reconcile+rollout ~3, settle >=5 for
                                      # the contents assertions (60s scrape, 2m cache refresh)
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
                                      # to name this one back. Checked against
                                      # `maintenance-plan.py --open` on 2026-09-17.
  - kube-prometheus-stack-91.4.0      # MANDATORY. §4.3-4.5 read THIS Prometheus over a >=5-min
                                      # settle; kps-91.4.0 restarts Prometheus AND Alertmanager
                                      # (2-5 min blind spot) and a replaying Prometheus answers
                                      # "no data", which reads as an unpoller regression and
                                      # would trigger a needless §5 revert. That plan's own §6
                                      # says it outright: "Any future unpoller plan must re-add
                                      # the exclusion for the same reason" (it dropped the
                                      # unpoller-v5.2.5 ref on 2026-09-16 when that plan
                                      # executed). Both are window:null, so they CAN be
                                      # co-slotted without this line.
  - prometheus-crd-ownership          # Same instrument, and it CreateReplace-adjacent touches
                                      # servicemonitors.monitoring.coreos.com — the CRD that
                                      # defines the object carrying this plan's only scrape
                                      # path. Its §4.2 asserts generation/resourceVersion are
                                      # UNCHANGED, so the expected perturbation is zero; the
                                      # exclusion is for the failure case, where a momentary
                                      # CRD race stops the unpoller scrape and this plan's
                                      # verification misattributes it to the image bump.
                                      # vetted + window:null → co-slottable without this line.
  - cilium-1.20.2                     # A CNI roll restarts pod networking cluster-wide; every
                                      # assertion in §4 (scrape, cache refresh, InfluxDB write
                                      # path) rides that network. cilium-1.20.2 already lists
                                      # every open executable plan for exactly this reason and
                                      # explicitly dropped its unpoller-v5.2.5 ref on
                                      # 2026-09-16 when that plan executed; this is the
                                      # successor it would re-add.
security_ref: null                    # version-currency driver only; no vulnerability content.
                                      # The TLS-posture reference in §1.3 is an ALREADY-ACCEPTED
                                      # risk (F-cafe8865 / AR-114), cited as a premise of the
                                      # base-image analysis, not a driver for this plan.
capability_change: false              # dependency refresh + base-image rebuild. No new opt-in,
                                      # no config key, no user-visible behaviour change. The
                                      # rendered manifest delta is ONE image tag.
rollback_class: git-revert
finding_refs: [F-0e3c2de5]            # the plan-lane finding that OWNS this retarget: "unpoller
                                      # v5.2.6 published 2026-09-16 00:40Z, 3 h before the
                                      # nightly window: the vetted plan targets v5.2.5, so the
                                      # window executed v5.2.5 as reviewed and left v5.2.6 for
                                      # the next cycle". This plan is that next cycle.
                                      # NOT listed: F-23119c27 (the v5.2.4 → v5.2.5 version
                                      # finding) — already satisfied by b0ffb944, it is
                                      # script-produced and auto-closes on the next sweep.
                                      # A v5.2.5 → v5.2.6 version finding does not exist yet;
                                      # the next sweep's version check will file one.
status: draft
window: null
premises:
  - id: live-image-still-v5.2.5
    why: >-
      `current:` claims v5.2.5 (shipped last night by plan unpoller-v5.2.5,
      commit b0ffb944). If the cluster already moved — e.g. the operator
      narrowed the `*unpoller*` deny rule to `max: patch` (§1.4) and Step 0's
      direct-bump lane landed v5.2.6 on its own — this plan is a no-op: verify
      per §4 and retire it, do not execute.
    run: kubectl get deploy -n monitoring unpoller -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: ghcr.io/unpoller/unpoller:v5.2.5
  - id: git-pin-still-v5.2.5
    why: >-
      Same premise, git side. The rollout is one line in helmrelease.yaml; if
      main already carries v5.2.6 the §3.2 edit produces an empty diff and the
      §5 revert target is wrong.
    run: "git show HEAD:kubernetes/apps/monitoring/unpoller/app/helmrelease.yaml | grep -c 'tag: v5.2.5'"
    expect_exact: "1"
  - id: chart-still-2.4.0
    why: >-
      The entire "image-only is safe" argument (§1.1) is that chart 2.4.0 is a
      version-agnostic wrapper already vetted twice. A different chart version
      means different templates and this plan's analysis is void — and per
      F-a2cd7a11 the chart leg moves in a SEPARATE lane, so it can change
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
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/unifi-controller-rate-limit.md
  - docs/sops/monitoring.md
  - docs/sops/auto-update.md
generated: "2026-09-17"
---

# unpoller: image v5.2.5 → v5.2.6 (image-only patch, chart stays 2.4.0)

## 1) Summary & why held

### 1.1 What changes

**One line**: `image.tag: v5.2.5 → v5.2.6` in
`kubernetes/apps/monitoring/unpoller/app/helmrelease.yaml`.

**Which leg moves — state it explicitly (F-a2cd7a11).** unpoller's chart and
image move in two independent lanes, so a chart bump can land days apart from an
image bump and split the pair. **This plan moves the IMAGE leg ONLY.** The chart
stays `2.4.0`, the `HelmRepository` stays on HTTP, and no chart value changes.
Live today and after this plan: chart `2.4.0` + image `v5.2.6`. The chart leg is
deliberately parked — `flux-oci-chart-sources` §3.5 blocks unpoller's OCI
migration precisely because it would force a chart upgrade in the same commit.
No `upConfig` (secret) edit. No policy edit.

### 1.2 Upstream evidence (v5.2.6, published 2026-09-16 00:40:46Z)

GitHub `compare/v5.2.5...v5.2.6` → `status: ahead`, **4 commits, 3 files**
(re-measured 2026-09-17, independently of the window agent's 2026-09-16 01:40Z
measurement recorded on F-0e3c2de5 — **the two agree exactly on the shape**):

| File | Delta | Effect on us |
|---|---|---|
| `Dockerfile` | `+1/-1` — PR #1091 `build(docker): bump distroless base to static-debian13` | The only non-dependency change. Assessed in §1.3. |
| `go.mod` | `+6/-6` — PR #1089 `build(deps): bump the all group across 1 directory with 4 updates` | Dependency refresh; no functional surface. |
| `go.sum` | `+12/-12` — same PR | Checksums for the above. |

**NONE of the review-sensitive paths changed**, re-verified against the file
list of the compare: `pkg/influxunifi/` (InfluxDB tag/field schema),
`pkg/promunifi/` (Prometheus metric names, the scrape-cache config contract) and
`examples/up.conf.example` (the config contract). There is **no Go source change
at all** in this release — the binary differs only by its recompiled
dependencies and its base layer.

Consequences, each of which the v5.2.5 review already established and this delta
cannot have moved:

- **No metric rename.** `prometheusrule.yaml`'s nine `unpoller_*` selectors
  (including the `UnifiMetricsAbsent` guard, `absent(unpoller_device_uptime_seconds)`
  for 15m) keep matching. All five in-repo dashboards are Prometheus-datasource
  — measured 2026-09-17: **118 `"type": "prometheus"`, zero `"influxdb"`** across
  `app/dashboards/*.yaml`.
- **No InfluxDB schema change.** The 21 measurements in bucket `default`
  (`uap`, `uap_radios`, `uap_vaps`, `usw`, `usw_ports`, `usg`, `clients`,
  `wan`, …) keep their tag/field names, so the Grafana `unpoller-influxdb`
  datasource and any operator-built InfluxDB panels need no repointing.
- **No config-contract change.** The one key whose type changed in v5.2.5
  (`[prometheus] interval`, where an explicit `0` now disables the scrape cache)
  is untouched here, and our config sets `"2m"` explicitly — asserted in §2.5.

### 1.3 The distroless base change — the one novel element, MEASURED not assumed

**First, a correction to the finding record.** F-0e3c2de5 records the base move
as `static-debian12 -> static-debian13`. The actual Dockerfile diff is
`static-debian11 -> static-debian13`:

```
-FROM gcr.io/distroless/static-debian11
+FROM gcr.io/distroless/static-debian13
```

and the upstream commit message gives the reason: *"Debian 11 (bullseye) has
reached end of life, so the gcr.io/distroless/static-debian11 base image no
longer receives security updates. Move to static-debian13 (trixie), which is
published for every platform the release targets."* So the jump is **two Debian
majors, not one** — a bigger move than the finding implies, which is why it was
checked rather than waved through. (Repo correction filed in the dispatch report;
the finding text is not edited by this plan.)

**Why a distroless major matters at all:** `gcr.io/distroless/static-*` ships the
CA trust store, and a base swap replaces the `ca-certificates` package — newer
bundles *remove* distrusted and expired roots. On a component that talks TLS to
the UniFi controller, a silently-emptied or silently-changed trust store is a
real failure mode, and it would present as "green pod, no metrics".

**Three measurements, taken 2026-09-17, that close it:**

1. **The trust store exists in BOTH bases, at the same path.** Listing the tar
   entries of every layer of `gcr.io/distroless/static-debian11` and
   `static-debian13` (linux/amd64) returns `etc/ssl/certs/ca-certificates.crt`
   in each. The bundle is not lost by the move; only its contents are newer.
2. **No code path in our deployment consults that trust store.** The config has
   exactly three sections — `[unifi]`, `[prometheus]`, `[influxdb]` — and
   exactly two URLs: the controller over `https` and InfluxDB over plaintext
   `http` to an in-cluster Service (`influxdb-influxdb2.databases`, port 80).
   The controller client runs with TLS verification **disabled** — a
   long-standing operator-accepted posture recorded on **F-cafe8865 (AR-114)**
   and already published in `docs/sops/unifi-controller-rate-limit.md` §3 — which
   the live v5.2.5 pod prints at startup:
   `=> URL: https://<controller> (verify SSL: false, timeout: 1m0s)`.
   A client that does not validate never reads the bundle; a plaintext client
   never opens TLS. **Both TLS-relevant paths are therefore insensitive to the
   CA-bundle contents by construction**, which is what makes this base major
   low-risk HERE and would NOT make it low-risk on a component that verifies.
3. **The runtime contract of the image is byte-identical apart from layers.**
   Comparing the amd64 image configs of both tags from ghcr:

   | | v5.2.5 | v5.2.6 |
   |---|---|---|
   | `User` | `'0'` | `'0'` |
   | `Entrypoint` | `/usr/bin/unpoller` | `/usr/bin/unpoller` |
   | `SSL_CERT_FILE` | `/etc/ssl/certs/ca-certificates.crt` | `/etc/ssl/certs/ca-certificates.crt` |
   | layers | 13 | 15 (base 11 → 13 layers) |
   | created | 2026-09-12T22:55:31Z | 2026-09-16T00:40:12Z |

   The `User` row is the one that could have bitten: our HelmRelease
   deliberately does NOT set `runAsNonRoot`/`runAsUser` (the comment in
   `helmrelease.yaml` explains why — the declared USER could not be read at
   hardening time), and it DOES set `readOnlyRootFilesystem: true`. A base that
   changed the declared uid could have produced `CreateContainerConfigError`
   or a container unable to read its own config. It did not change.

**Residual risk after those three:** the recompiled binary carries new
dependency versions, and the base carries a new libc-free layer set. Neither is
provable from metadata — which is exactly what §4 measures at runtime, on the
running pod, rather than asserting here.

### 1.4 Why it was held — and the honest verdict

The `*unpoller*` deny rule in `runbooks/auto-update-policy.yaml` carries **no
`max:` key** (re-read 2026-09-17, unchanged), and `coverage.py::deny_rule_for`
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
the same verdict the reviewed v5.2.5 plan reached, for the same rule, one release
earlier. `risk: low`. The plan is written anyway because the human / window agent
decides, not the planner.

**Deny-rule note for the operator (NOT edited by this plan).** The v5.2.5 plan
recommended narrowing `*unpoller*` to `max: patch` and rewriting the reason; that
has **not** happened (verified 2026-09-17 — the rule is byte-identical and still
names `v5.2.4` as the pinned tag, now two releases stale). The facts that bear on
it are unchanged and are recorded in that plan's history (`git show
f3869634^:runbooks/maintenance/plans/unpoller-v5.2.5.md` §1), in summary: no glob
can separate the image leg from the chart leg (`assign_lane()` keys on the
component name), the chart has never shipped a patch release so `max: patch`
opens image patches only, and the newer OCI charts declare appVersions BELOW our
pin. **If the rule is narrowed before this plan runs**, Step 0's direct-bump lane
will ship v5.2.6 on its own, premises `live-image-still-v5.2.5` /
`git-pin-still-v5.2.5` will FAIL, and the right action is to run §4 against the
already-landed bump and retire this file — not to execute it.

### 1.5 Derived execution class

`capability_change: false`, `rollback_class: git-revert`, `needs_reboot: false`,
`shared: []`, `risk: low` → satisfies `auto-night` in
`runbooks/autonomy-policy.yaml` (`require` all three, `forbid_shared:
[storage, longhorn]`, `forbid_risk: [high]`). Confirm with
`.venv/bin/python3 runbooks/maintenance-plan.py --open`; the plan does not claim
a class.

## 2) Pre-checks

1. **Premises pass mechanically** (the gate refuses the plan otherwise):
   ```bash
   .venv/bin/python3 runbooks/plan-premises.py unpoller-v5.2.6 --require-premises
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
   for t in v5.2.5 v5.2.6; do echo "== $t"; curl -sI -H "Authorization: Bearer $TOKEN" \
     -H "Accept: application/vnd.oci.image.index.v1+json" \
     "https://ghcr.io/v2/unpoller/unpoller/manifests/$t" | grep -iE '^HTTP|docker-content-digest'; done
   # 2026-09-17: v5.2.5 → 200, sha256:123a42e6…   v5.2.6 → 200, sha256:b6912acc…
   # (v5.2.5 digest matches the imageID on the LIVE pod — so the rollback target
   #  in §5 is the exact artifact that has been serving since 2026-09-16 01:48Z.)
   ```
4. **Re-resolve the target** — a plan is a snapshot and unpoller ships fast
   (v5.2.0 → v5.2.6 in 16 days; v5.2.6 itself landed 3 h before the window that
   would have taken it, which is why F-0e3c2de5 exists). If a newer `v5.2.x`
   exists at execution:
   ```bash
   curl -s "https://api.github.com/repos/unpoller/unpoller/releases?per_page=10" \
     | python3 -c "import sys,json;[print(r['tag_name'],r['published_at'][:10]) for r in json.load(sys.stdin) if r['tag_name'].startswith('v5.')]"
   # for any newer tag N:
   curl -s "https://api.github.com/repos/unpoller/unpoller/compare/v5.2.6...N" \
     | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['status'],d['total_commits']);[print(f['status'],f['filename']) for f in d['files']]"
   ```
   `identical` / 0 commits → a re-tagged rebuild; take N and this analysis
   carries over. Real commits → re-run the §1.2 review for the delta before
   bumping, paying attention to `pkg/influxunifi/` (schema), `pkg/promunifi/`
   (metric names, config keys) and `examples/up.conf.example` (config contract).
   **Anything touching those beyond a one-liner is a new plan, not a retarget.**
   A `Dockerfile` base change alone is a retarget, but re-run §1.3's three
   measurements against the new base before taking it.
5. **The ONE config key whose contract changed in v5.2.5 is still explicit and
   positive**, and the TLS posture §1.3 depends on is unchanged. Print counts
   only — never the config itself:
   ```bash
   S=$(mktemp); sops -d kubernetes/apps/monitoring/unpoller/app/secret.sops.yaml > "$S"
   grep -cE '^[[:space:]]*interval = "2m"' "$S"    # expect 2 (prometheus + influxdb)
   grep -cE '^[[:space:]]*interval = "?0'  "$S"    # expect 0 — nobody disabled the cache
   grep -cE '^[[:space:]]*verify_ssl = false' "$S" # expect 1 — §1.3 measurement 2 holds
   grep -cE 'https://' "$S"                        # expect 1 — the controller, and only it
   rm -f "$S"
   ```
   If `verify_ssl` has become `true` since this plan was written, **stop**:
   §1.3's argument that the CA bundle is off the live path no longer holds, and
   the base-major bump needs a fresh assessment (a trust-store regression would
   then present as a total loss of UniFi metrics).
6. **Baselines for §4 — MEASURE THEM NOW, in this session. Do not reuse the
   numbers below.** They are this plan's authoring measurements (2026-09-17
   01:58Z / 02:01Z) and are recorded only to show the expected magnitude and to
   justify the §4.4 band:
   ```bash
   kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 >/dev/null 2>&1 & PF=$!
   sleep 3
   q(){ echo -n "$1 => "; curl -s --data-urlencode "query=$1" http://localhost:9090/api/v1/query \
        | python3 -c "import sys,json;print([r['value'][1] for r in json.load(sys.stdin)['data']['result']])"; }
   q 'up{job="unpoller"}'                                   # [1]
   q 'count(unpoller_site_adopted)'                         # [3]
   q 'count(unpoller_device_uptime_seconds)'                # [10]
   q 'count({__name__=~"unpoller_.*"})'                     # [7607] then [7605] 3 min later
   q 'unpoller_prometheus_cache_age_seconds'                # [89.6] then [89.5]
   q 'unpoller_prometheus_refresh_failures_total'           # [0]
   kill $PF 2>/dev/null
   kubectl -n monitoring get pod -l app.kubernetes.io/name=unpoller \
     -o jsonpath='{.items[0].status.containerStatuses[0].imageID}{"\n"}'   # §4.1 must DIFFER
   ```
   **Why re-measuring is mandatory, with the evidence:** the v5.2.5 plan recorded
   `count({__name__=~"unpoller_.*"}) = 7953` on 2026-09-15. Two days later the
   same query returns **7607 — a 4.4% drift**, which would blow a ±2% band on
   its own and fail a healthy exporter. The series population tracks how many
   wireless clients are associated, so it moves with the household, not with the
   software. Over a SHORT horizon it is tight: measured over the last 6 h,
   `min_over_time` 7555 / `max_over_time` 7668 (±0.75% around ~7610), and two
   samples 3 min apart differed by 2 series. That is what makes a ±2% band
   against a SAME-SESSION baseline both meaningful and passable.
7. **InfluxDB write-path baseline** (cheap, and §4.5 compares against it). The
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
     -d 'from(bucket:"default") |> range(start:-30m) |> filter(fn:(r)=>r._measurement=="uap_radios") |> keep(columns:["_time"]) |> sort(columns:["_time"],desc:true) |> limit(n:1)'
   kill $PF 2>/dev/null
   # 2026-09-17 02:00Z baseline: newest uap_radios _time = 2026-09-17T02:00:53Z
   # (org `influxdata`, bucket `default`, measurement `uap_radios` — all three
   #  verified to exist at authoring time, alongside 20 sibling measurements.)
   ```
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
   runbooks/update-marker.sh add unpoller monitoring 1 "v5.2.5->v5.2.6 image patch (plan unpoller-v5.2.6)"
   ```
2. **Bump the tag** — one line in
   `kubernetes/apps/monitoring/unpoller/app/helmrelease.yaml`. Dry-tested on a
   scratch copy on macOS (BSD sed) at authoring time; the resulting diff is
   exactly:
   ```
   50c50
   <       tag: v5.2.5
   ---
   >       tag: v5.2.6
   ```
   ```bash
   sed -i '' 's/^      tag: v5\.2\.5$/      tag: v5.2.6/' kubernetes/apps/monitoring/unpoller/app/helmrelease.yaml
   grep -n 'tag: v5\.2\.' kubernetes/apps/monitoring/unpoller/app/helmrelease.yaml   # exactly one line, v5.2.6
   grep -c 'tag: v5.2.6' kubernetes/apps/monitoring/unpoller/app/helmrelease.yaml    # exactly 1
   ```
   Then add ONE line to the comment block directly above the tag, after the
   existing "2026-09-16: v5.2.4 -> v5.2.5 …" paragraph, so the next reader sees
   the lineage without git archaeology (replace `XX` with the execution day —
   the stub is a placeholder, not a value):
   ```
         # 2026-09-XX: v5.2.5 -> v5.2.6 image patch (plan unpoller-v5.2.6): dependabot
         # go.mod/go.sum group + distroless base static-debian11 -> static-debian13
         # (bullseye EOL). No Go source change; no metric rename, no InfluxDB schema
         # change, no config-contract change. Chart still 2.4.0.
   ```
   Do NOT touch `runbooks/auto-update-policy.yaml` in this plan — the rule
   narrowing is the operator's separate, code-reviewed decision (§1.4).
3. **Commit, shared-worktree safe** (`git commit --only`, never `git add -A` —
   other sessions commit into this same index, and `runbooks/state/active-updates.json`
   is routinely dirty from step 1 and from other agents' markers):
   ```bash
   git fetch origin main && git merge --ff-only origin/main
   git commit --only kubernetes/apps/monitoring/unpoller/app/helmrelease.yaml \
     -m "chore(unpoller): image v5.2.5 -> v5.2.6 on chart 2.4.0 (plan unpoller-v5.2.6)"
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
   agent's contract requires. **`F-0e3c2de5` is `authored_by: policy-cli`, not a
   script producer — it will NOT auto-close.** Close it by hand in the same turn,
   citing the bump commit:
   ```bash
   runbooks/policy-cli.py finding close F-0e3c2de5 --commit <sha>
   ```

## 4) Verification

`Ready=True` proves nothing here — a running unpoller that stopped emitting
looks identical to a healthy one, and that is the documented failure mode of
this exact component (the chart-Service trap, §1 premises). Wait **≥ 5 min**
after the new pod is Ready (60s scrape + 2m cache refresh), then:

1. **New bytes are running.** Tag is `ghcr.io/unpoller/unpoller:v5.2.6` AND the
   pod's `imageID` DIFFERS from the §2.6 baseline (it should carry the v5.2.6
   index digest `sha256:b6912acc…` from §2.3, or its amd64 child — all three
   nodes are amd64):
   ```bash
   kubectl -n monitoring get pod -l app.kubernetes.io/name=unpoller \
     -o jsonpath='{.items[0].spec.containers[0].image}{"  "}{.items[0].status.containerStatuses[0].imageID}{"\n"}'
   ```
   **FAIL signature:** an unchanged `imageID` means `IfNotPresent` served a
   cached layer set under a moved tag, and everything below would be measuring
   v5.2.5.
2. **The rebuilt binary identifies itself as v5.2.6, on the FRESH pod.** This is
   the assertion that separates "the tag moved" from "the new binary runs", and
   it matters more than usual here because the Go source is unchanged — the
   version string is one of the few in-process differences the base rebuild
   carries:
   ```bash
   kubectl -n monitoring logs -l app.kubernetes.io/name=unpoller --tail=200 | grep -iE 'Starting Up'
   # MUST show:  [INFO] UniFi Poller v5.2.6 Starting Up! PID: 1
   # FAIL if it shows v5.2.5 — the rollout did not replace the process.
   ```
3. **The config contract survived the rebuild** — read PROMPTLY on the fresh
   pod, it is a startup line. `pkg/promunifi/collector.go` `Run()` logs one of
   two mutually exclusive lines; the live v5.2.5 pod printed the first at
   2026-09-16T01:48:54Z, and since `pkg/promunifi/` is untouched by this delta
   (§1.2) the text must be identical:
   ```bash
   kubectl -n monitoring logs -l app.kubernetes.io/name=unpoller --tail=200 | grep -iE 'scrape cache'
   # MUST show:  Prometheus scrape cache enabled, refresh interval: 2m0s
   # FAIL if:    Prometheus scrape cache disabled; /metrics fetches live   (our "2m" parsed as 0)
   # FAIL if:    ... refresh interval: 1m0s                                 (parsed as nil → default)
   ```
   Also confirm the TLS posture §1.3 rests on is what the new binary actually
   does — a base-image trust-store change would show up here if it mattered:
   ```bash
   kubectl -n monitoring logs -l app.kubernetes.io/name=unpoller --tail=200 | grep -iE 'verify SSL'
   # MUST show:  => URL: https://<controller> (verify SSL: false, timeout: 1m0s)
   # FAIL if the controller block is absent or followed by x509/certificate errors
   #      — that is the CA-bundle regression this base bump could theoretically cause.
   ```
4. **CONTENTS ASSERTION (the scrape still delivers the same population)** —
   measured by the §2.6 `q` helper, compared to the SAME-SESSION baseline, all
   evaluated ≥ 5 min after Ready so the window starts after the change:
   - `up{job="unpoller"}` == `1`
   - `count(unpoller_site_adopted)` == baseline (3 at authoring)
   - `count(unpoller_device_uptime_seconds)` == baseline (10 at authoring — the
     `UnifiDeviceOffline` rule's comment independently records 10 devices)
   - `count({__name__=~"unpoller_.*"})` within **±2% of the §2.6 baseline** AND
     **≥ 6000 absolute**. The band is justified in §2.6 (6 h spread ±0.75%); the
     absolute floor is the part that cannot be argued away by drift and catches
     the "green and empty" failure — a collapsed exporter returns 0 or single
     digits, not 6000.
   - `count(count_over_time(unpoller_site_adopted[5m]))` > 0 at that point, so
     the assertion is reading post-change samples rather than stale ones.

   **This is the check that fails if the exporter came up green and empty** —
   the chart-Service trap, a metric rename, or a scrape-path break all land
   here. A count materially ABOVE baseline is also a finding (in v5.2.5 the
   benign cause was locate-mode devices newly exported; this delta has no such
   mechanism, so investigate rather than accept).
5. **CONTENTS ASSERTION (the background cache poller runs at OUR interval):**
   `unpoller_prometheus_cache_age_seconds` EXISTS and is `< 150` on two samples
   3 min apart. Measured over the last 6 h at authoring, this gauge peaks at
   **90.3 s** against a 2m refresh, so 150 leaves real headroom and still trips
   on a stalled poller. **The failure signature is `absent(...)`, not a large
   number**: `cacheAgeGauge()` is only registered inside
   `if u.scrapeCacheEnabled()`, so a cache taken as disabled makes the series
   vanish entirely rather than grow. Also
   `increase(unpoller_prometheus_refresh_failures_total[10m])` == 0.
6. **CONTENTS ASSERTION (the InfluxDB write path still advances):** re-run the
   §2.7 Flux query — the newest `uap_radios` `_time` must be **NEWER** than the
   §2.7 baseline timestamp. Tag/field names are unchanged by this release
   (§1.2), so nothing needs repointing; a frozen timestamp would mean the write
   path broke, which §1 says cannot happen from this delta — **which is exactly
   why it is checked.** This is the second independent output of the same
   process, so it distinguishes "Prometheus scrape broke" from "the poller
   stopped polling".
7. `UnifiMetricsAbsent` (`absent(unpoller_device_uptime_seconds)`, `for: 15m`)
   and `UnifiControllerUnreachable` are NOT firing 15 min after Ready; the
   in-repo Grafana UniFi dashboards render data past the rollout time, not a
   flat line ending at it.

## 5) Rollback

One `git revert` of the §3.3 commit restores `image.tag: v5.2.5`:

```bash
git revert <sha>
git push origin main
```

The rollback target is unusually well-proven here: v5.2.5 is published
(§2.3 confirmed HTTP 200, digest `sha256:123a42e6…`), and that exact digest is
the `imageID` the live pod has been running since 2026-09-16T01:48:49Z with 0
restarts — this is a return to a state observed healthy for a full day, not to a
theoretical one.

Then let Flux roll the Deployment back and confirm §4.1 shows `v5.2.5`, §4.2
shows `UniFi Poller v5.2.5 Starting Up!`, and §4.4–4.6 pass again.

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
  the nine `unifi.*` alert rules go blind (the `UnifiMetricsAbsent` guard fires
  after 15m, which is the intended loud failure), and the 21 InfluxDB UniFi
  measurements freeze. **No workload, gateway, storage or auth path depends on
  unpoller, and nothing depends on it for recovery** — it is a leaf exporter.
- **Shared infra: none perturbed**, hence `shared: []` (justified in the
  frontmatter). unpoller continues writing to the shared influxdb2 (`databases`
  ns, bucket `default`) with an unchanged schema and restarts nothing shared.
  §4.6 checks that write path anyway because it is cheap, and because the v5.1.0
  plan taught that "the schema did not change" is a claim, not a check.
- **The off-cluster surface it DOES touch: the UniFi controller API.** The
  rollout is chart-default `RollingUpdate` on 1 replica with no PVC, so for a few
  seconds two pollers authenticate against the gateway concurrently. At a 2m poll
  cadence that is a single extra login round, far under the threshold that caused
  the 429 lockout (`docs/sops/unifi-controller-rate-limit.md`: ~1 login/min at
  2m vs ~4/min at 30s). Acceptable; no `Recreate` needed (no RWO volume). **Do
  not "fix" this by enabling the chart's PodMonitor** — that is the duplicate-
  scrape path the premises forbid.
- **Same-namespace / same-instrument plans (checked against
  `maintenance-plan.py --open`, 2026-09-17):**
  - `kube-prometheus-stack-91.4.0` (vetted, window null) — **hard conflict, in
    `conflicts_with`**, and its own §6 asks any successor unpoller plan to re-add
    it. Never the same window. If an operator overrides that, run unpoller
    **fully before** kps (complete §4 including the ≥5-min settle) or **fully
    after** kps's own verification has passed — never interleaved.
  - `prometheus-crd-ownership` (vetted, window null) — **in `conflicts_with`**;
    it touches the CRD behind this plan's only scrape path. Expected
    perturbation is zero (its §4.2 asserts the CRDs are unchanged); the
    exclusion exists so that if it is ever non-zero, the damage does not get
    misattributed to this image bump and revert it needlessly.
  - `cilium-1.20.2` (draft, window null) — **in `conflicts_with`**; a CNI roll
    restarts the network every §4 assertion rides on.
  - `otel-operator-0.21.0` — **gone, and deliberately not listed.** It executed
    during the nightly 2026-09-17 window (commit `9a35168f`) and was retired the
    same night (`37f7c7a6`), while this plan was being written; there is no plan
    file left to conflict with. It was never a constraint anyway: it rolls the
    otel daemon-collector DaemonSet, which does not scrape unpoller —
    unpoller's path is ServiceMonitor → Prometheus, which it does not restart.
  - `edot-collector-0.161.0` (draft, window null, `shared: [monitoring]`) —
    **not a conflict.** Read at authoring: it rolls `deployment/edot-collector`
    and its own §4 reads `otelcol_*` from this same Prometheus, but it restarts
    neither Prometheus nor anything on unpoller's scrape path, and its
    `conflicts_with` does not name unpoller. The two `touches.shared` sets do
    not even intersect (this plan declares `[]`). Sharing a window is
    acceptable, in either order.
  - **A collector roll of either kind causes a ~10-30 s per-node pod-log gap in
    Elasticsearch.** Never read ES log continuity as an unpoller signal on a
    night one runs — every assertion in §4 reads Prometheus or InfluxDB, which
    a collector restart does not perturb.
  - `flux-oci-chart-sources` §3.5 explicitly parks unpoller (migrating it to OCI
    would force a chart upgrade in the same commit, because 2.4.0 is absent from
    the OCI repo). This plan does not move `HelmRepository/unpoller`, so there is
    no ordering relation — but it is the reason the chart leg stays put.
- **Pre-existing noise, NOT this plan's scope — do not "fix" it mid-window:** the
  live log carries periodic `[INFO] Re-authenticating to UniFi Controller …`
  lines driven by intermittent `401`/`500` responses from the UDM-Pro's Network
  app (the same flaky control plane as the JVM-GC pattern). The scrape cache
  preserves the last snapshot across them, and
  `unpoller_prometheus_refresh_failures_total` is 0. A re-auth line after the
  rollout is **not** a regression; only a sustained failure to poll (cache age
  growing past 150 s, §4.5) is.
- **Deny rule:** untouched by this plan (§1.4 gives the operator the facts). If
  it is narrowed first and Step 0 lands the bump, the premises fail on purpose —
  run §4 against the landed bump and retire this plan, do not re-run it.
