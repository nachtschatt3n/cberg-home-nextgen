# Service Integration Reference

> Maintained manually. Update after endpoint changes, new integrations, or config restructuring.
> See `docs/sops/` for step-by-step procedures for each integration.

---

## Ollama AI Endpoint

Single Ollama instance on Mac Mini M4 Pro (`192.168.30.111:11434`) using
Metal Performance Shaders (MPS) for GPU acceleration.

### Models

| Model | Purpose |
|-------|---------|
| `gemma4:26b-mlx` | All LLM tasks (chat, reasoning, vision, voice). Multimodal. |
| `nomic-embed-text:latest` | Text embeddings |

### API Formats

**Native Ollama API (preferred):**
```
Base URL: http://192.168.30.111:11434/api
Endpoints: /api/chat, /api/generate
API Key: Not required
Model name: gemma4:26b-mlx (exact, not gemma4 or gemma4:26b-mlx-instruct)
```

**OpenAI-compatible (for apps that require it):**
```
Base URL: http://192.168.30.111:11434/v1
Endpoints: /v1/chat/completions
```

### Host settings — the numbers live in one place, not here

Engine version, `OLLAMA_CONTEXT_LENGTH`, `OLLAMA_KEEP_ALIVE`, `OLLAMA_NUM_PARALLEL`,
`OLLAMA_MAX_LOADED_MODELS`, the warm set and the measurements behind them are
documented in **`local-ollama-monitor/docs/ollama-model-setup.md`**. They are
deliberately NOT duplicated here — two copies of a number drift, and a stale
number in this file is what a consumer change would be built on.

### ⚠️ Host/consumer context coupling — read before changing `OLLAMA_CONTEXT_LENGTH`

The MLX build of gemma4 has **no baked `num_ctx`**. (The retired GGUF did: 131072
was a model parameter.) The MLX build inherits `OLLAMA_CONTEXT_LENGTH` from the
host env instead. Every consumer that declares a context window is therefore
**mirroring a host setting, not describing the model** — and the two must move
together.

**Rule: lower the consumers FIRST, then the host. Raise the host FIRST, then the
consumers.** Either way the consumer's declared window must never exceed what the
host serves, or the consumer promises a context that will not be delivered and its
compaction never fires in time.

Consumers that declare a context window and must be moved in lockstep:

