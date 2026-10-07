---
plan_id: scan-inbox-validator-3.3.0
component: scan-inbox-validator
also_covers: [paperless-ngx]             # SAME image, SAME commit. scan-inbox-validator
                                         # reuses ghcr.io/paperless-ngx/paperless-ngx for
                                         # its python3+pikepdf runtime; docs/sops/paperless.md
                                         # §2 + §6a.6 require both pins to move together.
                                         # Renovate PR #308 itself edits BOTH files. Without
                                         # this key coverage.py would read the paperless-ngx
                                         # row as unplanned and dispatch a second planner for
                                         # the identical bump (F-dc4066f9 / F-d71bc523 shape).
pr: 308                                  # feat(container): update ghcr.io/paperless-ngx/
                                         # paperless-ngx ( 3.2.1 → 3.3.0 ) — touches
                                         # helmrelease.yaml + validator-deployment.yaml,
                                         # all 4 checks green (Flate Render Gate SUCCESS).
                                         # NOT merged by this plan: §3 commits the tag move
                                         # together with the startup-budget raise in ONE
                                         # commit on main; Renovate closes #308 itself.
kind: image
current: "3.2.1"                         # live-verified 2026-10-07: BOTH deployments run
                                         # ghcr.io/paperless-ngx/paperless-ngx:3.2.1;
                                         # paperless.version 3.2.1
target: "3.3.0"                          # ghcr index digest sha256:6b94799bc769a063b3340cc5847402e626d4d91d29a295a8e747f8e9bead4207
                                         # == the digest ghcr `latest` resolves to
                                         # (read 2026-10-07) -> stable channel
update_type: minor
risk: medium                             # Three ADDITIVE, reversible Django migrations
                                         # (CreateModel + 2 nullable AddField) on the only
                                         # copy of the document DB, plus a forced full
                                         # tantivy index rebuild (SCHEMA_VERSION 2 -> 3) at
                                         # container start. Same shape as paperless-ngx-3.2.0,
                                         # which executed green 2026-09-26 (a94d749e).
est_duration_min: 60                     # 50 (the executed 3.2.0 plan's measured budget:
                                         # roll + rebuild + verification + restore roll)
                                         # + ~10 for the pre-migration logical dump (§3.1)
needs_reboot: false
touches:
  namespaces: [office]
  resources:
    - helmrelease/paperless-ngx                  # values.image.tag + 3 temporary raises (§3.2)
    - deployment/paperless-ngx                   # Recreate roll onto 3.3.0, then a 2nd roll (§3.8 restore)
    - deployment/scan-inbox-validator            # image tag 3.2.1 -> 3.3.0 (Recreate)
    - kustomization/paperless-ngx                # namespace office (NOT flux-system)
    - pvc/paperless-data                         # tantivy index under data/index REBUILT in place
    - deployment/paperless-db                    # SCHEMA ONLY: documents 0027, paperless 0017+0018
                                                 # applied by s6 init-migrations; image untouched
  shared: []                                     # No Alertmanager silence is written (see §6), no
                                                 # route/Gateway/listener change: the app is a
                                                 # CONSUMER of the public edge (HTTPRoute ->
                                                 # envoy-external), not a perturber of it. One
                                                 # longhorn-static volume's CONTENTS, not the
                                                 # Longhorn control plane. The CIFS consume/inbox
                                                 # shares are mounted, not reconfigured.
depends_on: []
conflicts_with:
  - paperless-db-13.0.2          # HARD. Scales deployment/paperless-ngx to 0, suspends this HR + KS,
                                 # one-way MariaDB datadir conversion of the SAME DB this plan migrates.
  - kube-prometheus-stack-91.9.0 # §4 CONTROL reads Prometheus (restart counter, memory alert) —
                                 # the window's instrument is shared infra (README rule).
  - redis-fleet-8.10.2           # restarts deployment/paperless-redis (celery broker + the #14189
                                 # mail-fetch cache lock) AND lists deployment/paperless-ngx; it would
                                 # confound §4.6's mail-cycle gate and the consume round-trip.
  - flux-fleet-0.60.0            # restarts helm-controller/kustomize-controller mid-roll; §3 depends on
                                 # helm-controller honouring timeout 20m / retries 0 for this release.
  - flux-distribution-2.9.6      # same reason as flux-fleet-0.60.0.
  - flux-oci-chart-sources       # moves THIS HelmRelease's chart source (gabe565 -> OCI); both plans
                                 # edit helmrelease.yaml.
  - helm-drift-detection         # changes HR drift/remediation behaviour fleet-wide; this plan holds
                                 # remediation OFF on this HR for the duration of the roll.
  - flux-reconciler-impersonation  # re-wires every Kustomization's reconciler identity incl. office.
exclusive: false
security_ref: null                       # Version-currency driver; the brief carried no
                                         # security evidence. Note only (ids, no detail):
                                         # the AR-029 rows F-e6b70b55 and F-46d1bfdc are
                                         # pinned to the :3.2.1 tag string and will lapse
                                         # / re-evaluate when the tag moves. Detail stays
                                         # on the finding records.
capability_change: true                  # HONEST true. 3.3.0 ships new features and API
                                         # surface (#14276 stored barcode contents + a new
                                         # documents_documentbarcode model and API/search
                                         # field; #14067 separate embedding API key; #14202
                                         # LLM extra params), and CHANGES the publicly
                                         # reachable /admin/ login: #14270 wraps
                                         # admin.site.login in allauth secure_admin_login
                                         # (measured 3.2.1 baseline: GET /admin/login/ -> 200,
                                         # Django's own password form). #14356 changes
                                         # ProcessedMail ownership semantics.
rollback_class: git-revert               # Nothing forward-only: all three migrations have
                                         # Django-generated reverses (CreateModel ->
                                         # DeleteModel, AddField -> RemoveField), and the
                                         # index self-heals on downgrade (3.2.1's
                                         # needs_rebuild() sees schema_version 3 != 2).
                                         # The §3.1 logical dump is INSURANCE for one
                                         # anomaly only — a migration that half-applies on
                                         # MariaDB (non-transactional DDL) — see §5.3.
finding_refs: [F-b40c9350, F-6b6c515a]   # queried 2026-10-07 with SWEEP_PG_DSN up:
                                         # F-b40c9350 "scan-inbox-validator: image
                                         # ghcr.io/paperless-ngx/paperless-ngx 3.2.1 → 3.3.0
                                         # (minor)" (version, status new) and F-6b6c515a
                                         # "paperless-ngx: image ... 3.2.1 → 3.3.0 (minor)"
                                         # (version, status new). Both are answered by this
                                         # one commit.
review: null
status: draft
window: null                             # Planner note, not a claim: HUMAN-GATED
                                         # (capability_change), attended, no reboot; sized
                                         # for a sat-attended slot (90 min: 60 of work +
                                         # 30 rollback budget). NOT sat-attended:2026-10-24
                                         # (holds paperless-db-13.0.2) and NOT the same
                                         # night as kube-prometheus-stack-91.9.0.
