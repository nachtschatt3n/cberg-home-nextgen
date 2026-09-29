---
plan_id: grafana-13.2.6
component: grafana
pr: null                            # no Renovate PR; coverage direct-bump candidate held by G3
kind: chart
current: "13.2.5"
target: "13.2.6"
update_type: patch
risk: low
est_duration_min: 15
needs_reboot: false
touches:
  namespaces: [monitoring]
  resources:
    - helmrelease/monitoring/grafana
    - deployment/monitoring/grafana            # one Recreate roll (pod template changes)
    - kustomization/monitoring/grafana
    - pvc/monitoring/grafana-config            # mounted, not modified; no sqlite migration this hop
    - configmap/monitoring/grafana
    - configmap/monitoring/grafana-dashboards-default
    - configmap/monitoring/grafana-dashboards-flux
    - configmap/monitoring/grafana-dashboards-kubernetes
    - configmap/monitoring/grafana-dashboards-nginx
    - configmap/monitoring/grafana-dashboards-teslamate
    - servicemonitor/monitoring/grafana
    - httproute/monitoring/grafana             # unchanged; Grafana UI is down ~1 min during Recreate
    - kubernetes/apps/monitoring/grafana/app/helmrelease.yaml
  shared: [monitoring]                # Grafana is the monitoring UI; it is NOT a
                                      # dependency of Prometheus/Alertmanager, so
                                      # alerting keeps working through the roll.
depends_on: []
conflicts_with:
  - flux-oci-chart-sources            # swaps grafana's chart source AND rolls deployment/grafana
  - helm-drift-detection              # writes a field on every HelmRelease incl. grafana
  - flux-reconciler-impersonation     # changes how helm-controller reconciles every HR
  - flux-fleet-0.60.0                 # helm-controller swap mid-upgrade would confound the verdict
exclusive: false
security_ref: null                    # no security driver; the running image is unchanged by this hop
capability_change: false              # chart packaging patch: same app (13.2.2), same features;
                                      # only tightens container securityContext of 3 helper containers
rollback_class: git-revert            # appVersion 13.2.2 on both sides -> no forward-only
                                      # sqlite/unified-storage migration is crossed
finding_refs: [F-cce839da]
review: null
status: draft
window: null
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/grafana-image-changes.md
  - docs/sops/verification-contents-not-shape.md
premises:
  - id: live-chart-still-13.2.5
    why: "Diff/rollback baseline. If the chart already moved, this plan is stale."
    run: kubectl get helmrelease grafana -n monitoring -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: "13.2.5"
  - id: helmrelease-ready
    why: "Do not stack a bump on an already-failing release."
    run: kubectl get helmrelease grafana -n monitoring -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: live-image-13.2.2-distroless
    why: >-
      The low-risk / git-revert verdict rests on the RUNNING app being 13.2.2
      with no image.tag override, so the target chart renders the SAME image.
    run: kubectl get deploy grafana -n monitoring -o jsonpath='{.spec.template.spec.containers[?(@.name=="grafana")].image}'
    expect_exact: "docker.io/grafana/grafana:13.2.2-distroless"
  - id: repo-cache-has-target
    why: >-
      The appVersion premise below reads the LOCAL helm index; a stale cache
      fails exactly like a moved appVersion. Run `helm repo update
      grafana-community` first if this fails. (Alias grafana-community =
      grafana-community.github.io/helm-charts, the same URL as the in-cluster
      HelmRepository flux-system/grafana. The local alias named `grafana` is a
      DIFFERENT, frozen repo -- do not use it.)
    run: helm show chart grafana-community/grafana --version 13.2.6 | grep '^version:'
    expect_exact: "version: 13.2.6"
  - id: target-appversion-unchanged
    why: >-
      Central claim. Chart 13.2.6 must ship appVersion 13.2.2 (identical to
      the running app); if it moved, this plan is void and must be re-triaged
      per docs/sops/grafana-image-changes.md (forward-only migration).
    run: helm show chart grafana-community/grafana --version 13.2.6 | grep '^appVersion:'
    expect_exact: "appVersion: 13.2.2"
  - id: no-absolute-sidecar-folder-annotation
    why: >-
      k8s-sidecar 2.11.2 (_get_destination_folder in src/resources.py) writes
      to an ABSOLUTE grafana_folder annotation verbatim, bypassing the
      emptyDir mounted at /var/lib/grafana/dashboards/sidecar. With the new
      readOnlyRootFilesystem that write would hit EROFS. Every live annotation
      must be relative (measured 2026-09-29 -- Pellets, Media, UniFi, or none).
    run: kubectl get cm,secret -A -l grafana_dashboard -o jsonpath='{range .items[*]}{.metadata.annotations.grafana_folder}{"\n"}{end}' | awk '/^\//{n++} END{print n+0}'
    expect_exact: "0"
  - id: no-values-override-of-hardened-contexts
    why: >-
      The render diff in section 1 assumes we set neither
      sidecar.securityContext nor downloadDashboards.*; an override added
      since would change what the chart default does to us.
    run: kubectl get helmrelease grafana -n monitoring -o jsonpath='{.spec.values.sidecar.securityContext}{.spec.values.downloadDashboards}' | wc -c | tr -d ' '
    expect_exact: "0"
