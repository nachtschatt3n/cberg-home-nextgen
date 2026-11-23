---
plan_id: immich-server-3.4.1
component: immich-server
pr: 531                               # Renovate "update ghcr.io/immich-app/immich-server ( v3.3.6 -> v3.4.2 )", OPEN 2026-11-19. Since the ML
                                      # tag went live at v3.4.1-openvino the PR moves the SERVER tag only. Still do NOT merge it: this plan
                                      # lands the tag as its own commit WITH the retries 3 -> 0 guard (see §6). Retargeted 2026-11-19 from
                                      # v3.4.1 (plan_id kept: the go/no-go issue and the security finding key on it).
kind: image
current: "v3.3.6"                     # live 2026-11-13: deploy/immich-server ghcr.io/immich-app/immich-server:v3.3.6, pod imageID
                                      # @sha256:e1981983b1c13f6024b57d72e7ecae3342eed1581201ab09fb248932d86c593a (== ghcr index
                                      # digest of v3.3.6, HEAD 2026-11-13), node k8s-nuc14-01.
target: "v3.4.2"                      # ghcr index digest sha256:fc880c1bf665b4aab1e74c15e56ab871225989cd546536e6b77e771869af06bd
                                      # (HEAD manifests/v3.4.2, 2026-11-19). v3.4.2 published 2026-11-18T20:14Z, GitHub `Latest`, not a
                                      # prerelease/draft. (Previous target v3.4.1 = sha256:7c489add..., 2026-11-11.)
update_type: minor
risk: medium                          # three forward-only schema migrations on the only copy of the immich DB (an older server refuses
                                      # the newer schema, proven here 2026-10-12, a844cf8d) + a FEATURE minor two days old on a publicly
                                      # routed app whose OIDC login path changed. The forward step itself is small and additive.
est_duration_min: 60                  # pre-checks 5 + dump 2 (20 s in-pod on 2026-10-22) + copy-off checks 2 + scratch restore-proof
                                      # <=20 (cap; duration never recorded by the two earlier runs) + push/Flux/pull/Recreate/migrate ~8
                                      # + verification incl. a real OIDC login ~15 + retries-restore commit 3 + slack 5.
needs_reboot: false
touches:
  namespaces: [media]
  resources:
    - helmrelease/immich-server               # the edit (kubernetes/apps/media/immich/app/helmrelease.yaml: main tag + upgrade retries)
    - deployment/immich-server                # strategy Recreate (live): one pod replaced, ~1-2 min API/web outage
    - service/immich-server                   # unchanged; endpoints move to the new pod
    - httproute/immich-server                 # NOT edited; §4.8/§4.9 read the app through it
    - deployment/immich-postgres              # NOT restarted; database `immich` gets 3 forward migrations, and a scratch database
                                              # `immich_restoretest` is created + dropped (restore proof)
    - pvc/immich-pg-data                      # longhorn 20Gi (3.5G used, 17G free 2026-11-13); scratch DB ~1.3G transient
    - pvc/immich-data                         # CIFS cifs-immich-cache (SEVERE tier): READ only by this plan (nightly dumps under
                                              # /data/backups). The new server may create dirs under /data on its own (see §1).
    - pvc/immich-library                      # CIFS cifs-immich-icloud-backup (SEVERE tier), mounted ro: read by §4.10 only
  shared: [igpu-i915, monitoring, gateway/envoy-external, authentik]
                                              # i915: the pod requests+limits gpu.intel.com/i915: 1 on k8s-nuc14-01; Recreate frees then
                                              # re-claims the slot. monitoring: §4 reads Prometheus. envoy-external + authentik: §4.8/§4.9
                                              # read the app through the public Gateway and perform a real OIDC login (nothing is changed there).
depends_on: []                        # The ML half is already live (deploy/immich-machine-learning = v3.4.1-openvino, 2026-11-19) and has
                                      # no plan file any more; the two halves are not technically coupled (measured, §1 "ML compatibility").
conflicts_with:
  # 2026-11-19 retarget: removed talos-linux-1.14.5 and icloud-drive-fleet-2.3.0 (both status superseded, no longer schedulable);
  # all other entries re-checked against the plan set and still present (statuses: vetted/draft/awaiting-go). No nextcloud entry.
  - redis-fleet-8.10.3                # rolls media/immich-redis (BullMQ store) AND restarts immich-server; its gates and ours would
                                      # each read the other's Recreate/queue drop as their own.
  - helm-drift-detection              # rolls the intel-gpu-plugin DaemonSet (i915 re-register under our new pod) and changes how
                                      # helm-controller applies this HR while we rely on upgrade.remediation.retries: 0.
  - flux-oci-chart-sources            # may move the app-template chart source under this HR mid-window.
  - talos-linux-1.14.6                # node roll (exclusive, supersedes 1.14.5): reboots nuc14-01 (server) and nuc14-03 (immich-postgres).
  - talos-power-tuning-ab             # changes the nuc14 thermal/power envelope; immich-server's cpu:4 cap is a thermal bound.
  - longhorn-1.13.0                   # storage engine bump (exclusive) under immich-pg-data while we dump/restore/migrate it.
  - frigate-reolink-go2rtc-flv        # shared igpu-i915; its Recreate can land on nuc14-01 and contend for a slot under §4.10.
  - kube-prometheus-stack-93.3.0     # draft, exclusive, window null: restarts Prometheus, which this plan's gates read (retargeted 2026-11-16 from retired 92.22.0)
  - envoy-gateway-1.10.0              # §4.8/§4.9 read through envoy-external; a data-plane roll would be read as our failure.
  - coredns-1.50.5                    # vetted (chart 1.50.7): RollingUpdate of both CoreDNS pods. immich-server resolves
                                      # immich-postgres / immich-redis by name at start (and the busybox init containers do too);
                                      # with upgrade.remediation.retries 0 a DNS blip mid-migration fails the HR and lands us in §5.
                                      # coredns-1.50.5 does NOT list this plan back (§6).
  - n8n-2.47.7                        # draft, backup-restore: rollback-class stacking (house rule 81fdd797) - two forward-only
                                      # plans in one slot leave no rollback capacity for either. n8n-2.47.7 already lists this plan.
exclusive: false
security_ref: F-9f05768d           # critical sweep finding for this image; vulnerability detail is DB-only (policy-cli.py finding show
                                      # F-9f05768d), deliberately not reproduced in this public file.
capability_change: true               # A feature minor, declared from what the change does: new HTTP routes (controller `passkeys`,
                                      # two of them public; `/.well-known/webauthn`; an admin-only backups API), new workflow
                                      # trigger/filters, JPEG XL as a transcode target, a stricter CSP, and one REMOVED API field
                                      # (`password` on PUT/PATCH /users/me, upstream #32623 "Breaking API change"). Passkeys and the
                                      # backups feature both default OFF (measured in source, §1) - §4.5 asserts they stay off.
