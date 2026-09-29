# The Email Worker (cloudflare/email-worker/worker.js): plain ES module, no build
# step, deployed straight from the repo. See that directory's README.md.

resource "cloudflare_workers_script" "mail_ingest_email" {
  count              = local.mail_edge
  account_id         = var.account_id
  script_name        = local.mail_worker_name
  content            = file(local.mail_worker_source)
  main_module        = "worker.js"
  compatibility_date = "2026-09-01"

  bindings = [
    {
      name = "SECRET_DOMAIN"
      type = "plain_text"
      text = var.secret_domain
    },
    {
      name = "HMAC_KEY"
      type = "secret_text"
      text = var.ingest_hmac_key
    },
    {
      name = "ACCESS_CLIENT_ID"
      type = "secret_text"
      text = cloudflare_zero_trust_access_service_token.mail_ingest[0].client_id
    },
    {
      name = "ACCESS_CLIENT_SECRET"
      type = "secret_text"
      text = cloudflare_zero_trust_access_service_token.mail_ingest[0].client_secret
    },
    {
      # Personal address -> secret_text so it is not shown in the dashboard.
      name = "FALLBACK"
      type = "secret_text"
      text = var.fallback_address
    },
  ]

  # Workers Logs (free tier) -- the Worker logs one JSON line per message,
  # without addresses.
  observability = {
    enabled = true
  }
}
