# Offline test of the mail rollout switches (mock provider, no API calls, no
# state): cd terraform/cloudflare && terraform test
# Needs no credentials; never touches the real backend.

mock_provider "cloudflare" {
  mock_resource "cloudflare_zero_trust_access_service_token" {
    defaults = { id = "tok-id", client_id = "cid.access", client_secret = "csecret" }
  }
  mock_resource "cloudflare_zero_trust_access_policy" {
    defaults = { id = "pol-id" }
  }
  mock_resource "cloudflare_workers_script" {
    defaults = { id = "mail-ingest-email" }
  }
}

variables {
  cloudflare_api_token = "x"
  zone_id              = "0123456789abcdef0123456789abcdef"
  account_id           = "fedcba9876543210fedcba9876543210"
  secret_domain        = "example.test"
  ingest_hmac_key      = "k"
  fallback_address     = "fb@elsewhere.test"
  stalwart_dkim_records = {
    "202609r" = "v=DKIM1; k=rsa; p=${join("", [for i in range(400) : "A"])}"
    "202609e" = "v=DKIM1; k=ed25519; p=abc"
  }
  brevo_records = {
    code  = { name = "@", type = "TXT", content = "brevo-code:123" }
    dkim1 = { name = "brevo1._domainkey", type = "CNAME", content = "b1.example-test.dkim.brevo.com" }
  }
}

run "all_off_is_noop" {
  command = plan
  assert {
    condition     = length(cloudflare_workers_script.mail_ingest_email) == 0 && length(cloudflare_dns_record.mail_spf) == 0 && length(cloudflare_email_routing_dns.main) == 0 && length(terraform_data.mail_guard) == 0
    error_message = "defaults must create nothing"
  }
}

run "edge_only" {
  command = apply
  variables {
    mail_edge_enabled = true
  }
  assert {
    condition     = length(cloudflare_email_routing_dns.main) == 0 && length(cloudflare_email_routing_catch_all.main) == 0
    error_message = "edge pass must not publish MX"
  }
  assert {
    condition     = cloudflare_zero_trust_access_application.mail_ingest[0].destinations[0].uri == "mail-ingest.example.test"
    error_message = "access host"
  }
  assert {
    condition     = strcontains(cloudflare_ruleset.zone_custom_firewall[0].rules[0].expression, "\"mail-ingest.example.test\"")
    error_message = "waf expression"
  }
  assert {
    condition     = length(cloudflare_workers_script.mail_ingest_email[0].bindings) == 5
    error_message = "bindings"
  }
}

run "inbound_without_dns_refused" {
  command = plan
  variables {
    mail_edge_enabled    = true
    mail_inbound_enabled = true
  }
  expect_failures = [terraform_data.mail_guard]
}

run "full" {
  command = apply
  variables {
    mail_edge_enabled    = true
    mail_dns_enabled     = true
    mail_inbound_enabled = true
  }
  assert {
    condition     = cloudflare_dns_record.mail_spf[0].content == "\"v=spf1 include:_spf.mx.cloudflare.net include:spf.brevo.com ~all\""
    error_message = "spf"
  }
  assert {
    condition     = cloudflare_dns_record.mail_dmarc[0].content == "\"v=DMARC1; p=none; rua=mailto:dmarc@example.test\"" && cloudflare_dns_record.mail_dmarc[0].name == "_dmarc.example.test"
    error_message = "dmarc"
  }
  assert {
    condition     = length(regexall("\" \"", cloudflare_dns_record.stalwart_dkim["202609r"].content)) == 1 && cloudflare_dns_record.stalwart_dkim["202609r"].name == "202609r._domainkey.example.test"
    error_message = "dkim chunking"
  }
  assert {
    condition     = cloudflare_dns_record.brevo["code"].name == "example.test" && cloudflare_dns_record.brevo["code"].content == "\"brevo-code:123\"" && cloudflare_dns_record.brevo["dkim1"].name == "brevo1._domainkey.example.test"
    error_message = "brevo"
  }
  assert {
    condition     = cloudflare_email_routing_catch_all.main[0].actions[0].type == "worker" && cloudflare_email_routing_catch_all.main[0].actions[0].value[0] == "mail-ingest-email"
    error_message = "catch-all worker"
  }
}

run "rollback_forward" {
  command = plan
  variables {
    mail_edge_enabled    = true
    mail_dns_enabled     = true
    mail_inbound_enabled = true
    mail_catch_all_mode  = "forward"
  }
  assert {
    condition     = cloudflare_email_routing_catch_all.main[0].actions[0].type == "forward"
    error_message = "catch-all forward"
  }
}
