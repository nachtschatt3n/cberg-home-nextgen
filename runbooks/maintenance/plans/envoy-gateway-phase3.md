---
plan_id: envoy-gateway-phase3
component: envoy-gateway
pr: null
kind: migration-cutover             # Phase 3: external apps + Cloudflare tunnel flip
current: "external apps on ingress-nginx (26 Ingresses, className: external — verified 2026-08-16; cloudflared wildcard -> nginx)"
target: "external apps on HTTPRoute/envoy-external; cloudflared wildcard -> envoy-external"
update_type: migration
risk: high                          # the external cutover touches the Cloudflare
                                    # tunnel path serving 26 public apps; per-
                                    # hostname canaries first, wildcard flip last
                                    # (one revertible commit). PLUS the DNS-target
                                    # exposure gate below — this is the phase that can
                                    # publish RFC1918 addressing to a public zone.
est_duration_min: 90
needs_reboot: false
touches:
  namespaces: [network, all-external]
  resources:
    - "26 external Ingress -> HTTPRoute on envoy-external"
    - "cloudflared config.yaml: per-hostname canary rules, then wildcard flip"
    - "external-dns TARGET annotations carried to HTTPRoutes (GATED — see §2.1)"
    - "https-redirect catch-all EXEMPTION route for the plain-HTTP Alexa stream (GATED — see §2.2)"
    - "uptime-kuma forward-auth pair on envoy-external (uptime-kuma-authentik-outpost, priority annotation)"
    - "music-assistant: 3 exposure mechanisms must stay consistent (see §2.2)"
  shared: [cloudflared, auth, dns]  # SOLO-ish session: no other plan may touch
                                    # cloudflared/cert-manager/authentik; avoid
                                    # co-scheduling app plans whose verification
                                    # is via public ingress.
                                    # dns: ADDED 2026-08-16 — this phase writes to the
                                    # PUBLIC Cloudflare zone (26 hostnames) via
                                    # external-dns under `policy: sync`, which deletes.
depends_on: [envoy-gateway-phase2]
conflicts_with: []  # don't run an app-template tier in this session  # RESOLVED 2026-08-18: app-template migration (renamed 5.1) EXECUTED 78/78 — dead ref removed
security_ref: null                  # see envoy-gateway-phase4; AR-055's escalation
                                    # clause keys on THIS phase (the external cutover)
status: reference                     # was 'scheduled' with window:null — a contradiction:
                                      # a plan that believes it is scheduled but names no slot
                                      # silently never runs. 'reference' is the honest state:
                                      # deliberately outside the window system until its
                                      # track is activated (P0.4, 2026-08-26).
                                    # (gateway-api v1.5.1, new org). phase0 re-run and
                                    # executed the same day: DNS gates passed twice,
                                    # including the restart-with-CRDs-present gate that
                                    # armed the original outage. Attended project — see
                                    # window note below.
window: null                          # 2026-08-15: the envoy chain is NOT window work.
                                      # phase2 alone is est 120m and the largest window is 90m,
                                      # so it never fit; the 5 phases are strictly sequential,
                                      # which shuffling cannot fix. Operator decision: run the
                                      # migration as an ATTENDED PROJECT outside the window
                                      # system — which is what a 5-phase ingress migration
                                      # actually is. Do NOT schedule these into windows.
                                      # `window: null` here is DELIBERATE, not neglect:
                                      # maintenance-plan.py --open classifies these as
                                      # REFERENCE / UNWINDOWED by design.
                                      # (previous value kept in git history)
# auto_execute RETIRED 2026-08-26 (P2.1b) — execution class is now DERIVED
# from capability_change/rollback_class per runbooks/autonomy-policy.yaml.
sops_refs:
  - docs/troubleshooting/ingress-migration-plan.md
  - docs/sops/k8s-gateway-dns.md     # ADDED 2026-08-16 — §10 external-dns scoping and
                                     # the negative-test method
  - docs/sops/cloudflare.md
generated: "2026-08-07"
amended: "2026-08-16"                # phase-0 execution learnings folded in
---

# Envoy Gateway — Phase 3: external + tunnel cutover

## 1. Summary & why

Per decision doc §P3: (1) convert external apps to HTTPRoutes on
`envoy-external` (public DNS unchanged — everything CNAMEs to
external.${SECRET_DOMAIN} → tunnel). (2) cloudflared ordered per-hostname
canaries → `https://envoy-external.network.svc:443` (originServerName +
http2Origin) above the wildcard→nginx rule; canaries MUST include authentik's
own hostname (verify SSO before anything else), one forward-auth app, and
nextcloud (websockets). Soak. (3) Wildcard flip = one commit; **rollback =
revert that commit** (seconds). (4) Move the `dependsOn: cloudflared`
ordering from the external nginx HR to the EG ks.

