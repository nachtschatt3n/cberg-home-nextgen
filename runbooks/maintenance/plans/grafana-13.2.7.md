---
plan_id: grafana-13.2.7
component: grafana
pr: null                            # no Renovate PR; coverage direct-bump candidate held by G3
kind: chart
current: "13.2.6"
target: "13.2.7"
update_type: patch
risk: low
est_duration_min: 20
needs_reboot: false
touches:
  namespaces: [monitoring]
  resources:
    - helmrelease/monitoring/grafana
    - deployment/monitoring/grafana            # one Recreate roll; the grafana container image moves 13.2.2 -> 13.2.3
    - kustomization/monitoring/grafana
    - pvc/monitoring/grafana-config            # sqlite + unified storage booted by the new binary (no migration files in this hop)
    - configmap/monitoring/grafana
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
  - talos-linux-1.14.2                # exclusive node roll; evicts grafana and touches monitoring
exclusive: false
security_ref: F-38473276              # the 13.2.2-distroless image row; upstream 13.2.3 is a
                                      # security release -- detail stays on the DB record
capability_change: false              # Grafana patch 13.2.2 -> 13.2.3: same features, no new route,
                                      # permission or exposure. The CSP default gains `blob:` in img-src,
                                      # which is inert here (content_security_policy is off by default
                                      # and our values do not set it).
rollback_class: git-revert            # valid ONLY while section 4.3 reads performed=0 on every
                                      # migrator; the 13.2.2..13.2.3 diff adds no migration files
finding_refs: [F-38473276]            # no version finding for 13.2.6 -> 13.2.7 existed at write time
                                      # (last sweep 2026-09-29, before chart 13.2.7 was indexed);
                                      # add it here once the next sweep mints it
review: null
status: draft
window: null
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/grafana-image-changes.md
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/backup.md
premises:
  - id: live-chart-still-13.2.6
    why: "Diff/rollback baseline. If the chart already moved, this plan is stale."
    run: kubectl get helmrelease grafana -n monitoring -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: "13.2.6"
  - id: helmrelease-ready
    why: "Do not stack a bump on an already-failing release."
    run: kubectl get helmrelease grafana -n monitoring -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: live-image-13.2.2-distroless
    why: >-
      Rollback baseline. The revert target must be the image that is running
      now; if something else is running, the git-revert class is unproven.
    run: kubectl get deploy grafana -n monitoring -o jsonpath='{.spec.template.spec.containers[?(@.name=="grafana")].image}'
    expect_exact: "docker.io/grafana/grafana:13.2.2-distroless"
  - id: no-image-override
    why: >-
      The chart templates the image as appVersion + "-distroless". An
      image.tag/repository override in our values would make this chart bump
      a no-op, or roll a different image than the one assessed in section 1.
    run: kubectl get helmrelease grafana -n monitoring -o jsonpath='{.spec.values.image}' | wc -c | tr -d ' '
    expect_exact: "0"
  - id: preinstall-disabled
    why: >-
      Load-bearing on distroless (SOP grafana-image-changes section 7). Without
      it, a restart lets the background installer kill bundled datasource
      backends it cannot rewrite on the read-only rootfs.
    run: kubectl get deploy grafana -n monitoring -o jsonpath='{.spec.template.spec.containers[?(@.name=="grafana")].env[?(@.name=="GF_PLUGINS_PREINSTALL_DISABLED")].value}'
    expect_exact: "true"
  - id: repo-cache-has-target
    why: >-
      The appVersion premise below reads the LOCAL helm index, and a stale
      cache fails exactly like a moved appVersion. Run `helm repo update
      grafana-community` first if this fails. (Alias grafana-community =
      grafana-community.github.io/helm-charts, the same URL as the in-cluster
      HelmRepository flux-system/grafana. The local alias named `grafana` is a
      DIFFERENT, frozen repo -- do not use it.)
    run: helm show chart grafana-community/grafana --version 13.2.7 | grep '^version:'
    expect_exact: "version: 13.2.7"
  - id: target-appversion-13.2.3
    why: >-
      Central claim. Chart 13.2.7 renders grafana 13.2.3. Any other appVersion
      means section 1's upstream assessment is about the wrong binary.
    run: helm show chart grafana-community/grafana --version 13.2.7 | grep '^appVersion:'
    expect_exact: "appVersion: 13.2.3"
  # The target-image-exists check is NOT a premise: plan-premises.py allows no
  # network fetch (curl refused). It is the first STOP gate in section 2.
