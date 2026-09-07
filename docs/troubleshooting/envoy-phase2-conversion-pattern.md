# Envoy phase 2 — Ingress → HTTPRoute conversion pattern

Status: ACTIVE (2026-09-07). Delete when phase 4 completes and nginx is gone.

Derived from the phase 1 pilots, which passed. Everything here is a rule that
cost us a failure or a near-miss — follow it literally.

## The two shapes

**A. Chart is bjw-s `app-template`** (has a `route:` values key). Replace the
`ingress:` block with `route:` in the HelmRelease. Rules default to the primary
service, so `rules:` can be omitted. Reference: `echo-server` (commit 59477771).

```yaml
route:
  app:
    kind: HTTPRoute
    hostnames: ["{{ .Release.Name }}.${SECRET_DOMAIN}"]
    parentRefs:
      - group: gateway.networking.k8s.io
        kind: Gateway
        name: envoy-internal
        namespace: network
        sectionName: https
    labels:      { gethomepage.dev/enabled: "true" }
    annotations: { gethomepage.dev/... }          # move ALL of them across
```

**B. Any other chart** (no Gateway API support). Set the chart's
`ingress.enabled: false` and add a standalone `httproute.yaml` to the app dir +
its `kustomization.yaml`. Reference: `headlamp` (commit ff019ee5).

## Non-negotiable rules

1. **Ingress removal and HTTPRoute creation go in ONE commit.** k8s-gateway now
   watches both kinds. Leave both alive and the host gets two records (.100 and
   .103) and resolves non-deterministically.

2. **`sectionName: https` only.** The `http` listener is owned cluster-wide by
   `httproute-https-redirect`, which 301s every host. Attaching an app route to
   `http` fights it.

3. **Move the `gethomepage.dev/*` annotations AND the
   `gethomepage.dev/enabled: "true"` LABEL** onto the route in the same commit.
   Homepage runs `gateway: true` and `ingress: true` in parallel, so a tile
   vanishes only if the annotations are dropped, not because of the migration.

4. **Do NOT carry over `nginx.ingress.kubernetes.io/*` annotations.** They have
   no meaning on an HTTPRoute. Leave them inert in the HelmRelease behind
   `enabled: false` as the rollback target until phase 4; do not delete yet.

5. **Never point a backendRef at an ExternalName Service.** Envoy Gateway
   resolves backends through EndpointSlices; ExternalName has none. Point at
   the real Service, cross-namespace if needed (see 6).

## Forward-auth apps (9 of them) — the expensive extra

Per app: a second HTTPRoute for the callback path, a ReferenceGrant, and a
SecurityPolicy. Reference: `headlamp/app/httproute.yaml`.

6. **The ReferenceGrant MUST live in `kube-system`, NOT next to the app.** Each
   app's Flux Kustomization sets `targetNamespace: <app-ns>`, which SILENTLY
   REWRITES any `namespace:` field in that directory — the grant lands in the
   app namespace and authorises nothing. Same trap as Longhorn Volume CRs.
   Add them to `kubernetes/apps/kube-system/authentik/app/referencegrants.yaml`.

7. **Each grant needs TWO `from` entries**, and missing the second is the easy
   mistake — it leaves the app broken *and* unprotected:
   - `gateway.networking.k8s.io` / `HTTPRoute`
   - `gateway.envoyproxy.io` / `SecurityPolicy`

8. **The callback route must be SEPARATE and more specific** than the app route
   (`/outpost.goauthentik.io` vs `/`). Gateway API resolves by longest path
   match. Folded into one route, the login callback proxies to the app and loops.

9. **SecurityPolicy targets ONLY the app route.** Targeting the callback route
   makes it require the auth it exists to establish.

10. **`path: /outpost.goauthentik.io/auth/envoy`**, never `/auth/nginx`.
    Verified live: `/auth/envoy` → 302 (correct ext_authz deny), `/auth/nginx`
    and `/auth/traefik` → 500 without their dialect headers.

11. **`failOpen: false`.** An outpost outage must deny, never silently publish
    an authenticated-only app.

12. **NO Authentik change is needed.** Provider mode `forward_single` is not an
    nginx/envoy setting; a proxy outpost serves all four dialects at once. The
    plan's "switch the provider to envoy mode" step does not exist. Do not edit
    the SOPS blueprint.

## 13. The Authentik outpost publishes its OWN Ingress — this WILL break the app

