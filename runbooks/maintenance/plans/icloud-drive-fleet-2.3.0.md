---
plan_id: icloud-drive-fleet-2.3.0
component: icloud-drive-fleet           # mandarons/icloud-drive (repo github.com/mandarons/icloud-docker) on BOTH
                                        # backup/icloud-docker-mu and backup/icloud-docker-andrea ("KEEP IN SYNC")
pr: 445                                 # renovate/mandarons-icloud-drive-2.x, touches exactly the two helmrelease.yaml; CI green
                                        # (Flate Render Gate, Flux Local Diff helmrelease + kustomization), checked 2026-10-27
kind: image
current: "2.2.0@sha256:672ef76694381ec7c63543f231cd8e1244a003719acdc576e30e11a2c42a68b7"
target: "2.3.0@sha256:a352dd8a9e5b371d1f1f1c8fce886a2b88836204d0d857a2cd4474f505a60763"
                                        # Docker Hub tag 2.3.0 = OCI index (amd64 + arm64), pushed 2026-10-26T22:11Z;
                                        # identical to the digest in PR #445
update_type: minor
risk: low                               # for OUR config (photos.filters.file_sizes: [original], no preserve_originals_as_bak,
                                        # no fallback_to_original) every behaviour change in 2.3.0 is gated off; the auth
                                        # code path (icloudpy base.py, src/sync.py 2FA handler) is byte-identical. The real
                                        # change is the runtime: Python 3.10 -> 3.14, alpine 3.22 -> 3.24 (§1).
est_duration_min: 30                    # in-window: ~5 min land + Recreate x2, 20 min post-start watch, ~5 min checks.
                                        # The photo-cycle CONTENTS gate (§4.2) completes ~4.5 h AFTER the window (measured
                                        # first-cycle length after the 2026-10-23 restart) and is a sweep follow-up.
needs_reboot: false
touches:
  namespaces: [backup]
  resources:
    - helmrelease/icloud-docker-mu
    - helmrelease/icloud-docker-andrea
    - deployment/icloud-docker-mu
    - deployment/icloud-docker-andrea
    - pvc/icloud-docker-mu-data          # CIFS cifs-icloud-docker-mu (subdir icloud-backup/mu, Retain) - remount only, NO PVC change
    - pvc/icloud-docker-andrea-data      # CIFS cifs-icloud-docker-andrea (subdir icloud-backup/andrea, Retain) - remount only
    - pvc/icloud-docker-mu-session       # Longhorn RWO (longhorn-static) - detach/re-attach on Recreate
    - pvc/icloud-docker-andrea-session   # Longhorn RWO (dynamic, pvc-f6ec0213-...) - detach/re-attach on Recreate
  shared: [monitoring, nas-icloud-backup]
                                        # monitoring: READ-only - §4 reads Prometheus + the icloud-sync-probe pushgateway
                                        #   series (the window's instrument).
                                        # nas-icloud-backup: the //NAS icloud-backup tree. This plan WRITES into it (the apps'
                                        #   normal sync) and immich (cifs-immich-icloud-backup, ro) + icloud-backup-freshness
                                        #   READ the parent dir. A mass re-download (§4.2 guard) would churn immich's library
                                        #   scan. No other plan writes there.
depends_on: []
conflicts_with: [longhorn-1.13.0, talos-linux-1.14.4, flux-oci-chart-sources]
                                        # longhorn-1.13.0: Recreate detaches/re-attaches both Longhorn session volumes; never
                                        #   during a storage-engine upgrade (that plan is also exclusive: true).
                                        # talos-linux-1.14.4: node roll reschedules both pods mid-first-cycle and voids §4
                                        #   (exclusive: true anyway; declared for the record).
                                        # flux-oci-chart-sources: moves the bjw-s app-template source these HRs render from.
                                        # kube-prometheus-stack: NO plan file exists, but Renovate PR #428 (92.11.1 -> 92.14.0)
                                        #   is OPEN; a same-night Step 0 landing restarts the instrument §4 reads. Cannot be named
                                        #   here without a DEAD-REF, so premise kps-chart-unchanged fails the plan instead.
                                        # Renovate PR #354 (icloud-sync-probe python 3.14.9 -> 3.15.2) likewise has no plan file;
                                        #   it changes the probe that produces every icloud_* series §4 reads -> premise
                                        #   sync-probe-image-unchanged.