| Consumer | Where | Sends `num_ctx` on the wire? |
|---|---|---|
| `openclaw` | `helmrelease.yaml` — `contextWindow` on all four `ollama`/`ollama-native` refs | No — uses `/v1`, which has no `num_ctx` field. Over-declaring only over-promises. |
| `hermes-agent` | `configmap.yaml` **and** `/opt/data/config.yaml` on the PVC (the ConfigMap is a SEED — see Known Gotcha #14) | No — `/v1`. Client-side budgeting only. |
| `home-assistant` | HA UI, per Ollama subentry | **YES — and it cannot be omitted.** |
| `sure` | `LLM_CONTEXT_WINDOW` (client-side cap, currently far below the host ceiling) | No. Safe across host moves; re-check the margin before raising it. |

**Home Assistant is the dangerous one.** Its Ollama integration **cannot leave
`num_ctx` unset** — an omitted value does not mean "inherit the host default", it
sends **8192**. So HA always transmits an explicit `num_ctx`, and if that value
disagrees with the host's, **every HA call forces an evict-and-reload of the pinned
18 GB model.** HA must be moved in lockstep with any `OLLAMA_CONTEXT_LENGTH`
change — it is the one consumer where a mismatch is not a promise problem but a
thrashing problem. HA also sets `keep_alive: -1` on its subentries, so a single
call re-pins whatever it loads, permanently.

### Application Configuration

Verification provenance matters here: this table was wrong on 2026-09-04 in both
directions (it listed apps as migrated that were not, and omitted `sure`, the
largest single consumer). Each row says **how and when** its current value was
confirmed, so a claim can be re-checked rather than trusted.

| App | Endpoint | Model | Provider Config | Verified |
|-----|---------|-------|-----------------|----------|
| sure | `http://192.168.30.111:11434/v1` | `gemma4:26b-mlx` | **TWO places:** `OPENAI_MODEL` plain env in `helmrelease.yaml` (this one wins) **and** `OPENAI_MODEL` in `secret.sops.yaml`. Also `LLM_CONTEXT_WINDOW` (client-side cap) and `OPENAI_REQUEST_TIMEOUT`. | 2026-09-04, live pod env on `sure-web` + `sure-worker` |
| hermes-agent | `http://192.168.30.111:11434/v1` | `gemma4:26b-mlx` | `configmap.yaml` is a **SEED ONLY**; live config is `/opt/data/config.yaml` on the `hermes-agent-data` PVC. Also declares `context_length`. | 2026-09-04, file read in-container after restart |
| anythingllm | `http://192.168.30.111:11434` | `gemma4:26b-mlx` + `nomic-embed-text:latest` | `OLLAMA_BASE_PATH`, `EMBEDDING_BASE_PATH` | 2026-09-04, live container env after restart |
| openclaw | `http://192.168.30.111:11434/v1` | `gemma4:26b-mlx` | `OLLAMA_BASE`, `OLLAMA_MODEL` | 2026-09-05, live `openclaw.json` on the PVC after restart |
| next-ai-draw-io | `http://192.168.30.111:11434/api` | `gemma4:26b-mlx` | `AI_PROVIDER: "ollama"`, `OLLAMA_BASE_URL` | 2026-09-04, live pod env |
| librechat | `http://192.168.30.111:11434/v1` | `gemma4:26b-mlx` (fetch=true) | Custom endpoint "Ollama" | 2026-09-05, config + all 37 Mongo collections audited |
| open-webui | `http://192.168.30.111:11434` | (all available) | `ollamaUrls` | 2026-09-05, `webui.db` config + `model` table |
| paperless-ngx (native AI) | `http://192.168.30.111:11434` | `gemma4:26b-mlx` + `nomic-embed-text:latest` | DB-stored `ApplicationConfiguration` row (`ai_enabled`/`llm_*`/`llm_embedding_*`), not GitOps — see `docs/sops/paperless.md` §4a. Retired `paperless-gpt`/`paperless-ai` sidecars 2026-08-24. | 2026-09-04, `ApplicationConfiguration` DB row |
| affine | `http://192.168.30.111:11434/v1` | `gemma4:26b-mlx` + `nomic-embed-text:latest` | OpenAI-compat copilot configmap | 2026-09-04, live ConfigMap JSON |
| frigate-nvr | `http://192.168.30.111:11434/v1` | `gemma4:26b-mlx` (in encrypted config) | `OPENAI_BASE_URL` | 2026-09-04, `/config/config.yml` read in-container after restart |
| nextcloud | `http://192.168.30.111:11434/v1` | `gemma4:26b-mlx` + `nomic-embed-text:latest` | NC UI: `integration_openai` + `context_chat` | 2026-09-04, `occ config:app:get` — all FOUR model keys |
| n8n | (UI-configured) | `gemma4:26b-mlx` | `ollamaApi` credential holds only the base URL; the MODEL is a per-node parameter in the workflow JSON. One node in `ai-sysadmin-agent` (inactive). | 2026-09-05, `workflow_entity` queried **through the SQLite driver** — see the WAL note below |
| n8n | Cloud | OpenAI, Anthropic (cloud models) | n8n UI: `openAiApi`, `anthropicApi` credentials | n/a — cloud only |
| ha-ai-harness | `http://192.168.30.111:11434` | `gemma4:e2b-mlx` (edge) + `gemma4:26b-mlx` (dense) | `OLLAMA_URL`, `EDGE_MODEL`, `DENSE_MODEL` | 2026-09-04, live pod env |
| home-assistant | `http://192.168.30.111:11434` | `gemma4:26b-mlx` (all integrations) | HA UI | 2026-09-05, ha-agent, confirmed with `/api/ps` snapshots |
| headlamp | `http://192.168.30.111:11434` | `gemma4:26b-mlx` | Headlamp UI: AI Assistant plugin | NOT VERIFIABLE — per-browser localStorage, no server-side config |
| paperclip | Cloud | OpenAI API (cloud) | `OPENAI_API_KEY` in SOPS secret | n/a — cloud only |

### How to verify an app's model — and how NOT to

**Never grep an application's database file.** On 2026-09-05 two agents reached
opposite conclusions about n8n from the same 512 MB `database.sqlite`:

- A raw `grep` over the file found **664** occurrences of the old tag and **zero**
  of the new one, and concluded n8n was still on the GGUF.
- A query through the SQLite driver found **14 workflows, 0 naming the old tag,
  1 naming the new one.**

Both reads were of real bytes; only one was of *live* data. Two things defeat a
file-level grep:

1. **WAL mode.** Recent writes live in `database.sqlite-wal` until a checkpoint.
   The updated value was in the WAL, so the main file did not contain it at all.
2. **Free pages.** SQLite does not zero deleted rows. `execution_entity` had been
   pruned to **0 rows**, yet the file still carried the byte patterns of every
   deleted execution record. That is where all 664 hits lived — dead pages, not
   live rows.

So a file grep can report the old value (from dead pages) *and* miss the new value
(sitting in the WAL) simultaneously — wrong in both directions at once.

**Always query through the application's own driver or CLI** (`n8n export:workflow`,
`occ config:app:get`, `sqlite3`/driver, `mongosh`, `manage.py shell`). The same
applies to any app that keeps its own state: AnythingLLM, LibreChat, Open WebUI,
n8n, Nextcloud, paperless, OpenClaw, hermes-agent. A related false positive was hit
on AnythingLLM the same night — three "hits" that turned out to be chat transcripts
in `workspace_chats.response`, not configuration.

