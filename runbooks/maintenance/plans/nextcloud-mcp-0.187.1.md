---
plan_id: nextcloud-mcp-0.187.1        # KEPT on retarget (2026-09-22). The id is an identifier, not an
                                      # assertion: nextcloud-34.0.4 and nextcloud-redis-hardening name it in
                                      # conflicts_with, the home-operation go/no-go issue is keyed on it, and
                                      # the finding_refs ownership claim joins on it. README "When the held
                                      # target MOVES — refresh the plan, do not replace it". `target:` is
                                      # the authoritative field.
component: nextcloud-mcp
pr: null                              # no Renovate PR (`gh pr list --state all --search
                                      # nextcloud-mcp` is empty); held by the `*nextcloud-mcp*`
                                      # `max: patch` deny rule in runbooks/auto-update-policy.yaml
                                      # via coverage.py's PLAN lane, not by a live PR
kind: image
current: "0.184.5"
target: "0.195.4"                     # RETARGETED 2026-09-25 (was 0.195.0; PATCH-only, same 0.195 line).
                                      # Verified head: GHCR 0.195.4 index digest sha256:24417dcb… is
                                      # IDENTICAL to `latest`; 0.195.5 and 0.196.0 404; GitHub release
                                      # v0.195.4 is Latest, not a pre-release (2026-09-25T12:56Z). The
                                      # sweep brief said "0.195.1"; 0.195.2/.3/.4 shipped after it, so
                                      # 0.195.1 would have been stale on commit. History: 0.187.1 ->
                                      # 0.195.0 (2026-09-22) -> 0.195.4 (2026-09-25). §1.1
update_type: minor                    # semver label only — at major version 0 the MINOR digit
                                      # is the breaking axis; this hop crosses ELEVEN minor lines
                                      # (0.185 .. 0.195), twenty tags, TWO of them BREAKING-tagged
                                      # plus the 0.185.0 SDK-major floor. Every tag read: §1.2.
risk: medium
est_duration_min: 35                  # 30 -> 35 (2026-09-22): two more CONTENTS gates (bulk-ops
                                      # schema, contacts paging) and a memory-settle gate for the
                                      # python 3.14 base + four new native office readers (§1.6).
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
                                      # server version (§1.2). nextcloud-34.0.4 DOES touch the
                                      # server — see conflicts_with, not depends_on: either
                                      # order works, they must not share a slot.
conflicts_with:
  - nextcloud-34.0.4                  # vetted, sun-attended:2026-10-04 (the day AFTER this
                                      # plan's slot — satisfied). It restarts deployment/nextcloud
                                      # and moves it 34.0.3 -> 34.0.4; §4.5 here talks to that
                                      # server, so a restart mid-verification makes a calendar-
                                      # list failure unattributable, and the namespace-wide
                                      # silence that plan sets would mask this rollout's noise.
                                      # Reciprocal: that plan lists this id. Re-take the §2.4
                                      # baselines the SAME DAY as execution, after any server move.
  - nextcloud-redis-hardening         # ADDED 2026-09-22 (RECIPROCITY — that draft already lists
                                      # this id). It quiesces the Nextcloud server and restarts
                                      # its Redis (sessions/file-locks); every §4 contents gate
                                      # here is a live call INTO that server. Different slots.
  - kube-prometheus-stack-91.4.1      # ADDED 2026-09-22 (authoring rule 4): §2.5/§4.9 read the
                                      # window's instrument (Prometheus `ALERTS`, kube-state
                                      # metrics); that plan restarts Prometheus + operator, and
                                      # an unscraped gate reads EMPTY on both sides. ONE-SIDED as
                                      # of this write — the reciprocal entry on that (draft,
                                      # unwindowed) plan is owed by whoever edits it next; this
                                      # planner writes only this file.
security_ref: F-80459b23              # security-driven bump: a newer upstream tag exists and
                                      # taking it is the only remediation this household performs
                                      # for a third-party image. Detail stays on the record.
capability_change: true               # HONEST FACT, reviewed with the plan (§1.3): the agent's
                                      # reach grows by 21 tools (9 nc_webdav_* trash/versions/tags,
                                      # 12 nc_shopping_list_*), two existing tools change semantics
                                      # (0.192.0 bulk-ops recurring-series default; 0.188.1 contacts
                                      # photo opt-in + paging) and one stub becomes real (0.187.0
                                      # nc_calendar_find_availability). Routes to an attended
                                      # window — which the deny rule mandates anyway.
rollback_class: git-revert            # stateless bridge: no PVC, no volumes, no DATABASE_URL /
                                      # TOKEN_STORAGE_DB — its alembic migrations run against an
                                      # EPHEMERAL SQLite in /tmp recreated on every container start
                                      # (premises 4+5 prove it; log line re-read 2026-09-22).
                                      # `values.image.tag` is the diff.
finding_refs: [F-9af9baf7, F-80459b23, F-bb713800]   # F-bb713800 ADDED 2026-09-22: the drift
                                      # finding this refresh answers (plan-or-page joins on this field).
status: awaiting-go   # RESET 2026-09-25: the operator GO recorded for 0.195.0 does NOT extend to 0.195.4 (an
                      # approval is scoped to what was reviewed, §1.8). A FRESH GO for 0.195.4 is required
                      # before the 2026-10-03 run. Reviewed 2026-09-23 at 0.195.0 (needs-fix -> fixed).
                      # FRESH GO for 0.195.4 given by the operator 2026-09-25 (home-operation decide
                      # approve, exec_state=pending). Status stays awaiting-go per the pre-window convention.
window: "now:2026-09-26"   # ON-DEMAND NOW run 2026-09-26 (run-now.py stamp; was 'sat-attended:2026-10-03')
                                      # reboot, git-revert). Slot re-checked 2026-09-22: also holds
                                      # external-dns-unowned-cnames (draft, 40 min, medium) — no shared resource
                                      # (§6); 40+35 = 75 of 90 min, risk 2+2 = 4 of 6. Attended by the deny-rule
                                      # reason ("every minor hop needs its release notes read by a human");
                                      # never the nightly/unattended window.
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
      stale read — the calendar DAV encoding change in 0.185.5 and the
      trash/versions/tags WebDAV calls added in 0.188.0/0.189.0 talk to this
      server directly. Drift-tolerant on the PATCH digit (review 2026-09-15):
      nextcloud-34.0.4 is vetted for sun-attended:2026-10-04, and a hard pin on
      34.0.3 would fail this plan closed as a phantom the moment that plan
      executes first. A server MAJOR/MINOR move still fails it — that is the
      re-vet trigger. Whatever patch is live, re-take the §2.4 baselines the
      same day.
    run: kubectl get deploy -n office nextcloud -o jsonpath='{.spec.template.spec.containers[?(@.name=="nextcloud")].image}'
    expect_matches: 'docker\.io/nextcloud:34\.0\.[0-9]+$'
  - id: deployment-mode-still-single-user-basic
    why: >-
      The 0.185.0 BREAKING (mcp>=2.1 SDK floor, elicitation degrades to
      message_only) and every 0.190.0 auth change (CIMD client_ids, RFC 9207
      iss, grant-ownership checks) fire only on the multi-user Login Flow /
      OAuth path. This deployment runs MCP_DEPLOYMENT_MODE=single_user_basic —
      static credentials, no Login Flow, no elicitation, CIMD_ALLOWED_HOSTS
      unset (default: disabled) — so those changes are inert HERE. If this
      value ever changes to a multi-user mode the risk assessment in §1.2 is
      void and the plan must be re-vetted, not run.
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
      The same four-key fact also proves no COLLABORA_URL / DOCLING_API_URL /
      QDRANT_URL, i.e. every optional processor and vector-sync feature added
      in 0.191.0–0.195.4 stays off (§1.2, §1.2a).
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
  - docs/sops/verification-contents-not-shape.md
generated: "2026-09-25"
---

## 1. Summary & why held

`kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml:34` pins
`ghcr.io/cbcoutinho/nextcloud-mcp-server` at `0.184.5`. Upstream head is
`0.195.4` (sweep finding `F-9af9baf7`, re-verified §1.1). `coverage.py` routes
it to the PLAN lane: *"0.x release-line move — at major 0 the minor IS the
breaking axis"*, and the `*nextcloud-mcp*` deny rule (`max: patch`) exists
because upstream has shipped BREAKING-tagged releases on minor hops before
(0.176.0 removed the webhook registration API and dropped its table; 0.177.0
tightened `create_share`).

**This is the second retarget of this plan.** `nextcloud-mcp-0.185.3` was
superseded 2026-09-13 (`00c62d4c`); this file was written 2026-09-15 for
0.187.1, approved the same day, and flagged drifted 2026-09-19 (`F-bb713800`)
when upstream had moved six more lines. Refreshed **in place** 2026-09-22 per
the README ("refresh, do not replace") — same `plan_id`, new `target:`.
Everything below was re-derived for 0.195.0; nothing was sed-ed forward.

**Third refresh, 2026-09-25: 0.195.0 → 0.195.4 (PATCH-only, same line).**
The four patch tags were read individually (§1.2a) and the
`v0.195.0...v0.195.4` source diff checked: fixes only, no tool added,
renamed or removed, no env var, no schema, `mcp` stays 2.1.1, base image moves
only by digest within `python:3.14-slim-trixie` (+ `uv` 0.12.14 → 0.12.18
build tool). Risk, duration, reboot and rollback class are UNCHANGED. The
operator GO recorded for 0.195.0 is **void for 0.195.4** — see §1.8.

