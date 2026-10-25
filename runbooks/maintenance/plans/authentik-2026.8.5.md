---
plan_id: authentik-2026.8.5
component: authentik
pr: 364                               # chart PR "update authentik ( 2026.8.3 → 2026.8.5 )" (retargeted 2026-10-23 from
                                      # 2026.8.4: upstream published 2026.8.5 on 2026-10-21, newest stable). Its lockstep
                                      # sibling is PR 359 (ghcr.io/goauthentik/server 2026.8.3 → 2026.8.5,
                                      # the two patch-session-settings init pins). Do NOT merge either PR on
                                      # its own: §3 lands the union of both diffs in ONE commit, and Renovate
                                      # closes both PRs once main already carries the change.
kind: chart
current: "chart 2026.8.3; server+worker ghcr.io/goauthentik/server:2026.8.3 (chart appVersion), both patch-session-settings initContainers pinned :2026.8.3; 13 managed proxy outposts on ghcr.io/goauthentik/proxy:2026.8.3"
target: "chart 2026.8.5 + both initContainer pins ghcr.io/goauthentik/server:2026.8.5 in ONE commit; 13 managed proxy outposts pushed to ghcr.io/goauthentik/proxy:2026.8.5"
update_type: patch
risk: medium                          # mechanically the easiest authentik bump yet: chart templates and
                                      # values byte-identical (only Chart.yaml/lock/README differ), ZERO
                                      # Django migrations, ZERO blueprint YAML changes, settings.py unchanged.
                                      # NOT low because of (a) full-cluster SSO blast radius + a manual
                                      # 13-outpost push, and (b) the client-IP behaviour change in §1, which
                                      # needs an operator decision (A/B/C) at the GO.
est_duration_min: 45
needs_reboot: false
touches:
  namespaces: [kube-system]
  resources:
    - helmrelease/authentik                     # chart.spec.version + 2 initContainer image pins
    - deployment/authentik-server               # 3 replicas, rolling restart
    - deployment/authentik-worker               # 3 replicas, rolling restart
    - "deployment/authentik-pg (postgres 18.6): NOT restarted, NO schema change (2026.8.5 ships no migrations; django_migrations count stays 777)"
    - deployment/ak-outpost-alertmanager-forward-auth
    - deployment/ak-outpost-arag-web-forward-auth
    - deployment/ak-outpost-esphome-forward-auth
    - deployment/ak-outpost-frigate-forward-auth
    - deployment/ak-outpost-gods-eye-view-forward-auth
    - deployment/ak-outpost-headlamp-forward-auth
    - deployment/ak-outpost-homepage-forward-auth
    - deployment/ak-outpost-longhorn-forward-auth
    - deployment/ak-outpost-nocodb-forward-auth
    - deployment/ak-outpost-phpmyadmin-forward-auth
    - deployment/ak-outpost-prometheus-forward-auth
    - deployment/ak-outpost-solarfocus-scraper-forward-auth
    - deployment/ak-outpost-uptime-kuma-forward-auth
    - "authentik client-IP derivation (upstream behaviour change in 2026.8.4+; impact assessment on F-7006f363)"
  shared:
    - identity-provider   # authentik = SSO (OIDC) + forward-auth for the whole estate
    - authentik           # every OIDC app and all 13 forward-auth-protected apps log in through it
    - gateway/envoy       # authentik-server is published on envoy-external (public edge); the 13
                          # outposts back the SecurityPolicy ext-auth of their apps; the §1
                          # client-IP change interacts with this gateway (assessment on F-7006f363)
    - monitoring          # §4 reads Prometheus series + alert state
depends_on:
  - authentik-web-max-requests            # SAME helmrelease.yaml. Lands first on a nightly; its 24 h soak (S1-S3) must
                                          # have PASSED before this plan's GO. Not a hard technical dependency, a
                                          # blast-radius/attribution ordering (two authentik rolls, one cause each).
conflicts_with:
  - authentik-web-max-requests            # also here: same file, never two pending commits in one window
  - etcd-timeouts-5000-500                # etcd must be quiet during the roll; do not stack
  - talos-linux-1.14.4                    # node roll evicts every authentik pod mid-verification (replaces retired 1.14.2)
  - envoy-proxy-config-distroless-v1.39.4 # restarts the envoy data plane that carries auth.<domain> and every
  - envoy-proxy-config-distroless-v1.40.0 # forward-auth ext-auth call; would also confound the §4 G7 client-IP probe
  - flux-reconciler-impersonation         # exclusive (blocked); changes how helm-controller applies this HR
  # No kube-prometheus-stack plan is open (92.x retired 2026-10-23); G4/G6 read Prometheus, so add one here if
  # a kube-prometheus-stack bump is ever planned for the same night.
