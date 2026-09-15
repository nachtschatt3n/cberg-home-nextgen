---
plan_id: nextcloud-mcp-0.187.1
component: nextcloud-mcp
pr: null                              # no Renovate PR (`gh pr list --state all --search
                                      # nextcloud-mcp` is empty); held by the `*nextcloud-mcp*`
                                      # `max: patch` deny rule in runbooks/auto-update-policy.yaml
                                      # via coverage.py's PLAN lane, not by a live PR
kind: image
current: "0.184.5"
target: "0.187.1"
update_type: minor                    # semver label only — at major version 0 the MINOR digit
                                      # is the breaking axis; this hop crosses THREE minor lines
                                      # (0.184 -> 0.185 -> 0.186 -> 0.187), nine tags. See §1.2.
risk: medium
est_duration_min: 30
needs_reboot: false
touches:
  namespaces: [office]
  resources:
    - helmrelease/nextcloud-mcp
    - deployment/nextcloud-mcp
                                      # httproute/nextcloud-mcp deliberately NOT listed (review
                                      # 2026-09-15): it is re-rendered by the same HelmRelease
                                      # but its spec does not change — image tag is the whole
                                      # diff — so it is not perturbed.
  shared: []                          # no shared datastore, gateway, CNI or DNS perturbed, so
                                      # gateway/envoy is NOT declared. Cross-namespace CONSUMER
                                      # coupling (ai/openclaw, Claude Desktop on the Mac) is real
                                      # blast radius but not shared-infra — see §6.
depends_on: []                        # Flux `dependsOn: nextcloud` is an ordering constraint
                                      # (namespace/reconcile-first), not a version coupling —
                                      # no release note in range states a minimum Nextcloud
                                      # server version (§1.2). nextcloud-34.0.4 (draft) DOES
                                      # touch the server — see conflicts_with, not depends_on:
                                      # either order works, they must not share a slot.
conflicts_with:
  - nextcloud-34.0.4                  # ADDED 2026-09-15 (review): that draft restarts
                                      # deployment/nextcloud and moves it 34.0.3 -> 34.0.4;
                                      # §4.4 here talks to that server, so a restart mid-
                                      # verification makes a calendar-list failure
                                      # unattributable, and the namespace-wide silence that
                                      # plan sets would mask this rollout's noise. Different
                                      # slots (e.g. sat/sun of one weekend); the
                                      # nextcloud-server premise below is drift-tolerant
                                      # (34.0.x) so either order is fine — re-take the §2.4
                                      # baselines the SAME DAY as execution, after any server
                                      # move. bitnamilegacy-exit-nextcloud-db (office, blocked,
                                      # window null) cannot claim a slot today; add it if it is
                                      # revived — see §6.
security_ref: F-80459b23              # security-driven bump: a newer upstream tag exists and
                                      # taking it is the only remediation this household performs
                                      # for a third-party image. Detail stays on the record.
capability_change: true               # HONEST FACT, reviewed with the plan (§1.3): two
                                      # agent-visible tool behaviours change for our consumers —
                                      # 0.187.0 turns `nc_calendar_find_availability` from a
                                      # registered-but-unimplemented tool into a working one, and
                                      # 0.186.0 WILL register `shopping_list_*` tools (upstream
                                      # deliberately does not gate them on app presence; the
                                      # Nextcloud app is not installed here, so calls 404 —
                                      # additive, §1.2). Routes to an attended window — which
                                      # the deny rule mandates anyway.
rollback_class: git-revert            # stateless bridge: no PVC, no volumes, no DATABASE_URL /
                                      # TOKEN_STORAGE_DB — its alembic migrations run against an
                                      # EPHEMERAL SQLite in /tmp recreated on every pod start
                                      # (premises 4+5 prove it). `values.image.tag` is the diff.
finding_refs: [F-9af9baf7, F-80459b23]
status: awaiting-go   # OPERATOR GO 2026-09-15 (direct, attended update in its window; recorded in home-operation, exec_state=pending). REVIEWED 2026-09-15, corrections c36388bc
window: "sat-attended:2026-10-03"   # assigned 2026-09-15 from the review synthesis (capacity-checked); go/no-go via home-operation
                                      # reason ("every minor hop needs its release notes read by a
                                      # human") is explicit; never the nightly/unattended window.
                                      # Capacity note (2026-09-15): sat-attended:2026-09-19 holds
                                      # 45min/low, sun-attended:2026-09-20 holds 60min/low — either
                                      # fits this 30min/medium with margin. §6.
