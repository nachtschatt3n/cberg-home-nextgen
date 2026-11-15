variable "cloudflare_api_token" {
  type      = string
  sensitive = true
}

variable "zone_id" {
  type      = string
  sensitive = true
}

# Secondary zone. The domain name is a secret (public repo) and lives only in
# cluster-secrets.sops.yaml as SECRET_DOMAIN_ANDREAMOSTELLER; ./tf exports it.
variable "andreamosteller_domain" {
  type      = string
  sensitive = true
}

variable "andreamosteller_origin_ip" {
  type        = string
  description = "Current origin (mittwald) until cutover to the tunnel"
  default     = "37.202.4.23"
}
