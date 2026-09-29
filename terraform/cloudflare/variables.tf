variable "cloudflare_api_token" {
  type      = string
  sensitive = true
}

variable "zone_id" {
  type      = string
  sensitive = true
}

# ── Own-domain mail (Stalwart) ────────────────────────────────────────────────
# All values below are fed by ./tf from SOPS; nothing mail-related is in git.
# Rollout switches (all default OFF so a plain `./tf plan` stays a no-op):
#   mail_edge_enabled    Pass 1: Access app + service token, WAF skip rule,
#                        Email Worker, fallback destination address.
#   mail_dns_enabled     SPF / DMARC / Stalwart DKIM / Brevo records.
#   mail_inbound_enabled Pass 2: Email Routing on (MX) + catch-all -> Worker.
#                        THIS is the moment mail starts arriving.

variable "account_id" {
  description = "Cloudflare account id (Workers, Access and routing addresses are account-level). ./tf derives it from the zone lookup."
  type        = string
  sensitive   = true
  default     = null
}

variable "secret_domain" {
  description = "Zone apex / mail domain (SECRET_DOMAIN from cluster-secrets). ./tf exports it."
  type        = string
  sensitive   = true
  default     = null
}

variable "ingest_hmac_key" {
  description = "Shared HMAC key between the Email Worker and the mail-ingest shim (same value as INGEST_HMAC_KEY in the cluster). From terraform/cloudflare/email.sops.yaml."
  type        = string
  sensitive   = true
  default     = null
}

variable "fallback_address" {
  description = "Verified Email Routing destination the Worker forwards to when the cluster cannot take a message. From terraform/cloudflare/email.sops.yaml."
  type        = string
  sensitive   = true
  default     = null
}

variable "mail_edge_enabled" {
  description = "Create the Cloudflare edge for inbound mail: Access app/token, WAF skip, Email Worker, fallback address."
  type        = bool
  default     = false
}

variable "mail_dns_enabled" {
  description = "Publish the mail-auth TXT records (SPF, DMARC) plus any stalwart_dkim_records / brevo_records."
  type        = bool
  default     = false
}

variable "mail_inbound_enabled" {
  description = "Enable Email Routing (Cloudflare adds + locks the MX records) and point the catch-all at the Worker. Requires mail_edge_enabled and mail_dns_enabled."
  type        = bool
  default     = false
}

variable "mail_catch_all_mode" {
  description = "Catch-all action: \"worker\" (normal) or \"forward\" (rollback: everything straight to fallback_address)."
  type        = string
  default     = "worker"
  validation {
    condition     = contains(["worker", "forward"], var.mail_catch_all_mode)
    error_message = "mail_catch_all_mode must be \"worker\" or \"forward\"."
  }
}

variable "stalwart_dkim_records" {
  description = "Stalwart DKIM public keys: selector => TXT value (e.g. \"v=DKIM1; k=rsa; p=...\"). Published as <selector>._domainkey. Values > 255 chars are split into quoted strings automatically."
  type        = map(string)
  default     = {}
}

variable "brevo_records" {
  description = "Brevo verification/DKIM records, keyed by an arbitrary label. name is relative to the zone apex (\"@\" for the apex), e.g. { code = { name = \"@\", type = \"TXT\", content = \"brevo-code:...\" }, dkim1 = { name = \"brevo1._domainkey\", type = \"CNAME\", content = \"b1.<domain>.dkim.brevo.com\" } }."
  type = map(object({
    name    = string
    type    = string
    content = string
  }))
  default = {}
  validation {
    condition     = alltrue([for r in values(var.brevo_records) : contains(["TXT", "CNAME"], r.type)])
    error_message = "brevo_records only supports TXT and CNAME (MX/SPF are owned by email_dns.tf / Email Routing)."
  }
}

variable "mail_ingest_waf_skip_phases" {
  description = "Ruleset phases the mail-ingest skip rule bypasses. Drop http_request_sbfm if the free plan's API refuses it (Super Bot Fight Mode is Pro+; free Bot Fight Mode cannot be skipped at all and is already off)."
  type        = list(string)
  default     = ["http_ratelimit", "http_request_firewall_managed", "http_request_sbfm"]
}
