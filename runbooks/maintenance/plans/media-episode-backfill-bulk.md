---
plan_id: media-episode-backfill-bulk
component: media-library
pr: null
kind: data
current: "episode NFO ~2.5% + the canary show (stage 2); 15 shows still at zero episode NFO"
target: "episode_nfo_pct >= 80% (SOP floor) across the TV section"
update_type: n/a
risk: medium
est_duration_min: 60                  # ~15 shows x ~3-4 min per show incl. per-batch checks
needs_reboot: false
touches:
  namespaces: [media]
  resources:
    - "cifs-plex-media / cifs-jellyfin-media (file WRITES — episode .nfo only)"
    - "job/media-episode-sidecar (one Job per show)"
    - "Plex + Jellyfin TV libraries (rescan per batch)"
  shared: [media]
depends_on: [media-episode-canary]
conflicts_with: []
status: draft
window: "sat-early:2026-10-03"
auto_execute: false                   # NEVER unattended
sops_refs:
  - docs/sops/media-library-standards.md
  - docs/sops/storage-safety.md
generated: "2026-08-15"
---

# Media stage 3/4 — bulk episode-NFO backfill, one show per batch

## 1) Summary & why held

Stage 3 of 4. The tool is written (stage 1) and proven live on one show (stage 2).
This stage runs it across the remaining shows to lift `episode_nfo_pct` from ~2.5%
to the SOP floor of ≥80%.

**The work is concentrated, which is what makes it fit a window.** Only 4 of 20
shows have any episode NFO at all — **16 have zero** — so the backfill is ~787
episodes across 15 remaining shows (the canary took one). Per show the tool makes a
handful of TMDb calls and writes a few dozen small files; the per-show wall time is
dominated by the verification between batches, not by the writing.

**The batch boundary IS the rollback boundary.** One show per Job, operator go/no-go
between shows, audit re-run every few shows. A bad TMDb series match damages exactly
one show's episode sidecars and is undone by deleting that show's newly written
`.nfo` files.

**Two shows need a hand-formatted query — do them last.** Both hit documented traps
in the SOP's TMDb query ladder and return nothing when queried as their folder name:
one folder is a **de-umlauted German title** (needs the proper umlaut form; the SOP's
naming rule is that umlauts stay `ä/ö/ü` — this folder predates that), and one is
**concatenated without periods or spaces** (needs the properly punctuated title).
Supply `TMDB_ID` (best) or a hand-written `TMDB_QUERY` for these two, verify the
resolved series title in the dry-run output before writing, and run them only after
the other 13 have succeeded.

**Do not use `sidecar.py`.** It unlinks every `.nfo` in the target folder before
writing — per show that destroys `tvshow.nfo` and drives `series_compliance_pct` off
100.0 while writing zero episode NFOs. Only `episode_sidecar.py` from stage 1 may be
used here.

**`backdrop_pct` must not move.** The four movies without `fanart.jpg` are a closed
WONTFIX (TMDb has no backdrop for any of them; `fanart_pct` 99.2 already passes its
≥90 floor). Jellyfin backdrop stays 546/550. 550/550 is not the target.

## 2) Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) STORAGE SAFETY — docs/sops/storage-safety.md. cifs-plex-media / cifs-jellyfin-media
#    are CATASTROPHIC class (a PVC delete wipes the whole share). File WRITES ONLY here.
#    No PVC operation of any kind, in either direction, in this window.

# b) stage 2 landed and held
mise exec -- kubectl create job -n media audit-pre-$(date +%s) --from=cronjob/media-library-audit
mise exec -- kubectl logs -n media job/audit-pre-<id> | grep -E '"section": "(tv|movies)"'
# require: episode_nfo_pct = 2.5 + the canary's share, series_compliance_pct 100.0,
# season_layout_pct 100.0, movies metrics unchanged. If series_compliance_pct is below
# 100.0, STOP — something already deleted a tvshow.nfo and that must be understood first.

