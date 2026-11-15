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

# Second secondary zone (live mail). Name is secret, see SECRET_DOMAIN_MATHIASUHL.
variable "mathiasuhl_domain" {
  type      = string
  sensitive = true
}

# Extra records (DKIM, DMARC, TXT, ...) as a JSON list kept SOPS-encrypted in
# SECRET_MATHIASUHL_EXTRA_RECORDS. Names are relative to the zone ("@" = apex).
# Example: [{"name":"google._domainkey","type":"TXT","content":"v=DKIM1; ..."}]
# Optional keys per item: ttl (default 300), priority (MX/SRV).
variable "mathiasuhl_extra_records" {
  type      = string
  sensitive = true
  default   = "[]"
}
