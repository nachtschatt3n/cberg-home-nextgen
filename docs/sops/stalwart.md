# SOP: Stalwart Mail Server

> Description: Run, configure, verify and recover the in-cluster Stalwart mail server (`office/stalwart`) that hosts own-domain mail.
> Version: `2026.09.29`
> Last Updated: `2026-09-29`
> Owner: `cberg-agent`

---

## 1) Description

Stalwart (v0.16.x) is the own-domain mail server: SMTP (MTA + submission), IMAP,
JMAP and a web admin UI, all from a single binary. This SOP covers the phase-1
internal deployment and the operational model that later phases (Brevo relay,
Cloudflare Email Routing ingest, LAN LoadBalancer) build on.

- Scope: `kubernetes/apps/office/stalwart/`, `kubernetes/apps/monitoring/kube-prometheus-stack/app/stalwart-alerts.yaml`
- Prerequisites: repo mise env (`kubectl`, `sops`), `stalwart-cli` >= 1.0.13 on the Mac
  (`brew install stalwartlabs/tap/stalwart-cli`, or the release tarball from
  `github.com/stalwartlabs/cli`, verify its `.sha256`)
- Out of scope: Cloudflare side (Terraform in `terraform/cloudflare/`), the
  `mail-ingest` shim (phase 3), client LoadBalancer (phase 4)

**The v0.16 config model — read this first.** Since v0.16 the only file on disk
is `config.json`, and it names **only the datastore** (RocksDB here). Every other
setting — domains, listeners, DKIM keys, certificates, relay routes, accounts,
metrics auth, log output — is a JMAP object **inside the datastore**. The live
store is therefore the source of truth; git holds a *seed plan* that re-converges
it (`bootstrap/plan.ndjson.tmpl`), not a projection Flux reconciles. The same
rule as blueprint gotcha #14 ("a ConfigMap can be a SEED") applies.

---

## 2) Overview

| Setting | Value |
|---------|-------|
| Namespace | `office` |
| Image | `stalwartlabs/stalwart:v0.16.24@sha256:ec011be2…` (uid/gid 2000) |
| Chart | bjw-s `app-template` 5.1.0, single replica, `strategy: Recreate` |
| Datastore | RocksDB at `/var/lib/stalwart/data` on `longhorn-static` volume `stalwart-data` (20Gi, `Retain`) |
| Config seed | `kubernetes/apps/office/stalwart/bootstrap/plan.ndjson.tmpl` + `apply-bootstrap.sh` |
| Secrets | `stalwart-secret` (SOPS): `STALWART_RECOVERY_ADMIN`, `RECOVERY_ADMIN_USER/PASSWORD`, `METRICS_USERNAME/PASSWORD`, `INGEST_HMAC_KEY`, `MATHIAS_PASSWORD`, `BREVO_SMTP_USERNAME/PASSWORD` (placeholders until phase 2) |
| TLS | cert-manager `Certificate stalwart-mail` → secret `stalwart-tls` (`mail.<domain>`, letsencrypt-production DNS-01), mounted at `/etc/stalwart-tls` (directory, no subPath) |
| Web admin / JMAP | `https://stalwart.<domain>` via HTTPRoute on `envoy-internal` (LAN/VPN only) |
| Metrics | `/metrics/prometheus` on 8080, basic auth (`prometheus` / `METRICS_PASSWORD`) |
| DNS resolver | Custom: 1.1.1.1 + 9.9.9.9 (UDP) — the in-cluster split-DNS view has no MX/TXT |
| Max message size | 30 MiB (`Email.maxMessageSize` and `MtaStageData.maxMessageSize`) |

**Listener / port layout (all ClusterIP `stalwart`, no LoadBalancer yet):**

| Listener | Port | Protocol | TLS | Purpose |
|----------|------|----------|-----|---------|
| `http` | 8080 | HTTP | none (TLS at Envoy) | web admin, JMAP, health, metrics |
| `smtp` | 25 | SMTP | STARTTLS offered | **internal only** — delivery target for the phase-3 ingest shim; never on a LoadBalancer |
| `submissions` | 465 | SMTP | implicit | client submission |
| `submission` | 587 | SMTP | STARTTLS | client submission |
| `imaps` | 993 | IMAP4 | implicit | mail clients |

