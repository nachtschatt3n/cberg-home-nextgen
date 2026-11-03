---
plan_id: plex-1.43.5.11079
component: plex
pr: null                              # No Renovate PR. Surfaced by coverage.py as lane=PLAN
                                      # (group plex-1.43.5.11079), dispatched by nightly:2026-10-28
                                      # Step 0.5. Version finding F-4b7ecd9c.
kind: image
current: "1.43.5.11029-6bf8af3f0"     # re-verified live 2026-10-28: statefulset/plex-plex-media-server
                                      # image index.docker.io/plexinc/pms-docker:1.43.5.11029-6bf8af3f0,
                                      # pod imageID sha256:01bdf0ad6d53198da4331540c1e73ab65db7a72e961fff97ecb0847d46055c5f
                                      # (= registry index digest of that tag), /identity version identical.
target: "1.43.5.11079-b3b13e506"      # Docker Hub tag pushed 2026-10-26T08:05Z, manifest LIST digest
                                      # sha256:6d778d41daae68f89115aa87a44ae14a96b23e71a2093da173b5a9aac4091336
                                      # (HEAD on registry-1.docker.io AND the hub tag API agree; also `latest`).
                                      # Pin stays TAG-ONLY, matching the current house form for this HR.
update_type: patch
risk: low                             # Same 1.43.5 line, build 11029 -> 11079. The hold was a G3
                                      # FALSE POSITIVE ("release notes unavailable"): the notes exist at
                                      # Plex's own downloads API (§1), and contain no breaking change.
                                      # Single-replica StatefulSet (RollingUpdate on a 1-replica STS =
                                      # delete-then-create, no Multi-Attach), config on longhorn-static RWO,
                                      # media on CIFS mounted unchanged. Not "trivial": PMS builds run
                                      # forward DB migrations (measured, §1.3), which is why rollback is
                                      # backup-restore, not git-revert.
est_duration_min: 35                  # pre-checks + baselines 8, DB copy 2, edit/commit/push/propagate 5,
                                      # pull (~350 MB) + start 5, gates §4 10, slack 5
needs_reboot: false
touches:
  namespaces: [media]
  resources:
    - helmrelease/plex                       # the only file change: values.image.tag
    - statefulset/plex-plex-media-server     # one pod replaced (plex-plex-media-server-0)
    - service/plex-plex-media-server         # unchanged; LB 192.168.55.30:32400 endpoints move
    - httproute/plex                         # unchanged; host unreachable ~2-3 min during the roll
    - pvc/plex-config                        # longhorn-static RWO 10Gi, PV/volume plex-config; remounted,
                                             # library DB migrated FORWARD by the new PMS on first start
    - pvc/plex-media-smb                     # cifs-plex-media, subdir "/", CATASTROPHIC tier; remounted
                                             # only. NO PVC/PV action of any kind in this plan.
    - cronjob/media-plex-fs-classifier       # unchanged; reads the Plex API (01:35 daily) - see §6
  shared: [igpu-i915, media]          # igpu-i915: pod requests+limits gpu.intel.com/i915: 1 and mounts
                                      # /dev/dri (hostPath); currently on k8s-nuc14-02, no nodeSelector.
                                      # media: remount of the //NAS/media share ROOT (subdir /), shared
                                      # with Jellyfin and the library-tools CronJobs. Read/write only.
                                      # gateway/envoy NOT perturbed: the HTTPRoute and Gateways are not
                                      # edited; only the backend pod changes.
depends_on: []
conflicts_with:
  - media-naming-p3                   # renames files under cifs-plex-media and drives Plex
                                      # re-identification; a PMS restart/DB migration mid-rename breaks
                                      # both its gates and ours (G4 library counts would move for a
                                      # reason that is not the image).
  - helm-drift-detection              # adds driftDetection to every HR incl. media/plex and gates on
                                      # "no Helm upgrade happened" - this plan IS a Helm upgrade of that
                                      # HR; its P2 intel-gpu-plugin DaemonSet roll means "NEW GPU pods
                                      # cannot schedule for ~1 min per node" - our new pod IS a GPU pod.
  - flux-oci-chart-sources            # lists media/plex among its rolled releases and baselines Plex
                                      # library counts (its §862 gate); interleaving breaks attribution.
  - talos-linux-1.14.5                # exclusive node roll (GPU node, CIFS remounts). Was talos-linux-1.14.4,
                                      # which is `superseded` (retargeted to 1.14.5 on 2026-11-02); 1.14.5
                                      # names this plan back (reciprocal, igpu-i915). Re-checked 2026-11-03.
  - jellyfin-3.7.0                    # ADDED 2026-11-03 (review): shares igpu-i915 and the //NAS/media root, and is a Plex API peer
  - python-fleet-3.15.2               # ADDED 2026-11-03: its suggestion is the same sat-attended:2026-11-14;
                                      # 35 + 35 = 70 of 70 usable min (ZERO slack for a rollback), and its
                                      # media/library-tools CronJob touch moves the same Plex API consumers.
                                      # Needs the reciprocal entry in python-fleet-3.15.2 (not edited here).
  - flux-reconciler-impersonation     # exclusive; its FAIL shapes name media/plex - our delivery path is
                                      # the Flux helm-controller apply that plan re-identities.
exclusive: false
security_ref: null                    # security_evidence: none for this group. See §1.2 on the
                                      # upstream "(Security)" category items (not reproduced here).
capability_change: true               # NOT "to be safe" - two concrete behaviour changes reach our data
                                      # path: (1) NEW FEATURE "reading artist and album metadata from NFO
                                      # files in music libraries" - our Music section (key 3, agent
                                      # tv.plex.agents.music) holds album.nfo sidecars by house standard
                                      # (media-library-standards.md), so Music metadata may change on the
                                      # next refresh; whether the reader is on by default could NOT be
                                      # verified (no such pref exists at 11029). (2) changed handling of
                                      # requests arriving via a reverse proxy, and our clients reach PMS
                                      # through envoy-internal (customConnections advertises the HTTPRoute
                                      # host). A reviewer who proves (1) is opt-in-and-off may flip this.
