---
plan_id: iobroker-12.0.0
component: iobroker
pr: null                              # no Renovate PR; surfaced by coverage.py needs_plan_groups
                                      # ("major — needs an assessed window plan"), nightly 2026-10-05 Step 0.5
kind: image
current: "v11.1.0"                    # live 2026-10-05: sts/iobroker image buanet/iobroker:v11.1.0,
                                      # pod imageID docker.io/buanet/iobroker@sha256:f41eb305ff20d57e1ea0d89a68d9484f9655b547286cc08bf3df8a1ce9991edf
                                      # (an OLDER build of the tag: upstream re-pushes v11.1.0, its
                                      # current index digest is ff01c6d3..., see §5)
target: "v12.0.0@sha256:46b7b467244ef54bf4f1faadad988a630f94aff16613d4a3a0c161e72ad8808a"
                                      # OCI image INDEX digest; read 2026-10-05 from registry-1.docker.io
                                      # (HEAD manifests/v12.0.0, docker-content-digest) AND the Docker Hub
                                      # tag API — identical. amd64 child sha256:4091d15c237c8bcf798189be6fe62d41272b5b1458bdfee45a60ea458e95fba8.
                                      # GitHub release "Stable Release v12.0.0", published 2026-10-04.
update_type: major
risk: low                             # Honest reading: the major is a RUNTIME swap (Debian 12->13,
                                      # Node 22->24), not an ioBroker data/format change. /opt/iobroker
                                      # (js-controller 7.0.6, adapters, jsonl DBs) lives on the PVC and is
                                      # NOT replaced by the image. This install runs only 3 instances
                                      # (admin.0, backitup.0, discovery.0), no MQTT/Node-RED/VIS adapter,
                                      # no measured LAN client (§1.4). Every native module was checked
                                      # against Node 24 (§1.3). Rollback is a git revert to an image whose
                                      # PVC contents are untouched. Blast radius = this one idle pod.
est_duration_min: 30                  # pre-checks 6 + edit/commit/push/propagate 5 + pull (~0.5 GB) and
                                      # start (startup probe up to 15 min, typically ~1.5 min) 5 +
                                      # §4 gates 10 + slack 4
needs_reboot: false
touches:
  namespaces: [home-automation]
  resources:
    - helmrelease/iobroker            # the ONE edited line: values...containers.main.image.tag
                                      # (kubernetes/apps/home-automation/iobroker/app/helm-release.yaml)
    - statefulset/iobroker            # replicas 1; pod iobroker-0 deleted+recreated by the sts controller
                                      # (StatefulSets are immune to the RWO multi-attach race)
    - pvc/iobroker-config             # longhorn-static RWO 15Gi, PV/volumeHandle iobroker-config;
                                      # remounted only. NO PVC/PV action of any kind.
    - service/iobroker                # LoadBalancer 192.168.55.25 (Cilium LB-IPAM), NOT edited; endpoints
                                      # move to the new pod (~2 min gap)
    - httproute/iobroker              # envoy-external, NOT edited; backend unavailable during the restart
  shared: []                          # Deliberate. No gateway/envoy change (route object untouched, only
                                      # its backend pod restarts), no shared DB (jsonl DBs are in-pod),
                                      # no MQTT broker role in practice (no mqtt adapter installed — the
                                      # 1883 service port has no listener behind it), no GPU, no CIFS.
                                      # §4 reads Prometheus (kube-state-metrics) for 2 gates, so a
                                      # same-night kube-prometheus-stack plan is listed in conflicts_with.
