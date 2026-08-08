# SOP: Immich Photo Library

> Description: Deploy and operate Immich — the self-hosted family photo/video library — as a read-only **external-library viewer** over the iCloud backup on the UniFi NAS, with Intel-iGPU ML face detection, Authentik OIDC SSO, and full Prometheus + Elasticsearch observability.
> Version: `2026.08.08`
> Last Updated: `2026-08-08`
> Owner: `cberg-agent / media`

---

## 1) Description

Immich indexes the existing iCloud mirror (`icloud-docker-mu`, soon `-andrea`) as
**read-only external libraries** and adds a gallery, face detection, and smart
search on top. **iCloud remains the source of truth** — Immich never writes to or
deletes the originals (`:ro` CIFS mount).

- Scope: `media` namespace; `kubernetes/apps/media/immich/`
- Prerequisites: Flux, SOPS age key, `kubectl`, `mise` tooling; iGPU device plugin (`intel-device-plugin-gpu`); csi-driver-smb; Longhorn
- Out of scope: Andrea's photo sync (needs a future `icloud-docker-andrea` deployment — prerequisite for her library); primary-upload/mobile-backup usage (this is a viewer)

---

## 2) Overview

| Setting | Value |
|---------|-------|
| Namespace | `media` (privileged PSA — ML needs `/dev/dri`) |
| Source of truth | `kubernetes/apps/media/immich/` (GitOps) |
| Components | `immich-server`, `immich-machine-learning`, `immich-postgres` (VectorChord), `immich-redis` |
| Version | `v3.1.0` (server + ML pinned identical) |
| DB image | `ghcr.io/immich-app/postgres:14-vectorchord0.4.3-pgvectors0.2.0` (`DB_VECTOR_EXTENSION=vectorchord`) |
| Originals | RO CIFS `cifs-immich-icloud-backup` → `/libraries` (`//NAS/backups` subdir `icloud-backup`) |
| Generated data | Longhorn: `immich-upload` (/data), `immich-ml-cache` (/cache), `immich-pg-data` |
| ML accel | Intel **iGPU** (OpenVINO, `gpu.intel.com/i915`) — **not** the NPU. CPU fallback = plain image tag |
| Ingress | `external` (Cloudflare tunnel) `immich.${SECRET_DOMAIN}` |
| Auth | Authentik **OIDC** (`immich-oauth2-blueprint.yaml`), Auto Register on |
| Metrics | `IMMICH_TELEMETRY_INCLUDE=all` → :8081/:8082, scraped by `immich-server-metrics` ServiceMonitor |
| Logs | Automatic via OTel daemon → edot-collector → ES `logs-generic-default` |
| Alerts | `immich-alerts` PrometheusRule (kube-prometheus-stack) |

---

## 3) Blueprints

- Authentik OIDC: `immich-oauth2-blueprint.yaml` data key in
  `kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml`
  (client_id/secret kept in sync with `media/immich/app/secret.sops.yaml`).
- No other blueprints.

---

## 4) Operational Instructions

### Deploy (GitOps)
1. Manifests live under `kubernetes/apps/media/immich/`; registered in
   `kubernetes/apps/media/kustomization.yaml`. Push to main → Flux reconciles.
2. Bring-up order is enforced by `dependsOn`: postgres + redis → server; ML is
   independent. All four are app-template `3.7.3` HelmReleases.

### First-run interactive steps (cannot be GitOps)
1. **First-boot admin** — visit `https://immich.${SECRET_DOMAIN}`, create the
   local admin (cannot be seeded).
2. **OAuth settings** — Admin → Settings → OAuth: set issuer
   `https://auth.${SECRET_DOMAIN}/application/o/immich/`, paste `OAUTH_CLIENT_ID` +
   `OAUTH_CLIENT_SECRET` (from the secret / blueprint), scopes `openid email profile`,
   enable **Auto Register**.
3. **Per-user external libraries** — after a user logs in once via SSO, Admin →
   External Libraries: create one library per user with import path
   `/libraries/mu/photos` (later `/libraries/andrea/photos`), assign to that user,
   set exclusion globs + a scan cron, and kick the first scan.