generated: "2026-10-01"
---

# grafana: chart 13.2.6 -> 13.2.7 (Grafana 13.2.2 -> 13.2.3, security patch)

## 1) Summary & why held

**Why held.** Coverage G3 reported `unverified (release notes unavailable)`, and
with 0 green / 0 reverts in 90 days of earned autonomy an unverified bump may not
take the unattended lane. This is the same lookup miss as grafana-13.2.6: the
notes exist as GitHub release `grafana-13.2.7` in `grafana-community/helm-charts`,
published 2026-09-29T09:19Z. See the report for the repo correction.

**Unlike 13.2.6, this hop changes the Grafana binary.** The chart source diff
(`helm pull` 13.2.6 and 13.2.7, `diff -r`, measured 2026-10-01) is exactly two
lines in `Chart.yaml`: `version` and `appVersion: 13.2.2 -> 13.2.3`. No template,
values or subchart change. The chart release note is a single line:

> * [grafana] Update docker.io/grafana/grafana Docker tag to v13.2.3 by
>   @renovate[bot] in #847

Because we set no `image` override (premise `no-image-override`), the rendered
grafana container moves `grafana:13.2.2-distroless -> grafana:13.2.3-distroless`.
Docker Hub lists that tag (pushed 2026-09-29; index digest
`sha256:202e5d5b3f84...`, linux/amd64 manifest `sha256:8c7801a8ed84...`). The render diff otherwise matches 13.2.6: the
`helm.sh/chart` label on every object, and the image tag.

**Upstream Grafana v13.2.3** (GitHub release `v13.2.3`, published
2026-09-29T09:02Z). The release notes have one section, `### Security`, with
three security fixes. Their identifiers stay on the `security_ref` record per
`docs/sops/vulnerability-disclosure.md`. There is no breaking-change, deprecation
or migration entry.

**Measured against the code, not the notes.** `v13.2.2...v13.2.3` is 23 commits
and 181 files. Leaving out docs, go.mod/go.sum, package.json, generated TS types
and tests, the hop touches:

| Change | Effect on us |
|---|---|
| `Dockerfile`: `alpine:3.24.1 -> 3.24.2` | Base-layer patch only. The distroless stage is unchanged. |
| `packaging/{deb,rpm}/systemd/grafana-server.service`: `PLUGIN_UNIX_SOCKET_DIR=/run/grafana` (PR #133555, backport of #131593) | **None.** This is systemd-unit only and does not reach the container image, so backend-plugin sockets stay where they are on our read-only rootfs. (Checked because a moved socket dir on a read-only rootfs would kill every datasource backend.) |
| `conf/defaults.ini`: CSP template `img-src * data:` -> `img-src * data: blob:` (#133455) | Inert. `content_security_policy` defaults to false, and our values set no `security`/CSP key. |
| `pkg/storage/unified/apistore/managed.go`: new `enforceClassicFPAssignment`. Only a service identity (the file provisioner) may *newly* assign the classic-file-provisioning manager; rewrites of an already-classic-FP object keep working. | This is our dashboard path: 65 of 72 dashboards are file-provisioned (dashboardProviders + sidecar). The provisioner is the allowed service identity. Nothing in this repo pushes dashboards via `api/dashboards/db|import` (grep of `kubernetes/` and `runbooks/` = 0 hits), and no values set `allowUiUpdates`. Expected effect is nil. Section 4.3 checks it positively, because unified storage is where this Grafana broke before (`a0556c6d`, `44f4c523`). |
| `pkg/services/publicdashboards/...`: org lookup now requires `is_enabled=true` | We do not use public dashboards. Not exercised. |
| `pkg/services/ngalert/provisioning/alert_rules.go`: early return for an empty folder filter | We provision no Grafana-managed alert rules (alerting is Prometheus/Alertmanager). Not exercised. |
| `apps/provisioning/pkg/repository/git/*`: nanogit error wrapping | Git Sync is not used. |

**No migration files are in the diff.** Nothing under
`pkg/services/sqlstore/migrations` or any `*migrat*` path changed. The live pod
(13.2.2) logs `performed=0` on all four migrators: migrator, secret-migrator,
resource-migrator and unifiedstorage-migrator. 13.2.3 should log the same. This
is the condition for the `git-revert` rollback class, and section 4.3 gates on it.

**Verdict.** The hold was a lookup false positive. The real change is a Grafana
patch release with security fixes and no schema change: one Recreate roll, about
1 min of UI outage. `risk: low`, no reboot, not a capability change. It is still
an **application binary move**, so the SOP grafana-image-changes datasource gate
(section 4.4) is mandatory, not optional.

**House hazards, checked.**
- `GF_PLUGINS_PREINSTALL_DISABLED: "true"` is live (premise
  `preinstall-disabled`). The new image ships its own `plugins-bundled` set. If
  the var were missing, the background installer would race it on the read-only
  rootfs (SOP section 7, the 2026-09-12 incident).
- PVC-leftover trap (SOP section 2, fact 2): a plugin count that holds could come
  from `/var/lib/grafana/plugins` on the PVC rather than from the image. Section
  4.4 therefore also checks per-datasource health and a real query, not only the
  count.
- Unified storage: see the classic-FP row above, gated in section 4.3.

## 2) Pre-checks

Run `helm repo update grafana-community` first, then the premises:
`.venv/bin/python3 runbooks/plan-premises.py grafana-13.2.7`. All must pass.

**STOP gate: the target image is published.** If it is not, the Recreate roll
leaves Grafana in ImagePullBackOff, because the old pod is already gone:
```bash
curl -s https://hub.docker.com/v2/repositories/grafana/grafana/tags/13.2.3-distroless | grep -o '"name":"13.2.3-distroless"' | head -1
# PASS: prints "name":"13.2.3-distroless" (2026-10-01: present, pushed 2026-09-29).
# FAIL: empty output. Control 2026-10-01: the same command for the nonexistent tag 13.2.9-distroless printed nothing.
```

Then record the baseline. The numbers below were measured 2026-10-01 against pod
`grafana-6d4c855556-v4w5r` (chart 13.2.6). Re-measure, because the post-change
comparison is against the live baseline, not these.

```bash
U=$(kubectl -n monitoring get secret grafana-admin-secret -o jsonpath='{.data.admin-user}' | base64 -d)
P=$(kubectl -n monitoring get secret grafana-admin-secret -o jsonpath='{.data.admin-password}' | base64 -d)
export U P
kubectl -n monitoring port-forward svc/grafana 33011:80 >/dev/null 2>&1 & PF=$!; sleep 4
curl -s http://127.0.0.1:33011/api/health                                   # 2026-10-01: version 13.2.2, database ok
curl -s -u "$U:$P" 'http://127.0.0.1:33011/api/plugins?embedded=0&type=datasource' \
  | python3 -c 'import sys,json; print("ds_plugins="+str(len(json.load(sys.stdin))))'   # 2026-10-01: 18
cat > /tmp/grafana-prov-count.py <<'EOF'
import os, json, base64, urllib.request
a = "Basic " + base64.b64encode(f"{os.environ['U']}:{os.environ['P']}".encode()).decode()
def g(p):
    return json.load(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:33011" + p, headers={"Authorization": a})))
ds = g("/api/search?type=dash-db&limit=5000"); prov = err = 0
for d in ds:
    try: prov += bool(g("/api/dashboards/uid/" + d["uid"])["meta"].get("provisioned"))
    except Exception: err += 1
print(f"dashboards={len(ds)} provisioned={prov} fetch_errors={err}")
EOF
python3 /tmp/grafana-prov-count.py                                         # 2026-10-01: dashboards=72 provisioned=65 fetch_errors=0
kill $PF

# Error-signature baseline for section 4.3: one line per distinct logger|msg|document of a
# level=error line. logger=context (per-request HTTP lines, incl. our own probes) is excluded;
# section 4.4 gates the datasources.
cat > /tmp/grafana-err-sig.py <<'EOF'
import sys, re
sig = set()
for line in sys.stdin:
    if not re.search(r'\blevel=error\b', line, re.I):
        continue
    lg = re.search(r'\blogger=(\S+)', line)
    lg = lg.group(1) if lg else "?"
    if lg == "context":
        continue
    msg = re.search(r'\bmsg="([^"]*)"', line)
    doc = re.search(r'\bdocument=(\S+)', line)
    sig.add(f'{lg} | {msg.group(1) if msg else "?"} | {doc.group(1) if doc else "-"}')
print("\n".join(sorted(sig)))
EOF
OLDPOD=$(kubectl -n monitoring get pods -l app.kubernetes.io/name=grafana -o jsonpath='{.items[0].metadata.name}')
kubectl -n monitoring logs $OLDPOD -c grafana | python3 /tmp/grafana-err-sig.py > /tmp/grafana-err-base.txt
cat /tmp/grafana-err-base.txt
# 2026-10-01 (pod grafana-6d4c855556-v4w5r, started 2026-09-30T01:39:22Z) printed exactly one line,
# a BOOT-TIME dashboard-store error (logged 2s after start) that recurs on every start and is NOT
# caused by this hop:
#   services.store.kind.dashboard | Unexpected element in Dashboard JSON | default/dashboard.grafana.app/dashboards/1iY4QMJVk-psee

kubectl get cm,secret -A -l grafana_dashboard -o name | wc -l               # 2026-10-01: 37 (sidecar objects)

# Longhorn backup of the config volume -- the restore point if section 5's migration branch is ever reached
kubectl get volume -n storage grafana-config -o jsonpath='{.status.lastBackupAt}{"\n"}'   # 2026-10-01: 2026-09-30T03:09:12Z
# Must be < 26h old. lastBackupAt lags one cycle (docs/sops/backup.md), so if it looks stale,
# cross-check the newest Completed Backup CR for grafana-config before you call it a STOP.
```

Record `BASE_DS` (18), `BASE_DASH` (72), `BASE_PROV` (65) and `BASE_SC` (37),
and keep `/tmp/grafana-err-base.txt`. These are the pass bars in section 4.

**STOP** if the backup is older than 26h and no Completed Backup CR from the last
26h exists. The git-revert class assumes no migration. If that assumption fails,
the backup is the only way back.

## 3) Steps (GitOps)

This is the low-risk patch path of `docs/sops/application-update.md`: commit,
push, let Flux reconcile, verify. No alert silence is needed, because Grafana's
~1 min Recreate gap fires no Prometheus/Alertmanager alert on its own.

1. Edit the chart pin. This was dry-tested on a scratch copy with BSD sed
   (2026-10-01). The resulting diff is exactly
   `11c11 <       version: 13.2.6 --- >       version: 13.2.7`, and `13.2.6`
   occurs once in the file:
   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   sed -i '' 's/^      version: 13\.2\.6$/      version: 13.2.7/' kubernetes/apps/monitoring/grafana/app/helmrelease.yaml
   git diff --stat kubernetes/apps/monitoring/grafana/app/helmrelease.yaml   # expect: 1 insertion, 1 deletion
   ```
2. Commit only that path, then verify authorship before you push:
   ```bash
   git commit --only kubernetes/apps/monitoring/grafana/app/helmrelease.yaml \
     -m "chore(grafana): chart 13.2.6 -> 13.2.7 (Grafana 13.2.2 -> 13.2.3, upstream security patch) [plan grafana-13.2.7]"
   git log -1 --format=%s     # must be the subject above
   git show --stat HEAD       # must list only helmrelease.yaml
   git push
   ```
3. Reconcile only if the webhook has not picked the change up within ~2 min. The
   Kustomization lives in namespace **monitoring**, not flux-system:
   ```bash
   flux reconcile kustomization grafana -n monitoring --with-source
   kubectl -n monitoring get hr grafana -o jsonpath='{.spec.chart.spec.version}{"\n"}'   # must print 13.2.7 BEFORE judging the upgrade
   ```
4. Wait for the Recreate roll:
   ```bash
   kubectl rollout status deployment/grafana -n monitoring --timeout=300s
   ```
   `rollout status` can green-light the old generation, so section 4.1 checks the
   pod itself.

## 4) Verification

Every gate states the failure it catches. Run all of them.

**4.1 Release landed and the NEW pod runs the NEW binary.**
```bash
kubectl get hr grafana -n monitoring -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion}{"\n"}'
# PASS: "True 13.2.7". FAIL prints False / 13.2.6 (upgrade failed or not reconciled).
POD=$(kubectl -n monitoring get pods -l app.kubernetes.io/name=grafana -o jsonpath='{.items[0].metadata.name}')
kubectl -n monitoring get pod $POD -o jsonpath='{.metadata.labels.helm\.sh/chart} {.status.startTime} {.status.containerStatuses[?(@.name=="grafana")].image}{"\n"}'
# PASS: "grafana-13.2.7 <startTime after the push> docker.io/grafana/grafana:13.2.3-distroless".
# FAIL: grafana-13.2.6 or a 13.2.2 image = the old pod is still serving (stale generation).
kubectl -n monitoring port-forward svc/grafana 33011:80 >/dev/null 2>&1 & PF=$!; sleep 4
curl -s http://127.0.0.1:33011/api/health | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["version"], d["database"])'
# PASS: "13.2.3 ok". Live control 2026-10-01: printed "13.2.2 ok" on the old pod, so a stale
# pod or a failed DB open prints something different here.
```

**4.2 Pod and helpers are healthy (unchanged helpers, but a restart is a restart).**
```bash
kubectl -n monitoring get pod $POD -o jsonpath='{range .status.initContainerStatuses[*]}{.name} {.state.terminated.reason} {.state.terminated.exitCode}{"\n"}{end}'
# PASS: "init-chown-data Completed 0" (if present) and "download-dashboards Completed 0".
# FAIL: Error / non-zero exit. If download-dashboards fails, read its log first: a curl (22) is an
# upstream grafana.com/GitHub 404, which is NOT caused by this hop (section 6).
kubectl -n monitoring get pod $POD -o jsonpath='{range .status.containerStatuses[*]}{.name} restarts={.restartCount}{"\n"}{end}'
# PASS: restarts=0 for grafana, grafana-sc-dashboard, grafana-sc-datasources.
kubectl -n monitoring logs $POD -c grafana-sc-dashboard | grep -c '"msg": "Writing '
# PASS: == BASE_SC (37). FAIL: fewer = the sidecar died or skipped objects before writing.
```
Known pre-existing noise, NOT caused by this hop: both sidecars bind health port
8080 in the same pod, so one logs a traceback ending
`OSError: [Errno 98] Address in use`. It is present on the 13.2.6 pod too.

**4.3 No schema migration ran, and unified-storage provisioning still owns the dashboards.**
```bash
kubectl -n monitoring logs $POD -c grafana | grep 'msg="migrations completed"' \
  | awk '{n++; if ($0 !~ /performed=0 /) bad++} END{print "lines="n+0, "nonzero="bad+0}'
# PASS: lines=4 nonzero=0 (live 2026-10-01 on 13.2.2: migrator, secret-migrator, resource-migrator,
# unifiedstorage-migrator, all performed=0). FAIL: lines=0 (wrong container, rotated log, reworded
# message -- the gate captured nothing) or nonzero>0 (a migration ran -> the rollback class is no
# longer git-revert; use section 5 "If a migration ran").
python3 /tmp/grafana-prov-count.py
# PASS: dashboards == BASE_DASH (72), provisioned >= BASE_PROV (65), fetch_errors=0.
# What this CAN detect: fetch_errors>0 (dashboards listed but not loadable from unified storage),
# and provisioned or dashboards FALLING (provenance metadata lost on existing rows, or rows gone).
# What it CANNOT detect: a classic-FP gate refusal. enforceClassicFPAssignment is skipped for an
# object that is ALREADY classic-file-provisioned (managed.go@v13.2.3,
# checkManagerPropertiesOnUpdateSpec ~L157), so all 65 existing provisioned dashboards bypass it on
# update; and the providers run with disableDelete, so a refused write keeps the old row and
# neither number moves.
```

**This hop has NO gate for the classic-FP create path.** The new check only bites
when the provisioner *newly* assigns the classic-FP manager, i.e. creates a
dashboard that does not exist yet. This plan adds no dashboard, so that path is
not exercised in the window. Its first real exercise is the next new sidecar or
dashboardProviders dashboard after the hop; the error-signature gate below sees
a refusal only if one happens during this boot.

```bash
kubectl -n monitoring logs $POD -c grafana | python3 /tmp/grafana-err-sig.py \
  | LC_ALL=C comm -13 /tmp/grafana-err-base.txt - | tee /tmp/grafana-err-new.txt
echo "new_error_sigs=$(grep -c . /tmp/grafana-err-new.txt)"
# PASS: new_error_sigs=0. FAIL: >0. Each printed line is a level=error signature (logger | msg |
# document) the 13.2.2 pod did not have: a dashboard-store, provisioning or unified-storage error,
# whatever its logger name or wording. This replaces the earlier `level=error | grep provision`
# filter, which missed the real dashboard-store error class (logger=services.store.kind.dashboard,
# msg="Unexpected element in Dashboard JSON") and printed 0 on a log that contained it.
# Demonstrated able to fail (2026-10-01, live 13.2.2 log as the known-bad input):
#   - vs an EMPTY baseline it prints 1 line (the psee "Unexpected element in Dashboard JSON" error);
#   - vs its own baseline it prints 0;
#   - with a synthetic `level=error msg="Can not set the classic-file-provisioning resource manager"`
#     line appended, it prints exactly that signature.
# The script sorts by codepoint, hence LC_ALL=C for comm. A log that was not read at all also
# prints 0 here -- the migrations gate above (lines=4) is what proves the right log was read.
kubectl -n monitoring logs $POD -c grafana | grep -ciE 'classic-file-provisioning resource manager'
# INFORMATIONAL, not a gate. The string is upstream's 403 text from managed.go and has never been
# observed in a real log here (0 on 13.2.2), so a 0 proves nothing. If non-zero, read the lines;
# the signature gate above will already have printed them as a FAIL.
```

**4.4 Datasource gate (mandatory for any Grafana binary change, SOP grafana-image-changes section 6).**
```bash
curl -s -u "$U:$P" 'http://127.0.0.1:33011/api/plugins?embedded=0&type=datasource' \
  | python3 -c 'import sys,json; print("ds_plugins="+str(len(json.load(sys.stdin))))'
# PASS: >= BASE_DS (18). FAIL: a drop (13 on 2026-09-12) = bundled backends missing or killed.
for uid in prometheus elasticsearch influxdb unpoller-influxdb pellets TeslaMate; do
  printf '%s -> ' $uid
  curl -s -u "$U:$P" "http://127.0.0.1:33011/api/datasources/uid/$uid/health" \
    | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("status"), str(d.get("message",""))[:60])'
