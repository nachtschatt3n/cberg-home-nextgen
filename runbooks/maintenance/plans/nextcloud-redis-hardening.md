---
plan_id: nextcloud-redis-hardening
component: nextcloud-redis
pr: null                              # Not a version bump. No Renovate PR exists or can
                                      # exist: this changes two Deployments, a
                                      # NetworkPolicy, a SOPS Secret and HelmRelease
                                      # values. security_ref carries the driver.
kind: config
current: "deploy/office/nextcloud-redis runs `redis-server --save \"\" --appendonly no` with NO --requirepass; networkpolicy/office/nextcloud-redis ingress is `ports: [6379/TCP]` with NO `from:`; the main container's REDIS_URL is the unauthenticated form; deploy/nextcloud-notify-push env is exactly `PORT NEXTCLOUD_URL` and its redis config comes from config.php (password None) -- all re-measured live 2026-09-28"
target: "requirepass from SOPS key `nextcloud-config/redis-password` behind a sh -c wrapper that REFUSES to start unauthenticated; main/cron/worker-sidecar authenticate via the chart's externalRedis.existingSecret + one hand-added env; notify_push authenticates via its OWN `REDIS_URL` env (upstream env-over-config.php precedence), NOT via config.php; the NetworkPolicy admits only the three real consumer pod sets"
update_type: hardening
risk: medium                          # No data at risk: this Redis holds cache, PHP
                                      # sessions and transient file locks, no PVC. What IS
                                      # at risk is availability during the window (every
                                      # request 500s if server and clients disagree on
                                      # auth, hence the quiesce) and every logged-in user
                                      # is logged out. Not low: attended, user-visible.
est_duration_min: 40                  # quiesce 5 · git+reconcile 10 · verify 20 · resume 5
needs_reboot: false
touches:
  namespaces: [office]
  resources:
    - deployment/nextcloud-redis                # command (wrapper + --requirepass), env
    - networkpolicy/nextcloud-redis             # ingress `from:` podSelectors
    - secret/nextcloud-config                   # NEW key redis-password (SOPS)
    - helmrelease/nextcloud                     # externalRedis.existingSecret + worker sidecar env
    - deployment/nextcloud                      # rolls (new env); quiesced for the window
    - cronjob/nextcloud-cron                    # new env via the chart; suspended in-window
    - deployment/nextcloud-notify-push          # NEW env REDIS_PASSWORD + REDIS_URL; rolls
    - deployment/nextcloud-whiteboard           # Reloader-rolled (auto annotation) when Secret nextcloud-config changes
    - kustomization/nextcloud                   # suspended during the quiesce
  shared: []                                    # office-local. No storage operation: config.php
                                                # on pvc/nextcloud-config is NOT written by this
                                                # revision (that was the 09-26 failure mode).
depends_on: []
conflicts_with:
  - bitnamilegacy-exit-nextcloud-db     # blocked, latent. Same app quiesced, risk:high, DB-restore
                                        # rollback; never stack a session-store auth change on it.
  - nextcloud-mcp-0.198.0               # its verification calls the Nextcloud API, which this plan
                                        # takes down for ~20 min. Lists this plan reciprocally.
  - nextcloud-fleet-35.0.1              # draft. Edits helmrelease.yaml AND notify-push.yaml (image
                                        # lockstep) and rolls the same Deployments. Lists this plan.
  - redis-fleet-8.10.2                  # draft. Bumps the image line in redis-deployment.yaml, the
                                        # same file §3.2 patches (3-way merge proven clean, §3.2),
                                        # and Recreate-rolls the same Redis. Lists this plan.
  - flux-reconciler-impersonation       # awaiting-go sun-attended:2026-10-11. Changes how Flux
                                        # applies EVERY namespace incl. office; this plan's §3.3
                                        # depends on the nextcloud Kustomization applying cleanly.
                                        # Not reciprocal on its side (the scheduler honours either).
  - flux-oci-chart-sources              # draft. Its stage 5 moves office/nextcloud to an OCI
                                        # chartRef: rewrites the same helmrelease.yaml §3.2(a)
                                        # 3-way-patches, and after it §3.2(c)'s
                                        # `yq .spec.chart.spec.version` reads null -> render gate
                                        # aborts. Also rolls nextcloud-mariadb. Not reciprocal on
                                        # its side (review 2026-09-28); the scheduler honours either.
security_ref: F-069b1775              # posture detail lives on the finding, not here
capability_change: false              # same cache/session/lock service, same app behaviour
# autonomy_override REMOVED 2026-09-28 under SD-11 ("interruption acceptable, loss
# not"): its only reason was that the redis swap logs every user out. That is
# interruption, which the operator accepts in the nightly window. No data (no
# PVC, cache/sessions/locks only) and no capability change (declared false).
rollback_class: git-revert            # ONE commit, four files, reverts cleanly. Unlike the
                                      # 09-26 revision there is NO in-place config.php write,
                                      # so the revert is the whole rollback.
backup_gate: null                     # nothing durable is touched: no PVC write, no DB, and the
                                      # Redis holds only cache/sessions/locks by design.
finding_refs: [F-069b1775]            # resolved 2026-09-22 on plan authorship (aab921ba; its
                                      # action was "author a hardening plan"). Re-queried
                                      # 2026-09-28: still the only nextcloud-redis posture
                                      # finding. F-3fcdca7b (8.10.1 -> 8.10.2 patch) is a
                                      # version row owned by redis-fleet-8.10.2, not this plan.
review: ready-for-go@2026-09-28
status: awaiting-go  # 2026-10-01 nightly: DEFERRED + go_no_go ingested -- SD-11 derives it pre-approved, but §2 "ABORT if ... the window is unattended" and §6 "Attended only (autonomy_override: human-gated)" were never updated when the override was removed; risk medium. Reconcile the body (or GO it for an attended slot). Was: vetted  # 2026-09-28 RE-PLAN (plan-reviewer ready-for-go, HUMAN-GATED; needs an operator GO) after the 2026-09-26 NOW run was reverted at old §3.7
                # (landing da77a7de, revert b65617d1). Old §3.7 (`occ config:system:set redis
                # password` so notify_push would read it from config.php) was a deterministic
                # no-op. This revision drops the config.php write entirely and gives notify_push
                # the password through its own REDIS_URL env. Needs review + a fresh GO.
