# solarfocus-scraper

Scrapes a Solarfocus pellet^top heater via VNC (no Modbus available), OCRs
values with Tesseract (German lang pack), and publishes to MQTT with Home
Assistant auto-discovery. 36 sensors across 9 UI screens — kettle temps,
buffer stratification, heat-circuit setpoints/mixer positions, warm-water
tank, and operating-hour counters.

A small HTTP server exposes `/status` (live page: current screen + last
capture + every value with timestamps + state-machine graph), `/metrics`
(Prometheus), and `/healthz` (for k8s probes).

Licensed MIT, © 2026 Mathias Uhl.

## How it works

### Navigation as a state machine

The heater UI is modelled as a directed graph of screens:

```
main ──► auswahlmenue ──► kundenmenue ──► betriebsstunden_p1 ──► p2 ──► p3
                    │
                    ├──► kessel
                    ├──► heizkreise_og ──► heizkreise_fbh
                    └──► warmwasser
```

Each `Screen` has a **hash region** (a small static part of the UI —
title text, version string — whose sha256 fingerprints the screen) and a
`parent` pointer (where the back arrow leads). Forward edges in `EDGES`
encode "click at (x, y) on screen A → land on screen B".

`navigate_to(target)` does BFS over forward edges + back edges:

1. Capture the screen; identify it via hash.
2. BFS the shortest path to target.
3. Click the first edge (forward tap or back arrow).
4. Repeat until at target, or bail after 12 steps.