premises:
  - id: app-pin-is-3.2.1
    why: "current: claims 3.2.1 for the app. If the cluster already moved, every baseline in section 2 is wrong."
    run: "kubectl get deploy -n office paperless-ngx -o jsonpath='{.spec.template.spec.containers[0].image}'"
    expect_exact: "ghcr.io/paperless-ngx/paperless-ngx:3.2.1"
  - id: validator-pin-is-3.2.1
    why: "The second pin of the same image. Both must start in parity, or a post-upgrade failure cannot be attributed."
    run: "kubectl get deploy -n office scan-inbox-validator -o jsonpath='{.spec.template.spec.containers[0].image}'"
    expect_exact: "ghcr.io/paperless-ngx/paperless-ngx:3.2.1"
  - id: repo-helmrelease-pin-is-3.2.1
    why: "The anchored edit in step 3.2 needs exactly one tag line with 3.2.1 in HEAD, or it aborts on its own assert."
    run: "git show HEAD:kubernetes/apps/office/paperless-ngx/app/helmrelease.yaml | grep -c 'tag: \"3.2.1\"'"
    expect_exact: "1"
  - id: repo-validator-pin-is-3.2.1
    why: "Same guard for the validator pin."
    run: "git show HEAD:kubernetes/apps/office/paperless-ngx/app/validator-deployment.yaml | grep -c 'paperless-ngx:3.2.1'"
    expect_exact: "1"
  - id: helmrelease-ready-on-chart-0.24.1
    why: "A not-Ready or drifted HelmRelease means something else is mid-flight. Only values change here, never the chart."
    run: "kubectl get hr -n office paperless-ngx -o jsonpath='{.status.conditions[?(@.type==\"Ready\")].status} {.status.history[0].chartVersion}'"
    expect_exact: "True 0.24.1"
  - id: kustomization-ready
    why: "The Flux Kustomization lives in namespace office. A failing reconcile would make the push in step 3.4 land somewhere unobservable."
    run: "kubectl get kustomization -n office paperless-ngx -o jsonpath='{.status.conditions[?(@.type==\"Ready\")].status}'"
    expect_exact: "True"
  - id: startup-budget-is-stock
    why: "30 = the stock 150 s budget restored by 4577d3ea. Anything else means a previous raise was never restored, and the restore anchors in step 3.8 would not match."
    run: "kubectl get deploy -n office paperless-ngx -o jsonpath='{.spec.template.spec.containers[0].startupProbe.failureThreshold}'"
    expect_exact: "30"
  - id: memory-limit-still-6gi
    why: "OCR_MODE=force OOM-kills at 3Gi; the rebuild adds a 512 MB tantivy writer heap on top."
    run: "kubectl get deploy -n office paperless-ngx -o jsonpath='{.spec.template.spec.containers[0].resources.limits.memory}'"
    expect_exact: "6Gi"
  - id: strategy-is-recreate
    why: "paperless-data is RWO longhorn-static at replicas 1; RollingUpdate deadlocks on Multi-Attach."
    run: "kubectl get deploy -n office paperless-ngx -o jsonpath='{.spec.strategy.type}'"
    expect_exact: "Recreate"
  - id: index-volume-healthy
    why: "The index is rebuilt in place on this volume."
    run: "kubectl get volume -n storage paperless-data -o jsonpath='{.status.state} {.status.robustness}'"
    expect_exact: "attached healthy"
  - id: db-volume-healthy
    why: "The migrations write to the only copy of the document DB."
    run: "kubectl get volume -n storage paperless-db-data -o jsonpath='{.status.state} {.status.robustness}'"
    expect_exact: "attached healthy"
  - id: db-still-on-12.3.3
    why: "If paperless-db-13.0.2 has run, every DB baseline here predates a datadir conversion and must be re-taken; the dump procedure in 3.1 was written against 12.3.3."
    run: "kubectl get deploy -n office paperless-db -o jsonpath='{.spec.template.spec.containers[0].image}'"
    expect_exact: "mariadb:12.3.3"
  - id: validator-is-up
    why: "The validator must be healthy BEFORE the bump, or a post-upgrade failure cannot be attributed to the new image."
    run: "kubectl get deploy -n office scan-inbox-validator -o jsonpath='{.status.readyReplicas}'"
    expect_exact: "1"
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/paperless.md
  - docs/sops/backup.md
  - docs/sops/longhorn.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-10-07"
---

# paperless-ngx + scan-inbox-validator 3.2.1 -> 3.3.0 (both pins, one commit)

## 1) Summary & why held

### 1.1 What moves

One image, pinned twice in `kubernetes/apps/office/paperless-ngx/app/`:

| Pin | File | Line (HEAD 2026-10-07) |
|---|---|---|
| app | `helmrelease.yaml` | 33: `tag: "3.2.1"` |
| validator | `validator-deployment.yaml` | 34: `image: ghcr.io/paperless-ngx/paperless-ngx:3.2.1` |

**Lockstep: YES, both move in this plan, in one commit.** `scan-inbox-validator`
is not a separate component. It reuses the paperless image only for `python3` +
`pikepdf` and overrides the entrypoint (`command: ["python3",
"/scripts/validator.py"]`), so it bypasses s6. It never runs migrations and never
touches the index. Moving it alone would be safe for the DB. But the SOP rule
(`docs/sops/paperless.md` §2, verification test §6a.6) is image parity, and
Renovate PR #308 already edits both files. Splitting them would buy nothing.
The DB/index risk is entirely on the **app** pin.

### 1.2 Why it was held, and whether the hold is right

