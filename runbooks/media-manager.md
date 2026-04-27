# Runbook: Media Manager

Operator-facing flows for the `media-manager` sub-agent. Definitions live in:

- Agent: `.claude/agents/media-manager.md`
- Standard: `docs/sops/media-library-standards.md`
- GitOps app: `kubernetes/apps/media/library-tools/`
- Tube Archivist (Jellyfin-only): `kubernetes/apps/download/tube-archivist/app/{metadata,image}-sync-{configmap,cronjob}.yaml`

## SOP Integration

Before any non-trivial action, check for relevant SOPs in `docs/sops/`:

- List SOPs: `ls docs/sops/`
- Search by topic: `rg -n "<keyword>" docs/sops/*.md`
- Mandatory pre-flight for any storage delete: `docs/sops/storage-safety.md`.

## When to invoke the agent

Invoke `media-manager` (Claude sub-agent, `subagent_type: media-manager`) for:

- "organise the latest jdownloader batch"
- "migrate Movies starting with A to the nested layout"
- "migrate <show> to nested layout"
- "audit the media library"
- "check metadata for <item>"
- "fix metadata / cover art for <movie or show>"
- "add a new Tube Archivist channel to Plex"
- "rebuild artwork for one show"
- Anything that requires walking, classifying, renaming, sidecaring, or rescanning the Plex/Jellyfin libraries

