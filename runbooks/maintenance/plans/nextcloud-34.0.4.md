---
plan_id: nextcloud-34.0.4
component: nextcloud
pr: null                              # no Renovate PR — coverage.py direct-bump items
                                      # F-f3e9ddb0 (server) + F-4a9d6631 (notify-push),
                                      # both routed to the PLAN lane by the `*nextcloud*`
                                      # deny rule in runbooks/auto-update-policy.yaml.
                                      # The CHART leg (9.2.6 -> 9.3.0) has NO finding id of
                                      # its own: version-check-current.md line 197 carries
                                      # chart and image in ONE row, and only the image half
                                      # was raised as a finding. Measured 2026-09-20 with
                                      # `policy-cli.py finding list --grep chart`: no
                                      # nextcloud chart row exists. So nothing but this
                                      # plan tracks the chart move — do not assume a
                                      # finding will re-raise it if this plan is dropped.
kind: chart                           # CHANGED 2026-09-20: this is now a chart+image lockstep
                                      # move (house precedent: authentik-pg18-lockstep also
                                      # files a chart+image lockstep as `kind: chart`). The
                                      # three image tags still move — they ride with the chart,
                                      # see §1.1.
current: "34.0.3 (chart 9.2.6, whiteboard backend v1.5.9)"
target: "34.0.4 (chart 9.3.0, whiteboard backend v2.0.0)"
                                      # PROSE ON PURPOSE. lib/plan_matching.py:_ver_tokens()
                                      # tokenizes these two fields, and target_covers() /
                                      # version_pair_match() join held updates to this plan on
                                      # those tokens. The compound form makes all FOUR held
                                      # items (server image, notify-push image, chart, and the
                                      # whiteboard backend) resolve to this plan instead of
                                      # reading as unplanned.
update_type: major                    # HONEST, and it is the whiteboard leg that earns it, not
                                      # the server: server 34.0.3 -> 34.0.4 is a patch and the
                                      # chart hop is a minor, but this plan now also lands
                                      # whiteboard 1.5.9 -> 2.0.0 on BOTH legs (§1.6). A plan is
                                      # classified by its largest leg, never its average.
risk: medium                          # household's primary file/mail/calendar server;
                                      # startup-time `occ upgrade` with a documented
                                      # stuck-maintenance / broken-Mail-app history
                                      # (33.0.0->33.0.4, 2026-06-06). See §1.3 for the
                                      # mechanism and §3.2 for how this plan defuses it.
                                      # NOT raised to high by the whiteboard major: that leg is
                                      # one stateless container (no PVC, no DB, no migration)
                                      # whose revert is one line (§5.4), and the chart half is
                                      # measurably inert (§1.2). The dominant risk is unchanged
                                      # — it is still the entrypoint's occ upgrade.
est_duration_min: 75                  # 45 -> 75 (2026-09-20). Added: the Mail baseline +
                                      # Mail contents gate (~15 min of IMAP round trips across
                                      # 3 accounts, twice), and the whiteboard backend rollout
                                      # + its browser collaboration round-trip (~10 min). Fits
                                      # sun-attended (200 min) with room; does NOT fit
                                      # sat-attended/nightly (90 min) — §6.
needs_reboot: false
touches:
  namespaces: [office]
  resources:
    - helmrelease/nextcloud                     # chart.spec.version 9.2.6 -> 9.3.0 + image.tag
                                                # + worker sidecar tag (+ temporary
                                                # upgrade.remediation.retries 3 -> 0 -> 3)
    - deployment/nextcloud                      # Recreate rollout; entrypoint rsync + occ upgrade
    - deployment/nextcloud-notify-push          # tag moves in the SAME commit (lockstep rule)
    - deployment/nextcloud-whiteboard           # image v1.5.9 -> v2.0.0 in the SAME commit as
                                                # the app leg that §3.2 installs (§1.6)
    - service/nextcloud-whiteboard              # unchanged; read by §4 gate 5
    - httproute/nextcloud-whiteboard            # unchanged; read by §4 gate 5. Route is NOT edited —
                                                # one Pod rolls behind it, so `shared:` stays []
    - secret/nextcloud-config                   # READ ONLY: key `whiteboard-jwt-secret` feeds
                                                # both legs. Not rewritten — the JWT contract is
                                                # unchanged upstream in 2.0.0 (§1.6)
    - cronjob/nextcloud-cron                    # template image re-rendered by the chart, PLUS
                                                # one new rendered key `suspend: false` (§1.2)
    - pvc/nextcloud-config                      # html/ rsynced, custom_apps/ rewritten by app updates
    - statefulset/nextcloud-mariadb             # NOT restarted — receives one-way app migrations
    - deployment/nextcloud-redis                # NOT restarted — clients reconnect; notify_push_* keys rewritten
    - "new: snapshot.longhorn.io/nextcloud-config-pre-34-0-4 + nextcloud-mariadb-pre-34-0-4 (ns storage)"
  shared: []                                    # own Longhorn volumes only; gateway/envoy,
                                                # cert-manager, cilium, coredns untouched.
                                                # The whiteboard IS on the public edge, but this
                                                # plan rolls a Pod BEHIND an unmodified
                                                # HTTPRoute/Gateway — so no gateway/envoy entry.
                                                # Cross-namespace CONSUMERS (ai/openclaw mail +
                                                # calendar skills, office/nextcloud-mcp,
                                                # Homepage widget) see a 2-5 min 503 — §6.
depends_on: []
conflicts_with:
  - bitnamilegacy-exit-nextcloud-db             # same helmrelease.yaml, both restart
                                                # deployment/nextcloud. That plan is `blocked`
                                                # with window: null, so no live collision
                                                # today — the guard is for when it revives.
                                                # RECIPROCITY (2026-09-15 review): the ref was
                                                # added on THAT plan too — maintenance-plan.py
                                                # --validate checks only that refs resolve,
                                                # not that both sides declare them.
  - nextcloud-mcp-0.187.1                       # ADDED 2026-09-15 (review), reciprocal of that
                                                # plan's declaration: its §4.4 talks to THIS
                                                # server and the §2.5 silence here is
                                                # namespace-wide. Never the same slot; different
                                                # slots of one weekend in either order are fine
                                                # (its server premise tolerates 34.0.x and it
                                                # re-takes its baselines the same day). §6.
                                                # NOT listed: nextcloud-whiteboard-2.0.0. It is
                                                # SUPERSEDED by this plan (§1.6), not a conflict,
                                                # and the operator is retiring the file. A ref to
                                                # a deleted plan is a --validate ERROR, so this
                                                # plan deliberately names it in prose only.
security_ref: F-ab9e243a              # security driver for the SERVER image bump. What it is and
                                      # why this tag answers it live on the record only —
                                      # never counts, IDs or vocabulary here (public repo).
                                      # The whiteboard leg has its own OPEN security row
                                      # (F-6c461103) — carried in finding_refs, not here:
                                      # render-board.py:84 hides a planned finding on an EXACT
                                      # security_ref match, and this field holds exactly one id.
capability_change: true               # the SERVER patch changes no capability, but `occ
                                      # upgrade` drags every pending appstore update along
                                      # (Updater.php:244) — Mail 5.10 -> 5.12 is two minor
                                      # lines with user-visible features, plus Talk, Calendar,
                                      # Contacts, CODE. And whiteboard 2.0.0 is a MAJOR on both
                                      # legs (Vue 3 front end; a backend room-authorization gate
                                      # that can refuse a socket join v1.5.9 accepted).
                                      # Honest answer: users will see changes.
rollback_class: backup-restore        # a git revert is NOT a rollback once `occ upgrade`
                                      # ran: the entrypoint refuses to start an older image
                                      # on newer data (§5.3). Rollback = DB dump restore +
                                      # Longhorn snapshot revert of nextcloud-config. No
                                      # backup_gate named => human-gated, which the deny rule
                                      # demands anyway ("operator-supervised only").
                                      # The whiteboard BACKEND leg alone is a true one-line
                                      # git-revert (§5.4) — the weakest class wins the field.
finding_refs: [F-f3e9ddb0, F-4a9d6631, F-ab9e243a, F-53ba35b1, F-6c461103]
                                      # F-53ba35b1 (version/critical, whiteboard v1.5.9 ->
                                      # v2.0.0) and F-6c461103 (security/critical, whiteboard)
                                      # ADDED 2026-09-20: this plan now delivers that bump, so
                                      # it must carry the ownership claim finding-triage.py:230
                                      # joins on. Both were re-measured open/unchanged
                                      # (last_seen 2026-09-19) before being claimed.
status: vetted   # RE-VETTED 2026-09-20 after the B1/B2 rewrite. Independent reviewer ran every gate read-only against the live cluster: verdict ready-for-go, every_gate_can_fail=true, mail_gate_is_real=true, whiteboard_both_legs_covered=true, gates_still_vacuous=NONE, blocking_issues=NONE, 18 premises PASS. NOT YET SCHEDULED: HUMAN-GATED (capability_change), needs an attended slot and a fresh operator GO.
window: "sun-attended:2026-10-04"   # SLOTTED 2026-09-20 after the B1/B2 rewrite was reviewed ready-for-go. Capacity: 75 of 200 min, risk 2 of 6, slot otherwise EMPTY. Deliberately NOT sun-attended:2026-10-11 - that holds jellyfin-12.1, and jellyfin (high, backup-restore, capability_change) plus this plan (major, backup-restore, capability_change) is two backup-restore rollbacks in one window, the same no-rollback-capacity stacking the reconciler already rejected for jellyfin+frigate. Not 09-26/10-03/10-10 either: 45/20/45 min free, 75 does not fit. Not 09-27: talos-1.14.0 needs that whole slot. HUMAN-GATED - still requires an operator GO before it runs.
                                      # sun-attended). Never `nightly`: the executor must
                                      # watch the entrypoint log during §3.4 and be able to
                                      # run the §5.1 recovery inside the same slot.
