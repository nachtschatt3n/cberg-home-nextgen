# SOP: Immutable Job/CronJob Image Bumps

> Description: How to change the image (or any pod-spec field) of a Flux-managed
> `batch/v1` Job whose `.spec.template` is immutable, using the `vN` rename
> convention — and how to do it safely when the Job bootstraps a live database.
> Version: `2026.08.18`
> Last Updated: `2026-08-18`
> Owner: `platform-sre`

---

## 1) Description

Kubernetes rejects most in-place edits to a `batch/v1` Job. A Flux Kustomization
that carries a Job manifest therefore **cannot** deliver an image bump, a command
change, an env change, or a resource change to an already-created Job: the apply
fails and the Kustomization goes `NotReady`. The dangerous part is not the error
— it is that the error is *quiet*. The old Job object stays exactly as it was,
the change looks landed in git, and every later reconcile of that Kustomization
fails too, so **the whole app path silently stops updating**.

This SOP covers detecting that state, fixing it with the `vN` rename convention
used in this repo, and the pre-flight safety work required when the Job
bootstraps a **live** database.

- Scope: every `kind: Job` manifest under `kubernetes/apps/**`, and the Flux
  Kustomizations that deliver them. Reference implementation:
  `kubernetes/apps/databases/sweep-history/app/init-job.yaml`.
- Prerequisites: repo write access (work on `main`, no feature branches),
  `kubectl` + `flux` against the cluster, and for DB-bootstrap jobs a working
  `psql` path (port-forward to `postgresql` in `databases`, or `SWEEP_PG_DSN`
  as set up by `runbooks/sweep-run.py`).
- Out of scope: Deployment/StatefulSet immutable-selector failures (those are
  `docs/sops/application-update.md` §7), and schema *migrations* that are not
  create-if-not-exists (those need their own one-shot migration script and an
  upgrade plan under `runbooks/maintenance/plans/`).

---

## 2) Overview

What is and is not mutable on an existing object:

| Setting | Value |
|---------|-------|
| Namespace | wherever the Job lives (reference case: `databases`) |
| Source of truth | `kubernetes/apps/<category>/<app>/app/*-job.yaml` |
| Critical dependency | Flux Kustomization with `prune: true` |
| Job `.spec.template` | **IMMUTABLE** after creation — image, command, env, volumes, resources |
| Job mutable fields | `.spec.parallelism`, `.spec.suspend`, `.spec.ttlSecondsAfterFinished`, `.spec.activeDeadlineSeconds` (and `.spec.completions` only while the Job is being created / for `NonIndexed` unstarted Jobs) |
| CronJob `.spec.jobTemplate` | **MUTABLE** — the CronJob is a template factory; the *next* scheduled Job is created from the edited template |
| CronJob already-created Jobs | still immutable — an in-flight Job keeps the old image until the next schedule |
| Fix for a standalone Job | rename `metadata.name` with a `vN` suffix → Flux prunes old, creates new |

The precise distinction that matters:

- **Standalone `batch/v1` Job** — this is the trap. The Job controller sets
  defaults and a controller-uid selector at admission, and the API server
  rejects any later change to `.spec.template`. A Flux apply of the edited
  manifest fails with `field is immutable`.
- **`batch/v1` CronJob** — editing `.spec.jobTemplate` (including the image) is
  a legal update and needs **no rename**. It takes effect on the next scheduled
  run; nothing back-patches the Jobs the CronJob already created. If you need
  it immediately, delete the current Job or trigger a manual run — do not
  rename the CronJob.

So: **rename Jobs, edit CronJobs.**

---

## 3) Blueprints

Source of truth for the convention is the Job manifest's own header comment.

- Source of truth file(s): `kubernetes/apps/databases/sweep-history/app/init-job.yaml`
- Related manifests/templates:
  `kubernetes/apps/databases/sweep-history/app/schema-configmap.yaml` (the
  bootstrap script + `schema.sql` the Job runs),
  `kubernetes/apps/databases/sweep-history/ks.yaml` (`prune: true`)
