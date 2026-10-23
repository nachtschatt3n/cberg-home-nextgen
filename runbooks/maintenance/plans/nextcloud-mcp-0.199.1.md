---
plan_id: nextcloud-mcp-0.199.1
component: nextcloud-mcp
pr: null                              # no Renovate PR; held by the `*nextcloud-mcp*` `max: patch` deny rule
                                      # (runbooks/auto-update-policy.yaml:325) via coverage.py's PLAN lane
kind: image
current: "0.184.5"
target: "0.199.1"                     # Verified 2026-10-09: GHCR 0.199.1 index digest sha256:42f45f0e… is
                                      # IDENTICAL to `latest`; 0.199.2 and 0.200.0 404; GitHub v0.199.1 is Latest,
                                      # not a pre-release (published 2026-10-08T07:26Z). Upstream `master` has had
                                      # only a submodule bump since (944d7410).
update_type: minor                    # semver label only. At major 0 the MINOR digit is the breaking axis, and this
                                      # hop crosses FIFTEEN minor lines (0.185 .. 0.199). 0.185..0.198.3 were read
                                      # tag-by-tag in the two predecessor plans (carried in §1.3). 0.198.4..0.199.1
                                      # are read here (§1.2).
risk: medium                          # stateless bridge with a cheap tag rollback, BUT the 0.195.5 calendar regression
                                      # is STILL present in 0.199.1 (§1.2), so the EXPECTED outcome today is a STOP
                                      # at §2.7. Not raised to high because nothing here is forward-only and the
                                      # failure is caught before the commit.
est_duration_min: 40                  # same gate set as nextcloud-mcp-0.198.0 + two short 0.199.0 packaging gates
needs_reboot: false
touches:
  namespaces: [office]
  resources:
    - helmrelease/nextcloud-mcp
    - deployment/nextcloud-mcp
                                      # httproute/nextcloud-mcp (envoy-internal/https) re-renders from the same HR,
                                      # but its spec does not change (the image tag is the whole diff), so it is not perturbed.
  shared: [monitoring]                # READ-only: §2.5/§4.9/§4.10 read Prometheus (the window's instrument). No
                                      # gateway, CNI, DNS, storage or shared DB is perturbed. Cross-namespace
                                      # CONSUMERS (ai/openclaw, Claude Desktop) are blast radius, not shared infra (§6).
depends_on: []                        # Flux `dependsOn: nextcloud` is ordering-only; no release note in range states
                                      # a minimum Nextcloud server version (0.199.0's oidc-2.5 note is OAuth-only).
conflicts_with:
  - app-template-5.2.1                # awaiting-go nightly:2026-10-09. Its Batch A sed edits THIS helmrelease.yaml
                                      # (chart 5.1.0 -> 5.2.1, line 12) and re-renders this Deployment; a same-night
                                      # run makes §4.2's roll unattributable. Its list names nextcloud-mcp-0.198.0;
                                      # re-pointing that to this id is coordinator bookkeeping (§1.5).
  - nextcloud-fleet-35.0.1            # sun-attended:2026-10-18. Nextcloud 34 -> 35 MAJOR; §4.5/§4.6 read CalDAV
                                      # from that server. After it runs, premise 2 fails closed and this plan must be re-vetted.
  - redis-fleet-8.10.2                # sun-attended:2026-10-25. Restarts office/nextcloud-redis (logs every user out);
                                      # every §4 gate is a live call into Nextcloud.
  - bitnamilegacy-exit-nextcloud-db   # blocked/unwindowed; restarts deployment/nextcloud if it is revived.
  - nextcloud-mcp-0.198.0             # same component, same HR line, blocked. This plan SUPERSEDES it (§1.5). The entry
                                      # binds nothing once that file is set `superseded` (terminal); drop it then.
                                      # (kube-prometheus-stack-91.9.0 was executed + retired 3da2a100; no kps plan open.)
exclusive: false
security_ref: F-80459b23              # The record is about the live 0.184.5 image and names a newer upstream tag as the
                                      # remedy. The dispatch reason was the 0.x minor move, not security, but the
                                      # finding is answered by this bump. Detail stays on the record (§1.4).
capability_change: true               # vs the LIVE 0.184.5: +21 tools (4 of them WRITE), behaviour changes on live tools
                                      # (0.192.0 bulk-ops series default, 0.188.1 contacts photo opt-in, 0.187.0 real
                                      # find_availability, 0.199.1 fixed-offset datetimes stored as UTC) and the 0.195.5
                                      # calendar-addressing change (§1.2).
rollback_class: git-revert            # no PVC, no volumes, no DATABASE_URL/TOKEN_STORAGE_DB (premises 4+5). Executed
                                      # as an inverse tag edit (§5), because `git revert` refuses in the shared worktree.
finding_refs: [F-9af9baf7, F-80459b23] # F-9af9baf7 = the version finding (title names 0.198.5 as of 2026-10-07; target
                                      # moves to 0.199.1 on the next sweep). F-80459b23 = the security finding. Both are
                                      # also on nextcloud-mcp-0.198.0 (blocked) until it is superseded.
review: null
status: superseded                        # Coordinator: the §2.7 STOP still fires (7A=2, 7B count=1 at v0.199.1, measured
                                      # 2026-10-09). Not schedulable until the operator picks §1.6 A/B/C; consider
                                      # setting `blocked` with that reason when this file is reviewed.
window: null   # SUPERSEDED 2026-10-23 by nextcloud-mcp-0.200.2 (one plan per target); blocked together with it on the upstream calendar regression
premises:
  - id: image-is-still-0.184.5
    why: >-
      `current:` and the rollback target are 0.184.5. If the cluster has moved,
      the diff, the baselines and the rollback digest are wrong.
    run: kubectl get deploy -n office nextcloud-mcp -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: ghcr.io/cbcoutinho/nextcloud-mcp-server:0.184.5
  - id: nextcloud-server-still-34
    why: >-
      §4.5/§4.6 read CalDAV from this server, and the §1.2 regression analysis was
      measured against 34.0.4. Patch drift is tolerated. If nextcloud-fleet-35.0.1
      (a MAJOR) moves first, this fails closed and forces a re-vet.
    run: kubectl get deploy -n office nextcloud -o jsonpath='{.spec.template.spec.containers[?(@.name=="nextcloud")].image}'
    expect_matches: 'docker\.io/nextcloud:34\.0\.[0-9]+$'
  - id: deployment-mode-still-single-user-basic
    why: >-
      The 0.185.0 elicitation break, the 0.190.0/0.198.1 CIMD/OAuth changes, the
      0.197.0 SAR scopes and the 0.199.0 oidc-2.5 client-auth change all fire only
      on the OAuth / multi-user path. single_user_basic makes them inert; any other
      mode voids §1.2/§1.3.
    run: kubectl get secret -n office nextcloud-mcp-config -o json | jq -r '.data.MCP_DEPLOYMENT_MODE' | jq -Rr '@base64d'
    expect_exact: single_user_basic
  - id: exactly-four-config-keys
    why: >-
      This premise proves five things. (a) There is no DATABASE_URL/TOKEN_STORAGE_DB, so
      rollback is free. (b) There is no VECTOR_SYNC_ENABLED/ENABLE_SEMANTIC_SEARCH,
      EMBEDDING_GATEWAY_URL or SAR_ENABLED, so the 0.196.0 indexing BREAKING, the
      0.197.0/0.198.0 SAR surface, the 0.199.0 SAR plugin
      (`features.sar_available` requires sar_enabled AND vector sync AND a
      gateway) and the 0.199.0 semantic-extra startup check
      (`config_validators.py`, fires only with vector sync on) stay off.
      (c) There is no CIMD_ALLOWED_HOSTS. (d) There is no COLLABORA_URL / DOCLING_API_URL.
      (e) There is no LOGIN_FLOW_OIDC_* key, which is only for the 0.199.0 docker-compose login-flow
      service.
    run: kubectl get secret -n office nextcloud-mcp-config -o go-template='{{range $k,$v := .data}}{{$k}},{{end}}'
    expect_exact: MCP_DEPLOYMENT_MODE,NEXTCLOUD_HOST,NEXTCLOUD_PASSWORD,NEXTCLOUD_USERNAME,
  - id: no-volumes-on-the-pod
    why: >-
      This is the second half of the stateless claim: there is nothing to snapshot,
      and no RWO multi-attach guard is needed.
    run: kubectl get deploy -n office nextcloud-mcp -o json | jq -r '.spec.template.spec.volumes'
    expect_exact: "null"
  - id: helmrelease-chart-5.1-or-5.2.1
    why: >-
      Verification assumes the app-template render (tcp probes, container name
      `main`). app-template-5.2.1 bumps this HR's chart label-only, so both versions are
      accepted. Any other chart version means an unreviewed render change.
    run: kubectl get helmrelease -n office nextcloud-mcp -o jsonpath='{.status.history[0].chartVersion}'
    expect_matches: '^5\.(1\.0|2\.1)$'
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/auto-update.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-10-09"
---

