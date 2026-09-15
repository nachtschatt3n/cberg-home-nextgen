---
plan_id: mealie-v3.26.0
component: mealie
pr: null                              # direct-bump lane item (coverage.py) — no Renovate PR
kind: image
current: "v3.25.1"                    # live on deployment/mealie, verified 2026-09-15
target: "v3.26.0"                     # ghcr.io/mealie-recipes/mealie:v3.26.0, manifest HTTP 200
                                      # (negative control v9.9.9 -> 404), verified 2026-09-15
update_type: minor
risk: low                             # the hold reason (outbound-request guard) is a NO-OP for
                                      # this deployment — see §1. Residual risk is the ordinary
                                      # "minor with 4 additive Alembic revisions" risk, and the
                                      # one real trap is in ROLLBACK (§5), not in the upgrade.
est_duration_min: 25
needs_reboot: false
touches:
  namespaces: [office]
  resources:
    - helmrelease/mealie              # image tag edit
    - deployment/mealie               # Recreate (single replica, RWO PVC) — ~1-2 min outage
    - pvc/mealie-data                 # read by the image-backfill migration (§1.3); not written
    - deployment/mealie-pg            # NOT restarted. Schema migrated in place by Mealie's
                                      # startup Alembic: +3 tables, +2 nullable columns,
                                      # +1 data reconcile on recipes.image
    - pvc/mealie-pg-data              # the schema change above lands here
  shared: []                          # no gateway/envoy, cert-manager, cilium, coredns, shared
                                      # DB or longhorn perturbation. httproute/mealie untouched.
                                      # Authentik is a READ dependency of §4 verification only.
depends_on: []
conflicts_with:
  - authentik-pg18-lockstep           # §4.4 proves the OIDC login path end to end; a window
  - authentik-pg17-decommission       # that is also moving the auth DB confounds that proof
capability_change: true               # user-visible: ingredient substitutions, note-to-step
                                      # linking, OIDC avatars, bottom-sheet UI, meal-plan rule
                                      # filtering — plus an in-app ANNOUNCEMENT ("outbound
                                      # request protection") every user sees on first load, and
                                      # a capability RESTRICTION (private-network targets are
                                      # now refused). Same bar as nocodb-2026.09.0.
rollback_class: backup-restore        # HONEST RATING. A plain `git revert` does NOT restore
                                      # service: v3.25.1's startup runs an unguarded
                                      # `alembic upgrade head` against a DB stamped with a
                                      # revision it has never heard of, and crash-loops. Every
                                      # rollback needs a DB step (§5) — stamp reset or dump
                                      # restore — which is why the gate below is mandatory.
backup_gate: "pg_dump -Fc of the `mealie` database taken from the LIVE deploy/mealie-pg pod
  BEFORE the tag edit is pushed, verified by `pg_restore -l` listing >= 60 TABLE DATA entries
  and a non-trivial file size, with the pre-upgrade counts (alembic head 69e942bab3aa,
  recipes, users, notes, public tables) captured to a sidecar file for the §4 contents diff.
  The 03:0x Longhorn backup of mealie-pg-data is NOT a substitute: it is block-level and
  predates nothing useful here — the dump is what makes §5 option B exact."
security_ref: null                    # no security driver on OUR side; upstream's SSRF
                                      # hardening is the reason for the hold, not a finding
finding_refs:
  - F-ec4c1644                        # "coverage.py direct-bump lane has NO G3 breaking-change
                                      #  gate … mealie v3.25.1 -> v3.26.0 rated AUTO". Status
                                      #  RESOLVED 2026-09-15 (cd163006: the direct-bump breaking
                                      #  gate in coverage.py + DirectBumpBreakingGateTest in
                                      #  runbooks/tests/test-coverage-lane-safety.py + the
                                      #  auto-update.md correction). Kept as the ownership link
                                      #  for the HELD ITEM this plan disposes of; there is
                                      #  nothing left to close. See §6.
status: awaiting-go   # OPERATOR GO 2026-09-15 (direct, attended update in its window; recorded in home-operation, exec_state=pending). REVIEWED 2026-09-15, corrections c36388bc
window: "sat-attended:2026-09-26"   # assigned 2026-09-15 from the review synthesis (capacity-checked); go/no-go via home-operation
                                      # against 90). capability_change:true => human-gated, so
                                      # sat-attended / sun-attended, not nightly unattended.
