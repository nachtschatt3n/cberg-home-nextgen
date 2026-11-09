---
plan_id: vaultwarden-1.37.5
component: vaultwarden                # HelmRelease office/vaultwarden (bjw-s app-template 5.3.0), image vaultwarden/server
pr: 242                               # Renovate "fix(container): update vaultwarden/server ( 1.37.3 → 1.37.5 )" — OPEN, 4/4 checks SUCCESS (2026-11-08)
kind: image
current: "1.37.3"                     # MEASURED live 2026-11-08: deploy image vaultwarden/server:1.37.3 (digest sha256:1587c45f…70e0),
                                      # GET /api/version -> "1.37.3", `/vaultwarden --version` -> 1.37.3 / Web-Vault 2026.7.0
target: "1.37.5"                      # Docker Hub tag pushed 2026-11-01T22:14Z, manifest-list digest
                                      # sha256:4fe17f415f90087377d37c755e0ea3cf189dcc6794e49cdd2a9adbb4937d9e1f, amd64 present;
                                      # GitHub release 1.37.5 prerelease=false, newest (measured 2026-11-08)
update_type: patch
risk: low                             # technical risk low: TWO additive SQLite migrations (§1.3), every upgrade note N/A to our
                                      # env (§1.1). Blast radius if wrong is HIGH (household credential store) — carried by
                                      # capability_change/HUMAN-GATED + 3 backups, not by inflating risk.
est_duration_min: 30                  # 8 pre-checks/baselines, 3 edit+commit+push, ~4 reconcile (Recreate, 1 pod), 10 verification
                                      # incl. operator login, 5 buffer
needs_reboot: false
touches:
  namespaces: [office]
  resources:                          # every object verified to EXIST live 2026-11-08 (kubectl get)
    - helmrelease/vaultwarden         # the only object this plan EDITS (values.controllers.main.containers.main.image.tag)
    - deployment/vaultwarden          # pod template image changes -> ONE pod roll; strategy Recreate (verified live)
    - pvc/vaultwarden-data            # RWO longhorn-static (PV/volume vaultwarden-data); SQLite db.sqlite3 migrated in place
                                      # (+users.key_id, +org_policies.revision_date) and a pre-upgrade VACUUM copy written next to it (§3.2)
    - httproute/vaultwarden           # unchanged spec; serves 503 during the ~30-60 s Recreate gap
  shared:
    - monitoring                      # §4 reads Prometheus (probe_success / kube-state-metrics / ALERTS)
    - credentials                     # household password manager: every family client loses sync for the roll gap
depends_on: []
conflicts_with:
  - redis-fleet-8.10.3                # reciprocal (2026-11-02 sweep): it lists vaultwarden-1.37.4 -> needs vaultwarden-1.37.5 on its side (§6)
  - helm-drift-detection              # adds spec.driftDetection to every HR incl. helmrelease/vaultwarden (same object)
  - flux-oci-chart-sources            # rewrites the bjw-s chart source block of this HR (same spec.chart block)
exclusive: false
security_ref: F-3ee3a4fa              # Trivy "newer tag available" row; upstream app-level fixes tracked on F-e5e30871 (§1.4)
capability_change: true               # NOT a same-behaviour bump: upstream (cumulative 1.37.4+1.37.5) removes API routes (legacy
                                      # register/prelogin), breaks `bw send receive` for CLI <= 2026.4.2, removes 12 client feature
                                      # flags and the Duo iframe prompt, changes org-member/permission behaviour, tightens config
                                      # validation, and ships web vault 2026.7.0 -> 2026.10.1 (§1.2). Nothing we RUN uses the removed
                                      # parts (§1.1) but feature loss for a family client is what SD-11 reserves for a human.
rollback_class: git-revert            # MEASURED from upstream code (§1.3c): both migrations only ADD columns (one nullable, one with a
                                      # constant DEFAULT); diesel_migrations 2.3.2 ignores applied versions the old binary does not
                                      # embed, so 1.37.3 boots on the migrated DB. Data fallback (§5.B/§5.C) is a named VACUUM copy
                                      # + the nightly Longhorn backup — a contingency, not the rollback path.
finding_refs: [F-68aca77f]            # version finding "vaultwarden: image vaultwarden/server 1.37.3 → 1.37.5 (patch)"
                                      # (F-11bb688f = the separate chart leg, NOT this plan; F-e5e30871 = plan-lane security row)
