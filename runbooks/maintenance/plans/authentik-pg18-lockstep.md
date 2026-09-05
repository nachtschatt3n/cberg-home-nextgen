---
plan_id: authentik-pg18-lockstep
component: authentik
pr: null                              # no open Renovate PR found (gh pr list --search authentik: empty);
                                      # coverage.py currently holds the chart bump in LOCKSTEP behind the
                                      # image sibling before a PR is even opened — see Summary.
kind: chart
current: "chart 2026.8.0 (server+worker+initContainers ghcr.io/goauthentik/server:2026.8.0, 12x proxy outposts ghcr.io/goauthentik/proxy:2026.8.0); bundled/rollback postgresql pinned 17.11-bookworm"
target: "chart 2026.8.1 (server+worker+initContainers :2026.8.1, outposts pushed to :2026.8.1); bundled/rollback postgresql image bump to 18.6-bookworm DECLINED — stays pinned 17.11-bookworm, see Summary"
update_type: patch                    # the executed half (chart) is a patch release; the image half is
                                      # a major bump that this plan deliberately does NOT execute
risk: medium                          # identity-plane blast radius (see touches.shared), but a
                                      # same-line (2026.8.x) patch bump following a documented SOP with
                                      # a pre-flight check — not the minor/major jump that has crashlooped
                                      # this app before (2026.5.6 -> 2026.8.0)
est_duration_min: 35
needs_reboot: false
touches:
  namespaces: [kube-system]
  resources:
    - helmrelease/authentik                              # chart.spec.version + 2 initContainer image tags
    - deployment/authentik-server                         # 3 replicas, rolling restart
    - deployment/authentik-worker                         # 3 replicas, rolling restart
    - deployment/ak-outpost-alertmanager-forward-auth
    - deployment/ak-outpost-arag-web-forward-auth
    - deployment/ak-outpost-esphome-forward-auth
    - deployment/ak-outpost-frigate-forward-auth
    - deployment/ak-outpost-headlamp-forward-auth
    - deployment/ak-outpost-homepage-forward-auth
    - deployment/ak-outpost-kubernetes-dashboard-forward-auth
    - deployment/ak-outpost-longhorn-forward-auth
    - deployment/ak-outpost-nocodb-forward-auth
    - deployment/ak-outpost-phpmyadmin-forward-auth
    - deployment/ak-outpost-prometheus-forward-auth
    - deployment/ak-outpost-solarfocus-scraper-forward-auth
    - deployment/ak-outpost-uptime-kuma-forward-auth
    - "NOT touched (deliberately): statefulset/authentik-postgresql (bundled 17.11-bookworm rollback DB) and its PVC data-authentik-postgresql-0"
    - "NOT touched: deployment/authentik-pg (the live postgres:18.6-bookworm DB — already on 18.6 since the 2026-08-20 cutover, out of scope here)"
  shared:
    - identity-provider   # authentik IS the SSO/forward-auth plane for the whole cluster: every
                          # OIDC app (Grafana, Superset, Immich, LibreChat, Mealie, Paperless, ...)
                          # and every one of the 12 forward-auth outposts listed above goes dark on
                          # login if server/worker crashloop or an outpost is left on a broken proxy
                          # build. Treat this as full-cluster-SSO blast radius, not a single-app bump.
    - ingress             # outpost Deployments sit behind their apps' ingress auth-url/auth-signin
                          # annotations; a broken outpost = 401/502 on every app it fronts
depends_on: []
conflicts_with: []        # no resource collision with authentik-pg17-decommission (see Summary) but
                          # both plans edit the SAME FILE (helmrelease.yaml) — see Interference notes
                          # for why they must not be applied as concurrent edits in one window
security_ref: null
capability_change: false  # 2026.8.1 is documented bug fixes only (sources, indexing, proxy header
                          # parsing, websocket, expression engine, LDAP) — no new user-visible
                          # behaviour; the new tx-mode PG pooler support is opt-in and not enabled here
