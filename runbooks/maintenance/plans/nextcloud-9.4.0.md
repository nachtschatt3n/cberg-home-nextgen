---
plan_id: nextcloud-9.4.0
component: nextcloud
pr: null                              # no open Renovate PR for the chart (gh pr list, 2026-10-01).
                                      # Held group nextcloud-9.4.0 from the cron sweep cycle
                                      # b23be87b-1659-497e-b2c0-4a8eaca41f06; routed to PLAN by the
                                      # `*nextcloud*` deny rule.
kind: chart
current: "9.3.0"
target: "9.4.0"
update_type: minor
risk: low                             # MEASURED (§1.2): 9.3.0 -> 9.4.0 differs ONLY in Chart.yaml
                                      # appVersion 34.0.4 -> 35.0.1. With our values (image.tag pinned)
                                      # the rendered manifests differ in 14 METADATA label lines on 7
                                      # objects and in NO pod template -> no pod roll, no occ run, no
                                      # migration. The risk that the deny rule names (occ migrations,
                                      # Mail custom_app, stuck maintenance) lives entirely in
                                      # nextcloud-fleet-35.0.1, which this plan depends on.
est_duration_min: 20                  # pre-checks + render-diff gate ~8, commit/reconcile ~4,
                                      # verification incl. Mail gate ~6, slack ~2
needs_reboot: false
touches:
  namespaces: [office]
  resources:
    - helmrelease/nextcloud                     # chart.spec.version 9.3.0 -> 9.4.0 (one line)
    - deployment/nextcloud                      # metadata labels only (helm.sh/chart,
                                                # app.kubernetes.io/version); pod template unchanged
    - deployment/nextcloud-metrics              # metadata labels only
    - cronjob/nextcloud-cron                    # metadata labels only; jobTemplate unchanged
    - configmap/nextcloud-config                # metadata labels only; data unchanged
    - configmap/nextcloud-phpconfig             # metadata labels only; data unchanged
    - service/nextcloud                         # metadata labels only
    - service/nextcloud-metrics                 # metadata labels only
  shared: []                                    # no Gateway/HTTPRoute, cert-manager, cilium,
                                                # coredns, Longhorn or CIFS operation. Bundled
                                                # mariadb subchart is byte-identical (20.5.5 both).
depends_on:
  - nextcloud-fleet-35.0.1                      # the image 34.0.4 -> 35.0.1 MAJOR. This chart's
                                                # appVersion IS 35.0.1; applying it while 34.0.4
                                                # runs breaks the operator's lockstep rule, stamps a
                                                # false app.kubernetes.io/version, and FAILS the fleet
                                                # plan's `our-chart-pin-is-9.3.0` premise. See §1.3:
                                                # the preferred path is to FOLD this line into the
                                                # fleet plan's Commit B and supersede this file.
conflicts_with:
  # - nextcloud-redis-hardening (RESOLVED 2026-10-04: executed + retired 418faa1e (now:2026-10-03); dead ref removed per the dead-ref convention)
    # same helmrelease.yaml + same helm release; its §5
                                                # restores helmrelease.yaml from a parent that would
                                                # predate this bump; its render gate is pinned to
                                                # "chart $V" measured on 9.3.0.
  - bitnamilegacy-exit-nextcloud-db             # same helmrelease.yaml / same helm release.
  - flux-oci-chart-sources                      # stage 5 replaces chart.spec.version with an OCI
                                                # chartRef in this exact block; §3's sed + gates
                                                # would read nothing.
  - helm-drift-detection                        # patches helmrelease/nextcloud.
  - flux-fleet-0.60.0                           # helm-controller restart mid-upgrade.
  - flux-reconciler-impersonation               # changes the identity office/nextcloud reconciles
                                                # under; a reconcile failure would be misattributed.
exclusive: false
security_ref: null                    # dispatch: "No security evidence". No finding exists for the
                                      # chart leg (policy-cli finding list --grep nextcloud, 2026-10-01).
capability_change: false              # metadata labels only; no image, value, template or app change.
                                      # Every user-visible change of NC 35 belongs to (and is declared
                                      # true by) nextcloud-fleet-35.0.1.
