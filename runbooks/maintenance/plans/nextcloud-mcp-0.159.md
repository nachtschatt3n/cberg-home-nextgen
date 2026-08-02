---
plan_id: nextcloud-mcp-0.159
component: nextcloud-mcp
pr: null                            # no open Renovate PR for this bump — bump the image tag by hand
kind: image
current: "0.140.4"
target: "0.159.1"
update_type: minor                  # 0.140→0.159 is a 0.x minor bump by semver, but spans ~19 minors / 7 breaking releases
risk: medium
est_duration_min: 25
needs_reboot: false
touches:
  namespaces: [office]
  resources:
    - helmrelease/nextcloud-mcp
    - deployment/nextcloud-mcp       # single replica, stateless (envFrom secret only)
    - service/nextcloud-mcp          # port 8000
    - ingress/nextcloud-mcp          # className "internal" — backend swap only, no controller restart
  shared: []                         # no shared DB/storage/cert-manager/cni; ingress class not perturbed (new backend pod only)
depends_on: []
conflicts_with: []                   # none pending; DO NOT co-schedule with any openclaw restart/upgrade (ai ns consumes this MCP endpoint — see Interference)
status: draft
window: "tue-early:2026-08-18"       # the window AFTER nextcloud (thu 08-13), so it's
                                     # tested against the already-upgraded + verified
                                     # nextcloud, but NOT sharing its occ-migration
                                     # window. Do NOT co-schedule any openclaw restart
                                     # (ai ns consumes this MCP endpoint).
auto_execute: false
sops_refs:
  - docs/sops/application-update.md
generated: "2026-08-02"
---

# nextcloud-mcp 0.140.4 → 0.159.1

## 1) Summary & why held

Image bump of the Nextcloud MCP bridge `ghcr.io/cbcoutinho/nextcloud-mcp-server`
`0.140.4 → 0.159.1` (namespace `office`). This server is the MCP bridge that lets
assistants reach Nextcloud (files/calendar/contacts/mail/deck). It has **two live
consumers**:
1. **Claude Desktop** on the Mac mini — external, via ingress `https://nextcloud-mcp.${SECRET_DOMAIN}/mcp`.
2. **OpenClaw** in-cluster (`ai` namespace) — via mcporter (`NEXTCLOUD_MCP_URL`);
   the "read-only file + supported-Nextcloud-app surface" the family briefing uses
   (paperless / nextcloud-mail / calendar / nc-health).

**Why the auto-updater held it (G3 breaking-change gate + span size).** Renovate
labels `0.140→0.159` a "minor", but the span crosses **seven separate `BREAKING
CHANGE` releases** and the latest one (0.159.0) carries a container-runtime
breaking banner — G3 trips on the release-notes scan and holds it for review.

**Investigation result — the two scariest breaking changes DO NOT apply to this
deployment.** This is the crux of the medium (not high) rating:

- **0.148.0 "OAuth scope enforcement now actually applies to tool calls"** — this
  path is OAuth-only ("under OAuth, a request arriving without a verified token is
  denied"). This deployment runs **`MCP_DEPLOYMENT_MODE: single_user_basic`**
  (Nextcloud app-password / HTTP BasicAuth, confirmed in
  `secret.sops.yaml`), not OAuth. The OAuth token-verification change is N/A.
  (Residual: the same release also hardened app-password *scope* checks — verify a
  read tool-call still succeeds post-bump; see Verification.)
- **0.159.0 "container now runs as uid 1000 … /app/.oauth mount is gone … a stale
  volume fails to start rather than degrading"** — the failure mode is a
  **persisted volume** with root-owned `tokens.db` that the new uid-1000 process
  can't chmod. This pod mounts **no volume at all** (confirmed: only the
  serviceaccount token; no PVC, no `/app/.oauth`, no `runAsUser` override). It
  starts fresh with nothing persisted, so the uid-1000 switch is a no-op here.

**Breaking changes that DO touch this deployment's tool contract (the real
watch-items — behavioral, not infra):**

