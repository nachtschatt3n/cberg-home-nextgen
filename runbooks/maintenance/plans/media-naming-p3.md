---
plan_id: media-naming-p3
component: media-library
pr: null
finding_refs: [F-88f103eb]
kind: data
current: "episode naming 88.9% (703/791) — 88 off-standard filenames (live media-library-audit-29842545, 2026-09-28; the 87 title-less 'Show - SxxEyy' files are SOP-compliant since a04c35ac; 16 episodes moved to TV Shows/_duplicates on 2026-09-22) — F-88f103eb"
target: "episode naming >= 99% (SOP floor) — `Show Name - S01E01 - Episode Title.ext`"
update_type: n/a
risk: high                            # a rename is the only step in this family that can LOSE a file
est_duration_min: 240                 # was 60 (sized against the mis-reported 99). Surface on
                                      # 2026-09-28 is 88 files (+ their sidecars, roughly doubling the
                                      # move count) — RE-SIZE per show once the breakdown is re-derived
                                      # (review 2026-09-28). One show per batch. See §1.
needs_reboot: false
touches:
  namespaces: [media]
  resources:
    - "cifs-plex-media / cifs-jellyfin-media (file RENAMES — media files + their sidecars)"
    - "Plex + Jellyfin TV libraries (re-identification after each show)"
  shared: [media]
depends_on: []   # NFO backfill EXECUTED 71e6ac58 (stage plan retired). The index plan is 'superseded', which window-scheduler.py:246 never counts as executed, so naming it blocked this plan forever.
conflicts_with:                       # FILLED 2026-09-21; was [].
  - n8n-2.39.8                        # ROLLBACK-CLASS STACKING: all three are backup-restore
  - jellyfin-12.1                     # (n8n, jellyfin-12.1, paperless-db-13.0.2) — added 2026-09-28
  - paperless-db-13.0.2               # (review); jellyfin-12.1 already declared this plan.
  # - nextcloud-34.0.4 (RESOLVED 2026-09-26: executed + retired in now:2026-09-26; ref removed) # `rollback_class: backup-restore`, as is this
  # - nocodb-2026.09.0 (RESOLVED 2026-09-26: executed + retired in now:2026-09-26; ref removed) # plan. Two backup-restore rollbacks in one
                                      # slot leave no rollback capacity for either.
                                      # Declared once per pair — window-scheduler.py
                                      # :253-260 reads conflicts_with in EITHER
                                      # direction. At 240 min this plan fits no
                                      # current slot (sun budget is 180 after the
                                      # Step-0 reserve), so the guard is for when it
                                      # is re-scoped, not for today.
capability_change: false
rollback_class: backup-restore    # DECLARED 2026-09-06. NOT git-revert: a rename
                          # mutates the file, and this plan already records a
                          # folder rename that was reverted and did NOT restore
                          # — Jellyfin had cached the failed identification, so
                          # the revert left the library degraded. There is a
                          # rollback script driven by a rename manifest, and the
                          # plan notes rollback is slower than the rename itself.
                          # That is restore-shaped, not commit-shaped.
autonomy_override: human-gated  # A rename pass over the household media library,
                                # on a plan whose own body documents a revert
                                # that failed to restore, is not something to
                                # run while nobody is watching — whatever the
                                # derivation says.
premises:
  - id: organize-reads-stdin-plan
    why: Steps 2-3 feed an approved JSON move list to organize.py on stdin; if the entrypoint changed, the invocation is wrong.
    run: kubectl get cronjob -n media media-organize -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].command}'
    expect_exact: '["python","/app/organize.py"]'
  - id: plex-is-statefulset
    why: Pre-checks and the playback gate target the Plex pod by this name.
    run: kubectl get sts -n media plex-plex-media-server -o name
    expect_exact: statefulset.apps/plex-plex-media-server
status: draft
window: null                          # UNSCHEDULED. 240m fits no current window as one block;
                                      # SPLIT before rescheduling, one show per batch. Each batch is
                                      # independently verifiable and revertible. Surface re-measured
                                      # 2026-09-28: 88 files (F-88f103eb). Attended weekend window
                                      # only; not the same slot as jellyfin-12.1, paperless-db-13.0.2
                                      # or n8n-2.39.8 (conflicts_with).
# auto_execute RETIRED 2026-08-26 (P2.1b) — execution class is now DERIVED
# from capability_change/rollback_class per runbooks/autonomy-policy.yaml.
# (original rationale: NEVER unattended — operator-approved rename table required)
sops_refs:
  - docs/sops/media-library-standards.md
  - docs/sops/storage-safety.md
