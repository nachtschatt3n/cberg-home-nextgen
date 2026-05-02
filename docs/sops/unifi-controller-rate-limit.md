# SOP: UniFi Controller Login Rate Limit (unpoller)

> Description: Operate, diagnose, and recover the unpoller → UniFi controller integration when the controller's login endpoint rate-limit (HTTP 429) interrupts metric collection. Covers the relationship between unpoller polling cadence, the controller's `/api/auth/login` throttle, and the SSH workflow on the gateway.
> Version: `2026.05.03`
> Last Updated: `2026-05-03`
> Owner: `homelab-ops`

---

## 1) Description

unpoller (chart `unpoller@2.1.0`, image `ghcr.io/unpoller/unpoller:v2.39.0`) scrapes the UniFi controller and emits metrics to Prometheus and InfluxDB. Two independent exporters share the same controller credentials. Each exporter performs its own login on every polling cycle, so the effective login-attempt rate is `2 × (1 / interval)`.

The UniFi gateway (UDM/UDM-Pro/Dream Machine line) enforces a per-IP rate limit on `POST /api/auth/login` inside the `unifi-core` binary. The threshold is not user-configurable through any settings file or env var — it is part of the binary. When the threshold is crossed the controller returns HTTP `429 Too Many Requests`, which sends unpoller into a self-perpetuating retry+re-auth storm that prolongs the outage.

This SOP describes the chosen polling interval, how to reset the controller-side counter, how to triage a 429 event, and how to harden the integration over time.

- Scope: `monitoring/unpoller`, the UniFi gateway login endpoint, related Grafana dashboards
- Prerequisites: kubectl + flux + sops via mise; root SSH to the gateway (creds stored locally — see §10)
- Out of scope: `ulp-go` identity service tuning (different process, ports 9080/9443; unrelated to this issue)

---

## 2) Overview

| Setting | Value |
|---------|-------|
| Namespace | `monitoring` |
| Source of truth | `kubernetes/apps/monitoring/unpoller/app/secret.sops.yaml` |
| HelmRelease | `kubernetes/apps/monitoring/unpoller/app/helmrelease.yaml` |
| Polling interval (current) | `30s` (Prometheus + InfluxDB exporters) |
| Backoff interval (after 429) | `2m` |
| Effective login rate at 30s | ~4 logins/min per gateway IP |
| Effective login rate at 2m | ~1 login/min per gateway IP |
| Controller endpoint hit | `POST /api/auth/login` on gateway port 443 (proxied to `unifi-core` via unix socket) |
| Rate-limit enforcer | `unifi-core` binary on gateway (not nginx, not `ulp-go`) |
| Reset trigger (observed) | gateway OS reboot; gateway firmware update (which reboots) |

---

## 3) Blueprints

- Source of truth file: `kubernetes/apps/monitoring/unpoller/app/secret.sops.yaml`
- Mounted by HelmRelease via `valuesFrom` → `targetPath: upConfig` → chart-rendered Secret `unpoller`
- Pod consumes config from `/etc/unpoller/up.conf`

```toml
# Pattern for the upConfig field (encrypted in repo, never committed in plaintext)
[unifi]
dynamic = false

[[unifi.controller]]
url = "https://<gateway-ip>"
user = "<service-account>"
pass = "<password>"
sites = ["all"]
# ... save_* flags ...
verify_ssl = false

[prometheus]
http_listen = "0.0.0.0:9130"
namespace = "unpoller"
interval = "30s"     # ← tune here
disable = false
buffer = 50

[influxdb]
url = "http://influxdb-influxdb2.databases.svc.cluster.local:80"
# ... credentials ...
interval = "30s"     # ← keep equal to [prometheus].interval
disable = false
```

Both `[prometheus].interval` and `[influxdb].interval` must be changed together — they drive independent exporters that each authenticate on their own schedule.

---

## 4) Operational Instructions

### 4.1 Change the polling interval (primary tuning lever)

