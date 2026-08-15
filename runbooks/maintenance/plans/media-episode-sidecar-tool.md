---
plan_id: media-episode-sidecar-tool
component: media-library
pr: null                              # tooling work, not a version bump
kind: infra                           # new script in the library-tools ConfigMap + a suspended CronJob
current: "no per-episode NFO writer exists anywhere in library-tools (verified 2026-08-15)"
target: "episode_sidecar.py + a suspended media-episode-sidecar CronJob, DRY-RUN by default, writing nothing on the share"
update_type: n/a
risk: low                             # ships a tool that cannot write unless explicitly told to
est_duration_min: 90                  # code authoring + review — NOT a maintenance-window job
needs_reboot: false
touches:
  namespaces: [media]
  resources:
    - configmap/library-tools-scripts  # new episode_sidecar.py key
    - "new: cronjob/media-episode-sidecar (suspend: true, never scheduled)"
  shared: []                           # writes NOTHING to the media share in this stage
depends_on: []
conflicts_with: []
status: vetted                        # VETTED 2026-08-15. Premises re-verified live against the
                                      # library-tools ConfigMap and a fresh audit run:
                                      #  - `episode_sidecar.py` does NOT exist; ConfigMap keys are
                                      #    common/audit/rescan/cleanup/organize/sidecar/
                                      #    metadata_coverage/cleanup_nfos/per_item_refresh/
                                      #    plex_fs_classifier .py — confirmed.
                                      #  - No equivalent writer exists: zero occurrences of
                                      #    `episodedetails` or any per-season TMDb call in the
                                      #    ConfigMap. Existing `sidecar.py` writes exactly one file
                                      #    (tvshow.nfo for shows) — the "writes zero episode NFOs"
                                      #    premise HOLDS.
                                      #  - The cited unlink trap in sidecar.py is REAL. Line drift
                                      #    only: plan cites :805, it is now :803-806
                                      #    (kubernetes/apps/media/library-tools/app/scripts-configmap.yaml).
                                      #    Two accuracy nuances for the implementer: the unlink is
                                      #    `item_path.iterdir()` i.e. NON-recursive (it cannot reach
                                      #    episode NFOs inside `Season XX/`, only the show root), and
                                      #    it is followed by a tvshow.nfo rewrite — so the
                                      #    destructive outcome materialises on a failed/wrong TMDb
                                      #    match that exits before the write.
window: null                          # DELIBERATE — see §6. This is attended development work,
                                      # not a maintenance-window operation. It must LAND before
                                      # media-episode-canary's window (tue-early:2026-09-15).
auto_execute: false
sops_refs:
  - docs/sops/media-library-standards.md
  - docs/sops/storage-safety.md
  - docs/sops/audit-script-correctness.md
generated: "2026-08-15"
---

# Media stage 1/4 — write the per-episode NFO tool (attended, out-of-window)

## 1) Summary & why held

Stage 1 of 4 from the former `media-episode-backfill` (120 min, un-schedulable —
the longest window is 90 min). Splitting it revealed something more useful than a
smaller estimate: **the first stage is not window work at all.**

`episode_nfo_pct` is 2.5% (20/807) against an ≥80% SOP floor. Closing it requires
writing a `.nfo` beside each episode file (`audit.py` counts
`ep.with_suffix(".nfo").exists()`). **No tool in `library-tools` can do that**, verified
2026-08-15 against `kubernetes/apps/media/library-tools/app/scripts-configmap.yaml`:

- `sidecar.py` writes exactly **one** file per invocation — `<folder>.nfo` for
  `ITEM_KIND=movie` or `tvshow.nfo` for `ITEM_KIND=show`. It has no episode path.
- `common.py`'s TMDb helpers (`tmdb_search`, `tmdb_smart`, `tmdb_best_match`) only
  hit `/search/{movie,tv}` — there is no `/tv/{id}/season/{n}` call anywhere.
- `per_item_refresh.py` calls server-side refresh APIs; it writes no files.

**The trap that makes this stage mandatory rather than optional.** The superseded
plan prescribed running `sidecar.py` per show with `ITEM_KIND=show`. `sidecar.py`
unlinks **every** `.nfo` in the target folder before writing
(`scripts-configmap.yaml:805`):

```python
for f in item_path.iterdir():
    if f.is_file() and f.suffix.lower() == '.nfo':
        try: f.unlink()
```

Run per show, that deletes each show's existing `tvshow.nfo` and rewrites it from a
fresh TMDb match — driving `series_compliance_pct` (currently **100.0%** across all
20 shows) down, while writing **zero** episode NFOs. The prescribed tool would have
regressed the very metric the plan's own verification gate depends on. **`sidecar.py`
must not be used for episode work, in this stage or any later one.**

**Why this stage has no window.** Authoring and code-reviewing a script that writes
files onto a catastrophic-class CIFS share is open-ended, iterative, human work. Boxing
it into a 60-minute slot at 05:00 creates pressure to ship an unreviewed writer — the
exact failure mode that produced the trap above. It lands as a normal reviewed commit;
the *window* stages are the ones that run it (stages 2–4).

