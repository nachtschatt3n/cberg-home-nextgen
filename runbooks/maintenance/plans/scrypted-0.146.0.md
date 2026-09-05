---
plan_id: scrypted-0.146.0
component: scrypted
pr: null                          # no Renovate PR number given/found (gh pr search: none open)
kind: image
current: "v0.143.0-noble-full"
target: "v0.146.0-noble-full"
update_type: n/a                  # this plan documents a HOLD decision, not an upgrade to execute
risk: medium                      # reflects what executing the bump WOULD be, not "doing nothing"
est_duration_min: 25              # only relevant if/when the hold condition clears (see §3)
needs_reboot: false
touches:
  namespaces: [home-automation]
  resources: [helmrelease/scrypted, deployment/scrypted, pvc/scrypted-data, pvc/scrypted-media]
  shared: []                      # no shared infra RECONFIGURED; intel-device-plugin-gpu is a
                                  # dependency (see Interference notes) but nothing here changes it
depends_on: []
conflicts_with: []
security_ref: null
capability_change: false
rollback_class: git-revert
finding_refs: []
status: draft
window: null
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/storage-safety.md
generated: "2026-09-05"
---

## 1. Summary & why held — VERDICT: DO NOT UPGRADE YET, hold confirmed correct

The auto-updater held `koush/scrypted:v0.146.0-noble-full` because it reads as
upstream's pre-release channel. **Investigated and confirmed: the hold is
correct, not a false positive.** Recommendation is to leave this update HELD.

Evidence:

- The `v0.146.0-noble-full` tag **exists and is pullable** on Docker Hub
  (pushed 2026-09-02T16:09Z, multi-arch amd64+arm64, digest
  `sha256:054a7ba8...` / `sha256:bd651cd2...`) — so this is not a typo'd or
  unpublished tag.
- But **koush/scrypted has no GitHub Release for `v0.146.0` at all** — the
  release list jumps `v0.143.0` (2025-10-28, `prerelease:false`) straight to
  `v0.145.0` (2026-09-02, `prerelease:false`). Checked via
  `api.github.com/repos/koush/scrypted/releases`.
- This matches a consistent recent pattern (verified across the last 10
  release cycles, v0.127 through v0.145): **every version that gets a formal,
  non-prerelease GitHub Release has an ODD minor number.** Even-numbered
  minors (`v0.142.x`, `v0.144.0/.1/.3`, and now `v0.146.0`) are pushed to
  Docker Hub as interim/development builds between stable cuts, with no
  corresponding Release entry — i.e. exactly upstream's pre-release/dev
  channel, just not labeled that way in the tag string (a known upstream gap:
  [koush/scrypted#1887](https://github.com/koush/scrypted/issues/1887), still
  open, no fix shipped).
- Release notes for `v0.145.0` (the current stable) list TypeScript
  strict-mode migration, HomeKit/Reolink/Alexa/Unifi-Protect bugfixes, and a
  Node.js bump to 22.21.0 — no explicit breaking changes for our config, but
  that release note is for the version we are NOT bumping to. **No release
  notes exist yet for whatever will ship as `v0.147.0`** (the next expected
  odd/stable cut), which is the version `v0.146.0`'s changes will actually
  land under — so there is nothing yet to audit for breakage.

**Release condition (re-check this before every window that surfaces this
plan):**

```bash
curl -s "https://api.github.com/repos/koush/scrypted/releases?per_page=5" | \
  python3 -c "import sys,json; [print(r['tag_name'], r['prerelease']) for r in json.load(sys.stdin)]"
```

Ship this update only when ONE of these becomes true:
1. A GitHub Release for `v0.146.x` or later appears with `prerelease: false`
   (i.e. upstream breaks its own odd/even pattern and promotes this line), or
2. The next odd release (expected `v0.147.0`) is cut as `prerelease: false`
   — at that point re-run this planner against the NEW target tag
   (`v0.147.0-noble-full`), not this one, since `v0.146.0` itself will remain
   a superseded dev build. **Retire this plan file at that point rather than
   editing it to a new target** — same convention as any executed/obsoleted
   plan (see `runbooks/maintenance/plans/README.md`).

**Adjacent, cheaper option worth flagging separately (NOT part of this
plan):** `v0.145.0-noble-full` is *already* the current stable release
(`prerelease:false`, confirmed pullable, HTTP 200) and is newer than the
cluster's current `v0.143.0-noble-full` with no documented breaking changes
for our setup. If the operator wants to move scrypted forward now rather than
wait out `v0.146.0`, the safe path is a **new, separate** update targeting
`v0.143.0 → v0.145.0-noble-full` — that should get its own plan/PR, not be
folded into this one silently (this plan's `target` must stay truthful to the
held update it was dispatched for).

## 2. Blast radius / why this is `risk: medium` even though nothing runs today

Scrypted is live camera/NVR infrastructure with real hardware coupling, so the
risk rating reflects what executing a bump here would cost, for whenever the
hold clears:

- **Privileged pod**: `securityContext.privileged: true`, `SYS_ADMIN`,
  `runAsUser: 0` — full container capability, not a sandboxed app.
- **Hardware passthrough**: `hostPath /dev/dri` + `gpu.intel.com/i915: 1`
  request/limit for hardware transcoding. The iGPU is **shared** with
  Jellyfin, Plex, Frigate, Immich-ML, and MakeMKV via the cluster-wide
  `intel-device-plugin-gpu` (see `docs/applications.md` device-plugin row).
  This plan does not touch that plugin, but the Kustomization has an explicit
  `dependsOn: intel-device-plugin-gpu` — if that plugin is unhealthy, Flux
  won't reconcile scrypted at all (pre-check below).
- **Restart cost — lost recording window**: this is a single-replica
  Deployment (`strategy` is chart default; not `Recreate`-pinned in values,
  worth verifying at execution time per the Longhorn RWO-multi-attach SOP even
  though `scrypted-media` is CIFS/RWX and immune — `scrypted-data` is
  `longhorn` dynamic RWX too, so multi-attach is not the risk here). The real
  cost is that **any camera actively recording through Scrypted stops
  recording for the pod's downtime** (image pull + container start, typically
  30-90s for a ~1GB `-full` image already cached on the node, longer on a
  cold pull). There is no HA/failover for NVR recording during that window —
  this is a real, if short, coverage gap, not just an "app was briefly down"
  blip.