rollback_class: git-revert            # nothing forward-only: no pod start, no occ, no DB write (§5).
finding_refs: []                      # F-38fecaa8 (chart 9.3.0 -> 9.4.0, found open 2026-10-05) is
                                      # claimed by nextcloud-fleet-35.0.1, which now delivers this leg.
                                      # Original note: none existed for chart 9.3.0 -> 9.4.0 (queried 2026-10-01 with
                                      # SWEEP_PG_DSN up). The image findings F-7344f3ec / F-7bcfda63
                                      # are owned by nextcloud-fleet-35.0.1 and deliberately NOT
                                      # double-claimed here.
review: null
status: superseded                    # 2026-10-05: FOLDED into nextcloud-fleet-35.0.1 Commit B (the
                                      # preferred path of §1.3) per operator decision relayed by the
                                      # coordinator. Kept for the evidence trail; never runs.
superseded_by: nextcloud-fleet-35.0.1
window: null
premises:
  # Runner grammar (plan-premises.py): kubectl/flux/git/helm READ verbs + bare text filters.
  # Run from the REPO ROOT. Measured 2026-10-01 (premise 1, 2 and 6 are EXPECTED to fail
  # until nextcloud-fleet-35.0.1 has executed — that is the depends_on, made checkable).
  - id: fleet-executed-image-is-35.0.1-on-both-containers
    why: >-
      The lockstep precondition. This plan only ever runs AFTER the 35.0.1 image is live; then the
      chart's appVersion matches what runs. Today (2026-10-01) it reads
      "docker.io/nextcloud:34.0.4 nextcloud:34.0.4" -> FAIL, correctly.
    run: kubectl get deploy -n office nextcloud -o jsonpath='{.spec.template.spec.containers[?(@.name=="nextcloud")].image} {.spec.template.spec.containers[?(@.name=="worker")].image}'
    expect_exact: "docker.io/nextcloud:35.0.1 nextcloud:35.0.1"
  - id: git-chart-pin-is-9.3.0-exactly-once
    why: >-
      §3 rewrites exactly one line-anchored `version: 9.3.0`. If the fleet plan was refreshed to
      carry the chart in its Commit B (the preferred fold, §1.3), this reads 0 -> this plan is
      SUPERSEDED: set status superseded, do not run.
    run: "git show HEAD:kubernetes/apps/office/nextcloud/app/helmrelease.yaml | grep -c '^      version: 9.3.0$'"
    expect_exact: "1"
  - id: live-chart-pin-is-9.3.0
    why: Same fact, live side; a mismatch with git means a reconcile is in flight or failed.
    run: kubectl get helmrelease -n office nextcloud -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: "9.3.0"
  - id: helmrelease-ready
    why: Starting a helm upgrade on a failed or in-flight one is how remediation thrash begins.
    run: kubectl get helmrelease -n office nextcloud -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: fleet-temporary-remediation-restored
    why: >-
      nextcloud-fleet-35.0.1 §3.3 sets upgrade.remediation.retries 0 for its attempt and restores 3
      in its §3.6. Running this plan between those two commits would ride on retries 0 and on the
      26-min startup budget — i.e. inside the fleet plan's open state.
    run: kubectl get helmrelease -n office nextcloud -o jsonpath='{.spec.upgrade.remediation.retries}'
    expect_exact: "3"
  - id: chart-source-is-helmrepository
    why: >-
      §3 edits chart.spec.version; if flux-oci-chart-sources stage 5 moved nextcloud to an OCI
      chartRef, the field is gone and this plan must be re-derived.
    run: kubectl get helmrelease -n office nextcloud -o jsonpath='{.spec.chart.spec.sourceRef.kind}/{.spec.chart.spec.sourceRef.name}'
    expect_exact: "HelmRepository/nextcloud"
  - id: server-deployment-one-ready-replica
    why: A pod not Ready now is mid-restart or stuck in maintenance; the §4 no-roll gate would lie.
    run: kubectl get deploy -n office nextcloud -o jsonpath='{.status.readyReplicas}'
    expect_exact: "1"
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/maintenance-windows.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-10-01"
---

# nextcloud chart 9.3.0 -> 9.4.0 (appVersion 34.0.4 -> 35.0.1) — the chart leg of the 35 lockstep

> **SUPERSEDED 2026-10-05 by `nextcloud-fleet-35.0.1`.** The FOLD path (§1.3) was
> taken: the chart line `version: 9.3.0 -> 9.4.0` now rides in that plan's
> Commit B together with image 35.0.1, its render-diff gate is that plan's
> §2.0(e), and the chart finding F-38fecaa8 is claimed there. Nothing below is to
> be executed; the measurements (§1.2) remain the evidence for the fold.

