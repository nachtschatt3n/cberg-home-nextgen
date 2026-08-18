---
plan_id: unpoller-v3
component: unpoller
pr: null                              # no Renovate PR open (image lives in chart
                                      # values `image.tag`); held via sweep finding
                                      # F-a5ceabc1 (section: version) — direct bump.
kind: image+chart                     # BOTH halves, one window — see §1.4
current: "image v2.39.0 / chart 2.1.0"
target: "image v3.5.0 + chart 2.4.0"  # RETARGETED 2026-08-18 (twice). (a) image v3.4.1 ->
                                      # v3.5.0: published the same day, fixes an input-plugin
                                      # panic reported on our exact controller version (§1.3).
                                      # (b) chart 2.1.0 -> 2.4.0: this plan originally said
                                      # "upstream has published no v3-aware chart; 2.1.0 is
                                      # its newest". TRUE when written this afternoon, FALSE
                                      # hours later — chart 2.3.0 (appVersion v3.4.1) shipped
                                      # 2026-08-18 00:37Z and 2.4.0 (appVersion v3.5.0) at
                                      # 14:52Z. The chart must move WITH the image: 2.4.0
                                      # changes three templates our HelmRelease depends on
                                      # (§1.4), and a chart-only bump would put a v3-aware
                                      # chart on a v2 image.
update_type: major
risk: medium
est_duration_min: 45                  # +15m for the chart-side template changes (§1.4);
                                      # + a 24h metric-continuity soak before the
                                      # dashboards/alerts follow-up is judged
needs_reboot: false
touches:
  namespaces: [monitoring]
  resources:
    - helmrelease/unpoller                    # image.tag bump AND chart 2.1.0 -> 2.4.0
    - service/unpoller                        # chart 2.4.0 ADDS a Service template that
                                              # collides with our hand-written one (§1.4)
    - podmonitor/unifi-poller                 # chart 2.4.0 makes it conditional; the
                                              # postRenderer that deletes it can go (§1.4)
    - deployment/unpoller                     # rolls (RollingUpdate, stateless, no PVC)
    - "metric continuity: 5 provisioned Grafana dashboards (network-sites, uap/usg/usw/client-insights) — all query unpoller_* via the Prometheus datasource"
    - prometheusrule/unifi-alerts             # not edited, but its one LIVE rule changes meaning (see notes)
    - "SLO unifi-device-availability (sweep_history slo_definitions) — keyed on unpoller_device_uptime_seconds"
    - "influxdb output (databases/influxdb2) — write-only; measurement drift possible, no schema risk to other writers"
  shared: [unifi-controller]          # polls the UDM login endpoint; the per-IP
                                      # /api/auth/login 429 throttle is shared with
                                      # unifictl security-sweep checks — see
                                      # docs/sops/unifi-controller-rate-limit.md
depends_on: []
conflicts_with: [grafana-chart-11]    # scheduled fri-early:2026-08-21. Verification
                                      # here is "dashboard panels non-empty"; running
                                      # in the same window as a Grafana chart major
                                      # (which rolls Grafana + re-renders all dashboard
                                      # provisioning) makes an empty panel unattributable.
security_ref: null                    # version-currency driver, not a security fix
status: draft
window: "mon-early:2026-08-24"                 # SCHEDULED 2026-08-18: medium risk 30m; monitoring-only; conflicts_with grafana-chart-11 (fri 08-21) respected — 3 days apart
auto_execute: false
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/unifi-controller-rate-limit.md
  - docs/sops/monitoring.md
generated: "2026-08-18"
retargeted: "2026-08-18"              # v3.4.1 -> v3.5.0 (image) AND +chart 2.4.0; both
                                      # deltas re-verified against the upstream diffs
---

# unpoller v2.39.0 → v3.5.0 (image major) + chart 2.1.0 → 2.4.0

## 1. Summary & why held

Bump `ghcr.io/unpoller/unpoller` from v2.39.0 to v3.5.0 **and** the `unpoller`
chart from 2.1.0 to 2.4.0, in the SAME window, as one change.

