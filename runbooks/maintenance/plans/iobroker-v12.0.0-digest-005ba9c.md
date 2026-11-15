---
plan_id: iobroker-v12.0.0-digest-005ba9c
component: iobroker
pr: 352                               # Renovate "update buanet/iobroker ( 46b7b46 -> 005ba9c )", digest-only, CI green
                                      # (Flate Render Gate, Flux Local Diff x2) when read 2026-11-14.
kind: image
current: "v12.0.0@sha256:46b7b467244ef54bf4f1faadad988a630f94aff16613d4a3a0c161e72ad8808a"   # live 2026-11-14: statefulset/iobroker, pod iobroker-0 on k8s-nuc14-03
target: "v12.0.0@sha256:005ba9c285887d2ca13dad94aab75a93bf2fea1c5016c6f54802c4e1c4fb0a27"    # Docker Hub index digest of v12.0.0 (== latest-v12 == build 20261112.040747), pushed 2026-11-12T04:22Z
update_type: patch                    # same tag, rebuilt image (digest-only). Contents NOT diffed here (§1).
risk: low
est_duration_min: 20                  # pre-checks 5, commit+reconcile 2, pull+start up to 6 (startup probe allows 15 min, PACKAGES
                                      # installs influxdb2-cli at boot), verification 7. NOT measured on a prior roll.
needs_reboot: false
touches:
  namespaces: [home-automation]
  resources:
    - helmrelease/iobroker                # the one edit: image.tag digest in app/helm-release.yaml
    - statefulset/iobroker                # 1 replica, updateStrategy RollingUpdate; pod iobroker-0 is deleted and recreated
    - pod/iobroker-0
    - pvc/iobroker-config                 # longhorn-static RWO 15Gi (1003M used), PV iobroker-config; re-attached, NOT modified by this plan
    - service/iobroker                    # LoadBalancer 192.168.55.25; endpoints leave and return
    - httproute/iobroker                  # envoy-external (public host); returns 503 while the pod is down
  shared: []                              # nothing shared is restarted. No other workload in home-automation consumes iobroker
                                          # (see §1 Consumers). Gates G1-G4,G6,G7 read the kube API / pod only; G5 (Prometheus) is
                                          # informational, so no monitoring serialization is needed.
depends_on: []
conflicts_with:
  - longhorn-1.13.0                       # storage engine bump (exclusive) under pvc/iobroker-config while it re-attaches
  - talos-linux-1.14.5                    # node roll: reboots the node iobroker-0 and its Longhorn replicas sit on
  - flux-oci-chart-sources                # may move the app-template chart source under this HR mid-window
  - helm-drift-detection                  # changes how helm-controller applies HelmReleases, this one included
exclusive: false
security_ref: F-87b87b41                  # AR-029 accepted "already on newest tag" row for this image; this is a same-tag rebuild, so the
                                          # plan changes whatever that row measures. Detail stays in the DB.
                                          # F-c630e5e6 (AR-029 "no upstream fix", same image) is the sibling row, also listed below.
capability_change: false                  # same tag, same env/ports/mounts/route. No new route, port, permission or exposure.
rollback_class: git-revert                # image-only; see §5 for the backup-restore fallback if the new image touched PVC data on boot
finding_refs: [F-87b87b41, F-c630e5e6]    # queried 2026-11-14 (`policy-cli.py finding list --grep iobroker`); F-c630e5e6 is the same-image AR-029
                                          # row (shown 2026-11-15: accepted, section security): a digest move can change what it measures, so it is
                                          # tied to this plan too. F-c7b79015 / F-9eb8def2 are Wazuh/Falco volume rows, EXCLUDED: about
                                          # iobroker-0 execs, not answered by an image bump.