review: ready-for-go@2026-11-08   # plan-reviewer 2026-11-08: needs-fix (4.3 absence gate without a positive control; dangling 1.37.4 refs), both fixed and spot-verified (banner grep prints 1 on the live pod); HUMAN-GATED, GO at the window
premises:
  - id: live-image-is-1.37.3
    why: >-
      The plan's rollback target and the "migrations have not run yet" baseline both assume the
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
      must never open the same SQLite file. Verified Recreate on 2026-11-08.
    run: kubectl get deploy vaultwarden -n office -o jsonpath='{.spec.strategy.type}'
    expect_exact: "Recreate"
  - id: no-removed-flag-env
    why: >-
      Upstream (1.37.4): if EXPERIMENTAL_CLIENT_FEATURE_FLAGS lists a removed flag, admin-panel saves fail;
      DUO_USE_IFRAME is now ignored; IP_HEADER=X-Forwarded-For semantics changed (rightmost untrusted);
      DATABASE_URL would mean we are not on the SQLite file §3.2 backs up. None may be set on the
      Deployment (measured 2026-11-08: 0). The /data/config.json half (admin-panel overrides) needs exec,
      which premises refuse — it is §2.4b.
    run: kubectl get deploy vaultwarden -n office -o jsonpath='{range .spec.template.spec.containers[0].env[*]}{.name}{"\n"}{end}' | grep -c -x -e EXPERIMENTAL_CLIENT_FEATURE_FLAGS -e DUO_USE_IFRAME -e IP_HEADER -e DATABASE_URL
    expect_exact: "0"
  - id: nightly-backup-exists
    why: >-
      Contingency §5.C restores the newest Completed Longhorn backup. Existence only — plan-premises.py
      refuses python3, so FRESHNESS is the §2.6 longhorn-backup-age.py gate.
    run: kubectl get backups.longhorn.io -n storage -l backup-volume=vaultwarden-data -o jsonpath='{.items[*].status.state}'
    expect_contains: Completed
status: vetted
window: sun-attended:2026-12-06   # fallback sat-attended:2026-12-12; n8n 60 min + this 30 min fits the 180-min Sunday budget, namespaces disjoint
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/backup.md
  - docs/sops/longhorn.md
  - docs/sops/longhorn-rwo-multi-attach.md
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/vulnerability-disclosure.md
generated: "2026-11-08"
---

# vaultwarden: image 1.37.3 -> 1.37.5 (two additive SQLite migrations; API/flag removals N/A to our config)

Retarget of `vaultwarden-1.37.4` (superseded; that plan never executed — aborted 2026-10-22 on a
too-strict `ciphers>=1` gate, since relaxed). Renovate re-targeted PR #242 from 1.37.4 to 1.37.5, so
this plan covers the **cumulative** 1.37.3 -> 1.37.5 jump: 1.37.4 notes + migration AND 1.37.5 notes + migration.

## 1) Summary & why held

`office/vaultwarden` is the household password manager: bjw-s app-template 5.3.0, one
Deployment (`strategy: Recreate`, 1 replica), image `vaultwarden/server:1.37.3`, **SQLite** at
`/data/db.sqlite3` on the RWO `longhorn-static` volume `vaultwarden-data` (10 Gi, Bound, 2 Longhorn replicas,
nightly Longhorn backup via `storage/daily-backup-all-volumes` @ 23:00 UTC; 9 Completed backups, newest 19.4 h old on
2026-11-08). Exposed only on `envoy-internal` (HTTPRoute `office/vaultwarden`, `sectionName: https`),
Homepage-registered, **no Authentik/SSO in front** (vaultwarden does its own auth; no SSO env set). Blackbox probe
`monitoring/http-vaultwarden` hits `/alive` through DNS -> Envoy -> route. Renovate PR #242 is a one-line tag
bump (`gh pr diff 242`: `-tag: "1.37.3"` / `+tag: "1.37.5"`), 4/4 checks SUCCESS. Answers finding `F-68aca77f`.

**Why held:** auto-update gate G3 — both upstream releases carry an **"Upgrade notes"** section (GitHub releases
`dani-garcia/vaultwarden` tags `1.37.4` 2026-10-05 and `1.37.5` 2026-11-01, via `gh api repos/dani-garcia/vaultwarden/releases/tags/<tag>`).

### 1.1 The upgrade notes, quoted, with our exposure (live-measured 2026-11-08)

