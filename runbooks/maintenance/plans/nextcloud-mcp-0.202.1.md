---
plan_id: nextcloud-mcp-0.202.1
component: nextcloud-mcp
pr: 258                               # Renovate "feat(container): update ghcr.io/cbcoutinho/nextcloud-mcp-server ( 0.184.5 → 0.202.1 )",
                                      # branch renovate/ghcr.io-cbcoutinho-nextcloud-mcp-server-0.x (retargeted from 0.201.2),
                                      # OPEN / MERGEABLE, all 4 checks SUCCESS incl. Flate Render Gate (gh pr view 258, 2026-10-27).
                                      # Held by the `*nextcloud-mcp*` `max: patch` deny rule (0.x minor line move).
kind: image
current: "0.184.5"
target: "0.202.1"                     # Verified 2026-10-27: GHCR 0.202.1 index sha256:b8424756…ae9e1 == `latest`; 0.202.2 and
                                      # 0.203.0 404; GitHub v0.202.1 is Latest (published 2026-10-26T10:33Z), not a pre-release.
update_type: minor                    # semver label only. At major 0 the MINOR is the breaking axis; this hop crosses EIGHTEEN
                                      # minor lines (0.185 .. 0.202). 0.185..0.201.2 carried from nextcloud-mcp-0.201.2 (§1.3);
                                      # 0.201.2..0.202.1 read here per tag + source diff + lockfile diff (§1.2).
risk: medium                          # stateless bridge, cheap tag rollback, nothing forward-only. BUT the 0.195.5
                                      # calendar-addressing regression is STILL present at v0.202.1 AND on master (§1.1), and
                                      # the data that triggers it is still live (2 of 4 calendars, re-measured 2026-10-27), so
                                      # the EXPECTED outcome today is a STOP at §2.7 before any commit. New at 0.202.1: a broad
                                      # dependency relock (142 packages incl. caldav 3.2.1 -> 3.6.0, mcp 2.1.1 -> 2.3.0), §1.2.
est_duration_min: 40
needs_reboot: false
touches:
  namespaces: [office]
  resources:
    - helmrelease/nextcloud-mcp
    - deployment/nextcloud-mcp
                                      # httproute/nextcloud-mcp + svc/nextcloud-mcp re-render from the same HR but their spec
                                      # does not change (the image tag is the whole diff), so they are not perturbed.
  shared: [monitoring]                # READ-only: §2.5/§4.9/§4.10 read Prometheus (the window's instrument). No gateway, CNI,
                                      # DNS, storage or shared DB is perturbed. Consumers (ai/openclaw, Claude Desktop) are
                                      # blast radius, not shared infra (§6).
depends_on: []                        # Flux `dependsOn: nextcloud` is ordering-only; no note in 0.185..0.202.1 states a
                                      # minimum Nextcloud server version.
conflicts_with:
  - nextcloud-9.4.1                   # vetted nightly:2026-10-28; chart/exporter leg of Nextcloud, restarts deployment/nextcloud.
  - nextcloud-whiteboard-2.1.2        # vetted nightly:2026-10-29; same office namespace.
  - redis-fleet-8.10.3                # (retargeted 2026-10-27 from superseded 8.10.2; draft) sun-attended:2026-11-29; restarts office/nextcloud-redis (all sessions drop).
  - bitnamilegacy-exit-nextcloud-db   # blocked/unwindowed; quiesces Nextcloud if revived.
  - nextcloud-mcp-0.201.2             # SUPERSEDED BY THIS PLAN (§1.5): same component, same HR line. The three vetted plans
                                      # above still name 0.201.2 (not dead: the file stays, `superseded`); re-point them here.
                                      # No kube-prometheus-stack plan is open on 2026-10-27; any new one must be added here
                                      # because §2.5/§4.9/§4.10 read Prometheus.
exclusive: false
security_ref: F-80459b23              # security driver; detail stays on the record (§1.4).
capability_change: true               # vs LIVE 0.184.5: +21 tools (4 WRITE), behaviour changes on live tools (0.192.0 bulk-ops
                                      # series default, 0.188.1 contacts photo opt-in, 0.187.0 find_availability, 0.199.1
                                      # fixed-offset datetimes stored as UTC, 0.200.0 Talk thread params, 0.201.0 Deck card
                                      # params), 0.202.1 30-min MCP session idle timeout, and the 0.195.5 calendar change.
rollback_class: git-revert            # no PVC, no volumes, no DATABASE_URL/TOKEN_STORAGE_DB (premises). Executed as an inverse
                                      # tag edit (§5) because `git revert` refuses in the shared worktree when anything is staged.
finding_refs: [F-9af9baf7, F-80459b23] # F-9af9baf7 = version finding (title names 0.202.1, last seen 2026-10-27). F-80459b23 =
                                      # security finding. Carried from nextcloud-mcp-0.201.2 (superseded by this plan).
review: null
status: blocked                       # Planner 2026-10-27: §2.7 STOP fires (7A=2 live, 7B count=1 at v0.202.1 and master).
                                      # The operator decision of 2026-10-23 ("wait for upstream", §1.6 A) is NOT satisfied
                                      # by 0.202.1 -> stays `blocked` with the same unblock condition.
window: null                          # BLOCKED (operator decision 2026-10-23: wait for upstream). Unblock condition (carried from
                                      # 0.201.2): an upstream tag whose calendar.py no longer does `unquote(calendar_name)` in
                                      # _get_calendar_url AND §2.7 passes live. Then: attended slot only (sat/sun), never nightly.
