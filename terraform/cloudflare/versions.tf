terraform {
  required_version = ">= 1.6"
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 5.0"
    }
  }
  backend "kubernetes" {
    secret_suffix = "cloudflare-tfstate"
    namespace     = "flux-system"
  }
}

provider "cloudflare" {
  api_token = var.cloudflare_api_token
}