| Upstream note (quoted/condensed) | Applies to us? | Evidence |
|---|---|---|
| 1.37.4 "**Reverse proxies:** with `IP_HEADER=X-Forwarded-For`, the client IP is now the rightmost address not in `IP_HEADER_TRUSTED_PROXIES` (it used to be the leftmost)." | **No.** We do not set `IP_HEADER` (default `X-Real-IP`); the XFF path is not taken. Deployment env list = ADMIN_TOKEN, DOMAIN, PORT, SMTP_* and the Reloader marker only. | premise `no-removed-flag-env` (=0) |
| 1.37.5 "**Web vault:** the bundled web vault is now v2026.10.1. If you serve your own web vault older than v2026.7.1, you might have compatibility issues." | **No.** We serve the **bundled** vault: no `WEB_VAULT_FOLDER`/`WEB_VAULT_ENABLED` env, no `/web-vault` mount (Deployment env + `ls /data` show none); live `--version` prints `Web-Vault 2026.7.0` (the bundled one in 1.37.3). It will print 2026.10.1 after. | env list; `§2.5`/`§4.2` Web-Vault line |
| 1.37.5 "**Configuration:** invalid values now stop startup with an error" (numeric options tighter: e.g. >65535 for `LOGIN_RATELIMIT_MAX_BURST`, `TRASH_AUTO_DELETE_DAYS`, `EVENTS_DAYS_RETAIN`, `SMTP_TIMEOUT`; >255 for `EMAIL_ATTEMPTS_LIMIT`; rate-limit/DB timeout options >= 1; cron options must be empty/valid)." | **No, but it is the one note that could hard-fail startup, so it is gated.** Our only numeric/cron options are `PORT=80` and `SMTP_PORT=587` (valid); no rate-limit, retain, timeout, or cron option is set; `/data/config.json` absent (§2.4b). A violation shows as a crash-looping pod (§4.1 RESTARTS) and an error in §4.3. | env dump 2026-11-08 |
| 1.37.4 "**Sends:** `bw send receive` on CLI 2026.4.2 and older no longer works." | **Not by anything we run** (no `bw` CLI consumer in repo, no Bitwarden-backed ClusterSecretStore). An old CLI on a family laptop would lose Send-receive -> capability change. | repo grep 2026-10-07 |
| 1.37.4 "**Feature flags:** … removed … If `EXPERIMENTAL_CLIENT_FEATURE_FLAGS` still lists one of them, startup logs a warning and saving admin-panel settings fails." | **No.** Env unset; no `/data/config.json`. | premise + §2.4b |
| 1.37.4 "**Duo:** `DUO_USE_IFRAME` removed and ignored." | **No.** Not set. | premise |
| 1.37.4 "**Custom templates:** new email template `email/recover_twofactor`." | **No action.** No `templates/` dir in `/data` (`ls /data` 2026-11-08: attachments, db files, icon_cache, rsa_key.pem, sends, tmp). | `ls /data` |
| 1.37.4 "legacy `POST /identity/accounts/register` and `POST /api/accounts/prelogin` removed. No current client uses them." | Route removal — used as a POSITIVE gate in §4.5 (legacy 200 today, must 404 after). Verified in source: at tag 1.37.5 `src/api/core/accounts.rs` no longer registers `post_prelogin`; `src/api/identity.rs` keeps `/accounts/prelogin` (+ new `/accounts/prelogin/password`). 1.37.3 had both. | `gh api …contents/src/api/…?ref=1.37.3 / 1.37.5`; live probe: legacy 200, current 200 |
| 1.37.4 MariaDB/MySQL TLS on Alpine | **No.** SQLite, Debian image. | no `DATABASE_URL` |

### 1.2 Behaviour changes not in "Upgrade notes" (why `capability_change: true`)

From the release bodies: web vault 2026.8/2026.9/2026.10 support (emergency-access and account-recovery payloads,
2FA user-verification token for Authenticator/Email/Duo, Fill Assist policy), new `revision_date` on org policies, new
client feature flags, configurable 2FA remember duration, fixes to org-member revocation/permissions and cipher/attachment
org checks, Rocket 0.5.2, WebSocket idle-close, delete-user now removes auth requests. These change what clients can do. None is
expected to hurt a current official client, but they are user-visible on the credential store, so the plan declares it.
The 1.37.5 "Note" says web vault 2026.7.1+ needs this server version to toggle two-step login methods and 2026.9.0+ needs it for
emergency-access takeover: the upgrade fixes client-side breakage rather than causing it.

### 1.3 Database migration — measured from upstream code, not assumed