exclusive: false
security_ref: F-7006f363              # security driver and impact assessment for this plan; detail lives on the record, not here.
capability_change: true               # USER/SECURITY-VISIBLE: 2026.8.4+ changes how authentik derives the client IP
                                      # (upstream behaviour change, §1; local assessment on F-7006f363). Also
                                      # outpost->upstream HTTP/2 negotiation is dropped (HTTP/1.1 only).
rollback_class: git-revert            # no migrations, no blueprint changes: a revert is a clean image roll
finding_refs: [F-7006f363, F-2fb59c74, F-67fa2a51, F-dcbe773f, F-4bc24032, F-eb4061e5]
                                      # F-7006f363 = client-IP change + operator decision (this plan's driver);
                                      # F-2fb59c74 = the version finding (retargets to 8.5 on the next sweep);
                                      # the others are image findings whose remedy is this bump. Detail on the records;
                                      # do not assume 8.5 clears every item (closure is measured by the next scan).
review: null
status: draft
window: null
premises:
  - id: server-on-2026.8.3
    why: "`current:` claims the server Deployment runs :2026.8.3."
    run: kubectl get deploy -n kube-system authentik-server -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: ghcr.io/goauthentik/server:2026.8.3
  - id: worker-on-2026.8.3
    why: "`current:` claims the worker Deployment runs :2026.8.3."
    run: kubectl get deploy -n kube-system authentik-worker -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: ghcr.io/goauthentik/server:2026.8.3
  - id: hr-chart-2026.8.3
    why: "The HelmRelease has not already been moved (e.g. PR 364 merged alone by another session)."
    run: kubectl get helmrelease -n kube-system authentik -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: "2026.8.3"
  - id: thirteen-outposts-on-2026.8.3
    why: "§3 step 6 pushes exactly 13 outpost Deployments. Measured 2026-10-15: 13 on proxy:2026.8.3, 14 Outpost rows (13 managed + embedded), all kubernetes_disabled_components ['ingress']."
    run: kubectl get deploy -n kube-system -o jsonpath='{range .items[*]}{.spec.template.spec.containers[0].image}{"\n"}{end}' | grep -c 'goauthentik/proxy:2026.8.3'
    expect_exact: "13"
  - id: chart-2026.8.5-published
    why: "Target chart exists and carries the 2026.8.5 server image (newest stable upstream release, 2026-10-21)."
    run: helm show chart authentik --repo https://charts.goauthentik.io --version 2026.8.5
    expect_matches: 'goauthentik/server:2026\.8\.5'
  - id: no-ingress-objects
    why: "Zero Ingress objects cluster-wide; an outpost-published Ingress is the known post-upgrade hijack (CLAUDE.md, SOP authentik.md)."
    run: kubectl get ingress -A -o name | wc -l | tr -d ' '
    expect_exact: "0"
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/authentik.md
  - docs/sops/backup.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-10-15"
retargeted: "2026-10-23"              # 2026.8.4 -> 2026.8.5 per independent review; premises re-run, see section 1
---

# authentik 2026.8.3 -> 2026.8.5 (chart + both init pins in lockstep, then the 13 outposts)

## 1. Summary & why held

Same-line patch (spanning two upstream releases, 2026.8.4 and 2026.8.5) with the
same shape as the executed `authentik-2026.8.3` (`e9442f55`, retired in
`d4ccfa09`). Three pins move in ONE commit: `spec.chart.spec.version` (line 13) and
the two `patch-session-settings` initContainer images (lines 139 and 306 of
`kubernetes/apps/kube-system/authentik/app/helmrelease.yaml`). Renovate split them
across two PRs, **#364** (chart) and **#359** (server image = the two init pins).
Merging either one alone recreates the init/server skew that
`docs/sops/authentik.md` §"Upgrading Authentik" warns about.

**Retargeted 2026-10-23 from 2026.8.4 to 2026.8.5.** Newest stable upstream is
`version/2026.8.5` (GitHub, published 2026-10-21T12:57Z, not a prerelease; the
parallel `2026.5.8` is the older line). Re-run today: ghcr `server:2026.8.5` and
`proxy:2026.8.5` return HTTP 200; chart 2026.8.5 is in the index
(`artifacthub.io/images` names `server:2026.8.5`); PR #364 and #359 are both
OPEN and now carry the 2026.8.5 title; the live cluster is still entirely on
2026.8.3 (HelmRelease 2026.8.3, 13 outposts on `proxy:2026.8.3`, 27 `ak-outpost`
Services).

**Why held.** The operator deny rule `*authentik*` in
`runbooks/auto-update-policy.yaml` (2026-09-22). It allows an authentik upgrade
only when the chart and BOTH init pins move in one reviewed commit, in an
attended window, after the target tag is confirmed published. All three
conditions are met by §3, plus the operator decision below.

