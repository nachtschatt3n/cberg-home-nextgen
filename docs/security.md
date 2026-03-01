# Security Reference

> Maintained manually. Update after key rotation, new app integrations, or policy changes.
> For detailed SOPs, see `docs/sops/sops-encryption.md` and `docs/sops/authentik.md`.

---

## Security Overview

| Layer | Component | Purpose |
|-------|-----------|---------|
| Secrets | SOPS + age | Git-safe encrypted secrets |
| Identity | Authentik | Unified SSO, forward auth proxy |
| TLS | cert-manager + Let's Encrypt | Automated certificate management |
| External access | Cloudflare Tunnel | No inbound ports; DDoS protection |
| Network | UniFi IDS/IPS | Threat Management on gateway |
| VPN | WireGuard (UniFi) | Secure remote admin access |
| Scanning | security-check.py | Weekly automated security audit |

---

## Accepted Risk Register

The following risks are explicitly accepted as of **2026-03-01** with compensating controls.
Each item must be reviewed on the listed review date (or sooner after incident, host migration,
or policy changes).

### AR-2026-03-01-01 — Local Talos Bootstrap Artifacts in Plaintext

- Status: Accepted risk
- Scope: Local-only files in `kubernetes/bootstrap/talos/clusterconfig/`:
  - `kubernetes-k8s-nuc14-01.yaml`
  - `kubernetes-k8s-nuc14-02.yaml`
  - `kubernetes-k8s-nuc14-03.yaml`
  - `talosconfig`
- Git exposure: **Not committed in git** (paths are ignored by
  `kubernetes/bootstrap/talos/clusterconfig/.gitignore`)
- Rationale: Required local operational artifacts for Talos node management and recovery.
- Compensating controls:
  - Keep permissions restrictive (`0600` or stricter) on local files.
  - Never copy these artifacts to shared locations, tickets, or chat.
  - Rotate Talos/Kubernetes bootstrap material immediately if host compromise is suspected.
  - Prefer regenerating ephemeral local artifacts over long-term retention when practical.
- Owner: Platform operations
- Next review date: **2026-06-01**

### AR-2026-03-01-02 — Local `cloudflared.json` Credential File

- Status: Accepted risk
- Scope: Local tunnel credential file `cloudflared.json`
- Git exposure: **Not committed in git** (ignored by repository `.gitignore`)
- Rationale: Local runtime credential required by Cloudflare tunnel tooling.
- Compensating controls:
  - Keep file local-only with restrictive permissions (`0600`).
  - Do not reference or embed file contents in repository manifests or docs.
  - Rotate the tunnel credential immediately after suspected host compromise.
  - Prefer SOPS-encrypted Kubernetes secret (`kubernetes/apps/network/external/cloudflared/app/secret.sops.yaml`)
    for cluster-managed credential workflows.
- Owner: Platform operations
- Next review date: **2026-06-01**

---

## Secret Management (SOPS + age)

