# Off-site backup storage. Names are deliberately neutral (public repo).
resource "random_password" "box" {
  length           = 32
  special          = true
  override_special = "-_."
}

resource "random_password" "sub" {
  length           = 32
  special          = true
  override_special = "-_."
}

resource "hcloud_storage_box" "backup" {
  name             = "offsite-1"
  storage_box_type = "bx21"
  location         = "fsn1"
  password         = "${random_password.box.result}"
  ssh_keys         = [var.admin_pubkey]

  access_settings = {
    ssh_enabled          = true
    reachable_externally = true
    samba_enabled        = false
    webdav_enabled       = false
    zfs_enabled          = false
  }

  # Hetzner snapshots are the ransomware safeguard: they are managed through
  # the console/API, not over SFTP, so a stolen backup key cannot delete them.
  snapshot_plan = {
    max_snapshots = 10
    hour          = 2
    minute        = 30
  }

  delete_protection = true

  lifecycle {
    ignore_changes  = [ssh_keys]
    prevent_destroy = true
  }
}

resource "hcloud_storage_box_subaccount" "restic" {
  storage_box_id = hcloud_storage_box.backup.id
  name           = "restic"
  home_directory = "r/"
  password       = "${random_password.sub.result}"

  access_settings = {
    ssh_enabled          = true
    reachable_externally = true
    samba_enabled        = false
    webdav_enabled       = false
  }
}

output "box_server" {
  value     = hcloud_storage_box.backup.server
  sensitive = true
}

output "box_username" {
  value     = hcloud_storage_box.backup.username
  sensitive = true
}

output "sub_username" {
  value     = hcloud_storage_box_subaccount.restic.username
  sensitive = true
}