a. `gh api repos/dani-garcia/vaultwarden/compare/1.37.3...1.37.5` lists exactly TWO new migrations per engine; for SQLite:
   1. `migrations/sqlite/2026-09-02-120000_add_key_id/up.sql` = `ALTER TABLE users ADD COLUMN key_id TEXT;` (nullable, no default, no backfill). `down.sql` empty.
   2. `migrations/sqlite/2026-10-07-120000_add_org_policy_revision_date/up.sql` = `ALTER TABLE org_policies ADD COLUMN revision_date DATETIME NOT NULL DEFAULT '1970-01-01 00:00:00'; UPDATE org_policies SET revision_date = CURRENT_TIMESTAMP;`. `down.sql` empty.
   Only 1.37.5 adds #2 (`compare/1.37.4...1.37.5` shows 6 migration files = 3 engines x up/down).
   Neither drops, renames or rewrites existing data; the `UPDATE` only touches the new column (if `organizations`/`org_policies` are empty, as §3.2's counts will show, it is a no-op).
b. Migrations run automatically at startup (`src/db/mod.rs` -> `run_pending_migrations`), diesel 2.3.14 / diesel_migrations 2.3.2 (Cargo.toml @1.37.5).
c. **Rollback compatibility (reasoned from code + SQL, not tested on a live 1.37.3 binary):** `diesel_migrations` 2.3.2 `pending_migrations`
   removes each applied version from the binary's embedded set, so an applied version the old binary does not embed is ignored, not an error;
   1.37.3's diesel schema uses explicit column lists, and any 1.37.3 INSERT into `org_policies` omits `revision_date`, which has a constant
   `DEFAULT`, so it still succeeds. `users.key_id` is nullable. ⇒ reverting the image tag is a valid rollback without a data restore.
   Lost on revert: any `key_id`/`revision_date` values written meanwhile (clients re-send; harmless unless org policies exist; §3.2 counts show).
d. SQLite is tiny (`db.sqlite3` ~280 KB, volume ~1 % used) — migrations take milliseconds. DB is in WAL mode (`db.sqlite3-wal/-shm` present live): use the online
   `/vaultwarden backup` (VACUUM INTO, read-only connection), never a raw file copy.
e. The aborted 2026-10-22 run left a VACUUM copy `/data/db_20261022_184225.sqlite3` on the PVC (measured). It is a harmless older restore point; §3.2 writes a fresh, named one.

### 1.4 Security driver (detail NOT in this file)

Both upstream releases lead with app-level security fixes. Per `docs/sops/vulnerability-disclosure.md` the specifics stay off this
public file; they live on the DB records referenced by `security_ref` (F-3ee3a4fa) and the plan-lane row F-e5e30871 (re-checked
2026-11-08 via `policy-cli.py finding list --grep vaultwarden`). `finding_refs` carries the version finding F-68aca77f. The security
driver argues for the earliest slot. (F-f734b0ed is the AR-029 acceptance row for the *current* image; it is independent of this bump.)

### 1.5 Verdict on the hold

Mostly a false positive for *risk*: every upgrade note is N/A to our config and both migrations are additive and rollback-compatible. It is NOT a
false positive for *autonomy*: the cumulative release removes client-facing behaviour (§1.2) on the household credential store, so it stays
HUMAN-GATED (operator GO required; the §4.6 real login is an operator step). No irreversible migration found, so no extra gate beyond capability_change.

## 0) RUN RULES (carried from vaultwarden-1.37.4's 2026-10-22 abort)

- ABORT (change nothing, report) if ANY premise, 2.2, 2.3, 2.5 or 2.6 fails, or §3.2 shows `mig-before` != `0 0 0`.
  Everything up to and including 3.2 is non-mutating for the app (3.2 only writes a VACUUM copy).
- **Empty vault is expected** (operator 2026-10-23: vault is intentionally unpopulated until the Bitwarden migration): `ciphers = 0` is NOT a wrong-file
  signal. The wrong-file signal is `users = 0` or no `__diesel_schema_migrations` rows. Do not re-add a `ciphers >= 1` gate.
- Section 4.6 (human login) is not a blocker unattended: run 4.1-4.5 + CONTROLs and leave 4.6 for the operator. FAIL of 4.1-4.5 -> execute 5.A.
  A failed 4.4a/4.4b -> do NOT auto-restore (5.B is operator break-glass): report, leave 1.37.3 reverted via 5.A, keep `$B` (mode 700, holds a DB copy).
- Never print DB contents, tokens, or exported vault data; only counts and pass/fail strings. Do not log in with, create, or modify real accounts; no test account is created (§4.6 is read-only on real data by the operator).
- Do not run 22:00-23:30 UTC (Longhorn trim/cleanup/backup, see §6).

## 2) Pre-checks

Run from `/Users/mu/code/cberg-home-nextgen` (zsh on the Mac mini).

```bash
cd /Users/mu/code/cberg-home-nextgen

# 2.1 premises (the run-time gate) — ALL must PASS
.venv/bin/python3 runbooks/plan-premises.py vaultwarden-1.37.5

# 2.2 target tag AND digest still published (guards a yanked/re-pushed tag -> ImagePullBackOff or a different image)
curl -s https://hub.docker.com/v2/repositories/vaultwarden/server/tags/1.37.5 \
  | python3 -c "import sys,json; d=json.load(sys.stdin); a=[i['architecture'] for i in d.get('images',[])]; ok=d.get('name')=='1.37.5' and 'amd64' in a and d.get('digest')=='sha256:4fe17f415f90087377d37c755e0ea3cf189dcc6794e49cdd2a9adbb4937d9e1f'; print('TAG_OK' if ok else 'TAG_MISSING_OR_DIGEST_CHANGED', d.get('digest'), a)"
# PASS: TAG_OK   FAIL prints TAG_MISSING_OR_DIGEST_CHANGED (a re-pushed tag changes the digest: re-review before proceeding)

# 2.3 PR #242 still the exact one-line diff to 1.37.5 and green
gh pr diff 242 | grep -c '^[-+] *tag: "1.37.[35]"$'      # PASS: 2   (FAIL 0/other: Renovate re-targeted again -> re-plan)
gh pr diff 242 | grep -c '^+ *tag: "1.37.5"$'           # PASS: 1
gh pr checks 242                                        # PASS: every row "pass"
gh api repos/dani-garcia/vaultwarden/releases --jq '.[0]|.tag_name+" prerelease="+(.prerelease|tostring)'
# PASS: "1.37.5 prerelease=false". Anything newer = re-plan (a newer patch may have changed the notes).

# 2.4 pod healthy, no restarts; record the pod name (it must CHANGE in §4.1)
kubectl -n office get pods -l app.kubernetes.io/name=vaultwarden \
  -o 'custom-columns=N:.metadata.name,READY:.status.containerStatuses[0].ready,RESTARTS:.status.containerStatuses[0].restartCount,NODE:.spec.nodeName'
# PASS: exactly one pod, READY true

# 2.4b no admin-panel config.json overriding env (exec is refused in premises, so it lives here)
kubectl -n office exec deploy/vaultwarden -- sh -c 'test -e /data/config.json && echo CONFIG_JSON_PRESENT || echo no-config-json'
# PASS: no-config-json (measured 2026-11-08). CONFIG_JSON_PRESENT -> grep it for experimental_client_feature_flags /
# duo_use_iframe and for numeric options above the 1.37.5 limits before proceeding; fix in the admin panel first.

# 2.5 BASELINE workspace (mode 700: it will hold a copy of the credential DB; deleted in §4.8)
B=$(mktemp -d /tmp/vw-1375.XXXXXX); chmod 700 "$B"; echo "B=$B"
H=$(kubectl -n office get httproute vaultwarden -o jsonpath='{.spec.hostnames[0]}'); echo "$H" > "$B/host"
curl -s -m 10 "https://$H/api/version" | tee "$B/version-before"; echo
# PASS: "1.37.3"
kubectl -n office exec deploy/vaultwarden -- /vaultwarden --version | tee "$B/binver-before"
# measured 2026-11-08: Vaultwarden 1.37.3 / Web-Vault 2026.7.0
curl -s -o /dev/null -w 'alive %{http_code}\n' -m 10 "https://$H/alive"               # PASS: alive 200 (baseline for 4.1)
curl -s -o /dev/null -w 'legacy-before %{http_code}\n' -m 10 -X POST "https://$H/api/accounts/prelogin" -H 'content-type: application/json' -d '{"email":"nobody@example.invalid"}'
# PASS: legacy-before 200 (measured 2026-11-08). If it is already 404 the instrument for 4.5 is meaningless: STOP.

# 2.6 newest Longhorn backup CR name (contingency §5.C restores THIS one)
.venv/bin/python3 runbooks/longhorn-backup-age.py vaultwarden-data --max-hours 26 | tee "$B/longhorn-backup"
# PASS: "vaultwarden-data <N>h FRESH via backup-cr backup=backup-…"; record the backup name
# (2026-11-08: backup-64bead389996479e, 19.4 h). FAIL prints STALE / non-zero -> do not proceed without a fresh backup.
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
# PASS: users >= 1 AND the migration table has rows (we are reading the live DB). ciphers = 0 is EXPECTED (§0).
sqlite3 "$B/pre.sqlite3" "select count(*) from __diesel_schema_migrations;" | awk '$1>=1{print "MIGRATIONS_PRESENT"}'  # PASS: MIGRATIONS_PRESENT
MIG="select count(*) from __diesel_schema_migrations where version in ('20260902120000','20261007120000'); select count(*) from pragma_table_info('users') where name='key_id'; select count(*) from pragma_table_info('org_policies') where name='revision_date';"
sqlite3 "$B/pre.sqlite3" "$MIG" | tr '\n' ' ' | tee "$B/mig-before"; echo
# PASS: "0 0 0 "  (neither migration applied; any other value means something already ran 1.37.4/1.37.5 — STOP and investigate)
```

Dry-run 2026-11-08 on a scratch SQLite (macOS sqlite3 3.51) with the upstream table names and both upstream `up.sql` statements:
before `0 0 0 `, after `2 1 1 `; the `UPDATE` left 0 rows at the `1970-01-01` placeholder.

### 3.3 GitOps change — merge Renovate PR #242 (preferred) or the identical hand edit

```bash
cd /Users/mu/code/cberg-home-nextgen
gh pr merge 242 --squash
git pull --ff-only
```

Fallback if the PR is gone/conflicted (identical one-line change; BSD-sed dry-run on a scratch copy 2026-11-08 produced exactly
`42c42 <  tag: "1.37.3" --- >  tag: "1.37.5"`):

```bash
sed -i '' 's/^\([[:space:]]*tag: \)"1\.37\.3"$/\1"1.37.5"/' kubernetes/apps/office/vaultwarden/app/helmrelease.yaml
git diff --stat   # exactly 1 file, 1 insertion, 1 deletion
printf 'fix(vaultwarden): update vaultwarden/server 1.37.3 -> 1.37.5\n\nPlan: runbooks/maintenance/plans/vaultwarden-1.37.5.md\n' > /tmp/vw-msg.txt
git commit --only kubernetes/apps/office/vaultwarden/app/helmrelease.yaml -F /tmp/vw-msg.txt
git log -1 --format=%s     # must be YOUR subject (shared-worktree message-swap race)
git show --stat HEAD       # exactly the one file
git push
```

Let the GitHub webhook reconcile (no manual `flux reconcile` — application-update.md). Watch:

```bash
kubectl -n office get helmrelease vaultwarden -w     # until Ready True with the new revision (Ctrl-C)
```

Expected: the old pod terminates (Recreate), the new one starts; startup applies both migrations;
readiness (`/alive`) green within ~30 s. The HR has `upgrade.remediation.retries: 3`: a pod that never goes Ready makes Helm fail and,
after retries, roll back to 1.37.3 by itself — compatible per §1.3c, but then go to §5.A to make git agree.

## 4) Verification

Run 2 min after the HR is Ready. `B`, `H` from §2.5.

```bash
# 4.1 one NEW pod, Ready, 0 restarts, live image is the target
kubectl -n office get pods -l app.kubernetes.io/name=vaultwarden \
  -o 'custom-columns=N:.metadata.name,IMG:.spec.containers[0].image,READY:.status.containerStatuses[0].ready,RESTARTS:.status.containerStatuses[0].restartCount,DIGEST:.status.containerStatuses[0].imageID'
# PASS: exactly one pod, name != the §2.4 name, IMG vaultwarden/server:1.37.5, READY true, RESTARTS 0,
#       DIGEST contains a sha256 that is NOT 1587c45f… (the 1.37.3 digest). Rollout-status alone green-lights the OLD generation
#       (feedback_rollout_status_old_generation). Note: imageID is the per-arch digest (amd64 f8863ab2…), not the manifest-list digest.
# FAIL: RESTARTS > 0 / CrashLoopBackOff = migration or config-validation failure (see 4.3).

# 4.2 the running SERVER reports the target
curl -s -m 10 "https://$H/api/version"; echo
# PASS: "1.37.5"   FAIL: "1.37.3" (old pod still serving / Helm auto-rolled back) or a 503 body
kubectl -n office exec deploy/vaultwarden -- /vaultwarden --version
# PASS: "Vaultwarden 1.37.5" AND "Web-Vault 2026.10.1" (FAIL: Web-Vault still 2026.7.0 = old binary or a pinned WEB_VAULT_FOLDER)
curl -s -o /dev/null -w 'alive %{http_code}\n' -m 10 "https://$H/alive"                  # PASS: alive 200

# 4.3 no migration / startup / config error in the log (case-insensitive; Rocket+diesel log mixed case)
kubectl -n office logs deploy/vaultwarden | grep -c 'Version 1.37.5'
# PASS (positive control, must run first): 1. The startup banner is proven to emit (the 1.37.3 pod prints 'Version 1.37.3', count 1,
# measured 2026-11-08); 0 = the log is silent or the old/crashed pod answered, so the absence check below proves nothing: FAIL.
kubectl -n office logs deploy/vaultwarden | grep -i -E 'error|panic|migration|failed|invalid' || echo NO_ERRORS
# PASS: NO_ERRORS (whole pod log, no --since: the pod is minutes old and the healthy log is only the ~6-line banner). A failed migration prints "Error running migrations" and panics; a 1.37.5 config-validation failure prints
# an error naming the option and exits (pod restarts, 4.1 RESTARTS > 0); a feature-flag misconfig prints a warning naming the flag.
```

**CONTENTS ASSERTION: the vault's data survived both migrations unchanged and the migrations
actually ran on THIS database** — measured by a post-upgrade VACUUM copy, compared to the §3.2 baseline:

```bash
POD=$(kubectl -n office get pod -l app.kubernetes.io/name=vaultwarden -o jsonpath='{.items[0].metadata.name}')
kubectl -n office exec "$POD" -- /vaultwarden backup | tee "$B/backup-post.out"
POST=$(sed -n "s/^Backup to '\(.*\)' was successful$/\1/p" "$B/backup-post.out"); test -n "$POST" || echo "FAIL: no post backup"
kubectl -n office cp "$POD:$POST" "$B/post.sqlite3"
sqlite3 "$B/post.sqlite3" 'PRAGMA integrity_check;'                        # 4.4a PASS: ok
Q="select 'users',count(*) from users union all select 'ciphers',count(*) from ciphers union all select 'folders',count(*) from folders union all select 'attachments',count(*) from attachments union all select 'organizations',count(*) from organizations union all select 'users_organizations',count(*) from users_organizations union all select 'twofactor',count(*) from twofactor;"
sqlite3 -separator ' ' "$B/post.sqlite3" "$Q" > "$B/counts-after"
diff "$B/counts-before" "$B/counts-after" && echo COUNTS_SAME              # 4.4b PASS: COUNTS_SAME
MIG="select count(*) from __diesel_schema_migrations where version in ('20260902120000','20261007120000'); select count(*) from pragma_table_info('users') where name='key_id'; select count(*) from pragma_table_info('org_policies') where name='revision_date';"
sqlite3 "$B/post.sqlite3" "$MIG" | tr '\n' ' '; echo
# 4.4c PASS: "2 1 1 "
```

What each gate guards against: 4.4a a corrupted file (`integrity_check` prints the damaged pages instead of `ok`); 4.4b a
re-initialised/empty DB (pod came up on a fresh `emptyDir` or wrong mount: `users` drops to 0 and `diff` prints it) or rows
lost in migration — a delta while family members are actively editing is explainable only by `select count(*) from <table>
where updated_at > '<§3.2 UTC time>'`, check that before calling it loss (note: the empty-ciphers baseline makes a drop in
`users`/`twofactor` the load-bearing signal); 4.4c the shape-green failure where the new binary runs against a different DB
file — the version rows/columns are absent (`0 0 0`) — or only the first migration ran (`1 1 0`). The §3.2 read must have shown
`0 0 0`, so 4.4c cannot pass by accident.

```bash
# 4.5 removed route gone, current login pre-step intact (proves the NEW router serves, and the
#     DB-backed login path answers). Measured 2026-11-08 on 1.37.3: both 200.
curl -s -o /dev/null -w 'legacy %{http_code}\n' -m 10 -X POST "https://$H/api/accounts/prelogin" -H 'content-type: application/json' -d '{"email":"nobody@example.invalid"}'
curl -s -o /dev/null -w 'current %{http_code}\n' -m 10 -X POST "https://$H/identity/accounts/prelogin" -H 'content-type: application/json' -d '{"email":"nobody@example.invalid"}'
# PASS: "legacy 404" and "current 200". FAIL modes: legacy 200 = old binary; current non-200 = login broken for every client.
# (The probe email is a nonexistent address: no real account is touched; prelogin returns KDF params only.)
```

**4.6 Real login (operator step, non-blocking unattended — the auth-class contents assertion; no test account is created):** in a private
browser window open `https://<host>/` (Homepage → Office → Vaultwarden), log in with a real
account incl. 2FA, confirm the new web vault loads (Settings footer shows 2026.10.1) and the vault view opens (it may be empty, §0), and on one phone pull-to-sync and confirm
"Last sync" updates. FAIL: login error / spinner / client says server unsupported. (The DB counts cannot
prove the client↔server crypto contract still works; this can.)

**CONTROL lines** (instrument checks; Prometheus via
`kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 2; …; kill $PF`):

CONTROL: metric probe_success — `min_over_time(probe_success{probe_component="vaultwarden"}[5m])` read ≥ 5 min after the roll must be `1` (one series, instance = the /alive URL). It goes 0 if DNS, Envoy, the route or the new Rocket server fails; an EMPTY result is a FAIL (instrument gone), not a pass. Re-measure that exactly one series exists before the roll (it did on 2026-10-07; re-verify, the label set is the instrument).
CONTROL: metric kube_deployment_status_replicas_available — `kube_deployment_status_replicas_available{namespace="office",deployment="vaultwarden"}` = 1.
CONTROL: alertname VaultwardenHttpProbeFailing — not firing 10 min after the roll (rule in `kubernetes/apps/monitoring/kube-prometheus-stack/app/vaultwarden-alerts.yaml`, `for: 5m`; a ~1 min Recreate gap does not reach it — if it fires, the server is down, not rolling).
CONTROL: alertname VaultwardenHttpProbeAbsent — not firing (guards the probe_success gate against reading an absent series as healthy).

```bash
# 4.7 soak: re-read 4.2 + the probe_success CONTROL 30 min after the roll; and the next morning
#     confirm the 23:00 UTC Longhorn backup of vaultwarden-data is Completed:
.venv/bin/python3 runbooks/longhorn-backup-age.py vaultwarden-data --max-hours 26

# 4.8 hygiene — ONLY after 4.1-4.7 pass and the soak is clean: delete the off-cluster DB copies.
#     (The db_*.sqlite3 VACUUM copies — including the 2026-10-22 one — stay ON the PVC as restore points; remove them in a
#     later window once a post-upgrade nightly backup exists — they are ~300 KB each.)
[ -n "$B" ] && [ -d "$B" ] && rm -rf "$B"
```

Shell state: `$B` and `$H` (and `$POD`) exist only in the shell that ran §2.5. The window agent runs each tool call in a fresh
shell, so re-derive them every call: `B=` the `/tmp/vw-1375.*` dir recorded in §2.5 (`ls -d /tmp/vw-1375.*`), `H=$(cat "$B/host")`,
`POD=$(kubectl -n office get pod -l app.kubernetes.io/name=vaultwarden -o jsonpath='{.items[0].metadata.name}')`.

## 5) Rollback

Decide by symptom. In every branch the household's clients keep their offline vault copy.

### 5.A Image/app regression, data intact (4.1/4.2/4.3/4.5/4.6 fail; 4.4 passes) — plain git revert

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <the §3.3 commit sha>
git log -1 --format=%s && git show --stat HEAD     # your revert, one file
git push
```
1.37.3 boots on the migrated DB (§1.3c: unknown applied migrations ignored; extra columns invisible/defaulted). Confirm: `curl -s https://$H/api/version` → `"1.37.3"`; one pod
`vaultwarden/server:1.37.3` Ready, 0 restarts; re-run the §4.4 count block → COUNTS_SAME vs
`$B/counts-before` (4.4c will read `2 1 1` — expected, the columns stay); probe CONTROL back to 1;
operator login works. If Helm already auto-rolled back (HR remediation), still push the revert
so git and cluster agree. (§1.3c is derived from code, not a rehearsed boot — if 1.37.3 does NOT boot on the migrated DB, go straight to 5.B.)

### 5.B Database damaged or 1.37.3 refuses the migrated DB (4.4a not `ok`, 4.4b shows rows LOST, or 5.A pod crash-loops) — restore the §3.2 VACUUM copy

Break-glass, operator present. Steps 2 and 4 are direct cluster actions on the PVC (no GitOps
path exists for SQLite file contents); state that in the window report.

1. Revert the image AND stop the app in one commit, so nothing writes the DB:
   ```bash
   git revert --no-commit <the §3.3 commit sha>
   # add `replicas: 0` under controllers.main (2-space YAML, same level as `annotations:`)
   $EDITOR kubernetes/apps/office/vaultwarden/app/helmrelease.yaml
   git commit --only kubernetes/apps/office/vaultwarden/app/helmrelease.yaml -m "revert(vaultwarden): 1.37.5 + scale 0 for DB restore"
   git log -1 --format=%s && git push
   kubectl -n office get pods -l app.kubernetes.io/name=vaultwarden   # wait: No resources found
   ```
2. Swap the DB from a helper pod mounting the same RWO PVC (as uid 1000, like the app):
   ```bash
   PRE=$(cat "$B/pre-path")      # e.g. /data/db_20261110_071500.sqlite3
   kubectl -n office run vw-restore --image=vaultwarden/server:1.37.3 --restart=Never \
     --overrides='{"spec":{"securityContext":{"runAsUser":1000,"runAsGroup":1000,"fsGroup":1000},"containers":[{"name":"vw-restore","image":"vaultwarden/server:1.37.3","command":["sleep","3600"],"volumeMounts":[{"name":"d","mountPath":"/data"}]}],"volumes":[{"name":"d","persistentVolumeClaim":{"claimName":"vaultwarden-data"}}]}}'
   kubectl -n office wait pod/vw-restore --for=condition=Ready --timeout=120s
   kubectl -n office exec vw-restore -- sh -c "cp -p /data/db.sqlite3 /data/db.sqlite3.broken.\$(date -u +%Y%m%d_%H%M%S) && cp -p '$PRE' /data/db.sqlite3 && rm -f /data/db.sqlite3-wal /data/db.sqlite3-shm && ls -la /data"
   kubectl -n office delete pod vw-restore
   ```
3. Remove `replicas: 0` again (commit `--only`, verify subject, push).
4. Confirm: 1.37.3 pod Ready; §4.4 count block on a fresh backup → identical to
   `$B/counts-before`; 4.4c reads `0 0 0` (pre-migration file is back); operator login.
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
  flags, newer web vault — user-visible. Operator GO required (attended slot preferred; §4.6 needs the operator). Do not set it `false` to reach SD-10/SD-11: feature loss is
  exactly the case those exclude. ~30 min; no reboot; single pod.
- **conflicts_with** carries: `helm-drift-detection` and `flux-oci-chart-sources` (both rewrite this HelmRelease's spec);
  `coredns-1.50.2` (it gates on the same `http-vaultwarden` probe and roll cluster DNS);
  `redis-fleet-8.10.3` (office namespace, both read Prometheus after a restart). No open `kube-prometheus-stack` plan exists
  today (2026-11-08); if one appears for the same night, serialize — our CONTROLs read Prometheus.
  **Repo corrections owed (reciprocity is not validated):** `redis-fleet-8.10.3` still lists `vaultwarden-1.37.4` in
  its `conflicts_with`; it must list `vaultwarden-1.37.5` (fixed 2026-11-08, as was `nextcloud-mcp-0.206.0` prose).
  Reciprocal `vaultwarden-1.37.5` entries were added to `coredns-1.50.2`, `helm-drift-detection` and `flux-oci-chart-sources` on 2026-11-08; `nextcloud-mcp-0.203.0` / `0.204.0` prose still names `vaultwarden-1.37.4` (owned by another session).
- `office` co-tenants (sure, nextcloud, penpot, paperless, affine, mealie, …) are not touched: separate pods, PVCs and DBs; vaultwarden shares no
  database, cache or secret with them. Reloader watches `vaultwarden-secret`; this plan does not touch the Secret, so no second roll.
- **Do not run 22:00-23:30 UTC** (live Longhorn RecurringJobs, `kubectl get cronjob -n storage`): `global-filesystem-trim` 22:00 UTC,
  `global-snapshot-cleanup` 22:30 UTC and `daily-backup-all-volumes` `0 23 * * *` UTC act on `vaultwarden-data`. A snapshot/backup racing the
  migration is harmless for SQLite but muddies the 5.C restore point. Outside that band an unattended nightly runner (03:30 Berlin) is clear.
- No shared infra is restarted. Envoy, CoreDNS, cert-manager, Longhorn engine: untouched.
- The pre-upgrade restore point `/data/db_<UTC>.sqlite3` stays on the PVC (and therefore inside every later Longhorn backup). That is intended.
