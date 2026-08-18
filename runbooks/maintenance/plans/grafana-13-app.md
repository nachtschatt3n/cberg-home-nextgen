---
plan_id: grafana-13-app
component: grafana
pr: null
kind: image                           # application major on an already-migrated chart
current: "Grafana app 12.4.8 (image.tag pin) on chart 12.10.4"
target: "Grafana app 13.1.3 (chart 12.10.4 appVersion default — pin removed)"
update_type: major
risk: high                            # one-way DB migration to unified storage on first start
est_duration_min: 60
needs_reboot: false
touches:
  namespaces: [monitoring]
  resources:
    - helmrelease/grafana
    - deployment/grafana
    - pvc/grafana-config               # grafana.db — MIGRATED IN PLACE, not reversible by git
    - "longhorn:volume/grafana-config" # backup = the only true rollback
    - "38 provisioned dashboards + 6 provisioned datasources"
    - "Authentik OIDC login for grafana"
  shared: [monitoring]
depends_on: [grafana-chart-12]
conflicts_with: []                    # RESOLVED 2026-08-18: kube-prometheus-stack-88 EXECUTED — dead ref removed
status: draft
window: "sun-window:2026-09-13"                 # RESHUFFLED 2026-08-16 onto the daily-window cadence
                                      # (7 windows/week, was 4). Deliberate soaks are
                                      # preserved, not compressed — see the windows YAML.
auto_execute: false
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/monitoring.md
  - docs/sops/backup.md
  - docs/sops/longhorn.md
generated: "2026-08-15"
---

# Grafana stage 4/4 — application 12.4.8 → 13.1.3 (drop the image pin)

## 1) Summary & why held

Final stage. The chart is already at 12.10.4 (stage 3); the only remaining
difference from upstream default is our `image.tag: "12.4.8"` pin. Removing it
takes the application to the chart's appVersion **13.1.3**.

**This is the stage that is genuinely one-way, and the reason the migration was
split.** From Grafana's own 13.0 upgrade guide:

> *"Grafana automatically migrates folders and dashboards to unified storage on
> startup. Legacy SQL tables (`dashboard`, `dashboard_acl`,
> `dashboard_provisioning`, `dashboard_version`, `dashboard_tag`,
> `library_element_connection`, `folder`) are deprecated… Downgrades after
> migration will not reflect changes made in unified storage without restoring
> backups."*

So `git revert` alone is **not** a rollback once Grafana 13 has started against
`grafana.db`. The rollback is: revert **and** restore the `grafana-config`
Longhorn volume. That is why this stage is `risk: high`, sits in a 90-minute
weekend window with 30 minutes of slack, and requires an operator present.

**Also from the 13.0 guide, checked against this deployment:**

| upstream breaking change | applies here? |
|---|---|
| v13.0.0 pulled over a Git Sync migration bug; fixed in 13.0.1 | **No** — target is 13.1.3, and no Git-Sync/provisioning feature flags are set. |
| Image renderer plugin support removed; must run as a separate service | **No** — `imageRenderer.enabled` is false (never set in our values). |
| `grafana-cli` / `grafana-server` commands removed (use `grafana cli` / `grafana server`) | **No** — the chart's entrypoint is used; we run no custom commands. |
| Legacy single-tenant Alertmanager API endpoints removed/restricted | **Low** — alerting is Prometheus/Alertmanager via kube-prometheus-stack; no Grafana-managed alert rules are provisioned here. |
| Data source APIs by numeric ID disabled by default; use UIDs | **No** — every provisioned datasource in the HelmRelease declares an explicit `uid`. |
| RBAC tightening for custom/UID-scoped roles | **No** — no custom RBAC roles; access is Authentik OIDC + default roles. |
| React 18 → 19 (plugin impact) | **Watch** — no third-party plugins are installed (`plugins:` unset), but 38 imported community dashboards render through core panels; a panel that fails to render is the realistic failure mode. |

