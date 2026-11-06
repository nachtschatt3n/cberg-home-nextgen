---
plan_id: immich-server-3.3.6
component: immich-server
also_covers: [immich-machine-learning]   # ONE plan for both coverage groups (immich-server-3.3.6 +
                                         # immich-machine-learning-3.3.6): Renovate PR #484 moves both tags.
pr: 484                               # Renovate "update immich monorepo ( v3.3.5 -> v3.3.6 )", OPEN 2026-11-05,
                                      # CI green (Flate Render Gate, Flux Local Diff x2). Executed as TWO direct
                                      # commits (ML, then server), not by merging the grouped PR (see §6).
kind: image
current: "v3.3.5"                     # live 2026-11-06: deploy/immich-server ghcr.io/immich-app/immich-server:v3.3.5,
                                      #   imageID @sha256:485d546a2e31d6a8b4db8423fcba5c109de8c218d93410af115fd1ccfc4352a6;
                                      # deploy/immich-machine-learning ...immich-machine-learning:v3.3.5-openvino,
                                      #   imageID @sha256:1dbac7f811b51b80c55ee0cf678e0089d3532c798f14a65747d5d7b473a4f9d6
                                      # (both == ghcr index digests, HEAD 2026-11-06). Both pods on k8s-nuc14-01.
target: "v3.3.6"                      # server v3.3.6 index sha256:e1981983b1c13f6024b57d72e7ecae3342eed1581201ab09fb248932d86c593a
                                      # ML v3.3.6-openvino index sha256:035c30de002da9d4d4ae3872107bb9d8e195ead1c1f9fd470a2b0149ed37aec1
                                      # (HEAD manifests 2026-11-06). Release published 2026-11-04T17:24Z.
update_type: patch
risk: low                             # MEASURED, not assumed: compare v3.3.5...v3.3.6 has NO file under
                                      # server/src/schema/migrations (server change = package.json version string
                                      # only). The only functional change is ML: ORT rebuilt with --no_telemetry
                                      # + ORT_DISABLE_TELEMETRY. Residual risk = an OpenVINO EP regression from
                                      # the ORT rebuild (ML is stateless, git-revert rollback).
est_duration_min: 50                  # pre-checks 5 + dump 2 (20 s in-pod on 2026-10-22, 1241 MB DB) + scratch
                                      # restore-proof <=20 + ML roll/verify 8 + server roll/verify 8 + slack 7.
needs_reboot: false
touches:
  namespaces: [media]
  resources:
    - helmrelease/immich-machine-learning     # edit 1: machine-learning-helmrelease.yaml tag (+ fallback comment)
    - deployment/immich-machine-learning      # strategy Recreate (live): ~1-2 min no ML (smart search / face jobs queue)
    - helmrelease/immich-server               # edit 2: helmrelease.yaml main container tag
    - deployment/immich-server                # strategy Recreate (live): ~1-2 min API/web outage
    - service/immich-server                   # unchanged; endpoints move to the new pod
    - service/immich-machine-learning         # unchanged; endpoints move to the new pod
    - deployment/immich-postgres              # NOT restarted; scratch database immich_restoretest created + dropped
                                              # (restore proof); database `immich` gets one version_history row, no schema change
    - pvc/immich-pg-data                      # longhorn 20Gi (3.5G used, 17G free 2026-11-06); scratch DB ~1.3G transient
    - pvc/immich-data                         # CIFS cifs-immich-cache: READ only (nightly dumps under /data/backups)
    - pvc/immich-ml-cache                     # longhorn; models reused unchanged, read only
  shared: [igpu-i915, monitoring]             # both pods request gpu.intel.com/i915: 1 on k8s-nuc14-01; Recreate frees then
                                              # re-claims each slot. §4 reads Prometheus (the window's instrument).
depends_on: []
conflicts_with:
  - redis-fleet-8.10.3                # rolls media/immich-redis (BullMQ store); its gates and ours would each read the
                                      # other's Recreate/queue drop as their own.
  - helm-drift-detection              # rolls the intel-gpu-plugin DaemonSet (i915 re-register under our new pods) and
                                      # changes how helm-controller applies these HRs.
  - flux-oci-chart-sources            # may move the app-template chart source under these HRs mid-window.
  - talos-linux-1.14.5                # node roll (exclusive): reboots nuc14-01 (server+ML) and nuc14-03 (immich-postgres).
  - talos-power-tuning-ab             # changes the nuc14 thermal/power envelope; immich-server's cpu:4 cap is a thermal bound.
  - longhorn-1.13.0                   # storage engine bump (exclusive) under immich-pg-data while we dump/restore it.
  - icloud-drive-fleet-2.3.0          # writes the icloud-backup tree immich reads (ro); a mass re-download triggers
                                      # library-scan jobs that drift the §2.5/§3.2/§4.3 count comparisons.
  - frigate-reolink-go2rtc-flv        # shared igpu-i915 (both plans declare it). frigate runs on k8s-nuc14-02 today
                                      # (immich on -01), but its Recreate can land on -01 and contend for a slot while
                                      # §4.2's GPU-device gate runs. Not mirrored there yet (vetted, HUMAN-GATED).
exclusive: false
security_ref: F-7424ba26              # disposition + all detail on the DB record only (docs/sops/vulnerability-disclosure.md)
security_driven: false                # true would claim a remediation the measurement contradicts.
capability_change: false              # server: version string only (no route/permission/API/exposure change).
                                      # ML: REMOVES an unintended outbound telemetry path (ORT -> Microsoft); same
                                      # inference behaviour, nothing new the software can do.
rollback_class: git-revert            # MEASURED: no migration between v3.3.5 and v3.3.6, and Immich's downgrade guard
                                      # (server/src/repositories/database.repository.ts@v3.3.6, runMigrations) fires
                                      # ONLY on "previously executed migration ... is missing". The v3.3.6 boot adds a
                                      # version_history row, which version.service.ts never compares against for
                                      # downgrade. A v3.3.5 server therefore boots on a DB a v3.3.6 server touched.
                                      # The dump + restore-proof below is kept anyway (deny rule *immich*, §6).