- Required IDs/constants: the name suffix itself is the version marker —
  **major** `v1, v2, v3` = schema version; **minor** `v1a, v1b, v3a, v3b` =
  bootstrap/script/image fixes that do **not** alter the schema.

```yaml
---
# One-shot init Job. Major suffix (v1, v2, …) tracks schema version. Minor
# suffix (v1a, v1b, …) tracks bash-only bootstrap fixes that don't alter
# the schema. Flux prune deletes the previous Job and creates the new one.
#
# History:
#   v3  — added the 4 operator-curated policy tables. No data migration here.
#   v3a — pin image to the live digest (float-tag pinning batch); no schema or
#         bash change. Rename forces prune+recreate (Job spec is immutable);
#         bootstrap is idempotent.
#   v3b — <one line: what changed and why, and that the bootstrap is idempotent>
#   v4  — partial UNIQUE index on sweep_findings(finding_id) WHERE
#         resolved_at IS NULL.
#   v5  — CHECK ck_findings_resolved_status (resolved_at IS NULL OR
#         status='resolved').
apiVersion: batch/v1
kind: Job
metadata:
  name: sweep-history-init-v3b   # <- the ONLY field that must change to redeploy
  namespace: databases
spec:
  backoffLimit: 6
  ttlSecondsAfterFinished: 604800
  template:
    spec:
      restartPolicy: OnFailure
      containers:
        - name: bootstrap
          image: <registry>/<image>:<tag>@sha256:<digest>
```

Rules for the block above:

1. Bump the **minor** letter for an image bump, a digest re-pin, a bash fix, or
   any pod-spec change that leaves `schema.sql` semantically unchanged.
2. Bump the **major** number when `schema.sql` gains or changes tables/columns.
3. **Every rename appends exactly one `History:` line** — what changed, why, and
   an explicit statement that the bootstrap is idempotent (or what makes it
   safe). The History block is the audit trail; a rename without one is
   incomplete.
4. Keep the manifest filename stable (`init-job.yaml`); only `metadata.name`
   carries the version.

---

## 4) Operational Instructions

1. **Preparation**
   - Identify the Job and confirm it is a Job, not a CronJob:
     `kubectl get job,cronjob -A | grep <name>`. If it is a CronJob, stop —
     just edit `.spec.jobTemplate` and push; no rename.
   - Confirm the delivering Kustomization has `prune: true`
     (`grep -n 'prune:' kubernetes/apps/<category>/<app>/ks.yaml`). Without
     prune, the old Job is orphaned instead of removed (see §7).
   - **Read the Job's script end-to-end** (usually a ConfigMap next to it).
     If it touches a live database, do the whole of §4a before continuing.
   - Verify the new image tag/digest actually exists in the registry
     (`docs/sops/application-update.md` §4 Step 0). Never bump to an
     unpublished tag.

2. **Change implementation**
   - Edit the image (or whatever pod-spec field changed) **and**
     `metadata.name` in the same commit: `<name>-v3a` → `<name>-v3b`.
   - Append the one-line `History:` entry.
   - Lint: `kubeconform -summary -exit-on-error -ignore-missing-schemas kubernetes/apps/<category>/<app>`.

3. **Commit/push (GitOps)** — directly on `main`, staging only the specific
   hunks you changed (the worktree is shared with other sessions).

4. **Reconciliation/rollout checks** — Flux prunes the old Job and creates the
   new one; then run §6.

```bash
# Example operation flow
grep -n 'name: .*-v[0-9]' kubernetes/apps/databases/sweep-history/app/init-job.yaml
git add -p kubernetes/apps/databases/sweep-history/app/init-job.yaml
git commit -m "fix(sweep-history): bump init image, v3a -> v3b (Job spec is immutable)"
git push
flux reconcile kustomization -n flux-system sweep-history --with-source
kubectl -n databases get jobs -l app.kubernetes.io/name=sweep-history
```

