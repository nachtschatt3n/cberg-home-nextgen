# SOP: MariaDB Major Upgrade (Bitnami chart)

> Description: Taking a Bitnami-chart MariaDB across a server major (12 → 13 and onward) without leaving old-format system tables under a new binary, including the digest-pinning rule the free-tier catalog forces on us.
> Version: `2026.10.23`
> Last Updated: `2026-10-23`
> Owner: `cberg-agent / operator`

## Description

How to take a Bitnami-chart MariaDB across a **server major** (12 → 13 and
onward) without leaving old-format system tables under a new binary. Written
after the `databases/mariadb` 12.2.2 → 13.0.1 upgrade on 2026-08-15, where two
failure modes appeared that no amount of reading the chart would have predicted.

Applies to the **Bitnami-chart** MariaDBs — `databases/mariadb` and
`office/nextcloud` — which run the Bitnami entrypoint and will hit both traps.
**`office/paperless-ngx` is NOT one of them**: `paperless-db` is a plain
Deployment on the Docker Official `mariadb` image and has neither trap; use
"Docker Official image path" below instead.

## Overview

Two things go wrong, and both are silent:

**1. The Bitnami entrypoint ALWAYS skips `mariadb-upgrade`.**
Root cause (read live in the 13.0.1 image, 2026-10-04):
`/opt/bitnami/scripts/libmariadb.sh:538` calls
`"${DB_BIN_DIR}/mariadb_upgrade" … || info "This installation is already upgraded"`,
but `DB_BIN_DIR=/opt/bitnami/mariadb/bin` holds only `mariadb-upgrade`
(hyphen) and the `mysql_upgrade` symlink — there is no `mariadb_upgrade`. The
call fails with not-found and the `||` turns it into the reassuring info line
on EVERY start, so on a server-major roll the upgrade never runs. Run it by
hand (below) on every engine bump; if a future Bitnami build fixes the name,
the manual run is a harmless no-op.
It logged *"This installation is already upgraded"* and moved on. The
HelmRelease reported `Ready=True`, and `SELECT VERSION()` returned the NEW
version — while the datadir marker still recorded the OLD one. That is
12-format system tables being served by a 13 binary. Every signal an operator
would normally trust said success.

**2. `mariadb-upgrade` over the default TLS/TCP loopback resets mid-run.**
It fails with `TLS/SSL error: Connection reset by peer`, half-applies the
privilege-table migration, and emits hundreds of misleading
`server has gone away` errors. The server never crashed. The tell is that two
runs fail at *different* script lines — a bad statement fails in the same place
every time; a transport problem moves around. Use
`--protocol=socket --skip-ssl`.

## Blueprints

N/A.

## Operational Instructions

1. **Confirm what the instance actually holds.** Risk follows the data, not the
   version delta. `SELECT table_schema, COUNT(*) FROM information_schema.tables
   GROUP BY 1;` — a metadata-only instance is a very different upgrade from one
   with user schemas.
2. **Take a logical dump.**
   `mariadb-dump --default-character-set=utf8mb4 --all-databases`. This is the
   only rollback that works: MariaDB majors are **one-way**, there is no
   downgrade. Verify it is non-empty and ends `-- Dump completed`.
   **Chmod it `0600` in a `0700` directory** — the dump contains
   `mysql.global_priv` password hashes.

   **`--default-character-set=utf8mb4` is not optional, and omitting it fails
   silently.** Without it the client negotiates the *server* default, and the
   server default is not the storage encoding. On 2026-08-19 this destroyed a
   Nextcloud migration: `@@character_set_server` and
   `information_schema.schemata` both read `utf8mb3`, while all 206 tables were
   `utf8mb4_bin`. The server transcoded every 4-byte character to `?` on its way
   out, so the dump — the rollback floor — was already corrupt when written.
   **The value that decides this is
   `information_schema.tables.table_collation`, not the server or schema
   default.** Check it before you dump:

   ```bash
   mariadb -N -e "select table_collation, count(*) from information_schema.tables
                  where table_schema='<db>' group by 1;"
   ```

   Then prove the dump round-trips 4-byte data before you trust it:

   ```bash
   # rows whose content is genuinely multi-byte
   mariadb -N -B <db> --default-character-set=utf8mb4 \
     -e "select count(*) from <table> where char_length(<col>) <> octet_length(<col>);"
   # the dump must still contain real 4-byte lead bytes, not '?'
   LC_ALL=C grep -c $'[\xf0-\xf4]' "$DUMP" || echo "NO 4-BYTE SEQUENCES — DUMP IS LOSSY, ABORT"
   ```
