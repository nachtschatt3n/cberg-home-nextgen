---
plan_id: tube-archivist-elasticsearch-9.5.5
component: tube-archivist-elasticsearch
pr: 433
kind: image
current: "8.19.0"                     # bbilly1/tubearchivist-es:8.19.0, live pod digest
                                      # sha256:9da63fb1973ec3d57daf6916be948eddd0d8a404cc8e447c938480c85fe2c554
                                      # (= Docker Hub digest of the 8.19.0 tag, measured 2026-10-26)
target: "9.5.5"                       # Docker Hub digest sha256:9513a22cd332402cb6fd6ef69844f4f78717190ba9e2e08cb72b3288839d84fa
                                      # (single-arch amd64 manifest, pushed 2026-10-25T07:55Z)
update_type: major
risk: medium                          # one-way data step (ES cannot downgrade), but the index is
                                      # tiny (6.5 MB, 7 ta_* indices, all created on 8.x), ES's own
                                      # upgrade assistant reports zero deprecations, and the rollback
                                      # is a restore that §3.3 PROVES before anything is pushed.
est_duration_min: 65                  # preamble+pre-checks 7 + flush/snapshot 2 + on-demand Longhorn backup ~12
                                      # (all-volume job measured 10m04s on 2026-10-25) + restore proof
                                      # ~15 + bump/rollout up to 10 + verification 8 + the enforced 15-min
                                      # observation wait (§4.5) overlaps §4.2-4.4 only partly + retries restore 3.
                                      # sat-attended budget is 70 (90 - 20 Step 0): this plan fits ALONE only —
                                      # python-fleet (35) on 2026-11-14 would make 100 > 70.
needs_reboot: false
touches:
  namespaces: [download, storage]
  resources:
    - helmrelease/tube-archivist-elasticsearch   # tag, upgrade.timeout, remediation (temporarily), container memory limit 2Gi -> 3Gi
    - deployment/tube-archivist-elasticsearch
    - pvc/tube-archivist-elasticsearch-data-5g    # longhorn-static RWO, upgraded in place by ES 9 (one-way)
    - pv/tube-archivist-elasticsearch-data-5g
    - deployment/tube-archivist                   # restarted once in §4.4 to re-run its ES startup checks
    - job/tube-archivist-nfo-sync-*               # one-off job from cronjob/tube-archivist-nfo-sync (§4.3)
    - job/pre-ta-es9-*                            # ns storage, one-off from cronjob/daily-backup-all-volumes
    - volume.longhorn.io/tube-archivist-es-restoretest   # ns storage; scratch, created + deleted in §3.3 (Flux cannot own a Longhorn Volume CR)
    - volume.longhorn.io/tube-archivist-elasticsearch-data-5g   # ns storage; READ by the backup gate; in R2 only, the live volume is orphaned and a -r<date> copy is created and the PV is repointed (§5)
    - pvc/tube-archivist-es-restoretest           # scratch, created + deleted in §3.3
    - pod/ta-es-restoretest                       # scratch, created + deleted in §3.3
    - pvc/tube-archivist-youtube                  # cifs-tube-archivist-media (SEVERE tier) — NOT touched,
                                                  # named so nobody touches it
  shared: [storage/longhorn, monitoring]   # storage/longhorn: creates + deletes a Longhorn Volume CR in ns storage (§3.3),
                                      # runs the ALL-VOLUME Longhorn backup Job (§3.2, ~10 min, touches every volume's
                                      # backup chain) and, in R2, repoints a PV. Declared like jellyfin-config-rwo-migration;
                                      # the autonomy policy forbids unattended execution for storage/longhorn, so this is
                                      # HUMAN-GATED by derivation, not by courtesy. monitoring: an Alertmanager silence is
                                      # created and §4.5 reads Prometheus (the window's instrument is shared infra).
depends_on: []                        # Runs FIRST under tube-archivist v0.5.12 (whose ES gate accepts
                                      # majors 8..9, §1.2). tube-archivist-0.6.0 declares
                                      # depends_on: [tube-archivist-elasticsearch-9.5.5] and runs on a LATER NIGHT.
conflicts_with:
  - tube-archivist-0.6.0              # LATER NIGHT, never the same window: §4.4 restarts the TA app and would confound that
                                      # plan's §4 (and its own two Recreate rolls would confound this plan's §4.4)
  - redis-fleet-8.10.2                # also restarts deployment/tube-archivist and gates on it (§6)
  - longhorn-1.13.0                   # exclusive; storage engine one-way upgrade — this plan's backup Job + scratch volume + a
                                      # freshly 9.x-upgraded volume must not meet it inside 24 h either way (§6)
  - flux-reconciler-impersonation     # exclusive; uses helmrelease/tube-archivist-elasticsearch as its canary
  - talos-linux-1.14.4                # exclusive + reboot: node roll; no slot within 24 h (the new ES pod would be rescheduled
                                      # mid-observation, §4.5)
  - helm-drift-detection              # its gate asserts identical Helm revisions; this plan creates a new Helm revision on
                                      # helmrelease/tube-archivist-elasticsearch (and a second spec-only one in §3.6)
exclusive: false
security_ref: F-e268f1cc              # the AR-029 "already newest" acceptance on the 8.19.0 image —
                                      # its premise is false since 9.5.5 exists; detail in the DB.
capability_change: false              # same app (tube-archivist v0.5.12), same API surface, same
                                      # exposure; only the search engine major moves.
rollback_class: backup-restore
backup_gate: "§3.2: ES _flush (gated: _shards.failed == 0) + a manual ES snapshot pre-es9-<YYYYMMDD> in repo ta_snapshot (state SUCCESS), THEN an on-demand Longhorn backup via a one-off Job from cronjob/daily-backup-all-volumes (ns storage). PASS = the Job completes AND a Backup CR labelled backup-volume=tube-archivist-elasticsearch-data-5g exists with state Completed, a non-empty status.url and creationTimestamp AFTER GATE_START (recorded before the trigger) AND `.venv/bin/python3 runbooks/longhorn-backup-age.py tube-archivist-elasticsearch-data-5g --max-hours 1` prints FRESH (the same call printed STALE at 3.7h on 2026-10-26, so it can fail). The 23:00Z nightly backup alone does NOT satisfy the gate. The one-off Job (no ttl) is deleted by exact name afterwards; note it consumes one slot of the volumes' retain:7 history."
restore_proof: "§3.3, BEFORE the tag edit is pushed: the §3.2 Backup CR's status.url is restored into the scratch Longhorn volume tube-archivist-es-restoretest (numberOfReplicas 1), bound by a scratch PV/PVC in ns download, copied into an emptyDir and opened by a scratch pod ta-es-restoretest running bbilly1/tubearchivist-es:8.19.0. PASS = version.number 8.19.0 AND cluster health not red AND _cat/count/ta_video >= the §3.1 baseline AND > 0 AND _cat/count/ta_channel >= its baseline AND _cat/snapshots/ta_snapshot lists pre-es9-<YYYYMMDD> (proves the backup postdates the snapshot). Any mismatch = STOP, do not push. Scratch objects deleted by exact name at the end of §3.3."
finding_refs: [F-e268f1cc]            # queried 2026-10-26 (`finding list --grep tubearchivist-es`):
                                      # no version-section finding exists for this bump; F-0ac6bc26
                                      # (no-fix residual on the same image) is NOT claimed — it is
                                      # re-evaluated by security-check against 9.5.5 after the bump.