review: ready-for-go@2026-11-16      # plan-reviewer 2nd pass 2026-11-16: ready-for-go, 0 blocking (1st pass needs-fix: G7 grepped stdout; now reads iobroker.current.log with baseline, verified live). Advisory: read G7 as a printed count not exit status (grep -c exits 1 on 0); G7 alone cannot prove a clean boot, G3/G4 cover startup.
status: vetted
window: null
premises:
  - id: sts-runs-old-digest
    why: "current and every baseline below were captured against this pin. If it already moved, this plan is stale."
    run: |-
      kubectl get statefulset iobroker -n home-automation -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "buanet/iobroker:v12.0.0@sha256:46b7b467244ef54bf4f1faadad988a630f94aff16613d4a3a0c161e72ad8808a"
  - id: manifest-pin-is-old-digest
    why: "the §3 edit replaces exactly this digest; 0 means git already moved and the edit would be a silent no-op."
    run: |-
      grep -c 'sha256:46b7b467244ef54bf4f1faadad988a630f94aff16613d4a3a0c161e72ad8808a' kubernetes/apps/home-automation/iobroker/app/helm-release.yaml
    expect_exact: "1"
  - id: hr-ready
    why: "a HelmRelease already failing would mask whether the bump itself reconciled."
    run: |-
      kubectl get helmrelease iobroker -n home-automation -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: pvc-bound
    why: "the pod mounts pvc/iobroker-config at /opt/iobroker; Pending/Lost means the new pod cannot start."
    run: |-
      kubectl get pvc iobroker-config -n home-automation -o jsonpath='{.status.phase}'
    expect_exact: "Bound"
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/longhorn.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-11-14"
---

# iobroker v12.0.0 digest 46b7b46 -> 005ba9c

## 1. Summary & why held

**What changes.** The tag stays `v12.0.0`; only the pinned digest moves. Upstream (`buanet/iobroker`)
republishes the same version tag on every image rebuild (Docker Hub, 2026-11-14: `v12.0.0`,
`latest-v12` and `v12.0.0-build.20261112.040747` all resolve to `sha256:005ba9c2...`; earlier
rebuilds exist for 11-11 and 11-06). The pod therefore picks up several rebuilds at once.
The js-controller inside is a data-dir-resident install (`/opt/iobroker` on the PVC), currently
js-controller 7.0.6 on Node v24.21.0. That is expected to be unchanged (the image does not own it),
but this is MEASURED in §4, not assumed.

**Why held (inferred, not stated by the PR).** A digest-only move on a mutable version tag carries no
release notes and no semver signal, so the auto-updater cannot prove it safe. The PR body has no
notes ("Some dependencies could not be looked up"). I did NOT diff the image contents; upstream
changelog evidence for this rebuild was not retrieved. The risk call below rests on the
measured blast radius, not on knowing what changed in the image.

**Third-party image rule.** We consume `buanet/iobroker`; we bump, never rebuild or patch it.

**Consumers (measured 2026-11-14).**
- Home Assistant: `grep -rIl -i "iobroker\|192.168.55.25"` over `/config` (yaml/json) in the
  home-assistant pod returned nothing. HA does not depend on iobroker (nor the reverse).
- Repo: no other app references `192.168.55.25`/iobroker except the influxdb token comment (a
  365-day token for org `cberg`; the influxdb adapter is not installed, see below).
- Live adapters: `iob list instances` shows exactly 3, all enabled: `admin.0` (0.0.0.0:8081),
  `backitup.0`, `discovery.0`. `node_modules` holds only admin, backitup, discovery, js-controller.
  Nothing listens on 8082/vis (curl 000); admin on 8081 answers 200. The Service still advertises
  vis/node-red/mqtt/nuki/alexa ports, and `objects.jsonl` still contains stale
  `system.adapter.{cloud,iot,iqontrol,jarvis,javascript,vis-2,web,history}.0` rows, but none of those
  are running, so no live automation, voice or MQTT flow is observed to depend on this pod.
  CAVEAT: an external client that only talks to the LoadBalancer IP (Alexa cloud, a phone app) would
  not show in a repo or HA grep; with these adapters absent there is nothing for it to talk to.
- Backups: backitup writes a tar.gz nightly at 02:48 Berlin to `/opt/iobroker/backups` (latest
  `iobroker_2026_11_14-02_48_10_backupiobroker.tar.gz`); it lives ON the PVC, so it is not an
  independent copy. Longhorn `daily-backup-all-volumes` (23:00 UTC) last completed
  2026-11-13T23:08:47Z (11 backups on record for `iobroker-config`).

