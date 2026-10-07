---
plan_id: vaultwarden-1.37.4
component: vaultwarden                # HelmRelease office/vaultwarden (bjw-s app-template 5.1.0), image vaultwarden/server
pr: 242                               # Renovate "fix(container): update vaultwarden/server ( 1.37.3 → 1.37.4 )" — CI green 2026-10-07
kind: image
current: "1.37.3"                     # MEASURED live 2026-10-07: deploy image vaultwarden/server:1.37.3, GET /api/version -> "1.37.3",
                                      # `/vaultwarden --version` -> Vaultwarden 1.37.3 / Web-Vault 2026.7.0
target: "1.37.4"                      # Docker Hub tag published 2026-10-05T23:37Z, multi-arch incl. amd64 (measured)
update_type: patch
risk: low                             # technical risk low (§1.3: every upgrade note is N/A to our config; one ADDITIVE SQLite
                                      # migration that the old binary tolerates). Blast radius if wrong is HIGH (household
                                      # credential store) — that is carried by capability_change/HUMAN-GATED + 3 backups, not
                                      # by inflating risk.
est_duration_min: 30                  # 8 pre-checks/baselines, 3 edit+commit+push, ~4 reconcile (Recreate, 1 pod), 10 verification
                                      # incl. operator login, 5 buffer
needs_reboot: false
touches:
  namespaces: [office]
  resources:                          # every object verified to EXIST live 2026-10-07 (kubectl get)
    - helmrelease/vaultwarden         # the only object this plan EDITS (values.controllers.main.containers.main.image.tag)
    - deployment/vaultwarden          # pod template image changes -> ONE pod roll; strategy Recreate (verified live)
    - pvc/vaultwarden-data            # RWO longhorn-static (PV/volume vaultwarden-data); SQLite db.sqlite3 migrated in place
                                      # (+1 nullable column) and a pre-upgrade VACUUM copy written next to it (§3.2)
    - httproute/vaultwarden           # unchanged spec; serves 503 during the ~30-60 s Recreate gap
  shared:
    - monitoring                      # §4 reads Prometheus (probe_success / kube-state-metrics / ALERTS)
    - credentials                     # household password manager: every family client loses sync for the roll gap
depends_on: []
conflicts_with:
  - app-template-5.2.1                # Batch A edits THIS helmrelease.yaml (chart 5.1.0) and its §4 asserts vaultwarden keeps the
                                      # SAME pod/generation — same night = merge conflict + a false GEN_CHANGED abort
  - kube-prometheus-stack-91.9.0      # §4 reads Prometheus (shared instrument); kps lists every Prometheus reader
  - coredns-1.48.2                    # its §4 gates on min_over_time(probe_success{probe_class="http"}) incl. http-vaultwarden;
                                      # our Recreate gap would fail that gate and vice versa (a DNS fault fails ours)
  - chart-patches-coredns-reloader-blackbox  # rolls the blackbox exporter that produces our CONTROL series, and its
                                      # premise/§4 read probe http-vaultwarden
  - nextcloud-fleet-35.0.1            # its §2.5 Alertmanager silence is office-wide -> would hide VaultwardenHttpProbe*
  - helm-drift-detection              # adds spec.driftDetection to every HR incl. helmrelease/vaultwarden (same object)
  - flux-oci-chart-sources            # rewrites the bjw-s chart source block of this HR (same spec.chart block)
exclusive: false
security_ref: F-3ee3a4fa              # Trivy "newer tag available" row; upstream app-level fixes tracked on F-e5e30871 (§1.4)
capability_change: true               # NOT a same-behaviour bump: upstream REMOVES API routes (legacy register/prelogin),
                                      # breaks `bw send receive` for CLI <= 2026.4.2, removes 12 client feature flags and
                                      # the Duo iframe prompt, changes org-member/permission behaviour, adds a new email
                                      # template and ships a newer web vault (§1.2). Nothing we RUN uses the removed parts
                                      # (§1.3), but feature loss for a family client is exactly what SD-11 reserves for a human.
rollback_class: git-revert            # MEASURED from upstream code (§1.3c): the only migration adds a NULLABLE column; diesel
                                      # 2.3 `pending_migrations` silently ignores applied versions it does not embed, so 1.37.3
                                      # boots on the migrated DB. Data fallback (§5.B/§5.C) is a named VACUUM copy + the
                                      # nightly Longhorn backup — it is a contingency, not the rollback path.