review: ready-for-go@2026-10-26   # plan-reviewer 2026-10-26: needs-fix on one blocker (restore wait state string unknown), fixed + stub-tested by the planner; HUMAN-GATED, window null
status: vetted
window: null
premises:
  - id: es-hr-still-8.19.0
    why: Every baseline, the restore-proof image and the rollback revert target assume the HR pins 8.19.0.
    run: kubectl get helmrelease -n download tube-archivist-elasticsearch -o jsonpath='{.spec.values.controllers.main.containers.app.image.tag}'
    expect_exact: "8.19.0"
  - id: es-live-image-8.19.0
    why: The workload actually serving must be the pinned 8.19.0 (no phantom/rollback copy).
    run: kubectl get deploy -n download tube-archivist-elasticsearch -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "bbilly1/tubearchivist-es:8.19.0"
  - id: ta-app-still-v0.5.12
    why: >-
      This plan is designed to run BEFORE tube-archivist-0.6.0 (upstream path 0.5.12 -> ES 9 -> 0.6.0).
      If the app already moved, §4.4's startup-log assertions and the sequencing argument must be re-derived.
    run: kubectl get deploy -n download tube-archivist -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "bbilly1/tubearchivist:v0.5.12"
  - id: es-pvc-longhorn-static-named
    why: backup_gate, restore_proof and the §5 restore all rest on this exact static volume binding.
    run: kubectl get pvc -n download tube-archivist-elasticsearch-data-5g -o jsonpath='{.spec.storageClassName} {.spec.volumeName}'
    expect_exact: "longhorn-static tube-archivist-elasticsearch-data-5g"
  - id: es-volume-attached
    why: An on-demand Longhorn backup only runs for an attached volume (recurring jobs skip detached ones).
    run: kubectl get volumes.longhorn.io -n storage tube-archivist-elasticsearch-data-5g -o jsonpath='{.status.state}'
    expect_exact: "attached"
  - id: es-hr-remediation-default
    why: §3.4 sets upgrade.remediation.retries 0 and §3.6 restores 3; the pre-state must be 3.
    run: kubectl get helmrelease -n download tube-archivist-elasticsearch -o jsonpath='{.spec.upgrade.remediation.retries}'
    expect_exact: "3"
  - id: backup-cronjob-exists
    why: The backup_gate is triggered from this CronJob (NOT `backup-of-all-volumes`, which does not exist).
    run: kubectl get cronjob -n storage daily-backup-all-volumes -o jsonpath='{.metadata.name}'
    expect_exact: "daily-backup-all-volumes"
  - id: repo-pin-8.19.0
    why: The §3.4 python patch aborts unless the tag line and the upgrade block match exactly once; drift breaks it.
    run: grep -c 'tag. "8.19.0"' kubernetes/apps/download/tube-archivist/app/elasticsearch-helmrelease.yaml
    expect_exact: "1"
  - id: media-sc-retain
    why: storage-safety.md — the media PVC on cifs-tube-archivist-media is never touched, but confirm Retain anyway.
    run: kubectl get sc cifs-tube-archivist-media -o jsonpath='{.reclaimPolicy}'
    expect_exact: "Retain"
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/backup.md
  - docs/sops/longhorn.md
  - docs/sops/storage-safety.md
generated: "2026-10-26"
---

# tube-archivist-elasticsearch 8.19.0 -> 9.5.5 (PR #433)

## 1. Summary & why held

Renovate PR #433 bumps the Tube Archivist search backend `bbilly1/tubearchivist-es`
(an Elastic image rebuilt by the Tube Archivist maintainer) from `8.19.0` to `9.5.5`.
This is a **major** Elasticsearch upgrade, held by `coverage.py` ("major — needs an
assessed window plan"). That hold is correct. Nothing here is a false positive.

### 1.1 Why it is not auto-safe — one-way data

Elastic, *Prepare to upgrade* (deploy-manage/upgrade/prepare-to-upgrade), quoted:

> "To perform a major upgrade from 8.x to 9.x of Elasticsearch, you must first upgrade to 8.19.x."
> "Indices created in 7.x or earlier must be reindexed, deleted, or archived (marked as read-only) before upgrading to 9.x."
> "After you start to upgrade your Elasticsearch cluster, you cannot downgrade any of its nodes."
> "If you can't complete the upgrade process, you must restore from a snapshot which was taken before starting the upgrade."

So a plain `git revert` is **not** a rollback after 9.5.5 has opened the data
directory. Also, Flux's default `upgrade.remediation.retries: 3` on this HR would
auto-rollback a slow or failed upgrade to 8.19.0, and 8.19.0 cannot start on
9.x-touched data. That turns a recoverable slow start into an outage. §3.4
therefore disables remediation for the attempt, per `application-update.md` Step 2.

### 1.2 Does tube-archivist v0.5.12 support ES 9? Yes, by its own code.

- `backend/config/management/commands/ta_connection.py` at tag **v0.5.12** (and
  already at v0.5.11) has `MIN_MAJOR, MAX_MAJOR = 8, 9`. The startup version check
  passes for any 8.x or 9.x. The v0.6.0 file is identical on these lines.
- TA talks to ES over raw REST (`ElasticWrap`, `requests`), with no version-pinned
  client library. The v0.5.12...v0.6.0 compare has no ES-API change. Its ES-touching
  diffs are pagination clamping, snapshot teardown and media-URL rewrites.
- Upstream v0.6.0 release notes (non-prerelease, published 2026-10-25), §Elasticsearch:
  > "The Elasticsearch update path is from `8.19.0` to `9.5.5`. If you use
  > `bbilly1/tubearchivist-es`, update it together with Tube Archivist."
  > "Update older installations to v0.5.12 and let startup complete before moving to v0.6.0."
  Upstream `docker-compose.yml`: v0.5.12 says "use official es 8.19.0", master says "es 9.5.5".

**Sequencing decision.** Run this ES plan first, under v0.5.12, which accepts ES 9.
That keeps the one-way data step separate from the app's breaking changes (non-root
user, nginx removal, media-URL change). Then run `tube-archivist-0.6.0` after it, on a
LATER night (never the same window, §6). "Together" in the upstream note means "same upgrade
cycle". It does not mean "same commit". Nothing in v0.6.0 needs ES 9, and nothing
in ES 9 needs v0.6.0.

### 1.3 Live readiness, measured 2026-10-26 (read-only GETs inside the ES pod)

- `GET /` -> `8.19.0`, `minimum_index_compatibility_version 7.0.0`. 8.19.x is the
  required starting point.
- Every index reports `index.version.created = 8525000`, which is an 8.x index
  version. There are **no 7.x-created indices**: `ta_channel, ta_comment, ta_config,
  ta_download_v2, ta_playlist, ta_subtitle, ta_video`.
- `GET _migration/deprecations` returns empty for cluster, node, index, ML, ILM,
  data-stream and template checks. `GET _migration/system_features` ->
  `NO_MIGRATION_NEEDED`.
- Cluster health is green, 1 node, 27 shards. Disk: indices 6.5 MB, 37 MB used of 4.8 GB.
- SLM `ta_daily` (cron `0 0 10 * * ?`, no timezone set, so UTC: 10:00Z = 11:00 CET) runs into fs repo `ta_snapshot` at
  `/usr/share/elasticsearch/data/snapshot`. This is the **same PVC**, so the ES
  snapshots are not independent of the volume. That is why the gate also takes a
  Longhorn backup.
- Target image (9.5.5): UBI9-minimal base, `User 1000:0`, entrypoint unchanged.
  `usr/bin/curl` and `usr/bin/sh` are in the base layer, and no later layer has a
  whiteout. So the HR's `curl`-based startup, readiness and liveness probes keep
  working. (The current 8.19.0 image is Ubuntu 24.04 and also ships curl.)

## 2. Pre-checks

All commands run from `/Users/mu/code/cberg-home-nextgen` in zsh. Any FAIL here is an
ABORT: nothing has changed yet.

**Shell state does not persist between Bash calls** (the window agent runs each block in a
fresh shell). Everything below therefore keeps its state in ONE env file, `/tmp/ta-es9-env.sh`
(mode 600, no secret in it), and **every later block starts with
`source /tmp/ta-es9-env.sh`** and, where it needs a variable, `need VAR ...`, which fails
closed (`ENV_MISSING_STOP`) instead of letting an empty variable turn a gate into a pass.

### 2.0 Preamble (run once; re-run the `source` line at the top of every later block)