> **Premise correction (2026-08-18, evening).** This plan was written this
> afternoon saying *"the upstream helm-chart repo has published no v3-aware
> chart; 2.1.0 is its newest"*. That was true when written and went stale hours
> later: chart **2.3.0** (appVersion `v3.4.1`) was published 2026-08-18 00:37Z
> and **2.4.0** (appVersion `v3.5.0`) at 14:52Z. Both halves now move together —
> see §1.4 for the three chart template changes that actually touch us.

Held because it is a **major** with two documented breaking changes (sweep
finding `F-a5ceabc1`):

1. **v3.0.0 — UniFi API compatibility rebase.** Release notes: *"Unifi network
   APIs have changed significantly in later 10.x releases"*; v3 tracks the
   upstream `unifi` library v5.26.0 (v5.30.0 by v3.4.0) and *"may not work for
   older UniFi installations on 9.x network APIs and the earlier 10.x
   releases"*, and users should *"expect metrics, events and logs to have
   changed (new, missing, changed)"*. So individual `unpoller_*` series may
   appear/vanish/relabel — the blast radius is everything keyed on those names
   (enumerated below).
2. **v3.2.0 — Prometheus behavior change (quoted breaking change):** *"Unpoller
   now background refreshes data by default every 60s instead of polling the
   unifi API on-demand per prometheus scrape"*. **Correction (2026-08-18, read
   from the code, not the release note):** upstream says `interval = 0` restores
   the old per-scrape behaviour — it does not, at v3.4.1 or v3.5.0.
   `normalizeInterval` maps any value `<= 0` to the 60s default and clamps
   anything below the 15s floor upward, so per-scrape polling **cannot be
   restored at all in v3.x**. Keeping `interval = "2m"` is still the right
   action; the reason previously given for it was wrong. Two consequences:
   - **`UnifiControllerUnreachable` changes meaning.** It fires on
     `up{job="unpoller"} == 0`, which today works because unpoller polls the
     controller inline per scrape (the alert annotation says exactly that).
     With v3's cached background refresh, a controller outage no longer fails
     the scrape — `up` stays 1 and the exporter serves stale data. Post-upgrade
     this alert only detects exporter death, not controller unreachability.
        **The replacement signal already exists** and needs no research:
     `unpoller_prometheus_cache_age_seconds` (v3.2.0+) reports seconds since
     the last successful background refresh, or `-1` if none has ever
     succeeded. That is the correct basis for the follow-up alert, and it
     doubles as the empty-exporter detector described in point 3.
   - The **unifi-device-availability SLO's present-gating** shifts the same
     way: a controller-unreachable episode may serve cached "up" devices
     instead of absent series. Slightly *more* forgiving, never a false
     burn — acceptable, but record it.

3. **v3.5.0 (2026-08-18) — why this plan was retargeted off v3.4.1.** The
   delta is 12 commits over 6 files and changes nothing this plan relied on:
   `pkg/promunifi/collector.go` is byte-identical between the two tags, so the
   background-refresh analysis in point 2 holds verbatim, and the `unifi/v5`
   library stays at v5.30.0 (no further API rebase). Three things matter:
   - **Input-plugin panic recovery.** v3.x could exit (code 2, no error text)
     while polling the Site Speed Test `aggregated-dashboard` endpoint,
     crashlooping before `:9130` ever opened. It was reported against UniFi
     Network **10.4.57 — the version our controller runs** (recorded in
     `runbooks/version-check-current.md`), which makes v3.5.0 strictly safer
     for us than v3.4.1, and is the whole reason to retarget.
   - **…but recovery is not a root-cause fix.** The panic is converted to an
     error for the whole collection cycle. With the unifi input as our ONLY
     input, a recurring panic means the background refresh never succeeds:
     `/metrics` goes empty, `unpoller_prometheus_cache_age_seconds` reads `-1`,
     and **`up` stays 1**. The crashloop becomes a silent empty exporter, which
     neither `up` nor HelmRelease-Ready can see. §4 now tests for it directly.
   - **One label added:** `unpoller_wan_interface_state` gains a `state` label,
     changing that series' identity. No consumer in this repo references it
     (grepped across `kubernetes/`, `runbooks/`, `docs/`) — zero impact. No
     metric was added, removed or renamed otherwise, so the 7,886-series
     baseline and the ±20% band in §4 stand unchanged.
   - Not applicable to us: the `alarms` endpoint 400 fix — our config sets
     `save_alarms = false`.

