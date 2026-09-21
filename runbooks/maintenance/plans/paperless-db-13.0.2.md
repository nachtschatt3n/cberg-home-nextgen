---
plan_id: paperless-db-13.0.2
component: paperless-db
pr: null                              # No Renovate PR. The image is pinned in a plain
                                      # Deployment yaml (db-deployment.yaml), not a chart,
                                      # so it rides coverage.py's direct-bump lane. Verified
                                      # 2026-09-16: `gh pr list` shows exactly one open PR
                                      # (#212, talos), nothing for mariadb.
kind: image
current: "12.3.3"                     # live-verified 2026-09-16: deployment image AND
                                      # SELECT VERSION() = 12.3.3-MariaDB-ubu2404, datadir
                                      # marker 12.3.3-MariaDB (binary and marker in lockstep)
target: "13.0.2"
update_type: major                    # MariaDB server major: 12.3 -> 13.0
risk: high                            # one-way datadir conversion on the household document
                                      # library, which has NO second copy (see §1.4)
est_duration_min: 60                  # same proven shape as paperless-db-12.3.3, which ran
                                      # this exact procedure end-to-end in that budget
needs_reboot: false
touches:
  namespaces: [office]
  resources:
    - deployment/paperless-db                   # image bump
    - pvc/paperless-db-data                     # datadir converted IN PLACE (one-way)
    - deployment/paperless-ngx                  # quiesced (scale 0) for the duration
    - kustomization/paperless-ngx               # suspended during the quiesce
    - helmrelease/paperless-ngx                 # suspended during the quiesce (no edit)
  shared: []                                    # own longhorn-static volume; no shared infra.
                                                # NOT `storage`: this perturbs one volume, not
                                                # the Longhorn control plane.
depends_on: []
conflicts_with: [bitnamilegacy-exit-nextcloud-db, paperless-ngx-3.2.0,
                 external-dns-unowned-cnames, jellyfin-12.1, media-naming-p3,
                 n8n-2.39.8, nextcloud-34.0.4, nocodb-2026.09.0]
                                      # ROLLBACK-CLASS STACKING, added 2026-09-21 as a
                                      # consequence of unblocking this plan. Until today it
                                      # was `blocked`, so it was not in the live
                                      # backup-restore set and the set was fully declared at
                                      # 15/15 pairs. Moving to `draft` made it the SEVENTH
                                      # live plan of that class and created six new pairs,
                                      # all undeclared — measured through
                                      # maintenance-plan.py's own load_plans(), which is the
                                      # only reader that carries rollback_class.
                                      # Two backup-restore rollbacks in one slot leave no
                                      # rollback capacity for either, and this plan's
                                      # rollback is a restore-from-dump on a database with
                                      # no second copy. Declared once per pair:
                                      # window-scheduler.py:253-260 honours the field in
                                      # EITHER direction, so the six counterparts need no
                                      # reciprocal entry.
                                      # Scheduling metadata only — no step, gate or rollback
                                      # procedure is touched by this edit.
                                      # TWO guards.
                                      # (1) bitnamilegacy-exit-nextcloud-db — CARRIED FORWARD
                                      # from paperless-db-12.3.3
                                      # and re-checked 2026-09-21 against every other plan's
                                      # frontmatter. The guard is still REAL: both plans are
                                      # namespace `office`, both risk:high, both
                                      # rollback_class:backup-restore, both are one-way MariaDB
                                      # datadir operations, and 60 + 80 = 140 min does not fit
                                      # a 90-min window. nextcloud-db is `blocked` with
                                      # window:null, so the collision is LATENT, not live —
                                      # but nothing else would stop them sharing a slot if it
                                      # unblocks. NOTE: reciprocity is one-sided — that plan
                                      # lists `paperless-db-12.3.3` (now executed), not this
                                      # plan_id. --validate checks refs resolve, not
                                      # reciprocity, so the other side needs updating by
                                      # whoever next touches it (reported, not edited here).
                                      # (2) paperless-ngx-3.2.0 — ADDED 2026-09-21. That plan
                                      # (written 2026-09-20, after this one) already declares a
                                      # HARD conflict against this plan_id, and it touches the
                                      # SAME objects: deployment/paperless-ngx,
                                      # kustomization/paperless-ngx, helmrelease/paperless-ngx
                                      # AND deployment/paperless-db (its migration 0026). Its
                                      # verification needs a live, writable paperless-db, which
                                      # §3.1 here scales away for the whole window. Never the
                                      # same slot, in either order. This side was the missing
                                      # half of that pair; the pair is now mutual.
security_ref: null                    # version-currency driver, not a security driver —
                                      # same as paperless-db-12.3.3. See §1.5 for the one
                                      # security-adjacent interaction (cited by id only).
capability_change: false              # same DB service, same app behaviour intended
rollback_class: backup-restore        # NOT git-revert. See §5 — reverting the manifest alone
                                      # points a 12.3.3 binary at a 13.0-converted datadir,
                                      # which is worse than doing nothing.
backup_gate: "logical dump taken in-window with --default-character-set=utf8mb4, proven by ONE FAIL-CLOSED script under set -euo pipefail (§3.2) that exits non-zero on: a missing '-- Dump completed' trailer, <74 CREATE TABLE, <10 MB, a 4-byte lead-byte scan that fails its own POSITIVE CONTROL, or a dump with zero 4-byte content — plus per-table row counts, the 4-byte canary and the documents_document baseline captured in §3.3, all BEFORE the image bump"
finding_refs: [F-1c080cce]            # CORRECTED 2026-09-21 (was []). The sweep HAS now filed
                                      # it: `policy-cli.py finding show F-1c080cce` returns
                                      # section `version`, severity `critical`, status
                                      # `unchanged`, resolved_at None (i.e. OPEN), title
                                      # "paperless-db: image mariadb 12.3.3 → 13.0.2 (major)",
                                      # first_seen 2026-09-17 02:20, last_seen 2026-09-21 17:00.
                                      # WHY THE ORIGINAL NOTE READ IT WRONG, so the next reader
                                      # does not repeat it: the finding_id is derived from a
                                      # fingerprint that is STABLE PER COMPONENT+KIND, so the
                                      # resolved 11.8.9 -> 12.3.3 rows and this open 12.3.3 ->
                                      # 13.0.2 row share the SAME id F-1c080cce. `finding list`
                                      # therefore shows both a `resolved` and an `unchanged`
                                      # row under one id; the note keyed on the resolved one
                                      # and concluded no open finding existed. Check
                                      # status/resolved_at on the NEWEST row, not the id.
                                      # This is a PLAN-lane critical: without the ref here the
                                      # plan-or-page join leaves it reading as unplanned and it
                                      # pages the operator after plan_sla_days.
status: vetted                        # VETTED 2026-09-21. An independent plan-reviewer
                                      # returned ready-for-go on the SECOND pass, after B1-B3
                                      # were repaired, and then a further pass cleared six
                                      # non-blocking items — including the one that mattered:
                                      # $DUMP was set only inside §3.2's script block but used
                                      # by §5.4's destructive restore, so in a fresh shell hours
                                      # later it expanded EMPTY. That is a defect in the only
                                      # rollback for a database with no second copy, and it
                                      # bites exactly when everything else has already failed.
                                      # STILL REQUIRED BEFORE IT RUNS: an operator GO recorded
                                      # against sat-attended:2026-10-24 specifically. The
                                      # override of the RECOMMENDATION block is a decision to
                                      # proceed at all; it is NOT a window GO, and this plan is
                                      # HUMAN-GATED so nothing will run it unattended.
                                      # PREVIOUSLY: unblocked 2026-09-21 by an explicit operator override of
                                      # the RECOMMENDATION block (annotated in place below, not
                                      # deleted). §2's ABORT list keys on exactly that override
                                      # existing, so it is recorded HERE and in the block, not
                                      # only in conversation.
                                      # WHY `draft` IS NOW CORRECT, AND WAS NOT BEFORE:
                                      # F-61d8147e records that a plan stopped by a prose header
                                      # while its machine-readable status says `draft` is a
                                      # plan-state hygiene defect — the two must not disagree.
                                      # While the recommendation stood, `blocked` was the only
                                      # honest value. The recommendation is now overridden, so
                                      # the prose and the status agree again and `draft` is the
                                      # accurate state: written, not yet reviewed.
                                      # NOT `vetted`: no plan-reviewer has passed this since the
                                      # override, and the scheduler ignores `draft`, so nothing
                                      # can claim a slot before that review.
                                      # WHAT THE OPERATOR ACCEPTED, recorded so the trade is not
                                      # re-litigated from memory: MariaDB 13.0 is a ROLLING
                                      # release whose community support ends 2026-12-31, against
                                      # 2029-06-12 for the 12.3 LTS line; upstream ships no patch
                                      # releases on an innovation line, so staying patched means
                                      # a further one-way datadir migration each quarter; and
                                      # MARIADB_AUTO_UPGRADE=1 is live, so the conversion is
                                      # irreversible from the first second the new image starts,
                                      # with no look-first step and no abort point, on a database
                                      # with no second copy. The operator was shown all of this
                                      # and chose to proceed.