On an unknown screen (hash doesn't match any), the state machine taps the
back arrow to escape and retries — so a cycle recovers cleanly from any
starting state the heater's touchscreen might have been left in.

### OCR

Tesseract on 2× LANCZOS-upscaled crops. Per-field config (`FIELD_NUM` for
digits with `,.-` whitelist; `FIELD_TEXT` for German status strings).
Status text fields set `invert=True` — grayscale conversion + inversion
turns white-on-blue status bars into the black-on-white Tesseract prefers.

### Coordinator

A single `Coordinator` singleton owns all runtime state. `run_cycle` gates
on `try_begin_cycle()` so a second concurrent caller returns `busy`
immediately — the status page can't kick off cycles, and two scheduled
cycles can't overlap. State mutations take a lock briefly at phase
boundaries (connecting → navigating → ocr → publishing → done); the HTTP
handler snapshots under the same lock so the UI reflects in-flight state.

## Local dev

```bash
sudo pacman -S tesseract tesseract-data-deu

cd apps/solarfocus-scraper
mise install        # Python 3.12 + uv (inherited from repo root)
mise run deps       # uv pip install -r requirements.txt
cp .env.example .env
# edit .env: VNC_HOST, VNC_PASSWORD
```

`.mise.toml` sets `_.python.venv` to `./.venv`, so `cd`-ing here
auto-activates the isolated venv.

For MQTT testing, port-forward the cluster broker:

```bash
kubectl port-forward -n home-automation svc/mosquitto-internal 1883:1883
```

## CLI

| Command | Purpose |
|---|---|
| `python main.py probe` | Connect, capture main screen |
| `python main.py click X Y` | Click (X, Y), capture result |
| `python main.py explore` | Interactive click loop |
| `python main.py navigate <screen>` | Drive state machine to a named screen |
| `python main.py screens` | List configured screens + edges + calibration status |
| `python main.py calibrate <screen>` | Compute + print hash for the current screen |
| `python main.py ocr IMG x,y,w,h [--psm ...] [--invert]` | OCR a region of a saved image |
| `python main.py hash IMG x,y,w,h` | sha256 of a region |
| `python main.py cycle --dry-run` | Full cycle, no MQTT |
| `python main.py cycle --no-mqtt` | Full cycle, skip MQTT entirely |
| `python main.py cycle` | Full cycle, publish to MQTT |
| `python main.py run [--no-mqtt] [--interval N]` | Production loop + HTTP server on :8080 |

## Status website

`python main.py run` starts an HTTP server on `:8080`:

- `/` or `/status` — auto-refreshing HTML page showing cycle state, last
  captured screen image, all values with per-field timestamps and age,
  and the state-machine graph (screens + calibration + edges)
- `/screenshot.png` — raw PNG of the latest captured screen
- `/metrics` — Prometheus format
- `/healthz` — 200 when last cycle < `SCRAPE_INTERVAL_SECONDS * 2 + 60s` ago

## Metrics

| Name | Type | Notes |
|---|---|---|
| `solarfocus_scraper_up` | gauge | 1 while process alive |
| `solarfocus_scraper_last_run_timestamp_seconds` | gauge | unix time of last OK cycle |
| `solarfocus_scraper_last_run_duration_seconds` | gauge | last OK cycle duration |
| `solarfocus_scraper_runs_total{status}` | counter | status ∈ ok\|navigation_failed\|busy\|sanity_failed\|paused |

## MQTT topics

| Topic | Payload | Retained |
|---|---|---|
| `solarfocus/<field>` | sensor value (string) | no |
| `solarfocus/scraper/status` | ok\|busy\|navigation_failed\|sanity_failed\|paused | yes |
| `solarfocus/scraper/last_run` | ISO8601 timestamp | yes |
| `solarfocus/scraper/pause` | on\|off (retained) — scraper reads on each cycle | yes |
| `solarfocus/scraper/pause/set` | on\|off (HA writes here; scraper mirrors to `pause`) | no |
| `solarfocus/scraper/last_error_image` | base64 PNG of the screen when nav failed | yes |
| `homeassistant/sensor/solarfocus_pellettop/<field>/config` | HA discovery JSON | yes |
| `homeassistant/switch/solarfocus_pellettop/pause/config` | HA discovery JSON | yes |

## Sensors (36)

**Main screen (5):** `kesseltemperatur`, `restsauerstoffgehalt`, `status_text`,
`fill_level_percent` (pixel-count over the storage bar), `outside_temperature`.

**Kessel screen (3):** `puffer_temp_top`, `puffer_temp_bottom`, `kessel_status_text`.

**Heizkreis OG (5):** `og_vorlauftemperatur`, `og_vorlaufsolltemperatur`,
`og_mischerposition`, `og_status_text`, `og_heizkreis_status`.

**Heizkreis Fussbodenheizung (5):** `fbh_vorlauftemperatur`,
`fbh_vorlaufsolltemperatur`, `fbh_mischerposition`, `fbh_status_text`,
`fbh_heizkreis_status`.

**Warmwasser / Trinkwasserspeicher (3):** `ww_ist_temp`, `ww_soll_temp`, `ww_modus`.

**Betriebsstundenzähler p1 (7):** Saugzuggebläse, Lambdasonde,
Wärmetauscherreinigung, Zündung, Einschub, Saugaustragung, Ascheaustragungsschnecke.

**Betriebsstundenzähler p2 (5):** Pelletsbetrieb Teillast, Pelletsbetrieb,
Kesselstarts, Betriebsstunden seit Wartung, Pelletsverbrauch (kg).

**Betriebsstundenzähler p3 / Wärmeverteilung (3):** RLA-Pumpe, OG Heizkreis,
Fussbodenheizung.

## Pause toggle

Home Assistant auto-discovers `switch.solarfocus_pellet_heater_scraper_pause`.
Flipping it writes to `solarfocus/scraper/pause/set`; the scraper's MQTT
callback mirrors that to the retained `solarfocus/scraper/pause` topic,
and each cycle checks the in-memory pause flag at the top and skips work
if on.

## Calibration workflow (adding a new screen)

1. `python main.py navigate <parent_of_new_screen>` — get to a known screen
2. `python main.py click <x> <y>` — tap the icon that opens the new screen
3. Decide a stable hash region (title text is usually best) and a name
4. Add a `Screen(hash_region=(x,y,w,h), expected_hash="", parent="...")`
   entry to `SCREENS` + an `EDGES[(parent, new)] = (x, y)` entry
5. `python main.py calibrate <new_screen>` — prints the sha256; paste it
   into `expected_hash`
6. Use `python main.py ocr <screenshot> x,y,w,h [--invert]` to find bboxes
   for each field; add `FieldSpec` entries to `BBOXES`, sanity bounds to
   `SANITY_BOUNDS`, discovery metadata to `SENSORS`
7. `python main.py cycle --dry-run` until all values parse

## Files

- `main.py` — everything (state machine, VNC, OCR, MQTT, HTTP, scheduler)
- `requirements.txt` — pinned deps
- `.env.example` — env var template (copy to `.env`)
- `.mise.toml` — Python 3.12 + local venv at `./.venv`
- `Dockerfile` — python:3.12-slim + tesseract, runs as uid 1000
- `screenshots/` — gitignored capture target

## Deployment

Image: `ghcr.io/nachtschatt3n/solarfocus-scraper` (built by
`.github/workflows/solarfocus-scraper.yaml` on push to main).

Kubernetes manifests live at `kubernetes/apps/home-automation/solarfocus-scraper/`:

- `ks.yaml` — Flux Kustomization
- `app/helmrelease.yaml` — bjw-s app-template v3.7.3, uid 1000, read-only
  root fs, liveness+readiness on `/healthz`, metrics service + ServiceMonitor
- `app/secret.sops.yaml` — SOPS-encrypted VNC creds

Alerts live at
`kubernetes/apps/monitoring/kube-prometheus-stack/app/solarfocus-scraper-alerts.yaml`
(6 rules: scraper up/stale/failing + pod not-ready/crash-loop/restart).
