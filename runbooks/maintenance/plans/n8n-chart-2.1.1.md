---
plan_id: n8n-chart-2.1.1
component: n8n
pr: null                              # no Renovate PR exists (gh pr list --search n8n,
                                      # 2026-09-25: none open). Reached the PLAN lane via
                                      # finding F-8e5e5c66 / coverage.py's no-PR path.
kind: chart
current: "2.0.1"                      # live: hr/n8n spec.chart.spec.version AND
                                      # status.history[0].chartVersion, 2026-09-25
target: "2.1.1"                       # tag exists: helm pull oci://8gears.container-registry.com/library/n8n
                                      # --version 2.1.1 -> digest sha256:ac5e38f96b91bb39539a0e1647d5f390b8aadf6c03f706e61acfd783b03a6217
update_type: minor
risk: low                             # rendered-manifest diff against OUR values is three
                                      # items (§1.2): a startupProbe, readiness path
                                      # /healthz -> /healthz/readiness, one inert worker
                                      # ConfigMap. No selector, strategy, env, volume,
                                      # service or image change. Same-image restart, no
                                      # migrations, rollback is a one-commit git revert.
est_duration_min: 25                  # 5 pre-checks + 3 render gate + 2 commit/push +
                                      # 3 reconcile/Recreate + 10 settle + 2 verify
needs_reboot: false
touches:
  namespaces: [home-automation]
  resources:
    - helmrelease/n8n                 # the one edited line: spec.chart.spec.version
    - deployment/n8n                  # probes change -> pod template changes -> Recreate
    - service/n8n                     # unchanged; its single endpoint flaps ~1 min
    - "configmap/n8n-worker-config (NEW, created by chart 2.1.1, mounted by nothing while worker.enabled=false; absent today — verified NotFound 2026-09-25)"
    - httproute/n8n                   # not edited; backend is replaced during Recreate
  shared: []                          # n8n is on its own embedded SQLite; the HTTPRoute and
                                      # Gateway envoy-external are untouched; no
                                      # ServiceMonitor, so nothing here reads Prometheus.
depends_on:
  - n8n-2.39.8                        # ORDER: image 2.38.7 -> 2.40.7 FIRST, chart AFTER.
                                      # Why this order and not the reverse is §1.3. Enforced
                                      # twice: here (unmet depends_on => skipped) and by the
                                      # premise image-is-2.40.7.
conflicts_with:
  - n8n-2.39.8                        # NOT the same window either — see §1.3/§6. The chart
                                      # restart must land on an instance that has settled
                                      # after the irreversible migration night, and its
                                      # failure must be attributable to the chart alone.
  - flux-oci-chart-sources            # HARD. That plan moves hr/n8n's chart SOURCE
                                      # (spec.chart.spec -> spec.chartRef). Version and source
                                      # of the same HelmRelease in one window = a failed
                                      # reconcile nobody can attribute, and §5 stops being a
                                      # one-commit revert. Same reasoning n8n-2.39.8 uses.
  - talos-1.14.1                      # a node drain during the Recreate is harmless to data
                                      # but makes §4's restart-count gate unreadable.
exclusive: false
security_ref: null                    # no security driver: the chart carries no image of its
                                      # own for this deployment (§1.2 — image is pinned).
capability_change: false              # probes and one unused ConfigMap. No n8n behaviour,
                                      # UI, API or workflow semantics change.
rollback_class: git-revert            # nothing forward-only: same image, no DB write, the
                                      # new ConfigMap is Helm-owned and pruned on revert.
finding_refs:                         # queried 2026-09-25 with SWEEP_PG_DSN up
                                      # (`finding list --grep n8n`)
  - F-8e5e5c66                        # "n8n: chart 2.0.1 -> 2.1.1 (minor)" — THIS plan.
                                      # NOT claimed: F-09588936 / F-910a4a4b (image; owned by
                                      # n8n-2.39.8).
