---
plan_id: paperless-ngx-3.2.0
component: paperless-ngx
pr: null                               # No Renovate PR. Verified 2026-09-20:
                                       # `gh pr list` shows exactly one open PR (#212,
                                       # talos CLI pin). Both pins are plain image tags
                                       # (a HelmRelease values key + a Deployment yaml),
                                       # so this rides coverage.py's direct-bump lane.
kind: image
current: "3.1.3"                       # live-verified 2026-09-20: BOTH Deployments run
                                       # ghcr.io/paperless-ngx/paperless-ngx:3.1.3, and the
                                       # serving process reports paperless.version 3.1.3
target: "3.2.1"                        # RETARGETED 2026-09-25 from 3.2.0 (plan_id kept per
                                       # README "Keep the plan_id when you refresh").
                                       # v3.2.1 released 2026-09-20, GitHub release NOT
                                       # prerelease and marked Latest; ghcr index digest
                                       # sha256:5fa76604a81df6945086e0837b14b56543d137e8ce4f311cc5d9ebe907e74e79
                                       # == the digest ghcr `latest` resolves to (read
                                       # 2026-09-25) -> stable channel. 3.2.0 remains
                                       # the release that carries the schema change below.
update_type: minor
risk: medium                           # NOT from the flagged ng-select line (frontend-only).
                                       # From the search-index rebuild: 3.2.0 (crossed by
                                       # this 3.1.3 -> 3.2.1 path; 3.2.1 keeps it) bumps the
                                       # tantivy SCHEMA_VERSION 1 -> 2, which forces a full
                                       # rebuild of the 973-document full-text index at
                                       # container start, plus one Django migration. A
                                       # rebuild that yields an EMPTY index is structurally
                                       # healthy and silently returns no search results.
est_duration_min: 50
needs_reboot: false
touches:
  namespaces: [office]
  resources:
    - helmrelease/paperless-ngx                  # values.image.tag 3.1.3 -> 3.2.1
    - deployment/paperless-ngx                   # Recreate roll onto the new image
                                                 # scan-inbox-validator REMOVED from touches
                                                 # 2026-09-25: its pin (the SAME image) was
                                                 # already moved 3.1.3 -> 3.2.1 by 9557fa89
                                                 # (2026-09-21, operator instruction, own
                                                 # commit). Live-verified 2026-09-25: it runs
                                                 # :3.2.1. This plan no longer edits it; it
                                                 # only re-reads it (premises + CA4).
    - kustomization/paperless-ngx                # namespace `office` (NOT flux-system)
    - pvc/paperless-data                         # tantivy index under data/index REBUILT
                                                 # IN PLACE (RWO longhorn-static)
    - deployment/paperless-db                    # schema only: migration 0026 applied
                                                 # (two AlterFields); image NOT touched
  shared:
    - monitoring                       # CORRECTED 2026-09-20 (was `[]`). §2.5 WRITES a
                                       # silence into Alertmanager
                                       # (svc/kube-prometheus-stack-alertmanager, live
                                       # v0.34.0, GET /api/v2/silences -> 200 verified
                                       # read-only 2026-09-20), so this plan PERTURBS shared
                                       # monitoring state even though §4 never READS
                                       # Prometheus. Declared as a shared surface (a
                                       # post-placement warning), NOT as a conflicts_with:
                                       # the silence is a courtesy to the pager, not an
                                       # instrument of any gate here, so a same-slot
                                       # kube-prometheus-stack-91.4.1 cannot blind this
                                       # plan's verification — it can only drop the silence
                                       # during its ~1 min Alertmanager restart. Sequencing
                                       # note in §6.
                                       # NOT declared, deliberately: the PUBLIC edge
                                       # (HTTPRoute paperless-ngx -> Gateway
                                       # envoy-external/https) — this plan does not touch the
                                       # route, the Gateway or any listener; it is a consumer
                                       # of that edge, not a perturber of it. Nor
                                       # storage/longhorn: it rebuilds ONE longhorn-static
                                       # volume's CONTENTS, not the Longhorn control plane
                                       # (same rationale the paperless-db plans use).
depends_on: []
conflicts_with: [paperless-db-13.0.2]  # HARD. That plan scales deployment/paperless-ngx to
                                       # 0, suspends this HelmRelease and this Kustomization,
                                       # and performs a ONE-WAY MariaDB datadir conversion on
                                       # the same library. This plan's migration 0026 and its
                                       # whole verification need a live, writable
                                       # paperless-db. Never the same window, in either
                                       # order. NOTE reciprocity is one-sided: that plan
                                       # cannot list a plan_id that did not exist when it was
                                       # written. --validate checks refs resolve, not
                                       # reciprocity — reported as a repo correction, not
                                       # edited here.
                                       # Deliberately NOT listed: kube-prometheus-stack-91.4.1
                                       # (plan_id corrected 2026-09-20 — that plan retargeted
                                       # 91.4.0 -> 91.4.1 on 2026-09-20; it is status `draft`,
                                       # window null). This plan's §4 never reads Prometheus,
                                       # so that stack cannot blind any gate here. It IS named
                                       # in touches.shared as `monitoring` because §2.5 writes
                                       # an Alertmanager silence — a post-placement warning,
                                       # not a slot veto. See §6 for the sequencing rule.
                                       # Also NOT listed: nextcloud-34.0.4 (namespace `office`
                                       # overlap only — no shared resource, no shared
                                       # datastore; and it sits in sun-attended, a different
                                       # slot from the sat-attended this plan is sized for).
security_ref: F-9c2b83cf               # RE-QUERIED 2026-09-25 (F-15987249 is now RESOLVED).
                                       # F-9c2b83cf: open, section `security`, against the
                                       # running `:3.1.3` app image, "newer upstream tag
                                       # available", triage lane COVERED (image-or-version-
                                       # bump) — i.e. it is waiting on exactly this bump.
                                       # See also F-56e8bbdd (open, AR-029-accepted, pinned
                                       # to the 3.1.3 tag string — lapses when the tag moves)
                                       # and F-e6b70b55 (open, AR-029-accepted residual set
                                       # of the `:3.2.1` TARGET image, already running in
                                       # scan-inbox-validator). We bump, we never rebuild.
                                       # Security refs stay OUT of finding_refs: they are
                                       # citations, not PLAN-lane ownership claims.
                                       # Detail stays on the finding records — never here.
capability_change: true                # HONEST true, and it decides the execution class.
                                       # The 3.1.3 -> 3.2.1 path changes ingest-time
                                       # behaviour, not just the UI. From 3.2.0:
                                       # "Improve matching for correspondents, storage path and
                                       # labels by removing bias + adding minimum match
                                       # threshold" (#12164) alters auto-classification of
                                       # incoming documents, and "skip documents with empty
                                       # content in apply AI suggestions WF" (#13985) changes
                                       # when the AI workflow action fires. Both are
                                       # user-visible on the household's live ingestion path.
                                       # From 3.2.1: mail-fetch overlap guard moves from a
                                       # PaperlessTask-row check to a Redis cache lock with a
                                       # 30-min TTL (#14189), and ocrmypdf 17.12 (ligature
                                       # text-layer fix, #14190) changes OCR text output under
                                       # OCR_MODE=force.
rollback_class: git-revert             # A real git revert, verified against the code paths:
                                       # the index self-heals on downgrade (§5) and both
                                       # migration operations are reversible AlterFields.
                                       # NOT backup-restore: nothing forward-only happens.
finding_refs: [F-6b6c515a]             # RE-QUERIED 2026-09-25 with SWEEP_PG_DSN up
                                       # (finding list --grep paperless-ngx --all). The
                                       # 2026-09-20 query found none; the version sweep has
                                       # since opened F-6b6c515a, "paperless-ngx: image
                                       # ghcr.io/paperless-ngx/paperless-ngx 3.1.3 -> 3.2.1
                                       # (minor)" — the exact component + target this plan
                                       # answers. Claimed so the finding reads as planned.
status: draft
window: null                           # the scheduler assigns. Shape: attended (see
                                       # capability_change), no reboot. Sized against
                                       # sat-attended, which is the 90-min slot
                                       # (`maintenance-windows.yaml`, re-read 2026-09-20):
                                       # 50 min of work leaves a 40-min rollback budget.
                                       # NOT sun-attended — that slot is 200 min but already
                                       # holds absenty-drop-npm-runtime + nextcloud-34.0.4,
                                       # both `awaiting-go` on sun-attended:2026-09-20.
