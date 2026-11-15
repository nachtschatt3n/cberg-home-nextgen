# Secondary Cloudflare zone, DNS-only records pointing at the current host.
# Explicitly authorised exception to "DNS records belong to external-dns":
# these two static records exist until the cutover to the tunnel.
resource "cloudflare_zone" "andreamosteller" {
  account = {
    id = data.cloudflare_zone.main.account.id
  }
  name = var.andreamosteller_domain
  type = "full"
}

resource "cloudflare_dns_record" "andreamosteller_apex" {
  zone_id = cloudflare_zone.andreamosteller.id
  name    = var.andreamosteller_domain
  type    = "A"
  content = var.andreamosteller_origin_ip
  ttl     = 300
  proxied = false
}

resource "cloudflare_dns_record" "andreamosteller_www" {
  zone_id = cloudflare_zone.andreamosteller.id
  name    = "www.${var.andreamosteller_domain}"
  type    = "A"
  content = var.andreamosteller_origin_ip
  ttl     = 300
  proxied = false
}
