---
plan_id: frigate-0.18.0
component: frigate
pr: null                              # no Renovate PR — coverage.py direct-bump lane
                                      # routed this to PLAN: "0.x release-line move
                                      # (0.17 -> 0.18) — at major 0 the minor IS the
                                      # breaking axis". Sweep finding F-24463e2b.
kind: image
current: "0.17.2"                     # verified live 2026-09-15: manifest tag AND the
                                      # running pod (frigate-7db8f9dbc5-4vxvc on
                                      # k8s-nuc14-02) both read
                                      # ghcr.io/blakeblackshear/frigate:0.17.2;
                                      # /api/version = 0.17.2-3d4dd3a
target: "0.18.0"                      # GA 2026-09-12T13:17Z (not pre-release; latest).
                                      # GHCR index digest sha256:9678a83a76e4730ac7d9
                                      # ea7428370e32ae656d6b312aaad30d6c69f3fef14d35.
                                      # No non-prerelease GitHub Release newer than
                                      # v0.18.0 as of 2026-09-15 (`gh api releases`,
                                      # §2i — the GHCR tags/list is pagination-blind).
update_type: minor                    # semver-minor, but a 0.x line hop: upstream ships
                                      # a config migrator + 3 sqlite migrations with it.
risk: medium
est_duration_min: 50
needs_reboot: false
touches:
  namespaces: [home-automation]
  resources:
    - helmrelease/frigate              # image tag + temporary remediation change
    - deployment/frigate               # Recreate rollout (expect TWO restarts — §6)
    - configmap/frigate-config         # SOPS-encrypted; HAND-MIGRATED to 0.18 shape (§1)
    - pvc/frigate-config               # Longhorn RWO 8Gi; holds frigate.db — 3 one-way
                                      # sqlite migrations run on first 0.18 boot
    - pvc/frigate-media                # CIFS RWX (//NAS/frigate, subdir /media, Retain).
                                      # Snapshot FORMAT on disk changes (no new .jpg);
                                      # no PVC/PV operation of any kind in this plan.
    - cronjob/frigate-restart          # UNCHANGED and KEPT — the leak-mitigation exit
                                      # condition is NOT met by this bump (§6)
  shared: [igpu-i915]                 # ADDED 2026-09-15 (review): the SAME token
                                      # scrypted-0.147.0 and jellyfin-12.1 use — `shared`
                                      # is an INTERSECTION key. Frigate holds
                                      # gpu.intel.com/i915:1 on k8s-nuc14-02, the physical
                                      # render node (/dev/dri/renderD128) it shares with
                                      # scrypted (live holders on nuc14-02: frigate +
                                      # scrypted). Nothing else shared is restarted or
                                      # reconfigured.
                                      # Soft dependencies (not perturbed, but they
                                      # observe the restart): mosquitto (frigate/
                                      # available flips), home-assistant (frigate
                                      # integration entities go unavailable for the
                                      # rollout), intel-device-plugin NPU on nuc14-02
                                      # (1/1, exclusively frigate's), the Mac-mini
                                      # Ollama host (genai descriptions + the NEW chat
                                      # role). See §6.
depends_on: []
conflicts_with:
  - talos-1.14.0                      # reboots every node; that plan's own rule is
                                      # "no other plan may share its window"
  - multus-macvlan-foundation         # mutates Talos machine config on the node that
                                      # pins frigate (nuc14-02)
  - scrypted-0.147.0                  # ADDED 2026-09-15 (review): same node k8s-nuc14-02,
                                      # same /dev/dri/renderD128, both privileged GPU
                                      # churn — a driver wedge with both in flight cannot
                                      # be bisected. Mirrors scrypted-0.147.0's own
                                      # declaration so the guard holds whichever file the
                                      # window agent reads first.
security_ref: F-b0dcee3c              # security driver for the image bump; what it is
                                      # and why this tag answers it live on the record
                                      # only (we bump, we never rebuild).
capability_change: true               # 0.18 adds user-visible surface that our config
                                      # ENABLES by construction: the migrated genai
                                      # provider gets the new `chat` role (a tool-calling
                                      # chat UI against the household LLM), full
                                      # in-UI config editing, camera profiles, a
                                      # redesigned motion review, and annotated
                                      # snapshots move from disk files to on-demand
                                      # API rendering. Not cosmetic — say so.
rollback_class: backup-restore        # NOT plain git-revert: 0.18 runs three forward-
                                      # only peewee migrations on frigate.db at boot
                                      # (033_create_export_case_table,
                                      # 034_add_export_case_to_exports,
                                      # 035_add_motion_heatmap). They are additive, so
                                      # a revert-only attempt is TRIED FIRST (§5 tier A),
                                      # but the honest path back is the pre-upgrade DB
                                      # copy (§5 tier B).
backup_gate: "Online sqlite backup of /config/frigate.db taken INSIDE the running pod
  (sqlite3 Connection.backup(), WAL-consistent) to /config/frigate.db.pre-0.18.0 BEFORE
  the tag edit is pushed, with PRAGMA integrity_check == ok on the copy and size within
  10% of the live file (~394 MB on 2026-09-15), plus the same-night Longhorn backup of
  volume frigate-config showing lastBackupAt >= today 03:00 as the disaster fallback.
  Pre-upgrade row counts (event, recordings, reviewsegment, export) recorded for the §4
  contents comparison."
finding_refs: [F-24463e2b, F-b0dcee3c]   # NOT F-08b3aaae — that is a camera-hardware
                                          # decision, out of scope here (§6)
status: awaiting-go   # OPERATOR GO 2026-09-15 (direct, attended update in its window; recorded in home-operation, exec_state=pending). REVIEWED 2026-09-15, corrections c36388bc
window: "sun-attended:2026-10-04"   # assigned 2026-09-15 from the review synthesis (capacity-checked); go/no-go via home-operation
                                      # agent assigns