depends_on: []
conflicts_with:
  - flux-fleet-0.60.0                 # Flux controller bump changes the delivery path this bump rides (review 2026-10-05)
  - flux-oci-chart-sources            # its bjw-s chartRef switch edits this same helm-release.yaml (review 2026-10-05)
  - app-template-5.2.1                # edits THIS helm-release.yaml (chart 5.1.0 -> 5.2.1) and its
                                      # --compare-workloads gate covers sts/iobroker: our pod roll reads
                                      # as GEN_CHANGED there, and a mixed chart+image change breaks our
                                      # attribution. NOT yet reciprocal — see report / §6.
  - helm-drift-detection              # adds spec.driftDetection to every HR incl. helmrelease/iobroker;
                                      # same object, same helm-controller pass
  - flux-reconciler-impersonation     # exclusive:true already keeps its slot empty; named so the
                                      # dependency is explicit (our delivery path is the Flux apply it re-identities)
  - kube-prometheus-stack-91.9.0      # §4 G7 reads kube-state-metrics through Prometheus — the window's
                                      # instrument is shared infra
exclusive: false
security_ref: null                    # no security driver for this plan. Related, NOT owned: the two
                                      # AR-029 "already on newest" register rows for the v11.1.0 image
                                      # (F-38995b9e, F-dd52e0d4) — their premise lapses now that a newer
                                      # upstream tag exists; detail stays in the DB.
capability_change: false              # same app, same adapters, same config, same ports; only the
                                      # container base OS and Node runtime change. No new feature,
                                      # route, permission or exposure.
rollback_class: git-revert            # nothing forward-only (§1.5): the image does not rewrite
                                      # /opt/iobroker on an existing install, js-controller/DB format
                                      # stay on the PVC version. Backstops (not gates): backitup
                                      # minimal tarball 02:48 daily on the PVC + Longhorn daily backup.
backup_gate: null                     # not required: rollback_class git-revert, no one-way data step.
                                      # §2.4 still REQUIRES a Completed Longhorn backup <= 26 h old as a
                                      # belt-and-braces pre-check.
finding_refs: [F-2466513f]            # version finding v11.1.0 -> v12.0.0, emitted by sweep 481b9c1f (2026-10-05).
                                      # Earlier note: `policy-cli.py finding list --grep iobroker` (2026-10-05): only the
                                      # two AR-029 security rows and F-0a5ad294 (chart 5.1.0->5.2.1, owned
                                      # by app-template-5.2.1). No version finding for v12.0.0 exists yet
                                      # (the tag shipped 2026-10-04, after the last sweep 2026-10-03).
review: null
status: draft
window: null
premises:
  # All read-only. Values measured live 2026-10-05.
  - id: sts-on-v11.1.0
    why: >-
      `current:` and every baseline in §2 (Node 22.22.0, Debian 12, 3 instances, object count) were
      captured against this tag. If the StatefulSet already moved, this plan is stale.
    run: kubectl get sts -n home-automation iobroker -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: buanet/iobroker:v11.1.0
  - id: hr-ready
    why: "A HelmRelease already failing would mask whether the bump itself reconciled."
    run: kubectl get helmrelease -n home-automation iobroker -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: sts-ready
    why: "The pre-state must be a running iobroker-0, or the §4 before/after comparison has no baseline."
    run: kubectl get sts -n home-automation iobroker -o jsonpath='{.status.readyReplicas}'
    expect_exact: "1"
  - id: config-volume-healthy
    why: "The PVC is the whole install; it must be attached and healthy before the pod is replaced."
    run: kubectl get volumes.longhorn.io -n storage iobroker-config -o jsonpath='{.status.state}/{.status.robustness}'
    expect_exact: attached/healthy
  - id: pv-retain
    why: "The PV must stay Retain (it is the only copy of the ioBroker install apart from backups)."
    run: kubectl get pv iobroker-config -o jsonpath='{.spec.persistentVolumeReclaimPolicy}'
    expect_exact: Retain
  - id: longhorn-backup-exists
    why: >-
      Backstop for the (unexpected) case that the new image re-initialises /opt/iobroker. Freshness
      (<= 26 h) is asserted in §2.4 because premises cannot do date arithmetic; this premise only
      proves the volume HAS a recorded backup.
    run: kubectl get volumes.longhorn.io -n storage iobroker-config -o jsonpath='{.status.lastBackupAt}'
    expect_matches: '^20[0-9]{2}-[0-9]{2}-[0-9]{2}T'
  - id: route-accepted
    why: "Baseline for G6: the HTTPRoute must be Accepted on envoy-external before, or a post-change failure is not ours."
    run: kubectl get httproute -n home-automation iobroker -o jsonpath='{.status.parents[0].conditions[?(@.type=="Accepted")].status}'
    expect_exact: "True"
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/longhorn.md
  - docs/sops/backup.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-10-05"
