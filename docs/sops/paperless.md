# SOP: Paperless-ngx Document Management

> Description: Operating standard for paperless-ngx and its full ingestion pipeline — Epson ES-580W scanner → SMB inbox → validator → consume, email ingestion, the paperless-gpt (vision-OCR) and paperless-ai (RAG) add-ons, OCR tuning, and library curation.
> Version: `2026.08.19`
> Last Updated: `2026-08-19`
> Owner: `paperless-agent` (global, `~/.claude/agents/paperless-agent.md`)

---

## 1) Description

Covers the document lifecycle end to end: capture → OCR → split → classify →
store, across all ingestion paths, plus deployment health and library-wide
metadata curation.

- Scope: `office` namespace — `paperless-ngx` (+ `paperless-db`, `paperless-redis`), `paperless-gpt`,
  `paperless-ai`, the `scan-inbox-validator` Deployment, the Epson ES-580W scanner,
  and the GMX document mailbox.
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
| AI add-ons | paperless-gpt (vision-OCR, tag-triggered) · paperless-ai (RAG, `*/30`) → Ollama `gemma4:26b` @ `192.168.30.111:11434` |

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
  paperless-ai (*/30) / paperless-gpt (on tag) tag/title; else built-in matcher
Email: forwarded invoice → GMX INBOX → MailRule (inline+attachment *.pdf) → consume
```

---

## 3) Blueprints

- Source of truth files: `kubernetes/apps/office/paperless-ngx/app/helmrelease.yaml`
  (OCR/consumer env, 6Gi limit, ingress), `validator-configmap.yaml` +
  `validator-deployment.yaml` (scan-inbox validator), `storageclass.yaml`,
  `pvc.yaml`.
- paperless-gpt: `kubernetes/apps/office/paperless-gpt/app/configmap.yaml` (strict
  `ocr_prompt.tmpl`) + `helmrelease.yaml`. paperless-ai: `.../paperless-ai/app/`.
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

---

## 7) Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Emailed PDF never ingested | rule `attachment_type=1` skips **inline** PDFs (forwarded invoices) | set `attachment_type=2` + `filter=*.pdf`; old mail also needs `maximum_age` lifted |
| Mail consume `PermissionError /tmp/paperless/paperless-mail-*` | `process_mail_accounts` was run from a **root** shell (root-owned temp) | queue via `.delay()` or let the beat run; never trigger from a root exec |
| Mail re-run says "No new documents" but INBOX has unread PDFs | UIDs are in the `ProcessedMail` table (even `FAILED`) | delete the `FAILED` rows to reprocess |
| paperless CrashLoopBackOff, exit 137 OOMKilled | `OCR_MODE=force` re-OCRs a multi-page doc's pages concurrently > mem limit | keep limit **6Gi**; pull the wedging file out of `/consume` via the validator pod to recover |
| Vision-OCR (paperless-gpt) writes empty/garbage | gemma4 thinking model returns empty; default prompt encourages hallucination | retry empties, never overwrite with empty; strict `ocr_prompt.tmpl` is mounted |
| Doc partly garbled (upside-down pages) | ocrmypdf OSD confidence too low to rotate | rotate-both-tesseract (Example C) |
| validator CrashLoopBackOff | liveness probe used `pgrep` (absent in image) | heartbeat-file probe (already in `validator-deployment.yaml`) |
| One PDF stuck in `/consume`, paperless crash-loops on it (tesseract `generate_hocr` ParseError / `SubprocessOutputError`) | under `OCR_MODE=force`, tesseract can ParseError on a **near-blank duplex back** (e.g. only hole-punch marks) and wedge the whole PDF on every 10s poll | pull the file via the `scan-inbox-validator` pod (stops the loop), drop/pre-OCR the blank page, re-consume the good page(s). Mitigate at source: **Skip Blank Pages ON** on the Epson preset (raise the blank threshold if hole-punches slip through) |
| Document `created` date is a **birthdate** (e.g. 1980-12-10, 2020-04-08) not the doc date | paperless's date parser picks a DOB from the letter body over the real document date — systematic on medical Rezepte/Rechnungen and insurance forms | sanity-check dates on ingest for medical/insurance docs; re-set `created` from the printed invoice/letter date. Watch for it in any batch audit |
| `bulk_edit.split()` / any `manage.py shell` write op fails with `PermissionError`/`[Errno 13]` on a temp PDF, or **every** queued `consume_file` task cluster-wide starts failing on `meta.json`/`.managed.json`/`MEDIA_LOCK` under the Tantivy index | `kubectl exec` into the pod defaults to **root**; a root `manage.py shell` leaves root-owned temp files (`/tmp/paperless/...`, `/tmp/paperless_*.pdf`) or root-owned search-index files that the celery worker (uid 1000 `paperless`) can't read/write — same root-cause class as the mail `PermissionError` row above, but applies to any bulk_edit/manage.py write, not just mail | prefix with `gosu paperless` (present in the image) for any `manage.py shell` that writes files or triggers a filename-move/index signal — never run one bare/as root. If already corrupted: `find /usr/src/paperless/data/index /tmp/paperless -user root` and `chown paperless:paperless` the hits — this unblocks the *entire* shared queue, not just the one task |
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
1. Pods `paperless-ngx` / `-gpt` / `-ai` / mariadb / `paperless-redis` / `scan-inbox-validator`
   — READY + **restart count** (climbing = OOM crash-storm).
2. paperless mem limit = **6Gi**; `Document.objects.count()`; `/consume` PDF
   backlog = 0; validator heartbeat fresh.
3. Mail beat firing (every 10 min, "No new documents" = healthy) + INBOX
   unprocessed-PDF = 0.
4. Flux kustomizations/HelmReleases Ready; git in sync.

Known-normal (not faults): "No new documents" every 10 min; `page already has
text! … running OCR anyway` (force mode); `Too few characters. Skipping this page`
(blank duplex back); the `Inbox` tag on the operator's to-review pile; English
AI titles on German docs; foreign-language invoices scoring low on a German dict.

---

## 10) Security Check

- Public repo: never commit the real domain, the mailbox address, or
  `*.sops.yaml` plaintext. Don't name specific document content (people, invoice
  details) in committed artifacts — IDs/counts are fine.
- API tokens (paperless-gpt/ai), mail credentials, and `csi-driver-smb` live in
  SOPS/cluster secrets — reference via `secretKeyRef`, never inline.
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

- `kubernetes/apps/office/paperless-ngx/app/` · `paperless-gpt/app/` ·
  `paperless-ai/app/`.
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