status: draft
window: null
premises:
  - id: image-is-2.40.7
    why: >-
      Ordering guard. This plan is written to run AFTER n8n-2.39.8 has shipped
      image 2.40.7 (§1.3). If the image is still 2.38.7 the dependency has not
      executed — do not run. If it is something else, n8n-2.39.8 was re-targeted
      again: re-check §1.2 point 4 (readiness endpoint on that image) and update
      this premise before running.
    run: kubectl get deploy -n home-automation n8n -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: n8nio/n8n:2.40.7
  - id: chart-still-2.0.1
    why: "The rendered diff in §1.2 is 2.0.1 -> 2.1.1; a different starting chart voids it."
    run: kubectl get helmrelease -n home-automation n8n -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: "2.0.1"
  - id: git-chart-pin-2.0.1
    why: "Git side of the same premise; §3.2's sed must hit exactly one line."
    run: "git show HEAD:kubernetes/apps/home-automation/n8n/app/helmrelease.yaml | grep -c 'version: 2.0.1'"
    expect_exact: "1"
  - id: helmrelease-ready
    why: "Do not stack a chart bump on a release that is already failing (e.g. left Failed by n8n-2.39.8)."
    run: kubectl get helmrelease -n home-automation n8n -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: strategy-still-recreate
    why: >-
      Single replica on RWO Longhorn PVC n8n-config: anything but Recreate risks a
      Multi-Attach hang on the pod-template change this plan causes
      (docs/sops/longhorn-rwo-multi-attach.md). Chart 2.1.1 renders Recreate
      unchanged (§1.2), this asserts the live side.
    run: kubectl get deploy -n home-automation n8n -o jsonpath='{.spec.strategy.type}'
    expect_exact: Recreate
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/longhorn-rwo-multi-attach.md
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/auto-update.md
generated: "2026-09-25"
---

# n8n: Helm chart 2.0.1 → 2.1.1 (probes only; runs AFTER n8n-2.39.8)

## 1) Summary & why held

### 1.1 What changes

One line in `kubernetes/apps/home-automation/n8n/app/helmrelease.yaml`:
`spec.chart.spec.version: 2.0.1 → 2.1.1` (chart `n8n` from the 8gears OCI
registry, HelmRepository `flux-system/n8n`). The image stays pinned by
`values.image.tag`.

**Why held:** auto-update-policy rule `match: "*n8n*"`, `max: patch`. That
rule exists for the n8n *image*, whose beta ships on the next minor line with
no prerelease marker. Its glob also catches this *chart*, where the concern
does not apply. So the hold is **a false positive in substance**, even though
the rule behaved as written. See the repo correction in §6.4.

### 1.2 The chart diff, measured (2026-09-25)

The diff was taken by pulling 2.0.1, 2.1.0 and 2.1.1 (`helm pull … --untar`). The
2.1.x changelog in `Chart.yaml` `artifacthub.io/changes` has four items:
- readiness moves to `/healthz/readiness`;
- a `startupProbe` is added to main, worker and webhook;
- worker `QUEUE_HEALTH_CHECK_ACTIVE` now defaults to true;
- "Updated n8n to 2.36.8".

Both versions were rendered with `helm template` using **our exact
HelmRelease values**. The rendered objects were diffed after normalising the
`rollme` random annotation and the version labels. **The complete diff is:**

1. `Deployment/n8n` adds a `startupProbe` (`httpGet /healthz`, `periodSeconds: 10`, `failureThreshold: 30`).
2. `Deployment/n8n` `readinessProbe.httpGet.path` changes from `/healthz` to `/healthz/readiness`. Liveness is unchanged: `/healthz`, 10 s × 3.
3. A new `ConfigMap/n8n-worker-config` (`QUEUE_HEALTH_CHECK_ACTIVE: "true"`) appears, created because `worker.config` is now non-empty by default (`{{- if .Values.worker.config }}`). Only `deployment.worker.yaml` references it, and it is not rendered with `worker.enabled: false`. It is inert.
4. `checksum/config` pod annotation changes. It is irrelevant here, because `rollme: {{ randAlphaNum 5 }}` already rolls the pod on every Helm upgrade.

