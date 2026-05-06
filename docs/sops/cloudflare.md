# SOP: Cloudflare Zone Management

> Description: Spec-driven management of Cloudflare zone settings via Terraform with Kubernetes state backend. Covers how to change zone settings, manage bot protection, and detect configuration drift.
> Version: `2026.05.06`
> Last Updated: `2026-05-06`
> Owner: `homelab`

---

## 1) Description

All Cloudflare zone settings are managed as code using Terraform. The state is stored as a Kubernetes Secret in the `flux-system` namespace — no third-party backends, accessible from any machine on the LAN with a kubeconfig.

- Scope: Cloudflare zone settings, bot management
- Prerequisites: SOPS age key at `~/.config/sops/age/keys.txt`, kubeconfig at repo root, `terraform` via mise
- Out of scope: DNS records (owned by external-dns via Flux — **do not add `cloudflare_record` resources here**), page rules, workers

---

## 2) Overview

| Setting | Value |
|---------|-------|
| Terraform root | `terraform/cloudflare/` |
| State backend | Kubernetes Secret `tfstate-default-cloudflare-tfstate` in `flux-system` |
| Token source | `kubernetes/apps/network/external/cloudflared/cf-security-audit-token.sops.yaml` |
| Zone ID source | Resolved at runtime via CF API from `SECRET_DOMAIN` in cluster-secrets |
| Wrapper script | `terraform/cloudflare/tf` (use instead of `terraform` directly) |

### Current managed settings

| Resource | Setting | Value |
|----------|---------|-------|
| `cloudflare_zone_setting.ssl` | SSL mode | `full` |
| `cloudflare_zone_setting.min_tls_version` | Min TLS | `1.2` |
| `cloudflare_zone_setting.always_use_https` | Always HTTPS | `on` |
| `cloudflare_zone_setting.security_header` | HSTS | `max_age=31536000, nosniff=true` |
| `cloudflare_bot_management.main` | Bot Fight Mode | `true` |
| `cloudflare_bot_management.main` | Block AI Bots | `block` |

### Settings NOT managed by Terraform

These settings return 403 when written via the CF API on the free plan. They are at their correct values in the dashboard and verified by the security runbook (§12.6c):

`http2`, `http3`, `ipv6`, `brotli`, `websockets`, `browser_check`, `email_obfuscation`, `0rtt`, `tls_1_3`, `opportunistic_encryption`, `security_level`

---

## 3) Blueprints

- Terraform source: `terraform/cloudflare/`
- Token (SOPS): `kubernetes/apps/network/external/cloudflared/cf-security-audit-token.sops.yaml`
- State secret: `kubectl get secret -n flux-system tfstate-default-cloudflare-tfstate`

```
terraform/cloudflare/
  versions.tf          # kubernetes backend + cloudflare provider ~> 5.0
  variables.tf         # cloudflare_api_token (sensitive), zone_id (sensitive)
  main.tf              # data "cloudflare_zone" lookup
  zone_settings.tf     # zone setting resources
  bot_protection.tf    # cloudflare_bot_management resource
  tf                   # wrapper script — decrypts secrets, sets KUBECONFIG, execs terraform
  .gitignore           # .terraform/, *.tfplan, crash.log
  .terraform.lock.hcl  # provider version lock (committed)
```

---

## 4) Operational Instructions

Always use the `./tf` wrapper instead of calling `terraform` directly. It decrypts the API token and zone ID from SOPS at runtime and points to the repo-local kubeconfig.

### First-time setup on a new machine

```bash
mise use -g terraform          # install terraform via mise
cd terraform/cloudflare
./tf init                      # configure kubernetes backend
```

### Change a zone setting

1. Edit the relevant `.tf` file (e.g. `zone_settings.tf` or `bot_protection.tf`)
2. Preview the change:
   ```bash
   cd terraform/cloudflare
   ./tf plan
   ```
3. Apply:
   ```bash
   ./tf apply
   ```
