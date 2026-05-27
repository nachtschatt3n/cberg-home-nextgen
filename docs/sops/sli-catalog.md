# SOP: SLI Catalog (sweep-history Track C / Phase 0)

> Description: Inventory of SLI candidates per integration, with explicit signal sources (Prometheus / Elasticsearch / hactl / kubectl / none) and pilot-ready ratings. Drives the `slo_definitions` table in sweep_history Postgres (the runtime SLO catalog).
> Version: `2026.05.19`
> Last Updated: `2026-05-19`
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

Sorted by readiness. Source citations included so a follow-up can re-confirm without re-discovering.

### Pilot-ready (Prometheus-native, ship today)

| # | Integration | Numerator | Denominator | Source | Notes |
|---|---|---|---|---|---|
| 1 | **mosquitto** broker | `up{job="mosquitto"}` over window | total scrapes in window | `sapcc/mosquitto-exporter:0.8.0` sidecar — already in `kubernetes/apps/home-automation/mosquitto/app/helmrelease.yaml` | Cleanest pilot. Numerator + denominator both trivial PromQL. |
| 2 | **longhorn** storage | `count(longhorn_volume_robustness{robustness="healthy"})` | `count(longhorn_volume_robustness)` | Native Longhorn metrics, ServiceMonitor in `monitoring/kube-prometheus-stack/app/` | Existing PrometheusRule `longhorn-alerts.yaml` defines thresholds — SLO is a generalisation. |
| 3 | **unifi** device availability (via Unpoller) | `sum(unifipoller_device_uptime_seconds > 0)` | `count(unifipoller_device_uptime_seconds)` | `kubernetes/apps/monitoring/unpoller/app/` | 9 PrometheusRule rules already alert on derived signals — SLO complements with budget-tracking. |

### Partial (signal exists but needs wiring)

| # | Integration | Why partial | Path to pilot-ready |
|---|---|---|---|
| 4 | **frigate** NVR | Prom metrics exist (`frigate_detections_total`, `frigate_detection_fps`) but no clear "good event" definition. Plus 684k errors / 7d in ES from a single signature — fix-first situation. | (a) Sample frigate `*_total` counters from a live Prom scrape; (b) isolate top error signature in Kibana; (c) decide whether SLO measures detection throughput, detection latency, or error rate. |
| 5 | **home-assistant-core** | hactl is CLI-only. `Critical:` / `Warnings:` counts + `unavailable_entities` count are well-defined, but not queryable from Prom/ES until wrapped. | (a) Either expose hactl output as Prometheus metrics via a small in-cluster exporter, OR (b) add a new step inside `runbooks/sweep-run.py` (or a dedicated `hactl-check.py`) that polls hactl and inserts counts into `sweep_findings` via the existing `runbooks/lib/findings_writer.py` contract. (b) is cheaper — reuses the local-execution architecture instead of adding cluster-side surface. |
| 6 | **shelly** | (From plan-mode inventory.) Connected MQTT clients is countable via mosquitto exporter (`mosquitto_clients_connected`) but the *expected* count is hardcoded (~34–38). Numerator clear, denominator is a constant. | Acceptable for v0 — define denominator as a literal `36` when adding the SLO via `policy-cli slo add`, with a TODO to derive it dynamically. |

### Deferred (no signal yet, or intentionally out of scope)

| # | Integration | Reason | Revisit when |
|---|---|---|---|
| 7 | **flux** GitOps | Kustomization/HelmRelease `Ready` conditions are real-time only, no Prom exporter deployed. | Either deploy flux's built-in Prometheus exporter (small Helm values change), or have `runbooks/sweep-run.py` query `flux get` and emit reconcile counts to `sweep_findings` on each invocation. |
| 8 | **miele** cloud | Intentionally NOT an SLO target — measures vendor SaaS reliability, not anything you can act on. Documented as accepted-risk in `docs/troubleshooting/ha-upstream-integration-issues.md`. Allowlisted at 100 errors/cycle in the `noise_suppressions` table (category `known_ha_error_sources`). | Never. |

---

## 6) Verification Tests

For each entry marked `pilot-ready`:

```bash
# Mosquitto signal smoke test (port-forward, then PromQL via API)
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &
curl -s 'http://localhost:9090/api/v1/query?query=up{job="mosquitto"}' | jq

# Longhorn
curl -s 'http://localhost:9090/api/v1/query?query=count(longhorn_volume_robustness)' | jq

# UniFi (Unpoller)
curl -s 'http://localhost:9090/api/v1/query?query=count(unifipoller_device_uptime_seconds)' | jq
```

Each query must return a single sample (not an empty result). If empty, the signal isn't actually live and the entry must move from `pilot-ready` to `partial`.

---

## 7) Troubleshooting

**"Numerator returns 0 / empty"** — the metric name has drifted between exporter versions. Compare against the running pod's `/metrics` endpoint via `kubectl exec` (or `kubectl port-forward` + curl). Update the catalog entry.

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
- [sli-slo-framework.md](sli-slo-framework.md) — *(will exist after C4)* — the operator-facing SOP for adding new SLOs
- `slo_definitions` table in sweep_history Postgres — runtime SLO catalog; browse at `sweep.<DOMAIN>/policies/slos`
- [runbooks/slo-check.py](../../runbooks/slo-check.py) — *(will exist after C1)* — multi-backend calculator
- `noise_suppressions` table in sweep_history Postgres — informal thresholds being formalised as SLOs; browse at `sweep.<DOMAIN>/policies/noise`
- [unifi-controller-rate-limit.md](unifi-controller-rate-limit.md) — implicit UniFi SLO target (30s polling → 99% device-up)
- [docs/troubleshooting/ha-upstream-integration-issues.md](../troubleshooting/ha-upstream-integration-issues.md) — Miele accepted-risk posture

---

## Version History

| Date | Version | Change |
|---|---|---|
| 2026-05-19 | 2026.05.19 | Initial catalog — 8 entries, 3 pilot-ready, 3 partial, 2 deferred |
