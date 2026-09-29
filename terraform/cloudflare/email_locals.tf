# Shared locals + guard rails for the own-domain mail stack (email_*.tf).
locals {
  mail_edge    = var.mail_edge_enabled ? 1 : 0
  mail_dns     = var.mail_dns_enabled ? 1 : 0
  mail_inbound = var.mail_inbound_enabled ? 1 : 0

  mail_ingest_host   = var.secret_domain == null ? null : "mail-ingest.${var.secret_domain}"
  mail_worker_name   = "mail-ingest-email"
  mail_worker_source = "${path.module}/../../cloudflare/email-worker/worker.js"

  # TXT content in the quoted, <=255-char character-string form the Cloudflare
  # API returns, so long DKIM keys do not show a perpetual diff.
  txt_chunk = 255
}

# Fail the plan early instead of half-applying an inconsistent rollout.
resource "terraform_data" "mail_guard" {
  count = (var.mail_edge_enabled || var.mail_dns_enabled || var.mail_inbound_enabled) ? 1 : 0

  lifecycle {
    precondition {
      condition     = var.account_id != null && var.secret_domain != null
      error_message = "account_id and secret_domain must be set (run through ./tf)."
    }
    precondition {
      condition     = !var.mail_edge_enabled || (var.ingest_hmac_key != null && var.fallback_address != null)
      error_message = "mail_edge_enabled needs ingest_hmac_key and fallback_address (terraform/cloudflare/email.sops.yaml)."
    }
    precondition {
      condition     = !var.mail_inbound_enabled || (var.mail_edge_enabled && var.mail_dns_enabled)
      error_message = "mail_inbound_enabled requires mail_edge_enabled (Worker exists) and mail_dns_enabled (our merged SPF must exist BEFORE Email Routing is enabled, or Cloudflare adds its own and the zone ends up with two SPF records)."
    }
  }
}