**Verdict after reading all twenty release-note sets (§1.2) and the source
diff (§1.6): the hop carries THREE upstream-tagged BREAKING CHANGES.
0.185.0 (mcp SDK v2 floor) and 0.194.0 (`parsing_metadata` key rename) are
inert for this deployment's mode and configuration; 0.192.0
(`nc_calendar_bulk_operations` no longer touches a recurring series unless
`apply_to_series=true`) is LIVE on our tool surface but is a safer default
that adds a parameter and removes no caller-visible field. Everything else is
fixes, 21 additive tools, and optional document-processing features that stay
off without their env vars. Risk stays `medium`, not `low`, for two honest
reasons: (a) the server moves SDK major (1.29.0 → 2.1.1) and base runtime
(python 3.12 → 3.14) in one hop, and (b) the two consumers' client libraries —
now actually measured, §1.4 — sit on different SDK majors from the server and
from each other, so the real-world effect is asserted empirically in §4, not
assumed.**

### 1.1 Registry verification (done 2026-09-22; re-run at execution, §2 step 0)

GHCR OCI index (`Accept: application/vnd.oci.image.index.v1+json`, anonymous
pull-scope token):

| tag | result |
|---|---|
| `0.184.5` (live) | 200, digest `sha256:f6d8839722587f2cd37ec5218a18479f9e313be9904ad4f6bbb36f98bc827065` — identical to the running pod's `imageID` |
| `0.187.1` (old target) | 200, digest `sha256:57d9c93f…` — superseded, NOT the head |
| `0.195.0` (previous target, GO'd 2026-09-23) | 200, digest `sha256:33c37e0063ff6cded7c9406d94a1868eca7b41ab4901b2f01d23eaa76beefd28` — superseded |
| `0.195.1` / `0.195.2` / `0.195.3` | 200 — `fc14e4c7…` / `ad742445…` / `a19516ff…` (intermediate patches, read in §1.2a) |
| **`0.195.4` (target)** | **200, digest `sha256:24417dcb804fc65bcb8712226bf70be71018aefd2ec7b27e9392a4d4e1ed707c`** (re-read 2026-09-25) |
| `latest` | 200, digest **identical** to `0.195.4` → 0.195.4 is upstream's channel head (settles coverage's "CHANNEL UNRESOLVED" note) |
| `0.195.5`, `0.196.0` | 404 — nothing newer exists (2026-09-25) |
| `stable` | 404 — there is no `stable` tag on this repo; `latest` is the only channel pointer |

Full tag pagination (2 pages, 1181 tags — the single-page `tags/list` call
stops at 0.159.0 and must not be used to judge the head) lists exactly
`0.188.0 0.188.1 0.189.0 0.190.0 0.190.1 0.191.0 0.192.0 0.193.0 0.193.1
0.194.0 0.195.0` above 0.187.1 (2026-09-22); `0.195.1`–`0.195.4` were added
2026-09-23..25. GitHub releases agree: `v0.195.4` published
2026-09-25T12:56:04Z, marked Latest, not a pre-release; none of
v0.195.1–v0.195.4 is a pre-release — the channel is stable (upstream publishes
no rc/beta tags on this line). 0.195.4 clears the 48h
`minimum_release_age_hours` gate only at 2026-09-27T12:56Z. **Executed 2026-09-26 in an attended NOW
run it is ~17-30 h old**: G5 governs the unattended lane and is waived for security-driven bumps
(`security_ref: F-80459b23`), so it does not block this attended run -- but the operator's GO takes a
sub-48h artifact knowingly (0.195.0, 7 days old, was the reviewed alternative).
Tags carry no `v` prefix on GHCR (`0.195.4`), only on GitHub releases
(`v0.195.4`).

### 1.2 What actually changed, 0.184.5 → 0.195.4, read per tag

Quoted from the GitHub release bodies (`gh release view vX.Y.Z -R cbcoutinho/nextcloud-mcp-server`).
Rows 0.185.0–0.187.1 were reviewed 2026-09-15 and are carried here condensed;
rows 0.188.0–0.195.0 are new in this refresh.

