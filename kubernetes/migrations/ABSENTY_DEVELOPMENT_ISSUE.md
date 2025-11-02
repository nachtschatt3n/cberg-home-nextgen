# absenty-development Issue

## Problem
The absenty-development pod crashes on startup with "bundler: command not found: rails"

## Root Cause
The development container image (`ghcr.io/nachtschatt3n/absenty:sha-ff3910e-dev`) is missing pre-installed Ruby gems, unlike the production image which has them.

## Migration Status
- ✅ Data migration successful (147MB on /data, 228MB on /storage)
- ✅ Volumes using correct PVCs: `absenty-development-data-new`, `absenty-development-storage-new`
- ❌ Application not starting due to image issue

## Attempted Fixes
1. Adding `bundle install` to startup command - times out before completing
2. Increasing startup probe to 18 minutes - still times out
3. Using emptyDir for bundle cache - doesn't persist across restarts
4. Created PVC for bundle cache - helps but install still too slow
5. Using initContainer - in progress

## Proper Solution
Rebuild the development container image with gems pre-installed:

```dockerfile
# Add to Dockerfile after COPY Gemfile
COPY Gemfile* ./
RUN bundle config set --local path '/usr/local/bundle' && \
    bundle install && \
    bundle clean
```

This matches how the production image is built and will eliminate the need for runtime gem installation.

## Workaround
For now, absenty-development is scaled to 0 replicas. The production instance (`absenty-production`) is working correctly.

## Files Modified
- `kubernetes/apps/custom-code-production/absenty-development/app/helmrelease.yaml` - Multiple fixes attempted
- Created PVC: `absenty-development-bundle` (2Gi) for gem cache

## Next Steps
1. Fix the container image build process
2. Update image tag in HelmRelease
3. Remove workarounds (initContainer, bundle PVC, modified command)
4. Scale back to 1 replica
