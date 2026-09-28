# SOP: Media Library Standards (Plex + Jellyfin + Tube Archivist)

> Description: Canonical on-disk layout, naming, sidecar/NFO conventions, and intake workflow for the shared Plex/Jellyfin/Tube Archivist media library.
> Version: `2026.09.28`
> Last Updated: `2026-09-28`
> Owner: `media-manager`

| Field | Value |
|---|---|
| **Version** | 2026.09.28 |
| **Last Updated** | 2026-09-28 |
| **Owner** | media-manager |
| **Applies to** | All content under `//${NAS_HOSTNAME}/media/data/` consumed by Plex (`media/plex`) and Jellyfin (`media/jellyfin`); JDownloader intake at `//${NAS_HOSTNAME}/media/downloads/jdownloader`; Tube Archivist content at `//${NAS_HOSTNAME}/media/downloads/tube-archivist` (surfaced in Jellyfin only — Plex is intentionally not configured for YouTube). |

---

## Description

This SOP defines the canonical on-disk layout for the shared media library. Both Plex and Jellyfin parse the same Kodi-derived layout, so one standard serves both servers and switching between them is zero-cost.

The standard is **nested**: every movie, show, and season has its own folder. Sidecar metadata (`.nfo`) and artwork (`poster.jpg`, `fanart.jpg`) live next to the media they describe. Server-side caches (transcoder output, chapter previews) stay in each app's config PVC and are out of scope here.

This SOP is the source of truth for the `media-manager` sub-agent (`.claude/agents/media-manager.md`) and the `library-tools` GitOps app (`kubernetes/apps/media/library-tools/`).

- Scope: layout, naming, sidecar conventions, dedup decisions, audit thresholds, intake-from-jdownloader flow, Tube Archivist surfacing (Jellyfin-only).
- Prerequisites: read `docs/sops/storage-safety.md` first — every operation in this SOP touches a CIFS share whose blast radius is the whole share.
- Out of scope: Plex/Jellyfin server-side configuration, transcoder tuning, library-section creation in the Plex/Jellyfin UI.

## Overview

| Setting | Value |
|---|---|
| Library root (NAS view) | `/mnt/nas/media/data/` |
| Library root (SMB share) | `//${NAS_HOSTNAME}/media/data/` |
| Plex pod mount | `/data/data/` (PVC `plex-media-smb`, StorageClass `cifs-plex-media`, `reclaim: Retain`) |
| Jellyfin pod mount | `/media/data/` (PVC `jellyfin-media-smb`, StorageClass `cifs-jellyfin-media`, `reclaim: Retain`) |
| JDownloader intake | `/mnt/nas/media/downloads/jdownloader/` (JDownloader pod path `/output`, PVC `jdownloader-downloads`; library-tools jobs reach it as `/data/downloads/jdownloader` on the single `plex-media-smb` share-root mount) |
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

### Jellyfin API auth (the legacy-header trap, 12.x)

Send the key as **`Authorization: MediaBrowser Token="<key>"`** — nothing else.
Jellyfin guards four *legacy* forms behind `EnableLegacyAuthorization`: the
`X-Emby-Token` header, the `X-MediaBrowser-Token` header, the `api_key=` query
parameter and the `X-Emby-Authorization` header. Jellyfin **12.x** ships the
`DisableLegacyAuthorization` migration, which flips that flag to `false` in
`system.xml` on first boot, after which every one of those forms returns
**HTTP 401** — indistinguishable, from the caller's side, from a wrong key. The
`Authorization: MediaBrowser Token=…` header (and the `ApiKey=` query
parameter, capital A/K) are not guarded and keep working.

Measured 2026-09-22 against the live server (`10.11.11`, legacy still enabled):
modern header → 200, `X-Emby-Token` → 200, `api_key=` → 200, no auth → 401.
The 200s on the legacy forms are **not** a reason to use them — they end at the
12.x upgrade (plan `jellyfin-12.1`, gate G3). All four call sites in
`library-tools`' `scripts-configmap.yaml` (`rescan.py`, `metadata_coverage.py`,
`per_item_refresh.py`) were switched to the header form in `5b8193c9`. Any new
Jellyfin client — a CronJob, a dashboard, an agent skill — must use the header
form from day one; do not re-enable legacy authorization on the server to
accommodate one.

