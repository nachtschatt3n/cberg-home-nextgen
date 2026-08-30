# SOP: Paperless-ngx Document Management

> Description: Operating standard for paperless-ngx and its full ingestion pipeline — Epson ES-580W scanner → SMB inbox → validator → consume, email ingestion, native AI (LLM suggestions + RAG), OCR tuning, and library curation.
> Version: `2026.08.30`
> Last Updated: `2026-08-30`
> Owner: `paperless-agent` (global, `~/.claude/agents/paperless-agent.md`)

---

## 1) Description

Covers the document lifecycle end to end: capture → OCR → split → classify →
store, across all ingestion paths, plus deployment health and library-wide
metadata curation.

- Scope: `office` namespace — `paperless-ngx` (+ `paperless-db`, `paperless-redis`),
  its native AI module, the `scan-inbox-validator` Deployment, the Epson ES-580W
  scanner, and the GMX document mailbox.
- **paperless-gpt (vision-OCR/metadata) and paperless-ai (auto-tag/RAG) were
  retired 2026-08-24** in favor of paperless-ngx 3.0.5's built-in AI module — see
  §4a below. Vision-OCR has no native replacement; hard-to-OCR scans now go
  through **manual review** (operator + Claude Code reading the page image
  directly on demand) instead of an automated pipeline stage. This is a
  deliberate scope reduction, not a gap to fill.
- Prerequisites: repo-local `mise` tooling (`kubectl`, `flux`, `sops`); local SOPS
  age key; LAN access to the cluster (VLAN 55) and scanner (IoT VLAN).
- Out of scope: Ollama model lifecycle (→ ollama-agent), UniFi/scanner network
  (→ unifi-agent), Home Assistant (→ ha-agent), cluster/manifest/PVC mutations
  (→ cberg-agent / cluster-ops-agent).

---

## 2) Overview