rollback_class: backup-restore        # MEASURED forward-only step: schema_migrations grew 447 -> 448 rows
                                      # between the butler DB copies of 2026-10-19 (pre-11029) and
                                      # 2026-10-28 (post-11029), i.e. a same-line PMS build migrated the
                                      # library DB. Expect the same of 11079. A plain git revert puts the
                                      # OLD binary on a NEWER DB; Plex does not support downgrade, so the
                                      # rollback restores the §3.2 pre-change copy (procedure in §5).
backup_gate: "§3.2: a FRESH consistent copy of the live library DB taken in-pod with Plex SQLite `.backup` (online-backup API, safe against the live WAL) into the Databases dir as pre-11079-<UTC-ts>.com.plexapp.plugins.library.db (plus the blobs DB the same way), BEFORE the tag edit is pushed. PASS = opened with `file:<copy>?mode=ro&immutable=1`: `pragma integrity_check` prints exactly `ok` AND `select count(*) from schema_migrations` equals the §2.6 SM_BASE (448 at authoring) AND `select count(*) from metadata_items` is >= 1 and equals the same count read from the live DB in the same minute. A missing/0-byte copy fails the open (`unable to open database file`, dry-tested). Secondary layers, both premises/pre-checks: the PMS butler copy com.plexapp.plugins.library.db-<date> <= 3 days old, and the nightly Longhorn backup of volume plex-config FRESH < 26h (`runbooks/longhorn-backup-age.py plex-config --max-hours 26`; the same call with --max-hours 1 prints STALE, measured 2026-10-28)."
finding_refs: [F-4b7ecd9c, F-170214c3]   # F-170214c3 = probes ignored by the chart (separate job, NOT folded into this bump); F-4b7ecd9c now reads -> 1.43.6.11085, see §1.5            # "plex: image plexinc/pms-docker 1.43.5.11029-6bf8af3f0 ->
                                      # 1.43.5.11079-b3b13e506 (patch)" - queried 2026-10-28 with
                                      # SWEEP_PG_DSN up (`finding list --grep plex` and `--grep pms-docker`).
                                      # F-ba0fe5d7 (plex chart source UNRESOLVED) is a different job.
review: null
status: draft
window: null                          # RECOMMENDED sat-attended:2026-11-14 (09:00 Berlin, 90 min, 70 usable; this plan
                                      # is 35, alone in the slot). Not stamped: the scheduler / operator GO assigns it (HUMAN-GATED).
premises:
  - id: sts-image-is-current
    why: >-
      current:, the DB-migration baseline and every count below were captured
      against this exact tag. If the StatefulSet already moved, this plan is stale.
    run: kubectl get statefulset plex-plex-media-server -n media -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_contains: "plexinc/pms-docker:1.43.5.11029-6bf8af3f0"
  - id: repo-pin-is-current
    why: "The §3.1 sed anchors on this exact line; if it is gone the edit is a no-op and the window would 'pass' without changing anything."
    run: "grep -c 'tag: 1.43.5.11029-6bf8af3f0$' kubernetes/apps/media/plex/app/helmrelease.yaml"
    expect_exact: "1"
  - id: hr-ready
    why: "A HelmRelease already failing would mask whether the bump itself reconciled."
    run: kubectl get helmrelease plex -n media -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: chart-source-unchanged
    why: >-
      The chart is a GitRepository pinned by commit (helm-chart-1.9.0). This plan
      changes only the image; a moved chart commit in the same reconcile breaks
      attribution of any failure.
    run: kubectl get gitrepository plex -n flux-system -o jsonpath='{.spec.ref.commit}'
    expect_exact: "96d39230ad375c941505bd1ba024d354e73a6caf"
  - id: media-class-still-retain
    why: >-
      storage-safety.md: cifs-plex-media is CATASTROPHIC tier (subdir /). This plan
      performs NO PVC action, but if the class ever reads Delete the executor must
      STOP before touching anything in this namespace.
    run: kubectl get sc cifs-plex-media -o jsonpath='{.reclaimPolicy}'
    expect_exact: "Retain"
  - id: media-pv-still-retain
    why: "The bound PV carries its own reclaim policy; it must also be Retain."
    run: kubectl get pv pvc-93fb23f2-2de0-4e73-8507-d53d058f77cf -o jsonpath='{.spec.persistentVolumeReclaimPolicy}'
    expect_exact: "Retain"
  - id: config-volume-healthy
    why: "The secondary rollback layer is the nightly Longhorn backup of this volume; it must be attached and healthy."
    run: kubectl get volumes.longhorn.io plex-config -n storage -o jsonpath='{.status.state}/{.status.robustness}'
    expect_exact: "attached/healthy"
  - id: plex-pod-not-restarting
    why: "A pod already restarting would make G1 (restartCount 0 on the new pod) meaningless as a baseline."
    run: kubectl get pod plex-plex-media-server-0 -n media -o jsonpath='{.status.containerStatuses[0].restartCount}'
    expect_exact: "0"
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/storage-safety.md
  - docs/sops/longhorn.md
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/vulnerability-disclosure.md
generated: "2026-10-28"
---

# Plex Media Server 1.43.5.11029 -> 1.43.5.11079 (no PR)

## 1. Summary & why held

**Change:** one line in `kubernetes/apps/media/plex/app/helmrelease.yaml`,
`values.image.tag: 1.43.5.11029-6bf8af3f0 -> 1.43.5.11079-b3b13e506`. Chart
(GitRepository `flux-system/plex`, commit `96d39230`, chart 1.9.0) unchanged.

**Why held:** coverage G3 "could not verify the release notes (unverified
(release notes unavailable))", earned autonomy 0/0 in 90d. **The hold is a
false positive of the notes lookup**, not a breaking-change signal:
`runbooks/check-all-versions.py` has no release-notes source for
`plexinc/pms-docker` (its image->GitHub map near line 544 has no entry, and the
`plexinc/pms-docker` GitHub repo does not publish per-PMS-build notes anyway).

### 1.1 Primary-source release notes (read 2026-10-28)

Source: Plex's own downloads API, `https://plex.tv/api/downloads/5.json`
(`computer.Linux`). The **public** channel's current version is exactly
`1.43.5.11079-b3b13e506`, `release_date` 1792755866 = 2026-10-23T11:44Z (the
plexpass/beta channel shows the same build). Relevant items, quoted:

- Added: "(Metadata) Added support for reading artist and album metadata from
  NFO files in music libraries (PM-6153)" — **affects us** (see capability_change).