premises:
  - id: image-is-still-0.184.5
    why: >-
      current: and the rollback target are 0.184.5. If the cluster has moved, the
      diff, the baselines and the rollback digest are wrong.
    run: kubectl get deploy -n office nextcloud-mcp -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: ghcr.io/cbcoutinho/nextcloud-mcp-server:0.184.5
  - id: renovate-pr-258-still-targets-0.202.1
    why: >-
      Drift detector. The Renovate branch commit subject is the PR title. If
      upstream ships 0.202.2/0.203.x Renovate rewrites it and this fails, which
      forces a §1.2 re-read of the new tags and a §2.7-B re-run before anything
      merges. Run the §2.0 git fetch first; a stale local ref is the only way
      this can read green on a drifted PR, and §2.0's registry probe covers that.
    run: git log -1 --format=%s origin/renovate/ghcr.io-cbcoutinho-nextcloud-mcp-server-0.x
    expect_exact: "feat(container): update ghcr.io/cbcoutinho/nextcloud-mcp-server ( 0.184.5 → 0.202.1 )"
  - id: nextcloud-server-is-35
    why: >-
      §4.5/§4.6/§4.13 read CalDAV/OCS from this server. Live 35.0.2 on
      2026-10-27. Patch drift tolerated; a 36.x or 34.x server fails this closed
      and the §2.4 baselines must be re-taken against the new server.
    run: kubectl get deploy -n office nextcloud -o jsonpath='{.spec.template.spec.containers[?(@.name=="nextcloud")].image}'
    expect_matches: 'docker\.io/nextcloud:35\.0\.[0-9]+(@sha256:[0-9a-f]+)?$'
  - id: deployment-mode-still-single-user-basic
    why: >-
      The 0.185.0 elicitation break, the 0.190.0/0.198.1 CIMD/OAuth changes,
      the 0.199.0 oidc-2.5 change, the 0.200.1 BasicAuthMiddleware 401 path and
      the 0.201.2 AS-proxy refresh-error change (auth/oauth_routes.py, OAuth
      mode only) are all inert in single_user_basic. Any other mode voids §1.2/§1.3.
    run: kubectl get secret -n office nextcloud-mcp-config -o json | jq -r '.data.MCP_DEPLOYMENT_MODE' | jq -Rr '@base64d'
    expect_exact: single_user_basic
  - id: exactly-four-config-keys
    why: >-
      Proves no DATABASE_URL/TOKEN_STORAGE_DB (free rollback), no
      VECTOR_SYNC_ENABLED/ENABLE_SEMANTIC_SEARCH/EMBEDDING_GATEWAY_URL/SAR_ENABLED
      (0.196-0.199 indexing/SAR surface stays off), no CIMD_ALLOWED_HOSTS, no
      COLLABORA_URL/DOCLING_API_URL, no LOGIN_FLOW_OIDC_*.
    run: kubectl get secret -n office nextcloud-mcp-config -o go-template='{{range $k,$v := .data}}{{$k}},{{end}}'
    expect_exact: MCP_DEPLOYMENT_MODE,NEXTCLOUD_HOST,NEXTCLOUD_PASSWORD,NEXTCLOUD_USERNAME,
  - id: no-volumes-on-the-pod
    why: >-
      Second half of the stateless claim: nothing to snapshot, no RWO
      multi-attach guard needed.
    run: kubectl get deploy -n office nextcloud-mcp -o json | jq -r '.spec.template.spec.volumes'
    expect_exact: "null"
  - id: helmrelease-chart-5.3.0
    why: >-
      Verification assumes the app-template 5.3.0 render (container `main`,
      tcp probes). Any other chart means an unreviewed render change.
    run: kubectl get helmrelease -n office nextcloud-mcp -o jsonpath='{.status.history[0].chartVersion}'
    expect_exact: 5.3.0
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/auto-update.md
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/vulnerability-disclosure.md
generated: "2026-10-27"
---

## 1. Summary & why held

`kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml:34` pins
`ghcr.io/cbcoutinho/nextcloud-mcp-server` at `0.184.5`. Renovate PR **#258**
(retargeted again by Renovate) now moves it to `0.202.1` (upstream head). The
auto-updater holds it because this is a 0.x release-line move (0.184 -> 0.202):
at major 0 the minor is the breaking axis, and the `*nextcloud-mcp*` deny rule
(`max: patch`) demands a human read of every minor hop. Dispatched by sweep
`3f978ad9` rule 4d0. Security-driven: F-80459b23 (§1.4).

**Verdict: STILL DO NOT RUN AS-IS. 0.202.1 does NOT resolve the blocker of
`nextcloud-mcp-0.198.0` / `0.199.1` / `0.200.2` / `0.201.2`.** The operator
decided on 2026-10-23 to wait for upstream; the unblock condition is not met.

### 1.1 The blocker, re-checked 2026-10-27

- **Code:** `_get_calendar_url()` still returns
  `encode_dav_url(f"{self._calendar_home_url}{unquote(calendar_name)}/")` at
  `nextcloud_mcp_server/client/calendar.py:582` on **v0.202.1 and master**
  (both fetched via `gh api … contents … ?ref=`, `grep -c 'unquote(calendar_name)'`
  = 1 each, `def _get_calendar_url` present). calendar.py is not in the
  `compare v0.201.2...v0.202.1` file list.
- **Data:** re-measured 2026-10-27 through the running 0.184.5 pod
  (`nc_calendar_list_calendars`, read-only): **4 calendars, 2 with a literal `%`
  in their URI** — unchanged. Per-calendar event counts carried
  `[3, 0, 200, 0]` (2026-10-25); §2.4 F re-takes them on the day.
- **Effect** (reproduced 2026-10-21 and 2026-10-25, carried):
  `events.py --emulate-double-decode` read `[3, 0, 0, 0]`, `isError=false` — the
  busiest calendar (200 events) silently reads **empty**. Feature loss; operator
  policy is "interruption OK, data/feature loss not".