### 4a) Safety checklist — Job bootstraps a LIVE database

A rename does not just redeploy the Job: **it re-runs it, in full, against
production data.** This checklist is mandatory before any rename of a
DB-touching Job. Do not skip it because "only the image changed".

- **(a) Read the bootstrap script end-to-end first.** All of it — the shell
  wrapper *and* every `.sql` it applies. You are re-executing this against live
  data; "I only changed the image tag" is not a reason to skip the read.
- **(b) Confirm every statement is create-if-not-exists / idempotent:**
  - `CREATE TABLE IF NOT EXISTS ...`
  - `CREATE INDEX IF NOT EXISTS ...`
  - guarded role/database creation, i.e. the
    `psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='<role>'" | grep -q 1 || psql -c "CREATE ROLE ..."`
    and `SELECT 1 FROM pg_database WHERE datname='<db>' | grep -q 1 || CREATE DATABASE ...` forms
  - `GRANT` / `ALTER DEFAULT PRIVILEGES` (naturally idempotent)
  - `ALTER ROLE ... WITH PASSWORD ...` (idempotent, but note it **re-asserts**
    the SOPS-held password — fine, and it is why a rotated password must also
    be a rename)
- **(c) STOP and escalate to the operator if the script does ANYTHING else.**
  Any of these is a hard stop, not a judgement call:
  - a bare `DROP TABLE` / `DROP INDEX` / `DROP DATABASE` / `DROP ROLE`
  - `TRUNCATE`
  - `DELETE FROM`
  - an unguarded `INSERT` (no `ON CONFLICT DO NOTHING`, no `WHERE NOT EXISTS`) —
    a re-run duplicates rows
  - a destructive `ALTER` — dropping a column, adding a `NOT NULL` without a
    default, renaming, or changing a primary key
- **(d) Widening vs narrowing `ALTER TABLE ... ALTER COLUMN ... TYPE`.**
  A **widening** change is acceptable and idempotent — it is a no-op once
  applied. The live precedent in this repo is
  `ALTER TABLE slo_snapshots ALTER COLUMN budget_remaining_pct TYPE NUMERIC(8,2)`
  (widened from `NUMERIC(5,2)`), which re-runs harmlessly forever.
  A **narrowing** change is **not** safe: it can fail on existing rows or
  silently round/truncate them. Narrowing belongs in a reviewed one-shot
  migration with a backup and an upgrade plan — never in a re-runnable
  bootstrap Job.
- **(e) Take a logical backup of the affected tables FIRST, regardless of how
  clean (b) looked.** Per table, so restore is surgical:

  ```bash
  kubectl port-forward -n databases svc/postgresql 5432:5432 &
  export PGHOST=localhost PGPORT=5432 PGUSER=<admin-user> PGPASSWORD=<from-sops>
  TS=$(date +%Y%m%d-%H%M%S)
  for t in accepted_risks slo_definitions noise_suppressions security_acceptances; do
    pg_dump -d sweep_history -t "$t" -f "/tmp/${t}-${TS}.sql"
  done
  ls -l /tmp/*-${TS}.sql   # non-zero size for every table
  ```

  Keep the dumps **out of the repo** (`/tmp`, never `kubernetes/`) — they
  contain operator policy data.
- **(f) Capture row counts BEFORE, and compare AFTER.**

  ```bash
  psql -d sweep_history -tAc "
    SELECT 'accepted_risks', count(*) FROM accepted_risks
    UNION ALL SELECT 'slo_definitions', count(*) FROM slo_definitions
    UNION ALL SELECT 'noise_suppressions', count(*) FROM noise_suppressions
    UNION ALL SELECT 'security_acceptances', count(*) FROM security_acceptances
    UNION ALL SELECT 'sweep_findings', count(*) FROM sweep_findings
    UNION ALL SELECT 'sweep_cycles', count(*) FROM sweep_cycles;" | tee /tmp/rowcounts-before.txt
  ```

  After the Job completes, re-run into `/tmp/rowcounts-after.txt` and `diff`.
  Any change other than rows added by normal traffic between the two samples is
  an incident: restore from (e) immediately.