rollback_class: backup-restore        # forward-only for Immich: server/src/repositories/database.repository.ts (same guard at v3.3.6
                                      # and v3.4.1) throws 'Migration "<name>" was already applied to this database but is not in this
                                      # version of Immich ... Downgrades are not supported.' when kysely reports a previously executed
                                      # migration as missing. v3.3.6 on a DB holding the 3 new kysely_migrations rows cannot start.
backup_gate: "§3.1 fresh plain-SQL pg_dump of database immich taken from deploy/immich-postgres AFTER the pre-checks and BEFORE the tag edit is pushed, streamed to $HOME/immich-backups/pre-3.4.2/immich.sql.gz on the Mac under set -o pipefail. PASS = gzip -t ok AND size >= 300000000 bytes (Immich's own gzip of the same DB is ~414 MB (413,952,373 B on 2026-11-13); the 2026-10-22 gzip -1 dump was 458,994,958 B) AND the stream ends with '-- PostgreSQL database dump complete' AND the 'COPY public.' block count equals the live public BASE TABLE count (72 on 2026-11-13) AND the dump's newest kysely_migrations row is 1792213725597-AddAssetFaceAssetState. Secondary layers: Immich's own 02:00 nightly dump of today under /data/backups (v3.3.6 name), and the 23:00Z Longhorn backup of pvc-34a7dcaa-1069-415b-8abb-84da7acf914e (immich-pg-data) FRESH < 26h."
restore_proof: "§3.2: the §3.1 dump is restored into a SCRATCH database immich_restoretest on the same immich-postgres instance (psql -v ON_ERROR_STOP=1, Immich's documented search_path rewrite) and, BEFORE the tag edit is pushed, count(*) of asset, asset_face, person, \"user\", album and library in immich_restoretest must equal the §2.5 live counts, the public BASE TABLE count must be 72, the newest kysely_migrations row must be 1792213725597-AddAssetFaceAssetState, and pg_extension must list vchord and vector. Any mismatch or a psql error = STOP, do not push. The scratch DB is dropped at the end of §3.2 by its exact name (never DROP DATABASE immich here)."
finding_refs: [F-54e86f6d, F-9f05768d] # F-54e86f6d version: "immich-server: image ghcr.io/immich-app/immich-server v3.3.6 -> v3.4.0 (minor)" - this
                                      # plan supersedes its target with v3.4.2. F-9f05768d = the critical security finding (still open
                                      # 2026-11-19, newer upstream tag exists). Queried 2026-11-13, re-queried 2026-11-19 (`policy-cli.py finding list --grep
                                      # immich`). F-f7fa90d3 (immich-machine-learning) belongs to the sibling plan, not here.
review: ready-for-go@2026-11-19         # plan-reviewer verdict for the v3.4.2 retarget (digest fc880c1b...); 2026-11-23: §4.6 up query pinned to pod=$NEWPOD per reviewer hardening
status: vetted
window: null
premises:
  - id: server-image-is-v3.3.6
    why: >-
      current, the digest, the baselines and the "pre-migration" expectation were captured
      against this pin. If the Deployment already moved, this plan is stale - stop and re-assess.
    run: |-
      kubectl get deploy immich-server -n media -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "ghcr.io/immich-app/immich-server:v3.3.6"
  - id: server-hr-ready
    why: "A HelmRelease already failing would mask whether the bump itself reconciled."
    run: |-
      kubectl get helmrelease immich-server -n media -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: server-strategy-recreate
    why: >-
      Single replica holding an i915 slot; RollingUpdate would start the new pod (and its
      migrations) while the old one still serves.
    run: |-
      kubectl get deploy immich-server -n media -o jsonpath='{.spec.strategy.type}'
    expect_exact: "Recreate"
  - id: hr-upgrade-retries-is-3
    why: >-
      §3.3 flips upgrade.remediation.retries 3 -> 0 with a sed anchored on the value 3. If it
      is not 3 the sed is a silent no-op and Helm could roll back onto the migrated DB.
    run: |-
      kubectl get helmrelease immich-server -n media -o jsonpath='{.spec.upgrade.remediation.retries}'
    expect_exact: "3"
  - id: tag-line-matches-once
    why: "The §3.3 tag sed must match exactly one line of the server HelmRelease in the working tree."
    run: |-
      grep -c '^[[:space:]]*tag: v3\.3\.6$' kubernetes/apps/media/immich/app/helmrelease.yaml
    expect_exact: "1"
  - id: immich-alerts-quiet
    why: "ImmichServerNotReady / ImmichPodCrashLooping must be quiet before the change, or §4.7 cannot attribute a firing."
    run: |-
      kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=ALERTS%7Balertname%3D~%22ImmichServerNotReady%7CImmichPodCrashLooping%22%2Calertstate%3D%22firing%22%7D'
    expect_contains: '"result":[]'
  - id: immich-postgres-still-pg14
    why: >-
      Renovate PR #282 (immich-app/postgres 14 -> 16, held) must not have landed: the dump,
      the restore proof, the §5 restore path and the §2.5 baselines all assume pg14.
    run: |-
      kubectl get deploy immich-postgres -n media -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_matches: '^ghcr\.io/immich-app/postgres:14-'
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/immich.md
  - docs/sops/backup.md
  - docs/sops/storage-safety.md
  - docs/sops/authentik.md
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/vulnerability-disclosure.md
generated: "2026-11-13"
retargeted: "2026-11-19"
---

# immich-server v3.3.6 -> v3.4.2

## 1. Summary & why held

One-line image-tag bump of the Immich server container in
`kubernetes/apps/media/immich/app/helmrelease.yaml` (`controllers.main.containers.main.image.tag`),
plus a temporary `upgrade.remediation.retries: 3 -> 0` guard in the same commit (§6).
The two `busybox:1.38.0` init containers (`wait-for-postgres`, `wait-for-redis`) in the same pod
are **unchanged and out of scope** - the `busybox` repo named on the workload is not part of this update.

**Why held - a TRUE positive.** Deny rule `*immich*` in `runbooks/auto-update-policy.yaml`:
"Immich server applies forward-only DB migrations; revert after migration crash-loops. Plan lane
only: dump + scratch-restore proof first." Measured for this hop: listing
`server/src/schema/migrations` at tags `v3.3.6` (102 files) and `v3.4.1` (105 files) gives exactly
three new migrations, all present in v3.4.0 already (v3.4.0 and v3.4.1 lists are identical):

