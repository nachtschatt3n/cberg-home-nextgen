---
plan_id: paperclip-backup-cleanup-busybox-pin
component: paperclip-backup-cleanup   # the raw CronJob ai/paperclip-backup-cleanup (NOT the paperclip
                                      # HelmRelease; its wait-for-postgres init already runs busybox 1.38.0)
pr: null                              # no Renovate PR: a floating `stable` tag is exactly what Renovate
                                      # cannot see. Surfaced by the version check (finding_refs below).
kind: image
current: "busybox:stable@sha256:73aaf090f3d85aa34ee199857f03fa3a95c8ede2ffd4cc2cdb5b94e566b11662 (== busybox:1.36.1 index digest)"
target: "busybox:1.38.0@sha256:fd7dc98638c8e305f4dc34e979f1c0fdfdcaeb0fbf8fcff77ae834b6da3d7e6e"
update_type: minor                    # 1.36.1 -> 1.38.0, plus floating tag -> explicit version tag
risk: low                             # one daily CronJob that only deletes *.sql files older than 7 days;
                                      # no Deployment, Service or route changes; same uid/PVC/command
est_duration_min: 20                  # pre-checks 4 + edit/commit/push 3 + Flux apply 3 + manual verify
                                      # Job + contents gates 6 + slack 4
needs_reboot: false
touches:
  namespaces: [ai]
  resources:
    - cronjob/paperclip-backup-cleanup        # jobTemplate image line only
    - "job/paperclip-backup-cleanup-verify-<ts> (ai)"   # optional manual verification Job (§4.2), ttl 24h
    - pvc/paperclip-data                      # mounted RWO alongside the running app via podAffinity;
                                              # the Job deletes *.sql backups older than 7 days (same
                                              # policy as every night, see §1)
    - kubernetes/apps/ai/paperclip/app/backup-cleanup.yaml
  shared: []                                  # no gateway/envoy, no shared DB, no storage-engine change.
                                              # Reconciled by kustomize-controller like every app; the
                                              # Prometheus read in §4 is covered by conflicts_with.
depends_on: []
conflicts_with:
  - flux-fleet-0.60.0                 # 2026-10-05 review: Flux controller roll (named for completeness)
  - cli-tool-pins                     # 2026-10-05 review: its kustomize render-hash gate covers paperclip/app
  - paperclip-26.04                   # Recreates deploy/paperclip; the cleanup Job's required podAffinity
                                      # targets that pod, so a same-slot run leaves the verify Job Pending
                                      # and both plans' gates unattributable (same ns, same PVC).
  - flux-distribution-2.9.6           # rolls kustomize-controller, which applies this commit and its revert.
  - flux-reconciler-impersonation     # exclusive; changes the identity that applies ai/.
  - kube-prometheus-stack-91.9.0      # §4 CONTROL lines read Prometheus (kube-state-metrics series).
exclusive: false
security_ref: null                    # currency/drift-visibility driver, no security finding.
capability_change: false              # same job, same command, same uid, same retention rule; only the
                                      # busybox build that executes it changes
rollback_class: git-revert            # nothing forward-only: the image line is the whole change; files
                                      # the Job deletes are exactly the ones the nightly run deletes anyway
finding_refs: [F-d818430e, F-22ea15c4]  # version findings: busybox stable -> 1.38.0 (floating tag)
premises:
  - id: repo-pin-is-stable-digest
    why: "Step 3.1's python edit anchors on this exact line; zero or two matches means the file moved under the plan."
    run: >-
      grep -c 'image: busybox:stable@sha256:73aaf090f3d85aa34ee199857f03fa3a95c8ede2ffd4cc2cdb5b94e566b11662' kubernetes/apps/ai/paperclip/app/backup-cleanup.yaml
    expect_exact: "1"
  - id: live-cronjob-on-stable-digest
    why: "current: claims the live CronJob still runs the 1.36.1-equivalent stable digest. If it already moved, the plan is stale."
    run: kubectl get cronjob -n ai paperclip-backup-cleanup -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].image}'
    expect_exact: "busybox:stable@sha256:73aaf090f3d85aa34ee199857f03fa3a95c8ede2ffd4cc2cdb5b94e566b11662"
  - id: cronjob-not-suspended
    why: "The next-morning gate (4.4) relies on the 04:00Z scheduled run happening."
    run: kubectl get cronjob -n ai paperclip-backup-cleanup -o jsonpath='{.spec.suspend}'
    expect_exact: "false"
  - id: paperclip-pod-ready
    why: "The Job has REQUIRED podAffinity to the paperclip pod (RWO PVC co-mount); with no ready paperclip pod the verify Job cannot schedule."
    run: kubectl get deploy -n ai paperclip -o jsonpath='{.status.readyReplicas}'
    expect_exact: "1"
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/longhorn-rwo-multi-attach.md
  - docs/sops/storage-safety.md
