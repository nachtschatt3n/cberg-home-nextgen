---
plan_id: grafana-repo-swap
component: grafana
pr: null                              # no Renovate PR: the pinned repo is frozen, so the
                                      # version checker reports grafana as "latest ✅"
kind: infra                           # HelmRepository source URL only — chart version unchanged
current: "HelmRepository grafana → https://grafana.github.io/helm-charts (chart 10.5.15)"
target: "HelmRepository grafana → https://grafana-community.github.io/helm-charts (chart 10.5.15, UNCHANGED)"
update_type: major                    # source migration; the chart version deliberately does not move
risk: low                             # same chart version, verified present in the new repo
est_duration_min: 30
needs_reboot: false
touches:
  namespaces: [flux-system, monitoring]
  resources:
    - helmrepository/grafana           # flux-system — the only object edited
    - helmrelease/grafana              # monitoring — re-resolves its source, version unchanged
  shared: [monitoring]                 # a failed source resolution stalls the grafana HR, and
                                       # grafana is how the cluster is observed
depends_on: []
conflicts_with: [kube-prometheus-stack-88]
status: draft
window: "tue-early:2026-08-18"
auto_execute: false
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/monitoring.md
generated: "2026-08-15"
---

# Grafana stage 1/4 — HelmRepository URL swap (chart version frozen at 10.5.15)

## 1) Summary & why held

Stage 1 of 4, split out of the former `grafana-chart-migration` (120→90 min,
un-schedulable in a 90 min window with rollback slack). This stage moves the
**source only**. Nothing else changes: chart stays `10.5.15`, all three CVE image
pins stay, values stay.

**Why it is needed.** `kubernetes/flux/meta/repositories/helm/grafana.yaml`
points at `https://grafana.github.io/helm-charts`. Verified against that repo's
`index.yaml` on 2026-08-15: its newest `grafana` chart is **10.5.15 /
appVersion 12.3.1, published 2026-01-30** — the repo is frozen. The live chart
moved to `https://grafana-community.github.io/helm-charts`, currently
**12.10.4 / appVersion 13.1.3 (2026-08-07)**. `check-all-versions.py` queries the
pinned repo, sees 10.5.15 as newest, and reports grafana as up to date. The green
result comes from a source that stopped answering.

**Why this stage is genuinely low risk — the evidence.** The community repo is a
full mirror plus continuation, not a fresh start: its index carries **837
grafana entries including `10.5.15` itself with the identical
`appVersion: 12.3.1`**. So the swap resolves to the *same chart version we run
today*. A correct execution produces **no change to any rendered object**.

```
grafana.github.io      newest grafana chart = 10.5.15 / app 12.3.1 (2026-01-30)  [frozen]
grafana-community.io   has 10.5.15 / app 12.3.1  ... through 12.10.4 / app 13.1.3
```

**What this stage explicitly does NOT do:** it does not bump the chart, does not
touch Grafana the application, and does not remove the 2026-08-14 CVE image pins.
Those are stages 2, 3 and 4 (`grafana-chart-11`, `grafana-chart-12`,
`grafana-13-app`).

## 2) Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) both repos actually serve what this plan claims — re-verify, don't trust the doc
for U in https://grafana.github.io/helm-charts https://grafana-community.github.io/helm-charts; do
  curl -sSL "$U/index.yaml" -o /tmp/idx.yaml
  python3 - "$U" <<'PY'
import sys, yaml, re
u = sys.argv[1]
d = yaml.safe_load(open("/tmp/idx.yaml"))
g = d["entries"]["grafana"]
k = lambda v: [int(p) for p in re.split(r"[.\-+]", v["version"])[:3] if p.isdigit()]
g.sort(key=k)
print(u)
print("  newest      :", g[-1]["version"], "app", g[-1].get("appVersion"))
print("  has 10.5.15 :", [x.get("appVersion") for x in g if x["version"] == "10.5.15"])
PY
done
# REQUIRED: grafana-community must list 10.5.15 with appVersion 12.3.1. If it does not,
# STOP — this stage's whole safety argument is that the target version already exists there.

# b) current live state, to compare against afterwards
mise exec -- flux get sources helm -n flux-system grafana
mise exec -- kubectl get hr -n monitoring grafana \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.lastAppliedRevision}{"\n"}'   # True 10.5.15
mise exec -- kubectl get deploy -n monitoring grafana \
  -o jsonpath='{range .spec.template.spec.containers[*]}{.name}={.image}{"\n"}{end}'
mise exec -- kubectl get deploy -n monitoring grafana -o jsonpath='{.metadata.generation}{"\n"}'
mise exec -- kubectl exec -n monitoring deploy/grafana -c grafana -- \
  sh -c 'find /var/lib/grafana/dashboards -name "*.json" | wc -l'      # record the number (expect 38)