```bash
cd /Users/mu/code/cberg-home-nextgen
umask 077
cat > /tmp/ta-es9-env.sh <<'ENVEOF'
# no secrets here; ELASTIC_PASSWORD is read INSIDE the ES pod, never on this host
es_pod() { kubectl get pods -n download -l app.kubernetes.io/instance=tube-archivist-elasticsearch --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1:].metadata.name}'; }
esget()  { kubectl exec -n download "$(es_pod)" -c app -- sh -c "curl -s -u elastic:\$ELASTIC_PASSWORD 'http://localhost:9200/$1'"; }
espost() { kubectl exec -n download "$(es_pod)" -c app -- sh -c "curl -s -X POST -u elastic:\$ELASTIC_PASSWORD 'http://localhost:9200/$1'"; }
esput()  { kubectl exec -n download "$(es_pod)" -c app -- sh -c "curl -s -X PUT -u elastic:\$ELASTIC_PASSWORD 'http://localhost:9200/$1'"; }
rget()   { kubectl exec -n download ta-es-restoretest -c app -- sh -c "curl -s -u elastic:\$ELASTIC_PASSWORD 'http://localhost:9200/$1'"; }
tapersist() { echo "export $1=$2" >> /tmp/ta-es9-env.sh; export "$1=$2"; }   # values: no spaces, no secrets
need() { for v in "$@"; do eval "val=\${$v:-}"; test -n "$val" || { echo "ENV_MISSING_STOP: $v"; return 1; }; done; }
ENVEOF
source /tmp/ta-es9-env.sh
tapersist D "$(date +%Y%m%d)"
test -n "$(es_pod)" && echo "es_pod=$(es_pod)"      # EXPECT the live pod name (empty = selector wrong, STOP)
```

### 2.1 Premises and the target digest

```bash
source /tmp/ta-es9-env.sh
.venv/bin/python3 runbooks/plan-premises.py tube-archivist-elasticsearch-9.5.5 --require-premises   # all PASS, no REFUSED

# target still published at the planned digest (network: not a premise)
curl -s "https://hub.docker.com/v2/repositories/bbilly1/tubearchivist-es/tags/9.5.5" \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print([i['digest'] for i in d['images']])"
#   EXPECT ['sha256:9513a22cd332402cb6fd6ef69844f4f78717190ba9e2e08cb72b3288839d84fa'].
#   A different digest = re-pushed tag: re-run the §1.3 image check (curl present) before going on, and
#   update NEW_DIGEST in §3.5.
```

### 2.2 Flux + workloads healthy

```bash
flux get helmreleases -n download | grep tube-archivist          # 3 rows, READY True
kubectl get pods -n download -o wide | grep -E '^tube-archivist-(elasticsearch|redis|[0-9a-f]+-)'   # Running 1/1
```

### 2.3 ES readiness, re-measured (read-only GETs). EXPECT exactly as in §1.3

```bash
source /tmp/ta-es9-env.sh
esget '' | python3 -c "import sys,json;print(json.load(sys.stdin)['version']['number'])"            # 8.19.0
esget '_all/_settings?filter_path=*.settings.index.version.created' \
  | python3 -c "import sys,json;v={k:x['settings']['index']['version']['created'] for k,x in json.load(sys.stdin).items()};print(v);sys.exit(0 if v and all(s.startswith('8') for s in v.values()) else 'FAIL: non-8.x index')"
esget '_migration/deprecations' | python3 -c "
import sys,json;d=json.load(sys.stdin)
n=sum(len(v) for v in d.values() if isinstance(v,(list,dict)))
print('deprecations',n);sys.exit(0 if n==0 else 'FAIL: deprecations present, read them before going on')"
esget '_cluster/health' | python3 -c "import sys,json;s=json.load(sys.stdin)['status'];print(s);sys.exit(0 if s=='green' else 'FAIL')"
#   (each python check exits non-zero on the failure it names; an empty dict for index versions also fails
#    via the `v and` guard; an auth error body has no 'version' key -> KeyError -> non-zero)
```

### 2.4 No in-flight TA work (a download writing during the gate would be lost on rollback)

The earlier `kubectl logs | grep downloading` check was noise (about 2000 hits per 24 h of
yt-dlp metadata lines), so it is replaced by a filesystem check. yt-dlp writes in-progress
files under `/cache/download` and moves them on completion; a file touched in the last 10
minutes means a download is live.

```bash
kubectl exec -n download deploy/tube-archivist -c app -- sh -c 'find /cache/download -type f -mmin -10 | wc -l'
#   EXPECT 0 (measured 0 on 2026-10-26, with one stale file present: the -mmin filter is what matters).
#   >0 = a download is active: wait and re-run. How it fails: any touched .part/.ytdl file makes it >0;
#   a wrong path prints 0 with an error on stderr (the `ls -d /cache/download` line below proves the path exists).
kubectl exec -n download deploy/tube-archivist -c app -- ls -d /cache/download
```

### 2.5 Monitoring instrument not moving under us

§4.5 reads Prometheus. Renovate PR #428 (kube-prometheus-stack 92.11.1 -> 92.13.1) is
OPEN, parked by the 48 h age gate, and Step 0 of this window can apply it right before §4.5.

```bash
gh pr view 428 --json state,title -q '.state + " " + .title'                      # note OPEN/MERGED
kubectl get hr -n monitoring kube-prometheus-stack -o jsonpath='{.spec.chart.spec.version}{"\n"}'
kubectl get pod -n monitoring prometheus-kube-prometheus-stack-0 -o jsonpath='{.status.startTime}{"\n"}'
#   If Step 0 bumped KPS this window, Prometheus restarted: §4.5 must wait until its pod has been up
#   >= 20 min (the script in §4.5 checks this and fails closed), or this plan moves to another night.
```

## 3. Steps

### 3.0 Silence + update marker (application-update.md Step 1)

```bash
source /tmp/ta-es9-env.sh
kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 >/dev/null 2>&1 & AM=$!; sleep 2
NOW=$(python3 -c "from datetime import *;print(datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
END=$(python3 -c "from datetime import *;print((datetime.now(timezone.utc)+timedelta(hours=3)).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
SID=$(curl -s -X POST localhost:9093/api/v2/silences -H 'Content-Type: application/json' -d '{
  "matchers":[{"name":"namespace","value":"download","isRegex":false,"isEqual":true},
              {"name":"alertname","value":"TubeArchivist.*|Kube(Pod|Deployment).*","isRegex":true,"isEqual":true}],
  "startsAt":"'$NOW'","endsAt":"'$END'","createdBy":"maintenance-window",
  "comment":"tube-archivist-elasticsearch 8.19.0->9.5.5 — rollout noise. auto-expires 3h"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['silenceID'])")
test -n "$SID" && tapersist SILENCE_ID "$SID" || echo SILENCE_FAILED_STOP
kill $AM 2>/dev/null
runbooks/update-marker.sh add tube-archivist-elasticsearch download 3 "ES 8.19.0->9.5.5"
```

The silence only stops paging. Prometheus keeps evaluating, and §4.5 reads
**Prometheus** `/api/v1/alerts`, so the gate still sees the alerts.

### 3.1 Baseline counts (contents, taken BEFORE the backup)

```bash
source /tmp/ta-es9-env.sh; need D || exit 1
for i in ta_video ta_channel ta_playlist ta_download_v2 ta_config; do
  printf '%s ' $i; esget "_cat/count/$i?h=count"; done | tee /tmp/ta-es-baseline-$D.txt
#   measured 2026-10-26: ta_video 1669, ta_channel 33, ta_playlist 6, ta_download_v2 3, ta_config 2
B_VID=$(awk '$1=="ta_video"{print $2}' /tmp/ta-es-baseline-$D.txt); B_CH=$(awk '$1=="ta_channel"{print $2}' /tmp/ta-es-baseline-$D.txt)
if test "${B_VID:-0}" -gt 0 && test "${B_CH:-0}" -gt 0; then tapersist B_VID "$B_VID"; tapersist B_CH "$B_CH"; echo BASELINE_OK; else echo BASELINE_EMPTY_STOP; fi
#   an empty baseline makes every later >= check vacuous, hence STOP; B_VID/B_CH now live in the env file
```

