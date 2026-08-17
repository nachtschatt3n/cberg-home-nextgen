#!/usr/bin/env bash
# Emit the CREATE DATABASE / CREATE USER / GRANT statements for the showcase apps.
#
# Reads the credentials back out of the SOPS-encrypted per-app secrets, so the
# passwords exist in exactly one place (the encrypted files) and are never
# committed in plaintext. Requires the cluster age key.
#
#   ./runbooks/emit-showcase-database-sql.sh | mysql -h <mariadb-host> -u root -p
#
# Run from anywhere; it resolves the showcase app tree relative to the repo root.
# Deliberately an operator-run script and NOT a Flux Job: creating the databases
# needs MariaDB ROOT credentials, and a Job in my-software-showcase would have to
# mount those into an app namespace. One-shot bootstrap for EOL snapshots does not
# justify putting DB root credentials there.
#
# Key names differ per app (DB_USERNAME/DB_DATABASE vs DB_USER/DB_NAME vs
# DATABASE_*) because each app's config/database.yml differs; this reads
# whichever pair is present.
set -euo pipefail
cd "$(dirname "$0")/../kubernetes/apps/my-software-showcase"
for f in */app/secret.sops.yaml; do
  [ -f "$f" ] || continue
  d=$(sops -d "$f" 2>/dev/null) || { echo "-- skip $f (cannot decrypt)" >&2; continue; }
  # sops strips quotes from non-numeric scalars on decrypt, so accept both forms
  # \{0,1\} not \? — GNU sed's \? is a literal '?' on the macOS/BSD sed this
  # operator-run script actually executes under (silent 0-database emission).
  get() { echo "$d" | sed -n "s/^  $1: *\"\{0,1\}\([^\"]*\)\"\{0,1\}$/\1/p"; }
  user=$(get DB_USERNAME); [ -z "$user" ] && user=$(get DB_USER)
  [ -z "$user" ] && user=$(get DATABASE_USER)
  name=$(get DB_DATABASE); [ -z "$name" ] && name=$(get DB_NAME)
  [ -z "$name" ] && name=$(get DATABASE_NAME)
  # DB_PASS is the PHP tier's key name (ibgastro, globalmobility, uzeit-de).
  # Omitting it created those three users with an EMPTY password: the app could
  # not authenticate, and anything else in the cluster could. Refuse rather than
  # emit a passwordless CREATE USER.
  pass=$(get DB_PASSWORD); [ -z "$pass" ] && pass=$(get DATABASE_PASSWORD)
  [ -z "$pass" ] && pass=$(get DB_PASS)
  if [ -z "$pass" ]; then
    echo "-- REFUSING ${name:-unknown}: no password key found in $f" >&2
    continue
  fi
  [ -z "$user$name$pass" ] && continue
  # utf8mb3, not utf8mb4: these are Rails 3.2 / TYPO3 4.2-era schemas whose
  # index definitions predate the 767-byte prefix limit that utf8mb4 trips.
  # None was boot-tested against utf8mb4, so do not opt them into it blindly.
  echo "CREATE DATABASE IF NOT EXISTS \`$name\` CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci;"
  echo "CREATE USER IF NOT EXISTS '$user'@'%' IDENTIFIED BY '$pass';"
  # '%' rather than a host/IP: pod IPs are ephemeral.
  echo "GRANT ALL PRIVILEGES ON \`$name\`.* TO '$user'@'%';"
done
echo "FLUSH PRIVILEGES;"
# The target is MariaDB, not MySQL 5.7. These apps predate STRICT_TRANS_TABLES
# and will reject rows MariaDB's default sql_mode would refuse. Set this
# server-side (or per-app via the connection) before loading any schema:
echo "-- Operator note: these apps need a relaxed sql_mode, e.g."
echo "-- SET GLOBAL sql_mode = 'NO_ENGINE_SUBSTITUTION';"
