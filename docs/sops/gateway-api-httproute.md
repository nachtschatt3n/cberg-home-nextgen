# SOP: Gateway API / HTTPRoute Routing (Envoy Gateway)

> Description: How HTTP ingress works in this cluster now that ingress-nginx is gone — writing, reviewing and debugging HTTPRoutes on the two Envoy Gateways, including forward-auth, backend TLS, timeouts and the verification gate that catches the failures which are invisible at apply time.
> Version: `2026.09.07`
> Last Updated: `2026-09-07`
> Owner: `homelab operator (cberg-home-nextgen)`

---

## 1) Description

On **2026-09-07** the migration from ingress-nginx to Envoy Gateway completed.
ingress-nginx is **deleted**: zero `Ingress` objects, zero `IngressClass`
objects, zero nginx controllers cluster-wide. All HTTP traffic is carried by
**104 HTTPRoutes** attached to two Gateways.

This SOP is the durable form of the conversion knowledge that previously lived
in `docs/troubleshooting/envoy-phase2-conversion-pattern.md` (deleted with this
SOP's creation, per the repo's troubleshooting-doc lifecycle rule). **Every
numbered rule below cost a real failure or a near-miss on migration day.** They
are not style preferences.

- **Scope**: every HTTP-exposed application in the cluster; namespace `network`
  (Gateways, GatewayClass, gateway-scoped policies), `kube-system` (Authentik
  outposts + their ReferenceGrants), and each app's own namespace (its
  HTTPRoute / SecurityPolicy / BackendTLSPolicy / Backend).
- **Prerequisites**: `kubectl` against the cluster (VLAN 55, LAN-only), repo
  write access, `dig`, `curl`. GitOps via Flux — no direct cluster edits except
  the two documented manual steps (Authentik outpost Ingress delete, which no
  longer applies once all outposts are converted; and Longhorn Volume CRs,
  unrelated).
- **Out of scope**: L4 load balancing (Cilium LB-IPAM), the cloudflared tunnel
  internals (`docs/sops/cloudflare.md`), split-horizon DNS
  (`docs/sops/k8s-gateway-dns.md`), and Envoy Gateway version upgrades
  (`docs/sops/envoy-gateway-upgrade.md`).

---

## 2) Overview

| Setting | Value |
|---------|-------|
| GatewayClass | `envoy` |
| Internal Gateway | `envoy-internal` in `network` — LB **192.168.55.103**, 68 hostnames / 79 routes |
| External Gateway | `envoy-external` in `network` — LB **192.168.55.104**, 25 hostnames / 27 routes |
| Total HTTPRoutes | 104 |
| Listeners (both) | `http` (80, redirect-only) and `https` (443, Terminate, wildcard cert `${SECRET_DOMAIN/./-}-production-tls`) |
| Source of truth | `kubernetes/apps/network/envoy-gateway/app/` (`gateways.yaml`, `policies.yaml`, `gatewayclass.yaml`, `helmrelease.yaml`) |
| Per-app routes | `kubernetes/apps/<ns>/<app>/app/httproute.yaml`, or the bjw-s `route:` values key in the HelmRelease |
| ReferenceGrants | `kubernetes/apps/kube-system/authentik/app/referencegrants.yaml` — **all of them, always in kube-system** |
| Internal DNS | k8s-gateway at **192.168.55.101** watches HTTPRoutes and answers `*.${SECRET_DOMAIN}` with the parent Gateway's LB IP |
| External DNS | external-dns `--source=gateway-httproute --cloudflare-proxied`; target read from the **Gateway** annotation |
| External path | Cloudflare edge → cloudflared tunnel wildcard → `envoy-external` (192.168.55.104) |
| Gateway-wide request timeout | **60s**, in the single `BackendTrafficPolicy` `envoy-compression` |
| Envoy's own route default | **15s** — the reason the above exists |
| Critical dependency | k8s-gateway (internal), cloudflared + Cloudflare DNS (external), Authentik outposts (forward-auth apps) |

**The two shapes an app can take:**

- **Shape A — bjw-s `app-template` charts**: use the chart's `route:` values
  key in the HelmRelease. Rules default to the primary Service.
- **Shape B — any other chart**: set the chart's own `ingress.enabled: false`
  and add a standalone `httproute.yaml` to the app directory plus its
  `kustomization.yaml`.

---

## 3) Blueprints

- Gateways + the external-dns target annotation:
  `kubernetes/apps/network/envoy-gateway/app/gateways.yaml`
- Gateway-scoped policies (compression, timeout, client-IP detection):
  `kubernetes/apps/network/envoy-gateway/app/policies.yaml`
- Extension API enablement (`Backend`):
  `kubernetes/apps/network/envoy-gateway/app/helmrelease.yaml` →
  `config.envoyGateway.extensionApis.enableBackend: true`
- Cluster-wide HTTP→HTTPS redirect (owns the `http` listener on both gateways):
  `kubernetes/apps/network/envoy-gateway/app/httproute-https-redirect.yaml`
- Forward-auth ReferenceGrants:
  `kubernetes/apps/kube-system/authentik/app/referencegrants.yaml`