window: "sat-attended:2026-10-24"      # OPERATOR-CHOSEN 2026-09-21. The first slot that can
                                      # take it: 0 of 70 schedulable minutes used, and it holds
                                      # none of the six backup-restore plans this one now
                                      # conflicts with. Every earlier slot fails on one axis or
                                      # the other — 09-26/09-27/10-03/10-10 on capacity,
                                      # 10-04/10-11/10-17/10-18 because each already holds a
                                      # backup-restore plan. At 60 min it fits ALONE, with 10
                                      # minutes spare; it must not share the slot.
                                      # SUPERSEDED NOTE: the scheduler assigns; nothing should claim a slot
                                      # while the recommendation stands
premises:
  # SCOPE NOTE (inherited from paperless-db-12.3.3, re-confirmed against
  # plan-premises.py on 2026-09-16): a premise may not `kubectl exec` — the
  # runner refuses anything outside its read-verb allowlist. So the live
  # COLLATION and 4-byte-content assertions cannot live here; they live in §2,
  # which runs in-window and does query the database. Every command below was
  # executed on 2026-09-16 and returned the expected value.
  - id: still-on-12.3.3
    why: >-
      The migration is 12.3.3 -> 13.0.2. If the cluster already moved, the dump
      baseline, the rollback target and this plan's entire premise are wrong.
      Measured 2026-09-16: mariadb:12.3.3.
    run: kubectl get deploy -n office paperless-db -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "mariadb:12.3.3"
  - id: auto-upgrade-is-armed
    why: >-
      THE most load-bearing fact in this plan, and the difference from the
      12.3.3 migration. MARIADB_AUTO_UPGRADE=1 is ALREADY in the manifest and
      live on the pod (it was added BY the 12.3.3 plan). So the 13.0.2 container
      runs mariadb-upgrade on its FIRST start, automatically — the one-way
      datadir conversion happens the instant the new image is pulled, with no
      look-first option and no abort point. If this ever reads anything but "1",
      the failure mode inverts to a 13.0 binary silently serving 12.3-format
      system tables, and §3 must be re-planned. Measured 2026-09-16: "1".
    run: kubectl get deploy -n office paperless-db -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="MARIADB_AUTO_UPGRADE")].value}'
    expect_exact: "1"
  - id: restore-path-exists
    why: >-
      rollback_class is backup-restore and there is no second copy of this
      database (the pre-replatform volume paperless-mariadb was DELETED
      2026-08-30, aa825d8f). A restore path must be proven to EXIST before
      anything is touched — this premise fails closed if no Completed backup
      CR for paperless-db-data is present. Measured 2026-09-16: 8 Completed
      backups, newest 2026-09-15T03:03:17Z, 620756992 bytes. FRESHNESS is
      asserted separately in §2 because it is time-relative.
    run: kubectl get backups.longhorn.io -n storage -o jsonpath='{.items[?(@.status.volumeName=="paperless-db-data")].status.state}'
    expect_contains: "Completed"
  - id: backups-still-scheduled
    why: >-
      A restore path that has stopped being refreshed is a stale one. The volume
      must still be in the default recurring-job group that CronJob
      storage/daily-backup-all-volumes (owned by the RecurringJob of the same
      name) drives at 03:00. Measured 2026-09-16: label present, enabled.
    run: kubectl get volume -n storage paperless-db-data -o jsonpath='{.metadata.labels}'
    expect_contains: "recurring-job-group.longhorn.io/default"
  - id: charset-invariant-intact
    why: >-
      The utf8mb4 server pin is what stops a repeat of the OperationalError 1366
      that broke every mail-processing cycle before 9cb10b76 (2026-08-30). It is
      also why the dump's 4-byte proof in §3.2 is mandatory. If these args ever
      go missing, the charset invariant is already broken and a major upgrade is
      the wrong thing to be doing. Measured 2026-09-16: all three args present.
    run: kubectl get deploy -n office paperless-db -o jsonpath='{.spec.template.spec.containers[0].args}'
    expect_contains: "utf8mb4_general_ci"
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/mariadb-major-upgrade.md        # see §1.6 — applicability is WRONG for this
                                              # component (F-6d08960a); follow the executed
                                              # 12.3.3 plan where they disagree
  - docs/sops/postgres-major-upgrade.md       # sibling precedent for the SHAPE of a major
                                              # DB upgrade in this household
  - docs/sops/backup.md
  - docs/sops/paperless.md
  - docs/sops/longhorn.md
  - docs/sops/storage-safety.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-09-16"
---

> ## ✅ OVERRIDDEN BY THE OPERATOR, 2026-09-21 — the recommendation below stands as the record of what was traded away
>
> **The operator was shown this block's full argument — the LTS→rolling move, the
> 2026-12-31 support end against 2029-06-12, the absence of patch releases on an
> innovation line, the quarterly one-way migrations that follow, the
> irreversibility from first container start, and the finding of no upside — and
> chose to proceed.** §2's ABORT condition "the operator has not explicitly
> overridden the RECOMMENDATION block" is therefore satisfied, and `status:` moved
> from `blocked` to `draft`.
>
> Nothing below is deleted. It remains the reasoning this decision overrode, so a
> future reader sees the cost that was accepted rather than an unexplained bump.
> Re-verified 2026-09-21 before unblocking: premises PASS (5), live image
> `mariadb:12.3.3`, `MARIADB_AUTO_UPGRADE=1` armed, newest Completed backup for
> `paperless-db-data` 2026-09-21T03:05:10Z (620756992 bytes) — inside §2's 26h
> freshness bound.
>
> STILL REQUIRED before this runs: a plan-reviewer pass (`draft` → `vetted`), a
> window that does not stack it with another `backup-restore` plan, and an
> operator GO recorded for that specific window.
>
> ## ⛔ RECOMMENDATION (ORIGINAL, OVERRIDDEN): DO NOT EXECUTE — this is an operator DECISION, not a routine bump
>
> **This plan is written, complete and executable, and it recommends against
> running itself.** The window agent must not schedule it; the decision belongs
> to the operator.
>
> The bump is not "12.3.3 → a newer 12.3.x". It moves the household's document
> database **off the LTS line and onto a rolling release**:
>
> | | MariaDB 12.3 (now) | MariaDB 13.0 (target) |
> |---|---|---|
> | Release type | **LTS** | **rolling / innovation** |
> | Released | 2026-05-28 | 2026-09-15 (**1 day** before this plan) |
> | Community support ends | **2029-06-12** | **2026-12-31** |
> | Further patch releases? | yes, for ~3 more years | **no** — upstream's model is "no patch version releases of an innovation release after GA … users are supposed to upgrade to the next minor innovation release" |
>
> So executing this trades ~33 months of supported life for ~3.5 months, and
> commits us to a **quarterly one-way datadir migration** (13.0 → 13.1 → 13.2 …)
> just to stay patched — on a database that has **no second copy**.
>
> The migration is **irreversible** and, because `MARIADB_AUTO_UPGRADE=1` is
> already live, it is **irreversible from the first second the new image starts**.
>
> **There is no upside to buy this with.** 12.3.3 is the newest tag on the LTS
> line (verified on Docker Hub 2026-09-16 — no 12.3.4 exists), it is current and
> fully supported, and none of 13.0's features (`TYPE .. IS REF CURSOR`,
> `innodb_log_archive`, optimizer-trace additions) is used by paperless-ngx.
>
> **Recommended instead:** stay on 12.3.3 LTS and revisit at the **next LTS**
> (upstream's stated model is that the `.3` of each major is LTS, so 13.3 —
> expected mid-2027, date not yet announced by upstream). That is one LTS→LTS hop,
> exactly the shape of the 11.8→12.3 migration that already succeeded here.
>
> **If the operator decides to go anyway**, §2–§6 are the real, executable
> procedure, and every command in them names an object verified to exist.