**Home Assistant cloud AI integrations (UI-configured, no change):**
- OpenAI (ChatGPT): conversation, AI task, TTS (`gpt-4o-mini-tts`), STT
- Google Generative AI: conversation, TTS, AI task, STT
- Google Translate: TTS

**OpenClaw voice synthesis (say.py):** self-hosted **Qwen3-TTS** (mlx-audio)
on the Mac mini, Trusted VLAN. The base URL comes from the
`OPENCLAW_TTS_FALLBACK_URL` key (name is legacy) in the `openclaw-secret` SOPS
secret — never hard-code it here. This is the **only** provider — ElevenLabs was removed on
2026-08-18 (metered, effectively unused, and its character guard once blocked a
whole morning briefing). Qwen3 returns WAV, which say.py converts to OGG/Opus
via ffmpeg before `sendVoice`. Voice/seed are pinned so multi-chunk briefings
keep one consistent voice; a dead-air guard re-synthesises any chunk whose
speech rate collapses. If the local server is down there is NO fallback — the
openclaw-probe CronJob pages critical.

### Testing Endpoints

```bash
# Test chat endpoint
curl -X POST http://192.168.30.111:11434/api/chat \
  -H "Content-Type: application/json" \
  -d '{"model": "gemma4:26b-mlx", "messages": [{"role": "user", "content": "Hello"}], "stream": false}'

# Test OpenAI-compatible endpoint
curl -X POST http://192.168.30.111:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "gemma4:26b-mlx", "messages": [{"role": "user", "content": "Hello"}]}'

# List available models
curl http://192.168.30.111:11434/api/tags
```

---

## Homepage Dashboard

Homepage provides an auto-discovering dashboard via Kubernetes integration (RBAC-enabled).

**Deployment:** `kubernetes/apps/default/homepage/`

### Service Discovery

Homepage auto-discovers services via ingress annotations. Both annotations AND labels are required.

**Required annotations:**
```yaml
annotations:
  gethomepage.dev/enabled: "true"
  gethomepage.dev/name: "My App Name"
  gethomepage.dev/group: "Group Name"
  gethomepage.dev/icon: "app-icon.png"
  gethomepage.dev/description: "Brief description"
labels:
  gethomepage.dev/enabled: "true"   # REQUIRED for discovery
```

### Homepage Groups