generated: "2026-08-15"
---

# Media stage 4/4 — rename the 88 off-standard episode filenames (attended)

## 0) Independently re-verified 2026-08-20 — and the surface is softer than 404 suggests

The 49.9% figure was confirmed by a read-only scan of the actual filenames,
run outside the audit so a second bad regex could not agree with the first.
It reproduces the audit exactly, and the *reason* it differs from the old
87.7% is now pinned down:

| reading | compliant | pct |
|---|---|---|
| any prefix before ` - SxxEyy - ` | 616 | 76.3% |
| prefix **equals the show folder** (the SOP rule) | **403** | **49.9%** |

So the audit is right and the old 87.7% was the lax-regex artifact.

**CORRECTION 2026-08-20 (second pass).** A first reading of this called the
213 "a mechanical prefix substitution, do them first". **That was wrong and
generating the rename table is what caught it.** The table came out proposing
to rewrite correctly-named files to match malformed folders — it would have
damaged 213 good filenames. Do not restore that framing.

The 404 splits into two unrelated problems:

- **213 files across just 2 shows are FOLDER-side.** The filenames are already
  correct; the *folder* disagrees with them. One folder is concatenated without
  periods or spaces while its 43 files carry the properly punctuated title; the
  other folder drops a separator its 170 files include. The remedy is
  **2 folder renames and zero file renames**, which is a completely different
  risk profile from 213 file operations. Caveat: renaming a show folder changes
  the library path, so Plex/Jellyfin re-match the series — check watch state and
  artwork after, and do it as its own step.
- **191 files across 12 shows are genuine file-naming faults** — 99 carry an
  `SxxEyy` but no ` - ` separators, 92 deviate otherwise. **This, not 404, is
  the real file-rename surface**, and the 240-minute estimate should be re-sized
  against it.

**FOLDER RENAMES ARE NOT THE CHEAP HALF — one was attempted and reverted
(2026-08-20).** Of the two folder-side shows, the 43-file one renamed cleanly
and its files are now compliant. The 170-file one did not:

- Renaming its folder made the filenames compliant, but **Jellyfin lost the
  series overview** — the new folder name is not identifiable, and Jellyfin
  matches on the folder, not on the sidecar. Plex was unaffected
  (`unmatched: 0`, 100% coverage throughout).
- **Reverting the folder name did NOT restore it.** Jellyfin had already cached
  the failed identification, so the revert left the library in the degraded
  state. Assume a rename is one-way from the media server's point of view.
- A `replaceAllMetadata` + `replaceAllImages` refresh, used trying to recover,
  blocked the `/health` endpoint long enough for the **liveness probe to fail
  and the kubelet to SIGKILL the pod** (exit 137 — not OOM; the limit is 12Gi
  and it was using ~300Mi). One restart. It settled, but do not fire a full
  refresh at a live server as a recovery step.

**Consequences for this plan:** a folder rename must be treated as
media-server-identity surgery, not a filename fix. Do them ONE at a time, and
plan the Jellyfin *Identify* step (operator, UI, provider id from the show's
own `tvshow.nfo`) as part of the same step rather than as cleanup. For the
170-file show the safer route is the FILE side after all — rename the files to
match the existing, identifiable folder name, which leaves the media servers'
matching untouched.

**OPTION B EXECUTED 2026-08-20 — file-side rename, and it also repaired the
folder-rename damage.** The 170-file show was fixed by renaming the FILES to
match its existing, identifiable folder, instead of renaming the folder.

- **344 files renamed, not 170.** Each video has a `.nfo` sidecar that must
  move with it or the whole episode-NFO backfill is orphaned: 173 video + 171
  sidecar. `tvshow.nfo`, `poster.jpg` and `fanart.jpg` are NOT prefixed and
  must be excluded. Any future rename batch has to count sidecars, not
  episodes.
- Result: naming 55.3 -> 76.3, and `episode_nfo_pct` HELD at 96.3 — proof the
  sidecars travelled with their videos. File count 347 before and after.
- **It also restored what the folder rename broke.** Because episode identity
  (`SxxEyy`) and the folder never changed, both servers re-matched cleanly and
  Jellyfin recovered the overview it had lost: back to 100.0/100.0, Plex
  `unmatched: 0` throughout. **This is the evidence that the file side is the
  correct direction** — it moves nothing the media servers key on.
- 3 of the show's 173 videos stay non-compliant: they carry no valid `SxxEyy`
  and belong to the 191-file bucket, not this one.

