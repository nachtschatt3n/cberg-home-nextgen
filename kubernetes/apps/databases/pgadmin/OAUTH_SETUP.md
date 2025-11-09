# pgAdmin OAuth/OIDC Setup with Authentik

## Overview
pgAdmin is configured to use OAuth/OIDC authentication via Authentik. Users will authenticate through Authentik instead of using pgAdmin's built-in authentication.

## Step 1: Create OAuth Provider in Authentik

1. Log in to Authentik at `https://auth.example.com`
2. Navigate to **Applications** → **Providers**
3. Click **Create** → **OAuth2/OpenID Provider**
4. Configure the provider:
   - **Name**: `pgAdmin`
   - **Authorization flow**: Select an appropriate flow (Authorization Code recommended)
   - **Redirect URIs**: `https://pgadmin.example.com/oauth2/callback`
   - **Client type**: `Confidential`
   - **Client ID**: (will be generated, copy this)
   - **Client secret**: (will be generated, copy this)
   - **Scopes**: Ensure `openid`, `email`, `profile` are included
5. Click **Create**

## Step 2: Create Application in Authentik

1. Navigate to **Applications** → **Applications**
2. Click **Create**
3. Configure the application:
   - **Name**: `pgAdmin`
   - **Slug**: `pgadmin`
   - **Provider**: Select the `pgAdmin` provider created above
   - **Launch URL**: `https://pgadmin.example.com`
4. Click **Create**

## Step 3: Assign Users/Groups

1. In the Application, go to **User assignments** or **Group assignments**
2. Assign users or groups who should have access to pgAdmin

## Step 4: Update pgAdmin Secret

After creating the OAuth provider, update the secret with the actual client ID and secret:

```bash
# Decrypt the secret
export SOPS_AGE_KEY_FILE=age.key
sops kubernetes/apps/databases/pgadmin/app/secret.sops.yaml

# Update these values:
# PGADMIN_CONFIG_OAUTH_CLIENT_ID: "<client-id-from-authentik>"
# PGADMIN_CONFIG_OAUTH_CLIENT_SECRET: "<client-secret-from-authentik>"

# Re-encrypt
sops --encrypt --in-place kubernetes/apps/databases/pgadmin/app/secret.sops.yaml

# Commit and push
git add kubernetes/apps/databases/pgadmin/app/secret.sops.yaml
git commit -m "feat(pgadmin): update OAuth client credentials from Authentik"
git push origin main
```

## Step 5: Restart pgAdmin

After updating the secret:

```bash
flux reconcile source git flux-system
flux reconcile kustomization pgadmin -n databases
kubectl delete pod -n databases -l app=pgadmin
```

## Verification

1. Navigate to `https://pgadmin.example.com`
2. You should be redirected to Authentik for authentication
3. After authenticating, you'll be redirected back to pgAdmin
4. You should be logged in automatically

## Troubleshooting

- Check pgAdmin logs: `kubectl logs -n databases -l app=pgadmin`
- Verify OAuth endpoints are accessible
- Ensure redirect URI matches exactly in Authentik
- Check that users/groups are assigned to the application in Authentik
