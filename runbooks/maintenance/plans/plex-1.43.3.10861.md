---
plan_id: plex-1.43.3.10861
component: plex
pr: null                          # coverage.py PLAN lane (version-type unknown); no open Renovate PR captured
kind: image
current: "1.43.3.10828-00f62d37d"
target: "1.43.3.10861-07dfddaeb"
update_type: patch                # PMS build bump within 1.43.3 (10828 → 10861); non-semver scheme
risk: low
est_duration_min: 15
needs_reboot: false
touches:
  namespaces: [media]
  resources:
    - helmrelease/plex
    - statefulset/plex-plex-media-server        # single replica; pod plex-plex-media-server-0
    - service/plex-plex-media-server            # LoadBalancer 192.168.55.30:32400 (Cilium LB-IPAM)
    - ingress/plex                              # internal ingressClass → plex.${SECRET_DOMAIN}
    - pvc/plex-config                           # longhorn-static, 10Gi — SQLite library DB (read/remount only)
  shared: []                                    # perturbs no shared cluster infra; CIFS media PVC is NOT touched
depends_on: []
conflicts_with: []                              # soft: do not co-schedule with ingress-nginx-1.15.6 / an Envoy-Gateway
                                                # cutover (transiently drops the plex.${DOMAIN} web path) — see Interference
status: draft
window: "tue-early:2026-08-25"       # MOVED 2026-08-15: tue-early:2026-08-18 held 70m of work
                                      # (librechat 30 + nextcloud-mcp 25 + plex 15) in a 60m
                                      # window. plex is the smallest and has no depends_on, so
                                      # moving it costs least; 08-25 then holds absenty 45 +
                                      # plex 15 = exactly 60m.
                                      # only — no overlap with the other tue-early plans.
auto_execute: false
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/storage-safety.md
  - docs/sops/longhorn.md
generated: "2026-08-12"
---

# plex 1.43.3.10828 → 1.43.3.10861

## 1) Summary & why held

Routine Plex Media Server build bump, same 1.43.3 line, build `10828-00f62d37d`
→ `10861-07dfddaeb` (image `plexinc/pms-docker`). Target multi-arch tag verified
present on Docker Hub (amd64 variant exists).

**Why held (not a real breaking change):** `coverage.py` could not prove it
safe — the PMS tag scheme (`<maj>.<min>.<patch>.<build>-<hash>`) is not semver,
so the "version-type" is *unknown* and it fell into the **PLAN** lane rather than
AUTO. There is no upstream migration/breaking-change signal for this build; the
hold is essentially a classifier false-positive on the tag format.

It still belongs in a window (not a blind auto-merge) because **Plex is a shared,
stateful media workload**:
- Single-replica StatefulSet (`plex-plex-media-server-0`) — the tag change rolls
  the pod, which **interrupts every active playback session** (no second replica
  to drain to).
- The library metadata lives in a **SQLite DB** on the `plex-config`
  (`longhorn-static`, 10Gi) volume. A new PMS build can run a schema
  migration / integrity check on first start; a corrupt or interrupted upgrade
  can leave the DB in maintenance/repair. So we restart with session awareness
  and a known-good Longhorn backup in hand.

**Blast radius is small:** image-tag-only change. The CIFS media library
(`plex-media-smb`, class `cifs-plex-media`, `reclaimPolicy: Retain`) is **only
remounted, never modified or deleted** — storage-safety rules are not exercised
by this plan. No shared cluster infra (ingress-controller, cilium, coredns,
cert-manager, longhorn) is perturbed.

## 2) Pre-checks

```bash
export KUBECONFIG=${KUBECONFIG:-$HOME/.kube/config}

# a) Cluster + Flux healthy, no in-flight reconcile fighting us
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
flux get helmreleases  -n media | awk 'NR==1 || $4 != "True"'
kubectl get pods -n media -l app.kubernetes.io/instance=plex

# b) Current pod / image (record for rollback)
kubectl get statefulset plex-plex-media-server -n media \
  -o jsonpath='image={.spec.template.spec.containers[0].image}{"\n"}'
#   expect …/pms-docker:1.43.3.10828-00f62d37d

# c) Library DB backup is FRESH (nightly Longhorn backup CronJob @ 03:00).
#    plex-config volume must be healthy + backed up within ~24h.
kubectl get volume plex-config -n storage \
  -o jsonpath='robustness={.status.robustness} lastBackup={.status.lastBackupAt}{"\n"}'
#   robustness=healthy AND lastBackup within the last day → GO. If stale, take a
#   fresh Longhorn backup of plex-config before proceeding (docs/sops/longhorn.md).

# d) ACTIVE-SESSION DRAIN CHECK — do not roll while people are watching.
POD=plex-plex-media-server-0
TOKEN=$(kubectl exec -n media $POD -c plex-media-server -- \
  sh -c "grep -o 'PlexOnlineToken=\"[^\"]*\"' '/config/Library/Application Support/Plex Media Server/Preferences.xml'" \
  | sed 's/.*="//;s/"//')
kubectl exec -n media $POD -c plex-media-server -- \
  sh -c "wget -qO- 'http://localhost:32400/status/sessions?X-Plex-Token=$TOKEN'" | grep -c '<Video\|<Track\|<Session'
#   0 → safe to proceed. >0 → active playback; defer to a lower-usage moment in
#   the window, or confirm go with the operator (streams WILL be cut).
```