```bash
# 1. Decrypt locally (do NOT commit plaintext)
mise exec -- sops -d kubernetes/apps/monitoring/unpoller/app/secret.sops.yaml > /tmp/unpoller-secret.yaml

# 2. Edit /tmp/unpoller-secret.yaml — change BOTH `interval = "..."` lines

# 3. Copy back into the repo path with .sops.yaml extension and encrypt in place
cp /tmp/unpoller-secret.yaml kubernetes/apps/monitoring/unpoller/app/secret-new.sops.yaml
mise exec -- sops -e -i kubernetes/apps/monitoring/unpoller/app/secret-new.sops.yaml
mv kubernetes/apps/monitoring/unpoller/app/secret-new.sops.yaml \
   kubernetes/apps/monitoring/unpoller/app/secret.sops.yaml
rm -f /tmp/unpoller-secret.yaml

# 4. Verify encryption header present and plaintext round-trip works
grep '^sops:' kubernetes/apps/monitoring/unpoller/app/secret.sops.yaml | head -1
mise exec -- sops -d kubernetes/apps/monitoring/unpoller/app/secret.sops.yaml | grep interval

# 5. Commit + push
git add kubernetes/apps/monitoring/unpoller/app/secret.sops.yaml
git commit -m "chore(unpoller): set poll interval to <new value>"
git push origin main
```

Flux reconciles the kustomization, which updates the `unpoller-credentials` Secret. The HelmRelease's `valuesFrom` watches that Secret and triggers a Helm upgrade automatically. If the chart values do not change (only the referenced Secret content), the pod will pick up the new mounted file but unpoller reads its config only at startup — force a rollout:

```bash
mise exec -- kubectl rollout restart deployment/unpoller -n monitoring
mise exec -- kubectl rollout status  deployment/unpoller -n monitoring --timeout=60s
```

### 4.2 Set up SSH key auth on the gateway (recommended hardening)

Password-based root SSH should be replaced with key auth. From the workstation:

```bash
# Use the locally stored credential (see §10) for the one-time copy
source ~/.config/cberg-secrets/dmp-cberg.env
ssh-copy-id -i ~/.ssh/id_ed25519.pub root@$DMP_CBERG_HOST
# Provide $DMP_CBERG_ROOT_PW when prompted

# Add a host alias
cat >> ~/.ssh/config <<'EOF'
Host dmp-cberg
  HostName 192.168.55.1
  User root
  IdentityFile ~/.ssh/id_ed25519
  StrictHostKeyChecking accept-new
EOF
chmod 600 ~/.ssh/config

# Verify
ssh dmp-cberg "uptime"
```

After this works, the password in `~/.config/cberg-secrets/dmp-cberg.env` becomes a break-glass-only secret.

### 4.3 Recover from a sustained 429 storm

```bash
# 1. Stop the bleeding — temporarily widen the polling interval to 2m
#    (follow §4.1 with interval = "2m")

# 2. Reset the controller-side counter — the only known reset is a gateway reboot
ssh dmp-cberg "reboot"

# 3. After ~3 minutes, verify unpoller is collecting again
mise exec -- kubectl logs -n monitoring -l app.kubernetes.io/name=unpoller --tail=20 \
  | grep -E "Measurements Exported|429|Re-authenticating"

# 4. Once stable for >30 minutes, optionally restore interval = "30s" via §4.1
```

---

## 5) Examples

### Example A: Restore 30s polling after a known firmware update

The gateway reboots itself after a controller firmware update, which clears the login-attempt counter. This is the safe window to tighten the interval back to 30s.

```bash
# After the gateway is back up and the controller HelmRelease in monitoring is Ready
mise exec -- flux get helmreleases -A | grep unpoller   # expect READY=True

# Edit secret per §4.1, set both intervals to "30s", commit, push, restart pod
# Watch for ~10 minutes that no 429s appear in the gateway access log (see §9)
```

### Example B: Apply emergency backoff during peak ingest

If a transient burst is causing 429s during the day, push interval to 2m without rebooting the gateway. Polls will resume succeeding within one cycle once the per-IP throttle window slides.

```bash
# Edit secret per §4.1 with interval = "2m", commit, push, rollout restart
mise exec -- kubectl logs -n monitoring -l app.kubernetes.io/name=unpoller --tail=5 \
  | grep "interval:"
# Expect: "Poller->InfluxDB started, version: 2, interval: 2m0s, ..."
```

---

## 6) Verification Tests

### Test 1: New interval is live

```bash
mise exec -- kubectl logs -n monitoring -l app.kubernetes.io/name=unpoller --tail=20 \
  | grep "Poller->InfluxDB started"
```

Expected:
- A line containing the new interval value, e.g. `interval: 30s` or `interval: 2m0s`

If failed:
- Pod did not restart. Run `kubectl rollout restart deployment/unpoller -n monitoring`.

