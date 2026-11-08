---
plan_id: nextcloud-mcp-0.206.0
component: nextcloud-mcp
pr: 258                               # Renovate "feat(container): update ghcr.io/cbcoutinho/nextcloud-mcp-server ( 0.184.5 → 0.206.0 )",
                                      # branch renovate/ghcr.io-cbcoutinho-nextcloud-mcp-server-0.x (retargeted a 9th time; was
                                      # 0.204.0 in nextcloud-mcp-0.204.0). OPEN. Held by the `*nextcloud-mcp*` `max: patch` deny
                                      # rule (0.x minor line move). Branch-head subject verified 2026-11-08 (git log origin/…).
kind: image
current: "0.184.5"
target: "0.206.0"                     # Verified 2026-11-08: GHCR 0.206.0 index sha256:977768c9…55b1ba == `latest`; 0.206.1 and
                                      # 0.207.0 404; GitHub v0.206.0 is Latest (published 2026-11-07T13:59Z), not a pre-release.
update_type: minor                    # semver label only. At major 0 the MINOR is the breaking axis; this hop crosses TWENTY-TWO
                                      # minor lines (0.185 .. 0.206). 0.185..0.204.0 carried from nextcloud-mcp-0.204.0; 0.204.1..0.206.0
                                      # read here per tag + source diff (§1.2). NEW BREAKING at 0.206.0: unknown tool arguments are refused.
risk: medium                          # stateless bridge, cheap tag rollback, nothing forward-only. BUT (1) the 0.195.5
                                      # calendar-addressing regression is STILL present at v0.206.0 AND on master (§1.1) and the data
                                      # that triggers it is still live (2 of 4 calendars, re-measured 2026-11-08), so the EXPECTED
                                      # outcome today is a STOP at §2.7 before any commit; (2) 0.206.0 turns a silently-ignored
                                      # undeclared tool argument into isError, which a consumer that guesses arguments will hit (§1.2, §4.15);
                                      # (3) Starlette 0.x -> 1.x runtime dependency (0.204.2).
est_duration_min: 45
needs_reboot: false
touches:
  namespaces: [office]
  resources:
    - helmrelease/nextcloud-mcp
    - deployment/nextcloud-mcp
                                      # httproute/nextcloud-mcp + svc/nextcloud-mcp re-render from the same HR but their spec
                                      # does not change (the image tag is the whole diff), so they are not perturbed.
  shared: [monitoring]                # READ-only: §2.5/§4.9/§4.10 read Prometheus (the window's instrument). No gateway, CNI,
                                      # DNS, storage or shared DB is perturbed. Consumers (ai/openclaw via mcporter, Claude Desktop
                                      # via the envoy-internal HTTPRoute) are blast radius, not shared infra (§6).
depends_on: []                        # Flux `dependsOn: nextcloud` is ordering-only; no note in 0.185..0.206.0 states a
                                      # minimum Nextcloud server version.
conflicts_with:
  - nextcloud-mcp-0.204.0             # SUPERSEDED BY THIS PLAN (§1.5): same component, same HR line, same PR #258.
  - nextcloud-mcp-0.203.0             # superseded transitively (already superseded by 0.204.0's lineage; still `blocked` on disk).
  - redis-fleet-8.10.3                # vetted, sun-attended:2026-11-29; restarts office/nextcloud-redis + deployment/nextcloud
                                      # (every §4 contents gate is a live call into Nextcloud).
  - bitnamilegacy-exit-nextcloud-db   # blocked/unwindowed; quiesces Nextcloud if revived.
  - helm-drift-detection              # vetted sat-attended:2026-11-28; adds a spec field to EVERY HelmRelease incl.
                                      # helmrelease/nextcloud-mcp -> must not share a slot with this HR's image change.
  - flux-oci-chart-sources            # vetted sun-attended:2026-12-13; re-points bjw-s app-template HRs to an OCIRepository;
                                      # this HR's sourceRef is HelmRepository bjw-s -> it re-renders this HR.
  - envoy-gateway-1.10.0              # draft; Claude Desktop reaches this service through envoy-internal (§4.11); a gateway
                                      # data-plane roll in the same slot makes a Desktop failure unattributable. NEW vs 0.204.0.
  - talos-linux-1.14.5                # vetted sun-attended:2026-11-22, exclusive node roll; evicts this pod and Nextcloud.
  - etcd-timeouts-5000-500            # blocked; restarts etcd on all control-plane nodes (API unavailability blinds every §4 kubectl gate).
                                      # No kube-prometheus-stack plan is open on 2026-11-08; any new one must be added here
                                      # because §2.5/§4.9/§4.10 read Prometheus.
exclusive: false
security_ref: F-80459b23              # security driver; detail stays on the record (§1.5).
capability_change: true               # vs LIVE 0.184.5: +25 tools (6 WRITE: 4 nc_webdav_* tag/trash/version writes from
                                      # 0.188/0.189, nc_webdav_edit_file + nc_mail_save_draft from 0.203.0), behaviour changes on
                                      # live tools (0.192.0 bulk-ops series default, 0.188.1 contacts photo opt-in, 0.187.0
                                      # find_availability, 0.199.1 fixed-offset datetimes stored as UTC, 0.200.0 Talk thread
                                      # params, 0.201.0 Deck card params, 0.203.0 nc_webdav_read_file line ranges, 0.204.0
                                      # contacts create/update write vCard N, 0.205.0 nc_calendar_list_events `truncated` field +
                                      # limit-after-filters, 0.206.0 undeclared tool arguments REFUSED), 0.202.1 30-min MCP session
                                      # idle timeout, and the 0.195.5 calendar change.
rollback_class: git-revert            # no PVC, no volumes, no DATABASE_URL/TOKEN_STORAGE_DB (premises). Executed as an inverse
                                      # tag edit (§5) because `git revert` refuses in the shared worktree when anything is staged.
                                      # Caveat: drafts saved / files edited / contacts written via the new WRITE paths stay in
                                      # Nextcloud after a rollback (household data written by a consumer, not by this plan).
finding_refs: [F-80459b23, F-9af9baf7] # F-80459b23 = security finding (open, last seen 2026-11-06). F-9af9baf7 = version
                                      # finding (open, title "0.184.5 → 0.204.3 (minor)" at 2026-11-06 -- it lags the PR; script-owned).
                                      # `policy-cli.py finding list --grep nextcloud-mcp` 2026-11-08: these two + F-f02df447
                                      # (AR-029 accepted residual, not owned by a plan).
review: null
status: blocked                       # 2026-11-08 reviewer fix: §2.7 STOP fires (7A=2 live, 7B count=1 at v0.206.0 and master) and the
                                      # operator decision of 2026-10-23 ("wait for upstream", §1.7 A) is NOT satisfied by 0.206.0.
                                      # Unblock only on an upstream tag where _get_calendar_url no longer blindly unquotes (or if the
                                      # operator reverses the decision: options B/C). Do not schedule; re-review when upstream moves.
