---
plan_id: authentik-2026.8.3
component: authentik
pr: null                              # no open Renovate PR (gh pr list --search authentik: [] on
                                      # 2026-09-25); held by coverage.py needs_plan + the
                                      # operator deny rule "*authentik*" in auto-update-policy.yaml
kind: chart
current: "chart 2026.8.2; server+worker run ghcr.io/goauthentik/server:2026.8.2 (chart appVersion) with both patch-session-settings initContainers pinned :2026.8.2; 12 managed proxy outposts on ghcr.io/goauthentik/proxy:2026.8.2"
target: "chart 2026.8.3 + both initContainer pins ghcr.io/goauthentik/server:2026.8.3 in ONE commit; 12 managed proxy outposts pushed to ghcr.io/goauthentik/proxy:2026.8.3"
update_type: patch
risk: medium                          # same-line patch, chart templates+values byte-identical
                                      # (measured: helm pull 2026.8.2 vs 2026.8.3, only Chart.yaml/
                                      # lock/README differ), but full-cluster SSO blast radius, a
                                      # forward-only (empty) Django merge migration, and a manual
                                      # 12-outpost image push
est_duration_min: 40
needs_reboot: false
touches:
  namespaces: [kube-system]
  resources:
    - helmrelease/authentik                     # chart.spec.version + 2 initContainer image pins
    - deployment/authentik-server               # 3 replicas, rolling restart
    - deployment/authentik-worker               # 3 replicas, rolling restart (runs the migration + blueprint re-apply)
    - "authentik DB schema (deployment/authentik-pg, postgres 18.6): +1 row in django_migrations (authentik_core 0065_merge, operations=[]); NOT restarted"
    - deployment/ak-outpost-alertmanager-forward-auth
    - deployment/ak-outpost-arag-web-forward-auth
    - deployment/ak-outpost-esphome-forward-auth
    - deployment/ak-outpost-frigate-forward-auth
    - deployment/ak-outpost-headlamp-forward-auth
    - deployment/ak-outpost-homepage-forward-auth
    - deployment/ak-outpost-longhorn-forward-auth
    - deployment/ak-outpost-nocodb-forward-auth
    - deployment/ak-outpost-phpmyadmin-forward-auth
    - deployment/ak-outpost-prometheus-forward-auth
    - deployment/ak-outpost-solarfocus-scraper-forward-auth
    - deployment/ak-outpost-uptime-kuma-forward-auth
    - "upstream system blueprints re-applied on the image change (system/providers-oauth2.yaml profile-scope mapping, system/object-attributes-user.yaml)"
  shared:
    - identity-provider   # authentik = SSO (OIDC) + forward-auth for the whole estate
    - authentik           # every OIDC app and all 12 forward-auth-protected apps log in through it
    - gateway/envoy       # authentik-server is published via HTTPRoute on envoy-external (public
                          # edge); the 12 outposts back the SecurityPolicy ext-auth of their apps
    - monitoring          # §4 reads Prometheus alerts/series; authentik gauges change label shape
depends_on: []
conflicts_with:
  - authentik-pg17-decommission       # SAME component, SAME helmrelease.yaml, sat-attended:2026-09-26,
                                      # awaiting-go; its residual verification (a forward-auth sign-in
                                      # in the authentik event log) must not be read across an authentik
                                      # roll — see §6. Do not co-schedule.
  - wazuh-2xx-edge-coverage           # sat-attended:2026-09-26; edits helmrelease/authentik and restarts
                                      # authentik-server, and its §3.1 client_ip baseline is changed by
                                      # this release (X-Forwarded-For-with-ports fix) — see §6
  - talos-1.14.1                      # node roll evicts every authentik pod mid-verification
  - kube-prometheus-stack-91.4.1      # §4 reads Prometheus + Alertmanager (the window's instrument)
  - flux-reconciler-impersonation     # exclusive; changes how helm-controller applies this HR
exclusive: false
security_ref: F-51a63a20              # server image; proxy-image record is F-adb82e20. Detail on the
                                      # records only (policy-cli.py finding show) — public repo.