premises:
  - id: live-image-is-still-0.17.2
    why: >-
      `current:` claims 0.17.2. If the cluster already moved (hand bump, or a later
      coverage.py run), the diff, the migration snippet and the §4/§5 baselines in
      this plan are stale and must be re-derived before executing.
    run: kubectl get deploy -n home-automation frigate -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: ghcr.io/blakeblackshear/frigate:0.17.2
  - id: config-is-a-read-only-configmap-subpath-mount
    why: >-
      The WHOLE plan shape rests on this: Frigate's automatic config migrator
      refuses to run on a read-only config file (§1), which is why the ConfigMap
      is hand-migrated in git in the same commit as the tag. If someone changed
      the mount to a writable PVC file, the migrator would run on its own and the
      hand-migration + the reloader double-restart reasoning are both wrong.
    run: kubectl get deploy -n home-automation frigate -o jsonpath='{.spec.template.spec.containers[0].volumeMounts[?(@.mountPath=="/config/config.yml")].readOnly}'
    expect_exact: "true"
  - id: live-config-still-carries-the-flat-pre-0.18-genai-block
    why: >-
      §3's migration snippet asserts on exactly ONE flat `genai:` block (2-space
      `provider: openai` directly under it). If the live ConfigMap was already
      migrated (4-space, under `default:`), the snippet aborts and the ConfigMap
      step must be skipped, not repeated.
    run: >-
      kubectl get cm -n home-automation frigate-config -o jsonpath='{.data.config\.yml}'
      | grep -c -E '^  provider: openai$'
    expect_exact: "1"
  - id: node-kernel-supports-0.18-intel-gpu-stats
    why: >-
      0.18 drops intel_gpu_top and reads per-client DRM counters; upstream requires
      kernel >= 6.5 on the host. nuc14-02 runs 6.18.x under Talos v1.13.10. A
      Talos downgrade or a node swap below 6.5 would leave GPU stats blank (not
      fatal, but §4 asserts on them).
    run: kubectl get node k8s-nuc14-02 -o jsonpath='{.status.nodeInfo.kernelVersion}'
    expect_matches: '^(6\.([5-9]|[1-9][0-9])|[7-9]\.)'
  - id: restart-cronjob-still-daily-0230
    why: >-
      §6 sequences this plan against the 02:30 leak-mitigation restart and KEEPS
      that CronJob. If its schedule moved or it was suspended, the mitigation
      assumptions (container age, ContainerRestartMitigationStale) in §4 change.
    run: kubectl get cronjob -n home-automation frigate-restart -o jsonpath='{.spec.schedule}'
    expect_exact: "30 2 * * *"
  - id: frigate-config-volume-healthy
    why: >-
      The sqlite migration and the pre-upgrade DB copy both write to the Longhorn
      volume `frigate-config`. A degraded volume (rebuilding replica) is not the
      moment to run a one-way schema migration on it.
    run: kubectl get volume -n storage frigate-config -o jsonpath='{.status.robustness}'
    expect_exact: healthy
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/frigate-memory-leak.md
  - docs/sops/storage-safety.md
  - docs/sops/longhorn-rwo-multi-attach.md
generated: "2026-09-15"
---

# frigate 0.17.2 → 0.18.0

## 1) Summary & why held

**What changes:** the `image.tag` in
`kubernetes/apps/home-automation/frigate-nvr/app/helmrelease.yaml` moves from
`0.17.2` to `0.18.0`, and — in the SAME commit — the SOPS-encrypted
`configmap.sops.yaml` is hand-migrated to the 0.18 config shape. The Helm chart
(`blakeblackshear/frigate` 7.8.0, appVersion 0.14.1) is a generic Deployment
wrapper and needs no change. Nothing else in the repo consumes frigate's on-disk
files or the removed API endpoints (checked 2026-09-15: the only repo mentions
outside the app folder are comments, alert rules and the health check).

**Why held:** `coverage.py` routes any 0.x release-line move to PLAN, and the
version snapshot (2026-09-15 03:42) flagged upstream's own breaking-change list.
Read against OUR config, the list collapses to one real migration and one
structural trap:

1. **The one migration that hits us — `genai` becomes a provider mapping.**
   Upstream (v0.18.0 release notes): *"GenAI now supports multiple providers. As
   a result, the global `genai` config is now a mapping of keys to GenAI provider
   setups, and a new `roles` field defines what tasks each provider will be used
   for … Existing configs will be automatically migrated."* Our live config has
   the pre-0.18 flat block (`genai: {provider: openai, api_key, model:
   gemma4:26b-mlx}`), and 0.18's schema is `genai: dict[str, GenAIConfig]`
   (`frigate/config/config.py` line 513) with `extra="forbid"` — a flat block
   does not validate. The upstream migrator (`migrate_018_0`,
   `frigate/util/config.py` v0.18.0) does exactly this and nothing else to a
   config like ours:

   ```python
   if genai and genai.get("provider"):
       genai["roles"] = ["descriptions", "chat"]
       new_config["genai"] = {"default": genai}
   ...
   new_config["version"] = "0.18-0"
   ```

   The other 0.18 migrations (`clean_copy` removal, zones/masks → dict form with
   `enabled`/`friendly_name`, `sync_recordings`, `timelapse_args`,
   `ui.date_format`/`time_format`) are **no-ops for us** — none of those keys
   exist in our config (no zones, no masks, no `clean_copy`, no `ui:` block).

2. **The trap — "automatically migrated" does not apply to us.** Our config is
   a ConfigMap mounted `readOnly: true` via `subPath` at `/config/config.yml`.
   The migrator checks writability FIRST and returns without touching anything:

   ```python
   if not os.access(config_file, os.W_OK):
       logger.error("Config file is read-only, unable to migrate config file.")
       return
   ```

   The 0.17.2 pod logs that exact line at every boot (seen 2026-09-15 02:30:19).
   So on 0.18.0 the flat block would be validated unmigrated and rejected, and
   0.18's `__main__` then tries to start in **safe mode** — the UI comes up, the
   pod goes Ready, and **no camera runs**. Flux/Helm would call that a success.
   That is why (a) the ConfigMap is migrated by hand in git, (b) §3.3 validates
   the migrated file against the real 0.18.0 image before anything is pushed, and
   (c) §4's first assertion is per-camera FPS, never pod readiness.

