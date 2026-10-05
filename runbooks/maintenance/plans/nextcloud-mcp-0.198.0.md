---
plan_id: nextcloud-mcp-0.198.0
component: nextcloud-mcp
pr: null                              # no Renovate PR; held by the `*nextcloud-mcp*` `max: patch` deny rule
                                      # (runbooks/auto-update-policy.yaml) via coverage.py's PLAN lane
kind: image
current: "0.184.5"
target: "0.198.3"                     # RETARGETED in place 2026-10-05 (2nd refresh; plan_id/filename kept as
                                      # 0.198.0). Verified 2026-10-05: GHCR 0.198.3 index digest sha256:b7faa131…
                                      # is IDENTICAL to `latest`; 0.198.4 and 0.199.0 404; GitHub v0.198.3 is
                                      # Latest, not a pre-release (published 2026-10-01T13:47Z). v0.198.1...v0.198.3
                                      # (8 commits) touches only vector-sync discovery, the Postgres token-storage
                                      # engine and the WebDAV SEARCH paging offset -- all inert here (§1.2);
                                      # client/calendar.py is byte-identical (sha256 f17ebf59…), so the 0.195.5
                                      # regression is STILL present. Prior target 0.198.1 (2026-10-01).
update_type: minor                    # semver label only -- at major 0 the MINOR digit is the breaking axis; this
                                      # hop crosses FOURTEEN minor lines (0.185 .. 0.198). 0.185..0.195.4 were read
                                      # tag-by-tag in nextcloud-mcp-0.187.1 (carried in §1.3); 0.195.5..0.198.3 are
                                      # read here (§1.2).
risk: medium                          # stateless bridge, cheap git-revert -- BUT §1.2's regression means the
                                      # EXPECTED outcome today is a STOP at §2.7 (see Summary). Not raised to high:
                                      # nothing here is forward-only and the failure is caught before the commit.
est_duration_min: 40                  # 35 (predecessor) + the per-calendar event-read gate (§2.4 F / §4.6)
needs_reboot: false
touches:
  namespaces: [office]
  resources:
    - helmrelease/nextcloud-mcp
    - deployment/nextcloud-mcp
                                      # httproute/nextcloud-mcp re-renders from the same HR but its spec does not
                                      # change (image tag is the whole diff) -- not perturbed.
  shared: [monitoring]                # READ-only: §2.5/§4.9/§4.10 read Prometheus (the window's instrument). No
                                      # gateway, CNI, DNS, storage or shared DB is perturbed. Cross-namespace
                                      # CONSUMERS (ai/openclaw, Claude Desktop) are blast radius, not shared infra (§6).
depends_on: []                        # Flux `dependsOn: nextcloud` is ordering-only; no release note in range states
                                      # a minimum Nextcloud server version.
conflicts_with:
  # - nextcloud-mcp-0.187.1 (DROPPED 2026-10-05: `superseded` = terminal, so the entry binds nothing. If
  #   option B (§1.6) revives it, re-add it here AND reciprocally there -- the two must never share a slot.)
  - app-template-5.2.1                # nightly:2026-10-02 -- its Batch A sed edits THIS helmrelease.yaml (chart
                                      # 5.1.0 -> 5.2.1, line 12) and re-renders this Deployment; a same-night run
                                      # makes §4.2's roll unattributable. Reciprocal entry re-pointed 2026-10-01.
  # - nextcloud-redis-hardening (RESOLVED 2026-10-04: executed + retired 418faa1e (now:2026-10-03); dead ref removed per the dead-ref convention)
    # nightly:2026-10-01 -- quiesces the Nextcloud server + restarts its Redis;
                                      # every §4 contents gate is a live call into that server. Reciprocal re-pointed.
  - nextcloud-fleet-35.0.1            # sun-attended:2026-10-18 -- Nextcloud 34 -> 35 MAJOR; §4.5/§4.6 read CalDAV
                                      # from that server. After it runs, premise 2 fails closed -> re-vet here.
  - bitnamilegacy-exit-nextcloud-db   # blocked/unwindowed; restarts deployment/nextcloud if revived -- same reason.
  - kube-prometheus-stack-91.9.0      # draft 2026-10-05 -- restarts Prometheus, the instrument §2.5/§4.9/§4.10 read
                                      # (rule 4: a same-night kps bump vs a Prometheus-reading verification).
                                      # Reciprocal already present in that plan's conflicts_with.
exclusive: false
security_ref: F-80459b23              # re-read 2026-09-29: the record is about the 0.184.5 image and names a newer
                                      # upstream tag as the remedy -- it genuinely applies. Detail stays on the record.
capability_change: true               # 21 new tools (4 of them WRITE), behaviour changes on live tools (0.192.0
                                      # bulk-ops series default, 0.188.1 contacts photo opt-in, 0.187.0 real
                                      # find_availability), and the 0.195.5 calendar-addressing change (§1.2).
                                      # RE-CHECKED 2026-10-05 for 0.198.3: still true -- the whole 0.184.5 hop is
                                      # what ships; 0.198.2/0.198.3 add nothing (no tool, route or config key).
rollback_class: git-revert            # no PVC, no volumes, no DATABASE_URL/TOKEN_STORAGE_DB: alembic runs against an
                                      # ephemeral /tmp SQLite recreated each start (premises 4+5).
finding_refs: [F-9af9baf7, F-80459b23] # F-9af9baf7 = the version finding (title names 0.198.3, re-read 2026-10-05);
                                      # F-80459b23 = the security finding. nextcloud-mcp-0.187.1 also lists
                                      # both but is `superseded` (terminal) since 2026-10-01.