# paperless-db: mariadb 12.3.3 → 13.0.2 (LTS → ROLLING major)

## 1. Summary & why held

Held by the version gate as a major (`runbooks/version-check-current.md`,
generated 2026-09-16 03:42, row: `paperless-db | office | 12.3.3 → 13.0.2 |
🔴 MAJOR`), and additionally by the standing deny rule `*mariadb*`
(`max: patch`) in `runbooks/auto-update-policy.yaml`: *"A DB-engine bump is
never unattended-safe."* Both holds are correct.

This plan follows `runbooks/maintenance/plans/paperless-db-12.3.3.md` — the
**executed, verified** 11.8.9 → 12.3.3 plan for this exact component — as its
template. Where the two differ, it is called out explicitly below.

### 1.1 What the major boundary actually requires

Established from MariaDB's own documentation and release data, not by analogy:

- **`mariadb-upgrade` must run**, and here it runs *automatically*. The official
  image only runs it when `MARIADB_AUTO_UPGRADE=1` — which the 12.3.3 plan added
  and which is **already live** (premise `auto-upgrade-is-armed`). Evidence it
  works on this deployment: the 12.3.3 roll logged *"Major version upgrade
  detected from 11.8.8-MariaDB to 12.3.3-MariaDB"* and completed all 8 phases;
  a later restart logged *"MariaDB upgrade not required"* (measured again
  2026-09-16 — still the current tail).
- **This INVERTS the 12.3.3 plan's main risk.** There, the danger was that
  `mariadb-upgrade` would be *skipped* (SOP failure mode 1). Here the env var is
  already armed, so the danger is the opposite: the conversion runs the moment
  the pod starts. **There is no "start it and look" step, and no abort point
  after the image lands.** That single fact is the biggest gotcha in this file.
- **Incompatible changes 12.3 → 13.0** are modest, and upstream has published
  **no `Upgrading from MariaDB 12.3 to MariaDB 13.0` guide** (checked
  2026-09-16 — the docs site's upgrade-path index has 11.8→12.3 but no 12.3→13.0
  page; the generic "Upgrading Between Major MariaDB Versions" page applies).
  From the 13.0 changes page and the 13.0.2 release notes:
  - `binlog_row_event_max_size` default raised to 64 KB (no binlog consumer here
    — single server, no replication).
  - `PERFORMANCE_SCHEMA` digests switch to `XXH3_128`.
  - New `innodb_log_archive` (opt-in, off by default).
  - New SQL surface: `TYPE .. IS REF CURSOR`, `RECORD` routine params,
    `UPDATE ... RETURNING`. None used by paperless's Django schema.
  - No removed/renamed system variables that this Deployment sets. Our three
    args (`--character-set-server`, `--collation-server`,
    `--innodb-file-per-table`) are all still valid in 13.0.
  **The breaking change is not a SQL incompatibility — it is the support
  lifecycle.** See the RECOMMENDATION block.
- **Base image changes too.** `12.3.3` publishes a `-noble` variant (Ubuntu
  24.04; the live server string is `12.3.3-MariaDB-ubu2404`). `13.0.2` publishes
  no `-noble` — its variants are bare, `-resolute`, `-ubi`, `-ubi10`. So this
  bump also carries an OS base jump underneath the DB major. Verified against
  the Docker Hub tag list 2026-09-16.

### 1.2 Is the data directory one-way? YES — and the rollback cannot be a git revert

Upstream: *"an in-place downgrade to a previous major version is only allowed if
you have not yet executed `mariadb-upgrade` on the new version"*, because the
`mysql` schema's privilege and system tables change between majors. With
`MARIADB_AUTO_UPGRADE=1` live, `mariadb-upgrade` **always** runs on first start.
Therefore the datadir is one-way **from the first start of 13.0.2**, and:

> **Reverting `db-deployment.yaml` to `mariadb:12.3.3` is NOT a rollback.** It
> points the old binary at a 13.0-converted datadir. That is worse than doing
> nothing. `rollback_class: backup-restore` is set for this reason, and §5 is a
> restore *procedure*, not a revert line.

### 1.3 Does paperless itself constrain the DB version?

Checked upstream (paperless-ngx docs, `setup`): it states *"For new
installations, it is recommended to use PostgreSQL as the database backend"* and
that `PAPERLESS_DBENGINE` must be one of `postgresql`, `mariadb`, `sqlite`.
It declares **no minimum and no maximum MariaDB version**, and no MariaDB
caveat beyond the PostgreSQL preference. Our wiring (`helmrelease.yaml`:
`PAPERLESS_DBENGINE: mariadb`, `PAPERLESS_DBHOST: paperless-db`,
`PAPERLESS_DBPORT: 3306`) is unaffected by the server major.

**So paperless does not block 13.0.2 — but it does not ask for it either.**
Nothing in the application needs this bump; there is no paperless feature, fix
or requirement on the other side of it.

### 1.4 Blast radius, and why `risk: high`

`paperless-db` is the document library's only database, and — per
`docs/sops/paperless.md` §2 — **there is no rollback floor: the live DB is the
only copy.** The pre-replatform volume `paperless-mariadb` was deleted
2026-08-30 (`aa825d8f`). Live baseline measured 2026-09-16:

- **970 documents** (`documents_document`), 74 tables in `paperless`, all
  `utf8mb4_general_ci`, 225 MB used of a 4.9 GB volume (ample headroom for the
  entrypoint's system-table backup).
- The **4-byte content canary is live**: 1 row in
  `paperless_mail_processedmail` has `HEX(subject) LIKE '%F09F%'` — the emoji
  subject class that caused `OperationalError 1366` before the utf8mb4
  conversion. This is why §3.2's 4-byte dump proof is mandatory, not optional.
- Volume `paperless-db-data`: `attached`/`healthy`, `longhorn-static`, PV
  reclaim **`Retain`**, driver `driver.longhorn.io`, 8 Completed backups, newest
  **2026-09-15T03:03:17Z**.

Downstream of an outage: the paperless web UI + API, the scanner→SMB→validator→
consume pipeline, email ingestion, the native-AI suggestions path, and the ARAG
bill push (`health-insurance-agent`). All ingestion **buffers** upstream, so a
quiesce loses nothing — it delays.

### 1.5 One security-adjacent interaction (cited by id only, no detail here)

`security-check.py` rates a fixable-CVE finding actionable only when
`_newer_upstream_tag_exists()`. A newer tag (13.0.2) now exists, and **the flip
this section predicted has since happened** — so the ids are updated here to
match the DB rather than sending a reader after a closed row (verified against
the findings DB 2026-09-21):

- **F-fbbeecab** — the standing `[AR-029] already on the newest upstream tag`
  acceptance on the `mariadb:12.3.3` image — is now **`resolved`** (resolved
  2026-09-17). Do not chase it; it is closed.
- **F-c83c3494** is the row that replaced it and is **open** (first seen
  2026-09-17, the same cycle F-fbbeecab closed). It is the "newer upstream tag
  available, bump the image" finding on that image, and it will read as pressure
  to take this bump.

It should not:

- The household rule is *bump, never rebuild* — but it does not say *bump onto
  an unsupported line*. 13.0 stops receiving patches at 2026-12-31, so bumping
  there **worsens** the long-run patch posture rather than improving it.
- Per CLAUDE.md, quote the **contextual** tier, not the raw scanner count:
  `paperless-db` is a **ClusterIP** Service with no HTTPRoute and no external
  exposure, so it is not external-unauth and these do not reach this household's
  `critical` tier.
- Detail stays on the finding record. Nothing about it is restated in this file.

### 1.6 Which document I followed, and a repo correction owed

I followed **`runbooks/maintenance/plans/paperless-db-12.3.3.md`** (executed,
verified) as authoritative, **not** `docs/sops/mariadb-major-upgrade.md`.

That SOP is titled *"MariaDB Major Upgrade (Bitnami chart)"* and its Description
still claims it applies to `office/paperless-ngx` "via the Bitnami entrypoint".
**That is wrong for this component** and is already filed as **F-6d08960a**:
`paperless-db` runs the Docker Official image, and its working path is
`MARIADB_AUTO_UPGRADE` + the utf8mb4/4-byte content proof. Concretely, the SOP's
paths do not exist here — it names `/bitnami/mariadb/data/mysql_upgrade_info`,
whereas this deployment's marker is **`/var/lib/mysql/mariadb_upgrade_info`**
(read live 2026-09-16: `12.3.3-MariaDB`). Following the SOP literally would
`cat` a nonexistent file and read the empty result as… whatever the reader
wanted.

Two parts of that SOP **do** still apply and are kept below: the socket/`--skip-ssl`
invocation for a manual `mariadb-upgrade`, and the
`--default-character-set=utf8mb4` dump rule (whose omission silently corrupted a
Nextcloud migration's rollback floor on 2026-08-19).

> **Material for F-6d08960a** (noted here so it is not lost when the 12.3.3 plan
> file is retired per `plans/README.md`): the Docker-Official path that SOP is
> missing is exactly §1.1 + §3.2 + §3.6 of this file — `MARIADB_AUTO_UPGRADE=1`
> semantics, the `/var/lib/mysql/mariadb_upgrade_info` marker path, and the
> positive-control 4-byte dump proof. **This plan does not edit docs**; that is
> the finding's own work item.

## 2. Pre-checks

Run `plan-premises.py paperless-db-13.0.2 --require-premises` first — it fails
closed. It cannot cover the gates below: a premise may not `kubectl exec`, and
its allowlist has no `curl` and no `date` (`runbooks/plan-premises.py`,
`ALLOWED` / `ALLOWED_BARE`), so the SQL, the freshness arithmetic and the
registry check must live here.

**These gates are FAIL-CLOSED, not eyeball.** They were eyeball-only until
2026-09-21 and every one of them merely PRINTED; the forms below were each
driven to a red with a deliberately broken input on this Mac before being
written down (see the dry-test notes inline). Run the whole block; a non-zero
exit means STOP, and nothing in §3 has happened yet.

*Portability, measured on this Mac (macOS/zsh) 2026-09-21, not assumed:*
`date -d` does not exist (`date: illegal option -- d`) — the freshness gate uses
BSD `date -u -j -f`. There is **no `timeout` and no `gtimeout`** binary, and no
`crane`/`skopeo`/`docker` — hence `curl --max-time` for the registry gate.

```bash
# Informational first (read, don't gate — a WARNING here is a judgement call):
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
flux get helmreleases -A   | awk 'NR==1 || $5 != "True"'
kubectl -n office get pods -l app=paperless-db          # expect 1/1 Running, 0 restarts
kubectl -n office exec deploy/paperless-db -- df -h /var/lib/mysql   # measured: 225M/4.9G
```

```bash
set -euo pipefail          # EVERY gate below aborts the run. Do not drop this line.

# --- Gate 1: the component is still where this plan thinks it is -------------
IMG=$(kubectl -n office get deploy paperless-db -o jsonpath='{.spec.template.spec.containers[0].image}')
echo "image=$IMG"
[ "$IMG" = "mariadb:12.3.3" ] || { echo "ABORT: image is $IMG, this plan assumes mariadb:12.3.3"; exit 1; }

# --- Gate 2: volume attached AND healthy (computed, not read off a table) ----
VS=$(kubectl get volume -n storage paperless-db-data -o jsonpath='{.status.state}/{.status.robustness}')
echo "volume=$VS"
[ "$VS" = "attached/healthy" ] || { echo "ABORT: volume is $VS, expected attached/healthy"; exit 1; }
# Dry-tested 2026-09-21: returns "attached/healthy" -> GATE-PASS; any other
# state or an empty status fails the string compare and exits 1.

# --- Gate 3: the nightly backup is FRESH (<26h) ------------------------------
# Reads the Backup CRs directly — the authoritative source — so the documented
# lastBackupAt lag (docs/sops/backup.md) cannot manufacture a false abort.
LB=$(kubectl -n storage get backups.longhorn.io \
       -o jsonpath='{range .items[*]}{.status.volumeName}{" "}{.status.state}{" "}{.status.backupCreatedAt}{"\n"}{end}' \
     | awk '$1=="paperless-db-data" && $2=="Completed" {print $3}' | sort | tail -1)
echo "newest Completed backup=[$LB]"
BSEC=$(date -u -j -f "%Y-%m-%dT%H:%M:%SZ" "$LB" "+%s" 2>/dev/null) \
  || { echo "ABORT: no parseable Completed backup for paperless-db-data"; exit 1; }
AGE_H=$(( ( $(date -u +%s) - BSEC ) / 3600 ))
echo "backup age=${AGE_H}h"
[ "$AGE_H" -lt 26 ] || { echo "ABORT: newest backup is ${AGE_H}h old (bound 26h)"; exit 1; }
# Dry-tested 2026-09-21 against the live CR (2026-09-21T03:05:10Z -> age 15h,
# PASS) and against an EMPTY timestamp, which is the case that matters: the
# `date` parse fails, the `||` branch fires, exit 1. It does NOT silently
# compute an age from an empty string.

# --- Gate 4: COLLATION + table count (the assertion premises cannot make) ----
COLL=$(kubectl -n office exec deploy/paperless-db -- sh -c \
  'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" -N -B -e \
   "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=\"paperless\";
    SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=\"paperless\" AND table_collation NOT LIKE \"utf8mb4%\";"')
NT=$(echo "$COLL" | head -1 | tr -d '[:space:]')
NB=$(echo "$COLL" | tail -1 | tr -d '[:space:]')
echo "paperless tables=$NT  non-utf8mb4=$NB"
[ -n "$NT" ] && [ -n "$NB" ] || { echo "ABORT: empty collation query result — the gate could not measure"; exit 1; }
[ "$NT" -eq 74 ] || { echo "ABORT: $NT tables in paperless, expected 74"; exit 1; }
[ "$NB" -eq 0 ]  || { echo "ABORT: $NB paperless tables are NOT utf8mb4_* — that is a 9cb10b76 regression; fix that first, do not upgrade over it"; exit 1; }
# Dry-tested 2026-09-21 against the live DB: NT=74, NB=0 -> GATE-PASS. The
# empty-output control (a query that returns nothing, e.g. the exec failing)
# hits the `-n` check and exits 1 rather than letting `[ "" -eq 74 ]` decide.

# --- Gate 5: the TARGET TAG IS PULLABLE — and this must pass BEFORE §3.1 -----
# WHY HERE: db-deployment.yaml uses `strategy: Recreate`, so the working 12.3.3
# pod is torn down BEFORE the new image is pulled. An unpullable tag therefore
# leaves the household document DB with NO pod, mid-window, after the app is
# already quiesced. Resolve the manifest digest first.
TOK=$(curl -s --max-time 20 "https://auth.docker.io/token?service=registry.docker.io&scope=repository:library/mariadb:pull" \
      | /usr/bin/python3 -c 'import sys,json
try:
    print(json.load(sys.stdin)["token"])
except Exception:
    pass' || true)
[ -n "$TOK" ] || { echo "ABORT: no registry token"; exit 1; }
# The try/except + `|| true` make the NEXT line the thing that fails, rather than
# the assignment. Without them, under `set -euo pipefail`, a failed curl or a
# non-JSON body kills the block at the assignment with a raw Python traceback and
# the `[ -n "$TOK" ]` check is unreachable — it fails CLOSED either way, so this
# is a consistency/legibility fix, not a safety fix. Dry-tested 2026-09-21 against
# four fixtures: valid token -> exit 0; empty body, non-JSON body, and well-formed
# JSON with no "token" key -> all print "ABORT: no registry token", exit 1. The
# unfixed form on the same non-JSON fixture exits 1 with a JSONDecodeError
# traceback and never prints its own message (measured).
DIG=$(curl -s --max-time 20 -D - -o /dev/null \
        -H "Authorization: Bearer $TOK" \
        -H 'Accept: application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.list.v2+json' \
        "https://registry-1.docker.io/v2/library/mariadb/manifests/13.0.2" \
      | awk 'tolower($1)=="docker-content-digest:"{print $2}' | tr -d '\r')
echo "digest=$DIG"
case "$DIG" in
  sha256:*) echo "PULLABLE: mariadb:13.0.2 -> $DIG" ;;
  *) echo "ABORT: mariadb:13.0.2 has no resolvable manifest digest — do NOT quiesce"; exit 1 ;;
esac
# Dry-tested 2026-09-21, WITH A NEGATIVE CONTROL: the real tag returned
# sha256:d4fdec0510ad498e4f3127da30a99df3745bd6d5e611ae6ac5f76403d9284a8d
# (http 200), and `13.0.2-nope` returned an empty digest (http 404) -> exit 1.
# So this gate can fail, and it fails on exactly the condition it names.
# LIMIT, stated honestly: this proves the tag resolves from THIS Mac, not that
# the node's containerd can reach Docker Hub right now. It cannot be stronger
# without creating a pod, which is a cluster mutation and not a pre-check.
```

**ABORT this plan if** any gate above exits non-zero, **or** if the operator has
not explicitly overridden the RECOMMENDATION block (that one is a human fact,
recorded in the banner above and in `status:` — it cannot be computed here).

## 3. Steps

All cluster writes are executed by the window agent / cberg-agent. The manifest
change is GitOps.

**3.1 Quiesce the app** (scanner SMB inbox and the GMX mailbox buffer upstream —
documents queue, nothing is lost):

> **§2 gate 5 (target tag pullable) MUST have passed before this step.** This
> Deployment uses `strategy: Recreate`: the working 12.3.3 pod is destroyed
> before the 13.0.2 image is pulled, so an unpullable tag leaves the document
> database with no pod at all, with the app already scaled to 0.

```bash
flux suspend kustomization paperless-ngx -n office   # ns office, NOT flux-system
flux suspend helmrelease   paperless-ngx -n office
kubectl -n office scale deploy/paperless-ngx --replicas=0
kubectl -n office wait --for=delete pod -l app.kubernetes.io/name=paperless-ngx --timeout=120s
```

(Label verified live 2026-09-16: the pod template carries
`app.kubernetes.io/name=paperless-ngx`; `paperless-db` carries `app=paperless-db`.)

**3.2 Logical dump — the rollback floor (non-negotiable):**

**THIS BLOCK IS THE ONLY ROLLBACK.** `rollback_class: backup-restore`, and with
`MARIADB_AUTO_UPGRADE=1` live there is no abort point after the image lands. So
it is ONE script under `set -euo pipefail` in which **every** assertion exits
non-zero. It was fail-open until 2026-09-21 — every check was
`... || echo "ABORT"` (`echo` exits 0), a bare `grep -c` that printed a number
and asserted nothing, an `ls -lh`, and byte-scans that printed `0` or `1` and
carried on. A dump truncated by a reset `kubectl exec` stream, or one that had
silently lost its 4-byte content, passed all of it — and the run went on to
convert the datadir with a corrupt rollback floor.

```bash
set -euo pipefail

mkdir -p ~/backups/paperless-db && chmod 0700 ~/backups/paperless-db
DUMP=~/backups/paperless-db/paperless-db-pre-13.0.2-$(date +%Y%m%d%H%M).sql

# --routines --events: cheap insurance. --all-databases does NOT imply them, and
# a rollback that restores tables but drops stored routines/events is a rollback
# that is quietly incomplete. They only add bytes, so the floor below still holds.
kubectl -n office exec deploy/paperless-db -- sh -c \
  'mariadb-dump --default-character-set=utf8mb4 --single-transaction --all-databases \
   --routines --events -uroot -p"$MARIADB_ROOT_PASSWORD"' > "$DUMP"
# ^ under `set -e` the dump's OWN exit status is now load-bearing: a failed or
#   reset exec aborts here instead of being discarded.
chmod 0600 "$DUMP"

tail -1 "$DUMP" | grep -q -- '-- Dump completed' || { echo "ABORT: dump incomplete (no '-- Dump completed' trailer)"; exit 1; }

T=$(grep -c 'CREATE TABLE' "$DUMP" || true); echo "CREATE TABLE=$T"
[ "$T" -ge 74 ] || { echo "ABORT: only $T CREATE TABLE (expect >=74)"; exit 1; }

# TARGETED assertion — the >=74 count alone is LOOSER THAN IT READS. The dump is
# --all-databases, so it also carries the ~30-40 `mysql`/`sys`/`performance_schema`
# tables; the threshold could therefore be met with only about HALF of paperless's
# own 74 tables present. Name a table that must be there, so a partial dump cannot
# satisfy the count:
grep -qE '^CREATE TABLE `?documents_document`?[^a-zA-Z0-9_]' "$DUMP" \
  || { echo "ABORT: dump has no paperless documents_document table — partial dump, NOT a valid rollback"; exit 1; }

S=$(wc -c < "$DUMP" | tr -d ' '); echo "bytes=$S"
[ "$S" -gt 10000000 ] || { echo "ABORT: $S bytes; the 12.3.3 dump was ~25.8 MB"; exit 1; }

FB(){ /usr/bin/python3 -c "import sys;print(sum(1 for l in open(sys.argv[1],'rb') if any(0xf0<=b<=0xf4 for b in l)))" "$1"; }
printf 'ascii\nemoji \xf0\x9f\x93\x84 here\n' > /tmp/ctl.txt
[ "$(FB /tmp/ctl.txt)" -eq 1 ] || { echo "ABORT: 4-byte CHECKER broken (positive control failed) — the dump is NOT implicated; fix the checker"; exit 1; }
[ "$(FB "$DUMP")" -gt 0 ]      || { echo "ABORT: dump lost 4-byte content — NOT a valid rollback"; exit 1; }

echo "GATE PASSED — $DUMP is a usable rollback floor"
```

**Dry-tested 2026-09-21 on this Mac, under BOTH `zsh` (the executor's shell) and
`sh`, against four fixtures** — this block is the reason the plan can be trusted
to stop:

| fixture | result |
|---|---|
| a well-formed 12 MB dump with 80 `CREATE TABLE` + an emoji + the trailer | `GATE PASSED`, **exit 0** |
| the same file truncated to 500 KB (simulates a reset exec stream) | `ABORT: dump incomplete …`, **exit 1** |
| the same file with the 4-byte sequence rewritten to `?` (the 2026-08-19 Nextcloud failure, byte-for-byte) | `ABORT: dump lost 4-byte content …`, **exit 1** |
| a 39-byte stub with one `CREATE TABLE` | `ABORT: only 1 CREATE TABLE …`, **exit 1** |

Notes on the form, each of which was measured rather than assumed:

- `/usr/bin/python3` is named explicitly (3.9.6 on this Mac) — a bare `python3`
  resolves to the repo `.venv` in some shells and is absent in others.
- `|| true` on `grep -c` is deliberate: with 0 matches `grep` exits **1**, which
  under `set -e` kills the script at the *assignment* with no message of its own.
  The guard keeps the failure but makes it say why. (Exit **2** is the distinct
  *missing-file* case. Both re-measured on this Mac 2026-09-21 in `bash` and
  `zsh`: zero matches → 1, absent file → 2. An earlier revision of this note
  said a zero-match `grep -c` exits 2; it does not.)
- `wc -c < "$DUMP" | tr -d ' '` — BSD `wc` pads its output with leading spaces,
  so the `tr` gives a clean value to echo and to compare. It is **defensive
  hygiene, not a requirement**: re-measured 2026-09-21, padded `wc` output of the
  form `[     100]` passes `[ "$S" -gt … ]` unchanged in `bash`, `zsh` and `sh`,
  plain and under `set -euo pipefail`, because `test -gt` strips leading
  whitespace when coercing to an integer. Keep the `tr` — it costs nothing and
  the echoed value is cleaner — but do not repeat the earlier claim that the
  comparison *breaks* without it. That does not reproduce.

`--default-character-set=utf8mb4` is **not optional**: without it the server
transcodes 4-byte characters to `?` on the way out and the rollback floor is
corrupt when written (this destroyed a Nextcloud migration's dump on
2026-08-19).

**Why the 4-byte proof runs its POSITIVE CONTROL first** (kept — a byte-scan
that cannot prove itself is worth nothing here): a checker that cannot see
4-byte content makes its own zero meaningless, and a zero here means "STOP", so
a blind checker aborts a *good* migration. The SOP's
`LC_ALL=C grep -c $'[\xf0-\xf4]'` form is exactly that failure — it **returns 0
on macOS/BSD regardless of content** (measured 2026-09-07). Hence the Python
byte scan, and hence the control, both folded into the fail-closed block above
rather than printed beside it.

Live baseline: 1 row in `paperless_mail_processedmail` has
`HEX(subject) LIKE '%F09F%'` (re-measured 2026-09-21 — still 1). A ZERO from the
dump scan **with a PASSING control** means the dump lost 4-byte content and is
not a valid rollback.

**3.3 MEASURE the baselines** (the contents baseline for §4 — and the fix for
two gates that would otherwise false-red *after* the point of no return).

**Read this before editing anything here.** §4.4 and §4.5 used to compare
against the literals `1` and `970`, measured 2026-09-16. Ingestion runs right up
until §3.1 quiesces, so both literals drift: `documents_document` was **986** on
2026-09-21, i.e. the `970` gate was already 16 documents stale and would have
gone red on a perfectly healthy 13.0 database — routing the operator into §5
(snapshot revert, or datadir wipe + dump replay) for nothing. **Every post-check
compares to a value measured HERE, never to a number typed into this file.**

```bash
set -euo pipefail

# --- per-table row counts ----------------------------------------------------
kubectl -n office exec deploy/paperless-db -- sh -c '
  for t in $(mariadb -N -uroot -p"$MARIADB_ROOT_PASSWORD" -e \
    "SELECT table_name FROM information_schema.tables
     WHERE table_schema=\"paperless\" AND table_type=\"BASE TABLE\""); do
    echo "$t $(mariadb -N -uroot -p"$MARIADB_ROOT_PASSWORD" -e \
      "SELECT COUNT(*) FROM paperless.\`$t\`")"
  done' | sort > /tmp/paperless-db-counts-pre.txt

N=$(wc -l < /tmp/paperless-db-counts-pre.txt | tr -d ' '); echo "tables counted=$N"
[ "$N" -eq 74 ] || { echo "ABORT: baseline has $N rows, expected 74 — the baseline is unusable, and §4.3 would diff two broken files"; exit 1; }
# ^ THIS ASSERTION IS THE POINT. If the loop fails (exec killed, auth change) it
#   writes an EMPTY file; §4.3 then diffs two empty files, prints COUNTS-MATCH
#   and reads green on nothing. Dry-tested 2026-09-21: the empty file gives
#   "ABORT: baseline has 0 rows" exit 1, and `diff` of two empty files was
#   confirmed silent + exit 0 — i.e. the false green is real, and this stops it.

# --- documents_document baseline (what §4.5's UI count is compared against) ---
DOCS_PRE=$(awk '$1=="documents_document"{print $2}' /tmp/paperless-db-counts-pre.txt)
[ -n "$DOCS_PRE" ] && [ "$DOCS_PRE" -gt 0 ] || { echo "ABORT: no documents_document baseline"; exit 1; }
echo "$DOCS_PRE" > /tmp/paperless-db-docs-pre.txt
echo "documents_document baseline=$DOCS_PRE"     # 986 on 2026-09-21; WILL differ in-window

# --- 4-byte canary baseline (what §4.4 is compared against) ------------------
CANARY_PRE=$(kubectl -n office exec deploy/paperless-db -- sh -c \
  'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" -N -B -e \
   "SELECT COUNT(*) FROM paperless.paperless_mail_processedmail WHERE HEX(subject) LIKE \"%F09F%\";"' \
  | tr -d '[:space:]')
[ -n "$CANARY_PRE" ] && [ "$CANARY_PRE" -gt 0 ] || { echo "ABORT: 4-byte canary baseline is $CANARY_PRE — there is NO canary to check after the upgrade, so §4.4 could not fail; stop and find out why"; exit 1; }
echo "$CANARY_PRE" > /tmp/paperless-db-canary-pre.txt
echo "4-byte canary baseline=$CANARY_PRE"        # 1 on 2026-09-21
```

Dry-tested 2026-09-21 against the live DB: the loop produced exactly 74 lines,
`documents_document 986`, canary `1`; the empty-file and missing-row controls
both exited 1. The canary `> 0` assertion matters in its own right — a canary of
zero makes §4.4 a gate that cannot fail, which is the one thing worse than a
stale literal.

**3.4 Longhorn snapshot — fast-path insurance** (DB is idle; app is at 0):

```bash
kubectl apply -f - <<'EOF'
apiVersion: longhorn.io/v1beta2
kind: Snapshot
metadata:
  name: paperless-db-data-pre-13-0-2
  namespace: storage
spec:
  volume: paperless-db-data
  createSnapshot: true
EOF
kubectl -n storage get snapshot.longhorn.io paperless-db-data-pre-13-0-2 \
  -o jsonpath='{.status.readyToUse}{"\n"}'
# expect: true   (name verified free 2026-09-16 — the only snapshot on this
#                 volume is the daily daily-ba-23690c14-…; the 12.3.3 plan's
#                 paperless-db-data-pre-12-3-3 has already aged out)
```

**3.5 GitOps change** — one line in
`kubernetes/apps/office/paperless-ngx/app/db-deployment.yaml`:

Dry-tested on a scratch copy on macOS (BSD sed) 2026-09-16; the resulting diff is
exactly:

```diff
41c41
<         image: mariadb:12.3.3
---
>         image: mariadb:13.0.2
```

```bash
cd /Users/mu/code/cberg-home-nextgen
sed -i '' 's|^        image: mariadb:12\.3\.3$|        image: mariadb:13.0.2|' \
  kubernetes/apps/office/paperless-ngx/app/db-deployment.yaml
git diff --stat kubernetes/apps/office/paperless-ngx/app/db-deployment.yaml
```

`MARIADB_AUTO_UPGRADE=1` is **already present** (lines 68–69) — do not re-add it,
and do not remove it. Update the header comment's version references while there.

```bash
git fetch origin main && git merge --ff-only origin/main
git commit --only kubernetes/apps/office/paperless-ngx/app/db-deployment.yaml -F <msgfile>
git log -1 --format=%s     # shared worktree: confirm the subject is YOURS before pushing
git show --stat HEAD       # ONLY db-deployment.yaml
git push origin main
```

**3.6 Roll the DB** (the Kustomization owns this Deployment; the reconcile is
SOP-sanctioned here):

```bash
flux resume kustomization paperless-ngx -n office
flux reconcile kustomization paperless-ngx -n office --with-source
kubectl -n office rollout status deploy/paperless-db --timeout=300s

# WATCH the conversion actually happen — this is the point of no return:
kubectl -n office logs deploy/paperless-db | grep -iE 'upgrade|phase|version' | head -40
# EXPECT a line of the form "Major version upgrade detected from 12.3.3-MariaDB
# to 13.0.2-MariaDB" followed by phases 1..8.
# If it instead says "MariaDB upgrade not required" on a FIRST 13.0.2 start,
# the datadir was NOT converted — go to the manual invocation below.
```

If the entrypoint upgrade did not run or half-ran (the SOP's failure mode 2 —
TLS/TCP loopback resets mid-run, whose tell is that two runs fail at *different*
lines), run it by hand over the socket:

```bash
kubectl -n office exec deploy/paperless-db -- sh -c \
  'mariadb-upgrade --protocol=socket --skip-ssl -uroot -p"$MARIADB_ROOT_PASSWORD"'
```

**3.7 Verify the DB half of §4 — then and only then un-quiesce the app:**

```bash
flux resume helmrelease paperless-ngx -n office
flux reconcile helmrelease paperless-ngx -n office
# The reconcile does NOT restore replicas=1 (measured 2026-09-07): §3.1 scaled with
# kubectl, which is drift the HelmRelease does not correct unless driftDetection is
# enabled — and it is not (spec.driftDetection is unset on all 124 HRs; see the
# helm-drift-detection plan). Scale back explicitly, or the plan finishes with the
# app silently at 0/0 and every check still green.
kubectl -n office scale deploy/paperless-ngx --replicas=1
kubectl -n office rollout status deploy/paperless-ngx --timeout=300s
```

## 4. Verification

Version alone is the known misleading signal. Each gate below states the failure
it can actually catch.

```bash
# 1. Binary AND datadir marker agree on 13.0.2.
kubectl -n office exec deploy/paperless-db -- sh -c \
  'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" -N -e "SELECT VERSION();";
   cat /var/lib/mysql/mariadb_upgrade_info'
# expect: 13.0.2-MariaDB...  AND  13.0.2-MariaDB
# CATCHES: the SOP's failure mode 1 — a 13.0.2 binary serving 12.3-format system
# tables. That state returns the NEW version from VERSION() while the marker still
# reads 12.3.3-MariaDB, and nothing else goes red. Marker path verified live
# (/var/lib/mysql/..., NOT the SOP's /bitnami/... path — see §1.6).
```

```bash
# 2. Integrity across every schema.
kubectl -n office exec deploy/paperless-db -- sh -c \
  'mariadb-check --protocol=socket --all-databases -uroot -p"$MARIADB_ROOT_PASSWORD"' \
  | grep -ivE '[[:space:]]ok$' || echo "all OK"
# CATCHES: tables the upgrade left needing repair.
# ON THE PATTERN '[[:space:]]ok$' — this is DEFENCE IN DEPTH, not a reproduced
# failure, and the distinction is recorded so nobody "simplifies" it back.
# An earlier revision of this comment claimed mariadb-check emits a
# TAB-separated "<db>.<table>\tOK" that a literal-space ' ok$' would miss,
# false-reddening a healthy table after the point of no return. That claim does
# NOT hold for this component: client/mysqlcheck.c at tag mariadb-13.0.2 has
# three output paths in print_result(), all "%-50s %s\n" or "%-9s: %s\n" —
# SPACE-padded, with no tab path on this branch. So the space form would in fact
# have worked. '[[:space:]]ok$' is kept anyway because it is a strict SUPERSET of
# ' ok$' (space, tab or any other blank), costs nothing, and removes a dependency
# on upstream's column formatting staying byte-stable across a major version —
# which is precisely the thing this plan is changing.
# Still case-INSENSITIVE and still anchored, so a naive `grep -v OK` (which also
# swallows any table name containing "ok") is not reintroduced.
# NOTE: the executed paperless-db-12.3.3 plan carries the even weaker `grep -v OK`
# form. Do not copy it back; that is the bug this line fixes.
```

```bash
# 3. CONTENTS ASSERTION: per-table row counts of the paperless schema —
#    re-run the §3.3 loop into /tmp/paperless-db-counts-post.txt, ASSERT the
#    post file is itself well-formed, then diff against the pre baseline.
set -euo pipefail
kubectl -n office exec deploy/paperless-db -- sh -c '
  for t in $(mariadb -N -uroot -p"$MARIADB_ROOT_PASSWORD" -e \
    "SELECT table_name FROM information_schema.tables
     WHERE table_schema=\"paperless\" AND table_type=\"BASE TABLE\""); do
    echo "$t $(mariadb -N -uroot -p"$MARIADB_ROOT_PASSWORD" -e \
      "SELECT COUNT(*) FROM paperless.\`$t\`")"
  done' | sort > /tmp/paperless-db-counts-post.txt

NPOST=$(wc -l < /tmp/paperless-db-counts-post.txt | tr -d ' ')
NPRE=$(wc -l < /tmp/paperless-db-counts-pre.txt  | tr -d ' ')
echo "pre=$NPRE post=$NPOST"
[ "$NPRE" -eq 74 ] && [ "$NPOST" -eq 74 ] || { echo "ABORT: pre=$NPRE post=$NPOST, expected 74/74 — a diff of two broken files proves nothing"; exit 1; }
diff /tmp/paperless-db-counts-pre.txt /tmp/paperless-db-counts-post.txt && echo COUNTS-MATCH
# CATCHES: silent row loss. Fails loudly if any of the 74 tables changed count.
# The 74/74 pre-assertion is what makes the diff meaningful: dry-tested
# 2026-09-21, `diff` of two EMPTY files is silent and exits 0, so without it a
# post loop that failed entirely reads as COUNTS-MATCH — green on nothing.
# Baseline is a real measurement, not a shape check: an empty DB fails this
# while pod-Ready and SELECT VERSION() both still pass.
```

```bash
# 4. CONTENTS ASSERTION: the 4-byte content class survived — the original
#    OperationalError 1366 failure mode. Compared to the value MEASURED in §3.3,
#    never to a literal (a literal `1` typed on 2026-09-16 would false-red here,
#    AFTER the point of no return, on a healthy database).
set -euo pipefail
CANARY_PRE=$(cat /tmp/paperless-db-canary-pre.txt)
CANARY_POST=$(kubectl -n office exec deploy/paperless-db -- sh -c \
  'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" -N -B -e \
   "SELECT COUNT(*) FROM paperless.paperless_mail_processedmail WHERE HEX(subject) LIKE \"%F09F%\";"' \
  | tr -d '[:space:]')
echo "canary pre=$CANARY_PRE post=$CANARY_POST"
[ -n "$CANARY_POST" ] || { echo "ABORT: canary query returned nothing — could not measure"; exit 1; }
[ "$CANARY_POST" -eq "$CANARY_PRE" ] || { echo "ABORT: 4-byte canary $CANARY_PRE -> $CANARY_POST"; exit 1; }

# Collation, same computed form as §2 gate 4 (total 74, non-utf8mb4 must be 0)
COLL=$(kubectl -n office exec deploy/paperless-db -- sh -c \
  'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" -N -B -e \
   "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=\"paperless\";
    SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=\"paperless\" AND table_collation NOT LIKE \"utf8mb4%\";"')
NT=$(echo "$COLL" | head -1 | tr -d '[:space:]'); NB=$(echo "$COLL" | tail -1 | tr -d '[:space:]')
echo "tables=$NT non-utf8mb4=$NB"
[ -n "$NT" ] && [ -n "$NB" ] || { echo "ABORT: empty collation result"; exit 1; }
[ "$NT" -eq 74 ] && [ "$NB" -eq 0 ] || { echo "ABORT: tables=$NT non-utf8mb4=$NB"; exit 1; }
# CATCHES: a charset regression that flattened 4-byte content to '?'. Row counts
# CANNOT catch this — a transcoded row still counts as one row. §3.3 has already
# proven CANARY_PRE > 0, so this comparison cannot be a gate that always passes.
# Both forms dry-tested read-only against the live 12.3.3 DB 2026-09-21
# (canary=1, tables=74, non-utf8mb4=0) plus their empty-result controls.
```

```bash
# 5. The dependent app works. A DB its app cannot use is the failure worth catching.
kubectl -n office get pods -l app.kubernetes.io/name=paperless-ngx   # 1/1 Running
kubectl -n office logs deploy/paperless-ngx --since=15m | grep -iE '1366|OperationalError|mailbox.login' || echo clean
# Then the paperless.md §6a canary (API token, from the openclaw pod) and the UI:
# the dashboard document count MUST equal the §3.3 MEASURED baseline — read it,
# do not type it:
#     cat /tmp/paperless-db-docs-pre.txt     # 986 on 2026-09-21, WILL have moved
# and one existing document must open.
# CORRECTED 2026-09-21: this said "MUST equal 970", a literal measured 2026-09-16.
# documents_document was already 986 by 2026-09-21 — ingestion runs until §3.1
# quiesces — so the literal was guaranteed to go red on a healthy upgrade and
# send the operator into §5's destructive rollback for nothing.
# CATCHES: a healthy-but-unusable DB. A 401 here is a TOKEN failure, NOT missing
# documents — never read it as data loss (this exact mislabel happened 2026-08-30).
```

```bash
# 6. Ingestion round-trip (attended): drop a throwaway PDF into the scanner SMB
#    inbox and watch it become a document — exercises validator -> consume -> DB
#    WRITE on 13.0, which every read-only check above would miss.
kubectl -n office logs deploy/paperless-ngx -f --tail=20
```

Nightly Longhorn backup of `paperless-db-data` must complete on the next 03:00
cycle (check `lastBackupAt` next sweep). **Do not delete the §3.2 dump or the
§3.4 snapshot until that backup is Completed** — until then they are the only
recovery path for a 13.0-format datadir.

## 5. Rollback

**There is no in-place downgrade, and no manifest revert that helps.** Never run
`mariadb:12.3.3` against a datadir 13.0.2 has started on.

Trigger: the server will not start on 13.0.2; `mariadb-upgrade` cannot complete;
the §4.3 counts diff is non-silent; the §4.4 collation/4-byte assertion fails; or
paperless cannot serve its library.

1. **Quiesce again** — re-suspend per §3.1 and scale the DB down:
   ```bash
   flux suspend kustomization paperless-ngx -n office
   flux suspend helmrelease   paperless-ngx -n office
   kubectl -n office scale deploy/paperless-ngx --replicas=0
   kubectl -n office scale deploy/paperless-db  --replicas=0
   ```
2. **Revert the manifest** (necessary, not sufficient — do this while the data is
   still being restored, and keep the Kustomization suspended until step 3 or 4
   completes):
   ```bash
   git revert <hash-of-the-3.5-commit>    # back to mariadb:12.3.3
   git push origin main
   ```
3. **Fast path — Longhorn snapshot revert** (preferred; `paperless-db-data-pre-13-0-2`
   was taken with the server idle). Detach the volume, revert it to that snapshot
   via the Longhorn UI/API (maintenance-mode attach), re-attach, resume the
   Kustomization, scale up. This returns a **12.3-format** datadir, which the
   reverted 12.3.3 image can open.
   > **STORAGE SAFETY:** this is a snapshot *revert*, not a PVC delete. **Do not
   > delete or recreate `paperless-db-data`.** Its PV is `Retain`,
   > `longhorn-static`, driver `driver.longhorn.io` (verified 2026-09-16). If any
   > step ever seems to call for deleting a PVC, run the 3-step pre-flight from
   > CLAUDE.md (`subdir`, `reclaimPolicy`, StorageClass) and STOP.
4. **Fallback — dump restore into a fresh datadir.** Only if the snapshot revert
   fails. With the Deployment back on 12.3.3 and scaled to 0, clear the datadir
   *contents* via a one-off debug pod mounting `paperless-db-data`
   (`rm -rf /var/lib/mysql/*` — this PVC only, triple-check the claim name; the
   PVC and PV themselves are NOT deleted), scale up so the entrypoint
   re-initialises from the `MARIADB_*` env, then:

   **Re-derive `$DUMP` first — do not assume it is still set.** It is assigned
   only inside §3.2's own script block. §5 will very likely run in a FRESH SHELL
   hours later, where `$DUMP` expands to empty and the restore below silently
   reads from the terminal instead of the dump — in the one rollback path of a
   database with no second copy, at the moment everything else has already gone
   wrong. This block fails closed instead:

   ```bash
   set -euo pipefail
   DUMP=$(ls -t "$HOME"/backups/paperless-db/paperless-db-pre-13.0.2-*.sql 2>/dev/null | head -1 || true)
   [ -n "$DUMP" ] && [ -s "$DUMP" ] || { echo "ABORT: no pre-upgrade dump found — do NOT wipe the datadir"; exit 1; }
   echo "restoring from $DUMP ($(wc -c < "$DUMP" | tr -d ' ') bytes)"
   ```
   Dry-tested on this Mac 2026-09-21 under `bash`, `zsh` and `sh`, against three
   fixtures, with `$HOME` overridden to a scratch tree:

   - **no matching file** → prints the `ABORT`, exit 1, in all three shells. The
     naive `DUMP=$(ls -t … | head -1)` — without `2>/dev/null … || true` — instead
     dies at the *assignment* under `set -euo pipefail`, so the `[ -n "$DUMP" ]`
     check never runs and the operator sees only `ls`'s error.
   - **a zero-byte dump present** → `ABORT` via `-s`, exit 1, all three shells.
     This is the case the `-n` check alone would wave through.
   - **two dumps present** → the newest is selected; verified by reading the file's
     *contents*, not by trusting the name's timestamp.

   Expect harmless stderr noise under `zsh` in the no-match case: zsh fails the
   glob itself, *before* `ls` runs, so `2>/dev/null` cannot suppress its
   `no matches found` line. Measured — it does not change the outcome (the
   substitution is still empty, `|| true` absorbs the status, and the explicit
   check still prints the `ABORT` and exits 1). The `|| true` is what keeps the
   failure on the explicit check, which is the one that says why.

   ```bash
   kubectl -n office exec -i deploy/paperless-db -- sh -c \
     'mariadb --default-character-set=utf8mb4 -uroot -p"$MARIADB_ROOT_PASSWORD"' < "$DUMP"
   ```
   `--default-character-set=utf8mb4` on the way IN as well, or the restore
   re-introduces the 1366 bug.

   **Then reload the grant tables before step 6 verifies anything.** The dump is
   `--all-databases`, so it rewrites `mysql.global_priv` (and the rest of the
   `mysql` schema) **on disk**, while the running server keeps serving its
   in-memory grants from before the restore. Every subsequent connection — the
   step-6 checks, and paperless itself when it comes back — then authenticates
   against stale grants, which presents as an intermittent access-denied that
   looks like a failed restore:

   ```bash
   kubectl -n office exec deploy/paperless-db -- sh -c \
     'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" -e "FLUSH PRIVILEGES;"'
   # Equivalent and arguably cleaner here, since the pod is disposable at this
   # point and a cold start also re-reads the restored system tables:
   #   kubectl -n office rollout restart deploy/paperless-db
   #   kubectl -n office rollout status  deploy/paperless-db --timeout=300s
   ```

   (Not dry-tested — running it would mean running the restore. It is the
   documented consequence of reloading `mysql.*` under a live server, and the
   cost of including it if unnecessary is one statement.)
5. **Last resort — restore from the Longhorn backup** (newest Completed backup of
   `paperless-db-data`, e.g. `backup-3416ef68e9e74554` @ 2026-09-15T03:03:17Z):
   restore it into a new volume and rebind, per `docs/sops/backup.md`. Costs up to
   24h of documents — the dump and snapshot exist precisely so this is not needed.
6. **Confirm the back-state, don't assume it:** `SELECT VERSION();` → 12.3.3,
   marker → `12.3.3-MariaDB`, §4.3 counts diff silent against
   `/tmp/paperless-db-counts-pre.txt`, §4.4 collation + 4-byte assertions pass,
   paperless serves, ingestion round-trip passes. Then set this plan
   `status: blocked` with the failure recorded.

## 6. Interference notes

- **`conflicts_with` carries TWO plan_ids. Both are hard.**
  - **`bitnamilegacy-exit-nextcloud-db`** — carried forward. Same namespace
    (`office`), both `risk: high`, both `rollback_class: backup-restore`, both
    one-way MariaDB datadir operations, and 60 + 80 = 140 min cannot fit a
    90-min window. That plan is currently `blocked` with `window: null`, so the
    collision is latent — but nothing else would stop them sharing a slot if it
    unblocks. **Reciprocity gap:** that plan's `conflicts_with` still names
    `paperless-db-12.3.3` (executed), not this plan_id. `--validate` checks that
    refs resolve, not that they are mutual, so the other side needs the same
    edit — flagged, not edited here.
  - **`paperless-ngx-3.2.0`** — ADDED 2026-09-21; this plan's list predated it.
    That plan was written 2026-09-20 and already declares a HARD conflict
    against `paperless-db-13.0.2` (`cb7c2acd`), so until now the pair was
    one-sided — and **only `conflicts_with` is honoured by the scheduler**, on
    whichever side it is read from, so a one-sided declaration is a coin flip.
    It is not merely a duration clash: it touches `deployment/paperless-ngx`,
    `kustomization/paperless-ngx`, `helmrelease/paperless-ngx` **and
    `deployment/paperless-db`** (its Django migration 0026), while §3.1 here
    scales paperless-ngx to 0 and suspends both the Kustomization and the
    HelmRelease for the whole window. Its migration and its entire verification
    need a live, writable `paperless-db`; this plan removes exactly that. And in
    the other order, its baselines would predate a one-way datadir conversion.
    **Never the same slot, in either order.** The pair is now mutual.
- **Do not co-schedule with any Longhorn engine/storage work.** The upgrade holds
  `paperless-db-data` attached and the §3.4 snapshot is the fast rollback path.
- **Attended, never nightly.** `risk: high` + `rollback_class: backup-restore`
  derives **HUMAN-GATED** under `runbooks/autonomy-policy.yaml` (`auto-backup-gated`
  carries `forbid_risk: [high]`), and that is correct here. `needs_reboot: false`,
  so a Saturday slot would suffice *if* it ran at all.
- **Ingestion downtime ~30–40 min inside the window.** The paperless app is at 0
  while the dump and bump run. Scanner drops land in the SMB inbox and email sits
  in the GMX mailbox — both buffer, nothing is lost, consume catches up after
  §3.7. The ARAG bill push and any paperless API consumers will error during the
  quiesce; Homepage and Uptime Kuma will flag paperless — pre-silence per
  `docs/sops/application-update.md` §Step 1, and drop an active-update marker
  (`runbooks/update-marker.sh add paperless-ngx office 4 "..."`) so the
  alert-triage agent treats the noise as EXPECTED.
- **The suspend/scale in §3.1 must be symmetric**, and the order in §3.6/§3.7 is
  deliberate: the Kustomization resumes (DB rolls, DB verified) *before* the
  HelmRelease resumes (app returns). Do not resume the HR early.
- **Dumps contain `mysql.global_priv` password hashes** — keep them `0600` in a
  `0700` directory, never commit them, and delete them once the post-upgrade
  nightly backup has completed.
- **`scan-inbox-validator` rides the paperless-ngx image, not the DB image** — it
  is untouched by this plan, but it does talk to the same consume share, so leave
  it running.
