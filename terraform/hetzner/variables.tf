variable "hcloud_token" {
  type      = string
  sensitive = true
}

# Public half of the admin SSH key. The box accepts keys at CREATE ONLY, so this
# is ignored after creation (see lifecycle in main.tf). The private half lives
# in the SOPS-encrypted off-site backup secret, never in this directory.
variable "admin_pubkey" {
  type = string
}
