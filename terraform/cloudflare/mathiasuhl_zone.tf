# Zone for a domain with live Google mail. All records DNS-only (never proxied).
# Known records are carried over exactly; anything else goes in the encrypted
# extra-records list (see variables.tf). Export the full record list from the
# current DNS provider BEFORE switching nameservers.
locals {
  mathiasuhl_google_mx = {
    "aspmx.l.google.com"      = 1
    "alt1.aspmx.l.google.com" = 5
    "alt2.aspmx.l.google.com" = 5
    "alt3.aspmx.l.google.com" = 10
    "alt4.aspmx.l.google.com" = 10
  }
  mathiasuhl_a_records = {
    apex_216 = { name = "@", content = "216.239.32.21" }
    apex_37  = { name = "@", content = "37.202.4.23" }
    www_216  = { name = "www", content = "216.239.32.21" }
    www_37   = { name = "www", content = "37.202.4.23" }
  }
  mathiasuhl_extra = {
    for r in jsondecode(var.mathiasuhl_extra_records) :
    "${r.name}-${r.type}-${substr(sha1(r.content), 0, 8)}" => r
  }
}

resource "cloudflare_zone" "mathiasuhl" {
  account = {
    id = data.cloudflare_zone.main.account.id
  }
  name = var.mathiasuhl_domain
  type = "full"
}

resource "cloudflare_dns_record" "mathiasuhl_a" {
  for_each = local.mathiasuhl_a_records
  zone_id  = cloudflare_zone.mathiasuhl.id
  name     = each.value.name == "@" ? var.mathiasuhl_domain : "${each.value.name}.${var.mathiasuhl_domain}"
  type     = "A"
  content  = each.value.content
  ttl      = 300
  proxied  = false
}

resource "cloudflare_dns_record" "mathiasuhl_mx" {
  for_each = local.mathiasuhl_google_mx
  zone_id  = cloudflare_zone.mathiasuhl.id
  name     = var.mathiasuhl_domain
  type     = "MX"
  content  = each.key
  priority = each.value
  ttl      = 300
  proxied  = false
}

resource "cloudflare_dns_record" "mathiasuhl_extra" {
  for_each = nonsensitive(toset(keys(local.mathiasuhl_extra)))
  zone_id  = cloudflare_zone.mathiasuhl.id
  name     = local.mathiasuhl_extra[each.key].name == "@" ? var.mathiasuhl_domain : "${local.mathiasuhl_extra[each.key].name}.${var.mathiasuhl_domain}"
  type     = local.mathiasuhl_extra[each.key].type
  content  = local.mathiasuhl_extra[each.key].content
  priority = try(local.mathiasuhl_extra[each.key].priority, null)
  ttl      = try(local.mathiasuhl_extra[each.key].ttl, 300)
  proxied  = false
}
