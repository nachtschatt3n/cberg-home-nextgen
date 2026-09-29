# Cloudflare Email Routing for the zone.
#
# PROVIDER NOTE (v5.19): cloudflare_email_routing_settings calls the DEPRECATED
# POST /email/routing/enable, and cloudflare_email_routing_dns calls
# POST /email/routing/dns. BOTH "enable Email Routing and add + lock the MX and
# SPF records" -- enabling routing IS publishing the MX. So there is no separate
# "settings" resource here: cloudflare_email_routing_dns is the single
# inbound switch (mail_inbound_enabled), and destroying it (count -> 0) disables
# routing and removes the MX again (rollback).

# Fallback destination (account-level). Created in pass 1 so the operator can
# click Cloudflare's verification mail before inbound goes live; forward() only
# works to VERIFIED addresses.
resource "cloudflare_email_routing_address" "fallback" {
  count      = local.mail_edge
  account_id = var.account_id
  email      = var.fallback_address
}

resource "cloudflare_email_routing_dns" "main" {
  count   = local.mail_inbound
  zone_id = var.zone_id

  # Our merged SPF (email_dns.tf) must exist first, otherwise Cloudflare adds
  # its own `v=spf1 include:_spf.mx.cloudflare.net ~all` next to it.
  depends_on = [cloudflare_dns_record.mail_spf, terraform_data.mail_guard]
}

resource "cloudflare_email_routing_catch_all" "main" {
  count   = local.mail_inbound
  zone_id = var.zone_id
  name    = "catch-all -> mail-ingest"
  enabled = true
  matchers = [{
    type = "all"
  }]
  actions = [{
    type = var.mail_catch_all_mode
    value = (var.mail_catch_all_mode == "worker"
      ? [cloudflare_workers_script.mail_ingest_email[0].script_name]
    : [var.fallback_address])
  }]

  depends_on = [cloudflare_email_routing_dns.main]
}
