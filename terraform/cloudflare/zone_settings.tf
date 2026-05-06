# DNS records are intentionally NOT managed here.
# external-dns (running in the cluster, managed via Flux) owns all CNAME/A records
# and writes them directly to Cloudflare. Adding cloudflare_record resources here
# would cause conflicts and duplicate records.

# ── Settings to fix ───────────────────────────────────────────────────────────

resource "cloudflare_zone_setting" "ssl" {
  zone_id    = var.zone_id
  setting_id = "ssl"
  value      = "full"
}

resource "cloudflare_zone_setting" "min_tls_version" {
  zone_id    = var.zone_id
  setting_id = "min_tls_version"
  value      = "1.2"
}

resource "cloudflare_zone_setting" "always_use_https" {
  zone_id    = var.zone_id
  setting_id = "always_use_https"
  value      = "on"
}

resource "cloudflare_zone_setting" "security_header" {
  zone_id    = var.zone_id
  setting_id = "security_header"
  value = {
    strict_transport_security = {
      enabled            = true
      max_age            = 31536000
      include_subdomains = false
      preload            = false
      nosniff            = true
    }
  }
}

# ── Settings writable on free plan — documented to prevent drift ──────────────
# (http2, http3, ipv6, brotli, websockets, browser_check, email_obfuscation,
#  0rtt, tls_1_3, opportunistic_encryption, security_level all return 403 when
#  patched via API on the free plan — correct values are already set in the
#  dashboard and are verified by §12.6c of the security runbook.)