- Added: "(Network) Ignore manually specified public port for IPv6 connections
  (PM-5364)" and "Send subnet information to plex.tv so IPv6 and non-private
  local connections are detected correctly (PM-5364)" — we run
  `EnableIPv6=0`; no manual port mapping in Preferences.xml.
- Fixed: "(Network) Added IPv6 support to the preferred network interface
  (PM-6017)" — we set `PreferredNetworkInterface=eth0` with IPv6 off.
- Fixed: "(Transcoder) Photos could fail to load for clients connecting
  through a reverse proxy (PM-6476)" — our clients DO connect through a
  reverse proxy (envoy-internal; Preferences.xml `customConnections` lists the
  HTTPRoute host and the LB IP).
- Fixed: "(Butler) Scheduled loudness analysis ran on movie and TV libraries
  that had it disabled (PM-6263)" — Movies has `enableLoudnessAnalysis=true`,
  no change for us.
- "Updated Web to 4.162.1".

No item is marked breaking, no migration step is required of the operator.

### 1.5 Newer build exists on Hub (recorded 2026-11-03)

Docker Hub carries `1.43.6.11085-d1e52e169` (pushed 2026-11-02) and finding F-4b7ecd9c now reads
`-> 1.43.6.11085`. plex.tv's PUBLIC channel and Hub `latest` are still `1.43.5.11079-b3b13e506`, so
11079 stays the target (the public build is the supported one) and this plan will NOT close F-4b7ecd9c.
§2.2 STOPs and re-plans if plex.tv flips to 11085 before the window.

### 1.2 Upstream "(Security)" category items

The notes contain several items in Plex's own "(Security)" category, one of
which changes how PMS treats **requests arriving through a proxy** and one how
it decides **request locality**. Their per-item text is not reproduced here
(`docs/sops/vulnerability-disclosure.md`: it would describe what is unfixed on
the running 11029). The OPERATIONAL consequence is what this plan gates: our
only browser path is proxied, so §4 G6/G7 assert authenticated proxied access
still works and unauthenticated proxied access is still refused. Measured
baseline 2026-10-28: proxied `/library/sections` with token 200, without token
401; `allowedNetworks` is NOT set in Preferences.xml, so no "local = no auth"
behaviour is relied on anywhere. (Coordinator: if this should carry a
security_ref, the record belongs on the finding DB, not here.)

### 1.3 Forward-only DB step (measured)

Plex keeps butler copies of the library DB every 3 days. Read-only
(`immutable=1`) on those copies:

| copy | `count(*) schema_migrations` | integrity |
|---|---|---|
| `com.plexapp.plugins.library.db-2026-10-19` (before 11029 started 2026-10-20) | 447 | ok |
| `com.plexapp.plugins.library.db-2026-10-28` (on 11029) | 448 | ok |

So a same-line build migrated the DB. 11079 will plausibly do the same, and
Plex does not support running an older binary on a migrated DB. Hence
`rollback_class: backup-restore` with a fresh pre-change copy (§3.2).

### 1.4 Wiring

StatefulSet `plex-plex-media-server` (1 replica, `RollingUpdate` partition 0
→ delete-then-create, immune to Multi-Attach), container
`plex-plex-media-server-pms`, node k8s-nuc14-02 today, no nodeSelector,
i915 request/limit 1 + hostPath `/dev/dri`. Service LoadBalancer
`192.168.55.30:32400` (Cilium LB-IPAM). HTTPRoute `plex` on `envoy-internal`
(`https`), Homepage annotations on the route. Storage: `plex-config`
(longhorn-static, 10Gi, 35 % used) at `/config`; `plex-media-smb`
(cifs-plex-media, subdir `/`, Retain, CATASTROPHIC tier) at `/data`.
Library: 3 sections (movie / show / artist). API consumers: CronJob
`media-plex-fs-classifier` (01:35), plus the other library-tools jobs in §6.

## 2. Pre-checks

Run from the repo root on the Mac, zsh. Any FAIL = STOP, do not push.

2.0 Shell state. Every block runs in a FRESH shell (nothing survives between tool calls),
so no variable is carried by memory: values are written to `$W/state.env` /
`$W/counts.base` and every later block starts with `. /tmp/plex-11079-win/fns.sh`.
Paste once:

```bash
mkdir -p /tmp/plex-11079-win
rm -f /tmp/plex-11079-win/state.env /tmp/plex-11079-win/counts.*   # a stale state file must not satisfy later guards
cat > /tmp/plex-11079-win/fns.sh <<'FNS'
W=/tmp/plex-11079-win
DBDIR="/config/Library/Application Support/Plex Media Server/Plug-in Support/Databases"
T=$(kubectl get secret -n media media-manager-tokens -o jsonpath='{.data.PLEX_TOKEN}' | base64 -d)
D=$(kubectl get secret -n flux-system cluster-secrets -o jsonpath='{.data.SECRET_DOMAIN}' | base64 -d)
pms() { kubectl exec -n media plex-plex-media-server-0 -c plex-plex-media-server-pms -- "$@"; }
save() { grep -v "^$1=" "$W/state.env" 2>/dev/null > "$W/state.tmp"; printf '%s=%s\n' "$1" "$2" >> "$W/state.tmp"; mv "$W/state.tmp" "$W/state.env"; }
[ -f "$W/state.env" ] && . "$W/state.env"
true
FNS
. /tmp/plex-11079-win/fns.sh; test -n "$T" -a -n "$D" && echo FNS_OK
```

PASS = `FNS_OK`. Empty `$T`/`$D` (secret missing) is a STOP: later gates would run
vacuously against empty credentials. Values saved so far are shown by `cat $W/state.env`.

2.1 Premises:

```bash
.venv/bin/python3 runbooks/plan-premises.py plex-1.43.5.11079 --require-premises
```

PASS = every premise PASS, no `REFUSED`.

2.2 Target tag still exists and is still the same build (network checks the
premise runner refuses):

```bash
TOK=$(curl -s 'https://auth.docker.io/token?service=registry.docker.io&scope=repository:plexinc/pms-docker:pull' | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
curl -sI -H "Authorization: Bearer $TOK" \
  -H 'Accept: application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.oci.image.index.v1+json' \
  https://registry-1.docker.io/v2/plexinc/pms-docker/manifests/1.43.5.11079-b3b13e506 | grep -i docker-content-digest
```