review: ready-for-go@2026-10-05   # plan-reviewer 2026-10-05: ready-for-go, 0 blocking; nonblocking timing-guard + conflicts applied by coordinator
status: vetted
window: "nightly:2026-10-10"   # scheduled 2026-10-05: AUTO-NIGHT (image graduated); with the blackbox chart patch (25+20 = 45 of 70); 01:30Z exercises the delete path (PRE_OLD=1)
generated: "2026-10-05"
---

# paperclip-backup-cleanup: busybox `stable` -> `1.38.0` (digest-pinned)

## 1. Summary & why held

`kubernetes/apps/ai/paperclip/app/backup-cleanup.yaml` runs the daily (04:00Z)
`paperclip-backup-cleanup` CronJob on `busybox:stable@sha256:73aaf090...`. It was
digest-pinned on 2026-08-18 under the float-tag policy, but the TAG is still the
floating `stable`, so the version check cannot attribute it to a release and
reports it as behind (`F-d818430e`, `F-22ea15c4`). This plan replaces it with an
explicit version tag plus digest.

**Tag/digest evidence (measured 2026-10-05, Docker Hub API + registry `HEAD` with
an OCI index Accept header):**

| tag | index digest | last pushed |
|---|---|---|
| `stable` | `sha256:73aaf090f3d8...` (identical to the current pin) | 2026-03-24 |
| `1.36.1` | `sha256:73aaf090f3d8...` (so `stable` == 1.36.1 today) | 2026-03-24 |
| `1.38.0` | `sha256:fd7dc98638c8e305f4dc34e979f1c0fdfdcaeb0fbf8fcff77ae834b6da3d7e6e` | 2026-09-23 |
| `latest` | `sha256:fd7dc98638c8...` (== 1.38.0) | 2026-09-23 |

**Why this digest and not `dc2d74b...`:** the 38 busybox 1.38 containers running
in the cluster today (including paperclip's own `wait-for-postgres` init, and the
two existing `1.38.0@sha256:dc2d74b...` pins in anythingllm and edot-collector)
run the EARLIER push of the 1.38.0 tag (index `sha256:dc2d74b28e4c...`). Upstream
re-pushed the tag on 2026-09-23. I pulled the linux/amd64 layer of both pushes and
compared them: `/bin/busybox` is **byte-identical** (same sha256, same
`BusyBox v1.38.0 (2026-05-13 02:21:49 UTC)` banner, same 426 files). Only the
packaging changed. So this plan pins what the tag resolves to TODAY, and the
binary is the exact one already proven in-cluster. The two older `dc2d74b` pins
elsewhere are digest drift on a different component. They are not touched here.

**Why held / why not auto-safe:** a floating tag has no Renovate PR, and the
coverage lane cannot bump a `stable` tag. The change itself is small. If the hold
was a false positive, it was only because the tag is unversioned. `risk: low`.

**Command compatibility (the only behavioural risk):** the Job runs
`/bin/sh -c` with `[ -d ]`, `find DIR -maxdepth 1 -name '*.sql' [-mtime +7 -print
-delete]`, `wc -l` and `$(( ))` arithmetic. Checked against the 1.38.0 binary (the
same binary hash as the new digest) by running `busybox find --help` read-only in
a live `kmsg-heartbeat` pod on `busybox@sha256:dc2d74b...`. The output lists
`-maxdepth N`, `-name PATTERN`, `-mtime DAYS`, `-print` and `-delete`, and `wc`
is present. The image also ships `sh`, `find` and `wc` as applet links in
`/bin`.

**What the Job deletes:** `.sql` files in
`/paperclip/instances/default/data/backups` with `-mtime +7` (8 days old or
more). Paperclip writes these backups itself (in-app, about 04:00Z daily). Measured
2026-10-05 ~10:15Z: 8 `.sql` files, 1 of them `-mtime +7`. This morning's run
logged `backups: 8 -> 8 (removed 0 older than 7 days)`, because that file crossed
8 days after 04:00Z.