backup_gate: "§3.1 fresh plain-SQL pg_dump of database immich taken from deploy/immich-postgres AFTER the pre-checks and BEFORE any tag edit is pushed, streamed to $HOME/immich-backups/pre-3.3.6/immich.sql.gz on the Mac under set -o pipefail. PASS = gzip -t ok AND size >= 300000000 bytes (Immich's own gzip of the same DB is 413,739,579 B on 2026-11-06; the 2026-10-22 gzip -1 dump was 458,994,958 B) AND the stream ends with '-- PostgreSQL database dump complete' AND the 'COPY public.' block count equals the live public BASE TABLE count (72 on 2026-11-06) AND the dump's newest kysely_migrations row is 1792213725597-AddAssetFaceAssetState. Secondary layers: Immich's own 02:00 nightly dump of today under /data/backups (v3.3.5 name), and the 23:00Z Longhorn backup of pvc-34a7dcaa-1069-415b-8abb-84da7acf914e (immich-pg-data) FRESH < 26h."
restore_proof: "§3.2: the §3.1 dump is restored into a SCRATCH database immich_restoretest on the same immich-postgres instance (psql -v ON_ERROR_STOP=1, Immich's documented search_path rewrite) and, BEFORE any tag edit is pushed, count(*) of asset, asset_face, person, \"user\", album and library in immich_restoretest must equal the §2.5 live counts, the public BASE TABLE count must be 72, the newest kysely_migrations row must be 1792213725597-AddAssetFaceAssetState, and pg_extension must list vchord and vector. Any mismatch or a psql error = STOP, do not push. The scratch DB is dropped at the end of §3.2 by its exact name (never DROP DATABASE immich here)."
finding_refs: [F-eff49af5, F-6d0f4efc]  # F-eff49af5: version, "immich-server: image ... v3.3.5 -> v3.3.6 (patch)".
                                        # F-6d0f4efc: version, "immich-machine-learning: image ... v3.3.5-openvino" (-> v3.3.6-openvino).
                                        # Queried 2026-11-06 (`policy-cli.py finding list --grep immich`).
review: null
status: draft
window: null
premises:
  - id: server-image-is-v3.3.5
    why: >-
      current, the digests and the baselines were captured against this pin. If the
      Deployment already moved, this plan is stale (or Step 0 already applied it).
    run: |-
      kubectl get deploy immich-server -n media -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "ghcr.io/immich-app/immich-server:v3.3.5"
  - id: ml-image-is-v3.3.5-openvino
    why: "Same for the ML leg; the §4.1 digest gate assumes this starting point."
    run: |-
      kubectl get deploy immich-machine-learning -n media -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "ghcr.io/immich-app/immich-machine-learning:v3.3.5-openvino"
  - id: server-hr-ready
    why: "A HelmRelease already failing would mask whether the bump itself reconciled."
    run: |-
      kubectl get helmrelease immich-server -n media -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: ml-hr-ready
    why: "Same, for the ML HelmRelease."
    run: |-
      kubectl get helmrelease immich-machine-learning -n media -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: server-strategy-recreate
    why: >-
      Single replica holding an i915 slot; RollingUpdate would start the new pod while
      the old one still serves and holds the GPU slot.
    run: |-
      kubectl get deploy immich-server -n media -o jsonpath='{.spec.strategy.type}'
    expect_exact: "Recreate"
  - id: ml-strategy-recreate
    why: "ML mounts the RWO longhorn immich-ml-cache; RollingUpdate risks Multi-Attach (longhorn-rwo-multi-attach SOP)."
    run: |-
      kubectl get deploy immich-machine-learning -n media -o jsonpath='{.spec.strategy.type}'
    expect_exact: "Recreate"
  - id: immich-alerts-quiet
    why: "ImmichServerNotReady / ImmichMLNotReady / ImmichPodCrashLooping must be quiet before the change, or §4 cannot attribute a firing."
    run: |-
      kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=ALERTS%7Balertname%3D~%22ImmichServerNotReady%7CImmichMLNotReady%7CImmichPodCrashLooping%22%2Calertstate%3D%22firing%22%7D'
    expect_contains: '"result":[]'
  - id: immich-postgres-still-pg14
    why: >-
      Renovate PR #282 (immich-app/postgres 14 -> 16, held) must not have landed: the
      dump/restore proof, the pg14 restore path in §5.3 and the §2.5 baselines assume pg14.
    run: |-
      kubectl get deploy immich-postgres -n media -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_matches: '^ghcr\.io/immich-app/postgres:14-'
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/immich.md
  - docs/sops/backup.md
  - docs/sops/storage-safety.md
  - docs/sops/longhorn-rwo-multi-attach.md
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/vulnerability-disclosure.md
generated: "2026-11-06"
---

# immich v3.3.5 -> v3.3.6 (server + machine-learning)

## 1. Summary & why held

Two one-line image-tag bumps in `kubernetes/apps/media/immich/app/`:
- `machine-learning-helmrelease.yaml`: `tag: v3.3.5-openvino` -> `v3.3.6-openvino` (plus the
  fallback comment `plain v3.3.5 (CPU) tag` -> `v3.3.6`, kept in step as last time);
- `helmrelease.yaml`: main container `tag: v3.3.5` -> `v3.3.6`.

The two `busybox:1.38.0` init containers (`wait-for-postgres`, `wait-for-redis`) in the server
pod are **unchanged** and out of scope (they appear in the coverage group's image list only
because they live in the same HelmRelease; PR #484 does not touch them).

**Upstream evidence** (GitHub release `immich-app/immich` v3.3.6, 2026-11-04):
> "Unfortunately we missed that onnxruntime enabled telemetry by default in a recent release,
> resulting in the ML container automatically sending anonymous metric data to Microsoft. We
> have now disabled it."
Single PR: #32956 `fix(ml): disable onnxruntime telemetry`. `compare v3.3.5...v3.3.6` (2 commits,
15 files) changes, beyond version strings: `machine-learning/Dockerfile` (ORT build gains
`--no_telemetry` in the OpenVINO build stage) and `machine-learning/immich_ml/__init__.py`
(+`os.environ.setdefault("ORT_DISABLE_TELEMETRY", "1")`). The only `server/` change is
`server/package.json` `"version": "3.3.5"` -> `"3.3.6"`. **No file under
`server/src/schema/migrations/`.**