---

# iobroker v11.1.0 -> v12.0.0 (buanet/iobroker image major)

## 1. Summary & why held

**Change:** one line in `kubernetes/apps/home-automation/iobroker/app/helm-release.yaml`:
`tag: v11.1.0` -> `tag: v12.0.0@sha256:46b7b467...`. Chart (app-template 5.1.0) unchanged.

**Why held:** coverage.py routes every `major` to a plan. The hold is correct in form, but the
assessed risk is low (see `risk:` comment); this is not a false positive, it is a genuine major
that happens to have a tiny blast radius here.

### 1.1 Upstream evidence (read 2026-10-05)

GitHub release `buanet/ioBroker.docker` v12.0.0 ("Stable Release v12.0.0", 2026-10-04):

> * update debian baseimage from bookworm (12) to trixie (13)
> * fixing install.sh manipulation
> * testing node24
>
> This release contains a new recommended node version. Upgrading an existing ioBroker to a new
> node version may cause some issues. To minimize this, make sure your js-controller and adapters
> are in latest stable version. Make also sure you have a valid backup. [...] In some rare cases
> some adapters need a little help by reinstalling them.

The upstream build log (run 37211454915, job "Build latest amd64 image for iobroker") confirms
the runtime: `[LOG] Nodejs Version: 24`, `Setting up nodejs (24.21.0-1nodesource1)`. The
`compare v11.1.0...v12.0.0` diff touches only `debian/Dockerfile` (`FROM debian:trixie-slim`, one
extra `sed` on install.sh) and CI; every `debian/scripts/*.sh` (startup, setup_packages,
healthcheck, maintenance) is a pure rename with **0 additions / 0 deletions**. So the container
entrypoint behaviour is byte-identical to v11.1.0; only OS + Node change.

### 1.2 Why the Node major does NOT move ioBroker itself

`/opt/iobroker` is the PVC (`iobroker-config`). The startup script only extracts the image's
`initial_iobroker.tar` onto an EMPTY volume (first-run path); on an existing install it runs the
js-controller already on the PVC. So after the bump we run **js-controller 7.0.6 / admin 7.7.22 /
backitup 3.3.5 / discovery 5.0.0 — unchanged — on Node 24.21.0**. Upstream's "keep js-controller
current" advice is therefore relevant; see §1.6 for why this plan does not do an in-pod
`iob upgrade` first.

### 1.2b The main uncertainty, stated (added 2026-10-05 per plan review, option (a))

**js-controller 7.0.6 on Node 24 is untested upstream.** Its own CI matrix at `v7.0.6`
(`.github/workflows/ci-tests.yml`) is `node: [18, 20, 22]`; Node 24 entered the matrix only in the
7.2 line (`@v7.2.4`: `[22, 24, 26]`). The image vendor's v12.0.0 release note asks to bring
js-controller and adapters to latest stable FIRST; §1.6 deliberately does not, to keep this a
single-variable change. Consequence, accepted explicitly: **a loud revert is a plausible outcome
of this window**, not an edge case. That is acceptable for AUTO-NIGHT because (1) nothing is
migrated on first boot (startup scripts byte-identical to v11.1.0; same js-controller, same jsonl
DBs on the PVC), so `git revert` restores the exact prior runtime with no data at risk; (2) every
failure mode of an incompatible controller is loud and gated (G1/G3/G4/G7); (3) the hub is idle
(3 instances, no consumers in the repo). The alternative -- a separate js-controller 7.2.x plan
first, on v11 (7.2.x needs Node >= 22.19; live 22.22.0) -- is the follow-up if this reverts.
`risk: low` stays the IMPACT rating; the likelihood of a revert is higher than "low" suggests.