- **0.151.0** — `nc_webdav_read_file` returns **text/markdown, not base64**, and
  drops the `force_processor` arg (replaced by `parse_document`); `ENABLE_DOCUMENT_PROCESSING`
  removed. Quote: *"nc_webdav_read_file no longer accepts `force_processor`; it is
  replaced by `parse_document` … ENABLE_DOCUMENT_PROCESSING is removed."* Also
  adds *"configurable transport security and CORS origins"* — verify the ingress
  path still serves without new CORS/transport env being required.
- **0.145.0** — `nc_webdav_write_file` is now **fail-closed**: *"Omitting if_match
  now creates a file and fails if it already exists; to overwrite, pass the etag …
  or if_match=\"\*\"."* OpenClaw uses the read-only surface, so low impact, but any
  write client changes behavior.
- **0.146.0 / 0.150.0** — `nc_contacts_update_contact`, `nc_webdav_move_resource`,
  `nc_webdav_copy_resource` return typed objects instead of `None`/raw dict.
- **0.155.0** — `nc_semantic_search_answer` tool **removed**, generation-model
  settings removed. N/A here (no Qdrant/embedding backend configured — this is a
  plain app-password bridge).
- **0.156.2** — bundled `mcp` protocol lib bumped to `>=1.29,<1.30`. Small
  transport-compat surface with the streamable-HTTP clients (Claude Desktop, mcporter).
- **0.158.0** — new mail write tools (flags/tags/move/delete) + `MAIL_INDEX_TAG`.
  Additive.

**Net:** stateless image bump, no data/PVC to migrate, trivial revert. Rated
**medium** because it's a 19-minor jump touching the MCP tool contract that two
live consumers (one in-cluster, one on the Mac) depend on — the risk is a silent
tool-behavior regression in the briefing / Desktop surface, not infra or data loss.

## 2) Pre-checks

```bash
# a) current state: server Ready, 1 replica, on 0.140.4, 0 restarts
kubectl get pods -n office -l app.kubernetes.io/name=nextcloud-mcp -o wide
kubectl get pod -n office -l app.kubernetes.io/name=nextcloud-mcp \
  -o jsonpath='{.items[0].spec.containers[0].image}{"\n"}'          # -> ...nextcloud-mcp-server:0.140.4
kubectl get hr -n office nextcloud-mcp \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'   # True

# b) confirm the deployment is stateless (guards the 0.159.0 stale-volume trap is really N/A)
kubectl get pod -n office -l app.kubernetes.io/name=nextcloud-mcp \
  -o jsonpath='{range .items[0].spec.volumes[*]}{.name}{"\n"}{end}'  # only kube-api-access-* → no data volume
# and confirm mode is BasicAuth (guards 0.148.0 OAuth change is N/A)
sops -d kubernetes/apps/office/nextcloud-mcp/app/secret.sops.yaml | grep MCP_DEPLOYMENT_MODE   # single_user_basic

# c) verify the target tag exists on ghcr (bare tag, no 'v' prefix) — expect 200
TOKEN=$(curl -s "https://ghcr.io/token?scope=repository:cbcoutinho/nextcloud-mcp-server:pull" | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
curl -s -o /dev/null -w '0.159.1 -> %{http_code}\n' -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.list.v2+json" \
  https://ghcr.io/v2/cbcoutinho/nextcloud-mcp-server/manifests/0.159.1

# d) baseline a read tool-call works NOW (so a post-bump failure is attributable) — see Verification §4b for the curl
# e) no in-flight reconcile
flux get kustomizations -A | awk 'NR==1 || $5!="True"'

# f) heads-up: nextcloud itself is the upstream this bridges to — confirm it's Ready
kubectl get pods -n office -l app.kubernetes.io/name=nextcloud
```

## 3) Steps (GitOps, copy-pasteable)