window: "now:2026-10-03"   # ON-DEMAND NOW run 2026-10-03 (run-now.py stamp; was 'nightly:2026-10-01')
premises:
  # Read-verb only (plan-premises.py refuses exec). Each run 2026-09-28 and
  # returned the expected value.
  - id: redis-still-unauthenticated
    why: >-
      The whole plan assumes the server has no requirepass. If the command
      already carries one, the quiesce/cutover shape is wrong and §3 must be
      re-planned from the live state. Measured 2026-09-28.
    run: kubectl get deploy -n office nextcloud-redis -o jsonpath='{.spec.template.spec.containers[0].command}'
    expect_exact: '["redis-server","--save","","--appendonly","no"]'
  - id: netpol-source-open
    why: >-
      The `from:`-less rule is half of the finding. If someone already added a
      source restriction, the patch would conflict or overwrite it.
      Measured 2026-09-28.
    run: kubectl get networkpolicy -n office nextcloud-redis -o jsonpath='{.spec.ingress[0]}'
    expect_exact: '{"ports":[{"port":6379,"protocol":"TCP"}]}'
  - id: main-url-unauthenticated
    why: >-
      Before-state of §4 gate 3: the chart currently renders the password-less
      REDIS_URL form, i.e. externalRedis.existingSecret is not yet set.
      Measured 2026-09-28.
    run: kubectl get deploy -n office nextcloud -o jsonpath='{.spec.template.spec.containers[?(@.name=="nextcloud")].env[?(@.name=="REDIS_URL")].value}'
    expect_exact: 'redis://$(REDIS_HOST):$(REDIS_HOST_PORT)'
  - id: notify-push-env-before
    why: >-
      notify_push's env is exactly PORT + NEXTCLOUD_URL today, so its redis
      config comes from config.php (live --dump-config 2026-09-28: host
      nextcloud-redis, password None). The §3.2 patch hunk anchors on this env
      block; if someone already added REDIS_URL, re-derive the patch.
    run: kubectl get deploy -n office nextcloud-notify-push -o jsonpath='{.spec.template.spec.containers[0].env[*].name}'
    expect_exact: 'PORT NEXTCLOUD_URL'
  - id: secret-has-no-redis-password
    why: >-
      §3.2 restores the encrypted key from da77a7de. If the live Secret already
      carries a redis-password key, something else wrote it and §3.2 must stop
      rather than silently replace it. Measured 2026-09-28 (11 keys, none of them
      redis-password).
    run: kubectl get secret -n office nextcloud-config -o jsonpath='{.data}'
    expect_matches: '^(?!.*redis-password)'
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/bundled-datastore-exit.md      # §4 "Redis variant" — the wiring this plan completes
  - docs/sops/secret-rotation.md             # consumer-roll + in-pod hash verification
  - docs/sops/sops-encryption.md
  - docs/sops/container-dependencies.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-09-28"
---

# nextcloud-redis: requirepass + source-restricted NetworkPolicy (re-plan)

## 1. Summary & why

`deploy/office/nextcloud-redis` (official `redis:*-alpine`, plain manifests in
`kubernetes/apps/office/nextcloud/app/redis-deployment.yaml`) kept the retired
bundled instance's posture when it replaced it on 2026-08-19 (`d6070b82`): no
`--requirepass`, and a NetworkPolicy that names a port but no source. The
operator filed **`F-069b1775`**; this plan is the fix. Posture detail stays on
the finding. Contextual tier: ClusterIP, no HTTPRoute, internal-only, so not
`critical`; but it stores PHP **sessions** and **file locks**
(`memcache.locking`/`memcache.distributed` = `\OC\Memcache\Redis`), so medium.

### 1.1 What failed on 2026-09-26, and why this revision cannot fail the same way

The NOW run landed `da77a7de` (Secret key + wrapper + NetworkPolicy +
`externalRedis.existingSecret` + worker-sidecar env). **§4 gates 1-4 (server
refuses unauth, auth path works, main container carries the same password as
the Secret, app serves + writes keys) were GREEN.** It was reverted
(`b65617d1`) at the old §3.7 only: `occ config:system:set redis password`
exited 0 but did not write `config.php` (mtime/size unchanged,
byte-identical to the backup). Nextcloud's `SystemConfig` compares against the
MERGED config, and the chart-mounted `redis.config.php` overlay already puts
`getenv('REDIS_HOST_PASSWORD')` there, so the set is a no-op. `notify_push`
parses `config.php` on disk (it cannot evaluate `getenv()` in overlays), so it
never received the password.

**This revision does not touch `config.php` at all.** `notify_push` gets the
password from its own environment, which upstream gives precedence over
`config.php`:

- `nextcloud/notify_push` **v1.4.1** (the binary in the pod,
  `notify_push --version` → `notify_push 1.4.1`, `appinfo/info.xml` 1.4.1),
  `src/config.rs`:
  ```
  let from_config = opt.config_file ... PartialConfig::from_file(...)
  let from_env = PartialConfig::from_env()?;      // reads REDIS_URL
  let from_opt = PartialConfig::from_opt(opt);
  from_opt.merge(from_env).merge(from_config).try_into()
  ```
  and `merge()` takes `redis` **whole** from the higher-priority side
  (`redis: if self.redis.is_some() { self.redis } else { fallback.redis }`).
  So `REDIS_URL` (host, port, db, password) replaces the config.php redis
  block entirely; the DB URL and everything else still come from config.php.
