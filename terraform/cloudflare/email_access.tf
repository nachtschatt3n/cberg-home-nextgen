# Cloudflare Access in front of https://mail-ingest.<domain>/v1/ingest.
# Only the Email Worker holds the service token; the shim additionally checks an
# HMAC (defence in depth -- a leaked token alone cannot inject mail).
#
# NOTE: the service token's client_secret is stored in terraform state (the
# flux-system `tfstate-default-cloudflare-tfstate` Secret). The state is already
# secret-class; the secret never leaves Terraform otherwise (wired straight into
# the Worker binding below).

resource "cloudflare_zero_trust_access_service_token" "mail_ingest" {
  count      = local.mail_edge
  account_id = var.account_id
  name       = "mail-ingest-email-worker"
  # Default is 8760h: the token would silently expire after a year and every
  # inbound mail would drop to the fallback forward. Rotate deliberately instead
  # (bump client_secret_version).
  duration = "forever"
}

resource "cloudflare_zero_trust_access_policy" "mail_ingest" {
  count      = local.mail_edge
  account_id = var.account_id
  name       = "mail-ingest: email worker service token"
  decision   = "non_identity" # "Service Auth"
  include = [{
    service_token = {
      token_id = cloudflare_zero_trust_access_service_token.mail_ingest[0].id
    }
  }]
}

resource "cloudflare_zero_trust_access_application" "mail_ingest" {
  count      = local.mail_edge
  account_id = var.account_id
  name       = "mail-ingest"
  type       = "self_hosted"
  destinations = [{
    type = "public"
    uri  = local.mail_ingest_host
  }]
  # A missing/invalid token gets a 401 instead of a 302 to the login page; the
  # Worker treats any non-200/422 as "forward to fallback" either way.
  service_auth_401_redirect = true
  app_launcher_visible      = false
  session_duration          = "24h"
  policies = [{
    id         = cloudflare_zero_trust_access_policy.mail_ingest[0].id
    precedence = 1
  }]
}
