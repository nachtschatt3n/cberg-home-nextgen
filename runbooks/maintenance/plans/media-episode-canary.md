---
plan_id: media-episode-canary
component: media-library
pr: null
kind: data
current: "episode NFO 2.5% (20/807) · episode_sidecar.py proven in DRY-RUN only"
target: "one clean canary show fully sidecar'd (live write), with no other metric moved"
update_type: n/a
risk: medium                          # first live write onto a catastrophic-class CIFS share
est_duration_min: 40
needs_reboot: false
touches:
  namespaces: [media]
  resources:
    - "cifs-plex-media / cifs-jellyfin-media (file WRITES — one show subtree only)"
    - "job/media-episode-sidecar (from the suspended CronJob)"
    - "Plex + Jellyfin TV libraries (rescan of the canary show)"
  shared: [media]
depends_on: [media-episode-sidecar-tool]
conflicts_with: []
status: draft
window: "tue-early:2026-09-15"
auto_execute: false                   # NEVER unattended — writes to the share
sops_refs:
  - docs/sops/media-library-standards.md
  - docs/sops/storage-safety.md
generated: "2026-08-15"
---

# Media stage 2/4 — canary: one show, live episode-NFO write

## 1) Summary & why held

Stage 2 of 4. `episode_sidecar.py` exists and has been proven to write nothing in
dry-run (stage 1). This stage lets it write **for the first time**, on exactly one
show, and checks that the numbers move the way they should and that nothing else
moves at all.

**Why a canary is its own stage rather than the first item of a bulk run.** The
failure this guards against is not "the job crashes" — it is "the job succeeds and
writes 40 wrong files", or "the job succeeds and something *else* silently changes".
A bulk run discovers that after 787 files; a canary discovers it after ~40, inside a
single show subtree that is trivially revertible.

**Baseline that must hold** (audit of 2026-08-14/15): 20 shows, 807 episodes,
`episode_nfo_pct` **2.5**, `season_layout_pct` **100.0**, `series_compliance_pct`
**100.0**; movies `layout_pct` 99.6, `nfo_pct` 100.0, `poster_pct` 99.0,
`fanart_pct` 99.2; Plex `unmatched=0` in all three sections; Jellyfin 550 items,
overview 100%, primary 100%, backdrop 546/550.

**The one number that must NOT improve: `backdrop_pct`.** The four movies missing
`fanart.jpg` are a closed WONTFIX — TMDb has **no backdrop at all** for any of them
(`backdrop_path: None`, 0 backdrops across all languages, verified per-id against
`/movie/{id}/images`). `fanart_pct` 99.2% already passes its ≥90% floor and the four
are recorded as *best available*. If some step in this window "fixes" them, something
synthesised artwork that should not have been synthesised.

**Canary selection.** Pick a show that is unambiguous in TMDb: proper punctuation,
no umlaut transliteration, one clear season structure. **Do not** use the two shows
that hit the documented TMDb ladder traps (one folder is a de-umlauted German title;
one is concatenated without separators) — those need a hand-formatted `TMDB_QUERY`
and belong in stage 3 once the tool is proven.

## 2) Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) STORAGE SAFETY — read docs/sops/storage-safety.md first.
#    cifs-plex-media / cifs-jellyfin-media are CATASTROPHIC class: a PVC delete wipes
#    the whole share. This stage does file WRITES ONLY. No PVC operation of any kind.
#    Never `kubectl delete pvc` in this window.

# b) the tool from stage 1 is actually live
mise exec -- kubectl get configmap -n media library-tools-scripts \
  -o json | python3 -c "import sys,json;print('episode_sidecar.py' in json.load(sys.stdin)['data'])"
mise exec -- kubectl get cronjob -n media media-episode-sidecar \
  -o jsonpath='{.spec.suspend}{"\n"}'                       # true
# If this is false/missing: STOP and skip the window. Do NOT substitute sidecar.py —
# it unlinks every .nfo in the folder and would destroy tvshow.nfo (series_compliance_pct).

# c) fresh baseline from the audit CronJob (not by hand)
mise exec -- kubectl create job -n media audit-pre-$(date +%s) --from=cronjob/media-library-audit
mise exec -- kubectl logs -n media job/audit-pre-<id> | grep -E '"section": "(tv|movies)"'
# record every *_pct; they are the acceptance criteria in §4.

# d) pick the canary and DRY-RUN it once more, now, with today's data
mise exec -- kubectl create job -n media episode-canary-dry-$(date +%s) \
  --from=cronjob/media-episode-sidecar     # SHOW_PATH=<canary show>, DRY_RUN=1
mise exec -- kubectl logs -n media job/episode-canary-dry-<id> | tail -40
# expect written=0, unparsed=0, no_match=0, and a would-write path per episode.
# unparsed>0 means the filenames are not SxxEyy-clean — pick a different canary.

