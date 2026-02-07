# Music Assistant + Alexa Integration - REVISED PLAN

## Primary Goal

**Control Echo devices from Music Assistant Web UI** - Use Music Assistant as a universal music controller where you can:
- Select Echo devices (Echo Show, Echo Dot, etc.) as playback targets
- Browse your music library (Spotify, local files, etc.) in Music Assistant UI
- Play music on Echo devices by clicking in the UI
- Control volume, playback, and see status from Music Assistant

**Not about**: Voice commands like "Alexa, ask music assistant to play" - that's a separate feature we can test later.

## Problem Summary

### Root Cause #1: Stream Server Not Running
Music Assistant's stream server is **NOT running** due to port configuration conflict. When Music Assistant tries to start the stream server on port 8095, it fails with "address already in use" because the webserver is already using that port.

**Evidence from logs**:
```
INFO: Starting streamserver on music.secret-domain:8095
ERROR: [Errno 98] error while attempting to bind on address ('0.0.0.0', 8095): [errno 98] address already in use
```

### Root Cause #2: Echo Devices CANNOT Access Local Network URLs

**CRITICAL DISCOVERY** from research: Amazon Echo devices **cannot** access local network URLs like `http://192.168.55.25:8097/...` because:
- Playback commands route through **Amazon's cloud services**
- Echo devices only fetch streams from **publicly accessible HTTPS URLs**
- "Amazon Cloud instructs the Echo device to play something, and it's not occurring from within the realm of your local network" ([Source](https://community.home-assistant.io/t/amazon-echo-devices-to-send-tts-set-public-url-in-integration-configuration/656410))

**This means**:
- ❌ LoadBalancer IP approach (192.168.55.25) **will NOT work**
- ✅ External HTTPS ingress (`music-stream. secret-domain`) **is REQUIRED**
- ✅ The existing stream ingress is actually **necessary**, not optional!

## Current State

### Already Deployed ✅
- Music Assistant Server v2.7.5 in `home-automation` namespace
- Alexa API container (`ghcr.io/alams154/music-assistant-alexa-api:latest`) as sidecar
- External HTTPS endpoints:
  - `music-api.${SECRET_DOMAIN}` → Port 3000 (Alexa API)
  - `music-stream.${SECRET_DOMAIN}` → Port 8097 (Audio streaming)
- SOPS-encrypted secrets (`music-assistant-alexa-secrets`) with Amazon credentials
- TLS certificates via cert-manager

### Infrastructure Verified
- **Deployment**: `kubernetes/apps/home-automation/music-assistant-server/app/helmrelease.yaml`
- **External Ingresses**:
  - `ingress-alexa-api.yaml` (API endpoint)
  - `ingress-alexa-stream.yaml` (streaming endpoint)
- **Secrets**: `secret.sops.yaml` (encrypted with age key)

## What We Learned (Troubleshooting Summary)

### During Debugging Session
**Issues Encountered**:
1. ❌ Setting TCP Port to `80` → Tried to use external ingress, stream server tried to bind to port 80
2. ❌ Setting TCP Port to `8095` → Port conflict with webserver ("address already in use")
3. ❌ Stream ingress on port 8098 → Wrong backend port (stream server uses 8097)
4. ✅ Disabled signature verification on Alexa skill (fixed authentication errors)

**What We Thought** (INCORRECT):
- External domain (`music-stream.secret-domain`) was unnecessary complexity
- Echo devices could access LoadBalancer IP on local network
- Stream ingress was optional

### After Internet Research
**Critical Discovery**:
- **Echo devices CANNOT access local network URLs** - they only fetch from publicly accessible HTTPS URLs via Amazon cloud
- External HTTPS ingress is **REQUIRED**, not optional
- The "Published IP address" setting tells Music Assistant what URL to generate, not where to bind

**Corrected Understanding**:
- Stream server binds internally on port 8097 (default)
- Published IP should be **external HTTPS domain** (`music-stream.secret-domain:443`)
- Ingress routes external HTTPS → internal HTTP (port 8097)
- Echo devices fetch via: Amazon cloud → External HTTPS → Ingress → LoadBalancer → Stream server

## Requirements Met

### Infrastructure ✅
- Music Assistant Server v2.7.5 deployed in `home-automation` namespace
- Alexa API container (port 3000) - bridges Music Assistant ↔ Alexa
- Alexa skill container (port 5000) - handles Alexa skill requests
- LoadBalancer service at `192.168.55.25`
- External ingress for Alexa API: `music-api.secret-domain`
- SOPS-encrypted Amazon credentials
- Signature verification disabled (`ASK_VERIFY_REQUESTS: false`)
- Basic Auth disabled on Alexa API (not compatible with Alexa skill)

### Still Needed
- Stream server configuration (Published IP + correct port)
- Stream ingress backend port update (8098 → 8097)

## Deployment Architecture Summary

```
┌──────────────────────────────────────────────────────────────┐
│  Music Assistant Pod (hostNetwork: true)                     │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ app container (Music Assistant v2.7.5)                 │  │
│  │   - Webserver: 0.0.0.0:8095 ✅                          │  │
│  │   - Streamserver: 0.0.0.0:8097 ❌ (NOT RUNNING!)       │  │
│  │   └─ Reason: Configured with port 8095 (conflict)     │  │
│  │                                                         │  │
│  │ alexa-api container                                    │  │
│  │   - Port 3000: Alexa API bridge ✅                      │  │
│  │                                                         │  │
│  │ alexa-skill container                                  │  │
│  │   - Port 5000: Alexa skill handler ✅                   │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
                          ↓
         LoadBalancer Service (192.168.55.25)
                    ✅ Working
                          ↓
              ┌───────────┴───────────┐
              ↓                       ↓
    Alexa API Ingress         Stream Ingress
   music-api.secret-domain        music-stream.secret-domain
     (Port 443/TLS)           (Port 443/TLS)
          ✅                       ❌ (Backend port wrong: 8098 instead of 8097)
              ↓
    Echo Devices (via Amazon Cloud)
    - Living Room Echo Show 5
    - Etc.
```

## Solution Architecture (REVISED)

### Use Case: Controlling Echo Devices from Music Assistant UI

The goal is to use Music Assistant's web UI as a **universal remote control** for Echo devices. You select an Echo device as the playback target, browse music, and click play - the audio streams to that Echo device.

### How Music Assistant + Alexa Streaming Actually Works

Music Assistant runs **two separate HTTP servers**:
1. **Webserver** (port 8095): Web UI and API
2. **Streamserver** (port 8097 default): Audio streaming to players

When you control an Echo device from Music Assistant UI, the flow is:
```
Music Assistant UI
  ↓ (select Echo device)
Music Assistant → alexa-api → generates stream URL
  ↓ (URL format: https://music-stream.secret-domain/flow/...)
alexa-skill → Amazon Alexa cloud
  ↓ (Alexa cloud instructs Echo device)
Echo device fetches: https://music-stream.secret-domain/flow/...
  ↓ (via external HTTPS - MUST be publicly accessible!)
External Ingress (music-stream.secret-domain)
  ↓ (routes to backend)
LoadBalancer (192.168.55.25:8097)
  ↓
Music Assistant streamserver serves audio
```

**Key Constraint**: Echo devices **cannot** access local network IPs. They only fetch streams from **publicly accessible HTTPS URLs** routed through Amazon's cloud.

### Network Architecture Decision

**CORRECTED Approach**: **Use External HTTPS Ingress** (required, not optional)

**Why local IP won't work**:
- Echo devices don't directly access streams on local network
- All playback commands route through Amazon cloud first
- Amazon instructs Echo device to fetch from publicly accessible URL
- Local network URLs like `http://192.168.55.25:8097/` are unreachable

**Required Configuration**:
1. Stream server must listen on default port 8097 (internally)
2. Stream ingress (`music-stream.secret-domain`) must route to backend port 8097 (not 8098)
3. Published IP address must be external domain: `music-stream.secret-domain`
4. TCP Port must be external HTTPS port: `443` (ingress handles TLS termination)

## Available Tools for Implementation

### Browser Automation (Claude in Chrome Extension)

I have access to browser automation tools that can help with:

**Music Assistant UI Configuration**:
- Navigate to `https://music.secret-domain`
- Access Settings → System → Streams → Advanced settings
- Configure Published IP address and TCP Port fields
- Click SAVE buttons
- Verify settings are applied correctly

**Alexa Developer Console** (if needed for troubleshooting):
- Navigate to Amazon Developer Console
- Handle login flows if required
- Check skill configuration
- View skill testing interface

**Advantages**:
- Visual confirmation of UI changes
- Can handle complex multi-step configuration
- Screenshot evidence of settings
- Interactive troubleshooting if issues arise

**When to use**:
- UI-based configuration changes (Phases 1 & 3)
- Visual verification of settings
- If configuration needs adjustment during testing

## Implementation Plan (REVISED)

### Phase 1: Fix Stream Server - Use Default Port

**Goal**: Get Music Assistant's stream server running on default port 8097

**Steps**:

1. **Clear/reset Music Assistant stream settings**:
   - Navigate to: Settings → System → Streams → Advanced settings
   - Set "Published IP address": **LEAVE BLANK** (clear any value)
   - Set "TCP Port": **LEAVE BLANK** (clear any value)
   - Click SAVE
   - This allows Music Assistant to use defaults (auto-detect port 8097)

2. **Verify stream server starts successfully**:
   ```bash
   # Check logs for successful startup
   kubectl logs -n home-automation deployment/music-assistant-server -c app --tail=50 | grep -i stream

   # Should see: "Starting streamserver on <IP>:8097" (NO error about port 8095!)
   ```

3. **Test stream server is listening internally**:
   ```bash
   # From within cluster
   curl -I http://192.168.55.25:8097/

   # Should return HTTP response (even if 404, means server is listening)
   ```

### Phase 2: Fix Stream Ingress Backend Port (REQUIRED!)

**Goal**: Route external HTTPS traffic to correct backend port

**This is NOT optional** - Echo devices require external HTTPS access to streams.

1. **Update stream ingress configuration**:
   - File: `kubernetes/apps/home-automation/music-assistant-server/app/ingress-alexa-stream.yaml`
   - Find: `port: number: 8098`
   - Change to: `port: number: 8097`

2. **Commit and push change**:
   ```bash
   cd /home/mu/code/cberg-home-nextgen
   git add kubernetes/apps/home-automation/music-assistant-server/app/ingress-alexa-stream.yaml
   git commit -m "fix(music-assistant): update stream ingress backend port to 8097"
   git push
   ```

3. **Wait for Flux reconciliation**:
   ```bash
   # Monitor Flux applying the change
   kubectl get kustomization music-assistant-server -n flux-system -w
   ```

4. **Verify ingress is updated**:
   ```bash
   kubectl get ingress music-stream -n home-automation -o yaml | grep -A 3 "backend:"
   # Should show port: 8097
   ```

### Phase 3: Configure External URL for Stream Generation

**Goal**: Tell Music Assistant to generate externally accessible HTTPS URLs

1. **Set external stream URL in Music Assistant**:
   - Navigate to: Settings → System → Streams → Advanced settings
   - Set "Published IP address": `music-stream.secret-domain`
   - Set "TCP Port": `443`
   - Click SAVE

2. **Verify configuration applied**:
   ```bash
   kubectl logs -n home-automation deployment/music-assistant-server -c app --tail=50 | grep -i stream

   # Should see streamserver starting on music-stream.secret-domain:443
   ```

### Phase 4: Test External Stream Accessibility

**Goal**: Verify stream ingress works end-to-end

1. **Test HTTPS stream endpoint externally**:
   ```bash
   # From your local machine (not cluster)
   curl -I https://music-stream.secret-domain/

   # Should return HTTP 404 or similar (server responds, just no root path)
   # Should NOT return 502 Bad Gateway
   ```

2. **Test with actual stream path**:
   - Trigger playback from Music Assistant UI to Echo device
   - Monitor alexa-api logs to capture generated stream URL:
     ```bash
     kubectl logs -n home-automation deployment/music-assistant-server -c alexa-api -f
     ```
   - Copy the stream URL (should be `https://music-stream.secret-domain:443/flow/...`)
   - Test URL accessibility:
     ```bash
     curl -I "<stream-url-from-logs>"
     ```

### Phase 5: Test Playback to Echo Device

**From Music Assistant UI**:
1. Open Music Assistant UI: `https://music.secret-domain`
2. Navigate to Home or Players
3. Select an Echo device (Living Room Echo Show 5 2nd Gen)
4. Play a track
5. Monitor all three container logs in parallel:
   ```bash
   # Terminal 1: Music Assistant main
   kubectl logs -n home-automation deployment/music-assistant-server -c app -f

   # Terminal 2: Alexa API
   kubectl logs -n home-automation deployment/music-assistant-server -c alexa-api -f

   # Terminal 3: Alexa Skill
   kubectl logs -n home-automation deployment/music-assistant-server -c alexa-skill -f
   ```

**Expected Behavior**:
- alexa-api logs show: Stream URL generated with `https://music-stream.secret-domain:443/flow/...`
- alexa-skill logs show: No errors, request accepted
- Echo device announces: "Playing music from Music Assistant" (or similar)
- Audio starts playing within 3-5 seconds
- Music Assistant UI shows playback status

**If playback fails**:
- Check Echo device's spoken error message
- Review all three container logs for errors
- Verify stream URL is accessible externally (curl test from Phase 4)
- Check ingress logs: `kubectl logs -n kube-system -l app.kubernetes.io/name=ingress-nginx --tail=50 | grep music-stream`

## Critical Files to Modify

| File | Change | Required? |
|------|--------|-----------|
| Music Assistant UI Settings (Phase 1) | Published IP: **blank**, TCP Port: **blank** | **YES** (clears port conflict) |
| `ingress-alexa-stream.yaml` | Port 8098 → 8097 | **YES** (Echo devices need external HTTPS access) |
| Music Assistant UI Settings (Phase 3) | Published IP: `music-stream.secret-domain`, TCP Port: `443` | **YES** (generates correct HTTPS URLs) |

**File path**: `kubernetes/apps/home-automation/music-assistant-server/app/ingress-alexa-stream.yaml`

## Verification Checklist

### Phase 1: Stream Server Running Internally
- [ ] Music Assistant logs show: "Starting streamserver on <IP>:8097" (NO port 8095 error!)
- [ ] Internal port 8097 responds: `curl -I http://192.168.55.25:8097/`
- [ ] No "address already in use" errors in logs

### Phase 2: Stream Ingress Updated
- [ ] ingress-alexa-stream.yaml committed with port 8097
- [ ] Flux successfully reconciled the change
- [ ] Ingress backend shows port 8097: `kubectl get ingress music-stream -n home-automation -o yaml`

### Phase 3: External URL Configured
- [ ] Music Assistant settings show: Published IP `music-stream.secret-domain`, TCP Port `443`
- [ ] No errors when saving settings

### Phase 4: External Stream Accessibility
- [ ] External HTTPS endpoint responds: `curl -I https://music-stream.secret-domain/`
- [ ] Stream URLs use HTTPS format: `https://music-stream.secret-domain:443/flow/...`
- [ ] Actual stream URL is accessible externally (captured from logs and tested)

### Phase 5: Alexa Integration
- [ ] alexa-api generates stream URLs with external HTTPS domain
- [ ] alexa-skill accepts requests without errors
- [ ] Echo device successfully fetches stream via Amazon cloud
- [ ] No "problem with the skill's response" errors

### Playback
- [ ] Music Assistant UI → Echo device playback works
- [ ] Audio plays on Echo device within 3-5 seconds
- [ ] Music Assistant UI shows playback status
- [ ] Playback controls work (play/pause/stop)

## Expected Outcome

### Primary Goal: Music Assistant UI → Echo Device Control

Once complete, you will be able to:
1. **Open Music Assistant web UI** (`https://music.secret-domain`)
2. **Select an Echo device** as playback target (Living Room Echo Show 5, etc.)
3. **Browse your music library** (Spotify, local files, etc.)
4. **Click play on any track/album/playlist**
5. **Audio plays on the selected Echo device**
6. **Control playback** from Music Assistant UI:
   - Play/Pause/Stop
   - Volume adjustment
   - Track skipping
   - See current playback status

**This is NOT about voice commands**. The goal is to use Music Assistant's UI as a remote control for your Echo devices, treating them as just another playback target alongside other players.

### Secondary (Optional): Voice Control
Voice control ("Alexa, ask music assistant to play") uses the Alexa skill differently and can be tested later. The current focus is **UI-based control only**.

## Known Limitations

**Music Assistant + Alexa Integration** (from official documentation):
- Command execution may fail with frequent use (Alexa API rate limits)
- Playback status/volume display inconsistencies
- No synchronized multi-room playback
- No shuffle/repeat/crossfade support
- Alexa integration marked as "experimental" (beta channel)

**Kubernetes Deployment**:
- Not officially supported by Music Assistant
- Requires `hostNetwork: true` for layer 2 network access
- Manual IP configuration required (Published IP address)

## Compliance with Your Standards

This plan adheres to your GitOps and security standards:

**✅ No Breaking Changes**:
- Existing deployments remain unchanged
- No modifications to other services
- No changes to network VLANs or firewall rules required
- Uses existing LoadBalancer service (no new infrastructure)

**✅ GitOps Workflow**:
- Primary changes are UI configuration (Settings in Music Assistant)
- Ingress change follows standard Git workflow (edit → commit → push → Flux reconcile)
- No manual kubectl apply commands needed
- All changes are tracked and reversible

**✅ Security Standards**:
- No secrets exposed (already encrypted with SOPS)
- No new ports opened externally
- Maintains existing ingress TLS configuration
- Uses existing external ingress infrastructure

**✅ Network Architecture**:
- Respects existing VLAN segmentation
- Uses existing external DNS and ingress
- No split-brain DNS needed (keeps DNS simple and predictable)
- LoadBalancer IP is already part of k8s-network VLAN design

## Why Other Approaches Won't Work

### ❌ LoadBalancer IP Approach (Local Network)
**Won't work because**: Echo devices cannot access local network URLs. Amazon's cloud instructs Echo devices to fetch streams, and local IPs like `http://192.168.55.25:8097/` are unreachable from Amazon's infrastructure.

### ❌ Split-Brain DNS Approach
**Won't work because**: Even if `music-stream.secret-domain` resolves to a local IP internally, Echo devices still route through Amazon cloud which uses public DNS. The stream must be externally accessible.

### ✅ External HTTPS Ingress (ONLY Working Approach)
**Why this works**:
- Stream URL (`https://music-stream.secret-domain/flow/...`) is publicly accessible
- Amazon cloud can instruct Echo device to fetch from this URL
- Ingress handles TLS termination and routes to backend
- Stream server only needs to listen internally on port 8097

## What Changed After Research

**Original Plan (WRONG)**:
- Use LoadBalancer IP `192.168.55.25` for stream URLs
- Echo devices would access streams on local network
- Stream ingress was "optional"

**Corrected Plan (BASED ON RESEARCH)**:
- Use external HTTPS domain `music-stream.secret-domain` for stream URLs
- Echo devices **CANNOT** access local network - they route through Amazon cloud
- Stream ingress is **REQUIRED** (not optional)
- Research source: [Amazon Echo TTS Configuration Discussion](https://community.home-assistant.io/t/amazon-echo-devices-to-send-tts-set-public-url-in-integration-configuration/656410)

**Key Research Findings**:
1. **Port fallback**: Music Assistant tries next port if 8097 is occupied ([Docker Port Issues #2056](https://github.com/orgs/music-assistant/discussions/2056))
2. **Published IP configuration**: Required for Kubernetes/non-standard setups ([K8s Discussion #3103](https://github.com/orgs/music-assistant/discussions/3103))
3. **External URL requirement**: Stream must be HTTP accessible (no HTTPS on streamserver) but via external proxy ([System Settings](https://www.music-assistant.io/settings/core/))

## References

- [Music Assistant System Settings - Stream Server](https://www.music-assistant.io/settings/core/)
- [Music Assistant Alexa Player Support](https://www.music-assistant.io/player-support/alexa/)
- [Music Assistant Kubernetes Discussion](https://github.com/orgs/music-assistant/discussions/3103)
- [Docker Setup and Port Issues](https://github.com/orgs/music-assistant/discussions/2056)
- [Amazon Echo TTS Configuration](https://community.home-assistant.io/t/amazon-echo-devices-to-send-tts-set-public-url-in-integration-configuration/656410)
- [Alexa Media Player Discussion](https://github.com/alandtse/alexa_media_player/discussions/2774)
- [Music Assistant Technical Information](https://www.music-assistant.io/faq/tech-info/)