**Data/blast radius.** 1003M of 15G used; json-l object/state store (`objects.jsonl` /
`states.jsonl`, 8929 state lines) with the js-controller's own 9000/9001 loopback DB. A restart
drops the admin UI for the pod's startup time (about 2-6 min incl. boot-time package install).
No schema migration is expected from an image-only move; the entrypoint's PERMISSION_CHECK
re-chowns the volume on boot (it already does on every restart).

**Observed baseline noise (do not blame the bump for these).** Pod had 2 restarts; last
termination `exitCode 255, Unknown` at 2026-11-12T13:30:50Z (cause not investigated here; a
restart is evidently tolerated). The Falco/Wazuh 100404 volume rows (F-c7b79015, F-9eb8def2)
are about iobroker-0 execs and are NOT answered by this plan.

**Risk call: low.** Idle-looking workload (3 adapters), single replica, no consumers found,
git-revert rollback, a Longhorn backup under 24h old. The one unmeasured factor is the image
content diff (see above). Attended window NOT required (§6).

## 2. Pre-checks

```bash
# 1. Flux + pod healthy before touching anything
kubectl get hr iobroker -n home-automation        # READY True
kubectl get pod iobroker-0 -n home-automation     # 1/1 Running
# 2. Longhorn backup of the volume is < 24h old and Completed
kubectl get volume iobroker-config -n storage -o jsonpath='{.status.lastBackupAt}{"\n"}'
# 3. Baselines the §4 content gates compare against (record these in the window log)
kubectl exec -n home-automation iobroker-0 -- sh -c 'iob list instances | grep -c "system.adapter"'   # expect 3
kubectl exec -n home-automation iobroker-0 -- sh -c 'grep "\"version\"" /opt/iobroker/node_modules/iobroker.js-controller/package.json'   # expect 7.0.6
kubectl exec -n home-automation iobroker-0 -- sh -c 'node -v'                                          # expect v24.21.0
# 3b. G7 baseline: error-class lines in the REAL log (container stdout only holds the entrypoint banner, 2 lines in 3 days)
kubectl exec -n home-automation iobroker-0 -- sh -c 'grep -c -i -E "error|uncaught|ERR_MODULE|EACCES" /opt/iobroker/log/iobroker.current.log; readlink /opt/iobroker/log/iobroker.current.log; date "+%F %T"'
#    RECORD as G7_BASE (measured 2026-11-15: 0, file iobroker.2026-11-15.log, 80 bytes). Also record the symlink target and in-pod time.
kubectl exec -n home-automation iobroker-0 -- sh -c 'curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8081/'  # expect 200
kubectl get pod iobroker-0 -n home-automation -o jsonpath='{.status.containerStatuses[0].restartCount}{"\n"}'  # baseline N (was 2)
# 4. Fresh app-level backup into the PVC (the app's own command; in-pod write to its own backup dir)
kubectl exec -n home-automation iobroker-0 -- sh -c 'cd /opt/iobroker && iobroker backup 2>&1 | tail -3; ls -t backups | head -2'
#    RECORD the NEWEST file name printed here as PRE_BACKUP (the file `iobroker backup` just wrote). The scheduled backitup tar
#    (iobroker_YYYY_MM_DD-02_48_10_backupiobroker.tar.gz, e.g. the 2026-11-15 02:48 one) also sits in backups/ and is NOT this file.
# 5. Verify the target digest exists
curl -s "https://hub.docker.com/v2/repositories/buanet/iobroker/tags/v12.0.0" | python3 -c "import sys,json;print(json.load(sys.stdin)['digest'])"   # expect sha256:005ba9c2...
# 6. Silence + marker per docs/sops/application-update.md Step 1 (4h TTL), namespace home-automation
runbooks/update-marker.sh add iobroker home-automation 2 "v12.0.0 digest 46b7b46->005ba9c"
```
If pre-check 5 prints a different digest, Renovate's PR is stale (upstream rebuilt again): refresh
this plan's `target:` before continuing. If pre-check 2 shows a backup older than 24h, stop.

## 3. Steps

Digest-only change; no `retries: 0` override needed (StatefulSet, 1 replica; `upgrade.remediation.retries: 1`
would roll back a failed upgrade, which is the desired safety here).

