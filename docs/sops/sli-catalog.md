# SOP: SLI Catalog (sweep-history Track C / Phase 0)

> Description: Inventory of SLI candidates per integration, with explicit signal sources (Prometheus / Elasticsearch / hactl / kubectl / none) and pilot-ready ratings. Drives the `slo_definitions` table in sweep_history Postgres (the runtime SLO catalog).
> Version: `2026.09.22`
> Last Updated: `2026-09-22`
> Owner: `homelab-operator`

---

## 1) Description

This SOP is the **signal census** for the SLI/SLO programme being built on top of the sweep-history dashboard (`kubernetes/apps/monitoring/sweep-dashboard/`). Before authoring any individual SLO, this catalog lists every integration we care about, what numerator/denominator pair we could measure today, and where that signal currently lives. SLOs without a viable numerator-and-denominator pair are explicitly deferred — building an SLO target without a real signal produces theater, not reliability.

- Scope: smart-home + infra integrations on this cluster
- Prerequisites: read access to the cluster's Prometheus stack, Elasticsearch, and (locally) `hactl`
- Out of scope: defining the actual SLO targets — that's Track C / C4

---

## 2) Overview

Three signal backends in scope, in order of preference:

1. **Prometheus** — preferred. Time-series, recording-rule-friendly, supports burn-rate math via `rate()` + windows. Existing ServiceMonitor coverage is broad.
2. **Elasticsearch (ES)** — second choice. Log-event ratios are SLI-shaped (good_events / total_events over time window) but slower to query and harder to alert on. Used where Prom signal is absent.
3. **hactl** — third choice. Canonical health probe for Home Assistant but CLI-only; an SLO using it requires wrapping the CLI output into a queryable backend (Postgres or push-to-Prom).

Integrations missing all three are deferred until signal collection ships.

---

## 3) Blueprints

N/A — this is the inventory, not a code blueprint. Adding an SLO that's listed here as pilot-ready: `runbooks/policy-cli.py slo add` writes a row to the `slo_definitions` table; the calculator picks it up on the next `slo-check.py` invocation.

---

## 4) Operational Instructions

When adding a new integration to this catalog:

1. **Locate the source-of-truth signal.** Check the integration's HelmRelease for a ServiceMonitor / PodMonitor. Check `kubernetes/apps/monitoring/kube-prometheus-stack/app/` for any `additionalServiceMonitors` block targeting it. Search ES log streams via Kibana saved searches.
2. **Define numerator and denominator.** Concrete PromQL / ES query / hactl field. If you can't write the query in one line, the signal isn't SLI-shaped — refine or defer.
3. **Rate readiness** as `pilot-ready` / `partial` / `deferred`:
   - `pilot-ready`: query works today, returns sensible numbers, can be put into a calculator within an hour
   - `partial`: signal exists but needs additional plumbing (exporter wiring, log-pipeline filter, denominator clarification)
   - `deferred`: no signal yet OR the signal is intentionally out of scope (vendor SaaS, accepted-risk posture)
4. **Update the table below** in the same PR as the new integration.

---

## 5) Examples — Inventory

Sorted by readiness. Source citations included so a follow-up can re-confirm without re-discovering. **Every PromQL expression in the pilot-ready table was re-verified against the live Prometheus on 2026-09-22** (F-4613508e) — see §6 for the one-pass check and §7 for how to resolve a metric name that turns out not to exist.

### Pilot-ready (Prometheus-native, ship today)

