---
plan_id: authentik-2026.5.6
component: authentik
pr: null                            # Renovate PR # — fill in when opened; no open
                                    # PR found via gh at plan time (2026.5.5 was the
                                    # last merged, commit 0fc9921d)
kind: chart                         # authentik Helm chart bump (chart == appVersion)
current: "2026.5.5"
target: "2026.5.6"
update_type: patch
risk: medium                        # patch CONTENT is low-drama, but authentik is
                                    # the SSO enforcement point (auth.<DOMAIN>) — a
                                    # bad roll locks every forward-auth/SAML app out
est_duration_min: 30
needs_reboot: false                 # pods roll in place; no node reboot → weekday slot
touches:
  namespaces: [kube-system]
  resources:
    - helmrelease/authentik
    - deployment/authentik-server          # 3 replicas roll to :2026.5.6
    - deployment/authentik-worker           # 3 replicas roll to :2026.5.6
    - statefulset/authentik-postgresql       # server runs startup DB migrations
                                             # against it (NOT itself upgraded)
    - "deployment/ak-outpost-*-forward-auth"  # ~12 managed proxy outposts —
                                             # image does NOT auto-roll (see Steps 4)
  shared: [auth]                    # EVERY forward-auth-proxied app (homepage,
                                    # longhorn, prometheus, frigate, phpmyadmin, …)
                                    # + SAML apps (wazuh, opensearch) authenticate
                                    # through authentik. A bad roll = SSO outage for
                                    # all of them. The window agent must treat any
                                    # co-scheduled plan that also touches auth, or
                                    # any app-behind-authentik upgrade, as interference.
depends_on: []
conflicts_with: []                  # no other plan competes; but do NOT co-schedule
                                    # any plan for an app that sits behind authentik
                                    # forward-auth (see Interference notes)
status: awaiting-go                  # 2026-08-04 tue-early (unattended cron): risk
                                    # medium + auto_execute:false → fails the
                                    # unattended bar (max_unattended_risk: low).
                                    # Also NOT unattendable by construction: pre-check
                                    # 2.2 requires an interactive SSO login.
                                    # CVE re-scan 2026-08-04: 2026.5.6 does NOT clear
                                    # the carried critical — CVE-2026-31789 (openssl
                                    # 3.5.5-1~deb13u1) present identically in
                                    # proxy:2026.5.5 and :2026.5.6 → no security
                                    # urgency. go/no-go pushed. NOT applied.
window: "tue-early:2026-08-04"
auto_execute: false                 # medium + auth path → operator go/no-go always
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/authentik.md
  - docs/sops/backup.md
generated: "2026-07-31"
---

# authentik 2026.5.5 → 2026.5.6 — SSO/forward-auth chart patch

## 1. Summary & why held

**What changes:** a single-minor **patch** of the authentik Helm chart in
`kubernetes/apps/kube-system/authentik/app/helmrelease.yaml`:
`spec.chart.spec.version: 2026.5.5 → 2026.5.6`. The chart version == appVersion, so
this rolls the **server** (`ghcr.io/goauthentik/server`) and **worker** pods to
`:2026.5.6`. Two additional in-file image pins must move in lockstep — the
`patch-session-settings` init containers on both server and worker hardcode
`image: ghcr.io/goauthentik/server:2026.5.5` (helmrelease.yaml lines ~96 and
~224); they copy/patch `settings.py` and must match the running server version, so
**all three `2026.5.5` occurrences → `2026.5.6`**.

**Target verified published (2026-07-31):**
- Chart `2026.5.6` present in `https://charts.goauthentik.io/index.yaml`.
- `ghcr.io/goauthentik/server:2026.5.6` → HTTP 200.
- `ghcr.io/goauthentik/proxy:2026.5.6` → HTTP 200 (needed for the outpost roll, Step 4).

**Why it was held:** authentik is the cluster's **SSO enforcement point**
(`auth.${SECRET_DOMAIN}`, exposed via the external ingress → Cloudflare tunnel) and
the forward-auth gate for ~12 apps plus the SAML IdP for Wazuh/OpenSearch. The
auto-updater does not auto-merge an auth-path component even on a patch: the blast
radius of a mis-rolled auth server is "everyone is locked out," which is a
window-only change. The bump is tagged an **auth-path CVE remediation** — note the
image also **"drop[s] curl and runit"** from the container (CVE-surface reduction)
and rebases, so the Trivy image-CVE delta reads as a CVE bump even though there is
no named *application* CVE.