exclusive: false
security_ref: F-3b1cf57f                # security driver; detail on the finding record only (never in this file)
capability_change: false                # 2.3.0's new feature (file_sizes: full / adjusted, fallback_to_original) is OPT-IN and
                                        # not configured here; both configmaps request only `original`. No new route, port,
                                        # permission or exposure (service + ingress disabled, web UI stays off). Same
                                        # behaviour, new runtime.
rollback_class: git-revert              # no forward-only state: no DB, no schema; session files are the icloudpy cookiejar +
                                        # session JSON written by base.py, which is unchanged 0.11.0 -> 0.12.0; NAS files are
                                        # plain photos/drive files the 2.2.0 build reads by name+size/mtime as before (§5).
finding_refs: [F-3b1cf57f, F-5582fc62, F-bf1d72a8]
                                        # F-3b1cf57f security (critical, raw tier) on 2.2.0 - newer tag available
                                        # F-5582fc62 / F-bf1d72a8 version rows for icloud-docker-mu / -andrea 2.2.0 -> 2.3.0
                                        # NOT claimed (operator-owned, context only): F-1e5dda44 / F-1d9e0a1f / F-55544413 =
                                        # andrea 2FA re-auth pending. F-b7959c33 / F-f23bfad5 = mu's one stuck Apple-503 photo.