PASS = `sha256:6d778d41daae68f89115aa87a44ae14a96b23e71a2093da173b5a9aac4091336`.
A different digest = upstream re-pushed the tag: STOP and re-review.

```bash
curl -s https://plex.tv/api/downloads/5.json | python3 -c 'import sys,json;print(json.load(sys.stdin)["computer"]["Linux"]["version"])'
```

PASS = `1.43.5.11079-b3b13e506`. A newer version (e.g. 1.43.6.11085) = the target drifted: STOP,
refresh this plan in place (README "When the held target MOVES").

2.3 Storage-safety pre-flight (CLAUDE.md one-liner, read-only):

```bash
PV=$(kubectl get pvc plex-media-smb -n media -o jsonpath='{.spec.volumeName}') && \
  kubectl get pv $PV -o jsonpath='{.spec.csi.volumeAttributes}' | python3 -m json.tool && \
  echo "reclaim=$(kubectl get pv $PV -o jsonpath='{.spec.persistentVolumeReclaimPolicy}')"
```

PASS = `reclaim=Retain` (subdir `/` is expected and is why NOTHING in this
plan touches the PVC/PV). This plan never deletes, recreates, or edits any
PVC or PV.

2.4 Backups (secondary rollback layers):

```bash
.venv/bin/python3 runbooks/longhorn-backup-age.py plex-config --max-hours 26
```

PASS = line ends `FRESH` (measured 2026-10-28: `3.9h FRESH via backup-cr`).

```bash
kubectl exec -n media plex-plex-media-server-0 -c plex-plex-media-server-pms -- \
  sh -c 'ls -la "/config/Library/Application Support/Plex Media Server/Plug-in Support/Databases" | grep "library.db-20"'
```

PASS = the newest dated `com.plexapp.plugins.library.db-YYYY-MM-DD` is at most
3 days old (2026-10-28 at authoring). Also confirm `df -h /config` shows
> 1 GiB free (6.4G at authoring).

2.5 No one is watching (a restart kills streams):

```bash
. /tmp/plex-11079-win/fns.sh
curl -s -H "X-Plex-Token: $T" http://192.168.55.30:32400/status/sessions | grep -o '<MediaContainer size="[0-9]*"'
```