- Authentik outpost blueprints (the `kubernetes_disabled_components` key):
  `kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml`

Minimal HTTPRoute blueprint — the shape every app starts from:

```yaml
---
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: <app>
  namespace: <app-ns>
  labels:
    gethomepage.dev/enabled: "true"      # the LABEL, Homepage needs both
  annotations:
    gethomepage.dev/enabled: "true"
    gethomepage.dev/name: "<App>"
    gethomepage.dev/group: "<Group>"
    gethomepage.dev/icon: "<icon>.png"
spec:
  parentRefs:
    - group: gateway.networking.k8s.io
      kind: Gateway
      name: envoy-internal              # or envoy-external
      namespace: network
      sectionName: https                # NEVER http — see rule 2
  hostnames:
    - "<app>.${SECRET_DOMAIN}"
  rules:
    - matches:
        - path: { type: PathPrefix, value: / }
      backendRefs:
        - group: ""
          kind: Service
          name: <service>
          port: <NUMBER>                # resolved by hand — see rule 6
      timeouts:
        request: 60s                    # only if >60s is needed; see rule 5
        backendRequest: 60s
```

---

## 4) Operational Instructions

### 4.1 The ten load-bearing rules

**1. Gateway choice determines everything downstream.** `envoy-internal`
(.103) for LAN-only apps, `envoy-external` (.104) for anything reachable from
the internet through the cloudflared tunnel. There is no third option and no
per-route override of the publication path.

**2. `sectionName: https` only.** The `http` listener on both gateways is owned
cluster-wide by `httproute-https-redirect`, which 301s every host. Attaching an
app route to `http` fights it.

**3. external-dns target belongs on the GATEWAY, never on the route.**
external-dns runs `--source=gateway-httproute`; for that source it derives each
record's target from the **parent Gateway's** annotation and an
`external-dns.alpha.kubernetes.io/target` on the HTTPRoute is **silently
ignored**. `envoy-external` carries
`external-dns.alpha.kubernetes.io/target: "external.${SECRET_DOMAIN}"` so every
attached route publishes a CNAME to the tunnel hostname — exactly what the
Ingresses did. Getting this wrong on 2026-09-07 published an **A record to the
RFC1918 gateway IP**; Cloudflare refuses a private target for a proxied record,
the old CNAME had already been withdrawn with the Ingress, and the hostname
went dark publicly until the commit was reverted (`c41f0ff4` →
`0cf4cfcc` → `65dc2b7f`). **Never add a target annotation to a route.**

**4. Ingress removal and HTTPRoute creation go in ONE commit.** Historically
both kinds were watched simultaneously; leaving both alive produced two DNS
records and non-deterministic resolution. With nginx deleted this now means:
never land a route that replaces something without removing the something.

**5. Move the `gethomepage.dev/*` annotations AND the
`gethomepage.dev/enabled: "true"` LABEL** onto the route. Homepage runs
`kubernetes.gateway: true` and `kubernetes.ingress: true` in parallel, so a
tile vanishes only when the annotations are dropped — never because of the
migration itself.

**6. Do NOT carry `nginx.ingress.kubernetes.io/*` annotations across.** They
have no meaning on an HTTPRoute. Each one must be either translated (see §4.2)
or explicitly recorded as deliberately dropped, in a comment, with the reason.

**7. Never point a `backendRef` at an ExternalName Service.** Envoy Gateway
resolves backends through EndpointSlices; ExternalName has none. Point at the
real Service, cross-namespace if needed (which requires a ReferenceGrant).

**8. Named Service ports must be resolved to numbers by hand.** An HTTPRoute
`backendRef.port` takes a **number**, and the obvious guess is regularly wrong
because charts render the container port as `targetPort` and hardcode the
Service port:

| App | Guess | Actual Service port |
|-----|-------|---------------------|
| influxdb (`influxdb-influxdb2`) | 8086 | **80** |
| open-webui | 8080 | **80** |

A wrong port still reports `Accepted=True` and `ResolvedRefs=True` and simply
does not work. Always resolve it live:

```bash
kubectl get svc -n <ns> <svc> -o custom-columns=NAME:.metadata.name,PORTS:.spec.ports
```

**9. `postRenderers` patches targeting `kind: Ingress` match nothing** now that
no Ingress renders, and kustomize then **fails the ENTIRE post-render**,
stopping the HelmRelease installing. Seven instances were found on migration
day.

> **CRITICAL COROLLARY — this caused a live outage.** Remove *only the
> Ingress-targeting patch*, **never the whole `postRenderers` block**. On
> `anythingllm` the block held two patches; removal logic that keyed on "does
> this block mention `kind: Ingress` anywhere" deleted the Deployment patch
> too, destroying `strategy: Recreate`. A single-replica Deployment on an RWO
> Longhorn PVC then surged a second pod that deadlocked forever on
> `Multi-Attach` (`e0968989` broke it, `07c8f1ff` restored it; see
> `docs/sops/longhorn-rwo-multi-attach.md`). The correct test is **"does this
> block contain patches that do NOT target Ingress"** — if yes, surgically
> remove one patch and leave the rest.

