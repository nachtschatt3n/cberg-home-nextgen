---
plan_id: nextcloud-redis-hardening
component: nextcloud-redis
pr: null                              # Not a version bump. No Renovate PR exists or can
                                      # exist: this changes a Deployment's command, a
                                      # NetworkPolicy's `from:`, a SOPS Secret and three
                                      # HelmRelease values. security_ref carries the driver.
kind: config
current: "deploy/office/nextcloud-redis runs `redis-server --save \"\" --appendonly no` with NO --requirepass (live 2026-09-22); networkpolicy/office/nextcloud-redis ingress is `ports: [6379/TCP]` with NO `from:` (allow-from-anywhere on that port, live 2026-09-22); the main container's REDIS_URL is the unauthenticated `redis://$(REDIS_HOST):$(REDIS_HOST_PORT)` form; config.php persists `redis.password: ''`"
target: "requirepass from a SOPS-managed key (`nextcloud-config/redis-password`) enforced by a sh -c wrapper that REFUSES to start unauthenticated; every consumer (main container, cron pods, the hand-declared sidecar, notify_push via config.php) authenticates; the NetworkPolicy admits only the three real consumer pod sets; a non-consumer pod is PROVEN unable to connect"
update_type: hardening
risk: medium                          # No data at risk — this Redis holds cache, PHP
                                      # sessions and transient file locks, no PVC, nothing
                                      # survives a restart by design. What IS at risk is
                                      # availability during the window (every request 500s
                                      # if server and clients disagree on auth for even a
                                      # minute — hence the quiesce) and one known trap:
                                      # notify_push reads config.php, not env, and
                                      # reconnect-loops behind a green HelmRelease if the
                                      # password is not persisted there (d6070b82 lesson).
est_duration_min: 45                  # quiesce 5 · git+reconcile 10 · verify 20 · resume 10
needs_reboot: false
touches:
  namespaces: [office]
  resources:
    - deployment/nextcloud-redis                # command (wrapper + --requirepass), env
    - networkpolicy/nextcloud-redis             # ingress `from:` podSelectors
    - secret/nextcloud-config                   # NEW key redis-password (SOPS)
    - helmrelease/nextcloud                     # externalRedis.existingSecret + sidecar env
    - deployment/nextcloud                      # rolls (new env); quiesced for the window
    - cronjob/nextcloud-cron                    # new env via the chart; suspended in-window
    - deployment/nextcloud-notify-push          # rolls after config.php carries the password
    - pvc/nextcloud-config                      # config.php rewritten IN PLACE by occ (backed up first)
    - kustomization/nextcloud                   # suspended during the quiesce
  shared: []                                    # office-local. NOT `storage`: no volume operation.
depends_on: []
conflicts_with:
  - nextcloud-34.0.4                    # vetted, sun-attended:2026-10-04. Same helmrelease.yaml,
                                        # same deployment/nextcloud roll, same quiesce shape.
                                        # Two plans editing one HelmRelease in one slot is the
                                        # interference the window agent exists to catch.
                                        # RECIPROCITY GAP: that plan's list does not name this
                                        # plan_id (it predates this file); the scheduler honours
                                        # either side, so this one-sided entry is sufficient.
  - bitnamilegacy-exit-nextcloud-db     # blocked, window:null — latent. Same app quiesced,
                                        # risk:high, and its rollback is a DB restore; never
                                        # stack a session-store auth change on that.
  - nextcloud-mcp-0.187.1               # awaiting-go, sat-attended:2026-10-03. Different
                                        # HelmRelease and nextcloud-mcp does NOT connect to
                                        # this Redis (CLIENT LIST, 2026-09-22) — but its
                                        # verification calls the Nextcloud API, which this
                                        # plan takes down for ~20 min. Keep them apart.
security_ref: F-069b1775              # posture detail lives on the finding, not here
capability_change: false              # same cache/session/lock service, same app behaviour
rollback_class: git-revert            # ONE commit, three files, reverts cleanly — PLUS the
                                      # occ un-set of config.php (§5), which the revert
                                      # cannot do because config.php lives on the PVC.
backup_gate: "config.php copied IN-POD to config.php.pre-redis-auth-<ts> BEFORE the quiesce (§3.1, asserted by a byte-count compare), and a Completed Longhorn backup of volume nextcloud-config < 26h (premise config-volume-backed-up + §2 gate 3). No datastore dump: this Redis holds nothing durable."
finding_refs: [F-069b1775]            # filed 2026-08-19 (policy-cli finding show,
                                      # 2026-09-22). Its `action` is exactly this plan.