```bash
# the shape, key kept in-shell (secret media-manager-tokens, key JELLYFIN_API_KEY)
curl -s -H "Authorization: MediaBrowser Token=\"$JF_KEY\"" "http://<jellyfin-host>:8096/System/Info"
```

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

Decision rule: prefer higher bitrate, native film fps (`23.976` over PAL `25`), longer/complete duration. Nothing is ever overwritten: the automatic intake (below) applies a fixed rule set and displaces the loser into `_duplicates/`; anything outside that rule set (an fps mismatch, a duration off by more than 2%, a mixed resolution/bitrate verdict) is left in the intake for a human.

### Duplicate quarantine — `_duplicates/` requires a `.plexignore`, not just the prefix

When a dedup decision keeps one release and quarantines the loser, the loser moves to `_duplicates/<original relative path>/` under the section root (e.g. `Movies/_duplicates/Title (Year) - old-release/`) rather than being deleted outright, so it's recoverable if the decision is later reversed.

**The `_` prefix is a naming convention only — it has no effect on Plex or Jellyfin scanning.** Confirmed 2026-07-05: Plex's built-in "Special Keyword File/Folder Exclusion" auto-skips only `sample`, `extras`, `samples`, `bonus`, `bonus disc` (<https://support.plex.tv/articles/201381883-special-keyword-file-folder-exclusion/>) — nothing about a leading underscore or any custom prefix. Left unaddressed, Plex/Jellyfin will walk `_duplicates/` like any other folder, match it against metadata, and surface it as a second version (or a second item) in the library — exactly the failure the daily `plex-fs-classifier` CronJob's `skip_dir_leftover` bucket exists to catch (`kubernetes/apps/media/library-tools/app/plex-fs-classifier-cronjob.yaml`).