| Setting | Value |
|---------|-------|
| Namespace | `office` |
| Source of truth | `kubernetes/apps/office/paperless-ngx/app/` + this SOP + `paperless-agent` |
| Chart / image | gabe565 `paperless-ngx` · app image `3.0.5`. The `scan-inbox-validator` Deployment **reuses the same tag** (it wants only the image's python3 + pikepdf runtime, and overrides the entrypoint) — bump `helmrelease.yaml` and `validator-deployment.yaml` in the SAME commit, or the validator silently keeps running a retired image. |
| Ingress | `paperless.${SECRET_DOMAIN}` |
| **Memory limit** | **6Gi** (do NOT lower — `OCR_MODE=force` OOMs at 3Gi) |
| DB / cache | `paperless-db` Deployment + Service — Docker Official `mariadb:11.8.8` on the `longhorn-static` volume `paperless-db-data` (2 replicas; Volume CR hand-applied, charset `utf8mb3`). Bundled MariaDB subchart retired 2026-08-19 — orphaned volume `paperless-mariadb` kept `Retain` as the rollback floor until its clean-week retirement. Cache: standalone `paperless-redis` Deployment (official `redis:8.10.0-alpine`, no PVC — old PV `paperless-redis` kept Retain as rollback) |
| CIFS shares | `//<NAS>/paperless_ngx` → `consume`, `media`, `export`, `log`, `inbox` — StorageClasses `cifs-paperless-*`, **reclaim=Retain** |
| Scanner | Epson ES-580W `192.168.32.201` (IoT VLAN), duplex sheet-feed; SMB destination in panel **Presets** |
| Mail | document mailbox @ `imap.gmx.net:993` (SSL); MailRule id 1 |
| Native AI | `ai_enabled=True` · LLM suggestions `ollama`/`gemma4:26b`/`http://192.168.30.111:11434` · embeddings (RAG) `ollama`/`nomic-embed-text:latest`/same endpoint. **DB-stored** (`paperless.models.ApplicationConfiguration`), not GitOps — see §4a. paperless-gpt/paperless-ai retired 2026-08-24. |

Key OCR/consumer env (`paperless-ngx` helmrelease): `OCR_LANGUAGE=deu+eng`,
`OCR_MODE=force`, `OCR_ROTATE_PAGES_THRESHOLD=7`, `CONSUMER_BARCODE_SCANNER=ZXING`,
`CONSUMER_ENABLE_BARCODES=true`, `CONSUMER_RECURSIVE=true`,
`CONSUMER_SUBDIRS_AS_TAGS=true`, `CONSUMER_POLLING=10`,
`CONSUMER_DELETE_DUPLICATES=true`,
`FILENAME_FORMAT={created_year}/{correspondent}/{title}` + `..._REMOVE_NONE=true`.

Ingestion flow:
```
ES-580W preset (duplex, 300dpi, PDF, skip-blank) --SMB--> //NAS/paperless_ngx/inbox
  scan-inbox-validator: file stable + pikepdf valid + pages>0 --atomic--> /consume
  paperless (poll 10s): PATCHT split · force OCR (deu+eng) · store
  native AI suggestions (ai_enabled) tag/correspondent/type/title; else built-in matcher
  Hard-to-OCR scans: manual review (operator + Claude Code reads the page image on demand)
Email: forwarded invoice → GMX INBOX → MailRule (inline+attachment *.pdf) → consume
```

---

## 3) Blueprints

- Source of truth files: `kubernetes/apps/office/paperless-ngx/app/helmrelease.yaml`
  (OCR/consumer env, 6Gi limit, ingress), `validator-configmap.yaml` +
  `validator-deployment.yaml` (scan-inbox validator), `storageclass.yaml`,
  `pvc.yaml`.
- Native AI config (`ai_enabled`, `llm_*`, `llm_embedding_*`) is **DB state**
  (`paperless.models.ApplicationConfiguration`, singleton row) — not a manifest,
  not GitOps. Set/read via `manage.py shell` (see §4a). There is no
  `paperless-gpt`/`paperless-ai` directory anymore — both retired 2026-08-24.
- Mail accounts/rules and per-document metadata are **DB state**, not git —
  edited via the paperless UI or the manage.py shell (see §4).

```yaml
# MailRule id 1 "incomming mail" (target state)
attachment_type: 2            # process all incl. inline attachments
filter_attachment_filename_include: "*.pdf"
maximum_age: 30               # days (0 only for a one-off backlog recovery)
action: 3                     # MARK_READ (don't delete source mail)
folder: INBOX
```

---

## 4) Operational Instructions

**Manifest change (GitOps):** edit under `kubernetes/apps/office/...`, `task
kubeconform` + `kubeconform -summary`, commit to **main** (no feature
branches), push, let Flux reconcile.

### 4a) Native AI config (DB-stored, not GitOps)

`ai_enabled`/`llm_backend`/`llm_model`/`llm_endpoint`/`llm_api_key` (LLM
suggestions: title/correspondent/type/tags/date, text-only input) and
`llm_embedding_backend`/`llm_embedding_model`/`llm_embedding_endpoint`/
`llm_embedding_chunk_size` (RAG embedding/chat) live on the singleton
`paperless.models.ApplicationConfiguration` row. **Always use `gosu paperless`**
for the exec (SOP gotcha, see the permission-bug troubleshooting row) —
never a bare/root shell.

```bash
PPOD=$(mise exec -- kubectl get pod -n office -l app.kubernetes.io/name=paperless-ngx \
  --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}')
mise exec -- kubectl exec -n office "$PPOD" -c paperless-ngx -- gosu paperless \
  python3 /usr/src/paperless/src/manage.py shell -c "
from paperless.models import ApplicationConfiguration
ac = ApplicationConfiguration.objects.first()
ac.ai_enabled = True
ac.llm_backend = 'ollama'                      # LLMBackend choices: openai-like, ollama
ac.llm_model = 'gemma4:26b'
ac.llm_endpoint = 'http://192.168.30.111:11434'
ac.llm_embedding_backend = 'ollama'             # LLMEmbeddingBackend: openai-like, huggingface, ollama
ac.llm_embedding_model = 'nomic-embed-text:latest'
ac.llm_embedding_endpoint = 'http://192.168.30.111:11434'
ac.save()
"
```

Current cluster state (set 2026-08-24): `ai_enabled=True`, `llm_backend=ollama`,
`llm_model=gemma4:26b`, `llm_endpoint=http://192.168.30.111:11434`,
`llm_embedding_backend=ollama`, `llm_embedding_model=nomic-embed-text:latest`
(already pulled/pinned on the shared Ollama host — used by AnythingLLM, AFFiNE,
Nextcloud context_chat; see `docs/ai-usage-map.md`), `llm_embedding_endpoint`
same as `llm_endpoint`. `llm_embedding_chunk_size`/`llm_context_size`/
`llm_request_timeout` left `null` — falls back to the app's built-in defaults
(1024/8192/120) via `paperless/settings/__init__.py`.

**Vision-OCR has no native equivalent.** paperless-gpt used to auto-OCR
hard-to-read scans (garbled/decorative fonts, thermal receipts, rotated pages)
via a vision LLM. That automated fallback is retired; for a scan that OCR'd
badly, pull up the page image and have the operator + Claude Code read it
directly (manual transcription into `Document.content`), rather than expecting
an automated second-pass OCR stage.

**Document / DB / mail operations** run in the paperless shell:
```bash
PPOD=$(mise exec -- kubectl get pod -n office -l app.kubernetes.io/name=paperless-ngx \
  --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}')
mise exec -- kubectl exec -n office "$PPOD" -c paperless-ngx -- \
  python3 /usr/src/paperless/src/manage.py shell -c "<python>"
```
- `documents.bulk_edit.reprocess([ids])` — re-run OCR (force+deu+rotate).
- `documents.bulk_edit.delete([ids])` — move to **trash** (recoverable ~30d).
- Re-OCR then index: set `Document.content` and `d.save()`, then reindex with
  `documents.index.open_index_writer()` + `index.update_document(writer, d)`.
- Note: `Document.created` is a **date** (not datetime) — `.date()` errors.

**Touching `/inbox` or `/consume` when paperless is down:** exec the
`scan-inbox-validator` pod (it mounts both shares at `/inbox` and `/consume`).

**Scanner config** is behind Administrator Login — the operator applies changes;
guide them. Never type into a credential field.

---

## 5) Examples

### Example A: re-OCR garbled documents
```python
from documents.bulk_edit import reprocess
reprocess([381, 463, 475])   # force+deu+rotate straightens flipped pages
```

### Example B: fix email ingestion + recover a backlog (inline PDFs)
```python
from paperless_mail.models import MailRule, ProcessedMail
r = MailRule.objects.get(id=1)
r.attachment_type = 2; r.filter_attachment_filename_include = "*.pdf"
r.maximum_age = 0; r.action = 3; r.save()          # 0 to reach the old backlog
ProcessedMail.objects.filter(status="FAILED").delete()  # unblock skipped UIDs
# then queue via the worker (NOT a root shell) or write PDFs to /consume directly
from paperless_mail.tasks import process_mail_accounts
process_mail_accounts.delay()
```

### Example C: rotate-both-tesseract for pages ocrmypdf can't auto-rotate
```python
# per page: tesseract on original AND PIL rotate(180); keep the lower-garble one
# (garble = internal-caps ratio [a-z][A-Z]); write combined text back to content.
```

---

## 6) Verification Tests

1. Manifests: `task kubeconform` and
   `kubeconform -summary kubernetes/apps/office/paperless-ngx`.
2. Scanner happy path: run the "paperless" preset on a 2–3 page doc → appears in
   `inbox/`, validator log `moved -> consume` within ~30s, doc created in paperless
   within ~10s, OCR'd.
3. Split path: two docs with one **PATCHT** separator between them → **two**
   documents, separator page discarded.
4. Email: forward an invoice → within 10 min a new document appears; INBOX
   unprocessed-PDF count returns to 0.
5. Large-doc OCR: a 12+ page PDF consumes without OOM (pod restart count stays 0).
6. Image parity: the app and the validator must run the SAME tag —
   `kubectl -n office get deploy paperless-ngx scan-inbox-validator -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.template.spec.containers[0].image}{"\n"}{end}'`.
   A mismatch means an upgrade bumped the HelmRelease and left the validator behind.
7. Validator liveness on a new tag: the loop must still turn.
   `kubectl -n office exec deploy/scan-inbox-validator -- python3 -c "import os;print(os.path.getmtime('/tmp/validator.heartbeat'))"`
   twice, ~20s apart — the value must advance by `POLL_SECONDS`. A frozen
   heartbeat means the image lost `python3`/`pikepdf` or the CIFS inbox stalled.

### 6a) Post-update verification (after ANY paperless-ngx or paperless-db update)

Run all three after every image/chart bump of `paperless-ngx` or roll of
`paperless-db`, and after any DB restore.

1. **API-token canary.** From the openclaw pod (`ai` namespace):
   ```bash
   OPOD=$(mise exec -- kubectl get pod -n ai -l app.kubernetes.io/name=openclaw \
     -o jsonpath='{.items[0].metadata.name}')
   mise exec -- kubectl exec -n ai "$OPOD" -- paperless search ARAG | head -5
   ```
   Must return HTTP 200 with results. **A 401 means TOKEN failure — never
   interpret it as "documents are missing"** (this exact mislabeling happened
   2026-08-30: a silently deleted server-side token made a healthy library look
   empty to API consumers). On 401, compare prefixes: pod-side
   `printenv PAPERLESS_TOKEN | cut -c1-6` vs server-side
   `Token.objects` in a `manage.py shell` — prefixes only, never print full
   token values.
2. **Mail-ingestion check.** Grep the app logs for `paperless_mail` errors —
   specifically `OperationalError` **1366** (charset) and `mailbox.login`
   failures:
   ```bash
   mise exec -- kubectl logs -n office "$PPOD" -c paperless-ngx --since=30m | \
     grep -E "1366|OperationalError|mailbox.login|Login failed"
   ```
   Background (2026-08-30): the 2026-08-19 DB replatform created/restored the
   schema as utf8mb3; a 4-byte emoji in a mail subject then broke **every**
   mail-processing cycle with
   `(1366, "Incorrect string value ... paperless_mail_processedmail.subject")`
   — mail ingestion was dead for days while the beat kept reporting normally.
3. **Charset invariant.** All paperless tables AND the database default must be
   utf8mb4 (utf8mb4_general_ci). One-liner (in the `paperless-db` pod):
   ```bash
   mise exec -- kubectl exec -n office deploy/paperless-db -- sh -c \
     'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" -N -e "
      SELECT table_collation, COUNT(*) FROM information_schema.tables
        WHERE table_schema=\"paperless\" GROUP BY 1;
      SELECT default_collation_name FROM information_schema.schemata
        WHERE schema_name=\"paperless\";"'
   ```
   Expected: a single `utf8mb4_general_ci` row covering all tables, and
   `utf8mb4_general_ci` as the DB default. The enforcing config is the
   `--character-set-server=utf8mb4 --collation-server=utf8mb4_general_ci` args
   in `kubernetes/apps/office/paperless-ngx/app/db-deployment.yaml` — do not
   drop them, or future Django migrations create wrong-charset tables again.
   Fix for a stray table:
   `ALTER TABLE paperless.<t> CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;`
   (the varchar(1024) unique indexes on `documents_document` are long-unique
   HASH indexes on MariaDB 11.x — no key-length limit, CONVERT is safe).

### 6b) Paperless API token consumers (rotation checklist)

Every consumer of a paperless API token. **When a token is rotated or dies,
walk EVERY row** — on 2026-08-30 only openclaw was rotated at first and the
other three carriers of the dead token stayed silently broken for days
(arag-web logged 4,400+ `401 Invalid token`; the Mac scraper's breakage was
latent because `paperless-push` only authenticates when it has something to
upload). Env vars do not hot-reload: cluster consumers need a
`kubectl rollout restart` after the SOPS change reconciles.

| Consumer | Where | Credential location | Paperless user | Owning agent | Verify (expect HTTP 200) |
|---|---|---|---|---|---|
| openclaw (paperless skill; also the source the `runbooks/mealie-import.md` export step points at) | `ai` ns | `kubernetes/apps/ai/openclaw/app/secret.sops.yaml` → `PAPERLESS_TOKEN` | mathiasuhl | openclaw-agent | `kubectl exec -n ai <openclaw-pod> -- paperless search <term>` |
| arag-web (PaperlessSyncJob / DeductibleAnalysisJob / ReductionAnalysisJob) | `office` ns | `kubernetes/apps/office/arag-web/app/secret.sops.yaml` → `PAPERLESS_API_KEY` (envFrom) | mathiasuhl | health-insurance-agent | in-pod: ruby `Net::HTTP` GET `$PAPERLESS_API_URL/documents/?page_size=1` with `Token $PAPERLESS_API_KEY`; also grep pod logs for `Paperless API error 401` |
| mcpo (paperless MCP tools for LibreChat/Open WebUI) | `ai` ns | `kubernetes/flux/components/common/cluster-secrets.sops.yaml` → `PAPERLESS_API_KEY`, postBuild-substituted into `kubernetes/apps/ai/mcpo/app/secret.sops.yaml` (`paperless-api-key`) → env `PAPERLESS_API_KEY`. **Two-hop: rotate cluster-secrets, then reconcile flux-system BEFORE mcpo** | mathiasuhl | cluster-ops-agent | in-pod: python `urllib` GET `/api/documents/?page_size=1` with the env token |
| arag-scrape menubar/scraper (Mac mini) | Mac mini, not git-tracked | `/Users/mu/code/arag-scrape-ios/data/menubar_config.json` → `paperlessToken` (passed as `--token` to `arag-scraper paperless-push`) | mathiasuhl | health-insurance-agent | `curl -H "Authorization: Token <cfg value>" <paperlessURL>/documents/?page_size=1`. **Latent-failure trap:** the push step returns success without authenticating when nothing is pending — a green cycle does NOT prove the token works |
| *(removed 2026-08-30)* `PAPERLESS_TOKEN` key in the paperless-ngx secret | `office` ns | was consumed by nothing (leftover from retired paperless-gpt/paperless-ai); key deleted per operator decision | — | — | n/a |

> **Operator decision (2026-08-30): ONE shared API token by design.** All
> consumers authenticate with the same mathiasuhl token; per-consumer tokens
> were considered after the Aug-27 silent breakage and explicitly declined.
> Do not re-propose token-per-consumer in audits; the mitigation of choice is
> this consumer table + the §6a token canary, which turn a future rotation
> into a checklist walk of every row.


The `andreauhl` token has no known repo/Mac consumer (personal use only).

**Token-audit gap (known):** token deletions leave **no trail** — deleting or
regenerating a token in the profile UI kills API consumers silently (no log,
no event). After suspicious 401s, check
`rest_framework.authtoken.models.Token.objects.count()` and the per-user
prefixes against what consumers hold. Case: 2026-08-27/29 an out-of-band row
deletion removed the `mathiasuhl` token; a fresh one was minted 2026-08-30 and
rotated into openclaw's SOPS secret (commit `b44fc170`).

---

## 7) Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Emailed PDF never ingested | rule `attachment_type=1` skips **inline** PDFs (forwarded invoices) | set `attachment_type=2` + `filter=*.pdf`; old mail also needs `maximum_age` lifted |
| Every mail cycle throws `OperationalError (1366, "Incorrect string value: '\xF0...'")` on `paperless_mail_processedmail.subject` | a table (or the whole schema) is utf8mb3 — cannot store 4-byte UTF-8 (emoji in a mail subject); happened 2026-08-30 after the DB replatform restored utf8mb3 | convert to utf8mb4 (see §6a charset invariant); dump the DB first; verify the `db-deployment.yaml` charset args are utf8mb4 |
| Mail consume `PermissionError /tmp/paperless/paperless-mail-*` | `process_mail_accounts` was run from a **root** shell (root-owned temp) | queue via `.delay()` or let the beat run; never trigger from a root exec |
| Mail re-run says "No new documents" but INBOX has unread PDFs | UIDs are in the `ProcessedMail` table (even `FAILED`) | delete the `FAILED` rows to reprocess |
| paperless CrashLoopBackOff, exit 137 OOMKilled | `OCR_MODE=force` re-OCRs a multi-page doc's pages concurrently > mem limit | keep limit **6Gi**; pull the wedging file out of `/consume` via the validator pod to recover |
| Doc OCR'd badly (garbled/decorative fonts, thermal receipt, rotated) | no automated vision-OCR fallback anymore (paperless-gpt retired 2026-08-24) | manual review — operator + Claude Code reads the page image directly and transcribes into `Document.content`; see §4a |
| Doc partly garbled (upside-down pages) | ocrmypdf OSD confidence too low to rotate | rotate-both-tesseract (Example C) |
| validator CrashLoopBackOff | liveness probe used `pgrep` (absent in image) | heartbeat-file probe (already in `validator-deployment.yaml`) |
| One PDF stuck in `/consume`, paperless crash-loops on it (tesseract `generate_hocr` ParseError / `SubprocessOutputError`) | under `OCR_MODE=force`, tesseract can ParseError on a **near-blank duplex back** (e.g. only hole-punch marks) and wedge the whole PDF on every 10s poll | pull the file via the `scan-inbox-validator` pod (stops the loop), drop/pre-OCR the blank page, re-consume the good page(s). Mitigate at source: **Skip Blank Pages ON** on the Epson preset (raise the blank threshold if hole-punches slip through) |
| Document `created` date is a **birthdate** (e.g. 1980-12-10, 2020-04-08) not the doc date | paperless's date parser picks a DOB from the letter body over the real document date — systematic on medical Rezepte/Rechnungen and insurance forms | sanity-check dates on ingest for medical/insurance docs; re-set `created` from the printed invoice/letter date. Watch for it in any batch audit |
| `bulk_edit.split()` / any `manage.py shell` write op fails with `PermissionError`/`[Errno 13]` on a temp PDF, or **every** queued `consume_file` task cluster-wide starts failing on `meta.json`/`.managed.json`/`MEDIA_LOCK` under the Tantivy index | **STRUCTURALLY FIXED 2026-08-24** — `kubectl exec` into the pod used to default to **root** (empty `securityContext`/`podSecurityContext`), so a root `manage.py shell` left root-owned temp files (`/tmp/paperless/...`, `/tmp/paperless_*.pdf`) or root-owned search-index files that the celery worker (uid 1000 `paperless`) couldn't read/write — happened 4x in one day, including once via an operator UI action ("Edit PDF" re-consume). `helmrelease.yaml` now pins `podSecurityContext`/`securityContext` to `runAsUser/runAsGroup: 1000` (`fsGroup: 1000` at pod level), so every exec session defaults to `paperless` — this class of corruption is no longer possible. The image's s6-overlay entrypoint natively supports non-root start (`USER_IS_NON_ROOT` auto-detect); verified safe pre-rollout, see commit `177e9ce5`. | if it ever recurs (e.g. someone re-adds `user: root` or a per-exec `--as-root` override): `find /usr/src/paperless/data/index /tmp/paperless -user root` and `chown paperless:paperless` the hits — unblocks the *entire* shared queue, not just one task. **Caveat**: a *freshly re-provisioned* `paperless-data` PV defaults to root:root from Longhorn — check ownership before assuming the pinned uid will self-heal it (non-root init only warns, doesn't chown); see the note above `securityContext` in `helmrelease.yaml` |
| After `bulk_edit.split(..., delete_originals=True)`, some children exist but the **parent document is still present** with all original pages | the split is chord-based per call — if any one task in the page-list fails (e.g. the permission bug above), the delete-original chord body doesn't fire, and it does **not** auto-retry the failed page-ranges | re-run `bulk_edit.split()` for just the missing page-range(s) (or consume them individually with the same metadata overrides), then verify the parent is actually gone with `Document.objects.filter(pk=…).exists()` before trusting `delete_originals=True` did its job — don't assume the chord completed cleanly |

---

## 8) Diagnose Examples

```bash
PPOD=$(mise exec -- kubectl get pod -n office -l app.kubernetes.io/name=paperless-ngx \
  --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}')
# doc count, consume backlog
mise exec -- kubectl exec -n office "$PPOD" -c paperless-ngx -- python3 \
  /usr/src/paperless/src/manage.py shell -c "from documents.models import Document; \
  import os; print(Document.objects.count(), \
  len([f for f in os.listdir('/usr/src/paperless/consume') if f.endswith('.pdf')]))"
# mail scheduler firing + errors
mise exec -- kubectl logs -n office "$PPOD" -c paperless-ngx --since=25m | \
  grep -E "process_mail_accounts.*(succeeded|ERROR)"
# validator flow
VPOD=$(mise exec -- kubectl get pod -n office -l app.kubernetes.io/name=scan-inbox-validator \
  --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}')
mise exec -- kubectl exec -n office "$VPOD" -- sh -c 'ls -la /inbox /inbox/_failed /consume'
```

Garble detection library-wide: fraction of tokens with an internal capital
(`[a-z][A-Z]`) > 0.14 ⇒ likely garbled/flipped OCR. (A German-dictionary
hit-rate false-positives on foreign-language docs — don't use it.)

---

## 9) Health Check ("check paperless")

Read-only; summarise green/finding per row:
1. Pods `paperless-ngx` / `paperless-db` / `paperless-redis` / `scan-inbox-validator`
   — READY + **restart count** (climbing = OOM crash-storm).
2. paperless mem limit = **6Gi**; `Document.objects.count()`; `/consume` PDF
   backlog = 0; validator heartbeat fresh.
3. Mail beat firing (every 10 min, "No new documents" = healthy) + INBOX
   unprocessed-PDF = 0.
4. Native AI: `ApplicationConfiguration.objects.first().ai_enabled` is `True`
   and `llm_backend`/`llm_embedding_backend` are still `ollama` (a chart/DB
   restore can silently reset this singleton row — it's not covered by Flux).
5. Flux kustomizations/HelmReleases Ready; git in sync.

Known-normal (not faults): "No new documents" every 10 min; `page already has
text! … running OCR anyway` (force mode); `Too few characters. Skipping this page`
(blank duplex back); the `Inbox` tag on the operator's to-review pile; English
AI titles on German docs; foreign-language invoices scoring low on a German dict.

---

## 10) Security Check

- Public repo: never commit the real domain, the mailbox address, or
  `*.sops.yaml` plaintext. Don't name specific document content (people, invoice
  details) in committed artifacts — IDs/counts are fine.
- Mail credentials and `csi-driver-smb` live in SOPS/cluster secrets — reference
  via `secretKeyRef`, never inline. `llm_api_key` (native AI) is `None` — Ollama
  doesn't require one; if a future backend needs a key, put it in the DB row,
  not a manifest (the row isn't git-tracked, so redact accordingly if ever dumped).
- CIFS `cifs-paperless-*` PVCs are **Severe** class (`docs/sops/storage-safety.md`)
  — never delete without the 3-step pre-flight; keep reclaim=Retain.
- Never enter the scanner Administrator password (prohibited action).

---

## 11) Rollback Plan

- Manifest change: `git revert` the commit, push, Flux re-reconciles. Storage
  classes/PVCs are Retain, so reverting never touches NAS data.
- Document edits: `bulk_edit.delete` sends to **trash** (restorable ~30d);
  re-OCR is reproducible from the original PDF (untouched) via `reprocess`.
- Mail rule: revert the fields to prior values (record before changing). If a
  backlog run misbehaves, set `maximum_age` back and delete stray `ProcessedMail`
  rows; source emails are preserved when `action=MARK_READ`.
- OOM from a manifest memory change: raise `resources.limits.memory` and let the
  pod roll; pull any wedging file from `/consume` via the validator pod first.

---

## 12) References

- `kubernetes/apps/office/paperless-ngx/app/`. (No `paperless-gpt`/`paperless-ai`
  directories anymore — retired 2026-08-24.)
- `docs/sops/storage-safety.md`, `docs/sops/longhorn.md`, `docs/sops/monitoring.md`,
  `docs/sops/new-deployment-blueprint.md`, `docs/sops/ai-integration.md`.
- `~/.claude/agents/paperless-agent.md` (operational depth + hard rules).
- `AGENTS.md` / `CLAUDE.md` — GitOps, SOPS, network topology, work-on-main,
  storage safety.

---

## Version History

| Version | Date | Change |
|---------|------|--------|
| `2026.07.13` | 2026-07-13 | Initial SOP — pipeline, OCR/force+6Gi, email inline-PDF fix, vision-OCR + rotate-both-tesseract, health/security/rollback. |
| `2026.07.13` | 2026-07-13 | Add troubleshooting for hOCR crash on near-blank duplex backs (force-mode wedge in `/consume`) and the DOB date-misparse on medical/insurance docs (surfaced in the 64-doc scan-batch audit). |
| `2026.08.18` | 2026-08-18 | Record that `scan-inbox-validator` reuses the app's image tag (bump both in one commit); add image-parity and heartbeat-advances verification tests. |
| `2026.08.24` | 2026-08-24 | Add troubleshooting for the root-vs-uid1000 permission bug in `bulk_edit.split()`/`manage.py shell` writes (use `gosu paperless`) and the split chord's silent no-retry-no-delete failure mode — surfaced during the 9-doc/147-recipe HelloFresh/Marley Spoon batch split. |
| `2026.08.24` | 2026-08-24 | Retire paperless-gpt and paperless-ai in favor of paperless-ngx 3.0.5's native AI module (`ApplicationConfiguration` DB row — `ai_enabled`/`llm_*`/`llm_embedding_*`, `ollama`/`gemma4:26b` + `nomic-embed-text:latest`). Add §4a (native AI operations), document the new manual-vision-review fallback for hard scans, drop vision-OCR/gpt/ai troubleshooting rows and references. |
| `2026.08.24` | 2026-08-24 | Structural fix for the root-exec index-corruption bug: pin `podSecurityContext`/`securityContext` to `runAsUser/runAsGroup/fsGroup: 1000` in `helmrelease.yaml` so `kubectl exec` defaults to `paperless` instead of root. Verified safe (image supports non-root start natively; CIFS PVCs unaffected; Longhorn data PV already correctly owned) before rollout — see commit `177e9ce5`. Superseded the `gosu paperless`-discipline workaround in the troubleshooting table. |
| `2026.08.30` | 2026-08-30 | Add §6a post-update verification (API-token canary from the openclaw pod — 401 = token failure, not missing docs; mail-ingestion 1366/login log grep; utf8mb4 charset invariant + SQL one-liner) and the token-audit gap. Root cause fixed same day: replatformed DB was utf8mb3, an emoji mail subject broke every mail cycle — full schema converted to utf8mb4_general_ci, `db-deployment.yaml` server args bumped utf8mb3→utf8mb4. |
| `2026.08.30` | 2026-08-30 | Add §6b token-consumer table after the dead-token blast-radius audit: the Aug 27-29 token deletion had FOUR carriers (openclaw, arag-web, cluster-secrets→mcpo, Mac menubar config) but only openclaw was rotated at first. All four now aligned; documents the two-hop mcpo substitution, the Mac scraper's latent-failure trap, and the vestigial `PAPERLESS_TOKEN` key in the paperless-ngx secret (removal → cberg-agent). |
