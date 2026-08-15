---
plan_id: envoy-gateway-phase2
component: envoy-gateway
pr: null
kind: migration-bulk                # Phase 2: internal bulk conversion (76 Ingresses)
current: "internal apps on ingress-nginx (76 Ingresses, className: internal — verified 2026-08-16)"
target: "all internal apps on HTTPRoute/envoy-internal; nginx snippet-annotations disabled"
update_type: migration
risk: medium                        # per-app blast radius only; each batch = one
                                    # commit = one git revert; DNS flips back via
                                    # k8s-gateway TTL 60 on revert. The cluster-wide
                                    # DNS risk lives in phase 1 (the k8s-gateway
                                    # restart), not here — by phase 2 the resolver is
                                    # already watching HTTPRoute and proven.
est_duration_min: 120               # spans 2 sessions
needs_reboot: false
touches:
  namespaces: [all-internal, monitoring]   # batch-per-namespace commits; monitoring
                                    # because the alert rules + blackbox probes move here
  resources:
    - "76 internal Ingress -> HTTPRoute conversions (app-template route: block where possible)"
    - "9 remaining forward-auth apps -> SecurityPolicy pattern from phase1 pilot (§1.2)"
    - "13 ak-outpost-*-forward-auth Ingresses in kube-system -> HTTPRoute + ReferenceGrant"
    - "nextcloud/whiteboard security headers -> ResponseHeaderModifier"
    - "ai/librechat: configuration-snippet stripping X-Tenant-Id -> RequestHeaderModifier (SECURITY-LOAD-BEARING, §1.3)"
    - "wazuh/kibana: HTTPRoute + EG Backend tls.insecureSkipVerify (backend-protocol: HTTPS)"
    - "20 internal Ingresses with NO tls block -> explicit redirect/exempt decision each (§1.4)"
    - "ENTRY GATE: Envoy equivalents for the 3 nginx_ingress_* alert rules, proven firing (§1.5)"
    - "blackbox probes extended per batch (probe_success covers 4 of 102 hosts today)"
    - "HARDENING MILESTONE: allow-snippet-annotations=false on both nginx HRs"
  shared: [auth, dns]               # auth: forward-auth apps convert one at a time;
                                    # authentik provider mode flips per app.
                                    # dns: ADDED 2026-08-16 — every batch moves internal
                                    # A-record answers (k8s-gateway .100 -> .103) AND is
                                    # the live exercise of the external-dns gateway
                                    # filter (`bca46f0e`). 76 hostnames pass through the
                                    # one control that keeps them out of public DNS.
depends_on: [envoy-gateway-phase1]  # GATED: phase1 pilots must be GO (operator review).
                                    # HARD PREREQUISITE (2026-08-16): phase 1 step 0 —
                                    # k8s-gateway watchedResources must already include
                                    # HTTPRoute, or every converted host stops resolving
                                    # internally instead of flipping to .103.
conflicts_with: []                  # not with authentik/cloudflared/cert-manager plans;
                                    # and nothing that restarts k8s-gateway (shared: dns)
security_ref: null                  # see envoy-gateway-phase4; the phase-2 hardening
                                    # milestone (allow-snippet-annotations=false) is
                                    # AR-055's named compensating control, not the fix
status: scheduled                   # unblocked 2026-08-15: k8s-gateway 3.7.2/1.8.0
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
auto_execute: false
sops_refs:
  - docs/troubleshooting/ingress-migration-plan.md
  - docs/sops/k8s-gateway-dns.md     # ADDED 2026-08-16 — §10 "keep INTERNAL hostnames
                                     # out of PUBLIC DNS" is the normative source for
                                     # the batch-1 negative test below
  - docs/sops/authentik.md
generated: "2026-08-07"
amended: "2026-08-16"                # phase-0 execution learnings folded in
---

# Envoy Gateway — Phase 2: internal bulk (76 objects, 2 sessions)

## 1. Summary & why