3. **Pin the image by digest.** Bitnami has withdrawn semver tags: `bitnami/mariadb`
   publishes 394 tags of which exactly two (`latest`, `latest-metadata`) are not
   digests. `bitnamilegacy` is *behind* current versions and is not a fallback.
   So digest is the only pin available — see Troubleshooting for what that costs.
4. **Bump chart + digest together**, commit, push. Reconcile **Kustomization
   then HelmRelease** — a HelmRelease reconciled first upgrades with stale values
   while reporting Ready.
5. **Check the datadir marker before declaring success** (see Verification). If
   it lags, run the upgrade by hand:
   `mariadb-upgrade --protocol=socket --skip-ssl -uroot -p'…'`
   Expect all 8 phases to complete.

## Docker Official image path (paperless-db)

`office/paperless-ngx` `paperless-db` (`db-deployment.yaml`, image `mariadb:<ver>`,
no chart). Proven twice: 11.8.9 -> 12.3.3, then 12.3.3 -> 13.0.2 (executed
2026-10-21, commit `a99794cc`). The Bitnami traps above do not apply; these do:

1. **`MARIADB_AUTO_UPGRADE=1` must be in the Deployment env.** The official
   entrypoint only runs `mariadb-upgrade` when it is set. With it set, the
   upgrade runs automatically on the FIRST start of the new image, so there is
   **no abort point after the image lands**: the datadir conversion is one-way.
   Do not re-add it if present; check
   `kubectl -n office get deploy paperless-db -o jsonpath='{.spec.template.spec.containers[0].env}'`.
2. **Mandatory pre-bump dump with a fail-closed proof**, taken
   `--default-character-set=utf8mb4`, run under `set -euo pipefail`: exit non-zero
   on a missing `-- Dump completed` trailer, too few `CREATE TABLE`, an
   implausibly small file, a 4-byte lead-byte scan whose **positive control**
   fails, or a dump with zero 4-byte content. Chmod `0600` in a `0700` dir.
3. **utf8mb4 4-byte content proof (canary).** Before the bump record per-table row
   counts, the count of rows holding 4-byte characters (the canary; must be
   greater than 0 or it cannot fail) and the non-utf8mb4 table count (must be 0).
   After: counts identical, canary unchanged, non-utf8mb4 still 0. The server
   args pin `utf8mb4`; losing them regresses to `OperationalError 1366`.
4. **Quiesce the app** (scale `paperless-ngx` to 0; the HelmRelease reconcile does
   NOT restore replicas, scale back explicitly) before rolling the DB.
5. **Watch the conversion:** logs must show `Major version upgrade detected` and
   phases 1-8. `MariaDB upgrade not required` on a first start of a new major
   means the datadir was NOT converted: run
   `mariadb-upgrade --protocol=socket --skip-ssl -uroot -p"$MARIADB_ROOT_PASSWORD"`
   by hand (the TLS loopback reset also applies here).
6. **Rollback is restore-from-dump** (or Longhorn backup), never a git revert:
   a downgraded image refuses the converted datadir. Restore with
   `--default-character-set=utf8mb4` on the way in as well.

Plan files: `runbooks/maintenance/plans/paperless-db-13.0.2.md` holds the full
step-by-step scripts (§3.2 dump proof, §3.3 baselines, §4 assertions).