The image defaults (443 HTTPS, 4190 ManageSieve, 995 POP3S) are removed by the
plan's `reconcile` on `NetworkListener`. 143 (plain IMAP) is not configured.

---

## 3) Blueprints

- Source of truth file(s): the live datastore; seeded from
  `kubernetes/apps/office/stalwart/bootstrap/plan.ndjson.tmpl` (NDJSON `stalwart-cli apply`
  plan; `@DOMAIN@` is substituted by the script from `cluster-secrets.sops.yaml`)
- Apply script: `kubernetes/apps/office/stalwart/bootstrap/apply-bootstrap.sh`
- Related manifests: `kubernetes/apps/office/stalwart/app/*.yaml`, `ks.yaml`
- Hand-applied, NOT in kustomization: `app/longhorn-volume.yaml` (Longhorn `Volume` CR)

What the plan declares:

| Op | Object | Notes |
|----|--------|-------|
| create (first run only) | `Certificate` | PEM read from `File` `/etc/stalwart-tls/tls.{crt,key}`; SANs are server-set, so no natural key — the script skips it when one exists and wires its id into `SystemSettings` |
| upsert | `Domain` | `<domain>`, DKIM `Automatic` with RSA-SHA256 + Ed25519-SHA256, DNS + cert management `Manual`, sub-addressing on |
| reconcile | `NetworkListener` | exactly the 5 listeners above; anything else is deleted |
| reconcile | `Tracer` | exactly one `Stdout` tracer (the image default is a log FILE under `/var/log`, which never reaches Elasticsearch and fails on the read-only root fs); excludes `http.x-forwarded-missing` (see Troubleshooting) |
| upsert | `MtaRoute` `brevo` | Relay `smtp-relay.brevo.com:587`, secret from env `BREVO_SMTP_PASSWORD`. **Disabled** by not being referenced from `MtaOutboundStrategy.route` (routes have no enable flag) |
| upsert | `Account` `mathias` | added at runtime by the script with `MATHIAS_PASSWORD` (an account password is a plain `secret` string — it cannot reference an env var, which is why this is not a Flux Job) |
| update | `SystemSettings` | default domain, `mail.<domain>` hostname, default certificate |
| update | `MtaStageConnect`, `DnsResolver`, `Metrics`, `Email`, `MtaStageData`, `Http` | SMTP hostname, public resolvers, Prometheus basic auth (env `METRICS_PASSWORD`), 30 MiB, `useXForwarded: true` (Envoy is the HTTP client) |

Plan encoding notes (verified against v0.16.24): sets are JSON objects
(`{"value": true}`), object lists are index-keyed objects (`{"0": {...}}`),
expressions are `{"else": "<expr>", "match": {}}`, multi-variant values carry
`"@type"`, secrets use `{"@type":"EnvironmentVariable","variableName":"X"}`.

---

## 4) Operational Instructions

### 4.1 First deployment (done 2026-09-29)

1. Hand-apply the Longhorn volume once:
   `mise exec -- kubectl apply -f kubernetes/apps/office/stalwart/app/longhorn-volume.yaml`
2. Commit + push the manifests; Flux creates PV/PVC, Certificate, Deployment.
3. Port-forward the management listener:
   `mise exec -- kubectl port-forward -n office svc/stalwart 18080:8080`
4. Seed the store: `./kubernetes/apps/office/stalwart/bootstrap/apply-bootstrap.sh`
   (`--dry-run` validates the plan client-side only).
5. Reload settings (step 4.3). Listener changes additionally need a pod roll (4.4).

### 4.2 Changing configuration

Edit `plan.ndjson.tmpl`, run `apply-bootstrap.sh` (it is idempotent: a re-run
reports `0 created`), reload (4.3), commit the template. A change made only in the
web UI is drift — mirror it into the plan or export it (4.6).

