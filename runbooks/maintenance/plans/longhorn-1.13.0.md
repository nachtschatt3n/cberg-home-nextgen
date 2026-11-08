---
plan_id: longhorn-1.13.0
component: longhorn
pr: null                              # no Renovate PR exists (gh pr list --search longhorn: none open);
                                      # the bump reaches us via coverage.py's direct-bump lane and is
                                      # HELD by the `*longhorn*` max: patch deny rule (8201c9dc).
kind: chart
current: "1.12.1"
target: "1.13.0"
update_type: minor
risk: high                            # storage engine under all 79 volumes (75 attached + 4 detached, live 2026-11-06); the upgrade is ONE-WAY
                                      # (upstream downgrade prevention, §5); 25 Kustomizations (live 2026-11-06; 35 on 10-05)
                                      # dependsOn storage/longhorn -> cluster-wide Flux amber for
                                      # 5-15 min (docs/sops/longhorn.md "Chart Upgrade Storm").
est_duration_min: 70                  # pre-checks 15 + Phase A (chart, storm settle, verify) 30 +
                                      # Phase B (engine drain, async) 25. Phase B is SEPARABLE: if it
                                      # has not started by T+45 min, stop after Phase A (manager
                                      # 1.13.0 + engines 1.12.1 is a supported state) and re-window B.
needs_reboot: false
touches:
  namespaces: [storage]
  resources:
    - helmrelease/longhorn
    - daemonset/longhorn-manager       # rolls; serves the admission webhook on :9502
    - deployment/longhorn-ui
    - deployment/longhorn-driver-deployer
    - deployment/longhorn-global-manager   # NEW in 1.13.0, 3 replicas
    - "deployment/csi-attacher, csi-provisioner, csi-resizer, csi-snapshotter"   # re-created by the driver deployer under the NEW longhorn-csi-service-account;
                                      # images: csi-provisioner v5.3.0->v6.3.0, csi-attacher v4.12.0->v4.13.0 (resizer v2.2.1, snapshotter v8.6.0 unchanged)
    - daemonset/longhorn-csi-plugin    # node-driver-registrar v2.17.0->v2.18.0, livenessprobe v2.19.0->v2.20.0
    - "daemonset/engine-image-ei-* (new v1.13.0 engine image DaemonSet)"
    - "instancemanager/* (new v1.13.0 instance-manager pod per node)"
    - "crd/instancemanagerupgradecontrols.longhorn.io, instancemanagerupgrades.longhorn.io, snapshotgroups.longhorn.io"   # NEW CRDs
    - "clusterrole+clusterrolebinding/longhorn-csi-role, longhorn-csi-secret-role; role+rolebinding/longhorn-csi-role; serviceaccount/longhorn-csi-service-account"   # NEW RBAC
    - setting/concurrent-automatic-engine-upgrade-per-node-limit   # Phase B: 0 -> 1 -> 0 (CR op, not in git)
    - "volume/* (79 on 2026-11-06, all v1: 75 attached + 4 detached; Phase B live-upgrades the attached ones and RE-POINTS the detached ones, 34abe2bb)"
    - "systembackup/pre-1-13-0-<date>  (created in pre-check §2.6)"
    - "deployment/mealie (ns office) — restarted once in §4.4 as the attach/IO probe"
  shared:
    - storage/longhorn                # every stateful app in the cluster rides it
    - flux                            # 25 Kustomizations (live 2026-11-06) dependsOn storage/longhorn -> storm
    - monitoring                      # §4 reads Prometheus; longhorn-backend is a scrape target
                                      # whose reachability a chart default already broke once (3c73a7b0)
    - cifs/backups                    # the BackupTarget (NAS //…/backups) is written by the §2.6
                                      # SystemBackup; no CIFS StorageClass/PVC is touched
depends_on: []
conflicts_with:
  # Re-derived 2026-11-06 from every open plan's frontmatter (rule 4). Dead refs to plans no longer in
  # plans/ removed; executed jellyfin-config-rwo-migration dropped (executed now:2026-10-23).
  - postgres-digest-refresh-2026-11   # reciprocal, added 2026-11-08 (DB-restart plan; sun-attended:2026-12-20)
  - redis-fleet-8.10.3   # reciprocal, 2026-11-02 sweep 2ad957af (sun-attended:2026-11-29)
  - tube-archivist-elasticsearch-9.5.5   # reciprocal, added 2026-10-26 (sweep a1721200 plan review)
  - grafana-chart-14.4.0   # reciprocal, added 2026-10-26 (sweep a1721200 plan review)
  - etcd-timeouts-5000-500           # reciprocal; that plan is status: blocked, window null (2026-11-06). NOT a
                                      # dependency of this plan: both read etcd/control-plane health, so never the
                                      # same slot; either order is fine
  - talos-linux-1.14.5                # node roll restarts instance-managers + rebuilds replicas; never
                                      # pair with a storage-engine upgrade (same rule as 34abe2bb); it
                                      # depends_on THIS plan (sun-attended:2026-11-22)
  - flux-oci-chart-sources            # moves the longhorn HelmRepository source (shared storage/longhorn, flux)
  - flux-reconciler-impersonation     # Flux control-plane change (status blocked); same storm reasoning
  - bitnamilegacy-exit-nextcloud-db   # allocates a new Longhorn volume (status blocked)
  - otbr-thread-rcp-recovery          # scales otbr 0 -> 1, which ATTACHES otbr-data (pvc-da17b5c6-…), one of
                                      # the 4 ruled detached volumes in §2.2a; the census and Phase B
                                      # re-point would change underneath this plan
  - otbr-0.4.0                        # Recreate roll of the same pod/volume; same reason
  - anythingllm-1.19                  # reciprocal: re-attaches a Longhorn volume
  # 2026-11-06: removed edot-collector-0.164.0 - plan executed in the NOW run 2026-11-06 and retired (dead ref in maintenance-plan.py --validate).
  - icloud-drive-fleet-2.3.0          # reciprocal: Recreate detaches/re-attaches two Longhorn volumes
  - open-webui-0.13.0                 # reciprocal: copies/may restore a Longhorn volume
exclusive: true                       # the storm fans out to 25 dependents (+ transitive); any other
                                      # plan's Flux-Ready gate in the same slot reads false-red, and
                                      # a one-way storage change must not share attribution.
security_ref: F-878b4088              # csi-provisioner (highest of the set); see finding_refs; detail stays in the DB
capability_change: true               # NOT "to be safe": 1.13.0 adds 3 new CRD kinds (new API surface),
                                      # a new cluster-scoped workload (longhorn-global-manager running
                                      # the pod/PV controllers) and a new ServiceAccount with
                                      # cluster-wide Secret `get` (longhorn-csi-service-account). No
                                      # new feature is switched ON by our values, but the permission
                                      # and API surface change is real.
rollback_class: one-way               # upstream: "Once you successfully upgrade to v1.13.0, you will
                                      # not be allowed to revert to the previously installed version."
finding_refs:
  - F-f79c74ac                        # plan: 1.13.0 had no deny rule (now held)
  - F-4125346e                        # version: longhorn chart 1.12.1 -> 1.13.0
  - F-723fbe83                        # longhorn-manager image (clears in Phase A)
  - F-205433dd                        # longhorn-ui image (clears in Phase A)
  - F-3bc71aff                        # longhorn-engine image (clears in Phase B)
  - F-21e6a381                        # longhorn-instance-manager image (clears in Phase B)
  - F-23a73fba                        # longhorn-share-manager image (see §4.8 — may need a remount)
  - F-878b4088                        # csi-provisioner v5.3.0 -> v6.3.0 (clears in Phase A; highest)
  - F-8cbf9aa6                        # csi-attacher v4.12.0 -> v4.13.0 (clears in Phase A)
  - F-449e59eb                        # csi-node-driver-registrar v2.17.0 -> v2.18.0 (clears in Phase A)
  - F-e5ceb782                        # livenessprobe v2.19.0 -> v2.20.0 (clears in Phase A)