3. **Snapshot storage semantics change** (release notes): *"Frigate no longer
   saves annotated JPEG snapshots (.jpg) to disk. Only a clean, unannotated WebP
   snapshot (`<camera>-<id>-clean.webp`) is now stored … The `clean_copy`
   configuration option has been removed … The `snapshots.quality` default has
   changed from 70 to 60 … Users who previously relied on the annotated `.jpg`
   files on disk should instead use the `/api/events/<id>/snapshot.jpg`
   endpoint, which now honors `timestamp`, `bounding_box`, `crop`, `height`, and
   `quality` query parameters."* On 2026-09-15 the share holds 12,442 `.jpg` and
   12,367 `-clean.webp` files; after the bump only the webp is written for new
   events, old files age out with their events. **No consumer reads those files
   from disk**: Home Assistant's frigate integration (custom component 5.15.6,
   released 2026-09-03 — already 0.18/0.19-aware per its release notes) fetches
   snapshots through the API proxy, the vacation AI script fetches
   `/api/<cam>/latest.jpg?h=720`, and the vacation/smoke automations consume
   `binary_sensor.*_person_occupancy`, `switch.*_detect|snapshots` and
   `binary_sensor.kids_fire_alarm_sound` — all MQTT/integration entities that
   0.18 keeps. Nothing in this repo mounts `//NAS/frigate` except frigate.

4. **Everything else in the breaking list is verified inapplicable:** Intel GPU
   stats now need kernel ≥ 6.5 (nuc14-02 runs 6.18.48-talos — fine; `privileged:
   true` stays, it is no longer *required* but harmless); FFmpeg 8 breaks go2rtc
   **hardware transcoding** only (`#hardware` stream sources — we have no
   `go2rtc:` section at all; `ffmpeg.hwaccel_args: preset-intel-qsv-h264` and
   both `preset-rtsp-*` input presets are still defined in
   `frigate/ffmpeg_presets.py` v0.18.0); the JinaV2-on-GPU reindex does not apply
   (we run the default JinaV1, `model_size: large`, no CUDA; `SemanticSearchConfig`
   defaults unchanged, `reindex: false` stays valid); `/api/export DELETE` removal
   and the DeGirum detector removal touch nothing we use. The `openai` provider
   still falls back to the SDK's `OPENAI_BASE_URL` env var when `base_url` is
   unset (`frigate/genai/plugins/openai.py` v0.18.0 line 55), so the HelmRelease
   env pointing at the Mac-mini Ollama `/v1` keeps working unchanged.

**Why `risk: medium`:** blast radius is one pod in one namespace with its own
sqlite DB and a write-only CIFS share; no shared infra is restarted; no reboot.
It is not `low` because the config migration is manual (a mistake means cameras
silently down behind a Ready pod), the DB migration is one-way, this is the
household's security-camera function, and the rollout is a multi-minute camera
gap. It is not `high` because rollback is a git revert plus, at worst, a
verified in-pod DB copy, and nothing outside frigate can be damaged.

**Release-age cooldown (G5, 48h):** tag published 2026-09-12T13:17Z — cleared
2026-09-14T13:17Z. Informational; this plan was never in the unattended lane.

**Memory-leak mitigation — explicitly NOT retired by this plan.** The exit
condition in `docs/sops/frigate-memory-leak.md` is *"0.18 running here with
embeddings remote"*. The migrator assigns roles `[descriptions, chat]` — the
`embeddings` role stays with the in-process JinaV1 model, so the leak's source
(`frigate.embeddings`) is still local. Keep the 02:30 CronJob, the 10Gi limit,
`MALLOC_ARENA_MAX=1` and both alerts. Measure a week of 0.18 memory (§4) and
open a separate plan if the slope is gone; remote embeddings would be a
provider/capability decision for the operator (only llama.cpp does multimodal
embeddings upstream), not a side effect of this bump.

**Security driver (cited, not described):**

> **Security driver — detail withheld from this public repo.**
> Tracked as **F-b0dcee3c**.
> Full detail (CVE IDs, counts, exposure, exploitability) lives on the
> finding record — it is deliberately not reproduced here.
>
> - Dashboard: `https://sweep.<DOMAIN>/findings/F-b0dcee3c`
> - CLI: `runbooks/policy-cli.py finding show F-b0dcee3c`
>
> See `docs/sops/vulnerability-disclosure.md` before adding any
> vulnerability detail to a committed file.

When reporting on that finding, quote the board's *contextual* tier (read it
from the board at execution time — it was not re-verified by the 2026-09-15
review), never the raw `severity` column; the raw column is not what pages.
Version-currency finding: F-24463e2b.

## 2) Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) premises (the scheduler runs these too; run them yourself first)
python3 runbooks/plan-premises.py frigate-0.18.0 --require-premises

# b) frigate healthy, HR Ready, all 5 cameras streaming — capture the BASELINE
kubectl get hr -n home-automation frigate -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion}{"\n"}'
kubectl get pods -n home-automation -l app.kubernetes.io/name=frigate -o wide
kubectl -n home-automation port-forward svc/frigate 15000:5000 >/dev/null 2>&1 &
sleep 3
curl -s http://localhost:15000/api/version                        # 0.17.2-3d4dd3a
curl -s http://localhost:15000/api/stats | python3 -c "
import sys,json; s=json.load(sys.stdin)
for c,v in s['cameras'].items(): print(c, 'fps', v['camera_fps'], 'skipped', v['skipped_fps'])
print('detector ov inference_speed', s['detectors']['ov']['inference_speed'])
print('gpu', s.get('gpu_usages'))
print('processes', list(s.get('processes',{}).keys()))" | tee /tmp/frigate-baseline-stats.txt
# expect: kids 2.0, entry ~2.0, heater 2.0, living_room ~5.0, kitchen ~5.0, all skipped 0.0;
# detector ov ~6 ms. NOTE 2026-09-15: the 'entry' camera (F-08b3aaae, "physically offline")
# was STREAMING at plan-write time (camera_fps 2.1, RTSP 554 reachable, 0 crash-restarts in
# 24h). Record whatever it does NOW; the §4 comparison is against THIS capture, and a camera
# that was down before the bump is not a regression of the bump.

# c) header-trust baseline for the Authentik proxy mapping (compare in §4 — same command)
curl -s -H 'X-Authentik-Username: planner-check' -H 'X-Authentik-Groups: viewer' \
  http://localhost:15000/api/profile | tee /tmp/frigate-baseline-profile.json; echo

# d) semantic search readable before (same query in §4)
curl -s 'http://localhost:15000/api/events/search?query=person&limit=5' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('results', len(d) if isinstance(d,list) else d)"

