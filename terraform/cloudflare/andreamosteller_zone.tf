# Secondary Cloudflare zone for the legacy site's custom domain.
# Terraform owns ONLY the zone. Apex and www records are CNAMEs to the tunnel,
# created by external-dns from the DNSEndpoint in
# kubernetes/apps/network/external/cloudflared/dnsendpoint.yaml (cutover done;
# the two static A records that lived here until then were removed).
resource "cloudflare_zone" "andreamosteller" {
  account = {
    id = data.cloudflare_zone.main.account.id
  }
  name = var.andreamosteller_domain
  type = "full"
}