**10. Only ONE `BackendTrafficPolicy` may target a given Gateway.** A second is
rejected `Accepted=False reason=Conflicted` and **silently does nothing rather
than merging**. Every gateway-wide backend setting must therefore live in the
single existing object `envoy-compression` in
`kubernetes/apps/network/envoy-gateway/app/policies.yaml`, whatever its name
suggests. Add there; never create a sibling. (Learned via `e6e64e5a` →
`382a01c5`, "merged, not a second policy".)

### 4.2 Timeouts — the silent tightening

nginx's `proxy-read-timeout`/`proxy-send-timeout` default is **60s**. **Envoy's
own route default is 15s.** Phase 2 converted 48 rules with zero timeouts,
silently tightening every migrated app from 60s to 15s. The gateway-wide
`BackendTrafficPolicy` now restores parity with `timeout.http.requestTimeout:
60s`; per-route `rules[].timeouts` overrides it and wins.

| Case | Setting |
|------|---------|
| Ordinary app | nothing — inherits the gateway's 60s |
| App whose Ingress set an explicit longer `proxy-read-timeout` | carry that number explicitly (nextcloud: `300s`) |
| Streaming / long-poll / websocket-capable apps | `3600s` (anythingllm, librechat, open-webui, jellyfin, immich, teslamate, matter-server, mosquitto, iobroker, ha-ai-harness …) |
| **Persistent** websockets | **`0s`** = no timeout, per the Gateway API spec (nextcloud `/push` → `nextcloud-notify-push`) |

> **A `curl /` check returns in milliseconds and can NEVER detect a timeout
> regression.** This class of defect is invisible to the smoke test and
> surfaces days later as truncated downloads, severed notification channels,
> and BI query pages that die partway. Timeouts must be reasoned about at
> conversion time, from the annotations being replaced — not verified
> afterwards.

Other nginx annotations and where they went:

| nginx annotation | Gateway API equivalent |
|---|---|
| `proxy-read-timeout` / `proxy-send-timeout` | `HTTPRoute.rules[].timeouts` |
| `configuration-snippet` adding a response header | `filters: [ResponseHeaderModifier]` |
| `force-ssl-redirect` / `ssl-redirect` | already handled by `httproute-https-redirect` |
| `websocket-services` | nothing — Envoy passes HTTP/1.1 Upgrade natively |
| `proxy-buffering` / `proxy-request-buffering: off` | nothing — Envoy streams by default |
| `proxy-buffer-size` / `proxy-buffers-number` | Gateway-scoped `ClientTrafficPolicy` — **not** a route field |
| `proxy-body-size` | no route-level equivalent; Envoy streams uncapped (a **loosening**, not a break) |
| `use-forwarded-headers` | `ClientTrafficPolicy.clientIPDetection` (already set per gateway) |
| `auth-url` / `auth-signin` / `auth-response-headers` | `SecurityPolicy.extAuth` + a second HTTPRoute (§4.3) |
| `backend-protocol: HTTPS` | `BackendTLSPolicy`, or an EG `Backend` (§4.4) |

### 4.3 Forward-auth apps (Authentik proxy outposts)

An app is forward-auth protected if an **Authentik proxy outpost** exists for
its hostname. **Screen on the outpost, never on the app's own annotations** —
on 2026-09-07 nine outposts existed but only six apps carried `auth-url`;
`arag-web`, `uptime-kuma` and `kubernetes-dashboard` were missed and `arag-web`
broke in production (`04f9abc7`, reverted `d7ab1b74`).

Per forward-auth app you need **four** objects:

1. The **app HTTPRoute** (`/`).
2. A **separate, more specific callback HTTPRoute**
   (`/outpost.goauthentik.io`) pointing cross-namespace at
   `ak-outpost-<app>-forward-auth` in `kube-system`, port `9000`. Gateway API
   resolves by longest path match. Folded into one route, the login callback
   proxies to the app and loops.
3. A **ReferenceGrant** — see below.
4. A **SecurityPolicy** targeting **ONLY the app route** (targeting the
   callback route makes it require the auth it exists to establish), with
   `failOpen: false` and
   `path: /outpost.goauthentik.io/auth/envoy` (**never** `/auth/nginx` or
   `/auth/traefik` — those return 500 without their own dialect headers).

**ReferenceGrants: two traps at once.**

- A ReferenceGrant must live in the **TARGET service's namespace**, i.e.
  `kube-system`. And each app's Flux Kustomization sets
  `targetNamespace: <app-ns>`, which **silently rewrites any `namespace:`
  field in that app's directory** — so a grant written beside its app lands in
  the app namespace and **authorises nothing**. (Same trap as Longhorn Volume
  CRs.) They all live in
  `kubernetes/apps/kube-system/authentik/app/referencegrants.yaml`.
- Each grant needs **TWO `from` entries**, in **different API groups**:
  `gateway.networking.k8s.io`/`HTTPRoute` **and**
  `gateway.envoyproxy.io`/`SecurityPolicy`. An HTTPRoute-only grant leaves the
  SecurityPolicy rejected — the app is then **broken AND unprotected**, the
  worst of both.

**No Authentik provider change is needed.** A proxy outpost serves all four
dialects at once; `forward_single` is not an nginx/envoy setting. Do not edit
the provider in the SOPS blueprint.