- `from_env` parses `REDIS_URL` as a `redis::ConnectionInfo` and copies
  `redis_settings().password()`; `redis.rs::open_single` then calls
  `RedisConnectionInfo::set_password`, i.e. AUTH on connect.
- **Measured on the live binary, 2026-09-28** (read-only, `--dump-config`
  prints the parsed config and exits; nothing started or changed):
  without env → `host: "nextcloud-redis" … password: None`;
  with `REDIS_URL="redis://:dummyPW123@nextcloud-redis:6379"` →
  `host: "nextcloud-redis" … username: None, password: Some("dummyPW123")`.
  That is the exact URL shape §3.2 renders.
- Why the old `notify-push.yaml` note "Adding REDIS_HOST here does NOT work"
  is still true and not a contradiction: `from_env` reads `REDIS_URL`, never
  `REDIS_HOST`. The note is amended in the same patch.

### 1.2 What must move together (measured 2026-09-22, re-checked 2026-09-28)

| Consumer | How it gets the password after this plan | Proof |
|---|---|---|
| main container | `externalRedis.existingSecret` renders `REDIS_HOST_PASSWORD` (secretKeyRef) + `REDIS_URL=redis://:$(REDIS_HOST_PASSWORD)@…`; `redis.config.php` overlay reads the env | `helm template` chart **9.3.0** (the live chart) with the patched values: `REDIS_HOST_PASSWORD` entries 0 → **3** (re-run 2026-09-28); gate 3 GREEN on 09-26 |
| image entrypoint (`session.save_path`) | same env var (`?auth=`) | gate 4 GREEN on 09-26 |
| cron pods | chart includes the same env in the CronJob | same render (the 3rd entry) |
| worker sidecar (hand-declared in `helmrelease.yaml`) | hand-added `REDIS_HOST_PASSWORD` next to its `REDIS_HOST` | same render (the 2nd entry) |
| `deployment/nextcloud-notify-push` | **NEW: own env `REDIS_PASSWORD` (secretKeyRef) + `REDIS_URL=redis://:$(REDIS_PASSWORD)@nextcloud-redis:6379`** | upstream precedence + live `--dump-config` above; gates 5/6 |

Who connects (CLIENT LIST 2026-09-28): the main pod (15 conns), notify-push
(1, `cmd=ping`), cron pods intermittently, plus the local `redis-cli`.
`nextcloud-metrics`, `-mcp`, `-whiteboard`, `-mariadb` do not. The NetworkPolicy
`from:` (main+cron by `app.kubernetes.io/instance=nextcloud` +
`component in [app, cronjob]`, notify-push by `app=nextcloud-notify-push`) is
derived from that list — unchanged from `da77a7de`, which applied cleanly.

### 1.3 Why a `sh -c` wrapper, and why a quiesce

Unchanged from the reviewed 09-26 revision: the wrapper refuses to start with
an empty `REDIS_PASSWORD` (an empty `--requirepass` means "no password"), so a
broken Secret is a CrashLoop, not a silently open server. Redis has no dual
mode (NOAUTH vs "AUTH called without any password configured"), so the app is
scaled to 0 for the swap and brought back only after the server side is proven.
Every user is logged out regardless — sessions live in this Redis.

## 2. Pre-checks

Run `.venv/bin/python3 runbooks/plan-premises.py nextcloud-redis-hardening --require-premises`
first — fails closed. Then (zsh on the Mac mini; quoted jsonpaths):

```bash
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'     # informational
flux get helmreleases -A   | awk 'NR==1 || $5 != "True"'
```

```bash
set -euo pipefail
cd /Users/mu/code/cberg-home-nextgen
A=kubernetes/apps/office/nextcloud/app

# --- Gate 1: unauthenticated PONG today (before-state) ----------------------
R=$(kubectl -n office exec deploy/nextcloud-redis -- redis-cli ping | tr -d '[:space:]')
[ "$R" = "PONG" ] || { echo "ABORT: expected unauth PONG, got '$R'"; exit 1; }
# Failing input: a server already carrying requirepass answers NOAUTH.

# --- Gate 2: consumer set is still exactly the three we selector-for --------
kubectl -n office exec deploy/nextcloud-redis -- redis-cli CLIENT LIST \
  | awk '{for(i=1;i<=NF;i++) if($i ~ /^addr=/) print $i}' | sed 's/addr=//; s/:[0-9]*$//' | sort -u > /tmp/nc-redis-clients.txt
[ -s /tmp/nc-redis-clients.txt ] || { echo "ABORT: CLIENT LIST read empty"; exit 1; }
kubectl -n office get pods -o 'custom-columns=IP:.status.podIP,NAME:.metadata.name' --no-headers > /tmp/nc-pods.txt
while read ip; do
  [ "$ip" = "127.0.0.1" ] && continue
  n=$(awk -v ip="$ip" '$1==ip{print $2}' /tmp/nc-pods.txt)
  echo "client $ip -> ${n:-UNKNOWN}"
  case "$n" in nextcloud-[0-9a-f]*-*|nextcloud-cron-*|nextcloud-notify-push-*) ;;
    *) echo "ABORT: client outside the selector set ($ip -> ${n:-UNKNOWN})"; exit 1 ;;
  esac
done < /tmp/nc-redis-clients.txt
# Failing input: any IP mapping to another pod (or none) exits 1. 2026-09-28
# live list: 10.69.0.25 -> nextcloud-77bfc7f4f4-ctz5r, 10.69.0.63 ->
# nextcloud-notify-push-6b7579cf96-vjwwz -> PASS.

# --- Gate 3: the four files are where the patch expects them ----------------
# §3.2 re-applies da77a7de as a 3-way patch. secrets.sops.yaml must be
# byte-identical to the revert (a 3-way merge of a SOPS file would break its MAC).
git fetch -q origin main && git merge --ff-only origin/main
git diff --quiet b65617d1 HEAD -- $A/secrets.sops.yaml \
  || { echo "ABORT: secrets.sops.yaml changed since b65617d1 — do not 3-way a SOPS file; use the fallback in §3.2"; exit 1; }
git diff --quiet HEAD -- $A/ || { echo "ABORT: uncommitted changes under $A (shared worktree) — resolve first"; exit 1; }

# --- Gate 4: notify_push is healthy BEFORE (so a red after is ours) ---------
rc=0; kubectl -n office exec deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ notify_push:self-test" > /tmp/np-pre.txt 2>&1 || rc=$?
cat /tmp/np-pre.txt
[ "$rc" -eq 0 ] && grep -qiF 'push server is receiving redis messages' /tmp/np-pre.txt && ! grep -qiF 'is not receiving' /tmp/np-pre.txt \
  || { echo "ABORT (rc=$rc): notify_push self-test not clean before the change"; exit 1; }
# Live 2026-09-28: six ✓ lines, rc=0. Upstream SelfTest.php failure line is
# "push server is not receiving redis messages" with a non-zero exit.
```