| Migration | `up()` does |
|---|---|
| `1792511451454-AddPasskeyTable` | `CREATE TABLE "passkey"` and `"auth_challenge"` (FKs to `"user"`), indexes `passkey_userId_idx`, `passkey_updateId_idx`, `auth_challenge_userId_idx`, trigger `passkey_updatedAt`, one `migration_overrides` row |
| `1792517020180-AddUpdateIdIndexes` | `CREATE INDEX` `stack_updateId_idx`, `asset_face_updateId_idx`, `workflow_updateId_idx` |
| `1792568637987-AddAssetOwnerIdUpdateIdIndex` | `CREATE INDEX "asset_ownerId_updateId_idx" ON "asset" ("ownerId", "updateId")` |

All additive: no column dropped, no row rewritten. On this DB (asset 79,269 / asset_face 60,959
rows, 1242 MB, 2026-11-13) the index builds take seconds. The risk is the **rollback**, not the
forward step: Immich never runs `down()` on its own and an older server refuses a newer schema
(`database.repository.ts`: `Migration "<name>" was already applied to this database but is not in
this version of Immich ... Downgrades are not supported.`). That happened here on 2026-10-12
(`a844cf8d`). Hence `rollback_class: backup-restore`, with a fresh dump and a scratch-restore
proof before the push.