- **Storage**: `scrypted-media` is CIFS (`cifs-scrypted-media`,
  `//NAS/scrypted`, `subdir: /media`, `reclaimPolicy: Retain`) — confirmed in
  `docs/sops/storage-safety.md` "Severe" tier (would wipe one app's data if
  reclaim were ever `Delete`; it is not). **This plan does not delete, resize,
  or touch this PVC in any way** — it is an image-tag bump only. No
  storage-safety pre-flight is triggered because no PVC delete is planned;
  the CIFS mount is noted here purely so the window agent knows what NOT to
  touch.
- **No DB, no schema migration**: scrypted has no external DB dependency in
  this deployment; `docs/sops/backup.md` does not apply.

## 3. Pre-checks (run only once the release condition in §1 is met)

```bash
# 1. Re-confirm the release condition (see §1) — do not proceed if still pre-release-only.

# 2. Confirm the NEW target tag you're actually bumping to (v0.147.x by then) exists:
curl -s "https://hub.docker.com/v2/repositories/koush/scrypted/tags/<new-target-tag>" \
  -o /dev/null -w '%{http_code}\n'   # expect 200

# 3. Confirm intel-device-plugin-gpu is healthy (hard Kustomization dependsOn):
kubectl get pods -n kube-system -l app.kubernetes.io/name=intel-device-plugin-gpu
flux get kustomization -n flux-system intel-device-plugin-gpu

# 4. Confirm current Flux/HR state is clean before touching it:
flux get helmrelease -n home-automation scrypted
kubectl get pods -n home-automation -l app.kubernetes.io/name=scrypted

# 5. Note which cameras are actively recording RIGHT NOW so post-upgrade you can
#    confirm they resumed (see §5 contents assertion) — from the Scrypted UI
#    (https://scrypted.${SECRET_DOMAIN}) or:
kubectl exec -n home-automation deploy/scrypted -- ls -la /media 2>/dev/null | tail -5

# 6. Silence expected rollout noise (per docs/sops/application-update.md §Step 1):
kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 &
NOW=$(python3 -c "from datetime import *;print(datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
END=$(python3 -c "from datetime import *;print((datetime.now(timezone.utc)+timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
curl -s -X POST localhost:9093/api/v2/silences -H 'Content-Type: application/json' -d '{
  "matchers":[{"name":"namespace","value":"home-automation","isRegex":false,"isEqual":true},
              {"name":"alertname","value":"Scrypted.*|Kube(Pod|Deployment).*","isRegex":true,"isEqual":true}],
  "startsAt":"'$NOW'","endsAt":"'$END'","createdBy":"operator",
  "comment":"scrypted image bump — suppressing rollout noise. auto-expires 2h"}'
runbooks/update-marker.sh add scrypted home-automation 2 "scrypted image bump"
```

## 4. Steps (execute ONLY once §1's release condition is actually met)

1. Re-verify the exact target tag against the pattern in §1 — do not reuse
   `v0.146.0-noble-full` unless it specifically gained a non-prerelease
   Release; more likely you are bumping to whatever the next odd release is
   (e.g. `v0.147.0-noble-full`). Confirm that tag string exists (§3 step 2).
2. Edit `kubernetes/apps/home-automation/scrypted-nvr/app/helmrelease.yaml`:
   ```yaml
   containers:
     app:
       image:
         repository: koush/scrypted
         tag: <new-target-tag>          # e.g. v0.147.0-noble-full
   ```
3. Commit + push (GitOps only — no direct cluster edit):
   ```bash
   git commit --only kubernetes/apps/home-automation/scrypted-nvr/app/helmrelease.yaml \
     -m "feat(scrypted): bump <old-tag> -> <new-target-tag> (stable release, was held for pre-release channel)"
   git push
   ```