window: null                          # Unblock condition (carried): an upstream tag whose calendar.py no longer does
                                      # `unquote(calendar_name)` in _get_calendar_url AND §2.7 passes live. Then: attended slot only
                                      # (sat/sun), never nightly. Human-gated: 0.206.0 BREAKING touches the tool-call contract of
                                      # every tool the consumers use (§1.2).
premises:
  - id: image-is-still-0.184.5
    why: >-
      current: and the rollback target are 0.184.5. If the cluster has moved, the
      diff, the baselines and the rollback digest are wrong.
    run: kubectl get deploy -n office nextcloud-mcp -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: ghcr.io/cbcoutinho/nextcloud-mcp-server:0.184.5
  - id: renovate-pr-258-still-targets-0.206.0
    why: >-
      Drift detector. The Renovate branch commit subject is the PR title. If
      upstream ships 0.206.1/0.207.x Renovate rewrites it and this fails, which
      forces a §1.2 re-read of the new tags and a §2.7-B re-run before anything
      merges. Run the §2.0 git fetch first; a stale local ref is the only way
      this can read green on a drifted PR, and §2.0's registry probe covers that.
    run: git log -1 --format=%s origin/renovate/ghcr.io-cbcoutinho-nextcloud-mcp-server-0.x
    expect_exact: "feat(container): update ghcr.io/cbcoutinho/nextcloud-mcp-server ( 0.184.5 → 0.206.0 )"
  - id: nextcloud-server-is-35
    why: >-
      §4.5/§4.6/§4.13 read CalDAV/OCS from this server. Live 35.0.2 on
      2026-11-08. Patch drift tolerated; a 36.x or 34.x server fails this closed
      and the §2.4 baselines must be re-taken against the new server.
    run: kubectl get deploy -n office nextcloud -o jsonpath='{.spec.template.spec.containers[?(@.name=="nextcloud")].image}'
    expect_matches: 'docker\.io/nextcloud:35\.0\.[0-9]+(@sha256:[0-9a-f]+)?$'
  - id: deployment-mode-still-single-user-basic
    why: >-
      The 0.185.0 elicitation break, the 0.190.0/0.198.1 CIMD/OAuth changes,
      the 0.199.0 oidc-2.5 change, the 0.200.1 BasicAuthMiddleware 401 path, the
      0.201.2 AS-proxy refresh-error change, the 0.203.0 `mail.draft` scope and the
      0.204.1 resource-scope enforcement (all scope gates only apply in OAuth modes)
      are inert in single_user_basic. Any other mode voids §1.2/§1.3.
    run: kubectl get secret -n office nextcloud-mcp-config -o json | jq -r '.data.MCP_DEPLOYMENT_MODE' | jq -Rr '@base64d'
    expect_exact: single_user_basic
  - id: exactly-four-config-keys
    why: >-
      Proves no DATABASE_URL/TOKEN_STORAGE_DB (free rollback), no
      VECTOR_SYNC_ENABLED/ENABLE_SEMANTIC_SEARCH/EMBEDDING_GATEWAY_URL/SAR_ENABLED
      (0.196-0.199 indexing/SAR surface stays off), no CIMD_ALLOWED_HOSTS, no
      COLLABORA_URL/DOCLING_API_URL, no LOGIN_FLOW_OIDC_*, no OTEL_* (the 0.203.3
      HTTPX2ClientInstrumentor change is inert without an exporter), and no boolean
      env whose spelling the 0.205.4 config warning could flag.
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
generated: "2026-11-08"
---

## 1. Summary & why held

`kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml:34` pins
`ghcr.io/cbcoutinho/nextcloud-mcp-server` at `0.184.5` (live, verified
2026-11-08, pod `nextcloud-mcp-55ff568864-4z4rl`, imageID `sha256:f6d88397…c827065`).
Renovate PR **#258** (retargeted again: 0.204.0 -> **0.206.0**, upstream head)
moves it. The auto-updater holds it because this is a 0.x release-line move
(0.184 -> 0.206): at major 0 the minor is the breaking axis, and the
`*nextcloud-mcp*` deny rule (`max: patch`) demands a human read of every minor
hop. Security-driven: F-80459b23 (§1.5).

**Verdict: STILL DO NOT RUN AS-IS. 0.206.0 does NOT resolve the blocker of
`nextcloud-mcp-0.198.0` .. `0.204.0`**, and it adds a second human-gate item
(the 0.206.0 BREAKING change below). The operator decided on 2026-10-23 to wait
for upstream; the unblock condition is not met. This plan SUPERSEDES
`nextcloud-mcp-0.204.0` (§1.5).

### 1.1 The blocker, re-measured 2026-11-08 (fresh, not carried)

- **Code:** `_get_calendar_url()` still returns
  `encode_dav_url(f"{self._calendar_home_url}{unquote(calendar_name)}/")` at
  `nextcloud_mcp_server/client/calendar.py:586` on **v0.206.0 and master**
  (`gh api … contents … ?ref=`; `def _get_calendar_url` at :579 on both; the
  line moved 4 down from :582 because 0.205.0 edited the same file). The 0.205.0
  calendar hunks (limit/filter ordering, `BULK_EVENT_LIMIT`) do not touch the
  addressing.
- **Data:** measured 2026-11-08 through the running 0.184.5 pod (read-only
  `tools/call nc_calendar_list_calendars`): **4 calendars, 2 with a literal `%`
  in their URI** (`%3Cowner%3E%2bFamily%2b%2528Google%2bCalendar%2bimport%2529` and
  `%3Choliday-calendar%3E%2b%2528…%2529`) — unchanged since 2026-10-21. Live tool
  count on 0.184.5: **96** (unchanged).
- **Effect (carried reproduction, 2026-11-02, same code):** real per-calendar counts
  `[3, 0, 200, 0]`; with `--emulate-double-decode` (exactly the URI the post-0.195.5
  `_get_calendar_url` builds) `[3, 0, 0, 0]` — the busiest calendar silently reads
  **empty**. Feature loss; operator policy is "interruption OK, data/feature loss not".
- **Upstream:** no issue exists for the literal-`%` case (searched 2026-11-02; not
  re-searched today — §2.0 re-checks). Nine retargets (0.198 -> 0.206) have passed
  without a fix.

§2.7 therefore fails on both legs today and the window run ends there with
nothing committed.

| tag | GHCR (anonymous token, OCI index, 2026-11-08) |
|---|---|
| `0.184.5` (live) | 200, `sha256:f6d8839722587f2cd37ec5218a18479f9e313be9904ad4f6bbb36f98bc827065` (= running pod `imageID`) |
| `0.195.4` (last tag WITHOUT the regression; option B) | carried: `sha256:24417dcb804fc65bcb8712226bf70be71018aefd2ec7b27e9392a4d4e1ed707c` |
| `0.204.0` (previous target) | 200, `sha256:debf33ba775c2df785b8f079612ead31d4ab448b93048b6e2f2cb7ad94eb9479` |
| `0.205.0` | 200, `sha256:1bc06dafe658a932498eba22a7f6f39055769866bf24afc6edbc11b43b690bbf` |
| **`0.206.0` (target)** | **200, `sha256:977768c9107c1fee86905fc96f703646d32f9191b10ca9da0bdabf47e055b1ba`** |
| `latest` | 200, identical to 0.206.0 |
| `0.206.1`, `0.207.0` | 404 |

