---
plan_id: n8n-fleet-2.44.6
component: n8n
pr: 407                               # Renovate "chore(deps): update n8nio/n8n docker tag to v2.44.6",
                                      # CI green (Flate Render Gate + Flux Local Diff), MERGEABLE, 2026-10-25
kind: image
current: "2.44.5"                     # live: deployment/n8n image n8nio/n8n:2.44.5, pod imageID
                                      # sha256:bcb4e491..., `n8n --version` 2.44.5 (2026-10-25)
target: "2.44.6"                      # RE-TARGETED from the dispatched 2.45.3. 2.45.x is the BETA line:
                                      # GitHub marks every n8n@2.45.0..2.45.3 release prerelease=true,
                                      # and Docker Hub n8nio/n8n:2.45.3 == :beta == :next (sha256:bf88c378...).
                                      # 2.44.6 is GA: prerelease=false, and n8nio/n8n:2.44.6 == :latest ==
                                      # :stable (sha256:d02752c6ab446ae9db8deec2f9cc887c378f77cdcad31650814df936b7386dfb).
update_type: patch
risk: low                             # 7 commits, no DB migration files, one bug fix + a backported agents-UI
                                      # feature + Node 26.10.0 -> 26.12.1 in the runtime base. Same-minor revert
                                      # is clean. The hold on THIS target is a false positive (§1.3).
est_duration_min: 20                  # 4 pre-checks + 2 edit/commit/push + 4 reconcile/Recreate + 10 settle/verify
needs_reboot: false
touches:
  namespaces: [home-automation]
  resources:
    - helmrelease/n8n                 # the one edited line: values.image.tag
    - deployment/n8n                  # image changes -> pod template changes -> Recreate (~1-2 min down)
    - service/n8n                     # unchanged; its single endpoint is down during Recreate
    - pvc/n8n-config                  # RWO Longhorn, re-attached by the new pod; not written by a migration
    - httproute/n8n                   # not edited; its backend is absent during Recreate, so public webhooks
                                      # on envoy-external 5xx for that minute
  shared: []                          # own embedded SQLite on its own PVC; Gateways untouched; no ServiceMonitor.
                                      # §4 reads Prometheus only for kube-state-metrics series (see §6.2).
depends_on: []                        # n8n-chart-2.1.1 executed nightly 2026-10-25 (chart 2.1.1 live); see §1.4.
conflicts_with:
  - flux-oci-chart-sources            # vetted, sun-attended:2026-11-22; moves hr/n8n's chart source: two writers
                                      # on one object, and a failed boot must stay attributable to one change.
  - helm-drift-detection              # vetted, sat-attended:2026-11-07; adds a spec field to every HelmRelease
                                      # incl. helmrelease/n8n.
exclusive: false
security_ref: null                    # dispatched with no security evidence; see §1.5 for the open security
                                      # finding on the CURRENT tag (cited by id only, not claimed).
capability_change: true               # NOT "to be safe" — a fact: 2.44.6 backports
                                      # "feat(editor): Let agent owners make agents available in n8n Chat"
                                      # (#41703). It widens the n8n-Chat agent list endpoint to also return
                                      # unpublished agents in projects where the user holds agent:update +
                                      # agent:publish ("That audience may read the config"), plus a new
                                      # make-available UI. A new feature + a read-scope change. §1.2.
rollback_class: git-revert            # nothing forward-only: no migration files between 2.44.5 and 2.44.6,
                                      # so 2.44.5 boots on the 2.44.6 DB unchanged.
finding_refs:                         # queried 2026-10-25 with SWEEP_PG_DSN up (`finding list --grep n8n`)
  - F-09588936                        # "n8n: image n8nio/n8n 2.44.5 -> 2.45.3 (minor)" — the version finding this
                                      # held group was raised from. Answered by the GA patch, NOT by 2.45.3.
                                      # NOT claimed: F-8e5e5c66 (chart; owned by n8n-chart-2.1.1).