finding_refs: [F-68aca77f]            # version finding "vaultwarden: image vaultwarden/server 1.37.3 → 1.37.4 (patch)"
                                      # (F-11bb688f = the chart 5.2.1 leg, owned by app-template-5.2.1, NOT this plan)
review: null
premises:
  - id: live-image-is-1.37.3
    why: >-
      The plan's rollback target and the "migration has not run yet" baseline both assume the
      serving pod is 1.37.3. If something already moved it, re-plan.
    run: kubectl get deploy vaultwarden -n office -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "vaultwarden/server:1.37.3"
  - id: hr-ready-at-current-generation
    why: "No in-flight upgrade to stack on; git revert must land on a known-good revision."
    run: kubectl get helmrelease vaultwarden -n office -o jsonpath='{.metadata.generation}={.status.observedGeneration}={.status.conditions[?(@.type=="Ready")].status}'
    expect_matches: '^(\d+)=\1=True$'
  - id: repo-pins-1.37.3-once
    why: "§3.3's sed assumes exactly one matching tag line in the HR file (run from the repo root)."
    run: "grep -c '^              tag: \"1.37.3\"$' kubernetes/apps/office/vaultwarden/app/helmrelease.yaml"
    expect_exact: "1"
  - id: strategy-recreate
    why: >-
      Single replica on an RWO Longhorn PVC: a RollingUpdate would schedule the new pod before the
      old releases the volume (docs/sops/longhorn-rwo-multi-attach.md) and two vaultwarden processes
      must never open the same SQLite file. Verified Recreate on 2026-10-07.
    run: kubectl get deploy vaultwarden -n office -o jsonpath='{.spec.strategy.type}'
    expect_exact: "Recreate"
  - id: no-removed-flag-env
    why: >-
      Upstream: if EXPERIMENTAL_CLIENT_FEATURE_FLAGS lists a removed flag, admin-panel saves fail;
      DUO_USE_IFRAME is now ignored; the IP_HEADER=X-Forwarded-For semantics changed; DATABASE_URL
      would mean we are not on the SQLite file §3.2 backs up. None may be set on the Deployment
      (measured 2026-10-07: 0). The /data/config.json half (admin-panel overrides) needs exec, which
      premises refuse — it is §2.4b.
    run: kubectl get deploy vaultwarden -n office -o jsonpath='{range .spec.template.spec.containers[0].env[*]}{.name}{"\n"}{end}' | grep -c -x -e EXPERIMENTAL_CLIENT_FEATURE_FLAGS -e DUO_USE_IFRAME -e IP_HEADER -e DATABASE_URL
    expect_exact: "0"
  - id: nightly-backup-exists
    why: >-
      Contingency §5.C restores the newest Completed Longhorn backup. Existence only — plan-premises.py
      refuses python3, so FRESHNESS is the §2.6 longhorn-backup-age.py gate.
    run: kubectl get backups.longhorn.io -n storage -l backup-volume=vaultwarden-data -o jsonpath='{.items[*].status.state}'
    expect_contains: Completed
status: draft
window: null                          # planner recommendation (window agent decides): first attended slot without a declared
                                      # conflict, e.g. sat-attended:2026-10-10 next to jellyfin-12.1 (disjoint ns/objects;
                                      # git-revert class, so no backup-restore stacking) — or an operator NOW run (§1.4).
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/backup.md
  - docs/sops/longhorn.md
  - docs/sops/longhorn-rwo-multi-attach.md
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/vulnerability-disclosure.md
generated: "2026-10-07"
---

# vaultwarden: image 1.37.3 -> 1.37.4 (one additive SQLite migration; API/flag removals N/A to our config)

## 1) Summary & why held

`office/vaultwarden` is the household password manager: bjw-s app-template 5.1.0, one
Deployment (`strategy: Recreate`), image `vaultwarden/server:1.37.3`, SQLite at
`/data/db.sqlite3` on the RWO `longhorn-static` volume `vaultwarden-data` (10 Gi, 2 replicas,
nightly Longhorn backup via `storage/daily-backup-all-volumes` @ 03:00). Exposed only on
`envoy-internal` (HTTPRoute `office/vaultwarden`, `sectionName: https`), Homepage-registered,
no Authentik in front (vaultwarden does its own auth). Blackbox probe `monitoring/http-vaultwarden`
hits `/alive` through the full DNS -> Envoy -> route path. Renovate PR #242 is a one-line tag
bump, CI (`Flate Render Gate`, flux-local diff) green. Answers finding `F-68aca77f`.