premises:
  - id: pins-are-2.2.0
    why: "Fallback sed in §3 step 2 anchors on this exact tag line in both files; anything but 2 means the bump already landed, the files moved, or the two instances drifted apart."
    run: cat kubernetes/apps/backup/icloud-docker-mu/app/helmrelease.yaml kubernetes/apps/backup/icloud-docker-andrea/app/helmrelease.yaml | grep -c 'tag. "2\.2\.0@sha256:672ef76694381ec7c63543f231cd8e1244a003719acdc576e30e11a2c42a68b7"'
    expect_exact: "2"
  - id: live-images-are-2.2.0
    why: "current: and every §4 baseline were measured on this digest (live 2026-10-27)."
    run: kubectl get deploy -n backup icloud-docker-mu icloud-docker-andrea -o jsonpath='{range .items[*]}{.spec.template.spec.containers[0].image}{"\n"}{end}' | grep -c '2.2.0@sha256:672ef766'
    expect_exact: "2"
  - id: hrs-ready
    why: "A HelmRelease already failing would mask whether the bump reconciled."
    run: kubectl get helmrelease -n backup icloud-docker-mu icloud-docker-andrea -o jsonpath='{range .items[*]}{.status.conditions[?(@.type=="Ready")].status}{" "}{end}'
    expect_exact: "True True"
  - id: andrea-hr-not-suspended
    why: "icloud-docker-reauth.md Step 1 suspends the HR during an operator re-auth. A suspended HR means a re-auth is IN PROGRESS: do not land a change that would roll the pod when it is resumed mid-ceremony."
    run: kubectl get helmrelease -n backup icloud-docker-andrea -o jsonpath='suspend={.spec.suspend}'
    expect_exact: "suspend="
  - id: mu-hr-not-suspended
    why: "Same as above for mu."
    run: kubectl get helmrelease -n backup icloud-docker-mu -o jsonpath='suspend={.spec.suspend}'
    expect_exact: "suspend="
  - id: andrea-running-1-of-1
    why: "Re-auth SOP scales to 0; 0 replicas = re-auth in progress or abandoned at 0. Also guards the log premise below, whose grep would print 0 on a missing pod."
    run: kubectl get deploy -n backup icloud-docker-andrea -o jsonpath='{.spec.replicas}/{.status.availableReplicas}'
    expect_exact: "1/1"
  - id: mu-running-1-of-1
    why: "Same as above for mu."
    run: kubectl get deploy -n backup icloud-docker-mu -o jsonpath='{.spec.replicas}/{.status.availableReplicas}'
    expect_exact: "1/1"
  - id: andrea-not-auth-blocked
    why: "THE GATE FOR THE PENDING RE-AUTH (F-1e5dda44). A restart of a 2FA-blocked instance calls _request_2fa_push_once() again (src/sync.py _handle_2fa_required, per-process SyncState, identical in 2.2.0 and 2.3.0): one more code from Apple's per-day quota and an unsolicited 2FA prompt on the account owner's devices at 03:30, and the pre-existing auth failure would read as a bump regression. The retry loop logs this line every 600 s, so 30 min holds >=2 lines while blocked. Measured 2026-10-27 03:15 CET: 3 (FAILS today, by design). Passes once the operator re-auth is done."
    run: kubectl logs deploy/icloud-docker-andrea -n backup -c app --since=30m | grep -c -i -e '2FA is required' -e '2SA is required'
    expect_exact: "0"
  - id: mu-not-auth-blocked
    why: "Same, for mu: an auth failure must be pre-existing-free before the bump so §4 can attribute one to it. Measured 2026-10-27 over 3 h: 0."
    run: kubectl logs deploy/icloud-docker-mu -n backup -c app --since=30m | grep -c -i -e '2FA is required' -e '2SA is required'
    expect_exact: "0"
  - id: strategy-recreate
    why: "Both mount an RWO Longhorn session PVC at replicas 1; RollingUpdate would Multi-Attach (docs/sops/longhorn-rwo-multi-attach.md). Live 2026-10-27: Recreate Recreate."
    run: kubectl get deploy -n backup icloud-docker-mu icloud-docker-andrea -o jsonpath='{range .items[*]}{.spec.strategy.type}{" "}{end}'
    expect_exact: "Recreate Recreate"
  - id: mu-session-volume-healthy
    why: "Recreate detaches/re-attaches the trusted-session volume; losing it forces a 2FA re-auth."
    run: kubectl get volumes.longhorn.io -n storage icloud-docker-mu-session -o jsonpath='{.status.state}/{.status.robustness}'
    expect_exact: attached/healthy
  - id: andrea-session-volume-healthy
    why: "Same for andrea's dynamic session volume (pvc icloud-docker-andrea-session)."
    run: kubectl get volumes.longhorn.io -n storage pvc-f6ec0213-4b00-49d9-93b4-954d5fee1d31 -o jsonpath='{.status.state}/{.status.robustness}'
    expect_exact: attached/healthy
  - id: kps-chart-unchanged
    why: "§4 reads Prometheus. Renovate PR #428 (kube-prometheus-stack 92.11.1 -> 92.14.0) is open; if it landed the instrument restarted. Fails by design then: re-run after the stack settles."
    run: kubectl get helmrelease -n monitoring kube-prometheus-stack -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: "92.11.1"
  - id: sync-probe-image-unchanged
    why: "Every icloud_* series §4 reads comes from CronJob icloud-sync-probe; Renovate PR #354 would change its runtime. Do not change the instrument in the same night."
    run: kubectl get cronjob -n backup icloud-sync-probe -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].image}'
    expect_contains: "python:3.14.9-alpine"
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/icloud-docker-reauth.md
  - docs/sops/storage-safety.md
  - docs/sops/longhorn-rwo-multi-attach.md
  - docs/sops/verification-contents-not-shape.md
review: null
status: draft
window: null                            # recommend: the first nightly AFTER the operator's andrea re-auth (premise
                                        # andrea-not-auth-blocked) and not the night kps #428 or probe PR #354 lands. See §6.
generated: "2026-10-27"
---

# icloud-drive fleet (icloud-docker-mu + icloud-docker-andrea) 2.2.0 -> 2.3.0

## 1. Summary & why held

Bumps `mandarons/icloud-drive` on **both** iCloud backup instances in ns `backup`. The image is built from
github.com/mandarons/icloud-docker. The two HelmReleases are
`kubernetes/apps/backup/icloud-docker-{mu,andrea}/app/helmrelease.yaml`, both app-template 5.3.0, and the
change moves `2.2.0@sha256:672ef766…` to `2.3.0@sha256:a352dd8a…`. Renovate PR #445 is exactly these two
lines, and CI is green. Both instances change in one commit, because the manifests say "KEEP IN SYNC".

Security driver: see `security_ref`.