**The outpost publishes its OWN Ingress — historical, but keep the mechanism.**
Authentik's Kubernetes outpost controller created an Ingress per outpost in
`kube-system` carrying the **app's** hostname on the **default** ingress class,
holding only `/outpost.goauthentik.io`. It was in no git repo and had no
ownerRefs, so withdrawing the app's own Ingress did not move the hostname —
real clients got a 404 while the app was perfectly healthy on .103. The fix,
per outpost, was two steps and **both are required**:

1. Set `kubernetes_disabled_components: [ingress]` on **that outpost's**
   `config` in `configmap.sops.yaml`, then apply the blueprint
   (`ak apply_blueprint`) — a ConfigMap change alone does nothing.
   > **Some blueprints already contain `kubernetes_disabled_components: []`
   > (REPLACE it) and some do not contain the key at all (ADD it).** A blind
   > search-and-replace silently skips the second case. Appending a duplicate
   > key is silently overridden — YAML is last-wins.
2. **Delete the existing Ingress by hand.** Disabling the component stops the
   controller *managing* it; it does not delete it.

Any future outpost must be created with the component already disabled.

### 4.4 Backend TLS — two mechanisms, and which to use

When a backend speaks TLS (what `backend-protocol: HTTPS` expressed), a plain
HTTPRoute sends cleartext at a TLS port and hard-fails. There are two options
and they are **not** interchangeable:

| Use | When | Example |
|---|---|---|
| Gateway API **`BackendTLSPolicy`** | the backend cert has usable **SANs** and a CA you can reference | `kibana` — ECK issues a SAN cert and publishes its CA, so verification is real. **Strictly better than nginx**, which set `backend-protocol: HTTPS` with no `proxy-ssl-verify` and defaults `proxy_ssl_verify` to *off*. |
| Envoy Gateway **`Backend`** with `tls.insecureSkipVerify: true` | verification is **structurally impossible** | `wazuh-dashboard` — the cert has **no subjectAltName at all** (`CN=wazuh-dashboard`, issued by `CN=wazuh-root-ca`, valid to 2036). Modern TLS matches on SANs and ignores CN. |

`BackendTLSPolicy` **requires** `hostname` and has **no** `insecureSkipVerify`,
so it cannot express nginx's `proxy-ssl-verify: off`. That is the whole reason
the second mechanism exists here. Two further details:

- `BackendTLSPolicy.targetRefs[].sectionName` is the **port NAME**, not the
  number. `5601` is silently wrong; use `https`.
- Reference the CA via a Secret the operator rotates (e.g.
  `kibana-kb-http-certs-public`) so renewals need no manual step.

> **The `Backend` resource is an OPT-IN extension API.** It requires
> `config.envoyGateway.extensionApis.enableBackend: true` in the Envoy Gateway
> HelmRelease. **Without it the object applies cleanly and dry-run passes**,
> but any route referencing it fails at **REQUEST time** with
> `ResolvedRefs=False` ("Backend is disabled in Envoy Gateway configuration")
> and serves **500** (`e23c12ee`).

### 4.5 Normal change flow

```bash
# 1. Screen: is this app forward-auth protected? (outpost, not annotations)
kubectl get deploy -n kube-system | grep 'ak-outpost-'

# 2. Resolve the real Service port to a NUMBER
kubectl get svc -n <ns> <svc> -o custom-columns=NAME:.metadata.name,PORTS:.spec.ports

# 3. Write/edit the route, then validate with the right API version
kubeconform -summary -ignore-missing-schemas kubernetes/apps/<ns>/<app>/
helm template ... --api-versions gateway.networking.k8s.io/v1/HTTPRoute   # shape A only

# 4. Commit GitOps-style (shared index: --only with explicit paths)
git commit --only kubernetes/apps/<ns>/<app>/app/httproute.yaml -F msg.txt
git push

# 5. Run the verification gate in section 6 — Accepted AND ResolvedRefs, dig,
#    and a public-path curl for external hosts. Do NOT stop at "Flux is green".
```

Shape-A (`app-template`) caveats:

- "rules can be omitted" holds **only** with exactly one enabled Service. With
  two, `_validate.tpl` hard-fails (`An explicit rule is required...`).
- `app-template` picks the route apiVersion from Helm **Capabilities**, so an
  offline `helm template` renders `v1alpha2`, which this cluster's CRD does not
  serve. Always pass
  `--api-versions gateway.networking.k8s.io/v1/HTTPRoute`, or you are
  validating a shape the API would reject. This affects CI too (`flux-local
  test` runs without cluster capabilities).

---

## 5) Examples

### Example A: plain internal app (the 80% case)

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: open-webui
  namespace: ai
  labels: { gethomepage.dev/enabled: "true" }
  annotations:
    gethomepage.dev/enabled: "true"
    gethomepage.dev/name: "Open WebUI"
    gethomepage.dev/group: "AI"