4. **Chart 2.1.0 → 2.4.0 (new, 2026-08-18) — three template changes that hit
   THIS HelmRelease.** Diffed 2.1.0 vs 2.4.0 tarballs; the chart is still a thin
   deployment+secret chart, but:
   - **`service.enabled` is now a real template (default `false`) — a NAME
     COLLISION with our hand-written Service.** 2.1.0 had no Service template at
     all, which is why `kubernetes/apps/monitoring/unpoller/app/service.yaml`
     exists and why our `values.service.enabled: true` has been inert. Under
     2.4.0 that value suddenly RENDERS `Service/unpoller` in `monitoring` — the
     same name our Kustomization already owns. Two owners for one object, and
     the chart's port is named **`tcp`** while `servicemonitor.yaml` scrapes
     `port: http`: if the chart's Service wins, the ServiceMonitor selects a
     Service with no `http` port, the scrape target disappears, and **every**
     `unpoller_*` series stops — dashboards, alerts and the SLO all at once,
     with a green HelmRelease. **Action: set `service.enabled: false` in
     values** and keep the hand-written Service (it is the one the ServiceMonitor
     is written against). This is exactly the vetting an unattended chart-only
     bump would have skipped.
   - **`podMonitor.enabled` is now honoured.** 2.1.0 rendered
     `templates/pod-monitor.yaml` unconditionally, which is why the HelmRelease
     carries a `postRenderers` kustomize `$patch: delete` for
     `PodMonitor/unifi-poller` (a second 30s scrape doubles UniFi API load and
     duplicates every series). 2.4.0 wraps it in `{{- if .Values.podMonitor.enabled }}`
     and our values already say `false`, so **the postRenderer becomes dead
     code — remove it in the same commit** (leaving it is harmless but keeps a
     misleading comment in the manifest).
   - **`upConfigExistingSecret` added — do NOT adopt it here.** Our config comes
     from `valuesFrom` → `upConfig` (SOPS secret `unpoller-credentials`), which
     still renders the chart-managed secret exactly as today. Switching to the
     new mechanism is an unrelated refactor; not in this window.
   - Also new and unused by us: `extraEnv`, `priorityClassName`, and a
     whitespace-only fix in the default `upConfig` (we override it).
   - **appVersion is now `v3.5.0`** (2.1.0 said `v2.21.0`). We pin `image.tag`
     explicitly, so appVersion never selects the image for us — but it is the
     reason the chart and image must move together: chart 2.4.0 is written for
     the v3 image, and shipping it against `tag: v2.39.0` is an untested pairing
     that nobody planned.

### Blast radius enumeration (what queries unpoller metric names)

| Consumer | Prefix used | Live today? |
|---|---|---|
| 5 dashboards in `kubernetes/apps/monitoring/unpoller/app/dashboards/` (network-sites, uap-, usg-, usw-, client-insights) — ~250 panel queries | `unpoller_*` | yes — matches the 7,886 live `unpoller_*` series |
| `prometheusrule.yaml` `unifi-alerts`: UnifiDeviceOffline, UnifiAccessPointHighClientCount, UnifiDeviceHighMemory, UnifiDeviceHighCPU, UnifiSwitchPortDown, UnifiHighWirelessInterference | `unifipoller_*` | **NO — dead expressions.** Zero `unifipoller_*` series exist (config sets `namespace = "unpoller"`). Pre-existing bug, not caused by this upgrade. |
| `prometheusrule.yaml` `UnifiControllerUnreachable` | `up{job="unpoller"}` | yes — but semantics degrade under v3 (above) |
| SLO `unifi-device-availability` (sweep_history DB) | `unpoller_device_uptime_seconds` | yes — correct prefix (note: `docs/sops/sli-catalog.md` line 62 still documents the stale `unifipoller_` form) |