PASS = `<MediaContainer size="0"`. Non-zero = wait (re-check every
5 min up to 20 min, then defer; ask the operator, the window is attended). Empty output = the token or the LB path is
broken: STOP (that is also G6/G7's baseline).

2.6 Baselines (record into shell variables; also note them in the window log
as COUNTS only, never titles):

```bash
# Library section item counts. Negative control: a bad token prints sectionN=MISSING.
. /tmp/plex-11079-win/fns.sh
cat > /tmp/plex-11079-win/counts.sh <<'EOF'
#!/bin/zsh
T=$(kubectl get secret -n media media-manager-tokens -o jsonpath='{.data.PLEX_TOKEN}' | base64 -d)
kubectl exec -n media plex-plex-media-server-0 -c plex-plex-media-server-pms -- env T="$T" sh -c '
for k in $(curl -s -H "X-Plex-Token: $T" http://127.0.0.1:32400/library/sections | grep -o "<Directory [^>]*" | sed -n "s/.* key=\"\([0-9]*\)\".*/\1/p"); do
  n=$(curl -s -H "X-Plex-Token: $T" -H "X-Plex-Container-Start: 0" -H "X-Plex-Container-Size: 0" "http://127.0.0.1:32400/library/sections/$k/all" | grep -o "totalSize=\"[0-9]*\"" | head -1 | tr -dc 0-9)
  echo "section$k=${n:-MISSING}"
done' | sort
EOF
chmod +x /tmp/plex-11079-win/counts.sh
/tmp/plex-11079-win/counts.sh > "$W/counts.base"; cat "$W/counts.base"
test "$(wc -l < "$W/counts.base")" -eq 3 && ! grep -q MISSING "$W/counts.base" && echo COUNTS_BASE_OK
```

PASS = three lines, no `MISSING`, `COUNTS_BASE_OK` (authoring 2026-10-28: `section1=499`,
`section2=21`, `section3=20`; section1 cross-checks against the 01:35
`media-plex-fs-classifier` log `Plex items=499`). Dry-run on 2026-10-28.

```bash
# DB migration baseline from the newest butler copy (read-only, immutable).
. /tmp/plex-11079-win/fns.sh
NEWEST=$(kubectl exec -n media plex-plex-media-server-0 -c plex-plex-media-server-pms -- sh -c "cd \"$DBDIR\" && ls com.plexapp.plugins.library.db-20* | sort | tail -1")
SM_BASE=$(kubectl exec -n media plex-plex-media-server-0 -c plex-plex-media-server-pms -- sh -c "cd \"$DBDIR\" && \"/usr/lib/plexmediaserver/Plex SQLite\" \"file:$NEWEST?mode=ro&immutable=1\" 'select count(*) from schema_migrations;'")
print -r -- "NEWEST=$NEWEST SM_BASE=$SM_BASE"
case "$SM_BASE" in ''|*[!0-9]*) echo "SM_BASE_NOT_A_NUMBER"; false;; esac && save NEWEST "$NEWEST" && save SM_BASE "$SM_BASE" && echo SAVED
```

PASS = a number (448 at authoring) and `SAVED`. `SM_BASE_NOT_A_NUMBER` (an error text
instead of a number) = STOP; nothing is saved, so a later block cannot pass on an empty value.

```bash
# Proxied + LB path baseline (G6/G7 must reproduce these).
. /tmp/plex-11079-win/fns.sh
curl -s -o /dev/null -w 'proxied-auth %{http_code}\n'   -H "X-Plex-Token: $T" "https://plex.$D/library/sections"
curl -s -o /dev/null -w 'proxied-noauth %{http_code}\n' "https://plex.$D/library/sections"
curl -s -o /dev/null -w 'lb %{http_code}\n' http://192.168.55.30:32400/identity
```

PASS = `proxied-auth 200`, `proxied-noauth 401`, `lb 200` (measured 2026-10-28).

2.7 Timing: the window's start coincides with `media-intake-watcher`
(`*/30`), and `media-metadata-coverage` runs at `:00`. Push in §3.3 between
:32 and :50 past the hour so the ~3 min Plex outage falls between them.
Recommended slot `sat-attended:2026-11-14` starts 09:00 Berlin: Step 0 (20 min
reserve) ends ~09:20, so the :32-:50 push lands at ~09:32-09:50, clear of the :00/:30
jobs. (The text previously assumed a 03:30 nightly start; this plan is human-gated and
runs attended, never in the nightly.)

## 3. Steps

3.1 Edit (dry-tested on a scratch copy with BSD sed 2026-10-28; resulting diff
is exactly one line):

```bash
sed -i '' 's/tag: 1\.43\.5\.11029-6bf8af3f0$/tag: 1.43.5.11079-b3b13e506/' kubernetes/apps/media/plex/app/helmrelease.yaml
git diff --stat kubernetes/apps/media/plex/app/helmrelease.yaml
grep -c 'tag: 1.43.5.11079-b3b13e506$' kubernetes/apps/media/plex/app/helmrelease.yaml
```

Expected diff:

```
38c38
<       tag: 1.43.5.11029-6bf8af3f0
---
>       tag: 1.43.5.11079-b3b13e506
```

PASS = `1 file changed, 1 insertion(+), 1 deletion(-)` and grep prints `1`.
Do not commit yet.

3.2 BACKUP GATE — fresh consistent DB copy, BEFORE the push:

```bash
. /tmp/plex-11079-win/fns.sh
test -n "$SM_BASE" || { echo "GUARD: SM_BASE unset, run §2.6 first"; false; }
TS=$(date -u +%Y%m%dT%H%M%SZ)
CP="pre-11079-$TS.com.plexapp.plugins.library.db"
CPB="pre-11079-$TS.com.plexapp.plugins.library.blobs.db"
save TS "$TS"; save CP "$CP"; save CPB "$CPB"
kubectl exec -n media plex-plex-media-server-0 -c plex-plex-media-server-pms -- sh -c "cd \"$DBDIR\" && \
  \"/usr/lib/plexmediaserver/Plex SQLite\" com.plexapp.plugins.library.db \".backup '$CP'\" && \
  \"/usr/lib/plexmediaserver/Plex SQLite\" com.plexapp.plugins.library.blobs.db \".backup '$CPB'\" && \
  chown plex:plex \"$CP\" \"$CPB\" && ls -la \"$CP\" \"$CPB\""
kubectl exec -n media plex-plex-media-server-0 -c plex-plex-media-server-pms -- sh -c "cd \"$DBDIR\" && \
  \"/usr/lib/plexmediaserver/Plex SQLite\" \"file:$CP?mode=ro&immutable=1\" 'pragma integrity_check; select count(*) from schema_migrations; select count(*) from metadata_items;' && \
  \"/usr/lib/plexmediaserver/Plex SQLite\" \"file:com.plexapp.plugins.library.db?mode=ro\" 'select count(*) from metadata_items;' && \
  \"/usr/lib/plexmediaserver/Plex SQLite\" \"file:$CPB?mode=ro&immutable=1\" 'pragma integrity_check;'"
```

PASS = output lines in order: `ok`, `$SM_BASE`, N (>= 1), the same N from
the live DB, `ok`. Copy sizes ~39 MB / ~47 MB (live sizes at authoring). Any
`unable to open database file`, a second integrity line other than `ok`, or
N mismatch = STOP, do not push; delete nothing. The `.backup` syntax and
immutable read-back were dry-tested locally with sqlite3 (WAL-mode source)
on 2026-10-28; the immutable read on the real butler copies ran in-pod the
same day. `CP`/`CPB`/`TS` are saved to `$W/state.env` above (§5 sources them); also note them in
the window log.

3.2b **Rollback proof, BEFORE the push** (non-destructive: nothing in `$DBDIR` is
changed). A backup that cannot be restored is not a backup; this proves the §5.3
restore path end to end on the copy, and fails closed:
```bash
. /tmp/plex-11079-win/fns.sh
test -n "$CP" -a -n "$CPB" -a -n "$SM_BASE" || { echo "GUARD: state missing"; false; }
pms sh -c "cd \"$DBDIR\" && sha256sum \"$CP\" \"$CPB\" && df -Pk . | tail -1" | tee "$W/copy.sha"
#   (1) the restore tooling §5.3 depends on exists in THIS image:
pms sh -c 'test -d /var/run/s6/services/plex && test -x /usr/bin/s6-svc -o -x /command/s6-svc && command -v sha256sum >/dev/null && command -v pgrep >/dev/null && echo TOOLING_OK || echo TOOLING_MISSING'
#   (2) a restore-shaped copy of the copy opens, passes integrity and carries the baseline migration count:
pms sh -c "cd \"$DBDIR\" && cp -p \"$CP\" /tmp/rb-proof.db && \"/usr/lib/plexmediaserver/Plex SQLite\" /tmp/rb-proof.db 'pragma integrity_check; select count(*) from schema_migrations;'; rm -f /tmp/rb-proof.db"
#   (3) the byte-compare used by §5.3 can FAIL: a one-byte-different file must NOT compare equal:
pms sh -c "cd \"$DBDIR\" && cp -p \"$CP\" /tmp/rb-a.db && cp -p \"$CP\" /tmp/rb-b.db && printf x >> /tmp/rb-b.db && { cmp -s /tmp/rb-a.db \"$CP\" && echo SAME_OK; cmp -s /tmp/rb-b.db \"$CP\" || echo DIFF_DETECTED; }; rm -f /tmp/rb-a.db /tmp/rb-b.db"
```
PASS = two sha256 lines + a free-space line with >= 200000 KiB available (the restore needs
~90 MB plus the aside copy), `TOOLING_OK`, then `ok` and `$SM_BASE`, then `SAME_OK` and
`DIFF_DETECTED`. `TOOLING_MISSING`, a missing line, or `ok` without the right count = STOP:
do not push. The `/tmp/rb-*` scratch files are removed by the command itself (they are not
the Plex data).

3.3 Commit and push (shared worktree rules):

```bash
cat > /tmp/plex-11079-msg.txt <<'EOF'
fix(plex): bump plexinc/pms-docker 1.43.5.11029 -> 1.43.5.11079 (plan plex-1.43.5.11079)

Patch build on the 1.43.5 line. Release notes read from plex.tv downloads API.
Pre-change DB copy taken in-pod (backup gate) before push.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
git commit --only kubernetes/apps/media/plex/app/helmrelease.yaml -F /tmp/plex-11079-msg.txt
git log -1 --format=%s
git show --stat HEAD
git push
```

PASS = the subject is the one above (amend before push if not) and
`git show --stat` lists only `kubernetes/apps/media/plex/app/helmrelease.yaml`.
Record it: `. /tmp/plex-11079-win/fns.sh; save PUSH_TS $(date -u +%s)`. Flux webhook delivers; no manual reconcile
unless the HR has not picked up the new values within 10 min, in which case
`flux reconcile helmrelease plex -n media --with-source` once.

## 4. Verification

Every block starts with `. /tmp/plex-11079-win/fns.sh` (fresh shell). Do NOT assume
readiness from `rollout status` or a fixed sleep (rollout status green-lights the old
generation; a first start also runs the DB migration). **Poll `/identity` for the
target build, then poll the library API, and treat a timeout as a FAIL:**

```bash
. /tmp/plex-11079-win/fns.sh
for i in $(seq 1 40); do
  kubectl exec -n media plex-plex-media-server-0 -c plex-plex-media-server-pms -- curl -s -m 5 http://127.0.0.1:32400/identity 2>/dev/null | grep -q 'version="1.43.5.11079-b3b13e506"' && { echo IDENTITY_READY; break; }
  sleep 15
done; [ "$i" -lt 40 ] || echo IDENTITY_TIMEOUT
for j in $(seq 1 20); do
  c=$(curl -s -o /dev/null -w '%{http_code}' -m 5 -H "X-Plex-Token: $T" http://192.168.55.30:32400/library/sections); [ "$c" = 200 ] && { echo LIBRARY_READY; break; }; sleep 15
done; [ "$j" -lt 20 ] || echo LIBRARY_TIMEOUT
```
PASS = `IDENTITY_READY` then `LIBRARY_READY` (10 min / 5 min ceilings: pull ~350 MB and the DB migration; the pod has NO probes, so the poll is the only readiness gate). `IDENTITY_TIMEOUT` / `LIBRARY_TIMEOUT` = FAIL: go to §5
(look at `kubectl describe pod` and the PMS log first). The poll can fail: before the pod
restarts it greps the OLD build string and never prints READY. Then run G1-G9.

**G1 — the new image is what runs.**

```bash
kubectl get pod plex-plex-media-server-0 -n media -o jsonpath='{.status.containerStatuses[0].imageID} {.status.containerStatuses[0].restartCount} {.status.startTime}{"\n"}'
```

PASS = imageID ends `sha256:6d778d41daae68f89115aa87a44ae14a96b23e71a2093da173b5a9aac4091336`,
restartCount `0`, startTime after `$PUSH_TS` (from state.env; compare as epoch seconds). FAIL shape: the old
`sha256:01bdf0ad...` digest (HR not reconciled) or restarts > 0.

**G2 — HelmRelease reconciled.** `kubectl get helmrelease plex -n media -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion}'`
PASS = `True 1.9.0`, and `helm history plex -n media --max 1` shows a NEW
revision `deployed`. FAIL = `False` / `pending-upgrade` / revision unchanged.

**G3 — CONTENTS ASSERTION: the running server reports the target build.**

```bash
kubectl exec -n media plex-plex-media-server-0 -c plex-plex-media-server-pms -- curl -s http://127.0.0.1:32400/identity | grep -c 'version="1.43.5.11079-b3b13e506"'
```

PASS = `1`. FAIL prints `0` (measured 2026-10-28 against the target string on
11029: `0`; the old string gives `1`). Note `/identity` also contains the XML
declaration `version="1.0"`, so grep the full build string, never just
`version=`.

**G4 — CONTENTS ASSERTION: library item counts survive the DB migration.**

```bash
. /tmp/plex-11079-win/fns.sh
test -s "$W/counts.base" || { echo "GUARD: counts.base missing"; false; }
/tmp/plex-11079-win/counts.sh > "$W/counts.new"; cat "$W/counts.new"
cmp -s "$W/counts.base" "$W/counts.new" && echo COUNTS_MATCH || echo COUNTS_DIFF
```

PASS = `COUNTS_MATCH`, three lines, no `MISSING`. FAIL shapes: `MISSING` (API
or token broken — negative control: a bad token printed empty totalSize →
`MISSING`, measured 2026-10-28), a lower count (migration lost items), or 2
lines (a section vanished). An empty library reads as `section1=0`, not as a
match, so this fails on "structurally healthy but empty".

**G5 — DB migrated cleanly.**

```bash
. /tmp/plex-11079-win/fns.sh
test -n "$SM_BASE" || { echo "GUARD: SM_BASE unset"; false; }
kubectl exec -n media plex-plex-media-server-0 -c plex-plex-media-server-pms -- sh -c "cd \"$DBDIR\" && \"/usr/lib/plexmediaserver/Plex SQLite\" \"file:com.plexapp.plugins.library.db?mode=ro\" 'select count(*) from schema_migrations;'"
```

PASS = a number >= `$SM_BASE`; print `[ "$n" -ge "$SM_BASE" ] && echo MIG_OK || echo MIG_BAD`. Record it: `save SM_NEW <n>`, SM_NEW: if SM_NEW == SM_BASE the
build ran no migration and §5's DB restore step is unnecessary (rollback is
then a plain revert). A number < SM_BASE or an error = FAIL.