### Test 2: Successful exports, zero 429s

```bash
mise exec -- kubectl logs -n monitoring -l app.kubernetes.io/name=unpoller --since=5m \
  | grep -cE "UniFi Measurements Exported|429"
```

Expected:
- One or more `UniFi Measurements Exported` lines per polling cycle
- Zero lines containing `429`

If failed:
- Check the gateway access log per §8 to confirm the 429 source endpoint
- Apply emergency backoff per Example B

### Test 3: Prometheus is scraping unpoller

```bash
mise exec -- kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 >/dev/null 2>&1 &
sleep 3
curl -s 'http://localhost:9090/api/v1/query?query=unpoller_unifi_clients_total' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('result count:', len(d['data']['result']))"
killall kubectl
```

Expected:
- `result count:` greater than 0

If failed:
- ServiceMonitor or PodMonitor target may be down. Check `kube-prometheus-stack-prometheus` UI → Targets → search `unpoller`.

---

## 7) Troubleshooting

| Symptom | Likely Cause | First Fix |
|---------|--------------|-----------|
| Repeated `429 Too Many Requests` in unpoller logs | Login-attempt rate exceeded controller threshold | Set `interval = "2m"` (§4.1), then reboot gateway (§4.3) |
| `Re-authenticating` lines every few seconds | Reactive retry to 429s, NOT a session timeout | Same as above — root cause is the 429 |
| `interval:` log line still shows old value after edit | Pod not restarted | `kubectl rollout restart deployment/unpoller -n monitoring` |
| Helm upgrade not triggered after secret change | `valuesFrom` watcher lag | `flux reconcile helmrelease -n monitoring unpoller --with-source` |
| 429s persist after 2m + reboot | Different IP source (e.g. another homelab tool sharing the same service account) | Audit `grep ' 429 ' /data/unifi-core/logs/nginx-access.log` per §8 |
| `Permission denied (publickey,keyboard-interactive)` on SSH | Password auth disabled or wrong creds | Use creds from `~/.config/cberg-secrets/dmp-cberg.env`; if disabled, console access required |

---

## 8) Diagnose Examples

### Diagnose Example 1: Confirm 429 source is the login endpoint

```bash
ssh dmp-cberg "grep ' 429 ' /data/unifi-core/logs/nginx-access.log | tail -10"
```

Expected:
- Lines like `... 429 "POST /api/auth/login HTTP/1.1" ... ip=<unpoller-pod-host-ip> user="-"`
- The `user="-"` confirms the request never reached an authenticated session

If unclear:
- If 429s are on data endpoints (`/proxy/network/api/...`) instead of `/api/auth/login`, the throttle is different (likely a different rule set) — escalate.

### Diagnose Example 2: Identify which exporter is causing the storm

```bash
mise exec -- kubectl logs -n monitoring -l app.kubernetes.io/name=unpoller --since=5m \
  | grep -E "Re-authenticating|Poller->" | head -20
```

Expected:
- Two `Re-authenticating` lines within ~4 seconds of each other → both Prometheus and InfluxDB are auth-storming together
- Only one within a polling cycle → only one exporter is the source

If unclear:
- Temporarily set `[influxdb].disable = true` in the secret to isolate Prometheus alone

### Diagnose Example 3: Verify the controller-side rate limiter location

```bash
# 1. Confirm only nginx is on 443, but the API auth target is the unifi-core unix socket
ssh dmp-cberg "netstat -tlnp 2>/dev/null | grep -E ':(443|8443|9080|9443)\s'"

# 2. Confirm /api/auth/login is proxied to uos_auth_backend (unifi-core)
ssh dmp-cberg "grep -A 2 'uos_auth_backend' /data/unifi-core/config/http/upstream-uos.conf"
```

Expected:
- Port 443 owned by `nginx`, port 8443 owned by `java` (network controller — unrelated to login throttle)
- Port 9080/9443 owned by `ulp-go-app` (identity service — unrelated to login throttle)
- `uos_auth_backend` upstream points at a unix socket served by `unifi-core` — this is the throttle enforcer

### Diagnose Example 4: Discover the auth-block routing chain from scratch (after a firmware update)

Use this when a controller firmware update has shipped and Diagnose Example 3 paths may have moved. The chain to follow is **listening port → nginx server block → location for `/api/...` → upstream → unix socket → process**.