### 3.2 backup_gate: flush, ES snapshot, on-demand Longhorn backup

```bash
source /tmp/ta-es9-env.sh; need D B_VID || exit 1
espost '_flush' | python3 -c "import sys,json;s=json.load(sys.stdin)['_shards'];print(s);sys.exit(0 if s['total']>0 and s['failed']==0 else 'FLUSH_FAIL_STOP')"
#   gated: a failed shard flush or an auth error body (no '_shards' key -> KeyError) exits non-zero
esput "_snapshot/ta_snapshot/pre-es9-$D?wait_for_completion=true" \
  | python3 -c "import sys,json;s=json.load(sys.stdin)['snapshot'];print(s['snapshot'],s['state'],s['shards']);sys.exit(0 if s['state']=='SUCCESS' and s['shards']['failed']==0 else 'FAIL')"
#   (a manual snapshot is not subject to the ta_daily SLM retention; it is a roll-FORWARD
#    restore point inside ES 9 if indices misbehave while the node itself starts — §5 R0)

tapersist GATE_START "$(date -u +%Y-%m-%dT%H:%M:%SZ)"; echo "GATE_START=$GATE_START"
kubectl create job --from=cronjob/daily-backup-all-volumes pre-ta-es9-$D -n storage
kubectl wait -n storage job/pre-ta-es9-$D --for=condition=complete --timeout=30m
kubectl get backups.longhorn.io -n storage -l backup-volume=tube-archivist-elasticsearch-data-5g -o json \
  | GATE_START=$GATE_START python3 -c '
import json,os,sys
g=os.environ["GATE_START"]
c=[b for b in json.load(sys.stdin)["items"] if b["metadata"]["creationTimestamp"]>g and b.get("status",{}).get("state")=="Completed" and b.get("status",{}).get("url")]
c.sort(key=lambda b:b["metadata"]["creationTimestamp"])
if not c: sys.exit("GATE FAIL: no Completed backup with url after GATE_START")
print(c[-1]["metadata"]["name"]); open(os.path.expanduser("~/ta-es9-backup-url.txt"),"w").write(c[-1]["status"]["url"])'
#   the printed Backup CR name is GATE_BACKUP (status.url saved to ~/ta-es9-backup-url.txt under umask 077;
#   it contains no secret). An unsynced CR (F-a915dd47) has an empty url: wait 2 min and re-run the
#   selector; do not fall back to the 23:00Z backup.
.venv/bin/python3 runbooks/longhorn-backup-age.py tube-archivist-elasticsearch-data-5g --max-hours 1   # FRESH
kubectl delete job -n storage pre-ta-es9-$D          # exact name; no ttlSecondsAfterFinished on the CronJob (live 2026-10-26)
```

Side effect to know: this Job is the same all-volume backup as the nightly one. Longhorn
keeps `retain: 7` backups per volume for the RecurringJob, so one extra run shortens every
volume's retained history by one day. That is acceptable for a single run, and it is why
the Job must not be repeated "to be safe".

### 3.3 restore_proof: restore the gate backup into scratch and open it with 8.19.0

`docs/sops/longhorn.md`: the Longhorn `Volume` CR is applied by hand. The URL contains
`&`, so it is substituted with Python, never sed (`backup.md`, "Substituting a backup URL").

```bash
source /tmp/ta-es9-env.sh; need D B_VID B_CH || exit 1
S=$(mktemp -d); cat > $S/restoretest.yaml.tmpl <<'EOF'
---
apiVersion: longhorn.io/v1beta2
kind: Volume
metadata:
  name: tube-archivist-es-restoretest
  namespace: storage
spec:
  size: "5368709120"
  numberOfReplicas: 1
  staleReplicaTimeout: 30
  dataEngine: v1
  accessMode: rwo
  frontend: blockdev
  migratable: false
  encrypted: false
  fromBackup: "__BACKUP_URL__"
---
apiVersion: v1
kind: PersistentVolume
metadata:
  name: tube-archivist-es-restoretest
spec:
  capacity: {storage: 5Gi}
  volumeMode: Filesystem
  accessModes: [ReadWriteOnce]
  persistentVolumeReclaimPolicy: Retain
  storageClassName: longhorn-static
  csi:
    driver: driver.longhorn.io
    fsType: ext4
    volumeAttributes: {numberOfReplicas: "1", staleReplicaTimeout: "30"}
    volumeHandle: tube-archivist-es-restoretest
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: tube-archivist-es-restoretest
  namespace: download
spec:
  accessModes: [ReadWriteOnce]
  resources: {requests: {storage: 5Gi}}
  storageClassName: longhorn-static
  volumeName: tube-archivist-es-restoretest
EOF
URL="$(cat ~/ta-es9-backup-url.txt)" python3 -c 'import os,sys;sys.stdout.write(sys.stdin.read().replace("__BACKUP_URL__",os.environ["URL"]))' \
  < $S/restoretest.yaml.tmpl > $S/restoretest.yaml
grep -c '__BACKUP_URL__' $S/restoretest.yaml        # EXPECT 0
kubectl apply --dry-run=server -f $S/restoretest.yaml && kubectl apply -f $S/restoretest.yaml

# wait for the restore to finish: detached + not faulted + restoreRequired false (bounded loop, 20 min)
for n in $(seq 1 60); do
  st=$(kubectl get volumes.longhorn.io -n storage tube-archivist-es-restoretest -o jsonpath='{.status.state} {.status.robustness} {.status.restoreRequired}')
  echo "$n $st"; case "$st" in "detached unknown false"|"detached healthy false"|"detached degraded false") break;; esac; sleep 20; done
case "$st" in "detached unknown false"|"detached healthy false"|"detached degraded false") echo RESTORE_VOLUME_READY;; *) echo RESTORE_VOLUME_NOT_READY_STOP;; esac
#   A DETACHED Longhorn volume reports robustness `unknown` (live: other detached volumes read "detached unknown false"), so
#   `unknown` is the normal finished state; the earlier healthy/degraded-only match would have timed out every time.
#   fails closed: an unfinished restore (restoreRequired true), an attached/faulted volume or a missing object never matches, the loop
#   times out after 20 min and STOP is printed. Replica check (no failed replica, all stopped):
kubectl get replicas.longhorn.io -n storage -l longhornvolume=tube-archivist-es-restoretest -o jsonpath='{range .items[*]}{.status.currentState} failedAt={.spec.failedAt}{"\n"}{end}'
#   EXPECT every line "stopped failedAt=" (empty). The real proof is not this read: it is the scratch pod opening the data below.
echo "$S" > /tmp/ta-es9-scratchdir.txt
```