Gate reason (coverage.py, cycle 288980ff): *"G3 structural signal: migration/schema
change in the diff: new migration file
src/documents/migrations/0027_documentbarcode.py; src/documents/search/_schema.py:
SCHEMA_VERSION"*. **The hold is correct**, and this time the signal found the real
thing. The 3.2.0 hold had fired on a frontend `Chore:` line. Read from the actual
`v3.2.1...v3.3.0` tree diff (local clone, 96 commits, so the GitHub
compare API's 300-file cap does not apply):

**(a) Three Django migrations, all additive:**

| Migration | Operation | Effect here |
|---|---|---|
| `documents/0027_documentbarcode` | `CreateModel DocumentBarcode` (page, value, format, FK `document` CASCADE) | new table `documents_documentbarcode`, empty. Rows are written only when `barcode_store_values` is on (see (c)) |
| `paperless/0017_applicationconfiguration_llm_embedding_api_key` | `AddField` CharField(1024) **null=True** | nullable column on the singleton config row |
| `paperless/0018_applicationconfiguration_barcode_store_values` | `AddField` BooleanField **null=True** | nullable column; NULL means "fall back to env" |

No `RunPython`, no `AlterField` on existing data, no data rewrite. Every operation
has a Django-generated reverse. Live state 2026-10-07: `documents` at
`0026_alter_document_archive_checksum_and_more`, `paperless` at
`0016_alter_applicationconfiguration_ai_enabled`, `documents_documentbarcode`
absent, 74 tables in `paperless`. The migrations run automatically at container
start (s6 `init-migrations`), **before** the index check
(`init-search-index/dependencies.d/init-migrations` at v3.3.0).

**(b) The full-text index is force-rebuilt again.** `src/documents/search/_schema.py`:

```python
# v3 - barcodes JSON field for stored barcode contents
SCHEMA_VERSION: Final[int] = 3
```

Live sentinel 2026-10-07: `{"schema_version": 2, "language": "de",
"schema_fingerprint": "71d5…"}`, so `needs_rebuild()` logs
`Search index schema version mismatch - rebuilding.` and the whole index is rebuilt
inside the blocking s6 oneshot. **Port 8000 does not listen until it finishes**,
and the chart's `startupProbe` is a `tcpSocket` on 8000 with a 150 s budget.

`TantivyBackend.rebuild()` at v3.3.0 keeps the trap the 3.2.0 plan documented. The
order is `wipe_index` → `tantivy.Index(...)` → `_write_sentinels()` → the
`add_document` loop → `commit`. Its `except BaseException` restores only the
**in-memory** index pointer. So a rebuild that is killed partway (probe, OOM, node event) leaves a
v3 sentinel over a partial index. The next boot then comes up Ready on it. §4 CA1
(index-side membership) is the gate for this. The sentinel alone is not.

Measured budget (`docs/sops/paperless.md` §6a.4): the 3.1.3→3.2.1 rebuild was
`READY_AFTER` 115 s for 977 documents, against a stock 150 s budget. The SOP
instruction for the next schema bump is *"raise the startup failureThreshold for
the roll (and restore it after)"*. The library is now 994 documents. §3.2 follows
that SOP with the three raises that executed cleanly on 2026-09-26.

**(c) Behaviour/capability changes** (hence `capability_change: true`):
- #14276: barcode contents can be stored, listed and searched. This is **off by
  default**: `BarcodeConfig.barcode_store_values` = config row (NULL after 0018) →
  `settings.CONSUMER_STORE_BARCODE_VALUES` = `PAPERLESS_CONSUMER_STORE_BARCODE_VALUES`,
  which is unset. So 3.3.0 changes nothing at ingest here. §4 CA7 asserts it.
- #14270: `admin.site.login = secure_admin_login(admin.site.login)`, and the route
  is anchored `^admin/`. The `/admin/` path is reachable on the **public edge**
  (HTTPRoute → `envoy-external`, no SecurityPolicy). Measured on 3.2.1:
  `GET /admin/login/` → **200**, which is Django's own password form and sidesteps
  allauth MFA. After 3.3.0 an unauthenticated request should be redirected to the
  allauth login instead. This tightens security. §4 CA8 asserts it.
- #14356: ProcessedMail owner always follows the mail-rule owner.
- #14343: `PAPERLESS_LOGROTATE_MAX_SIZE/_BACKUPS`, `PAPERLESS_EMAIL_PORT`,
  `PAPERLESS_CONSUMER_POLLING_INTERVAL` and `THREADS_PER_WORKER` are now parsed
  with `get_int_from_env`/`get_float_from_env`. Our values are `"1048576"`, `"2"`,
  `587` and `10`, all valid numerics, so they do not trip the new parsers.
- #14254: interactive **bash** shells now source `/run/s6/container_environment`.
  The validator uses `python3` only and is unaffected.

### 1.3 What is NOT affected (checked in the v3.3.0 tree)

- **Validator runtime.** The Python base stays `uv:0.12.23-python3.14-trixie-slim`
  (was 0.12.16, same 3.14 line). `pikepdf` goes **10.2.0 → 10.13.0.post1**. The
  validator uses only `pikepdf.open(path)` and `len(pdf.pages)`
  (`validator-configmap.yaml:47-48`), and both still exist. §4 CA4 exercises exactly
  those two calls on a real PDF. A bare import check is not enough.
- **RAG vector store.** `src/paperless_ai/` changes only `client.py`
  (`additional_kwargs=llm_extra_params`, `{}` by default) and `embedding.py`
  (embedding API key fallback chain, used by the openai-like backend only; ours is
  `ollama`). There is no vector-store schema change and no `REEMBED_REQUIRED`. §4 CA7
  re-asserts `MISMATCH False`.
- **Chart, routing, secrets, OCR env, 6Gi limit, DB image.** Untouched.

## 2) Pre-checks

Any non-zero exit aborts **before** the first edit.

```bash
cd /Users/mu/code/cberg-home-nextgen
set -euo pipefail
ST=/private/tmp/claude-501/scan-inbox-validator-3.3.0; mkdir -p "$ST"

# 2.1 premises (13, fail-closed)
.venv/bin/python3 runbooks/plan-premises.py scan-inbox-validator-3.3.0 --require-premises

# 2.2 backups FRESH (< 26h) for BOTH volumes this plan writes to.
# Negative control measured 2026-10-07: `--max-hours 1` on paperless-data -> STALE rc 1.
python3 runbooks/longhorn-backup-age.py paperless-db-data --max-hours 26
python3 runbooks/longhorn-backup-age.py paperless-data    --max-hours 26

# 2.3 the target tag resolves (never bump to an unpublished tag)
TOKEN=$(curl -s --max-time 20 "https://ghcr.io/token?scope=repository:paperless-ngx/paperless-ngx:pull&service=ghcr.io" \
  | python3 -c "import sys,json;print(json.load(sys.stdin).get('token',''))")
DIG=$(curl -s --max-time 20 -o /dev/null -D - -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/vnd.oci.image.index.v1+json" \
  "https://ghcr.io/v2/paperless-ngx/paperless-ngx/manifests/3.3.0" \
  | awk 'tolower($1)=="docker-content-digest:"{print $2}' | tr -d '\r')
echo "digest=$DIG"
case "$DIG" in sha256:*) ;; *) echo "ABORT: 3.3.0 has no resolvable digest"; exit 1;; esac
# Measured 2026-10-07: 3.3.0 -> sha256:6b94799b… (200); 3.3.0-nope -> 404, empty -> ABORT.

# 2.4 consume/inbox backlog EMPTY (a wedged file would be misread as an upgrade failure)
B=$(kubectl exec -n office deploy/scan-inbox-validator -- sh -c \
  'echo $(ls -1 /consume/*.pdf 2>/dev/null | wc -l) $(ls -1 /inbox/*.pdf 2>/dev/null | wc -l)')
echo "backlog consume/inbox: $B"; [ "$B" = "0 0" ] || { echo "ABORT: backlog not empty"; exit 1; }
```

### 2.5 Baselines (§4 compares against THESE files, never against numbers typed here)

```bash
set -euo pipefail
ST=/private/tmp/claude-501/scan-inbox-validator-3.3.0
kubectl exec -n office deploy/paperless-ngx -c paperless-ngx -- \
  python3 /usr/src/paperless/src/manage.py shell -c "
from paperless.version import __version__
from documents.models import Document
from documents.search import get_backend, SearchMode
from paperless.config import AIConfig
b = get_backend()
db  = set(Document.objects.values_list('pk', flat=True))
idx = set(b.search_ids('*', None, search_mode=SearchMode.QUERY))
print('VERSION', '.'.join(map(str, __version__)))
print('DOCS', len(db)); print('MISSING_FROM_INDEX', len(db - idx))
for t in ['rechnung','versicherung','vertrag','januar']:
    print('HITS', t, len(b.search_ids(t, None, search_mode=SearchMode.TEXT)))
c = AIConfig(); print('AI', c.ai_enabled, c.llm_backend, c.llm_model, c.llm_embedding_backend, c.llm_embedding_model)
" | grep -E '^(VERSION|DOCS|MISSING_FROM_INDEX|HITS|AI) ' > "$ST/app-pre.txt"
cat "$ST/app-pre.txt"
grep -q '^VERSION 3.2.1$' "$ST/app-pre.txt"           || { echo "ABORT: baseline not taken on 3.2.1"; exit 1; }
grep -q '^MISSING_FROM_INDEX 0$' "$ST/app-pre.txt"    || { echo "ABORT: index already incomplete BEFORE the upgrade"; exit 1; }
[ "$(grep -c '^HITS ' "$ST/app-pre.txt")" -eq 4 ]     || { echo "ABORT: hit baseline incomplete"; exit 1; }

kubectl exec -n office deploy/paperless-db -- sh -c 'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" -N -B -e "
 SELECT \"TABLES\", COUNT(*) FROM information_schema.tables WHERE table_schema=\"paperless\";
 SELECT \"NONUTF8MB4\", COUNT(*) FROM information_schema.tables WHERE table_schema=\"paperless\" AND table_collation NOT LIKE \"utf8mb4%\";
 SELECT \"DOCROWS\", COUNT(*) FROM paperless.documents_document;
 SELECT \"CANARY\", COUNT(*) FROM paperless.paperless_mail_processedmail WHERE HEX(subject) LIKE \"%F09F%\";"' \
 > "$ST/db-pre.txt"
cat "$ST/db-pre.txt"
awk '$1=="TABLES"{t=$2} $1=="NONUTF8MB4"{n=$2} $1=="CANARY"{c=$2} END{exit !(t==74 && n==0 && c>0)}' "$ST/db-pre.txt" \
  || { echo "ABORT: DB baseline not 74 tables / all utf8mb4 / canary>0"; exit 1; }
```

Measured 2026-10-07 on 3.2.1, for orientation only: `DOCS 994`,
`MISSING_FROM_INDEX 0`, `EXTRA 0`, HITS 578 / 416 / 187 / 48, `AI True ollama
gemma4:26b-mlx ollama nomic-embed-text:latest`, 74 tables, all utf8mb4, CANARY 1,
validator `PIKEPDF 10.2.0 PY 3.14.7`. *Can the gates fail?* An exec that fails
writes an empty file. Every `grep -q`/`awk` limb above then exits 1, so an empty
baseline cannot pass.

```bash
runbooks/update-marker.sh add paperless-ngx office 2 "3.2.1->3.3.0 + migrations 0027/0017/0018 + index rebuild"
```

## 3) Steps

### 3.1 Pre-migration logical dump (insurance for §5.3, the only non-revert path)

The app keeps running. `--single-transaction` gives a consistent InnoDB snapshot.
`--default-character-set=utf8mb4` is **not optional**. Without it 4-byte
characters become `?`, which is how a Nextcloud rollback floor was destroyed on
2026-08-19. The block is fail-closed and adapted from the reviewed
`paperless-db-13.0.2` §3.2.

```bash
set -euo pipefail
ST=/private/tmp/claude-501/scan-inbox-validator-3.3.0
mkdir -p ~/backups/paperless-db && chmod 0700 ~/backups/paperless-db
DUMP=~/backups/paperless-db/paperless-pre-3.3.0-$(date +%Y%m%d%H%M).sql
printf '%s\n' "$DUMP" > "$ST/dump-path"          # §5.3 reads THIS file, never $DUMP
kubectl -n office exec deploy/paperless-db -- sh -c \
  'mariadb-dump --default-character-set=utf8mb4 --single-transaction --routines --events \
   --databases paperless -uroot -p"$MARIADB_ROOT_PASSWORD"' > "$DUMP"
chmod 0600 "$DUMP"
tail -1 "$DUMP" | grep -q -- '-- Dump completed' || { echo "ABORT: dump incomplete"; exit 1; }
T=$(grep -c '^CREATE TABLE' "$DUMP" || true); echo "CREATE TABLE=$T"
[ "$T" -ge 74 ] || { echo "ABORT: $T CREATE TABLE, expected >=74"; exit 1; }
grep -qE '^CREATE TABLE `documents_document` ' "$DUMP" || { echo "ABORT: no documents_document"; exit 1; }
S=$(wc -c < "$DUMP" | tr -d ' '); echo "bytes=$S"
[ "$S" -gt 10000000 ] || { echo "ABORT: $S bytes (the 12.3.3-era all-db dump was ~25.8 MB)"; exit 1; }
FB(){ /usr/bin/python3 -c "import sys;print(sum(1 for l in open(sys.argv[1],'rb') if any(0xf0<=b<=0xf4 for b in l)))" "$1"; }
printf 'ascii\nemoji \xf0\x9f\x93\x84 here\n' > "$ST/ctl.txt"
[ "$(FB "$ST/ctl.txt")" -eq 1 ] || { echo "ABORT: 4-byte checker broken (positive control)"; exit 1; }
[ "$(FB "$DUMP")" -gt 0 ]      || { echo "ABORT: dump lost 4-byte content"; exit 1; }
echo "DUMP GATE PASSED — $DUMP"
```

Why `--databases paperless` and not `--all-databases`: the restore in §5.3 replaces
only the `paperless` schema, and the `mysql` system tables are not touched by this
plan. The `>=74` count is therefore exact for this dump. It cannot be satisfied by
system tables, which the 13.0.2 plan had to work around. The size floor has
**not** been measured on a paperless-only dump. The DB holds 37 MB of
data+index (`information_schema`, 2026-10-07), so ~25 MB of SQL is expected. If
the floor trips on a genuinely complete dump (trailer present, 74 tables, 4-byte
content present), record the real size and lower the floor deliberately. Do not
bypass the gate.

### 3.2 One commit: both tags + the three temporary rebuild raises

The raises match the executed `paperless-ngx-3.2.0` plan (§3.2 there; restored by
`4577d3ea`):

| Deadline | Stock | For this roll | Why |
|---|---|---|---|
| kubelet `startupProbe` | 30 × 5 s = 150 s | **120 × 5 s = 600 s** | kills the container mid-rebuild → v3 sentinel over a partial index |
| Helm `spec.timeout` | 5m (unset) | **20m** | Helm would fail the release under a long rebuild |
| `upgrade.remediation` | retries 1 | **retries 0, remediateLastFailure false** | a Flux rollback mid-rebuild would roll 3.2.1 onto a half-migrated DB |

```bash
cd /Users/mu/code/cberg-home-nextgen
python3 - <<'PY'
import pathlib
p = pathlib.Path("kubernetes/apps/office/paperless-ngx/app/helmrelease.yaml")
s = p.read_text()
edits = [
 ("spec:\n  interval: 30m\n",
  "spec:\n  interval: 30m\n  timeout: 20m                    # RESTORE (remove) in step 3.8\n"),
 ("  upgrade:\n    cleanupOnFail: true\n    remediation:\n      retries: 1\n",
  "  upgrade:\n    cleanupOnFail: true\n    remediation:\n"
  "      retries: 0                    # RESTORE to 1 in step 3.8\n"
  "      remediateLastFailure: false   # RESTORE (remove) in step 3.8\n"),
 ("    image:\n      repository: ghcr.io/paperless-ngx/paperless-ngx\n      tag: \"3.2.1\"\n",
  "    probes:\n      startup:\n        spec:\n"
  "          failureThreshold: 120     # RESTORE to 30 in step 3.8\n"
  "    image:\n      repository: ghcr.io/paperless-ngx/paperless-ngx\n      tag: \"3.3.0\"\n"),
]
for old, new in edits:
    assert s.count(old) == 1, f"anchor not unique/found: {old[:50]!r}"
    s = s.replace(old, new)
p.write_text(s)
v = pathlib.Path("kubernetes/apps/office/paperless-ngx/app/validator-deployment.yaml")
t = v.read_text()
old = "          image: ghcr.io/paperless-ngx/paperless-ngx:3.2.1\n"
assert t.count(old) == 1, "validator anchor not unique/found"
v.write_text(t.replace(old, "          image: ghcr.io/paperless-ngx/paperless-ngx:3.3.0\n"))
print("FORWARD EDIT OK")
PY
```

Dry-tested 2026-10-07 on a scratch copy of both files (macOS). The exact result:

```diff
@@ -6,6 +6,7 @@
 spec:
   interval: 30m
+  timeout: 20m                    # RESTORE (remove) in step 3.8
@@ -21,16 +22,21 @@
     remediation:
-      retries: 1
+      retries: 0                    # RESTORE to 1 in step 3.8
+      remediateLastFailure: false   # RESTORE (remove) in step 3.8
@@
         allowInsecureImages: true
+    probes:
+      startup:
+        spec:
+          failureThreshold: 120     # RESTORE to 30 in step 3.8
     image:
       repository: ghcr.io/paperless-ngx/paperless-ngx
-      tag: "3.2.1"
+      tag: "3.3.0"
--- validator-deployment.yaml
34c34
<           image: ghcr.io/paperless-ngx/paperless-ngx:3.2.1
>           image: ghcr.io/paperless-ngx/paperless-ngx:3.3.0
```

A second run aborts on the remediation anchor **before** writing anything, so the
edit is not partially re-applied. Proof that the probe key reaches the container:
`helm template gabe565/paperless-ngx --version 0.24.1` with the edited values
renders `image: ghcr.io/paperless-ngx/paperless-ngx:3.3.0` and `startupProbe:
failureThreshold: 120, periodSeconds: 5`. Liveness and readiness stay at
3 × 10 s (rendered 2026-10-07).

### 3.3 Prove scope, then validate

```bash
grep -n '3\.3\.0' kubernetes/apps/office/paperless-ngx/app/helmrelease.yaml \
                  kubernetes/apps/office/paperless-ngx/app/validator-deployment.yaml
# expect EXACTLY two lines (helmrelease tag, validator image)
grep -rn 'paperless-ngx:3\.2\.1\|tag: "3\.2\.1"' kubernetes/apps/office/paperless-ngx/ && { echo "STOP: a 3.2.1 pin survived"; exit 1; } || true
git diff --stat -- kubernetes/apps/office/paperless-ngx/     # PATH-SCOPED: shared worktree
# expect 2 files changed
kubeconform -summary -exit-on-error -ignore-missing-schemas kubernetes/apps/office/paperless-ngx/
```

### 3.4 Commit (`--only`) and verify the subject is yours, then push

```bash
ST=/private/tmp/claude-501/scan-inbox-validator-3.3.0
MSG=$ST/msg-forward-$(date +%s).txt
cat > "$MSG" <<'EOF'
feat(container): update ghcr.io/paperless-ngx/paperless-ngx ( 3.2.1 -> 3.3.0 )

Moves the app (HelmRelease values) and scan-inbox-validator pins together
(image parity, docs/sops/paperless.md). Supersedes Renovate PR #308.

3.3.0 applies three additive Django migrations at startup (documents 0027
DocumentBarcode, paperless 0017/0018 nullable config columns) and bumps the
tantivy SCHEMA_VERSION 2 -> 3, which rebuilds the full-text index before the
webserver listens. Temporarily raised for this roll, restored in a follow-up:
startup failureThreshold 30 -> 120, spec.timeout 20m, upgrade remediation off.

Plan: runbooks/maintenance/plans/scan-inbox-validator-3.3.0.md
EOF
git fetch origin main && git merge --ff-only origin/main
git commit --only \
  kubernetes/apps/office/paperless-ngx/app/helmrelease.yaml \
  kubernetes/apps/office/paperless-ngx/app/validator-deployment.yaml \
  -F "$MSG"
git log -1 --format=%s     # MUST be the subject above; amend before push if not
git show --stat HEAD       # MUST be exactly the two files above
git rev-parse HEAD > "$ST/commit-forward.sha"
git push origin main
```

### 3.5 Watch the roll against a clock

```bash
ST=/private/tmp/claude-501/scan-inbox-validator-3.3.0
[ -s "$ST/roll-start" ] || date +%s > "$ST/roll-start"
flux reconcile kustomization paperless-ngx -n office --with-source
python3 - <<'PY'
import json, re, subprocess, time
st = "/private/tmp/claude-501/scan-inbox-validator-3.3.0"
hr = open("/Users/mu/code/cberg-home-nextgen/kubernetes/apps/office/paperless-ngx/app/helmrelease.yaml").read()
tags = re.findall(r'(?m)^      tag: "([^"]+)"$', hr)
fts = re.findall(r'(?m)^          failureThreshold: ([0-9]+)', hr)
assert len(tags) == 1 and len(fts) <= 1, (tags, fts)
want, want_ft = tags[0], (int(fts[0]) if fts else 30)
print("WANT tag=%s startup.failureThreshold=%d" % (want, want_ft))
start = int(open(st + "/roll-start").read()); deadline = time.time() + 540
while time.time() < deadline:
    raw = subprocess.run(["kubectl","get","pods","-n","office","-l","app.kubernetes.io/name=paperless-ngx","-o","json"],
                         capture_output=True, text=True).stdout or '{"items":[]}'
    for p in json.loads(raw)["items"]:
        if p["metadata"].get("deletionTimestamp"): continue
        c0 = p["spec"]["containers"][0]
        ft = (c0.get("startupProbe") or {}).get("failureThreshold")
        if not (c0.get("image","").endswith(":"+want) and ft == want_ft):
            print(time.strftime("%H:%M:%S"), p["metadata"]["name"], "PRE_ROLL_POD ignored", flush=True); continue
        cs = (p["status"].get("containerStatuses") or [{}])[0]
        print(time.strftime("%H:%M:%S"), p["metadata"]["name"], "ready=%s restarts=%s" % (cs.get("ready"), cs.get("restartCount",0)), flush=True)
        if cs.get("restartCount", 0):
            print("RESTARTED_DURING_ROLL - CA1 is now the gate; check the live probe threshold")
        if cs.get("ready") and cs.get("image","").endswith(":"+want):
            ra = int(time.time()) - start; open(st + "/ready-after","w").write(str(ra))
            print("READY_AFTER %ds" % ra); raise SystemExit(0)
    time.sleep(15)
print("STILL_NOT_READY %ds since roll start" % (int(time.time()) - start)); raise SystemExit(1)
PY
kubectl logs -n office deploy/paperless-ngx -c paperless-ngx \
  | grep -iE 'apply(ing)? .*(0027|0017|0018)|init-migrations|init-index|schema version mismatch|corrupted or incomplete|up to date'
```

The poll is the 3.2.0 plan's reviewed form. It waits for a pod whose **spec**
matches the committed file, so the old Ready pod cannot satisfy it. If it prints
`STILL_NOT_READY`, re-run the same block; it resumes from the files. Past 660 s
total, go to §5. **Expected logs:** `Applying documents.0027_documentbarcode... OK`,
`Applying paperless.0017_... OK`, `Applying paperless.0018_... OK`, then
`Search index schema version mismatch - rebuilding.`, then Ready. **Act, do not
wait,** if `restarts` increments while not Ready. That is the probe killing the
rebuild, which should be impossible at 600 s. Check
`kubectl get deploy -n office paperless-ngx -o jsonpath='{.spec.template.spec.containers[0].startupProbe.failureThreshold}'`
(must print `120`).

Record `READY_AFTER` in the close-out and in `docs/sops/paperless.md` §6a.4. It
is the second measured point for that budget.

### 3.6 Validator roll

The validator rolls in the same reconcile (Recreate, no probes beyond liveness).
§4 CA4 verifies it. Nothing to do here except not to skip CA4.

### 3.7 Run §4 in full before §3.8

### 3.8 Restore the three raises (second commit, second roll)

```bash
cd /Users/mu/code/cberg-home-nextgen
ST=/private/tmp/claude-501/scan-inbox-validator-3.3.0
python3 - <<'PY'
import pathlib
p = pathlib.Path("kubernetes/apps/office/paperless-ngx/app/helmrelease.yaml")
s = p.read_text()
edits = [
 ("  timeout: 20m                    # RESTORE (remove) in step 3.8\n", ""),
 ("      retries: 0                    # RESTORE to 1 in step 3.8\n"
  "      remediateLastFailure: false   # RESTORE (remove) in step 3.8\n", "      retries: 1\n"),
 ("    probes:\n      startup:\n        spec:\n"
  "          failureThreshold: 120     # RESTORE to 30 in step 3.8\n", ""),
]
for old, new in edits:
    assert s.count(old) == 1, f"restore anchor not unique/found: {old[:40]!r}"
    s = s.replace(old, new)
p.write_text(s); print("RESTORE OK")
PY
git diff "$(cat "$ST/commit-forward.sha")^" -- kubernetes/apps/office/paperless-ngx/app/helmrelease.yaml
```

**GATE:** the diff against the pre-forward file shows **exactly one hunk:
`-      tag: "3.2.1"` / `+      tag: "3.3.0"`**. This was dry-tested 2026-10-07 on
the scratch copy: forward then restore printed `33c33 < tag: "3.2.1" > tag:
"3.3.0"` and nothing else. Any surviving `timeout:`, `retries: 0`,
`remediateLastFailure` or `probes:` line means the restore is incomplete. Commit
with `--only kubernetes/apps/office/paperless-ngx/app/helmrelease.yaml`, check
`git log -1 --format=%s` and `git show --stat HEAD`, then push. Subject:
`fix(paperless-ngx): restore startup probe, helm timeout and upgrade remediation after 3.3.0 roll`.
This changes the pod template, so a **second Recreate roll** follows. The index is
already v3, so expect `Search index is up to date.` and a ~96 s start. Run
`rm "$ST/roll-start"`, then the §3.5 poll again (it now wants threshold 30), then
CA1 once more. Then confirm live:

```bash
kubectl get deploy -n office paperless-ngx -o jsonpath='{.spec.template.spec.containers[0].startupProbe.failureThreshold}{"\n"}'  # 30
kubectl get hr -n office paperless-ngx -o jsonpath='timeout=[{.spec.timeout}] retries={.spec.upgrade.remediation.retries}{"\n"}'   # timeout=[] retries=1
runbooks/update-marker.sh clear paperless-ngx
```

## 4) Verification

Floor (necessary, not sufficient):

```bash
kubectl get hr -n office paperless-ngx -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion}{"\n"}'   # True 0.24.1
kubectl get pods -n office -l 'app.kubernetes.io/name in (paperless-ngx,scan-inbox-validator)' \
  -o custom-columns='NAME:.metadata.name,IMAGE:.status.containerStatuses[0].image,READY:.status.containerStatuses[0].ready,RESTARTS:.status.containerStatuses[0].restartCount'
# BOTH running pods show ...:3.3.0 (SOP §6a.6 parity), READY true, RESTARTS 0.
# Read the RUNNING pod's image (status), not rollout status — that green-lights the old generation.
```

**CONTENTS ASSERTION 1: every document is in the rebuilt v3 index.** This is
measured by the set difference between DB primary keys and the ids the **index**
returns, compared to `$ST/app-pre.txt`.

```bash
ST=/private/tmp/claude-501/scan-inbox-validator-3.3.0
kubectl exec -n office deploy/paperless-ngx -c paperless-ngx -- \
  python3 /usr/src/paperless/src/manage.py shell -c "
from paperless.version import __version__
from documents.models import Document
from documents.search import get_backend, SearchMode
b = get_backend()
print('VERSION', '.'.join(map(str, __version__)))
print('SETTINGS', open('/usr/src/paperless/data/index/.index_settings.json').read().strip())
db  = set(Document.objects.values_list('pk', flat=True))
idx = set(b.search_ids('*', None, search_mode=SearchMode.QUERY))
print('DOCS', len(db)); print('INDEXED', len(idx)); print('MISSING_FROM_INDEX', len(db - idx))
for t in ['rechnung','versicherung','vertrag','januar']:
    print('HITS', t, len(b.search_ids(t, None, search_mode=SearchMode.TEXT)))
" | grep -E '^(VERSION|SETTINGS|DOCS|INDEXED|MISSING_FROM_INDEX|HITS) ' | tee "$ST/app-post.txt"
python3 - <<'PY'
st="/private/tmp/claude-501/scan-inbox-validator-3.3.0"
def load(f):
    d={}
    for l in open(f):
        k,_,v=l.strip().partition(' ')
        if k=='HITS': t,n=v.split(); d['HITS '+t]=int(n)
        else: d[k]=v
    return d
a,b=load(st+"/app-pre.txt"),load(st+"/app-post.txt")
ok=True
def chk(c,m):
    global ok; print(("PASS " if c else "FAIL ")+m); ok&=c
chk(b.get('VERSION')=='3.3.0', "version %s" % b.get('VERSION'))
chk('"schema_version": 3' in b.get('SETTINGS',''), "sentinel v3")
chk(b.get('MISSING_FROM_INDEX')=='0', "MISSING_FROM_INDEX %s" % b.get('MISSING_FROM_INDEX'))
chk(int(b.get('DOCS',0)) >= int(a['DOCS']), "DOCS %s >= pre %s" % (b.get('DOCS'), a['DOCS']))
for k in [k for k in a if k.startswith('HITS ')]:
    pre,post=a[k],b.get(k,0)
    chk(post>0 and abs(post-pre) <= max(2, pre*0.05), "%s pre=%d post=%d (>0 and within 5%%)" % (k,pre,post))
raise SystemExit(0 if ok else 1)
PY
```

PASS: every line `PASS`, exit 0. **What the guarded failure prints:** a rebuild
killed after `_write_sentinels()` shows `VERSION 3.3.0`, sentinel v3 and `DOCS`
unchanged, which are three green limbs, while `MISSING_FROM_INDEX` is large and
`HITS … post=0`. That is exactly the shape the 3.2.0 review caught (§1.2(b)).
`DOCS` is a database count and never touches the index. A missing
`app-post.txt` line makes `b.get` return the default, so the limb FAILs and does
not pass. If `search_ids` raises, the exec prints a traceback, `app-post.txt`
lacks the lines, and the check FAILs.

**CONTENTS ASSERTION 2: the migrations landed, the new table obeys the charset
invariant, and no rows were lost.** Compared to `$ST/db-pre.txt`.

```bash
ST=/private/tmp/claude-501/scan-inbox-validator-3.3.0
kubectl exec -n office deploy/paperless-db -- sh -c 'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" -N -B -e "
 SELECT \"TABLES\", COUNT(*) FROM information_schema.tables WHERE table_schema=\"paperless\";
 SELECT \"NONUTF8MB4\", COUNT(*) FROM information_schema.tables WHERE table_schema=\"paperless\" AND table_collation NOT LIKE \"utf8mb4%\";
 SELECT \"BARCODE_COLL\", table_collation FROM information_schema.tables WHERE table_schema=\"paperless\" AND table_name=\"documents_documentbarcode\";
 SELECT \"BARCODE_ROWS\", COUNT(*) FROM paperless.documents_documentbarcode;
 SELECT \"DOCROWS\", COUNT(*) FROM paperless.documents_document;
 SELECT \"CANARY\", COUNT(*) FROM paperless.paperless_mail_processedmail WHERE HEX(subject) LIKE \"%F09F%\";
 SELECT \"MIG\", app, name FROM paperless.django_migrations WHERE (app=\"documents\" AND name LIKE \"0027%\") OR (app=\"paperless\" AND name IN (\"0017_applicationconfiguration_llm_embedding_api_key\",\"0018_applicationconfiguration_barcode_store_values\"));"' \
 | tee "$ST/db-post.txt"
python3 - <<'PY'
st="/private/tmp/claude-501/scan-inbox-validator-3.3.0"
pre={l.split()[0]:l.split()[1] for l in open(st+"/db-pre.txt") if l.strip()}
post=[l.split() for l in open(st+"/db-post.txt") if l.strip()]
g={r[0]:r[1:] for r in post if r[0]!="MIG"}; mig=[r for r in post if r[0]=="MIG"]
res=[("TABLES 75", g.get("TABLES")==["75"]),
     ("NONUTF8MB4 0", g.get("NONUTF8MB4")==["0"]),
     ("barcode table utf8mb4", (g.get("BARCODE_COLL") or [""])[0].startswith("utf8mb4")),
     ("BARCODE_ROWS 0 (store off)", g.get("BARCODE_ROWS")==["0"]),
     ("DOCROWS >= pre", int((g.get("DOCROWS") or ["0"])[0]) >= int(pre["DOCROWS"])),
     ("CANARY == pre", g.get("CANARY")==[pre["CANARY"]]),
     ("3 migrations recorded", len(mig)==3)]
for m,c in res: print(("PASS " if c else "FAIL ")+m)
raise SystemExit(0 if all(c for _,c in res) else 1)
PY
```

*Can it fail?* If 0027 did not run, the `documents_documentbarcode` SELECT
errors, so `mariadb -e` aborts at that statement. The later rows never print and
`DOCROWS`/`CANARY`/`MIG` FAIL. A wrong-charset new table (the 2026-08-30 1366
class) FAILs `NONUTF8MB4 0`. An empty `db-post.txt` FAILs every limb.

**CONTENTS ASSERTION 3: the real consume path ingests AND indexes against schema
v3.** This is an attended step. Scan a 2-3 page document on the ES-580W
"paperless" preset (`docs/sops/paperless.md` §6.2). Do not re-feed a duplicate:
`CONSUMER_DELETE_DUPLICATES=true` drops it silently. Do not use a near-blank page:
under `OCR_MODE=force` it can ParseError and wedge the consumer.

```bash
kubectl logs -n office deploy/scan-inbox-validator --since=15m | grep -i 'moved -> consume'
kubectl exec -n office deploy/paperless-ngx -c paperless-ngx -- \
  python3 /usr/src/paperless/src/manage.py shell -c "
from documents.models import Document
from documents.search import get_backend, SearchMode
d = Document.objects.order_by('-added').first()
print('NEWEST', d.pk, d.added)
print('SEARCHABLE', d.pk in get_backend().search_ids(d.title.split()[0], None, search_mode=SearchMode.TEXT))
" | grep -E '^(NEWEST|SEARCHABLE) '
```

PASS: a `moved -> consume` line, `NEWEST` added after the roll, `SEARCHABLE True`.
This is the only gate that proves `add_or_update` writes against the v3 schema.
An index that rejects writes reads `SEARCHABLE False`, and a dead validator shows
no `moved` line. Fallback, only with no scanner access and strictly weaker:
`documents.bulk_edit.reprocess([pk])` on the newest document, then the same
`SEARCHABLE` check.

**CONTENTS ASSERTION 4: the validator's real code path works on 3.3.0.**
pikepdf jumped 10.2.0 → 10.13.0. This exercises the exact calls the validator
uses on a real PDF, not just an import, and checks the loop turns.

```bash
kubectl exec -n office deploy/scan-inbox-validator -- python3 -c "
import pikepdf, sys, os, time
p='/tmp/ca4.pdf'; pdf=pikepdf.new(); pdf.add_blank_page(); pdf.save(p)
with pikepdf.open(p) as q: n=len(q.pages)
os.remove(p)
bad='/tmp/ca4-bad.pdf'; open(bad,'wb').write(b'%PDF-1.7 truncated')
try:
    pikepdf.open(bad); rej=False
except Exception: rej=True
os.remove(bad)
a=os.path.getmtime('/tmp/validator.heartbeat'); time.sleep(25); b=os.path.getmtime('/tmp/validator.heartbeat')
print('PIKEPDF', pikepdf.__version__, 'PY', sys.version.split()[0], 'PAGES', n, 'REJECTS_BAD', rej, 'HEARTBEAT', 'ADVANCED' if b>a else 'FROZEN')
"
```

PASS: `PAGES 1 REJECTS_BAD True HEARTBEAT ADVANCED` on a pod whose image is
`:3.3.0` (floor). The two limbs guard different failures. `REJECTS_BAD True` is
the validator's QC function: a pikepdf that opened garbage would pass broken
scans to paperless. `PAGES 1` proves the happy path still counts pages. A loop
that is Running but dead prints `FROZEN`; the liveness probe takes ~3 min to
notice that.

**CONTENTS ASSERTION 5: mail ingestion still runs and still writes 4-byte
subjects.** This reuses the reviewed `paperless-ngx-3.2.0` §4.6 block, with the
state dir changed to `$ST`.

```bash
ST=/private/tmp/claude-501/scan-inbox-validator-3.3.0
kubectl logs -n office deploy/paperless-ngx -c paperless-ngx --since=30m > "$ST/app-30m.log"
python3 - <<'PY'
import re
t=open("/private/tmp/claude-501/scan-inbox-validator-3.3.0/app-30m.log").read()
ran=len(re.findall(r"process_mail_accounts\[[^\]]+\] succeeded in [0-9.]+s: '(?:No new documents were added|Added [0-9]+ document)", t))
skipped=len(re.findall(r"Mail account processing is already running", t))
bad=[m.group(0) for m in re.finditer(r"(?im)^.*(?:\(1366,|operationalerror|mailbox.login|login failed|error while processing mail account).*$", t)]
print("LOG_LINES", t.count("\n"), "MAIL_CYCLES_RAN", ran, "SKIPPED", skipped, "ERRORS", len(bad))
for l in bad[:5]: print("  ", l[:200])
PY
```

PASS: `MAIL_CYCLES_RAN >= 1` **and** `ERRORS 0`. `MAIL_CYCLES_RAN` is the positive
control on the same stream: `ERRORS 0` alone also reads 0 on a container that never
ran a cycle. If `SKIPPED > 0` and `RAN 0`, the #14189 30-min cache lock is still
held from the killed fetch, so re-run once the pod has been Ready > 35 min.
`RAN 0` with `SKIPPED 0` is a FAIL.

**CONTENTS ASSERTION 6: the RAG store did not escalate to a full re-embed, and
the AI row is intact.**

```bash
kubectl exec -n office deploy/paperless-ngx -c paperless-ngx -- \
  python3 /usr/src/paperless/src/manage.py shell -c "
from paperless.config import AIConfig
from paperless_ai.embedding import get_configured_model_name
from paperless_ai.indexing import read_store
c = AIConfig()
print('AI', c.ai_enabled, c.llm_backend, c.llm_model, c.llm_embedding_backend, c.llm_embedding_model)
with read_store() as s: print('MISMATCH', s.config_mismatch(get_configured_model_name(c)))
" | grep -E '^(AI|MISMATCH) '
```

PASS: `MISMATCH False` and the `AI` line is byte-identical to the one in
`$ST/app-pre.txt`. A missing line counts as a FAIL.

**CONTENTS ASSERTION 7: the barcode capability did NOT switch itself on.**

```bash
kubectl exec -n office deploy/paperless-ngx -c paperless-ngx -- \
  python3 /usr/src/paperless/src/manage.py shell -c "
from paperless.config import BarcodeConfig
print('BARCODE_STORE', BarcodeConfig().barcode_store_values)
" | grep '^BARCODE_STORE '
```

PASS: `BARCODE_STORE False`, with CA2's `BARCODE_ROWS 0`. If this reads `True`,
an env var or the config row turned on a feature this plan did not approve.
Report it. Do not "fix" it in-window.

**CONTENTS ASSERTION 8: the public `/admin/` login moved behind allauth (#14270).**

```bash
kubectl port-forward -n office svc/paperless-ngx 18000:8000 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s --max-time 10 -o /dev/null -w 'ADMIN_LOGIN code=%{http_code} loc=%{redirect_url}\n' http://localhost:18000/admin/login/
curl -s --max-time 10 -o /dev/null -w 'API_ROOT code=%{http_code}\n' http://localhost:18000/api/
kill $PF 2>/dev/null
```

Baseline on 3.2.1 (measured 2026-10-07): `ADMIN_LOGIN code=200` (Django's own
form). PASS: `code` is **not 200**. The expected value, from allauth's
`secure_admin_login` (unauthenticated → `login_required` → `LOGIN_URL`), is a 3xx
whose `loc` points at the allauth login, **not** `/admin/login/`. Record the exact
value. The positive control `API_ROOT` must answer (200 or 401/403, not `000`).
A `000` on both means the port-forward is dead, which is not a pass. This row
documents a capability change. A 200 here is not an outage. It means #14270
did not take effect, so report it.

**CONTROL lines (the instruments these gates read):**

```
CONTROL: metric kube_pod_container_status_restarts_total — for {namespace="office",container=~"paperless-ngx|validator"}: a series MUST exist for each CURRENT pod name (positive control: no series = FAIL, the instrument is blind) and every value MUST be 0 after the roll (a non-zero on paperless-ngx = the startupProbe killed the rebuild, the §1.2(b) trap). Measured present 2026-10-07: 1 series each, value 0.
CONTROL: alertname ContainerMemoryLimitImminent — must NOT be firing for namespace office during/after the rebuild (working set > 97% of the 6Gi limit for 5m precedes an OOM-kill mid-rebuild). Rule: kubernetes/apps/monitoring/kube-prometheus-stack/app/container-memory-alerts.yaml.
```

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
PODS=$(kubectl get pods -n office -l 'app.kubernetes.io/name in (paperless-ngx,scan-inbox-validator)' -o jsonpath='{.items[*].metadata.name}')
curl -s --data-urlencode 'query=kube_pod_container_status_restarts_total{namespace="office",container=~"paperless-ngx|validator"}' \
  localhost:19090/api/v1/query | PODS="$PODS" python3 -c "
import sys,json,os
r=json.load(sys.stdin)['data']['result']; want=set(os.environ['PODS'].split())
got={x['metric']['pod']:float(x['value'][1]) for x in r if x['metric']['pod'] in want}
print('RESTART_SERIES', got)
ok = want and set(got)==want and all(v==0 for v in got.values())
print('PASS' if ok else 'FAIL'); sys.exit(0 if ok else 1)"
curl -s --data-urlencode 'query=ALERTS{alertname="ContainerMemoryLimitImminent",namespace="office",alertstate="firing"}' \
  localhost:19090/api/v1/query | python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];print('MEM_ALERT_FIRING', len(r));sys.exit(1 if r else 0)"
kill $PF 2>/dev/null
```

## 5) Rollback

`helm rollback` is **not** available (`maxHistory: 1`). Roll back forward through
git. Order matters: **reverse the migrations while 3.3.0 code is still running**,
because 3.2.1 ships no 0027/0017/0018 files to reverse with.

### 5.1 Reverse the migrations (only if the 3.3.0 pod is Running)

```bash
kubectl exec -n office deploy/paperless-db -- sh -c 'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" -N -B -e "SELECT COUNT(*) FROM paperless.documents_documentbarcode;"'
# expect 0 (store is off by default, CA7). If NON-zero, the reverse drops stored
# barcode rows, which is acceptable because they are derived from the PDFs. Note the count in the close-out.
kubectl exec -n office deploy/paperless-ngx -c paperless-ngx -- python3 /usr/src/paperless/src/manage.py migrate documents 0026
kubectl exec -n office deploy/paperless-ngx -c paperless-ngx -- python3 /usr/src/paperless/src/manage.py migrate paperless 0016
kubectl exec -n office deploy/paperless-ngx -c paperless-ngx -- python3 /usr/src/paperless/src/manage.py showmigrations documents paperless | grep -E '0026_|0027_|0016_|0017_|0018_'
# expect [X] 0026, [ ] 0027, [X] 0016, [ ] 0017, [ ] 0018
```

**If the 3.3.0 pod never reached Running**, skip 5.1. Leaving the migrations
applied under 3.2.1 is safe, for these checked reasons. The two new config
columns are `NULL`-able, so 3.2.1's INSERT/UPDATE (which do not name them)
succeed. `documents_documentbarcode` has a DB-level FK to `documents_document`
**without** `ON DELETE CASCADE`, because Django emulates CASCADE in Python.
While that table is **empty** (CA2/§5.1 count), deleting a document is
unaffected. Django ignores applied migrations it has no file for. Re-run 5.1 on
the next 3.3.0 attempt.

### 5.2 Revert the tags (keep the raised budget)

`3.2.1` sees sentinel `schema_version 3 != 2` and **rebuilds the index back to
v2** at startup. That uses the same sentinel-first ordering (3.2.1
`_backend.py`), so the 600 s budget must still be in place. Do **not**
`git revert` the forward commit; it would drop the budget. Edit the tags only:

```bash
cd /Users/mu/code/cberg-home-nextgen
ST=/private/tmp/claude-501/scan-inbox-validator-3.3.0
grep -q 'failureThreshold: 120' kubernetes/apps/office/paperless-ngx/app/helmrelease.yaml \
  || { echo "3.8 already restored: re-run the 3.2 python edit's three raises first (tag lines aside), then this block"; exit 1; }
sed -i '' 's|^      tag: "3\.3\.0"$|      tag: "3.2.1"|' kubernetes/apps/office/paperless-ngx/app/helmrelease.yaml
sed -i '' 's|^          image: ghcr\.io/paperless-ngx/paperless-ngx:3\.3\.0$|          image: ghcr.io/paperless-ngx/paperless-ngx:3.2.1|' \
  kubernetes/apps/office/paperless-ngx/app/validator-deployment.yaml
[ "$(grep -c '^      tag: "3.2.1"$' kubernetes/apps/office/paperless-ngx/app/helmrelease.yaml)" = 1 ] \
 && [ "$(grep -c 'paperless-ngx:3.2.1$' kubernetes/apps/office/paperless-ngx/app/validator-deployment.yaml)" = 1 ] \
 || { echo "ROLLBACK EDIT INCOMPLETE - not committing"; exit 1; }
MSG=$ST/msg-rollback-$(date +%s).txt
printf 'revert(paperless-ngx): app + scan-inbox-validator 3.3.0 -> 3.2.1 (rollback, startup budget kept raised)\n\nPlan: runbooks/maintenance/plans/scan-inbox-validator-3.3.0.md\n' > "$MSG"
git commit --only kubernetes/apps/office/paperless-ngx/app/helmrelease.yaml kubernetes/apps/office/paperless-ngx/app/validator-deployment.yaml -F "$MSG"
git log -1 --format=%s && git show --stat HEAD && git push origin main
rm -f "$ST/roll-start"; flux reconcile kustomization paperless-ngx -n office --with-source
# then the §3.5 poll AS-IS (it reads tag 3.2.1 + threshold 120 from the file), then §3.8 restore.
```

The sed forms are anchored on line content (BSD sed, no `\s`). The reverse
substitutions were dry-tested on the forward-edited scratch copy 2026-10-07. The
validator file came back byte-identical to HEAD. The helmrelease came back
identical except for the 7 raise lines, which is intended: the budget stays
raised until §3.8. Timing: if §3.5 ended `STILL_NOT_READY`, the forward
Helm upgrade may still be inside its 20m wait. helm-controller does not act on
the new revision until that wait expires. That is expected, so keep re-running
the poll.

**Confirm the cluster is back:** the floor shows both pods on `:3.2.1`. Then run
CA1 with the pre file: `VERSION 3.2.1`, `"schema_version": 2`,
`MISSING_FROM_INDEX 0`, HITS within 5% of `$ST/app-pre.txt`. Then run CA2:
`TABLES 74` after 5.1 (75 if 5.1 was skipped), `NONUTF8MB4 0`, CANARY == pre.

### 5.3 Only if a migration HALF-applied (MariaDB DDL is not transactional)

The tell: §3.5 logs show `Applying documents.0027_documentbarcode...` followed by
an error, and the pod crash-loops on `Table 'documents_documentbarcode' already
exists` (the table was created but the `django_migrations` row was not written).
Restore the §3.1 dump:

```bash
ST=/private/tmp/claude-501/scan-inbox-validator-3.3.0
DUMP=$(cat "$ST/dump-path"); [ -s "$DUMP" ] || { echo "no dump at '$DUMP' - STOP, escalate"; exit 1; }
flux suspend kustomization paperless-ngx -n office
flux suspend helmrelease paperless-ngx -n office
kubectl -n office scale deploy/paperless-ngx --replicas=0
kubectl -n office wait --for=delete pod -l app.kubernetes.io/name=paperless-ngx --timeout=120s
# the dump does not know the new table: drop it first, then replay (dump = DROP TABLE IF EXISTS + CREATE per table)
kubectl -n office exec deploy/paperless-db -- sh -c 'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" -e "SET FOREIGN_KEY_CHECKS=0; DROP TABLE IF EXISTS paperless.documents_documentbarcode;"'
kubectl -n office exec -i deploy/paperless-db -- sh -c 'mariadb --default-character-set=utf8mb4 -uroot -p"$MARIADB_ROOT_PASSWORD"' < "$DUMP"
```

Then do §5.2 (tags back to 3.2.1, commit, push), `flux resume helmrelease
paperless-ngx -n office`, `flux resume kustomization paperless-ngx -n office`, and
`kubectl -n office scale deploy/paperless-ngx --replicas=1`. The reconcile does
**not** restore replicas, because driftDetection is off. Confirm with CA2: 74
tables, DOCROWS/CANARY == pre, and none of the three migrations recorded. Last
resort if the dump is unusable: the Longhorn backup of `paperless-db-data` that
§2.2 proved < 26h old (`docs/sops/backup.md` §"Restore from Backup").

## 6) Interference notes

- **Both pins move together, on purpose.** The DB/index risk sits only on the app
  pin. The validator bypasses s6, so it never migrates or reindexes. Parity is the
  SOP rule (`paperless.md` §2, §6a.6), and PR #308 already moves both. A split
  would leave the validator on an image whose pikepdf the app no longer ships. That
  is harmless, but it is a divergence the SOP forbids for no gain.
- **`paperless-db-13.0.2` (awaiting-go, sat-attended:2026-10-24) is a hard
  exclusion.** It quiesces this app and converts the DB datadir one-way. Never the
  same slot. Ordering is free, but it is **better to run this plan first or well
  after**, not the night before. Its `still-on-12.3.3` premise and this plan's
  `db-still-on-12.3.3` premise each re-check the other's precondition. That plan's
  `conflicts_with` does not list this plan_id. `--validate` checks only that refs
  resolve, and the scheduler honours the field in either direction. Report the
  missing reciprocal ref as a repo correction; this plan does not edit it.
- **`kube-prometheus-stack-91.9.0` (nightly:2026-10-08):** the CONTROL gates read
  Prometheus, so this is declared under `conflicts_with`.
- **No Alertmanager silence, unlike 3.2.0.** The measured rebuild is 115 s
  (§6a.4), and the 600 s ceiling is under the live `for:` of
  `KubePodNotReady`, `KubePodCrashLooping` and `KubeDeploymentReplicasMismatch`
  (all 900 s, read from `/api/v1/rules` 2026-10-07). Writing a namespace-wide silence would mask other `office` plans and
  would make `monitoring` a perturbed shared surface. The `update-marker` is the
  courtesy signal instead. If the rebuild runs > 10 min, that is already a §5
  trigger, not something to silence.
- **`redis-fleet-8.10.2`** restarts `paperless-redis`, the celery broker and the
  #14189 mail-lock cache. In the same slot it would confound CA3/CA5.
- **Flux plans** (`flux-fleet-0.60.0` tonight, `flux-distribution-2.9.6`,
  `flux-oci-chart-sources`, `helm-drift-detection`,
  `flux-reconciler-impersonation`): this plan holds HR remediation off with a 20m
  timeout for the roll and relies on helm-controller honouring that. A controller
  restart or a chart-source/drift change in the same slot breaks that assumption.
- **`Recreate` is load-bearing** for both Deployments (RWO `paperless-data`). The
  `strategy-is-recreate` premise guards it.
- **Ingestion buffers, nothing is lost.** The scanner lands on the SMB inbox, and
  the validator moves files only when paperless' consume poller is running. Mail
  stays on the server. The ARAG push (`health-insurance-agent`) retries.
- **Repo corrections owed (report, not edited here):** (1) `paperless-db-13.0.2`
  should list `scan-inbox-validator-3.3.0` in `conflicts_with`, the same pairing it
  carried for `paperless-ngx-3.2.0`. (2) `docs/sops/paperless.md` header row
  (line 39) still says "app image `3.1.3`" while 3.2.1 is live, which is doc drift.