premises:
  - id: app-pin-is-3.1.3
    why: "`current:` claims 3.1.3 for the app. If the cluster already moved, this plan is stale and every baseline in section 2 is wrong."
    run: "kubectl get deploy -n office paperless-ngx -o jsonpath='{.spec.template.spec.containers[0].image}'"
    expect_exact: "ghcr.io/paperless-ngx/paperless-ngx:3.1.3"
  - id: validator-pin-is-3.2.1
    why: "The SECOND pin of the same image was moved ahead of this plan to the TARGET (9557fa89, operator decision 2026-09-21). This plan closes the split by moving the app to match. If the validator is anywhere else, the parity premise this plan converges on is wrong - stop and re-plan."
    run: "kubectl get deploy -n office scan-inbox-validator -o jsonpath='{.spec.template.spec.containers[0].image}'"
    expect_exact: "ghcr.io/paperless-ngx/paperless-ngx:3.2.1"
  - id: repo-helmrelease-pin-is-3.1.3
    why: "The manifest the edit in section 3 targets. If HEAD no longer carries exactly one 3.1.3 tag line, the sed in step 3.3 would silently no-op or hit the wrong line."
    run: "git show HEAD:kubernetes/apps/office/paperless-ngx/app/helmrelease.yaml | grep -c 'tag: \"3.1.3\"'"
    expect_exact: "1"
  - id: repo-validator-pin-is-3.2.1
    why: "Same guard in git. Exactly one 3.2.1 occurrence means step 3.4 (verify-only) needs no edit and step 3.5's two-line parity grep is valid."
    run: "git show HEAD:kubernetes/apps/office/paperless-ngx/app/validator-deployment.yaml | grep -c 'paperless-ngx:3.2.1'"
    expect_exact: "1"
  - id: helmrelease-ready-on-chart-0.24.1
    why: "A not-Ready or drifted HelmRelease means something else is mid-flight; this plan must not stack a bump on top of it. The chart is NOT being changed - only values.image.tag."
    run: "kubectl get hr -n office paperless-ngx -o jsonpath='{.status.conditions[?(@.type==\"Ready\")].status} {.status.history[0].chartVersion}'"
    expect_exact: "True 0.24.1"
  - id: kustomization-ready
    why: "The Flux Kustomization lives in namespace office, NOT flux-system. A stale or failing reconcile would make the push in step 3.7 land somewhere unobservable."
    run: "kubectl get kustomization -n office paperless-ngx -o jsonpath='{.status.conditions[?(@.type==\"Ready\")].status}'"
    expect_exact: "True"
  - id: memory-limit-still-6gi
    why: "OCR_MODE=force OOM-kills paperless at 3Gi on multi-page documents. The full index rebuild adds a 512MB tantivy writer budget on top of that. If anything has lowered this limit, do not start."
    run: "kubectl get deploy -n office paperless-ngx -o jsonpath='{.spec.template.spec.containers[0].resources.limits.memory}'"
    expect_exact: "6Gi"
  - id: strategy-is-recreate
    why: "paperless-data is RWO on longhorn-static with replicas 1. Under RollingUpdate maxSurge rounds up to 1 and the replacement pod deadlocks on Multi-Attach. Recreate is load-bearing for this roll."
    run: "kubectl get deploy -n office paperless-ngx -o jsonpath='{.spec.strategy.type}'"
    expect_exact: "Recreate"
  - id: index-volume-healthy
    why: "The tantivy index that this upgrade rebuilds lives on this volume. Rebuilding an index on a degraded volume turns a recoverable upgrade into a restore."
    run: "kubectl get volume -n storage paperless-data -o jsonpath='{.status.state} {.status.robustness}'"
    expect_exact: "attached healthy"
  - id: index-volume-has-a-backup
    why: "The index is rebuilt in place. A volume that has never been backed up has no floor under it. Freshness (not merely existence) is re-checked in section 2."
    run: "kubectl get volume -n storage paperless-data -o jsonpath='{.status.lastBackupAt}'"
    expect_matches: "^20[0-9][0-9]-[0-9][0-9]-[0-9][0-9]T"
  - id: db-still-on-12.3.3
    why: "Migration 0026 and the whole verification need a live writable paperless-db. If paperless-db-13.0.2 has already run, this plan's baselines predate a datadir conversion and must be re-taken."
    run: "kubectl get deploy -n office paperless-db -o jsonpath='{.spec.template.spec.containers[0].image}'"
    expect_exact: "mariadb:12.3.3"
  - id: validator-is-up
    why: "The validator must be healthy BEFORE the bump, or a post-upgrade failure cannot be attributed to the new image."
    run: "kubectl get deploy -n office scan-inbox-validator -o jsonpath='{.status.readyReplicas}'"
    expect_exact: "1"
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/paperless.md
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/backup.md
  - docs/sops/longhorn.md
generated: "2026-09-20"
retargeted: "2026-09-25"                 # 3.2.0 -> 3.2.1; validator pin already at 3.2.1
---

# paperless-ngx 3.1.3 -> 3.2.1 (app pin; closes the split with scan-inbox-validator, already on 3.2.1)

## 1) Summary & why held

### 1.1 What moves

> **Retargeted 2026-09-25: 3.2.0 -> 3.2.1.** 3.2.1 (released 2026-09-20) is a
> four-fix patch on top of 3.2.0 — see §1.4. Everything in §1.2 about 3.2.0
> still applies, because 3.1.3 -> 3.2.1 crosses 3.2.0: `SCHEMA_VERSION` is still
> `2` at v3.2.1 (`_schema.py:28`), `_backend.py` and `document_index.py` are
> unchanged between v3.2.0 and v3.2.1, and **no Django migration was added**
> (no file under any `migrations/` in the v3.2.0...v3.2.1 compare, 8 commits).
>
> **The validator pin has ALREADY moved.** `9557fa89` (2026-09-21, operator
> instruction, "a DECISION, not drift") bumped `scan-inbox-validator` to
> `:3.2.1` while deliberately leaving the app at 3.1.3. Live 2026-09-25: the
> validator runs `:3.2.1` with `PIKEPDF 10.2.0 PY 3.14.7` and a heartbeat 13 s
> old. So this plan now moves **ONE pin** — the app — and ends the intentional
> split. The table below is the pre-2026-09-21 layout, kept for context.

ONE image, pinned TWICE in the same app folder (validator row: now `:3.2.1`):

| Pin | File | Line |
|---|---|---|
| app | `kubernetes/apps/office/paperless-ngx/app/helmrelease.yaml` | 33 — `tag: "3.1.3"` |
| validator | `kubernetes/apps/office/paperless-ngx/app/validator-deployment.yaml` | 34 — `image: ghcr.io/paperless-ngx/paperless-ngx:3.1.3` |

`scan-inbox-validator` is **not a separate component**. It reuses the paperless
image for its `python3` + `pikepdf` runtime and overrides the entrypoint
(`command: ["python3", "/scripts/validator.py"]`). Both pins move in one commit
or the scanner pipeline runs two paperless versions against one consume share.
The SOP states this as a rule (`docs/sops/paperless.md` §2). That rule has been
knowingly suspended since 2026-09-21 (`9557fa89`); this plan restores it.

### 1.2 Why it was held — and why the stated reason is not the real one

The lane reason was:

> G3 breaking-change signal — `- Chore: update ng-select to v24, handle breaking changes`

**That line is frontend-only, and the hold on those grounds is a false
positive.** Upstream PR #13951 touches 17 files, *every one of them* under
`src-ui/` (component templates/TS, `styles.scss`, `theme.scss`, `package.json`,
`pnpm-lock.yaml`, two e2e specs). No Python, no API, no consumer, no database.
The author's own summary: *"Shouldnt be noticeable for pngx users, but will
leave for 3.2"*. It cannot affect the scanner → SMB inbox → validator → consume
pipeline, because that path never renders a dropdown.

**But the hold was right, for a bigger reason the signal did not see.** Reading
the actual v3.1.3…v3.2.0 diff (145 commits, 300 files):

1. **The full-text search index is force-rebuilt.**
   `src/documents/search/_schema.py` bumps the on-disk schema:

   ```python
   # v1 - Initial tantivy schema format
   # v2 - build_schema() derived from PUBLIC_FIELDS, changing the field declaration
   #      order, and the write-only correspondent/document_type/storage_path/tag id
   #      columns dropped. tantivy compares schemas by ordered field list, so an
   #      index built by v1 rejects every write against the v2 schema.
   SCHEMA_VERSION: Final[int] = 2
   ```

   3.2.0 also adds a `schema_fingerprint()` (blake2b over the ordered field
   descriptors) stamped into `.index_settings.json`, so a shape change is caught
   even when the version is not bumped. The live index is **v1**:
   `.index_settings.json` reads `{"schema_version": 1, "language": "de"}`
   (measured 2026-09-20). `needs_rebuild()` compares `schema_version` first, so
   the mismatch fires and the **entire 973-document index is rebuilt from the
   database**.

   This happens **automatically at container start**, not on demand. The s6
   oneshot `init-search-index` runs
   `python3 manage.py document_index reindex --if-needed --no-progress-bar`
   (identical in 3.1.3 and 3.2.0), and `document_index.py` wraps the rebuild in
   `transaction.atomic()`. **The pod is NOT Ready until the rebuild finishes.**

   This is the risk, and it has a **deadline** attached. Measured live
   2026-09-20 on the running pod, the s6 chain is
   `init-search-index` (oneshot) → `init-complete` → `svc-webserver`
   (`ls /etc/s6-overlay/s6-rc.d/svc-webserver/dependencies.d` →
   `init-complete`; `init-complete/dependencies.d` contains
   `init-search-index`). **Port 8000 therefore does not listen until the
   rebuild finishes** — and the chart's `startupProbe` is a `tcpSocket` on
   exactly port 8000. See §3.2: the kubelet, not Flux, is the first thing that
   kills a long rebuild, and the stock budget is 150 s.

   The second trap is that the index sentinel is written **before** any
   document is indexed. From `src/documents/search/_backend.py` at v3.2.0,
   `TantivyBackend.rebuild()` runs, in this order:
   `wipe_index(self._path)` → `tantivy.Index(build_schema(), path=...)` →
   `_write_sentinels(self._path)` → *then* the `writer.add_document(doc)` loop
   → `writer.commit()`. `_write_sentinels` stamps
   `{"schema_version": 2, "language": ..., "schema_fingerprint": ...}`
   (`_schema.py`). The `transaction.atomic()` in `document_index.py` is a
   **database** transaction — it does not roll back index files. So a rebuild
   killed midway (probe kill, OOM, node event) leaves a v2 sentinel over an
   empty-or-partial index; on the next boot `needs_rebuild()` compares
   `schema_version`, `language` and `schema_fingerprint`, finds all three
   current, returns **False**, and the pod comes up **Ready on a broken
   index**.

   A rebuild that produces an *empty* index therefore leaves every structural
   signal green — pod Ready, HTTP 200, HelmRelease Ready, **and the sentinel
   reading v2** — while search silently returns nothing. That is exactly the
   shape-vs-contents failure class
   (`docs/sops/verification-contents-not-shape.md`), so §4 asserts
   **index-side** document membership and hit *counts* against measured
   baselines — never the sentinel alone, and never a database count, which
   never touches the index.

2. **Two Django migrations run** (corrected by review 2026-09-26: the GitHub
   compare API returns at most 300 files, so the v3.1.3...v3.2.0 file list the
   planner read was truncated; a full-tree diff shows a second migration).
   `paperless/0016_alter_applicationconfiguration_ai_enabled` makes
   `ApplicationConfiguration.ai_enabled` nullable and a RunPython rewrites
   `ai_enabled=False` rows to NULL (reverse: no-op). 3.1.3 resolves
   `app_config.ai_enabled or settings.AI_ENABLED`, no `PAPERLESS_AI_ENABLED` env
   is set, and §2.4(c) reads `AI True`, so the stored row is True and the data
   step changes nothing here; §4.7 re-asserts it. The documents one:
   `0026_alter_document_archive_checksum_and_more`
   (live DB is at `0025_workflowaction_apply_ai_suggestions`). It is two
   `AlterField`s: `Document.archive_checksum` gains `db_index=True` (973 rows —
   trivial), and `SavedViewFilterRule.rule_type` gains choice `50 "has
   duplicates"`. Both are reversible, which is what keeps `rollback_class` at
   `git-revert`.

