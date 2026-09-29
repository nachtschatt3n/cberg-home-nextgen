#!/usr/bin/env bash
# Seed / re-converge Stalwart's datastore config with stalwart-cli apply.
#
# Why this is not a Flux Job: in v0.16 an account password is a plain `secret`
# string on the Account object (it cannot reference an env var), so a Job
# would need the mailbox password in a ConfigMap. Run this from the operator
# Mac instead; see docs/sops/stalwart.md.
#
# Prereqs: mise env of this repo, stalwart-cli >= 1.0.13 on PATH (or
# STALWART_CLI=/path/to/stalwart-cli), and a port-forward:
#   mise exec -- kubectl port-forward -n office svc/stalwart 18080:8080
#
# Usage: ./apply-bootstrap.sh [--dry-run]
set -euo pipefail

repo="$(cd "$(dirname "$0")/../../../../.." && pwd)"
here="$repo/kubernetes/apps/office/stalwart/bootstrap"
secret="$repo/kubernetes/apps/office/stalwart/app/secret.sops.yaml"
cluster_secrets="$repo/kubernetes/flux/components/common/cluster-secrets.sops.yaml"
cli="${STALWART_CLI:-stalwart-cli}"

sops_get() {
    mise exec -- sops -d --extract "[\"stringData\"][\"$2\"]" "$1"
}

domain="$(sops_get "$cluster_secrets" SECRET_DOMAIN)"
[ -n "$domain" ] || { echo "SECRET_DOMAIN is empty" >&2; exit 1; }

export STALWART_URL="${STALWART_URL:-http://127.0.0.1:18080}"
export STALWART_USER="$(sops_get "$secret" RECOVERY_ADMIN_USER)"
export STALWART_PASSWORD="$(sops_get "$secret" RECOVERY_ADMIN_PASSWORD)"
mailbox_pw="$(sops_get "$secret" MATHIAS_PASSWORD)"

plan="$(mktemp "${TMPDIR:-/tmp}/stalwart-plan.XXXXXX")"
trap 'rm -f "$plan"' EXIT
chmod 600 "$plan"

sed "s/@DOMAIN@/$domain/g" "$here/plan.ndjson.tmpl" > "$plan"
# Certificate has no client-settable natural key (its SANs are server-set),
# so it cannot be upserted: create it on the first run only, and on re-runs
# point SystemSettings at the existing object's id instead.
# `query --json` prints NDJSON, one object per line.
cert_id="$("$cli" query Certificate --json --fields id | python3 -c 'import json,sys
rows=[json.loads(l) for l in sys.stdin if l.strip()]
print(rows[0]["id"] if rows else "")')"
if [ -n "$cert_id" ]; then
    python3 - "$plan" "$cert_id" <<'PY'
import sys
path, cid = sys.argv[1], sys.argv[2]
lines = [l for l in open(path).read().splitlines() if '"object":"Certificate"' not in l]
open(path, "w").write("\n".join(l.replace('"#cert-mail"', '"%s"' % cid) for l in lines) + "\n")
PY
fi

# The operator mailbox. Upsert matches on name, so a re-run resets the
# password to the SOPS value (that is the intended source of truth).
MAILBOX_PW="$mailbox_pw" python3 - "$plan" <<'PY'
import json, os, sys
op = {"@type": "upsert", "object": "Account", "matchOn": ["name"],
      "value": {"acc-mathias": {"@type": "User", "name": "mathias",
                "domainId": "#dom-main",
                "credentials": {"0": {"@type": "Password",
                                      "secret": os.environ["MAILBOX_PW"]}}}}}
lines = open(sys.argv[1]).read().splitlines()
# Account must come after the Domain it references, before the singletons.
idx = next(i for i, l in enumerate(lines) if '"object":"SystemSettings"' in l)
lines.insert(idx, json.dumps(op))
open(sys.argv[1], "w").write("\n".join(lines) + "\n")
PY

"$cli" apply --file "$plan" "$@"