> **Security driver** — sweep finding `F-3b1cf57f` (section `security`).
> Detail (affected packages, counts, exploitability) is kept on the finding
> record in sweep_history, not in this public repo. Read it with
> `runbooks/policy-cli.py finding show F-3b1cf57f`.

**Why held:** coverage.py G3 could not verify the release notes. The notes do exist, and I read them
(github.com/mandarons/icloud-docker/releases/tag/v2.3.0, published 2026-10-26T22:10Z, plus `CHANGELOG.md`
at tag v2.3.0). They list three changes: #577 (edited photos via `file_sizes: [full]`), #575 (a log-noise
fix) and #573 ("move to Python 3.14 and refresh dependencies"). The CHANGELOG has a **Changed** section
whose behavioural items are:

> On an edited photo, `medium`, `thumb` and the Live Photo `live_video_*` renditions now come from the
> `CPLAsset` record and therefore describe the edit. Their filenames do not change, so
> `check_photo_exists` sees a size mismatch and the first sync after the upgrade re-downloads them in place

> `photos.preserve_originals_as_bak` now hides the untouched original when the photo has an **edit**
> (`full`) …

> `icloudpy` 0.12.0: `PhotoAsset.versions` reads each version from the `CPLAsset` record first and falls
> back to `CPLMaster` …

> The image is built on Python 3.14 (`python:3.14-alpine3.24`, both stages)

**Which of these apply here.** I checked each one against the decrypted live config and the upstream code
diff (v2.2.0...v2.3.0, and icloudpy v0.11.0...v0.12.0):

- **Config.** Both `configmap.sops.yaml` set `photos.filters.file_sizes: ["original"]` and nothing else.
  `preserve_originals_as_bak` and `fallback_to_original` are unset (default false). So the
  medium/thumb/live re-download, the `.bak` change, the `-adjusted` suffix and the fallback are all
  **gated off**. In `src/sync_photos.py` they key on `"full" in file_sizes`, and `set_fallback_to_original`
  is `False` by default. The mu library holds **0** `*.original.bak` files (measured).
- **icloudpy CPLAsset-first lookup.** This is the one change that can reach `original`.
  `icloudpy/services/photos.py` now reads `fields = asset_fields if f"{prefix}Res" in asset_fields else
  master_fields`. The upstream docstring says the `CPLMaster` record carries `resOriginal*` and
  `CPLAsset` carries the edit (`resJPEGFull*`), so `original` should still resolve from the master. If an
  asset record ever carried `resOriginalRes` with a different size, `check_photo_exists` would re-download
  that original in place. That would mean bandwidth and NAS churn, not data loss (same path, overwrite).
  **§4.2 guards this explicitly.**
- **Auth path: unchanged.** `icloudpy/base.py` is not in the 0.11.0 -> 0.12.0 diff. The only `src/sync.py`
  hunks are `timezone.utc -> datetime.UTC`, and the `_handle_2fa_required` body is byte-identical between
  the two tags (diffed). The session cookiejar format is therefore unchanged in both directions.
- **Runtime jump.** This is the real change: `python:3.10-alpine3.22` -> `python:3.14-alpine3.24`. The live
  container prints `Python 3.10.20`. It is a wholesale dependency refresh (pytz and certifi dropped from
  icloudpy's direct requirements; `requests` still pulls certifi transitively). That is the risk §4.1
  tests for: import/TLS/runtime errors at start.
- **The sync-probe's log contract still holds.** `icloud-sync-probe` regexes the app logs. I grepped both
  tags' `src/` for every marker it uses (`:: Photos synced`, `:: Syncing photos...`,
  `:: Syncing drive...`, `:: Drive synced`, `Starting parallel downloads with`,
  `Parallel downloads completed:`, `Failed to download`, `2FA is required`,
  `Sign-in failed and will be retried`) and got identical counts in both. `docker-entrypoint.sh` is
  unchanged. A bump that silently renamed a marker would blind `ICloudBackupSyncStalled`; this one does not.

**Verdict:** for this configuration the hold is close to a false positive. It is a same-behaviour bump on a
new Python runtime. `risk: low`, `capability_change: false`, `rollback_class: git-revert`. Execution class
should derive **AUTO-NIGHT**. The one real constraint is the **pending andrea 2FA re-auth** (§2, §6). It is
operational, not technical.