**Housekeeping in the same commit (safe, verified):** at chart 12.10.4 the other
two pins equal the chart defaults exactly (`sidecar.image.tag: 2.10.1`,
`downloadDashboardsImage.tag: 8.21.0`), so dropping them changes nothing today
and lets them track the chart again. Prove it in the render before dropping
(step 3) — do not drop on trust.

## 2) Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) stage 3 landed and has soaked
mise exec -- kubectl get hr -n monitoring grafana \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.lastAppliedRevision}{"\n"}'   # True 12.10.4
mise exec -- kubectl get deploy -n monitoring grafana \
  -o jsonpath='{range .spec.template.spec.containers[*]}{.name}={.image}{"\n"}{end}'                  # grafana 12.4.8

# b) confirm which app version you are ACTUALLY about to install (appVersion can move)
curl -sSL https://grafana-community.github.io/helm-charts/index.yaml -o /tmp/gc.yaml
python3 - <<'PY'
import yaml
d = yaml.safe_load(open("/tmp/gc.yaml"))
print([ (x["version"], x.get("appVersion")) for x in d["entries"]["grafana"] if x["version"] == "12.10.4" ])
PY
# If appVersion is not 13.1.x, STOP and re-plan — this plan's evidence is for 13.1.3.

# c) THE mandatory backup. This is the rollback; without a fresh one, do not start.
#    Trigger a Longhorn backup of volume `grafana-config` and wait for it to complete.
mise exec -- kubectl get volume -n storage grafana-config \
  -o custom-columns=NAME:.metadata.name,STATE:.status.state,ROBUST:.status.robustness,LASTBACKUP:.status.lastBackupAt
# require: state=attached, robustness=healthy, lastBackupAt within the hour.

# d) capture the pre-migration state to diff against
mise exec -- kubectl exec -n monitoring deploy/grafana -c grafana -- \
  sh -c 'find /var/lib/grafana/dashboards -name "*.json" | wc -l'        # record (expect 38)
mise exec -- kubectl exec -n monitoring deploy/grafana -c grafana -- \
  sh -c 'ls -l /var/lib/grafana/grafana.db'                              # size + mtime
DOM=$(mise exec -- kubectl get secret -n flux-system cluster-secrets -o jsonpath='{.data.SECRET_DOMAIN}' | base64 -d)
# With an admin API token or via the UI, record the inventory you must see again afterwards:
#   number of dashboards, number of folders, list of datasource UIDs.
curl -s --max-time 20 "https://grafana.$DOM/api/health"                  # version 12.4.8, database ok

# e) no in-flight reconcile; operator present
mise exec -- flux get kustomizations -A | awk 'NR==1 || $5!="True"'
```

## 3) Steps

1. **Marker** (expect a longer-than-usual gap: the first 13.x start runs a DB migration):
   ```bash
   runbooks/update-marker.sh add grafana monitoring 2 "grafana app 12.4.8 -> 13.1.3 (unified storage migration)"
   ```
2. **Prove the pins are no-ops at this chart version, before removing them**:
   ```bash
   cd /tmp && rm -rf g13 && mkdir g13 && cd g13
   curl -sSL -o g.tgz https://github.com/grafana-community/helm-charts/releases/download/grafana-12.10.4/grafana-12.10.4.tgz
   tar xzf g.tgz
   python3 - <<'PY'
