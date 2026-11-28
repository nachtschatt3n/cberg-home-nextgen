---
plan_id: paperless-ngx-fleet-3.5.0
component: paperless-ngx
pr: null                              # No Renovate PR (gh pr list --search paperless, 2026-11-18: only
                                      # #240 redis and #523 python are open). Held by coverage.py's
                                      # direct-bump lane, gate G3 (migrations in the diff).
kind: image
current: "3.4.2"                      # live-verified 2026-11-18: HelmRelease values.image.tag, pod image
                                      # (digest sha256:d704e84f...), and deployment/scan-inbox-validator
target: "3.5.0"                       # tag verified 2026-11-18: GitHub release v3.5.0 (published
                                      # 2026-11-17) AND ghcr manifest 3.5.0 -> HTTP 200,
                                      # index digest sha256:8c1e2c4e0abb50576c7a09f062ed581e2d955e298a302e1e196a35338639005e
update_type: minor
risk: medium                          # schema migrations are trivial on our data (see 1.2), but they make
                                      # a plain `git revert` NON-working, and an un-flagged settings change
                                      # (ALLOWED_HOSTS, 1.3) would 400 every in-cluster API consumer.
est_duration_min: 45                  # dump+gate 5, baselines 3, edit/commit 5, reconcile+pull+migrate ~5,
                                      # verification 20 (incl. one end-to-end scan-pipeline document), slack 7.
                                      # Rollback (not included): R1 ~15 min, R2 ~25 min.
needs_reboot: false
touches:
  namespaces: [office]
  resources:
    - helmrelease/paperless-ngx                 # image tag + one new env var (PAPERLESS_ALLOWED_HOSTS)
    - deployment/paperless-ngx                  # Recreate roll; runs Django migrations 0028-0030 at start
    - deployment/scan-inbox-validator           # same image, same commit (SOP: never let the tags diverge)
    - pvc/paperless-db-data                     # schema change via the app's migrations (13 DROP COLUMN,
                                                # 1 ADD COLUMN); the paperless-db Deployment itself is NOT edited
    - pvc/paperless-ngx-consume                 # verification drops one generated PDF through inbox -> consume
    - pvc/paperless-ngx-inbox
  shared: [monitoring, paperless-api-consumers]  # monitoring: §4 CONTROL lines read Prometheus/Alertmanager.
                                                # paperless-api-consumers: openclaw (ns ai) and arag-web (ns office)
                                                # call the API by Service name; NOT restarted, but they break if
                                                # step 3.2 is skipped (see 1.3). Gateway/route untouched.
depends_on: []
conflicts_with:
  - kube-prometheus-stack-93.3.0              # §4 reads Prometheus/Alertmanager (the window's instrument)
  - redis-fleet-8.10.3                        # rolls deployment/paperless-redis AND checks deployment/paperless-ngx
  - flux-oci-chart-sources                    # stage 3 edits this same helmrelease.yaml (chart source move)
  - nextcloud-12.0.2                          # office-ns backup-restore plan: two restore-class rollbacks
  - bitnamilegacy-exit-nextcloud-db           # (same convention as the executed paperless-db-13.0.2)
  - nextcloud-9.4.5   # plan-refine 2026-11-28: successor of a dead ref
  # plan-refine 2026-11-28: dead ref(s) nextcloud-9.4.3 pruned
exclusive: false
security_ref: null                            # no security driver. F-51c2b4cc / F-fcbc238d (AR-029, accepted,
                                              # on 3.4.2) exist; this plan makes NO claim about them -- re-read
                                              # the security sweep after execution.
capability_change: true                       # NOT a same-behaviour bump: bulk-edit API calls become async
                                              # hand-offs (#14773/#14711), Host-header policy narrows (#14735),
                                              # new manual workflow trigger + markdown notes (#14704/#14626).
rollback_class: backup-restore                # a manifest revert ALONE leaves 3.4.2 reading a schema without its
                                              # 13 tn_* columns -> every tag query errors. Rollback = reverse
                                              # migration (R1) or restore of the in-window dump (R2); §5.
backup_gate: "in-window mariadb-dump of database paperless (--default-character-set=utf8mb4 --single-transaction --add-drop-database), proven by ONE fail-closed script under set -euo pipefail (§3.1) that exits non-zero on: missing '-- Dump completed' trailer, <75 CREATE TABLE, no documents_document table, <20 MB, or zero 4-byte lines with a passing positive control -- taken AFTER §2 and BEFORE the commit in §3.3"
finding_refs: []                              # policy-cli finding list --grep paperless-ngx (2026-11-18): no
                                              # version/plan finding exists for 3.5.0 (held by coverage.py only).
review: null
status: draft
window: null
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/paperless.md
  - docs/sops/backup.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-11-18"