premises:
  # All read-only single pipelines. Values measured live 2026-10-05; all 7 re-run PASS 2026-11-06 (revision for sweep 471de4f9 NEEDS-FIX).
  - id: longhorn-hr-chart-1-12-1-ready
    why: >-
      §3 A1's sed anchors on "1.12.1" and §5 case 1 reverts to it. A failed/in-flight release, or 1.13.0
      already applied behind the plan's back, makes the anchor and the rollback target wrong. Prints a
      different version or False and fails.
    run: kubectl get helmrelease -n storage longhorn -o jsonpath='{.spec.chart.spec.version} {.status.lastAttemptedRevision} {.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: 1.12.1 1.12.1 True
  - id: longhorn-settings-pre-state
    why: >-
      The plan is written for manager v1.12.1 (one minor step = supported path), V1-only volumes (the V2
      linked-clone breaking item and the "live upgrade only from v1.12.2" caveat are V2-only), and the
      engine drain OFF (so Phase A leaves engines on v1.12.1 and Phase B is the deliberate 0->1->0 drain).
      Any other value prints differently and fails.
    run: kubectl get settings.longhorn.io -n storage current-longhorn-version v2-data-engine concurrent-automatic-engine-upgrade-per-node-limit -o jsonpath='{range .items[*]}{.metadata.name}={.value} {end}'
    expect_exact: current-longhorn-version=v1.12.1 v2-data-engine=false concurrent-automatic-engine-upgrade-per-node-limit=0
  - id: k8s-server-minor-ge-34
    why: >-
      Release-notes breaking change: csi-provisioner v6.3.0 requires Kubernetes >= v1.34. Matches 34-39 and
      any 4x+ minor; prints e.g. 33 and fails below the floor.
    run: kubectl version -o json | jq -r '.serverVersion.minor'
    expect_matches: "^(3[4-9]|[4-9][0-9])$"
  - id: backuptarget-available
    why: >-
      The data net for a one-way upgrade is fresh per-volume backups (§2.4) and the SystemBackup (§2.6);
      both write to this BackupTarget. False/empty means neither exists.
    run: kubectl get backuptarget -n storage default -o jsonpath='{.status.available}'
    expect_exact: "true"
  - id: storage-zero-networkpolicies
    why: >-
      The 1.12.1 trap (3c73a7b0): chart-default NetworkPolicies cut the Prometheus scrape. §4.3 compares
      against 0; a non-zero baseline means the pin is already broken and §4.3 cannot attribute.
    run: kubectl get networkpolicy -n storage -o name | wc -l | tr -d ' '
    expect_exact: "0"
  - id: longhorn-detached-set-is-the-ruled-four
    why: >-
      §2.2a asks the operator for one ruling per DETACHED volume (rollback floor? backup older than
      detach accepted? Phase B engine re-point accepted?). The rulings are only valid for exactly this
      set. A fifth detached volume (an app crashed and released its PVC), or one of the four re-attached
      (otbr scaled back to 1), or one retired, prints a different list and fails -> re-measure and
      re-rule. Measured 2026-11-06.
    run: kubectl get volumes.longhorn.io -n storage -o jsonpath='{range .items[?(@.status.state=="detached")]}{.metadata.name}{" "}{end}'
    expect_exact: jellyfin-config pvc-da17b5c6-0d8c-42cf-9a25-bc444ac9a71d uzeit-de-fileadmin uzeit-de-uploads
  - id: longhorn-state-robustness-set
    why: >-
      "Avoid upgrading when volumes are in the Faulted status" (upstream). The only state/robustness
      pairs allowed are attached/healthy and detached/unknown; a degraded or faulted volume adds a token
      (e.g. attached/degraded) and fails. Measured 2026-11-06.
    run: kubectl get volumes.longhorn.io -n storage -o jsonpath='{range .items[*]}{.status.state}/{.status.robustness}{"\n"}{end}' | sort -u | tr '\n' ' '
    expect_exact: attached/healthy detached/unknown
review: ready-for-go@2026-11-06   # sweep 471de4f9: needs-fix (4 blockers: detached-volume census, backup timing, one-hot robustness gate, unpassable §4.6/4.7) -> planner fixed -> delta re-review ready-for-go (each changed gate shown failing on known-bad, passing live)
status: vetted   # 2026-11-06 re-vetted; HUMAN-GATED: operator GO + 4 detached-volume rulings (§2.2a) + 1.12.2 hold/retarget decision required
window: "sun-attended:2026-11-15"   # scheduled 2026-10-05: exclusive Sunday, 70 of 180; one week BEFORE talos-linux-1.14.5 (11-22, operator ordering 2026-11-02, which depends_on this plan). etcd-timeouts-5000-500 (was 11-08) is blocked/unwindowed since; this plan never depended on it, so the 11-15 slot stays viable
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/longhorn.md
  - docs/sops/storage-safety.md
  - docs/sops/backup.md
  - docs/sops/flux-dependency-revision-gate.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-10-01"
---

# Longhorn 1.12.1 -> 1.13.0 (chart + manager, then live engine drain)

## 1) Summary & why held

**What changes.** `kubernetes/apps/storage/longhorn/app/helmrelease.yaml`
`spec.chart.spec.version` `"1.12.1"` -> `"1.13.0"` (appVersion v1.13.0). Then,
in the same window, a live engine upgrade of every volume from
`longhorn-engine:v1.12.1` to `v1.13.0` by temporarily raising
`concurrent-automatic-engine-upgrade-per-node-limit` 0 -> 1 -> 0 — the exact
CR operation used for the 1.12.1 engine drain (34abe2bb).

**Why held.** The `*longhorn*` `max: patch` rule in
`runbooks/auto-update-policy.yaml` (8201c9dc, F-f79c74ac). Before that rule,
1.13.0 was held only by the 48h cooldown and would have landed unattended.
Three facts make it a planned change and not a false positive:

1. **It is one-way.** Upstream upgrade doc (longhorn.io/docs/1.13.0/deploy/upgrade):
   > "Starting with v1.5.0, Longhorn only supports upgrades from one minor
   > version to the next … Warning: Once you successfully upgrade to v1.13.0,
   > you will not be allowed to revert to the previously installed version."
   A `git revert` after a successful upgrade does NOT roll back — the
   pre-upgrade hook rejects the downgrade. See §5.
2. **Breaking change, checked:** release notes, "Breaking Changes":
   > "Because the CSI external-provisioner is upgraded to v6.3.0, all clusters
   > must be running Kubernetes v1.34 or later before installing or upgrading
   > to Longhorn v1.13.0."
   Live: server `v1.36.0` on all three nodes; chart `kubeVersion: '>=1.34.0-0'`.
   **Met.** The other breaking item (legacy V2 linked-clone volumes) does not
   apply: `v2-data-engine=false`, 79/79 volumes `dataEngine=v1` (re-measured 2026-11-06; 80 on 2026-10-05, 94 on 2026-10-01).
