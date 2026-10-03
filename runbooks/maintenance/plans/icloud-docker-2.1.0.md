---
plan_id: icloud-docker-2.1.0
component: icloud-docker                # BOTH instances: backup/icloud-docker-mu + backup/icloud-docker-andrea
pr: null                                # no Renovate PR exists (gh pr list --search icloud: [] on 2026-10-03).
                                        # The pin is a floating `main@sha256` build, which version-check reads
                                        # as "main == main" and never offers a release bump (see §6 repo note).
kind: image
current: "main@sha256:91486ec1eaeb382e7af264b7ffa935c5ba110f11c3c2f1805976782ff5017917"
                                        # live 2026-10-03 on BOTH deployments (deploy spec image). A main build
                                        # of ~2026-06-06 (between v1.25.0 and v1.26.0): icloudpy 0.9.0, has the
                                        # 1.26 python_keyring entrypoint change, lacks every Drive package fix.
target: "2.1.0"                         # pinned as 2.1.0@sha256:c57e8248fefc55d490f090eb5edd08ff53045861e4b8f532403926b38af36ba9
                                        # verified 2026-10-03 against registry-1.docker.io: tags `2.1.0` and
                                        # `latest` both resolve to that OCI index (linux/amd64 + arm64); the
                                        # amd64 config carries APP_VERSION=2.1.0, created 2026-10-01T05:55Z.
update_type: major
risk: medium                            # major jump (1.26..2.1, 222 commits) on the auth + Drive paths, but:
                                        # session/cookie format unchanged (icloudpy 0.9->0.10 is additive),
                                        # destination layout unchanged with our config (§1.3), web UI default
                                        # OFF, remove_obsolete stays false, and a no-write --dry-run of the NEW
                                        # image against the REAL session + share gates each instance (§3.3)
                                        # before anything is committed. Instances are independent.
est_duration_min: 140                   # pre-checks 10 + probe commit 10 + mu (backup 3, dry-run 10,
                                        # commit/resume 7, first v2 drive cycle ~30 + photo cycle ~17,
                                        # gates 8) ~75 + andrea (dry-run 8, commit/resume 7, drive ~1 +
                                        # photos ~12, gates 8) ~35 + SOP doc commit 5 + slack 5.
                                        # Measured cycle times: mu drive 31 min / photos 17 min, andrea
                                        # drive 1 min / photos 12 min (logs 2026-10-03).
needs_reboot: false
touches:
  namespaces: [backup]
  resources:
    - helmrelease/icloud-docker-mu        # image.tag edit (commit B)
    - helmrelease/icloud-docker-andrea    # image.tag edit (commit C)
    - deployment/icloud-docker-mu         # suspended+scaled 0 for the dry-run, then ONE Recreate roll
    - deployment/icloud-docker-andrea     # same
    - pvc/icloud-docker-mu-session        # Longhorn (longhorn-static, off-git). In-PVC backup copy written (§3.2),
                                          #   cookies re-written by the new image on auth (normal per-cycle behaviour)
    - pvc/icloud-docker-andrea-session    # Longhorn (dynamic `longhorn`, reclaim Delete — never delete it)
    - pvc/icloud-docker-mu-data           # CIFS cifs-icloud-docker-mu (Severe tier). Mounted READ-ONLY by the
                                          #   dry-run pod; written additively by v2 (newly unpacked packages)
    - pvc/icloud-docker-andrea-data       # CIFS cifs-icloud-docker-andrea (Severe tier). Same.
    - pod/icloud-v2-dryrun-mu             # throwaway, deleted in §3.3
    - pod/icloud-v2-dryrun-andrea         # throwaway, deleted in §3.6
    - configmap/icloud-sync-probe         # RE_AUTH extension (commit A) — Flux ks icloud-backup-freshness
    - cronjob/icloud-sync-probe           # not edited; picks up the configmap on its next run
    - docs/sops/icloud-docker-reauth.md   # re-auth pod image -> 2.1.0 digest (commit D)
  shared: [cifs/backups, monitoring, storage/longhorn, apple-id-2fa]
                                          # cifs/backups: //NAS/backups icloud-backup/{mu,andrea} subdirs.
                                          # monitoring: §4 reads Prometheus + Pushgateway gauges (the window's
                                          #   instrument) and commit A changes what the probe pushes.
                                          # storage/longhorn: the two session PVCs (no engine change).
                                          # apple-id-2fa: a failed auth burns Apple's per-day 2FA send quota for
                                          #   that Apple ID — the gate in §3.3 is built so it never triggers a push.
depends_on: []
conflicts_with:
  - app-template-5.2.1                  # edits the SAME two helmrelease.yaml files (chart 5.1.0->5.2.1, findings
                                        #   F-dfd6adca/F-68589ebb) and upgrades the SAME HRs; two writers on one
                                        #   file/HR in one window make either verification unattributable.
  - helm-drift-detection                # adds spec.driftDetection to every HR incl. both icloud HRs
  - flux-reconciler-impersonation       # changes the identity helm-controller applies backup/ with (exclusive)
  - flux-oci-chart-sources              # rewrites bjw-s app-template chart sources — same spec.chart block
  - flux-fleet-0.60.0                   # restarts helm/kustomize-controller mid-way through our suspend/resume
  - longhorn-1.13.0                     # storage engine bump under both session PVCs; also touches cifs/backups
  - talos-linux-1.14.2                  # node roll reschedules both pods mid-verification (exclusive anyway)
exclusive: false
security_ref: F-b2c35615                # AR-029 record on `mandarons/icloud-drive:main` ("already on newest").
                                        # A newer RELEASE exists (2.1.0), so that acceptance's premise lapses for
                                        # this image; the first sweep after the bump re-evaluates it. Detail
                                        # stays on the DB record — nothing about it is restated here.
capability_change: true                 # HONEST, not "to be safe". 2.x adds an embedded web UI (OFF by default,
                                        # not enabled here), Telegram-listen 2FA (opt-in, not enabled), and two
                                        # DEFAULT-ON behaviour changes that do apply to us: proactive trust-token
                                        # refresh (app.trust_refresh_days default 14, re-mints the Apple trust
                                        # cookie) and non-2FA sign-in failures backing off >=30 min instead of
                                        # crash-looping (#529). Drive packages are now unpacked/kept, i.e. new
                                        # trees appear on the share. => HUMAN-GATED, attended window.
rollback_class: git-revert              # image pin revert per instance. Nothing forward-only on the share
                                        # (remove_obsolete=false; v2 only ADDS unpacked package trees). The
                                        # session cookie jar format is unchanged (icloudpy 0.9.0 and 0.10.0 share
                                        # the LWPCookieJar code), so the old image reads what v2 writes; the
                                        # in-PVC session copy from §3.2 + the 03:00 Longhorn backup are the
                                        # contingency restore (§5.2), not the expected path.
finding_refs: [F-fb05162a]              # mu: 10 Drive items fail every drive cycle (package bundles + 1 Apple
                                        # "Unknown reason"). `policy-cli.py finding list --grep icloud` 2026-10-03:
                                        # F-fb05162a (plan, this), F-b2c35615 (AR-029, cited above), F-dfd6adca /
                                        # F-68589ebb (chart 5.2.1 — owned by app-template-5.2.1), F-f9db709b
                                        # (photos 503 item — NOT claimed; may or may not clear, see §4.6).
