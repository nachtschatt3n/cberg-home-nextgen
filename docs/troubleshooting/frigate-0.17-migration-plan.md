# Frigate 0.16.4 → 0.17.0 Migration Plan

> Active migration plan. Delete this file after successful upgrade.
> Created: 2026-03-01

---

## Breaking Changes vs Current Config Audit

Frigate 0.17.0 has 6 documented breaking changes. Here is the status of each against the live config in `configmap.sops.yaml`.

### 1. GenAI config restructured — ⚠️ AFFECTED (5 cameras)

**Change:** Camera-level `genai:` blocks move from directly under the camera to under `camera.objects.genai`.

**Current (0.16.x):**
```yaml
cameras:
  entry:
    genai:
      enabled: true
      use_snapshot: false
      prompt: "..."
      object_prompts: {...}
      objects: [person, ...]
```

**Required (0.17.0):**
```yaml
cameras:
  entry:
    objects:
      genai:
        enabled: true
        use_snapshot: false
        prompt: "..."
        object_prompts: {...}
        objects: [person, ...]
```

**Affected cameras:** `kids`, `entry`, `heater`, `living_room`, `kitchen`
(`guest_room` has no genai block — not affected)

The global `genai:` block (provider/api_key/model) stays at the top level and is not affected.

---

### 2. Recordings retention tiered — ⚠️ VERIFY REQUIRED

**Change:** `record.retain.continuous` and `record.retain.motion` are now separate named tiers replacing `record.retain.mode`.

**Current:**
```yaml
record:
  retain:
    days: 3
    mode: all
```

**Likely required (0.17.0):**
```yaml
record:
  retain:
    days: 3        # kept for alerts/detections default
    mode: all      # check if still valid or replaced by tier names
```

> ⚠️ Verify the exact new syntax in the [0.17.0 release notes](https://github.com/blakeblackshear/frigate/releases/tag/0.17.0) before applying. The `alerts` and `detections` sub-keys appear unchanged.

---

### 3. LPR models updated — ✅ NOT AFFECTED

Current config has no LPR (`license_plate_recognition`) section. No action needed.

---

### 4. `strftime_fmt` removed — ✅ NOT AFFECTED

Current config does not use `strftime_fmt`. No action needed.

---

### 5. Camera resolution auto-detection changed — ✅ NOT AFFECTED

All 6 cameras already have explicit `detect.width` and `detect.height`. No action needed.

---

### 6. go2rtc exec/expr/echo sources removed — ✅ NOT AFFECTED

All cameras use RTSP inputs only (`preset-rtsp-udp`, `preset-rtsp-generic`). No exec/expr/echo sources configured. No action needed.

---

## Config Changes Required

Edit `kubernetes/apps/home-automation/frigate-nvr/app/configmap.sops.yaml`.

### Change A: Move camera-level genai blocks (all 5 affected cameras)

For each affected camera, move the `genai:` block to be nested under `objects:`.

**kids** (genai disabled — still needs to move for schema compliance):
```yaml
# Before
    kids:
      genai:
        enabled: false
        ...

# After
    kids:
      objects:
        genai:
          enabled: false
          ...
```

**entry** (genai enabled):
```yaml
# Before
    entry:
      genai:
        enabled: true
        use_snapshot: false
        prompt: "Analyze the {label}..."
        object_prompts:
          person: "Examine the person..."
        objects: [person, bicycle, bird, ...]

# After
    entry:
      objects:
        genai:
          enabled: true
          use_snapshot: false
          prompt: "Analyze the {label}..."
          object_prompts:
            person: "Examine the person..."
          objects: [person, bicycle, bird, ...]
```

Apply the same pattern to **heater**, **living_room**, **kitchen**.

### Change B: Verify record retention syntax

After reading the 0.17.0 release notes, update the `record.retain` block if the `mode: all` syntax has changed. Current `alerts` and `detections` sub-keys are likely unchanged.

---

## Pre-Upgrade Checklist

- [ ] Read full [0.17.0 release notes](https://github.com/blakeblackshear/frigate/releases/tag/0.17.0) — confirm no additional breaking changes
- [ ] Verify `record.retain.mode` exact new syntax
- [ ] Back up `frigate.db` from the `frigate-config` PVC
- [ ] Note current recording retention settings so you can verify post-upgrade

```bash
# Check current DB size and location
kubectl exec -n home-automation deployment/frigate -- ls -lh /config/frigate.db

# Optional: copy db backup to local machine before upgrade
kubectl cp home-automation/$(kubectl get pod -n home-automation -l app.kubernetes.io/name=frigate -o jsonpath='{.items[0].metadata.name}'):/config/frigate.db /tmp/frigate-backup-$(date +%Y%m%d).db
```

---

## Upgrade Steps

1. **Apply config changes** — edit `configmap.sops.yaml` with the genai restructure and any record retention changes:
   ```bash
   sops kubernetes/apps/home-automation/frigate-nvr/app/configmap.sops.yaml
   ```

2. **Update image tag** in `helmrelease.yaml`:
   ```yaml
   image:
     tag: 0.17.0
   ```

3. **Commit and push** — Flux will apply the ConfigMap update and trigger a pod restart:
   ```bash
   git add kubernetes/apps/home-automation/frigate-nvr/app/configmap.sops.yaml \
           kubernetes/apps/home-automation/frigate-nvr/app/helmrelease.yaml
   git commit -m "chore(frigate): upgrade 0.16.4 → 0.17.0 with breaking config changes"
   git push
   ```

4. **Monitor pod startup** — the most likely failure point is the new image rejecting the old config:
   ```bash
   kubectl logs -n home-automation -l app.kubernetes.io/name=frigate -f
   ```

   Watch for: config validation errors, camera detection hangs (see Breaking Change 5 note — if a camera hangs, add explicit `detect.width`/`detect.height`).

5. **Verify cameras** — check all 6 cameras detect and record:
   ```bash
   # Check pod is Running
   kubectl get pods -n home-automation -l app.kubernetes.io/name=frigate

   # Check Frigate config loaded cleanly
   kubectl logs -n home-automation -l app.kubernetes.io/name=frigate | grep -i "config\|error\|warn" | head -30
   ```

---

## Rollback

If the upgrade fails, revert the image tag commit:

```bash
git revert HEAD  # or git revert <commit-sha>
git push
```

Flux will restore 0.16.4. The `frigate.db` is on the PVC and unaffected by a pod restart — no data loss.

---

## Verification After Upgrade

- [ ] All 6 cameras show live feed in Frigate UI
- [ ] Detection is working (person, objects appear on timeline)
- [ ] GenAI analysis triggers on `entry`, `heater`, `kitchen` cameras
- [ ] Recordings are being saved and retention is applying correctly
- [ ] No error-level log messages in pod logs
- [ ] Home Assistant still receiving Frigate MQTT events

```bash
# Quick health check post-upgrade
kubectl logs -n home-automation -l app.kubernetes.io/name=frigate --tail=50 | grep -i "error\|fatal\|exception"
```