## 1. Summary & why held

`kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml:34` pins
`ghcr.io/cbcoutinho/nextcloud-mcp-server` at `0.184.5`. Upstream head is
`0.199.1`. coverage.py holds it because this is a 0.x release-line move (0.184 -> 0.199),
and at major 0 the minor version is the breaking axis. The `*nextcloud-mcp*` deny rule
(`max: patch`) requires a human read of every minor hop. Sweep cycle
`7bedb113-3001-474e-99c3-3c8ca135cdbc` dispatched this id.

**Verdict: STILL DO NOT RUN AS-IS. The 0.195.5 calendar-addressing regression that
blocked `nextcloud-mcp-0.198.0` is unchanged in 0.199.1.**

- `_get_calendar_url()` still builds `encode_dav_url(f"{home}{unquote(calendar_name)}/")`.
  That is `client/calendar.py:582` at v0.199.1; it was line 568 at v0.198.3. The function body is
  identical, and `master` == v0.199.1 for this file (sha256 `d9cbf3f9…`).
- Two of the four calendars the MCP user owns still have a literal `%` in their
  Nextcloud URI. Re-measured live 2026-10-09 with `occ dav:list-calendars`: 4 calendars, 2 with a `%`-URI.
- No upstream issue exists for this case. Searched 2026-10-09 for "percent calendar" and
  "unquote"; the only hits are the closed issues #1449 and #776, which are unrelated.

So §2.7 (the hard STOP gate) still fails on both legs today: 7A=2 and 7B count=1 at v0.199.1
(dry-run 2026-10-09). **The operator decision in §1.6 is still open.** Neither
the window agent nor this planner can make it. Everything else in 0.198.4 to 0.199.1
was read and is inert or additive for this deployment (§1.2).

The 0.199.1 calendar fix ("store fixed-offset datetimes as UTC") is a write-path
correctness fix. It does NOT touch `_get_calendar_url`, and it does not help the read regression.

### 1.1 Registry verification (2026-10-09; re-run at §2.0)