## 1) Summary & why held

### 1.1 What moves

| Leg | From | To | Where |
|---|---|---|---|
| `spec.chart.spec.version` | 9.3.0 | **9.4.0** | `kubernetes/apps/office/nextcloud/app/helmrelease.yaml` line 11 |
| image `image.tag`, worker sidecar, notify-push | 35.0.1 (after fleet) | **unchanged** | owned by `nextcloud-fleet-35.0.1` |
| bundled mariadb subchart 20.5.5, exporter 0.9.1 | — | **unchanged** | identical in both chart tarballs |

Why held: the `*nextcloud*` deny rule — *"chart+image must bump together and run
occ migrations (Mail custom_app / stuck-maintenance trap) — operator-supervised
only."* That reason is about the IMAGE major, not this chart.

### 1.2 Upstream evidence — the chart is appVersion-only

Verified 2026-10-01 against `https://nextcloud.github.io/helm/index.yaml`: **9.4.0
exists**, created 2026-09-30T07:11Z, `appVersion: 35.0.1`; 9.3.0 is
`appVersion: 34.0.4`; dependency pins identical (postgresql 16.7.4, mariadb 20.5.5,
redis 21.1.3, collabora-online 1.1.60).

`diff -ru` of the two release tarballs
(`github.com/nextcloud/helm/releases/download/nextcloud-9.{3,4}.0/nextcloud-9.{3,4}.0.tgz`)
is exactly two lines in `Chart.yaml`:

```
-appVersion: 34.0.4
+appVersion: 35.0.1
-version: 9.3.0
+version: 9.4.0
```

`helm template` of both charts with OUR values (`spec.values` of the live
HelmRelease) differs in 14 lines, all `helm.sh/chart: nextcloud-9.4.0` and
`app.kubernetes.io/version: "35.0.1"` on the METADATA of ConfigMap
`nextcloud-config`, ConfigMap `nextcloud-phpconfig`, Service `nextcloud-metrics`,
Service `nextcloud`, Deployment `nextcloud`, Deployment `nextcloud-metrics`,
CronJob `nextcloud-cron`. The pod templates use `nextcloud.selectorLabels`
only (`templates/deployment.yaml` lines 23/27, `cronjob.yaml` 26/38), which do not
carry chart/version — so **no pod template changes, no rollout, no occ upgrade**.
`.Chart.AppVersion` reaches the image only when `image.tag` is empty
(`_helpers.tpl` `nextcloud.image`); ours is pinned.

### 1.3 Fold or follow — the recommendation

The operator rule is *chart+image move to NEWEST in lockstep*. Until 2026-09-30 no
chart carried a 35.x appVersion, so `nextcloud-fleet-35.0.1` was written image-only
on 9.3.0 with a hard premise, `newest-published-chart-still-carries-a-34-appversion`,
that says: *"The day upstream publishes a chart with appVersion 35.x this premise
FAILS, and the plan must be REFRESHED in place to a chart+image lockstep."*
**That day was 2026-09-30. The fleet premise now fails.**

- **Preferred — FOLD:** refresh `nextcloud-fleet-35.0.1` in place (keep its plan_id,
  window and GO issue) so its Commit B also carries
  `sed -i '' -E 's|^      version: 9\.3\.0$|      version: 9.4.0|'` on
  `helmrelease.yaml`, retire its appVersion-34 premise, flip its
  `our-chart-pin-is-9.3.0` premise, and add a §4 assertion
  `helm.sh/chart=nextcloud-9.4.0`. Because the chart diff is metadata only, the
  fold changes nothing in the fleet plan's risk, timing or rollback (its §5.3
  backup-restore already covers the whole release). When that refresh lands,
  this plan's premise `git-chart-pin-is-9.3.0-exactly-once` reads 0 -> set this
  file `status: superseded`.
- **Fallback — FOLLOW (this file):** if the fleet plan runs unchanged, this plan
  runs AFTER it (any later slot, or straight after its §3.6 in the same slot) and
  brings the chart to 9.4.0. Its effect is metadata-only either way.