The following did **not** change:
- **Selector:** unchanged (`instance`, `name`, `type: master`), so there is no immutable-field delete/recreate.
- **Strategy:** unchanged (Recreate).
- **Env set:** unchanged. The `env-set-unchanged` premise of n8n-2.39.8 stays true.
- **Service type:** unchanged. The `"ClusterIP_"` default fix is moot because we set `type: ClusterIP`.
- **Ingress `pathType` default:** moot, because the chart renders no Ingress.

**Default image: YES it changed, NO it does not reach us.** `appVersion`
moves from 1.122.4 to **2.36.8**. That is the image a values file *without*
`image.tag` would get. Our values pin `tag`, and the rendered image is
`n8nio/n8n:2.38.7` under both charts today. **The one way this chart bump
could hurt data** is if `image.tag` were ever lost from values. The chart
would then silently deploy 2.36.8 onto a 2.40.7-migrated SQLite schema, an
unsupported downgrade. §3.3 therefore gates on the rendered image before
commit.

**Point 4: the new readiness endpoint works on our images.** In both
n8n@2.38.7 and n8n@2.40.7, `abstract-server.ts` `setupHealthCheck()` answers
`/healthz/readiness` with 200 only when `connected && migrated &&
fullyReady`. `server.ts` calls `markAsReady()` at the end of init (line 121 at
2.38.7, line 124 at 2.40.7). Live on 2.38.7 (2026-09-25, port-forward):
`healthz=200 readiness=200`.

### 1.3 Decision: separate plan, chart AFTER the image. Not folded, not before.

**Why not fold it into n8n-2.39.8:** that plan's night is irreversible
(migration 9, `DropGitConnectionTables`, has no `down()`). Its rollback is a
Longhorn snapshot revert, and it already refuses to share a window with
`flux-oci-chart-sources` because "moving n8n's chart SOURCE in the same window
as its image tag makes a failed reconcile un-attributable". A chart
*version* bump is the same class of second variable. There is also a
concrete mechanism (next paragraph) by which the chart makes that night
worse.

**Why not chart first**, even though 2.1.1's changelog says the
startupProbe stops "the liveness probe [killing] containers that are still
running migrations":

- **The startupProbe buys nothing for n8n ≥ 2.38.** The chart's premise
  ("n8n only starts listening once … migrations are done") is false for our
  versions. In `base-command.ts` at both 2.38.7 and 2.40.7 the order is
  `dbConnection.init()` → `server.init()` (listen and `/healthz`) →
  `dbConnection.migrate()`. `/healthz` returns 200 *before* migrations start,
  so the startupProbe succeeds at once and hands over to the identical
  liveness probe. The migration-time liveness exposure is the same under
  either chart.
- **The readiness change alters Helm's wait on the migration night.**
  `hr/n8n` has no `spec.timeout` (read live), so Flux's default 5 min applies.
  Helm waits on Deployment readiness. Under 2.0.1, readiness is `/healthz`,
  which returns 200 at listen, so the upgrade completes in seconds while
  migrations continue. Under 2.1.1, readiness is 503 until all 13 migrations
  and full init finish. If that exceeds 5 min on the 489 MiB SQLite file, the
  HelmRelease goes **Failed** mid-migration. n8n-2.39.8 §3.3 disables
  remediation, so no auto-rollback fires, but its §3.8 then restores
  `retries: 3` onto a release in Failed state. That is a path its reviewers
  never assessed. Chart-after keeps the irreversible night on the exact Helm
  semantics that plan was written and reviewed against.