```bash
source /tmp/ta-es9-env.sh; need D B_VID B_CH || exit 1
S=$(cat /tmp/ta-es9-scratchdir.txt)
cat > $S/pod.yaml <<'EOF'
apiVersion: v1
kind: Pod
metadata:
  name: ta-es-restoretest          # deliberately NOT tube-archivist-* (keeps TubeArchivist* alerts clean)
  namespace: download
spec:
  restartPolicy: Never
  initContainers:
    - name: copy
      image: busybox:1.38
      securityContext: {runAsUser: 0}
      command: ["/bin/sh","-c","cp -a /r/. /work/ && chown -R 1000:1000 /work && du -sh /work"]
      volumeMounts:
        - {name: restored, mountPath: /r, readOnly: true}
        - {name: work, mountPath: /work}
  containers:
    - name: app
      image: bbilly1/tubearchivist-es:8.19.0
      securityContext: {runAsUser: 1000, runAsGroup: 1000}
      env:
        - {name: discovery.type, value: single-node}
        - {name: xpack.security.enabled, value: "true"}
        - {name: path.repo, value: /usr/share/elasticsearch/data/snapshot}
        - {name: ES_JAVA_OPTS, value: "-Xms512m -Xmx512m"}
        - name: ELASTIC_PASSWORD
          valueFrom: {secretKeyRef: {name: tube-archivist-secrets, key: TUBE_ARCHIVIST_ELASTIC_PASSWORD}}
      resources: {requests: {cpu: 200m, memory: 1Gi}, limits: {memory: 1536Mi}}
      volumeMounts:
        - {name: work, mountPath: /usr/share/elasticsearch/data}
  volumes:
    - name: restored
      persistentVolumeClaim: {claimName: tube-archivist-es-restoretest, readOnly: true}
    - name: work
      emptyDir: {sizeLimit: 2Gi}
EOF
kubectl apply -f $S/pod.yaml
kubectl wait -n download pod/ta-es-restoretest --for=condition=Ready --timeout=10m
# wait until the node answers with a USABLE status (a 401/503 error body also contains "status": do not match on that)
for n in $(seq 1 24); do
  R_HEALTH=$(rget '_cluster/health' | python3 -c "import sys,json;print(json.load(sys.stdin).get('status',''))" 2>/dev/null)
  case "$R_HEALTH" in green|yellow) break;; esac; sleep 10; done
R_VER=$(rget '' | python3 -c "import sys,json;print(json.load(sys.stdin)['version']['number'])")
R_VID=$(rget '_cat/count/ta_video?h=count' | tr -d '[:space:]'); R_CH=$(rget '_cat/count/ta_channel?h=count' | tr -d '[:space:]')
R_SNAP=$(rget '_cat/snapshots/ta_snapshot?h=id' | grep -c "^pre-es9-$D$")
echo "ver=$R_VER health=$R_HEALTH video=$R_VID/$B_VID channel=$R_CH/$B_CH presnap=$R_SNAP"
test "$R_VER" = 8.19.0 && { test "$R_HEALTH" = green || test "$R_HEALTH" = yellow; } && test "${R_VID:-0}" -ge "$B_VID" && test "${R_VID:-0}" -gt 0 \
  && test "${R_CH:-0}" -ge "$B_CH" && test "$R_SNAP" = 1 && echo RESTORE_PROOF_PASS || echo RESTORE_PROOF_FAIL_STOP
#   How it fails: an auth/empty response leaves R_VID empty -> ${R_VID:-0} = 0 -> FAIL; a health that never
#   reaches green/yellow (error body, red) -> FAIL; a backup taken BEFORE §3.2's snapshot lacks pre-es9-$D ->
#   R_SNAP 0 -> FAIL; a corrupt copy -> never Ready -> FAIL. B_VID/B_CH come from the env file (need above).

# cleanup — exact names only; Longhorn driver, Retain PV, scratch volume (never the live one):
kubectl delete pod -n download ta-es-restoretest --wait=true
kubectl get pv tube-archivist-es-restoretest -o jsonpath='{.spec.csi.driver} {.spec.csi.volumeHandle}{"\n"}'   # driver.longhorn.io tube-archivist-es-restoretest — else STOP
kubectl delete pvc -n download tube-archivist-es-restoretest
kubectl delete pv tube-archivist-es-restoretest
kubectl delete volumes.longhorn.io -n storage tube-archivist-es-restoretest
rm -rf $S /tmp/ta-es9-scratchdir.txt
```

**RESTORE_PROOF_FAIL_STOP => stop the plan here.** Nothing has been pushed. Clear the
silence and marker, then report.

### 3.4 The bump: tag + upgrade timeout + memory limit 3Gi + remediation off for the attempt (one commit)

The HelmRelease sets `install.timeout: 15m` but nothing for `upgrade`, so the 5 m Helm
default applies; a ~850 MB image pull plus an ES 9 start can exceed it, and with
`retries: 0` a timeout is terminal. The same commit adds `upgrade.timeout: 15m` and keeps it
afterwards (it is correct on its own).

The same commit raises the container memory limit from 2Gi to 3Gi (requests unchanged). The 8.19.0 pod already runs at a
1743Mi working set against 2048Mi; an OOMKill of 9.5.5 AFTER it has opened the data directory cannot be reverted cheaply
(it leads straight to R2), so the headroom is bought before the one-way step. The limit stays after the plan. It is a limit, not
a request, so scheduling is unchanged; check node allocatable memory first if in doubt.

Dry-tested 2026-10-26 on a scratch copy (python3, so BSD-sed quoting does not apply); the
script aborts without writing unless each anchor matches exactly once, and a second run
aborts (idempotence). Resulting diff:

```
21a22
>     timeout: 15m # 9.x image pull (~850 MB) + ES start can exceed the 5m default; with retries 0 a timeout is terminal
24c25,26
<       retries: 3
---
>       retries: 0 # ES major is one-way: a Helm rollback to 8.x cannot start on 9.x data
>       remediateLastFailure: false
44c46
<               tag: "8.19.0"
---
>               tag: "9.5.5"
62c64
<                 memory: 2Gi
---
>                 memory: 3Gi # ES 9 JVM + off-heap; 8.19.0 already sits at 1743Mi of 2Gi (working set, 2026-10-26)
```

```bash
source /tmp/ta-es9-env.sh; need D || exit 1
cat > /tmp/ta-es9-patch.py <<'EOF'
import pathlib, sys
p = pathlib.Path(sys.argv[1]); s = p.read_text()
edits = [
 ('  upgrade:\n    cleanupOnFail: true\n    remediation:\n      retries: 3\n',
  '  upgrade:\n    timeout: 15m # 9.x image pull (~850 MB) + ES start can exceed the 5m default; with retries 0 a timeout is terminal\n    cleanupOnFail: true\n    remediation:\n      retries: 0 # ES major is one-way: a Helm rollback to 8.x cannot start on 9.x data\n      remediateLastFailure: false\n'),
 ('              tag: "8.19.0"\n', '              tag: "9.5.5"\n'),
 ('              limits:\n                memory: 2Gi\n', '              limits:\n                memory: 3Gi # ES 9 JVM + off-heap; 8.19.0 already sits at 1743Mi of 2Gi (working set, 2026-10-26)\n'),
]
for old, new in edits:
    n = s.count(old)
    if n != 1: sys.exit(f"ABORT: anchor matched {n}x: {old[:50]!r}")
    s = s.replace(old, new)
p.write_text(s); print("es bump patched")
EOF
F=kubernetes/apps/download/tube-archivist/app/elasticsearch-helmrelease.yaml
python3 /tmp/ta-es9-patch.py $F                       # prints "es bump patched"
python3 -c "import yaml;yaml.safe_load(open('$F'));print('yaml ok')"
git diff --stat -- $F            # 1 file, 5 insertions(+), 3 deletions(-)
grep -c 'retries: 3' $F          # EXPECT 1 (the install: block, untouched)
# record the OLD generation BEFORE the push: §3.5 must not accept it
tapersist OLD_ES "$(es_pod)"; tapersist ROLL_START "$(date -u +%Y-%m-%dT%H:%M:%SZ)"; echo "OLD_ES=$OLD_ES"
cat > /tmp/ta-es9-msg.txt <<'EOF'
feat(tube-archivist): elasticsearch 8.19.0 -> 9.5.5 (supersedes #433)

ES major, one-way data step; plan tube-archivist-elasticsearch-9.5.5.
Upgrade remediation disabled for the attempt (Helm rollback to 8.x
cannot start on 9.x data), upgrade.timeout 15m, memory limit 2Gi -> 3Gi;
remediation restored after verification.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
git commit --only $F -F /tmp/ta-es9-msg.txt
git log -1 --format=%s            # MUST be the subject above (shared-worktree message race)
git show --stat HEAD              # exactly $F
git push
```

Renovate auto-closes #433 once `main` carries 9.5.5. Do not merge #433 as well.

### 3.5 Watch the rollout (Recreate, RWO) — new generation only

