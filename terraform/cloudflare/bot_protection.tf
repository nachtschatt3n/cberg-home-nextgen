resource "cloudflare_bot_management" "main" {
  zone_id          = var.zone_id
  fight_mode       = false # blocks Alexa skill dispatch (managed_challenge on Amazon POSTs to music-api) — see AR
  ai_bots_protection = "block"
}