## 2. Pre-checks

All frontmatter premises must PASS (`.venv/bin/python3 runbooks/plan-premises.py icloud-drive-fleet-2.3.0
--require-premises`). Then, as the executor:

1. **PR still targets the same digest** (premise runner cannot run `gh`):
   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   gh pr view 445 --json state,mergeable -q '.state+" "+.mergeable'          # expect: OPEN MERGEABLE
   gh pr diff 445 | grep -c '^+.*tag: "2\.3\.0@sha256:a352dd8a9e5b371d1f1f1c8fce886a2b88836204d0d857a2cd4474f505a60763"'   # expect: 2
   gh pr checks 445 | grep -c -i -e fail -e pending                           # expect: 0
   ```
   If #445 was retargeted (e.g. 2.3.1), STOP. Refresh this plan in place (README "When the held target
   MOVES") and do not use the fallback sed.
2. **Andrea re-auth state (the gate that matters).** The premise `andrea-not-auth-blocked` reads logs.
   Cross-check against the instrument:
   ```bash
   kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
   curl -s --get http://localhost:19090/api/v1/query --data-urlencode 'query=max by (account) (icloud_auth_required)' \
     | python3 -c "import sys,json; [print(r['metric']['account'], r['value'][1]) for r in json.load(sys.stdin)['data']['result']]"
   # expect BOTH lines, both 0:  andrea 0 / mu 0      (2026-10-27 03:15: andrea 1, mu 0 -> NO-GO today)
   curl -s --get http://localhost:19090/api/v1/query --data-urlencode 'query=ALERTS{alertname=~"ICloud.*",alertstate="firing"}' \
     | python3 -c "import sys,json; [print(r['metric']['alertname'], r['metric'].get('account')) for r in json.load(sys.stdin)['data']['result']]"
   # expect: no ICloudBackupAuthRequired line for any account. Missing series (fewer than 2 lines above) = probe broken -> STOP.
   kill $PF
   ```
   If andrea is still auth-blocked, **NO-GO for the whole plan**. Do not run "mu only": the instances
   must stay in sync. A separate andrea restart now would send an unsolicited 2FA push (§6). Record the
   reason and leave `window:` for re-scheduling. The operator's re-auth (docs/sops/icloud-docker-reauth.md,
   `INSTANCE=andrea`) is F-1e5dda44 and is **not** part of this plan.
3. **Baselines** (write them into the window log; §4.2 diffs against them). Each `find` over SMB takes
   ~15 s:
   ```bash
   for a in mu andrea; do
     echo "== $a photos=$(kubectl exec -n backup deploy/icloud-docker-$a -c app -- sh -c 'find /icloud/photos -type f | wc -l') \
   bak=$(kubectl exec -n backup deploy/icloud-docker-$a -c app -- sh -c 'find /icloud/photos -type f -name "*.original.bak" | wc -l') \
   drive=$(kubectl exec -n backup deploy/icloud-docker-$a -c app -- sh -c 'find /icloud/drive -type f | wc -l')"
   done
   # 2026-10-27 reference: mu photos=55030 bak=0 drive=68832 / andrea photos=24131 drive=7341
   ```
4. **Storage safety: read, do not act.** This plan does not create, delete or edit any PVC/PV/StorageClass.
   For the record, the CIFS data PVs are `subdir=icloud-backup/{mu,andrea}`, `reclaim=Retain` (severe tier
   per CLAUDE.md "Storage Safety"). If anything during this plan tempts a PVC delete/recreate, STOP. That
   is out of scope, and the 3-step pre-flight in `docs/sops/storage-safety.md` applies verbatim.

## 3. Steps

1. **Marker** (application-update.md):
   `runbooks/update-marker.sh add icloud-docker-mu backup 6 "icloud-drive 2.2.0->2.3.0"` and the same for
   `icloud-docker-andrea`. **No Alertmanager silence.** No icloud alert should fire on a clean run.
   `ICloudBackupDeploymentUnavailable` needs 30 min. `ICloudBackupSyncStalled` needs 6 h without
   `Photos synced`, and the first post-start cycle measured ~4.5 h (mu, 2026-10-23). If either fires,
   that is the regression signal. Do not mute it. Leave `upgrade.remediation.retries: 3` as is: Helm's
   auto-rollback is a safe first line here.
2. **Land the bump (preferred: merge the Renovate PR):**
   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   gh pr merge 445 --squash --delete-branch && git pull --ff-only
   git show --stat HEAD | grep -c 'kubernetes/apps/backup/icloud-docker-.*/app/helmrelease.yaml'   # expect 2
   ```
   **Fallback, if #445 is closed or unmergeable but the target is unchanged.** Make a direct edit. The sed
   was dry-tested on scratch copies (BSD sed, macOS, 2026-10-27) and changes exactly one line per file:
   `40c40` (mu) / `49c49` (andrea),
   `<  tag: "2.2.0@sha256:672ef766…68b7"  --->  tag: "2.3.0@sha256:a352dd8a…0763"`.
   ```bash
   for a in mu andrea; do
     sed -i '' 's|^\([[:space:]]*tag: \)"2\.2\.0@sha256:672ef76694381ec7c63543f231cd8e1244a003719acdc576e30e11a2c42a68b7"$|\1"2.3.0@sha256:a352dd8a9e5b371d1f1f1c8fce886a2b88836204d0d857a2cd4474f505a60763"|' \
       kubernetes/apps/backup/icloud-docker-$a/app/helmrelease.yaml
   done
   git diff --stat   # 2 files, 2 insertions, 2 deletions
   git commit --only kubernetes/apps/backup/icloud-docker-mu/app/helmrelease.yaml \
     kubernetes/apps/backup/icloud-docker-andrea/app/helmrelease.yaml \
     -m "feat(container): update mandarons/icloud-drive ( 2.2.0 -> 2.3.0 )" -m "Plan: icloud-drive-fleet-2.3.0. security_ref F-3b1cf57f."
   git log -1 --format=%s   # confirm the subject is THIS commit before pushing (shared worktree)
   git show --stat HEAD     # exactly the two helmrelease.yaml
   git push
   ```
   Then close #445 with a comment pointing at the commit.