premises:
  - id: hr-on-current-tag
    why: The plan bumps 3.4.2. If the HelmRelease already moved, the migration already ran and this plan is stale.
    run: kubectl get helmrelease paperless-ngx -n office -o jsonpath='{.spec.values.image.tag}'
    expect_exact: "3.4.2"
  - id: validator-on-current-tag
    why: The validator must move in the same commit; a different live tag means someone bumped one half already.
    run: kubectl get deploy scan-inbox-validator -n office -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "ghcr.io/paperless-ngx/paperless-ngx:3.4.2"
  - id: main-hr-anchor
    why: Step 3.2's sed matches exactly one quoted 3.4.2 in helmrelease.yaml; zero or two makes it a no-op or a double edit.
    run: git show origin/main:kubernetes/apps/office/paperless-ngx/app/helmrelease.yaml | grep -c -F -e '"3.4.2"'
    expect_exact: "1"
  - id: main-validator-anchor
    why: Step 3.2's second sed anchor.
    run: git show origin/main:kubernetes/apps/office/paperless-ngx/app/validator-deployment.yaml | grep -c -F -e 'paperless-ngx:3.4.2'
    expect_exact: "1"
  - id: allowed-hosts-not-yet-set
    why: Step 3.2's python edit refuses to run if the var exists; if someone added it, re-read the value instead of adding a second one.
    run: git show origin/main:kubernetes/apps/office/paperless-ngx/app/helmrelease.yaml | grep -c PAPERLESS_ALLOWED_HOSTS
    expect_exact: "0"
  - id: app-ready
    why: Baselines and the dump in section 2-3 need a healthy 3.4.2 app and DB.
    run: kubectl get deploy paperless-ngx paperless-db scan-inbox-validator -n office -o jsonpath='{.items[*].status.readyReplicas}'
    expect_exact: "1 1 1"
  - id: app-strategy-recreate
    why: Single replica on RWO longhorn-static paperless-data; RollingUpdate would Multi-Attach-deadlock the roll.
    run: kubectl get deploy paperless-ngx -n office -o jsonpath='{.spec.strategy.type}'
    expect_exact: "Recreate"
  - id: probes-are-tcp
    why: The 3.5.0 ALLOWED_HOSTS narrowing would 400 an httpGet probe sent with the pod IP as Host; this plan relies on all three probes being tcpSocket on 8000.
    run: kubectl get deploy paperless-ngx -n office -o jsonpath='{.spec.template.spec.containers[0].startupProbe.tcpSocket.port} {.spec.template.spec.containers[0].livenessProbe.tcpSocket.port} {.spec.template.spec.containers[0].readinessProbe.tcpSocket.port}'
    expect_exact: "8000 8000 8000"
  - id: nightly-dump-has-succeeded
    why: Second, independent restore source behind the in-window dump. Freshness (under 26h) is checked in pre-check 2.2.
    run: kubectl get cronjob db-dump-paperless-db -n office -o jsonpath='{.status.lastSuccessfulTime}'
    expect_matches: '^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$'
needs_replan: "channel-unresolved: channel-unresolved: coverage could not confirm 3.5.1 is the stable-channel head"
needs_replan_since: "2026-11-28"
---

# paperless-ngx 3.4.2 -> 3.5.0 (app + scan-inbox-validator, one image fleet)

## 1. Summary & why held

**What changes.** `ghcr.io/paperless-ngx/paperless-ngx` 3.4.2 -> 3.5.0 on both
consumers of the image in `office`: the `paperless-ngx` HelmRelease
(`values.image.tag`) and `deployment/scan-inbox-validator`
(`validator-deployment.yaml`, which reuses the image only for python3 + pikepdf).
The SOP rule holds: both in ONE commit. Plus one new env var on the app,
`PAPERLESS_ALLOWED_HOSTS` (1.3) -- **this var is required, not optional.**

### 1.1 Why held (coverage.py G3)
Three new Django migrations in `src/documents/migrations/` (read at tag v3.5.0):