premises:
  # Runner grammar (plan-premises.py): kubectl/flux/git/helm/talosctl READ verbs + the
  # ALLOWED_BARE text filters only — no exec, no curl, no python, no `$( )`/`;`. Everything
  # occ-derived (status, app set, notify_push self-test, the whiteboard APP version) is
  # therefore an EXECUTOR gate in §2.0b, run by hand and abort-on-mismatch, not a premise.
  # `helm` IS in the allowlist, which is what lets the chart-index premise below exist —
  # but run the premises FROM THE REPO ROOT: helm is a mise shim and resolves its version
  # from the repo's .mise.toml. Outside the repo the shim errors "No version is set",
  # which the runner correctly reports as a FAILURE, not a skip.
  # Every value below was re-measured live on 2026-09-20.
  - id: live-server-image-is-still-34.0.3-on-both-containers
    why: >-
      `current:` claims 34.0.3 on the main container AND the worker sidecar. If either
      already moved (a hand bump, a later coverage run), the §3.3 sed is partial or a
      no-op and the §4 baseline (34.0.3.2) is wrong.
    run: kubectl get deploy -n office nextcloud -o jsonpath='{.spec.template.spec.containers[?(@.name=="nextcloud")].image} {.spec.template.spec.containers[?(@.name=="worker")].image}'
    expect_exact: "docker.io/nextcloud:34.0.3 nextcloud:34.0.3"
  - id: notify-push-image-is-still-34.0.3
    why: >-
      notify-push runs the same image tag by rule (its manifest comment: "moves in the
      SAME commit as the server tag"; a lag was the sole driver of a security finding
      closed 2026-07-31). If it already differs, the lockstep edit in §3.3 must be
      re-derived rather than applied blind.
    run: kubectl get deploy -n office nextcloud-notify-push -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: nextcloud:34.0.3
  - id: git-pins-are-still-34.0.3
    why: >-
      §3.3 edits three 34.0.3 lines: `tag: 34.0.3`, the worker `image: nextcloud:34.0.3`
      (helmrelease.yaml) and `image: nextcloud:34.0.3` (notify-push.yaml). If the pins
      already differ the seds are no-ops and the commit is empty. The COUNT is the
      assertion, not the presence.
    run: >-
      git show HEAD:kubernetes/apps/office/nextcloud/app/helmrelease.yaml HEAD:kubernetes/apps/office/nextcloud/app/notify-push.yaml
      | grep -c '34\.0\.3$'
    expect_exact: "3"
  - id: our-chart-pin-is-still-9.2.6
    why: >-
      §3.3 rewrites the single line `version: 9.2.6` in helmrelease.yaml to 9.3.0. If our
      pin already moved, that sed is a no-op and the §1.2 inertness analysis (measured
      9.2.6 -> 9.3.0) describes a diff nobody is applying. This is the SOURCE end of the
      lockstep; the premise below is the TARGET end.
    run: kubectl get helmrelease -n office nextcloud -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: "9.2.6"
  - id: chart-9.3.0-still-carries-appversion-34.0.4
    why: >-
      THE PREMISE THIS PLAN WAS SENT BACK FOR (F-0cd73f3f). The whole lockstep argument is
      "chart 9.3.0 is the chart that carries our target image version". The previous
      revision could not check this — its only chart premise read OUR pin, so it passed
      12/12 while upstream had already invalidated the plan's central claim, and the halt
      only tripped by hand mid-window. This reads the PUBLISHED INDEX, mechanically, at
      preflight. It does NOT assert 9.3.0 is still the newest chart — that is deliberately
      an executor gate (§2.0b), because "newest" drifts and "9.3.0 carries 34.0.4" does not.
    run: "helm show chart nextcloud --repo https://nextcloud.github.io/helm --version 9.3.0 | grep -E '^appVersion'"
    expect_exact: "appVersion: 34.0.4"
  - id: helmrelease-is-ready-and-not-mid-upgrade
    why: >-
      Starting a helm upgrade on top of an in-flight or failed one is how Flux
      remediation thrash begins (application-update SOP §7). Ready=True is the only
      state this plan starts from.
    run: kubectl get helmrelease -n office nextcloud -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: server-deployment-has-one-ready-replica
    why: >-
      A pod that is not Ready right now is either mid-restart or already stuck in
      maintenance mode — either way the §2.0b occ gates cannot be trusted and the
      2026-06-06 failure would be started from, not avoided.
    run: kubectl get deploy -n office nextcloud -o jsonpath='{.status.readyReplicas}'
    expect_exact: "1"
  - id: redis-is-the-standalone-deployment-outside-the-helmrelease
    why: >-
      §1.5's claim "this bump does NOT restart nextcloud-redis" rests on redis being a
      plain Kustomize Deployment with no spec change in this plan. If it were folded
      back into the chart, a helm upgrade could roll it and sign every user out — the
      `*nextcloud-redis*` deny rule's whole concern. Note this matters MORE now that the
      chart version itself moves: a chart bump is exactly the event that could re-enable
      a bundled subchart.
    run: kubectl get deploy -n office nextcloud-redis -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_contains: "redis:8."
  - id: mariadb-is-still-the-bundled-statefulset-with-a-password-file
    why: >-
      §2.3 dump and §5.3 restore exec into `nextcloud-mariadb-0` and read
      `$MARIADB_ROOT_PASSWORD_FILE` (bitnami layout). If bitnamilegacy-exit-nextcloud-db
      has since replatformed the DB, those commands target the wrong server or fail closed.
    run: kubectl get sts -n office nextcloud-mariadb -o jsonpath='{.spec.template.spec.containers[0].env[*].name}'
    expect_contains: MARIADB_ROOT_PASSWORD_FILE
  - id: newest-longhorn-backup-of-nextcloud-mariadb-is-completed
    why: >-
      The durable rollback floor under §5.3 is the nightly 03:00 Longhorn backup. A
      newest backup in any state but Completed means the floor is missing; its AGE is
      read by the executor in §2.1 (the runner cannot do date math).
    run: kubectl get backups.longhorn.io -n storage -l backup-volume=nextcloud-mariadb --sort-by=.status.snapshotCreatedAt -o jsonpath='{.items[-1].status.state}'
    expect_exact: Completed
  - id: newest-longhorn-backup-of-nextcloud-config-is-completed
    why: >-
      Same floor for the code/custom_apps/config volume that §3.2 and the entrypoint
      rewrite; the §2.4 snapshot is same-day only.
    run: kubectl get backups.longhorn.io -n storage -l backup-volume=nextcloud-config --sort-by=.status.snapshotCreatedAt -o jsonpath='{.items[-1].status.state}'
    expect_exact: Completed
  - id: startup-probe-budget-is-unchanged
    why: >-
      §1.3's timing math (kubelet kills the container 60 s + 10 x 30 s = 360 s after start
      if status.php never answers) and the decision to drain the appstore pass FIRST (§3.2)
      both rest on these two numbers. A changed probe changes the risk shape.
    run: kubectl get deploy -n office nextcloud -o jsonpath='{.spec.template.spec.containers[?(@.name=="nextcloud")].startupProbe.failureThreshold} {.spec.template.spec.containers[?(@.name=="nextcloud")].startupProbe.periodSeconds}'
    expect_exact: "10 30"
  - id: flux-remediation-retries-is-3
    why: >-
      §3.3 flips `upgrade.remediation.retries` 3 -> 0 for the attempt and §3.6 restores
      3. If it is already something else, both edits need re-deriving.
    run: kubectl get helmrelease -n office nextcloud -o jsonpath='{.spec.upgrade.remediation.retries}'
    expect_exact: "3"
  # ===== whiteboard backend leg (absorbed from nextcloud-whiteboard-2.0.0, §1.6) =====
  # NB: never write a bare triple-dash marker inside this frontmatter, not even inside
  # a comment. maintenance-plan.py load_plans() extracts frontmatter with a naive
  # text.split(marker, 2)[1], so the FIRST one ends the block: every premise below it,
  # and sops_refs with them, is silently dropped while --validate still prints
  # "all plan frontmatter invariants hold". Caught here twice while writing this file.
  - id: whiteboard-backend-is-still-v1.5.9
    why: >-
      `current:` claims v1.5.9 on the live collaboration backend. If it already moved (a
      hand bump, a Step 0 direct-bump, a partial earlier run) the §3.3 sed is a no-op and
      the §4 gate 5a digest baseline is wrong. This is the plan's central factual claim about
      the backend leg.
    run: kubectl get deploy -n office nextcloud-whiteboard -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "ghcr.io/nextcloud-releases/whiteboard:v1.5.9"
  - id: whiteboard-git-pin-is-still-v1.5.9-and-there-is-exactly-one
    why: >-
      §3.3 edits exactly one line in whiteboard-proxy.yaml. If a SECOND pin had appeared
      the edit would be partial. The COUNT is the assertion. (The string v1.5.9 also
      appears in three files under runbooks/tests/ — those are parser FIXTURES, not pins,
      and must never be edited by this plan.)
    run: "git show HEAD:kubernetes/apps/office/nextcloud/app/whiteboard-proxy.yaml | grep -c 'whiteboard:v1\\.5\\.9'"
    expect_exact: "1"
  - id: whiteboard-deployment-has-one-ready-replica
    why: >-
      A backend that is not Ready right now is already broken, and this bump would be
      blamed for it. One Ready replica is the only state this leg starts from, and it is
      also the §4 gate 5 baseline.
    run: kubectl get deploy -n office nextcloud-whiteboard -o jsonpath='{.status.readyReplicas}'
    expect_exact: "1"
  - id: whiteboard-jwt-secret-still-sourced-from-nextcloud-config
    why: >-
      The single shared secret is the whole coupling between the two legs (§1.6). The
      claim "no secret work is required" rests on the wiring being unchanged: env
      JWT_SECRET_KEY <- secret/nextcloud-config key whiteboard-jwt-secret. If that moved,
      the upstream analysis still holds but this plan's "no secret work" claim does not.
    run: kubectl get deploy -n office nextcloud-whiteboard -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="JWT_SECRET_KEY")].valueFrom.secretKeyRef.name}'
    expect_exact: "nextcloud-config"
  - id: whiteboard-route-still-points-at-this-service
    why: >-
      §4 gate 5d exercises the public whiteboard hostname through the envoy-external Gateway and
      asserts it reaches THIS backend. If the HTTPRoute were re-pointed, that gate would be
      measuring something else and could pass while this service is dead.
    run: kubectl get httproute -n office nextcloud-whiteboard -o jsonpath='{.spec.rules[0].backendRefs[0].name}'
    expect_exact: "nextcloud-whiteboard"
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/backup.md
  - docs/sops/disaster-recovery.md
  - docs/sops/longhorn.md
  - docs/sops/maintenance-windows.md
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/vulnerability-disclosure.md
generated: "2026-09-20"               # REWRITTEN 2026-09-20 against operator decisions B1
                                      # (chart to the newest, 9.3.0, in lockstep with the
                                      # image) and B2 (whiteboard 2.0.0 accepted, both legs).
                                      # Every fact below was re-measured the same day.
---

# nextcloud 34.0.3 -> 34.0.4, chart 9.2.6 -> 9.3.0, whiteboard backend v1.5.9 -> v2.0.0 (one commit)

## 1) Summary & why held

### 1.1 What moves

**Five lines, three files, one commit.**

| File | Line / key | From | To |
|---|---|---|---|
| `kubernetes/apps/office/nextcloud/app/helmrelease.yaml` | `spec.chart.spec.version` | `9.2.6` | `9.3.0` |
| same | `values.image.tag` | `34.0.3` | `34.0.4` |
| same | `extraSidecarContainers[worker].image` | `nextcloud:34.0.3` | `nextcloud:34.0.4` |
| `kubernetes/apps/office/nextcloud/app/notify-push.yaml` | `image` | `nextcloud:34.0.3` | `nextcloud:34.0.4` |
| `kubernetes/apps/office/nextcloud/app/whiteboard-proxy.yaml` | `image` (line 25) | `ghcr.io/nextcloud-releases/whiteboard:v1.5.9` | `…:v2.0.0` |

The chart re-renders `cronjob/nextcloud-cron` with the new tag and one new key
on its own (§1.2). `metrics`, `mariadb` and `redis` specs do not change and do
not restart.

Both server coverage items (`nextcloud` F-f3e9ddb0 and `nextcloud-notify-push`
F-4a9d6631) are the same tag on the same image and are answered by this one
plan; notify-push runs the `notify_push` binary from the shared `custom_apps/`
PVC and only borrows the image for its runtime, so its tag must equal the
server's (the manifest says so, and a lag was a closed security finding on
2026-07-31). The whiteboard items (F-53ba35b1, F-6c461103) are answered here
too — see §1.6.

### 1.2 The chart DOES move in lockstep now — and 9.3.0 is measurably inert

The previous revision of this plan concluded *"there is no chart carrying
34.0.4 to move to"*. **That is stale and this section replaces it.** Measured
against the published index on **2026-09-20**:

| Chart | appVersion | Published |
|---|---|---|
| **9.3.0** | **34.0.4** | 2026-09-19T15:49:20Z |
| 9.2.7 | 34.0.4 | 2026-09-19T15:42:59Z |
| 9.2.6 (ours) | 34.0.3 | 2026-08-17T20:02:54Z |

So the `*nextcloud*` deny rule's *"chart+image must bump together"* clause now
has a target, and **the operator chose the newest: 9.3.0** (decision B1,
2026-09-20). The chart and the image move in the same commit.

**What 9.3.0 actually changes — measured from both tarballs, not from notes.**
`diff -rq` over the two unpacked charts reports four differing files, of which
`README.md` is documentation:

- `Chart.yaml`: `appVersion: 34.0.3 -> 34.0.4`, `version: 9.2.6 -> 9.3.0`.
- `values.yaml`: **exactly two lines added** — a comment and a new
  `cronjob.suspend: false` key.
- `templates/cronjob.yaml`: **one line added** — `suspend: {{ .suspend }}`.
- No other template, no `_helpers.tpl`, no subchart, no new required value.

**Rendered against our LIVE values** (`helm get values -n office nextcloud`,
then `helm template` on each chart) the entire 9.2.6 -> 9.3.0 delta is **29
changed lines**: 7 x `helm.sh/chart` label, 7 x `app.kubernetes.io/version`
label (14 old + 14 new) **and one added line**:

```
1259a1260
>   suspend: false
```

Three consequences worth stating, because each one is a trap avoided:

1. **It renders as a real `false`, not empty.** Our values override the
   `cronjob:` map but not `cronjob.suspend`, and Helm merges maps — so the
   chart default `false` survives into the render. A `suspend:` with an empty
   value would be a YAML `null`, which is *not* what happens here (verified in
   the rendered output above).
2. **It is a no-op on the live object.** `cronjob/nextcloud-cron` already reads
   `suspend=false` (measured 2026-09-20), so the new key asserts the state the
   CronJob is already in.
3. **The chart bump alone moves NO image.** Diffing just the `image:` lines of
   the two renders shows them byte-identical — every image in the render still
   comes from our pinned values. This is the proof that the chart half cannot
   silently drag a version along: the image moves **only** because §3.3 edits
   `tag:` by hand. (It is also why a chart-only bump would have been inert and
   a lie — the appVersion is a default this HelmRelease never uses.)

**The hold is still correct**, for the second half of the deny rule's sentence:
the image bump runs `occ upgrade` on pod start, and that is where the Mail /
stuck-maintenance trap lives (§1.3). `risk: medium`, attended — not a false
positive.

### 1.3 Why an image PATCH is migration-bearing here (the mechanism, with evidence)

The official image's `/entrypoint.sh` (read from the running 34.0.3 pod):

- line 189: `if version_greater "$image_version" "$installed_version"` → rsyncs
  `/usr/src/nextcloud/` over `/var/www/html/` (PVC `nextcloud-config`, RWX,
  ~730 MB in `core/`+`apps/`), then
- line 294: `run_as 'php /var/www/html/occ upgrade'`.

`occ upgrade` is `OC\Updater::doUpgrade()`. At **`lib/private/Updater.php:244`**
(same pod):

```php
// upgrade appstore apps
$this->upgradeAppStoreApps($this->appManager->getEnabledApps());
```

which for every **enabled** app calls `isUpdateAvailable()` →
`updateAppstoreApp()` — i.e. **a server patch bump downloads and installs every
pending appstore update, inside the container's startup path.**
`appstoreenabled` is unset here (default `true`), so this pass is live.

**The pending set, re-measured live 2026-09-20 — 13 updates, not the 12 the
previous revision listed.** Pod runs PHP **8.5.9**.