Live count re-derived 2026-08-16: **26** Ingresses with `className: external`.

## 2. Pre-checks

```bash
# phase 2 is actually complete — zero internal Ingresses left
mise exec -- kubectl get ingress -A -o jsonpath='{range .items[*]}{.spec.ingressClassName}{"\n"}{end}' | sort | uniq -c
#   expect: only "external" remains (26)
mise exec -- kubectl get gateway -n network                     # both PROGRAMMED
mise exec -- kubectl -n network logs deploy/external-dns | grep -o 'GatewayName:[^ ]* GatewayNamespace:[^ ]*'
mise exec -- kubectl -n network logs deploy/external-dns --tail=20 | grep -E 'All records|Changing record'
```

### 2.1 GATE — the DNS target annotation (PROMOTED 2026-08-16 from a bullet to a blocking pre-check)

This was tracked as a bullet in `touches`. It is an **un-gated public-exposure
risk** and is now an enforced gate, because it is the one failure in this phase
that leaks *addressing* rather than just breaking a service.

**Mechanism.** For the `gateway-httproute` source, external-dns derives an
HTTPRoute's record target from the **parent Gateway's LB address** unless the
route carries `external-dns.alpha.kubernetes.io/target`. `envoy-external`'s
address is **192.168.55.104** — RFC1918. So a converted external HTTPRoute
without the annotation either (a) publishes private addressing into the public
Cloudflare zone, or (b) is rejected by the Cloudflare API (`--cloudflare-proxied`
is set cluster-wide and a proxied record cannot point at a private address).
Neither outcome is acceptable and (b) fails loudly *per record*, so a partial
cutover with some hostnames dark is the realistic bad day.

**Verified fact that makes this concrete:** all **26/26** external Ingresses
carry `external-dns.alpha.kubernetes.io/target: "external.${SECRET_DOMAIN}"`
today (checked 2026-08-16 across every `className: external` object; zero
exceptions). The correct value is therefore already known for every host — the
only failure mode is *forgetting to carry it across* in a conversion commit.

**The gate — no conversion commit merges until this passes:**

```bash
# 1. BEFORE the batch: record the target every Ingress in it currently carries
mise exec -- kubectl get ingress -A -o json | python3 -c "
import sys,json
d=json.load(sys.stdin)
for i in d['items']:
    if i['spec'].get('ingressClassName')!='external': continue
    a=(i['metadata'].get('annotations') or {})
    print(i['metadata']['namespace']+'/'+i['metadata']['name'],
          a.get('external-dns.alpha.kubernetes.io/target','*** MISSING ***'))
"

# 2. AFTER the batch: EVERY HTTPRoute on envoy-external must carry a target.
#    This must print nothing. If it prints a route, that route is the exposure.
mise exec -- kubectl get httproute -A -o json | python3 -c "
import sys,json
d=json.load(sys.stdin)
bad=[]
for r in d['items']:
    parents=[p.get('name') for p in r['spec'].get('parentRefs',[])]
    if 'envoy-external' not in parents: continue
    if not r['spec'].get('hostnames'): continue
    if not (r['metadata'].get('annotations') or {}).get('external-dns.alpha.kubernetes.io/target'):
        bad.append(r['metadata']['namespace']+'/'+r['metadata']['name'])
print('\n'.join('MISSING TARGET: '+b for b in bad))
"

# 3. NEGATIVE assertion in the public zone: no A record with private addressing
for h in <converted-hosts>; do
  dig +short "$h".${SECRET_DOMAIN} @1.1.1.1
done | grep -E '^(192\.168|10\.|172\.(1[6-9]|2[0-9]|3[01]))\.' && echo "STOP: RFC1918 IN PUBLIC DNS" || echo "clean"

# 4. Positive assertion: each converted host still resolves to the tunnel CNAME
dig +short CNAME <host>.${SECRET_DOMAIN} @1.1.1.1     # expect external.${SECRET_DOMAIN}
```

**A cleaner variant the operator may prefer, but which must be A/B-proven, not
assumed:** annotate the `envoy-external` **Gateway** with the target instead of
each of the 26 routes, so the safe value is the default and a forgotten
annotation cannot fail open. Whether external-dns honours the target annotation
at the Gateway level for the `gateway-httproute` source is **version-dependent
and not verified here** — prove it with a throwaway `--dry-run --once`
external-dns pod on the same image before relying on it (method in
`docs/sops/k8s-gateway-dns.md` §10), and keep the per-route gate above as the
check either way. Do not adopt it on the strength of this paragraph.

### 2.2 GATE — the `https-redirect` catch-all will break the Alexa audio stream