| # | Integration | Numerator | Denominator | Source | Notes |
|---|---|---|---|---|---|
| 1 | **mosquitto** broker | `count(up{job="mosquitto-metrics"} == 1)` | `count(up{job="mosquitto-metrics"})` | `sapcc/mosquitto-exporter` sidecar — already in `kubernetes/apps/home-automation/mosquitto/app/helmrelease.yaml` | Cleanest pilot. **The job label is `mosquitto-metrics`, not `mosquitto`** (corrected 2026-09-22, F-4613508e): `up{job="mosquitto"}` matched 0 series. Also note the exporter's own series are prefixed `broker_*` (`broker_uptime`, `broker_clients_connected`, …), NOT `mosquitto_*` — no metric name in this cluster contains the string `mosquitto`. |
| 2 | **longhorn** storage | `count(longhorn_volume_robustness{state="healthy"} == 1)` | `count(longhorn_volume_robustness{state="healthy"})` | Native Longhorn metrics, ServiceMonitor in `monitoring/kube-prometheus-stack/app/` | Existing PrometheusRule `longhorn-alerts.yaml` defines thresholds — SLO is a generalisation. **There is no `robustness` LABEL** (corrected 2026-09-22, F-4613508e): the metric is a four-way per-state FAMILY carrying `state` ∈ `healthy`/`degraded`/`faulted`/`unknown`, one series per volume per state, valued `1` on the volume's active state. So the old numerator `{robustness="healthy"}` matched nothing **and** the old denominator `count(longhorn_volume_robustness)` returned 4× the volume count (376 series for 94 volumes) — which would have pinned the ratio near 24% even after fixing the numerator. Filtering the denominator to a single state is what makes it one series per volume. |
| 3 | **unifi** device availability (via Unpoller) | `count(unpoller_device_uptime_seconds > 0)` | `count(unpoller_device_uptime_seconds)` | `kubernetes/apps/monitoring/unpoller/app/`, scrape job `unpoller` | 9 PrometheusRule rules already alert on derived signals — SLO complements with budget-tracking. **The exporter prefix is `unpoller_`, not `unifipoller_`** (corrected 2026-09-22, F-4613508e) — no metric in this cluster begins with `unifipoller_`, so BOTH halves of the old ratio were empty. The numerator was also `sum()` over a *seconds* gauge rather than `count()`, which would have summed uptimes instead of counting devices. |
| 9 | **internal DNS** (k8s-gateway split-horizon) | `(count(probe_success{probe_class="dns"} == 1) or on() (count(probe_success{probe_class="dns"}) * 0))` | `(count(probe_success{probe_class="dns"}) or on() vector(0))` | `prometheus-blackbox-exporter` (chart 11.17.2 / blackbox v0.28.0) + 2 `Probe` CRs in `kubernetes/apps/monitoring/prometheus-blackbox-exporter/app/probes.yaml` | Live as SLO `internal-dns-resolution` — 99.9% / 7d (10.1 min budget), tags `network,dns,pilot`. **Answer-validating, not reachability**: `valid_rcodes=[NOERROR]` AND `validate_answer_rrs` (a real A record in `192.168.0.0/16`), so SERVFAIL, NXDOMAIN and NOERROR-with-empty-answer all count as failures — the 2026-08-15 shape, where every pod was Running and Flux was green. Numerator present-gated (longhorn pattern) so scrape gaps do not NaN-poison the window. `BlackboxProbesAbsent` alerts if the SLI goes silent. |
| 10 | **internal HTTP routing** (one host per Gateway) | `(count(probe_success{probe_class="http"} == 1) or on() (count(probe_success{probe_class="http"}) * 0))` | `(count(probe_success{probe_class="http"}) or on() vector(0))` | same exporter; 2 HTTPS `Probe` CRs, one representative host per Gateway (verified live 2026-09-08: `http-ingress-internal` -> `sweep.${SECRET_DOMAIN}` on `envoy-internal`, `http-ingress-external` -> `echo-server.${SECRET_DOMAIN}` on `envoy-external`). The CR names still say `ingress` for metric-continuity; the SLI is healthy and was never broken by the ingress-nginx deletion | Live as SLO `internal-ingress-availability` — 99.5% / 7d (50.4 min budget), tags `network,ingress,pilot`. End-to-end user path (CoreDNS → k8s-gateway → Envoy Gateway → TLS → backend); TLS verification left ON so cert expiry counts as the user-visible failure it is. Deliberately looser than #9 because single-replica backend rollouts land in this number; if backend churn dominates the budget the fix is a dedicated always-on probe endpoint per Gateway, **not** a looser target. |

### Partial (signal exists but needs wiring)