### Change ML accel (iGPU ⇄ CPU)
Swap the ML image tag in `machine-learning-helmrelease.yaml`:
`v3.1.0-openvino` (iGPU) ⇄ `v3.1.0` (CPU). Commit; Flux rolls it. No data impact.

---

## 5) Examples

```bash
# Watch reconciliation
flux get hr -n media | grep immich
kubectl get pods -n media -l app.kubernetes.io/instance=immich-server -w

# Confirm the iGPU is visible to ML
kubectl exec -n media deploy/immich-machine-learning -- ls -l /dev/dri

# Confirm vector extensions in the DB
kubectl exec -n media deploy/immich-postgres -- \
  psql -U immich -d immich -c '\dx'
```

---

## 6) Verification Tests (post-deploy acceptance — run top-to-bottom)

A failing test blocks sign-off; each notes its rollback trigger (see §11).

**T1 — Deployment/reconciliation**: `flux get hr -n media | grep immich` all
`Ready=True`; `kubectl get pods -n media -l app.kubernetes.io/instance=immich-server`
(and `-postgres`/`-redis`/`-machine-learning`) Running, 0 restarts; init
containers `wait-for-*` Completed; server log shows migrations applied +
"listening on 2283"; running image digests match the pinned tags (server == ML).

**T2 — Storage & Longhorn**: `immich-pg-data`/`immich-upload`/`immich-ml-cache`
PVCs Bound on `longhorn`; external-lib mount is **read-only** —
`kubectl exec -n media deploy/immich-server -- touch /libraries/x` → **read-only
file system**; `kubectl get sc cifs-immich-icloud-backup -o jsonpath='{.reclaimPolicy}'`
= `Retain`; storage-safety Test 1 & 2 print `OK`; the class is in the
storage-safety Retain table.

**T3 — Database/extensions**: `\dx` lists `vchord` + `vectors`; `/api/server/version`
and `/api/server/statistics` respond; no migration errors in the server log.

**T4 — ML / iGPU (NPU→iGPU correction)**: `/dev/dri` shows `renderD128`; the pod
has `gpu.intel.com/i915: 1` allocated; the ML log selects the **OpenVINO GPU**
provider (not CPU); trigger a face-detection job → completes and a face/person
appears in the UI; `intel_gpu_top` on the node shows engine activity during a
batch. **Fallback test**: swap to the CPU tag → same job completes (slower).

**T5 — External library & data integrity (no NAS writes)**: after a scan, `mu`'s
assets from `.../icloud-backup/mu/photos/YYYY/MM` appear; Immich asset count ≈ NAS
file count for a spot-checked month; thumbnails render (on Longhorn, not the NAS);
UI "delete" is disabled for external assets; **no new/modified files on the NAS**
attributable to Immich (icloud-docker stays the only writer).

**T6 — SSO & multi-user**: `ak show_blueprints | grep immich` → **present, not
errored**; "Login with OIDC" round-trips through Authentik; a new SSO identity
**auto-provisions** a user; `mu` sees only the mu library (and, once Andrea's sync
+ library exist, she sees only hers — cross-visibility = mis-assignment).

**T7 — Observability**: Prometheus `/targets` shows `immich-server-metrics`
endpoints **UP**; `immich_*` metrics return data; the Grafana "Immich" dashboard
(folder Media) populates; ES query on `logs-generic-default` for
`k8s.namespace.name=media` + `k8s.container.name=immich-server` returns recent
lines; `immich-alerts` rules loaded (`/rules`); **synthetic fire** — scale ML to 0
→ `ImmichMLNotReady` fires within ~5m and reaches Telegram + the watcher → scale
back → resolves.

**T8 — External access**: `immich.${SECRET_DOMAIN}` serves over the Cloudflare
tunnel from off-LAN (valid TLS, no NXDOMAIN — proves the `external-dns.target`
annotation); the Immich mobile app logs in via OIDC; add an Uptime-Kuma monitor →
green.

**T9 — Security**: repo `security-check` over the new manifests → no new criticals
beyond image-CVE hygiene; secrets SOPS-encrypted only; OIDC secret identical in
blueprint + app secret; external ingress carries the required annotations; PSA —
only the ML pod is privileged (`/dev/dri`), server/pg/redis run non-root with
dropped caps; admin registration locked after first admin.