### 4.3 Reload without restart

Most settings (metrics, tracer, DNS, limits, certificates) take effect after:

```bash
printf '%s\n' \
  '{"@type":"create","object":"Action","value":{"a1":{"@type":"ReloadSettings"}}}' \
  '{"@type":"create","object":"Action","value":{"a2":{"@type":"ReloadTlsCertificates"}}}' \
  > /tmp/stalwart-reload.ndjson
stalwart-cli apply --file /tmp/stalwart-reload.ndjson   # STALWART_URL/USER/PASSWORD exported
```

### 4.4 Listener changes need a pod roll — through git

`ReloadSettings` does **not** bind or close ports. Bump the pod annotation
`stalwart.cberg/listener-revision` in `app/helmrelease.yaml`, commit, push.
(`Recreate` means a short outage; that is expected.)

### 4.5 Certificate renewal

cert-manager renews `stalwart-tls`; the whole-directory mount updates the files
and Reloader (`reloader.stakater.com/auto`) restarts the pod, which re-reads the
PEM files. Nothing to do by hand.

### 4.6 Export (drift check / backup of config)

```bash
stalwart-cli snapshot Domain NetworkListener Tracer MtaRoute SystemSettings \
  MtaStageConnect DnsResolver Metrics Email MtaStageData Http \
  --output /tmp/stalwart-snapshot.ndjson        # secrets stripped by default
```

Diff it against the rendered plan. Never commit a snapshot (it contains the domain).

### 4.7 DKIM public keys (for the Terraform DNS records)

```bash
stalwart-cli query DkimSignature                       # selectors + algorithms
stalwart-cli get Domain <domain-id> --json \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["dnsZoneFile"])' \
  | grep -A3 _domainkey
```

Use **only** the `_domainkey` TXT records from that zone file. The rest of it is
Stalwart's generic suggestion (MX to `mail.`, `p=reject` DMARC, SRV/TLSA for
443/995) and does NOT match this design — MX/SPF/DMARC are owned by
`terraform/cloudflare/email_dns.tf`. Selectors follow `v{version}-{algorithm}-{date}`
(e.g. `v1-rsa-20260929`, `v1-ed25519-20260929`). Automatic rotation only runs with
automatic DNS management, which is off here, so keys stay stable until rotated
deliberately.

---

## 5) Examples

### Example 1: Add a mailbox