status: draft                         # WRITTEN 2026-09-22, NOT reviewed. Every command
                                      # below names an object verified to exist on
                                      # 2026-09-22; every gate was designed to have a
                                      # concrete failing input (stated inline). A
                                      # plan-reviewer pass is still required before `vetted`.
window: null                          # the scheduler assigns after vetting. Attended: every
                                      # logged-in user is logged out (PHP sessions live in
                                      # this Redis, no persistence) — announce it.
premises:
  # Read-verb only (plan-premises.py refuses exec). Each was run 2026-09-22 and
  # returned the expected value.
  - id: redis-still-unauthenticated
    why: >-
      The whole plan assumes the server has no requirepass. If the command
      already carries one, the quiesce/cutover shape is wrong and §3 must be
      re-planned from the live state. Measured 2026-09-22.
    run: kubectl get deploy -n office nextcloud-redis -o jsonpath='{.spec.template.spec.containers[0].command}'
    expect_exact: '["redis-server","--save","","--appendonly","no"]'
  - id: netpol-source-open
    why: >-
      The `from:`-less rule is half of the finding. If someone already added a
      source restriction, §3.3's edit must merge with it rather than replace it.
      Measured 2026-09-22.
    run: kubectl get networkpolicy -n office nextcloud-redis -o jsonpath='{.spec.ingress[0]}'
    expect_exact: '{"ports":[{"port":6379,"protocol":"TCP"}]}'
  - id: main-url-unauthenticated
    why: >-
      Proves the chart currently renders the password-less REDIS_URL form, i.e.
      externalRedis.existingSecret is not yet set. §4 gate 3 asserts the OTHER
      form after the change, so this is the before-state that makes that gate
      meaningful. Measured 2026-09-22.
    run: kubectl get deploy -n office nextcloud -o jsonpath='{.spec.template.spec.containers[?(@.name=="nextcloud")].env[?(@.name=="REDIS_URL")].value}'
    expect_exact: 'redis://$(REDIS_HOST):$(REDIS_HOST_PORT)'
  - id: notify-push-parses-config-php
    why: >-
      notify_push is started with config.php as its argument and parses it
      directly — that is why §3.7's occ write is mandatory and why a green
      HelmRelease proves nothing for it. If this ever changes (e.g. it starts
      reading REDIS_* env), §3.7 becomes optional. Measured 2026-09-22.
    run: kubectl get deploy -n office nextcloud-notify-push -o jsonpath='{.spec.template.spec.containers[0].command[1]}'
    expect_exact: /var/www/html/config/config.php
  - id: config-volume-backed-up
    why: >-
      §3.7 rewrites config.php on pvc/nextcloud-config. A Completed Longhorn
      backup of that volume must exist before anything writes to it (11
      Completed on 2026-09-22). Freshness is asserted in §2 because it is
      time-relative.
    run: kubectl get backups.longhorn.io -n storage -o jsonpath='{.items[?(@.status.volumeName=="nextcloud-config")].status.state}'
    expect_contains: Completed
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/bundled-datastore-exit.md      # §4 "Redis variant" — the wiring this plan completes
  - docs/sops/secret-rotation.md             # consumer-roll + in-pod hash verification
  - docs/sops/sops-encryption.md
  - docs/sops/container-dependencies.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-09-22"
---

# nextcloud-redis: requirepass + source-restricted NetworkPolicy

## 1. Summary & why

`deploy/office/nextcloud-redis` (official `redis:8.10.1-alpine`, plain manifests in
`kubernetes/apps/office/nextcloud/app/redis-deployment.yaml`) replaced the
chart-bundled Redis on 2026-08-19 (`d6070b82`) as a *pure registry move*: it
deliberately kept the retired instance's posture — no `--requirepass`, and a
NetworkPolicy that names a port but no source. Both were inherited, not
introduced; the operator deferred hardening out of that already-crowded window
and filed **`F-069b1775`** with the shape of the fix. This plan is that fix,
and closes that finding when it lands (§6). Posture detail stays on the finding record.