- **Upstream:** still **no issue** for the literal-`%` case (`gh search issues`
  2026-10-27: "calendar percent", "unquote calendar", "calendar %25", "calendar
  name encoded" -> none; "_get_calendar_url" -> only the closed, unrelated #1449).
  Upstream ships several tags a week but will not fix a bug nobody reported:
  filing the issue (§1.6 A text) is the practical prerequisite to unblocking.
- **New caveat:** 0.202.1 relocks `caldav` 3.2.1 -> 3.6.0 (§1.2). The URL is
  built by our-side `encode_dav_url` before caldav sees it, so the bump is not
  expected to change the outcome, but it was not observed. §4.6 is the binding
  check either way; it is not a reason to skip §2.7.

§2.7 therefore fails on both legs today and the window run ends there with
nothing committed.

| tag | GHCR (anonymous token, OCI index, 2026-10-27) |
|---|---|
| `0.184.5` (live) | 200, `sha256:f6d8839722587f2cd37ec5218a18479f9e313be9904ad4f6bbb36f98bc827065` (= running pod `imageID`, 2026-10-27) |
| `0.195.4` (last tag WITHOUT the regression; option B) | carried: `sha256:24417dcb804fc65bcb8712226bf70be71018aefd2ec7b27e9392a4d4e1ed707c` |
| **`0.202.1` (target)** | **200, `sha256:b842475624063f5c9e366a7af0e571848bd79bf2f6e345baac83ecf6bd9ae9e1`** |
| `latest` | 200, identical to 0.202.1 |
| `0.202.2`, `0.203.0` | 404 |

v0.202.1 was published 2026-10-26T10:33Z; it clears the 48 h
`minimum_release_age_hours` gate at 2026-10-28T10:33Z. Re-run §2.0.

### 1.2 What changed 0.201.2 -> 0.202.1, per tag + source diff

Source: `gh api compare v0.201.2...v0.202.1` (38 commits, 60 files, mostly
docs/ADR reflow and CI). **Dockerfile byte-identical** (`diff` of both refs).
`app.py`, `client/calendar.py`, `plugins.py` untouched. Runtime code changed:
`server/notes.py` (+61), `models/notes.py` (+20), and type-comment-only edits in
`document_processors/pymupdf.py`, `pypdfium2_fast.py`, `providers/bm25.py`,
`vector/document_chunker.py`, `vector/processor.py`, `vector/queue/procrastinate.py`.

| tag | release note (verbatim) | applies to us? |
|---|---|---|
| 0.201.3 | *"ci: never cancel pact runs for master pushes"* | CI only. |
| **0.202.0** | *"notes: add nc_notes_list_notes tool with a total count"* (+ description/limit fixes) | **Inert here.** Notes tools are registered through `configure_app_tools(mcp, "notes")` in `server/__init__.py`, *"gated on the app being installed for the user"*. The **Notes app is not installed** (`occ app:list` 2026-10-27: calendar, contacts, files_trashbin, files_versions, mail, spreed, systemtags) and the live 0.184.5 tool list has **0** `nc_notes_*` names. So the surface stays **117** with the same 21 new names (§4.4 adds a `nc_notes_` = 0 check). |
| **0.202.1** | *"deps: pin mcp to 2.3.x for the streamable-HTTP session idle timeout"* | **Applies, behaviour change, beneficial.** Commit `4e595ad418`: *"mcp 2.1.1 never reaps stateful streamable-HTTP sessions a client does not DELETE, so each one (and its last request body) lives until the process exits. mcp 2.3.0 adds a default 30-minute session idle timeout."* For us: (a) the memory curve should be flatter than 0.185..0.201 would have been (§4.9 limit unchanged); (b) a client that holds a session idle > 30 min gets the session reaped and must re-initialize. OpenClaw/mcporter opens a session per call (unaffected); Claude Desktop's `mcp-proxy` holds a long-lived session -> §4.11 adds an idle re-check. |
| (relock) | `uv.lock` 142 package moves between the two tags (not only mcp: a lock-maintenance relock rode along). Runtime-relevant: **`caldav` 3.2.1 -> 3.6.0**, `icalendar-searcher` 1.0.6 -> 1.3.0, `mcp`/`mcp-types` 2.1.1 -> 2.3.0, `httpx2`/`httpcore2` 2.12 -> 2.16, `pydantic` 2.13 -> 2.14, `uvicorn` 0.51 -> 0.54, `openai` 2.46 -> 3.37, `sqlalchemy` 2.0 -> 2.1, `qdrant-client` 1.18 -> 1.20, `pypdfium2` 5.12 -> 5.14, `cryptography` 49 -> 50 | **This is the real risk delta of the retarget.** caldav + icalendar-searcher sit directly under every calendar tool -> §4.5/§4.6/§4.7 are the gates (unchanged, they read contents). openai/sqlalchemy/qdrant are on the vector/semantic paths, off here (premise `exactly-four-config-keys`). pypdfium2 -> §4.12 import check. |

`pyproject.toml`: `mcp[cli] (>=2.1,<3)` -> `(>=2.3,<2.4)`; version line; ruff lint
pin (dev only).

### 1.3 0.184.5 -> 0.201.2, carried from nextcloud-mcp-0.201.2 §1.2/§1.3

- **0.185.0 BREAKING**: mcp SDK 1.29 -> 2.x, elicitation -> message_only. Inert
  in single_user_basic. Python 3.12 -> 3.14. Lifespan runs once per container
  start (§4.3).
- **0.192.0 BREAKING**: `nc_calendar_bulk_operations` leaves recurring series
  alone unless `apply_to_series=true` — safer default (§4.7).
- **0.194.0 / 0.196.0 / 0.197.0 / 0.198.0 BREAKING**: captioning key rename,
  vector-sync indexing, SAR scopes, `SAR_ENABLED`: inert (premise
  `exactly-four-config-keys`).
- **0.195.5 (REGRESSION ON OUR DATA)**: §1.1.
- **0.199.0 BREAKING**: semantic deps no longer default on PyPI — *"The Docker
  image is unaffected"*; §4.12 asserts the extras in-pod.
- 0.199.1: fixed-offset datetimes stored as UTC (write path only).
- 0.199.2-0.199.4: mail sync-on-uncached, document parse robustness, credential-free logging.
- **0.200.0**: Talk thread params on `talk_get_messages`/`talk_send_message` (optional, additive).
- 0.200.1: BasicAuthMiddleware 401 path — mounted only in multi-user BasicAuth (inert; §4.3 asserts absent).
- **0.200.2**: OCS-APIRequest header moved into the httpx client factory -> §4.13 Talk/OCS gate.
- 0.200.3-0.200.5: search/token-broker/debug-logging fixes, inert here.
- **0.201.0**: Deck card `startdate`/`color` (Deck app absent -> inert).
- **0.201.1**: handshake advertises `serverInfo.version` = package version -> §4.4 expects `2025-06-18 0.202.1`.
- 0.201.2: AS-proxy refresh error reporting (OAuth modes only, inert).
- Additive: 0.186.0 12 `nc_shopping_list_*` (registered ungated, app absent -> calls 404),
  0.188/0.189 9 `nc_webdav_*` tag/trash/version tools (4 WRITE), 0.188.1
  contacts photo opt-in + paging (§4.8), 0.187.0 real `find_availability`.

### 1.4 Security driver

> **Security driver: detail withheld from this public repo.**
> Tracked as **F-80459b23** (`security`). Quote the contextual tier from the sweep board, not the raw scanner severity.
> - Dashboard: `https://sweep.<DOMAIN>/findings/F-80459b23`
> - CLI: `runbooks/policy-cli.py finding show F-80459b23`

`F-f02df447` (`[AR-029]`, accepted) is the residual base-OS tally on the same
image. Whether 0.195.4 (option B) or 0.202.1 remediates the F-80459b23 set is a
per-tag scan question; the answer goes on the record
(`policy-cli.py finding detail F-80459b23`), never into this file. The 0.202.1
relock (142 packages, incl. `cryptography` 49 -> 50) makes a per-tag scan of
0.202.1 more informative than the 0.201.2 one was.

### 1.5 Supersession: this plan SUPERSEDES `nextcloud-mcp-0.201.2`

Dispatched by the sweep as a new plan_id for the new target, on the
coordinator's instruction (the plans README prefers refresh-in-place; the
carry-across is done by hand). `nextcloud-mcp-0.201.2` is set
`status: superseded` with a pointer here in the same pass. Carried: `pr`,
`finding_refs`, `security_ref`, the §1.6 decision and the operator's 2026-10-23
"wait for upstream" choice, the §2.7 STOP gate, all §4 gates, the §5 inverse-sed
rollback. Changed vs that plan: target/digest/PR-title premise, §1.1/§1.2
re-read at 0.202.1, §1.2 relock analysis (new), §4.4 `nc_notes_` = 0 check and
protocol expectation `0.202.1`, §4.11 Desktop idle re-check (mcp 2.3 session
idle timeout), §5 inverse sed now matches `0\.202\.1$`, `conflicts_with`
re-pointed (0.200.2/0.198.0 dropped — both already `superseded`; 0.201.2 added).

