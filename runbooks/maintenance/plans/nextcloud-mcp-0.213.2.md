---
plan_id: nextcloud-mcp-0.213.2
component: nextcloud-mcp
pr: 258                               # Renovate, branch renovate/ghcr.io-cbcoutinho-nextcloud-mcp-server-0.x, OPEN; title
                                      # "( 0.184.5 → 0.213.2 )" and the branch diff is the one tag line (read 2026-11-18).
kind: image
current: "0.184.5"
target: "0.213.2"                     # GHCR 0.213.2 = 200, index sha256:655c2864…6d325 == `latest`; 0.213.3 / 0.214.0 = 404.
                                      # GitHub v0.213.2 published 2026-11-17T15:04Z, not a pre-release; 48 h age gate clears
                                      # 2026-11-19T15:04Z. Upstream master HEAD 67896741 IS the 0.213.2 bump (nothing newer).
update_type: minor                    # semver label only. At major 0 the MINOR is the breaking axis; this hop crosses
                                      # TWENTY-NINE minor lines (0.185 .. 0.213).
risk: medium                          # stateless bridge, tag-only rollback, nothing forward-only. Medium because (1) the 0.195.5
                                      # calendar-addressing regression is STILL in the target (section 1.1, re-measured
                                      # 2026-11-18: 2.7-B FAIL 2/4), so the EXPECTED outcome today is a STOP at 2.7, nothing
                                      # committed; (2) 0.206.0 refuses undeclared tool arguments; (3) 0.207.3 changes the
                                      # advertised type of the mail recipient arguments; (4) 0.211.0 re-packages the Nextcloud
                                      # client layer into a second wheel. 0.212.0..0.213.2 add nothing that applies here (1.2).
est_duration_min: 50
needs_reboot: false
touches:
  namespaces: [office]
  resources:
    - helmrelease/nextcloud-mcp
    - deployment/nextcloud-mcp
                                      # httproute/nextcloud-mcp and service/nextcloud-mcp re-render from the same HR but their
                                      # spec does not change (the image tag is the whole diff).
  shared: [monitoring]                # READ-only: 2.5 / 4.9 / 4.10 read Prometheus. No gateway, CNI, DNS, storage or shared DB
                                      # is perturbed. Consumers (ai/openclaw via mcporter, Claude Desktop via the envoy-internal
                                      # HTTPRoute) are blast radius, not shared infra (section 6).
depends_on: []                        # Flux `dependsOn: nextcloud` is ordering only; no release note 0.185..0.213.2 states a
                                      # minimum Nextcloud server version.
supersedes:                           # this plan replaces every open/blocked predecessor; the coordinator retires them (1.6).
  - nextcloud-mcp-0.211.1             # status blocked on disk (untracked, another session's file) -> superseded
  - nextcloud-mcp-0.206.0             # already superseded (by 0.211.1); re-point superseded_by
  - nextcloud-mcp-0.204.0             # already superseded (by 0.211.1); re-point superseded_by
  - nextcloud-mcp-0.203.0             # already superseded (by 0.211.1); re-point superseded_by
  - nextcloud-mcp-0.202.1             # already superseded (by 0.203.0)
conflicts_with:
  - nextcloud-mcp-0.211.1             # SUPERSEDED BY THIS PLAN; same PR, same deployment, never both.
  - nextcloud-12.0.2                  # draft; quiesces Nextcloud (every section 4 contents gate is a live call into it).
  - nextcloud-9.4.3                   # vetted; chart + image roll of deployment/nextcloud (replaced nextcloud-35.0.2-digest-d88929d).
  - redis-fleet-8.10.3                # vetted, sun-attended:2026-11-29; restarts nextcloud-redis and deployment/nextcloud.
  - bitnamilegacy-exit-nextcloud-db   # blocked; quiesces Nextcloud if revived.
  - kube-prometheus-stack-93.3.0      # draft, exclusive: restarts Prometheus, which this plan's gates read.
  - helm-drift-detection              # vetted, sat-attended:2026-11-28; adds a spec field to every HelmRelease incl. this one.
  - flux-oci-chart-sources            # vetted, sun-attended:2026-12-13; re-points bjw-s app-template HRs (this HR's sourceRef).
  - envoy-gateway-1.10.0              # vetted, exclusive; Claude Desktop reaches this service through envoy-internal (4.11).
  - coredns-1.50.5                    # vetted; both consumers and the bridge itself resolve cluster names during every gate.
  - longhorn-1.13.0                   # vetted, exclusive; storage engine under Nextcloud's volumes.
  - talos-linux-1.14.6                # draft, exclusive node roll (replaced talos-linux-1.14.5); evicts this pod and Nextcloud.
  - etcd-timeouts-5000-500            # blocked; restarts etcd on all control-plane nodes (blinds every kubectl gate).
exclusive: false
security_ref: F-80459b23              # security driver; detail stays on the record (section 1.5).
capability_change: true               # vs LIVE 0.184.5: +25 tools registering here (6 WRITE), behaviour changes on live tools
                                      # (1.3/1.4), undeclared tool arguments refused (0.206.0), mail recipient arguments
                                      # advertised as arrays (0.207.3), contacts ADR writes (0.210.0), 30-min MCP session idle
                                      # timeout (0.202.1), and the 0.195.5 calendar change. 0.212.0..0.213.2 add none here.
rollback_class: git-revert            # no PVC, no volumes, no DATABASE_URL/TOKEN_STORAGE_DB (premises). Executed as an inverse
                                      # tag edit (section 5). Caveat: anything a consumer writes through the new WRITE tools
                                      # stays in Nextcloud after a rollback (household data, not written by this plan).
finding_refs: [F-80459b23, F-9af9baf7] # `finding list --grep nextcloud-mcp` 2026-11-18: F-80459b23 (security, critical) and
                                      # F-9af9baf7 (version; title still reads "0.184.5 → 0.212.0", script-owned, will re-key)
                                      # plus F-f02df447 (AR-029 accepted residual, not owned by a plan).
review: null
status: blocked                       # 2026-11-18 sweep fa131284: 2.7-B measured FAIL (2/4 calendars) on v0.213.2. Unblock when 2.7-B prints PASS on a newer tag.
blocked_reason: "upstream bug: nextcloud-mcp _get_calendar_url double-decodes calendar names with a literal %; still present in v0.213.2 and master (2026-11-18). Stay on 0.184.5; operator to file upstream issue (text in 1.7)."
window: null                          # If ever unblocked: attended slot only (sat/sun), never nightly.
premises:
  - id: image-is-still-0.184.5
    why: >-
      current: and the rollback target are 0.184.5. If the cluster has moved, the
      diff, the baselines and the rollback digest are wrong.
    run: kubectl get deploy -n office nextcloud-mcp -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: ghcr.io/cbcoutinho/nextcloud-mcp-server:0.184.5
  - id: renovate-pr-258-targets-0.213.2
    why: >-
      Drift detector. The Renovate branch commit subject is the PR title; it read
      0.213.2 on 2026-11-18. Anything newer fails this, which forces a re-read of
      the new tag and a 2.7-B re-run before anything merges. Run the 2.0 git
      fetch first.
    run: git log -1 --format=%s origin/renovate/ghcr.io-cbcoutinho-nextcloud-mcp-server-0.x
    expect_matches: '^feat\(container\): update ghcr\.io/cbcoutinho/nextcloud-mcp-server \( 0\.184\.5 → 0\.213\.2 \)$'
  - id: nextcloud-server-is-35
    why: >-
      Sections 4.5/4.6/4.13 read CalDAV/OCS from this server. Live 35.0.2 on
      2026-11-18. A 36.x or 34.x server fails this closed and the 2.4
      baselines must be re-taken against the new server.
    run: kubectl get deploy -n office nextcloud -o jsonpath='{.spec.template.spec.containers[?(@.name=="nextcloud")].image}'
    expect_matches: 'docker\.io/nextcloud:35\.0\.[0-9]+(@sha256:[0-9a-f]+)?$'
  - id: deployment-mode-still-single-user-basic
    why: >-
      The 0.185.0 elicitation break, every OAuth/CIMD/scope change between
      0.190 and 0.213.2 (incl. the 0.213.2 upstream-scope default) and the
      0.200.1 BasicAuthMiddleware 401 path are inert only in single_user_basic.
      Any other mode voids section 1.
    run: kubectl get secret -n office nextcloud-mcp-config -o json | jq -r '.data.MCP_DEPLOYMENT_MODE' | jq -Rr '@base64d'
    expect_exact: single_user_basic
  - id: exactly-four-config-keys
    why: >-
      Proves no DATABASE_URL/TOKEN_STORAGE_DB (free rollback), no vector-sync,
      semantic-search or SAR switch (0.196-0.199, the 0.208/0.209 search work and
      the 0.213.1 startup BM25 load stay off), no EMBEDDING_GATEWAY_* (0.213.0),
      no NEXTCLOUD_OIDC_SCOPES (0.213.2), no DOCUMENT_PARSE_MEM_LIMIT_MB, no OTEL_*.
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
generated: "2026-11-18"
---