## 2) Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) confirm the gap is still real and still the shape described above
grep -n "episode_nfo_pct" kubernetes/apps/media/library-tools/app/scripts-configmap.yaml
grep -n "ITEM_KIND\|tvshow.nfo\|f.unlink()" kubernetes/apps/media/library-tools/app/scripts-configmap.yaml | head
grep -rn "episode_sidecar\|episodedetails" kubernetes/apps/media/library-tools/app/ || echo "still no episode writer (expected)"

# b) current numbers, from the CronJob rather than by hand
mise exec -- kubectl logs -n media job/$(mise exec -- kubectl get jobs -n media \
  --sort-by=.metadata.creationTimestamp -o name | grep media-library-audit | tail -1 | cut -d/ -f2) \
  | grep '"section": "tv"'
# baseline to preserve: episode_nfo_pct 2.5, season_layout_pct 100.0, series_compliance_pct 100.0

# c) the TMDb key in the cluster is a v3 key (32-char hex). The v4 Bearer JWT returns 401
#    as a query param — see the SOP's "v3-vs-v4 trap".
mise exec -- kubectl get secret -n media media-manager-tokens -o json | python3 -c "
import sys, json, base64
d = json.load(sys.stdin)['data']
k = base64.b64decode(d['TMDB_API_KEY']).decode()
print('len', len(k), 'looks_v3', len(k) == 32 and all(c in '0123456789abcdef' for c in k.lower()))"

# d) read the SOP's episode schema before writing code
sed -n '/### Sidecar conventions/,/### TMDb integration/p' docs/sops/media-library-standards.md
# minimum episode fields: <season>, <episode>, <title>, <aired>
```

## 3) Steps

1. **Add `episode_sidecar.py` to
   `kubernetes/apps/media/library-tools/app/scripts-configmap.yaml`**, as a new key
   beside `sidecar.py`. Required behaviour — these are the review criteria, not
   suggestions:
   - **Never deletes.** No `unlink`, no `rmtree`, no truncate-then-write of an existing
     path other than the episode `.nfo` it is writing. This is the anti-`sidecar.py`
     rule and it is the single most important line of the review.
   - **Never touches `tvshow.nfo`, `poster.jpg` or `fanart.jpg`.** Series-level metadata
     is at 100% compliance and is out of scope.
   - **`DRY_RUN=1` by default.** Writes only when explicitly invoked with `DRY_RUN=0`.
     In dry-run it logs, per episode, the path it *would* write and the season/episode
     numbers it parsed.
   - **Scoped to one show per invocation** (`SHOW_PATH`), so the batch boundary is also
     the rollback boundary.
   - Resolves the series once (accept `TMDB_ID` directly, else `TMDB_QUERY`, else
     `common.tmdb_smart('show', folder_name, key)`), then fetches
     `https://api.themoviedb.org/3/tv/{id}/season/{n}?api_key=…` per season present on disk.
   - Parses `SxxEyy` from the filename with the existing `common.EPISODE_NAME_RE`
     convention; **skips** any file it cannot parse and counts it as `unparsed`
     (never guesses an episode number).
   - Writes `<episode basename>.nfo` beside the media file containing
     `<episodedetails>` with `<season>`, `<episode>`, `<title>`, `<aired>`, plus
     `<plot>` and `<uniqueid type="tmdb">` when available — matching the SOP schema
     and `sidecar.py`'s XML-escaping of `<`.
   - **Skips existing `.nfo` files** unless `OVERWRITE=1`, so a re-run is idempotent
     and can never clobber a hand-curated sidecar.
   - Calls `common.assert_safe_target()` on the show path and uses `common.log_event`
     + `common.anon_path` so nothing writes a media title into a log that lands in git.
   - Emits a final JSON summary line: `written`, `skipped_existing`, `unparsed`,
     `no_match`, `errors`.
2. **Add `episode-sidecar-cronjob.yaml`** modelled exactly on the existing
   `sidecar-cronjob.yaml`: `schedule: "0 0 31 2 *"`, `suspend: true`,
   `backoffLimit: 0`, `restartPolicy: Never`, the same `runAsUser/Group/fsGroup 1000`,
   the same `plex-media-smb` PVC mount, `TMDB_API_KEY` from `media-manager-tokens`,
   and `DRY_RUN: "1"` in the env block so an accidental `create job` writes nothing.
   Register it in `kustomization.yaml`.
3. **Code review before push.** This writes to `cifs-plex-media`, a **catastrophic-class**
   share (`docs/sops/storage-safety.md`). Reviewer's checklist: no delete of any kind;
   no path escaping `SHOW_PATH`; dry-run default; per-show scope; skip-existing; no
   media titles in log output.