# e) snapshot-file baseline on the CIFS share (contents assertion #3 compares to this)
kubectl -n home-automation exec deploy/frigate -c frigate -- sh -c \
  'cd /media/frigate/clips && echo "jpg=$(ls *.jpg | wc -l) webp=$(ls *-clean.webp | wc -l) newest_webp=$(ls -t *-clean.webp | head -1)"' \
  | tee /tmp/frigate-baseline-clips.txt

# f) MANDATORY backup_gate — online, WAL-consistent copy of frigate.db INSIDE the pod
kubectl -n home-automation exec deploy/frigate -c frigate -- python3 -c "
import sqlite3
s=sqlite3.connect('/config/frigate.db'); d=sqlite3.connect('/config/frigate.db.pre-0.18.0')
s.backup(d); d.close(); s.close(); print('backup written')"
kubectl -n home-automation exec deploy/frigate -c frigate -- python3 -c "
import sqlite3,os
print('integrity', sqlite3.connect('/config/frigate.db.pre-0.18.0').execute('pragma integrity_check').fetchone()[0])
print('live', os.path.getsize('/config/frigate.db'), 'copy', os.path.getsize('/config/frigate.db.pre-0.18.0'))"
# GATE: integrity == ok AND copy size within 10% of live (~394 MB on 2026-09-15). A copy
# orders of magnitude smaller is a bad export, not a small database. Do NOT proceed otherwise.

# g) pre-upgrade row counts — the §4 CONTENTS baseline (count(*), not estimates)
kubectl -n home-automation exec deploy/frigate -c frigate -- python3 -c "
import sqlite3; c=sqlite3.connect('/config/frigate.db')
for t in ('event','recordings','reviewsegment','export'):
    print(t, c.execute(f'select count(*) from {t}').fetchone()[0])
print('migrations', c.execute('select count(*) from migratehistory').fetchone()[0])" \
  | tee /tmp/frigate-baseline-rows.txt

# h) Longhorn disaster fallback is fresh (the 03:00 job must have finished for this volume)
kubectl get volume -n storage frigate-config \
  -o custom-columns=NAME:.metadata.name,LAST_BACKUP:.status.lastBackupAt,ROBUST:.status.robustness --no-headers
# expect lastBackupAt on TODAY's date (>= 03:00 local). lastBackupAt can lag one cycle —
# cross-check the newest Completed Backup CR per docs/sops/backup.md if it looks stale.