- **What chart-first would have gained** is a truthful `1/1` during the
  migration rollout: the pod is NotReady until migrated, instead of serving
  "n8n is starting up". That benefit is cosmetic. The item above is a risk.

**Chart-after costs nothing:**
- This plan's rollout is a same-image restart with no migrations.
- The high-risk plan runs unchanged: its `chart-still-2.0.1` premise stays
  true and needs no edit.
- The finding is severity `monitor` with no security driver, so waiting
  until after 2026-10-18 is free.

## 2) Pre-checks

### 2.1 Premises (frontmatter)
Run `runbooks/plan-premises.py` for this plan. All five must pass.
`image-is-2.40.7` fails today by design: it is the ordering lock.

### 2.2 The dependency is executed and settled
```bash
grep -E '^status:' runbooks/maintenance/plans/n8n-2.39.8.md     # expect: status: executed
kubectl get pods -n home-automation -l app.kubernetes.io/name=n8n \
  -o jsonpath='{.items[0].status.containerStatuses[0].restartCount} {.items[0].status.startTime}{"\n"}'
```
PASS: `executed`, and the pod has run ≥24 h since that window with restartCount
unchanged. FAIL example: `status: draft` means stop. A startTime in the last
24 h means the 2.40.7 instance has not settled, so stop.

### 2.3 Baseline for §4 (capture now, on the running pod)
```bash
kubectl exec -n home-automation deploy/n8n -- sh -c "n8n list:workflow --onlyId 2>/dev/null | grep -E '^[A-Za-z0-9]{16}\$' | wc -l"
kubectl exec -n home-automation deploy/n8n -- sh -c "n8n list:workflow --active=true --onlyId 2>/dev/null | grep -E '^[A-Za-z0-9]{16}\$' | sort | cksum"
```
Record both values. As of 2026-09-25 on 2.38.7 they read `15` and
`3124227881 136` (8 active). **Use the values captured at window time, not
these**, because n8n-2.39.8 may legitimately change them. The command form is
taken from n8n-2.39.8 §3.1a, including its reasoning. The 16-char id filter
strips the deprecation-warning line and reads `0` (FAIL) if the id format ever
changes.

### 2.4 Silence
Post the Alertmanager silence per `docs/sops/application-update.md` (update
step 1), scoped `namespace=home-automation`, 30 min. The Recreate takes n8n
down for about 1 min.

## 3) Steps

### 3.1 Sync
```bash
cd /Users/mu/code/cberg-home-nextgen && git fetch origin main && git merge --ff-only origin/main
```

### 3.2 Edit the chart version
```bash
sed -i '' 's/^\([[:space:]]*\)version: 2\.0\.1$/\1version: 2.1.1/' \
  kubernetes/apps/home-automation/n8n/app/helmrelease.yaml
```
This was dry-tested 2026-09-25 on a scratch copy of the real file with BSD sed.
`grep -c 'version: 2.0.1'` is `1` before. The resulting diff, verbatim:
```
12c12
<       version: 2.0.1
---
>       version: 2.1.1
```
`git diff --stat` must show exactly 1 file and 1 line changed.

### 3.3 BLOCKING render gate: the image must not fall back to the chart default
```bash
S=$(mktemp -d) && helm pull oci://8gears.container-registry.com/library/n8n --version 2.1.1 --untar --untardir "$S" >/dev/null 2>&1 && \
python3 -c "import yaml;d=yaml.safe_load(open('kubernetes/apps/home-automation/n8n/app/helmrelease.yaml'));yaml.safe_dump(d['spec']['values'],open('$S/v.yaml','w'))" && \
helm template n8n "$S/n8n" -n home-automation -f "$S/v.yaml" | grep -E '^[[:space:]]+image: "n8nio/n8n:' ; \
helm template n8n "$S/n8n" -n home-automation -f "$S/v.yaml" | grep -c 'path: /healthz/readiness'
```
PASS: the first command prints exactly `image: "n8nio/n8n:2.40.7"`, and the
count is `1`.