**Why held:** auto-update gate G3 — the upstream release notes for 1.37.4 carry an
**"Upgrade notes"** section (primary source: GitHub release `dani-garcia/vaultwarden` tag
`1.37.4`, published 2026-10-05T23:40Z, fetched via `gh api repos/dani-garcia/vaultwarden/releases/tags/1.37.4`).

### 1.1 The upgrade notes, quoted, with our exposure

| Upstream note (quoted/condensed) | Applies to us? | Evidence |
|---|---|---|
| "**Reverse proxies:** with `IP_HEADER=X-Forwarded-For`, the client IP is now the rightmost address that isn't in `IP_HEADER_TRUSTED_PROXIES` (it used to be the leftmost)." | **No.** We do not set `IP_HEADER`; the default is `X-Real-IP` (`src/config.rs` @1.37.4: `ip_header … "X-Real-IP"`). The XFF code path is not taken. | premise `no-removed-flag-env` (env grep = 0) |
| "**Sends:** `bw send receive` on CLI 2026.4.2 and older no longer works." | **Not by anything we run** — no `bw` CLI consumer in this repo, no external-secrets/Bitwarden store in the cluster (`kubectl get clustersecretstore -A` empty). A family member on an ancient CLI would lose Send-receive → capability change, see frontmatter. | repo grep 2026-10-07 |
| "**Feature flags:** … removed … If `EXPERIMENTAL_CLIENT_FEATURE_FLAGS` still lists one of them, startup logs a warning and saving settings in the admin panel fails until it's removed." | **No.** Env not set; no `/data/config.json` (admin-panel overrides). | premise `no-removed-flag-env` + §2.4b |
| "**Duo:** `DUO_USE_IFRAME` … is removed and ignored if set." | **No.** Not set. | same premise |
| "**Custom templates:** there's a new email template, `email/recover_twofactor`." | **No action.** We ship no custom templates (no `templates/` dir in `/data`, measured `ls -la /data`). | `ls -la /data` 2026-10-07 |
| "The legacy `POST /identity/accounts/register` and `POST /api/accounts/prelogin` endpoints are removed. No current client uses them." | Route removal — used as a POSITIVE gate in §4.4 (old route 200 today, must 404 after). | live probe 2026-10-07: both prelogin routes 200 |
| MariaDB/MySQL TLS on Alpine image | **No.** SQLite, Debian image. | no `DATABASE_URL` env |

### 1.2 Behaviour changes not in "Upgrade notes" (why `capability_change: true`)

From the same release body ("What's Changed"): web vault 2026.9.0 support (vault banner
policy), `organizationsNew`/`policiesNew` in sync, new client feature flags
(`pm-32009-new-item-types`, `pm-34171-card-scanner`, Windows credential sync, …), "Fix revoked
org members retaining access to org ciphers", "Ensure all user checked routes are confirmed",
"Hide the whole change-email section when EMAIL_CHANGE_ALLOWED is false", "Sends cleanup:
remove legacy endpoints", "Remove legacy API endpoints and compatibility code", "Align API with
upstream". These change what clients can do. None is expected to hurt a current official
client, but they are user-visible behaviour, so the plan declares it.

### 1.3 Database migration — measured from upstream code, not assumed

a. `gh api repos/dani-garcia/vaultwarden/compare/1.37.3...1.37.4` lists exactly ONE new
   migration per engine: `migrations/sqlite/2026-09-02-120000_add_key_id/up.sql` =
   `ALTER TABLE users ADD COLUMN key_id TEXT;` (nullable, no default, no backfill).
   `down.sql` is **empty**. `src/db/schema.rs` adds `key_id -> Nullable<Text>` to `users`.
b. Migrations run automatically at startup (`src/db/mod.rs`: `sqlite_migrations::run_migrations`
   -> `run_pending_migrations(MIGRATIONS)`), diesel 2.3.13 / diesel_migrations 2.3.2.
c. **Rollback compatibility:** `diesel_migrations` 2.3.2 `MigrationHarness::pending_migrations`
   builds a map of the binary's embedded migrations and `remove`s each applied version — an
   applied version the binary does not know (here `20260902120000`) is silently ignored, not
   an error. 1.37.3's diesel schema does not know `users.key_id` and selects/inserts explicit
   columns, so an extra nullable column is invisible to it. ⇒ reverting the image tag is a
   valid rollback without a data restore. What is lost on revert: any `key_id` a 2026.8.1+ web
   vault stored meanwhile (it is re-sent by the client; harmless).