| App | From → To | Enabled? | Note |
|---|---|---|---|
| `mail` | 5.10.12 → **5.12.0** | enabled | TWO minor lines, not one. Own DB migrations. The operator's hard requirement (§4 gate 2) |
| `richdocumentscode` | 26.4.104 → **26.4.303** | enabled | the built-in CODE AppImage — by far the largest download, and a large Collabora jump |
| `spreed` (Talk) | 24.0.4 → 24.0.5 | enabled | patch |
| `contacts` | 8.7.6 → **8.9.0** | enabled | two minor lines |
| `calendar` | 6.5.3 → 6.5.4 | enabled | patch |
| `richdocuments` | 11.1.0 → 11.1.1 | enabled | patch |
| `whiteboard` | 1.5.9 → **2.0.0** | enabled | **MAJOR — the app leg of §1.6** |
| `notify_push` | 1.4.0 → 1.4.1 | enabled | adds pgsql_ssl config support only |
| `drawio` | 4.3.5 → 4.3.9 | enabled | patch |
| `guests` | 4.9.0 → 4.10.0 | enabled | minor |
| `integration_paperless` | 1.0.13 → 1.0.14 | enabled | patch |
| `agenda_bot` | 1.6.0 → 1.7.0 | **disabled** | outside `occ upgrade`'s enabled-apps pass; `app:update --all` still moves it |
| `files_3dmodelviewer` | 0.0.16 → 0.0.18 | **disabled** | same |

**11 enabled + 2 disabled = 13.** (The previous revision said "10 enabled + 2
disabled", and named mail 5.11.5 and contacts 8.8.1 — all three figures were
stale by five days.) 68 apps enabled, 9 disabled overall.

Now the timer. The chart's startupProbe is `initialDelaySeconds: 60`,
`periodSeconds: 30`, `failureThreshold: 10`: **the kubelet kills the container
360 s after start if `status.php` has not answered.** Measured on the last
plain restart (2026-09-07, no upgrade): container start → Ready = **86 s**, so
the rsync alone is fine. What is *not* budgeted is thirteen appstore downloads
+ extractions onto an NFS-backed RWX volume inside `occ upgrade`. That is the
2026-06-06 incident in one sentence: *the probe restarted the pod mid-`occ
upgrade`; Mail's `vendor/` came out half-extracted, every `occ` and every cron
pod then failed on autoload, and maintenance mode stayed on*
(`project_nextcloud_upgrade_mailapp`).

**Defusal (§3.2):** run the appstore pass *first*, in the foreground of the
healthy pod, where there is no probe timer and each app prints its own result.
Then the image bump's `occ upgrade` has nothing left to download and finishes
in seconds. The remaining risk is the ordinary one (core migration on a
patch), and 34.0.4's notes carry no schema change.

### 1.4 Upstream 34.0.4 — what the release actually contains

Released 2026-09-10 (`nextcloud-releases/server` v34.0.4); Hub tag published
2026-09-12, multi-arch (re-verified present + amd64 on 2026-09-20). ~70 server
PRs, all fixes; relevant lines verbatim:

- `[Master] fix(security): Update code signing revocation list` — **five**
  times (#63358, #63364, #63370, #63521, #64097). This is the security
  content; the image-level driver is cited as `security_ref`.
- `Fix one core migration: Only add taskprocessing columns if they don't exist
  (#63404)` — makes an *existing* migration idempotent; already-applied rows in
  `oc_migrations` are not re-run.
- `Feat(updater): clear app_install_overwrite on major upgrades (#63633)` —
  **major** upgrades only; inert on 34.0.3→34.0.4.
- `Fix: don't rely on constraint for filecache_extended "upsert" when in
  transaction (#63985)`, `Fix(jobs): don't overwrite the --stop_after baseline
  in background-job:worker (#63328)` — the latter touches the exact command our
  worker sidecar loops on; behaviour fix, no config change.
- `Fix(iMIP): Prevent mails from carrying an unrelated user's name (#63310)`,
  `Fix: Check rememberme cookie previous session id matches uid (#63719)`,
  `Fix(2fa): Add missing BruteForceProtection attribute (#63732)`.
- Bundled apps: `app_api` "make db migrations idempotent", `activity`,
  `circles`, `files_pdfviewer`, `notifications`, `photos`, `text`, `viewer` —
  fixes only.
- **No PHP requirement change, no config key rename, no breaking change, no new
  schema migration.**

### 1.5 The two datastores — explicit verdicts

- **`nextcloud-redis` is NOT restarted.** It is a plain Kustomize Deployment
  (`redis-deployment.yaml`, `redis:8.10.1-alpine`) outside the HelmRelease with
  no spec change in this plan — and the chart's own redis subchart stays
  `enabled: false`, which the chart bump does not alter (§1.2: no subchart
  changed). The main pod's Recreate drops its client connections and they
  reconnect. Logins survive: PHP sessions live under `PHPREDIS_SESSION:*`
  (13 live keys of 972 measured), outside the Nextcloud instance prefix that
  any cache clear would touch. Users see a 503 for the 2-5 min of maintenance,
  not a sign-out. The `*nextcloud-redis*` deny rule is therefore not engaged.
- **`nextcloud-mariadb` is NOT restarted**, but it *is* written: the appstore
  app migrations (Mail 5.10 → 5.12 above all) are one-way. That, plus the
  entrypoint's refusal to start an older image on newer data (§5.3), is why
  `rollback_class: backup-restore` and why §2.3-2.4 take a dump and a snapshot
  before anything moves.

### 1.6 The whiteboard coupling — TWO legs, one commit (operator decision B2)

Whiteboard 2.0.0 is accepted (operator, 2026-09-20). It has **two legs, in
different places**, and the point of this section is that they are one change:

| Leg | Where it lives | Who moves it | Live today |
|---|---|---|---|
| **APP** `whiteboard` 1.5.9 → **2.0.0** | Nextcloud appstore → `custom_apps/whiteboard` on `pvc/nextcloud-config` + the DB. **In no git repo.** | `occ app:update --all` in **§3.2 of this plan** | app `1.5.9`, update offered |
| **BACKEND** `nextcloud-whiteboard` v1.5.9 → **v2.0.0** | `whiteboard-proxy.yaml` **line 25** | **§3.3 of this plan** | Deployment 1/1, internet-facing via HTTPRoute on `envoy-external` |

The genuinely major half is the **app** (Vue 3, a new minimum platform). The
backend change is small and was measured from both tarballs by the plan this
one supersedes: a new room-authorization gate in `RoomLifecycleService.joinRoom()`
that can refuse a socket join v1.5.9 accepted, `ServerService.start()` becoming
async, creator-attribution on broadcast payloads, and a Node base bump.

**Both legs share exactly one secret** — `whiteboard-jwt-secret` in
`kubernetes/apps/office/nextcloud/app/secrets.sops.yaml`, reaching the backend
as `JWT_SECRET_KEY` and the app as `jwt_secret_key` (the worker sidecar syncs
it every 300 s). **v2.0.0 introduces no new required env var and the JWT claim
shape is byte-identical**, so there is **no secret work in this plan**. The
premise `whiteboard-jwt-secret-still-sourced-from-nextcloud-config` pins our
half of that contract.

**Why they must land together.** §3.2 moves the app whether or not anyone plans
it — `occ app:update --all` has no way to skip one app, and the operator's
general policy is that app updates are always acceptable. So the only choice is
whether the backend follows in the same commit or days later. It follows in the
same commit.

> **Interim skew between §3.2 and §3.4 is expected and benign.** For the few
> minutes between the app update and the backend rollout the live state is
> **app 2.0.0 / backend 1.5.9** — the old backend simply lacks the new room
> gate and the creator-metadata protection, and the JWT it verifies is
> unchanged. That is the most common configuration in the wild and the benign
> direction. Do not treat it as a fault mid-run.

**`nextcloud-whiteboard-2.0.0` is SUPERSEDED by this plan.** That file owns the
backend leg today and declares `depends_on: [nextcloud-34.0.4]`; its §1.5
measured the skew analysis quoted above and concluded the correct end state is
both legs on 2.0.0. This plan now delivers both, carries its two findings
(F-53ba35b1, F-6c461103) in `finding_refs`, and absorbs its verification into
§4 gate 5. **The operator is retiring that file** — this plan does not edit it, and
deliberately does NOT name it in `conflicts_with`/`depends_on`, because a ref
to a deleted plan is a `--validate` ERROR.

> One consequence to expect until that file is deleted: `match_held_to_plan()`
> resolves the whiteboard held-bump to a plan by VERSION TOKENS (no name key
> relates `whiteboard` to component `nextcloud`), and both plans now carry
> v1.5.9/v2.0.0 in their `current`/`target`. The matcher will report the pair
> as **ambiguous** rather than silently picking. That is the designed
> behaviour, it is not an error to chase, and it disappears with the retirement.

### 1.7 Mail — the pre-existing condition you must know BEFORE reading §4 gate 2

The operator's hard requirement is *"make sure the email app works correctly"*.
Two measured facts shape how that is checked, and getting either wrong causes a
healthy upgrade to be rolled back:

1. **`occ mail:account:list` DOES NOT EXIST.** Verified on the live pod
   (`occ list mail`, Mail 5.10.12): the namespace offers `create`, `debug`,
   `delete`, `diagnose`, `export`, `export-threads`, `sync`, `train`, `update`
   — and no `list`. A gate built on it errors out and proves nothing. Accounts
   are therefore enumerated by **probing `mail:account:diagnose 1..10`**, and
   cross-checked against the DB. Live answer, 2026-09-20: **three accounts, ids
   1, 2, 3** (`select id from oc_mail_accounts` agrees; `oc_mail_accounts=3`).
   Do not hard-code "two".
2. **Account 3 (Gmail) ALREADY FAILS `mail:account:diagnose` — before this
   upgrade, and reproducibly.** It prints its IMAP capabilities, then exits **2**
   with `Horde error occurred: The object could not be deleted because it does
   not exist.` (`Could not get account statistics` in `nextcloud.log`). Measured
   3/3 on retry on 2026-09-20, and present in the aborted 2026-09-15 baseline
   too. **This is filed as `F-85ee12b0` and is NOT caused by this plan.** Its
   mailboxes are intact — `mail:mailbox:list 3` returns 14 rows. An executor who
   does not know this will read it as a regression and roll back a healthy
   upgrade.

Hence §4 gate 2 asserts **per-account behaviour is UNCHANGED**, not
"all accounts succeed". Account 2 is iCloud (`XAPPLEPUSHSERVICE`,
`X-APPLE-REMOTE-LINKS` in its capabilities) and is separately known for
**intermittent, benign, self-healing STATUS IMAP errors**
(`project_nextcloud_mail_account_quirks`) — those are not auth failures and
must not fail the gate.

There is also a custom app **`openclaw_mail` 0.1.0** (enabled). It is NOT an
appstore app: it is re-materialized into `custom_apps/openclaw_mail` by the
`install-openclaw-mail` initContainer on **every** pod boot, from the
`nextcloud-openclaw-mail-app` ConfigMap, and re-enabled by the worker sidecar.
A Recreate rollout re-runs both, so it should survive — §4 asserts it did.

## 2) Pre-checks

Run from the repo root on the Mac mini. Everything here is read-only except the
dump/snapshot artefacts.

**Baseline directory — `/Users/mu/db-dumps/nextcloud-34.0.4-exec/`, written
with TRUNCATING redirects only.** Every path in this plan is absolute and
literal on purpose: each tool call is a fresh shell, so a `B=…` set in §2 is
**gone** by §5 — and an unset variable in the §5.3 restore leg would read the
dump from an empty path. There are no cross-step shell variables in this plan.

> **Do NOT write into `/Users/mu/db-dumps/nextcloud-34.0.4/`.** That directory
> holds the **aborted 2026-09-15 run** (including a 718 MB dump of that day's
> DB). The previous revision appended with `tee -a` into it, so its
> `mail-diagnose-pre.txt` already contains a doubled account-3 retry — a gate
> comparing against it would be comparing against stale, duplicated data. Leave
> it for reference; this run uses the `-exec` directory and truncating writes.

```bash
cd /Users/mu/code/cberg-home-nextgen
# fresh by construction: if an earlier attempt left one, move it aside rather than merge
[ -d /Users/mu/db-dumps/nextcloud-34.0.4-exec ] && \
  mv /Users/mu/db-dumps/nextcloud-34.0.4-exec \
     "/Users/mu/db-dumps/nextcloud-34.0.4-exec.superseded-$(date +%Y%m%d%H%M%S)"
umask 077 && mkdir -p /Users/mu/db-dumps/nextcloud-34.0.4-exec
chmod 700 /Users/mu/db-dumps/nextcloud-34.0.4-exec
ls -ld /Users/mu/db-dumps/nextcloud-34.0.4-exec     # HOW IT FAILS: not drwx------ => stop, artefacts would be world-readable
```

**2.0 Premises — every one must PASS.** Run from the repo root (the chart-index
premise uses `helm`, a mise shim that resolves its version from `.mise.toml`).

```bash
cd /Users/mu/code/cberg-home-nextgen
.venv/bin/python3 runbooks/plan-premises.py nextcloud-34.0.4 --require-premises
```

HOW IT FAILS: any premise reporting FAIL — including one whose command errored
or returned nothing (the runner fails closed) — aborts the plan. Do not
"interpret" a failure; re-derive the section it names.

**2.0b The gates the premise runner cannot express** (they need `curl` or
`occ`). **ABORT on any mismatch.**

```bash
# (a) the target image tag is published and multi-arch (application-update SOP Step 0)
curl -s "https://hub.docker.com/v2/repositories/library/nextcloud/tags/34.0.4" \
  | grep -oE '"name":"34\.0\.4"|"architecture":"amd64"' | sort -u | tr '\n' ' '; echo
#   EXPECT: "architecture":"amd64" "name":"34.0.4"
#   HOW IT FAILS: either token missing => the tag was pulled or was never multi-arch. STOP —
#   never bump to an unpublished tag. (An empty line also fails: it means the API call itself
#   failed, which is indistinguishable from "no such tag" and must be treated as the worse one.)

# (b) 9.3.0 is still the NEWEST chart — the halt that sent this plan back (F-0cd73f3f)
curl -s https://nextcloud.github.io/helm/index.yaml | /Users/mu/code/cberg-home-nextgen/.venv/bin/python3 -c "
import sys, yaml
e = yaml.safe_load(sys.stdin)['entries']['nextcloud']
newest = e[0]
print('newest:', newest['version'], 'appVersion', newest['appVersion'])
print('9.3.0 present:', any(x['version'] == '9.3.0' for x in e))
print('newer-than-9.3.0 charts:', [x['version'] for x in e if x['version'] not in ('9.3.0','9.2.7','9.2.6')][:5])
"
#   EXPECT (2026-09-20): newest: 9.3.0 appVersion 34.0.4 / 9.3.0 present: True
#   HOW IT FAILS: "9.3.0 present: False" => the operator's chosen target was unpublished. STOP.
#   If `newest` is something ABOVE 9.3.0, this is the SAME class of drift that sent the plan
#   back: the premise chart-9.3.0-still-carries-appversion-34.0.4 will still PASS, because it
#   asks a different (deliberately drift-stable) question. Decide DELIBERATELY whether to
#   re-target — it is an operator call, never a silent absorb. The plan as written targets
#   9.3.0 exactly, and §1.2's inertness analysis was measured on 9.3.0 alone.

# (c) the instance is healthy and where we think it is
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ status"
#   EXPECT: installed true / version 34.0.3.2 / maintenance false / needsDbUpgrade false
#   HOW IT FAILS: maintenance:true or needsDbUpgrade:true => the instance is already mid-upgrade
#   or stuck. STOP — §5.1 comes BEFORE this plan, not after it.

# (d) the apps this plan makes promises about are present at the versions it claims
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ app:list --output=json" \
  | /Users/mu/code/cberg-home-nextgen/.venv/bin/python3 -c "
import sys, json
d = json.load(sys.stdin); en = d['enabled']
for a in ('mail','openclaw_mail','notify_push','google_synchronization','whiteboard','richdocuments','richdocumentscode'):
    print(f'{a:<24}', en.get(a))
print('counts: enabled', len(en), 'disabled', len(d['disabled']))
"
#   EXPECT (2026-09-20): mail 5.10.12 / openclaw_mail 0.1.0 / notify_push 1.4.0 /
#   google_synchronization 4.2.0 / whiteboard 1.5.9 / richdocuments 11.1.0 /
#   richdocumentscode 26.4.104 ; counts: enabled 68 disabled 9
#   HOW IT FAILS: any "None" => that app is disabled or gone, and §4's enabled-set equality
#   would then "pass" against a baseline that already lost it. STOP and find out why.

# (e) the pending set is the 13 this plan planned for
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ app:update --showonly" \
  | tee /Users/mu/db-dumps/nextcloud-34.0.4-exec/app-updates-pending-pre.txt | wc -l
#   EXPECT: 13, and the names/versions in §1.3's table.
#   HOW IT FAILS: a DIFFERENT count or a version above the table => upstream drifted again
#   (this is F-58f0bbab's whole subject). A LOWER count is as suspicious as a higher one.
#   Read the file before continuing; a new MAJOR in that list is an operator decision, not
#   an executor one.

# (f) live push is green BEFORE we touch anything
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ notify_push:self-test"
#   EXPECT: all six lines green, incl. "push server is running the same version as the app"
#   HOW IT FAILS: a red line here is a PRE-EXISTING fault (the notify-push.yaml config.php
#   redis-host trap) that this bump would otherwise be blamed for. Fix or accept it first.

# (g) the whiteboard app is pointed at OUR backend (else §4 gate 5e tests nothing)
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ config:app:get whiteboard collabBackendUrl"
#   EXPECT: wss://whiteboard.<our domain>   (measured non-empty 2026-09-20)
#   HOW IT FAILS: empty => the app is not talking to this backend; §4 gate 5e would pass vacuously.

# (h) both whiteboard tags exist in GHCR — the target AND the rollback target
TOKEN=$(curl -s "https://ghcr.io/token?scope=repository:nextcloud-releases/whiteboard:pull&service=ghcr.io" \
  | /Users/mu/code/cberg-home-nextgen/.venv/bin/python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
for T in v2.0.0 v1.5.9; do
  printf '%s ' "$T"
  curl -sI -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.oci.image.index.v1+json" \
    "https://ghcr.io/v2/nextcloud-releases/whiteboard/manifests/$T" | grep -i docker-content-digest
done
#   EXPECT exactly (re-verified 2026-09-20):
#     v2.0.0 docker-content-digest: sha256:059596633333d009890c64858f89f133ccd973a2e0823ad960a0cc05cf8657f1
#     v1.5.9 docker-content-digest: sha256:b60b7633f90d106ac6922f9bc27e1a1ca2442488b740fefdae4c812f34e9cebc
#   HOW IT FAILS: a DIFFERENT v2.0.0 digest => upstream rebuilt the tag after this plan was
#   written; STOP and re-read the release (the §4 gate 5a digest gate would fail anyway). A missing
#   v1.5.9 => §5.4 has no image to roll back to: ABORT the whiteboard leg.
#   (TOKEN is used in the SAME command block — it is not carried across steps.)
```

**2.1 Cluster / Flux / storage green, nothing in flight**

```bash
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'        # expect header ONLY
flux get helmreleases -n office | grep nextcloud                # READY True, chart 9.2.6
kubectl -n office get pods -l app.kubernetes.io/name=nextcloud  # all Running, 0 recent restarts
kubectl -n office get pods | grep -E 'nextcloud-(notify-push|redis|mariadb|whiteboard)'
kubectl get volumes -n storage nextcloud-mariadb nextcloud-config \
  -o custom-columns=NAME:.metadata.name,STATE:.status.state,ROBUST:.status.robustness,LAST_BACKUP:.status.lastBackupAt
kubectl -n office get jobs --sort-by=.metadata.creationTimestamp | grep nextcloud-cron | tail -3
```

EXPECT: header-only from the first line; volumes attached/healthy with
`lastBackupAt` from last night (measured 2026-09-20: mariadb 03:04:10Z, config
03:08:50Z — both `Completed`); newest cron Jobs `Complete 1/1`.
HOW IT FAILS: any non-True Kustomization printed by the `awk` means something
else is already broken and this window should fix that first. A
`lastBackupAt` older than ~36 h means the durable rollback floor under §5.3 is
not where the premises claim (the premise checks STATE; only the executor can
read the AGE).

**2.2 Application + DB baseline (the numbers §4 diffs against)**

```bash
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ status" \
  > /Users/mu/db-dumps/nextcloud-34.0.4-exec/occ-status-pre.txt
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ app:list --output=json" \
  > /Users/mu/db-dumps/nextcloud-34.0.4-exec/app-list-pre.json
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ config:system:get version" \
  > /Users/mu/db-dumps/nextcloud-34.0.4-exec/config-version-pre.txt      # 34.0.3.2
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ notify_push:self-test" \
  > /Users/mu/db-dumps/nextcloud-34.0.4-exec/notify-push-selftest-pre.txt 2>&1
cat /Users/mu/db-dumps/nextcloud-34.0.4-exec/config-version-pre.txt      # HOW IT FAILS: empty file => the exec failed silently; re-run before trusting §4
```

DB contents baseline — table count + row counts of the tables this change can
hurt:

```bash
kubectl exec -n office nextcloud-mariadb-0 -c mariadb -- sh -c '
  mariadb -uroot -p"$(cat $MARIADB_ROOT_PASSWORD_FILE)" -N -B nextcloud -e "show tables" | wc -l
  for T in oc_filecache oc_mail_accounts oc_mail_mailboxes oc_mail_messages oc_users oc_calendarobjects oc_cards oc_migrations oc_appconfig; do
    printf "%s=%s\n" "$T" "$(mariadb -uroot -p"$(cat $MARIADB_ROOT_PASSWORD_FILE)" -N -B nextcloud -e "select count(*) from $T")"
  done' 2>/dev/null | tee /Users/mu/db-dumps/nextcloud-34.0.4-exec/rows-pre.txt
```

EXPECT (measured 2026-09-20): first line **206**; `oc_filecache=34957`,
`oc_mail_accounts=3`, `oc_mail_mailboxes=35`, `oc_mail_messages=53549`,
`oc_users=3`, `oc_calendarobjects=2854`, `oc_cards=193`, `oc_migrations=531`,
`oc_appconfig=359`.
HOW IT FAILS: an EMPTY file or a zero table count means the exec or the
password file failed — that is a failure, not "no rows". Every count must be
> 0; this baseline is the only thing §4 gate 1 can compare against.

**2.2b MAIL BASELINE — the operator's hard requirement. Read §1.7 first.**

```bash
# CONTROL 1 — the instruments exist. If Mail 5.12.0 ever renames these, a later
# "0 mailboxes" would be indistinguishable from a real emptying.
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ list mail" \
  | grep -cE 'mail:account:diagnose|mail:mailbox:list'
#   EXPECT: 2   HOW IT FAILS: anything else => the gate below is measuring nothing. STOP.

# CONTROL 2 — how many accounts the DB says exist. The probe must find exactly these.
kubectl exec -n office nextcloud-mariadb-0 -c mariadb -- sh -c \
  'mariadb -uroot -p"$(cat $MARIADB_ROOT_PASSWORD_FILE)" -N -B nextcloud -e "select id from oc_mail_accounts order by id"' \
  2>/dev/null | tee /Users/mu/db-dumps/nextcloud-34.0.4-exec/mail-account-ids.txt
#   EXPECT: 1 2 3 on three lines (2026-09-20). HOW IT FAILS: empty => STOP (see CONTROL 1).

# ENUMERATE by probing 1..10 — `occ mail:account:list` does not exist (§1.7).
# Truncating redirect on the WHOLE loop: no `tee -a`, nothing appended to an older run.
for N in 1 2 3 4 5 6 7 8 9 10; do
  echo "===== account $N ====="
  kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ mail:account:diagnose $N" 2>&1
  echo "----- account $N exit=$? -----"
done > /Users/mu/db-dumps/nextcloud-34.0.4-exec/mail-diagnose-pre.txt 2>&1

grep -E '^===== account|^----- account|Account has [0-9]+ messages in [0-9]+ mailboxes|Horde error occurred|does not exist' \
  /Users/mu/db-dumps/nextcloud-34.0.4-exec/mail-diagnose-pre.txt
```

EXPECT, measured 2026-09-20 — **this exact shape is the baseline, failures
included**:

```
account 1  -> "Account has 26086 messages in 11 mailboxes"   exit=0
account 2  -> "Account has 11925 messages in 10 mailboxes"   exit=0    (iCloud)
account 3  -> capabilities, then "Horde error occurred: The object could not be
              deleted because it does not exist."            exit=2    (F-85ee12b0, PRE-EXISTING)
accounts 4..10 -> "Account N does not exist"                 exit=1
```

HOW IT FAILS: the probe finding **fewer** existing accounts than CONTROL 2
listed means the gate would silently skip one — STOP and re-derive. Accounts
4..10 must say *does not exist*; if one of them answers, there is an account
this plan never baselined.

```bash
# The per-account MAILBOX COUNT — the instrument that works on ALL THREE accounts,
# including the one whose diagnose errors. This is the equality gate in §4.
for N in 1 2 3; do
  printf '%s ' "$N"
  kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ mail:mailbox:list $N" \
    2>/dev/null | grep -c '^| [0-9]'
done > /Users/mu/db-dumps/nextcloud-34.0.4-exec/mail-mailboxcount-pre.txt
cat /Users/mu/db-dumps/nextcloud-34.0.4-exec/mail-mailboxcount-pre.txt
```

EXPECT exactly (2026-09-20):

```
1 11
2 10
3 14
```

HOW IT FAILS: any count of `0` is a failure, not an empty account — it means
the command errored (CONTROL 1 is the guard). Note 11 + 10 + 14 = 35 =
`oc_mail_mailboxes` from §2.2, which is the independent cross-check that this
instrument is reading real state.

**2.3 Pre-change DB dump — the restore point for §5.3.**
`--default-character-set=utf8mb4` is load-bearing: every table is `utf8mb4_bin`
while the server default is `utf8mb3`, and without it the server flattens every
4-byte character to `?` on the way out (bitnamilegacy-exit-nextcloud-db §3c —
that dump was lossy and passed every row-count check).

**The dump path is literal in every command below**, including §5.3 (the
previous revision set `D=…` here and read `"$D"` in the rollback, hours and
several fresh shells later — an unset `$D` makes the restore read from an empty
path).

```bash
kubectl exec -n office nextcloud-mariadb-0 -c mariadb -- sh -c \
  'mariadb-dump -uroot -p"$(cat $MARIADB_ROOT_PASSWORD_FILE)" \
     --default-character-set=utf8mb4 \
     --single-transaction --routines --triggers --events \
     --databases nextcloud' 2>/dev/null \
  > /Users/mu/db-dumps/nextcloud-34.0.4-exec/nextcloud-pre-34.0.4.sql
chmod 600 /Users/mu/db-dumps/nextcloud-34.0.4-exec/nextcloud-pre-34.0.4.sql

ls -l  /Users/mu/db-dumps/nextcloud-34.0.4-exec/nextcloud-pre-34.0.4.sql   # must NOT be 0 bytes (2026-09-15's was ~718 MB)
tail -1 /Users/mu/db-dumps/nextcloud-34.0.4-exec/nextcloud-pre-34.0.4.sql  # must read "-- Dump completed"
grep -c 'CREATE TABLE' /Users/mu/db-dumps/nextcloud-34.0.4-exec/nextcloud-pre-34.0.4.sql   # must equal 206 from §2.2
grep -c 'SET NAMES utf8mb4' /Users/mu/db-dumps/nextcloud-34.0.4-exec/nextcloud-pre-34.0.4.sql   # must be >= 1 — the charset proof
```

HOW IT FAILS: a zero-byte file, a missing `-- Dump completed` trailer, a
`CREATE TABLE` count below 206, or a `SET NAMES utf8mb4` count of 0 each mean
there is **no usable restore point** — and §5.3 is the only real rollback this
plan has. ABORT; do not proceed on a dump you have not checked.

**2.4 Longhorn snapshots — fast-path insurance for the PVC-resident code +
custom_apps and for the DB.** Same-day only (the 02:30
`global-snapshot-cleanup` deletes user snapshots); the dump + nightly backup
are the durable floor.

```bash
for V in nextcloud-config nextcloud-mariadb; do kubectl apply -f - <<EOF
apiVersion: longhorn.io/v1beta2
kind: Snapshot
metadata:
  name: ${V}-pre-34-0-4
  namespace: storage
spec:
  volume: ${V}
  createSnapshot: true
EOF
done
sleep 10
kubectl -n storage get snapshot.longhorn.io nextcloud-config-pre-34-0-4 nextcloud-mariadb-pre-34-0-4 \
  -o custom-columns=NAME:.metadata.name,READY:.status.readyToUse,SIZE:.status.size
```

EXPECT: `readyToUse true` on both. HOW IT FAILS: `false`/empty => the fast-path
revert in §5.3(c) does not exist; you are relying on the dump + last night's
backup alone. That is survivable but must be a conscious choice.

**2.5 Silence + active-update marker** (application-update SOP Step 1; 4 h TTL).
The port-forward is started and used **inside one command block** — it does not
survive to §3.6, which re-establishes its own.

```bash
runbooks/update-marker.sh add nextcloud office 4 "34.0.3->34.0.4 + chart 9.3.0 + whiteboard v2.0.0 (plan nextcloud-34.0.4)"

kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 >/dev/null 2>&1 & PF=$!
sleep 3
curl -s -X POST localhost:9093/api/v2/silences -H 'Content-Type: application/json' -d '{
  "matchers":[{"name":"namespace","value":"office","isRegex":false,"isEqual":true},
              {"name":"alertname","value":"Nextcloud.*|Kube(Pod|Deployment|Job).*|TargetDown","isRegex":true,"isEqual":true}],
  "startsAt":"'"$(/Users/mu/code/cberg-home-nextgen/.venv/bin/python3 -c "from datetime import *;print(datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")"'",
  "endsAt":"'"$(/Users/mu/code/cberg-home-nextgen/.venv/bin/python3 -c "from datetime import *;print((datetime.now(timezone.utc)+timedelta(hours=4)).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")"'",
  "createdBy":"maintenance-window-agent",
  "comment":"nextcloud 34.0.3->34.0.4 + chart 9.3.0 + whiteboard v2.0.0 — rollout and transient cron-job failures during maintenance mode. auto-expires 4h"}' \
  > /Users/mu/db-dumps/nextcloud-34.0.4-exec/silence.json
echo
/Users/mu/code/cberg-home-nextgen/.venv/bin/python3 -c \
  "import json;print('silenceID', json.load(open('/Users/mu/db-dumps/nextcloud-34.0.4-exec/silence.json'))['silenceID'])"
kill $PF 2>/dev/null        # $PF was set in THIS block — nothing is carried across steps
```

HOW IT FAILS: if the last line raises `KeyError: 'silenceID'`, the POST was
rejected (read `silence.json` for the body) — **do not proceed believing you are
silenced.** The silence is namespace-wide, which is why §6 forbids running
other `office` plans in this slot.

## 3) Steps

**3.1 Go/no-go.** All premises PASS, 2.0b-2.5 clean, dump + snapshots verified
present. The operator is present, can open Files + Mail + a whiteboard
afterwards, and knows the 07:00 briefing must not be running. Abort otherwise.

**3.2 Drain the appstore pass in the foreground (in-pod, deliberate, non-GitOps).**

This is the step that turns the trap into a routine bump. It is the same work
`occ upgrade` would do at line 244 during the next start (§1.3) — just done
where a probe cannot kill it and where each app reports on its own. It is not a
manifest change: appstore apps live on the `nextcloud-config` PVC
(`custom_apps/`) and in the DB, exist in no git repository, and are precisely
the "app state on a PVC with no GitOps path" class the CLAUDE.md exception
covers. The §2.4 snapshot is the backup taken before writing.

```bash
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ app:update --all" 2>&1 \
  | tee /Users/mu/db-dumps/nextcloud-34.0.4-exec/app-update-all.log

# CONTROL: the log must contain one success line per updated app — an EMPTY log is a failure,
# not "nothing to do" (§2.0b(e) already proved 13 updates were pending).
grep -cE 'updated|Updated' /Users/mu/db-dumps/nextcloud-34.0.4-exec/app-update-all.log       # expect ~13
grep -inE 'error|failed|could not|exception' /Users/mu/db-dumps/nextcloud-34.0.4-exec/app-update-all.log   # expect NO output
```

EXPECT: one "updated" line per pending app — **13 of them, including
`whiteboard` (→ 2.0.0) and `mail` (→ 5.12.0)**. `richdocumentscode` (the CODE
AppImage, 26.4.104 → 26.4.303) is the slow one: minutes, not seconds.

HOW IT FAILS: the second `grep` printing any line. Note `grep -c` exits 1 when
it counts zero — for the error grep, **no output and exit 1 is the PASS**.

```bash
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ app:update --showonly" \
  | tee /Users/mu/db-dumps/nextcloud-34.0.4-exec/app-updates-pending-post-3.2.txt | wc -l      # expect 0
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ status"
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ app:list --output=json" \
  > /Users/mu/db-dumps/nextcloud-34.0.4-exec/app-list-post-3.2.json

/Users/mu/code/cberg-home-nextgen/.venv/bin/python3 - <<'PY'
import json
pre  = json.load(open('/Users/mu/db-dumps/nextcloud-34.0.4-exec/app-list-pre.json'))
post = json.load(open('/Users/mu/db-dumps/nextcloud-34.0.4-exec/app-list-post-3.2.json'))
assert set(pre['enabled']) == set(post['enabled']), ('ENABLED SET CHANGED', set(pre['enabled']) ^ set(post['enabled']))
for a in ('mail', 'openclaw_mail', 'notify_push', 'google_synchronization', 'whiteboard'):
    assert a in post['enabled'], f'{a} LEFT THE ENABLED SET'
print('enabled set unchanged')
print('mail      ', pre['enabled']['mail'],       '->', post['enabled']['mail'])
print('whiteboard', pre['enabled']['whiteboard'], '->', post['enabled']['whiteboard'])
PY
```

EXPECT: pending list now **empty** (0 lines); `occ status` still
`34.0.3.2`, `maintenance: false`, `needsDbUpgrade: false`; the assertions print
`mail 5.10.12 -> 5.12.0` and `whiteboard 1.5.9 -> 2.0.0`.

HOW IT FAILS: a non-empty pending list means the drain did not finish and the
entrypoint's `occ upgrade` will try to download inside the 360 s probe budget —
the exact 2026-06-06 trap. An `AssertionError` means an app left the enabled
set; re-force-enable it (`occ app:enable --force <app>`) before continuing.

Two expected wrinkles, neither a fault:

- `occ notify_push:self-test` now fails ONLY on *"push server is running the
  same version as the app"* — the binary on disk is 1.4.1 while the running
  container still executes 1.4.0. Step 3.4 rolls that Deployment.
- The whiteboard is now **app 2.0.0 / backend v1.5.9** until §3.4 completes.
  That skew is benign and expected (§1.6).

**If any app update fails:** stop here; the instance is still 34.0.3 and
serving; fix that app with §5.1 (move aside → `app:install`) before touching
the image. Do not proceed to 3.3 with a broken app dir — that is the exact
state the entrypoint's `occ upgrade` turns into stuck maintenance.

**3.3 GitOps edit — one commit, three files, five lines + the temporary
remediation flip** (application-update SOP Step 2: a Flux rollback of a
half-run `occ upgrade` would start the OLD image on NEW data and crash-loop —
§5.3 — so remediation is off for the attempt).

Every `sed` below replaces a **whole anchored line with a literal**, rather than
using a capture group plus `\1`: a replacement like `\134.0.4` is ambiguous to
BSD sed (is that group 1 then "34", or group 13?). Literal lines have no such
reading. No `\s` anywhere; `sed -i ''` carries its mandatory BSD argument.

```bash
cd /Users/mu/code/cberg-home-nextgen
git fetch origin main && git merge --ff-only origin/main

sed -i '' -E 's|^      version: 9\.2\.6$|      version: 9.3.0|' \
  kubernetes/apps/office/nextcloud/app/helmrelease.yaml
sed -i '' -E 's|^      tag: 34\.0\.3$|      tag: 34.0.4|' \
  kubernetes/apps/office/nextcloud/app/helmrelease.yaml
sed -i '' -E 's|^          image: nextcloud:34\.0\.3$|          image: nextcloud:34.0.4|' \
  kubernetes/apps/office/nextcloud/app/helmrelease.yaml
sed -i '' -E 's|^          image: nextcloud:34\.0\.3$|          image: nextcloud:34.0.4|' \
  kubernetes/apps/office/nextcloud/app/notify-push.yaml
sed -i '' -E 's|^        image: ghcr\.io/nextcloud-releases/whiteboard:v1\.5\.9$|        image: ghcr.io/nextcloud-releases/whiteboard:v2.0.0|' \
  kubernetes/apps/office/nextcloud/app/whiteboard-proxy.yaml

# remediation: retries 3 -> 0 for this attempt (block is `upgrade:` -> `remediation:` -> `retries: 3`)
/Users/mu/code/cberg-home-nextgen/.venv/bin/python3 - <<'PY'
p = '/Users/mu/code/cberg-home-nextgen/kubernetes/apps/office/nextcloud/app/helmrelease.yaml'
s = open(p).read()
new = s.replace("  upgrade:\n    cleanupOnFail: true\n    remediation:\n      retries: 3\n",
                "  upgrade:\n    cleanupOnFail: true\n    remediation:\n      retries: 0                 # TEMPORARY (plan nextcloud-34.0.4 §3.3) — restore 3 in §3.6\n      remediateLastFailure: false\n", 1)
assert new != s, 'remediation block not found — edit by hand'
open(p, 'w').write(new)
print('remediation flipped to 0')
PY
```

Now the gates. **Each prints a number; the expected number is stated. A `0`
from a `grep -c` also exits 1 — for the "expect 0" line that exit IS the pass.**

```bash
cd /Users/mu/code/cberg-home-nextgen
# POSITIVE gates — each must print exactly 1 (these are the CONTROLS: they prove the
# seds matched, so that the "expect 0" gate below cannot pass by having eaten the file).
# Each prints a BARE number — one file per command.
grep -c '^      version: 9\.3\.0$'                  kubernetes/apps/office/nextcloud/app/helmrelease.yaml
grep -c '^      tag: 34\.0\.4$'                     kubernetes/apps/office/nextcloud/app/helmrelease.yaml
grep -c '^          image: nextcloud:34\.0\.4$'     kubernetes/apps/office/nextcloud/app/helmrelease.yaml
grep -c '^          image: nextcloud:34\.0\.4$'     kubernetes/apps/office/nextcloud/app/notify-push.yaml
grep -c 'whiteboard:v2\.0\.0'                       kubernetes/apps/office/nextcloud/app/whiteboard-proxy.yaml

# NEGATIVE gate — no old pin survives anywhere in the three files.
# With MULTIPLE files grep prefixes every count with the filename, so the PASS is
# THREE lines each ending in ":0" (not a bare 0), and the command exits 1:
#   .../helmrelease.yaml:0   .../notify-push.yaml:0   .../whiteboard-proxy.yaml:0
grep -cE '34\.0\.3|version: 9\.2\.6|whiteboard:v1\.5\.9' \
  kubernetes/apps/office/nextcloud/app/helmrelease.yaml \
  kubernetes/apps/office/nextcloud/app/notify-push.yaml \
  kubernetes/apps/office/nextcloud/app/whiteboard-proxy.yaml

grep -A2 'remediation:' kubernetes/apps/office/nextcloud/app/helmrelease.yaml \
  | grep -cE 'retries: 0|remediateLastFailure: false'        # expect 2
git diff --stat                                             # expect EXACTLY these 3 files
```

HOW IT FAILS: a positive gate printing `0` means that sed did not match (check
the indentation against the line numbers in §1.1 before re-running). The
negative gate printing anything but `0` means an old pin survived and the
commit would be half-applied. `git diff --stat` showing a fourth file means the
shared worktree is dirty — see the commit rules below.

Commit (shared worktree: `--only`, never `git add -A`):

```bash
cd /Users/mu/code/cberg-home-nextgen
cat > /tmp/nc-msg.txt <<'EOF'
feat(nextcloud): 34.0.3 -> 34.0.4 with chart 9.2.6 -> 9.3.0 (lockstep) + whiteboard backend v2.0.0

Executes runbooks/maintenance/plans/nextcloud-34.0.4.md.

CHART AND IMAGE MOVE TOGETHER, as the *nextcloud* deny rule requires. Chart
9.3.0 carries appVersion 34.0.4 (published 2026-09-19), so the lockstep clause
finally has a target; the operator chose the newest of the two candidates.
Rendered against our live values the 9.2.6 -> 9.3.0 chart delta is labels-only
plus one added `suspend: false` on the CronJob — which is already its live
state — so the chart half is behaviourally inert and every behaviour change
here comes from the image's occ upgrade. image.tag stays pinned explicitly on
the app container and the worker sidecar; notify-push moves in the same commit
by rule.

The collaboration backend moves v1.5.9 -> v2.0.0 in this same commit because
`occ app:update --all` (plan section 3.2) moves the Nextcloud whiteboard APP
1.5.9 -> 2.0.0. The two legs are one change and land together. This supersedes
plan nextcloud-whiteboard-2.0.0. No secret work: the JWT contract and the
env-var contract are unchanged upstream.

The 13 pending appstore updates were drained in the foreground BEFORE this
bump (plan section 3.2) so the entrypoint's occ upgrade has nothing to
download inside the 360 s startup-probe budget — the 2026-06-06 trap.

upgrade.remediation.retries 3 -> 0 for the attempt only (a Flux rollback onto
data occ upgrade already moved would crash-loop on the entrypoint's downgrade
refusal); restored in the follow-up commit.

security_ref: F-ab9e243a
finding_refs: F-f3e9ddb0 F-4a9d6631 F-53ba35b1 F-6c461103
EOF

git commit --only kubernetes/apps/office/nextcloud/app/helmrelease.yaml \
                  kubernetes/apps/office/nextcloud/app/notify-push.yaml \
                  kubernetes/apps/office/nextcloud/app/whiteboard-proxy.yaml \
                  -F /tmp/nc-msg.txt
git show --stat HEAD          # HOW IT FAILS: any file here that is not one of the three => a
                              # concurrent session's hunk rode along. Do NOT push; see CLAUDE.md
                              # "Committing in a SHARED worktree".
git log -1 --format=%s        # MUST be the subject above — .git/COMMIT_EDITMSG is shared and two
                              # sessions committing in the same second can swap messages. Amend now,
                              # never after the push.
git push origin main
```

**3.4 Watch the rollout — this is the attended part.** Flux reconciles the
Kustomization (webhook); the HelmRelease upgrades to chart 9.3.0 (`--wait`,
30 m timeout); the Deployment does `Recreate`. From the moment the new
container starts you have **360 s** before the startup probe kills it.

```bash
flux get kustomization -n office nextcloud                     # revision = your commit
flux get helmrelease -n office nextcloud                       # Upgrading -> Ready, chart 9.3.0
kubectl -n office get pods -l app.kubernetes.io/name=nextcloud -w   # old pod Terminating, new pod Init -> Running
```

In a second terminal, the moment the new pod exists (the pod name is resolved
and used in the **same** command — nothing is carried across steps):

```bash
kubectl -n office logs -f \
  "$(kubectl -n office get pod -l app.kubernetes.io/name=nextcloud,app.kubernetes.io/component=app -o jsonpath='{.items[0].metadata.name}')" \
  -c nextcloud --timestamps
```

Expected log shape and timing (measured rsync ≈ 86 s; `occ upgrade` with the
appstore pass already drained: seconds):

```
Initializing nextcloud 34.0.4.x ...
Upgrading nextcloud from 34.0.3.2 ...
Initializing finished                     <- ~90 s after start (rsync done)
Nextcloud or one of the apps require upgrade - only a limited number of commands are available
Setting log level to debug / Turned on maintenance mode
Updating database schema / Updated database
Updating <app> ...                        <- shipped apps only; NO downloads expected
Update successful
Turned off maintenance mode
Resetting log level
```

then Apache's `AH00558`/`Command line: 'apache2 -D FOREGROUND'`. HOW IT FAILS:
if at **~300 s after container start** the log is still inside `occ upgrade`,
get ready for §5.2 — do not delete the pod, do not scale anything; let the
kubelet act and then repair.

```bash
kubectl -n office rollout status deploy/nextcloud --timeout=15m
kubectl -n office rollout status deploy/nextcloud-notify-push --timeout=5m    # rolls on the tag change
kubectl -n office rollout status deploy/nextcloud-whiteboard --timeout=5m     # rolls on the v2.0.0 change
kubectl -n office get pods | grep -E '^nextcloud-(notify-push|whiteboard|cron)'
```

HOW IT FAILS: `rollout status` reporting success is **not** proof the new bytes
are running — it can green-light the old generation mid-upgrade. §4 verifies by
**digest**, which is the actual gate.

**3.5 Verify** — §4 in full. Every assertion, including the contents ones.

**3.6 Close out** (only after §4 is green):

```bash
cd /Users/mu/code/cberg-home-nextgen
/Users/mu/code/cberg-home-nextgen/.venv/bin/python3 - <<'PY'
p = '/Users/mu/code/cberg-home-nextgen/kubernetes/apps/office/nextcloud/app/helmrelease.yaml'
s = open(p).read()
new = s.replace("      retries: 0                 # TEMPORARY (plan nextcloud-34.0.4 §3.3) — restore 3 in §3.6\n      remediateLastFailure: false\n",
                "      retries: 3\n", 1)
assert new != s, 'temporary remediation block not found — check by hand'
open(p, 'w').write(new)
print('remediation restored to 3')
PY
grep -A2 'remediation:' kubernetes/apps/office/nextcloud/app/helmrelease.yaml | grep -c 'retries: 3'   # expect 2 (install + upgrade)
git commit --only kubernetes/apps/office/nextcloud/app/helmrelease.yaml \
  -m "chore(nextcloud): restore upgrade.remediation.retries 3 after the 34.0.4 rollout (plan nextcloud-34.0.4 §3.6)"
git show --stat HEAD && git log -1 --format=%s && git push origin main

runbooks/update-marker.sh clear nextcloud

kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 >/dev/null 2>&1 & PF=$!
sleep 3
curl -s -X DELETE "localhost:9093/api/v2/silence/$(/Users/mu/code/cberg-home-nextgen/.venv/bin/python3 -c "import json;print(json.load(open('/Users/mu/db-dumps/nextcloud-34.0.4-exec/silence.json'))['silenceID'])")" \
  -o /dev/null -w "DELETE -> HTTP %{http_code}\n"
curl -s localhost:9093/api/v2/silences | /Users/mu/code/cberg-home-nextgen/.venv/bin/python3 -c "
import sys, json
act = [s for s in json.load(sys.stdin) if s['status']['state'] == 'active' and 'office' in json.dumps(s['matchers'])]
print('active office silences remaining:', len(act))
for s in act: print('  STILL ACTIVE:', s['id'], s['comment'][:60])"
kill $PF 2>/dev/null        # $PF was set in THIS block — nothing is carried across steps
```

HOW IT FAILS: the count is the real gate, not the DELETE status — a 404 means
the id file was lost, in which case match on the `createdBy`/`comment` text
rather than leaving a namespace-wide silence to age out for 4 h.

Then retire this plan file in the commit that records the window (README: plans
are transient) and close the findings:

```bash
runbooks/policy-cli.py finding close F-f3e9ddb0 --commit <sha>
runbooks/policy-cli.py finding close F-4a9d6631 --commit <sha>
runbooks/policy-cli.py finding close F-53ba35b1 --commit <sha>
```

`F-ab9e243a` and `F-6c461103` are security rows that close on the post-window
security-check re-scan: **CONFIRM on that run's output that they actually
resolved rather than assuming**, and say so in the window report. Also close
`F-0cd73f3f` (the plan-lane row that sent this plan back — B1 and B2 are now
decided and implemented) once this plan executes. Keep
`/Users/mu/db-dumps/nextcloud-34.0.4-exec/` until the next nightly Longhorn
backup covers the post-upgrade state, then `rm -P` the dump.

## 4) Verification

Floor (shape):

```bash
kubectl get helmrelease -n office nextcloud \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion}{"\n"}'
#   EXPECT: True 9.3.0    HOW IT FAILS: chart still 9.3.0 but Ready False => the upgrade failed;
#   9.2.6 => Flux never applied the commit (check the Kustomization revision).
kubectl -n office get deploy nextcloud nextcloud-notify-push nextcloud-whiteboard \
  -o jsonpath='{range .items[*]}{.metadata.name}{" "}{range .spec.template.spec.containers[*]}{.image}{" "}{end}{"\n"}{end}'
#   EXPECT: nextcloud docker.io/nextcloud:34.0.4 nextcloud:34.0.4 /
#           nextcloud-notify-push nextcloud:34.0.4 /
#           nextcloud-whiteboard ghcr.io/nextcloud-releases/whiteboard:v2.0.0
kubectl -n office get pod -l app.kubernetes.io/name=nextcloud,app.kubernetes.io/component=app \
  -o jsonpath='{.items[0].status.containerStatuses[?(@.name=="nextcloud")].imageID}{"\n"}'
#   EXPECT: a 34.0.4 digest, restarts 0. HOW IT FAILS: a 34.0.3 digest means the Pod never rolled —
#   which `rollout status` will happily report as success.
kubectl -n office get cronjob nextcloud-cron \
  -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].image}{" suspend="}{.spec.suspend}{"\n"}'
#   EXPECT: docker.io/nextcloud:34.0.4 suspend=false
#   HOW IT FAILS: suspend=true would mean the chart's NEW key (§1.2) landed with the wrong value
#   and the 5-minute cron is silently dead — the one live consequence the chart bump could have.
kubectl -n office get jobs --sort-by=.metadata.creationTimestamp | grep nextcloud-cron | tail -2
#   EXPECT: newest Complete 1/1 — wait for one that STARTED after the rollout.
```

Application (the post-upgrade checklist from `project_nextcloud_upgrade_mailapp`,
made executable):

```bash
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ status" \
  | tee /Users/mu/db-dumps/nextcloud-34.0.4-exec/occ-status-post.txt
#   EXPECT: versionstring 34.0.4 / version 34.0.4.x / maintenance false / needsDbUpgrade false
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ config:system:get version"
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ app:list --output=json" \
  > /Users/mu/db-dumps/nextcloud-34.0.4-exec/app-list-post.json

/Users/mu/code/cberg-home-nextgen/.venv/bin/python3 - <<'PY'
import json
pre  = json.load(open('/Users/mu/db-dumps/nextcloud-34.0.4-exec/app-list-pre.json'))
post = json.load(open('/Users/mu/db-dumps/nextcloud-34.0.4-exec/app-list-post.json'))
assert set(pre['enabled']) == set(post['enabled']), ('ENABLED SET CHANGED — re-force-enable per memory', set(pre['enabled']) ^ set(post['enabled']))
assert not (set(post['disabled']) - set(pre['disabled'])), ('NEWLY DISABLED', set(post['disabled']) - set(pre['disabled']))
for a in ('mail', 'openclaw_mail', 'notify_push', 'google_synchronization', 'whiteboard', 'richdocuments'):
    assert a in post['enabled'], f'{a} LEFT THE ENABLED SET'
print('OK enabled set identical (%d apps)' % len(post['enabled']))
for a in ('mail', 'whiteboard', 'notify_push', 'openclaw_mail', 'richdocumentscode'):
    print(f'  {a:<20} {pre["enabled"].get(a)} -> {post["enabled"].get(a)}')
PY
```

EXPECT: `mail 5.10.12 -> 5.12.0`, `whiteboard 1.5.9 -> 2.0.0`,
`notify_push 1.4.0 -> 1.4.1`, `richdocumentscode 26.4.104 -> 26.4.303`, and
**`openclaw_mail 0.1.0 -> 0.1.0`** — the custom app is re-materialized by the
`install-openclaw-mail` initContainer on every boot and re-enabled by the
worker sidecar (§1.7), so a Recreate rollout must leave it enabled and
unchanged. HOW IT FAILS: `openclaw_mail` missing from `enabled` means the
initContainer or the worker's enable loop did not complete — the OpenClaw draft
route is down even though Nextcloud looks healthy.

```bash
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ app:update --showonly" | wc -l   # expect 0
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ notify_push:self-test" \
  | tee /Users/mu/db-dumps/nextcloud-34.0.4-exec/notify-push-selftest-post.txt        # all 6 lines green
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ integrity:check-core"   # no output = clean
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c \
  "tail -300 /var/www/html/data/nextcloud.log" | grep -E '"level":[34]' | grep -viE 'STATUS|Horde_Imap|account statistics' | head
#   EXPECT: no upgrade-related errors. The account-3 Horde noise and the iCloud STATUS noise are
#   filtered because both are known-benign and PRE-EXISTING (§1.7) — do not widen this filter to
#   hide anything else.
#   CONTROL: re-run WITHOUT the second grep; it must print SOMETHING (the known account-3 lines),
#   proving the log path and the level filter actually match. A silent empty result from both
#   greps means you are reading the wrong file, not that the log is clean.
curl -s "https://drive.${SECRET_DOMAIN}/status.php"    # substitute the real hostname by hand — it is not in this repo
#   EXPECT: installed true, maintenance false, versionstring 34.0.4 (through the Gateway, external path)
```

**CONTENTS ASSERTIONS** (README rule: assert the property the change could
silently break, not a proxy for it).

**1. CONTENTS ASSERTION: the database still holds the data.** Measured by the
same row-count loop as §2.2, compared to `rows-pre.txt`.

```bash
kubectl exec -n office nextcloud-mariadb-0 -c mariadb -- sh -c '
  mariadb -uroot -p"$(cat $MARIADB_ROOT_PASSWORD_FILE)" -N -B nextcloud -e "show tables" | wc -l
  for T in oc_filecache oc_mail_accounts oc_mail_mailboxes oc_mail_messages oc_users oc_calendarobjects oc_cards oc_migrations oc_appconfig; do
    printf "%s=%s\n" "$T" "$(mariadb -uroot -p"$(cat $MARIADB_ROOT_PASSWORD_FILE)" -N -B nextcloud -e "select count(*) from $T")"
  done' 2>/dev/null | tee /Users/mu/db-dumps/nextcloud-34.0.4-exec/rows-post.txt
diff /Users/mu/db-dumps/nextcloud-34.0.4-exec/rows-pre.txt \
     /Users/mu/db-dumps/nextcloud-34.0.4-exec/rows-post.txt
```

PASS: table count **≥** 206 (Mail 5.12 may ADD tables, never drop),
`oc_mail_accounts` still **3**, every listed count ≥ pre and > 0, and
`oc_migrations` **>** 531 (the migrations that ran are in the ledger).
HOW IT FAILS: a structurally healthy but emptied `oc_mail_messages` or
`oc_filecache` fails this and `occ status` would not notice. A `diff` showing
any DECREASE is a failure; only increases are allowed.

**2. CONTENTS ASSERTION: Mail still talks IMAP through the updated app —
per account, and unchanged.** *This is the operator's hard requirement and the
single most important gate in this plan.* **Read §1.7 before running it.**

```bash
# (a) CONTROLS first — same two as §2.2b. Instruments must still exist after Mail 5.12.0.
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ list mail" \
  | grep -cE 'mail:account:diagnose|mail:mailbox:list'                      # EXPECT 2
kubectl exec -n office nextcloud-mariadb-0 -c mariadb -- sh -c \
  'mariadb -uroot -p"$(cat $MARIADB_ROOT_PASSWORD_FILE)" -N -B nextcloud -e "select id from oc_mail_accounts order by id"' \
  2>/dev/null                                                               # EXPECT 1 2 3

# (b) the same 1..10 probe, truncating write
for N in 1 2 3 4 5 6 7 8 9 10; do
  echo "===== account $N ====="
  kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ mail:account:diagnose $N" 2>&1
  echo "----- account $N exit=$? -----"
done > /Users/mu/db-dumps/nextcloud-34.0.4-exec/mail-diagnose-post.txt 2>&1

# (c) the per-account MAILBOX COUNT — the hard equality, and it works on all three accounts
for N in 1 2 3; do
  printf '%s ' "$N"
  kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ mail:mailbox:list $N" \
    2>/dev/null | grep -c '^| [0-9]'
done > /Users/mu/db-dumps/nextcloud-34.0.4-exec/mail-mailboxcount-post.txt

diff /Users/mu/db-dumps/nextcloud-34.0.4-exec/mail-mailboxcount-pre.txt \
     /Users/mu/db-dumps/nextcloud-34.0.4-exec/mail-mailboxcount-post.txt \
  && echo "PASS: mailbox counts identical (1 11 / 2 10 / 3 14)"

# (d) the trailing statistics line, side by side
grep -E '^===== account|^----- account|Account has [0-9]+ messages in [0-9]+ mailboxes|Horde error occurred' \
  /Users/mu/db-dumps/nextcloud-34.0.4-exec/mail-diagnose-pre.txt
grep -E '^===== account|^----- account|Account has [0-9]+ messages in [0-9]+ mailboxes|Horde error occurred' \
  /Users/mu/db-dumps/nextcloud-34.0.4-exec/mail-diagnose-post.txt
```

**PASS requires all four:**

- **(c) prints `PASS: mailbox counts identical`.** The mailbox count per account
  is the hard equality — `1 11`, `2 10`, `3 14`. A count that changed means Mail
  5.12.0's migration lost or duplicated mailboxes. A count of `0` is a failure,
  not an empty account (control (a) is what distinguishes them).
- **Accounts 1 and 2 still print `Account has X messages in Y mailboxes` with
  the SAME Y**, and exit 0. **X may legitimately drift** — mail arrives, mail is
  deleted, and the baseline was taken minutes earlier (it moved 26038 → 26086 on
  account 1 between 2026-09-15 and 2026-09-20). So: **require Y equality, and
  require X to be non-zero and within a few percent of the baseline** — do not
  demand X equality, and do not roll back on a drifted message count.
- **Account 3 reproduces its PRE-EXISTING failure shape unchanged**: IMAP
  capabilities listed (so login and CAPABILITY worked), then
  `Horde error occurred: The object could not be deleted because it does not
  exist.`, exit **2**. That is `F-85ee12b0` and **is not a regression** — it was
  measured identically on 2026-09-15 and 2026-09-20 (§1.7).
  - If account 3 now **succeeds**: an improvement. Record it and close
    `F-85ee12b0` — do not treat the changed output as a failure.
  - If account 3 fails **differently** — no capabilities printed, an auth error,
    a timeout, or a different exception — **that IS a regression.** The
    capabilities block is the discriminator: it proves the IMAP session was
    established before the failure.
- **Accounts 4..10 still report `does not exist`.** If one answers, an account
  appeared that was never baselined and the gate above skipped it.

> **The iCloud account (2) may throw an intermittent `STATUS` IMAP error.**
> That is known-benign and self-healing
> (`project_nextcloud_mail_account_quirks`) — it is **not** an auth failure.
> **Retry that account up to three times before calling it a failure**, and
> never roll back a healthy upgrade over it. A `Horde error` on account 2 that
> persists across three retries is a different matter and does fail this gate.

Finally, **the operator opens Mail in a browser and reads one message body** in
each of the three accounts. HOW IT FAILS: a 500 on body fetch. Note the known
Gmail quirk — a body-fetch 500 caused by a stale IMAP UID after a provider-side
relabel/trash is a known condition, not an upgrade regression; re-fetch the
message from the refreshed list before concluding anything.

**3. CONTENTS ASSERTION: live push works end to end.** Measured by the
self-test's *"push server is receiving redis messages"* + *"can connect to the
Nextcloud server"* + *"same version"* lines all green: a real write through
redis to the rebuilt notify-push container, not a `PONG`. HOW IT FAILS: the
"same version" line red means the Deployment did not roll onto 34.0.4 and the
binary/app pair is skewed.

**4. CONTENTS ASSERTION: the metrics exporter still serves the UPGRADED
instance.** Measured by probing `svc/nextcloud-metrics` DIRECTLY (Service port
9100 → targetPort `metrics`/9205; `:9205` on the Service returns nothing),
compared to the pre-change values (measured 2026-09-20: `nextcloud_up 1`,
`nextcloud_system_info{version="34.0.3.2"} 1`, `nextcloud_users_total 3`):

```bash
kubectl exec -n office deploy/nextcloud -c nextcloud -- curl -s http://nextcloud-metrics:9100/metrics \
  | grep -E '^nextcloud_(up|system_info|users_total)' \
  | tee /Users/mu/db-dumps/nextcloud-34.0.4-exec/exporter-post.txt
```

PASS: `nextcloud_up 1`, `nextcloud_system_info{...version="34.0.4.x"...} 1`,
`nextcloud_users_total` equal to the `oc_users` count in `rows-post.txt` (3).
HOW IT FAILS: a missing line, `nextcloud_up 0`, or a version still reading
34.0.3.x. (An empty result is a failure too — the CONTROL is that this same
command printed three lines at baseline.)

Why the exporter and not Prometheus: Prometheus holds ZERO `nextcloud_*` series
and has no scrape target for this exporter — `svc/nextcloud-metrics` carries
only `prometheus.io/scrape` annotations, which kube-prometheus-stack ignores,
and there is no ServiceMonitor/PodMonitor in `office`. A PromQL assertion
therefore fails on the day regardless of the upgrade outcome. That gap is filed
as **`F-44f2be05`** and is a SEPARATE monitoring correction with its own commit
— do not skip the assertion, and do not "fix" it by adding the ServiceMonitor in
the same diff as the version bump.

**5. CONTENTS ASSERTION: the whiteboard backend is running v2.0.0 and its
collaboration is actually authorized end-to-end.** (Absorbed from
`nextcloud-whiteboard-2.0.0` §4 — §1.6.)

Run 5a-5c **before** 5d: they read the startup banner, which is only ~8 lines.
Once a browser generates join traffic the banner scrolls out of a short tail and
these gates read **empty — which is indistinguishable from a failure.**

```bash
# 5a — the new BYTES are running, by digest, not by tag
kubectl get pod -n office -l app=nextcloud-whiteboard \
  -o jsonpath='{.items[0].status.containerStatuses[0].imageID}{"\n"}'
#   PASS: ...whiteboard@sha256:059596633333d009890c64858f89f133ccd973a2e0823ad960a0cc05cf8657f1
#   HOW IT FAILS: the baseline digest sha256:b60b763... still here => the Pod never rolled, which a
#   green `kubectl rollout status` reports as success after a no-op.

# 5b — the backend reports its OWN version (from the image's package.json, not from our spec)
kubectl logs -n office deploy/nextcloud-whiteboard --tail=200 | grep -iE 'whiteboard@'
#   PASS: a line containing whiteboard@2.0.0. At baseline this printed "> whiteboard@1.5.9 server:start",
#   so it is independent of the tag we asked for. HOW IT FAILS: 1.5.9 here, or EMPTY (see ordering note).

# 5c — it finished starting (v2.0.0 made ServerService.start() await socket init)
kubectl logs -n office deploy/nextcloud-whiteboard --tail=200 \
  | grep -iE 'Server started successfully|Failed to start server'
#   PASS: "Server started successfully on port 3002" present AND "Failed to start server" absent.

# 5d — the service answers through the public edge with real contents
curl -s "https://whiteboard.${SECRET_DOMAIN}/socket.io/?EIO=4&transport=polling" | head -c 200; echo
#   Substitute the real hostname by hand (not in this repo). NOTE the quotes: the URL contains `?`
#   and `&`, which zsh would otherwise glob and background.
#   PASS: a body starting 0{"sid":"…","upgrades":["websocket"]…}  (measured in exactly this shape
#   against the live backend on 2026-09-20). HOW IT FAILS: a 404 or empty body while the port is
#   open = the socket.io engine failed to initialize — precisely the area v2.0.0 changed. An HTTP
#   200 on `/` alone proves nothing: v1.5.9 returned 200 there too.
```

**5e — the collaborative round-trip (operator, browser).** This is the property;
everything above it is corroboration.

1. Open a whiteboard file in Nextcloud Files as a real user (browser A).
2. Open the **same** file as a second session (browser B, or a second profile).
3. Draw a stroke in A.

```bash
# CONTROL + positive signal: the join line is emitted ONLY after v2.0.0's new
# roomClaims authorization check passes.
kubectl logs -n office deploy/nextcloud-whiteboard --since=10m | grep -iE 'joined room'
#   PASS: at least one "[<fileId>] <name> joined room" line. This is also the CONTROL for the
#   grep below: if this returns rows, the log stream and the pattern syntax work, so an empty
#   result from the next command means "no rejections", not "grep matched nothing".

kubectl logs -n office deploy/nextcloud-whiteboard --since=10m \
  | grep -iE '\[SECURITY\]|rejecting join|unauthorized room|Token verification failed|Token expired|\[AUTH\] Authentication failed'
#   PASS: EMPTY. HOW IT FAILS: "[SECURITY] Socket <id> rejected from unauthorized room <id>" is the
#   new v2.0.0 gate refusing the app's JWT — the fingerprint of an app/backend mismatch. The pod is
#   Ready and the board still opens and draws (upstream's architecture saves to browser IndexedDB
#   without the socket), so ONLY this gate can see the failure. Non-empty => §5.4.
```

PASS requires **B shows A's stroke** within a second or two and A's participant
avatar appears, **and** the join line is present, **and** the rejection grep is
empty.

**6. Attended:** the operator opens Files, Mail and Calendar on a phone, and
opens one office document (the CODE app was rebuilt in §3.2, so it reloads).

## 5) Rollback

Four tiers, in order of likelihood. Decide by evidence, not by reflex.

**5.1 Stuck maintenance mode and/or a broken app after `occ upgrade` (the
documented failure).** Symptoms: `occ status` shows `maintenance: true`, or
every `occ` fails with a PHP autoload error naming `custom_apps/<app>/vendor`,
cron pods `Error`, `status.php` still 200.

```bash
# 1. get occ loading at all — move the half-extracted app aside
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c \
  "mv /var/www/html/custom_apps/<app> /var/www/html/custom_apps/<app>.broken"
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ status"
# 2. finish what the entrypoint could not
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ upgrade"
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ maintenance:mode --off"
# 3. reinstall the app cleanly from the appstore
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "rm -rf /var/www/html/custom_apps/<app>.broken"
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ app:install <app>"
# 4. re-run §4 in full; re-force-enable anything that moved to Disabled
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ app:enable --force <app>"
```

If it was `notify_push`: after `app:install`, `kubectl -n office rollout
restart deploy/nextcloud-notify-push` so the container picks up the rebuilt
binary, then self-test. If it was `mail`: re-run §4 gate 2 in full afterwards,
not just `occ status`.

**5.2 The startup probe killed the container mid-`occ upgrade`.** The kubelet
restarts it; the entrypoint now sees `version.php` == image version (it is
copied *last*, before `occ upgrade`) so it skips rsync+upgrade and starts Apache
with Nextcloud still in maintenance. Do NOT let Flux or a rollback "help": with
`retries: 0` it will not. Run `occ upgrade` then `maintenance:mode --off` (direct
forms as in §5.1); if an app dir is half-extracted → §5.1. If the kill happened
*during the rsync* instead (log has no `Initializing finished`; `version.php`
still `34,0,3,2`), nothing was migrated — a plain revert (5.3a/d) is enough.

**5.3 Full rollback to 34.0.3 / chart 9.2.6 — only if the instance must go back
in time.** A bare `git revert` is **not** a rollback once `occ upgrade` ran: the
entrypoint (line 184) exits 1 with *"the version of the data (34.0.4.x) is
higher than the docker image version (34.0.3.x) and downgrading is not
supported"* and the pod crash-loops. Rollback therefore restores the data first.

```bash
# (a) freeze GitOps and stop every writer of the two volumes
flux suspend kustomization -n office nextcloud && flux suspend helmrelease -n office nextcloud
kubectl -n office scale deploy/nextcloud deploy/nextcloud-notify-push --replicas=0
kubectl -n office patch cronjob nextcloud-cron -p '{"spec":{"suspend":true}}'
kubectl -n office wait --for=delete pod -l app.kubernetes.io/name=nextcloud,app.kubernetes.io/component=app --timeout=5m

# (b) database: back to the §2.3 dump. LITERAL PATH — there is no $D in this plan.
kubectl exec -n office nextcloud-mariadb-0 -c mariadb -- sh -c \
  'mariadb -uroot -p"$(cat $MARIADB_ROOT_PASSWORD_FILE)" -e "DROP DATABASE nextcloud; CREATE DATABASE nextcloud CHARACTER SET utf8mb4 COLLATE utf8mb4_bin"'
kubectl exec -i -n office nextcloud-mariadb-0 -c mariadb -- sh -c \
  'mariadb -uroot -p"$(cat $MARIADB_ROOT_PASSWORD_FILE)" --default-character-set=utf8mb4' \
  < /Users/mu/db-dumps/nextcloud-34.0.4-exec/nextcloud-pre-34.0.4.sql 2>&1 | tail -5
# then re-run the §2.2 row-count loop and diff against rows-pre.txt: must be IDENTICAL
```

HOW (b) FAILS: if the redirect reads an empty or missing file the DROP has
already happened and the database is gone — **`ls -l` the dump path and confirm
its size BEFORE running the DROP.** This is exactly why the path is literal.

```bash
# (c) code + custom_apps + config: revert PVC nextcloud-config to the §2.4 snapshot.
#     Longhorn UI -> Volume nextcloud-config -> (detached now) -> Attach in Maintenance Mode
#     -> Snapshots -> nextcloud-config-pre-34-0-4 -> Revert -> Detach.
#     If the snapshot is gone (02:30 cleanup ran), restore last night's backup into a NEW
#     volume and rebind the PV per docs/sops/disaster-recovery.md + longhorn.md.
#     (Either way the volume must have NO consumers — that is what (a) guarantees.)

# (d) git: revert the bump commit(s), so the 34.0.3 / chart 9.2.6 spec meets 34.0.3 data
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <bump-sha> [<retries-restore-sha>]
git show --stat HEAD && git log -1 --format=%s && git push origin main
kubectl -n office patch cronjob nextcloud-cron -p '{"spec":{"suspend":false}}'
flux resume helmrelease -n office nextcloud && flux resume kustomization -n office nextcloud
# Flux re-applies replicas: 1; then §4 floor + occ status (34.0.3.2, maintenance false, chart 9.2.6)
# + notify_push self-test + the row-count diff == rows-pre.txt + §4 gate 2 (Mail) in full
```

Note the appstore updates from §3.2 also live on that volume; the snapshot
revert takes them back too (Mail 5.10.12, whiteboard app 1.5.9, etc.),
consistent with the DB dump. Reverting (d) also takes the whiteboard **backend**
to v1.5.9, which re-pairs it with the reverted app — the one place where the
two legs being in one commit makes the rollback simpler, not harder.

If the image bump is abandoned *before* §3.3 but after §3.2, nothing needs
reverting: every updated app declares NC 32-35 compatibility and runs fine on
34.0.3 — just roll notify-push so its binary matches its app, and either bump
the whiteboard backend on its own or accept the benign app-2.0.0/backend-1.5.9
skew (§1.6).

**5.4 Whiteboard backend ONLY — a genuine one-line revert.** Take this when §4
gate 5 fails but Nextcloud itself is healthy (the common case: `[SECURITY]`
rejections in the backend log while Files and Mail are fine). It is stateless:
no PVC, no DB, no migration, `/tmp` is an `emptyDir` discarded with the Pod.

```bash
cd /Users/mu/code/cberg-home-nextgen
sed -i '' -E 's|^        image: ghcr\.io/nextcloud-releases/whiteboard:v2\.0\.0$|        image: ghcr.io/nextcloud-releases/whiteboard:v1.5.9|' \
  kubernetes/apps/office/nextcloud/app/whiteboard-proxy.yaml
grep -c 'whiteboard:v1\.5\.9' kubernetes/apps/office/nextcloud/app/whiteboard-proxy.yaml   # expect 1
git commit --only kubernetes/apps/office/nextcloud/app/whiteboard-proxy.yaml \
  -m "revert(nextcloud-whiteboard): backend v2.0.0 -> v1.5.9 (plan nextcloud-34.0.4 §5.4)"
git show --stat HEAD && git log -1 --format=%s && git push origin main
kubectl rollout status -n office deploy/nextcloud-whiteboard --timeout=180s
kubectl get pod -n office -l app=nextcloud-whiteboard \
  -o jsonpath='{.items[0].status.containerStatuses[0].imageID}{"\n"}'
#   EXPECT: ...@sha256:b60b7633f90d106ac6922f9bc27e1a1ca2442488b740fefdae4c812f34e9cebc
```

**Understand what this does and does not restore.** It leaves **app 2.0.0 /
backend 1.5.9** — the §1.6 benign-direction skew, not the pre-change world,
because the app leg was delivered by §3.2 and lives on a PVC in no git
repository. In practice that is the right place to stop: it is the configuration
most installations run. **Do not roll the app back reflexively.** Only if §4
gate 5e still fails after this revert is the app half at fault, and then the
path is §5.3's snapshot + dump (the app leg is not a git operation) — the
appstore still serves the v1.5.9 release for platform 34.

## 6) Interference notes

- **Attended weekend slot only; never `nightly`.** Not only duration (75 min now
  — it no longer fits a 90-minute slot comfortably alongside anything else, and
  `sun-attended` at 200 min is the right home) but because §3.4 needs eyes on a
  log with a 360 s deadline, §4 gate 2 and gate 5e need a human at a browser,
  and §5.1 is a hands-on repair. The deny rule says the same in fewer words.
- **This plan now carries a MAJOR (`update_type: major`, `capability_change:
  true`) and is human-gated by policy.** It will never ride Step 0 of any
  window, and it must not be run unattended under any circumstances.
- **Shared RWX volume.** `pvc/nextcloud-config` is mounted by
  `deployment/nextcloud`, `deployment/nextcloud-notify-push` and every
  `nextcloud-cron` Job (RWX, Longhorn share-manager/NFS — so notify-push's
  default RollingUpdate is safe here, no multi-attach). §3.2 rewrites
  `custom_apps/` under all three at once; that is why cron may print one
  transient error during the seconds an app is being replaced. Expected.
- **Cron every 5 min.** Jobs that start while `occ upgrade` holds maintenance
  mode exit non-zero → `KubeJobFailed`-class alerts; the §2.5 silence covers
  `namespace=office`. Do not suspend the CronJob for the normal path (it is the
  first post-upgrade contents signal); §5.3 suspends it only for the restore.
  Note the chart's new `suspend` key (§1.2) renders `false` — §4's floor asserts
  it, because a `true` there would silently kill the 5-minute cron.
- **Consumers that will see a 2-5 min 503:** `office/nextcloud-mcp` (bridge for
  OpenClaw), `ai/openclaw` mail + calendar skills (Juno's morning briefing reads
  Mail — **do not run this during the 07:00 briefing**), the Homepage widget,
  phones' DAV sync, the whiteboard front-end. None need action; all reconnect.
  `notify_push` reconnects on its own once the server answers.
- **The whiteboard is internet-facing** (`envoy-external`). This plan rolls one
  Pod behind an UNCHANGED HTTPRoute/Gateway, so `shared:` stays `[]` — but if a
  plan that perturbs `envoy-external` or its listeners is ever scheduled into
  the same slot, §4 gate 5d stops being a valid measurement and `gateway/envoy`
  must be added to `touches.shared` along with a conflict against that plan. No
  such plan is windowed today.
- **CODE restart.** `richdocumentscode` is replaced in §3.2 — any office
  document open in a browser at that moment reloads. Say so before starting.
- **Not restarted, deliberately:** `nextcloud-redis` (own deny rule; sessions
  survive, §1.5) and `nextcloud-mariadb` (written, not bounced). A window agent
  that sees redis client churn in metrics during §3.4 is seeing reconnects, not
  a restart — `kubectl -n office get pod -l app=nextcloud-redis` shows the same
  pod, restarts 0.
- **`conflicts_with: bitnamilegacy-exit-nextcloud-db`** — same `helmrelease.yaml`,
  same Deployment restart, and that plan replatforms the very DB this plan dumps
  from. It is `blocked`/unwindowed today; if it is revived, run this plan first
  (a smaller, reversible change on the known server) and let that one start from
  34.0.4 / chart 9.3.0. The reciprocal ref lives on that plan too (2026-09-15) —
  the validator does not enforce reciprocity.
- **`conflicts_with: nextcloud-mcp-0.187.1`** (draft, `office`, 30 min, Flux
  `dependsOn: nextcloud`) — reciprocal of that plan's declaration. Its
  verification calls this server, so a 2-5 min 503 during §3.4 would fail its
  checks, and the namespace-wide §2.5 silence would hide its rollout alerts.
  Never the same slot. Different slots of one weekend are fine in either order —
  its `nextcloud-server-unchanged` premise tolerates `34.0.x` and it re-takes
  its baselines the same day. It is a MINOR hop held by the `*nextcloud-mcp*`
  `max: patch` deny rule (PLAN lane, HUMAN-GATED): it will NOT ride Step 0.
- **`nextcloud-whiteboard-2.0.0` is SUPERSEDED, not conflicting** (§1.6). It must
  NOT be scheduled: running it after this plan would be a no-op at best (its own
  premise `live-whiteboard-backend-is-still-v1.5.9` would FAIL, which is the
  correct outcome) and its §2.3 branch logic assumes it owns the backend leg.
  The operator is retiring the file.
- **Other same-namespace neighbours** (mealie, paperless-*): no shared resource,
  but do not run them *in parallel* in the same slot — the §2.5 silence is
  namespace-wide and would mask their rollout noise too. Sequential is fine.
- **Step 0 of the same window** touches nothing in this plan's blast radius: the
  `*nextcloud*` deny rule keeps nextcloud, notify-push, nextcloud-redis and the
  whiteboard backend out of the safe lane, and nextcloud-mcp minor hops are
  PLAN-lane (above).
- **Longhorn housekeeping.** The two §2.4 snapshots are removed by the 02:30
  `global-snapshot-cleanup` the next night; that is intended (the dump and the
  nightly backup are the durable floor). Do not "fix" it by adding retain rules.
- **Timing math is a premise.** `startup-probe-budget-is-unchanged` exists
  because the entire §3.2 rationale is a number; if someone raises the threshold
  before this runs, the plan still works — it just has more slack.
- **Upstream drift is now machine-checked at preflight**, not by hand
  mid-window: `chart-9.3.0-still-carries-appversion-34.0.4` reads the published
  index (F-0cd73f3f's core ask). The app-inventory half of that finding is still
  an executor gate (§2.0b(e)) because the premise runner cannot exec `occ` —
  that residue belongs to F-58f0bbab, which asks for an "upstream facts" premise
  kind, and is not solved by this plan.