---

## 5) Examples

### Example A: common case — image bump on the sweep-history init Job

Motivation: a **security-driven image bump** of the bootstrap container from
`pgvector/pgvector:0.8.1-pg16` to `0.8.6-pg16` (tracked as
`security_ref: F-xxxxxxxx`; details stay on the sweep_findings record, never in
git). The Job bootstraps the **live policy database** that holds
`accepted_risks`, `slo_definitions`, `noise_suppressions` and
`security_acceptances` — the tables `runbooks/policy-cli.py` and every audit
script read. So the bump is a §4a case, not a one-line edit.

```bash
# 1. Safety pre-flight (§4a): read schema-configmap.yaml end-to-end.
#    Verdict for this Job: CREATE TABLE/INDEX IF NOT EXISTS throughout, guarded
#    role+database creation, GRANT/ALTER DEFAULT PRIVILEGES, and ONE widening
#    ALTER (budget_remaining_pct -> NUMERIC(8,2), already applied = no-op).
#    No DROP / TRUNCATE / DELETE / unguarded INSERT. => safe to re-run.
sed -n '1,200p' kubernetes/apps/databases/sweep-history/app/schema-configmap.yaml

# 2. Backup + BEFORE row counts (§4a e/f) into /tmp.

# 3. Resolve the new digest, then edit BOTH the image and metadata.name:
#      image: pgvector/pgvector:0.8.6-pg16@sha256:<digest>
#      name:  sweep-history-init-v3a  ->  sweep-history-init-v3b
#    ... and append the History line:
#      v3b — security-driven base-image bump (security_ref: F-xxxxxxxx); no
#            schema or bash change. Rename forces prune+recreate (Job spec is
#            immutable); bootstrap is idempotent.

kubeconform -summary -exit-on-error -ignore-missing-schemas \
  kubernetes/apps/databases/sweep-history/app
git add -p kubernetes/apps/databases/sweep-history/app/init-job.yaml
git commit -m "fix(sweep-history): init image bump, v3a -> v3b (immutable Job spec)"
git push

# 4. Watch the swap: old Job pruned, new Job created and completing.
kubectl -n databases get jobs -l app.kubernetes.io/name=sweep-history -w
```

### Example B: edge case — Flux already stuck on `field is immutable`

Someone bumped the image without the rename. The Kustomization has been
`NotReady` for days and nothing in that path has deployed since.

```bash
# Confirm the blocked Kustomization and read the actual error
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
kubectl describe kustomization -n flux-system <name> | sed -n '/Conditions/,$p'
# -> Job.batch "<name>" is invalid: spec.template: Invalid value: ...: field is immutable

# Fix forward: rename metadata.name (+ History line), commit, push.
# Do NOT hand-edit the live Job and do NOT delete the new-named Job.
flux reconcile kustomization -n flux-system <name> --with-source

# Everything else that Kustomization owns was ALSO blocked — re-verify it all:
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
kubectl -n <ns> get all
```

### Example C: it is a CronJob — do NOT rename

```bash
# Edit .spec.jobTemplate.spec.template.spec.containers[0].image in git, push.
flux reconcile kustomization -n flux-system <name> --with-source
kubectl -n <ns> get cronjob <name> -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].image}{"\n"}'
# The next scheduled Job uses the new image. Already-created Jobs keep the old one.
```

---

## 6) Verification Tests

### Test 1: Flux is Ready and the rename actually swapped the Job

```bash
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
kubectl -n <ns> get jobs -l app.kubernetes.io/name=<app>
kubectl -n <ns> get job <new-name> \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
```

Expected:
- The first command prints only the header row (no `NotReady` Kustomization).
- Only the **new** Job name is listed; the old `vN` name is gone.
- The printed image is the new tag/digest from git.

