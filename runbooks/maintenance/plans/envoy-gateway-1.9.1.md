---
plan_id: envoy-gateway-1.9.1
component: envoy-gateway
pr: null                            # Renovate is denied from touching this chart at all
                                    # (auto-update-policy.yaml `*envoy-gateway*` /
                                    # `*gateway-helm*` catch-alls) — no PR exists; this is
                                    # a direct-bump plan per the coverage.py pattern.
kind: chart
current: "1.9.0"                    # gateway-helm chart == appVersion v1.9.0, live 20d
                                    # (phase 0.5, 2026-08-16)
target: "1.9.1"                     # gateway-helm chart == appVersion v1.9.1
update_type: patch
risk: low                           # See §1 "Why held vs. why this instance is low risk".
                                    # Technically trivial (image-only + one unused-field
                                    # CRD tightening, zero live traffic); the component
                                    # FAMILY stays on the deny-list for good reason and
                                    # this plan does not argue otherwise.
est_duration_min: 25
needs_reboot: false
touches:
  namespaces: [network]
  resources:
    - "helmrelease/envoy-gateway (network): chart gateway-helm 1.9.0 -> 1.9.1"
    - "kustomization/envoy-gateway-crds (network): re-vendored gateway.envoyproxy.io_securitypolicies + _envoyextensionpolicies CRDs (schema tightening + doc text only — see §1.2)"
    - "deployment/envoy-gateway (network): control-plane pod restart, image envoyproxy/gateway v1.9.0 -> v1.9.1"
    - "deployment/envoy-internal, deployment/envoy-external (network): data-plane Envoy pods restart, default proxy image envoyproxy/envoy distroless-v1.39.0 -> v1.39.1 (controller-managed, not directly in the HelmRelease)"
  shared: []                        # NOT [ingress] today — verified live: exactly 1
                                    # HTTPRoute cluster-wide (hostname-less
                                    # network/https-redirect), 0 apps route through EG,
                                    # ingress-nginx still serves all 102 Ingresses. See
                                    # §6 for why this stops being true once phase 1 runs.
depends_on: []
conflicts_with: [envoy-gateway-phase1]   # both touch helmrelease/envoy-gateway +
                                          # crds/envoy-gateway-crds; don't run in the
                                          # same session as phase1 pilot work
security_ref: null
capability_change: false            # no user/app-visible behaviour changes — nothing
                                    # routes through EG yet, and the only CRD schema
                                    # change tightens a field (`SecurityPolicy.spec.oidc.
                                    # provider.issuer`) that no SecurityPolicy CR in this
                                    # cluster uses (0 SecurityPolicy CRs exist — verified)
rollback_class: git-revert
finding_refs: []
status: draft
window: null                        # window agent assigns; note in §6 this plan is
                                    # small enough to actually fit a normal window,
                                    # unlike the phase1-4 chain
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/k8s-gateway-dns.md
generated: "2026-09-05"
---

# Envoy Gateway — chart 1.9.0 -> 1.9.1 (patch)

## 1. Summary & why held