## 3) Steps (GitOps — copy-pasteable)

```bash
cd /Users/mu/code/cberg-home-nextgen
export KUBECONFIG=${KUBECONFIG:-$HOME/.kube/config}

# 1) Mark active-update so alert-triage-agent treats the restart noise as EXPECTED
runbooks/update-marker.sh add plex media 1 "1.43.3.10828 -> 1.43.3.10861 build bump"

# 2) (optional, belt-and-suspenders) short silence for the rollout window
kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 &
NOW=$(python3 -c "from datetime import *;print(datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
END=$(python3 -c "from datetime import *;print((datetime.now(timezone.utc)+timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
curl -s -X POST localhost:9093/api/v2/silences -H 'Content-Type: application/json' -d '{
  "matchers":[{"name":"namespace","value":"media","isRegex":false,"isEqual":true},
              {"name":"alertname","value":"Kube(Pod|StatefulSet).*","isRegex":true,"isEqual":true}],
  "startsAt":"'$NOW'","endsAt":"'$END'","createdBy":"maintenance-window",
  "comment":"plex 1.43.3.10861 build bump — rollout noise. auto-expires 1h"}'
```

3) **Edit the image tag** in
`kubernetes/apps/media/plex/app/helmrelease.yaml` (single line, `spec.values.image.tag`):

```yaml
    image:
      repository: plexinc/pms-docker
      tag: 1.43.3.10861-07dfddaeb   # was 1.43.3.10828-00f62d37d
      pullPolicy: IfNotPresent
```