**Owed by the coordinator (this planner writes only plan files):**
1. Re-point the reciprocal `conflicts_with` entries naming `nextcloud-mcp-0.201.2`
   to this id: `nextcloud-9.4.1`, `nextcloud-whiteboard-2.1.2`. (`redis-fleet-8.10.3`,
   retargeted from 8.10.2 by a concurrent session 2026-10-27, already names this
   id.) Refs stay non-dead in the meantime because the 0.201.2 file remains.
2. Re-key the home-operation `go_no_go`/blocked issue for nextcloud-mcp to this id.

### 1.6 The operator decision (unchanged; operator chose A on 2026-10-23)

| option | what | cost |
|---|---|---|
| **A. Wait for upstream** (CHOSEN 2026-10-23) | Still no upstream issue exists — filing one is the practical prerequisite. Issue text: *"`_get_calendar_url` unquotes calendar names; Nextcloud calendar URIs CAN contain a literal `%` (created by CalDAV clients that percent-encode the URI); reads silently return empty."* Retarget to the first tag whose `_get_calendar_url` no longer unquotes blindly; §2.7 B detects that. | Security finding stays open until then. Five upstream retargets (0.198 -> 0.202) have now passed without a fix. |
| B. Take 0.195.4 now | Revive `nextcloud-mcp-0.187.1` (superseded) with this plan's §4.6 event gate; park this file. | Only worth it if 0.195.4 remediates F-80459b23 (§1.4). |
| C. Change the data | Recreate the two `%`-URI calendars with clean URIs, then run this plan (§2.7 A passes). | Breaks every CalDAV client syncing those calendars; operator-only data surgery. |
| D. Accept | Run 0.202.1 and accept 0 events from the busiest calendar via MCP. | Feature loss. Not recommended. |

## 2. Pre-checks

0. **Target still upstream head + PR unchanged** (premises have no network verb):
   ```bash
   cd /Users/mu/code/cberg-home-nextgen || exit 1
   git fetch origin main renovate/ghcr.io-cbcoutinho-nextcloud-mcp-server-0.x
   gh pr view 258 --json state,mergeable,files --jq '.state, .mergeable, [.files[].path]'
   # expect: OPEN / MERGEABLE / ["kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml"]
   TOKEN=$(curl -s "https://ghcr.io/token?scope=repository:cbcoutinho/nextcloud-mcp-server:pull&service=ghcr.io" \
     | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
   for t in 0.202.1 latest 0.202.2 0.203.0; do
     printf '%-8s ' "$t"
     curl -sI -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.oci.image.index.v1+json" \
       "https://ghcr.io/v2/cbcoutinho/nextcloud-mcp-server/manifests/$t" \
       | tr -d '\r' | awk 'NR==1{printf "%s ",$2} tolower($1)=="docker-content-digest:"{print $2}'; echo
   done
   # measured 2026-10-27: 0.202.1 200 sha256:b8424756…ae9e1; latest 200 SAME; 0.202.2 404; 0.203.0 404.
   # A newer tag -> STOP: read its release body, run §2.7 B against it, refresh THIS file in place.
   ```
1. **Premises** (seven, fail-closed; run AFTER §2.0's fetch):
   ```bash
   python3 runbooks/plan-premises.py nextcloud-mcp-0.202.1 --require-premises
   ```
2. **Health floor**:
   ```bash
   flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
   flux get helmreleases -A   | awk 'NR==1 || $5 != "True"'
   kubectl get pods -n office -l app.kubernetes.io/name=nextcloud-mcp     # live 2026-10-21: nextcloud-mcp-55ff568864-4z4rl 1/1, restarts=0
   kubectl get helmrelease -n office nextcloud-mcp -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'   # expect True
   kubectl get kustomization -n office nextcloud-mcp                     # live: Ready True
   ```
3. **Nextcloud apps behind the tool families**:
   ```bash
   kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c 'php occ app:list' \
     | grep -iE '^[[:space:]]*- (calendar|contacts|deck|notes|tables|shoppinglist|mail|spreed|collectives|news|cookbook|files_versions|files_trashbin|systemtags):'
   # carried 2026-09-22: calendar, contacts, mail, spreed, files_trashbin, files_versions, systemtags. spreed MUST be
   # present (§4.13 reads Talk); if it is gone, §4.13 baseline reads isError and must be replaced, not skipped.
   ```
4. **CONTENTS baseline on the CURRENT server (0.184.5)**. All artefacts in `/tmp/ncmcp/`:
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
   wc -l < /tmp/ncmcp/tools.before                       # measured 2026-10-21: 96
   # B) calendar list, C) files root, D) addressbooks, G) Talk conversations (OCS path, §4.13)
   /tmp/ncmcp/call.sh tools/call '{"name":"nc_calendar_list_calendars","arguments":{}}' > /tmp/ncmcp/calendars.before
   /tmp/ncmcp/call.sh tools/call '{"name":"nc_webdav_list_directory","arguments":{"path":""}}' > /tmp/ncmcp/files.before
   /tmp/ncmcp/call.sh tools/call '{"name":"nc_contacts_list_addressbooks","arguments":{}}' > /tmp/ncmcp/addressbooks.before
   /tmp/ncmcp/call.sh tools/call '{"name":"talk_list_conversations","arguments":{}}' > /tmp/ncmcp/talk.before
   for f in calendars files addressbooks talk; do python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); assert not d["result"].get("isError"), d; print(sys.argv[1], "ok")' /tmp/ncmcp/$f.before; done
   # measured 2026-10-21: all four ok; talk structuredContent success=True total=2
   # E) negotiated protocol + serverInfo
   kubectl port-forward -n office svc/nextcloud-mcp 18000:8000 >/dev/null 2>&1 & PF=$!; sleep 2
   curl -s -X POST http://localhost:18000/mcp -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
     -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"plan-probe","version":"0"}}}' \
     | python3 -c 'import sys,json
   raw=sys.stdin.read(); data=[l[5:].strip() for l in raw.splitlines() if l.startswith("data:")]
   r=json.loads(data[-1] if data else raw)["result"]; print(r["protocolVersion"], r["serverInfo"].get("version"))' | tee /tmp/ncmcp/protocol.before
   kill $PF 2>/dev/null                                  # 0.184.5: "2025-06-18 1.29.0"
   ```
   **F) Per-calendar EVENT reads (the §1.1 regression lives here).** For each calendar, call `nc_calendar_list_events` with the `name` the server returned (what a consumer does), range 2015-01-01..2030-12-31, limit 200:
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
   # measured 2026-10-21 on 0.184.5: 4 calendars; pct-URI calendars=2; per-calendar counts=[3, 0, 200, 0]
   ```
   Re-take A-G on the day, and again after any Nextcloud server move.