**G6 — LAN and proxied paths serve the new build.**

```bash
. /tmp/plex-11079-win/fns.sh
curl -s "https://plex.$D/identity" | grep -c 'version="1.43.5.11079-b3b13e506"'
curl -s -o /dev/null -w 'lb %{http_code}\n' http://192.168.55.30:32400/identity
```

PASS = `1` and `lb 200`. FAIL = `0` (envoy reaching a stale endpoint or 503)
or a non-200 on the LB.

**G7 — proxied auth behaviour unchanged (the upstream proxy/locality change).**

```bash
. /tmp/plex-11079-win/fns.sh
curl -s -o /dev/null -w 'proxied-auth %{http_code}\n'   -H "X-Plex-Token: $T" "https://plex.$D/library/sections"
curl -s -o /dev/null -w 'proxied-noauth %{http_code}\n' "https://plex.$D/library/sections"
```

PASS = `proxied-auth 200` AND `proxied-noauth 401`, identical to §2.6. FAIL
either way: a 401/403 on the authenticated call means proxied clients lost
access (every browser/app user); a 200 on the unauthenticated call means the
proxy path now bypasses auth — FAIL and roll back immediately.

**G8 — hardware transcode device still present.**

```bash
kubectl exec -n media plex-plex-media-server-0 -c plex-plex-media-server-pms -- sh -c 'test -c /dev/dri/renderD128 && echo DRI_OK || echo DRI_MISSING'
kubectl get pod plex-plex-media-server-0 -n media -o jsonpath='{.spec.containers[0].resources.limits.gpu\.intel\.com/i915}{" "}{.spec.nodeName}{"\n"}'
```

