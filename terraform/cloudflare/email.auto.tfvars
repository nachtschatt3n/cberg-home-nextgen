# Own-domain mail rollout switches (non-secret; see variables.tf). Flip in a
# commit so the intended Cloudflare state is recorded in git -- a bare
# `./tf apply` without these would otherwise DESTROY the mail edge.
# Secrets/domain-bearing values come from SOPS via ./tf, never from this file.
mail_edge_enabled    = false
mail_dns_enabled     = false
mail_inbound_enabled = false
mail_catch_all_mode  = "worker"