generated: "2026-09-29"
---

# grafana: chart 13.2.5 -> 13.2.6 (patch, appVersion unchanged at 13.2.2)

## 1) Summary & why held

**Why held.** Coverage G3 reported `unverified (release notes unavailable)`, and
with 0 green / 0 reverts in 90 days of earned autonomy an unverified bump may not
take the unattended lane. It was a lookup miss, not a real absence: the notes
exist as GitHub release `grafana-13.2.6` in `grafana-community/helm-charts`,
published 2026-09-27. See the report for the repo correction (G3 probably does
not resolve the monorepo's `<chart>-<version>` tag form).

**What changed upstream.** Quoted from the release notes:

> * [CI] Update dependency databus23/helm-diff to v3.15.15 (#834)
> * [grafana] Harden testFramework, downloadDashboards, sidecar, and
>   imageRenderer securityContext defaults (#790)

PR #790 says: "downloadDashboards.securityContext / sidecar.securityContext:
added readOnlyRootFilesystem: true. Both containers only ever write to
already-mounted emptyDir/PVC paths, so this is safe by default." The PR also
fixed `.helmignore`, where `tests/` had matched `templates/tests/`, so the
testFramework templates now ship in the package.

**Measured, not assumed (2026-09-29).**

1. **appVersion is 13.2.2 on both sides.** `helm show chart
   grafana-community/grafana --version {13.2.5,13.2.6}` returns
   `appVersion: 13.2.2` for both. The chart templates the image as
   `{{ .Chart.AppVersion }}-distroless` with no pin, and the live image is
   `grafana:13.2.2-distroless`. The Grafana binary does not change, no sqlite or
   unified-storage migration is crossed, and `git revert` is a complete
   rollback.
2. **Chart source diff** (`helm pull` both, `diff -r`): only `Chart.yaml`
   version, `.helmignore` (`ci/`→`/ci/`, `tests/`→`/tests/`), a new
   `templates/tests/` directory, and `values.yaml` securityContext defaults for
   testFramework, downloadDashboards, sidecar and imageRenderer.
3. **Render diff against OUR values** (`helm template` of both charts fed the
   real `spec.values` from `helmrelease.yaml`) changes exactly two things:
   - the `helm.sh/chart: grafana-13.2.5 → grafana-13.2.6` label on every object,
     including the pod template;
   - `readOnlyRootFilesystem: true` added to exactly **three containers**:
     init `download-dashboards` (curl 8.22.0), `grafana-sc-dashboard`, and
     `grafana-sc-datasources` (k8s-sidecar 2.11.2).
   `testFramework.enabled: false` means the newly packaged test templates render
   nothing. imageRenderer is not enabled, so its new pod/container contexts
   render nothing. The `grafana` container's own securityContext is identical on
   both sides, and so are the selector, strategy (`Recreate`), volumes and
   `grafana.ini`.

**Is readOnlyRootFilesystem safe for OUR three containers?** Checked against
upstream code, not taken from the PR's claim:

- `download-dashboards` runs the rendered `download_dashboards.sh`. It does
  `mkdir -p /var/lib/grafana/dashboards/*`, then `curl -skf … | sed … > <file>`.
  Every write lands on `/var/lib/grafana`, the `grafana-config` PVC mount, which
  is writable. It uses pipes with no temp files and no `sed -i`. The script runs
  `set -eufo pipefail`, so a failed write fails the init container and the pod
  stays in `Init:Error`. That failure is loud.
- `k8s-sidecar` 2.11.2 (`src/helpers.py` `write_data_to_file`) writes only via
  `os.makedirs(folder)` + `open(<folder>/<file>)`. `folder` is `FOLDER` joined
  with a **relative** `grafana_folder` annotation, which stays inside the
  emptyDir mounts (`/var/lib/grafana/dashboards/sidecar`,
  `/etc/grafana/provisioning/datasources`). The only escape is an **absolute**
  annotation (`_get_destination_folder`: `if os.path.isabs(...)`). All 37 live
  labeled objects carry relative or no annotations, and a premise guards this.
  The image already runs as uid 65534 over a root-owned `/app`, so it could not
  write its root filesystem before this change either.

**Verdict.** The hold was a false positive of the release-notes lookup. The
actual change is a chart-packaging patch: one pod roll and three containers
losing a write path that they provably do not use. `risk: low`, no reboot,
`git-revert`. Not a capability change.

**House hazards, checked.**
- `GF_PLUGINS_PREINSTALL_DISABLED: "true"` is set in our `env:` and untouched by
  this hop. The roll is still a restart, and a restart is never neutral on
  distroless (SOP §7). The datasource gate in §4 is therefore mandatory.
- Grafana 13 unified storage (`a0556c6d`): there is no app version change, so no
  unified-storage migration runs. The migrator lines must still read
  `performed=0` (§4.3).

## 2) Pre-checks

Run `helm repo update grafana-community` first, then the premises:
`.venv/bin/python3 runbooks/plan-premises.py grafana-13.2.6`. All must pass.

Then record the baseline. The numbers below were measured 2026-09-29; re-measure,
because the post-change comparison is against the live baseline, not these.

```bash
U=$(kubectl -n monitoring get secret grafana-admin-secret -o jsonpath='{.data.admin-user}' | base64 -d)
P=$(kubectl -n monitoring get secret grafana-admin-secret -o jsonpath='{.data.admin-password}' | base64 -d)
kubectl -n monitoring port-forward svc/grafana 33011:80 >/dev/null 2>&1 & PF=$!; sleep 4
curl -s http://127.0.0.1:33011/api/health                                   # 2026-09-29: version 13.2.2, database ok
curl -s -u "$U:$P" 'http://127.0.0.1:33011/api/plugins?embedded=0&type=datasource' \
  | python3 -c 'import sys,json; print("ds_plugins="+str(len(json.load(sys.stdin))))'   # 2026-09-29: 18
curl -s -u "$U:$P" 'http://127.0.0.1:33011/api/search?type=dash-db&limit=5000' \
  | python3 -c 'import sys,json; print("dashboards="+str(len(json.load(sys.stdin))))'   # 2026-09-29: 72
kill $PF

# number of sidecar-sourced dashboard objects = expected "Writing" count after the roll
kubectl get cm,secret -A -l grafana_dashboard -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' | wc -l   # 2026-09-29: 37

# Longhorn backup of the config volume exists (belt-and-braces; not needed for this rollback class)
kubectl get volume -n storage grafana-config -o jsonpath='{.status.lastBackupAt}{"\n"}'   # must be < 26h old
```

Record `BASE_DS`, `BASE_DASH` and `BASE_SC`. They are the pass bars in §4.

## 3) Steps (GitOps)

Low-risk patch path of `docs/sops/application-update.md`: commit, push, let Flux
reconcile, verify. No alert silence is needed. Grafana's ~1 min Recreate gap
fires no Prometheus/Alertmanager alert on its own. If the window agent
standardises on silences, add a 30 min silence scoped to `namespace=monitoring`,
`alertname=~"KubePod.*|KubeDeployment.*"`.

1. Edit the chart pin. This was dry-tested on a scratch copy with BSD sed and the
   resulting diff is exactly `11c11 <       version: 13.2.5 --- >       version: 13.2.6`:
   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   sed -i '' 's/^      version: 13\.2\.5$/      version: 13.2.6/' kubernetes/apps/monitoring/grafana/app/helmrelease.yaml
   git diff --stat kubernetes/apps/monitoring/grafana/app/helmrelease.yaml   # expect: 1 insertion, 1 deletion
   ```
2. Commit only that path, then verify authorship before push:
   ```bash
   git commit --only kubernetes/apps/monitoring/grafana/app/helmrelease.yaml \
     -m "chore(grafana): chart 13.2.5 -> 13.2.6 (appVersion unchanged 13.2.2; securityContext hardening of helper containers) [plan grafana-13.2.6, F-cce839da]"
   git log -1 --format=%s     # must be the subject above
   git show --stat HEAD       # must list only helmrelease.yaml
   git push
   ```
3. Reconcile only if the webhook has not picked it up within ~2 min. The
   Kustomization lives in namespace **monitoring**, not flux-system:
   ```bash
   flux reconcile kustomization grafana -n monitoring --with-source
   kubectl -n monitoring get hr grafana -o jsonpath='{.spec.chart.spec.version}{"\n"}'   # must print 13.2.6 BEFORE judging the upgrade
   ```
4. Wait for the Recreate roll:
   ```bash
   kubectl rollout status deployment/grafana -n monitoring --timeout=300s
   ```
   `rollout status` can green-light the old generation, so §4.1 checks the pod
   itself.

## 4) Verification

Every gate states the failure it catches. Run all of them.

**4.1 Release landed and the NEW pod runs it.**
```bash
kubectl get hr grafana -n monitoring -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion}{"\n"}'
# PASS: "True 13.2.6". FAIL prints False / 13.2.5 (upgrade failed or not reconciled).
POD=$(kubectl -n monitoring get pods -l app.kubernetes.io/name=grafana -o jsonpath='{.items[0].metadata.name}')
kubectl -n monitoring get pod $POD -o jsonpath='{.metadata.labels.helm\.sh/chart} {.status.startTime}{"\n"}'
# PASS: grafana-13.2.6 and a startTime after the push. FAIL: grafana-13.2.5 = old pod still serving.
kubectl -n monitoring get pod $POD -o jsonpath='{range .spec.initContainers[*]}{.name}={.securityContext.readOnlyRootFilesystem}{"\n"}{end}{range .spec.containers[*]}{.name}={.securityContext.readOnlyRootFilesystem}{"\n"}{end}'
# PASS: download-dashboards=true, grafana-sc-dashboard=true, grafana-sc-datasources=true, grafana=true,
#       init-chown-data=false. FAIL: an empty value for the three = the hardening did not render (wrong chart).
kubectl -n monitoring get deploy grafana -o jsonpath='{.spec.template.spec.containers[?(@.name=="grafana")].image}{"\n"}'
# PASS: docker.io/grafana/grafana:13.2.2-distroless. Any other tag = appVersion premise was wrong -> STOP, roll back.
```

**4.2 The three hardened containers did their writes.**
```bash
kubectl -n monitoring get pod $POD -o jsonpath='{range .status.initContainerStatuses[*]}{.name} {.state.terminated.reason} {.state.terminated.exitCode}{"\n"}{end}'
# PASS: "download-dashboards Completed 0". A failed write under set -euo pipefail
# prints Error / non-zero exit and the pod sits in Init:Error.
kubectl -n monitoring get pod $POD -o jsonpath='{range .status.containerStatuses[*]}{.name} restarts={.restartCount}{"\n"}{end}'
# PASS: restarts=0 for all three containers.
for c in grafana-sc-dashboard grafana-sc-datasources grafana; do
  printf '%s rofs_errors=' $c; kubectl -n monitoring logs $POD -c $c | grep -ci 'read-only file system'
done
# PASS: 0 for each. The failure this guards: k8s-sidecar os.makedirs()/open() raising
# "OSError: [Errno 30] Read-only file system: '<path>'" (Python strerror for EROFS).
# Case-insensitive on purpose. (grep -c prints 0 and exits 1 on no match -- read the
# number, not the exit code.)
kubectl -n monitoring logs $POD -c grafana-sc-dashboard | grep -c '"msg": "Writing '
# PASS: == BASE_SC (37 on 2026-09-29). NOTE: the sidecar logs "Writing" BEFORE open(), so this
# count alone cannot catch a write failure -- that is what the rofs_errors gate above is for.
# This count catches the sidecar dying or skipping objects before reaching the write.
```
Known pre-existing noise, NOT caused by this hop: both sidecars bind health port
8080 in the same pod, so one logs a traceback ending
`OSError: [Errno 98] Address in use`. It appears in the 2026-09-27 pod too.
Errno 98 is not a gate failure. Errno 30 is.

**4.3 No schema migration ran (appVersion unchanged).**
```bash
kubectl -n monitoring logs $POD -c grafana | grep 'msg="migrations completed"'
# PASS: every line (migrator, secret-migrator, resource-migrator, unifiedstorage-migrator)
# shows performed=0. FAIL: performed=N>0 means the app version moved -> the rollback
# class is no longer git-revert; follow section 5 "if a migration ran".
```

**4.4 Datasource gate (mandatory for any Grafana restart, SOP grafana-image-changes §6).**
```bash
kubectl -n monitoring port-forward svc/grafana 33011:80 >/dev/null 2>&1 & PF=$!; sleep 4
curl -s -u "$U:$P" 'http://127.0.0.1:33011/api/plugins?embedded=0&type=datasource' \
  | python3 -c 'import sys,json; print("ds_plugins="+str(len(json.load(sys.stdin))))'
# PASS: >= BASE_DS (18). FAIL: a drop (13 on 2026-09-12) = bundled backends killed.
for uid in prometheus elasticsearch influxdb unpoller-influxdb pellets TeslaMate; do
  printf '%s -> ' $uid
  curl -s -u "$U:$P" "http://127.0.0.1:33011/api/datasources/uid/$uid/health" \
    | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("status"), d.get("message","")[:60])'
done
# PASS: OK for all six. FAIL prints ERROR or a plugin.notRegistered/404 message
# (all six OK on 2026-09-29).
curl -s -u "$U:$P" -o /dev/null -w 'alertmanager_proxy=%{http_code}\n' \
  'http://127.0.0.1:33011/api/datasources/proxy/uid/alertmanager/api/v2/status'
# PASS: 200 (Alertmanager has no backend /health, so use the proxy).
curl -s -u "$U:$P" -H 'Content-Type: application/json' -X POST 'http://127.0.0.1:33011/api/ds/query' \
  -d '{"from":"now-5m","to":"now","queries":[{"refId":"A","datasource":{"uid":"prometheus","type":"prometheus"},"expr":"count(kube_pod_info)","instant":true,"range":false}]}' \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); v=d["results"]["A"]["frames"][0]["data"]["values"][1][0]; print("pods="+str(v))'