**Why the hold fired at all:** `runbooks/auto-update-policy.yaml` carries three
deny rules that all match this component — `*gateway-helm*`, `*gateway-crds-helm*`,
and the explicit catch-all `*envoy-gateway*` ("Catch-all for Envoy Gateway
artifacts (image/chart aliases) — same hold as gateway-helm"). That catch-all is
exactly the "why held" text given for this update. It exists because (a) EG
v1.7.0 shipped an ext-auth regression (`envoyproxy/gateway#8202`) that broke
redirect auth, and this stack is the planned forward-auth path for Authentik
from Phase 1 on, and (b) every prior EG chart bump has dragged the Gateway API
CRD channel with it, which is the exact mechanism that caused the 2026-08-15
full internal-DNS outage (`docs/sops/k8s-gateway-dns.md` §8). **This family
stays on the deny-list; this plan does not argue for removing the hold**, only
for what this one instance requires.

**Relationship to the in-flight migration (read first):** `envoy-gateway-phase1`
through `phase4` (`runbooks/maintenance/plans/envoy-gateway-phase{1,2,3,4}.md`,
all `status: reference`, attended/unwindowed) are the approved Envoy Gateway
migration replacing EOL ingress-nginx. I read all four before writing this.
**None of them own or reference a 1.9.0 -> 1.9.1 bump** — phase 0.5 (already
executed, `22f38e36`/`aa5db834`) took the chart from 1.8.3 to exactly 1.9.0 and
stopped there; phase1 §1.1's "verified starting state" table cites chart
**1.9.0** as the given baseline; phases 2-4 don't touch the chart version at
all. So this is **case (c) from the dispatch brief: a genuine standalone
bump**, not a duplicate and not a fold-in. It also isn't a prerequisite for
phase 1 — phase 1's step 0 is about `k8s-gateway` `watchedResources`, unrelated
to the EG chart version.

**Why this instance is low risk despite the family-wide hold** (verified
2026-09-05 by pulling and diffing both OCI charts locally — `helm pull
oci://docker.io/envoyproxy/gateway-helm --version {1.9.0,1.9.1}` and the
`gateway-crds-helm` counterpart):

1. **No Gateway API CRD channel move.** Every file the `gateway-api-standard.yaml`
   vendoring step produces (`crds/gateway-api-standard.yaml`, standard-channel
   `HTTPRoute`/`Gateway`/`GatewayClass`/etc.) is **byte-identical** between
   1.9.0 and 1.9.1. The bundle stays at v1.6.1. This is the specific hazard the
   deny-rule reasons for `*gateway-helm*`/`*gateway-crds-helm*` call out ("a
   chart bump drags the Gateway API CRD channel with it") — **it does not apply
   to this bump.**
2. **k8s-gateway is unaffected.** k8s-gateway's informers only react to Gateway
   API CRDs (§1 above — unchanged) and today watch only `["Ingress","
   Service"]` (HTTPRoute isn't added until phase 1 step 0, not yet run — only
   1 HTTPRoute exists cluster-wide, `network/https-redirect`, and it's
   hostname-less). No restart-and-verify DNS gate is required for this plan.
3. **Envoy Gateway's own CRDs change, but narrowly.** Diffing
   `gateway-crds-helm`'s rendered templates, exactly two files differ:
   - `gateway.envoyproxy.io_securitypolicies.yaml`: `SecurityPolicy.spec.oidc.
     provider.issuer` goes from `minLength: 1` to a pattern requiring an
     `https://` scheme (`^https://[^/?#@]+(/[^?#]*)?$`). **Zero SecurityPolicy
     CRs exist in this cluster today** (verified: `kubectl get securitypolicy -A`
     returns nothing — phase 1's headlamp pilot, which would be the first
     consumer, hasn't executed). Nothing this bump touches uses the `oidc`
     field at all; the planned forward-auth pattern (phase 1 §1.2) uses
     `extAuth.http`, a different field entirely.
   - `gateway.envoyproxy.io_envoyextensionpolicies.yaml`: description-text-only
     change (two doc strings reworded for clarity). No schema change.
4. **Image-only for everything else.** `values.yaml` / `_helpers.tpl` diffs are
   exactly: control-plane image `envoyproxy/gateway:v1.9.0 -> v1.9.1`, default
   ratelimit sidecar tag `17b1956c -> 8fe6ea42` (inert — rate limiting isn't
   configured), default Envoy proxy image `distroless-v1.39.0 -> v1.39.1`.
5. **Zero live traffic (re-verified 2026-09-05):** `kubectl get httproute -A`
   returns exactly 1 object (`network/https-redirect`, hostname-less);
   `ingress-nginx` still serves all 102 app Ingresses. Both gateways
   (`envoy-internal` 192.168.55.103, `envoy-external` 192.168.55.104) are
   `PROGRAMMED=True`, 19-20d old, 0/0 restarts on the data-plane pods. A bad
   rollout here breaks nothing user-facing — this is the same "cheapest to
   revert" argument phase 0.5 used for the 1.8.3->1.9.0 bump, and it still
   holds.

Net: this bump is a smaller, lower-risk version of what phase 0.5 already did
safely. Recommend running it **before** phase 1 starts routing real traffic,
to keep chart/CRD bumps decoupled from live-route risk (the same pattern the
migration itself has followed throughout).

## 2. Pre-checks

```bash
# confirm the exact starting point this plan assumes
mise exec -- kubectl get deploy -n network envoy-gateway -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
#   expect: docker.io/envoyproxy/gateway:v1.9.0
mise exec -- kubectl get gateway -n network
#   expect: envoy-internal .103 / envoy-external .104, both PROGRAMMED=True
mise exec -- kubectl get httproute -A --no-headers | wc -l
#   expect: 1 (network/https-redirect, hostname-less) — if this is >1, phase 1
#   has started; re-check for interference with envoy-gateway-phase1 before proceeding
mise exec -- kubectl get securitypolicy -A
#   expect: no resources found (confirms §1 point 3 — nothing uses .spec.oidc)
mise exec -- kubectl get ingress -A --no-headers | wc -l
#   expect: 102 (nginx still serves everything; EG carries none of it)

# confirm 1.9.1 is actually published (already done once during planning; re-verify at execution time)
helm show chart oci://docker.io/envoyproxy/gateway-helm --version 1.9.1 | grep -E '^(version|appVersion):'
#   expect: version: 1.9.1 / appVersion: v1.9.1

# 0 firing alerts before touching anything
mise exec -- kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &
curl -s http://localhost:9090/api/v1/alerts | grep -o '"alertname":"[^"]*"' | grep -vE 'Watchdog|InfoInhibitor' | sort -u
```

## 3. Steps

1. Edit `kubernetes/apps/network/envoy-gateway/app/helmrelease.yaml`: bump
   `spec.chart.spec.version: 1.9.0` -> `1.9.1`. Update the version-history
   comment block above it (follow the existing style — it already documents
   the 1.8.3->1.9.0 rationale; append the 1.9.0->1.9.1 line noting "patch,
   image-only + unused-field CRD tightening, no Gateway API CRD channel move,
   zero live traffic").
2. Re-vendor the Envoy-Gateway-owned CRDs (this is the step that is easy to
   forget — the chart version bump alone does NOT update
   `crds/envoy-gateway.yaml`, which is applied by the separate
   `envoy-gateway-crds` Flux Kustomization, not by Helm):
   ```bash
   mise exec -- bash kubernetes/apps/network/envoy-gateway/crds/revendor.sh 1.9.1
   git diff --stat kubernetes/apps/network/envoy-gateway/crds/
   #   expect: gateway-api-standard.yaml UNCHANGED (0 diff — confirms no channel
   #   move); envoy-gateway.yaml changed (the securitypolicies/
   #   envoyextensionpolicies tightening from §1.2/§1.3 above)
   ```
   If `gateway-api-standard.yaml` shows ANY diff, STOP — that means the
   Gateway API CRD channel moved between what was analyzed here and what
   revendor.sh actually pulled at execution time (a chart re-release can
   happen). Treat that as a materially different, higher-risk change and do
   not proceed on this plan's low-risk rating; escalate to attended review
   the way phase 0.5 was handled.
3. `task kubeconform` (or `kubeconform -summary -exit-on-error
   -ignore-missing-schemas kubernetes/apps/network/envoy-gateway/`) locally
   before committing.
4. Commit both changes together (`git commit --only
   kubernetes/apps/network/envoy-gateway/app/helmrelease.yaml
   kubernetes/apps/network/envoy-gateway/crds/ -m '...'` — see the shared-worktree
   rule in CLAUDE.md, use `--only` with explicit paths) and push. Flux
   reconciles `envoy-gateway-crds` first (it's the `dependsOn` for the app
   Kustomization, `wait: true`), then `envoy-gateway`.
5. Watch the rollout:
   ```bash
   mise exec -- flux get kustomization -n network envoy-gateway-crds envoy-gateway
   mise exec -- kubectl rollout status -n network deploy/envoy-gateway
   mise exec -- kubectl get pods -n network -l app.kubernetes.io/name=envoy-gateway -o wide
   ```
6. The data-plane Envoy proxy Deployments (`envoy-internal`, `envoy-external`)
   are controller-managed, not Flux-managed directly — confirm the EG
   controller rolls them onto the new default proxy image after it restarts:
   ```bash
   mise exec -- kubectl get deploy -n network envoy-internal envoy-external -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.spec.template.spec.containers[?(@.name=="envoy")].image}{"\n"}{end}'
   #   expect both to show distroless-v1.39.1 once the controller has reconciled
   #   (may take a few minutes after the control-plane pod comes up healthy)
   ```

## 4. Verification

- **Flux green:** both Kustomizations `Ready=True`; HelmRelease `envoy-gateway`
  `Ready=True` at chart 1.9.1.
- **Image versions land:**
  ```bash
  mise exec -- kubectl get deploy -n network envoy-gateway -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
  #   expect: docker.io/envoyproxy/gateway:v1.9.1
  ```
- **CRD schema landed** (CONTENTS ASSERTION, not shape — a `Ready` Kustomization
  proves apply succeeded, not that the new schema is the one being served):
  ```bash
  mise exec -- kubectl get crd securitypolicies.gateway.envoyproxy.io -o jsonpath='{.spec.versions[0].schema.openAPIV3Schema.properties.spec.properties.oidc.properties.provider.properties.issuer.pattern}{"\n"}'
  #   expect: ^https://[^/?#@]+(/[^?#]*)?$  (was empty/absent under minLength before)
  ```
- **Gateways still Programmed, addresses unchanged:**
  ```bash
  mise exec -- kubectl get gateway -n network
  #   expect: envoy-internal 192.168.55.103 / envoy-external 192.168.55.104, both PROGRAMMED=True
  ```
- **The one live route survives and still does its job** (the only real traffic
  behaviour this stack has today):
  ```bash
  curl -sI --resolve <any-host-on-envoy>.${SECRET_DOMAIN}:80:192.168.55.103 http://<any-host-on-envoy>.${SECRET_DOMAIN}/
  #   expect: 301 -> https://... (https-redirect catch-all still functioning)
  ```
  There is no positive "app served via EG" test possible yet — nothing routes
  through it. That is expected and matches the pre-phase-1 state; do not
  invent a traffic test that doesn't exist yet.
- **0 firing alerts**, in particular check `envoy-gateway-alerts.yaml`'s rules
  and the PodMonitor scrape (`kubernetes/apps/network/envoy-gateway/app/podmonitor.yaml`)
  didn't go dark across the restart:
  ```bash
  curl -s http://localhost:9090/api/v1/targets | python3 -c "
  import sys,json
  t=json.load(sys.stdin)['data']['activeTargets']
  print([x['health'] for x in t if 'envoy' in x.get('labels',{}).get('job','')])"
  ```
- **k8s-gateway untouched** (confirms §1 point 2 held in practice, not just on
  paper):
  ```bash
  mise exec -- kubectl get pods -n network -l app.kubernetes.io/name=k8s-gateway -o jsonpath='{.items[0].status.startTime}{"\n"}'
  #   expect: UNCHANGED from before this plan ran (k8s-gateway must not have restarted)
  mise exec -- kubectl logs -n network deploy/k8s-gateway --tail=50 | grep -cE "Could not sync|failed to list"   # expect 0
  ```

## 5. Rollback

```bash
git revert <chart-bump-commit>
git push
mise exec -- flux reconcile kustomization envoy-gateway-crds -n network --with-source
mise exec -- flux reconcile kustomization envoy-gateway -n network --with-source
mise exec -- kubectl get deploy -n network envoy-gateway -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
#   confirm back to docker.io/envoyproxy/gateway:v1.9.0
```
No CRD-version-floor rollback trap applies here (that trap, documented in
phase1 §1.1, is specific to the Gateway API standard-channel
`ValidatingAdmissionPolicy`, which this bump does not touch — confirmed by the
byte-identical `gateway-api-standard.yaml` diff in §1). A plain revert is
sufficient in both directions.

## 6. Interference notes

- `shared: []` is accurate **today** — verified zero apps route through EG.
  **This changes the moment phase 1 executes.** Once even one HTTPRoute
  carries real traffic, any future envoy-gateway chart bump becomes a
  `shared: [ingress]` change and needs the phase-2/3-style negative-test
  discipline (auth fail-open checks, DNS-leak checks) that this plan
  deliberately does not need yet. Don't copy this plan's low-risk shape
  forward without re-deriving it against the live-traffic state at that time.
- `conflicts_with: [envoy-gateway-phase1]` — both modify
  `helmrelease/envoy-gateway` and the `envoy-gateway-crds` Kustomization; don't
  run this in the same session as phase 1 pilot work. No ordering requirement
  the other way: this plan can run before or after phase 1 with no functional
  dependency, but running it **before** is recommended (§1) to keep the
  version bump decoupled from live-route risk, matching how phase 0.5 was
  sequenced.
- **Not a DNS-control-plane change** — unlike phase 1 step 0 / phase 4 steps
  2-3, this plan does not touch `k8s-gateway`, `external-dns`, CoreDNS or
  AdGuard, and does not require their restart-and-verify gates. Verification
  §4's k8s-gateway check exists only to prove that stays true in practice.
- If `runbooks/auto-update-policy.yaml`'s three envoy-gateway deny rules are
  ever revisited, this plan is evidence for narrowing scope (e.g. exempting
  patch bumps that don't move the CRD channel) — but that is a policy change
  for the operator to make deliberately, not something this plan proposes or
  should be read as arguing for by itself.