> **Trap for whoever does the remaining 191.** Recovering a mis-identified
> series in Jellyfin means selecting the item to re-identify. Selecting it by
> NAME PREFIX picked the wrong series and stamped one show's provider id onto
> another, silently. **Select by PATH.** It was caught only because a
> duplicate-name check ran afterwards, and fixed by re-applying the correct id
> from the target folder's own `tvshow.nfo`.

**One show cannot be fixed by renaming alone.** It holds 52 files numbered
continuously `S01E01..S01E52`, while TMDb lists 26 episodes in season 1 —
verified by forcing the series id from its own `tvshow.nfo`. Episodes 27-52
therefore match nothing and received no sidecar in the NFO backfill. They
need a season split (`S02Exx`) before either naming or NFO coverage can
reach them; a prefix-only rename will not help.


## 1) Summary & why held

Final stage. **Re-measured 2026-09-28 (F-88f103eb):** 88 of 791 episodes do not match
the SOP form `Show Name - S01E01 - Episode Title.ext`; `episode_naming_pct` is **88.9%**
(703/791) against a ≥99% floor. The drop from the earlier 404/49.9% and 191 figures is
not renaming work: the audit now accepts the SOP's title-less `Show - SxxEyy` form
(a04c35ac, 87 files) and 16 episodes moved to `_duplicates` in the 2026-09-22 dedup. The
per-show breakdown of the 88 must be re-derived before scheduling. (The paragraphs below
record the history of the measurement.)

**Scope correction (2026-08-16, sweep N-22):** this stage was originally sized
against "99 filenames in 4 shows / 87.7%". That figure came from a lax audit
regex (` - SxxEyy\b`, case-insensitive, no prefix/title constraint) that measured
a *weaker* rule than the SOP mandates and under-counted the surface ~4x. The audit
now measures the real SOP rule — case-sensitive `SxxExx` token, filename prefix
equal to the show folder name, and a non-empty episode title — so the true surface
is **404 files across 12 shows** (10 of which are fully non-compliant; the largest
single show holds 173). Nothing on disk changed; only the measurement was corrected.

**This is materially bigger than the family assumed and no longer fits one window.**
At one-show-per-batch with per-show go/no-go it spans **multiple weekend windows**.
`est_duration_min` was raised 60 → 240 to reflect that; the maintenance-window
agent will split it across windows rather than force it into one.

**This is the only stage in the family that can lose data.** Every other stage writes
additive sidecars whose rollback is "delete what was added". A rename mutates the file
that *is* the media. It therefore runs last, attended, in a weekend window, with an
operator-approved rename table produced **before** anything moves.

**It runs after the NFO backfill, not before, and the ordering is load-bearing.** After
`media-episode-backfill-bulk` each episode has a `.nfo` whose basename must match the
media file. A rename that moves `X.mkv` without also moving `X.nfo` silently orphans
the sidecar and drops `episode_nfo_pct` right back down. The SOP's multi-step rename
exists for exactly this:

1. media file → 2. the matching `.nfo` → 3. the NFO's XML fields → 4. delete stale sidecars.

**Why the rename table is the real deliverable.** The dangerous failure is not a
crashed job; it is a rename that collides (two source files mapping to one target) or
that mis-parses an episode number and swaps two episodes. Both are invisible in the
counters afterwards — `episode_naming_pct` goes up either way.

## 2) Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) STORAGE SAFETY — docs/sops/storage-safety.md first. cifs-plex-media /
#    cifs-jellyfin-media are CATASTROPHIC class. This stage RENAMES files in place.
#    No PVC operation of any kind. Never `kubectl delete pvc` in this window.
#    Renames must be move-only (the organize.py invariant): never copy-then-delete.

# b) baseline + confirm stage 3 held
mise exec -- kubectl create job -n media audit-pre-$(date +%s) --from=cronjob/media-library-audit
mise exec -- kubectl logs -n media job/audit-pre-<id> | grep -E '"section": "(tv|movies)"'
# record: episode_naming_pct (49.9 pre-stage, corrected metric), episode_nfo_pct (>=80 after stage 3),
# season_layout_pct 100.0, series_compliance_pct 100.0.

# c) THE deliverable — produce the rename table and have it APPROVED before any move.
#    For each of the 12 affected shows, list: current filename -> proposed filename, plus the
#    matching .nfo and -thumb.jpg. Keep it OUTSIDE the repo (public repo: no titles).
#    Validate the table mechanically before showing it to the operator:
#      * every target matches the SOP regex `<Show> - S\d\dE\d\d( - .+)?\.(mkv|mp4|avi|m4v)`
#      * TARGETS ARE UNIQUE — a collision would overwrite a real episode
#      * no target already exists on disk
#      * every source has exactly one target and vice versa (a bijection)
#      * season/episode numbers are taken from the EXISTING SxxEyy in the source name
#        where present; where absent, the operator confirms the mapping by hand
#      * umlauts stay as `ä/ö/ü` — the SOP forbids transliteration and CIFS handles UTF-8