spec:
  parentRefs:
    - group: gateway.networking.k8s.io
      kind: Gateway
      name: envoy-internal
      namespace: network
      sectionName: https
  hostnames: ["chat.${SECRET_DOMAIN}"]
  rules:
    - matches: [{ path: { type: PathPrefix, value: / } }]
      backendRefs:
        - group: ""
          kind: Service
          name: open-webui
          port: 80          # NOT 8080 — verified against the live Service
      timeouts:
        request: 3600s      # streaming LLM responses; 60s would truncate them
        backendRequest: 3600s
```

### Example B: forward-auth app (four objects, two namespaces)

```yaml
# --- in kubernetes/apps/monitoring/headlamp/app/httproute.yaml ---
# 1) app route (targeted by the SecurityPolicy)
# 2) callback route: same hostname, path /outpost.goauthentik.io,
#    backendRef -> kube-system/ak-outpost-headlamp-forward-auth:9000
# 3) SecurityPolicy:
apiVersion: gateway.envoyproxy.io/v1alpha1
kind: SecurityPolicy
metadata: { name: headlamp-forward-auth, namespace: monitoring }
spec:
  targetRefs:
    - group: gateway.networking.k8s.io
      kind: HTTPRoute
      name: headlamp            # ONLY the app route, never the callback
  extAuth:
    failOpen: false             # an outpost outage must DENY
    http:
      backendRefs:
        - { group: "", kind: Service, name: ak-outpost-headlamp-forward-auth, namespace: kube-system, port: 9000 }
      path: /outpost.goauthentik.io/auth/envoy    # /auth/nginx returns 500
      headersToBackend: [Set-Cookie, X-authentik-username, X-authentik-groups,
                         X-authentik-email, X-authentik-name, X-authentik-uid]
---
# --- in kubernetes/apps/kube-system/authentik/app/referencegrants.yaml ---
# 4) grant — in kube-system (TARGET ns), with BOTH from-kinds
apiVersion: gateway.networking.k8s.io/v1beta1
kind: ReferenceGrant
metadata: { name: headlamp-outpost-access, namespace: kube-system }
spec:
  from:
    - { group: gateway.networking.k8s.io, kind: HTTPRoute,      namespace: monitoring }
    - { group: gateway.envoyproxy.io,     kind: SecurityPolicy, namespace: monitoring }
  to:
    - { group: "", kind: Service, name: ak-outpost-headlamp-forward-auth }
```

### Example C: multi-path route with a persistent websocket

```yaml
rules:
  - matches: [{ path: { type: PathPrefix, value: /push } }]
    backendRefs: [{ group: "", kind: Service, name: nextcloud-notify-push, port: 7867 }]
    timeouts: { request: 0s, backendRequest: 0s }   # 0s = no timeout; 60s would
                                                    # sever the WS every minute
  - matches: [{ path: { type: PathPrefix, value: / } }]
    backendRefs: [{ group: "", kind: Service, name: nextcloud, port: 8080 }]
    timeouts: { request: 300s, backendRequest: 300s }  # was proxy-read-timeout: 300
    filters:
      - type: ResponseHeaderModifier
        responseHeaderModifier:
          set: [{ name: Strict-Transport-Security, value: "max-age=31536000; includeSubDomains; preload" }]
```

### Example D: TLS backend, both mechanisms

```yaml
# SAN cert available -> BackendTLSPolicy (real verification)
apiVersion: gateway.networking.k8s.io/v1
kind: BackendTLSPolicy
metadata: { name: kibana-backend-tls, namespace: monitoring }
spec:
  targetRefs:
    - { group: "", kind: Service, name: kibana-kb-http, sectionName: https }  # port NAME
  validation:
    caCertificateRefs: [{ group: "", kind: Secret, name: kibana-kb-http-certs-public }]
    hostname: kibana-kb-http.monitoring.svc     # must match a SAN
---
# No SAN at all -> EG Backend (requires extensionApis.enableBackend: true)
apiVersion: gateway.envoyproxy.io/v1alpha1
kind: Backend
metadata: { name: wazuh-dashboard-tls, namespace: security }
spec:
  endpoints: [{ fqdn: { hostname: wazuh-dashboard.security.svc.cluster.local, port: 5601 } }]
  tls: { insecureSkipVerify: true }
# ...and the route's backendRef targets the Backend, not the Service:
#   - { group: gateway.envoyproxy.io, kind: Backend, name: wazuh-dashboard-tls }
```

---

## 6) Verification Tests

**This is the gate. Both real failures on 2026-09-07 were invisible at apply
time and visible only in status.** "Flux reconciled" and "the object applied"
prove nothing here.

### Test 1: route status — BOTH conditions

```bash
kubectl get httproute -n <ns> <name> -o json | python3 -c "
import sys,json
for p in json.load(sys.stdin)['status']['parents']:
    for c in p['conditions']:
        print(c['type'], c['status'], c.get('reason'))"
