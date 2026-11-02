---
plan_id: mealie-3.30.0
component: mealie
pr: 384                               # Renovate PR "update ghcr.io/mealie-recipes/mealie ( v3.28.0 -> v3.30.0 )", OPEN, CI green
                                      # (Flate Render Gate + Flux Local Diff). This plan lands the bump by a direct commit on main
                                      # (the same edit plus the attended-run guards of section 3), then closes #384 as superseded.
kind: image
current: "v3.28.0"                    # live on deployment/mealie and in git, verified 2026-11-02 (/api/app/about reports v3.28.0)
target: "v3.30.0"                     # ghcr.io/mealie-recipes/mealie:v3.30.0, published 2026-10-31, latest, not a pre-release.
                                      # v3.29.0 was assessed and REJECTED as an intermediate target: it carries 5 of the 9
                                      # migrations and does not satisfy the finding's remediation condition (section 1.1).
update_type: minor
risk: medium                          # Not low: nine forward-only Alembic revisions (one of them rewrites recipe time TEXT into
                                      # new columns), an authlib minor bump on the internet-facing OIDC login path, and a rollback that
                                      # needs a database restore. Not high: additive schema, one small standalone database
                                      # (184 recipes, 20 MB), a fresh dump + proven restore taken first, 2 users.
est_duration_min: 45                  # pre-checks 10 + backup gate and restore proof 8 + edit/commit/push 3 + Flux, Recreate,
                                      # migration, Ready 6 + verification incl. the operator's real login 12 + unsuspend/settle 6.
                                      # Rollback, if needed, adds ~15 (section 5).
needs_reboot: false
touches:
  namespaces: [office]
  resources:
    - helmrelease/mealie              # image tag; upgrade.remediation disabled for the attempt, restored after (section 3)
    - deployment/mealie               # Recreate (single replica, RWO PVC): 1-3 min hard outage of an INTERNET-FACING app
    - deployment/mealie-pg            # NOT restarted. Schema migrated in place by Mealie's startup Alembic (9 revisions)
    - pvc/mealie-pg-data              # the schema change and the time-text rewrite land here
    - pvc/mealie-data                 # read only (recipe images); no revision touches files
    - cronjob/mealie-shopping-sync    # SUSPENDED in git for the window (section 3.3), unsuspended after the contents gate
    - httproute/mealie                # unchanged; the route is down only while the pod is
  shared:
    - monitoring                      # section 4 reads Prometheus/Alertmanager state - the window's instrument
    - authentik                       # READ dependency only (OIDC discovery/token/userinfo for the section 4.4 login). Not perturbed;
                                      # listed so the scheduler warns on any future Authentik change in the same window.
    # Deliberately NOT gateway/envoy: no Gateway, route, cert, DNS or SecurityPolicy edit. NOT storage/longhorn: no PVC is
    # created, resized or deleted; the Longhorn volumes are only read for backup freshness.
depends_on: []
conflicts_with:
  # Same Flux Kustomization office/mealie and the same file as section 3.3: never two pending commits on it in one window.
  - python-fleet-3.15.2               # bumps the image of cronjob/mealie-shopping-sync (sat-attended:2026-11-14). RECIPROCAL ENTRY OWED
                                      # in that plan (the scheduler honours the field in either direction; --validate does not check reciprocity).
  # The section 4.4 login rides envoy-external + Authentik; a data-plane or identity change in the same window confounds it.
  - envoy-proxy-config-distroless-v1.39.4
  - envoy-proxy-config-distroless-v1.40.0
  - envoy-proxy-config-distroless-v1.40.2
  # Platform plans that rewrite every HelmRelease / app-template consumer (this HR is one), or restart the control plane.
  - helm-drift-detection              # adds spec.driftDetection to every HelmRelease incl. mealie; sat-attended:2026-11-07 (60 of 70 schedulable min)
  - flux-oci-chart-sources            # rewrites HelmRelease chart sources (app-template consumers)
  - etcd-timeouts-5000-500            # restarts etcd on all control-plane nodes; also a backup-restore plan (rollback-class stacking)
  - longhorn-1.13.0                   # exclusive storage-engine upgrade
  - talos-linux-1.14.5                # exclusive 3-node reboot roll
  # Rollback-class stacking: two backup-restore rollbacks in one slot leave neither a rollback budget (office, same class).
  - bitnamilegacy-exit-nextcloud-db
  # Same-night kube-prometheus-stack bump would blind the section 4 gates: NONE is open (no kps plan in the directory,
  # 2026-11-02). If one is filed, add it here AND list this plan there.
  # redis-fleet-8.10.3 (sun-attended:2026-11-29, office) does not touch Mealie; not listed, but do not stack it in the same
  # slot if the operator wants a clean attribution for the first post-bump login.
exclusive: false
security_ref: F-c0bd7eb7              # the driver. Detail stays on the finding record (vulnerability-disclosure.md); block below.
# runbooks/policy-cli.py finding ref F-c0bd7eb7  -- paste the printed block here when vetting; it is not reproduced in this draft.
capability_change: true               # HONEST, not "to be safe": the release adds user-visible behaviour on a family-facing app
                                      # (metric/imperial unit conversion, structured recipe times with a one-time rewrite of the stored
                                      # time text, simplified shopping-list entry, per-step durations, week-wide meal-plan entries,
                                      # in-app AI prompt editor) AND new auth/exposure surface that ships OFF (reverse-proxy auth
                                      # endpoint, meal-plan iCal feed, native OIDC client). One of them is only safe because we do not
                                      # set it (REVERSE_PROXY_AUTH_ENABLED), which section 4.5 asserts. => HUMAN-GATED, never nightly
                                      # unattended. The security driver is real, but severity does not turn a capability change into
                                      # a standard change.
rollback_class: backup-restore        # A plain git revert does NOT restore service once the schema has moved: v3.28.0's startup runs
                                      # an unguarded `alembic upgrade head` against a DB stamped with a revision it has never heard of
                                      # and exits (section 1.4). Every post-migration rollback needs a DB step (section 5).
backup_gate: "pg_dump -Fc of the `mealie` database streamed from the LIVE deploy/mealie-pg pod to ~/backups/mealie BEFORE the commit is
  pushed, with a sha256 equal on both sides, a `pg_restore -l` run IN THE POD (the Mac's pg_restore is 16.14 and cannot read a
  PostgreSQL 18 archive: it prints 'unsupported version (1.16) in file header') listing >= 65 TABLE DATA entries, and the
  pre-upgrade row counts captured to a sidecar file for the section 4 contents diff. The Longhorn backup of mealie-pg-data (runs
  23:00Z daily) is block-level and is NOT a substitute: the dump is what makes section 5 option B exact."
restore_proof: "Section 3.2 step 4: the dump is restored with --exit-on-error into a SCRATCH database (mealie_restoretest) inside the
  mealie-pg pod, its recipes / users / recipe_instructions / group_meal_plans / shopping_list_item_extras / alembic_version counts
  are diffed against the live database, and the scratch database is dropped. A dump that does not restore here is a NO-GO."
finding_refs:
  - F-c0bd7eb7                        # the contextual CRITICAL for ghcr.io/mealie-recipes/mealie:v3.28.0. This plan IS its remedy.
  - F-9848e326                        # the version row "mealie v3.28.0 -> v3.30.0 (minor)" this plan lands.
  # Context, NOT claimed: F-655a9c6c ("Held-by-engine bumps with no plan": homepage and mealie v3.29.0) is a multi-component plan
  # finding; this plan answers only its mealie half and must not be recorded as closing it. F-99cd628f / F-6cd9118b are AR-029
  # acceptances for what upstream has not fixed and are unaffected by the bump.
review: null
status: draft
window: null                          # the window agent assigns it. RECOMMENDATION (section 6): an operator-triggered NOW run
                                      # (home-operation run) as soon as the operator can be present; otherwise sat-attended:2026-11-07,
                                      # which fits only if helm-drift-detection moves (60 + 45 > 70 schedulable minutes). Not nightly.