| tag | GHCR (anonymous token, OCI index) |
|---|---|
| `0.184.5` (live) | 200, running pod `imageID` `sha256:f6d8839722587f2cd37ec5218a18479f9e313be9904ad4f6bbb36f98bc827065` |
| `0.195.4` (last tag WITHOUT the regression; option B) | 200, `sha256:24417dcb804fc65bcb8712226bf70be71018aefd2ec7b27e9392a4d4e1ed707c` |
| `0.198.3` (0.198.0 plan's target) | 200, `sha256:b7faa131d1c4c4dbb1da7c24ccd96d35dcb41ad6f0ac6bcd5abd69282b8cd4b8` |
| `0.199.0` | 200, `sha256:f8f0e8a8276b6f8d114aac440b030eccacb55a0226e793155e80e52852931918` |
| **`0.199.1` (target)** | **200, `sha256:42f45f0ebc368b47b0b8f29249bebf347960831f5819aba70b607c2c62b928c3`** |
| `latest` | 200, identical to 0.199.1 |
| `0.199.2`, `0.200.0` | 404 |

GitHub releases in the new range: v0.198.4 (2026-10-06T06:35Z), v0.198.5
(10-06T17:09Z), v0.199.0 (10-08T06:27Z), v0.199.1 (10-08T07:26Z, Latest). None
is a pre-release. 0.199.1 clears the 48 h `minimum_release_age_hours` gate at
2026-10-10T07:26Z. The line still ships several tags a week, so re-run §2.0 on the day.

### 1.2 What changed 0.198.3 -> 0.199.1, read per tag + source diff

Sources: `gh release view` bodies, and `git diff v0.198.3 v0.199.1` (83 commits, 47 files excl. tests).
`uv.lock`: **`mcp` stays 2.1.1**. Dockerfile: base `python:3.14-slim-trixie` digest bump,
`uv` 0.12.19 -> 0.12.22, and both `uv sync` lines gain `--extra semantic`. Entrypoint
unchanged (`/opt/venv/bin/nextcloud-mcp-server run --host 0.0.0.0`). `client/contacts.py`
is byte-identical (sha256 `2b71e900…`). Under `server/`, only `webdav.py` (no tool
added/renamed/removed: no `async def`/`@mcp.tool` line in the diff), `__init__.py`
(drops the eager `configure_semantic_tools` import) and `sar.py` (plugin-gated) change.
The `@mcp.tool` count across `server/` is 197 at both tags.

| tag | class | what it says | applies to us? |
|---|---|---|---|
| 0.198.4 | fix (webdav) | *"strip the -zstd content-coding suffix from etags"*: `_normalize_etag` adds `-zstd` to the suffix list. | Benign. Our MCP talks to the Nextcloud Service directly. A `-zstd` etag would only appear behind a zstd-compressing front end, and the change is strip-only. |
| 0.198.5 | fix (sar) | Renders failed SAR index rows; blank per-document export reason allowed. | **Inert** (SAR off, premise 4). |
| **0.199.0** | **BREAKING** | *"the semantic-search dependencies are no longer installed by default. Deployments using ENABLE_SEMANTIC_SEARCH / VECTOR_SYNC_ENABLED from PyPI must install `nextcloud-mcp-server[semantic]`. **The Docker image is unaffected.**"* Also: SAR moves to a plugin entry point (`sar_plugin.py`); PDF/Office parsing moves to a `documents` extra; *"auth: work with Nextcloud oidc 2.5's stricter client auth and resource policy"*. | **Inert, verified in source.** (1) The Dockerfile at v0.199.1 runs `uv sync … --extra semantic --extra postgres --extra observability`, and `semantic` includes `nextcloud-mcp-server[documents]` (pyproject.toml). So pymupdf/pypdfium2/python-docx etc. are still in the image, and `nc_webdav_read_file` keeps parsing PDFs/Office instead of returning them raw with the new *"Install it with: pip install 'nextcloud-mcp-server[documents]'"* note. §4.12 asserts this in-pod. (2) The SAR plugin's `available` = `features.sar_available`, which is False without SAR_ENABLED + vector sync + gateway. `register_plugin_tools` (app.py:1914) then logs `Plugin sar: not available, skipping` and registers nothing. (3) The oidc-2.5 change is in `auth/unified_verifier.py` / `browser_oauth_routes.py`, which are OAuth-only. (4) The new semantic-extra startup check (`config_validators.py`) fires only with vector sync on. |
| 0.199.1 | fix (calendar) | *"anchor UNTIL on the caller's offset; store absolute TRIGGER as UTC"*, *"store fixed-offset datetimes as UTC"* | **Behaviour change on the WRITE path only.** A create/update with a fixed-offset start (`…+02:00`) is now stored as a UTC `DTSTART` instead of an unresolvable `TZID="UTC+02:00"`. Named-timezone input is unchanged. This is an improvement for clients that read our calendars. Not exercised here: no writes are made against household calendars. Does NOT touch `_get_calendar_url`. |

**Tool surface is unchanged versus 0.195.4 and 0.198.3.** 0.195.4's surface was measured live
at **117** (96 + the exact 21 names in §4.4) during the 2026-09-26 attempt.
§4.4 still expects 117.

### 1.3 0.184.5 -> 0.198.3, carried from the predecessors

The full evidence is in `nextcloud-mcp-0.187.1` §1.2/§1.6 (0.185..0.195.4) and
`nextcloud-mcp-0.198.0` §1.2 (0.195.5..0.198.3). Condensed:

- **0.185.0 BREAKING**: mcp SDK 1.29 -> 2.x and elicitation -> message_only. Inert in
  single_user_basic. Base python 3.12 -> 3.14. The lifespan now runs once per
  container start (§4.3).
- **0.192.0 BREAKING**: `nc_calendar_bulk_operations` leaves recurring series alone
  unless `apply_to_series=true`. This is a safer default (§4.7).
- **0.194.0 BREAKING**: parsing_metadata key rename. Inert (captioning off).
- **0.195.5 (REGRESSION ON OUR DATA)**: `_get_calendar_url` now runs `unquote()` on the calendar name
  before encoding. Upstream's code comment says *"Nextcloud calendar URIs never contain a literal `%`, so
  the unquote is lossless in practice"*. That is false for 2 of our 4 calendars. Reads come back
  **EMPTY WITHOUT AN ERROR**. This was emulated live on 0.184.5 on 2026-09-29: the busiest calendar read
  `200 -> 0`, `isError=false`. Writes target the same wrong URI.
- **0.196.0 / 0.197.0 / 0.198.0 BREAKING** (vector-sync indexing, SAR scopes,
  `SAR_ENABLED`): inert (premise 4).
- 0.186.0: 12 `nc_shopping_list_*` tools (they register; the app is absent, so calls 404). 0.188.0/0.189.0:
  9 `nc_webdav_*` tag/trash/version tools (4 WRITE). 0.188.1: contacts photo
  opt-in + paging (§4.8). 0.187.0: real `find_availability`. 0.198.1/0.198.2/0.198.3:
  CIMD, vector-sync discovery and Postgres-engine fixes, all inert.
- Consumer config: OpenClaw's `NEXTCLOUD_MCP_URL` ends in `/mcp` (fixed `ec432f12`),
  and the §4.11 `case` guard refuses anything else.

### 1.4 Security driver

> **Security driver: detail withheld from this public repo.**
> Tracked as **F-80459b23** (`security`). Quote the contextual tier from the sweep board, not the raw scanner severity.
> - Dashboard: `https://sweep.<DOMAIN>/findings/F-80459b23`
> - CLI: `runbooks/policy-cli.py finding show F-80459b23`

`F-f02df447` (`[AR-029]`, accepted) is the residual base-OS tally on the same
image. It is expected to change, not to clear. Whether 0.195.4 (option B) and 0.199.1
remediate the F-80459b23 set is a per-tag scan question. The answer goes on the
record (`policy-cli.py finding detail F-80459b23`), never into this file.

### 1.5 Relationship to the older plans: this plan SUPERSEDES both

- **`nextcloud-mcp-0.198.0` (status `blocked`)**: superseded by this file. The README
  default is "refresh in place, keep the plan_id". The orchestrator dispatched a new id
  instead, so the README's carry-across rule applies by hand. Carried here:
  `finding_refs` (F-9af9baf7, F-80459b23), `security_ref`, the §1.6 decision, all
  gates, and the conflict set (minus the executed kube-prometheus-stack-91.9.0).
- **`nextcloud-mcp-0.187.1` (status `superseded` since 2026-10-01)**: stays superseded.
  It is the vehicle for option B (§1.6) and would need re-opening for that.
- **Owed by the coordinator. This planner writes only this file and edits neither old plan.**
  1. Set `nextcloud-mcp-0.198.0` to `status: superseded` with a pointer here, then
     drop it from this file's `conflicts_with`.
  2. Re-point `app-template-5.2.1`'s `conflicts_with` entry `nextcloud-mcp-0.198.0`
     to `nextcloud-mcp-0.199.1`. Add the reciprocal entry for this id to `nextcloud-fleet-35.0.1`,
     `redis-fleet-8.10.2` and `bitnamilegacy-exit-nextcloud-db` if they carry
     the old id. `maintenance-plan.py --validate` raises DEAD-REF only on deletion, not on supersession.
  3. Re-key the home-operation `go_no_go` issue for nextcloud-mcp to this id. This was
     already owed by the 0.198.0 plan (§1.5 there) and has not been done.

### 1.6 The operator decision this plan cannot make (unchanged from 0.198.0, re-checked 2026-10-09)

| option | what | cost |
|---|---|---|
| **A. Wait for upstream** (recommended default) | **Prerequisite: FILE the upstream issue.** None exists (re-searched 2026-10-09), so "wait" has no end without it. Issue text: *"`_get_calendar_url` unquotes calendar names; Nextcloud calendar URIs CAN contain a literal `%` (created by CalDAV clients that percent-encode the URI); reads silently return empty."* Retarget this plan to the first tag whose `_get_calendar_url` no longer unquotes blindly. §2.7 B detects that. | Security finding stays open until then. |
| **B. Take 0.195.4 now** | Revive `nextcloud-mcp-0.187.1` (its blocker is cleared). Add this plan's §4.6 event gate to it, and park this file. | Worth it only if 0.195.4 actually remediates F-80459b23 (§1.4). The next hop is again a minor-line plan. |
| **C. Change the data** | Recreate the two `%`-URI calendars with clean URIs in Nextcloud, then run this plan (§2.7 A passes). | The URI changes, which breaks every CalDAV client syncing those calendars and may lose share/subscription state. This is data surgery, so operator only. |
| D. Accept | Run 0.199.1 and accept that MCP consumers read 0 events from the household's busiest calendar. | Feature loss. Operator policy is "interruption OK, data/feature loss not". Not recommended. |

## 2. Pre-checks

0. **Target is still upstream head** (manual; premises have no network verb):
   ```bash
   TOKEN=$(curl -s "https://ghcr.io/token?scope=repository:cbcoutinho/nextcloud-mcp-server:pull&service=ghcr.io" \
     | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
   for t in 0.199.1 latest 0.199.2 0.200.0; do
     printf '%-8s ' "$t"
     curl -sI -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.oci.image.index.v1+json" \
       "https://ghcr.io/v2/cbcoutinho/nextcloud-mcp-server/manifests/$t" \
       | tr -d '\r' | awk 'NR==1{printf "%s ",$2} tolower($1)=="docker-content-digest:"{print $2}'; echo
   done
   # expect: 0.199.1 200 sha256:42f45f0ebc368b47b0b8f29249bebf347960831f5819aba70b607c2c62b928c3;
   #         latest 200 SAME digest; 0.199.2 404; 0.200.0 404.  (measured 2026-10-09)
   # A newer tag -> STOP: read its release body + run §2.7 B against it before retargeting (refresh THIS file in place).
   ```
1. **Premises** (six, fail-closed):
   ```bash
   python3 runbooks/plan-premises.py nextcloud-mcp-0.199.1 --require-premises
   ```
2. **Health floor**:
   ```bash
   flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
   flux get helmreleases -A   | awk 'NR==1 || $5 != "True"'
   kubectl get pods -n office -l app.kubernetes.io/name=nextcloud-mcp        # expect 1/1 Running (live 2026-10-09: nextcloud-mcp-55ff568864-4z4rl, restarts=0)
   kubectl get helmrelease -n office nextcloud-mcp -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'   # expect True
   ```
3. **Nextcloud apps behind the tool families** (a change here changes §4.4's "works vs 404s"):
   ```bash
   kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c 'php occ app:list' \
     | grep -iE '^[[:space:]]*- (calendar|contacts|deck|notes|tables|shoppinglist|mail|spreed|collectives|news|cookbook|files_versions|files_trashbin|systemtags):'
   # measured 2026-09-22: calendar, contacts, mail, spreed, files_trashbin, files_versions, systemtags;
   # NO deck/notes/tables/shoppinglist/cookbook/collectives/news
   ```
4. **CONTENTS baseline on the CURRENT server** (0.184.5). Everything writes to `/tmp/ncmcp/` (fixed paths; no shell variable crosses blocks):
   ```bash
   mkdir -p /tmp/ncmcp && cat > /tmp/ncmcp/call.sh <<'EOF'
   #!/usr/bin/env bash
   # usage: call.sh <method> '<params-json>'   -> prints the JSON-RPC result body (streamable-HTTP handshake)
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
        -d "{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"$1\",\"params\":${2:-"{}"}}" \
     | python3 -c 'import sys,json
   raw=sys.stdin.read(); data=[l[5:].strip() for l in raw.splitlines() if l.startswith("data:")]
   print(json.dumps(json.loads(data[-1] if data else raw)))'
   EOF
   chmod +x /tmp/ncmcp/call.sh

   # A) tool surface
   /tmp/ncmcp/call.sh tools/list '{}' > /tmp/ncmcp/tools_list.before.json
   python3 -c 'import json; d=json.load(open("/tmp/ncmcp/tools_list.before.json")); [print(t["name"]) for t in d["result"]["tools"]]' | sort > /tmp/ncmcp/tools.before
   wc -l < /tmp/ncmcp/tools.before                       # measured 2026-09-29: 96
   # B) calendar list, C) files root, D) addressbooks
   /tmp/ncmcp/call.sh tools/call '{"name":"nc_calendar_list_calendars","arguments":{}}' > /tmp/ncmcp/calendars.before
   /tmp/ncmcp/call.sh tools/call '{"name":"nc_webdav_list_directory","arguments":{"path":""}}' > /tmp/ncmcp/files.before
   /tmp/ncmcp/call.sh tools/call '{"name":"nc_contacts_list_addressbooks","arguments":{}}' > /tmp/ncmcp/addressbooks.before
   for f in calendars files addressbooks; do python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); assert not d["result"].get("isError"), d; print(sys.argv[1], "ok")' /tmp/ncmcp/$f.before; done
   # E) negotiated protocol + serverInfo
   kubectl port-forward -n office svc/nextcloud-mcp 18000:8000 >/dev/null 2>&1 & PF=$!; sleep 2
   curl -s -X POST http://localhost:18000/mcp -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
     -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"plan-probe","version":"0"}}}' \
     | python3 -c 'import sys,json
   raw=sys.stdin.read(); data=[l[5:].strip() for l in raw.splitlines() if l.startswith("data:")]
   r=json.loads(data[-1] if data else raw)["result"]; print(r["protocolVersion"], r["serverInfo"].get("version"))' | tee /tmp/ncmcp/protocol.before
   kill $PF 2>/dev/null                                  # 0.184.5: "2025-06-18 1.29.0"
   ```
   **F) Per-calendar EVENT reads (the §1.2 regression lives here).** For each calendar, call `nc_calendar_list_events` with the `name` the server itself returned, which is what a consumer does. Use a fixed 2015-01-01..2030-12-31 range, limit 200:
   ```bash
   cat > /tmp/ncmcp/events.py <<'EOF'
   # usage: events.py <calendars.json> <out.json> [--emulate-double-decode]
   import json, subprocess, sys
   from urllib.parse import unquote
   def full_unquote(s):
       for _ in range(8):
           n = unquote(s)
           if n == s: return s
           s = n
       raise SystemExit(f"unquote did not converge: {s!r}")
   src, out = sys.argv[1], sys.argv[2]
   emulate = "--emulate-double-decode" in sys.argv[3:]
   r = json.load(open(src))["result"]; assert not r.get("isError"), r
   sc = r.get("structuredContent") or json.loads(" ".join(c.get("text", "") for c in r.get("content", [])))
   cals = sc["calendars"]; assert cals, "no calendars"
   res = {}
   for c in cals:
       name = unquote(unquote(c["name"])) if emulate else c["name"]
       args = json.dumps({"name": "nc_calendar_list_events", "arguments": {"calendar_name": name,
               "start_date": "2015-01-01", "end_date": "2030-12-31", "limit": 200}})
       p = subprocess.run(["/tmp/ncmcp/call.sh", "tools/call", args], capture_output=True, text=True, check=True)
       rr = json.loads(p.stdout)["result"]
       txt = " ".join(x.get("text", "") for x in rr.get("content", []))
       body = rr.get("structuredContent") or json.loads(txt)
       assert not rr.get("isError"), (c["href"], txt[:200])
       res[full_unquote(c["href"])] = {"total_found": int(body["total_found"]),
                                       "pct_uri": "%" in unquote(c["href"].rstrip("/").split("/")[-1])}
   json.dump(res, open(out, "w"), indent=1)
   print(f"{len(res)} calendars; pct-URI calendars={sum(v['pct_uri'] for v in res.values())}; per-calendar counts={[v['total_found'] for v in res.values()]}")
   EOF
   cat > /tmp/ncmcp/events_gate.py <<'EOF'
   # usage: events_gate.py <events.before.json> <events.after.json>
   import json, sys
   b, a = (json.load(open(p)) for p in sys.argv[1:3])
   assert b and set(b) == set(a), f"calendar key sets differ: missing={sorted(set(b)-set(a))} added={sorted(set(a)-set(b))}"
   bad = []
   for k, v in b.items():
       nb, na = v["total_found"], a[k]["total_found"]
       if nb > 0 and na == 0: bad.append(f"calendar #{sorted(b).index(k)+1} (pct_uri={v['pct_uri']}): {nb} -> 0 events (SILENT EMPTY READ)")
       elif abs(na - nb) > 2: bad.append(f"calendar #{sorted(b).index(k)+1} (pct_uri={v['pct_uri']}): {nb} -> {na} events")
   assert not bad, "per-calendar event reads regressed: " + "; ".join(bad)
   print("per-calendar event counts before/after:", [(v["total_found"], a[k]["total_found"]) for k, v in sorted(b.items())], "PASS")
   EOF
   python3 /tmp/ncmcp/events.py /tmp/ncmcp/calendars.before /tmp/ncmcp/events.before.json
   # measured 2026-09-29 on 0.184.5: 4 calendars; pct-URI calendars=2; per-calendar counts=[3, 0, 200, 0]
   ```
   Re-take A-F on the day, and again after any Nextcloud server move.
5. **No firing alerts in office/ai**:
   ```bash
   kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 >/dev/null 2>&1 & PF=$!; sleep 2
   curl -s --data-urlencode 'query=ALERTS{namespace=~"office|ai",alertstate="firing"}' http://localhost:9090/api/v1/query \
     | python3 -c "import sys,json; r=json.load(sys.stdin)['data']['result']; n=sorted(x['metric'].get('alertname') for x in r if x['metric'].get('alertname') not in ('Watchdog','InfoInhibitor')); print(n or 'NONE FIRING')" | tee /tmp/ncmcp/alerts.before
   kill $PF 2>/dev/null
   # CAN FAIL (2026-09-26): count_over_time of this selector over 30d returned KubeJobFailed/MealiePodRestarted.
   ```
6. **Active-update marker**:
   ```bash
   runbooks/update-marker.sh add nextcloud-mcp office 2 "0.184.5->0.199.1 image bump"
   ```
7. **HARD STOP GATE: the 0.195.5 calendar-addressing regression (§1.2).** Proceed only if A or B passes:
   ```bash
   # A) data side: does any owned calendar still have a literal '%' in its URI?  (from §2.4 F)
   python3 -c 'import json; d=json.load(open("/tmp/ncmcp/events.before.json")); n=sum(v["pct_uri"] for v in d.values()); print("pct-URI calendars:", n); raise SystemExit(0 if n==0 else 1)' \
     && echo "7A PASS" || echo "7A FAIL"
   # B) code side: does the TARGET tag still unquote the name before encoding?
   #    Fetch to a file and FAIL CLOSED: a failed fetch (bad ref, rate limit, 404 body) must never read as "0 matches".
   REF=v0.199.1; F=/tmp/ncmcp/calendar.py.$REF; rm -f "$F"
   if ! gh api "repos/cbcoutinho/nextcloud-mcp-server/contents/nextcloud_mcp_server/client/calendar.py?ref=$REF" \
        -H 'Accept: application/vnd.github.raw' > "$F"; then echo "7B FAIL ($REF): fetch failed -- gate NOT evaluated"
   elif ! grep -q 'def _get_calendar_url' "$F"; then echo "7B FAIL ($REF): _get_calendar_url absent -- file moved/renamed, re-read by hand"
   elif [ "$(grep -c 'unquote(calendar_name)' "$F")" -eq 0 ]; then echo "7B PASS ($REF): unquote(calendar_name) count=0 -- re-read the new _get_calendar_url, then still run §4.6"
   else echo "7B FAIL ($REF): unquote(calendar_name) count=$(grep -c 'unquote(calendar_name)' "$F")"; fi
   # measured 2026-10-09: 7A FAIL (live occ dav:list-calendars: 4 calendars, 2 with '%' in the URI);
   #   7B FAIL (v0.199.1): count=1 and 7B FAIL (master): count=1 -- calendar.py:582.
   #   History: PASS at v0.195.4 (count 0); FAIL at v0.198.0/.1/.3; REF=main -> fetch failed (default branch is `master`).
   # BOTH FAIL -> STOP. Do not commit. Clear the marker (runbooks/update-marker.sh clear nextcloud-mcp)
   #   and return the plan to the operator with §1.6. This is the expected outcome today.
   ```
   *The gate can fail AND pass:* 7A read 2 on live data (2026-09-29, re-measured 2026-10-09). 7B
   prints PASS at v0.195.4 (count 0), FAIL at v0.199.1/master (count 1), and fails closed on a
   non-existent ref. Read the printed `7A`/`7B` verdict lines. There is no other output to interpret.

## 3. Steps

1. §2.0-2.7 green. In practice that means §2.7 passed via A or B. Otherwise stop here.
2. Edit the tag (BSD-sed safe, POSIX class). Dry-tested 2026-10-09 on a scratch copy with macOS BSD sed: `34c34 <               tag: 0.184.5 / >               tag: 0.199.1`, one hunk. The inverse (§5) restores the file byte-identical (`cmp` clean):
   ```bash
   cd /Users/mu/code/cberg-home-nextgen || exit 1
   sed -i '' 's/^\([[:space:]]*tag: \)0\.184\.5$/\10.199.1/' kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml
   git diff --stat -- kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml    # expect 1 file, 1+/1-; 0 files = no-op: STOP
   git diff -- kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml | grep -E '^[-+][[:space:]]+tag:'
   # expect exactly:  -              tag: 0.184.5   /   +              tag: 0.199.1
   ```
3. Commit + push (shared worktree: use `--only` and verify the subject):
   ```bash
   cat > /tmp/ncmcp/msg-nextcloud-mcp-0.199.1.txt <<'EOF'
   feat(nextcloud-mcp): image 0.184.5 -> 0.199.1

   Crosses fifteen 0.x minor lines (0.185 .. 0.199). Release bodies and
   source diffs read per tag (runbooks/maintenance/plans/nextcloud-mcp-0.199.1.md
   section 1). BREAKING tags 0.185.0/0.194.0/0.196.0/0.197.0/0.198.0/0.199.0
   are inert for single_user_basic with no vector sync/SAR; the 0.199.0
   semantic/documents extras are still installed in the Docker image.
   0.192.0 adds apply_to_series (safer default); 0.199.1 stores fixed-offset
   datetimes as UTC. 21 new tools, no tool removed, mcp 2.1.1, python 3.14.
   The 0.195.5 calendar-addressing gate (section 2.7) passed before this commit.

   security_ref: F-80459b23
   finding_refs: F-9af9baf7, F-80459b23
   EOF
   git fetch origin main && git merge --ff-only origin/main
   git commit --only kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml -F /tmp/ncmcp/msg-nextcloud-mcp-0.199.1.txt
   git show --stat HEAD      # exactly ONE file
   git log -1 --format=%s    # expect: feat(nextcloud-mcp): image 0.184.5 -> 0.199.1 ; else `git commit --amend --only -F <msg>` before push
   git push origin main
   git rev-parse HEAD > /tmp/ncmcp/bump.sha && cat /tmp/ncmcp/bump.sha
   ```
4. Reconcile. The SOP permits forcing a reconcile in a window. `kustomization/nextcloud-mcp` is in ns `office` (verified live 2026-10-09):
   ```bash
   flux reconcile kustomization nextcloud-mcp -n office --with-source
   flux reconcile hr -n office nextcloud-mcp
   ```
   Single replica and no volumes (premise 5), so there is no RWO/Recreate concern. There is no migration Job.
5. Watch:
   ```bash
   kubectl rollout status deploy/nextcloud-mcp -n office --timeout=180s
   kubectl get pods -n office -l app.kubernetes.io/name=nextcloud-mcp
   ```

## 4. Verification

Instruments (for `plan-premises.py --controls`):

- CONTROL: metric `kube_deployment_status_replicas_available`: `{namespace="office",deployment="nextcloud-mcp"}` must read `1` after the roll.
- CONTROL: metric `kube_pod_container_status_restarts_total`: `{namespace="office",container="main",pod=~"nextcloud-mcp-.*"}` must read `0` on the new pod 5 min after Ready.
- CONTROL: metric `container_memory_working_set_bytes`: same selector, must stay below `800Mi` (limit 1Gi).
- CONTROL: metric `ALERTS`: `{namespace=~"office|ai",alertstate="firing"}` must be EMPTY after settle (the §2.5 query's name exclusions apply).

1. **Flux Ready**:
   ```bash
   kubectl get helmrelease -n office nextcloud-mcp -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} chart={.status.history[0].chartVersion}{"\n"}'
   # expect: True chart=5.1.0 (or 5.2.1 if app-template-5.2.1 ran first)
   ```
2. **New bytes running, clean start log**:
   ```bash
   kubectl get pod -n office -l app.kubernetes.io/name=nextcloud-mcp -o jsonpath='{range .items[*]}{.metadata.name} restarts={.status.containerStatuses[0].restartCount} {.status.containerStatuses[0].imageID}{"\n"}{end}'
   # expect ONE pod, restarts=0, imageID ending sha256:42f45f0ebc368b47b0b8f29249bebf347960831f5819aba70b607c2c62b928c3
   #   (f6d88397… = old build still serving; f8f0e8a8… = 0.199.0 / b7faa131… = 0.198.3 / 24417dcb… = 0.195.4 committed by mistake)
   kubectl logs -n office deploy/nextcloud-mcp > /tmp/ncmcp/log.after-start
   python3 - <<'EOF'
   import re
   L=open("/tmp/ncmcp/log.after-start").read().splitlines()
   err=[l for l in L if re.search(r'(^|\s)(ERROR|CRITICAL)\s', l)]
   tb=[i for i,l in enumerate(L) if l.startswith('Traceback')]
   vc=[i for i in tb if i>0 and 'Could not parse vCard' in L[i-1]]
   print(f"lines={len(L)} ERROR/CRITICAL={len(err)} Traceback={len(tb)} vCard-attributed={len(vc)}")
   assert L, "EMPTY log -- wrong pod/container; do not pass"
   assert not err and len(tb)==len(vc), "unattributed ERROR/CRITICAL/Traceback -- read /tmp/ncmcp/log.after-start"
   EOF
   # vCard Tracebacks are known data (FN-less contacts; client/contacts.py byte-identical 0.195.4..0.199.1).
   # RE-RUN this scan AFTER §4.6 into /tmp/ncmcp/log.after-events (same script, other path).
   # CAN FAIL: a reviewer injected one unattributed Traceback + one ERROR line into a copy, and the assertion fired.
   ```
3. **CONTENTS ASSERTION (mcp 2.x lifespan + SAR plugin skipped)**:
   ```bash
   kubectl logs -n office deploy/nextcloud-mcp | grep -c 'Starting MCP session in single-user BasicAuth mode'
   # expect 1 right after start and STILL 1 after §4.4's sessions (format string at app.py:976 at v0.199.1;
   #   on 0.184.5 it climbs per session: 24 lines on the live pod 2026-09-29). A climbing count = old build.
   kubectl logs -n office deploy/nextcloud-mcp | grep -ciE 'plugin sar: (not available, skipping|registering tools)'
   kubectl logs -n office deploy/nextcloud-mcp | grep -ciE 'plugin sar: registering tools'
   # expect first >=1 and second 0 (plugins.py register_plugin_tools, v0.199.1). First 0 = log level hides INFO
   #   (then rely on §4.4's sar grep) or not a 0.199 build; second >=1 = SAR registered -> STOP, §5.
   ```
4. **CONTENTS ASSERTION (surface = baseline + the 21 names; SAR absent)**:
   ```bash
   cat > /tmp/ncmcp/tools.expected_new <<'EOF'
   nc_shopping_list_add_items
   nc_shopping_list_check_item
   nc_shopping_list_clear_checked_items
   nc_shopping_list_create_list
   nc_shopping_list_delete_item
   nc_shopping_list_delete_list
   nc_shopping_list_get_items
   nc_shopping_list_get_list
   nc_shopping_list_get_lists
   nc_shopping_list_uncheck_all_items
   nc_shopping_list_update_item
   nc_shopping_list_update_list
   nc_webdav_find_by_tag_name
   nc_webdav_get_file_tags
   nc_webdav_list_tags
   nc_webdav_list_trash
   nc_webdav_list_versions
   nc_webdav_restore_from_trash
   nc_webdav_restore_version
   nc_webdav_tag_file
   nc_webdav_untag_file
   EOF
   /tmp/ncmcp/call.sh tools/list '{}' > /tmp/ncmcp/tools_list.after.json
   python3 -c 'import json; d=json.load(open("/tmp/ncmcp/tools_list.after.json")); [print(t["name"]) for t in d["result"]["tools"]]' | sort > /tmp/ncmcp/tools.after
   comm -23 /tmp/ncmcp/tools.before /tmp/ncmcp/tools.after                                   # DISAPPEARED: expect EMPTY
   comm -13 /tmp/ncmcp/tools.before /tmp/ncmcp/tools.after | diff - /tmp/ncmcp/tools.expected_new && echo 'NEW TOOLS == EXPECTED'
   grep -ciE 'sar' /tmp/ncmcp/tools.after                                                   # expect 0 (SAR must not register)
   wc -l < /tmp/ncmcp/tools.after                                                            # expect 117
   kubectl port-forward -n office svc/nextcloud-mcp 18000:8000 >/dev/null 2>&1 & PF=$!; sleep 2
   curl -s -X POST http://localhost:18000/mcp -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
     -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"plan-probe","version":"0"}}}' \
     | python3 -c 'import sys,json
   raw=sys.stdin.read(); data=[l[5:].strip() for l in raw.splitlines() if l.startswith("data:")]
   r=json.loads(data[-1] if data else raw)["result"]; print(r["protocolVersion"], r["serverInfo"].get("version"))' | tee /tmp/ncmcp/protocol.after
   kill $PF 2>/dev/null
   # expect "2025-06-18 " (echoed offer; EMPTY serverInfo.version is the mcp 2.x signature; "1.29.0" = old build)
   ```
   117 and the exact 21 names were measured live on 0.195.4 (gate PASS, 2026-09-26). 0.195.5-0.199.1 add tools only in the plugin-gated `server/sar.py` (§1.2).
5. **CONTENTS ASSERTION (calendar LIST: same set, encoding-shape tolerant).** Carried verbatim from the reviewer-proven gate (`a1e5c69e`). This gate CANNOT see the §1.2 regression. §4.6 can.
   ```bash
   /tmp/ncmcp/call.sh tools/call '{"name":"nc_calendar_list_calendars","arguments":{}}' > /tmp/ncmcp/calendars.after
   /tmp/ncmcp/call.sh tools/call '{"name":"nc_webdav_list_directory","arguments":{"path":""}}' > /tmp/ncmcp/files.after
   python3 - /tmp/ncmcp/calendars.before /tmp/ncmcp/calendars.after /tmp/ncmcp/files.before /tmp/ncmcp/files.after <<'EOF'
   import json, sys
   from urllib.parse import unquote
   CB, CA, FB, FA = sys.argv[1:5]
   def result(p):
       r = json.load(open(p))["result"]; assert not r.get("isError"), (p, r)
       return r
   def full_unquote(s):
       for _ in range(8):
           n = unquote(s)
           if n == s: return s
           s = n
       raise AssertionError(f"unquote did not converge: {s!r}")
   def cals(p):
       r = result(p)
       sc = r.get("structuredContent") or json.loads(" ".join(c.get("text", "") for c in r.get("content", [])))
       items = sc.get("calendars")
       assert isinstance(items, list) and items, f"{p}: no non-empty `calendars` list"
       out, shapes = {}, []
       for c in items:
           seg = c["href"].rstrip("/").split("/")[-1]
           assert c["name"] in (seg, unquote(seg)), f"{p}: name {c['name']!r} is neither raw nor once-decoded {seg!r}"
           if seg != unquote(seg): shapes.append("raw" if c["name"] == seg else "once")
           key = full_unquote(c["href"])
           assert key not in out, f"{p}: two calendars collapse to one key"
           out[key] = (c["display_name"], full_unquote(c["name"]))
       return out, shapes
   (b, sb), (a, sa) = cals(CB), cals(CA)
   missing, added = sorted(b.keys() - a.keys()), sorted(a.keys() - b.keys())
   changed = sorted(k for k in b.keys() & a.keys() if b[k] != a[k])
   assert not (missing or added or changed), f"calendar set differs: missing={len(missing)} added={len(added)} changed={len(changed)}"
   fb, fa = (" ".join(c.get("text", "") for c in result(p).get("content", [])) for p in (FB, FA))
   assert len(fa) > 0, "empty file listing after bump"
   print(f"calendars before/after: {len(b)} {len(a)} | shape before={sorted(set(sb))} after={sorted(set(sa))} | files bytes: {len(fb)} {len(fa)}")
   EOF
   # expect: calendars before/after: 4 4 | shape before=['raw'] after=['once'] | …
   ```
6. **CONTENTS ASSERTION (per-calendar EVENT reads: the §1.2 regression)**:
   ```bash
   python3 /tmp/ncmcp/events.py /tmp/ncmcp/calendars.after /tmp/ncmcp/events.after.json
   python3 /tmp/ncmcp/events_gate.py /tmp/ncmcp/events.before.json /tmp/ncmcp/events.after.json
   # PASS: every calendar that was non-empty before is non-empty after, |delta| <= 2 (edits during the window).
   # FAIL prints: "calendar #N (pct_uri=True): 200 -> 0 events (SILENT EMPTY READ)" -> §5 rollback.
   kubectl logs -n office deploy/nextcloud-mcp > /tmp/ncmcp/log.after-events
   # then re-run the §4.2 python scan with "log.after-start" replaced by "log.after-events"; any unattributed ERROR -> §5.
   ```
   *Demonstrated 2026-09-29 on 0.184.5:* `events.py … --emulate-double-decode` sends exactly the URI that the post-0.195.5 `_get_calendar_url` builds, `quote(unquote(name))`. It read `[3, 0, 0, 0]` against a real `[3, 0, 200, 0]` with `isError=false`, and the gate FAILED with the SILENT EMPTY READ line (rc=1). Before-vs-before PASSes. **Limit:** the second `%`-URI calendar holds 0 events in range, so a regression on it is invisible to counts. §2.7 A covers it structurally.
7. **CONTENTS ASSERTION (0.192.0 BREAKING visible)**: `nc_calendar_bulk_operations` gains `apply_to_series` (default False) and loses no property:
   ```bash
   python3 - <<'EOF'
   import json
   def props(p, name):
       t=[t for t in json.load(open(p))["result"]["tools"] if t["name"]==name]; assert t, f"{name} missing from {p}"
       return t[0].get("inputSchema",{}).get("properties",{})
   b=props("/tmp/ncmcp/tools_list.before.json","nc_calendar_bulk_operations"); a=props("/tmp/ncmcp/tools_list.after.json","nc_calendar_bulk_operations")
   assert "apply_to_series" not in b, "baseline already had it -- was §2.4 A taken on 0.184.5?"
   assert "apply_to_series" in a and a["apply_to_series"].get("default") in (False, None), a.get("apply_to_series")
   assert set(b) <= set(a), f"LOST properties: {set(b)-set(a)}"
   print("bulk_operations props before/after:", len(b), len(a))
   EOF
   ```
8. **CONTENTS ASSERTION (0.188.1 contacts)**: the schema gained `include_photos`/`limit`/`offset`, and a live list returns `has_photo` with no inline photo by default:
   ```bash
   python3 - <<'EOF'
   import json
   def props(p, name):
       t=[t for t in json.load(open(p))["result"]["tools"] if t["name"]==name]; assert t, name
       return set(t[0].get("inputSchema",{}).get("properties",{}))
   b=props("/tmp/ncmcp/tools_list.before.json","nc_contacts_list_contacts"); a=props("/tmp/ncmcp/tools_list.after.json","nc_contacts_list_contacts")
   assert b == {"addressbook"}, f"baseline schema unexpected: {b}"
   assert {"addressbook","include_photos","limit","offset"} <= a, f"paging/photo params ABSENT: {a}"
   print("list_contacts props:", sorted(b), "->", sorted(a))
   EOF
   AB=$(python3 -c 'import json,re
   d=json.load(open("/tmp/ncmcp/addressbooks.before")); txt=" ".join(c.get("text","") for c in d["result"].get("content",[]))
   m=re.search(r"\"(?:name|id|uri)\"\s*:\s*\"([^\"]+)\"", txt); print(m.group(1) if m else "")')
   [ -n "$AB" ] || { echo "no addressbook id parsed -- inspect /tmp/ncmcp/addressbooks.before"; false; }
   /tmp/ncmcp/call.sh tools/call "{\"name\":\"nc_contacts_list_contacts\",\"arguments\":{\"addressbook\":\"$AB\",\"limit\":5}}" > /tmp/ncmcp/contacts.after
   python3 - <<'EOF'
   import json,re
   r=json.load(open("/tmp/ncmcp/contacts.after"))["result"]; assert not r.get("isError"), r
   txt=" ".join(c.get("text","") for c in r.get("content",[]))
   assert "has_photo" in txt, "has_photo ABSENT -- 0.188.1 mapper not running (or empty addressbook: check raw file)"
   inline=re.findall(r'"photo"\s*:\s*"(?:data:image|[A-Za-z0-9+/]{200,})', txt)
   assert not inline, f"{len(inline)} inline photo payload(s) although include_photos defaults to False"
   print("contacts: has_photo present, inline photos:", len(inline))
   EOF
   # CAN FAIL: a reviewer matched 91 inline payloads with this regex on 0.184.5 (4 in the first 5).
   ```
9. **Memory + restarts** (python 3.14 + office readers at import), 5 min after Ready:
   ```bash
   kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 >/dev/null 2>&1 & PF=$!; sleep 2
   curl -s --data-urlencode 'query=container_memory_working_set_bytes{namespace="office",container="main",pod=~"nextcloud-mcp-.*"}' http://localhost:9090/api/v1/query \
     | python3 -c "
   import sys,json; r=json.load(sys.stdin)['data']['result']
   assert r, 'EMPTY -- not scraped yet (or Prometheus restarting); retry, do not pass'
   for x in r:
       mib=float(x['value'][1])/2**20; print(x['metric']['pod'], f'{mib:.0f} MiB'); assert mib < 800, f'{mib:.0f} MiB >= 800'
   "
   curl -s --data-urlencode 'query=kube_pod_container_status_restarts_total{namespace="office",container="main",pod=~"nextcloud-mcp-.*"}' http://localhost:9090/api/v1/query \
     | python3 -c "import sys,json; r=json.load(sys.stdin)['data']['result']; assert r, 'EMPTY'; print([(x['metric']['pod'], x['value'][1]) for x in r]); assert all(x['value'][1]=='0' for x in r), 'restarts > 0'"
   kill $PF 2>/dev/null
   ```
10. **No new firing alerts**: re-run §2.5 and diff against `/tmp/ncmcp/alerts.before`. Expect `NONE FIRING` both times.
11. **The real consumers**:
    - OpenClaw (`ai`, mcporter, TS SDK). mcporter exits 0 on HTTP 500/`isError`, so the gate is the JSON body:
      ```bash
      kubectl exec -n ai deploy/openclaw -c app -- sh -c '
        M=/home/node/.openclaw/lib/node_modules/mcporter/dist/cli.js
        node "$M" --version >&2
        case "$NEXTCLOUD_MCP_URL" in
          http://nextcloud-mcp.*:8000/mcp) ;;
          *) echo "4.11 STOP: NEXTCLOUD_MCP_URL is not the streamable-HTTP endpoint .../mcp" >&2; exit 3;;
        esac
        cfg=$(mktemp /tmp/mcporter-ncmcp.XXXXXX)
        printf "{\"imports\":[],\"mcpServers\":{\"nextcloud\":{\"baseUrl\":\"%s\",\"headers\":{\"Authorization\":\"\${NEXTCLOUD_MCP_AUTH_HEADER}\"}}}}" "$NEXTCLOUD_MCP_URL" > "$cfg"
        node "$M" call --config "$cfg" --output json --timeout 30000 nextcloud.nc_webdav_list_directory path=""
        rm -f "$cfg"' > /tmp/ncmcp/openclaw.after
      python3 - /tmp/ncmcp/openclaw.after /tmp/ncmcp/files.after <<'EOF'
      import json, sys
      out, ref = sys.argv[1], sys.argv[2]
      raw = open(out).read(); assert raw.strip(), f"{out}: empty"
      d = json.loads(raw)
      assert "error" not in d and not d.get("isError"), f"OpenClaw/mcporter call FAILED: {json.dumps(d)[:300]}"
      got = {f["name"] for f in d.get("files", [])}
      r = json.load(open(ref))["result"]
      want = {f["name"] for f in (r.get("structuredContent") or json.loads(r["content"][0]["text"]))["files"]}
      assert got and got == want, f"root listing via OpenClaw differs: missing={len(want-got)} extra={len(got-want)}"
      print(f"4.11 OpenClaw/mcporter PASS: {len(got)} root entries")
      EOF
      ```
    - **Claude Desktop (attended).** Config read 2026-10-09 (`~/Library/Application Support/Claude/claude_desktop_config.json`, entry `nextcloud`): `mise exec uv -- uvx mcp-proxy --transport streamablehttp https://nextcloud-mcp.<DOMAIN>/mcp`, with no client auth header (single_user_basic: the server authenticates to Nextcloud with its own app password). The path is HTTPRoute `nextcloud-mcp` on `envoy-internal/https`, then svc :8000 `/mcp`. Nothing in 0.185..0.199 changes the `/mcp` path or the streamable-HTTP transport on the server side. The mcp 2.x server change happened at 0.185.0, and 0.199.x keeps mcp 2.1.1. `mcp-proxy` is unpinned (`uvx` resolves the latest at app launch). So **fully quit and relaunch Claude Desktop** after the roll, because the proxy holds a session to the old pod. Then list the root folder, **ask for this week's events from the busiest calendar** (the human form of §4.6), and confirm the tool count shown for `nextcloud` grew by 21. Record the `mcp-proxy` version uvx resolved. A Desktop-only failure with §4.4/§4.11 green is a client-pin issue, not a server rollback trigger (§5 last bullet).
12. **CONTENTS ASSERTION (0.199.0 packaging: the semantic/documents extras are still in the image)**:
    ```bash
    kubectl exec -n office deploy/nextcloud-mcp -c main -- /opt/venv/bin/python -c \
      'import importlib.util as u; m=["pymupdf","pypdfium2","docx","openpyxl","qdrant_client"]; r={x: u.find_spec(x) is not None for x in m}; print(r); raise SystemExit(0 if all(r.values()) else 1)' \
      && echo "4.12 PASS" || echo "4.12 FAIL"
    # FAIL means the image dropped the extras: nc_webdav_read_file would return PDFs/Office raw with the
    #   "Install it with: pip install 'nextcloud-mcp-server[documents]'" note (server/webdav.py, v0.199.1) -> §5.
    # CAN FAIL: features.documents_installed() keys on exactly find_spec("pymupdf"). On the live 0.184.5 pod
    #   `/opt/venv/bin/python` exists (verified 2026-10-09, Python 3.12.14); the module set there is the pre-split core deps.
    ```
13. **Close out**: `runbooks/update-marker.sh clear nextcloud-mcp`. Retire this file and the superseded predecessors in the same commit series. F-9af9baf7/F-80459b23 are script-owned and should close on the next sweep. Verify that rather than assume it.

## 5. Rollback

Stateless (premises 4-5), so the rollback is an inverse image-tag edit. It is not `git revert`, because in this shared worktree `git revert` refuses (rc=128) whenever another session has staged anything.

```bash
cd /Users/mu/code/cberg-home-nextgen || exit 1
sed -i '' 's/^\([[:space:]]*tag: \)0\.199\.1$/\10.184.5/' kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml
git diff --stat -- kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml    # expect 1 file 1+/1-; 0 files = no-op: STOP
cat > /tmp/ncmcp/msg-revert-nextcloud-mcp-0.199.1.txt <<'EOF'
Revert "feat(nextcloud-mcp): image 0.184.5 -> 0.199.1"

Rollback per runbooks/maintenance/plans/nextcloud-mcp-0.199.1.md section 5
(stateless bridge, image tag only). Reverts the commit in /tmp/ncmcp/bump.sha.
EOF
git commit --only kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml -F /tmp/ncmcp/msg-revert-nextcloud-mcp-0.199.1.txt
git show --stat HEAD && git log -1 --format=%s    # ONE file; subject = Revert "feat(nextcloud-mcp): image 0.184.5 -> 0.199.1"
git push origin main
flux reconcile kustomization nextcloud-mcp -n office --with-source && flux reconcile hr -n office nextcloud-mcp
kubectl rollout status deploy/nextcloud-mcp -n office --timeout=180s
kubectl get pod -n office -l app.kubernetes.io/name=nextcloud-mcp -o jsonpath='{range .items[*]}{.metadata.name} {.status.containerStatuses[0].imageID}{"\n"}{end}'
# expect imageID ending sha256:f6d8839722587f2cd37ec5218a18479f9e313be9904ad4f6bbb36f98bc827065
```
(Inverse sed dry-tested 2026-10-09 on macOS against the forward edit. It restores the scratch copy byte-identical, `cmp` clean.)

Confirm the cluster is back:
- Re-run §4.4. `tools.after` must equal `tools.before` (96, `comm` empty both ways), and the protocol must read `2025-06-18 1.29.0`.
- Re-run §4.6 into `events.revert.json` and gate it against `events.before.json`. The busiest calendar must be back at its count.
- Re-run §4.11 (OpenClaw), and relaunch Claude Desktop.
- If the failure was consumer-side (protocol/client), note it on `F-9af9baf7` via `policy-cli.py finding detail`. The fix there is pinning the client, not holding the server.

## 6. Interference notes

- **Consumers, not shared infra.** OpenClaw (`ai`, mcporter entry `nextcloud`) and Claude Desktop lose or change tools silently if this goes wrong. Treat any post-bump OpenClaw Nextcloud-tool failure as this plan's. The §1.2 regression is precisely such a silent failure ("no events" instead of an error), which is why §4.6 exists and why the Claude Desktop check asks for events.
- **Same file as `app-template-5.2.1`** (awaiting-go nightly:2026-10-09). Its Batch A sed changes line 12 (chart) of this helmrelease, and this plan changes line 34 (tag). The edits do not collide textually, but they must not share a night (§4.2 attribution). Premise 6 accepts either chart version.
- **Nextcloud server work** (`nextcloud-fleet-35.0.1` 10-18, `redis-fleet-8.10.2` 10-25, `bitnamilegacy-exit-nextcloud-db` if revived): every §4 contents gate is a live call into that server, so this plan never shares a slot with them. After 35.0.1 lands, premise 2 fails closed. Re-vet then, because Nextcloud 35 CalDAV behaviour feeds straight into §1.2's analysis.
- **Prometheus**: §2.5/§4.9/§4.10 read it. No kube-prometheus-stack plan is open (91.9.0 executed + retired `3da2a100`). If a new one is written, it goes in `conflicts_with` on both sides.
- **Attended only.** The deny rule mandates it, and `capability_change: true` routes it there anyway. Never `nightly`. Nothing here touches Longhorn, cert-manager, cilium, coredns or the Gateways.
- **`talos-linux-1.14.2`** (awaiting-go sun-attended:2026-11-01, `exclusive: true`): its node roll restarts this pod and the Nextcloud server. Its `exclusive` flag already keeps this plan out of its slot. If the two land on adjacent days, take §2.4's baseline AFTER the roll.
- **Supersession bookkeeping** (§1.5): until `nextcloud-mcp-0.198.0` is set `superseded`, two live plans own the same component and the same findings. They are cross-listed in `conflicts_with` here so the scheduler can never place both.

## 7. What I could not verify (2026-10-09)

- **Whether 0.195.4 / 0.199.1 remediate F-80459b23.** This decides whether option B closes the security driver. Any scan result goes on the record, not here.
- **The upstream fix timeline.** No upstream issue exists for the literal-`%` calendar-URI case (re-searched 2026-10-09). Filing one is an operator/agent action outside this plan, and it is the prerequisite for option A.
- **Write-path behaviour on the `%`-URI calendars** (create/update/delete event), and the 0.199.1 fixed-offset -> UTC write change. By code, writes target the same wrong URI. Not exercised: no writes against live household calendars.
- **The second `%`-URI calendar** holds no events in 2015-2030, so §4.6 cannot see a regression on it. §2.7 A covers it structurally.
- **`mcp-proxy` (Claude Desktop) and mcporter (TS SDK) against mcp 2.1.1 at 0.199.1.** Not re-measured. 0.195.4 (same mcp 2.1.1) reached the consumer gate on 2026-09-26 and failed only on the since-fixed OpenClaw URL.
- **Whether the INFO-level `Plugin sar: …` line is emitted at the deployed log level** (§4.3, second check). If it is not, §4.4's `sar` grep is the binding check.