v0.206.0 was published 2026-11-07T13:59Z; it clears the 48 h
`minimum_release_age_hours` gate at 2026-11-09T13:59Z. Re-run §2.0.

### 1.2 What changed 0.204.0 -> 0.206.0, per tag + source diff

Source: `gh api compare v0.204.0...v0.206.0` (98 commits, 92 files; most are tests,
CI and Renovate digest bumps). Runtime-relevant files: `errors.py`, `client/{calendar,
contacts,webdav,ocs,dav_errors}.py`, `server/{calendar,contacts,deck,notes,cookbook,
__init__}.py`, `utils/{parsing,text_edit,validation}.py`, `auth/*`, `config.py`,
`sar_case.py`, `vector/*`. **No tool is added or removed** (no `@mcp.tool` /
`async def nc_` line added or removed; the `nc://capabilities` RESOURCE handler was only
MOVED from `app.py` to `server/__init__.py` and scope-gated: a resource, not a tool). `Dockerfile`: base `python:3.14-slim-trixie`
digest bump only. `pyproject`: **`starlette<1.0` -> `<1.11`** (runtime), `version`.

| tag | release note (verbatim) | applies to us? |
|---|---|---|
| 0.204.1 | *"auth: enforce OAuth scopes on MCP resources"*; *"gate nc://capabilities and guard every registered resource"* | Inert: scopes only gate in OAuth modes (premise `deployment-mode-still-single-user-basic`). |
| **0.204.2** | *"deps: update dependency starlette to v1"*; *"migrate off decorators removed in Starlette 1.0"* | **Applies — the whole HTTP layer moves to Starlette 1.x.** Nothing the plan reads is a Starlette API directly, but a startup/route break surfaces as a crash loop or a dead `/mcp`; gates: §4.2 (clean start log), §4.3, §4.4 (initialize + tools/list answer), §4.11. Probes are tcpSocket, so a green rollout does NOT prove `/mcp` works. |
| 0.204.3 | *"resolve ty 0.0.97 diagnostics"* | Type-check only. |
| **0.205.0** | *"calendar: report truncation in list_events and apply min_duration_minutes"*; *"apply event filters before the limit and honour limit across calendars"*; *"raise bulk-operation match cap from 50 to BULK_EVENT_LIMIT"*; *"reject negative list_events limit"*; sar: refused case-file write -> 403 | **Applies to a tool we have.** `nc_calendar_list_events` fetches `limit+1`, returns the EARLIEST `limit` events AFTER filters and adds a new response field `truncated: bool`; negative `limit` -> ToolError. Consumers that read the old shape keep working (field is additive); counts for the busiest calendar (200 at `limit=200`) may now report `truncated=true`. Bulk operations can match more events than 50 (write path; not exercised). SAR is absent (premise). Gate: new §4.14. |
| 0.205.1 | *"log what was swallowed where a handler falls back silently"* | Logging only; **more WARNING lines are expected** — §4.2's scan matches ERROR/CRITICAL/Traceback only. |
| 0.205.2 | *"keep CRLF pairs intact in apply_edits"*, *"make four payload parsers total…"*, webhook warnings | `apply_edits` backs `nc_webdav_edit_file` (WRITE, not exercised). |
| 0.205.3 | *"keep an escaped ; or , inside one N, ADR, NICKNAME or CATEGORIES component on read"* | Read path of contacts (vCard N). Gate: §4.8 reads contacts. |
| 0.205.4 | *"config: warn once per unrecognised boolean"*; *"auth: refuse any backslash in _safe_next_url"* | Config warning only; OAuth redirect helper inert here. |
| **0.206.0 BREAKING** | *"BREAKING CHANGE: tool calls carrying arguments absent from the tool's inputSchema now return an error (isError) instead of succeeding with the extra keys ignored."* | **Applies to EVERY tool, and to every consumer.** `NextcloudMCPServer.call_tool` raises `ToolError("<tool>: unknown argument(s) '<k>'; valid: …")` before any Nextcloud request, and `list_tools` now advertises `additionalProperties: false` on every `inputSchema` (upstream PR #1792, `errors.py`; top-level keys only). It does NOT change what valid calls do. Consequence: a client (an LLM choosing arguments via mcporter, or Claude Desktop) that was passing a wrong/renamed argument and silently getting "success" will now get an error — correct behaviour, but a visible one, and the only change in this hop that can turn a previously "working" consumer call into a failure. Gates: §2.4 H (our gate calls use only declared arguments), §4.15. |

**Net surface vs live 0.184.5: still 96 + 25 = 121** (derived from source: no tool
added/removed in 0.204.0..0.206.0; not observed on a running pod). §4.4 expects
protocol line `2025-06-18 0.206.0` (`errors.py:229` at v0.206.0:
`kwargs.setdefault("version", version("nextcloud-mcp-server"))`, pyproject
`version = "0.206.0"`).

**How the consumers use this server (measured/read 2026-11-08):**

- **OpenClaw (ai, upgraded to 2026.11.1 / node 24.22.2 the same day):** mcporter 0.17.0
  with a registration `nextcloud` -> `$NEXTCLOUD_MCP_URL` =
  `the in-cluster service endpoint nextcloud-mcp.office.svc.cluster.local:8000/mcp` (ConfigMap
  `openclaw-mcp-servers`, rendered at container start by the helmrelease init script;
  `kubernetes/apps/ai/openclaw/app/mcporter-config.yaml`), auth header EMPTY. The
  family skills (`nc`, `cal`, `contacts`, `nextcloud-mail`) in `skills-configmap.sops.yaml`
  talk to Nextcloud DIRECTLY (cal.py: "Direct CalDAV — no MCP layer"); the workspace
  doc says "Files: `nc` or the Nextcloud MCP". So the MCP server is an agent-chosen
  alternate path, NOT a scripted one: no repo file pins a tool name or argument list
  (grep of the repo and of the live workspace found none). The 0.206.0 risk for OpenClaw
  is therefore an LLM occasionally guessing an argument and now seeing an error it can
  self-correct from (the error text lists the valid names).
- **Claude Desktop (attended):** `nextcloud` entry via `uvx mcp-proxy --transport
  streamablehttp https://nextcloud-mcp.<DOMAIN>/mcp` (memory `nextcloud_mcp.md`).
  Same reasoning; plus the 0.202.1 30-minute session idle timeout.

### 1.2a 0.203.0 -> 0.204.0, carried from nextcloud-mcp-0.204.0 §1.2

- **0.203.1** VTODO partial-dict merge now raises instead of destroying a todo (safety fix; write path).
- **0.203.2** `nc_calendar_manage_calendar(action="list")` returns ONE content block `{calendars, total_count}`
  (was one block per calendar); tables row payload parse fix.
- **0.203.3** every Nextcloud call (WebDAV, CalDAV auth, CardDAV, OCS/Talk, Mail) moved `httpx` -> `httpx2`
  (source-only evidence; gates §4.2/§4.5/§4.6/§4.8/§4.11/§4.13).
- **0.204.0** `nc_contacts_create_contact` / `nc_contacts_update_contact` write vCard N (optional new params; write path).

### 1.3 0.202.1 -> 0.203.0, carried from nextcloud-mcp-0.203.0 §1.2

- 0.202.2: `POST /api/v1/vector-viz/search` deprecated — inert (vector sync off).
- **0.203.0**: `nc_mail_save_draft` (WRITE, `@require_scopes("mail.draft")`, scope
  only gates in OAuth modes) + `nc_mail_view_attachment`; `nc_webdav_edit_file`
  (WRITE, in-place edit of plain-text files) + `nc_webdav_view_image` (server-side
  Pillow decode, bounded by upstream's "bound image decode memory" fix; §4.9 reads
  idle memory only); `nc_webdav_read_file` line-range params (additive). New base
  digest `python:3.14-slim-trixie` + `uv` 0.13.6.

### 1.4 0.184.5 -> 0.202.1, carried from nextcloud-mcp-0.202.1 §1.2/§1.3

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
- **0.200.0**: Talk thread params (optional, additive). 0.200.1: BasicAuthMiddleware
  401 path — multi-user only (inert; §4.3 asserts absent). **0.200.2**: OCS-APIRequest
  header moved into the httpx client factory -> §4.13 Talk/OCS gate (doubly relevant
  now that 0.203.3 swapped that factory to httpx2).
- **0.201.0**: Deck card params (Deck absent -> inert). **0.201.1**: handshake
  advertises `serverInfo.version` = package version -> §4.4.
- **0.202.0**: `nc_notes_list_notes`, app-gated (Notes not installed -> 0 `nc_notes_*`, §4.4).
- **0.202.1**: mcp 2.3 30-minute streamable-HTTP session idle timeout (§4.11 Desktop idle
  re-check) + broad relock (`caldav` 3.2.1 -> 3.6.0, `icalendar-searcher` 1.0.6 -> 1.3.0,
  `mcp` 2.1.1 -> 2.3.0, …). caldav/icalendar-searcher sit under every calendar tool ->
  §4.5/§4.6/§4.7 are the gates.
- Additive: 0.186.0 12 `nc_shopping_list_*` (app absent -> calls 404), 0.188/0.189
  9 `nc_webdav_*` tag/trash/version tools (4 WRITE), 0.188.1 contacts photo opt-in
  + paging (§4.8), 0.187.0 real `find_availability`.

### 1.5 Security driver and supersession

> **Security driver: detail withheld from this public repo.**
> Tracked as **F-80459b23** (`security`). Quote the contextual tier from the sweep board, not the raw scanner severity.
> - Dashboard: `https://sweep.<DOMAIN>/findings/F-80459b23`
> - CLI: `runbooks/policy-cli.py finding show F-80459b23`

`F-f02df447` (`[AR-029]`, accepted) is the residual base-OS tally on the same
image. Whether 0.195.4 (option B) or 0.206.0 remediates the F-80459b23 set is a
per-tag scan question; the answer goes on the record
(`policy-cli.py finding detail F-80459b23`), never into this file. 0.206.0 carries
a new base-image digest (`python:3.14-slim-trixie` -> `af8a5aa…`) and a relock, so a
0.204.0 scan result does NOT carry blindly.

**Supersession: this plan SUPERSEDES `nextcloud-mcp-0.204.0`** (and transitively
`-0.203.0`, `-0.202.1`). Dispatched as a new plan_id for the new target on the
coordinator's instruction (the plans README prefers refresh-in-place; the
carry-across is done by hand). This planner does NOT edit the older files. Carried:
`pr`, `finding_refs`, `security_ref`, the §1.7 decision, the §2.7 STOP gate, all §4
gates, the §5 inverse-sed rollback. Changed vs 0.204.0: target/digest/PR-title
premise; §1.1 re-measured; §1.2 read at 0.204.1..0.206.0; protocol expectation
`0.206.0`; log-line refs `app.py:1046`/`:3390`; §2.4 H and §4.14/§4.15 added; two
OpenClaw consumer checks added as the §2.8 pre-check; `conflicts_with` gains `envoy-gateway-1.10.0`,
`talos-linux-1.14.5`, `etcd-timeouts-5000-500`.