FAIL, with the ABORT reason:
- `n8nio/n8n:2.36.8` means `image.tag` is gone from values. The chart would
  downgrade onto a migrated schema.
- `0` means the wrong chart version was pulled.

Measured 2026-09-25 against today's values: `image: "n8nio/n8n:2.38.7"` and
`1`. That confirms the gate reads the pinned tag, not `appVersion`.

### 3.4 Commit and push (shared worktree)
Commit message (`/tmp/n8n-chart-msg.txt`):
```
fix(n8n): chart 2.0.1 -> 2.1.1 (probes: startupProbe + /healthz/readiness)

Image stays pinned at 2.40.7. Rendered diff vs our values: startupProbe added,
readiness /healthz -> /healthz/readiness, inert n8n-worker-config ConfigMap.

Plan: runbooks/maintenance/plans/n8n-chart-2.1.1.md
```
```bash
git commit --only kubernetes/apps/home-automation/n8n/app/helmrelease.yaml -F /tmp/n8n-chart-msg.txt
git show --stat HEAD && git log -1 --format=%s    # MUST be this subject, 1 file; amend before push if not
git push origin main
```
No manual `flux reconcile`: the push webhook drives it.

### 3.5 Watch
```bash
kubectl get pods -n home-automation -l app.kubernetes.io/name=n8n -w    # old pod terminates fully, new one reaches 1/1
```
Under 2.1.1, `1/1` now means `connected && migrated && fullyReady`. It is no
longer just "process listening".

## 4) Verification

Each gate names the failure it catches.

```bash
# V1 chart actually applied   — FAIL prints n8n-2.0.1 (HR did not upgrade)
kubectl get deploy -n home-automation n8n -o jsonpath='{.metadata.labels.helm\.sh/chart}{"\n"}'          # n8n-2.1.1
kubectl get hr -n home-automation n8n -o jsonpath='{.status.history[0].chartVersion} {.status.conditions[?(@.type=="Ready")].status}{"\n"}'   # 2.1.1 True
# V2 probes are the new ones  — FAIL prints /healthz and an empty startup value
kubectl get deploy -n home-automation n8n -o jsonpath='{.spec.template.spec.containers[0].readinessProbe.httpGet.path} {.spec.template.spec.containers[0].startupProbe.failureThreshold}{"\n"}'   # /healthz/readiness 30
# V3 image did NOT move       — FAIL prints n8nio/n8n:2.36.8 (chart default leaked => §5 immediately)
kubectl get deploy -n home-automation n8n -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'  # n8nio/n8n:2.40.7
# V4 the endpoint is really in the Service — FAIL prints false or nothing
kubectl get endpointslice -n home-automation -l kubernetes.io/service-name=n8n -o jsonpath='{.items[*].endpoints[*].conditions.ready}{"\n"}'   # true
```
The EndpointSlice exists today (`n8n-762tk`, ready `true`). With readiness on
`/healthz/readiness`, `true` now proves the DB is connected and migrated,
which `/healthz` never did.

```bash
# V5 serving, both endpoints
kubectl port-forward -n home-automation svc/n8n 15678:5678 >/dev/null 2>&1 & PF=$!; sleep 4
curl -s -o /dev/null -w 'healthz=%{http_code}\n'   http://localhost:15678/healthz
curl -s -o /dev/null -w 'readiness=%{http_code}\n' http://localhost:15678/healthz/readiness
kill $PF
```
PASS: both `200`. Readiness `503` means the pod is up but not migrated, or not
fully initialised. It then cannot be Ready, and V4 would also fail.