d. SQLite is tiny (`db.sqlite3` 278 KB, volume 1 % used) — the migration is milliseconds.
e. `/vaultwarden backup` (built into the binary, `src/main.rs` @1.37.4) does
   `VACUUM INTO '/data/db_<UTC>.sqlite3'` over a read-only connection — a consistent, online
   copy. §3.2 uses it as the named pre-upgrade restore point.

### 1.4 Security driver (detail NOT in this file)

The upstream release is also flagged by upstream as security-relevant. Per
`docs/sops/vulnerability-disclosure.md` the specifics stay off this public file. There is no
security finding for it yet (`policy-cli.py finding list --grep vaultwarden` shows only the
version rows and two AR-029 scanner rows, 2026-10-07). **Coordinator action:** record one with
`policy-cli.py finding add` and set `security_ref:` here; it argues for the earliest attended
slot or an operator NOW run rather than a far-out Sunday.

### 1.5 Verdict on the hold

Mostly a false positive for *risk*: every upgrade note is N/A to our config, and the migration
is additive and rollback-compatible. It is NOT a false positive for *autonomy*: the release
removes client-facing behaviour (§1.2) on the household credential store, so it stays
HUMAN-GATED (operator GO, attended — the operator also does the §4.6 real login).

## 2) Pre-checks

Run from `/Users/mu/code/cberg-home-nextgen` (zsh on the Mac mini).

```bash
cd /Users/mu/code/cberg-home-nextgen

# 2.1 premises (the run-time gate) — ALL must PASS
.venv/bin/python3 runbooks/plan-premises.py vaultwarden-1.37.4

# 2.2 target tag still published (guards a yanked/re-pushed tag -> ImagePullBackOff)
curl -s https://hub.docker.com/v2/repositories/vaultwarden/server/tags/1.37.4 \
  | python3 -c "import sys,json; d=json.load(sys.stdin); a=[i['architecture'] for i in d.get('images',[])]; print('TAG_OK' if d.get('name')=='1.37.4' and 'amd64' in a else 'TAG_MISSING', a)"
# PASS: TAG_OK   FAIL prints TAG_MISSING

# 2.3 PR #242 still the exact one-line diff and green
gh pr diff 242 | grep -c '^[-+] *tag: "1.37.[34]"$'      # PASS: 2
gh pr checks 242                                        # PASS: every row "pass"

# 2.4 pod healthy, no restarts; record the pod name (it must CHANGE in §4.1)
kubectl -n office get pods -l app.kubernetes.io/name=vaultwarden \
  -o 'custom-columns=N:.metadata.name,READY:.status.containerStatuses[0].ready,RESTARTS:.status.containerStatuses[0].restartCount,NODE:.spec.nodeName'
# PASS: exactly one pod, READY true

# 2.4b no admin-panel config.json overriding env (exec is refused in premises, so it lives here)
kubectl -n office exec deploy/vaultwarden -- sh -c 'test -e /data/config.json && echo CONFIG_JSON_PRESENT || echo no-config-json'
# PASS: no-config-json (measured 2026-10-07). CONFIG_JSON_PRESENT -> grep it for experimental_client_feature_flags /
# duo_use_iframe before proceeding; a removed flag there must be cleared in the admin panel first.

# 2.5 BASELINE workspace (mode 700: it will hold a copy of the credential DB; deleted in §4.8)
B=$(mktemp -d /tmp/vw-1374.XXXXXX); chmod 700 "$B"; echo "B=$B"
H=$(kubectl -n office get httproute vaultwarden -o jsonpath='{.spec.hostnames[0]}'); echo "$H" > "$B/host"
curl -s -m 10 "https://$H/api/version" | tee "$B/version-before"; echo
# PASS: "1.37.3"
kubectl -n office exec deploy/vaultwarden -- /vaultwarden --version | tee "$B/binver-before"
# measured 2026-10-07: Vaultwarden 1.37.3 / Web-Vault 2026.7.0

# 2.6 newest Longhorn backup CR name (contingency §5.C restores THIS one)
.venv/bin/python3 runbooks/longhorn-backup-age.py vaultwarden-data --max-hours 26 | tee "$B/longhorn-backup"
# PASS: "vaultwarden-data <N>h FRESH via backup-cr backup=backup-…"; record the backup name
```

