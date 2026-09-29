# Mail-auth DNS records: the ONLY records this stack creates. All MX/TXT
# (+ Brevo DKIM CNAMEs); external-dns keeps owning A/AAAA/CNAME for apps (it runs
# policy: sync with a TXT registry and only touches records it registered, and
# its managed types exclude MX/TXT -- never add them).
#
# The MX records are NOT here: Cloudflare Email Routing adds and locks them
# (email_routing.tf, mail_inbound_enabled).
#
# Every value that contains the domain comes from SOPS via ./tf.

locals {
  # SPF: one record for both the Email Routing forwarder and Brevo outbound.
  mail_spf = "v=spf1 include:_spf.mx.cloudflare.net include:spf.brevo.com ~all"

  mail_dmarc = var.secret_domain == null ? null : "v=DMARC1; p=none; rua=mailto:dmarc@${var.secret_domain}"

  # "<a>" "<b>" ... split at 255 chars (RFC 1035 character-string limit).
  stalwart_dkim_txt = {
    for sel, v in var.stalwart_dkim_records :
    sel => join(" ", [for i in range(0, length(v), local.txt_chunk) : format("\"%s\"", substr(v, i, local.txt_chunk))])
  }
}

resource "cloudflare_dns_record" "mail_spf" {
  count   = local.mail_dns
  zone_id = var.zone_id
  name    = var.secret_domain
  type    = "TXT"
  content = "\"${local.mail_spf}\""
  ttl     = 1
  comment = "SPF: Cloudflare Email Routing + Brevo (terraform/cloudflare/email_dns.tf)"
}

resource "cloudflare_dns_record" "mail_dmarc" {
  count   = local.mail_dns
  zone_id = var.zone_id
  name    = "_dmarc.${var.secret_domain}"
  type    = "TXT"
  content = "\"${local.mail_dmarc}\""
  ttl     = 1
  comment = "DMARC p=none (terraform/cloudflare/email_dns.tf)"
}

resource "cloudflare_dns_record" "stalwart_dkim" {
  for_each = var.mail_dns_enabled ? local.stalwart_dkim_txt : {}
  zone_id  = var.zone_id
  name     = "${each.key}._domainkey.${var.secret_domain}"
  type     = "TXT"
  content  = each.value
  ttl      = 1
  comment  = "Stalwart DKIM (terraform/cloudflare/email_dns.tf)"
}

resource "cloudflare_dns_record" "brevo" {
  for_each = var.mail_dns_enabled ? var.brevo_records : {}
  zone_id  = var.zone_id
  name     = each.value.name == "@" ? var.secret_domain : "${each.value.name}.${var.secret_domain}"
  type     = each.value.type
  content  = each.value.type == "TXT" ? "\"${trim(each.value.content, "\"")}\"" : each.value.content
  ttl      = 1
  proxied  = false
  comment  = "Brevo ${each.key} (terraform/cloudflare/email_dns.tf)"
}