5. **No firing alerts in office/ai**:
   ```bash
   kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 >/dev/null 2>&1 & PF=$!; sleep 2
   curl -s --data-urlencode 'query=ALERTS{namespace=~"office|ai",alertstate="firing"}' http://localhost:9090/api/v1/query \
     | python3 -c "import sys,json; r=json.load(sys.stdin)['data']['result']; n=sorted(x['metric'].get('alertname') for x in r if x['metric'].get('alertname') not in ('Watchdog','InfoInhibitor')); print(n or 'NONE FIRING')" | tee /tmp/ncmcp/alerts.before
   kill $PF 2>/dev/null
   # CAN FAIL: count_over_time of this selector over 30d returned KubeJobFailed/MealiePodRestarted (2026-09-26).
   ```
6. **Active-update marker**:
   ```bash
   runbooks/update-marker.sh add nextcloud-mcp office 2 "0.184.5->0.202.1 image bump"
   ```
7. **HARD STOP GATE: the 0.195.5 calendar-addressing regression.** Proceed only if A or B passes:
   ```bash
   # A) data side: does any owned calendar still have a literal '%' in its URI?  (from §2.4 F)
   python3 -c 'import json; d=json.load(open("/tmp/ncmcp/events.before.json")); n=sum(v["pct_uri"] for v in d.values()); print("pct-URI calendars:", n); raise SystemExit(0 if n==0 else 1)' \
     && echo "7A PASS" || echo "7A FAIL"
   # B) code side: does the TARGET tag still unquote the name before encoding? FAIL CLOSED on fetch errors.
   REF=v0.202.1; F=/tmp/ncmcp/calendar.py.$REF; rm -f "$F"
   if ! gh api "repos/cbcoutinho/nextcloud-mcp-server/contents/nextcloud_mcp_server/client/calendar.py?ref=$REF" \
        -H 'Accept: application/vnd.github.raw' > "$F"; then echo "7B FAIL ($REF): fetch failed -- gate NOT evaluated"
   elif ! grep -q 'def _get_calendar_url' "$F"; then echo "7B FAIL ($REF): _get_calendar_url absent -- file moved/renamed, re-read by hand"
   elif [ "$(grep -c 'unquote(calendar_name)' "$F")" -eq 0 ]; then echo "7B PASS ($REF): unquote(calendar_name) count=0 -- re-read the new _get_calendar_url, then still run §4.6"
   else echo "7B FAIL ($REF): unquote(calendar_name) count=$(grep -c 'unquote(calendar_name)' "$F")"; fi
   # measured 2026-10-27: 7A FAIL (pct-URI calendars: 2); 7B FAIL (v0.202.1): count=1, calendar.py:582; same on master.
   #   History: PASS at v0.195.4 (count 0); FAIL at v0.198.0/.1/.3, v0.199.1, v0.200.5, v0.201.2, v0.202.1, master.
   #   REF=main -> fetch fails (default branch is `master`) -> prints "fetch failed", never PASS.
   # BOTH FAIL -> STOP. Do not merge/commit. runbooks/update-marker.sh clear nextcloud-mcp, and return to the operator with §1.6.
   #   This is the EXPECTED outcome today.
   ```
   *The gate can fail AND pass:* 7A read 2 on live data 2026-10-21. 7B prints
   PASS at v0.195.4 (count 0), FAIL at v0.202.1/master (count 1), and fails
   closed on a non-existent ref. Read the printed `7A`/`7B` verdict lines.

## 3. Steps

1. §2.0-2.7 green, i.e. §2.7 passed via A or B. Otherwise stop here.
2. Merge the Renovate PR (preferred path; the branch file is byte-identical to the BSD-sed edit below, `cmp` clean 2026-10-21):
   ```bash
   cd /Users/mu/code/cberg-home-nextgen || exit 1
   gh pr view 258 --json state,files --jq '.state, [.files[].path]'   # OPEN, ["kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml"]
   gh pr merge 258 --squash --delete-branch
   git fetch origin main && git merge --ff-only origin/main
   grep -n '^[[:space:]]*tag: ' kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml   # expect 34:              tag: 0.202.1
   git log -1 --format='%H %s' -- kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml | tee /tmp/ncmcp/bump.sha
   # expect subject: feat(container): update ghcr.io/cbcoutinho/nextcloud-mcp-server ( 0.184.5 → 0.202.1 ) (#258)
   ```
   **Fallback if #258 has been retargeted/closed** (do not merge a PR whose title no longer says 0.202.1): edit locally. Dry-tested 2026-10-27 on a scratch copy with macOS BSD sed: `34c34 <               tag: 0.184.5 / >               tag: 0.202.1`, one hunk; the result is byte-identical (`cmp`) to the PR #258 branch file.
   ```bash
   sed -i '' 's/^\([[:space:]]*tag: \)0\.184\.5$/\10.202.1/' kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml
   git diff --stat -- kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml    # expect 1 file, 1+/1-; 0 files = no-op: STOP
   printf '%s\n' 'feat(nextcloud-mcp): image 0.184.5 -> 0.202.1' '' \
     'Plan: runbooks/maintenance/plans/nextcloud-mcp-0.202.1.md (section 2.7 gate passed).' '' \
     'security_ref: F-80459b23' 'finding_refs: F-9af9baf7, F-80459b23' > /tmp/ncmcp/msg-bump.txt
   git commit --only kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml -F /tmp/ncmcp/msg-bump.txt
   git show --stat HEAD && git log -1 --format=%s   # ONE file; subject must be YOURS, else amend before push
   git push origin main && git rev-parse HEAD > /tmp/ncmcp/bump.sha
   ```