Execute per the decision doc §P2. Batch by namespace, one commit per batch,
flux-local CI green before merge; `gethomepage.dev/*` annotations move
Ingress→HTTPRoute in the same commit (no double discovery). app-template apps
(~60) use the chart's native `route:` block; foreign charts get standalone
httproute.yaml. Forward-auth apps replicate the pilot-B pattern (HTTPRoute +
outpost route + ReferenceGrant + SecurityPolicy + ak provider mode flip).
(langfuse, which would have kept its Ingress until its OAuth loop was proven
on the new path, was removed from the cluster on 2026-08-13 — one fewer
forward-auth conversion and no cookie workaround needed.)

Live count re-derived 2026-08-16: **76** Ingresses with `className: internal`
(of 102 total). That is the object count this phase must drive to zero.

**Session 2 exit criterion:** zero internal Ingresses left → set
`allow-snippet-annotations: false` +
`annotations-risk-level: High` on BOTH nginx HelmReleases (neutralizes the
injection-CVE class per AR-055's compensating-control commitment).

### 1.1 Phase-0 learning that lands squarely on this phase: the 76-hostname DNS leak

This is the phase the `bca46f0e` fix exists for. Before it, external-dns's
`gateway-httproute` source was **completely unscoped**:

> **`--ingress-class=external` filters Ingress objects ONLY. It has no effect
> whatsoever on HTTPRoutes.** Every one of the ~76 internal hostnames this
> phase converts would have been published to the **public** Cloudflare zone
> on the first batch — internal-only services, named publicly, in a public
> DNS zone.

It was latent through phase 0 only because no HTTPRoute carried a hostname
(still true today: the single `network/https-redirect` route is hostname-less).
**Phase 2 batch 1 is the moment it would have fired.**

Now scoped, and verified live in the running external-dns pod's args:
`--gateway-name=envoy-external --gateway-namespace=network`. Chosen because it
is a **default-deny allowlist of exactly one Gateway** — a typo, a rename, or a
newly added gateway all fail **CLOSED** (nothing published). Rejected
alternatives, so nobody re-opens them: `--gateway-label-filter` needs a label
on Gateway objects owned by this workstream; `--label-filter` also applies to
the `ingress` and `crd` sources, where under `policy: sync` it would prune the
existing external records.

Two standing cautions for this phase:

- **`--source=crd` (DNSEndpoint) is still entirely unfiltered** — any
  DNSEndpoint in any namespace goes straight to the public zone. One exists
  (`network/cloudflared`). It is the widest remaining path to public DNS; do
  not reach for a DNSEndpoint as a shortcut during a batch.
- **`policy: sync` deletes.** `sources` must keep `ingress` for the whole of
  phase 2 (both kinds coexist during the parallel run). Dropping it early would
  delete the records of every not-yet-converted app. It is phase-4 work.

### 1.2 The forward-auth outposts are the hard part — and they fail OPEN

Gateway API has **no forward-auth primitive**. In Envoy Gateway this is a
`SecurityPolicy` (`extAuth.http`) attached per route — a different object with
different semantics from the nginx `auth-url`/`auth-signin`/`auth-snippet`/
`auth-response-headers` annotation quartet. This is not an annotation
translation; it is a re-implementation of the auth path, once per app.

Live inventory (2026-08-16):

- **10 apps** carry the nginx forward-auth annotations, **all `className:
  internal`**: `databases/nocodb`, `databases/phpmyadmin`, `default/homepage`,
  `home-automation/esphome`, `home-automation/frigate`,
  `home-automation/solarfocus-scraper`, `monitoring/alertmanager`,
  `monitoring/headlamp`, `monitoring/prometheus`, `storage/longhorn-ui`.
  headlamp is the phase-1 pilot → **9 remain for this phase**, which is exactly
  the "9 remaining forward-auth apps" already in `touches`.
- **13 `ak-outpost-*-forward-auth` Ingresses** exist in `kube-system` — three
  more than there are `auth-url` consumers. The extras are **`arag-web`,
  `kubernetes-dashboard`, `uptime-kuma`**: each is protected by a different
  mechanism (uptime-kuma is `external` and has its own
  `uptime-kuma-authentik-outpost` Ingress using a `priority` annotation, so it
  is **phase-3 work**, not phase-2). **Do not treat the 10-app `auth-url` list
  as the whole auth surface** — enumerate by outpost Ingress and reconcile the
  two lists before writing any batch.

**A mistranslation here fails OPEN, and silently.** A missing or misattached
SecurityPolicy does not error; the route simply serves the app with no auth,
and every functional check ("the page loads", "Ready=True", "the tile is
green") passes. **The only verification that catches it is a negative one** —
see §4.

### 1.3 Annotation conversion inventory — what has no Gateway API equivalent

Live counts across all 102 Ingresses (2026-08-16). None of these has a direct
Gateway API translation; each needs an EG-specific answer (`BackendTrafficPolicy`,
`ClientTrafficPolicy`, `Backend`, or an accepted behaviour change):

| count | annotation | note |
|---|---|---|
| 14 | `proxy-buffer-size` | EG buffering defaults differ — decide once, apply as a policy |
| 14 | `proxy-buffers-number` | ditto |
| 13 | `proxy-read-timeout` | `BackendTrafficPolicy` timeout |
| 13 | `proxy-send-timeout` | ditto |
| 13 | `affinity` | **session affinity** — EG has consistent-hash/cookie LB policy; behaviour is not identical |
| 13 | `proxy-busy-buffers-size` | |
| 9 | `proxy-body-size` | `ClientTrafficPolicy` |
| 3 | `configuration-snippet` | see below — one is security-load-bearing |
| 2 | `enable-websocket` / `websocket-services` | EG upgrades by default; verify, don't assume |
| 2 | `backend-protocol` | **kibana, wazuh-dashboard** — HTTPS upstreams, need an EG `Backend` |
| 2 | `proxy-http-version`, `proxy-buffering`, `proxy-connect-timeout` | |
| 1 | `proxy-request-buffering`, `proxy-ssl-verify` | |

**`ai/librechat-librechat`'s `configuration-snippet` is load-bearing security,
not cosmetics.** Its whole body is:

```
proxy_set_header X-Tenant-Id "";
```

LibreChat v0.8.5+ **trusts** that header on four unauthenticated routes, so the
snippet exists to stop a client from supplying it. Converting that route
without reproducing the strip — as an HTTPRoute `RequestHeaderModifier`
setting `X-Tenant-Id` to empty (a `remove:` alone is not equivalent if the
upstream treats absent and empty differently — verify against the app) —
**reopens the hole**. Treat librechat as a named, individually-verified
conversion, not part of a namespace batch.

The other two snippets (`office/nextcloud`, `office/nextcloud-whiteboard`) are
security **response** headers (HSTS/X-Frame-Options/etc.) → `ResponseHeaderModifier`,
already in `touches`.

Note the ordering consequence: **`allow-snippet-annotations: false` (the
session-2 exit criterion) cannot land until all 3 snippet users are converted**
— it is the same milestone, and librechat is on its critical path.

### 1.4 The 24 Ingresses with no TLS block, and what is out of scope

**24 of 102 Ingresses have no `tls:` block** — the same hazard class as the
phase-3 Alexa case, because the hostname-less `https-redirect` catch-all
(phase 1 §1.4a) 301s **every** host arriving on :80 once routes carry
hostnames. Split: **20 internal** (this phase) — `home-automation/ha-ai-harness`,
`matter-server`, `mosquitto`, `mqttx-web`, `node-red`, `scrypted`, `trmnl-ha`,
`zigbee2mqtt`, plus the 12 `kube-system/ak-outpost-*-forward-auth` Ingresses —
and **4 external** (phase 3) — `default/echo-server`, `flux-system/flux-webhook`,
`home-automation/home-assistant`, `home-automation/music-assistant-alexa-stream`.
Each of the 20 needs an explicit decision recorded in its batch commit:
**redirect (default, fine for anything a browser reaches over HTTPS) or exempt
(a more-specific hostname HTTPRoute that does not redirect)**. Do not let the
default apply silently to a machine-to-machine endpoint.

**Out of scope for this phase, stated so nobody "fixes" it:** 4 apps run
`hostNetwork` — `esphome`, `home-assistant`, `matter-server`,
`music-assistant-server` — because they need multicast/mDNS discovery, which
**no** gateway routes. Their web UIs still have Ingresses that convert
normally; their discovery path does not go through ingress at all and is a
separate Multus/macvlan track (`multus-macvlan-foundation`). Likewise **L4
stays on Cilium LB-IPAM** (mosquitto, plex, home-assistant, adguard DNS,
open-webui, iobroker, scrypted, traccar-osmand, wazuh-syslog and
`music-assistant-server` on 192.168.55.29/4 ports) — LoadBalancer Services are
untouched by any phase.

### 1.5 ENTRY GATE — three alerts go blind at cutover, and nothing would say so

Measured 2026-08-16: `nginx_ingress_controller_requests` has **208 series**;
`envoy_http_downstream_rq_total` has **10**. The metric namespace changes
completely at migration — it is not a relabel, it is a different vocabulary.

**Three alerting rules query `nginx_ingress_*` and simply stop evaluating** the
moment traffic leaves nginx (a PromQL expression over a metric that no longer
receives samples does not error; it just never fires):

| alert | file |
|---|---|
| `IngressNginx5xxSustained` | `kubernetes/apps/monitoring/kube-prometheus-stack/app/ingress-nginx-availability-alerts.yaml` |
| `AuthentikIngressAuthFailures` | `kubernetes/apps/monitoring/kube-prometheus-stack/app/authentik-alerts.yaml` |
| `AuthentikIngressAuthBackendError` | same file |

The last two are the **only** signal that forward-auth is failing. And
forward-auth mistranslation **fails open** (§1.2). So the failure mode this
phase is most likely to cause is precisely the one whose alerting disappears
*during* this phase. That is the 2026-08-15 DNS outage's defect repeating in a
new place: **absence of a signal scored as health.**

**This is an ENTRY GATE, not a cleanup item.** Before the first auth-protected
app is converted:

1. Author Envoy equivalents for all three (Envoy Gateway exposes
   `envoy_http_downstream_rq_total` and friends via the existing PodMonitor;
   the ext_authz path has its own counters).
2. **Prove each one fires** — deliberately trigger a 5xx and an auth failure on
   the pilot/first-batch host and watch the alert go pending→firing in
   Alertmanager. A rule that is merely `Ready` in Prometheus has not been
   tested; that is the same mistake as trusting a green rollout.
3. Keep the nginx rules in place for the whole parallel run (both stacks serve;
   both signals are wanted). They are deleted in phase 4 with their controller.

Two facts that bound this work: **14 other Authentik alerts are
controller-independent** (pod/worker/outpost/postgres/blueprint) and survive
untouched, and **0 Grafana dashboards reference nginx metrics** — dashboards
are not a concern here. The gap is exactly these three rules.

**Blackbox probes are the second half of the gate.** Only **4 `probe_success`
series** exist today (2 DNS, 2 HTTP) against 102 Ingresses. Extend them to at
least one host per batch, **added BEFORE the batch converts**, so a regression
surfaces as a probe failure rather than a household complaint. A probe added
after the fact cannot tell you whether you broke it.

## 2. Pre-checks (run once per session, before batch 1)

```bash
# phase 1 step 0 actually landed — the prerequisite this phase silently assumes
mise exec -- kubectl get cm -n network k8s-gateway -o jsonpath='{.data.Corefile}' | grep resources
#   MUST contain HTTPRoute. If it says only "Ingress Service", STOP: every
#   converted host will stop resolving instead of flipping to .103.
mise exec -- kubectl logs -n network deploy/k8s-gateway --tail=100 | grep -cE "Could not sync|failed to list"   # 0

# the external-dns gateway filter is live in the PROCESS, not just in git
mise exec -- kubectl -n network logs deploy/external-dns | grep -o 'GatewayName:[^ ]* GatewayNamespace:[^ ]*'
#   expect GatewayName:envoy-external GatewayNamespace:network

# the external record set is intact and external-dns is idle (policy: sync can DELETE)
mise exec -- kubectl -n network logs deploy/external-dns --tail=20 | grep -E 'All records|Changing record'

# baseline object counts
mise exec -- kubectl get ingress -A --no-headers | wc -l                       # 102 at start
mise exec -- kubectl get ingress -A -o jsonpath='{range .items[*]}{.spec.ingressClassName}{"\n"}{end}' | sort | uniq -c
mise exec -- kubectl get httproute -A --no-headers | wc -l
mise exec -- kubectl get gateway -n network                                    # both PROGRAMMED
# 0 firing alerts; blackbox DNS probes alive (a silent SLI reads 100%)
mise exec -- kubectl get probe -n monitoring dns-k8s-gateway-primary dns-k8s-gateway-secondary

# §1.5 ENTRY GATE — the metric vocabulary is about to change under three alerts.
# Port-forward Prometheus, then:
#   count of nginx series (baseline, will decay to 0 as batches land):
#     count(nginx_ingress_controller_requests)                # 208 on 2026-08-16
#   count of envoy series (must grow as batches land):
#     count(envoy_http_downstream_rq_total)                   # 10 on 2026-08-16
#   the three at-risk rules must have a LIVE Envoy-based counterpart loaded:
mise exec -- kubectl get prometheusrule -n monitoring -o json | python3 -c "
import sys,json
d=json.load(sys.stdin)
for r in d['items']:
    for g in r['spec']['groups']:
        for a in g.get('rules',[]):
            if 'alert' not in a: continue
            e=str(a.get('expr',''))
            if 'nginx_ingress' in e: print('NGINX-BOUND :', a['alert'])
            if 'envoy_' in e:        print('ENVOY-BOUND :', a['alert'])
"
#   expect, before the first auth conversion: an ENVOY-BOUND counterpart for
#   each of IngressNginx5xxSustained / AuthentikIngressAuthFailures /
#   AuthentikIngressAuthBackendError, each PROVEN FIRING at least once.
```

## 3. Steps

1. **Batch 1 is the DNS-leak canary.** Pick a *small* namespace (2-3 apps) and
   run the §4 negative test before batch 2 is even written. Do not queue
   several batches ahead of the first verification.
2. Batches 2..n: one namespace per commit, flux-local CI green before merge,
   homepage annotations moved in the same commit.
3. Forward-auth apps (9) one at a time, pilot-B pattern, each with its own
   authentik provider mode flip.
4. Session-2 exit: zero internal Ingresses → `allow-snippet-annotations: false`
   + `annotations-risk-level: High` on BOTH nginx HelmReleases.

## 4. Verification

Per batch: app serves via .103 (k8s-gateway flipped), auth loop OK on
converted auth apps, homepage tile intact, 0 firing alerts.

### 4.0 The test matrix (numbered so a batch commit can cite results)

All counts measured live 2026-08-16. Tests 1-3 apply to **every** converted
app; the rest apply where the annotation/behaviour is present.

**Every app, every batch**

1. **Internal DNS answer.** `dig +short @192.168.55.101 <host>.${SECRET_DOMAIN} A`
   → internal-class hosts `192.168.55.103`, external-class `192.168.55.104`
   (during the parallel run, a not-yet-converted host still answers .100/.102).
   TTL is 60, so a wrong answer is visible inside a minute — do not wait longer
   than that and call it "propagation".
2. **HTTP 200 through the NEW path, plus the app's own health endpoint.**
   "Pod Ready" is not a route test; `--resolve` to the gateway VIP so you are
   provably not still being served by nginx.
3. **`Ready=True` on the HTTPRoute AND on the parent Gateway listener.** A
   route can be `Accepted` while unattached (wrong `sectionName`, wrong
   namespace, missing ReferenceGrant):
   ```bash
   mise exec -- kubectl get httproute -n <ns> <name> -o json | python3 -c "
   import sys,json
   d=json.load(sys.stdin)
   for p in d['status']['parents']:
       print(p['parentRef'].get('name'), p['parentRef'].get('sectionName'),
             [(c['type'],c['status']) for c in p['conditions']])
   "
   # every parent must show Accepted=True AND ResolvedRefs=True
   ```

**Auth-protected hosts (the 9 remaining outposts) — mandatory**

4. **Unauthenticated request must be REFUSED** (302 into the signin flow, or
   401/403). **A 200 here means extAuth is not wired and the app is exposed.**
   Command in §4.1 below. Test the root path *and* a deep path.
5. **Authenticated round-trip completes** and lands on the app.
6. **The `auth-response-headers` equivalent actually reaches the backend.** The
   app must still see its identity headers (`X-authentik-username` et al.) — an
   app that authenticates but receives no identity header will happily serve
   **200 for the wrong user**. Check the app's own access log or an echo
   endpoint; do not infer it from "I am logged in".

**Plain-HTTP exceptions (20 internal no-TLS Ingresses, §1.4)**

7. `curl -sI http://<host>.${SECRET_DOMAIN}` must return the **app's**
   response, **not a 301**. The hostname-less `https-redirect` catch-all must
   be overridden by a more-specific hostname HTTPRoute.
8. **Control:** the catch-all still redirects everything else. The exception
   must not become the rule.

**Special behaviours, by annotation (all verified present)**

9. **WebSockets** — `ai/librechat-librechat`, `ai/open-webui`
    (`enable-websocket: true`), `office/nextcloud`,
    `office/nextcloud-whiteboard` (`websocket-services`). Open a WS connection
    and **hold it >60 s**. A broken upgrade path still serves the page fine, so
    a page-load check proves nothing.
10. **`ai/librechat-librechat` header strip** — a client-supplied
    `X-Tenant-Id` must **NOT** reach the backend
    (`curl -H 'X-Tenant-Id: attacker' ...`, then look at what the app saw).
    Load-bearing security (§1.3), currently a `configuration-snippet`.
11. **HTTPS upstreams** — `monitoring/kibana` and `security/wazuh-dashboard`
    (`backend-protocol: HTTPS`; wazuh-dashboard also `proxy-ssl-verify: off`).
    Confirm TLS-to-backend works. Plaintext-to-a-TLS-backend fails as a **502**,
    which reads like an app problem and sends you debugging the wrong thing.
12. **Large uploads** — `proxy-body-size` ×9: `office/nextcloud` (**4G**),
    `media/immich-server` (**0** = unlimited), `ai/anythingllm`,
    `ai/librechat-librechat`, `home-automation/teslamate` (100m),
    `databases/superset` (50m), `office/paperless-{ngx,ai,gpt}` (64m). Upload a
    file **larger than the Envoy default**, which is lower than every one of
    these. Untested, this surfaces weeks later as "Nextcloud won't take my
    video".
13. **Session affinity** — `affinity: cookie` ×13, and note **all 13 are the
    `kube-system/ak-outpost-*-forward-auth` Ingresses**, not app backends. So
    sticky routing is part of the **forward-auth path itself**: if it breaks,
    auth breaks intermittently (the hardest class of bug to attribute). Test it
    with the outposts scaled >1, or record explicitly that they run single-replica
    and affinity is therefore inert today.
14. **Long-poll / streaming** — `proxy-read-timeout` ×13, most at **3600s**
    (`anythingllm`, `librechat`, `open-webui`, `ha-ai-harness`, `matter-server`,
    `mosquitto`, `immich-server`, `jellyfin`, `nextcloud-whiteboard`), some at
    600/300 (`teslamate`, `paperless-gpt`, `nextcloud`, `paperless-ai`). Hold an
    **idle** connection past Envoy's default (15s) to prove the timeout was
    translated. LLM streaming responses are the daily victim here.

### 4.1 The NEGATIVE auth test (expanded from test 4)

### 4.2 The DNS-leak negative test — per batch, non-negotiably on batch 1
`Ready=True` on the HTTPRoute proves nothing about what external-dns did with
it; assert the negative outcome (SOP §10):

```bash
# for each converted internal hostname in the batch:
mise exec -- kubectl -n network logs deploy/external-dns | grep -i '<host>'   # expect: NOTHING
dig +short <host>.${SECRET_DOMAIN} @1.1.1.1                                   # expect: EMPTY
# the TXT registry record too — an A record whose k8s.a- TXT is missing is
# treated as unowned and is left behind FOREVER under policy: sync:
dig +short TXT k8s.a-<host>.${SECRET_DOMAIN} @1.1.1.1                         # expect: EMPTY

# and the positive side: the internal answer moved
mise exec -- dig +short @192.168.55.101 <host>.${SECRET_DOMAIN} A             # expect 192.168.55.103

# external record set unchanged by an internal batch
mise exec -- kubectl -n network logs deploy/external-dns --tail=20 | grep -E 'All records|Changing record'
```

If a converted internal hostname DOES appear in public DNS: stop the phase,
revert the batch, and treat it as a filter regression — the A record alone is
not enough to clean up, the `k8s.a-<host>` TXT ownership record must exist for
external-dns to ever delete it again.

A mistranslated SecurityPolicy fails open and every positive check still
passes. Prove the refusal, not the success:

```bash
# from a context with NO authentik session (fresh container / curl, no cookies):
curl -sS -o /dev/null -w '%{http_code} %{redirect_url}\n' \
     --resolve <host>.${SECRET_DOMAIN}:443:192.168.55.103 \
     https://<host>.${SECRET_DOMAIN}/
#   expect 302 -> auth.${SECRET_DOMAIN}/... (or 401/403). A 200 IS THE FAILURE.

# deep-link / non-root path too — some misattachments only cover "/":
curl -sS -o /dev/null -w '%{http_code}\n' ... https://<host>.${SECRET_DOMAIN}/<some/deep/path>
#   expect the same refusal, NOT 200

# and the positive side, in a browser with a session: the app loads AND the
# X-authentik-* headers arrive at the backend (check the app's own access log
# or an echo endpoint), i.e. headersToBackend really is wired.
```

Record the observed status code per app in the batch commit message. "Auth
works" is not a verification result; `302 -> auth.${SECRET_DOMAIN}` is.

Session-2 exit verification: `kubectl get ingress -A` shows **0** with
`className: internal`; both nginx HelmReleases show
`allow-snippet-annotations: false` in the rendered ConfigMap.

## 5. Rollback

Per app/batch: `git revert` the batch commit → the Ingress returns and
k8s-gateway flips the answer back to .100 within TTL 60. Nothing else is
touched, which is the whole reason for one-commit-per-batch.

Do **not** roll back phase 1 step 0 (`watchedResources`) to undo a phase-2
batch — that would break resolution for every already-converted host. Revert
batches; leave the resolver alone.

## 6. Interference notes

- `shared: [auth, dns]`. Nothing that restarts k8s-gateway, and nothing
  touching external-dns flags/sources, may run alongside a batch — the
  gateway filter is the only thing standing between 76 internal hostnames and
  the public zone.
- Batches that miss a session simply carry to the next; there is no
  half-migrated state that must not be left overnight (both stacks serve in
  parallel by design).
- **Not window work** (see `window: null`): 120 min against a 90 min maximum
  window, strictly sequential after phase 1. Attended project.
