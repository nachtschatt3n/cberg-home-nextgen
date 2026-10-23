---
plan_id: ninth-banner-feedback-db-init-v1-0.8.7
component: ninth-banner-feedback-db-init-v1   # one-shot bootstrap Job, ns databases; uses the image ONLY as a psql client
pr: 383                               # CURRENT Renovate PR "fix(container): update pgvector/pgvector ( 0.8.6 → 0.8.7 )", opened
                                      # 2026-10-18T01:05Z, touches only init-job.yaml, CI green, OPEN and HELD by the policy deny rule
                                      # `*ninth-banner-feedback-db*` (added 2026-10-17, `paths:`-scoped; re-verified 2026-10-23 with
                                      # auto-update.py dry-run: "HELD ... [path rule ...]"). DO NOT MERGE IT: it bumps the image
                                      # WITHOUT renaming the Job, the change that has now failed FOUR times (#238, #316, #340, #362 -
                                      # each merged, each reverted; §1.2). This plan lands a direct commit with the rename instead,
                                      # then closes #383 (§3.6). Earlier drafts named #340 (merged 2026-10-14T01:32Z, reverted
                                      # 6e69fb82) and relied on it being OPEN; that premise was false by 2026-10-23.
kind: image
current: "pgvector/pgvector:0.8.6-pg16@sha256:ccc6e83d6e35e931dc7c5def2022729d5a6c370318d099181995567ff1fb4d6b on job/ninth-banner-feedback-db-init-v1"
target: "pgvector/pgvector:0.8.7-pg16@sha256:7b822b0aac60967beb1ea5e576b8602c94c300a157d187f385ae3e0da199b90a on job/ninth-banner-feedback-db-init-v1a (renamed: Job .spec.template is immutable)"
update_type: patch
risk: low                             # client-only image on a Job that already re-runs every 7 days (TTL GC + Flux recreate,
                                      # last re-run 2026-10-12T14:01Z, Succeeded). The 0.8.7 client against this exact server is
                                      # already proven by oc8-db-init-v1a + sweep-history-init-v9a (Succeeded 2026-10-12, §1.3).
                                      # The ONLY failure mode that ever hit this component is the missing rename (§1.2).
est_duration_min: 20                  # pre-checks + baselines 6 · edit/lint/commit/push 3 · Flux prune+create+Job run ~3
                                      # (ks interval 30m, so allow one manual reconcile, §3.4) · verification 5 · slack 3
needs_reboot: false
touches:
  namespaces: [databases]
  resources:                          # every object verified to EXIST live 2026-10-13 (kubectl get), except the v1a Job this creates
    - job/ninth-banner-feedback-db-init-v1      # pruned by Flux (its completed pod goes with it)
    - job/ninth-banner-feedback-db-init-v1a     # created by Flux; re-runs the idempotent bootstrap (§1.4)
    - kustomization/ninth-banner-feedback-db    # ns databases, prune: true, wait: false, dependsOn databases/postgresql
    - configmap/ninth-banner-feedback-db-bootstrap   # read-only (mounted script), NOT edited
    - secret/ninth-banner-feedback-db           # read-only (env), NOT edited
    - secret/postgresql                         # read-only (admin creds as env), NOT edited
    - role/ninth_banner_feedback@postgresql     # bootstrap re-asserts ALTER ROLE ... PASSWORD (same SOPS value)
    - database/ninth_banner_feedback@postgresql # bootstrap re-asserts OWNER + REVOKE/GRANT CONNECT,TEMPORARY
    - deployment/the-ninth-banner               # my-software-production; the consumer, NOT touched — §4 reads its feedback_store_up
  shared: [postgresql, monitoring]    # postgresql = the shared databases/postgresql instance (same token nocodb-2026.09.1 and
                                      # pgvector-fleet used): this plan runs admin DDL against it but does NOT restart it.
                                      # monitoring = §4 reads Prometheus (feedback_store_up, kube_job_status_succeeded, ALERTS).
depends_on: []                        # pgvector-fleet-0.8.7 is already EXECUTED (retired 41aa7b83); its end state is asserted by
                                      # premise shared-postgresql-on-0.8.7 instead of a dead ref.
conflicts_with:
  - flux-distribution-2.9.6           # same: Flux controllers replaced under the reconcile this plan relies on.
  - flux-reconciler-impersonation     # changes WHO applies the databases Kustomizations (incl. ninth-banner-feedback-db);
                                      # a prune failing on RBAC would be indistinguishable from this plan failing.
exclusive: false
security_ref: F-d6d47945              # accepted register row on the 0.8.6-pg16 tag whose remedy is "newer upstream tag, bump the
                                      # image". This Job's completed pod is the LAST object in the cluster still carrying the
                                      # 0.8.6-pg16 digest (measured 2026-10-13, §1.1). Detail stays on the record. Whether the
                                      # row clears is for the next sweep to MEASURE, not for this plan to claim.
capability_change: false              # same bootstrap script, byte-identical; only the psql client binary changes. No new role,
                                      # grant, route, permission or exposure.
rollback_class: git-revert            # nothing forward-only: client-only image, the bootstrap is idempotent (guarded CREATE,
                                      # ALTER/GRANT/REVOKE re-asserts) and contains no extension DDL, no DROP/TRUNCATE/DELETE/
                                      # INSERT. A revert renames back to v1 and re-runs the same script on 0.8.6. A logical dump of
                                      # ninth_banner_feedback is still taken first (§2.6) as a cheap belt-and-braces.
