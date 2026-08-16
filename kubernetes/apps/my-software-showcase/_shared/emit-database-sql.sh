#!/usr/bin/env bash
# Emit the CREATE DATABASE / CREATE USER / GRANT statements for the showcase apps.
#
# Reads the credentials back out of the SOPS-encrypted per-app secrets, so the
# passwords exist in exactly one place (the encrypted files) and are never
# committed in plaintext. Requires the cluster age key.
#
#   ./emit-database-sql.sh | mysql -h <mariadb-host> -u root -p
#
# Key names differ per app (DB_USERNAME/DB_DATABASE vs DB_USER/DB_NAME vs
# DATABASE_*) because each app's config/database.yml differs; this reads
# whichever pair is present.
set -euo pipefail
cd "$(dirname "$0")/.."
for f in */app/secret.sops.yaml; do
  [ -f "$f" ] || continue
  d=$(sops -d "$f" 2>/dev/null) || { echo "-- skip $f (cannot decrypt)" >&2; continue; }
  # sops strips quotes from non-numeric scalars on decrypt, so accept both forms
  get() { echo "$d" | sed -n "s/^  $1: *\"\\?\\([^\"]*\\)\"\\?$/\\1/p"; }
  user=$(get DB_USERNAME); [ -z "$user" ] && user=$(get DB_USER)
  [ -z "$user" ] && user=$(get DATABASE_USER)
  name=$(get DB_DATABASE); [ -z "$name" ] && name=$(get DB_NAME)
  [ -z "$name" ] && name=$(get DATABASE_NAME)
  pass=$(get DB_PASSWORD); [ -z "$pass" ] && pass=$(get DATABASE_PASSWORD)
  [ -z "$user$name$pass" ] && continue
  echo "CREATE DATABASE IF NOT EXISTS \`$name\` CHARACTER SET utf8 COLLATE utf8_general_ci;"
  echo "CREATE USER IF NOT EXISTS '$user'@'%' IDENTIFIED BY '$pass';"
  echo "GRANT ALL PRIVILEGES ON \`$name\`.* TO '$user'@'%';"
done
echo "FLUSH PRIVILEGES;"