| Group | Used For |
|-------|---------|
| AI | AI/ML applications and services |
| Databases | Database management UIs |
| System | System administration tools |
| Network Services | Network infrastructure UIs |
| Home Automation | Smart home and IoT services |
| Monitoring | Observability and monitoring tools |
| Infrastructure | Core infrastructure services |
| Office | Productivity and office applications |
| Media | Media servers and streaming services |
| Download | Download managers and archivers |
| Software Development | Custom development applications |
| Storage | Storage management UIs |

### Icon Selection

- **Dashboard Icons**: https://github.com/walkxcode/dashboard-icons
- **Material Design Icons**: `mdi-icon-name`
- **Simple Icons**: `si-brand-name`

### Troubleshooting

```bash
# Check Homepage logs
kubectl logs -n default -l app.kubernetes.io/name=homepage

# Verify ingress has both annotations AND labels
kubectl get ingress {name} -n {ns} -o yaml | grep -A5 "annotations:"
kubectl get ingress {name} -n {ns} -o yaml | grep -A5 "labels:"
```

*See `docs/sops/homepage-integration.md` for step-by-step procedures.*

---

## Flux GitOps

**Deployment:** `kubernetes/flux/` and `kubernetes/apps/flux-system/`

### Reconciliation Flow

```
Push to main → GitHub webhook → Flux source-controller detects change
  → kustomize-controller reconciles Kustomizations
  → helm-controller reconciles HelmReleases
  → Cluster state updated
```

### Key Concepts

| Concept | Description |
|---------|-------------|
| HelmRelease | Declares a Helm chart deployment with values |
| HelmRepository | Defines a Helm chart source (OCI or HTTP) |
| Kustomization | Applies a directory of manifests with patches |
| Receiver | Webhook endpoint that triggers reconciliation |

### Key Commands

```bash
# Status overview
flux get kustomizations -A
flux get helmreleases -A
flux get sources helm -A

# Force reconciliation
flux reconcile kustomization {name} -n flux-system --with-source
flux reconcile helmrelease {name} -n {namespace}

# Check logs
kubectl logs -n flux-system deployment/helm-controller --tail=50
kubectl logs -n flux-system deployment/source-controller --tail=50
kubectl logs -n flux-system deployment/kustomize-controller --tail=50

# Suspend/resume
flux suspend helmrelease {name} -n {ns}
flux resume helmrelease {name} -n {ns}
```

### Webhook

Flux Webhook Receiver listens for GitHub push events to trigger immediate reconciliation
instead of waiting for the 30m polling interval.

---

## Renovate Dependency Updates

Renovate automatically creates PRs for dependency updates.

**Configuration:** `.github/renovate.json5`

| Setting | Value |
|---------|-------|
| Schedule | Every weekend |
| Auto-merge | GitHub Actions minor/patch only |
| Semantic commits | Enabled |
| Managers | Flux, Helm, Kubernetes, Kustomize, Helmfile |

### PR Conventions

| Type | Commit Prefix | Auto-merge |
|------|--------------|-----------|
| Major | `feat!:` | No — review required |
| Minor | `feat:` | Yes (GitHub Actions) |
| Patch | `fix:` | Yes (GitHub Actions) |
| Digest | `chore:` | Yes |

### Renovate Dashboard

Open PRs are tracked in `runbooks/version-check-current.md` (generated by `check-all-versions.py`).

```bash
# Check open Renovate PRs
gh pr list --label "renovate"

# View version check report
python3 runbooks/check-all-versions.py
```

---

## UniFi Network Management

**Tool:** `unifictl` — CLI for UniFi Network Controller

**Controller URL:** `https://192.168.30.1:8443`

### Configuration

```bash
# One-time setup
unifictl login \
  --controller-url https://192.168.30.1:8443 \
  --username cli-adm \
  --site default \
  --scope user
# (enter password when prompted)
```

### Key Commands

```bash
unifictl local health               # Network health summary
unifictl local devices              # All devices (switches, APs, gateway)
unifictl local clients              # Connected clients
unifictl local networks -o json     # VLAN/network config
unifictl local wlans                # WiFi networks
unifictl local events               # Recent events
unifictl local top-clients --limit 10  # Top bandwidth consumers
```