review: null
status: draft
window: null
premises:
  - id: live-image-is-main-build
    why: >-
      current and the rollback target assume BOTH deployments run the main@91486ec1
      build. If a Step 0 lane or a hand edit already moved either, this plan is stale.
    run: kubectl get deploy -n backup icloud-docker-mu icloud-docker-andrea -o jsonpath='{.items[*].spec.template.spec.containers[0].image}'
    expect_exact: "mandarons/icloud-drive:main@sha256:91486ec1eaeb382e7af264b7ffa935c5ba110f11c3c2f1805976782ff5017917 mandarons/icloud-drive:main@sha256:91486ec1eaeb382e7af264b7ffa935c5ba110f11c3c2f1805976782ff5017917"
  - id: manifest-pin-once-per-file
    why: >-
      §3.4/§3.6 rewrite exactly one tag line (plus its comment block) per file;
      the edit script asserts a single anchor and was dry-tested on copies of both.
    run: grep -c 'tag. "main@sha256:91486ec1eaeb382e7af264b7ffa935c5ba110f11c3c2f1805976782ff5017917"' kubernetes/apps/backup/icloud-docker-mu/app/helmrelease.yaml kubernetes/apps/backup/icloud-docker-andrea/app/helmrelease.yaml
    expect_matches: '(?s)icloud-docker-mu/app/helmrelease\.yaml:1\s+.*icloud-docker-andrea/app/helmrelease\.yaml:1\s*$'
  - id: hrs-ready
    why: A reconcile already failing would make the §4 gates unattributable.
    run: kubectl get helmrelease -n backup icloud-docker-mu icloud-docker-andrea -o jsonpath='{.items[*].status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True True"
  - id: mu-config-safe
    why: >-
      "No re-download / no reorganise" (§1.3) rests on: remove_obsolete false for
      drive AND photos, and none of the 2.x layout/exposure keys set (web_ui,
      library_destinations, flatten_packages, filename_format, file_format).
      The count is 2 only if both remove_obsolete:false lines exist and no
      layout key is present. Reads counts only, never prints the config.
    run: kubectl get configmap -n backup icloud-docker-mu-config -o jsonpath='{.data.config\.yaml}' | grep -c -e 'remove_obsolete. false' -e web_ui -e library_destinations -e flatten_packages -e filename_format -e file_format
    expect_exact: "2"
  - id: andrea-config-safe
    why: Same as mu-config-safe, for andrea.
    run: kubectl get configmap -n backup icloud-docker-andrea-config -o jsonpath='{.data.config\.yaml}' | grep -c -e 'remove_obsolete. false' -e web_ui -e library_destinations -e flatten_packages -e filename_format -e file_format
    expect_exact: "2"
  - id: no-exposure-in-backup-ns
    why: >-
      The web UI must not become reachable. Today the backup namespace has no
      Service and no HTTPRoute; 2.1.0 EXPOSEs 8080 in the image but app-template
      renders no Service (service.main.enabled false). If anything appeared here,
      re-check exposure before the bump.
    run: kubectl get httproute,service -n backup -o name | wc -l
    expect_matches: '^\s*0\s*$'
  - id: mu-session-backup-enrolled
    why: §5.2 last-resort restore uses the nightly Longhorn backup of the session volume.
    run: kubectl get volume -n storage icloud-docker-mu-session -o jsonpath='{.metadata.labels}'
    expect_contains: "recurring-job-group.longhorn.io/default"
  - id: andrea-session-backup-enrolled
    why: >-
      Same for andrea. Its session PV is dynamic (pvc-f6ec0213-…, the volumeName
      of PVC icloud-docker-andrea-session on 2026-10-03); if the PVC was ever
      recreated this name no longer exists and the premise fails, which is the
      point — re-resolve before relying on §5.2.
    run: kubectl get volume -n storage pvc-f6ec0213-4b00-49d9-93b4-954d5fee1d31 -o jsonpath='{.metadata.labels}'
    expect_contains: "recurring-job-group.longhorn.io/default"
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/icloud-docker-reauth.md
  - docs/sops/storage-safety.md
  - docs/sops/longhorn.md
  - docs/sops/backup.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-10-03"
---

# icloud-docker (mu + andrea): `main@91486ec1` -> release 2.1.0

## 1. Summary & why held

**Change (per instance, mu first):** in
`kubernetes/apps/backup/icloud-docker-<instance>/app/helmrelease.yaml` the image
tag `"main@sha256:91486ec1…"` becomes
`"2.1.0@sha256:c57e8248fefc55d490f090eb5edd08ff53045861e4b8f532403926b38af36ba9"`
(plus its comment block). Config, secrets, PVCs, chart (app-template 5.1.0),
`strategy: Recreate` and the pod securityContext are untouched. Two small
companion commits: the sync-probe learns v2's new sign-in-failure line (§3.1),
and the re-auth SOP's throwaway pod image follows the new digest (§3.8).

**Driver:** F-fb05162a — mu's Drive sync fails 10 items on every drive cycle
(live 2026-10-03: `icloud_drive_items_failed{account="mu"} = 10`, failing for
~45 h; andrea `0`). Nine are Apple package bundles the running code rejects
(`Unhandled file type - cannot unpack the package application/octet-stream`,
then an `[Errno 2]` on the `.zip` rename); one is an item Apple answers with
`Unknown reason`.

**Why held:** major version (1.x -> 2.x), not on any safe lane, and the pin is a
floating `main` build with no Renovate PR.

### 1.1 Upstream evidence (verified in source, not only release notes)

Cloned `github.com/mandarons/icloud-docker` and read tag `v2.1.0`; copied
`/app/src` out of the running mu pod to diff against it.