```

Expected:
- `Accepted True` **AND** `ResolvedRefs True`. Both, every time.

If failed:
- `RefNotPermitted` → missing/mis-namespaced ReferenceGrant (§4.3).
- `BackendNotFound` → wrong Service name, or a `Backend` ref with the
  extension API disabled (§4.4).

### Test 2: internal DNS actually moved

```bash
dig +short @192.168.55.101 <app>.${SECRET_DOMAIN}
```

Expected:
- `192.168.55.103` (internal apps) or `192.168.55.104` (external apps).

If failed:
- Something else still publishes that hostname. Check for a second HTTPRoute
  on the same hostname, and confirm k8s-gateway is healthy
  (`docs/sops/k8s-gateway-dns.md`).

### Test 3: real-client HTTP — NOT with `--resolve`, NOT only from the LAN

```bash
# INTERNAL apps: from the LAN, using the REAL name (no --resolve)
curl -o /dev/null -w '%{http_code} %{remote_ip}\n' https://<app>.${SECRET_DOMAIN}/
```

Expected:
- Plain app → `200`, `remote_ip` = `192.168.55.103`.
- Forward-auth app → `302` to the auth host. **A `200` is a FAIL-OPEN** and
  means the SecurityPolicy did not attach.

```bash
# EXTERNAL apps: resolve via a PUBLIC resolver, through the Cloudflare edge
dig +short @1.1.1.1 <app>.${SECRET_DOMAIN}          # must be Cloudflare IPs, never RFC1918
curl -o /dev/null -w '%{http_code} %{remote_ip}\n' \
  --resolve <app>.${SECRET_DOMAIN}:443:$(dig +short @1.1.1.1 <app>.${SECRET_DOMAIN} | head -1) \
  https://<app>.${SECRET_DOMAIN}/
```

Expected:
- A public (Cloudflare) address, and a real response through the edge.

If failed:
- An RFC1918 answer from `1.1.1.1` means external-dns published an A record to
  the gateway IP — the target annotation is on the route instead of the Gateway
  (rule 3). Cloudflare rejects that for a proxied record and the host goes dark.

> **Why the obvious check is wrong.** `curl --resolve` against the internal IP
> pins the address and therefore tests **Envoy directly, bypassing the very DNS
> record the conversion exists to move**. It passed on `headlamp` while real
> clients were getting a 404. And LAN split-horizon resolves to the internal
> gateway and returns `200` while real internet clients get a 404 — so a
> LAN-only check cannot validate an external host either. Use the real name
> from the LAN for internal apps, and the public resolution path for external
> ones.

### Test 4: SecurityPolicy attached (forward-auth apps only)

```bash
kubectl get securitypolicy -n <ns> <name> -o json | python3 -c "
import sys,json
for a in json.load(sys.stdin)['status']['ancestors']:
    for c in a['conditions']: print(c['type'], c['status'], c.get('reason'))"
```

Expected:
- `Accepted True`.

If failed:
- `Accepted False` with a ref error → the ReferenceGrant is missing its
  `gateway.envoyproxy.io/SecurityPolicy` `from` entry.

### Test 5: no gateway-scoped policy conflict

```bash
kubectl get backendtrafficpolicy -A -o json | python3 -c "
import sys,json
for p in json.load(sys.stdin)['items']:
    for a in p.get('status',{}).get('ancestors',[]):
        for c in a['conditions']:
            print(p['metadata']['name'], c['type'], c['status'], c.get('reason'))"