3. Let the Flux webhook reconcile. Do not run a manual `flux reconcile`. Each Deployment is `Recreate`:
   the old pod terminates, the Longhorn session volume detaches and re-attaches, and the CIFS data volume
   remounts (`smb.csi.k8s.io`, no attach step). The new pod reaches `1/1` (no probes are configured). It
   then starts with **Drive** (`:: Syncing drive...`, measured ~2 h 09 min for mu on the last restart).
   Photos does not run until Drive finishes.
4. When §4.1 passes: record the in-window result. Set `status: awaiting-soak` and add a comment naming the
   §4.2 deadline (pod start + 6 h). Clear the markers after §4.2 passes:
   `runbooks/update-marker.sh clear icloud-docker-mu` and `... clear icloud-docker-andrea`.

## 4. Verification

### 4.1 In-window gates (run 20 min after both new pods are Running)

1. **New digest is what runs (not the old generation):**
   ```bash
   kubectl get pod -n backup -l 'app.kubernetes.io/instance in (icloud-docker-mu,icloud-docker-andrea)' \
     -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.status.containerStatuses[0].imageID}{"\n"}{end}'
   ```
   PASS: two lines, both ending `@sha256:a352dd8a9e5b371d1f1f1c8fce886a2b88836204d0d857a2cd4474f505a60763`.
   FAIL: the old pod's `…672ef766…` (rollout status green-lights the old generation; see
   feedback_rollout_status_old_generation), or the per-arch child digest `sha256:d83566072db8…`. That
   would mean the index pin was resolved differently and needs investigating, not rollback.
2. **The runtime actually changed:** for each instance,
   `kubectl exec -n backup deploy/icloud-docker-$a -c app -- python3 --version`. PASS: `Python 3.14.`.
   FAIL: `Python 3.10.20` (baseline today).
