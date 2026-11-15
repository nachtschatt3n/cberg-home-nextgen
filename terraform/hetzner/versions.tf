terraform {
  required_version = ">= 1.6"
  required_providers {
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "~> 1.70"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
  backend "kubernetes" {
    secret_suffix = "hetzner-tfstate"
    namespace     = "flux-system"
  }
}

provider "hcloud" {
  token = var.hcloud_token
}