*See `docs/network.md` for full UniFi command reference.*

---

## External DNS

external-dns automatically manages DNS records in Cloudflare.

**Deployment:** `kubernetes/apps/network/external/external-dns/`

### Behavior

- Watches ingress resources with `ingressClassName: external`
- Creates CNAME records in Cloudflare: `service.domain → external.domain`
- Uses Cloudflare API token (stored in `secret.sops.yaml`)
- TXT ownership records prefixed with `k8s.`

### Adding External DNS for an App

Add annotation to ingress:
```yaml
annotations:
  external-dns.alpha.kubernetes.io/target: "external.${SECRET_DOMAIN}"
```

The ingress must also use `ingressClassName: external`.

---

## Longhorn Storage

**Deployment:** `kubernetes/apps/storage/longhorn/`

See `docs/sops/longhorn.md` for detailed operational procedures.

### Storage Class Selection

| Class | Use For |
|-------|---------|
| `longhorn` | App databases, StatefulSets, auto-provisioned volumes |
| `longhorn-static` | Config directories, manually managed volumes |

### Key Facts

- Default replicas: 2
- Backup target: UNAS-CBERG NAS
- Backup schedule: Daily CronJob at 3:00 AM
- Dynamic PV names: auto-generated UUIDs (expected for `longhorn` class)
- Static PV names: human-readable (required for `longhorn-static` class)

```bash
# Check volumes
kubectl get volumes -n storage
kubectl get pv,pvc -A | grep {app}

# UI access
kubectl port-forward -n storage svc/longhorn-frontend 8080:80
# Then open http://localhost:8080
```

---

## AdGuard Home DNS

**Deployment:** `kubernetes/apps/network/internal/adguard-home/`

| Setting | Value |
|---------|-------|
| Service IP | 192.168.55.5 (LoadBalancer) |
| DNS port | 53 |
| DNS-over-TLS | 853 |
| Upstream | Cloudflare 1.1.1.1 (DoH), Quad9 9.9.9.9 (DoH) |
| Internal domains | `*.domain` → k8s-gateway 192.168.55.101 |

All LAN clients use 192.168.55.5 as primary DNS (pushed via UniFi DHCP).

---

## CSI Driver SMB (NAS Integration)

**Deployment:** `kubernetes/apps/kube-system/csi-driver-smb/`

Provides SMB/CIFS volume mounts from UNAS-CBERG NAS (192.168.55.240) to Kubernetes pods.

Used by:
- Applications needing large file storage (Jellyfin media library, etc.)
- Backup targets

```bash
# Check SMB CSI driver pods
kubectl get pods -n kube-system -l app=csi-smb-node
kubectl get pods -n kube-system -l app=csi-smb-controller
```


---

## Solarfocus Pellet Heater (VNC → MQTT)

**Deployment:** `kubernetes/apps/home-automation/solarfocus-scraper/`
**Source:** [`github.com/nachtschatt3n/solarfocus-scraper`](https://github.com/nachtschatt3n/solarfocus-scraper) (separate public repo — MIT)
**Image:** `ghcr.io/nachtschatt3n/solarfocus-scraper` — **SHA-pinned**, currently
`sha-a72e07e`. There is no `:latest` deployment; the tag is bumped by an explicit
commit, so read the HelmRelease/Deployment for the live value rather than trusting
this line.

The heater (Solarfocus pellet^top) exposes no Modbus, so we drive its VNC
touchscreen, OCR the visible values with Tesseract, and publish to MQTT
with Home Assistant auto-discovery.

### Architecture

- **State machine** over 13 UI screens (`main`, `auswahlmenue`, `kundenmenue`,
  `betriebsstunden_p1`–`p3`, `kessel`, `heizkreise_og`, `warmwasser`,
  `alert_modal`, `heizkreise_fbh`, `saugaustragung`,
  `automatische_saugsondenumschalteinheit`). Each screen is fingerprinted by a
  sha256 hash of a small static region (title text, version string);
  forward edges are click coordinates; back edges use the top-left back
  arrow (overridable per screen via `back_xy`).
- **Coordinator** singleton serialises cycles (`try_begin_cycle()` gates
  concurrent `run_cycle` calls to `busy`) and owns the last screenshot
  + all value records for the status page.
- **40 sensors** published as individual MQTT topics under
  `solarfocus/<field>`; HA auto-discovers them via retained configs on
  `homeassistant/sensor/solarfocus_pellettop/<field>/config`.
- **Per-field availability.** Each heater sensor carries TWO availability
  sources with `availability_mode: all` — `solarfocus/scraper/availability`
  (the whole cycle failed) and `solarfocus/<field>/available` (this one field
  OCR'd to `None` for N consecutive cycles while the rest of the cycle
  succeeded). Clearing the retained state topic would NOT achieve this: retain
  only governs replay to new subscribers, so an already-connected HA keeps the
  stale value. The scraper's own diagnostic entities (`scraper/status`,
  `scraper/last_run`, `alert/*`) are deliberately NOT gated this way — they must
  stay readable precisely when the heater sensors are unavailable, since they
  are what explain why. Counter `solarfocus_scraper_field_missing_total`
  tracks the per-field misses on `/metrics`.

