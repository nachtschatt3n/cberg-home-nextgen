resource "cloudflare_bot_management" "main" {
  zone_id          = var.zone_id
  fight_mode       = true
  ai_bots_protection = "block"
}