**Retarget 2026-11-19 (v3.4.1 -> v3.4.2).** v3.4.2 (published 2026-11-18T20:14Z, GitHub `Latest`,
`isPrerelease=false`, `isDraft=false`; ghcr index digest above) is an 11-commit patch on top of v3.4.1
(`gh api repos/immich-app/immich/compare/v3.4.1...v3.4.2`). **It adds no migration**: the tree object of
`server/src/schema/migrations` is byte-identical at both tags (git tree sha `cbb7ef7e...`, 105 files, newest
`1792568637987-AddAssetOwnerIdUpdateIdIndex`), and `database.repository.ts`, `constants.ts`,
`machine-learning.repository.ts` and `immich_ml/schemas.py` have identical blob SHAs. The migration risk
is therefore EXACTLY that of 3.4.1: three forward-only, additive migrations. Server-side code changes are
two files: `server/src/utils/media.ts` (drop `range=pc` on vaapi, #33262 - touches the i915 transcode
path used here, hence §4.10b) and `server/src/repositories/telemetry.repository.ts` (#33450, below).
Other changes: web fixes (CSP hash for external styles #33275, slideshow, combobox, filename alignment),
integrity-report downloads fix, FUTO Backups module 1.18.1 / restic 0.19.1-futo.2 bump (#33448; the
backups feature still defaults off). Release headline: "Some more bug fixes and a new FUTO Backups
version in this one!"

**Exporter bind address changed again in v3.4.2** (#33450 / #33457 "fix: prometheus exporter listening").
v3.4.1 bound `host: '0.0.0.0'`; v3.4.2 binds `host` from `IMMICH_HOST`, defaulting to `'::'`
(`const { telemetry, host = '::' } = new ConfigRepository().getEnv()`). Live, `IMMICH_HOST` is NOT set on
the Deployment and the pod's current listeners (ports 8081/8082/2283) are already `[::]` sockets in
`/proc/net/tcp6` with `bindv6only=0`, serving IPv4 scrapes (`up{job="immich-server"}` = 1 on both
endpoints 2026-11-19), so a `::` bind is expected to keep working over the IPv4-only Service
(`ipFamilies: [IPv4]`). That is a prediction, not a proof - §4.6 stays the hard gate.

**Upstream evidence** (GitHub releases `immich-app/immich`; v3.4.2 is `Latest`, not a prerelease; the v3.4.0/v3.4.1 notes below still apply to the 3.3.6 -> 3.4.2 jump):
- `v3.4.0` (2026-11-10): "This release adds workflow improvements, JPEG XL support, tags on mobile
  (finally?!), a plethora of security fixes and other improvements and bug fixes." The notes carry a
  Security section; it is not reproduced here.
- `v3.4.1` (2026-11-11): "This patch release fixes various bugs. Notably, it also fixes the
  performance issues with shared links." It includes #33203 "fix: prometheus exporter should listen
  on all interfaces" - "Regression of #32759 which changed the default value from `0.0.0.0` to
  `localhost`". **v3.4.0 would have cut both scrape endpoints of this deployment**; v3.4.1 source
  reads `new PrometheusExporter({ port, host: '0.0.0.0' })` (`telemetry.repository.ts@v3.4.1`).
  v3.4.1 fixed that; v3.4.2 changes the bind again (above). This is why §4.6 is a hard gate, not a formality.

**Behaviour changes that matter for THIS deployment** (each read in upstream source/PR, each with a gate):

1. **OAuth cookie handling changed** (#32600: the state / code-verifier cookies are now only set
   for server-generated values). Login here is Authentik OIDC. Gate: a real OIDC login, §4.9.
2. **CSP no longer ships `unsafe-inline`** (#30529; `server/helmet.json@v3.4.1`:
   `script-src 'self' 'wasm-unsafe-eval' https://www.gstatic.com`). The app is served through
   Cloudflare + `envoy-external`; anything on that path that injects an inline script would now be
   blocked in the browser. Not provable from the cluster. Gate: browser console check, §4.9.
3. **Passkeys (WebAuthn) added** - controller `passkeys`, with `authentication/start|finish`
   declared `@Authenticated({ public: true })`. Default config is `passkey: { enabled: false,
   domain: null }` (`server/src/utils/config.ts@v3.4.1`) and the service throws
   `BadRequestException('Passkeys are disabled')`. Nothing in this plan enables it. Gate: §4.5.
4. **Backups feature ("FUTO Backups" / yucca, #32268) added** behind `backup.beta`, default
   `false`; the image now carries `restic`. Per the PR text its config lives under
   `MEDIA_LOCATION/backups/yucca` and a restic cache under `MEDIA_LOCATION/restic-cache`, i.e. on
   the CIFS `/data` share. **Not verified:** whether the module creates those directories or any
   `futo_backups_*` table at boot while the flag is off (`database.repository.ts@v3.4.1` adds
   `ignorePrefixes: ['futo_backups_']` to the schema drift check). §4.2 therefore asserts the named
   objects, not an exact table count, and §4.5 asserts the feature flag reads `false`. Leave any
   such directory alone - no `rm` on a CIFS share in this plan.
5. **Library crawl no longer follows symlinks** (#32614). Measured 2026-11-13:
   `find /libraries -type l -print -quit` in the server pod returned nothing with exit 0 over the
   whole ro library, so no asset is reachable only through a symlink. Gate: asset counts, §4.3.
6. **Nightly DB dump compresses with `pigz --rsyncable` on all cores when available** (#32806; the
   filename format is unchanged, `immich-db-backup-<ts>-v<version>-pg<ver>.sql.gz`). The pod's
   `cpu: "4"` limit bounds it; do not touch that limit (thermal bound on nuc14-01).
7. **Removed API field**: `password` on `PUT/PATCH /users/me` (#32623). Nothing in this repo calls it.

Server version requirements did not move: `server/src/constants.ts` differs between v3.3.6 and v3.4.1 only
by the webauthn exclude path, a JPEG XL constant and an API tag description - the vector-extension
version ranges are untouched, and live extensions are `vchord 0.4.3`, `vector 0.8.1`.

**ML compatibility (`immich-machine-learning`, live `v3.4.1-openvino`).**
- No ML move is required by this plan. The server-to-ML wire contract is unchanged across v3.3.6, v3.4.1
  and v3.4.2: `server/src/repositories/machine-learning.repository.ts` (blob `7c52778e...`) and
  `machine-learning/immich_ml/schemas.py` (blob `2364d7cc...`) are identical at v3.4.1 and v3.4.2; the
  only ML-tree change in 3.4.2 is the `pyproject.toml` version string and `uv.lock`. A v3.4.2 server with
  the live v3.4.1 ML (and, per the earlier measurement, v3.3.6 ML) is the same request/response shape.
- Equal server/ML versions are upstream's recommendation, not something this plan could prove is enforced;
  the evidence here is the identical wire-contract files above, and the live pairing server v3.3.6 + ML
  v3.4.1 has been running since the ML bump. One patch of skew (server 3.4.2, ML 3.4.1) is acceptable; §4.11
  and a smart-search/face job in the UI after the roll are the observable checks if in doubt.
- `ghcr.io/immich-app/immich-machine-learning:v3.4.2-openvino` is NOT published yet (registry HEAD 404
  2026-11-19; `v3.4.2` and `v3.4.2-cuda` exist), so ML cannot be moved in lockstep today even if wanted.
  Renovate will propose it separately; that ML bump is stateless and plan-lane-free.
- Never merge PR #531 as-is: it would land the tag without the `retries: 0` guard (§6).

## 2. Pre-checks

Run from `/Users/mu/code/cberg-home-nextgen` (zsh on the Mac mini).

2.1 Premises: `.venv/bin/python3 runbooks/plan-premises.py immich-server-3.4.1 --require-premises`
→ all PASS. Any FAIL or REFUSED = do not run.

2.2 Flux sanity, nothing in flight in media:
```bash
flux get helmreleases -n media | grep immich      # all four Ready=True
kubectl get pods -n media -o wide | grep immich   # 4 pods Running
```

2.3 DB disk headroom for the scratch restore (needs > 5G free; 17G on 2026-11-13):
```bash
kubectl exec -n media deploy/immich-postgres -- df -h /var/lib/postgresql/data
```

2.4 No library scan / bulk job running (counts in 2.5 would drift):
```bash
kubectl logs -n media deploy/immich-server -c main --since=10m | grep -ciE 'library.*scan|queue.*active'
```
Non-zero is not a stop by itself; note it and treat `asset` / `asset_face` as ">= baseline" in §4.3.

2.5 Baseline (keep in the window log; §3.2 and §4 compare against `/tmp/immich-baseline.txt`):
```bash
kubectl exec -n media deploy/immich-postgres -- sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -F" " \
  -c "select (select count(*) from asset),(select count(*) from asset_face),(select count(*) from person),(select count(*) from \"user\"),(select count(*) from album),(select count(*) from library)" \
  -c "select count(*) from information_schema.tables where table_schema=\$\$public\$\$ and table_type=\$\$BASE TABLE\$\$" \
  -c "select name from kysely_migrations order by name desc limit 1"' | tee /tmp/immich-baseline.txt
```
Measured 2026-11-19: `79280 60960 2381 2 0 2` / `72` / `1792213725597-AddAssetFaceAssetState` (kysely_migrations count 101; 2026-11-13 read `79269 60959`, assets drift upward).

2.6 Checks the premise runner cannot express. ANY failure = STOP, do not push:
```bash
# (a) DB still at the v3.3.6 head: third line of /tmp/immich-baseline.txt must read
#     1792213725597-AddAssetFaceAssetState. A 17925... name = a v3.4 server already ran; plan is stale.
# (b) today's Immich nightly dump exists (absence also means the job queue is unhealthy):
kubectl exec -n media deploy/immich-server -c main -- ls /data/backups | grep -c "immich-db-backup-$(TZ=Europe/Berlin date +%Y%m%d)T020000-v3.3.6"   # 1 (measured 1 on 2026-11-13; 2026-11-19 nightly present); 0 = STOP
# (c) Longhorn backup of the immich-pg-data volume under 26h:
.venv/bin/python3 runbooks/longhorn-backup-age.py pvc-34a7dcaa-1069-415b-8abb-84da7acf914e --max-hours 26   # must contain FRESH (2026-11-13: "3.6h FRESH via backup-cr")
# (d) target still the published tag and the digest this plan recorded:
gh release view v3.4.2 -R immich-app/immich --json isPrerelease,isDraft,tagName   # isPrerelease false, isDraft false
gh release list -R immich-app/immich -L 5                                  # a newer v3.4.x = note it, do NOT retarget in the window
# (e) open regressions against the target (judgement call for the operator, not an automatic stop):
gh issue list -R immich-app/immich --search 'v3.4.2 in:title,body created:>2026-11-18 sort:reactions-+1-desc' -L 15
```

2.7 ML state (informational): `kubectl get deploy immich-machine-learning -n media -o jsonpath='{.spec.template.spec.containers[0].image}'`.
Live 2026-11-19: `...:v3.4.1-openvino`. `v3.4.1-openvino` or `v3.4.2-openvino` = fine; `v3.3.6-openvino` = also allowed (§1 "ML compatibility"), say so in the window log.
Also confirm the pinned digest is still what this plan recorded (a re-pushed tag would invalidate §4.1):
```bash
T=$(curl -s "https://ghcr.io/token?scope=repository:immich-app/immich-server:pull" | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
curl -sI -H "Authorization: Bearer $T" -H "Accept: application/vnd.oci.image.index.v1+json" https://ghcr.io/v2/immich-app/immich-server/manifests/v3.4.2 | grep -i docker-content-digest
# must read sha256:fc880c1bf665b4aab1e74c15e56ab871225989cd546536e6b77e771869af06bd (v3.4.1 reads 7c489add...: control, proves the grep prints a per-tag value)
```

## 3. Steps

### 3.1 Fresh pre-upgrade dump to the Mac (backup_gate)
```bash
set -o pipefail
mkdir -p "$HOME/immich-backups/pre-3.4.2" && chmod 700 "$HOME/immich-backups"
D="$HOME/immich-backups/pre-3.4.2/immich.sql.gz"
kubectl exec -n media deploy/immich-postgres -- sh -c \
  'pg_dump --clean --if-exists -U "$POSTGRES_USER" -d "$POSTGRES_DB" | gzip -1' > "$D" \
  || { echo "DUMP FAILED"; exit 1; }
gzip -t "$D" && echo GZIP_OK
stat -f %z "$D"                                                        # >= 300000000
gunzip -c "$D" | tail -5 | grep -c -- '-- PostgreSQL database dump complete'   # 1
gunzip -c "$D" | grep -c '^COPY public\.'                              # == 72 (second line of the 2.5 baseline)
gunzip -c "$D" | awk '/^COPY public.kysely_migrations /{f=1;next} f&&/^\\\./{exit} f' | sort | tail -1
#   last line must contain 1792213725597-AddAssetFaceAssetState
```
Any check failing = STOP (no push). Can fail: a truncated stream fails `gzip -t` and lacks the
"dump complete" trailer; a wrong database prints a COPY count far from 72.

Second copy for the §5.2 fallback - today's Immich nightly dump, read through the server pod
(the only pod that mounts `/data`; read-only use of the CIFS share):
```bash
set -o pipefail
N="immich-db-backup-$(TZ=Europe/Berlin date +%Y%m%d)T020000-v3.3.6-pg14.19.sql.gz"
kubectl exec -n media deploy/immich-server -c main -- cat "/data/backups/$N" > "$HOME/immich-backups/pre-3.4.2/nightly.sql.gz" \
  || echo "NIGHTLY COPY FAILED"
gzip -t "$HOME/immich-backups/pre-3.4.2/nightly.sql.gz" && stat -f %z "$HOME/immich-backups/pre-3.4.2/nightly.sql.gz"   # ~413 MB (413,952,373 B on 2026-11-13)
```
A failed nightly copy is a note, not a stop (the fresh dump above is the gate; this is the spare).

### 3.2 Restore proof into a SCRATCH database (restore_proof)
```bash
set -o pipefail
D="$HOME/immich-backups/pre-3.4.2/immich.sql.gz"
kubectl exec -n media deploy/immich-postgres -- sh -c \
  'psql -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE immich_restoretest OWNER \"$POSTGRES_USER\""'
gunzip -c "$D" \
 | sed "s/SELECT pg_catalog.set_config('search_path', '', false);/SELECT pg_catalog.set_config('search_path', 'public, pg_catalog', true);/g" \
 | kubectl exec -i -n media deploy/immich-postgres -- sh -c \
   'psql -U "$POSTGRES_USER" -d immich_restoretest -v ON_ERROR_STOP=1 -q' > /tmp/immich-restoretest.log 2>&1 \
 && echo RESTORE_OK || echo RESTORE_FAILED
kubectl exec -n media deploy/immich-postgres -- sh -c 'psql -U "$POSTGRES_USER" -d immich_restoretest -At -F" " \
  -c "select (select count(*) from asset),(select count(*) from asset_face),(select count(*) from person),(select count(*) from \"user\"),(select count(*) from album),(select count(*) from library)" \
  -c "select count(*) from information_schema.tables where table_schema=\$\$public\$\$ and table_type=\$\$BASE TABLE\$\$" \
  -c "select name from kysely_migrations order by name desc limit 1" \
  -c "select string_agg(extname, \$\$,\$\$ order by extname) from pg_extension where extname in (\$\$vchord\$\$,\$\$vector\$\$)"' \
  | tee /tmp/immich-restoretest.txt
diff <(head -3 /tmp/immich-baseline.txt) <(head -3 /tmp/immich-restoretest.txt) && echo COUNTS_MATCH
grep -c '^vchord,vector$' /tmp/immich-restoretest.txt   # 1
```
PASS = `RESTORE_OK`, `COUNTS_MATCH`, extensions line `1`. If 2.4 showed active jobs and only
`asset` / `asset_face` differ, re-take 2.5 and the restoretest counts back-to-back once; a second
mismatch = STOP. A real failure prints a psql `ERROR:` in `/tmp/immich-restoretest.log`
(ON_ERROR_STOP aborts) or a count of 0. If the restore exceeds 20 min, abort it, drop the scratch
DB and STOP (window budget).

Then drop the scratch DB **by its exact name**:
```bash
kubectl exec -n media deploy/immich-postgres -- sh -c \
  'psql -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 -c "DROP DATABASE immich_restoretest"'
```

### 3.3 The GitOps change
Dry-tested on a scratch copy of the file (BSD sed, macOS, 2026-11-13); each sed matches exactly one line:
```bash
sed -i '' 's|^\([[:space:]]*tag: \)v3\.3\.6$|\1v3.4.2|' kubernetes/apps/media/immich/app/helmrelease.yaml
# Helm-remediation guard (§6): same commit, upgrade block only.
sed -i '' '/^  upgrade:/,/^  uninstall:/ s/^\([[:space:]]*retries: \)3$/\10/' kubernetes/apps/media/immich/app/helmrelease.yaml
git diff --stat -- kubernetes/apps/media/immich/app/helmrelease.yaml
git diff -- kubernetes/apps/media/immich/app/helmrelease.yaml | grep -c '^[-+] '   # 4 (two lines out, two in)
```
Diff from the dry run: `25c25 <       retries: 3 --- >       retries: 0` and
`77c77 <               tag: v3.3.6 --- >               tag: v3.4.2`. Any other changed line = stop, `git checkout` the file.
(The ML file's tag reads `v3.4.1-openvino` already and is not matched by this sed - ML is not part of this plan.)

Commit and push (shared worktree - `--only`, then check the subject is yours):
```bash
git commit --only kubernetes/apps/media/immich/app/helmrelease.yaml \
  -m "feat(immich): immich-server v3.3.6 -> v3.4.2 (plan immich-server-3.4.1)"
git log -1 --format=%s     # must be the subject above; amend before push if not
git show --stat HEAD       # exactly one file
OLDPOD=$(kubectl get pod -n media -l app.kubernetes.io/instance=immich-server -o jsonpath='{.items[0].metadata.name}')
git push
PUSH_TS=$(date -u +%s)     # §4.1 / §4.7 / §4.11 read OLDPOD and PUSH_TS
```
Record the commit SHA as `$BUMP`. The Flux webhook reconciles; Recreate replaces the pod; the new
server runs the three migrations at startup.

### 3.4 After §4 passes: restore the remediation retries
```bash
sed -i '' '/^  upgrade:/,/^  uninstall:/ s/^\([[:space:]]*retries: \)0$/\13/' kubernetes/apps/media/immich/app/helmrelease.yaml
git diff -- kubernetes/apps/media/immich/app/helmrelease.yaml | grep -c '^[-+] '   # 2
git commit --only kubernetes/apps/media/immich/app/helmrelease.yaml \
  -m "chore(immich): restore upgrade remediation retries 0 -> 3 after immich-server v3.4.2 verified (plan immich-server-3.4.1)"
git log -1 --format=%s && git show --stat HEAD
git push
```
Dry-run diff: `25c25 <       retries: 0 --- >       retries: 3`. No pod change (HR spec only; confirm the pod name is unchanged).

## 4. Verification

4.1 Rollout + digest (floor). Before pushing §3.3, record the pre-change pod name and the push time:
```bash
OLDPOD=$(kubectl get pod -n media -l app.kubernetes.io/instance=immich-server -o jsonpath='{.items[0].metadata.name}')
echo "$OLDPOD"          # e.g. immich-server-b5cf5f646-92xlj (live 2026-11-16)
# ... git push (§3.3) ...
PUSH_TS=$(date -u +%s)  # take this IMMEDIATELY after `git push` returns
```
Then poll the imageID until it changes, bounded (do NOT trust `rollout status`, which green-lights the old generation):
```bash
NEW=fc880c1bf665b4aab1e74c15e56ab871225989cd546536e6b77e771869af06bd
for i in $(seq 1 40); do   # 40 x 15 s = 10 min cap
  ID=$(kubectl get pod -n media -l app.kubernetes.io/instance=immich-server \
    -o jsonpath='{.items[*].status.containerStatuses[?(@.name=="main")].imageID}')
  case "$ID" in *"$NEW"*) echo "NEW_DIGEST after $((i*15))s"; break;; esac
  sleep 15
done
case "$ID" in *"$NEW"*) ;; *) echo "DIGEST_NOT_CHANGED: $ID";; esac
NEWPOD=$(kubectl get pod -n media -l app.kubernetes.io/instance=immich-server -o jsonpath='{.items[0].metadata.name}')
test "$NEWPOD" != "$OLDPOD" && echo POD_REPLACED
kubectl wait pod/"$NEWPOD" -n media --for=condition=Ready --timeout=10m
```
PASS = `NEW_DIGEST after ...`, `POD_REPLACED`, and the pod condition met. Can fail: after 10 min the
old pod still prints `sha256:e1981983...` (`DIGEST_NOT_CHANGED`) - Flux has not applied the commit
or the pull failed; check `flux get helmrelease immich-server -n media` before anything else.

4.2 CONTENTS ASSERTION: all three migrations applied and their objects exist - measured by:
```bash
kubectl exec -n media deploy/immich-postgres -- sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At \
  -c "select name from kysely_migrations order by name desc limit 1" \
  -c "select count(*) from kysely_migrations" \
  -c "select count(*) from information_schema.tables where table_schema=\$\$public\$\$ and table_name in (\$\$passkey\$\$,\$\$auth_challenge\$\$)" \
  -c "select count(*) from pg_indexes where schemaname=\$\$public\$\$ and indexname in (\$\$stack_updateId_idx\$\$,\$\$asset_face_updateId_idx\$\$,\$\$workflow_updateId_idx\$\$,\$\$asset_ownerId_updateId_idx\$\$,\$\$passkey_userId_idx\$\$,\$\$passkey_updateId_idx\$\$,\$\$auth_challenge_userId_idx\$\$)" \
  -c "select count(*) from information_schema.tables where table_schema=\$\$public\$\$ and table_type=\$\$BASE TABLE\$\$"'
```
PASS = `1792568637987-AddAssetOwnerIdUpdateIdIndex` / `104` / `2` / `7` / a number `>= 74`.
Can fail - the live pre-state on 2026-11-13 printed `1792213725597-AddAssetFaceAssetState` / `101` /
`0` / `0` / `72`. Record the last number and, if it is above 74, list the extra tables in the window
log (`\dt futo_backups_*`): that answers the §1 item-4 unknown; it is not a failure.

4.3 CONTENTS ASSERTION: no data lost - counts compared to the 2.5 baseline. Re-run the first 2.5
query; PASS = `person`, `user`, `album`, `library` equal the baseline (`2381 2 0 2`); `asset` and
`asset_face` `>=` baseline (night jobs add, a scan must not remove). Any decrease = STOP and
assess before anything else: an `asset` drop after this bump points at §1 item 5 (symlink crawl)
and is NOT fixed by a DB restore alone.

4.4 API answers as v3.4.2:
```bash
kubectl port-forward -n media svc/immich-server 22830:2283 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s localhost:22830/api/server/version; echo
curl -s localhost:22830/api/server/ping; echo
curl -s localhost:22830/api/server/features; echo
curl -s -w '\nHTTP %{http_code}\n' -X POST -H 'content-type: application/json' -d '{}' localhost:22830/api/passkeys/authentication/start
curl -sI localhost:22830/ | grep -i content-security-policy
kill $PF 2>/dev/null
```
PASS = version contains `"major":3,"minor":4,"patch":2` (pre-state `"minor":3,"patch":6`) and ping is `{"res":"pong"}`.

4.5 New capabilities stay OFF (same output as 4.4):
- `features` contains `"backups":false` and still contains `"oauth":true` and `"passwordLogin":true`.
  Pre-state 2026-11-13 has no `backups` key at all, so its absence post-change = wrong image or a
  renamed flag: stop and read `server/src/dtos/server.dto.ts` for the target.
- the passkey POST returns **exactly `HTTP 400`** with a body containing `Passkeys are disabled`
  (case-insensitive). Anything else fails the gate: `404` = the route does not exist, i.e. still the
  old image (the v3.3.6 pre-state returns `404`); `2xx` = passkeys are enabled, which nobody decided;
  a `400` with a DIFFERENT message (e.g. a DTO validation error on the empty body) means the request
  never reached the disabled-check, so it proves nothing about the flag - stop and read
  `server/src/services/passkey.service.ts@v3.4.2`, do not call it a pass.
- the CSP header line is recorded in the window log (informational; no CSP header was returned on
  `HEAD /` at v3.3.6 on 2026-11-13).

4.6 Metrics still scraped after the restart - the gate for the v3.4.0 exporter regression (§1):
CONTROL: metric up - `up{job="immich-server"}` returns two series (endpoints `metrics-api`,
`metrics-ms`), both `1`, with a sample timestamp after the new pod became Ready (measured
2026-11-13: two series, both 1). A localhost-bound exporter reads `0` on both.
```bash
kubectl get --raw "/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=up%7Bjob%3D%22immich-server%22%2Cpod%3D%22$NEWPOD%22%7D"   # pinned to the NEW pod: an old-pod series cannot satisfy the gate
```
CONTROL: metric immich_users_total - CONTENTS ASSERTION: the series carried by the NEW pod name
reads `2`, the `"user"` count of the 2.5 baseline (measured 2026-11-13: `2`, label
`endpoint="metrics-api"`). Empty or carrying only the old pod name = the API exporter is not
emitting; a value other than 2 = the server is not reading the database we migrated.
```bash
kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=immich_users_total'
```
Allow up to 3 scrape intervals (60 s each) before calling it failed.

4.7 Alerts quiet, measured from the PUSH (`$PUSH_TS`, §4.1), not from Ready:
CONTROL: alertname ImmichServerNotReady - not firing.
CONTROL: alertname ImmichPodCrashLooping - not firing.
(Same query as the `immich-alerts-quiet` premise; PASS = `"result":[]`.) Read it no earlier than
`$PUSH_TS + 15 min` AND no earlier than the new pod's `.status.startTime + 10 min`
(`kubectl get pod "$NEWPOD" -n media -o jsonpath='{.status.startTime}'`), whichever is later.
Why not "10 min after Ready": a pod that crash-loops through its migrations before finally going
Ready has already spent its alert `for:` window before Ready; counting from Ready would read a
quiet query over a period that excluded the failure. Additionally confirm
`kubectl get pod "$NEWPOD" -n media -o jsonpath='{.status.containerStatuses[?(@.name=="main")].restartCount}'`
prints `0` - a non-zero count is a startup failure even if the alerts never reached `firing`.

4.8 Public route still serves the app (through Cloudflare + `envoy-external`, hostname read from the route so it is not written here):
```bash
H=$(kubectl get httproute immich-server -n media -o jsonpath='{.spec.hostnames[0]}')
curl -s "https://$H/api/server/version"; echo      # "major":3,"minor":4,"patch":2
curl -s -o /dev/null -w '%{http_code}\n' "https://$H/"   # 200
```

4.9 Real login + CSP, in Chrome on the Mac (auth-class change, §1 items 1 and 2). The executor
does this itself; only a password prompt goes to the operator:
- open `https://$H/` in a fresh private window with DevTools Console open;
- the login page renders and the console shows **no** `Refused to execute inline script` /
  `Content Security Policy` error that stops the app from booting (a blocked injected third-party
  snippet with the app working is a note for the report, not a rollback);
- click the OAuth button, complete the Authentik login, land on the timeline with thumbnails
  loading, open one photo and one video.
PASS = logged in via OIDC and assets display. Can fail: an OAuth callback error page
(state/verifier cookie mismatch) or a blank page with CSP errors. A failure here with 4.1-4.8
green is the case for §5 "decision first": password login still works for the admin, so prefer
diagnosing over restoring.

4.10 Mounts and GPU unchanged (SOP T2):
```bash
kubectl exec -n media deploy/immich-server -c main -- sh -c 'touch /libraries/x; ls /dev/dri'
```
PASS = `touch` fails with `Read-only file system` and the listing contains `renderD128`.

4.10b VAAPI transcode flag change (#33262 drops `range=pc` on vaapi; i915 path used here). Informational,
not a rollback trigger: with hardware transcoding enabled in the admin settings, trigger one short video
transcode (or open a video that needs it) and read `kubectl logs -n media "$NEWPOD" -c main --since=10m | grep -ciE 'vaapi.*(error|fail)|ffmpeg.*(error|exited with code [1-9])'`.
Can fail: a non-zero count right after the transcode means the new filter chain is rejected by the iGPU;
a 0 only counts if the transcode actually ran (control: the same grep over the log must also show the job
line, `grep -ciE 'transcod'` >= 1). If transcoding is disabled in settings this check is skipped and says so.

4.11 No migration/DB errors in the server log since start (case-insensitive). The read is the
WHOLE log of the new pod (no `--since`): migrations run at container start, so a time window anchored
at verification time could exclude them. This is an ABSENCE
gate, so it carries its two controls in the same step; a zero is only a pass when both controls pass.
```bash
RE='downgrades are not supported|migration.*(fail|error)|QueryFailedError|error: relation|column .* does not exist'
# CONTROL 1 - the log read is from the NEW pod and is non-empty:
test "$NEWPOD" != "$OLDPOD" && echo POD_IS_NEW                          # $OLDPOD/$NEWPOD from §4.1
kubectl logs -n media "$NEWPOD" -c main | wc -l             # must be > 0
kubectl logs -n media "$NEWPOD" -c main | grep -c 'Finished running migrations'   # positive control: must be >= 2 (proves the read covers the migration phase)
# CONTROL 2 - the pattern can match the 2026-10-12 failure text (dry-tested on macOS 2026-11-16: prints 1):
echo 'Downgrades are not supported' | grep -ciE "$RE"                   # must print 1
# GATE:
kubectl logs -n media "$NEWPOD" -c main | grep -ciE "$RE"   # must print 0
```
PASS = `POD_IS_NEW`, line count `> 0`, replay `1`, gate `0` (gate measured `0` on v3.3.6, 2026-11-13).
Can fail: the 2026-10-12 incident printed "Downgrades are not supported". A line count of 0 (wrong
pod, log not yet flushed, or a crashed container with no current log) makes the gate's `0`
meaningless - re-read after 60 s, and if still empty use `--previous` and treat it as a FAIL.

4.12 Next morning (not a window gate): `/data/backups` holds a dump named
`immich-db-backup-<date>T020000-v3.4.2-pg14.19.sql.gz` of roughly the previous size (413 MB) -
proves the pigz path (§1 item 6) produces a dump. Then close `F-54e86f6d` (version) and, once the sweep
re-scans the new tag and agrees, `F-9f05768d` (security) with
`runbooks/policy-cli.py finding close <id> --commit $BUMP`.

## 5. Rollback

**Decision first.** If v3.4.2 boots and serves (4.1-4.4 pass) but something else is off (OIDC,
CSP, a UI regression), **prefer roll-forward or leave it and report** - a DB restore costs ~20 min,
loses the job output since the dump, and upstream ships patch releases within days. Restore only
if the server cannot serve on the migrated DB, or data is missing (4.3).

**Never just `git revert $BUMP`.** v3.3.6 against the migrated DB refuses to start ("Downgrades
are not supported"). The rollback is this procedure, in order:

5.1 Stop the server so nothing writes or migrates mid-restore (rollback-only direct actions):
```bash
flux suspend helmrelease immich-server -n media
kubectl scale deploy/immich-server -n media --replicas=0
kubectl get pods -n media -l app.kubernetes.io/instance=immich-server   # none
```

5.2 Replace database `immich` from the §3.1 dump (the one §3.2 proved restorable):
```bash
set -o pipefail
D="$HOME/immich-backups/pre-3.4.2/immich.sql.gz"
kubectl exec -n media deploy/immich-postgres -- sh -c \
  'psql -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 -c "DROP DATABASE \"$POSTGRES_DB\" WITH (FORCE)" -c "CREATE DATABASE \"$POSTGRES_DB\" OWNER \"$POSTGRES_USER\""'
gunzip -c "$D" \
 | sed "s/SELECT pg_catalog.set_config('search_path', '', false);/SELECT pg_catalog.set_config('search_path', 'public, pg_catalog', true);/g" \
 | kubectl exec -i -n media deploy/immich-postgres -- sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -q' \
 && echo RESTORE_OK
```
Then re-run the 2.5 query: PASS = identical to `/tmp/immich-baseline.txt` (72 tables, newest
migration back to `1792213725597-AddAssetFaceAssetState`).
Fallbacks if the Mac dump is unusable, in this order:
- `$HOME/immich-backups/pre-3.4.2/nightly.sql.gz`, the copy of today's Immich nightly dump taken
  in §3.1 (same restore pipe, `D` pointed at it). It is copied off BEFORE the push on purpose:
  `/data/backups` is only mounted in the server pod, which 5.1 scales to zero.
  **Never** restore a dump whose name carries `-v3.4.1-` or `-v3.4.2-`: it holds the migrated schema.
- the Longhorn backup of `pvc-34a7dcaa-1069-415b-8abb-84da7acf914e` per `docs/sops/backup.md`
  (restore to a NEW volume; never delete `immich-pg-data`).

5.3 Revert the tag in git and resume. `$BUMP` also carried `retries: 0`; the revert restores `3`,
which is correct once the DB is back at the old schema. If §3.4 already landed, revert `$BUMP` only
and resolve the one-line `retries` conflict to `3`.
```bash
git revert --no-edit $BUMP
git log -1 --format=%s && git show --stat HEAD
git push
flux resume helmrelease immich-server -n media
kubectl get deploy immich-server -n media -o jsonpath='{.spec.replicas}'   # 1; if 0: kubectl scale deploy/immich-server -n media --replicas=1
```

5.4 Confirm back: image `...immich-server:v3.3.6`, imageID `sha256:e1981983...593a`,
`/api/server/version` = `"minor":3,"patch":6`, 4.11 grep = `0`, 4.6 both `up` series `1`, 4.7
alerts quiet, HR Ready. The ML Deployment is not touched by any of this and stays on
v3.4.1-openvino (§1: unchanged wire contract).

Data-loss bound: only DB writes between §3.1 and the restore (face/job results and any album or
share edits made in that interval, on a read-only viewer of the iCloud library; job output is
regenerable by re-queuing). Originals sit on a `ro` mount and are never at risk. No PVC or PV is
created, deleted or patched at any point, and nothing is removed from either CIFS share
(`docs/sops/storage-safety.md`); directories a v3.4.2 server may have created under `/data` are
left in place.

Cleanup (any time later): `rm -rf "$HOME/immich-backups/pre-3.4.2"` once the plan is executed and soaked 7 days.

## 6. Interference notes

- **Helm remediation hazard (2026-10-12 shape).** `helmrelease.yaml` sets
  `upgrade.remediation.retries: 3` (live, premise `hr-upgrade-retries-is-3`) with the helm-controller
  default strategy `rollback`. A v3.4.2 startup that fails or times out (20m) would make Helm roll
  the Deployment back to v3.3.6 ON THE ALREADY-MIGRATED DB, where it crash-loops and the HR flaps.
  §3.3 sets `retries: 0` in the same commit so a failed upgrade stays failed with the new pod
  visible; §3.4 restores `3` after §4 passes. If the upgrade fails: do not let Flux retry;
  `flux suspend helmrelease immich-server -n media`, then §5.
- **Step 0 must not touch immich.** The `*immich*` deny rule holds it; an auto-revertable batch
  containing an immich bump is the exact 2026-10-12 failure (finding `F-2efa3b1f`). If Step 0
  somehow applied it, premise `server-image-is-v3.3.6` fails and this plan is stale.
- **ML:** already at v3.4.1-openvino live; no ML plan exists and none is required (§1 "ML compatibility").
  A later ML 3.4.2 bump is independent. PR #531 is never merged as-is (§1).
- **Human-gated by construction:** `capability_change: true` + `rollback_class: backup-restore`.
  §4.9 needs a browser and an Authentik login, so this is not a 03:30 unattended plan.
- **i915 / nuc14-01:** Recreate frees and re-claims a `gpu.intel.com/i915` slot on k8s-nuc14-01
  (shared with immich-ml and others at `sharedDevNum=3`). Hence the frigate / helm-drift conflicts.
- **Thermal:** the `cpu: "4"` limit is a standing thermal bound - do not touch it. The new pigz
  dump at 02:00 is bounded by it.
- **immich-postgres on nuc14-03** takes the scratch-restore load (index builds); no other plan in
  this window should be measuring nuc14-03 thermals.
- **Public route** (`envoy-external`, Cloudflare) is unchanged; users see a 1-2 min outage.
  Mobile apps older than the server keep working against a newer server in general; not tested here.
- **Prometheus** is this plan's instrument - `kube-prometheus-stack-93.3.0` conflicts (retargeted
  2026-11-16 from the retired 92.22.0).
- **CoreDNS (`coredns-1.50.5`, vetted, chart 1.50.7):** its RollingUpdate replaces both CoreDNS pods.
  immich-server and its `wait-for-postgres` / `wait-for-redis` init containers resolve
  `immich-postgres` / `immich-redis` by Service name at start, and during this plan
  `upgrade.remediation.retries` is `0`: a resolution failure while the migrations run fails the HR
  with no retry and pushes us into §5 for a cause that is not the upgrade. Never in the same slot.
- **Rollback-class stacking with `n8n-2.47.7`** (backup-restore, 21 forward-only migrations): two
  forward-only plans in one slot leave no rollback capacity for either (house rule `81fdd797`).
- **`postgres-fleet-18.7-alpine` / `postgres-fleet-18.7-bookworm` share nothing with
  `immich-postgres`.** Their `touches` are `authentik-pg` (+ its two psql CronJobs) in kube-system and
  `mealie-pg` in office; `immich-postgres` runs `ghcr.io/immich-app/postgres:14-...` (premise
  `immich-postgres-still-pg14`), a different image line, Deployment, PVC and namespace. No conflict
  declared, deliberately. (The bookworm plan's Authentik restart would break a §4.9 OIDC login if
  run at the same moment; the window agent sequences that by time, not by a conflict.)
- **Reciprocity (re-read 2026-11-19):** `envoy-gateway-1.10.0`, `kube-prometheus-stack-93.3.0`, `n8n-2.47.7`
  and `talos-linux-1.14.6` already name `immich-server-3.4.1` (the plan_id, unchanged). Their entries
  for `immich-machine-learning-3.4.1` point at a plan that no longer exists; that is for their owners at
  vetting. **Gap:** `coredns-1.50.5`, redis-fleet-8.10.3, helm-drift-detection, flux-oci-chart-sources,
  talos-power-tuning-ab, longhorn-1.13.0 and frigate-reolink-go2rtc-flv do not list this plan back;
  `window-scheduler.py` honours a one-sided declaration (`81fdd797`), so serialisation holds from this
  side. Removed from our list as superseded: `talos-linux-1.14.5`, `icloud-drive-fleet-2.3.0`.
