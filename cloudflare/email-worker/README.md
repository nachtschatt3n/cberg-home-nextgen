# mail-ingest Email Worker

Cloudflare Email Worker that takes every inbound message for the zone (Email Routing catch-all) and hands it to the in-cluster `mail-ingest` shim. The shim passes it to Stalwart over SMTP.

```
sender MTA -> Cloudflare MX (Email Routing, SPF/DMARC enforced)
           -> this Worker  -- HTTPS + Access service token + HMAC -->
              https://mail-ingest.<domain>/v1/ingest  (tunnel -> envoy-external)
           -> mail-ingest shim -- SMTP :25 --> Stalwart
```

| Shim answer | Worker action |
|---|---|
| `200` | Done. Stalwart accepted the message. |
| `422` | `message.setReject(<Stalwart's SMTP reply>)`: permanent bounce, for example an unknown mailbox or spam. |
| Anything else (`503`, `401`/`403` from Access, `5xx`), a thrown fetch, or a timeout after 25 s | `message.forward(FALLBACK)` to the verified fallback mailbox, so no mail is lost while the cluster is down. |

Email Routing cannot defer a message. An uncaught exception is a permanent bounce, so every path is wrapped. If even `forward()` fails, the Worker calls `setReject` with a 451 text so the sender gets a readable bounce.

## Deployment

**Terraform only.** Do not use wrangler or the dashboard. `terraform/cloudflare/email_worker.tf` uploads `worker.js` as-is (an ES module with no build step) under the script name `mail-ingest-email`, with these bindings:

| Binding | Type | Source |
|---|---|---|
| `SECRET_DOMAIN` | plain_text | `TF_VAR_secret_domain` (cluster-secrets) |
| `HMAC_KEY` | secret_text | `terraform/cloudflare/email.sops.yaml` `ingest-hmac-key`. The same value as the cluster's `INGEST_HMAC_KEY`. |
| `ACCESS_CLIENT_ID` / `ACCESS_CLIENT_SECRET` | secret_text | `cloudflare_zero_trust_access_service_token.mail_ingest` |
| `FALLBACK` | secret_text | `email.sops.yaml` `fallback-address` (must be a verified routing address) |

The rollout switches live in `terraform/cloudflare/email.auto.tfvars`:

1. `mail_edge_enabled = true` creates the Access app and token, the WAF skip rule, this Worker and the fallback address. After this step, click the verification mail sent to the fallback address.
2. `mail_dns_enabled = true` publishes SPF, DMARC, DKIM and Brevo records.
3. `mail_inbound_enabled = true` turns on Email Routing, which publishes the MX records, and sets catch-all → Worker. **Mail starts arriving at this step.**

Rollback: set `mail_catch_all_mode = "forward"` to send everything straight to the fallback address, or set `mail_inbound_enabled = false` to remove the MX records.

## Request contract

```
POST /v1/ingest                      body = message.raw (exactly message.rawSize bytes)
CF-Access-Client-Id / -Secret        Access service token
X-Env-From, X-Env-To                 encodeURIComponent(envelope address)
X-Ts                                 unix seconds (shim allows ±300 s)
X-Raw-Size                           message.rawSize
X-Sig                                hex HMAC-SHA256(HMAC_KEY, `${ts}\n${from}\n${to}\n${rawSize}`)
                                     over the DECODED addresses
```

The body is deliberately left out of the HMAC. Hashing up to 25 MiB would exceed the free plan's roughly 10 ms CPU budget per message; network wait time does not count toward that budget. The exact length binds the body instead.

## Implementation notes

- **Streaming body:** `message.raw` is a `ReadableStream` that can be read once. It is piped through the Workers-runtime `FixedLengthStream(rawSize)`, so the request carries a `Content-Length` instead of chunked encoding. If the byte count does not match, the fetch errors and the Worker falls back to forwarding. `duplex: "half"` is only a Node/undici requirement. workerd ignores it, and the Worker passes it so the module also runs under Node for tests.
- **Forward after reading:** `forward()` runs after `raw` has been consumed. Cloudflare forwards the original message it holds, not the stream. **Verify during Phase 3 by scaling Stalwart to 0.** The fallback copy must arrive complete.
- **Timeout:** an `AbortController` aborts the request after 25 s. The shim's own SMTP timeout is 20 s, so a slow Stalwart returns 503 before the Worker gives up.
- **Exports:** the default export is the only one. workerd treats named exports as entrypoints, so the test hooks hang off `default._test`.
- **Logs:** Workers Logs are enabled in Terraform. The Worker logs one JSON line per message (`delivered` / `rejected` / `fallback`) and never logs addresses.

## Tests

```
cd cloudflare/email-worker && node --test
```

The tests use mocked `fetch` and message objects. They cover 200, 422 (JSON and plain text, truncation), 503/5xx/4xx/3xx → forward, a thrown fetch, a timeout, a failing `forward()`, a non-ASCII envelope, and the HMAC matching the shim's definition.