3. Reconcile (the SOP permits forcing in a window; `kustomization/nextcloud-mcp` is in ns `office`, verified live):
   ```bash
   flux reconcile kustomization nextcloud-mcp -n office --with-source
   flux reconcile hr -n office nextcloud-mcp
   ```
   Single replica, no volumes (premise), so no RWO/Recreate concern; no migration Job.
4. Watch:
   ```bash
   kubectl rollout status deploy/nextcloud-mcp -n office --timeout=180s
   kubectl get pods -n office -l app.kubernetes.io/name=nextcloud-mcp
   ```

## 4. Verification

Instruments (for `plan-premises.py --controls`):

- CONTROL: metric `kube_deployment_status_replicas_available`: `{namespace="office",deployment="nextcloud-mcp"}` must read `1` after the roll.
- CONTROL: metric `kube_pod_container_status_restarts_total`: `{namespace="office",container="main",pod=~"nextcloud-mcp-.*"}` must read `0` on the new pod 5 min after Ready.
- CONTROL: metric `container_memory_working_set_bytes`: same selector, must stay below `800Mi` (limit 1Gi).
- CONTROL: metric `ALERTS`: `{namespace=~"office|ai",alertstate="firing"}` must be EMPTY after settle (§2.5 exclusions apply).

1. **Flux Ready**:
   ```bash
   kubectl get helmrelease -n office nextcloud-mcp -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} chart={.status.history[0].chartVersion}{"\n"}'
   # expect: True chart=5.3.0
   ```
2. **New bytes running, clean start log**:
   ```bash
   kubectl get pod -n office -l app.kubernetes.io/name=nextcloud-mcp -o jsonpath='{range .items[*]}{.metadata.name} restarts={.status.containerStatuses[0].restartCount} {.status.containerStatuses[0].imageID}{"\n"}{end}'
   # expect ONE pod, restarts=0, imageID ending sha256:b842475624063f5c9e366a7af0e571848bd79bf2f6e345baac83ecf6bd9ae9e1
   #   (f6d88397… = old build still serving: rollout status green-lit the OLD generation -> wait/re-check, do not pass)
   kubectl logs -n office deploy/nextcloud-mcp > /tmp/ncmcp/log.after-start
   python3 - /tmp/ncmcp/log.after-start <<'EOF'
   import re, sys
   L=open(sys.argv[1]).read().splitlines()
   err=[l for l in L if re.search(r'(^|\s)(ERROR|CRITICAL)\s', l)]
   tb=[i for i,l in enumerate(L) if l.startswith('Traceback')]
   vc=[i for i in tb if i>0 and 'Could not parse vCard' in L[i-1]]
   print(f"lines={len(L)} ERROR/CRITICAL={len(err)} Traceback={len(tb)} vCard-attributed={len(vc)}")
   assert L, "EMPTY log -- wrong pod/container; do not pass"
   assert not err and len(tb)==len(vc), "unattributed ERROR/CRITICAL/Traceback -- read the log"
   EOF
   # vCard Tracebacks are known data (FN-less contacts). Re-run AFTER §4.6 against /tmp/ncmcp/log.after-events.
   # CAN FAIL: a reviewer injected one unattributed Traceback + one ERROR line into a copy and the assertion fired (0.199.1 review).
   ```
3. **CONTENTS ASSERTION (mcp 2.x lifespan; SAR plugin + multi-user middleware absent)**:
   ```bash
   kubectl logs -n office deploy/nextcloud-mcp > /tmp/ncmcp/log.now
   grep -c 'Starting MCP session in single-user BasicAuth mode' /tmp/ncmcp/log.now
   # expect 1 right after start and STILL 1 after §4.4's sessions (app.py:1038; app.py is unchanged v0.200.5 -> v0.202.1). On 0.184.5 it climbs per
   #   session: 46 on the live pod 2026-10-21. A climbing count = old build. 0 = INFO hidden -> the two absence checks
   #   below have no positive control and §4.4's grep becomes the binding check.
   grep -ciE 'plugin sar: (not available, skipping|registering tools)' /tmp/ncmcp/log.now    # expect >=1 (positive control)
   grep -ciE 'plugin sar: registering tools' /tmp/ncmcp/log.now                              # expect 0; >=1 -> STOP, §5
   grep -ci 'BasicAuthMiddleware enabled' /tmp/ncmcp/log.now                                 # expect 0 (app.py:3389, INFO);
   #   >=1 means multi-user mode is live -> the 0.200.1 401 path guards every consumer request -> STOP, §5.
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
   grep -ciE 'sar' /tmp/ncmcp/tools.after                                                   # expect 0
   grep -c '^nc_notes_' /tmp/ncmcp/tools.after                                              # expect 0: Notes app absent (§2.3) -> 0.202.0's
   #   nc_notes_list_notes is gated out by configure_app_tools. >=1 = Notes was installed since §2.3 -> re-read §1.2, not a FAIL by itself.
   wc -l < /tmp/ncmcp/tools.after                                                            # expect 117
   kubectl port-forward -n office svc/nextcloud-mcp 18000:8000 >/dev/null 2>&1 & PF=$!; sleep 2
   curl -s -X POST http://localhost:18000/mcp -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
     -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"plan-probe","version":"0"}}}' \
     | python3 -c 'import sys,json
   raw=sys.stdin.read(); data=[l[5:].strip() for l in raw.splitlines() if l.startswith("data:")]
   r=json.loads(data[-1] if data else raw)["result"]; print(r["protocolVersion"], r["serverInfo"].get("version"))' | tee /tmp/ncmcp/protocol.after
   kill $PF 2>/dev/null
   # expect "2025-06-18 0.202.1" (0.201.1 errors.py: NextcloudMCPServer defaults version to the package version).
   #   "1.29.0" = old 0.184.5 build still serving; EMPTY = a 0.185..0.201.0 build (wrong image) -> do not pass.
   ```
   117 + the exact 21 names were measured live on 0.195.4 (2026-09-26). 0.195.5..0.202.1 add no tool that registers HERE: 0.202.0's `nc_notes_list_notes` is the only new tool name and is app-gated (Notes absent, §1.2). Note: the `@mcp.tool` grep count (124 at v0.200.5, v0.201.2 and v0.202.1) is a weak proxy — the notes tool landed without moving it, because app tools register via `configure_app_tools`; the binding check is this gate's `comm`/`wc` against the live list. 0.201.0 adds only optional `startdate`/`color` params to Deck card tools (Deck app not installed here).