review: null
status: draft
window: null
premises:
  - id: image-is-still-0.184.5
    why: >-
      `current:` and the rollback target are 0.184.5. If the cluster moved, the
      diff, the baselines and the rollback digest are wrong.
    run: kubectl get deploy -n office nextcloud-mcp -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: ghcr.io/cbcoutinho/nextcloud-mcp-server:0.184.5
  - id: nextcloud-server-still-34
    why: >-
      §4.5/§4.6 read CalDAV from this server and the §1.2 regression analysis was
      measured against 34.0.4. Patch drift is tolerated; nextcloud-fleet-35.0.1
      (a MAJOR) moving first fails this closed and forces a re-vet.
    run: kubectl get deploy -n office nextcloud -o jsonpath='{.spec.template.spec.containers[?(@.name=="nextcloud")].image}'
    expect_matches: 'docker\.io/nextcloud:34\.0\.[0-9]+$'
  - id: deployment-mode-still-single-user-basic
    why: >-
      0.185.0's elicitation break, 0.190.0's and 0.198.1's CIMD/OAuth changes and
      0.197.0's sar.read/sar.write scopes all fire only on the OAuth / multi-user path.
      single_user_basic makes them inert; any other mode voids §1.2/§1.3.
    run: kubectl get secret -n office nextcloud-mcp-config -o json | jq -r '.data.MCP_DEPLOYMENT_MODE' | jq -Rr '@base64d'
    expect_exact: single_user_basic
  - id: exactly-four-config-keys
    why: >-
      Proves (a) no DATABASE_URL/TOKEN_STORAGE_DB, so rollback is free; (b) no
      VECTOR_SYNC_ENABLED/ENABLE_SEMANTIC_SEARCH, EMBEDDING_GATEWAY_URL or
      SAR_ENABLED, so the 0.196.0 indexing BREAKING and the 0.197.0/0.198.0 SAR
      tools, routes and scopes stay off (SAR registers only inside the
      vector-sync branch, app.py:1880-1888 at v0.198.0/v0.198.1 -- app.py is
      untouched by that patch and by 0.198.2/0.198.3); (c) no CIMD_ALLOWED_HOSTS, so the 0.198.1
      CIMD fix is unreachable; (d) no COLLABORA_URL /
      DOCLING_API_URL, so optional processors stay off; (e) no vector sync and
      no DATABASE_URL, so the 0.198.2 discovery fix and the 0.198.3
      Postgres-engine fix are unreachable.
    run: kubectl get secret -n office nextcloud-mcp-config -o go-template='{{range $k,$v := .data}}{{$k}},{{end}}'
    expect_exact: MCP_DEPLOYMENT_MODE,NEXTCLOUD_HOST,NEXTCLOUD_PASSWORD,NEXTCLOUD_USERNAME,
  - id: no-volumes-on-the-pod
    why: >-
      Second half of the stateless claim: nothing to snapshot, no RWO
      multi-attach guard needed.
    run: kubectl get deploy -n office nextcloud-mcp -o json | jq -r '.spec.template.spec.volumes'
    expect_exact: "null"
  - id: helmrelease-chart-5.1-or-5.2.1
    why: >-
      Verification assumes the app-template render (tcp probes, container name
      `main`). app-template-5.2.1 (nightly:2026-10-02) bumps this HR's chart
      label-only; both are accepted. Any other chart version means an
      unreviewed render change.
    run: kubectl get helmrelease -n office nextcloud-mcp -o jsonpath='{.status.history[0].chartVersion}'
    expect_matches: '^5\.(1\.0|2\.1)$'
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/auto-update.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-09-29"
---

## 1. Summary & why held

`kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml:34` pins
`ghcr.io/cbcoutinho/nextcloud-mcp-server` at `0.184.5`; upstream head is
`0.198.3` (`F-9af9baf7`). **Retargeted in place** 2026-10-01 from 0.198.0 to
0.198.1, and **again 2026-10-05 to 0.198.3** (plan_id and filename keep
`0.198.0`): 0.198.1 touches only `auth/cimd.py` + packaging; 0.198.2/0.198.3
touch only vector-sync discovery, the Postgres token-storage engine and the
WebDAV SEARCH offset (§1.2), so every 0.198.0 conclusion below carries.
coverage.py: *"0.x release-line move (0.184 -> 0.198)
-- at major 0 the minor IS the breaking axis"*; the `*nextcloud-mcp*` deny rule
(`max: patch`) requires a human read of every minor hop. Security driver:
`F-80459b23` (§1.4).

**Verdict: DO NOT RUN THIS HOP AS-IS. 0.195.5 (inside this range) introduced a
calendar-addressing change that silently empties reads of this household's
largest calendar.** Measured, not inferred (§1.2 row 0.195.5): two of the four
calendars the MCP user owns have a Nextcloud calendar URI that contains a
literal `%28`/`%29` (read from `occ dav:list-calendars` AND from the href the
server returns). From 0.195.5 on, `_get_calendar_url()` runs `unquote()` on the
calendar name before encoding it once (`client/calendar.py:561-568` at
v0.198.0, byte-identical at v0.198.1, v0.198.3 and `master`). Upstream's own justification in the code and commit `855c0f8b`:
*"Nextcloud calendar URIs never contain a literal `%`, so the unquote is
lossless in practice"* -- false for our data. The request goes to a
non-existent URI, and Nextcloud answers with an empty calendar, not an error.
Emulated live on 0.184.5 on 2026-09-29, by passing the doubly-decoded name that
0.198.0 (and so 0.198.1/0.198.3) will build: `nc_calendar_list_events` returned `isError=false,
total_found=0` for a calendar that returns **200 (limit-capped)** events with
its real name. The new `errors: [...]` field (0.195.5) does NOT catch it,
because nothing raised. Consumers would get "no events" / "you are free"
answers that are confidently wrong. The carried-over calendar-LIST gate (§4.5)
would PASS, because listing is unaffected. Only the per-calendar event-read
gate (§4.6, new) catches it.