review: ready-for-go@2026-10-25   # plan-reviewer 2026-10-25 (needs-fix on bookkeeping only; fixed 5490d7fd, premises 5/5 PASS)
status: vetted
window: nightly:2026-11-05   # human-gated (capability_change): needs operator GO
premises:
  - id: chart-plan-executed
    why: >-
      Live-state guard. n8n-chart-2.1.1 executed 2026-10-25 (§1.4); the HelmRelease
      must carry chart 2.1.1. If it is anything else, re-plan rather than run.
    run: kubectl get helmrelease -n home-automation n8n -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: "2.1.1"
  - id: image-is-2.44.5
    why: "The §1.2 diff is 2.44.5 -> 2.44.6; a different start voids it (e.g. Step 0 already merged #407)."
    run: kubectl get deploy -n home-automation n8n -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: n8nio/n8n:2.44.5
  - id: git-tag-pin-2.44.5
    why: "Git side of the same premise; the §3.2 sed must hit exactly one line."
    run: "git show HEAD:kubernetes/apps/home-automation/n8n/app/helmrelease.yaml | grep -c 'tag: \"2.44.5\"'"
    expect_exact: "1"
  - id: helmrelease-ready
    why: "Do not stack an image bump on a release left Failed by the chart plan."
    run: kubectl get helmrelease -n home-automation n8n -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: strategy-still-recreate
    why: >-
      Single replica on RWO Longhorn PVC n8n-config: anything but Recreate risks a
      Multi-Attach hang on the pod-template change (docs/sops/longhorn-rwo-multi-attach.md).
      Chart 2.1.1 renders Recreate (n8n-chart-2.1.1 §1.2); this asserts the live side after it.
    run: kubectl get deploy -n home-automation n8n -o jsonpath='{.spec.strategy.type}'
    expect_exact: Recreate
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/longhorn-rwo-multi-attach.md
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/auto-update.md
generated: "2026-10-25"
---

# n8n: image 2.44.5 → 2.44.6 (GA patch; the dispatched 2.45.3 is beta)

## 1) Summary & why held

### 1.1 What changes

One line in `kubernetes/apps/home-automation/n8n/app/helmrelease.yaml`:
`values.image.tag: "2.44.5" → "2.44.6"`. This is the same change as Renovate
PR #407. No chart, values, env, PVC or route change.

### 1.2 Why the target is 2.44.6 and not 2.45.3 (primary sources, 2026-10-25)

The sweep dispatched this group as `2.44.5 → 2.45.3`. That target is a
pre-release, so this plan does not use it:

| Source | 2.45.x | 2.44.6 |
|---|---|---|
| GitHub releases `n8n-io/n8n` | `n8n@2.45.0`, `2.45.1`, `2.45.2`, `2.45.3`: all `prerelease: true`; the `beta` release is also `prerelease: true` | `n8n@2.44.6`: `prerelease: false`; the `stable` release is `prerelease: false` |
| Docker Hub digests | `2.45.3` = `beta` = `next` = `sha256:bf88c378…` | `2.44.6` = `latest` = `stable` = `sha256:d02752c6…` |

The 2.45.x line is n8n's beta channel. This is the hazard the deny rule
`*n8nio/n8n*` (`max: patch`) exists for. **2.45.3 must not be planned until
upstream moves `stable` onto 2.45.x.** When that happens it becomes a normal
minor-version plan. It also needs its migration review, because 2.45 is a new
minor.

What 2.44.6 contains: `compare n8n@2.44.5...n8n@2.44.6` has 7 commits.
- `fix(Postgres Node): Prevent global pgtypes overwrite (#41667)`. This is the
  only CHANGELOG entry, and it is irrelevant here because n8n runs on SQLite.
  It only affects workflows that use the Postgres node.
- `feat(editor): Let agent owners make agents available in n8n Chat (no-changelog)
  (#41703)`. This is backported. `AgentsService.findChatReachableByUserPaginated`
  now also lists agents in projects where the user holds `agent:update` +
  `agent:publish`, whether or not they are published to n8n Chat. A
  make-available modal is added in editor-ui. The list returns
  `{count:0}` when the agents setting is disabled. Whether this instance has it
  enabled could not be read without auth (`/rest/module-settings` → 401). This
  change is why `capability_change: true`.