If failed:
- `kubectl describe kustomization -n flux-system <name>` and read the
  `Conditions` — an `is invalid: spec.template: ... field is immutable` message
  means the rename did not land (check you edited `metadata.name`, not just a
  comment).

### Test 2: the Job completed and its output is the expected bootstrap

```bash
kubectl -n <ns> wait --for=condition=complete job/<new-name> --timeout=300s
kubectl -n <ns> logs job/<new-name>
```

Expected:
- `job.batch/<new-name> condition met`.
- Logs show the expected bootstrap steps and no SQL errors — for
  sweep-history: `==> Ensure roles exist`, `==> Ensure database sweep_history
  exists`, `==> Apply schema migrations`, `==> Apply grants`, `==> Done`.

If failed:
- `kubectl -n <ns> describe job/<new-name>` for the pod failure reason, then
  `kubectl -n <ns> logs job/<new-name> --previous`. `ON_ERROR_STOP=1` means the
  first failing statement is the last line of output.

### Test 3: data is intact (DB-bootstrap Jobs only)

```bash
psql -d sweep_history -tAc "... same UNION ALL query as §4a(f) ..." \
  | tee /tmp/rowcounts-after.txt
diff /tmp/rowcounts-before.txt /tmp/rowcounts-after.txt
```

Expected:
- `diff` is empty (or shows only rows added by normal traffic in the interval).

If failed:
- Stop all sweep activity and restore the affected table from the §4a(e) dump
  (see §11), then re-read the bootstrap script for the destructive statement
  that (b)/(c) missed.

### Test 4: the consumers still work

```bash
runbooks/policy-cli.py risk list
runbooks/policy-cli.py slo list
runbooks/policy-cli.py noise list
runbooks/policy-cli.py sec list
```

Expected:
- Each returns the expected populated table — roles, grants and schema all
  survived the re-run.

If failed:
- A permission error means the grants block did not complete; re-check Test 2's
  logs for the `==> Apply grants` section.

---

## 7) Troubleshooting

| Symptom | Likely Cause | First Fix |
|---------|--------------|-----------|
| `Job.batch "<name>" is invalid: spec.template: Invalid value: ...: field is immutable` | pod-spec edit applied to an existing Job | rename `metadata.name` with the next `vN` suffix (§4), commit, push |
| Image bump "committed" in git but the cluster still runs the old image; no alert | the Kustomization has been `NotReady` since the failed apply; the old Job object is untouched | `flux get kustomizations -A \| awk 'NR==1 \|\| $5 != "True"'`, then rename |
| Everything else in that app folder also stopped updating | one immutable-field error fails the **whole** Kustomization apply, not just the Job | fix the Job, reconcile, then re-verify every object that Kustomization owns |
| Old `vN` Job still present next to the new one | Kustomization has `prune: false` (or the Job is not owned by that Kustomization) | set `prune: true` in `ks.yaml`; as a one-off, `kubectl -n <ns> delete job <OLD-name>` — the **old** name only, never the new one |
| New Job `Completed` but the app still behaves old | you renamed a **CronJob**, or an in-flight Job from the CronJob is still running the old template | CronJobs are mutable — revert the rename, edit `.spec.jobTemplate`, wait for the next schedule |
| Job re-runs and row counts change | the bootstrap is not idempotent (unguarded `INSERT`, `DELETE`, `TRUNCATE`) | restore from the §4a(e) `pg_dump`, revert the commit (§11), fix the script before renaming again |
| `PGPASSWORD`/`${VAR}` empty inside the Job's script | Flux `postBuild.substituteFrom` ate the bash `${VAR}` | escape as `$${VAR}` in the ConfigMap (cluster-wide rule) |

```bash
# Quick debugging commands
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
kubectl describe kustomization -n flux-system <name> | sed -n '/Conditions/,$p'
kubectl -n <ns> get jobs -o custom-columns=NAME:.metadata.name,IMAGE:.spec.template.spec.containers[0].image,COMPLETIONS:.status.succeeded
kubectl -n <ns> logs job/<name> --tail=50
```

