---
plan_id: unpoller-v5.2.5
component: unpoller
pr: null                              # no open Renovate PR (`gh pr list --search unpoller`
                                      # empty, 2026-09-15); the item reached the PLAN lane via
                                      # coverage.py's no-PR direct-bump path, blocked by the
                                      # `*unpoller*` deny rule — see §1
kind: image
current: "v5.2.4"                     # live on deployment/unpoller, verified 2026-09-15
target: "v5.2.5"                      # released 2026-09-12; ghcr manifest HEAD 200
update_type: patch
risk: low                             # image-only patch on an unchanged chart; no metric
                                      # rename, no InfluxDB schema change, no config-format
                                      # change for OUR config — the hold is a glob wider than
                                      # its reason (§1), not a property of this release
est_duration_min: 15                  # commit+push ~2, reconcile+rollout ~3, settle ≥5 for the
                                      # contents assertions (60s scrape, 2m cache refresh)
needs_reboot: false
touches:
  namespaces: [monitoring]
  resources:
    - helmrelease/unpoller
    - deployment/unpoller
    - "ghcr.io/unpoller/unpoller"
  shared: []                          # unpoller keeps writing to the shared influxdb2 in
                                      # `databases` exactly as it does today — this patch
                                      # changes NO tag/field name (§1) and restarts nothing
                                      # shared, so nothing is perturbed. Listed as [] on
                                      # purpose; §6 explains the write-path continuity check.
depends_on: []
conflicts_with:
  - kube-prometheus-stack-91.4.0      # HARD: §4.3-4.4 read THIS Prometheus over a ≥5-min
                                      # settle, and kps-91.4.0 restarts it (2-5 min blind
                                      # spot) — a replaying Prometheus reads "no data" and
                                      # would trigger a needless unpoller revert. Both plans
                                      # are AUTO-NIGHT with window null, and only this FIELD
                                      # is honoured by window-scheduler.py (the
                                      # shared:[monitoring] overlap is a post-placement
                                      # warning) — 2026-09-15 review. otel-operator-0.21.0
                                      # (same namespace) is NOT a conflict: serialize per
                                      # §6, either order. grafana-chart-13.2.3, once named
                                      # here, is `superseded` since 2026-09-14 — not a
                                      # constraint.
security_ref: null                    # version-currency driver only; no vulnerability content
capability_change: false              # scraper internals + a bug fix; no new opt-in enabled,
                                      # no user-visible behaviour change
rollback_class: git-revert
finding_refs: [F-23119c27]            # the sweep's version finding for exactly this bump
                                      # (section version, severity monitor, producer script —
                                      # it auto-closes when the version check next sees v5.2.5)