1. Edit `kubernetes/apps/home-automation/iobroker/app/helm-release.yaml`, line `tag: v12.0.0@sha256:46b7b467...`:
   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   python3 - <<'PY'
   p = "kubernetes/apps/home-automation/iobroker/app/helm-release.yaml"
   s = open(p).read()
   old = "46b7b467244ef54bf4f1faadad988a630f94aff16613d4a3a0c161e72ad8808a"
   new = "005ba9c285887d2ca13dad94aab75a93bf2fea1c5016c6f54802c4e1c4fb0a27"
   assert s.count(old) == 1, s.count(old)
   open(p, "w").write(s.replace(old, new))
   PY
   git diff --stat -- kubernetes/apps/home-automation/iobroker/app/helm-release.yaml   # 1 line changed
   ```
   (Not dry-tested on a scratch copy; the assert makes a miss fatal. Renovate's own diff on PR #352 is the
   same single line, so merging the PR is an equivalent alternative.)
2. Commit exactly that path and push (shared worktree: `git commit --only`, then `git log -1 --format=%s`):
   ```bash
   git commit --only kubernetes/apps/home-automation/iobroker/app/helm-release.yaml -F <msgfile>
   git show --stat HEAD && git log -1 --format=%s && git push origin main
   ```
   Commit subject must carry no media titles/CVE ids. Close PR #352 afterwards if committed directly.
3. Let the Flux webhook reconcile (no manual reconcile). Watch:
   `kubectl get pod iobroker-0 -n home-automation -w` until 1/1 Running (startup probe budget 15 min).

## 4. Verification

CONTROL: kubectl objects (live API) for G1-G4; the pod's own log file for G7. G5 (Prometheus
`kube_statefulset_status_replicas_ready`) is INFORMATIONAL only: it restates G3/G1 and does not gate, so a
same-night `kube-prometheus-stack-93.3.0` bump neither blocks this plan nor is blocked by it (if it
disagrees with G3, note it, do not fail). No alert in `ALERTS{namespace="home-automation"}` fired on
2026-11-14 (empty result), so a firing one afterwards is attributable.

| Gate | Command | PASS | What FAIL looks like |
|---|---|---|---|
| G1 spec moved | `kubectl get sts iobroker -n home-automation -o jsonpath='{.spec.template.spec.containers[0].image}'` | contains `sha256:005ba9c285887d2c` | still `46b7b467...`: reconcile did not apply (HR stalled/rolled back) |
| G2 LIVE pod runs it (not the old generation) | `kubectl get pod iobroker-0 -n home-automation -o jsonpath='{.status.containerStatuses[0].imageID}'` | ends `sha256:005ba9c2...` | old imageID or empty; `rollout status` alone green-lights the old pod, so this is the real check |
| G3 pod ready, no crash loop | `kubectl get pod iobroker-0 -n home-automation -o jsonpath='{.status.containerStatuses[0].ready}{" "}{.status.containerStatuses[0].restartCount}'` | `true 0` (fresh pod, count resets) | `false`, or restartCount >= 1 within 10 min |
| G4 CONTENTS ASSERTION: the app's data and controller are intact | in pod: `iob list instances \| grep -c system.adapter` ; `iob status` ; js-controller version ; `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8081/` | `3`, `iobroker is running on this host.`, `7.0.6` (any change is reported and judged, not auto-failed), `200` | `0` or missing adapters (data dir not read), `iobroker is not running`, curl 000/5xx (admin dead while the port-only probe is green) |
| G5 (informational, non-gating) metric agrees | Prometheus: `kube_statefulset_status_replicas_ready{namespace="home-automation",statefulset="iobroker"}` | `1` | `0` with G3 true = scrape disagrees; record and investigate, does not fail the plan |
| G6 public route | from the Mac: `curl -s -o /dev/null -w "%{http_code}" https://iobroker.<DOMAIN>/` (host from the HTTPRoute, not committed) | 200 or the app's login redirect (not 503) | 503 from Envoy = no ready backend |
| G7 admin log has no new errors | `kubectl exec -n home-automation iobroker-0 -- sh -c 'grep -c -i -E "error\|uncaught\|ERR_MODULE\|EACCES" /opt/iobroker/log/iobroker.current.log'` (run >= 5 min after G3 true; first confirm `readlink /opt/iobroker/log/iobroker.current.log` equals the pre-check 3b target) | count <= G7_BASE (pre-check 3b). The pod appends to the same date-named file, so everything above the baseline was written after the restart. If the symlink target changed (day rollover), the new file is all post-baseline: PASS = count 0 in it, or judge each line | count > G7_BASE: new error-class lines since the baseline (print them with the same grep without `-c`). The old gate read `kubectl logs`, which holds only the entrypoint banner and could never fail. REPLAYED on scratch logs 2026-11-15: clean file -> 0 (PASS), file with 4 appended error-class lines -> 4 > 0 (FAIL), and `echo 'ERROR x' \| grep -c -i -E ...` -> 1, so the mixed-case pattern does match. Measured live: the real log is 80 bytes today (info only) |