- **Never:** apply 9.4.0 BEFORE the image is 35.0.1. That inverts the lockstep,
  labels a 34.0.4 deployment `version: "35.0.1"`, and fails the fleet plan's
  `our-chart-pin-is-9.3.0` premise mid-queue.

If the operator answers fleet D1 with "wait", this plan waits with it — the
depends_on keeps it unrunnable, which is correct.

### 1.4 Risk

Low. Nothing starts, nothing migrates. The one way this could do harm is if the
helm upgrade rolled the pod after all (e.g. a values change landed between
planning and execution that renders differently on 9.4.0); §2.2's render-diff
gate and §4 gate 2 (pod UID unchanged) both catch that.

## 2) Pre-checks

Run from `/Users/mu/code/cberg-home-nextgen` on the Mac mini. Scratch dir
`/Users/mu/db-dumps/nextcloud-9.4.0-exec/` (literal path everywhere). One Bash
call per block.

**2.0 Premises**

```bash
.venv/bin/python3 runbooks/plan-premises.py nextcloud-9.4.0     # all PASS or STOP
mkdir -p /Users/mu/db-dumps/nextcloud-9.4.0-exec && chmod 700 /Users/mu/db-dumps/nextcloud-9.4.0-exec
```

HOW IT FAILS: `fleet-executed-...` FAIL => the fleet plan has not run: STOP (not
due). `git-chart-pin-is-9.3.0-exactly-once` reads 0 => folded: mark this plan
`superseded`, STOP. `fleet-temporary-remediation-restored` reads 0 => the fleet
plan's §3.6 has not landed: STOP.

**2.1 Fleet outcome is healthy (not just its image)**

```bash
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ status --output=json"
#   EXPECT: "version":"35.0.1.<n>"  "maintenance":false  "needsDbUpgrade":false
#   HOW IT FAILS: 34.x => fleet not done; maintenance true / needsDbUpgrade true => the fleet
#   upgrade is stuck: STOP and hand back to nextcloud-fleet-35.0.1 §5.1, never stack this on it.
```

**2.2 Render-diff gate — re-measure that 9.4.0 is still metadata-only against TODAY's values**

`helm --repo` currently fails on this Mac (`no cached repo found ... temp-*-index.yaml`,
measured 2026-10-01), so the tarballs come straight from the GitHub release.

```bash
cd /Users/mu/db-dumps/nextcloud-9.4.0-exec && rm -rf c93 c94 && mkdir c93 c94
curl -sfL https://github.com/nextcloud/helm/releases/download/nextcloud-9.3.0/nextcloud-9.3.0.tgz | tar xz -C c93
curl -sfL https://github.com/nextcloud/helm/releases/download/nextcloud-9.4.0/nextcloud-9.4.0.tgz | tar xz -C c94
grep -E '^(version|appVersion):' c94/nextcloud/Chart.yaml
#   EXPECT: appVersion: 35.0.1 / version: 9.4.0   (empty => download failed: STOP)
cd /Users/mu/code/cberg-home-nextgen
.venv/bin/python3 -c "
import yaml;d=yaml.safe_load(open('kubernetes/apps/office/nextcloud/app/helmrelease.yaml'))
yaml.safe_dump(d['spec']['values'],open('/Users/mu/db-dumps/nextcloud-9.4.0-exec/values.yaml','w'))"
for v in 93 94; do
  helm template nextcloud /Users/mu/db-dumps/nextcloud-9.4.0-exec/c$v/nextcloud -n office \
    -f /Users/mu/db-dumps/nextcloud-9.4.0-exec/values.yaml > /Users/mu/db-dumps/nextcloud-9.4.0-exec/render-$v.yaml || echo "RENDER $v FAILED"
done
wc -l /Users/mu/db-dumps/nextcloud-9.4.0-exec/render-93.yaml /Users/mu/db-dumps/nextcloud-9.4.0-exec/render-94.yaml
diff /Users/mu/db-dumps/nextcloud-9.4.0-exec/render-93.yaml /Users/mu/db-dumps/nextcloud-9.4.0-exec/render-94.yaml \
  | grep -E '^[<>]' | grep -vE '^[<>] +(helm\.sh/chart: nextcloud-9\.[34]\.0|app\.kubernetes\.io/version: "(34\.0\.4|35\.0\.1)")$' | wc -l
diff /Users/mu/db-dumps/nextcloud-9.4.0-exec/render-93.yaml /Users/mu/db-dumps/nextcloud-9.4.0-exec/render-94.yaml | grep -c '^>'
```