# d) free space + servers healthy + nobody watching
mise exec -- kubectl exec -n media sts/plex-plex-media-server -- df -h /data | tail -1
mise exec -- kubectl get pods -n media | grep -E 'plex|jellyfin'
# Active sessions: Plex /status/sessions MediaContainer size MUST read size="0" (a presence
# check: the attribute always prints, so a live stream reads size="N"). Replay it once with a
# stream playing before trusting it. Jellyfin: GET /Sessions?activeWithinSeconds=60 filtered to
# entries with NowPlayingItem must be empty, demonstrated the same way. (Review 2026-09-28: the
# old `kubectl logs deploy/plex | grep playing || echo` targeted a NotFound object and could not fail.)
```

## 3) Steps

Operator go/no-go **per show**, against the approved table. One show per batch.

1. **Marker**:
   ```bash
   runbooks/update-marker.sh add media-library media 2 "episode filename normalisation — one show per batch, approved rename table"
   ```
2. **Dry-run the approved move list for one show** through `media-organize`
   (`organize.py` reads a JSON move list on stdin; it has no SHOW_PATH/dry-run env and
   generates no proposals of its own):
   ```bash
   # The APPROVED TABLE is the organize.py input, kept off-repo:
   # /private/tmp/<session>/rename-<show>.json = {"dry_run": true, "moves":[{"src":"/data/data/TV Shows/<show>/Season NN/<old>","dst":".../<new>"}, ...]}
   # (one entry per video AND per .nfo AND per -thumb.jpg). Feed it on stdin:
   # kubectl create job -n media rename-dry-<show>-$(date +%s) --from=cronjob/media-organize --dry-run=client -o yaml
   # -> set command to ["/bin/sh","-ec","python /app/organize.py < /plan/plan.json"] with the JSON mounted from a
   # scratch Secret/ConfigMap created and deleted in-window (never committed).
   # PASS = organize-done ok == len(moves), fail == 0. The log is anonymised (anon_path), so the dry run proves
   # count + safety guards only; the NAMES are proven by the table validation in §2(c), not by a diff.
   # UNTESTED as of review 2026-09-28: the planner must dry-test this invocation before vetting.
   ```
3. **Execute for that show**, re-running the same Job with `"dry_run": false`. Media file and its
   `.nfo`/`-thumb.jpg` move in the same moves list. NFO XML fields are NOT rewritten (no
   tool exists; SxxEyy is unchanged by a file-side rename, so `<season>/<episode>` stay
   correct). The off-repo approved JSON, not the Job log, is the rollback input — the Job
   log is path-anonymised.
4. **Immediately verify that show** before starting the next: episode count on disk
   unchanged, no orphaned `.nfo`, Plex/Jellyfin still match every episode (§4).
5. **Rescan** after each show and confirm the server re-identified the renamed files
   rather than creating duplicates:
   ```bash
   mise exec -- kubectl create job -n media rescan-$(date +%s) --from=cronjob/media-rescan
   ```
6. **Stop at the window boundary.** A show is atomic; stopping between shows leaves a
   consistent library. Do not start a show with less than 15 minutes left — a rename
   rollback is slower than a rename.
7. Clear the marker: `runbooks/update-marker.sh clear media-library`.

## 4) Verification

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) FIRST: nothing was lost. Episode COUNT is the primary safety metric here —
#    a collision silently reduces it.
mise exec -- kubectl create job -n media audit-post-$(date +%s) --from=cronjob/media-library-audit
mise exec -- kubectl logs -n media job/audit-post-<id> | grep '"section": "tv"'
```

| metric | expected |
|---|---|
| `episodes_total` | **exactly the §2(b) pre-show value** (791 on 2026-09-28) — any drop means a rename collided |
| `episode_naming_pct` | up toward ≥ 99.0 for the shows processed |
| `episode_nfo_pct` | **unchanged** — if it fell, `.nfo` files were orphaned by their media file |
| `season_layout_pct` | still 100.0 |
| `series_compliance_pct` | still 100.0 |
| movies metrics | untouched |