| # | Integration | Why partial | Path to pilot-ready |
|---|---|---|---|
| 4 | **frigate** NVR | **Frigate is not scraped at all** (verified 2026-09-22, F-4613508e). The previous claim "Prom metrics exist (`frigate_detections_total`, `frigate_detection_fps`)" was false: both return zero series, no metric name in this cluster contains `frigate`, and `kubernetes/apps/home-automation/frigate-nvr/` ships no ServiceMonitor. The only frigate-named scrape job is `ak-outpost-frigate-forward-auth-metrics` — the Authentik outpost in front of frigate, not frigate itself. Separately, no clear "good event" definition. (The original entry's "684k errors / 7d in ES from a single signature" is a 2026-05-19 figure and was **not** re-measured.) | (a) Ship a ServiceMonitor against frigate's `/api/prometheus` endpoint — nothing here can be rated above `deferred`-in-practice until that lands; (b) only then sample the `*_total` counters from a live scrape; (c) isolate the top error signature in Kibana; (d) decide whether the SLO measures detection throughput, detection latency, or error rate. |
| 5 | **home-assistant-core** | hactl is CLI-only. `Critical:` / `Warnings:` counts + `unavailable_entities` count are well-defined, but not queryable from Prom/ES until wrapped. | (a) Either expose hactl output as Prometheus metrics via a small in-cluster exporter, OR (b) add a new step inside `runbooks/sweep-run.py` (or a dedicated `hactl-check.py`) that polls hactl and inserts counts into `sweep_findings` via the existing `runbooks/lib/findings_writer.py` contract. (b) is cheaper — reuses the local-execution architecture instead of adding cluster-side surface. |
| 6 | **shelly** | (From plan-mode inventory.) Connected MQTT clients is countable via the mosquitto exporter, but the *expected* count is hardcoded (~34–38). Numerator clear, denominator is a constant. **The metric is `broker_clients_connected`, not `mosquitto_clients_connected`** (corrected 2026-09-22, F-4613508e) — the latter has no series. Second problem found in the same pass: it is **broker-wide** (live value 47 on 2026-09-22), covering every MQTT client and not shelly alone. | Acceptable for v0 — define the denominator as a literal when adding the SLO via `policy-cli slo add`, with a TODO to derive it dynamically. Be explicit in the SLO description that v0 measures "MQTT clients connected to the broker", **not** "shelly devices online": the exporter offers no per-client breakdown, so a shelly-only numerator needs a different source (e.g. a `$SYS`-independent probe or Z2M-style per-device state). |

### Deferred (no signal yet, or intentionally out of scope)

| # | Integration | Reason | Revisit when |
|---|---|---|---|
| 7 | **flux** GitOps | Kustomization/HelmRelease `Ready` conditions are real-time only, no Prom exporter deployed. | Either deploy flux's built-in Prometheus exporter (small Helm values change), or have `runbooks/sweep-run.py` query `flux get` and emit reconcile counts to `sweep_findings` on each invocation. |
| 8 | **miele** cloud | Intentionally NOT an SLO target — measures vendor SaaS reliability, not anything you can act on. Documented as accepted-risk in `docs/troubleshooting/ha-upstream-integration-issues.md`. Allowlisted at 100 errors/cycle in the `noise_suppressions` table (category `known_ha_error_sources`). | Never. |

---

## 6) Verification Tests

For each entry marked `pilot-ready`. Every query below was re-verified against
the live Prometheus on 2026-09-22, after three of the five pilot entries were
found naming metrics with **zero** series (F-4613508e).

```bash
# Port-forward once; capture the PID and kill it BY PID — job control is not
# available in a non-interactive zsh, so `kill %1` fails and the forward leaks.
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 \
  >/dev/null 2>&1 & PF=$!; sleep 3

# Every pilot numerator AND denominator in one pass. Prefer python3 over jq
# (AGENTS.md). Assert the SAMPLE COUNT, never just the value: an empty vector is
# PromQL's normal "no data", not an error, so a dead metric prints nothing at
# all rather than failing — which is exactly how #1/#2/#3 survived since
# 2026-05-19.
python3 - <<'EOF'
import json, urllib.parse, urllib.request
B = 'http://localhost:9090/api/v1/query?'
Q = [
 ('1 mosquitto num', 'count(up{job="mosquitto-metrics"} == 1)'),
 ('1 mosquitto den', 'count(up{job="mosquitto-metrics"})'),
 ('2 longhorn num',  'count(longhorn_volume_robustness{state="healthy"} == 1)'),
 ('2 longhorn den',  'count(longhorn_volume_robustness{state="healthy"})'),
 ('3 unifi num',     'count(unpoller_device_uptime_seconds > 0)'),
 ('3 unifi den',     'count(unpoller_device_uptime_seconds)'),
 # #9/#10 are present-GATED (`or on() vector(0)`), so their SLI form can NEVER
 # return an empty result — that is the point of the gate. Emptiness must
 # therefore be asserted on the RAW selector, or this test is blind for them.
 ('9 dns raw',       'probe_success{probe_class="dns"}'),
 ('10 http raw',     'probe_success{probe_class="http"}'),
 ('9 dns num',       '(count(probe_success{probe_class="dns"} == 1) or on() (count(probe_success{probe_class="dns"}) * 0))'),
 ('10 http num',     '(count(probe_success{probe_class="http"} == 1) or on() (count(probe_success{probe_class="http"}) * 0))'),
]
dead = []
for name, q in Q:
    r = json.load(urllib.request.urlopen(B + urllib.parse.urlencode({'query': q})))['data']['result']
    print(f"{name:<16} samples={len(r):<3} value={r[0]['value'][1] if r else None}")
    if not r:
        dead.append(name)
print('DEAD (signal absent — demote the entry to `partial`):', dead or 'none')
raise SystemExit(1 if dead else 0)
EOF

kill $PF 2>/dev/null
```

Expected: `DEAD: none`, exit 0. Measured 2026-09-22 — mosquitto `1 / 1`,
longhorn `92 / 94`, unifi `10 / 10`, dns raw `2` series, http raw `2` series,
dns and http numerators `2` each.

A query returning `samples=0` means the signal is not live and the entry must
move from `pilot-ready` to `partial` — **but check §7 first**: far more often
the signal is fine and the metric NAME in this catalog is wrong.

---

## 7) Troubleshooting

**"Numerator returns 0 / empty"** — the metric name has drifted between exporter versions, or was never right to begin with. Compare against the running pod's `/metrics` endpoint via `kubectl exec` (or `kubectl port-forward` + curl). Update the catalog entry.

**"The catalog names a metric that does not exist"** — the failure found on 2026-09-22 (F-4613508e), when three of the five pilot-ready entries plus one partial entry named series with zero samples. It hides well: an empty vector is not an error, so `count(up{job="mosquitto"})` returns *no sample* rather than `0`, and anything reading it sees "no data" — the entry looks parked, not broken. Never copy a metric name from a chart README, an upstream dashboard, or another cluster. Resolve it against THIS Prometheus:

```bash
# 1. What is that exporter's real job label?  (<frag> e.g. mos, unpoll, frigate)
curl -s http://localhost:9090/api/v1/label/job/values \
  | python3 -c "import sys,json;print([j for j in json.load(sys.stdin)['data'] if '<frag>' in j])"

# 2. What metric names does that job actually export?
curl -s --get http://localhost:9090/api/v1/query \
  --data-urlencode 'query=group by(__name__)({job="<job>"})' \
  | python3 -c "import sys,json;print(sorted(r['metric']['__name__'] for r in json.load(sys.stdin)['data']['result']))"

# 3. Is the label you plan to filter on real? (it may be a per-state FAMILY)
curl -s --get http://localhost:9090/api/v1/query --data-urlencode 'query=<metric>' \
  | python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];print(r[0]['metric'] if r else 'NO SERIES')"
```

Command 3 is the one that caught #2: `longhorn_volume_robustness` carries no `robustness` label at all, and the label set it *does* carry changed the correct **denominator** too, not just the numerator. A name fix is not finished until you have re-derived both halves of the ratio.

**"Denominator returns 0"** — there are literally no instances of the resource (e.g., no Longhorn volumes). SLO would divide by zero; either skip this cycle or fall back to a configurable minimum.

**"PromQL scrape gap during window"** — Prometheus retention is 7d, 20GB. Windows >7d can't be evaluated from Prom alone; need recording rules to roll up. Track C will author these in C1.

---

## 8) Diagnose Examples

```bash
# Find every exporter ServiceMonitor in the cluster
kubectl get servicemonitor -A -o jsonpath='{range .items[*]}{.metadata.namespace}/{.metadata.name}{"\t"}{.spec.endpoints[*].port}{"\n"}{end}'

# Frigate native metrics endpoint sample (port-forward)
kubectl port-forward -n home-automation svc/frigate-nvr 5000:5000 &
curl -s http://localhost:5000/api/prometheus | grep -E '^frigate_.*_total ' | head -20

# hactl doctor JSON dump (local; not in-cluster)
hactl doctor --json | jq '{overall, critical: .critical_count, warning: .warning_count, unavailable: .unavailable_entities, zombies: .zombie_devices}'
```

---

## 9) Health Check

`runbooks/slo-check.py` (Track C / C1) reads this catalog's pilot-ready entries by name and emits `slo_snapshots` rows. If any entry promoted to `pilot-ready` returns empty/null at probe time for 24h, demote it in this catalog (PR) — empty SLO snapshots pollute the time series.

---

## 10) Security Check

- This SOP contains no secrets.
- Per the CLAUDE.md privacy rule, when discussing integrations in commit messages or PR bodies use placeholders (`<integration>`, `<exporter>`) only if the value is sensitive — exporter names (mosquitto, longhorn, unpoller) are public and fine to name.
- No new RBAC or network policies are introduced by this catalog (the SLO calculator's RBAC ships in C1).

---

## 11) Rollback Plan

Reverting this SOP is a no-op (it's documentation). To roll back an SLO that turned out to have a bad signal:

1. Disable or delete the row in `slo_definitions` via `runbooks/policy-cli.py slo disable NAME` (preferred — keeps audit trail) or `delete NAME` (hard-remove).
2. Move the catalog row in this SOP from `pilot-ready` to `partial` or `deferred` with the reason.
3. Any historical `slo_snapshots` rows for that name are preserved — they're useful evidence of the failed pilot.

---

## 12) References

- [SOP-TEMPLATE.md](SOP-TEMPLATE.md) — section structure this SOP follows
- [policy-cli.md](policy-cli.md) — the operator-facing SOP for adding/disabling SLOs (`policy-cli.py slo add|disable`)
- `slo_definitions` table in sweep_history Postgres — runtime SLO catalog; browse at `sweep.<DOMAIN>/policies/slos`
- [runbooks/slo-check.py](../../runbooks/slo-check.py) — multi-backend calculator
- `noise_suppressions` table in sweep_history Postgres — informal thresholds being formalised as SLOs; browse at `sweep.<DOMAIN>/policies/noise`
- [unifi-controller-rate-limit.md](unifi-controller-rate-limit.md) — implicit UniFi SLO target (30s polling → 99% device-up)
- [docs/troubleshooting/ha-upstream-integration-issues.md](../troubleshooting/ha-upstream-integration-issues.md) — Miele accepted-risk posture
- [k8s-gateway-dns.md](k8s-gateway-dns.md) — the 2026-08-15 internal-DNS outage that motivated entries #9/#10
- `kubernetes/apps/monitoring/prometheus-blackbox-exporter/` — exporter + Probe CRs backing both entries

---

## Version History

| Date | Version | Change |
|---|---|---|
| 2026-05-19 | 2026.05.19 | Initial catalog — 8 entries, 3 pilot-ready, 3 partial, 2 deferred |
| 2026-08-15 | 2026.08.15 | +2 pilot-ready blackbox entries (#9 internal DNS, #10 internal ingress) after the 2026-08-15 zero-signal DNS outage (N-15). Catalog now 10 entries: 5 pilot-ready, 3 partial, 2 deferred. |
| 2026-09-22 | 2026.09.22 | **Three of the five pilot-ready entries named metrics with ZERO series in Prometheus, plus one partial entry (F-4613508e).** #1 mosquitto queried job `mosquitto` (real: `mosquitto-metrics`; the exporter's series are `broker_*`, and nothing in this cluster is named `mosquitto_*`). #2 longhorn filtered on a `robustness="healthy"` LABEL that does not exist — the metric is a per-`state` family with 4 series per volume, so the old **denominator** was 4× inflated as well. #3 unifi used the `unifipoller_` prefix (real: `unpoller_`) and `sum()` on a seconds gauge where `count()` was meant, so both halves were wrong. #6 shelly used `mosquitto_clients_connected` (real: `broker_clients_connected`, and it is broker-wide rather than shelly-only). #4 frigate's "Prom metrics exist" claim was false — frigate is not scraped at all and ships no ServiceMonitor; the only frigate-named job is its Authentik outpost. #9/#10 blackbox entries re-verified live and left unchanged. §6 replaced with a single pass/fail sweep over every pilot numerator AND denominator that asserts sample COUNT (an empty vector is PromQL's normal "no data", not an error) and tests the RAW selector for #9/#10, whose present-gated form can never return empty by construction. §7 gained the three discovery commands that resolve a name against the live Prometheus. |