**Contextual tier, per CLAUDE.md:** the Service is `ClusterIP` with no
HTTPRoute — internal-only, not external-unauth, so it does not reach this
household's `critical` tier. It is nonetheless the store for PHP **sessions**
and **file locks** (`memcache.locking` and `memcache.distributed` are both
`\OC\Memcache\Redis`, read via `occ` 2026-09-22), so the exposure is not
limited to cache poisoning. Medium, worth one attended window.

### 1.1 What must move together — measured, not inferred (2026-09-22)

The password has to appear in **five** places in the same change set, or every
Nextcloud request fails:

| Consumer | How it gets the host today | How it will get the password | Proof |
|---|---|---|---|
| main container | chart `externalRedis.host` → `REDIS_HOST`; `redis.config.php` overlay reads `getenv('REDIS_HOST_PASSWORD')` | `externalRedis.existingSecret.{enabled,secretName,passwordKey}` renders `REDIS_HOST_PASSWORD` from `secretKeyRef` AND flips `REDIS_URL` to `redis://:$(REDIS_HOST_PASSWORD)@…` | `helm template` of chart **9.2.6** with those values, run locally 2026-09-22 (`_helpers.tpl` L197-226); in-pod `redis.config.php` read the same day |
| image entrypoint (`session.save_path`) | `/entrypoint.sh` L98-117 builds `tcp://host:port?auth=<REDIS_HOST_PASSWORD>` | same env var — nothing extra | read in-pod 2026-09-22 |
| cron pods (`cronjob/nextcloud-cron`) | chart includes `nextcloud.env` in the CronJob template too | same values, automatically | `helm template`: the rendered `nextcloud-cron` carries the same four `REDIS_*` env entries |
| the hand-declared sidecar in `helmrelease.yaml` (~L296-330, the container that carries its OWN `REDIS_HOST: nextcloud-redis`) | hardcoded env, **not** chart-driven — no `externalRedis` value reaches it | add `REDIS_HOST_PASSWORD` from `secretKeyRef` by hand, next to its `REDIS_HOST` | the manifest comment says exactly this: "keep in lockstep with externalRedis.host" |
| `deployment/nextcloud-notify-push` | **parses `config.php` directly**, ignores env and the overlay (`notify-push.yaml` note; premise `notify-push-parses-config-php`) | `occ config:system:set redis password --value=…` so the value is PERSISTED in `config.php`, then roll the Deployment | live `occ config:system:get redis` shows `password: ''` today; `occ notify_push:self-test` is the gate that can fail |

Who actually connects (Redis `CLIENT LIST`, 2026-09-22): the main pod (19
connections), one `nextcloud-cron` pod (1), `nextcloud-notify-push` (1), plus
the probe on `127.0.0.1`. `nextcloud-metrics`, `nextcloud-mcp`,
`nextcloud-whiteboard`, `nextcloud-mariadb` do **not** connect — the
NetworkPolicy `from:` below is derived from that, not from "what sounds
related". Pod labels, read live: main `app.kubernetes.io/instance=nextcloud` +
`app.kubernetes.io/component=app`; cron `…/instance=nextcloud` +
`…/component=cronjob`; notify-push `app=nextcloud-notify-push`.

### 1.2 Why a `sh -c` wrapper and not `$(REDIS_PASSWORD)` argv expansion

The two sibling deployments (`paperless-redis`, `superset-redis-official`) use
Kubernetes `$(REDIS_PASSWORD)` expansion in `command:`. That works — but if the
env var is ever missing, Kubernetes leaves the literal `$(REDIS_PASSWORD)` in
place and Redis starts with *that* as the password, and an **empty** value
yields `--requirepass ""`, which Redis documents as "no password" (not
exercised here — stated from the Redis config semantics). The wrapper below
asserts non-empty and refuses to start otherwise, so a broken Secret produces a
CrashLoopBackOff instead of an unauthenticated server that every check reads as
healthy. Both forms leave the password in the container's argv; `REDISCLI_AUTH`
keeps it off the probe's.

### 1.3 Why a quiesce, not a rolling change

Redis has no dual mode: the moment `requirepass` is live, un-authenticated
clients get `NOAUTH`; before it is live, an authenticating client gets
`ERR AUTH … called without any password configured`. There is no order of
operations with zero errors, so the app is scaled to 0 for the swap and brought
back only after the server side is proven (§4 gates 1-2). Every user is logged
out regardless — sessions live in this Redis and it has no persistence.