---

## 8) Diagnose Examples

### Diagnose Example 1: "the image bump never reached the cluster"

```bash
# 1. What does git say?
git log --oneline -3 -- kubernetes/apps/<category>/<app>/app/
grep -n 'image:\|name: ' kubernetes/apps/<category>/<app>/app/*-job.yaml

# 2. What does the cluster run?
kubectl -n <ns> get job -o custom-columns=NAME:.metadata.name,IMAGE:.spec.template.spec.containers[0].image

# 3. Why did delivery stop?
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
kubectl describe kustomization -n flux-system <name> | sed -n '/Conditions/,$p'
```

Expected:
- The Kustomization is `False`/`NotReady` with an
  `is invalid: spec.template: ... field is immutable` message, and the live Job
  name equals the **pre-bump** `vN` name → confirmed: missing rename.

If unclear:
- Compare the manifest's `metadata.name` with the live Job name. Identical names
  plus a different image = the rename was forgotten. Different names plus an old
  Job still present = a prune problem, not an immutability problem.

### Diagnose Example 2: "the renamed Job ran but the database looks wrong"

```bash
kubectl -n <ns> logs job/<new-name> | tail -40
psql -d sweep_history -tAc "\dt" 2>/dev/null || echo "connect/permission failure"
psql -d sweep_history -tAc "SELECT count(*) FROM accepted_risks;"
diff /tmp/rowcounts-before.txt /tmp/rowcounts-after.txt
```

Expected:
- Logs end at `==> Done` with no SQL error, all expected tables present, and the
  `diff` empty → the Job is fine and the problem is elsewhere (client DSN,
  port-forward, wrong database).

If unclear:
- Re-read the script for a non-idempotent statement (§4a c) and grep the schema
  for anything that is not `IF NOT EXISTS`:
  `grep -nE 'DROP |TRUNCATE|DELETE FROM|^ *INSERT' kubernetes/apps/<category>/<app>/app/*configmap*.yaml`

---

## 9) Health Check

Recurring, cheap, and the thing that would have caught the silent stall:

```bash
# 1. No Kustomization is stuck (this is the whole early-warning signal)
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'

# 2. Every Job manifest's metadata.name matches a live Job of that name
grep -rn 'name: .*-v[0-9]' kubernetes/apps --include='*job*.yaml'
kubectl get jobs -A -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name,SUCCEEDED:.status.succeeded

# 3. No orphaned previous-generation Jobs left behind
kubectl get jobs -A | grep -E '\-v[0-9][a-z]?\b'
```

Expected:
- Command 1 prints only the header row.
- For each Job manifest, exactly one live Job with the manifest's name and
  `SUCCEEDED=1`; no older `vN` sibling.

---

## 10) Security Check

```bash
# No plaintext secret entered the manifest with the bump
grep -nE 'PASSWORD|TOKEN|SECRET' kubernetes/apps/<category>/<app>/app/*-job.yaml
# -> must be secretKeyRef only, never a literal `value:`

# Image is digest-pinned, not a float tag
grep -n 'image:' kubernetes/apps/<category>/<app>/app/*-job.yaml

# No vulnerability detail leaked into git with the bump
git diff --cached | grep -inE 'CVE-[0-9]{4}-[0-9]+|critical: *[0-9]+|high: *[0-9]+'

# No dumps or decrypted policy data staged
git status --short | grep -E '\.sql$|rowcounts'
```

Expected:
- No plaintext secrets in the repo — credentials only via `secretKeyRef` into
  the app's SOPS secret.
- The image carries an `@sha256:` digest alongside the tag.
- **Zero** CVE IDs, per-image vulnerability counts, or unfixed-vulnerability
  descriptions in the manifest, the `History:` line, or the commit message.
  A bump is motivated in git as "a security-driven image bump" plus
  `security_ref: F-xxxxxxxx`; the detail lives on the `sweep_findings` record
  (`docs/sops/vulnerability-disclosure.md`).