finding_refs: [F-8d31fbb2]            # version finding "ninth-banner-feedback-db-init-v1: image pgvector/pgvector 0.8.6-pg16 →
                                      # 0.8.7-pg16 (patch)" (queried 2026-10-13 with `finding list --grep ninth-banner`).
                                      # NOT claimed: F-793d72d5 (auto-update should route kind:Job image bumps to the PLAN lane),
                                      # which this plan does not fix — see §6 repo corrections.
review: ready-for-go@2026-10-23      # delta plan-reviewer 2026-10-23: ready-for-go
status: vetted
window: "nightly:2026-10-30"   # stamped 2026-10-23 on delta review
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/immutable-job-image-bumps.md     # §4 rename convention + §4a live-DB checklist (done in §1.4)
  - docs/sops/backup.md
  - docs/sops/storage-safety.md                # read-only relevance: no PVC/PV/Volume is touched, let alone deleted
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/vulnerability-disclosure.md
generated: "2026-10-13"
refreshed: "2026-10-23"             # PR/hold-rule state re-measured; dead conflicts_with refs dropped (no kube-prometheus-stack
                                      # plan is open - if one is filed, re-add it: §4 reads Prometheus)
premises:
  # Read-verb only. Each was run 2026-10-13 ~02:00Z and returned exactly the expected value.
  - id: job-v1-current
    why: >-
      `current:` claims the live Job is v1 on the 0.8.6 digest and Succeeded. If someone already renamed/bumped it, this plan is
      a no-op and its sed matches nothing. NOTE: the Job is TTL-deleted 7d after completion (next ~2026-10-19T14:01Z) and Flux
      recreates it within its 30m interval; a NotFound inside that gap is benign — re-run the premise after the next reconcile.
    run: kubectl get job -n databases ninth-banner-feedback-db-init-v1 -o jsonpath='{.spec.template.spec.containers[0].image} {.status.succeeded}'
    expect_exact: pgvector/pgvector:0.8.6-pg16@sha256:ccc6e83d6e35e931dc7c5def2022729d5a6c370318d099181995567ff1fb4d6b 1
  - id: repo-pin-once
    why: >-
      §3.2's sed assumes exactly one name line ending in `-init-v1` and one 0.8.6 image line in the file (run from repo root).
      If a Renovate PR (#383 or a successor) was merged in the meantime and NOT reverted the image line is already 0.8.7 WITHOUT a
      rename - the broken state of §1.2: stop and follow §5.C instead. (#340 and #362 were merged and reverted; the live
      repo file read 0.8.6 / `-init-v1` on 2026-10-23, so the count 2 holds today.)
    run: "grep -c -e '^  name: ninth-banner-feedback-db-init-v1$' -e 'image: pgvector/pgvector:0.8.6-pg16@sha256:ccc6e83d6e35e931dc7c5def2022729d5a6c370318d099181995567ff1fb4d6b$' kubernetes/apps/databases/ninth-banner-feedback-db/app/init-job.yaml"
    expect_exact: "2"
  - id: shared-postgresql-on-0.8.7
    why: >-
      This plan follows pgvector-fleet-0.8.7 (executed 2026-10-12). The rationale "same client as the server" and the
      precedent in §1.3 both rest on the shared instance already running the 0.8.7 digest with 1 ready replica.
    run: kubectl get deploy -n databases postgresql -o jsonpath='{.spec.template.spec.containers[0].image} {.status.readyReplicas}'
    expect_exact: pgvector/pgvector:0.8.7-pg16@sha256:7b822b0aac60967beb1ea5e576b8602c94c300a157d187f385ae3e0da199b90a 1
  - id: sibling-init-jobs-green-on-0.8.7
    why: >-
      The two sibling bootstrap Jobs renamed by the fleet (v1a, v9a) ran the 0.8.7 psql client against this server and
      Succeeded. That is the evidence the client works here; if either is failing now, the client is not proven.
    run: kubectl get job -n databases oc8-db-init-v1a sweep-history-init-v9a -o jsonpath='{.items[*].status.succeeded}'
    expect_exact: 1 1
  - id: ks-prune-and-ready
    why: >-
      The rename only works if Flux prunes v1. prune must be true and the Kustomization Ready (a NotReady ks would swallow the
      commit; it reads DependencyNotReady for a few seconds whenever postgresql reconciles — re-run once before failing).
    run: kubectl get ks -n databases ninth-banner-feedback-db -o jsonpath='{.spec.prune} {.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: true True
  - id: bootstrap-has-no-destructive-sql
    why: >-
      §1.4 read the script end-to-end and found it idempotent. The only lines matching these words are the two-line header
      comment "No DROP, / TRUNCATE, DELETE or INSERT". A count above 2 means someone added destructive SQL since — STOP,
      re-do SOP §4a. (Below 2 means the comment was rewritten: re-read the script before going on.)
    run: "grep -c -i -e 'drop' -e 'truncate' -e 'delete' -e 'insert' kubernetes/apps/databases/ninth-banner-feedback-db/app/bootstrap-configmap.yaml"
    expect_exact: "2"
---

# ninth-banner-feedback-db-init-v1: pgvector 0.8.6-pg16 -> 0.8.7-pg16 (rename to v1a)

## 1. Summary & why held

**What changes:** one image digest on one one-shot Job, `databases/ninth-banner-feedback-db-init-v1`. The Job uses the
pgvector image **only as a `psql` client**. It provisions the login role and the empty database `ninth_banner_feedback`
on the shared `databases/postgresql` for The Ninth Banner's player-feedback store. A Job's `.spec.template` is immutable,
so the bump **must** rename the Job (`v1` -> `v1a`, `docs/sops/immutable-job-image-bumps.md` §3 rule 1). Flux then prunes
`v1` and creates `v1a`, which re-runs the bootstrap once against live data.

**Why it was held:** coverage gate G3 could not read the release notes ("unavailable"). Earned autonomy shows
**0 green / 4 reverts in 90d** (the 2 of 10-08/10-12 plus #340 and #362). Both facts are explained below, and neither is a property of pgvector 0.8.7.

### 1.1 Why this Job was not in `pgvector-fleet-0.8.7`

- The fleet plan was authored on **2026-10-03** with a five-pin inventory: 3 servers plus 2 client-only Jobs
  (`oc8-db-init-v1`, `sweep-history-init-v9`).
- This component did not exist then. It was added on **2026-10-05 15:52** (`37b1f449`), after the fleet's pin list was
  frozen. The fleet's 2026-10-05 re-review checked the plan's own five pins and never re-enumerated the repo.
- The fleet executed green on 2026-10-12 (`0652cdfb`, `cc38bcad`, `33d660c1`, `90fd9037`) and was retired in `41aa7b83`,
  leaving this sixth pin behind.
- `rg 'pgvector:0.8.6' kubernetes/` now finds exactly one image line: this Job's. Live, the Job's completed pod
  `ninth-banner-feedback-db-init-v1-*` is the **only** pod in the cluster still carrying the 0.8.6-pg16 digest (measured
  2026-10-13 over all pods/containers).

**Can it simply follow the fleet?** Yes. It is the same image line (pg16), the same digest, and the same shape as fleet
leg D (`90fd9037` renamed oc8-db `v1->v1a` and sweep-history `v9->v9a` with a History line). This plan is that leg,
applied to the pin the fleet missed.

### 1.2 What the 2 reverts in 90d actually were — the gotcha this plan exists for

All four reverts were this one Renovate change auto-merged at Step 0 of a nightly window:
- **#238**: merged 2026-10-08T01:35Z, reverted `1891b318`.
- **#316**: merged 2026-10-12T01:36Z, reverted `2bf4d320`.
- **#340**: merged 2026-10-14T01:32Z (`d8adbd5a`), reverted `6e69fb82` - a one-file PR, so it failed alone.
- **#362**: merged 2026-10-17T01:34Z (`cc6dc1c4`), reverted `cab1eb44` - scored a safe patch, failed the post-apply
  health gate, and took the whole 7-PR batch with it.

State after the last revert (measured 2026-10-23): repo `init-job.yaml` = `-init-v1` on the 0.8.6 digest; live Job
`v1` = 0.8.6, `succeeded=1`; `ks/ninth-banner-feedback-db` Ready on main. Nothing is broken now - the hold keeps it so.

**The hold rule that exists (added 2026-10-17 after #362, `runbooks/auto-update-policy.yaml`, deny
`*ninth-banner-feedback-db*` with `paths: [.../init-job.yaml]`).** It is path-scoped because Renovate keys the PR on the
shared depName `pgvector/pgvector`. Re-verified 2026-10-23: `runbooks/auto-update.py` (dry run) prints #383 as HELD with
`[path rule '*ninth-banner-feedback-db*': PR changes ...init-job.yaml]`. Consequences for this plan: (a) the Step-0
safe-update apply set excludes #383 on its own - the window agent need not hand-filter it; (b) the rule's reason text says
"twice before"/"7-PR batch" - stale count, harmless; (c) **do NOT remove the rule when this plan executes**: its removal
condition is "Job renamed per bump automatically or carries the force annotation", and this plan renames by hand once.
The next pgvector patch will open another Renovate PR that the rule must hold again.

Each PR changed the image in six files, including **three Job manifests, none of them renamed**. Flux's server-side
dry-run rejects a changed Job template as immutable, so the Kustomization fails. The window's health gate then reverted
the **whole batch**. Sweep finding `F-793d72d5` records this: *"immutable init-Job template failed dry-run, whole 11-PR
batch auto-reverted (nightly 2026-10-08)"*.

The live Flux inventory confirms it. `kustomization/ninth-banner-feedback-db` `.status.history` holds the bumped-manifest
digest `sha256:13faaa47…` with `lastReconciledStatus: ReconciliationFailed` and 28 attempts, first at
2026-10-08T01:36:59Z and last at 2026-10-12T01:50:07Z. Those times line up with the two merge→revert intervals.

**The open PR #383 is the same broken change.** It is a one-file version of #316: the image is bumped and
`metadata.name` stays `-init-v1`, CI is green, and it is mergeable. Merging it reproduces the failure a fifth time. The
Render Gate cannot catch it, because a static render has no live object to compare against. **Never merge #383. This
plan replaces it.**

### 1.3 Upstream evidence and same-server proof

- Upstream `CHANGELOG.md` for v0.8.7 (2026-10-01) lists only bug fixes: an IVFFlat build buffer overflow, and `avg` with
  no matching rows. This plan relies on the fleet's primary-source reading of 2026-10-03 for that, and re-measured
  nothing upstream.
- None of this matters to this component. The bootstrap issues **no extension DDL** (no `CREATE EXTENSION` and no
  `vector` objects; read in full in §1.4). The only thing that changes is the `psql` binary inside the image.
- The 0.8.7-pg16 image carries the same PostgreSQL 16.15 Debian build as the server it talks to. That server is the
  shared instance, which has run this exact digest since `33d660c1`.
- The client is already proven against this server. `oc8-db-init-v1a` and `sweep-history-init-v9a` run on the same
  digest and both have `succeeded=1`, completed 2026-10-12T11:26Z (premise `sibling-init-jobs-green-on-0.8.7`).
- Target digest re-checked on Docker Hub on 2026-10-13: `0.8.7-pg16` -> `sha256:7b822b0a…199b90a`,
  `last_updated 2026-10-01T17:34Z`. It has not been re-pushed since the fleet pinned it.

### 1.4 SOP §4a live-DB checklist (done at authoring, re-asserted by premise)

`configmap/ninth-banner-feedback-db-bootstrap` `bootstrap.sh` was read end-to-end on 2026-10-13. Every statement is
idempotent:
- guarded `CREATE ROLE ninth_banner_feedback LOGIN` (`pg_roles` probe), then
  `ALTER ROLE … NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD '<SOPS value>'`
- guarded `CREATE DATABASE ninth_banner_feedback OWNER …` (`pg_database` probe), then `ALTER DATABASE … OWNER TO …`
- `REVOKE CONNECT, TEMPORARY … FROM PUBLIC` and `GRANT CONNECT, TEMPORARY … TO ninth_banner_feedback`

There is no DROP, TRUNCATE, DELETE, INSERT, or table DDL. The app creates its own tables. The script runs with
`ON_ERROR_STOP=1` and `set -euo pipefail`, so any SQL error fails the Job instead of passing silently.

**Strongest evidence that the re-run is safe: it already happens weekly.** `ttlSecondsAfterFinished: 604800` deletes the
completed Job after 7 days, and Flux recreates it from the manifest on its next 30m reconcile. The current `v1` object was
re-created and re-ran the bootstrap at **2026-10-12T14:01:36Z** (Succeeded; log shows all three `==>` markers and 0
error lines). `feedback_store_up` stayed 1 throughout (§4).

**The one real hazard is the password re-assert.** `ALTER ROLE … PASSWORD` sets the role password to
`secret/ninth-banner-feedback-db`. If that ever diverged from the password inside `FEEDBACK_DATABASE_URL` in
`my-software-production/the-ninth-banner-feedback`, the re-run would lock the app out. On 2026-10-13 they matched
(`PW_MATCH`, compared in-process without printing). §2.4 re-checks this before the commit.

## 2. Pre-checks

Run on the Mac mini from the repo root (zsh). Everything here is read-only.

```bash
cd /Users/mu/code/cberg-home-nextgen
W=/tmp/nbf-087; mkdir -p "$W"

# 2.1 Premises — all six must PASS (re-run ks-prune-and-ready once if it reads DependencyNotReady)
.venv/bin/python3 runbooks/plan-premises.py ninth-banner-feedback-db-init-v1-0.8.7

# 2.2 The Renovate PR is still open and still the broken one-file change (it must NOT have been merged), and the hold
#     rule still holds it. Take the PR number from `gh pr list --search pgvector` if #383 was replaced.
gh pr view 383 --json state,files -q '.state+" "+([.files[].path]|join(","))'
# PASS: OPEN kubernetes/apps/databases/ninth-banner-feedback-db/app/init-job.yaml
# MERGED -> if the repo file now reads 0.8.7 on `-init-v1` the cluster is in the §1.2 broken state: go to §5.C, do not run §3.
#           (MERGED with the file back on 0.8.6 means it was reverted, as #340/#362 were: re-open the plan at §2.1.)
.venv/bin/python3 runbooks/auto-update.py 2>&1 | grep -c -E '#383 .*HELD .*path rule .{1,3}ninth-banner-feedback-db'
# PASS: 1  (the deny rule is live; 0 = the rule was removed or the PR was renumbered: Step 0 could merge it - stop and look)

# 2.3 Target digest unchanged upstream
curl -s "https://hub.docker.com/v2/repositories/pgvector/pgvector/tags/0.8.7-pg16" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['digest'])"
# PASS: sha256:7b822b0aac60967beb1ea5e576b8602c94c300a157d187f385ae3e0da199b90a
# FAIL (other digest): upstream re-pushed the tag; stop — do not silently re-pin.

# 2.4 Password-consistency gate (prints only MATCH/MISMATCH, never the value)
python3 - <<'EOF'
import json,subprocess,base64,urllib.parse
def sec(ns,n,k):
    d=json.loads(subprocess.check_output(["kubectl","get","secret","-n",ns,n,"-o","json"]))["data"][k]
    return base64.b64decode(d).decode()
a=sec("databases","ninth-banner-feedback-db","NINTH_BANNER_FEEDBACK_PASSWORD")
u=urllib.parse.urlparse(sec("my-software-production","the-ninth-banner-feedback","FEEDBACK_DATABASE_URL"))
print("PW_MATCH" if a and a==urllib.parse.unquote(u.password or "") else "PW_MISMATCH",
      "user="+str(u.username), "db="+u.path.lstrip("/"))
EOF
# PASS: PW_MATCH user=ninth_banner_feedback db=ninth_banner_feedback   (measured 2026-10-13)
# PW_MISMATCH -> STOP. The re-run would set the role to the databases-side password and lock the app out.
#                That is an operator secret decision, not window work.

# 2.5 Baseline snapshot of role/db attributes + per-table exact counts (admin, in-pod, read-only)
cat > "$W/state.sql" <<'EOF'
\pset tuples_only on
\pset format unaligned
SELECT 'role:'||rolname||' login='||rolcanlogin||' super='||rolsuper||' createdb='||rolcreatedb||' createrole='||rolcreaterole FROM pg_roles WHERE rolname='ninth_banner_feedback';
SELECT 'db:'||datname||' owner='||pg_get_userbyid(datdba)||' acl='||coalesce(datacl::text,'NULL') FROM pg_database WHERE datname='ninth_banner_feedback';
\c ninth_banner_feedback
SELECT 'tbl:'||table_schema||'.'||table_name||'='||(xpath('/row/c/text()', query_to_xml(format('select count(*) as c from %I.%I', table_schema, table_name), false, true, '')))[1]::text
  FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog','information_schema') AND table_type='BASE TABLE' ORDER BY 1;
EOF
kubectl exec -i -n databases deploy/postgresql -- sh -c 'psql -X -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres -f -' \
  < "$W/state.sql" | grep -E '^(role|db|tbl):' > "$W/before.txt"; cat "$W/before.txt"
# PASS: one role: line, one db: line, >=1 tbl: line. Measured 2026-10-13:
#   role:ninth_banner_feedback login=true super=false createdb=false createrole=false
#   db:ninth_banner_feedback owner=ninth_banner_feedback acl={ninth_banner_feedback=CTc/ninth_banner_feedback}
#   6 tbl: lines (public.analytics_error/player/session/view, feedback_attachment, feedback_report)
test "$(grep -c '^tbl:' "$W/before.txt")" -ge 1 || echo "BASELINE_EMPTY — stop"

# 2.6 Belt-and-braces logical dump of the feedback DB (~4 MB), validated locally (Homebrew pg_restore 16)
#     Do NOT validate with in-pod `pg_restore -l` fed on stdin: it hangs (measured 2026-10-13).
kubectl exec -n databases deploy/postgresql -- sh -c 'pg_dump -U "$POSTGRES_USER" -Fc ninth_banner_feedback' > "$W/nbf.dump"
echo "dump_tables=$(/opt/homebrew/bin/pg_restore -l "$W/nbf.dump" | grep -c 'TABLE DATA') live_tables=$(grep -c '^tbl:' "$W/before.txt")"
# PASS: dump_tables == live_tables (6 == 6 on 2026-10-13). Mismatch or 0 -> stop.

# 2.7 Consumer healthy right now (the CONTROL baseline for §4.E)
kubectl get deploy -n my-software-production the-ninth-banner -o jsonpath='{.status.readyReplicas}/{.spec.replicas}{"\n"}'
# PASS: 1/1
```

## 3. Steps (GitOps)

```bash
cd /Users/mu/code/cberg-home-nextgen
F=kubernetes/apps/databases/ninth-banner-feedback-db/app/init-job.yaml

# 3.1 Clean start for this file (shared worktree)
git status --porcelain "$F"     # PASS: prints nothing

# 3.2 Rename + re-pin + History line (BSD sed; dry-tested on a scratch copy 2026-10-13)
sed -i '' \
 -e 's|^  name: ninth-banner-feedback-db-init-v1$|  name: ninth-banner-feedback-db-init-v1a|' \
 -e 's|pgvector/pgvector:0\.8\.6-pg16@sha256:ccc6e83d6e35e931dc7c5def2022729d5a6c370318d099181995567ff1fb4d6b|pgvector/pgvector:0.8.7-pg16@sha256:7b822b0aac60967beb1ea5e576b8602c94c300a157d187f385ae3e0da199b90a|' \
 -e 's|^#   v1 -- role + database for The Ninth Banner feedback store\.$|&\
#   v1a -- image pgvector 0.8.6-pg16 -> 0.8.7-pg16 (digest re-pinned); no script change.\
#          Rename forces prune+recreate (Job spec immutable); bootstrap is idempotent.|' "$F"
git diff --stat "$F"            # PASS: 1 file changed, 4 insertions(+), 2 deletions(-)
git diff "$F"
```

Expected diff (from the scratch-copy dry run):

```
+#   v1a -- image pgvector 0.8.6-pg16 -> 0.8.7-pg16 (digest re-pinned); no script change.
+#          Rename forces prune+recreate (Job spec immutable); bootstrap is idempotent.
-  name: ninth-banner-feedback-db-init-v1
+  name: ninth-banner-feedback-db-init-v1a
-          image: pgvector/pgvector:0.8.6-pg16@sha256:ccc6e83d6e35e931dc7c5def2022729d5a6c370318d099181995567ff1fb4d6b
+          image: pgvector/pgvector:0.8.7-pg16@sha256:7b822b0aac60967beb1ea5e576b8602c94c300a157d187f385ae3e0da199b90a
```

```bash
# 3.3 Gate the commit on the edit (both checks must print the expected value)
grep -c '^  name: ninth-banner-feedback-db-init-v1a$' "$F"                                  # PASS: 1
grep -c 'image: pgvector/pgvector:0.8.7-pg16@sha256:7b822b0aac60967beb1ea5e576b8602c94c300a157d187f385ae3e0da199b90a$' "$F"  # PASS: 1
kubeconform -summary -exit-on-error -ignore-missing-schemas kubernetes/apps/databases/ninth-banner-feedback-db/app
# Also fix the stale Job name in the inventory doc, in the SAME commit:
sed -i '' 's|(`ninth-banner-feedback-db-init-v1`, no DROP|(`ninth-banner-feedback-db-init-v1a`, no DROP|' docs/applications.md
git diff --stat docs/applications.md   # PASS: 1 file changed, 1 insertion(+), 1 deletion(-)

# 3.4 Commit ONLY these two paths, verify, push (write the message file first)
cat > "$W/msg.txt" <<'EOF'
fix(ninth-banner-feedback-db): init Job to pgvector 0.8.7-pg16 (v1 -> v1a)

Client-only image bump; Job spec is immutable so the rename forces
prune+recreate. Bootstrap re-read end-to-end, idempotent (immutable-job-image-bumps
SOP 4a). The pin pgvector-fleet-0.8.7 missed (component added after the fleet
inventory). Supersedes Renovate #383, which bumps without the rename.
Plan ninth-banner-feedback-db-init-v1-0.8.7.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
git commit --only "$F" docs/applications.md -F "$W/msg.txt"
git log -1 --format=%s     # PASS: subject is exactly the first line above — amend before push if not (message-swap race)
git show --stat HEAD       # PASS: exactly the two paths
git push

# 3.5 Let Flux pick it up. The ks interval is 30m, so after 3 min without v1a, reconcile it once.
#     Note: the Kustomization lives in ns databases, NOT flux-system (the SOP's example names the wrong namespace — §6).
kubectl get job -n databases ninth-banner-feedback-db-init-v1a 2>/dev/null \
  || flux reconcile kustomization ninth-banner-feedback-db -n databases --with-source

# 3.6 Close the broken Renovate PR (Renovate would auto-close once main has 0.8.7, but do not leave it mergeable overnight)
gh pr close 383 --comment "Superseded by the v1 -> v1a rename commit (plan ninth-banner-feedback-db-init-v1-0.8.7). This PR bumps a Job image without renaming the Job, which fails Flux dry-run (immutable template); see F-793d72d5."
```

## 4. Verification

Run within 10 minutes of the push. Every gate states what its failure prints.

```bash
cd /Users/mu/code/cberg-home-nextgen; W=/tmp/nbf-087

# 4.A Flux applied the rename: v1 pruned, v1a present, ks Ready on the pushed revision
for i in $(seq 1 30); do
  S=$(kubectl get job -n databases ninth-banner-feedback-db-init-v1a -o jsonpath='{.status.succeeded}{.status.failed}' 2>/dev/null)
  [ "$S" = "1" ] && break; sleep 10; done
kubectl get job -n databases ninth-banner-feedback-db-init-v1 2>&1 | grep -c -i 'notfound'          # PASS: 1
kubectl get job -n databases ninth-banner-feedback-db-init-v1a \
  -o jsonpath='{.spec.template.spec.containers[0].image} {.status.succeeded}{"\n"}'
# PASS: pgvector/pgvector:0.8.7-pg16@sha256:7b822b0a...199b90a 1
# FAIL shapes: NotFound (Flux never applied -> check `flux get ks -n databases`), "<digest> " with an empty
#   succeeded plus .status.failed>0 (bootstrap error -> 4.B log), or v1 still present (prune failed).
kubectl get ks -n databases ninth-banner-feedback-db -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.lastAppliedRevision}{"\n"}'
# PASS: True refs/heads/main@sha1:<the commit from 3.4>
# FAIL: False ... "field is immutable" -> the rename did not land (the §1.2 failure) -> §5.A.

# 4.B The bootstrap actually ran end-to-end on the new client
kubectl logs -n databases job/ninth-banner-feedback-db-init-v1a | grep -c -E '^==> (Ensure role|Ensure database|Done)'   # PASS: 3
kubectl logs -n databases job/ninth-banner-feedback-db-init-v1a | grep -c -i -E 'error|fatal'                        # PASS: 0
# (Baseline measured on v1 2026-10-13: 3 and 0. With ON_ERROR_STOP a failing statement aborts before "==> Done", so the
#  first count drops below 3 on any SQL failure. Case-insensitive because psql prints "ERROR:".)

# 4.C CONTENTS: role/db attributes byte-identical, table set identical, no table lost rows
kubectl exec -i -n databases deploy/postgresql -- sh -c 'psql -X -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres -f -' \
  < "$W/state.sql" | grep -E '^(role|db|tbl):' > "$W/after.txt"
diff <(grep -E '^(role|db):' "$W/before.txt") <(grep -E '^(role|db):' "$W/after.txt") && echo ATTRS_SAME
python3 - "$W/before.txt" "$W/after.txt" <<'EOF'
import sys
def t(p): return {l.split('=')[0]: int(l.rsplit('=',1)[1]) for l in open(p) if l.startswith('tbl:')}
b,a=t(sys.argv[1]),t(sys.argv[2])
if not b: print("BASELINE_EMPTY"); sys.exit(1)
lost=[k for k in b if k not in a]; shrunk=[k for k in b if k in a and a[k]<b[k]]
print("TABLES_OK" if not lost and not shrunk and set(a)==set(b) else f"TABLES_FAIL lost={lost} shrunk={shrunk} new={sorted(set(a)-set(b))}")
EOF
# PASS: ATTRS_SAME and TABLES_OK. The app writes continuously, so counts may GROW; a shrink or a lost table fails.

# 4.D CONTENTS: the role still authenticates with the SOPS password over TCP (what the app does), and a wrong password is refused
#     MUST use the service address: -h 127.0.0.1 inside the pod is pg_hba trust and accepts ANY password (measured 2026-10-13).
kubectl get secret -n databases ninth-banner-feedback-db -o jsonpath='{.data.NINTH_BANNER_FEEDBACK_PASSWORD}' | base64 -d \
  | kubectl exec -i -n databases deploy/postgresql -- sh -c 'read -r P; PGPASSWORD="$P" psql -X -h postgresql.databases.svc -U ninth_banner_feedback -d ninth_banner_feedback -tAc "select current_user"'
# PASS: ninth_banner_feedback
printf 'wrong-on-purpose\n' | kubectl exec -i -n databases deploy/postgresql -- sh -c 'read -r P; PGPASSWORD="$P" psql -X -h postgresql.databases.svc -U ninth_banner_feedback -d ninth_banner_feedback -tAc "select 1"' >/dev/null 2>&1; echo "neg_rc=$?"
# PASS: neg_rc=2 (proves this gate CAN fail; neg_rc=0 means auth is trust on this path and 4.D proves nothing -> treat as FAIL)

# 4.E The consumer still reaches its store (Prometheus)
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
for q in 'feedback_store_up{namespace="my-software-production",job="the-ninth-banner"}' \
         'kube_job_status_succeeded{namespace="databases",job_name="ninth-banner-feedback-db-init-v1a"}' \
         'ALERTS{alertname="TheNinthBannerFeedbackStoreDown",alertstate="firing"}'; do
  curl -s --data-urlencode "query=$q" http://localhost:19090/api/v1/query \
   | python3 -c "import sys,json; r=json.load(sys.stdin)['data']['result']; print(len(r), [x['value'][1] for x in r])"; done
kill $PF 2>/dev/null
# PASS: "1 ['1']"   then "1 ['1']"   then "0 []"
# FAIL: feedback_store_up "0 []" (series gone -> the app or the scrape is broken, NOT a pass) or ['0']; job series empty
#       (kube-state-metrics has not seen v1a yet: wait 1 min and re-run before failing).

# 4.F The 0.8.6-pg16 digest is gone from the cluster (pruned v1's completed pod takes it with it)
for i in $(seq 1 30); do
  N=$(kubectl get pods -A -o json | python3 -c "import sys,json; print(sum(1 for p in json.load(sys.stdin)['items'] for c in p['spec'].get('containers',[])+p['spec'].get('initContainers',[]) if '0.8.6-pg16' in c['image']))")
  [ "$N" = "0" ] && break; sleep 10; done; echo "pods_on_0.8.6=$N"
# PASS: pods_on_0.8.6=0   (was 1 at authoring: ninth-banner-feedback-db-init-v1-4ncrd, Completed)
```

CONTENTS ASSERTION: the role `ninth_banner_feedback` and database `ninth_banner_feedback` keep identical attributes,
owner and ACL. The same table set exists with no table losing rows. Measured by `$W/state.sql` before vs. after (4.C),
compared to the §2.5 baseline.

CONTENTS ASSERTION: the role still authenticates over TCP with the SOPS-held password, and a wrong password is refused.
Measured by 4.D through `postgresql.databases.svc`. Baseline 2026-10-13: success and `neg_rc=2`.

CONTROL: metric feedback_store_up — `{namespace="my-software-production",job="the-ninth-banner"}` must return exactly
one series with value 1. An empty result is a FAIL. Limitation, measured: `min_over_time(feedback_store_up[7d])` stayed
1 across the 2026-10-12 shared-instance restart, so this metric is a floor and not the decisive gate. 4.D is the
decisive gate.

CONTROL: metric kube_job_status_succeeded — `{namespace="databases",job_name="ninth-banner-feedback-db-init-v1a"}` == 1.

CONTROL: alertname TheNinthBannerFeedbackStoreDown — must not be firing (rule in
`kubernetes/apps/monitoring/kube-prometheus-stack/app/the-ninth-banner-alerts.yaml`, `for: 15m`, so it only catches a
sustained break: re-check at the end of the window).

## 5. Rollback

**5.A Job failed, the ks is stuck, or 4.C/4.D fails:**

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <sha-from-3.4>      # renames back to v1 on 0.8.6, restores docs/applications.md
git log -1 --format=%s && git show --stat HEAD && git push
kubectl get job -n databases ninth-banner-feedback-db-init-v1 -o jsonpath='{.spec.template.spec.containers[0].image} {.status.succeeded}{"\n"}'
# Back when: 0.8.6 digest + 1, v1a NotFound, ks Ready True on the revert revision; then re-run 4.C and 4.D against before.txt.
```

The revert re-runs the same idempotent script on the 0.8.6 client, which is exactly what happened on 2026-10-12T14:01Z.
Nothing forward-only happened, so the revert is the whole rollback.

**5.B Role or database state damaged (4.C shows a lost or shrunk table, or the app cannot log in after 5.A).** This is
not expected from this script, but if it happens:
- Password lockout: the role password is re-asserted from SOPS on every run. Fix the SECRET, not the role (operator
  decision; see §2.4).
- Data loss in `ninth_banner_feedback`: restore from `$W/nbf.dump`, taken in §2.6 and validated against the live table
  count. Run the restore into the existing DB as admin:

  ```bash
  kubectl exec -i -n databases deploy/postgresql -- sh -c 'pg_restore -U "$POSTGRES_USER" -d ninth_banner_feedback --clean --if-exists --no-owner --role=ninth_banner_feedback' < "$W/nbf.dump"
  ```

  Fallback: the 03:00 Longhorn backup of `postgresql-data-5g` (CronJob `storage/daily-backup-all-volumes`). That restore
  is whole-instance, so it is an operator decision.

**5.C A Renovate PR (#383 or a successor) was merged and NOT reverted before this plan ran (premise `repo-pin-once` reads 1, repo file on 0.8.7 with `-init-v1`).** The ks is failing
on the immutable Job, as in §1.2. Do not revert that merge blindly, because it also carries the wanted image. Instead apply only
the rename half of §3.2 (the first `-e` plus the History `-e`), commit, and push. That completes the change and lets Flux
prune `v1` and create `v1a`. Then run §4.

## 6. Interference notes

- **No restart of anything.** The shared `databases/postgresql` is only a target for about 7 short admin statements.
  Locks are held for milliseconds, and the same statements already run weekly. `nocodb-2026.09.1` also declares
  `shared: [postgresql]`. It does not restart the instance and works on a different database, so the overlap is
  advisory and is not in `conflicts_with`.
- **Step 0 of the same window:** the `*ninth-banner-feedback-db*` deny rule holds #383 (§1.2; premise-style check in
  §2.2), so Step 0 will not merge it. If the rule were ever removed, #383 would reproduce §1.2 inside the safe-update
  batch (as #362 did with 6 innocent PRs). §3.6 closes #383 after this plan lands. Keep the rule afterwards (§1.2 c).
- **Flux plans** (`flux-distribution-2.9.6`, `flux-reconciler-impersonation`): this plan's whole
  mechanism is a Flux prune+create, so it must not run under a controller swap or an RBAC change of the applier.
  `flux-oci-chart-sources` only rewrites HelmRelease chart sources and does not touch this plain Kustomization, so it is
  not listed.
- **Prometheus:** 4.E reads it; no `kube-prometheus-stack` plan is open as of 2026-10-23 (add one to `conflicts_with` if filed).
- **The Ninth Banner app is redeployed often by CI** (helm release revisions v33 to v37 within 5 days, one 12 minutes
  before authoring). A CI deploy landing during 4.E can blip `feedback_store_up`. If 4.E fails while
  `kubectl get deploy -n my-software-production the-ninth-banner` shows a fresh rollout, wait for it and re-run 4.E
  before rolling back. 4.D is independent of the app pod.
- **Storage:** no PVC, PV or Longhorn Volume is touched, and nothing is deleted except the Job object `v1` (by Flux
  prune, with its completed pod).

### Repo corrections found while planning (report, not fixed here)

1. **auto-update has no immutable-Job guard.** `rg -i 'immutable|kind: *Job'` over `runbooks/auto-update.py`,
   `runbooks/coverage.py` and `auto-update-policy.yaml` finds nothing. Any Renovate image bump that touches a `kind: Job`
   manifest without a `metadata.name` change is guaranteed to fail Flux's dry-run. It cost two whole-batch reverts
   (#238, #316) and is already filed as `F-793d72d5`. This plan does not fix it, and the next pgvector or postgres bump
   will hit it again. **Partly mitigated 2026-10-17** by the path-scoped deny rule (it HOLDS, which is what stopped #383),
   but it is a per-component hand rule: a new Job-image consumer is unprotected until someone writes its rule. Options
   still open: route PRs that touch a Job image to the PLAN lane generically, or a Renovate `packageRules` that
   excludes `**/init-job.yaml`.
2. **Those reverts poison earned autonomy for this component.** "0 green / 4 reverts" is a Renovate-shape failure (no
   rename), not a pgvector 0.8.7 failure. The autonomy ledger attributes it to `ninth-banner-feedback-db-init-v1` and its
   siblings.
3. **`docs/sops/immutable-job-image-bumps.md` §4 example** runs
   `flux reconcile kustomization -n flux-system sweep-history`. That Kustomization lives in ns `databases`
   (`kubectl get ks -n databases sweep-history`), so the example fails NotFound as written.
4. **Fleet plans enumerate pins at authoring time only.** `pgvector-fleet-0.8.7` froze its inventory on 10-03 and a pin
   added on 10-05 slipped through. A premise such as `grep -rc '<old digest>' kubernetes/ | ...` with the expected total
   would have caught it at window time.
