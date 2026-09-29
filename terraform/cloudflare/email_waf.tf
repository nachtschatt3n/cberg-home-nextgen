# WAF skip for the Email Worker -> mail-ingest subrequest.
#
# Free-plan feasibility (checked 2026-09-29):
#   - Bot Fight Mode (free) runs OUTSIDE the ruleset engine and cannot be skipped
#     by any rule; it is already off (bot_protection.tf, fight_mode = false).
#   - ai_bots_protection = "block" targets verified AI-crawler user agents; a
#     Worker subrequest is not one. http_request_sbfm is listed defensively (it
#     is the Super Bot Fight Mode phase, Pro+); drop it from
#     var.mail_ingest_waf_skip_phases if the API refuses it on this plan.
#   - Free plan: 5 custom rules per zone; this uses 1.
#
# OWNERSHIP: this is the zone's ONE http_request_firewall_custom entrypoint
# ruleset (none existed on 2026-09-29). Any custom rule later added in the
# dashboard will be overwritten by the next apply -- add it here instead.
# Access still enforces the service token; skip does not bypass Access.

resource "cloudflare_ruleset" "zone_custom_firewall" {
  count       = local.mail_edge
  zone_id     = var.zone_id
  name        = "default"
  description = "Zone custom firewall rules (terraform/cloudflare/email_waf.tf)"
  kind        = "zone"
  phase       = "http_request_firewall_custom"

  rules = [{
    ref         = "mail_ingest_skip"
    description = "mail-ingest: let the Email Worker reach /v1/ingest"
    expression  = "(http.host eq \"${local.mail_ingest_host}\" and http.request.uri.path eq \"/v1/ingest\" and http.request.method eq \"POST\")"
    action      = "skip"
    action_parameters = {
      ruleset  = "current"
      phases   = var.mail_ingest_waf_skip_phases
      products = ["bic", "securityLevel", "uaBlock", "zoneLockdown"]
    }
    logging = {
      enabled = true
    }
    enabled = true
  }]
}