**T10 — Neighbour/regression safety**: `icloud-docker-mu` still `Syncing`;
Plex/Jellyfin still transcode (no `Insufficient gpu.intel.com/i915` scheduling
events — `sharedDevNum` slots not starved); Frigate NPU untouched; **0 firing
alerts** cluster-wide (Watchdog excluded); edot ES-rejection rate still 0.

---

## 7) Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| ML `CrashLoopBackOff` after image pull | OpenVINO per-release regression / iGPU init | Swap ML tag to the plain `v3.1.0` (CPU) tag; re-open a GH issue upstream |
| ML logs "No GPU"/falls back to CPU | `/dev/dri` not mounted or i915 not allocated | Confirm `intel-device-plugin-gpu` Ready, `/dev/dri/renderD128` present, pod privileged |
| SSO fails: `invalid_request` "The request is otherwise malformed" | provider `grant_types` empty (blueprint-only provider, Authentik ≥2026.5) | Blueprint must set `grant_types: [authorization_code, refresh_token]`; the redirect_uri is a red herring. See `docs/sops/authentik.md` OIDC gotchas |
| Server `redirect_uri mismatch` on SSO | callback URL missing from blueprint | Add the exact URL as a `strict` redirect_uri; re-encrypt configmap; wait for Reloader |
| SSO works but no user created | Auto Register disabled | Enable it in Immich Admin → OAuth |
| External assets show but thumbnails fail | `immich-upload` PVC full or perms | Check `ImmichUploadPVCFillingUp`; verify fsGroup 1000 on `/data` |
| `\dx` missing `vchord`/`vectors` | wrong PG image or `DB_VECTOR_EXTENSION` | Must be the immich `postgres:14-vectorchord…` image + `vectorchord` |
| Immich indexed but library empty | wrong import path or scan not run | Import path must be `/libraries/<user>/photos`; kick a scan |
| Immich writes appear on the NAS | mount not read-only | SC must carry `ro`; PVC/PV `Retain`; STOP and re-check per storage-safety |

---

## 8) Diagnose Examples

```bash
# ML provider + GPU usage
kubectl logs -n media deploy/immich-machine-learning | grep -iE "openvino|provider|gpu|cpu"
# Logs in ES (via edot) — port-forward ES and query, or use Kibana:
#   k8s.namespace.name:media AND k8s.container.name:immich-server
# Metrics target health
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &
curl -s localhost:9090/api/v1/targets | grep immich
# Blueprint state
kubectl exec -n kube-system deploy/authentik-server -- ak show_blueprints | grep -i immich
```

---

## 9) Health Check

- All four HelmReleases `Ready=True`; pods Running 0-restarts (T1).
- `/api/server/ping` returns `pong`; `/api/server/statistics` responds (T3).
- ML Ready and using the iGPU (T4); metrics targets UP + dashboard populated (T7).
- No firing `immich-*` alerts; `icloud-docker-mu` syncing; Kuma monitor green (T8/T10).

---

## 10) Security Check

- Secrets SOPS-encrypted (`^(data|stringData)$`, correct age recipient); no
  plaintext creds in git (T9).
- External-library mount **read-only**; SC/PV `Retain`; registered in
  storage-safety Retain table (T2).
- OIDC client secret synced blueprint ⇄ app secret; unique `client_id`.
- Only the ML pod privileged (documented `/dev/dri` exception); others non-root,
  caps dropped.

---

## 11) Rollback Plan

- **T1–T4 fail badly** → `git revert` the deploy commit(s) + reconcile → Flux
  prunes the immich HRs/ingress/SM/dashboard/alerts. Read-only CIFS mount + Retain
  SC/PV + Longhorn PVCs mean **no photo or DB data is destroyed** (originals never
  touched; PG volume orphaned, reclaimable).
- **Authentik blueprint errored/collision** → revert the `configmap.sops.yaml`
  change; Reloader rolls authentik back; other SSO apps unaffected (immich
  blueprint is additive).
- **ML only broken** → switch the ML image to the CPU (non-`-openvino`) tag; no
  data impact.
- **Full teardown** → revert all commits, then manually delete the orphaned
  Longhorn `immich-pg-data`/`immich-upload`/`immich-ml-cache` PVCs (per the
  storage-safety delete pre-flight). The NAS `icloud-backup` tree and icloud-docker
  are never touched.