4. Commit the changed `.tf` file:
   ```bash
   git add terraform/cloudflare/
   git commit -m "fix(cloudflare): <what changed and why>"
   git push
   ```

### Add a new managed setting

Add a new `cloudflare_zone_setting` resource block to `zone_settings.tf`:

```hcl
resource "cloudflare_zone_setting" "example" {
  zone_id    = var.zone_id
  setting_id = "example_setting"
  value      = "desired_value"
}
```

Check provider v5 docs for the exact `setting_id` and valid `value` options:
`cloudflare_zone_setting` — one resource per setting, not the deprecated `cloudflare_zone_settings_override`.

**Note:** Some settings return 403 on the free plan even with Zone Settings → Edit permission. If a `plan` shows the setting as a change but `apply` returns 403, add it to the "not managed" comment block instead.

### Rotate or update the API token

The token is shared between Terraform and the security audit runbook. To rotate:

1. Create a new token in the Cloudflare dashboard with permissions:
   - Zone → Zone Settings → Edit
   - Zone → Zone → Edit
   - Zone → DNS → Edit
   - Zone → Bot Management → Edit
2. Update the SOPS secret in place:
   ```bash
   sops kubernetes/apps/network/external/cloudflared/cf-security-audit-token.sops.yaml
   # Edit api-token value, save — SOPS re-encrypts automatically
   ```
3. Commit and push the updated SOPS file.
4. Run `./tf plan` to confirm the new token works (exit 0 = no drift).

---

## 5) Examples

### Example A: Enable a new zone setting

To set `security_level` to `high` (if it becomes writable on free plan):

```hcl
# zone_settings.tf
resource "cloudflare_zone_setting" "security_level" {
  zone_id    = var.zone_id
  setting_id = "security_level"
  value      = "high"
}
```

```bash
./tf plan   # shows: 1 to add
./tf apply
git add terraform/cloudflare/zone_settings.tf
git commit -m "fix(cloudflare): raise security_level to high"
```

### Example B: Disable Bot Fight Mode temporarily

```hcl
# bot_protection.tf
resource "cloudflare_bot_management" "main" {
  zone_id          = var.zone_id
  fight_mode       = false          # was true
  ai_bots_protection = "block"
}
```

```bash
./tf plan   # shows: 1 to change
./tf apply
```

---

## 6) Verification Tests

### Test 1: No drift after apply

```bash
cd terraform/cloudflare
./tf plan -detailed-exitcode -out=/dev/null
echo "Exit: $?"
```

Expected:
- Exit code `0` — "No changes. Your infrastructure matches the configuration."

If failed (exit 2):
- Run `./tf plan` (without `-detailed-exitcode`) to see which resource drifted
- Apply to correct: `./tf apply`

### Test 2: Settings live on Cloudflare

```bash
CF_TOKEN=$(mise exec -- sops -d kubernetes/apps/network/external/cloudflared/cf-security-audit-token.sops.yaml \
  | python3 -c "import sys,yaml; print(yaml.safe_load(sys.stdin)['stringData']['api-token'])")
ZONE_ID="$(./tf output -raw zone_id 2>/dev/null || echo '92f555b8d4791a24e9fd38c669fa24e5')"

for setting in ssl min_tls_version always_use_https; do
  val=$(curl -sf "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/settings/$setting" \
    -H "Authorization: Bearer $CF_TOKEN" | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['value'])")
  echo "$setting: $val"
done
```

Expected:
- `ssl: full`
- `min_tls_version: 1.2`
- `always_use_https: on`

### Test 3: State stored in cluster

```bash
kubectl get secret -n flux-system tfstate-default-cloudflare-tfstate
```

Expected:
- Secret exists with `type: Opaque`

---

## 7) Troubleshooting

