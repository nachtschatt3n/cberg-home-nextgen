---
plan_id: dashcast-1.6.48
component: dashcast
pr: 578                               # open Renovate PR is v1.6.46 -> v1.6.49 (supersedes 1.6.48; see section 1.3). No PR exists for 1.6.48 itself.
kind: image
current: "v1.6.46@sha256:6c780d5d06b5d022caafda0a0bbbc6f87fda9c00b460bc85a44b16ff59870465"
target: "v1.6.48@sha256:d4ef60f9deed182a483a585fa14a198401d2b78a00000ac6cdb8dcbb5be8d96a"
update_type: patch                    # 1.6.46 -> 1.6.48, same minor line
risk: low                             # stateless (emptyDir only), 1 replica, LAN-only TCP service, git-revert rollback;
                                      # server diff is ~60 lines of optional env parsing, defaults identical (section 1.1)
est_duration_min: 15
needs_reboot: false
touches:
  namespaces: [home-automation]
  resources:
    - helmrelease/dashcast            # values.controllers.dashcast.containers.app.image.tag
    - deployment/dashcast             # pod replaced; default RollingUpdate, no PVC so no Multi-Attach risk
    - service/dashcast                # LoadBalancer 192.168.55.32:9555, unchanged
    - prometheusrule/dashcast-alerts  # read only (ns monitoring): the three alerts are the failure instrument
  shared: [monitoring]                # verification reads Prometheus; no HTTPRoute, Authentik, Gateway or Longhorn
depends_on: []
conflicts_with:
  - kube-prometheus-stack-93.3.0      # section 4 V3 reads Prometheus; do not share a night with its restart
exclusive: false
security_ref: F-d2130a4d
capability_change: false              # new env DASHCAST_WARM_FOR/COUNT are opt-in and unset here; no new route, port or permission
rollback_class: git-revert
finding_refs: [F-56a47893]
supersedes: dashcast-1.6.45           # that plan (status: superseded) assessed 1.2.14 -> 1.6.45; its 1.1 assessment is not repeated
review: ready-for-go@2026-11-23
status: vetted
window: null
premises:
  - id: dashcast-live-image
    why: >-
      The plan edits v1.6.46 -> v1.6.48. If the live image is not exactly v1.6.46 (Renovate already merged #578 to 1.6.49, a
      revert, Flux stuck) the sed in section 3 matches nothing or the baseline is wrong. Prints a different string and fails.
    run: kubectl get deploy dashcast -n home-automation -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "ghcr.io/huskerminion/techo5-dashcast:v1.6.46@sha256:6c780d5d06b5d022caafda0a0bbbc6f87fda9c00b460bc85a44b16ff59870465"
  - id: dashcast-hr-ready
    why: >-
      A failed or rolled-back Helm release (upgrade.remediation.strategy rollback) leaves the Deployment on another image than git.
      Anything other than True fails.
    run: kubectl get helmrelease dashcast -n home-automation -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
sops_refs:
  - docs/sops/application-update.md
generated: "2026-11-23"
---

# dashcast v1.6.46 -> v1.6.48

## 1. Summary & why held

**What it is.** dashcast (`dashcast/` in HuskerMinion/techo5, MIT) is a headless-Chrome server that renders Home Assistant
dashboards and streams them to TECHO5 screens over a Noise-encrypted TCP protocol on :9555. Our deployment:
`kubernetes/apps/home-automation/dashcast/app/helmrelease.yaml` (app-template, 1 replica, no PVC, memory request 256Mi / limit 1Gi,
LoadBalancer 192.168.55.32 on Cilium L2, secret `dashcast-secret`). No HTTPRoute, Authentik or Homepage entry.

**Why held.** Coverage reason: G3 could not verify the release notes (release notes unavailable; the upstream releases describe
the whole TECHO5 firmware project, not `dashcast/`) and earned autonomy has no SWEEP_PG_DSN history, so an unverified bump goes to
an assessed window. It is not held for a breaking change. This plan supersedes `dashcast-1.6.45.md` (left in place, status
superseded); that plan's source review of 1.2.14 -> 1.6.45 still stands and is not duplicated.

**Live state measured 2026-11-23.** `deploy/dashcast` runs `v1.6.46@sha256:6c780d5d...` (pod imageID matches, 45 h old, 0 restarts,
HelmRelease Ready=True, log line `dashcast ready listen=:9555 home_assistant=...`, 54Mi). `main` contains #566 (954dc6d26).

### 1.1 Breaking-change assessment (source, `compare/v1.6.45...v1.6.48`, 101 commits)

