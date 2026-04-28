# SOP: Media Library Standards (Plex + Jellyfin + Tube Archivist)

> Description: Canonical on-disk layout, naming, sidecar/NFO conventions, and intake workflow for the shared Plex/Jellyfin/Tube Archivist media library.
> Version: `2026.04.27`
> Last Updated: `2026-04-27`
> Owner: `media-manager`

| Field | Value |
|---|---|
| **Version** | 2026.04.27 |
| **Last Updated** | 2026-04-27 |
| **Owner** | media-manager |
| **Applies to** | All content under `//${NAS_HOSTNAME}/media/data/` consumed by Plex (`media/plex`) and Jellyfin (`media/jellyfin`); JDownloader intake at `//${NAS_HOSTNAME}/media/downloads/jdownloader`; Tube Archivist content at `//${NAS_HOSTNAME}/media/downloads/tube-archivist` (bridged into the Plex view). |

---

## Description

This SOP defines the canonical on-disk layout for the shared media library. Both Plex and Jellyfin parse the same Kodi-derived layout, so one standard serves both servers and switching between them is zero-cost.

The standard is **nested**: every movie, show, and season has its own folder. Sidecar metadata (`.nfo`) and artwork (`poster.jpg`, `fanart.jpg`) live next to the media they describe. Server-side caches (transcoder output, chapter previews) stay in each app's config PVC and are out of scope here.

This SOP is the source of truth for the `media-manager` sub-agent (`.claude/agents/media-manager.md`) and the `library-tools` GitOps app (`kubernetes/apps/media/library-tools/`).

- Scope: layout, naming, sidecar conventions, dedup decisions, audit thresholds, intake-from-jdownloader flow, Tube Archivist→Plex bridge.
- Prerequisites: read `docs/sops/storage-safety.md` first — every operation in this SOP touches a CIFS share whose blast radius is the whole share.
- Out of scope: Plex/Jellyfin server-side configuration, transcoder tuning, library-section creation in the Plex/Jellyfin UI.

## Overview

| Setting | Value |
|---|---|
| Library root (NAS view) | `/mnt/nas/media/data/` |
| Library root (SMB share) | `//${NAS_HOSTNAME}/media/data/` |
| Plex pod mount | `/data/data/` (PVC `plex-media-smb`, StorageClass `cifs-plex-media`, `reclaim: Retain`) |
| Jellyfin pod mount | `/media/data/` (PVC `jellyfin-media-smb`, StorageClass `cifs-jellyfin-media`, `reclaim: Retain`) |
| JDownloader intake | `/mnt/nas/media/downloads/jdownloader/` (pod path `/output`, PVC `jdownloader-downloads`) |
| Tube Archivist source | `/mnt/nas/media/downloads/tube-archivist/` (pod path `/youtube`, PVC `tube-archivist-youtube`) |
| Sections (Plex) | `Movies`, `TV Shows`, `Music` |
| Sections (Jellyfin) | `Movies`, `TV Shows`, `Music`, plus a `YouTube` library pointed directly at `/media/downloads/tube-archivist/` |

---

## Blueprints

N/A — this SOP defines a file/directory standard, not a Kubernetes blueprint. The GitOps app that enforces it is `kubernetes/apps/media/library-tools/` (audit + organize + sidecar Jobs). YouTube content already gets correct sidecars from the existing `tube-archivist-{nfo,image}-sync` CronJobs (`kubernetes/apps/download/tube-archivist/app/`).

---

## Operational Instructions

### Layout — nested