**Why held — the deny rule `*immich*` in `runbooks/auto-update-policy.yaml`** ("Immich server
applies forward-only DB migrations; revert after migration crash-loops. Plan lane only: dump +
scratch-restore proof first"). For THIS release the stated hazard is **absent**:
- no migration ships (above);
- Immich's downgrade refusal is keyed only on a missing migration
  (`database.repository.ts@v3.3.6`, `runMigrations`: throws "Downgrades are not supported"
  only when kysely reports `previously executed migration (.+) is missing`);
- `version.service.ts@v3.3.6` only INSERTs a `version_history` row (`3.3.6`) on boot and never
  refuses an older version. Live `version_history` today: 3.3.5 / 3.3.3 / 3.3.1.

So the hold is a false positive *for this target*, and `rollback_class: git-revert` is the
measured truth. The plan still takes the fresh dump and scratch-restore proof the deny rule
demands (cheap, proven on 2026-10-23, and it is the safety net if the §4.2 migration-head
guard ever reads something unexpected). `risk: low`; the main operational risk is the ML side:
ORT is **rebuilt from source** with a new flag, so an OpenVINO execution-provider regression
(the SOP's known per-release failure mode, `docs/sops/immich.md` §7) is the thing to watch.

**Security reference F-7424ba26.** This plan carries `security_ref: F-7424ba26`. Whether this
landing affects that finding, and its disposition, are recorded on the sweep_findings row only
(docs/sops/vulnerability-disclosure.md). Do not close it with this plan's SHAs; the next sweep
scan decides.

Context: Immich here is a read-only iCloud-library viewer; `/data` (CIFS `cifs-immich-cache`)
is fully derived, originals are on a `ro` mount (`cifs-immich-icloud-backup`). **No PVC is
deleted, created or resized by this plan.**

## 2. Pre-checks

Run from `/Users/mu/code/cberg-home-nextgen` (zsh on the Mac mini). Any FAIL = do not run.

2.1 Premises:
```bash
.venv/bin/python3 runbooks/plan-premises.py immich-server-3.3.6 --require-premises
```

2.2 Flux and workloads healthy:
```bash
flux get helmreleases -n media | grep -E 'NAME|immich'   # all four immich-* Ready=True
kubectl get pods -n media -o wide | grep immich           # 4/4 Running
```

2.3 Target tags exist with the digests recorded in frontmatter (upstream did not re-push):
```bash
for r in immich-server:v3.3.6 immich-machine-learning:v3.3.6-openvino; do
  repo=${r%%:*}; tag=${r##*:}
  TOK=$(curl -s "https://ghcr.io/token?scope=repository:immich-app/$repo:pull" | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
  echo "$r $(curl -sI -H "Authorization: Bearer $TOK" \
    -H 'Accept: application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.list.v2+json,application/vnd.oci.image.manifest.v1+json' \
    https://ghcr.io/v2/immich-app/$repo/manifests/$tag | grep -i docker-content-digest)"
done
# PASS: server  sha256:e1981983b1c13f6024b57d72e7ecae3342eed1581201ab09fb248932d86c593a
#       ML      sha256:035c30de002da9d4d4ae3872107bb9d8e195ead1c1f9fd470a2b0149ed37aec1  (measured 2026-11-06)
# FAIL: empty digest (404/auth) or a different digest -> stop, re-read the release.
```

2.4 DB disk headroom for the scratch restore (needs > 5G free; 17G free on 2026-11-06):
```bash
kubectl exec -n media deploy/immich-postgres -- df -h /var/lib/postgresql/data
```

2.5 Baseline counts (kept in /tmp, compared by §3.2 and §4.3):
```bash
mkdir -p /tmp/immich-336
kubectl exec -n media deploy/immich-postgres -- sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -F" " \
  -c "select (select count(*) from asset),(select count(*) from asset_face),(select count(*) from person),(select count(*) from \"user\"),(select count(*) from album),(select count(*) from library)" \
  -c "select count(*) from information_schema.tables where table_schema=\$\$public\$\$ and table_type=\$\$BASE TABLE\$\$" \
  -c "select name from kysely_migrations order by name desc limit 1"' | tee /tmp/immich-336/baseline.txt
```
Measured 2026-11-06: `79224 60902 2375 2 0 2` / `72` / `1792213725597-AddAssetFaceAssetState`.
Third line must read `1792213725597-AddAssetFaceAssetState`; anything newer = a v3.3.6+ server
already ran -> plan stale, STOP.

2.6 Backups and ML baselines (the premise runner cannot express these):
```bash
# (a) today's Immich nightly dump exists (absence also means the job queue is unhealthy):
kubectl exec -n media deploy/immich-server -c main -- ls /data/backups | grep -c "immich-db-backup-$(TZ=Europe/Berlin date +%Y%m%d)T020000-v3.3.5"   # PASS 1; 0 = STOP
# (b) Longhorn backup of immich-pg-data under 26h:
.venv/bin/python3 runbooks/longhorn-backup-age.py pvc-34a7dcaa-1069-415b-8abb-84da7acf914e --max-hours 26   # must contain FRESH
# (c) ML baseline: the iGPU is VISIBLE to OpenVINO (positive device check), only the
#     known-broken OCR model fails to prepare. The device check is the gate: upstream
#     immich_ml/sessions/ort.py@v3.3.6 `openvino_device` returns "GPU.<id>" only if
#     get_available_openvino_device_ids() lists a GPU, else silently "CPU" (no info-level log).
kubectl exec -n media deploy/immich-machine-learning -- python3 -c "import onnxruntime as ort;print(ort.capi._pybind_state.get_available_openvino_device_ids())" \
  | tee /tmp/immich-336/ov-devices-before.txt
#   measured 2026-11-06 (v3.3.5-openvino, ORT 1.30.0): ['CPU', 'GPU']   -> must contain 'GPU'; else STOP (already degraded)
kubectl exec -n media deploy/immich-machine-learning -- sh -c 'ls -d /cache/*/*/*/openvino/*/ 2>/dev/null' | tee /tmp/immich-336/ov-gpu-cachedirs-before.txt
#   GPU-kind cache dirs (ort.py `directory` = <model>/openvino/<device.kind>/; kind is empty on CPU).
#   measured 2026-11-06: 6 dirs, 12.71.4-112eu under clip/{textual,visual}, buffalo_l/{detection,recognition}, ocr/LATIN__PP-OCRv5_mobile/{detection,recognition} -- informational
kubectl -n media logs deploy/immich-machine-learning 2>/dev/null | sed 's/\x1b\[[0-9;]*m//g' > /tmp/immich-336/ml-before.log
grep -c "\['OpenVINOExecutionProvider'" /tmp/immich-336/ml-before.log                 # LIVENESS only (54 on 2026-11-06):
#   this line lists AVAILABLE providers and prints identically when OpenVINO runs on device CPU.
grep -A3 -E 'RuntimeError: *Preparing' /tmp/immich-336/ml-before.log | grep -oE '/cache/[A-Za-z_-]+/[A-Za-z0-9_.-]+/[a-z]+' | sort | uniq -c
#   expected: only /cache/ocr/LATIN__PP-OCRv5_mobile/recognition (pre-existing, unrelated)
# (d) server-side non-OCR ML request failures, last 24h (0 on 2026-11-06):
kubectl -n media logs deploy/immich-server --since=24h 2>/dev/null | sed 's/\x1b\[[0-9;]*m//g' \
  | grep -E "Machine learning request '" | grep -vc "request '{\"ocr\""
# (e) telemetry kill-switch ABSENT on v3.3.5 (proves §4.4 can fail):
kubectl exec -n media deploy/immich-machine-learning -- sh -c 'cd /usr/src && python3 -c "import immich_ml,os;print(\"ORT_TELEMETRY_ENV=\"+str(os.environ.get(\"ORT_DISABLE_TELEMETRY\")))"'
#   measured 2026-11-06: ORT_TELEMETRY_ENV=None
```

## 3. Steps

### 3.1 Fresh pre-upgrade dump to the Mac (backup_gate)
```bash
set -o pipefail
mkdir -p "$HOME/immich-backups/pre-3.3.6" && chmod 700 "$HOME/immich-backups"
D="$HOME/immich-backups/pre-3.3.6/immich.sql.gz"
kubectl exec -n media deploy/immich-postgres -- sh -c \
  'pg_dump --clean --if-exists -U "$POSTGRES_USER" -d "$POSTGRES_DB" | gzip -1' > "$D" \
  || { echo "DUMP FAILED"; exit 1; }
gzip -t "$D" && echo GZIP_OK
stat -f %z "$D"                                                                 # >= 300000000
gunzip -c "$D" | tail -5 | grep -c -- '-- PostgreSQL database dump complete'    # 1
gunzip -c "$D" | grep -c '^COPY public\.'                                       # == 72
gunzip -c "$D" | awk '/^COPY public.kysely_migrations /{f=1;next} f&&/^\\\./{exit} f' | sort | tail -1
#   must contain 1792213725597-AddAssetFaceAssetState
```
Any check failing = STOP (no push). Can fail: a truncated stream fails `gzip -t` / the trailer
check; a wrong DB prints a COPY count far from 72.

### 3.2 Restore proof into a SCRATCH database (restore_proof)
```bash
set -o pipefail
D="$HOME/immich-backups/pre-3.3.6/immich.sql.gz"
kubectl exec -n media deploy/immich-postgres -- sh -c \
  'psql -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE immich_restoretest OWNER \"$POSTGRES_USER\""'
gunzip -c "$D" \
 | sed "s/SELECT pg_catalog.set_config('search_path', '', false);/SELECT pg_catalog.set_config('search_path', 'public, pg_catalog', true);/g" \
 | kubectl exec -i -n media deploy/immich-postgres -- sh -c \
   'psql -U "$POSTGRES_USER" -d immich_restoretest -v ON_ERROR_STOP=1 -q' > /tmp/immich-336/restoretest.log 2>&1 \
 && echo RESTORE_OK || echo RESTORE_FAILED
kubectl exec -n media deploy/immich-postgres -- sh -c 'psql -U "$POSTGRES_USER" -d immich_restoretest -At -F" " \
  -c "select (select count(*) from asset),(select count(*) from asset_face),(select count(*) from person),(select count(*) from \"user\"),(select count(*) from album),(select count(*) from library)" \
  -c "select count(*) from information_schema.tables where table_schema=\$\$public\$\$ and table_type=\$\$BASE TABLE\$\$" \
  -c "select name from kysely_migrations order by name desc limit 1" \
  -c "select string_agg(extname, \$\$,\$\$ order by extname) from pg_extension where extname in (\$\$vchord\$\$,\$\$vector\$\$)"' \
  | tee /tmp/immich-336/restoretest.txt
diff <(head -3 /tmp/immich-336/baseline.txt) <(head -3 /tmp/immich-336/restoretest.txt) && echo COUNTS_MATCH
grep -c '^vchord,vector$' /tmp/immich-336/restoretest.txt   # 1
```
PASS = `RESTORE_OK`, `COUNTS_MATCH`, extensions `1`. A real failure prints a psql `ERROR:` in
`/tmp/immich-336/restoretest.log` (ON_ERROR_STOP aborts) or a count of 0. If only
`asset`/`asset_face` differ (night jobs between §2.5 and §3.1), re-take §2.5 and the restoretest
counts back-to-back once; a second mismatch = STOP. Restore > 20 min = abort, drop, STOP.

Drop the scratch DB **by its exact name** (both on PASS and on abort):
```bash
kubectl exec -n media deploy/immich-postgres -- sh -c \
  'psql -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 -c "DROP DATABASE immich_restoretest"'
```

### 3.3 ML leg first (own commit)
Dry-tested on a scratch copy (BSD sed, 2026-11-06); resulting diff, exactly two lines:
```
47c47
<             # Fallback on OpenVINO regressions: swap to the plain `v3.3.5` (CPU) tag.
>             # Fallback on OpenVINO regressions: swap to the plain `v3.3.6` (CPU) tag.
51c51
<               tag: v3.3.5-openvino
>               tag: v3.3.6-openvino
```
```bash
sed -i '' \
  -e 's|^\([[:space:]]*tag: \)v3\.3\.5-openvino$|\1v3.3.6-openvino|' \
  -e 's|swap to the plain `v3\.3\.5` (CPU) tag|swap to the plain `v3.3.6` (CPU) tag|' \
  kubernetes/apps/media/immich/app/machine-learning-helmrelease.yaml
git diff --stat -- kubernetes/apps/media/immich/app/machine-learning-helmrelease.yaml   # 1 file, 2 +/2 -
cat > /tmp/immich-336/msg-ml.txt <<'EOF'
fix(immich-ml): v3.3.5-openvino -> v3.3.6-openvino (plan immich-server-3.3.6)

Upstream #32956: onnxruntime telemetry disabled (ORT rebuilt --no_telemetry +
ORT_DISABLE_TELEMETRY). No ML inference change. Renovate PR #484 (ML leg).
EOF
git commit --only kubernetes/apps/media/immich/app/machine-learning-helmrelease.yaml -F /tmp/immich-336/msg-ml.txt
git log -1 --format=%s      # must be the subject above; amend before push if not (shared worktree)
git show --stat HEAD        # exactly 1 file
git push
```
Record the SHA as `$ML_BUMP`. Flux webhook reconciles; wait, then run §4.1 (ML part), §4.2 and
§4.4 **before** the server leg. Any ML FAIL -> §5.1, and do not start §3.4.

### 3.4 Server leg (own commit)
Dry-tested on a scratch copy (BSD sed, 2026-11-06): `77c77 <  tag: v3.3.5 --->  tag: v3.3.6`
(the ML file uses `tag: v3.3.5-openvino`/`v3.3.6-openvino` and is not matched; the busybox
`tag: 1.38.0` lines are not matched).
```bash
sed -i '' 's|^\([[:space:]]*tag: \)v3\.3\.5$|\1v3.3.6|' kubernetes/apps/media/immich/app/helmrelease.yaml
git diff --stat -- kubernetes/apps/media/immich/app/helmrelease.yaml   # 1 file, 1 +/1 -
cat > /tmp/immich-336/msg-server.txt <<'EOF'
fix(immich): immich-server v3.3.5 -> v3.3.6 (plan immich-server-3.3.6)

Version-string-only server release (no schema migration between v3.3.5 and
v3.3.6). Renovate PR #484 (server leg); dump + scratch-restore proof taken first.
EOF
git commit --only kubernetes/apps/media/immich/app/helmrelease.yaml -F /tmp/immich-336/msg-server.txt
git log -1 --format=%s && git show --stat HEAD   # own subject, exactly 1 file
git push
```
Record the SHA as `$SRV_BUMP`. The `upgrade.remediation.retries: 3` block is left as is this
time (see §6: a Helm auto-rollback to v3.3.5 is harmless without a migration). Renovate closes
PR #484 itself once main satisfies it; if it is still open after the next Renovate run, close
it with a comment naming both SHAs.

## 4. Verification

4.1 CONTENTS ASSERTION: the running containers are the target index digests (rollout status
alone can green-light the old generation) — measured by pod `imageID`:
```bash
kubectl rollout status deploy/immich-machine-learning -n media --timeout=10m
kubectl get pod -n media -l app.kubernetes.io/name=immich-machine-learning \
  -o jsonpath='{range .items[*]}{.metadata.name} {.status.phase} {.status.containerStatuses[0].imageID}{"\n"}{end}'
# PASS: exactly one pod, Running, imageID ends sha256:035c30de002da9d4d4ae3872107bb9d8e195ead1c1f9fd470a2b0149ed37aec1
# FAIL: old digest sha256:1dbac7f8... , two pods, or Pending (i915 / Multi-Attach)
# --- after §3.4:
kubectl rollout status deploy/immich-server -n media --timeout=10m
kubectl get pod -n media -l app.kubernetes.io/instance=immich-server \
  -o jsonpath='{.items[0].status.containerStatuses[?(@.name=="main")].imageID}'
# PASS: ends sha256:e1981983b1c13f6024b57d72e7ecae3342eed1581201ab09fb248932d86c593a
# FAIL: old digest sha256:485d546a... (the live value on 2026-11-06)
```

4.2 CONTENTS ASSERTION: ML inference returns real embeddings and runs the face pipeline —
measured by a direct `/predict` call (v3.3.3/v3.3.5 baseline: textual 512 dims all non-zero,
visual 512 dims, facial-recognition key present):
```bash
python3 - <<'EOF'
import zlib,struct
w=h=256
raw=b''.join(b'\x00'+b''.join(bytes([(x*7+y*3)%256,(x*y)%256,(y*5)%256]) for x in range(w)) for y in range(h))
def c(t,d): return struct.pack('>I',len(d))+t+d+struct.pack('>I',zlib.crc32(t+d)&0xffffffff)
open('/tmp/immich-336/probe.png','wb').write(b'\x89PNG\r\n\x1a\n'+c(b'IHDR',struct.pack('>IIBBBBB',w,h,8,2,0,0,0))+c(b'IDAT',zlib.compress(raw))+c(b'IEND',b''))
EOF
kubectl -n media port-forward svc/immich-machine-learning 13003:3003 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s -m 120 -X POST http://127.0.0.1:13003/predict \
  -F 'entries={"clip":{"textual":{"modelName":"ViT-B-32__openai"}}}' -F 'text=a photo of a dog' \
  | python3 -c "import sys,json;r=json.load(sys.stdin);e=r['clip'];e=json.loads(e) if isinstance(e,str) else e;n=sum(1 for x in e if x!=0);print('TEXT',len(e),n);sys.exit(0 if len(e)==512 and n>500 else 1)" && echo TEXT_PASS || echo TEXT_FAIL
curl -s -m 180 -X POST http://127.0.0.1:13003/predict \
  -F 'entries={"clip":{"visual":{"modelName":"ViT-B-32__openai"}},"facial-recognition":{"detection":{"modelName":"buffalo_l","options":{"minScore":0.7}},"recognition":{"modelName":"buffalo_l"}}}' \
  -F 'image=@/tmp/immich-336/probe.png' \
  | python3 -c "import sys,json;r=json.load(sys.stdin);e=r['clip'];e=json.loads(e) if isinstance(e,str) else e;ok=len(e)==512 and isinstance(r.get('facial-recognition'),list) and r.get('imageWidth')==256;print('VISUAL',len(e),'faces',len(r.get('facial-recognition',[])));sys.exit(0 if ok else 1)" && echo VISUAL_PASS || echo VISUAL_FAIL
kill $PF 2>/dev/null
```
PASS = `TEXT_PASS` and `VISUAL_PASS`. **This `/predict` call is the real ML functional check**
(the §4.6 server-side "Machine learning request" grep is only an absence gate over whatever
jobs happened to run). Can fail: an HTTP 500 / refused connection / non-JSON body makes the
python raise; a zero vector fails the `n>500` floor. (faces=0 is expected; the probe image has
no faces.) Then, the iGPU path (the release's real risk — ORT was rebuilt from source):
```bash
# GATE: OpenVINO can see the iGPU in the NEW pod (positive device check, baseline §2.6c):
kubectl exec -n media deploy/immich-machine-learning -- python3 -c "import onnxruntime as ort;print(ort.capi._pybind_state.get_available_openvino_device_ids())" \
  | tee /tmp/immich-336/ov-devices-after.txt
grep -c "'GPU" /tmp/immich-336/ov-devices-after.txt                       # PASS 1 (baseline ['CPU', 'GPU'])
kubectl -n media logs deploy/immich-machine-learning 2>/dev/null | sed 's/\x1b\[[0-9;]*m//g' > /tmp/immich-336/ml-after.log
grep -c "\['OpenVINOExecutionProvider'" /tmp/immich-336/ml-after.log      # LIVENESS only, >= 1 (not a GPU proof)
grep -A3 -E 'RuntimeError: *Preparing' /tmp/immich-336/ml-after.log | grep -oE '/cache/[A-Za-z_-]+/[A-Za-z0-9_.-]+/[a-z]+' \
  | grep -vc 'ocr/LATIN__PP-OCRv5_mobile/recognition'                     # PASS 0
# INFORMATIONAL (not a gate): GPU-kind cache dirs still present, and whether any were written
# after the new pod started (a cache HIT does not rewrite them, so "none newer" is not a failure):
kubectl exec -n media deploy/immich-machine-learning -- sh -c 'ls -d /cache/*/*/*/openvino/*/ 2>/dev/null' \
  | diff /tmp/immich-336/ov-gpu-cachedirs-before.txt - && echo GPU_CACHEDIRS_SAME
MLSTART=$(kubectl get pod -n media -l app.kubernetes.io/name=immich-machine-learning -o jsonpath='{.items[0].status.startTime}')
kubectl exec -n media deploy/immich-machine-learning -- find /cache -path '*/openvino/*/*' -newermt "$MLSTART" | head -5
```
Why the device check and not the log line: upstream `immich_ml/sessions/ort.py@v3.3.6`
(`openvino_device`, ~L143-145) returns `"GPU.<device_id>"` only when
`get_available_openvino_device_ids()` contains a GPU entry and otherwise silently picks `"CPU"`
with no info-level log, while the "Setting execution providers to ['OpenVINOExecutionProvider',
'CPUExecutionProvider']" line lists AVAILABLE providers and prints identically in both cases.
Can fail: a rebuilt ORT/OpenVINO that lost the GPU plugin, or a pod that came up without the
`gpu.intel.com/i915` device, prints `['CPU']` -> grep 0 = FAIL -> §5.1. A model other than the
known-broken OCR one failing to prepare -> second count >= 1 = FAIL.

4.3 CONTENTS ASSERTION: server DB unchanged in shape, no data lost — measured against §2.5:
```bash
kubectl exec -n media deploy/immich-postgres -- sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -F" " \
  -c "select (select count(*) from asset),(select count(*) from asset_face),(select count(*) from person),(select count(*) from \"user\"),(select count(*) from album),(select count(*) from library)" \
  -c "select count(*) from information_schema.tables where table_schema=\$\$public\$\$ and table_type=\$\$BASE TABLE\$\$" \
  -c "select name from kysely_migrations order by name desc limit 1" \
  -c "select version from version_history order by \"createdAt\" desc limit 1"'
```
PASS = migration head still `1792213725597-AddAssetFaceAssetState`, table count `72`, newest
`version_history` = `3.3.6`; `person`/`user`/`album`/`library` equal to baseline, `asset`/`asset_face`
`>=` baseline. Can fail: before the server leg the last line reads `3.3.5` (live 2026-11-06); a
NEW migration head means upstream code differs from the measured compare -> stop and treat the
rollback as §5.3 (restore), not a plain revert.

4.4 CONTENTS ASSERTION: the telemetry kill-switch is live in the ML package — measured in the
new pod (pre-state `ORT_TELEMETRY_ENV=None`, §2.6e):
```bash
kubectl exec -n media deploy/immich-machine-learning -- sh -c 'cd /usr/src && python3 -c "import immich_ml,os;print(\"ORT_TELEMETRY_ENV=\"+str(os.environ.get(\"ORT_DISABLE_TELEMETRY\")))"'
kubectl exec -n media deploy/immich-machine-learning -- grep -c ORT_DISABLE_TELEMETRY /usr/src/immich_ml/__init__.py
```
PASS = `ORT_TELEMETRY_ENV=1` and `1`. FAIL = `None` / `0` (image is not v3.3.6 content).

4.5 API answers as v3.3.6 (unauthenticated endpoints):
```bash
kubectl port-forward -n media svc/immich-server 22830:2283 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s localhost:22830/api/server/version; echo
curl -s localhost:22830/api/server/ping; echo
kill $PF 2>/dev/null
```
PASS = `{"major":3,"minor":3,"patch":6}` and `{"res":"pong"}`. Can fail: the old pod answers `"patch":5`.

4.6 Server boot log of the NEW pod, read from its own `startTime` (never `--since=15m`, which can
start after the boot lines and read 0 on anything). Positive controls first — they prove the
window covers the whole boot — then the gates:
```bash
SRVSTART=$(kubectl get pod -n media -l app.kubernetes.io/instance=immich-server -o jsonpath='{.items[0].status.startTime}')
kubectl logs -n media deploy/immich-server -c main --since-time="$SRVSTART" 2>/dev/null | sed 's/\x1b\[[0-9;]*m//g' > /tmp/immich-336/srv-boot.log
grep -c '^Initializing Immich v3.3.6' /tmp/immich-336/srv-boot.log                  # CONTROL == 1 (boot banner inside the window)
grep -c 'Finished running migrations' /tmp/immich-336/srv-boot.log                  # CONTROL >= 2 (Microservices + Api workers)
grep -c 'Immich Server is listening .*\[v3.3.6\]' /tmp/immich-336/srv-boot.log      # CONTROL == 1
grep -c 'Migration ".*" succeeded' /tmp/immich-336/srv-boot.log                     # GATE   == 0 (no migration may run)
grep -ciE 'downgrades are not supported|migration.*(fail|error)|QueryFailedError|error: relation|column .* does not exist' /tmp/immich-336/srv-boot.log   # GATE 0
```
Measured on the live v3.3.5 pod's boot (2026-10-23 01:42 local, startTime 2026-10-22T23:41:52Z,
same commands with `v3.3.5`): banner 1, `Finished running migrations` 2, listening `[v3.3.5]` 1,
error grep 0 — and `Migration ".*" succeeded` **1** (`1792213725597-AddAssetFaceAssetState`, the
v3.3.5 migration). That boot is the known-bad shape for this gate: the same line on the v3.3.6
boot means a migration ran that the compare says does not exist -> STOP, treat rollback as §5.3.
If any CONTROL misses (log rotated, wrong pod, old pod still serving), the gates are unproven ->
re-read from the pod; never read a 0 gate as PASS without all three controls.

Server-side ML-request absence (secondary only; §4.2 `/predict` is the real ML check — this grep
only sees whatever jobs happened to run):
```bash
SINCE=$(kubectl -n media get pod -l app.kubernetes.io/name=immich-machine-learning -o jsonpath='{.items[0].status.startTime}')
kubectl -n media logs deploy/immich-server -c main --since-time="$SINCE" 2>/dev/null | sed 's/\x1b\[[0-9;]*m//g' \
  | grep -E "Machine learning request '" | grep -vc "request '{\"ocr\""                                                    # PASS 0 (baseline §2.6d = 0)
```
Can fail: the 2026-10-12 incident printed "Downgrades are not supported"; a broken ML backend
prints non-OCR `Machine learning request ... failed` lines.

4.7 Metrics and alerts:
CONTROL: metric up — `up{job="immich-server"}` returns two series (endpoints `metrics-api`,
`metrics-ms`), both `1`, from the NEW pod name (measured 2026-11-06: two series, both 1, pod
immich-server-8645f84d9-4t8k9 = the old pod; a series still naming it = stale scrape).
```bash
kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=up%7Bjob%3D%22immich-server%22%7D'
```
CONTROL: metric kube_pod_status_ready — `sum(kube_pod_status_ready{namespace="media",pod=~"immich-machine-learning-.*",condition="true"})` reads 1 (EMPTY or 0 = FAIL).
CONTROL: alertname ImmichServerNotReady — not firing 10 min after Ready.
CONTROL: alertname ImmichMLNotReady — not firing 10 min after Ready.
CONTROL: alertname ImmichPodCrashLooping — not firing.
CONTROL: alertname ImmichPodRestarted — not firing 15 min after Ready (warning, `increase(restarts[15m]) > 0`
for 1m; a clean Recreate starts the new pod at restartCount 0 and does not trip it, so a firing
here is a real container restart). Rule loaded and `inactive` on 2026-11-06 (`/api/v1/rules`).
```bash
kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=ALERTS%7Balertname%3D~%22ImmichServerNotReady%7CImmichMLNotReady%7CImmichPodCrashLooping%7CImmichPodRestarted%22%2Calertstate%3D%22firing%22%7D'
```
PASS = `"result":[]` (live 2026-11-06). Plus restart counts:
```bash
kubectl get pod -n media -l app.kubernetes.io/name=immich-machine-learning -o jsonpath='{.items[0].status.containerStatuses[0].restartCount}'   # 0
kubectl get pod -n media -l app.kubernetes.io/instance=immich-server -o jsonpath='{.items[0].status.containerStatuses[?(@.name=="main")].restartCount}'   # 0
```

4.8 Originals still read-only (SOP T2):
`kubectl exec -n media deploy/immich-server -c main -- touch /libraries/x` -> must fail with
`Read-only file system`.

4.9 Post-window: the next sweep re-rates F-eff49af5 / F-6d0f4efc (and the AR-accepted image
findings) against v3.3.6; close the version findings with
`policy-cli.py finding close <id> --commit <sha>` only if the sweep agrees.
**F-7424ba26 (security_ref):** do not close it with this plan's SHAs; the sweep's next scan of
v3.3.6 decides (detail on the DB record).

## 5. Rollback

Nothing in this release is forward-only (§1), so the default rollback is a per-leg git revert.
Revert only the leg that failed; never a range revert that also crosses an older immich-server
tag move.

5.1 ML leg failed (§4.1-ML / §4.2 / §4.4 / ML alerts):
```bash
git revert --no-edit $ML_BUMP
git log -1 --format=%s && git show --stat HEAD   # Revert of YOUR ML commit; only machine-learning-helmrelease.yaml
git push
```
If `git revert` refuses (shared index dirty), do the inverse edit and commit with `--only`:
```bash
sed -i '' -e 's|^\([[:space:]]*tag: \)v3\.3\.6-openvino$|\1v3.3.5-openvino|' \
  -e 's|swap to the plain `v3\.3\.6` (CPU) tag|swap to the plain `v3.3.5` (CPU) tag|' \
  kubernetes/apps/media/immich/app/machine-learning-helmrelease.yaml
git commit --only kubernetes/apps/media/immich/app/machine-learning-helmrelease.yaml -m "revert(immich-ml): back to v3.3.5-openvino (plan immich-server-3.3.6 rollback)"
git log -1 --format=%s && git show --stat HEAD && git push
```
Confirm: ML imageID ends `sha256:1dbac7f811b51b80c55ee0cf678e0089d3532c798f14a65747d5d7b473a4f9d6`,
§4.2 PASS again. Alternative only if the OpenVINO path alone broke: the SOP's plain CPU tag at
the same version (`v3.3.6`), operator's choice. Do not start §3.4 after an ML rollback.

5.2 Server leg failed, migration head unchanged (§4.3 still `1792213725597-AddAssetFaceAssetState`):
```bash
git revert --no-edit $SRV_BUMP      # inverse edit fallback: sed -i '' 's|^\([[:space:]]*tag: \)v3\.3\.6$|\1v3.3.5|' (dry-tested: restores the original byte-for-byte)
git log -1 --format=%s && git show --stat HEAD   # only helmrelease.yaml
git push
```
Confirm: server imageID ends `sha256:485d546a2e31d6a8b4db8423fcba5c109de8c218d93410af115fd1ccfc4352a6`,
`/api/server/version` = `{"major":3,"minor":3,"patch":5}`, §4.6 boot-log read from the reverted
pod's `startTime` shows banner `v3.3.5` = 1 and listening `[v3.3.5]` = 1 with the error grep 0
and `Migration ".*" succeeded` 0, alerts quiet, HR
Ready. v3.3.5 boots fine on the DB (the extra `version_history` row `3.3.6` is inert; a later
v3.3.6 boot simply adds another row).

5.3 Only if §4.3 showed a NEW migration head (contradicts the measured compare) and v3.3.5 then
refuses to start: the restore procedure, in order —
```bash
flux suspend helmrelease immich-server -n media
kubectl scale deploy/immich-server -n media --replicas=0
set -o pipefail
D="$HOME/immich-backups/pre-3.3.6/immich.sql.gz"
kubectl exec -n media deploy/immich-postgres -- sh -c \
  'psql -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 -c "DROP DATABASE \"$POSTGRES_DB\" WITH (FORCE)" -c "CREATE DATABASE \"$POSTGRES_DB\" OWNER \"$POSTGRES_USER\""'
gunzip -c "$D" \
 | sed "s/SELECT pg_catalog.set_config('search_path', '', false);/SELECT pg_catalog.set_config('search_path', 'public, pg_catalog', true);/g" \
 | kubectl exec -i -n media deploy/immich-postgres -- sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -q' \
 && echo RESTORE_OK
# re-run §2.5: PASS = identical to /tmp/immich-336/baseline.txt
git revert --no-edit $SRV_BUMP && git log -1 --format=%s && git show --stat HEAD && git push
flux resume helmrelease immich-server -n media
kubectl get deploy -n media immich-server -o jsonpath='{.spec.replicas}'   # 1; if 0: kubectl scale ... --replicas=1
```
Fallbacks if the Mac dump is unusable: today's `/data/backups/immich-db-backup-<today>T020000-v3.3.5-pg14.19.sql.gz`
(same restore pipe via `kubectl exec -n media deploy/immich-server -c main -- cat <file>` — run
before scaling the server to 0, or read it from the CIFS share), or the Longhorn backup of
`pvc-34a7dcaa-1069-415b-8abb-84da7acf914e` per `docs/sops/backup.md` (restore to a NEW volume;
never delete `immich-pg-data`).

Data-loss bound: only face/job results written after §3.1 on a read-only viewer
(regenerable). Originals are on a `ro` mount; `/data` is derived. **No PVC — CIFS or Longhorn —
is deleted at any point** (`docs/sops/storage-safety.md`).

Cleanup after a 7-day soak: `rm -rf "$HOME/immich-backups/pre-3.3.6"` (and the stale
`pre-3.3.5` directory from the previous plan).

## 6. Interference notes

- **Deny rule vs. this target.** `*immich*` holds every immich bump on the forward-only-migration
  reason. v3.3.6 carries no migration; this plan follows the rule's procedure anyway (dump +
  scratch-restore proof) but declares the measured `rollback_class: git-revert`. The window agent
  must still not let Step 0 / `auto-update.py` batch this bump into an auto-revertable batch —
  if Step 0 already moved either image, the image premises fail and this plan is stale.