Authentik's Kubernetes outpost controller creates an Ingress per forward-auth
outpost, in `kube-system`, carrying the **app's** hostname on the **default**
ingress class — and `internal` IS the default here, so it points at .100. It
holds only the `/outpost.goauthentik.io` path. It is in NO git repository and
has NO ownerRefs.

Consequence: withdrawing the app's own Ingress does not move the host to Envoy.
That outpost Ingress becomes the ONLY remaining record, k8s-gateway keeps
answering .100, nginx has no `/` route there, and **real clients get a 404
while the app is perfectly healthy on .103.** This happened to headlamp on
2026-09-07 and went unnoticed because the gate was run with `curl --resolve`.

Per app, as it converts (never in bulk — the outpost Ingress is what routes the
callback for every app still on nginx):

1. In `configmap.sops.yaml`, set on THAT outpost's `config`:
   `kubernetes_disabled_components: [ingress]`.
   The block already contains `kubernetes_disabled_components: []` — REPLACE it.
   Appending a second key is silently overridden (YAML last-wins).
2. Apply it: `kubectl exec -n kube-system deploy/authentik-worker -c worker --
   ak apply_blueprint /blueprints/<app>-blueprint.yaml`. A ConfigMap change
   alone does nothing; blueprints are applied by a periodic task.
3. Confirm it took:
   `ak shell -c "from authentik.outposts.models import Outpost;
   print(Outpost.objects.get(name='<outpost>').config.kubernetes_disabled_components)"`
4. **Delete the existing Ingress by hand.** Disabling the component stops the
   controller MANAGING it; it does not delete what is already there. Once
   disabled, the delete sticks (verified).

## Verification gate — per app, before moving on

Neither of the phase 1 failures surfaced at apply time. Check STATUS, not
reconcile success:

```bash
kubectl get httproute -n <ns> <name> -o json | \
  python3 -c "import sys,json;[print(c['type'],c['status'],c.get('reason')) \
  for p in json.load(sys.stdin)['status']['parents'] for c in p['conditions']]"
# BOTH Accepted=True AND ResolvedRefs=True. RefNotPermitted = missing grant.

kubectl get securitypolicy -n <ns> <name> -o json | grep -A3 conditions   # auth apps
dig +short @192.168.55.101 <host>            # must become 192.168.55.103

# CURL WITHOUT --resolve. This is not a style preference: --resolve pins the IP
# and therefore tests Envoy directly, bypassing the very DNS record the
# conversion is supposed to move. Gate B passed on headlamp with --resolve
# while real clients were getting a 404. Use the real name, then assert the
# remote_ip came back as .103.
curl -o /dev/null -w '%{http_code} %{remote_ip}' https://<host>/
# plain app => 200 ; forward-auth app => 302 to auth host (NEVER 200, that is a
# fail-open and means the SecurityPolicy did not attach)
```

## 14. Two corrections to shape A (found in the first batch)

- "rules can be omitted" holds ONLY with exactly one enabled Service. With two,
  `_validate.tpl` hard-fails (`An explicit rule is required...`) — write the
  rule explicitly.
- `app-template` picks the route apiVersion from Helm **Capabilities**, so an
  offline `helm template` renders `v1alpha2`, which this cluster's CRD does not
  serve. Validate with
  `--api-versions gateway.networking.k8s.io/v1/HTTPRoute`, or you are checking
  a shape the API would reject. Affects CI too (`flux-local test` runs without
  cluster capabilities).

## 15. Not one-to-one convertible — needs per-app design, do not guess

- `backend-protocol: HTTPS` + `proxy-ssl-verify: "off"` (e.g. wazuh-dashboard):
  the Gateway API equivalent is `BackendTLSPolicy`, whose v1 schema has NO
  `insecureSkipVerify` and REQUIRES `hostname`. Converting means going from no
  verification to must-verify: the backend CA has to be wired in and the SAN
  has to match. Leave as an Ingress until designed.
- `proxy-buffer-size` / `proxy-buffers-number`: maps to `ClientTrafficPolicy`,
  not to any route field.

## Rollback

Per app, `git revert <commit>`. nginx still runs and its ingress class is
untouched, so reverting restores the Ingress and DNS follows within one TTL
(60s). No CRDs are touched by phase 2, so revert is genuinely available here —
unlike the Gateway API bundle, whose ValidatingAdmissionPolicy blocks its own
rollback.
