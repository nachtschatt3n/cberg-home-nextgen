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
target: "3.2.0"                        # released 2026-09-19; ghcr tag exists
                                       # (index digest sha256:22dc423ff48ac1629977dbf0c9625ba9f60d3bd1291a2ff173c65351984a14c2)
update_type: minor
risk: medium                           # NOT from the flagged ng-select line (frontend-only).
                                       # From the search-index rebuild: 3.2.0 bumps the
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
    - helmrelease/paperless-ngx                  # values.image.tag 3.1.3 -> 3.2.0
    - deployment/paperless-ngx                   # Recreate roll onto the new image
    - deployment/scan-inbox-validator            # SAME image, SECOND pin — must move in the
                                                 # same commit or the validator silently
                                                 # keeps running the retired 3.1.3 image
    - kustomization/paperless-ngx                # namespace `office` (NOT flux-system)
    - pvc/paperless-data                         # tantivy index under data/index REBUILT
                                                 # IN PLACE (RWO longhorn-static)
    - deployment/paperless-db                    # schema only: migration 0026 applied
                                                 # (two AlterFields); image NOT touched
  shared: []                           # Deliberate and checked. The app is exposed on the
                                       # PUBLIC edge (HTTPRoute paperless-ngx -> Gateway
                                       # envoy-external/https) but this plan does not touch
                                       # the route, the Gateway or any listener — it is a
                                       # consumer of that edge, not a perturber of it. It
                                       # rebuilds ONE longhorn-static volume's contents, not
                                       # the Longhorn control plane (same rationale the
                                       # paperless-db plans use). Verification reads the
                                       # paperless API and the pod directly and does NOT
                                       # read Prometheus, so the monitoring stack is not an
                                       # instrument of this plan — see §6.
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
                                       # Deliberately NOT listed: kube-prometheus-stack-91.4.0
                                       # (this plan's §4 never reads Prometheus) and
                                       # nextcloud-34.0.4 (namespace `office` overlap only —
                                       # no shared resource, no shared datastore).
security_ref: F-15987249               # AR-029-accepted on 3.1.3 under the "already on the
                                       # newest upstream tag" branch. 3.2.0 makes that premise
                                       # FALSE — a newer tag now exists, so the accepted-risk
                                       # rationale lapses and the bump is the household's only
                                       # sanctioned remedy for a third-party image (we bump,
                                       # we never rebuild). Detail stays on the finding record.
capability_change: true                # HONEST true, and it decides the execution class.
                                       # 3.2.0 changes ingest-time behaviour, not just the UI:
                                       # "Improve matching for correspondents, storage path and
                                       # labels by removing bias + adding minimum match
                                       # threshold" (#12164) alters auto-classification of
                                       # incoming documents, and "skip documents with empty
                                       # content in apply AI suggestions WF" (#13985) changes
                                       # when the AI workflow action fires. Both are
                                       # user-visible on the household's live ingestion path.
rollback_class: git-revert             # A real git revert, verified against the code paths:
                                       # the index self-heals on downgrade (§5) and both
                                       # migration operations are reversible AlterFields.
                                       # NOT backup-restore: nothing forward-only happens.
finding_refs: []                       # DELIBERATELY EMPTY, queried not assumed. With
                                       # SWEEP_PG_DSN up on 2026-09-20:
                                       #   finding list --section version --all  (80 rows)
                                       #   finding list --grep 'paperless-ngx' --all
                                       #   finding list --grep '3.2.0' --all
                                       # No finding exists for paperless-ngx 3.1.3 -> 3.2.0;
                                       # the only 3.2.0 rows are immich's, and every
                                       # paperless-ngx version row (3.0.5, 3.1.0, 3.1.3) is
                                       # RESOLVED. This update reached the queue from
                                       # coverage.py's needs_plan list, not from a finding, so
                                       # there is no PLAN-lane row to join and nothing to page
                                       # on. Same precedent and reasoning as
                                       # paperless-db-13.0.2. A `finding add` was deliberately
                                       # NOT made: `version` is a script-owned section, and an
                                       # agent-authored row there is auto-closed on the next
                                       # cycle.
status: draft
window: null                           # the scheduler assigns. Shape: attended (see
                                       # capability_change), no reboot, fits a 90-min
                                       # sat-attended slot with rollback budget to spare.