- `pg_dump` output and row-count files stay in `/tmp`, never staged.
- Role passwords are unchanged unless the rotation was intentional — note that
  the bootstrap re-asserts them from SOPS on every run.

---

## 11) Rollback Plan

Repo convention: **revert forward with a new commit. Never `reset --hard`,
never force-push.**

```bash
# 1. Revert the rename + image bump (restores the previous vN name and image)
git revert <sha>
git push
flux reconcile kustomization -n flux-system <name> --with-source

# Flux prunes the v3b Job and recreates v3a from the reverted manifest, which
# re-runs the (idempotent) bootstrap on the OLD image. Verify with §6 Test 2.

# 2. If Flux did not prune (prune: false), remove the superseded Job by name
kubectl -n <ns> delete job <name-that-should-no-longer-exist>

# 3. If DATA was harmed, restore the affected tables from the §4a(e) dumps
kubectl port-forward -n databases svc/postgresql 5432:5432 &
psql -d sweep_history -c "BEGIN; TRUNCATE <table>; \i /tmp/<table>-<TS>.sql; COMMIT;"
# Restore ONE table at a time, verify counts against /tmp/rowcounts-before.txt
# after each, and do it with the operator watching — this is the only step in
# this SOP that is itself destructive.

# 4. Re-verify the consumers
runbooks/policy-cli.py risk list
runbooks/policy-cli.py slo list
```

---

## 12) References

- `kubernetes/apps/databases/sweep-history/app/init-job.yaml` — reference
  implementation of the `vN` convention and its `History:` block
- `kubernetes/apps/databases/sweep-history/app/schema-configmap.yaml` — the
  idempotent bootstrap script + `schema.sql` (widening-`ALTER` precedent)
- `kubernetes/apps/databases/sweep-history/ks.yaml` — `prune: true`, the
  prerequisite for rename-based redeploy
- `docs/sops/application-update.md` — general version-bump SOP (silences,
  immutable Deployment selectors, revert path)
- `docs/sops/vulnerability-disclosure.md` — what may and may not be written into
  git when a bump is security-motivated
- `docs/sops/policy-cli.md` and `runbooks/policy-cli.py` — the consumers of the
  policy tables used in the verification tests
- `docs/sops/backup.md` — backup/restore context beyond the per-table `pg_dump`

---

## Version History

- `2026.08.18`: Initial — Job `.spec.template` immutability vs mutable CronJob
  `.spec.jobTemplate`, the silent-stall failure shape and its detection, the
  `vN` major/minor rename convention with mandatory `History:` entry, the
  live-database safety checklist (idempotency audit, hard-stop statements,
  widening-vs-narrowing `ALTER`, per-table `pg_dump`, row-count before/after),
  and the revert-only rollback path.

## DDL that a migration script cannot ship

A one-shot Python migration under `runbooks/` connects as the app role
(`sweep_writer` for sweep-history), which holds DML but **not table ownership**.
`CREATE INDEX`, `ALTER TABLE` and `ADD CONSTRAINT` therefore fail with
`must be owner of table <t>` — as `runbooks/refingerprint-findings.py` did on
2026-08-18, correctly rolling its whole transaction back rather than
half-applying.

Split the work by privilege, not by convenience:

| Change | Ships via |
|---|---|
| Row rewrites, backfills, dedupe | the migration script (app role) |
| Index / constraint / column DDL | `schema-configmap.yaml` + an init-Job suffix bump (owner) |

**Order matters and is not guessable: run the data migration FIRST.** A
constraint or unique index build fails the Job if any row still violates it, so
a Job-first sequence turns a clean migration into a failed reconcile. Have the
migration script attempt the DDL opportunistically inside a `SAVEPOINT` (so an
owner-DSN run lands it immediately) and report it as delivered-elsewhere on
failure, rather than aborting the data half over a missing grant.