Follow-up, NOT a window gate: the morning after the roll, `ls -t /opt/iobroker/backups | head -1` in the pod should show a
newer 02:48 backitup tar than the pre-roll one (catches backitup breaking on the new image). The operator or next sweep checks it.

Then drop the update marker: `runbooks/update-marker.sh` removal per the SOP, and delete the silence.

## 5. Rollback

1. `git revert <commit> --no-edit` (the one-line digest change) and push; Flux re-pins `46b7b467...`
   (the old digest stays on Docker Hub as a content-addressed manifest, so it remains pullable;
   confirm with `docker manifest inspect buanet/iobroker@sha256:46b7b467...` before the window).
2. Confirm: G1/G2 with the OLD digest, G3, G4 again.
3. If the new image altered the PVC on boot so the OLD image will not start (nothing expected, but the
   entrypoint writes into the volume): restore the data volume, NOT blindly. Preferred order:
   (a) the file pre-check 4 produced (PRE_BACKUP, the newest name printed by `iobroker backup`, taken just before
   the roll; NOT the 02:48 backitup tar, which is up to a day older and is only the fallback if PRE_BACKUP is missing): in the pod,
   `cd /opt/iobroker && iobroker restore <PRE_BACKUP>` (kept in `/opt/iobroker/backups`);
   (b) if the pod will not start at all: Longhorn restore of `iobroker-config` from the newest Completed
   backup (`kubectl get backups.longhorn.io -n storage`, label `backup-volume=iobroker-config`;
   the volume is static `longhorn-static`, PV/PVC/volume all named `iobroker-config`; follow
   `docs/sops/longhorn.md` and the storage-safety rules, it is Longhorn not CIFS so the CIFS delete
   pre-flight does not apply). Loss window up to ~24h of iobroker state; acceptable for 3 idle adapters.
4. A Flux auto-rollback (`upgrade.remediation.retries: 1`) may already have reverted a failing upgrade;
   check `helm history iobroker -n home-automation` before acting.

## 6. Interference notes

- **Does it need an attended window? No.** Low risk, git-revert rollback, no consumer found, nothing
  shared restarted. It is eligible for the unattended `nightly` (03:30 Europe/Berlin) window once a
  plan-reviewer verdict sets `review: ready-for-go@...` (SD-10 requires that; `review` is null now).
  If the operator wants zero surprise, an attended Saturday also works: nothing about it needs a reboot.
  Avoid 02:48 Berlin (backitup run) and 23:00 UTC (Longhorn nightly backup) overlapping the pod down time.
- `conflicts_with` carries the serialization above. `kube-prometheus-stack-93.3.0` is deliberately NOT listed: G5 is
  informational, so no gate depends on Prometheus. Reciprocal awareness: that plan's frontmatter does not name this
  plan (checked 2026-11-15) and is not edited here; it needs no entry unless a Prometheus-reading gate is added.
  Serialize against any node roll (`talos-linux-1.14.5`): the pod's Longhorn replicas are on two nodes and the pod itself on k8s-nuc14-03.
- Other workloads in `home-automation` (home-assistant, mosquitto, node-red, esphome, matter-server,
  frigate) are untouched. No NetworkPolicy exists in the namespace.
- Open question for the reviewer: the Service/route still expose ports for adapters that are not
  installed (vis, node-red, mqtt, nuki, alexa). Not this plan's job, but a candidate cleanup.