premises:
  - id: live-image-is-v3.28.0
    why: >-
      `current:` claims v3.28.0. If the cluster already moved (a direct-bump, a hand edit), the section 3.4 diff,
      the section 2.2 baselines and the section 5 rollback target are all stale.
    run: kubectl get deploy -n office mealie -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: ghcr.io/mealie-recipes/mealie:v3.28.0
  - id: git-pin-is-v3.28.0
    why: >-
      Section 3.4 edits exactly one tag line. If git already differs from v3.28.0 the sed is a no-op and the commit
      would be empty or wrong; better to refuse than to "upgrade" nothing.
    run: "git show HEAD:kubernetes/apps/office/mealie/app/helmrelease.yaml | grep -c 'tag: v3.28.0'"
    expect_exact: "1"
  - id: helmrelease-ready-on-app-template-5.3.0
    why: >-
      The values path section 3.4 edits and the rendered `strategy: Recreate` guard belong to the app-template 5.x schema,
      and a HelmRelease that is already failing would make every later gate ambiguous.
    run: kubectl get helmrelease -n office mealie -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: "5.3.0"
  - id: helmrelease-is-ready
    why: >-
      A not-Ready HelmRelease before the change means the section 4 "Ready" gate proves nothing about this change.
    run: kubectl get helmrelease -n office mealie -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: recreate-strategy-still-rendered
    why: >-
      Single replica on an RWO Longhorn PVC. RollingUpdate would deadlock on Multi-Attach and look intermittent
      (docs/sops/longhorn-rwo-multi-attach.md). Verified on the rendered Deployment, not on the values.
    run: kubectl get deploy -n office mealie -o jsonpath='{.spec.strategy.type}'
    expect_exact: Recreate
  - id: env-has-no-new-surface-switches-and-oidc-on
    why: >-
      Sections 1.3 and 4.5 were derived for the env as measured: OIDC on, and NONE of REVERSE_PROXY_AUTH_*, HOST_IP,
      API_HOST, OPENAI_CUSTOM_PROMPT_DIR set. If someone has since set one, the "ships OFF" and "nothing to migrate"
      conclusions must be re-derived. The negative lookaheads keep this fail-closed.
    run: kubectl get deploy -n office mealie -o jsonpath='{.spec.template.spec.containers[0].env[*].name}'
    expect_matches: '^(?!.*REVERSE_PROXY_AUTH)(?!.*HOST_IP)(?!.*API_HOST)(?!.*OPENAI_CUSTOM_PROMPT_DIR)(?=.*OIDC_AUTH_ENABLED)(?=.*OIDC_CONFIGURATION_URL).*$'
  - id: mealie-pg-is-the-standalone-postgres-18
    why: >-
      Sections 3.2, 4.2 and 5 all `kubectl exec` into deploy/mealie-pg with `-U mealie`, and the in-pod pg_restore
      is the only one that can read the dump (pg 18 archive format). If the DB was replatformed those commands
      would target the wrong server.
    run: kubectl get deploy -n office mealie-pg -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_contains: "postgres:18."
  - id: both-mealie-volumes-bound
    why: >-
      Section 2.3 relies on the two Longhorn volumes being the ones Mealie mounts. A Pending PVC means the pod is not
      the thing the baselines were taken from.
    run: kubectl get pvc -n office mealie-data mealie-pg-data -o jsonpath='{.items[*].status.phase}'
    expect_exact: "Bound Bound"
  - id: route-is-still-on-envoy-external
    why: >-
      The 1.3 exposure analysis and the section 4.5 external probes assume the internet-facing Gateway. If the route
      moved to envoy-internal the external gates test the wrong path.
    run: kubectl get httproute -n office mealie -o jsonpath='{.spec.parentRefs[0].name}'
    expect_exact: envoy-external
  - id: shopping-sync-not-already-suspended
    why: >-
      Section 3.3 suspends the CronJob in git and section 3.8 removes the line. If it is already suspended (by hand
      or by another plan) the unsuspend would silently re-enable something someone else stopped.
    run: kubectl get cronjob -n office mealie-shopping-sync -o jsonpath='{.spec.suspend}'
    expect_exact: "false"
  - id: git-has-no-suspend-or-remediation-edit-pending
    why: >-
      The seds in sections 3.3 and 3.4 assume the pre-window files. A leftover `suspend: true` or
      `remediateLastFailure` from an aborted earlier attempt would double-apply or mask the restore step.
    run: "git show HEAD:kubernetes/apps/office/mealie/app/helmrelease.yaml | grep -c remediateLastFailure"
    expect_exact: "0"
  - id: mealie-pg-volume-healthy
    why: >-
      The dump is taken from this volume and the Longhorn backup is the second line of defence. A degraded volume
      makes both weaker, and a rebuild during a schema migration is the wrong time.
    run: kubectl get volumes.longhorn.io mealie-pg-data -n storage -o jsonpath='{.status.robustness}'
    expect_exact: healthy
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/backup.md
  - docs/sops/authentik.md
  - docs/sops/longhorn-rwo-multi-attach.md
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/vulnerability-disclosure.md
generated: "2026-11-02"
---

# Mealie - image v3.28.0 -> v3.30.0 (security-driven, nine forward-only migrations)

## 1) Summary & why held

Bump `ghcr.io/mealie-recipes/mealie` from **v3.28.0** to **v3.30.0** in
`kubernetes/apps/office/mealie/app/helmrelease.yaml` (272 upstream commits, two releases: v3.29.0 on 2026-10-17 and v3.30.0
on 2026-10-31). The pod is `Recreate`d (single replica on RWO `mealie-data`); on start Mealie runs **nine** Alembic
revisions against the standalone `mealie-pg` (`postgres:18.6-bookworm`, PVC `mealie-pg-data`), which is not restarted.
Mealie is exposed on the **internet-facing** Gateway (`envoy-external`; external ingress accepted under AR-007, unchanged).

**Why this is a plan and not an auto-bump.** The auto-updater's structural diff held it on database migrations. The hold
note counted two new Alembic files; the real number between the two tags is **nine** (directory listing of
`mealie/alembic/versions` at v3.28.0 vs v3.30.0; head moves `3527efeeec34` -> `071e03b4f851`). Migrations make the rollback a
database operation, not an image revert (1.4), and one of them rewrites stored recipe data (1.3).

**Why it cannot wait for a quiet quarter.** It is the security remedy for sweep finding **F-c0bd7eb7** (a contextual CRITICAL on
this image; detail is on the finding record, not here - `runbooks/policy-cli.py finding show F-c0bd7eb7`). Operator rule: we bump
third-party images, we never rebuild them, so the bump is the only remedy available.

### 1.1 Why the target is v3.30.0 and not v3.29.0 (measured 2026-11-02)

