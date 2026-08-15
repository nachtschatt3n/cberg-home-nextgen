---
plan_id: grafana-chart-migration
component: grafana
pr: null
kind: chart
current: "chart 10.5.15 (grafana.github.io, frozen) / Grafana app 12.4.8 (image-pinned)"
target: "chart 12.10.4 (grafana-community.github.io) / Grafana app 13.1.3 — delivered in 4 stages"
update_type: major
risk: high
est_duration_min: 180                 # sum of the four stages (30+45+45+60), for reference only
needs_reboot: false
touches:
  namespaces: [monitoring, flux-system]
  resources:
    - "see the individual stage plans — this file executes nothing"
  shared: [monitoring]
depends_on: []
conflicts_with: [kube-prometheus-stack-88]
status: superseded                    # INDEX ONLY — split into 4 stage plans on 2026-08-15
window: null                          # never schedule this file; schedule the stages
auto_execute: false
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/monitoring.md
  - docs/sops/backup.md
generated: "2026-08-14"
superseded_by:
  - grafana-repo-swap
  - grafana-chart-11
  - grafana-chart-12
  - grafana-13-app
---

# Grafana chart migration — INDEX (split into 4 stages, 2026-08-15)

**This file is an index. It executes nothing.** The original single plan was
90 minutes against a 90-minute maximum window — a 100%-booked window, where the
first thing sacrificed on an overrun is the rollback. It was split into four
stages, each of which leaves Grafana in a consistent, working, independently
revertible state.

| # | plan | what moves | risk | est | window |
|---|---|---|---|---|---|
| 1 | [`grafana-repo-swap`](grafana-repo-swap.md) | HelmRepository URL → `grafana-community`; **chart stays 10.5.15** | low | 30 m | `tue-early:2026-08-18` |
| 2 | [`grafana-chart-11`](grafana-chart-11.md) | chart 10.5.15 → **11.6.1**; app stays 12.4.8 | medium | 45 m | `thu-early:2026-08-27` |
| 3 | [`grafana-chart-12`](grafana-chart-12.md) | chart 11.6.1 → **12.10.4**; app *still* 12.4.8 | medium | 45 m | `tue-early:2026-09-01` |
| 4 | [`grafana-13-app`](grafana-13-app.md) | drop the image pin → **Grafana 13.1.3** | high | 60 m | `sat-early:2026-09-26` |

## Where the cut lines came from

The split point is **chart 11.6.1** — verified from the community repo index on
2026-08-15 as the last chart whose `appVersion` is still Grafana 12 (`12.4.3`);
chart `12.0.0` is where `appVersion` becomes Grafana 13. That makes it possible to
move the chart major and the application major in *different* windows:

```
10.5.15 → app 12.3.1     11.6.1 → app 12.4.3     12.0.0 → app 13.0.0     12.10.4 → app 13.1.3
                                  ↑ last Grafana-12 chart
```

The repo swap is separable and near-free because the community repo carries the
**identical 10.5.15 chart** (837 grafana entries, full history) — so stage 1
resolves to exactly what is running and must produce no rendered change at all.

The application major is the only genuinely one-way step: Grafana 13 migrates
folders and dashboards into unified storage on first start, so `git revert` alone
is not a rollback there. Isolating it is the point of the split.

## Facts carried forward from the original plan

- **The pinned repo is frozen**, not merely behind: `grafana.github.io/helm-charts`
  newest grafana chart is 10.5.15 / appVersion 12.3.1 (2026-01-30).
  `check-all-versions.py` reports grafana as "latest ✅" because it asks a repo that
  stopped answering.
- **No CVE urgency.** The 13 fixable criticals (grafana 12.3.1, k8s-sidecar 2.5.0,
  curl 8.9.1) were cleared on 2026-08-14 by pinning image tags on the existing chart.
  This migration is about leaving a dead repo.
- **The pins must survive stages 2 and 3.** Chart 11.6.1 defaults are *older* than the
  pins (sidecar 2.6.0, curl 8.19.0); only at chart 12.10.4 do the defaults equal them
  (2.10.1 / 8.21.0). Dropping them early re-opens the criticals.
- **The duplicate-`sidecar:`-key trap.** The first attempt at the CVE pin no-op'd
  because a second top-level `sidecar:` key was silently dropped by YAML
  last-one-wins while the HelmRelease still reported Ready. Every stage that pins
  anything verifies the **rendered Deployment**, not the HR status.
- **Never in the same window as `kube-prometheus-stack-88`** (`sat-early:2026-08-22`):
  both touch `monitoring`, and kps 88.3.0 resolves its own grafana dependency from
  the new repo.

## For the window agent

Schedule the **stages**, never this file. `depends_on` between them is a hard chain:
1 → 2 → 3 → 4. Each stage carries its own pre-checks, verification and rollback; none
of them says "see stage 1".