premises:
  - id: app-pin-is-3.1.3
    why: "`current:` claims 3.1.3 for the app. If the cluster already moved, this plan is stale and every baseline in section 2 is wrong."
    run: "kubectl get deploy -n office paperless-ngx -o jsonpath='{.spec.template.spec.containers[0].image}'"
    expect_exact: "ghcr.io/paperless-ngx/paperless-ngx:3.1.3"
  - id: validator-pin-is-3.1.3
    why: "The SECOND pin of the same image. This is the premise the whole plan exists to protect - if these two ever diverge, the scanner pipeline is running two paperless versions against one consume share."
    run: "kubectl get deploy -n office scan-inbox-validator -o jsonpath='{.spec.template.spec.containers[0].image}'"
    expect_exact: "ghcr.io/paperless-ngx/paperless-ngx:3.1.3"
  - id: repo-helmrelease-pin-is-3.1.3
    why: "The manifest the edit in section 3 targets. If HEAD no longer carries exactly one 3.1.3 tag line, the sed in step 3.3 would silently no-op or hit the wrong line."
    run: "git show HEAD:kubernetes/apps/office/paperless-ngx/app/helmrelease.yaml | grep -c 'tag: \"3.1.3\"'"
    expect_exact: "1"
  - id: repo-validator-pin-is-3.1.3
    why: "Same guard for the second file. Exactly one occurrence is what makes the sed in step 3.4 safe."
    run: "git show HEAD:kubernetes/apps/office/paperless-ngx/app/validator-deployment.yaml | grep -c 'paperless-ngx:3.1.3'"
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
---

# paperless-ngx 3.1.3 -> 3.2.0 (app + scan-inbox-validator, one commit)

## 1) Summary & why held

### 1.1 What moves

ONE image, pinned TWICE in the same app folder, moved together:

| Pin | File | Line |
|---|---|---|
| app | `kubernetes/apps/office/paperless-ngx/app/helmrelease.yaml` | 33 — `tag: "3.1.3"` |
| validator | `kubernetes/apps/office/paperless-ngx/app/validator-deployment.yaml` | 34 — `image: ghcr.io/paperless-ngx/paperless-ngx:3.1.3` |

`scan-inbox-validator` is **not a separate component**. It reuses the paperless
image for its `python3` + `pikepdf` runtime and overrides the entrypoint
(`command: ["python3", "/scripts/validator.py"]`). Both pins move in one commit
or the scanner pipeline runs two paperless versions against one consume share.
The SOP states this as a rule (`docs/sops/paperless.md` §2). There is no second
plan for the validator, by design.

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

   This is the risk. A rebuild that produces an *empty* index leaves every
   structural signal green — pod Ready, HTTP 200, HelmRelease Ready — while
   search silently returns nothing. That is exactly the shape-vs-contents
   failure class (`docs/sops/verification-contents-not-shape.md`), so §4 asserts
   hit *counts* against measured baselines, not index existence.

2. **One Django migration runs**: `0026_alter_document_archive_checksum_and_more`
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

- **RAG / LLM vector store**: zero files under `src/paperless_ai/` changed
  between v3.1.3 and v3.2.0, so no `REEMBED_REQUIRED` schema migration is
  triggered. The nightly `llm_index` task stays incremental. §4.7 re-asserts
  this rather than trusting it.
- **The validator's own runtime**: it overrides `command:`, so it bypasses
  s6-overlay entirely — it never runs migrations and never reindexes. It needs
  only `python3` + `pikepdf`, both still present. The Dockerfile diff removes
  only the **NLTK** data downloads (the classifier now preprocesses via Tantivy)
  and bumps the uv base 0.12.5 → 0.12.16, still `python3.14-trixie`.
- **Routing, storage classes, secrets, OCR env, the 6Gi limit**: untouched.
- **Security**: see `security_ref` in the frontmatter. Detail stays on the
  finding record — not in this file.

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
PPOD=$(kubectl get pod -n office -l app.kubernetes.io/name=paperless-ngx \
  --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}')

# (a) version + index sentinel + document count + REAL search hit counts
kubectl exec -n office "$PPOD" -c paperless-ngx -- \
  python3 /usr/src/paperless/src/manage.py shell -c "