### Endpoints (ClusterIP, port 8080)

| Path | Purpose |
|------|---------|
| `/` or `/status` | Live HTML page: current screen, last capture PNG, all values with timestamps, state-machine graph |
| `/screenshot.png` | Raw PNG of the latest captured screen |
| `/metrics` | Prometheus format — scraped by the bundled ServiceMonitor |
| `/healthz` | 200 while last cycle finished within `2×SCRAPE_INTERVAL + 60s` |

### MQTT topic tree

| Topic | Payload | Retained |
|-------|---------|----------|
| `solarfocus/<field>` | sensor value (string) | no |
| `solarfocus/<field>/available` | online \| offline — per-field availability | yes |
| `solarfocus/scraper/availability` | online \| offline — whole-cycle availability | yes |
| `solarfocus/scraper/status` | ok \| busy \| navigation_failed \| sanity_failed \| paused | yes |
| `solarfocus/scraper/last_run` | ISO8601 timestamp | yes |
| `solarfocus/scraper/pause` | on \| off — read at start of each cycle | yes |
| `solarfocus/scraper/pause/set` | on \| off — HA writes here, scraper mirrors to `pause` | no |
| `solarfocus/alert/active` | on \| off — heater alert modal present (`device_class: problem`) | yes |
| `solarfocus/alert/title` | most recent alert title | yes |
| `solarfocus/alert/body` | most recent alert body | yes |
| `solarfocus/alert/last_seen` | ISO8601 timestamp of the last alert | yes |
| **`solarfocus-diag/scraper/last_error_image`** | base64 PNG, published on navigation_failed | yes |

> **The failure screenshot lives on a SEPARATE topic prefix.** It moved from
> `solarfocus/scraper/last_error_image` to `solarfocus-diag/...` in `sha-87ba870`
> so the ~250 KB retained base64 PNG is no longer redelivered to every
> `solarfocus/#` subscriber on reconnect (retained dump: 19,224 B → 1,999 B).
> The old topic still exists but is published empty as a tombstone — subscribing
> to it during an incident gets you nothing. Prefix is configurable via
> `MQTT_DIAG_TOPIC_PREFIX` (default `<MQTT_TOPIC_PREFIX>-diag`).

### Operational notes

- **VNC is single-connection**. When someone uses the heater's physical
  touchscreen, VNC connect fails; the scraper reports `status=busy` and
  publishes nothing for that cycle (not an error — expected).
- **Pause**: the `switch.solarfocus_pellet_heater_scraper_pause` HA entity
  toggles the retained `solarfocus/scraper/pause` topic. Useful when
  servicing the heater via VNC from a laptop.
- **Navigation failures** capture the full screenshot as base64 and
  publish it to `solarfocus-diag/scraper/last_error_image` so you can see
  what the heater was showing when the cycle bailed — usually means a
  firmware redraw shifted something, re-calibrate the affected screen's
  hash via `python main.py calibrate <screen>`.