## 2. Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen
.venv/bin/python3 runbooks/plan-premises.py paperclip-backup-cleanup-busybox-pin   # all PASS, or STOP
flux get kustomizations -n ai --no-header | awk '$1=="paperclip"'                  # Ready True
kubectl get cronjob -n ai paperclip-backup-cleanup -o jsonpath='{.status.lastSuccessfulTime}{"\n"}'   # today 04:00Z-ish
# Do NOT run inside 03:50-04:20Z (the scheduled 04:00Z cleanup run) NOR within +-20 min of paperclip's
# in-app backup, whose timer is relative to POD START (measured 08:56Z daily on 2026-10-05; it moves on
# every pod restart) -- live guard: newest *.sql mtime + 24h must be > 20 min away (review 2026-10-05).
# A +1 total in 4.3 means a backup landed: re-baseline, it is not a failure.
date -u +%H:%M
kubectl exec -n ai deploy/paperclip -c app -- sh -c 'find /paperclip/instances/default/data/backups -maxdepth 1 -name "*.sql" -printf "%TY-%Tm-%Td %TH:%TM\n" | sort | tail -1'   # newest backup (GNU find in the app container)
# Baseline for 4.3 (counts only, no file names needed):
kubectl exec -n ai deploy/paperclip -c app -- sh -c 'D=/paperclip/instances/default/data/backups; echo total=$(find $D -maxdepth 1 -name "*.sql" | wc -l) old=$(find $D -maxdepth 1 -name "*.sql" -mtime +7 | wc -l)'
# record PRE_TOTAL / PRE_OLD. STOP if total=0: the floor gate in 4.3 would then be untestable.
```

Storage note: `paperclip-data` is a Longhorn RWO PVC (`longhorn` class, not CIFS).
This plan deletes no PVC. The storage-safety rules are cited because the Job
deletes files on it, and that is unchanged nightly behaviour.

## 3. Steps

3.1 Edit the one image line. The python anchors on the full line and asserts
exactly one match. Dry-tested on a scratch copy on 2026-10-05; `kubeconform` on
the result: `Valid: 1`.

```bash
cd /Users/mu/code/cberg-home-nextgen
F=kubernetes/apps/ai/paperclip/app/backup-cleanup.yaml python3 - <<'EOF'
import os, re
p = os.environ["F"]
s = open(p).read()
old = re.compile(r'^(\s+image: )busybox:stable@sha256:73aaf090f3d85aa34ee199857f03fa3a95c8ede2ffd4cc2cdb5b94e566b11662  # .*$', re.M)
assert len(old.findall(s)) == 1, "anchor count != 1 -- file moved under the plan, STOP"
s = old.sub(r'\1busybox:1.38.0@sha256:fd7dc98638c8e305f4dc34e979f1c0fdfdcaeb0fbf8fcff77ae834b6da3d7e6e  # 1.38.0 multi-arch index digest, verified 2026-10-05 (Hub API + registry HEAD); was busybox:stable (== 1.36.1)', s)
open(p, "w").write(s)
print("edited")
EOF
git diff kubernetes/apps/ai/paperclip/app/backup-cleanup.yaml
```

Expected diff (from the dry-run):

```
<               image: busybox:stable@sha256:73aaf090f3d85aa34ee199857f03fa3a95c8ede2ffd4cc2cdb5b94e566b11662  # digest-pinned 2026-08-18 (float-tag policy); == busybox:1.36.1 already cached on the nodes; re-pin deliberately
>               image: busybox:1.38.0@sha256:fd7dc98638c8e305f4dc34e979f1c0fdfdcaeb0fbf8fcff77ae834b6da3d7e6e  # 1.38.0 multi-arch index digest, verified 2026-10-05 (Hub API + registry HEAD); was busybox:stable (== 1.36.1)
```

3.2 Validate, commit only this path, verify the subject, and push.

```bash
kubeconform -summary -ignore-missing-schemas kubernetes/apps/ai/paperclip/app/backup-cleanup.yaml   # Valid: 1
printf 'fix(paperclip): pin backup-cleanup busybox stable -> 1.38.0@digest\n\nplan: paperclip-backup-cleanup-busybox-pin\n' > /tmp/msg-bb.txt
git commit --only kubernetes/apps/ai/paperclip/app/backup-cleanup.yaml -F /tmp/msg-bb.txt
git log -1 --format=%s        # must be YOUR subject (shared-worktree message-swap race); amend before push if not
git show --stat HEAD          # exactly one file
git push
```

3.3 Wait for the Flux webhook to apply it. Do not run `flux reconcile`.

```bash
SHA=$(git rev-parse HEAD)
for i in $(seq 1 30); do r=$(kubectl get ks -n ai paperclip -o jsonpath='{.status.lastAppliedRevision}'); case "$r" in *"$SHA"*) echo applied; break;; esac; sleep 10; done
```

## 4. Verification

4.1 **CronJob spec carries the new pin.**
```bash
kubectl get cronjob -n ai paperclip-backup-cleanup -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].image}{"\n"}'
```
PASS: exactly `busybox:1.38.0@sha256:fd7dc98638c8e305f4dc34e979f1c0fdfdcaeb0fbf8fcff77ae834b6da3d7e6e`.
FAIL looks like the old `stable@...` string, which means Flux did not apply. Check
`flux get ks -n ai paperclip` before continuing.

4.2 **Run the job once now (manual Job from the CronJob).** This is a real
mutation, so the window agent delegates it to cberg-agent. It is safe and
policy-neutral. The Job deletes exactly the files the next 04:00Z run would
delete (`*.sql` with `-mtime +7`) and nothing else. It needs no API access
(`automountServiceAccountToken: false`). Flux does not prune it: it carries no
kustomize labels. `ttlSecondsAfterFinished: 86400` removes it. Do not run it in
03:50-04:20Z.
```bash
J=paperclip-backup-cleanup-verify-$(date -u +%Y%m%d%H%M)
kubectl create job -n ai --from=cronjob/paperclip-backup-cleanup "$J"
kubectl wait -n ai --for=condition=complete "job/$J" --timeout=180s; echo rc=$?
P=$(kubectl get pods -n ai -l job-name="$J" -o jsonpath='{.items[0].metadata.name}')
kubectl get pod -n ai "$P" -o jsonpath='{.status.containerStatuses[0].imageID}{"\n"}'
kubectl logs -n ai "$P"
```
PASS: `rc=0`. The imageID contains `sha256:fd7dc98638c8e305f4dc34e979f1c0fdfdcaeb0fbf8fcff77ae834b6da3d7e6e`.
The log's last line matches `^backups: [0-9]+ -> [0-9]+ \(removed [0-9]+ older than 7 days\)$`.
FAIL modes and what they print:
- A missing applet or option makes `sh` print `find: unrecognized: -delete` or
  `sh: wc: not found`. The `|| true` swallows a failed `find -delete`, so the exit
  code alone cannot catch this. That is why 4.3 counts files instead of trusting
  `rc`.
- `Pending` / `wait` timeout means podAffinity found no paperclip pod. That is a
  §6 interference (paperclip Recreate in flight), not an image fault.
- `ImagePullBackOff` means a wrong digest. Roll back (§5).

4.3 CONTENTS ASSERTION: deletion still works, and only on old files. Measured by
the same `find` counts as §2, compared to `PRE_TOTAL`/`PRE_OLD`.
```bash
kubectl exec -n ai deploy/paperclip -c app -- sh -c 'D=/paperclip/instances/default/data/backups; echo total=$(find $D -maxdepth 1 -name "*.sql" | wc -l) old=$(find $D -maxdepth 1 -name "*.sql" -mtime +7 | wc -l)'
```
PASS needs all of the following:
- `old=0`.
- `total == PRE_TOTAL - PRE_OLD`, and the log's `removed` count equals `PRE_OLD`.
- A floor: `total >= 1`.

FAIL modes:
- `old>0` means `-delete` silently did nothing. This is the `|| true` case above.
- `total < PRE_TOTAL - PRE_OLD`, or `total=0`, means the age filter matched too
  much (a `-mtime` semantics regression). STOP, roll back, and check the Longhorn
  backups of `paperclip-data` before the next 04:00Z run.

If `PRE_OLD` was 0, this run does not exercise the delete path. The positive test
then moves to 4.4.

4.4 **Next-morning gate (the scheduled run on the new image).** The window agent
or the next sweep checks this after 04:00Z the following day:
```bash
kubectl get cronjob -n ai paperclip-backup-cleanup -o jsonpath='{.status.lastSuccessfulTime}{"\n"}'   # the morning after the push
JS=$(kubectl get jobs -n ai -o json | python3 -c "import sys,json;j=[x for x in json.load(sys.stdin)['items'] if x['metadata']['name'].startswith('paperclip-backup-cleanup-') and '-verify-' not in x['metadata']['name']];j.sort(key=lambda x:x['metadata']['creationTimestamp']);print(j[-1]['metadata']['name'] if j else 'NONE')")
kubectl get pods -n ai -l job-name="$JS" -o jsonpath='{.items[0].status.containerStatuses[0].imageID}{"\n"}'   # must contain fd7dc986...
kubectl logs -n ai -l job-name="$JS" | grep -i '^backups:'                                                      # the run's count line
```
PASS: `lastSuccessfulTime` is newer than the push, and the newest scheduled Job's
pod imageID is the new digest. If `PRE_OLD` was 0, the 4.3 counts must also hold
after that run (`old=0`, `total>=1`).

CONTROL: metric kube_job_status_succeeded — `kube_job_status_succeeded{namespace="ai",job_name=~"paperclip-backup-cleanup-verify-.*"} == 1` after 4.2 (empty result = the series was never scraped → FAIL, not pass).
CONTROL: metric kube_cronjob_status_last_successful_time — `{namespace="ai",cronjob="paperclip-backup-cleanup"}` must advance past the push time at the next 04:00Z run (4.4). Live series confirmed 2026-10-05 (value = 2026-10-05T04:00:11Z).
CONTROL: alertname KubeJobFailed — must NOT be firing for `namespace="ai"`, `job_name=~"paperclip-backup-cleanup.*"` after 4.2 and after 4.4.

```bash
pq(){ kubectl get --raw "/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=$1" | python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];print(len(r),[x['value'][1] for x in r])"; }
pq 'kube_job_status_succeeded%7Bnamespace%3D%22ai%22%2Cjob_name%3D~%22paperclip-backup-cleanup-verify-.%2A%22%7D'   # "1 ['1']"; "0 []" = FAIL
pq 'ALERTS%7Balertname%3D%22KubeJobFailed%22%2Cnamespace%3D%22ai%22%7D'                                              # "0 []"
```

## 5. Rollback

The image line is the whole change, and nothing is forward-only.
```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <sha-from-3.2>
git log -1 --format=%s     # confirm it is your revert subject
git push
# wait for ks ai/paperclip lastAppliedRevision == new HEAD (3.3 loop), then:
kubectl get cronjob -n ai paperclip-backup-cleanup -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].image}{"\n"}'
# == busybox:stable@sha256:73aaf090f3d85aa34ee199857f03fa3a95c8ede2ffd4cc2cdb5b94e566b11662
kubectl delete job -n ai "$J" --ignore-not-found     # optional; ttl removes it within 24h anyway
```
Files the verify Job deleted are not restored by a revert. By construction they
are the ones the next scheduled run would have deleted within 24h. If 4.3 showed
over-deletion (`total` below the expected value), use the daily Longhorn backup of
`paperclip-data` (RecurringJob `daily-backup-all-volumes`) per
`docs/sops/backup.md`. That would be a data-recovery task outside this plan's
git-revert class. In that case, stop and page the operator.

## 6. Interference notes

- **paperclip-26.04** (`conflicts_with`): it Recreates `deploy/paperclip`. This
  Job has REQUIRED podAffinity to that pod, so a same-slot run strands the verify
  Job in `Pending`. Either plan can run first; they only must not overlap.
- **Timing:** avoid 03:50-04:20Z (paperclip's in-app backup timer plus the
  scheduled cleanup). In the `nightly` window (03:30 Europe/Berlin = 01:30Z in
  CEST) this is naturally clear, and 4.4 lands about 2.5h later on its own.
- **Flux controllers** (`flux-distribution-2.9.6`, `flux-reconciler-impersonation`)
  apply this commit and its revert, so do not run either in the same slot.
- **Prometheus** is read in §4 (CONTROL lines), so do not share a slot with
  `kube-prometheus-stack-91.9.0`.
- **Out of scope:** the other `busybox:1.38.0@sha256:dc2d74b...` pins (anythingllm,
  edot-collector kmsg-heartbeat) are on an older push of the same tag. Their binary
  is byte-identical (§1), so this is cosmetic digest drift with no functional
  difference. It belongs to a fleet digest refresh, not here.
- The pull is about 2 MB per node. No node reboot, no Service, route or Homepage
  change.