**ABORT if** any gate fails, or if the window is unattended.

## 3. Steps

Executed by the window agent / cberg-agent. Everything is GitOps; there is
**no in-pod write** in this revision.

**3.1 Marker, silence, quiesce:**

```bash
set -euo pipefail
cd /Users/mu/code/cberg-home-nextgen
runbooks/update-marker.sh add nextcloud office 1 "redis auth hardening — users logged out"
# pre-silence the Nextcloud HTTP/Kuma alerts per docs/sops/application-update.md Step 1

flux suspend helmrelease   nextcloud -n office
flux suspend kustomization nextcloud -n office
kubectl -n office patch cronjob nextcloud-cron -p '{"spec":{"suspend":true}}'
kubectl -n office scale deploy/nextcloud             --replicas=0
kubectl -n office scale deploy/nextcloud-notify-push --replicas=0
kubectl -n office wait --for=delete pod -l app.kubernetes.io/component=app,app.kubernetes.io/instance=nextcloud --timeout=180s
kubectl -n office wait --for=delete pod -l app=nextcloud-notify-push --timeout=120s
# let a RUNNING cron pod finish (Completed ones persist and are irrelevant):
for p in $(kubectl -n office get pod -l app.kubernetes.io/component=cronjob --field-selector=status.phase=Running -o name); do
  kubectl -n office wait --for=delete "$p" --timeout=300s || kubectl -n office wait --for=jsonpath='{.status.phase}'=Succeeded "$p" --timeout=60s
done

# PROVE the quiesce at the server:
CL=$(kubectl -n office exec deploy/nextcloud-redis -- redis-cli CLIENT LIST)
echo "$CL" | grep -q 'addr=127.0.0.1' || { echo "ABORT: CLIENT LIST read failed — quiesce unproven"; exit 1; }
N=$(echo "$CL" | grep -vc 'addr=127.0.0.1' || true)
[ "$N" -eq 0 ] || { echo "ABORT: $N client(s) still connected"; exit 1; }
```

**3.2 Build the change (four files) — pre-tested patches, no hand edits:**

```bash
set -euo pipefail
cd /Users/mu/code/cberg-home-nextgen && export SOPS_AGE_KEY_FILE=/Users/mu/code/cberg-home-nextgen/age.key
A=kubernetes/apps/office/nextcloud/app

# (a) Re-apply the reviewed, 09-26-proven server/app half EXACTLY: the diff between
#     the revert and the original landing = da77a7de's change to three files
#     (Secret key redis-password, redis wrapper + REDISCLI_AUTH + NetworkPolicy from:,
#     externalRedis.existingSecret + worker-sidecar REDIS_HOST_PASSWORD).
git diff b65617d1 da77a7de -- $A/helmrelease.yaml $A/redis-deployment.yaml $A/secrets.sops.yaml | git apply --3way
# Dry-tested 2026-09-28 in a --shared clone of this repo: clean on HEAD; and ALSO clean
# (3-way) after a simulated redis 8.10.1 -> 8.10.2 image bump (the image line is hunk
# context), which it PRESERVED: `image: redis:8.10.2-alpine` + `--requirepass` both present.
# Result on HEAD: 3 files changed, 59 insertions(+), 45 deletions(-).

# (b) notify_push gets the password from its OWN env (§1.1):
git apply <<'PATCH'
diff --git a/kubernetes/apps/office/nextcloud/app/notify-push.yaml b/kubernetes/apps/office/nextcloud/app/notify-push.yaml
--- a/kubernetes/apps/office/nextcloud/app/notify-push.yaml
+++ b/kubernetes/apps/office/nextcloud/app/notify-push.yaml
@@ -60,9 +60,31 @@ spec:
           # `occ notify_push:self-test` — a green HelmRelease will not catch
           # it (found the hard way during the 2026-08-19 redis registry move).
           # Adding REDIS_HOST here does NOT work; it was tried and reverted.
+          #
+          # REDIS_URL, however, DOES work and is how the password reaches
+          # notify_push (plan nextcloud-redis-hardening). notify_push's
+          # Config::from_opt merges CLI > env > config.php and takes the env
+          # `redis` block WHOLE when REDIS_URL is set (src/config.rs
+          # v1.4.1, `from_opt.merge(from_env).merge(from_config)`), so the
+          # host AND the password below override config.php. This is also
+          # why `occ config:system:set redis password` cannot be the path:
+          # the chart's redis.config.php overlay already supplies the value
+          # in the merged config, so the set is a no-op and config.php on
+          # disk never changes (reverted b65617d1). Keep the host in
+          # lockstep with externalRedis.host. Verify with
+          # `notify_push --dump-config` (count only, never print it).
           env:
             - name: PORT
               value: "7867"
+            # Declared BEFORE REDIS_URL: $(VAR) expansion only sees earlier
+            # entries. Alphanumeric by construction, so no URL-encoding.
+            - name: REDIS_PASSWORD
+              valueFrom:
+                secretKeyRef:
+                  name: nextcloud-config
+                  key: redis-password
+            - name: REDIS_URL
+              value: "redis://:$(REDIS_PASSWORD)@nextcloud-redis:6379"
             - name: NEXTCLOUD_URL
               value: "http://nextcloud:8080"
           volumeMounts:
PATCH
# Dry-tested 2026-09-28 (`git apply --check` on HEAD). Its hunk is the env block at
# L60-68, away from the `image:` line (L38) that nextcloud-fleet-35.0.1 edits.

# (c) Assert the CONTENTS of what we are about to commit:
sops -d $A/secrets.sops.yaml | .venv/bin/python3 -c 'import sys,yaml; d=yaml.safe_load(sys.stdin)["stringData"]; v=d.get("redis-password",""); assert len(v)==40 and v.isalnum(), "ABORT: redis-password missing/malformed"; print("redis-password OK (40 alnum), %d keys" % len(d))'
# FAILS on: a SOPS MAC mismatch (sops -d exits non-zero), a missing key, or a non-alnum
# value that would corrupt both redis:// URLs.
[ "$(yq '.spec.template.spec.containers[0].env[].name' $A/notify-push.yaml | tr '\n' ' ')" = "PORT REDIS_PASSWORD REDIS_URL NEXTCLOUD_URL " ] \
  || { echo "ABORT: notify-push env order wrong — REDIS_PASSWORD must precede REDIS_URL"; exit 1; }
grep -q -- '--requirepass "\$REDIS_PASSWORD"' $A/redis-deployment.yaml || { echo "ABORT: wrapper not in redis-deployment.yaml"; exit 1; }
yq 'select(.kind=="NetworkPolicy") | .spec.ingress[0].from | length' $A/redis-deployment.yaml | grep -qx 2 \
  || { echo "ABORT: NetworkPolicy from: does not carry the two podSelectors"; exit 1; }
V=$(yq '.spec.chart.spec.version' $A/helmrelease.yaml)
C=$(helm template nextcloud --repo https://nextcloud.github.io/helm/ --version "$V" -f <(yq '.spec.values' $A/helmrelease.yaml) | grep -c 'name: REDIS_HOST_PASSWORD')
[ "$C" -eq 3 ] || { echo "ABORT: expected 3 REDIS_HOST_PASSWORD (main, worker, cron) on chart $V — got $C"; exit 1; }
# Measured 2026-09-28 on chart 9.3.0: 0 before, 3 after.
kubeconform -summary -ignore-missing-schemas $A/notify-push.yaml $A/redis-deployment.yaml
# Measured 2026-09-28: 5 resources, Valid: 5.
```