## 3) Steps

### 3.1 Announce the gap
Tell the household: password manager sync pauses ~1 minute. Clients keep their offline vault.

### 3.2 Named pre-upgrade restore point (online VACUUM copy, on the PVC) + off-cluster copy for counting

```bash
B=<the dir printed in 2.5>
POD=$(kubectl -n office get pod -l app.kubernetes.io/name=vaultwarden -o jsonpath='{.items[0].metadata.name}')
kubectl -n office exec "$POD" -- /vaultwarden backup | tee "$B/backup-pre.out"
# PASS: "Backup to '/data/db_YYYYMMDD_HHMMSS.sqlite3' was successful"  (exit 0; prints "Backup failed." + exit 1 otherwise)
PRE=$(sed -n "s/^Backup to '\(.*\)' was successful$/\1/p" "$B/backup-pre.out"); echo "PRE=$PRE"
test -n "$PRE" || echo "ABORT: no backup path captured"
echo "$PRE" > "$B/pre-path"
kubectl -n office cp "$POD:$PRE" "$B/pre.sqlite3"
sqlite3 "$B/pre.sqlite3" 'PRAGMA integrity_check;'                       # PASS: ok
Q="select 'users',count(*) from users union all select 'ciphers',count(*) from ciphers union all select 'folders',count(*) from folders union all select 'attachments',count(*) from attachments union all select 'organizations',count(*) from organizations union all select 'users_organizations',count(*) from users_organizations union all select 'twofactor',count(*) from twofactor;"
sqlite3 -separator ' ' "$B/pre.sqlite3" "$Q" | tee "$B/counts-before"
# PASS: users >= 1 and ciphers >= 1 (an empty vault here means we are reading the wrong file — STOP)
sqlite3 "$B/pre.sqlite3" "select count(*) from __diesel_schema_migrations where version='20260902120000'; select count(*) from pragma_table_info('users') where name='key_id';" | tr '\n' ' ' | tee "$B/mig-before"; echo
# PASS: "0 0 "  (migration not yet applied; a "1 1" means something already ran 1.37.4 — STOP and investigate)
```

The SQL and the before/after `diff` were dry-run on a scratch SQLite with the upstream table
names (`users`, `ciphers`, `folders`, `attachments`, `organizations`, `users_organizations`,
`twofactor`, `__diesel_schema_migrations` — `src/db/schema.rs` @1.37.4) on macOS sqlite 3.51.0:
before `0 0`, after applying the upstream `up.sql` + version row `1 1`, counts diff silent,
`integrity_check` = `ok`.

### 3.3 GitOps change — merge Renovate PR #242 (preferred) or the identical hand edit

```bash
cd /Users/mu/code/cberg-home-nextgen
gh pr merge 242 --squash
git pull --ff-only
```

Fallback if the PR is gone/conflicted (identical one-line change; sed dry-run on a scratch copy
2026-10-07 produced exactly `42c42 <  tag: "1.37.3" --- >  tag: "1.37.4"`):

```bash
sed -i '' 's/^\([[:space:]]*tag: \)"1\.37\.3"$/\1"1.37.4"/' kubernetes/apps/office/vaultwarden/app/helmrelease.yaml
git diff --stat   # exactly 1 file, 1 insertion, 1 deletion
printf 'fix(vaultwarden): update vaultwarden/server 1.37.3 -> 1.37.4\n\nPlan: runbooks/maintenance/plans/vaultwarden-1.37.4.md\n' > /tmp/vw-msg.txt
git commit --only kubernetes/apps/office/vaultwarden/app/helmrelease.yaml -F /tmp/vw-msg.txt
git log -1 --format=%s     # must be YOUR subject (shared-worktree message-swap race)
git show --stat HEAD       # exactly the one file
git push
```

Let the GitHub webhook reconcile (no manual `flux reconcile` — application-update.md). Watch:

```bash
kubectl -n office get helmrelease vaultwarden -w     # until Ready True with the new revision (Ctrl-C)
```

Expected: the old pod terminates (Recreate), the new one starts; startup runs the
`add_key_id` migration; readiness (`/alive`) green within ~30 s. The HR has
`upgrade.remediation.retries: 3`: a pod that never goes Ready makes Helm fail and, after retries,
roll back to 1.37.3 by itself — compatible per §1.3c, but then go to §5.A to make git agree.

