---
plan_id: paperless-ngx-3.0.5
component: paperless-ngx
pr: null                              # no open Renovate PR for this bump at plan time;
                                      # the major is held by policy, not by a PR gate.
                                      # If Renovate opens one before the window, record
                                      # the number here and re-check the target version.
kind: image                           # image tag + env-var migration. NO chart bump:
                                      # gabe565 chart stays 0.24.1 (appVersion 2.14.7 is
                                      # only a default we already override).
current: "2.20.15"
target: "3.0.5"
update_type: major
risk: high                            # irreversible Django migrations + a full-text index
                                      # replacement + a silent-ingestion-halt trap + an
                                      # API default-version jump that hits 4 API consumers
est_duration_min: 75
needs_reboot: false
touches:
  namespaces:
    - office                          # everything actually mutated lives here
    - ai                              # NOT mutated — but openclaw's `paperless` skill and
                                      # mcpo's paperless MCP are API consumers that the
                                      # default-API-version jump can break. See §6.
  resources:
    - helmrelease/paperless-ngx       # image tag + env changes
    - deployment/paperless-ngx        # rolls; runs Django migrations on first start
    - statefulset/paperless-ngx-mariadb   # NOT upgraded — but its SCHEMA is migrated
    - pvc/paperless-data              # Whoosh index replaced by a Tantivy index (rebuild)
    - pvc/paperless-mariadb           # DB volume behind the schema migration
    - pvc/paperless-ngx-consume       # ingestion path — read/write only, NEVER deleted
    - pvc/paperless-ngx-inbox         # scanner staging — read/write only, NEVER deleted
    - pvc/paperless-ngx-media         # document store — read only during this plan
    - pvc/paperless-ngx-export        # holds the pre-upgrade DB dump
    - deployment/paperless-gpt        # API consumer, not upgraded — may break, see §6
    - deployment/paperless-ai         # API consumer, not upgraded — may break, see §6
    - deployment/scan-inbox-validator # untouched, but it is half the ingestion pipeline
  shared: []                          # no shared infra is perturbed: ingress object is
                                      # unchanged, no cert-manager/CNI/coredns/shared-DB
                                      # involvement. The DB and cache are per-app subcharts.
depends_on: []                        # prerequisite is a VERSION state, not another plan:
                                      # v3 may only be entered from exactly 2.20.15, which
                                      # is what we run today. See §1.
conflicts_with:
  - longhorn-1.12.1-engine            # schema migration + full index rebuild = sustained
                                      # IO on two Longhorn volumes; never during a live
                                      # engine upgrade
  # - <paperless bitnamilegacy-exit plan_id>   # authored separately; see §6 for the
  #   ordering relationship. Fill in the real plan_id once it exists.
security_ref: F-2898fafa
status: draft
window: "sun-window:2026-08-23"                 # RESHUFFLED 2026-08-16 onto the daily-window cadence
                                      # (7 windows/week, was 4). Deliberate soaks are
                                      # preserved, not compressed — see the windows YAML.
                                      # booked run (08-22 kps, 08-29 app-template, 09-05
                                      # longhorn, 09-12 superset-pg-cutover, 09-26 grafana-13).
                                      # Tue/Thu are 60m slots — too short for this plan.
                                      # MUST BE THE ONLY PLAN IN THE WINDOW (§6).
auto_execute: false                   # major with a security driver — operator go/no-go
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/paperless.md
  - docs/sops/backup.md
  - docs/sops/storage-safety.md
  - docs/sops/vulnerability-disclosure.md
generated: "2026-08-15"
---

# paperless-ngx 2.20.15 → 3.0.5 (major)

## 1) Summary & why held

Image-only major: `ghcr.io/paperless-ngx/paperless-ngx` `2.20.15` → `3.0.5`
(published 2026-08-01), plus the env-var migration that v3 requires. The gabe565
chart stays at `0.24.1` — the chart's `appVersion` is only a default we already
override, and its template already injects what v3 newly demands (see below).