3. **Ingest behaviour changes** (the honest basis for `capability_change: true`):
   correspondent/storage-path/label matching drops its bias and gains a minimum
   match threshold (#12164), and the apply-AI-suggestions workflow now skips
   empty-content documents (#13985).

**Repo correction to report, not to silently plan around:** the G3 signal
matched a `Chore:` dependency line and missed a `SCHEMA_VERSION` bump that
forces a full index rebuild. The remedy cited here comes from upstream code
(`_schema.py`, `document_index.py`, the s6 `init-search-index` run script), not
from the gate's reason string.

### 1.3 What is NOT affected (checked, not assumed)

- **RAG / LLM vector store**: five non-test files under `src/paperless_ai/` DO
  change between v3.1.3 and v3.2.1 (ai_classifier, client, exceptions, indexing,
  taxonomy; the earlier "zero" came from the 300-file-capped compare). The only
  `indexing.py` change removes an unused helper, `vector_store.py` is unchanged
  and no `paperless_ai` migration exists, so no `REEMBED_REQUIRED` schema
  migration is triggered. The nightly `llm_index` task stays incremental. §4.7 re-asserts
  this rather than trusting it.
- **The validator's own runtime**: it overrides `command:`, so it bypasses
  s6-overlay entirely — it never runs migrations and never reindexes. It needs
  only `python3` + `pikepdf`, both still present. The Dockerfile diff removes
  only the **NLTK** data downloads (the classifier now preprocesses via Tantivy)
  and bumps the uv base 0.12.5 → 0.12.16, still `python3.14-trixie`.
- **Routing, storage classes, secrets, OCR env, the 6Gi limit**: untouched.
- **Security**: see `security_ref` in the frontmatter. Detail stays on the
  finding record — not in this file.

### 1.4 What 3.2.1 adds on top of 3.2.0 (release notes + the v3.2.0...v3.2.1 diff)

Stable channel: GitHub release `v3.2.1` is **not** a prerelease and is marked
**Latest**; the ghcr `latest` tag resolves to the same index digest as `3.2.1`
(`sha256:5fa76604…`, read 2026-09-25). No breaking-change or migration note.
The four fixes, and what each means here:

- **#14180 — rebuild the search index when tantivy files are missing.**
  `open_or_rebuild_index()` now catches the `ValueError` from
  `tantivy.Index.open()` (e.g. a missing `meta.json`) and wipes + rebuilds.
  **This does NOT close the §1.2 partial-rebuild trap**: a rebuild killed
  after `_write_sentinels()` leaves a *valid* (openable) v2 index with too few
  documents — `Index.open()` succeeds, nothing is caught, the pod serves Ready
  on a partial index. CA1's `MISSING_FROM_INDEX` stays the load-bearing gate.
  What it *does* change: a torn index now self-heals by a full rebuild at the
  next open instead of hard-failing every read/write — so an unexpected
  *second* not-Ready rebuild after a restart is plausible and is not by itself
  a failure (§3.8).
- **#14189 — mail-fetch overlap guard is now a cache lock.** The
  `PaperlessTask`-row check is replaced by `cache.add("paperless_mail_fetch_lock",
  …, timeout=30*60)` on the Django cache, which paperless points at its Redis
  (`_parse_caches()` → `_CHANNELS_REDIS_URL`). If the worker is killed
  mid-fetch (e.g. by this roll), the lock self-expires within **30 min**; until
  then scheduled fetches log `Mail account processing is already running;
  skipping this run.` That is expected right after the roll and is **not** the
  §4.6 failure signal.
- **#14190 — ocrmypdf pinned to `>=17.12,<17.13`** (ligature text-layer fix).
  Under `OCR_MODE=force` this changes the OCR text of newly ingested pages; CA3
  exercises it.
- **#14182 — flower `--conf` only when `flowerconfig.py` exists.** Flower is
  not enabled in this deployment; no effect.
- `src/paperless_ai/` is untouched by 3.2.1 as well (not in the compare file
  list), so §4.7's `MISMATCH False` expectation stands.

**Risk class unchanged: `medium`.** 3.2.1 adds no migration, no schema change
and no breaking note; the risk is still the 3.2.0 index rebuild.

## 2) Pre-checks

Run in order. Any FAIL aborts before the first edit.

```bash
cd /Users/mu/code/cberg-home-nextgen

# 2.1 Premises (all 12 must PASS; fail-closed)
.venv/bin/python3 runbooks/plan-premises.py paperless-ngx-3.2.0 --require-premises

# 2.2 Nothing in flight
flux get kustomizations -n office paperless-ngx
flux get helmreleases  -n office paperless-ngx
kubectl get pods -n office -l app.kubernetes.io/name=paperless-ngx \
  -o custom-columns='NAME:.metadata.name,READY:.status.containerStatuses[0].ready,RESTARTS:.status.containerStatuses[0].restartCount'

# 2.3 Backup freshness (existence is a premise; RECENCY is checked here).
#     Expect a timestamp from the most recent 03:00 run, not merely non-empty.
kubectl get volume -n storage paperless-data \
  -o jsonpath='{.status.lastBackupAt}{"\n"}'
kubectl get snapshots.longhorn.io -n storage \
  -o custom-columns='NAME:.metadata.name,VOL:.spec.volume,READY:.status.readyToUse,TIME:.status.creationTime' \
  --no-headers | grep paperless-data
```

If that timestamp is older than ~26h, take one before proceeding
(`docs/sops/backup.md` §"Pre-Upgrade Backup Procedure"; the CronJob is
`storage/daily-backup-all-volumes` — verified live 2026-09-20):

```bash
kubectl create job --from=cronjob/daily-backup-all-volumes \
  pre-upgrade-backup-$(date +%Y%m%d) -n storage
kubectl wait --for=condition=complete job/pre-upgrade-backup-$(date +%Y%m%d) \
  -n storage --timeout=3600s
```

### 2.4 BASELINES — capture these; §4 compares against them

These are the numbers that make §4 able to fail. Measured 2026-09-20 on 3.1.3;
**re-measure in-window**, do not reuse these values if days have passed.

```bash
# (a) version + index sentinel + INDEX-SIDE membership + REAL search hit counts.
#     Exec via deploy/ so no captured pod name can go stale (§4/§5 do the same).
kubectl exec -n office deploy/paperless-ngx -c paperless-ngx -- \
  python3 /usr/src/paperless/src/manage.py shell -c "
from paperless.version import __version__
from documents.models import Document
from documents.search import get_backend, SearchMode
print('VERSION', '.'.join(map(str, __version__)))
print('SETTINGS', open('/usr/src/paperless/data/index/.index_settings.json').read().strip())
b = get_backend()
db  = set(Document.objects.values_list('pk', flat=True))
idx = set(b.search_ids('*', None, search_mode=SearchMode.QUERY))
print('DOCS', len(db))
print('INDEXED', len(idx))
print('MISSING_FROM_INDEX', len(db - idx))
print('EXTRA_IN_INDEX', len(idx - db))
for term in ['rechnung','versicherung','vertrag','januar']:
    print('HITS', term, len(b.search_ids(term, None, search_mode=SearchMode.TEXT)))
"
```

Measured baseline on 3.1.3 (2026-09-20, re-measured after the review):

```
VERSION  3.1.3
SETTINGS {"schema_version": 1, "language": "de"}
DOCS     973
INDEXED  976
MISSING_FROM_INDEX 0
EXTRA_IN_INDEX     3
HITS rechnung 566 · versicherung 405 · vertrag 179 · januar 45
```

> **Why `INDEXED` is 976 and not 973, and why CA1 must NOT assert equality.**
> Measured, not assumed: `search_ids('*', …, QUERY)` returned 976 ids, all
> distinct (`len(set(ids)) == 976`, no duplicates), containing **every one of
> the 973 database pks** plus **3 ids that no longer exist in the database** —
> stale entries for deleted documents that the live v1 index never dropped.
> An `INDEXED == 973` gate would therefore FAIL on today's healthy index.
> The load-bearing limb is `MISSING_FROM_INDEX == 0`; `EXTRA_IN_INDEX` is
> reported for information only. Note `search_ids` is uncapped by default
> (v3.2.0 `_backend.py`: `limit=None` → `effective_limit = searcher.num_docs`),
> so this counts the whole index, not a result page.
> **After the 3.2.1 rebuild expect `EXTRA_IN_INDEX` to drop to 0** — the
> rebuild sources every document from the database, so the 3 stale ids cannot
> survive it. That is a *prediction*, not a gate: do not fail the upgrade on it.

```bash
# (b) served UI bundle identity (the ng-select leg's baseline)
kubectl exec -n office deploy/paperless-ngx -c paperless-ngx -- python3 -c "
import hashlib
for p in ('/usr/src/paperless/static/frontend/en-US/main.js',
          '/usr/src/paperless/static/frontend/en-US/styles.css'):
    d = open(p,'rb').read()
    print(p.rsplit('/',1)[-1], len(d), hashlib.sha256(d).hexdigest()[:16])
"
# baseline 2026-09-20: main.js 2933613 c853f88fc4f28392 · styles.css 275917 2f620075dee0af2f

# (c) native-AI config row (DB-stored, NOT GitOps - a restore can silently reset it)
kubectl exec -n office deploy/paperless-ngx -c paperless-ngx -- \
  python3 /usr/src/paperless/src/manage.py shell -c "
from paperless.config import AIConfig
c = AIConfig()
print('AI', c.ai_enabled, c.llm_backend, c.llm_model, c.llm_embedding_backend, c.llm_embedding_model)
"
# expected: AI True ollama gemma4:26b-mlx ollama nomic-embed-text:latest

# (d) consume backlog must be EMPTY before we roll (a wedged file would be
#     misread as an upgrade failure)
kubectl exec -n office deploy/scan-inbox-validator -- \
  sh -c 'ls -1 /consume/*.pdf 2>/dev/null | wc -l; ls -1 /inbox/*.pdf 2>/dev/null | wc -l'
```

### 2.5 Silence alerts + drop the active-update marker

```bash
# ONE Bash block. State goes to FIXED FILES under /private/tmp/claude-501/paperless-ngx-3.2.0 because agent
# Bash calls share no shell variables: section 5 reads the silence id back from
# /private/tmp/claude-501/paperless-ngx-3.2.0/silence-id. Local port 19093 (not 9093) so a parallel plan's
# Alertmanager port-forward cannot collide with this one.
mkdir -p /private/tmp/claude-501/paperless-ngx-3.2.0
kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 19093:9093 >/dev/null 2>&1 & PF=$!
sleep 2
NOW=$(python3 -c "from datetime import *;print(datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
END=$(python3 -c "from datetime import *;print((datetime.now(timezone.utc)+timedelta(hours=3)).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
# CAPTURE the result — a silence POST that fails must not be silent (see gate below)
SIL_CODE=$(curl -s -o /private/tmp/claude-501/paperless-ngx-3.2.0/silence-resp.json -w '%{http_code}' \
  -X POST localhost:19093/api/v2/silences -H 'Content-Type: application/json' -d '{
  "matchers":[{"name":"namespace","value":"office","isRegex":false,"isEqual":true},
              {"name":"alertname","value":"Kube(Pod|Deployment).*","isRegex":true,"isEqual":true}],
  "startsAt":"'$NOW'","endsAt":"'$END'","createdBy":"maintenance-window-agent",
  "comment":"paperless-ngx 3.1.3->3.2.1 - index rebuild keeps the pod not-Ready for minutes. auto-expires 3h"}')
echo "SILENCE_HTTP $SIL_CODE"; cat /private/tmp/claude-501/paperless-ngx-3.2.0/silence-resp.json; echo
SIL_ID=$(python3 -c "import json;print(json.load(open('/private/tmp/claude-501/paperless-ngx-3.2.0/silence-resp.json')).get('silenceID',''))" 2>/dev/null)
echo "SILENCE_ID ${SIL_ID:-NONE}"
printf '%s\n' "$SIL_ID" > /private/tmp/claude-501/paperless-ngx-3.2.0/silence-id    # section 5 reads THIS file, never $SIL_ID
# Read it BACK — the POST echoing an id is not proof the silence is active
curl -s "localhost:19093/api/v2/silence/$SIL_ID" | python3 -c "
import sys,json
try:
    d=json.load(sys.stdin); print('SILENCE_STATE', d['status']['state'], 'ENDS', d['endsAt'])
except Exception as e: print('SILENCE_READBACK_FAILED', e)
"
kill $PF 2>/dev/null

runbooks/update-marker.sh add paperless-ngx office 2 "3.1.3->3.2.1 + full search index rebuild"
```

**GATE — the silence must exist before the roll.** PASS requires
`SILENCE_HTTP 200`, a non-empty `SILENCE_ID`, and `SILENCE_STATE active`.
*What failure prints:* `SILENCE_HTTP 000` (port-forward never came up —
`curl` writes no body, so `SILENCE_ID NONE`), `SILENCE_HTTP 400` with a
`"failed to parse"` body (a malformed `startsAt`/matcher), or
`SILENCE_READBACK_FAILED`. Any of those means the rebuild's multi-minute
not-Ready window **will page the operator** — fix it or accept the pages
deliberately; do not proceed assuming silence. `endsAt` is 3 h (was 2 h): the
startup budget in §3.2 is now up to 10 min and the silence must outlive a
rollback too. Verified read-only 2026-09-20: Alertmanager v0.34.0,
`GET /api/v2/silences` → 200.

## 3) Steps

```bash
cd /Users/mu/code/cberg-home-nextgen
```

**3.1 — Confirm the target image exists** (never bump to an unpublished tag):

```bash
TOKEN=$(curl -s "https://ghcr.io/token?scope=repository:paperless-ngx/paperless-ngx:pull&service=ghcr.io" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
curl -sI -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/vnd.oci.image.index.v1+json" \
  "https://ghcr.io/v2/paperless-ngx/paperless-ngx/manifests/3.2.1" | grep -iE '^HTTP|docker-content-digest'
# expect HTTP/2 200 and (verified 2026-09-25)
# docker-content-digest: sha256:5fa76604a81df6945086e0837b14b56543d137e8ce4f311cc5d9ebe907e74e79
```

**3.2 — Give the rebuild room to finish: raise the startup budget, raise the
Helm timeout, and disable Flux remediation.** All three, in the same commit as
the tag bump. Disabling Flux remediation alone is **not** enough — it defends
against the wrong thing, in the wrong order.

Measured live 2026-09-20, and reproduced by `helm template` against the real
HelmRelease values, the three deadlines that can kill a rebuild are:

| Deadline | Budget | Source |
|---|---|---|
| **kubelet `startupProbe`** | **150 s** | `failureThreshold: 30` × `periodSeconds: 5`, `initialDelaySeconds: 0`, `tcpSocket: 8000` — live on `deploy/paperless-ngx` |
| Helm operation timeout | 300 s | `spec.timeout` is unset → helm-controller default `5m0s` (confirmed in the HelmRelease CRD v2 schema) |
| Flux upgrade remediation | on failure | `upgrade.remediation.retries: 1` + `maxHistory: 1` |

**The kubelet fires FIRST, at 150 s, and §3.8's old advice to "expect the pod to
sit not-Ready" would have trained the operator to watch it happen.** Because
`svc-webserver` waits on `init-complete` which waits on `init-search-index`
(§1.2), port 8000 does not listen during the rebuild — so every startup probe
fails, and at 30 consecutive failures the kubelet **kills the container and
restarts it**, mid-rebuild, leaving the v2 sentinel over a partial index (§1.2).
The current no-op startup consumes **28 s** of that budget already (live pod:
container `startedAt` 22:00:49 → `Ready` 22:01:17; the 41 s pod-level figure
includes the two initContainers, which run *before* the probe budget starts),
leaving only ~122 s for a full rebuild of 973 documents / 5.0 MB of extracted
text / 35 MB of on-disk index.

**The rebuild's real duration is UNMEASURED** — it cannot be measured without
performing the upgrade, and this plan does not guess at it. Instead the budget
is raised well past any plausible value and the actual number is recorded in
§3.8. Raising only the probe would just move the failure to the 300 s Helm
timeout, so `spec.timeout` moves too.

Apply all three edits (anchored, dry-tested on a scratch copy 2026-09-20 — the
`install:` block is deliberately left alone):

```bash
cd /Users/mu/code/cberg-home-nextgen
python3 - <<'PY'
import pathlib
p = pathlib.Path("kubernetes/apps/office/paperless-ngx/app/helmrelease.yaml")
s = p.read_text()
edits = [
 ("spec:\n  interval: 30m\n",
  "spec:\n  interval: 30m\n  timeout: 20m                    # RESTORE (remove) in step 3.9\n"),
 ("  upgrade:\n    cleanupOnFail: true\n    remediation:\n      retries: 1\n",
  "  upgrade:\n    cleanupOnFail: true\n    remediation:\n"
  "      retries: 0                    # RESTORE to 1 in step 3.9\n"
  "      remediateLastFailure: false   # RESTORE (remove) in step 3.9\n"),
 ("    image:\n      repository: ghcr.io/paperless-ngx/paperless-ngx\n",
  "    probes:\n      startup:\n        spec:\n"
  "          failureThreshold: 120     # RESTORE to 30 in step 3.9\n"
  "    image:\n      repository: ghcr.io/paperless-ngx/paperless-ngx\n"),
]
for old, new in edits:
    assert s.count(old) == 1, f"anchor not unique/found: {old[:40]!r}"
    s = s.replace(old, new)
p.write_text(s)
print("STRUCTURAL EDIT OK")
PY
```

Resulting diff (verified on a scratch copy — this is the exact output):

```diff
@@ -6,6 +6,7 @@
   namespace: office
 spec:
   interval: 30m
+  timeout: 20m                    # RESTORE (remove) in step 3.9
   chart:
     spec:
       chart: paperless-ngx
@@ -21,13 +22,18 @@
   upgrade:
     cleanupOnFail: true
     remediation:
-      retries: 1
+      retries: 0                    # RESTORE to 1 in step 3.9
+      remediateLastFailure: false   # RESTORE (remove) in step 3.9
   uninstall:
     keepHistory: false
   values:
     global:
       security:
         allowInsecureImages: true
+    probes:
+      startup:
+        spec:
+          failureThreshold: 120     # RESTORE to 30 in step 3.9
     image:
       repository: ghcr.io/paperless-ngx/paperless-ngx
       tag: "3.1.3"
```

`failureThreshold: 120` × `periodSeconds: 5` = **600 s (10 min)** of startup
budget; `timeout: 20m` keeps Helm from failing the release underneath it.

**Proof the probe override actually reaches the container** (this is a
gabe565 chart that inherits the `bjw-s` common library 1.5.1 — the key is
*not* obvious, and setting the wrong one fails silently as "no change"). Dry-run
2026-09-20: `helm template` the real values before and after the edit and diff
the rendered `Deployment` — the ONLY two differences are the image tag and the
startup threshold, with `livenessProbe`/`readinessProbe` untouched:

```diff
-        image: ghcr.io/paperless-ngx/paperless-ngx:3.1.3
+        image: ghcr.io/paperless-ngx/paperless-ngx:3.2.1   # (dry-run was against 3.2.0; the tag string is the only render input that changed)
         startupProbe:
-          failureThreshold: 30
+          failureThreshold: 120
           initialDelaySeconds: 0
           periodSeconds: 5
           tcpSocket:
             port: 8000
```

**Accepted trade-off, stated deliberately:** for this one roll a genuinely
wedged container takes up to 10 min to be restarted instead of 150 s. That is
the point — a wedged-looking container *is* the expected state here. Liveness
and readiness are unchanged (`failureThreshold: 3` × `periodSeconds: 10`), so
once the app is serving, normal failure detection is back to ~30 s. Step 3.9
restores the 150 s budget; leaving 120 in place would silently weaken startup
detection for this app forever.

**3.3 — Bump the app pin.** BSD sed, re-dry-tested on a scratch copy 2026-09-25:

```bash
sed -i '' 's|^      tag: "3.1.3"$|      tag: "3.2.1"|' \
  kubernetes/apps/office/paperless-ngx/app/helmrelease.yaml
```

Resulting diff line (verified on a scratch copy **with the §3.2 edit already
applied**, which is the order the window agent runs them in):

```
39c39
<       tag: "3.1.3"
---
>       tag: "3.2.1"
```

> The tag sits at line **39**, not 33, once §3.2 has inserted the four-line
> `probes:` block above it. The `sed` is anchored on the line's *content*
> (`^      tag: "3.1.3"$`), so it matches either way — but do not be surprised
> by the line number, and do not "fix" it back to 33.

**3.4 — Validator pin: VERIFY ONLY, no edit** (changed 2026-09-25). It already
reads `:3.2.1` (`9557fa89`). Do **not** run a sed against it; confirm instead:

```bash
grep -n 'paperless-ngx:' kubernetes/apps/office/paperless-ngx/app/validator-deployment.yaml
# expect exactly: 34:          image: ghcr.io/paperless-ngx/paperless-ngx:3.2.1
```

If it reads anything else, someone moved it since 2026-09-25 — stop; the
parity target of this plan is no longer 3.2.1.

**3.5 — Prove BOTH pins moved and nothing else did:**

```bash
grep -n '3\.2\.1' kubernetes/apps/office/paperless-ngx/app/helmrelease.yaml \
                  kubernetes/apps/office/paperless-ngx/app/validator-deployment.yaml
# expect EXACTLY two lines: helmrelease.yaml:39 and validator-deployment.yaml:34
grep -rn '3\.1\.3' kubernetes/apps/office/paperless-ngx/
# expect NO hits
git diff --stat -- kubernetes/apps/office/paperless-ngx/
# expect exactly 1 file changed: helmrelease.yaml (validator was moved in 9557fa89)
git diff -- kubernetes/apps/office/paperless-ngx/app/helmrelease.yaml
# expect the §3.2 diff (timeout / retries / probes) PLUS the one tag line
```

> **The `git diff --stat` MUST be path-scoped.** Measured 2026-09-20: this is a
> shared worktree and it currently carries an unstaged `runbooks/health-check.sh`
> (+80 lines) owned by another session, so a bare `git diff --stat` reports
> **2 files changed** for the wrong reason and would keep reporting a plausible
> count no matter what a concurrent session does. Scope it, or the gate passes
> on someone else's work.

**3.6 — Validate the manifests:**

```bash
kubeconform -summary -exit-on-error -ignore-missing-schemas \
  kubernetes/apps/office/paperless-ngx/
```

**3.7 — Commit with `--only` (shared worktree) and verify the subject is YOURS
before pushing.** Two sessions committing in the same second can swap message
files:

```bash
mkdir -p /private/tmp/claude-501/paperless-ngx-3.2.0
MSG=/private/tmp/claude-501/paperless-ngx-3.2.0/msg-paperless-ngx-3.2.0-$(date +%s).txt   # unique name, same block as its use
cat > "$MSG" <<'EOF'
feat(container): update ghcr.io/paperless-ngx/paperless-ngx ( 3.1.3 -> 3.2.1 )

Moves the HelmRelease values tag to 3.2.1, matching scan-inbox-validator, which
has run the same image at 3.2.1 since 9557fa89. Ends the intentional split.

The path crosses 3.2.0, which bumps the tantivy search SCHEMA_VERSION 1 -> 2, so the full-text index is
rebuilt from the database at container start (s6 init-search-index runs
document_index reindex --if-needed). Django migration 0026 also applies.

The webserver does not listen until that rebuild finishes, so three limits are
raised for this roll and RESTORED in a follow-up commit:
  - values.probes.startup.spec.failureThreshold 30 -> 120 (150s -> 600s), or the
    kubelet restarts the container mid-rebuild and leaves a v2 index sentinel
    over a partial index;
  - spec.timeout 20m (default 5m), so Helm does not fail underneath it;
  - upgrade.remediation retries 0 + remediateLastFailure false, so a Flux
    rollback cannot fire mid-rebuild.

Plan: runbooks/maintenance/plans/paperless-ngx-3.2.0.md
EOF

git commit --only \
  kubernetes/apps/office/paperless-ngx/app/helmrelease.yaml \
  -F "$MSG"

git log -1 --format=%s        # MUST be the paperless subject above; amend if not
git show --stat HEAD          # MUST be exactly the one file above
git rev-parse HEAD > /private/tmp/claude-501/paperless-ngx-3.2.0/commit-3.7.sha   # read by the 3.9 gate (file, not a shell var)
git push
```

**3.8 — Watch the reconcile and the rebuild, against a clock.** A not-Ready pod
is expected here — but it is expected **for a bounded time**, and "expect
not-Ready" is not a licence to ignore it. Start a timer:

```bash
mkdir -p /private/tmp/claude-501/paperless-ngx-3.2.0
flux reconcile kustomization paperless-ngx -n office --with-source
[ -s /private/tmp/claude-501/paperless-ngx-3.2.0/roll-start ] || date +%s > /private/tmp/claude-501/paperless-ngx-3.2.0/roll-start
printf '3.2.1\n' > /private/tmp/claude-501/paperless-ngx-3.2.0/expect-tag
# Bounded, non-interactive poll (NO `-w`, no Ctrl-C; fits one Bash call).
# All state is in files, so if it prints STILL_NOT_READY just run THIS block
# again: it resumes against the same roll-start. Past 660 s total -> section 5.
python3 - <<'PY'
import json, subprocess, time
st = "/private/tmp/claude-501/paperless-ngx-3.2.0"
start = int(open(st + "/roll-start").read())
want = open(st + "/expect-tag").read().strip()
deadline = time.time() + 540
while time.time() < deadline:
    raw = subprocess.run(["kubectl", "get", "pods", "-n", "office", "-l",
                          "app.kubernetes.io/name=paperless-ngx", "-o", "json"],
                         capture_output=True, text=True).stdout or '{"items":[]}'
    for p in json.loads(raw)["items"]:
        if p["metadata"].get("deletionTimestamp"):
            continue
        cs = (p["status"].get("containerStatuses") or [{}])[0]
        img = cs.get("image", "")
        rs = cs.get("restartCount", 0)
        print(time.strftime("%H:%M:%S"), p["metadata"]["name"], img.rsplit(":", 1)[-1],
              "ready=%s restarts=%s" % (cs.get("ready"), rs), flush=True)
        if rs:
            print("RESTARTED_DURING_REBUILD - see the RESTARTS bullet below; CA1 is now the gate")
        if cs.get("ready") and img.endswith(":" + want):
            ra = int(time.time()) - start
            open(st + "/ready-after", "w").write(str(ra))
            print("READY_AFTER %ds" % ra)
            raise SystemExit(0)
    time.sleep(15)
print("STILL_NOT_READY %ds since roll start" % (int(time.time()) - start))
raise SystemExit(1)
PY

# the rebuild's own log lines (deploy/ target - no captured pod name to go stale)
kubectl logs -n office deploy/paperless-ngx -c paperless-ngx \
  | grep -iE 'init-index|schema version mismatch|fingerprint mismatch|up to date|reindex'
```

**Expected:** `[init-index] Checking search index...` followed by
`Search index schema version mismatch - rebuilding.` (the exact string
`needs_rebuild()` logs when `schema_version` differs), then Ready.
New in 3.2.1 (#14180): a line `Search index is corrupted or incomplete -
rebuilding from scratch.` means `Index.open()` raised and a *further* full
rebuild ran. Not a failure by itself — but it means the index was torn, so CA1
must be green on the final pod before you proceed.

**Two things that are NOT the plan working — act, do not wait:**

- **`RESTARTS` incrementing while not-Ready.** That is the startupProbe killing
  the rebuild. With §3.2 applied it should be impossible inside 10 min; if you
  see it, §3.2 did not take effect — check the live probe with
  `kubectl get deploy -n office paperless-ngx -o jsonpath='{.spec.template.spec.containers[0].startupProbe.failureThreshold}'`
  (must print `120`, not `30`). **A restart here means the index is now
  sentinel-v2 over a partial rebuild** (§1.2), so §4's CA1 is the gate that
  matters and a pass on a restarted pod still needs CA1 green.
- **Ready never arrives within ~10 min.** The budget is exhausted. Do not
  "give it another minute" — go to §5.

```bash
# if it is still not Ready, this tells you WHICH deadline you are against
kubectl get pods -n office -l app.kubernetes.io/name=paperless-ngx \
  -o custom-columns='READY:.status.containerStatuses[0].ready,RESTARTS:.status.containerStatuses[0].restartCount'
kubectl get hr -n office paperless-ngx -o jsonpath='{range .status.conditions[*]}{.type}={.status} {.reason}{"\n"}{end}'
```

**Record `READY_AFTER` in the close-out and in `docs/sops/paperless.md`.** It is
the number this plan could not measure in advance, it sizes every future
paperless bump, and it is what lets the next planner set a real budget instead
of a generous one.

**3.9 — After §4 passes, restore ALL THREE §3.2 changes.** Leaving any of them
in place silently weakens this app forever: the startup budget stays at 10 min,
Helm waits 20 min on every future operation, and Flux's rollback safety net
stays off. Anchored and dry-tested on a scratch copy 2026-09-20:

```bash
cd /Users/mu/code/cberg-home-nextgen
python3 - <<'PY'
import pathlib
p = pathlib.Path("kubernetes/apps/office/paperless-ngx/app/helmrelease.yaml")
s = p.read_text()
edits = [
 ("  timeout: 20m                    # RESTORE (remove) in step 3.9\n", ""),
 ("      retries: 0                    # RESTORE to 1 in step 3.9\n"
  "      remediateLastFailure: false   # RESTORE (remove) in step 3.9\n",
  "      retries: 1\n"),
 ("    probes:\n      startup:\n        spec:\n"
  "          failureThreshold: 120     # RESTORE to 30 in step 3.9\n", ""),
]
for old, new in edits:
    assert s.count(old) == 1, f"restore anchor not unique/found: {old[:40]!r}"
    s = s.replace(old, new)
p.write_text(s)
print("RESTORE OK")
PY

# PROOF the restore is complete: the ONLY surviving difference from the
# pre-upgrade file must be the image tag. Diff against the PARENT of the 3.7
# commit (the pre-upgrade file). A bare `git diff` compares against HEAD, which
# already carries the 3.7 commit, so it would print the REMOVAL of the
# timeout/retries/probes lines on a correct restore - a false STOP.
git diff "$(cat /private/tmp/claude-501/paperless-ngx-3.2.0/commit-3.7.sha)^" -- kubernetes/apps/office/paperless-ngx/app/helmrelease.yaml
```

```diff
-      tag: "3.1.3"
+      tag: "3.2.1"
```

**GATE:** that diff shows **one hunk, the tag line, and nothing else**. Any
surviving `timeout:`, `retries: 0`, `remediateLastFailure:` or `probes:` line
means the restore did not complete. Confirm against the live cluster after
Flux reconciles, not just against the file:

```bash
kubectl get deploy -n office paperless-ngx \
  -o jsonpath='{.spec.template.spec.containers[0].startupProbe.failureThreshold}{"\n"}'   # must be 30
kubectl get hr -n office paperless-ngx \
  -o jsonpath='{.spec.timeout} {.spec.upgrade.remediation.retries}{"\n"}'                 # must be "  1" (timeout empty, retries 1)
```

Commit with `--only` + the same `git log -1 --format=%s` subject check as §3.7,
using a unique message file in the same block, e.g.
`MSG=/private/tmp/claude-501/paperless-ngx-3.2.0/msg-paperless-ngx-3.2.0-restore-$(date +%s).txt`, subject
`fix(paperless-ngx): restore startup probe, helm timeout and upgrade remediation after 3.2.1 roll`.

**This restore changes the pod template (`startupProbe.failureThreshold`), so it
triggers a SECOND Recreate roll** — a brief outage on an already-current v2 index
(expect the ~30 s no-op startup, `Search index is up to date.`). Run the §3.8 poll
again (it resumes from the files; reset with
`rm /private/tmp/claude-501/paperless-ngx-3.2.0/roll-start`) and re-run CA1 once on that pod.

**3.10 — Close-out (success path too).** After §4 passes and §3.9 has landed, run
the final "clear the marker and drop the silence" block at the end of §5. It is
not rollback-only: left in place, the namespace-wide `office` silence masks pod
alerts of any other `office` plan for up to 3 h.

## 4) Verification

Floor first (necessary, NOT sufficient):

```bash
kubectl get hr -n office paperless-ngx \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion}{"\n"}'
# expect: True 0.24.1   (chart unchanged - only the image moved)
kubectl get deploy -n office paperless-ngx scan-inbox-validator \
  -o custom-columns='NAME:.metadata.name,IMAGE:.spec.template.spec.containers[*].image'
# BOTH must read ...:3.2.1  - this is SOP paperless.md section 6.6, image parity
kubectl get pods -n office -l app.kubernetes.io/name=paperless-ngx \
  -o custom-columns='READY:.status.containerStatuses[0].ready,RESTARTS:.status.containerStatuses[0].restartCount'
```

> Verify the running pod's image, not `kubectl rollout status` — that reports
> success against the OLD generation mid-HelmRelease-upgrade.

### CONTENTS ASSERTION 1 — every document is actually IN the rebuilt index

**The property:** the rebuilt v2 index contains the whole library — not that a
rebuild was *attempted*, and not that the database still has 973 rows.
**Measured by:** set difference between the database's primary keys and the ids
the **index itself** returns.
**Compared to:** §2.4(a) (`DOCS 973`, `MISSING_FROM_INDEX 0`).

```bash
kubectl exec -n office deploy/paperless-ngx -c paperless-ngx -- \
  python3 /usr/src/paperless/src/manage.py shell -c "
from paperless.version import __version__
from documents.models import Document
from documents.search import get_backend, SearchMode
print('VERSION', '.'.join(map(str, __version__)))
print('SETTINGS', open('/usr/src/paperless/data/index/.index_settings.json').read().strip())
db  = set(Document.objects.values_list('pk', flat=True))
idx = set(get_backend().search_ids('*', None, search_mode=SearchMode.QUERY))
print('DOCS', len(db))
print('INDEXED', len(idx))
print('MISSING_FROM_INDEX', len(db - idx))
print('EXTRA_IN_INDEX', len(idx - db))
"
```

PASS, all four limbs:

1. `VERSION 3.2.1`
2. `SETTINGS` shows `"schema_version": 2` **and** a `"schema_fingerprint"` key
3. **`MISSING_FROM_INDEX 0`** ← the load-bearing limb
4. `INDEXED` ≥ `DOCS` (973, or 974 after the CA3 test document)

`EXTRA_IN_INDEX` is informational: it was **3** on 3.1.3 (stale ids for deleted
documents) and should fall to **0** after a rebuild, which sources every
document from the database. Do not fail the upgrade on it.

**What failure prints — and why the obvious gates do not catch it.** This
assertion exists because of a specific race, confirmed in the v3.2.0 source
(`_backend.py`, `TantivyBackend.rebuild()`; the file is unchanged at v3.2.1, and
3.2.1's #14180 only catches an *unopenable* index, not a partial one): the index is wiped, the new v2
index is created, **`_write_sentinels()` stamps `schema_version: 2` + the
fingerprint, and only THEN does the `writer.add_document()` loop start.** The
`transaction.atomic()` in `document_index.py` is a database transaction and does
not roll back index files.

So a rebuild killed midway — by the startupProbe (§3.2), an OOM, or a node
event — leaves this state:

| Signal | Reads | Catches the failure? |
|---|---|---|
| pod Ready / HTTP 200 | green | **no** — `needs_rebuild()` sees a current sentinel and returns False, so the next boot serves immediately |
| `SETTINGS schema_version: 2` + fingerprint | green | **no** — written before the first document |
| `DOCS 973` | green | **no** — `Document.objects.count()` is a DATABASE count that never touches the index |
| **`MISSING_FROM_INDEX`** | **973 (or a partial count)** | **yes** |

A killed rebuild therefore prints `VERSION 3.2.1`, a v2 `SETTINGS` line and
`DOCS 973` — three green limbs — alongside `INDEXED 0` and
`MISSING_FROM_INDEX 973`. **An earlier draft of this plan asserted only those
three green limbs and would have passed the exact failure the plan exists to
catch.**

If `search_ids('*', …)` raises instead of returning, that is a FAIL, not a pass —
do not swallow the exception. (Verified on the live 3.1.3 index: the query
returns the whole index, uncapped — v3.2.0 `_backend.py` uses
`effective_limit = searcher.num_docs` when `limit` is None.)

> **Do NOT assert on `data/index/meta.json` segment sums.** Measured live:
> `sum(max_doc)` = 976 against 973 real documents — segment bookkeeping counts
> superseded segments. An equality check there fails on a healthy index.

### CONTENTS ASSERTION 2 — search still returns the same documents

**The property:** the rebuilt v2 index is *queryable* and holds the same
content, not merely the same count.
**Measured by:** four real term queries.
**Compared to:** the §2.4(a) baseline (2026-09-20: 566 / 405 / 179 / 45).

```bash
kubectl exec -n office deploy/paperless-ngx -c paperless-ngx -- \
  python3 /usr/src/paperless/src/manage.py shell -c "
from documents.search import get_backend, SearchMode
b = get_backend()
for term in ['rechnung','versicherung','vertrag','januar']:
    print('HITS', term, len(b.search_ids(term, None, search_mode=SearchMode.TEXT)))
"
```

PASS: every count **> 0** (the floor) **and** within ±5% of baseline (the
ceiling). A ceiling alone is not enough — a total collapse to 0 must fail, not
read as "fewer noisy hits".

What failure prints: `HITS rechnung 0` on a Ready pod — the empty-index
outcome this whole plan is shaped around. Note the harmless
`40 objects imported automatically` banner that `manage.py shell` prints first;
grep for `^HITS`, and case-insensitively if you grep the words.

### CONTENTS ASSERTION 3 — the consume pipeline still ingests AND indexes

**Primary (attended window — preferred, exercises the real path):** run the
ES-580W "paperless" preset on a 2-3 page document (`docs/sops/paperless.md`
§6.2). Assert, in order: the file appears in `/inbox`; the validator logs
`moved -> consume` within ~30s; a new Document appears within ~10s; and its OCR
text is **searchable** (which proves the write path against the *new* v2
schema, not just the DB insert):

```bash
kubectl logs -n office deploy/scan-inbox-validator --since=10m | grep -i 'moved -> consume'
kubectl exec -n office deploy/paperless-ngx -c paperless-ngx -- \
  python3 /usr/src/paperless/src/manage.py shell -c "
from documents.models import Document
from documents.search import get_backend, SearchMode
d = Document.objects.order_by('-added').first()
print('NEWEST', d.pk, d.title)
print('SEARCHABLE', d.pk in get_backend().search_ids(d.title.split()[0], None, search_mode=SearchMode.TEXT))
"
```

PASS: `SEARCHABLE True`. That single boolean is the one assertion proving
`add_or_update` works against schema v2 — the failure mode the upstream comment
warns about (*"an index built by v1 rejects every write against the v2
schema"*) shows up here and nowhere else.

> **Trap — do NOT re-feed an existing document as the test input.**
> `PAPERLESS_CONSUMER_DELETE_DUPLICATES=true` means a checksum-identical PDF is
> silently deleted and the document count never moves, which reads as an
> ingestion failure that is not one.
> **Trap — do NOT use a blank/near-blank page.** Under `OCR_MODE=force`
> tesseract can ParseError on a near-blank duplex back and wedge the consumer on
> every 10s poll (`docs/sops/paperless.md` §7).

**Fallback (only if no scanner access — strictly weaker, does NOT exercise the
CIFS consume path):** re-OCR one already-clean document and assert it comes back
searchable, plus assert the validator loop still turns (CA4):

```bash
kubectl exec -n office deploy/paperless-ngx -c paperless-ngx -- \
  python3 /usr/src/paperless/src/manage.py shell -c "
from documents.bulk_edit import reprocess
from documents.models import Document
d = Document.objects.order_by('-added').first()
print('REPROCESS', d.pk); reprocess([d.pk])
"
# wait ~60s, then re-run the SEARCHABLE check above for that pk
```

### CONTENTS ASSERTION 4 — the validator is still on 3.2.1 and still works

**The property:** the second pin (already `:3.2.1` since `9557fa89`) was not
disturbed by this roll and its loop still turns. Baseline 2026-09-25 on 3.2.1:
`PIKEPDF 10.2.0 PY 3.14.7`, heartbeat age 13 s.

```bash
kubectl get deploy -n office scan-inbox-validator \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'   # must be :3.2.1
kubectl exec -n office deploy/scan-inbox-validator -- \
  python3 -c "import pikepdf, sys; print('PIKEPDF', pikepdf.__version__, 'PY', sys.version.split()[0])"
# heartbeat must ADVANCE - both reads inside ONE call (validator poll = 15 s)
kubectl exec -n office deploy/scan-inbox-validator -- \
  python3 -c "import os,time; a=os.path.getmtime('/tmp/validator.heartbeat'); time.sleep(25); b=os.path.getmtime('/tmp/validator.heartbeat'); print('HEARTBEAT', a, b, 'ADVANCED' if b > a else 'FROZEN')"
```

PASS: image is `:3.2.1`, `PIKEPDF` prints a version, and `HEARTBEAT ... ADVANCED`. What failure prints: `ModuleNotFoundError: pikepdf`, or a
frozen mtime — a validator that is Running but whose loop is dead (the liveness
probe would take ~3 min to notice).

### CONTENTS ASSERTION 5 — the frontend bundle actually changed

**The property:** the ng-select v24 rebuild produced a *different, plausible*
bundle, and it is actually served. A bundler change fails silently as a
different bundle, not as a failed build.
**Compared to:** §2.4(b) (`main.js` 2933613 bytes / `c853f88fc4f28392`).

```bash
kubectl exec -n office deploy/paperless-ngx -c paperless-ngx -- python3 -c "
import hashlib
for p in ('/usr/src/paperless/static/frontend/en-US/main.js',
          '/usr/src/paperless/static/frontend/en-US/styles.css'):
    d = open(p,'rb').read()
    print(p.rsplit('/',1)[-1], len(d), hashlib.sha256(d).hexdigest()[:16])
"
# and prove it SERVES (these paths are public - no auth needed; verified 2026-09-20)
kubectl port-forward -n office svc/paperless-ngx 18000:8000 >/dev/null 2>&1 & PF=$!
sleep 3
for u in /static/frontend/en-US/main.js /static/frontend/en-US/styles.css; do
  curl -s -o /dev/null -w "$u code=%{http_code} bytes=%{size_download} type=%{content_type}\n" \
    "http://localhost:18000$u"
done
kill $PF 2>/dev/null
```

PASS: the sha256 prefix **differs** from baseline; `main.js` is still > 1 MB and
`content_type` is `text/javascript`; both return 200. What failure prints: an
unchanged hash (the frontend never rebuilt — the image did not really move), a
tiny body, or `text/html` (an error page served where the bundle should be).

### 4.6 — App-side canary and mail-ingestion guard (SOP §6a)

```bash
OPOD=$(kubectl get pod -n ai -l app.kubernetes.io/name=openclaw -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n ai "$OPOD" -- paperless search ARAG | head -5
# 200 + results. A 401 is a TOKEN failure - never read it as "documents are missing".

mkdir -p /private/tmp/claude-501/paperless-ngx-3.2.0
kubectl logs -n office deploy/paperless-ngx -c paperless-ngx --since=30m > /private/tmp/claude-501/paperless-ngx-3.2.0/app-30m.log
python3 - <<'PY'
import re
t = open("/private/tmp/claude-501/paperless-ngx-3.2.0/app-30m.log").read()
ran = len(re.findall(r"process_mail_accounts\[[^\]]+\] succeeded in [0-9.]+s: '(?:No new documents were added|Added [0-9]+ document)", t))
skipped = len(re.findall(r"Mail account processing is already running", t))
bad = [m.group(0) for m in re.finditer(r"(?im)^.*(?:1366|operationalerror|mailbox.login|login failed|error while processing mail account).*$", t)]
print("LOG_LINES", t.count("\n"), "MAIL_CYCLES_RAN", ran, "SKIPPED", skipped, "ERRORS", len(bad))
for line in bad[:5]:
    print("  ", line[:200])
PY
# PASS: MAIL_CYCLES_RAN >= 1 AND ERRORS 0.
# MAIL_CYCLES_RAN is the positive control on the IDENTICAL stream: it proves the
# window covers at least one real post-roll mail cycle on the right container
# (measured by review 2026-09-26 on 3.1.3: 9 process_mail_accounts lines in the
# last 30 min, 'succeeded ... No new documents were added'). ERRORS 0 alone
# would also read 0 on a container that never ran a mail cycle.
# paperless_mail logs propagate to the root console handler (settings LOGGING,
# v3.2.1), so these strings DO reach `kubectl logs`. 3.2.1 catches MailError per
# account and still returns 'No new documents were added.', logging
# 'Error while processing mail account ...' - hence that pattern.
# MAIL_CYCLES_RAN 0 with SKIPPED > 0 = the #14189 cache lock: re-run this block
# once the new pod has been Ready > 35 min. MAIL_CYCLES_RAN 0 with SKIPPED 0 = FAIL.
```

> 3.2.1 (#14189): `Mail account processing is already running; skipping this
> run.` in the worker log for up to 30 min after the roll is the cache lock left
> by a fetch the roll killed, expiring on its TTL — **not** a failure. It becomes
> one only if it is still logged > 35 min after the new pod went Ready (the lock
> is renewed only by a *running* fetch).

### 4.7 — The RAG index must NOT have silently escalated to a full re-embed

```bash
kubectl exec -n office deploy/paperless-ngx -c paperless-ngx -- \
  python3 /usr/src/paperless/src/manage.py shell -c "
from paperless.config import AIConfig
from paperless_ai.embedding import get_configured_model_name
from paperless_ai.indexing import read_store
cfg = AIConfig()
print('AI', cfg.ai_enabled, cfg.llm_backend, cfg.llm_model)
with read_store() as s:
    print('MISMATCH', s.config_mismatch(get_configured_model_name(cfg)))
"
```

PASS: `MISMATCH False` (nightly `llm_index` stays incremental) and the AI row
still matches §2.4(c). 3.2.x adds no re-embed trigger to `src/paperless_ai/` (see §1.3), so a `True`
here means something else changed the row — investigate before closing.

## 5) Rollback

**`helm rollback` is NOT available**: `maxHistory: 1` means the pre-upgrade
revision is not retained. Roll back **forward through git**.

```bash
cd /Users/mu/code/cberg-home-nextgen
# Do NOT `git revert` the 3.7 commit: that also drops failureThreshold back to 30,
# and 3.1.3 must REBUILD the index v2 -> v1 at startup with the SAME
# sentinel-before-documents ordering (v3.1.3 _backend.py rebuild(): wipe_index ->
# _write_sentinels -> add_document loop) and WITHOUT 3.2.1's #14180 recovery.
# A 150 s budget would let the kubelet kill that rebuild and leave 3.1.3 Ready on
# a partial v1 index. After 3.9 a revert also conflicts. Edit the TAG only.
# (The validator stays :3.2.1 - 9557fa89, operator decision; do NOT touch it.)
# If migration 0026 must be reversed, do it BEFORE this edit, while 3.2.1 code is
# live (3.1.3 has no 0026 file to reverse to) - see below.
grep -q 'failureThreshold: 120' kubernetes/apps/office/paperless-ngx/app/helmrelease.yaml \
  || echo "3.9 ALREADY RESTORED - re-run the section 3.2 python edit FIRST, then continue"
sed -i '' 's|^      tag: "3.2.1"$|      tag: "3.1.3"|' \
  kubernetes/apps/office/paperless-ngx/app/helmrelease.yaml
grep -c 'tag: "3.1.3"' kubernetes/apps/office/paperless-ngx/app/helmrelease.yaml          # must print 1
grep -c 'failureThreshold: 120' kubernetes/apps/office/paperless-ngx/app/helmrelease.yaml  # must print 1
mkdir -p /private/tmp/claude-501/paperless-ngx-3.2.0
MSG=/private/tmp/claude-501/paperless-ngx-3.2.0/msg-paperless-ngx-3.2.0-rollback-$(date +%s).txt
printf 'revert(paperless-ngx): app image 3.2.1 -> 3.1.3 (rollback, startup budget kept raised)\n\nPlan: runbooks/maintenance/plans/paperless-ngx-3.2.0.md\n' > "$MSG"
git commit --only kubernetes/apps/office/paperless-ngx/app/helmrelease.yaml -F "$MSG"
git log -1 --format=%s && git show --stat HEAD
git push
rm -f /private/tmp/claude-501/paperless-ngx-3.2.0/roll-start && printf '3.1.3\n' > /private/tmp/claude-501/paperless-ngx-3.2.0/expect-tag
flux reconcile kustomization paperless-ngx -n office --with-source
# then run the section 3.8 poll block WITHOUT its `printf '3.2.1\n'` line (it
# must read expect-tag 3.1.3), and after the checks below pass run section 3.9
# (restore) - its gate then shows NO diff at all against the pre-3.7 file.
```

**The search index self-heals on the way back — verified in the 3.1.3 source.**
`v3.1.3`'s `needs_rebuild()` reads `.index_settings.json` and compares
`data.get("schema_version") != SCHEMA_VERSION` (which is `1` there). After the
upgrade the file says `2`, so the mismatch fires and the 3.1.3 container logs
`Search index schema version mismatch - rebuilding.` and rebuilds back to v1 at
startup. No manual step is required; expect the same not-Ready rebuild window as
the forward path. Nothing about the index is one-way.

**Migration 0026 does not need reversing**, and normally should not be: 3.1.3's
code is unaware of it, and both effects are inert there (an extra index on
`documents_document.archive_checksum`, plus one unused `rule_type` choice).
Django does not error on an applied migration it does not know. Reverse it only
if a later step demands a byte-exact schema, and only BEFORE the tag edit above
(while 3.2.1 code, which carries the migration files, is still running).
`paperless 0016` can be left applied too (its reverse is AlterField + a no-op
RunPython):

```bash
kubectl exec -n office deploy/paperless-ngx -c paperless-ngx -- \
  python3 /usr/src/paperless/src/manage.py migrate documents 0025
```

Both operations are `AlterField`, which is reversible — this is why
`rollback_class` is `git-revert` and not `backup-restore`.

**Confirm the cluster is back:**

```bash
kubectl get deploy -n office paperless-ngx scan-inbox-validator \
  -o custom-columns='NAME:.metadata.name,IMAGE:.spec.template.spec.containers[*].image'   # paperless-ngx :3.1.3, scan-inbox-validator :3.2.1 (the pre-plan split)
# the rollback KEEPS the §3.2 raises until section 3.9 runs after these checks
kubectl get deploy -n office paperless-ngx \
  -o jsonpath='{.spec.template.spec.containers[0].startupProbe.failureThreshold}{"\n"}'   # 120 (30 after 3.9)
kubectl exec -n office deploy/paperless-ngx -c paperless-ngx -- \
  python3 /usr/src/paperless/src/manage.py shell -c "
from paperless.version import __version__
from documents.models import Document
from documents.search import get_backend, SearchMode
print('VERSION', '.'.join(map(str, __version__)))
print('SETTINGS', open('/usr/src/paperless/data/index/.index_settings.json').read().strip())
db  = set(Document.objects.values_list('pk', flat=True))
idx = set(get_backend().search_ids('*', None, search_mode=SearchMode.QUERY))
print('MISSING_FROM_INDEX', len(db - idx))
print('HITS', len(get_backend().search_ids('rechnung', None, search_mode=SearchMode.TEXT)))
"
# expect VERSION 3.1.3, schema_version 1, MISSING_FROM_INDEX 0, HITS back at ~566 (NOT 0)
```

**Only if the index volume itself is damaged** (not for a failed upgrade): the
index is fully derived from the database and can always be rebuilt with
`document_index reindex --recreate`. Restore `paperless-data` from the Longhorn
backup (`docs/sops/backup.md` §"Restore from Backup") only if the volume is
lost — never as the first response to a bad upgrade.

Finally: clear the marker and drop the silence (it auto-expires after 3 h, but
leave nothing muted once the roll is settled either way).

```bash
runbooks/update-marker.sh clear paperless-ngx

# expire the §2.5 silence early, using the id §2.5 wrote to a FILE (agent Bash
# calls share no shell variables - $SIL_ID from §2.5 does not exist here)
SIL_ID=$(cat /private/tmp/claude-501/paperless-ngx-3.2.0/silence-id 2>/dev/null)
echo "SILENCE_ID ${SIL_ID:-NONE}"   # NONE -> use the list-and-match fallback below
kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 19093:9093 >/dev/null 2>&1 & PF=$!
sleep 2
curl -s -o /dev/null -w 'SILENCE_DELETE %{http_code}\n' -X DELETE "localhost:19093/api/v2/silence/$SIL_ID"
curl -s "localhost:19093/api/v2/silence/$SIL_ID" \
  | python3 -c "import sys,json;print('SILENCE_STATE', json.load(sys.stdin)['status']['state'])"
kill $PF 2>/dev/null
# expect SILENCE_DELETE 200 then SILENCE_STATE expired. If the file is empty,
# list and match on the comment instead (port 19093):
#   curl -s localhost:19093/api/v2/silences | python3 -c "
#   import sys,json
#   for s in json.load(sys.stdin):
#       if 'paperless-ngx 3.1.3->3.2.1' in s.get('comment',''):
#           print(s['id'], s['status']['state'])"
```

## 6) Interference notes

- **This plan now moves ONE pin; the other already moved.** Since
  `9557fa89` the validator runs `:3.2.1` and the app `:3.1.3` — an
  operator-sanctioned split. This plan ends it. Rollback re-opens the split
  (app back to 3.1.3, validator stays 3.2.1), which is the pre-plan state, not
  a new divergence. §4's image-parity check is the gate.
- **`conflicts_with: [paperless-db-13.0.2]` is a hard exclusion.** That plan
  scales `deployment/paperless-ngx` to 0, suspends this HelmRelease *and* this
  Kustomization, and does a one-way MariaDB datadir conversion on the same
  library. This plan runs a Django migration and needs a live writable DB for
  every assertion in §4. Never the same window, in either order. That plan is
  now `vetted` and slotted `sat-attended:2026-10-24` (re-read 2026-09-25), and
  since 2026-09-21 it lists `paperless-ngx-3.2.0` back — the pair is mutual.
  The plan_id was kept on the 3.2.1 retarget precisely so that ref still
  resolves.
- **The window's INSTRUMENT is not shared — but a shared surface IS touched.**
  §4 deliberately reads the paperless API, the pod and the served static assets
  — **never Prometheus** — so a same-slot `kube-prometheus-stack-91.4.1` cannot
  blind any gate in this plan, and no `conflicts_with` is declared on that
  basis. That is *not* the same as "monitoring is untouched": **§2.5 WRITES a
  silence into Alertmanager**, so `touches.shared` now names `monitoring`
  (corrected 2026-09-20 — it previously read `[]` and asserted the stack was not
  involved at all). `kube-prometheus-stack-91.4.1` declares
  `shared: [monitoring]`, touches `statefulset/alertmanager-kube-prometheus-stack`
  and documents a ~1 min Alertmanager blind spot during its restart. Consequence
  if they share a slot: **take the §2.5 silence AFTER that plan's Alertmanager
  restart has settled**, or the silence is created against an instance that is
  about to restart and the rebuild's not-Ready window pages the operator anyway.
  The §2.5 read-back gate (`SILENCE_STATE active`) is what catches that — it is
  the reason the silence is now verified rather than fire-and-forget.
  That plan does **not** list this one in `conflicts_with`; asymmetric
  declarations have been honoured symmetrically since 2026-09-15, so this stays
  a scheduling *warning* by design, not a veto.
- **`nextcloud-34.0.4` shares namespace `office` only.** No shared resource, no
  shared datastore, no shared volume (its `touches` are its own HelmRelease,
  Deployments, cron, PVC, MariaDB StatefulSet and Redis; `shared: []`).
  Namespace overlap alone is a warning, not a veto.
  **Window arithmetic, corrected 2026-09-20** — the earlier "45 + 50 against a
  90-min window is tight" compared two plans that are not in the same slot:
  `nextcloud-34.0.4` is scheduled `sun-attended:2026-09-20`, and **sun-attended
  is 200 min, not 90** (raised from 150 on 2026-09-12). That slot is also
  already carrying `absenty-drop-npm-runtime` (60 min) alongside it, both
  `awaiting-go`. **The slot this plan is sized against is `sat-attended`, which
  is the 90-min one** — 50 min of work there leaves a 40-min rollback budget.
  So the two plans are not competing for the same 90 minutes at all; if a
  scheduler ever does put them in one slot, sequence rather than parallelize.
- **A not-Ready pod is expected — but it is BOUNDED, and the kubelet is the
  first thing that would have killed it.** The index rebuild runs as a blocking
  s6 oneshot (`init-search-index` → `init-complete` → `svc-webserver`, verified
  live), so port 8000 does not listen while it runs — and the chart's
  `startupProbe` is a `tcpSocket` on exactly that port with a **150 s** budget
  (`failureThreshold: 30` × `periodSeconds: 5`). The no-op startup already eats
  28 s of it. **An earlier draft of this plan defended only against Flux and
  told the operator to expect a not-Ready pod — which would have trained them to
  watch the kubelet restart the container mid-rebuild.** §3.2 therefore raises
  three limits together (probe → 600 s, `spec.timeout` → 20 m, remediation off);
  raising only one just moves the failure to the next deadline. **§3.9 must
  restore all three** — left in place they permanently weaken startup detection,
  slow every future Helm operation, and remove Flux's rollback safety net from
  this app.
- **The rebuild's duration is the one number this plan could not measure, and
  it is not guessed at.** It cannot be measured without performing the upgrade.
  The corpus is measured — 973 documents, 5,197,578 characters of extracted text
  (~5.0 MB), 35 MB of on-disk index, `du -sm` live 2026-09-20 — but *how long
  tantivy takes to re-index that* is **unverified**. Rather than assert a
  number, §3.2 raises the budget far past any plausible value (600 s) and §3.8
  **records the actual `READY_AFTER`**. Feed that number into
  `docs/sops/paperless.md` afterwards: the next paperless bump should set a
  real budget, not another generous one. `est_duration_min: 50` covers the roll
  + verification + a 10-min worst-case rebuild inside the 90-min sat-attended
  slot.
- **`Recreate` on both Deployments is load-bearing**, not incidental:
  `paperless-data` is RWO on `longhorn-static` with `replicas: 1`. Under
  `RollingUpdate` the surge pod deadlocks on Multi-Attach. The premise
  `strategy-is-recreate` guards it.
- **Do not lower the 6Gi limit** to "make room" for anything. `OCR_MODE=force`
  OOM-kills at 3Gi on multi-page documents, and the rebuild adds a 512 MB
  tantivy writer budget on top.
- **The AI config row is not GitOps.** `ApplicationConfiguration` is a DB
  singleton; a DB restore silently resets it. §2.4(c) captures it and §4.7
  re-asserts it.
- **Repo correction (report, do not silently absorb):** the G3 breaking-change
  signal fired on a frontend `Chore:` line and missed the `SCHEMA_VERSION 1 -> 2`
  bump that forces a full index rebuild. The hold was correct; its stated reason
  was not. Worth a look at whether the release-notes scanner can see
  `SCHEMA_VERSION`/migration signals in the diff rather than only the notes prose.