`kubectl wait --for=condition=Ready` straight after `git push` passes on the OLD 8.19.0 pod
(Flux has not rolled yet), so the gate below accepts a pod only if it is NOT `OLD_ES`, is
not terminating, and its `imageID` ends with the 9.5.5 digest, AND the Deployment spec says
`:9.5.5`.

```bash
source /tmp/ta-es9-env.sh; need OLD_ES || exit 1
NEW_DIGEST=sha256:9513a22cd332402cb6fd6ef69844f4f78717190ba9e2e08cb72b3288839d84fa
for n in $(seq 1 90); do
  img=$(kubectl get deploy -n download tube-archivist-elasticsearch -o jsonpath='{.spec.template.spec.containers[0].image}')
  new=$(kubectl get pods -n download -l app.kubernetes.io/instance=tube-archivist-elasticsearch -o json | OLD_ES=$OLD_ES NEW_DIGEST=$NEW_DIGEST python3 -c '
import json,os,sys
for p in json.load(sys.stdin)["items"]:
    if p["metadata"]["name"]==os.environ["OLD_ES"] or p["metadata"].get("deletionTimestamp"): continue
    for c in p.get("status",{}).get("containerStatuses",[]):
        if c["name"]=="app" and c.get("imageID","").endswith(os.environ["NEW_DIGEST"]): print(p["metadata"]["name"]); sys.exit(0)')
  echo "$n deploy_image=$img new_pod=${new:-none}"
  if [ "$img" = "bbilly1/tubearchivist-es:9.5.5" ] && [ -n "$new" ]; then break; fi
  sleep 10
done
if [ "$img" = "bbilly1/tubearchivist-es:9.5.5" ] && [ -n "$new" ]; then tapersist ES "$new"; echo NEW_GENERATION_FOUND; else echo NEW_GENERATION_NOT_FOUND_GO_TO_5; fi
#   How it fails: before Flux rolls, the Deployment still says :8.19.0 and the only pod is OLD_ES -> loop keeps
#   going; if Flux never applies, or the pull never finishes inside 15 min, NOT_FOUND is printed.
kubectl wait -n download pod/$ES --for=condition=Ready --timeout=10m && tapersist ES_READY_AT "$(date +%s)"
kubectl get pod -n download $ES -o jsonpath='{.status.containerStatuses[?(@.name=="app")].restartCount}{" "}{.status.containerStatuses[?(@.name=="app")].lastState.terminated.reason}{"\n"}'
#   EXPECT "0 " (restartCount 0, no terminated reason). "N OOMKilled" = JVM heap + off-heap above the 2Gi limit
#   (the limit is now 3Gi; 8.19.0 measured a 1743Mi working set on 2026-10-26): STOP, go to §5 (R1 grep first).
kubectl logs -n download $ES -c app | grep -ciE 'cannot downgrade|failed to obtain node lock|IllegalStateException|exception during startup'   # EXPECT 0
kubectl get events -n download --field-selector involvedObject.name=$ES | grep -ciE 'OOMKill'                                                  # EXPECT 0
```

If the pod is not Ready within 10 minutes, `NEW_GENERATION_NOT_FOUND` printed, restartCount
> 0, or either grep is > 0, go to §5.

### 3.6 After §4 passes: restore remediation (second commit, no pod restart)

Only the two remediation lines revert; `timeout: 15m` and the 3Gi limit stay. Dry-tested on the scratch copy
(diff against the pre-plan file after both scripts: the `timeout` line, the tag line and the memory-limit line only).

```bash
source /tmp/ta-es9-env.sh; need ES || exit 1
cat > /tmp/ta-es9-revert.py <<'EOF'
import pathlib, sys
p = pathlib.Path(sys.argv[1]); s = p.read_text()
old = '      retries: 0 # ES major is one-way: a Helm rollback to 8.x cannot start on 9.x data\n      remediateLastFailure: false\n'
new = '      retries: 3\n'
n = s.count(old)
if n != 1: sys.exit(f"ABORT: anchor matched {n}x")
p.write_text(s.replace(old, new)); print("remediation restored")
EOF
F=kubernetes/apps/download/tube-archivist/app/elasticsearch-helmrelease.yaml
python3 /tmp/ta-es9-revert.py $F
git diff -- $F                    # only the two remediation lines revert
printf 'chore(tube-archivist): restore ES upgrade remediation after 9.5.5\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\n' > /tmp/ta-es9-msg2.txt
git commit --only $F -F /tmp/ta-es9-msg2.txt && git log -1 --format=%s && git show --stat HEAD && git push
#   then confirm: same pod name/startTime as §4 (spec.upgrade is not a pod-template change, no pod roll)
kubectl get pod -n download $ES -o jsonpath='{.metadata.name} {.status.startTime}{"\n"}'
```

Finally, delete the silence and clear the marker:

```bash
source /tmp/ta-es9-env.sh; need SILENCE_ID || exit 1
kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 >/dev/null 2>&1 & AM=$!; sleep 2
curl -s -X DELETE localhost:9093/api/v2/silences/$SILENCE_ID; kill $AM 2>/dev/null
runbooks/update-marker.sh clear tube-archivist-elasticsearch
rm -f /tmp/ta-es9-env.sh /tmp/ta-es9-patch.py /tmp/ta-es9-revert.py /tmp/ta-es9-msg.txt /tmp/ta-es9-msg2.txt
```

## 4. Verification

Every block starts with `source /tmp/ta-es9-env.sh` (see §2).

### 4.1 Floor (shape checks)

```bash
source /tmp/ta-es9-env.sh; need ES || exit 1
flux get helmreleases -n download tube-archivist-elasticsearch     # READY True, chart app-template@5.3.0
kubectl get pod -n download $ES -o jsonpath='{.status.containerStatuses[?(@.name=="app")].imageID}{"\n"}'
#   EXPECT ...@sha256:9513a22cd332402cb6fd6ef69844f4f78717190ba9e2e08cb72b3288839d84fa (§2.1 digest)
esget '' | python3 -c "import sys,json;print(json.load(sys.stdin)['version']['number'])"   # 9.5.5
esget '_cluster/health' | python3 -c "import sys,json;print(json.load(sys.stdin)['status'])"   # green
```

### 4.2 CONTENTS ASSERTION: every index survived with its documents

CONTENTS ASSERTION: the doc counts of ta_video and ta_channel on ES 9.5.5 are >= the
§3.1 baseline and > 0 (these two GATE). ta_playlist, ta_download_v2 and ta_config are INFORMATIONAL: the download queue
legitimately shrinks (3 -> 2 was observed) and playlist/config change by use; a lower count there is printed, never a failure.

```bash
source /tmp/ta-es9-env.sh; need D || exit 1
test -s /tmp/ta-es-baseline-$D.txt || { echo BASELINE_FILE_MISSING_FAIL; exit 1; }
for i in ta_video ta_channel ta_playlist ta_download_v2 ta_config; do
  b=$(awk -v i=$i '$1==i{print $2}' /tmp/ta-es-baseline-$D.txt); n=$(esget "_cat/count/$i?h=count" | tr -d '[:space:]')
  case $i in ta_video|ta_channel)
    if test -z "$b"; then echo "$i NO_BASELINE FAIL"
    elif test "${n:-0}" -ge "$b" && test "${n:-0}" -gt 0; then echo "$i $n>=$b PASS"; else echo "$i ${n:-EMPTY}<$b FAIL"; fi;;
  *) echo "$i now=${n:-EMPTY} baseline=${b:-none} INFO";; esac; done
esget '_all/_settings?filter_path=*.settings.index.version.created' | python3 -c "import sys,json;print(sorted({x['settings']['index']['version']['created'] for x in json.load(sys.stdin).values()}))"
#   EXPECT ['8525000'] — same indices, read by 9.x; a fresh 9.x version id means an index was RECREATED (empty) -> FAIL
```