**Upstream evidence (2026.8.3 -> 2026.8.5, GitHub compare, re-measured
2026-10-23).**

- **2026.8.5 itself** (`version/2026.8.4...version/2026.8.5`, 12 commits, release
  notes list five fixes): `endpoints: fix MultipleObjectsReturned`,
  `enterprise/providers/microsoft_entra: skip members already in the group`,
  `root: bump cert-related deps`, two web fixes. Docs and CI otherwise. No
  breaking-change section. In the 8.4 -> 8.5 file list: **no migrations, no
  blueprint YAML (only `blueprints/schema.json`), `authentik/root/settings.py` and
  `client_ip.rs` unchanged.** Same for the whole 8.3 -> 8.5 range (no path under
  `*/migrations/`, none of `authentik/root/settings.py`).
- **Chart diff** (`helm pull` 2026.8.3 vs 2026.8.5, `diff -rq`): `Chart.yaml`
  (appVersion + image annotations), `Chart.lock`, README, and ONE `values.yaml`
  line: the BUNDLED postgresql tag `17.11-bookworm -> 17.11-trixie`. The bundled
  database is `enabled: false` in our HelmRelease (retired 2026-09-24; the live DB
  is `deployment/authentik-pg`), so it renders nothing. Templates are
  byte-identical.