rollback_class: git-revert
finding_refs: [F-8ab2ee07]  # plan-lane finding: "authentik postgres 17.11 finding is attributed to
                            # the already-replaced bundled StatefulSet, and its PLAN lane now
                            # lockstep-blocks the routine authentik chart patch" — this plan is the
                            # "exclude the bundled block from version attribution" arm of its own
                            # prescribed remediation (the other arm, "finish the decommission", is
                            # authentik-pg17-decommission.md, not this plan).
status: draft
window: null
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/authentik.md
  - docs/sops/backup.md
generated: "2026-09-05"
---

# authentik chart 2026.8.0 -> 2026.8.1, with the postgres-18 lockstep sibling declined

## Summary & why held

The auto-updater surfaced this as a **lockstep pair** because `coverage.py`
groups the authentik chart bump with its "postgres 17.11 -> 18.6" image sibling
before either is auto-merged. Investigation shows the pairing is a **stale
attribution artifact**, already diagnosed by the sweep itself
(`F-8ab2ee07`, plan lane, first seen 2026-09-03): *"Live authentik runs
deployment/authentik-pg on postgres:18.6-bookworm (verified 2026-09-03); the
17.11-bookworm tag ... belongs to the SUPERSEDED bundled Bitnami StatefulSet
authentik-postgresql-0, which is still Running but no longer serves
authentik. ... a routine patch is blocked by a decommission."*

Verified independently against the live cluster and repo today (2026-09-05):

- `deployment/authentik-pg` (the DB authentik actually talks to,
  `AUTHENTIK_POSTGRESQL__HOST=authentik-pg`) has run **postgres:18.6-bookworm**
  since the `authentik-postgres-18` cutover on 2026-08-20. It is not part of
  this held update at all.
- The only `postgres:17.11-bookworm` pin left in the repo is
  `postgresql.image.tag` in `kubernetes/apps/kube-system/authentik/app/helmrelease.yaml`,
  which controls the **bundled/legacy StatefulSet `authentik-postgresql`** —
  kept running on purpose as the cutover's rollback (still 1/1 Ready, 243d old,
  holds the pre-cutover data). Its own in-repo comment already forbids the
  bump this held update proposes: *"Pin the postgres image explicitly (chart
  2026.8.0 defaults to 17.11-bookworm). SAME major only: 18.x is a data-dir
  migration."*
- Its accepted-risk row (`AR-113`, sweep finding `F-94ee84b5`) says the same
  thing: *"STALE TARGET, NOT A HELD UPGRADE ... Retiring the 17.11 StatefulSet
  is plan authentik-pg17-decommission ... not being rushed to clear a board."*
- `runbooks/maintenance/plans/authentik-pg17-decommission.md` (status
  `awaiting-soak`) already owns that StatefulSet's endgame: **delete it**, not
  upgrade it in place. A same-tag-swap major bump on a legacy `bitnamilegacy`
  image against a live data directory is exactly the kind of one-way,
  unsupervised data-dir migration that plan's whole gate structure exists to
  prevent doing by accident.

**Verdict: this is not a real lockstep dependency.** The chart bump does not
touch `postgresql.image.tag` (it is an explicit override in our values, not
inherited from the chart default), so nothing technical ties the two together.
This plan executes the **chart bump only** and formally **declines** the
postgres image bump — the image pin stays at `17.11-bookworm` until
`authentik-pg17-decommission` deletes the StatefulSet outright. That decommission
plan's own gates look close to satisfied as of today (7-day soak: satisfied,
16 days elapsed; verified Longhorn backup on the NEW volume `authentik-pg-data`:
satisfied, `lastBackupAt: 2026-09-05T03:06:42Z`) — its remaining gate, a
verified login through both an OIDC app and a forward-auth app since cutover,
is an operator check-off this plan does not attempt to satisfy on its behalf.
That is `authentik-pg17-decommission`'s call to make, not this plan's.

