# ── Settings that need fixing ─────────────────────────────────────────────────

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

# ── Settings already correct — documented to prevent drift ────────────────────

resource "cloudflare_zone_setting" "tls_1_3" {
  zone_id    = var.zone_id
  setting_id = "tls_1_3"
  value      = "on"
}

resource "cloudflare_zone_setting" "automatic_https_rewrites" {
  zone_id    = var.zone_id
  setting_id = "automatic_https_rewrites"
  value      = "on"
}

resource "cloudflare_zone_setting" "opportunistic_encryption" {
  zone_id    = var.zone_id
  setting_id = "opportunistic_encryption"
  value      = "on"
}

resource "cloudflare_zone_setting" "security_level" {
  zone_id    = var.zone_id
  setting_id = "security_level"
  value      = "medium"
}

resource "cloudflare_zone_setting" "http2" {
  zone_id    = var.zone_id
  setting_id = "http2"
  value      = "on"
}

resource "cloudflare_zone_setting" "http3" {
  zone_id    = var.zone_id
  setting_id = "http3"
  value      = "on"
}

resource "cloudflare_zone_setting" "ipv6" {
  zone_id    = var.zone_id
  setting_id = "ipv6"
  value      = "on"
}

resource "cloudflare_zone_setting" "brotli" {
  zone_id    = var.zone_id
  setting_id = "brotli"
  value      = "on"
}

resource "cloudflare_zone_setting" "websockets" {
  zone_id    = var.zone_id
  setting_id = "websockets"
  value      = "on"
}

resource "cloudflare_zone_setting" "browser_check" {
  zone_id    = var.zone_id
  setting_id = "browser_check"
  value      = "on"
}

resource "cloudflare_zone_setting" "email_obfuscation" {
  zone_id    = var.zone_id
  setting_id = "email_obfuscation"
  value      = "on"
}

resource "cloudflare_zone_setting" "zero_rtt" {
  zone_id    = var.zone_id
  setting_id = "0rtt"
  value      = "off"
}