5. **CONTENTS ASSERTION (calendar LIST: same set, encoding-shape tolerant)**. This gate CANNOT see the §1.1 regression; §4.6 can.
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
   ```
6. **CONTENTS ASSERTION (per-calendar EVENT reads: the §1.1 regression)**:
   ```bash
   python3 /tmp/ncmcp/events.py /tmp/ncmcp/calendars.after /tmp/ncmcp/events.after.json
   python3 /tmp/ncmcp/events_gate.py /tmp/ncmcp/events.before.json /tmp/ncmcp/events.after.json
   # PASS: every calendar non-empty before is non-empty after, |delta| <= 2.
   # FAIL prints: "calendar #N (pct_uri=True): 200 -> 0 events (SILENT EMPTY READ)" -> §5 rollback.
   kubectl logs -n office deploy/nextcloud-mcp > /tmp/ncmcp/log.after-events   # re-run the §4.2 scan on this file
   ```
   *Demonstrated 2026-10-21 on 0.184.5:* `events.py … --emulate-double-decode` (sends exactly the URI the post-0.195.5 `_get_calendar_url` builds) read `[3, 0, 0, 0]` against a real `[3, 0, 200, 0]`, `isError=false`; feeding that into `events_gate.py` reports the 200 -> 0 SILENT EMPTY READ and exits 1. Before-vs-before PASSes. **Limit:** the second `%`-URI calendar holds 0 events in range, so counts cannot see a regression on it; §2.7 A covers it structurally.
7. **CONTENTS ASSERTION (0.192.0 BREAKING visible)**:
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
8. **CONTENTS ASSERTION (0.188.1 contacts)**:
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
9. **Memory + restarts**, 5 min after Ready:
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
10. **No new firing alerts**: re-run §2.5 into `/tmp/ncmcp/alerts.after` and `diff /tmp/ncmcp/alerts.before /tmp/ncmcp/alerts.after`. Expect `NONE FIRING` both times; a new alertname is a FAIL.
11. **The real consumers**:
    - OpenClaw (`ai`, mcporter). mcporter exits 0 on HTTP 500/`isError`, so the gate is the JSON body:
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
      (Live 2026-10-21: `NEXTCLOUD_MCP_URL=the in-cluster nextcloud-mcp service URL (port 8000, /mcp)`, auth header empty — the 0.200.1 401 path would not apply even if mounted.)
    - **Claude Desktop (attended).** Entry `nextcloud` runs `uvx mcp-proxy --transport streamablehttp https://nextcloud-mcp.<DOMAIN>/mcp` (HTTPRoute `nextcloud-mcp` on `envoy-internal/https` -> svc :8000). Fully quit and relaunch Desktop after the roll (the proxy holds a session to the old pod), list the root folder, **ask for this week's events from the busiest calendar** (the human form of §4.6), and confirm the tool count grew by 21. **Idle re-check (0.202.1, mcp 2.3 30-min session idle timeout):** leave Desktop idle >= 35 min, then list the root folder again. PASS = it answers (mcp-proxy re-initialized after the reap). FAIL prints a session-not-found / 404 error in Desktop until relaunch: record it on F-9af9baf7 as a client issue (mcp-proxy does not re-init) — it is the documented upstream behaviour, not a rollback trigger. A Desktop-only failure with §4.4/§4.11 green is a client-pin issue, not a rollback trigger.
12. **CONTENTS ASSERTION (0.199.0 packaging: semantic/documents extras still in the image)**:
    ```bash
    kubectl exec -n office deploy/nextcloud-mcp -c main -- /opt/venv/bin/python -c \
      'import importlib.util as u; m=["pymupdf","pypdfium2","docx","openpyxl","qdrant_client"]; r={x: u.find_spec(x) is not None for x in m}; print(r); raise SystemExit(0 if all(r.values()) else 1)' \
      && echo "4.12 PASS" || echo "4.12 FAIL"
    # FAIL -> nc_webdav_read_file returns PDFs/Office raw with the "pip install 'nextcloud-mcp-server[documents]'" note -> §5.
    ```
13. **CONTENTS ASSERTION (0.200.2 OCS header refactor: Talk still answers)**. Talk is pure OCS; a call site that lost `OCS-APIRequest: true` is refused by Nextcloud.
    ```bash
    /tmp/ncmcp/call.sh tools/call '{"name":"talk_list_conversations","arguments":{}}' > /tmp/ncmcp/talk.after
    python3 - /tmp/ncmcp/talk.before /tmp/ncmcp/talk.after <<'EOF'
    import json, sys
    def toks(p):
        r = json.load(open(p))["result"]
        txt = " ".join(c.get("text", "") for c in r.get("content", []))
        assert not r.get("isError"), f"{p}: isError -- {txt[:200]}"
        sc = r.get("structuredContent") or json.loads(txt)
        assert sc.get("success") is True, f"{p}: success={sc.get('success')!r}"
        return {c["token"] for c in sc["results"]}
    b, a = toks(sys.argv[1]), toks(sys.argv[2])
    assert b, "baseline has 0 conversations -- gate cannot see an empty read; pick another OCS tool"
    assert a == b, f"conversation set differs: missing={len(b-a)} added={len(a-b)}"
    print(f"4.13 Talk/OCS PASS: {len(a)} conversations before and after")
    EOF
    # Baseline 2026-10-21: success=True, 2 conversations. FAILS on: isError/OCS 997 (header lost), success!=True,
    #   or an empty/changed token set (a new DM created during the window = re-run, not a pass).
    ```
14. **Close out**: `runbooks/update-marker.sh clear nextcloud-mcp`. Set this plan `executed` (0.201.2 is already `superseded`). F-9af9baf7/F-80459b23 are script-owned and should close on the next sweep — verify, don't assume.