EXPECT: both renders > 1000 lines (1431 on 2026-10-01); the first count **0**
(no changed line other than the two label kinds); the second count **14** (7
objects x 2 labels). HOW IT FAILS: a render of 0 lines or `RENDER .. FAILED` =>
the gate measured nothing: STOP. First count > 0 => 9.4.0 renders a real
difference with the current values (something moved since 2026-10-01): STOP and
re-plan. Second count 0 => the two renders are identical, i.e. both tarballs are
the same file: STOP.

**2.3 Baselines for §4**

```bash
kubectl get pod -n office -l app.kubernetes.io/name=nextcloud,app.kubernetes.io/component=app \
  -o jsonpath='{.items[*].metadata.uid}' > /Users/mu/db-dumps/nextcloud-9.4.0-exec/pod-uid-pre.txt
kubectl get deploy -n office nextcloud -o jsonpath='{.metadata.generation}' > /Users/mu/db-dumps/nextcloud-9.4.0-exec/gen-pre.txt
cat /Users/mu/db-dumps/nextcloud-9.4.0-exec/pod-uid-pre.txt; echo; cat /Users/mu/db-dumps/nextcloud-9.4.0-exec/gen-pre.txt; echo
helm history nextcloud -n office --max 1
```

EXPECT: exactly one UID; a generation number; history row `deployed
nextcloud-9.3.0 34.0.4` (APP VERSION is the CHART's appVersion, so it still says
34.0.4 although 35.0.1 runs — that mismatch is what this plan removes). HOW IT FAILS: zero or two
UIDs => mid-rollout: STOP.

**2.4 Mail baseline — the operator's hard gate** (instruments as re-measured in
`nextcloud-fleet-35.0.1` §2.2b; Mail app exposes no `mail:account:list`).

```bash
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ list mail" \
  | grep -cE '^ +mail:(mailbox:list|account:test) '
#   EXPECT: 2. Anything else => the gate below measures nothing: STOP.
kubectl exec -n office nextcloud-mariadb-0 -c mariadb -- sh -c \
  'mariadb -uroot -p"$(cat $MARIADB_ROOT_PASSWORD_FILE)" -N -B nextcloud -e "select account_id, count(*) from oc_mail_mailboxes group by account_id order by account_id"' \
  2>/dev/null > /Users/mu/db-dumps/nextcloud-9.4.0-exec/mail-db-pre.txt
cat /Users/mu/db-dumps/nextcloud-9.4.0-exec/mail-db-pre.txt
#   EXPECT: one line per account (3 accounts, ids 1 2 3 on 2026-09-28). Empty => STOP.
for N in $(cut -f1 /Users/mu/db-dumps/nextcloud-9.4.0-exec/mail-db-pre.txt); do
  printf '%s\t' "$N"
  kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ mail:mailbox:list $N" \
    2>/dev/null | grep -c '^| [0-9]'
done > /Users/mu/db-dumps/nextcloud-9.4.0-exec/mail-occ-pre.txt
diff /Users/mu/db-dumps/nextcloud-9.4.0-exec/mail-db-pre.txt /Users/mu/db-dumps/nextcloud-9.4.0-exec/mail-occ-pre.txt && echo MAIL-INSTRUMENT-AGREES
```

EXPECT `MAIL-INSTRUMENT-AGREES`. HOW IT FAILS: a mismatch BEFORE we touch
anything is pre-existing (likely fallout from the fleet run): STOP and resolve
under the fleet plan — never attribute it to this chart bump.

## 3) Steps

**3.1 Go/no-go.** Premises PASS, §2.1-2.4 clean.

**3.2 The edit + commit** (sed dry-tested on a scratch copy 2026-10-01, BSD sed;
resulting diff was exactly `11c11 <       version: 9.3.0 ---  >       version: 9.4.0`).