> Single image tag, one place: `helmrelease.yaml` line ~34,
> `controllers.main.containers.main.image.tag`. Bare tag `0.159.1` (the ghcr image
> has **no `v` prefix**). No env/config change is required — the OAuth and
> stale-volume breaking changes are N/A (see Summary); `single_user_basic` +
> the existing `NEXTCLOUD_HOST/USERNAME/PASSWORD` secret carry over unchanged.

1. **Silence + active-update marker** (per application-update SOP §1). Suppresses
   the expected ~30s not-ready blip during the rolling replace, and tells the
   alert-triage-agent the OpenClaw briefing surface may hiccup:
   ```bash
   runbooks/update-marker.sh add nextcloud-mcp office 1 "0.140.4->0.159.1 image bump"
   ```

2. **(Optional, recommended for this big jump) disable Flux rollback for the run**
   so a crash-looping new pod *sticks* long enough to read its startup logs (uid-1000
   / CORS / transport surprises) instead of being auto-reverted mid-inspection.
   Edit `kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml`:
   ```yaml
     upgrade:
       cleanupOnFail: false
       remediation:
         retries: 0                 # was 3 — RESTORE to 3 after success (step 5)
   ```

3. **Bump the image tag** in `kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml`:
   ```bash
   sed -i '' 's|tag: 0.140.4|tag: 0.159.1|' kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml
   grep -n 'tag: 0.159.1' kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml   # confirm exactly one hit
   ```

4. **Commit + push** (work on `main`, stage only this hunk):
   ```bash
   git add -p kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml
   git commit -m "feat(nextcloud-mcp): update image ( 0.140.4 → 0.159.1 )"
   git push
   ```
   Flux webhook reconciles; the Deployment rolls the single replica.

5. **On success**, restore rollback (if step 2 was applied) and clear the marker:
   ```bash
   # edit helmrelease.yaml: upgrade.remediation.retries back to 3 (and drop cleanupOnFail if you added it)
   git add -p kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml
   git commit -m "chore(nextcloud-mcp): restore upgrade rollback retries after 0.159.1" && git push
   runbooks/update-marker.sh clear nextcloud-mcp
   ```

## 4) Verification

**4a — pod rolled + healthy**
```bash
kubectl get hr -n office nextcloud-mcp -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'   # True
kubectl get pods -n office -l app.kubernetes.io/name=nextcloud-mcp
kubectl get pod -n office -l app.kubernetes.io/name=nextcloud-mcp \
  -o jsonpath='{.items[0].spec.containers[0].image}{"\n"}'      # -> ...nextcloud-mcp-server:0.159.1
# uid-1000 startup sanity (the 0.159.0 change): logs must NOT show PermissionError / chmod on tokens.db
POD=$(kubectl get pod -n office -l app.kubernetes.io/name=nextcloud-mcp -o jsonpath='{.items[0].metadata.name}')
kubectl logs -n office $POD | tail -40   # expect "server listening"/uvicorn on :8000, no PermissionError, no CORS/transport fatal
kubectl get pod -n office $POD -o jsonpath='{.items[0].status.containerStatuses[0].restartCount}{"\n"}' 2>/dev/null
```

**4b — the MCP server actually serves + BasicAuth tool-call still works** (this is
the load-bearing check: proves the 0.148.0 scope-hardening didn't lock out the
app-password, and the mcp-1.29 protocol lib speaks to a client):
```bash
kubectl port-forward -n office svc/nextcloud-mcp 8000:8000 >/dev/null 2>&1 &
PF=$!; sleep 2
U=$(sops -d kubernetes/apps/office/nextcloud-mcp/app/secret.sops.yaml | awk '/NEXTCLOUD_USERNAME:/{print $2}')
P=$(sops -d kubernetes/apps/office/nextcloud-mcp/app/secret.sops.yaml | awk '/NEXTCLOUD_PASSWORD:/{print $2}')
# initialize handshake — a 200 with serverInfo proves the streamable-HTTP endpoint + protocol lib are alive
curl -s -u "$U:$P" -X POST localhost:8000/mcp \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"verify","version":"1"}}}' | head -c 800; echo
# tools/list — confirm the tool set is present and nc_semantic_search_answer is GONE (0.155.0), read/write tools present
curl -s -u "$U:$P" -X POST localhost:8000/mcp \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' | grep -o '"name":"[^"]*"' | sort -u
kill $PF 2>/dev/null
# Expect: NO InsufficientScopeError, and tool names include nc_webdav_read_file, nc_calendar_*, nc_contacts_* etc.
```

