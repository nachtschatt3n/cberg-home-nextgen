---
plan_id: nextcloud-fleet-35.0.1
component: nextcloud
pr: null                              # no Renovate PR. coverage.py direct-bump group
                                      # (needs_plan_groups, dispatched by the nightly window
                                      # 2026-09-28 Step 0.5) + held chart group nextcloud-9.4.0
                                      # (cron sweep 2026-10-01); routed to PLAN by the
                                      # `*nextcloud*` deny rule AND by update_type major.
kind: chart                           # CHANGED 2026-10-05 (re-plan): chart+image LOCKSTEP, house
                                      # precedent nextcloud-34.0.4 / authentik-pg18-lockstep file a
                                      # lockstep as `kind: chart`. The image tags still move — they
                                      # ride in the same commit (§1.1). also_covers below waives
                                      # coverage.py's kind guard for both legs.
current: "34.0.4 (chart 9.3.0)"
target: "35.0.1 (chart 9.4.0)"        # PROSE ON PURPOSE: lib/plan_matching.py _ver_tokens() reads
                                      # BOTH tokens, so this one plan covers the image finding
                                      # (35.0.1) and the chart finding (9.4.0).
also_covers:
  - nextcloud-notify-push             # same image, same tag, SAME commit (notify-push.yaml
                                      # lockstep comment). Machine-readable so coverage.py
                                      # does not dispatch a second planner for it.
update_type: major
risk: high                            # MAJOR on the household's primary file/mail/calendar
                                      # server. One-way core + app migrations inside the
                                      # container's startup path; SEVEN enabled apps (6 appstore
                                      # + our openclaw_mail) declare max-version 34 and are
                                      # auto-disabled then re-downloaded (5 majors) INSIDE
                                      # `occ upgrade`, where the startup probe timer runs (§1.3).
                                      # The last PATCH upgrade (2026-09-26) was already killed by
                                      # that probe mid-`occ upgrade`. Rollback is a DB restore +
                                      # Longhorn snapshot revert, not a git revert (§5.3).
                                      # The chart leg (9.3.0 -> 9.4.0) adds NO risk: measured
                                      # metadata-labels-only render diff (§1.2).
est_duration_min: 150                 # pre-checks + render-diff gate + verified dump + config tar
                                      # + snapshots ~35; Commit A (openclaw_mail compat, a plain
                                      # 34.0.4 restart via reloader) ~10; §3.2b app pre-drain on 34
                                      # incl. Mail mini-gate ~10; Commit B rollout, budgeted to the
                                      # temporary 26 min startup window ~30; §4 incl. the Mail
                                      # contents gate on 3 accounts ~25; close-out ~15; slack ~25.
                                      # Fits sun-attended (schedulable budget 180) only if NOTHING
                                      # else over 30 min shares the day; NOT sat/nightly (90).
needs_reboot: false
touches:
  namespaces: [office]
  resources:
    - helmrelease/nextcloud                     # chart.spec.version 9.3.0 -> 9.4.0 + image.tag +
                                                # worker sidecar tag (ONE commit, ONE helm upgrade);
                                                # TEMPORARY upgrade.remediation.retries 3->0 and
                                                # startupProbe.failureThreshold 10->50 (§3.3), both
                                                # restored in §3.6 (chart stays 9.4.0).
    - deployment/nextcloud                      # rolled THREE times: Commit A (reloader, 34.0.4 ->
                                                # 34.0.4), Commit B (Recreate, entrypoint rsync +
                                                # occ upgrade 34 -> 35), §3.6 probe restore (35 -> 35).
                                                # Chart 9.4.0 changes its metadata labels only.
    - deployment/nextcloud-notify-push          # tag 34.0.4 -> 35.0.1 in Commit B
    - configmap/nextcloud-openclaw-mail-app     # info.xml max-version 34 -> 35 (Commit A)
    - cronjob/nextcloud-cron                    # template image re-rendered + chart labels
    - deployment/nextcloud-metrics              # chart labels only (no pod-template change, no
                                                # roll); reads the upgraded instance (§4 g4)
    - configmap/nextcloud-config                # chart labels only; data unchanged (§1.2)
    - configmap/nextcloud-phpconfig             # chart labels only; data unchanged
    - service/nextcloud                         # chart labels only
    - service/nextcloud-metrics                 # chart labels only
    - pvc/nextcloud-config                      # html/ rsynced, custom_apps/ rewritten by the
                                                # §3.2b pre-drain (5 patch updates on 34) and by
                                                # 5 app-major re-downloads in occ upgrade
                                                # (Longhorn RWX, longhorn-static)
    - statefulset/nextcloud-mariadb             # NOT restarted; receives one-way core + app migrations
    - deployment/nextcloud-redis                # NOT restarted; clients reconnect
    - pvc/nextcloud-data                        # CIFS (cifs-nextcloud-data) — mounted, NEVER
                                                # deleted/recreated by this plan (storage-safety)
    - "new: snapshot.longhorn.io/nextcloud-config-pre-35-0-1 + nextcloud-mariadb-pre-35-0-1 (ns storage)"
  shared: []                                    # own Longhorn volumes only. No Gateway/HTTPRoute,
                                                # cert-manager, cilium, coredns change. Consumers
                                                # in OTHER namespaces (ai/openclaw mail+calendar
                                                # skills, office/nextcloud-mcp, Homepage widget)
                                                # see a 503 for the duration of maintenance — §6.
depends_on: []                                  # nextcloud-9.4.0 is SUPERSEDED by this plan (folded
                                                # into Commit B 2026-10-05); it is no longer a dependent.
conflicts_with:
  - bitnamilegacy-exit-nextcloud-db             # same helmrelease.yaml, same DB this plan migrates
                                                # one-way; that plan's dump would capture a half-state.
  - nextcloud-mcp-0.198.0                       # its verification talks to this server; the §2.5
                                                # silence here is office-wide.
  - redis-fleet-8.10.2                          # restarts nextcloud-redis and (by its own touches)
                                                # deployment/nextcloud + notify-push — a restart
                                                # of either during §3.4 is the §5.2 failure.
  - flux-oci-chart-sources                      # moves the nextcloud chart SOURCE (chart.spec ->
                                                # OCI chartRef — Commit B's version sed would read
                                                # nothing) and rolls statefulset/nextcloud-mariadb.
  - flux-reconciler-impersonation               # changes the identity office/nextcloud reconciles
                                                # under; a reconcile failure mid-§3.4 leaves retries:0 set.
  - chart-patches-coredns-reloader-blackbox     # reloader roll is Commit A's mechanism; a coredns roll in §3.4 breaks appstore downloads
  - reloader-2.2.18                             # same reason: Commit A RELIES on a reloader roll (reciprocal)
  - coredns-1.48.1                              # appstore downloads inside occ upgrade need DNS (superseded
                                                # 2026-10-05 by coredns-1.48.2; kept until that file retires)
  - coredns-1.48.2                              # same reason (reciprocal: it lists this plan)
  - flux-distribution-2.9.6                     # restarts all six Flux controllers mid-§3.4 => release stranded
                                                # with retries: 0 (reciprocal; that plan is exclusive anyway)
  - flux-fleet-0.60.0                           # helm-controller restart mid-§3.4 strands the release pending-upgrade (retries: 0)
  - helm-drift-detection                        # patches helmrelease/nextcloud; its no-upgrade gate collides with Commit B
  - kube-prometheus-stack-91.9.0                # §4 gate 4 reads Prometheus; §2.5 silence lives in its
                                                # Alertmanager (reciprocal: it lists this plan)
  - app-template-5.2.1                          # rolls office workloads + ai/openclaw (consumer) under the office-wide silence
  - penpot-chart-1.10.0                         # office namespace, hidden by the §2.5 office-wide silence
  - penpot-cache-9.2                            # office namespace, hidden by the §2.5 office-wide silence
  - paperless-db-13.0.2                         # office namespace, hidden by the §2.5 office-wide silence
  - sure-0.7.5                                  # office namespace, hidden by the §2.5 office-wide silence
  - python-fleet-3.14.8                         # touches office workloads, hidden by the §2.5 office-wide silence
  - pgvector-fleet-0.8.7                        # touches office workloads, hidden by the §2.5 office-wide silence
  - talos-linux-1.14.2                          # node reboots (+ the k8s control-plane roll folded in from the
                                                # superseded k8s-1.36.5); a drain/apiserver restart mid-§3.4 is §5.2
  - longhorn-1.13.0                             # one-way storage engine move; §2.4 snapshots + §5.3 revert need a stable Longhorn
  # [rollback-class stacking (house rule 81fdd797: every backup-restore pair is
  #  declared; two in one slot leave no rollback capacity for either)]
  # - mariadb-28.1.1  # RESOLVED 2026-10-06: executed green now:2026-10-05, plan retired in 5af1e51f
  - jellyfin-12.1                               # backup-restore
  - n8n-2.39.8                                  # backup-restore
  - nocodb-2026.09.1                            # backup-restore (reciprocal)
  - media-naming-p3                             # backup-restore
  - talos-power-tuning-ab                       # backup-restore
  - talos-sysfs-power-caps                      # backup-restore
exclusive: false
security_ref: F-c5e87023              # the 34.0.4 image security finding (detail in the DB only —
                                      # docs/sops/vulnerability-disclosure.md); this bump is its
                                      # remedy ("newer upstream tag available"). Not the DRIVER of
                                      # the timing — the major is planned on its own merits.
capability_change: true               # a MAJOR: Talk 24 -> 25, Office (richdocuments) 11 -> 12,
                                      # Assistant 3 -> 4, OpenAI integration 4 -> 5, automated
                                      # tagging 5 -> 6 ride along, and context_chat LEAVES the
                                      # enabled set (§1.4). Users will see changes. (The chart
                                      # leg alone would be false — §1.2.)
rollback_class: backup-restore        # entrypoint refuses an older image on newer data (§5.3).
                                      # No backup_gate named => human-gated, which the deny rule
                                      # ("operator-supervised only") demands anyway.
finding_refs: [F-7344f3ec, F-7bcfda63, F-38fecaa8, F-c5e87023]
                                      # F-7344f3ec version/critical nextcloud image 34.0.4 -> 35.0.1
                                      # F-7bcfda63 version/critical nextcloud-notify-push 34.0.4 -> 35.0.1
                                      # F-38fecaa8 version/monitor nextcloud chart 9.3.0 -> 9.4.0
                                      #   (moved here from the superseded nextcloud-9.4.0)
                                      # F-c5e87023 security/warning on the 34.0.4 image (remedied by the bump)
                                      # all four measured open (last_seen 2026-10-05) before claiming.
review: ready-for-go@2026-10-05   # plan-reviewer 2026-10-05: needs-fix (GO carry-over, conflicts) -> fixed -> delta ready-for-go. Needs the one-line operator re-confirm of the lockstep shape (§3.1 STOPs without it)
status: awaiting-go                         # RE-PLANNED 2026-10-05: image-only -> chart 9.4.0 + image 35.0.1
                                      # lockstep (operator decision relayed by the coordinator). Was
                                      # awaiting-go/ready-for-go@2026-09-28 on the image-only shape; the
                                      # review field is REMOVED — a fresh plan-reviewer pass is owed.
                                      # GO: §1.7 — a ONE-LINE operator re-confirm is required (bundled
                                      # with the go/no-go), the 2026-10-02 GO covered image-only only.
window: "sun-attended:2026-10-18"     # SCHEDULED 2026-09-28 by maintenance-window-agent; kept on re-plan.
                                      # The executor must read the entrypoint log live in §3.4
                                      # and run §5.1/§5.2 inside the same slot.