```bash
cd /Users/mu/code/cberg-home-nextgen
git fetch origin main && git merge --ff-only origin/main
sed -i '' -E 's|^      version: 9\.3\.0$|      version: 9.4.0|' kubernetes/apps/office/nextcloud/app/helmrelease.yaml
git diff -- kubernetes/apps/office/nextcloud/app/helmrelease.yaml
grep -c '^      version: 9\.4\.0$' kubernetes/apps/office/nextcloud/app/helmrelease.yaml   # EXPECT 1
grep -c '9\.3\.0' kubernetes/apps/office/nextcloud/app/helmrelease.yaml                 # EXPECT 0 (exit 1 = pass)
kubectl kustomize kubernetes/apps/office/nextcloud/app >/dev/null && echo RENDER-OK
printf '%s\n\n%s\n\nCo-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>\n' \
  "feat(nextcloud): chart 9.3.0 -> 9.4.0 (appVersion 35.0.1, lockstep with image) (plan nextcloud-9.4.0)" \
  "Chart diff is Chart.yaml appVersion only; with image.tag pinned the render differs in metadata labels only - no pod roll." \
  > /Users/mu/db-dumps/nextcloud-9.4.0-exec/msg.txt
git commit --only kubernetes/apps/office/nextcloud/app/helmrelease.yaml -F /Users/mu/db-dumps/nextcloud-9.4.0-exec/msg.txt
git show --stat HEAD && git log -1 --format=%s     # ONLY helmrelease.yaml; subject must be this one — else amend BEFORE push
git rev-parse HEAD > /Users/mu/db-dumps/nextcloud-9.4.0-exec/bump-sha.txt
git push origin main
```

The diff MUST be the single line 11 change. Anything else in `git diff` => a
foreign hunk or a moved line: STOP, do not commit.

**3.3 Wait for helm-controller** (webhook-driven; no manual reconcile unless 10 min
pass with `lastAttemptedRevision` still 9.3.0 — then `flux reconcile hr nextcloud -n office`
once, per application-update SOP).

```bash
for i in $(seq 1 20); do
  R=$(kubectl get hr -n office nextcloud -o jsonpath='{.status.lastAttemptedRevision} {.status.conditions[?(@.type=="Ready")].status}')
  echo "$R"; [ "$R" = "9.4.0 True" ] && break; sleep 30
done
```

## 4) Verification

Every gate states what its failure prints.

1. **CONTENTS ASSERTION — the release is on 9.4.0.**
   ```bash
   helm history nextcloud -n office --max 1
   kubectl get deploy -n office nextcloud -o jsonpath='{.metadata.labels.helm\.sh/chart} {.metadata.labels.app\.kubernetes\.io/version}{"\n"}'
   ```
   PASS: history row `deployed  nextcloud-9.4.0  35.0.1`; labels
   `nextcloud-9.4.0 35.0.1`. FAIL shapes: `nextcloud-9.3.0 34.0.4` (not applied —
   measured live 2026-10-01, so the gate demonstrably reads the label);
   `failed`/`pending-upgrade` in history (helm upgrade failed — §5).
2. **No pod roll (the thing this plan claims does not happen).**
   ```bash
   diff <(kubectl get pod -n office -l app.kubernetes.io/name=nextcloud,app.kubernetes.io/component=app -o jsonpath='{.items[*].metadata.uid}') \
        /Users/mu/db-dumps/nextcloud-9.4.0-exec/pod-uid-pre.txt && echo SAME-POD
   echo "gen now=$(kubectl get deploy -n office nextcloud -o jsonpath='{.metadata.generation}') pre=$(cat /Users/mu/db-dumps/nextcloud-9.4.0-exec/gen-pre.txt)"
   ```
   PASS: `SAME-POD` and equal generations (metadata label changes do not bump
   `generation`). FAIL: a diff / higher generation => the pod template changed
   after all (§1.4 premise broken) — the new pod runs the SAME 35.0.1 image so it
   is not dangerous, but verify gate 3 on the new pod and report the plan defect.
3. **App healthy, version and maintenance flag.**
   ```bash
   kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ status --output=json"
   ```
   PASS: `"version":"35.0.1.<n>"`, `"maintenance":false`, `"needsDbUpgrade":false`.
   FAIL: maintenance true => stuck-maintenance trap (fleet §5.1 recovery).
   **CONTROL: metric `nextcloud_system_info`** (label `version`; read 34.0.4.1 live
   2026-10-01) and **CONTROL: metric `nextcloud_up`** (1 live 2026-10-01):
   ```bash
   kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
   curl -s 'http://localhost:19090/api/v1/query?query=nextcloud_up' | .venv/bin/python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];print('nextcloud_up',[x['value'][1] for x in r])"
   curl -s 'http://localhost:19090/api/v1/query?query=nextcloud_system_info' | .venv/bin/python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];print('version',[x['metric'].get('version') for x in r])"
   kill $PF 2>/dev/null
   ```
   PASS: `nextcloud_up ['1']`, `version ['35.0.1.<n>']`. FAIL: `[]` => the series
   vanished (exporter or scrape broke). Not expected: ServiceMonitor
   `monitoring/nextcloud-metrics` selects only `app.kubernetes.io/{name,component}`
   (measured 2026-10-01), not the version label this plan changes. `['0']` =>
   exporter cannot reach the server.