How it fails (the two gated indices): a missing index returns an error body, so `n` is empty and reads 0, which is
a FAIL. A recreated, empty index has count 0, which is a FAIL, and its created-version
changes. A missing baseline now prints `NO_BASELINE FAIL` (the earlier `${b:-1}` default
would have passed any `n > 0`); a missing baseline FILE exits before the loop.

### 4.3 CONTENTS ASSERTION: the real consumer reads the index

CONTENTS ASSERTION: `tube-archivist-nfo-sync` reads `ta_video/_search?size=10000`
from ES 9.5.5 and retrieves >= B_VID videos. It must not print `Error fetching from ES`
(that code path is `get_all_videos()` in `configmap/tube-archivist-nfo-sync`: on any
HTTP or auth error it prints that line and returns `[]`, which makes the result
`Retrieved 0 videos`).

```bash
source /tmp/ta-es9-env.sh; need D B_VID || exit 1
J=nfo-sync-es9-$D; kubectl create job -n download --from=cronjob/tube-archivist-nfo-sync $J
kubectl wait -n download job/$J --for=condition=complete --timeout=15m
LOG=$(kubectl logs -n download job/$J)
ERRS=$(printf '%s\n' "$LOG" | grep -ci 'error fetching from es')
RET=$(printf '%s\n' "$LOG" | sed -n 's/^Retrieved \([0-9][0-9]*\) videos.*/\1/p' | tail -1)
echo "errors=$ERRS retrieved=${RET:-NONE} baseline=$B_VID"
if test "$ERRS" = 0 && test -n "$RET" && test "$RET" -gt 0 && test "$RET" -ge "$B_VID"; then echo NFO_PASS; else echo NFO_FAIL; fi
#   fails on: the error line (ERRS>0), no "Retrieved" line (RET empty), Retrieved 0, or fewer than the baseline
kubectl delete job -n download $J
```

### 4.4 CONTENTS ASSERTION: the app passes its ES startup checks against 9.5.5

The only code path that runs v0.5.12's `_es_version_check` and `_es_path_check` is
app startup, so restart the app once. Success prints `✓ ES version check passed`.
Failure prints `🗙 ES version check failed`, sleeps 60 s and raises `CommandError`
(source: `ta_connection.py`). The grep is case-insensitive. This is the ONLY restart of the
app in this window: the sibling `tube-archivist-0.6.0` runs on a later night.

```bash
source /tmp/ta-es9-env.sh
tapersist RS "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
kubectl rollout restart deploy/tube-archivist -n download
kubectl rollout status deploy/tube-archivist -n download --timeout=10m
TA=$(kubectl get pods -n download -l app.kubernetes.io/name=tube-archivist --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1:].metadata.name}')
CT=$(kubectl get pod -n download $TA -o jsonpath='{.metadata.creationTimestamp}')
python3 -c "import sys;sys.exit(0 if '$CT' > '$RS' else 'OLD_GENERATION_FAIL')" && echo "new generation $TA created $CT > restart $RS"
kubectl logs -n download $TA | grep -ciE 'es version check passed'                    # EXPECT >= 1
kubectl logs -n download $TA | grep -ciE 'check failed'                               # EXPECT 0
kubectl logs -n download $TA | grep -ciE 'path\.repo'                                 # EXPECT >= 1 ([5] check ran)
```

### 4.5 Alerts and restarts (Prometheus, not Alertmanager — the silence does not hide these)

CONTROL: alertname TubeArchivistPodCrashLooping — must NOT be firing for any pod in download 15 min after §3.5.
CONTROL: alertname TubeArchivistPodNotReady — must NOT be firing (expr covers pod=~"tube-archivist-.*", which includes the ES pod).
CONTROL: metric kube_pod_container_status_restarts_total — the NEW ES pod's series must EXIST and increase over 15m must be 0. An empty result is a FAIL (series not scraped), not a pass.

The 15-minute observation is ENFORCED by the script (it waits until `ES_READY_AT + 900 s`
before reading), and it refuses to read from a Prometheus that has itself been up for less
than 20 minutes (a KPS bump applied by Step 0 restarts it; an `increase()` over a window it
has not covered reads 0 and would pass vacuously). The silence is not a control: these are
read from Prometheus. Foreground waits may be blocked by the harness; if so, run the wait
loop under `Monitor` with the same condition.

```bash
source /tmp/ta-es9-env.sh; need ES ES_READY_AT || exit 1
while [ $(( $(date +%s) - ES_READY_AT )) -lt 900 ]; do sleep 30; done; echo "15 min observation elapsed"
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 >/dev/null 2>&1 & PF=$!; sleep 2
PST=$(kubectl get pod -n monitoring prometheus-kube-prometheus-stack-0 -o jsonpath='{.status.startTime}')
python3 -c "
from datetime import datetime,timezone,timedelta
t=datetime.strptime('$PST','%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
age=(datetime.now(timezone.utc)-t)
print('prometheus up',age)
import sys;sys.exit(0 if age>timedelta(minutes=20) else 'PROMETHEUS_TOO_YOUNG_WAIT_OR_MOVE')"
curl -s localhost:9090/api/v1/alerts | python3 -c "
import sys,json
a=[x['labels']['alertname'] for x in json.load(sys.stdin)['data']['alerts'] if x['state']=='firing' and x['labels'].get('alertname','').startswith('TubeArchivist')]
print(a or 'none');sys.exit(1 if a else 0)"
curl -s --data-urlencode "query=increase(kube_pod_container_status_restarts_total{namespace=\"download\",pod=\"$ES\"}[15m])" localhost:9090/api/v1/query \
  | python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];print(r);sys.exit('FAIL: no series' if not r else (1 if any(float(x['value'][1])>0 for x in r) else 0))"
kill $PF 2>/dev/null
```

Known limit: the two alert checks are absence checks and no known-bad baseline exists for
them on this cluster today; the restart-counter check is the one with a defined failure
(empty series or increase > 0), and the OOM/restart read in §3.5 is the direct signal.

## 5. Rollback

Decide by the failure point:

- **Fail at or before §3.3:** nothing has changed. Clear the silence and marker. Done.
- **R0, roll forward:** ES 9.5.5 is Ready but an index is missing or short (§4.2).
  Restore from the in-repo snapshot inside 9.x, which reads 8.x snapshots:
  `POST _snapshot/ta_snapshot/pre-es9-$D/_restore` with
  `{"indices":"ta_*","include_global_state":false}`. Close or delete the affected
  `ta_*` index first; ES refuses to restore over an open index. Then re-run §4.2–4.4.
  If that fails, go to R2.
- **R1, cheap revert attempt:** ES 9.5.5 never became Ready and its log shows no
  node-metadata upgrade. `git revert --no-edit <§3.4 commit>`, then `git log -1 --format=%s`,
  `git show --stat HEAD`, `git push`. If 8.19.0 then starts and §4.2 passes against
  the baseline, you are back. If its log matches
  `grep -ciE 'cannot downgrade|incompatible|IndexFormatTooNew'` with a result > 0,
  the data dir was already upgraded. Do not retry. Go to R2. (An OOMKilled 9.5.5 whose
  node already opened the data dir lands here too.)
- **R2, restore from the gate backup.** This is the path §3.3 already exercised for the
  CONTENTS of the backup; §3.3 does NOT exercise the PV/PVC repoint below, so verify that
  part step by step. `volumeHandle` on a PV is immutable and `pv/pvc` are git-tracked in
  `elasticsearch-volume.yaml`, so the live volume is never overwritten. Restore into a NEW
  volume and repoint:

```bash
source /tmp/ta-es9-env.sh; need D || exit 1
cd /Users/mu/code/cberg-home-nextgen
flux suspend kustomization tube-archivist -n download
flux suspend helmrelease tube-archivist-elasticsearch -n download
kubectl scale deploy -n download tube-archivist-elasticsearch --replicas=0
kubectl wait -n download --for=delete pod -l app.kubernetes.io/instance=tube-archivist-elasticsearch --timeout=5m
R=tube-archivist-elasticsearch-data-5g-r$D
# (a) Volume CR: §3.3's template, Volume document only, name -> $R, numberOfReplicas 2 (the live
#     volume runs 2; git's PV says "3" — write the SAME value you choose into the PV in (b)).
#     fromBackup = ~/ta-es9-backup-url.txt, substituted with the §3.3 python one-liner. Wait detached+healthy:
kubectl get volumes.longhorn.io -n storage $R -o jsonpath='{.status.state} {.status.robustness} {.status.restoreRequired}{"\n"}'   # loop as in §3.3 until "detached unknown false" (a detached volume reports robustness unknown)
# (b) git, NOT pushed yet: elasticsearch-volume.yaml
#       PV  metadata.name -> $R ; spec.csi.volumeHandle -> $R   (Retain, longhorn-static, ext4, 5Gi unchanged)
#       PVC spec.volumeName -> $R ; PVC NAME stays tube-archivist-elasticsearch-data-5g (= existingClaim)
#     elasticsearch-helmrelease.yaml: tag back to "8.19.0" (git revert of §3.4 if not already done in R1)
# (c) free the old binding — pre-flight first (Longhorn, Retain; NEVER name pvc/tube-archivist-youtube):
PV=$(kubectl get pvc -n download tube-archivist-elasticsearch-data-5g -o jsonpath='{.spec.volumeName}')
kubectl get pv "$PV" -o jsonpath='{.spec.csi.driver} {.spec.persistentVolumeReclaimPolicy} {.spec.csi.volumeHandle}{"\n"}'
#     MUST print: driver.longhorn.io Retain tube-archivist-elasticsearch-data-5g — anything else: STOP
kubectl delete pvc -n download tube-archivist-elasticsearch-data-5g
kubectl delete pv "$PV"     # Retain: Longhorn volume tube-archivist-elasticsearch-data-5g (the 9.x state)
                            # stays for forensics; delete it only after the restored one has soaked
# (d) commit --only both files, verify subject + stat, push; resume:
flux resume kustomization tube-archivist -n download
kubectl get pvc -n download tube-archivist-elasticsearch-data-5g -o jsonpath='{.status.phase} {.spec.volumeName}{"\n"}'   # Bound $R
flux resume helmrelease tube-archivist-elasticsearch -n download
# (e) the Deployment is still at replicas 0: `kubectl scale` changed the live object but Helm's three-way merge
#     compares the OLD manifest (replicas 1) with the NEW one (replicas 1), sees no difference and does not
#     restore it. Wait until the Deployment spec carries the 8.19.0 image, then scale up explicitly:
for n in $(seq 1 60); do
  img=$(kubectl get deploy -n download tube-archivist-elasticsearch -o jsonpath='{.spec.template.spec.containers[0].image}')
  [ "$img" = "bbilly1/tubearchivist-es:8.19.0" ] && break; sleep 10; done; echo "deploy image=$img"       # must read 8.19.0
kubectl scale deploy/tube-archivist-elasticsearch -n download --replicas=1
kubectl wait -n download pod -l app.kubernetes.io/instance=tube-archivist-elasticsearch --for=condition=Ready --timeout=10m
kubectl get deploy -n download tube-archivist-elasticsearch -o jsonpath='{.spec.replicas} {.status.readyReplicas}{"\n"}'   # 1 1
```

**Confirm you are back.** The pod imageID must be
`...@sha256:9da63fb1973ec3d57daf6916be948eddd0d8a404cc8e447c938480c85fe2c554`, and
`GET /` must report `8.19.0`. The pod must mount the NEW volume:
`kubectl get pod -n download <pod> -o jsonpath='{.spec.volumes}'` names PVC
`tube-archivist-elasticsearch-data-5g` and that PVC's `volumeName` is `$R`. Re-run §4.2 (ta_video/ta_channel >= baseline, created versions
`8525000`), §4.3 (nfo-sync retrieves >= B_VID) and §4.4 (TA restart passes the ES
check). A Ready pod alone is not evidence. Anything written to ES between §3.2 and
the failure is lost: a few minutes at night, which §2.4 kept empty. Then clear the
silence and marker, and set this plan `status: blocked` with the failure log.

## 6. Interference notes

- **Order and window recommendation.** ES first, `tube-archivist-0.6.0` on a LATER night,
  never the same window: §4.4 here restarts the TA app, which would confound that plan's
  §4, and that plan's two Recreate rolls would confound this plan's §4.4. Both are
  HUMAN-GATED (storage/longhorn surface here; an authenticated-sync change there). The
  sat-attended budget is 70 min (90 - 20 Step 0). Booked Saturdays at writing: 2026-11-07
  (otel-operator + helm-drift), 2026-11-14 (python-fleet, 35 min: 35 + 65 = 100 > 70, and
  the slot is 23 h before the Longhorn roll on 2026-11-15), 2026-11-21 (authentik, 45 min:
  45 + 65 > 70). **Recommended: `sat-attended:2026-11-28`** (free, 13 days after the Longhorn
  roll, 27 days after the Talos roll), then `tube-archivist-0.6.0` on `sat-attended:2026-12-05`.
  Note `redis-fleet-8.10.2` is on 2026-11-29: it restarts the TA app the day after this
  plan, so keep the 11-28 observation (§4.5) finished before the window closes and do not
  read that restart as an ES effect. `window` is left null because the plan is `draft`
  (the scheduler refuses non-vetted plans); the coordinator stamps it after review.
- **Avoid the ES snapshot clock.** SLM `ta_daily` (`0 0 10 * * ?`, UTC unless a timezone is
  set: measured live 2026-10-26, no timezone field) fires at 10:00Z = 11:00 CET /
  12:00 CEST, into the same repo. A 09:00 Berlin Saturday window ends well before it in
  both seasons; do not let this plan straddle it.
- **tube-archivist-0.6.0** also warns: v0.6.0 deletes existing ES snapshots if snapshots are
  disabled, which would remove this plan's `pre-es9-*` snapshot, so leave snapshots enabled
  until both plans have soaked.
- **`redis-fleet-8.10.2`** (vetted, `sun-attended:2026-11-29`). It restarts
  `deployment/tube-archivist` and gates on it, so it is listed in `conflicts_with`.
  That plan should list this one reciprocally (`--validate` does not check reciprocity).
- **`longhorn-1.13.0`** (exclusive, `sun-attended:2026-11-15`), **`talos-linux-1.14.4`**
  (exclusive, reboot, `sun-attended:2026-11-01`), **`flux-reconciler-impersonation`**
  (exclusive; canary is `helmrelease/tube-archivist-elasticsearch`), **`helm-drift-detection`**
  (asserts identical Helm revisions): all declared in `conflicts_with`. No slot within 24 h
  of a Longhorn or Talos roll in either direction (the 2026-11-02 nightly follows the Talos roll).
- **Prometheus is read in §4.5.** `kube-prometheus-stack` PR #428 (92.11.1 -> 92.13.1) is
  open and parked by the age gate; if Step 0 of the same window applies it, Prometheus
  restarts. §2.5 and §4.5 detect that (`PROMETHEUS_TOO_YOUNG_WAIT_OR_MOVE`); wait or move.
- **Longhorn:** §3.2 starts the same all-volume backup Job that runs nightly at 23:00Z
  (~10 min, incremental, concurrency 2). Do not start it while another plan's
  backup gate Job is running in the same window. Run them one after the other, since
  both wait on `job/... --for=condition=complete`.
- **Storage safety:** `pvc/tube-archivist-youtube` (`cifs-tube-archivist-media`,
  severe tier) is never named in any step. The only PVC/PV deletes in this plan are
  the `tube-archivist-es-restoretest` scratch objects (§3.3) and, in R2 only, the
  Longhorn-backed ES binding, after its driver/Retain pre-flight.
- **Future ES work, not this plan:** after 9.5.5, `_migration/deprecations` will
  start flagging the 8.x-created `ta_*` indices as needing a reindex before ES 10.
  That becomes a TA-side reindex question at the next major.