# PASS: a positive integer (341 on 2026-09-29). FAIL: IndexError/KeyError traceback = no data came
# back through the query path even if /health is OK. Controls measured 2026-09-29: this exact
# command printed pods=341; with expr count(nonexistent_metric_xyz) it raised IndexError.
# NOTE: the "from"/"to" keys are REQUIRED -- the SOP section 6 form omits them and returns
# {"values": []} on a HEALTHY Grafana, i.e. it can never pass.
curl -s -u "$U:$P" 'http://127.0.0.1:33011/api/search?type=dash-db&limit=5000' \
  | python3 -c 'import sys,json; print("dashboards="+str(len(json.load(sys.stdin))))'
# FLOOR ONLY: == BASE_DASH (72). Provisioners run with disableDelete, so a missing
# sidecar file would NOT drop this count. The sidecar gate is 4.2, not this one.
kill $PF
kubectl -n monitoring logs $POD -c grafana | grep -ciE 'plugin.*not (found|registered)|read-only file system'
# PASS: 0.
```

## 5) Rollback

**Trigger.** Any §4 gate fails. Do not debug in place, because Grafana is the
instrument.

The rollback class is `git-revert`. It is valid because §4.3 shows
`performed=0`: 13.2.6 and 13.2.5 both run app 13.2.2.

```bash
cd /Users/mu/code/cberg-home-nextgen
SHA=$(git log -1 --format=%H -- kubernetes/apps/monitoring/grafana/app/helmrelease.yaml)
git show --stat $SHA                      # confirm it is THIS plan's commit
git revert --no-edit $SHA
git log -1 --format=%s                    # confirm subject is "Revert ... grafana ... 13.2.6"
git push
flux reconcile kustomization grafana -n monitoring --with-source
kubectl rollout status deployment/grafana -n monitoring --timeout=300s
```

Confirm you are back:
- `kubectl get hr grafana -n monitoring -o jsonpath='{.status.history[0].chartVersion}'` prints `13.2.5`.
- The new pod's `helm.sh/chart` label reads `grafana-13.2.5`, and its three helper
  containers show an empty `readOnlyRootFilesystem`.
- Re-run §4.2 through §4.4. A rollback is a restart and needs the same datasource
  gate.

**If the datasource gate fails on BOTH sides**, the plugin-preinstall hazard is
back, not caused by this chart. Check that `GF_PLUGINS_PREINSTALL_DISABLED` is
still `"true"` in the rendered Deployment
(`kubectl -n monitoring get deploy grafana -o jsonpath='{.spec.template.spec.containers[?(@.name=="grafana")].env}'`)
and escalate. Do not iterate in the window.

**If a migration ran** (§4.3 `performed>0`, which would contradict the premises),
do not chart-revert across it. Stop and restore the `grafana-config` Longhorn
backup taken by `storage/daily-backup-all-volumes` (03:00) following
`docs/sops/backup.md`. This path should be unreachable while the
`target-appversion-unchanged` premise holds.

## 6) Interference notes

- **Hard conflicts (in `conflicts_with`):**
  - `flux-oci-chart-sources` moves grafana's chart source and explicitly rolls
    `deployment/grafana`.
  - `helm-drift-detection` and `flux-reconciler-impersonation` change how every
    HelmRelease, grafana included, is reconciled.
  - `flux-fleet-0.60.0` swaps helm-controller. A controller restart mid-upgrade
    would make a failed §4.1 ambiguous.
- **Namespace neighbours in `monitoring`** (shared namespace only, no resource
  overlap): `otel-operator-0.23.0` (nightly 2026-10-03), `uptime-kuma-2.5.5-slim-rootless`
  (sat 2026-10-03), `chart-patches-coredns-reloader-blackbox` (sun 2026-11-01),
  and `app-template-5.2.1`. They can share a window, but run this plan first or
  last, not interleaved: a Grafana outage while another plan reads dashboards
  would confuse that plan's verification. None of them reads Grafana. This plan
  reads Prometheus through Grafana (§4.4 query), and no open kube-prometheus-stack
  plan exists (`kube-prometheus-stack-91.4.1` executed 2026-09-26).
- **User impact:** the Grafana UI and Authentik-SSO login are unavailable for
  about 1 minute (Recreate, single replica, RWO `grafana-config`). Alerting is
  unaffected, because Alertmanager and Prometheus do not depend on Grafana. The
  Homepage tile goes red briefly.
- **External fetches at init:** `download-dashboards` pulls ~30 dashboards from
  grafana.com and GitHub raw on every start (unchanged behaviour). An upstream
  404 or outage fails the init under `curl -f` and blocks the pod, whatever this
  hop does. If §4.2 shows `Init:Error`, read `kubectl -n monitoring logs $POD -c
  download-dashboards` before blaming readOnlyRootFilesystem: a curl `(22)` is an
  upstream URL, an `EROFS`/`Read-only` message is this hop.
- **Superseded sibling:** `grafana-chart-13.2.3.md` is `superseded` and does not
  interact. It is still named in `helm-drift-detection`'s `conflicts_with`.
- **Window fit:** 15 min, low risk, no reboot, no operator-present requirement
  beyond the default go/no-go for a G3-held item.