**Owed by the coordinator (this planner writes only this file):**
1. Set `nextcloud-mcp-0.204.0` to `status: superseded`, `superseded_by:
   nextcloud-mcp-0.206.0`, and do the same for `-0.203.0` (still `blocked`); they own
   F-80459b23/F-9af9baf7 until then, and `conflicts_with` here keeps the three from
   sharing a slot. `-0.202.1` is already `superseded_by: nextcloud-mcp-0.203.0` — leave it.
2. `redis-fleet-8.10.3` / `helm-drift-detection` / `flux-oci-chart-sources` /
   `envoy-gateway-1.10.0` should list this plan reciprocally.
3. Re-key the home-operation `go_no_go`/blocked issue for nextcloud-mcp to this id.

### 1.6 Why this is still a plan and not a DECIDE re-route

The judgement call (wait vs 0.195.4 vs data surgery vs accept) was already
taken by the operator on 2026-10-23 and is recorded here; what remains is a
window action gated on an upstream event, which is exactly what §2.7 B
expresses. BUT: with no upstream issue filed, "wait" has no end condition, and
the security finding stays open for as long as it lasts. The coordinator should
surface that (option A's cost below) rather than let a ninth retarget pass
silently. File the upstream issue (text in §1.7 A) — it is the one action that
can end the wait.

### 1.7 The operator decision (unchanged; operator chose A on 2026-10-23)

| option | what | cost |
|---|---|---|
| **A. Wait for upstream** (CHOSEN 2026-10-23) | Still no upstream issue exists — filing one is the practical prerequisite. Issue text: *"`_get_calendar_url` unquotes calendar names; Nextcloud calendar URIs CAN contain a literal `%` (created by CalDAV clients that percent-encode the URI); reads silently return empty."* Retarget to the first tag whose `_get_calendar_url` no longer unquotes blindly; §2.7 B detects that. | Security finding stays open until then. Seven upstream retargets (0.198 -> 0.204) have now passed without a fix; with no issue filed, "wait" has no end condition. |
| B. Take 0.195.4 now | Revive `nextcloud-mcp-0.187.1` (superseded) with this plan's §4.6 event gate; park this file. | Only worth it if 0.195.4 remediates F-80459b23 (§1.5). |
| C. Change the data | Recreate the two `%`-URI calendars with clean URIs, then run this plan (§2.7 A passes). | Breaks every CalDAV client syncing those calendars; operator-only data surgery. |
| D. Accept | Run 0.206.0 and accept 0 events from the busiest calendar via MCP. | Feature loss. Not recommended. |

## 2. Pre-checks

0. **Target still upstream head + PR unchanged** (premises have no network verb):
   ```bash
   cd /Users/mu/code/cberg-home-nextgen || exit 1
   git fetch origin main renovate/ghcr.io-cbcoutinho-nextcloud-mcp-server-0.x
   gh pr view 258 --json state,mergeable,files --jq '.state, .mergeable, [.files[].path]'
   # expect: OPEN / MERGEABLE / ["kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml"]
   TOKEN=$(curl -s "https://ghcr.io/token?scope=repository:cbcoutinho/nextcloud-mcp-server:pull&service=ghcr.io" \
     | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
   for t in 0.206.0 latest 0.206.1 0.207.0; do
     printf '%-8s ' "$t"
     curl -sI -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.oci.image.index.v1+json" \
       "https://ghcr.io/v2/cbcoutinho/nextcloud-mcp-server/manifests/$t" \
       | tr -d '\r' | awk 'NR==1{printf "%s ",$2} tolower($1)=="docker-content-digest:"{print $2}'; echo
   done
   # measured 2026-11-08: 0.206.0 200 sha256:977768c9…55b1ba; latest 200 SAME; 0.206.1 404; 0.207.0 404.
   # A newer tag -> STOP: read its release body, run §2.7 B against it, refresh THIS file in place.
   ```
1. **Premises** (seven, fail-closed; run AFTER §2.0's fetch):
   ```bash
   python3 runbooks/plan-premises.py nextcloud-mcp-0.206.0 --require-premises
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
   wc -l < /tmp/ncmcp/tools.before                       # measured 2026-10-21, 2026-10-31 and 2026-11-02: 96
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
   **H) Our gate calls use only declared arguments (0.206.0 BREAKING: undeclared keys are refused).** Runs against the 0.184.5 schema just saved; the post-roll calls are re-checked in §4.15:
   ```bash
   python3 - <<'PYEOF'
   import json
   used = {"nc_calendar_list_events": {"calendar_name","start_date","end_date","limit"},
           "nc_webdav_list_directory": {"path"}, "nc_contacts_list_contacts": {"addressbook"},
           "nc_calendar_list_calendars": set(), "nc_contacts_list_addressbooks": set(), "talk_list_conversations": set()}
   tools = {t["name"]: set(t.get("inputSchema", {}).get("properties", {})) for t in json.load(open("/tmp/ncmcp/tools_list.before.json"))["result"]["tools"]}
   missing = [n for n in used if n not in tools]; assert not missing, f"gate tools absent on live server: {missing}"
   bad = {n: sorted(a - tools[n]) for n, a in used.items() if a - tools[n]}
   assert not bad, f"gate calls send undeclared arguments (0.206.0 would refuse them): {bad}"
   print("H PASS: every gate argument is declared on the live server")
   PYEOF
   # measured 2026-11-08 on 0.184.5: H PASS. CAN FAIL: adding "bogus" to the nc_webdav_list_directory set prints
   #   {'nc_webdav_list_directory': ['bogus']} and the assert fires (negative control run 2026-11-08).
   # NOTE: nc_contacts_list_contacts on 0.184.5 declares ONLY `addressbook` (§4.8 asserts it); `limit` is sent only after the roll.
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
   runbooks/update-marker.sh add nextcloud-mcp office 2 "0.184.5->0.206.0 image bump"
   ```
7. **HARD STOP GATE: the 0.195.5 calendar-addressing regression.** Proceed only if A or B passes:
   ```bash
   # A) data side: does any owned calendar still have a literal '%' in its URI?  (from §2.4 F)
   python3 -c 'import json; d=json.load(open("/tmp/ncmcp/events.before.json")); n=sum(v["pct_uri"] for v in d.values()); print("pct-URI calendars:", n); raise SystemExit(0 if n==0 else 1)' \
     && echo "7A PASS" || echo "7A FAIL"
   # B) code side: does the TARGET tag still unquote the name before encoding? FAIL CLOSED on fetch errors.
   REF=v0.206.0; F=/tmp/ncmcp/calendar.py.$REF; rm -f "$F"
   if ! gh api "repos/cbcoutinho/nextcloud-mcp-server/contents/nextcloud_mcp_server/client/calendar.py?ref=$REF" \
        -H 'Accept: application/vnd.github.raw' > "$F"; then echo "7B FAIL ($REF): fetch failed -- gate NOT evaluated"
   elif ! grep -q 'def _get_calendar_url' "$F"; then echo "7B FAIL ($REF): _get_calendar_url absent -- file moved/renamed, re-read by hand"
   elif [ "$(grep -c 'unquote(calendar_name)' "$F")" -eq 0 ]; then echo "7B PASS ($REF): unquote(calendar_name) count=0 -- re-read the new _get_calendar_url, then still run §4.6"
   else echo "7B FAIL ($REF): unquote(calendar_name) count=$(grep -c 'unquote(calendar_name)' "$F")"; fi
   # measured 2026-11-08: 7A FAIL (pct-URI calendars: 2); 7B FAIL (v0.206.0): count=1, calendar.py:586; same on master.
   #   History: PASS at v0.195.4 (count 0); FAIL at v0.198.0/.1/.3, v0.199.1, v0.200.5, v0.201.2, v0.202.1, v0.203.0, v0.204.0, v0.206.0, master.
   #   REF=main -> fetch fails (default branch is `master`) -> prints "fetch failed", never PASS.
   # BOTH FAIL -> STOP. Do not merge/commit. runbooks/update-marker.sh clear nextcloud-mcp, and return to the operator with §1.7.
   #   This is the EXPECTED outcome today.
   ```
   *The gate can fail AND pass:* 7A read 2 on live data 2026-10-21. 7B prints
   PASS at v0.195.4 (count 0), FAIL at v0.206.0/master (count 1), and fails
   closed on a non-existent ref. Read the printed `7A`/`7B` verdict lines.

8. **OpenClaw consumer path unchanged** (a pre-check, not a premise: the seven frontmatter premises do not cover OpenClaw, and `kubectl exec` with `;`/`&&` is awkward in the runner; OpenClaw moved to 2026.11.1 / node 24 on 2026-11-08):
   ```bash
   kubectl exec -n ai deploy/openclaw -c app -- sh -c 'ls /home/node/.openclaw/lib/node_modules/mcporter/dist/cli.js; node /home/node/.openclaw/lib/node_modules/mcporter/dist/cli.js --version; printenv NEXTCLOUD_MCP_URL'
   # expect the cli.js path, a mcporter version (0.17.0 on 2026-11-08), and exactly the in-cluster service endpoint nextcloud-mcp.office.svc.cluster.local:8000/mcp
   # Anything else -> §4.11's config template is wrong: STOP and re-point it, do not skip the consumer gate.
   ```

## 3. Steps

1. §2.0-2.7 green, i.e. §2.7 passed via A or B. Otherwise stop here.
2. Merge the Renovate PR (preferred path; the branch file is byte-identical to the BSD-sed edit below, `cmp` clean 2026-10-21):
   ```bash
   cd /Users/mu/code/cberg-home-nextgen || exit 1
   gh pr view 258 --json state,files --jq '.state, [.files[].path]'   # OPEN, ["kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml"]
   gh pr merge 258 --squash --delete-branch
   git fetch origin main && git merge --ff-only origin/main
   grep -n '^[[:space:]]*tag: ' kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml   # expect 34:              tag: 0.206.0
   git log -1 --format='%H %s' -- kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml | tee /tmp/ncmcp/bump.sha
   # expect subject: feat(container): update ghcr.io/cbcoutinho/nextcloud-mcp-server ( 0.184.5 → 0.206.0 ) (#258)
   ```
   **Fallback if #258 has been retargeted/closed** (do not merge a PR whose title no longer says 0.206.0): edit locally. Dry-tested 2026-11-08 on a scratch copy with macOS BSD sed: `34c34 <               tag: 0.184.5 / >               tag: 0.206.0`, one hunk; the result is byte-identical (`cmp`) to the PR #258 branch file (`git show origin/renovate/ghcr.io-cbcoutinho-nextcloud-mcp-server-0.x:…/helmrelease.yaml`).
   ```bash
   sed -i '' 's/^\([[:space:]]*tag: \)0\.184\.5$/\10.206.0/' kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml
   git diff --stat -- kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml    # expect 1 file, 1+/1-; 0 files = no-op: STOP
   printf '%s\n' 'feat(nextcloud-mcp): image 0.184.5 -> 0.206.0' '' \
     'Plan: runbooks/maintenance/plans/nextcloud-mcp-0.206.0.md (section 2.7 gate passed).' '' \
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
   # expect ONE pod, restarts=0, imageID ending sha256:977768c9107c1fee86905fc96f703646d32f9191b10ca9da0bdabf47e055b1ba
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
   # expect 1 right after start and STILL 1 after §4.4's sessions (app.py:1046 at v0.206.0, a %s-formatted logger.info; the 0.203.3 httpx2 swap shifted it 4 lines and edits only imports/except clauses). On 0.184.5 it climbs per
   #   session: 46 on the live pod 2026-10-21. A climbing count = old build. 0 = INFO hidden -> the two absence checks
   #   below have no positive control and §4.4's grep becomes the binding check.
   grep -ciE 'plugin sar: (not available, skipping|registering tools)' /tmp/ncmcp/log.now    # expect >=1 (positive control)
   grep -ciE 'plugin sar: registering tools' /tmp/ncmcp/log.now                              # expect 0; >=1 -> STOP, §5
   grep -ci 'BasicAuthMiddleware enabled' /tmp/ncmcp/log.now                                 # expect 0 (app.py:3390 at v0.206.0, INFO);
   #   >=1 means multi-user mode is live -> the 0.200.1 401 path guards every consumer request -> STOP, §5.
   ```
4. **CONTENTS ASSERTION (surface = baseline + the 25 names; SAR absent)**:
   ```bash
   cat > /tmp/ncmcp/tools.expected_new <<'EOF'
   nc_mail_save_draft
   nc_mail_view_attachment
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
   nc_webdav_edit_file
   nc_webdav_find_by_tag_name
   nc_webdav_get_file_tags
   nc_webdav_list_tags
   nc_webdav_list_trash
   nc_webdav_list_versions
   nc_webdav_restore_from_trash
   nc_webdav_restore_version
   nc_webdav_tag_file
   nc_webdav_untag_file
   nc_webdav_view_image
   EOF
   /tmp/ncmcp/call.sh tools/list '{}' > /tmp/ncmcp/tools_list.after.json
   python3 -c 'import json; d=json.load(open("/tmp/ncmcp/tools_list.after.json")); [print(t["name"]) for t in d["result"]["tools"]]' | sort > /tmp/ncmcp/tools.after
   comm -23 /tmp/ncmcp/tools.before /tmp/ncmcp/tools.after                                   # DISAPPEARED: expect EMPTY
   comm -13 /tmp/ncmcp/tools.before /tmp/ncmcp/tools.after | diff - /tmp/ncmcp/tools.expected_new && echo 'NEW TOOLS == EXPECTED'
   grep -ciE 'sar' /tmp/ncmcp/tools.after                                                   # expect 0
   grep -c '^nc_notes_' /tmp/ncmcp/tools.after                                              # expect 0: Notes app absent (§2.3) -> 0.202.0's
   #   nc_notes_list_notes is gated out by configure_app_tools. >=1 = Notes was installed since §2.3 -> re-read §1.2-§1.4, not a FAIL by itself.
   wc -l < /tmp/ncmcp/tools.after                                                            # expect 121
   kubectl port-forward -n office svc/nextcloud-mcp 18000:8000 >/dev/null 2>&1 & PF=$!; sleep 2
   curl -s -X POST http://localhost:18000/mcp -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
     -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"plan-probe","version":"0"}}}' \
     | python3 -c 'import sys,json
   raw=sys.stdin.read(); data=[l[5:].strip() for l in raw.splitlines() if l.startswith("data:")]
   r=json.loads(data[-1] if data else raw)["result"]; print(r["protocolVersion"], r["serverInfo"].get("version"))' | tee /tmp/ncmcp/protocol.after
   kill $PF 2>/dev/null
   # expect "2025-06-18 0.206.0" (0.201.1 errors.py: NextcloudMCPServer defaults version to the package version).
   #   "1.29.0" = old 0.184.5 build still serving; EMPTY = a 0.185..0.201.0 build (wrong image) -> do not pass.
   ```
   117 + the exact 21 names were measured live on 0.195.4 (2026-09-26). 0.195.5..0.202.1 add no tool that registers HERE: 0.202.0's `nc_notes_list_notes` is app-gated (Notes absent). 0.203.0 adds exactly four that DO register here (§1.3): `nc_mail_save_draft` + `nc_mail_view_attachment` (Mail app installed; `configure_app_tools(mcp, "mail")`), `nc_webdav_edit_file` + `nc_webdav_view_image` (`configure_webdav_tools`, always registered) -> 121. 0.203.1..0.206.0 add and remove NO tool (no `@mcp.tool` / `async def nc_` line in the `compare v0.203.0...v0.206.0` patches, checked 2026-11-02) -> still 121. Derived from source at v0.206.0, not observed live (§7); a mismatch here is a re-read, and a MISSING name from the carried 21 is a FAIL. Note: the `@mcp.tool` grep count (124 at v0.200.5, v0.201.2 and v0.202.1) is a weak proxy — the notes tool landed without moving it, because app tools register via `configure_app_tools`; the binding check is this gate's `comm`/`wc` against the live list. 0.201.0 adds only optional `startdate`/`color` params to Deck card tools (Deck app not installed here).
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
    - **Claude Desktop (attended).** Entry `nextcloud` runs `uvx mcp-proxy --transport streamablehttp https://nextcloud-mcp.<DOMAIN>/mcp` (HTTPRoute `nextcloud-mcp` on `envoy-internal/https` -> svc :8000). Fully quit and relaunch Desktop after the roll (the proxy holds a session to the old pod), list the root folder, **ask for this week's events from the busiest calendar** (the human form of §4.6), and confirm the tool count grew by 25. **Idle re-check (0.202.1, mcp 2.3 30-min session idle timeout):** leave Desktop idle >= 35 min, then list the root folder again. PASS = it answers (mcp-proxy re-initialized after the reap). FAIL prints a session-not-found / 404 error in Desktop until relaunch: record it on F-9af9baf7 as a client issue (mcp-proxy does not re-init) — it is the documented upstream behaviour, not a rollback trigger. A Desktop-only failure with §4.4/§4.11 green is a client-pin issue, not a rollback trigger.
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
14. **CONTENTS ASSERTION (0.205.0 calendar list_events: `truncated` + limit-after-filters)**. Uses a non-`%` calendar so it can be evaluated even while §1.1 stands; it needs a calendar with >= 2 events in range (baseline 2026-11-02: `personal` has 3; re-read `events.before.json`).
    ```bash
    python3 - <<'PYEOF'
    import json, subprocess
    from urllib.parse import unquote
    ev = json.load(open("/tmp/ncmcp/events.before.json"))
    cal = json.load(open("/tmp/ncmcp/calendars.after"))["result"]
    sc = cal.get("structuredContent") or json.loads(" ".join(c.get("text", "") for c in cal["content"]))
    def fu(s):
        for _ in range(8):
            n = unquote(s)
            if n == s: return s
            s = n
        return s
    cands = [(c["name"], ev[fu(c["href"])]["total_found"]) for c in sc["calendars"]
             if "%" not in unquote(c["href"].rstrip("/").split("/")[-1]) and ev[fu(c["href"])]["total_found"] >= 2]
    assert cands, "no non-% calendar with >=2 events: gate cannot see truncation -- pick another or record why"
    name, n = cands[0]
    def call(limit):
        a = json.dumps({"name": "nc_calendar_list_events", "arguments": {"calendar_name": name, "start_date": "2015-01-01", "end_date": "2030-12-31", "limit": limit}})
        r = json.loads(subprocess.run(["/tmp/ncmcp/call.sh", "tools/call", a], capture_output=True, text=True, check=True).stdout)["result"]
        assert not r.get("isError"), r
        return r.get("structuredContent") or json.loads(" ".join(c.get("text", "") for c in r["content"]))
    cut, full = call(1), call(n + 50)
    assert cut["total_found"] == 1 and cut.get("truncated") is True, f"limit=1 on a {n}-event calendar must be truncated: {cut.get('total_found')} {cut.get('truncated')!r}"
    assert full["total_found"] == n and full.get("truncated") is False, f"limit>count must NOT be truncated: {full.get('total_found')} {full.get('truncated')!r}"
    print(f"4.14 PASS: {name}: limit=1 -> 1 event truncated=True; limit={n+50} -> {n} events truncated=False")
    PYEOF
    # CAN FAIL: a build that predates 0.205.0 has no `truncated` key -> `None is True` fails the first assert (old image still serving).
    #   Do NOT use the busiest (200-event) calendar here: it is a %-URI calendar and reads 0 under §1.1.
    ```