capability_change: true               # small but user-visible: the upstream system blueprint
                                      # providers-oauth2.yaml changes the OIDC `profile` scope so the
                                      # `picture` claim is omitted for generated (data: URI) avatars.
                                      # Any OIDC client that displayed the generated avatar stops
                                      # receiving it. Attended-only regardless (operator hold note).
rollback_class: git-revert            # the only schema change is an EMPTY merge migration; 2026.8.2
                                      # code ignores an applied-but-unknown migration row (see §5)
finding_refs: [F-2fb59c74, F-51a63a20, F-adb82e20]   # version-monitor chart patch; server + proxy
                                      # image records (bump-never-rebuild). Confirm closure on the
                                      # next scan; do not assume 2026.8.3 clears every item.
status: draft
window: null                          # PROPOSED: sun-attended:2026-10-04 (see §6) — the window agent assigns
premises:
  - id: server-still-on-2026.8.2
    why: "`current:` claims the server Deployment runs :2026.8.2."
    run: kubectl get deploy -n kube-system authentik-server -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: ghcr.io/goauthentik/server:2026.8.2
  - id: worker-still-on-2026.8.2
    why: "`current:` claims the worker Deployment runs :2026.8.2."
    run: kubectl get deploy -n kube-system authentik-worker -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: ghcr.io/goauthentik/server:2026.8.2
  - id: hr-chart-still-2026.8.2
    why: "The HelmRelease has not already been moved by another session."
    run: kubectl get helmrelease -n kube-system authentik -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: "2026.8.2"
  - id: twelve-outposts-on-2026.8.2
    why: "The outpost push in §3 step 6 targets exactly 12 Deployments on the old proxy tag."
    run: kubectl get deploy -n kube-system -o jsonpath='{range .items[*]}{.spec.template.spec.containers[0].image}{"\n"}{end}' | grep -c 'goauthentik/proxy:2026.8.2'
    expect_exact: "12"
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/authentik.md
  - docs/sops/backup.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-09-25"
---

# authentik 2026.8.2 -> 2026.8.3 (chart + both init pins in lockstep, then the 12 outposts)

## 1. Summary & why held

A same-line patch. Three pins move in ONE commit, exactly as in `bfdaa95a`
(2026.8.1 -> 2026.8.2): `spec.chart.spec.version` and the two
`patch-session-settings` initContainer images (server line 108, worker line 244
of `helmrelease.yaml`). The main server/worker image is NOT pinned in our
values — it comes from the chart's `appVersion` — so a chart-only bump would run
2026.8.3 code with a 2026.8.2 `settings.py` copied over it by the stale init
container. That skew is the hazard `docs/sops/authentik.md` §"Upgrading
Authentik" describes (2026.5.6 -> 2026.8.0 crashlooped every replica at once
this way).

**Why held.** Two independent holds:
1. The operator deny rule `*authentik*` in `runbooks/auto-update-policy.yaml`
   (2026-09-22). The unattended AUTO lane routed this bump while G3 reported the
   release notes unavailable — a fail-open on the SSO front door. The rule says
   to move the chart and both image pins together in an ATTENDED window.
2. `coverage.py` needs_plan (sweep cycle 835c6ebc).

**Upstream evidence** — GitHub release `version/2026.8.3`, published
2026-09-17T22:15Z. Chart 2026.8.3 is in the index, and ghcr `server:2026.8.3` and
`proxy:2026.8.3` both return HTTP 200 (checked 2026-09-25). The items that matter here:

- **`core: fix migrations (version-2026.8)` (#26209, cherry-pick of #26208).**
  This is the one real schema touch. It rewrites the dependencies of
  `authentik_core.0064_user_authentik_c_usernam_2f0e4b_idx`
  (`0063_actor`/`rbac.0011` -> `0059_add_application_meta_hide`/`rbac.0010`) and
  adds `0065_merge_20260916_1253` with `operations = []`. It fixes upstream issue
  #25996, where 2026.5.7 -> 2026.8.2 failed with `InconsistentMigrationHistory`.
  **Measured on our DB (read-only `ak shell`, 2026-09-25):** `0063_actor`
  (2026-08-19), `rbac.0011` (2026-08-19) and `0064` (2026-09-08) are all
  applied, in the right order, and so are the new dependencies `0059` and
  `rbac.0010`. We are not in the broken state #25996 describes. The upgrade
  applies only the empty merge `0065`.
- **Upstream system blueprints change** (they re-apply on every image bump since
  the `/blueprints/cberg` layout):
  - `blueprints/system/providers-oauth2.yaml`: the `profile` scope now sets
    `picture` only for URL avatars, not for generated `data:` avatars
    (#26080). This is the `capability_change` above.
  - `blueprints/system/object-attributes-user.yaml`: the typo
    `employee_departmenet` becomes `employee_department`, with a NEW managed id.
    The misspelled attribute row is left orphaned. That is cosmetic. Nothing in
    `kubernetes/` or `docs/` references either key (grep, 2026-09-25).
  - `authentik/blueprints/v1/importer.py`: pk identifiers are now coerced via
    `model._meta.pk.to_python()` during validation (from the compare diff; no
    effect expected on our `cberg/` blueprints, which G3 asserts).
- **`root: fix metric gauges for multiprocessor mode` (#25882).** Gauges gain
  `multiprocess_mode` (`livesum` for outpost connection, `livemax` for
  last-update, `livemostrecent` for task gauges). The `pid` label disappears from
  those series. Measured today: `authentik_tasks_workers` has 2 `pid`
  series per server pod (6 total). After the change, expect 1 per pod. No repo
  rule keys on `pid` (grep of `kubernetes/`), and `min(authentik_tasks_workers)` /
  `max(sum by (pod)(authentik_tasks_queued))` survive the label change. Old
  series go stale after 5 min, which is expected and not an alert.
- Other fixes: proxy outposts refresh sessions on impersonation change
  (#26086), ak-axum `X-Forwarded-For` with ports (#25682), policy-binding cache
  invalidation (#25989), LDAP cached-searcher leak (#26028), websocket close code
  to outposts (#26090), and `login_hint` loop on cancel (#26111). No
  breaking-change section is published for 2026.8.3.
- **Chart diff 2026.8.2 -> 2026.8.3** (`helm pull` both, `diff -r`): only
  `Chart.yaml` (appVersion + artifacthub image annotations), `Chart.lock`
  timestamp and README badges. Templates and `values.yaml` are byte-identical.

**Managed outposts DO need a bump — the server upgrade does not do it.** This is
confirmed live: all 12 `ak-outpost-*-forward-auth` Deployments run
`ghcr.io/goauthentik/proxy:2026.8.2` and were moved there by hand on 2026-09-12.
`docs/sops/authentik.md` §2 "Managed outposts do NOT follow the server" forbids
the `KubernetesController(...).up()` loop (on 2026.8.2 it deleted
`svc/ak-outpost-homepage-forward-auth` — that Deployment is generation 1,
created 2026-09-12, which is the scar). The SOP-sanctioned path is `kubectl set
image`, one outpost at a time. These Deployments and Services exist in no git
repo (controller-created), so this is the documented non-GitOps exception, not a
bypass. The 13th outpost (`authentik Embedded Outpost`) runs inside
authentik-server and follows the server image.

Security records `F-51a63a20` (server) and `F-adb82e20` (proxy) cite
"newer upstream tag available". The house rule is bump-never-rebuild, so
this plan is their remedy. Detail stays on the records.

## 2. Pre-checks

Run from the repo root on the Mac mini (zsh). Every jsonpath is single-quoted.

1. **Premises** — `.venv/bin/python3 runbooks/plan-premises.py authentik-2026.8.3`.
   All four must pass. The outpost count must be exactly 12. A different number
   means an outpost was added or reaped, so re-derive the step 6 list before
   continuing.
2. **Healthy baseline, all pods Ready on 2026.8.2:**
   ```bash
   kubectl get pods -n kube-system -l app.kubernetes.io/instance=authentik \
     -o custom-columns='NAME:.metadata.name,IMAGE:.spec.containers[0].image,READY:.status.containerStatuses[0].ready,RESTARTS:.status.containerStatuses[0].restartCount'
   flux get hr -n kube-system authentik        # READY True, 2026.8.2
   kubectl get svc -n kube-system -o name | grep -c ak-outpost   # baseline: 25 (12 outpost + 12 -metrics + embedded)
   ```
3. **Backup gate — the live DB's Longhorn backup newer than 26h.** The empty
   merge migration makes a revert safe (§5). The backup is the floor if
   anything else surprises:
   ```bash
   kubectl get backups.longhorn.io -n storage -o json | python3 -c '
   import sys,json,datetime as d
   b=[x["status"]["backupCreatedAt"] for x in json.load(sys.stdin)["items"] if x["status"].get("volumeName")=="authentik-pg-data" and x["status"].get("state")=="Completed"]
   age=(d.datetime.now(d.timezone.utc)-d.datetime.fromisoformat(max(b).replace("Z","+00:00"))).total_seconds()/3600
   print("newest", max(b), "age_h", round(age,1)); sys.exit(0 if age<26 else 1)'
   ```
   Exit 1 means STOP. Wait for or trigger the `storage/daily-backup-all-volumes`
   run first. Measured 2026-09-25: newest `2026-09-24T03:00:10Z`, 7 Completed.
4. **Migration history still consistent** (same read as the §1 measurement):
   ```bash
   POD=$(kubectl get pods -n kube-system -l app.kubernetes.io/component=server -o jsonpath='{.items[0].metadata.name}')
   kubectl exec -n kube-system "$POD" -c server -- ak shell -c "
   from django.db.migrations.recorder import MigrationRecorder as R
   q=R.Migration.objects
   for a,n in [('authentik_core','0059_add_application_meta_hide'),('authentik_core','0063_actor'),('authentik_core','0064_user_authentik_c_usernam_2f0e4b_idx'),('authentik_rbac','0010_remove_role_group_alter_role_name'),('authentik_rbac','0011_initialpermissionspermission')]:
       print('MIG', a, n, q.filter(app=a,name=n).exists())
   print('MIG65', q.filter(app='authentik_core',name='0065_merge_20260916_1253').exists())
   " 2>/dev/null | grep MIG
   ```
   PASS: five `True` lines and `MIG65 False`. `MIG65 True` means the upgrade
   already ran, so stop and re-check the premises.
5. **Baselines for §4** (save the output):
   ```bash
   W=$(kubectl get pods -n kube-system -l app.kubernetes.io/component=worker -o jsonpath='{.items[0].metadata.name}')
   kubectl exec -n kube-system "$W" -c worker -- ak shell -c "
   from authentik.blueprints.models import BlueprintInstance as B
   from collections import Counter
   qs=B.objects.all()
   print('BP', dict(Counter(b.path.split('/')[0] if '/' in b.path else '<BARE>' for b in qs)), 'notok', [(b.path,b.status) for b in qs if b.status!='successful'])
   from authentik.providers.oauth2.models import OAuth2Provider as P
   print('GT empty', [p.name for p in P.objects.all() if not p.grant_types], 'of', P.objects.count())
   " 2>/dev/null | grep -E '^(BP|GT)'
   ```
   Measured 2026-09-25: `BP {'cberg': 21, 'default': 19, 'system': 11, 'migrations': 1} notok []`,
   `GT empty [] of 19`.
6. **Pre-flight the new image's `settings.py`** (SOP §1). This catches a moved
   path or a renamed setting that would make the init `sed` silently no-op:
   ```bash
   kubectl run ak-preflight --rm -i --restart=Never -n kube-system \
     --image=ghcr.io/goauthentik/server:2026.8.3 --command -- sh -c '
     test -f /authentik/root/settings.py && echo settings.py OK
     grep -c "SESSION_EXPIRE_AT_BROWSER_CLOSE = True" /authentik/root/settings.py'
   ```
   PASS: `settings.py OK` and `1`. Upstream `authentik/root/settings.py` is
   unchanged between the two tags (GitHub compare file list), so this is
   expected to pass. A `0` means the sed would no-op, so STOP.
7. **Not co-running:** `authentik-pg17-decommission` is `executed` or has no
   step running today. `wazuh-2xx-edge-coverage` is not in flight.
   `git log -3 --format='%h %s' -- kubernetes/apps/kube-system/authentik/` shows
   no uncommitted/unreconciled authentik change.

## 3. Steps

1. **Silence + marker** (application-update.md Step 1):
   ```bash
   runbooks/update-marker.sh add authentik kube-system 2 "2026.8.2->2026.8.3 upgrade"
   ```
   Then create an Alertmanager silence on `namespace="kube-system"` +
   `alertname=~"Authentik.*"` for 60 min, per SOP Step 1. Record the silence id.
   The §4 gates read Prometheus directly, not Alertmanager, so the silence does
   not blind them.
2. **Edit the three pins** (dry-tested on a scratch copy with macOS BSD sed,
   2026-09-25):
   ```bash
   sed -i '' \
     -e 's|^      version: 2026\.8\.2$|      version: 2026.8.3|' \
     -e 's|image: ghcr\.io/goauthentik/server:2026\.8\.2$|image: ghcr.io/goauthentik/server:2026.8.3|' \
     kubernetes/apps/kube-system/authentik/app/helmrelease.yaml
   grep -c '2026\.8\.2' kubernetes/apps/kube-system/authentik/app/helmrelease.yaml   # must print 0
   grep -c '2026\.8\.3' kubernetes/apps/kube-system/authentik/app/helmrelease.yaml   # must print 3
   ```
   The dry-run `diff` was exactly (3 hunks, nothing else):
   ```
   13c13
   <       version: 2026.8.2
   >       version: 2026.8.3
   108c108
   <           image: ghcr.io/goauthentik/server:2026.8.2
   >           image: ghcr.io/goauthentik/server:2026.8.3
   244c244
   <           image: ghcr.io/goauthentik/server:2026.8.2
   >           image: ghcr.io/goauthentik/server:2026.8.3
   ```
3. **Commit only that file and push:**
   ```bash
   git commit --only kubernetes/apps/kube-system/authentik/app/helmrelease.yaml \
     -m "chore(authentik): chart + initContainer pins 2026.8.2 -> 2026.8.3 (plan authentik-2026.8.3)"
   git show --stat HEAD            # exactly 1 file, 3 insertions / 3 deletions
   git log -1 --format=%s          # must be the subject above — amend before push if not
   git push
   ```
   The Flux webhook reconciles. `flux reconcile` only if nothing moves within
   5 min (SOP Example B pattern).
4. **Watch the roll.** The worker runs the migration on start:
   ```bash
   kubectl rollout status -n kube-system deploy/authentik-server --timeout=10m
   kubectl rollout status -n kube-system deploy/authentik-worker --timeout=10m
   ```
   Any `CrashLoopBackOff` or `InconsistentMigrationHistory` in
   `kubectl logs -n kube-system deploy/authentik-worker -c worker --tail=200`
   means go to §5 immediately.
5. **Run the §4 server gates (G1-G5) BEFORE touching any outpost.** A broken
   server with outposts on the new tag doubles the rollback.
6. **Push the 12 outposts, ONE first.** Follow SOP §2 and never use the
   `KubernetesController.up()` loop:
   ```bash
   push() {
     kubectl set image -n kube-system "deploy/ak-outpost-$1-forward-auth" proxy=ghcr.io/goauthentik/proxy:2026.8.3 &&
     kubectl rollout status -n kube-system "deploy/ak-outpost-$1-forward-auth" --timeout=3m &&
     kubectl get endpoints -n kube-system "ak-outpost-$1-forward-auth" -o jsonpath='{.subsets[0].ports[*].port}{"\n"}'
   }
   push homepage     # canary; the endpoints line must print 9000 and 9443 (either order)
   ```
   Log in to Homepage through forward-auth in a real browser. Only if that
   succeeds, continue with the rest one at a time, checking each endpoints
   line:
   ```bash
   for a in alertmanager arag-web esphome frigate headlamp longhorn nocodb phpmyadmin prometheus solarfocus-scraper uptime-kuma; do
     echo "== $a"; push "$a" || { echo "STOP at $a"; break; }
   done
   ```
   (bash/zsh-safe: the list is literal words, not a scalar variable.) Any
   `STOP` or an empty endpoints line: see §5 "outpost".
7. **Close out** (application-update.md Step 5). Delete the silence and run
   `runbooks/update-marker.sh clear authentik`.
8. **Deny rule** — the rule's own text says "REMOVE THIS RULE once the upgrade
   is done deliberately". Its glob `*authentik*` also holds every future
   authentik bump, which may be what the operator wants. **Ask the operator.**
   Remove or keep it in a separate reviewed commit to
   `runbooks/auto-update-policy.yaml`, never folded into step 3.

## 4. Verification

Each gate lists what its failure prints.

- **G1 — every pod on the new tag and Ready.**
  ```bash
  kubectl get pods -n kube-system -l app.kubernetes.io/instance=authentik \
    -o custom-columns='NAME:.metadata.name,IMAGE:.spec.containers[0].image,INIT:.spec.initContainers[*].image,READY:.status.containerStatuses[0].ready' \
    | grep -v 'server:2026.8.3.*server:2026.8.3.*true'
  ```
  PASS: only the header line. FAIL: any pod on `:2026.8.2` (old
  ReplicaSet still serving, or init skew) or `false`. A readyReplicas count
  cannot catch this — see SOP §3.
- **G2 — the migration applied, and ONLY the expected one.** Re-run pre-check 4.
  PASS: five `True` lines plus `MIG65 True`. FAIL: `MIG65 False`, which means
  the worker never finished migrating even though the pod is Ready.
- **G3 — blueprints re-applied successfully (CONTENTS).** Re-run pre-check 5.
  PASS: `notok []`, and the `system` count is ≥ 11 and `default` ≥ 19, `cberg`
  == 21, no `<BARE>`. `GT empty [] of 19` stays unchanged. FAIL looks like
  `notok [('system/object-attributes-user.yaml','error')]`, or any OIDC
  provider name in `GT empty [...]`. The latter is the silent failure where
  every login to that app fails while authentik looks healthy
  (`project_authentik_blueprint_grant_types`). Also run SOP "Verification after
  the rollout" check 2 (`kubectl get ingress -A` → `No resources found`, since an
  outpost-published Ingress is the re-appear risk after an upgrade) and check 3
  (login-flow orders `[10, 15, 20, 30, 100]`).
- **G4 — task workers alive (CONTROL).**
  CONTROL: metric authentik_tasks_workers — `min(authentik_tasks_workers)` over
  series with `version="2026.8.3"` must be ≥ 1 (baseline 3).
  ```bash
  kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
  curl -s localhost:19090/api/v1/query --data-urlencode 'query=min(authentik_tasks_workers{version="2026.8.3"})' \
    | python3 -c 'import sys,json; r=json.load(sys.stdin)["data"]["result"]; print("WORKERS", r[0]["value"][1] if r else "EMPTY"); sys.exit(0 if r and float(r[0]["value"][1])>=1 else 1)'
  kill $PF
  ```
  The `version="2026.8.3"` matcher is what makes this able to fail. Stale
  2026.8.2 series read 3 for up to 5 min after the roll. `EMPTY` means the
  new pods are not exporting or not scraped, and `0` means the worker pool is
  dead. Both exit 1. Label-shape note: expect 1 series per pod now, down from
  2, because the `pid` label is dropped (#25882). That is not a regression.
  CONTROL: alertname AuthentikTaskWorkersZero — must not be firing (read
  `/api/v1/alerts` on the same forward, since the Alertmanager silence does not
  hide Prometheus alert state).
  CONTROL: alertname AuthentikServerDown — not firing.
  CONTROL: alertname AuthentikWorkerDown — not firing.
  CONTROL: alertname AuthentikPodCrashLooping — not firing.
- **G5 — real logins, both paths (CONTENTS).**
  CONTENTS ASSERTION: an OIDC login and a forward-auth login both complete on
  2026.8.3 — measured by a real browser login to Grafana (OIDC) and to Longhorn
  or Homepage (forward-auth), then confirmed in the audit table, compared to the
  pre-window newest `login` event:
  ```bash
  kubectl exec -n kube-system deploy/authentik-pg -- psql -U authentik -d authentik -Atc \
    "select action, created from authentik_events_event where action in ('login','authorize_application') and created > now() - interval '15 minutes' order by created desc limit 5"
  ```
  PASS: at least one `login` and one `authorize_application` row newer than the
  step 3 push. FAIL: zero rows, which means the browser "worked" from a cached
  session and proved nothing. Log out first.
- **G6 — outposts on 2026.8.3, connected, Services intact (CONTENTS).**
  ```bash
  kubectl get deploy -n kube-system -o jsonpath='{range .items[*]}{.spec.template.spec.containers[0].image}{"\n"}{end}' | grep -c 'goauthentik/proxy:2026.8.3'   # 12
  kubectl get svc -n kube-system -o name | grep -c ak-outpost                                                                        # 25 (baseline)
  POD=$(kubectl get pods -n kube-system -l app.kubernetes.io/component=server -o jsonpath='{.items[0].metadata.name}')   # re-derive: the roll replaced every pod
  kubectl exec -n kube-system "$POD" -c server -- ak shell -c "
  from authentik.outposts.models import Outpost, OutpostState
  for o in Outpost.objects.all(): print('OP', o.name, sorted({s.version for s in OutpostState.for_outpost(o)}))
  " 2>/dev/null | grep '^OP' | grep -v "\['2026.8.3'\]"
  ```
  PASS: `12`, `25`, and the last command prints nothing. The server itself
  reports every outpost (including embedded) on exactly `['2026.8.3']` over
  its websocket. FAIL: `11` or fewer means a push was skipped. `24` means the
  portless-Service bug deleted one (SOP §2). An `OP x ['2026.8.2']` or `[]`
  line means that outpost is not connected on the new build.
  CONTROL: metric authentik_outpost_connection — `count(authentik_outpost_connection{version="2026.8.3"} == 1)`
  must be ≥ 12 once the 12 outposts' own exporters are scraped (baseline:
  15 series = 12 outpost jobs + 3 embedded server-side). Fewer than 12 means an
  outpost is not connected or not scraped.
  CONTROL: alertname AuthentikOutpostDisconnected — not firing 20 min after
  step 6 (its `for:` window).
  CONTROL: alertname AuthentikOutpostMetricsAbsent — not firing. This guards
  the label-shape change: if the new gauge mode dropped the series entirely,
  this is the alert that says so.

## 5. Rollback

**Server/worker (G1-G5 fail):**
```bash
git revert --no-edit <step-3 sha>
git show --stat HEAD && git log -1 --format=%s     # 1 file, subject "Revert ..."
git push
```
Flux rolls server, worker and both init containers back to 2026.8.2 together.
The `django_migrations` row for `authentik_core.0065_merge_20260916_1253` stays.
That is safe: Django's `MigrationLoader.check_consistent_history` skips applied
migrations that are not in the code's graph, and 0065's `operations` are empty.
2026.8.2's own `0064` still depends on `0063_actor`/`rbac.0011`, which are
applied earlier (pre-check 4). No data or schema to undo. Confirm the rollback by
re-running G1 with `2026.8.2` in the grep, plus G5.

If 2026.8.2 then refuses to start with a migration error (not expected), do not
fight it. Restore `authentik-pg-data` from the backup named in pre-check 3,
following `docs/sops/backup.md`. Take a fresh `pg_dump` of `deploy/authentik-pg`
to `~/db-dumps/authentik-pre-restore-<ts>.dump` before restoring, because it
holds secrets. Purge it once done.

**Outposts (any step 6 failure):** the same command with the old tag, for each
outpost already pushed:
`kubectl set image -n kube-system deploy/ak-outpost-<app>-forward-auth proxy=ghcr.io/goauthentik/proxy:2026.8.2`.
Never `kubectl delete` an outpost Deployment. If a Service vanished (`24` in
G6), recreate it by copying an intact sibling's spec. `selector` must equal
the Deployment's `spec.selector.matchLabels`, with ports 9000 (http) / 9443 (https), numeric
`targetPort` (SOP §2). If the server is reverted, outposts on 2026.8.3 still
work (server/outpost are cross-version compatible — 2026-06-04 upgrade, memory `project_authentik_outpost_upgrade`), but push them
back so versions agree.

Afterwards: delete the silence, `runbooks/update-marker.sh clear authentik`,
and record the failure on `F-2fb59c74`.

## 6. Interference notes

- **authentik-pg17-decommission (sat-attended:2026-09-26, awaiting-go): do NOT
  co-schedule.** Its steps 1-4 are done (`5f162456`). Its residual is step 5
  (an operator-local `rm -P` of dumps) plus a verification that looks for a
  forward-auth sign-in in the authentik event log on the new DB. That
  verification would read ACROSS this plan's server roll and outpost push, so a
  failure could not be attributed to either plan. Both plans also own
  `helmrelease.yaml`, which rules out concurrent edits. Declared in
  `conflicts_with`. The reciprocal entry on that plan is owed. It is not added
  here, because this planner writes only its own file. **Sequence it after that
  plan is `executed`.** The two are technically independent (the decommission
  no longer touches anything this plan changes). The conflict is about
  attribution and the shared file, not a resource race.
- **wazuh-2xx-edge-coverage (sat-attended:2026-09-26, draft):** it edits
  `helmrelease/authentik`, restarts `authentik-server`, and baselines
  `client_ip` from `authentik_events_event`. 2026.8.3 changes client-IP
  extraction (#25682, `X-Forwarded-For` with ports), so running both together
  would corrupt that plan's before/after comparison. Declared.
  **Repo correction for that plan's author:** its §1.1 table says the
  HelmRelease has no `AUTHENTIK_LISTEN__TRUSTED_PROXY_CIDRS`, but `f2d6c667`
  added it (`10.69.0.0/16`, server and worker). Its Case B remedy is already
  live.
- **talos-1.14.1 (sun-attended:2026-09-27):** a node roll evicts every authentik
  pod. Declared.
- **kube-prometheus-stack-91.4.1 (unwindowed):** G4/G6 read Prometheus. Declared.
- **flux-reconciler-impersonation (sun-attended:2026-10-11, exclusive):** declared.
- **Proposed window: `sun-attended:2026-10-04`.** It is the earliest attended slot with room
  that does not collide. sat 09-26 holds both authentik plans above, sun 09-27
  is the Talos roll, and sat 10-03's 70-min budget already holds nextcloud-mcp
  (35) and cannot take 40 more. sun 10-04 has nextcloud-34.0.4 (75 min, medium,
  namespace `office`, no SSO dependency found in its plan), which gives 115 of
  180 min and risk-load 4 of 6. Fallback: `sun-attended:2026-10-18` alongside
  n8n (45 min, no authentik touch).
- **Full-cluster SSO blast radius.** A crashlooping server or worker drops login
  for every OIDC app and all 12 forward-auth apps at once. Run it with the
  operator present, and not alongside any other identity-adjacent or
  gateway/envoy change.
- **Metrics label shape changes** (#25882: `pid` dropped from authentik gauges).
  Any dashboard that grouped by `pid` flattens. None exists in the repo.
- **Repo correction — deny-rule reason text.** The `*authentik*` rule says a
  chart-only bump "moves the templates while the running image stays put". That
  is backwards for this HelmRelease. The main image is NOT pinned in values, so
  a chart-only bump MOVES the running image. What stays put is the two
  `patch-session-settings` initContainers, which then overlay an old
  `settings.py` onto new code. The hazard is real. The mechanism in the reason
  is wrong. Fix it when the rule is removed or kept in step 8.