import yaml
d = yaml.safe_load(open("grafana/values.yaml"))
print("sidecar default        :", d["sidecar"]["image"]["tag"])          # must be >= 2.10.1
print("downloadDashboards dflt:", d["downloadDashboardsImage"]["tag"])   # must be >= 8.21.0
PY
   ```
   If either default is **lower** than the current pin, keep that pin and drop only
   the other — never let this stage regress a CVE fix.
3. **Edit `kubernetes/apps/monitoring/grafana/app/helmrelease.yaml`**: remove the
   `image.tag: "12.4.8"` override (and the two now-equal pins proven in step 2),
   leaving the surrounding comment block rewritten to record that the app now
   follows the chart's appVersion. Chart version stays `12.10.4`.
   ```bash
   grep -n 'tag:' kubernetes/apps/monitoring/grafana/app/helmrelease.yaml   # review every remaining tag
   grep -c '^    sidecar:' kubernetes/apps/monitoring/grafana/app/helmrelease.yaml   # still exactly 1
   ```
4. **Render and read the actual Deployment object** (the anti-no-op check; a values
   key at the wrong path silently does nothing while the HR reports Ready):
   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   mise exec -- yq '.spec.values' kubernetes/apps/monitoring/grafana/app/helmrelease.yaml \
     | sed -e 's/\${SECRET_DOMAIN}/example.invalid/g' \
           -e 's/\${INFLUXDB_ORG}/org/g' -e 's/\${INFLUXDB_BUCKET}/bucket/g' > /tmp/g13/values.yaml
   mise exec -- helm template grafana /tmp/g13/grafana -n monitoring -f /tmp/g13/values.yaml \
     | mise exec -- yq 'select(.kind=="Deployment" and .metadata.name=="grafana")
                        | [.spec.template.spec.containers[].image,
                           .spec.template.spec.initContainers[].image]'
   # expect grafana/grafana:13.1.3 and k8s-sidecar >= 2.10.1
   ```
5. **Validate, commit, push** (on `main`, stage only this file):
   ```bash
   mise exec -- kubeconform -summary -exit-on-error -ignore-missing-schemas kubernetes/apps/monitoring/grafana
   git add kubernetes/apps/monitoring/grafana/app/helmrelease.yaml
   git commit -m "feat(grafana): take Grafana 13.1.3 (drop image pin; chart 12.10.4)"
   git push
   ```
   `deploymentStrategy: Recreate` — the old pod goes first, then 13.1.3 starts and
   migrates folders/dashboards into unified storage. Watch the log live:
   ```bash
   mise exec -- kubectl logs -n monitoring deploy/grafana -c grafana -f | grep -iE 'migrat|unified|error|fatal'
   ```
6. Clear the marker only after §4 fully passes: `runbooks/update-marker.sh clear grafana`.

## 4) Verification

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) release + rollout
mise exec -- kubectl get hr -n monitoring grafana \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.lastAppliedRevision}{"\n"}'   # True 12.10.4
mise exec -- kubectl rollout status deploy/grafana -n monitoring --timeout=600s
mise exec -- kubectl get deploy -n monitoring grafana \
  -o jsonpath='{range .spec.template.spec.containers[*]}{.name}={.image}{"\n"}{end}'                  # grafana 13.1.3

# b) the migration completed cleanly
mise exec -- kubectl logs -n monitoring deploy/grafana -c grafana --since=30m \
  | grep -iE 'migrat|unified storage|error|fatal|panic' | head -40
mise exec -- kubectl get pods -n monitoring -l app.kubernetes.io/name=grafana -o json | python3 -c "
import sys, json
for p in json.load(sys.stdin)['items']:
    for cs in p['status'].get('containerStatuses', []):
        print(cs['name'], cs['image'], 'ready', cs['ready'], 'restarts', cs['restartCount'])"

# c) provisioning survived
mise exec -- kubectl exec -n monitoring deploy/grafana -c grafana -- \
  sh -c 'find /var/lib/grafana/dashboards -name "*.json" | wc -l'        # same as pre-check (38)
DOM=$(mise exec -- kubectl get secret -n flux-system cluster-secrets -o jsonpath='{.data.SECRET_DOMAIN}' | base64 -d)
curl -s --max-time 20 "https://grafana.$DOM/api/health"                  # database ok, version 13.1.3

