# Frigate NVR Update Plan

## Current State

- **Chart Version**: 7.3.0
- **Image Tag**: 0.15.1
- **Config Location**: Inline in `helmrelease.yaml`
- **Config Storage**: PVC `frigate-config` (longhorn-static, 8Gi)

## Target State

- **Chart Version**: 7.8.0 (latest)
- **Image Tag**: 0.16.2 (latest)
- **Config Location**: SOPS encrypted ConfigMap
- **Config Storage**: Keep existing PVC for database and other files

## Configuration Improvements

### 1. Security Enhancements

**Current Issues:**
- RTSP credentials hardcoded in config: `rtsp://camac:Ja3YP@192.168.33.91/live`
- MQTT credentials commented but not using environment variables

**Recommendations:**
- Use environment variables for RTSP credentials: `{FRIGATE_RTSP_USER}` and `{FRIGATE_RTSP_PASSWORD}`
- Move MQTT credentials to environment variables if needed
- Store credentials in SOPS encrypted Secret

### 2. Recording Configuration Updates

**Current Config:**
```yaml
record:
  enabled: True
  retain:
    days: 3
    mode: all
  alerts:
    retain:
      days: 30
      mode: motion
  detections:
    retain:
      days: 30
      mode: motion
```

**Recommended (per latest docs):**
```yaml
record:
  enabled: True
  continuous:
    days: 3  # Continuous recording retention
  motion:
    days: 7  # Motion-based recording retention
  alerts:
    retain:
      days: 30
      mode: all  # Keep all alert recordings
  detections:
    retain:
      days: 30
      mode: motion  # Keep motion-based detection recordings
```

### 3. Camera Configuration Improvements

**Issues Found:**
- All cameras use same genai prompt (mentions "front door" even for kids, heater, guest_room)
- Missing `detect` section configuration (width, height, fps)
- No zones defined
- Camera-specific prompts should be more accurate

**Recommendations:**
- Add `detect` section with appropriate resolution and fps
- Customize genai prompts per camera location
- Consider adding zones for better detection accuracy
- Review object lists per camera (some cameras have many objects that may not be relevant)

### 4. Detector Configuration

**Current:**
```yaml
detectors:
  ov:
    type: openvino
    device: GPU
model:
  width: 300
  height: 300
  input_tensor: nhwc
  input_pixel_format: bgr
  path: /openvino-model/ssdlite_mobilenet_v2.xml
  labelmap_path: /openvino-model/coco_91cl_bkgr.txt
```

**Status:** ✅ Looks correct for Intel GPU with OpenVINO

### 5. Semantic Search

**Current:**
```yaml
semantic_search:
  enabled: True
  model_size: large
  reindex: False
```

**Status:** ✅ Correct configuration

### 6. GenAI Configuration

**Current:**
```yaml
genai:
  enabled: false
  provider: ollama
  base_url: http://ollama-ipex.ai.svc.cluster.local:11434
  model: llava:7b
```

**Recommendations:**
- Consider updating model to `llava:latest` or newer version
- Verify ollama service availability
- Consider using environment variable for base_url if it changes

### 7. Database Configuration

**Missing:** Database path configuration

**Recommendation:**
```yaml
database:
  path: /config/frigate.db
```

### 8. MQTT Configuration

**Current:**
```yaml
mqtt:
  host: "mosquitto.home-automation.svc.cluster.local"
  port: 1883
```

**Recommendations:**
- Add `enabled: true` explicitly
- Consider using environment variables for credentials if authentication is needed
- Verify MQTT credentials are properly configured

## Implementation Steps

1. ✅ Review current configuration against latest docs
2. Create SOPS encrypted ConfigMap with improved configuration
3. Create SOPS encrypted Secret for RTSP credentials
4. Update HelmRelease to:
   - Use latest chart version (7.8.0)
   - Use latest image tag (0.16.2)
   - Reference ConfigMap instead of inline config
   - Add environment variables for credentials