```

Expected:
- Exactly one policy per Gateway, `Accepted True`. Any `Conflicted` means a
  second policy was added and is doing nothing (rule 10).

---

## 7) Troubleshooting

| Symptom | Likely Cause | First Fix |
|---------|--------------|-----------|
| App healthy, real clients get **404** | Another object still holds the hostname on a different address, or DNS never moved | `dig @192.168.55.101 <host>`; look for a duplicate HTTPRoute on the same hostname |
| External hostname **dark**, `1.1.1.1` returns an RFC1918 address | external-dns target annotation put on the **route** — silently ignored (rule 3) | Remove it from the route; the target lives on `envoy-external` |
| `ResolvedRefs=False` / `RefNotPermitted` | ReferenceGrant missing, or landed in the app namespace via `targetNamespace` rewrite | Move the grant to `kube-system/.../referencegrants.yaml` |
| SecurityPolicy `Accepted=False` but route fine | Grant has only the `HTTPRoute` `from` entry, not `SecurityPolicy` | Add the second `from` entry (different API group) |
| Route serves **500**, `ResolvedRefs=False` "Backend is disabled" | `extensionApis.enableBackend` not set | Enable it in the Envoy Gateway HelmRelease |
| HelmRelease stuck, post-render error about a patch matching nothing | `postRenderers` patch still targets `kind: Ingress` | Remove **only that patch**, never the block (rule 9) |
| Pod stuck `ContainerCreating` on `Multi-Attach` right after a route change | The `postRenderers` block was deleted wholesale, taking `strategy: Recreate` | Restore the Deployment patch; see `docs/sops/longhorn-rwo-multi-attach.md` |
| Long requests truncate at ~15s | Route bypassing the gateway policy, or the policy is `Conflicted` | Check Test 5, then set `rules[].timeouts` |
| Long requests truncate at ~60s | Inheriting the gateway default; app needs an explicit longer timeout | Set `rules[].timeouts` (3600s streaming, 0s persistent WS) |
| `Accepted=True`, `ResolvedRefs=True`, still nothing works | Wrong `backendRef.port` number (rule 8) | Compare against `kubectl get svc -n <ns> <svc>` |
| Login redirect loop | Callback folded into the app route, or SecurityPolicy targets the callback route | Split into two routes; target only the app route |
| Homepage tile vanished | `gethomepage.dev/*` annotations or the label not carried onto the route | Add both the label and the annotations |

```bash
# Quick debugging
kubectl get httproute -A                       # everything, with parents
kubectl get gateway -n network                 # PROGRAMMED must be True
kubectl logs -n network deploy/envoy-gateway --tail=100
kubectl get svc -n network | grep envoy        # LB IPs .103 / .104
```

---

## 8) Diagnose Examples

### Diagnose Example 1: "the app is up but everyone gets a 404"

```bash
APP=headlamp; HOST=$APP.${SECRET_DOMAIN}
kubectl get httproute -A -o json | python3 -c "
import sys,json,os
h=os.environ['HOST']
for r in json.load(sys.stdin)['items']:
    if h in r['spec'].get('hostnames',[]):
        print(r['metadata']['namespace'], r['metadata']['name'],
              [p['name'] for p in r['spec']['parentRefs']])"
dig +short @192.168.55.101 $HOST
curl -o /dev/null -w '%{http_code} %{remote_ip}\n' https://$HOST/
```

Expected:
- Exactly one route (or an app route + a more-specific callback route), and
  `dig` returning the parent Gateway's IP. Confirms root cause when `dig`
  returns something *other* than .103/.104, or when two unrelated routes claim
  the hostname.

If unclear:
- Check whether a non-git object publishes the name (historically the Authentik
  outpost Ingress). `kubectl get httproute,gateway -A | grep <host>`.

### Diagnose Example 2: "external host went dark after conversion"

```bash
HOST=<app>.${SECRET_DOMAIN}
dig +short @1.1.1.1 $HOST                        # RFC1918 answer == the bug
kubectl get gateway -n network envoy-external \
  -o jsonpath='{.metadata.annotations}' | python3 -m json.tool
kubectl get httproute -n <ns> <name> \
  -o jsonpath='{.metadata.annotations}' | python3 -m json.tool
kubectl logs -n network deploy/external-dns --tail=50 | grep -i "$HOST"
```

Expected:
- The **Gateway** carries `external-dns.alpha.kubernetes.io/target:
  external.${SECRET_DOMAIN}` and the **route carries no target annotation**.
  external-dns logs showing an attempted A record to `192.168.55.104`, or a
  Cloudflare rejection of a private target for a proxied record, confirms
  rule 3.

If unclear:
- Verify the cloudflared wildcard still points at `envoy-external`
  (`docs/sops/cloudflare.md`).

### Diagnose Example 3: "authenticated app is serving 200 to anonymous clients"

```bash
kubectl get securitypolicy -n <ns> -o wide
kubectl get referencegrant -n kube-system <app>-outpost-access -o yaml
curl -o /dev/null -w '%{http_code}\n' https://<app>.${SECRET_DOMAIN}/
```

Expected:
- A `302`. A `200` means the SecurityPolicy never attached — almost always the
  missing `gateway.envoyproxy.io/SecurityPolicy` grant entry, which leaves the
  app **unprotected**. Treat as a security incident, not a routing bug.

If unclear:
- Confirm the outpost is running: `kubectl get deploy -n kube-system | grep
  ak-outpost-<app>`.

---

## 9) Health Check

```bash
# 1. Both gateways programmed with their pinned LB IPs
kubectl get gateway -n network
#    -> envoy-internal 192.168.55.103 True ; envoy-external 192.168.55.104 True

# 2. No route is degraded — this should print NOTHING
kubectl get httproute -A -o json | python3 -c "
import sys,json
for r in json.load(sys.stdin)['items']:
    for p in r['status'].get('parents',[]):
        bad=[c for c in p['conditions'] if c['status']!='True']
        if bad: print(r['metadata']['namespace'], r['metadata']['name'],
                      [(c['type'],c.get('reason')) for c in bad])"

# 3. Gateway-wide policies accepted, none Conflicted
kubectl get backendtrafficpolicy,clienttrafficpolicy,securitypolicy -A

# 4. nginx really is gone (both must say 'No resources found')
kubectl get ingress -A
kubectl get ingressclass

# 5. Route count sanity (expected ~104 after 2026-09-07)
kubectl get httproute -A --no-headers | wc -l
```

Expected:
- Both Gateways `PROGRAMMED=True`; check 2 silent; no `Conflicted` policy; zero
  Ingress and zero IngressClass; route count in the low 100s.

---

## 10) Security Check

```bash
# 1. Every forward-auth app still denies anonymously (302, never 200)
for h in headlamp nocodb phpmyadmin arag-web uptime-kuma; do
  printf '%s ' "$h"
  curl -s -o /dev/null -w '%{http_code}\n' https://$h.${SECRET_DOMAIN}/
done

# 2. No SecurityPolicy is fail-open
kubectl get securitypolicy -A -o json | python3 -c "
import sys,json
for p in json.load(sys.stdin)['items']:
    fo=p['spec'].get('extAuth',{}).get('failOpen')
    if fo is not False: print('FAIL-OPEN:', p['metadata']['namespace'], p['metadata']['name'], fo)"

# 3. No internal-only app leaked onto the external gateway
kubectl get httproute -A -o json | python3 -c "
import sys,json
for r in json.load(sys.stdin)['items']:
    if any(p['name']=='envoy-external' for p in r['spec']['parentRefs']):
        print(r['metadata']['namespace'], r['metadata']['name'], r['spec'].get('hostnames'))"

# 4. No real domain committed anywhere in the route manifests
grep -rn "SECRET_DOMAIN" kubernetes/apps --include='httproute*.yaml' | wc -l

# 5. ReferenceGrants are all in kube-system and none is over-broad
kubectl get referencegrant -A
```

Expected:
- Every forward-auth host returns `302`, never `200` (a `200` is a fail-open
  and an incident).
- No `failOpen: true` or unset anywhere.
- The `envoy-external` list contains **only** intentionally internet-exposed
  apps (25 hostnames as of 2026-09-07) — anything unexpected there is a
  material exposure change.
- All hostnames in git are templated `${SECRET_DOMAIN}`; no literal domain.
- All ReferenceGrants in `kube-system`, each naming a specific
  `ak-outpost-*-forward-auth` Service (never a wildcard `to`).

---

## 11) Rollback Plan

**There is no nginx to fall back to.** ingress-nginx was deleted in `ad1ea7c2`
and it is permanently EOL upstream — restoring it is not a rollback path.
Rollback is therefore **per route, forward, within Gateway API**:

```bash
# 1. Revert the offending commit (routes are self-contained per app)
git revert <commit>
git push                              # Flux reconciles; DNS follows in ~60s TTL

# 2. If the route is wedged and the app must be reachable now, detach it and
#    reattach a known-good copy — never leave two routes on one hostname
kubectl -n <ns> delete httproute <name>
kubectl apply -f kubernetes/apps/<ns>/<app>/app/httproute.yaml

# 3. Re-run the full gate before declaring recovery
kubectl get httproute -n <ns> <name> -o json | python3 -c "
import sys,json
[print(c['type'],c['status'],c.get('reason'))
 for p in json.load(sys.stdin)['status']['parents'] for c in p['conditions']]"
dig +short @192.168.55.101 <app>.${SECRET_DOMAIN}
curl -o /dev/null -w '%{http_code} %{remote_ip}\n' https://<app>.${SECRET_DOMAIN}/
```

Rollback cautions specific to this migration:

- **Never roll back by deleting a whole `postRenderers` block** — that is what
  caused the anythingllm Multi-Attach deadlock. Revert the commit instead.
- **CRDs are never touched by a route change**, so route-level revert is
  genuinely available. The Gateway API CRD *bundle* is different: its
  ValidatingAdmissionPolicy blocks its own rollback. Do not treat a CRD bump as
  revertible — see `docs/sops/envoy-gateway-upgrade.md`.
- Reverting a forward-auth conversion also needs the Authentik side considered:
  re-enabling an outpost's `ingress` component with no ingress controller
  present would create a dangling object. Leave
  `kubernetes_disabled_components: [ingress]` set.

---

## 12) References

- `kubernetes/apps/network/envoy-gateway/app/` — Gateways, policies, GatewayClass, HelmRelease
- `kubernetes/apps/kube-system/authentik/app/referencegrants.yaml` — all ReferenceGrants
- `kubernetes/apps/monitoring/headlamp/app/httproute.yaml` — canonical forward-auth example
- `kubernetes/apps/office/nextcloud/app/httproute.yaml` — canonical multi-path/websocket/timeout example
- `kubernetes/apps/monitoring/kibana/app/httproute.yaml` — `BackendTLSPolicy` example
- `kubernetes/apps/security/wazuh/app/httproute.yaml` — EG `Backend` + `insecureSkipVerify` example
- `docs/sops/envoy-gateway-upgrade.md` — upgrading Envoy Gateway / the CRD bundle
- `docs/sops/k8s-gateway-dns.md` — internal split-horizon DNS (192.168.55.101)
- `docs/sops/cloudflare.md` — the external path (tunnel + edge)
- `docs/sops/authentik.md` — blueprints, outposts, providers
- `docs/sops/longhorn-rwo-multi-attach.md` — why `strategy: Recreate` in a postRenderer is load-bearing
- `docs/sops/homepage-integration.md` — the `gethomepage.dev/*` label + annotations contract
- Migration commits: `c41f0ff4`/`0cf4cfcc`/`65dc2b7f` (external-dns target),
  `e0968989`/`07c8f1ff` (postRenderer damage + restore),
  `e6e64e5a`/`382a01c5` (single BackendTrafficPolicy), `e23c12ee` (Backend
  extension API), `5bc0a682` (cloudflared wildcard flip), `ad1ea7c2`
  (ingress-nginx deleted)

---

## Version History

- `2026.09.07`: Created on completion of the Envoy Gateway migration (104
  HTTPRoutes; ingress-nginx deleted). Supersedes and replaces
  `docs/troubleshooting/envoy-phase2-conversion-pattern.md`, which was deleted
  per the troubleshooting-doc lifecycle rule.