PASS = `DRI_OK` and `1 <node>`. FAIL = `DRI_MISSING` or the pod `Pending` on
`Insufficient gpu.intel.com/i915` (would show in G1 as no new pod).

**G9 — stable after 10 min (Prometheus; port-forward with `$!`, kill by PID).**

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
for q in 'kube_statefulset_status_replicas_ready{namespace="media",statefulset="plex-plex-media-server"}' \
         'kube_pod_container_status_restarts_total{namespace="media",container="plex-plex-media-server-pms"}'; do
  curl -s -G http://localhost:19090/api/v1/query --data-urlencode "query=$q" | python3 -c 'import sys,json;r=json.load(sys.stdin)["data"]["result"];print(len(r),[x["value"][1] for x in r])'
done
kill $PF 2>/dev/null
```

CONTROL: metric kube_statefulset_status_replicas_ready — `{namespace="media",statefulset="plex-plex-media-server"}` reads `1 ['1']` at `$PUSH_TS`+10min (baseline `1 ['1']`, measured 2026-10-28; the same query for a nonexistent statefulset returns `0 []`, so an unscraped metric fails rather than passes).
CONTROL: metric kube_pod_container_status_restarts_total — `{namespace="media",container="plex-plex-media-server-pms"}` reads `1 ['0']` on the new pod at `$PUSH_TS`+10min; `0 []` (no series) is a FAIL, not a pass.

**G10 (next morning, non-blocking):** the 01:35 `media-plex-fs-classifier`
run logs `Plex items=` equal to `section1` from §2.6 and `unmatched=0`
(`kubectl logs -n media job/<newest media-plex-fs-classifier job> --tail=5`).
Also note in the morning report whether the Music section (key 3) gained a
new NFO-related pref (`/library/sections/3/prefs`) — that answers the
capability_change open question for future Plex plans.

## 5. Rollback

Trigger: any of G1-G9 FAIL, or a G7 auth regression (immediate).

5.1 Revert the image:

```bash
git revert --no-edit <the §3.3 commit sha>
git log -1 --format=%s          # confirm it is YOUR revert
git show --stat HEAD            # only helmrelease.yaml
git push
```

Wait with the same `/identity` poll as §4 but for the OLD build (never a bare `rollout status`):
```bash
. /tmp/plex-11079-win/fns.sh
for i in $(seq 1 40); do
  kubectl exec -n media plex-plex-media-server-0 -c plex-plex-media-server-pms -- curl -s -m 5 http://127.0.0.1:32400/identity 2>/dev/null | grep -q 'version="1.43.5.11029-6bf8af3f0"' && { echo OLD_IDENTITY_READY; break; }
  sleep 15
done; [ "$i" -lt 40 ] || echo OLD_IDENTITY_TIMEOUT
```
`OLD_IDENTITY_READY` = the old binary is serving (with a migrated DB it may instead
crash-loop or log a database error: that is the 5.3 case, `OLD_IDENTITY_TIMEOUT`).

5.2 Decide whether the DB must be restored (`. /tmp/plex-11079-win/fns.sh` gives
`SM_BASE`, `SM_NEW`, `TS`, `CP`, `CPB`; an empty `CP` = STOP, the §3.2 gate never ran): if G5 recorded SM_NEW == SM_BASE
(no migration), skip to 5.4. Otherwise, or if after 5.1 the old binary
crash-loops / logs a database error, continue with 5.3.

5.3 Restore the §3.2 pre-change copy (PMS must not be running on the DB while
it is replaced). This is an in-pod edit of app data on a PVC with no GitOps
path (CLAUDE.md exception: backup exists from §3.2, nothing is deleted, read
back after). It runs with PMS stopped inside the pod via the image's s6
service control, AFTER 5.1 so the binary that restarts is the old one:

```bash
. /tmp/plex-11079-win/fns.sh
test -n "$CP" -a -n "$CPB" -a -n "$TS" || { echo "GUARD: restore state missing"; false; }
kubectl exec -n media plex-plex-media-server-0 -c plex-plex-media-server-pms -- sh -c 's6-svc -d /var/run/s6/services/plex; sleep 10; echo "pms_procs=$(pgrep -c -x "Plex Media Serv")"'
```

PASS = `pms_procs=0`. (Never `pgrep -f 'Plex Media Server'` here: the
`sh -c` command line itself contains that string and self-matches. `-x`
on the 15-char comm `Plex Media Serv` printed `1` live and `0` for a
nonexistent name, 2026-10-28.) Verified in the 11029 image 2026-10-28:
`/var/run/s6/services/plex/{run,finish}` exist, and `finish` only kills the
PMS processes — it does not stop the container. Do NOT `kill 1` (restarts
the container and PMS reopens the DB). **Clock:** the live pod has NO liveness/readiness/startup probes
(F-170214c3: the HelmRelease sets them at the values top level but the chart reads `pms.*`), so nothing
restarts the container while PMS is down; there is no race. Still run the swap promptly (the copy is ~90 MB, seconds).
If PMS was restarted by anything before the swap, it has reopened the migrated DB: stop it again and repeat.
Then, in `$DBDIR`, move the migrated files aside and put the copies in place:

```bash
. /tmp/plex-11079-win/fns.sh
kubectl exec -n media plex-plex-media-server-0 -c plex-plex-media-server-pms -- sh -c "cd \"$DBDIR\" && \
  mkdir -p rollback-aside-$TS && \
  mv com.plexapp.plugins.library.db com.plexapp.plugins.library.db-wal com.plexapp.plugins.library.db-shm \
     com.plexapp.plugins.library.blobs.db com.plexapp.plugins.library.blobs.db-wal com.plexapp.plugins.library.blobs.db-shm rollback-aside-$TS/ 2>/dev/null; \
  cp -p \"$CP\" com.plexapp.plugins.library.db && cp -p \"$CPB\" com.plexapp.plugins.library.blobs.db && \
  chown plex:plex com.plexapp.plugins.library.db com.plexapp.plugins.library.blobs.db && \
  cmp -s \"$CP\" com.plexapp.plugins.library.db && cmp -s \"$CPB\" com.plexapp.plugins.library.blobs.db && echo RESTORE_IDENTICAL && \
  \"/usr/lib/plexmediaserver/Plex SQLite\" com.plexapp.plugins.library.db 'pragma integrity_check; select count(*) from schema_migrations;' && \
  s6-svc -u /var/run/s6/services/plex"
