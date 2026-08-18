---
plan_id: unpoller-v3
component: unpoller
pr: null                              # no Renovate PR open (image lives in chart
                                      # values `image.tag`); held via sweep finding
                                      # F-a5ceabc1 (section: version) — direct bump.
kind: image
current: "v2.39.0"
target: "v3.4.1"
update_type: major
risk: medium
est_duration_min: 30                  # + a 24h metric-continuity soak before the
                                      # dashboards/alerts follow-up is judged
needs_reboot: false
touches:
  namespaces: [monitoring]
  resources:
    - helmrelease/unpoller                    # image.tag bump; chart stays 2.1.0
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
---

# unpoller v2.39.0 → v3.4.1 (image major)

## 1. Summary & why held

Bump `ghcr.io/unpoller/unpoller` from v2.39.0 to v3.4.1 in the unpoller
HelmRelease values (chart stays `unpoller@2.1.0` — the upstream helm-chart repo
has published **no v3-aware chart**; 2.1.0 is its newest and is a thin
deployment+secret chart, expected to run the v3 image unchanged).

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
   unifi API on-demand per prometheus scrape"* (`interval = 0` restores the old
   per-scrape behavior). Two consequences for us:
   - **`UnifiControllerUnreachable` changes meaning.** It fires on
     `up{job="unpoller"} == 0`, which today works because unpoller polls the
     controller inline per scrape (the alert annotation says exactly that).
     With v3's cached background refresh, a controller outage no longer fails
     the scrape — `up` stays 1 and the exporter serves stale data. Post-upgrade
     this alert only detects exporter death, not controller unreachability.
   - The **unifi-device-availability SLO's present-gating** shifts the same
     way: a controller-unreachable episode may serve cached "up" devices
     instead of absent series. Slightly *more* forgiving, never a false
     burn — acceptable, but record it.

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

# b. target image published (verified 2026-08-18: HTTP 200)
TOKEN=$(curl -s "https://ghcr.io/token?scope=repository:unpoller/unpoller:pull" | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/vnd.oci.image.index.v1+json" \
  https://ghcr.io/v2/unpoller/unpoller/manifests/v3.4.1        # expect 200

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
   runbooks/update-marker.sh add unpoller monitoring 4 "v2.39.0->v3.4.1 major"
   ```
2. Edit `kubernetes/apps/monitoring/unpoller/app/helmrelease.yaml`:
   ```yaml
       image:
         repository: ghcr.io/unpoller/unpoller
         pullPolicy: IfNotPresent
         tag: v3.4.1        # was v2.39.0
   ```
   **Do not touch `secret.sops.yaml`.** The existing `up.conf` TOML
   (`[unifi]`/`[[unifi.controller]]` user+pass, `[prometheus]`, `[influxdb]`)
   remains valid in v3; v3's Integration-API/api-key auth is additive, not
   required. Keep `[prometheus] interval = "2m"` — under v3 it governs the
   background-refresh cadence (a gentle 0.5 login/min against the 429-throttled
   `/api/auth/login`; setting `interval = 0` to restore v2 per-scrape behavior
   is explicitly NOT wanted here, per `unifi-controller-rate-limit.md`).
3. Commit + push (hunk-scoped, this file only):
   ```bash
   git add kubernetes/apps/monitoring/unpoller/app/helmrelease.yaml
   git commit -m "feat(unpoller)!: v2.39.0 -> v3.4.1 (plan unpoller-v3, F-a5ceabc1)"
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
# scrape target up, HR Ready
kubectl get hr -n monitoring unpoller -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'
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

# influxdb output still writing (no error lines in the last 10m of logs)
kubectl logs -n monitoring deployment/unpoller --since=10m | grep -ci 'influx.*err' || true   # expect 0
```

Soak 24h (daily sweep + SLO burn-rate windows cover it), then delete this plan
file per the plans README and file the follow-up finding for the dead
`unifipoller_*` alert rules + the degraded `UnifiControllerUnreachable`
semantics (needs a staleness/exporter-internal-error based replacement) + the
stale `docs/sops/sli-catalog.md` line 62.

## 5. Rollback

```bash
git revert <bump-commit-sha> && git push     # single-file revert of the tag bump
flux reconcile kustomization unpoller -n flux-system --with-source   # optional: skip the 30m wait
kubectl rollout status deployment/unpoller -n monitoring --timeout=120s
# confirm back: image v2.39.0, up{job="unpoller"} == 1, series count back at baseline
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