premises:
  - id: live-image-is-still-v3.25.1
    why: >-
      `current:` claims v3.25.1. If the cluster already moved (a later coverage.py
      direct-bump, a hand-applied bump), this plan's diff, its §4 baselines (alembic head,
      table count, backfill prediction) and its §5 rollback target are all stale.
    run: kubectl get deploy -n office mealie -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: ghcr.io/mealie-recipes/mealie:v3.25.1
  - id: git-pin-is-still-v3.25.1
    why: >-
      §3.3 edits exactly one line. If the pin in git already differs from v3.25.1 the
      sed is a no-op and the commit is empty — better to refuse than to "upgrade" nothing.
    run: "git show HEAD:kubernetes/apps/office/mealie/app/helmrelease.yaml | grep -c 'tag: v3.25.1'"
    expect_exact: "1"
  - id: no-http-allow-list-and-oidc-still-on
    why: >-
      §1.2's verdict ("no HTTP_ALLOW_LIST needed") was derived for the env as measured:
      OIDC via authlib, no allow list set. If someone has since ADDED HTTP_ALLOW_LIST, or
      REMOVED OIDC, the §4.4 login assertion and the §1.2 reasoning must be re-derived
      before executing. Negative lookahead on the env-name list keeps this fail-closed.
    run: kubectl get deploy -n office mealie -o jsonpath='{.spec.template.spec.containers[0].env[*].name}'
    expect_matches: '^(?!.*HTTP_ALLOW_LIST)(?=.*OIDC_CONFIGURATION_URL)(?=.*OIDC_AUTH_ENABLED).*$'
  - id: oidc-discovery-url-still-points-at-the-authentik-app
    why: >-
      §1.2 rests on the discovery URL being served by Authentik behind the external
      Gateway (resolves to 192.168.55.104 from inside the pod). If it were repointed —
      e.g. at the in-cluster authentik-server Service — the "private address" question
      changes shape and the avatar self-allow-list host changes with it.
    run: kubectl get deploy -n office mealie -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="OIDC_CONFIGURATION_URL")].value}'
    expect_contains: /application/o/mealie/.well-known/openid-configuration
  - id: mealie-pg-is-still-the-standalone-postgres-18
    why: >-
      §3.2 (dump), §4.2 (schema diff) and §5 (stamp reset / restore) all `kubectl exec`
      into deploy/mealie-pg with `-U mealie -d mealie`. If the DB was replatformed those
      commands would target the wrong server or fail closed.
    run: kubectl get deploy -n office mealie-pg -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_contains: "postgres:18."
  - id: helmrelease-still-on-app-template-5.x
    why: >-
      The values path §3.3 edits (`controllers.main.containers.main.image.tag`) and the
      rendered `strategy: Recreate` guard (docs/sops/longhorn-rwo-multi-attach.md) belong
      to the app-template 5.x schema. A chart major in between would move both.
    run: kubectl get helmrelease -n office mealie -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: "5.1.0"
  - id: recipe-data-pvc-is-bound
    why: >-
      Migration 4b91d3a7c0e2 reconciles `recipes.image` against files on the data
      volume. Its own guard skips the CLEARING half if it sees no image files at all —
      but only if the volume is absent entirely. A Bound-but-wrong volume would clear
      every image reference. §2.4 measures the file count; this asserts the claim.
    run: kubectl get pvc -n office mealie-data -o jsonpath='{.status.phase}'
    expect_exact: Bound
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/backup.md
  - docs/sops/authentik.md
  - docs/sops/longhorn-rwo-multi-attach.md
generated: "2026-09-15"
---

# Mealie — image v3.25.1 → v3.26.0

## 1) Summary & why held

Bump `ghcr.io/mealie-recipes/mealie` from **v3.25.1** to **v3.26.0** (76 upstream
commits) in `kubernetes/apps/office/mealie/app/helmrelease.yaml`. One line changes.
The pod is `Recreate`d (single replica on the RWO Longhorn PVC `mealie-data`); Mealie's
startup runs four additive Alembic revisions against the standalone `mealie-pg`
(`postgres:18.6-bookworm`, PVC `mealie-pg-data`), which is not restarted.

**Why it was held.** `coverage.py` rated this AUTO (mealie is on the policy `age_waive`
list, so no G5 cooldown) — but the direct-bump lane applies no G3 breaking-change scan
on its regular path (**F-ec4c1644**), and the v3.26.0 release notes open with:

> **BREAKING CHANGE** — Mealie now checks where its own outgoing requests are going.
> Anything the server fetches on your behalf, such as importing a recipe from a URL,
> downloading a recipe image, sending a webhook, or running a recipe action, is only
> allowed to reach addresses on the public internet. […] Users requiring private network
> access must explicitly allowlist targets using the `HTTP_ALLOW_LIST` environment
> variable, which accepts hostnames or CIDR ranges.

Upstream PR: mealie-recipes/mealie#7914 *"fix: harden server-initiated HTTP against SSRF
and DNS rebinding"* (merged 2026-09-04). The window agent held it manually on 2026-09-15
and asked one precise question, answered in §1.2.

### 1.1 What #7914 actually wraps — read from the PR's file list and the v3.26.0 source

The PR touches exactly these runtime files (`gh api …/pulls/7914/files`):