Add an `Account` op (the script's inline python is the pattern) with a password
stored as a new key in `stalwart-secret`, run the script, verify IMAP login (6.4).

### Example 2: Enable the Brevo relay (phase 2)

Put real `BREVO_SMTP_USERNAME/PASSWORD` into the SOPS secret, set `authUsername`
in the `brevo` route, and add an `MtaOutboundStrategy` update whose `route`
expression returns `'brevo'` for non-local recipients
(`{"else":"'brevo'","match":{"0":{"if":"is_local_domain(rcpt_domain)","then":"'local'"}}}`).
Reload, then send a test to an external mailbox.

---

## 6) Verification Tests

### Test 1: Flux + pod

```bash
mise exec -- flux get kustomizations -n office stalwart
mise exec -- flux get helmreleases -n office stalwart
mise exec -- kubectl get pod -n office -l app.kubernetes.io/name=stalwart   # 1/1, 0 restarts
```

### Test 2: Health endpoints (via port-forward)

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:18080/healthz/ready   # 200
```

### Test 3: Web admin through Envoy (LAN)

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://stalwart.<domain>/            # 302 -> /account
curl -s -o /dev/null -w '%{http_code}\n' https://stalwart.<domain>/login       # 200
```

### Test 4: IMAPS + submission login

Port-forward 993/587, connect with SNI `mail.<domain>` and full certificate
verification (python `imaplib.IMAP4_SSL` with a custom socket), log in as the
operator account, `SELECT INBOX`; for 587 do `EHLO`, `STARTTLS`, `AUTH`.

### Test 5: Metrics scraped + rules loaded

```bash
# Prometheus: up{namespace="office",service="stalwart"} == 1
# /api/v1/rules contains group stalwart.pods.health, stalwart.scrape, stalwart.auth
```

### Test 6: Logs in Elasticsearch

`logs-generic-default`, filter `resource.attributes.k8s.namespace.name: office`
and `resource.attributes.k8s.container.name: app`, pod prefix `stalwart-`.

### Test 7: Storage

```bash
mise exec -- kubectl get volume -n storage stalwart-data   # attached, healthy
```

---

## 7) Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `/metrics/prometheus` returns 404 | Prometheus exporter not enabled in the store, or not reloaded | apply plan, reload (4.3) |
| New port refuses connections after apply | listeners bind only at start | bump `listener-revision` (4.4) |
| Log flood `X-Forwarded-For header is missing` | `useXForwarded: true` and kubelet probes / Prometheus / port-forward send no XFF | event is excluded in the Stdout tracer; re-apply plan if the tracer was reset |
| No pod logs at all | tracer is the image-default log FILE | re-apply plan (reconciles to Stdout) |
| Web logins from everyone look like one IP / Envoy IP banned | `useXForwarded` off | keep `Http.useXForwarded: true` |
| PVC `Pending` | Longhorn `Volume` CR not applied | step 4.1.1 |
| Pod stuck `ContainerCreating`, `secret "stalwart-tls" not found` | certificate not issued yet | wait for `Certificate stalwart-mail` Ready (DNS-01, ~1-2 min) |

---

## 8) Diagnose Examples

```bash
mise exec -- kubectl logs -n office deploy/stalwart --tail=100
mise exec -- kubectl describe certificate -n office stalwart-mail
stalwart-cli query NetworkListener        # what the store declares
stalwart-cli query Tracer
stalwart-cli query QueuedMessage          # outbound queue (phase 2+)
```

---

## 9) Health Check

- Pod Ready, 0 restarts; `StalwartPodNotReady`/`CrashLooping`/`Restarted` quiet
- `up{namespace="office",service="stalwart"} == 1` (`StalwartMetricsAbsent` guards it)
- `Certificate stalwart-mail` Ready, `notAfter` > 30 days
- Longhorn `stalwart-data` healthy and in the daily backup set

---

## 10) Security Check

- `stalwart-secret` stays SOPS-encrypted; no plaintext passwords in the plan template
- No LoadBalancer Service and no route on `envoy-external` for 8080/993/465/587
  until the planned phases; port 25 is never exposed outside the cluster
- `STALWART_RECOVERY_ADMIN` is the break-glass admin; rotate it via the SOPS secret
  (Reloader rolls the pod)
- `INGEST_HMAC_KEY` is shared with the Terraform email stack (phase 3); rotate both together
- `useXForwarded: true` means an in-cluster client talking to 8080 directly could
  spoof its IP for rate limiting — acceptable while 8080 is ClusterIP-only

---

## 11) Rollback Plan

- Config: re-apply a previous `plan.ndjson.tmpl` from git, or a saved snapshot (4.6)
- Manifests: `git revert <sha> && git push`
- Data: the PV is `Retain`; restore `stalwart-data` from the Longhorn backup
  (`docs/sops/backup.md`). All config lives in the same volume, so one restore
  brings back mail and settings together.

---

## 12) References

- Plan: phases 1-5 (own-domain mail via Cloudflare Email Routing + Brevo)
- Upstream: `github.com/stalwartlabs/stalwart/blob/main/UPGRADING/v0_16.md`,
  `stalw.art/docs/management/cli/apply`, `stalw.art/docs/cluster/orchestration/kubernetes/`
- `docs/sops/longhorn.md`, `docs/sops/gateway-api-httproute.md`, `docs/sops/new-deployment-blueprint.md`

---

## Version History

| Version | Date | Change |
|---------|------|--------|
| 2026.09.29 | 2026-09-29 | Initial SOP (phase 1 internal deployment) |