4. **CONTENTS ASSERTION — Mail (hard gate).** Re-run the §2.4 loop into
   `mail-occ-post.txt` and diff against `mail-occ-pre.txt`; then
   ```bash
   for N in $(cut -f1 /Users/mu/db-dumps/nextcloud-9.4.0-exec/mail-db-pre.txt); do
     kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ mail:account:test $N" 2>&1 \
       | grep -ciE 'connection test passed'
   done
   ```
   PASS: no diff; one `1` per account. FAIL: `0` for an account => IMAP for that
   account broken — compare with the fleet plan's post-run mail evidence before
   blaming this bump (no pod restart happened here, gate 2).
5. **Flux floor:** `flux get hr -n office nextcloud` Ready True, revision 9.4.0;
   `kubectl get kustomization -n office nextcloud` Ready True.

Close-out: set `status: executed` in this file (separate commit, `--only`).

## 5) Rollback

Nothing forward-only happened (no pod start, no occ, no DB write), so a git
revert is the complete procedure.

```bash
cd /Users/mu/code/cberg-home-nextgen
git fetch origin main && git merge --ff-only origin/main
git revert --no-edit $(cat /Users/mu/db-dumps/nextcloud-9.4.0-exec/bump-sha.txt)
git show --stat HEAD && git log -1 --format=%s      # only helmrelease.yaml; subject "Revert ...chart 9.3.0 -> 9.4.0..."
git push origin main
```

Confirm: `kubectl get hr -n office nextcloud -o jsonpath='{.status.lastAttemptedRevision}'`
-> `9.3.0`; deployment label `helm.sh/chart` -> `nextcloud-9.3.0`; §4 gates 2-4
green. If the helm upgrade itself FAILED (history `failed`) Flux remediation
(retries 3, restored by the fleet plan) rolls back to the previous revision
automatically — which is the SAME 35.0.1 image, so that rollback is safe (unlike
during the fleet plan, where retries are 0 for exactly that reason). Then revert
the commit so git matches.

## 6) Interference notes

- **Ordering:** strictly after `nextcloud-fleet-35.0.1` (depends_on), including its
  §3.6 restore commit. May run in the same sun-attended slot right after fleet's §4
  is green — that is the closest the FOLLOW path gets to lockstep. Better still:
  fold (§1.3) and supersede this file.
- **Repo correction for the window agent / reviewer:** the fleet plan's premise
  `newest-published-chart-still-carries-a-34-appversion` now FAILS on substance
  (9.4.0 = appVersion 35.0.1, published 2026-09-30), AND its `run:` uses
  `helm show chart --repo ...`, which on 2026-10-01 errors on this Mac
  (`no cached repo found`) — so it would also fail for the wrong reason. The fleet
  plan needs its in-place refresh before its 2026-10-18 slot either way.
- Same-file / same-release plans in `conflicts_with`: `nextcloud-redis-hardening`
  (nightly 2026-10-01 — if it lands first, §2.2's render gate covers its values),
  `bitnamilegacy-exit-nextcloud-db`, `flux-oci-chart-sources`, `helm-drift-detection`;
  helm-controller/identity changes: `flux-fleet-0.60.0`,
  `flux-reconciler-impersonation`.
- No alert silence needed: no pod restarts. If gate 2 shows an unexpected roll,
  `KubeDeploymentRolloutStuck`-class alerts may fire for ~minutes; that is the
  signal, not noise.
- §4 gate 3 reads Prometheus; no open kube-prometheus-stack plan exists today
  (2026-10-01). If one appears for the same night, add it to `conflicts_with`.
- Consumers in other namespaces (ai/openclaw mail/calendar skills,
  office/nextcloud-mcp, Homepage) see nothing: no restart.