```bash
# b) THE load-bearing check — the servers re-identified the files rather than
#    creating duplicate or unmatched items
mise exec -- kubectl create job -n media coverage-$(date +%s) --from=cronjob/media-metadata-coverage
mise exec -- kubectl logs -n media job/coverage-<id> | tail -30
#   Show-level only (section 2 counts SHOWS: total 20) — it cannot see an episode error.
#   The episode gate is: Plex section-2 episode count (/library/sections/2/all?type=4 totalSize)
#   and Jellyfin Episode count (/Items?IncludeItemTypes=Episode&Recursive=true TotalRecordCount)
#   BOTH equal their §2(b) pre-show values, captured in §2(b).
#   (media-plex-fs-classifier walks Movies only — not a TV gate; removed 2026-09-28.)

# c) per show, by hand: open the renamed show in Jellyfin and confirm episode ORDER and
#    titles are right. An off-by-one that swapped two episodes leaves every counter
#    perfect and the library wrong — this check is the only thing that catches it.

# d) no orphaned sidecars
#    For each renamed show, confirm every .nfo has a media file with the same basename
#    (the audit's episode_nfo_pct covers this in aggregate; spot-check one season).
```

Success = episode count unchanged, `episode_naming_pct` ≥ 99 for the processed shows,
`episode_nfo_pct` and `series_compliance_pct` unchanged, Plex and Jellyfin episode counts
equal their pre-show values, and hand-verified episode order.

## 5) Rollback

**Replay the approved move list in reverse, per show.** The Job log is path-anonymised
and cannot be inverted; the off-repo approved JSON is the rollback input, which is why one
show per batch is a hard rule.

```bash
# Swap src/dst in the SAME approved JSON and run it through media-organize exactly as §3 step 2:
python3 -c 'import json,sys; p=json.load(open(sys.argv[1])); p["moves"]=[{"src":m["dst"],"dst":m["src"]} for m in reversed(p["moves"])]; p["dry_run"]=False; json.dump(p,open(sys.argv[2],"w"))' rename-<show>.json rollback-<show>.json
# atomic_mv refuses an existing dst, so a partial rollback stops rather than overwrites.
# Keep rename-<show>.json until the show's §4 checks pass.
#
# NEVER delete the PVC. cifs-plex-media is catastrophic class (docs/sops/storage-safety.md).
```

Then prove the library is back:

```bash
mise exec -- kubectl create job -n media audit-rb-$(date +%s) --from=cronjob/media-library-audit
mise exec -- kubectl logs -n media job/audit-rb-<id> | grep '"section": "tv"'
# episodes_total unchanged, episode_naming_pct back to the pre-show value,
# episode_nfo_pct unchanged, series_compliance_pct 100.0
mise exec -- kubectl create job -n media rescan-rb-$(date +%s) --from=cronjob/media-rescan
mise exec -- kubectl create job -n media coverage-rb-$(date +%s) --from=cronjob/media-metadata-coverage
# Plex unmatched=0
```

**If a file cannot be found after a rename, do not improvise a delete.** The move-only
invariant means it still exists somewhere — search both the show folder and the section
root for the basename (`docs/sops/media-library-standards.md`, "Diagnose Example 1").
Nothing in this plan deletes a media file; if any step proposes it, stop.

## 6) Interference notes

- **Out of order:** running this before `media-episode-backfill-bulk` is not merely
  premature — it changes the work. Rename first and the later NFO backfill writes
  sidecars for the new names (fine); backfill first and rename second means each rename
  must carry its `.nfo` along (the SOP's 4-step order). This plan is written for the
  second case. If the backfill has **not** run, the rename table must be rebuilt without
  the `.nfo` steps, and this plan re-verified — do not execute it as written.
- **`shared: [media]`** — Plex, Jellyfin and Tube Archivist read the same share. Renames
  cause re-identification; expect items to briefly disappear from the UI during a scan.
  Do not co-schedule any other `media` plan and do not run while anyone is watching.
- **Never unattended.** `autonomy_override: human-gated` is load-bearing twice over: an approved
  rename table is required *and* per-show go/no-go is required.
- **Public repo:** the rename table, the show names and the episode titles must never be
  committed, pasted into a commit message, or written into a runbook artefact. Keep the
  table outside the repo; report counts only.
- **The window's slack is the rollback budget.** Leave generous slack per show: replaying a rename log in reverse takes longer than the original rename.
  If a show fails verification, spend the remaining time rolling that show back rather
  than starting the next one.
- After this stage the whole `media-episode-backfill` family is complete: episode NFO
  ≥80%, naming ≥99%, and the movie fanart gap closed as WONTFIX (4 items with no
  upstream backdrop; `fanart_pct` 99.2 against a ≥90 floor).