# e) free space (hundreds of small files, but check anyway)
mise exec -- kubectl exec -n media deploy/plex -- df -h /data/data | tail -1
```

## 3) Steps

Operator go/no-go before the live run. One show only. Do not bulk-run.

1. **Marker** so alert triage expects Plex/Jellyfin scan activity:
   ```bash
   runbooks/update-marker.sh add media-library media 1 "episode NFO canary — one show, live write"
   ```
2. **Record the canary's current state** so the rollback is exact:
   ```bash
   mise exec -- kubectl create job -n media episode-canary-list-$(date +%s) \
     --from=cronjob/media-episode-sidecar    # DRY_RUN=1 — the would-write list IS the file inventory
   mise exec -- kubectl logs -n media job/episode-canary-list-<id> | tee /tmp/canary-plan.txt
   ```
   Every path in this list is a file that does not yet exist and that the rollback will
   delete. Nothing outside this list may change.
3. **Live run on the canary only**:
   ```bash
   mise exec -- kubectl create job -n media episode-canary-write-$(date +%s) \
     --from=cronjob/media-episode-sidecar
   # patch env: SHOW_PATH=<canary show>, DRY_RUN=0, OVERWRITE unset (skip-existing stays on)
   mise exec -- kubectl logs -n media job/episode-canary-write-<id> -f | tail -60
   ```
   Expect the JSON summary to show `written` = the number of would-write lines from
   step 2, `skipped_existing` = the show's pre-existing NFOs, `errors=0`.
4. **Trigger a library rescan** for the TV section (delegate cluster actions to
   cberg-agent per the window contract):
   ```bash
   mise exec -- kubectl create job -n media rescan-$(date +%s) --from=cronjob/media-rescan
   ```
5. Clear the marker after §4 passes: `runbooks/update-marker.sh clear media-library`.

**Do not** proceed to a second show in this window. Stage 3 is the bulk run and it
has its own go/no-go.

## 4) Verification

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) re-run the audit and compare against the pre-check baseline
mise exec -- kubectl create job -n media audit-post-$(date +%s) --from=cronjob/media-library-audit
mise exec -- kubectl logs -n media job/audit-post-<id> | grep -E '"section": "(tv|movies)"'
```

Acceptance criteria — **all** of them:

| metric | expected |
|---|---|
| `episode_nfo_pct` | up by roughly `canary_episodes / 807 * 100`, and by no more |
| `series_compliance_pct` | **still 100.0** — the `sidecar.py` unlink trap shows up here |
| `season_layout_pct` | still 100.0 |
| movies `nfo_pct` / `poster_pct` / `fanart_pct` | unchanged (100.0 / 99.0 / 99.2) |
| `movie_nfo_orphan` | unchanged (4) |

```bash
# b) THE load-bearing check — the servers still MATCH everything. A wrong NFO does not
#    show up on disk; it shows up as a mismatched or re-identified item.
mise exec -- kubectl create job -n media coverage-$(date +%s) --from=cronjob/media-metadata-coverage
mise exec -- kubectl logs -n media job/coverage-<id> | tail -30
#   Plex : unmatched=0 in all 3 sections (unchanged)
#   Jellyfin: overview 100%, primary 100%, backdrop STILL 546/550
#             — 550/550 is NOT the target; the 4 are an upstream WONTFIX (§1).

# c) spot-check the canary's content by hand (operator, in the Plex/Jellyfin UI):
#    open 3 episodes across 2 seasons — title, air date and episode number must be the
#    RIGHT ones for those files. A whole-show off-by-one (wrong TMDb season mapping)
#    is the realistic bad outcome and it is invisible in the counters.

# d) no server-side damage
mise exec -- kubectl get pods -n media | grep -E 'plex|jellyfin'      # Running, no restarts
mise exec -- kubectl logs -n media job/episode-canary-write-<id> | grep -iE 'error|traceback' || echo clean
```

Success = `episode_nfo_pct` up by exactly the canary's share, every other metric
unchanged, Plex `unmatched=0`, Jellyfin backdrop still 546/550, and three
hand-checked episodes correct.

## 5) Rollback

The write was additive and confined to one show, so rollback is deleting exactly the
files listed in `/tmp/canary-plan.txt` — **and nothing else**.

```bash
# Delete ONLY the episode .nfo files this run created, via an ephemeral Job that mounts
# the same PVC (same pattern as organize.py). Feed it the explicit path list from
# /tmp/canary-plan.txt; do not glob "*.nfo" across the show, which would also remove
# the 20 pre-existing episode NFOs and tvshow.nfo.
#
#   NEVER delete the PVC. cifs-plex-media is catastrophic class (docs/sops/storage-safety.md).
#   No `kubectl delete pvc` under any circumstance in this plan.
```

Then confirm the library is back to baseline:

```bash
mise exec -- kubectl create job -n media audit-rb-$(date +%s) --from=cronjob/media-library-audit
mise exec -- kubectl logs -n media job/audit-rb-<id> | grep '"section": "tv"'
# episode_nfo_pct back to 2.5, series_compliance_pct 100.0, season_layout_pct 100.0
mise exec -- kubectl create job -n media rescan-rb-$(date +%s) --from=cronjob/media-rescan
```

If the failure was *wrong content* rather than *unwanted files*, the cheaper fix is to
re-run the tool for that show with a corrected `TMDB_ID`/`TMDB_QUERY` and `OVERWRITE=1`
— but only after the operator has confirmed the correct series id. **No media file is
ever touched by this plan; if any step proposes deleting a media file, stop.**

## 6) Interference notes

- **Out of order:** this stage cannot run without `media-episode-sidecar-tool`. If the
  tool is not in the live ConfigMap, **skip the window** — do not fall back to
  `sidecar.py`, which unlinks every `.nfo` in the folder and would take
  `series_compliance_pct` off 100.0 while writing zero episode NFOs.
- **`shared: [media]`** — Plex, Jellyfin and Tube Archivist read the same share, and this
  window triggers a rescan. Do not co-schedule with anything else touching `media`, and
  avoid running while someone is watching.
- **Never unattended.** `auto_execute: false` is load-bearing: this writes files on a
  share whose PVC class once wiped 4.7 TB.
- **Public repo:** no show/movie/artist/channel names in the commit message, the job
  logs that get quoted, or any committed artefact. `<canary show>` is the correct way
  to refer to it. Counts are fine.
- The 05:00 weekday slot is deliberate: the audit + coverage CronJobs and a rescan all
  run inside the window, and nobody is watching. 40 min of work in a 60 min window
  leaves room for the file-list rollback.