15. **CONTENTS ASSERTION (0.206.0 BREAKING: unknown arguments refused, schemas strict, every gate call declared)**:
    ```bash
    python3 - <<'PYEOF'
    import json, subprocess
    td = json.load(open("/tmp/ncmcp/tools_list.after.json"))["result"]["tools"]
    lax = [t["name"] for t in td if t.get("inputSchema", {}).get("additionalProperties") is not False]
    assert td and not lax, f"{len(lax)} of {len(td)} tools do not advertise additionalProperties:false (old build?): {lax[:5]}"
    props = {t["name"]: set(t.get("inputSchema", {}).get("properties", {})) for t in td}
    used = {"nc_calendar_list_events": {"calendar_name","start_date","end_date","limit"}, "nc_webdav_list_directory": {"path"},
            "nc_contacts_list_contacts": {"addressbook","include_photos","limit","offset"}}
    bad = {n: sorted(a - props[n]) for n, a in used.items() if a - props[n]}
    assert not bad, f"gate calls use arguments the NEW schema does not declare: {bad}"
    def call(args):
        p = json.dumps({"name": "nc_webdav_list_directory", "arguments": args})
        return json.loads(subprocess.run(["/tmp/ncmcp/call.sh", "tools/call", p], capture_output=True, text=True, check=True).stdout)
    r = call({"path": "", "plan_probe_unknown_arg": 1})
    res = r.get("result", {}); txt = " ".join(c.get("text", "") for c in res.get("content", [])) + json.dumps(r.get("error", ""))
    assert (res.get("isError") or "error" in r) and "unknown argument" in txt.lower() and "plan_probe_unknown_arg" in txt, f"undeclared argument NOT refused: {json.dumps(r)[:300]}"
    assert not call({"path": ""})["result"].get("isError"), "declared call must still succeed"
    print(f"4.15 PASS: {len(td)} strict schemas; unknown arg refused; declared call ok")
    PYEOF
    # CAN FAIL: on 0.205.x or earlier the probe call SUCCEEDS (extra key ignored) and the schemas lack additionalProperties -> first assert fires.
    #   The probe is a READ (list root) with a junk key; the refusal happens before any Nextcloud request.
    ```
    **Human gate:** if §4.15 is the only red item, the roll itself is healthy and the failure is consumer-side — go to §4.11 and read the consumers' actual call (Claude Desktop transcript / OpenClaw agent session) before choosing between rollback (§5) and leaving it (the error text names the valid arguments, so an LLM client self-corrects).