4. **Validate, commit, push** (on `main`, stage only these files):
   ```bash
   mise exec -- kubeconform -summary -exit-on-error -ignore-missing-schemas kubernetes/apps/media/library-tools
   git add kubernetes/apps/media/library-tools/app/scripts-configmap.yaml \
           kubernetes/apps/media/library-tools/app/episode-sidecar-cronjob.yaml \
           kubernetes/apps/media/library-tools/app/kustomization.yaml
   git commit -m "feat(library-tools): add episode_sidecar.py (dry-run default, never deletes)"
   git push
   ```
5. **Prove it in dry-run against one clean show** — no writes, so this is safe to do
   immediately after the commit reconciles:
   ```bash
   mise exec -- kubectl create job -n media episode-sidecar-dryrun-$(date +%s) \
     --from=cronjob/media-episode-sidecar
   # patch SHOW_PATH to a clean, unambiguous show; leave DRY_RUN=1
   mise exec -- kubectl logs -n media job/episode-sidecar-dryrun-<id> | tail -40
   ```

## 4) Verification

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) the tool is actually in the cluster's ConfigMap (not just in git)
mise exec -- kubectl get configmap -n media library-tools-scripts \
  -o jsonpath='{.data.episode_sidecar\.py}' | head -20
mise exec -- kubectl get cronjob -n media media-episode-sidecar \
  -o jsonpath='{.spec.suspend} {.spec.schedule}{"\n"}'            # true, the never-schedule

# b) THE load-bearing check — the dry run wrote NOTHING on the share
mise exec -- kubectl logs -n media job/episode-sidecar-dryrun-<id> | tail -40
# expect: a would-write line per episode, a JSON summary with written=0, and NO
# "nfo-written" events. Then confirm on disk, from the audit rather than by hand:
mise exec -- kubectl create job -n media audit-check-$(date +%s) --from=cronjob/media-library-audit
mise exec -- kubectl logs -n media job/audit-check-<id> | grep '"section": "tv"'
# episode_nfo_pct MUST still be 2.5; series_compliance_pct MUST still be 100.0.
# Any movement means the tool wrote in dry-run — that is a hard failure, revert it.

# c) the parser is right before it is ever allowed to write
#    In the dry-run output, spot-check 5 episodes across 2 seasons: the parsed
#    season/episode numbers must match the filenames, and the target path must be
#    <episode basename>.nfo in the SAME directory — never a folder-level file.

# d) nothing else regressed
mise exec -- kubectl get pods -n media | grep -E 'plex|jellyfin'    # untouched
```

Success = `episode_sidecar.py` present in the live ConfigMap, CronJob suspended,
dry-run summary showing `written=0`, audit numbers **unchanged** (2.5 / 100.0 / 100.0),
and a hand-checked sample of parsed season/episode targets.

## 5) Rollback

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <tool-commit-sha>
git push
mise exec -- kubectl get configmap -n media library-tools-scripts \
  -o json | python3 -c "import sys,json;print(sorted(json.load(sys.stdin)['data'].keys()))"
# episode_sidecar.py gone
mise exec -- kubectl get cronjob -n media | grep episode-sidecar || echo "CronJob gone (expected)"
```

**There is nothing on the share to undo** — this stage runs only in dry-run, so no
file was created, modified or deleted. Confirm with a fresh audit run: `episode_nfo_pct`
2.5, `series_compliance_pct` 100.0, `season_layout_pct` 100.0.

If a dry-run job is somehow still running, delete the Job (not the PVC, ever):
`mise exec -- kubectl delete job -n media episode-sidecar-dryrun-<id>`.

## 6) Interference notes

- **Why `window: null`.** This is attended development, not a window operation. It has
  no cluster-risk profile worth a slot, its duration is genuinely uncertain, and
  rushing it is how the `sidecar.py` trap got written into a plan in the first place.
  **It must land before `media-episode-canary`'s window (`tue-early:2026-09-15`)** — if
  it has not, that window has nothing to execute and should be skipped, not improvised.
- **Out of order:** stages 2–4 all invoke this tool. Without it, `media-episode-canary`
  cannot run and the only tool that *looks* like a substitute (`sidecar.py`) would
  delete `tvshow.nfo` files. If the tool is missing, **skip the window** — do not
  substitute.
- **Storage safety.** `cifs-plex-media` / `cifs-jellyfin-media` are catastrophic class:
  a PVC delete wipes the entire share (`docs/sops/storage-safety.md`; the 2026-04-26
  incident wiped ~4.7 TB in 17 minutes). This plan performs **file writes only, and in
  this stage not even those**. No PVC operation of any kind, ever, in this plan family.
- **Public repo:** never write a show, movie, artist or channel name into the script's
  log output, the commit message, or any committed artefact. Use `common.anon_path`.
  Counts are fine; names are not.
- Two of the 16 target shows hit documented TMDb ladder traps (one folder name is a
  de-umlauted German title, one is concatenated without separators). The tool must
  therefore accept `TMDB_ID` and `TMDB_QUERY` overrides — that requirement exists
  because of those two shows, and it is exercised in stage 3, not here.
