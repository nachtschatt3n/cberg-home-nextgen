# Longhorn Name Migration — Pending UUID PVs

Auto-updated by compliance check. These PVs use dynamic `longhorn` provisioning and have UUID-generated names (`pvc-*`). Per policy, UUID names are **acceptable** for dynamic `longhorn` class PVs (dynamic provisioning by design). This list is maintained for auditability.

**Policy reminder:** Only `longhorn-static` PVs must have clean/meaningful names. UUID names on `longhorn` (dynamic) class are expected and correct.

Last updated: 2026-03-28

## Current UUID PVs (Dynamic Longhorn — Expected)

| PV Name | Namespace | Claim |
|---------|-----------|-------|
| pvc-07220c82-2c71-4a3a-ae8c-a04e558d0f21 | my-software-production | absenty-storage |
| pvc-1cb9f072-fe84-469e-8a70-2abddd844e02 | home-automation | traccar-postgres-data |
| pvc-27866fc8-77df-4fe6-8397-e69f3fa0fa7d | office | affine-pg-data |
| pvc-415b27a4-1e87-43c0-9a5f-86af6a7d06ae | ai | librechat-meilisearch |
| pvc-4b686821-bd3d-450a-a22b-cda964a16d35 | office | affine-storage |
| pvc-5182e7fc-2993-43a1-b64d-e5aa1edea8d2 | my-software-development | absenty-bundle |
| pvc-626c58f8-d889-4bda-9056-a8509ce202d4 | home-automation | matter-server-data |
| pvc-629cc62f-96ea-497c-bd4b-954613a135a6 | ai | librechat-librechat-images |
| pvc-77167e86-f960-4f51-8ec1-c79c82684b06 | databases | redis-data |
| pvc-773cc06e-4984-4bcf-ae38-64fe77f68a5c | ai | paperclip-postgresql-data |
| pvc-a545f6e7-2134-4b43-98b5-f0e8a3c1fe69 | databases | redisinsight-data |
| pvc-af6e749e-1ca8-433b-8a10-f3cc5b41ed53 | my-software-development | absenty-storage |
| pvc-b2d0193f-4a12-4b38-95c2-66283163cbe0 | monitoring | elasticsearch-data-elasticsearch-es-default-0 |
| pvc-b32f29a6-e7d3-49d7-879a-5c3808c6dadf | ai | anythingllm-storage-claim |
| pvc-bd13d22f-9885-4d47-958e-07507a06d6ac | home-automation | scrypted-data |
| pvc-c0e52c2a-91b1-4f72-ac57-cc1f5719fe41 | my-software-production | absenty-data |
| pvc-c6b7afbb-afa4-4222-abca-82098015cfa5 | office | affine-config |
| pvc-cb151bc0-c164-4e35-a287-58a78b859ebb | ai | librechat-mongodb |
| pvc-cdbd0a10-fa71-43f7-a442-00b4d7f99808 | ai | paperclip-data |
| pvc-e230506d-5f62-41cd-88b0-7ddcab0e90d8 | home-automation | trmnl-ha-data |
| pvc-fdc34672-c53a-41fe-a2d3-21125d0cac72 | my-software-development | absenty-data |

## Policy

These do NOT require migration. Dynamic PVs on `longhorn` class intentionally use UUID names.
Migration is only required for `longhorn-static` PVs that incorrectly use UUID names (currently: none).

See `runbooks/longhorn-name-migration.md` for the migration procedure if ever needed.