```bash
# V6 CONTENTS — same inventory as the §2.3 baseline
kubectl exec -n home-automation deploy/n8n -- sh -c "n8n list:workflow --onlyId 2>/dev/null | grep -E '^[A-Za-z0-9]{16}\$' | wc -l"
kubectl exec -n home-automation deploy/n8n -- sh -c "n8n list:workflow --active=true --onlyId 2>/dev/null | grep -E '^[A-Za-z0-9]{16}\$' | sort | cksum"
```
PASS: both are identical to §2.3. A changed active cksum means a workflow was
deactivated on boot. `0` means the filter matched nothing, which is a FAIL,
never a pass.

```bash
# V7 settle 10 min, then: no probe-driven restarts
kubectl get pods -n home-automation -l app.kubernetes.io/name=n8n -o jsonpath='{.items[0].status.containerStatuses[0].restartCount}{"\n"}'   # 0
kubectl get events -n home-automation --field-selector involvedObject.kind=Pod | grep -i n8n | grep -iE 'unhealthy|probe' || echo NO_PROBE_EVENTS
```
PASS: `0` and `NO_PROBE_EVENTS`. A readiness path the image does not serve
would show `Readiness probe failed: HTTP probe failed with statuscode: 404`
here. The grep is case-insensitive.

`configmap/n8n-worker-config` now exists. This is expected (§1.2 item 3) and
is not a failure.

## 5) Rollback

Nothing forward-only happened: same image, no DB writes by this change.

```bash
git fetch origin main && git merge --ff-only origin/main
git revert --no-edit <sha-of-§3.4>
git show --stat HEAD && git log -1 --format=%s    # 1 file, subject starts "Revert \"fix(n8n): chart 2.0.1 -> 2.1.1"
git push origin main
```
Confirm the cluster is back:
- `kubectl get deploy -n home-automation n8n -o jsonpath='{.metadata.labels.helm\.sh/chart} {.spec.template.spec.containers[0].readinessProbe.httpGet.path}'` shows `n8n-2.0.1 /healthz`.
- `kubectl get cm -n home-automation n8n-worker-config` returns `NotFound` (Helm prunes it).
- V3, V5 and V6 pass again.

**If V3 ever printed `2.36.8`** (image downgraded onto a 2.40.7 schema): do
the revert *immediately*. Then check n8n-2.39.8 §4.2's migration count. If
2.36.8 booted and wrote anything, treat it as n8n-2.39.8 §5.2 (snapshot
revert), not as a chart rollback. §3.3 exists so this cannot happen.

## 6) Interference notes

### 6.1 Ordering and windows
- `depends_on: [n8n-2.39.8]` plus `conflicts_with: [n8n-2.39.8]`: this plan
  runs in a *later* window than the image upgrade. The earliest sensible slot
  is the first window ≥24 h after n8n-2.39.8 executes (it is proposed for
  sun-attended:2026-10-18).
- Risk low, `capability_change: false`, git-revert. It fits a Saturday or
  nightly slot. The execution class comes from `autonomy-policy.yaml`, not
  from this file.
- The window agent assigns `window:`.

### 6.2 Shared surfaces
None. n8n runs on its own SQLite file. The HTTPRoute and Gateway are
untouched, and n8n has no ServiceMonitor, so verification never reads
Prometheus. No kube-prometheus-stack conflict is needed.

### 6.3 Other plans that touch hr/n8n
- `flux-oci-chart-sources` (chart source) is listed in `conflicts_with`.
- `flux-reconciler-impersonation` and `float-tag-pinning` list home-automation
  but do not edit this chart's version. They are not declared.

### 6.4 Repo correction (reported, not fixed here)
The `*n8n*` rule in `runbooks/auto-update-policy.yaml` is justified only by
the n8n image's channel layout ("beta on the next MINOR line"). Its glob also
holds the 8gears chart, which has no such channel. Consider narrowing it to
the image (e.g. `n8nio/n8n`), so that future chart minors like this one go
through the ordinary safe-update gates.

Upstream correction worth filing with 8gears: the startupProbe rationale in
`values.yaml` ("n8n only starts listening once … migrations are done") does
not hold for current n8n, which listens before `migrate()`.