### 1.3 Native modules, checked one by one on the live PVC (2026-10-05)

`find node_modules -name '*.node' -path '*build/Release*'` + `binding.gyp` scan:

| Module | Who uses it | ABI exposure on Node 24 | Effect |
|---|---|---|---|
| `@serialport/bindings-cpp` | discovery (serial scan) | **N-API prebuild** (`prebuildify --napi`, `prebuilds/linux-x64`) — ABI-stable | none |
| `diskusage` (NAN, built for ABI 127) | js-controller-common-db `getHostInfo` | will NOT load on ABI 137 | `require` is wrapped in `try {} catch {}` (tools.js ~l.1435) -> host disk-usage stats in admin go blank. Cosmetic. |
| `unix-dgram` | winston-syslog (optionalDependency) | **already broken today** — live `require` fails with "compiled against NODE_MODULE_VERSION 115 ... requires 127" | none new; proves ioBroker tolerates a dead optional native module |
| `ssh2` / `cpu-features` | optional crypto accel | optional | none |

For adapters, js-controller 7.0.6 auto-rebuilds on start failure (`main.js` ~l.3047: an adapter
stderr containing `NODE_MODULE_VERSION` / `Error: The module '` / `Could not locate the bindings
file` sets `needsRebuild`). The image ships `make`/`g++` (verified in the v11 pod; install.sh
installs build tools in both). None of our 3 adapters needs it per the table above.

### 1.4 Consumers / exposure

- Instances: `admin.0` (8081), `backitup.0` (minimal backup 02:48 daily, 10-day retention, no
  influx/mysql/redis targets), `discovery.0`. No mqtt, node-red, vis, lovelace, simple-api adapter
  — the extra service ports (1880/1883/8082/8087/8091/9000/9001/51988/51989/53388) have nothing
  listening behind them except the in-pod jsonl DB servers on 9000/9001.
- No repo reference to iobroker or 192.168.55.25 outside its own app dir.
- Exposed via HTTPRoute on `envoy-external` (in-app auth, no SecurityPolicy) + LB 192.168.55.25.
- `PACKAGES=influxdb2-cli` is reinstalled at every start from the influxdata apt repo; on trixie
  that apt step could fail (new apt signature policy), and `setup_packages.sh` treats that as
  non-fatal (`echo "Failed."`, continues). backitup's `influxDBEnabled` is **false**, so the CLI is
  unused. G5 records whether it installed; failure is informational.

### 1.5 Forward-only check

Nothing forward-only: no DB schema/format change (same js-controller on the PVC), no adapter
install/upgrade, no PV change. The only thing the new runtime might write is a rebuilt native
module under `node_modules`, which js-controller rebuilds again if we go back to Node 22.

### 1.6 Deliberately NOT done in this window

- **No in-pod `iob upgrade self` / adapter upgrades first.** That is an unplanned, unreviewed
  mutation of the install on the PVC (js-controller 7.0.6 -> 7.2.4) with its own rollback story;
  mixing it into this window would break attribution. Upstream's advice is a recommendation, and
  the specific hazards it guards against (native adapter modules) were checked in §1.3. Record as a
  follow-up if the operator wants the install current.
- **No `npm rebuild diskusage`.** In-pod `node_modules` edits are outside the CLAUDE.md
  in-pod-edit exception (that covers app *config* with no GitOps path). Blank disk stats are
  recorded as a follow-up, not fixed in-window.

## 2. Pre-checks

Run from the repo root on the Mac mini (zsh). All read-only.