**Discovery made while planning (pre-existing, upgrade-independent):** 6 of the
7 UniFi alert rules can never fire today. Do NOT silently fold a mass metric
rename into this plan — the `unifipoller_*` names don't map 1:1 onto v3 names
(e.g. `unifipoller_device_sys_mem` has no direct `unpoller_` twin). File it as
its own follow-up finding/plan after the v3 metric surface has soaked 24h.

## 2. Pre-checks

```bash
# a. unpoller healthy on the current version, chart Ready
kubectl get hr -n monitoring unpoller -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} chart={.status.history[0].chartVersion}{"\n"}'
kubectl get pods -n monitoring -l app.kubernetes.io/name=unpoller   # 1/1, 0 recent restarts

# b. target image published (v3.5.0 verified 2026-08-18: HTTP 200)
TOKEN=$(curl -s "https://ghcr.io/token?scope=repository:unpoller/unpoller:pull" | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/vnd.oci.image.index.v1+json" \
  https://ghcr.io/v2/unpoller/unpoller/manifests/v3.5.0        # expect 200

# c. controller Network application on the newer 10.x APIs that v3 targets
#    (v3.x tracks unifi lib v5.26.0→v5.30.0; older 10.x/9.x network APIs are
#    explicitly "may not work"). Uses the CACHED session — never a fresh login.
unifictl local health get

# d. baseline the metric surface (compare post-upgrade)
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &
curl -sG http://localhost:9090/api/v1/query --data-urlencode 'query=count({__name__=~"unpoller_.+"})'
# 2026-08-18 baseline: 7886 series
curl -sG http://localhost:9090/api/v1/query --data-urlencode 'query=count(count by (name) (unpoller_device_uptime_seconds))'
# baseline: ~10 devices (SLO denominator)

# e. no in-flight monitoring reconcile
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
```

## 3. Steps

1. Drop the active-update marker + a 4h alert silence for the monitoring
   rollout noise (SOP `application-update.md` §4 Step 1):
   ```bash
   runbooks/update-marker.sh add unpoller monitoring 4 "v2.39.0->v3.5.0 major"
   ```
2. Edit `kubernetes/apps/monitoring/unpoller/app/helmrelease.yaml` — **chart and
   image in ONE commit** (§1.4):
   ```yaml
     chart:
       spec:
         chart: unpoller
         version: 2.4.0     # was 2.1.0
   ...
       image:
         repository: ghcr.io/unpoller/unpoller
         pullPolicy: IfNotPresent
         tag: v3.5.0        # was v2.39.0
   ...
       service:
         enabled: false     # was true — INERT on 2.1.0 (no Service template),
                            # but 2.4.0 renders Service/unpoller and collides
                            # with our hand-written service.yaml, whose port is
                            # named `http` (the ServiceMonitor selects on it)
   ```
   …and DELETE the now-dead `postRenderers:` block (chart 2.4.0 honours
   `podMonitor.enabled: false`, which our values already set).

   Render before pushing — this is the gate that catches the Service collision:
   ```bash
   mise exec -- helm template unpoller unpoller/unpoller --version 2.4.0 \
     -f /tmp/unpoller-values.yaml | grep -E '^kind:|^  name:'
   # expect: Deployment + Secret + ServiceAccount only.
   # NO Service, NO PodMonitor. If either appears, stop — the values are wrong.
   ```
   **Do not touch `secret.sops.yaml`.** The existing `up.conf` TOML
   (`[unifi]`/`[[unifi.controller]]` user+pass, `[prometheus]`, `[influxdb]`)
   remains valid in v3; v3's Integration-API/api-key auth is additive, not
   required. Keep `[prometheus] interval = "2m"` — under v3 it governs the
   background-refresh cadence (a gentle 0.5 login/min against the 429-throttled
   `/api/auth/login`). v2's per-scrape behaviour is **not recoverable** in v3:
   `interval = 0` silently becomes the 60s default rather than disabling the
   background refresh. That is fine — a 2m cadence is exactly what
   `unifi-controller-rate-limit.md` wants — but do not lower it expecting the
   old semantics back.

   **One decision to take at the window (new at v3.4.1):** the
   `save_speedtest` toggle (`[[unifi.controller]]`, `*bool`, defaults **true**)
   gates the Site Speed Test `aggregated-dashboard` poll that triggers the
   §1.3 panic. Setting `save_speedtest = false` is the belt-and-braces
   mitigation, but it is the ONLY reason to touch `secret.sops.yaml` in this
   plan. Default: leave the secret alone and rely on v3.5.0's panic recovery;
   if the pod panics or serves an empty `/metrics` at step 4, add
   `save_speedtest = false` as the first remediation before rolling back.