## 5. Rollback

Stateless (premises: no volumes, no DB keys), so rollback is an inverse image-tag edit — NOT `git revert`, which refuses (rc=128) in this shared worktree whenever another session has staged anything. Dry-tested 2026-10-27 on a scratch copy (macOS BSD sed): forward sed gives `34c34 <               tag: 0.184.5 / >               tag: 0.202.1`, `cmp`-identical to the PR #258 branch file; inverse sed then restores the original byte-identical (`cmp` clean). The inverse sed matches `0\.202\.1$` — the superseded plans' inverse seds match tags never deployed and would be no-ops; do not copy them.

```bash
cd /Users/mu/code/cberg-home-nextgen || exit 1
git fetch origin main && git merge --ff-only origin/main
sed -i '' 's/^\([[:space:]]*tag: \)0\.202\.1$/\10.184.5/' kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml
git diff --stat -- kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml    # expect 1 file 1+/1-; 0 files = no-op: STOP
printf '%s\n' 'revert(nextcloud-mcp): image 0.202.1 -> 0.184.5' '' \
  'Rollback per runbooks/maintenance/plans/nextcloud-mcp-0.202.1.md section 5' \
  '(stateless bridge, image tag only). Reverts the commit recorded in /tmp/ncmcp/bump.sha.' > /tmp/ncmcp/msg-revert.txt
git commit --only kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml -F /tmp/ncmcp/msg-revert.txt
git show --stat HEAD && git log -1 --format=%s    # ONE file; subject = revert(nextcloud-mcp): image 0.202.1 -> 0.184.5
git push origin main
flux reconcile kustomization nextcloud-mcp -n office --with-source && flux reconcile hr -n office nextcloud-mcp
kubectl rollout status deploy/nextcloud-mcp -n office --timeout=180s
kubectl get pod -n office -l app.kubernetes.io/name=nextcloud-mcp -o jsonpath='{range .items[*]}{.metadata.name} {.status.containerStatuses[0].imageID}{"\n"}{end}'
# expect imageID ending sha256:f6d8839722587f2cd37ec5218a18479f9e313be9904ad4f6bbb36f98bc827065
```
Renovate will re-open/refresh PR #258 afterwards; that is expected — the deny rule keeps it held.

Confirm the cluster is back:
- Re-run §4.4: `tools.after` == `tools.before` (96, `comm` empty both ways), protocol `2025-06-18 1.29.0`.
- Re-run §4.6 into `events.revert.json` gated against `events.before.json`: the busiest calendar back at its count.
- Re-run §4.13 and §4.11 (OpenClaw); relaunch Claude Desktop.
- If the failure was consumer-side, note it on F-9af9baf7 via `policy-cli.py finding detail`; the fix there is pinning the client.


## 6. Interference notes

- **Consumers, not shared infra.** OpenClaw (`ai`, mcporter entry `nextcloud`) and Claude Desktop lose or change tools silently if this goes wrong. The §1.1 regression is precisely a silent failure ("no events", not an error), which is why §4.6 exists and the Desktop check asks for events.
- **Nextcloud server work** (`nextcloud-9.4.1` nightly 10-28, `nextcloud-whiteboard-2.1.2` nightly 10-29, `redis-fleet-8.10.3` sun 11-29, `bitnamilegacy-exit-nextcloud-db` if revived): every §4 contents gate is a live call into that server, so never share a slot. A Nextcloud server minor/major move fails premise `nextcloud-server-is-35` closed or invalidates the §2.4 baselines: re-take them after it.
- **Prometheus**: §2.5/§4.9/§4.10 read it. No kube-prometheus-stack plan is open on 2026-10-27; a future one must list this plan and vice versa.
- **Node rolls** (`talos-linux-1.14.4` vetted sun-attended:2026-11-01, `exclusive: true`; `talos-power-tuning-ab` exclusive) restart this pod and Nextcloud; exclusivity keeps them out of this slot. If adjacent, take §2.4 baselines AFTER the roll.
- **app-template**: HR on 5.3.0; no open app-template plan touches this file. A later app-template bump on this HR must list this plan.
- **Attended only.** Deny rule + `capability_change: true`. Never `nightly`. Nothing here touches Longhorn, cert-manager, cilium, coredns or the Gateways.
- **Supersession** (§1.5): `nextcloud-mcp-0.201.2` is `superseded` and cross-listed in `conflicts_with`. 0.198.0/0.199.1/0.200.2/0.187.1 were already `superseded`. Only this file owns F-9af9baf7/F-80459b23 as a live plan.
- **Session idle timeout (0.202.1)**: any MCP client holding a session idle > 30 min is reaped after the bump. OpenClaw opens per-call sessions (unaffected); Claude Desktop is checked in §4.11.

## 7. What I could not verify (2026-10-27)

- **Whether 0.202.1 (or 0.195.4) remediates F-80459b23.** Per-tag scan question; result goes on the record, not here.
- **That the image reports `serverInfo.version == "0.202.1"`.** Derived from source (`importlib.metadata.version("nextcloud-mcp-server")` with the Dockerfile's `uv sync` install); `errors.py:17` imports stdlib `importlib.metadata` at v0.202.1 (the dropped `importlib-metadata` backport package does not matter); not observed on a running 0.201.x/0.202.x pod. If it reads a different non-empty string, confirm the imageID digest (§4.2) and treat that as the binding check.
- **Upstream fix timeline.** No upstream issue exists for the literal-`%` calendar-URI case (searched 2026-10-27).
- **caldav 3.2.1 -> 3.6.0 / icalendar-searcher 1.0.6 -> 1.3.0 behaviour on our data.** Lockfile-only evidence; not run. §4.5-§4.7 are the gates.
- **mcp-proxy (Claude Desktop) behaviour after a 30-min session reap.** Not tested; §4.11 idle re-check observes it.
- **Per-calendar event counts** carried from 2026-10-25; only the calendar list / `%` count was re-measured 2026-10-27.
- **Write-path behaviour on the `%`-URI calendars**, the 0.199.1 fixed-offset -> UTC change, Talk thread writes (0.200.0) and Deck card fields (0.201.0): not exercised (writes against household data; Deck absent).
- **The second `%`-URI calendar** has 0 events in range; §4.6 cannot see a regression on it (§2.7 A covers it structurally).
- **Talk baseline** (2 conversations) is carried from 2026-10-21, not re-measured today; §2.4 G re-takes it on the day.