- `ci: Bump base image node versions` / `Bump node pc image versions`. The
  runtime Node moves from **26.10.0 to 26.12.1** (`docker/images/n8n/Dockerfile`
  `ARG NODE_VERSION`). The DHI base moves from 24.21.0 to 24.22.1. Live today:
  `node --version` → `v26.10.0`.
- Three CI-only commits and the release commit.
- **No file under `packages/@n8n/db/src/migrations`** is in the diff. Only
  `packages/@n8n/db/package.json` changes, as a version bump. Nothing forward-only
  happens, so the plan is `rollback_class: git-revert`.

### 1.3 Why held, and why the hold on 2.44.6 is a false positive

Two separate gates are involved. Neither gate is about 2.44.6's content:

1. **coverage.py** reads the newest tag (2.45.3, a minor) and puts the group
   in the PLAN lane under the beta-channel reason. That is correct for 2.45.3.
2. **auto-update.py** would take PR #407 at Step 0, because it is a patch,
   `max: patch` admits it and CI is green. It did not, and the cause is the
   title parser. Dry-run on 2026-10-25:
   `⏸️  #407 ? → [?] — title not in "update <dep> ( x → y )" nor "update <dep> to <x.y.z>" shape`.
   The Renovate title `update n8nio/n8n docker tag to v2.44.6` has `docker tag`
   between the dep and `to`, and the version starts with `v`. **Repo
   correction (reported, not fixed here):** the parser should accept
   Renovate's `update <dep> docker tag to v<x.y.z>` form. #430 fails the same
   way today. Until that is fixed, any GA n8n patch PR in this title shape
   stalls with no plan.

So for 2.44.6 itself, the risk is that of a normal stable patch. It is
planned rather than waved through because of the ordering constraint in §1.4
and the capability fact in §1.2.

### 1.4 Ordering: the chart plan is done

`n8n-chart-2.1.1` executed in the nightly of 2026-10-25 (chart 2.0.1 → 2.1.1,
V1-V7 green) and its plan is retired, so it is no longer in `depends_on` or
`conflicts_with`. The live premise `chart-plan-executed` still checks that the
HelmRelease carries chart 2.1.1. This image bump is a separate, later restart,
so a failed boot is attributable to the image alone. It cannot share the
chart's window because that window has already run; the earliest slot is any
later window.

### 1.5 Security note (citation only)

An open security finding, **F-d8bf68df**, exists against the *current* tag
2.44.5. Its detail is on the finding record. This plan does NOT claim it,
because nobody has measured whether 2.44.6 resolves it. The Node runtime bump
makes that plausible, but plausible is not measured. After execution, the
sweep's next security pass re-reads the image. If it clears, close the finding
against the §3 commit.

## 2) Pre-checks

Run all premises first (`plan-premises.py n8n-fleet-2.44.6`). Then:

```bash
# 2.0 Channel gate (auto-update-policy `*n8nio/n8n*`): Docker Hub `stable` must still be 2.44.6.
# Moved here from the premises because plan-premises.py refuses curl, `;` and quoted pipes.
S=$(curl -s https://hub.docker.com/v2/repositories/n8nio/n8n/tags/stable | python3 -c "import sys,json; print(json.load(sys.stdin)['digest'])")
T=$(curl -s https://hub.docker.com/v2/repositories/n8nio/n8n/tags/2.44.6 | python3 -c "import sys,json; print(json.load(sys.stdin)['digest'])")
echo "stable=$S"; echo "2.44.6=$T"
[ "$S" = "sha256:d02752c6ab446ae9db8deec2f9cc887c378f77cdcad31650814df936b7386dfb" ] && [ "$S" = "$T" ] && echo PASS || echo FAIL
```
PASS: prints `PASS` (verified 2026-10-25: both digests equal
`sha256:d02752c6ab446ae9db8deec2f9cc887c378f77cdcad31650814df936b7386dfb`).
FAIL prints `FAIL`, and also fires on an empty fetch (an empty `$S` matches
nothing), so a dead registry cannot pass. FAIL means upstream moved `stable`:
STOP and re-target.