| Symptom | Likely Cause | First Fix |
|---------|--------------|-----------|
| `terraform not found` | terraform not installed | `mise use -g terraform` |
| `no configuration has been provided` | `KUBE_CONFIG_PATH` not set | Use `./tf` wrapper, not `terraform` directly |
| `403 Unauthorized to access requested resource` | Setting not writable on free plan | Move to "not managed" comment block |
| `403 Authentication error` | Token missing a permission scope | Add missing scope in CF dashboard (Zone Settings → Edit, Bot Management → Edit) |
| `token not found` | Wrong key in SOPS file | Key must be `api-token` (not `token`) |
| Exit code 2 from `./tf plan` | Live settings differ from spec | Run `./tf apply` to re-converge |

```bash
# Verify token is active
CF_TOKEN=$(mise exec -- sops -d kubernetes/apps/network/external/cloudflared/cf-security-audit-token.sops.yaml \
  | python3 -c "import sys,yaml; print(yaml.safe_load(sys.stdin)['stringData']['api-token'])")
curl -sf "https://api.cloudflare.com/client/v4/user/tokens/verify" \
  -H "Authorization: Bearer $CF_TOKEN" | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['status'])"
```

---

## 8) Diagnose Examples

### Diagnose Example 1: Apply fails with 403

```bash
cd terraform/cloudflare
./tf apply 2>&1 | grep "Error\|403\|code"
```

Expected on success:
- No output — apply completes cleanly

If 403 with code `9109`:
- The `setting_id` is not writable via API on the free plan — remove the resource and document in the "not managed" comment block

If 403 with code `10000`:
- Token authentication failure — verify token has the required permission groups in CF dashboard

### Diagnose Example 2: Backend unreachable

```bash
cd terraform/cloudflare
./tf init 2>&1
```

If `dial tcp [::1]:80`:
- `KUBE_CONFIG_PATH` is not being set — ensure you're using `./tf` not `terraform` directly
- Verify repo-root kubeconfig exists: `ls ../../kubeconfig`

If kubeconfig missing:
- Regenerate: `talhelper genconfig` from `kubernetes/bootstrap/talos/`

---

## 9) Health Check

```bash
cd terraform/cloudflare
./tf plan -detailed-exitcode -out=/dev/null 2>&1
# Exit 0 = healthy ✅   exit 2 = drift 🔴   exit 1 = error ⚠️
```

---

## 10) Security Check

```bash
# No secrets in committed .tf files
grep -rE "(cfut_|Bearer |api.key\s*=\s*\"|password\s*=)" terraform/cloudflare/*.tf
# Expected: no output

# Token decrypts correctly
mise exec -- sops -d kubernetes/apps/network/external/cloudflared/cf-security-audit-token.sops.yaml \
  | python3 -c "import sys,yaml; d=yaml.safe_load(sys.stdin); print('key present:', 'api-token' in d.get('stringData',{}))"
# Expected: key present: True

# State secret exists in protected namespace
kubectl get secret -n flux-system tfstate-default-cloudflare-tfstate -o jsonpath='{.metadata.namespace}'
# Expected: flux-system
```

---

## 11) Rollback Plan

Terraform zone settings cannot be destroyed (Cloudflare API constraint) — rollback means changing the value back.

To revert a setting to its previous value:

```bash
# Edit the resource value in the .tf file, then:
cd terraform/cloudflare
./tf apply
git add terraform/cloudflare/
git commit -m "revert(cloudflare): revert <setting> to <previous-value>"
git push
```

To revert to Cloudflare defaults (if a setting was never managed before):
- Remove the resource block from the `.tf` file
- Run `./tf apply` — Terraform removes it from state but the live value stays as-is (not deleted from CF)
- Manually reset in the CF dashboard if needed

---

## 12) References

- Provider docs: Cloudflare Terraform Provider v5 — `cloudflare_zone_setting`, `cloudflare_bot_management`
- Security runbook: `runbooks/security-check.md` §12.6c (zone settings audit), §12.8 (drift detection)
- Token SOPS file: `kubernetes/apps/network/external/cloudflared/cf-security-audit-token.sops.yaml`
- Terraform source: `terraform/cloudflare/`

---

## Version History

- `2026.05.06`: Initial SOP — Terraform Kubernetes-backend workflow, 5 managed settings applied