Phase 0 installed HTTPRoute `network/https-redirect`: **no `hostnames:`**,
attached to the `http` (:80) listener of **both** gateways, filter
`requestRedirect{scheme: https, statusCode: 301}`. Hostname-less means it
matches **every** host that arrives on :80. It is inert today only because no
route carries a hostname. **This phase is where it stops being inert for
external traffic.**

The collision, verified 2026-08-16:

> `home-automation/music-assistant-alexa-stream` (`className: external`) has
> **no `tls:` block** and explicitly sets `nginx.ingress.kubernetes.io/ssl-redirect: false`
> **and** `force-ssl-redirect: false`. The Alexa audio stream is deliberately
> plain HTTP (Music Assistant publishes `publish_ip:bind_port` over `http`).
> Attach its hostname to `envoy-external` and the catch-all 301s the stream to
> HTTPS — **Alexa playback breaks**, and it breaks in Amazon's fetcher, not in
> a browser, so it will not show up in a manual spot-check.

**Gateway API has no per-route `ssl-redirect: false`.** The exemption must be
modelled structurally: a **more-specific HTTPRoute carrying that hostname,
attached to the `http` listener, that forwards to the backend instead of
redirecting** — relying on Gateway API's hostname-match precedence (a route
with a specific hostname wins over a hostname-less one). That precedence is
the entire mechanism, so it must be *demonstrated*, not assumed.

**The gate — before any external hostname is attached:**

```bash
# 1. enumerate the external Ingresses with NO tls block (the hazard set).
#    Verified 2026-08-16: 4 of 26 — echo-server, flux-webhook, home-assistant,
#    music-assistant-alexa-stream.
mise exec -- kubectl get ingress -A -o json | python3 -c "
import sys,json
d=json.load(sys.stdin)
for i in d['items']:
    if i['spec'].get('ingressClassName')!='external': continue
    a=(i['metadata'].get('annotations') or {})
    if not i['spec'].get('tls') or a.get('nginx.ingress.kubernetes.io/ssl-redirect')=='false':
        print('DECIDE (redirect or exempt):', i['metadata']['namespace']+'/'+i['metadata']['name'])
"
#    Each one gets an explicit, recorded decision in its commit. No silent defaults.

# 2. PROVE the precedence with the exemption route in place, BEFORE the cutover:
curl -sS -o /dev/null -w '%{http_code} %{redirect_url}\n' \
     --resolve <alexa-stream-host>.${SECRET_DOMAIN}:80:192.168.55.104 \
     http://<alexa-stream-host>.${SECRET_DOMAIN}/<stream-path>
#    expect 200 (served over plain HTTP). A 301 to https:// IS THE FAILURE.

# 3. CONTROL — a normal external host must STILL be redirected (proving the
#    exemption is scoped to one hostname and did not disable the catch-all):
curl -sS -o /dev/null -w '%{http_code} %{redirect_url}\n' \
     --resolve <normal-external-host>.${SECRET_DOMAIN}:80:192.168.55.104 \
     http://<normal-external-host>.${SECRET_DOMAIN}/
#    expect 301 -> https://...
```

**Music Assistant has three distinct exposure mechanisms that must stay
consistent** — this phase touches only the first two, but a change to any one
of them can break the other:

| mechanism | object | note |
|---|---|---|
| external Ingress ×2 | `music-assistant-alexa-api` (TLS) and `music-assistant-alexa-stream` (**no TLS**, both ssl-redirect flags false) | convert here; the stream is the exemption above |
| internal Ingress | `music-assistant-server` (TLS) | converted in phase 2 |
| LoadBalancer | `home-automation/music-assistant-server` @ **192.168.55.29**, 4 ports | L4, Cilium LB-IPAM — **untouched by every phase** |

Plus `music-assistant-server` runs `hostNetwork` for multicast/mDNS discovery,
which no gateway routes. Background on the Alexa path (Cloudflare Bot Fight
Mode, the forced `publish_ip:bind_port http` stream URL) is in the AR-049
history — do not "fix" the plain-HTTP stream into HTTPS as part of this phase.

### 2.3 Standing exposure note — `--source=crd` is unfiltered

`sources: ["crd", "ingress", "gateway-httproute"]`. The gateway source is
scoped (`--gateway-name`/`--gateway-namespace`) and the ingress source is
scoped (`--ingress-class=external`). **`crd` (DNSEndpoint) has no filter at
all** — any DNSEndpoint in any namespace publishes straight to the public zone.
Exactly one exists today: `network/cloudflared` (the tunnel CNAME). After this
phase it is the widest remaining path to public DNS in the cluster. Do not
create a DNSEndpoint as a workaround for a target-annotation problem in this
phase; that trades a gated risk for an ungated one.

## 3. Steps