```bash
cd /Users/mu/code/cberg-home-nextgen
# 2.1 Flux healthy for this app, no in-flight reconcile
flux get helmreleases -n home-automation n8n
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
```
PASS: the n8n HR is `True` and no kustomization is non-Ready in the path. A
non-Ready `home-automation` or `flux-system` kustomization means STOP.

```bash
# 2.2 Backup fresh (safety net only; rollback does not need it, §5)
kubectl get volumes.longhorn.io n8n-config -n storage -o jsonpath='{.status.lastBackupAt}{"\n"}'
kubectl get cronjob -n storage daily-backup-all-volumes -o jsonpath='{.status.lastSuccessfulTime}{"\n"}'
```
PASS: `lastBackupAt` is within 26 h. On 2026-10-25 it read `2026-10-24T23:06:53Z`.
If it is empty or older, run no upgrade, because the net is gone. `lastBackupAt`
can lag one cycle; if it looks stale, cross-check the newest Completed Backup CR
(`docs/sops/backup.md`).

```bash
# 2.3 CONTENTS baseline — record both values
kubectl exec -n home-automation deploy/n8n -- sh -c "n8n list:workflow --onlyId 2>/dev/null | grep -E '^[A-Za-z0-9]{16}\$' | wc -l"
kubectl exec -n home-automation deploy/n8n -- sh -c "n8n list:workflow --active=true --onlyId 2>/dev/null | grep -E '^[A-Za-z0-9]{16}\$' | sort | cksum"
kubectl exec -n home-automation deploy/n8n -- node --version
```
Measured 2026-10-25: `15` workflows, active cksum `3124227881 136`, node
`v26.10.0`. Re-measure at window time, because workflows change. A `0` count
means the filter matched nothing; that is a broken baseline, so STOP.

## 3) Steps

```bash
cd /Users/mu/code/cberg-home-nextgen
# 3.1 sync
git fetch origin main && git merge --ff-only origin/main

# 3.2 edit (dry-tested on a scratch copy with BSD sed, 2026-10-25; resulting diff:
#        31c31  <       tag: "2.44.5"  --->       tag: "2.44.6")
sed -i '' 's/^\([[:space:]]*tag: \)"2\.44\.5"$/\1"2.44.6"/' kubernetes/apps/home-automation/n8n/app/helmrelease.yaml
git diff --stat kubernetes/apps/home-automation/n8n/app/helmrelease.yaml   # 1 file, 1 insertion, 1 deletion
grep -c 'tag: "2.44.6"' kubernetes/apps/home-automation/n8n/app/helmrelease.yaml   # 1

# 3.3 commit ONLY this path (shared worktree), verify, push
MSG=$(mktemp -t n8n-msg)
printf 'fix(container): update n8nio/n8n ( 2.44.5 → 2.44.6 ) (plan n8n-fleet-2.44.6, supersedes #407)\n\nGA stable patch; 2.45.x is the beta channel and stays held.\n\nCo-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>\n' > "$MSG"
git commit --only kubernetes/apps/home-automation/n8n/app/helmrelease.yaml -F "$MSG"
git log -1 --format=%s          # must be the subject above; amend before push if not
git show --stat HEAD            # exactly 1 file
git push origin main
```
Flux picks this up through the webhook. Do not run a manual `flux reconcile`.
Renovate closes #407 by itself once `main` carries 2.44.6. If #407 is still
open after one Renovate cycle, close it by hand and do NOT merge it.

```bash
# 3.4 wait for the Recreate (expect ~1-2 min with no pod, then one new pod); bounded, then V2
kubectl rollout status deploy/n8n -n home-automation --timeout=300s
```
PASS: prints `successfully rolled out`. A timeout (non-zero exit) with the new
pod in `ContainerCreating` and a `Multi-Attach` event means the strategy premise
was wrong: go to §5. Rollout status can green-light the old generation, so
continue to V2 (pod digest) before trusting it.

## 4) Verification

