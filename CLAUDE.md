- we only use the main branch and no PRs

## Longhorn Storage Standards

### Storage Class Usage
- **longhorn** (dynamic provisioning): Use for application data, databases, and growing volumes
  - PVC names: Clean and descriptive (e.g., `postgres-data`, `redis-cache`)
  - PV names: Auto-generated UUIDs (e.g., `pvc-df1999c2-...`) - THIS IS NORMAL AND EXPECTED
  - Best for: StatefulSet volumes, application databases, data that grows over time

- **longhorn-static**: Use ONLY for configuration directories and manually managed volumes
  - PVC names: Match application (e.g., `home-assistant-config`)
  - PV names: Clean names matching PVC
  - Requires pre-existing Longhorn volume
  - Best for: Fixed-size config directories, volumes needing manual control

### Important: UUID PV Names Are Normal
- When using `longhorn` storage class, PV names will be UUIDs like `pvc-4b56f40c-...`
- This is **standard Kubernetes behavior**, not a misconfiguration
- Do NOT attempt to migrate these to clean names - it's costly, risky, and unnecessary
- PVC names are what users interact with - those should be clean
- See `/docs/migration/pv-pvc-migration-lessons-learned.md` for detailed explanation

### PV/PVC Migration Warning
- **DO NOT** attempt to migrate existing dynamically provisioned volumes to longhorn-static
- Migration requires:
  - Application downtime (30-45 min per volume)
  - Complex Longhorn volume pre-creation
  - Data migration with risk of data loss
  - Manual cleanup
- Cost-benefit analysis: Purely cosmetic, not worth the effort/risk
- Only migrate if volume is truly static config data

### Storage Naming Convention
For new deployments:
- PVC naming: `{app-name}-{purpose}` (e.g., `langfuse-postgresql-data`, `bytebot-cache`)
- Storage class selection:
  - Application data → `longhorn` (accept UUID PVs)
  - Config directories → `longhorn-static` (clean PVs)
- Never mix concerns: one PVC per purpose (data, config, cache, logs separately)