## 2. Pre-checks

Run `runbooks/plan-premises.py nextcloud-redis-hardening --require-premises`
first — fails closed. Then the gates below, which need `exec` and time
arithmetic the premise runner cannot do.

```bash
# Informational first:
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
flux get helmreleases -A   | awk 'NR==1 || $5 != "True"'
kubectl -n office get pods -l app=nextcloud-redis            # 1/1 Running
kubectl -n office get pods -l app.kubernetes.io/instance=nextcloud
```

```bash
set -euo pipefail

# --- Gate 1: the server answers UNauthenticated today (before-state) --------
R=$(kubectl -n office exec deploy/nextcloud-redis -- redis-cli ping | tr -d '[:space:]')
echo "ping=$R"
[ "$R" = "PONG" ] || { echo "ABORT: expected PONG from an unauthenticated ping, got '$R' — the before-state is not what this plan assumes"; exit 1; }
# Failing input: a server already carrying requirepass answers NOAUTH -> exit 1.

# --- Gate 2: the consumer set is still exactly the three we selector-for ----
kubectl -n office exec deploy/nextcloud-redis -- redis-cli CLIENT LIST \
  | awk '{for(i=1;i<=NF;i++) if($i ~ /^addr=/) print $i}' | sed 's/addr=//; s/:[0-9]*$//' | sort -u > /tmp/nc-redis-clients.txt
kubectl -n office get pods -o custom-columns='IP:.status.podIP,NAME:.metadata.name' --no-headers > /tmp/nc-pods.txt
while read ip; do
  [ "$ip" = "127.0.0.1" ] && continue
  n=$(awk -v ip="$ip" '$1==ip{print $2}' /tmp/nc-pods.txt)
  echo "client $ip -> ${n:-UNKNOWN}"
  case "$n" in nextcloud-[0-9a-f]*|nextcloud-cron-*|nextcloud-notify-push-*) ;;
    *) echo "ABORT: a client outside the selector set is connected ($ip -> ${n:-UNKNOWN}); the from: block below would cut it off"; exit 1 ;;
  esac
done < /tmp/nc-redis-clients.txt
# Failing input: any connected IP that maps to a pod not matched by the case
# (or to no pod at all) exits 1. Dry-tested 2026-09-22 against the live list:
# three pods, all matched -> PASS; an injected 10.0.0.1 -> ABORT.

# --- Gate 3: the config volume's newest Completed backup is FRESH (<26h) -----
LB=$(kubectl -n storage get backups.longhorn.io \
      -o jsonpath='{range .items[*]}{.status.volumeName}{" "}{.status.state}{" "}{.status.backupCreatedAt}{"\n"}{end}' \
    | awk '$1=="nextcloud-config" && $2=="Completed" {print $3}' | sort | tail -1)
echo "newest Completed backup=[$LB]"
BSEC=$(date -u -j -f "%Y-%m-%dT%H:%M:%SZ" "$LB" "+%s" 2>/dev/null) \
  || { echo "ABORT: no parseable Completed backup for nextcloud-config"; exit 1; }
AGE_H=$(( ( $(date -u +%s) - BSEC ) / 3600 ))
echo "backup age=${AGE_H}h"
[ "$AGE_H" -lt 26 ] || { echo "ABORT: newest backup is ${AGE_H}h old (bound 26h)"; exit 1; }
# BSD date form, same as paperless-db-13.0.2 §2 gate 3 (macOS: no `date -d`).
# Failing input: an empty LB fails the parse and exits 1.

# --- Gate 4: notify_push is healthy BEFORE we touch it (so a red after is ours)
kubectl -n office exec deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ notify_push:self-test" > /tmp/np-pre.txt
grep -q "receiving redis messages" /tmp/np-pre.txt && ! grep -q "✗" /tmp/np-pre.txt \
  || { echo "ABORT: notify_push self-test is not clean before the change:"; cat /tmp/np-pre.txt; exit 1; }
# Measured 2026-09-22: six ✓ lines, no ✗ -> PASS.
```

**ABORT if** any gate exits non-zero, or if the window is unattended — users
are logged out and this plan needs a human on the `occ` step.

## 3. Steps

All cluster writes are executed by the window agent / cberg-agent. Manifest and
Secret changes are GitOps; the one in-place write (`config.php`, §3.7) is the
documented no-GitOps-path exception (CLAUDE.md) and is backed up first.