```bash
# 2.0 premises (scheduler re-runs them; run explicitly before the edit)
.venv/bin/python3 runbooks/plan-premises.py iobroker-12.0.0

# 2.1 Flux / HR sane, nothing mid-reconcile for this app
flux get kustomizations -n home-automation iobroker
flux get helmreleases -n home-automation iobroker

# 2.2 BASELINE capture (writes $W for §4 diffs)
W=/private/tmp/claude-501/iobroker-12.0.0   # FIXED plan-scoped path: shell vars do not survive between the window agent's Bash calls (review 2026-10-05)
if [ -d "$W" ] && [ -n "$(ls -A "$W" 2>/dev/null)" ]; then echo "STOP: $W holds files from an earlier attempt -- move them aside first"; exit 1; fi; mkdir -p "$W"
kubectl -n home-automation exec iobroker-0 -- bash -c 'node -v; . /etc/os-release; echo "debian=$VERSION_ID"' | tee "$W/runtime-before.txt"
#   expect: v22.22.0 / debian=12
kubectl -n home-automation exec iobroker-0 -- bash -c 'cd /opt/iobroker && iobroker object list "*" 2>/dev/null | wc -l' | tr -d ' ' | tee "$W/objcount-before.txt"
#   measured 2026-10-05: 156
kubectl -n home-automation exec iobroker-0 -- bash -c 'cd /opt/iobroker && iobroker list instances 2>/dev/null | grep -c "^+ system.adapter\."' | tee "$W/instances-before.txt"
#   measured: 3
kubectl -n home-automation exec iobroker-0 -- bash -c 'cd /opt/iobroker && iobroker object get system.config 2>/dev/null' \
  | python3 -c 'import sys,json; d=json.load(sys.stdin)["common"]; print(d.get("language"), d.get("licenseConfirmed"), d.get("firstDayOfWeek"))' | tee "$W/sysconfig-before.txt"
kubectl -n home-automation exec iobroker-0 -- bash -c 'ls -la /opt/iobroker/iobroker-data/objects.jsonl /opt/iobroker/iobroker-data/states.jsonl' | tee "$W/jsonl-before.txt"
#   measured: objects.jsonl ~9.3 MB, states.jsonl ~6.5 MB

# 2.3 backitup minimal tarball from today exists on the PVC (02:48 daily)
kubectl -n home-automation exec iobroker-0 -- bash -c "ls -1 /opt/iobroker/backups | grep -c \"iobroker_$(date +%Y_%m_%d)-\""
#   PASS: 1.  0 => backitup did not run today: STOP and investigate (it is the fast restore path).

# 2.4 Longhorn backup <= 26 h old and Completed
kubectl get backups.longhorn.io -n storage -l backup-volume=iobroker-config \
  --sort-by=.status.backupCreatedAt \
  -o custom-columns='NAME:.metadata.name,STATE:.status.state,CREATED:.status.backupCreatedAt' | tail -1
#   PASS: STATE Completed and CREATED within the last 26 h. If today's 03:00 run is still
#   InProgress (nightly window starts 03:30), wait for Completed — do NOT proceed during it.
```

## 3. Steps

```bash
cd /Users/mu/code/cberg-home-nextgen
F=kubernetes/apps/home-automation/iobroker/app/helm-release.yaml

# 3.1 the edit (BSD-sed safe; dry-tested on a scratch copy 2026-10-05; leaves the
#     commented '#tag: v10.0.0' line alone because the pattern anchors on '^[[:space:]]*tag: v11.1.0$')
sed -i '' 's|^\([[:space:]]*tag: \)v11\.1\.0$|\1v12.0.0@sha256:46b7b467244ef54bf4f1faadad988a630f94aff16613d4a3a0c161e72ad8808a|' "$F"
git diff -- "$F"
#   expected diff (exactly one line, line 40):
#   -              tag: v11.1.0
#   +              tag: v12.0.0@sha256:46b7b467244ef54bf4f1faadad988a630f94aff16613d4a3a0c161e72ad8808a

# 3.2 render gate. kubeconform skips the HelmRelease CRD, so it only proves YAML shape;
#     the values change is a plain string, so a YAML parse + the image line is the real check:
python3 -c "import yaml,sys; d=yaml.safe_load(open('$F')); print(d['spec']['values']['controllers']['main']['containers']['main']['image']['tag'])"
#   PASS prints: v12.0.0@sha256:46b7b467244ef54bf4f1faadad988a630f94aff16613d4a3a0c161e72ad8808a
kubeconform -summary -ignore-missing-schemas kubernetes/apps/home-automation/iobroker

# 3.3 commit ONLY this file (shared worktree), verify, push
printf '%s\n\n%s\n' "feat(iobroker): buanet/iobroker v11.1.0 -> v12.0.0 (Debian 13, Node 24) [plan iobroker-12.0.0]" \
  "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>" > /tmp/iob12-msg.txt
git commit --only "$F" -F /tmp/iob12-msg.txt
git log -1 --format=%s        # must be the subject above — amend before push if not
git show --stat HEAD          # must list exactly the one helm-release.yaml
git push

# 3.4 propagation: the push webhook updates the GitRepository; kustomization/iobroker and the HR
#     follow. Watch (read-only) — no manual reconcile unless nothing moved after 10 min:
kubectl get hr -n home-automation iobroker -w   # Ctrl-C once Ready=True with the new revision
kubectl -n home-automation get pod iobroker-0 -w   # Terminating -> ContainerCreating -> Running 1/1
#   The startup probe allows up to 15 min (60 x 15 s); typical ~90 s. If still not Ready at
#   15 min, go to §5.
```