CONTROL: metric kube_pod_container_info — the gate reads its `image` label for `namespace="home-automation",container="n8n"`. Exactly 1 series with `docker.io/n8nio/n8n:2.44.6` is required. This was verified live on 2026-10-25: 1 series, image `…:2.44.5`. The negative control `container="n8n-nonexistent"` returned 0 series, so an empty result is detectable and is a FAIL.
CONTROL: metric kube_pod_container_status_restarts_total — `namespace="home-automation",container="n8n"` must read `0` after the 10-minute settle. Verified as present live on 2026-10-25 (value 0).
CONTENTS ASSERTION: the workflow inventory survives the image swap. Measured by the two `n8n list:workflow` lines in V5, compared to the §2.3 baseline. Both must be identical, and a count of `0` is a FAIL.

```bash
# V1 spec
kubectl get deploy -n home-automation n8n -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
```
PASS: `n8nio/n8n:2.44.6`. `2.44.5` means Flux has not applied the commit; check
`flux get hr -n home-automation n8n`.

```bash
# V2 the RUNNING pod's digest (rollout status can green-light the old generation)
kubectl get pods -n home-automation -l app.kubernetes.io/name=n8n -o jsonpath='{range .items[*]}{.metadata.name} {.status.containerStatuses[0].imageID}{"\n"}{end}'
```
PASS: exactly one pod, with imageID ending
`sha256:d02752c6ab446ae9db8deec2f9cc887c378f77cdcad31650814df936b7386dfb`.
The old pod shows `sha256:bcb4e491…`. Seeing `bf88c378…` means the BETA image
was pulled; roll back at once.

```bash
# V3 the binary and runtime inside
kubectl exec -n home-automation deploy/n8n -- n8n --version
kubectl exec -n home-automation deploy/n8n -- node --version
```
PASS: `2.44.6` and `v26.12.1`. Seeing `2.44.5`/`v26.10.0` means the old pod is
still serving.

```bash
# V4 serving: liveness + DB-migrated readiness
kubectl port-forward -n home-automation svc/n8n 15678:5678 >/dev/null 2>&1 & PF=$!; sleep 4
curl -s -o /dev/null -w 'healthz=%{http_code}\n'   http://localhost:15678/healthz
curl -s -o /dev/null -w 'readiness=%{http_code}\n' http://localhost:15678/healthz/readiness
kill $PF 2>/dev/null
```
PASS: both are `200`; this read `readiness=200` live on 2026-10-25. A `503` on
readiness means the process is up but the DB is not connected or initialised.
A `000` means nothing is listening, or the forward died with the pod; set it up
again.

```bash
# V5 CONTENTS — same inventory as §2.3
kubectl exec -n home-automation deploy/n8n -- sh -c "n8n list:workflow --onlyId 2>/dev/null | grep -E '^[A-Za-z0-9]{16}\$' | wc -l"
kubectl exec -n home-automation deploy/n8n -- sh -c "n8n list:workflow --active=true --onlyId 2>/dev/null | grep -E '^[A-Za-z0-9]{16}\$' | sort | cksum"
```
PASS: both values equal §2.3. A different active cksum means a workflow was
deactivated on boot. `0` is a FAIL, never a pass.

```bash
# V6 Prometheus (kube-state-metrics) after a 10 min settle
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 4
curl -s --data-urlencode 'query=kube_pod_container_info{namespace="home-automation",container="n8n"}' http://localhost:19090/api/v1/query \
  | python3 -c "import sys,json; r=json.load(sys.stdin)['data']['result']; print(len(r), [x['metric'].get('image') for x in r])"
curl -s --data-urlencode 'query=kube_pod_container_status_restarts_total{namespace="home-automation",container="n8n"}' http://localhost:19090/api/v1/query \
  | python3 -c "import sys,json; r=json.load(sys.stdin)['data']['result']; print(len(r), [x['value'][1] for x in r])"
kill $PF 2>/dev/null
```
PASS: the first line prints `1 ['docker.io/n8nio/n8n:2.44.6']` and the second
prints `1 ['0']`. A result of `0 []` means no data, which is a FAIL and not a
pass; check kube-state-metrics before concluding anything.

## 5) Rollback