**3.0 Generate the password on this Mac — alphanumeric ONLY:**

```bash
PW=$(LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 40); echo "${#PW} chars"
[ "${#PW}" -eq 40 ] || { echo "ABORT: generator produced ${#PW} chars"; exit 1; }
```

Why no symbols: the chart embeds it in `redis://:<pw>@host:port` and the image
entrypoint in `?auth=<pw>` — URL-reserved characters (`@ : / ? & # %`) corrupt
both. Keep `$PW` in this shell; it is typed into `sops` once and never printed.

**3.1 Back up config.php, then quiesce (silence + marker first):**

```bash
runbooks/update-marker.sh add nextcloud office 1 "redis auth hardening — users logged out"
# pre-silence the Nextcloud HTTP/Kuma alerts per docs/sops/application-update.md Step 1

set -euo pipefail
TS=$(date +%Y%m%d%H%M)
kubectl -n office exec deploy/nextcloud -c nextcloud -- sh -c \
  "cp /var/www/html/config/config.php /var/www/html/config/config.php.pre-redis-auth-$TS && \
   wc -c < /var/www/html/config/config.php && wc -c < /var/www/html/config/config.php.pre-redis-auth-$TS" \
  | tr -d ' ' | uniq -c | awk '$1!=2{print "ABORT: backup byte count differs from source"; exit 1}'
echo "backup: config.php.pre-redis-auth-$TS"
# Failing input: a copy that produced a different size prints two distinct
# counts -> uniq -c yields lines with count 1 -> ABORT.

flux suspend helmrelease   nextcloud -n office
flux suspend kustomization nextcloud -n office
kubectl -n office patch cronjob nextcloud-cron -p '{"spec":{"suspend":true}}'
kubectl -n office scale deploy/nextcloud            --replicas=0
kubectl -n office scale deploy/nextcloud-notify-push --replicas=0
kubectl -n office wait --for=delete pod -l app.kubernetes.io/component=app,app.kubernetes.io/instance=nextcloud --timeout=180s
kubectl -n office wait --for=delete pod -l app=nextcloud-notify-push --timeout=120s
# any in-flight cron pod finishes on its own; wait for it:
kubectl -n office wait --for=delete pod -l app.kubernetes.io/component=cronjob --timeout=300s || true

# PROVE the quiesce at the server, not at the pod list:
N=$(kubectl -n office exec deploy/nextcloud-redis -- redis-cli CLIENT LIST | grep -vc 'addr=127.0.0.1' || true)
echo "non-local redis clients=$N"
[ "$N" -eq 0 ] || { echo "ABORT: $N client(s) still connected — quiesce did not hold"; exit 1; }
```

**3.2 Secret — add the key (repo path, never `/tmp`):**

```bash
sops kubernetes/apps/office/nextcloud/app/secrets.sops.yaml
#   under stringData of Secret nextcloud-config add:
#   redis-password: <paste $PW>
sops -d kubernetes/apps/office/nextcloud/app/secrets.sops.yaml | grep -c '^  redis-password:'   # 1
```

**3.3 `redis-deployment.yaml` — wrapper, env, and the `from:` block:**

```yaml
        command:
        - /bin/sh
        - -c
        - |
          # Refuse to start unauthenticated: an empty --requirepass means "no
          # password" to Redis, and a missing env var must be a crash, not a
          # silently open server.
          [ -n "$REDIS_PASSWORD" ] || { echo "REDIS_PASSWORD is empty — refusing to start"; exit 1; }
          exec redis-server --save "" --appendonly no --requirepass "$REDIS_PASSWORD"
        env:
        - name: REDIS_PASSWORD
          valueFrom:
            secretKeyRef:
              name: nextcloud-config
              key: redis-password
        # redis-cli reads REDISCLI_AUTH — keeps the password off the probe argv.
        - name: REDISCLI_AUTH
          valueFrom:
            secretKeyRef:
              name: nextcloud-config
              key: redis-password
```

Probes stay `redis-cli ping | grep -q PONG` (bare `redis-cli ping` exits 0 on
`NOAUTH` — measured 2026-09-22 against `paperless-redis`: `exit=0`, grep form
`exit=1`).