- **Package fix is real and in 2.1.0** (CHANGELOG 2.1.0 "Fixed"; code in
  `src/drive_package_processing.py`): *"Package extraction is gated on
  `zipfile.is_zipfile()` rather than the libmagic MIME string, which reports
  `application/octet-stream` for many of Apple's packageDownload zips.
  Previously those packages were never unpacked"* (#525/#526). Unrecognised
  non-zip bundles are now kept as a single file (`keeping as single-file
  bundle`, #461 — `drive.flatten_packages` is the opt-in to keep ALL packages
  flat; default `False`, we do not set it). *"Drive packages … are no longer
  re-downloaded on every sync"* (#526) and flat bundles likewise (#473/#550).
  Bare-rooted iWork zips extract into their own bundle dir, so two siblings no
  longer collide (#473). `is_zipfile` is first introduced by `a6d562be0`,
  contained in `v2.1.0` only (not `v2.0.0`). The running code's
  `Unhandled file type - cannot unpack` string does not exist in 2.1.0.
- **icloudpy 0.9.0 -> 0.10.0** (`requirements.txt`). Diffed both wheels from
  PyPI: `base.py` only ADDS security-key (WebAuthn) methods;
  `trigger_2fa_push_notification`, `validate_2fa_code`, `trust_session`,
  `_authenticate_with_token` and the cookie-jar code are unchanged;
  `services/drive.py` forwards a timeout. The "Unknown reason" item is
  Apple-side; whether 0.10.0 changes it is unknown — expected residual = 1.
- **Not the cause, but noted:** 2.0.0 also only adds per-library destinations
  (opt-in) and the web UI (opt-in).

### 1.2 Auth / keyring — no re-auth expected (and it is gated, not assumed)

- Session cookies live on `/config/session_data` (Longhorn PVC); same
  `DEFAULT_COOKIE_DIRECTORY` in both versions, same icloudpy cookie code.
- The "keyring ownership change" is `docker-entrypoint.sh`: 2.1.0 runs
  `chown -R abc:abc /config/session_data /config/python_keyring` on every start
  (#549). Live: `/config/session_data` is already `1000:1000` and `abc` is
  remapped to uid 1000 by `PUID=1000`, so the chown is a no-op. No
  fsGroup/securityContext change is needed.
- `/config/python_keyring` is NOT persistent here (only `config.yaml` and
  `session_data` are mounted; `/config` is container overlay). The password is
  re-stored from `ENV_ICLOUD_PASSWORD` on every start in both versions
  (`sync.py: if ENV_ICLOUD_PASSWORD_KEY in os.environ: store_password_in_keyring`).
  The 1.26/1.27 keyring migration therefore has nothing to migrate. Both pods
  restarted 3x in the last week on the current image without a 2FA prompt.
- Trust cookie (`X-APPLE-WEBAUTH-HSA-TRUST`) expiry read from the jar
  (no network): mu 2026-12-24, andrea 2026-12-25 — ~82 days of headroom.
  2.1.0's default `trust_refresh_days: 14` will re-mint it in mid-December,
  which REDUCES the next forced re-auth risk. Residual (low): if Apple were to
  reject the stored trust token, icloudpy falls back to an SRP password
  sign-in, which can surface a sign-in prompt on older trusted devices even
  though no code is requested; with the cookies valid to 2026-12-24/25 and
  both pods restarting cleanly on them this week, this is not expected.
- **Gate, not assumption:** §3.3 runs the 2.1.0 image with `--dry-run` against
  the real session. Its code (`sync.py` ~L1467) logs
  `DRY RUN: 2FA required — finish interactive auth first` and **returns
  without requesting a push** when a second factor is needed. On a NON-2FA
  sign-in failure it does NOT return: `_handle_auth_transport_error`
  (`sync.py` ~L1161-1190) logs `Sign-in failed and will be retried`, sends the
  configured Telegram notification, sleeps >= 30 min and would sign in again —
  so §3.3 polls the log for at most 10 min and kills the pod at the first
  auth line. Net: at most ONE Apple sign-in per instance, never a push. Only a
  PASS proceeds to the commit.
- **Re-auth needed? Expected NO.** Phones are only needed on the contingency
  branch (§3.3 STOP-AUTH -> leave the instance on the old image; the old image
  keeps working since nothing was committed). mu's operator phone should be at
  hand in the attended window; Andrea's phone is needed only if andrea's dry-run
  says STOP-AUTH, and then the andrea half is simply deferred.

### 1.3 Destination layout — unchanged, no re-download (verified in code)

- `photos.library_destinations` default `{}` -> `_library_destination()`
  returns the base destination unchanged (`sync_photos.py:512-545`). Path is
  still `<root>/photos/all/<%Y/%m>/<name>__original__<id>.<ext>`
  (`_sync_all_photos_in_library` -> `os.path.join(destination_path, "all")`
  in both versions; live share has exactly one top-level dir `all/` for both
  accounts).
- `photos.filename_format` default `"metadata"` (the historical
  `name__size__id` form); `photo.created.strftime(folder_format)` and
  `check_photo_exists` (size compare) are byte-identical between versions;
  icloudpy's `created`/`asset_date` is identical in 0.9.0 and 0.10.0.
- Legacy renames: 2.1.0 adds a `live_video_*` self-heal only; we sync
  `file_sizes: [original]`, so it does not apply.
- `remove_obsolete: false` for drive and photos (premise); 2.1.0 also adds a
  25 % obsolete-delete ceiling — irrelevant while false. **Must stay false.**
- Drive: same mirror-tree layout. First v2 drive cycle downloads the 9
  previously failing packages once and unpacks them (new trees, additive).
- **Gate, not assumption:** §3.3's `--dry-run --check-files 200`
  (`src/migration_check.py`, "Pure read: no downloads … no cookie writes" —
  it does write the session cookie on sign-in like any cycle) computes the
  exact on-disk path v2 would use for the newest 200 photos per library and
  200 Drive files and reports `would_skip / size_mismatch / not_found`. A
  layout change shows up as mass `not_found`.

### 1.4 Web UI — stays off and unexposed

`app.web_ui.enabled` default **False** (`config_parser.get_web_ui_enabled`),
bind host default `127.0.0.1`; neither config sets `app.web_ui` (premise). The
image `EXPOSE`s 80/8080, but app-template renders no Service
(`service.main.enabled: false`) and there is no HTTPRoute in `backup` (premise).
§4.4 asserts nothing listens on 8080 inside the pod.

### 1.5 Monitoring continuity — log formats unchanged, ONE behaviour gap fixed here

Grepped every string the probe (`sync-probe-configmap.yaml`) parses in the
running source and in 2.1.0: `Syncing photos...`, `Photos synced`,
`Syncing drive...`, `Drive synced`, `Starting parallel downloads with N threads
for M files...`, `Parallel downloads completed: S successful, F failed`,
`drive_file_download.py :: <n> :: Downloading <path> ...`, `Failed to download`,
`Error: 2FA is required. Please log in.`, `Password is not stored in keyring.`
— all present with identical text; the console formatter is unchanged
(`src/__init__.py` diff touches only rotation + config guards). So **no
detector goes blind**; the gauges keep updating.

**Behaviour gap (#529):** the running image crashes on a non-2FA sign-in
failure (wrong password, Apple 409 throttle / pending-terms, invalid token) —
that crash-loop is what `ICloudBackupDeploymentUnavailable` (30 m) catches
today. 2.1.0 instead logs `Sign-in failed and will be retried: <reason>` and
backs off >= 30 min with the pod Running, so DeploymentUnavailable no longer
fires and `icloud_auth_required` stays 0 (the probe's `RE_AUTH` does not know
the line). Only `ICloudBackupSyncStalled` (6 h) would catch it. §3.1 adds the
three icloudpy `ICloudPyFailedLoginException` texts after that prefix to
`RE_AUTH` (a plain network fault at sign-in is deliberately left to
SyncStalled). The handler formats `{error!s}` of a two-argument exception, so
the REAL line is a tuple repr — rendered with icloudpy 0.10.0's own exception
classes: `Sign-in failed and will be retried: ('Invalid email/password
combination.', ICloudPyAPIResponseException('Unauthorized (401)'))`. The
pattern therefore allows anything between the prefix and the reason (`: .*(`).
Dry-tested on a scratch copy with that exact line (and a `Failed to initiate
srp authentication.` / 409 variant): -> 1; clean log -> 0; network fault
`HTTPSConnectionPool(...)` -> 0; the UNEDITED probe returns 0 for the real
lines (the control that shows the gap exists); and the full
`runbooks/tests/test-icloud-drive-probe.py` (incl. `promtool test rules`)
passes against the edited copy.

## 2. Pre-checks

Run from the repo root on the Mac mini (zsh). `export PATH="$HOME/.local/share/mise/shims:$PATH"` first.

**2.1 Premises:** `.venv/bin/python3 runbooks/plan-premises.py icloud-docker-2.1.0` — all PASS, else STOP.

**2.2 Upstream digest unchanged** (a re-pushed `2.1.0` would invalidate §1):
```bash
TOKEN=$(curl -s "https://auth.docker.io/token?service=registry.docker.io&scope=repository:mandarons/icloud-drive:pull" | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
curl -sI -H "Authorization: Bearer $TOKEN" -H 'Accept: application/vnd.oci.image.index.v1+json' \
  https://registry-1.docker.io/v2/mandarons/icloud-drive/manifests/2.1.0 | grep -i docker-content-digest
```
PASS: `sha256:c57e8248fefc55d490f090eb5edd08ff53045861e4b8f532403926b38af36ba9`. Anything else (or empty) -> STOP.

**2.3 Session backups fresh** (03:00 recurring job; §5.2 floor):
```bash
kubectl get volume -n storage icloud-docker-mu-session pvc-f6ec0213-4b00-49d9-93b4-954d5fee1d31 \
  -o custom-columns=NAME:.metadata.name,STATE:.status.state,ROBUST:.status.robustness,LAST_BACKUP:.status.lastBackupAt
```
PASS: both rows `ROBUST`=`healthy` (STATE reads `attached`), `LAST_BACKUP` = today ~03:0x **UTC** (the RecurringJob fires 03:00; Longhorn reports UTC timestamps). If stale, cross-check per `docs/sops/backup.md` "lastBackupAt Can Lag".

**2.4 Baseline gauges** (record the numbers in the window log):
```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
q(){ curl -s http://localhost:19090/api/v1/query --data-urlencode "query=$1" | python3 -c 'import sys,json; r=json.load(sys.stdin)["data"]["result"]; print(" ".join(x["metric"].get("account","?")+"="+x["value"][1] for x in r) or "EMPTY")'; }
q 'max by (account) (icloud_drive_items_failed)'          # 2026-10-03: mu=10 andrea=0
q 'max by (account) (icloud_sync_items_failed)'           # 2026-10-03: mu=1  andrea=0
q 'max by (account) (icloud_auth_required)'               # must be 0 0 — else STOP (fix auth first, SOP)
q 'time() - max by (account) (icloud_sync_last_success_timestamp_seconds)'   # must be < 3600 for both
kill $PF 2>/dev/null
```
`EMPTY` on any line = the instrument is missing -> STOP (do not read it as 0).

**2.5 Trust headroom** (no network; prints only cookie name + date):
```bash
for i in mu andrea; do kubectl -n backup exec deploy/icloud-docker-$i -c app -- python3 -c '
import glob,os,http.cookiejar,datetime
for f in glob.glob("/config/session_data/*"):
    if f.endswith(".session") or ".backup." in f or os.path.isdir(f): continue
    j=http.cookiejar.LWPCookieJar(f); j.load(ignore_discard=True, ignore_expires=True)
    print([(c.name, datetime.datetime.utcfromtimestamp(c.expires).date()) for c in j if "TRUST" in c.name])'; done
```
PASS: an expiry >= 14 days out for each (2026-10-03: 2026-12-24 / 2026-12-25). Closer -> proceed only with the phone of that Apple ID at hand.

**2.6 No in-flight work:** `flux get hr -n backup` both `Ready True`, not suspended; no `icloud-reauth-*` / `icloud-v2-dryrun-*` pod exists (`kubectl -n backup get pod -o name | grep -E 'reauth|dryrun'` prints nothing).

## 3. Steps

Each commit: write the message to a UNIQUE file, `git commit --only <paths> -F <file>`, then `git log -1 --format=%s` must show YOUR subject and `git show --stat HEAD` only your paths, before `git push`. Never source the sweep DSN in the same shell as `git commit`.

### 3.1 Commit A — probe learns v2's sign-in-failure line (lands first, harmless on the old image)

```bash
python3 - kubernetes/apps/backup/icloud-backup-freshness/app/sync-probe-configmap.yaml <<'PY'
import sys
p=sys.argv[1]; t=open(p).read()
old='        r"|Authentication required for Account|\\(421\\)|INCORRECT_PCS_KEY",\n'
new=('        r"|Authentication required for Account|\\(421\\)|INCORRECT_PCS_KEY"\n'
     '        # icloud-docker >= 2.1.0 (#529) no longer crash-loops on a non-2FA sign-in\n'
     '        # failure; it backs off >= 30 min and logs this line instead. The error is\n'
     '        # rendered as a tuple repr: "...retried: (\'Invalid email/password ...\', ...)".\n'
     '        # Only the icloudpy ICloudPyFailedLoginException texts count as auth -- a\n'
     '        # plain network fault at sign-in is left to ICloudBackupSyncStalled.\n'
     '        r"|Sign-in failed and will be retried: .*(Invalid email/password|Invalid authentication token|Failed to initiate srp)",\n')
assert t.count(old)==1, t.count(old)
open(p,"w").write(t.replace(old,new)); print("edited")
PY
git diff --stat kubernetes/apps/backup/icloud-backup-freshness/app/sync-probe-configmap.yaml   # 1 file, +7 -1
```
Gate — the edited probe must flag the REAL v2 lines and not a network fault
(any `FAIL` or a non-zero exit -> do not commit):
```bash
cat > /tmp/icloud-probe-gate-check.py <<'EOF'
import sys, yaml, types
src = yaml.safe_load(open(sys.argv[1]))["data"]["icloud_sync_probe.py"]
m = types.ModuleType("p"); exec(compile(src, "p", "exec"), m.__dict__)
T = "2026-10-03T10:%02d:00.000Z x :: "
ok = [T % 0 + "INFO :: sync.py :: 627 :: Syncing photos...", T % 10 + "INFO :: sync.py :: 629 :: Photos synced"]
cases = {
  "clean": (ok, 0),
  "signin-auth-real": (ok + [T % 20 + "ERROR :: sync.py :: 1171 :: Sign-in failed and will be retried: ('Invalid email/password combination.', ICloudPyAPIResponseException('Unauthorized (401)'))"], 1),
  "signin-srp-real": (ok + [T % 20 + "ERROR :: sync.py :: 1171 :: Sign-in failed and will be retried: ('Failed to initiate srp authentication.', ICloudPyAPIResponseException('Conflict (409)'))"], 1),
  "signin-network": (ok + [T % 20 + "ERROR :: sync.py :: 1171 :: Sign-in failed and will be retried: HTTPSConnectionPool(host='idmsa.apple.com', port=443): Read timed out."], 0),
}
bad = 0
for name, (lines, want) in cases.items():
    got = m.analyse([lines], 1759600000).get("icloud_auth_required")
    print(name, got, "ok" if got == want else "FAIL"); bad += got != want
sys.exit(1 if bad else 0)
EOF
.venv/bin/python3 /tmp/icloud-probe-gate-check.py kubernetes/apps/backup/icloud-backup-freshness/app/sync-probe-configmap.yaml   # 4x ok, exit 0
.venv/bin/python3 runbooks/tests/test-icloud-drive-probe.py      # must end "OK: icloud drive probe + alert tests passed"
```
Dry-tested 2026-10-03 on a scratch copy: edited -> 4x `ok`, exit 0; the
UNEDITED configmap -> `signin-auth-real 0 FAIL`, `signin-srp-real 0 FAIL`,
exit 1 (so the gate can fail); test suite `OK`. The real-line text was rendered
with icloudpy 0.10.0's own exception classes. Resulting diff:
```
<         r"|Authentication required for Account|\(421\)|INCORRECT_PCS_KEY",
>         r"|Authentication required for Account|\(421\)|INCORRECT_PCS_KEY"
>         # icloud-docker >= 2.1.0 (#529) no longer crash-loops on a non-2FA sign-in
>         ...
>         r"|Sign-in failed and will be retried: .*(Invalid email/password|Invalid authentication token|Failed to initiate srp)",
```
Recommended in the same commit: add the two real lines above as fixtures to
`runbooks/tests/test-icloud-drive-probe.py` so the suite pins them.
Commit (`fix(icloud-sync-probe): count icloud-docker 2.x sign-in failures as auth-required`), push. Confirm applied:
```bash
kubectl get configmap -n backup icloud-sync-probe -o jsonpath='{.data.icloud_sync_probe\.py}' | grep -c 'Sign-in failed and will be retried'   # 1
```
Wait for the next `*/10` probe Job and check it ends `account=mu pushed` and `account=andrea pushed`:
`kubectl -n backup logs job/$(kubectl -n backup get jobs -o name | grep icloud-sync-probe | sort | tail -1 | cut -d/ -f2)`.

### 3.2 mu — back up the session (in-PVC copy, SOP naming convention)

```bash
export INSTANCE=mu
BK_TS=$(date +%Y%m%d_%H%M%S); echo "BK_TS=$BK_TS"      # write it down: §5.2 needs it
kubectl -n backup exec deploy/icloud-docker-$INSTANCE -c app -- sh -c "cd /config/session_data && for f in *; do case \"\$f\" in *.backup.*|lost+found) continue;; esac; cp -p \"\$f\" \"\$f.backup.$BK_TS\"; done && ls | grep -c 'backup.$BK_TS'"
```
PASS: prints `2` (the cookie jar + the `.session` file). Shell logic dry-tested on a scratch dir with the same name shapes (skips older `*.backup.*` and `lost+found`). File names contain the Apple ID: never paste `ls` output into notes.

### 3.3 mu — stop the loop, then dry-run 2.1.0 against the real session + share

Suspend FIRST, then scale (so no reconcile can race the scale-down):
```bash
flux suspend helmrelease icloud-docker-$INSTANCE -n backup
kubectl -n backup scale deploy icloud-docker-$INSTANCE --replicas=0
kubectl -n backup wait --for=delete pod -l app.kubernetes.io/name=icloud-docker-$INSTANCE --timeout=120s
kubectl -n backup get pod -l app.kubernetes.io/name=icloud-docker-$INSTANCE -o name | wc -l    # 0
```
(`kubectl wait --for=delete -l …` may print "no matching resources found" and
exit non-zero when the pod is already gone — cosmetic; the `wc -l` = `0` line is the check.)

Throwaway pod — NEW image, session RW (it must sign in), share **read-only**,
same env as the HelmRelease. Runs the image's own `--dry-run --check-files 200`
after the same uid remap the entrypoint does (`abc` -> 1000). `/config` itself
is chowned to abc because the app opens `app.logger.filename:
/config/icloud.log` at import time; in this pod `/config` is a root-owned
mountpoint (the real entrypoint chowns it), and without the chown python would
die with a PermissionError before signing in.
```bash
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: icloud-v2-dryrun-$INSTANCE
  namespace: backup
  labels:
    app.kubernetes.io/name: icloud-v2-dryrun-$INSTANCE
spec:
  restartPolicy: Never
  securityContext:
    runAsUser: 0
    runAsGroup: 0
    fsGroup: 1000
    fsGroupChangePolicy: OnRootMismatch
  containers:
    - name: app
      image: mandarons/icloud-drive:2.1.0@sha256:c57e8248fefc55d490f090eb5edd08ff53045861e4b8f532403926b38af36ba9
      command: ["sh", "-c"]
      args:
        - >-
          groupmod -o -g 1000 abc && usermod -o -u 1000 abc &&
          mkdir -p /config/python_keyring && chown abc:abc /config /config/python_keyring &&
          exec su-exec abc sh -c 'cd /app && export PYTHONPATH=/app HOME=/home/abc &&
          exec python ./src/main.py --dry-run --check-files 200'
      env:
        - {name: TZ, value: Europe/Berlin}
        - {name: ENV_CONFIG_FILE_PATH, value: /config/config.yaml}
        - name: ENV_ICLOUD_PASSWORD
          valueFrom: {secretKeyRef: {name: icloud-docker-$INSTANCE-secrets, key: SECRET_ICLOUD_PASSWORD}}
      volumeMounts:
        - {name: config, mountPath: /config/config.yaml, subPath: config.yaml}
        - {name: session, mountPath: /config/session_data}
        - {name: data, mountPath: /icloud, readOnly: true}
  volumes:
    - {name: config, configMap: {name: icloud-docker-$INSTANCE-config}}
    - {name: session, persistentVolumeClaim: {claimName: icloud-docker-$INSTANCE-session}}
    - {name: data, persistentVolumeClaim: {claimName: icloud-docker-$INSTANCE-data, readOnly: true}}
EOF
```
(Validated with `kubectl apply --dry-run=server` for both instances on 2026-10-03; TZ value = the live deployment's `TZ`.)

**Bounded wait — never let it sign in twice.** On a non-2FA sign-in failure the
dry-run does not exit: it logs `Sign-in failed and will be retried`, sends the
configured **Telegram notification** (expect one message to the ops chat on that
branch — it is not a real outage), sleeps >= 30 min and would sign in again.
So poll for at most 10 min and kill the pod at the first auth line:
```bash
for n in $(seq 1 20); do
  sleep 30
  PH=$(kubectl -n backup get pod icloud-v2-dryrun-$INSTANCE -o jsonpath='{.status.phase}')
  kubectl -n backup logs icloud-v2-dryrun-$INSTANCE 2>/dev/null | grep -qiE 'Sign-in failed|2FA required|2FA is required' && { echo "AUTH LINE -> stop"; break; }
  [ "$PH" = Succeeded ] || [ "$PH" = Failed ] && { echo "phase=$PH"; break; }
done
kubectl -n backup logs icloud-v2-dryrun-$INSTANCE > /tmp/icloud-dryrun-$INSTANCE.log 2>&1
kubectl -n backup delete pod icloud-v2-dryrun-$INSTANCE --wait=true     # MUST be gone before the app scales up (RWO session)
```
Gate on counts only — the raw log names personal files; delete it afterwards:
```bash
cat > /tmp/icloud-dryrun-gate.py <<'EOF'
import re, sys
ANSI = re.compile(r"\x1b\[[0-9;]*m")
lines = [ANSI.sub("", l) for l in sys.stdin.read().splitlines()]
def has(p): return any(re.search(p, l, re.I) for l in lines)
auth_ok = has(r"DRY RUN: authentication succeeded")
need_2fa = has(r"DRY RUN: 2FA required|2FA is required")
signin_fail = has(r"Sign-in failed and will be retried")
done = has(r"DRY RUN complete")
tracebacks = sum(1 for l in lines if "Traceback (most recent call last)" in l)
rx = re.compile(r"DRY RUN: (?P<lib>.+?) \(dest .*?\): sampled=(?P<s>\d+) would_skip=(?P<w>\d+) size_mismatch=(?P<m>\d+) not_found=(?P<n>\d+) errors=(?P<e>\d+)")
rows = [m.groupdict() for l in lines for m in [rx.search(l)] if m]
if need_2fa:
    verdict = "STOP-AUTH"            # Apple wants a second factor: do NOT re-run
elif signin_fail:
    verdict = "STOP-SIGNIN"          # password/throttle/terms: do NOT re-run
elif not auth_ok or not done or not rows:
    verdict = "STOP-INCOMPLETE"      # crashed/killed before sign-in or mid-walk: fix + re-run is allowed
else:
    verdict = "PASS"
for r in rows:
    s, w, m, n, e = (int(r[k]) for k in "swmne")
    kind = "drive" if r["lib"] == "Drive" else "photos"
    limit = 20 if kind == "drive" else 10
    bad = (n + e) if kind == "drive" else (m + n + e)  # drive: unpacked packages always size-mismatch (dir sum vs zip size)
    ok = bad <= limit and (s > 0 or kind == "photos") and (kind == "drive" or w >= s - limit)  # an EMPTY photos library may sample 0
    print(f"{kind:6} lib={'Drive' if kind=='drive' else 'lib#'+str(rows.index(r))} sampled={s} would_skip={w} size_mismatch={m} not_found={n} errors={e} -> {'ok' if ok else 'FAIL'}")
    if not ok and verdict == "PASS":
        verdict = "STOP-LAYOUT"
if verdict == "PASS" and not (any(r["lib"] == "Drive" for r in rows) and any(r["lib"] != "Drive" and int(r["s"]) > 0 for r in rows)):
    verdict = "STOP-INCOMPLETE"
print("lines=%d auth_ok=%s need_2fa=%s signin_fail=%s complete=%s tracebacks=%d VERDICT=%s" % (len(lines), auth_ok, need_2fa, signin_fail, done, tracebacks, verdict))
EOF
python3 /tmp/icloud-dryrun-gate.py < /tmp/icloud-dryrun-$INSTANCE.log
rm -f /tmp/icloud-dryrun-$INSTANCE.log
```
Gate controls (synthetic logs, 2026-10-03): realistic -> `PASS`; 200 photos
`not_found` -> `STOP-LAYOUT`; drive 50 `not_found` -> `STOP-LAYOUT`;
`DRY RUN: 2FA required` -> `STOP-AUTH`; the real tuple-repr `Sign-in failed …`
line -> `STOP-SIGNIN`; a `PermissionError` traceback with no sign-in ->
`STOP-INCOMPLETE`; missing `DRY RUN complete` -> `STOP-INCOMPLETE`. Photos
allow <= 10 of 200 not-skip (newest-first sample: photos taken since the last
cycle are legitimately `not_found`); Drive allows <= 20 `not_found`+`errors`
(the 9 failing packages are `not_found` today) and ignores `size_mismatch`
(an unpacked package dir never equals its zip size — `migration_check.py:236-279`).
The drive check is size-only while the real `file_exists` also compares mtime;
`file_exists` is byte-identical between the two versions, and §4.2's
`drive_downloads <= 300` is the real re-download guard.

**Restoring the old image on any STOP** (nothing was committed; `flux resume`
alone does NOT rescale — helm-controller performs no action for an in-sync
release without driftDetection, so the Deployment would stay at 0):
```bash
flux resume helmrelease icloud-docker-$INSTANCE -n backup
kubectl -n backup scale deploy icloud-docker-$INSTANCE --replicas=1
kubectl -n backup rollout status deploy/icloud-docker-$INSTANCE --timeout=300s
kubectl -n backup get pod -l app.kubernetes.io/name=icloud-docker-$INSTANCE -o name | wc -l    # 1
```

- **PASS** -> 3.4.
- **STOP-AUTH / STOP-SIGNIN** -> do NOT re-run (each sign-in attempt costs quota /
  deepens a throttle). Restore the old image (block above) and confirm the old
  pod's log shows `Syncing` and no `2FA is required` / crash within 15 min.
  If the OLD image now also fails auth, the session genuinely expired or the
  account needs attention: `docs/sops/icloud-docker-reauth.md` from Step 1
  (incl. Step 4b terms check; that Apple ID's phone). Mark the plan `blocked`,
  and do not bump the other instance in this window (the verdict contradicts
  §1.2 — re-investigate first).
- **STOP-INCOMPLETE** -> look at `tracebacks` / the pod's last lines (operator
  terminal only). A crash before `authentication succeeded` cost no Apple
  sign-in and may be fixed and re-run ONCE. Otherwise restore the old image and
  mark `blocked`.
- **STOP-LAYOUT** -> restore the old image; mark `blocked` with the counts;
  nothing was written to the share (mounted read-only).

### 3.4 Commit B — mu image pin

```bash
cat > /tmp/icloud-hr-edit.py <<'PY'
import re, sys
p = sys.argv[1]
t = open(p).read()
pat = re.compile(
    r'^( +)# Pinned to the `main` build \(2026-06-06\).*?\n'
    r'(?:\1#.*\n)*?'
    r'\1tag: "main@sha256:91486ec1eaeb382e7af264b7ffa935c5ba110f11c3c2f1805976782ff5017917"\n',
    re.M)
m = pat.search(t)
assert m and len(pat.findall(t)) == 1, "anchor not found exactly once -- STOP"
ind = m.group(1)
new = (
    f"{ind}# Release 2.1.0 (2026-10-01): icloudpy 0.10.0 (keeps 0.9.0's\n"
    f"{ind}# trigger_2fa_push_notification() needed for iOS 26.4+ 2FA), and fixes\n"
    f"{ind}# Drive package handling (#525/#526 is_zipfile, #461, #473, #550).\n"
    f"{ind}# Web UI stays OFF (app.web_ui unset => disabled, loopback-only).\n"
    f"{ind}# KEEP IN SYNC with the other icloud-docker-* instance.\n"
    f"{ind}# See docs/sops/icloud-docker-reauth.md.\n"
    f'{ind}tag: "2.1.0@sha256:c57e8248fefc55d490f090eb5edd08ff53045861e4b8f532403926b38af36ba9"\n'
)
open(p, "w").write(t[:m.start()] + new + t[m.end():])
print("edited", p)
PY
python3 /tmp/icloud-hr-edit.py kubernetes/apps/backup/icloud-docker-mu/app/helmrelease.yaml
git diff kubernetes/apps/backup/icloud-docker-mu/app/helmrelease.yaml    # 7 comment/tag lines -> 7, nothing else
```
Dry-tested on copies of BOTH files 2026-10-03 (mu replaces 6 comment lines + tag;
andrea 8 comment lines incl. its old "KEEP IN SYNC" pair + tag); a second run
aborts with `anchor not found exactly once -- STOP` (idempotence guard).
Parsed result: `{'repository': 'mandarons/icloud-drive', 'tag': '2.1.0@sha256:c57e8248…6ba9', 'pullPolicy': 'IfNotPresent'}`.

Commit (`feat(icloud-docker-mu): mandarons/icloud-drive main build -> 2.1.0`), verify subject, push. Record `SHA_MU=$(git rev-parse HEAD)`.
Wait until the Kustomization applied it (HR is still suspended, so nothing rolls yet):
```bash
flux get kustomization icloud-docker-mu -n backup     # revision main@sha1:<SHA_MU>
kubectl get helmrelease -n backup icloud-docker-mu -o jsonpath='{.spec.values.controllers.main.containers.app.image.tag}'   # 2.1.0@sha256:c57e8248…
```
Then release it (the SOP's resume; it upgrades and rescales to 1):
```bash
T_SWITCH=$(date +%s); echo "T_SWITCH=$T_SWITCH"
flux resume helmrelease icloud-docker-mu -n backup
kubectl -n backup rollout status deploy/icloud-docker-mu --timeout=300s
kubectl -n backup get pod -l app.kubernetes.io/name=icloud-docker-mu -o name | wc -l    # 1
```
Here the resume DOES restore `replicas: 1`: the changed tag makes helm-controller
run an upgrade, and Helm's three-way patch re-applies the rendered `replicas: 1`
(reviewer verified with `helm template` on the live values). If `wc -l` prints 0
after 5 min, `kubectl -n backup scale deploy icloud-docker-mu --replicas=1`.

### 3.5 mu — verify (§4) BEFORE touching andrea

Run §4.1-§4.6 for `INSTANCE=mu`. All PASS -> 3.6. Any FAIL -> §5.1 for mu, and do not start andrea.

### 3.6 andrea — same flow

`export INSTANCE=andrea`, then §3.2 (backup; record a new `BK_TS`), §3.3 (dry-run
+ gate; STOP-AUTH here means only andrea is deferred — mu stays on 2.1.0),
§3.4 with the andrea path (`python3 /tmp/icloud-hr-edit.py kubernetes/apps/backup/icloud-docker-andrea/app/helmrelease.yaml`,
commit `feat(icloud-docker-andrea): mandarons/icloud-drive main build -> 2.1.0`,
`SHA_ANDREA`, `flux get kustomization icloud-docker-andrea -n backup`, new `T_SWITCH`,
`flux resume helmrelease icloud-docker-andrea -n backup`, rollout status).
Note andrea's HR has an explicit `replicas: 1` — resume restores it.

### 3.7 andrea — verify

§4.1-§4.6 for `INSTANCE=andrea` (drive baseline 0, photos baseline 0).

### 3.8 Commit D — re-auth SOP follows the new digest

The SOP's throwaway re-auth pod must run the same image as the HelmRelease (its
own comment says so). Only after BOTH instances passed:
```bash
cat > /tmp/icloud-sop-edit.py <<'PY'
import sys
p = sys.argv[1]; t = open(p).read()
D_OLD = "main@sha256:91486ec1eaeb382e7af264b7ffa935c5ba110f11c3c2f1805976782ff5017917"
D_NEW = "2.1.0@sha256:c57e8248fefc55d490f090eb5edd08ff53045861e4b8f532403926b38af36ba9"
reps = [
    ("      image: mandarons/icloud-drive:" + D_OLD + "\n",
     "      image: mandarons/icloud-drive:" + D_NEW + "\n"),
    ("**Image requirement:** the icloud-docker `:latest`/release tag (v1.25.0) still\n"
     "bundles the broken icloudpy 0.8.0. The HelmRelease is therefore pinned to the\n"
     "`main` build digest (`sha256:91486ec1…`, icloudpy 0.9.0). If you ever see the\n"
     "script print `icloudpy < 0.9.0 in this image`, the pin regressed — restore it.\n",
     "**Image requirement:** both HelmReleases pin release `2.1.0` by digest\n"
     "(`sha256:c57e8248…`, icloudpy 0.10.0, which keeps `trigger_2fa_push_notification()`).\n"
     "Release v1.25.0 and older bundle the broken icloudpy 0.8.0; until the 2.1.0\n"
     "upgrade the pin was a `main` build (`sha256:91486ec1…`). If you ever see the\n"
     "script print `icloudpy < 0.9.0 in this image`, the pin regressed — restore it.\n"),
    ("      # MUST be the same pinned digest as the HelmRelease. `:latest` (v1.25.0)\n"
     "      # ships icloudpy 0.8.0, which has no trigger_2fa_push_notification() —\n",
     "      # MUST be the same pinned digest as the HelmRelease. Releases <= v1.25.0\n"
     "      # ship icloudpy 0.8.0, which has no trigger_2fa_push_notification() —\n"),
    ("0.9.0 build (tag `main`, digest sha256:91486ec1…) and retry.",
     ">= 0.9.0 build (release 2.1.0, digest sha256:c57e8248…) and retry."),
    ("| Auth library | `icloudpy` 0.9.0 via the pinned image digest",
     "| Auth library | `icloudpy` 0.10.0 (icloud-docker 2.1.0) via the pinned image digest"),
]
for old, new in reps:
    n = t.count(old)
    assert n == 1, (n, old[:60])
    t = t.replace(old, new)
open(p, "w").write(t); print("sop edited")
PY
python3 /tmp/icloud-sop-edit.py docs/sops/icloud-docker-reauth.md && git diff --stat docs/sops/icloud-docker-reauth.md
```
Dry-tested on a copy 2026-10-03 (5 replacements: pod image line ~138 and its `:latest (v1.25.0)` comment ~134, the script's `main`/91486ec1 hint ~185, paragraph 64-67, table row 91; afterwards `91486ec1` survives only in the historical sentence). Also bump the SOP header `Version`/`Last Updated` to the execution date and add a one-line changelog row. Commit (`docs(icloud-docker-reauth): re-auth pod image follows the 2.1.0 pin`), verify subject, push. If only mu was upgraded, do NOT run this — the re-auth pod must match andrea's still-old image too; note it as owed instead.

### 3.9 Close-out

`policy-cli.py finding close F-fb05162a --commit <SHA_MU>` only if §4.2 drove mu's drive failures to <= 2; otherwise update its action text with the measured count. Retire the plan file in the same commit as Commit D (or a follow-up) per the plans README.

## 4. Verification (per instance, after its §3.4 resume)

`INSTANCE` and `T_SWITCH` set from §3.4. Prometheus helper (re-establish after every Recreate):
```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
q(){ curl -s http://localhost:19090/api/v1/query --data-urlencode "query=$1" | python3 -c 'import sys,json; r=json.load(sys.stdin)["data"]["result"]; print(r[0]["value"][1] if r else "EMPTY")'; }
```
`EMPTY` always means FAIL/NOT-YET, never 0.

**4.1 The new image is what runs** (rollout status green-lights the OLD generation too):
```bash
kubectl -n backup get pod -l app.kubernetes.io/name=icloud-docker-$INSTANCE -o jsonpath='{.items[*].status.containerStatuses[*].imageID}'
```
PASS: exactly one pod, imageID contains `sha256:c57e8248fefc55d490f090eb5edd08ff53045861e4b8f532403926b38af36ba9` (index digest) or its linux/amd64 manifest `sha256:75721c55632d…`; restartCount 0. Fails if Flux remediation rolled back to the main build (would show `91486ec1…`/its manifest).

**4.2 Logs of the new pod — auth held, no mass download, packages handled** (poll every 10 min; mu needs ~50 min for drive+photos, andrea ~15):
```bash
cat > /tmp/icloud-v2-log-gate.py <<'PY'
import re, sys
ANSI = re.compile(r"\x1b\[[0-9;]*m")
L = [ANSI.sub("", l) for l in sys.stdin.read().splitlines()]
def c(p): return sum(1 for l in L if re.search(p, l, re.I))
auth = c(r"2FA is required|Sign-in failed and will be retried|Authentication required for Account|\(421\)|Password is not stored in keyring|INCORRECT_PCS_KEY")
drive_start, drive_done = c(r":: Syncing drive\.\.\."), c(r":: Drive synced")
photos_done = c(r":: Photos synced")
photo_dl = c(r"photo_file_utils\.py :: \d+ :: Downloading ")
drive_dl = c(r"drive_file_download\.py :: \d+ :: Downloading ")
unpacked = c(r"Successfully unpacked the package|keeping as single-file bundle")
old_marker = c(r"Unhandled file type - cannot unpack")
traceback = c(r"Traceback \(most recent call last\)")
print(f"lines={len(L)} auth_errors={auth} drive_start={drive_start} drive_done={drive_done} photos_done={photos_done} "
      f"photo_downloads={photo_dl} drive_downloads={drive_dl} packages_handled={unpacked} old_unpack_errors={old_marker} tracebacks={traceback}")
v = "PASS"
if len(L) == 0: v = "FAIL-NO-LOGS"
elif auth: v = "FAIL-AUTH"
elif old_marker: v = "FAIL-OLD-CODE"
elif drive_start == 0: v = "WAIT-OR-FAIL-NO-DRIVE-START"
elif drive_done == 0 or photos_done == 0: v = "WAIT"
elif photo_dl > 100: v = "FAIL-MASS-PHOTO-DOWNLOAD"
elif drive_dl > 300: v = "FAIL-MASS-DRIVE-DOWNLOAD"
elif len(sys.argv) > 1 and sys.argv[1] == "mu" and unpacked == 0: v = "FAIL-NO-PACKAGES-HANDLED"
print("VERDICT=" + v)
PY
kubectl -n backup logs deploy/icloud-docker-$INSTANCE -c app | python3 /tmp/icloud-v2-log-gate.py $INSTANCE
```
PASS criteria and what each failure prints:
- `auth_errors=0` — FAIL-AUTH if any 2FA/421/sign-in/keyring line (go to §5.1 immediately; do not let it loop: `kubectl -n backup scale deploy icloud-docker-$INSTANCE --replicas=0` + `flux suspend` first, per the SOP's quota rule).
- `drive_start>=1` within 10 min of start (drive runs first at startup — `sync.py` L509 before L592). Absent after 15 min with the pod Running -> FAIL (wedged before auth).
- `drive_done>=1` and `photos_done>=1` — `WAIT` until then; mu not done after 90 min -> check progress (`drive_downloads` still rising = slow first cycle, extend to 150 min; flat = FAIL).
- `photo_downloads <= 100` — a layout/naming change would re-download the library (thousands of lines). Live control: the OLD image's mu log logged 176 photo downloads in 24 h (~7 per cycle, incl. the one 503 item), so <= 100 over one-two cycles is a real ceiling.
- `drive_downloads <= 300`; `old_unpack_errors=0` (the string does not exist in 2.1.0 — a hit means the old code is running).
- mu only: `packages_handled >= 1` (the 9 packages are now unpacked or kept; a floor, so "nothing happened" cannot pass) — enforced in the VERDICT (`FAIL-NO-PACKAGES-HANDLED`, keyed on the `$INSTANCE` argument) once drive+photos are done. Controls: synthetic mu log without an unpack line -> `FAIL-NO-PACKAGES-HANDLED`; same log as `andrea` -> `PASS`; with `Successfully unpacked the package` -> `PASS`.
Live negative control 2026-10-03: the same script on mu's current (old-image) 24 h log prints `old_unpack_errors=24 … VERDICT=FAIL-OLD-CODE`; synthetic controls: 2FA line -> `FAIL-AUTH`, 150 photo downloads -> `FAIL-MASS-PHOTO-DOWNLOAD`, no `Photos synced` -> `WAIT`, empty input -> `FAIL-NO-LOGS`.

**4.3 CONTENTS ASSERTION: the Drive failing set shrank — measured by the probe on a cycle that ran on 2.1.0.**
After the first `Drive synced` of the new pod, wait for the next `*/10` probe run, then:
```bash
echo "drive_cycle_after_switch=$(q "max(icloud_drive_sync_last_success_timestamp_seconds{account=\"$INSTANCE\"}) - $T_SWITCH")"   # must be > 0
echo "drive_items_failed=$(q "max(icloud_drive_items_failed{account=\"$INSTANCE\"})")"
```
Read `drive_items_failed` ONLY once `drive_cycle_after_switch > 0` (until then Pushgateway still holds the old image's value — the probe omits gauges it cannot establish).
- mu: PASS `<= 2` (expected 1: the Apple "Unknown reason" item). `3..10` = fix incomplete, no regression -> keep 2.1.0, record count on F-fb05162a. `> 10` = regression -> §5.1.
- andrea: PASS `<= 1` (baseline 0).
CONTROL: metric icloud_drive_items_failed — failed downloads in the newest completed drive cycle; band above.
CONTROL: metric icloud_drive_sync_last_success_timestamp_seconds — must exceed T_SWITCH (a v2 cycle completed and was observed).

**4.4 Web UI not listening** (inside the app pod; `/proc/net/tcp*` field 2 = local addr, field 4 `0A` = LISTEN, 8080 = `1F90`):
```bash
kubectl -n backup exec deploy/icloud-docker-$INSTANCE -c app -- sh -c 'cat /proc/net/tcp /proc/net/tcp6 2>/dev/null' > /tmp/icloud-sockets-$INSTANCE.txt
grep -c 'local_address' /tmp/icloud-sockets-$INSTANCE.txt                                           # table headers read: must be >= 1
awk '$4=="0A"{print $2}' /tmp/icloud-sockets-$INSTANCE.txt | grep -ic ':1F90'                       # listeners on 8080
```
PASS: table headers `>= 1` (every successful read of `/proc/net/tcp*` starts
with a `sl local_address rem_address st …` header, whatever sockets exist — an
empty read, wrong container or exec error prints `0` here and FAILS the gate
instead of passing as "no listener"; the socket ROW count is not usable as the
proof: the second review measured 2 rows every sample and andrea had no
ESTABLISHED socket at all, only CLOSE_WAIT) AND listeners on 8080 = `0`. Live 2026-10-03 (old image): mu and andrea both headers `2` (tcp + tcp6), listeners `0`; empty input -> headers `0`. Control: `printf ' 0: 0100007F:1F90 00000000:0000 0A\n' | awk '$4=="0A"{print $2}' | grep -ic ':1F90'` prints `1`. Plus `kubectl get httproute,service -n backup -o name | wc -l` still `0`.

**4.5 Photos still syncing on 2.1.0:**
```bash
echo "photos_after_switch=$(q "max(icloud_sync_last_success_timestamp_seconds{account=\"$INSTANCE\"}) - $T_SWITCH")"   # > 0
echo "photos_failed=$(q "max(icloud_sync_items_failed{account=\"$INSTANCE\"})")"   # <= baseline + 1 (mu 1->2, andrea 0->1)
echo "auth_required=$(q "max(icloud_auth_required{account=\"$INSTANCE\"})")"      # 0
echo "probe_age=$(q "time() - max(icloud_sync_probe_last_success_timestamp_seconds{account=\"$INSTANCE\"})")"   # < 1200
kubectl -n backup exec deploy/icloud-docker-$INSTANCE -c app -- ls -1 /icloud/photos    # exactly: all
```
CONTENTS ASSERTION: the photo tree layout is unchanged — `/icloud/photos` still has exactly one entry `all` (baseline 2026-10-03, both accounts); a `library_destinations`/layout change would add sibling dirs.
CONTROL: metric icloud_sync_last_success_timestamp_seconds — newest `Photos synced` must be after T_SWITCH.
CONTROL: metric icloud_sync_items_failed — photo failures in the newest cycle, <= baseline + 1.
CONTROL: metric icloud_auth_required — 0.
CONTROL: metric icloud_sync_probe_last_success_timestamp_seconds — probe observed the account within 20 min.

**4.6 Alerts quiet:**
```bash
curl -s http://localhost:19090/api/v1/alerts | python3 -c 'import sys,json
for a in json.load(sys.stdin)["data"]["alerts"]:
    l=a["labels"]
    if l["alertname"].startswith("ICloud") and a["state"]=="firing": print(l["alertname"], l.get("account"))'
kill $PF 2>/dev/null
```
CONTROL: alertname ICloudBackupAuthRequired — not firing for the instance.
CONTROL: alertname ICloudBackupDeploymentUnavailable — not firing (it can be pending for the ~10 min of scale-0; must clear after resume).
CONTROL: alertname ICloudBackupSyncStalled — not firing.
CONTROL: alertname ICloudDriveSyncStalled — not firing.
Pre-existing and expected: `ICloudBackupPersistentDownloadFailures` (mu, the photos 503 item, F-f9db709b) and `ICloudDrivePersistentDownloadFailures` (mu) — the latter should resolve within 24 h if 4.3 reads <= 1 and the residual item is the same one (it keeps the "failing since" age of the Unknown-reason item, so it may legitimately stay; judge by 4.3, not by this alert).

**4.7 Morning-after soak (next sweep):** `icloud_drive_items_failed{account="mu"}` still <= 2 on the second v2 drive cycle (proves #526's "no re-download each sync" — `drive_downloads` in the second cycle should be ~0-1, versus ~10 per cycle on the old image), both accounts' last-success ages < 6 h.

## 5. Rollback

### 5.1 Image rollback (per instance — the other instance is unaffected)

1. If the instance is looping on auth: stop it first (quota): `kubectl -n backup scale deploy icloud-docker-$INSTANCE --replicas=0; flux suspend helmrelease icloud-docker-$INSTANCE -n backup`.
2. Restore the exact pre-change file without touching the shared index:
```bash
SHA=$SHA_MU   # or $SHA_ANDREA
F=kubernetes/apps/backup/icloud-docker-$INSTANCE/app/helmrelease.yaml
git show "$SHA^:$F" > "$F" && git diff --stat "$F"
git commit --only "$F" -F <unique-msg-file>     # "revert(icloud-docker-<instance>): back to main@91486ec1 (2.1.0 failed <gate>)"
git log -1 --format=%s && git show --stat HEAD && git push
```
3. **Wait until the revert is the HelmRelease spec — BEFORE any resume, force-reconcile or scale.**
   A forced upgrade of a spec that still says 2.1.0 would restore `replicas: 1` on
   the FAILED image, and on the FAIL-AUTH branch 2.1.0's `_handle_2fa_required`
   (`sync.py` ~L995-1011, `_request_2fa_push_once`) would request a 2FA push and
   send a Telegram message — exactly what this rollback exists to stop.
```bash
flux reconcile kustomization icloud-docker-$INSTANCE -n backup --with-source
TAG=$(kubectl get hr -n backup icloud-docker-$INSTANCE -o jsonpath='{.spec.values.controllers.main.containers.app.image.tag}'); echo "$TAG"
[ "$TAG" = "main@sha256:91486ec1eaeb382e7af264b7ffa935c5ba110f11c3c2f1805976782ff5017917" ] && echo REVERT-APPLIED || echo "STOP: HR spec is not the old pin yet -- do not resume/scale; re-check the push and the Kustomization"
```
   Only on `REVERT-APPLIED`:
```bash
flux resume helmrelease icloud-docker-$INSTANCE -n backup 2>/dev/null
flux reconcile helmrelease icloud-docker-$INSTANCE -n backup --force   # application-update SOP §11
kubectl -n backup scale deploy icloud-docker-$INSTANCE --replicas=1    # in case step 1 scaled to 0 (resume alone does not rescale)
kubectl -n backup get pod -l app.kubernetes.io/name=icloud-docker-$INSTANCE -o name | wc -l   # 1
```
4. Confirm: §4.1 shows `91486ec1…` again; §4.2's script on the new pod shows `auth_errors=0` and `drive_start>=1` (old image prints `old_unpack_errors` again for mu — expected); §4.5 photos last-success advances past the rollback time.
5. Commit A (probe) does NOT need reverting: the added pattern never matches the old image's output (that string does not exist there).

### 5.2 Session restore (only if the old image now asks for 2FA after rollback)

The cookie format is shared, so this is not expected. If it happens, with the deploy at 0 and the HR suspended (5.1 step 1):
```bash
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata: {name: icloud-session-restore-$INSTANCE, namespace: backup}
spec:
  restartPolicy: Never
  securityContext: {runAsUser: 1000, runAsGroup: 1000, fsGroup: 1000}
  containers:
    - name: app
      image: mandarons/icloud-drive:main@sha256:91486ec1eaeb382e7af264b7ffa935c5ba110f11c3c2f1805976782ff5017917
      command: ["sleep", "infinity"]
      volumeMounts: [{name: session, mountPath: /config/session_data}]
  volumes: [{name: session, persistentVolumeClaim: {claimName: icloud-docker-$INSTANCE-session}}]
EOF
kubectl -n backup wait --for=condition=Ready pod/icloud-session-restore-$INSTANCE --timeout=120s
kubectl -n backup exec icloud-session-restore-$INSTANCE -- sh -c "cd /config/session_data && for b in *.backup.$BK_TS; do cp -p \"\$b\" \"\${b%.backup.$BK_TS}\"; done && ls | grep -c 'backup.$BK_TS'"   # 2
kubectl -n backup delete pod icloud-session-restore-$INSTANCE --wait=true
flux resume helmrelease icloud-docker-$INSTANCE -n backup
kubectl -n backup scale deploy icloud-docker-$INSTANCE --replicas=1    # resume alone does not rescale an in-sync release
```
(Restore loop dry-tested on a scratch dir 2026-10-03.) Confirm with §4.2 (`auth_errors=0`). If 2FA is STILL required, the trust was revoked server-side — restoring files cannot fix that: run `docs/sops/icloud-docker-reauth.md` from Step 1, including **Step 4b** (pending-terms probe), with that Apple ID's phone (Andrea's for andrea). Last-resort floor for a corrupted volume: the 03:00 Longhorn backup of `icloud-docker-mu-session` / `pvc-f6ec0213-…` per `docs/sops/backup.md` (restore into the same volume name; NEVER delete the andrea session PVC — reclaim `Delete`).

### 5.3 Share

Nothing to restore: `remove_obsolete: false`, the dry-run mounted the share read-only, and v2 only adds unpacked package trees. The old image will again fail those 9 packages (status quo). Never delete or prune anything on `cifs-icloud-docker-*` as part of a rollback (Severe tier, `docs/sops/storage-safety.md`).

## 6. Interference notes

- **Sequencing inside the plan:** probe (A) -> mu (B, verify) -> andrea (C, verify) -> SOP (D). andrea never starts while mu is unverified; andrea's STOP never rolls back mu.
- **Downtime:** each instance is down ~10-20 min (scale-0 + dry-run + Recreate). `ICloudBackupDeploymentUnavailable` needs 30 min, so it should not fire; if a dry-run drags past ~20 min, expect it pending/firing and do not treat it as a regression. No user-facing service (no route).
- **Shared surfaces:** both data PVCs sit on `//NAS/backups` (`icloud-backup/mu`, `icloud-backup/andrea`); `icloud-backup-freshness` reads the parent read-only through `cifs-immich-icloud-backup` — not edited. First mu drive cycle downloads ~9 packages (tens of MB) — no bulk traffic.
- **Monitoring is the instrument:** §4 reads Prometheus and Pushgateway. No `kube-prometheus-stack` / pushgateway plan is open (kube-prometheus-stack-91.4.1 executed); if one appears for the same night it must be added to `conflicts_with` on both sides.
- **conflicts_with rationale:** app-template-5.2.1 edits the same two files and HRs (chart bump) — it lists this plan reciprocally (added in 0525329a). helm-drift-detection / flux-oci-chart-sources / flux-reconciler-impersonation / flux-fleet-0.60.0 all change how these HRs are reconciled while we suspend/resume them. longhorn-1.13.0 moves the engine under the session PVCs and touches `cifs/backups`. talos-linux-1.14.2 reschedules both pods.
- **Window:** human-gated (capability_change true) and needs ~140 min -> a **sun-attended** slot (180 min budget) or an operator-triggered on-demand NOW run. Not sat-attended (70 min budget). The operator's phone should be within reach for the mu half (contingency only).
- **Apple 2FA quota:** never re-run a dry-run that returned STOP-AUTH; never leave a 2.1.0 pod looping on `2FA is required` (2.1.0 requests a push once per re-auth episode — one quota unit — then loops on `retry_login_interval: 600`).
- **Repo notes (not fixed by this plan):** (1) version-check/security-check compare the floating `main` tag with itself, so neither saw that a newer RELEASE (2.1.0) existed — AR-029 record F-b2c35615 says "already on newest" for an image that had three newer releases; after this bump the pin is a semver tag and the check works again.