## 4. Verification

Every gate states what its failure prints. Run in order; any FAIL -> §5.

```bash
# G1 — the NEW image is what runs (guards: a cached/old image or a failed pull still serving)
kubectl -n home-automation get pod iobroker-0 -o jsonpath='{.status.containerStatuses[0].imageID} {.status.containerStatuses[0].restartCount}{"\n"}'
#   PASS: imageID ends in @sha256:46b7b467244ef54bf4f1faadad988a630f94aff16613d4a3a0c161e72ad8808a, restarts 0.
#   FAIL prints the old digest f41eb305... (no roll happened) or restarts > 0 (crash-looping).

# G2 — HR reconciled the change
kubectl get hr -n home-automation iobroker -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.lastAttemptedRevision}{"\n"}'
#   PASS: "True". FAIL: False + an upgrade error message.

# G3 — CONTENTS: the runtime actually changed (guards: right digest label, wrong runtime)
W=/private/tmp/claude-501/iobroker-12.0.0   # re-set: fresh shell; same fixed path as §2.2
kubectl -n home-automation exec iobroker-0 -- bash -c 'node -v; . /etc/os-release; echo "debian=$VERSION_ID"' | tee "$W/runtime-after.txt"
#   PASS: v24.* and debian=13.  FAIL: v22.22.0 / debian=12 (= same as $W/runtime-before.txt).

# G4 — CONTENTS: ioBroker is alive with ALL its instances (guards: controller up but adapters dead)
kubectl -n home-automation exec iobroker-0 -- bash -c 'cd /opt/iobroker; iobroker status; for i in admin.0 backitup.0 discovery.0; do printf "%s " $i; iobroker state get system.adapter.$i.alive 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin)[\"val\"])"; done'
#   PASS: "iobroker is running on this host." and all three print True.
#   Why it can fail: `alive` is written with expire:true (measured), so a dead adapter's state
#   EXPIRES and `state get` returns null -> python raises TypeError / prints None. A crash-looping
#   adapter with a native-module error also leaves `alive` false/expired.
#   If one adapter is not alive: check `iobroker logs --lines 200 | grep -iE "NODE_MODULE_VERSION|rebuild|error"`;
#   js-controller's auto-rebuild may need 1-2 min — re-check once after 3 min, then §5.

# G5 — CONTENTS ASSERTION (the property that could silently break): the EXISTING install was
#      used, not a fresh one (guards: first-run path extracting initial_iobroker.tar over/next to the PVC)
W=/private/tmp/claude-501/iobroker-12.0.0   # re-set: fresh shell; same fixed path as §2.2
kubectl -n home-automation exec iobroker-0 -- bash -c 'cd /opt/iobroker && iobroker object list "*" 2>/dev/null | wc -l' | tr -d ' ' | tee "$W/objcount-after.txt"
kubectl -n home-automation exec iobroker-0 -- bash -c 'cd /opt/iobroker && iobroker list instances 2>/dev/null | grep -c "^+ system.adapter\."' | tee "$W/instances-after.txt"
kubectl -n home-automation exec iobroker-0 -- bash -c 'cd /opt/iobroker && iobroker object get system.config 2>/dev/null' \
  | python3 -c 'import sys,json; d=json.load(sys.stdin)["common"]; print(d.get("language"), d.get("licenseConfirmed"), d.get("firstDayOfWeek"))' > "$W/sysconfig-after.txt"
diff "$W/sysconfig-before.txt" "$W/sysconfig-after.txt" && echo SYSCONFIG_SAME
kubectl -n home-automation logs iobroker-0 | grep -c 'Existing installation of ioBroker detected'
kubectl -n home-automation logs iobroker-0 | grep -ciE 'no data detected|start with a fresh installation'
#   PASS: objcount-after >= objcount-before (156 on 2026-10-05; may grow by a few host
#         objects, never shrink), instances-after == 3, SYSCONFIG_SAME (baseline "en True monday"),
#         first log grep 1, second log grep 0.
#   FAIL: a fresh install has ~1/3 the objects, 1 instance (admin only), licenseConfirmed
#         False, and the startup log's Step 2 prints "There is no data detected in /opt/iobroker."
#         (iobroker_startup.sh Step 2 branch; the positive control is today's v11 log, which
#         prints "Existing installation ..." exactly once). NOTE: /opt/iobroker/.fresh_install is
#         NOT usable as a signal — the startup script deletes it on every path (l.330/l.535).
# Informational only (do not block): PACKAGES install result
kubectl -n home-automation logs iobroker-0 | grep -iE 'influxdb2-cli' | tail -2

# G6 — the app serves: in-pod, via the LB IP, and the route is still Accepted
kubectl -n home-automation exec iobroker-0 -- bash -c 'curl -s -o /dev/null -w "%{http_code} %{size_download}\n" http://127.0.0.1:8081/; curl -s http://127.0.0.1:8081/ | grep -ic "<title>admin"'
curl -s -o /dev/null -w '%{http_code}\n' http://192.168.55.25:8081/
kubectl get httproute -n home-automation iobroker -o jsonpath='{.status.parents[0].conditions[?(@.type=="Accepted")].status} {.status.parents[0].conditions[?(@.type=="ResolvedRefs")].status}{"\n"}'
#   PASS: "200 <~4.7 kB>" and title count >= 1 (grep -i: upstream title is "Admin"), LB 200,
#   route "True True". FAIL: 000/5xx (admin.0 down), title 0 (an error page with a 200).

# G7 — soak, read from Prometheus at T+10 min
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 &
PF=$!; sleep 3
for q in 'kube_statefulset_status_replicas_ready{namespace="home-automation",statefulset="iobroker"}' \
         'increase(kube_pod_container_status_restarts_total{namespace="home-automation",pod="iobroker-0"}[10m])'; do
  curl -s --data-urlencode "query=$q" http://localhost:19090/api/v1/query \
   | python3 -c 'import sys,json; r=json.load(sys.stdin)["data"]["result"]; assert r, "EMPTY RESULT = FAIL"; print([x["value"][1] for x in r])'
done
kill $PF
#   PASS: replicas_ready ['1'], restarts increase ['0'] (or '0.0'). An EMPTY result is a FAIL
#   (asserted), not a pass — both series were measured non-empty on 2026-10-05.
```