```
data/
├── Movies/
│   └── Title (Year)/                                   # one folder per movie
│       ├── Title (Year).mkv
│       ├── Title (Year).nfo
│       ├── poster.jpg                                  # folder-level poster
│       ├── fanart.jpg                                  # folder-level backdrop
│       └── extras/                                     # optional: trailers, behind-the-scenes
│
├── TV Shows/
│   └── Show Name/                                      # one folder per show
│       ├── tvshow.nfo                                  # series metadata
│       ├── poster.jpg                                  # series poster
│       ├── fanart.jpg                                  # series backdrop
│       ├── banner.jpg                                  # optional
│       ├── Season 01/                                  # season subfolder
│       │   ├── season01-poster.jpg                     # optional per-season art
│       │   ├── Show Name - S01E01 - Episode Title.mkv
│       │   ├── Show Name - S01E01 - Episode Title.nfo
│       │   └── Show Name - S01E01 - Episode Title-thumb.jpg
│       └── Season 02/ …
│
├── Music/
│   └── Artist Name/
│       ├── artist.jpg
│       └── Album (Year)/
│           ├── 01 - Track.flac
│           ├── folder.jpg                              # album cover
│           └── album.nfo
│
# YouTube content lives outside data/ — at /media/downloads/tube-archivist/UC*/.
# Jellyfin scans that path directly via the existing TA NFO+image sync sidecars
# (folder.jpg / backdrop.jpg / banner.jpg / .nfo). Plex is intentionally not
# configured for YouTube — Jellyfin is the authoritative viewer for it.
```

### Naming rules