```yaml
  ingress:
  - from:
    - podSelector:
        matchExpressions:
        - {key: app.kubernetes.io/instance,  operator: In, values: [nextcloud]}
        - {key: app.kubernetes.io/component, operator: In, values: [app, cronjob]}
    - podSelector:
        matchLabels:
          app: nextcloud-notify-push
    ports:
    - port: 6379
      protocol: TCP
```

Rewrite the file's header comment: the "Deliberately NO --requirepass" and
"READ THE SEMANTICS" paragraphs describe the state this plan removes — replace
them with one line pointing at this plan's commit, do not leave them to mislead.

**3.4 `helmrelease.yaml` — three edits:**

```yaml
    externalRedis:
      enabled: true
      host: nextcloud-redis
      port: "6379"
      existingSecret:
        enabled: true
        secretName: nextcloud-config
        passwordKey: redis-password
```

Leave `redis.enabled: false` and `redis.auth.enabled: false` exactly as they
are — in the `externalRedis` branch the URL form is selected by
`existingSecret`, and the existing comment's reason for keeping `auth.enabled:
false` still holds. Then, in the hand-declared sidecar (~L327, next to its
`REDIS_HOST: nextcloud-redis`):

```yaml
            - name: REDIS_HOST_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: nextcloud-config
                  key: redis-password
```

Update the "No password — matches the retired instance" comment under
`externalRedis` in the same edit.

**3.5 Render-check locally, commit, push:**

```bash
task kubeconform
helm template nextcloud --repo https://nextcloud.github.io/helm/ --version 9.2.6 \
  -f <(yq '.spec.values' kubernetes/apps/office/nextcloud/app/helmrelease.yaml) 2>/dev/null \
  | grep -c 'REDIS_HOST_PASSWORD'     # expect >= 2 (main deployment + cron)
git fetch origin main && git merge --ff-only origin/main
git commit --only kubernetes/apps/office/nextcloud/app/secrets.sops.yaml \
                  kubernetes/apps/office/nextcloud/app/redis-deployment.yaml \
                  kubernetes/apps/office/nextcloud/app/helmrelease.yaml -F <msgfile>
git log -1 --format=%s     # shared worktree: YOUR subject
git show --stat HEAD       # exactly the three files
git push origin main
```

**3.6 Land the server side first (HR still suspended), prove it:**

```bash
flux resume    kustomization nextcloud -n office
flux reconcile kustomization nextcloud -n office --with-source
kubectl -n office rollout status deploy/nextcloud-redis --timeout=180s
# §4 gates 1 and 2 NOW — do not resume the HelmRelease until both pass.
```

**3.7 Bring the app back, persist the password for notify_push, resume the rest:**

```bash
flux resume    helmrelease nextcloud -n office
flux reconcile helmrelease nextcloud -n office
# The values change fires a Helm upgrade, which re-asserts the chart's replicas;
# assert rather than assume (the paperless-db plan measured a no-values-change
# resume NOT restoring replicas):
[ "$(kubectl -n office get deploy nextcloud -o jsonpath='{.spec.replicas}')" = "1" ] \
  || kubectl -n office scale deploy/nextcloud --replicas=1
kubectl -n office rollout status deploy/nextcloud --timeout=300s
# §4 gate 3 (env) and gate 4 (app) NOW.

# Persist into config.php — the ONLY way notify_push learns the password:
kubectl -n office exec -i deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c \
  "php occ config:system:set redis password --value=\"$PW\" && php occ config:system:get redis password | wc -c"
# expect a byte count of 41 (40 chars + newline)

kubectl -n office scale deploy/nextcloud-notify-push --replicas=1
kubectl -n office rollout status deploy/nextcloud-notify-push --timeout=180s
# §4 gate 5 NOW.