CONTENTS ASSERTION: the existing ioBroker install (objects DB, instances, system.config) is the one
running — measured by G5 object count / instance count / system.config fields, compared to the §2.2
baseline in `$W` (156 objects, 3 instances on 2026-10-05).
CONTENTS ASSERTION: the runtime really is Node 24 on Debian 13 — measured by G3 `node -v` and
`/etc/os-release`, compared to `$W/runtime-before.txt` (v22.22.0 / 12).
CONTROL: metric kube_statefulset_status_replicas_ready — `{namespace="home-automation",statefulset="iobroker"}` must be 1 at T+10 min; empty result = FAIL.
CONTROL: metric kube_pod_container_status_restarts_total — `increase(...{pod="iobroker-0"}[10m])` must be 0; empty result = FAIL.

**Follow-ups to record after a PASS (not in-window work):** host disk-usage stats in admin go
blank (diskusage is a NAN module, §1.3); js-controller/adapters are behind latest stable
(7.0.6 vs 7.2.4; backitup 3.3.5 vs 4.x) — an operator decision whether to `iob upgrade`.

## 5. Rollback

Trigger: any G1-G7 FAIL, or pod not Ready 15 min after the roll.

```bash
cd /Users/mu/code/cberg-home-nextgen
# 5.1 revert the single commit (restores tag: v11.1.0)
git revert --no-edit <sha-of-3.3>
git log -1 --format=%s ; git show --stat HEAD     # exactly the one helm-release.yaml
git push
# 5.2 watch it roll back
kubectl -n home-automation get pod iobroker-0 -w
```