## 4) Verification

Run 2 min after the HR is Ready. `B`, `H` from §2.5.

```bash
# 4.1 one NEW pod, Ready, 0 restarts, live image is the target
kubectl -n office get pods -l app.kubernetes.io/name=vaultwarden \
  -o 'custom-columns=N:.metadata.name,IMG:.spec.containers[0].image,READY:.status.containerStatuses[0].ready,RESTARTS:.status.containerStatuses[0].restartCount'
# PASS: exactly one pod, name != the §2.4 name, IMG vaultwarden/server:1.37.4, READY true, RESTARTS 0
# (rollout-status alone green-lights the OLD generation — feedback_rollout_status_old_generation)

# 4.2 the running SERVER reports the target
curl -s -m 10 "https://$H/api/version"; echo
# PASS: "1.37.4"   FAIL: "1.37.3" (old pod still serving / Helm auto-rolled back) or a 503 body
kubectl -n office exec deploy/vaultwarden -- /vaultwarden --version
# PASS: "Vaultwarden 1.37.4" (record the Web-Vault line next to the §2.5 one)

# 4.3 no migration / startup error in the log (case-insensitive; Rocket+diesel log mixed case)
kubectl -n office logs deploy/vaultwarden --since=10m | grep -i -E 'error|panic|migration|failed' || echo NO_ERRORS
# PASS: NO_ERRORS. A failed migration prints "Error running migrations" and panics -> pod would
# also restart (4.1 RESTARTS > 0); a feature-flag misconfig prints a warning naming the flag.
```

**CONTENTS ASSERTION: the vault's data survived the migration unchanged and the migration
actually ran on THIS database** — measured by a post-upgrade VACUUM copy, compared to the §3.2
baseline:

```bash
POD=$(kubectl -n office get pod -l app.kubernetes.io/name=vaultwarden -o jsonpath='{.items[0].metadata.name}')
kubectl -n office exec "$POD" -- /vaultwarden backup | tee "$B/backup-post.out"
POST=$(sed -n "s/^Backup to '\(.*\)' was successful$/\1/p" "$B/backup-post.out"); test -n "$POST" || echo "FAIL: no post backup"
kubectl -n office cp "$POD:$POST" "$B/post.sqlite3"
sqlite3 "$B/post.sqlite3" 'PRAGMA integrity_check;'                        # 4.4a PASS: ok
Q="select 'users',count(*) from users union all select 'ciphers',count(*) from ciphers union all select 'folders',count(*) from folders union all select 'attachments',count(*) from attachments union all select 'organizations',count(*) from organizations union all select 'users_organizations',count(*) from users_organizations union all select 'twofactor',count(*) from twofactor;"
sqlite3 -separator ' ' "$B/post.sqlite3" "$Q" > "$B/counts-after"
diff "$B/counts-before" "$B/counts-after" && echo COUNTS_SAME              # 4.4b PASS: COUNTS_SAME
sqlite3 "$B/post.sqlite3" "select count(*) from __diesel_schema_migrations where version='20260902120000'; select count(*) from pragma_table_info('users') where name='key_id';" | tr '\n' ' '; echo
# 4.4c PASS: "1 1 "
```

What each gate guards against: 4.4a a corrupted file (`integrity_check` prints the damaged
pages instead of `ok`); 4.4b a re-initialised/empty DB (e.g. the pod came up on a fresh
`emptyDir` or a wrong mount: counts drop to `users 0` / `ciphers 0`, and `diff` prints them),
or rows lost in the migration — a ciphers delta while family members are actively editing is
explainable only by `select count(*) from ciphers where updated_at > '<§3.2 UTC time>'`, check
that before calling it loss; 4.4c the shape-green failure where the new binary runs but against a
different DB file — then the version row and column are absent (`0 0`). Baseline today: the
§3.2 read must show `0 0` (premise-level STOP otherwise), so 4.4c cannot pass by accident.

```bash
# 4.5 removed route gone, current login pre-step intact (proves the NEW router serves, and the
#     DB-backed login path answers). Measured 2026-10-07 on 1.37.3: both 200.
curl -s -o /dev/null -w 'legacy %{http_code}\n' -m 10 -X POST "https://$H/api/accounts/prelogin" -H 'content-type: application/json' -d '{"email":"nobody@example.invalid"}'
curl -s -o /dev/null -w 'current %{http_code}\n' -m 10 -X POST "https://$H/identity/accounts/prelogin" -H 'content-type: application/json' -d '{"email":"nobody@example.invalid"}'
# PASS: "legacy 404" and "current 200". FAIL modes: legacy 200 = old binary; current non-200 = login broken for every client.
```