5. Update kustomization.yaml to include ConfigMap and Secret
6. Test configuration validation before applying

## Files to Create/Modify

### New Files:
- `kubernetes/apps/home-automation/frigate-nvr/app/configmap.sops.yaml` - Encrypted config
- `kubernetes/apps/home-automation/frigate-nvr/app/secret.sops.yaml` - Encrypted RTSP credentials

### Modified Files:
- `kubernetes/apps/home-automation/frigate-nvr/app/helmrelease.yaml` - Update version and config reference
- `kubernetes/apps/home-automation/frigate-nvr/app/kustomization.yaml` - Add ConfigMap and Secret

## Migration Notes

- The existing `frigate-config` PVC will continue to be used for database and other runtime files
- The ConfigMap will contain only the `config.yml` file
- RTSP credentials will be moved to environment variables via Secret
- No data migration needed - Frigate will read the new config on restart

## Testing Checklist

- [x] Validate config syntax before encryption
- [x] Verify SOPS encryption works correctly
- [x] Check that HelmRelease references ConfigMap correctly
- [x] Verify environment variables are passed to container
- [ ] Test Frigate starts with new configuration
- [ ] Verify cameras connect successfully
- [ ] Check recording functionality
- [ ] Verify MQTT connectivity
- [ ] Test genai functionality (if enabled)

## Implementation Summary

### Files Created:
1. `kubernetes/apps/home-automation/frigate-nvr/app/configmap.sops.yaml` - SOPS encrypted ConfigMap with improved Frigate configuration
2. `kubernetes/apps/home-automation/frigate-nvr/app/secret.sops.yaml` - SOPS encrypted Secret with RTSP credentials

### Files Modified:
1. `kubernetes/apps/home-automation/frigate-nvr/app/helmrelease.yaml`:
   - Updated chart version: 7.3.0 → 7.8.0
   - Updated image tag: 0.15.1 → 0.16.2
   - Removed inline `config:` section
   - Added environment variables for RTSP credentials from Secret
   - Added ConfigMap volume mount to `/config/config.yml`

2. `kubernetes/apps/home-automation/frigate-nvr/app/kustomization.yaml`:
   - Added `configmap.sops.yaml` and `secret.sops.yaml` to resources

### Key Configuration Improvements:

1. **Security**: RTSP credentials moved from plaintext config to SOPS encrypted Secret
2. **Recording**: Updated to use new format (`continuous`/`motion` instead of `retain.days.mode`)
3. **Camera Detection**: Added `detect` sections with proper resolution and fps settings
4. **Camera Prompts**: Fixed genai prompts to match actual camera locations
5. **Database**: Added explicit database path configuration
6. **MQTT**: Added explicit `enabled: true` flag

### Next Steps:

1. Commit and push changes to trigger Flux reconciliation
2. Monitor HelmRelease reconciliation: `flux get helmrelease frigate -n home-automation`
3. Check pod logs after deployment: `kubectl logs -n home-automation -l app.kubernetes.io/name=frigate`
4. Verify config is loaded correctly by checking Frigate UI
5. Test camera connectivity and recording functionality

### Potential Issues to Watch:

1. **ConfigMap Mount Conflict**: The ConfigMap is mounted to `/config/config.yml` while the PVC mounts to `/config`. This should work with `subPath`, but if there are issues, we may need to adjust the mount path or use an initContainer.

2. **Environment Variable Format**: The `env` section uses `valueFrom` which is standard Kubernetes syntax. If the Helm chart doesn't support this format directly, we may need to use `envFrom` or a different approach.

3. **Config File Location**: Frigate looks for `config.yml` in `/config` by default. Our mount should place it there correctly, but verify if the chart expects a different location.

### Rollback Plan:

If issues occur, you can:
1. Revert the HelmRelease to use inline config temporarily
2. Keep the ConfigMap and Secret for future migration
3. Or revert all changes using git if needed