Note on the v11.1.0 tag: upstream re-pushes it (current index digest `ff01c6d3...`, ours was
`f41eb305...`). With `pullPolicy: IfNotPresent` the node that still caches the old build reuses
it; another node pulls the newer v11.1.0 build (same Node 22 / Debian 12 line). If an EXACT
restore is needed, replace the revert with
`tag: v11.1.0@sha256:f41eb305ff20d57e1ea0d89a68d9484f9655b547286cc08bf3df8a1ce9991edf`
(verified still pullable from registry-1.docker.io 2026-10-05, HTTP 200).

Confirm the cluster is back: G1 shows a v11 digest, G3 prints `v22.*` / `debian=12`, G4 all three
`True`, G5 counts equal `$W/*-before.txt`, G6 200.

**If G5 showed a fresh install (data not seen)** — the only scenario needing more than a revert:
1. Revert as above first (stop writing to the volume with the new image).
2. If after the revert the counts still do not match the baseline, restore from the backitup
   tarball of today (`/opt/iobroker/backups/iobroker_<today>-02_48_10_backupiobroker.tar.gz`) with
   `iobroker restore <file>` in the pod (operator-present), or
3. Longhorn path (docs/sops/backup.md): scale the HR to 0 (suspend the HR + set replicas 0 in git),
   restore the §2.4 backup to a new volume and repoint per `docs/sops/longhorn.md` (static PV,
   `volumeHandle` is immutable — a new PV/PVC pair is required). Operator-present only.

## 6. Interference notes

- **app-template-5.2.1 (vetted)** edits the same `helm-release.yaml` (chart line) and its
  `--compare-workloads` gate includes `sts/iobroker`; same window = GEN_CHANGED in its gate and a
  mixed change in ours. Listed in `conflicts_with`; the app-template plan does **not** yet list
  `iobroker-12.0.0` — reciprocal entry needed in that file (reported as a repo correction, not
  edited here). Either order works; the line edits do not overlap, so whichever runs second
  rebases trivially.
- **helm-drift-detection** touches every HR incl. this one; **flux-reconciler-impersonation**
  (exclusive) re-identities the apply path; **kube-prometheus-stack-91.9.0 (91.4.1 executed 2026-09-26)** would take G7's
  instrument down. All in `conflicts_with`.
- **Longhorn backup timing:** the storage RecurringJob `daily-backup-all-volumes` fires 03:00;
  the nightly window starts 03:30. §2.4 requires today's iobroker-config backup to be Completed
  before the roll so the pod restart does not detach the volume mid-backup.
- **backitup** runs at 02:48 — finished before the window; nothing to coordinate.
- No shared infra perturbed: the HTTPRoute and Service objects are not edited (only their backend
  pod restarts, ~2 min unavailability of the admin UI). No MQTT/Node-RED/VIS consumers exist.
- Eligible for the unattended nightly window on the facts (risk low, capability_change false,
  git-revert rollback, no reboot) once reviewed.