Only 5 files under `dashcast/` changed: README, docker-compose.yml, `main.go` (+7), `warm.go` (+44 -2), `warm_test.go` (+29).
`dashcast/Dockerfile` is NOT in the diff, so the base image, uid 65534, `HOME=/tmp`, `LISTEN` and entrypoint are unchanged and
our securityContext/probe stay valid. The only code change is release v1.6.47's "Dashcast: `DASHCAST_WARM_FOR` and
`DASHCAST_WARM_COUNT` set how long a parked dashboard stays warm, and how many" (#668):

- The previously hard-coded constants (5 minutes, 4 tabs) become the defaults (`warmForDefault`, `warmCountDefault`); the test
  asserts `warmFor == 5m, warmCount == 4` when unset. We set neither variable, so behaviour is identical.
- Bad values never stop the process: `warmSettings` logs a Warn and keeps the default (count bounded 1..16).
- `main.go` logs `parked dashboards kept_for=... kept=...` only if a value differs from the default, so that line is ABSENT here.
- Everything else in v1.6.46..48 notes is device firmware (emoji, alarms, Valencian, NetBird add-on, Music Assistant labels); it
  applies only after a DEVICE firmware update and the server bump changes no wire protocol. The v1.6.47 NetBird removal and the
  "Show Action button event" removal are device-side and do not touch our server.
- Not verifiable from the cluster: which firmware versions the connected TECHO5 devices run, and whether any device is attached.

### 1.2 Verdict

False-positive hold ("unverified", not "breaking"). `risk: low`. Residual risk: a Chrome/CDP regression visible only with a real
screen attached.

### 1.3 Newer tag exists

Renovate #578 (open) targets `v1.6.49` (registry digest `sha256:2c04e24babd9f0663e499a6004443e65a1481797bf7eaedb2cda87c885ed90d0`,
== `latest`, measured). `compare/v1.6.48...v1.6.49` is 32 commits with ZERO files under `dashcast/`, i.e. the server binary source
is unchanged. If the operator prefers to land the current tag, set `target` accordingly and use that digest in section 3; the
gates are identical. Otherwise merging #578 after this plan avoids the PR and the plan racing (close #578 or let it rebase to
the plan's commit).

## 2. Pre-checks