kubectl -n office patch cronjob nextcloud-cron -p '{"spec":{"suspend":false}}'
# §4 gates 6 and 7, then:
runbooks/update-marker.sh remove nextcloud office
```

## 4. Verification

Each gate names the failure it catches and the input that turns it red.

```bash
set -euo pipefail
# 1. requirepass is LIVE: an unauthenticated ping is refused.
U=$(kubectl -n office exec deploy/nextcloud-redis -- sh -c 'env -u REDISCLI_AUTH redis-cli ping 2>&1' || true)
echo "unauth ping -> $U"
echo "$U" | grep -q NOAUTH || { echo "ABORT: unauthenticated ping was NOT refused — the server is open"; exit 1; }
# CATCHES: the wrapper not taking effect (old ReplicaSet still serving, empty
# password, wrong Secret key). Failing input: the pre-change server answers PONG.
```

```bash
# 2. …and the authenticated path works (the probes depend on it).
A=$(kubectl -n office exec deploy/nextcloud-redis -- sh -c 'redis-cli ping' | tr -d '[:space:]')
[ "$A" = "PONG" ] || { echo "ABORT: authenticated ping got '$A' — REDISCLI_AUTH and --requirepass disagree"; exit 1; }
# CATCHES: two different values in the two env entries (typo in one key name).
```

```bash
# 3. The MAIN container carries the password form, and the SAME value.
URL=$(kubectl -n office get deploy nextcloud -o jsonpath='{.spec.template.spec.containers[?(@.name=="nextcloud")].env[?(@.name=="REDIS_URL")].value}')
[ "$URL" = 'redis://:$(REDIS_HOST_PASSWORD)@$(REDIS_HOST):$(REDIS_HOST_PORT)' ] \
  || { echo "ABORT: REDIS_URL is '$URL' — externalRedis.existingSecret did not render"; exit 1; }
P=$(kubectl -n office exec deploy/nextcloud -c nextcloud -- sh -c 'printf %s "$REDIS_HOST_PASSWORD" | sha256sum | cut -c1-8')
S=$(kubectl -n office get secret nextcloud-config -o jsonpath='{.data.redis-password}' | base64 -d | shasum -a 256 | cut -c1-8)
echo "pod=$P secret=$S"
[ -n "$P" ] && [ "$P" = "$S" ] || { echo "ABORT: pod value ($P) != Secret ($S) — pod started before the Secret landed (docs/sops/secret-rotation.md)"; exit 1; }
# CATCHES: the exact bc4a2fbf failure — a pod rolled before the Secret rewrite.
```

```bash
# 4. The app is USING the authenticated Redis, not erroring past it.
kubectl -n office exec deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ status" | grep -q 'installed: true' \
  || { echo "ABORT: occ status not installed:true"; exit 1; }
curl -s -o /dev/null -w '%{http_code}\n' --max-time 15 https://<nextcloud-host>/status.php | grep -q '^200$' \
  || { echo "ABORT: status.php not 200"; exit 1; }
NA=$(kubectl -n office logs deploy/nextcloud -c nextcloud --since=10m | grep -ci 'NOAUTH\|AUTH failed' || true)
[ "$NA" -eq 0 ] || { echo "ABORT: $NA NOAUTH/AUTH lines in the last 10m"; exit 1; }
K=$(kubectl -n office exec deploy/nextcloud-redis -- sh -c 'redis-cli DBSIZE' | awk '{print $NF}')
echo "keys=$K"
[ "$K" -gt 0 ] || { echo "ABORT: 0 keys after the app served status.php — it is not writing to this Redis"; exit 1; }
# CATCHES: an app that came up but silently lost its cache/locks. DBSIZE was
# ~140 steady-state before the change (redis-deployment.yaml comment); a fresh
# server that stays at 0 after traffic is the red. Failing input: point the app
# at a wrong password and it 500s AND DBSIZE stays 0.
```

```bash
# 5. notify_push re-parsed config.php WITH the password — the d6070b82 trap.
kubectl -n office exec deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ notify_push:self-test" > /tmp/np-post.txt
cat /tmp/np-post.txt
grep -q "receiving redis messages" /tmp/np-post.txt && ! grep -q "✗" /tmp/np-post.txt \
  || { echo "ABORT: notify_push is not healthy after the change — check config.php redis.password and roll the Deployment"; exit 1; }
# CATCHES: §3.7's occ write skipped or the Deployment not rolled after it. This
# exact gate went red on 2026-08-19 behind a green HelmRelease.
```

```bash
# 6. Cron pods authenticate (they get the env from the chart, not from us).
J=nextcloud-cron-verify-$(date +%H%M)
kubectl -n office create job --from=cronjob/nextcloud-cron $J
kubectl -n office wait --for=condition=complete job/$J --timeout=300s \
  || { echo "ABORT: verify cron job did not complete"; kubectl -n office logs job/$J | tail -20; exit 1; }