3. Commit + push (hunk-scoped, this file only):
   ```bash
   git add kubernetes/apps/monitoring/unpoller/app/helmrelease.yaml
   git commit -m "feat(unpoller)!: chart 2.1.0 -> 2.4.0 + image v2.39.0 -> v3.5.0 (plan unpoller-v3, F-a5ceabc1)"
   git push
   ```
4. Watch the rollout — startup log is the config-compat gate (no local way to
   dry-run v3 against our TOML):
   ```bash
   kubectl rollout status deployment/unpoller -n monitoring --timeout=120s
   kubectl logs -n monitoring deployment/unpoller --tail=50
   # expect: config parsed, controller login OK, prometheus exporter on :9130,
   # influxdb writes OK. Any TOML/flag parse error -> rollback (§5).
   ```
   RollingUpdate briefly runs two pollers against the controller login
   endpoint; that transient doubling is acceptable, but if a 429 retry storm
   starts, follow the recovery in `docs/sops/unifi-controller-rate-limit.md`
   (never add manual login retries).
5. On success: clear the marker (`runbooks/update-marker.sh clear unpoller`),
   drop the silence early.

## 4. Verification

```bash
# scrape target up, HR Ready ON THE NEW CHART
kubectl get hr -n monitoring unpoller \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} chart={.status.history[0].chartVersion}{"\n"}'   # True 2.4.0

# chart-side collision check (§1.4): exactly ONE Service, ours, with an `http`
# port — and no chart PodMonitor
kubectl get svc -n monitoring unpoller -o jsonpath='{.spec.ports[*].name}{"\n"}'   # http
kubectl get podmonitor -n monitoring unifi-poller 2>&1 | tail -1                   # NotFound
kubectl get servicemonitor -n monitoring unpoller -o jsonpath='{.spec.endpoints[0].port}{"\n"}'  # http

curl -sG http://localhost:9090/api/v1/query --data-urlencode 'query=up{job="unpoller"}'   # == 1

# metric surface survived the API rebase (within ~20% of the 7886 baseline;
# v3 release notes promise "new, missing, changed" — investigate any big drop)
curl -sG http://localhost:9090/api/v1/query --data-urlencode 'query=count({__name__=~"unpoller_.+"})'

# the specific series the dashboards + SLO stand on
for m in unpoller_device_info unpoller_device_uptime_seconds unpoller_client_uptime_seconds unpoller_device_stations; do
  curl -sG http://localhost:9090/api/v1/query --data-urlencode "query=count($m)"; echo " <- $m"
done   # all > 0

# SLO unifi-device-availability numerator+denominator non-empty and sane
curl -sG http://localhost:9090/api/v1/query --data-urlencode 'query=count(count by (name) (unpoller_device_uptime_seconds > 0))'
# == device count from pre-check (d); denominator clamp keeps the SLO from a false burn

# dashboards: spot-check "UniFi Network Sites" + "UAP Insights" in Grafana —
# headline panels (device count, client count, throughput) non-empty for the
# last 15m. Data freshness: series timestamps advance every <=2m (background
# refresh), while the 60s ServiceMonitor scrape keeps `up` green.

# NEW at v3.5.0 — the silent-empty-exporter mode that `up` and HR-Ready both
# miss (see §1.3): the background refresh must have succeeded recently.
curl -sG http://localhost:9090/api/v1/query --data-urlencode 'query=unpoller_prometheus_cache_age_seconds'
# expect >= 0 (never -1) AND < 360 (3x the 2m interval)
kubectl logs -n monitoring deployment/unpoller --since=15m | grep -ci 'panic' || true   # expect 0

# influxdb output still writing (no error lines in the last 10m of logs)
kubectl logs -n monitoring deployment/unpoller --since=10m | grep -ci 'influx.*err' || true   # expect 0
```