# c) the tool is live and still dry-run-by-default
mise exec -- kubectl get configmap -n media library-tools-scripts \
  -o json | python3 -c "import sys,json;print('episode_sidecar.py' in json.load(sys.stdin)['data'])"
mise exec -- kubectl get cronjob -n media media-episode-sidecar \
  -o jsonpath='{.spec.suspend} {.spec.jobTemplate.spec.template.spec.containers[0].env}{"\n"}' | head -c 400

# d) build the run order — 13 clean shows first, the 2 trap shows last
mise exec -- kubectl create job -n media shows-list-$(date +%s) --from=cronjob/media-library-audit
# From the audit output, list the shows with episode_nfo coverage 0. Write the order into
# a scratch file OUTSIDE the repo (show names must never be committed — public repo).

# e) free space + servers healthy
mise exec -- kubectl exec -n media deploy/plex -- df -h /data/data | tail -1
mise exec -- kubectl get pods -n media | grep -E 'plex|jellyfin'
```

## 3) Steps

Operator go/no-go per show. **One show per Job.** Never bulk-run all shows in one Job.

1. **Marker** (expect sustained Plex/Jellyfin scan activity for the window):
   ```bash
   runbooks/update-marker.sh add media-library media 2 "episode NFO bulk backfill — one show per batch"
   ```
2. **Per show, dry-run first, then write** — this two-step is not optional; it is how a
   bad series match is caught before any file exists:
   ```bash
   # (i) dry run — read the resolved series title and the would-write count
   mise exec -- kubectl create job -n media ep-dry-$(date +%s) --from=cronjob/media-episode-sidecar
   #     env: SHOW_PATH=<show>, DRY_RUN=1
   mise exec -- kubectl logs -n media job/ep-dry-<id> | tail -40
   #     CHECK: resolved series title + year is the right series; unparsed=0; no_match=0.
   #     If the folder name is one of the two trap shows, add TMDB_ID=<id> (preferred) or a
   #     hand-formatted TMDB_QUERY and re-run the dry run until the title is right.

   # (ii) live write for that show only
   mise exec -- kubectl create job -n media ep-write-$(date +%s) --from=cronjob/media-episode-sidecar
   #     env: SHOW_PATH=<show>, DRY_RUN=0   (OVERWRITE stays unset: skip-existing protects
   #                                          the 20 pre-existing episode NFOs)
   mise exec -- kubectl logs -n media job/ep-write-<id> | tail -40
   #     written == the dry-run would-write count, errors=0
   ```
3. **Every 3–4 shows, re-run the audit and stop if anything but `episode_nfo_pct` moved**:
   ```bash
   mise exec -- kubectl create job -n media audit-mid-$(date +%s) --from=cronjob/media-library-audit
   mise exec -- kubectl logs -n media job/audit-mid-<id> | grep '"section": "tv"'
   ```
4. **Rescan once per batch group** (not per show — it is expensive):
   ```bash
   mise exec -- kubectl create job -n media rescan-$(date +%s) --from=cronjob/media-rescan
   ```
5. **Stop at the window boundary, not at the show list boundary.** Each show is atomic,
   so an incomplete run is a consistent state: the shows that were done stay done, and
   the rest carry to the next window. Record where you stopped. **Do not** start a show
   with less than 5 minutes left.
6. Clear the marker: `runbooks/update-marker.sh clear media-library`.

## 4) Verification

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) the target metric moved, and only it
mise exec -- kubectl create job -n media audit-post-$(date +%s) --from=cronjob/media-library-audit
mise exec -- kubectl logs -n media job/audit-post-<id> | grep -E '"section": "(tv|movies)"'
```

| metric | expected |
|---|---|
| `episode_nfo_pct` | **≥ 80.0** if all shows ran; otherwise up by the share of the shows that did |
| `series_compliance_pct` | **still 100.0** (the unlink trap fires here if `sidecar.py` was used) |
| `season_layout_pct` | still 100.0 |
| `episode_naming_pct` | **unchanged at 87.7** — renames are stage 4, not this stage |
| movies `nfo_pct` / `poster_pct` / `fanart_pct` | unchanged (100.0 / 99.0 / 99.2) |
| `movie_nfo_orphan` | unchanged (4) |