So §2.7 is a hard STOP gate. It passes only if (a) no owned calendar URI holds
a literal `%` any more, or (b) the target tag no longer has
`unquote(calendar_name)` in `_get_calendar_url`. Neither holds today:
v0.198.3 and upstream's default branch `master` still have it (checked
2026-10-05; `calendar.py` sha256 `f17ebf59…` identical across v0.198.1, v0.198.3, master;
v0.198.0 identical per the 2026-10-01 read). **The operator has to choose
the way forward (§1.6). The window agent cannot pick it.** Everything else in
the hop was read and is inert or additive for this deployment (§1.2, §1.3).

### 1.1 Registry verification (2026-10-05; re-run at §2.0)

| tag | GHCR (anonymous token, OCI index) |
|---|---|
| `0.184.5` (live) | 200 -- running pod `imageID` `sha256:f6d8839722587f2cd37ec5218a18479f9e313be9904ad4f6bbb36f98bc827065` |
| `0.195.4` (predecessor's target, last tag WITHOUT the §1.2 regression) | 200, `sha256:24417dcb804fc65bcb8712226bf70be71018aefd2ec7b27e9392a4d4e1ed707c` |
| `0.195.5` (regression enters) | 200, `sha256:079f02fb6b4bea5612b5aa4d90423d7df3ceca1dff473a9309e596bee6b2aba4` |
| `0.198.0` (original target) | 200, `sha256:dbfeb3eb78c6fc75c155407f64d7f86eeea3d4a4aa544ae7ec785da121394143` |
| `0.198.1` (previous target) | 200, `sha256:427e08268bdbbbc0b7f6fea5c2e6cd906a5e72caeeff027e55b208ca08e72af7` |
| `0.198.2` | 200, `sha256:116d9d238f1dce8ed9a57426089c645f84940fb9c3b09d547b33e70c4c90d3db` |
| **`0.198.3` (target)** | **200, `sha256:b7faa131d1c4c4dbb1da7c24ccd96d35dcb41ad6f0ac6bcd5abd69282b8cd4b8`** |
| `latest` | 200, identical to 0.198.3 |
| `0.198.4`, `0.199.0` | 404 |

GitHub releases: v0.195.5 (2026-09-27T09:50Z), v0.196.0 (2026-09-27T21:09Z),
v0.197.0 (21:13Z), v0.197.1 (22:37Z), v0.198.0 (2026-09-28T10:53Z),
v0.198.1 (2026-09-30T12:13Z), v0.198.2 (2026-10-01T13:44Z), v0.198.3
(2026-10-01T13:47Z, Latest). None is a pre-release. v0.196.1/v0.197.2
do not exist. 0.198.3 cleared the 48 h `minimum_release_age_hours` gate at
2026-10-03T13:47Z; four days without a newer tag as of 2026-10-05. Six releases in four days, so the line is moving fast. Re-run
§2.0 on the day.

### 1.2 What changed 0.195.4 -> 0.198.3, read per tag + source diff

Release bodies (`gh release view vX -R cbcoutinho/nextcloud-mcp-server`) and
`git diff v0.195.4 v0.198.0` (36 non-test files). Under `server/`, only
`calendar.py` (no tool added, renamed or removed) and the new `sar.py` changed.
`uv.lock` changes only the project version and the `ty` dev dependency, so
**`mcp` stays 2.1.1**. The Dockerfile moves only the `python:3.14-slim-trixie`
base digest and `uv` 0.12.18 -> 0.12.19. The entrypoint is unchanged.
`v0.198.0...v0.198.1` (GitHub compare, read 2026-10-01) touches only
`nextcloud_mcp_server/auth/cimd.py` (+54/-2), its unit test, `CHANGELOG.md`,
`pyproject.toml`/`uv.lock` (version line), and two CI workflow pins. No
Dockerfile, `app.py`, `server/` or `client/` change; `client/calendar.py` is
byte-identical, so the 0.195.5 regression is still present.
`v0.198.1...v0.198.3` (GitHub compare, read 2026-10-05: `ahead`, 8 commits incl.
2 merges/2 version bumps, 14 files) touches `client/__init__.py`
(`find_files_by_tag`), `client/webdav.py` (SEARCH paging), `vector/scanner.py`,
`auth/storage.py` (Postgres engine), `docs/configuration.md`, tests, CHANGELOG
and version lines. No Dockerfile, `app.py`, `server/`, `client/calendar.py` or
`client/contacts.py` change, and no dependency change (`uv.lock` is the version
line only).

| tag | class | what it says | applies to us? |
|---|---|---|---|
| **0.195.5** | fix (calendar) | *"accept percent-encoded calendar names, report skipped calendars"*: `_get_calendar_url` now `unquote()`s the name before encoding once. Cross-calendar reads return an additive `errors: [{calendar_name, error}]`. `get_upcoming_events` drops its serial loop for `search_events_across_calendars`. | **APPLIES: REGRESSION ON OUR DATA** (see Summary). 2 of 4 owned calendars have a literal `%` in the URI. For both, every per-calendar operation (`_get_calendar` is used by list/get/create/update/delete event, todos, bulk ops, availability; `client/calendar.py:572,808,850,867,1046,…`) addresses a non-existent collection. Reads come back EMPTY WITHOUT an error (measured); writes would fail or land nowhere. The `errors` field and the `ListEventsResponse`/`UpcomingEventsResponse`/`ListTodosResponse` output-schema growth are additive. |
| **0.196.0** | **BREAKING** | *"with VECTOR_SYNC_INDEXABLE_MIME_TYPES unset, tagged .msg, .txt, .md and .csv files are now indexed …"*. Plus `TextProcessor` registers at import, and *"reading a text file stays raw"*. | **Inert**: vector sync is off (premise 4). `TextProcessor` registers unconditionally (`document_processors/__init__.py`), but `is_parseable_document()` now returns False for `text/*` (`utils/document_parser.py:46-49`), so `nc_webdav_read_file` on text keeps returning the raw file, the same as 0.195.4. |
| **0.197.0** | **BREAKING** | `/api/v1/status` reports `sar_available`; SAR tools/routes need `sar.read`/`sar.write` scopes; NER client API change; SAR case/export/redaction feature (ADR-040). | **Inert**: SAR tools register only inside `if settings.vector_sync_enabled:` and `sar_available()` (app.py:1880-1888). Routes are behind the same check. Scopes are advertised only via DCR (OAuth mode). Nothing is registered in single_user_basic with 4 config keys. |
| 0.197.1 | fix (redaction) | NER windowing / job-title redaction fixes | Inert (SAR off). |
| **0.198.0** | **BREAKING** | *"SAR cases and redacted export are no longer served implicitly when vector sync and EMBEDDING_GATEWAY_URL are configured. Set SAR_ENABLED=true to keep them."* | **Inert**: we never had SAR (no vector sync). `sar_available()` now also requires `sar_enabled` (default False), and a startup `ValueError` fires only if SAR_ENABLED is set without its prerequisites. That key is absent here (premise 4). |
| 0.198.1 | fix (auth) | *"accept any port on portless loopback CIMD redirect URIs"* (upstream PR #1578) | **Inert in single_user_basic**: `validate_cimd_client` is reached only from `auth/oauth_routes.py` (the OAuth authorize route), and CIMD is disabled when `cimd_allowed_hosts` is empty (`config.py:86-87`, default `""`; no such key here, premise 4). |
| 0.198.2 | fix (vector-sync) | *"page SEARCH correctly and never delete on partial discovery"* (PR #1579): `find_files_by_tag` now RAISES when a tagged folder's walk fails instead of returning a partial list; the scanner treats a < 50 % discovery as implausible; `WEBDAV_SEARCH_PAGE_SIZE` 500 -> 1000; the SEARCH offset moves from `<d:firstresult>` to the searchdav namespace `<sd:firstresult>`. | **Inert**: `find_files_by_tag`, `search_files_all` and the scanner are reached only from `vector/scanner.py` (vector sync off, premise 4). The one live tool on `search_files` (`server/webdav.py:1078`) passes `limit` only, never `offset`, so its request XML gains only an unused `xmlns:sd` declaration. |
| 0.198.3 | fix (storage) | *"disable psycopg auto-prepare on the Postgres engine"* (PR #1580): `connect_args={"prepare_threshold": None}` in `_build_postgres_engine`. | **Inert**: that engine is built only for a `postgresql` `DATABASE_URL`; we have none (premise 4) and run the ephemeral `/tmp` SQLite. |

**Tool surface is unchanged versus 0.195.4.** The only `@mcp.tool` additions
in range are in `server/sar.py` (7 tools), which are not registered here.
0.195.4's surface was **measured live at 117** during the 2026-09-26 attempt 2
(the predecessor's gate 4.4 PASSED: 96 + the exact 21 names). So §4.4 expects
117, i.e. the same 21 new names over today's 96.

### 1.3 0.184.5 -> 0.195.4, carried from `nextcloud-mcp-0.187.1` (read tag-by-tag there, §1.2/§1.2a/§1.6)

Condensed. The full evidence is in that file:

- **0.185.0 BREAKING** (mcp SDK >=2.1, elicitation -> message_only). Inert in single_user_basic. The server moves SDK major 1.29.0 -> 2.1.1 and base python 3.12 -> 3.14. Lifespan runs once per container start, not once per session (§4.3).
- **0.192.0 BREAKING** (`nc_calendar_bulk_operations` leaves recurring series alone unless `apply_to_series=true`). This is live surface with a safer default and one added parameter (§4.7).
- **0.194.0 BREAKING** (parsing_metadata key rename). Inert (captioning off).
- **0.185.5** (CalDAV URL encoding, one rule): the list `name` becomes the once-decoded href segment. On 0.195.4 our two `%` calendars still addressed correctly (verified with a case-insensitive compare: `quote(name)` == href). 0.195.5 is what breaks it (§1.2).
- **0.188.1** contacts: photo opt-in + paging (§4.8). **0.188.0/0.189.0**: 9 `nc_webdav_*` tag/trash/version tools (4 WRITE, backed by core apps). **0.186.0**: 12 `nc_shopping_list_*` (register; the app is absent, so calls 404). **0.187.0**: real `nc_calendar_find_availability`. **0.190.0** CIMD/OAuth: inert. **0.191/0.194/0.195.0**: office readers register at import (reach note). **0.195.1-0.195.4**: fixes (page-range reads, vCard per-property fallback that still Tracebacks on FN-less vCards, RLIMIT hardening).
- Predecessor run history (2026-09-26, `now:`): attempt 1 false-STOPped at the calendar-name encoding gate (gate fixed `a1e5c69e`, carried as §4.5). Attempt 2 passed 4.1-4.7 on 0.195.4 and failed the OpenClaw consumer gate on `POST /` 404. That was a consumer-config defect, fixed in `ec432f12` (`NEXTCLOUD_MCP_URL` now ends in `/mcp`), and the §4.11 `case` guard now refuses anything else. **Re-verified 2026-09-29: the in-pod URL matches `http://nextcloud-mcp.*:8000/mcp`, mcporter 0.9.0.** The predecessor's blocker is therefore cleared at the gate/config level. It still needs a re-review and a fresh GO, and it never measured the §1.2 regression because 0.195.4 does not have it.

### 1.4 Security driver

> **Security driver: detail withheld from this public repo.**
> Tracked as **F-80459b23** (`security`). Quote the contextual tier from the sweep board, not the raw scanner severity.
> - Dashboard: `https://sweep.<DOMAIN>/findings/F-80459b23`
> - CLI: `runbooks/policy-cli.py finding show F-80459b23`

`F-f02df447` (`[AR-029]`, accepted) is the residual base-OS tally on the same
image. It is expected to change, not to clear. **Not verified:** whether
0.195.4 (the regression-free alternative in §1.6) already remediates the
F-80459b23 set. No per-tag scan was run. Check the record, or a Trivy scan of
`0.195.4`, before choosing option B.

### 1.5 Relationship to `nextcloud-mcp-0.187.1` (blocked): this plan SUPERSEDES it

The README's default is "refresh in place, keep the plan_id". This is the
exception it names ("the new target turns the change into a different job"):

(1) the hop now crosses a tag that regresses our data, and that needs an
operator decision the old plan never carried;
(2) the old plan hit its retry cap (two aborts), and its GO is void;
(3) the orchestrator dispatched this id.

On review/commit of this file, the coordinator should do these steps. This
planner writes only this file.

- DONE 2026-10-01: `nextcloud-mcp-0.187.1` set to `status: superseded` with a pointer here (re-open it if the operator picks option B, §1.6).
- DONE 2026-10-01: reverse refs re-pointed in `app-template-5.2.1`, `nextcloud-redis-hardening`, `nextcloud-fleet-35.0.1` (conflicts_with) and the prose in `n8n-2.39.8`. Left as-is: `bitnamilegacy-exit-nextcloud-db`, `kube-prometheus-stack-91.4.1` (executed; historical prose).
- STILL OWED: re-key the home-operation `go_no_go` issue from `nextcloud-mcp-0.187.1` to this id, with target 0.198.3 (or 0.195.4 if B).
- `finding_refs` carried: F-9af9baf7, F-80459b23. F-bb713800 (old drift finding) is resolved, so it was not carried.

### 1.6 The operator decision this plan cannot make

| option | what | cost |
|---|---|---|
| **A. Wait for upstream** (recommended default) | **Prerequisite: someone must FILE the upstream issue first** -- none exists (§7), so without it "wait" has no end. Issue text: *"`_get_calendar_url` unquotes names; Nextcloud calendar URIs CAN contain a literal `%` (created by CalDAV clients that percent-encode the URI); reads silently empty."* Retarget this plan to the first tag whose `_get_calendar_url` no longer unquotes blindly (§2.7 B detects it). | Security finding stays open until then. |
| **B. Take 0.195.4 now** | Revive `nextcloud-mcp-0.187.1` (its blocker is cleared, §1.3). Add this plan's §4.6 event gate to it. Supersede THIS file until upstream fixes the regression. | Only if 0.195.4 actually remediates F-80459b23 (unverified, §1.4). Next hop is then again a minor-line plan. |
| **C. Change the data** | Recreate the two `%`-URI calendars with clean URIs in Nextcloud, then run this plan (§2.7 A passes). | Recreating changes the URI, which breaks every CalDAV client syncing them (phones/desktops) and may lose subscription/share state. This is data surgery, so operator only. |
| D. Accept | Run 0.198.3 and accept that MCP consumers read 0 events from the household's busiest calendar. | Feature loss. Per operator policy, "interruption OK, data/feature loss not". Not recommended. |

## 2. Pre-checks

0. **Target still upstream head** (manual; premises have no network verb):
   ```bash
   TOKEN=$(curl -s "https://ghcr.io/token?scope=repository:cbcoutinho/nextcloud-mcp-server:pull&service=ghcr.io" \
     | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
   for t in 0.198.3 latest 0.198.4 0.199.0; do
     printf '%-8s ' "$t"
     curl -sI -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.oci.image.index.v1+json" \
       "https://ghcr.io/v2/cbcoutinho/nextcloud-mcp-server/manifests/$t" \
       | tr -d '\r' | awk 'NR==1{printf "%s ",$2} tolower($1)=="docker-content-digest:"{print $2}'; echo
   done
   # expect: 0.198.3 200 sha256:b7faa131d1c4c4dbb1da7c24ccd96d35dcb41ad6f0ac6bcd5abd69282b8cd4b8;
   #         latest 200 SAME digest; 0.198.4 404; 0.199.0 404.  (measured 2026-10-05)
   # A newer tag -> STOP, read its release body + re-run §2.7 B against it before retargeting.
   ```
1. **Premises** (six, fail-closed):
   ```bash
   python3 runbooks/plan-premises.py nextcloud-mcp-0.198.0 --require-premises
   ```
2. **Health floor**:
   ```bash
   flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
   flux get helmreleases -A   | awk 'NR==1 || $5 != "True"'
   kubectl get pods -n office -l app.kubernetes.io/name=nextcloud-mcp        # expect 1/1 Running
   kubectl get helmrelease -n office nextcloud-mcp -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'   # expect True
   ```
3. **Nextcloud apps behind the tool families** (a change here changes §4.4's "works vs 404s"):
   ```bash
   kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c 'php occ app:list' \
     | grep -iE '^[[:space:]]*- (calendar|contacts|deck|notes|tables|shoppinglist|mail|spreed|collectives|news|cookbook|files_versions|files_trashbin|systemtags):'
   # predecessor measured 2026-09-22: calendar, contacts, mail, spreed, files_trashbin, files_versions, systemtags;
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
   **F) Per-calendar EVENT reads (new; the §1.2 regression lives here).** For each calendar, the helper calls `nc_calendar_list_events` with the `name` that server itself returned (which is what a consumer does). It uses a fixed 2015-01-01..2030-12-31 range, limit 200:
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
   Re-take A-F on the day, after any Nextcloud server move.
5. **No firing alerts in office/ai**:
   ```bash
   kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 >/dev/null 2>&1 & PF=$!; sleep 2
   curl -s --data-urlencode 'query=ALERTS{namespace=~"office|ai",alertstate="firing"}' http://localhost:9090/api/v1/query \
     | python3 -c "import sys,json; r=json.load(sys.stdin)['data']['result']; n=sorted(x['metric'].get('alertname') for x in r if x['metric'].get('alertname') not in ('Watchdog','InfoInhibitor')); print(n or 'NONE FIRING')" | tee /tmp/ncmcp/alerts.before
   kill $PF 2>/dev/null
   # CAN FAIL (predecessor, 2026-09-26): count_over_time of this selector over 30d returned KubeJobFailed/MealiePodRestarted.
   # (2026-10-05: the Watchdog/InfoInhibitor exclusion moved from a PromQL `alertname!~` matcher into the python
   #  filter -- same result set; plan-premises.py --controls flagged the negative matcher because those chart-built-in
   #  alerts are declared by no PrometheusRule under kubernetes/.)
   ```
6. **Active-update marker**:
   ```bash
   runbooks/update-marker.sh add nextcloud-mcp office 2 "0.184.5->0.198.3 image bump"
   ```
7. **HARD STOP GATE: the 0.195.5 calendar-addressing regression (§1.2).** Proceed only if A or B passes:
   ```bash
   # A) data side: does any owned calendar still have a literal '%' in its URI?  (from §2.4 F)
   python3 -c 'import json; d=json.load(open("/tmp/ncmcp/events.before.json")); n=sum(v["pct_uri"] for v in d.values()); print("pct-URI calendars:", n); raise SystemExit(0 if n==0 else 1)' \
     && echo "7A PASS" || echo "7A FAIL"
   # B) code side: does the TARGET tag still unquote the name before encoding?
   #    Fetch to a file and FAIL CLOSED: a failed fetch (bad ref, rate limit, 404 body) must never read as "0 matches".
   REF=v0.198.3; F=/tmp/ncmcp/calendar.py.$REF; rm -f "$F"
   if ! gh api "repos/cbcoutinho/nextcloud-mcp-server/contents/nextcloud_mcp_server/client/calendar.py?ref=$REF" \
        -H 'Accept: application/vnd.github.raw' > "$F"; then echo "7B FAIL ($REF): fetch failed -- gate NOT evaluated"
   elif ! grep -q 'def _get_calendar_url' "$F"; then echo "7B FAIL ($REF): _get_calendar_url absent -- file moved/renamed, re-read by hand"
   elif [ "$(grep -c 'unquote(calendar_name)' "$F")" -eq 0 ]; then echo "7B PASS ($REF): unquote(calendar_name) count=0 -- re-read the new _get_calendar_url, then still run §4.6"
   else echo "7B FAIL ($REF): unquote(calendar_name) count=$(grep -c 'unquote(calendar_name)' "$F")"; fi
   # measured 2026-10-01: 7A FAIL (2); 7B FAIL at v0.198.1 (count=1), v0.198.0 (1), master (1); PASS at v0.195.4 (0);
   # re-measured 2026-10-05: 7B FAIL at v0.198.3 (count=1) and master (count=1) -- calendar.py:568 unchanged;
   #   REF=main -> "7B FAIL (main): fetch failed" (the default branch is `master`; the old pipe form printed 0 = false PASS here)
   # BOTH FAIL -> STOP. Do not commit. Clear the marker (runbooks/update-marker.sh clear nextcloud-mcp)
   #   and return the plan to the operator with §1.6. This is the expected outcome today.
   ```
   *Gate can fail AND pass:* 7A read 2 on live data (2026-09-29). 7B was dry-run 2026-10-01 against four refs and printed
   FAIL for v0.198.1/v0.198.3/master (count 1), PASS for v0.195.4 (count 0), and FAIL-closed for the non-existent ref `main`
   (fetch error, gh rc=1). Read the printed `7B PASS`/`7B FAIL` verdict line; there is no other output to interpret.

## 3. Steps

1. §2.0-2.7 green (in practice: §2.7 passed via A or B). Otherwise stop here.
2. Edit the tag (BSD-sed safe, POSIX class). Dry-tested 2026-10-05 on a scratch copy (macOS BSD sed): `34c34 <               tag: 0.184.5 / >               tag: 0.198.3`, one hunk. The inverse restores byte-identical:
   ```bash
   cd /Users/mu/code/cberg-home-nextgen || exit 1
   sed -i '' 's/^\([[:space:]]*tag: \)0\.184\.5$/\10.198.3/' kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml
   git diff --stat -- kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml    # expect 1 file, 1+/1-; 0 files = no-op: STOP
   git diff -- kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml | grep -E '^[-+][[:space:]]+tag:'
   # expect exactly:  -              tag: 0.184.5   /   +              tag: 0.198.3
   ```
3. Commit + push (shared worktree: `--only`, verify subject):
   ```bash
   cat > /tmp/ncmcp/msg-nextcloud-mcp-0.198.0.txt <<'EOF'
   feat(nextcloud-mcp): image 0.184.5 -> 0.198.3

   Crosses fourteen 0.x minor lines (0.185 .. 0.198). Release bodies and
   source diffs read per tag (runbooks/maintenance/plans/nextcloud-mcp-0.198.0.md
   section 1). BREAKING tags 0.185.0/0.194.0/0.196.0/0.197.0/0.198.0 are inert
   for single_user_basic with no vector sync/SAR; 0.198.1 is a CIMD/OAuth-only
   fix and 0.198.2/0.198.3 are vector-sync/Postgres-only fixes (all inert
   here); 0.192.0 adds apply_to_series
   (safer default). 21 new tools, no tool removed, mcp 2.1.1, python 3.14 base.
   The 0.195.5 calendar-addressing gate (section 2.7) passed before this commit.

   security_ref: F-80459b23
   finding_refs: F-9af9baf7, F-80459b23
   EOF
   git fetch origin main && git merge --ff-only origin/main
   git commit --only kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml -F /tmp/ncmcp/msg-nextcloud-mcp-0.198.0.txt
   git show --stat HEAD      # exactly ONE file
   git log -1 --format=%s    # expect: feat(nextcloud-mcp): image 0.184.5 -> 0.198.3 ; else `git commit --amend --only -F <msg>` before push
   git push origin main
   git rev-parse HEAD > /tmp/ncmcp/bump.sha && cat /tmp/ncmcp/bump.sha
   ```
4. Reconcile (SOP permits forcing in a window; `kustomization/nextcloud-mcp` is in ns `office`, verified live):
   ```bash
   flux reconcile kustomization nextcloud-mcp -n office --with-source
   flux reconcile hr -n office nextcloud-mcp
   ```
   Single replica, no volumes (premise 5), so no RWO/Recreate concern. There is no migration Job, and `upgrade.remediation.retries: 3` stays as is.
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
   # expect ONE pod, restarts=0, imageID ending sha256:b7faa131d1c4c4dbb1da7c24ccd96d35dcb41ad6f0ac6bcd5abd69282b8cd4b8
   #   (f6d88397… = old build still serving; 427e0826… = 0.198.1 / 116d9d23… = 0.198.2 / dbfeb3eb… = 0.198.0 / 24417dcb… = 0.195.4 committed by mistake)
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
   # vCard Tracebacks are known data (FN-less contacts; client/contacts.py:734 at v0.198.0/v0.198.1, file untouched through v0.198.3, unchanged since 0.195.4).
   # RE-RUN this scan AFTER §4.6 into /tmp/ncmcp/log.after-events (same script, other path): §4.6 is the first traffic
   # that addresses the %-URI calendars, and caldav's "Deviation from expectations found" ERROR lines it logs on a
   # wrong-collection request are an INDEPENDENT signal of the §1.2 regression, not tied to event counts.
   # CAN FAIL: predecessor's reviewer injected one unattributed Traceback + one ERROR line into a copy -> assertion fired.
   ```
3. **CONTENTS ASSERTION (mcp 2.x lifespan landed)**:
   ```bash
   kubectl logs -n office deploy/nextcloud-mcp | grep -c 'Starting MCP session in single-user BasicAuth mode'
   # expect 1 right after start and STILL 1 after §4.4's sessions. The log string is at app.py:979 at v0.198.0 (app.py unchanged through 0.198.3).
   #   On 0.184.5 it climbs per session: 24 lines on the live pod 2026-09-29. A climbing count = old build.
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
   117 and the exact 21 names were measured live on 0.195.4 (predecessor attempt 2, gate PASS). 0.195.5-0.198.3 add tools only in the gated `server/sar.py` (§1.2).
5. **CONTENTS ASSERTION (calendar LIST: same set, encoding-shape tolerant).** Carried verbatim from the predecessor's fixed gate (`a1e5c69e`, reviewer-proven 2026-09-26). This gate CANNOT see the §1.2 regression. §4.6 is the one that can.
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
6. **CONTENTS ASSERTION (per-calendar EVENT reads: the §1.2 regression). New gate.**
   ```bash
   python3 /tmp/ncmcp/events.py /tmp/ncmcp/calendars.after /tmp/ncmcp/events.after.json
   python3 /tmp/ncmcp/events_gate.py /tmp/ncmcp/events.before.json /tmp/ncmcp/events.after.json
   # PASS: every calendar non-empty before is non-empty after, |delta| <= 2 (edits during the window).
   # FAIL prints: "calendar #N (pct_uri=True): 200 -> 0 events (SILENT EMPTY READ)" -> §5 rollback.
   kubectl logs -n office deploy/nextcloud-mcp > /tmp/ncmcp/log.after-events
   # then re-run the §4.2 python scan with "log.after-start" replaced by "log.after-events"; any unattributed ERROR -> §5.
   ```
   *Demonstrated 2026-09-29 on 0.184.5.* `events.py … --emulate-double-decode` sends exactly the URI that 0.198.0's (= 0.198.1's = 0.198.3's) `_get_calendar_url` builds, `quote(unquote(name))`. It read `[3, 0, 0, 0]` against a real `[3, 0, 200, 0]` with `isError=false` throughout, and the gate FAILED with the SILENT EMPTY READ line (rc=1). Before-vs-before PASSes. **Limit:** the second `%`-URI calendar holds 0 events in range, so a regression on it is invisible to counts. §2.7 A covers it structurally.
7. **CONTENTS ASSERTION (0.192.0 BREAKING visible)**: `nc_calendar_bulk_operations` gains `apply_to_series`, default False, and loses no property:
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
8. **CONTENTS ASSERTION (0.188.1 contacts)**: schema gained `include_photos`/`limit`/`offset`, and a live list returns `has_photo` with no inline photo by default:
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
   # CAN FAIL: predecessor's reviewer matched 91 inline payloads with this regex on 0.184.5 (4 in the first 5).
   ```
9. **Memory + restarts (python 3.14 + office readers + TextProcessor at import)**, 5 min after Ready:
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
10. **No new firing alerts**: re-run §2.5 and diff against `/tmp/ncmcp/alerts.before` (expect `NONE FIRING` both).
11. **The real consumers**:
    - OpenClaw (`ai`, mcporter 0.9.0, TS SDK). Carried from the predecessor with the corrected endpoint guard. mcporter exits 0 on HTTP 500/`isError`, so the gate is the JSON body:
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
      Endpoint guard re-checked 2026-09-29: the in-pod URL matches, mcporter 0.9.0. The checker's FAIL paths (isError, HTTP 500, empty) were proven by the predecessor's reviewer.
    - Attended: the operator opens the `nextcloud` server in Claude Desktop (`uvx mcp-proxy`, python mcp 2.x client), lists the root folder, and **asks for this week's events from the busiest calendar**. That is the human form of §4.6. Record the `mcp` version uvx resolved.
12. **Close out**: `runbooks/update-marker.sh clear nextcloud-mcp`. Retire this file (and the superseded predecessor) in the same commit series. F-9af9baf7/F-80459b23 are script-owned and should close on the next sweep, so verify that rather than assume it.

## 5. Rollback

Stateless (premises 4-5), so the rollback is an inverse image-tag edit. Not `git revert`: in this shared worktree it refuses (rc=128) whenever another session has staged anything. The predecessor reproduced that.

```bash
cd /Users/mu/code/cberg-home-nextgen || exit 1
sed -i '' 's/^\([[:space:]]*tag: \)0\.198\.3$/\10.184.5/' kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml
git diff --stat -- kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml    # expect 1 file 1+/1-; 0 files = no-op: STOP
cat > /tmp/ncmcp/msg-revert-nextcloud-mcp-0.198.0.txt <<'EOF'
Revert "feat(nextcloud-mcp): image 0.184.5 -> 0.198.3"

Rollback per runbooks/maintenance/plans/nextcloud-mcp-0.198.0.md section 5
(stateless bridge, image tag only). Reverts the commit in /tmp/ncmcp/bump.sha.
EOF
git commit --only kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml -F /tmp/ncmcp/msg-revert-nextcloud-mcp-0.198.0.txt
git show --stat HEAD && git log -1 --format=%s    # ONE file; subject = Revert "feat(nextcloud-mcp): image 0.184.5 -> 0.198.3"
git push origin main
flux reconcile kustomization nextcloud-mcp -n office --with-source && flux reconcile hr -n office nextcloud-mcp
kubectl rollout status deploy/nextcloud-mcp -n office --timeout=180s
kubectl get pod -n office -l app.kubernetes.io/name=nextcloud-mcp -o jsonpath='{range .items[*]}{.metadata.name} {.status.containerStatuses[0].imageID}{"\n"}{end}'
# expect imageID ending sha256:f6d8839722587f2cd37ec5218a18479f9e313be9904ad4f6bbb36f98bc827065
```
(Inverse sed dry-tested 2026-10-05 on macOS against the 0.198.3 forward edit: restores the scratch copy byte-identical, `cmp` clean.)

Confirm the cluster is back:
- Re-run §4.4. `tools.after` must equal `tools.before` (96, `comm` empty both ways), and protocol must read `2025-06-18 1.29.0`.
- Re-run §4.6 into `events.revert.json` and gate it against `events.before.json`. The busiest calendar must be back at its count.
- Re-run §4.11.
- If the failure was consumer-side (protocol), note it on `F-9af9baf7` via `policy-cli.py finding detail`. The fix there is pinning the client, not holding the server.

## 6. Interference notes

- **Consumers, not shared infra.** OpenClaw (`ai`, `mcporter-config.yaml` entry `nextcloud`) and Claude Desktop lose or change tools silently if this goes wrong. Treat any post-bump OpenClaw Nextcloud-tool failure as this plan's. The §1.2 regression is precisely such a silent failure: "no events" instead of an error. That is why §4.6 exists and why the operator's Claude Desktop check asks for events, not just files.
- **Same file as `app-template-5.2.1`** (nightly:2026-10-02). Its Batch A sed changes line 12 (chart) of this helmrelease. This plan changes line 34 (tag). The edits do not collide textually, but they must not share a night (§4.2 attribution). Premise 6 accepts either chart version.
- **Nextcloud server work** (`nextcloud-redis-hardening` 10-01, `nextcloud-fleet-35.0.1` 10-18, `bitnamilegacy-exit-nextcloud-db` if revived): every §4 contents gate is a live call into that server, so never the same slot. After 35.0.1 lands, premise 2 fails closed. Re-vet, because Nextcloud 35 CalDAV behaviour feeds straight into §1.2's analysis.
- **Prometheus**: §2.5/§4.9/§4.10 read it. `kube-prometheus-stack-91.9.0` (draft, 2026-10-05) restarts it, so it is in `conflicts_with` here and this plan is already in its list (both sides, re-checked 2026-10-05).
- **Attended only.** The deny rule mandates it, and `capability_change: true` routes it there anyway. Never `nightly`. Nothing here touches Longhorn, cert-manager, cilium, coredns or the Gateways.
- **`talos-linux-1.14.2`** (draft, `exclusive: true`, needs_reboot, sun-attended only): its node roll restarts this pod and the Nextcloud server it reads. Its `exclusive` flag already keeps every other plan out of its slot, so it is not listed in `conflicts_with`. If the two ever land on adjacent days, take §2.4's baseline AFTER the roll, never before it.
- **Supersession bookkeeping** (§1.5): `nextcloud-mcp-0.187.1` is `superseded` and the reverse refs are re-pointed (2026-10-01). Its `conflicts_with` entry here was dropped 2026-10-05 (a terminal plan binds nothing). Only the `go_no_go` re-key is still owed. If option B revives 0.187.1, the scheduler must never place both.

## 7. What I could not verify (2026-09-29; re-read 2026-10-01 for the 0.198.1 retarget and 2026-10-05 for 0.198.3)

- **Whether 0.195.4 remediates F-80459b23.** No per-tag scan was run. This decides whether option B (§1.6) closes the security driver.
- **The upstream fix timeline.** No upstream issue exists for the literal-`%` calendar-URI case (searched 2026-09-29; the only related one is #1449, closed). Filing one is an operator/agent action outside this plan.
- **Write-path behaviour of 0.198.x on the `%`-URI calendars** (create/update/delete event). By code, they target the same wrong URI. Not exercised: no writes were made against the live calendars.
- **The second `%`-URI calendar** holds no events in 2015-2030, so §4.6 cannot see a regression on it. §2.7 A covers it structurally.
- **Behaviour on the wire of TS SDK 1.30.0 (mcporter) against mcp 2.1.1.** Not re-measured here. The predecessor's attempt 2 did reach 4.10 on 0.195.4 (same mcp 2.1.1), where it failed only on the since-fixed URL.