1. Convert external apps to HTTPRoutes on `envoy-external`, in batches,
   carrying `external-dns.alpha.kubernetes.io/target` across in the same
   commit. §2.1 gate per batch.
2. cloudflared ordered per-hostname canaries above the wildcard→nginx rule:
   authentik's own hostname first (verify SSO before anything else), then one
   forward-auth app, then nextcloud (websockets). Soak.
3. Wildcard flip — one commit.
4. Move the `dependsOn: cloudflared` ordering from the external nginx HR to
   the EG ks.

## 4. Verification

Every canary hostname serves + authenticates; after flip, spot-check
10 public apps + SAML (wazuh) + **the Alexa music-stream path over plain HTTP
(§2.2 step 2 re-run post-flip — a 301 here is a regression, and Amazon's
fetcher is the only real consumer, so a browser check does not substitute)**;
0 firing alerts;
Kuma all green (69 monitors are the real external verification fleet).
**Run the phase-2 §4.0 test matrix (tests 1-14) against every converted
external app** — it is not internal-specific. Notes that differ here: test 1's
expected answer is `192.168.55.104`; test 2 must be run **through the tunnel**
(a `--resolve` to the gateway VIP proves EG serves it, but only a request via
the public hostname proves cloudflared's rule ordering is right); tests 7/8 are
the §2.2 gate.

**The three nginx-bound alerts go fully blind at the wildcard flip.**
`IngressNginx5xxSustained`, `AuthentikIngressAuthFailures` and
`AuthentikIngressAuthBackendError` query `nginx_ingress_*`; the flip takes the
external estate's traffic to Envoy in one commit, so their series stop
receiving samples for the last remaining traffic. Their Envoy counterparts were
built and **proven firing** as the phase-2 entry gate (§1.5 there) — re-confirm
before the flip that those counterparts are still loaded and that a deliberate
5xx on an external canary makes one fire. Do not flip on the assumption they
survived phase 2 untouched.

**Extend blackbox probes to the external canaries BEFORE the canary rules
land** (4 `probe_success` series exist against 102 hosts). A probe added after
a regression cannot tell you when it started.

**Music Assistant discovery is invisible to both ingress controllers.** After
anything touching it, confirm **speaker discovery still works** (mDNS/multicast
via `hostNetwork`, plus the LoadBalancer on **192.168.55.29**, ports
5000/80/8095/8097). A migration that verifies green on all three Ingresses can
coexist with silently broken discovery, because that path never traverses a
gateway at all.

Plus the §2.1 target gate AND the §2.2 redirect gate (both the exemption and
the control) re-run after the wildcard flip, the **negative auth test** from
phase 2 §4 for `uptime-kuma` (its outpost pair moves in this phase and a
mistranslated SecurityPolicy fails OPEN and silently), and:

```bash
# public record set did not grow or shrink unexpectedly, and nothing was pruned
mise exec -- kubectl -n network logs deploy/external-dns --tail=40 | grep -E 'Changing record|Deleting'
```

## 5. Rollback

Wildcard flip: `git revert` that one commit — seconds, and the tunnel returns
to nginx. Per-app conversions: `git revert` the batch commit; the Ingress
returns and external-dns restores its record from the Ingress source (which is
still enabled — `sources` keeps `ingress` until phase 4 precisely so this
rollback works).

If a route was published with a bad target: revert the commit, then confirm
external-dns actually *deleted* the bad record (`grep 'Deleting'` in the log,
then `dig`). A record whose `k8s.a-<host>` TXT ownership record is missing will
NOT be deleted by `policy: sync` — it must be removed in the Cloudflare UI/API
by the operator.

## 6. Interference notes

- **SOLO-ish.** `shared: [cloudflared, auth, dns]` — no other plan may touch
  cloudflared, cert-manager, authentik, external-dns or k8s-gateway in this
  session, and no plan whose verification path is a public hostname may be
  co-scheduled. `conflicts_with: [app-template-5.0]`.
- **AR-055 flag (do not edit the policy DB from this plan).** AR-055 accepts
  the ingress-nginx exposure with a hard review at **2026-09-18** and escalates
  to the Chainguard contingency (`ingress-nginx-1.15.6.md`, kept as break-glass)
  "if the external cutover hasn't happened" — i.e. if *this* phase has not run.
  Its justification text was written 2026-08-07 and still describes the
  pre-incident plan: it predates the DNS outage, the k8s-gateway upgrade, the
  phase-0 rollback-and-reapply, and the decision to run the chain attended and
  unwindowed. Since the phases now carry **no scheduled dates at all**, nothing
  in the system will surface slippage against 2026-09-18 before it happens.
  Operator action, outside this plan: re-review AR-055's justification and its
  date. Flagged, deliberately not changed.
- **Not window work** (see `window: null`): 90 min *and* strictly after phases
  1-2. Attended project.