```bash
# b) THE load-bearing check — the servers still match every item
mise exec -- kubectl create job -n media coverage-$(date +%s) --from=cronjob/media-metadata-coverage
mise exec -- kubectl logs -n media job/coverage-<id> | tail -30
#   Plex: unmatched=0 in all 3 sections
#   Jellyfin: overview 100%, primary 100%, backdrop STILL 546/550 (the 4 are WONTFIX)

# c) per-show sanity, by hand, for the two trap shows especially: open 2 episodes each in
#    Jellyfin and confirm the episode titles belong to THAT series. A wrong-series match
#    writes a full, valid, completely incorrect set of sidecars — the counters cannot see it.

# d) job hygiene
mise exec -- kubectl get jobs -n media | grep ep-write        # all Complete, none Failed
mise exec -- kubectl logs -n media job/ep-write-<id> | grep -iE 'error|traceback' || echo clean
```

Success = `episode_nfo_pct` at or above 80.0 for the shows processed, every other
metric unchanged, Plex `unmatched=0`, Jellyfin backdrop 546/550, and hand-checked
episode titles correct for the two trap shows.

## 5) Rollback

Rollback is per show — that is why the batch boundary is one show.

```bash
# For the affected show only: delete the episode .nfo files that THIS run created.
# Use the dry-run would-write list from step 2(i) as the explicit path list.
# Do NOT glob "*.nfo" across the show — that also removes tvshow.nfo and any
# pre-existing episode NFO, converting a small mistake into a metric regression.
#
# NEVER delete the PVC. cifs-plex-media is catastrophic class (docs/sops/storage-safety.md);
# no `kubectl delete pvc` in this window under any circumstance.
```

Confirm the library is back where it was:

```bash
mise exec -- kubectl create job -n media audit-rb-$(date +%s) --from=cronjob/media-library-audit
mise exec -- kubectl logs -n media job/audit-rb-<id> | grep '"section": "tv"'
# episode_nfo_pct back to the pre-show value; series_compliance_pct 100.0
mise exec -- kubectl create job -n media rescan-rb-$(date +%s) --from=cronjob/media-rescan
mise exec -- kubectl create job -n media coverage-rb-$(date +%s) --from=cronjob/media-metadata-coverage
# Plex unmatched=0 again
```

For a *wrong content* failure (right count, wrong series), the better fix is to re-run
that show with the correct `TMDB_ID` and `OVERWRITE=1` rather than to delete — but only
after the operator confirms the series id. **No media file is ever touched by this plan.
If any step proposes deleting a media file, stop.**

## 6) Interference notes

- **Out of order:** running this before `media-episode-canary` means the tool's first
  live write is 787 files across 15 shows instead of ~40 files in one — the canary
  exists precisely so that a systematic parsing or matching error is caught cheaply.
  Running it before `media-episode-sidecar-tool` is impossible (no tool), and the
  substitute that *looks* right (`sidecar.py`) deletes `tvshow.nfo` files.
- **`shared: [media]`** — Plex, Jellyfin and Tube Archivist share the mount and this
  window rescans repeatedly. Do not co-schedule any other `media` plan, and expect
  degraded playback responsiveness during scans.
- **Never unattended.** Per-show go/no-go is the control that keeps a bad match to one
  show.
- **Public repo:** show names must not appear in commit messages, quoted logs, or any
  committed artefact — `<show>` / `Show - SXXEYY` / counts only. Keep the run-order
  scratch file outside the repo.
- **Partial completion is a valid outcome.** Shows are atomic; stopping halfway leaves a
  consistent library and a higher `episode_nfo_pct`. If shows remain, request another
  window rather than overrunning this one — the rollback needs the slack.
- Stage 4 (`media-naming-p3`) renames files. Renaming a media file after this stage
  also requires renaming its new `.nfo` — that ordering dependency is stated in stage 4
  and is why the rename stage runs last.