**If the window aborts anywhere between §3.2 and the §3.3 commit**, clear the
shared index/worktree of the staged change (it contains the new Secret key and
another session's plain `git commit` would pick it up):
`git restore --staged --worktree -- $A/secrets.sops.yaml $A/redis-deployment.yaml $A/helmrelease.yaml $A/notify-push.yaml`.

**Fallback if §2 gate 3 aborted** (secrets.sops.yaml changed since the revert):
apply (a) to `helmrelease.yaml` + `redis-deployment.yaml` only, then generate a
fresh key straight into SOPS, never into a shell variable (repo cwd so
`.sops.yaml` applies):

```bash
.venv/bin/python3 -c 'import secrets,string,json;print(json.dumps("".join(secrets.choice(string.ascii_letters+string.digits) for _ in range(40))),end="")' \
  | sops set --value-stdin $A/secrets.sops.yaml '["stringData"]["redis-password"]'
```
then run (c) unchanged. (Dry-tested 2026-09-26 with sops 3.13.0: +1 key, other
ciphertexts byte-identical.)

**3.3 Commit, push, land the server side (HR still suspended), prove it:**

```bash
set -euo pipefail
cd /Users/mu/code/cberg-home-nextgen
A=kubernetes/apps/office/nextcloud/app
MSG=$(mktemp /tmp/nc-redis-hardening-msg.XXXXXX)
printf '%s\n' "feat(nextcloud-redis): requirepass + source-restricted NetworkPolicy; notify_push via REDIS_URL" "" \
  "Plan nextcloud-redis-hardening (security_ref F-069b1775). Re-lands da77a7de and" \
  "adds REDIS_PASSWORD/REDIS_URL env to nextcloud-notify-push (upstream env-over-config.php)." > "$MSG"
git commit --only $A/secrets.sops.yaml $A/redis-deployment.yaml $A/helmrelease.yaml $A/notify-push.yaml -F "$MSG"
git log -1 --format=%s        # MUST be the subject above (shared worktree message race)
git show --stat HEAD          # exactly the four files
git push origin main || { git pull --rebase --autostash origin main && git show --stat HEAD && git push origin main; } \
  || { echo "ABORT: push failed — an UNPUSHED local commit sits on shared main; do NOT reset it, resolve with the operator (nothing reached the cluster yet: KS/HR still suspended)"; exit 1; }
git rev-parse HEAD > /tmp/nc-redis-hardening.landing; cat /tmp/nc-redis-hardening.landing   # §5 reads it (agent shells keep no variables)

flux resume    kustomization nextcloud -n office
flux reconcile kustomization nextcloud -n office --with-source
kubectl -n office rollout status deploy/nextcloud-redis --timeout=180s
[ "$(kubectl -n office get hr nextcloud -o jsonpath='{.spec.suspend}')" = "true" ] || echo "WARN: HR no longer suspended"
# This reconcile also re-applies notify-push.yaml (replicas: 1 + the new env). The new
# notify-push pod starts while Nextcloud is still scaled to 0, fails its startup
# self-test against NEXTCLOUD_URL and restarts (seen 2026-09-27 08:52 in its log:
# "Self test failed: Error while communicating with nextcloud instance"). Expected;
# §3.4 restarts it explicitly once the app is back.
# §4 gates 1 and 2 NOW. Do not resume the HelmRelease until both pass.
```

**3.4 Bring the app back, then notify_push, then cron:**

```bash
set -euo pipefail
flux resume    helmrelease nextcloud -n office
flux reconcile helmrelease nextcloud -n office
[ "$(kubectl -n office get deploy nextcloud -o jsonpath='{.spec.replicas}')" = "1" ] \
  || kubectl -n office scale deploy/nextcloud --replicas=1
kubectl -n office rollout status deploy/nextcloud --timeout=300s
# §4 gates 3 and 4 NOW.

kubectl -n office rollout restart deploy/nextcloud-notify-push   # resets any CrashLoop backoff from §3.3
kubectl -n office rollout status  deploy/nextcloud-notify-push --timeout=180s
# §4 gates 5 and 6 NOW.

kubectl -n office patch cronjob nextcloud-cron -p '{"spec":{"suspend":false}}'
# §4 gates 7, 8 and 9, then:
runbooks/update-marker.sh clear nextcloud
```

## 4. Verification

Each gate names the failure it catches and the input that turns it red.

CONTENTS ASSERTION: notify_push's PARSED redis config carries the Secret's password — measured by `notify_push --dump-config` inside the new pod (count of the quoted value, never printed), compared to the before-state `password: None` (live 2026-09-28).
CONTENTS ASSERTION: the app writes through the authenticated Redis — `DBSIZE > 0` after a served `status.php`, compared to 0 on a freshly started server.
CONTENTS ASSERTION: end-to-end push delivery — `occ notify_push:self-test` "push server is receiving redis messages" (PHP publishes over the authenticated connection, notify_push must receive it over its own).
CONTROL: metric kube_deployment_status_replicas_available — gate 9 asserts `{namespace="office",deployment="nextcloud-notify-push"} == 1`.
CONTROL: metric kube_pod_container_status_restarts_total — gate 9 asserts the ABSOLUTE value `max(...{pod="<the new notify-push pod>"}) == 0` (not `increase()`, which reads 0 on restarts that precede a fresh pod's first scrape — review 2026-09-28 replayed it on the 09-27 episode: increase=0, absolute=2).

```bash
set -euo pipefail
# 1. requirepass is LIVE: an unauthenticated ping is refused.
U=$(kubectl -n office exec deploy/nextcloud-redis -- sh -c 'env -u REDISCLI_AUTH redis-cli ping 2>&1' || true)
echo "unauth ping -> $U"
echo "$U" | grep -qi NOAUTH || { echo "ABORT: unauth ping NOT refused — server is open"; exit 1; }
# CATCHES: wrapper not in effect. Failing input: today's server answers PONG.
# GREEN on 2026-09-26 with this exact manifest.
```

```bash
# 2. …and the authenticated path works (the probes depend on it).
A=$(kubectl -n office exec deploy/nextcloud-redis -- sh -c 'redis-cli ping' | tr -d '[:space:]')
[ "$A" = "PONG" ] || { echo "ABORT: authenticated ping got '$A'"; exit 1; }
# CATCHES: REDISCLI_AUTH and --requirepass reading different keys.
```

```bash
# 3. MAIN container carries the password form, and the SAME value as the Secret.
URL=$(kubectl -n office get deploy nextcloud -o jsonpath='{.spec.template.spec.containers[?(@.name=="nextcloud")].env[?(@.name=="REDIS_URL")].value}')
[ "$URL" = 'redis://:$(REDIS_HOST_PASSWORD)@$(REDIS_HOST):$(REDIS_HOST_PORT)' ] \
  || { echo "ABORT: REDIS_URL is '$URL' — existingSecret did not render"; exit 1; }
P=$(kubectl -n office exec deploy/nextcloud -c nextcloud -- sh -c 'printf %s "$REDIS_HOST_PASSWORD" | sha256sum | cut -c1-8')
S=$(kubectl -n office get secret nextcloud-config -o jsonpath='{.data.redis-password}' | base64 -d | shasum -a 256 | cut -c1-8)
[ "$S" != e3b0c442 ] || { echo "ABORT: Secret key redis-password empty/missing"; exit 1; }
[ -n "$P" ] && [ "$P" = "$S" ] || { echo "ABORT: pod ($P) != Secret ($S)"; exit 1; }
# CATCHES: a pod rolled before the Secret landed (bc4a2fbf). e3b0c442 = sha256("").
```

```bash
# 4. The app is USING the authenticated Redis.
kubectl -n office exec deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ status" | grep -qi 'installed: true' \
  || { echo "ABORT: occ status not installed:true"; exit 1; }
H=$(kubectl -n office get httproute nextcloud -o jsonpath='{.spec.hostnames[0]}')
[ -n "$H" ] || { echo "ABORT: no HTTPRoute hostname"; exit 1; }
curl -s -o /dev/null -w '%{http_code}\n' --max-time 15 "https://$H/status.php" | grep -q '^200$' || { echo "ABORT: status.php not 200"; exit 1; }
K=$(kubectl -n office exec deploy/nextcloud-redis -- sh -c 'redis-cli DBSIZE' | awk '{print $NF}')
echo "keys=$K"; [ "$K" -gt 0 ] || { echo "ABORT: 0 keys — app not writing to this Redis"; exit 1; }
# CATCHES: an app up but not using the cache/locks. The server was restarted in §3.3
# with the app at 0, so it starts empty; >0 can only come from the authenticated app.
```

```bash
# 5. notify_push PARSED the password from its env (the 09-26 failure, now as a gate).
R=$(kubectl -n office exec deploy/nextcloud-notify-push -- sh -c '
  [ -n "$REDIS_PASSWORD" ] || { echo "NOENV"; exit 0; }
  D=$(/var/www/html/custom_apps/notify_push/bin/x86_64/notify_push --dump-config /var/www/html/config/config.php 2>&1)
  printf "pw=%s host=%s none=%s\n" \
    "$(printf "%s\n" "$D" | grep -cF "\"$REDIS_PASSWORD\",")" \
    "$(printf "%s\n" "$D" | grep -cF "host: \"nextcloud-redis\"")" \
    "$(printf "%s\n" "$D" | grep -A12 "redis:" | grep -c "password. None")"')
echo "dump-config: $R"
[ "$R" = "pw=1 host=1 none=0" ] || { echo "ABORT: notify_push does not carry the password ($R)"; exit 1; }
# Output is COUNTS only — the dump holds the DB and Redis passwords and never leaves the pod.
# FAILS on: env missing (NOENV), REDIS_URL not honoured (pw=0, none=1 — exactly today's
# live dump: `password: None`), wrong host (host=0). The multi-line Debug format
# (`password: Some(\n "…",\n)`) was measured on the live binary 2026-09-28, which is why
# the quoted value is matched with its trailing comma rather than on the `Some(` line.
# DRY-TESTED 2026-09-28 against the live pod, env injected into the exec only:
#   no env                                  -> NOENV                    (ABORT)
#   REDIS_PASSWORD set, no REDIS_URL        -> pw=0 host=1 none=1       (ABORT)
#   REDIS_PASSWORD + REDIS_URL (§3.2 shape) -> pw=1 host=1 none=0       (PASS)
```

```bash
# 6. End-to-end: PHP publishes, notify_push receives, both over authenticated Redis.
rc=0; kubectl -n office exec deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ notify_push:self-test" > /tmp/np-post.txt 2>&1 || rc=$?
cat /tmp/np-post.txt
[ "$rc" -eq 0 ] && grep -qiF 'push server is receiving redis messages' /tmp/np-post.txt && ! grep -qiF 'is not receiving' /tmp/np-post.txt \
  || { echo "ABORT (rc=$rc): notify_push not healthy after the change"; exit 1; }
# Failing input (upstream SelfTest.php): "🗴 push server is not receiving redis messages"
# + non-zero exit. This gate went red on 2026-08-19 behind a green HelmRelease.
```

```bash
# 7. Cron pods authenticate (env from the chart).
J=nextcloud-cron-verify-$(date +%H%M)
kubectl -n office create job --from=cronjob/nextcloud-cron $J
kubectl -n office wait --for=condition=complete job/$J --timeout=300s \
  || { echo "ABORT: verify cron job did not complete"; kubectl -n office logs job/$J | tail -20; exit 1; }
kubectl -n office delete job $J
```

```bash
# 8. NetworkPolicy: a NON-consumer cannot reach 6379; a consumer-labelled pod can.
NEG=$(kubectl -n office run np-neg --rm -i --restart=Never --image=busybox:1.38.0 --quiet -- \
        sh -c 'nc -z -w 3 nextcloud-redis 6379; echo rc=$?' 2>/dev/null | tail -1)
POS=$(kubectl -n office run np-pos --rm -i --restart=Never --image=busybox:1.38.0 --quiet \
        --labels=app.kubernetes.io/instance=nextcloud,app.kubernetes.io/component=app -- \
        sh -c 'nc -z -w 3 nextcloud-redis 6379; echo rc=$?' 2>/dev/null | tail -1)
echo "neg=$NEG pos=$POS"
[ "$NEG" = "rc=1" ] || { echo "ABORT: unlabelled pod reached Redis — from: not enforced"; exit 1; }
[ "$POS" = "rc=0" ] || { echo "ABORT: consumer-labelled pod blocked — selector too narrow"; exit 1; }
# CATCHES both directions. busybox:1.38.0 = the chart's wait-for-redis image, on the nodes.
```

```bash
# 9. notify-push stays up and has NOT restarted (run ≥10 min after §3.4).
PODS=$(kubectl -n office get pod -l app=nextcloud-notify-push -o 'jsonpath={range .items[*]}{.metadata.name}{" "}{.status.containerStatuses[0].restartCount}{"\n"}{end}')
echo "$PODS"
[ "$(printf '%s\n' "$PODS" | grep -c .)" -eq 1 ] || { echo "ABORT: expected exactly one notify-push pod"; exit 1; }
NP=$(printf '%s\n' "$PODS" | awk '{print $1}'); RC=$(printf '%s\n' "$PODS" | awk '{print $2}')
[ "$RC" = "0" ] || { echo "ABORT: $NP restartCount=$RC — auth/connect loop"; exit 1; }
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
q() { curl -s --get http://localhost:9090/api/v1/query --data-urlencode "query=$1" \
      | .venv/bin/python3 -c 'import sys,json; r=json.load(sys.stdin)["data"]["result"]; print(r[0]["value"][1] if r else "EMPTY")'; }
AV=$(q 'kube_deployment_status_replicas_available{namespace="office",deployment="nextcloud-notify-push"}')
RS=$(q "max(kube_pod_container_status_restarts_total{namespace=\"office\",pod=\"$NP\"})")
kill $PF 2>/dev/null
echo "available=$AV restarts(abs)=$RS"
[ "$AV" = "1" ] || { echo "ABORT: notify-push available=$AV"; exit 1; }
[ "$RS" = "0" ] || { echo "ABORT: notify-push restarts=$RS (EMPTY = not scraped yet: wait 1 min and re-run; never a pass)"; exit 1; }
# KNOWN-BAD DEMONSTRATION (review 2026-09-28): the same absolute read on pod
# nextcloud-notify-push-6b7579cf96-vjwwz returns 2 (its 09-27 08:49-08:51 startup
# self-test restarts), where the old increase()[10m..3d] form read 0.
# notify-push has no probes, so available=1 only means "running"; gate 6 is the real signal.
```

Nightly Longhorn backups are unaffected (no PVC written).

## 5. Rollback

Trigger: `nextcloud-redis` rollout not complete / CrashLoop in §3.3, or gate 1/2 red after §3.3 → steps 1-3 then resume the HR; any of gates
3-9 red after §3.4 → the full sequence. Sessions drop a second time; say so.

1. Quiesce again. If the Redis server is SERVING with working auth (gate 2 green),
   use §3.1 including the CLIENT LIST proof. If it is NOT (wrapper CrashLoop,
   §3.3 `rollout status` timed out, or gate 2 red so CLIENT LIST errors), the
   CLIENT LIST proof cannot run — prove the quiesce by replica state instead:
   ```bash
   flux suspend kustomization nextcloud -n office                      # else the next reconcile re-scales notify-push to 1
   kubectl -n office scale deploy/nextcloud-notify-push --replicas=0   # the §3.3 reconcile set it back to 1
   [ "$(kubectl -n office get deploy nextcloud -o jsonpath='{.spec.replicas}')" = "0" ] || kubectl -n office scale deploy/nextcloud --replicas=0
   kubectl -n office wait --for=delete pod -l app.kubernetes.io/component=app,app.kubernetes.io/instance=nextcloud --timeout=180s
   kubectl -n office wait --for=delete pod -l app=nextcloud-notify-push --timeout=120s
   [ "$(kubectl -n office get cronjob nextcloud-cron -o jsonpath='{.spec.suspend}')" = "true" ] || { echo "ABORT: cron not suspended"; exit 1; }
   ```
2. Revert the landing commit (shared worktree: `--no-commit` + `--only`):
   ```bash
   cd /Users/mu/code/cberg-home-nextgen && A=kubernetes/apps/office/nextcloud/app
   LANDING=$(cat /tmp/nc-redis-hardening.landing); [ -n "$LANDING" ] || { echo "ABORT: no landing sha recorded"; exit 1; }
   git revert --no-edit --no-commit "$LANDING"      # the sha recorded in §3.3
   MSG=$(mktemp /tmp/nc-redis-rollback-msg.XXXXXX); printf 'Revert nextcloud-redis hardening (plan nextcloud-redis-hardening §5)\n' > "$MSG"
   git commit --only $A/secrets.sops.yaml $A/redis-deployment.yaml $A/helmrelease.yaml $A/notify-push.yaml -F "$MSG"
   git log -1 --format=%s; git show --stat HEAD      # yours; exactly the four files
   git push origin main
   ```
   Restores the unauthenticated command, the `from:`-less policy, the
   password-less HelmRelease values and notify-push's two-var env in one revision.
3. `flux resume kustomization nextcloud -n office && flux reconcile kustomization nextcloud -n office --with-source`;
   `kubectl -n office rollout status deploy/nextcloud-redis` — §2 gate 1 must now
   read PONG unauthenticated (the rollback's success condition).
4. `flux resume helmrelease nextcloud -n office && flux reconcile helmrelease nextcloud -n office`;
   scale `deploy/nextcloud` to 1 if needed; `occ status`.
5. `kubectl -n office rollout restart deploy/nextcloud-notify-push`; then §2 gate 4's
   self-test form must be clean (it reads config.php again, which was never
   modified — `password: None` against an open server, the 2026-09-28 state).
6. Un-suspend the CronJob; `runbooks/update-marker.sh clear nextcloud`.

Nothing on any PVC is changed by this plan, so there is nothing else to restore
(the 09-26 revision's config.php backup/un-set steps are gone with its config.php write).

## 6. Interference notes

- **`nextcloud-fleet-35.0.1`** (draft) edits the same `helmrelease.yaml` and
  `notify-push.yaml` and rolls the same Deployments. Whichever lands second must
  re-run §2 gate 3 / its own pre-flight; §3.2's notify-push hunk does not overlap
  the image line.
- **`redis-fleet-8.10.2`** / finding `F-3fcdca7b` (image patch on the same
  `redis-deployment.yaml`, safe lane, may land at Step 0 of the same window):
  §3.2(a) is a 3-way apply proven to merge cleanly over that bump and keep it.
  Do not run both plans in one window — two Recreate rolls of the session store.
- **`flux-oci-chart-sources`** (stage 5) switches the nextcloud HelmRelease to
  an OCI `chartRef`; §3.2(c)'s render gate reads `.spec.chart.spec.version`. If
  it lands first, re-derive the render command from the chartRef before running.
- Adjacent, not conflicts: `helm-drift-detection` (driftDetection on this HR),
  `chart-patches-coredns-reloader-blackbox` (Reloader rolls whiteboard here).
- **`flux-reconciler-impersonation`** changes how Flux applies `office`; do not
  put both in one window — a failed apply in §3.3 would be ambiguous.
- **Attended only** (`autonomy_override: human-gated`). Every logged-in user is
  logged out; gate 8 creates two throwaway pods in `office`.
- **Password exposure surface:** notify-push's container env (readable in that
  container only) and redis-server's argv, the same as the two sibling Redis
  deployments; the pod spec shows only `$(REDIS_PASSWORD)`. The password is NOT
  written to `config.php`. The Secret key restored from `da77a7de` was live for
  ~6 min on 2026-09-26 and never left SOPS/etcd; if the operator prefers a fresh
  value, use the §3.2 fallback generator instead of (a) for the Secret.
- **After this lands:** `F-069b1775` is already `resolved` (plan authorship,
  `aab921ba`); record the landing commit on it via `policy-cli finding`, do not
  re-open it. The old notify-push.yaml note about `zz_touch` + config.php for
  a HOST change remains valid for hosts; for the password it is superseded by
  the REDIS_URL env above (REDIS_URL now also pins the host, so a future host
  rename must edit REDIS_URL too — hence "keep in lockstep" in the comment).
- **Repo correction (not planned around):** the old plan's §3.7 idea and the
  `notify-push.yaml` comment both treated config.php as notify_push's only redis
  source; upstream v1.4.1 gives env precedence. The 09-26 status note's untested
  `zz_touch` idea was NOT pursued: whether a forced rewrite would persist an
  overlay value into config.php is unmeasured, and it would put a second copy of
  the password on the PVC plus an in-pod write that git cannot revert. The env
  path needs neither.