## Examples

```bash
# Pre-flight: what is actually in here?
kubectl -n <ns> exec <pod> -- mariadb -uroot -p"$PW" -N \
  -e "SELECT table_schema, COUNT(*) FROM information_schema.tables GROUP BY 1;"

# The upgrade invocation that works (socket, no TLS)
kubectl -n <ns> exec <pod> -- mariadb-upgrade --protocol=socket --skip-ssl -uroot -p"$PW"
```

## Verification Tests

Version alone is **not** sufficient — it was the misleading signal:

```bash
SELECT VERSION();                                   # necessary, not sufficient
cat /bitnami/mariadb/data/mariadb_upgrade_info      # must show the NEW version (Bitnami file name; NOT mysql_upgrade_info)
mariadb-check --protocol=socket --all-databases -uroot -p"$PW"   # expect all OK
```

Then confirm a *dependent application* still works — for this cluster that
means phpMyAdmin connects, or Nextcloud/Paperless serve. A database that starts
but that its app cannot use is the failure worth catching.

Compare against the pre-upgrade baseline: same schema count, same table counts,
same user count. `sys` gaining a view or two is normal — MariaDB rebuilds its
own diagnostic schema in upgrade phase 4.

**Counts cannot detect encoding loss, so they are necessary and not
sufficient.** A dump taken over the wrong connection charset restores the right
number of rows into the right number of tables with the right collations, and
every count matches — while the *contents* of those rows have been flattened.
Add a byte-for-byte spot-check of known 4-byte content, source vs target:

```bash
select count(*) from <table> where char_length(<col>) <> octet_length(<col>);
select hex(<col>) from <table> where char_length(<col>) <> octet_length(<col>) limit 5;
```

The two sides must agree on both. See step 2, and
`docs/sops/verification-contents-not-shape.md`.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Ready=True`, correct `VERSION()`, but stale datadir marker | entrypoint skipped `mariadb-upgrade` | run it by hand over the socket |
| `TLS/SSL error: Connection reset by peer`, hundreds of `server has gone away` | TLS/TCP loopback transport, **not** a crashed server | `--protocol=socket --skip-ssl` |
| Two runs fail at *different* lines | transport, not a bad statement | as above |
| `ImagePullBackOff` after a reschedule | digest pin went untagged when `latest` rolled | mirror the image, or move to the official upstream `mariadb` image |

## Diagnose Examples

```bash
kubectl -n <ns> logs <pod> | grep -iE 'upgrade|already upgraded'
kubectl -n <ns> exec <pod> -- ls -la /bitnami/mariadb/data/mariadb_upgrade_info
```

## Health Check

Pod 1/1 with no restart loop; `mariadb-check --all-databases` all-OK; the
consuming app serving; Longhorn volume healthy with its reclaim policy intact.

Consumers during the bounce (F-9ab5f80f): a tenant may restart **once** while
`mariadb-0` is down -- gate on <= 1 restart per consumer and Ready after the
bounce, not on zero. Build any processlist tenant baseline from persistent-pool
(Rails) users only; the PHP showcase tenants connect per request and are absent
between requests. Showcase Rails liveness is `tcpSocket` since `f515915c`, so a
restart there now indicates a real fault. See `docs/sops/maintenance-windows.md`
§7 "Plan-authoring lessons (2026-10-04)".

## Security Check

Dumps are `0600` in a `0700` directory and are **not** committed. The digest pin
freezes patching, so it needs an accepted-risk entry with a review date —
Renovate's `helm-values` manager needs an `image.tag` and matches nothing on a
`digest:`-only block, so no tooling will ever surface drift on it.

## Rollback Plan

There is **no in-place downgrade**. Rollback is: scale to 0, restore the
pre-upgrade dump into a fresh datadir on the previous image, scale up. This is
why step 2 is not optional. Reverting the manifest alone gets you the old binary
pointed at an upgraded datadir, which is worse than doing nothing.