**The actual fix**: write a `.plexignore` file (Plex's real gitignore-style scan-exclusion mechanism, read at each directory level during a scan) at each affected section root:

```
# <section root>/.plexignore, e.g. Movies/.plexignore
_duplicates/
_duplicates/**
_archive/
_archive/**
```

Apply via an ephemeral Job mounting the existing `plex-media-smb` PVC (same pattern as `organize.py` — write-only, no deletes), then force a Plex section refresh via `cluster-ops-agent` (`POST /library/sections/{id}/refresh?force=1`) so the new ignore rules are honored on the next directory walk. Jellyfin has its own equivalent ignore mechanism per library (check current Jellyfin version's docs — do not assume it matches Plex's `.plexignore` syntax) — verify separately if Jellyfin's Movies/TV Shows libraries also walk `_duplicates/`.

**Known related gap**: the Plex "Movies" section (id 1) is rooted at `/data/data` (the share's data root), not `/data/data/Movies`. Every item does live under `Movies/`, so the broad root is tidiness, not a bug, and a `.plexignore` at the `Movies/` level still works (ignore rules cascade from wherever the file sits). **Do not fix it through the API by adding `/data/data/Movies` and removing the root.** Plex ties every media item to the location id it was first scanned under (`media_items.section_location_id`), and a scan of a newly added nested location does not move items to it (verified 2026-09-28: 501/501 items stayed on the root id after a folder-scoped scan of the new location). Removing the root would leave every item without a location, and with `autoEmptyTrash` on they would be deleted. The only in-place fix is a DB edit with Plex scaled to 0 (move the location ids, then rewrite `section_locations.root_path`), after a DB snapshot. That needs an operator go/no-go.

### Audit thresholds

The `library-tools` audit CronJob computes a per-item compliance record. Library is considered healthy when:

| Section | Layout ✓ | NFO ✓ | Poster ✓ | Fanart ✓ |
|---|---|---|---|---|
| Movies | ≥ 99% | ≥ 95% | ≥ 95% | ≥ 90% |
| TV Shows (series-level) | ≥ 99% | ≥ 95% | ≥ 95% | ≥ 90% |
| TV Shows (episode-level) | ≥ 99% | ≥ 80% | n/a | n/a |
| Music | ≥ 95% | ≥ 80% | ≥ 80% (folder.jpg, ≥ 500 px square) | n/a |
| YouTube (Jellyfin-only) | n/a — TA-managed | ≥ 99% | ≥ 99% (folder.jpg) | ≥ 99% (backdrop.jpg) |

Poster minimum: 600 px wide, aspect ratio ≈ 2:3. Fanart minimum: 1280 px wide, aspect ratio ≈ 16:9.

**Album covers are square and have their OWN minimum: 500 px, aspect ratio ≈ 1:1.**
Decided 2026-09-06; before that the Music row specified a folder.jpg *coverage*
target but no dimension test at all, and `check_album()` silently reused the
600 px 2:3 POSTER minimum defined above it. That is a movie-poster rule applied
to album art, and it scored the section at 2.6% (1 of 39) — a real measurement
against a threshold nobody had chosen for it. 32 of the 39 covers are exactly
500×500, the signature of a single upstream default rather than a library
problem. Because that number was also the audit's printed headline ("Worst
compliance metric"), it masked any genuine regression elsewhere for as long as
it stood. The constant is now `ALBUM_COVER_MIN_WIDTH` in
`scripts-configmap.yaml`, separate from `POSTER_MIN_WIDTH`, so the two cannot
drift into each other again.

Measured across all 39 covers when the floor was set: **2.6% (1/39) at 600 px →
94.9% (37/39) at 500 px**, against the ≥ 80% row above. The floor is
deliberately NOT vacuous — two covers (486×500, 496×500) still fail on width,
so the metric can still detect a regression. Had the test used `max(w, h)` it
would read 39/39 and detect nothing, which is the failure mode where a
threshold is "met" by being unable to fail.

### Phantom "Various Artists" artist (divergent `albumartist` tag)

**Symptom:** the Music audit shows one item unmatched (no summary/thumb/art) as a
metadata-less **"Various Artists"** artist, even though the album sits on disk
under the correct artist folder with full sidecars (`folder.jpg`, `album.nfo`).

**Cause:** Plex groups an album by its *set* of album-artist tags. A single track
with a divergent `albumartist` (classically a guest-collab track tagged to the
other artist) makes the album span two album-artists, so Plex files the whole
album under a synthetic, art-less "Various Artists" artist.

**Fix (two parts — correcting the tag alone is NOT enough):**
1. Normalize the divergent track's `albumartist`/`TPE2` so all tracks share one
   album-artist, and collapse any duplicate `<albumartist>` in `album.nfo`.
   Mount-only edit — rewrite the ID3 tag frame only; leave the audio stream and
   the track's *display* `artist` credit intact.
2. **A rescan will NOT re-parent an already-created album — not a plain scan, not
   a forced scan, not even after an mtime `touch`.** Use a Plex-native artist
   merge (no file writes):
   `PUT /library/metadata/<real-artist-ratingKey>/merge?ids=<phantom-ratingKey>`.
   The album moves under the real artist and the phantom drops (GET → 404). With
   the tags now consistent, a later rescan keeps it there; reversible via Plex
   "Split Apart". (2026-08-10: cleared the last Music unmatched item this way → 100%.)

### Automatic intake from JDownloader (media-intake-watcher)

Since 2026-09-28 new downloads are sorted **automatically**. CronJob
`media/media-intake-watcher` runs `intake.py`
(`kubernetes/apps/media/library-tools/app/`) every 30 min. It mounts the share
root once (`plex-media-smb` at `/data`); the intake is
`/data/downloads/jdownloader`, the library is `/data/data`. **Never mount the
intake as a second PVC**: two CIFS mounts are two filesystems, every rename
between them fails with `EXDEV`, and the watcher's preflight refuses to run.

Per top-level intake item (names starting with `.` or `_` are ignored):

1. **Incomplete guard.** The watcher skips (`pending`) any item that holds a
   `.rar`/`.rNN`/`.part` file, or that has anything modified in the last 30 min.
2. **Classify.**
   - `SxxEyy` on every video: **TV**.
   - One feature video and a year matching `(19|20)\d{2}`: **movie**.
   - Audio only: **music**, grouped by the album tag. Album, album-artist
     (majority), year and track tags must be consistent.
   - YouTube-looking names (`[<11-char id>]`, "youtube") are flagged and left
     in place. Tube Archivist owns YouTube.
   - Anything else is **ambiguous** and stays in the intake.
3. **Resolve the target** per the layout above.
   - Movies and shows: an existing library folder wins (normalised name
     match). If there is none, a TMDb match is used, and it must be
     confident: same year and an equal normalised title. Its German title
     names the folder. If there is no confident match, the item is ambiguous.
   - Episodes: `<Show> - SXXEYY[ - <TMDb episode title>]`.
   - Music: `Music/<Album Artist>/<Album> (<Year>)/NN - <Title>.<ext>`,
     or `D-NN - <Title>` when the album has more than one disc.
4. **Dedupe** when the target slot is occupied. The watcher ffprobes both
   files:

   | Verdict | Rule | Action |
   |---|---|---|
   | identical | same size and same probe | intake copy → `_duplicates/` |
   | better | higher resolution **and** higher bitrate, same fps, duration within ±2% (audio: higher bitrate, duration within ±2%) | **REPLACE**: library file → `_duplicates/` first, then the new file takes the same name (the extension may change). NFO and artwork stay untouched. |
   | worse | lower resolution **and** lower bitrate, same fps, duration within ±2% | intake copy → `_duplicates/` |
   | anything else | e.g. 25 vs 23.976 fps, or a mixed resolution/bitrate verdict | left in the intake as ambiguous |

5. **`_duplicates/` layout:**
   - TV: `TV Shows/_duplicates/<Show>/Season XX/<orig filename>`
   - Movies: `Movies/_duplicates/<Title (Year)> - intake dup <YYYY-MM-DD>/<orig filename>`
   - Music: `Music/_duplicates/<Artist>/<Album (Year)> - intake dup <date>/<orig>`

   The watcher also ensures the section's `.plexignore` lists `_duplicates/`
   and that `_duplicates/.ignore` exists for Jellyfin. **Nothing in
   `_duplicates/` is ever deleted automatically.** Emptying it is a manual
   operator decision.
6. **Execute** through `organize.apply_plan`:
   - Renames only. `atomic_mv` never overwrites, refuses cross-device moves
     and size-verifies every destination.
   - A REPLACE is an ordered group. If step 2 fails, step 1 is rolled back.
   - Then sidecars: `sidecar.py` for a new movie or show folder, and
     `episode_sidecar.py` (write-missing-only) for episodes.
   - For music, before the move: a stream-copy tag fix of album-artist and
     disc numbers (the audio is not re-encoded). After the move: `folder.jpg`
     (the loose cover, or the embedded art) and `album.nfo`.
   - Then `cleanup()` removes the intake folder. It first re-verifies every
     destination and refuses while any audio file or any non-sample video
     remains. Only scene junk (`.nfo`, `.txt`, `.sfv`, samples) is ever
     deleted.
7. **Rescan only the changed folders.** Plex gets
   `/library/sections/{id}/refresh?path=`. Jellyfin gets
   `POST /Library/Media/Updated` once per folder, 2s apart. Full-library
   scans were removed from `rescan.py`: they locked Jellyfin's SQLite.

**Safety stops:**
- The whole run is aborted before the first move if more than 50 items
  would move.
- The run stops if free space drops by more than 1 GiB during it. A rename
  never consumes space.
- The intake root can never be removed (`cleanup` and `assert_safe_target`
  both refuse it).
- Logs and metrics carry only counts, reason codes, anonymised paths and an
  8-hex item id. They never carry a title.

**Kill switch:** set `INTAKE_APPLY` to `"0"` in
`kubernetes/apps/media/library-tools/app/intake-cronjob.yaml`, then commit and
push. The watcher keeps planning, logging and pushing metrics, but nothing on
disk changes, not even its state file (`<intake>/.intake-state.json`, which
holds hashed first-seen times and failures).

**Notifications:**
- IT-ops alerts come from `media-intake-alerts.yaml`: a failed move,
  ambiguous for more than 24h, a safety stop, the watcher going stale, and an
  `absent()` guard. The gauges are pushed to pushgateway as
  `media_intake_items{state=pending|ambiguous|failed|planned}` and related
  series.
- The daily business summary goes to the OpenClaw briefing, not Telegram.
  `runbooks/media-intake-digest.py` runs at the nightly maintenance-window
  close-out and ingests `media-intake-<date>` (`window_warning`, `info`,
  source `maintenance`).

**Manual path** (ambiguous items, bulk migrations): the `media-manager` agent
still owns it. It uses the suspended `media-organize` / `media-cleanup` /
`media-rescan` templates, which now use the same single share-root mount (plan
paths `/data/downloads/jdownloader/...`), a 24h TTL, and a folder-scoped
`RESCAN_PATHS`.

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
└── <channel>_YYYYMMDD_<title>.nfo        # <episodedetails> root (NOT <movie>) — see schema below
```

Point a Jellyfin library at `/media/downloads/tube-archivist/` and these are picked up via the `Nfo` metadata reader + the embedded image extractor.

**TA per-video NFO schema** (written by `tube-archivist-nfo-sync`, switched
from `<movie>` to `<episodedetails>` in commit 5bb03b9d for Jellyfin TV
library compatibility):

```xml
<episodedetails>
  <title>...</title>
  <showtitle>...</showtitle>            <!-- TA channel name -->
  <season>YYYY</season>                 <!-- year as season -->
  <episode>NNN</episode>                <!-- ordinal within year -->
  <aired>YYYY-MM-DD</aired>
  <plot>...</plot>
  <runtime>...</runtime>
  <thumb>...</thumb>
</episodedetails>
```

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
| Tube Archivist videos missing in Jellyfin | TA sidecar sync has not run yet for that channel, or the Jellyfin `TubeArchivist` library has not rescanned | Check the `:00` `tube-archivist-nfo-sync` and `:30` `tube-archivist-image-sync` jobs, then refresh the Jellyfin library. There is no Plex bridge — Plex is intentionally not configured for YouTube |
| Quarantined `_duplicates/` folder still indexed | `.plexignore` stops Plex only; Jellyfin uses a different mechanism | Jellyfin skips any directory containing an empty file named `.ignore` — the `.plexignore` at the section root does **not** apply to it. Both files are needed to hide a quarantine folder from both servers |
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

- `2026.09.28`: Automatic intake (`media-intake-watcher`, `intake.py`): classification, confident-TMDb-only naming, ffprobe dedupe (identical / better→two-step REPLACE / worse / ambiguous incl. the fps rule), `_duplicates/` layout + Jellyfin `.ignore`, music layout + tag fixes, incomplete-download guard, safety stops, kill switch `INTAKE_APPLY=0`, pushgateway alerts + OpenClaw daily digest. Single share-root mount (EXDEV fix) for organize/cleanup. `rescan.py` is folder-scoped only. The Plex Movies-root gap is documented as NOT API-fixable (items stay bound to the root location id).
- `2026.09.22`: Added the Jellyfin API auth note next to the TMDb trap (F-5d27f37e): 12.x disables the four legacy forms (`X-Emby-Token`, `X-MediaBrowser-Token`, `api_key=`, `X-Emby-Authorization`); use `Authorization: MediaBrowser Token="<key>"`. Live 10.11.11 responses measured; scripts already switched in `5b8193c9`.
- `2026.08.15`: Removed the stale Tube Archivist→Plex bridge references (scope line, applies-to, troubleshooting row) — TA content is Jellyfin-only and no bridge CronJob exists. Documented that Jellyfin's scan-exclusion mechanism is an empty `.ignore` file inside the folder, not the `.plexignore` at the section root.
- `2026.07.05`: Documented that `_duplicates/`/`_archive/` prefixes are naming-only and require a `.plexignore` file per section root to actually stop Plex from scanning them (found via daily sweep: a quarantined duplicate was still indexed under `Movies/_duplicates/`). Confirmed Plex's built-in keyword exclusion doesn't cover custom prefixes.
- `2026.04.27`: Initial standard. Nested layout. Migration workflow from prior flat layout. Tube Archivist→Plex bridge. Audit thresholds.