# i) target tag still resolves and nothing newer appeared (re-verify at execution time)
TOKEN=$(curl -s "https://ghcr.io/token?scope=repository:blakeblackshear/frigate:pull&service=ghcr.io" | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
curl -sI -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.oci.image.index.v1+json" \
  https://ghcr.io/v2/blakeblackshear/frigate/manifests/0.18.0 | grep -i -E 'HTTP/|docker-content-digest'
# expect 200 + sha256:9678a83a76e4730ac7d9ea7428370e32ae656d6b312aaad30d6c69f3fef14d35
gh api repos/blakeblackshear/frigate/releases --jq '.[0:5][] | "\(.tag_name) pre=\(.prerelease) draft=\(.draft) \(.published_at)"'
# expect: the newest line with pre=false draft=false is v0.18.0. A newer non-prerelease
#   (0.18.1, 0.19.0, ...) means re-plan the target, not silently take it.
# Do NOT use `ghcr.io/v2/.../tags/list` for this check: it is pagination-blind — on
#   2026-09-15 it returned [] for 0.18.* although 0.18.0 resolves above, so it could not
#   see a newer 0.18.x either.

# j) HA side: integration version + no in-flight flux work
kubectl -n home-automation exec deploy/home-assistant -c app -- python3 -c \
  "import json; print(json.load(open('/config/custom_components/frigate/manifest.json'))['version'])"   # >= 5.15.6
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
```

## 3) Steps

1. **Marker + silence** (attended-tier update per `application-update.md` §4):
   ```bash
   runbooks/update-marker.sh add frigate home-automation 4 "0.17.2 -> 0.18.0 (plan frigate-0.18.0)"
   ```
   Silence `Kube(Pod|Deployment).*` for `namespace=home-automation` + the
   `ContainerRestartMitigationStale` / `ContainerMemoryBudgetExceeded` pair for
   4h using the SOP's curl (they will not fire, but the rollout resets the
   container age those rules read).

2. **Hand-migrate the ConfigMap to the 0.18 shape** (decrypt → transform →
   encrypt in the repo path, per CLAUDE.md SOPS rules). The transform mirrors
   `migrate_018_0` exactly and ABORTS unless it finds exactly one flat block:
   ```bash
   F=kubernetes/apps/home-automation/frigate-nvr/app/configmap.sops.yaml
   sops -d "$F" > /tmp/frigate-cm.yaml
   python3 - /tmp/frigate-cm.yaml <<'PY'
   import re, sys, pathlib
   p = pathlib.Path(sys.argv[1]); s = p.read_text()
   flat = re.compile(r'^    genai:\n      provider: openai\n      api_key: (.*)\n      model: (.*)\n', re.M)
   assert len(flat.findall(s)) == 1, "expected exactly ONE flat genai block — already migrated? STOP"
   assert not re.search(r'^    version:', s, re.M), "config already carries a version: key — STOP"
   s = flat.sub(lambda m: (
       "    genai:\n"
       "      default:\n"
       "        provider: openai\n"
       f"        api_key: {m.group(1)}\n"
       f"        model: {m.group(2)}\n"
       "        roles:\n"
       "          - descriptions\n"
       "          - chat\n"), s)
   assert s.count("  config.yml: |\n") == 1
   s = s.replace("  config.yml: |\n", "  config.yml: |\n    version: 0.18-0\n", 1)
   p.write_text(s); print("migrated: genai -> genai.default{roles:[descriptions,chat]}, version: 0.18-0")
   PY
   # sanity: the inner config still parses and has the expected shape (no secrets printed)
   python3 -c "
   import yaml,sys; d=yaml.safe_load(open('/tmp/frigate-cm.yaml')); c=yaml.safe_load(d['data']['config.yml'])
   print('version', c['version'], '| genai keys', list(c['genai']), '| roles', c['genai']['default']['roles'], '| provider', c['genai']['default']['provider'])
   print('cameras', list(c['cameras']), '| semantic_search', c['semantic_search'])"
   # expect: version 0.18-0 | genai keys ['default'] | roles ['descriptions','chat'] | provider openai
   #         cameras [kids, entry, heater, living_room, kitchen] | semantic_search unchanged
   ```
   Do NOT re-encrypt yet — step 3 validates this file first.

3. **Validate the migrated config against the REAL 0.18.0 image before pushing
   anything** — and pre-pull the image on nuc14-02 in the same move. Ephemeral,
   namespaced, deleted in the same step (cberg-agent runs this; no Flux-owned
   object is touched):
   ```bash
   python3 -c "
   import yaml; d=yaml.safe_load(open('/tmp/frigate-cm.yaml')); open('/tmp/frigate-candidate.yml','w').write(d['data']['config.yml'])"
   kubectl -n home-automation create configmap frigate-config-candidate --from-file=config.yml=/tmp/frigate-candidate.yml
   cat <<'EOF' | kubectl -n home-automation apply -f -
   apiVersion: v1
   kind: Pod
   metadata: { name: frigate-config-validate }
   spec:
     restartPolicy: Never
     nodeSelector: { kubernetes.io/hostname: k8s-nuc14-02 }   # pre-pulls 0.18.0 where frigate runs
     containers:
       - name: validate
         image: ghcr.io/blakeblackshear/frigate:0.18.0
         command: ["python3", "-u", "-m", "frigate", "--validate-config"]
         env: [{ name: OPENAI_BASE_URL, value: "http://192.168.30.111:11434/v1" }]
         volumeMounts:
           - { name: config, mountPath: /config }
           - { name: candidate, mountPath: /config/config.yml, subPath: config.yml, readOnly: true }
         resources: { requests: { cpu: 200m, memory: 512Mi }, limits: { memory: 2Gi } }
     volumes:
       - { name: config, emptyDir: {} }
       - { name: candidate, configMap: { name: frigate-config-candidate } }
   EOF
   kubectl -n home-automation wait pod/frigate-config-validate --for=jsonpath='{.status.phase}'=Succeeded --timeout=10m \
     || kubectl -n home-automation logs frigate-config-validate | tail -40
   kubectl -n home-automation logs frigate-config-validate | grep -iE 'valid|safe mode'
   PHASE=$(kubectl -n home-automation get pod frigate-config-validate -o jsonpath='{.status.phase}')
   BAD=$(kubectl -n home-automation logs frigate-config-validate | grep -ciE 'not valid|validation error|safe mode')
   echo "phase=$PHASE bad_lines=$BAD"
   # GATE — BOTH must hold, not either: phase == Succeeded (exit 0) AND bad_lines == 0.
   # The "*** Your config file is valid." banner and exit 0 are NOT a verdict on their own.
   # At v0.18.0 `frigate/__main__.py` handles `--validate-config` AFTER its
   # `except ValidationError` block: on a failed validation it prints the errors ("Your
   # config file is not valid!" / "Config Validation Errors"), re-loads the config with
   # safe_load=True — which DROPS `genai` entirely — prints "Starting Frigate in safe
   # mode.", and then still falls through to the "valid" banner and sys.exit(0). So a
   # broken genai block, the exact mistake this step exists to catch, yields phase
   # Succeeded + the banner. Any "not valid" / "Validation Error" / "safe mode" line is a
   # FAIL regardless of the trailing banner and exit code: fix the candidate and re-run;
   # do NOT push. (A failure that is clearly not about the config — e.g. a model download —
   # is read, not treated as a config verdict.)
   kubectl -n home-automation delete pod frigate-config-validate configmap frigate-config-candidate
   ```
   Then encrypt in place (repo path, never from /tmp):
   ```bash
   cp /tmp/frigate-cm.yaml kubernetes/apps/home-automation/frigate-nvr/app/configmap-new.sops.yaml
   sops -e -i kubernetes/apps/home-automation/frigate-nvr/app/configmap-new.sops.yaml
   mv kubernetes/apps/home-automation/frigate-nvr/app/configmap-new.sops.yaml "$F"
   rm -f /tmp/frigate-cm.yaml /tmp/frigate-candidate.yml
   head -20 "$F" | grep -q 'sops:' || echo "NOT ENCRYPTED — STOP"
   sops -d "$F" | grep -c -E '^        roles:$'     # expect 1
   ```

4. **Disable HR rollback for the attempt** — a Helm rollback here is strictly
   harmful: it would restore the 0.17.2 image against the already-migrated
   ConfigMap (kustomize-owned, not Helm-owned) on an already-migrated DB. In
   `kubernetes/apps/home-automation/frigate-nvr/app/helmrelease.yaml`:
   ```yaml
     upgrade:
       cleanupOnFail: true
       remediation:
         retries: 0
         remediateLastFailure: false   # TEMP for plan frigate-0.18.0 — restore retries: 1 after §4
   ```

5. **Bump the image tag** in the same file:
   ```yaml
       image:
         repository: ghcr.io/blakeblackshear/frigate
         tag: 0.18.0
   ```
   Also update the stale comment block in `restart-cronjob.yaml`
   ("0.18 is beta only") — a comment-only edit, in the same commit, so the
   mitigation file does not lie about why it still exists (it stays because
   embeddings are still local, §1).

6. **Commit + push — ONE commit, hunk-scoped (shared worktree, per CLAUDE.md)**.
   The tag and the migrated ConfigMap must land together: 0.17.2 rejects the
   0.18 shape (`extra="forbid"`) and 0.18.0 rejects the flat shape, so a split
   commit guarantees a safe-mode boot in between.
   ```bash
   git fetch origin main && git merge --ff-only origin/main
   git commit --only \
     kubernetes/apps/home-automation/frigate-nvr/app/helmrelease.yaml \
     kubernetes/apps/home-automation/frigate-nvr/app/configmap.sops.yaml \
     kubernetes/apps/home-automation/frigate-nvr/app/restart-cronjob.yaml \
     -m "feat(frigate): 0.17.2 -> 0.18.0 + hand-migrated genai config (plan frigate-0.18.0)"
   git show --stat HEAD      # exactly these three files
   git push origin main
   ```

7. **Watch the rollout — expect TWO Recreate restarts** (§6: reloader reacts to
   the ConfigMap, Helm to the pod template; order is a race, outcome is the
   same). Judge nothing before **t+8 min after the LAST pod creation** — cameras
   re-negotiate RTSP at different rates after any restart
   (`frigate-memory-leak.md` §6).
   ```bash
   kubectl get pods -n home-automation -l app.kubernetes.io/name=frigate -w   # Ctrl-C when the 0.18.0 pod is Running
   kubectl -n home-automation logs deploy/frigate -f | grep -iE 'migrat|not valid|validation error|safe mode|peewee|Starting|frigate.genai|ERROR'
   # expect ON THE FINAL 0.18.0 POD: "Config file is read-only, unable to migrate config
   #   file." (still true, harmless — the file already IS 0.18-0), then peewee_migrate
   #   applying 033/034/035, and ZERO "not valid" / "Validation Error" / "safe mode" lines.
   #   A "safe mode" line from the FIRST pod of the pair (0.17.2 booting on the already-
   #   migrated ConfigMap — the reloader-first race, §6) is expected and is NOT the §4
   #   failure signature; `kubectl logs deploy/frigate` follows the current pod, so once the
   #   0.18.0 pod is up you are reading the right log.
   ```
   The HR may report a transient timeout if pull+boot exceeds Helm's 5m wait; with
   `retries: 0` nothing is rolled back and the next interval marks it Ready.

8. **On success (after §4):** restore `retries: 1`, remove `remediateLastFailure`,
   commit + push, clear the marker, delete the silence.
   ```bash
   git commit --only kubernetes/apps/home-automation/frigate-nvr/app/helmrelease.yaml \
     -m "chore(frigate): restore HR remediation retries after 0.18.0 bump"
   git push origin main
   runbooks/update-marker.sh clear frigate
   ```
   Leave `/config/frigate.db.pre-0.18.0` in place until the next nightly Longhorn
   backup after sign-off, then delete it in-pod (`rm /config/frigate.db.pre-0.18.0`).

## 4) Verification

```bash
kubectl -n home-automation port-forward svc/frigate 15000:5000 >/dev/null 2>&1 &
sleep 3

# floor: HR Ready, pod on 0.18.0, 0 restarts after settle, version endpoint
kubectl get hr -n home-automation frigate -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'
kubectl get pods -n home-automation -l app.kubernetes.io/name=frigate \
  -o jsonpath='{.items[0].spec.containers[0].image} restarts={.items[0].status.containerStatuses[0].restartCount} node={.items[0].spec.nodeName}{"\n"}'
curl -s http://localhost:15000/api/version                     # 0.18.0-<sha>

# CONTENTS ASSERTION 1: the hand-migrated config is LIVE and cameras RUN (not safe mode) —
# measured by /api/stats per-camera FPS + /api/config genai shape, compared to the §2b baseline.
# A Ready pod in safe mode passes every shape check and fails this one.
curl -s http://localhost:15000/api/stats | python3 -c "
import sys,json; s=json.load(sys.stdin)
cams=s['cameras']; assert len(cams)==5, cams.keys()
for c,v in cams.items(): print(c, 'fps', v['camera_fps'], 'skipped', v['skipped_fps'])
print('detector ov inference_speed', s['detectors']['ov']['inference_speed'])
print('gpu', s.get('gpu_usages'))
print('processes', list(s.get('processes',{}).keys()))"
# expect: every camera that streamed in §2b streams now (fps within ±0.5 of baseline, skipped 0.0);
#   detector inference speed within ~2x of baseline (NPU still used — a 10x jump means CPU fallback);
#   gpu_usages present (new DRM-counter path, values may differ — presence is the check);
#   'embeddings' still in processes (local JinaV1, as designed — see §1 mitigation note).
curl -s http://localhost:15000/api/config | python3 -c "
import sys,json; c=json.load(sys.stdin)
g=c['genai']; assert list(g)==['default'], list(g)
print('provider', g['default']['provider'], 'model', g['default']['model'], 'roles', g['default']['roles'])
print('version', c.get('version'))
for cam in ('entry','heater','kitchen'): print(cam, 'objects.genai.enabled', c['cameras'][cam]['objects']['genai']['enabled'])"
# expect provider openai, model gemma4:26b-mlx, roles [descriptions, chat], version 0.18-0,
#   entry/heater/kitchen genai enabled True (kids/living_room False, as before)
kubectl -n home-automation logs deploy/frigate | grep -ciE 'not valid|validation error|safe mode'   # 0 (the FINAL 0.18.0 pod's log; upstream prints "not valid!" / "Config Validation Errors" / "Starting Frigate in safe mode.")

# CONTENTS ASSERTION 2 (data migration class): row counts on frigate.db >= the §2g baseline,
# measured with the same count(*), and the three 0.18 migrations recorded.
kubectl -n home-automation exec deploy/frigate -c frigate -- python3 -c "
import sqlite3; c=sqlite3.connect('/config/frigate.db')
for t in ('event','recordings','reviewsegment','export'):
    print(t, c.execute(f'select count(*) from {t}').fetchone()[0])
print('migrations', c.execute('select count(*) from migratehistory').fetchone()[0])
print([r[0] for r in c.execute('select name from migratehistory order by id desc limit 3')])"
# expect: each count >= /tmp/frigate-baseline-rows.txt (event/reviewsegment may be higher —
#   new events since); migrations == baseline + 3; newest names 033_..., 034_..., 035_add_motion_heatmap

# CONTENTS ASSERTION 3 (the snapshot path HA notifications use): the API renders an annotated
# JPEG on demand for the newest event, and new events write ONLY -clean.webp on the share.
EID=$(curl -s 'http://localhost:15000/api/events?limit=1&has_snapshot=1' | python3 -c "import sys,json;print(json.load(sys.stdin)[0]['id'])")
curl -s -o /tmp/snap.jpg -w 'http=%{http_code} bytes=%{size_download}\n' "http://localhost:15000/api/events/$EID/snapshot.jpg?bounding_box=1&timestamp=1"
python3 -c "b=open('/tmp/snap.jpg','rb').read(4); print('jpeg-magic', b[:2]==b'\xff\xd8')"
# expect http=200, bytes > 10000, jpeg-magic True
kubectl -n home-automation exec deploy/frigate -c frigate -- sh -c \
  'cd /media/frigate/clips && echo "jpg=$(ls *.jpg | wc -l) webp=$(ls *-clean.webp | wc -l) newest_webp=$(ls -t *-clean.webp | head -1)"'
# expect vs /tmp/frigate-baseline-clips.txt: webp count >= baseline AND (after >=1 new tracked
#   object) newest_webp has changed — the FLOOR; jpg count <= baseline — the ceiling. Both.
#   If no object has been tracked yet, walk past the kitchen camera and re-run — do not
#   accept "no new files" as proof of anything.

# CONTENTS ASSERTION 4: the migrated genai provider still reaches the household LLM.
# Regenerate a description for a recent event on a genai-enabled camera (an app-level
# action, not a cluster mutation) and assert a non-empty description comes back.
EID=$(curl -s 'http://localhost:15000/api/events?cameras=kitchen,heater,entry&limit=1&has_snapshot=1' | python3 -c "import sys,json;print(json.load(sys.stdin)[0]['id'])")
curl -s -X PUT "http://localhost:15000/api/events/$EID/description/regenerate?source=snapshot"; echo
sleep 45
curl -s "http://localhost:15000/api/events/$EID" | python3 -c "import sys,json; d=json.load(sys.stdin); print('description_len', len((d.get('data') or {}).get('description') or ''))"
# expect description_len > 0 and no 'frigate.genai' ERROR lines in the pod log since the rollout

# proxy header-trust behaviour is IDENTICAL to the §2c baseline (whatever it was)
curl -s -H 'X-Authentik-Username: planner-check' -H 'X-Authentik-Groups: viewer' http://localhost:15000/api/profile \
  | diff - /tmp/frigate-baseline-profile.json && echo "profile behaviour unchanged"

# semantic search still readable on the untouched JinaV1 index (same query as §2d)
curl -s 'http://localhost:15000/api/events/search?query=person&limit=5' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('results', len(d) if isinstance(d,list) else d)"   # >= 1

# MQTT + Home Assistant consumers
kubectl exec -n home-automation deployment/mosquitto -c app -- timeout 5 mosquitto_sub -t 'frigate/available' -C 1   # online
# via ha-agent: binary_sensor.{kitchen,living_room,heater,kids,entry}_person_occupancy and
# switch.{kitchen,...}_detect are 'on'/'off' — NOT 'unavailable' — 5 min after the rollout.

# external path through envoy-internal + Authentik (302 to the outpost or 200, never 5xx)
curl -sk -o /dev/null -w '%{http_code}\n' "https://frigate.${SECRET_DOMAIN}/"

# alerts: nothing new firing (ignore Watchdog/InfoInhibitor)
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 >/dev/null 2>&1 &
sleep 2; curl -s http://localhost:9090/api/v1/alerts | grep -o '"alertname":"[^"]*"' | grep -vE 'Watchdog|InfoInhibitor' | sort -u

# memory: record the 0.18 baseline for the leak question (compare over the next 7 days;
# the 02:30 restart keeps running regardless)
kubectl -n home-automation top pod -l app.kubernetes.io/name=frigate

# OPERATOR (attended): open the UI, confirm live view on all cameras, open Explore and
# confirm a semantic search returns results, open Settings and confirm the config editor
# shows the genai.default block. This is the acceptance gate for capability_change: true.
```

## 5) Rollback

**Tier A — revert only (try first).** The three 0.18 DB migrations are
additive (new `export_case` table, a column on `export`, a motion-heatmap
table), and peewee-migrate ignores history rows for files it does not ship, so
0.17.2 is expected to boot on the migrated DB. The revert restores the tag,
the flat `genai:` block and `retries: 1` in one move because they share one
commit:

```bash
git fetch origin main && git merge --ff-only origin/main
git revert <bump-commit-sha> --no-edit && git push origin main
kubectl get pods -n home-automation -l app.kubernetes.io/name=frigate -w     # expect two Recreates again
# then re-run §2b's stats capture: all cameras streaming on 0.17.2-3d4dd3a, and
# `grep -ciE 'not valid|validation error|safe mode'` == 0 on the final 0.17.2 pod's log
```

Known cosmetic residue of tier A: tracked objects created while 0.18 ran have
only a `-clean.webp` on disk, so 0.17.2's `/api/events/<id>/snapshot.jpg`
returns 404 for THOSE events until they age out. Nothing else is lost.

**Tier B — revert + restore the pre-upgrade DB** (only if 0.17.2 fails to boot
on the migrated DB, or §4 assertion 2 showed data loss):

```bash
# 1) fence — nothing may hold the RWO volume while the file is swapped
kubectl -n home-automation scale deploy/frigate --replicas=0
kubectl -n home-automation wait --for=delete pod -l app.kubernetes.io/name=frigate --timeout=5m

# 2) swap the DB from a throwaway pod on the SAME node (Longhorn RWO attaches there)
cat <<'EOF' | kubectl -n home-automation apply -f -
apiVersion: v1
kind: Pod
metadata: { name: frigate-db-restore }
spec:
  restartPolicy: Never
  nodeSelector: { kubernetes.io/hostname: k8s-nuc14-02 }
  containers:
    - name: sh
      image: docker.io/library/busybox:1.37
      command: ["sh","-c","sleep 3600"]
      volumeMounts: [{ name: config, mountPath: /config }]
  volumes:
    - name: config
      persistentVolumeClaim: { claimName: frigate-config }
EOF
kubectl -n home-automation wait pod/frigate-db-restore --for=condition=Ready --timeout=5m
kubectl -n home-automation exec frigate-db-restore -- sh -c '
  cd /config && ls -la frigate.db* &&
  mv frigate.db frigate.db.post-0.18.0-failed && rm -f frigate.db-wal frigate.db-shm &&
  cp frigate.db.pre-0.18.0 frigate.db && ls -la frigate.db*'
kubectl -n home-automation delete pod frigate-db-restore

# 3) bring 0.17.2 back (the git revert from tier A must already be pushed)
kubectl -n home-automation scale deploy/frigate --replicas=1
kubectl get pods -n home-automation -l app.kubernetes.io/name=frigate -w
# then §2b's stats capture + §2g's row counts == the pre-upgrade baseline
```

The `scale` commands are the one sanctioned direct-cluster action (fencing the
restore); Flux's desired state is restored by the git revert itself. The
`frigate-config` Longhorn backup from that morning's 03:00 run is the disaster
fallback if the in-pod copy itself is bad — restoring it is a Longhorn
volume-restore per `docs/sops/backup.md` / `docs/sops/longhorn.md`, and it also
rewinds the config directory to 03:00.

**Never touch `pvc/frigate-media` or its PV in any rollback.** It is a CIFS
class (`cifs-frigate-media`, `subdir: /media`, Retain — "severe" tier in
`docs/sops/storage-safety.md`); this plan needs no PVC operation and none is
authorised.

## 6) Interference notes

- **Expect two Recreate restarts, not one — and the FIRST is most likely a
  transient 0.17.2 SAFE-MODE boot.** The Deployment carries
  `reloader.stakater.com/auto: "true"` and the ConfigMap changes in the same
  commit as the pod template. The race is not a coin flip: kustomize-controller
  applies the ConfigMap and the HelmRelease together, reloader patches the
  Deployment within seconds, and helm-controller upgrades later — so the first
  Recreate is usually **0.17.2 booting on the already-migrated ConfigMap**.
  0.17.2 rejects the 0.18 `genai` shape (`extra="forbid"`), so that pod starts
  in safe mode (mqtt disabled, `frigate/available` offline, HA entities
  `unavailable`) until Helm swaps the image and the second Recreate boots
  0.18.0 on the same ConfigMap. Harmless: safe mode writes nothing back to the
  DB and runs no migration. But a `Starting Frigate in safe mode.` /
  `not valid` line from that FIRST pod is **not** the §4 failure signature —
  §4 reads only the final 0.18.0 pod's log, which must carry zero such lines.
  `strategy: Recreate` + RWO PVC means the old pod is gone before the new one
  is scheduled — each restart is a ~60-90 s camera gap, plus image pull time on
  the first one if §3.3's pre-pull was skipped. Total expected camera outage:
  3-6 min. Judge health only at t+8 min after the last pod creation.
- **A wrong config fails SILENTLY-GREEN.** 0.18's `__main__` starts safe mode
  on a validation error: pod Ready, UI up, `/api/version` answers, Helm
  succeeds — and zero cameras run. Only §4 assertion 1 catches it. The window
  agent must not close on Flux Ready.
- **Timing vs the 02:30 leak-mitigation restart.** This plan is HUMAN-GATED
  and recommends a Sunday 09:00 slot, so the 02:30 restart ran ~6.5 h earlier
  and this plan restarts the pod again. Harmless —
  `ContainerRestartMitigationStale` measures age < 30h.
  The CronJob is KEPT (embeddings remain local, §1). If, after 7 days on 0.18,
  the working-set slope is flat, retire the mitigation in its own plan per the
  exit condition in `docs/sops/frigate-memory-leak.md` — never as a side
  effect here.
- **Timing vs the 03:00 Longhorn backup.** §2h requires the `frigate-config`
  backup to have COMPLETED before the push; the `daily-backup-all-volumes`
  CronJob (ns `storage`, owned by the Longhorn RecurringJob of the same name;
  `backup-of-all-volumes` does not exist) walks ~93 volumes — long finished by
  a 09:00 Sunday slot, but verify `lastBackupAt >= today 03:00` rather than
  assuming.
- **Execution class.** `capability_change: true` + `rollback_class:
  backup-restore` derive an attended class under `runbooks/autonomy-policy.yaml`
  — this must NOT run in the unattended `nightly` window. **Recommended slot
  (not assigned — `window: null`): `sun-attended:2026-09-20`** — currently
  `absenty-drop-npm-runtime` (low, 60 min); adding this plan (medium, 50 min)
  gives risk-load 3 / 110 min against capacity 6 / 200 min.
  `sat-attended:2026-09-19` already holds 45 min of a 90-min window; 45+50
  overshoots it. `sun-attended:2026-09-27` is talos-1.14.0 — excluded by
  `conflicts_with`. The window agent decides.
- **Intel NPU is exclusive.** nuc14-02 advertises `npu.intel.com/accel: 1`,
  fully claimed by frigate. Between pod delete and re-create nothing else
  requests it today; if a future workload does, frigate goes `Pending` on
  the NPU, not on the image. `gpu.intel.com/i915` is 2/5 used on that node
  (frigate + scrypted).
- **scrypted is the other i915 consumer on k8s-nuc14-02** (added 2026-09-15,
  review): `deployment/scrypted` — privileged, `SYS_ADMIN` — holds
  `gpu.intel.com/i915:1` on the same node and re-probes the same
  `/dev/dri/renderD128` on every restart. `conflicts_with: [scrypted-0.147.0]`
  and `shared: [igpu-i915]` mirror that plan's own declaration; never co-slot
  the two (a driver wedge with both in flight cannot be attributed).
  `jellyfin-12.1` declares the same `igpu-i915` token but runs on nuc14-03 —
  a scheduler INTERFERENCE warning, not a hardware conflict; still prefer
  separate slots so the window's warnings stay clean.
- **Home Assistant is a consumer, not a participant.** Integration 5.15.6
  reconnects on MQTT availability; `binary_sensor.*_person_occupancy` and
  `switch.*_detect|snapshots` go `unavailable` during each restart and
  recover with it. The vacation alarm triggers on `to: on`, so the
  unavailable→off transitions cannot false-alarm. If `input_boolean.vacation_mode`
  is on during the window, expect the AI second-opinion script to fail once
  (`/api/<cam>/latest.jpg` unreachable mid-restart) — benign.
- **The household LLM gets a new caller.** The migrated provider carries the
  `chat` role; 0.18's chat UI will send tool-calling requests to the Mac-mini
  Ollama (`gemma4:26b-mlx`) when a user opens it. User-initiated only; if the
  operator does not want that, drop `chat` from `roles` in a follow-up commit
  (the migrator's default is both — this plan matches upstream deliberately).
  Ollama-side capacity is `ollama-agent` territory; nothing there changes.
- **F-08b3aaae (entry camera) is out of scope and, on 2026-09-15, factually
  stale**: the camera streamed at 2.1 fps with RTSP reachable and no
  crash-restarts in 24h. Disabling it in config is an operator DECISION
  (log-volume containment vs. losing front-door coverage), not a window
  action, and this plan neither depends on it nor touches it. Re-run §2b at
  execution time and compare like with like.
- **Docs follow-up (doc-agent, not this window):** `docs/sops/frigate-memory-leak.md`
  §12 and `restart-cronjob.yaml` say "0.18 is beta only" — 0.18.0 is GA since
  2026-09-12. The CronJob comment is corrected in this plan's commit; the SOP
  version-history line is a doc-agent edit.