premises:
  - id: image-is-still-0.184.5
    why: >-
      `current:` claims 0.184.5 and the rollback target is that tag. If the
      cluster already moved, this plan is stale and its diff and verification
      baseline no longer match reality (the README's phantom-plan failure mode).
    run: kubectl get deploy -n office nextcloud-mcp -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: ghcr.io/cbcoutinho/nextcloud-mcp-server:0.184.5
  - id: nextcloud-server-unchanged
    why: >-
      No release note in range states a minimum Nextcloud server version, but
      "nothing moved underneath this" must be observed, not assumed from a
      stale read — the calendar DAV encoding change in 0.185.5 talks to this
      server directly. Drift-tolerant on the PATCH digit (review 2026-09-15):
      nextcloud-34.0.4 is a live draft, and a hard pin on 34.0.3 would fail
      this plan closed as a phantom the moment that plan executes first. A
      server MAJOR/MINOR move still fails it — that is the re-vet trigger.
      Whatever patch is live, re-take the §2.4 baselines the same day.
    run: kubectl get deploy -n office nextcloud -o jsonpath='{.spec.template.spec.containers[?(@.name=="nextcloud")].image}'
    expect_matches: 'docker\.io/nextcloud:34\.0\.[0-9]+$'
  - id: deployment-mode-still-single-user-basic
    why: >-
      The ONE BREAKING-tagged change in this hop (0.185.0, mcp>=2.1 SDK floor:
      server-initiated elicitation degrades to message_only) fires only on the
      multi-user Login Flow consent path. This deployment runs
      MCP_DEPLOYMENT_MODE=single_user_basic — static credentials, no Login
      Flow, no elicitation — so that change is inert HERE. If this value ever
      changes to a multi-user mode the risk assessment in §1.2 is void and the
      plan must be re-vetted, not run.
    run: kubectl get secret -n office nextcloud-mcp-config -o json | jq -r '.data.MCP_DEPLOYMENT_MODE' | jq -Rr '@base64d'
    expect_exact: single_user_basic
  - id: no-persistent-token-store-configured
    why: >-
      `rollback_class: git-revert` rests on the server owning NO persistent
      schema. Upstream persists refresh tokens only when DATABASE_URL or
      TOKEN_STORAGE_DB is set; otherwise it uses an ephemeral SQLite in /tmp
      (pod logs: "Using ephemeral token storage ... set DATABASE_URL or
      TOKEN_STORAGE_DB to persist"). The secret's key set is exactly the four
      connection keys — if a fifth appears, a downgrade may face a
      forward-migrated schema and this plan's rollback is no longer free.
    run: kubectl get secret -n office nextcloud-mcp-config -o go-template='{{range $k,$v := .data}}{{$k}},{{end}}'
    expect_exact: MCP_DEPLOYMENT_MODE,NEXTCLOUD_HOST,NEXTCLOUD_PASSWORD,NEXTCLOUD_USERNAME,
  - id: no-volumes-on-the-pod
    why: >-
      Second half of the stateless claim — the Deployment mounts nothing, so
      there is no PVC to snapshot, no RWO multi-attach guard needed, and a
      rolling update cannot strand on storage.
    run: kubectl get deploy -n office nextcloud-mcp -o json | jq -r '.spec.template.spec.volumes'
    expect_exact: "null"
  - id: helmrelease-chart-5.1.0
    why: >-
      The verification commands assume the app-template 5.1.0 render (probe
      shape, route key). A chart hop landing in the same window would change
      what "Ready" means here.
    run: kubectl get helmrelease -n office nextcloud-mcp -o jsonpath='{.status.history[0].chartVersion}'
    expect_exact: "5.1.0"
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/auto-update.md
generated: "2026-09-15"
---

## 1. Summary & why held

`kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml:34` pins
`ghcr.io/cbcoutinho/nextcloud-mcp-server` at `0.184.5`. Upstream head is
`0.187.1` (sweep finding `F-9af9baf7`). `coverage.py` routes it to the PLAN
lane: *"0.x release-line move (0.184 -> 0.187) — at major 0 the minor IS the
breaking axis"*, and the `*nextcloud-mcp*` deny rule (`max: patch`) exists
because upstream has shipped BREAKING-tagged releases on minor hops before
(0.176.0 removed the webhook registration API and dropped its table; 0.177.0
tightened `create_share`). The prior plan `nextcloud-mcp-0.185.3` was
superseded 2026-09-13 (`00c62d4c`, `F-a1984c9f`) because upstream moved two
more minor lines past its target; this plan re-reads **every** tag in the
range rather than sed-ing that file's target.

**Verdict after reading all nine release-note sets (§1.2): the hop carries
exactly ONE upstream-tagged BREAKING CHANGE (0.185.0, MCP SDK v2 floor), and it
is inert for this deployment's auth mode. Everything after 0.185.0 is fixes and
additive features. Risk stays `medium`, not `low`, for one honest reason: both
consumers (OpenClaw's `mcporter`, Claude Desktop's `mcp-proxy`) are installed
UNPINNED at launch, so their MCP client-library version — and therefore the
real-world effect of a server-side SDK-major migration — is not knowable from
this repo. §4 is written to catch that empirically.**

### 1.1 Registry verification (done 2026-09-15; re-run at execution, §2 step 0)

GHCR OCI index (`Accept: application/vnd.oci.image.index.v1+json`, anonymous
pull-scope token):

| tag | result |
|---|---|
| `0.184.5` (live) | 200, digest `sha256:f6d88397…` |
| `0.187.1` (target) | 200, digest `sha256:57d9c93f…` |
| `latest` | 200, digest **identical** to `0.187.1` → 0.187.1 is upstream's channel head |
| `0.187.2`, `0.188.0` | 404 — nothing newer exists |
| `stable` | 404 — there is no `stable` tag on this repo; this is why coverage's `max_rule_fallback` reported the stable channel "unreadable". `latest` is the only channel pointer. |

Release age: `v0.187.1` published 2026-09-12T15:39Z — past the 48h
`minimum_release_age_hours` gate by any window. Tags carry no `v` prefix on
GHCR (`0.187.1`), only on GitHub releases (`v0.187.1`).

### 1.2 What actually changed, 0.184.5 → 0.187.1, read per tag

Quoted from the GitHub release bodies (`gh release view vX.Y.Z -R cbcoutinho/nextcloud-mcp-server`).

| tag | published | class | what it says | applies to us? |
|---|---|---|---|---|
| **0.185.0** | 2026-09-05 | **BREAKING CHANGE** | *"requires mcp>=2.1,<3 (protocol 2026-07-28). Server-initiated elicitation no longer reaches 2026-era clients — progressive consent degrades to message_only, with the login URL carried in the returned message. Deployments pinning mcp<2 must stay on the previous release."* Plus: *fix(errors): restore the tool-failure message mcp 2.x withholds*; *fix(sharing): a bare RuntimeError loses its message under mcp 2.x*; refactors lifting deck/notes/mail tool registration to module level. | **Inert on the stated path**: elicitation/progressive consent is the multi-user **Login Flow**; we run `single_user_basic` (premise 3; pod log: "Starting MCP session in single-user BasicAuth mode"). The SDK-major migration itself is the residual risk — server-side protocol behaviour vs. our unpinned clients (§1.4). No tool renamed or removed. |
| 0.185.1 | 2026-09-08 | fix (auth, upstream advisory) | *"verify the Login Flow granter is the caller"* | Login Flow only — not exercised here. Security detail, if any, tracked on the finding record (§1.5), not here. |
| 0.185.2 | 2026-09-09 | fix (auth) | *"resolve the Login Flow caller's UID from Nextcloud, not IdP claims"* | Login Flow only — not exercised here. |
| 0.185.3 | 2026-09-09 | fix (deck) | attachment type on id-addressed routes; card attachments linked, Files-share ones no longer hidden | No `deck_*` tools are registered on our server (Deck app not installed on Nextcloud, §2.3) — inert. |
| 0.185.4 | 2026-09-11 | fix (processors) | *"batch OCR is worker-only — stop the inline escalation loop"* | Optional document processors are not configured (pod log: "No optional document processors configured") — inert. |
| **0.185.5** | 2026-09-11 | fix (calendar) | *"encode DAV URLs by one rule, not two"*; *"percent-encode DAV URLs built from decoded path segments"*; DAV encoders moved to a shared module | **Applies.** Calendar is installed (Nextcloud `calendar 6.5.3`) and is on the tool surface both consumers use. A behaviour fix on the CalDAV request path — verified directly in §4.4. |
| 0.186.0 | 2026-09-11 | feat (additive) | *"add Nextcloud Shopping List app support"* (+ fixes to its `add_items`, typed item schema) | New `shopping_list_*` tools **WILL register** even though the Shopping List app is **not installed** on our Nextcloud (§2.3): at v0.187.1 `server/__init__.py`'s `APP_CAPABILITY_KEY` deliberately EXCLUDES shopping_list (upstream comment: *"gating it would hide working tools on every instance that has it"*; only notes/tables/deck/cookbook/talk are app-gated). Calls fail with a Nextcloud 404 — additive, not breaking; §4.3 expects them to appear. |
| **0.187.0** | 2026-09-12 | feat (calendar) | *"implement nc_calendar_find_availability"*; fixes: *"reject an unknown availability timezone"*, *"refuse availability when a calendar cannot be read"* | **Applies — behaviour, not surface.** The tool name is ALREADY in the live 0.184.5 tool list with a full description; 0.187.0 makes it work (v0.184.5 `client/calendar.py:2918`: *"This is a simplified stub that returns empty list"*, with a `find_availability is not fully implemented` warning log). This is the `capability_change: true` fact. |
| 0.187.1 | 2026-09-12 | fix (ingest) | empty download counted on the truncation panel; empty document payloads refused instead of dead-lettered; OCR log placeholder | Document-ingest pipeline — not configured here — inert. |

**No tag in range renames or removes an MCP tool, drops a table, changes the
required Nextcloud server version, or changes any env var this deployment
sets.** The 0.176.0 failure shape (removed API + dropped table) does not recur.

### 1.3 Storage: does the server own a table or a PVC?

It runs alembic at startup (`nextcloud_mcp_server.migrations - Upgrading
database to revision: head`) — but against `sqlite+aiosqlite:////tmp/…` because
neither `DATABASE_URL` nor `TOKEN_STORAGE_DB` is set (premise 4), and the pod
mounts no volumes (premise 5). The schema is recreated from nothing on every
pod start and discarded with the container. **There is nothing to back up and
nothing a downgrade can collide with**, hence `rollback_class: git-revert`.

### 1.4 The residual risk, stated plainly

0.185.0 moved the server to the MCP python-sdk v2 line. Our two consumers:

- **OpenClaw** (`ai`): `mcporter` installed by `install_npm mcporter` at pod
  start (`kubernetes/apps/ai/openclaw/app/helmrelease.yaml:442`), unpinned;
  speaks streamable-HTTP to this server per `mcporter-config.yaml`.
- **Claude Desktop** (operator's Mac): `uvx mcp-proxy --transport
  streamablehttp https://nextcloud-mcp.${SECRET_DOMAIN}/mcp` from
  `~/Library/Application Support/Claude/claude_desktop_config.json`, unpinned.

Neither client version is statically knowable from this repo. MCP servers
negotiate protocol version downward at `initialize`, and the 0.184.5 server
already answers a `2025-06-18` initialize correctly (§2.4 baseline was
captured exactly that way), so a hard break is unlikely — but "unlikely" is
why §4.3–4.5 assert the actual tool surface and a real consumer round-trip
rather than trusting the TCP probe.

### 1.5 Security driver

> **Security driver — detail withheld from this public repo.**
> Tracked as **F-80459b23** (`security`; contextual tier on the record is
> MEDIUM — internal exposure, not in KEV — quote that, not the raw scanner
> severity).
> Full detail (CVE IDs, counts, exposure, exploitability) lives on the
> finding record — it is deliberately not reproduced here.
>
> - Dashboard: `https://sweep.<DOMAIN>/findings/F-80459b23`
> - CLI: `runbooks/policy-cli.py finding show F-80459b23`

`F-f02df447` (`[AR-029]`, accepted) is the already-newest-tag tally on the same
image; it is expected to narrow but not clear after the bump — base-OS package
drift is independent of the app version. A non-zero residual there is the
accepted-risk model for third-party images, not a plan failure.

## 2. Pre-checks

0. **Re-verify the target is still upstream's head** (manual — the premise
   checker has no network tool). If `0.187.2`/`0.188.0` now return 200,
   **STOP**: read that tag's release body before retargeting — at major 0 a
   new minor is a new breaking surface, never a sed.
   ```bash
   TOKEN=$(curl -s "https://ghcr.io/token?scope=repository:cbcoutinho/nextcloud-mcp-server:pull&service=ghcr.io" \
     | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
   for t in 0.187.1 latest 0.187.2 0.188.0; do
     printf '%-8s ' "$t"
     curl -sI -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.oci.image.index.v1+json" \
       "https://ghcr.io/v2/cbcoutinho/nextcloud-mcp-server/manifests/$t" \
       | tr -d '\r' | awk 'NR==1{printf "%s ",$2} tolower($1)=="docker-content-digest:"{print $2}'; echo
   done
   # expect: 0.187.1 200 <digest>; latest 200 <SAME digest>; 0.187.2 404; 0.188.0 404
   ```
1. **Premises pass** (all six, fail-closed):
   ```bash
   python3 runbooks/plan-premises.py nextcloud-mcp-0.187.1 --require-premises
   ```
2. **Cluster health floor** — no unrelated red before starting:
   ```bash
   flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
   flux get helmreleases -A   | awk 'NR==1 || $5 != "True"'
   kubectl get pods -n office -l app.kubernetes.io/name=nextcloud-mcp
   # expect: 1/1 Running, 0 restarts
   kubectl get helmrelease -n office nextcloud-mcp -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'
   # expect: True (no in-flight upgrade)
   ```
3. **Which Nextcloud apps the tool families depend on** (informs §1.2 rows
   for 0.185.3 / 0.186.0 — a change here changes what "superset" means):
   ```bash
   kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c 'php occ app:list' \
     | grep -iE 'calendar|contacts|deck|notes|tables|shoppinglist|mail|talk|collectives|news'
   # measured 2026-09-15: calendar 6.5.3, contacts 8.7.6 present; NO deck, notes, tables, shopping list
   ```
4. **Capture the CONTENTS baseline on the CURRENT server** — this is what §4
   diffs against. Save the helper once; it does the streamable-HTTP handshake
   (`initialize` → `notifications/initialized` → request) over a port-forward,
   so no hostname or in-cluster FQDN appears anywhere:
   ```bash
   mkdir -p /tmp/ncmcp && cat > /tmp/ncmcp/call.sh <<'EOF'
   #!/usr/bin/env bash
   # usage: call.sh <method> '<params-json>'   -> prints the JSON-RPC result body
   set -euo pipefail
   kubectl port-forward -n office svc/nextcloud-mcp 18000:8000 >/dev/null 2>&1 & PF=$!
   trap 'kill $PF 2>/dev/null' EXIT; sleep 2
   H='Content-Type: application/json'; A='Accept: application/json, text/event-stream'
   INIT='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"plan-probe","version":"0"}}}'
   SID=$(curl -s -D - -o /dev/null -X POST http://localhost:18000/mcp -H "$H" -H "$A" -d "$INIT" \
         | tr -d '\r' | awk 'tolower($1)=="mcp-session-id:"{print $2}')
   [ -n "$SID" ] || { echo "no mcp-session-id from initialize" >&2; exit 1; }
   curl -s -o /dev/null -X POST http://localhost:18000/mcp -H "$H" -H "$A" -H "mcp-session-id: $SID" \
        -d '{"jsonrpc":"2.0","method":"notifications/initialized"}'
   curl -s -X POST http://localhost:18000/mcp -H "$H" -H "$A" -H "mcp-session-id: $SID" \
        -d "{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"$1\",\"params\":${2:-{\}}}" \
     | python3 -c 'import sys,json
   raw=sys.stdin.read(); data=[l[5:].strip() for l in raw.splitlines() if l.startswith("data:")]
   print(json.dumps(json.loads(data[-1] if data else raw)))'
   EOF
   chmod +x /tmp/ncmcp/call.sh

   # A) tool surface
   /tmp/ncmcp/call.sh tools/list '{}' \
     | python3 -c 'import sys,json; d=json.load(sys.stdin); [print(t["name"]) for t in d["result"]["tools"]]' \
     | sort > /tmp/ncmcp/tools.before
   wc -l < /tmp/ncmcp/tools.before          # measured 2026-09-15: 96
   # B) calendar set (the 0.185.5 DAV-encoding path)
   /tmp/ncmcp/call.sh tools/call '{"name":"nc_calendar_list_calendars","arguments":{}}' > /tmp/ncmcp/calendars.before
   python3 -c 'import json; d=json.load(open("/tmp/ncmcp/calendars.before")); assert not d["result"].get("isError"), d; print(len(json.dumps(d)))'
   # C) files root (the plain WebDAV path)
   /tmp/ncmcp/call.sh tools/call '{"name":"nc_webdav_list_directory","arguments":{"path":""}}' > /tmp/ncmcp/files.before
   python3 -c 'import json; d=json.load(open("/tmp/ncmcp/files.before")); assert not d["result"].get("isError"), d; print(len(json.dumps(d)))'
   # D) the NEGOTIATED protocol version from `initialize` — the direct evidence for the
   #    §1.4 unpinned-client risk (free to capture; compare in §4.3)
   kubectl port-forward -n office svc/nextcloud-mcp 18000:8000 >/dev/null 2>&1 & PF=$!; sleep 2
   curl -s -X POST http://localhost:18000/mcp -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
     -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"plan-probe","version":"0"}}}' \
     | python3 -c 'import sys,json
   raw=sys.stdin.read(); data=[l[5:].strip() for l in raw.splitlines() if l.startswith("data:")]
   r=json.loads(data[-1] if data else raw)["result"]; print(r["protocolVersion"], r["serverInfo"].get("version"))' | tee /tmp/ncmcp/protocol.before
   kill $PF 2>/dev/null
   ```
   Baseline measured 2026-09-15 on 0.184.5: **96 tools** across the families
   `collectives_*` (20), `nc_calendar_*` (17, incl. `nc_calendar_find_availability`),
   `nc_contacts_*` (8), `nc_mail_*` (13), `nc_news_*` (8), `nc_share_*` (6),
   `nc_webdav_*` (13), `talk_*` (11). No `deck_*`, `notes_*`, `tables_*`,
   `shopping_list_*`. **Re-take A-D on the day of execution**, after any
   Nextcloud server move (nextcloud-34.0.4), so the §4 diff is against the
   true pre-state.
5. **No firing alerts for office/ai** (ignore Watchdog/InfoInhibitor):
   ```bash
   kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &
   curl -s http://localhost:9090/api/v1/alerts | python3 -c "
   import sys, json
   for a in json.load(sys.stdin)['data']['alerts']:
       ln = a['labels']
       if ln.get('namespace') in ('office','ai'):
           print(ln.get('alertname'), ln.get('namespace'), a.get('state'))
   "
   ```
6. **Active-update marker** (SOP §4 step 1) so alert-triage treats rollout
   noise as expected. A full Alertmanager silence is optional here — single
   replica, ~30s roll, tcp probes; `KubePodNotReady` needs 15m to fire:
   ```bash
   runbooks/update-marker.sh add nextcloud-mcp office 2 "0.184.5->0.187.1 image bump"
   ```

## 3. Steps

1. Confirm §2 steps 0–6 are green. Do not proceed on a failed premise.
2. Edit the image tag — one line, the whole diff:
   ```bash
   # BSD sed (macOS) does NOT honour `\s` in a BRE — `\(\s*tag: \)` silently matches nothing
   # and the edit no-ops (dry-tested 2026-09-15). Use the POSIX class:
   sed -i '' 's/^\([[:space:]]*tag: \)0\.184\.5$/\10.187.1/' kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml
   git diff --stat kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml   # expect: 1 file, 1 insertion, 1 deletion — a 0-file diff means the sed did not match: STOP
   git diff kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml | grep -E '^[-+][[:space:]]+tag:'
   # expect exactly:  -              tag: 0.184.5  /  +              tag: 0.187.1
   ```
3. Commit + push — shared worktree, so `--only` with the explicit path:
   ```bash
   cat > /tmp/ncmcp/msg.txt <<'EOF'
   feat(nextcloud-mcp): image 0.184.5 -> 0.187.1

   Crosses three 0.x minor lines (0.185, 0.186, 0.187); at major 0 the minor
   digit is the breaking axis, so every tag's release body was read
   (runbooks/maintenance/plans/nextcloud-mcp-0.187.1.md §1.2). The single
   BREAKING-tagged change (0.185.0: mcp>=2.1 SDK floor, elicitation degrades
   to message_only) affects only the multi-user Login Flow path; this
   deployment runs MCP_DEPLOYMENT_MODE=single_user_basic. Also lands the
   0.185.5 CalDAV URL-encoding fix and 0.187.0's working
   nc_calendar_find_availability. No tool renamed/removed, no schema owned
   (ephemeral /tmp SQLite, no PVC).

   security_ref: F-80459b23
   finding_refs: F-9af9baf7, F-80459b23
   EOF
   git fetch origin main && git merge --ff-only origin/main
   git commit --only kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml -F /tmp/ncmcp/msg.txt
   git show --stat HEAD      # exactly ONE file: the helmrelease. Anything else rode in from the shared index — fix before pushing.
   git push origin main
   ```
4. Let Flux reconcile (`interval: 30m`). Forcing is permitted by the SOP when
   the window needs it sooner:
   ```bash
   flux reconcile kustomization nextcloud-mcp -n office --with-source
   flux reconcile hr -n office nextcloud-mcp
   ```
   No immutable selectors, no PVC, no migration Job — a plain single-replica
   rolling Deployment update (the RWO multi-attach guard does not apply:
   premise 5, no volumes).
5. Watch the roll:
   ```bash
   kubectl rollout status deploy/nextcloud-mcp -n office --timeout=180s
   kubectl get pods -n office -l app.kubernetes.io/name=nextcloud-mcp
   ```

## 4. Verification

1. **Flux Ready on the new revision**:
   ```bash
   kubectl get helmrelease -n office nextcloud-mcp -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} chart={.status.history[0].chartVersion}{"\n"}'
   # expect: True chart=5.1.0
   ```
2. **Pod on the target tag, settled, no traceback on startup**:
   ```bash
   kubectl get deploy -n office nextcloud-mcp -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
   # expect: ghcr.io/cbcoutinho/nextcloud-mcp-server:0.187.1
   kubectl get pods -n office -l app.kubernetes.io/name=nextcloud-mcp     # 1/1 Running, RESTARTS 0 after 2 min
   kubectl logs -n office deploy/nextcloud-mcp --tail=200 | grep -ciE 'traceback|error' ; echo '^ expect 0'
   ```
3. **CONTENTS ASSERTION (surface): the MCP tool set is a superset of the
   pre-bump baseline** — measured by `tools/list` through the real
   streamable-HTTP handshake, compared to `/tmp/ncmcp/tools.before`. A TCP
   probe proves the port is open; this proves the server still registers what
   our agents call.
   ```bash
   /tmp/ncmcp/call.sh tools/list '{}' \
     | python3 -c 'import sys,json; d=json.load(sys.stdin); [print(t["name"]) for t in d["result"]["tools"]]' \
     | sort > /tmp/ncmcp/tools.after
   comm -23 /tmp/ncmcp/tools.before /tmp/ncmcp/tools.after     # tools that DISAPPEARED — expect EMPTY
   comm -13 /tmp/ncmcp/tools.before /tmp/ncmcp/tools.after     # new tools — EXPECT shopping_list_* here (§1.2: upstream does not gate them on app presence)
   wc -l /tmp/ncmcp/tools.after                                # expect > 96 (96 + the shopping_list_* family)
   # negotiated protocol version after the bump — compare to /tmp/ncmcp/protocol.before (§2.4 D);
   # a changed value is the §1.4 risk made visible and goes on F-9af9baf7, whatever §4.5 shows
   kubectl port-forward -n office svc/nextcloud-mcp 18000:8000 >/dev/null 2>&1 & PF=$!; sleep 2
   curl -s -X POST http://localhost:18000/mcp -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
     -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"plan-probe","version":"0"}}}' \
     | python3 -c 'import sys,json
   raw=sys.stdin.read(); data=[l[5:].strip() for l in raw.splitlines() if l.startswith("data:")]
   r=json.loads(data[-1] if data else raw)["result"]; print(r["protocolVersion"], r["serverInfo"].get("version"))' | tee /tmp/ncmcp/protocol.after
   kill $PF 2>/dev/null; diff /tmp/ncmcp/protocol.before /tmp/ncmcp/protocol.after || echo 'protocol/server version changed — record on F-9af9baf7'
   ```
   Also confirm the session log line still names our auth mode after the
   first real session (`initialize` above creates one):
   ```bash
   kubectl logs -n office deploy/nextcloud-mcp --tail=100 | grep -c 'Starting MCP session in single-user BasicAuth mode'; echo '^ expect >= 1'
   ```
4. **CONTENTS ASSERTION (behaviour): the two Nextcloud-facing paths this hop
   touched still return real data** — `nc_calendar_list_calendars` crosses the
   0.185.5 DAV-encoding rewrite, `nc_webdav_list_directory` is the files path
   both consumers use most. Compared to the §2.4 baselines: same calendar set,
   non-empty file listing, `isError` false on both.
   ```bash
   /tmp/ncmcp/call.sh tools/call '{"name":"nc_calendar_list_calendars","arguments":{}}' > /tmp/ncmcp/calendars.after
   /tmp/ncmcp/call.sh tools/call '{"name":"nc_webdav_list_directory","arguments":{"path":""}}' > /tmp/ncmcp/files.after
   python3 - <<'EOF'
   import json,re
   def names(p):
       d=json.load(open(p)); r=d["result"]; assert not r.get("isError"), (p, r)
       txt=" ".join(c.get("text","") for c in r.get("content",[]))
       return txt
   cb, ca = names("/tmp/ncmcp/calendars.before"), names("/tmp/ncmcp/calendars.after")
   fb, fa = names("/tmp/ncmcp/files.before"),     names("/tmp/ncmcp/files.after")
   assert len(ca) > 0 and len(fa) > 0, "empty result after bump"
   # calendar identifiers must all survive the DAV-encoding change
   ids = lambda s: set(re.findall(r'"(?:name|display_name|id|uri)"\s*:\s*"([^"]+)"', s))
   missing = ids(cb) - ids(ca)
   assert not missing, f"calendars missing after bump: {missing}"
   print("calendar ids before/after:", len(ids(cb)), len(ids(ca)), "| files listing bytes before/after:", len(fb), len(fa))
   EOF
   ```
5. **The actual consumer, not just the endpoint** — from the OpenClaw session
   (`ai`), exercise one read through its `nextcloud` MCP entry (list the same
   root folder or the calendars) and confirm real data comes back. This is the
   only assertion that can catch an `mcporter`-side protocol mismatch, since
   its MCP client library is installed unpinned at pod start (§1.4). Attended
   windows: the operator repeats it once from Claude Desktop (`mcp-proxy`), the
   second unpinned client.
6. **No new firing alerts** in `office`/`ai` — re-run §2.5 and diff.
7. **Close out**: `runbooks/update-marker.sh clear nextcloud-mcp`; delete this
   plan file in the same commit series once `executed`. `F-80459b23` and
   `F-9af9baf7` are script-owned and close themselves on the next sweep when
   the tag on the record no longer matches the live image — verify that
   happened rather than assuming it.

## 5. Rollback

Stateless bridge, no data, no owned schema (premises 4–5) — a straight
image-tag revert:

```bash
git revert --no-edit <bump-commit-sha>
git push origin main
flux reconcile kustomization nextcloud-mcp -n office --with-source && flux reconcile hr -n office nextcloud-mcp
kubectl rollout status deploy/nextcloud-mcp -n office --timeout=180s
kubectl get deploy -n office nextcloud-mcp -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
# expect: ghcr.io/cbcoutinho/nextcloud-mcp-server:0.184.5
```

Confirm the cluster is back by re-running §4.3 and §4.4 against the reverted
pod: `tools.after` must equal `tools.before` exactly, and both tool calls must
return the baseline data. Then re-run §4.5 from OpenClaw. If the failure was a
consumer-side protocol mismatch rather than the server, note it on
`F-9af9baf7` (`policy-cli.py finding detail`) — the fix is pinning the client,
not holding the server forever.

## 6. Interference notes

- **Cross-namespace consumer, not a shared-infra token.** OpenClaw (`ai`)
  consumes this server as its `nextcloud` MCP tool
  (`kubernetes/apps/ai/openclaw/app/mcporter-config.yaml`). This plan edits
  nothing in `ai`, but a bad bump makes OpenClaw lose that tool *silently*
  (outbound keeps working; the tool call just fails) — treat any post-bump
  OpenClaw nextcloud-tool failure as belonging to THIS plan, not as `ai`
  noise. Claude Desktop on the operator's Mac is the second consumer; it is
  outside the cluster and needs an attended check (§4.5).
- **`capability_change: true` → attended lane.** Derived class is attended
  regardless (deny-rule reason); the flag documents WHY: an existing tool
  (`nc_calendar_find_availability`) starts doing real work for the agent, and
  new `shopping_list_*` tools WILL register (visible to the agent; calls 404
  until the app is installed). Neither is a reason to hold — both are
  additive — but the operator should know the agent's reach grew.
- **`nextcloud-34.0.4`** (`office`, draft, attended weekend only) — in
  `conflicts_with` since 2026-09-15: it restarts `deployment/nextcloud` and
  moves it 34.0.3 → 34.0.4, and its §2.5 silence is namespace-wide. Never
  the same slot: a Nextcloud restart mid-§4.4 makes a calendar-list failure
  unattributable, and the silence would mask this rollout's noise. Different
  slots of one weekend are fine in either order — it is a MINOR hop held by
  the `*nextcloud-mcp*` `max: patch` deny rule (PLAN lane, HUMAN-GATED), so
  it never rides Step 0 either. **Re-take the §2.4 baselines (A-D) the same
  day as execution, after any server move**, so the §4 diff is against the
  true pre-state; the `nextcloud-server-unchanged` premise tolerates the
  patch digit for exactly this reason.
- **`bitnamilegacy-exit-nextcloud-db`** (`office`, `blocked`, unwindowed)
  restarts `deployment/nextcloud` when revived. If both are ever live in one
  window, add it to `conflicts_with` and run this (lighter, stateless) bump
  FIRST, then verify §4.4 again after the DB work — same reasoning.
- **Flux `dependsOn: nextcloud`** is ordering-only (namespace/reconcile-first);
  confirmed not a version coupling by reading every release body in range.
- **Window fit (2026-09-15 queue):** `sat-attended:2026-09-19` carries
  45min/low, `sun-attended:2026-09-20` carries 60min/low — this 30min/medium
  fits either with margin. Never `nightly`: the deny rule's reason is explicit
  and this plan narrows *why* for this hop, it does not overturn it.
- Nothing here touches Longhorn, cert-manager, cilium, coredns, or any other
  route on `envoy-internal` — safe alongside unrelated `office`/`ai` work that
  does not share a resource listed in `touches`.

## What I could not verify

- **Client MCP library versions** for `mcporter` (OpenClaw) and `mcp-proxy`
  (Claude Desktop) — both installed unpinned at launch. §4.3–4.5 are written
  to catch the effect empirically because it cannot be proven ahead of time;
  the negotiated `protocolVersion` captured in §2.4 D / §4.3 is the one
  server-side number that makes a client-side break attributable.

(Two earlier items here — whether `shopping_list_*` registers with the app
absent, and whether `nc_calendar_find_availability` was a stub on 0.184.5 —
were settled from upstream source in the 2026-09-15 review and moved into
§1.2: it registers regardless; it was a stub at `client/calendar.py:2918`.)