kubectl -n office logs job/$J | grep -qi 'NOAUTH' && { echo "ABORT: cron job hit NOAUTH"; exit 1; }
kubectl -n office delete job $J
```

```bash
# 7. NetworkPolicy: a NON-consumer cannot reach 6379; a consumer-labelled pod can.
NEG=$(kubectl -n office run np-neg --rm -i --restart=Never --image=busybox:1.38.0 --quiet -- \
        sh -c 'nc -z -w 3 nextcloud-redis 6379; echo rc=$?' 2>/dev/null | tail -1)
POS=$(kubectl -n office run np-pos --rm -i --restart=Never --image=busybox:1.38.0 --quiet \
        --labels=app.kubernetes.io/instance=nextcloud,app.kubernetes.io/component=app -- \
        sh -c 'nc -z -w 3 nextcloud-redis 6379; echo rc=$?' 2>/dev/null | tail -1)
echo "negative control: $NEG   positive control: $POS"
[ "$NEG" = "rc=1" ] || { echo "ABORT: an unlabelled pod reached Redis — the from: block is not enforced (or not applied)"; exit 1; }
[ "$POS" = "rc=0" ] || { echo "ABORT: a consumer-labelled pod could NOT reach Redis — selector too narrow, the app would be locking out"; exit 1; }
# CATCHES both directions: a policy that does not restrict (NEG rc=0) and one
# that restricts too much (POS rc=1). busybox:1.38.0 is the image the chart's
# wait-for-redis init container already uses, so it is present on the nodes.
```

Nightly Longhorn backup of `nextcloud-config` must complete on the next 03:00
cycle (it now holds the rewritten `config.php`). Keep the in-pod
`config.php.pre-redis-auth-*` copy until then.

## 5. Rollback

Trigger: gate 1/2 red after §3.6 (server side wrong) → revert before resuming
the HelmRelease; gate 3-7 red after §3.7 → full sequence below. Sessions are
dropped a second time; say so.

1. Quiesce again (§3.1 minus the backup).
2. `git revert <the §3.5 commit> && git push` — restores the unauthenticated
   command, the `from:`-less policy, and the password-less HelmRelease values
   in one revision.
3. `flux resume kustomization nextcloud -n office && flux reconcile kustomization nextcloud -n office --with-source`;
   `kubectl -n office rollout status deploy/nextcloud-redis` — gate 1 must now
   FAIL (PONG unauthenticated), which is the rollback's success condition.
4. `flux resume helmrelease nextcloud -n office && flux reconcile helmrelease nextcloud -n office`;
   scale to 1; `occ status`.
5. **Un-persist the password — the revert cannot do this:**
   ```bash
   kubectl -n office exec deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c \
     "php occ config:system:set redis password --value=''"
   ```
   If `occ` itself is unhappy, restore the file: `cp config.php.pre-redis-auth-<ts> config.php`
   in-pod (same directory, same owner — read back and `wc -c` compare).
6. Scale notify-push to 1, `occ notify_push:self-test` clean; un-suspend the
   CronJob; remove the marker.

The Secret key `redis-password` may stay in SOPS after a revert; it is inert
without consumers. Do not delete anything on the PVC.

## 6. Interference notes

- **`nextcloud-34.0.4` (sun-attended 2026-10-04) is a hard conflict** — same
  HelmRelease file, same Deployment roll, same quiesce. Whichever lands first,
  the other must re-read `helmrelease.yaml` before editing; the sidecar env
  block and `externalRedis` are edited by THIS plan only.
- **Attended only.** Every logged-in user is logged out; the `occ` write is a
  human-verified step; and gate 7 creates two throwaway pods in `office`.
- **No storage operation.** `pvc/nextcloud-config` is written through `occ`
  (one file), never detached, resized or deleted. The Longhorn backup is the
  floor beneath the in-pod copy.
- **Silence Nextcloud's Kuma/HTTP alerts for the window** and drop the
  active-update marker so the alert-triage agent reads the noise as EXPECTED.
- **Password lands in `config.php` in plaintext** on the PVC — the same file
  already holds the database password; that is Nextcloud's design, not a new
  exposure. It also sits in the container argv of `nextcloud-redis` (readable
  inside that container only), the same as the two sibling Redis deployments.
- **After this lands**, F-069b1775 closes with `finding close F-069b1775 --commit <sha>`
  in the same turn (agent-authored rows never auto-close), and the
  `redis-deployment.yaml` header must no longer describe the open posture.