16. **Close out**: `runbooks/update-marker.sh clear nextcloud-mcp`. Set this plan `executed` (0.204.0 and 0.203.0 must already read `superseded`). F-9af9baf7/F-80459b23 are script-owned and should close on the next sweep — verify, don't assume.

## 5. Rollback

Stateless (premises: no volumes, no DB keys), so rollback is an inverse image-tag edit — NOT `git revert`, which refuses (rc=128) in this shared worktree whenever another session has staged anything. Dry-tested 2026-11-08 on a scratch copy (macOS BSD sed): forward sed gives `34c34 <               tag: 0.184.5 / >               tag: 0.206.0`, `cmp`-identical to the PR #258 branch file; inverse sed then restores the original byte-identical (`cmp` clean). The inverse sed matches `0\.206\.0$` — the superseded plans' inverse seds (`0\.204\.0$`, `0\.203\.0$`, …) match tags never deployed and would be silent no-ops; do not copy them.

```bash
cd /Users/mu/code/cberg-home-nextgen || exit 1
git fetch origin main && git merge --ff-only origin/main
sed -i '' 's/^\([[:space:]]*tag: \)0\.206\.0$/\10.184.5/' kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml
git diff --stat -- kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml    # expect 1 file 1+/1-; 0 files = no-op: STOP
printf '%s\n' 'revert(nextcloud-mcp): image 0.206.0 -> 0.184.5' '' \
  'Rollback per runbooks/maintenance/plans/nextcloud-mcp-0.206.0.md section 5' \
  '(stateless bridge, image tag only). Reverts the commit recorded in /tmp/ncmcp/bump.sha.' > /tmp/ncmcp/msg-revert.txt
git commit --only kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml -F /tmp/ncmcp/msg-revert.txt
git show --stat HEAD && git log -1 --format=%s    # ONE file; subject = revert(nextcloud-mcp): image 0.206.0 -> 0.184.5
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
- **Nextcloud server work** (`redis-fleet-8.10.3` sun 11-29 restarts nextcloud + nextcloud-redis; `bitnamilegacy-exit-nextcloud-db` if revived; any future Nextcloud chart/server plan — none is open on 2026-11-08; `nextcloud-9.4.1`/`nextcloud-whiteboard-2.1.2` name no plan file and are NOT listed; `nextcloud-9.4.0` exists but is `superseded`): every §4 contents gate is a live call into that server, so never share a slot. A Nextcloud server minor/major move fails premise `nextcloud-server-is-35` closed or invalidates the §2.4 baselines: re-take them after it.
- **Prometheus**: §2.5/§4.9/§4.10 read it. No kube-prometheus-stack plan is open on 2026-11-08 (grep of every non-terminal plan's `component:`); a future one must list this plan and vice versa.
- **Gateway / API-server work** (NEW vs 0.204.0): `envoy-gateway-1.10.0` (draft) rolls the envoy-internal data plane that Claude Desktop uses to reach this service; `etcd-timeouts-5000-500` (blocked) restarts etcd on all control-plane nodes. Neither shares a slot with this plan (`conflicts_with`), so a §4.11 Desktop failure is always attributable to this roll.
- **OpenClaw** (`openclaw-2026.11.1`, status `executed` 2026-11-08 00:36Z): rolled to node 24 / mcporter 0.17.0 the same day. Not listed in `conflicts_with` (terminal), but the §4.11 consumer gate is written against the post-roll pod; if OpenClaw is rolled again the two premises `openclaw-mcporter-cli-present` / `openclaw-points-at-the-streamable-http-endpoint` fail closed rather than letting the gate run against a moved CLI.
- **Node rolls** (`talos-linux-1.14.4` vetted, `talos-linux-1.14.5` draft, `talos-power-tuning-ab` vetted — all `exclusive: true`) restart this pod and Nextcloud; exclusivity keeps them out of this slot. If adjacent, take §2.4 baselines AFTER the roll.
- **app-template**: HR on 5.3.0; no open app-template plan touches this file. A later app-template bump on this HR must list this plan.
- **Attended only.** Deny rule + `capability_change: true`. Never `nightly`. Nothing here touches Longhorn, cert-manager, cilium, coredns or the Gateways.
- **Supersession** (§1.5): this plan supersedes `nextcloud-mcp-0.204.0` and `-0.203.0` (both still `blocked` on disk until the coordinator flips them — listed in `conflicts_with` so they can never share a slot). 0.202.1/0.201.2/0.200.2/0.199.1/0.198.0/0.187.1 are already `superseded`. Once they are flipped, only this file owns F-9af9baf7/F-80459b23 as a live plan.
- **helm-drift-detection** (vetted sat-attended:2026-11-28) adds a spec field to every HelmRelease, including `helmrelease/nextcloud-mcp`; listed in `conflicts_with`. **flux-oci-chart-sources** (vetted sun-attended:2026-12-13) re-points bjw-s app-template HelmReleases from the HTTP `HelmRepository` to an `OCIRepository` — `helmrelease/nextcloud-mcp` uses `sourceRef: HelmRepository bjw-s` (helmrelease.yaml:13-16), so that plan re-renders this HR; listed in `conflicts_with` (new vs the 0.203.0 draft). **python-fleet-3.15.2** and **vaultwarden-1.37.4** share namespace `office` but touch disjoint resources (mcpo/openclaw-probe/mealie-shopping-sync; vaultwarden) — no conflict, adjacency fine.
- **New WRITE tools (0.203.0, carried into 0.206.0)**: once running, consumers can save Mail drafts and edit plain-text files in the service account's Nextcloud. Not a shared-infra perturbation, but it is why `capability_change: true` and why the operator GO must name it.
- **Session idle timeout (0.202.1)**: any MCP client holding a session idle > 30 min is reaped after the bump. OpenClaw opens per-call sessions (unaffected); Claude Desktop is checked in §4.11.

## 7. What I could not verify (2026-11-08)

- **Whether 0.206.0 (or 0.195.4) remediates F-80459b23.** Per-tag scan question; result goes on the record, not here.
- **That the image reports `serverInfo.version == "0.206.0"`.** Derived from source (`errors.py:229` at v0.206.0, stdlib `importlib.metadata`), not observed on a running pod. If it reads a different non-empty string, confirm the imageID digest (§4.2) and treat that as the binding check.
- **Starlette 1.x (0.204.2) and httpx -> httpx2 (0.203.3) on our transport path.** Source/changelog evidence only; not run. §4.2, §4.4, §4.5, §4.6, §4.8, §4.11, §4.13 are the gates.
- **Which tool/argument shapes the LLM consumers actually send.** No repo file pins them (OpenClaw's scripted skills bypass the MCP server); the OpenClaw session history was not mined. §2.4 H proves OUR gate calls are clean; §4.15 proves the new refusal fires; neither proves an agent's ad-hoc call is clean.
- **Upstream fix timeline.** No upstream issue exists for the literal-`%` calendar-URI case (searched 2026-11-02; the code at v0.206.0 is unchanged, §1.1).
- **caldav / icalendar-searcher relock behaviour on our data** (0.202.1 and the 0.204.1 `lock file maintenance`): lockfile-only evidence. §4.5-§4.7 are the gates.
- **mcp-proxy (Claude Desktop) behaviour after a 30-min session reap.** Not tested; §4.11 idle re-check observes it.
- **Write paths** — the 0.203.1 VTODO merge fix, the 0.204.0 contacts vCard N writes, the 0.205.2 `apply_edits` CRLF fix, the 0.203.0 Mail-draft/WebDAV-edit tools, bulk-ops with the raised cap, writes on the `%`-URI calendars, the 0.199.1 fixed-offset -> UTC change, Talk thread writes and Deck card fields: not exercised (writes against household data; Deck absent).
- **The second `%`-URI calendar** has 0 events in range; §4.6 cannot see a regression on it (§2.7 A covers it structurally).
- **Talk baseline** (2 conversations) is carried from 2026-10-21, not re-measured; §2.4 G re-takes it on the day.
- **Fresh 2026-11-08 measurements** (not carried): live image/digest, 96 tools, 4 calendars / 2 `%`-URI, chart 5.3.0, container `main` limit 1Gi, no volumes path (premise), PR #258 branch-head subject, GHCR tags + digests (0.204.0/0.205.0/0.206.0/latest; 0.206.1 and 0.207.0 404), calendar.py `unquote(calendar_name)` at v0.206.0 and master (line 586), `app.py:1046`/`:3390` log sites, `errors.py:229`, OpenClaw mcporter 0.17.0 + `NEXTCLOUD_MCP_URL`, node v24.22.2.

## Repo corrections noted by this planner

- `docs/sops/ai-integration.md` / `mcporter-config.yaml` describe the `nextcloud` MCP entry as "read-only … (read-oriented)". After this roll the same server exposes 6 WRITE tools plus Mail-draft and file-edit; the description is no longer true and nothing in the mcporter registration restricts it. Decision for the operator, not a window action.