**4c — end-to-end from the two real consumers** (the point of the whole thing):
- **OpenClaw (in-cluster):** confirm mcporter can still reach the endpoint and read
  the nextcloud surface — trigger/observe the next family briefing's nextcloud
  section (calendar/mail/nc-health), or exec into the openclaw pod and run its
  mcporter nextcloud tool-list. A `nc_webdav_read_file` now returns
  **markdown, not base64** (0.151.0) — confirm the briefing renders file content
  normally rather than a base64 blob.
- **Claude Desktop (Mac mini):** confirm the `nextcloud` MCP server still lists
  tools and a file read / calendar list returns real content. (No client-config
  change needed — same ingress URL + app-password.)

Success = HR Ready=True, one pod Ready on `:0.159.1` with 0 restarts after ~3 min,
clean startup log, initialize+tools/list succeed under BasicAuth, and both
consumers read Nextcloud content.

## 5) Rollback

Stateless bridge, no persisted data — downgrade is instant and safe:
```bash
git revert --no-edit <bump-commit-sha>     # restores tag 0.140.4 (+ rollback setting if reverting both commits)
git push
flux reconcile helmrelease -n office nextcloud-mcp --force
```
Confirm back-to-good:
```bash
kubectl get pod -n office -l app.kubernetes.io/name=nextcloud-mcp \
  -o jsonpath='{.items[0].spec.containers[0].image}{"\n"}'   # -> ...:0.140.4
kubectl get hr -n office nextcloud-mcp -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'  # True
```
Then re-run 4b/4c against the two consumers. Clear the marker
(`runbooks/update-marker.sh clear nextcloud-mcp`). No DB/PVC restore is ever needed
(nothing is persisted).

## 6) Interference notes

- **Blast radius is one namespace, one stateless pod.** Only the `nextcloud-mcp`
  Deployment rolls; brief (~30s) endpoint unavailability during the single-replica
  replace. No shared DB/storage/cert-manager/cni touched. Ingress class `internal`
  is not perturbed (backend endpoint swap only — no controller restart), so
  `shared: []`.
- **Cross-namespace downstream consumer — OpenClaw (`ai` ns).** OpenClaw reaches
  this server over HTTP via mcporter (`NEXTCLOUD_MCP_URL`). During the pod replace,
  OpenClaw's nextcloud MCP calls fail for ~30s. **Do NOT run this in the same
  window as an OpenClaw restart/upgrade** — a simultaneous bounce of both can wedge
  the briefing's MCP session. If an OpenClaw plan lands in the same window, set it
  `conflicts_with` this one (order: bump+verify nextcloud-mcp *first*, then OpenClaw).
  Avoid the OpenClaw morning-briefing window.
- **External consumer — Claude Desktop on the Mac mini** (via ingress). Same ~30s
  blip; auto-reconnects. No config change.
- **The functional risk is a tool-contract regression, not infra.** The load-bearing
  post-checks are 4b (BasicAuth tool-call still authorized after the 0.148.0 scope
  hardening) and 4c (read returns markdown not base64 after 0.151.0). If either
  consumer's nextcloud surface misbehaves, that's the signal to roll back — the pod
  can be perfectly "Ready" while the tool contract has drifted.
- **Not a reboot job** (`needs_reboot: false`), low blast, stateless — fits a short
  tue/thu-early no-reboot window. Operator-present preferred only to eyeball the two
  consumers post-bump, not because of scope.