- **Two commits, ML first.** Not merging grouped PR #484: a single grouped commit can only be
  reverted as a pair (the 2026-10-12 `b9a14f69` shape). ML is the leg with real (OpenVINO) risk
  and a free revert; verify it before the server moves. No hard coupling: the server talks to ML
  only via `/ping` and `/predict` with no version handshake, and a one-patch skew has run before.
- **Helm remediation:** `upgrade.remediation.retries: 3` (default strategy rollback) is left
  alone. Last plan set it to 0 because a Helm rollback onto a migrated DB crash-loops; with no
  migration, a Helm rollback to v3.3.5 is exactly §5.2 and harmless.
- **i915 / nuc14-01:** both Recreates free and re-claim a `gpu.intel.com/i915` slot on
  k8s-nuc14-01 (shared with jellyfin, makemkv). Hence `helm-drift-detection` (intel-gpu-plugin
  roll), `talos-power-tuning-ab` and `talos-linux-1.14.5` in `conflicts_with`.
- **immich-postgres on nuc14-03** takes the scratch-restore load (index builds); `longhorn-1.13.0`
  must not run under the dump/restore.
- **immich-redis:** `redis-fleet-8.10.3` rolls it and drops queued BullMQ jobs — conflicts.
- **icloud-drive-fleet-2.3.0:** a mass re-download churns the tree immich scans and drifts the
  count gates — conflicts.