1. `git pull --rebase`; then `grep -n 'tag:' kubernetes/apps/home-automation/dashcast/app/helmrelease.yaml` must show
   `v1.6.46@sha256:6c780d5d...` (if it shows 1.6.49, #578 already merged: stop, run section 4 as a soak and retire this plan).
2. Premises pass: `.venv/bin/python3 runbooks/plan-premises.py dashcast-1.6.48 --require-premises`.
3. Digest still resolves (registry can re-point a tag):
   `T=$(curl -s "https://ghcr.io/token?scope=repository:huskerminion/techo5-dashcast:pull" | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")`
   then `curl -sI -H "Authorization: Bearer $T" -H "Accept: application/vnd.oci.image.index.v1+json" https://ghcr.io/v2/huskerminion/techo5-dashcast/manifests/v1.6.48 | grep -i docker-content-digest`
   must print `sha256:d4ef60f9deed182a483a585fa14a198401d2b78a00000ac6cdb8dcbb5be8d96a`.
4. Home Assistant healthy (dashcast reads dashboards via `HA_URL`): `kubectl get deploy home-assistant -n home-automation` READY 1/1.
5. Operator question: are any TECHO5 screens attached now (V5 needs one)? Not readable from the cluster.

## 3. Steps

1. Edit the tag (BSD-sed dry-tested on a scratch copy; resulting diff line):
   ```
   sed -i '' 's|^\([[:space:]]*tag:[[:space:]]*\)v1\.6\.46@sha256:6c780d5d[0-9a-f]*|\1v1.6.48@sha256:d4ef60f9deed182a483a585fa14a198401d2b78a00000ac6cdb8dcbb5be8d96a|' kubernetes/apps/home-automation/dashcast/app/helmrelease.yaml
   # 41c41
   # <               tag: v1.6.46@sha256:6c780d5d06b5d022caafda0a0bbbc6f87fda9c00b460bc85a44b16ff59870465
   # >               tag: v1.6.48@sha256:d4ef60f9deed182a483a585fa14a198401d2b78a00000ac6cdb8dcbb5be8d96a
   ```
   `git diff --stat` must show exactly 1 line changed in 1 file.
2. `git commit --only kubernetes/apps/home-automation/dashcast/app/helmrelease.yaml -m "fix(container): update ghcr.io/huskerminion/techo5-dashcast ( v1.6.46 -> v1.6.48 )"`; run `git log -1 --format=%s` and confirm it is YOUR subject; `git push`.
3. Flux webhook reconciles; no manual reconcile and no `sops` involved.

## 4. Verification

- **V1 image (CONTENTS):** `kubectl get pod -n home-automation -l app.kubernetes.io/name=dashcast -o jsonpath='{.items[0].status.containerStatuses[0].imageID}'`
  must end `@sha256:d4ef60f9deed182a483a585fa14a198401d2b78a00000ac6cdb8dcbb5be8d96a`. Fails with `...6c780d5d...` if the old
  generation is still running (`rollout status` would not catch that).
- **V2 startup log:** `kubectl logs deploy/dashcast -n home-automation --tail=200` contains `dashcast ready` and `home_assistant=`,
  and does NOT match (case-insensitive) `all have to be set`, `DASHCAST_PAGES`, `DASHCAST_WARM`, `panic`, or `chrome` near `fail`.
  A `DASHCAST_WARM` hit would mean an env var leaked in (we set none) and the Warn path ran. Also expect NO `parked dashboards`
  line (defaults in effect); its presence means a non-default value reached the pod.
- **V3 alerts/restarts:** `DashcastPodNotReady`, `DashcastPodCrashLooping`, `DashcastPodRestarted` (loaded, `kubectl get prometheusrule dashcast-alerts -n monitoring`)
  0 firing, and `kube_pod_container_status_restarts_total{namespace="home-automation",pod=~"dashcast-.*"}` stays 0; confirm the
  query returns a series first (empty reads the same before and after). A crash loop or OOM moves the counter.
- **V4 service:** `kubectl get svc dashcast -n home-automation` EXTERNAL-IP `192.168.55.32`; pod 1/1 Ready (exec probe reads the
  :2553 listen socket, so an unbound port keeps it NotReady).
- **V5 end to end (operator-present, only gate exercising Chrome/CDP):** open the dashboard on one TECHO5 device. Log shows
  `device connected name=... path=...`; FAIL on `opening the dashboard failed`, `could not ask Home Assistant what its dashboards are`,
  `device failed the handshake`, or the screen showing "NOT LIVE" more than once an hour. Turn the screen off and on within 5 min
  and confirm the dashboard returns instantly (parked-tab path in warm.go). No screen attached means V1-V4 prove only that the
  server is up; say so in the window report.
- **V6 memory:** `kubectl top pod -n home-automation -l app.kubernetes.io/name=dashcast` well under 1Gi (baseline 54Mi idle);
  parked tabs hold 150-250 MB each so up to 4 screens can approach the limit; OOMKilled restart = raise the limit separately, not a rollback by itself.

## 5. Rollback

Stateless (no PVC, schema, or one-way step), so a plain revert is complete:
1. `git revert <sha of the step-2 commit>` (restores `v1.6.46@sha256:6c780d5d06b5d022caafda0a0bbbc6f87fda9c00b460bc85a44b16ff59870465`), push.
2. Confirm V1 with imageID ending `...6c780d5d...`, HelmRelease Ready=True, `dashcast ready` in the log.
3. Renovate may re-open the bump; hold it with a deny rule in `runbooks/auto-update-policy.yaml` if desired.
A failed Helm upgrade auto-rolls back (`upgrade.remediation.strategy: rollback`, `cleanupOnFail: true`).

## 6. Interference notes

- Namespace `home-automation` is shared with Home Assistant; dashcast depends on it (one-way). A pod restart blanks TECHO5
  dashboards for ~20-40 s (parked tabs are lost too).
- No Gateway/HTTPRoute, Authentik, Longhorn, CIFS or reboot involved. A Talos roll or Cilium L2/LB change (`cilium-1.20.5`
  re-homes .32's lease) would also drop the stream; not declared as a conflict because it is a transient, not a correctness, clash.
- `conflicts_with kube-prometheus-stack-93.3.0`: V3 reads Prometheus (shared instrument).
- Open PR #578 (1.6.49) touches the same tag line: do not run both; the second will conflict in git.
- Repo notes: `coverage.py` reports the plan group with `pr: null` while #578 (a newer target) is open, so group ids and Renovate PRs
  drift apart; no SOP correction needed. `finding_refs` uses F-56a47893 (version finding); `security_ref` F-ae4e500c is the
  fixable-HIGH finding against the older v1.6.45 tag, detail stays in the findings DB.