## 1. Summary & why held

`kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml:34` pins
`ghcr.io/cbcoutinho/nextcloud-mcp-server` at `0.184.5` (live 2026-11-18: pod
`nextcloud-mcp-55ff568864-4z4rl`, imageID `sha256:f6d88397…c827065`, 2 restarts,
96 tools). Renovate PR **#258** now reads `0.184.5 → 0.213.2`. The auto-updater
holds it because this is a 0.x release-line move (`*nextcloud-mcp*` deny rule,
`max: patch`): at major 0 the minor is the breaking axis and this hop crosses 29
minor lines. Security-driven: F-80459b23 (1.5).

This plan **supersedes `nextcloud-mcp-0.211.1`** (blocked, last targeted 0.212.0)
and with it the whole predecessor chain (1.6). It carries the predecessor's
verified gate set forward unchanged except for the target strings, digests and
source line numbers, which were re-read against v0.213.2.

**Verdict 2026-11-18: DO NOT RUN until section 2.7-B prints PASS.** The
0.195.5 calendar double-decode is still in v0.213.2 and in upstream master
(1.1). I re-ran 2.7-B today against the live calendar list and the v0.213.2
source: `7B FAIL: 2/4 calendars addressed correctly`, exit 1. The positive control
(same file, only line 589 changed) prints `7B PASS: 4/4`, so the gate still
works. The upstream issue the predecessor asked the operator to file (1.7) has
**not been filed** (searched 2026-11-18, 0 hits). The four new tags
(0.212.0..0.213.2) are inert for this deployment (1.2), so nothing in this
refresh changes the risk. Only the target and the evidence moved.

### 1.1 Upstream fix search (2026-11-18): none

- **Tags.** `gh release list`: v0.213.2 (2026-11-17T15:04Z, Latest), v0.213.1
  (2026-11-17T00:20Z), v0.213.0 (2026-11-16T22:10Z), v0.212.0. GHCR `0.213.3` /
  `0.214.0` = 404. Upstream master HEAD `67896741` (2026-11-17T15:03Z) is the
  `bump: version 0.213.1 → 0.213.2` commit, so master = target.