| File | What it does now |
|---|---|
| `mealie/pkgs/safehttp/transport.py` | `SafeTransport` / `AsyncSafeTransport`: resolve once, reject private/loopback/link-local/CGNAT/multicast/reserved (incl. IPv4-mapped IPv6), pin via curl `RESOLVE`, re-validate per redirect hop. Allow/deny lists: `_matches()` is an **exact lowercase hostname match OR resolved-IP-in-CIDR**. Deny > allow > default. |
| `mealie/pkgs/safehttp/fetch.py`, `__init__.py` | scraper fetch path (recipe import from URL, recipe image download) — already guarded before, now pinned |
| `mealie/services/event_bus_service/publisher.py` | **webhooks** moved from raw `requests.post` to `safehttp.post` |
| `mealie/routes/households/controller_group_recipe_actions.py` | **recipe actions** likewise |
| `mealie/core/security/providers/openid_provider.py` | **only the OIDC *avatar* fetch** (`picture` claim, new feature #7624) goes through `SafeTransport` |
| `mealie/core/settings/settings.py` | `HTTP_ALLOW_LIST: str = ""`, `HTTP_DISALLOW_LIST: str = ""` (comma-separated hosts or CIDRs) |
| frontend `…/Announcements/2026-09-04_1_outbound-request-protection.vue` | in-app announcement shown to users |

Explicitly **not** covered (PR body): Apprise notifications (third-party library).

### 1.2 THE OIDC QUESTION — does the guard cover discovery / token / userinfo? **No.**

Measured from inside the running pod on 2026-09-15: the OIDC discovery host
(`auth.${SECRET_DOMAIN}`) resolves to **`192.168.55.104`** — the `envoy-external`
Gateway's LAN IP, via the CoreDNS split-horizon forward to k8s-gateway at `.101`. That is
an RFC1918 address, so **if** the guard wrapped the OIDC client, every login would fail
with `invalid request on local resource`. It does not, for three reasons that are each
sufficient on their own:

1. **`mealie/routes/auth/auth.py` is not in the PR.** At v3.26.0 it still builds the client
   as `authlib.integrations.starlette_client.OAuth().register("oidc",
   server_metadata_url=settings.OIDC_CONFIGURATION_URL, client_kwargs=…)`. Discovery
   (`load_server_metadata()`), the authorization redirect, the code→token exchange
   (`authorize_access_token` / `fetch_access_token`) and `userinfo()` all run on
   **authlib's own httpx client** with no custom transport. `grep safehttp auth.py` → 0
   hits. Nothing in the PR monkeypatches httpx globally.
2. **The one OIDC path that IS wrapped self-allow-lists the provider.**
   `OpenIDProvider._picture_allow_hosts()` appends
   `urlparse(settings.OIDC_CONFIGURATION_URL).hostname` to the allow list, with the
   upstream comment *"The provider's own host is one: Mealie already contacts it on every
   login, and self-hosted setups routinely run it on a private network."* So even an
   avatar hosted on the Authentik hostname would be fetched.
3. **Avatar failure can never fail a login.** `_update_profile_image_from_claim()` returns
   early when there is no `picture` claim and wraps the whole fetch in
   `except Exception: logger.debug(...)`. Authentik's managed `profile` scope emits
   `name / given_name / preferred_username / nickname / groups` — **no `picture`** — so
   with `OIDC_SCOPES_OVERRIDE: "openid email profile"` this branch does not even fire.

**Verdict: `HTTP_ALLOW_LIST` is NOT required, and this plan deliberately does NOT set it.**
Adding `auth.${SECRET_DOMAIN}` or `192.168.55.0/24` would buy nothing for login (the
authlib path ignores the list) while re-opening exactly the SSRF surface upstream just
closed — a user-supplied recipe-import / webhook / recipe-action URL could then be pointed
at the external Gateway (or the whole VLAN). The only thing the list would change for us
is the avatar path, which is already self-allowed. §3.3 records this as a comment next to
the tag so the next reader does not "fix" the upstream warning by adding it.

*(The first-pass web summary of the PR claimed it covered "OIDC discovery and
token/userinfo endpoints". That claim is wrong; it was checked against the source, which
is why this section quotes files and functions rather than the summary.)*

### 1.3 Every other outbound surface, measured

| Surface | How we use it | Measured 2026-09-15 | Impact |
|---|---|---|---|
| Webhooks | not configured | `webhook_urls` = **0** rows | none |
| Recipe actions | not configured | `recipe_actions` = **0** rows | none |
| Event notifiers (Apprise) | not configured; not covered by the guard anyway | `group_events_notifiers` = **0** | none |
| Recipe import from URL / image download | public recipe sites, by hand | n/a | unchanged (already guarded, now pinned) |
| `runbooks/mealie-import.py` | pushes parsed recipes INTO Mealie via `/api/recipes` (inbound) | — | none |
| `mealie-shopping-sync` CronJob | separate pod calling Mealie + HA (inbound to both) | `*/5 * * * *` | none from the guard; sees a 1-2 min hole during Recreate (§6) |
| Home Assistant → Mealie | inbound | — | none |
| OpenAI / SMTP | unset (`OPENAI_BASE_URL`, `SMTP_HOST` absent) | — | none |

**So the hold reason is a no-op for this deployment: `risk: low`.** The hold itself was
still correct — the lane had no way to know any of the above, and the plan file is what
routes this item to the PLAN lane instead of unattended AUTO. Still written, per the rule.

### 1.4 What the minor actually brings that is NOT a no-op

Four Alembic revisions land at startup (chain verified from the migration files):

```
69e942bab3aa  (current DB head — equals v3.25.1's newest script)
  └─ b3f1c9a27d84  users.external_avatar_hash  (nullable column)
     └─ f2191b69db2e  +ingredient_foods_substitutions, +recipes_ingredients_substitutions
        └─ 4b91d3a7c0e2  backfill recipes.image from disk  (DATA reconcile, downgrade = no-op)
           └─ 3527efeeec34  +recipe_note_ref_link, notes.reference_id  (nullable)  ← v3.26.0 head
```

`4b91d3a7c0e2` is the one to watch. It walks `SELECT id, image FROM recipes`, checks
`/app/data/recipes/<id>/images/original.webp` on the PVC, restores a missing key where a
file exists and **clears** the key where no file exists. Its guard only holds the clearing
half back when *no* recipe has a file at all. Measured baseline: **173 recipes, 173 with an
image key, 173 `original.webp` on disk** → the predicted log line is
`Recipe image backfill checked 173 recipes: 0 image references restored, 0 cleared`.
§4.3 asserts exactly that.

And the rollback trap (§5): `mealie/db/init_db.py::main()` compares the DB's Alembic head
with the scripts shipped in the image and, on mismatch, calls `command.upgrade(cfg, "head")`
**unguarded**. v3.25.1 has no script for `3527efeeec34`, so it raises and the container
exits. A `git revert` alone therefore yields a CrashLoopBackOff, not a rollback.

## 2) Pre-checks

Run inside the window. Every check has a pass condition; a fail is a no-go.

```bash
cd /Users/mu/code/cberg-home-nextgen
export KUBECONFIG="$PWD/kubeconfig"
```

**2.0 — Premises, mechanically.** These are the frontmatter assertions; the checker is
read-only by construction.

```bash
.venv/bin/python3 runbooks/plan-premises.py mealie-v3.26.0 --require-premises
```
**PASS:** exit 0, 7/7 passed.

**2.1 — Flux green, pod steady, no other office/auth plan mid-flight.**

```bash
mise exec -- flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
mise exec -- flux get helmreleases   -A | awk 'NR==1 || $5 != "True"'
kubectl -n office get pods -l app.kubernetes.io/name=mealie -o wide
kubectl -n office get pods -l app=mealie-pg
python3 runbooks/maintenance-plan.py --open | grep -E 'authentik|mealie'
```
**PASS:** both flux lists print only the header; `mealie-*` pod `1/1 Running`, restarts 0;
`mealie-pg-*` `1/1 Running`; no `authentik-pg*` plan shares this window (`conflicts_with`).

**2.2 — The DB reads that cannot be premises** (they need `kubectl exec`, which the
premise allowlist refuses on purpose). Record the output — §4.2 diffs against it.

```bash
kubectl -n office exec deploy/mealie-pg -- psql -U mealie -d mealie -At \
  -c "select 'alembic_head='||version_num from alembic_version" \
  -c "select 'webhook_urls='||count(*) from webhook_urls" \
  -c "select 'recipe_actions='||count(*) from recipe_actions" \
  -c "select 'notifiers='||count(*) from group_events_notifiers" \
  -c "select 'recipes='||count(*) from recipes" \
  -c "select 'recipes_with_image='||count(*) from recipes where image is not null and image <> 'no image'" \
  -c "select 'users='||count(*) from users" \
  -c "select 'users_oidc='||count(*) from users where auth_method='OIDC'" \
  -c "select 'notes='||count(*) from notes" \
  -c "select 'tables='||count(*) from information_schema.tables where table_schema='public'"
```
**PASS / baseline 2026-09-15:** `alembic_head=69e942bab3aa` · `webhook_urls=0` ·
`recipe_actions=0` · `notifiers=0` · `recipes=173` · `recipes_with_image=173` · `users=2` ·
`users_oidc=1` · `notes=2` · `tables=66`.
**Why `recipes_with_image` excludes `'no image'`** (review 2026-09-15): that string is
Mealie's `NO_IMAGE` sentinel, and migration `4b91d3a7c0e2` treats a row carrying it as
having NO image key — it is RESTORED if `original.webp` exists and CLEARED if not. A
sentinel row counted as "with image" would mispredict the §4.3 backfill line and fail a
correct upgrade. (The 173 baseline was measured with `is not null`; re-measure with the
corrected query on the day — if the number differs, that difference is the sentinel rows.)
**If `webhook_urls` or `recipe_actions` is no longer 0: STOP.** Someone configured an
outbound target since this plan was written; read the row, resolve its host from the pod,
and if it is private the plan needs an `HTTP_ALLOW_LIST` entry for *that host only* —
re-derive, do not guess. **If `alembic_head` ≠ `69e942bab3aa`: STOP** — the DB is not
where §1.4 says it is.

**2.3 — Backups fresh (Longhorn, both volumes).**

```bash
kubectl get volumes -n storage -o custom-columns=NAME:.metadata.name,STATE:.status.state,ROBUST:.status.robustness,LAST_BACKUP:.status.lastBackupAt --no-headers | grep mealie
```
**PASS:** both `mealie-data` and `mealie-pg-data` `attached healthy` with `LAST_BACKUP`
inside 24 h (the CronJob runs `0 3 * * *`; `lastBackupAt` can lag one cycle —
`docs/sops/backup.md`). *(2026-09-15: both backed up 2026-09-14T03:0xZ.)*

**2.4 — The image files the backfill migration will read.**

```bash
kubectl -n office exec deploy/mealie -c main -- sh -c \
  'echo recipe_dirs=$(ls -1 /app/data/recipes | wc -l); echo original_webp=$(find /app/data/recipes -maxdepth 3 -name original.webp | wc -l); df -h /app/data | tail -1'
```
**PASS:** `original_webp` **equals** `recipes_with_image` from §2.2 (173 = 173 at
plan-write time) and `/app/data` is on `/dev/longhorn/mealie-data`. If they differ, the
migration WILL clear (or restore) the difference — that is upstream's intended repair, but
write the numbers down so §4.3's prediction is `restored = webp − with_image` /
`cleared = with_image − webp`, not 0/0 — where `with_image` is the §2.2 count that already
excludes the `'no image'` sentinel (a sentinel row with a file on disk lands in `restored`,
one without lands in `cleared`).

**2.5 — The OIDC discovery path works BEFORE the change** (so a §4.4 failure is
attributable). From inside the pod, through the same DNS the app uses:

```bash
kubectl -n office exec deploy/mealie -c main -- python3 -c "
import os,json,socket,urllib.request,urllib.parse
u=os.environ['OIDC_CONFIGURATION_URL']; h=urllib.parse.urlparse(u).hostname
print('resolves:',sorted({a[4][0] for a in socket.getaddrinfo(h,443)}))
d=json.load(urllib.request.urlopen(u,timeout=10)); print('issuer ok:', 'issuer' in d, '| token_endpoint ok:', 'token_endpoint' in d)"
```
**PASS:** `resolves: ['192.168.55.104']`, `issuer ok: True | token_endpoint ok: True`.

**2.6 — Alert baseline.**

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9099:9090 >/dev/null 2>&1 &
sleep 4
curl -s localhost:9099/api/v1/alerts | python3 -c "
import sys,json
a=[x['labels'].get('alertname') for x in json.load(sys.stdin)['data']['alerts'] if x['state']=='firing' and x['labels'].get('alertname') not in ('Watchdog','InfoInhibitor')]
print('firing:',len(a),a)"
kill %1 2>/dev/null
```
**PASS:** no `Mealie*` alert firing. Write the list down for §4.6.

## 3) Steps

**3.1 — Active-update marker** (`docs/sops/application-update.md` Step 1). No Alertmanager
silence: `MealieNotReady` / `MealieCrashLooping` are `for: 5m` and the Recreate + Alembic
run is expected in well under that. `MealiePodRestarted` is `for: 1m` on
`increase(kube_pod_container_status_restarts_total[15m]) > 0`
(`kubernetes/apps/monitoring/kube-prometheus-stack/app/mealie-alerts.yaml`) — a clean
Recreate is a FRESH pod (restart count 0), so it stays silent on the happy path, but it WILL
fire within ~1 min during a §5 crash-loop rollback; the marker makes that (and any stray
alert) read as EXPECTED by the triage agent.

```bash
runbooks/update-marker.sh add mealie office 2 "image v3.25.1->v3.26.0"
```

**3.2 — BACKUP GATE (mandatory; `rollback_class: backup-restore`).** Taken from the live
pg pod, before anything is pushed.

```bash
DUMP_DIR="$HOME/backups/mealie"; mkdir -p "$DUMP_DIR"
TS=$(date +%Y%m%d_%H%M%S)
DUMP="$DUMP_DIR/mealie-pre-v3.26.0-$TS.dump"
kubectl -n office exec deploy/mealie-pg -- pg_dump -U mealie -d mealie -Fc > "$DUMP"
ls -l "$DUMP"
pg_restore -l "$DUMP" | grep -c 'TABLE DATA'
# baseline counts alongside the dump (re-run the §2.2 command, redirected):
kubectl -n office exec deploy/mealie-pg -- psql -U mealie -d mealie -At \
  -c "select 'alembic_head='||version_num from alembic_version" \
  -c "select 'recipes='||count(*) from recipes" \
  -c "select 'recipes_with_image='||count(*) from recipes where image is not null and image <> 'no image'" \
  -c "select 'users='||count(*) from users" \
  -c "select 'notes='||count(*) from notes" \
  -c "select 'tables='||count(*) from information_schema.tables where table_schema='public'" \
  > "$DUMP.counts.txt"; cat "$DUMP.counts.txt"
```
**PASS:** file size clearly non-trivial (hundreds of KB for 173 recipes), `TABLE DATA`
count ≥ 60 (66 public tables at plan-write time), `.counts.txt` matches §2.2.
*(`pg_restore` is available locally via the postgres client tools; if not,
`kubectl -n office exec -i deploy/mealie-pg -- pg_restore -l < "$DUMP"` gives the same
listing.)*

**3.3 — The edit: one tag, plus the comment that stops the next reader adding
`HTTP_ALLOW_LIST`.** File: `kubernetes/apps/office/mealie/app/helmrelease.yaml`.

```bash
sed -i '' 's/^\(              tag: \)v3\.25\.1$/\1v3.26.0/' kubernetes/apps/office/mealie/app/helmrelease.yaml
git --no-pager diff --stat   # exactly 1 file, 1 line changed so far
```

Then, directly above the `env:` line of the `main` container (line ~67), insert this
comment block by hand (it is documentation for the outbound-request guard; keep it):

```yaml
            # v3.26.0+ refuses server-initiated HTTP to private addresses (recipe
            # import/image download, webhooks, recipe actions) unless the target is
            # on HTTP_ALLOW_LIST. Deliberately NOT set here: the OIDC login path
            # (authlib, routes/auth/auth.py) is NOT routed through that guard, so
            # auth.${SECRET_DOMAIN} resolving to the envoy-external LAN IP is fine;
            # the only guarded OIDC call (avatar fetch) self-allow-lists the
            # provider host; and we run 0 webhooks / 0 recipe actions. Adding the
            # auth host or the VLAN here would only re-open the SSRF surface for
            # user-supplied URLs. See runbooks/maintenance/plans/mealie-v3.26.0 §1.2.
```

**Expected `git diff`:** the tag line `v3.25.1` → `v3.26.0` and the comment block. Nothing
else. **Do not** add `HTTP_ALLOW_LIST`. **Do not** touch `upgrade.remediation` — the
migration is additive and the startup probe already allows 10 min (`failureThreshold: 60`),
so Flux's rollback will not race it (that guard exists for the from-scratch install case).

**3.4 — Commit ONLY that file, verify, push** (shared worktree — CLAUDE.md).

```bash
cat > /tmp/mealie-msg.txt <<'EOF'
chore(mealie): image v3.25.1 -> v3.26.0 (held: upstream outbound-request guard)

Minor bump. v3.26.0 ships mealie-recipes/mealie#7914, which refuses
server-initiated HTTP to private addresses unless HTTP_ALLOW_LIST is set.
Verified against the v3.26.0 source that the OIDC login path (authlib) is
NOT behind that guard and that this deployment has 0 webhooks / 0 recipe
actions, so no allow list is set — a comment in the HelmRelease records why.

Four additive Alembic revisions run at startup (head 69e942bab3aa ->
3527efeeec34); pre-upgrade pg_dump taken per the plan's backup gate.

Plan: runbooks/maintenance/plans/mealie-v3.26.0.md
Finding: F-ec4c1644 (resolved cd163006; this commit is the held item it surfaced)

<ATTRIBUTION LINES OF THE EXECUTING SESSION — replace this line; do NOT copy the
planner's Co-Authored-By / Claude-Session lines into the executing commit>
EOF
git commit --only kubernetes/apps/office/mealie/app/helmrelease.yaml -F /tmp/mealie-msg.txt
git show --stat HEAD          # MUST list exactly helmrelease.yaml
git push origin main
```

**3.5 — Watch the rollout.** The GitHub webhook triggers Flux; no manual reconcile by
default. If nothing has moved after 3 minutes, `mise exec -- flux reconcile ks mealie
-n office --with-source` is acceptable (SOP §11 shape), once.

```bash
kubectl -n office rollout status deploy/mealie --timeout=15m
kubectl -n office logs deploy/mealie -c main --tail=300 | grep -E 'Migration|alembic|backfill|safehttp|\[OIDC\]|Error|Traceback' || true
```
**Expected:** `Migration needed. Performing migration...`, the four `Running upgrade`
lines ending in `4b91d3a7c0e2 -> 3527efeeec34`, the backfill line from §1.4, then uvicorn
serving. Under `Recreate` there is a 1-2 minute hole; do **not** hand-delete pods
mid-Recreate (SOP §4 Step 4).

## 4) Verification

### 4.1 Floor — Flux / pod / version

```bash
kubectl -n office get helmrelease mealie -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'
kubectl -n office get pods -l app.kubernetes.io/name=mealie -o custom-columns=NAME:.metadata.name,READY:.status.containerStatuses[0].ready,RESTARTS:.status.containerStatuses[0].restartCount,IMAGE:.status.containerStatuses[0].image
kubectl -n office exec deploy/mealie -c main -- python3 -c "
import json,urllib.request; d=json.load(urllib.request.urlopen('http://127.0.0.1:9000/api/app/about')); print('version:',d.get('version'))"
```
**PASS:** `True` · `ready=true restarts=0 image=…mealie:v3.26.0` · `version: v3.26.0`.

### 4.2 CONTENTS ASSERTION 1 — the schema landed exactly, and nothing was lost

> **CONTENTS ASSERTION:** the DB is at v3.26.0's Alembic head with precisely the three new
> tables and two new columns, and every pre-existing row count is unchanged — measured by
> the psql block below, compared to the §2.2 / `$DUMP.counts.txt` baseline.

```bash
kubectl -n office exec deploy/mealie-pg -- psql -U mealie -d mealie -At \
  -c "select 'alembic_head='||version_num from alembic_version" \
  -c "select 'tables='||count(*) from information_schema.tables where table_schema='public'" \
  -c "select 'new_tables='||count(*) from information_schema.tables where table_schema='public' and table_name in ('ingredient_foods_substitutions','recipes_ingredients_substitutions','recipe_note_ref_link')" \
  -c "select 'new_cols='||count(*) from information_schema.columns where (table_name='users' and column_name='external_avatar_hash') or (table_name='notes' and column_name='reference_id')" \
  -c "select 'recipes='||count(*) from recipes" \
  -c "select 'users='||count(*) from users" \
  -c "select 'users_oidc='||count(*) from users where auth_method='OIDC'" \
  -c "select 'notes='||count(*) from notes"
```
**PASS — exactly:** `alembic_head=3527efeeec34` · `tables=69` (baseline + 3) ·
`new_tables=3` · `new_cols=2` · `recipes`, `users`, `users_oidc`, `notes` **identical**
to baseline (173 / 2 / 1 / 2 at plan-write time). `tables=66` with `alembic_head` moved
means a migration half-applied — treat as FAIL and go to §5.

### 4.3 CONTENTS ASSERTION 2 — the image backfill touched what it should, and nothing else

> **CONTENTS ASSERTION:** `recipes.image` still references an image for every recipe that
> has one on disk — measured by the migration's own summary line in the pod log AND by the
> post-upgrade `recipes_with_image` count, compared to §2.2 / §2.4.

```bash
kubectl -n office logs deploy/mealie -c main | grep -E 'Recipe image backfill|Skipping the clearing half'
kubectl -n office exec deploy/mealie-pg -- psql -U mealie -d mealie -At \
  -c "select 'recipes_with_image='||count(*) from recipes where image is not null and image <> 'no image'"
```
**PASS:** the log line reads `Recipe image backfill checked <recipes> recipes:
<webp − with_image> image references restored, <with_image − webp> cleared` — with the
2026-09-15 numbers, **`checked 173 recipes: 0 image references restored, 0 cleared`** —
and `recipes_with_image` equals the §2.4 `original_webp` count (173).
**FAIL:** any `Skipping the clearing half` line (the migration could not see the volume —
the pod ran with `/app/data` unmounted or empty; §5 immediately, then find out why the
PVC premise passed), or `cleared` > the §2.4 prediction.

### 4.4 CONTENTS ASSERTION 3 — the login path the hold was about

> **CONTENTS ASSERTION:** an OIDC login through Authentik completes end to end on v3.26.0
> with the discovery host still resolving to a private address and NO allow list set —
> measured by a real browser login (attended plan) plus the callback line in the access
> log, compared to §2.5 and to the absence of any `[safehttp] blocked` line.

1. Operator: open `https://mealie.${SECRET_DOMAIN}`, click *Login with Authentik*, complete
   the Authentik flow with a `mealie-users` member. **PASS:** lands on the Mealie home
   page signed in. (The in-app "outbound request protection" announcement appearing is
   expected — it is the release's own notice, not an error.)
2. Mechanically, within a few minutes of that login:

```bash
kubectl -n office logs deploy/mealie -c main --since=15m | grep -E 'oauth/callback' | tail -3
kubectl -n office logs deploy/mealie -c main --since=15m | grep -cE '\[safehttp\] blocked|\[OIDC\].*(error|refusing|failed|not present)' || true
# and the §2.5 discovery probe again, unchanged
```
**PASS:** the `/api/auth/oauth/callback?code=…` request is logged with a **3xx** (the
authlib redirect into the app), not 401/500; the blocked/error grep prints **0**; the
§2.5 probe still shows `192.168.55.104` + `issuer ok: True`. If uvicorn's access log
does not emit 3xx lines at the configured log level (the callback grep comes back empty
rather than showing a 401/500), fall back to the PRIMARY pass signal: step 1's browser
login landed signed-in on the home page AND the blocked/error grep prints 0 — that pair
is sufficient; an empty access-log grep alone is not a failure.
**If the callback returns 401/500 or a `[safehttp] blocked … auth.…` line appears:** §1.2
was wrong for this build — go to §5, and only then consider `HTTP_ALLOW_LIST` with
exactly the auth hostname (hostnames match exactly; never a CIDR) as a re-planned change.

### 4.5 (optional, mutation-free) — prove the guard is actually live, not just harmless

In the UI: *Recipes → Import → URL* with `http://mealie-pg:5432/`. **Expected:** the import
fails immediately and the log shows
`[safehttp] blocked request to http://mealie-pg:5432/: resolves to non-public address 10.96.x.x`.
No recipe is created (the scrape fails before creation). This demonstrates the new code
path is in force for user-supplied URLs — the thing this release is for.

### 4.6 Settle

```bash
kubectl -n office get jobs --sort-by=.status.startTime | tail -3      # next mealie-shopping-sync Complete
# alerts: repeat §2.6 after >=10 min — no Mealie* firing
runbooks/update-marker.sh clear mealie
```
**PASS:** the first `mealie-shopping-sync-*` Job started after the rollout is `Complete`
(1/1); alert list matches the §2.6 baseline. Then clear the marker.

## 5) Rollback

**Read §1.4 first: `git revert` alone crash-loops v3.25.1.** `init_db.main()` sees the DB
head `3527efeeec34`, which v3.25.1's scripts do not contain, and calls
`alembic upgrade head` unguarded → `Can't locate revision identified by '3527efeeec34'` →
exit → CrashLoopBackOff → Flux remediation cannot help (`maxHistory: 1`, and the DB is the
problem, not the chart). The rollback is therefore **revert + one DB step**.

**5.1 — Revert the manifest.**

```bash
git revert --no-edit HEAD        # or: git checkout <pre-bump-sha> -- kubernetes/apps/office/mealie/app/helmrelease.yaml
git show --stat HEAD             # exactly helmrelease.yaml
git push origin main
```

**5.2 — The DB step. Pick ONE.**

*Option A — stamp reset (fast, keeps everything written since the upgrade).* The four
revisions are additive; v3.25.1's ORM never selects the new tables/columns, and the only
data change (`recipes.image` reconcile) has no downgrade by upstream's own design. Point the
stamp back and leave the extra schema in place — it is inert to v3.25.1 and is
re-adopted cleanly on the next attempt at v3.26.0 (Alembic would then see head
`69e942bab3aa` and re-run the four scripts; `create_table` on existing tables would
fail, so **before re-attempting v3.26.0 after an Option-A rollback, restore the stamp to
`3527efeeec34` or drop the three tables + two columns** — note it in the re-plan).

```bash
kubectl -n office exec deploy/mealie-pg -- psql -U mealie -d mealie -At \
  -c "update alembic_version set version_num='69e942bab3aa'" \
  -c "select 'alembic_head='||version_num from alembic_version"
```

*Option B — exact restore from the §3.2 gate dump (loses anything created after the dump;
use when §4.2/§4.3 showed data damage rather than a plain startup failure).*

```bash
kubectl -n office exec -i deploy/mealie-pg -- pg_restore -U mealie -d mealie --clean --if-exists --no-owner < "$DUMP"
kubectl -n office exec deploy/mealie-pg -- psql -U mealie -d mealie -At \
  -c "select 'alembic_head='||version_num from alembic_version" \
  -c "select 'recipes='||count(*) from recipes" -c "select 'tables='||count(*) from information_schema.tables where table_schema='public'"
```
**Expected:** `alembic_head=69e942bab3aa`, `recipes` and `tables` equal to
`$DUMP.counts.txt`. (`--clean --if-exists` only drops objects that are IN the dump; the
three new tables and two new columns are not in it — they did not exist at dump time —
so they SURVIVE the restore. After Option B therefore also run
`drop table if exists recipe_note_ref_link, recipes_ingredients_substitutions,
ingredient_foods_substitutions; alter table users drop column if exists
external_avatar_hash; alter table notes drop column if exists reference_id;` to leave the
schema byte-for-byte pre-upgrade. Harmless if already gone.)

**5.3 — Let the v3.25.1 pod come up.** After the DB step, either wait for the next
CrashLoopBackOff retry or delete the crash-looping pod once — safe under `Recreate`
(single replica, RWO; the replacement lands on the same attachment).

```bash
kubectl -n office get pods -l app.kubernetes.io/name=mealie
kubectl -n office rollout status deploy/mealie --timeout=10m
```

**5.4 — Confirm the cluster is back, by the cluster and not by `git log`:**
`kubectl get deploy -n office mealie -o jsonpath='{.spec.template.spec.containers[0].image}'`
→ `…:v3.25.1`; `/api/app/about` → `v3.25.1`; `alembic_head=69e942bab3aa`;
`recipes=173`; and the §4.4 real login succeeds. Clear the marker.

## 6) Interference notes

- **Shared infra: none.** Only namespace `office`; `mealie-pg` is not restarted; the
  HTTPRoute, Gateway, cert, DNS are untouched. No storage-class, PVC or Longhorn change
  (nothing here deletes a PVC; `docs/sops/storage-safety.md` is not engaged).
- **`conflicts_with` the two Authentik-DB plans** because §4.4 is a live login through
  Authentik. A window that is also migrating or decommissioning the auth DB cannot tell a
  Mealie regression from an Authentik one. Run this after Step 0 safe-updates have settled,
  and not interleaved with an Authentik plan.
- **Expected noise, not regressions:** one `mealie-shopping-sync` Job (`*/5`) may fail
  during the 1-2 minute Recreate hole — the next one passes (§4.6). The memory note
  *"mealie sync 500s are HA, not Mealie"* concerns the HA side and is unrelated to this
  change. `MealieNotReady` / `MealieCrashLooping` are `for: 5m` and should not fire;
  `MealiePodRestarted` (`for: 1m`, restart-count increase) fires only if §5 is exercised
  — the §3.1 marker covers either.
- **The `HTTP_ALLOW_LIST` temptation.** If anything at all looks wrong after the bump, the
  release notes will suggest setting it. Do not — unless §4.4 has *proved* the login path
  is blocked, which §1.2 shows it cannot be in this build. The correct reaction to any
  other failure is §5.
- **Rollback is not free (see §5).** The window agent must budget the DB step. This is the
  single biggest gotcha of the plan: an operator who reverts the tag and walks away gets a
  crash loop, not v3.25.1.
- **Re-attempt after a rollback** needs the §5.2 Option-A caveat handled (stamp forward or
  drop the additive schema) — put it in the re-plan, do not improvise in-window.
- **F-ec4c1644 is RESOLVED (cd163006, 2026-09-15) — this plan covers only the bump.** The
  finding's Action — a direct-bump breaking-change gate before the AUTO exit in
  `runbooks/coverage.py`, `DirectBumpBreakingGateTest` in
  `runbooks/tests/test-coverage-lane-safety.py`, and the `docs/sops/auto-update.md`
  correction — has already landed. The finding stays in `finding_refs` only as the
  ownership link for the *mealie* item it surfaced; there is no pending code work behind
  it and nothing to close on execution. (Consequence for the lane: coverage.py now routes
  this item to PLAN both via "plan exists" and via the new gate, so the nightly Step 0 will
  not apply v3.26.0 unattended — no deny rule is needed.)

### Duration against the slot

| Phase | Min |
|---|---:|
| §2 pre-checks incl. premises | 6 |
| §3.1-3.2 marker + dump + counts | 3 |
| §3.3-3.4 edit, commit, push | 3 |
| §3.5 webhook → Flux → Recreate → Alembic → Ready | 5 |
| §4 verification incl. the real login and a settle | 8 |
| **Total** | **25** |

Rollback, if needed, adds ~10 min (revert, stamp reset, pod restart, re-verify).