# c) nothing else in flight
mise exec -- flux get kustomizations -A | awk 'NR==1 || $5!="True"'
mise exec -- flux get helmreleases -A   | awk 'NR==1 || $5!="True"'
```

## 3) Steps

1. **Active-update marker** so alert triage treats a brief grafana blip as EXPECTED:
   ```bash
   runbooks/update-marker.sh add grafana monitoring 1 "HelmRepository URL swap to grafana-community (chart unchanged)"
   ```
2. **Edit the HelmRepository URL only** in
   `kubernetes/flux/meta/repositories/helm/grafana.yaml`:
   ```yaml
   spec:
     interval: 1h
     url: https://grafana-community.github.io/helm-charts
   ```
   Add a one-line comment recording that `grafana.github.io` is frozen at 10.5.15.
3. **Confirm the HelmRelease is untouched** — this stage must not move the chart:
   ```bash
   grep -n 'version: 10.5.15' kubernetes/apps/monitoring/grafana/app/helmrelease.yaml
   git diff --stat        # exactly ONE file, exactly one changed line (+ comment)
   ```
4. **Commit + push** (work on `main`, stage only this file):
   ```bash
   git add kubernetes/flux/meta/repositories/helm/grafana.yaml
   git commit -m "chore(grafana): point HelmRepository at grafana-community (chart stays 10.5.15)"
   git push
   ```
5. Let Flux reconcile the source on its own. Do **not** force-reconcile the
   HelmRelease: the desired chart version has not changed, so a healthy outcome is
   Helm making no release at all.
6. On success clear the marker: `runbooks/update-marker.sh clear grafana`.

## 4) Verification

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) the SOURCE re-resolved against the new URL
mise exec -- kubectl get helmrepository -n flux-system grafana \
  -o jsonpath='{.spec.url}{"  ready="}{.status.conditions[?(@.type=="Ready")].status}{"\n"}'
# expect the grafana-community URL and ready=True. A 404/index parse error shows up here
# FIRST — this is the failure this stage is designed to catch cheaply.

# b) the HelmRelease is still on 10.5.15 and Ready
mise exec -- kubectl get hr -n monitoring grafana \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.lastAppliedRevision}{"\n"}'   # True 10.5.15

# c) THE load-bearing check — nothing was re-rendered. Same images, same generation.
mise exec -- kubectl get deploy -n monitoring grafana \
  -o jsonpath='{range .spec.template.spec.containers[*]}{.name}={.image}{"\n"}{end}'
mise exec -- kubectl get deploy -n monitoring grafana -o jsonpath='{.metadata.generation}{"\n"}'
# images MUST equal the pre-check values (grafana 12.4.8, k8s-sidecar 2.10.1) and the
# Deployment generation MUST be unchanged. A bumped generation means the render moved —
# investigate before leaving the window; it should be a byte-identical chart.

# d) grafana still serves and still has its dashboards
mise exec -- kubectl get pods -n monitoring -l app.kubernetes.io/name=grafana   # Ready, 0 new restarts
mise exec -- kubectl exec -n monitoring deploy/grafana -c grafana -- \
  sh -c 'find /var/lib/grafana/dashboards -name "*.json" | wc -l'              # same count as pre-check
DOM=$(mise exec -- kubectl get secret -n flux-system cluster-secrets -o jsonpath='{.data.SECRET_DOMAIN}' | base64 -d)
curl -s -o /dev/null -w '%{http_code}\n' --max-time 20 "https://grafana.$DOM/api/health"   # 200
```

Success = HelmRepository Ready on the new URL, HR Ready on 10.5.15, Deployment
generation and container images **unchanged**, dashboard count unchanged, `/api/health` 200.

## 5) Rollback

One-line revert; there is no data path involved.

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <swap-commit-sha>     # restores https://grafana.github.io/helm-charts
git push
mise exec -- kubectl get helmrepository -n flux-system grafana \
  -o jsonpath='{.spec.url}{"  ready="}{.status.conditions[?(@.type=="Ready")].status}{"\n"}'
mise exec -- kubectl get hr -n monitoring grafana \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.lastAppliedRevision}{"\n"}'   # True 10.5.15
```

Confirmed back = old URL, source Ready, HR Ready on 10.5.15, grafana pod unchanged.
Because the chart version never moved, no Helm rollback and no PVC restore can be
required by this stage.

## 6) Interference notes

- **Runs out of order → nothing works downstream.** `grafana-chart-11` (stage 2)
  requests chart `11.6.1`, which exists **only** in the community repo. Running
  stage 2 before this one leaves the HelmRelease unable to resolve its chart:
  the HR goes not-Ready with a "chart version not found" error while the running
  pod keeps serving. Recovery is to run this stage; nothing is lost, but the
  window is wasted.
- **`conflicts_with: kube-prometheus-stack-88`** — that plan is on
  `sat-early:2026-08-22` and also touches `monitoring`. This stage is deliberately
  4 days earlier and must be **verified green and left settled** before it. If this
  stage is rolled back or its verification is inconclusive, tell the operator
  before kps-88's window opens: debugging a monitoring problem across two
  monitoring changes is what the separation is for.
- kube-prometheus-stack sets `grafana.enabled: false`
  (`helmvalues.yaml:274`), so this standalone release is the only grafana in the
  cluster. Nothing in kps consumes this HelmRepository.
- Grafana is the cluster's viewing surface: do not co-schedule with any plan
  whose verification depends on dashboards.
