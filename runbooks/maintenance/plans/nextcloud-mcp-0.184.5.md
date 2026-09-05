---
plan_id: nextcloud-mcp-0.184.5
component: nextcloud-mcp
pr: null
kind: image
current: "0.179.0"
target: "0.184.5"
update_type: minor
risk: low
est_duration_min: 20
needs_reboot: false
touches:
  namespaces: [office]
  resources: [helmrelease/nextcloud-mcp, deployment/nextcloud-mcp, kustomization/nextcloud-mcp]
  shared: []
depends_on: []
conflicts_with: [nextcloud-9.2.6]
security_ref: null
capability_change: true   # v0.181.0 (inside this span) changes the response
                          # CONTRACT of one MCP tool (nc_calendar_update_todo):
                          # dict -> typed envelope, drops status_code, raises
                          # on failure instead of reporting a status. That is
                          # user-visible behaviour change for anything driving
                          # that tool (OpenClaw's calendar/todo skills), even
                          # though no repo code hard-parses the old shape.
                          # Everything else in 0.180..0.184.5 is feat/fix/perf,
                          # non-breaking. Flagged true out of caution for that
                          # one tool; do not run fully unattended.
rollback_class: git-revert
finding_refs: []
status: draft
window: null
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/flux-dependency-revision-gate.md
generated: "2026-09-05"
---

## 1) Summary & why held

`nextcloud-mcp` (ghcr.io/cbcoutinho/nextcloud-mcp-server) is a third-party MCP
bridge server deployed in `office` (HelmRelease `nextcloud-mcp`, app-template
5.1.0 chart, unchanged by this bump — image tag only). It exposes Nextcloud
files/notes/calendar/contacts/deck/tables as MCP tools over HTTP, consumed
in-cluster by OpenClaw (`ai` namespace, `kubernetes/apps/ai/openclaw/app/mcporter-config.yaml`,
the `"nextcloud"` server entry) and reachable on the internal ingress class at
`nextcloud-mcp.${SECRET_DOMAIN}` for any externally-configured MCP client
(e.g. a Claude Desktop config on an operator machine — not itself tracked in
this repo, so this plan cannot verify it, only flag it for an operator spot
check post-upgrade).