> **Security driver — detail withheld from this public repo.**
> Tracked as **F-2898fafa** (`security` / severity `accepted`).
> Full detail (CVE IDs, counts, exposure, exploitability) lives on the
> finding record — it is deliberately not reproduced here.
>
> - Dashboard: `https://sweep.<DOMAIN>/findings/F-2898fafa`
> - CLI: `runbooks/policy-cli.py finding show F-2898fafa`
>
> See `docs/sops/vulnerability-disclosure.md` before adding any
> vulnerability detail to a committed file.

**Why it is held — the upstream evidence.** `v3.0.0` ships nine changes tagged
`[BREAKING]` in its release notes, and upstream publishes a dedicated
[v3 Migration Guide](https://docs.paperless-ngx.com/migration-v3/). Five of them
land directly on this deployment:

1. **`CONSUMER_POLLING` was renamed — and the fallback is silent.** The migration
   guide's table: *"`CONSUMER_POLLING` → `CONSUMER_POLLING_INTERVAL` — Renamed for
   clarity."* v3 rewrote the consumer on `watchfiles`, and in
   `src/paperless/settings/__init__.py` the new setting defaults to `0`:
   ```python
   CONSUMER_POLLING_INTERVAL = float(os.getenv("PAPERLESS_CONSUMER_POLLING_INTERVAL", 0))
   ```
   and in `document_consumer.py`: `use_polling = polling_interval > 0`. **Our
   `/consume` is a CIFS mount** (`cifs-paperless-consume`, written by the
   `scan-inbox-validator` pod through a *different* SMB client). Native
   filesystem events do not fire for a remote write on a CIFS mount — polling is
   the only mode that works here, which is exactly why
   `PAPERLESS_CONSUMER_POLLING: 10` exists today. If the rename is missed, the
   deployment comes up **green, healthy, and silently stops ingesting scans**.
   This single line is the highest-consequence item in the plan.
2. **`CONSUMER_BARCODE_SCANNER` was removed.** *"Support for pyzbar has been
   removed… The `CONSUMER_BARCODE_SCANNER` setting has been removed. zxing-cpp is
   now the only backend."* We set `ZXING` explicitly (PATCHT separator detection
   on 300dpi duplex scans); the guide's action is *"simply remove the setting"* —
   behaviour is unchanged, the variable is not. Confirmed absent from v3
   `settings/__init__.py`.
3. **OCR control was decoupled from archive control.** `PAPERLESS_OCR_MODE` keeps
   `force` (v3 choices are `auto`/`force`/`redo`/`off`) but archive generation
   moved to a new `PAPERLESS_ARCHIVE_FILE_GENERATION` (`auto`/`always`/`never`,
   default `auto`). The guide: *"Users who relied on the old defaults must set
   `archive_file_generation` to `always` to preserve the v2 behaviour of always
   creating an archive."* We relied on the v2 default, so this must be set
   explicitly.
4. **Whoosh → Tantivy.** *"The index format is incompatible with Whoosh, so the
   search index is automatically rebuilt from scratch on first startup after
   upgrading."* Automatic, but it is a startup cost and it is the reason a
   rollback needs a manual reindex (§5). Saved views using `note:` /
   `custom_field:` prefixes are auto-rewritten to `notes.note:` /
   `custom_fields.value:`; **unqualified** saved queries are *not* migrated and
   silently stop matching note/custom-field text. We have 6 saved views and 8
   custom fields — check them (§4).
5. **API v1 support removed, versions < 9 dropped, and the default version
   jumped.** v3 `settings/__init__.py`:
   ```python
   "DEFAULT_VERSION": "10",
   "ALLOWED_VERSIONS": ["9", "10"],
   ```
   In 2.x the default was the *oldest* version. **Every one of our API clients
   sends no `Accept: application/json; version=N` header**, so all of them get
   silently promoted from v1 semantics to v10 semantics in one step — verified by
   reading the clients: `paperless-gpt` sets only `Authorization` +
   `Content-Type`; `paperless-ai` builds its axios client with the same two
   headers; the openclaw `paperless` skill sends a bare
   `Accept: application/json`. The accumulated deltas they are exposed to include
   `Tag.colour` → `Tag.color` (v2), select-type custom fields returning
   `{id,label}` objects (v7), document-note user objects (v8), **document
   `created` becoming a date instead of a datetime** (v9), and saved-view field
   removal + `merge`/`rotate`/`edit_pdf` moving off the bulk-edit endpoint plus a
   **paginated `/api/tasks/`** with renamed fields (v10). **Neither add-on exposes
   a way to set the Accept header, so there is no "pin to v9" escape hatch** —
   verification is behavioural, and the fallback is rollback.