**4.6 Real login (operator, attended — the auth-class contents assertion):** in a private
browser window open `https://<host>/` (Homepage → Office → Vaultwarden), log in with a real
account incl. 2FA, open one item, confirm it decrypts; on one phone, pull-to-sync and confirm
"Last sync" updates. FAIL: login error / spinner / empty vault. (The DB counts above cannot
prove the client↔server crypto contract still works; this can.)

**CONTROL lines** (instrument checks; Prometheus via
`kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 2; …; kill $PF`):

CONTROL: metric probe_success — `min_over_time(probe_success{probe_component="vaultwarden"}[5m])` read ≥ 5 min after the roll must be `1` (one series, instance = the /alive URL; measured 2026-10-07: 1 series, value 1). It goes 0 if DNS, Envoy, the route or the new Rocket server fails; an EMPTY result is a FAIL (instrument gone), not a pass.
CONTROL: metric kube_deployment_status_replicas_available — `kube_deployment_status_replicas_available{namespace="office",deployment="vaultwarden"}` = 1 (measured 2026-10-07: 1).
CONTROL: alertname VaultwardenHttpProbeFailing — not firing 10 min after the roll (repo rule in `kubernetes/apps/monitoring/kube-prometheus-stack/app/vaultwarden-alerts.yaml`, `for: 5m`; a ~1 min Recreate gap does not reach it — if it fires, the server is down, not rolling).
CONTROL: alertname VaultwardenHttpProbeAbsent — not firing (guards the probe_success gate against reading an absent series as healthy).

```bash
# 4.7 soak: re-read 4.2 + the probe_success CONTROL 30 min after the roll; and the next morning
#     confirm the 03:00 Longhorn backup of vaultwarden-data is Completed:
.venv/bin/python3 runbooks/longhorn-backup-age.py vaultwarden-data --max-hours 26

# 4.8 hygiene — ONLY after 4.1-4.7 pass and the soak is clean: delete the off-cluster DB copies.
#     (The two db_*.sqlite3 VACUUM copies stay ON the PVC as restore points; remove them in a
#     later window once a post-upgrade nightly backup exists — they are ~300 KB each.)
rm -rf "$B"
```

## 5) Rollback

Decide by symptom. In every branch the household's clients keep their offline vault copy.

### 5.A Image/app regression, data intact (4.1/4.2/4.3/4.5/4.6 fail; 4.4 passes) — plain git revert

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <the §3.3 commit sha>
git log -1 --format=%s && git show --stat HEAD     # your revert, one file
git push
```
1.37.3 boots on the migrated DB (§1.3c: unknown applied migration ignored; extra nullable
column invisible). Confirm: `curl -s https://$H/api/version` → `"1.37.3"`; one pod
`vaultwarden/server:1.37.3` Ready, 0 restarts; re-run the §4.4 count block → COUNTS_SAME vs
`$B/counts-before` (4.4c will read `1 1` — expected, the column stays); probe CONTROL back to 1;
operator login works. If Helm already auto-rolled back (HR remediation), still push the revert
so git and cluster agree.

### 5.B Database damaged (4.4a not `ok`, or 4.4b shows rows LOST) — restore the §3.2 VACUUM copy

Break-glass, operator present. Steps 2 and 4 are direct cluster actions on the PVC (no GitOps
path exists for SQLite file contents); state that in the window report.

1. Revert the image AND stop the app in one commit, so nothing writes the DB:
   ```bash
   git revert --no-commit <the §3.3 commit sha>
   # add `replicas: 0` under controllers.main (2-space YAML, same level as `annotations:`)
   $EDITOR kubernetes/apps/office/vaultwarden/app/helmrelease.yaml
   git commit --only kubernetes/apps/office/vaultwarden/app/helmrelease.yaml -m "revert(vaultwarden): 1.37.4 + scale 0 for DB restore"
   git log -1 --format=%s && git push
   kubectl -n office get pods -l app.kubernetes.io/name=vaultwarden   # wait: No resources found
   ```