from paperless.version import __version__
from documents.models import Document
from documents.search import get_backend, SearchMode
print('VERSION', '.'.join(map(str, __version__)))
print('SETTINGS', open('/usr/src/paperless/data/index/.index_settings.json').read().strip())
print('DOCS', Document.objects.count())
b = get_backend()
for term in ['rechnung','versicherung','vertrag','januar']:
    print('HITS', term, len(b.search_ids(term, None, search_mode=SearchMode.TEXT)))
"
```

Measured baseline on 3.1.3 (2026-09-20):

```
VERSION  3.1.3
SETTINGS {"schema_version": 1, "language": "de"}
DOCS     973
HITS rechnung 566 · versicherung 405 · vertrag 179 · januar 45
```

```bash
# (b) served UI bundle identity (the ng-select leg's baseline)
kubectl exec -n office "$PPOD" -c paperless-ngx -- python3 -c "
import hashlib
for p in ('/usr/src/paperless/static/frontend/en-US/main.js',
          '/usr/src/paperless/static/frontend/en-US/styles.css'):
    d = open(p,'rb').read()
    print(p.rsplit('/',1)[-1], len(d), hashlib.sha256(d).hexdigest()[:16])
"
# baseline 2026-09-20: main.js 2933613 c853f88fc4f28392 · styles.css 275917 2f620075dee0af2f