`runbooks/auto-update-policy.yaml` holds this component unconditionally
(`match: "*nextcloud-mcp*"`, deliberately placed **above** the broader
`*nextcloud*` glob so it isn't matched — and excused — by the Nextcloud
server's occ/maintenance-mode reason, which does not apply here): *"upstream
ships BREAKING-tagged releases on minor hops (0.176.0 removed the webhook
registration API and dropped its table; 0.177.0 tightened create_share). Read
the release notes per hop — never an unattended bump."* Both of those cited
hops are already behind current (0.179.0); this plan covers the next span,
0.179.0 → 0.184.5, five more minor hops.

**Target tag verified to exist** (2026-09-05, multi-arch OCI index):
```
GET https://ghcr.io/v2/cbcoutinho/nextcloud-mcp-server/manifests/0.184.5
→ 200, docker-content-digest: sha256:f6d8839722587f2cd37ec5218a18479f9e313be9904ad4f6bbb36f98bc827065
```

**Full changelog read across the whole 0.179.0 → 0.184.5 span** (upstream
`CHANGELOG.md`, conventional-commits/commitizen generated — this repo IS the
authoritative BREAKING CHANGE marker per upstream's own convention):

| Version | Date | Content |
|---|---|---|
| 0.180.0 | 2026-08-21 | feat: Nextcloud Talk (spreed) conversation/participant/reaction tools, gated on the server's advertised feature flag. Additive only. |
| 0.181.0 | 2026-08-22 | **`### BREAKING CHANGE`** — `nc_calendar_update_todo` now returns a typed `UpdateTodoResponse` instead of a raw dict: gains a `BaseResponse` envelope (`success`, `timestamp`) + `calendar_name`, **drops `status_code`** — a failed update now **raises** rather than returning a failure status in the payload. `nc_calendar_complete_todo` gains an `etag` field (additive, non-breaking). Also: OCS client 423-Locked retry/jitter, ETag concurrency plumbing. |
| 0.181.1 | 2026-08-26 | fix: CI tooling only (pact CLI script pointer). No runtime change. |
| 0.182.0 | 2026-08-26 | feat: direct file linking from search results/reads. Additive. |
| 0.183.0 / 0.183.1 | 2026-08-28 | Vector/semantic-search indexing fixes (stale-chunk pruning) + an `icalendar` dependency bump. This deployment has no vector/Qdrant config wired (`secret.sops.yaml` carries only `NEXTCLOUD_HOST/USERNAME/PASSWORD` + `MCP_DEPLOYMENT_MODE=single_user_basic`) — dead code path here, zero risk. |
| 0.184.0 | 2026-08-30 | feat: calendar/event free/busy transparency data. Additive. |
| 0.184.1 | 2026-08-30 | fix: WebDAV ETag normalisation for a compressing proxy. Behind-the-scenes correctness fix. |
| 0.184.2 | 2026-09-01 | perf: JSON output compaction for tool results. No schema change to individual tool payloads. |
| 0.184.3 | 2026-09-03 | fix: OCR batch-job provider/retry bugs — OCR tier is part of the same vector/Astrolabe pipeline this deployment does not use. |
| 0.184.4 | 2026-09-04 | perf: concurrent calendar queries in cross-calendar search. Behaviour-preserving. |
| 0.184.5 | 2026-09-04 | fix(auth): `nc_auth_check_status` now polls a pending Login Flow v2 session before reporting the stored app password, so a scope-update never completes for `login_flow`/OAuth tenants (GH #1431/#1432). **This deployment runs `MCP_DEPLOYMENT_MODE=single_user_basic`** (static `NEXTCLOUD_USERNAME`/`NEXTCLOUD_PASSWORD`, no OAuth/Login-Flow session ever created) — confirmed by reading the PR: the fix is scoped entirely to the `nc_auth_check_status`/`nc_auth_update_scopes` pending-flow path, which single_user_basic never enters. **Not applicable to this deployment's auth wiring; no config change needed.** |

**Net finding: exactly one breaking change in the whole span, and it is
narrow.** `nc_calendar_update_todo`'s response envelope changed shape
(0.181.0). Everything else is additive feat/fix/perf. No MCP transport/protocol
version change, no change to how the server authenticates
(`single_user_basic` is untouched by every OAuth/Login-Flow-scoped commit in
this span, including the newest 0.184.5 fix), no environment-variable or
config-key change for this deployment mode (checked `env.sample`,
`docs/configuration.md` history — all touched knobs are OAuth/multi-user/
vector-specific).

**Does the client need a matching config change? No.** OpenClaw's MCP client
(`mcporter`) and Claude Desktop are both generic MCP consumers — they read the
tool's JSON schema and result at call time; nothing in this repo (grepped
`kubernetes/apps/ai/openclaw/`, skills, workspace docs) hard-parses
`nc_calendar_update_todo`'s old `status_code` field. The breaking change is
real (a failure that used to come back as data now comes back as a thrown MCP
tool error) but self-describing at the protocol level — an LLM-driven caller
adapts to the new schema from the tool description, it does not need a code or
manifest change. Flagged `capability_change: true` anyway because the
*behaviour* a human sees changed (a failed todo update now surfaces as a tool
error rather than a silent "not updated" status) — worth an operator's eyes
once, not worth blocking an attended window over.

**Blast radius assessment: this is a developer/assistant tool, not household
infrastructure.** Single Deployment replica, no PVC (no local token DB —
`single_user_basic` needs none), internal-only ingress, one in-cluster
consumer (OpenClaw's read-oriented "nextcloud" MCP entry) plus whatever
external MCP client an operator has pointed at it (unverifiable from this
repo). If this is wrong, the worst case is OpenClaw's Nextcloud-backed
tools/calendar-todo-update misbehave for however long it takes to notice and
revert one image tag — no data loss, no other app depends on this component's
uptime. **Hold was correct in spirit (never skip reading BREAKING-tagged
release notes on this repo) but the actual span is low risk** — recommend
`risk: low`, attended-but-brief rather than a long/reboot-capable window.

## 2) Pre-checks

```bash
# 1. Re-verify the target tag still exists (SOP Step 0 — re-check at execution
#    time, don't trust this investigation's timestamp if the window is days out)
TOKEN=$(curl -s "https://ghcr.io/token?scope=repository:cbcoutinho/nextcloud-mcp-server:pull&service=ghcr.io" | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
curl -sI -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.oci.image.index.v1+json" \
  "https://ghcr.io/v2/cbcoutinho/nextcloud-mcp-server/manifests/0.184.5" | grep -i docker-content-digest

# 2. Baseline: current pod healthy on 0.179.0, note the imageID (prove the
#    rollout actually changed bytes later, not just the tag string)
kubectl get pods -n office -l app.kubernetes.io/name=nextcloud-mcp -o wide
kubectl get pods -n office -l app.kubernetes.io/name=nextcloud-mcp \
  -o jsonpath='{.items[0].status.containerStatuses[0].imageID}{"\n"}'

# 3. Confirm office/nextcloud (the Flux dependsOn target) is Ready and
#    converged BEFORE you push — a dependency mid-reconcile makes this
#    Kustomization's post-push not-Ready message noise, not a real failure
#    (docs/sops/flux-dependency-revision-gate.md)
kubectl get kustomization -n office nextcloud \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.conditions[?(@.type=="Ready")].lastTransitionTime}{"\n"}'

# 4. Confirm the paired nextcloud-9.2.6 chart-bump plan is NOT scheduled in
#    this same window (conflicts_with) — if it is, defer one of the two
python3 runbooks/maintenance-plan.py --open | grep -i nextcloud

# 5. Baseline the MCP tool surface BEFORE the bump, so the post-upgrade
#    contents assertion has something real to diff against (see §4).
#    Port-forward the service and list tools + inspect nc_calendar_update_todo's
#    current (pre-0.181.0-shape... already-past, so should show the NEW shape
#    if 0.179.0 somehow already had it — it should NOT) output schema:
kubectl port-forward -n office svc/nextcloud-mcp 18000:8000 &
curl -s http://localhost:18000/mcp -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); t=[x for x in d.get('result',{}).get('tools',[]) if x['name']=='nc_calendar_update_todo']; print(json.dumps(t, indent=2))"
```

## 3) Steps

1. **Edit the image tag** in
   `kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml`:
   ```yaml
   image:
     repository: ghcr.io/cbcoutinho/nextcloud-mcp-server
     tag: 0.184.5   # was 0.179.0
   ```
2. Optional (recommended given the office-namespace coupling in §6): drop a
   short update marker so the alert-triage-agent treats any transient
   restart noise as expected, and so it isn't confused with the parallel
   `nextcloud-9.2.6` chart bump if the two land in the same week:
   ```bash
   runbooks/update-marker.sh add nextcloud-mcp office 1 "0.179.0->0.184.5 image bump"
   ```
3. **Commit + push, scoped to exactly this file** (shared-worktree rule —
   `git commit --only`):
   ```bash
   git commit --only kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml -m "$(cat <<'EOF'
   feat(nextcloud-mcp): bump image 0.179.0 -> 0.184.5

   Five minor hops upstream; one BREAKING CHANGE in the span (v0.181.0,
   nc_calendar_update_todo response envelope) — reviewed, no config change
   needed for this single_user_basic deployment. See
   runbooks/maintenance/plans/nextcloud-mcp-0.184.5.md for the full evidence.
   EOF
   )"
   git show --stat HEAD   # confirm only this file rode along
   git push
   ```
4. **Watch the reconcile** (single replica, no PVC, default RollingUpdate is
   fine here — nothing Longhorn-RWO-attached to deadlock on):
   ```bash
   flux get kustomization -n office nextcloud-mcp --watch
   flux get helmrelease -n office nextcloud-mcp
   kubectl get pods -n office -l app.kubernetes.io/name=nextcloud-mcp -w
   ```
5. Run Verification (§4).
6. On success: if you set the marker in step 2, clear it
   (`runbooks/update-marker.sh clear nextcloud-mcp`). Set this plan's
   `status: executed` and delete the file in the same commit, per
   `runbooks/maintenance/plans/README.md`.
   On failure: go to Rollback (§5).

## 4) Verification

```bash
# Flux Ready + correct chart/image recorded
kubectl get helmrelease -n office nextcloud-mcp \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'
kubectl get pods -n office -l app.kubernetes.io/name=nextcloud-mcp \
  -o jsonpath='{.items[0].spec.containers[0].image}{"\n"}'

# Proof the running BYTES changed, not just the tag string
kubectl get pods -n office -l app.kubernetes.io/name=nextcloud-mcp \
  -o jsonpath='{.items[0].status.containerStatuses[0].imageID}{"\n"}'
# compare against the pre-checks baseline imageID and against
# sha256:f6d8839722587... from §2 step 1
```

**CONTENTS ASSERTION (auth/API round-trip, per the "auth / SSO / identity"
exemplar — a healthy pod proves nothing about whether it can still talk to
Nextcloud):**

```bash
kubectl port-forward -n office svc/nextcloud-mcp 18000:8000 &

# (a) The tool surface actually carries the new v0.181.0 schema — not a
#     cached/stale spec from a Kustomization that silently didn't roll:
curl -s http://localhost:18000/mcp -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
  | python3 -c "
import sys, json
d = json.load(sys.stdin)
t = next(x for x in d['result']['tools'] if x['name']=='nc_calendar_update_todo')
schema = json.dumps(t.get('outputSchema') or t.get('inputSchema') or t)
assert 'success' in schema and 'calendar_name' in schema, 'still on the OLD dict shape — rollout did not actually land'
print('OK: nc_calendar_update_todo carries the 0.181.0+ envelope')
"

# (b) A REAL authenticated call against the live Nextcloud instance returns
#     REAL content — proves single_user_basic creds still authenticate post-
#     bump, not just that the pod is Ready. Use a low-risk read tool (notes
#     or capabilities), assert the response is non-empty and not an auth error:
curl -s http://localhost:18000/mcp -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"nc_notes_search_notes","arguments":{"query":""}}}' \
  | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert 'error' not in d, f'auth or call failure: {d}'
result = d.get('result', {})
assert result, 'empty result — pod is Ready but not actually serving Nextcloud data'
print('OK: authenticated call against drive.${SECRET_DOMAIN} returned real content')
"

# (c) Downstream consumer still connects — from an openclaw pod, confirm the
#     'nextcloud' mcporter entry reconnects and lists the same (new) tool set
#     rather than a session stuck on a stale cached schema:
kubectl exec -n ai deploy/openclaw -- mcporter list nextcloud 2>&1 | tail -20
```

CONTENTS ASSERTION: **the MCP tool response schema for
`nc_calendar_update_todo` AND a live authenticated read against the real
Nextcloud backend** — measured by the two `tools/call`/`tools/list` probes
above, compared against (a) the upstream 0.181.0 CHANGELOG schema description
and (b) the pre-upgrade baseline captured in §2 step 5. A pod that is merely
`Ready` with a `tcpSocket` probe passing proves nothing here — that is exactly
what this component's liveness/readiness probes check, and exactly what would
still pass if the credentials silently stopped authenticating.

## 5) Rollback

```bash
git revert <bump-commit-sha> --no-edit
# or, equivalently, hand-edit back:
# kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml: tag: 0.179.0
git commit --only kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml \
  -m "revert(nextcloud-mcp): back to 0.179.0"
git push
flux reconcile helmrelease -n office nextcloud-mcp --force
kubectl get pods -n office -l app.kubernetes.io/name=nextcloud-mcp \
  -o jsonpath='{.items[0].spec.containers[0].image}{"\n"}'   # confirm 0.179.0
runbooks/update-marker.sh clear nextcloud-mcp   # if it was set
```
No data migration occurred (no PVC, no schema/DB touched by this component),
so rollback is a pure image-tag revert — no backup-restore, no `maxHistory`
concern (chart version never changed).

## 6) Interference notes

- **`conflicts_with: [nextcloud-9.2.6]`** — both this plan and the Nextcloud
  chart 9.2.5→9.2.6 bump touch the `office` namespace. Do not run them in the
  same window / same batch of commits. Reasons:
  - **Diagnostic isolation**: if something in `office` misbehaves right after
    the window, you want exactly one namespace-scoped change in flight to
    blame it on.
  - **Flux `dependsOn` revision gate**: `nextcloud-mcp`'s Kustomization has
    `dependsOn: [office/nextcloud]` (revision-gated, not just readiness-gated
    — `docs/sops/flux-dependency-revision-gate.md`). Pushing both bumps close
    together produces a `dependency 'office/nextcloud' revision is not up to
    date` transient on `nextcloud-mcp` — benign, but easy to misread as this
    plan's own failure if you don't know the gate exists. **Sequence:** land
    the `nextcloud-9.2.6` chart bump first, wait for `office/nextcloud`'s
    Kustomization AND HelmRelease to report `Ready=True` at the new revision,
    *then* commit this plan. Do not batch the two pushes.
- **Downstream consumer**: OpenClaw (`ai` namespace) is the one in-cluster MCP
  client (`mcporter` "nextcloud" entry, HTTP transport, credentials from
  `openclaw-secret`). Single replica + rollout here means a brief window
  (seconds, no PVC to wait on) where OpenClaw's Nextcloud-backed tools return
  connection errors. Not disruptive on its own — the agent surfaces a tool
  error rather than silently failing — but worth knowing if a household
  member happens to ask the assistant a Nextcloud-calendar question during the
  exact rollout second.
- **Un-tracked external consumer**: the task description names Claude Desktop
  as a client of this MCP server via its internal ingress
  (`nextcloud-mcp.${SECRET_DOMAIN}`). No such client config exists anywhere in
  this repo (checked `docs/`, no `claude_desktop_config.json` under version
  control — expected, since that file lives on an operator's own machine, not
  in GitOps). This plan cannot verify or update it. **Operator action**: after
  landing this bump, if you use Claude Desktop against this server, restart
  that MCP connection once so it picks up the new tool schema instead of a
  cached one from the previous session.
- **No shared infra perturbed**: chart version unchanged (app-template 5.1.0),
  no PVC/Longhorn involvement, no ingress-controller/cilium/coredns/DB touch.
  `shared: []` is accurate.
- **The one real breaking change (v0.181.0, `nc_calendar_update_todo`) is
  scoped to exactly one tool.** If verification passes for the two `tools/call`
  probes in §4, nothing else in the 0.180.0–0.184.5 span needs separate
  scrutiny — the vector/OCR-pipeline commits (0.183.x/0.184.3) are dead code
  for this `single_user_basic`, no-Qdrant deployment, and the 0.184.5 auth fix
  is scoped to `login_flow`/OAuth tenants this deployment never becomes.