**Two things that are already satisfied — do not "fix" them.**

- *Prerequisite version.* *"Upgrading to Paperless-ngx v3 can only be performed
  from version 2.20.15."* We are on exactly `2.20.15`. This is why the plan
  targets `3.0.5` directly and why the running version must be re-confirmed in
  pre-checks — if anything moves us off `2.20.15` first, this plan is void.
- *`PAPERLESS_DBENGINE` is now mandatory.* The chart already emits it: gabe565
  `templates/common.yaml` renders `PAPERLESS_DBENGINE: mariadb` under
  `{{- else if .Values.mariadb.enabled }}`. No action, but verify it lands (§2).

**MariaDB is NOT dropped in 3.x** — this upgrade is *not* coupled to a database
migration. `PAPERLESS_DBENGINE` accepts `mariadb`, v3 still carries MariaDB-specific
code paths (`SILENCED_SYSTEM_CHECKS = ["mysql.W003"]`), and 3.0.5 even ships a
MariaDB-specific fix (*"avoid NotSupportedError from document_importer on
MariaDB"*). Our `paperless-ngx-mariadb-0` runs 11.8.2, comfortably above Django
5.2's floor. The bundled DB/cache still being `bitnamilegacy` images is a real
and separate problem — see §6.

**Other v3 changes that apply but need no action:** the task history table is
dropped on upgrade (expected, not a fault); duplicate rejection is no longer the
default but we already set `PAPERLESS_CONSUMER_DELETE_DUPLICATES: true`;
`PAPERLESS_SECRET_KEY` is now mandatory and we already inject it from
`paperless-ngx-secret`, so **sessions and tokens survive** — do not rotate it;
`MailRule.maximum_age > 32767` is clamped by a migration (ours is far below); the
NumPy `x86-64-v2` baseline is irrelevant on NUC14 hardware; we run no pre/post
consume scripts, so the positional-argument removal is moot; and we use no OIDC
on paperless, so the allauth `token_auth_method` note does not apply.

## 2) Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) THE prerequisite — v3 is only enterable from exactly 2.20.15
mise exec -- kubectl get deploy -n office paperless-ngx \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'      # must be ...:2.20.15

# b) target tag exists
curl -s -o /dev/null -w '%{http_code}\n' \
  "https://ghcr.io/v2/paperless-ngx/paperless-ngx/manifests/3.0.5" \
  -H "Authorization: Bearer $(curl -s 'https://ghcr.io/token?scope=repository:paperless-ngx/paperless-ngx:pull' | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')" \
  -H 'Accept: application/vnd.oci.image.index.v1+json'

# c) RECORD THESE NUMBERS — they are the success criteria in §4
PPOD=$(mise exec -- kubectl get pod -n office -l app.kubernetes.io/name=paperless-ngx \
  --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}')
mise exec -- kubectl exec -n office "$PPOD" -c paperless-ngx -- python3 \
  /usr/src/paperless/src/manage.py shell -c "
from documents.models import Document, Tag, Correspondent, DocumentType, SavedView, CustomField
from paperless_mail.models import MailRule
print('docs', Document.objects.count())
print('tags', Tag.objects.count(), 'corr', Correspondent.objects.count(), 'dtype', DocumentType.objects.count())
print('savedviews', SavedView.objects.count(), 'customfields', CustomField.objects.count())
print('mailrule_max_age', [(r.id, r.maximum_age) for r in MailRule.objects.all()])
"
# Baseline captured 2026-08-15: docs 701 · tags 36 · corr 151 · dtype 11 ·
# savedviews 6 · customfields 8. Re-take at execution time; the fresh numbers win.

# d) saved views that will silently stop matching note / custom-field text.
#    (Prefixed queries are auto-migrated; UNQUALIFIED ones are NOT.)
mise exec -- kubectl exec -n office "$PPOD" -c paperless-ngx -- python3 \
  /usr/src/paperless/src/manage.py shell -c "
from documents.models import SavedView
for v in SavedView.objects.all():
    print(v.id, repr(v.name), [(r.rule_type, r.value) for r in v.filter_rules.all()])
"
# Note any rule whose value is a bare search term — those need a manual rewrite
# to 'term OR notes.note:term OR custom_fields.value:term' after the upgrade.

# e) consume backlog MUST be empty — never upgrade mid-ingest
mise exec -- kubectl exec -n office "$PPOD" -c paperless-ngx -- \
  sh -c 'ls -1 /usr/src/paperless/consume | wc -l'      # expect 0
VPOD=$(mise exec -- kubectl get pod -n office -l app.kubernetes.io/name=scan-inbox-validator \
  --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}')
mise exec -- kubectl exec -n office "$VPOD" -- sh -c 'ls -la /inbox /consume'

# f) the chart really does inject the now-mandatory DBENGINE
mise exec -- kubectl get deploy -n office paperless-ngx \
  -o jsonpath='{range .spec.template.spec.containers[0].env[*]}{.name}={.value}{"\n"}{end}' \
  | grep -E 'DBENGINE|DBHOST|CONSUMER_POLLING|BARCODE|OCR_MODE'

# g) storage healthy + backups fresh (nightly 03:00; the window is 09:00)
mise exec -- kubectl get volume -n storage paperless-data paperless-mariadb paperless-redis \
  -o custom-columns=NAME:.metadata.name,STATE:.status.state,ROBUST:.status.robustness,LASTBACKUP:.status.lastBackupAt

# h) no in-flight reconcile / unrelated breakage
mise exec -- flux get kustomizations -A | awk 'NR==1 || $5!="True"'
mise exec -- kubectl get pods -n office | grep -E 'paperless|validator'

# i) formality — NumPy x86-64-v2 baseline (classifier SIGILLs on pre-2008 CPUs).
#    NUC14 is Meteor Lake; this is a check-the-box, not a risk.
mise exec -- talosctl -n 192.168.55.11 read /proc/cpuinfo | grep -o -m1 sse4_2
```

**Stop conditions:** running image is not `2.20.15`; `/consume` non-empty; any
Longhorn volume not `healthy`; `lastBackupAt` older than the previous night.

## 3) Steps

1. **Marker + alert silence** (per `docs/sops/application-update.md` §4 — this is
   an attended major, expect restart/not-ready noise):
   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   runbooks/update-marker.sh add paperless-ngx office 3 "2.20.15 -> 3.0.5 major"

   mise exec -- kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 &
   NOW=$(python3 -c "from datetime import *;print(datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
   END=$(python3 -c "from datetime import *;print((datetime.now(timezone.utc)+timedelta(hours=3)).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
   curl -s -X POST localhost:9093/api/v2/silences -H 'Content-Type: application/json' -d '{
     "matchers":[{"name":"namespace","value":"office","isRegex":false,"isEqual":true},
                 {"name":"alertname","value":"Kube(Pod|Deployment|Container).*","isRegex":true,"isEqual":true}],
     "startsAt":"'$NOW'","endsAt":"'$END'","createdBy":"maintenance-window-agent",
     "comment":"paperless-ngx 2.20.15->3.0.5 — rollout noise. auto-expires 3h"}'
   ```

2. **Take the pre-upgrade DB dump. This is the only rollback anchor** — v3's
   Django migrations are one-way and `maxHistory: 1` means `helm rollback` cannot
   reach the pre-upgrade revision:
   ```bash
   STAMP=$(date +%F-%H%M)
   mise exec -- kubectl exec -n office paperless-ngx-mariadb-0 -c mariadb -- \
     sh -c 'mariadb-dump -u root -p"$MARIADB_ROOT_PASSWORD" \
              --single-transaction --routines --triggers --databases "$MARIADB_DATABASE"' \
     > /tmp/paperless-mariadb-$STAMP.sql
   ls -l /tmp/paperless-mariadb-$STAMP.sql            # MUST be non-trivial, not 0 bytes
   head -5 /tmp/paperless-mariadb-$STAMP.sql          # real SQL, not an error message
   grep -c 'CREATE TABLE' /tmp/paperless-mariadb-$STAMP.sql   # expect dozens
   ```
   Park a durable copy on the (Retain-policy) export share so it survives the pod:
   ```bash
   PPOD=$(mise exec -- kubectl get pod -n office -l app.kubernetes.io/name=paperless-ngx \
     --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}')
   mise exec -- kubectl cp /tmp/paperless-mariadb-$STAMP.sql \
     office/$PPOD:/usr/src/paperless/export/paperless-mariadb-$STAMP.sql -c paperless-ngx
   ```
   > **Storage safety:** this step only *writes* to `cifs-paperless-export`. No
   > CIFS/SMB PVC is deleted anywhere in this plan. If any step ever appears to
   > require one, STOP and run the `docs/sops/storage-safety.md` pre-flight — the
   > `cifs-paperless-*` classes are per-app-share-wipe severe.

3. **Edit `kubernetes/apps/office/paperless-ngx/app/helmrelease.yaml`** — five
   changes, all under `spec.values`:

   | # | Change | Why |
   |---|---|---|
   | a | `image.tag: "2.20.15"` → `"3.0.5"` | the upgrade |
   | b | `env.PAPERLESS_CONSUMER_POLLING: 10` → `env.PAPERLESS_CONSUMER_POLLING_INTERVAL: 10` | **rename; without it, CIFS ingestion silently dies** |
   | c | delete `env.PAPERLESS_CONSUMER_BARCODE_SCANNER: "ZXING"` | setting removed upstream; zxing-cpp is now the only backend |
   | d | add `env.PAPERLESS_ARCHIVE_FILE_GENERATION: "always"` | preserves the v2 always-archive behaviour that we relied on by default |
   | e | `upgrade.remediation.retries: 1` → `0` **and** add `remediateLastFailure: false` | stops Flux rolling the migration back mid-flight (SOP §4 Step 2) |

   Keep every comment block in the file — the `OCR_MODE=force` / 6Gi rationale,
   the rotate-threshold note, the `FILENAME_FORMAT_REMOVE_NONE` note. **Do not
   touch** `resources.limits.memory: 6Gi` (force-OCR OOMs below it),
   `PAPERLESS_OCR_MODE: "force"` (still a valid v3 choice),
   `PAPERLESS_SECRET_KEY` (rotating it invalidates every session and token), the
   chart version, or anything under `mariadb:` / `redis:`.

   Extend the barcode comment so the next reader knows why the scanner setting
   vanished, e.g.:
   ```yaml
   # ZXING is the only barcode backend as of v3 (pyzbar removed upstream) —
   # PAPERLESS_CONSUMER_BARCODE_SCANNER no longer exists. PATCHT splitting is
   # unchanged. See docs/sops/paperless.md.
   PAPERLESS_CONSUMER_ENABLE_BARCODES: true
   # Renamed in v3 (was PAPERLESS_CONSUMER_POLLING). MUST stay > 0: /consume is a
   # CIFS mount written by the validator pod, and native fs events never fire for
   # a remote SMB write — interval 0 would silently stop all scanner ingestion.
   PAPERLESS_CONSUMER_POLLING_INTERVAL: 10
   ```

4. **Validate, commit, push** (on `main`, staging only these hunks):
   ```bash
   mise exec -- kubeconform -summary -exit-on-error -ignore-missing-schemas \
     kubernetes/apps/office/paperless-ngx
   git add -p kubernetes/apps/office/paperless-ngx/app/helmrelease.yaml
   git commit -m "feat(paperless-ngx): 2.20.15 -> 3.0.5 major + v3 env migration (F-2898fafa)"
   git push
   ```
   > Commit-message rule: `F-2898fafa` only. No advisory IDs, no counts — see
   > `docs/sops/vulnerability-disclosure.md` §2.2.

5. **Watch the migration run.** Do not hand-delete pods; do not `flux reconcile
   --force` unless the HelmRelease is visibly stuck:
   ```bash
   mise exec -- kubectl logs -n office -l app.kubernetes.io/name=paperless-ngx \
     -c paperless-ngx -f --tail=100
   ```
   Expect, in order: init containers wait for mariadb/redis → `Apply migrations`
   (including the MailRule clamp and the saved-view query rewrite) → a Tantivy
   index build → `Watching /usr/src/paperless/consume using polling (interval:
   10.0s)`. **That last line is the proof that step 3b landed.** Startup is
   noticeably longer than a normal roll — the index rebuild is doing real work.

6. **On success:** restore `upgrade.remediation.retries: 3`, remove
   `remediateLastFailure: false`, commit + push; drop the Alertmanager silence;
   `runbooks/update-marker.sh clear paperless-ngx`.
   **On failure:** §5, and clear the marker either way.

7. **Record the post-upgrade scan result on the finding — not in this file:**
   ```bash
   mise exec -- trivy image ghcr.io/paperless-ngx/paperless-ngx:3.0.5 \
     --severity CRITICAL,HIGH --ignore-unfixed > /tmp/post-scan.txt
   source runbooks/lib/sweep-pg-dsn.sh && sweep_pg_dsn_up
   runbooks/policy-cli.py finding detail F-2898fafa \
     --plan paperless-ngx-3.0.5 --component paperless-ngx --detail-file /tmp/post-scan.txt
   rm -f /tmp/post-scan.txt
   ```

## 4) Verification

```bash
cd /Users/mu/code/cberg-home-nextgen
PPOD=$(mise exec -- kubectl get pod -n office -l app.kubernetes.io/name=paperless-ngx \
  --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}')

# a) Flux + rollout
mise exec -- kubectl get helmrelease -n office paperless-ngx \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'          # True
mise exec -- kubectl get deploy -n office paperless-ngx \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'                # ...:3.0.5
mise exec -- kubectl get pods -n office | grep -E 'paperless|validator'        # Ready, restarts stable
mise exec -- kubectl get deploy -n office paperless-ngx \
  -o jsonpath='{.spec.template.spec.containers[0].resources.limits.memory}{"\n"}'   # 6Gi

# b) THE load-bearing check — the consumer is in POLLING mode, not fs-events mode
mise exec -- kubectl logs -n office "$PPOD" -c paperless-ngx | grep -i "Watching .*consume"
#    MUST read: "using polling (interval: 10.0s)".
#    "using native file system events" = ingestion is dead. Treat as a FAILURE.

# c) data intact — compare against the §2c baseline, exactly
mise exec -- kubectl exec -n office "$PPOD" -c paperless-ngx -- python3 \
  /usr/src/paperless/src/manage.py shell -c "
from documents.models import Document, Tag, Correspondent, DocumentType, SavedView, CustomField
print('docs', Document.objects.count())
print('tags', Tag.objects.count(), 'corr', Correspondent.objects.count(), 'dtype', DocumentType.objects.count())
print('savedviews', SavedView.objects.count(), 'customfields', CustomField.objects.count())
"

# d) Tantivy index actually got built — full-text search returns hits
mise exec -- kubectl exec -n office "$PPOD" -c paperless-ngx -- python3 \
  /usr/src/paperless/src/manage.py shell -c "
from documents.models import Document
d = Document.objects.exclude(content='').first()
w = [t for t in (d.content or '').split() if len(t) > 5][:1]
print('probe term:', w)
"
#    then, with that term, through the API (also proves auth + serialisation):
DOM=$(mise exec -- kubectl get secret -n flux-system cluster-secrets -o jsonpath='{.data.SECRET_DOMAIN}' | base64 -d)
curl -s -o /dev/null -w 'ingress %{http_code}\n' --max-time 20 "https://paperless.$DOM/"

# e) end-to-end ingestion — the real test (docs/sops/paperless.md §6.2)
#    Run the scanner's "paperless" preset on a 2-3 page document, or drop a known
#    PDF into the inbox share via the validator pod. Then:
VPOD=$(mise exec -- kubectl get pod -n office -l app.kubernetes.io/name=scan-inbox-validator \
  --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}')
mise exec -- kubectl logs -n office "$VPOD" --tail=30        # "moved -> consume"
mise exec -- kubectl logs -n office "$PPOD" -c paperless-ngx --tail=80 | grep -i consum
#    Document count must increase by 1. OCR text must be German-correct (deu+eng,
#    force) and an ARCHIVE file must exist for it — that is what step 3d bought:
mise exec -- kubectl exec -n office "$PPOD" -c paperless-ngx -- python3 \
  /usr/src/paperless/src/manage.py shell -c "
from documents.models import Document
d = Document.objects.order_by('-added').first()
print(d.id, d.title, 'archive:', bool(d.archive_filename), 'chars:', len(d.content or ''))
"

# f) barcode split still works — two docs separated by a PATCHT page yield TWO
#    documents with the separator discarded (pyzbar is gone; zxing-cpp only).

# g) API CONSUMERS — the default version moved v1 -> v10 under them
mise exec -- kubectl logs -n office -l app.kubernetes.io/name=paperless-gpt --tail=100 \
  | grep -iE 'error|406|not acceptable|unexpected|nil|panic'
mise exec -- kubectl logs -n office -l app.kubernetes.io/name=paperless-ai --tail=100 \
  | grep -iE 'error|406|undefined|failed'
#    Behavioural, not just log-clean: tag a document `paperless-gpt` and confirm
#    it is picked up, OCR'd and re-titled; confirm paperless-ai's */30 run tags a
#    fresh document. Custom fields (8 of them) and tag colours are the most
#    likely breakage (API v7 / v2 deltas).
#    openclaw skill smoke (it also sends no version header):
mise exec -- kubectl exec -n ai deploy/openclaw -- \
  sh -lc 'python3 ~/clawd/skills/paperless.py search Rechnung 2>&1 | head -20'
#    arag-web files bills into paperless — exercise one push before calling done.
```

**Success =** HelmRelease Ready on `3.0.5`; the consumer log line says
**polling**; object counts match the §2c baseline exactly; a fresh scan completes
end-to-end with correct German OCR *and* an archive file; search returns hits;
and all four API consumers (paperless-gpt, paperless-ai, openclaw skill,
arag-web) still work. Anything less is a rollback, not a "watch it for a day".

## 5) Rollback

**The DB migration does not reverse.** Reverting the image alone against a
v3-migrated schema leaves 2.20.15 facing tables it does not understand. The
rollback is therefore *revert + restore*, and it needs the §3.2 dump.

```bash
cd /Users/mu/code/cberg-home-nextgen

# 1) revert the version+env commit (this also restores CONSUMER_POLLING etc.)
git revert --no-edit <upgrade-commit-sha>
git push

# 2) scale paperless down so nothing writes during the restore
mise exec -- kubectl scale deploy -n office paperless-ngx --replicas=0
mise exec -- kubectl rollout status deploy/paperless-ngx -n office --timeout=180s

# 3) restore the pre-upgrade database (the dump was taken with --databases, so it
#    recreates and re-selects the schema itself)
mise exec -- kubectl exec -i -n office paperless-ngx-mariadb-0 -c mariadb -- \
  sh -c 'mariadb -u root -p"$MARIADB_ROOT_PASSWORD"' < /tmp/paperless-mariadb-<STAMP>.sql
# (If the local copy is gone, the durable one is on the export share:
#  /usr/src/paperless/export/paperless-mariadb-<STAMP>.sql )

# 4) bring it back on 2.20.15
mise exec -- kubectl scale deploy -n office paperless-ngx --replicas=1
mise exec -- kubectl rollout status deploy/paperless-ngx -n office --timeout=600s

# 5) rebuild the WHOOSH index — v3 replaced the on-disk index with a Tantivy one
#    that 2.20.15 cannot read. Search stays broken until this runs.
PPOD=$(mise exec -- kubectl get pod -n office -l app.kubernetes.io/name=paperless-ngx \
  --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}')
mise exec -- kubectl exec -n office "$PPOD" -c paperless-ngx -- python3 \
  /usr/src/paperless/src/manage.py document_index reindex
```

**Confirmed back =** image is `2.20.15`; document count matches the §2c baseline;
the consumer log line reports polling at 10s; a test scan ingests end-to-end;
search returns hits; paperless-gpt / paperless-ai logs clean; `https://paperless.<DOMAIN>/`
returns 200.

If the dump restore itself fails, the fallback is the nightly Longhorn backup of
`paperless-mariadb` (`docs/sops/backup.md`) — expect to lose the day's ingests.
**Never** delete a `cifs-paperless-*` PVC as part of any recovery
(`docs/sops/storage-safety.md`): the document media is on those shares and it is
never the thing that needs repairing here.

## 6) Interference notes

- **Solo window.** `est_duration_min: 75` in a 90-minute slot, and Step 0 of every
  window (the safe-update auto-apply, `docs/sops/auto-update.md`) runs first. Do
  not co-schedule anything else on `sat-early:2026-09-19`. If Step 0 happens to
  carry a `paperless-gpt` / `paperless-ai` image bump (both are pinned to
  `latest`, so their content moves independently of any PR), note it — a
  simultaneous add-on change would confound §4g. Prefer to defer add-on churn to
  the following window so the API-consumer verdict is clean.
- **`namespaces: [office, ai]` is deliberate.** Nothing in `ai` is *mutated*, but
  openclaw's `paperless` skill and mcpo's paperless MCP are API clients that get
  silently promoted from API v1 to v10 semantics by this upgrade. `arag-web`
  (also `office`) files bills through the same API. Four consumers, none of which
  can pin a version — this is the single widest blast-radius item after the
  polling rename.
- **`shared: []` is honest.** The ingress object is untouched, the DB and cache
  are per-app subcharts, and no cert-manager / CNI / coredns / shared-DB surface
  is involved. What this plan *does* generate is sustained IO on `paperless-data`
  (full index rebuild) and `paperless-mariadb` (schema migration) — hence
  `conflicts_with: longhorn-1.12.1-engine` (`sat-early:2026-09-05`, comfortably
  before this window) rather than a blanket `shared: [storage]` that would
  false-positive against every storage-adjacent plan.
- **Relationship to the bitnamilegacy exit (separate plan, do not duplicate
  here).** The bundled `bitnamilegacy/mariadb:latest` and
  `bitnamilegacy/redis:latest` come from an archived registry that will never
  publish another fix; replacing them is its own plan. The two are **independent
  but must not share a window**, and **this plan should run first**:
  1. v3 does not require the DB move — MariaDB is fully supported in 3.x, so
     there is no forced coupling and no reason to serialise the security fix
     behind a data migration.
  2. Running an engine migration and a schema-breaking major in one window means
     a failure cannot be attributed, and the two rollbacks fight each other (one
     restores a dump into the old engine, the other repoints at a new one).
  3. The engine migration will use `document_exporter` / `document_importer`, and
     3.0.5 specifically fixes a `document_importer` failure on MariaDB — doing
     the version upgrade first means the migration runs on the fixed tooling.

  Add the real plan_id to `conflicts_with` (placeholder comment in the
  frontmatter) once that plan exists.
- **Ownership.** `paperless-ngx` is operationally owned by the `paperless-agent`
  (`docs/sops/paperless.md`). Bring it in for §4e/§4f/§4g — the ingestion,
  barcode-split and OCR-quality judgements are its call, and the OCR traps
  (`OCR_MODE=force` needs the 6Gi limit; a near-blank duplex back can ParseError
  and wedge `/consume` on every poll) are exactly the failure modes a fresh major
  can resurface.
- **User-visible downtime** is the pod roll plus the index rebuild — call it a
  few minutes with search degraded until Tantivy finishes. Scans landing in
  `/inbox` during the window are safe: the validator holds them and paperless
  picks them up on the next poll *provided step 3b landed*.