- **From 2026.8.4** (carried forward, in this range): outpost proxy no longer
  negotiates HTTP/2 to upstreams (#26281), HTTP/1.1 for OAuth backchannel
  requests (#26422), embedded JWKS over the unix socket (#26448),
  `providers/proxy: fix startup reconcile not being atomic` (#26344),
  `flows: allow unauthenticated flows for re-authentication` (#26785),
  `django-channels-postgres: refresh pool credentials` (#26505), plus SCIM, SAML,
  LDAP/Kerberos and web fixes we do not exercise.

### THE GOTCHA: client-IP derivation changes (OPERATOR DECISION at the GO)

Client-IP derivation changed upstream (PR 26353); see F-7006f363. Re-verified 2026-10-23: identical on `version/2026.8.5` and upstream `main`, so moving to 2026.8.5 does not avoid it.

What it means for this estate (consumers of the derived IP, how the gateway
interacts with it, baseline readings, the probe command and its expected values) is
an impact assessment and lives **only** on finding **F-7006f363** in the operations
database (`runbooks/policy-cli.py finding show F-7006f363`), per
`docs/sops/vulnerability-disclosure.md`. The window agent reads it before the GO.

#### Decision card (the window agent presents this at the GO)

Not a patch-bump "go?". Pick one; record the answer with `home-operation decide`
before the window; the G7 expected reading is read from that record. Impact of each
option: see F-7006f363.

| | A. Upgrade, accept | B. Hold at 2026.8.3 | C. A plus a blueprint change |
|---|---|---|---|
| Action | chart + 2 init pins + 13 outposts to 2026.8.5 | nothing; plan stays `draft`; PR #364/#359 stay held | a second reviewed blueprint commit (see F-7006f363) |
| Follow-up | accepted risk (AR) for the behaviour: needle = the behaviour, not a version, `--expires` <= 180 d | needs an Envoy-side plan (not written); every future release has the same behaviour | AR plus the blueprint commit |
| Reversibility | `git revert` of one commit (no migrations) | n/a | revert both commits |

Planner recommendation (not a decision): A or C over B, because B only defers an
unavoidable upstream behaviour while forgoing the fixes. §3 is written for A or C.
Under B this plan stays `draft` and gains `depends_on` on the Envoy-side plan.

**Managed outposts do NOT follow the server.** SOP §2: all 13
`ak-outpost-*-forward-auth` Deployments stay on `proxy:2026.8.3` until pushed.
The sanctioned path is `kubectl set image` one outpost at a time. These
Deployments exist in no git repo, so this is the documented non-GitOps
exception. The 14th outpost (`authentik Embedded Outpost`) runs inside
authentik-server and follows the server image.

**Do NOT** use a bulk `Outpost.objects.all(): o.save()` or the
`KubernetesController(...).up()` loop. `o.save()` fires the controller's
post_save path, and SOP §2 records that path deleting
`svc/ak-outpost-homepage-forward-auth` on 2026.8.2: "treat any outpost save
... as capable of deleting that outpost's Service". (The memory note recommending
bulk `o.save()` predates that and is stale; see the report.)

## 2. Pre-checks

Run from the repo root on the Mac mini (zsh). Every jsonpath is single-quoted.

0. **Operator decision recorded** (A, B or C, from §1). Without one, STOP. This
   plan must not run on a default.
1. **Premises:** `.venv/bin/python3 runbooks/plan-premises.py authentik-2026.8.5`.
   All six must pass; PR state is checked by the `gh` commands in pre-check 2 (the premise runner refuses `gh`). If the outpost count is not 13, an outpost was added or
   reaped: re-derive the step 6 list from the live Outpost list first.
2. **PRs still unmerged and main untouched:**
   ```bash
   gh pr view 364 --json state -q .state; gh pr view 359 --json state -q .state   # OPEN, OPEN
   git log -3 --format='%h %s' -- kubernetes/apps/kube-system/authentik/app/helmrelease.yaml
   grep -c '2026\.8\.3' kubernetes/apps/kube-system/authentik/app/helmrelease.yaml  # 3 (still 3 after web-max-requests: it adds env lines only)
   ```
   If either PR is MERGED, re-read the file. The intended end state may already
   be half-reached: chart moved but init pins not, or the reverse. In that case
   step 2 lands only the missing pins.
3. **Healthy baseline:**
   ```bash
   kubectl get pods -n kube-system -l app.kubernetes.io/instance=authentik \
     -o custom-columns='NAME:.metadata.name,IMAGE:.spec.containers[0].image,READY:.status.containerStatuses[0].ready,RESTARTS:.status.containerStatuses[0].restartCount'
   flux get hr -n kube-system authentik                          # READY True, 2026.8.3
   kubectl get svc -n kube-system -o name | grep -c ak-outpost   # baseline 27 (measured 2026-10-15)
   ```
4. **Backup gate.** The `authentik-pg-data` Longhorn backup must be newer than
   26 h. No migration is expected, so this is the floor, not the plan:
   ```bash
   python3 runbooks/longhorn-backup-age.py authentik-pg-data --max-hours 26
   ```
   Exit 1 means STOP and wait for the `storage/daily-backup-all-volumes` run.
   Measured 2026-10-15: newest `2026-10-14T23:05:36Z`, 8 Completed.
5. **Baselines for §4.** Save the output:
   ```bash
   W=$(kubectl get pods -n kube-system -l app.kubernetes.io/component=worker -o jsonpath='{.items[0].metadata.name}')
   kubectl exec -n kube-system "$W" -c worker -- ak shell -c "
   from authentik.blueprints.models import BlueprintInstance as B
   from collections import Counter
   qs=B.objects.all()
   print('BP', dict(Counter(b.path.split('/')[0] if '/' in b.path else '<BARE>' for b in qs)), 'notok', [(b.path,b.status) for b in qs if b.status!='successful'])
   from authentik.providers.oauth2.models import OAuth2Provider as P
   print('GT empty', [p.name for p in P.objects.all() if not p.grant_types], 'of', P.objects.count())
   from django.db.migrations.recorder import MigrationRecorder as R
   print('MIGCOUNT', R.Migration.objects.count())
   from authentik.stages.authenticator_static.models import AuthenticatorStaticStage as S
   print('TOKCNT', [(s.name, s.token_count) for s in S.objects.all()])
   " 2>/dev/null | grep -E '^(BP|GT|MIGCOUNT|TOKCNT)' | tee /private/tmp/authentik-2026.8.5-baseline.txt
   ```
   Measured 2026-10-15:
   - `BP {'system': 11, 'cberg': 23, 'default': 19, 'migrations': 1} notok []`
   - `GT empty [] of 19`
   - `MIGCOUNT 777`
   - `TOKCNT [('default-authenticator-static-setup', 10)]`

   A non-empty `notok` means STOP and fix it first (SOP "stuck in `error`").
6. **Outpost baseline on 8.3 (Q1/Q3).** Port-forward Prometheus (as in G6) and record
   `count(count by (outpost_name)(authentik_outpost_connection{version="2026.8.3"} == 1))`
   (Q1) and `count(authentik_outpost_connection == 0) or vector(0)` (Q3). Require
   **Q1 = 14 and Q3 = 0**. After a CNI/node roll outposts reconnect only after a fixed
   300 s wait (measured 2026-10-25: Q1 read 10 and Q3 non-zero right after the Cilium roll,
   then 14/0 on re-measure). If not 14/0, wait up to 10 minutes and re-run; if still not
   14/0, investigate (outpost pod logs) and STOP: do not start the roll on a degraded baseline.
6b. **Client-IP probe baseline** (the G7 probe from F-7006f363, run now). The
   expected baseline reading is on the record. If it already reads like the
   post-upgrade value, something else changed the edge: STOP and investigate.
7. **Pre-flight the new image's `settings.py`** (SOP §1):
   ```bash
   kubectl run ak-preflight --rm -i --restart=Never -n kube-system \
     --image=ghcr.io/goauthentik/server:2026.8.5 --command -- sh -c '
     test -f /authentik/root/settings.py && echo settings.py OK
     grep -c "SESSION_EXPIRE_AT_BROWSER_CLOSE = True" /authentik/root/settings.py'
   ```
   PASS: `settings.py OK` and `1`. A `0` means the init `sed` would no-op, so
   STOP.
8. **web-max-requests soaked.** `authentik-web-max-requests` is EXECUTED and its
   soak gates S1-S3 (flip count < 230 vs baseline 694, worker exits <= 3 per pod
   per 24 h, memory max < 1200 MiB) were read at roll + 25 h and PASSED. If it is
   not executed or any S gate failed, STOP: two authentik rolls with an
   unproven first one make a regression unattributable. Then check no
   `conflicts_with` plan is in flight. Log out of authentik in the test browser now, so that G5 cannot be satisfied
   by a cached session. On 2026.8.3 G5 ended "satisfied-with-caveat (existing
   session)", and the newest `login` event on 2026-10-15 was 2026-10-02.

## 3. Steps

1. **Silence + marker** (application-update.md Step 1):
   ```bash
   runbooks/update-marker.sh add authentik kube-system 2 "2026.8.3->2026.8.5 upgrade"
   ```
   Then create an Alertmanager silence on `namespace="kube-system"` +
   `alertname=~"Authentik.*"` for 60 min, per SOP Step 1. Record the silence
   id. The §4 gates read Prometheus `/api/v1/alerts` directly, so the silence
   does not blind them.
2. **Edit the three pins.** Dry-tested on a scratch copy with macOS BSD sed,
   2026-10-15:
   ```bash
   sed -i '' \
     -e 's|^      version: 2026\.8\.3$|      version: 2026.8.5|' \
     -e 's|image: ghcr\.io/goauthentik/server:2026\.8\.3$|image: ghcr.io/goauthentik/server:2026.8.5|' \
     kubernetes/apps/kube-system/authentik/app/helmrelease.yaml
   grep -c '2026\.8\.3' kubernetes/apps/kube-system/authentik/app/helmrelease.yaml   # must print 0
   grep -c '2026\.8\.5' kubernetes/apps/kube-system/authentik/app/helmrelease.yaml   # must print 3
   ```
   Re-dry-tested 2026-10-23 on a scratch copy of the current file (macOS BSD sed):
   `grep -c 2026.8.3` -> 0, `grep -c 2026.8.5` -> 3, and exactly 3 hunks, identical
   to the union of PR #364 and PR #359. The line numbers below are for the tree
   BEFORE `authentik-web-max-requests` lands; that plan adds 9 lines to the server
   env block, so expect the pin lines to shift (the sed is pattern-based and
   unaffected, but the commit must still show exactly 3 insertions / 3 deletions):
   ```
   13c13
   <       version: 2026.8.3
   >       version: 2026.8.5
   139c139
   <           image: ghcr.io/goauthentik/server:2026.8.3
   >           image: ghcr.io/goauthentik/server:2026.8.5
   306c306
   <           image: ghcr.io/goauthentik/server:2026.8.3
   >           image: ghcr.io/goauthentik/server:2026.8.5
   ```
3. **Commit only that file and push:**
   ```bash
   git commit --only kubernetes/apps/kube-system/authentik/app/helmrelease.yaml \
     -m "chore(authentik): chart + initContainer pins 2026.8.3 -> 2026.8.5 (plan authentik-2026.8.5, supersedes #364 #359)"
   git show --stat HEAD            # exactly 1 file, 3 insertions / 3 deletions
   git log -1 --format=%s          # must be the subject above; amend before push if not
   git push
   ```
   The Flux webhook reconciles. Run `flux reconcile` only if nothing moves
   within 5 min (SOP Example B pattern).
4. **Watch the roll:**
   ```bash
   kubectl rollout status -n kube-system deploy/authentik-server --timeout=10m
   kubectl rollout status -n kube-system deploy/authentik-worker --timeout=10m
   ```
   Any `CrashLoopBackOff`, or a Python traceback in
   `kubectl logs -n kube-system deploy/authentik-worker -c worker --tail=200`,
   means go to §5 now.
5. **Run the §4 server gates G1-G5 and G7 BEFORE touching any outpost.**
6. **Push the 13 outposts, homepage first** (SOP §2; never `o.save()`, never the
   `up()` loop, never `kubectl delete`). Each fenced block is ONE
   self-contained Bash call. `push` exits non-zero unless the Service endpoints
   are exactly 9000 and 9443. That is the same function that ran in bash and zsh
   on 2026-09-26.
   ```bash
   push() {
     kubectl set image -n kube-system "deploy/ak-outpost-$1-forward-auth" proxy=ghcr.io/goauthentik/proxy:2026.8.5 &&
     kubectl rollout status -n kube-system "deploy/ak-outpost-$1-forward-auth" --timeout=3m &&
     P=$(kubectl get endpoints -n kube-system "ak-outpost-$1-forward-auth" -o jsonpath='{.subsets[0].ports[*].port}' 2>/dev/null | tr ' ' '\n' | sort | tr '\n' ' ') &&
     echo "EP $1: [$P]" && [ "$P" = "9000 9443 " ]
   }
   push homepage || echo "STOP at homepage"     # canary
   ```
   Log in to Homepage through forward-auth in a real browser, after logging
   out. This canary exercises the new HTTP/1.1-only upstream and backchannel
   path. Only if it succeeds, push the remaining 12:
   ```bash
   push() {
     kubectl set image -n kube-system "deploy/ak-outpost-$1-forward-auth" proxy=ghcr.io/goauthentik/proxy:2026.8.5 &&
     kubectl rollout status -n kube-system "deploy/ak-outpost-$1-forward-auth" --timeout=3m &&
     P=$(kubectl get endpoints -n kube-system "ak-outpost-$1-forward-auth" -o jsonpath='{.subsets[0].ports[*].port}' 2>/dev/null | tr ' ' '\n' | sort | tr '\n' ' ') &&
     echo "EP $1: [$P]" && [ "$P" = "9000 9443 " ]
   }
   for a in alertmanager arag-web esphome frigate gods-eye-view headlamp longhorn nocodb phpmyadmin prometheus solarfocus-scraper uptime-kuma; do
     echo "== $a"; push "$a" || { echo "STOP at $a"; break; }
   done
   ```
   That is 12 literal words plus the homepage canary, 13 in total. On any
   `STOP`, see §5 "Outposts".
7. **MFA blueprint re-apply** (SOP "Email, recovery and MFA"). This is
   conditional. Re-read `TOKCNT` as in pre-check 5. Only if it now reads `6`,
   re-apply `cberg/mfa-recovery-blueprint.yaml` once with the SOP "Fix" recipe,
   filtered to that path. With no blueprint YAML changed upstream it should
   still read `10`, and then there is nothing to do.
8. **Close out** (application-update.md Step 5): delete the silence, then run
   `runbooks/update-marker.sh clear authentik`. Confirm PRs #364 and #359
   show CLOSED after Renovate's next run. If either is still open, close it
   with a comment naming the step 3 sha. Do not merge it.
9. **Record the §1 decision** where the operator chose. Under A: the AR (with
   `--expires`). Under C: the separate blueprint commit. The `*authentik*`
   deny rule stays. This plan does not touch it.

## 4. Verification

Each gate lists what its failure prints.

- **G1: every pod on the new tag and Ready, init included.**
  ```bash
  kubectl get pods -n kube-system -l app.kubernetes.io/instance=authentik \
    -o custom-columns='NAME:.metadata.name,IMAGE:.spec.containers[0].image,INIT:.spec.initContainers[*].image,READY:.status.containerStatuses[0].ready' \
    | grep -v 'server:2026.8.5.*server:2026.8.5.*true'
  ```
  PASS: only the header line (plus the `authentik-pg` pod line, whose image is
  `postgres:18.6-bookworm`, if the label matches it). FAIL: any pod still on
  `:2026.8.3` (old ReplicaSet serving, or init skew), or `false`.
- **G2: no unexpected schema change (CONTENTS).** Re-run pre-check 5.
  CONTENTS ASSERTION: `django_migrations` row count after == before. Measured by
  `MIGCOUNT`, compared to `/private/tmp/authentik-2026.8.5-baseline.txt`
  (777). FAIL: any other number. 2026.8.5 ships no migrations, so a change
  means a different image than the one analysed in §1 is running. Stop and read
  the new rows before deciding on §5, because a revert is then no longer
  trivially schema-safe.
- **G3: blueprints intact (CONTENTS).** Same output as G2. PASS:
  - `notok []`, with counts equal to the baseline line
    (`system 11, cberg 23, default 19, migrations 1`) and no `<BARE>`.
  - `GT empty [] of 19`.
  - `TOKCNT` 10, or 10 again after step 7.

  FAIL: any provider listed in `GT empty`. That is the silent failure where
  every login to that app fails while authentik looks healthy
  (`project_authentik_blueprint_grant_types`). A `notok` row is also a FAIL:
  first read its task log per SOP "stuck in `error`".

  Then run SOP "Verification after the rollout" check 2:
  `kubectl get ingress -A` must print `No resources found`, and every outpost
  must still show `kubernetes_disabled_components ['ingress']`, which the G6
  ak-shell output prints. Then SOP check 3: the login-flow stage orders equal
  the SOP's expected list.
- **G4: task workers alive (CONTROL).**
  CONTROL: metric authentik_tasks_workers. The gate reads
  `min(authentik_tasks_workers{version="2026.8.5"})`, which must be ≥ 1
  (baseline 3).
  ```bash
  kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
  curl -s localhost:19090/api/v1/query --data-urlencode 'query=min(authentik_tasks_workers{version="2026.8.5"})' \
    | python3 -c 'import sys,json; r=json.load(sys.stdin)["data"]["result"]; print("WORKERS", r[0]["value"][1] if r else "EMPTY"); sys.exit(0 if r and float(r[0]["value"][1])>=1 else 1)'
  curl -s localhost:19090/api/v1/alerts | python3 -c 'import sys,json; a=[x["labels"]["alertname"] for x in json.load(sys.stdin)["data"]["alerts"] if x["labels"]["alertname"].startswith("Authentik") and x["state"]=="firing"]; print("FIRING", sorted(set(a)))'
  kill $PF
  ```
  The `version="2026.8.5"` matcher is what lets this fail. `EMPTY` means the new
  pods are not exporting or not scraped, and `0` means the worker pool is dead.
  Both exit 1.
  CONTROL: alertname AuthentikTaskWorkersZero. Must not be in `FIRING`. Since
  `403298e1` it ignores the stale previous-version series that made it a false
  positive on 2026.8.3.
  CONTROL: alertname AuthentikServerDown. Not firing.
  CONTROL: alertname AuthentikWorkerDown. Not firing.
  CONTROL: alertname AuthentikPodCrashLooping. Not firing.
- **G5: real logins, both paths (CONTENTS).**
  CONTENTS ASSERTION: an OIDC login and a forward-auth login both complete on
  2026.8.5. Measured by a real browser login, after logging out, to Grafana
  (OIDC) and to Homepage or Longhorn (forward-auth). Then confirm in the
  audit table:
  ```bash
  kubectl exec -n kube-system deploy/authentik-pg -- psql -U authentik -d authentik -Atc \
    "select action, created from authentik_events_event where action in ('login','authorize_application') and created > now() - interval '15 minutes' order by created desc limit 5"
  ```
  PASS: at least one `login` and one `authorize_application` row newer than the
  step 3 push. FAIL: zero rows. The browser "worked" from a cached session and
  proved nothing (the 2026.8.3 caveat). Do not accept a caveat here: pre-check
  8 removed its cause.
- **G6: outposts on 2026.8.5, connected, Services intact (CONTENTS).** Run
  this no earlier than 6 min after the last push. Outposts re-dial on a backoff
  of up to 300 s. If it fails, wait 5 min and re-run ONCE.
  ```bash
  kubectl get deploy -n kube-system -o jsonpath='{range .items[*]}{.spec.template.spec.containers[0].image}{"\n"}{end}' | grep -c 'goauthentik/proxy:2026.8.5'   # 13
  kubectl get svc -n kube-system -o name | grep -c ak-outpost                                                                        # 27
  POD=$(kubectl get pods -n kube-system -l app.kubernetes.io/component=server -o jsonpath='{.items[0].metadata.name}')
  kubectl exec -n kube-system "$POD" -c server -- ak shell -c "
  from authentik.outposts.models import Outpost, OutpostState
  for o in Outpost.objects.all(): print('OP', o.name, o.config.kubernetes_disabled_components, sorted({str(s.version) for s in OutpostState.for_outpost(o)}))
  " 2>/dev/null | grep '^OP' | grep -v "\['ingress'\] \['2026.8.5'\]"
  ```
  PASS: `13`, `27`, and the last command prints nothing. Every one of the 14
  outposts must report `['ingress']` and exactly `['2026.8.5']`.

  FAIL readings:
  - `12` or fewer: a push was skipped.
  - `26`: the portless-Service bug deleted a Service (SOP §2).
  - Any `OP` line: that outpost is not connected on the new build, or it lost
    the ingress suppression. Measured 2026-10-15 on 2026.8.3: all 14 lines
    read `['ingress'] ['2026.8.3']`, so the filter matches today's healthy
    state with the version swapped.

  CONTROL: metric authentik_outpost_connection. Three exact readings, all required
  (port-forward Prometheus first: `kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 &`,
  then `curl -s -G localhost:19090/api/v1/query --data-urlencode 'query=<Q>'`):
  - Q1 `count(count by (outpost_name)(authentik_outpost_connection{version="2026.8.5"} == 1))` must be exactly **14**
    (13 forward-auth outposts + the embedded outpost, which reports once per server pod, so 16 series but 14 names).
    A bare `>= 13` would pass with an outpost missing; an EMPTY result is a FAIL (nothing on 8.5 is connected).
  - Q2 `count(authentik_outpost_connection{version!="2026.8.5"}) or vector(0)` must be **0** (stale old-version
    series disappear ~5 min after the last push; non-zero after 6 min = an outpost or server pod still on 8.3).
  - Q3 `count(authentik_outpost_connection == 0) or vector(0)` must be **0**.
  Controls measured live 2026-10-23 (all still on 8.3): Q1 with `version="2026.8.3"` returned 12-13 while two outposts sat in the
  known 5-min recycle dip and is 14 when all are connected (so a short count is a real signal: wait for the
  dip to end, re-run once); Q1 as written for 8.5 returns EMPTY today (the gate fails before the change); the `or vector(0)`
  form is required because `count(x == 0)` is empty, not 0, when nothing matches.
  CONTROL: alertname AuthentikOutpostNotUpdated. Not firing 20 min after step 6.
  It is the alert that says an outpost lags the server version.
  CONTROL: alertname AuthentikOutpostDisconnected. Not firing 20 min after
  step 6.
  CONTROL: alertname AuthentikOutpostMetricsAbsent. Not firing.
- **G7: client-IP behaviour, measured (CONTENTS; the §1 gotcha).**
  Run the probe on **F-7006f363** (`runbooks/policy-cli.py finding show F-7006f363`;
  the command and the expected reading live there, not in this public file).
  CONTENTS ASSERTION: the client IP authentik acts on matches the decision taken in
  §1. Measured by the `REMOTE` field of the probe's own access-log line, compared to
  the pre-check 6 baseline; the expected post-roll value for the chosen option is
  read from the decision record. A baseline-like reading after the roll means the
  image is not 2026.8.5: re-run G1. No `REMOTE` line at all is a FAIL of the probe
  itself (wrong host, or logs not reached), not a pass.

## 5. Rollback

**Server/worker (G1-G5 or G7 fail):**
```bash
git revert --no-edit <step-3 sha>
git show --stat HEAD && git log -1 --format=%s     # 1 file, subject "Revert ..."
git push
```
Flux rolls server, worker and both init containers back to 2026.8.3 together.
2026.8.5 adds no migrations (G2 asserts that the count is unchanged), so there is
no schema to undo. Confirm with G1 grepping for `2026.8.3`, plus G5 and G7
(reading back to the pre-check 6 baseline).

If G2 showed new migration rows, do NOT revert blind. Read the rows first. If
2026.8.3 then refuses to start, restore `authentik-pg-data` from the backup
named in pre-check 4, following `docs/sops/backup.md`. Before restoring, take a
`pg_dump` of `deploy/authentik-pg` to `~/db-dumps/authentik-pre-restore-<ts>.dump`.
It holds secrets: purge it once done.

**Outposts (any step 6 failure):** for each outpost already pushed, run
`kubectl set image -n kube-system deploy/ak-outpost-<app>-forward-auth proxy=ghcr.io/goauthentik/proxy:2026.8.3`.
Never `kubectl delete` an outpost Deployment, and never `o.save()` to "fix" it.
If a Service vanished (`26` in G6), recreate it by copying an intact sibling's
spec: `selector` = the Deployment's `spec.selector.matchLabels`, ports 9000
(http) and 9443 (https), with numeric `targetPort` (SOP §2). Server and outposts
are cross-version compatible, but push outposts back after a server revert so
the versions agree.

Afterwards: delete the silence and run `runbooks/update-marker.sh clear authentik`.
PRs #364/#359 stay open (held by the deny rule) until a retry.

## 6. Interference notes

- **Operator decision first (§1 decision card, pre-check 0).** The window agent's
  go/no-go for this plan IS that decision. Present A/B/C verbatim, not as "patch
  bump, go?".
- **Ordering: `authentik-web-max-requests` first** (nightly), at least two nights
  earlier so its 24 h soak is read (pre-check 8). Same `helmrelease.yaml`; never two
  pending commits in one window.
- **Attended slot only** (SSO blast radius, a manual 13-outpost push, a real-browser
  login gate). Not `nightly`. No reboot; 45 min.
- **talos-linux-1.14.4:** a node roll evicts or severs authentik pods and outpost
  websockets. Declared; not the same slot.
- **envoy-proxy-config-distroless-v1.39.4 / v1.40.0** (drafts): they restart the
  Envoy data plane that carries `auth.<domain>` and every forward-auth ext-auth
  call. Running either makes a login failure unattributable and confounds G7.
  Declared. Under option B, the Envoy-side follow-up plan (see F-7006f363) becomes this plan's `depends_on`.
- **flux-reconciler-impersonation** (exclusive, blocked): declared, carried over.
- **etcd-timeouts-5000-500:** declared; etcd must be quiet during the roll.
- **coredns-1.48.1:** no conflict declared. authentik resolves only `authentik-pg`
  in-cluster. Avoid the same slot anyway if capacity allows, since login failures
  there would be ambiguous.
- **Prometheus:** G4/G6 read it. No kube-prometheus-stack plan is open (92.x plans
  retired 2026-10-23); if one is ever planned, serialize it away from this slot.
- **Repo corrections noted:** the `*authentik*` deny rule and SOP are consistent with
  this plan; the stale `project_authentik_outpost_upgrade` memory recommending bulk
  `o.save()` is superseded by SOP §2 (see §1).