- **Code.** `packages/nextcloud-client/src/nextcloud_client/calendar.py:589` at
  v0.213.2 is byte-identical to v0.212.0:
  `return encode_dav_url(f"{self._calendar_home_url}{unquote(calendar_name)}/")`,
  with the same docstring premise (*"Nextcloud calendar URIs never contain a
  literal `%`"*). The `list_calendars` naming line
  (`calendar_name = unquote(calendar_url.rstrip("/").split("/")[-1])`) is still
  present (1 match), so the 2.7-B model still applies. `compare v0.212.0...v0.213.2`
  (20 commits, 25 files) touches no file under `nextcloud_client/` except `base.py`
  (metrics hook placement, 1.2).
- **Issues/PRs.** `gh search issues|prs` for `_get_calendar_url`,
  `integration_google`, `calendar percent`, `Google Calendar import`: only
  #1449 (closed), PR #1563 (merged, the change that introduced the regression)
  and PR #1450 (merged). **The bug is still unreported upstream.**
- **Measured 2026-11-18** (scratch dir, live `calendars.before` taken through
  0.184.5 with the 2.4 `call.sh`, read-only MCP calls): 4 calendars, 2 with a
  `%` URI; `calurl_gate.py` on v0.213.2 = `FAIL 2/4` (calendars #3, #4,
  `pct_uri=True`), exit 1; on the one-line-fixed copy = `PASS 4/4`, exit 0.

Mechanism (unchanged, derived from source in the predecessor and re-confirmed by
the run above): `list_calendars()` hands callers the once-decoded href segment,
which here contains a literal `%` (`…+%28Google+Calendar+import%29`).
`_get_calendar_url()` unquotes it again, and `encode_dav_url` encodes once, so the
request addresses `…+(Google+Calendar+import)`, a collection that does not
exist. Result: `nc_calendar_list_events` returns 0 events with `isError=false`
(carried 2026-10-21: real `[3, 0, 200, 0]`, post-0.195.5 `[3, 0, 0, 0]`), and
cross-calendar search silently skips those calendars.

| tag | GHCR (anonymous token, OCI index) |
|---|---|
| `0.184.5` (live) | 200, `sha256:f6d8839722587f2cd37ec5218a18479f9e313be9904ad4f6bbb36f98bc827065` (= running pod `imageID`, 2026-11-18) |
| `0.195.4` (last tag without the regression; option B) | carried: `sha256:24417dcb804fc65bcb8712226bf70be71018aefd2ec7b27e9392a4d4e1ed707c` |
| `0.212.0` (predecessor's target) | carried 2026-11-16: `sha256:8fbf449a68e92b416e475804dd4adaf4f9c43a5b3d83e8dc0da0b112b359700e` |
| **`0.213.2` (target)** | **200, `sha256:655c2864b48fd3f0696480ebe19a165ff114a582b30b9cec1d6ab4923586d325`** (2026-11-18) |
| `latest` | 200, identical to 0.213.2 |
| `0.213.3`, `0.214.0` | 404 |

### 1.2 What changed 0.212.0 -> 0.213.2 (read here: release bodies + `compare v0.212.0...v0.213.2`)

Files changed: `Dockerfile`, `app.py`, `cli.py`, `config.py`,
`observability/{metrics,middleware,tracing}.py`, `providers/{gateway,gateway_batch,ner,registry,rerank}.py`,
`packages/nextcloud-client/src/nextcloud_client/base.py`, both `pyproject.toml`,
`uv.lock`, docs, tests. **No file under `server/` changed: the tool surface is
identical to 0.211.1/0.212.0** (121 vs live 96, see 4.4).

| tag | release note (verbatim) | applies to us? |
|---|---|---|
| 0.212.0 | *"db: apply procrastinate 3.11's schema migration via Alembic"*; *"deps: update dependency procrastinate to >=3.11,<3.12"* | Inert: Alembic revision runs only with an app DB; we have no DATABASE_URL (premise `exactly-four-config-keys`). Read by the predecessor 2026-11-16. |
| 0.213.0 | *"gateway: authenticate with a projected ServiceAccount token file"*; *"gateway: address Sonar findings on FileTokenProvider"*; *"gateway: diagnosable token-file failures and stable auth log labels"* | Inert: new `EMBEDDING_GATEWAY_TOKEN_FILE` setting and a new `ValueError` in `Settings.__post_init__` when it is combined with the M2M trio. Both fire only with `embedding_provider == "gateway"` / the key set; none of those keys exist here (premise). |
| 0.213.1 | *"observability: load BM25 at startup and emit stable HTTP status keys"* | Mostly inert. `_load_bm25_model()` is called only right after `_init_qdrant_collection_with_retry()` inside the vector-sync startup branches (`app.py` ~2375 and ~2566), which do not run here (vector sync off). The Dockerfile now sets `ENV OTEL_SEMCONV_STABILITY_OPT_IN=http/dup` and the HTTP middleware adds `http.request.method` / `http.response.status_code` span attributes: only visible with tracing on (no `OTEL_*` keys). `base.py` moves the `on_api_call` metrics hook into a `try/finally` inside the trace span for both the buffered and the streamed request path. That is the only change in the Nextcloud client layer that every tool call runs through. Error re-raising (`HTTPStatusError`/`RequestError` enrichment) is unchanged in the diff. Gates 4.5-4.8 and 4.13 exercise both paths. |
| 0.213.2 | *"auth: request every supported scope upstream by default"* | Inert: changes the default of `--oauth-scopes` / `NEXTCLOUD_OIDC_SCOPES` (now `DEFAULT_OIDC_SCOPES`, adds mail/talk/collectives/shopping_list/semantic/sar scopes). Used only by the OAuth AS proxy; single_user_basic never requests upstream scopes (premise `deployment-mode-still-single-user-basic`). |

Version-dependent gate anchors re-read at v0.213.2: `app.py:1065`
("Starting MCP session in %s BasicAuth mode"), `app.py:3411`
("BasicAuthMiddleware enabled"), `plugins.py:126/130` (unchanged),
`dav_urls.py` (61 lines, fetched for 2.7-B), `nextcloud-client==0.213.2`
pinned in the root `pyproject.toml` (lockstep), so 4.12 expects `0.213.2/0.213.2`.

### 1.3 0.206.0 -> 0.212.0 (carried from nextcloud-mcp-0.211.1, read per tag + source diff there)

- **0.206.1 / 0.207.1 / 0.207.2 / 0.208.1 / 0.210.1 / 0.211.1**: PDF parse
  worker threads, a config warning for an unset key, classifier text, lint,
  SonarCloud hygiene and base-image digest. Inert or read-path only.
- **0.207.0** `nc_tables_get_row`, `nc_tables_read_view`: app-gated, Tables absent (4.4 asserts 0).
- **0.207.3** mail recipients typed as `list[MailRecipient]`, addresses
  validated, recipient arrays accepted on `send_message`/`save_draft`. **Applies
  to a live WRITE tool**: on 0.184.5 `to`/`cc`/`bcc` are `string`. Gate 4.16.
- **0.208.0 / 0.209.0** exact/hybrid search algorithms on `nc_semantic_search`: not registered here.
- **0.210.0** contacts write ADR on create/update: additive, not exercised.
- **0.211.0 BREAKING (packaging)**: the client layer is the separate
  `nextcloud_client` wheel; loggers renamed `nextcloud_mcp_server.client.*` ->
  `nextcloud_client.*`; `from_env()`, `auth.BearerAuth`, `controllers`,
  `models.users` removed. We import nothing from the project and no repo file
  filters on the old logger name (grep 2026-11-14, carried). Failure shape is an
  ImportError crash loop or a missing module at first call; probes are tcpSocket,
  so gates 4.2, 4.4, 4.12 and the per-family reads carry it.

### 1.4 0.184.5 -> 0.206.0 (carried from the earlier plans, source-verified there)

- **0.185.0 BREAKING** mcp SDK 1.29 -> 2.x, Python 3.12 -> 3.14; elicitation
  change inert in single_user_basic. Lifespan runs once per container (4.3).
- **0.186.0-0.189.0** +12 `nc_shopping_list_*` (app absent, calls 404), +9
  `nc_webdav_*` tag/trash/version tools (4 WRITE), contacts photo opt-in + paging
  (4.8), real `find_availability`.
- **0.192.0 BREAKING** `nc_calendar_bulk_operations` leaves recurring series
  alone unless `apply_to_series=true` (4.7).
- **0.194.0 / 0.196.0 / 0.197.0 / 0.198.0 BREAKING** captioning key rename,
  vector-sync indexing, SAR scopes, `SAR_ENABLED`: inert (premise).
- **0.195.5** the regression of section 1.1.
- **0.199.0 BREAKING** semantic deps no longer default on PyPI; *"The Docker
  image is unaffected"* (4.12 asserts it). 0.199.1 fixed-offset datetimes stored as UTC.
- **0.200.x** Talk thread params; OCS header moved into the client factory (4.13).
- **0.201.1** handshake advertises the package version (4.4). **0.202.0**
  `nc_notes_list_notes`, app-gated (Notes absent). **0.202.1** 30-minute
  streamable-HTTP session idle timeout (4.11).
- **0.203.0** `nc_mail_save_draft`, `nc_mail_view_attachment`,
  `nc_webdav_edit_file`, `nc_webdav_view_image`. **0.203.2**
  `nc_calendar_manage_calendar(action="list")` returns one block. **0.203.3**
  every Nextcloud call moved httpx -> httpx2. **0.204.0** contacts write vCard N.
- **0.204.1** OAuth scopes enforced on MCP resources: inert in single_user_basic.
- **0.204.2** Starlette 0.x -> 1.x under the whole HTTP layer. Gates 4.2-4.4.
- **0.205.0** `nc_calendar_list_events` applies filters before the limit and adds
  `truncated: bool`; negative `limit` refused. Gate 4.14. **0.205.1** more
  WARNING lines by design. **0.205.3** vCard N/ADR escape handling on read (4.8).
- **0.206.0 BREAKING**: *"tool calls carrying arguments absent from the tool's
  inputSchema now return an error (isError) instead of succeeding with the extra
  keys ignored."* Applies to every tool and every consumer. Gates 2.4-H, 4.15.

**Net config/env/auth impact 0.184.5 -> 0.213.2 for THIS deployment** (four
keys, single_user_basic, no DB, no vector sync): no required new key, no renamed
key we set, no removed key we set. Every auth change (0.190-0.204.1 OAuth/CIMD/scopes,
0.213.0 gateway token file, 0.213.2 scope default) sits behind a mode or key we
do not use. The consumer-visible changes are behavioural: undeclared arguments
refused (0.206.0), recipient arrays (0.207.3), session idle reaping (0.202.1),
+25 tools including WRITE tools, and the calendar regression.

### 1.5 Security driver

> **Security driver: detail withheld from this public repo.**
> Tracked as **F-80459b23** (`security`). Quote the contextual tier from the sweep board, not the raw scanner severity.
> - Dashboard: `https://sweep.<DOMAIN>/findings/F-80459b23`
> - CLI: `runbooks/policy-cli.py finding show F-80459b23`

`F-f02df447` (`[AR-029]`, accepted) is the residual tally on the same image.
Whether 0.213.2 (or 0.195.4, option B) remediates the F-80459b23 set is a
per-tag scan question; the answer goes on the record
(`policy-cli.py finding detail F-80459b23 --plan nextcloud-mcp-0.213.2`), never
into this file. Not scanned by this planner today. The base image digest may
have moved again (Dockerfile changed in 0.213.1), so the predecessor's 0.212.0
scan does not carry.

### 1.6 Supersession

This plan SUPERSEDES `nextcloud-mcp-0.211.1` (status `blocked`, untracked file
owned by another session) and, through it, `-0.206.0`, `-0.204.0`, `-0.203.0`
(already `superseded` by 0.211.1) and `-0.202.1` and older (already
`superseded`). This planner edits none of them.

Owed by the coordinator (this planner writes only this file):
1. Flip `nextcloud-mcp-0.211.1` to `status: superseded`,
   `superseded_by: nextcloud-mcp-0.213.2`. Optionally re-point the three
   0.203/0.204/0.206 `superseded_by` to this id.
2. Carry the predecessor's `blocked` decision here if the operator agrees
   (frontmatter `status` comment): the blocker is unchanged.
3. Replace `nextcloud-mcp-0.211.1` (and the stale 0.203/0.204/0.206 ids) with this
   id in the `conflicts_with` of `nextcloud-9.4.3`, `kube-prometheus-stack-93.3.0`,
   `talos-linux-1.14.6`, `redis-fleet-8.10.3` and `nextcloud-12.0.2`
   (the last still names only `nextcloud-mcp-0.204.0`).
4. Re-key the home-operation blocked/go-no-go issue for nextcloud-mcp to this id.

### 1.7 Options (carried from 0.211.1, re-checked 2026-11-18)

| option | what | verdict 2026-11-18 |
|---|---|---|
| **A'. Get the fix upstream, stay on 0.184.5 until then** (RECOMMENDED) | File the issue below (operator action: public GitHub, operator's account). The maintainer ships near-daily (four tags in 48 h); the fix is one line. 2.7-B detects it functionally on the next refresh. | No feature loss, nothing to undo. **Still not filed** (search 2026-11-18). Without it the fix will not come: the four new tags are in unrelated areas. The predecessor set **2026-11-30** as the date to re-put B. |
| B. Interim: take 0.195.4 | Revive the 0.187.1 plan with this plan's 4.6 gate. | Carried: 0.195.4 reduces but does NOT clear the F-80459b23 set (numbers on the record). Partial remediation, costs a full window plus a second roll later. Fallback only. |
| C. Change the data | Recreate the two `%`-URI calendars with clean URIs. | **NOT FEASIBLE** (1.8). |
| D. Accept | Run 0.213.2, accept empty MCP reads of the two Google-import calendars. | Silent feature loss for Claude Desktop and cross-calendar MCP search (OpenClaw reads the family calendar via `gcal`, not this MCP). Operator decision only. 4.6 would need an explicit exemption. |
| E. Client-side convention | Callers pass the still-encoded href segment. | Rejected: LLM consumers pass `name`, and the server's cross-calendar paths pass `name` internally. |
| F. Patch/rebuild the image | | Out of scope (operator rule 2026-09-06: third-party images are bumped, never rebuilt). Contributing the fix upstream (A') is in scope. |

**Issue text for the operator to file** (unchanged from the predecessor; no
household names; the URI pattern is the app's, not ours):

> **Title:** Calendars created by Nextcloud's Google integration read empty: `_get_calendar_url` unquotes names that contain a literal `%`
>
> Since 0.195.5 (`unquote` added for #1449), `CalendarClient._get_calendar_url()` does `encode_dav_url(home + unquote(calendar_name) + "/")`. `list_calendars()` already returns `name = unquote(href_segment)`, so a calendar whose URI contains a literal `%` is decoded twice and the request addresses a different, non-existent collection. `nc_calendar_list_events` then returns 0 events with `isError=false`, and cross-calendar search silently skips the calendar.
>
> The docstring's premise ("Nextcloud calendar URIs never contain a literal `%`") does not hold: Nextcloud's own **integration_google** app creates every imported calendar with `$newCalUri = urlencode($newCalName)` where `$newCalName = "<name> (Google Calendar import)"` (`lib/Service/GoogleCalendarAPIService.php`, `importCalendar()`), so every Google-imported calendar has a URI like `My+Calendar+%28Google+Calendar+import%29`.
>
> Repro: import any Google calendar via integration_google; `nc_calendar_list_calendars` lists it; `nc_calendar_list_events` on that `name` returns 0 events.
>
> Suggested fix: treat the `name` returned by `list_calendars` as the decoded URI (do not `unquote` again); to keep #1449's percent-encoded input working, unquote only when the given name does not match a listed calendar name verbatim.

Still unchanged at v0.213.2: the code line, file path
(`packages/nextcloud-client/src/nextcloud_client/calendar.py:589`) and docstring the issue quotes.

### 1.8 Why the data cannot be changed (option C; carried from 0.211.1, measured read-only 2026-11-16)

The two `%`-URI calendars are machine-maintained mirrors written by Nextcloud's
`integration_google` app (`google_synchronization` job). Its `importCalendar()`
computes `urlencode("<name> (Google Calendar import)")`, looks the calendar up by
THAT URI and creates it if absent, so a renamed clean-URI copy would be orphaned
and the `%`-URI calendar re-created on the next run. The larger one held 2888
objects with writes as recent as 2026-10-31. 2.7-A can therefore never pass while
the household uses the Google import. The pass path is B (an upstream code fix).
Not re-measured today; nothing in this refresh depends on new numbers.

## 2. Pre-checks

All artefacts go to `/tmp/ncmcp/`. Run from `/Users/mu/code/cberg-home-nextgen`.

### 2.0 Target still upstream head, PR unchanged

```bash
cd /Users/mu/code/cberg-home-nextgen || exit 1
git fetch origin main renovate/ghcr.io-cbcoutinho-nextcloud-mcp-server-0.x
gh pr view 258 --json state,mergeable,files --jq '.state, .mergeable, [.files[].path]'
# expect: OPEN / MERGEABLE (UNKNOWN right after a Renovate rebase: re-run) / ["kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml"]
TOKEN=$(curl -s "https://ghcr.io/token?scope=repository:cbcoutinho/nextcloud-mcp-server:pull&service=ghcr.io" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
for t in 0.213.2 latest 0.213.3 0.214.0; do
  printf '%-8s ' "$t"
  curl -sI -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.oci.image.index.v1+json" \
    "https://ghcr.io/v2/cbcoutinho/nextcloud-mcp-server/manifests/$t" \
    | tr -d '\r' | awk 'NR==1{printf "%s ",$2} tolower($1)=="docker-content-digest:"{print $2}'; echo
done
# measured 2026-11-18: 0.213.2 200 sha256:655c2864…6d325; latest 200 SAME; 0.213.3 404; 0.214.0 404.
# A newer tag -> STOP: read its release body, run 2.7-B against it, refresh THIS file in place (keep the plan_id).
```

### 2.1 Premises (seven, fail-closed; after the 2.0 fetch)

```bash
.venv/bin/python3 runbooks/plan-premises.py nextcloud-mcp-0.213.2 --require-premises
```

### 2.2 Health floor

```bash
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
flux get helmreleases -A   | awk 'NR==1 || $5 != "True"'
kubectl get pods -n office -l app.kubernetes.io/name=nextcloud-mcp   # live 2026-11-18: 1/1 Running, 2 restarts
kubectl get helmrelease -n office nextcloud-mcp -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'   # True
kubectl get kustomization -n office nextcloud-mcp                    # Ready True
```

### 2.3 Nextcloud apps behind the tool families

```bash
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c 'php occ app:list' \
  | grep -iE '^[[:space:]]*- (calendar|contacts|deck|notes|tables|shoppinglist|mail|spreed|collectives|news|cookbook|files_versions|files_trashbin|systemtags):'
# carried 2026-09-22 (not re-run 2026-11-14): calendar, contacts, mail, spreed, files_trashbin, files_versions, systemtags.
# `tables` or `notes` present -> the expected tool count in 4.4 changes: re-derive it, do not force 121.
# `spreed` absent -> the 4.13 baseline reads isError: replace that gate, do not skip it.
```

### 2.4 CONTENTS baseline on the current server (0.184.5)

```bash
mkdir -p /tmp/ncmcp && cat > /tmp/ncmcp/call.sh <<'EOF'
#!/usr/bin/env bash
# usage: call.sh <method> '<params-json>'   -> prints the JSON-RPC response (streamable-HTTP handshake)
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

cat > /tmp/ncmcp/proto.sh <<'EOF'
#!/usr/bin/env bash
# prints "<protocolVersion> <serverInfo.version>"
set -euo pipefail
kubectl port-forward -n office svc/nextcloud-mcp 18000:8000 >/dev/null 2>&1 & PF=$!
trap 'kill $PF 2>/dev/null' EXIT; sleep 2
curl -s -X POST http://localhost:18000/mcp -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"plan-probe","version":"0"}}}' \
  | python3 -c 'import sys,json
raw=sys.stdin.read(); data=[l[5:].strip() for l in raw.splitlines() if l.startswith("data:")]
r=json.loads(data[-1] if data else raw)["result"]; print(r["protocolVersion"], r["serverInfo"].get("version"))'
EOF
chmod +x /tmp/ncmcp/proto.sh

# A) tool surface
/tmp/ncmcp/call.sh tools/list '{}' > /tmp/ncmcp/tools_list.before.json
python3 -c 'import json; d=json.load(open("/tmp/ncmcp/tools_list.before.json")); [print(t["name"]) for t in d["result"]["tools"]]' | sort > /tmp/ncmcp/tools.before
wc -l < /tmp/ncmcp/tools.before                       # measured 2026-11-14 and 2026-11-18: 96
# B) calendars, C) files root, D) addressbooks, G) Talk conversations
/tmp/ncmcp/call.sh tools/call '{"name":"nc_calendar_list_calendars","arguments":{}}' > /tmp/ncmcp/calendars.before
/tmp/ncmcp/call.sh tools/call '{"name":"nc_webdav_list_directory","arguments":{"path":""}}' > /tmp/ncmcp/files.before
/tmp/ncmcp/call.sh tools/call '{"name":"nc_contacts_list_addressbooks","arguments":{}}' > /tmp/ncmcp/addressbooks.before
/tmp/ncmcp/call.sh tools/call '{"name":"talk_list_conversations","arguments":{}}' > /tmp/ncmcp/talk.before
for f in calendars files addressbooks talk; do python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); assert not d["result"].get("isError"), d; print(sys.argv[1], "ok")' /tmp/ncmcp/$f.before; done
# E) negotiated protocol + serverInfo
/tmp/ncmcp/proto.sh | tee /tmp/ncmcp/protocol.before   # 0.184.5: "2025-06-18 1.29.0"
```

**F) Per-calendar EVENT reads (the section 1.1 regression lives here):**

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
    assert not rr.get("isError"), (c["href"], txt[:200])
    body = rr.get("structuredContent") or json.loads(txt)
    res[full_unquote(c["href"])] = {"total_found": int(body["total_found"]),
                                    "pct_uri": "%" in unquote(c["href"].rstrip("/").split("/")[-1])}
json.dump(res, open(out, "w"), indent=1)
print(f"{len(res)} calendars; pct-URI calendars={sum(v['pct_uri'] for v in res.values())}; per-calendar counts={[v['total_found'] for v in res.values()]}")
EOF
cat > /tmp/ncmcp/events_gate.py <<'EOF'
# usage: events_gate.py <events.before.json> <events.after.json>
import json, sys
b, a = (json.load(open(p)) for p in sys.argv[1:3])
assert b and set(b) == set(a), f"calendar key sets differ: missing={len(set(b)-set(a))} added={len(set(a)-set(b))}"
bad = []
for k, v in b.items():
    nb, na = v["total_found"], a[k]["total_found"]
    if nb > 0 and na == 0: bad.append(f"calendar #{sorted(b).index(k)+1} (pct_uri={v['pct_uri']}): {nb} -> 0 events (SILENT EMPTY READ)")
    elif abs(na - nb) > 2: bad.append(f"calendar #{sorted(b).index(k)+1} (pct_uri={v['pct_uri']}): {nb} -> {na} events")
assert not bad, "per-calendar event reads regressed: " + "; ".join(bad)
print("per-calendar event counts before/after:", [(v["total_found"], a[k]["total_found"]) for k, v in sorted(b.items())], "PASS")
EOF
python3 /tmp/ncmcp/events.py /tmp/ncmcp/calendars.before /tmp/ncmcp/events.before.json
# carried 2026-10-21 on 0.184.5: 4 calendars; pct-URI calendars=2; per-calendar counts=[3, 0, 200, 0]
# (calendar count and pct-URI count re-measured 2026-11-18: 4 and 2; event counts not re-measured.)
```

**H) Our gate calls use only declared arguments (0.206.0 refuses undeclared keys):**

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
# CAN FAIL: adding "bogus" to the nc_webdav_list_directory set prints {'nc_webdav_list_directory': ['bogus']} (negative control, 2026-11-08).
```

### 2.5 No firing alerts in office/ai

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 >/dev/null 2>&1 & PF=$!; sleep 2
curl -s --data-urlencode 'query=ALERTS{namespace=~"office|ai",alertstate="firing"}' http://localhost:9090/api/v1/query \
  | python3 -c "import sys,json; r=json.load(sys.stdin)['data']['result']; n=sorted(x['metric'].get('alertname') for x in r if x['metric'].get('alertname') not in ('Watchdog','InfoInhibitor')); print(n or 'NONE FIRING')" | tee /tmp/ncmcp/alerts.before
kill $PF 2>/dev/null
# CAN FAIL: this selector returned KubeJobFailed/MealiePodRestarted over a 30 d window on 2026-09-26.
```

### 2.6 Active-update marker

```bash
runbooks/update-marker.sh add nextcloud-mcp office 2 "0.184.5->0.213.2 image bump"
```

### 2.7 HARD STOP GATE: the 0.195.5 calendar-addressing regression

Proceed only if **B** prints PASS. A is a reading only (section 1.8: it cannot
pass while the Google import exists).

```bash
# A) data side (reading only): owned calendars with a literal '%' in their URI (from 2.4 F)
python3 -c 'import json; d=json.load(open("/tmp/ncmcp/events.before.json")); print("7A pct-URI calendars:", sum(v["pct_uri"] for v in d.values()))'
# measured 2026-11-18: 2

# B) code side, FUNCTIONAL: execute the TARGET tag's own _get_calendar_url (+ its dav_urls.encode_dav_url)
#    on every live calendar from 2.4 B, fed the name the target's list_calendars hands out, and check the
#    URL it builds decodes to the URI the server stores. FAIL CLOSED on fetch errors or a changed shape.
REF=v0.213.2; D=packages/nextcloud-client/src/nextcloud_client
rm -f /tmp/ncmcp/cal.$REF.py /tmp/ncmcp/dav.$REF.py
cat > /tmp/ncmcp/calurl_gate.py <<'EOF'
# usage: calurl_gate.py <calendar.py of REF> <dav_urls.py of REF> <calendars.json from 2.4-B>
import ast, json, sys
from urllib.parse import unquote, quote, urlsplit, urlunsplit
cal_src, dav_src, cals_path = sys.argv[1:4]
src = open(cal_src).read()
NAMING = 'calendar_name = unquote(calendar_url.rstrip("/").split("/")[-1])'
if NAMING not in src:
    sys.exit("7B FAIL: list_calendars naming line changed -- re-read list_calendars by hand, then re-model this gate")
fn = [n for n in ast.walk(ast.parse(src)) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "_get_calendar_url"]
if len(fn) != 1 or isinstance(fn[0], ast.AsyncFunctionDef):
    sys.exit(f"7B FAIL: _get_calendar_url found {len(fn)}x or async -- re-read by hand")
g = {"unquote": unquote, "quote": quote, "urlsplit": urlsplit, "urlunsplit": urlunsplit}
exec(open(dav_src).read(), g)
exec(ast.get_source_segment(src, fn[0]), g)
r = json.load(open(cals_path))["result"]; assert not r.get("isError"), r
sc = r.get("structuredContent") or json.loads(" ".join(c.get("text", "") for c in r["content"]))
cals = sc["calendars"]; assert cals, "no calendars"
class Self: _calendar_home_url = "https://nc.invalid/remote.php/dav/calendars/u/"
bad, ok = [], 0
for i, c in enumerate(cals, 1):
    seg = c["href"].rstrip("/").split("/")[-1]
    want = unquote(seg)            # the URI the server stores (href decoded once)
    name = unquote(seg)            # what the target's list_calendars returns (the NAMING line)
    try:
        url = g["_get_calendar_url"](Self(), name)
    except Exception as e:
        sys.exit(f"7B FAIL: _get_calendar_url raised {type(e).__name__} -- depends on more than the name, re-read by hand")
    got = unquote(urlsplit(url).path.rstrip("/").split("/")[-1])
    if got == want: ok += 1
    else: bad.append(f"calendar #{i} (pct_uri={'%' in want}): built URL resolves to a different URI")
print(f"7B {'FAIL' if bad else 'PASS'}: {ok}/{len(cals)} calendars addressed correctly" + ("; " + "; ".join(bad) if bad else ""))
sys.exit(1 if bad else 0)
EOF
if ! gh api "repos/cbcoutinho/nextcloud-mcp-server/contents/$D/calendar.py?ref=$REF" -H 'Accept: application/vnd.github.raw' > /tmp/ncmcp/cal.$REF.py \
   || ! gh api "repos/cbcoutinho/nextcloud-mcp-server/contents/$D/dav_urls.py?ref=$REF" -H 'Accept: application/vnd.github.raw' > /tmp/ncmcp/dav.$REF.py; then
  echo "7B FAIL ($REF): fetch failed -- gate NOT evaluated (file moved again? re-locate it by hand)"
else
  python3 -I /tmp/ncmcp/calurl_gate.py /tmp/ncmcp/cal.$REF.py /tmp/ncmcp/dav.$REF.py /tmp/ncmcp/calendars.before
fi
```

Measured 2026-11-18 (dry run in a scratch dir against a live
`calendars.before` taken through 0.184.5 with the 2.4 `call.sh`):

- `v0.213.2`: `7B FAIL: 2/4 calendars addressed correctly; calendar #3 (pct_uri=True): built URL resolves to a different URI; calendar #4 (pct_uri=True): built URL resolves to a different URI`, exit 1. Identical for `v0.212.0` and `v0.211.1` (2026-11-16).
- **Positive control:** the same v0.213.2 file with only line 589 changed
  (`{unquote(calendar_name)}` -> `{calendar_name}`, i.e. the fix requested in
  1.7) prints `7B PASS: 4/4 calendars addressed correctly`, exit 0. So the gate
  passes on a real fix and does not depend on the fix taking that exact shape;
  a fix that makes the function async or dependent on server state fails
  closed with "re-read by hand", and section 4.6 then remains the binding check.
- The old grep (`unquote(calendar_name)` count) is retired: a correct fix that
  keeps an `unquote` behind a guard would have read FAIL forever.

**B FAIL -> STOP.** Do not merge or commit. Run
`runbooks/update-marker.sh clear nextcloud-mcp` and return to the operator with
section 1.7. This is the expected outcome until upstream ships the fix.
When a newer tag exists, set `REF` to it (2.0 tells you) and refresh this file.

### 2.8 OpenClaw consumer path unchanged

```bash
kubectl exec -n ai deploy/openclaw -c app -- sh -c 'ls /home/node/.openclaw/lib/node_modules/mcporter/dist/cli.js; node /home/node/.openclaw/lib/node_modules/mcporter/dist/cli.js --version; printenv NEXTCLOUD_MCP_URL'
# expect the cli.js path, a mcporter version (0.17.0 on 2026-11-14) and the in-cluster nextcloud-mcp service URL, port 8000, path /mcp.
# Anything else -> the 4.11 config template is wrong: STOP and re-point it, do not skip the consumer gate.
```

## 3. Steps

1. Sections 2.0-2.8 green, i.e. 2.7-B printed PASS. Otherwise stop here.
2. Merge the Renovate PR **only if its title says 0.213.2** (it did on
   2026-11-18; if Renovate has moved it, STOP per 2.0, or use the fallback below):

```bash
cd /Users/mu/code/cberg-home-nextgen || exit 1
gh pr view 258 --json state,title,files --jq '.state, .title, [.files[].path]'
# expect OPEN / "... ( 0.184.5 → 0.213.2 )" / ["kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml"]
gh pr merge 258 --squash --delete-branch
git fetch origin main && git merge --ff-only origin/main
grep -n '^[[:space:]]*tag: ' kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml   # expect 34:              tag: 0.213.2
git log -1 --format='%H %s' -- kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml | tee /tmp/ncmcp/bump.sha
```

   **Fallback if #258 does not say 0.213.2 or was closed** (never merge a PR
   whose title names another tag). Dry-tested 2026-11-18 on a scratch copy with
   macOS BSD sed; resulting diff: `34c34` / `<               tag: 0.184.5` /
   `>               tag: 0.213.2`, one hunk.

```bash
sed -i '' 's/^\([[:space:]]*tag: \)0\.184\.5$/\10.213.2/' kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml
git diff --stat -- kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml    # expect 1 file, 1+/1-; 0 files = no-op: STOP
printf '%s\n' 'feat(nextcloud-mcp): image 0.184.5 -> 0.213.2' '' \
  'Plan: runbooks/maintenance/plans/nextcloud-mcp-0.213.2.md (section 2.7-B gate passed).' '' \
  'security_ref: F-80459b23' 'finding_refs: F-9af9baf7, F-80459b23' > /tmp/ncmcp/msg-bump.txt
git commit --only kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml -F /tmp/ncmcp/msg-bump.txt
git show --stat HEAD && git log -1 --format=%s   # ONE file; the subject must be YOURS, else amend before push
git push origin main && git rev-parse HEAD > /tmp/ncmcp/bump.sha
```

3. Reconcile (the SOP permits forcing inside a window) and watch:

```bash
flux reconcile kustomization nextcloud-mcp -n office --with-source
flux reconcile hr -n office nextcloud-mcp
kubectl rollout status deploy/nextcloud-mcp -n office --timeout=180s
kubectl get pods -n office -l app.kubernetes.io/name=nextcloud-mcp
```

   Single replica, no volumes (premise): no RWO/Recreate concern, no migration Job.

## 4. Verification

Instruments (for `plan-premises.py --controls`):

- CONTROL: metric `kube_deployment_status_replicas_available`: `{namespace="office",deployment="nextcloud-mcp"}` must read `1` after the roll.
- CONTROL: metric `kube_pod_container_status_restarts_total`: `{namespace="office",container="main",pod=~"nextcloud-mcp-.*"}` must read `0` on the new pod 5 min after Ready.
- CONTROL: metric `container_memory_working_set_bytes`: same selector, must stay below `800Mi` (limit 1Gi).
- CONTROL: metric `ALERTS`: `{namespace=~"office|ai",alertstate="firing"}` must be EMPTY after settle (2.5 exclusions apply).

### 4.1 Flux Ready

```bash
kubectl get helmrelease -n office nextcloud-mcp -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} chart={.status.history[0].chartVersion}{"\n"}'
# expect: True chart=5.3.0
```

### 4.2 New bytes running, clean start log

```bash
kubectl get pod -n office -l app.kubernetes.io/name=nextcloud-mcp -o jsonpath='{range .items[*]}{.metadata.name} restarts={.status.containerStatuses[0].restartCount} {.status.containerStatuses[0].imageID}{"\n"}{end}'
# expect ONE pod, restarts=0, imageID ending sha256:655c2864b48fd3f0696480ebe19a165ff114a582b30b9cec1d6ab4923586d325
#   f6d88397… = the OLD build still serving (rollout status green-lit the old generation): wait and re-check, do not pass.
kubectl logs -n office deploy/nextcloud-mcp > /tmp/ncmcp/log.after-start
cat > /tmp/ncmcp/logscan.py <<'EOF'
import re, sys
L=open(sys.argv[1]).read().splitlines()
err=[l for l in L if re.search(r'(^|\s)(ERROR|CRITICAL)\s', l)]
tb=[i for i,l in enumerate(L) if l.startswith('Traceback')]
vc=[i for i in tb if i>0 and 'Could not parse vCard' in L[i-1]]
old=[l for l in L if 'nextcloud_mcp_server.client.' in l]
print(f"lines={len(L)} ERROR/CRITICAL={len(err)} Traceback={len(tb)} vCard-attributed={len(vc)} old-logger-lines={len(old)}")
assert L, "EMPTY log -- wrong pod/container; do not pass"
assert not err and len(tb)==len(vc), "unattributed ERROR/CRITICAL/Traceback -- read the log (ImportError/ModuleNotFoundError = 0.211.0 packaging)"
assert not old, "logger nextcloud_mcp_server.client.* still present -- this is a pre-0.211.0 build"
EOF
python3 /tmp/ncmcp/logscan.py /tmp/ncmcp/log.after-start
# vCard Tracebacks are known data (FN-less contacts). Re-run AFTER 4.6 and 4.8 against /tmp/ncmcp/log.after-events.
# CAN FAIL: the live 0.184.5 log carries 2 old-logger lines in its last 3000 (measured 2026-11-14), so the last assert
#   fires on the old build; an injected Traceback/ERROR line fires the second (reviewer control, 0.199.1 review).
```

### 4.3 CONTENTS ASSERTION (lifespan once per container; SAR plugin and multi-user middleware absent)

```bash
kubectl logs -n office deploy/nextcloud-mcp > /tmp/ncmcp/log.now
grep -c 'Starting MCP session in single-user BasicAuth mode' /tmp/ncmcp/log.now
# expect 1 right after start and STILL 1 after 4.4's sessions (app.py:1065 at v0.213.2). On 0.184.5 it climbs per session.
#   0 = INFO hidden -> the absence checks below have no positive control; 4.4 becomes the binding check.
grep -ciE 'plugin sar: (not available, skipping|registering tools)' /tmp/ncmcp/log.now    # expect >=1 (positive control, plugins.py:126/130)
grep -ciE 'plugin sar: registering tools' /tmp/ncmcp/log.now                              # expect 0; >=1 -> STOP, section 5
grep -ci 'BasicAuthMiddleware enabled' /tmp/ncmcp/log.now                                 # expect 0 (app.py:3411 at v0.213.2); >=1 -> STOP, section 5
```

### 4.4 CONTENTS ASSERTION (surface = baseline + exactly 25 names; version handshake)

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
grep -ci 'sar' /tmp/ncmcp/tools.after                                                     # expect 0
grep -c -e '^nc_notes_' -e '^nc_tables_' -e '^nc_semantic_' /tmp/ncmcp/tools.after        # expect 0 (apps absent, vector sync off)
wc -l < /tmp/ncmcp/tools.after                                                            # expect 121
/tmp/ncmcp/proto.sh | tee /tmp/ncmcp/protocol.after
# expect "2025-06-18 0.213.2". "1.29.0" = old build still serving; an empty version = a 0.185..0.201.0 build (wrong image).
```

The 25 names are 21 measured live on 0.195.4 (2026-09-26) plus four from
0.203.0; 0.203.1..0.213.2 add only the two app-gated Tables tools (no file under `server/` changed in 0.212.0..0.213.2). Derived from
source, not observed. A MISSING name is a FAIL; an unexpected extra name is a
re-read (was Tables or Notes installed since 2.3?).

### 4.5 CONTENTS ASSERTION (calendar LIST and files root: same set)

This gate cannot see the 1.1 regression; 4.6 can.

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
    raise AssertionError("unquote did not converge")
def cals(p):
    r = result(p)
    sc = r.get("structuredContent") or json.loads(" ".join(c.get("text", "") for c in r.get("content", [])))
    items = sc.get("calendars")
    assert isinstance(items, list) and items, f"{p}: no non-empty `calendars` list"
    out = {}
    for c in items:
        key = full_unquote(c["href"])
        assert key not in out, f"{p}: two calendars collapse to one key"
        out[key] = (c["display_name"], full_unquote(c["name"]))
    return out
b, a = cals(CB), cals(CA)
missing, added = b.keys() - a.keys(), a.keys() - b.keys()
changed = [k for k in b.keys() & a.keys() if b[k] != a[k]]
assert not (missing or added or changed), f"calendar set differs: missing={len(missing)} added={len(added)} changed={len(changed)}"
def names(p):
    r = result(p)
    return {f["name"] for f in (r.get("structuredContent") or json.loads(r["content"][0]["text"]))["files"]}
fb, fa = names(FB), names(FA)
assert fb and fa == fb, f"root listing differs: missing={len(fb-fa)} extra={len(fa-fb)}"
print(f"calendars before/after: {len(b)} {len(a)} | root entries before/after: {len(fb)} {len(fa)} PASS")
EOF
# FAILS on: isError, an empty calendar list, a changed calendar set, an empty or changed root listing.
```

### 4.6 CONTENTS ASSERTION (per-calendar EVENT reads: the 1.1 regression)

```bash
python3 /tmp/ncmcp/events.py /tmp/ncmcp/calendars.after /tmp/ncmcp/events.after.json
python3 /tmp/ncmcp/events_gate.py /tmp/ncmcp/events.before.json /tmp/ncmcp/events.after.json
# PASS: every calendar non-empty before is non-empty after, |delta| <= 2.
# FAIL prints: "calendar #N (pct_uri=True): 200 -> 0 events (SILENT EMPTY READ)" -> section 5.
kubectl logs -n office deploy/nextcloud-mcp > /tmp/ncmcp/log.after-events && python3 /tmp/ncmcp/logscan.py /tmp/ncmcp/log.after-events
```

Demonstrated 2026-10-21 on 0.184.5: `events.py … --emulate-double-decode` read
`[3, 0, 0, 0]` against a real `[3, 0, 200, 0]` and the gate exited 1 with the
SILENT EMPTY READ line. Limit: the second `%`-URI calendar holds 0 events in
range, so counts cannot see a regression on it; 2.7-B covers it (it addresses every
calendar, including that one, through the target's own code).

### 4.7 CONTENTS ASSERTION (0.192.0 visible on bulk operations)

```bash
python3 - <<'EOF'
import json
def props(p, name):
    t=[t for t in json.load(open(p))["result"]["tools"] if t["name"]==name]; assert t, f"{name} missing from {p}"
    return t[0].get("inputSchema",{}).get("properties",{})
b=props("/tmp/ncmcp/tools_list.before.json","nc_calendar_bulk_operations"); a=props("/tmp/ncmcp/tools_list.after.json","nc_calendar_bulk_operations")
assert "apply_to_series" not in b, "baseline already had it -- was 2.4 A taken on 0.184.5?"
assert "apply_to_series" in a and a["apply_to_series"].get("default") in (False, None), a.get("apply_to_series")
assert set(b) <= set(a), f"LOST properties: {set(b)-set(a)}"
print("bulk_operations props before/after:", len(b), len(a), "PASS")
EOF
```

### 4.8 CONTENTS ASSERTION (contacts read path: paging, photo opt-in)

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
assert "has_photo" in txt, "has_photo ABSENT -- 0.188.1 mapper not running (or empty addressbook: check the raw file)"
inline=re.findall(r'"photo"\s*:\s*"(?:data:image|[A-Za-z0-9+/]{200,})', txt)
assert not inline, f"{len(inline)} inline photo payload(s) although include_photos defaults to False"
print("contacts: has_photo present, inline photos:", len(inline), "PASS")
EOF
# CAN FAIL: this regex matched 91 inline payloads on 0.184.5 (reviewer control).
```

### 4.9 Memory and restarts, 5 min after Ready

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
curl -s --data-urlencode 'query=kube_deployment_status_replicas_available{namespace="office",deployment="nextcloud-mcp"}' http://localhost:9090/api/v1/query \
  | python3 -c "import sys,json; r=json.load(sys.stdin)['data']['result']; assert r, 'EMPTY'; assert r[0]['value'][1]=='1', r; print('available=1')"
kill $PF 2>/dev/null
# The OLD pod's series (2 restarts) can linger for the staleness interval: an assertion on 'restarts > 0' naming the old pod
#   name is a retry after 5 min, not a failure.
```

### 4.10 No new firing alerts

Re-run 2.5 into `/tmp/ncmcp/alerts.after`; `diff /tmp/ncmcp/alerts.before /tmp/ncmcp/alerts.after`
must be empty. A new alertname is a FAIL.

### 4.11 The real consumers

OpenClaw (`ai`, mcporter). mcporter exits 0 on `isError`, so the gate is the body:

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

Claude Desktop (attended): entry `nextcloud` runs `uvx mcp-proxy --transport
streamablehttp https://nextcloud-mcp.<DOMAIN>/mcp`. Fully quit and relaunch
Desktop after the roll, list the root folder, **ask for this week's events from
the busiest calendar** (the human form of 4.6), and confirm the tool count grew
by 25. Idle re-check (0.202.1): leave Desktop idle 35 min, list the root folder
again. A session-not-found error until relaunch is the documented upstream
behaviour: record it on F-9af9baf7 as a client issue, not a rollback trigger. A
Desktop-only failure with 4.4 and the OpenClaw gate green is a client-pin issue.

### 4.12 CONTENTS ASSERTION (0.199.0 extras and the 0.211.0 client wheel are in the image)

```bash
kubectl exec -n office deploy/nextcloud-mcp -c main -- /opt/venv/bin/python -c '
import importlib.util as u, importlib.metadata as md
m=["pymupdf","pypdfium2","docx","openpyxl","qdrant_client","nextcloud_client","nextcloud_client.calendar"]
r={x: u.find_spec(x) is not None for x in m}; v=(md.version("nextcloud-client"), md.version("nextcloud-mcp-server"))
print(r, v); raise SystemExit(0 if all(r.values()) and v==("0.213.2","0.213.2") else 1)' \
  && echo "4.12 PASS" || echo "4.12 FAIL"
# FAIL shapes: a False for an extras module (PDF/Office reads degrade to raw bytes); PackageNotFoundError for nextcloud-client
#   or a version pair other than 0.213.2/0.213.2 (wrong or pre-0.211 image: there the distribution does not exist) -> section 5.
```

### 4.13 CONTENTS ASSERTION (OCS path: Talk still answers)

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
# FAILS on: isError / OCS 997 (header lost), success != True, an empty or changed token set.
```

### 4.14 CONTENTS ASSERTION (0.205.0 `truncated` + limit-after-filters)

Uses a non-`%` calendar with at least 2 events in range.

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
print(f"4.14 PASS: limit=1 -> 1 event truncated=True; limit={n+50} -> {n} events truncated=False")
PYEOF
# CAN FAIL: a pre-0.205.0 build has no `truncated` key -> `None is True` fails the first assert.
```

### 4.15 CONTENTS ASSERTION (0.206.0: unknown arguments refused, schemas strict)

```bash
python3 - <<'PYEOF'
import json, subprocess
td = json.load(open("/tmp/ncmcp/tools_list.after.json"))["result"]["tools"]
lax = [t["name"] for t in td if t.get("inputSchema", {}).get("additionalProperties") is not False]
assert td and not lax, f"{len(lax)} of {len(td)} tools do not advertise additionalProperties:false (old build?): {lax[:5]}"
props = {t["name"]: set(t.get("inputSchema", {}).get("properties", {})) for t in td}
used = {"nc_calendar_list_events": {"calendar_name","start_date","end_date","limit"}, "nc_webdav_list_directory": {"path"},
        "nc_contacts_list_contacts": {"addressbook","limit"}}
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
# CAN FAIL: on 0.205.x or earlier the probe call SUCCEEDS and the schemas lack additionalProperties.
# The probe is a READ (list root) with a junk key; the refusal happens before any Nextcloud request (errors.py:272).
```

Human gate: if 4.15 is the only red item, the roll is healthy and the failure
is consumer-side. Read the consumer's actual call before choosing rollback; the
error text names the valid arguments, so an LLM client can self-correct.

### 4.16 CONTENTS ASSERTION (0.207.3: mail recipient arguments advertised as arrays)

Schema-only; no mail is sent.

```bash
python3 - <<'PYEOF'
import json
def prop(p, tool, arg):
    t=[t for t in json.load(open(p))["result"]["tools"] if t["name"]==tool]; assert t, f"{tool} missing from {p}"
    return t[0]["inputSchema"]["properties"][arg]
b = prop("/tmp/ncmcp/tools_list.before.json", "nc_mail_send_message", "to")
assert b.get("type") == "string", f"baseline `to` is not a string -- was 2.4 A taken on 0.184.5? {b}"
for tool in ("nc_mail_send_message", "nc_mail_save_draft"):
    a = prop("/tmp/ncmcp/tools_list.after.json", tool, "to")
    assert a.get("type") == "array" and a.get("items"), f"{tool}.to is not an array of recipients: {json.dumps(a)[:200]}"
print("4.16 PASS: `to` string -> array on send_message; array on save_draft")
PYEOF
# CAN FAIL: on 0.184.5 `to` is {"type":"string"} (measured 2026-11-14) -> the array assert fires on an old build.
# NOT covered: that a consumer still passing a JSON STRING is accepted (upstream source comment says the SDK decodes it;
#   untested because the only test is sending mail). If an agent reports a recipient validation error after the roll,
#   that is this change: the fix is client-side (pass an array), not a rollback.
```

### 4.17 Close out

`runbooks/update-marker.sh clear nextcloud-mcp`. Set this plan `executed`; the
predecessor `nextcloud-mcp-0.211.1` must already read `superseded`. F-9af9baf7 and
F-80459b23 are script-owned and should close on the next sweep: verify, do not
assume. Record the post-roll scan outcome on F-80459b23.

## 5. Rollback

Stateless (premises: no volumes, no DB keys), so rollback is an inverse image
tag edit, not `git revert` (which refuses in this shared worktree whenever
another session has something staged). Dry-tested 2026-11-14 on a scratch copy
with macOS BSD sed: forward then inverse restores the original byte-identical
(`cmp` clean; re-run 2026-11-18 for 0.213.2). The inverse sed matches `0\.213\.2$` only; the inverse seds in
the superseded plans match tags that were never deployed and would be silent
no-ops.

```bash
cd /Users/mu/code/cberg-home-nextgen || exit 1
git fetch origin main && git merge --ff-only origin/main
sed -i '' 's/^\([[:space:]]*tag: \)0\.213\.2$/\10.184.5/' kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml
git diff --stat -- kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml    # expect 1 file 1+/1-; 0 files = no-op: STOP
mkdir -p /tmp/ncmcp && printf '%s\n' 'revert(nextcloud-mcp): image 0.213.2 -> 0.184.5' '' \
  'Rollback per runbooks/maintenance/plans/nextcloud-mcp-0.213.2.md section 5' \
  '(stateless bridge, image tag only).' > /tmp/ncmcp/msg-revert.txt
git commit --only kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml -F /tmp/ncmcp/msg-revert.txt
git show --stat HEAD && git log -1 --format=%s    # ONE file; subject = revert(nextcloud-mcp): image 0.213.2 -> 0.184.5
git push origin main
flux reconcile kustomization nextcloud-mcp -n office --with-source
flux reconcile hr -n office nextcloud-mcp
kubectl rollout status deploy/nextcloud-mcp -n office --timeout=180s
kubectl get pod -n office -l app.kubernetes.io/name=nextcloud-mcp -o jsonpath='{range .items[*]}{.metadata.name} {.status.containerStatuses[0].imageID}{"\n"}{end}'
# expect imageID ending sha256:f6d8839722587f2cd37ec5218a18479f9e313be9904ad4f6bbb36f98bc827065
```

Renovate re-opens or refreshes PR #258 afterwards; the deny rule keeps it held.

Confirm the cluster is back:
- 4.4 re-run: `tools.after` == `tools.before` (96, `comm` empty both ways), protocol `2025-06-18 1.29.0`.
- 4.6 re-run into `events.revert.json`, gated against `events.before.json`: the busiest calendar is back at its count.
- 4.13 and the OpenClaw half of 4.11 re-run; relaunch Claude Desktop.
- Not reverted by this: anything a consumer wrote through the new WRITE tools
  while the target ran (mail drafts, edited text files, contact fields). Those
  are ordinary Nextcloud objects; list them from the consumer's session if needed.

## 6. Interference notes

- **Predecessor plan `nextcloud-mcp-0.211.1`** drives the same PR #258 and
  the same deployment. Never vet or schedule both: it is in `conflicts_with`
  and `supersedes`, and must be flipped to `superseded` (1.6) before this one is vetted.
- **Consumers, not shared infra.** OpenClaw (`ai`, mcporter entry `nextcloud`)
  and Claude Desktop lose or change tools silently if this goes wrong. The 1.1
  regression is a silent failure ("no events", not an error), which is why 4.6
  exists and the Desktop check asks for events.
- **Nextcloud server work** (`nextcloud-12.0.2`, `nextcloud-9.4.3`,
  `redis-fleet-8.10.3`, `bitnamilegacy-exit-nextcloud-db`): every contents gate
  is a live call into that server, so never share a slot; all four are in
  `conflicts_with`. After any of them runs, re-take the 2.4 baselines.
- **Prometheus**: 2.5 / 4.9 / 4.10 read it; `kube-prometheus-stack-93.3.0`
  (draft, exclusive) is in `conflicts_with`.
- **HelmRelease-wide changes**: `helm-drift-detection` (every HR) and
  `flux-oci-chart-sources` (bjw-s app-template `sourceRef`) both re-render
  `helmrelease/nextcloud-mcp`; in `conflicts_with`.
- **Gateway / DNS / API server**: `envoy-gateway-1.10.0` rolls the data plane
  Claude Desktop uses; `coredns-1.50.5` rolls the resolver both consumers and
  the bridge use; `etcd-timeouts-5000-500` blinds kubectl. None may share the
  slot, so a 4.11 failure is always attributable to this roll.
- **Node / storage work**: `talos-linux-1.14.6` and `longhorn-1.13.0` are
  exclusive already; listed so the dependency is explicit. `talos-power-tuning-ab`
  and `flux-reconciler-impersonation` are exclusive and not listed.
- **Same namespace, disjoint resources**: `postgres-digest-refresh-2026-11`
  (affine-pg, sure-pg) and `postgres-fleet-18.7-bookworm` (mealie-pg) restart
  other workloads in `office`; no conflict, but they make the 2.5 / 4.10 alert
  diff noisy if adjacent in the same slot. Prefer not to co-schedule.
- **Attended only.** Deny rule plus `capability_change: true`. Never `nightly`.
  Nothing here touches Longhorn, cert-manager, cilium, coredns or the Gateways.
- **New WRITE tools**: once running, consumers can save Mail drafts, edit
  plain-text files, restore versions/trash and tag files in the service
  account's Nextcloud. The operator GO must name this.
- **Session idle timeout (0.202.1)**: a client holding a session idle for more
  than 30 min is reaped. OpenClaw opens per-call sessions; Desktop is checked in 4.11.

## 7. What I could not verify (2026-11-18)

- **Per-tag remediation of F-80459b23 by 0.213.2.** Not scanned by this
  planner. The 0.212.0 scan (predecessor, 2026-11-16) does not carry: the 0.213.1
  Dockerfile changed. The window agent or the next sweep should scan 0.213.2 and
  record the result on the finding, not here.
- **The target image was not run.** Tool count 121, `serverInfo.version`
  `0.213.2`, strict schemas, log lines and the client wheel version are derived
  from the predecessor's v0.211.1 source read plus the v0.211.1..v0.212.0 and
  v0.212.0..v0.213.2 diffs, not observed on a pod.
- **The `base.py` metrics-hook refactor (0.213.1)** was read in the diff only.
  Error enrichment and re-raise look unchanged. Gates 4.5-4.8 and 4.13 are the
  runtime check on both request paths.
- **Whether upstream will accept the fix** or choose another shape; 2.7-B passes
  on any synchronous fix that addresses our hrefs correctly (positive control
  re-run today).
- **The 0.207.3 backward-compatibility claim** (a JSON-string recipient argument
  still accepted): upstream source comment only.
- **Which tool and argument shapes the LLM consumers actually send.** No repo
  file pins them.
- **Per-calendar event counts** `[3, 0, 200, 0]` and the Talk baseline are
  carried from 2026-10-21. Re-measured today: calendar count (4), `%`-URI count
  (2), tool count (96). 2.4 re-takes all of them on the day.
- **`php occ app:list`** (2.3) is carried from 2026-09-22. Tables/Notes absence
  is supported today only indirectly (0 such tools among the 96 live).
- **Write paths** (mail send/draft, file edit, contacts N/ADR, bulk calendar
  operations, Talk thread writes, tag/trash/version writes): not exercised.
- **Minors 0.185-0.211.1**: carried from the earlier plans' per-tag reads. I
  read the four new release bodies (0.212.0, 0.213.0, 0.213.1, 0.213.2) and the
  `compare v0.212.0...v0.213.2` patches for `Dockerfile`, `app.py`, `cli.py`,
  `config.py`, `middleware.py`, `registry.py`, `base.py` and both `pyproject.toml`.
  I did not read the `providers/gateway*.py`, `ner.py`, `rerank.py`, `metrics.py`
  or `tracing.py` patches (all behind the embedding gateway / vector / OTel paths
  that are off here).

## Repo corrections noted by this planner

- (carried) Every nextcloud-mcp plan older than 0.211.1 has a 2.7-B command that
  reads `nextcloud_mcp_server/client/calendar.py`, a path that no longer exists
  from v0.211.0 on. It fails closed, but anyone refreshing one of those files in
  place would be measuring nothing.
- (carried) `docs/sops/ai-integration.md` /
  `kubernetes/apps/ai/openclaw/app/mcporter-config.yaml` describe the `nextcloud`
  MCP entry as read-oriented. After this roll the same server exposes WRITE tools
  and nothing in the registration restricts them. This needs an operator
  decision, not a window action.
- `nextcloud-12.0.2`'s `conflicts_with` still names only `nextcloud-mcp-0.204.0`,
  a superseded id, so the interference check does not see the live nextcloud-mcp
  plan from that side (1.6 item 3).
- `supersedes:` is not a documented frontmatter field in
  `runbooks/maintenance/plans/README.md`. It is used here because the dispatcher
  asked for it. If tools should act on it, document it there.