```

PASS = `RESTORE_IDENTICAL`, then `ok`, then `$SM_BASE` (PMS is started ONLY after the byte-compare passed; its absence means the swap did not happen: do not start PMS, re-run). Nothing is deleted: the migrated DB stays in
`rollback-aside-$TS/` until the operator clears it. Watch history recorded
between the §3.2 copy and the rollback (minutes, at night) is lost — that is
the accepted cost.

Fallback if the §3.2 copy is unusable: the newest butler copy
(`$NEWEST`, same procedure), then the Longhorn backup of volume
`plex-config` (`docs/sops/longhorn.md` restore path; restore into a NEW
volume and repoint is an attended operation — surface to the operator, do not
improvise it unattended).

5.4 **Rollback proof** (after the poll in 5.1 or the restart in 5.3; every line must pass,
none is inferred): 
```bash
. /tmp/plex-11079-win/fns.sh
for i in $(seq 1 40); do kubectl exec -n media plex-plex-media-server-0 -c plex-plex-media-server-pms -- curl -s -m 5 http://127.0.0.1:32400/identity 2>/dev/null | grep -q 'version="1.43.5.11029-6bf8af3f0"' && { echo OLD_IDENTITY_READY; break; }; sleep 15; done; [ "$i" -lt 40 ] || echo OLD_IDENTITY_TIMEOUT
for j in $(seq 1 20); do c=$(curl -s -o /dev/null -w '%{http_code}' -m 5 -H "X-Plex-Token: $T" http://192.168.55.30:32400/library/sections); [ "$c" = 200 ] && { echo LIBRARY_READY; break; }; sleep 15; done; [ "$j" -lt 20 ] || echo LIBRARY_TIMEOUT
kubectl exec -n media plex-plex-media-server-0 -c plex-plex-media-server-pms -- sh -c "cd \"$DBDIR\" && \"/usr/lib/plexmediaserver/Plex SQLite\" \"file:com.plexapp.plugins.library.db?mode=ro\" 'select count(*) from schema_migrations;'"   # == $SM_BASE
/tmp/plex-11079-win/counts.sh > "$W/counts.rb"; cmp -s "$W/counts.base" "$W/counts.rb" && echo COUNTS_RESTORED || echo COUNTS_NOT_RESTORED
```
PASS = `OLD_IDENTITY_READY`, `LIBRARY_READY`, the migration count equals `$SM_BASE` (the
old binary cannot have raised it), `COUNTS_RESTORED`. A count of `$SM_BASE + 1` after a
"restore" means the migrated DB is still in place: the swap did not happen. Then:
G1 shows `sha256:01bdf0ad6d53198da4331540c1e73ab65db7a72e961fff97ecb0847d46055c5f`
with 0 restarts; `/identity` greps `version="1.43.5.11029-6bf8af3f0"` → `1`;
`counts.base` equals `counts.rb` (above); G7 reads `200`/`401`. Record
the failure on F-4b7ecd9c and set this plan `status: blocked` with the
failing gate.

## 6. Interference notes

- **Catastrophic-tier storage.** `plex-media-smb` is on `cifs-plex-media`
  (subdir `/`, the whole `//NAS/media` export, shared with Jellyfin). This
  plan only remounts it via a pod restart. It must never be widened into a
  PVC/PV delete or recreate for any reason; if something storage-shaped goes
  wrong, STOP and surface (storage-safety.md).
- **GPU node.** The pod claims one `gpu.intel.com/i915` and has no
  nodeSelector; the STS deletes the old pod before creating the new one, so
  our slot is free first. Do not run alongside another GPU pod recreate on
  the same node (frigate, jellyfin, immich, makemkv, scrypted) or the
  intel-gpu-plugin roll in `helm-drift-detection` — declared in
  `conflicts_with` for the latter.
- **Library-tools jobs hit the Plex API**: `media-intake-watcher` (*/30, triggers
  rescans), `media-metadata-coverage` (hourly :00), `media-per-item-refresh`
  (every 6h at :00), `media-library-audit` 01:45, `media-plex-fs-classifier`
  01:35. A run landing in the ~3 min outage fails once and retries next
  schedule; §2.7 times the push to avoid them. Do not suspend them (that is a
  manifest change outside this plan).
- **media-naming-p3** renames files on this share and re-identifies Plex
  items; must never share a window (declared).
- **Plex butler** runs DB backups/maintenance at night (copies at 02:04 every
  3 days). A restart interrupts any running butler task harmlessly; the §3.2
  copy is independent of it.
- **Prometheus** is read by G9: no `kube-prometheus-stack` plan is open today
  (checked 2026-10-28); if one is added for the same night it must go into
  `conflicts_with` on both sides.
- **Execution class:** `capability_change: true` routes this HUMAN-GATED
  despite `risk: low`; it needs an operator GO, it cannot ride SD-10.
- **Repo correction owed (not done here):** `check-all-versions.py` has no
  release-notes source for `plexinc/pms-docker`, so every Plex build will be
  held by G3 the same way. The authoritative source is
  `https://plex.tv/api/downloads/5.json` (`computer.Linux.version`,
  `items_added`, `items_fixed`).