4) **Commit + push** (Flux webhook reconciles; HelmRelease interval 30m, so force
if you don't want to wait):

```bash
git add kubernetes/apps/media/plex/app/helmrelease.yaml
git commit -m "chore(plex): bump image 1.43.3.10828 → 1.43.3.10861 (build bump)"
git push
flux reconcile helmrelease plex -n media --with-source   # optional: don't wait for the 30m interval
```

No rollback-disable / Deployment-delete dance is needed: this is a StatefulSet
image-tag bump (not a chart relabel), so the pod rolls in place and reuses the
same `plex-config` PVC. Leave `upgrade.remediation.retries: 3` as-is.

## 4) Verification

```bash
export KUBECONFIG=${KUBECONFIG:-$HOME/.kube/config}
POD=plex-plex-media-server-0

# a) HelmRelease reconciled + Ready
kubectl get hr plex -n media \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'   # True

# b) Pod rolled to new image, Ready 1/1, stable (0 restarts after settle)
kubectl get pod $POD -n media -o jsonpath='{.spec.containers[0].image}{"\n"}'
#   …/pms-docker:1.43.3.10861-07dfddaeb
kubectl get pod $POD -n media

# c) PMS answering (readiness/liveness hits /identity already, confirm explicitly)
kubectl exec -n media $POD -c plex-media-server -- wget -qO- http://localhost:32400/identity | head -c 300

# d) LIBRARY DB INTACT — sections enumerate + no DB corruption in logs
TOKEN=$(kubectl exec -n media $POD -c plex-media-server -- \
  sh -c "grep -o 'PlexOnlineToken=\"[^\"]*\"' '/config/Library/Application Support/Plex Media Server/Preferences.xml'" \
  | sed 's/.*="//;s/"//')
kubectl exec -n media $POD -c plex-media-server -- \
  sh -c "wget -qO- 'http://localhost:32400/library/sections?X-Plex-Token=$TOKEN'" | grep -o 'title="[^"]*"'
#   expect the movie/TV/music libraries listed (same as before the bump)
kubectl logs -n media $POD -c plex-media-server --tail=200 | grep -iE 'database|corrupt|integrity|migrat' | tail -20
#   expect a normal startup / "database is OK"; NO "database disk image is malformed"

# e) TEST STREAM (operator): open plex.${SECRET_DOMAIN} (or the LB IP 192.168.55.30:32400)
#    and play one title. Confirm playback starts AND a transcode uses the Intel
#    iGPU (HardwareAcceleratedCodecs) — check for "using hardware accelerated"
#    in the logs and that the /dev/dri mount is present:
kubectl exec -n media $POD -c plex-media-server -- ls -l /dev/dri
kubectl logs -n media $POD -c plex-media-server --tail=100 | grep -i 'hardware' | tail -5

# f) Homepage tile green (ingress annotations unchanged) + service LB IP intact
kubectl get svc plex-plex-media-server -n media -o jsonpath='lb={.status.loadBalancer.ingress[0].ip}{"\n"}'  # 192.168.55.30
```

On success: drop the silence (`curl -s -X DELETE localhost:9093/api/v2/silences/<id>`)
and clear the marker: `runbooks/update-marker.sh clear plex`.

## 5) Rollback

Image-tag revert (fast path — the SQLite DB is forward/back compatible across a
same-minor build in the overwhelming majority of cases):

```bash
cd /Users/mu/code/cberg-home-nextgen
# restore the known-good tag
git checkout HEAD~1 -- kubernetes/apps/media/plex/app/helmrelease.yaml   # or edit tag back to 1.43.3.10828-00f62d37d
git commit -m "revert(plex): back to 1.43.3.10828 (rollout verification failed)"
git push
flux reconcile helmrelease plex -n media --with-source
# confirm restored
kubectl get pod plex-plex-media-server-0 -n media -o jsonpath='{.spec.containers[0].image}{"\n"}'   # …10828-00f62d37d
kubectl exec -n media plex-plex-media-server-0 -c plex-media-server -- wget -qO- http://localhost:32400/identity | head -c 200
# then re-run Verification (d) + (e): library sections enumerate + a test stream plays
```

**If the library DB was damaged by the new build** (Verification (d) shows
"malformed" / stuck in DB repair and a tag-revert does not clear it): restore the
`plex-config` volume from the fresh nightly Longhorn backup per
`docs/sops/longhorn.md`. Scale the StatefulSet to 0 first
(`kubectl scale statefulset plex-plex-media-server -n media --replicas=0`),
restore the volume, scale back to 1. **Never delete the CIFS `plex-media-smb`
PVC** during any recovery (class `cifs-plex-media`, catastrophic per
`docs/sops/storage-safety.md`) — the library DB, not the media files, is what a
bad build touches.

## 6) Interference notes

- **Single-replica restart = hard stream cut.** There is no drain; the running
  pod is replaced. The pre-check active-session query gates this — run the bump
  when sessions are 0 (a low-usage weekday 05:00 window is ideal).
- **Config DB lives on `longhorn-static`.** Do NOT co-schedule this with a
  Longhorn/storage-disruptive plan or a node-reboot plan in the same window — a
  Longhorn volume-engine restart or a node reboot while PMS is mid DB-migration
  is the one way this low-risk bump turns into a DB-repair incident. This plan is
  `needs_reboot: false` and should go to a Tue/Thu/Sat no-reboot slot, never the
  Sun reboot window alongside Talos.
- **Ingress consumer, not perturber.** Plex is reachable via the `internal`
  ingressClass (`plex.${SECRET_DOMAIN}`) AND directly on LB IP
  `192.168.55.30:32400`. This bump does not touch the ingress controller, but a
  co-scheduled `ingress-nginx-1.15.6` upgrade or an Envoy-Gateway cutover would
  transiently drop the web path and confound the test-stream verification. Prefer
  a different window from those; if they must share, sequence the ingress change
  first and verify Plex last.
- **Media-namespace co-tenancy.** `jellyfin`, `immich`, `makemkv`,
  `library-tools` share the `media` namespace and the `//NAS/media` CIFS share.
  This image bump touches none of their resources and does not modify the share,
  so there is no data interference — but avoid running the
  `library-tools`/`plex-fs-classifier` cronjob-triggered rescans or a
  media-manager library scan against Plex during its restart (transient
  connection errors only, not data risk).
- **GPU device.** The pod requests `gpu.intel.com/i915` (Intel iGPU via the node
  device plugin) and hostPath `/dev/dri`. The replacement pod must reschedule
  onto a node with a free i915 slot; if it lands Pending on the GPU request,
  that's the failure mode to watch, not the image itself.