```bash
# Step A — Which processes own the externally-reachable ports?
#   This tells you which binary handles each port without guessing.
ssh dmp-cberg "netstat -tlnp 2>/dev/null | grep -E 'LISTEN' | awk '{print \$4, \$7}' | sort -u"
# Expect (paths may differ across firmware):
#   0.0.0.0:443     nginx: master
#   :::8443         java          ← UniFi network controller (NOT the auth throttle)
#   :::9080/9443    ulp-go-app    ← identity service (NOT the auth throttle)
#   127.0.0.1:8081  java          ← controller's internal API (proxied by nginx)

# Step B — Where is nginx's active config and what does it include?
#   Watch for ".disabled" suffixes — those files are NOT loaded.
ssh dmp-cberg "ls /etc/nginx/ /etc/nginx/conf.d/ 2>/dev/null"
ssh dmp-cberg "grep -E 'include' /etc/nginx/nginx.conf | grep -v '^\s*#'"
# Expect: include lines pointing at /data/unifi-core/config/http/site-*.conf
#         and /data/unifi-core/config/http/upstream-*.conf — that directory is
#         the real source of routing truth.

# Step C — Which server block + location handles /api/auth/login ?
#   The login endpoint usually falls under a generic "/api/" location.
ssh dmp-cberg "grep -rEn 'location /api' /usr/share/unifi-core/http/ /data/unifi-core/config/http/ 2>/dev/null"
ssh dmp-cberg "sed -n '/location \\/api\\/ {/,/^}/p' /usr/share/unifi-core/http/shared-post-setup-server.conf"
# Expect: a `proxy_pass http://uos_api_backend/api/;` line, plus an
#         `include .../auth.conf;` line that wires authentication.

# Step D — What auth subrequest fires per /api/* call?
ssh dmp-cberg "grep -E 'auth_request' /usr/share/unifi-core/http/auth.conf"
# Expect: `auth_request /internal/auth/public-api;`

# Step E — Where does that internal auth subrequest go?
ssh dmp-cberg "grep -A 2 'location /internal/auth/public-api' /usr/share/unifi-core/http/shared-post-setup-server.conf"
# Expect: `proxy_pass http://uos_auth_backend/public-api;`

# Step F — What backend is uos_auth_backend?
ssh dmp-cberg "cat /data/unifi-core/config/http/upstream-uos.conf"
# Expect: `server unix:/data/unifi-core/config/http/uos-auth.sock;`

# Step G — Which process owns that socket? (this is the throttle enforcer)
ssh dmp-cberg "ls -la /data/unifi-core/config/http/uos-*.sock 2>/dev/null"
ssh dmp-cberg "ps aux | grep -E 'unifi-core' | grep -v grep"
# Expect: a single `unifi-core` process owns those sockets — IT is the binary
#         that decides whether a given IP gets a 200 or a 429 on /api/auth/login.

# Step H — Confirm the throttle is NOT in nginx (no rate-limit zones anywhere)
ssh dmp-cberg "grep -rEn 'limit_req|limit_conn' /etc/nginx/ /usr/share/unifi-core/http/ /data/unifi-core/config/http/ 2>/dev/null"
# Expect: empty. If non-empty, an additional nginx-side throttle exists
#         and tuning interval alone may not be sufficient.

# Step I — Confirm the throttle is NOT in iptables (no hashlimit/recent rules)
ssh dmp-cberg "iptables -L -n 2>/dev/null | grep -iE 'hashlimit|recent|hashlimit'"
# Expect: empty. Existing 'limit:' lines only apply to logging suppression.

# Step J — Look for any user-tunable setting before assuming it's hardcoded
ssh dmp-cberg "find /etc/unifi-core /usr/lib/unifi-core /data/unifi-core/config -maxdepth 2 -type f \( -name '*.yaml' -o -name '*.props' -o -name '*.conf' -o -name '*.json' \) 2>/dev/null"
ssh dmp-cberg "grep -rEi 'rate.?limit|throttle|login.?attempt|max.?login' /data/unifi-core/config/ /usr/lib/unifi-core/ 2>/dev/null | head -10"
# Expect (current firmware): no matches. The threshold is baked into the
# unifi-core binary. If matches appear on a future firmware, document the
# new tunable in this SOP and §2 Overview.
```

Expected (overall):
- The chain `nginx :443 → location /api/ → auth_request /internal/auth/public-api → uos_auth_backend → unix:.../uos-auth.sock → unifi-core process` confirms that `unifi-core` is the only enforcer
- Steps H, I, J prove no other layer (nginx, iptables, settings file) participates in the throttle decision

If unclear:
- If Step C points at a different server block (e.g. `site-direct-connect.conf`), repeat Steps D–F using that file instead — Ubiquiti occasionally restructures the per-context server blocks across major firmware releases.
- If Step G shows a process other than `unifi-core` owning the socket, that new process becomes the enforcer; update §2 Overview accordingly.

If unclear:
- `ps aux | grep unifi-core` should show a `unifi-core` process with the socket files in its open file table.

---

## 9) Health Check

```bash
# Once per shift / after any unpoller or gateway change