premises:
  # Runner grammar (plan-premises.py): kubectl/flux/git/helm READ verbs + bare text
  # filters only. Everything occ-derived is an EXECUTOR gate in §2, not a premise.
  # Run from the REPO ROOT (helm is a mise shim). All values measured live 2026-10-05.
  - id: live-server-image-is-34.0.4-on-both-containers
    why: >-
      current claims 34.0.4 on the main container AND the worker sidecar. The entrypoint
      only allows ONE major per upgrade (entrypoint.sh line 192); if the instance already
      moved, the §3.3 seds are no-ops and every §4 baseline is wrong.
    run: kubectl get deploy -n office nextcloud -o jsonpath='{.spec.template.spec.containers[?(@.name=="nextcloud")].image} {.spec.template.spec.containers[?(@.name=="worker")].image}'
    expect_exact: "docker.io/nextcloud:34.0.4 nextcloud:34.0.4"
  - id: notify-push-image-is-34.0.4
    why: >-
      notify-push runs the same image by rule. If it already differs, the lockstep edit
      must be re-derived rather than applied blind.
    run: kubectl get deploy -n office nextcloud-notify-push -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "nextcloud:34.0.4"
  - id: git-pins-are-34.0.4-exactly-three
    why: >-
      §3.3 rewrites exactly three line-anchored 34.0.4 pins (tag, worker image, notify-push
      image). The COUNT is the assertion.
    run: >-
      git show HEAD:kubernetes/apps/office/nextcloud/app/helmrelease.yaml HEAD:kubernetes/apps/office/nextcloud/app/notify-push.yaml
      | grep -c '34\.0\.4$'
    expect_exact: "3"
  - id: git-chart-pin-is-9.3.0-exactly-once
    why: >-
      §3.3 rewrites exactly one line-anchored `      version: 9.3.0` (chart.spec.version).
      0 => the chart already moved (or flux-oci-chart-sources replaced chart.spec with an
      OCI chartRef): re-derive Commit B, do not run it.
    run: "git show HEAD:kubernetes/apps/office/nextcloud/app/helmrelease.yaml | grep -c '^      version: 9.3.0$'"
    expect_exact: "1"
  - id: our-chart-pin-is-9.3.0
    why: Same fact, live side; a mismatch with git means a reconcile is in flight or failed.
    run: kubectl get helmrelease -n office nextcloud -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: "9.3.0"
  - id: chart-source-is-helmrepository
    why: >-
      Commit B edits chart.spec.version against HelmRepository/nextcloud. If
      flux-oci-chart-sources moved nextcloud to an OCI chartRef the field is gone.
    run: kubectl get helmrelease -n office nextcloud -o jsonpath='{.spec.chart.spec.sourceRef.kind}/{.spec.chart.spec.sourceRef.name}'
    expect_exact: "HelmRepository/nextcloud"
  - id: lockstep-chart-9.4.0-carries-appversion-35.0.1
    why: >-
      THE LOCKSTEP PREMISE (replaces the retired "newest chart still carries a 34
      appVersion" premise, which FAILED on 2026-09-30 and triggered this re-plan). Chart
      9.4.0 must still be published with appVersion 35.0.1 — the pairing Commit B applies.
      Checked by exact version so it does not depend on what "newest" is.
    run: "helm show chart nextcloud --repo https://nextcloud.github.io/helm --version 9.4.0 | grep -E '^appVersion'"
    expect_exact: "appVersion: 35.0.1"
  - id: newest-published-chart-is-still-9.4.0
    why: >-
      Operator rule: chart+image move to the NEWEST. If upstream publishes a newer chart
      (e.g. 9.4.1 / appVersion 35.0.2) before the window, this premise FAILS and the plan
      must be REFRESHED in place to that pair (README "When the held target MOVES") —
      never run a stale lockstep. Note `helm show chart` without --version = newest.
    run: "helm show chart nextcloud --repo https://nextcloud.github.io/helm | grep -E '^version'"
    expect_exact: "version: 9.4.0"
  - id: helmrelease-ready
    why: Starting a helm upgrade on an in-flight or failed one is how remediation thrash begins.
    run: kubectl get helmrelease -n office nextcloud -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: server-deployment-one-ready-replica
    why: A pod not Ready now is mid-restart or stuck in maintenance; the §2 occ gates would lie.
    run: kubectl get deploy -n office nextcloud -o jsonpath='{.status.readyReplicas}'
    expect_exact: "1"
  - id: openclaw-mail-git-declares-max-34
    why: >-
      §1.4 / Commit A rewrites this exact line to max-version 35. If it already moved, Commit
      A is empty (skip it); if it moved to something else, re-derive.
    run: "git show HEAD:kubernetes/apps/office/nextcloud/app/openclaw-mail/info.xml | grep -c 'nextcloud min-version=\"30\" max-version=\"34\"'"
    expect_exact: "1"
  - id: deployment-still-reloader-auto
    why: >-
      Commit A relies on reloader to roll deployment/nextcloud when the openclaw_mail
      ConfigMap changes — and §3.2 SEPARATES that roll from the image bump precisely so a
      reloader roll can never land in the middle of the 35 occ upgrade (§1.5).
    run: kubectl get deploy -n office nextcloud -o jsonpath='{.metadata.annotations.reloader\.stakater\.com/auto}'
    expect_exact: "true"
  - id: startup-probe-budget-is-60-30-10
    why: >-
      §3.3 raises failureThreshold 10 -> 50 for the attempt and §3.6 restores 10. The
      python edit asserts the exact block; a changed probe changes the budget math in §1.5.
    run: kubectl get deploy -n office nextcloud -o jsonpath='{.spec.template.spec.containers[?(@.name=="nextcloud")].startupProbe.initialDelaySeconds} {.spec.template.spec.containers[?(@.name=="nextcloud")].startupProbe.periodSeconds} {.spec.template.spec.containers[?(@.name=="nextcloud")].startupProbe.failureThreshold}'
    expect_exact: "60 30 10"
  - id: flux-remediation-retries-is-3
    why: §3.3 flips 3 -> 0 for the attempt and §3.6 restores 3.
    run: kubectl get helmrelease -n office nextcloud -o jsonpath='{.spec.upgrade.remediation.retries}'
    expect_exact: "3"
  - id: redis-is-standalone-deployment
    why: >-
      §1.6 claims this bump does not restart nextcloud-redis (a plain Kustomize Deployment,
      no spec change here). If it were back in the chart, a helm upgrade would sign every
      user out.
    run: kubectl get deploy -n office nextcloud-redis -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_contains: "redis:8."
  - id: mariadb-bundled-sts-with-password-file
    why: >-
      §2.3 dump and §5.3 restore exec into nextcloud-mariadb-0 and read
      MARIADB_ROOT_PASSWORD_FILE. If bitnamilegacy-exit-nextcloud-db replatformed the DB,
      those commands target the wrong server.
    run: kubectl get sts -n office nextcloud-mariadb -o jsonpath='{.spec.template.spec.containers[0].env[*].name}'
    expect_contains: MARIADB_ROOT_PASSWORD_FILE
  - id: newest-longhorn-backup-nextcloud-mariadb-completed
    why: Durable rollback floor under §5.3 (the executor reads its AGE in §2.1).
    run: kubectl get backups.longhorn.io -n storage -l backup-volume=nextcloud-mariadb --sort-by=.status.snapshotCreatedAt -o jsonpath='{.items[-1].status.state}'
    expect_exact: Completed
  - id: newest-longhorn-backup-nextcloud-config-completed
    why: Same floor for the code/custom_apps/config volume the entrypoint and app re-downloads rewrite.
    run: kubectl get backups.longhorn.io -n storage -l backup-volume=nextcloud-config --sort-by=.status.snapshotCreatedAt -o jsonpath='{.items[-1].status.state}'
    expect_exact: Completed
  - id: nextcloud-data-pvc-is-the-cifs-class
    why: >-
      Storage-safety anchor: the data PVC is CIFS (severe tier). This plan mounts it and
      never deletes/recreates it; the rollback restores the DB and nextcloud-config ONLY.
    run: kubectl get pvc -n office nextcloud-data -o jsonpath='{.spec.storageClassName}'
    expect_exact: cifs-nextcloud-data
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/backup.md
  - docs/sops/longhorn.md
  - docs/sops/storage-safety.md
  - docs/sops/maintenance-windows.md
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/vulnerability-disclosure.md
generated: "2026-10-05"               # re-planned (chart+image lockstep); first written 2026-09-28
---

# nextcloud 34.0.4 -> 35.0.1 (MAJOR) + chart 9.3.0 -> 9.4.0 in LOCKSTEP, notify-push in lockstep — two commits

> **Re-planned 2026-10-05** (operator decision relayed by the coordinator): the
> image-only shape is retired. Chart 9.4.0 (appVersion 35.0.1, published
> 2026-09-30) now rides in Commit B with the image. The former chart-only plan
> `nextcloud-9.4.0` is `superseded` by this file. Review status reset to
> `draft`; see §1.7 for whether the operator GO carries.

## 1) Summary & why held

### 1.1 What moves

| Leg | From | To | Where |
|---|---|---|---|
| server image `image.tag` | 34.0.4 | **35.0.1** | `kubernetes/apps/office/nextcloud/app/helmrelease.yaml` line 35 |
| worker sidecar image | `nextcloud:34.0.4` | `nextcloud:35.0.1` | same file line 234 |
| notify-push image | `nextcloud:34.0.4` | `nextcloud:35.0.1` | `notify-push.yaml` line 40 |
| `openclaw_mail` custom app compat | `max-version="34"` | `max-version="35"` | `openclaw-mail/info.xml` line 28 (**Commit A, separate**) |
| chart `spec.chart.spec.version` | 9.3.0 | **9.4.0** | `helmrelease.yaml` line 11 (**Commit B, same commit as the image**) |
| enabled appstore apps with a 34-compatible patch pending (`mail` 5.12.2->5.12.3, `calendar` 6.6.1->6.6.2, `contacts` 8.9.0->8.9.1, `google_synchronization` 4.3.1->4.3.2, `richdocuments` 11.1.1->11.1.2) | — | taken on **34.0.4** first | §3.2b pre-drain (`occ app:update --all`), so Mail's move is gated on its own |
| mariadb (`bitnamilegacy/mariadb:latest`), `xperimental/nextcloud-exporter:0.9.1`, bundled subcharts | — | **unchanged** | identical in both chart tarballs; mariadb subchart not enabled here |

Why held: the `*nextcloud*` deny rule — *"chart+image must bump together and run
occ migrations (Mail custom_app / stuck-maintenance trap) — operator-supervised
only"* — and it is a MAJOR (coverage returns PLAN for any major).

### 1.2 The chart moves 9.3.0 -> 9.4.0 in the same commit — measured metadata-only

Re-measured 2026-10-05 against `https://nextcloud.github.io/helm/index.yaml`:
newest chart **9.4.0, appVersion 35.0.1** (created 2026-09-30T07:11Z); 9.3.0 is
appVersion 34.0.4. Newest image tag on Docker Hub in the 35 line is **35.0.1**
(no 35.0.2), amd64 digest unchanged since 2026-09-28
(`sha256:fc04168b172e09d9b9bc7665476a77898634fe2833f0a320366fb9eb0db491db`).
So 9.4.0 + 35.0.1 is the NEWEST lockstep pair, exactly the operator rule.

- **Chart source diff** — `diff -ru` of the two release tarballs
  (`github.com/nextcloud/helm/releases/download/nextcloud-9.{3,4}.0/nextcloud-9.{3,4}.0.tgz`)
  is exactly `Chart.yaml` `appVersion: 34.0.4 -> 35.0.1` and `version: 9.3.0 -> 9.4.0`.
  No template, `values.yaml` or values-schema change; subchart pins identical.
- **Rendered diff with OUR values** (`helm template` of `spec.values` from git HEAD,
  2026-10-05): current values on 9.3.0 vs current values on 9.4.0 = **14 lines,
  all metadata labels** (`helm.sh/chart`, `app.kubernetes.io/version`) on 7
  objects: ConfigMap `nextcloud-config`, ConfigMap `nextcloud-phpconfig`, Service
  `nextcloud`, Service `nextcloud-metrics`, Deployment `nextcloud`, Deployment
  `nextcloud-metrics`, CronJob `nextcloud-cron`. Pod templates use
  `nextcloud.selectorLabels` only, which carry neither label — **the chart leg
  alone rolls nothing**. `.Chart.AppVersion` reaches the image only when
  `image.tag` is empty (`_helpers.tpl` `nextcloud.image`); ours is pinned.
- **The full Commit B render** (9.3.0 + current values vs 9.4.0 + Commit-B
  values, dry-run on scratch copies 2026-10-05) differs in exactly: the 14 label
  lines, 4 image lines (`docker.io/nextcloud:34.0.4 -> 35.0.1` on the main
  container and the cron template, `nextcloud:34.0.4 -> 35.0.1` on the worker,
  plus the notify-push manifest outside the chart) and `failureThreshold 10 -> 50`.
  Nothing else. §2.0(e) re-measures this on the day.
- **Consequence:** one helm upgrade, one pod roll (the one the image already
  causes). The chart adds no migration, no probe, no new object, no removed
  object. `helm history` APP VERSION will read 35.0.1 matching what runs (the
  image-only shape would have left it reading 34.0.4).

The former premise `newest-published-chart-still-carries-a-34-appversion` (FAILED
2026-09-30 — the trigger for this re-plan) is replaced by
`lockstep-chart-9.4.0-carries-appversion-35.0.1` and
`newest-published-chart-is-still-9.4.0` (the latter fails, correctly, the day a
newer chart ships — refresh again, never run a stale pair).

### 1.3 Upstream evidence — Nextcloud 35 upgrade requirements

`docs.nextcloud.com/.../release_notes/upgrade_to_35.html`, verbatim:

- *"PHP 8.2 is no longer supported."* — image 35.0.1 ships **PHP 8.5.11**
  (`PHP_VERSION` in the image config, amd64 digest
  `sha256:fc04168b172e09d9b9bc7665476a77898634fe2833f0a320366fb9eb0db491db`);
  live pod already runs 8.5.11. **No PHP change.** Base `php:8.5-apache-trixie`.
- *"MariaDB 10.6 is out of support ... The minimum supported version of MariaDB
  is now 10.11 LTS."* — live `nextcloud-mariadb-0` reports **11.8.2-MariaDB**.
  **Satisfied; no DB engine change.**
- MySQL 9 MD5 note — not applicable (MariaDB).
- Upgrade path: `entrypoint.sh` lines 189-195 (identical in the 34 and 35 image
  dirs of `nextcloud/docker`) refuse to skip a major; 34.0.4 is the newest 34
  patch, so 34 -> 35 is the one supported hop.
- `config.sample.php` v34.0.4 vs v35.0.1: the only removed key is
  `systemtags.managerFactory`, which we do not set. Every key in our
  `custom.config.php` survives.
- The worker sidecar loops `occ background-job:worker
  "OC\TaskProcessing\SynchronousBackgroundJob"`: both
  `lib/private/TaskProcessing/SynchronousBackgroundJob.php` and
  `core/Command/Background/JobWorker.php` exist at v35.0.1 (HTTP 200).

### 1.4 Why a MAJOR is dangerous HERE — the app-compatibility map (the real risk)

`OC\Updater::doUpgrade()` at v35.0.1 (`lib/private/Updater.php` 253-265):

```php
$this->checkAppsRequirements();      // 373-377: incompatible non-shipped app -> disableApp($app, true)
...
$this->upgradeAppStoreApps($this->appManager->getEnabledApps());
$autoDisabledApps = $this->appManager->getAutoDisabledApps();
if (!empty($autoDisabledApps)) {
    $this->upgradeAppStoreApps(array_keys($autoDisabledApps), $autoDisabledApps);
}
```

So every enabled app whose installed `info.xml` says `max-version < 35` is
**auto-disabled**, then — if the appstore has a 35-compatible release — **downloaded,
migrated and re-enabled INSIDE `occ upgrade`**, i.e. inside the startup probe's
window. Live `info.xml` (all 21 dirs under `custom_apps/`) + `occ app:list` (68
enabled / 9 disabled) + appstore `platform/35.0.1` and `platform/34.0.4`,
**re-measured 2026-10-05**:

| App (enabled unless noted) | Installed / declared max | 34 patch pending (§3.2b) | 35.0.1 newest stable | Outcome in `occ upgrade` |
|---|---|---|---|---|
| `spreed` (Talk) | 24.0.5 / 34 | — | **25.0.5** (major, ~203 MB dir) | auto-disable -> download -> re-enable |
| `richdocuments` (Office) | 11.1.1 / 34 | 11.1.2 | **12.0.1** (major) | same |
| `assistant` | 3.5.0 / 34 | — | **4.0.0** (major) | same |
| `integration_openai` | 4.5.2 / 34 | — | **5.0.0** (major) | same |
| `files_automatedtagging` | 5.0.0 / 34 | — | **6.0.0** (major) | same |
| `context_chat` | 5.4.0 / 34 | — | **none** (no stable 35 release) | **auto-disabled and STAYS disabled** |
| `openclaw_mail` (OURS, ConfigMap) | 0.1.0 / **34** | — | not in appstore | would be **disabled** -> OpenClaw's draft-with-attachments route dies; worker's `app:enable` then fails every boot. **Fixed by Commit A.** |
| `mail` | 5.12.2 / 35 | **5.12.3** | 5.12.3 | compatible; patch taken on 34 in §3.2b, then **unchanged** through `occ upgrade` |
| `calendar` | 6.6.1 / 35 | 6.6.2 | 6.6.2 | patch on 34, then unchanged |
| `contacts` | 8.9.0 / 36 | 8.9.1 | 8.9.1 | patch on 34, then unchanged |
| `google_synchronization` | 4.3.1 / 35 | 4.3.2 | 4.3.2 | patch on 34, then unchanged (check by NAME afterwards — the app that has been silently re-disabled before) |
| `drawio` 4.3.9, `guests` 4.10.0, `integration_{overleaf 2.0.2,paperless 1.0.14,watsonx 1.3.0}`, `notify_push` 1.4.1, `richdocumentscode` 26.4.402, `whiteboard` 2.0.0 | max 35/36 | — | same | unchanged |
| `agenda_bot` (disabled) 1.7.0 / 34, `files_3dmodelviewer` (disabled) 0.0.18 / 35 | — | agenda_bot 1.7.1 | 1.7.1 / 0.0.18 | stay disabled (harmless in the update list) |

Shipped (core) apps move with the image and are not listed. All 9 disabled apps
(`admin_audit agenda_bot encryption files_3dmodelviewer files_external photos
suspicious_login twofactor_nextcloud_notification user_ldap`) stay disabled.

**Why §3.2b exists (new on re-plan).** `Updater::upgradeAppStoreApps()` at
v35.0.1 (`lib/private/Updater.php` 397-411) calls
`installer->isUpdateAvailable($app)` for EVERY enabled app and updates it if
anything newer is compatible. Since 2026-09-28 `mail` 5.12.3 was published, so
without a pre-drain the Mail app would ALSO be swapped inside `occ upgrade`,
inside the probe window, entangled with the core migration — and a Mail
breakage could not be attributed. Taking the five 34-compatible patches on
34.0.4 FIRST (operator standing rule: app updates are always take-able) and
gating Mail right there means `occ upgrade` touches Mail only through the core
migration, and leaves only the six 35-only majors for the probe window.

- **Mail's code does not move during the major**, which is the good news for the
  operator's hard gate: after §3.2b the risk to Mail is the core migration and
  the maintenance flag, not a Mail migration. It is gated twice as a CONTENTS
  assertion — after the pre-drain (§3.2b, on 34) and after the major (§4 gate 2).
- **context_chat leaving the enabled set is accepted, not a regression**:
  `occ app_api:app:list` shows **no ExApps** and `app_api:daemon:list` shows
  **no daemon** — context_chat has no backend here and is functionally inert.
  §4 expects `enabled_post == enabled_pre - {context_chat}` (plus context_chat
  if upstream ships a stable 35 release before the window — then it is updated
  instead; both are PASS).
- App majors riding along are in-policy (operator standing rule: app updates are
  always take-able).

### 1.5 The two timing traps, and how this plan defuses each

1. **Startup probe vs `occ upgrade`.** Chart startupProbe = 60 s + 10 x 30 s =
   **360 s**. On 2026-09-26 a *patch* upgrade's rsync alone took **~289 s** and the
   probe killed the container inside `occ upgrade` (retired `nextcloud-34.0.4`
   close-out, `e43a1381`). A major rsyncs all of core and then downloads ~390 MB
   of five app majors into the RWX volume inside `occ upgrade`. The 35-only majors
   cannot be pre-drained (those releases require >= 35); the 34-compatible
   patches ARE pre-drained in §3.2b, which only shortens this pass. **Defusal:**
   Commit B temporarily sets `startupProbe.failureThreshold: 50` (60 + 50 x 30 =
   **1560 s = 26 min**, below the HelmRelease `timeout: 30m`), restored in §3.6.
   Liveness/readiness only start after startup succeeds, so they are unaffected.
2. **Reloader roll vs `occ upgrade`.** `deploymentAnnotations:
   reloader.stakater.com/auto: "true"` means changing the
   `nextcloud-openclaw-mail-app` ConfigMap rolls `deployment/nextcloud`. Put in the
   SAME commit as the image, reloader and helm-controller race; a reloader
   Recreate landing mid-35-upgrade is exactly §5.2. **Defusal:** Commit A
   (ConfigMap only; `max-version 35` is still valid on 34 since min is 30) rolls a
   harmless 34.0.4 -> 34.0.4 restart FIRST; Commit B follows only once that is Ready.

Also carried from the retired plan: **Flux remediation off** for the attempt
(`retries: 0`, `remediateLastFailure: false`) — a Flux rollback of a half-run
upgrade starts the 34 image on 35 data, which `entrypoint.sh` line 184-186 refuses:
*"Can't start Nextcloud because the version of the data (...) is higher than the
docker image version (...) and downgrading is not supported."*

### 1.6 Datastores

- `nextcloud-redis`: not restarted (standalone Deployment, no spec change). Users
  see a 503 during maintenance, not a sign-out.
- `nextcloud-mariadb`: not restarted but **written one-way** (core 35 schema + 5
  app-major migrations). Hence the verified dump + snapshots in §2.3/§2.4.
- `nextcloud-data` (CIFS `cifs-nextcloud-data`, severe tier): read/written by the
  app as usual; **no PVC/PV operation anywhere in this plan, including rollback.**
- `config/` (`config.php` + chart-projected `*.config.php`, ~68 KB): lives on the
  `nextcloud-config` volume (subPath `config`) and is rewritten by `occ upgrade`
  (version, app paths). Covered by the §2.4 snapshot AND by a local tar copy
  taken in §2.3b (a second, file-level restore path for config alone).

### 1.7 Does the operator GO carry over? — NO: one-line re-confirm required

The GO in the decision ledger (decided_at 2026-10-02T08:18:48Z, per the
plan-reviewer's ledger read 2026-10-05) chose the **image-only** shape. What the
re-plan changes:

| Change | Effect | Inside SD-6 (scope-reducing / patch-level)? |
|---|---|---|
| chart 9.3.0 -> 9.4.0 in Commit B | 14 metadata-label lines; no pod template, value, object, migration or capability change (§1.2). Rollback §5.3(d) restores 9.3.0 with the image. | No — it ADDS a leg |
| §3.2b pre-drain of 5 app patches on 34, incl. **Mail 5.12.2 -> 5.12.3** | the same updates `occ upgrade` would apply anyway (Updater.php 397-411), moved earlier so Mail is gated on its own; covered by the §2.3 dump + §2.4 snapshot taken before it | No — it moves the operator's hard-gate app before the major |
| dump-to-Commit-B gap grows ~35-45 min (Commit A + §3.2b + mini-gate) | user writes in that gap are lost on a §5.3 restore (the dump is the floor) | No — widens the data-loss window |
| app drift since the GO (spreed 25.0.5, richdocuments 12.0.1) | patch-level drift of apps already in the GO'd set | Yes |
| est 130 -> 150 min | duration only | Yes |

My planner judgement is that none of this adds a new data- or feature-loss
CLASS (the chart leg is exactly the lockstep the operator's standing rule
demands). But it is not a scope-reducing amendment, so SD-6 does not carry the GO
over, and a coordinator relay is not consent. **Required:** a one-line operator
re-confirm, bundled into the window's go/no-go and NOT presented as a new
data-loss decision:

> "nextcloud: lockstep chart 9.4.0 + image 35.0.1, with an app pre-drain on 34
> (Mail 5.12.2 -> 5.12.3 first, gated) — still GO?"

Record the answer with `home-operation decide` against this plan_id at once. No
§3 step runs before it.

## 2) Pre-checks

Run from `/Users/mu/code/cberg-home-nextgen` on the Mac mini, zsh. Each block
is ONE Bash call; nothing survives between calls except FILES in
`/Users/mu/db-dumps/nextcloud-35.0.1-exec/` (literal path everywhere — never a
`$D`). Any command with `--timeout` > 110 s: Bash tool timeout 600000 ms. Every
`occ` in the DIRECT form (`kubectl exec ... -- su -s /bin/sh www-data -c "php occ ..."`).

**2.0 Premises + executor gates**

```bash
.venv/bin/python3 runbooks/plan-premises.py nextcloud-fleet-35.0.1       # all PASS or STOP
mkdir -p /Users/mu/db-dumps/nextcloud-35.0.1-exec && chmod 700 /Users/mu/db-dumps/nextcloud-35.0.1-exec
ls /Users/mu/db-dumps/nextcloud-35.0.1-exec/                             # must be EMPTY; if an earlier
                                                                         # attempt left files, move the dir aside
```

```bash
# (a) target tag still published, amd64 present, digest unchanged since planning.
#     Docker Hub's HUB API, not the registry manifest endpoint: the anonymous registry
#     path answered TOOMANYREQUESTS (pull rate limit) on 2026-10-05, which this gate would
#     have read as "tag missing". Negative control measured: tag 35.0.99 -> HTTP 404 ->
#     curl -f exits non-zero -> the python prints a JSONDecodeError.
curl -sf "https://hub.docker.com/v2/repositories/library/nextcloud/tags/35.0.1" \
  | .venv/bin/python3 -c "import sys,json;d=json.load(sys.stdin);print([i['digest'] for i in d['images'] if i['architecture']=='amd64'])"
#   EXPECT: ['sha256:fc04168b172e09d9b9bc7665476a77898634fe2833f0a320366fb9eb0db491db'] (re-measured 2026-10-05)
#   HOW IT FAILS: [] or a JSONDecodeError => tag missing/API failed: STOP. A DIFFERENT digest =>
#   upstream rebuilt the tag (normal for the official image, e.g. PHP patch): re-check its
#   PHP_VERSION is still 8.5.x before continuing; not a stop by itself.
```

```bash
# (b) instance healthy and exactly where we think
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ status --output=json"
#   EXPECT: "version":"34.0.4.1" "maintenance":false "needsDbUpgrade":false
#   HOW IT FAILS: maintenance true / needsDbUpgrade true => already stuck: §5.1 FIRST, not this plan.
```

```bash
# (c) the app-compat map in §1.4 still holds (appstore drifts daily)
curl -s https://apps.nextcloud.com/api/v1/platform/35.0.1/apps.json -o /Users/mu/db-dumps/nextcloud-35.0.1-exec/apps35.json
.venv/bin/python3 - <<'PY'
import json
a = {x['id']: x for x in json.load(open('/Users/mu/db-dumps/nextcloud-35.0.1-exec/apps35.json'))}
assert len(a) > 100, 'appstore list empty/short — API failed, gate cannot read'
for app in ['spreed','richdocuments','assistant','integration_openai','files_automatedtagging','context_chat',
            'mail','calendar','contacts','google_synchronization','notify_push','whiteboard','richdocumentscode','guests']:
    rs = [r['version'] for r in a.get(app, {}).get('releases', []) if not r['isNightly'] and '-' not in r['version']]
    print(f'{app:24s} {max(rs, key=lambda v: [int(p) for p in v.split(".")]) if rs else "NONE"}')
PY
#   EXPECT (2026-10-05): spreed 25.0.5, richdocuments 12.0.1, assistant 4.0.0, integration_openai 5.0.0,
#   files_automatedtagging 6.0.0, context_chat NONE, mail 5.12.3, calendar 6.6.2, contacts 8.9.1,
#   google_synchronization 4.3.2, notify_push 1.4.1, whiteboard 2.0.0, richdocumentscode 26.4.402, guests 4.10.0
#   (patch drift on any of these is normal and fine; the gate is NONE vs a version)
#   HOW IT FAILS: any of the 9 compatible apps printing NONE => it will be auto-disabled with no
#   replacement: STOP, that is an operator decision. mail NONE => hard STOP (the operator's gate).
#   context_chat now showing a stable version is FINE (it will be updated instead of disabled).
```

```bash
# (d) Commit-A precondition: live openclaw_mail still declares max 34 (Commit A not yet applied)
kubectl exec -n office deploy/nextcloud -c nextcloud -- sh -c 'grep -o "<nextcloud[^>]*>" /var/www/html/custom_apps/openclaw_mail/appinfo/info.xml'
#   EXPECT: <nextcloud min-version="30" max-version="34"/>   (35 => Commit A already landed; skip §3.2)
```

```bash
# (e) CHART RENDER-DIFF GATE — re-measure on the day that 9.3.0 -> 9.4.0 is still
#     metadata-only against TODAY's values (§1.2). Tarballs from the GitHub release
#     (helm --repo has failed on this Mac before with "no cached repo found").
cd /Users/mu/db-dumps/nextcloud-35.0.1-exec && rm -rf c93 c94 && mkdir c93 c94
curl -sfL https://github.com/nextcloud/helm/releases/download/nextcloud-9.3.0/nextcloud-9.3.0.tgz | tar xz -C c93
curl -sfL https://github.com/nextcloud/helm/releases/download/nextcloud-9.4.0/nextcloud-9.4.0.tgz | tar xz -C c94
grep -E '^(version|appVersion):' c94/nextcloud/Chart.yaml
#   EXPECT: appVersion: 35.0.1 / version: 9.4.0   (empty => download failed: STOP)
diff -rq c93/nextcloud c94/nextcloud
#   EXPECT exactly: "Files c93/nextcloud/Chart.yaml and c94/nextcloud/Chart.yaml differ" (one line)
cd /Users/mu/code/cberg-home-nextgen
.venv/bin/python3 -c "
import yaml;d=yaml.safe_load(open('kubernetes/apps/office/nextcloud/app/helmrelease.yaml'))
yaml.safe_dump(d['spec']['values'],open('/Users/mu/db-dumps/nextcloud-35.0.1-exec/values.yaml','w'))"
for v in 93 94; do
  helm template nextcloud /Users/mu/db-dumps/nextcloud-35.0.1-exec/c$v/nextcloud -n office \
    -f /Users/mu/db-dumps/nextcloud-35.0.1-exec/values.yaml > /Users/mu/db-dumps/nextcloud-35.0.1-exec/render-$v.yaml || echo "RENDER $v FAILED"
done
wc -l /Users/mu/db-dumps/nextcloud-35.0.1-exec/render-93.yaml /Users/mu/db-dumps/nextcloud-35.0.1-exec/render-94.yaml
diff /Users/mu/db-dumps/nextcloud-35.0.1-exec/render-93.yaml /Users/mu/db-dumps/nextcloud-35.0.1-exec/render-94.yaml \
  | grep -E '^[<>]' | grep -vE '^[<>] +(helm\.sh/chart: nextcloud-9\.[34]\.0|app\.kubernetes\.io/version: "(34\.0\.4|35\.0\.1)")$' | wc -l
diff /Users/mu/db-dumps/nextcloud-35.0.1-exec/render-93.yaml /Users/mu/db-dumps/nextcloud-35.0.1-exec/render-94.yaml | grep -c '^>'
#   EXPECT (measured 2026-10-05): both renders 1446 lines (> 1000 is the floor); first count 0;
#   second count 14 (7 objects x 2 labels).
#   HOW IT FAILS: 0-line render / "RENDER .. FAILED" => the gate measured nothing: STOP.
#   First count > 0 => 9.4.0 now renders a REAL difference with today's values: STOP, re-plan.
#   Second count 0 => both renders identical (same tarball twice): STOP.
```

**2.1 Flux / storage green, nothing in flight**

```bash
for K in office/nextcloud storage/longhorn; do
  printf '%s ' "$K"; kubectl get kustomization -n "${K%%/*}" "${K##*/}" \
    -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{" "}{.status.lastAppliedRevision}{"\n"}'
done                                                               # expect True <sha> on both
kubectl -n office get pods | grep -E '^nextcloud'                  # all Running, recent restarts 0
kubectl get volumes.longhorn.io -n storage nextcloud-mariadb nextcloud-config \
  -o custom-columns=NAME:.metadata.name,STATE:.status.state,ROBUST:.status.robustness,LAST_BACKUP:.status.lastBackupAt
kubectl -n office get jobs --sort-by=.metadata.creationTimestamp | grep nextcloud-cron | tail -3
kubectl get cronjob -n storage daily-backup-all-volumes -o jsonpath='{.status.lastSuccessfulTime}{"\n"}'
```

EXPECT: both `True`; volumes `healthy`; `lastBackupAt` within ~36 h (measured
2026-09-27T03:09Z for both; lastBackupAt can lag one cycle — cross-check the
newest Completed `backups.longhorn.io` per `docs/sops/backup.md`); newest cron
Jobs `Complete 1/1`. HOW IT FAILS: a backup older than ~36 h means the durable
floor under §5.3 is missing — the dump in §2.3 is then the ONLY restore point;
proceed only as a conscious operator choice.

**2.2 Baselines (the numbers §4 diffs against)**

```bash
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ app:list --output=json" \
  > /Users/mu/db-dumps/nextcloud-35.0.1-exec/app-list-pre.json
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ notify_push:self-test" \
  > /Users/mu/db-dumps/nextcloud-35.0.1-exec/notify-push-selftest-pre.txt 2>&1
.venv/bin/python3 -c "import json;d=json.load(open('/Users/mu/db-dumps/nextcloud-35.0.1-exec/app-list-pre.json'));print('enabled',len(d['enabled']),'disabled',len(d['disabled']))"
#   EXPECT (2026-09-28, re-measured 2026-10-05): enabled 68 disabled 9. HOW IT FAILS: a JSON error => the exec failed; re-run.
cat /Users/mu/db-dumps/nextcloud-35.0.1-exec/notify-push-selftest-pre.txt
#   EXPECT: every line green. A red line here is PRE-EXISTING — fix or accept before the bump.
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "tail -400 /var/www/html/data/nextcloud.log" \
  | grep -ciE '"level":[34]' > /Users/mu/db-dumps/nextcloud-35.0.1-exec/log-errcount-pre.txt
cat /Users/mu/db-dumps/nextcloud-35.0.1-exec/log-errcount-pre.txt
#   EXPECT: >= 1 (known Mail STATUS/NONEXISTENT noise; loglevel is 2 so level 3/4 = errors). 0 => the path/level filter reads nothing: the §4 gate 6 log check is UNINSTRUMENTED and is informational only.

kubectl exec -n office nextcloud-mariadb-0 -c mariadb -- sh -c '
  mariadb -uroot -p"$(cat $MARIADB_ROOT_PASSWORD_FILE)" -N -B nextcloud -e "show tables" | wc -l
  for T in oc_filecache oc_mail_accounts oc_mail_mailboxes oc_mail_messages oc_users oc_calendarobjects oc_cards oc_migrations oc_appconfig oc_share; do
    printf "%s=%s\n" "$T" "$(mariadb -uroot -p"$(cat $MARIADB_ROOT_PASSWORD_FILE)" -N -B nextcloud -e "select count(*) from $T")"
  done' 2>/dev/null > /Users/mu/db-dumps/nextcloud-35.0.1-exec/rows-pre.txt
cat /Users/mu/db-dumps/nextcloud-35.0.1-exec/rows-pre.txt
```

EXPECT: first line **206** (2026-09-28 and 2026-10-05), every count > 0, `oc_mail_accounts=3`,
`oc_mail_mailboxes=31` (2026-09-28 — it was 35 on 09-26; take TODAY's number,
never this one). HOW IT FAILS: an empty file or a 0 means the exec/password
read failed — that is a failure, not "no rows".

**2.2b MAIL BASELINE — the operator's hard gate.** Facts (re-measured
2026-09-28, Mail **5.12.2**): `mail:account:list` does not exist;
`mail:account:diagnose` is now an ALIAS of `mail:account:test` and no longer
prints per-account message statistics (retired plan close-out) — so the
instruments are `mail:mailbox:list` (works on all three accounts) and the DB.

```bash
# CONTROL 1 — the instruments exist (a later "0" must not be a renamed command)
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ list mail" \
  | grep -cE '^ +mail:(mailbox:list|account:test|account:sync) '
#   EXPECT: 3   HOW IT FAILS: anything else => the gate below measures nothing. STOP.
# CONTROL 2 — accounts per the DB (ground truth; ids 1 2 3 on 2026-09-28)
kubectl exec -n office nextcloud-mariadb-0 -c mariadb -- sh -c \
  'mariadb -uroot -p"$(cat $MARIADB_ROOT_PASSWORD_FILE)" -N -B nextcloud -e "select account_id, count(*) from oc_mail_mailboxes group by account_id order by account_id"' \
  2>/dev/null > /Users/mu/db-dumps/nextcloud-35.0.1-exec/mail-mailboxes-db-pre.txt
cat /Users/mu/db-dumps/nextcloud-35.0.1-exec/mail-mailboxes-db-pre.txt
#   EXPECT (2026-09-28, unchanged 2026-10-05): "1 10 / 2 9 / 3 12" (tab-separated). Empty => STOP.
# The occ instrument, per account id FROM CONTROL 2 (never a hard-coded list)
for N in $(cut -f1 /Users/mu/db-dumps/nextcloud-35.0.1-exec/mail-mailboxes-db-pre.txt); do
  printf '%s\t' "$N"
  kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ mail:mailbox:list $N" \
    2>/dev/null | grep -c '^| [0-9]'
done > /Users/mu/db-dumps/nextcloud-35.0.1-exec/mail-mailboxcount-pre.txt
diff /Users/mu/db-dumps/nextcloud-35.0.1-exec/mail-mailboxes-db-pre.txt \
     /Users/mu/db-dumps/nextcloud-35.0.1-exec/mail-mailboxcount-pre.txt && echo "INSTRUMENT AGREES WITH DB"
#   EXPECT: INSTRUMENT AGREES WITH DB (measured 10/9/12 both ways 2026-09-28).
#   HOW IT FAILS: a mismatch => occ and the DB disagree before we touched anything; the §4
#   gate would be comparing noise. Resolve first.
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ mail:account:sync 999999" > /dev/null 2>&1; echo "NEGATIVE CONTROL sync exit=$?"
#   EXPECT: non-zero. 0 => the sync exit status carries no signal; gate 2(c) must then be judged on output text only.
# (c-pre) MANDATORY 34.0.4 IMAP BASELINE — the same loop §4 gate 2(c) runs after the
# upgrade, taken NOW so "per-account shape unchanged" has something to compare against.
# Distinct file names (-pre-) so the post run cannot overwrite them.
for N in $(cut -f1 /Users/mu/db-dumps/nextcloud-35.0.1-exec/mail-mailboxes-db-pre.txt); do
  echo "===== account $N ====="
  kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ mail:account:sync $N" > /Users/mu/db-dumps/nextcloud-35.0.1-exec/mail-sync-pre-$N.txt 2>&1
  echo "----- sync exit=$? -----"
  tail -3 /Users/mu/db-dumps/nextcloud-35.0.1-exec/mail-sync-pre-$N.txt
  kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ mail:account:test $N" > /Users/mu/db-dumps/nextcloud-35.0.1-exec/mail-test-pre-$N.txt 2>&1
  echo "----- test exit=$? -----"
  tail -5 /Users/mu/db-dumps/nextcloud-35.0.1-exec/mail-test-pre-$N.txt
done > /Users/mu/db-dumps/nextcloud-35.0.1-exec/mail-imap-pre.txt 2>&1
cat /Users/mu/db-dumps/nextcloud-35.0.1-exec/mail-imap-pre.txt
#   EXPECT: for EVERY account: sync exit=0, test exit=0, and "IMAP connection test passed".
#   HOW IT FAILS: any account failing HERE is a PRE-EXISTING failure on 34.0.4 — resolve it
#   or have the operator explicitly accept it BEFORE the GO; never attribute it to 35.0.1.
```

**2.3 Pre-change DB dump — the restore point for §5.3.**
`--default-character-set=utf8mb4` is load-bearing (tables are `utf8mb4_bin`;
without it 4-byte characters flatten to `?` — the lossy dump of
bitnamilegacy-exit-nextcloud-db attempt 1).

```bash
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ maintenance:mode --on"
#   A consistent point-in-time: no writes during the dump. (Users see maintenance from here.)
kubectl exec -n office nextcloud-mariadb-0 -c mariadb -- sh -c \
  'mariadb-dump -uroot -p"$(cat $MARIADB_ROOT_PASSWORD_FILE)" --default-character-set=utf8mb4 \
     --single-transaction --routines --triggers --events --databases nextcloud' 2>/dev/null \
  > /Users/mu/db-dumps/nextcloud-35.0.1-exec/nextcloud-pre-35.0.1.sql
chmod 600 /Users/mu/db-dumps/nextcloud-35.0.1-exec/nextcloud-pre-35.0.1.sql
ls -l  /Users/mu/db-dumps/nextcloud-35.0.1-exec/nextcloud-pre-35.0.1.sql          # NOT 0 bytes (~700 MB class)
tail -1 /Users/mu/db-dumps/nextcloud-35.0.1-exec/nextcloud-pre-35.0.1.sql         # "-- Dump completed ..."
grep -c 'CREATE TABLE' /Users/mu/db-dumps/nextcloud-35.0.1-exec/nextcloud-pre-35.0.1.sql       # == line 1 of rows-pre.txt
grep -c 'SET NAMES utf8mb4' /Users/mu/db-dumps/nextcloud-35.0.1-exec/nextcloud-pre-35.0.1.sql  # >= 1
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ maintenance:mode --off"
```

HOW IT FAILS: zero bytes, no trailer, a CREATE TABLE count below the §2.2
table count, or no `SET NAMES utf8mb4` => **no usable restore point: ABORT.**
(Maintenance is switched off again because Commit A restarts the pod anyway and
a stuck-on flag would confuse §3.2's gate.)

**2.3b Config backup — file-level, independent of the snapshot.** `config.php`
carries secrets: this file stays in the mode-700 exec dir on the Mac, never in
the repo, and is `rm -P`'d with the dump at close-out.

```bash
kubectl exec -n office deploy/nextcloud -c nextcloud -- tar cf - -C /var/www/html config \
  > /Users/mu/db-dumps/nextcloud-35.0.1-exec/config-pre-35.0.1.tar
chmod 600 /Users/mu/db-dumps/nextcloud-35.0.1-exec/config-pre-35.0.1.tar
tar tf /Users/mu/db-dumps/nextcloud-35.0.1-exec/config-pre-35.0.1.tar | grep -cE '^config/(config|custom\.config)\.php$'
#   EXPECT: 2 (both files present in the archive; 17 entries total on 2026-10-05).
#   HOW IT FAILS: 0 / "tar: Error" => the exec produced no archive: re-run; no Commit B without it.
tar xOf /Users/mu/db-dumps/nextcloud-35.0.1-exec/config-pre-35.0.1.tar config/config.php | grep -c "'version' => '34\.0\.4"
#   EXPECT: 1 — the archive is the 34 config, not an already-upgraded one.
helm history nextcloud -n office --max 1
#   EXPECT: deployed  nextcloud-9.3.0  34.0.4  (the row §4 floor compares against)
```

**2.4 Longhorn snapshots (same-day fast path; the 02:30 cleanup deletes them).**

```bash
for V in nextcloud-config nextcloud-mariadb; do kubectl apply -f - <<EOF
apiVersion: longhorn.io/v1beta2
kind: Snapshot
metadata:
  name: ${V}-pre-35-0-1
  namespace: storage
spec:
  volume: ${V}
  createSnapshot: true
EOF
done
sleep 10
kubectl -n storage get snapshots.longhorn.io nextcloud-config-pre-35-0-1 nextcloud-mariadb-pre-35-0-1 \
  -o custom-columns=NAME:.metadata.name,READY:.status.readyToUse,SIZE:.status.size
```

EXPECT `readyToUse true` on both. HOW IT FAILS: false/empty => §5.3(c) has no
fast path; the nextcloud-config rollback then needs the nightly backup restore
into a new volume (disaster-recovery SOP) — a conscious operator choice.

**2.5 Silence + active-update marker** (application-update SOP; 4 h TTL). One block.

```bash
runbooks/update-marker.sh add nextcloud office 4 "34.0.4->35.0.1 major (plan nextcloud-fleet-35.0.1)"
kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 >/dev/null 2>&1 & PF=$!
sleep 3
curl -s -X POST localhost:9093/api/v2/silences -H 'Content-Type: application/json' -d '{
  "matchers":[{"name":"namespace","value":"office","isRegex":false,"isEqual":true}],
  "startsAt":"'"$(.venv/bin/python3 -c "from datetime import *;print(datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")"'",
  "endsAt":"'"$(.venv/bin/python3 -c "from datetime import *;print((datetime.now(timezone.utc)+timedelta(hours=4)).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")"'",
  "createdBy":"maintenance-window-agent",
  "comment":"nextcloud 34.0.4->35.0.1 major (plan nextcloud-fleet-35.0.1). auto-expires 4h"}' \
  > /Users/mu/db-dumps/nextcloud-35.0.1-exec/silence.json
.venv/bin/python3 -c "import json;print('silenceID', json.load(open('/Users/mu/db-dumps/nextcloud-35.0.1-exec/silence.json'))['silenceID'])"
kill $PF 2>/dev/null
```

HOW IT FAILS: `KeyError: 'silenceID'` => the POST was rejected; do not proceed
believing you are silenced. The silence is deliberately NAMESPACE-WIDE (no
alertname matcher): the rollout alerts that fire here are kube-prometheus-stack
chart defaults that no repo PrometheusRule declares, so an alertname regex
naming them cannot be verified by `plan-premises.py --controls` — and a
namespace scope is honest about what it hides. That is why §6 keeps every other
`office` plan out of this slot, and why §3.6 deletes it the moment §4 is green.

## 3) Steps

**3.1 Go/no-go.** All premises PASS; §2.0 (a)-(e), §2.1-2.5 clean; dump, config
tar and snapshots verified; operator present; the operator's one-line re-confirm
of the lockstep shape (§1.7) is recorded via `home-operation decide`. Without it: STOP.

**3.2 Commit A — openclaw_mail compatibility ONLY (reloader rolls a 34.0.4 restart).**

```bash
cd /Users/mu/code/cberg-home-nextgen
git fetch origin main && git merge --ff-only origin/main
sed -i '' -E 's|^        <nextcloud min-version="30" max-version="34"/>$|        <nextcloud min-version="30" max-version="35"/>|' \
  kubernetes/apps/office/nextcloud/app/openclaw-mail/info.xml
git diff -- kubernetes/apps/office/nextcloud/app/openclaw-mail/info.xml
#   EXPECT exactly (dry-tested on a scratch copy 2026-09-28, BSD sed):
#   -        <nextcloud min-version="30" max-version="34"/>
#   +        <nextcloud min-version="30" max-version="35"/>
grep -c 'max-version="35"' kubernetes/apps/office/nextcloud/app/openclaw-mail/info.xml   # EXPECT 1
printf '%s\n\n%s\n\nCo-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>\n' \
  "feat(nextcloud): openclaw_mail declares NC 35 compatibility (plan nextcloud-fleet-35.0.1 commit A)" \
  "Without it occ upgrade 34->35 auto-disables the app (Updater::checkAppsRequirements) and the OpenClaw draft route dies. Separate commit so the reloader roll it triggers cannot overlap the 35 occ upgrade." \
  > /Users/mu/db-dumps/nextcloud-35.0.1-exec/msg-a.txt
git commit --only kubernetes/apps/office/nextcloud/app/openclaw-mail/info.xml -F /Users/mu/db-dumps/nextcloud-35.0.1-exec/msg-a.txt
git show --stat HEAD && git log -1 --format=%s        # ONLY info.xml; subject must be commit A's
git push origin main
```

Then wait for the reloader roll (Bash timeout 600000 ms):

```bash
kubectl -n office rollout status deploy/nextcloud --timeout=9m
kubectl exec -n office deploy/nextcloud -c nextcloud -- sh -c 'grep -o "<nextcloud[^>]*>" /var/www/html/custom_apps/openclaw_mail/appinfo/info.xml'
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ status --output=json"
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ app:list --output=json" \
  | .venv/bin/python3 -c "import sys,json;print('openclaw_mail', json.load(sys.stdin)['enabled'].get('openclaw_mail'))"
```

EXPECT: `max-version="35"` inside the pod; `34.0.4.1`, maintenance false;
`openclaw_mail 0.1.0`. HOW IT FAILS: still `max-version="34"` => reloader did not
roll (see `feedback_reloader_annotation_same_commit_no_roll`): check the pod
`startTime` is after the push; if not, `kubectl -n office rollout restart
deploy/nextcloud` ONCE (the only direct action this plan permits, and only here,
on 34.0.4). Do NOT start Commit B until this block is green.

**3.2b App pre-drain on 34.0.4 — take the 34-compatible app patches FIRST, gate Mail.**
In-pod `occ` is the only path for appstore app state (it lives on the
`nextcloud-config` volume + DB, no GitOps path); covered by the §2.3 dump and
§2.4 snapshot, both taken before this step. Why: §1.4 (Updater.php 397-411 would
otherwise swap Mail inside `occ upgrade`).

```bash
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ app:update --showonly"
#   EXPECT (2026-10-05): agenda_bot 1.7.1, richdocuments 11.1.2, calendar 6.6.2, google_synchronization 4.3.2,
#   mail 5.12.3, contacts 8.9.1 (patch drift is fine). EMPTY => already drained: skip to the Mail gate.
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ app:update --all" \
  > /Users/mu/db-dumps/nextcloud-35.0.1-exec/predrain.txt 2>&1; echo "app:update exit=$?"
cat /Users/mu/db-dumps/nextcloud-35.0.1-exec/predrain.txt
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ app:update --showonly"
#   EXPECT: exit=0; "<app> updated" per app; the second --showonly prints NOTHING.
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ status --output=json"
#   EXPECT: "version":"34.0.4.1" "maintenance":false "needsDbUpgrade":false
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ app:list --output=json" \
  > /Users/mu/db-dumps/nextcloud-35.0.1-exec/app-list-predrain.json
.venv/bin/python3 - <<'PY2'
import json
pre  = json.load(open('/Users/mu/db-dumps/nextcloud-35.0.1-exec/app-list-pre.json'))
post = json.load(open('/Users/mu/db-dumps/nextcloud-35.0.1-exec/app-list-predrain.json'))
assert set(pre['enabled']) == set(post['enabled']), ('ENABLED SET CHANGED on 34', set(pre['enabled']) ^ set(post['enabled']))
for a in ('mail','calendar','contacts','google_synchronization','richdocuments','openclaw_mail'):
    print(a, pre['enabled'].get(a), '->', post['enabled'].get(a))
PY2
#   EXPECT: no AssertionError; mail 5.12.2 -> 5.12.3 (or newer 34-compatible), openclaw_mail 0.1.0 -> 0.1.0.
```

Then the **Mail mini-gate on 34** — the §2.2b instruments, written to `-predrain-`
files so the §2.2b `-pre-` baselines are never overwritten (one Bash call):

```bash
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ list mail" \
  | grep -cE '^ +mail:(mailbox:list|account:test|account:sync) '          # EXPECT 3 (else the gate measures nothing: STOP)
kubectl exec -n office nextcloud-mariadb-0 -c mariadb -- sh -c \
  'mariadb -uroot -p"$(cat $MARIADB_ROOT_PASSWORD_FILE)" -N -B nextcloud -e "select account_id, count(*) from oc_mail_mailboxes group by account_id order by account_id"' \
  2>/dev/null > /Users/mu/db-dumps/nextcloud-35.0.1-exec/mail-mailboxes-db-predrain.txt
for N in $(cut -f1 /Users/mu/db-dumps/nextcloud-35.0.1-exec/mail-mailboxes-db-pre.txt); do
  printf '%s\t' "$N"
  kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ mail:mailbox:list $N" \
    2>/dev/null | grep -c '^| [0-9]'
done > /Users/mu/db-dumps/nextcloud-35.0.1-exec/mail-mailboxcount-predrain.txt
diff /Users/mu/db-dumps/nextcloud-35.0.1-exec/mail-mailboxes-db-pre.txt  /Users/mu/db-dumps/nextcloud-35.0.1-exec/mail-mailboxes-db-predrain.txt  && echo "PASS DB mailboxes identical (predrain)"
diff /Users/mu/db-dumps/nextcloud-35.0.1-exec/mail-mailboxcount-pre.txt /Users/mu/db-dumps/nextcloud-35.0.1-exec/mail-mailboxcount-predrain.txt && echo "PASS occ mailboxes identical (predrain)"
for N in $(cut -f1 /Users/mu/db-dumps/nextcloud-35.0.1-exec/mail-mailboxes-db-pre.txt); do
  echo "===== account $N ====="
  kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ mail:account:sync $N" > /Users/mu/db-dumps/nextcloud-35.0.1-exec/mail-sync-predrain-$N.txt 2>&1
  echo "----- sync exit=$? -----"
  tail -3 /Users/mu/db-dumps/nextcloud-35.0.1-exec/mail-sync-predrain-$N.txt
  kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ mail:account:test $N" > /Users/mu/db-dumps/nextcloud-35.0.1-exec/mail-test-predrain-$N.txt 2>&1
  echo "----- test exit=$? -----"
  tail -5 /Users/mu/db-dumps/nextcloud-35.0.1-exec/mail-test-predrain-$N.txt
done > /Users/mu/db-dumps/nextcloud-35.0.1-exec/mail-imap-predrain.txt 2>&1
cat /Users/mu/db-dumps/nextcloud-35.0.1-exec/mail-imap-predrain.txt
```

Compare `mail-imap-predrain.txt` with `mail-imap-pre.txt` (same per-account shape). PASS: identical mailbox counts, every account
`sync exit=0` + `IMAP connection test passed`, i.e. §4 gate 2's rule. HOW IT
FAILS: an autoload error naming `custom_apps/mail` or a lost account => §5.1
steps 1-3 for `mail` ON 34 (the instance is not yet migrated, so this is cheap);
if Mail cannot be made green on 34, STOP before Commit B (§5.4: nothing else to
undo; the §5.3(b)/(c) restore returns Mail to 5.12.2 if the operator wants it).
Also confirm the next SCHEDULED cron run completes (schedule `*/5 * * * *`; no
manual Job — this plan makes no direct object), since the 2026-06-06 Mail
breakage showed up as cron pods in `Error`:

```bash
date -u +%Y-%m-%dT%H:%M:%SZ > /Users/mu/db-dumps/nextcloud-35.0.1-exec/predrain-done.txt
# wait >= 6 min after the line above, then:
kubectl -n office get jobs --sort-by=.metadata.creationTimestamp \
  -o custom-columns=NAME:.metadata.name,CREATED:.metadata.creationTimestamp,SUCCEEDED:.status.succeeded,FAILED:.status.failed \
  | grep nextcloud-cron | tail -2
#   PASS: a Job CREATED after the timestamp in predrain-done.txt with SUCCEEDED 1, FAILED <none>.
#   HOW IT FAILS: no newer Job (cronjob suspended / controller stuck) or FAILED >= 1 =>
#   `kubectl -n office logs job/<name>`; STOP before Commit B.
```

**3.3 Commit B — the major + the chart, in lockstep. Chart pin + image pins + temporary remediation-off + startup budget.**

```bash
cd /Users/mu/code/cberg-home-nextgen
git fetch origin main && git merge --ff-only origin/main
sed -i '' -E 's|^      version: 9\.3\.0$|      version: 9.4.0|' kubernetes/apps/office/nextcloud/app/helmrelease.yaml
sed -i '' -E 's|^      tag: 34\.0\.4$|      tag: 35.0.1|' kubernetes/apps/office/nextcloud/app/helmrelease.yaml
sed -i '' -E 's|^          image: nextcloud:34\.0\.4$|          image: nextcloud:35.0.1|' \
  kubernetes/apps/office/nextcloud/app/helmrelease.yaml kubernetes/apps/office/nextcloud/app/notify-push.yaml
.venv/bin/python3 - <<'PY'
p = '/Users/mu/code/cberg-home-nextgen/kubernetes/apps/office/nextcloud/app/helmrelease.yaml'
s = open(p).read()
a = "  upgrade:\n    cleanupOnFail: true\n    remediation:\n      retries: 3\n"
b = ("  upgrade:\n    cleanupOnFail: true\n    remediation:\n"
     "      retries: 0                 # TEMPORARY (plan nextcloud-fleet-35.0.1 §3.3) - restore 3 in §3.6\n"
     "      remediateLastFailure: false\n")
c = ("    startupProbe:\n      enabled: true\n      initialDelaySeconds: 60\n      periodSeconds: 30\n"
     "      timeoutSeconds: 5\n      failureThreshold: 10\n")
d = ("    startupProbe:\n      enabled: true\n      initialDelaySeconds: 60\n      periodSeconds: 30\n"
     "      timeoutSeconds: 5\n      failureThreshold: 50               # TEMPORARY (plan nextcloud-fleet-35.0.1 §3.3) - restore 10 in §3.6\n")
assert s.count(a) == 1, 'remediation block not found exactly once'
assert s.count(c) == 1, 'startupProbe block not found exactly once'
s = s.replace(a, b, 1).replace(c, d, 1)
open(p, 'w').write(s)
print('remediation 3->0, startupProbe failureThreshold 10->50')
PY
git diff --stat -- kubernetes/apps/office/nextcloud/app/
```

The diff dry-tested on scratch copies of git HEAD (2026-10-05, BSD sed + the
python block above) is exactly:

```
helmrelease.yaml  11c11     version: 9.3.0 -> version: 9.4.0
helmrelease.yaml  25c25,26  retries: 3  ->  retries: 0 # TEMPORARY ... + remediateLastFailure: false
helmrelease.yaml  34c35     tag: 34.0.4 ->  tag: 35.0.1
helmrelease.yaml  234c235   image: nextcloud:34.0.4 -> image: nextcloud:35.0.1
helmrelease.yaml  544c545   failureThreshold: 10 -> failureThreshold: 50 # TEMPORARY ...
notify-push.yaml  40c40     image: nextcloud:34.0.4 -> image: nextcloud:35.0.1
```

Gates (each bare number stated; the "expect 0" line exits 1 and that IS the pass):

```bash
cd /Users/mu/code/cberg-home-nextgen
grep -c '^      version: 9\.4\.0$'              kubernetes/apps/office/nextcloud/app/helmrelease.yaml   # 1
grep -c '9\.3\.0'                              kubernetes/apps/office/nextcloud/app/helmrelease.yaml   # 0 (exits 1 = pass)
grep -c '^      tag: 35\.0\.1$'                 kubernetes/apps/office/nextcloud/app/helmrelease.yaml   # 1
grep -c '^          image: nextcloud:35\.0\.1$' kubernetes/apps/office/nextcloud/app/helmrelease.yaml   # 1
grep -c '^          image: nextcloud:35\.0\.1$' kubernetes/apps/office/nextcloud/app/notify-push.yaml   # 1
grep -c 'failureThreshold: 50 '                kubernetes/apps/office/nextcloud/app/helmrelease.yaml   # 1
grep -c 'retries: 0 '                          kubernetes/apps/office/nextcloud/app/helmrelease.yaml   # 1
grep -c '34\.0\.4' kubernetes/apps/office/nextcloud/app/helmrelease.yaml kubernetes/apps/office/nextcloud/app/notify-push.yaml
#   PASS: two lines each ending ":0"
kubectl kustomize kubernetes/apps/office/nextcloud/app >/dev/null && echo RENDER-OK
# The FULL Commit B render, chart 9.4.0 + the edited values, against §2.0(e)'s render-93.yaml:
.venv/bin/python3 -c "
import yaml;d=yaml.safe_load(open('kubernetes/apps/office/nextcloud/app/helmrelease.yaml'))
yaml.safe_dump(d['spec']['values'],open('/Users/mu/db-dumps/nextcloud-35.0.1-exec/values-b.yaml','w'))"
helm template nextcloud /Users/mu/db-dumps/nextcloud-35.0.1-exec/c94/nextcloud -n office \
  -f /Users/mu/db-dumps/nextcloud-35.0.1-exec/values-b.yaml > /Users/mu/db-dumps/nextcloud-35.0.1-exec/render-94-b.yaml || echo "RENDER B FAILED"
diff /Users/mu/db-dumps/nextcloud-35.0.1-exec/render-93.yaml /Users/mu/db-dumps/nextcloud-35.0.1-exec/render-94-b.yaml | grep -E '^[<>]' \
  | grep -vE '^[<>] +(helm\.sh/chart: nextcloud-9\.[34]\.0|app\.kubernetes\.io/version: "(34\.0\.4|35\.0\.1)"|(image: (docker\.io/)?nextcloud:(34\.0\.4|35\.0\.1))|failureThreshold: (10|50))$' | wc -l
diff /Users/mu/db-dumps/nextcloud-35.0.1-exec/render-93.yaml /Users/mu/db-dumps/nextcloud-35.0.1-exec/render-94-b.yaml | grep -c '^>'
#   PASS (dry-run 2026-10-05): first count 0; second count 18 (14 labels + 3 image lines + 1 probe line).
#   HOW IT FAILS: first count > 0 => Commit B renders something the plan did not plan: STOP, git checkout the two files.
# Row baseline RIGHT BEFORE Commit B (users wrote for ~35-45 min since §2.2): §4 gate 1 diffs against THIS.
kubectl exec -n office nextcloud-mariadb-0 -c mariadb -- sh -c '
  mariadb -uroot -p"$(cat $MARIADB_ROOT_PASSWORD_FILE)" -N -B nextcloud -e "show tables" | wc -l
  for T in oc_filecache oc_mail_accounts oc_mail_mailboxes oc_mail_messages oc_users oc_calendarobjects oc_cards oc_migrations oc_appconfig oc_share; do
    printf "%s=%s\n" "$T" "$(mariadb -uroot -p"$(cat $MARIADB_ROOT_PASSWORD_FILE)" -N -B nextcloud -e "select count(*) from $T")"
  done' 2>/dev/null > /Users/mu/db-dumps/nextcloud-35.0.1-exec/rows-preB.txt
cat /Users/mu/db-dumps/nextcloud-35.0.1-exec/rows-preB.txt        # EXPECT 11 lines, every count > 0; empty/0 => exec failed: re-run before committing
printf '%s\n\n%s\n\n%s\n\nCo-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>\n' \
  "feat(nextcloud): 34.0.4 -> 35.0.1 (major) + chart 9.3.0 -> 9.4.0 lockstep + notify-push (plan nextcloud-fleet-35.0.1)" \
  "Chart 9.4.0 differs from 9.3.0 only in Chart.yaml appVersion 34.0.4 -> 35.0.1 (rendered: metadata labels only). TEMPORARY for this rollout: upgrade.remediation.retries 0 and startupProbe.failureThreshold 50 (26 min budget for occ upgrade + 5 app-major downloads); both restored in the follow-up commit." \
  "finding_refs: F-7344f3ec F-7bcfda63 F-38fecaa8 F-c5e87023" \
  > /Users/mu/db-dumps/nextcloud-35.0.1-exec/msg-b.txt
git commit --only kubernetes/apps/office/nextcloud/app/helmrelease.yaml kubernetes/apps/office/nextcloud/app/notify-push.yaml \
  -F /Users/mu/db-dumps/nextcloud-35.0.1-exec/msg-b.txt
git show --stat HEAD && git log -1 --format=%s       # EXACTLY these 2 files; subject is commit B's — else amend BEFORE push
git rev-parse HEAD > /Users/mu/db-dumps/nextcloud-35.0.1-exec/bump-sha.txt
git push origin main
```

**3.4 Watch the rollout (the attended part).** Recreate: the old pod goes, the
new one runs rsync -> `occ upgrade`. Budget: 1560 s from container start.
A HelmRelease that reports Failed (upgrade timeout: HR timeout is 30m against the 26m
startup budget plus pull/init/readiness) while §4 is green is NOT a §5 trigger — with
retries: 0 there is no auto-rollback, and the §3.6 spec change re-runs the upgrade.

```bash
flux get helmrelease -n office nextcloud                         # Upgrading
POD=$(kubectl -n office get pod -l app.kubernetes.io/name=nextcloud,app.kubernetes.io/component=app -o jsonpath='{.items[0].metadata.name}')
echo "pod=$POD started=$(kubectl -n office get pod "$POD" -o jsonpath='{.status.containerStatuses[?(@.name=="nextcloud")].state.running.startedAt}') now=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
kubectl -n office logs "$POD" -c nextcloud --timestamps --tail=60
```

Re-issue every ~60 s (bounded reads; no `-f`, no `-w`). Expected shape:

```
Initializing nextcloud 35.0.1.x ...
Upgrading nextcloud from 34.0.4.1 ...
Initializing finished                       <- rsync done (budget ~5-8 min on this RWX volume)
Turned on maintenance mode / Updating database schema / Updated database
Disabled incompatible app: spreed | richdocuments | assistant | integration_openai |
  files_automatedtagging | context_chat      <- EXPECTED (§1.4). openclaw_mail must NOT appear.
Checking for update of app ... / Update app <x> from App Store  <- the 5 majors download here
Update successful / Turned off maintenance mode
The following apps have been disabled:       <- entrypoint's own diff; EXPECT exactly: context_chat
```

HOW IT FAILS: `openclaw_mail` in a "disabled" line => Commit A did not reach the
pod: §5.1 step 4. A second "disabled" name besides `context_chat` => that app's
download failed: §5.1 (reinstall + enable). Still inside `occ upgrade` at ~24 min
after start => prepare §5.2; do not delete pods, do not scale.

```bash
kubectl -n office rollout status deploy/nextcloud --timeout=9m              # re-issue while the log shows progress
kubectl -n office rollout status deploy/nextcloud-notify-push --timeout=5m
flux get helmrelease -n office nextcloud                                     # Ready True
```

`rollout status` green is NOT proof — §4 checks the running digest.

**3.5 Verify** — §4 in full.

**3.6 Close out (only after §4 is green).**

```bash
cd /Users/mu/code/cberg-home-nextgen
git fetch origin main && git merge --ff-only origin/main
.venv/bin/python3 - <<'PY'
p = '/Users/mu/code/cberg-home-nextgen/kubernetes/apps/office/nextcloud/app/helmrelease.yaml'
s = open(p).read()
a = ("      retries: 0                 # TEMPORARY (plan nextcloud-fleet-35.0.1 §3.3) - restore 3 in §3.6\n"
     "      remediateLastFailure: false\n")
c = "      failureThreshold: 50               # TEMPORARY (plan nextcloud-fleet-35.0.1 §3.3) - restore 10 in §3.6\n"
assert s.count(a) == 1 and s.count(c) == 1, 'temporary blocks not found — check by hand'
s = s.replace(a, "      retries: 3\n", 1).replace(c, "      failureThreshold: 10\n", 1)
open(p, 'w').write(s); print('restored retries 3 + startup failureThreshold 10')
PY
grep -c 'TEMPORARY (plan nextcloud-fleet-35.0.1' kubernetes/apps/office/nextcloud/app/helmrelease.yaml   # EXPECT 0 (exits 1)
git diff -- kubernetes/apps/office/nextcloud/app/helmrelease.yaml | grep -c '^[-+] '                     # EXPECT 5 (3 removed + 2 added)
printf '%s\n\nCo-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>\n' \
  "chore(nextcloud): restore remediation retries 3 + startupProbe 10 after the 35.0.1 rollout (plan nextcloud-fleet-35.0.1 §3.6)" \
  > /Users/mu/db-dumps/nextcloud-35.0.1-exec/msg-c.txt
git commit --only kubernetes/apps/office/nextcloud/app/helmrelease.yaml -F /Users/mu/db-dumps/nextcloud-35.0.1-exec/msg-c.txt
git show --stat HEAD && git log -1 --format=%s && git push origin main
```

This restore commit rolls the pod once more (probe spec change) — a plain 35 ->
35 restart; re-run §4's floor + gate 2(c) after it. Then:

```bash
runbooks/update-marker.sh clear nextcloud
kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 >/dev/null 2>&1 & PF=$!
sleep 3
curl -s -X DELETE "localhost:9093/api/v2/silence/$(.venv/bin/python3 -c "import json;print(json.load(open('/Users/mu/db-dumps/nextcloud-35.0.1-exec/silence.json'))['silenceID'])")" -o /dev/null -w "DELETE -> HTTP %{http_code}\n"
curl -s localhost:9093/api/v2/silences | .venv/bin/python3 -c "
import sys,json
a=[s for s in json.load(sys.stdin) if s['status']['state']=='active' and 'nextcloud-fleet-35.0.1' in s.get('comment','')]
print('plan silences still active:', len(a))"
kill $PF 2>/dev/null
for F in F-7344f3ec F-7bcfda63 F-38fecaa8; do   # F-c5e87023 (security) re-measures on the next sweep's image scan
  .venv/bin/python3 runbooks/policy-cli.py finding close "$F" --commit "$(cat /Users/mu/db-dumps/nextcloud-35.0.1-exec/bump-sha.txt)"
done
```

Retire this plan file in the commit that records the window. Keep the exec dir
until the next nightly Longhorn backup covers the 35 state, then `rm -P` the dump
AND `config-pre-35.0.1.tar` (it holds `config.php` secrets).

## 4) Verification

Floor (shape — necessary, not sufficient):

```bash
kubectl get helmrelease -n office nextcloud -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion}{"\n"}'
#   EXPECT: True 9.4.0
helm history nextcloud -n office --max 1
#   EXPECT: deployed  nextcloud-9.4.0  35.0.1   (pre: nextcloud-9.3.0 34.0.4 — §2.3b)
kubectl get deploy -n office nextcloud -o jsonpath='{.metadata.labels.helm\.sh/chart} {.metadata.labels.app\.kubernetes\.io/version}{"\n"}'
#   CONTENTS ASSERTION (chart leg): "nextcloud-9.4.0 35.0.1". FAIL shape "nextcloud-9.3.0 34.0.4"
#   (measured live 2026-10-05, so the gate demonstrably reads the label) => chart leg not applied.
kubectl -n office get pod -l app.kubernetes.io/name=nextcloud,app.kubernetes.io/component=app \
  -o jsonpath='{range .items[0].status.containerStatuses[*]}{.name}{" "}{.imageID}{" restarts="}{.restartCount}{"\n"}{end}'
#   EXPECT: nextcloud + worker on a nextcloud@sha256 digest of 35.0.1 (compare with §2.0(a) or the index).
#   HOW IT FAILS: a 34.0.4 digest (sha256:20298c35... index) => the pod never rolled.
kubectl -n office get pod -l app=nextcloud-notify-push -o jsonpath='{.items[0].status.containerStatuses[0].image}{"\n"}'   # nextcloud:35.0.1
kubectl -n office get cronjob nextcloud-cron -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].image}{" suspend="}{.spec.suspend}{"\n"}'
#   EXPECT: docker.io/nextcloud:35.0.1 suspend=false
kubectl -n office get jobs --sort-by=.metadata.creationTimestamp | grep nextcloud-cron | tail -2
#   EXPECT: newest Job that STARTED after the rollout is Complete 1/1 (the 2026-06-06 failure = cron pods Error)
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ status --output=json"
#   EXPECT: "versionstring":"35.0.1" "maintenance":false "needsDbUpgrade":false
```

**1. CONTENTS ASSERTION: the database still holds the data** — same loop as
§2.2 into `rows-post.txt`, diffed with `rows-preB.txt` (taken in §3.3 right before
Commit B; `rows-pre.txt` is ~35-45 min older and is the §5.3 restore reference only).

```bash
kubectl exec -n office nextcloud-mariadb-0 -c mariadb -- sh -c '
  mariadb -uroot -p"$(cat $MARIADB_ROOT_PASSWORD_FILE)" -N -B nextcloud -e "show tables" | wc -l
  for T in oc_filecache oc_mail_accounts oc_mail_mailboxes oc_mail_messages oc_users oc_calendarobjects oc_cards oc_migrations oc_appconfig oc_share; do
    printf "%s=%s\n" "$T" "$(mariadb -uroot -p"$(cat $MARIADB_ROOT_PASSWORD_FILE)" -N -B nextcloud -e "select count(*) from $T")"
  done' 2>/dev/null > /Users/mu/db-dumps/nextcloud-35.0.1-exec/rows-post.txt
diff /Users/mu/db-dumps/nextcloud-35.0.1-exec/rows-preB.txt /Users/mu/db-dumps/nextcloud-35.0.1-exec/rows-post.txt
```

PASS: every count > 0; `oc_users`, `oc_mail_accounts` **equal**;
`oc_calendarobjects`, `oc_cards`, `oc_share` **no decrease** (DAV clients may
write between `rows-preB` and the Recreate; a DROP is the failure); cron may move
`oc_filecache`/`oc_mail_messages` slightly — allow +/- 1 %, never a large drop;
`oc_migrations` **strictly greater** (the 35 migrations are recorded); table
count >= pre (a major may add tables). HOW IT FAILS: a structurally healthy but
emptied table — `occ status` would never see it.

**2. CONTENTS ASSERTION: Mail works, per account (the operator's hard gate).**

```bash
# (a) CONTROLS again — instruments still exist post-upgrade
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ list mail" \
  | grep -cE '^ +mail:(mailbox:list|account:test|account:sync) '                        # EXPECT 3
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ app:list --output=json" \
  | .venv/bin/python3 -c "import sys,json;print('mail', json.load(sys.stdin)['enabled'].get('mail'))"   # EXPECT the version §3.2b left (5.12.3 on 2026-10-05) — UNCHANGED by the major
# (b) mailbox count per account, DB and occ, against the pre baseline
kubectl exec -n office nextcloud-mariadb-0 -c mariadb -- sh -c \
  'mariadb -uroot -p"$(cat $MARIADB_ROOT_PASSWORD_FILE)" -N -B nextcloud -e "select account_id, count(*) from oc_mail_mailboxes group by account_id order by account_id"' \
  2>/dev/null > /Users/mu/db-dumps/nextcloud-35.0.1-exec/mail-mailboxes-db-post.txt
for N in $(cut -f1 /Users/mu/db-dumps/nextcloud-35.0.1-exec/mail-mailboxes-db-pre.txt); do
  printf '%s\t' "$N"
  kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ mail:mailbox:list $N" \
    2>/dev/null | grep -c '^| [0-9]'
done > /Users/mu/db-dumps/nextcloud-35.0.1-exec/mail-mailboxcount-post.txt
diff /Users/mu/db-dumps/nextcloud-35.0.1-exec/mail-mailboxes-db-pre.txt  /Users/mu/db-dumps/nextcloud-35.0.1-exec/mail-mailboxes-db-post.txt && echo "PASS DB mailboxes identical"
diff /Users/mu/db-dumps/nextcloud-35.0.1-exec/mail-mailboxcount-pre.txt /Users/mu/db-dumps/nextcloud-35.0.1-exec/mail-mailboxcount-post.txt && echo "PASS occ mailboxes identical"
# (c) a real IMAP round-trip per account: sync, then the connection test
for N in $(cut -f1 /Users/mu/db-dumps/nextcloud-35.0.1-exec/mail-mailboxes-db-pre.txt); do
  echo "===== account $N ====="
  kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ mail:account:sync $N" > /Users/mu/db-dumps/nextcloud-35.0.1-exec/mail-sync-$N.txt 2>&1
  echo "----- sync exit=$? -----"
  tail -3 /Users/mu/db-dumps/nextcloud-35.0.1-exec/mail-sync-$N.txt
  kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ mail:account:test $N" > /Users/mu/db-dumps/nextcloud-35.0.1-exec/mail-test-$N.txt 2>&1
  echo "----- test exit=$? -----"
  tail -5 /Users/mu/db-dumps/nextcloud-35.0.1-exec/mail-test-$N.txt
done > /Users/mu/db-dumps/nextcloud-35.0.1-exec/mail-imap-post.txt 2>&1
cat /Users/mu/db-dumps/nextcloud-35.0.1-exec/mail-imap-post.txt
```

**Diff the shape against `mail-imap-pre.txt`** (the §2.2b (c-pre) baseline taken on 34.0.4) —
the pass rule is "per-account shape unchanged".
PASS requires: both (b) diffs print PASS (mailbox counts are the hard equality;
a `0` is an error, not an empty account — control (a) distinguishes them);
every account's `sync` exits 0; `test` shows an established IMAP session
(capabilities / success line) for every account. Known-benign, never a rollback
reason by themselves: the iCloud account's intermittent `STATUS` errors (retry
up to 3x — `project_nextcloud_mail_account_quirks`), and a Gmail account's
`[NONEXISTENT]` on the `[Google Mail]` `\NoSelect` container (F-85ee12b0 shape).
HOW IT FAILS: an auth error, a PHP autoload error naming `custom_apps/mail`
(the 2026-06-06 failure: every occ breaks while `status.php` stays 200), a
mailbox count change, or an exit != 0 that persists across 3 retries.
Finally, **MANDATORY browser check (SD-8, done by the coordinator in Chrome —
not delegated to the operator, not skippable):** open Mail in the web UI and
read one message body per account (3 accounts), and confirm the account list
shows all 3. PASS only with 3 bodies rendered. A body-fetch 500 on Gmail right
after a relabel is the stale-UID quirk: `mail:account:sync` and re-open before
concluding anything. Record the result in the window report; gate 2 is not
green without it.

**3. CONTENTS ASSERTION: the enabled-app set is what §1.4 predicts, and the
custom OpenClaw route survived.**

```bash
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ app:list --output=json" \
  > /Users/mu/db-dumps/nextcloud-35.0.1-exec/app-list-post.json
.venv/bin/python3 - <<'PY'
import json
pre  = json.load(open('/Users/mu/db-dumps/nextcloud-35.0.1-exec/app-list-pre.json'))
post = json.load(open('/Users/mu/db-dumps/nextcloud-35.0.1-exec/app-list-post.json'))
lost = set(pre['enabled']) - set(post['enabled'])
assert lost <= {'context_chat'}, ('UNEXPECTEDLY DISABLED — §5.1 reinstall/enable', lost)
for a in ('mail','openclaw_mail','notify_push','google_synchronization','whiteboard','richdocuments','spreed','calendar','contacts'):
    assert a in post['enabled'], f'{a} LEFT THE ENABLED SET'
want = {'spreed':'25.','richdocuments':'12.','assistant':'4.','integration_openai':'5.','files_automatedtagging':'6.'}
for a, v in want.items():
    got = post['enabled'].get(a, '')
    assert got.startswith(v), (a, 'expected', v, 'got', got)
print('OK enabled', len(post['enabled']), '(pre', len(pre['enabled']), ') lost:', sorted(lost))
PY
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ app:update --showonly"
```

PASS: `OK enabled 67 (pre 68) lost: ['context_chat']` (or 68 / `[]` if a stable
context_chat 35 release shipped). HOW IT FAILS: any other lost app, or an app
still on its 34-line version (its download failed and it was re-enabled on old
code — or not re-enabled). `openclaw_mail` missing => the draft route is down
even though Nextcloud looks healthy; §5.1 step 4. Re-force-enable nothing
blindly: first read why it was disabled in `nextcloud.log`.

**4. CONTENTS ASSERTION: the monitoring exporter reports the UPGRADED instance.**

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 >/dev/null 2>&1 & PF=$!
sleep 3
for Q in 'nextcloud_up' 'nextcloud_system_info' 'nextcloud_users_total' 'nextcloud_up{job="does-not-exist"}'; do
  printf '%s => ' "$Q"
  curl -s localhost:9090/api/v1/query --data-urlencode "query=$Q" | .venv/bin/python3 -c "
import sys,json; r=json.load(sys.stdin)['data']['result']; print([(x['metric'].get('version',''), x['value'][1]) for x in r])"
done
kill $PF 2>/dev/null
```

CONTROL: metric nextcloud_up — must be `1` on the `nextcloud-metrics` job (measured present 2026-09-28, value 1).
CONTROL: metric nextcloud_system_info — the `version` label must read `35.0.1.x`, value 1 (was `34.0.4.1`).
CONTROL: metric nextcloud_users_total — must equal `oc_users` in `rows-post.txt`.
CONTROL: alertname LonghornBackupFailed — must be NOT firing for `nextcloud-config`/`nextcloud-mariadb` before §3.2 (the durable floor exists).

PASS: `nextcloud_up` 1, `system_info` version `35.0.1.*`, users equal.
The deliberately-wrong query (`job="does-not-exist"`) MUST print `[]` — that is
the negative control proving an empty result is what "absent" looks like; if it
prints data the query path is broken. HOW IT FAILS: version still `34.0.4.*`
(exporter reading a stale pod or the scrape stopped: check `up{job="nextcloud-metrics"}`),
or `[]` for `nextcloud_up` (scrape broken — the series existed at baseline).
Scrape interval lag: wait 2 min after Ready before reading.

**5. CONTENTS ASSERTION: live push works end to end.**

```bash
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ notify_push:self-test"
```

PASS: all lines green incl. *"push server is receiving redis messages"* and
*"push server is running the same version as the app"* — a real write through
redis to the rebuilt container. HOW IT FAILS: the version line red => notify-push
did not roll onto 35.0.1.

**6. External path + logs.**

```bash
curl -s "https://drive.<SECRET_DOMAIN>/status.php"     # substitute the real host by hand — not in this repo
#   EXPECT: "maintenance":false,"versionstring":"35.0.1"
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "tail -2000 /var/www/html/data/nextcloud.log" \
  | grep -ciE '"level":[34]'
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "tail -2000 /var/www/html/data/nextcloud.log" \
  | grep -iE '"level":[34]' > /Users/mu/db-dumps/nextcloud-35.0.1-exec/log-err-post.txt
# Exclusion is case-SENSITIVE and specific (the known Mail noise only): a case-insensitive
# 'STATUS' would also drop /status.php, getStatus and "HTTP status 500" upgrade errors.
echo "excluded-as-known-noise: $(grep -cE 'Horde_Imap_Client|\[NONEXISTENT\]| STATUS ' /Users/mu/db-dumps/nextcloud-35.0.1-exec/log-err-post.txt)"
grep -vE 'Horde_Imap_Client|\[NONEXISTENT\]| STATUS ' /Users/mu/db-dumps/nextcloud-35.0.1-exec/log-err-post.txt | tail -20
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ integrity:check-core"   # INFORMATIONAL ONLY: absence-shaped, never shown to fire on this instance; not a PASS criterion
```

The first grep is the CONTROL (the log path/level filter matches something — at
baseline the known Mail noise produced lines); the second must show no
upgrade-related errors (autoload, migration, "app not compatible" for anything
but context_chat). **Attended:** operator opens Files (list + one download),
Calendar, one Office document (richdocuments 12 + CODE), and Talk once.

## 5) Rollback

Decide by evidence. Tiers in order of likelihood.

**5.1 Stuck maintenance mode and/or a broken or disabled app after `occ upgrade`.**
Symptoms: `maintenance: true`; every `occ` fails with an autoload error naming
`custom_apps/<app>`; cron pods `Error`; an app missing from §4 gate 3.

```bash
# 1. get occ loading — move a half-extracted app aside (ONLY if an autoload error names it)
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "mv /var/www/html/custom_apps/<app> /var/www/html/custom_apps/<app>.broken"
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ status"
# 2. finish the upgrade
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ upgrade"
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ maintenance:mode --off"
# 3. reinstall / update the app from the appstore (35-compatible release)
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "rm -rf /var/www/html/custom_apps/<app>.broken"
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ app:install <app>"   # or app:update <app> if present
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ app:enable <app>"
# 4. openclaw_mail specifically (NOT an appstore app — never app:install it):
kubectl exec -n office deploy/nextcloud -c nextcloud -- sh -c 'grep -o "<nextcloud[^>]*>" /var/www/html/custom_apps/openclaw_mail/appinfo/info.xml'
#    must read max-version="35" (Commit A); then:
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ app:enable openclaw_mail"
```

If it was `mail`: re-run §4 gate 2 in full. If `notify_push`:
`kubectl -n office rollout restart deploy/nextcloud-notify-push`, then gate 5.
Then §4 in full.

**5.2 The startup probe (26 min budget) killed the container mid-`occ upgrade`.**
The kubelet restarts it; `version.php` is copied last by the rsync, so the
entrypoint now sees image == installed and skips straight to Apache with
Nextcloud still in maintenance. With `retries: 0` Flux does not "help". Run
§5.1 steps 2-3 (`occ upgrade`, `maintenance:mode --off`), then check every
app in §1.4's table. If the kill happened DURING the rsync (no `Initializing
finished` in the previous container's log — `kubectl logs --previous`), nothing
was migrated: the restarted container simply re-runs the upgrade.

**5.3 Full rollback to 34.0.4 — only if the instance must go back in time.**
A bare `git revert` is NOT a rollback: the 34 image refuses 35 data
(entrypoint lines 184-186) and crash-loops. Restore data first. **The CIFS data
PVC (`nextcloud-data`) is NOT touched in any step** — files written to it during
the window survive; a DB restore to the pre-state can leave such files unknown to
the filecache (a later `occ files:scan --all` repairs that; maintenance mode made
the window small).

```bash
# (a) freeze GitOps, stop every writer of the two Longhorn volumes
flux suspend kustomization -n office nextcloud && flux suspend helmrelease -n office nextcloud
kubectl -n office scale deploy/nextcloud deploy/nextcloud-notify-push --replicas=0
kubectl -n office patch cronjob nextcloud-cron -p '{"spec":{"suspend":true}}'
kubectl -n office wait --for=delete pod -l app.kubernetes.io/name=nextcloud,app.kubernetes.io/component=app --timeout=5m
# cron Job pods also mount the RWX nextcloud-config volume: suspend (above) stops NEW runs; wait out a running one
for i in $(seq 1 20); do
  R=$(kubectl get pods -n office -l app.kubernetes.io/name=nextcloud,app.kubernetes.io/component=cronjob --field-selector=status.phase=Running -o name | wc -l | tr -d ' ')
  echo "running cron pods=$R"; [ "$R" = "0" ] && break; sleep 15
done
#   EXPECT: running cron pods=0 (read 0 live 2026-10-05; runs last ~20 s). Still >0 after 5 min => a hung
#   cron pod holds the volume: STOP, inspect it with the operator; do NOT detach/revert under it.
# (b) DB back to the §2.3 dump — CHECK THE FILE FIRST, the DROP is irreversible
ls -l /Users/mu/db-dumps/nextcloud-35.0.1-exec/nextcloud-pre-35.0.1.sql
tail -1 /Users/mu/db-dumps/nextcloud-35.0.1-exec/nextcloud-pre-35.0.1.sql     # "-- Dump completed" or STOP
kubectl exec -n office nextcloud-mariadb-0 -c mariadb -- sh -c \
  'mariadb -uroot -p"$(cat $MARIADB_ROOT_PASSWORD_FILE)" -e "DROP DATABASE nextcloud; CREATE DATABASE nextcloud CHARACTER SET utf8mb4 COLLATE utf8mb4_bin"'
kubectl exec -i -n office nextcloud-mariadb-0 -c mariadb -- sh -c \
  'mariadb -uroot -p"$(cat $MARIADB_ROOT_PASSWORD_FILE)" --default-character-set=utf8mb4' \
  < /Users/mu/db-dumps/nextcloud-35.0.1-exec/nextcloud-pre-35.0.1.sql 2>&1 | tail -5
# re-run the §2.2 row loop into rows-restored.txt; diff with rows-pre.txt: must be IDENTICAL
```

(c) code + custom_apps + config: revert **Longhorn volume `nextcloud-config`**
to snapshot `nextcloud-config-pre-35-0-1` — Longhorn UI -> Volume
nextcloud-config (detached after (a)) -> Attach in Maintenance Mode ->
Snapshots -> `nextcloud-config-pre-35-0-1` -> Revert -> Detach. If the snapshot
is gone (02:30 cleanup), restore the last nightly backup into a new volume per
`docs/sops/disaster-recovery.md` + `docs/sops/longhorn.md`. (The snapshot
predates Commit A AND the §3.2b pre-drain, so it also carries `openclaw_mail`
max-34 and Mail 5.12.2 etc. — consistent with the §2.3 dump, which predates both
too; Commit A itself is harmless on 34 and is NOT reverted.)

**Config-only fallback** (if the volume revert is impossible and a nightly-backup
restore is the route, or after it, to put the exact pre-window `config/` back):
with the volume attached to a running 34.0.4 pod again,

```bash
tar tf /Users/mu/db-dumps/nextcloud-35.0.1-exec/config-pre-35.0.1.tar | grep -c '^config/config\.php$'    # 1 or STOP
kubectl exec -i -n office deploy/nextcloud -c nextcloud -- tar xf - -C /var/www/html \
  < /Users/mu/db-dumps/nextcloud-35.0.1-exec/config-pre-35.0.1.tar
kubectl exec -n office deploy/nextcloud -c nextcloud -- grep -E "^ *'version' =>" /var/www/html/config/config.php
#   EXPECT: 'version' => '34.0.4.1',
```

The chart-projected `*.config.php` files are single-file ConfigMap mounts over
the same paths (read-only); `tar` may print "Read-only file system"/"Cannot
open" for exactly those — expected and harmless, the ConfigMap is the source of
truth for them. `config.php` itself is a plain file on the volume and IS restored.

```bash
# (d) git: restore helmrelease.yaml + notify-push.yaml from <bump-sha>^ (NOT `git revert`,
#     which refuses when another session has anything staged in the shared index)
cd /Users/mu/code/cberg-home-nextgen
git fetch origin main && git merge --ff-only origin/main
git log --format='%h %s' "$(cat /Users/mu/db-dumps/nextcloud-35.0.1-exec/bump-sha.txt)^..HEAD" -- \
  kubernetes/apps/office/nextcloud/app/helmrelease.yaml kubernetes/apps/office/nextcloud/app/notify-push.yaml
#   EXPECT: only commit B and (optionally) the §3.6 restore. ANY other subject => STOP, hand-merge
#   with the operator (whole-file restore would silently discard it).
for P in kubernetes/apps/office/nextcloud/app/helmrelease.yaml kubernetes/apps/office/nextcloud/app/notify-push.yaml; do
  git show "$(cat /Users/mu/db-dumps/nextcloud-35.0.1-exec/bump-sha.txt)^:$P" > "$P.rollback-tmp" && mv "$P.rollback-tmp" "$P" || echo "RESTORE FAILED: $P"
done
grep -c '^      tag: 34\.0\.4$' kubernetes/apps/office/nextcloud/app/helmrelease.yaml                    # 1
grep -c '^          image: nextcloud:34\.0\.4$' kubernetes/apps/office/nextcloud/app/helmrelease.yaml     # 1
grep -c '^          image: nextcloud:34\.0\.4$' kubernetes/apps/office/nextcloud/app/notify-push.yaml     # 1
grep -c 'TEMPORARY (plan nextcloud-fleet-35.0.1' kubernetes/apps/office/nextcloud/app/helmrelease.yaml     # 0
grep -c '^      version: 9\.3\.0$' kubernetes/apps/office/nextcloud/app/helmrelease.yaml                 # 1 (chart back to 9.3.0 with the image)
printf '%s\n\nCo-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>\n' \
  "revert(nextcloud): back to 34.0.4 + chart 9.3.0 after DB dump + nextcloud-config snapshot restore (plan nextcloud-fleet-35.0.1 §5.3)" \
  > /Users/mu/db-dumps/nextcloud-35.0.1-exec/msg-rollback.txt
git commit --only kubernetes/apps/office/nextcloud/app/helmrelease.yaml kubernetes/apps/office/nextcloud/app/notify-push.yaml \
  -F /Users/mu/db-dumps/nextcloud-35.0.1-exec/msg-rollback.txt
git show --stat HEAD && git log -1 --format=%s && git push origin main
kubectl -n office patch cronjob nextcloud-cron -p '{"spec":{"suspend":false}}'
flux resume helmrelease -n office nextcloud && flux resume kustomization -n office nextcloud
```

Confirm back: `occ status` = `34.0.4.1`, maintenance false; HelmRelease Ready on
9.3.0 and `helm history` row `nextcloud-9.3.0 34.0.4`; `rows-restored.txt` == `rows-pre.txt`; §4 gates 2, 3 (against
`app-list-pre.json`: identical enabled set incl. context_chat), 4 (`version`
34.0.4.1) and 5 all green.

**5.4 Abandon before Commit B** (after Commit A and/or §3.2b): nothing to revert —
`max-version 35` is valid on 34.0.4 (min 30), and the pre-drained app patches are
ordinary 34-compatible updates. Leave both in place. The ONLY exception is a Mail
that cannot be made green on 34 after §3.2b: then §5.3(a)-(c) (dump + snapshot,
both pre-drain) restores Mail 5.12.2; skip (d) — git never changed.

**Chart leg on its own needs no rollback procedure.** It is metadata-only (§1.2)
and travels with the image in (d). A helm upgrade that FAILS on a chart-specific
error (not seen in the dry-run render) is handled exactly like any Commit B
failure: with `retries: 0` nothing auto-rolls-back; read the HR message, fix
forward or run §5.3.

## 6) Interference notes

- **Slot:** `sun-attended` only (150 min against a schedulable budget of 180;
  operator present for §3.4 and the browser checks). Never `nightly`/`sat-attended`
  (90 min). Nothing else over ~30 min fits beside it on 2026-10-18; it is the only
  plan in that slot today.
- **Office-wide silence (§2.5)**: no other `office` plan in the same slot. The
  declared conflicts: `bitnamilegacy-exit-nextcloud-db`
  (same helmrelease.yaml / same DB), `nextcloud-mcp-0.198.0` (consumer),
  `redis-fleet-8.10.2` (restarts nextcloud-redis + our Deployments),
  `flux-oci-chart-sources` (moves this chart's source, rolls mariadb),
  `flux-reconciler-impersonation` (changes office/nextcloud's reconcile identity),
  `chart-patches-coredns-reloader-blackbox` (reloader + coredns), `flux-fleet-0.60.0` (helm-controller restart),
  `helm-drift-detection` (patches this HelmRelease), and the office-namespace plans hidden by the §2.5 silence:
  `app-template-5.2.1`, `penpot-chart-1.10.0`, `penpot-cache-9.2`, `paperless-db-13.0.2`.
  Added on the 2026-10-05 re-plan: `reloader-2.2.18` + `coredns-1.48.1` (Commit A's
  mechanism / appstore DNS — both already list this plan), `kube-prometheus-stack-91.9.0`
  (§4 gate 4 + the §2.5 silence; it already lists this plan), `talos-linux-1.14.2`
  (node reboots), `longhorn-1.13.0` (snapshots / §5.3 revert), and the
  backup-restore stacking set per house rule 81fdd797 (`mariadb-28.1.1`,
  `jellyfin-12.1`, `n8n-2.39.8`, `nocodb-2026.09.1`, `media-naming-p3`,
  `talos-power-tuning-ab`, `talos-sysfs-power-caps`). Several of these do NOT yet
  list this plan back — the reviewer/sweep must add `nextcloud-fleet-35.0.1` where
  missing (`--validate` checks resolution, not reciprocity).
- **Prometheus is an instrument here (§4 gate 4)**: `kube-prometheus-stack-91.9.0`
  is declared; any further kube-prometheus-stack plan must be added on both sides.
- **Superseded sibling:** `nextcloud-9.4.0` (the chart-only FOLLOW plan) is
  `superseded` by this file; `flux-fleet-0.60.0` still lists it in its
  conflicts — harmless (the file remains), but that ref can be dropped there.
- **Step 0 safe-updates** in the same window must not touch `office/nextcloud*`
  (the deny rule already holds them); if Step 0 auto-reverts a batch mid-§3.4,
  stop and re-read the Kustomization revision before continuing.
- **Consumers see a 503 for the whole maintenance period** (up to ~30 min):
  `ai/openclaw` mail/calendar skills (check no OpenClaw cron is due —
  `feedback_no_openclaw_roll_during_crons`), `office/nextcloud-mcp`, Homepage
  widget, DAV clients on phones (they retry).
- **Three pod rolls**, not one: Commit A (reloader), Commit B (the upgrade + the
  chart), §3.6 (probe restore). Only Commit B migrates; the chart adds no roll of
  its own. §3.2b app updates do NOT roll the pod.
- **Chart lockstep drift:** the moment a chart newer than 9.4.0 is published
  (premise `newest-published-chart-is-still-9.4.0`), this plan must be refreshed
  in place again (keep the `plan_id`) to the newest chart+image pair — per
  operator rule. Same if Docker Hub ships 35.0.2 with no chart: re-plan, do not
  run a pair that is no longer the newest without an explicit decision.
- **Storage safety:** no PVC/PV delete, patch or recreate anywhere; the CIFS
  data PVC is untouched even in §5.3.