2. Swap the DB from a helper pod mounting the same RWO PVC (as uid 1000, like the app):
   ```bash
   PRE=$(cat "$B/pre-path")      # e.g. /data/db_20261010_071500.sqlite3
   kubectl -n office run vw-restore --image=vaultwarden/server:1.37.3 --restart=Never \
     --overrides='{"spec":{"securityContext":{"runAsUser":1000,"runAsGroup":1000,"fsGroup":1000},"containers":[{"name":"vw-restore","image":"vaultwarden/server:1.37.3","command":["sleep","3600"],"volumeMounts":[{"name":"d","mountPath":"/data"}]}],"volumes":[{"name":"d","persistentVolumeClaim":{"claimName":"vaultwarden-data"}}]}}'
   kubectl -n office wait pod/vw-restore --for=condition=Ready --timeout=120s
   kubectl -n office exec vw-restore -- sh -c "cp -p /data/db.sqlite3 /data/db.sqlite3.broken.\$(date -u +%Y%m%d_%H%M%S) && cp -p '$PRE' /data/db.sqlite3 && rm -f /data/db.sqlite3-wal /data/db.sqlite3-shm && ls -la /data"
   kubectl -n office delete pod vw-restore
   ```
3. Remove `replicas: 0` again (commit `--only`, verify subject, push).
4. Confirm: 1.37.3 pod Ready; §4.4 count block on a fresh backup → identical to
   `$B/counts-before`; 4.4c reads `0 0` (pre-migration file is back); operator login.
   Data written between §3.2 and the restore (minutes, during the window) is lost — say so.

### 5.C PVC/volume itself unusable — Longhorn restore

Restore the backup named in `$B/longhorn-backup` (§2.6) per `docs/sops/backup.md`
("Use restore workflow and rebind PV/PVC"). The PV `vaultwarden-data` has an immutable
`volumeHandle: vaultwarden-data`, so the restored Longhorn volume must carry that exact name
(delete/rename the broken volume first, after `kubectl get volume -n storage vaultwarden-data`
confirms its state) — this is the static-volume procedure in `docs/sops/longhorn.md`; the CR
is applied by hand, Flux owns only `pv.yaml` + `pvc.yaml`. Loses up to ~1 day of vault edits
(clients re-push nothing automatically) — escalate to the operator before starting.

## 6) Interference notes

- **HUMAN-GATED by design** (`capability_change: true`): removed API routes, removed client
  flags, newer web vault — user-visible. Needs an operator GO and an attended window; the
  operator also performs §4.6. Do not set it `false` to reach SD-10/SD-11: feature loss is
  exactly the case those exclude. Runs in ~30 min; no reboot; single pod.
- **conflicts_with** carries: `app-template-5.2.1` (edits this very file and asserts this pod
  does NOT roll — run these on different nights, either order; whichever lands second must
  rebase its file edit), `kube-prometheus-stack-91.9.0` (our CONTROLs read Prometheus),
  `coredns-1.48.2` and `chart-patches-coredns-reloader-blackbox` (both read/roll the
  `http-vaultwarden` probe chain — our Recreate gap fails their gate, their DNS/exporter roll
  fails ours), `nextcloud-fleet-35.0.1` (office-wide Alertmanager silence would hide
  `VaultwardenHttpProbe*`), `helm-drift-detection` and `flux-oci-chart-sources` (both rewrite
  this HelmRelease's spec). **Reciprocity is owed**: none of those plans lists
  `vaultwarden-1.37.4` yet — the coordinator should add it on their side (`--validate` does not
  check reciprocity).
- `office` namespace co-tenants (sure, nextcloud, penpot, paperless, affine, mealie, …) are
  not touched: separate pods, PVCs and DBs; vaultwarden shares no database, cache or secret with
  them. Reloader watches `vaultwarden-secret`; this plan does not touch the Secret, so no
  second roll.
- **Do not run inside 02:00-03:30 local**: global `filesystem-trim` (02:00), `snapshot-cleanup`
  (02:30) and `daily-backup-all-volumes` (03:00) act on `vaultwarden-data`; a Longhorn backup
  snapshot racing the migration is harmless for SQLite-in-WAL but muddies §5.C's restore point.
  The attended day windows avoid this automatically.
- No shared infra is restarted. Envoy, CoreDNS, cert-manager, Longhorn engine: untouched.
- The pre-upgrade restore point `/data/db_<UTC>.sqlite3` stays on the PVC (and therefore inside
  every later Longhorn backup). That is intended; it is the same data the live DB holds.