3. **Process alive and syncing, no runtime breakage.** For each instance:
   ```bash
   kubectl logs -n backup deploy/icloud-docker-$a -c app --since=25m | sed 's/\x1b\[[0-9;]*m//g' > /tmp/icd-$a.log
   grep -c ':: Syncing drive\.\.\.' /tmp/icd-$a.log                                  # PASS >= 1
   grep -c -i -e 'Traceback' -e 'ModuleNotFoundError' -e 'ImportError' -e 'SSLError' -e 'CERTIFICATE_VERIFY_FAILED' /tmp/icd-$a.log   # PASS 0
   grep -c -i -e '2FA is required' -e '2SA is required' -e 'Sign-in failed and will be retried' /tmp/icd-$a.log   # PASS 0
   kubectl get pod -n backup -l app.kubernetes.io/instance=icloud-docker-$a -o jsonpath='{.items[0].status.containerStatuses[0].restartCount}'   # PASS 0
   ```
   These gates can fail. A Python 3.14 import or TLS regression prints a `Traceback` at start, and
   `docker-entrypoint.sh` then restarts the container (restartCount > 0). A lost or rejected session prints
   `Error: 2FA is required` (src/sync.py:1173, the same line andrea prints today: 3 times in 30 min,
   measured). The pre-check premise proved that line was absent BEFORE the bump, so if it appears now,
   the bump is the cause. The greps are case-insensitive against ANSI-stripped output (the app logs with
   colour codes).
4. **Drive is actually moving data, not wedged** (sync-probe series lag up to 10 min, and Drive runs ~2 h,
   so read the network counter instead, per icloud-docker-reauth.md Troubleshooting):
   `kubectl exec -n backup deploy/icloud-docker-$a -c app -- grep eth0 /proc/net/dev`, taken twice 2 min
   apart. PASS: the receive-bytes column grows. FAIL: unchanged, which is the silent-wedge case of
   2026-09-06.