| Migration | Operations | Reversible by Django? |
|---|---|---|
| `0028_replace_tag_tree_fields` | 13x `RemoveField` on `Tag`: `tn_ancestors_count/_pks`, `tn_children_count/_pks`, `tn_depth`, `tn_descendants_count/_pks`, `tn_index`, `tn_level`, `tn_order`, `tn_priority`, `tn_siblings_count/_pks` (upstream "Performance: replace django-treenode with adjacency-list tags", #14612; `treenode` leaves `INSTALLED_APPS`). `tn_parent` is **kept** and is the new adjacency link. | Columns come back with their defaults (all 13 have `default=` in django-treenode's model), but their CONTENTS are gone. They are derived caches, rebuildable with `Tag.update_tree()` on 3.4.2. |
| `0029_alter_workflowrun_type_alter_workflowtrigger_type` | `AlterField` choices only: adds `(5, "Manual")` | Yes (no SQL of substance) |
| `0030_note_format` | `AddField note.format` CharField default `"plain"` | Yes (drops the column) |

No other app ships a migration in this range (the 255-file compare
v3.4.2...v3.5.0 contains only these three migration files). The tantivy search
index is untouched (no file under `src/documents/search/` changed), so **no index
rebuild at start** -- the start-up budget is the measured ~96 s no-op restart
against the 150 s startupProbe (SOP §6a.4). The AI vector store keeps
`SCHEMA_VERSION = 2` in both tags; the new `VEC0_CHUNK_SIZE`/`DB_PAGE_SIZE`
apply only to a newly created or rebuilt store, so **no re-embed** is triggered.

### 1.2 Measured on our data (read-only, 2026-11-18)
- Applied head: `documents.0027_documentbarcode` (so exactly 0028-0030 will run).
- `documents_tag`: **51 tags, 0 with `tn_parent_id` set** -- the tag tree is flat,
  so the dropped caches carry no structure; `tn_*` columns present: 14 (13 to drop + `tn_parent`).
- `documents_note`: 0 rows; `documents_workflowtrigger`: 0 rows -- 0029/0030 touch nothing.
- `documents_document`: 1241 rows (max id 1476); `documents_document_tags`: 2978.
- All 75 tables `utf8mb4_general_ci`; schema 45.2 MB; DB `13.0.2-MariaDB`.
- Backups: CronJob `office/db-dump-paperless-db` last success 2026-11-17T21:54Z;
  Longhorn `paperless-db-data` / `paperless-data` backed up 2026-11-17T23:0xZ, healthy.

So the migration itself is low-risk here. What it costs is the rollback: after
0028 a manifest revert is no longer a rollback (3.4.2's model SELECTs the 13
dropped columns -> `OperationalError: Unknown column` on every tag query).
Hence `rollback_class: backup-restore` and §5 as a procedure.

### 1.3 The breaking change the hold did NOT name -- ALLOWED_HOSTS (#14735)
Release note: *"Note that some users may need to adjust their
`PAPERLESS_ALLOWED_HOSTS` setting with this release"*. The code
(`src/paperless/settings/__init__.py`, v3.5.0):

```python
def _get_allowed_hosts() -> list[str]:
    if "PAPERLESS_ALLOWED_HOSTS" in os.environ or os.getenv("PAPERLESS_URL"):
        allowed_hosts = get_list_from_env("PAPERLESS_ALLOWED_HOSTS")
    else:
        allowed_hosts = ["*"]
```

3.4.2 was `get_list_from_env("PAPERLESS_ALLOWED_HOSTS", default=["*"])`. We set
`PAPERLESS_URL` and not `PAPERLESS_ALLOWED_HOSTS`, so ALLOWED_HOSTS goes from the
live `['*', 'paperless.<domain>']` (measured in-pod via `django.conf.settings`)
to `['localhost', 'paperless.<domain>']`. Every request whose Host is the
Service name gets **HTTP 400 DisallowedHost**. In-cluster callers by Service
name (URLs decrypted read-only from their SOPS secrets, host part only):

| Consumer | URL host | Today |
|---|---|---|
| openclaw `paperless` skill (ns `ai`) | `paperless-ngx.office.svc.cluster.local:8000` | 200 |
| arag-web PaperlessSyncJob etc. (ns `office`) | `paperless-ngx.office.svc.cluster.local:8000` | 200 |
| `runbooks/health-check.sh:7878` | `paperless-ngx.office.svc:8000` | -- |
| arag-scrape (Mac), browser users, Envoy | `paperless.<domain>` (public route) | unaffected |
| kubelet probes | tcpSocket 8000 | unaffected (premise `probes-are-tcp`) |
| mcpo | no paperless server in live `mcpo-config` (only the API key env remains) | n/a |

Without step 3.2's env var the app comes up **Ready and green** and silently
breaks openclaw + arag-web -- a pure shape-check pass. §4.4 is the gate for it,
with a negative control.

### 1.4 Other notable changes (no action, but know them)
- Bulk edit / bulk metadata operations become async hand-offs (#14773, #14711):
  `POST /api/documents/bulk_edit/` returns a task, not a finished edit. No
  repo/cluster consumer calls bulk_edit (grepped openclaw skill, arag-web,
  arag-scrape, runbooks); the paperless-agent's manual bulk recipes must poll the
  task before reading back.
- New celery beat task clears expired sessions (#14722); markdown notes; manual
  workflow trigger; django-allauth 65.20 -> 65.21.1; MFA trusted-AMR default fix.

## 2. Pre-checks

Run from the repo root on the Mac mini (zsh). Abort the plan on any failure.

**2.1 Premises + no in-flight work**
```bash
.venv/bin/python3 runbooks/plan-premises.py paperless-ngx-fleet-3.5.0 --require-premises
flux get kustomizations -n office | awk 'NR==1 || /paperless/'
flux get helmreleases -n office | awk 'NR==1 || /paperless/'
# Inbox and consume dirs empty (nothing mid-ingest). Expect both counts 0:
kubectl exec -n office deploy/scan-inbox-validator -- python3 -c "import os;print(len([f for f in os.listdir('/inbox') if not f.startswith(('.','_'))]), len([f for f in os.listdir('/consume') if not f.startswith('.')]))"
```
If either count is non-zero, wait ~2 min and re-run (validator polls every 15 s,
consumer every 10 s). Do not start while a document is in flight.

**2.2 Backup freshness (second restore source)**
```bash
kubectl get cronjob db-dump-paperless-db -n office -o jsonpath='{.status.lastSuccessfulTime}{"\n"}'
kubectl get volume paperless-db-data paperless-data -n storage -o custom-columns=NAME:.metadata.name,LAST:.status.lastBackupAt,ROB:.status.robustness
```
PASS: lastSuccessfulTime within the last 26 h; both volumes `healthy`.

**2.3 Baselines (the CONTENTS reference for §4) -- save to a file**
```bash
mkdir -p ~/backups/paperless-db && chmod 0700 ~/backups/paperless-db
BASE=~/backups/paperless-db/pre-3.5.0-baseline.txt
kubectl exec -n office deploy/paperless-db -- sh -c 'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" -N paperless -e "
SELECT \"head\", name FROM django_migrations WHERE app=\"documents\" ORDER BY id DESC LIMIT 1;
SELECT \"maxdoc\", MAX(id) FROM documents_document;
SELECT \"docs\", COUNT(*) FROM documents_document;
SELECT \"tags\", COUNT(*) FROM documents_tag;
SELECT \"tagparents\", COUNT(*) FROM documents_tag WHERE tn_parent_id IS NOT NULL;
SELECT \"doctags_old\", COUNT(*) FROM documents_document_tags WHERE document_id <= (SELECT MAX(id) FROM documents_document);
SELECT \"corr\", COUNT(*) FROM documents_correspondent;
SELECT \"dtypes\", COUNT(*) FROM documents_documenttype;
SELECT \"mailrules\", COUNT(*) FROM paperless_mail_mailrule;
SELECT \"tokens\", COUNT(*) FROM authtoken_token;
SELECT \"tncols\", COUNT(*) FROM information_schema.columns WHERE table_schema=\"paperless\" AND table_name=\"documents_tag\" AND column_name LIKE \"tn\\_%\";"' 2>/dev/null | tee "$BASE"
grep -c . "$BASE"   # must print 11 -- fewer means a query failed silently
```
Expected today (2026-11-18): head `0027_documentbarcode`, tags 51, tagparents 0,
tncols 14. `head` other than 0027 -> STOP (the plan is stale).

**2.4 Host-header baseline (proves §4.4 can discriminate)**
```bash
kubectl exec -n office deploy/paperless-ngx -c paperless-ngx -- python3 -c '
import urllib.request as u, urllib.error as e
for h in ("paperless-ngx.office.svc.cluster.local:8000","paperless-ngx.office.svc:8000","paperless-ngx:8000","bogus.invalid"):
    r=u.Request("http://127.0.0.1:8000/api/", headers={"Host": h})
    try: c=u.urlopen(r,timeout=10).status
    except e.HTTPError as x: c=x.code
    print(h,c)'
```
Measured 2026-11-18 on 3.4.2: all four print `200` (ALLOWED_HOSTS `*`). On 3.5.0
`bogus.invalid` must flip to `400` -- that flip is the negative control in §4.4.

**2.5 Consumer canaries (must be green BEFORE, or a later failure is not ours)**
```bash
OPOD=$(kubectl get pod -n ai -l app.kubernetes.io/name=openclaw -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n ai "$OPOD" -c app -- paperless search ARAG | grep -c '"id"'      # >= 1 (measured: JSON list)
kubectl exec -n office deploy/arag-web -- sh -c 'ruby -e "require %q(net/http); u=URI(ENV[%q(PAPERLESS_API_URL)]+%q(/documents/?page_size=1)); r=Net::HTTP::Get.new(u); r[%q(Authorization)]=%q(Token )+ENV[%q(PAPERLESS_API_KEY)]; puts Net::HTTP.start(u.host,u.port){|h| h.request(r)}.code"'   # 200 (measured)
```

## 3. Steps

**3.1 Logical dump -- the R2 rollback floor (fail-closed; take it LAST before the commit)**

Same proven shape as the executed `paperless-db-13.0.2` §3.2, narrowed to the
`paperless` database (grants live in `mysql.*` and are not touched by this plan,
so they are deliberately NOT in the dump; `--add-drop-database` makes the
restore a clean replace).
```bash
set -euo pipefail
DUMP=~/backups/paperless-db/paperless-pre-3.5.0-$(date +%Y%m%d%H%M).sql
echo "$DUMP" > ~/backups/paperless-db/LATEST-pre-3.5.0   # §5 reads the path from here (fresh shell safe)
kubectl exec -n office deploy/paperless-db -- sh -c \
  'mariadb-dump --default-character-set=utf8mb4 --single-transaction --routines --events \
   --databases paperless --add-drop-database -uroot -p"$MARIADB_ROOT_PASSWORD"' > "$DUMP"
chmod 0600 "$DUMP"
tail -1 "$DUMP" | grep -q -- '-- Dump completed' || { echo "ABORT: no '-- Dump completed' trailer"; exit 1; }
T=$(grep -c 'CREATE TABLE' "$DUMP" || true); echo "CREATE TABLE=$T"
[ "$T" -ge 75 ] || { echo "ABORT: only $T CREATE TABLE (live schema has 75)"; exit 1; }
grep -qE '^CREATE TABLE `?documents_document`?[^a-zA-Z0-9_]' "$DUMP" || { echo "ABORT: no documents_document"; exit 1; }
S=$(wc -c < "$DUMP" | tr -d ' '); echo "bytes=$S"
[ "$S" -gt 20000000 ] || { echo "ABORT: $S bytes (schema is ~45 MB on disk; nightly dump ~44 MB)"; exit 1; }
FB(){ /usr/bin/python3 -c "import sys;print(sum(1 for l in open(sys.argv[1],'rb') if any(0xf0<=b<=0xf4 for b in l)))" "$1"; }
printf 'ascii\nemoji \xf0\x9f\x93\x84 here\n' > /tmp/ctl.txt
[ "$(FB /tmp/ctl.txt)" -eq 1 ] || { echo "ABORT: 4-byte checker broken (positive control)"; exit 1; }
[ "$(FB "$DUMP")" -gt 0 ] || { echo "ABORT: dump lost 4-byte content (live has emoji mail subjects)"; exit 1; }
echo "GATE PASSED -- $DUMP"
set +euo pipefail
```
Run it in a subshell or a dedicated terminal so `set -e` cannot kill the
executor's session. Any `ABORT` -> stop the plan; nothing has changed yet.

**3.2 Edit (dry-tested 2026-11-18 on scratch copies with BSD sed + /usr/bin/python3)**
```bash
cd /Users/mu/code/cberg-home-nextgen
HR=kubernetes/apps/office/paperless-ngx/app/helmrelease.yaml
VAL=kubernetes/apps/office/paperless-ngx/app/validator-deployment.yaml
sed -i '' 's/^      tag: "3\.4\.2"$/      tag: "3.5.0"/' "$HR"
sed -i '' 's#image: ghcr.io/paperless-ngx/paperless-ngx:3\.4\.2$#image: ghcr.io/paperless-ngx/paperless-ngx:3.5.0#' "$VAL"
/usr/bin/python3 - "$HR" <<'EOF'
import sys
p=sys.argv[1]; s=open(p).read()
anchor='      PAPERLESS_URL: "https://paperless.${SECRET_DOMAIN}"\n'
assert s.count(anchor)==1, "anchor not unique"
assert 'PAPERLESS_ALLOWED_HOSTS' not in s, "already present"
add=('      # 3.5.0 (#14735): when PAPERLESS_URL is set and PAPERLESS_ALLOWED_HOSTS is not,\n'
     '      # ALLOWED_HOSTS shrinks from ["*"] to [localhost, <PAPERLESS_URL host>], so\n'
     '      # in-cluster API consumers (openclaw, arag-web, health-check.sh) calling the\n'
     '      # Service name get HTTP 400 DisallowedHost. List every in-cluster name here.\n'
     '      PAPERLESS_ALLOWED_HOSTS: "paperless.${SECRET_DOMAIN},paperless-ngx,paperless-ngx.office,paperless-ngx.office.svc,paperless-ngx.office.svc.cluster.local"\n')
open(p,'w').write(s.replace(anchor, anchor+add))
EOF
git diff --stat -- "$HR" "$VAL"     # expect: 2 files, helmrelease +6/-1, validator +1/-1
```
Dry-run diff (scratch copy):
```
33c33   <       tag: "3.4.2"   >       tag: "3.5.0"
78a79,83  > (4 comment lines) + PAPERLESS_ALLOWED_HOSTS: "paperless.${SECRET_DOMAIN},paperless-ngx,paperless-ngx.office,paperless-ngx.office.svc,paperless-ngx.office.svc.cluster.local"
34c34   <           image: ghcr.io/paperless-ngx/paperless-ngx:3.4.2   >  ...:3.5.0
```
`helm template gabe565/paperless-ngx --version 0.24.1` with the edited values
renders `image: ghcr.io/paperless-ngx/paperless-ngx:3.5.0` and the env entry
`PAPERLESS_ALLOWED_HOSTS` (verified 2026-11-18). `${SECRET_DOMAIN}` is
substituted by Flux postBuild exactly as for `PAPERLESS_URL` on the line above.

Optional doc fix in the same commit (also clears doc finding F-da5de40c, which
reports the SOP still naming 3.4.1):
```bash
sed -i '' 's/app image `3\.4\.1`/app image `3.5.0`/' docs/sops/paperless.md
```

**3.3 Validate, commit, push (shared worktree rules)**
```bash
kubeconform -summary -ignore-missing-schemas kubernetes/apps/office/paperless-ngx/app/
cat > /tmp/plx-msg.txt <<'EOF'
feat(paperless): paperless-ngx 3.4.2 -> 3.5.0 (app + scan-inbox-validator)

Runs documents migrations 0028-0030 (treenode cache columns dropped, flat tag
tree, 0 notes/workflow triggers). Sets PAPERLESS_ALLOWED_HOSTS: 3.5.0 narrows
ALLOWED_HOSTS to the PAPERLESS_URL host when the var is unset, which would 400
openclaw/arag-web calling the Service name. Plan: paperless-ngx-fleet-3.5.0.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
git commit --only "$HR" "$VAL" -F /tmp/plx-msg.txt      # add docs/sops/paperless.md if 3.2's optional fix was made
git log -1 --format=%s     # must be the subject above -- amend before push if not
git show --stat HEAD       # only the 2 (or 3) files above
git push
```
No manual `flux reconcile` -- the webhook drives it (SOP application-update).
Note the commit SHA for §5.

**3.4 Watch the roll** (Recreate: old pod terminates, new pod pulls ~1 GB, init
waits for db/redis, s6 `init-migrations` runs `migrate`, then the webserver)
```bash
kubectl get pod -n office -l app.kubernetes.io/name=paperless-ngx -w   # Ctrl-C once 1/1 Running
kubectl logs -n office deploy/paperless-ngx -c paperless-ngx --since=10m | grep -i -E "apply|migrat|error|traceback" | head -40
```
Expected log lines include `Applying documents.0028_replace_tag_tree_fields... OK`,
`0029_...OK`, `0030_note_format... OK`. A `Traceback` before the webserver starts
-> go to §5 (decide R1/R2 by whether 0028 shows `OK`).

## 4. Verification

**4.1 Both workloads on the new digest** (not the old generation)
```bash
kubectl get pod -n office -l app.kubernetes.io/name=paperless-ngx -o jsonpath='{range .items[*]}{.status.containerStatuses[0].imageID}{"\n"}{end}'
kubectl get pod -n office -l app.kubernetes.io/name=scan-inbox-validator -o jsonpath='{range .items[*]}{.status.containerStatuses[0].imageID}{"\n"}{end}'
kubectl get pod -n office -l app.kubernetes.io/name=paperless-ngx -o jsonpath='{.items[0].status.containerStatuses[0].restartCount}{"\n"}'
```
PASS: both imageIDs end in `8c1e2c4e0abb50576c7a09f062ed581e2d955e298a302e1e196a35338639005e`
(today they end in `d704e84f...`, so this fails if the roll did not happen);
restartCount `0`.

**4.2 Migrations applied -- schema CONTENTS, not "pod Ready"**
```bash
kubectl exec -n office deploy/paperless-db -- sh -c 'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" -N paperless -e "
SELECT name FROM django_migrations WHERE app=\"documents\" ORDER BY id DESC LIMIT 1;
SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=\"paperless\" AND table_name=\"documents_tag\" AND column_name LIKE \"tn\\_%\";
SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=\"paperless\" AND table_name=\"documents_note\" AND column_name=\"format\";
SELECT table_collation, COUNT(*) FROM information_schema.tables WHERE table_schema=\"paperless\" GROUP BY 1;"' 2>/dev/null
kubectl exec -n office deploy/paperless-ngx -c paperless-ngx -- sh -c 'cd /usr/src/paperless/src && python3 manage.py showmigrations --plan' | grep -c '\[ \]'
```
PASS: `0030_note_format`; tn columns `1` (was 14 -- only `tn_parent` survives);
`format` column `1` (was 0); one collation row `utf8mb4_general_ci 75` (a stray
latin1/utf8mb3 table from a migration would show a second row -- SOP §6a.3);
unapplied migrations `0`. Each line differs from the §2.3 baseline, so a pod
that came up on the old schema fails here.

**4.3 Data intact -- CONTENTS ASSERTION**

CONTENTS ASSERTION: the library and its tag links survived 0028 -- measured by
the same counts as §2.3, with the tag-link count bound to the BASELINE's max
document id (so documents ingested after the upgrade cannot mask a loss),
compared line-by-line to `pre-3.5.0-baseline.txt`:
```bash
B=~/backups/paperless-db/pre-3.5.0-baseline.txt; P=~/backups/paperless-db/post-3.5.0.txt
MAXDOC=$(awk '$1=="maxdoc"{print $2}' "$B"); echo "MAXDOC=$MAXDOC"   # must be a number (1476 on 2026-11-18)
kubectl exec -n office deploy/paperless-db -- sh -c "mariadb -uroot -p\"\$MARIADB_ROOT_PASSWORD\" -N paperless -e '
SELECT \"tags\", COUNT(*) FROM documents_tag;
SELECT \"tagparents\", COUNT(*) FROM documents_tag WHERE tn_parent_id IS NOT NULL;
SELECT \"doctags_old\", COUNT(*) FROM documents_document_tags WHERE document_id <= $MAXDOC;
SELECT \"corr\", COUNT(*) FROM documents_correspondent;
SELECT \"dtypes\", COUNT(*) FROM documents_documenttype;
SELECT \"mailrules\", COUNT(*) FROM paperless_mail_mailrule;
SELECT \"tokens\", COUNT(*) FROM authtoken_token;
SELECT \"docs_old\", COUNT(*) FROM documents_document WHERE id <= $MAXDOC;'" 2>/dev/null | tee "$P"
grep -c . "$P"   # must print 8
diff <(grep -E '^(tags|tagparents|doctags_old|corr|dtypes|mailrules|tokens)[[:space:]]' "$B") \
     <(grep -E '^(tags|tagparents|doctags_old|corr|dtypes|mailrules|tokens)[[:space:]]' "$P") && echo CONTENTS-OK
awk '$1=="docs"{print "docs_baseline",$2}' "$B"; awk '$1=="docs_old"{print "docs_old_now",$2}' "$P"
```
PASS: `8`, `CONTENTS-OK`, and `docs_old_now` == `docs_baseline` (no pre-existing
document vanished; new ones may have been added). Baseline values 2026-11-18:
tags 51, tagparents 0, corr 189, dtypes 13, mailrules 1, tokens 2. A tag-link
loss from the column drop, or a lost API token (which reads to consumers as
"documents missing", SOP §6a.1), prints a diff line; an empty `$P` fails the
`grep -c` first, so a failed query cannot pass as "no diff". (Caveat: a
legitimate tag/correspondent edit by a user during the window also prints a
diff line -- inspect it before rolling back.)

**4.4 ALLOWED_HOSTS: consumers reach the API, enforcement is live (with negative control)**

Re-run the §2.4 script. PASS: the three Service-name hosts print `200`, AND
`bogus.invalid` prints `400`.
- Service-name host `400` = step 3.2's env var missing or wrong (the #14735
  break) -> fix forward (amend the var) or §5.
- `bogus.invalid` still `200` = the new settings code is NOT what is running
  (old image/generation) or ALLOWED_HOSTS is still `*` -- the check cannot be
  trusted either way; do not pass.
Code path cited: `_get_allowed_hosts()` + `_parse_paperless_url()` in
`src/paperless/settings/__init__.py` at v3.5.0 (quoted in 1.3).

**4.5 Real consumers (SOP §6a.1 token canary + arag-web)**
Re-run §2.5. PASS: openclaw prints a count `>= 1` (a 400/401 prints an error,
count `0`); arag-web prints `200`. Both go through
`paperless-ngx.office.svc.cluster.local:8000` -- this is the actual production
path 1.3 would have broken.

**4.6 Mail ingestion clean (SOP §6a.2)**
```bash
kubectl logs -n office deploy/paperless-ngx -c paperless-ngx --since=30m | grep -i -c -E "1366|OperationalError|mailbox.login|login failed|DisallowedHost|Unknown column"
```
PASS: `0`. Wait for at least one mail cycle (10 min) after Ready before reading
this. `DisallowedHost` / `Unknown column` are added here because they are the two
3.5.0-specific failure strings (1.3 / 1.2).

**4.7 End-to-end scan pipeline on the new image (validator + consume + OCR)**

Generates a 3 KB text PDF *inside the validator pod with the new image's pikepdf*
(dry-run 2026-11-18 in the 3.4.2 validator: 3090 bytes, re-opens valid; >
`MIN_SIZE_BYTES` 2048) and drops it in the inbox:
```bash
kubectl exec -n office deploy/scan-inbox-validator -- python3 -c '
import pikepdf
p=pikepdf.new(); p.add_blank_page(page_size=(595,842)); pg=p.pages[0]
font=p.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.Font,Subtype=pikepdf.Name.Type1,BaseFont=pikepdf.Name.Helvetica))
pg.Resources=pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=font))
pg.Contents=p.make_stream(b"".join(b"BT /F1 14 Tf 50 %d Td (PLAN VERIFY PAPERLESS 350 LINE %d) Tj ET\n" % (800-i*20,i) for i in range(38)))
p.save("/inbox/.plan-verify-350.tmp", compress_streams=False)
import os; os.rename("/inbox/.plan-verify-350.tmp","/inbox/plan-verify-350.pdf"); print("dropped")'
sleep 120   # validator: 2 stable polls x 15 s + 20 s mtime age; consumer polls 10 s; 1-page OCR ~30-60 s
kubectl logs -n office deploy/scan-inbox-validator --since=5m | grep -i "plan-verify-350"
kubectl exec -n office deploy/paperless-db -- sh -c 'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" -N paperless -e "SELECT COUNT(*), SUM(content LIKE \"%PLAN VERIFY%\") FROM documents_document WHERE title LIKE \"plan-verify-350%\" AND deleted_at IS NULL;"' 2>/dev/null
```
PASS: validator logs `moved -> consume: plan-verify-350.pdf` (a `FAILED (...)
-> _failed/` line means the new image's pikepdf rejected it); DB prints `1 1` --
one document whose OCR'd content contains the text (OCR_MODE=force rasterises and
re-OCRs, so this proves tesseract + ocrmypdf work on 3.5.0, not just that a row
exists). `0 NULL` after 3 min = consume broken. Clean-up (to trash, restorable):
```bash
kubectl exec -n office deploy/paperless-ngx -c paperless-ngx -- sh -c 'cd /usr/src/paperless/src && python3 manage.py shell -c "from documents.models import Document; print(Document.objects.filter(title__startswith=\"plan-verify-350\").delete())"'
```
Also SOP §6.7: validator heartbeat advances (two reads ~20 s apart differ).

**4.8 Instruments**

CONTROL: alertname ContainerOOMKilled -- must NOT be firing for `office/paperless-ngx` for 30 min after Ready (4.7's OCR run is the load that would trip it; rule in `kubernetes/apps/monitoring/kube-prometheus-stack/app/container-memory-alerts.yaml`).
CONTROL: metric kube_deployment_status_replicas_available -- `{namespace="office",deployment=~"paperless-ngx|scan-inbox-validator"}` must read 1 for both, sampled after 4.7; an empty result is a FAIL (the instrument is down, not the app healthy).
```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 >/dev/null 2>&1 & PF=$!; sleep 2
curl -s 'http://localhost:9090/api/v1/query' --data-urlencode 'query=kube_deployment_status_replicas_available{namespace="office",deployment=~"paperless-ngx|scan-inbox-validator"}' | /usr/bin/python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];print(len(r),[x['value'][1] for x in r])"
curl -s http://localhost:9090/api/v1/alerts | /usr/bin/python3 -c "import sys,json;a=[x for x in json.load(sys.stdin)['data']['alerts'] if x['labels'].get('alertname')=='ContainerOOMKilled' and x['labels'].get('namespace')=='office'];print('OOM-firing',len(a))"
kill $PF 2>/dev/null
```
PASS: `2 ['1', '1']` and `OOM-firing 0`.

## 5. Rollback

**Decide first, by what the §3.4 logs / §4.2 show:**
- 0028 NOT applied (head still `0027`, tn columns 14): pure manifest problem ->
  `git revert <sha> && git push`; confirm with §4.1 (imageIDs back to `d704e84f...`)
  and §4.5. Done.
- Fix-forward first if only 4.4/4.5 fail (Host header): correct the
  `PAPERLESS_ALLOWED_HOSTS` value and push; the schema is fine.
- 0028 applied and the app must go back: **R1** (keeps everything ingested since
  the upgrade). If R1 errors at any step: **R2**.

**R1 -- reverse migrations with the 3.5.0 code, then revert the image (~15 min)**
The 3.5.0 image is the only one that knows how to un-apply 0028-0030.
```bash
# 1. while 3.5.0 is still running:
kubectl exec -n office deploy/paperless-ngx -c paperless-ngx -- sh -c 'cd /usr/src/paperless/src && python3 manage.py migrate documents 0027_documentbarcode'
#    expect "Unapplying documents.0030_note_format... OK", 0029 OK, 0028 OK
# 2. confirm schema is back to the 3.4.2 shape (tn columns 14, head 0027):
#    re-run the §4.2 query: expect 0027_documentbarcode / 14 / 0
# 3. revert the commit (image + env var together; 3.4.2 ignores the env var anyway):
git revert --no-edit <sha-from-3.3> && git log -1 --format=%s && git push
# 4. once the 3.4.2 pod is Ready, rebuild the treenode caches (the 13 columns came
#    back at their defaults; with 0 parents this only fixes sibling order/counts):
kubectl exec -n office deploy/paperless-ngx -c paperless-ngx -- sh -c 'cd /usr/src/paperless/src && python3 manage.py shell -c "from documents.models import Tag; Tag.update_tree(); print(Tag.objects.filter(tn_level=1).count(), Tag.objects.count())"'
#    expect "51 51" (measured on 3.4.2 today: 51 51)
```
Between step 1 and the 3.4.2 pod coming up (~3 min) the 3.5.0 code runs against
the 0027 schema: creating a NEW tag would fail (the re-added NOT NULL columns
have no DB default). Do not edit tags in that gap; ingestion of documents is
unaffected.

**R2 -- restore the in-window dump (~25 min; loses DB rows written after §3.1)**
```bash
DUMP=$(cat ~/backups/paperless-db/LATEST-pre-3.5.0); ls -l "$DUMP"
# 1. record what will be lost (documents ingested after the dump; their ORIGINAL
#    files stay on the CIFS media share and can be re-consumed afterwards):
MAXDOC=$(awk '$1=="maxdoc"{print $2}' ~/backups/paperless-db/pre-3.5.0-baseline.txt)
kubectl exec -n office deploy/paperless-db -- sh -c "mariadb -uroot -p\"\$MARIADB_ROOT_PASSWORD\" -N paperless -e 'SELECT id, original_filename FROM documents_document WHERE id > $MAXDOC'" 2>/dev/null | tee ~/backups/paperless-db/post-dump-docs.txt
# 2. stop the app writing (Flux would scale it back, so suspend first):
flux suspend kustomization paperless-ngx -n office
flux suspend helmrelease paperless-ngx -n office
kubectl scale deploy paperless-ngx scan-inbox-validator -n office --replicas=0
# 3. restore (the dump carries DROP DATABASE IF EXISTS / CREATE DATABASE / USE):
kubectl exec -i -n office deploy/paperless-db -- sh -c 'mariadb --default-character-set=utf8mb4 -uroot -p"$MARIADB_ROOT_PASSWORD"' < "$DUMP"
# 4. verify against the baseline BEFORE starting the app: re-run §2.3 -> head
#    0027_documentbarcode, tncols 14, and every other line identical to
#    pre-3.5.0-baseline.txt (diff must be silent).
# 5. revert the manifest and resume Flux (resume re-applies replicas: 1):
git revert --no-edit <sha-from-3.3> && git log -1 --format=%s && git push
flux resume kustomization paperless-ngx -n office
flux resume helmrelease paperless-ngx -n office
```
R2 is the same restore shape the db-dumps restore proof exercised for
paperless (`docs/sops/backup.md`, "Database Dumps": import rc 0, counts
identical). If the in-window dump is unusable, the nightly
`db-dump-paperless-db` output on the NAS (`db-dumps/paperless-db/`) is the next
source (loses up to a day), then the Longhorn backup of `paperless-db-data`
(whole-volume restore per `docs/sops/longhorn.md`).

**Confirm the cluster is back (either path):** §4.1 imageIDs end `d704e84f...`;
§4.2 shows `0027_documentbarcode` / 14 tn columns; §2.4 all four `200`; §2.5
both canaries green; §4.6 `0`. After R2, re-consume the files listed in
`post-dump-docs.txt` (paperless-agent).

## 6. Interference notes

- **Downtime:** Recreate -> paperless UI/API down ~2-4 min (image pull + ~96 s
  start). Scans landing meanwhile wait in the inbox/consume share (nothing is
  lost); mail is picked up next cycle. openclaw/arag-web calls fail during the
  gap -- do not run this while the openclaw morning briefing or an arag-web sync
  is due.
- **Not restarted:** paperless-db, paperless-redis, openclaw, arag-web. The DB
  takes only the app's own DDL (13 DROP COLUMN on a 51-row table, 1 ADD COLUMN on
  an empty table: sub-second).
- **conflicts_with:** `redis-fleet-8.10.3` rolls paperless-redis and checks this
  app; `flux-oci-chart-sources` stage 3 edits the same helmrelease.yaml (merge
  conflict / mixed roll); `kube-prometheus-stack-93.3.0` would pull the
  instrument §4.8 reads; the three office `backup-restore` plans are the
  rollback-capacity rule.
- **Memory:** unchanged (8Gi limit, THREADS_PER_WORKER=2). 4.7 is a one-page
  OCR -- well under the measured 1.8-2.8 GiB per-doc peak.
- **Repo correction (report, not done here):** `docs/sops/paperless.md` should
  record that `PAPERLESS_ALLOWED_HOSTS` is now load-bearing (any new in-cluster
  consumer by Service name must be added to it), and §11 "Rollback Plan" says
  `git revert` is the manifest rollback -- false for any image bump that carries
  migrations (this one included).