3. **Architecture moves inside a minor** (measured by `helm template` of both
   charts with OUR `spec.values`, `--kube-version 1.36.0`): 47 -> 58 objects.
   New: `Deployment longhorn-global-manager` (3 replicas, runs the cluster-wide
   pod and PV controllers that previously lived in the manager DaemonSet —
   upstream: "Before upgrading, make sure at least one of its pods can be
   scheduled"); CSI sidecars move to a dedicated `longhorn-csi-service-account`
   with new ClusterRole/Role bindings; 3 new CRDs
   (`instancemanagerupgradecontrols`, `instancemanagerupgrades`,
   `snapshotgroups`, all `v1beta2`). **No existing CRD changes its
   served/storage versions** (diffed). Rendered ConfigMaps, Services and
   StorageClasses are identical apart from the version label.

**The 1.12.1 trap, re-checked for 1.13.0.** 1.13.0 keeps
`networkPolicies.restrictInternalTraffic: true` as the chart DEFAULT and
renders **6 NetworkPolicies** without our pin. Our top-level
`networkPolicies.restrictInternalTraffic: false` (3c73a7b0) is still honoured —
rendered with our values: **0 NetworkPolicies** on both 1.12.1 and 1.13.0. 1.13.0
also adds `networkPolicies.metricsScrapeSources` (the allow-list hook the
3c73a7b0 note said adoption would need); adopting the hardening stays a
separate plan — do NOT flip it here.

**Upgrade path.** 1.12.1 -> 1.13.0 is `x.y.* -> x.(y+1).*`: supported. The
release notes' "live upgrade only from v1.12.2" caveat is about **V2** volumes
only (none here). Do not wait for v1.12.2.

**Moving base: v1.12.2 is in release candidacy** (`v1.12.2-rc4` published
2026-11-05, rc1..rc4 since 2026-10-15; `gh api repos/longhorn/longhorn/releases`,
2026-11-06). A GA 1.12.2 is a PATCH, and the `*longhorn*` rule is `max: patch`,
so it is AUTO-eligible: once its cooldown lapses it can land UNATTENDED at a
`nightly` Step 0 before 11-15 (manager roll + the 25-Kustomization storm, engines
staying on v1.12.1 because the drain limit is 0). If that happens this plan's
premises `longhorn-hr-chart-1-12-1-ready` and `longhorn-settings-pre-state` FAIL
(they read 1.12.2 / v1.12.2) — that is the intended stop, not a bug. Two paths,
operator's choice:
- **Recommended: hold the base still until this plan has run.** Operator edits
  the `*longhorn*` rule in `runbooks/auto-update-policy.yaml` to a full hold
  (drop `max: patch`; time-boxed "until longhorn-1.13.0 executes", like the
  `*kube-prometheus-stack*` rule) — a code-reviewed policy change the planner
  does not make. Rationale: an unattended storage-manager roll the week before
  a one-way minor upgrade moves both the rollback baseline (§5 case 1) and the
  §2/§4 measurements this plan was reviewed against.
- **Or accept 1.12.2 and retarget in place** (README "When the held target
  MOVES"; keep the plan_id): `current: "1.12.2"`; A1's sed anchor `"1\.12\.1"`
  -> `"1\.12\.2"`; premise `longhorn-hr-chart-1-12-1-ready` -> `1.12.2 1.12.2 True`;
  `longhorn-settings-pre-state` -> `current-longhorn-version=v1.12.2`; §2.1 and
  §5 case 1 expect 1.12.2. 1.12.2 -> 1.13.0 is still exactly one minor
  (supported). Engines would still be on v1.12.1 (limit 0), so Phase B drains
  v1.12.1 -> v1.13.0 as written; §4.2's "v1.12.1 row" then reads alongside an
  unused v1.12.2 EngineImage (refCount 0). Re-read the 1.12.2 chart's
  rendered NetworkPolicies (the 3c73a7b0 trap) before re-review.

**Engine/instance-manager behaviour (why Phase B exists).** Upstream:
> "first upgrade Longhorn manager to the latest version, then manually upgrade
> the Longhorn engine … Since Longhorn v1.1.1, we provide an option to help you
> automatically upgrade engines."
Live `concurrent-automatic-engine-upgrade-per-node-limit` = `0`, so after
Phase A every volume stays on the v1.12.1 engine and the three v1.12.1
instance-manager pods keep running beside new v1.13.0 ones. That is a
supported, compatible state (the gate in §4.2 asserts `INCOMPATIBLE=false`),
but it leaves the engine and instance-manager findings open. Phase B drains.

**Security driver — detail withheld from this public repo.** Tracked as
F-723fbe83 (manager), F-205433dd (ui), F-3bc71aff (engine), F-21e6a381
(instance-manager), F-23a73fba (share-manager): each a "newer upstream tag
available" finding on the v1.12.1 images. Chart 1.13.0 also bumps four CSI
sidecar images, each with its own finding and cleared in Phase A:
csi-provisioner v5.3.0 -> v6.3.0 (F-878b4088, the highest of the set and this
plan's `security_ref`), csi-attacher v4.12.0 -> v4.13.0 (F-8cbf9aa6),
csi-node-driver-registrar v2.17.0 -> v2.18.0 (F-449e59eb), livenessprobe
v2.19.0 -> v2.20.0 (F-e5ceb782). Tags read from `helm show values
longhorn/longhorn --version 1.13.0` and the live objects 2026-10-05;
csi-resizer v2.2.1 and csi-snapshotter v8.6.0 are unchanged — so **F-5281ebca
(csi-resizer) and F-05d645cb (csi-snapshotter) do NOT clear with this plan**
and are deliberately not in `finding_refs`; they need a later chart that bumps
those sidecars. `runbooks/policy-cli.py finding show <id>`.
Convention: `docs/sops/vulnerability-disclosure.md`.

**Freshness caveat.** 1.13.0 was published 2026-09-29 (still the newest
stable release on 2026-11-06; no 1.13.1 release or rc — only `v1.13.1-dev-*` dev tags). Enforced as pre-check §2.0 — not as a premise, because
the only premise-legal read (`helm show chart` from the local repo cache)
cannot fail on a newer release until someone runs `helm repo update`, which
is not a read.

## 2) Pre-checks (all read-only except 2.6; every one must PASS)

Run from the repo root on the Mac mini (zsh). The frontmatter `premises:`
(`plan-premises.py longhorn-1.13.0`) cover the HR/setting/server/backup-target/
NetworkPolicy pre-state plus the detached-volume set and the state/robustness set; 2.1-2.5 re-read the same facts with context.

2.0 **1.13.0 is still the newest 1.13.x** (upstream, not the local cache).
```bash
gh api repos/longhorn/longhorn/releases --jq '[.[]|select(.prerelease|not)|.tag_name][0:3]|join(" ")'
# PASS: first token is v1.13.0 (2026-11-06: "v1.13.0 v1.12.1 v1.11.3"). If it prints v1.13.1 (or later
# 1.13.x): STOP, retarget THIS plan in place (keep the plan_id; README "When the held target MOVES")
# and re-review. If a GA v1.12.2 appears AND §2.1 reads 1.12.2: the base moved — follow the
# retarget path in §1 "Moving base" (STOP and re-review; do not run the 1.12.1-anchored steps).
# Also read the Release-Known-Issues wiki entry for v1.13.0:
# https://github.com/longhorn/longhorn/wiki/Release-Known-Issues — a known data-path issue = STOP.
# An error/empty print (gh unauthenticated, rate-limited) is a FAIL, not a pass.
```

2.1 **Chart and cluster at the expected pre-state.**
```bash
kubectl -n storage get hr longhorn -o jsonpath='{.spec.chart.spec.version} {.status.conditions[?(@.type=="Ready")].status}{"\n"}'
# PASS: 1.12.1 True   (FAILS on 1.12.2 if a GA patch auto-landed — see §1 "Moving base")
kubectl version -o json | python3 -c "import sys,json;v=json.load(sys.stdin)['serverVersion'];print(v['major'],v['minor'])"
# PASS: minor >= 34 (live 2026-10-01: 1 36)
kubectl -n storage get settings.longhorn.io current-longhorn-version default-engine-image v2-data-engine concurrent-automatic-engine-upgrade-per-node-limit -o custom-columns=N:.metadata.name,V:.value --no-headers
# PASS: v1.12.1 / longhorn-engine:v1.12.1 / false / 0
```

2.2 **Volume census: every ATTACHED volume healthy, the DETACHED set exactly the
four ruled in 2.2a, none faulted/degraded, none V2** (upstream: "Avoid upgrading
when volumes are in the Faulted status"). Live 2026-11-06 is NOT one uniform
line: 75 attached + 4 detached. A detached Longhorn volume reads robustness
`unknown` (no running engine to judge; all four on 2026-11-06), so "unknown" is
legitimate ONLY on the named detached four.
```bash
kubectl -n storage get volumes.longhorn.io -o jsonpath='{range .items[*]}{.spec.dataEngine} {.status.state} {.status.robustness} {.status.currentImage}{"\n"}{end}' | sort | uniq -c
# PASS: exactly these two lines (2026-11-06):
#   75 v1 attached healthy docker.io/longhornio/longhorn-engine:v1.12.1
#    4 v1 detached unknown docker.io/longhornio/longhorn-engine:v1.12.1
# The attached count may differ from 75 only if volumes were added/retired since 11-06 (then the
# new number is $ATTACHED). FAILS (STOP + triage) on: any third line — "attached degraded",
# "attached faulted", "attached unknown", a v2 line, or an engine other than v1.12.1.
CENSUS=$(kubectl -n storage get volumes.longhorn.io -o name | grep -c .)
ATTACHED=$(kubectl -n storage get volumes.longhorn.io -o jsonpath='{range .items[?(@.status.state=="attached")]}{.metadata.name}{"\n"}{end}' | grep -c .)
echo "CENSUS=$CENSUS ATTACHED=$ATTACHED"
# PASS: CENSUS == ATTACHED + 4  (2026-11-06: CENSUS=79 ATTACHED=75). $CENSUS (all volumes) and
# $ATTACHED (attached only) are DIFFERENT numbers from here on; §2.4/§4 say which one they use.
kubectl -n storage get volumes.longhorn.io -o jsonpath='{range .items[?(@.status.state=="detached")]}{.metadata.name}{" "}{end}'; echo
# PASS, exactly: jellyfin-config pvc-da17b5c6-0d8c-42cf-9a25-bc444ac9a71d uzeit-de-fileadmin uzeit-de-uploads
# (also the premise longhorn-detached-set-is-the-ruled-four). A fifth name = a workload released its
# volume since 11-06 -> STOP, find out why, and get a 2.2a ruling for it; a missing name = it was
# re-attached or retired -> drop its ruling, re-measure CENSUS/ATTACHED.
kubectl -n storage get volumes.longhorn.io -o jsonpath='{range .items[?(@.status.state=="attached")]}{.metadata.name} {.status.robustness}{"\n"}{end}' | grep -vc ' healthy$'
# PASS: 0 (2026-11-06: 0). Prints the number of attached volumes that are not healthy.
```

2.2a **Operator rulings for the four detached volumes — required, one per
volume, recorded in the window's GO record BEFORE Phase A starts and hard-gating
B2.** Why they matter here: (a) Phase B does NOT skip detached volumes — 34abe2bb
measured that the automatic engine upgrade re-points a detached volume's
`spec.image` directly (two sanctioned rollback floors moved without ever being
attached; only an explicit per-volume pin would exclude one); (b) a detached
volume is never backed up (`allow-recurring-job-while-volume-detached=false`,
live 2026-11-06), so its newest backup predates its detach (§2.4b reads
`OLDER-THAN-DETACH` for all four today).

| Volume | Consumer / why detached | Detached since (`lastPodRefAt`) | Newest backup | Ruling asked |
|---|---|---|---|---|
| `jellyfin-config` | `media/jellyfin-config` (RWX, longhorn-static). Orphan since the executed `jellyfin-config-rwo-migration` (now:2026-10-23) cut Jellyfin over to `jellyfin-config-rwo`; tracked as **F-013d6eca** (snapshot chain not pruned). Last mounted read-only by the copy Job `jf-rwo-copy`. That plan's 14-day retention ran from the 10-24 green check (~11-07); deleting it is a separate operator-approved storage plan, never this one. | 2026-10-23T12:53Z | 2026-10-23T12:27Z (26 min before the read-only copy; no writes after it by that plan's design) | **Is it still a rollback floor?** If YES: accept the Phase B engine re-point (restore-from-backup, the floor's real recovery path, does not depend on the engine version). If NO: either accept the same, or retire it in its own storage-safety plan BEFORE this window (then it leaves the set and the premise must be re-measured). |
| `pvc-da17b5c6-0d8c-42cf-9a25-bc444ac9a71d` | `home-automation/otbr-data` (dynamic `longhorn`). otbr scaled to `replicas: 0` in git 2026-10-30 (RCP stopped answering Spinel); waits on `otbr-thread-rcp-recovery` (draft). | 2026-10-30T22:02Z | 2026-10-29T23:03Z (~23 h before detach, while otbr-agent was crash-looping) | Accept the ~23 h backup gap (the Thread dataset is also held in HA `thread.datasets`) and the engine re-point; and keep both otbr plans out of this slot (`conflicts_with`). |
| `uzeit-de-fileadmin` | No PV/PVC any more: uzeit-de decommissioned in 14d9a2259 (2026-10-23, "volumes Retain + NAS backup, DB dumped"); the Longhorn volumes were kept deliberately. | 2026-10-23T11:05Z | 2026-10-22T23:03Z (~12 h before detach) | Accept the ~12 h gap + engine re-point, or retire in a separate storage-safety plan first. |
| `uzeit-de-uploads` | Same as above. | 2026-10-23T11:05Z | 2026-10-22T23:03Z | Same as above. |

Obtain all four rulings at GO time (one question batch). Hard gate: a volume
without a recorded ruling = do not start B2 (Phase B is what moves a detached
volume's engine; the Phase A manager roll does not touch a detached volume's
data).

2.3 **No failed BackingImage** (upstream manual check).
```bash
kubectl -n storage get backingimages.longhorn.io --no-headers 2>/dev/null | wc -l   # expect 0 (none in use; 0 on 2026-11-06)
```

2.4 **Backups fresh** (upstream prerequisite: "Always back up volumes before
upgrading"). Live schedule (`kubectl -n storage get cronjob`, 2026-11-06; no
`timeZone`, so UTC): trim `0 22 * * *`, snapshot-cleanup `30 22 * * *`,
`daily-backup-all-volumes` `0 23 * * *` (RecurringJob group `default`). At a
09:00 Europe/Berlin start in November (08:00Z) the newest run is ~9 h old.

2.4a — ATTACHED volumes, `--max-hours 14` (09:00 CET start leaves ~5 h of
slack; a missed 23:00Z run makes every line ~33 h STALE):
```bash
.venv/bin/python3 runbooks/longhorn-backup-age.py $(kubectl -n storage get volumes.longhorn.io -o jsonpath='{range .items[?(@.status.state=="attached")]}{.metadata.name}{" "}{end}') --max-hours 14 > /tmp/lh-pre-backup.txt; echo rc=$?
echo "FRESH=$(grep -c ' FRESH ' /tmp/lh-pre-backup.txt) other=$(grep -vc ' FRESH ' /tmp/lh-pre-backup.txt)"
# PASS: rc=0 and FRESH == $ATTACHED, other=0. Measured 2026-11-06 02:13Z: rc=0, FRESH=75 other=0
# (newest 3.2 h). The helper exits 1 on any STALE/NONE and 2 on a lookup error; an EMPTY volume
# list (jsonpath matched nothing) is an argparse error, rc=2 — measured, fails closed.
# KNOWN-BAD control (why the set is split): the same command over ALL volumes
# (`-o jsonpath='{.items[*].metadata.name}'`) reads rc=1 with the 4 detached STALE (171-339 h)
# on 2026-11-06, so the pre-2026-11-06 form of this check could never pass.
kubectl -n storage get backuptarget default -o jsonpath='{.status.available}{"\n"}'   # PASS: true
```

2.4b — DETACHED volumes: a confirmed backup exists, and is it newer than the
detach? (zsh, BSD-safe; ISO-8601 Z timestamps compare lexically.)
```bash
.venv/bin/python3 runbooks/longhorn-backup-age.py $(kubectl -n storage get volumes.longhorn.io -o jsonpath='{range .items[?(@.status.state=="detached")]}{.metadata.name}{" "}{end}') --max-hours 2400 >/dev/null; echo detached-confirmed-rc=$?
# PASS: rc=0 — each detached volume HAS a confirmed Completed backup (2026-11-06: rc=0). rc=1 = NONE -> STOP.
kubectl -n storage get volumes.longhorn.io -o jsonpath='{range .items[?(@.status.state=="detached")]}{.metadata.name} {.status.lastBackupAt} {.status.kubernetesStatus.lastPodRefAt}{"\n"}{end}' | python3 -c 'import sys
for l in sys.stdin:
    f = l.split() + ["", ""]
    n, b, d = f[0], f[1], f[2]
    v = "COVERS-DETACH" if (b and d and b >= d) else "OLDER-THAN-DETACH"
    print(n, v, "backup=" + (b or "NONE"), "detach=" + (d or "NONE"))'
# PASS per volume: COVERS-DETACH, OR OLDER-THAN-DETACH with that volume's 2.2a ruling recorded.
# 2026-11-06 reads OLDER-THAN-DETACH for all four (backup/detach pairs as in the 2.2a table), so
# without the rulings this check FAILS today. A missing timestamp prints NONE and fails closed.
```

2.5 **Scrape baseline** (the instrument §4 reads). `longhorn_volume_robustness`
is ONE-HOT over a `state` label (`healthy|degraded|faulted|unknown`, one series
each per volume, exactly one ==1): `count(longhorn_volume_robustness==1)` is
therefore the volume COUNT whatever their health and can never fail on a
degraded volume. Health is read per state:
```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
for q in 'count(up{job="longhorn-backend"}==1)' 'count(longhorn_volume_robustness{state="healthy"}==1)' 'count(longhorn_volume_robustness{state="unknown"}==1)' 'count(longhorn_volume_robustness{state=~"degraded|faulted"}==1) or vector(0)' 'count(longhorn_volume_robustness==1)' 'count(longhorn_instance_manager_cpu_usage_millicpu)'; do
  echo "$q => $(curl -s --data-urlencode "query=$q" http://localhost:19090/api/v1/query | python3 -c 'import sys,json;r=json.load(sys.stdin)["data"]["result"];print(r[0]["value"][1] if r else "EMPTY")')"; done
kill $PF 2>/dev/null
# PASS, in order: 3 / $ATTACHED / 4 / 0 / $CENSUS / 3
# Measured 2026-11-06 02:2xZ:  3 / 75 / 4 / 0 / 79 / 3. "EMPTY" on any line = STOP (the
# degraded|faulted line carries `or vector(0)` so a healthy fleet reads 0, not EMPTY).
# The unknown=4 line is the live CONTROL that the healthy count can fail: the 4 detached volumes
# drop out of it (75, not 79) while the unfiltered count still reads 79.
kubectl -n storage get networkpolicy -o name | wc -l    # PASS: 0
```

2.6 **Longhorn SystemBackup** (upstream: "It is recommended to create a
Longhorn system backup before performing the upgrade"). The only existing
SystemBackups (`unas-v1`, `unas-v2`) are v1.6.2 from 2025 — useless. Volume
data is already covered by 2.4, so skip re-backing volumes:
```bash
D=$(date +%Y%m%d)
cat <<EOF | kubectl apply -f -
apiVersion: longhorn.io/v1beta2
kind: SystemBackup
metadata:
  name: pre-1-13-0-$D
  namespace: storage
spec:
  volumeBackupPolicy: disabled
EOF
# Wait until Ready (typically < 2 min):
kubectl -n storage get systembackups.longhorn.io pre-1-13-0-$D -o jsonpath='{.status.state} {.status.version}{"\n"}'
# PASS: "Ready v1.12.1". "Error" or stuck > 10 min -> STOP (backup target path is broken,
# which would also break every post-upgrade backup).
```

2.7 **No in-flight storage work.** No `otbr-thread-rcp-recovery` / `otbr-0.4.0`
(would attach a ruled detached volume), `talos-*`, or engine drain in progress
(`exclusive: true` keeps them out of the slot, but confirm):
`kubectl -n storage get volumes.longhorn.io -o jsonpath='{range .items[*]}{.status.currentImage}{" "}{.spec.image}{"\n"}{end}' | awk '$1!=$2' | wc -l` -> `0` (2026-11-06: 0).
Not running 22:00-00:00 UTC (= 23:00-01:00 CET): trim 22:00Z,
snapshot-cleanup 22:30Z, backup 23:00Z (`kubectl -n storage get cronjob`
verified 2026-11-06). The sun-attended slot (08:00-11:20Z in CET) is clear of all three.

## 3) Steps

### Phase A — chart 1.12.1 -> 1.13.0 (GitOps)

A1. Edit the version (dry-tested on a scratch copy, BSD sed):
```bash
sed -i '' 's/^\([[:space:]]*version:[[:space:]]*\)"1\.12\.1"$/\1"1.13.0"/' kubernetes/apps/storage/longhorn/app/helmrelease.yaml
git diff kubernetes/apps/storage/longhorn/app/helmrelease.yaml
# Expected, exactly one hunk:
# -      version: "1.12.1"
# +      version: "1.13.0"
```
Do NOT touch `networkPolicies.restrictInternalTraffic: false` or the inert
`longhorn:` block. Do NOT add `spec.upgrade.remediation` / rollback — a Flux
rollback after a successful upgrade is a downgrade Longhorn refuses.

A2. Commit + push (shared worktree rules):
```bash
git commit --only kubernetes/apps/storage/longhorn/app/helmrelease.yaml -m "feat(longhorn): chart 1.12.1 -> 1.13.0 (plan longhorn-1.13.0)"
git show --stat HEAD && git log -1 --format=%s    # only the helmrelease; subject is yours
git push
```

A3. **Push nothing else until §4.1 converges** — every commit re-arms the
`dependsOn` revision gate for 25 Kustomizations (live 2026-11-06) (docs/sops/longhorn.md "Chart
Upgrade Storm"). Expect 5-15 min of cluster-wide Flux amber; do NOT roll back
on dependents' messages. Judge only `storage/longhorn` and revision
convergence (§4.1).

If the HelmRelease reports a failed upgrade with `pre-upgrade hooks failed`:
the upgrade did NOT happen (pre-upgrade checker refused it) -> read
`kubectl -n storage logs job/longhorn-pre-upgrade` and go to §5 case 1. If it
failed on `timeout` while §4.2 shows all new pods Ready, the upgrade applied
and only Helm's wait expired: operator-present, run
`flux reconcile hr longhorn -n storage --force` once to re-record it.

### Phase B — live engine drain v1.12.1 -> v1.13.0 (CR operation)

Start only if §4.1-§4.6 all PASS and the clock is <= T+45 min; otherwise end
the window after Phase A and re-window Phase B as its own slot.

B1. Confirm the new engine image is the default and deployed:
```bash
kubectl -n storage get engineimages.longhorn.io -o custom-columns=N:.metadata.name,IMG:.spec.image,STATE:.status.state,INCOMPAT:.status.incompatible,REF:.status.refCount
kubectl -n storage get settings.longhorn.io default-engine-image -o jsonpath='{.value}{"\n"}'
# PASS: a v1.13.0 row state=deployed incompatible=false; default = ...longhorn-engine:v1.13.0
```
B2. Enable the drain (one volume per node at a time — 34abe2bb precedent):
```bash
kubectl -n storage patch settings.longhorn.io concurrent-automatic-engine-upgrade-per-node-limit --type merge -p '{"value":"1"}'
```
B3. Watch progress (async; each live upgrade is a brief per-volume IO pause):
```bash
kubectl -n storage get volumes.longhorn.io -o jsonpath='{range .items[*]}{.status.currentImage} {.status.robustness}{"\n"}{end}' | sort | uniq -c
```
The 4 ruled detached volumes print robustness `unknown` throughout — expected;
per 34abe2bb they are re-pointed to v1.13.0 without being attached.
Abort criteria (go to §5 Phase B): any volume `faulted`; > 2 volumes
`degraded` for > 10 min; any `unknown` count above the detached 4 (an attached
volume lost its engine); any app pod with IO errors on its PVC.
B4. When every volume reports `v1.13.0` (or at the window's end, whichever
first), **always** return the limit to 0:
```bash
kubectl -n storage patch settings.longhorn.io concurrent-automatic-engine-upgrade-per-node-limit --type merge -p '{"value":"0"}'
kubectl -n storage get settings.longhorn.io concurrent-automatic-engine-upgrade-per-node-limit -o jsonpath='{.value}{"\n"}'   # PASS: 0
```
A partially drained fleet is a supported state; finish it in the next slot.

## 4) Verification

4.1 **Storm converged (the clearing test from docs/sops/longhorn.md).**
```bash
kubectl get endpoints -n storage longhorn-admission-webhook -o jsonpath='{range .subsets[*].addresses[*]}{.ip}{" "}{end}{"\n"}' | wc -w   # PASS: 3
kubectl -n storage get ds longhorn-manager -o jsonpath='{.status.desiredNumberScheduled} {.status.numberReady} {.status.updatedNumberScheduled}{"\n"}'   # PASS: 3 3 3
REV=$(kubectl -n flux-system get gitrepository flux-system -o jsonpath='{.status.artifact.revision}' | sed 's/.*sha1://' | cut -c1-8); echo "artifact=$REV"
flux get kustomizations -A | tail -n +2 | grep 'refs/heads/main@sha1:' | grep -cv "sha1:$REV"   # PASS: 0 within 20 min
```
Compare against the GitRepository's ARTIFACT revision, never local `git rev-parse
HEAD`: this is a shared worktree and another session's commit moves local HEAD
(and the artifact) independently; the artifact is what the Kustomizations
converge to. Confirm `artifact=` names the A2 commit or a descendant of it
(`git merge-base --is-ancestor <sha-of-A2> $REV && echo ok`). The
`refs/heads/main@` filter is defensive: other GitRepositories exist
(`csi-driver-smb`, `oc8`, `plex`); none sources a Kustomization today (0
non-main lines, 2026-10-05), but one that did would never carry this sha and
would read as permanent non-convergence.
Fails if: the webhook Service has no endpoints (prints < 3) or the DS is
stuck below desired (> 10 min => "wedged" per SOP; diagnose
`kubectl -n storage logs ds/longhorn-manager --previous`).

4.2 **CONTENTS ASSERTION: the manager is actually 1.13.0 and still accepts the old engine** — measured through the manager API and the EngineImage CR, compared to 2.1.
```bash
kubectl -n storage get settings.longhorn.io current-longhorn-version -o jsonpath='{.value}{"\n"}'   # PASS: v1.13.0
kubectl -n storage get ds longhorn-manager -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'   # PASS: ...longhorn-manager:v1.13.0
kubectl -n storage get engineimages.longhorn.io -o custom-columns=IMG:.spec.image,STATE:.status.state,INCOMPAT:.status.incompatible --no-headers
# PASS: the v1.12.1 row is "deployed false" (still compatible) and a v1.13.0 row is "deployed false".
# A "true" in INCOMPAT for v1.12.1 means volumes cannot be operated until upgraded -> start Phase B at once.
kubectl -n storage get deploy longhorn-global-manager -o jsonpath='{.status.readyReplicas}/{.spec.replicas}{"\n"}'   # PASS: 3/3 (>=1 is upstream's minimum)
kubectl -n storage get deploy csi-attacher csi-provisioner -o jsonpath='{range .items[*]}{.metadata.name}={.spec.template.spec.serviceAccountName} {.status.readyReplicas}{"\n"}{end}'
# PASS: both "=longhorn-csi-service-account 3". Still longhorn-service-account => the driver
# deployer has not rolled the CSI layer yet (wait); Ready < 3 => new SA lacks a permission.
```
CONTENTS ASSERTION: the four CSI sidecar images actually rolled (clears F-878b4088,
F-8cbf9aa6, F-449e59eb, F-e5ceb782) — measured from the live pod specs, compared
to the pre-state v5.3.0 / v4.12.0 / v2.17.0 / v2.19.0 (2026-10-05).
```bash
kubectl -n storage get deploy csi-provisioner csi-attacher -o jsonpath='{range .items[*]}{.metadata.name} {.spec.template.spec.containers[0].image} {.status.readyReplicas} {.status.updatedReplicas}{"\n"}{end}'
# PASS, exactly:
#   csi-provisioner docker.io/longhornio/csi-provisioner:v6.3.0 3 3
#   csi-attacher docker.io/longhornio/csi-attacher:v4.13.0 3 3
kubectl -n storage get ds longhorn-csi-plugin -o jsonpath='{range .spec.template.spec.containers[*]}{.name} {.image}{"\n"}{end}{.status.numberReady}/{.status.desiredNumberScheduled} upd={.status.updatedNumberScheduled}{"\n"}'
# PASS: node-driver-registrar ...csi-node-driver-registrar:v2.18.0, longhorn-liveness-probe
# ...livenessprobe:v2.20.0, longhorn-csi-plugin ...longhorn-manager:v1.13.0, and "3/3 upd=3".
kubectl -n storage get pod -l app=csi-provisioner -o jsonpath='{range .items[*]}{.spec.containers[0].image} {.status.phase}{"\n"}{end}' | sort | uniq -c
# PASS: one line "3 docker.io/longhornio/csi-provisioner:v6.3.0 Running" — the POD image, not only
# the Deployment template (a template on v6.3.0 with old pods still serving fails here).
```
A pre-state tag on any line = the driver deployer has not re-created the CSI
layer (wait <= 10 min after §4.1, then diagnose
`kubectl -n storage logs deploy/longhorn-driver-deployer`).

4.3 **Prometheus still scrapes longhorn-manager (the 3c73a7b0 regression class).**
```bash
kubectl -n storage get networkpolicy -o name | wc -l   # PASS: 0 (a non-zero count is the 1.12.1 trap again)
# then re-run the 2.5 Prometheus block >= 5 min after 4.1 passes
# PASS, in order: 3 / $ATTACHED / 4 / 0 / $CENSUS / >=3
#   (2026-11-06 baseline 3 / 75 / 4 / 0 / 79 / 3; IM count is 6 while old+new IMs coexist before
#   Phase B — also PASS). Run it again after Phase B: same PASS.
```
CONTROL: metric up — `up{job="longhorn-backend"}` must be 1 on all 3 manager
pods' NEW IPs; 3c73a7b0 is the measured negative (all three went 0 with the
NetworkPolicies present).
CONTROL: metric longhorn_volume_robustness — the gate is
`count(longhorn_volume_robustness{state="healthy"}==1) == $ATTACHED`. NOT
`count(longhorn_volume_robustness==1) == $CENSUS`: the metric is one-hot over
`state` (4 series per volume, exactly one ==1; `count by (state)` reads 79 for
each of healthy/degraded/faulted/unknown on 2026-11-06), so the unfiltered
count is the volume count and reads $CENSUS even with every volume degraded —
it is kept only as the exporter-completeness line. Known-bad reading that
proves the filtered gate can fail: `{state="unknown"}` reads **4** live (the
detached set) and those 4 are absent from the healthy count (75, not 79); a
volume going degraded/faulted after the roll moves the same way — healthy
drops below $ATTACHED and the `degraded|faulted` line goes above 0. An empty
result prints `EMPTY` and fails (the series is emitted by the manager, so a
silently dead exporter cannot pass).
CONTROL: metric longhorn_instance_manager_cpu_usage_millicpu — count >= 3.
CONTROL: alertname LonghornManagerDown — must NOT be firing 10 min after 4.1
(`expr: up{job="longhorn-backend"} == 0`, for 2m, in
`kubernetes/apps/monitoring/kube-prometheus-stack/app/longhorn-alerts.yaml`).
(`LonghornVolumeDegraded` is deliberately NOT a gate: its expression reads a
`robustness` label that `longhorn_volume_robustness` does not carry, so it
cannot fire — F-ff6e6d43. Volume health is gated by the
`{state="healthy"}==$ATTACHED` / `degraded|faulted == 0` controls above and the
§4.7 census.)

4.4 **CONTENTS ASSERTION: a real detach -> attach -> mount -> write/read round-trip through the NEW CSI layer** — measured on `office/mealie` (`mealie-data`, longhorn-static RWO, Deployment strategy `Recreate`, verified live), compared to a nonce written in the same step.
```bash
kubectl -n office rollout restart deploy/mealie && kubectl -n office rollout status deploy/mealie --timeout=300s
N=lh113-$(date +%s)
kubectl -n office exec deploy/mealie -c main -- sh -c "echo $N > /app/data/.lh-upgrade-probe && sync && cat /app/data/.lh-upgrade-probe && rm /app/data/.lh-upgrade-probe"
# PASS: prints exactly the nonce. FAILS on: pod stuck ContainerCreating (attach/mount via new
# csi-attacher/longhorn-csi-plugin broken — rollout status times out), "Read-only file system"
# or "Input/output error" (non-zero exit), or a different string.
kubectl -n office get pod -l app.kubernetes.io/name=mealie -o jsonpath='{.items[0].status.startTime}{"\n"}'   # must be AFTER the push time
```
Run 4.4 again after Phase B (the volume's engine has then been live-swapped).
Residual: the PROVISION path (csi-provisioner v6.3.0) is not exercised — no
scratch PVC is created, by rule; it is exercised by the next new PVC. The
positive gate for the provisioner is the §4.2 image + `3 3` readiness line.
Informational only (NOT a gate — absence of "error" in a log proves nothing,
and leader-election chatter can contain the word):
`kubectl -n storage logs deploy/csi-provisioner --since=30m | grep -i error | tail -5` —
read it, record it in the window report.

4.5 **UI serves and talks to the 1.13.0 manager** (CONTENTS, not 200).
```bash
kubectl -n storage port-forward svc/longhorn-frontend 18080:80 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s http://localhost:18080/v1/settings/current-longhorn-version | python3 -c "import sys,json;print(json.load(sys.stdin).get('value'))"
kill $PF 2>/dev/null
# PASS: v1.13.0 (measured pre-change through the same path: v1.12.1). An HTML body or
# a JSON error raises in python and prints a traceback = FAIL.
```

4.6 **Backups still work.**
- Immediately: `kubectl -n storage get backuptarget default -o jsonpath='{.status.available} {.status.lastSyncedAt}{"\n"}'` -> `true` and a timestamp AFTER the push.
- Next morning (deferred gate, the window agent records it in its report).
  The first post-upgrade backup is the `daily-backup-all-volumes` run at
  **23:00 UTC on the window day** (00:00 CET; CronJob `0 23 * * *`, no
  timeZone). Run the check the next morning between 07:00 and 12:00
  Europe/Berlin: at any time in that range the 14 h horizon starts AFTER the
  sun-attended window closed (11:20Z at the latest), so a FRESH line can only
  come from a backup taken under 1.13.0. Attached volumes only — detached ones
  are never backed up (`allow-recurring-job-while-volume-detached=false`) and
  would read STALE forever:
  ```bash
  .venv/bin/python3 runbooks/longhorn-backup-age.py $(kubectl -n storage get volumes.longhorn.io -o jsonpath='{range .items[?(@.status.state=="attached")]}{.metadata.name}{" "}{end}') --max-hours 14 > /tmp/lh-post-backup.txt; echo rc=$?
  echo "FRESH=$(grep -c ' FRESH ' /tmp/lh-post-backup.txt) other=$(grep -vc ' FRESH ' /tmp/lh-post-backup.txt)"
  # PASS: rc=0, FRESH == $ATTACHED, other=0. FAILS: a 1.13.0 backup regression leaves the pre-window
  # 23:00Z backups (~33 h old by then) -> STALE, rc=1. Known-bad form: over ALL volumes this reads
  # rc=1 because of the 4 detached (measured 2026-11-06) — do not "fix" it that way.
  ```
  CONTROL: alertname LonghornBackupFailed — not firing
  (`(longhorn_backup_state == 4) unless on(volume) (longhorn_backup_state == 3)`).
  CONTROL: metric longhorn_backup_state — non-empty (2026-10-01: 882 series).
  Note upstream fixed "Recurring-job pods report success after startup or volume
  execution errors" (#13587) in 1.13.0: a CronJob that was silently green may
  now honestly fail. A new failure here is signal, not upgrade breakage — triage it.

4.7 **Phase B result.**
```bash
kubectl -n storage get volumes.longhorn.io -o jsonpath='{range .items[*]}{.status.state} {.status.robustness} {.status.currentImage}{"\n"}{end}' | sort | uniq -c
# PASS: exactly two lines (attached gate + detached expectation, 34abe2bb):
#   <$ATTACHED> attached healthy docker.io/longhornio/longhorn-engine:v1.13.0
#   4 detached unknown docker.io/longhornio/longhorn-engine:v1.13.0
# FAILS on: any attached line still on v1.12.1 (drain incomplete -> finish next slot), any
# attached degraded/faulted/unknown line, or a detached count other than 4. A detached volume
# left on v1.12.1 (if Longhorn did not re-point it this time) is a NAMED residual, acceptable
# only for one of the 4 ruled volumes: it keeps the v1.12.1 EngineImage at refCount > 0 and
# F-3bc71aff partially open — record the name on the finding.
kubectl -n storage get instancemanagers.longhorn.io -o custom-columns=IMG:.spec.image,ST:.status.currentState --no-headers | sort | uniq -c
# PASS (may take minutes after the last volume): 3 x instance-manager:v1.13.0 running, 0 x v1.12.1
kubectl -n storage get engineimages.longhorn.io -o custom-columns=IMG:.spec.image,REF:.status.refCount --no-headers
# PASS: v1.12.1 refCount 0 (then GC'd). A non-zero residual must be NAMED volume-by-volume.
```

4.8 **Share-managers (F-23a73fba) — observe, do not force.** Two RWX
volumes have a share-manager pod (live 2026-11-06): `nextcloud-config` and
`oc8-sessions`. (`jellyfin-config`'s share-manager is gone — the volume has
been detached since the executed RWX->RWO migration, 2026-10-23.)
```bash
kubectl -n storage get pod -l longhorn.io/component=share-manager -o jsonpath='{range .items[*]}{.metadata.name} {.spec.containers[0].image}{"\n"}{end}'
# Expect 2 lines (share-manager-nextcloud-config, share-manager-oc8-sessions); each still
# :v1.12.1 is NORMAL immediately after the window. A third line = an RWX volume was attached.
```
A share-manager pod is only re-created on the next remount of its RWX volume;
do NOT restart Nextcloud or oc8 for it here. nextcloud-config clears at
Nextcloud's next pod restart and oc8-sessions at oc8's (no open plan schedules
either on 2026-11-06). F-23a73fba closes only when both print `:v1.13.0`.
Record the per-pod state on the finding.

## 5) Rollback

**There is no chart rollback after a successful upgrade** (downgrade
prevention, §1). The procedure depends on where it failed:

**Case 1 — pre-upgrade hook refused (upgrade never happened).** §4.2 still
shows `current-longhorn-version=v1.12.1`. Safe to revert:
```bash
git revert --no-edit <sha-of-A2>    # restores version: "1.12.1"
git show --stat HEAD && git log -1 --format=%s
git push
kubectl -n storage get hr longhorn -o jsonpath='{.status.history[0].chartVersion} {.status.conditions[?(@.type=="Ready")].status}{"\n"}'   # PASS: 1.12.1 True
```
Then confirm 2.2 and 2.5 match their baselines.

**Case 2 — upgraded, but a regression (scrape lost, CSI attach failing, UI broken).**
Forward-fix, do NOT revert the version:
- Scrape lost / NetworkPolicies appeared: confirm `networkPolicies.restrictInternalTraffic: false`
  is still at the TOP LEVEL of `spec.values`; if 1.13.x changed its semantics,
  set `networkPolicies.metricsScrapeSources` to the monitoring namespace +
  Prometheus pod selector (from the chart's values.yaml comment) — a separate
  commit, after reading the rendered policy.
- CSI attach failing under the new SA: collect `kubectl -n storage logs deploy/csi-attacher`
  and `kubectl -n storage describe deploy/csi-attacher`; this is an upstream
  bug -> open/track the upstream issue and take the next 1.13.x patch (the
  `max: patch` rule lets it auto-apply).
- Volumes faulted/data loss (last resort): restore the affected attached
  volumes from the 23:00Z backups verified in 2.4a, and a detached one from the
  pre-detach backup named in 2.4b (the backup the operator accepted in 2.2a)
  (`docs/sops/backup.md` restore section);
  Longhorn resources from SystemBackup `pre-1-13-0-<date>` via a
  `SystemRestore` CR (docs/sops/longhorn.md / upstream "Restore Longhorn System").
  Note: a SystemRestore into a 1.13.0 install from a 1.12.1 backup is itself
  version-gated — it is a disaster-recovery path, not a downgrade.

**Phase B — partial or misbehaving drain.**
1. Stop it: patch the limit back to `0` (B4). In-flight upgrades finish; no new ones start.
2. A volume that misbehaves on the new engine can be live-upgraded BACK to the
   v1.12.1 engine image while that EngineImage is still deployed (refCount > 0
   keeps it from GC) — Longhorn UI -> volume -> Upgrade Engine -> select v1.12.1,
   one volume at a time, attended. Once the v1.12.1 EngineImage has GC'd this
   path is gone; that is why B4 runs before the window closes and 4.7 is
   checked before declaring Phase B done.
3. Confirm: rerun 4.4 and the 4.3 Prometheus block.

## 6) Interference notes

- **Exclusive slot.** A Longhorn manager roll takes down the admission webhook
  (served by longhorn-manager :9502) for the DaemonSet roll and fans out to 25
  Kustomizations that `dependsOn: storage/longhorn` (measured live 2026-11-06;
  the SOP says 36). Any other plan's "Flux Ready" gate in the same slot reads
  false-red, and every extra commit re-arms the storm. Hence `exclusive: true`
  on top of `conflicts_with`.
- **Window choice.** HUMAN-GATED (one-way + capability_change + storage floor).
  Recommended: **`sun-attended:2026-11-15`, exclusive** (70 of 180 min).
  `talos-linux-1.14.5` (`sun-attended:2026-11-22`, vetted) `depends_on` this
  plan (operator ordering 2026-11-02), so 11-15 gives the new engine a week and
  >= 2 green nightly backup cycles before the node roll; if Talos slips, the
  gap only grows. If THIS plan slips past 11-15 it pushes the Talos roll with
  it. `etcd-timeouts-5000-500` was meant to land 11-08 first; it is now
  `status: blocked`, `window: null` (2026-11-06). This plan never depended on
  it (`depends_on: []`) — the two only must not share a slot — so the 11-15
  slot stays viable whether or not etcd-timeouts runs before it. A
  `sat-attended` slot also fits the budget but runs into the following
  Sunday's attended work with no soak day. `nightly` (03:30 CET = 02:30Z) does
  not collide with the backup chain any more (trim 22:00Z, snapshot-cleanup
  22:30Z, backup 23:00Z, verified `kubectl -n storage get cronjob` 2026-11-06)
  but is unattended — not allowed for a one-way, human-gated storage change.
  Never 22:00-00:00 UTC.
- **Moving base — Longhorn 1.12.2 at nightly Step 0.** `v1.12.2-rc4` was
  published 2026-11-05. The `*longhorn*` rule is `max: patch`, so a GA 1.12.2
  is AUTO-eligible and can land unattended at any `nightly` Step 0 between now
  and 11-15 — a manager roll plus the 25-Kustomization storm with nobody
  present, and this plan's two state premises fail on the window morning.
  Recommendation to the operator (policy edit, not made by the planner): make
  `*longhorn*` a full time-boxed hold until this plan executes, then restore
  `max: patch`. If 1.12.2 is allowed to land, retarget per §1 "Moving base"
  (current 1.12.2; 1.12.2 -> 1.13.0 is still one minor) and re-review.
- **Reciprocity** (this plan writes only its own file). Measured 2026-11-06,
  plans in `conflicts_with` that already name `longhorn-1.13.0` back:
  `redis-fleet-8.10.3`, `tube-archivist-elasticsearch-9.5.5`, `grafana-chart-14.4.0`,
  `etcd-timeouts-5000-500`, `talos-linux-1.14.5`, `flux-oci-chart-sources`,
  `anythingllm-1.19`, `edot-collector-0.164.0`, `icloud-drive-fleet-2.3.0`,
  `open-webui-0.13.0`. Owed (should add it): `otbr-thread-rcp-recovery`,
  `otbr-0.4.0`, `flux-reconciler-impersonation`, `bitnamilegacy-exit-nextcloud-db`
  (the last two are blocked; `exclusive: true` here keeps the slot clean anyway).
- **Detached-volume plans.** `otbr-thread-rcp-recovery` / `otbr-0.4.0` would
  scale otbr 0 -> 1 and attach `otbr-data` (one of the four ruled detached
  volumes); a retirement plan for `jellyfin-config` (F-013d6eca) or the two
  `uzeit-de-*` volumes would remove one. Either changes the §2.2 set and fails
  the premise `longhorn-detached-set-is-the-ruled-four`: run them on another
  day; before this plan is fine (re-measure + re-rule), never in the slot.
- **Prometheus is shared instrument.** §2.5/§4.3 read it. No
  kube-prometheus-stack plan is open (2026-11-06) and the `*kube-prometheus-stack*`
  deny rule holds every bump until the Talos roll, so Step 0 cannot restart
  Prometheus in this window. If a kps change is ever placed the same day, this
  plan moves and §2.5's baseline is re-measured after it lands.
- **Storage safety.** No PVC/PV is deleted or created by this plan. No CIFS
  StorageClass is touched; the BackupTarget (CIFS) is only written to by the
  SystemBackup (2.6). The `mealie` restart in 4.4 is the only app pod this
  plan restarts deliberately.
- **Not in this plan (deliberate):** adopting `restrictInternalTraffic` /
  `metricsScrapeSources`; turning off `csi.allowControllerSecretAccess` (safe
  later — no StorageClass carries `csi.storage.k8s.io/provisioner-secret-*`,
  verified); age-based retention; un-nesting the inert `longhorn:` values block.

**Repo corrections found while planning** (not fixed here — planner writes only the plan):
1. `docs/sops/longhorn.md` §"Longhorn Version Upgrade via Flux" step 3 says
   `kubectl rollout status -n storage deployment/longhorn-manager` — longhorn-manager
   is a **DaemonSet**; the command fails. Should be `ds/longhorn-manager`, and the
   section should mention the one-way downgrade prevention and the separate
   engine-drain step (`concurrent-automatic-engine-upgrade-per-node-limit` is 0
   by design here).
2. Same SOP says 36 `dependsOn` Kustomizations; live count is 25 (2026-11-06; 35 on 2026-10-05).