The same `trivy image --scanners vuln --severity CRITICAL --ignore-unfixed` run was applied to v3.28.0 (the **positive control**: it
reproduced the finding's own fixable-critical count exactly, so the method sees what the sweep sees), v3.29.0 and v3.30.0, and each
result was intersected with the CISA known-exploited feed (the tier the finding is rated on). **v3.30.0 is the lowest tag that
satisfies the finding's remediation condition; v3.29.0 does not** - the fix arrives with the python base-image refresh that only the
v3.30.0 build contains (the release also bumps `authlib` to 1.9.x, PRs #8792/#8796). So v3.29.0 is not a useful stop: it costs five of
the nine migrations and fixes nothing that pages. Per-package detail stays on the finding record.

Section 4.7 therefore asserts that the finding's exploited-rated tier no longer applies to the running tag - it deliberately does NOT
require an empty scan. Do not "improve" that into a stricter gate: whatever remains is governed by the existing AR-029 acceptance.

### 1.2 The nine revisions, one by one (read from the v3.30.0 files)

```
3527efeeec34  (live head)
 +- 27621d27c7e1  recipes: +total_time_seconds +prep_time_seconds +perform_time_seconds; DATA REWRITE of the three time TEXT columns
 +- a8f3b2c1d4e5  group_meal_plans.recipe_scale  (NOT NULL, server_default 1)
 +- 3697d65c5f92  DELETE FROM cookbooks_to_{categories,tags,tools}, plan_rules_to_{categories,tags}   (no downgrade)
 +- f3a8b6c1d2e4  ALTER TYPE authmethod ADD VALUE 'REVERSE_PROXY'                                    (no downgrade; enum values cannot be dropped)
 +- 1e69ea7cd45e  household_preferences.mealplan_ical_token + unique index
 +- a91720b8a7e7  CREATE TABLE ai_prompt_overrides (+3 indexes); imports OPENAI_CUSTOM_PROMPT_DIR files if that env is set
 +- afdc42353aa4  recipe_instructions.duration_seconds
 +- a9f823e9e441  group_meal_plans.end_date + index
 +- 071e03b4f851  backfills ai_provider_settings for groups lacking one                              (no downgrade)
                  = v3.30.0 head
```

| Revision | What it does to OUR data (measured 2026-11-02) | Reversible? |
|---|---|---|
| `27621d27c7e1` | Docstring: *"moves existing text into it, but only when the whole string is unambiguously a duration ... Anything else is left as text, untouched."* Our 130 / 21 / 17 non-empty total / prep / perform texts: 86 recipes carry a RANGE (`30-40 Minuten`) and 2 are `ca. 25 Minuten` - **left as text**; the plain `15 Minuten`, `1 hour 20 minutes`, `PT32H`, `PT24H` forms are converted and their text column set to NULL. No row is `none` (so nothing is cleared). | Downgrade rebuilds the text in ENGLISH (`PT32H` becomes `1 day 8 hours`, `30 Minuten` becomes `30 minutes`): meaning kept, original strings lost. Only the pre-upgrade dump restores the originals. |
| `3697d65c5f92` | Deletes five legacy join tables. **All five are empty on our DB** (cookbooks and meal-plan rules were already folded into `query_filter_string`), so it is a no-op here. | No downgrade, and nothing to restore. |
| `f3a8b6c1d2e4` | Adds an enum value. Harmless to v3.28.0 code, but the enum can no longer be returned to its old shape except by restore. | No. |
| `a91720b8a7e7` | Creates `ai_prompt_overrides`. `OPENAI_CUSTOM_PROMPT_DIR` is **not set** on our Deployment (premise `env-has-no-new-surface-switches-and-oidc-on`), so no rows are imported. Release note: *"The old `OPENAI_CUSTOM_PROMPT_DIR` env var has been removed, but if you had any custom prompts they will be imported into the new format automatically."* | Table drop. |
| `071e03b4f851` | `groups` = 1 and `ai_provider_settings` = 1, so it inserts nothing. | No downgrade needed. |
| the rest | additive nullable / defaulted columns and indexes | yes |

**Atomicity is not relied on.** `mealie/alembic/env.py` runs all pending revisions inside one `context.begin_transaction()`
(no `transaction_per_migration`), which is atomic on Postgres - but `27621d27c7e1` opens its own `orm.Session` on the same
connection and calls `commit()`, and v3.30.0 also bumps SQLAlchemy to 2.1.x. Whether that inner commit is joined or real
cannot be established offline, so the plan treats "head is somewhere between 3527efeeec34 and 071e03b4f851" as a possible
failure state and gates on the head value (4.2), never on the pod being Running.

### 1.3 Breaking changes, new surface and the behaviour that matters to us

No "BREAKING CHANGE" heading exists in either release. What the notes and source show, assessed against our wiring:

| Item | Source | Impact here |
|---|---|---|
| Reverse-proxy auth (`/api/auth/reverse-proxy`, v3.29.0 #8183) | `settings.REVERSE_PROXY_AUTH_ENABLED: bool = False`; the route does `if not settings.REVERSE_PROXY_AUTH_READY: raise not_found()`; code comment: with the default `HOST_IP="*"` "uvicorn trusts every peer" | **Ships OFF.** We set none of the `REVERSE_PROXY_AUTH_*` vars (premise). On an internet-facing app the only failure mode is someone enabling it later; 4.5 asserts it answers 404. **Do not add these env vars.** |
| `HOST_IP` default | `docker/entry.sh` no longer derives `HOST_IP` from the default route; `AppSettings` defaults it to `"*"` | uvicorn now trusts `X-Forwarded-*` from any peer (previously only the pod's gateway address, i.e. effectively never Envoy). Effect: access logs and the cookie `Secure` attribute now see the real client / `https`. Behavioural, not breaking; no action, noted so the first log diff is not misread. |
| Listen address | #8569: `API_HOST` default `""`, one dual-stack `::` socket, IPv4 fallback if IPv6 is unavailable | Kubelet probes use the pod's IPv4; verified by the probes themselves (4.1). |
| Meal-plan iCal feed (v3.29.0 #8461, v3.30.0 #8909) | opt-in; "anyone with the iCal link can subscribe without any additional auth" | **Ships OFF** (`mealplan_ical_token` NULL). 4.5 asserts no household has a token after the migration. |
| OIDC | `authlib` 1.8.x -> 1.9.x; `OIDC_VERIFY_X509_STRICT` (default true, same as the Python 3.13+ behaviour already live), `OIDC_NATIVE_*` (unset), avatar refresh from stable URLs | **The one real risk.** Discovery, token exchange and userinfo run on authlib. The discovery host resolves to the envoy-external LAN address and Authentik cannot assert `email_verified` (hence `OIDC_REQUIRES_EMAIL_VERIFICATION: "false"` in our HelmRelease). A library minor on that path can only be proven by a real login (4.4). `OIDC_REMEMBER_ME` / `TOKEN_TIME` are still honoured in v3.30.0 settings. |
| Outbound-request guard (v3.26.0) | already live since the v3.26.0 plan; unchanged | none - `webhook_urls`, `recipe_actions`, notifiers were 0 on 2026-09-15; re-checked in 2.2. |
| `mealie-shopping-sync` | CronJob, every 5 min, reads `/api/households/shopping/lists` and PUTs `extras.ha_synced` back; **add-only** push to Home Assistant | No shopping-list table is touched by any revision. The risk is the API contract: if `extras` stopped round-tripping, all 209 stamped items would be re-pushed onto the family's Alexa list. Hence the CronJob is suspended in git for the window and released only after 4.3 proves the read path (section 3.3). |
| Home Assistant | no `mealie` config entry exists in HA (`core.config_entries` has no mealie domain, checked 2026-11-02); HA is only the push TARGET of the sync | The memory note "Server got itself in trouble = aiohttp/HA, not Mealie" applies to the sync's HA leg and is unchanged. Nothing in HA reads Mealie. |
| Open upstream issue against v3.30.0 | #8946 (2026-11-02): public, unauthenticated recipe viewing redirects to login | We run a private household; no public recipe sharing is configured. Not a gate. |

### 1.4 Why a revert alone crash-loops

`mealie/db/init_db.py::main()` (identical logic at v3.28.0, lines 115-119) compares the DB's Alembic heads with the scripts in
the image and, when they differ, calls `command.upgrade(cfg, "head")` unguarded. v3.28.0 has no script for
`071e03b4f851`, so it raises `Can't locate revision` and the container exits: CrashLoopBackOff, and Flux's own rollback cannot
help (`maxHistory: 1`, and the DB is what is wrong). A revert is therefore **revert + one DB step**, or, if the migration never
committed, revert alone (section 5.1 decides which by reading the head).

### 1.5 Repo corrections found while planning (state in the report, do not silently plan around)

1. `runbooks/maintenance/plans/mealie-v3.26.0` (retired, in git history) gated its dump with a LOCAL `pg_restore -l ... | grep -c
   'TABLE DATA'`. The Mac's `pg_restore` is **16.14**; against this cluster's PostgreSQL 18 archive it prints `unsupported version
   (1.16) in file header` and the count reads 0. That fails closed, but at the wrong place. This plan lists the archive in the pod
   (3.2 step 3). Any future plan that copies the v3.26.0 gate inherits the defect.
2. `kubectl exec -i deploy/mealie-pg -- pg_restore -l < dump` (stdin) **hangs** on a custom-format archive (needs a seekable
   file). Restore and list from a file inside the pod, as 3.2 and 5.2 do.
3. The v3.26.0 plan names the Longhorn backup time as "03:0x"; the live `daily-backup-all-volumes` RecurringJob runs
   `0 23 * * *` (UTC) since 2026-10-13. Section 2.3 uses an age check, not a clock time.
4. `age_waive` for `*mealie*` in `runbooks/auto-update-policy.yaml` lapses 2026-12-31 ("re-decide before it lapses"). Not part of
   this change; flagged so it is not forgotten.

## 2) Pre-checks

Run inside the window, in one shell. Every check has a pass condition; a fail is a no-go. Work directory for artifacts:

```bash
cd /Users/mu/code/cberg-home-nextgen
W=$(mktemp -d /tmp/mealie-3.30.0.XXXXXX); echo "$W"          # keep this path for sections 3 and 4
H=$(kubectl get httproute -n office mealie -o jsonpath='{.spec.hostnames[0]}'); echo "host_resolved=${H:+yes}"
```

**2.0 Premises, mechanically** (read-only by construction):

```bash
.venv/bin/python3 runbooks/plan-premises.py mealie-3.30.0 --require-premises
```
**PASS:** exit 0, 12/12 passed, no `REFUSED` line.

**2.1 Flux green, nothing else mid-flight on this surface, target still current.**

```bash
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
flux get helmreleases   -A | awk 'NR==1 || $5 != "True"'
kubectl get pods -n office -l app.kubernetes.io/name=mealie
kubectl get pods -n office -l app=mealie-pg
.venv/bin/python3 runbooks/maintenance-plan.py --open | grep -E 'python-fleet|helm-drift|flux-oci|envoy-proxy|etcd-timeouts|longhorn|talos'
gh release list -R mealie-recipes/mealie --limit 3 --json tagName,isPrerelease -q '.[]|"\(.tagName) pre=\(.isPrerelease)"'
```
**PASS:** both flux lists print only the header; mealie and mealie-pg `1/1 Running`, restarts 0; the `--open` grep shows none of those
plans stamped for TODAY's window (a stamp for another date is fine); the newest non-pre-release tag is `v3.30.0`.
**If a `v3.30.1` (or newer 3.30.x) exists: STOP.** Re-read its notes, retarget by refreshing this plan in place (README "When the
held target MOVES"); do not bump to a tag whose notes this plan never read.

**2.2 Database baseline** (cannot be a premise: `kubectl exec` is refused by the runner). Save it; section 4 diffs against it.

```bash
kubectl exec -n office deploy/mealie-pg -- psql -U mealie -d mealie -At \
  -c "select 'alembic_head='||version_num from alembic_version" \
  -c "select 'recipes='||count(*) from recipes" \
  -c "select 'users='||count(*) from users" \
  -c "select 'users_oidc='||count(*) from users where auth_method='OIDC'" \
  -c "select 'groups='||count(*) from groups" \
  -c "select 'steps='||count(*) from recipe_instructions" \
  -c "select 'mealplans='||count(*) from group_meal_plans" \
  -c "select 'ai_settings='||count(*) from ai_provider_settings" \
  -c "select 'shopping_items='||count(*) from shopping_list_items" \
  -c "select 'ha_synced_rows='||count(*) from shopping_list_item_extras where key_name='ha_synced'" \
  -c "select 'webhooks='||count(*) from webhook_urls" \
  -c "select 'recipe_actions='||count(*) from recipe_actions" \
  -c "select 'notifiers='||count(*) from group_events_notifiers" \
  -c "select 'legacy_join_rows='||((select count(*) from cookbooks_to_categories)+(select count(*) from cookbooks_to_tags)+(select count(*) from cookbooks_to_tools)+(select count(*) from plan_rules_to_categories)+(select count(*) from plan_rules_to_tags))" \
  -c "select 'tables='||count(*) from information_schema.tables where table_schema='public'" \
  -c "select 'enum_authmethod='||string_agg(enumlabel,',' order by enumsortorder) from pg_enum e join pg_type t on t.oid=e.enumtypid where t.typname='authmethod'" \
  -c "select 'total_text='||count(*) from recipes where total_time<>''" \
  -c "select 'prep_text='||count(*) from recipes where prep_time<>''" \
  -c "select 'perform_text='||count(*) from recipes where perform_time<>''" \
  -c "select 'range_rows='||count(*) from recipes where total_time ~ '[0-9]-[0-9]' or prep_time ~ '[0-9]-[0-9]' or perform_time ~ '[0-9]-[0-9]'" \
  -c "select 'none_text_rows='||count(*) from recipes where lower(trim(total_time))='none' or lower(trim(prep_time))='none' or lower(trim(perform_time))='none'" \
  -c "select 'iso_text_rows='||count(*) from recipes where total_time ~* '^P' or prep_time ~* '^P' or perform_time ~* '^P'" \
  -c "select 'dbsize='||pg_size_pretty(pg_database_size('mealie'))" | tee "$W/baseline.txt"
```
**PASS / baseline 2026-11-02:** `alembic_head=3527efeeec34` - `recipes=184` - `users=2` - `users_oidc=1` - `groups=1` - `steps=1083` -
`mealplans=50` - `ai_settings=1` - `shopping_items=209` - `ha_synced_rows=209` - `webhooks=0` - `recipe_actions=0` - `notifiers=0` -
`legacy_join_rows=0` - `tables=69` - `enum_authmethod=MEALIE,LDAP,OIDC` - `total_text=130` - `prep_text=21` - `perform_text=17` -
`range_rows=86` - `none_text_rows=0` - `iso_text_rows=1` - `dbsize=20 MB`.
**STOP conditions:** `alembic_head` is not `3527efeeec34` (the DB is not where 1.2 says); `legacy_join_rows` > 0 (3697d65c5f92
would delete real cookbook/rule links - read them first, the revision comment says they are dead data, prove it);
`webhooks`/`recipe_actions`/`notifiers` > 0 (outbound targets exist - re-derive against the v3.26.0 guard); `none_text_rows` > 0
(the revision clears those; the 4.3 arithmetic needs the new baseline). Other counts have drifted legitimately if recipes were
added: write the new numbers down, they replace the ones above in section 4 - but a DROP in `recipes`, `users` or `shopping_items`
since the last sweep is a STOP.

**2.3 Backups fresh and the volumes healthy** (both volumes; second line of defence behind the dump).

```bash
kubectl get volumes.longhorn.io -n storage mealie-data mealie-pg-data \
  -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.status.lastBackupAt}{" "}{.status.robustness}{"\n"}{end}' | python3 -I -c "
import sys,datetime as d
bad=0
for l in sys.stdin:
    n,t,r=l.split()
    age=(d.datetime.now(d.timezone.utc)-d.datetime.fromisoformat(t.replace('Z','+00:00'))).total_seconds()/3600
    ok = age<30 and r=='healthy'
    bad += (not ok)
    print(n,'age_h=%.1f'%age,r,'OK' if ok else 'FAIL')
sys.exit(1 if bad else 0)"
```
**PASS:** both lines `OK`, exit 0 (measured 2026-11-02 08:06 local: both 8.2 h, healthy). A volume with no `lastBackupAt` fails on the split.
This can fail: age >= 30 h or robustness != healthy prints `FAIL` and exits 1.

**2.4 Shopping-sync read-path baseline** (the exact reads `sync.py` performs; the script is reused in 4.3).

```bash
cat > "$W/synccheck.py" <<'PY'
import json, os, sys, urllib.request
base, token = sys.argv[1].rstrip("/"), os.environ["MEALIE_TOKEN"]
def get(path):
    req = urllib.request.Request(base + path, headers={"Authorization": "Bearer " + token})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)
lists = get("/api/households/shopping/lists?perPage=100")["items"]
items = synced = excluded = unchecked_unsynced = 0
for l in lists:
    for it in get("/api/households/shopping/lists/" + l["id"]).get("listItems") or []:
        items += 1
        ex = it.get("extras") or {}
        synced += bool(ex.get("ha_synced"))
        excluded += bool(ex.get("ha_exclude"))
        if not it.get("checked") and not ex.get("ha_synced") and not ex.get("ha_exclude"):
            unchecked_unsynced += 1
print("lists=%d items=%d ha_synced=%d ha_exclude=%d would_push=%d" % (len(lists), items, synced, excluded, unchecked_unsynced))
PY
export MEALIE_TOKEN=$(kubectl get secret -n office mealie-shopping-sync -o jsonpath='{.data.MEALIE_TOKEN}' | base64 -d)
kubectl port-forward -n office svc/mealie 19000:9000 >/dev/null 2>&1 & PF=$!; sleep 3
python3 -I "$W/synccheck.py" http://127.0.0.1:19000 | tee "$W/sync-before.txt"
kill $PF 2>/dev/null; unset MEALIE_TOKEN
kubectl logs -n office "$(kubectl get pods -n office -o name | grep mealie-shopping-sync | tail -1)" 2>/dev/null | tail -1
```
**PASS / baseline 2026-11-02:** `lists=1 items=209 ha_synced=209 ha_exclude=0 would_push=0`, and the last sync Job log ends
`done: pushed=0 already-synced=209 excluded=0 lists=1`. `would_push` must be 0 before the window; a non-zero value means items
are waiting for the next tick and the post-window `pushed=0` gate (4.3) must be adjusted by that number. (The last grep may print
nothing if the 1 h Job TTL expired; that is not a failure, `sync-before.txt` is the baseline.)

**2.5 OIDC and exposure baseline BEFORE the change** (so a section 4 failure is attributable).

```bash
curl -s -m 15 -o /dev/null -D - "https://$H/api/auth/oauth" | tr -d '\r' | grep -i -E '^(HTTP|location)' \
  | sed -E 's/(state|nonce|code_challenge)=[^&]*/\1=X/g' | tee "$W/oauth-before.txt"
curl -s -m 15 -D - -o /dev/null -H 'X-Forwarded-User: probe' "https://$H/api/auth/reverse-proxy" | tr -d '\r' | grep -i -E '^(HTTP|content-type)' | tee "$W/revproxy-before.txt"
kubectl exec -n office deploy/mealie -c main -- python3 -c "
import os,json,socket,urllib.request,urllib.parse
u=os.environ['OIDC_CONFIGURATION_URL']; h=urllib.parse.urlparse(u).hostname
print('resolves:',sorted({a[4][0] for a in socket.getaddrinfo(h,443)}))
d=json.load(urllib.request.urlopen(u,timeout=10)); print('issuer ok:', 'issuer' in d, '| token_endpoint ok:', 'token_endpoint' in d)"
```
**PASS / baseline 2026-11-02:** `oauth-before.txt` = `HTTP/2 302` plus a `location:` to the Authentik authorize endpoint with
`response_type=code`, the app's `client_id`, `redirect_uri=https%3A%2F%2F<host>%2Flogin`, `scope=openid+email+profile` and
`code_challenge_method=S256` (the normaliser was run twice and produced identical output). `revproxy-before.txt` = `HTTP/2 200`,
`content-type: text/html` - on v3.28.0 that route does not exist and the SPA fallback answers; this is the value 4.5 must flip.
The pod probe prints `resolves: ['192.168.55.104']` and `issuer ok: True | token_endpoint ok: True`.

**2.6 Alert baseline.**

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 4
curl -s localhost:19090/api/v1/alerts | python3 -I -c "
import sys,json
a=[x['labels'].get('alertname') for x in json.load(sys.stdin)['data']['alerts'] if x['state']=='firing' and x['labels'].get('alertname') not in ('Watchdog','InfoInhibitor')]
print('firing:',len(a),a)"
kill $PF 2>/dev/null
```
**PASS:** no `Mealie*` and no `KubeJobFailed` for `office` firing. Write the list down for 4.6.

## 3) Steps

**3.1 Active-update marker** (`docs/sops/application-update.md` Step 1; no Alertmanager silence: the `Mealie*` rules are
`for: 5m` / `for: 1m` and this is an attended run).

```bash
runbooks/update-marker.sh add mealie office 2 "image v3.28.0->v3.30.0"
```

**3.2 BACKUP GATE and RESTORE PROOF (mandatory; `rollback_class: backup-restore`).** Nothing is pushed before every sub-step passes.

```bash
umask 077
DUMP_DIR="$HOME/backups/mealie"; mkdir -p "$DUMP_DIR"
DUMP="$DUMP_DIR/mealie-pre-v3.30.0-$(date +%Y%m%d_%H%M%S).dump"; echo "$DUMP"
# 1. stream the dump out (the same mechanism produced a 782605-byte archive in the 2026-11-02 dry run)
kubectl exec -n office deploy/mealie-pg -- pg_dump -U mealie -d mealie -Fc > "$DUMP"
ls -l "$DUMP"; cp "$W/baseline.txt" "$DUMP.counts.txt"
[ "$(stat -f %z "$DUMP")" -ge 500000 ] && echo SIZE_OK || echo SIZE_TOO_SMALL
# 2. put a copy in the pod and prove both copies are byte-identical
kubectl exec -i -n office deploy/mealie-pg -- sh -c 'cat > /tmp/mealie-pre-v3.30.0.dump' < "$DUMP"
echo "local=$(shasum -a 256 "$DUMP" | cut -d' ' -f1)"
echo "pod  =$(kubectl exec -n office deploy/mealie-pg -- sha256sum /tmp/mealie-pre-v3.30.0.dump | cut -d' ' -f1)"
# 3. list the archive IN THE POD (pg 18 pg_restore reads a pg 18 archive; the Mac's 16.14 cannot)
N=$(kubectl exec -n office deploy/mealie-pg -- pg_restore -l /tmp/mealie-pre-v3.30.0.dump | grep -c 'TABLE DATA'); echo "table_data=$N"
[ "${N:-0}" -ge 65 ] && echo TABLE_DATA_OK || echo TABLE_DATA_TOO_FEW
# 4. RESTORE PROOF into a scratch database, diff counts, drop it
kubectl exec -n office deploy/mealie-pg -- sh -c 'createdb -U mealie mealie_restoretest && pg_restore -U mealie -d mealie_restoretest --no-owner --exit-on-error /tmp/mealie-pre-v3.30.0.dump'; echo "restore_exit=$?"
for DB in mealie mealie_restoretest; do
  echo "== $DB"; kubectl exec -n office deploy/mealie-pg -- psql -U mealie -d $DB -At \
    -c "select 'alembic_head='||version_num from alembic_version" -c "select 'recipes='||count(*) from recipes" \
    -c "select 'users='||count(*) from users" -c "select 'steps='||count(*) from recipe_instructions" \
    -c "select 'mealplans='||count(*) from group_meal_plans" -c "select 'ha_synced_rows='||count(*) from shopping_list_item_extras where key_name='ha_synced'" \
    -c "select 'tables='||count(*) from information_schema.tables where table_schema='public'" | tee "$W/proof-$DB.txt"
done
diff "$W/proof-mealie.txt" "$W/proof-mealie_restoretest.txt" && echo RESTORE_PROOF_IDENTICAL
kubectl exec -n office deploy/mealie-pg -- dropdb -U mealie --force mealie_restoretest
kubectl exec -n office deploy/mealie-pg -- psql -U mealie -d mealie -At -c "select 'scratch_dbs_left='||count(*) from pg_database where datname='mealie_restoretest'"
```
**PASS - all of:** (1) `SIZE_OK` (782605 bytes on 2026-11-02; under 500000 is a NO-GO); (2) the two sha256 lines are equal;
(3) `TABLE_DATA_OK` (the database has 69 tables; the check FAILS CLOSED - a PostgreSQL version mismatch or a truncated archive
prints 0 and `TABLE_DATA_TOO_FEW`); (4) `restore_exit=0` AND `RESTORE_PROOF_IDENTICAL` (`--exit-on-error` turns any restore error into
a non-zero exit, and the diff independently fails on an empty or partial scratch DB); (5) `scratch_dbs_left=0`. **Any failure: NO-GO.** Do not push; the dump is the only
exact rollback (5.2 B) and an unproven dump is a hope, not a gate. The dump holds password hashes and API tokens: it stays
under `~/backups/mealie` (mode 600 via `umask`) and is never copied into the repo.

**3.3 Suspend the shopping-sync CronJob in git** (so a broken `extras` round-trip cannot push 209 duplicate items to the
household's Alexa list before 4.3 has proved the read path). File:
`kubernetes/apps/office/mealie/app/shopping-sync-cronjob.yaml` (one `spec:` at column 0, verified).

```bash
F=kubernetes/apps/office/mealie/app/shopping-sync-cronjob.yaml
sed -i '' '/^spec:$/a\
  suspend: true
' "$F"
git --no-pager diff -U0 -- "$F"
```
**Expected diff, dry-tested on a scratch copy on macOS:** `7a8` / `>   suspend: true` - exactly one added line, directly under `spec:`.

**3.4 The edit: one tag, and the attended-run guard on the HelmRelease** (SOP `application-update.md` Step 2: a
startup-migration app must not be auto-rolled-back mid-attempt, because Flux's rollback would put v3.28.0 against a migrated DB
and crash-loop it while hiding the new pod's logs). File: `kubernetes/apps/office/mealie/app/helmrelease.yaml`.

```bash
F=kubernetes/apps/office/mealie/app/helmrelease.yaml
sed -i '' 's/^\(              tag: \)v3\.28\.0$/\1v3.30.0/' "$F"
sed -i '' '/^  upgrade:/,/^  uninstall:/ s/^      retries: 3$/      retries: 0\
      remediateLastFailure: false/' "$F"
git --no-pager diff -U0 -- "$F"
```
**Expected diff, dry-tested on a scratch copy (BSD sed):**

```
32c32,33
<       retries: 3
---
>       retries: 0
>       remediateLastFailure: false
66c67
<               tag: v3.28.0
---
>               tag: v3.30.0
```
Only `upgrade.remediation` changes (the range stops at `uninstall:`; `install.remediation.retries: 3` above it is untouched). **Do not
use `yq -i` for either file: it reformats comments and flow maps across the whole file (measured).** Do not add
`HTTP_ALLOW_LIST`, any `REVERSE_PROXY_AUTH_*`, `HOST_IP` or `API_HOST` - 1.3 explains why each would be wrong.

**3.5 Commit ONLY those two files, verify the subject and the content, push** (shared worktree - CLAUDE.md).

```bash
cat > "$W/msg1.txt" <<'EOF'
fix(mealie): image v3.28.0 -> v3.30.0 (security remedy; attended, migrations, cronjob suspended)

Minor bump, nine forward-only Alembic revisions (head 3527efeeec34 -> 071e03b4f851),
one of which rewrites stored recipe time text. Pre-upgrade pg_dump taken and its
restore proven in a scratch database (plan section 3.2).

Window-scoped guards, both reverted in the follow-up commit once verified:
- helmrelease upgrade.remediation retries 0 / remediateLastFailure false
- mealie-shopping-sync suspended until the shopping-list read path is proven

Plan: runbooks/maintenance/plans/mealie-3.30.0.md
Finding: F-c0bd7eb7 (security_ref), F-9848e326
Supersedes Renovate PR #384.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_012bXdxrZGGHNy5e4RnF6seD
EOF
git commit --only kubernetes/apps/office/mealie/app/helmrelease.yaml kubernetes/apps/office/mealie/app/shopping-sync-cronjob.yaml -F "$W/msg1.txt"
git log -1 --format=%s        # MUST be the subject above, not another session's
git show --stat HEAD          # MUST list exactly those two files
C1=$(git rev-parse HEAD); echo "C1=$C1"
git push origin main
T0=$(date +%s); echo "T0=$T0"
```
If `git log -1 --format=%s` shows a foreign subject, `git commit --amend -F "$W/msg1.txt"` BEFORE pushing (the message files swap, not
the content). The commit message carries no CVE ids, counts or exploitability notes (vulnerability-disclosure.md).

**3.6 Watch the rollout.** The GitHub webhook triggers Flux; no manual reconcile by default. If nothing has moved after 3 minutes,
`flux reconcile ks mealie -n office --with-source` is acceptable once. Do **not** hand-delete pods mid-`Recreate` (SOP Step 4).

```bash
kubectl rollout status deploy/mealie -n office --timeout=15m
kubectl logs -n office deploy/mealie -c main --tail=400 | grep -i -E 'Migration needed|Converted .* recipe times|Running upgrade|Traceback|Error|Uvicorn running' || true
```
**Expected (informational, not the gate):** `Migration needed. Performing migration...`, and a line of the form `Converted N
recipe times to structured durations and cleared 0 empty ones across 184 recipes` (N is whatever 4.3 computes; the line comes from
the migration's own logger). A `Traceback` or `Can't locate revision` is a failure: go to section 5.

**3.7 Run section 4 now, before step 3.8.**

**3.8 Release the guards (ONLY after 4.1-4.5 PASS).** One follow-up commit: restore `retries: 3`, drop `remediateLastFailure`, and
unsuspend. Both seds are the inverse of 3.3/3.4 and were dry-tested to restore the pre-window files byte for byte.

```bash
sed -i '' '/^  upgrade:/,/^  uninstall:/ {
/^      remediateLastFailure: false$/d
s/^      retries: 0$/      retries: 3/
}' kubernetes/apps/office/mealie/app/helmrelease.yaml
sed -i '' '/^  suspend: true$/d' kubernetes/apps/office/mealie/app/shopping-sync-cronjob.yaml
git --no-pager diff -U0 -- kubernetes/apps/office/mealie/app/        # exactly the two inverse hunks; the tag stays v3.30.0
cat > "$W/msg2.txt" <<'EOF'
chore(mealie): restore remediation retries and unsuspend shopping-sync after v3.30.0 verification

Window guards from the preceding commit released after the schema, time-text,
OIDC login and shopping-list read-path gates passed.

Plan: runbooks/maintenance/plans/mealie-3.30.0.md

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_012bXdxrZGGHNy5e4RnF6seD
EOF
git commit --only kubernetes/apps/office/mealie/app/helmrelease.yaml kubernetes/apps/office/mealie/app/shopping-sync-cronjob.yaml -F "$W/msg2.txt"
git log -1 --format=%s; git show --stat HEAD; C2=$(git rev-parse HEAD)
git push origin main
```
Then run 4.3 step "first sync" and 4.6 (settle). Close the Renovate PR: `gh pr close 384 --comment "landed directly on main
with window guards (mealie-3.30.0 plan)"` (Renovate would otherwise close it on its next run; either is fine).

## 4) Verification

Gate summary: every gate states the failure it guards against; the CONTENTS ASSERTION lines are the property, the CONTROL lines the
instrument. Section 4.4 needs the operator at a browser; this plan is attended for that reason.

### 4.1 Floor - Flux / pod / version / probes

```bash
kubectl get helmrelease -n office mealie -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'
kubectl get pods -n office -l app.kubernetes.io/name=mealie -o custom-columns='NAME:.metadata.name,READY:.status.containerStatuses[0].ready,RESTARTS:.status.containerStatuses[0].restartCount,IMAGE:.status.containerStatuses[0].image'
kubectl exec -n office deploy/mealie -c main -- python3 -c "
import json,urllib.request; d=json.load(urllib.request.urlopen('http://127.0.0.1:9000/api/app/about')); print('version:',d.get('version'),'| oidc:',d.get('enableOidc'),'| tokenTime:',d.get('tokenTime'))"
curl -s -m 15 "https://$H/api/app/about" | python3 -I -c "import sys,json; d=json.load(sys.stdin); print('external version:', d.get('version'))"
```
**PASS:** `True` - `ready=true restarts=0 image=...mealie:v3.30.0` - `version: v3.30.0 | oidc: True | tokenTime: 8760` - `external version: v3.30.0`.
**Guards against:** `rollout status` green-lighting the OLD generation (feedback_rollout_status_old_generation) - the `version:` line is
read from the running process, not from the Deployment spec; and the external line proves the Gateway serves the NEW pod, not a
cached or stale endpoint. `tokenTime: 8760` shows `TOKEN_TIME` survived (persistent login, 2026-09-26).

### 4.2 CONTENTS ASSERTION 1 - the schema landed exactly and nothing was lost

> **CONTENTS ASSERTION:** the DB is at v3.30.0's Alembic head with precisely the new table, the seven new columns and the new enum
> value, and every pre-existing row count is unchanged - measured by the psql block below, compared to `$W/baseline.txt`.

```bash
kubectl exec -n office deploy/mealie-pg -- psql -U mealie -d mealie -At \
  -c "select 'alembic_head='||version_num from alembic_version" \
  -c "select 'tables='||count(*) from information_schema.tables where table_schema='public'" \
  -c "select 'new_tables='||count(*) from information_schema.tables where table_schema='public' and table_name='ai_prompt_overrides'" \
  -c "select 'new_cols='||count(*) from information_schema.columns where (table_name,column_name) in (('recipes','total_time_seconds'),('recipes','prep_time_seconds'),('recipes','perform_time_seconds'),('group_meal_plans','recipe_scale'),('group_meal_plans','end_date'),('household_preferences','mealplan_ical_token'),('recipe_instructions','duration_seconds'))" \
  -c "select 'enum_authmethod='||string_agg(enumlabel,',' order by enumsortorder) from pg_enum e join pg_type t on t.oid=e.enumtypid where t.typname='authmethod'" \
  -c "select 'recipes='||count(*) from recipes" -c "select 'users='||count(*) from users" \
  -c "select 'users_oidc='||count(*) from users where auth_method='OIDC'" -c "select 'groups='||count(*) from groups" \
  -c "select 'steps='||count(*) from recipe_instructions" -c "select 'mealplans='||count(*) from group_meal_plans" \
  -c "select 'ai_settings='||count(*) from ai_provider_settings" -c "select 'ai_prompt_overrides_rows='||count(*) from ai_prompt_overrides" \
  -c "select 'shopping_items='||count(*) from shopping_list_items" \
  -c "select 'ha_synced_rows='||count(*) from shopping_list_item_extras where key_name='ha_synced'" | tee "$W/after.txt"
```
**PASS - exactly:** `alembic_head=071e03b4f851` - `tables=70` (baseline 69 + 1) - `new_tables=1` - `new_cols=7` -
`enum_authmethod=MEALIE,LDAP,OIDC,REVERSE_PROXY` - `recipes`, `users`, `users_oidc`, `groups`, `steps`, `mealplans`, `ai_settings`,
`shopping_items`, `ha_synced_rows` all **identical** to `$W/baseline.txt` (184 / 2 / 1 / 1 / 1083 / 50 / 1 / 209 / 209 at write time) -
`ai_prompt_overrides_rows=0`.
**Guards against:** a head that stopped partway (Alembic can leave an intermediate head if the inner session commit of
27621d27c7e1 was real, 1.2); `tables=69` with `alembic_head` moved means a half-applied migration: **FAIL, section 5.** A missing
`REVERSE_PROXY` label means the enum revision did not run.

### 4.3 CONTENTS ASSERTION 2 - the time rewrite converted what it should and lost nothing; the sync read path survived

> **CONTENTS ASSERTION:** for each of total / prep / perform time, "rows still holding text" plus "rows holding seconds" equals the
> pre-upgrade count of non-empty texts (nothing vanished, nothing was invented); the ranges and `ca.` forms are untouched; known ISO
> forms became the exact seconds - measured by the SQL below, compared to `$W/baseline.txt`.

```bash
kubectl exec -n office deploy/mealie-pg -- psql -U mealie -d mealie -At \
  -c "select 'total_sum='||(count(*) filter (where total_time<>'')+count(total_time_seconds)) ||' seconds='||count(total_time_seconds) from recipes" \
  -c "select 'prep_sum='||(count(*) filter (where prep_time<>'')+count(prep_time_seconds)) ||' seconds='||count(prep_time_seconds) from recipes" \
  -c "select 'perform_sum='||(count(*) filter (where perform_time<>'')+count(perform_time_seconds)) ||' seconds='||count(perform_time_seconds) from recipes" \
  -c "select 'range_rows_still_text='||count(*) from recipes where total_time ~ '[0-9]-[0-9]' or prep_time ~ '[0-9]-[0-9]' or perform_time ~ '[0-9]-[0-9]'" \
  -c "select 'total_pt32h_converted='||count(*) filter (where total_time_seconds=115200 and total_time is null) from recipes" \
  -c "select 'prep_pt24h_converted='||count(*) filter (where prep_time_seconds=86400 and prep_time is null) from recipes" \
  -c "select 'iso_text_left='||count(*) from recipes where total_time ~* '^P' or prep_time ~* '^P' or perform_time ~* '^P'"
```
**PASS:** `total_sum=130`, `prep_sum=21`, `perform_sum=17` (equal to the baseline `total_text`/`prep_text`/`perform_text`; the `none` clearing
does not apply, baseline `none_text_rows=0`); the three `seconds=` figures are each **above the floor** (total >= 25, prep >= 15,
perform >= 15; at write time the convertible, non-range texts were 42 / 21 / 17) - a floor so a no-op migration cannot pass;
`range_rows_still_text=86` (the ranges stay text); `total_pt32h_converted` >= 1 and `prep_pt24h_converted` >= 1 (at write time one
recipe holds both a `PT32H` total, 115200 s, and a `PT24H` prep, 86400 s; if the data has moved, recompute the two expected values from
the 2.2 `iso_text_rows` and the actual texts) and `iso_text_left=0`.
**Guards against:** the migration silently doing nothing (floor), silently dropping text without writing seconds (sum < baseline), or
over-reaching into ranges (`range_rows_still_text` < 86). The `Converted N recipe times` log line is corroboration, not the gate.

Then the **sync read path** (the CronJob is still suspended) - the same reads `sync.py` makes, now against v3.30.0:

```bash
export MEALIE_TOKEN=$(kubectl get secret -n office mealie-shopping-sync -o jsonpath='{.data.MEALIE_TOKEN}' | base64 -d)
kubectl port-forward -n office svc/mealie 19000:9000 >/dev/null 2>&1 & PF=$!; sleep 3
python3 -I "$W/synccheck.py" http://127.0.0.1:19000 | tee "$W/sync-after.txt"
kill $PF 2>/dev/null; unset MEALIE_TOKEN
diff "$W/sync-before.txt" "$W/sync-after.txt" && echo SYNC_READ_PATH_IDENTICAL
```
**PASS:** `SYNC_READ_PATH_IDENTICAL` and `would_push=0` (`lists=1 items=209 ha_synced=209 ha_exclude=0 would_push=0`).
**Guards against:** `extras` no longer round-tripping through the shopping-list API (all stamped items would read `ha_synced=0` /
`would_push=209`, and releasing the CronJob would push 209 duplicates onto the Alexa list). Failing this is a **NO-GO for step 3.8**: leave the
CronJob suspended, keep the new pod if everything else is healthy, and decide with the operator whether to patch `sync.py` for the new
contract (a separate change) or roll back (section 5).

After step 3.8 has been pushed and Flux has applied it, prove the first real run:

```bash
kubectl get cronjob -n office mealie-shopping-sync -o jsonpath='suspend={.spec.suspend}{"\n"}'
# wait for the next */5 tick, then:
J=$(kubectl get jobs -n office --sort-by=.status.startTime -o name | grep mealie-shopping-sync | tail -1); echo "$J"
kubectl wait --for=condition=complete "$J" -n office --timeout=7m
kubectl logs -n office "$J" | tail -3
```
**PASS:** `suspend=<none>` or `false`; the Job is `Complete`; the log ends `done: pushed=0 already-synced=209 excluded=0 lists=1`
(`pushed` must be 0 unless `sync-before.txt` showed `would_push` > 0; `lists=1`). **Guards against:** a sync that "succeeds" while reading nothing
(`lists=0` or `already-synced` collapsing to 0) - the line carries both numbers.

### 4.4 CONTENTS ASSERTION 3 - the login path the library bump rides (operator at a browser)

> **CONTENTS ASSERTION:** a real OIDC login through Authentik completes end to end on v3.30.0 with the unchanged authorize request -
> measured by a mechanical authorize-redirect diff (no credentials) AND a browser login by an Authentik `mealie-users` member whose
> callback is logged 200, compared to `$W/oauth-before.txt` and the 2.5 discovery probe.

Mechanical half (proves discovery, client registration and PKCE configuration after the authlib bump, with no credentials):

```bash
curl -s -m 15 -o /dev/null -D - "https://$H/api/auth/oauth" | tr -d '\r' | grep -i -E '^(HTTP|location)' \
  | sed -E 's/(state|nonce|code_challenge)=[^&]*/\1=X/g' > "$W/oauth-after.txt"
diff "$W/oauth-before.txt" "$W/oauth-after.txt" && echo AUTHORIZE_REQUEST_IDENTICAL
```
**PASS:** `AUTHORIZE_REQUEST_IDENTICAL` (same status, same Authentik host, same `client_id`, `redirect_uri`, `scope`,
`code_challenge_method=S256`). The normaliser was proven stable by running it twice against v3.28.0 (identical output), so a non-empty
diff is a real change, not noise. **Guards against:** the OIDC client failing to register (the route would answer 500 `Could not initialize
OAuth client`) or a changed scope/redirect.

Human half - **the operator, not the agent**:

1. Open `https://<mealie host>`, click *Login with Authentik*, complete the flow as a `mealie-users` member (one of the two existing users).
   **PASS:** lands on the Mealie home page, signed in; the recipe list is non-empty.
2. In the browser devtools, Application -> Cookies: `mealie.access_token` expires about **one year** out (Max-Age near 31536000), not
   "Session". **PASS:** persistent. **Guards against:** `OIDC_REMEMBER_ME` regressing the 2026-09-26 persistent-login fix (a session cookie
   logs the iOS PWA out on every close).
3. Mechanically, within a few minutes of that login:

```bash
kubectl logs -n office deploy/mealie -c main --since=15m | grep -E 'oauth/callback' | tail -3
kubectl logs -n office deploy/mealie -c main --since=15m | grep -ciE 'OIDC.*(not present|missing|failed|error|refus)|Traceback' || true
kubectl exec -n office deploy/mealie-pg -- psql -U mealie -d mealie -At -c "select 'users='||count(*) from users" -c "select 'users_oidc='||count(*) from users where auth_method='OIDC'"
```
**PASS:** the `GET /api/auth/oauth/callback?code=...` line ends `200 OK` (the route returns the token JSON; a 401 is a rejected
login, a 500 a library failure); the error grep prints **0** (it is case-insensitive and matches the upstream
`[OIDC] Required claims not present in ID token or userinfo endpoint` wording); `users=2` and `users_oidc=1` (an existing account was
matched; a third user would mean the claim mapping changed and auto-provisioned a duplicate).
**If the callback is 401/500 or the claims error appears:** this is the authlib bump or the `email_verified` handling. Do **not**
reach for `HTTP_ALLOW_LIST` or loosen `OIDC_REQUIRES_EMAIL_VERIFICATION`; go to section 5.

### 4.5 CONTENTS ASSERTION 4 - the new auth/exposure surface shipped OFF on the internet-facing route

> **CONTENTS ASSERTION:** the reverse-proxy login endpoint answers `404` from the application and no household has an iCal token -
> measured from outside through the Gateway with a spoofed `X-Forwarded-User`, and by SQL, compared to the `200 text/html` SPA
> fallback recorded in 2.5 (the route did not exist on v3.28.0).

```bash
curl -s -m 15 -D - -o /dev/null -H 'X-Forwarded-User: probe' "https://$H/api/auth/reverse-proxy" | tr -d '\r' | grep -i -E '^(HTTP|content-type)' | tee "$W/revproxy-after.txt"
curl -s -m 15 -H 'X-Forwarded-User: probe' "https://$H/api/auth/reverse-proxy" | grep -c access_token || true
kubectl exec -n office deploy/mealie-pg -- psql -U mealie -d mealie -At -c "select 'ical_tokens_set='||count(*) from household_preferences where mealplan_ical_token is not null"
```
**PASS:** `HTTP/2 404` and `content-type: application/json` (so the route exists in this build, the app is the one answering, and it is
disabled); the `access_token` grep prints **0**; `ical_tokens_set=0`.
**FAIL:** `200`, a token in the body, or `401` (401 means the endpoint is ENABLED and rejecting only for lack of a header - someone
set `REVERSE_PROXY_AUTH_ENABLED`; remove it before anything else, this is an authentication-bypass surface on a public host).
A `200 text/html` here means the old image is still serving.

### 4.6 Settle, alerts, instruments

> **CONTROL:** alertname MealiePodNotReady - not firing 10 minutes after the rollout (rule exists in `mealie-alerts.yaml`; loaded state `inactive`).
> **CONTROL:** alertname MealiePodCrashLooping - not firing 10 minutes after the rollout.
> **CONTROL:** alertname KubeJobFailed - no `office` Job failed (the CronJob was suspended across the Recreate hole, so none is expected).
> **CONTROL:** metric kube_pod_status_ready - exactly one `mealie-<hash>-*` series with value 1 after the rollout (floor, not just "no alert").
> **CONTROL:** metric kube_cronjob_status_last_successful_time - for `office/mealie-shopping-sync` the value is greater than `T0` from step 3.5 once the 4.3 Job completed.

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 4
for q in 'ALERTS{alertname=~"Mealie.*|KubeJobFailed",alertstate="firing",namespace="office"}' \
         'kube_pod_status_ready{namespace="office",pod=~"mealie-[0-9a-f]+-.*",condition="true"}' \
         'kube_cronjob_status_last_successful_time{namespace="office",cronjob="mealie-shopping-sync"}' \
         'up{job="kube-state-metrics"}'; do
  printf '%s => ' "$q"; curl -s -G localhost:19090/api/v1/query --data-urlencode "query=$q" | python3 -I -c "import sys,json; r=json.load(sys.stdin)['data']['result']; print(len(r), [x['value'][1] for x in r][:3])"
done
kill $PF 2>/dev/null
runbooks/update-marker.sh clear mealie
```
**PASS:** line 1 `0 []`; line 2 `1 ['1']`; line 3 one series whose value is greater than `T0`; line 4 (the positive control, kube-state-metrics itself) at least one series with value 1 - proof the
instrument answers, so the `0 []` above is a real zero and not an unreachable Prometheus. Wait >= 10 minutes after Ready before reading
line 1. These queries were run against the live instrument on 2026-11-02 (rules loaded and `inactive`; the metrics return series).

### 4.7 The security outcome (the reason for the window)

> **CONTENTS ASSERTION:** the property that rates F-c0bd7eb7 critical no longer holds for the image that is now running - measured by
> scanning the running tag and intersecting the result with the CISA known-exploited feed (empty is the PASS), with an injected-ID
> control proving the check can fail.

```bash
kubectl get pods -n office -l app.kubernetes.io/name=mealie -o jsonpath='{.items[0].status.containerStatuses[0].image}{" "}{.items[0].status.containerStatuses[0].imageID}{"\n"}'
curl -s -m 60 https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json -o "$W/kev.json"
mise exec -- trivy image --quiet --scanners vuln --severity CRITICAL --ignore-unfixed -f json -o "$W/live.json" ghcr.io/mealie-recipes/mealie:v3.30.0
python3 -I - "$W/live.json" "$W/kev.json" <<'PY'
import json,sys,copy
scan,kevf=sys.argv[1:3]
kev={v['cveID'] for v in json.load(open(kevf))['vulnerabilities']}
doc=json.load(open(scan))
def hits(d):
    return sum(1 for r in d.get('Results') or [] for x in (r.get('Vulnerabilities') or []) if x['VulnerabilityID'] in kev)
inj=copy.deepcopy(doc)
inj.setdefault('Results',[{}])
inj['Results'][0].setdefault('Vulnerabilities',[])
inj['Results'][0]['Vulnerabilities']=(inj['Results'][0]['Vulnerabilities'] or [])+[{'VulnerabilityID':sorted(kev)[0]}]
print('kev_hits=%d control_injected_delta=%d kev_feed_entries=%d' % (hits(doc), hits(inj)-hits(doc), len(kev)))
PY
```
**PASS:** the pod image is `...mealie:v3.30.0`; `kev_hits=0`, `control_injected_delta=1` and `kev_feed_entries` > 1000 (measured 2026-11-02 on
v3.30.0: `kev_hits=0 control_injected_delta=1 kev_feed_entries=1766`). **The control makes it fail-able:** a truncated feed, an empty scan or a broken
script would print `control_injected_delta=0` or a tiny `kev_feed_entries`, which voids the PASS. Do **not** require an empty scan (1.1). The sweep's own security-check re-scans the running image on its next cycle and resolves F-c0bd7eb7 itself; do not
hand-close the finding (agent-authored closes are not trusted, `finding close` is for rows this plan authored, and this plan authored none).

## 5) Rollback

**Read 1.4 first.** The first action is always to read the head, because it picks the branch:

```bash
kubectl exec -n office deploy/mealie-pg -- psql -U mealie -d mealie -At -c "select 'alembic_head='||version_num from alembic_version"
```

**5.1 Head is still `3527efeeec34`** (the migration never committed, e.g. a failure before or during it): a plain revert suffices.

```bash
git revert --no-edit HEAD            # if only step 3.5 was pushed; if 3.8 was pushed too: git revert --no-edit HEAD HEAD~1
git show --stat HEAD                 # exactly helmrelease.yaml (+ shopping-sync-cronjob.yaml)
git push origin main
```
The revert restores tag v3.28.0, `retries: 3` and the unsuspended CronJob in one step. Confirm per 5.4.

**5.2 Head moved (`27621d27c7e1` through `071e03b4f851`, or anything not `3527efeeec34`): revert + a DB step. Pick ONE.**

*Option B - exact restore from the 3.2 dump (AUTHORITATIVE; loses anything written after the dump, which is minutes of an attended window).*

```bash
# 1. stop the new pod by reverting the manifest (Recreate removes v3.30.0; v3.28.0 will then crash-loop on the unknown head - expected)
git revert --no-edit HEAD            # or HEAD HEAD~1 if 3.8 was pushed
git show --stat HEAD && git push origin main
kubectl get pods -n office -l app.kubernetes.io/name=mealie     # wait until the new pod is Error/CrashLoopBackOff, i.e. holds no sessions
# 2. make sure the dump is in the pod (the pod's /tmp copy survives unless mealie-pg restarted)
kubectl exec -n office deploy/mealie-pg -- ls -l /tmp/mealie-pre-v3.30.0.dump \
  || kubectl exec -i -n office deploy/mealie-pg -- sh -c 'cat > /tmp/mealie-pre-v3.30.0.dump' < "$DUMP"
echo "pod  =$(kubectl exec -n office deploy/mealie-pg -- sha256sum /tmp/mealie-pre-v3.30.0.dump | cut -d' ' -f1)"
echo "local=$(shasum -a 256 "$DUMP" | cut -d' ' -f1)"          # must be equal
# 3. rebuild the database from the dump (drops EVERYTHING, including the new table, columns and enum value - that is the point)
kubectl exec -n office deploy/mealie-pg -- sh -c 'dropdb -U mealie --force mealie && createdb -U mealie mealie && pg_restore -U mealie -d mealie --no-owner --exit-on-error /tmp/mealie-pre-v3.30.0.dump'
# 4. verify against the 3.2 sidecar
kubectl exec -n office deploy/mealie-pg -- psql -U mealie -d mealie -At \
  -c "select 'alembic_head='||version_num from alembic_version" -c "select 'recipes='||count(*) from recipes" \
  -c "select 'users='||count(*) from users" -c "select 'tables='||count(*) from information_schema.tables where table_schema='public'" \
  -c "select 'enum_authmethod='||string_agg(enumlabel,',' order by enumsortorder) from pg_enum e join pg_type t on t.oid=e.enumtypid where t.typname='authmethod'" \
  -c "select 'total_text='||count(*) from recipes where total_time<>''"
# 5. let v3.28.0 come up: delete the crash-looping pod once (safe under Recreate + single replica + RWO)
kubectl delete pod -n office -l app.kubernetes.io/name=mealie
kubectl rollout status deploy/mealie -n office --timeout=10m
```
**Expected step 4:** `alembic_head=3527efeeec34`, `recipes`/`users`/`total_text` equal to `$DUMP.counts.txt`, `tables=69`,
`enum_authmethod=MEALIE,LDAP,OIDC`. `dropdb --force` is deliberate: it terminates the crash-looping pod's reconnect attempts, which would
otherwise make a plain `dropdb` race. **Why not `pg_restore --clean`:** it drops only objects present in the dump, so the new
`ai_prompt_overrides` table (which has a foreign key to `ai_provider_settings`) would block the drop of its parent and the new columns
and enum value would survive - a half-old schema. Rebuilding the database avoids that.

*Option A - `alembic downgrade` on the running v3.30.0 pod (keeps writes made since the upgrade; NOT rehearsed; only with an explicit
operator GO and only if the v3.30.0 pod still starts).*

```bash
kubectl exec -n office deploy/mealie -c main -- python3 -c "
from alembic import command; from alembic.config import Config
from mealie.db.init_db import ALEMBIC_DIR
command.downgrade(Config(str(ALEMBIC_DIR / 'alembic.ini')), '3527efeeec34')"
```
Cost, stated up front: `27621d27c7e1`'s downgrade rewrites time text in ENGLISH (`PT32H` -> `1 day 8 hours`, German texts -> English), the enum value
`REVERSE_PROXY` stays, and `3697d65c5f92`/`071e03b4f851` have no downgrade. After it, revert the manifest as in B step 1 and delete the pod.
If this fails or leaves the head anywhere other than `3527efeeec34`, fall back to Option B (the dump is unaffected).

**5.3 After any rollback** keep the CronJob unsuspended only once v3.28.0 is serving and 5.4 passes (a sync against a crash-looping app is
harmless - it fails closed - but a sync during the restore window reads a half-built DB). A re-attempt needs a FRESH 3.2 dump and the
sidecar re-taken; do not reuse the old dump after the rolled-back DB has taken new writes.

**5.4 Confirm the cluster is back, by the cluster and not by `git log`:**

```bash
kubectl get deploy -n office mealie -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'     # ...:v3.28.0
kubectl exec -n office deploy/mealie -c main -- python3 -c "
import json,urllib.request; print(json.load(urllib.request.urlopen('http://127.0.0.1:9000/api/app/about')).get('version'))"   # v3.28.0
kubectl exec -n office deploy/mealie-pg -- psql -U mealie -d mealie -At -c "select version_num from alembic_version"          # 3527efeeec34
kubectl get cronjob -n office mealie-shopping-sync -o jsonpath='suspend={.spec.suspend}{"\n"}'                            # not true
```
plus the 4.4 browser login (the old build must still log in), the 4.3 sync read path, and `runbooks/update-marker.sh clear mealie`.
Record the failure on the plan (`status: blocked`) with the first error line; do not re-attempt in the same window.

## 6) Interference notes

- **Window recommendation (the finding is a live critical: do not queue it behind routine work).** Class derives HUMAN-GATED
  (`capability_change: true`), so **the nightly window is out** and an operator must be present for 4.4 (a real login cannot be
  automated; there is no service-account login to Authentik). In order of preference:
  1. **An on-demand NOW run** (`home-operation run`, `on_demand: now`, 480 min ceiling, serial, attended) the day the operator can sit
     through 45 minutes. Nothing else is stamped for it. Plans needing a stamp use `run-now.py stamp`, never a hand-written `now:` ref.
  2. **`sat-attended:2026-11-07`** (the soonest attended slot): holds `helm-drift-detection` (60 min, medium) and the slot's schedulable
     budget is 70 min (90 - 20 Step-0 reserve), so both do not fit (60 + 45). Moving `helm-drift-detection` to a later Saturday is an
     **operator decision**; its conflicts_with already pairs it with other plans, and it rewrites THIS HelmRelease, so sharing a slot
     with it would also confound attribution. Not stamped by this plan.
  3. Not recommended: `sun-attended:2026-11-08` (`etcd-timeouts-5000-500`, restarts etcd on every control-plane node, backup-restore class
     stacking, and the Talos plan's recommended slot) and `sat-attended:2026-11-14` (`python-fleet-3.15.2` edits the same Flux
     Kustomization and CronJob file). Waiting for 11-14 means two more weeks on an open critical finding.
- **Operator decision - exposure while waiting.** If no slot is available within the week, the compensating controls in scope are
  dropping the `envoy-external` parent from `httproute/mealie` (keeping `envoy-internal`) or leaving it as accepted under AR-007. Rebuilding or
  patching the image is out of scope (operator rule). This plan does not choose; it only says the choice exists.
- **Single-slot rollback budget.** `rollback_class: backup-restore` plans are never stacked in one slot (see `conflicts_with`). Option B
  costs ~15 minutes; the slot must have it.
- **Outage:** 1-3 minutes, hard, internet-facing (Recreate on an RWO volume; the startup probe allows 10 minutes for the migration, the
  HelmRelease 15). Expect a handful of 502/503 from `envoy-external` and `MealiePodNotReady` pending (it fires only after `for: 5m`).
- **Expected noise, not regressions:** `MealiePodRestarted` (`for: 1m`) can flag once; the marker from 3.1 covers it. The CronJob is suspended
  across the hole, so no `KubeJobFailed` is expected. The first post-bump access-log lines show a real client IP instead of the Envoy pod
  (the `HOST_IP` default change, 1.3) - not a fault.
- **The `HTTP_ALLOW_LIST` / `REVERSE_PROXY_AUTH_*` / `HOST_IP` temptation.** If anything looks wrong, release notes and issues will
  suggest env vars. Do not set any of them unless a gate has PROVEN the need; each one widens an SSRF or authentication surface on a public host.
- **Shared instrument:** section 4 reads Prometheus. A same-night `kube-prometheus-stack` bump would blind 4.6; none is open, and the
  field above must be updated if one is filed.
- **Reciprocity owed:** `python-fleet-3.15.2` must list `mealie-3.30.0` in its own `conflicts_with` (this plan lists it; the validator does
  not check the other direction). I may not edit another plan from this dispatch; the window agent or the sweep should.
- **This plan closes nothing by itself.** F-c0bd7eb7 resolves when the sweep re-scans the running image (4.7); F-9848e326 when the version
  row disappears from the next snapshot; F-655a9c6c is only half answered (homepage is a different component).

### Duration against the slot

| Phase | Min |
|---|---:|
| 2 pre-checks incl. premises, DB baseline, sync and OIDC baselines | 10 |
| 3.1-3.2 marker, dump, sha256, in-pod list, scratch-DB restore proof | 8 |
| 3.3-3.5 two edits, commit, push | 3 |
| 3.6 webhook -> Flux -> Recreate -> 9 revisions -> Ready | 6 |
| 4 verification incl. the operator's real login | 12 |
| 3.8 release guards, first real sync tick, settle, scan | 6 |
| **Total** | **45** |

Rollback adds ~15 min (revert, dump restore, pod restart, re-verify incl. a login).