| tag | published | class | what it says | applies to us? |
|---|---|---|---|---|
| **0.185.0** | 2026-09-05 | **BREAKING CHANGE** | *"requires mcp>=2.1,<3 (protocol 2026-07-28). Server-initiated elicitation no longer reaches 2026-era clients — progressive consent degrades to message_only … Deployments pinning mcp<2 must stay on the previous release."* + tool-failure-message and RuntimeError fixes under mcp 2.x; deck/notes/mail registration lifted to module level. | **Inert on the stated path** (elicitation = multi-user Login Flow; premise 3). The SDK-major move itself is the residual risk (§1.4). `uv.lock`: `mcp 1.29.0` → `mcp 2.1.1`. No tool renamed or removed — mail's 13 tools re-verified by name at 0.195.0 (§1.6). |
| 0.185.1 / 0.185.2 | 2026-09-08/09 | fix (auth) | Login Flow granter/UID checks | Login Flow only — not exercised here. |
| 0.185.3 | 2026-09-09 | fix (deck) | attachment routes | No `deck_*` tools registered (Deck app absent, §2.3) — inert. |
| 0.185.4 | 2026-09-11 | fix (processors) | batch OCR worker-only | No document processors configured (pod log) — inert. |
| **0.185.5** | 2026-09-11 | fix (calendar) | DAV URLs encoded by one rule; percent-encode decoded path segments | **Applies.** Calendar 6.5.3 is installed and on both consumers' surface — verified directly in §4.5. |
| 0.186.0 | 2026-09-11 | feat (additive) | Shopping List app support | 12 `nc_shopping_list_*` tools **WILL register** although the app is **not installed** (§2.3): `server/__init__.py` at 0.195.0 keeps shopping_list out of `APP_CAPABILITY_KEY` (*"gating it would hide working tools on every instance that has it"*). Calls fail with a Nextcloud 404 — additive; §4.4 expects exactly these names. (The 2026-09-15 draft guessed the prefix `shopping_list_*`; the source says `nc_shopping_list_*`.) |
| **0.187.0** | 2026-09-12 | feat (calendar) | `nc_calendar_find_availability` implemented (+ timezone validation) | **Applies — behaviour, not surface.** The name was already registered on 0.184.5 as a stub (`client/calendar.py:2918` "simplified stub that returns empty list"); 0.187.0 makes it real. Part of `capability_change: true`. |
| 0.187.1 | 2026-09-12 | fix (ingest) | empty-download / empty-payload handling | Ingest pipeline not configured — inert. |
| **0.188.0** | 2026-09-15 | feat (webdav) | *"expose file tags"*; `@with_links` on `nc_webdav_find_by_tag_name`; typed responses + exclusion guards for the tag tools | **Applies — additive surface.** 5 new tools: `nc_webdav_list_tags`, `nc_webdav_get_file_tags`, `nc_webdav_find_by_tag_name`, `nc_webdav_tag_file`, `nc_webdav_untag_file`. Backed by core `systemtags 1.24.0` (installed, §2.3), so unlike shopping-list these WORK. Two of them WRITE (tag/untag) — the agent's reach grows. |
| 0.188.1 | 2026-09-15 | fix (contacts) | *"make photo payloads opt-in and add paging"*; mapper keeps photo default, list/search opt out | **Applies — behaviour change on a live tool.** `nc_contacts_list_contacts` (and search) gain `include_photos: bool = False`, `limit`, `offset`; inline base64 `photo` is now `None` in list/search results, `has_photo` reported instead (source diff §1.6). A consumer that displayed contact photos from a list call loses them until it passes `include_photos=true`. Contacts 8.7.6 is installed. Asserted in §4.7. |
| **0.189.0** | 2026-09-16 | feat (webdav) | *"add trash bin and file version tools"*; OCS header on trash/version calls; restore idempotency/refusals | **Applies — additive surface.** 4 new tools: `nc_webdav_list_trash`, `nc_webdav_restore_from_trash`, `nc_webdav_list_versions`, `nc_webdav_restore_version`. Backed by core `files_trashbin 1.24.0` / `files_versions 1.27.0` (installed). Two of them WRITE (restore). |
| 0.190.0 | 2026-09-17 | feat/fix (auth) | CIMD client_ids + RFC 9207 `iss` (#1470); CIMD SSRF/dot-segment hardening; snake_case ToolAnnotations hints on the tag tools; registered client wins over CIMD | OAuth/AS-proxy path only. New setting `CIMD_ALLOWED_HOSTS` defaults to `""` = *disabled* (`config.py` diff). Inert in `single_user_basic`. The ToolAnnotations fix changes tool METADATA on the 5 tag tools only (hint keys), not names. |
| 0.190.1 | 2026-09-17 | fix (deps) | pact installer sha | Test tooling — inert. |
| 0.191.0 | 2026-09-17 | feat (processors) | native PPTX reader via python-pptx; docling auto-serves OOXML | The PPTX reader registers **unconditionally** at module import (`document_processors/__init__.py`, priority 15) — no service needed. Effect: `nc_webdav_read_file` on a `.pptx` returns extracted text where it previously had no parser. Not a break; noted as reach. docling stays off (no `DOCLING_API_URL`). |
| **0.192.0** | 2026-09-18 | **BREAKING CHANGE** | *"nc_calendar_bulk_operations skips events that belong to a recurring series unless apply_to_series=true is passed; previously the whole series was updated or deleted."* + *"set ORGANIZER on events with attendees"* | **APPLIES — the one BREAKING change on our live surface.** `nc_calendar_bulk_operations` is registered today (measured, §2.4). The new default is the SAFER one (a bulk update/delete no longer rewrites a whole series through one matched occurrence); the tool gains `apply_to_series: bool = False` (`server/calendar.py:814` at 0.195.0) and removes no field. A caller relying on the OLD series-wide effect must now pass the flag. Neither consumer scripts bulk calendar edits (OpenClaw's registration is read-oriented; Claude Desktop is interactive). §4.6 asserts the parameter is present — the change made visible. |
| 0.193.0 | 2026-09-18 | feat (pptx) | caption raster pictures via docling-serve (ADR-037) | Opt-in (`OFFICE_CAPTION_IMAGES=false` default) — inert. |
| 0.193.1 | 2026-09-18 | fix (calendar) | `create_meeting` description; *"bind create_meeting events to a timezone (#1502)"* | Applies, benign: `nc_calendar_create_meeting` gains `timezone: str = ""` and falls back to the user's Nextcloud timezone (`client.users.get_current_user_timezone()`), logging a warning if unreadable. Fixes a real bug (floating-time meetings). |
| **0.194.0** | 2026-09-19 | **BREAKING CHANGE** | *"parsing_metadata keys pptx_pictures_found and pptx_pictures_captioned (added in 0.193.0) are renamed to pictures_found and pictures_captioned."* + native `.xlsx` (openpyxl) and `.docx` (python-docx) readers (ADR-038); `OFFICE_CAPTION_*` supersedes `PPTX_CAPTION_*` with a deprecation shim | **Inert**: the renamed keys exist only when captioning is on (it is not), and 0.193.0 never ran here. The `.docx`/`.xlsx` readers register unconditionally like PPTX (§1.6) — same "read_file now parses office docs" reach note. |
| 0.195.0 | 2026-09-19 | feat/fix/perf | legacy + ODF office via a shared Collabora service (ADR-039); vector-sync discovers office/Outlook docs; *"index only formats this build can read"*; *"empty indexable-MIME list = index nothing"*; concurrent tagged-folder expansion | Collabora processor registers **only if `COLLABORA_URL` is set** (source: `if _settings.collabora_url:`) — absent here. Vector-sync is off (no `QDRANT_URL`/`VECTOR_SYNC_ENABLED`, premise 4). New `.msg` (Outlook) reader registers unconditionally via `olefile`. Inert beyond the reach note. |

**No tag in range renames or removes an MCP tool, drops a table, changes the
required Nextcloud server version, or changes any env var this deployment
sets.** The 0.176.0 failure shape (removed API + dropped table) does not
recur. Confirmed against source, not only the notes: the live 96-name tool
list is a strict subset of the names registered by `server/*.py` at
`v0.195.0` (§1.6), and 0.195.1–0.195.4 register no new tool (§1.2a).

### 1.2a The 0.195.x patch tail, 0.195.0 → 0.195.4 (read 2026-09-25)

| tag | published | class | what it says | applies to us? |
|---|---|---|---|---|
| 0.195.1 | 2026-09-23 | fix/refactor | *"webdav: scope a range read's failed-parse fallback to the slice"*; *"webdav: reap the read-path parse worker, add page-range reads"* | **Additive on a live tool.** `nc_webdav_read_file` gains two OPTIONAL args `page_start`/`page_end` (PDF only; rejected with `parse_document="raw"`) and `ReadFileResponse` gains three optional fields `page_count`/`page_start`/`page_end` (`server/webdav.py`, `models/webdav.py` diff). No field removed, default behaviour unchanged when the args are omitted. The parse worker is now reaped after a read — if anything, LOWERS §4.8 working set. Dockerfile: base `python:3.14-slim-trixie` digest bump + `uv` 0.12.14 → 0.12.18; no entrypoint change. |
| 0.195.2 | 2026-09-24 | fix | *"observability: classify tool errors from the wire-shaped result"* | Metrics labelling only. Inert. |
| 0.195.3 | 2026-09-24 | fix (contacts) | *"contacts: drop only unparseable vCard properties, not the whole contact"* | **Applies, benign.** A contact with a property pythonvCard4 rejects (reduced-form `BDAY:--MMDD`, vCard-3 `GEO:`) now keeps its name/phone/email instead of an empty projection; emits a `WARNING Dropped unparseable vCard properties` log line. §4.7 can only get MORE populated. **It does NOT rescue a vCard with no `FN`** (`_parses_alone` prepends `FN:x`, so no line fails alone, `dropped` is empty and the error re-raises): the caller still logs `WARNING Could not parse vCard ...` **with `exc_info=True` — a Traceback** (`client/contacts.py:733-739` at v0.195.4). Two contacts in the household's first addressbook hit exactly this on 0.184.5 today (`FN is required`), so §4.2 attributes vCard Tracebacks instead of counting every Traceback (reviewer 2026-09-26). |
| 0.195.4 | 2026-09-25 | fix (documents) | *"documents: skip the RLIMIT_AS cap when the OS refuses it"* | Hardening of the document-parse isolation worker; no config. Inert unless `setrlimit` fails in the pod, in which case 0.195.0 would have failed the parse. |

`uv.lock` across 0.195.0..0.195.4 changes only the project version and the
`ty` dev dependency: **`mcp` stays 2.1.1**, so §1.4, §4.4's protocol gate and
the 117-name tool surface are unchanged. No tag in the tail is BREAKING-tagged.

### 1.3 Storage: does the server own a table or a PVC?

It runs alembic at startup (`nextcloud_mcp_server.migrations - Upgrading
database to revision: head`) — but against `sqlite+aiosqlite:////tmp/…`
because neither `DATABASE_URL` nor `TOKEN_STORAGE_DB` is set (premise 4), and
the pod mounts no volumes (premise 5). The schema is recreated from nothing on
every container start and discarded with the container. **There is nothing to
back up and nothing a downgrade can collide with**, hence
`rollback_class: git-revert`. (0.185.0 changes WHEN this runs — once per
container start under mcp 2.x instead of once per MCP session under 1.x, see
§1.7 — not WHERE.)

### 1.4 The residual risk, stated plainly — now with measured client versions

0.185.0 moved the server to the MCP python-sdk v2 line (`mcp 2.1.1` locked at
0.195.0). Our two consumers, measured 2026-09-22 (the 2026-09-15 draft could
not):

- **OpenClaw** (`ai`): `mcporter 0.9.0` at
  `/home/node/.openclaw/lib/node_modules/mcporter` (installed 2026-09-19 by
  `install_npm mcporter`, `kubernetes/apps/ai/openclaw/app/helmrelease.yaml:442`,
  unpinned), bundling **`@modelcontextprotocol/sdk` 1.30.0** (TypeScript). That
  SDK's `src/types.ts` declares `LATEST_PROTOCOL_VERSION = '2025-11-25'` and
  `SUPPORTED_PROTOCOL_VERSIONS = ['2025-11-25','2025-06-18','2025-03-26','2024-11-05','2024-10-07']`.
  It speaks streamable-HTTP to this server per `mcporter-config.yaml`
  (`transport: http`, `Authorization` header from the openclaw secret).
- **Claude Desktop** (operator's Mac): `uvx mcp-proxy --transport
  streamablehttp https://nextcloud-mcp.${SECRET_DOMAIN}/mcp` from
  `~/Library/Application Support/Claude/claude_desktop_config.json`, unpinned.
  The uv cache holds `mcp_proxy-0.12.0` (requires `mcp>=1.17.0`) and, newest,
  `mcp-2.2.0` (2026-09-09) — a python **2.x** client, same SDK major as the
  target server.

Server side, `mcp 2.1.1` (`src/mcp-types/mcp_types/version.py`) declares
`HANDSHAKE_PROTOCOL_VERSIONS = ('2024-11-05','2025-03-26','2025-06-18','2025-11-25')`
— *"revisions reachable via the initialize handshake"* — and
`MODERN_PROTOCOL_VERSIONS = ('2026-07-28',)` (the stateless per-request
envelope). So mcporter's offer (`2025-11-25`) and this plan's probe offer
(`2025-06-18`) are both handshake-negotiable on the new server; a hard break is
NOT expected from the protocol table. What the table cannot tell us is how the
two implementations behave on the wire — which is why §4.4 asserts the
negotiated `protocolVersion` for a `2025-06-18` offer and §4.10 runs a real
call through each consumer rather than trusting the TCP probe.

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
accepted-risk model for third-party images, not a plan failure. Note the base
image itself moves in this hop (§1.6), so the residual will be a different set.

### 1.6 What the release notes do NOT say — from the source diff

`gh api repos/cbcoutinho/nextcloud-mcp-server/compare/v0.184.5...v0.195.0`
(81 non-test files). The findings that matter for an operator:

- **Base runtime major: `python:3.12-slim-trixie` → `python:3.14-slim-trixie`**
  (`Dockerfile`, the only two changed lines: `FROM` and the `uv` 0.12.9 →
  0.12.14 copy). No entrypoint/`PUID`/`su-exec` change, so SOP §7d
  (root-required entrypoints) is not triggered. A runtime major is the kind of
  change that shows up as a startup import error or a memory shift, not as a
  release note — hence §4.2 (traceback grep) and §4.8 (working-set ceiling).
- **Four native document readers now import and register at module load with
  no config**: `PptxProcessor`, `DocxProcessor`, `XlsxProcessor` (priority 15)
  and `MsgProcessor` (`document_processors/__init__.py`); new runtime deps
  `python-pptx`, `python-docx`, `openpyxl`, `olefile` (`pyproject.toml`). The
  pod log line *"No optional document processors configured"* is still emitted
  (app.py:188) because it describes the OPTIONAL (service-backed) set, not
  these. Effect for us: `nc_webdav_read_file` on office documents returns text.
- **mcp 2.x moved transport config off the constructor**: upstream now passes
  `transport_security=_build_transport_security()` and
  `max_request_body_size=_max_request_body_size()` to
  `mcp.streamable_http_app(...)`. `_build_transport_security()` defaults to DNS
  rebinding protection **off** (explicitly, to keep k8s service DNS names
  working); `MCP_DNS_REBINDING_PROTECTION`/`MCP_ALLOWED_HOSTS` are unset here
  (premise 4) so the port-forward probe (`Host: localhost:18000`) and the
  HTTPRoute hostname keep working. The body cap is derived from
  `WEBDAV_WRITE_MAX_MB` (default 50 MB) so mcp 2.x's 4 MiB default does not
  cut `nc_webdav_write_file` off.
- **Tool inventory at `v0.195.0`, extracted from every `server/*.py`**
  (`@mcp.tool(...)` decorators plus mail's module-level `mcp.tool(...)(fn)`
  form): calendar 17, collectives 20, contacts 8, mail 13, news 8, sharing 6,
  talk 11, webdav 22 (= 13 today + 9 new), shopping_list 12; tables 6,
  cookbook/deck/notes app-gated (absent here); auth_tools 3 / oauth_tools 4
  registered only under `oauth_enabled` (Login Flow) — not our mode. Every one
  of today's 96 live names is present. **Expected surface after the bump: 117
  = 96 + 9 + 12**, and §4.4 asserts the exact 21 new names, not just a count.
- **0.190.0 CIMD** lives in a new `auth/cimd.py` behind `cimd_allowed_hosts`
  (default `""`, disabled) — dead code for this mode.

### 1.7 One behaviour change in OUR mode that no note mentions

Upstream's own comment on `app_lifespan_basic` (app.py, 0.195.0): *"mcp 2.x
enters this lifespan once, when the Streamable HTTP session manager starts, and
shares the result across every session and request (1.x entered it per
session)."* Live 0.184.5 shows exactly that 1.x shape: 8 `Starting MCP session
in single-user BasicAuth mode` lines and 9 alembic `Upgrading database`
runs in the last 2000 log lines — one per client session. After the bump both
happen **once per container start**, and the single-user Nextcloud client (one
httpx pool) is shared by every session. Consequences: (a) the log-line gate in
§4.3 must expect a count of exactly 1 that does NOT grow with probe sessions;
(b) the ephemeral token SQLite is created once, not per session (premise 4
unchanged); (c) a Nextcloud-side credential change now needs a pod restart to
take effect rather than a new session — irrelevant to this bump, worth knowing.

### 1.8 Approval state — a FRESH GO is required, and the open issue is mis-targeted

> **2026-09-25 retarget 0.195.0 → 0.195.4: the GO recorded for 0.195.0
> (2026-09-23) does NOT carry over.** Status is `awaiting-go` and means it:
> the operator must be re-asked with a card naming **0.195.4** before the
> `sat-attended:2026-10-03` run. The diff is patch-only (§1.2a) and the risk
> class is unchanged, which is why this is a same-day edit rather than a
> re-review — but "patch-only" is a claim the operator is entitled to see
> before it runs. The home-operation go/no-go card must be re-targeted to
> 0.195.4 by the coordinator/window agent (this planner does not write it).
> The text below is the 2026-09-22 history.

Read from the home-operation store 2026-09-22 (`kubectl -n ai exec
deploy/openclaw -c app -- /home/node/.openclaw/bin/home-operation --json
decisions --pending-exec` and `... --json list`):

- `decisions --pending-exec` carries **no** nextcloud-mcp row. The 2026-09-15
  GO (recorded in `4ddcf81e`) is already void — it was cleared when the drift
  was flagged (`a3afa9ba`, 2026-09-20).
- The `go_no_go` issue keyed **`nextcloud-mcp-0.187.1`** is OPEN, `decision:
  null`, `needs_decision: true`, opened `2026-09-20T18:55:13Z` — **with
  `target: "0.187.1"` and a title naming 0.187.1**.

Therefore: (1) nothing recorded authorizes any run of this plan; (2) the open
issue must be **re-ingested (UPSERT by key) with `target: 0.195.0` and a title
naming 0.195.0** by the window agent / sweep before the operator is asked —
an approval recorded against a card that says 0.187.1 is scoped to 0.187.1
(SOP: *"an approval is scoped to what was reviewed"*; same class as the
`nextcloud-34.0.4` note *"does NOT extend to any later target"*); (3) this
plan goes back through `plan-reviewer-agent` → `vetted` first, because §1.2,
§1.6, §4 and `conflicts_with` all changed. `run-now.py preflight` now refuses
a drifted plan as NEEDS-DECISION (`F-58f0bbab`, `test-run-now-plan-drift.py`);
with `target:` at 0.195.0 that gate clears — it does not replace the GO.

## 2. Pre-checks

0. **Re-verify the target is still upstream's head** (manual — the premise
   checker has no network tool). If `0.195.5`/`0.196.0` now return 200,
   **STOP**: read that tag's release body before retargeting — at major 0 a
   new minor is a new breaking surface, never a sed. A new PATCH on 0.195 is
   the one case where retargeting is a same-day edit (same line; still re-read
   the body and re-run this step).
   ```bash
   TOKEN=$(curl -s "https://ghcr.io/token?scope=repository:cbcoutinho/nextcloud-mcp-server:pull&service=ghcr.io" \
     | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
   for t in 0.195.4 latest 0.195.5 0.196.0; do
     printf '%-8s ' "$t"
     curl -sI -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.oci.image.index.v1+json" \
       "https://ghcr.io/v2/cbcoutinho/nextcloud-mcp-server/manifests/$t" \
       | tr -d '\r' | awk 'NR==1{printf "%s ",$2} tolower($1)=="docker-content-digest:"{print $2}'; echo
   done
   # expect: 0.195.4 200 sha256:24417dcb…; latest 200 <SAME digest>; 0.195.5 404; 0.196.0 404
   #   (a DIFFERENT digest on `latest` means a newer tag shipped: STOP and read it, per the rule above)
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
3. **Which Nextcloud apps the tool families depend on** (informs the §1.2
   rows for 0.186.0 / 0.188.0 / 0.189.0 — a change here changes what
   "superset" and "works vs 404s" mean):
   ```bash
   kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c 'php occ app:list' \
     | grep -iE '^\s*- (calendar|contacts|deck|notes|tables|shoppinglist|mail|spreed|collectives|news|cookbook|files_versions|files_trashbin|systemtags):'
   # measured 2026-09-22: calendar 6.5.3, contacts 8.7.6, mail 5.10.12, spreed 24.0.4,
   #   files_trashbin 1.24.0, files_versions 1.27.0, systemtags 1.24.0 present;
   #   NO deck, notes, tables, shoppinglist, cookbook, collectives, news
   #   (collectives/news tools register regardless — upstream gates neither)
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
        -d "{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"$1\",\"params\":${2:-"{}"}}" \
     | python3 -c 'import sys,json
   raw=sys.stdin.read(); data=[l[5:].strip() for l in raw.splitlines() if l.startswith("data:")]
   print(json.dumps(json.loads(data[-1] if data else raw)))'
   EOF
   chmod +x /tmp/ncmcp/call.sh

   # A) tool surface (names) + the full tools/list document (schemas, for §4.6/§4.7)
   /tmp/ncmcp/call.sh tools/list '{}' > /tmp/ncmcp/tools_list.before.json
   python3 -c 'import json; d=json.load(open("/tmp/ncmcp/tools_list.before.json")); [print(t["name"]) for t in d["result"]["tools"]]' \
     | sort > /tmp/ncmcp/tools.before
   wc -l < /tmp/ncmcp/tools.before          # measured 2026-09-22: 96
   # B) calendar set (the 0.185.5 DAV-encoding path)
   /tmp/ncmcp/call.sh tools/call '{"name":"nc_calendar_list_calendars","arguments":{}}' > /tmp/ncmcp/calendars.before
   python3 -c 'import json; d=json.load(open("/tmp/ncmcp/calendars.before")); assert not d["result"].get("isError"), d; print(len(json.dumps(d)))'
   # C) files root (the plain WebDAV path)
   /tmp/ncmcp/call.sh tools/call '{"name":"nc_webdav_list_directory","arguments":{"path":""}}' > /tmp/ncmcp/files.before
   python3 -c 'import json; d=json.load(open("/tmp/ncmcp/files.before")); assert not d["result"].get("isError"), d; print(len(json.dumps(d)))'
   # D) contacts: addressbooks (the 0.188.1 paging/photo path is asserted in §4.7 against this)
   /tmp/ncmcp/call.sh tools/call '{"name":"nc_contacts_list_addressbooks","arguments":{}}' > /tmp/ncmcp/addressbooks.before
   python3 -c 'import json; d=json.load(open("/tmp/ncmcp/addressbooks.before")); assert not d["result"].get("isError"), d; print(len(json.dumps(d)))'
   # E) the NEGOTIATED protocol version + serverInfo from `initialize` — the direct evidence
   #    for the §1.4 client risk AND the build identity (serverInfo.version IS the mcp SDK version)
   kubectl port-forward -n office svc/nextcloud-mcp 18000:8000 >/dev/null 2>&1 & PF=$!; sleep 2
   curl -s -X POST http://localhost:18000/mcp -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
     -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"plan-probe","version":"0"}}}' \
     | python3 -c 'import sys,json
   raw=sys.stdin.read(); data=[l[5:].strip() for l in raw.splitlines() if l.startswith("data:")]
   r=json.loads(data[-1] if data else raw)["result"]; print(r["protocolVersion"], r["serverInfo"].get("version"))' | tee /tmp/ncmcp/protocol.before
   kill $PF 2>/dev/null
   # measured 2026-09-22 on 0.184.5:  2025-06-18 1.29.0
   ```
   Baseline measured 2026-09-22 on 0.184.5: **96 tools** — `collectives_*`
   (20), `nc_calendar_*` (17, incl. `nc_calendar_bulk_operations` WITHOUT an
   `apply_to_series` property and `nc_calendar_find_availability` as a stub),
   `nc_contacts_*` (8, `nc_contacts_list_contacts` with the single property
   `addressbook`), `nc_mail_*` (13), `nc_news_*` (8), `nc_share_*` (6),
   `nc_webdav_*` (13), `talk_*` (11). No `deck_*`, `notes_*`, `tables_*`,
   `nc_shopping_list_*`. **Re-take A–E on the day of execution**, after any
   Nextcloud server move (nextcloud-34.0.4 is the day after; if the order ever
   flips, re-take), so the §4 diff is against the true pre-state.
5. **No firing alerts for office/ai** (Watchdog/InfoInhibitor are excluded
   by NAME — InfoInhibitor DOES carry a namespace label: `{alertname="InfoInhibitor",namespace="ai"}`
   fired within the last 30 d, reviewer 2026-09-26):
   ```bash
   kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 >/dev/null 2>&1 & PF=$!; sleep 2
   curl -s --data-urlencode 'query=ALERTS{namespace=~"office|ai",alertstate="firing",alertname!~"Watchdog|InfoInhibitor"}' http://localhost:9090/api/v1/query \
     | python3 -c "import sys,json; r=json.load(sys.stdin)['data']['result']; print([x['metric'].get('alertname') for x in r] or 'NONE FIRING')" | tee /tmp/ncmcp/alerts.before
   kill $PF 2>/dev/null
   # measured 2026-09-22 and 2026-09-26: NONE FIRING
   # CAN FAIL (absence gate, demonstrated 2026-09-26): count_over_time(ALERTS{namespace=~"office|ai",
   #   alertstate="firing"}[30d]) returned KubeJobFailed (office, ai) and MealiePodRestarted (office) --
   #   this selector does match real firing alerts in these namespaces.
   ```
6. **Active-update marker** (SOP §4 step 1) so alert-triage treats rollout
   noise as expected. A full Alertmanager silence is optional here — single
   replica, ~30s roll, tcp probes; the chart-bundled pod-not-ready alert needs
   15m to fire:
   ```bash
   runbooks/update-marker.sh add nextcloud-mcp office 2 "0.184.5->0.195.4 image bump"
   ```

## 3. Steps

1. Confirm §2 steps 0–6 are green. Do not proceed on a failed premise.
2. Edit the image tag — one line, the whole diff:
   ```bash
   # BSD sed (macOS) does NOT honour `\s` in a BRE — `\(\s*tag: \)` silently matches nothing
   # and the edit no-ops. Use the POSIX class. Dry-tested 2026-09-25 on a scratch copy:
   #   34c34  <               tag: 0.184.5  /  >               tag: 0.195.4   (one hunk, rc=1)
   sed -i '' 's/^\([[:space:]]*tag: \)0\.184\.5$/\10.195.4/' kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml
   git diff --stat kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml   # expect: 1 file, 1 insertion, 1 deletion — a 0-file diff means the sed did not match: STOP
   git diff kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml | grep -E '^[-+][[:space:]]+tag:'
   # expect exactly:  -              tag: 0.184.5  /  +              tag: 0.195.4
   ```
3. Commit + push — shared worktree, so `--only` with the explicit path, and
   confirm the subject is yours before pushing (two sessions committing in the
   same second can swap message files):
   ```bash
   cat > /tmp/ncmcp/msg-nextcloud-mcp-0.187.1.txt <<'EOF'
   feat(nextcloud-mcp): image 0.184.5 -> 0.195.4

   Crosses eleven 0.x minor lines (0.185 .. 0.195, twenty-four tags); at major 0
   the minor digit is the breaking axis, so every tag's release body and the
   v0.184.5...v0.195.0 + v0.195.0...v0.195.4 source diffs were read
   (runbooks/maintenance/plans/nextcloud-mcp-0.187.1.md §1.2, §1.2a, §1.6). Three
   BREAKING-tagged changes: 0.185.0 (mcp>=2.1 SDK floor, elicitation ->
   message_only) and 0.194.0 (parsing_metadata key rename) are inert for
   MCP_DEPLOYMENT_MODE=single_user_basic with no processors configured;
   0.192.0 (nc_calendar_bulk_operations leaves recurring series alone unless
   apply_to_series=true) is a safer default on a live tool and adds a
   parameter only. Adds 21 tools (nc_webdav_* trash/versions/tags,
   nc_shopping_list_*), contacts paging/photo opt-in (0.188.1), the 0.185.5
   CalDAV URL-encoding fix, a working nc_calendar_find_availability,
   nc_webdav_read_file page ranges (0.195.1, optional args), per-property
   vCard parse fallback (0.195.3). Base
   image python 3.12 -> 3.14. No tool renamed/removed, no schema owned
   (ephemeral /tmp SQLite, no PVC).

   security_ref: F-80459b23
   finding_refs: F-9af9baf7, F-80459b23, F-bb713800
   EOF
   git fetch origin main && git merge --ff-only origin/main
   git commit --only kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml -F /tmp/ncmcp/msg-nextcloud-mcp-0.187.1.txt
   git show --stat HEAD      # exactly ONE file: the helmrelease. Anything else rode in from the shared index — fix before pushing.
   git log -1 --format=%s    # expect: feat(nextcloud-mcp): image 0.184.5 -> 0.195.4 — if not, `git commit --amend --only -F /tmp/ncmcp/msg-nextcloud-mcp-0.187.1.txt` before pushing (`--only` with no paths = reword only; a bare `--amend` would sweep another session's staged hunks into this commit)
   git push origin main
   git rev-parse HEAD > /tmp/ncmcp/bump.sha && cat /tmp/ncmcp/bump.sha   # fixed path: §5 and the run log read it; no shell variable crosses blocks
   ```
4. Let Flux reconcile (`interval: 30m`). Forcing is permitted by the SOP when
   the window needs it sooner (`kustomization/nextcloud-mcp` lives in
   namespace `office`, verified live):
   ```bash
   flux reconcile kustomization nextcloud-mcp -n office --with-source
   flux reconcile hr -n office nextcloud-mcp
   ```
   No immutable selectors, no PVC, no migration Job — a plain single-replica
   rolling Deployment update (the RWO multi-attach guard does not apply:
   premise 5, no volumes). Flux `upgrade.remediation.retries: 3` stays as is:
   the SOP's "disable rollback" step is for init-migration apps, and this one
   owns no state a rollback could half-apply.
5. Watch the roll:
   ```bash
   kubectl rollout status deploy/nextcloud-mcp -n office --timeout=180s
   kubectl get pods -n office -l app.kubernetes.io/name=nextcloud-mcp
   ```

## 4. Verification

Instruments this section reads — each named so `plan-premises.py --controls`
can confirm it exists (all four PRESENT in the live label index 2026-09-22):

- CONTROL: metric `kube_deployment_status_replicas_available` — `{namespace="office",deployment="nextcloud-mcp"}` must read `1` after the roll (reads `0` while the new pod is not Ready; read `1` today).
- CONTROL: metric `kube_pod_container_status_restarts_total` — `{namespace="office",container="main",pod=~"nextcloud-mcp-.*"}` must read `0` on the NEW pod 5 min after Ready (a python-3.14/mcp-2.x import failure shows as a climbing counter; `0` today).
- CONTROL: metric `container_memory_working_set_bytes` — `{namespace="office",container="main",pod=~"nextcloud-mcp-.*"}` must stay below `800Mi` (limit is 1Gi; 336 MiB today on 0.184.5 — the ceiling exists because four office readers and a runtime major now load at import).
- CONTROL: metric `ALERTS` — `{namespace=~"office|ai",alertstate="firing"}` must be EMPTY after settle (empty today; the chart-bundled Kube* pod/deployment alerts carry these namespace labels).

1. **Flux Ready on the new revision**:
   ```bash
   kubectl get helmrelease -n office nextcloud-mcp -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} chart={.status.history[0].chartVersion}{"\n"}'
   # expect: True chart=5.1.0     (a failed upgrade prints False + the Released message; a chart hop prints a different version)
   ```
2. **Pod on the target tag AND digest, settled, no traceback on startup** —
   `imageID` is the only proof the new bytes run; the tag alone would also
   match a pod stuck pulling:
   ```bash
   kubectl get deploy -n office nextcloud-mcp -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
   # expect: ghcr.io/cbcoutinho/nextcloud-mcp-server:0.195.4
   kubectl get pod -n office -l app.kubernetes.io/name=nextcloud-mcp -o jsonpath='{range .items[*]}{.metadata.name} restarts={.status.containerStatuses[0].restartCount} {.status.containerStatuses[0].imageID}{"\n"}{end}'
   # expect: ONE pod, restarts=0, imageID ending sha256:24417dcb804fc65bcb8712226bf70be71018aefd2ec7b27e9392a4d4e1ed707c
   #         (the OLD digest f6d88397… here means the roll did not happen or was remediated back;
   #          33c37e00… means the 0.195.0 bytes — the superseded target — are running: wrong tag committed)
   kubectl logs -n office deploy/nextcloud-mcp > /tmp/ncmcp/log.after-start     # whole log of the NEW container, no --tail
   python3 - <<'EOF'
   import re
   L=open("/tmp/ncmcp/log.after-start").read().splitlines()
   err=[l for l in L if re.search(r'(^|\s)(ERROR|CRITICAL)\s', l)]
   tb=[i for i,l in enumerate(L) if l.startswith('Traceback')]
   vc=[i for i in tb if i>0 and 'Could not parse vCard' in L[i-1]]
   print(f"lines={len(L)} ERROR/CRITICAL={len(err)} Traceback={len(tb)} vCard-attributed={len(vc)}")
   assert L, "EMPTY log -- wrong pod/container or log not yet written; do not pass"
   assert not err and len(tb)==len(vc), "unattributed ERROR/CRITICAL/Traceback in the new pod's log -- read /tmp/ncmcp/log.after-start"
   EOF
   # PASS: ERROR/CRITICAL=0 and every Traceback is vCard-attributed (0.195.4 still logs WARNING
   #   'Could not parse vCard ...' WITH exc_info for contacts lacking FN -- client/contacts.py:733-739 at
   #   v0.195.4; the 0.195.3 per-property fallback cannot rescue a missing FN). Those are known data, not
   #   a regression, and appear as soon as ANY caller lists the first addressbook.
   # CAN FAIL (demonstrated 2026-09-26, reviewer): the identical matcher on the live 0.184.5 log read
   #   Traceback=4 vCard-attributed=4 ERROR/CRITICAL=0 (so it DOES match this container's Tracebacks), and a
   #   scratch copy with one injected unattributed Traceback + one 'ERROR [x] uvicorn.error' line read
   #   ERROR/CRITICAL=1 Traceback=5 vCard-attributed=4 -> assertion fires.
   # (reviewer 2026-09-23: the 'Configuring MCP server for ... mode' line is logged at app.py:1824 BEFORE the
   #  first log handler exists (installed inside NextcloudMCPServer at 1825) and never reaches the log --
   #  demonstrated on the live pod. The mode is proven by premise 3 and by the §4.3 'Starting MCP session' line.)
   ```
3. **CONTENTS ASSERTION (lifespan semantics landed, §1.7): the BasicAuth
   session lifespan ran exactly once, at container start, and does not run
   again per probe session** — measured by counting the line before and after
   §4.4's sessions:
   ```bash
   kubectl logs -n office deploy/nextcloud-mcp | grep -c 'Starting MCP session in single-user BasicAuth mode'   # no --tail: later probes add lines
   # expect: 1 immediately after start (on 0.184.5 this line only appeared once a client session opened)
   # …after §4.4 has opened two sessions, re-run: still 1. A count that climbs means the 1.x per-session
   # lifespan is still running, i.e. the pod is NOT on the mcp 2.x build — cross-check §4.2's imageID.
   ```
4. **CONTENTS ASSERTION (surface): the MCP tool set is exactly the baseline
   plus the 21 names §1.6 derived from source** — measured by `tools/list`
   through the real streamable-HTTP handshake, compared to
   `/tmp/ncmcp/tools.before`. A TCP probe proves the port is open; this
   proves the server still registers what our agents call, and that the
   additions are the ones the notes promise (a different set means an
   unreviewed change).
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
   python3 -c 'import json; d=json.load(open("/tmp/ncmcp/tools_list.after.json")); [print(t["name"]) for t in d["result"]["tools"]]' \
     | sort > /tmp/ncmcp/tools.after
   comm -23 /tmp/ncmcp/tools.before /tmp/ncmcp/tools.after     # tools that DISAPPEARED — expect EMPTY
   comm -13 /tmp/ncmcp/tools.before /tmp/ncmcp/tools.after | diff - /tmp/ncmcp/tools.expected_new && echo 'NEW TOOLS == EXPECTED'   # expect the echo; any diff line is an unreviewed addition/omission
   wc -l < /tmp/ncmcp/tools.after                              # expect 117
   # negotiated protocol version + serverInfo after the bump — compare to /tmp/ncmcp/protocol.before (§2.4 E)
   kubectl port-forward -n office svc/nextcloud-mcp 18000:8000 >/dev/null 2>&1 & PF=$!; sleep 2
   curl -s -X POST http://localhost:18000/mcp -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
     -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"plan-probe","version":"0"}}}' \
     | python3 -c 'import sys,json
   raw=sys.stdin.read(); data=[l[5:].strip() for l in raw.splitlines() if l.startswith("data:")]
   r=json.loads(data[-1] if data else raw)["result"]; print(r["protocolVersion"], r["serverInfo"].get("version"))' | tee /tmp/ncmcp/protocol.after
   kill $PF 2>/dev/null
   # expect: '2025-06-18 ' -- protocolVersion 2025-06-18 and serverInfo.version EMPTY
   #   - protocolVersion 2025-06-18: the offer is in mcp 2.1.1's HANDSHAKE_PROTOCOL_VERSIONS (§1.4), so the
   #     server must echo it. Any OTHER value (e.g. 2025-11-25 or 2026-07-28) means the server counter-offered
   #     and the §1.4 client risk is real for 2025-06-18-era clients — record it on F-9af9baf7 and weigh §4.10.
   #   - serverInfo.version EMPTY: mcp 2.x reports the version the app passes and substitutes nothing
   #     (the app constructs NextcloudMCPServer("Nextcloud MCP", lifespan=...) with no version); 1.x printed
   #     its own 1.29.0. So the empty string IS the 2.x signature, and a non-empty '1.29.0' after the roll
   #     means the old build is still serving (the §5 rollback check stays valid). Build identity rests on
   #     the §4.2 imageID digest, not on this field (reviewer 2026-09-23).
   ```
5. **CONTENTS ASSERTION (behaviour): the two Nextcloud-facing paths this hop
   touched still return real data** — `nc_calendar_list_calendars` crosses the
   0.185.5 DAV-encoding rewrite (and 0.192.0/0.193.1 touched the same
   module), `nc_webdav_list_directory` is the files path both consumers use
   most (and the webdav module gained 9 tools). Compared to the §2.4
   baselines: same calendar set, non-empty file listing, `isError` false on
   both.
   ```bash
   /tmp/ncmcp/call.sh tools/call '{"name":"nc_calendar_list_calendars","arguments":{}}' > /tmp/ncmcp/calendars.after
   /tmp/ncmcp/call.sh tools/call '{"name":"nc_webdav_list_directory","arguments":{"path":""}}' > /tmp/ncmcp/files.after
   # Paths are ARGUMENTS so §5 can replay the identical gate on calendars.revert/files.revert.
   python3 - /tmp/ncmcp/calendars.before /tmp/ncmcp/calendars.after /tmp/ncmcp/files.before /tmp/ncmcp/files.after <<'EOF'
   import json, sys
   from urllib.parse import unquote
   CB, CA, FB, FA = sys.argv[1:5]
   def result(p):
       r = json.load(open(p))["result"]; assert not r.get("isError"), (p, r)
       return r
   def full_unquote(s):
       # 0.184.5 emits `name` as the RAW href segment; 0.185.5+ unquote()s it once
       # (client/calendar.py:584 at v0.185.5, :730 at v0.195.4). A calendar whose Nextcloud URI itself
       # holds a literal `%28` therefore reads `%2528` on 0.184.5 and `%28` on 0.195.x -- SAME calendar.
       # ONE unquote leaves the two shapes one level apart: that false STOP reverted the 2026-09-26 run.
       # Decode until stable so both collapse to one key.
       for _ in range(8):
           n = unquote(s)
           if n == s: return s
           s = n
       raise AssertionError(f"unquote did not converge: {s!r}")
   def cals(p):
       r = result(p)
       sc = r.get("structuredContent") or json.loads(" ".join(c.get("text", "") for c in r.get("content", [])))
       items = sc.get("calendars")
       assert isinstance(items, list) and items, f"{p}: no non-empty `calendars` list -- fix the parser before judging"
       assert sc.get("total_count", len(items)) == len(items), f"{p}: total_count {sc.get('total_count')} != {len(items)} rows"
       out, shapes = {}, []
       for c in items:
           seg = c["href"].rstrip("/").split("/")[-1]
           # name must be the href segment raw (<=0.185.4) or decoded ONCE (>=0.185.5); anything else
           # (over-decoded to "(", truncated, swapped) breaks the name->URL round-trip the tools rely on.
           assert c["name"] in (seg, unquote(seg)), f"{p}: name {c['name']!r} is neither raw nor once-decoded href segment {seg!r}"
           if seg != unquote(seg): shapes.append("raw" if c["name"] == seg else "once")
           key = full_unquote(c["href"])      # href is byte-identical across 0.184.5/0.195.4 (measured 2026-09-26)
           assert key not in out, f"{p}: two calendars collapse to one key {key!r} -- compare raw hrefs instead"
           out[key] = (c["display_name"], full_unquote(c["name"]))
       return out, shapes
   (b, sb), (a, sa) = cals(CB), cals(CA)
   missing, added = sorted(b.keys() - a.keys()), sorted(a.keys() - b.keys())
   changed = sorted(k for k in b.keys() & a.keys() if b[k] != a[k])
   assert not (missing or added or changed), f"calendar set differs: missing={missing} added={added} changed={[(k, b[k], a[k]) for k in changed]}"
   fb, fa = (" ".join(c.get("text", "") for c in result(p).get("content", [])) for p in (FB, FA))
   assert len(fa) > 0, "empty file listing after bump"
   print(f"calendars before/after: {len(b)} {len(a)} | encoded-name shape before={sorted(set(sb))} after={sorted(set(sa))} | files listing bytes before/after: {len(fb)} {len(fa)}")
   EOF
   # expect (forward): calendars before/after: 4 4 | encoded-name shape before=['raw'] after=['once'] | ...
   #   after=['raw'] on the forward run means the 0.185.5 fix is NOT in the running image -- cross-check §4.2's digest.
   # PROVEN 2026-09-26 (reviewer) on the recorded /tmp/ncmcp readings: PASS on calendars.before vs .after
   #   (0.184.5 `%2528` vs 0.195.4 `%28`) and vs .revert; the OLD one-unquote gate reproduces the false
   #   "2 missing". FAILS (rc=1) on synthetic copies of calendars.after with: an encoded calendar removed,
   #   a plain calendar removed, a display_name renamed, a URI renamed, a name over-decoded to "(",
   #   isError=true, and an empty list.
   ```
6. **CONTENTS ASSERTION (the 0.192.0 BREAKING, made visible):
   `nc_calendar_bulk_operations` now carries `apply_to_series`** — measured on
   the `tools/list` document, compared to the baseline where the property is
   absent (measured 2026-09-22: 15 properties, no `apply_to_series`). This
   gate fails on the old build by construction.
   ```bash
   python3 - <<'EOF'
   import json
   def props(p, name):
       d=json.load(open(p)); t=[t for t in d["result"]["tools"] if t["name"]==name]
       assert t, f"{name} missing from {p}"
       return t[0].get("inputSchema",{}).get("properties",{})
   b=props("/tmp/ncmcp/tools_list.before.json","nc_calendar_bulk_operations")
   a=props("/tmp/ncmcp/tools_list.after.json","nc_calendar_bulk_operations")
   assert "apply_to_series" not in b, "baseline already had apply_to_series — was §2.4 A taken on 0.184.5?"
   assert "apply_to_series" in a, f"apply_to_series ABSENT after bump; props={sorted(a)}"
   assert a["apply_to_series"].get("default") in (False, None), a["apply_to_series"]
   assert set(b) <= set(a), f"bulk_operations LOST properties: {set(b)-set(a)}"
   print("bulk_operations props before/after:", len(b), len(a), "| apply_to_series default:", a["apply_to_series"].get("default"))
   EOF
   ```
7. **CONTENTS ASSERTION (the 0.188.1 contacts change, both halves):
   `nc_contacts_list_contacts` gained `include_photos`/`limit`/`offset`, AND a
   real list call on the first addressbook returns contacts with `has_photo`
   and no inline photo payload by default** — schema from the `tools/list`
   documents, contents from a live call against the §2.4 D addressbook set.
   ```bash
   python3 - <<'EOF'
   import json
   def props(p, name):
       d=json.load(open(p)); t=[t for t in d["result"]["tools"] if t["name"]==name]
       assert t, f"{name} missing from {p}"
       return set(t[0].get("inputSchema",{}).get("properties",{}))
   b=props("/tmp/ncmcp/tools_list.before.json","nc_contacts_list_contacts")
   a=props("/tmp/ncmcp/tools_list.after.json","nc_contacts_list_contacts")
   assert b == {"addressbook"}, f"baseline schema unexpected: {b}"
   assert {"addressbook","include_photos","limit","offset"} <= a, f"paging/photo params ABSENT after bump: {a}"
   print("list_contacts props before/after:", sorted(b), sorted(a))
   EOF
   AB=$(python3 -c 'import json,re
   d=json.load(open("/tmp/ncmcp/addressbooks.before")); txt=" ".join(c.get("text","") for c in d["result"].get("content",[]))
   m=re.search(r"\"(?:name|id|uri)\"\s*:\s*\"([^\"]+)\"", txt); print(m.group(1) if m else "")')
   [ -n "$AB" ] || { echo "no addressbook id parsed from §2.4 D — inspect /tmp/ncmcp/addressbooks.before"; false; }
   /tmp/ncmcp/call.sh tools/call "{\"name\":\"nc_contacts_list_contacts\",\"arguments\":{\"addressbook\":\"$AB\",\"limit\":5}}" > /tmp/ncmcp/contacts.after
   python3 - <<'EOF'
   import json,re
   d=json.load(open("/tmp/ncmcp/contacts.after")); r=d["result"]; assert not r.get("isError"), r
   txt=" ".join(c.get("text","") for c in r.get("content",[]))
   assert "has_photo" in txt, "has_photo key ABSENT — the 0.188.1 mapper is not running (or the addressbook is empty: check the raw file)"
   inline=re.findall(r'"photo"\s*:\s*"(?:data:image|[A-Za-z0-9+/]{200,})', txt)
   assert not inline, f"{len(inline)} inline photo payload(s) returned although include_photos defaults to False"
   print("contacts listed (limit 5) — has_photo present, inline photos:", len(inline))
   EOF
   ```
   *Absence half demonstrated 2026-09-26 (reviewer):* the identical `"photo"` regex on a 0.184.5
   `nc_contacts_list_contacts` of the same first addressbook matched 91 inline payloads, 4 of them in
   the first 5 contacts -- so on the new build "0 inline" is the default working, not a regex that
   cannot match. The first addressbook is also the one holding the two FN-less vCards, so this call
   adds vCard Tracebacks to the log (expected; §4.2 attributes them).
8. **Memory settle (python 3.14 + four native readers at import, §1.6)** —
   5 minutes after Ready, read the working set through Prometheus and assert
   the ceiling; the limit is 1Gi and an OOMKill would show as the §4.2
   restart counter, this catches the slow climb before it:
   ```bash
   kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 >/dev/null 2>&1 & PF=$!; sleep 2
   curl -s --data-urlencode 'query=container_memory_working_set_bytes{namespace="office",container="main",pod=~"nextcloud-mcp-.*"}' http://localhost:9090/api/v1/query \
     | python3 -c "
   import sys,json; r=json.load(sys.stdin)['data']['result']
   assert r, 'EMPTY — the new pod is not scraped yet (or Prometheus is mid-restart: see conflicts_with); retry, do not pass'
   for x in r:
       mib=float(x['value'][1])/2**20; print(x['metric']['pod'], f'{mib:.0f} MiB'); assert mib < 800, f'working set {mib:.0f} MiB >= 800 MiB ceiling'
   "
   curl -s --data-urlencode 'query=kube_pod_container_status_restarts_total{namespace="office",container="main",pod=~"nextcloud-mcp-.*"}' http://localhost:9090/api/v1/query \
     | python3 -c "import sys,json; r=json.load(sys.stdin)['data']['result']; assert r, 'EMPTY'; print([(x['metric']['pod'], x['value'][1]) for x in r]); assert all(x['value'][1]=='0' for x in r), 'restarts > 0'"
   kill $PF 2>/dev/null
   # measured 2026-09-22 on 0.184.5: 336 MiB, restarts 0
   ```
9. **No new firing alerts** in `office`/`ai` — re-run §2.5 and diff against
   `/tmp/ncmcp/alerts.before` (expect both `NONE FIRING`). An EMPTY Prometheus
   answer is not a pass — the query above asserts a result row exists for the
   memory metric first, so a dead scrape is caught there.
10. **The actual consumers, not just the endpoint** — the only assertion that
    can catch a client-library/protocol mismatch (§1.4):
    - From OpenClaw (`ai`; `mcporter` / TS SDK, offers `2025-11-25`) — the SAME
      client binary, URL and Authorization header the agent uses. The pod's
      `/etc/openclaw-mcp/mcp-servers.json` is OpenClaw's own map (`url`,
      placeholder tokens), NOT mcporter's `{"mcpServers":{..."baseUrl"...}}`
      schema, so a throwaway mcporter config is built from the pod env. mcporter
      interpolates `${VAR}` in `headers` but NOT in `baseUrl` (0.9.0 throws
      `ERR_INVALID_URL` on it), hence the printf; the header value never lands
      on disk. **mcporter exits 0 on HTTP 500 and on `isError`** (measured
      0.9.0), so the gate is the JSON body, never `$?`:
      ```bash
      kubectl exec -n ai deploy/openclaw -c app -- sh -c '
        M=/home/node/.openclaw/lib/node_modules/mcporter/dist/cli.js
        node "$M" --version >&2
        cfg=$(mktemp /tmp/mcporter-ncmcp.XXXXXX)
        printf "{\"imports\":[],\"mcpServers\":{\"nextcloud\":{\"baseUrl\":\"%s\",\"headers\":{\"Authorization\":\"\${NEXTCLOUD_MCP_AUTH_HEADER}\"}}}}" "$NEXTCLOUD_MCP_URL" > "$cfg"
        node "$M" call --config "$cfg" --output json --timeout 30000 nextcloud.nc_webdav_list_directory path=""
        rm -f "$cfg"' > /tmp/ncmcp/openclaw.after
      python3 - /tmp/ncmcp/openclaw.after /tmp/ncmcp/files.after <<'EOF'
      import json, sys
      out, ref = sys.argv[1], sys.argv[2]
      raw = open(out).read()
      assert raw.strip(), f"{out}: empty -- mcporter printed nothing (its exit status is 0 even on HTTP 500/isError)"
      d = json.loads(raw)
      assert "error" not in d and not d.get("isError"), f"OpenClaw/mcporter call FAILED: {json.dumps(d)[:300]}"
      got = {f["name"] for f in d.get("files", [])}
      r = json.load(open(ref))["result"]
      want = {f["name"] for f in (r.get("structuredContent") or json.loads(r["content"][0]["text"]))["files"]}
      assert got, f"{out}: no `files` in the mcporter result -- not real data"
      assert got == want, f"root listing via OpenClaw differs from files.after: missing={sorted(want-got)} extra={sorted(got-want)}"
      print(f"4.10 OpenClaw/mcporter PASS: {len(got)} root entries, identical to files.after")
      EOF
      # record the mcporter version printed on stderr (install_npm mcporter is UNPINNED; npm head is
      # 0.14.x, the plan measured 0.9.0 on 2026-09-22) so a failure is attributable.
      ```
      PROVEN 2026-09-26 (reviewer, mcporter 0.9.0 AND 0.14.1 locally, identical `sh -c`
      body): the config parses, the Authorization header is interpolated onto
      the POST to `/mcp`; the checker PASSes on a result carrying the 26 root
      entries of `files.after`, and FAILs on an `isError` result, on an HTTP 500
      (`{"error": "SSE error: Non-200 status code (500)", ...}`, exit 0) and on
      empty output. What the fake server could NOT prove is the real TS-SDK ↔
      `mcp 2.1.1` handshake — that is exactly what this live call is for.
    - Attended windows: the operator repeats it once from Claude Desktop
      (`mcp-proxy` 0.12.0 with python `mcp` 2.2.0 — a 2.x client): open the
      `nextcloud` server, list the root folder. Note in the run log which
      `mcp` version uvx resolved (`ls -t ~/.cache/uv/archive-v0 | head`), so a
      future failure is attributable.
11. **Close out**: `runbooks/update-marker.sh clear nextcloud-mcp`; delete
    this plan file in the same commit series once `executed`. `F-80459b23` and
    `F-9af9baf7` are script-owned and close themselves on the next sweep when
    the tag on the record no longer matches the live image — verify that
    happened rather than assuming it. `F-bb713800` (plan drift) is
    already `resolved` (2026-09-23T14:48Z, re-read 2026-09-26) -- nothing to close; kept in
    `finding_refs` as history only.

## 5. Rollback

Stateless bridge, no data, no owned schema (premises 4–5) — a straight
image-tag revert:

```bash
# NOT `git revert`: in this shared worktree it refuses with rc=128 ("your local changes would be
# overwritten by revert") whenever ANY other session has something staged -- the index held a foreign
# staged add at the start of the 2026-09-26 review; reproduced in a scratch repo. Inverse edit + --only
# instead (inverse sed dry-tested 2026-09-26 on a scratch copy: restores the file byte-identical).
cd /Users/mu/code/cberg-home-nextgen || exit 1
sed -i '' 's/^\([[:space:]]*tag: \)0\.195\.4$/\10.184.5/' kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml
git diff --stat -- kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml   # expect 1 file, 1+/1- ; 0 files = sed no-op: STOP
cat > /tmp/ncmcp/msg-revert-nextcloud-mcp-0.187.1.txt <<'EOF'
Revert "feat(nextcloud-mcp): image 0.184.5 -> 0.195.4"

Rollback per runbooks/maintenance/plans/nextcloud-mcp-0.187.1.md section 5
(stateless bridge, image tag only). Reverts the bump commit recorded in
/tmp/ncmcp/bump.sha.
EOF
git commit --only kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml -F /tmp/ncmcp/msg-revert-nextcloud-mcp-0.187.1.txt
git show --stat HEAD      # exactly ONE file: the helmrelease
git log -1 --format=%s    # expect: Revert "feat(nextcloud-mcp): image 0.184.5 -> 0.195.4"
git push origin main
flux reconcile kustomization nextcloud-mcp -n office --with-source && flux reconcile hr -n office nextcloud-mcp
kubectl rollout status deploy/nextcloud-mcp -n office --timeout=180s
kubectl get pod -n office -l app.kubernetes.io/name=nextcloud-mcp -o jsonpath='{range .items[*]}{.metadata.name} {.status.containerStatuses[0].imageID}{"\n"}{end}'
# expect: imageID ending sha256:f6d8839722587f2cd37ec5218a18479f9e313be9904ad4f6bbb36f98bc827065 (the 0.184.5 index digest, §1.1)
```

Confirm the cluster is back by re-running §4.4 and §4.5 against the reverted
pod: `tools.after` must equal `tools.before` exactly (96 names, `comm` empty
both ways), `protocol.after` must read `2025-06-18 1.29.0`, and both tool
calls must return the baseline data (replay §4.5 with its 2nd and 4th path
arguments replaced by `/tmp/ncmcp/calendars.revert` and `/tmp/ncmcp/files.revert`;
expect `after=['raw']`). Then re-run §4.10 from OpenClaw. If the
failure was a consumer-side protocol mismatch rather than the server, note it
on `F-9af9baf7` (`policy-cli.py finding detail`) — the fix is pinning the
client (`install_npm mcporter@<ver>` / `uvx --from mcp-proxy==<ver>`), not
holding the server forever.

## 6. Interference notes

- **Cross-namespace consumer, not a shared-infra token.** OpenClaw (`ai`)
  consumes this server as its `nextcloud` MCP tool
  (`kubernetes/apps/ai/openclaw/app/mcporter-config.yaml`). This plan edits
  nothing in `ai`, but a bad bump makes OpenClaw lose that tool *silently*
  (outbound keeps working; the tool call just fails) — treat any post-bump
  OpenClaw nextcloud-tool failure as belonging to THIS plan, not as `ai`
  noise. Claude Desktop on the operator's Mac is the second consumer; it is
  outside the cluster and needs an attended check (§4.10).
- **`capability_change: true` → attended lane.** Derived class is attended
  regardless (deny-rule reason); the flag documents WHY: 21 new tools, four of
  which WRITE into Nextcloud (`nc_webdav_tag_file`, `nc_webdav_untag_file`,
  `nc_webdav_restore_from_trash`, `nc_webdav_restore_version`) and all of
  which work today because their backing apps are core; `nc_shopping_list_*`
  register but 404; `nc_calendar_bulk_operations` changes what a series-wide
  edit needs; contacts lists drop inline photos; `nc_webdav_read_file` now
  parses office documents. None is a reason to hold — but the operator should
  know the agent's reach grew, and the OpenClaw `nextcloud` entry's
  description (*"read-oriented"*) is now further from the truth than before.
- **Same slot: `external-dns-unowned-cnames`** (`sat-attended:2026-10-03`,
  draft, 40 min, medium, `touches.shared: [gateway/envoy]`, namespace
  `network`). No shared resource with this plan: it writes ownership TXT
  records for `envoy-external` hosts in Cloudflare; this server is on
  `envoy-internal`, every gate here goes over a port-forward, and §4.10 from
  OpenClaw resolves the internal hostname via k8s-gateway, untouched by that
  plan. Capacity 75/90 min, risk 4/6. Suggested order: this plan FIRST
  (shorter, `git-revert`), then external-dns — so a DNS-side issue there
  cannot be confused with a consumer failure here.
- **`nextcloud-34.0.4`** (`office`, vetted, `sun-attended:2026-10-04` — the
  next day): in `conflicts_with` since 2026-09-15 and reciprocal. Never the
  same slot: a Nextcloud restart mid-§4.5 makes a calendar-list failure
  unattributable, and that plan's namespace-wide silence would mask this
  rollout's noise. Consecutive days are fine in either order; the
  `nextcloud-server-unchanged` premise tolerates the patch digit for exactly
  this reason. **Re-take the §2.4 baselines (A–E) the same day as execution.**
- **`nextcloud-redis-hardening`** (`office`, draft, unwindowed): reciprocal
  conflict added 2026-09-22. It quiesces the server and restarts the Redis
  that holds PHP sessions/file locks — every §4 contents gate here is a live
  call into that server. Different slots.
- **`kube-prometheus-stack-91.4.1`** (`monitoring`): **EXECUTED 2026-09-26** (91.5.2, on-demand;
  Prometheus pod restarted ~05:00Z and all four §4 CONTROL series re-read PRESENT at 05:2xZ by the
  reviewer) -- the conflict is moot for today's run. History: added
  on THIS side 2026-09-22 because §2.5, §4.8 and §4.9 read Prometheus; a
  Prometheus/operator restart mid-window makes the memory gate print EMPTY
  (which §4.8 refuses to pass, but cannot turn into a pass either). The
  reciprocal entry on that plan is owed by its next editor.
- **`bitnamilegacy-exit-nextcloud-db`** (`office`, `blocked`, unwindowed)
  restarts `deployment/nextcloud` when revived. If both are ever live in one
  window, add it to `conflicts_with` and run this (lighter, stateless) bump
  FIRST, then verify §4.5 again after the DB work — same reasoning.
- **Flux `dependsOn: nextcloud`** is ordering-only (namespace/reconcile-first);
  confirmed not a version coupling by reading every release body in range.
- Never `nightly`: the deny rule's reason is explicit and this plan narrows
  *why* for this hop, it does not overturn it. Nothing here touches Longhorn,
  cert-manager, cilium, coredns, or any other route on `envoy-internal` — safe
  alongside unrelated `office`/`ai` work that does not share a resource listed
  in `touches`.

## 7. What I could not verify (2026-09-22)

- **The wire behaviour of the TS SDK 1.30.0 client (mcporter) against the
  python mcp 2.1.1 server.** Both protocol tables say `2025-11-25` is
  handshake-negotiable (§1.4) and I read the server's version registry, but I
  could not read the 2.1.1 `ServerSession` negotiation branch itself
  (fetched `session.py`, the grep found no `SUPPORTED_PROTOCOL_VERSIONS` — the
  logic moved), and mcporter's exact `initialize` payload is not in this repo.
  §4.4 (negotiated version for a `2025-06-18` offer) and §4.10 (a real
  mcporter call) are the empirical answer.
- **Which `mcp` version `uvx mcp-proxy` will resolve on the day.** The cache
  shows 2.2.0 as newest (2026-09-09); uvx re-resolves per launch. §4.10 asks
  the operator to record it.
- **Whether `nc_contacts_list_contacts` on the household's first addressbook
  returns at least one contact** — §4.7 asserts `has_photo` is present, which
  needs a non-empty result; if the first addressbook is empty the gate tells
  you to look at the raw file rather than passing.
- **The runtime effect of python 3.12 → 3.14 on this exact image** beyond
  "upstream CI built and released it": no per-tag CI status was fetched. §4.2
  (traceback grep, restart counter) and §4.8 (working set) are the gates.
- **The home-operation issue's target field** can only be corrected by an
  emitter with write access (window agent / sweep); this planner read it
  (§1.8) and could not fix it.

(Settled since the 2026-09-15 draft and moved into §1.4/§1.6: the consumers'
client-library versions; that `nc_shopping_list_*` registers with the app
absent; the exact 21 new tool names; that mail's 13 tools survive the
module-level registration refactor.)