CONTROL: alertname ICloudBackupAuthRequired — must NOT be firing for account mu or andrea at the end of the window (andrea's pre-existing firing is excluded by premise andrea-not-auth-blocked).
CONTROL: alertname ICloudBackupDeploymentUnavailable — must NOT be firing (fires after 30 min of < 1 available replica).
CONTROL: metric icloud_auth_required — `max by (account)` returns exactly two series (mu, andrea), both 0, on the first icloud-sync-probe run after both new pods start (CronJob every 10 min). Fewer than two series = instrument broken, which fails the gate rather than passing it.

### 4.2 Contents gate (sweep follow-up, deadline = new pod start + 6 h)

This change could silently break the thing these apps exist for: **photos still land, and existing
photos are NOT re-downloaded en masse** (the icloudpy CPLAsset-first path in §1). Two failure modes are
in play. A wedge yields no `Photos synced`. A mass re-download yields a huge `successful` count and NAS
churn under the immich-read tree.

CONTENTS ASSERTION: first post-bump photo pass per account completes and re-downloads ~nothing — measured by the first `Photo processing complete: N successful, M failed` line in the new pod (`kubectl logs -n backup deploy/icloud-docker-$a -c app | sed 's/\x1b\[[0-9;]*m//g' | grep -m1 'Photo processing complete'`), compared to the pre-bump baseline of `0 successful, 1 failed` (mu, 12 of 12 passes in the last 6 h, 2026-10-27; the 1 is the known Apple-503 item). PASS: N <= 200 (new photos since the window plus slack). FAIL: N in the thousands. That is the CPLAsset `original` size-mismatch case: roll back (§5) and file it upstream. The line is emitted by `photo_download_manager.py` (lines 461 in v2.3.0 and 402 in v2.2.0, identical text).

CONTENTS ASSERTION: library not shrunk, no new `.bak` sidecars — measured by re-running the §2.3 `find` counts after the first `Photos synced`, compared to the §2.3 baseline. PASS: photos >= baseline and bak == 0 (mu baseline 0), drive >= baseline. `remove_obsolete: false` on both instances, so any drop is a defect, not a cleanup.

CONTROL: metric icloud_sync_last_success_timestamp_seconds — for EACH account, the value must advance past the new pod's `status.startTime` before the deadline (query `max by (account) (icloud_sync_last_success_timestamp_seconds)` and compare to the epoch of startTime). Today's baseline: mu ~20 min old; andrea ~10 h old (stalled by auth). After the re-auth gate, andrea must also advance.
CONTROL: metric icloud_drive_sync_last_success_timestamp_seconds — must advance past pod startTime for each account (first Drive cycle ~2 h).
CONTROL: alertname ICloudBackupSyncStalled — must NOT fire for either account (6 h without a `Photos synced`).
CONTROL: alertname ICloudBackupPersistentDownloadFailures — must not newly fire. mu's one known 503 item is already counted on the finding record (F-b7959c33) and is not a regression.

After §4.2 passes, retire this plan (`status: executed`, delete the file in the commit that records it).
Then close F-5582fc62 / F-bf1d72a8 and re-check F-3b1cf57f on the next security sweep:
`finding close <id> --commit <sha>`.

## 5. Rollback

Trigger: any §4.1 FAIL, or §4.2 FAIL (mass re-download / library shrink / no `Photos synced` by the
deadline with a 2.3.0-specific error in the log).

1. Revert the bump commit (both instances together, so they stay in sync):
   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   git revert --no-edit <sha-of-the-bump-commit>
   git log -1 --format=%s     # must be: Revert "feat(container): update mandarons/icloud-drive ( 2.2.0 -> 2.3.0 )" (or the squash title)
   git show --stat HEAD       # exactly the two helmrelease.yaml
   git push
   ```
2. Confirm the cluster is back:
   `kubectl get pod -n backup -l 'app.kubernetes.io/instance in (icloud-docker-mu,icloud-docker-andrea)' -o jsonpath='{range .items[*]}{.status.containerStatuses[0].imageID}{"\n"}{end}'`.
   PASS: both lines end `@sha256:672ef76694381ec7c63543f231cd8e1244a003719acdc576e30e11a2c42a68b7`.
   Also `python3 --version` should print `Python 3.10.20`, and the §4.1.3 greps should show 0
   auth/Traceback lines.
3. **Why a plain revert is enough.** No forward-only state exists. The session files are icloudpy's
   cookiejar + session JSON, written by an unchanged `base.py`. Photos and drive files are plain files
   that 2.2.0 matches by path + size/mtime. In the mass re-download case, the re-fetched files are the same
   originals written to the same paths, so there is nothing to restore. If a session were somehow
   invalidated, the recovery is the operator re-auth SOP (`docs/sops/icloud-docker-reauth.md`). It is NOT
   a PVC operation: never delete or recreate the session or data PVCs (CIFS severe tier + Longhorn
   trusted-session state).

## 6. Interference notes

- **Pending andrea re-auth (F-1e5dda44, operator-only).** This is the gate. A pod restart of a 2FA-blocked
  instance triggers a fresh `_request_2fa_push_once()`, which costs one Apple 2FA code from the per-day
  quota and puts an unsolicited prompt on the account owner's devices at night. It would also attribute
  a pre-existing failure to the bump. So the plan runs only once `andrea-not-auth-blocked` passes. Do not
  split into a mu-only leg. The fleet is pinned together on purpose, and mu's driver is not urgent enough
  to justify the drift (contextual tier on the finding record). If the operator re-auths in daytime, the
  next nightly is the natural slot. The re-auth SOP's helper pod pins its own 2.1.0 image; that is
  unaffected by this plan.
- **Do not run during a re-auth.** If the operator is mid-ceremony (HR suspended / replicas 0), the
  premises fail. That is intended. A git change to the HR during a scale-0 re-auth would re-render
  `replicas: 1` on the next upgrade and contend for the RWO session PVC (re-auth SOP, Troubleshooting).
- **Instrument stability.** §4 reads Prometheus and the `icloud-sync-probe` pushgateway series. Not the
  same night as kube-prometheus-stack PR #428 or the probe's python PR #354. Neither has a plan file,
  so both are enforced by premises.
- **Long tail.** In-window work is ~30 min. The meaningful gate (§4.2) completes ~4.5 h later and is a
  sweep follow-up (`awaiting-soak`), not a reason to hold the window open.
- **Shared NAS tree.** Writes land under `//NAS/…/icloud-backup/{mu,andrea}`. immich (ro) and
  icloud-backup-freshness read the parent. A mass re-download would be visible as an immich rescan
  burst; §4.2 catches it first.
- No gateway/HTTPRoute, DNS, CNI, cert-manager or shared DB is touched. No Authentik outpost is involved
  (service and ingress are disabled; web UI off).