**Upstream evidence — genuine patch, no breaking change, no migration**
([2026.5 release notes](https://docs.goauthentik.io/releases/2026.5/)): the 2026.5.6
section lists **no CVEs and no breaking changes**. It is bug-fixes + hardening:
`"fix auth schema for device endpoints"`, `"in-process per-IP rate throttle"`,
`"filter policy engine"` (perf), several SCIM-provider fixes, `"drop curl and runit"`
from the container image, `"app view failing when no events permissions"`. None
require a data migration or config change. So the **content risk is low**; `risk:
medium` is set entirely by the **auth blast radius**, not by the diff. This is not a
false-positive hold — the policy correctly routed an auth-path item to a window.

**The one thing that makes this non-trivial (do not skip):** the managed
forward-auth proxy **outposts do NOT auto-roll their image on a server bump.** The
~12 `ak-outpost-*-forward-auth` Deployments keep running `proxy:2026.5.5` (still
functional — outpost/server are cross-version compatible — but carrying the old
image's CVEs, so the CVE remediation is *incomplete* until they roll). They are
forced to `:2026.5.6` with a bulk `o.save()` in the ak shell (Step 4).
**NEVER `kubectl delete` an outpost Deployment to force it** — authentik does not
promptly recreate a deleted managed Deployment, which causes a forward-auth OUTAGE
for that app (learned the hard way on the 2026.2.3→2026.5.2 upgrade).

## 2. Pre-checks

Run from repo root (`cd /Users/mu/code/cberg-home-nextgen`). **All must pass before
the bump.**

```bash
# 2.1 authentik currently healthy on 2026.5.5 — HR Ready, server+worker 3/3
mise exec -- kubectl get helmrelease -n kube-system authentik \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion}{"\n"}'
# Expected: "True 2026.5.5"
mise exec -- kubectl get pods -n kube-system -l app.kubernetes.io/instance=authentik
# Expected: authentik-server (3/3) + authentik-worker (3/3) Running, 0 restarts,
#           authentik-postgresql-0 Running.

# 2.2 SSO actually works RIGHT NOW (baseline — so a post-roll failure is attributable).
#     Do an interactive login through a proxied app AND capture the outpost baseline:
mise exec -- kubectl get deploy -n kube-system -l app.kubernetes.io/managed-by=goauthentik.io \
  -o custom-columns=NAME:.metadata.name,IMAGE:'.spec.template.spec.containers[0].image' --no-headers
# Expected: every ak-outpost-*-forward-auth on ghcr.io/goauthentik/proxy:2026.5.5.
#           Record the COUNT of outposts — Step 4 must roll all of them.

# 2.3 Blueprints load cleanly (no pre-existing blueprint error that a roll would surface)
WRK=$(mise exec -- kubectl get pods -n kube-system -l app.kubernetes.io/component=worker \
  -o jsonpath='{.items[0].metadata.name}')
mise exec -- kubectl exec -n kube-system "$WRK" -c worker -- ak shell -c \
  "from authentik.blueprints.models import BlueprintInstance;
print('blueprints:', BlueprintInstance.objects.count(),
      'errored:', BlueprintInstance.objects.exclude(status='successful').count())"
# Expected: errored: 0

# 2.4 Fresh Longhorn backup of the authentik postgres volume (< 24h) — recovery
#     floor for the startup migration. (data-authentik-postgresql-0)
mise exec -- kubectl get jobs -n storage | grep daily-backup-all-volumes | tail -1
# Expected: last backup job Complete within 24h. If not → trigger a backup first
#           (docs/sops/backup.md) before proceeding.

# 2.5 No in-flight Flux reconcile
mise exec -- flux get helmreleases -A | grep -vE "True|^NAMESPACE"   # empty
mise exec -- flux get kustomizations -A | grep -vE "True|^NAMESPACE" # empty

# 2.6 Zero firing alerts (Watchdog/InfoInhibitor excluded)
mise exec -- bash -c 'kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &>/dev/null &
sleep 2
curl -s http://localhost:9090/api/v1/alerts | python3 -c "
import sys,json
a=[x for x in json.load(sys.stdin)[\"data\"][\"alerts\"] if x[\"state\"]==\"firing\" and x[\"labels\"][\"alertname\"] not in (\"Watchdog\",\"InfoInhibitor\")]
print(f\"Firing: {len(a)}\")"
kill %1 2>/dev/null'
# Expected: Firing: 0
```

**Go criteria:** HR Ready on 2026.5.5, server+worker 3/3, SSO login works, outposts
all on `proxy:2026.5.5` (count noted), 0 errored blueprints, postgres backup < 24h,
all Flux Ready, 0 firing alerts. Any failure → **stop and surface**.

## 3. Steps

GitOps only. The maintenance-window-agent delegates the git changes to
`cberg-agent`; the outpost `o.save()` (Step 4) is an in-cluster `kubectl exec`, not a
manifest change — it is the one manual action this plan requires.

### 3a. Silence rollout noise + drop an active-update marker

Server (3) + worker (3) rolling, plus outpost pods bouncing in Step 4, will fire
`KubePod*` / `authentik*` noise. Suppress it (application-update.md §Step 1):

```bash
cd /Users/mu/code/cberg-home-nextgen
mise exec -- bash -c 'kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 &>/dev/null &
sleep 2
NOW=$(python3 -c "from datetime import *;print(datetime.now(timezone.utc).strftime(\"%Y-%m-%dT%H:%M:%S.000Z\"))")
END=$(python3 -c "from datetime import *;print((datetime.now(timezone.utc)+timedelta(hours=2)).strftime(\"%Y-%m-%dT%H:%M:%S.000Z\"))")
curl -s -X POST localhost:9093/api/v2/silences -H "Content-Type: application/json" -d "{
  \"matchers\":[{\"name\":\"namespace\",\"value\":\"kube-system\",\"isRegex\":false,\"isEqual\":true},
              {\"name\":\"alertname\",\"value\":\"authentik.*|Kube(Pod|Deployment).*\",\"isRegex\":true,\"isEqual\":true}],
  \"startsAt\":\"$NOW\",\"endsAt\":\"$END\",\"createdBy\":\"operator\",
  \"comment\":\"authentik 2026.5.5->2026.5.6 upgrade — rollout noise. auto-expires 2h\"}"
kill %1 2>/dev/null'

runbooks/update-marker.sh add authentik kube-system 2 "2026.5.5->2026.5.6 chart patch"
```

### 3b. Bump the chart + init-container image pins in git

All **three** `2026.5.5` occurrences in the HelmRelease move to `2026.5.6`
(chart version + the two `patch-session-settings` init-container images):

```bash
cd /Users/mu/code/cberg-home-nextgen
sed -i '' 's/2026\.5\.5/2026.5.6/g' \
  kubernetes/apps/kube-system/authentik/app/helmrelease.yaml

# Verify exactly the 3 intended lines changed (chart version + 2 init images), nothing else:
grep -n "2026.5.6" kubernetes/apps/kube-system/authentik/app/helmrelease.yaml
# Expected: 3 hits — spec.chart.spec.version, and two `ghcr.io/goauthentik/server:2026.5.6`.
git diff kubernetes/apps/kube-system/authentik/app/helmrelease.yaml

git add kubernetes/apps/kube-system/authentik/app/helmrelease.yaml
git commit -m "feat(authentik): update chart + server image ( 2026.5.5 → 2026.5.6 )"
git push
```

> If a Renovate PR is open for this, merging it is equivalent for the chart-version
> line — but confirm it ALSO bumps the two init-container image pins. Renovate has
> historically bumped the chart line only; if the PR leaves the init images at
> `2026.5.5`, follow up with the `sed` above so the `settings.py` patch matches the
> server. Do not leave a version skew between server and its init container.

### 3c. Let Flux reconcile, watch the server/worker roll

```bash
mise exec -- flux reconcile helmrelease -n kube-system authentik --with-source
mise exec -- kubectl rollout status deploy/authentik-server -n kube-system --timeout=10m
mise exec -- kubectl rollout status deploy/authentik-worker -n kube-system --timeout=10m
# Watch the first new server pod's logs for the startup DB migration to complete
# cleanly (patch migrations are light, but confirm no migration error):
mise exec -- kubectl logs -n kube-system -l app.kubernetes.io/component=server \
  --tail=60 | grep -iE "migrat|error|listen" | tail -20
```

If the server crash-loops on a migration (should not for a patch), do NOT let it
thrash — see Rollback (§5). `upgrade.remediation.retries: 3` stays as-is; a patch
migration does not justify disabling rollback, and `cleanupOnFail: true` is already set.

### 3d. Confirm the auth path BEFORE touching outposts

```bash
# Server up on the new version, HR Ready
mise exec -- kubectl get helmrelease -n kube-system authentik \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion}{"\n"}'
# Expected: "True 2026.5.6"
# Interactive: log in through a proxied app (e.g. Longhorn UI) — SSO redirect to
# auth.<DOMAIN> and back must still work. Do NOT proceed to Step 4 if SSO is broken.
```

### 4. Roll the managed proxy outposts to :2026.5.6 (the held-reason step)

The outpost Deployments are still on `proxy:2026.5.5`. Force them all to `:2026.5.6`
with a bulk `o.save()` (fires `post_save` → controller re-renders each Deployment
with the new `%(version)s`). **~30s. Do NOT `kubectl delete` an outpost Deployment.**

```bash
WRK=$(mise exec -- kubectl get pods -n kube-system -l app.kubernetes.io/component=worker \
  -o jsonpath='{.items[0].metadata.name}')
mise exec -- kubectl exec -n kube-system "$WRK" -c worker -- ak shell -c "
from authentik.outposts.models import Outpost
for o in Outpost.objects.all(): o.save()
print('re-saved', Outpost.objects.count(), 'outposts')
"
# Then watch them roll:
mise exec -- kubectl get pods -n kube-system -l app.kubernetes.io/managed-by=goauthentik.io -w
# (Ctrl-C once all ak-outpost-* pods are Running on the new ReplicaSet.)
```

### 5. Clear silence + marker on success

```bash
runbooks/update-marker.sh clear authentik
# delete the silence early if healthy (else it self-expires in 2h):
mise exec -- bash -c 'kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 &>/dev/null &
sleep 2
curl -s localhost:9093/api/v2/silences | python3 -c "
import sys,json
for s in json.load(sys.stdin):
  if \"authentik 2026.5.5->2026.5.6\" in s.get(\"comment\",\"\"): print(s[\"id\"])" | \
  xargs -I{} curl -s -X DELETE localhost:9093/api/v2/silences/{}
kill %1 2>/dev/null'
```

## 4. Verification

```bash
# 4.1 HelmRelease reconciled + Ready on the new chart
mise exec -- kubectl get helmrelease -n kube-system authentik \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion}{"\n"}'
# Expected: "True 2026.5.6"

# 4.2 server + worker on :2026.5.6, 3/3 each, 0 restarts after settle
mise exec -- kubectl get pods -n kube-system -l app.kubernetes.io/instance=authentik \
  -o custom-columns=NAME:.metadata.name,IMAGE:'.spec.containers[*].image',READY:.status.containerStatuses[*].ready
mise exec -- kubectl get deploy -n kube-system authentik-server authentik-worker \
  -o custom-columns=NAME:.metadata.name,IMAGE:'.spec.template.spec.containers[0].image'
# Expected: ghcr.io/goauthentik/server:2026.5.6 on both.

# 4.3 EVERY outpost advanced to proxy:2026.5.6 (the held-reason gate) — none left on .5.5
mise exec -- kubectl get deploy -n kube-system -l app.kubernetes.io/managed-by=goauthentik.io \
  -o custom-columns=NAME:.metadata.name,IMAGE:'.spec.template.spec.containers[0].image' --no-headers
# Expected: all N (Pre-check 2.2 count) on ghcr.io/goauthentik/proxy:2026.5.6, all Ready.

# 4.4 Blueprints still load cleanly (roll didn't break blueprint apply)
WRK=$(mise exec -- kubectl get pods -n kube-system -l app.kubernetes.io/component=worker \
  -o jsonpath='{.items[0].metadata.name}')
mise exec -- kubectl exec -n kube-system "$WRK" -c worker -- ak shell -c \
  "from authentik.blueprints.models import BlueprintInstance;
print('errored:', BlueprintInstance.objects.exclude(status='successful').count())"
# Expected: errored: 0

# 4.5 SSO end-to-end through a forward-auth app AND a SAML app:
#   - Forward-auth: open Longhorn / Prometheus / Homepage → redirect to
#     auth.<DOMAIN>, authenticate, land back in the app.
#   - SAML: open Wazuh / OpenSearch Dashboards → "Sign in with SSO" round-trips.
#   Both must succeed. This is the real success signal.

# 4.6 auth.<DOMAIN> ingress serves (external class / Cloudflare tunnel path)
mise exec -- kubectl get ingress -n kube-system authentik-server

# 4.7 Zero firing alerts once the silence is dropped
mise exec -- bash -c 'kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &>/dev/null &
sleep 2
curl -s http://localhost:9090/api/v1/alerts | python3 -c "
import sys,json
a=[x for x in json.load(sys.stdin)[\"data\"][\"alerts\"] if x[\"state\"]==\"firing\" and x[\"labels\"][\"alertname\"] not in (\"Watchdog\",\"InfoInhibitor\")]
print(f\"Firing: {len(a)}\")"
kill %1 2>/dev/null'
# Expected: Firing: 0
```

**Success =** HR Ready on 2026.5.6, server+worker 3/3 on `:2026.5.6`, **all N
outposts on `proxy:2026.5.6`**, 0 errored blueprints, forward-auth **and** SAML SSO
both round-trip, 0 firing alerts.

## 5. Rollback

Single-file chart revert. authentik server/worker roll back to `:2026.5.5`; the
bundled postgres is untouched by a within-minor patch (no schema downgrade needed —
2026.5.6 migrations are additive/light, and the DB backup from Pre-check 2.4 is the
floor if anything went sideways).

```bash
cd /Users/mu/code/cberg-home-nextgen

# Revert the bump commit (restores all 3 pins to 2026.5.5)
git log --oneline -5 -- kubernetes/apps/kube-system/authentik/app/helmrelease.yaml
git revert --no-edit <bump-commit-sha>
git push
mise exec -- flux reconcile helmrelease -n kube-system authentik --with-source
mise exec -- kubectl rollout status deploy/authentik-server -n kube-system --timeout=10m
mise exec -- kubectl rollout status deploy/authentik-worker -n kube-system --timeout=10m

# If server is wedged pending-upgrade after a failed migration:
#   mise exec -- helm rollback authentik <last-deployed-rev> -n kube-system --wait=false
#   mise exec -- flux reconcile helmrelease -n kube-system authentik --force

# Roll the outposts BACK to proxy:2026.5.5 too (same o.save() mechanism — the
# controller re-renders them to match the now-reverted server version). NEVER
# kubectl delete an outpost Deployment.
WRK=$(mise exec -- kubectl get pods -n kube-system -l app.kubernetes.io/component=worker \
  -o jsonpath='{.items[0].metadata.name}')
mise exec -- kubectl exec -n kube-system "$WRK" -c worker -- ak shell -c "
from authentik.outposts.models import Outpost
for o in Outpost.objects.all(): o.save()
"
```

**Confirm cluster is back:** HR Ready on `2026.5.5` (Verification 4.1), server+worker
3/3 on `:2026.5.5`, all outposts back on `proxy:2026.5.5` (4.3), forward-auth + SAML
SSO both round-trip (4.5). Clear the update marker (`runbooks/update-marker.sh clear
authentik`) and drop the silence.

## 6. Interference notes

- **Weekday window, non-reboot.** `needs_reboot: false` — pods roll in place. Assign
  to `tue-early` or `thu-early` (1h, `allow_reboot: false`). Risk weight 2. ~30 min
  budget (bump + reconcile + server/worker roll + the outpost `o.save()` roll +
  interactive SSO verification) fits the 1h slot comfortably.
- **`shared: [auth]` is the whole story.** During the server roll (Step 3c) and the
  outpost roll (Step 4) there are brief moments where a forward-auth check or a SAML
  handshake can fail transiently. **Do NOT co-schedule, in the same window, any plan
  that upgrades an app sitting behind authentik forward-auth** (longhorn, prometheus,
  homepage, frigate, phpmyadmin, …) **or a SAML app** (wazuh, opensearch) — its own
  verification could flap on an auth blip and be misread as its failure. If the
  window agent finds such a plan queued for the same slot, **run authentik first,
  fully verify SSO (4.5), then run the other** — or defer the other to the next slot.
- **The outpost roll is mandatory and easy to forget.** A "successful" server bump
  that leaves the outposts on `proxy:2026.5.5` is an INCOMPLETE upgrade — the CVE
  remediation this bump exists for is not delivered until the outposts roll (Step 4 /
  Verification 4.3). The window agent must not mark the plan executed until 4.3 shows
  all outposts on `:2026.5.6`.
- **Never `kubectl delete` a managed outpost Deployment** to "force" it — authentik
  does not promptly recreate it, causing a forward-auth OUTAGE for that app. Use
  `o.save()` only (Step 4). This applies in rollback too.
- **Bundled postgres is in the blast namespace but not upgraded.** The server runs
  startup migrations against `authentik-postgresql-0` (Longhorn volume
  `data-authentik-postgresql-0`); the Pre-check 2.4 backup is the recovery floor.
  Do not touch the postgres StatefulSet as part of this plan.
- **cberg-agent does the GitOps (Steps 3a–3c, 3b commit/push); the `ak shell`
  `o.save()` (Step 4) and the interactive SSO checks (4.5) are the operator-present
  in-cluster actions.** No direct manifest mutation outside the single helmrelease.yaml edit.