- **Prometheus** is this plan's instrument; no kube-prometheus-stack plan is open on 2026-11-06,
  but any that appears must be added to `conflicts_with` (both sides).
- **Reciprocity:** `conflicts_with` here is not yet mirrored on `icloud-drive-fleet-2.3.0`,
  `longhorn-1.13.0`, `flux-oci-chart-sources`, `talos-power-tuning-ab` (they name the retired
  `immich-*-3.3.x` plans or nothing); the vetting pass should add `immich-server-3.3.6` there.
- **Renovate PR #282 (`ghcr.io/immich-app/postgres` 14 -> 16, OPEN, held) must NOT be merged
  the same night.** It is a postgres MAJOR on `immich-postgres` (pg_upgrade/dump-restore
  territory): it would invalidate this plan's §3.1 dump/§3.2 restore proof and the §5.3 restore
  path (dump taken from pg14) and break the §2.5/§4.3 baselines. Serialize: this plan first,
  #282 in its own window with its own plan. If #282 lands first, premise
  `immich-postgres-still-pg14` fails and this plan is stale (live 2026-11-06:
  `ghcr.io/immich-app/postgres:14-vectorchord0.4.3-pgvectors0.2.0@sha256:...`).
- **F-7424ba26:** see §1; disposition lives on the DB record.
- **frigate-reolink-go2rtc-flv** (shared `igpu-i915`): added to `conflicts_with`; frigate is on
  nuc14-02 today, but serialize the two so §4.2's GPU-device gate reads a quiet device plugin.
  That plan is HUMAN-GATED on enabling HTTP on the cameras, which the operator declined, so the
  collision is unlikely in practice.
- **Public route** (`envoy-external`) unchanged; users see ~1-2 min outage per leg.
- **Supersedes nothing open:** `immich-server-3.3.5` is `status: executed`; its §5 restore path
  targets a dump directory (`pre-3.3.5`) that this plan does not use.