4. Watch the reconcile (no manual `flux reconcile --force` needed — the
   HelmRelease has a 30m interval and `reloader.stakater.com/auto: "true"`
   already fires on annotation/config changes, but the image tag change flows
   through the HelmRelease values directly, so Flux's normal interval/webhook
   reconcile picks it up):
   ```bash
   flux get helmrelease -n home-automation scrypted --watch
   kubectl get pods -n home-automation -l app.kubernetes.io/name=scrypted -w
   ```
5. Do not hand-delete the pod mid-rollout; let the chart's own update strategy
   run. If it wedges, follow `docs/sops/application-update.md` §7
   troubleshooting table before improvising.

## 5. Verification

Floor (shape checks — necessary but not sufficient):
```bash
kubectl get helmrelease -n home-automation scrypted \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'
kubectl get pods -n home-automation -l app.kubernetes.io/name=scrypted
kubectl get pods -n home-automation -l app.kubernetes.io/name=scrypted \
  -o jsonpath='{.items[0].status.containerStatuses[0].imageID}{"\n"}'   # prove NEW bytes, not just tag string
```

**CONTENTS ASSERTION (required — a Ready pod proves the container started, not
that recording resumed):** compare the newest file mtime under the CIFS
`scrypted-media` mount for each camera that was actively recording per §3
step 5, taken AFTER the pod settles, against a timestamp taken BEFORE the
restart. A camera that was recording pre-upgrade must show a file newer than
the restart time within one recording-segment interval (check the segment
length configured per-camera in the Scrypted UI; if unknown, allow 5 minutes):
```bash
kubectl exec -n home-automation deploy/scrypted -- \
  find /media -type f -newermt '<restart-timestamp>' -printf '%TY-%Tm-%Td %TH:%TM %p\n' | sort | tail -20
```
A Ready pod with zero new files past the restart timestamp for a
previously-active camera is a FAIL — recording silently did not resume (e.g.
lost RTSP re-auth, plugin incompatibility with the new base image), even
though every shape check above is green.

Also spot-check the Scrypted web UI (`https://scrypted.${SECRET_DOMAIN}`)
reports the new version string in Settings, and that at least one camera's
live view actually renders a frame (not just "connected").

## 6. Rollback

```bash
git log --oneline -- kubernetes/apps/home-automation/scrypted-nvr/app/helmrelease.yaml | head -5
git checkout <pre-bump-commit> -- kubernetes/apps/home-automation/scrypted-nvr/app/helmrelease.yaml
git commit -m "revert(scrypted): back to v0.143.0-noble-full — <reason>"
git push
flux reconcile helmrelease -n home-automation scrypted --force   # only if interval hasn't fired yet
```
Confirm rollback landed by `imageID` (not tag), same command as §5. Then
delete the Alertmanager silence early and clear the update marker:
```bash
curl -s -X DELETE localhost:9093/api/v2/silences/<id>
runbooks/update-marker.sh clear scrypted
```

## 7. Interference notes

- **Hard dependency, not shared perturbation**: `ks.yaml` sets
  `dependsOn: intel-device-plugin-gpu` (kube-system). This plan does not
  change that plugin, but the window agent should not schedule this alongside
  any plan that touches/restarts `intel-device-plugin-gpu` itself — if that
  dependency Kustomization is mid-reconcile or unhealthy, this HelmRelease
  will not apply.
- **iGPU is a shared, non-Kubernetes-tracked resource**: Jellyfin, Plex,
  Frigate, Immich-ML, and MakeMKV all request `gpu.intel.com/i915` too. The
  device-plugin's resource count is about scheduling slots, not concurrent
  hardware transcode session limits — if another app is pushing heavy
  transcode load at the same moment scrypted restarts and re-establishes
  camera streams, expect transient transcode failures unrelated to this
  bump. Prefer a quiet window for other GPU-heavy apps if one can be chosen.
- **No storage action of any kind planned** — `scrypted-media` (CIFS,
  `Retain`, `subdir: /media`, "Severe" tier per storage-safety.md) and
  `scrypted-data` (Longhorn dynamic) are both left completely alone. If a
  future version of this plan ever needs a PVC action, the storage-safety
  3-step pre-flight applies in full.
- **Do not conflate with a v0.145.0 bump**: if the operator separately
  approves moving to `v0.145.0-noble-full` (see §1 "adjacent option"), that
  must be tracked as its own plan file/PR with its own `target:` — do not
  edit this file's `target` to `v0.145.0-noble-full` to "make progress"; that
  would misrepresent what was actually held and investigated here.
- **Biggest gotcha for whoever revisits this**: the tempting shortcut is
  "a newer tag than v0.146.0 exists on Docker Hub, ship the newest one." Don't
  — re-run the release-condition check in §1 fresh every time; the odd/even
  pattern means there is very likely ANOTHER even-numbered dev build (e.g.
  `v0.148.0`) sitting on Docker Hub by the time this is revisited, and it is
  just as much pre-release as `v0.146.0` is today.