done
# PASS: OK for all six (all six OK on 2026-10-01). FAIL prints ERROR, or None plus a
# plugin.notRegistered / "Plugin not found" message when a backend did not register.
curl -s -u "$U:$P" -o /dev/null -w 'alertmanager_proxy=%{http_code}\n' \
  'http://127.0.0.1:33011/api/datasources/proxy/uid/alertmanager/api/v2/status'
# PASS: 200 (200 on 2026-10-01). Alertmanager has no backend /health, so use the proxy.
curl -s -u "$U:$P" -H 'Content-Type: application/json' -X POST 'http://127.0.0.1:33011/api/ds/query' \
  -d '{"from":"now-5m","to":"now","queries":[{"refId":"A","datasource":{"uid":"prometheus","type":"prometheus"},"expr":"count(kube_pod_info)","instant":true,"range":false}]}' \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); v=d["results"]["A"]["frames"][0]["data"]["values"][1][0]; print("pods="+str(v))'
# PASS: a positive integer (334 on 2026-10-01). FAIL: IndexError/KeyError traceback = no data came
# back through the query path even though /health is OK. Control (plan grafana-13.2.6 review,
# 2026-09-29): expr count(nonexistent_metric_xyz) raises IndexError. "from"/"to" are REQUIRED.
kill $PF
kubectl -n monitoring logs $POD -c grafana | grep -ciE 'plugin.*not (found|registered)|read-only file system'
# SUPPLEMENTARY absence gate. PASS: 0. Matches the archived slim-incident string
# `plugin prometheus not found` and an EROFS from the preinstaller.
```

## 5) Rollback

**Trigger.** Any section 4 gate fails. Do not debug in place: Grafana is the
instrument.

**Normal path: `git-revert`.** It is valid only when section 4.3 printed
`nonzero=0`, so no migration ran and 13.2.2 can boot the same database. The
SOP's general rule is "roll the variant, never the version", because migrations
are forward-only. This revert is the exception the SOP itself verified on
2026-08-18: both boots logged `performed=0`, so the round trip leaves the schema
untouched.

```bash
cd /Users/mu/code/cberg-home-nextgen
SHA=$(git log -1 --format=%H -- kubernetes/apps/monitoring/grafana/app/helmrelease.yaml)
git show --stat $SHA                      # confirm it is THIS plan's commit (subject names grafana-13.2.7)
git revert --no-edit $SHA
git log -1 --format=%s                    # confirm subject is "Revert ... grafana ... 13.2.7"
git push
flux reconcile kustomization grafana -n monitoring --with-source
kubectl rollout status deployment/grafana -n monitoring --timeout=300s
```

Confirm you are back:
- `kubectl get hr grafana -n monitoring -o jsonpath='{.status.history[0].chartVersion}'` prints `13.2.6`.
- The new pod's `helm.sh/chart` label reads `grafana-13.2.6`, its grafana
  container image is `docker.io/grafana/grafana:13.2.2-distroless`, and
  `/api/health` reports `13.2.2`.
- Re-run sections 4.2 through 4.4. A rollback is a restart and needs the same
  datasource gate.

**If the datasource gate fails on BOTH sides**, the plugin-preinstall hazard is
back and this chart did not cause it. Check that `GF_PLUGINS_PREINSTALL_DISABLED`
is still `"true"` in the rendered Deployment
(`kubectl -n monitoring get deploy grafana -o jsonpath='{.spec.template.spec.containers[?(@.name=="grafana")].env}'`),
then escalate. Do not iterate in the window.

**If a migration ran** (section 4.3 `nonzero>0`), this is a backup-restore
procedure, not a revert. A 13.2.2 binary must not boot a database that 13.2.3
migrated.
1. If 13.2.3 itself is healthy (sections 4.2 and 4.4 pass), **stay forward**.
   Record the unexpected migration and leave the release in place. Being forward
   on a working patch costs less than a restore.
2. If 13.2.3 is unhealthy, scale Grafana to zero *through git* by setting
   `replicas: 0` in the HelmRelease values, committed with `--only` like step 3.2.
   Then restore the `grafana-config` Longhorn volume from the backup recorded in
   section 2 (the `storage/daily-backup-all-volumes` RecurringJob, 03:00), using
   the restore procedure in `docs/sops/backup.md`. Revert the chart commit and
   restore `replicas` in the same push, and let Flux bring 13.2.2 up on the
   restored volume. Re-run sections 4.2 through 4.4.
3. The data at risk is dashboards and settings changed since the backup. Every
   provisioned dashboard and datasource is regenerated from git and the sidecar.
   Only UI-made state (7 non-provisioned dashboards, preferences, annotations)
   rolls back to 03:00.

## 6) Interference notes

- **Hard conflicts (in `conflicts_with`):**
  - `flux-oci-chart-sources` moves grafana's chart source and explicitly rolls
    `deployment/grafana`.
  - `helm-drift-detection` (sat-attended 2026-11-07) and
    `flux-reconciler-impersonation` (sun-attended 2026-10-11) change how every
    HelmRelease, grafana included, is reconciled.
  - `flux-fleet-0.60.0` (nightly 2026-10-06) swaps helm-controller. A controller
    restart mid-upgrade would make a failed section 4.1 ambiguous.
  - `talos-linux-1.14.2` (draft, exclusive, sun-attended) evicts and reschedules
    every pod including grafana, and names `monitoring` in its touches. Never
    the same window.
- **Namespace neighbours in `monitoring`** (shared namespace, no resource
  overlap): `otel-operator-0.23.0` (nightly 2026-10-03),
  `uptime-kuma-2.5.5-slim-rootless` (sat 2026-10-03), `app-template-5.2.1`
  (nightly 2026-10-02), `chart-patches-coredns-reloader-blackbox`
  (sun 2026-11-01), and the drafts `edot-collector-0.162.0` and
  `unpoller-5.4.0`. They can share a window. Run this plan first or last, not
  interleaved:
  - `unpoller-5.4.0` section 4.8 has an INFORMATIONAL check that renders the
    Grafana UniFi dashboards, and a Grafana roll in the middle of it would
    confuse that check.
  - In the other direction, this plan's section 4.4 health-checks the
    `unpoller-influxdb` and `elasticsearch` datasources, and an unpoller or
    edot roll does not take those down: they are InfluxDB and Elasticsearch,
    not the exporters.
  - This plan reads Prometheus through Grafana (section 4.4 query), and no open
    kube-prometheus-stack plan exists (`kube-prometheus-stack-91.4.1` executed
    2026-09-26).
- **`teslamate-4.3`** (draft) does not roll `teslamate-postgres`, so the
  `TeslaMate` datasource health in section 4.4 is unaffected if both land the
  same night.
- **User impact:** the Grafana UI and Authentik-SSO login are unavailable for
  about 1 minute (Recreate, single replica, RWO `grafana-config`). Alerting is
  unaffected, because Alertmanager and Prometheus do not depend on Grafana. The
  Homepage tile goes red briefly.
- **External fetches at init:** `download-dashboards` pulls ~30 dashboards from
  grafana.com and GitHub raw on every start (unchanged behaviour). An upstream
  outage fails the init and blocks the pod, whatever this hop does. Read that
  container's log before blaming 13.2.3.
- **Superseded sibling:** `grafana-chart-13.2.3.md` is `superseded` and does not
  interact.
- **Window fit:** 20 min, low risk, no reboot. A nightly slot is fine.
  Derived class AUTO-NIGHT (risk low, `capability_change: false`,
  `rollback_class: git-revert`).