Nothing forward-only: there are no migration files between 2.44.5 and 2.44.6
(§1.2), and the image is the only change.

```bash
cd /Users/mu/code/cberg-home-nextgen
git fetch origin main && git merge --ff-only origin/main
git revert --no-edit <sha-of-§3.3>
git log -1 --format=%s && git show --stat HEAD   # 'Revert "fix(container): update n8nio/n8n ( 2.44.5 → 2.44.6 )…', 1 file
git push origin main
```
Confirm the cluster is back:
- V1 prints `n8nio/n8n:2.44.5`, and V2 shows imageID `sha256:bcb4e4917141f4a5249c8eadf2776d347f4c2ede75adfbbc82064826af9a8ead`.
- V3 prints `2.44.5` / `v26.10.0`.
- V4 is `200`/`200`, and V5 equals §2.3.
- Leave PR #407 closed. Renovate re-opens a PR for the next stable patch.

**If V5 fails after rollback as well** (inventory lost, not an image problem):
this is no longer an image rollback. Scale `deploy/n8n` to 0 through git
(`main.replicaCount: 0`) and restore `n8n-config` from the newest Longhorn
backup checked in §2.2, following `docs/sops/backup.md` (restore to a new
volume, then repoint per `docs/sops/longhorn.md`). That is an attended
operator action. Do not improvise it in a nightly window.

## 6) Interference notes

### 6.1 Ordering and windows
- `n8n-chart-2.1.1` has already executed (§1.4), so there is no ordering
  constraint left. Any window is eligible once the operator GO is recorded.
  Keep it out of the `sat-attended:2026-11-07` and `sun-attended:2026-11-22`
  windows, which carry the two conflicting plans.
- `capability_change: true` (§1.2), so the execution class derived by
  `autonomy-policy.yaml` is human-gated, not SD-10. The operator GO is
  expected to be quick: risk is low, the restart is about 2 min, and the
  revert is one commit. If a reviewer can show that the agents/n8n-Chat
  module is disabled on this instance, making the feature inert, that is a
  reason to re-declare `false` *with that evidence*. It is not a reason to
  change it unproven.
- The window agent assigns `window:`.

### 6.2 Shared surfaces
- None perturbed. The public edge (`envoy-external`) is only *read through*:
  n8n webhooks return 5xx for the ~1-2 min Recreate. Callers that retry, such
  as Telegram, recover. Fire-and-forget webhook senders lose that minute.
- V6 reads Prometheus, but only kube-state-metrics series. A same-night
  kube-prometheus-stack bump would not add a conflict entry, because no
  kube-prometheus-stack *plan* exists today. The open KPS PRs #427/#428 are
  Step 0 safe updates. Step 0 health-gates and settles them BEFORE plans run,
  so they cannot change the instrument mid-gate. If a KPS plan is ever
  written for the same night, add it to `conflicts_with` on both sides.

### 6.3 Other plans that touch hr/n8n
- `n8n-chart-2.1.1` is `executed` and not referenced on purpose, so its
  file does not leave a DEAD-REF here.
- `flux-oci-chart-sources` (vetted, `sun-attended:2026-11-22`) and
  `helm-drift-detection` (vetted, `sat-attended:2026-11-07`) both write
  hr/n8n and are listed in `conflicts_with`.
- `flux-reconciler-impersonation` is `exclusive: true` and `blocked`, so it
  needs no entry here.
- `n8n-2.39.8` is `executed`. It is not referenced on purpose, so its eventual
  retirement does not leave a DEAD-REF.

### 6.4 Repo corrections (reported, not fixed here)
1. `auto-update.py`'s Renovate title parser rejects `update <dep> docker tag to
   v<x.y.z>` (#407, #430). As a result, GA stable patches of a denied-to-patch
   image never reach Step 0.
2. When the newest tag is pre-release, coverage.py reports the group's target
   as that newest tag (2.45.3, beta). It does not report the newest GA tag
   (2.44.6). The beta-channel hold is correct, but the dispatched target should
   then be the GA tag. Otherwise every dispatch for this group starts at the
   wrong version.