# (c) native-AI config row (DB-stored, NOT GitOps - a restore can silently reset it)
kubectl exec -n office "$PPOD" -c paperless-ngx -- \
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
kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 >/dev/null 2>&1 & PF=$!
sleep 2
NOW=$(python3 -c "from datetime import *;print(datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
END=$(python3 -c "from datetime import *;print((datetime.now(timezone.utc)+timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
curl -s -X POST localhost:9093/api/v2/silences -H 'Content-Type: application/json' -d '{
  "matchers":[{"name":"namespace","value":"office","isRegex":false,"isEqual":true},
              {"name":"alertname","value":"Kube(Pod|Deployment).*","isRegex":true,"isEqual":true}],
  "startsAt":"'$NOW'","endsAt":"'$END'","createdBy":"maintenance-window-agent",
  "comment":"paperless-ngx 3.1.3->3.2.0 - index rebuild keeps the pod not-Ready for minutes. auto-expires 2h"}'
kill $PF 2>/dev/null

runbooks/update-marker.sh add paperless-ngx office 2 "3.1.3->3.2.0 + full search index rebuild"
```

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
  "https://ghcr.io/v2/paperless-ngx/paperless-ngx/manifests/3.2.0" | grep -iE '^HTTP|docker-content-digest'
# expect HTTP/2 200 and
# docker-content-digest: sha256:22dc423ff48ac1629977dbf0c9625ba9f60d3bd1291a2ff173c65351984a14c2
```

**3.2 — Disable Flux upgrade remediation for this run.** This is not optional
here. The HelmRelease carries `upgrade.remediation.retries: 1` **and**
`maxHistory: 1`. The new pod stays not-Ready for the whole index rebuild; if
that outruns the Helm timeout, Flux rolls the release back *mid-rebuild* — the
exact "Recreate + Flux rollback thrash" trap in `docs/sops/application-update.md`
§2. Edit `helmrelease.yaml` lines 21-24 to:

```yaml
  upgrade:
    cleanupOnFail: true
    remediation:
      retries: 0
      remediateLastFailure: false   # RESTORE to retries:1 in step 3.9
```

**3.3 — Bump the app pin.** BSD sed, dry-tested on a scratch copy 2026-09-20:

```bash
sed -i '' 's|^      tag: "3.1.3"$|      tag: "3.2.0"|' \
  kubernetes/apps/office/paperless-ngx/app/helmrelease.yaml
```

Resulting diff line (verified):

```
33c33
<       tag: "3.1.3"
---
>       tag: "3.2.0"
```

**3.4 — Bump the validator pin** (the step that is silently skipped if you only
read the HelmRelease). Dry-tested on a scratch copy:

```bash
sed -i '' 's|ghcr.io/paperless-ngx/paperless-ngx:3.1.3|ghcr.io/paperless-ngx/paperless-ngx:3.2.0|' \
  kubernetes/apps/office/paperless-ngx/app/validator-deployment.yaml
```

Resulting diff line (verified):

```
34c34
<           image: ghcr.io/paperless-ngx/paperless-ngx:3.1.3
---
>           image: ghcr.io/paperless-ngx/paperless-ngx:3.2.0
```

**3.5 — Prove BOTH pins moved and nothing else did:**

```bash
grep -n '3\.2\.0' kubernetes/apps/office/paperless-ngx/app/helmrelease.yaml \
                  kubernetes/apps/office/paperless-ngx/app/validator-deployment.yaml
# expect EXACTLY two lines: helmrelease.yaml:33 and validator-deployment.yaml:34
grep -rn '3\.1\.3' kubernetes/apps/office/paperless-ngx/
# expect NO hits
git diff --stat
# expect exactly 2 files changed
```

**3.6 — Validate the manifests:**

```bash
kubeconform -summary -exit-on-error -ignore-missing-schemas \
  kubernetes/apps/office/paperless-ngx/
```

**3.7 — Commit with `--only` (shared worktree) and verify the subject is YOURS
before pushing.** Two sessions committing in the same second can swap message
files:

```bash
cat > /tmp/paperless-320-msg.txt <<'EOF'
feat(container): update ghcr.io/paperless-ngx/paperless-ngx ( 3.1.3 -> 3.2.0 )

Moves BOTH pins of the image in lockstep: the HelmRelease values tag and the
scan-inbox-validator Deployment, which reuses the same image for its python3 +
pikepdf runtime.

3.2.0 bumps the tantivy search SCHEMA_VERSION 1 -> 2, so the full-text index is
rebuilt from the database at container start (s6 init-search-index runs
document_index reindex --if-needed). Django migration 0026 also applies.

Flux upgrade remediation is temporarily disabled so the rollback cannot fire
mid-rebuild; restored in a follow-up commit.

Plan: runbooks/maintenance/plans/paperless-ngx-3.2.0.md
EOF

git commit --only \
  kubernetes/apps/office/paperless-ngx/app/helmrelease.yaml \
  kubernetes/apps/office/paperless-ngx/app/validator-deployment.yaml \
  -F /tmp/paperless-320-msg.txt

git log -1 --format=%s        # MUST be the paperless subject above; amend if not
git show --stat HEAD          # MUST be exactly the two files above
git push
```

**3.8 — Watch the reconcile and the rebuild.** Expect the pod to sit not-Ready
while the index rebuilds; that is the plan working, not failing:

```bash
flux reconcile kustomization paperless-ngx -n office --with-source
kubectl get pods -n office -l app.kubernetes.io/name=paperless-ngx -w   # Ctrl-C when 1/1

# the rebuild's own log line:
PPOD=$(kubectl get pod -n office -l app.kubernetes.io/name=paperless-ngx \
  --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}')
kubectl logs -n office "$PPOD" -c paperless-ngx | grep -iE 'init-index|schema version mismatch|fingerprint mismatch|up to date|reindex'
```

Record how long the pod took to reach Ready — it sizes every future paperless
bump.

**3.9 — After §4 passes, restore remediation** (`retries: 1`,
`remediateLastFailure` removed) and commit with `--only` + the same
subject check.

## 4) Verification

Floor first (necessary, NOT sufficient):

```bash
kubectl get hr -n office paperless-ngx \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion}{"\n"}'
# expect: True 0.24.1   (chart unchanged - only the image moved)
kubectl get deploy -n office paperless-ngx scan-inbox-validator \
  -o custom-columns='NAME:.metadata.name,IMAGE:.spec.template.spec.containers[*].image'
# BOTH must read ...:3.2.0  - this is SOP paperless.md section 6.6, image parity
kubectl get pods -n office -l app.kubernetes.io/name=paperless-ngx \
  -o custom-columns='READY:.status.containerStatuses[0].ready,RESTARTS:.status.containerStatuses[0].restartCount'
```

> Verify the running pod's image, not `kubectl rollout status` — that reports
> success against the OLD generation mid-HelmRelease-upgrade.

### CONTENTS ASSERTION 1 — the index actually migrated AND is not empty

**The property:** the rebuilt index holds the whole library, on schema v2.
**Measured by:** the sentinel file + a live document count, in one call.
**Compared to:** §2.4(a).

```bash
PPOD=$(kubectl get pod -n office -l app.kubernetes.io/name=paperless-ngx \
  --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n office "$PPOD" -c paperless-ngx -- \
  python3 /usr/src/paperless/src/manage.py shell -c "
from paperless.version import __version__
from documents.models import Document
print('VERSION', '.'.join(map(str, __version__)))
print('SETTINGS', open('/usr/src/paperless/data/index/.index_settings.json').read().strip())
print('DOCS', Document.objects.count())
"
```

PASS: `VERSION 3.2.0`; `SETTINGS` shows `"schema_version": 2` **and** a
`"schema_fingerprint"` key; `DOCS` is 973 (or 974 after the §4 CA3 test doc).

What failure prints: a rebuild that never ran leaves `"schema_version": 1` with
no fingerprint — and because 3.2.0's `needs_rebuild()` returns True on that, the
pod would be looping the rebuild rather than serving. A rebuild that ran against
an empty/wrong database prints `DOCS 0` while the pod is perfectly Ready.

> **Do NOT assert on `data/index/meta.json` segment sums.** Measured live:
> `sum(max_doc)` = 976 against 973 real documents — segment bookkeeping counts
> superseded segments. An equality check there fails on a healthy index.

### CONTENTS ASSERTION 2 — search still returns the same documents

**The property:** the rebuilt v2 index is *queryable* and holds the same
content, not merely the same count.
**Measured by:** four real term queries.
**Compared to:** the §2.4(a) baseline (2026-09-20: 566 / 405 / 179 / 45).

```bash
kubectl exec -n office "$PPOD" -c paperless-ngx -- \
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
kubectl exec -n office "$PPOD" -c paperless-ngx -- \
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
kubectl exec -n office "$PPOD" -c paperless-ngx -- \
  python3 /usr/src/paperless/src/manage.py shell -c "
from documents.bulk_edit import reprocess
from documents.models import Document
d = Document.objects.order_by('-added').first()
print('REPROCESS', d.pk); reprocess([d.pk])
"
# wait ~60s, then re-run the SEARCHABLE check above for that pk
```

### CONTENTS ASSERTION 4 — the validator runs the new image and still works

**The property:** the second pin moved *and* the new image can still run the
validator loop (it needs `python3` + `pikepdf`; the 3.2.0 Dockerfile dropped the
NLTK data, so prove what it kept rather than assuming).

```bash
kubectl get deploy -n office scan-inbox-validator \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'   # must be :3.2.0
kubectl exec -n office deploy/scan-inbox-validator -- \
  python3 -c "import pikepdf, sys; print('PIKEPDF', pikepdf.__version__, 'PY', sys.version.split()[0])"
# heartbeat must ADVANCE - run twice, ~20s apart
kubectl exec -n office deploy/scan-inbox-validator -- \
  python3 -c "import os; print(os.path.getmtime('/tmp/validator.heartbeat'))"
```

PASS: image is `:3.2.0`, `PIKEPDF` prints a version, and the second heartbeat is
larger than the first. What failure prints: `ModuleNotFoundError: pikepdf`, or a
frozen mtime — a validator that is Running but whose loop is dead (the liveness
probe would take ~3 min to notice).

### CONTENTS ASSERTION 5 — the frontend bundle actually changed

**The property:** the ng-select v24 rebuild produced a *different, plausible*
bundle, and it is actually served. A bundler change fails silently as a
different bundle, not as a failed build.
**Compared to:** §2.4(b) (`main.js` 2933613 bytes / `c853f88fc4f28392`).

```bash
kubectl exec -n office "$PPOD" -c paperless-ngx -- python3 -c "
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

kubectl logs -n office "$PPOD" -c paperless-ngx --since=30m \
  | grep -iE "1366|operationalerror|mailbox.login|login failed"
# expect NO hits (grep is case-insensitive on purpose - upstream mixes case)
```

### 4.7 — The RAG index must NOT have silently escalated to a full re-embed

```bash
kubectl exec -n office "$PPOD" -c paperless-ngx -- \
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
still matches §2.4(c). `src/paperless_ai/` is untouched by 3.2.0, so a `True`
here means something else changed the row — investigate before closing.

## 5) Rollback

**`helm rollback` is NOT available**: `maxHistory: 1` means the pre-upgrade
revision is not retained. Roll back **forward through git**.

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <sha-of-step-3.7>     # restores BOTH pins to 3.1.3 together
git log -1 --format=%s && git show --stat HEAD
git push
flux reconcile kustomization paperless-ngx -n office --with-source
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
if a later step demands a byte-exact schema:

```bash
kubectl exec -n office "$PPOD" -c paperless-ngx -- \
  python3 /usr/src/paperless/src/manage.py migrate documents 0025
```

Both operations are `AlterField`, which is reversible — this is why
`rollback_class` is `git-revert` and not `backup-restore`.

**Confirm the cluster is back:**

```bash
kubectl get deploy -n office paperless-ngx scan-inbox-validator \
  -o custom-columns='NAME:.metadata.name,IMAGE:.spec.template.spec.containers[*].image'   # both :3.1.3
kubectl exec -n office "$PPOD" -c paperless-ngx -- \
  python3 /usr/src/paperless/src/manage.py shell -c "
from paperless.version import __version__
from documents.search import get_backend, SearchMode
print('VERSION', '.'.join(map(str, __version__)))
print('SETTINGS', open('/usr/src/paperless/data/index/.index_settings.json').read().strip())
print('HITS', len(get_backend().search_ids('rechnung', None, search_mode=SearchMode.TEXT)))
"
# expect VERSION 3.1.3, schema_version 1, HITS back at ~566 (NOT 0)
```

**Only if the index volume itself is damaged** (not for a failed upgrade): the
index is fully derived from the database and can always be rebuilt with
`document_index reindex --recreate`. Restore `paperless-data` from the Longhorn
backup (`docs/sops/backup.md` §"Restore from Backup") only if the volume is
lost — never as the first response to a bad upgrade.

Finally: clear the marker and drop the silence.

```bash
runbooks/update-marker.sh clear paperless-ngx
```

## 6) Interference notes

- **This plan moves TWO pins of one image.** Any vetting that checks only
  `helmrelease.yaml` will believe the work is done while
  `scan-inbox-validator` still runs 3.1.3. §4's image-parity check is the gate.
- **`conflicts_with: [paperless-db-13.0.2]` is a hard exclusion.** That plan
  scales `deployment/paperless-ngx` to 0, suspends this HelmRelease *and* this
  Kustomization, and does a one-way MariaDB datadir conversion on the same
  library. This plan runs a Django migration and needs a live writable DB for
  every assertion in §4. Never the same window, in either order. That plan is
  currently `blocked`, so the collision is latent, not live.
  **Reciprocity gap to report:** `paperless-db-13.0.2` does not list
  `paperless-ngx-3.2.0` (it predates this file). `--validate` checks that refs
  resolve, not that they are mutual — whoever next edits that plan should add
  the back-reference.
- **The window's instrument is not shared here.** §4 deliberately reads the
  paperless API, the pod and the served static assets — **never Prometheus** —
  so a same-night `kube-prometheus-stack-91.4.0` does not blind this plan's
  verification, and no conflict is declared on that basis.
- **`nextcloud-34.0.4` shares namespace `office` only.** No shared resource, no
  shared datastore, no shared volume. Namespace overlap alone is a warning, not
  a veto; they can share a slot if the clock allows (45 + 50 against a 90-min
  attended window is tight — sequence, do not parallelize).
- **Expect a not-Ready pod for minutes, and do not treat it as failure.** The
  index rebuild runs as a blocking s6 oneshot before the app serves. This is why
  step 3.2 disables Flux remediation: with `retries: 1` + `maxHistory: 1`, a
  rebuild that outruns the Helm timeout gets rolled back mid-flight and
  `helm rollback` cannot reach the previous revision. **Step 3.9 must restore
  `retries: 1` — a plan that leaves remediation off silently removes Flux's
  safety net from this app forever.**
- **The rebuild's duration is the one number this plan could not measure**
  (it cannot run without doing the upgrade). 973 documents / ~35 MB of index on
  a healthy Longhorn volume should be minutes, and `est_duration_min: 50`
  budgets for it, but **record the actual Ready time in §3.8** — it sizes every
  future paperless bump and belongs in the SOP afterwards.
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