Soak 24h (daily sweep + SLO burn-rate windows cover it), then delete this plan
file per the plans README and file the follow-up finding for the dead
`unifipoller_*` alert rules + the degraded `UnifiControllerUnreachable`
semantics (replace it with a `unpoller_prometheus_cache_age_seconds` staleness
rule — see §1.3, the metric already exists) + the stale
`docs/sops/sli-catalog.md` line 62.

## 5. Rollback

```bash
git revert <bump-commit-sha> && git push     # single-file revert: chart 2.4.0 -> 2.1.0,
                                            # image v3.5.0 -> v2.39.0, service.enabled
                                            # back to true, postRenderer restored — all
                                            # in one commit, so one revert undoes both halves
flux reconcile kustomization unpoller -n flux-system --with-source   # optional: skip the 30m wait
kubectl rollout status deployment/unpoller -n monitoring --timeout=120s
# confirm back: image v2.39.0, up{job="unpoller"} == 1, series count back at baseline
# (v2 has no cache-age metric — its absence after a rollback is expected)
kubectl get deploy -n monitoring unpoller -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
```

Stateless exporter, no schema/state migration in either direction — rollback is
complete once the old pod is Ready and scraped. Prometheus keeps any
v3-era-only series as stale history; no cleanup needed.

## 6. Interference notes

- **`conflicts_with: grafana-chart-11`** (currently `fri-early:2026-08-21`):
  that plan rolls Grafana itself and re-renders all 38 provisioned dashboard
  ConfigMaps in `monitoring`. This plan's pass/fail signal is "unpoller
  dashboard panels non-empty" — in a shared window an empty panel can't be
  attributed to the exporter vs the Grafana migration. Different window, either
  order; prefer this one FIRST so grafana-chart-11's own verification then
  exercises dashboards against the already-soaked v3 metric surface.
- **Shared UniFi controller login endpoint** (`shared: [unifi-controller]`):
  the UDM's per-IP `/api/auth/login` 429 throttle is shared with unifictl
  (security sweep). Don't schedule alongside anything that logs into the
  controller repeatedly; the window agent should treat a 429 during rollout as
  "back off", never retry (SOP `unifi-controller-rate-limit.md` §4.4).
- **Alert semantics, not just availability:** post-upgrade,
  `UnifiControllerUnreachable` no longer detects controller unreachability
  (cached background refresh keeps `up`==1). Until the follow-up lands, a
  UniFi Network-app JVM GC stall (known ~8d recurrence) will surface via SLO
  data-staleness rather than this alert. The window agent should not read a
  quiet `unifi-alerts` group as "verified healthy".
- InfluxDB output writes to `databases/influxdb2` — write-only; v3 measurement
  drift affects only Unpoller-InfluxDB Grafana panels, no other writer/reader.
- No reboot, no storage, no ingress/DNS/CNI surface. Namespace blast radius is
  `monitoring` only; the polled controller is out-of-cluster and is only ever
  read.