status: vetted   # REVIEWED 2026-09-15 (plan-reviewer fan-out, corrections applied in c36388bc)
window: "nightly:2026-09-16"   # AUTO-ASSIGNED 2026-09-15 by window-scheduler (AUTO-NIGHT; category graduated — eligible for unattended execution)
premises:
  - id: live-image-still-v5.2.4
    why: >-
      `current:` claims v5.2.4. If the cluster already moved — e.g. the operator
      narrowed the `*unpoller*` deny rule to `max: patch` (§1) and Step 0's
      direct-bump lane landed v5.2.5 before this plan ran — this plan is a
      no-op: verify per §4 and retire it, do not execute.
    run: kubectl get deploy -n monitoring unpoller -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: ghcr.io/unpoller/unpoller:v5.2.4
  - id: git-pin-still-v5.2.4
    why: >-
      Same premise, git side. The rollout is one line in helmrelease.yaml; if
      main already carries v5.2.5 the §3 edit produces an empty diff and the
      §5 revert target is wrong.
    run: "git show HEAD:kubernetes/apps/monitoring/unpoller/app/helmrelease.yaml | grep -c 'tag: v5.2.4'"
    expect_exact: "1"
  - id: chart-still-2.4.0
    why: >-
      The entire "image-only is safe" argument (§1) is that chart 2.4.0 is a
      version-agnostic wrapper we have already vetted. A different chart
      version means different templates and this plan's analysis is void.
    run: kubectl get helmrelease -n monitoring unpoller -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: "2.4.0"
  - id: helmrelease-ready
    why: "Do not stack a bump on top of an already-failing release."
    run: kubectl get helmrelease -n monitoring unpoller -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: chart-service-still-disabled
    why: >-
      `service.enabled: false` is what keeps the chart's own Service (port
      named `tcp`) from displacing our hand-written one (port named `http`,
      which the ServiceMonitor selects). If someone flipped it, every
      unpoller_* series would already be gone under a green HelmRelease and
      §4's baselines would be meaningless.
    run: kubectl get helmrelease -n monitoring unpoller -o jsonpath='{.spec.values.service.enabled}'
    expect_exact: "false"
  - id: chart-podmonitor-still-disabled
    why: >-
      A second scrape (the chart's PodMonitor at 30s) would double UniFi API
      load and duplicate every series, which would corrupt the count-based
      contents assertions in §4.3.
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
  - docs/sops/monitoring.md
  - docs/sops/auto-update.md
generated: "2026-09-15"
---

# unpoller: image v5.2.4 → v5.2.5 (image-only patch, chart stays 2.4.0)

## 1) Summary & why held

**What changes.** One line: `image.tag: v5.2.4 → v5.2.5` in
`kubernetes/apps/monitoring/unpoller/app/helmrelease.yaml`. Chart stays
`2.4.0`. No `upConfig` (secret) edit. No policy edit.

**Upstream evidence (v5.2.5, published 2026-09-12).** This is a REAL source
delta, not a re-tagged rebuild like v5.2.3→v5.2.4 was: GitHub
`compare/v5.2.4...v5.2.5` returns `status: ahead`, 7 commits, 39 files. Every
one of them was read for this plan:

| Change | What it does | Effect on us |
|---|---|---|
| PR #1086 `fix: honor scrape-cache disable and export locate-mode devices` (a) | `[prometheus] interval` becomes `*cnfg.Duration`. New contract: **omitted** → cache on at 60s; **explicit `0`** → cache DISABLED, `/metrics` fetches live; **> 0** used as-is; < 15s now only *warns* instead of clamping to 15s. | **None.** Our config sets `interval = "2m"` explicitly (verified from the decrypted secret, 2026-09-15). 120s > 0 and ≥ 15s, so v5.2.4 already used it as-is; v5.2.5 does the same. The only way this patch changes behaviour is a config that sets `0` — we do not. |
| PR #1086 (b) | Removes the `\|\| s.Locating.Val` guard in every output package (`promunifi`, `influxunifi`, `datadogunifi`, `otelunifi`), for UAP/UDM/UXG/USG/USW/PDU/UBB/UCI/UDB. Devices in LED **locate mode** were silently dropped from export; now they are exported like any adopted device. | **Fix, not a schema change.** No metric, label, tag or field is renamed. A device would only *gain* series while someone has "Locate" active in the UniFi UI (today: none). |
| PR #1087 `fix(promunifi): accept a bracketed IPv6 http_listen in the health check` | `DebugOutput()` (the `--health-check`/debug path) parses `http_listen` with `net.SplitHostPort` instead of `strings.Split(":")`. | **None.** Our `http_listen = "0.0.0.0:9130"` parses identically either way, and our liveness/readiness probes are `httpGet /` on 9130 — they never call this code. |
| dependabot: `google.golang.org/grpc` 1.83.1→1.83.2, "all group with 4 updates" | `go.mod`/`go.sum` only. | Runtime library refresh; no functional surface. |

**InfluxDB schema: unchanged.** `pkg/influxunifi/` is touched ONLY by the
one-line locate-guard removal above — no tag/field rename since v5.1.0 (which
b3cae4c1 already absorbed). The Grafana `unpoller-influxdb` datasource
(Flux, bucket `default`) and any operator-built InfluxDB panels need no
repointing. All five in-repo UniFi dashboards
(`app/dashboards/*.yaml`) are Prometheus-datasource (verified by grep: every
`"type"` is `prometheus`, zero `influxdb`), and no Prometheus metric name moves,
so `prometheusrule.yaml` (`unpoller_*` selectors, incl. the `UnifiMetricsAbsent`
guard) keeps matching.

**Why it was held — and the honest verdict.** The `*unpoller*` deny rule in
`runbooks/auto-update-policy.yaml` carries no `max:`, and
`coverage.py::deny_rule_for` blocks EVERY update_type for a rule without one
(`mx is None → block`). So the patch was blocked mechanically. But the rule's
*reason* is entirely about **chart** bumps: the pinned `image.tag` outranks
`appVersion`, so a chart bump would score as a safe minor and land unattended
while templating for v3, and chart templates change semantics between releases.
**An image-only patch under the same chart 2.4.0 does not engage that reason at
all** — the chart is untouched, the pin still outranks appVersion exactly as
before, and the three overrides that make image-only safe (`service.enabled:
false`, `podMonitor.enabled: false`, `dashboards.create: false`) are unchanged
and are asserted as premises above. This hold is a false positive of a glob
that is wider than its own justification. `risk: low`; the plan is written
anyway because the human/window agent decides, not the planner.

**Deny-rule note for the operator (NOT edited by this plan).** Whether to
narrow the rule is an operator decision; the facts that bear on it:

- **No glob can separate the image leg from the chart leg.** `assign_lane()`
  keys both on the component name (`key = comp` → `unpoller`), which is the
  same limitation `plans/README.md` "Known phantoms" records for authentik.
  So the only lever is `max:`.
- **`max: patch` would open image patches AND chart patches — and chart
  patches do not exist.** The chart's entire history is six versions
  (`2.11.2-Chart4/5/6`, `2.1.0`, `2.3.0`, `2.4.0`); it has never shipped a
  patch release. Chart minors (`2.5.0+`) stay held under `max: patch`, which
  is precisely what the rule's reason is about. This is the same narrowing
  applied to `*grafana*` on 2026-09-12 for the same "reason blocks more than it
  argues" defect.
- **Chart bumps are not even visible to coverage.py today.** Our
  `HelmRepository/unpoller` points at the HTTP index
  (`unpoller.github.io/helm-chart`), whose newest entry is still
  `2.4.0 → appVersion v3.5.0`. The newer charts live ONLY on OCI
  (`oci://ghcr.io/unpoller/helm-chart/unpoller`, 2.5.0–2.8.0) — see
  `runbooks/maintenance/plans/flux-oci-chart-sources.md` §3.5 (a PLAN, not an
  SOP — it is not under `docs/sops/`), which deliberately parks unpoller until
  a chart plan exists. Measured 2026-09-15: OCI chart 2.8.0 ships
  `appVersion: v5.2.3` (below our pin), and 2.5.0 declares `v5.3.0`, a tag
  that has no upstream release (newest is v5.2.5). The rule's own removal
  condition ("a chart ships appVersion ≥ the pinned tag AND its values diff is
  re-vetted") is therefore a matter for that future chart plan, not for this
  image patch.
- **Recommendation:** narrow `*unpoller*` to `max: patch` and rewrite the reason
  to say what is held (chart minor/major, image minor/major) and why patches
  are permitted, bump the policy version — a separate, code-reviewed commit.
  If that lands **before** this plan runs, Step 0's direct-bump lane will ship
  v5.2.5 on its own, premises `live-image-still-v5.2.4` / `git-pin-still-v5.2.4`
  will FAIL, and the right action is to run §4 against the already-landed bump
  and retire this file — not to execute it.

**Derived execution class.** `capability_change: false`, `rollback_class:
git-revert`, `needs_reboot: false`, `shared: []`, `risk: low` → satisfies
`auto-night` in `runbooks/autonomy-policy.yaml`. Confirm with
`.venv/bin/python3 runbooks/maintenance-plan.py --open`; the plan does not
claim a class.

## 2) Pre-checks

1. **Premises pass mechanically** (the gate refuses the plan otherwise):
   ```bash
   .venv/bin/python3 runbooks/plan-premises.py unpoller-v5.2.5 --require-premises
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
   for t in v5.2.4 v5.2.5; do echo "== $t"; curl -sI -H "Authorization: Bearer $TOKEN" \
     -H "Accept: application/vnd.oci.image.index.v1+json" \
     "https://ghcr.io/v2/unpoller/unpoller/manifests/$t" | grep -iE '^HTTP|docker-content-digest'; done
   # 2026-09-15: v5.2.4 → 200, sha256:e1fad2c2…  v5.2.5 → 200, sha256:123a42e6…
   ```
4. **Re-resolve the target** — a plan is a snapshot, and unpoller ships fast
   (v5.2.0→v5.2.5 in 12 days). If a newer `v5.2.x` exists at execution:
   ```bash
   curl -s "https://api.github.com/repos/unpoller/unpoller/releases?per_page=10" \
     | python3 -c "import sys,json;[print(r['tag_name'],r['published_at'][:10]) for r in json.load(sys.stdin) if r['tag_name'].startswith('v5.')]"
   # for any newer tag N:
   curl -s "https://api.github.com/repos/unpoller/unpoller/compare/v5.2.5...N" \
     | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['status'],d['total_commits']);[print(f['status'],f['filename']) for f in d['files']]"
   ```
   `identical` / 0 commits → a rebuild; take N and this analysis carries over.
   Real commits → re-run the §1 review for the delta before bumping, paying
   attention to `pkg/influxunifi/` (schema), `pkg/promunifi/` (metric names,
   config keys) and `examples/up.conf.example` (config contract). Anything
   touching those beyond a one-liner is a new plan, not a retarget.
5. **The ONE config key whose contract changed is set explicitly and positive**
   (§1 row 1). Print counts only — never the config itself:
   ```bash
   sops -d kubernetes/apps/monitoring/unpoller/app/secret.sops.yaml | grep -cE '^\s*interval = "2m"'   # expect 2 (prometheus + influxdb)
   sops -d kubernetes/apps/monitoring/unpoller/app/secret.sops.yaml | grep -cE '^\s*interval = "?0'    # expect 0 — nobody disabled the cache
   ```
6. **Baselines for §4** (record every number; measured 2026-09-15 in brackets):
   ```bash
   kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &
   q(){ curl -s --data-urlencode "query=$1" http://localhost:9090/api/v1/query | python3 -c "import sys,json;print([r['value'][1] for r in json.load(sys.stdin)['data']['result']])"; }
   q 'up{job="unpoller"}'                                   # [1]
   q 'count(unpoller_site_adopted)'                         # [3]
   q 'count(unpoller_device_uptime_seconds)'                # [10]
   q 'count({__name__=~"unpoller_.*"})'                     # [7953 at 02:xx, 7954 by 06:xx the same day — RE-RECORD, never copy]
   q 'unpoller_prometheus_cache_age_seconds'                # [< 150 — cache poller alive at our 2m]
   q 'unpoller_prometheus_refresh_failures_total'           # [0]
   kubectl -n monitoring get pod -l app.kubernetes.io/name=unpoller -o jsonpath='{.items[0].status.containerStatuses[0].imageID}{"\n"}'   # record — §4.1 must differ
   ```
   InfluxDB write-path baseline (optional but cheap; token from the decrypted
   secret's `auth_token`, never echoed):
   ```bash
   kubectl port-forward -n databases svc/influxdb-influxdb2 8086:80 &
   curl -s 'http://localhost:8086/api/v2/query?org=influxdata' -H "Authorization: Token $INFLUX_TOKEN" \
     -H 'Content-Type: application/vnd.flux' \
     -d 'from(bucket:"default") |> range(start:-15m) |> filter(fn:(r)=>r._measurement=="uap_radios") |> keep(columns:["_time"]) |> last(column:"_time")'
   ```
7. No in-flight reconcile on `monitoring`; no other plan mid-execution in the
   namespace (§6).

## 3) Steps

1. **Update marker** (cheap, recommended; a silence is NOT needed for the low
   tier per application-update.md Example A — the rollout is a RollingUpdate
   of a stateless 1-replica Deployment, so the scrape gap is at most one
   interval and `UnifiMetricsAbsent` needs 15m to fire):
   ```bash
   runbooks/update-marker.sh add unpoller monitoring 1 "v5.2.4->v5.2.5 image patch (plan unpoller-v5.2.5)"
   ```
2. **Bump the tag** — one line in
   `kubernetes/apps/monitoring/unpoller/app/helmrelease.yaml`:
   ```bash
   sed -i '' 's/^      tag: v5\.2\.4$/      tag: v5.2.5/' kubernetes/apps/monitoring/unpoller/app/helmrelease.yaml
   grep -n 'tag: v5\.2\.' kubernetes/apps/monitoring/unpoller/app/helmrelease.yaml   # exactly one line, v5.2.5
   ```
   Then add ONE line to the comment block directly above the tag, after the
   existing "2026-09-06: image-only major …" paragraph, so the next reader
   sees the lineage without git archaeology (replace `XX` with the execution
   day — the stub is a placeholder, not a value):
   ```
         # 2026-09-XX: v5.2.4 -> v5.2.5 image patch (plan unpoller-v5.2.5): scrape-cache
         # interval contract (explicit 0 now disables; ours is "2m", unaffected) + locate-mode
         # devices exported. No metric rename, no InfluxDB schema change. Chart still 2.4.0.
   ```
   Do NOT touch `runbooks/auto-update-policy.yaml` in this plan — the rule
   narrowing is the operator's separate decision (§1).
3. **Commit, shared-worktree safe** (`git commit --only`, never `git add -A`):
   ```bash
   git fetch origin main && git merge --ff-only origin/main
   git commit --only kubernetes/apps/monitoring/unpoller/app/helmrelease.yaml \
     -m "chore(unpoller): image v5.2.4 -> v5.2.5 on chart 2.4.0 (plan unpoller-v5.2.5)"
   git show --stat HEAD      # exactly ONE file
   git push origin main
   ```
4. **Let Flux reconcile on the webhook** — no manual `flux reconcile` by
   default. Watch the rollout:
   ```bash
   kubectl -n monitoring get pods -l app.kubernetes.io/name=unpoller -w
   ```
   Only if nothing has rolled after 10 min: check
   `flux get kustomization unpoller -n monitoring` shows the pushed revision;
   if the source is stale, `flux reconcile kustomization unpoller -n monitoring --with-source`.
5. **Close-out** after §4 passes: clear the marker
   (`runbooks/update-marker.sh clear unpoller`), delete this plan file in the
   close-out commit (`plans/README.md`: executed plans are deleted, git has
   the history), and record the execution via `autonomy-record.py` as the
   window agent's contract requires. `F-23119c27` is script-produced
   (`metadata.producer: script`) and auto-closes when the next sweep's version
   check no longer sees the gap — do not hand-close it; DO confirm it closed on
   the next sweep.

## 4) Verification

`Ready=True` proves nothing here — a running unpoller that stopped emitting
looks identical to a healthy one. Wait **≥ 5 min** after the new pod is Ready
(scrape 60s, cache refresh 2m), then:

1. **New bytes are running.** Tag is `ghcr.io/unpoller/unpoller:v5.2.5` AND
   the pod's `imageID` differs from the §2.6 baseline (it should carry the
   v5.2.5 index digest from §2.3 or its per-platform child):
   ```bash
   kubectl -n monitoring get pod -l app.kubernetes.io/name=unpoller \
     -o jsonpath='{.items[0].spec.containers[0].image}{"  "}{.items[0].status.containerStatuses[0].imageID}{"\n"}'
   ```
2. **Pod Ready, 0 restarts after 5 min, and the startup log proves the config
   contract survived the type change.** `pkg/promunifi/collector.go` `Run()`
   logs one of two lines at start. The `… cache enabled, refresh interval: %v`
   line already existed in v5.2.4 (v5.2.5 only changed its argument to
   `refreshInterval()`); the `… cache disabled; /metrics fetches live` line is
   NEW in v5.2.5. **Read it promptly on the FRESH pod** — it is a startup line,
   and on the 8-day-old v5.2.4 pod it had already rotated out of
   `--tail=3000` at review time (2026-09-15), so a late read proves nothing:
   ```bash
   kubectl -n monitoring logs -l app.kubernetes.io/name=unpoller --tail=200 | grep -E 'scrape cache'
   # MUST show:  Prometheus scrape cache enabled, refresh interval: 2m0s
   # FAIL if:    Prometheus scrape cache disabled; /metrics fetches live   (our "2m" parsed as 0 → rollback §5)
   # FAIL if:    ... refresh interval: 1m0s                                 (parsed as nil → default; config not honoured → rollback)
   ```
3. **CONTENTS ASSERTION (scrape still delivers the same population):**
   `up{job="unpoller"} == 1` — measured by the §2.6 `q` helper — AND
   `count(unpoller_site_adopted)` == baseline (3) AND
   `count(unpoller_device_uptime_seconds)` == baseline (10) AND
   `count({__name__=~"unpoller_.*"})` within ±2% of baseline (7953), all
   evaluated ≥ 5 min after Ready so the window starts after the change
   (`count(count_over_time(unpoller_site_adopted[5m])) > 0` at that point).
   This is the check that fails if the exporter came up green and empty. A
   count materially ABOVE baseline is also a finding (a device in locate mode
   newly exported — §1 row 2 — is the only benign cause; confirm in the UniFi
   UI).
4. **CONTENTS ASSERTION (the one behaviour this patch touches — the background
   cache poller runs at OUR interval):** `unpoller_prometheus_cache_age_seconds`
   EXISTS and is `< 150` on two samples 3 min apart — measured by the §2.6
   `q` helper, compared to the pre-change value. If the cache had been taken
   as disabled, this gauge is never registered (`cacheAgeGauge()` is only
   registered inside `if u.scrapeCacheEnabled()`), so `absent(...)` is the
   failure signature, not a large number. Also
   `increase(unpoller_prometheus_refresh_failures_total[10m]) == 0`.
5. **CONTENTS ASSERTION (InfluxDB write path still advances):** re-run the
   §2.6 Flux query — the newest `uap_radios` `_time` must be NEWER than the
   baseline. Tag/field names are unchanged by this release, so nothing needs
   repointing; a frozen timestamp would mean the write path broke, which §1
   says cannot happen from this delta — that is exactly why it is checked.
6. `UnifiMetricsAbsent` and `UnifiControllerUnreachable` are NOT firing 15 min
   after Ready; the in-repo Grafana UniFi dashboards render data past the
   rollout time, not a flat line ending at it.

## 5) Rollback

One `git revert` of the §3.3 commit restores `image.tag: v5.2.4` (tag still
published — §2.3 confirmed HTTP 200, digest `sha256:e1fad2c2…`):

```bash
git revert <sha>
git push origin main
```

Then let Flux roll the Deployment back and confirm §4.1 shows `v5.2.4`, and
§4.3–4.5 pass again. unpoller is a stateless scraper: nothing persistent to
restore, and the InfluxDB schema is identical on both sides of this patch, so
there is no mixed-key window to clean up. If Helm is ever wedged
`pending-upgrade` (not expected for a tag-only change): `helm rollback unpoller
<last-deployed-rev> -n monitoring --wait=false` then `flux reconcile
helmrelease unpoller -n monitoring --force` per application-update.md §11.
Clear the update marker either way.

## 6) Interference notes

- **Blast radius if wrong:** UniFi observability only — `unpoller_*` series
  stop, the `unifi.*` alert groups go blind (the `UnifiMetricsAbsent` guard
  fires after 15m, which is the intended loud failure), InfluxDB UniFi
  measurements freeze. No workload, gateway, storage or auth path depends on
  unpoller, and nothing depends on it for recovery.
- **Shared infra: none perturbed.** unpoller continues writing to the shared
  influxdb2 (`databases` ns, bucket `default`) with an unchanged schema and
  restarts nothing shared; `shared: []` is deliberate. §4.5 checks the write
  path anyway because it is cheap and because the previous unpoller plan
  taught that "the schema did not change" is a claim, not a check.
- **Same-namespace plans (live as of 2026-09-15):**
  - `kube-prometheus-stack-91.4.0` — **hard conflict, in `conflicts_with`.** It
    restarts Prometheus and Alertmanager; §4.3-4.4 need a stable scrape pipeline
    over a ≥5-min settle to mean anything, and a Prometheus replaying its WAL
    answers "no data", which reads as a regression and would trigger a needless
    §5 revert. Never the same window. If the operator overrides that, run
    unpoller **fully before** kps (complete §4 including the settle) or **fully
    after** kps's own verification has passed — never interleaved.
  - `otel-operator-0.21.0` — same namespace, so the scheduler will flag
    INTERFERENCE if co-slotted, but it is not on unpoller's scrape path
    (ServiceMonitor → Prometheus; the daemon collector does not scrape
    unpoller). Sharing a window is acceptable; **serialize**, either order.
  - `grafana-chart-13.2.3` — named in earlier drafts of this plan; `superseded`
    since 2026-09-14 and no longer a constraint.
  - `runbooks/maintenance/plans/flux-oci-chart-sources.md` §3.5 explicitly
    parks unpoller and this plan does not move `HelmRepository/unpoller`; no
    ordering relation.
- **Rollout mechanics:** chart-default `RollingUpdate`, 1 replica, no PVC —
  for a few seconds two pollers hit the UDM-Pro concurrently. At a 2m poll
  cadence that is a single extra API round, well under the 429 threshold that
  motivated the 60s ServiceMonitor. Acceptable; no `Recreate` needed (no RWO
  volume).
- **Pre-existing noise, NOT this plan's scope — do not "fix" mid-window:** the
  live log carries periodic `[INFO] Re-authenticating to UniFi Controller …`
  lines triggered by `401` on `stat/sitedpi` / `500` on `stat/sta` from the
  UDM-Pro's Network app (the same flaky control plane as the JVM-GC pattern in
  memory). The scrape cache preserves the last snapshot across them and
  `unpoller_prometheus_refresh_failures_total` is 0 over the pod's 8-day life.
  A re-auth line after the rollout is NOT a regression; only a sustained
  failure to poll (cache age growing past 150s, §4.4) is.
- **Deny rule:** untouched by this plan (§1 gives the operator the facts). If
  it is narrowed first and Step 0 lands the bump, the premises fail on purpose
  — retire this plan, do not re-run it.