# A. Pod healthy and exporting
mise exec -- kubectl get pods -n monitoring -l app.kubernetes.io/name=unpoller
mise exec -- kubectl logs  -n monitoring -l app.kubernetes.io/name=unpoller --since=10m \
  | grep -cE "UniFi Measurements Exported"
# Expect: pod 1/1 Running with restartCount stable; export count > 0

# B. Zero recent 429s on the controller side (last ~50 entries)
ssh dmp-cberg "grep ' 429 ' /data/unifi-core/logs/nginx-access.log | tail -5"
# Expect: empty or only entries from before the last gateway reboot

# C. Flux healthy
mise exec -- flux get helmreleases -n monitoring unpoller
# Expect: READY=True
```

Expected:
- All three checks green; no 429 entries newer than the last gateway boot time

---

## 10) Security Check

```bash
# A. No plaintext credentials in the repo
grep -rE 'pass[[:space:]]*=[[:space:]]*"[^"]+"' kubernetes/apps/monitoring/unpoller/ \
  --include='*.yaml' | grep -v '\.sops\.yaml:'
# Expect: empty output

# B. Secret file is encrypted
grep -c '^sops:' kubernetes/apps/monitoring/unpoller/app/secret.sops.yaml
# Expect: 1

# C. Local credential file mode 600, owner-only
stat -f '%A %u %N' ~/.config/cberg-secrets/dmp-cberg.env
# Expect: 600 <your uid> <path>

# D. Local credential directory not present in the repo
git -C ~/code/cberg-home-nextgen ls-files | grep -i cberg-secrets
# Expect: empty output

# E. No SSH credentials, IP-camera RTSP URLs, or controller passwords printed in any committed log
git -C ~/code/cberg-home-nextgen log --all -p -- runbooks/ | grep -iE 'pass[[:space:]]*=|root@|ssh-copy-id'
# Expect: empty (or only references to this SOP / template strings)
```

Expected:
- No plaintext secrets in the repo
- Secret file properly SOPS-encrypted
- Local credential file owner-readable only
- Local credential file path is unknown to the repo

---

## 11) Rollback Plan

```bash
# Roll back the most recent secret change
git revert <commit-sha> --no-edit
git push origin main

# Force HelmRelease + pod refresh so the prior interval takes effect immediately
mise exec -- flux reconcile helmrelease -n monitoring unpoller --with-source
mise exec -- kubectl rollout restart deployment/unpoller -n monitoring

# Verify
mise exec -- kubectl logs -n monitoring -l app.kubernetes.io/name=unpoller --tail=10 \
  | grep "Poller->InfluxDB started"
```

If the rollback itself triggers a 429 storm, immediately apply Example B (set interval to `2m`) and reboot the gateway.

---

## 12) References

- HelmRelease: `kubernetes/apps/monitoring/unpoller/app/helmrelease.yaml`
- Encrypted secret: `kubernetes/apps/monitoring/unpoller/app/secret.sops.yaml`
- ServiceMonitor: `kubernetes/apps/monitoring/unpoller/app/servicemonitor.yaml`
- PrometheusRule: `kubernetes/apps/monitoring/unpoller/app/prometheusrule.yaml`
- SOPS workflow: `docs/sops/sops-encryption.md`
- Local credential file: `~/.config/cberg-secrets/dmp-cberg.env` (NOT in repo)
- Upstream unpoller docs: <https://unpoller.com/>

---

## Version History

- `2026.05.03`: Initial SOP. Documents the `unifi-core` login rate-limit root cause, the `interval` tuning workflow, the gateway-reboot reset path, and the local credential storage convention.