- **Movies**: filename = folder name = `Title (Year)`. Year in parens (4 digits, **must be in range 1900–2099** — `(1080)` / `(720)` looks like a year but is the resolution; year regex must constrain to `(19[0-9]{2}|20[0-9]{2})`). Drop release suffixes (e.g. `.GERMAN.DL.720p.WEB.h264-WAYNE`, `.BDRip.x264-BLOODY`).
- **TV episodes**: `Show Name - S01E01 - Episode Title.mkv` inside `TV Shows/<Show>/Season 01/`. Episode title is preferred; if unknown, `Show Name - S01E01.mkv` is acceptable.
- **Multi-part movies** (DVDRips split across CDs, originally `-a.avi`/`-b.avi`): merge into one folder using **Plex multi-part naming**: `Title (Year)/Title (Year) - cd1.avi`, `... - cd2.avi`. Plex+Jellyfin treat them as one continuous movie (https://support.plex.tv/articles/200381043-multi-part-movies/).
- **YouTube**: filename shape is whatever Tube Archivist writes (`<channel>_YYYYMMDD_<title>.mp4`). Jellyfin scans `/media/downloads/tube-archivist/UC*/` directly — no rename or migration needed.
- **Umlauts**: use proper `ä`, `ö`, `ü`. CIFS on this NAS handles UTF-8 cleanly — do not transliterate to `ae`/`oe`/`ue`.
- **Sidecars**: same basename as the media file:
  - Movie: `Title (Year).nfo` next to the file; folder-level `poster.jpg` + `fanart.jpg`.
  - Episode: `Show - S01E01 - Title.nfo` + `Show - S01E01 - Title-thumb.jpg` next to the file.
  - Series (folder-level): `tvshow.nfo`, `poster.jpg`, `fanart.jpg`, optional `banner.jpg`, optional `season01-poster.jpg`.

### Sidecar conventions (Plex + Jellyfin both honour these)

- Plex local-asset matching docs: <https://support.plex.tv/articles/200220677-local-media-assets-movies/> and <https://support.plex.tv/articles/200220717-local-media-assets-tv-shows/>.
- Jellyfin movies docs: <https://jellyfin.org/docs/general/server/media/movies/> and shows: <https://jellyfin.org/docs/general/server/media/shows/>.
- NFO schema (Kodi/XBMC): minimum movie fields `<title>`, `<year>`, optional `<uniqueid type="tmdb">`. Minimum episode fields `<season>`, `<episode>`, `<title>`, `<aired>`. Minimum series `tvshow.nfo`: `<title>`, `<year>`, optional `<uniqueid type="tvdb">`.
- **One nfo per folder.** Plex/Jellyfin auto-write `movie.nfo` alongside any existing `<folder>.nfo` during their library scans. Both servers read either, but having two creates drift. **Standard: keep `<folder>.nfo` (matches the SOP), periodically delete the auto-generated `movie.nfo`.** A scheduled cleanup is in the audit CronJob's plan.

### TMDb integration (the v3-vs-v4 trap)

`sidecar.py` calls `https://api.themoviedb.org/3/search/...?api_key=<KEY>&query=...`. The `&api_key=` URL parameter requires a **v3 API key** (32-char hex string). TMDb's newer **v4 Read Access Token** is a JWT-style long string and is sent as `Authorization: Bearer <TOKEN>` — it does NOT work as a query param and returns HTTP 401. When populating `media-manager-tokens.sops.yaml`, use the **"API Key (v3 auth)"** field from <https://www.themoviedb.org/settings/api>, not the v4 token.

### Dedup / quality decisions (German scene ranking)

Default release preference (highest to lowest quality at equal resolution):

```
4sf / DisneyHD  >  WAYNE  >  SAUERKRAUT  >  AVTOMAT WEBRip  >  older DVDRip
```

This ranking is a tie-breaker only. Always probe before any replace — file size alone misleads. Probe with:

```bash
ffprobe -v error -select_streams v:0 \
  -show_entries stream=width,height \
  -show_entries format=duration,bit_rate,size \
  -of default=noprint_wrappers=1 FILE
```

Decision rule: prefer higher bitrate, native film fps (`23.976` over PAL `25`), longer/complete duration. Never overwrite without surfacing the probe diff to the user for explicit go/no-go.

### Audit thresholds

The `library-tools` audit CronJob computes a per-item compliance record. Library is considered healthy when:

| Section | Layout ✓ | NFO ✓ | Poster ✓ | Fanart ✓ |
|---|---|---|---|---|
| Movies | ≥ 99% | ≥ 95% | ≥ 95% | ≥ 90% |
| TV Shows (series-level) | ≥ 99% | ≥ 95% | ≥ 95% | ≥ 90% |
| TV Shows (episode-level) | ≥ 99% | ≥ 80% | n/a | n/a |
| Music | ≥ 95% | ≥ 80% | ≥ 80% (folder.jpg) | n/a |
| YouTube (Jellyfin-only) | n/a — TA-managed | ≥ 99% | ≥ 99% (folder.jpg) | ≥ 99% (backdrop.jpg) |

Poster minimum: 600 px wide, aspect ratio ≈ 2:3. Fanart minimum: 1280 px wide, aspect ratio ≈ 16:9.

### Intake from JDownloader

The `media-manager` sub-agent owns the loop. Summary:

1. List `/mnt/nas/media/downloads/jdownloader/` via a debug pod that mounts `jdownloader-downloads`.
2. Classify each item: TV iff filename matches `S\d{2}E\d{2}` (case-insensitive); else movie; else escalate.
3. ffprobe each candidate; if a same-name target exists, build a quality-diff table.
4. Compute target paths under `/mnt/nas/media/data/{Movies,TV Shows}/...` per the nested layout.
5. Render the move plan + conflicts as a table; surface to user for go/no-go.
6. On approval: ephemeral Job creates destination folders, runs `mv` (atomic, same CIFS mount), writes/refreshes sidecars, fetches missing artwork from TMDb / TVDb.
7. Verify each target exists with `size > 0` (sample-stat in the same Job).
8. Cleanup: `rm -rf` the **specific** JDownloader subdirectory whose contents are now fully verified at destination. Hard-coded path. Never glob the share root.
9. Trigger Plex section rescan + Jellyfin library refresh for the affected sections only (delegated to `cluster-ops-agent`).
10. Report counts + any "unmatched" items in Plex/Jellyfin after rescan.

### Migration: existing flat layout → nested

The library was previously organised in flat form (movies flat in `Movies/`, episodes flat under each show with no `Season XX/` subdirs). The agent migrates one batch at a time — default unit is one alphabetical letter for movies, one show for TV — never the whole library at once.

Per batch: `mkdir` destination → `mv` media + `.nfo` → run `sidecar.py` to materialise `poster.jpg` + `fanart.jpg` in the new folder → verify `size > 0` → rescan affected section → pause for user spot-check → next batch.

### Tube Archivist (Jellyfin-only)

Tube Archivist writes channel-level `.nfo` + `folder.jpg` / `backdrop.jpg` / `banner.jpg` into its own PVC via two CronJobs (`tube-archivist-metadata-sync` at `:00`, `tube-archivist-image-sync` at `:30`). Jellyfin's media mount has `subdir: /` so Jellyfin sees the path natively. Configure a Jellyfin library section pointing at `/media/downloads/tube-archivist/` once; new channels appear automatically.

Plex is **intentionally not configured** for YouTube content. The audit script does not walk `data/YouTube/` (it does not exist) and does not score Tube Archivist channels — Jellyfin owns that section end-to-end.

---

## Examples

> Examples use placeholders. **Real media titles must never appear in this repo** — see Security Check below.

### Example A — One movie, fully compliant

```
data/Movies/Movie Title (Year)/
├── Movie Title (Year).mkv
├── Movie Title (Year).nfo
├── poster.jpg
├── fanart.jpg
└── extras/
    └── Movie Title (Year) - Trailer.mkv
```

`Movie Title (Year).nfo` (minimal Kodi schema):

```xml
<movie>
  <title>Movie Title</title>
  <year>YYYY</year>
  <uniqueid type="tmdb">000000</uniqueid>
</movie>
```

### Example B — One TV show with two seasons

```
data/TV Shows/Show Name/
├── tvshow.nfo
├── poster.jpg
├── fanart.jpg
├── banner.jpg
├── Season 01/
│   ├── season01-poster.jpg
│   ├── Show Name - S01E01 - Episode Title.mkv
│   ├── Show Name - S01E01 - Episode Title.nfo
│   └── Show Name - S01E01 - Episode Title-thumb.jpg
└── Season 02/
    ├── Show Name - S02E01 - Episode Title.mkv
    └── Show Name - S02E01 - Episode Title.nfo
```

### Example C — One Tube Archivist channel (Jellyfin view, TA-managed)

The TA CronJobs already write this layout — no manual action required.

```
downloads/tube-archivist/UC<channel-id>/
├── artist.nfo                             # written by tube-archivist-nfo-sync
├── tvshow.nfo                             # written by tube-archivist-nfo-sync
├── folder.jpg                             # poster — written by tube-archivist-image-sync
├── backdrop.jpg                           # fanart — written by tube-archivist-image-sync
├── banner.jpg                             # written by tube-archivist-image-sync
├── <channel>_YYYYMMDD_<title>.mp4
└── <channel>_YYYYMMDD_<title>.nfo
```

Point a Jellyfin library at `/media/downloads/tube-archivist/` and these are picked up via the `Nfo` metadata reader + the embedded image extractor.

---

## Verification Tests

### Test 1 — Plex picks up local poster without internet

```bash
# Pick any movie folder you've just sidecar'd (do NOT write its name into the repo)
# Open Plex UI → Movies → that item → ⋯ → Refresh Metadata → Force Refresh
# Cut WAN briefly (or block plex.tv from the cluster) and re-trigger refresh
```

Expected:
- The item still shows the local `poster.jpg` and `fanart.jpg` after the forced refresh.
- Plex log line `Local Media Assets` referenced as the source.

If failed:
- Confirm `poster.jpg` is in the **per-movie folder**, not in `Movies/` directly.
- Plex Settings → Movies library → Edit → Advanced → ensure `Local Media Assets` agent is enabled and high in priority.

### Test 2 — Jellyfin picks up `.nfo` instead of remote provider

```bash
# Disable all remote metadata providers in Jellyfin: Settings → Libraries → Movies → Metadata downloaders → uncheck all
# Refresh metadata for a single item
```

Expected:
- Title, year, plot, IDs all populate from the on-disk `.nfo`.
- Re-enabling remote providers does not change displayed metadata.

If failed:
- Validate `.nfo` parses as XML: `xmllint --noout '<file>.nfo'`.
- Confirm `Nfo` plugin is enabled in Jellyfin's metadata reader list.

### Test 3 — Audit CronJob compliance baseline

```bash
kubectl -n media create job --from=cronjob/media-library-audit media-audit-test-1
kubectl -n media wait --for=condition=Complete job/media-audit-test-1 --timeout=10m
kubectl -n media logs job/media-audit-test-1 | tail -50
```

Expected:
- Job completes successfully.
- Output report exists at `runbooks/media-library-current.md` (auto-generated, gitignored) with per-section compliance percentages.
- All percentages meet or exceed the thresholds in the table above (after the migration + sidecar backfill is done).

If failed:
- Inspect job logs for individual item errors.
- Re-run with `DEBUG=1` env to get per-item compliance records.

---

## Troubleshooting

| Symptom | Likely Cause | First Fix |
|---|---|---|
| Plex shows generic poster despite `poster.jpg` being on disk | Item not in its own folder, or Local Media Assets agent disabled | Move the `.mkv` into a `Title (Year)/` folder; verify Plex agent priority |
| Jellyfin keeps re-downloading metadata | `.nfo` malformed or `Nfo` reader disabled | `xmllint` the nfo; enable `Nfo` in metadata downloaders |
| Episode shows up under "Specials" | Filename missing `S\d{2}E\d{2}` pattern | Rename to `Show - S01E01.mkv` or correct the malformed pattern |
| Two identical movies showing in library | Item exists at both flat path and nested path | Run audit, identify drift, remove the flat duplicate after `size > 0` verification |
| Tube Archivist videos missing in Plex | Bridge CronJob did not run / channel not yet processed by TA's metadata-sync | Check TA `:00`/`:30` jobs first, then run the `:45` bridge manually |
| `mv` fails with "Permission denied" on CIFS | UID/GID mismatch with mount options | Mount uses `uid=1000,gid=1000,noperm` — Job must run as 1000:1000 |

```bash
# Quick health probe
kubectl -n media get cronjob media-library-audit
kubectl -n media get jobs | grep media-library | tail -5
kubectl -n media logs $(kubectl -n media get pods -l job-name --no-headers | awk '{print $1}' | head -1)
```

---

## Diagnose Examples

### Diagnose Example 1 — Bulk move appears to have lost files

```bash
# Recover quickly: the move-only invariant means files still exist somewhere.
# Search both source and destination roots for the basename.
kubectl -n media exec deploy/jellyfin -- find /media/data -name '*<basename>*' 2>/dev/null
kubectl -n media exec deploy/jellyfin -- find /media -path '*/downloads/jdownloader/*<basename>*' 2>/dev/null
```

Expected:
- The file appears at exactly one location (either old or new). If neither, escalate immediately — possible data loss.

If unclear:
- Check the `library-tools` Job logs for the specific batch: `kubectl -n media logs job/media-organize-<id>`. The script logs every `mv src dst` line.

### Diagnose Example 2 — Plex / Jellyfin item count drops after a migration batch

```bash
# Compare item count before/after via Plex API (token redacted, do not echo to logs)
PLEX_SECTION_ID=1   # set via library-tools secret
kubectl -n media exec sts/plex-plex-media-server -- \
  curl -s "http://localhost:32400/library/sections/${PLEX_SECTION_ID}/all?X-Plex-Token=${PLEX_TOKEN}" | \
  grep -oE '<Video ' | wc -l
```

Expected:
- Item count after rescan = item count before + (intake additions) - (deduped replacements).

If unclear:
- Open Plex Web → that library → "Manage Library" → look for "Unmatched" items. Rescan single offending item to surface the parser error.

---

## Health Check

```bash
# Daily audit job last-run status
kubectl -n media get cronjob media-library-audit -o json | python3 -c "
import sys, json, datetime
c = json.load(sys.stdin)
last = c['status'].get('lastSuccessfulTime', 'never')
print(f'Last successful audit: {last}')
"

# Compliance summary (read the auto-generated report)
head -40 runbooks/media-library-current.md 2>/dev/null || echo 'no audit report yet'

# Confirm both apps see the share
kubectl -n media exec sts/plex-plex-media-server -- ls /data/data | head
kubectl -n media exec deploy/jellyfin -- ls /media/data | head
```

Expected:
- Last successful audit within the last 24 h.
- All section compliance percentages meet thresholds in the Overview table.
- Both Plex and Jellyfin see `Movies/`, `TV Shows/`, `Music/` at the share root. Jellyfin additionally has a YouTube library pointing at `/media/downloads/tube-archivist/`.

---

## Security Check

This repo is **public**. Two distinct redaction concerns:

1. No plaintext credentials.
2. **No real media titles** — listing what the user owns is both a privacy leak and a copyright-exposure vector. Examples in this SOP, the agent file, the runbook, the audit report, commit messages, and PR bodies must use placeholders (`<movie>`, `<show>`, `Title (Year)`, `Show - SXXEYY`).

```bash
# 1. No plaintext tokens in repo
grep -rE 'X-Plex-Token|JELLYFIN_API_KEY|TMDB_API_KEY|TVDB_API_KEY' kubernetes/ docs/ runbooks/ \
  --include='*.yaml' --include='*.md' | grep -v 'sops:' | grep -v 'enc:'

# 2. Secret is encrypted
head -20 kubernetes/apps/media/_secrets/media-manager-tokens.sops.yaml | grep -q 'sops:' \
  && echo OK || echo MISSING

# 3. CronJob uses the secret via envFrom, not hardcoded values
grep -A3 'env\|envFrom' kubernetes/apps/media/library-tools/app/*.yaml | grep -E 'name:|key:'

# 4. No real media titles in committed text. The audit report runbooks/media-library-current.md
#    is gitignored — any title leak would have to come from docs/runbooks/agent files,
#    which use placeholders only. Spot-check by sampling 'rg' on a known-bad pattern set
#    (specific to the user's library — keep the pattern file local, not in the repo).
git ls-files docs/sops/media-library-standards.md \
              .claude/agents/media-manager.md \
              runbooks/media-manager.md
# Inspect each manually; only placeholders (Title (Year), Show Name, Channel Name) must appear.
```

Expected:
- No plaintext token strings in any file.
- `media-manager-tokens.sops.yaml` exists and contains a `sops:` metadata block.
- Job specs reference the secret via `envFrom: secretRef` or `env: valueFrom: secretKeyRef`, never inline values.
- No real media titles in any committed file. Only placeholders.

---

## Rollback Plan

Every layout / migration / intake operation is `mv`-only on the same CIFS mount. To roll back:

```bash
# 1. Identify the source and destination of the move from the Job log
kubectl -n media logs job/media-organize-<id> | grep '^mv '

# 2. Reverse the rename. Hard-code paths from the log; no globs.
kubectl -n media debug -it node/k8s-nuc14-01 \
  --image=busybox --target=plex-plex-media-server -- \
  sh -c 'mv "/data/<dst>" "/data/<src>"'

# 3. Trigger Plex + Jellyfin rescan via cluster-ops-agent
```

For the GitOps pieces (library-tools app): `git revert <commit>` on the introducing commit removes them cleanly. Plex and Jellyfin always re-scan from the source of truth on disk, so server-side state is self-healing.

---

## References

- `.claude/agents/media-manager.md` — sub-agent that owns enforcement
- `runbooks/media-manager.md` — operator-facing flows
- `kubernetes/apps/media/library-tools/` — GitOps app implementing audit + organize + sidecar Jobs
- `kubernetes/apps/download/tube-archivist/app/{metadata,image}-sync-{configmap,cronjob}.yaml` — TA's own sidecar generators (Jellyfin reads them directly)
- `kubernetes/apps/media/{plex,jellyfin}/app/helmrelease.yaml` — server deployments and PVC mounts
- `kubernetes/apps/download/{jdownloader,tube-archivist}/app/` — intake sources
- `docs/sops/storage-safety.md` — CIFS PVC safety rules (mandatory pre-flight)
- `docs/sops/SOP-TEMPLATE.md` — SOP structure
- Plex local-asset docs — <https://support.plex.tv/articles/200220677-local-media-assets-movies/>
- Jellyfin movies/shows docs — <https://jellyfin.org/docs/general/server/media/movies/>

---

## Version History

- `2026.04.27`: Initial standard. Nested layout. Migration workflow from prior flat layout. Tube Archivist→Plex bridge. Audit thresholds.