All secrets stored in Git are encrypted with [SOPS](https://github.com/getsops/sops) using
[age](https://github.com/FiloSottile/age) encryption.

**Age Public Key:**
```
age1nw624gkjpl0sattullahnekdswjcvsgarf8gwwyf9jdqc0zm9enqyp2pf6
```

**Age Private Key Location:** `$PWD/age.key` (gitignored; set via `SOPS_AGE_KEY_FILE`)

### SOPS Path Rules (`.sops.yaml`)

| Path Pattern | Scope | Fields Encrypted |
|-------------|-------|-----------------|
| `talos/**/*.sops.yaml` | Talos node configs | Entire file (`mac_only_encrypted: true`) |
| `kubernetes/**/*.sops.yaml` | Kubernetes secrets | Only `data` and `stringData` fields |

**Critical:** SOPS creation rules are path-based. Files MUST be in the correct repository path
when encrypting — cannot encrypt from `/tmp/` or other paths.

### File Naming Convention

All encrypted files MUST use the `.sops.yaml` suffix:
- ✅ `secret.sops.yaml`
- ✅ `configmap.sops.yaml`
- ❌ `secret.yaml` (never commit unencrypted)

### Encrypted File Locations

| Location | Purpose |
|----------|---------|
| `kubernetes/apps/{ns}/{app}/app/secret.sops.yaml` | Per-app secrets |
| `kubernetes/flux/components/common/cluster-secrets.sops.yaml` | Cluster-wide variables (domain, etc.) |
| `kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml` | Authentik blueprints (encrypted) |
| `talos/**/*.sops.yaml` | Talos node configurations |

---

## SOPS Quick Reference

```bash
# Edit encrypted file (opens $EDITOR, auto-re-encrypts on save)
sops kubernetes/apps/{ns}/{app}/app/secret.sops.yaml

# Decrypt to stdout for inspection
sops -d kubernetes/apps/{ns}/{app}/app/secret.sops.yaml

# Encrypt in place (file must be in kubernetes/ or talos/ path)
sops -e -i kubernetes/apps/{ns}/{app}/app/secret.sops.yaml

# Verify file is encrypted
head -20 kubernetes/apps/{ns}/{app}/app/secret.sops.yaml | grep "sops:"
```

### Correct Workflow for Updating Secrets

```bash
# Method 1: Edit directly (preferred for small changes)
sops kubernetes/apps/{ns}/{app}/app/secret.sops.yaml

# Method 2: Decrypt → edit → re-encrypt (for complex changes)
sops -d kubernetes/apps/{ns}/{app}/app/secret.sops.yaml > /tmp/secret.yaml
# Edit /tmp/secret.yaml
cp /tmp/secret.yaml kubernetes/apps/{ns}/{app}/app/secret-new.sops.yaml
sops -e -i kubernetes/apps/{ns}/{app}/app/secret-new.sops.yaml
mv kubernetes/apps/{ns}/{app}/app/secret-new.sops.yaml kubernetes/apps/{ns}/{app}/app/secret.sops.yaml
rm /tmp/secret.yaml
```

**Common Errors:**

| Error | Cause | Fix |
|-------|-------|-----|
| `no matching creation rules found` | File not in kubernetes/ or talos/ path | Move to correct path before encrypting |
| `sops metadata not found` | File not encrypted yet | Use `sops -e -i` to encrypt first |
| Flux can't decrypt | age key not in flux-system | Check `kubectl get secret sops-age -n flux-system` |

---

## Authentik — Identity Provider

Authentik provides SSO and forward-auth proxy for all externally and internally exposed services.

**Deployment:** `kubernetes/apps/kube-system/authentik/`

### Blueprint-Only Approach

**ALWAYS use blueprints for Authentik configuration — never the UI.** Blueprints are:
- Version-controlled and GitOps-compatible
- Reproducible across environments
- Stored in SOPS-encrypted ConfigMap: `kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml`

### Key Authentik Flow UUIDs

| Flow | UUID |
|------|------|
| default-provider-authorization-implicit-consent | `0cdf1b8c-88f9-4b90-a063-a14e18192f74` |
| default-provider-invalidation-flow | `b8a97e00-f02f-48d9-b854-b26bf837779c` |
| Local Kubernetes Cluster service connection | `162f6c4f-053d-4a1a-9aa6-d8e590c49d70` |

### New App Integration Checklist

- [ ] Create `kubernetes/apps/{ns}/{app}/app/authentik-blueprint.yaml` (source of truth)
- [ ] Decrypt `configmap.sops.yaml`, add blueprint entry, re-encrypt
- [ ] Create proxy provider entry with hardcoded flow UUIDs (not slugs)
- [ ] Create application entry using `!KeyOf` to reference provider
- [ ] Create outpost entry with `service_connection` UUID and `kubernetes_namespace: kube-system`
- [ ] Add `gethomepage.dev/enabled: "true"` auth annotations to ingress
- [ ] Create separate ingress for `/outpost.goauthentik.io/*` paths
- [ ] Deploy and verify: `kubectl exec -n kube-system deployment/authentik-server -- python3 manage.py show_blueprints`

### Blueprint Pattern

```yaml
version: 1
entries:
  - id: my-app-provider
    model: authentik_providers_proxy.proxyprovider
    state: present
    attrs:
      external_host: "https://myapp.domain"
      internal_host: "http://myapp.namespace.svc.cluster.local:PORT"
      authorization_flow: "0cdf1b8c-88f9-4b90-a063-a14e18192f74"
      invalidation_flow: "b8a97e00-f02f-48d9-b854-b26bf837779c"

  - id: my-app-application
    model: authentik_core.application
    attrs:
      name: My App
      slug: my-app
      provider: !KeyOf my-app-provider
      meta_launch_url: "https://myapp.domain"

  - id: my-app-outpost
    model: authentik_outposts.outpost
    attrs:
      name: my-app-forward-auth
      type: proxy
      service_connection: "162f6c4f-053d-4a1a-9aa6-d8e590c49d70"
      providers:
        - !KeyOf my-app-provider
      config:
        authentik_host: "https://auth.domain"
        kubernetes_namespace: kube-system
```

### Blueprint DON'Ts

- ❌ Never use slug names for flow references (use UUIDs)
- ❌ Never use string names for provider references (use `!KeyOf`)
- ❌ Never use Flux variable substitution in ConfigMap data (use SOPS-encrypted ConfigMap)
- ❌ Never configure Authentik via UI

### Authentik Debugging

```bash
# Check blueprints loaded
kubectl exec -n kube-system deployment/authentik-server -- python3 manage.py show_blueprints

# Check outpost deployment
kubectl get deployment -n kube-system ak-outpost-{app}-forward-auth

# Check outpost service
kubectl get svc -n kube-system ak-outpost-{app}-forward-auth

# Blueprint application logs
kubectl logs -n kube-system -l app.kubernetes.io/name=authentik --tail=100 | grep -i blueprint
```

---

## TLS / cert-manager

cert-manager v1.19.3 manages TLS certificates via Let's Encrypt.

**Deployment:** `kubernetes/apps/cert-manager/cert-manager/`

| Setting | Value |
|---------|-------|
| Issuer | Let's Encrypt (ACME) |
| Challenge type | DNS-01 via Cloudflare API |
| Scope | Wildcard `*.domain` + specific hostnames |
| Renewal | Automatic, 30 days before expiry |
| Namespace | cert-manager |

```bash
# Check certificate status
kubectl get certificates -A
kubectl get certificaterequests -A

# Check cert-manager logs
kubectl logs -n cert-manager deployment/cert-manager --tail=50
```

---

## External Access Security

**Cloudflare Tunnel** is the ONLY external access path:
- No inbound firewall ports open on WAN
- All traffic encrypted through Cloudflare Tunnel (QUIC + TLS)
- Cloudflare DDoS protection and WAF at edge
- External ingress-nginx only reachable via tunnel

External services additionally protected by:
- Authentik forward auth (for services that require login)
- Cloudflare Access policies where configured

---

## Security Audit Runbook

Automated weekly security audit: `runbooks/security-check.py`

Covers:
1. SOPS encryption coverage (no plaintext secrets)
2. Sensitive data exposure scan
3. Git history scanning
4. CVE exposure check
5. Authentik authentication logs
6. Attack pattern detection (Elasticsearch logs)
7. RBAC audit
8. External exposure review
9. Certificate expiry
10. Flux security
11. UniFi network security events

Output: `runbooks/security-check-current.md` (gitignored — contains findings)

```bash
python3 runbooks/security-check.py
```

*See `docs/sops/sops-encryption.md` for detailed encryption SOPs.*
*See `docs/sops/authentik.md` for detailed Authentik SOPs.*