# d) THE load-bearing check is human, not a probe. Grafana can report perfectly healthy
#    with an empty library or dead panels:
#      * log in via Authentik OIDC (the OAuth path is a real 13.x risk area);
#      * dashboard COUNT and FOLDER count match the pre-check inventory;
#      * open one dashboard per datasource — Prometheus, Elasticsearch, InfluxDB,
#        TeslaMate, Pellets, Unpoller InfluxDB — and confirm panels render DATA;
#      * spot-check two imported community dashboards (React 19 panel regressions
#        show up as a broken panel, not a failed pod).
```

Success = HR Ready, grafana on `13.1.3` with 0 restart loops, migration log clean,
dashboard/folder inventory matching the pre-check, OIDC login working, and every
datasource rendering data.

## 5) Rollback

**`git revert` alone is NOT sufficient once 13.1.3 has started.** Two cases:

**Case A — the pod never came up / migration failed early (no successful 13.x start).**
```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <grafana13-commit-sha>       # restores image.tag 12.4.8 (+ the pins)
git push
mise exec -- kubectl rollout status deploy/grafana -n monitoring --timeout=600s
mise exec -- kubectl get deploy -n monitoring grafana \
  -o jsonpath='{range .spec.template.spec.containers[*]}{.name}={.image}{"\n"}{end}'   # 12.4.8
curl -s --max-time 20 "https://grafana.$DOM/api/health"                                # version 12.4.8
```
If 12.4.8 starts and the dashboard inventory matches the pre-check, you are back.

**Case B — 13.1.3 started and migrated `grafana.db` (the expected case).** Revert the
commit as in Case A **and restore the volume**, or 12.4.8 will run against a
migrated database:
```bash
mise exec -- kubectl scale deploy/grafana -n monitoring --replicas=0     # release the RWO volume
# restore Longhorn volume `grafana-config` from the pre-check backup per docs/sops/longhorn.md
#   + docs/sops/backup.md, then:
mise exec -- kubectl scale deploy/grafana -n monitoring --replicas=1
mise exec -- kubectl rollout status deploy/grafana -n monitoring --timeout=600s
```
Anything created in Grafana between the backup and the rollback is lost — for this
instance that is dashboards edited in the UI (all 38 provisioned dashboards and all
datasources are re-provisioned from git on start, so they come back regardless).

If Helm wedges `pending-upgrade`, clear it per `docs/sops/application-update.md` §11.

**Recovery floor:** the nightly Longhorn backup of `grafana-config` (CronJob
`storage/backup-of-all-volumes`, 03:00) — but take the fresh one in pre-check (c);
do not rely on the nightly.

## 6) Interference notes

- **Out of order:** this stage assumes chart 12.10.4 is already live and soaked. Run
  it before `grafana-chart-12` and you either get chart-11 defaults (Grafana 12.4.3,
  a silent *downgrade* of the running app) or, if the chart bump is folded in, one
  window containing a chart major *and* an app major with a non-reversible DB
  migration — the exact combination this 4-stage split exists to avoid.
- **The rollback needs the window's slack.** A PVC restore is minutes of Longhorn
  work plus a restart; 60 min of work in a 90 min window leaves room for it. Do not
  co-schedule anything else here.
- **`conflicts_with: kube-prometheus-stack-88`** — shared `monitoring` namespace.
  More practically: Grafana is how the cluster is observed, and this stage takes it
  down and migrates its database. Nothing whose verification needs dashboards may
  share this window.
- The k8s-sidecar watches dashboards in **all** namespaces
  (`sidecar.dashboards.searchNamespace: ALL`), so other apps' dashboard ConfigMaps
  are re-imported into the migrated store. Check a dashboard owned by another app
  (e.g. a Flux or TeslaMate one) as part of the smoke test, not only a monitoring one.
- After this stage the HelmRelease carries **no** image pins; grafana returns to
  normal auto-update coverage against the community chart. Tell the operator — it
  changes what the version checker will report from the next sweep onward.