Do **not** invoke for: Plex / Jellyfin server upgrades (that's `cluster-ops-agent`); Helm chart bumps (`version-check-agent`); generic kubectl debugging.

> **Privacy note:** when phrasing a task to the agent, you can name a specific show / movie / channel in your prompt — that text stays in the live conversation. The agent itself will **never** write the title back into any committed artifact (commit, doc, runbook, audit report, PR body). The repo is public.

## Common flows

### 1. Run an audit and read the report

```bash
# Trigger a one-off audit job (read-only)
kubectl -n media create job --from=cronjob/media-library-audit "media-audit-$(date +%s)"

# Watch progress
kubectl -n media get jobs | grep media-audit | tail -5

# Read the latest auto-generated report
less runbooks/media-library-current.md
```

The report lists per-section compliance against the thresholds in `docs/sops/media-library-standards.md` plus a worst-N table, an orphan-sidecar list, and a drift list. It is gitignored and overwritten on every run — do not hand-edit.

### 2. Organise a new JDownloader batch

```text
Invoke the agent: "organise the latest jdownloader batch"
```

The agent will:

1. List `/mnt/nas/media/downloads/jdownloader` via a debug pod.
2. ffprobe each candidate.
3. Render a move plan as a table.
4. Surface the plan + any conflicts for go/no-go.
5. On approval: create destination folders, `mv`, write sidecars, fetch artwork.
6. Verify each target `size > 0`.
7. `rm -rf` the specific subdirs (hard-coded paths, no globs).
8. Delegate Plex/Jellyfin rescan to `cluster-ops-agent`.
9. Report counts + any "unmatched" items.

If anything is ambiguous (file conflict, broken RAR, unknown classification), the agent stops and asks via `AskUserQuestion`.

### 3. Migrate one batch from flat to nested

```text
Invoke the agent: "migrate Movies starting with A to the nested layout"
# or
Invoke the agent: "migrate <show name> to the nested layout"
```

Default unit = one alphabetical letter for movies, one show for TV. The agent never runs "migrate everything" in one shot. Pause between batches for spot-check before proceeding.

### 4. Repair missing metadata / cover art for a single item

```text
Invoke the agent: "fix metadata for <movie or show>"
```

(Use the title in the live prompt only — do **not** paste it into a commit message, doc, or runbook log; this repo is public.)

The agent will fetch the missing sidecar(s) from TMDb / TVDb / MusicBrainz, resize to target dimensions if needed, write to the correct on-disk path, then trigger a single-item rescan via `cluster-ops-agent`.

### 5. Add a new Tube Archivist channel (Jellyfin)

Tube Archivist content is **Jellyfin-only** by design. After adding a channel in the TA UI, wait for the next `:00` (NFO sync) + `:30` (image sync) tick, then ask the agent to "trigger a Jellyfin library refresh". The channel appears in the Jellyfin YouTube library automatically. First time only: in the Jellyfin UI, point a library section at `/media/downloads/tube-archivist/` and select metadata reader `Nfo` + image source `Folder image`. Plex is intentionally not configured for YouTube.

## Recovery from a failed batch

The move-only invariant means files still exist somewhere — either at the source or the destination. Never assume data loss; always search first.

```bash
# Search both source and destination roots for the basename
BASENAME='<filename without extension>'
kubectl -n media exec deploy/jellyfin -- find /media/data -name "*${BASENAME}*" 2>/dev/null
kubectl -n media exec deploy/jellyfin -- find /media -path "*/downloads/jdownloader/*${BASENAME}*" 2>/dev/null

# Inspect the failing Job's log — every mv is logged
kubectl -n media logs job/media-organize-<id> | grep -E '^(mv |VERIFY |CLEANUP )'
```

To reverse a move: read the `mv src dst` log line, then run `mv dst src` (hard-coded paths, no globs) from a debug pod that mounts `plex-media-smb`. Then trigger a Plex/Jellyfin rescan to re-index.

For a wider recovery (multiple files affected), surface the situation to the user with the inventory before any reversal — the prior incident (2026-04-26, see `docs/sops/storage-safety.md`) was made worse by reflexive cleanup.

## How to read `media-library-current.md`

The report has four sections per library:

1. **Compliance summary** — percentages against the SOP thresholds.
2. **Worst offenders** — top-N items by missing-artifact count.
3. **Orphan sidecars** — `.nfo` / `.jpg` files with no matching media file. Surface to user before deletion.
4. **Drift** — `.nfo` whose `<title>` or `<year>` no longer matches the filename. Indicates a manual rename without sidecar update.

Compliance percentages below the threshold trigger a Prometheus alert if they persist > 24 h.

## Troubleshooting

| Symptom | First check |
|---|---|
| Audit Job won't start | `kubectl -n media describe cronjob media-library-audit` — look for image-pull or PVC binding errors. |
| `mv` fails with "Permission denied" | Confirm Job runs as 1000:1000 (matching CIFS mount `uid=1000,gid=1000,noperm`). |
| Plex doesn't pick up local poster | Item must be in its own folder. Re-check layout compliance for that item. |
| TA channel missing in Jellyfin | TA `:00`/`:30` jobs haven't completed yet — check `kubectl -n download get jobs \| grep tube-archivist`. Then trigger a Jellyfin rescan. |
| Agent reports "0 items moved" but downloads dir not empty | Items still match no classification rule — agent asks via `AskUserQuestion`; check there are no pending questions. |
| TMDb sidecar fetch returns HTTP 401 | Token in `media-manager-tokens.sops.yaml` is the v4 Bearer JWT. `sidecar.py` uses v3 query-param API. Replace with the short "API Key (v3 auth)" from <https://www.themoviedb.org/settings/api>. |
| `_duplicates/` items showing up in Plex/Jellyfin Movies library | The `_` prefix only excludes `audit.py`; servers walk it. Either move `_duplicates/` outside `Movies/`, or add an exclusion path in each library's UI. |

## Common gotchas (from real bulk-organise session)

### Wrong TMDb match (search returns sequel for query of the original)

**Symptom**: `sidecar.py` returns a TMDb match for a sequel/related movie, not the title queried — e.g. searching for `<franchise>` returns `<franchise>: <newer-sequel>`.

**Cause**: TMDb's search endpoint returns multiple results sorted by relevance, but our retry scripts ranked by **popularity**, which favors newer/blockbuster sequels.

**Fix**: use the smarter scoring in newer scripts — exact title match (10000 + popularity) > startswith (5000 + pop) > contains (1000 + pop) > popularity. Re-fetch the offending item with a year-restricted query (`&year=YYYY` is very accurate when year is correct).

### Resolution mistaken for year (`Movie (1080)`)

**Symptom**: a folder named `Movie (1080)` shows up after the migration script. The audit reports year mismatches between folder year (1080) and nfo year (real).

**Cause**: original filename had no year token, so `(1080)` (resolution leak) was caught by an over-permissive `\((\d{4})\)` regex.

**Fix**: rename folder to use the nfo's real year. The `media-cleanup-nfos` Job (in this session) auto-handled folders where folder year ∈ {360, 480, 720, 1080, 1440, 2160} by reading the nfo's `<year>` and renaming.

### Multi-part DVDRip detection (`Movie -a.avi` + `Movie -b.avi`)

**Symptom**: two folders for what looks like the same movie, or one folder with both `-a` and `-b` files inside.

**Cause**: pre-2010s German DVDRips were commonly split across two CDs. Both halves are needed for the full movie.

**Fix**: merge into one folder using **Plex multi-part naming**: `<title> (Year)/<title> (Year) - cd1.avi` and `... - cd2.avi`. Plex+Jellyfin play them as one continuous movie.

### Auto-generated `movie.nfo` alongside `<folder>.nfo`

**Symptom**: each folder has TWO nfo files: `<folder>.nfo` (your canonical) and `movie.nfo` (Plex/Jellyfin auto-write).

**Cause**: both servers write `movie.nfo` during their library scans when the existing nfo doesn't satisfy them, OR when the user clicks "Refresh metadata" in the UI.

**Fix**: keep `<folder>.nfo` (matches the SOP), delete `movie.nfo` periodically. The cleanup is now part of the standard NFO maintenance pass.

### Same-name folders containing different movies

**Symptom**: two folders named the same except for the year, `ffprobe` shows different runtimes inside each.

**Cause**: a previous bulk-rename mis-matched movie content to the wrong canonical name. Common pair: a sequel got the parent franchise's name applied to it.

**Fix**: ffprobe both, identify by canonical runtime (look up the actual movie's runtime; a 23-minute delta is a strong signal you have two different cuts/movies), rename folders to match actual content. Disambiguate via swap (rename one to a temp name, then rename other to free name, then rename temp back).

### Wrong TMDb match (German anime BDRiP releases)

**Symptom**: a folder name like `<title> GERMAN 5 1 AC3 ANiME BDRiP (1080)` returns no TMDb match.

**Cause**: filename has so many release tokens that the cleaned query is dominated by audio-channel + container noise (`5 1 ANiME (1080)`).

**Fix**: aggressive noise-token stripping (extend the noise regex), strip distributor prefixes, try with `language=de-DE`, drop trailing single-digit numbers (audio channel artifacts), recognise `(1080)` as resolution-not-year.

## See also

- `docs/sops/media-library-standards.md` — the standard
- `docs/sops/storage-safety.md` — CIFS PVC pre-flight (mandatory)
- `runbooks/health-check.md` — cluster health context
- `runbooks/version-check.md` — Plex / Jellyfin / Tube Archivist upgrade path