**Does not supersede or duplicate `authentik-pg17-decommission.md`.** That plan
deletes the StatefulSet; this plan does not touch it at all. They edit
different keys of the same `helmrelease.yaml` (chart version + initContainer
tags here, vs. `postgresql.enabled` there) and can run in either order or in
separate windows — see Interference notes for the one real collision (same
file, don't edit concurrently).

**Why the chart half is genuinely worth doing, not just a paperwork close-out:**
2026.8.1's fixed-in notes include a proxy-outpost bug fix ("fixed header
parsing in non-compliant backends and double host sent on token
introspection") that lands on the exact Rust proxy outposts protecting the 12
forward-auth apps below, plus fixes to sources, core indexing, websocket
(`AUTHENTIK_INSECURE=true`), the expression engine, and LDAP `krbLastPwdChange`
handling. No DB-migration or schema-breaking change is documented for 2026.8.1
(the breaking changes on record — trusted-proxy CIDR enforcement, `hash_password`
stdin-only, WebAuthn dup-device removal — landed with 2026.8.0, which we
already run). Bumping also moves `ghcr.io/goauthentik/server` and
`ghcr.io/goauthentik/proxy` off `2026.8.0`, which the security section
separately flags (`F-7dbcf1b6` server, `F-aca2957c` proxy — detail on the
findings, not here: this repo is public).

## Pre-checks

1. Confirm current state matches this plan's assumptions:
   ```bash
   kubectl get deploy -n kube-system authentik-server authentik-worker \
     -o custom-columns=NAME:.metadata.name,IMAGE:.spec.template.spec.containers[0].image
   kubectl get pods -n kube-system -l app.kubernetes.io/instance=authentik \
     -o custom-columns=NAME:.metadata.name,IMAGE:.spec.containers[0].image,READY:.status.containerStatuses[0].ready
   kubectl get deploy -n kube-system -l 'app.kubernetes.io/name notin ()' 2>/dev/null | grep ak-outpost
   ```
2. Pre-flight the new server image before committing anything (catches a moved
   `settings.py` path or a renamed setting that would make the `sed` in the
   initContainer silently no-op):
   ```bash
   kubectl run ak-preflight --rm -i --restart=Never -n kube-system \
     --image=ghcr.io/goauthentik/server:2026.8.1 --command -- sh -c '
     test -f /authentik/root/settings.py && echo settings.py OK
     grep -c "SESSION_EXPIRE_AT_BROWSER_CLOSE = True" /authentik/root/settings.py'
   ```
   Expect `settings.py OK` and a count of `1`. If either fails, STOP — do not
   proceed with this plan as written; the `patch-session-settings` initContainer
   hack needs re-validating against the new image first.
3. Verify the target chart version and both image tags actually exist:
   ```bash
   curl -sI -H "Accept: application/vnd.oci.image.index.v1+json" \
     "https://ghcr.io/v2/goauthentik/server/manifests/2026.8.1" | grep -i docker-content-digest
   curl -sI -H "Accept: application/vnd.oci.image.index.v1+json" \
     "https://ghcr.io/v2/goauthentik/proxy/manifests/2026.8.1" | grep -i docker-content-digest
   helm show chart oci://ghcr.io/goauthentik/helm-charts/authentik --version 2026.8.1 >/dev/null
   ```
4. Confirm no in-flight Flux reconcile / other authentik change is running:
   `flux get helmrelease -n kube-system authentik`.
5. Confirm no other plan is mid-edit on
   `kubernetes/apps/kube-system/authentik/app/helmrelease.yaml` (shared-worktree
   rule — see CLAUDE.md "Committing in a SHARED worktree").
6. Silence alerts + drop an active-update marker per
   `docs/sops/application-update.md` §Step 1:
   ```bash
   runbooks/update-marker.sh add authentik kube-system 2 "chart 2026.8.0->2026.8.1"
   ```

## Steps

Follow `docs/sops/authentik.md` → "Upgrading Authentik" verbatim: **all three
version strings move in one commit.**

1. Edit `kubernetes/apps/kube-system/authentik/app/helmrelease.yaml`:
   - `spec.chart.spec.version`: `2026.8.0` -> `2026.8.1`
   - `server.initContainers[patch-session-settings].image`:
     `ghcr.io/goauthentik/server:2026.8.0` -> `ghcr.io/goauthentik/server:2026.8.1`
   - `worker.initContainers[patch-session-settings].image`: same change
   - Do **not** touch `postgresql.image.tag` (stays `17.11-bookworm`) or
     `postgresql.enabled` (stays `true`) — see Summary.
2. `git commit --only kubernetes/apps/kube-system/authentik/app/helmrelease.yaml -m '...'`
   (per CLAUDE.md shared-worktree rule — do not `git add -A`), then push.
3. Let Flux reconcile (`flux get helmrelease -n kube-system authentik -w`, or
   `interval: 30m` means it may need a `flux reconcile hr authentik -n kube-system`
   if you don't want to wait — that IS calling for reconcile per the SOP path,
   not a manual cluster mutation).
4. Watch the rollout — server and worker are 3 replicas each; confirm every pod
   lands on the new tag AND is Ready (readyReplicas alone lies — it counts
   old-ReplicaSet pods):
   ```bash
   kubectl get pods -n kube-system -l app.kubernetes.io/instance=authentik \
     -o custom-columns='NAME:.metadata.name,IMAGE:.spec.containers[0].image,READY:.status.containerStatuses[0].ready'
   ```
5. Push the 12 managed proxy outposts onto the new image — a server upgrade
   does **not** do this automatically (`docs/sops/authentik.md` §2). **Never
   `kubectl delete` an outpost Deployment** to force it.
   ```bash
   POD=$(kubectl get pods -n kube-system -l app.kubernetes.io/component=server \
     --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}')
   kubectl exec -n kube-system "$POD" -c server -- ak shell -c "
   from authentik.outposts.models import Outpost
   from authentik.outposts.controllers.kubernetes import KubernetesController
   for o in Outpost.objects.all():
       if not o.service_connection: continue
       try: KubernetesController(o, o.service_connection).up()
       except Exception as e: print('partial', o.name, e)
   "
   ```
   Expect a `ControllerException (403)` per outpost (benign RBAC gap at the
   Secret-comparison step — the image bump still lands per the SOP note); a
   bulk `o.save()`-only path would report success and change nothing, so use
   the `up()` form above, not a shortcut.

## Verification

- Every server/worker pod on `ghcr.io/goauthentik/server:2026.8.1` and Ready
  (command in step 4).
- **CONTENTS ASSERTION (auth / SSO, per README's per-class table):** a real
  login through each affected path, not just pod health — ask the SERVER what
  version each outpost reports over its own websocket, which proves the
  proxies actually picked up the new build (pod `Running` on the new tag does
  not prove the controller's `up()` actually reconciled it):
  ```bash
  kubectl exec -n kube-system "$POD" -c server -- ak shell -c "
  from authentik.outposts.models import Outpost, OutpostState
  for o in Outpost.objects.all():
      print(o.name, [s.version for s in OutpostState.for_outpost(o)])
  "
  ```
  Then exercise, with a real browser: one OIDC app login (e.g. Grafana) and one
  forward-auth app login (e.g. Longhorn or Homepage) — both must succeed. These
  fail differently, so both paths, not one.
- OIDC providers kept non-empty `grant_types` across the blueprint re-apply
  that a server restart triggers (the field an upgrade can silently zero per
  `docs/sops/authentik.md` "Rules & gotchas"):
  ```bash
  kubectl exec -n kube-system "$POD" -c server -- ak shell -c "
  from authentik.providers.oauth2.models import OAuth2Provider
  for p in OAuth2Provider.objects.all(): print(p.name, p.grant_types)
  "
  ```
  Every row must be non-empty (`[authorization_code, refresh_token]` at minimum).
- No crashloop: `kubectl get pods -n kube-system -l app.kubernetes.io/instance=authentik | grep -v Running` returns nothing.
- Bundled 17.11 StatefulSet untouched and still Running (proves the decline
  held): `kubectl get sts -n kube-system authentik-postgresql` still `1/1`,
  `kubectl get pod -n kube-system -l app.kubernetes.io/name=postgresql -o jsonpath='{.items[0].spec.containers[0].image}'`
  still `...postgres:17.11-bookworm`.
- `runbooks/version-check-current.md` next run shows the chart finding
  (`F-2fb59c74`) resolved and the image finding (`F-94ee84b5`/AR-113) still
  present, unchanged and still AR-suppressed (proves the decline didn't
  accidentally get merged too).

## Rollback

`git revert` the chart-bump commit, push, let Flux reconcile back to
`2026.8.0` + matching initContainer tags. No destructive migration is
documented for 2026.8.1, so a straight revert is expected to be clean; if
Django already ran a forward migration that the 2026.8.0 code can't read,
treat it as `authentik-postgres-18`'s rollback path does — restore from the
`authentik-pg-data` Longhorn backup (`lastBackupAt: 2026-09-05T03:06:42Z` as of
this writing) rather than fighting a downgrade. After a revert, re-run the
outpost push (step 5) pointed at `2026.8.0` — outposts do not auto-follow a
downgrade any more than they auto-follow an upgrade. Clear the update marker
and restore alert routing per `docs/sops/application-update.md` §Step 5.

## Interference notes

- **Full-cluster SSO blast radius.** If server/worker crashloop mid-rollout,
  every OIDC and forward-auth app in the cluster loses login simultaneously —
  this is not scoped to `kube-system`. Do not run this alongside any other
  identity-adjacent change (Authentik blueprint edits, ingress-controller
  work) in the same window.
- **Same-file collision, not a resource collision, with `authentik-pg17-decommission`.**
  Both plans edit `kubernetes/apps/kube-system/authentik/app/helmrelease.yaml`
  but touch disjoint keys (chart version/initContainers here vs.
  `postgresql.enabled` there). If both are scheduled in the same window, apply
  them as two sequential commits (edit, commit, push, reconcile, verify — then
  the next plan's edit), never as concurrent edits to the same working copy,
  per the shared-worktree rule in CLAUDE.md.
- **This plan is the reason `F-8ab2ee07` and the coverage.py lockstep exist.**
  Once this plan executes, re-check whether `coverage.py`'s lockstep grouping
  needs the same "exclude the bundled 17.11 image from version attribution"
  fix at the source, or whether it will keep re-pairing routine future
  authentik chart patches with the same stale image finding until
  `authentik-pg17-decommission` finally executes. That is a tooling fix, out
  of scope for this plan, but worth flagging back to the sweep.
- **Do not treat this plan as clearing `authentik-pg17-decommission`'s gate.**
  Its soak (16 days) and backup (today's) gates look satisfied by coincidence
  of timing, not because of anything this plan does — the remaining
  dual-path-login gate is that plan's own pre-check, to be run fresh at its
  own execution time, not backdated to this plan's verification pass.
- **Parallel pg18-family work elsewhere this cycle** (paperless-ngx's bundled-DB
  exit/major-bump plans, superset's postgres cutover/decommission plans) shares
  no namespace, storage, or resource with authentik's DB work — no direct
  technical interference. But they are all major/high-risk DB-adjacent changes;
  the window agent should avoid stacking more than one live-DB cutover/major
  bump per window regardless of namespace, to keep operator attention and the
  03:00 Longhorn backup CronJob from overlapping several at once. This plan
  itself adds none of that risk — the DB-adjacent half is declined, not run.
- **Outpost and server images each have an open security record**
  (`F-aca2957c` proxy, `F-7dbcf1b6` server). Everything about their content
  lives on those records — `runbooks/policy-cli.py finding detail F-aca2957c`
  — and is deliberately not restated in this file, which is public. This bump
  is expected to resolve both on next scan: confirm post-execution against the
  findings rather than assuming.
